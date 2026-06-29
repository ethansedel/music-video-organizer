"""Local Chromaprint extraction and rate-limited AcoustID lookup client."""

from __future__ import annotations

import json
import shutil
import subprocess
import time
from collections.abc import Callable, Mapping
from pathlib import Path
from typing import Any
from urllib.error import HTTPError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from mvo.models import AcousticFingerprint, AcoustIDCandidate, AcoustIDRecording

_ENDPOINT = "https://api.acoustid.org/v2/lookup"
_USER_AGENT = (
    "MusicVideoOrganizer/0.7.0 (https://github.com/ethansedel/music-video-organizer)"
)

CommandRunner = Callable[[list[str], float], subprocess.CompletedProcess[str]]
Transport = Callable[[str, bytes, Mapping[str, str], float], Mapping[str, Any]]


class FingerprintError(RuntimeError):
    """A recoverable local fingerprint generation failure."""


class AcoustIDError(RuntimeError):
    """A recoverable AcoustID request or response failure."""


class FingerprintExtractor:
    """Invoke the official fpcalc utility without shell interpretation."""

    def __init__(
        self,
        executable: str | Path | None = None,
        runner: CommandRunner | None = None,
        *,
        timeout: float = 180.0,
        fingerprint_seconds: int = 120,
    ) -> None:
        self._executable = str(executable) if executable else shutil.which("fpcalc")
        self._runner = runner or self._run
        self._timeout = timeout
        self._fingerprint_seconds = fingerprint_seconds

    @property
    def available(self) -> bool:
        """Return whether an fpcalc executable was discovered or supplied."""

        return bool(self._executable)

    def fingerprint(self, path: str | Path) -> AcousticFingerprint:
        """Generate a compact fingerprint while leaving media untouched."""

        if not self._executable:
            raise FingerprintError(
                "fpcalc was not found; install Chromaprint and try again"
            )
        command = [
            self._executable,
            "-json",
            "-length",
            str(self._fingerprint_seconds),
            "--",
            str(Path(path)),
        ]
        try:
            completed = self._runner(command, self._timeout)
        except (OSError, subprocess.TimeoutExpired) as error:
            raise FingerprintError(str(error)) from error
        if completed.returncode != 0:
            detail = completed.stderr.strip() or "fpcalc failed"
            raise FingerprintError(detail)
        try:
            payload = json.loads(completed.stdout)
            duration = round(float(payload["duration"]))
            fingerprint = str(payload["fingerprint"])
        except (ValueError, TypeError, KeyError, json.JSONDecodeError) as error:
            raise FingerprintError("fpcalc returned malformed JSON") from error
        if duration <= 0 or not fingerprint:
            raise FingerprintError("fpcalc returned an empty fingerprint")
        return AcousticFingerprint(duration=duration, value=fingerprint)

    @staticmethod
    def _run(command: list[str], timeout: float) -> subprocess.CompletedProcess[str]:
        return subprocess.run(  # noqa: S603
            command,
            capture_output=True,
            check=False,
            text=True,
            timeout=timeout,
        )


class AcoustIDClient:
    """Look up fingerprints via POST with caching and conservative pacing."""

    def __init__(
        self,
        api_key: str,
        transport: Transport | None = None,
        *,
        clock: Callable[[], float] = time.monotonic,
        sleep: Callable[[float], None] = time.sleep,
        minimum_interval: float = 1 / 3,
        timeout: float = 20.0,
    ) -> None:
        if not api_key.strip():
            raise ValueError("AcoustID API key is required")
        self._api_key = api_key.strip()
        self._transport = transport or self._request_json
        self._clock = clock
        self._sleep = sleep
        self._minimum_interval = minimum_interval
        self._timeout = timeout
        self._last_request_at: float | None = None
        self._cache: dict[tuple[int, str], tuple[AcoustIDCandidate, ...]] = {}
        self.request_count = 0

    def lookup(self, fingerprint: AcousticFingerprint) -> tuple[AcoustIDCandidate, ...]:
        """Look up a compact fingerprint and linked MusicBrainz recordings."""

        cache_key = (fingerprint.duration, fingerprint.value)
        if cache_key in self._cache:
            return self._cache[cache_key]
        self._wait_for_rate_limit()
        body = urlencode(
            {
                "client": self._api_key,
                "duration": fingerprint.duration,
                "fingerprint": fingerprint.value,
                "meta": "recordings releasegroups compress",
                "format": "json",
            }
        ).encode()
        try:
            payload = self._transport(
                _ENDPOINT,
                body,
                {
                    "User-Agent": _USER_AGENT,
                    "Content-Type": "application/x-www-form-urlencoded",
                    "Accept": "application/json",
                },
                self._timeout,
            )
            candidates = self._parse_candidates(payload)
        except (OSError, ValueError, TypeError, KeyError) as error:
            raise AcoustIDError(str(error)) from error
        finally:
            self._last_request_at = self._clock()
            self.request_count += 1
        self._cache[cache_key] = candidates
        return candidates

    def _wait_for_rate_limit(self) -> None:
        if self._last_request_at is None:
            return
        remaining = self._minimum_interval - (self._clock() - self._last_request_at)
        if remaining > 0:
            self._sleep(remaining)

    @staticmethod
    def _parse_candidates(
        payload: Mapping[str, Any],
    ) -> tuple[AcoustIDCandidate, ...]:
        if payload.get("status") != "ok":
            error = payload.get("error", {})
            raise ValueError(error.get("message", "AcoustID lookup failed"))
        candidates: list[AcoustIDCandidate] = []
        for result in payload.get("results", []):
            recordings: list[AcoustIDRecording] = []
            for recording in result.get("recordings", []):
                artists = tuple(
                    str(artist["name"])
                    for artist in recording.get("artists", [])
                    if artist.get("name")
                )
                recordings.append(
                    AcoustIDRecording(
                        recording_id=str(recording["id"]),
                        title=recording.get("title"),
                        artists=artists,
                    )
                )
            candidates.append(
                AcoustIDCandidate(
                    acoustid_id=str(result["id"]),
                    score=float(result.get("score", 0)),
                    recordings=tuple(recordings),
                )
            )
        return tuple(candidates)

    @staticmethod
    def _request_json(
        url: str, body: bytes, headers: Mapping[str, str], timeout: float
    ) -> Mapping[str, Any]:
        request = Request(url, data=body, headers=dict(headers), method="POST")
        try:
            with urlopen(request, timeout=timeout) as response:  # noqa: S310
                return json.load(response)
        except HTTPError as error:
            message = AcoustIDClient._http_error_message(error)
            raise OSError(f"HTTP {error.code}: {message}") from error

    @staticmethod
    def _http_error_message(error: HTTPError) -> str:
        try:
            payload = json.load(error)
            return str(payload.get("error", {}).get("message") or error.reason)
        except (ValueError, TypeError, AttributeError):
            return str(error.reason)
