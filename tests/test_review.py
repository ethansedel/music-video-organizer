from pathlib import Path

from mvo.analyzer import LibraryAnalyzer
from mvo.overrides import MetadataOverrideStore
from mvo.review import ReviewSession


def test_review_session_shows_skipped_video_and_saves_resolution(
    tmp_path: Path,
) -> None:
    media = tmp_path / "Mystery.mp4"
    media.write_bytes(b"video")
    store = MetadataOverrideStore(tmp_path / ".mvo-overrides.json")
    session = ReviewSession(LibraryAnalyzer().analyze(tmp_path), store)

    before = session.items()
    updated = session.update(
        "Mystery.mp4",
        {
            "artist": "Artist",
            "title": "Song",
            "featured_artists": [],
            "versions": [],
            "year": None,
        },
    )

    assert len(before) == 1
    assert before[0]["status"] == "review"
    assert updated["status"] == "resolved"
    assert updated["destination"] == "Artist/Artist - Song.mp4"
    assert media.read_bytes() == b"video"
    assert store.path.exists()


def test_review_session_rejects_video_not_in_review_set(tmp_path: Path) -> None:
    media = tmp_path / "Artist - Song.mp4"
    media.write_bytes(b"video")
    session = ReviewSession(
        LibraryAnalyzer().analyze(tmp_path),
        MetadataOverrideStore(tmp_path / "reviews.json"),
    )

    assert session.items() == []
