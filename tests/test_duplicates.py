from pathlib import Path

from mvo.analyzer import LibraryAnalyzer
from mvo.duplicates import DuplicateDetector
from mvo.models import DuplicateKind


def test_finds_exact_duplicates_by_size_and_sha256(tmp_path: Path) -> None:
    (tmp_path / "Artist - One.mp4").write_bytes(b"identical bytes")
    nested = tmp_path / "nested"
    nested.mkdir()
    (nested / "Different - Name.mkv").write_bytes(b"identical bytes")

    result = DuplicateDetector().detect(LibraryAnalyzer().analyze(tmp_path))

    assert len(result.groups) == 1
    group = result.groups[0]
    assert group.kind is DuplicateKind.EXACT
    assert group.signature.startswith("sha256:")
    assert group.recoverable_bytes == len(b"identical bytes")


def test_same_size_different_content_is_not_exact_duplicate(tmp_path: Path) -> None:
    (tmp_path / "Artist - One.mp4").write_bytes(b"abc")
    (tmp_path / "Other - Two.mp4").write_bytes(b"xyz")

    result = DuplicateDetector().detect(LibraryAnalyzer().analyze(tmp_path))

    assert result.groups == ()


def test_finds_metadata_matches_with_different_file_content(tmp_path: Path) -> None:
    (tmp_path / "Artist - Song.mp4").write_bytes(b"short")
    nested = tmp_path / "alternate"
    nested.mkdir()
    (nested / "artist - song.mkv").write_bytes(b"a much longer encode")

    result = DuplicateDetector().detect(LibraryAnalyzer().analyze(tmp_path))

    assert len(result.groups) == 1
    assert result.groups[0].kind is DuplicateKind.METADATA
    assert result.groups[0].recoverable_bytes == 0


def test_does_not_repeat_exact_group_as_metadata_match(tmp_path: Path) -> None:
    content = b"same file"
    (tmp_path / "Artist - Song.mp4").write_bytes(content)
    nested = tmp_path / "copy"
    nested.mkdir()
    (nested / "artist - song.mp4").write_bytes(content)

    result = DuplicateDetector().detect(LibraryAnalyzer().analyze(tmp_path))

    assert [group.kind for group in result.groups] == [DuplicateKind.EXACT]


def test_hashes_only_files_that_share_a_size(tmp_path: Path) -> None:
    first = tmp_path / "Artist - One.mp4"
    second = tmp_path / "Other - Two.mp4"
    first.write_bytes(b"1")
    second.write_bytes(b"22")
    hashed: list[Path] = []

    def record_hash(path: Path) -> str:
        hashed.append(path)
        return "digest"

    DuplicateDetector(hasher=record_hash).detect(LibraryAnalyzer().analyze(tmp_path))

    assert hashed == []


def test_hash_errors_are_recoverable(tmp_path: Path) -> None:
    (tmp_path / "Artist - One.mp4").write_bytes(b"a")
    (tmp_path / "Other - Two.mp4").write_bytes(b"b")

    def fail_hash(path: Path) -> str:
        raise OSError(f"cannot read {path.name}")

    result = DuplicateDetector(hasher=fail_hash).detect(
        LibraryAnalyzer().analyze(tmp_path)
    )

    assert result.groups == ()
    assert len(result.issues) == 2
    assert all("Unable to hash file" in issue.message for issue in result.issues)


def test_duplicate_detection_does_not_modify_media(tmp_path: Path) -> None:
    first = tmp_path / "Artist - Song.mp4"
    second = tmp_path / "copy.mp4"
    first.write_bytes(b"unchanged")
    second.write_bytes(b"unchanged")
    before = {path: path.stat().st_mtime_ns for path in (first, second)}

    DuplicateDetector().detect(LibraryAnalyzer().analyze(tmp_path))

    assert first.read_bytes() == b"unchanged"
    assert second.read_bytes() == b"unchanged"
    assert {path: path.stat().st_mtime_ns for path in (first, second)} == before
