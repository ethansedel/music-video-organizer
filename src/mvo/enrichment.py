"""Match parsed filenames to optional MusicBrainz recording candidates."""

from __future__ import annotations

import re
import unicodedata

from mvo.models import (
    AnalysisResult,
    ConfidenceLevel,
    EnrichedVideo,
    EnrichmentResult,
    MatchStatus,
    MusicBrainzCandidate,
)
from mvo.musicbrainz import MusicBrainzClient, MusicBrainzError

_WHITESPACE = re.compile(r"\s+")


class MusicBrainzEnricher:
    """Apply a bounded number of MusicBrainz searches to parsed videos."""

    def __init__(self, client: MusicBrainzClient | None = None) -> None:
        self._client = client or MusicBrainzClient()

    def enrich(
        self, analysis: AnalysisResult, *, max_queries: int = 25
    ) -> EnrichmentResult:
        """Enrich eligible videos, conservatively auto-matching only exact names."""

        if max_queries < 0:
            raise ValueError("max_queries cannot be negative")
        items: list[EnrichedVideo] = []
        for video in analysis.videos:
            parsed = video.parsed
            if not parsed.artist or parsed.confidence.level is ConfidenceLevel.LOW:
                items.append(
                    EnrichedVideo(
                        video, MatchStatus.SKIPPED, (), "metadata needs review"
                    )
                )
                continue
            if self._client.request_count >= max_queries and self._client.would_query(
                parsed.artist, parsed.title
            ):
                items.append(
                    EnrichedVideo(video, MatchStatus.SKIPPED, (), "query limit reached")
                )
                continue
            try:
                candidates = self._client.search_recordings(parsed.artist, parsed.title)
            except MusicBrainzError as error:
                items.append(
                    EnrichedVideo(
                        video, MatchStatus.ERROR, (), f"lookup failed: {error}"
                    )
                )
                continue
            if not candidates:
                items.append(
                    EnrichedVideo(
                        video, MatchStatus.NOT_FOUND, (), "no recording found"
                    )
                )
                continue
            best = candidates[0]
            if self._is_strong_match(parsed.artist, parsed.title, best):
                status = MatchStatus.MATCHED
                message = "exact artist/title match"
            else:
                status = MatchStatus.REVIEW
                message = "candidate requires review"
            items.append(EnrichedVideo(video, status, candidates, message))
        return EnrichmentResult(analysis.root, tuple(items), self._client.request_count)

    @classmethod
    def _is_strong_match(
        cls, artist: str, title: str, candidate: MusicBrainzCandidate
    ) -> bool:
        return (
            candidate.score >= 95
            and cls._normalize(artist) == cls._normalize(candidate.artist_credit)
            and cls._normalize(title) == cls._normalize(candidate.title)
        )

    @staticmethod
    def _normalize(value: str) -> str:
        value = unicodedata.normalize("NFKC", value).casefold()
        return _WHITESPACE.sub(" ", value).strip()
