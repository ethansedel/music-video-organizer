from pathlib import Path

from mvo.execution_report import render_execution_html, write_execution_report
from mvo.models import (
    AnalyzedVideo,
    Confidence,
    ConfidenceLevel,
    ExecutionItem,
    ExecutionResult,
    ExecutionStatus,
    ParsedVideo,
    PlannedVideo,
    PlanStatus,
    VideoFile,
)


def _result(tmp_path: Path) -> ExecutionResult:
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
    item = ExecutionItem(planned, ExecutionStatus.MOVED, "moved <safely>")
    return ExecutionResult(tmp_path, (item,), False)


def test_execution_report_is_escaped_and_auditable(tmp_path: Path) -> None:
    html = render_execution_html(_result(tmp_path))

    assert "Execution completed" in html
    assert "A&amp;B.mp4" in html
    assert "&lt;Artist&gt;" in html
    assert "moved &lt;safely&gt;" in html
    assert "never overwrites" in html


def test_writes_execution_report_to_selected_path(tmp_path: Path) -> None:
    output = tmp_path / "execution.html"

    written = write_execution_report(_result(tmp_path), output)

    assert written == output.resolve()
    assert "execution audit" in output.read_text(encoding="utf-8")


def test_execution_report_warns_when_rollback_is_incomplete(tmp_path: Path) -> None:
    result = _result(tmp_path)
    incomplete = ExecutionResult(result.root, result.items, True, False)

    html = render_execution_html(incomplete)

    assert "rollback incomplete" in html
