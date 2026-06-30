from pathlib import Path

from mvo.analyzer import LibraryAnalyzer
from mvo.musicbrainz import MusicBrainzClient
from mvo.overrides import MetadataOverrideStore
from mvo.review import ReviewSession, _basic_authorization


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


def test_network_review_uses_liner_notes_basic_credentials() -> None:
    assert _basic_authorization("secret-pass") == (
        "Basic bGluZXItbm90ZXM6c2VjcmV0LXBhc3M="
    )


def test_review_session_rejects_video_not_in_review_set(tmp_path: Path) -> None:
    media = tmp_path / "Artist - Song.mp4"
    media.write_bytes(b"video")
    session = ReviewSession(
        LibraryAnalyzer().analyze(tmp_path),
        MetadataOverrideStore(tmp_path / "reviews.json"),
    )

    assert session.items() == []


def test_all_scope_includes_already_organized_videos(tmp_path: Path) -> None:
    artist = tmp_path / "Artist"
    artist.mkdir()
    (artist / "Artist - Song.mp4").write_bytes(b"video")
    session = ReviewSession(
        LibraryAnalyzer().analyze(tmp_path),
        MetadataOverrideStore(tmp_path / "reviews.json"),
    )

    assert session.items() == []
    assert session.items(scope="all")[0]["status"] == "organized"


def test_conflict_recommends_higher_resolution_and_preserves_alternate(
    tmp_path: Path,
) -> None:
    (tmp_path / "Artist - Song [720p].mp4").write_bytes(b"small")
    preferred = tmp_path / "Artist - Song [1080p].mp4"
    preferred.write_bytes(b"larger video")
    store = MetadataOverrideStore(tmp_path / "reviews.json")
    session = ReviewSession(LibraryAnalyzer().analyze(tmp_path), store)

    items = session.items()
    recommended = next(item for item in items if item["recommended"])
    assert set(recommended["conflict_paths"]) == {
        "Artist - Song [720p].mp4",
        "Artist - Song [1080p].mp4",
    }
    updated = session.choose_preferred(recommended["path"])

    assert recommended["path"] == preferred.name
    assert all(item["status"] == "resolved" for item in updated)
    destinations = {item["destination"] for item in updated}
    assert destinations == {
        "Artist/Artist - Song.mp4",
        "Artist/Artist - Song [Alternate].mp4",
    }


def test_conflict_copy_can_move_to_recoverable_mvo_trash(tmp_path: Path) -> None:
    unwanted = tmp_path / "Artist - Song [720p].mp4"
    unwanted.write_bytes(b"lower")
    (tmp_path / "Artist - Song [1080p].mp4").write_bytes(b"higher")
    session = ReviewSession(
        LibraryAnalyzer().analyze(tmp_path),
        MetadataOverrideStore(tmp_path / "reviews.json"),
    )

    result = session.trash_duplicate(unwanted.name, "TRASH_FILE")

    assert not unwanted.exists()
    assert (tmp_path / result["destination"]).read_bytes() == b"lower"
    assert result["destination"] == f".mvo-trash/{unwanted.name}"
    assert session.items() == []
    trash_items = session.items(scope="trash")
    assert len(trash_items) == 1
    assert trash_items[0]["trashed"] is True
    assert session.media_path(trash_items[0]["path"]).read_bytes() == b"lower"


def test_manual_musicbrainz_search_returns_editable_candidate(
    tmp_path: Path,
) -> None:
    (tmp_path / "Mystery.mp4").write_bytes(b"video")
    payload = {
        "recordings": [
            {
                "id": "recording-id",
                "score": 99,
                "title": "Misery Business",
                "first-release-date": "2007-06-18",
                "artist-credit": [{"name": "Paramore"}],
            }
        ]
    }
    client = MusicBrainzClient(transport=lambda *_args: payload)
    session = ReviewSession(
        LibraryAnalyzer().analyze(tmp_path),
        MetadataOverrideStore(tmp_path / "reviews.json"),
        musicbrainz=client,
    )

    candidates = session.search_metadata("Paramore", "Misery Business")

    assert candidates == [
        {
            "artist": "Paramore",
            "title": "Misery Business",
            "year": 2007,
            "score": 99,
            "recording_id": "recording-id",
        }
    ]


def test_commit_requires_phrase_and_moves_only_saved_correction(
    tmp_path: Path,
) -> None:
    media = tmp_path / "Mystery.mp4"
    media.write_bytes(b"video")
    store = MetadataOverrideStore(tmp_path / ".mvo-overrides.json")
    session = ReviewSession(LibraryAnalyzer().analyze(tmp_path), store)
    session.update(
        "Mystery.mp4",
        {
            "artist": "Artist",
            "title": "Song",
            "featured_artists": [],
            "versions": [],
            "year": None,
        },
    )

    try:
        session.apply_saved("wrong")
    except ValueError as error:
        assert "MOVE_FILES" in str(error)
    else:
        raise AssertionError("commit accepted the wrong confirmation")

    result = session.apply_saved("MOVE_FILES")

    assert result["moved"] == 1
    assert not media.exists()
    assert (tmp_path / "Artist" / "Artist - Song.mp4").read_bytes() == b"video"
    assert (tmp_path / ".mvo-review-execution.html").exists()
