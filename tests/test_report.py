from pathlib import Path

from mvo.models import (
    AnalysisResult,
    AnalyzedVideo,
    Confidence,
    ConfidenceLevel,
    ParsedVideo,
    VideoFile,
)
from mvo.report import render_html, write_html_report


def _result(tmp_path: Path) -> AnalysisResult:
    source = VideoFile(
        path=tmp_path / "unsafe.mp4",
        relative_path=Path("A&B/unsafe.mp4"),
        size_bytes=1536,
        extension=".mp4",
    )
    parsed = ParsedVideo(
        source_name="unsafe.mp4",
        artist="<script>alert(1)</script>",
        title="A & B",
        featured_artists=(),
        versions=("Live",),
        year=2020,
        confidence=Confidence(0.95, ConfidenceLevel.HIGH, ("safe",)),
    )
    return AnalysisResult(
        root=tmp_path,
        videos=(AnalyzedVideo(source=source, parsed=parsed),),
        issues=(),
    )


def test_report_escapes_all_filename_metadata(tmp_path: Path) -> None:
    html = render_html(_result(tmp_path))

    assert "<script>" not in html
    assert "&lt;script&gt;alert(1)&lt;/script&gt;" in html
    assert "A&amp;B/unsafe.mp4" in html
    assert "1.5 KiB" in html


def test_writes_standalone_report_to_selected_path(tmp_path: Path) -> None:
    output = tmp_path / "reports" / "library.html"

    written = write_html_report(_result(tmp_path), output)

    assert written == output.resolve()
    assert output.read_text(encoding="utf-8").startswith("<!doctype html>")
