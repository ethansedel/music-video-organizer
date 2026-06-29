"""Small, rate-limited client for the public MusicBrainz recording search API."""

from __future__ import annotations

import json
import time
from collections.abc import Callable, Mapping
from typing import Any
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from mvo.models import MusicBrainzCandidate, ReleaseGroupRef

_RECORDING_ENDPOINT = "https://musicbrainz.org/ws/2/recording/"
_RELEASE_GROUP_ENDPOINT = "https://musicbrainz.org/ws/2/release-group/"
_CONTACT = "https://github.com/ethansedel/music-video-organizer"
_USER_AGENT = f"MusicVideoOrganizer/0.8.0 ({_CONTACT})"

Transport = Callable[[str, Mapping[str, str], float], Mapping[str, Any]]


class MusicBrainzError(RuntimeError):
    """A recoverable MusicBrainz request or response failure."""


class MusicBrainzClient:
    """Search recordings while identifying MVO and honoring one request/second."""

    def __init__(
        self,
        transport: Transport | None = None,
        *,
        clock: Callable[[], float] = time.monotonic,
        sleep: Callable[[float], None] = time.sleep,
        minimum_interval: float = 1.0,
        timeout: float = 15.0,
    ) -> None:
        self._transport = transport or self._request_json
        self._clock = clock
        self._sleep = sleep
        self._minimum_interval = minimum_interval
        self._timeout = timeout
        self._last_request_at: float | None = None
        self._cache: dict[tuple[str, str, int], tuple[MusicBrainzCandidate, ...]] = {}
        self._release_group_cache: dict[
            tuple[str, str, int], tuple[ReleaseGroupRef, ...]
        ] = {}
        self.request_count = 0

    def search_recordings(
        self, artist: str, title: str, *, limit: int = 5
    ) -> tuple[MusicBrainzCandidate, ...]:
        """Search recording candidates with an in-memory exact-query cache."""

        if not 1 <= limit <= 100:
            raise ValueError("MusicBrainz search limit must be between 1 and 100")
        cache_key = (artist.casefold(), title.casefold(), limit)
        if cache_key in self._cache:
            return self._cache[cache_key]

        self._wait_for_rate_limit()
        escaped_artist = self._escape(artist)
        escaped_title = self._escape(title)
        query = (
            f'artist:"{escaped_artist}" AND recording:"{escaped_title}" '
            "AND status:official"
        )
        params = urlencode({"query": query, "fmt": "json", "limit": limit})
        url = f"{_RECORDING_ENDPOINT}?{params}"
        try:
            payload = self._transport(
                url,
                {"User-Agent": _USER_AGENT, "Accept": "application/json"},
                self._timeout,
            )
            candidates = self._parse_candidates(payload)
        except (OSError, ValueError, TypeError, KeyError) as error:
            raise MusicBrainzError(str(error)) from error
        finally:
            self._last_request_at = self._clock()
            self.request_count += 1
        self._cache[cache_key] = candidates
        return candidates

    def search_release_groups(
        self, artist: str, title: str, *, limit: int = 5
    ) -> tuple[ReleaseGroupRef, ...]:
        """Search release groups directly for canonical artwork candidates."""

        if not 1 <= limit <= 100:
            raise ValueError("MusicBrainz search limit must be between 1 and 100")
        cache_key = (artist.casefold(), title.casefold(), limit)
        if cache_key in self._release_group_cache:
            return self._release_group_cache[cache_key]
        self._wait_for_rate_limit()
        escaped_artist = self._escape(artist)
        escaped_title = self._escape(title)
        query = f'artist:"{escaped_artist}" AND releasegroup:"{escaped_title}"'
        params = urlencode({"query": query, "fmt": "json", "limit": limit})
        url = f"{_RELEASE_GROUP_ENDPOINT}?{params}"
        try:
            payload = self._transport(
                url,
                {"User-Agent": _USER_AGENT, "Accept": "application/json"},
                self._timeout,
            )
            groups = self._parse_release_groups(payload)
        except (OSError, ValueError, TypeError, KeyError) as error:
            raise MusicBrainzError(str(error)) from error
        finally:
            self._last_request_at = self._clock()
            self.request_count += 1
        self._release_group_cache[cache_key] = groups
        return groups

    def would_query(self, artist: str, title: str, *, limit: int = 5) -> bool:
        """Return whether this search would consume a live API request."""

        return (artist.casefold(), title.casefold(), limit) not in self._cache

    @staticmethod
    def _parse_release_groups(
        payload: Mapping[str, Any],
    ) -> tuple[ReleaseGroupRef, ...]:
        groups = payload.get("release-groups", [])
        if not isinstance(groups, list):
            raise ValueError("MusicBrainz response has no release group list")
        result: list[ReleaseGroupRef] = []
        for group in groups:
            credits = group.get("artist-credit", [])
            artist_credit = "".join(
                f"{credit.get('name') or credit.get('artist', {}).get('name', '')}"
                f"{credit.get('joinphrase', '')}"
                for credit in credits
                if isinstance(credit, dict)
            ).strip()
            result.append(
                ReleaseGroupRef(
                    release_group_id=str(group["id"]),
                    title=str(group.get("title", "")),
                    primary_type=group.get("primary-type"),
                    score=int(group.get("score", 0)),
                    artist_credit=artist_credit,
                )
            )
        return tuple(result)

    def _wait_for_rate_limit(self) -> None:
        if self._last_request_at is None:
            return
        remaining = self._minimum_interval - (self._clock() - self._last_request_at)
        if remaining > 0:
            self._sleep(remaining)

    @staticmethod
    def _parse_candidates(
        payload: Mapping[str, Any],
    ) -> tuple[MusicBrainzCandidate, ...]:
        recordings = payload.get("recordings", [])
        if not isinstance(recordings, list):
            raise ValueError("MusicBrainz response has no recording list")
        result: list[MusicBrainzCandidate] = []
        for recording in recordings:
            credits = recording.get("artist-credit", [])
            artist_credit = "".join(
                f"{credit.get('name') or credit.get('artist', {}).get('name', '')}"
                f"{credit.get('joinphrase', '')}"
                for credit in credits
                if isinstance(credit, dict)
            ).strip()
            releases = recording.get("releases", [])
            release_titles = tuple(
                release["title"]
                for release in releases
                if isinstance(release, dict) and release.get("title")
            )
            release_groups: list[ReleaseGroupRef] = []
            seen_groups: set[str] = set()
            for release in releases:
                if not isinstance(release, dict):
                    continue
                group = release.get("release-group") or {}
                group_id = group.get("id")
                if not group_id or group_id in seen_groups:
                    continue
                seen_groups.add(group_id)
                release_groups.append(
                    ReleaseGroupRef(
                        release_group_id=str(group_id),
                        title=str(group.get("title") or release.get("title") or ""),
                        primary_type=group.get("primary-type"),
                    )
                )
            result.append(
                MusicBrainzCandidate(
                    recording_id=str(recording["id"]),
                    title=str(recording.get("title", "")),
                    artist_credit=artist_credit,
                    score=int(recording.get("score", 0)),
                    first_release_date=recording.get("first-release-date"),
                    release_titles=release_titles,
                    video=recording.get("video"),
                    release_groups=tuple(release_groups),
                )
            )
        return tuple(result)

    @staticmethod
    def _escape(value: str) -> str:
        return value.replace("\\", "\\\\").replace('"', '\\"')

    @staticmethod
    def _request_json(
        url: str, headers: Mapping[str, str], timeout: float
    ) -> Mapping[str, Any]:
        request = Request(url, headers=dict(headers))
        with urlopen(request, timeout=timeout) as response:  # noqa: S310
            return json.load(response)
