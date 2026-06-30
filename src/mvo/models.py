"""Immutable domain models shared by the Liner Notes pipeline."""

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


class PreflightStatus(StrEnum):
    """Execution-readiness disposition for one planned video."""

    READY = "ready"
    UNCHANGED = "unchanged"
    BLOCKED = "blocked"


class ExecutionStatus(StrEnum):
    """Final outcome of one explicitly confirmed organization action."""

    MOVED = "moved"
    UNCHANGED = "unchanged"
    SKIPPED = "skipped"
    FAILED = "failed"
    ROLLED_BACK = "rolled back"


class DuplicateKind(StrEnum):
    """Strength of evidence connecting files in a duplicate group."""

    EXACT = "exact"
    METADATA = "metadata match"


class MatchStatus(StrEnum):
    """Disposition of an optional MusicBrainz lookup."""

    MATCHED = "matched"
    REVIEW = "review"
    NOT_FOUND = "not found"
    SKIPPED = "skipped"
    ERROR = "error"


class ArtworkStatus(StrEnum):
    """Disposition of a read-only artwork preview lookup."""

    FOUND = "found"
    REVIEW = "review"
    NOT_FOUND = "not found"
    SKIPPED = "skipped"
    ERROR = "error"


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
    modified_ns: int = 0
    device: int = 0
    inode: int = 0


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
class PreflightItem:
    """One planned video plus its read-only safety validation."""

    planned: PlannedVideo
    status: PreflightStatus
    checks: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class PreflightResult:
    """Safety snapshot for a complete organization plan."""

    root: Path
    items: tuple[PreflightItem, ...]
    issues: tuple[ScanIssue, ...]

    @property
    def safe_to_execute(self) -> bool:
        """Whether this snapshot contains no known execution blockers."""

        return not self.issues and all(
            item.status is not PreflightStatus.BLOCKED for item in self.items
        )


@dataclass(frozen=True, slots=True)
class ExecutionItem:
    """One planned video and its final execution outcome."""

    planned: PlannedVideo
    status: ExecutionStatus
    message: str


@dataclass(frozen=True, slots=True)
class ExecutionResult:
    """Audit record for one explicitly confirmed execution run."""

    root: Path
    items: tuple[ExecutionItem, ...]
    rolled_back: bool
    rollback_complete: bool = True

    @property
    def moved_count(self) -> int:
        """Number of moves that remain applied after the run."""

        return sum(item.status is ExecutionStatus.MOVED for item in self.items)


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


@dataclass(frozen=True, slots=True)
class MusicBrainzCandidate:
    """Compact recording candidate returned by MusicBrainz."""

    recording_id: str
    title: str
    artist_credit: str
    score: int
    first_release_date: str | None
    release_titles: tuple[str, ...]
    video: bool | None
    release_groups: tuple[ReleaseGroupRef, ...] = ()


@dataclass(frozen=True, slots=True)
class ReleaseGroupRef:
    """MusicBrainz release group that can provide canonical cover art."""

    release_group_id: str
    title: str
    primary_type: str | None
    score: int = 0
    artist_credit: str = ""


@dataclass(frozen=True, slots=True)
class EnrichedVideo:
    """One analyzed video and its optional MusicBrainz candidates."""

    video: AnalyzedVideo
    status: MatchStatus
    candidates: tuple[MusicBrainzCandidate, ...]
    message: str


@dataclass(frozen=True, slots=True)
class EnrichmentResult:
    """Read-only MusicBrainz enrichment results."""

    root: Path
    items: tuple[EnrichedVideo, ...]
    query_count: int


@dataclass(frozen=True, slots=True)
class AcousticFingerprint:
    """Compact local Chromaprint result for one media file."""

    duration: int
    value: str


@dataclass(frozen=True, slots=True)
class AcoustIDRecording:
    """MusicBrainz recording metadata attached to an AcoustID result."""

    recording_id: str
    title: str | None
    artists: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class AcoustIDCandidate:
    """One AcoustID track candidate and its linked recordings."""

    acoustid_id: str
    score: float
    recordings: tuple[AcoustIDRecording, ...]


@dataclass(frozen=True, slots=True)
class FingerprintedVideo:
    """One video and the outcome of optional acoustic identification."""

    video: AnalyzedVideo
    status: MatchStatus
    candidates: tuple[AcoustIDCandidate, ...]
    duration: int | None
    message: str


@dataclass(frozen=True, slots=True)
class FingerprintResult:
    """Read-only acoustic identification results."""

    root: Path
    items: tuple[FingerprintedVideo, ...]
    fingerprint_count: int
    lookup_count: int


@dataclass(frozen=True, slots=True)
class ArtworkImage:
    """Remote Cover Art Archive image metadata; no image bytes are stored."""

    image_url: str
    thumbnail_250: str | None
    thumbnail_500: str | None
    thumbnail_1200: str | None
    types: tuple[str, ...]
    front: bool
    back: bool
    approved: bool
    comment: str


@dataclass(frozen=True, slots=True)
class ArtworkPreview:
    """One video and its remote artwork preview candidates."""

    video: AnalyzedVideo
    status: ArtworkStatus
    release_group: ReleaseGroupRef | None
    images: tuple[ArtworkImage, ...]
    message: str


@dataclass(frozen=True, slots=True)
class ArtworkResult:
    """Read-only artwork lookup results."""

    root: Path
    items: tuple[ArtworkPreview, ...]
    musicbrainz_queries: int
    cover_art_queries: int
