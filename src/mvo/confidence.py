"""Confidence policy for parsed music-video filenames."""

from __future__ import annotations

from dataclasses import dataclass

from mvo.models import Confidence, ConfidenceLevel


@dataclass(frozen=True, slots=True)
class ParseEvidence:
    """Parser observations used to produce a confidence score."""

    has_separator: bool
    has_artist: bool
    has_title: bool
    has_feature: bool = False
    has_version: bool = False


class ConfidenceEngine:
    """Score parser evidence using an explicit, independently testable policy."""

    def score(self, evidence: ParseEvidence) -> Confidence:
        """Return a bounded score, band, and readable explanation."""

        score = 0.0
        reasons: list[str] = []
        if evidence.has_separator:
            score += 0.45
            reasons.append("explicit artist/title separator")
        if evidence.has_artist:
            score += 0.2
            reasons.append("artist candidate found")
        if evidence.has_title:
            score += 0.25
            reasons.append("title candidate found")
        if evidence.has_feature:
            score += 0.05
            reasons.append("featured artist recognized")
        if evidence.has_version:
            score += 0.05
            reasons.append("version qualifier recognized")

        score = round(min(score, 1.0), 2)
        if score >= 0.8:
            level = ConfidenceLevel.HIGH
        elif score >= 0.55:
            level = ConfidenceLevel.MEDIUM
        else:
            level = ConfidenceLevel.LOW
        return Confidence(score=score, level=level, reasons=tuple(reasons))
