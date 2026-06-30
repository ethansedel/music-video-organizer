"""Standalone HTML reporting for analyzed music-video libraries."""

from __future__ import annotations

from html import escape
from pathlib import Path

from mvo.models import AnalysisResult, AnalyzedVideo, ConfidenceLevel


def render_html(result: AnalysisResult) -> str:
    """Render an escaped, portable HTML report."""

    counts = {
        level: sum(video.parsed.confidence.level is level for video in result.videos)
        for level in ConfidenceLevel
    }
    rows = "\n".join(_render_video_row(video) for video in result.videos)
    if not rows:
        rows = '<tr><td colspan="8" class="empty">No video files found.</td></tr>'
    issues = "".join(
        f"<li><code>{escape(str(issue.path))}</code>: {escape(issue.message)}</li>"
        for issue in result.issues
    )
    issue_section = (
        f"<section><h2>Scan issues</h2><ul>{issues}</ul></section>" if issues else ""
    )
    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Liner Notes report</title>
  <style>
    :root {{ color-scheme: light dark; font-family: system-ui, sans-serif; }}
    body {{ margin: 0 auto; max-width: 96rem; padding: 2rem; }}
    header {{ display: flex; flex-wrap: wrap; gap: 1rem; align-items: end; }}
    header h1 {{ margin: 0; flex: 1 1 30rem; }}
    .summary {{ display: flex; gap: .75rem; flex-wrap: wrap; margin: 1.5rem 0; }}
    .card {{ border: 1px solid #8886; border-radius: .6rem; padding: .8rem 1rem; }}
    table {{ border-collapse: collapse; width: 100%; }}
    th, td {{ border-bottom: 1px solid #8885; padding: .65rem; text-align: left; }}
    th {{ position: sticky; top: 0; background: Canvas; }}
    .confidence {{ font-weight: 700; text-transform: capitalize; }}
    .high {{ color: #16803a; }} .medium {{ color: #a46400; }} .low {{ color: #b42318; }}
    .empty {{ text-align: center; padding: 3rem; }}
    code {{ overflow-wrap: anywhere; }}
  </style>
</head>
<body>
  <header>
    <h1>Liner Notes</h1>
    <div><strong>Library:</strong> <code>{escape(str(result.root))}</code></div>
  </header>
  <section class="summary" aria-label="Summary">
    <div class="card"><strong>{len(result.videos)}</strong> videos</div>
    <div class="card high">
      <strong>{counts[ConfidenceLevel.HIGH]}</strong> high confidence
    </div>
    <div class="card medium">
      <strong>{counts[ConfidenceLevel.MEDIUM]}</strong> medium
    </div>
    <div class="card low">
      <strong>{counts[ConfidenceLevel.LOW]}</strong> needs review
    </div>
  </section>
  <table>
    <thead><tr><th>File</th><th>Artist</th><th>Title</th><th>Featuring</th><th>Version</th><th>Year</th><th>Size</th><th>Confidence</th></tr></thead>
    <tbody>{rows}</tbody>
  </table>
  {issue_section}
</body>
</html>
"""


def write_html_report(result: AnalysisResult, output: str | Path) -> Path:
    """Write the report to the exact user-selected path and return that path."""

    destination = Path(output).expanduser().resolve()
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(render_html(result), encoding="utf-8")
    return destination


def _render_video_row(video: AnalyzedVideo) -> str:
    parsed = video.parsed
    level = parsed.confidence.level.value
    reasons = escape("; ".join(parsed.confidence.reasons))
    return "".join(
        (
            "<tr>",
            f"<td><code>{escape(video.source.relative_path.as_posix())}</code></td>",
            f"<td>{escape(parsed.artist or '—')}</td>",
            f"<td>{escape(parsed.title)}</td>",
            f"<td>{escape(', '.join(parsed.featured_artists) or '—')}</td>",
            f"<td>{escape(', '.join(parsed.versions) or '—')}</td>",
            f"<td>{parsed.year or '—'}</td>",
            f"<td>{_format_size(video.source.size_bytes)}</td>",
            f'<td class="confidence {level}" title="{reasons}">'
            f"{level} ({parsed.confidence.score:.0%})</td>",
            "</tr>",
        )
    )


def _format_size(size_bytes: int) -> str:
    value = float(size_bytes)
    for unit in ("B", "KiB", "MiB", "GiB", "TiB"):
        if value < 1024 or unit == "TiB":
            return f"{value:.0f} {unit}" if unit == "B" else f"{value:.1f} {unit}"
        value /= 1024
    raise AssertionError("unreachable")
