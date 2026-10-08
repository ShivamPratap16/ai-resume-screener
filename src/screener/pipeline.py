import asyncio
import logging
import time
from collections.abc import Callable
from concurrent.futures import ProcessPoolExecutor
from concurrent.futures.process import BrokenProcessPool
from pathlib import Path

from .cache import JsonCache
from .config import Settings
from .eligibility import check_eligibility
from .github import GitHubClient, score_github
from .ingest import ExtractionError, discover, extract_text, file_hash
from .llm import LLMService, ResumeReviewer, build_reviewer
from .models import (
    BatchSummary, EligibilityResult, FailedFile, GitHubActivity, GitHubStatus, LLMReview, ParsedResume,
    RankedCandidate, RejectedCandidate, ScreeningReport,
)
from .parser import parse_resume
from .scoring import matched_skills, score_candidate

log = logging.getLogger(__name__)


def extract_and_parse(path: Path, data: bytes, digest: str, min_chars: int) -> ParsedResume:
    """Runs inside a worker process, so a pathological file can be timed out and killed."""
    text = extract_text(path, data)
    if len(text.strip()) < min_chars:
        raise ExtractionError("No extractable text (empty or scanned/image-only document)")
    return parse_resume(path, text, digest)


def load_resumes(
    input_dir: Path, settings: Settings, worker: Callable[..., ParsedResume] = extract_and_parse
) -> tuple[list[ParsedResume], list[FailedFile]]:
    """Parse every file; anything that can't be used becomes a failed/duplicate record, never an exception."""
    failed: list[FailedFile] = []
    jobs: list[tuple[Path, bytes, str]] = []
    seen_hashes: dict[str, str] = {}

    for path in discover(input_dir):
        if path.suffix.lower() not in settings.supported_extensions:
            failed.append(FailedFile(file=path.name, status="failed", error=f"Unsupported file type '{path.suffix}'"))
            continue
        try:
            data = path.read_bytes()
        except OSError as exc:
            failed.append(FailedFile(file=path.name, status="failed", error=f"Could not read file: {exc}"))
            continue
        digest = file_hash(data)
        if digest in seen_hashes:
            failed.append(FailedFile(file=path.name, status="duplicate", error=f"Identical file content to {seen_hashes[digest]}"))
            continue
        seen_hashes[digest] = path.name
        jobs.append((path, data, digest))

    parsed: list[ParsedResume] = []
    seen_emails: dict[str, str] = {}
    timeout = settings.parse_timeout_s
    pool = ProcessPoolExecutor(max_workers=settings.parse_workers)
    try:
        futures = [(job, pool.submit(worker, *job, settings.min_text_chars)) for job in jobs]
        for job, future in futures:
            path = job[0]
            outcome = _attempt(path, lambda: future.result(timeout=timeout), timeout)
            if outcome is None:
                # A crash kills the whole pool, failing every queued file; retry alone to find the real culprit.
                outcome = _attempt(path, lambda: _run_alone(worker, job, settings), timeout) or FailedFile(
                    file=path.name, status="failed", error="Parser worker crashed on this file"
                )
            if isinstance(outcome, FailedFile):
                failed.append(outcome)
                continue

            email = outcome.email.lower() if outcome.email else None
            if email and email in seen_emails:
                failed.append(FailedFile(file=path.name, status="duplicate", error=f"Same candidate email as {seen_emails[email]}"))
                continue
            if email:
                seen_emails[email] = path.name
            parsed.append(outcome)
    finally:
        _shutdown(pool)
    return parsed, failed


def _attempt(path: Path, get_result: Callable[[], ParsedResume], timeout: float) -> ParsedResume | FailedFile | None:
    """Turns every failure into a FailedFile; None means the worker pool died."""
    try:
        return get_result()
    except TimeoutError:
        return FailedFile(file=path.name, status="failed", error=f"Timed out after {timeout:g}s while parsing")
    except ExtractionError as exc:
        return FailedFile(file=path.name, status="failed", error=str(exc))
    except BrokenProcessPool:
        return None
    except Exception as exc:
        log.warning("Parser error on %s: %s", path.name, exc)
        return FailedFile(file=path.name, status="failed", error=f"Parser error: {exc}")


def _run_alone(worker: Callable[..., ParsedResume], job: tuple[Path, bytes, str], settings: Settings) -> ParsedResume:
    pool = ProcessPoolExecutor(max_workers=1)
    try:
        return pool.submit(worker, *job, settings.min_text_chars).result(timeout=settings.parse_timeout_s)
    finally:
        _shutdown(pool)


def _shutdown(pool: ProcessPoolExecutor) -> None:
    # shutdown(wait=True) would block forever on a hung worker, so stop without waiting and kill stragglers.
    workers = list(getattr(pool, "_processes", {}).values())
    pool.shutdown(wait=False, cancel_futures=True)
    for process in workers:
        if process.is_alive():
            process.terminate()


async def screen(
    input_dir: Path,
    settings: Settings | None = None,
    reviewer: ResumeReviewer | None = None,
    github_client: GitHubClient | None = None,
) -> ScreeningReport:
    settings = settings or Settings()
    started = time.perf_counter()
    resumes, failed = load_resumes(input_dir, settings)

    eligible, rejected = [], []
    for resume in resumes:
        result = check_eligibility(resume)
        if result.eligible:
            eligible.append(resume)
        else:
            rejected.append(_rejected(resume, result))

    if reviewer is None:
        reviewer, llm_mode = build_reviewer(settings.llm)
    else:
        llm_mode = f"enabled ({reviewer.model_name})"
    log.info("LLM review: %s", llm_mode)
    llm = LLMService(reviewer, settings.llm, JsonCache(settings.cache_dir / "llm.json"))
    gh_cache = JsonCache(settings.cache_dir / "github.json", ttl_s=settings.github.cache_ttl_s)
    github = github_client or GitHubClient(settings.github, gh_cache)

    # Only eligible candidates are enriched: no point spending API calls on rejected profiles.
    async with github:
        enrichments = await asyncio.gather(*[_enrich(r, github, llm) for r in eligible])

    ranked = [
        _ranked(resume, activity, review, llm_status, settings)
        for resume, (activity, (review, llm_status)) in zip(eligible, enrichments)
    ]
    ranked.sort(key=lambda c: (-c.total_score, -c.score_breakdown.ai_project_depth, -c.score_breakdown.python_backend, c.candidate_name))
    for i, candidate in enumerate(ranked, start=1):
        candidate.rank = i

    summary = BatchSummary(
        total_files=len(resumes) + len(failed),
        parsed=len(resumes),
        eligible=len(ranked),
        rejected=len(rejected),
        failed=sum(1 for f in failed if f.status == "failed"),
        duplicates=sum(1 for f in failed if f.status == "duplicate"),
        github_enriched=sum(1 for c in ranked if c.github_status == GitHubStatus.OK.value),
        llm_reviewed=sum(1 for c in ranked if c.llm_status.startswith("ok")),
        duration_s=round(time.perf_counter() - started, 2),
    )
    if llm.cache:
        llm.cache.save()
    return ScreeningReport(summary=summary, ranked=ranked, rejected=rejected, failed=failed)


def _rejected(resume: ParsedResume, result: EligibilityResult) -> RejectedCandidate:
    return RejectedCandidate(
        candidate_name=resume.name,
        rejection_reasons=result.rejection_reasons,
        matched_skills=matched_skills(resume),
        evidence=(result.python_evidence + result.ai_evidence)[:4],
        file=resume.file,
        email=resume.email,
    )


def _ranked(
    resume: ParsedResume, activity: GitHubActivity, review: LLMReview | None, llm_status: str, settings: Settings
) -> RankedCandidate:
    gh_points, gh_summary, gh_reasons = score_github(activity, settings.github)
    score = score_candidate(resume, gh_points, settings.scoring, review, gh_reasons)
    if activity.status not in (GitHubStatus.OK, GitHubStatus.NO_PROFILE):
        score.concerns.append(gh_summary)
    return RankedCandidate(
        candidate_name=resume.name,
        total_score=score.total,
        score_breakdown=score.breakdown,
        score_evidence=score.evidence,
        matched_skills=matched_skills(resume),
        project_summary=score.project_summary,
        projects=score.projects,
        github_url=activity.profile_url,
        github_summary=gh_summary,
        github_status=activity.status.value,
        strengths=score.strengths,
        concerns=score.concerns[:6],
        evidence=score.highlights,
        llm_status=llm_status,
        file=resume.file,
        email=resume.email,
    )


async def _fetch_github(resume: ParsedResume, github: GitHubClient) -> GitHubActivity:
    # Resumes sometimes link an old or mistyped account first; use the first one that exists.
    activity = await github.fetch(None)
    for username in resume.github_usernames:
        activity = await github.fetch(username)
        if activity.status != GitHubStatus.NOT_FOUND:
            break
    return activity


async def _enrich(resume: ParsedResume, github: GitHubClient, llm: LLMService):
    return await asyncio.gather(_fetch_github(resume, github), llm.review(resume))
