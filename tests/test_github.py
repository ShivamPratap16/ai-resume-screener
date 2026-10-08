import asyncio
from datetime import datetime, timedelta, timezone

import httpx

from screener.config import GitHubConfig
from screener.github import GitHubClient, score_github
from screener.models import GitHubActivity, GitHubStatus, RepoInfo
from screener.pipeline import _fetch_github

from conftest import make_resume

NOW = datetime(2026, 10, 1, tzinfo=timezone.utc)


def _repo(name, days_ago, language="Python", fork=False, archived=False, description=None):
    pushed = (NOW - timedelta(days=days_ago)).isoformat().replace("+00:00", "Z")
    return RepoInfo(name=name, language=language, fork=fork, archived=archived, pushed_at=pushed, description=description)


def _activity(repos, active_days=None):
    return GitHubActivity(username="x", status=GitHubStatus.OK, repos=repos, active_days_90d=active_days)


def test_active_relevant_profile_gets_full_points():
    repos = [_repo("rag-bot", 3), _repo("agent-lab", 20), _repo("llm-evals", 40), _repo("vector-db", 60, "Go")]
    points, summary, reasons = score_github(_activity(repos, active_days=12), now=NOW)
    assert points == 10
    assert "last push 3 days ago" in summary.lower()
    assert len(reasons) == 4 and all("+" in r for r in reasons)


def test_one_recent_push_scores_lower_than_steady_activity():
    repos = [_repo("rag-bot", 3)]
    steady, _, _ = score_github(_activity(repos, active_days=12), now=NOW)
    single, _, _ = score_github(_activity(repos, active_days=1), now=NOW)
    assert steady > single


def test_falls_back_to_repo_dates_when_events_unavailable():
    points, _, reasons = score_github(_activity([_repo("a", 5), _repo("b", 10), _repo("c", 20)]), now=NOW)
    assert "events unavailable" in reasons[1]
    assert points == 3 + 2 + 2 + 2


def test_forks_and_stale_repos_do_not_count():
    repos = [_repo("forked-langchain", 1, fork=True), _repo("old", 900)]
    points, _, _ = score_github(_activity(repos, active_days=0), now=NOW)
    assert points == 0


def test_failures_score_zero_with_reason():
    for status in (GitHubStatus.NO_PROFILE, GitHubStatus.NOT_FOUND, GitHubStatus.RATE_LIMITED, GitHubStatus.ERROR):
        points, summary, reasons = score_github(GitHubActivity(username="x", status=status, error="boom"), now=NOW)
        assert points == 0 and summary and reasons


def _client(handler) -> GitHubClient:
    http = httpx.AsyncClient(transport=httpx.MockTransport(handler), base_url="https://api.github.com")
    return GitHubClient(GitHubConfig(token=None), cache=None, http=http)


def test_client_parses_repos_and_dedupes_calls():
    calls = []

    def handler(request):
        calls.append(request.url.path)
        if request.url.path.endswith("/events/public"):
            return httpx.Response(200, json=[])
        return httpx.Response(200, json=[{"name": "rag", "language": "Python", "pushed_at": "2026-09-30T00:00:00Z"}])

    async def run():
        async with _client(handler) as gh:
            return await asyncio.gather(gh.fetch("Dev"), gh.fetch("dev"))

    first, second = asyncio.run(run())
    assert first.status == GitHubStatus.OK and first.repos[0].name == "rag"
    assert second is first
    assert calls == ["/users/Dev/repos", "/users/Dev/events/public"]


def test_not_found_and_missing_username():
    async def run():
        async with _client(lambda r: httpx.Response(404)) as gh:
            return await gh.fetch("ghost"), await gh.fetch(None)

    missing, none = asyncio.run(run())
    assert missing.status == GitHubStatus.NOT_FOUND
    assert none.status == GitHubStatus.NO_PROFILE


def test_rate_limit_stops_further_requests():
    calls = []

    def handler(request):
        calls.append(request.url.path)
        return httpx.Response(403, headers={"x-ratelimit-remaining": "0"})

    async def run():
        async with _client(handler) as gh:
            return await gh.fetch("a"), await gh.fetch("b")

    a, b = asyncio.run(run())
    assert a.status == b.status == GitHubStatus.RATE_LIMITED
    assert len(calls) == 1


def test_network_error_is_recorded_not_raised():
    def handler(request):
        raise httpx.ConnectTimeout("timed out")

    async def run():
        async with _client(handler) as gh:
            return await gh.fetch("slow")

    assert asyncio.run(run()).status == GitHubStatus.ERROR


def test_falls_back_to_second_linked_profile_when_first_is_missing():
    def handler(request):
        if "old-handle" in request.url.path:
            return httpx.Response(404)
        return httpx.Response(200, json=[])

    resume = make_resume("Jane Doe\ngithub.com/old-handle | github.com/new-handle\n")

    async def run():
        async with _client(handler) as gh:
            return await _fetch_github(resume, gh)

    activity = asyncio.run(run())
    assert activity.status == GitHubStatus.OK and activity.username == "new-handle"


def test_active_days_count_distinct_recent_push_days():
    today = datetime.now(timezone.utc)
    stamp = lambda days: (today - timedelta(days=days)).isoformat().replace("+00:00", "Z")
    events = [
        {"type": "PushEvent", "created_at": stamp(1)},
        {"type": "PushEvent", "created_at": stamp(1)},
        {"type": "PullRequestEvent", "created_at": stamp(5)},
        {"type": "WatchEvent", "created_at": stamp(2)},
        {"type": "PushEvent", "created_at": stamp(200)},
    ]

    def handler(request):
        if request.url.path.endswith("/events/public"):
            return httpx.Response(200, json=events)
        return httpx.Response(200, json=[])

    async def run():
        async with _client(handler) as gh:
            return await gh.fetch("dev")

    assert asyncio.run(run()).active_days_90d == 2


def test_events_failure_keeps_repo_data():
    def handler(request):
        if request.url.path.endswith("/events/public"):
            return httpx.Response(500)
        return httpx.Response(200, json=[{"name": "rag", "pushed_at": "2026-09-30T00:00:00Z"}])

    async def run():
        async with _client(handler) as gh:
            return await gh.fetch("dev")

    activity = asyncio.run(run())
    assert activity.status == GitHubStatus.OK and activity.active_days_90d is None and activity.repos
