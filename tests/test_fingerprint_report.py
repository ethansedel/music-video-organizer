from pathlib import Path

from mvo.acoustid import AcoustIDClient
from mvo.analyzer import LibraryAnalyzer
from mvo.fingerprint_report import render_fingerprint_html, write_fingerprint_report
from mvo.fingerprinting import AcousticIdentifier
from mvo.models import AcousticFingerprint


class Extractor:
    def fingerprint(self, _path: Path) -> AcousticFingerprint:
        return AcousticFingerprint(120, "private-fingerprint-value")


def _result(tmp_path: Path):
    (tmp_path / "A&B.mp4").touch()
    payload = {
        "status": "ok",
        "results": [
            {
                "id": "track-id",
                "score": 0.99,
                "recordings": [
                    {
                        "id": "recording-id",
                        "title": "A & B",
                        "artists": [{"name": "<Artist>"}],
                    }
                ],
            }
        ],
    }
    client = AcoustIDClient("key", transport=lambda *_args: payload)
    return AcousticIdentifier(Extractor(), client).identify(
        LibraryAnalyzer().analyze(tmp_path)
    )


def test_report_is_escaped_read_only_and_hides_fingerprint(tmp_path: Path) -> None:
    html = render_fingerprint_html(_result(tmp_path))

    assert "<Artist>" not in html
    assert "&lt;Artist&gt;" in html
    assert "A&amp;B.mp4" in html
    assert "private-fingerprint-value" not in html
    assert "No fingerprints were submitted" in html


def test_writes_fingerprint_report(tmp_path: Path) -> None:
    output = tmp_path / "acoustid.html"

    written = write_fingerprint_report(_result(tmp_path), output)

    assert written == output.resolve()
    assert "Acoustic identification" in output.read_text(encoding="utf-8")
