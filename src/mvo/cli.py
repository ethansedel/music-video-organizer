"""Command-line entry point for read-only library analysis."""

from __future__ import annotations

import argparse
from pathlib import Path

from mvo.analyzer import LibraryAnalyzer
from mvo.report import write_html_report


def build_parser() -> argparse.ArgumentParser:
    """Build the command-line argument parser."""

    parser = argparse.ArgumentParser(
        prog="mvo",
        description="Scan music-video filenames and write a read-only HTML report.",
    )
    parser.add_argument("library", type=Path, help="music-video library directory")
    parser.add_argument(
        "-o",
        "--output",
        type=Path,
        default=Path("report.html"),
        help="HTML report path (default: report.html)",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    """Run a scan and report the output location."""

    args = build_parser().parse_args(argv)
    try:
        result = LibraryAnalyzer().analyze(args.library)
        report = write_html_report(result, args.output)
    except (OSError, ValueError) as error:
        build_parser().error(str(error))
    print(f"Analyzed {len(result.videos)} video(s). Report: {report}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
