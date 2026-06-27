from pathlib import Path

import pytest

from mvo.scanner import LibraryScanner


def test_scans_supported_videos_recursively_and_sorts_them(tmp_path: Path) -> None:
    nested = tmp_path / "B folder"
    nested.mkdir()
    (nested / "second.MKV").write_bytes(b"22")
    (tmp_path / "first.mp4").write_bytes(b"1")
    (tmp_path / "notes.txt").write_text("ignore me", encoding="utf-8")

    result = LibraryScanner().scan(tmp_path)

    assert [item.relative_path.as_posix() for item in result.files] == [
        "B folder/second.MKV",
        "first.mp4",
    ]
    assert [item.size_bytes for item in result.files] == [2, 1]
    assert result.issues == ()


def test_does_not_follow_video_symlinks(tmp_path: Path) -> None:
    source = tmp_path / "source.mp4"
    source.write_bytes(b"video")
    link = tmp_path / "link.mp4"
    try:
        link.symlink_to(source)
    except OSError:
        pytest.skip("symlinks unavailable")

    result = LibraryScanner().scan(tmp_path)

    assert [item.relative_path.name for item in result.files] == ["source.mp4"]


def test_rejects_non_directory_root(tmp_path: Path) -> None:
    file_path = tmp_path / "video.mp4"
    file_path.touch()

    with pytest.raises(NotADirectoryError):
        LibraryScanner().scan(file_path)
