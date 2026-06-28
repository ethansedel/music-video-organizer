from pathlib import Path

from mvo.analyzer import LibraryAnalyzer
from mvo.enrichment import MusicBrainzEnricher
from mvo.models import MatchStatus
from mvo.musicbrainz import MusicBrainzClient


def _payload(artist: str = "Artist", title: str = "Song", score: int = 100):
    return {
        "recordings": [
            {
                "id": "recording-id",
                "score": score,
                "title": title,
                "artist-credit": [{"name": artist}],
            }
        ]
    }


def test_marks_exact_high_score_candidate_as_matched(tmp_path: Path) -> None:
    (tmp_path / "Artist - Song.mp4").touch()
    analysis = LibraryAnalyzer().analyze(tmp_path)
    client = MusicBrainzClient(transport=lambda *_args: _payload())

    result = MusicBrainzEnricher(client).enrich(analysis)

    assert result.items[0].status is MatchStatus.MATCHED
    assert result.items[0].message == "exact artist/title match"
    assert result.query_count == 1


def test_marks_inexact_candidate_for_review(tmp_path: Path) -> None:
    (tmp_path / "Artist - Song.mp4").touch()
    analysis = LibraryAnalyzer().analyze(tmp_path)
    client = MusicBrainzClient(
        transport=lambda *_args: _payload(title="Different Song", score=90)
    )

    result = MusicBrainzEnricher(client).enrich(analysis)

    assert result.items[0].status is MatchStatus.REVIEW


def test_skips_low_confidence_filename_without_query(tmp_path: Path) -> None:
    (tmp_path / "Mystery.mp4").touch()
    analysis = LibraryAnalyzer().analyze(tmp_path)
    client = MusicBrainzClient(transport=lambda *_args: _payload())

    result = MusicBrainzEnricher(client).enrich(analysis)

    assert result.items[0].status is MatchStatus.SKIPPED
    assert result.query_count == 0


def test_enforces_query_cap_but_allows_cached_repeat(tmp_path: Path) -> None:
    (tmp_path / "Artist - Song.mp4").touch()
    nested = tmp_path / "copy"
    nested.mkdir()
    (nested / "Artist - Song.mkv").touch()
    (tmp_path / "Other - Title.mp4").touch()
    analysis = LibraryAnalyzer().analyze(tmp_path)
    client = MusicBrainzClient(transport=lambda *_args: _payload())

    result = MusicBrainzEnricher(client).enrich(analysis, max_queries=1)

    assert result.query_count == 1
    assert [item.status for item in result.items].count(MatchStatus.SKIPPED) == 1


def test_reports_transport_error_without_stopping_run(tmp_path: Path) -> None:
    (tmp_path / "Artist - Song.mp4").touch()
    analysis = LibraryAnalyzer().analyze(tmp_path)

    def fail(*_args):
        raise OSError("offline")

    result = MusicBrainzEnricher(MusicBrainzClient(transport=fail)).enrich(analysis)

    assert result.items[0].status is MatchStatus.ERROR
    assert "offline" in result.items[0].message
