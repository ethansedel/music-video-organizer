"""Turn a filename into normalized parser input and bracketed qualifiers."""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

_BRACKETED = re.compile(
    r"\((?P<parentheses>[^()]*)\)|"
    r"\[(?P<brackets>[^\[\]]*)\]|"
    r"\{(?P<braces>[^{}]*)\}"
)
_CONTENT_ALIAS = re.compile(r"[\u3040-\u30ff\u3400-\u9fff]")
_SEPARATOR = re.compile(r"\s*(?:--+|;|\|)\s*|\s+(?:-|\u2013|\u2014)\s+")
_LEADING_TRACK = re.compile(r"^\s*\d{1,3}\s*[._-]+\s*")
_WHITESPACE = re.compile(r"\s+")


@dataclass(frozen=True, slots=True)
class TokenizedFilename:
    """Normalized filename components consumed by parsing strategies."""

    source_name: str
    stem: str
    segments: tuple[str, ...]
    qualifiers: tuple[str, ...]
    has_explicit_separator: bool


class FilenameTokenizer:
    """Normalize common filename punctuation without interpreting metadata."""

    def tokenize(self, filename: str | Path) -> TokenizedFilename:
        """Tokenize a basename or path while preserving display capitalization."""

        source_name = Path(filename).name
        stem = Path(source_name).stem
        qualifiers: list[str] = []

        def extract_qualifier(match: re.Match[str]) -> str:
            content = self._clean(next(group for group in match.groups() if group))
            if _CONTENT_ALIAS.search(content):
                return f" ({content}) "
            qualifiers.append(content)
            return " "

        core = _BRACKETED.sub(extract_qualifier, stem)
        core = _LEADING_TRACK.sub("", core)
        core = core.replace("_", " ").replace(".", " ")
        core = self._clean(core)

        segments = tuple(
            segment for part in _SEPARATOR.split(core) if (segment := self._clean(part))
        )
        return TokenizedFilename(
            source_name=source_name,
            stem=stem,
            segments=segments,
            qualifiers=tuple(item for item in qualifiers if item),
            has_explicit_separator=len(segments) > 1,
        )

    @staticmethod
    def _clean(value: str) -> str:
        return _WHITESPACE.sub(" ", value).strip(" -_.,")
