"""Composable filename parser for common music-video naming conventions."""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from mvo.confidence import ConfidenceEngine, ParseEvidence
from mvo.models import ParsedVideo
from mvo.tokenizer import FilenameTokenizer, TokenizedFilename

_FEATURE = re.compile(r"(?:^|\s+)(?:feat(?:uring)?\.?|ft\.?)\s+", re.IGNORECASE)
_YEAR = re.compile(r"^(?:19|20)\d{2}$")
_QUOTED_TITLE = re.compile(
    r"^(?P<artist>.+?)\s+['\u2018\u201c](?P<title>.+?)['\u2019\u201d]$"
)
_NOISE_SEGMENT = re.compile(
    r"^(?:directed by\b|please set to\b|official(?: music)? video$|music video$)",
    re.IGNORECASE,
)
_TECHNICAL = re.compile(
    r"^(?:"
    r"\d{3,4}p(?:\d+)?|[248]k|4k|8k|uhd|hd|fhd|sd|"
    r"x26[45]|h\.?26[45]|hevc|av1|vp9|divx|xvid|"
    r"aac|ac3|dts|flac|mp3|"
    r"web[- ]?dl|web[- ]?rip|blu[- ]?ray|bdrip|dvdrip|hdr|sdr|"
    r"official(?: music)? video|official audio|music video|video"
    r")$",
    re.IGNORECASE,
)
_COMPOUND_TECHNICAL = re.compile(
    r"(?:\d{3,4}p|\d+(?:\.\d+)?fps|x?h?26[45]|av1|hevc|aac|\d+kbit)",
    re.IGNORECASE,
)


@dataclass(frozen=True, slots=True)
class ParseCandidate:
    """Core artist/title fields returned by a parsing strategy."""

    artist: str | None
    title: str


class ParseStrategy(Protocol):
    """Interface for alternative filename layouts."""

    def matches(self, tokenized: TokenizedFilename) -> bool:
        """Return whether this strategy understands the token layout."""

    def parse(self, tokenized: TokenizedFilename) -> ParseCandidate:
        """Extract the core artist and title."""


class DelimitedStrategy:
    """Parse `Artist - Title` and equivalent explicitly delimited layouts."""

    def matches(self, tokenized: TokenizedFilename) -> bool:
        return tokenized.has_explicit_separator

    def parse(self, tokenized: TokenizedFilename) -> ParseCandidate:
        artist, *title_parts = tokenized.segments
        meaningful_parts = [
            part for part in title_parts if not _NOISE_SEGMENT.match(part)
        ]
        return ParseCandidate(artist=artist, title=" - ".join(meaningful_parts))


class QuotedTitleStrategy:
    """Parse `Artist 'Title'` layouts that omit an explicit separator."""

    def matches(self, tokenized: TokenizedFilename) -> bool:
        return len(tokenized.segments) == 1 and bool(
            _QUOTED_TITLE.fullmatch(tokenized.segments[0])
        )

    def parse(self, tokenized: TokenizedFilename) -> ParseCandidate:
        match = _QUOTED_TITLE.fullmatch(tokenized.segments[0])
        if match is None:
            raise ValueError("QuotedTitleStrategy used for an incompatible filename")
        return ParseCandidate(artist=match["artist"], title=match["title"])


class TitleOnlyStrategy:
    """Conservatively treat an undelimited filename as a title."""

    def matches(self, tokenized: TokenizedFilename) -> bool:
        return bool(tokenized.segments)

    def parse(self, tokenized: TokenizedFilename) -> ParseCandidate:
        title = tokenized.segments[0] if tokenized.segments else tokenized.stem
        return ParseCandidate(artist=None, title=title)


class FilenameParser:
    """Coordinate tokenization, layout parsing, metadata extraction, and scoring."""

    def __init__(
        self,
        tokenizer: FilenameTokenizer | None = None,
        confidence: ConfidenceEngine | None = None,
        strategies: tuple[ParseStrategy, ...] | None = None,
    ) -> None:
        self._tokenizer = tokenizer or FilenameTokenizer()
        self._confidence = confidence or ConfidenceEngine()
        self._strategies = strategies or (
            DelimitedStrategy(),
            QuotedTitleStrategy(),
            TitleOnlyStrategy(),
        )

    def parse(
        self, filename: str | Path, *, artist_hint: str | None = None
    ) -> ParsedVideo:
        """Infer metadata from a filename without reading or modifying the file."""

        tokenized = self._tokenizer.tokenize(filename)
        candidate = self._parse_core(tokenized)
        candidate = self._apply_artist_hint(candidate, artist_hint)

        artist, artist_features = self._split_feature(candidate.artist)
        title, title_features = self._split_feature(candidate.title)
        artist = self._strip_wrapping_quotes(artist)
        title = self._strip_wrapping_quotes(title)
        qualifier_features: list[str] = []
        versions: list[str] = []
        year: int | None = None

        for qualifier in tokenized.qualifiers:
            qualifier_head, feature_names = self._split_feature(qualifier)
            if feature_names:
                qualifier_features.extend(feature_names)
                if qualifier_head:
                    self._classify_qualifier(qualifier_head, versions)
                continue
            if _YEAR.fullmatch(qualifier):
                year = int(qualifier)
            elif not self._is_technical(qualifier):
                versions.append(qualifier)

        featured_artists = self._unique(
            (*artist_features, *title_features, *qualifier_features)
        )
        versions_tuple = self._unique(versions)
        evidence = ParseEvidence(
            has_separator=tokenized.has_explicit_separator,
            has_artist=bool(artist),
            has_title=bool(title),
            has_feature=bool(featured_artists),
            has_version=bool(versions_tuple),
        )
        return ParsedVideo(
            source_name=tokenized.source_name,
            artist=artist,
            title=title or tokenized.stem,
            featured_artists=featured_artists,
            versions=versions_tuple,
            year=year,
            confidence=self._confidence.score(evidence),
        )

    def _parse_core(self, tokenized: TokenizedFilename) -> ParseCandidate:
        for strategy in self._strategies:
            if strategy.matches(tokenized):
                return strategy.parse(tokenized)
        return ParseCandidate(artist=None, title=tokenized.stem)

    @staticmethod
    def _apply_artist_hint(
        candidate: ParseCandidate, artist_hint: str | None
    ) -> ParseCandidate:
        if candidate.artist or not artist_hint:
            return candidate
        hint = artist_hint.strip()
        title = candidate.title
        prefix = f"{hint} "
        if title.casefold().startswith(prefix.casefold()):
            title = title[len(prefix) :].strip()
        return ParseCandidate(artist=hint, title=title)

    @staticmethod
    def _split_feature(value: str | None) -> tuple[str | None, tuple[str, ...]]:
        if not value:
            return value, ()
        pieces = _FEATURE.split(value, maxsplit=1)
        if len(pieces) == 1:
            return value.strip(), ()
        primary, guests = pieces
        featured = tuple(
            name.strip()
            for name in re.split(r"\s*(?:,|&|\band\b)\s*", guests, flags=re.I)
            if name.strip()
        )
        return primary.strip() or None, featured

    @staticmethod
    def _unique(values: list[str] | tuple[str, ...]) -> tuple[str, ...]:
        seen: set[str] = set()
        result: list[str] = []
        for value in values:
            key = value.casefold()
            if key not in seen:
                seen.add(key)
                result.append(value)
        return tuple(result)

    @staticmethod
    def _classify_qualifier(qualifier: str, versions: list[str]) -> None:
        if qualifier and not FilenameParser._is_technical(qualifier):
            versions.append(qualifier)

    @staticmethod
    def _is_technical(qualifier: str) -> bool:
        normalized = re.sub(r"[_-]+", " ", qualifier).strip()
        if _TECHNICAL.fullmatch(normalized):
            return True
        return len(_COMPOUND_TECHNICAL.findall(normalized)) >= 2

    @staticmethod
    def _strip_wrapping_quotes(value: str | None) -> str | None:
        if value is None:
            return None
        return value.strip().strip("'\"\u2018\u2019\u201c\u201d")
