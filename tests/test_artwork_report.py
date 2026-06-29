from pathlib import Path

from mvo.analyzer import LibraryAnalyzer
from mvo.artwork import ArtworkFinder
from mvo.artwork_report import render_artwork_html, write_artwork_report
from mvo.coverart import CoverArtClient
from mvo.musicbrainz import MusicBrainzClient


def _result(tmp_path: Path):
    (tmp_path / "Artist - A&B.mp4").touch()
    musicbrainz_payload = {
        "release-groups": [
            {
                "id": "group",
                "score": 100,
                "title": "A&B",
                "artist-credit": [{"name": "Artist"}],
            }
        ]
    }
    art_payload = {
        "images": [
            {
                "image": "https://coverartarchive.org/full.jpg",
                "thumbnails": {"250": "https://coverartarchive.org/thumb.jpg"},
                "types": ["Front"],
                "front": True,
                "back": False,
                "approved": True,
                "comment": "",
            }
        ]
    }
    finder = ArtworkFinder(
        MusicBrainzClient(transport=lambda *_args: musicbrainz_payload),
        CoverArtClient(transport=lambda *_args: art_payload),
    )
    return finder.find(LibraryAnalyzer().analyze(tmp_path))


def test_report_escapes_metadata_and_uses_lazy_remote_preview(tmp_path: Path) -> None:
    html = render_artwork_html(_result(tmp_path))

    assert "<script>" not in html
    assert "Artist - A&amp;B.mp4" in html
    assert 'loading="lazy"' in html
    assert 'referrerpolicy="no-referrer"' in html
    assert "https://coverartarchive.org/thumb.jpg" in html
    assert "did not download" in html


def test_writes_artwork_report_only(tmp_path: Path) -> None:
    output = tmp_path / "artwork.html"

    written = write_artwork_report(_result(tmp_path), output)

    assert written == output.resolve()
    assert list(tmp_path.glob("*.jpg")) == []
