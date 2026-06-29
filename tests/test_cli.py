from pathlib import Path

import pytest

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


def test_cli_creates_opt_in_acoustid_report(
    tmp_path: Path, capsys: object, monkeypatch: object
) -> None:
    from mvo.acoustid import AcoustIDClient
    from mvo.models import AcousticFingerprint

    library = tmp_path / "library"
    library.mkdir()
    media = library / "Mystery.mp4"
    media.write_bytes(b"unchanged")
    output = tmp_path / "acoustid.html"

    class Extractor:
        available = True

        def fingerprint(self, _path: Path) -> AcousticFingerprint:
            return AcousticFingerprint(120, "fingerprint")

    payload = {"status": "ok", "results": []}
    client = AcoustIDClient("key", transport=lambda *_args: payload)
    monkeypatch.setenv("ACOUSTID_CLIENT_KEY", "key")  # type: ignore[attr-defined]
    monkeypatch.setattr("mvo.cli.FingerprintExtractor", Extractor)  # type: ignore[attr-defined]
    monkeypatch.setattr("mvo.cli.AcoustIDClient", lambda _key: client)  # type: ignore[attr-defined]

    exit_code = main(
        [str(library), "--acoustid", "--max-fingerprints", "1", "-o", str(output)]
    )

    assert exit_code == 0
    assert media.read_bytes() == b"unchanged"
    assert "No fingerprints were submitted" in output.read_text(encoding="utf-8")
    assert "Fingerprint-checked 1 video(s)" in capsys.readouterr().out  # type: ignore[attr-defined]


def test_cli_requires_acoustid_application_client_key(
    tmp_path: Path, monkeypatch: object
) -> None:
    monkeypatch.delenv("ACOUSTID_CLIENT_KEY", raising=False)  # type: ignore[attr-defined]

    with pytest.raises(SystemExit):
        main([str(tmp_path), "--acoustid"])


def test_cli_creates_opt_in_artwork_preview(
    tmp_path: Path, capsys: object, monkeypatch: object
) -> None:
    from mvo.coverart import CoverArtClient
    from mvo.musicbrainz import MusicBrainzClient

    library = tmp_path / "library"
    library.mkdir()
    media = library / "Artist - Song.mp4"
    media.write_bytes(b"unchanged")
    output = tmp_path / "artwork.html"
    musicbrainz_payload = {
        "release-groups": [
            {
                "id": "group",
                "score": 100,
                "title": "Song",
                "artist-credit": [{"name": "Artist"}],
            }
        ]
    }
    art_payload = {
        "images": [
            {
                "image": "https://coverartarchive.org/full.jpg",
                "thumbnails": {},
                "front": True,
                "approved": True,
            }
        ]
    }
    mb_client = MusicBrainzClient(transport=lambda *_args: musicbrainz_payload)
    art_client = CoverArtClient(transport=lambda *_args: art_payload)
    monkeypatch.setattr("mvo.cli.MusicBrainzClient", lambda: mb_client)  # type: ignore[attr-defined]
    monkeypatch.setattr("mvo.cli.CoverArtClient", lambda: art_client)  # type: ignore[attr-defined]

    exit_code = main(
        [str(library), "--artwork", "--max-artwork", "1", "-o", str(output)]
    )

    assert exit_code == 0
    assert media.read_bytes() == b"unchanged"
    assert "Remote preview only" in output.read_text(encoding="utf-8")
    assert "Artwork-checked 1 video(s)" in capsys.readouterr().out  # type: ignore[attr-defined]
