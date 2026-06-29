from pathlib import Path

import pytest

from mvo.analyzer import LibraryAnalyzer
from mvo.models import ConfidenceLevel
from mvo.overrides import MetadataOverride, MetadataOverrideStore


def test_override_store_round_trips_and_applies_reviewed_metadata(
    tmp_path: Path,
) -> None:
    media = tmp_path / "Mystery.mp4"
    media.write_bytes(b"video")
    analysis = LibraryAnalyzer().analyze(tmp_path)
    store = MetadataOverrideStore(tmp_path / "reviews.json")
    override = MetadataOverride(
        artist="The Artist",
        title="The Song",
        featured_artists=("A Guest",),
        versions=("Live",),
        year=2024,
    )

    store.save({"Mystery.mp4": override})
    updated = store.apply(analysis)

    assert store.load() == {"Mystery.mp4": override}
    assert updated.videos[0].parsed.artist == "The Artist"
    assert updated.videos[0].parsed.title == "The Song"
    assert updated.videos[0].parsed.confidence.level is ConfidenceLevel.HIGH
    assert media.read_bytes() == b"video"


def test_override_store_rejects_paths_outside_library(tmp_path: Path) -> None:
    store = MetadataOverrideStore(tmp_path / "reviews.json")

    with pytest.raises(ValueError, match="inside the library"):
        store.save({"../outside.mp4": MetadataOverride("Artist", "Song")})


def test_override_requires_artist_and_title() -> None:
    with pytest.raises(ValueError, match="artist"):
        MetadataOverride.from_dict({"artist": "", "title": "Song"})
