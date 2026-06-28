from pathlib import Path

from mvo.models import (
    AnalyzedVideo,
    Confidence,
    ConfidenceLevel,
    OrganizationPlan,
    ParsedVideo,
    PlannedVideo,
    PlanStatus,
    VideoFile,
)
from mvo.plan_report import render_plan_html, write_plan_report


def _plan(tmp_path: Path) -> OrganizationPlan:
    source = VideoFile(
        path=tmp_path / "A&B.mp4",
        relative_path=Path("A&B.mp4"),
        size_bytes=1,
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
    item = PlannedVideo(
        video=AnalyzedVideo(source, parsed),
        destination=Path("Artist/A&B.mp4"),
        status=PlanStatus.READY,
        notes=(),
    )
    return OrganizationPlan(root=tmp_path, items=(item,), issues=())


def test_plan_report_is_escaped_and_explicitly_read_only(tmp_path: Path) -> None:
    html = render_plan_html(_plan(tmp_path))

    assert "<Artist>" not in html
    assert "&lt;Artist&gt;" in html
    assert "A&amp;B.mp4" in html
    assert "No media has been renamed" in html


def test_writes_plan_report_to_selected_path(tmp_path: Path) -> None:
    output = tmp_path / "dry-run.html"

    written = write_plan_report(_plan(tmp_path), output)

    assert written == output.resolve()
    assert "dry-run" in output.read_text(encoding="utf-8")
