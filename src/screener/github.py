import asyncio
import re
from datetime import datetime, timedelta, timezone

import httpx

from .cache import JsonCache
from .config import GitHubConfig
from .models import GitHubActivity, GitHubStatus, RepoInfo

RELEVANT_REPO_RE = re.compile(
    r"\b(llm|rag|agents?|agentic|langchain|langgraph|gpt|ai|ml|embeddings?|vector|chatbot|retrieval|nlp)\b",
    re.IGNORECASE,
)
ACTIVITY_EVENTS = {"PushEvent", "PullRequestEvent"}


class GitHubClient:
    """Two calls per username (repos + public events), de-duplicated within a run and cached on disk."""

    def __init__(self, cfg: GitHubConfig, cache: JsonCache | None = None, http: httpx.AsyncClient | None = None):
        self.cfg = cfg
        self.cache = cache
        self._http = http
        self._owns_http = http is None
        self._inflight: dict[str, asyncio.Task] = {}
        self._semaphore = asyncio.Semaphore(cfg.max_concurrency)
        self._rate_limited = False

    async def __aenter__(self) -> "GitHubClient":
        if self._http is None:
            headers = {"Accept": "application/vnd.github+json", "User-Agent": "resume-screener"}
            if self.cfg.token:
                headers["Authorization"] = f"Bearer {self.cfg.token}"
            self._http = httpx.AsyncClient(base_url=self.cfg.api_url, headers=headers, timeout=self.cfg.timeout_s)
        return self

    async def __aexit__(self, *exc) -> None:
        if self._owns_http and self._http is not None:
            await self._http.aclose()
        if self.cache:
            self.cache.save()

    async def fetch(self, username: str | None) -> GitHubActivity:
        if not username:
            return GitHubActivity(status=GitHubStatus.NO_PROFILE)
        key = username.lower()
        if key not in self._inflight:
            self._inflight[key] = asyncio.create_task(self._fetch(username))
        return await self._inflight[key]

    async def _fetch(self, username: str) -> GitHubActivity:
        cached = self.cache.get(username.lower()) if self.cache else None
        if cached:
            return GitHubActivity.model_validate(cached)
        if self._rate_limited:
            return GitHubActivity(username=username, status=GitHubStatus.RATE_LIMITED, error="skipped: rate limit hit earlier in run")

        async with self._semaphore:
            try:
                resp = await self._http.get(
                    f"/users/{username}/repos", params={"type": "owner", "sort": "pushed", "per_page": 100}
                )
            except httpx.HTTPError as exc:
                return GitHubActivity(username=username, status=GitHubStatus.ERROR, error=f"{type(exc).__name__}: {exc}")
            activity = self._to_activity(username, resp)
            if activity.status == GitHubStatus.OK:
                activity.active_days_90d = await self._active_days(username)

        if self.cache and activity.status in (GitHubStatus.OK, GitHubStatus.NOT_FOUND):
            self.cache.set(username.lower(), activity.model_dump(mode="json"))
        return activity

    async def _active_days(self, username: str) -> int | None:
        """Best effort: the repos call already succeeded, so a failure here only loses this one signal."""
        try:
            resp = await self._http.get(f"/users/{username}/events/public", params={"per_page": 100})
        except httpx.HTTPError:
            return None
        if self._is_rate_limited(resp):
            self._rate_limited = True
            return None
        if resp.status_code != 200:
            return None
        cutoff = datetime.now(timezone.utc) - timedelta(days=self.cfg.activity_window_days)
        days = {
            e["created_at"][:10] for e in resp.json()
            if e.get("type") in ACTIVITY_EVENTS and _parse_time(e.get("created_at")) >= cutoff
        }
        return len(days)

    @staticmethod
    def _is_rate_limited(resp: httpx.Response) -> bool:
        return resp.status_code == 429 or (resp.status_code == 403 and resp.headers.get("x-ratelimit-remaining") == "0")

    def _to_activity(self, username: str, resp: httpx.Response) -> GitHubActivity:
        if resp.status_code == 404:
            return GitHubActivity(username=username, status=GitHubStatus.NOT_FOUND, error="profile not found")
        if self._is_rate_limited(resp):
            self._rate_limited = True
            return GitHubActivity(username=username, status=GitHubStatus.RATE_LIMITED, error="GitHub API rate limit reached")
        if resp.status_code != 200:
            return GitHubActivity(username=username, status=GitHubStatus.ERROR, error=f"HTTP {resp.status_code}")
        try:
            repos = [
                RepoInfo(
                    name=r["name"],
                    language=r.get("language"),
                    description=r.get("description"),
                    topics=r.get("topics") or [],
                    fork=r.get("fork", False),
                    archived=r.get("archived", False),
                    pushed_at=r.get("pushed_at"),
                    stars=r.get("stargazers_count", 0),
                )
                for r in resp.json()
            ]
        except (ValueError, KeyError, TypeError) as exc:
            return GitHubActivity(username=username, status=GitHubStatus.ERROR, error=f"unexpected response: {exc}")
        return GitHubActivity(username=username, status=GitHubStatus.OK, repos=repos)


def _parse_time(timestamp: str | None) -> datetime:
    if not timestamp:
        return datetime.min.replace(tzinfo=timezone.utc)
    return datetime.fromisoformat(timestamp.replace("Z", "+00:00"))


def _days_since(timestamp: str | None, now: datetime) -> float | None:
    return (now - _parse_time(timestamp)).total_seconds() / 86400 if timestamp else None


def is_relevant_repo(repo: RepoInfo) -> bool:
    haystack = " ".join([repo.name.replace("-", " ").replace("_", " "), repo.description or "", *repo.topics])
    return repo.language == "Python" or bool(RELEVANT_REPO_RE.search(haystack))


def _tier(value: float, tiers: tuple[tuple[int, int], ...]) -> int:
    """First (threshold, points) with value >= threshold."""
    return next((points for threshold, points in tiers if value >= threshold), 0)


def _recency_tier(days: float | None, tiers: tuple[tuple[int, int], ...]) -> int:
    """First (max_days, points) with days <= max_days."""
    return 0 if days is None else next((points for max_days, points in tiers if days <= max_days), 0)


def _max_points(tiers: tuple[tuple[int, int], ...]) -> int:
    return max(points for _, points in tiers)


def score_github(
    activity: GitHubActivity, cfg: GitHubConfig | None = None, now: datetime | None = None
) -> tuple[float, str, list[str]]:
    """Recent activity (push recency + active days) + maintained/relevant repos; tiers come from GitHubConfig."""
    cfg = cfg or GitHubConfig()
    failures = {
        GitHubStatus.NO_PROFILE: "No GitHub profile on resume (0 points, not a rejection).",
        GitHubStatus.NOT_FOUND: f"GitHub profile '{activity.username}' not found or private.",
        GitHubStatus.RATE_LIMITED: "GitHub enrichment skipped: API rate limit reached.",
        GitHubStatus.ERROR: f"GitHub enrichment failed: {activity.error}.",
    }
    if activity.status != GitHubStatus.OK:
        return 0.0, failures[activity.status], [failures[activity.status]]

    now = now or datetime.now(timezone.utc)
    own = [r for r in activity.repos if not r.fork]
    if not own:
        return 0.0, "GitHub profile has no original public repositories.", ["No original (non-fork) public repos: 0"]

    window = cfg.activity_window_days
    ages = [d for d in (_days_since(r.pushed_at, now) for r in own) if d is not None]
    latest = min(ages, default=None)
    recency = _recency_tier(latest, cfg.push_recency_tiers)

    consistency_max = _max_points(cfg.active_day_tiers)
    if activity.active_days_90d is not None:
        consistency = _tier(activity.active_days_90d, cfg.active_day_tiers)
        consistency_line = (
            f"{activity.active_days_90d} active day(s) with pushes/PRs in the last {window} days: "
            f"+{consistency}/{consistency_max}"
        )
    else:
        recent_repos = sum(1 for d in ages if d <= window)
        consistency = _tier(recent_repos, cfg.recent_repo_tiers)
        consistency_line = f"events unavailable; {recent_repos} repo(s) pushed in last {window} days: +{consistency}/{consistency_max}"

    maintained = [
        r for r in own if not r.archived and (_days_since(r.pushed_at, now) or 1e9) <= cfg.maintained_window_days
    ]
    relevant = [r for r in maintained if is_relevant_repo(r)]
    maintained_pts = _tier(len(maintained), cfg.maintained_repo_tiers)
    relevant_pts = _tier(len(relevant), cfg.relevant_repo_tiers)

    recency_max = _max_points(cfg.push_recency_tiers)
    reasons = [
        f"Latest push {latest:.0f} days ago: +{recency}/{recency_max}" if latest is not None else f"No push dates: +0/{recency_max}",
        consistency_line,
        f"{len(maintained)} original repo(s) updated in the last year: +{maintained_pts}/{_max_points(cfg.maintained_repo_tiers)}",
        f"{len(relevant)} of them Python/AI-relevant ({', '.join(r.name for r in relevant[:4]) or 'none'}): "
        f"+{relevant_pts}/{_max_points(cfg.relevant_repo_tiers)}",
    ]
    days = f", active on {activity.active_days_90d} day(s) in the last {window}" if activity.active_days_90d is not None else ""
    summary = (
        f"Last push {latest:.0f} days ago{days}; {len(maintained)} repo(s) maintained this year, "
        f"{len(relevant)} Python/AI-relevant."
    ) if latest is not None else "No recent pushes."
    return float(recency + consistency + maintained_pts + relevant_pts), summary, reasons
