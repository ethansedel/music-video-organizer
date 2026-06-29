from pathlib import Path

from mvo.models import (
    AnalyzedVideo,
    Confidence,
    ConfidenceLevel,
    OrganizationPlan,
    ParsedVideo,
    PlannedVideo,
    PlanStatus,
    PreflightStatus,
    VideoFile,
)
from mvo.preflight import PlanPreflight


def _plan(
    root: Path,
    source_name: str = "incoming.mp4",
    destination: Path = Path("Artist/Artist - Song.mp4"),
    *,
    status: PlanStatus = PlanStatus.READY,
) -> OrganizationPlan:
    source_path = root / source_name
    source = VideoFile(source_path, Path(source_name), 4, ".mp4")
    parsed = ParsedVideo(
        source_name,
        "Artist",
        "Song",
        (),
        (),
        None,
        Confidence(0.9, ConfidenceLevel.HIGH, ()),
    )
    item = PlannedVideo(AnalyzedVideo(source, parsed), destination, status, ())
    return OrganizationPlan(root, (item,), ())


def test_ready_plan_passes_without_modifying_media(tmp_path: Path) -> None:
    media = tmp_path / "incoming.mp4"
    media.write_bytes(b"safe")

    result = PlanPreflight().validate(_plan(tmp_path))

    assert result.safe_to_execute is True
    assert result.items[0].status is PreflightStatus.READY
    assert media.read_bytes() == b"safe"
    assert not (tmp_path / "Artist").exists()


def test_already_organized_file_is_unchanged(tmp_path: Path) -> None:
    media = tmp_path / "Artist - Song.mp4"
    media.write_bytes(b"safe")

    result = PlanPreflight().validate(
        _plan(tmp_path, source_name=media.name, destination=Path(media.name))
    )

    assert result.safe_to_execute is True
    assert result.items[0].status is PreflightStatus.UNCHANGED


def test_missing_or_changed_source_blocks_execution(tmp_path: Path) -> None:
    missing = PlanPreflight().validate(_plan(tmp_path))
    (tmp_path / "incoming.mp4").write_bytes(b"changed")
    changed = PlanPreflight().validate(_plan(tmp_path))

    assert missing.items[0].status is PreflightStatus.BLOCKED
    assert "missing" in missing.items[0].checks[0]
    assert changed.items[0].status is PreflightStatus.BLOCKED
    assert "size changed" in changed.items[0].checks[0]


def test_existing_destination_blocks_execution(tmp_path: Path) -> None:
    (tmp_path / "incoming.mp4").write_bytes(b"safe")
    destination = tmp_path / "Artist" / "Artist - Song.mp4"
    destination.parent.mkdir()
    destination.write_bytes(b"other")

    result = PlanPreflight().validate(_plan(tmp_path))

    assert result.safe_to_execute is False
    assert result.items[0].status is PreflightStatus.BLOCKED
    assert "destination already exists" in result.items[0].checks


def test_non_ready_plan_and_unsafe_destination_are_blocked(tmp_path: Path) -> None:
    (tmp_path / "incoming.mp4").write_bytes(b"safe")

    result = PlanPreflight().validate(
        _plan(
            tmp_path,
            destination=Path("../outside.mp4"),
            status=PlanStatus.REVIEW,
        )
    )

    assert result.items[0].status is PreflightStatus.BLOCKED
    assert "plan status is review" in result.items[0].checks
    assert "destination is not a safe relative path" in result.items[0].checks


def test_file_in_destination_parent_path_blocks_execution(tmp_path: Path) -> None:
    (tmp_path / "incoming.mp4").write_bytes(b"safe")
    (tmp_path / "Artist").write_bytes(b"not a directory")

    result = PlanPreflight().validate(_plan(tmp_path))

    assert result.items[0].status is PreflightStatus.BLOCKED
    assert "destination parent is not a directory" in result.items[0].checks[0]
