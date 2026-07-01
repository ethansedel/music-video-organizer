from pathlib import Path

import pytest

from mvo.cli import build_parser, main


def test_cli_uses_liner_notes_brand() -> None:
    parser = build_parser()

    assert parser.prog == "liner-notes"
    assert "Liner Notes" in parser.description


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


def test_cli_starts_review_editor_without_modifying_media(
    tmp_path: Path, monkeypatch: object
) -> None:
    media = tmp_path / "Mystery.mp4"
    media.write_bytes(b"unchanged")
    called: dict[str, object] = {}

    def fake_serve(
        session: object,
        *,
        host: str,
        port: int,
        open_browser: bool,
        password: str | None,
        refresh_seconds: int,
    ) -> None:
        called.update(
            session=session,
            host=host,
            port=port,
            open_browser=open_browser,
            password=password,
            refresh_seconds=refresh_seconds,
        )

    monkeypatch.setattr("mvo.cli.serve_review", fake_serve)  # type: ignore[attr-defined]

    exit_code = main([str(tmp_path), "--review", "--review-port", "9000"])

    assert exit_code == 0
    assert called["port"] == 9000
    assert called["host"] == "127.0.0.1"
    assert called["open_browser"] is True
    assert called["password"] is None
    assert called["refresh_seconds"] == 300
    assert media.read_bytes() == b"unchanged"


def test_cli_requires_password_for_network_review(tmp_path: Path) -> None:
    with pytest.raises(SystemExit):
        main([str(tmp_path), "--review", "--review-host", "0.0.0.0"])


def test_cli_rejects_too_frequent_review_refresh(tmp_path: Path) -> None:
    with pytest.raises(SystemExit):
        main([str(tmp_path), "--review", "--review-refresh-seconds", "29"])


def test_cli_creates_read_only_preflight_report(tmp_path: Path, capsys: object) -> None:
    library = tmp_path / "library"
    library.mkdir()
    media = library / "Artist - Song.mp4"
    media.write_bytes(b"unchanged")
    output = tmp_path / "preflight.html"

    exit_code = main([str(library), "--preflight", "--output", str(output)])

    assert exit_code == 0
    assert media.read_bytes() == b"unchanged"
    assert "Safety snapshot only" in output.read_text(encoding="utf-8")
    assert "Preflight-checked 1 video(s)" in capsys.readouterr().out  # type: ignore[attr-defined]


def test_cli_requires_exact_execution_confirmation(tmp_path: Path) -> None:
    media = tmp_path / "Artist - Song.mp4"
    media.write_bytes(b"unchanged")

    with pytest.raises(SystemExit):
        main([str(tmp_path), "--execute"])

    assert media.read_bytes() == b"unchanged"


def test_cli_rejects_execution_confirmation_outside_execution(
    tmp_path: Path,
) -> None:
    with pytest.raises(SystemExit):
        main([str(tmp_path), "--confirm-execution", "MOVE_FILES"])


def test_cli_rejects_non_html_execution_audit(tmp_path: Path) -> None:
    with pytest.raises(SystemExit):
        main(
            [
                str(tmp_path),
                "--execute",
                "--confirm-execution",
                "MOVE_FILES",
                "--output",
                str(tmp_path / "not-a-report.mp4"),
            ]
        )


def test_cli_executes_confirmed_moves_and_writes_audit(
    tmp_path: Path, capsys: object
) -> None:
    library = tmp_path / "library"
    incoming = library / "incoming"
    incoming.mkdir(parents=True)
    media = incoming / "Artist - Song.mp4"
    media.write_bytes(b"video")
    output = tmp_path / "execution.html"

    exit_code = main(
        [
            str(library),
            "--execute",
            "--confirm-execution",
            "MOVE_FILES",
            "--output",
            str(output),
        ]
    )

    assert exit_code == 0
    assert not media.exists()
    assert (library / "Artist" / "Artist - Song.mp4").read_bytes() == b"video"
    assert "Execution completed" in output.read_text(encoding="utf-8")
    assert "Executed 1 move(s)" in capsys.readouterr().out  # type: ignore[attr-defined]


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
