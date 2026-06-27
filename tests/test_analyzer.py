from pathlib import Path

from mvo.analyzer import LibraryAnalyzer


def test_analyzes_discovered_video_names(tmp_path: Path) -> None:
    (tmp_path / "Portishead - Roads.mp4").write_bytes(b"video")

    result = LibraryAnalyzer().analyze(tmp_path)

    assert len(result.videos) == 1
    assert result.videos[0].parsed.artist == "Portishead"
    assert result.videos[0].parsed.title == "Roads"


def test_uses_parent_folder_as_artist_hint(tmp_path: Path) -> None:
    artist_folder = tmp_path / "100 gecs"
    artist_folder.mkdir()
    (artist_folder / "100 gecs stupid horse.mp4").touch()

    result = LibraryAnalyzer().analyze(tmp_path)

    assert result.videos[0].parsed.artist == "100 gecs"
    assert result.videos[0].parsed.title == "stupid horse"
