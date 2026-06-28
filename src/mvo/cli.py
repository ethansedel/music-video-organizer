"""Command-line entry point for read-only library analysis."""

from __future__ import annotations

import argparse
from pathlib import Path

from mvo.analyzer import LibraryAnalyzer
from mvo.duplicate_report import write_duplicate_report
from mvo.duplicates import DuplicateDetector
from mvo.enrichment import MusicBrainzEnricher
from mvo.enrichment_report import write_enrichment_report
from mvo.musicbrainz import MusicBrainzClient
from mvo.plan_report import write_plan_report
from mvo.planner import FolderPlanner
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
    modes = parser.add_mutually_exclusive_group()
    modes.add_argument(
        "--plan",
        action="store_true",
        help="write a read-only organization plan instead of the analysis report",
    )
    modes.add_argument(
        "--duplicates",
        action="store_true",
        help="find exact and metadata-match duplicates without modifying files",
    )
    modes.add_argument(
        "--musicbrainz",
        action="store_true",
        help="opt in to MusicBrainz artist/title searches and write a match report",
    )
    parser.add_argument(
        "--max-queries",
        type=int,
        default=25,
        help="maximum MusicBrainz API queries (default: 25)",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    """Run a scan and report the output location."""

    args = build_parser().parse_args(argv)
    try:
        result = LibraryAnalyzer().analyze(args.library)
        if args.musicbrainz:
            enrichment = MusicBrainzEnricher(MusicBrainzClient()).enrich(
                result, max_queries=args.max_queries
            )
            report = write_enrichment_report(enrichment, args.output)
        elif args.duplicates:
            duplicates = DuplicateDetector().detect(result)
            report = write_duplicate_report(duplicates, args.output)
        elif args.plan:
            plan = FolderPlanner().plan(result)
            report = write_plan_report(plan, args.output)
        else:
            report = write_html_report(result, args.output)
    except (OSError, ValueError) as error:
        build_parser().error(str(error))
    if args.musicbrainz:
        label = "Enriched"
    elif args.duplicates:
        label = "Checked"
    elif args.plan:
        label = "Planned"
    else:
        label = "Analyzed"
    print(f"{label} {len(result.videos)} video(s). Report: {report}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
