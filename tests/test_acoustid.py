import subprocess
from collections.abc import Mapping
from io import BytesIO
from pathlib import Path
from typing import Any
from urllib.error import HTTPError
from urllib.parse import parse_qs

import pytest

from mvo.acoustid import (
    AcoustIDClient,
    AcoustIDError,
    FingerprintError,
    FingerprintExtractor,
)
from mvo.models import AcousticFingerprint


def _payload() -> dict[str, Any]:
    return {
        "status": "ok",
        "results": [
            {
                "id": "acoustid-track",
                "score": 0.98,
                "recordings": [
                    {
                        "id": "musicbrainz-recording",
                        "title": "Song",
                        "artists": [{"name": "Artist"}],
                    }
                ],
            }
        ],
    }


def test_fpcalc_runs_without_shell_and_parses_json(tmp_path: Path) -> None:
    media = tmp_path / "odd; name.mp4"
    media.touch()
    calls: list[tuple[list[str], float]] = []

    def runner(command: list[str], timeout: float):
        calls.append((command, timeout))
        return subprocess.CompletedProcess(
            command, 0, '{"duration": 123.4, "fingerprint": "abc"}', ""
        )

    result = FingerprintExtractor("/usr/bin/fpcalc", runner).fingerprint(media)

    assert result == AcousticFingerprint(duration=123, value="abc")
    assert calls[0][0] == [
        "/usr/bin/fpcalc",
        "-json",
        "-length",
        "120",
        "--",
        str(media),
    ]


def test_fpcalc_missing_binary_is_clear(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("mvo.acoustid.shutil.which", lambda _name: None)
    extractor = FingerprintExtractor()

    with pytest.raises(FingerprintError, match="fpcalc was not found"):
        extractor.fingerprint("video.mp4")


def test_fpcalc_failure_and_malformed_output_are_recoverable() -> None:
    failed = FingerprintExtractor(
        "fpcalc",
        lambda command, _timeout: subprocess.CompletedProcess(
            command, 2, "", "decoder failed"
        ),
    )
    malformed = FingerprintExtractor(
        "fpcalc",
        lambda command, _timeout: subprocess.CompletedProcess(command, 0, "{}", ""),
    )

    with pytest.raises(FingerprintError, match="decoder failed"):
        failed.fingerprint("video.mp4")
    with pytest.raises(FingerprintError, match="malformed JSON"):
        malformed.fingerprint("video.mp4")


def test_lookup_posts_fingerprint_and_parses_recording() -> None:
    calls: list[tuple[str, bytes, Mapping[str, str], float]] = []

    def transport(url: str, body: bytes, headers: Mapping[str, str], timeout: float):
        calls.append((url, body, headers, timeout))
        return _payload()

    client = AcoustIDClient("secret-key", transport=transport)
    candidates = client.lookup(AcousticFingerprint(123, "fingerprint-data"))

    body = parse_qs(calls[0][1].decode())
    assert calls[0][0] == "https://api.acoustid.org/v2/lookup"
    assert "secret-key" not in calls[0][0]
    assert body["client"] == ["secret-key"]
    assert body["duration"] == ["123"]
    assert body["fingerprint"] == ["fingerprint-data"]
    assert calls[0][2]["Content-Type"] == "application/x-www-form-urlencoded"
    assert candidates[0].score == 0.98
    assert candidates[0].recordings[0].artists == ("Artist",)


def test_lookup_caches_and_stays_below_three_requests_per_second() -> None:
    now = [0.0]
    sleeps: list[float] = []

    def sleep(seconds: float) -> None:
        sleeps.append(seconds)
        now[0] += seconds

    client = AcoustIDClient(
        "key",
        transport=lambda *_args: _payload(),
        clock=lambda: now[0],
        sleep=sleep,
    )
    first = AcousticFingerprint(1, "one")

    client.lookup(first)
    client.lookup(first)
    client.lookup(AcousticFingerprint(2, "two"))

    assert client.request_count == 2
    assert sleeps == [pytest.approx(1 / 3)]


def test_lookup_api_error_is_recoverable() -> None:
    client = AcoustIDClient(
        "key",
        transport=lambda *_args: {
            "status": "error",
            "error": {"message": "invalid client"},
        },
    )

    with pytest.raises(AcoustIDError, match="invalid client"):
        client.lookup(AcousticFingerprint(1, "value"))


def test_api_key_is_required() -> None:
    with pytest.raises(ValueError, match="API key"):
        AcoustIDClient(" ")


def test_http_error_surfaces_acoustid_json_message(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    error = HTTPError(
        "https://api.acoustid.org/v2/lookup",
        400,
        "Bad Request",
        {},
        BytesIO(b'{"error":{"message":"invalid client key"}}'),
    )

    def fail(*_args, **_kwargs):
        raise error

    monkeypatch.setattr("mvo.acoustid.urlopen", fail)

    with pytest.raises(OSError, match="HTTP 400: invalid client key"):
        AcoustIDClient._request_json(
            "https://api.acoustid.org/v2/lookup", b"body", {}, 1
        )
