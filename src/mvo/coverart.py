"""Read-only client for Cover Art Archive release-group metadata."""

from __future__ import annotations

import json
from collections.abc import Callable, Mapping
from typing import Any
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from mvo.models import ArtworkImage

_ENDPOINT = "https://coverartarchive.org/release-group/{release_group_id}"
_USER_AGENT = (
    "MusicVideoOrganizer/0.8.0 (https://github.com/ethansedel/music-video-organizer)"
)

Transport = Callable[[str, Mapping[str, str], float], Mapping[str, Any] | None]


class CoverArtError(RuntimeError):
    """A recoverable Cover Art Archive request or response failure."""


class CoverArtClient:
    """Fetch and cache remote artwork metadata without downloading image bytes."""

    def __init__(
        self, transport: Transport | None = None, *, timeout: float = 15.0
    ) -> None:
        self._transport = transport or self._request_json
        self._timeout = timeout
        self._cache: dict[str, tuple[ArtworkImage, ...]] = {}
        self.request_count = 0

    def lookup_release_group(self, release_group_id: str) -> tuple[ArtworkImage, ...]:
        """Return remote image metadata; an archive 404 becomes an empty result."""

        if release_group_id in self._cache:
            return self._cache[release_group_id]
        url = _ENDPOINT.format(release_group_id=release_group_id)
        try:
            payload = self._transport(
                url,
                {"User-Agent": _USER_AGENT, "Accept": "application/json"},
                self._timeout,
            )
            images = self._parse_images(payload or {})
        except (OSError, ValueError, TypeError, KeyError) as error:
            raise CoverArtError(str(error)) from error
        finally:
            self.request_count += 1
        self._cache[release_group_id] = images
        return images

    @staticmethod
    def _parse_images(payload: Mapping[str, Any]) -> tuple[ArtworkImage, ...]:
        images = payload.get("images", [])
        if not isinstance(images, list):
            raise ValueError("Cover Art Archive response has no image list")
        result: list[ArtworkImage] = []
        for image in images:
            thumbnails = image.get("thumbnails", {})
            result.append(
                ArtworkImage(
                    image_url=CoverArtClient._https(str(image["image"])),
                    thumbnail_250=CoverArtClient._optional_url(thumbnails.get("250")),
                    thumbnail_500=CoverArtClient._optional_url(thumbnails.get("500")),
                    thumbnail_1200=CoverArtClient._optional_url(thumbnails.get("1200")),
                    types=tuple(str(value) for value in image.get("types", [])),
                    front=bool(image.get("front")),
                    back=bool(image.get("back")),
                    approved=bool(image.get("approved")),
                    comment=str(image.get("comment", "")),
                )
            )
        return tuple(
            sorted(result, key=lambda item: (not item.front, not item.approved))
        )

    @staticmethod
    def _optional_url(value: object) -> str | None:
        return CoverArtClient._https(str(value)) if value else None

    @staticmethod
    def _https(value: str) -> str:
        if value.startswith("http://"):
            return "https://" + value.removeprefix("http://")
        return value

    @staticmethod
    def _request_json(
        url: str, headers: Mapping[str, str], timeout: float
    ) -> Mapping[str, Any] | None:
        request = Request(url, headers=dict(headers))
        try:
            with urlopen(request, timeout=timeout) as response:  # noqa: S310
                return json.load(response)
        except HTTPError as error:
            if error.code == 404:
                return None
            raise OSError(f"HTTP {error.code}: {error.reason}") from error
