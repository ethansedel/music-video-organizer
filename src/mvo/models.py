"""Immutable domain models shared by the MVO pipeline."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path


class ConfidenceLevel(StrEnum):
    """Human-readable confidence bands."""

    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class PlanStatus(StrEnum):
    """Safety disposition for a proposed organization action."""

    READY = "ready"
    REVIEW = "review"
    CONFLICT = "conflict"


class DuplicateKind(StrEnum):
    """Strength of evidence connecting files in a duplicate group."""

    EXACT = "exact"
    METADATA = "metadata match"


@dataclass(frozen=True, slots=True)
class Confidence:
    """A bounded confidence score and the evidence behind it."""

    score: float
    level: ConfidenceLevel
    reasons: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class ParsedVideo:
    """Metadata inferred from one filename."""

    source_name: str
    artist: str | None
    title: str
    featured_artists: tuple[str, ...]
    versions: tuple[str, ...]
    year: int | None
    confidence: Confidence


@dataclass(frozen=True, slots=True)
class VideoFile:
    """Read-only facts about a video discovered during scanning."""

    path: Path
    relative_path: Path
    size_bytes: int
    extension: str


@dataclass(frozen=True, slots=True)
class ScanIssue:
    """A recoverable filesystem error encountered by the scanner."""

    path: Path
    message: str


@dataclass(frozen=True, slots=True)
class ScanResult:
    """Files and non-fatal issues produced by a library scan."""

    root: Path
    files: tuple[VideoFile, ...]
    issues: tuple[ScanIssue, ...]


@dataclass(frozen=True, slots=True)
class AnalyzedVideo:
    """A discovered file paired with parsed filename metadata."""

    source: VideoFile
    parsed: ParsedVideo


@dataclass(frozen=True, slots=True)
class AnalysisResult:
    """Complete, report-ready analysis of a library."""

    root: Path
    videos: tuple[AnalyzedVideo, ...]
    issues: tuple[ScanIssue, ...]


@dataclass(frozen=True, slots=True)
class PlannedVideo:
    """One read-only proposed destination for an analyzed video."""

    video: AnalyzedVideo
    destination: Path
    status: PlanStatus
    notes: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class OrganizationPlan:
    """A complete dry-run plan that cannot modify media."""

    root: Path
    items: tuple[PlannedVideo, ...]
    issues: tuple[ScanIssue, ...]


@dataclass(frozen=True, slots=True)
class DuplicateGroup:
    """Two or more files connected by exact or metadata evidence."""

    kind: DuplicateKind
    signature: str
    videos: tuple[AnalyzedVideo, ...]

    @property
    def recoverable_bytes(self) -> int:
        """Potential savings for exact duplicates; zero for metadata matches."""

        if self.kind is not DuplicateKind.EXACT:
            return 0
        return sum(video.source.size_bytes for video in self.videos[1:])


@dataclass(frozen=True, slots=True)
class DuplicateResult:
    """Read-only duplicate findings plus recoverable scan/hash issues."""

    root: Path
    groups: tuple[DuplicateGroup, ...]
    issues: tuple[ScanIssue, ...]
