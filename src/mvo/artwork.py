"""Orchestrate bounded MusicBrainz and Cover Art Archive preview lookups."""

from __future__ import annotations

import re
import unicodedata

from mvo.coverart import CoverArtClient, CoverArtError
from mvo.models import (
    AnalysisResult,
    ArtworkPreview,
    ArtworkResult,
    ArtworkStatus,
    ConfidenceLevel,
)
from mvo.musicbrainz import MusicBrainzClient, MusicBrainzError

_WHITESPACE = re.compile(r"\s+")
_LIVE_RELEASE = re.compile(r"\b(?:live|concert)\b", re.IGNORECASE)


class ArtworkFinder:
    """Find canonical release-group artwork metadata without saving images."""

    def __init__(
        self, musicbrainz: MusicBrainzClient, cover_art: CoverArtClient
    ) -> None:
        self._musicbrainz = musicbrainz
        self._cover_art = cover_art

    def find(self, analysis: AnalysisResult, *, max_files: int = 10) -> ArtworkResult:
        """Look up artwork for at most max_files eligible videos."""

        if max_files < 0:
            raise ValueError("max_files cannot be negative")
        items: list[ArtworkPreview] = []
        attempted = 0
        for video in analysis.videos:
            parsed = video.parsed
            if not parsed.artist or parsed.confidence.level is ConfidenceLevel.LOW:
                items.append(
                    ArtworkPreview(
                        video,
                        ArtworkStatus.SKIPPED,
                        None,
                        (),
                        "metadata needs review",
                    )
                )
                continue
            if attempted >= max_files:
                items.append(
                    ArtworkPreview(
                        video, ArtworkStatus.SKIPPED, None, (), "file limit reached"
                    )
                )
                continue
            attempted += 1
            try:
                searched_groups = self._musicbrainz.search_release_groups(
                    parsed.artist, parsed.title
                )
                release_groups = tuple(
                    group
                    for group in searched_groups
                    if self._normalize(group.title) == self._normalize(parsed.title)
                )
                if not release_groups:
                    recordings = self._musicbrainz.search_recordings(
                        parsed.artist, parsed.title
                    )
                    release_groups = self._recording_release_groups(
                        recordings, parsed.title
                    )
            except MusicBrainzError as error:
                items.append(
                    ArtworkPreview(
                        video,
                        ArtworkStatus.ERROR,
                        None,
                        (),
                        f"MusicBrainz lookup failed: {error}",
                    )
                )
                continue
            if not release_groups:
                items.append(
                    ArtworkPreview(
                        video,
                        ArtworkStatus.REVIEW,
                        None,
                        (),
                        "no release group candidate",
                    )
                )
                continue
            release_group = release_groups[0]
            images = ()
            lookup_error: CoverArtError | None = None
            for group in release_groups[:3]:
                release_group = group
                try:
                    images = self._cover_art.lookup_release_group(
                        group.release_group_id
                    )
                except CoverArtError as error:
                    lookup_error = error
                    break
                if images:
                    break
            if lookup_error:
                items.append(
                    ArtworkPreview(
                        video,
                        ArtworkStatus.ERROR,
                        release_group,
                        (),
                        f"artwork lookup failed: {lookup_error}",
                    )
                )
                continue
            status = ArtworkStatus.FOUND if images else ArtworkStatus.NOT_FOUND
            message = "remote artwork available" if images else "no archived artwork"
            items.append(ArtworkPreview(video, status, release_group, images, message))
        return ArtworkResult(
            analysis.root,
            tuple(items),
            self._musicbrainz.request_count,
            self._cover_art.request_count,
        )

    @staticmethod
    def _normalize(value: str) -> str:
        normalized = unicodedata.normalize("NFKC", value).casefold()
        return _WHITESPACE.sub(" ", normalized).strip()

    @classmethod
    def _recording_release_groups(cls, recordings, title: str):
        """Collect exact-title groups, preferring studio releases over live ones."""

        expected = cls._normalize(title)
        groups = []
        seen = set()
        for recording in recordings:
            if cls._normalize(recording.title) != expected:
                continue
            for group in recording.release_groups:
                if group.release_group_id in seen:
                    continue
                seen.add(group.release_group_id)
                groups.append(group)
        return tuple(
            sorted(groups, key=lambda group: bool(_LIVE_RELEASE.search(group.title)))
        )
