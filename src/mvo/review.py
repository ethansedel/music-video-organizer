# ruff: noqa: E501
"""Local-only web editor for videos that need metadata review."""

from __future__ import annotations

import json
import secrets
import webbrowser
from dataclasses import replace
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any
from urllib.parse import urlsplit

from mvo.models import AnalysisResult, PlanStatus
from mvo.overrides import MetadataOverride, MetadataOverrideStore
from mvo.planner import FolderPlanner


class ReviewSession:
    """Coordinate editable overrides with fresh, read-only planning results."""

    def __init__(
        self,
        analysis: AnalysisResult,
        store: MetadataOverrideStore,
        planner: FolderPlanner | None = None,
    ) -> None:
        self.analysis = analysis
        self.store = store
        self.planner = planner or FolderPlanner()
        self.overrides = store.load()
        initial = self.planner.plan(analysis)
        scanned_paths = {
            video.source.relative_path.as_posix() for video in analysis.videos
        }
        self.review_paths = {
            item.video.source.relative_path.as_posix()
            for item in initial.items
            if item.status is not PlanStatus.READY
        } | (self.overrides.keys() & scanned_paths)

    def items(self) -> list[dict[str, object]]:
        """Return current editable fields and recomputed plan status."""

        current = self._current_analysis()
        plan = self.planner.plan(current)
        items: list[dict[str, object]] = []
        for planned in plan.items:
            path = planned.video.source.relative_path.as_posix()
            if path not in self.review_paths:
                continue
            parsed = planned.video.parsed
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
                    "status": (
                        "resolved"
                        if planned.status is PlanStatus.READY
                        else planned.status.value
                    ),
                    "notes": list(planned.notes),
                    "saved": path in self.overrides,
                }
            )
        return items

    def update(self, path: object, value: object) -> dict[str, object]:
        """Validate, persist, and return one edited review item."""

        if not isinstance(path, str) or path not in self.review_paths:
            raise ValueError("video is not part of this review session")
        override = MetadataOverride.from_dict(value)
        updated = {**self.overrides, path: override}
        self.store.save(updated)
        self.overrides = updated
        return next(item for item in self.items() if item["path"] == path)

    def _current_analysis(self) -> AnalysisResult:
        videos = tuple(
            replace(video, parsed=self.overrides[path].apply(video.parsed))
            if (path := video.source.relative_path.as_posix()) in self.overrides
            else video
            for video in self.analysis.videos
        )
        return replace(self.analysis, videos=videos)


def serve_review(
    session: ReviewSession,
    *,
    port: int = 8765,
    open_browser: bool = True,
) -> None:
    """Serve the review GUI on loopback until interrupted by the user."""

    token = secrets.token_urlsafe(24)
    handler = _handler_for(session, token)
    server = ThreadingHTTPServer(("127.0.0.1", port), handler)
    url = f"http://127.0.0.1:{server.server_port}/"
    print(f"Reviewing {len(session.review_paths)} video(s) at {url}")
    print(f"Corrections file: {session.store.path}")
    print("Press Control-C when you are finished.")
    if open_browser:
        webbrowser.open(url)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nReview editor stopped.")
    finally:
        server.server_close()


def _handler_for(
    session: ReviewSession, token: str
) -> type[BaseHTTPRequestHandler]:
    class ReviewHandler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:  # noqa: N802
            path = urlsplit(self.path).path
            if path == "/":
                self._send_bytes(
                    HTTPStatus.OK,
                    _page(token).encode(),
                    "text/html; charset=utf-8",
                )
            elif path == "/api/items":
                self._send_json(HTTPStatus.OK, {"items": session.items()})
            else:
                self._send_json(HTTPStatus.NOT_FOUND, {"error": "not found"})

        def do_POST(self) -> None:  # noqa: N802
            if urlsplit(self.path).path != "/api/overrides":
                self._send_json(HTTPStatus.NOT_FOUND, {"error": "not found"})
                return
            if self.headers.get("X-MVO-Token") != token:
                self._send_json(HTTPStatus.FORBIDDEN, {"error": "invalid token"})
                return
            try:
                length = int(self.headers.get("Content-Length", "0"))
                if length <= 0 or length > 64 * 1024:
                    raise ValueError("request body has an invalid size")
                payload = json.loads(self.rfile.read(length))
                if not isinstance(payload, dict):
                    raise ValueError("request body must be an object")
                item = session.update(payload.get("path"), payload.get("override"))
            except (ValueError, json.JSONDecodeError) as error:
                self._send_json(HTTPStatus.BAD_REQUEST, {"error": str(error)})
                return
            self._send_json(HTTPStatus.OK, {"item": item})

        def log_message(self, _format: str, *_args: Any) -> None:
            return

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

    return ReviewHandler


def _page(token: str) -> str:
    """Return the self-contained review application."""

    safe_token = json.dumps(token)
    return f'''<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>MVO Review</title><style>
:root{{--ink:#16201c;--muted:#607068;--paper:#f5f2e9;--card:#fffdf7;--accent:#176b55;--accent2:#d8eee5;--warn:#a54d2d;--line:#d8ddd7}}
*{{box-sizing:border-box}}body{{margin:0;background:var(--paper);color:var(--ink);font:16px/1.45 system-ui,sans-serif}}
header{{padding:38px max(24px,calc((100vw - 1120px)/2));background:#173b32;color:white}}h1{{margin:0 0 6px;font-size:clamp(28px,4vw,46px)}}header p{{margin:0;color:#cae0d8}}
main{{max-width:1120px;margin:auto;padding:24px}}.toolbar{{display:flex;gap:12px;flex-wrap:wrap;margin-bottom:18px}}input,button{{font:inherit}}input{{width:100%;padding:10px;border:1px solid var(--line);border-radius:8px;background:white}}#search{{flex:1;min-width:240px}}
.filters{{display:flex;gap:6px}}button{{border:0;border-radius:8px;padding:10px 14px;cursor:pointer}}.filters button{{background:#e4e7e2}}.filters button.active,.save{{background:var(--accent);color:white}}
.summary{{color:var(--muted);margin:10px 0 18px}}.list{{display:grid;gap:16px}}article{{background:var(--card);border:1px solid var(--line);border-radius:14px;padding:18px;box-shadow:0 4px 16px #1833290b}}
.top{{display:flex;justify-content:space-between;gap:12px;align-items:start}}h2{{font-size:17px;margin:0;overflow-wrap:anywhere}}.badge{{border-radius:999px;padding:5px 9px;font-size:12px;font-weight:700;background:#f4dfd7;color:var(--warn)}}.badge.resolved{{background:var(--accent2);color:var(--accent)}}
.path,.destination{{font-size:13px;color:var(--muted);overflow-wrap:anywhere}}.grid{{display:grid;grid-template-columns:1fr 1fr;gap:12px;margin-top:15px}}label{{font-size:13px;font-weight:700}}label input{{margin-top:5px;font-weight:400}}.wide{{grid-column:1/-1}}.actions{{display:flex;align-items:center;justify-content:space-between;margin-top:14px}}.message{{font-size:13px;color:var(--muted)}}.empty{{padding:50px;text-align:center;color:var(--muted)}}
@media(max-width:650px){{.grid{{grid-template-columns:1fr}}.wide{{grid-column:auto}}}}
</style></head><body><header><h1>Skipped video review</h1><p>Correct metadata here. Video files remain untouched until a confirmed execution.</p></header>
<main><div class="toolbar"><input id="search" type="search" placeholder="Search filenames, artists, or titles"><div class="filters"><button data-filter="all" class="active">All</button><button data-filter="open">Needs review</button><button data-filter="resolved">Resolved</button></div></div><div class="summary" id="summary">Loading…</div><section class="list" id="list"></section></main>
<script>
const token={safe_token};let items=[];let filter='all';
const esc=s=>String(s??'').replace(/[&<>"']/g,c=>({{'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}}[c]));
const split=s=>s.split(',').map(x=>x.trim()).filter(Boolean);
function visible(i){{const q=document.querySelector('#search').value.toLowerCase();const match=!q||[i.filename,i.artist,i.title,i.path].join(' ').toLowerCase().includes(q);return match&&(filter==='all'||(filter==='resolved')===(i.status==='resolved'));}}
function render(){{const shown=items.filter(visible);const resolved=items.filter(i=>i.status==='resolved').length;document.querySelector('#summary').textContent=`${{items.length}} skipped videos · ${{resolved}} resolved · ${{items.length-resolved}} still need review`;document.querySelector('#list').innerHTML=shown.length?shown.map(card).join(''):'<div class="empty">No videos match this view.</div>';}}
function card(i){{const id='i'+items.indexOf(i);return `<article id="${{id}}"><div class="top"><div><h2>${{esc(i.filename)}}</h2><div class="path">${{esc(i.path)}}</div></div><span class="badge ${{i.status==='resolved'?'resolved':''}}">${{esc(i.status==='resolved'?'Ready':i.status)}}</span></div><div class="grid"><label>Artist<input name="artist" value="${{esc(i.artist)}}"></label><label>Title<input name="title" value="${{esc(i.title)}}"></label><label>Featured artists<input name="featured" value="${{esc(i.featured_artists.join(', '))}}" placeholder="Separate multiple names with commas"></label><label>Version<input name="versions" value="${{esc(i.versions.join(', '))}}" placeholder="Live, Remix, Acoustic…"></label><label>Year<input name="year" inputmode="numeric" value="${{esc(i.year??'')}}" placeholder="Optional"></label><label class="wide">Proposed destination<input value="${{esc(i.destination)}}" readonly></label></div><div class="actions"><span class="message">${{esc(i.notes.join(' · '))}}</span><button class="save" onclick="save(${{items.indexOf(i)}},'${{id}}')">Save correction</button></div></article>`}}
async function save(index,id){{const el=document.getElementById(id),button=el.querySelector('.save'),message=el.querySelector('.message');button.disabled=true;message.textContent='Saving…';const get=n=>el.querySelector(`[name=${{n}}]`).value;const year=get('year').trim();const body={{path:items[index].path,override:{{artist:get('artist'),title:get('title'),featured_artists:split(get('featured')),versions:split(get('versions')),year:year?Number(year):null}}}};try{{const response=await fetch('/api/overrides',{{method:'POST',headers:{{'Content-Type':'application/json','X-MVO-Token':token}},body:JSON.stringify(body)}});const data=await response.json();if(!response.ok)throw Error(data.error);items[index]=data.item;render();}}catch(e){{message.textContent=e.message;button.disabled=false;}}}}
document.querySelector('#search').addEventListener('input',render);document.querySelectorAll('[data-filter]').forEach(b=>b.onclick=()=>{{filter=b.dataset.filter;document.querySelectorAll('[data-filter]').forEach(x=>x.classList.toggle('active',x===b));render();}});
fetch('/api/items').then(r=>r.json()).then(d=>{{items=d.items;render();}}).catch(e=>document.querySelector('#summary').textContent=e.message);
</script></body></html>'''
