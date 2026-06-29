from pathlib import Path

from mvo.models import (
    AnalyzedVideo,
    Confidence,
    ConfidenceLevel,
    ParsedVideo,
    PlannedVideo,
    PlanStatus,
    PreflightItem,
    PreflightResult,
    PreflightStatus,
    VideoFile,
)
from mvo.preflight_report import render_preflight_html, write_preflight_report


def _result(tmp_path: Path) -> PreflightResult:
    source = VideoFile(tmp_path / "A&B.mp4", Path("A&B.mp4"), 1, ".mp4")
    parsed = ParsedVideo(
        source.path.name,
        "<Artist>",
        "A & B",
        (),
        (),
        None,
        Confidence(0.9, ConfidenceLevel.HIGH, ()),
    )
    planned = PlannedVideo(
        AnalyzedVideo(source, parsed),
        Path("Artist/A&B.mp4"),
        PlanStatus.READY,
        (),
    )
    item = PreflightItem(planned, PreflightStatus.BLOCKED, ("destination <exists>",))
    return PreflightResult(tmp_path, (item,), ())


def test_preflight_report_is_escaped_and_explicitly_read_only(
    tmp_path: Path,
) -> None:
    html = render_preflight_html(_result(tmp_path))

    assert "A&amp;B.mp4" in html
    assert "destination &lt;exists&gt;" in html
    assert "Not ready" in html
    assert "does not" in html


def test_writes_preflight_report_to_selected_path(tmp_path: Path) -> None:
    output = tmp_path / "preflight.html"

    written = write_preflight_report(_result(tmp_path), output)

    assert written == output.resolve()
    assert "preflight" in output.read_text(encoding="utf-8")
