"""Bounded orchestration of local fingerprints and opt-in AcoustID lookups."""

from __future__ import annotations

from mvo.acoustid import (
    AcoustIDClient,
    AcoustIDError,
    FingerprintError,
    FingerprintExtractor,
)
from mvo.models import (
    AnalysisResult,
    FingerprintedVideo,
    FingerprintResult,
    MatchStatus,
)


class AcousticIdentifier:
    """Fingerprint and identify a bounded number of videos without writing media."""

    def __init__(self, extractor: FingerprintExtractor, client: AcoustIDClient) -> None:
        self._extractor = extractor
        self._client = client

    def identify(
        self, analysis: AnalysisResult, *, max_files: int = 5
    ) -> FingerprintResult:
        """Process at most max_files and report all remaining items as skipped."""

        if max_files < 0:
            raise ValueError("max_files cannot be negative")
        items: list[FingerprintedVideo] = []
        fingerprint_count = 0
        for index, video in enumerate(analysis.videos):
            if index >= max_files:
                items.append(
                    FingerprintedVideo(
                        video, MatchStatus.SKIPPED, (), None, "file limit reached"
                    )
                )
                continue
            try:
                fingerprint = self._extractor.fingerprint(video.source.path)
                fingerprint_count += 1
            except FingerprintError as error:
                items.append(
                    FingerprintedVideo(
                        video,
                        MatchStatus.ERROR,
                        (),
                        None,
                        f"fingerprint failed: {error}",
                    )
                )
                continue
            try:
                candidates = self._client.lookup(fingerprint)
            except AcoustIDError as error:
                items.append(
                    FingerprintedVideo(
                        video,
                        MatchStatus.ERROR,
                        (),
                        fingerprint.duration,
                        f"lookup failed: {error}",
                    )
                )
                continue
            if not candidates:
                status = MatchStatus.NOT_FOUND
                message = "no acoustic match found"
            elif candidates[0].score >= 0.9 and candidates[0].recordings:
                status = MatchStatus.MATCHED
                message = "strong acoustic match"
            else:
                status = MatchStatus.REVIEW
                message = "acoustic candidate requires review"
            items.append(
                FingerprintedVideo(
                    video, status, candidates, fingerprint.duration, message
                )
            )
        return FingerprintResult(
            analysis.root,
            tuple(items),
            fingerprint_count,
            self._client.request_count,
        )
