from pathlib import Path

from mvo.models import (
    AnalysisResult,
    AnalyzedVideo,
    Confidence,
    ConfidenceLevel,
    ParsedVideo,
    PlanStatus,
    VideoFile,
)
from mvo.planner import FolderPlanner


def _video(
    root: Path,
    relative_path: str,
    *,
    artist: str | None = "Artist",
    title: str = "Song",
    features: tuple[str, ...] = (),
    versions: tuple[str, ...] = (),
    year: int | None = None,
    level: ConfidenceLevel = ConfidenceLevel.HIGH,
) -> AnalyzedVideo:
    path = root / relative_path
    source = VideoFile(
        path=path,
        relative_path=Path(relative_path),
        size_bytes=10,
        extension=path.suffix.casefold(),
    )
    parsed = ParsedVideo(
        source_name=path.name,
        artist=artist,
        title=title,
        featured_artists=features,
        versions=versions,
        year=year,
        confidence=Confidence(
            0.9 if level is ConfidenceLevel.HIGH else 0.25, level, ()
        ),
    )
    return AnalyzedVideo(source=source, parsed=parsed)


def _plan(root: Path, *videos: AnalyzedVideo):
    analysis = AnalysisResult(root=root, videos=videos, issues=())
    return FolderPlanner().plan(analysis)


def test_builds_jellyfin_friendly_relative_destination(tmp_path: Path) -> None:
    video = _video(
        tmp_path,
        "incoming/random.mp4",
        artist="100 gecs",
        title="stupid horse",
        features=("GFOTY", "Count Baldor"),
        versions=("Remix",),
        year=2020,
    )

    item = _plan(tmp_path, video).items[0]

    assert item.destination == Path(
        "100 gecs/100 gecs feat. GFOTY & Count Baldor - stupid horse [Remix] (2020).mp4"
    )
    assert item.status is PlanStatus.READY


def test_routes_low_confidence_video_to_review(tmp_path: Path) -> None:
    video = _video(
        tmp_path,
        "Unstructured Filename.webm",
        artist=None,
        title="Unstructured Filename",
        level=ConfidenceLevel.LOW,
    )

    item = _plan(tmp_path, video).items[0]

    assert item.destination == Path("_Needs Review/Unstructured Filename.webm")
    assert item.status is PlanStatus.REVIEW
    assert item.notes == (
        "artist could not be determined",
        "parser confidence is low",
    )


def test_sanitizes_unsafe_and_reserved_path_components(tmp_path: Path) -> None:
    video = _video(
        tmp_path,
        "source.mp4",
        artist="CON",
        title='A/B: C? <Live> "Cut"',
    )

    item = _plan(tmp_path, video).items[0]

    assert item.destination == Path("_CON/CON - A-B- C- -Live- -Cut-.mp4")
    assert ".." not in item.destination.parts


def test_marks_case_insensitive_destination_collisions(tmp_path: Path) -> None:
    first = _video(tmp_path, "one.mp4", artist="Artist", title="Song")
    second = _video(tmp_path, "nested/two.mp4", artist="artist", title="song")

    plan = _plan(tmp_path, first, second)

    assert [item.status for item in plan.items] == [
        PlanStatus.CONFLICT,
        PlanStatus.CONFLICT,
    ]
    assert all("multiple files share" in item.notes[-1] for item in plan.items)


def test_planning_does_not_modify_media(tmp_path: Path) -> None:
    media = tmp_path / "Artist - Song.mp4"
    media.write_bytes(b"unchanged")
    before = media.stat()
    video = _video(tmp_path, media.name)

    _plan(tmp_path, video)

    assert media.read_bytes() == b"unchanged"
    assert media.stat().st_mtime_ns == before.st_mtime_ns
