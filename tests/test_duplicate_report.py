from pathlib import Path

from mvo.duplicate_report import render_duplicate_html, write_duplicate_report
from mvo.models import (
    AnalyzedVideo,
    Confidence,
    ConfidenceLevel,
    DuplicateGroup,
    DuplicateKind,
    DuplicateResult,
    ParsedVideo,
    VideoFile,
)


def _video(root: Path, relative_path: str) -> AnalyzedVideo:
    source = VideoFile(
        path=root / relative_path,
        relative_path=Path(relative_path),
        size_bytes=2048,
        extension=".mp4",
    )
    parsed = ParsedVideo(
        source_name=source.path.name,
        artist="<Artist>",
        title="A & B",
        featured_artists=(),
        versions=(),
        year=None,
        confidence=Confidence(0.9, ConfidenceLevel.HIGH, ()),
    )
    return AnalyzedVideo(source, parsed)


def _result(tmp_path: Path) -> DuplicateResult:
    group = DuplicateGroup(
        kind=DuplicateKind.EXACT,
        signature="sha256:abc",
        videos=(_video(tmp_path, "A&B.mp4"), _video(tmp_path, "copy.mp4")),
    )
    return DuplicateResult(root=tmp_path, groups=(group,), issues=())


def test_duplicate_report_is_escaped_and_read_only(tmp_path: Path) -> None:
    html = render_duplicate_html(_result(tmp_path))

    assert "<Artist>" not in html
    assert "&lt;Artist&gt;" in html
    assert "A&amp;B.mp4" in html
    assert "No files have been deleted" in html
    assert "2.0 KiB" in html
    assert "potential savings" in html


def test_writes_duplicate_report_to_selected_path(tmp_path: Path) -> None:
    output = tmp_path / "duplicates.html"

    written = write_duplicate_report(_result(tmp_path), output)

    assert written == output.resolve()
    assert "Duplicate detection" in output.read_text(encoding="utf-8")
