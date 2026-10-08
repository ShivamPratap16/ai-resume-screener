import argparse
import asyncio
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent / "src"))

from screener.pipeline import screen  # noqa: E402
from screener.report import console_summary, write_html, write_json  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description="Screen and rank resumes for the SDE (Python + AI) internship.")
    parser.add_argument("--input", type=Path, default=Path("resumes"), help="Folder with resumes (PDF/DOCX/TXT)")
    parser.add_argument("--output", type=Path, default=Path("output/results.json"), help="Where to write the JSON report")
    parser.add_argument("--html", type=Path, default=Path("output/report.html"), help="Where to write the HTML report")
    parser.add_argument("--top", type=int, default=10, help="Rows to print in the console summary")
    parser.add_argument("--redact-emails", action="store_true", help="Mask candidate emails in the JSON (for sharing)")
    parser.add_argument("-v", "--verbose", action="store_true")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO if args.verbose else logging.WARNING, format="%(levelname)s %(name)s: %(message)s")
    try:
        report = asyncio.run(screen(args.input))
    except FileNotFoundError as exc:
        print(exc, file=sys.stderr)
        return 1
    write_json(report, args.output, redact=args.redact_emails)
    write_html(report, args.html)
    print(console_summary(report, args.top))
    print(f"\nJSON report: {args.output}\nHTML report: {args.html}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
