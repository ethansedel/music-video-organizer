from pathlib import Path

from mvo.cli import main


def test_cli_creates_report(tmp_path: Path, capsys: object) -> None:
    library = tmp_path / "library"
    library.mkdir()
    (library / "Artist - Song.mp4").touch()
    output = tmp_path / "output.html"

    exit_code = main([str(library), "--output", str(output)])

    assert exit_code == 0
    assert output.exists()
    assert "Analyzed 1 video(s)" in capsys.readouterr().out  # type: ignore[attr-defined]


def test_cli_creates_read_only_plan_report(tmp_path: Path, capsys: object) -> None:
    library = tmp_path / "library"
    library.mkdir()
    media = library / "Artist - Song.mp4"
    media.write_bytes(b"unchanged")
    output = tmp_path / "dry-run.html"

    exit_code = main([str(library), "--plan", "--output", str(output)])

    assert exit_code == 0
    assert media.read_bytes() == b"unchanged"
    assert "Preview only" in output.read_text(encoding="utf-8")
    assert "Planned 1 video(s)" in capsys.readouterr().out  # type: ignore[attr-defined]


def test_cli_creates_read_only_duplicate_report(tmp_path: Path, capsys: object) -> None:
    library = tmp_path / "library"
    library.mkdir()
    first = library / "Artist - Song.mp4"
    second = library / "Copy - Song.mp4"
    first.write_bytes(b"same")
    second.write_bytes(b"same")
    output = tmp_path / "duplicates.html"

    exit_code = main([str(library), "--duplicates", "--output", str(output)])

    assert exit_code == 0
    assert first.read_bytes() == b"same"
    assert second.read_bytes() == b"same"
    assert "Read-only report" in output.read_text(encoding="utf-8")
    assert "Checked 2 video(s)" in capsys.readouterr().out  # type: ignore[attr-defined]


def test_cli_creates_opt_in_musicbrainz_report(
    tmp_path: Path, capsys: object, monkeypatch: object
) -> None:
    from mvo.musicbrainz import MusicBrainzClient

    library = tmp_path / "library"
    library.mkdir()
    media = library / "Artist - Song.mp4"
    media.write_bytes(b"unchanged")
    output = tmp_path / "musicbrainz.html"
    payload = {
        "recordings": [
            {
                "id": "recording-id",
                "score": 100,
                "title": "Song",
                "artist-credit": [{"name": "Artist"}],
            }
        ]
    }
    client = MusicBrainzClient(transport=lambda *_args: payload)
    monkeypatch.setattr("mvo.cli.MusicBrainzClient", lambda: client)  # type: ignore[attr-defined]

    exit_code = main(
        [str(library), "--musicbrainz", "--max-queries", "1", "-o", str(output)]
    )

    assert exit_code == 0
    assert media.read_bytes() == b"unchanged"
    assert "did not upload audio" in output.read_text(encoding="utf-8")
    assert "Enriched 1 video(s)" in capsys.readouterr().out  # type: ignore[attr-defined]
