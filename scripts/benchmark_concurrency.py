"""Times a full screening run with different GitHub concurrency limits (no cache, LLM off).

Usage: python scripts/benchmark_concurrency.py --input resumes --limits 1 5 10
Needs network access; set GITHUB_TOKEN to avoid the 60 requests/hour anonymous limit.
"""
import argparse
import asyncio
import sys
import tempfile
import time
from dataclasses import replace
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from screener.config import LLMConfig, Settings  # noqa: E402
from screener.github import GitHubClient  # noqa: E402
from screener.pipeline import screen  # noqa: E402


async def timed_run(input_dir: Path, limit: int) -> tuple[float, int]:
    base = Settings()
    with tempfile.TemporaryDirectory() as cache_dir:
        settings = replace(base, github=replace(base.github, max_concurrency=limit), llm=LLMConfig(mode="false"),
                           cache_dir=Path(cache_dir))
        started = time.perf_counter()
        report = await screen(input_dir, settings, github_client=GitHubClient(settings.github, cache=None))
        return time.perf_counter() - started, report.summary.github_enriched


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", type=Path, default=Path("resumes"))
    parser.add_argument("--limits", type=int, nargs="+", default=[1, 5, 10])
    args = parser.parse_args()
    baseline = None
    for limit in args.limits:
        seconds, enriched = asyncio.run(timed_run(args.input, limit))
        baseline = baseline or seconds
        print(f"max_concurrency={limit:<3} {seconds:6.2f}s  ({baseline / seconds:4.1f}x)  GitHub enriched: {enriched}")


if __name__ == "__main__":
    main()
