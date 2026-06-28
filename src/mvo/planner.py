"""Read-only destination planning for music-video libraries."""

from __future__ import annotations

import re
import unicodedata
from collections import defaultdict
from dataclasses import replace
from pathlib import Path

from mvo.models import (
    AnalysisResult,
    AnalyzedVideo,
    ConfidenceLevel,
    OrganizationPlan,
    PlannedVideo,
    PlanStatus,
)

_UNSAFE = re.compile(r'[<>:"/\\|?*\x00-\x1f]')
_WHITESPACE = re.compile(r"\s+")
_RESERVED = {
    "CON",
    "PRN",
    "AUX",
    "NUL",
    *(f"COM{number}" for number in range(1, 10)),
    *(f"LPT{number}" for number in range(1, 10)),
}
_MAX_COMPONENT_LENGTH = 180


class FolderPlanner:
    """Build safe relative destinations without touching the filesystem."""

    def plan(self, analysis: AnalysisResult) -> OrganizationPlan:
        """Create and collision-check a deterministic dry-run plan."""

        drafts = [self._plan_video(video) for video in analysis.videos]
        destinations: dict[str, list[int]] = defaultdict(list)
        for index, item in enumerate(drafts):
            destinations[self._path_key(item.destination)].append(index)

        for indexes in destinations.values():
            if len(indexes) < 2:
                continue
            for index in indexes:
                item = drafts[index]
                drafts[index] = replace(
                    item,
                    status=PlanStatus.CONFLICT,
                    notes=(*item.notes, "multiple files share this destination"),
                )

        return OrganizationPlan(
            root=analysis.root,
            items=tuple(drafts),
            issues=analysis.issues,
        )

    def _plan_video(self, video: AnalyzedVideo) -> PlannedVideo:
        parsed = video.parsed
        notes: list[str] = []
        if not parsed.artist:
            notes.append("artist could not be determined")
        if parsed.confidence.level is ConfidenceLevel.LOW:
            notes.append("parser confidence is low")

        if notes:
            destination = Path(
                "_Needs Review", self._safe_filename(video.source.path.name)
            )
            status = PlanStatus.REVIEW
        else:
            artist_folder = self._safe_component(parsed.artist or "Unknown Artist")
            display_artist = parsed.artist or "Unknown Artist"
            if parsed.featured_artists:
                display_artist += " feat. " + " & ".join(parsed.featured_artists)
            filename = f"{display_artist} - {parsed.title}"
            if parsed.versions:
                filename += " [" + ", ".join(parsed.versions) + "]"
            if parsed.year:
                filename += f" ({parsed.year})"
            filename = self._safe_component(filename) + video.source.extension
            destination = Path(artist_folder, filename)
            status = PlanStatus.READY
            if destination == video.source.relative_path:
                notes.append("already organized")

        return PlannedVideo(
            video=video,
            destination=destination,
            status=status,
            notes=tuple(notes),
        )

    @classmethod
    def _safe_filename(cls, filename: str) -> str:
        path = Path(filename)
        return cls._safe_component(path.stem) + path.suffix.casefold()

    @staticmethod
    def _path_key(path: Path) -> str:
        return unicodedata.normalize("NFC", path.as_posix()).casefold()

    @staticmethod
    def _safe_component(value: str) -> str:
        component = unicodedata.normalize("NFC", value)
        component = _UNSAFE.sub("-", component)
        component = _WHITESPACE.sub(" ", component).strip(" .")
        if not component:
            component = "Unknown"
        if component.upper() in _RESERVED:
            component = f"_{component}"
        if len(component) > _MAX_COMPONENT_LENGTH:
            component = component[:_MAX_COMPONENT_LENGTH].rstrip(" .")
        return component
