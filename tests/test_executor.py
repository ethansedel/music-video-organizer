from errno import EOPNOTSUPP
from pathlib import Path

import pytest

from mvo.analyzer import LibraryAnalyzer
from mvo.executor import PlanExecutor
from mvo.models import ExecutionStatus
from mvo.planner import FolderPlanner


def _plan(root: Path):
    return FolderPlanner().plan(LibraryAnalyzer().analyze(root))


def test_moves_ready_file_without_overwriting(tmp_path: Path) -> None:
    incoming = tmp_path / "incoming"
    incoming.mkdir()
    source = incoming / "Artist - Song.mp4"
    source.write_bytes(b"video")

    result = PlanExecutor().execute(_plan(tmp_path))

    destination = tmp_path / "Artist" / "Artist - Song.mp4"
    assert result.moved_count == 1
    assert result.items[0].status is ExecutionStatus.MOVED
    assert destination.read_bytes() == b"video"
    assert not source.exists()


def test_preflight_blocker_is_skipped(tmp_path: Path) -> None:
    source = tmp_path / "Unstructured.mp4"
    source.write_bytes(b"video")

    result = PlanExecutor().execute(_plan(tmp_path))

    assert result.moved_count == 0
    assert result.items[0].status is ExecutionStatus.SKIPPED
    assert source.read_bytes() == b"video"


def test_exclusive_move_preserves_both_files_when_destination_exists(
    tmp_path: Path,
) -> None:
    source = tmp_path / "source.mp4"
    destination = tmp_path / "destination.mp4"
    source.write_bytes(b"source")
    destination.write_bytes(b"destination")

    with pytest.raises(FileExistsError):
        PlanExecutor._move_exclusive(source, destination)

    assert source.read_bytes() == b"source"
    assert destination.read_bytes() == b"destination"


def test_exclusive_move_falls_back_when_hard_links_are_unsupported(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    source = tmp_path / "source.mp4"
    destination = tmp_path / "destination.mp4"
    source.write_bytes(b"source")

    def unsupported_link(*args: object, **kwargs: object) -> None:
        raise OSError(EOPNOTSUPP, "Operation not supported")

    monkeypatch.setattr("mvo.executor.os.link", unsupported_link)

    PlanExecutor._move_exclusive(source, destination)

    assert not source.exists()
    assert destination.read_bytes() == b"source"


def test_later_failure_rolls_back_earlier_moves(tmp_path: Path) -> None:
    incoming = tmp_path / "incoming"
    incoming.mkdir()
    first = incoming / "Artist - One.mp4"
    second = incoming / "Artist - Two.mp4"
    first.write_bytes(b"one")
    second.write_bytes(b"two")

    class FailingExecutor(PlanExecutor):
        def _move_exclusive(self, source: Path, destination: Path) -> None:
            if source == second:
                raise OSError("simulated failure")
            super()._move_exclusive(source, destination)

    result = FailingExecutor().execute(_plan(tmp_path))

    assert result.rolled_back is True
    assert result.moved_count == 0
    assert [item.status for item in result.items] == [
        ExecutionStatus.ROLLED_BACK,
        ExecutionStatus.FAILED,
    ]
    assert first.read_bytes() == b"one"
    assert second.read_bytes() == b"two"
    assert not (tmp_path / "Artist").exists()


def test_rollback_failure_is_reported_without_hiding_file_location(
    tmp_path: Path,
) -> None:
    incoming = tmp_path / "incoming"
    incoming.mkdir()
    first = incoming / "Artist - One.mp4"
    second = incoming / "Artist - Two.mp4"
    first.write_bytes(b"one")
    second.write_bytes(b"two")

    class RollbackFailingExecutor(PlanExecutor):
        def _move_exclusive(self, source: Path, destination: Path) -> None:
            if source == second or source.parent == tmp_path / "Artist":
                raise OSError("simulated failure")
            super()._move_exclusive(source, destination)

    result = RollbackFailingExecutor().execute(_plan(tmp_path))

    assert result.rolled_back is True
    assert result.rollback_complete is False
    assert result.items[0].status is ExecutionStatus.FAILED
    assert "rollback failed" in result.items[0].message
    assert (tmp_path / "Artist" / first.name).read_bytes() == b"one"
    assert second.read_bytes() == b"two"
