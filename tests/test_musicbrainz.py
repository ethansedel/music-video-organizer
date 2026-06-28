from collections.abc import Mapping
from typing import Any
from urllib.parse import parse_qs, urlparse

import pytest

from mvo.musicbrainz import MusicBrainzClient, MusicBrainzError


def _payload() -> dict[str, Any]:
    return {
        "recordings": [
            {
                "id": "026fa041-3917-4c73-9079-ed16e36f20f8",
                "score": "100",
                "title": "Song",
                "video": True,
                "first-release-date": "2020-01-02",
                "artist-credit": [
                    {"name": "Artist", "joinphrase": " feat. "},
                    {"artist": {"name": "Guest"}},
                ],
                "releases": [{"title": "Single"}],
            }
        ]
    }


def test_search_builds_identified_json_request_and_parses_candidate() -> None:
    calls: list[tuple[str, Mapping[str, str], float]] = []

    def transport(url: str, headers: Mapping[str, str], timeout: float):
        calls.append((url, headers, timeout))
        return _payload()

    candidates = MusicBrainzClient(transport=transport).search_recordings(
        "Artist", "Song"
    )

    query = parse_qs(urlparse(calls[0][0]).query)
    assert query["fmt"] == ["json"]
    assert query["limit"] == ["5"]
    assert query["query"] == ['artist:"Artist" AND recording:"Song"']
    assert calls[0][1]["User-Agent"].startswith("MusicVideoOrganizer/0.6.0 (")
    assert candidates[0].artist_credit == "Artist feat. Guest"
    assert candidates[0].release_titles == ("Single",)
    assert candidates[0].video is True


def test_caches_identical_searches_and_rate_limits_distinct_ones() -> None:
    now = [0.0]
    sleeps: list[float] = []

    def clock() -> float:
        return now[0]

    def sleep(seconds: float) -> None:
        sleeps.append(seconds)
        now[0] += seconds

    client = MusicBrainzClient(
        transport=lambda *_args: _payload(), clock=clock, sleep=sleep
    )

    client.search_recordings("Artist", "Song")
    client.search_recordings("Artist", "Song")
    client.search_recordings("Other", "Title")

    assert client.request_count == 2
    assert sleeps == [1.0]


def test_failed_request_counts_toward_rate_limit() -> None:
    def transport(*_args):
        raise OSError("service unavailable")

    client = MusicBrainzClient(transport=transport)

    with pytest.raises(MusicBrainzError, match="service unavailable"):
        client.search_recordings("Artist", "Song")

    assert client.request_count == 1


def test_rejects_invalid_search_limit() -> None:
    with pytest.raises(ValueError):
        MusicBrainzClient(transport=lambda *_args: {}).search_recordings(
            "Artist", "Song", limit=0
        )
