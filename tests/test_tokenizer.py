from mvo.tokenizer import FilenameTokenizer


def test_tokenizes_explicit_delimiter_and_qualifiers() -> None:
    result = FilenameTokenizer().tokenize("Artist - Great Song (Live) [1080p].mkv")

    assert result.source_name == "Artist - Great Song (Live) [1080p].mkv"
    assert result.segments == ("Artist", "Great Song")
    assert result.qualifiers == ("Live", "1080p")
    assert result.has_explicit_separator is True


def test_normalizes_dots_underscores_and_track_number() -> None:
    result = FilenameTokenizer().tokenize("07._Artist_-_Song_Title.mp4")

    assert result.segments == ("Artist", "Song Title")


def test_does_not_split_hyphens_inside_names() -> None:
    result = FilenameTokenizer().tokenize("Jay-Z - Hard-Knock Life.mp4")

    assert result.segments == ("Jay-Z", "Hard-Knock Life")


def test_accepts_unicode_dash_separator() -> None:
    result = FilenameTokenizer().tokenize("Beyoncé — Halo.mov")

    assert result.segments == ("Beyoncé", "Halo")


def test_accepts_semicolon_and_double_hyphen_separators() -> None:
    tokenizer = FilenameTokenizer()

    assert tokenizer.tokenize("Björk ; Hunter.mp4").segments == ("Björk", "Hunter")
    assert tokenizer.tokenize("Artist-- Song.mp4").segments == ("Artist", "Song")


def test_extracts_curly_qualifier_but_preserves_japanese_alias() -> None:
    result = FilenameTokenizer().tokenize(
        "Ichiban (イチバン) - Super Drive {Official Video}.mp4"
    )

    assert result.segments == ("Ichiban (イチバン)", "Super Drive")
    assert result.qualifiers == ("Official Video",)
