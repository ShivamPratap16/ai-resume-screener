import asyncio
import json
import os
import time
from dataclasses import replace
from pathlib import Path

import httpx
import pytest

from screener.config import GitHubConfig, LLMConfig, Settings
from screener.github import GitHubClient
from screener.models import LLMReview
from screener.pipeline import extract_and_parse, load_resumes, screen

from conftest import JAVA_REACT_ONLY, STRONG_AGENTIC, THIN_WRAPPER

ROOT = Path(__file__).resolve().parent.parent


def _offline_github() -> GitHubClient:
    http = httpx.AsyncClient(transport=httpx.MockTransport(lambda r: httpx.Response(404)), base_url="https://api.github.com")
    return GitHubClient(GitHubConfig(token=None), cache=None, http=http)


def _settings(tmp_path: Path) -> Settings:
    return Settings(llm=LLMConfig(mode="false"), cache_dir=tmp_path / "cache")


def _run(folder: Path, tmp_path: Path):
    return asyncio.run(screen(folder, _settings(tmp_path), github_client=_offline_github()))


def test_batch_survives_bad_files_and_ranks_candidates(tmp_path):
    folder = tmp_path / "resumes"
    folder.mkdir()
    (folder / "strong.txt").write_text(STRONG_AGENTIC, encoding="utf-8")
    (folder / "strong_copy.txt").write_text(STRONG_AGENTIC, encoding="utf-8")
    (folder / "thin.txt").write_text(THIN_WRAPPER, encoding="utf-8")
    (folder / "java.txt").write_text(JAVA_REACT_ONLY, encoding="utf-8")
    (folder / "broken.pdf").write_bytes(b"%PDF-1.4 garbage")
    (folder / "empty.txt").write_text("", encoding="utf-8")
    (folder / "photo.jpg").write_bytes(b"\xff\xd8\xff")

    report = _run(folder, tmp_path)

    s = report.summary
    assert (s.total_files, s.parsed, s.eligible, s.rejected, s.failed, s.duplicates) == (7, 3, 2, 1, 3, 1)
    assert [c.candidate_name for c in report.ranked] == ["Asha Rao", "Rahul Verma"]
    assert report.ranked[0].rank == 1 and report.ranked[0].github_status == "not_found"
    assert report.rejected[0].rejection_reasons
    assert all(f.error for f in report.failed)


def test_missing_input_folder_raises_clear_error(tmp_path):
    with pytest.raises(FileNotFoundError):
        _run(tmp_path / "nope", tmp_path)


SAMPLES = ROOT / "tests" / "fixtures" / "sample_resumes"


@pytest.mark.skipif(not SAMPLES.exists(), reason="run scripts/generate_sample_resumes.py first")
def test_sample_set_matches_expected_outcomes(tmp_path):
    manifest = json.loads((ROOT / "tests" / "fixtures" / "sample_manifest.json").read_text(encoding="utf-8"))
    report = _run(SAMPLES, tmp_path)
    outcome = {c.file: "eligible" for c in report.ranked}
    outcome |= {c.file: "rejected" for c in report.rejected}
    outcome |= {c.file: c.status for c in report.failed}
    for file, expected in manifest.items():
        want = expected.get("status") or ("eligible" if expected["eligible"] else "rejected")
        assert outcome[file] == want, file

    ranks = {c.file: c.rank for c in report.ranked}
    archetype = {f: m["archetype"] for f, m in manifest.items()}
    best_thin = min(r for f, r in ranks.items() if "thin" in archetype[f])
    worst_strong = max(r for f, r in ranks.items() if archetype[f] == "strong_agentic")
    assert worst_strong < best_thin


class QuotingReviewer:
    model_name = "fake"

    async def review(self, resume_text):
        return LLMReview(ai_project_depth=38, thin_wrapper=False, tutorial_like=False,
                         project_summary="LLM summary", evidence=["LangGraph multi-agent workflow"],
                         strengths=["LLM strength"], concerns=[])


def test_llm_review_flows_into_results(tmp_path):
    folder = tmp_path / "resumes"
    folder.mkdir()
    (folder / "strong.txt").write_text(STRONG_AGENTIC, encoding="utf-8")
    report = asyncio.run(screen(folder, _settings(tmp_path), reviewer=QuotingReviewer(), github_client=_offline_github()))
    top = report.ranked[0]
    assert top.llm_status == "ok" and top.project_summary == "LLM summary"
    assert top.evidence == ["LangGraph multi-agent workflow"]
    assert report.summary.llm_reviewed == 1


def hanging_worker(path, data, digest, min_chars):
    # Module-level so worker processes can import it.
    if path.name.startswith("hang"):
        time.sleep(60)
    return extract_and_parse(path, data, digest, min_chars)


def test_hanging_file_times_out_without_stalling_the_batch(tmp_path):
    folder = tmp_path / "resumes"
    folder.mkdir()
    (folder / "hang.txt").write_text(STRONG_AGENTIC.replace("asha.rao", "hang"), encoding="utf-8")
    (folder / "strong.txt").write_text(STRONG_AGENTIC, encoding="utf-8")
    settings = replace(_settings(tmp_path), parse_timeout_s=2, parse_workers=2)

    started = time.perf_counter()
    parsed, failed = load_resumes(folder, settings, worker=hanging_worker)

    assert [r.file for r in parsed] == ["strong.txt"]
    assert failed[0].file == "hang.txt" and "Timed out after 2s" in failed[0].error
    assert time.perf_counter() - started < 20


def crashing_worker(path, data, digest, min_chars):
    if path.name.startswith("crash"):
        os._exit(3)  # simulates a native-library crash on a malicious PDF
    return extract_and_parse(path, data, digest, min_chars)


def test_crashing_file_does_not_take_down_other_files(tmp_path):
    folder = tmp_path / "resumes"
    folder.mkdir()
    (folder / "a_strong.txt").write_text(STRONG_AGENTIC, encoding="utf-8")
    (folder / "crash.txt").write_text(THIN_WRAPPER.replace("rahul", "crash"), encoding="utf-8")
    (folder / "z_thin.txt").write_text(THIN_WRAPPER, encoding="utf-8")
    settings = replace(_settings(tmp_path), parse_timeout_s=10, parse_workers=2)

    parsed, failed = load_resumes(folder, settings, worker=crashing_worker)

    assert sorted(r.file for r in parsed) == ["a_strong.txt", "z_thin.txt"]
    assert [(f.file, f.error) for f in failed] == [("crash.txt", "Parser worker crashed on this file")]


def test_redacted_report_masks_emails_without_touching_the_original(tmp_path):
    from screener.report import mask_email, redact_emails

    assert mask_email("jane.doe@gmail.com") == "j***@gmail.com"
    assert mask_email(None) is None
    folder = tmp_path / "resumes"
    folder.mkdir()
    (folder / "strong.txt").write_text(STRONG_AGENTIC, encoding="utf-8")
    (folder / "java.txt").write_text(JAVA_REACT_ONLY, encoding="utf-8")
    report = _run(folder, tmp_path)
    redacted = redact_emails(report)
    assert redacted.ranked[0].email == "a***@example.com" and redacted.rejected[0].email == "r***@example.com"
    assert report.ranked[0].email == "asha.rao@example.com"
