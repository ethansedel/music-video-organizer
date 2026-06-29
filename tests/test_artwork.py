from pathlib import Path

from mvo.analyzer import LibraryAnalyzer
from mvo.artwork import ArtworkFinder
from mvo.coverart import CoverArtClient
from mvo.models import ArtworkStatus
from mvo.musicbrainz import MusicBrainzClient


def _musicbrainz_payload(with_group: bool = True):
    groups = (
        [
            {
                "id": "release-group-id",
                "score": 100,
                "title": "Song",
                "primary-type": "Single",
                "artist-credit": [{"name": "Artist"}],
            }
        ]
        if with_group
        else []
    )
    return {"release-groups": groups}


def _art_payload():
    return {
        "images": [
            {
                "image": "https://coverartarchive.org/image.jpg",
                "thumbnails": {"250": "https://coverartarchive.org/image-250.jpg"},
                "types": ["Front"],
                "front": True,
                "back": False,
                "approved": True,
                "comment": "",
            }
        ]
    }


def _finder(*, with_group: bool = True, with_art: bool = True) -> ArtworkFinder:
    musicbrainz = MusicBrainzClient(
        transport=lambda *_args: _musicbrainz_payload(with_group)
    )
    cover_art = CoverArtClient(
        transport=lambda *_args: _art_payload() if with_art else None
    )
    return ArtworkFinder(musicbrainz, cover_art)


def test_finds_canonical_release_group_artwork(tmp_path: Path) -> None:
    (tmp_path / "Artist - Song.mp4").touch()

    result = _finder().find(LibraryAnalyzer().analyze(tmp_path))

    item = result.items[0]
    assert item.status is ArtworkStatus.FOUND
    assert item.release_group is not None
    assert item.release_group.release_group_id == "release-group-id"
    assert item.images[0].front is True
    assert result.musicbrainz_queries == 1
    assert result.cover_art_queries == 1


def test_no_archive_art_is_not_an_error(tmp_path: Path) -> None:
    (tmp_path / "Artist - Song.mp4").touch()

    result = _finder(with_art=False).find(LibraryAnalyzer().analyze(tmp_path))

    assert result.items[0].status is ArtworkStatus.NOT_FOUND
    assert result.items[0].message == "no archived artwork"


def test_missing_release_group_requires_review(tmp_path: Path) -> None:
    (tmp_path / "Artist - Song.mp4").touch()

    result = _finder(with_group=False).find(LibraryAnalyzer().analyze(tmp_path))

    assert result.items[0].status is ArtworkStatus.REVIEW
    assert result.cover_art_queries == 0


def test_caps_artwork_queries(tmp_path: Path) -> None:
    for name in ("Artist - One.mp4", "Artist - Two.mp4"):
        (tmp_path / name).touch()

    result = _finder().find(LibraryAnalyzer().analyze(tmp_path), max_files=1)

    assert [item.status for item in result.items].count(ArtworkStatus.SKIPPED) == 1
    assert result.musicbrainz_queries == 2


def test_falls_back_to_next_release_group_with_art(tmp_path: Path) -> None:
    (tmp_path / "Artist - Song.mp4").touch()
    payload = _musicbrainz_payload()
    payload["release-groups"].insert(0, {"id": "no-art", "score": 100, "title": "Song"})
    musicbrainz = MusicBrainzClient(transport=lambda *_args: payload)
    cover_art = CoverArtClient(
        transport=lambda url, *_args: None if url.endswith("no-art") else _art_payload()
    )

    result = ArtworkFinder(musicbrainz, cover_art).find(
        LibraryAnalyzer().analyze(tmp_path)
    )

    assert result.items[0].status is ArtworkStatus.FOUND
    assert result.items[0].release_group is not None
    assert result.items[0].release_group.release_group_id == "release-group-id"
    assert result.cover_art_queries == 2


def test_recording_fallback_prefers_studio_group_over_live_group(
    tmp_path: Path,
) -> None:
    (tmp_path / "Artist - Song.mp4").touch()
    recording_payload = {
        "recordings": [
            {
                "id": "live-recording",
                "score": 100,
                "title": "Song",
                "artist-credit": [{"name": "Artist"}],
                "releases": [
                    {
                        "title": "Concert Live",
                        "release-group": {
                            "id": "live-group",
                            "title": "Concert Live",
                            "primary-type": "Album",
                        },
                    }
                ],
            },
            {
                "id": "studio-recording",
                "score": 99,
                "title": "Song",
                "artist-credit": [{"name": "Artist"}],
                "releases": [
                    {
                        "title": "Studio Album",
                        "release-group": {
                            "id": "studio-group",
                            "title": "Studio Album",
                            "primary-type": "Album",
                        },
                    }
                ],
            },
        ]
    }

    def musicbrainz_transport(url, *_args):
        return recording_payload if "/recording" in url else {"release-groups": []}

    musicbrainz = MusicBrainzClient(transport=musicbrainz_transport)
    cover_art = CoverArtClient(transport=lambda *_args: _art_payload())

    result = ArtworkFinder(musicbrainz, cover_art).find(
        LibraryAnalyzer().analyze(tmp_path)
    )

    assert result.items[0].release_group is not None
    assert result.items[0].release_group.release_group_id == "studio-group"


def test_artwork_lookup_does_not_create_or_modify_media_files(tmp_path: Path) -> None:
    media = tmp_path / "Artist - Song.mp4"
    media.write_bytes(b"unchanged")
    before = media.stat().st_mtime_ns

    _finder().find(LibraryAnalyzer().analyze(tmp_path))

    assert media.read_bytes() == b"unchanged"
    assert media.stat().st_mtime_ns == before
    assert list(tmp_path.glob("*.jpg")) == []
