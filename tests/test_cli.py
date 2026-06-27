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
