from pathlib import Path

from mvo.analyzer import LibraryAnalyzer
from mvo.enrichment import MusicBrainzEnricher
from mvo.enrichment_report import render_enrichment_html, write_enrichment_report
from mvo.musicbrainz import MusicBrainzClient


def _result(tmp_path: Path):
    (tmp_path / "Artist - A&B.mp4").touch()
    analysis = LibraryAnalyzer().analyze(tmp_path)
    payload = {
        "recordings": [
            {
                "id": "abc-123",
                "score": 100,
                "title": "A&B",
                "artist-credit": [{"name": "<Artist>"}],
            }
        ]
    }
    return MusicBrainzEnricher(
        MusicBrainzClient(transport=lambda *_args: payload)
    ).enrich(analysis)


def test_report_is_escaped_and_explicitly_read_only(tmp_path: Path) -> None:
    html = render_enrichment_html(_result(tmp_path))

    assert "<Artist>" not in html
    assert "&lt;Artist&gt;" in html
    assert "A&amp;B.mp4" in html
    assert "did not upload audio" in html
    assert "https://musicbrainz.org/recording/abc-123" in html
    assert "not found" in html
    assert "errors" in html


def test_writes_enrichment_report(tmp_path: Path) -> None:
    output = tmp_path / "musicbrainz.html"

    written = write_enrichment_report(_result(tmp_path), output)

    assert written == output.resolve()
    assert "MusicBrainz enrichment" in output.read_text(encoding="utf-8")
