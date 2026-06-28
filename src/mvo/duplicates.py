"""Layered, read-only duplicate detection."""

from __future__ import annotations

import hashlib
import re
import unicodedata
from collections import defaultdict
from collections.abc import Callable
from pathlib import Path

from mvo.models import (
    AnalysisResult,
    AnalyzedVideo,
    ConfidenceLevel,
    DuplicateGroup,
    DuplicateKind,
    DuplicateResult,
    ScanIssue,
)

_KEY_SEPARATOR = "\x1f"
_KEY_WHITESPACE = re.compile(r"\s+")
_HASH_CHUNK_SIZE = 1024 * 1024

FileHasher = Callable[[Path], str]


class DuplicateDetector:
    """Find confirmed byte duplicates and cautious metadata matches."""

    def __init__(self, hasher: FileHasher | None = None) -> None:
        self._hasher = hasher or self._sha256

    def detect(self, analysis: AnalysisResult) -> DuplicateResult:
        """Detect duplicates without modifying files or reading unique sizes."""

        issues = list(analysis.issues)
        exact_groups = self._find_exact(analysis.videos, issues)
        exact_members = {
            frozenset(video.source.path for video in group.videos)
            for group in exact_groups
        }
        metadata_groups = self._find_metadata(analysis.videos, exact_members)
        groups = (*exact_groups, *metadata_groups)
        return DuplicateResult(
            root=analysis.root,
            groups=groups,
            issues=tuple(issues),
        )

    def _find_exact(
        self, videos: tuple[AnalyzedVideo, ...], issues: list[ScanIssue]
    ) -> tuple[DuplicateGroup, ...]:
        by_size: dict[int, list[AnalyzedVideo]] = defaultdict(list)
        for video in videos:
            by_size[video.source.size_bytes].append(video)

        groups: list[DuplicateGroup] = []
        for _size, candidates in sorted(by_size.items()):
            if len(candidates) < 2:
                continue
            by_digest: dict[str, list[AnalyzedVideo]] = defaultdict(list)
            for video in candidates:
                try:
                    digest = self._hasher(video.source.path)
                except OSError as error:
                    issues.append(
                        ScanIssue(video.source.path, f"Unable to hash file: {error}")
                    )
                    continue
                by_digest[digest].append(video)
            for digest, matches in sorted(by_digest.items()):
                if len(matches) > 1:
                    groups.append(
                        DuplicateGroup(
                            kind=DuplicateKind.EXACT,
                            signature=f"sha256:{digest}",
                            videos=self._sorted(matches),
                        )
                    )
        return tuple(groups)

    def _find_metadata(
        self,
        videos: tuple[AnalyzedVideo, ...],
        exact_members: set[frozenset[Path]],
    ) -> tuple[DuplicateGroup, ...]:
        by_metadata: dict[str, list[AnalyzedVideo]] = defaultdict(list)
        for video in videos:
            parsed = video.parsed
            if not parsed.artist or parsed.confidence.level is ConfidenceLevel.LOW:
                continue
            parts = (
                parsed.artist,
                parsed.title,
                *parsed.featured_artists,
                *parsed.versions,
            )
            key = _KEY_SEPARATOR.join(self._normalize(part) for part in parts)
            by_metadata[key].append(video)

        groups: list[DuplicateGroup] = []
        for _key, matches in sorted(by_metadata.items()):
            if len(matches) < 2:
                continue
            member_paths = frozenset(video.source.path for video in matches)
            if member_paths in exact_members:
                continue
            parsed = matches[0].parsed
            label = f"{parsed.artist} — {parsed.title}"
            groups.append(
                DuplicateGroup(
                    kind=DuplicateKind.METADATA,
                    signature=label,
                    videos=self._sorted(matches),
                )
            )
        return tuple(groups)

    @staticmethod
    def _normalize(value: str) -> str:
        normalized = unicodedata.normalize("NFKC", value).casefold()
        return _KEY_WHITESPACE.sub(" ", normalized).strip()

    @staticmethod
    def _sorted(videos: list[AnalyzedVideo]) -> tuple[AnalyzedVideo, ...]:
        return tuple(
            sorted(
                videos,
                key=lambda video: video.source.relative_path.as_posix().casefold(),
            )
        )

    @staticmethod
    def _sha256(path: Path) -> str:
        digest = hashlib.sha256()
        with path.open("rb") as source:
            while chunk := source.read(_HASH_CHUNK_SIZE):
                digest.update(chunk)
        return digest.hexdigest()
