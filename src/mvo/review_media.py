"""Read-only media details and thumbnails for the local review editor."""

from __future__ import annotations

import json
import re
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path

_RESOLUTION = re.compile(r"(?<!\d)(?P<height>\d{3,4})p(?!\d)", re.IGNORECASE)


@dataclass(frozen=True, slots=True)
class MediaQuality:
    """Compact video quality facts used for duplicate recommendations."""

    width: int | None
    height: int | None
    bit_rate: int | None
    codec: str | None
    source: str

    @property
    def label(self) -> str:
        """Return a short human-readable quality summary."""

        pieces: list[str] = []
        if self.width and self.height:
            pieces.append(f"{self.width}×{self.height}")
        elif self.height:
            pieces.append(f"{self.height}p")
        if self.codec:
            pieces.append(self.codec.upper())
        if self.bit_rate:
            pieces.append(f"{self.bit_rate / 1_000_000:.1f} Mbps")
        return " · ".join(pieces) or "Quality unknown"

    @property
    def score(self) -> tuple[int, int, int]:
        """Sort by pixels, then bitrate, with probed facts preferred."""

        pixels = (
            (self.width or 0) * (self.height or 0)
            if self.width
            else (self.height or 0) ** 2
        )
        return pixels, self.bit_rate or 0, self.source == "ffprobe"


class ReviewMediaInspector:
    """Lazily inspect local videos without modifying them."""

    def __init__(self) -> None:
        self._quality_cache: dict[Path, MediaQuality] = {}
        self._thumbnail_cache: dict[Path, bytes | None] = {}

    def quality(self, path: Path) -> MediaQuality:
        """Return ffprobe facts, falling back to filename resolution tags."""

        if path not in self._quality_cache:
            self._quality_cache[path] = self._probe(path) or self.filename_quality(path)
        return self._quality_cache[path]

    @staticmethod
    def filename_quality(path: Path) -> MediaQuality:
        """Infer a conservative height from common filename tags."""

        match = _RESOLUTION.search(path.name)
        height = int(match["height"]) if match else None
        if height is None and re.search(r"(?<!\w)4k(?!\w)", path.name, re.I):
            height = 2160
        elif height is None and re.search(r"(?<!\w)8k(?!\w)", path.name, re.I):
            height = 4320
        return MediaQuality(None, height, None, None, "filename")

    def thumbnail(self, path: Path) -> bytes | None:
        """Generate and cache a small JPEG in memory using ffmpeg when available."""

        if path not in self._thumbnail_cache:
            self._thumbnail_cache[path] = self._make_thumbnail(path)
        return self._thumbnail_cache[path]

    @staticmethod
    def _probe(path: Path) -> MediaQuality | None:
        executable = shutil.which("ffprobe")
        if not executable:
            return None
        command = [
            executable,
            "-v",
            "error",
            "-select_streams",
            "v:0",
            "-show_entries",
            "stream=width,height,bit_rate,codec_name",
            "-show_entries",
            "format=bit_rate",
            "-of",
            "json",
            str(path),
        ]
        try:
            completed = subprocess.run(
                command,
                capture_output=True,
                check=True,
                timeout=20,
            )
            payload = json.loads(completed.stdout)
            stream = payload.get("streams", [{}])[0]
            format_info = payload.get("format", {})
            bit_rate = stream.get("bit_rate") or format_info.get("bit_rate")
            return MediaQuality(
                width=int(stream["width"]) if stream.get("width") else None,
                height=int(stream["height"]) if stream.get("height") else None,
                bit_rate=int(bit_rate) if bit_rate else None,
                codec=stream.get("codec_name"),
                source="ffprobe",
            )
        except (
            OSError,
            subprocess.SubprocessError,
            json.JSONDecodeError,
            TypeError,
            ValueError,
            IndexError,
        ):
            return None

    @staticmethod
    def _make_thumbnail(path: Path) -> bytes | None:
        executable = shutil.which("ffmpeg")
        if not executable:
            return None
        command = [
            executable,
            "-v",
            "error",
            "-ss",
            "0.1",
            "-i",
            str(path),
            "-frames:v",
            "1",
            "-vf",
            "scale=360:-2",
            "-f",
            "image2pipe",
            "-vcodec",
            "mjpeg",
            "pipe:1",
        ]
        try:
            completed = subprocess.run(
                command,
                capture_output=True,
                check=True,
                timeout=30,
            )
        except (OSError, subprocess.SubprocessError):
            return None
        return completed.stdout or None
