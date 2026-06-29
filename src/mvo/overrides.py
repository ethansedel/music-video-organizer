"""Persistent, user-reviewed metadata overrides."""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, replace
from pathlib import Path
from tempfile import NamedTemporaryFile

from mvo.models import (
    AnalysisResult,
    Confidence,
    ConfidenceLevel,
    ParsedVideo,
)


@dataclass(frozen=True, slots=True)
class MetadataOverride:
    """One complete, manually reviewed interpretation of a video filename."""

    artist: str
    title: str
    featured_artists: tuple[str, ...] = ()
    versions: tuple[str, ...] = ()
    year: int | None = None

    @classmethod
    def from_dict(cls, value: object) -> MetadataOverride:
        """Validate and construct an override from decoded JSON."""

        if not isinstance(value, dict):
            raise ValueError("override must be an object")
        artist = cls._required_text(value.get("artist"), "artist")
        title = cls._required_text(value.get("title"), "title")
        featured = cls._text_list(value.get("featured_artists", []), "featured_artists")
        versions = cls._text_list(value.get("versions", []), "versions")
        year_value = value.get("year")
        if year_value is None or year_value == "":
            year = None
        elif isinstance(year_value, int) and 1000 <= year_value <= 9999:
            year = year_value
        else:
            raise ValueError("year must be blank or a four-digit number")
        return cls(artist, title, featured, versions, year)

    def to_dict(self) -> dict[str, object]:
        """Return a stable JSON representation."""

        return {
            "artist": self.artist,
            "title": self.title,
            "featured_artists": list(self.featured_artists),
            "versions": list(self.versions),
            "year": self.year,
        }

    def apply(self, parsed: ParsedVideo) -> ParsedVideo:
        """Replace inferred fields while preserving the original source name."""

        return replace(
            parsed,
            artist=self.artist,
            title=self.title,
            featured_artists=self.featured_artists,
            versions=self.versions,
            year=self.year,
            confidence=Confidence(
                score=1.0,
                level=ConfidenceLevel.HIGH,
                reasons=("metadata manually reviewed",),
            ),
        )

    @staticmethod
    def _required_text(value: object, field: str) -> str:
        if not isinstance(value, str) or not value.strip():
            raise ValueError(f"{field} must not be blank")
        return value.strip()

    @staticmethod
    def _text_list(value: object, field: str) -> tuple[str, ...]:
        if not isinstance(value, list) or not all(
            isinstance(item, str) for item in value
        ):
            raise ValueError(f"{field} must be a list of text values")
        return tuple(item.strip() for item in value if item.strip())


class MetadataOverrideStore:
    """Load and atomically save overrides keyed by source-relative path."""

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path).expanduser().resolve()

    def load(self) -> dict[str, MetadataOverride]:
        """Load overrides, treating a missing file as an empty store."""

        if not self.path.exists():
            return {}
        try:
            payload = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as error:
            raise ValueError(f"could not read overrides file: {error}") from error
        if not isinstance(payload, dict) or payload.get("version") != 1:
            raise ValueError("overrides file has an unsupported format")
        raw_items = payload.get("overrides")
        if not isinstance(raw_items, dict):
            raise ValueError("overrides file must contain an overrides object")
        return {
            self._safe_key(key): MetadataOverride.from_dict(value)
            for key, value in raw_items.items()
        }

    def save(self, overrides: dict[str, MetadataOverride]) -> None:
        """Atomically replace the store without touching any media file."""

        self.path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "version": 1,
            "overrides": {
                self._safe_key(key): value.to_dict()
                for key, value in sorted(overrides.items())
            },
        }
        temporary: Path | None = None
        try:
            with NamedTemporaryFile(
                "w",
                encoding="utf-8",
                dir=self.path.parent,
                prefix=f".{self.path.name}.",
                suffix=".tmp",
                delete=False,
            ) as handle:
                json.dump(payload, handle, ensure_ascii=False, indent=2)
                handle.write("\n")
                handle.flush()
                os.fsync(handle.fileno())
                temporary = Path(handle.name)
            os.replace(temporary, self.path)
        finally:
            if temporary is not None:
                temporary.unlink(missing_ok=True)

    def apply(self, analysis: AnalysisResult) -> AnalysisResult:
        """Apply matching overrides to an immutable analysis result."""

        overrides = self.load()
        videos = tuple(
            replace(
                video,
                parsed=overrides[video.source.relative_path.as_posix()].apply(
                    video.parsed
                ),
            )
            if video.source.relative_path.as_posix() in overrides
            else video
            for video in analysis.videos
        )
        return replace(analysis, videos=videos)

    @staticmethod
    def _safe_key(value: object) -> str:
        if not isinstance(value, str) or not value or value.startswith("/"):
            raise ValueError("override paths must be non-empty relative paths")
        path = Path(value)
        if any(part in {"", ".", ".."} for part in path.parts):
            raise ValueError("override paths must stay inside the library")
        return path.as_posix()
