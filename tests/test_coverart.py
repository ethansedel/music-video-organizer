from collections.abc import Mapping
from io import BytesIO
from typing import Any
from urllib.error import HTTPError

from mvo.coverart import CoverArtClient


def _payload() -> dict[str, Any]:
    return {
        "images": [
            {
                "image": "http://coverartarchive.org/release/id/image.jpg",
                "thumbnails": {
                    "250": "http://coverartarchive.org/release/id/image-250.jpg",
                    "500": "https://coverartarchive.org/release/id/image-500.jpg",
                },
                "types": ["Front"],
                "front": True,
                "back": False,
                "approved": True,
                "comment": "",
            }
        ]
    }


def test_fetches_release_group_metadata_and_normalizes_https() -> None:
    calls: list[tuple[str, Mapping[str, str], float]] = []

    def transport(url: str, headers: Mapping[str, str], timeout: float):
        calls.append((url, headers, timeout))
        return _payload()

    client = CoverArtClient(transport=transport)
    images = client.lookup_release_group("release-group-id")

    assert calls[0][0].endswith("/release-group/release-group-id")
    assert calls[0][1]["Accept"] == "application/json"
    assert calls[0][1]["User-Agent"].startswith("LinerNotes/1.2.0")
    assert images[0].image_url.startswith("https://")
    assert images[0].thumbnail_250 == (
        "https://coverartarchive.org/release/id/image-250.jpg"
    )
    assert images[0].front is True


def test_caches_release_group_lookup() -> None:
    calls = 0

    def transport(*_args):
        nonlocal calls
        calls += 1
        return _payload()

    client = CoverArtClient(transport=transport)

    client.lookup_release_group("id")
    client.lookup_release_group("id")

    assert calls == 1
    assert client.request_count == 1


def test_archive_404_becomes_empty_result(monkeypatch: object) -> None:
    error = HTTPError("url", 404, "Not Found", {}, BytesIO(b""))

    def fail(*_args, **_kwargs):
        raise error

    monkeypatch.setattr("mvo.coverart.urlopen", fail)  # type: ignore[attr-defined]

    assert CoverArtClient._request_json("https://example.test", {}, 1) is None
