from pathlib import Path

from mvo.review_media import ReviewMediaInspector


def test_filename_quality_recognizes_resolution_tags() -> None:
    lower = ReviewMediaInspector.filename_quality(Path("Song [720p].mp4"))
    higher = ReviewMediaInspector.filename_quality(Path("Song [1080p].mp4"))

    assert lower.height == 720
    assert higher.height == 1080
    assert higher.score > lower.score
