"""HTML preview report for remote Cover Art Archive metadata."""

from __future__ import annotations

from html import escape
from pathlib import Path

from mvo.models import ArtworkPreview, ArtworkResult, ArtworkStatus


def render_artwork_html(result: ArtworkResult) -> str:
    """Render lazy remote thumbnails without writing artwork files."""

    counts = {
        status: sum(item.status is status for item in result.items)
        for status in ArtworkStatus
    }
    cards = "\n".join(_render_item(item) for item in result.items)
    if not cards:
        cards = '<p class="empty">No video files found.</p>'
    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Liner Notes artwork preview</title>
  <style>
    :root {{ color-scheme: light dark; font-family: system-ui, sans-serif; }}
    body {{ margin: 0 auto; max-width: 110rem; padding: 2rem; }}
    .notice {{ border: 2px solid #2878bd; border-radius: .6rem; padding: 1rem; }}
    .summary {{ display: flex; gap: .75rem; flex-wrap: wrap; margin: 1.5rem 0; }}
    .stat, .item {{ border: 1px solid #8886; border-radius: .6rem; padding: 1rem; }}
    .grid {{ display: grid; gap: 1rem;
      grid-template-columns: repeat(auto-fill, minmax(20rem, 1fr)); }}
    .item {{ display: grid; gap: .75rem; align-content: start; }}
    .item h2 {{ font-size: 1rem; margin: 0; overflow-wrap: anywhere; }}
    .art {{ width: 100%; aspect-ratio: 1; object-fit: contain; background: #8882; }}
    .status {{ font-weight: 700; }} .found {{ color: #16803a; }}
    .review, .not-found {{ color: #a46400; }} .error {{ color: #b42318; }}
    code {{ overflow-wrap: anywhere; }}
  </style>
</head>
<body>
  <h1>Artwork preview</h1>
  <p class="notice"><strong>Remote preview only.</strong>
  Liner Notes did not download or save artwork beside media. This report loads lazy
  thumbnails directly from the Cover Art Archive or Internet Archive.</p>
  <p><strong>Library:</strong> <code>{escape(str(result.root))}</code></p>
  <section class="summary" aria-label="Summary">
    <div class="stat">
      <strong>{result.musicbrainz_queries}</strong> MusicBrainz queries
    </div>
    <div class="stat"><strong>{result.cover_art_queries}</strong> artwork queries</div>
    <div class="stat found"><strong>{counts[ArtworkStatus.FOUND]}</strong> found</div>
    <div class="stat review">
      <strong>{counts[ArtworkStatus.REVIEW]}</strong> review
    </div>
    <div class="stat error"><strong>{counts[ArtworkStatus.ERROR]}</strong> errors</div>
    <div class="stat"><strong>{counts[ArtworkStatus.SKIPPED]}</strong> skipped</div>
  </section>
  <main class="grid">{cards}</main>
</body>
</html>
"""


def write_artwork_report(result: ArtworkResult, output: str | Path) -> Path:
    """Write an artwork preview report to the selected path."""

    destination = Path(output).expanduser().resolve()
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(render_artwork_html(result), encoding="utf-8")
    return destination


def _render_item(item: ArtworkPreview) -> str:
    parsed = item.video.parsed
    status = item.status.value
    status_class = status.replace(" ", "-")
    release_group = item.release_group
    group_text = release_group.title if release_group else "—"
    image = item.images[0] if item.images else None
    if image:
        thumbnail = image.thumbnail_250 or image.thumbnail_500 or image.image_url
        image_html = (
            f'<a href="{escape(image.image_url)}">'
            f'<img class="art" src="{escape(thumbnail)}" loading="lazy" '
            'referrerpolicy="no-referrer" alt="Remote cover art preview"></a>'
        )
    else:
        image_html = '<div class="art" aria-label="No artwork"></div>'
    return "".join(
        (
            '<article class="item">',
            f"<h2>{escape(item.video.source.relative_path.as_posix())}</h2>",
            image_html,
            f"<div>{escape(parsed.artist or '—')} — {escape(parsed.title)}</div>",
            f"<div><strong>Release group:</strong> {escape(group_text)}</div>",
            f'<div class="status {status_class}">{escape(status)}</div>',
            f"<div>{escape(item.message)}</div>",
            "</article>",
        )
    )
