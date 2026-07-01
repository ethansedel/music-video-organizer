import json
from pathlib import Path

import pytest

from mvo.quarantine import DuplicateQuarantine
from mvo.scanner import LibraryScanner


def test_quarantine_preserves_recoverable_copy_without_typed_phrase(
    tmp_path: Path,
) -> None:
    source = tmp_path / "Artist - Song [720p].mp4"
    source.write_bytes(b"video")
    video = LibraryScanner().scan(tmp_path).files[0]
    quarantine = DuplicateQuarantine()

    result = quarantine.quarantine(tmp_path, video)

    assert not source.exists()
    assert result.destination.read_bytes() == b"video"
    record = json.loads(
        (tmp_path / ".mvo-trash" / "audit.jsonl").read_text(encoding="utf-8")
    )
    assert record["source"] == source.name
    assert record["destination"] == f".mvo-trash/{source.name}"


def test_scanner_ignores_mvo_trash(tmp_path: Path) -> None:
    trash = tmp_path / ".mvo-trash"
    trash.mkdir()
    (trash / "Discarded.mp4").write_bytes(b"discarded")
    (tmp_path / "Kept.mp4").write_bytes(b"kept")

    scan = LibraryScanner().scan(tmp_path)

    assert [video.relative_path.as_posix() for video in scan.files] == ["Kept.mp4"]


def test_mvo_trash_supports_restore_and_gated_permanent_deletion(
    tmp_path: Path,
) -> None:
    source = tmp_path / "Discarded.mp4"
    source.write_bytes(b"video")
    quarantine = DuplicateQuarantine()
    video = LibraryScanner().scan(tmp_path).files[0]
    trashed = quarantine.quarantine(tmp_path, video)
    relative = trashed.destination.relative_to(tmp_path).as_posix()

    restored = quarantine.restore(tmp_path, relative)

    assert restored == source
    assert restored.read_bytes() == b"video"

    video = LibraryScanner().scan(tmp_path).files[0]
    trashed = quarantine.quarantine(tmp_path, video)
    relative = trashed.destination.relative_to(tmp_path).as_posix()

    assert quarantine.delete_permanently(tmp_path, relative) == 5
    assert not trashed.destination.exists()


def test_empty_mvo_trash_requires_phrase_and_reports_deleted_files(
    tmp_path: Path,
) -> None:
    trash = tmp_path / ".mvo-trash"
    trash.mkdir()
    (trash / "One.mp4").write_bytes(b"one")
    (trash / "Two.webm").write_bytes(b"two")
    quarantine = DuplicateQuarantine()

    with pytest.raises(ValueError, match="EMPTY_LINER_NOTES_TRASH"):
        quarantine.empty(tmp_path, confirmation="wrong")

    deleted, deleted_bytes, errors = quarantine.empty(
        tmp_path, confirmation="EMPTY_LINER_NOTES_TRASH"
    )

    assert (deleted, deleted_bytes, errors) == (2, 6, [])
    assert quarantine.list_files(tmp_path) == ()
