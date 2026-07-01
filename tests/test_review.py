from http.client import HTTPConnection
from http.server import ThreadingHTTPServer
from pathlib import Path
from threading import Thread
from urllib.parse import urlencode

import pytest

from mvo.analyzer import LibraryAnalyzer
from mvo.musicbrainz import MusicBrainzClient
from mvo.overrides import MetadataOverrideStore
from mvo.review import ReviewSession, _handler_for, _login_page, _page


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


def test_network_review_uses_themed_liner_notes_login() -> None:
    page = _login_page("Wrong password")

    assert "Liner Notes" in page
    assert "Music Video Organizer" in page
    assert "Wrong password" in page
    assert 'name="username" value="liner-notes"' in page


def test_review_page_keeps_javascript_newline_escapes() -> None:
    page = _page("token")

    assert r"join('\n')" in page
    assert "join('\n')" not in page


def test_network_review_login_uses_secure_session_cookie(tmp_path: Path) -> None:
    (tmp_path / "Mystery.mp4").write_bytes(b"video")
    session = ReviewSession(
        LibraryAnalyzer().analyze(tmp_path),
        MetadataOverrideStore(tmp_path / "reviews.json"),
    )
    server = ThreadingHTTPServer(
        ("127.0.0.1", 0), _handler_for(session, "csrf", password="secret-pass")
    )
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    connection = HTTPConnection("127.0.0.1", server.server_port, timeout=5)
    try:
        connection.request("GET", "/")
        response = connection.getresponse()
        response.read()
        assert response.status == 303
        assert response.getheader("Location") == "/login"

        body = urlencode({"username": "liner-notes", "password": "secret-pass"})
        connection.request(
            "POST",
            "/login",
            body,
            {"Content-Type": "application/x-www-form-urlencoded"},
        )
        response = connection.getresponse()
        response.read()
        cookie = response.getheader("Set-Cookie")
        assert response.status == 303
        assert "HttpOnly" in cookie
        assert "SameSite=Strict" in cookie

        connection.request("GET", "/", headers={"Cookie": cookie})
        response = connection.getresponse()
        page = response.read().decode()
        assert response.status == 200
        assert "Commit saved changes" in page
    finally:
        connection.close()
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


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


def test_conflict_recommends_higher_resolution_and_trashes_other_copy(
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
    assert len(updated) == 1
    assert updated[0]["status"] == "resolved"
    assert updated[0]["destination"] == "Artist/Artist - Song.mp4"
    assert not (tmp_path / "Artist - Song [720p].mp4").exists()
    assert (tmp_path / ".mvo-trash" / "Artist - Song [720p].mp4").exists()


def test_conflict_copy_can_move_to_recoverable_mvo_trash(tmp_path: Path) -> None:
    unwanted = tmp_path / "Artist - Song [720p].mp4"
    unwanted.write_bytes(b"lower")
    (tmp_path / "Artist - Song [1080p].mp4").write_bytes(b"higher")
    session = ReviewSession(
        LibraryAnalyzer().analyze(tmp_path),
        MetadataOverrideStore(tmp_path / "reviews.json"),
    )

    result = session.trash_duplicate(unwanted.name)

    assert not unwanted.exists()
    assert (tmp_path / result["destination"]).read_bytes() == b"lower"
    assert result["destination"] == f".mvo-trash/{unwanted.name}"
    assert session.items() == []
    trash_items = session.items(scope="trash")
    assert len(trash_items) == 1
    assert trash_items[0]["trashed"] is True
    assert session.media_path(trash_items[0]["path"]).read_bytes() == b"lower"


def test_review_refresh_finds_new_video(tmp_path: Path) -> None:
    (tmp_path / "Artist - First.mp4").write_bytes(b"first")
    session = ReviewSession(
        LibraryAnalyzer().analyze(tmp_path),
        MetadataOverrideStore(tmp_path / "reviews.json"),
    )
    (tmp_path / "Mystery.mp4").write_bytes(b"second")

    result = session.refresh()

    assert result["videos"] == 2
    assert any(item["path"] == "Mystery.mp4" for item in session.items())


def test_review_exports_jellyfin_nfo_without_overwrite(tmp_path: Path) -> None:
    artist = tmp_path / "Paramore"
    artist.mkdir()
    video = artist / "Paramore - Misery Business (2007).mp4"
    video.write_bytes(b"video")
    session = ReviewSession(
        LibraryAnalyzer().analyze(tmp_path),
        MetadataOverrideStore(tmp_path / "reviews.json"),
    )
    relative = video.relative_to(tmp_path).as_posix()

    preview = session.nfo_preview(relative)
    result = session.export_nfo([relative])

    assert preview["path"] == "Paramore/Paramore - Misery Business (2007).nfo"
    assert "Paramore - Misery Business" in preview["content"]
    assert result["written"] == [preview["path"]]
    assert session.export_nfo([relative])["errors"]


def test_review_nfo_requires_video_to_be_organized_first(tmp_path: Path) -> None:
    video = tmp_path / "Artist - Song.mp4"
    video.write_bytes(b"video")
    session = ReviewSession(
        LibraryAnalyzer().analyze(tmp_path),
        MetadataOverrideStore(tmp_path / "reviews.json"),
    )

    with pytest.raises(ValueError, match="organize this video"):
        session.nfo_preview(video.name)


def test_history_can_undo_quarantined_duplicate(tmp_path: Path) -> None:
    unwanted = tmp_path / "Artist - Song [720p].mp4"
    unwanted.write_bytes(b"lower")
    (tmp_path / "Artist - Song [1080p].mp4").write_bytes(b"higher")
    session = ReviewSession(
        LibraryAnalyzer().analyze(tmp_path),
        MetadataOverrideStore(tmp_path / "reviews.json"),
    )
    session.trash_duplicate(unwanted.name)

    record = session.history_items()[0]
    session.undo_history(record["id"])

    assert unwanted.read_bytes() == b"lower"
    assert session.history_items()[1]["can_undo"] is False


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
