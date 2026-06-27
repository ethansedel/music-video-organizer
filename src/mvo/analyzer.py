"""Application service that composes scanning and filename parsing."""

from __future__ import annotations

from pathlib import Path

from mvo.models import AnalysisResult, AnalyzedVideo
from mvo.parser import FilenameParser
from mvo.scanner import LibraryScanner


class LibraryAnalyzer:
    """Analyze a library through injected scanner and parser components."""

    def __init__(
        self,
        scanner: LibraryScanner | None = None,
        parser: FilenameParser | None = None,
    ) -> None:
        self._scanner = scanner or LibraryScanner()
        self._parser = parser or FilenameParser()

    def analyze(self, root: str | Path) -> AnalysisResult:
        """Scan and parse a library without modifying any media."""

        scan = self._scanner.scan(root)
        videos = tuple(
            AnalyzedVideo(
                source=video,
                parsed=self._parser.parse(
                    video.path.name,
                    artist_hint=(
                        video.relative_path.parent.name
                        if video.relative_path.parent != Path(".")
                        else None
                    ),
                ),
            )
            for video in scan.files
        )
        return AnalysisResult(root=scan.root, videos=videos, issues=scan.issues)
