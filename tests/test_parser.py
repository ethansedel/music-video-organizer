import pytest

from mvo.models import ConfidenceLevel
from mvo.parser import FilenameParser


@pytest.fixture
def parser() -> FilenameParser:
    return FilenameParser()


def test_parses_standard_artist_and_title(parser: FilenameParser) -> None:
    result = parser.parse("Massive Attack - Teardrop.mp4")

    assert result.artist == "Massive Attack"
    assert result.title == "Teardrop"
    assert result.featured_artists == ()
    assert result.confidence.level is ConfidenceLevel.HIGH
    assert result.confidence.score == 0.9


def test_parses_featured_artist_from_artist(parser: FilenameParser) -> None:
    result = parser.parse("Artist feat. Guest - Song.mp4")

    assert result.artist == "Artist"
    assert result.featured_artists == ("Guest",)
    assert result.title == "Song"


def test_parses_multiple_featured_artists_from_title(parser: FilenameParser) -> None:
    result = parser.parse("Artist - Song ft. Guest One & Guest Two.mp4")

    assert result.title == "Song"
    assert result.featured_artists == ("Guest One", "Guest Two")


def test_keeps_meaningful_versions_and_year(parser: FilenameParser) -> None:
    result = parser.parse("Artist - Song (Live at Wembley) (1998).mkv")

    assert result.versions == ("Live at Wembley",)
    assert result.year == 1998


@pytest.mark.parametrize(
    "technical_tag",
    ["1080p", "2160p", "4K", "x264", "HEVC", "WEB-DL", "Official Video"],
)
def test_ignores_technical_and_generic_video_tags(
    parser: FilenameParser, technical_tag: str
) -> None:
    result = parser.parse(f"Artist - Song [{technical_tag}].mp4")

    assert result.versions == ()


def test_falls_back_conservatively_to_title_only(parser: FilenameParser) -> None:
    result = parser.parse("Unstructured Filename.webm")

    assert result.artist is None
    assert result.title == "Unstructured Filename"
    assert result.confidence.level is ConfidenceLevel.LOW
    assert result.confidence.score == 0.25


def test_preserves_additional_title_dashes(parser: FilenameParser) -> None:
    result = parser.parse("Artist - Song - Radio Edit.mp4")

    assert result.artist == "Artist"
    assert result.title == "Song - Radio Edit"


# Regression: a bracket extractor must not discard a feature credit as generic metadata.
def test_feature_credit_inside_parentheses_is_not_lost(parser: FilenameParser) -> None:
    result = parser.parse("Artist - Song (feat. Guest).mp4")

    assert result.title == "Song"
    assert result.featured_artists == ("Guest",)
    assert result.versions == ()


# Regression: an internal hyphen must not be mistaken for the artist/title delimiter.
def test_hyphenated_names_are_not_split_twice(parser: FilenameParser) -> None:
    result = parser.parse("AC-DC - Rock-N-Roll Train.mp4")

    assert result.artist == "AC-DC"
    assert result.title == "Rock-N-Roll Train"


def test_deduplicates_feature_credits_case_insensitively(
    parser: FilenameParser,
) -> None:
    result = parser.parse("Artist feat. Guest - Song (ft. guest).mp4")

    assert result.featured_artists == ("Guest",)


# Regression: mixed version/feature qualifiers must preserve both pieces of metadata.
def test_mixed_version_and_feature_qualifier(parser: FilenameParser) -> None:
    result = parser.parse("Artist - Song (Live feat. Guest).mp4")

    assert result.versions == ("Live",)
    assert result.featured_artists == ("Guest",)


def test_uses_artist_folder_hint_and_removes_repeated_prefix(
    parser: FilenameParser,
) -> None:
    result = parser.parse(
        "100 gecs stupid horse (Remix) [feat. GFOTY and Count Baldor] "
        "{OFFICIAL MUSIC VIDEO} (1080p_24fps_H264-128kbit_AAC).mp4",
        artist_hint="100 gecs",
    )

    assert result.artist == "100 gecs"
    assert result.title == "stupid horse"
    assert result.featured_artists == ("GFOTY", "Count Baldor")
    assert result.versions == ("Remix",)


def test_ignores_director_instruction_and_compound_encoding_tags(
    parser: FilenameParser,
) -> None:
    result = parser.parse(
        "BEACH HOUSE - 'WISHES' - Directed by ERIC WAREHEIM (Official Video) "
        "- PLEASE SET TO 1080p!!! (854p_24fps_AV1-128kbit_AAC).mp4"
    )

    assert result.artist == "BEACH HOUSE"
    assert result.title == "WISHES"
    assert result.versions == ()


def test_parses_artist_followed_by_quoted_title(parser: FilenameParser) -> None:
    result = parser.parse(
        "billy woods & kenny segal 'Houthi' (1080p_24fps_H264-128kbit_AAC).mp4"
    )

    assert result.artist == "billy woods & kenny segal"
    assert result.title == "Houthi"
    assert result.versions == ()


@pytest.mark.parametrize("title", ["army of me", "human behaviour", "hunter"])
def test_parses_semicolon_delimited_bjork_titles(
    parser: FilenameParser, title: str
) -> None:
    result = parser.parse(f"björk ; {title} (HD) (1080p_25fps_H264-128kbit_AAC).mp4")

    assert result.artist == "björk"
    assert result.title == title
    assert result.versions == ()


def test_parses_double_hyphen_delimiter(parser: FilenameParser) -> None:
    result = parser.parse("Hot Action Cop-- Fever For The Flava.mp4")

    assert result.artist == "Hot Action Cop"
    assert result.title == "Fever For The Flava"


def test_preserves_japanese_aliases_and_removes_official_video_suffix(
    parser: FilenameParser,
) -> None:
    result = parser.parse(
        "Ichiban (イチバン) - Super Drive "
        "(スーパー・ドライブ) - Official Video "
        "(720p_30fps_H264-128kbit_AAC).mp4"
    )

    assert result.artist == "Ichiban (イチバン)"
    assert result.title == "Super Drive (スーパー・ドライブ)"
    assert result.versions == ()
