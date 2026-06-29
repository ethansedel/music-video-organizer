from pathlib import Path

from mvo.acoustid import AcoustIDClient, FingerprintError
from mvo.analyzer import LibraryAnalyzer
from mvo.fingerprinting import AcousticIdentifier
from mvo.models import AcousticFingerprint, MatchStatus


class FakeExtractor:
    def __init__(self, fail: bool = False) -> None:
        self.fail = fail
        self.paths: list[Path] = []

    def fingerprint(self, path: Path) -> AcousticFingerprint:
        self.paths.append(path)
        if self.fail:
            raise FingerprintError("decoder failed")
        return AcousticFingerprint(180, f"fingerprint-{path.name}")


def _client(score: float = 0.98, recordings: bool = True) -> AcoustIDClient:
    recording_data = (
        [{"id": "recording", "title": "Song", "artists": [{"name": "Artist"}]}]
        if recordings
        else []
    )
    return AcoustIDClient(
        "key",
        transport=lambda *_args: {
            "status": "ok",
            "results": [{"id": "track", "score": score, "recordings": recording_data}],
        },
        minimum_interval=0,
    )


def test_identifies_strong_acoustic_match(tmp_path: Path) -> None:
    (tmp_path / "Mystery.mp4").touch()

    result = AcousticIdentifier(FakeExtractor(), _client()).identify(
        LibraryAnalyzer().analyze(tmp_path)
    )

    assert result.items[0].status is MatchStatus.MATCHED
    assert result.items[0].duration == 180
    assert result.fingerprint_count == 1
    assert result.lookup_count == 1


def test_weak_or_unlinked_candidate_requires_review(tmp_path: Path) -> None:
    (tmp_path / "Mystery.mp4").touch()

    result = AcousticIdentifier(FakeExtractor(), _client(score=0.5)).identify(
        LibraryAnalyzer().analyze(tmp_path)
    )

    assert result.items[0].status is MatchStatus.REVIEW


def test_caps_files_before_fingerprinting(tmp_path: Path) -> None:
    for name in ("A.mp4", "B.mp4", "C.mp4"):
        (tmp_path / name).touch()
    extractor = FakeExtractor()

    result = AcousticIdentifier(extractor, _client()).identify(
        LibraryAnalyzer().analyze(tmp_path), max_files=1
    )

    assert len(extractor.paths) == 1
    assert [item.status for item in result.items].count(MatchStatus.SKIPPED) == 2


def test_fingerprint_error_does_not_stop_report(tmp_path: Path) -> None:
    (tmp_path / "Mystery.mp4").touch()

    result = AcousticIdentifier(FakeExtractor(fail=True), _client()).identify(
        LibraryAnalyzer().analyze(tmp_path)
    )

    assert result.items[0].status is MatchStatus.ERROR
    assert "decoder failed" in result.items[0].message
    assert result.lookup_count == 0


def test_fingerprinting_does_not_modify_media(tmp_path: Path) -> None:
    media = tmp_path / "Artist - Song.mp4"
    media.write_bytes(b"unchanged")
    before = media.stat().st_mtime_ns

    AcousticIdentifier(FakeExtractor(), _client()).identify(
        LibraryAnalyzer().analyze(tmp_path)
    )

    assert media.read_bytes() == b"unchanged"
    assert media.stat().st_mtime_ns == before
