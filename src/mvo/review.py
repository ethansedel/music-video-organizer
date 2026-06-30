# ruff: noqa: E501
"""Local-only web editor for videos that need metadata review."""

from __future__ import annotations

import base64
import json
import mimetypes
import secrets
import webbrowser
from collections import defaultdict
from dataclasses import replace
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlsplit

from mvo.analyzer import LibraryAnalyzer
from mvo.execution_report import write_execution_report
from mvo.executor import PlanExecutor
from mvo.models import (
    AnalysisResult,
    ExecutionStatus,
    OrganizationPlan,
    PlannedVideo,
    PlanStatus,
)
from mvo.musicbrainz import MusicBrainzClient, MusicBrainzError
from mvo.overrides import MetadataOverride, MetadataOverrideStore
from mvo.planner import FolderPlanner
from mvo.quarantine import DuplicateQuarantine
from mvo.review_media import ReviewMediaInspector


class ReviewSession:
    """Coordinate editable overrides with fresh, read-only planning results."""

    def __init__(
        self,
        analysis: AnalysisResult,
        store: MetadataOverrideStore,
        planner: FolderPlanner | None = None,
        musicbrainz: MusicBrainzClient | None = None,
        inspector: ReviewMediaInspector | None = None,
        executor: PlanExecutor | None = None,
        quarantine: DuplicateQuarantine | None = None,
    ) -> None:
        self.analysis = analysis
        self.store = store
        self.planner = planner or FolderPlanner()
        self.musicbrainz = musicbrainz or MusicBrainzClient()
        self.inspector = inspector or ReviewMediaInspector()
        self.executor = executor or PlanExecutor()
        self.quarantine = quarantine or DuplicateQuarantine()
        self.overrides = store.load()
        self.review_paths: set[str] = set()
        self._refresh_review_paths()

    def items(self, *, scope: str = "review") -> list[dict[str, object]]:
        """Return current editable fields and recomputed plan status."""

        if scope not in {"review", "all", "trash"}:
            raise ValueError("scope must be review, all, or trash")
        if scope == "trash":
            return self.trash_items()
        current = self._current_analysis()
        plan = self.planner.plan(current)
        conflicts: dict[str, list[PlannedVideo]] = defaultdict(list)
        for planned in plan.items:
            if planned.status is PlanStatus.CONFLICT:
                conflicts[planned.destination.as_posix()].append(planned)
        recommendations = {
            destination: self._recommended_path(group)
            for destination, group in conflicts.items()
        }
        items: list[dict[str, object]] = []
        for planned in plan.items:
            path = planned.video.source.relative_path.as_posix()
            if scope == "review" and path not in self.review_paths:
                continue
            parsed = planned.video.parsed
            conflict_group = conflicts.get(planned.destination.as_posix(), [])
            quality = self.inspector.filename_quality(planned.video.source.path)
            status = planned.status.value
            if planned.status is PlanStatus.READY:
                if planned.destination == planned.video.source.relative_path:
                    status = "organized"
                elif path in self.overrides:
                    status = "resolved"
            items.append(
                {
                    "path": path,
                    "filename": planned.video.source.path.name,
                    "artist": parsed.artist or "",
                    "title": parsed.title,
                    "featured_artists": list(parsed.featured_artists),
                    "versions": list(parsed.versions),
                    "year": parsed.year,
                    "destination": planned.destination.as_posix(),
                    "status": status,
                    "notes": list(planned.notes),
                    "saved": path in self.overrides,
                    "size": self._format_size(planned.video.source.size_bytes),
                    "quality": quality.label,
                    "conflict_paths": [
                        item.video.source.relative_path.as_posix()
                        for item in conflict_group
                    ],
                    "recommended": bool(conflict_group)
                    and recommendations[planned.destination.as_posix()] == path,
                }
            )
        return items

    def trash_items(self) -> list[dict[str, object]]:
        """Return review cards for videos held in Liner Notes Trash."""

        trash_root = self.analysis.root / self.quarantine.directory_name
        items: list[dict[str, object]] = []
        for path in self.quarantine.list_files(self.analysis.root):
            relative = path.relative_to(self.analysis.root).as_posix()
            original = path.relative_to(trash_root).as_posix()
            stat = path.stat()
            quality = self.inspector.filename_quality(path)
            items.append(
                {
                    "path": relative,
                    "filename": path.name,
                    "artist": "",
                    "title": path.stem,
                    "status": "trash",
                    "saved": False,
                    "size": self._format_size(stat.st_size),
                    "quality": quality.label,
                    "original_path": original,
                    "trashed": True,
                }
            )
        return items

    def update(self, path: object, value: object) -> dict[str, object]:
        """Validate, persist, and return one edited review item."""

        if not isinstance(path, str) or path not in self._video_paths():
            raise ValueError("video is not part of this library")
        override = MetadataOverride.from_dict(value)
        updated = {**self.overrides, path: override}
        self.store.save(updated)
        self.overrides = updated
        self.review_paths.add(path)
        return next(item for item in self.items() if item["path"] == path)

    def choose_preferred(self, path: object) -> list[dict[str, object]]:
        """Keep one collision item canonical and preserve others as alternates."""

        if not isinstance(path, str):
            raise ValueError("preferred path must be text")
        plan = self.planner.plan(self._current_analysis())
        selected = next(
            (
                item
                for item in plan.items
                if item.video.source.relative_path.as_posix() == path
            ),
            None,
        )
        if selected is None or selected.status is not PlanStatus.CONFLICT:
            raise ValueError("video is not part of a destination conflict")
        group = [
            item
            for item in plan.items
            if item.destination == selected.destination
            and item.status is PlanStatus.CONFLICT
        ]
        if any(item.video.parsed.artist is None for item in group):
            raise ValueError(
                "enter and save an artist for each copy before choosing a preferred file"
            )
        updated = dict(self.overrides)
        alternate_number = 1
        for item in group:
            parsed = item.video.parsed
            item_path = item.video.source.relative_path.as_posix()
            versions = parsed.versions
            if item_path != path:
                label = "Alternate" if alternate_number == 1 else f"Alternate {alternate_number}"
                alternate_number += 1
                versions = (*versions, label)
            updated[item_path] = MetadataOverride(
                artist=parsed.artist or "Unknown Artist",
                title=parsed.title,
                featured_artists=parsed.featured_artists,
                versions=versions,
                year=parsed.year,
            )
        self.store.save(updated)
        self.overrides = updated
        self.review_paths.update(
            item.video.source.relative_path.as_posix() for item in group
        )
        return self.items()

    def search_metadata(self, artist: object, title: object) -> list[dict[str, object]]:
        """Run one explicit MusicBrainz recording search for the editor."""

        if not isinstance(artist, str) or not artist.strip():
            raise ValueError("enter an artist before searching MusicBrainz")
        if not isinstance(title, str) or not title.strip():
            raise ValueError("enter a title before searching MusicBrainz")
        try:
            candidates = self.musicbrainz.search_recordings(
                artist.strip(), title.strip(), limit=5
            )
        except MusicBrainzError as error:
            raise ValueError(f"MusicBrainz search failed: {error}") from error
        return [
            {
                "artist": candidate.artist_credit,
                "title": candidate.title,
                "year": self._candidate_year(candidate.first_release_date),
                "score": candidate.score,
                "recording_id": candidate.recording_id,
            }
            for candidate in candidates
        ]

    def trash_duplicate(
        self, path: object, confirmation: object
    ) -> dict[str, object]:
        """Move one conflict copy to recoverable Liner Notes Trash."""

        if not isinstance(path, str):
            raise ValueError("duplicate path must be text")
        plan = self.planner.plan(self._current_analysis())
        selected = next(
            (
                item
                for item in plan.items
                if item.video.source.relative_path.as_posix() == path
            ),
            None,
        )
        if selected is None or selected.status is not PlanStatus.CONFLICT:
            raise ValueError("only an active destination conflict can be trashed")
        group = [
            item
            for item in plan.items
            if item.status is PlanStatus.CONFLICT
            and item.destination == selected.destination
        ]
        if len(group) < 2:
            raise ValueError("at least one duplicate copy must remain")
        result = self.quarantine.quarantine(
            plan.root,
            selected.video.source,
            confirmation=confirmation,
        )
        if path in self.overrides:
            self.overrides = {
                key: value for key, value in self.overrides.items() if key != path
            }
            self.store.save(self.overrides)
        self.analysis = LibraryAnalyzer().analyze(self.analysis.root)
        self._refresh_review_paths()
        return {
            "source": path,
            "destination": result.destination.relative_to(plan.root).as_posix(),
            "size": self._format_size(result.size_bytes),
        }

    def restore_trash(self, path: object, confirmation: object) -> dict[str, object]:
        """Restore one Liner Notes Trash file to its original path."""

        destination = self.quarantine.restore(
            self.analysis.root, path, confirmation=confirmation
        )
        self.analysis = LibraryAnalyzer().analyze(self.analysis.root)
        self._refresh_review_paths()
        return {"destination": destination.relative_to(self.analysis.root).as_posix()}

    def delete_trash(self, path: object, confirmation: object) -> dict[str, object]:
        """Permanently delete one selected Liner Notes Trash file."""

        size = self.quarantine.delete_permanently(
            self.analysis.root, path, confirmation=confirmation
        )
        return {"deleted": 1, "size": self._format_size(size)}

    def empty_trash(self, confirmation: object) -> dict[str, object]:
        """Permanently delete all reviewed Liner Notes Trash videos."""

        deleted, deleted_bytes, errors = self.quarantine.empty(
            self.analysis.root, confirmation=confirmation
        )
        return {
            "deleted": deleted,
            "size": self._format_size(deleted_bytes),
            "errors": errors,
        }

    def quality(self, path: object) -> dict[str, object]:
        """Return lazily probed quality details for one library video."""

        video_path = self.media_path(path)
        quality = self.inspector.quality(video_path)
        return {
            "label": quality.label,
            "width": quality.width,
            "height": quality.height,
            "bit_rate": quality.bit_rate,
            "codec": quality.codec,
        }

    def thumbnail(self, path: object) -> bytes | None:
        """Return a generated JPEG thumbnail for one library video."""

        return self.inspector.thumbnail(self.media_path(path))

    def media_path(self, path: object) -> Path:
        """Resolve an exact scanned relative path without allowing traversal."""

        if not isinstance(path, str):
            raise ValueError("video path must be text")
        paths = self._video_paths()
        if path in paths:
            return paths[path]
        return self.quarantine.resolve(self.analysis.root, path)

    def apply_saved(self, confirmation: object) -> dict[str, object]:
        """Execute only saved, ready corrections after exact confirmation."""

        if confirmation != "MOVE_FILES":
            raise ValueError("type MOVE_FILES to apply saved corrections")
        plan = self.planner.plan(self._current_analysis())
        selected = tuple(
            item
            for item in plan.items
            if item.video.source.relative_path.as_posix() in self.overrides
            and item.status is PlanStatus.READY
        )
        if not selected:
            raise ValueError("there are no saved, ready corrections to apply")
        execution = self.executor.execute(
            OrganizationPlan(plan.root, selected, plan.issues)
        )
        audit_path = self.store.path.with_name(".mvo-review-execution.html")
        report_error: str | None = None
        try:
            write_execution_report(execution, audit_path)
        except OSError as error:
            report_error = str(error)
        moved_paths = {
            item.planned.video.source.relative_path.as_posix()
            for item in execution.items
            if item.status is ExecutionStatus.MOVED
        }
        if moved_paths:
            self.overrides = {
                path: value
                for path, value in self.overrides.items()
                if path not in moved_paths
            }
            self.store.save(self.overrides)
        self.analysis = LibraryAnalyzer().analyze(self.analysis.root)
        self._refresh_review_paths()
        return {
            "moved": execution.moved_count,
            "unchanged": sum(
                item.status is ExecutionStatus.UNCHANGED for item in execution.items
            ),
            "failed": sum(
                item.status is ExecutionStatus.FAILED for item in execution.items
            ),
            "rolled_back": execution.rolled_back,
            "rollback_complete": execution.rollback_complete,
            "report": str(audit_path) if report_error is None else None,
            "report_error": report_error,
        }

    def _current_analysis(self) -> AnalysisResult:
        videos = tuple(
            replace(video, parsed=self.overrides[path].apply(video.parsed))
            if (path := video.source.relative_path.as_posix()) in self.overrides
            else video
            for video in self.analysis.videos
        )
        return replace(self.analysis, videos=videos)

    def _refresh_review_paths(self) -> None:
        initial = self.planner.plan(self.analysis)
        scanned_paths = set(self._video_paths())
        self.review_paths = {
            item.video.source.relative_path.as_posix()
            for item in initial.items
            if item.status is not PlanStatus.READY
        } | (self.overrides.keys() & scanned_paths)

    def _video_paths(self) -> dict[str, Path]:
        return {
            video.source.relative_path.as_posix(): video.source.path
            for video in self.analysis.videos
        }

    def _recommended_path(self, group: list[PlannedVideo]) -> str:
        recommended = max(
            group,
            key=lambda item: (
                self.inspector.filename_quality(item.video.source.path).height or 0,
                item.video.source.size_bytes,
            ),
        )
        return recommended.video.source.relative_path.as_posix()

    @staticmethod
    def _format_size(value: int) -> str:
        size = float(value)
        for unit in ("B", "KB", "MB", "GB", "TB"):
            if size < 1024 or unit == "TB":
                return f"{size:.1f} {unit}" if unit != "B" else f"{int(size)} B"
            size /= 1024
        return f"{size:.1f} TB"

    @staticmethod
    def _candidate_year(value: str | None) -> int | None:
        if value and len(value) >= 4 and value[:4].isdigit():
            return int(value[:4])
        return None


def serve_review(
    session: ReviewSession,
    *,
    host: str = "127.0.0.1",
    port: int = 8765,
    open_browser: bool = True,
    password: str | None = None,
) -> None:
    """Serve the password-protected review GUI until interrupted."""

    token = secrets.token_urlsafe(24)
    handler = _handler_for(session, token, password=password)
    server = ThreadingHTTPServer((host, port), handler)
    url = f"http://{host}:{server.server_port}/"
    print(f"Reviewing {len(session.review_paths)} video(s) at {url}")
    print(f"Corrections file: {session.store.path}")
    if password is not None:
        print("HTTP username: liner-notes")
    print("Press Control-C when you are finished.")
    if open_browser and host in {"127.0.0.1", "::1", "localhost"}:
        webbrowser.open(url)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nReview editor stopped.")
    finally:
        server.server_close()


def _handler_for(
    session: ReviewSession,
    token: str,
    *,
    password: str | None = None,
) -> type[BaseHTTPRequestHandler]:
    class ReviewHandler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:  # noqa: N802
            parsed_url = urlsplit(self.path)
            path = parsed_url.path
            query = parse_qs(parsed_url.query)
            if path == "/healthz":
                self._send_json(HTTPStatus.OK, {"status": "ok"})
                return
            if not self._authorized():
                return
            if path == "/":
                self._send_bytes(
                    HTTPStatus.OK,
                    _page(token).encode(),
                    "text/html; charset=utf-8",
                )
            elif path == "/api/items":
                try:
                    items = session.items(scope=query.get("scope", ["review"])[0])
                except ValueError as error:
                    self._send_json(HTTPStatus.BAD_REQUEST, {"error": str(error)})
                    return
                self._send_json(HTTPStatus.OK, {"items": items})
            elif path == "/api/quality":
                try:
                    quality = session.quality(query.get("path", [None])[0])
                except ValueError as error:
                    self._send_json(HTTPStatus.BAD_REQUEST, {"error": str(error)})
                    return
                self._send_json(HTTPStatus.OK, {"quality": quality})
            elif path == "/thumbnail":
                if query.get("token", [None])[0] != token:
                    self._send_json(HTTPStatus.FORBIDDEN, {"error": "invalid token"})
                    return
                try:
                    thumbnail = session.thumbnail(query.get("path", [None])[0])
                except ValueError as error:
                    self._send_json(HTTPStatus.BAD_REQUEST, {"error": str(error)})
                    return
                if thumbnail is None:
                    self._send_json(
                        HTTPStatus.NOT_FOUND, {"error": "thumbnail unavailable"}
                    )
                    return
                self._send_bytes(HTTPStatus.OK, thumbnail, "image/jpeg")
            elif path == "/media":
                if query.get("token", [None])[0] != token:
                    self._send_json(HTTPStatus.FORBIDDEN, {"error": "invalid token"})
                    return
                try:
                    media_path = session.media_path(query.get("path", [None])[0])
                    self._send_media(media_path)
                except ValueError as error:
                    self._send_json(HTTPStatus.BAD_REQUEST, {"error": str(error)})
                except OSError as error:
                    self._send_json(
                        HTTPStatus.INTERNAL_SERVER_ERROR, {"error": str(error)}
                    )
            else:
                self._send_json(HTTPStatus.NOT_FOUND, {"error": "not found"})

        def do_POST(self) -> None:  # noqa: N802
            if not self._authorized():
                return
            path = urlsplit(self.path).path
            if path not in {
                "/api/overrides",
                "/api/preferred",
                "/api/search",
                "/api/commit",
                "/api/trash",
                "/api/restore-trash",
                "/api/delete-trash",
                "/api/empty-trash",
            }:
                self._send_json(HTTPStatus.NOT_FOUND, {"error": "not found"})
                return
            if self.headers.get("X-Liner-Notes-Token") != token:
                self._send_json(HTTPStatus.FORBIDDEN, {"error": "invalid token"})
                return
            try:
                length = int(self.headers.get("Content-Length", "0"))
                if length <= 0 or length > 64 * 1024:
                    raise ValueError("request body has an invalid size")
                payload = json.loads(self.rfile.read(length))
                if not isinstance(payload, dict):
                    raise ValueError("request body must be an object")
                if path == "/api/overrides":
                    response = {
                        "item": session.update(
                            payload.get("path"), payload.get("override")
                        )
                    }
                elif path == "/api/preferred":
                    response = {
                        "items": session.choose_preferred(payload.get("path"))
                    }
                elif path == "/api/search":
                    response = {
                        "candidates": session.search_metadata(
                            payload.get("artist"), payload.get("title")
                        )
                    }
                elif path == "/api/trash":
                    response = {
                        "trash": session.trash_duplicate(
                            payload.get("path"), payload.get("confirmation")
                        )
                    }
                elif path == "/api/restore-trash":
                    response = {
                        "restore": session.restore_trash(
                            payload.get("path"), payload.get("confirmation")
                        )
                    }
                elif path == "/api/delete-trash":
                    response = {
                        "delete": session.delete_trash(
                            payload.get("path"), payload.get("confirmation")
                        )
                    }
                elif path == "/api/empty-trash":
                    response = {
                        "empty": session.empty_trash(payload.get("confirmation"))
                    }
                else:
                    response = {
                        "execution": session.apply_saved(payload.get("confirmation"))
                    }
            except (OSError, ValueError, json.JSONDecodeError) as error:
                self._send_json(HTTPStatus.BAD_REQUEST, {"error": str(error)})
                return
            self._send_json(HTTPStatus.OK, response)

        def log_message(self, _format: str, *_args: Any) -> None:
            return

        def _authorized(self) -> bool:
            if password is None:
                return True
            expected = _basic_authorization(password)
            if secrets.compare_digest(
                self.headers.get("Authorization", ""), expected
            ):
                return True
            self.send_response(HTTPStatus.UNAUTHORIZED)
            self.send_header("WWW-Authenticate", 'Basic realm="Liner Notes"')
            self.send_header("Content-Length", "0")
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            return False

        def _send_json(self, status: HTTPStatus, payload: object) -> None:
            self._send_bytes(
                status,
                json.dumps(payload, ensure_ascii=False).encode(),
                "application/json; charset=utf-8",
            )

        def _send_bytes(
            self, status: HTTPStatus, content: bytes, content_type: str
        ) -> None:
            self.send_response(status)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(content)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("Content-Security-Policy", "default-src 'self'; script-src 'unsafe-inline'; style-src 'unsafe-inline'")
            self.end_headers()
            self.wfile.write(content)

        def _send_media(self, path: Path) -> None:
            size = path.stat().st_size
            start = 0
            end = size - 1
            status = HTTPStatus.OK
            range_header = self.headers.get("Range")
            if range_header:
                if not range_header.startswith("bytes=") or "," in range_header:
                    self.send_error(HTTPStatus.REQUESTED_RANGE_NOT_SATISFIABLE)
                    return
                start_text, _, end_text = range_header[6:].partition("-")
                try:
                    start = int(start_text) if start_text else 0
                    end = int(end_text) if end_text else min(size - 1, start + 4_194_303)
                except ValueError:
                    self.send_error(HTTPStatus.REQUESTED_RANGE_NOT_SATISFIABLE)
                    return
                if start < 0 or end < start or start >= size:
                    self.send_error(HTTPStatus.REQUESTED_RANGE_NOT_SATISFIABLE)
                    return
                end = min(end, size - 1)
                status = HTTPStatus.PARTIAL_CONTENT
            length = end - start + 1
            self.send_response(status)
            self.send_header(
                "Content-Type",
                mimetypes.guess_type(path.name)[0] or "application/octet-stream",
            )
            self.send_header("Content-Length", str(length))
            self.send_header("Accept-Ranges", "bytes")
            self.send_header("Cache-Control", "no-store")
            if status is HTTPStatus.PARTIAL_CONTENT:
                self.send_header("Content-Range", f"bytes {start}-{end}/{size}")
            self.end_headers()
            with path.open("rb") as media:
                media.seek(start)
                remaining = length
                while remaining:
                    chunk = media.read(min(1024 * 1024, remaining))
                    if not chunk:
                        break
                    try:
                        self.wfile.write(chunk)
                    except (BrokenPipeError, ConnectionResetError):
                        break
                    remaining -= len(chunk)

    return ReviewHandler


def _basic_authorization(password: str) -> str:
    """Build the exact HTTP Basic value used by the server."""

    credentials = base64.b64encode(f"liner-notes:{password}".encode()).decode()
    return f"Basic {credentials}"


def _page(token: str) -> str:
    """Return the self-contained review application."""

    safe_token = json.dumps(token)
    return f'''<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Liner Notes</title><style>
:root{{--ink:#17211d;--muted:#64726b;--paper:#f3f0e8;--card:#fffdf8;--accent:#176b55;--accent2:#d9eee6;--warn:#a54d2d;--line:#d7ddd7;--blue:#315f91}}
*{{box-sizing:border-box}}body{{margin:0;background:var(--paper);color:var(--ink);font:16px/1.45 system-ui,sans-serif}}
header{{padding:34px max(22px,calc((100vw - 1180px)/2));background:#173b32;color:white}}
.head{{display:flex;justify-content:space-between;gap:20px;align-items:center}}h1{{margin:0 0 6px;font-size:clamp(28px,4vw,44px)}}.product-subtitle{{font-size:.42em;font-weight:500;margin-left:.65rem;color:#c9ddd6;white-space:nowrap}}header p{{margin:0;color:#c9ddd6}}
main{{max-width:1180px;margin:auto;padding:22px}}button,input{{font:inherit}}button{{border:0;border-radius:8px;padding:9px 13px;cursor:pointer;background:#e5e8e3}}button:disabled{{opacity:.55;cursor:wait}}
.primary,.save,.commit{{background:var(--accent);color:white}}.danger{{background:#a33c2f;color:white}}.commit{{padding:12px 17px;font-weight:750;white-space:nowrap}}
.scope,.toolbar,.filters,.media-actions,.actions{{display:flex;gap:8px;flex-wrap:wrap;align-items:center}}.scope{{margin-bottom:14px}}.scope button.active,.filters button.active{{background:#263f37;color:white}}
.toolbar{{margin-bottom:12px}}#search{{flex:1;min-width:260px;padding:10px 12px;border:1px solid var(--line);border-radius:8px}}
.summary{{color:var(--muted);margin:12px 0 18px}}.list{{display:grid;gap:17px}}article{{background:var(--card);border:1px solid var(--line);border-radius:15px;padding:17px;box-shadow:0 4px 16px #1833290a}}
.card-layout{{display:grid;grid-template-columns:190px 1fr;gap:17px}}.thumb{{height:108px;border-radius:10px;overflow:hidden;background:linear-gradient(145deg,#29473e,#172b25);display:grid;place-items:center}}.thumb img{{width:100%;height:100%;object-fit:cover}}.thumb.missing:after{{content:'No thumbnail';color:#cbdad4;font-size:13px}}.thumb.missing img{{display:none}}
.top{{display:flex;justify-content:space-between;gap:12px;align-items:start}}h2{{font-size:17px;margin:0;overflow-wrap:anywhere}}.path,.message,.quality{{font-size:13px;color:var(--muted);overflow-wrap:anywhere}}
.badge{{border-radius:999px;padding:5px 9px;font-size:12px;font-weight:750;background:#f3ddd5;color:var(--warn);text-transform:capitalize}}.badge.resolved,.badge.organized{{background:var(--accent2);color:var(--accent)}}.badge.ready{{background:#dce7f4;color:var(--blue)}}
.conflict{{margin:12px 0;padding:11px;border-radius:9px;background:#fff0d5;color:#775019;font-size:14px}}.recommended{{font-weight:800;color:var(--accent)}}
.grid{{display:grid;grid-template-columns:1fr 1fr;gap:11px;margin-top:14px}}label{{font-size:13px;font-weight:750}}label input{{display:block;width:100%;margin-top:5px;padding:9px;border:1px solid var(--line);border-radius:8px;background:white;font-weight:400}}.wide{{grid-column:1/-1}}.actions{{justify-content:space-between;margin-top:13px}}.right-actions{{display:flex;gap:8px;flex-wrap:wrap}}.empty{{padding:50px;text-align:center;color:var(--muted)}}
dialog{{border:0;border-radius:14px;padding:0;max-width:min(1100px,96vw);width:100%;box-shadow:0 20px 70px #0007}}dialog::backdrop{{background:#0d211bba}}.modal-head{{display:flex;justify-content:space-between;align-items:center;padding:15px 18px;border-bottom:1px solid var(--line)}}.modal-body{{padding:18px;max-height:78vh;overflow:auto}}video{{width:100%;max-height:65vh;background:black}}.candidate{{display:flex;justify-content:space-between;gap:12px;padding:13px 0;border-bottom:1px solid var(--line)}}.compare-grid{{display:grid;grid-template-columns:repeat(auto-fit,minmax(300px,1fr));gap:16px}}.compare-card{{border:1px solid var(--line);border-radius:12px;padding:13px;background:var(--card)}}.compare-card video{{height:230px;object-fit:contain;border-radius:8px}}.compare-card h3{{font-size:15px;overflow-wrap:anywhere}}.compare-details{{min-height:44px;color:var(--muted);font-size:13px;margin:8px 0}}.compare-card.recommended-copy{{border:2px solid var(--accent)}}
@media(max-width:720px){{.head{{align-items:start;flex-direction:column}}.card-layout{{grid-template-columns:1fr}}.thumb{{height:190px}}.grid{{grid-template-columns:1fr}}.wide{{grid-column:auto}}}}
</style></head><body>
<header><div class="head"><div><h1>Liner Notes <span class="product-subtitle">Music Video Organizer</span></h1><p>Preview files, fix metadata, resolve conflicts, and safely apply saved corrections.</p></div><button class="commit" onclick="commitSaved()">Commit saved changes</button></div></header>
<main>
<div class="scope"><button data-scope="review" class="active">Needs attention</button><button data-scope="all">All library videos</button><button data-scope="trash">Liner Notes Trash</button><button class="danger" id="empty-trash" onclick="emptyTrash()" hidden>Empty Liner Notes Trash</button></div>
<div class="toolbar"><input id="search" type="search" placeholder="Search filenames, artists, or titles"><div class="filters"><button data-filter="all" class="active">All</button><button data-filter="open">Unresolved</button><button data-filter="resolved">Ready / organized</button></div></div>
<div class="summary" id="summary">Loading…</div><section class="list" id="list"></section>
</main>
<dialog id="modal"><div class="modal-head"><strong id="modal-title">Preview</strong><button onclick="closeModal()">Close</button></div><div class="modal-body" id="modal-body"></div></dialog>
<script>
const token={safe_token};let items=[];let filter='all';let scope='review';let activeIndex=-1;
const esc=s=>String(s??'').replace(/[&<>"']/g,c=>({{'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}}[c]));
const split=s=>s.split(',').map(x=>x.trim()).filter(Boolean);
const url=(kind,path)=>`/${{kind}}?token=${{encodeURIComponent(token)}}&path=${{encodeURIComponent(path)}}`;
async function post(path,body){{const r=await fetch(path,{{method:'POST',headers:{{'Content-Type':'application/json','X-Liner-Notes-Token':token}},body:JSON.stringify(body)}});const d=await r.json();if(!r.ok)throw Error(d.error);return d;}}
async function load(nextScope=scope){{scope=nextScope;document.querySelector('#summary').textContent='Loading library…';document.querySelector('#empty-trash').hidden=scope!=='trash';const r=await fetch('/api/items?scope='+scope);const d=await r.json();if(!r.ok)throw Error(d.error);items=d.items;render();}}
function isResolved(i){{return ['resolved','organized','ready'].includes(i.status)}}
function visible(i){{const q=document.querySelector('#search').value.toLowerCase();const match=!q||[i.filename,i.artist,i.title,i.path].join(' ').toLowerCase().includes(q);return match&&(filter==='all'||(filter==='resolved')===isResolved(i));}}
function render(){{const shown=items.filter(visible);const saved=items.filter(i=>i.saved).length,conflicts=items.filter(i=>i.status==='conflict').length;document.querySelector('#summary').textContent=scope==='trash'?`${{items.length}} recoverable video files in Liner Notes Trash`:`${{items.length}} videos · ${{saved}} saved corrections · ${{conflicts}} destination conflicts`;document.querySelector('#list').innerHTML=shown.length?shown.map(card).join(''):`<div class="empty">${{scope==='trash'?'Liner Notes Trash is empty.':'No videos match this view.'}}</div>`;}}
function card(i){{return i.trashed?trashCard(i):activeCard(i)}}
function trashCard(i){{const index=items.indexOf(i),id='i'+index;return `<article id="${{id}}"><div class="card-layout"><div><div class="thumb"><img loading="lazy" src="${{url('thumbnail',i.path)}}" alt="Thumbnail for ${{esc(i.filename)}}" onerror="this.parentElement.classList.add('missing')"></div><div class="media-actions"><button onclick="preview(${{index}})">Preview file</button><button onclick="inspectQuality(${{index}})">Inspect quality</button></div><div class="quality">${{esc(i.quality)}} · ${{esc(i.size)}}</div></div><div><div class="top"><div><h2>${{esc(i.filename)}}</h2><div class="path">Originally: ${{esc(i.original_path)}}</div></div><span class="badge">Liner Notes Trash</span></div><p>This file is excluded from library scans and can still be recovered.</p><div class="right-actions"><button class="primary" onclick="restoreTrash(${{index}})">Restore</button><button class="danger" onclick="deleteTrash(${{index}})">Delete permanently</button></div></div></div></article>`}}
function activeCard(i){{const index=items.indexOf(i),id='i'+index;const conflict=i.status==='conflict'?`<div class="conflict">Multiple files share this destination. ${{i.recommended?'<span class="recommended">Recommended copy based on resolution and file size.</span>':''}} <button onclick="compareCopies(${{index}})">Compare copies</button> <button onclick="preferred(${{index}})">Keep this as preferred</button></div>`:'';return `<article id="${{id}}"><div class="card-layout"><div><div class="thumb"><img loading="lazy" src="${{url('thumbnail',i.path)}}" alt="Thumbnail for ${{esc(i.filename)}}" onerror="this.parentElement.classList.add('missing')"></div><div class="media-actions"><button onclick="preview(${{index}})">Preview file</button><button onclick="inspectQuality(${{index}})">Inspect quality</button></div><div class="quality">${{esc(i.quality)}} · ${{esc(i.size)}}</div></div><div><div class="top"><div><h2>${{esc(i.filename)}}</h2><div class="path">${{esc(i.path)}}</div></div><span class="badge ${{esc(i.status)}}">${{esc(i.status)}}</span></div>${{conflict}}<div class="grid"><label>Artist<input name="artist" value="${{esc(i.artist)}}"></label><label>Title<input name="title" value="${{esc(i.title)}}"></label><label>Featured artists<input name="featured" value="${{esc(i.featured_artists.join(', '))}}" placeholder="Separate names with commas"></label><label>Version<input name="versions" value="${{esc(i.versions.join(', '))}}" placeholder="Live, Remix, Acoustic…"></label><label>Year<input name="year" inputmode="numeric" value="${{esc(i.year??'')}}" placeholder="Optional"></label><label class="wide">Proposed destination<input value="${{esc(i.destination)}}" readonly></label></div><div class="actions"><span class="message">${{esc(i.notes.join(' · '))}}</span><div class="right-actions"><button onclick="searchMusicBrainz(${{index}})">Search MusicBrainz</button><button class="save" onclick="save(${{index}})">Save correction</button></div></div></div></div></article>`}}
function form(index){{const el=document.getElementById('i'+index),get=n=>el.querySelector(`[name=${{n}}]`).value;return {{el,get}}}}
async function save(index){{const f=form(index),button=f.el.querySelector('.save'),message=f.el.querySelector('.message'),year=f.get('year').trim();button.disabled=true;message.textContent='Saving…';try{{const d=await post('/api/overrides',{{path:items[index].path,override:{{artist:f.get('artist'),title:f.get('title'),featured_artists:split(f.get('featured')),versions:split(f.get('versions')),year:year?Number(year):null}}}});items[index]=d.item;render();}}catch(e){{message.textContent=e.message;button.disabled=false;}}}}
function preview(index){{activeIndex=index;document.querySelector('#modal-title').textContent=items[index].filename;document.querySelector('#modal-body').innerHTML=`<video controls autoplay src="${{url('media',items[index].path)}}"></video>`;document.querySelector('#modal').showModal();}}
async function inspectQuality(index){{const el=document.getElementById('i'+index),quality=el.querySelector('.quality');quality.textContent='Inspecting video…';try{{const r=await fetch('/api/quality?path='+encodeURIComponent(items[index].path));const d=await r.json();if(!r.ok)throw Error(d.error);quality.textContent=d.quality.label+' · '+items[index].size;}}catch(e){{quality.textContent=e.message;}}}}
async function compareCopies(index){{const paths=items[index].conflict_paths;window.compareItems=paths.map(path=>items.find(i=>i.path===path)).filter(Boolean);document.querySelector('#modal-title').textContent='Compare destination conflict';document.querySelector('#modal-body').innerHTML=`<p>Play the copies side by side, inspect their measured quality, then choose the copy that should keep the canonical filename. Other copies can be preserved as alternates or moved into recoverable Liner Notes Trash.</p><div class="compare-grid">${{window.compareItems.map((i,n)=>`<section class="compare-card ${{i.recommended?'recommended-copy':''}}"><video controls preload="metadata" poster="${{url('thumbnail',i.path)}}" src="${{url('media',i.path)}}"></video><h3>${{esc(i.filename)}}</h3><div class="compare-details" id="compare-quality-${{n}}">Inspecting… · ${{esc(i.size)}}${{i.recommended?' · Recommended':''}}</div><div class="right-actions"><button class="primary" onclick="chooseCompared(${{n}})">Choose this copy</button><button class="danger" onclick="trashCompared(${{n}})">Move to Liner Notes Trash</button></div></section>`).join('')}}</div>`;document.querySelector('#modal').showModal();await Promise.all(window.compareItems.map(async(i,n)=>{{try{{const r=await fetch('/api/quality?path='+encodeURIComponent(i.path)),d=await r.json();document.querySelector('#compare-quality-'+n).textContent=(r.ok?d.quality.label:d.error)+' · '+i.size+(i.recommended?' · Recommended':'');}}catch(e){{document.querySelector('#compare-quality-'+n).textContent=e.message+' · '+i.size;}}}}));}}
async function choosePreferredPath(path){{if(!confirm('Keep this copy as canonical and preserve the others as labeled alternates?'))return;try{{await post('/api/preferred',{{path}});const modal=document.querySelector('#modal');if(modal.open)closeModal();await load();}}catch(e){{alert(e.message);}}}}
function preferred(index){{return choosePreferredPath(items[index].path)}}
function chooseCompared(index){{return choosePreferredPath(window.compareItems[index].path)}}
async function trashCompared(index){{const item=window.compareItems[index],confirmation=prompt(`Move "${{item.filename}}" into recoverable Liner Notes Trash? Type TRASH_FILE to continue.`);if(confirmation===null)return;try{{const d=await post('/api/trash',{{path:item.path,confirmation}});closeModal();alert(`Moved to ${{d.trash.destination}}. You can recover it from Liner Notes Trash.`);await load();}}catch(e){{alert(e.message);}}}}
async function restoreTrash(index){{const item=items[index],confirmation=prompt(`Restore "${{item.filename}}" to ${{item.original_path}}? Type RESTORE_FILE to continue.`);if(confirmation===null)return;try{{const d=await post('/api/restore-trash',{{path:item.path,confirmation}});alert(`Restored to ${{d.restore.destination}}.`);await load();}}catch(e){{alert(e.message);}}}}
async function deleteTrash(index){{const item=items[index],confirmation=prompt(`Permanently delete "${{item.filename}}"? This cannot be undone. Type DELETE_FOREVER to continue.`);if(confirmation===null)return;try{{const d=await post('/api/delete-trash',{{path:item.path,confirmation}});alert(`Permanently deleted ${{d.delete.size}}.`);await load();}}catch(e){{alert(e.message);}}}}
async function emptyTrash(){{const confirmation=prompt(`Permanently delete all ${{items.length}} video files in Liner Notes Trash? This cannot be undone. Type EMPTY_LINER_NOTES_TRASH to continue.`);if(confirmation===null)return;try{{const d=await post('/api/empty-trash',{{confirmation}}),result=d.empty;alert(`Permanently deleted ${{result.deleted}} files (${{result.size}}).${{result.errors.length?' Some files failed: '+result.errors.join(' | '):''}}`);await load();}}catch(e){{alert(e.message);}}}}
async function searchMusicBrainz(index){{activeIndex=index;const f=form(index);document.querySelector('#modal-title').textContent='MusicBrainz results';document.querySelector('#modal-body').innerHTML='<p>Searching MusicBrainz…</p>';document.querySelector('#modal').showModal();try{{const d=await post('/api/search',{{artist:f.get('artist'),title:f.get('title')}});document.querySelector('#modal-body').innerHTML=d.candidates.length?d.candidates.map((c,n)=>`<div class="candidate"><div><strong>${{esc(c.artist)}} — ${{esc(c.title)}}</strong><br><span class="message">${{c.year??'Year unknown'}} · Match score ${{c.score}}</span></div><button onclick="useCandidate(${{n}})">Use this match</button></div>`).join(''):'<p>No MusicBrainz matches found.</p>';window.searchResults=d.candidates;}}catch(e){{document.querySelector('#modal-body').innerHTML='<p>'+esc(e.message)+'</p>';}}}}
function useCandidate(n){{const c=window.searchResults[n],f=form(activeIndex);f.el.querySelector('[name=artist]').value=c.artist;f.el.querySelector('[name=title]').value=c.title;if(c.year)f.el.querySelector('[name=year]').value=c.year;closeModal();}}
function closeModal(){{const modal=document.querySelector('#modal');modal.querySelectorAll('video').forEach(video=>{{video.pause();video.removeAttribute('src');}});modal.close();}}
async function commitSaved(){{const confirmation=prompt('This moves only saved, ready corrections and never overwrites files. Type MOVE_FILES to continue.');if(confirmation===null)return;try{{const d=await post('/api/commit',{{confirmation}}),x=d.execution,audit=x.report?` Audit: ${{x.report}}`:` Audit report error: ${{x.report_error}}`;alert(`Completed: ${{x.moved}} moved, ${{x.unchanged}} unchanged, ${{x.failed}} failed.${{audit}}`);await load();}}catch(e){{alert(e.message);}}}}
document.querySelector('#search').addEventListener('input',render);
document.querySelectorAll('[data-filter]').forEach(b=>b.onclick=()=>{{filter=b.dataset.filter;document.querySelectorAll('[data-filter]').forEach(x=>x.classList.toggle('active',x===b));render();}});
document.querySelectorAll('[data-scope]').forEach(b=>b.onclick=()=>{{document.querySelectorAll('[data-scope]').forEach(x=>x.classList.toggle('active',x===b));load(b.dataset.scope).catch(e=>document.querySelector('#summary').textContent=e.message);}});
load().catch(e=>document.querySelector('#summary').textContent=e.message);
</script></body></html>'''
