"""HTML report for opt-in MusicBrainz filename enrichment."""

from __future__ import annotations

from html import escape
from pathlib import Path

from mvo.models import EnrichedVideo, EnrichmentResult, MatchStatus


def render_enrichment_html(result: EnrichmentResult) -> str:
    """Render candidate matches without changing media metadata."""

    counts = {
        status: sum(item.status is status for item in result.items)
        for status in MatchStatus
    }
    rows = "\n".join(_render_row(item) for item in result.items)
    if not rows:
        rows = '<tr><td colspan="7">No video files found.</td></tr>'
    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Liner Notes MusicBrainz report</title>
  <style>
    :root {{ color-scheme: light dark; font-family: system-ui, sans-serif; }}
    body {{ margin: 0 auto; max-width: 110rem; padding: 2rem; }}
    .notice {{ border: 2px solid #2878bd; border-radius: .6rem; padding: 1rem; }}
    .summary {{ display: flex; gap: .75rem; flex-wrap: wrap; margin: 1.5rem 0; }}
    .card {{ border: 1px solid #8886; border-radius: .6rem; padding: .8rem 1rem; }}
    table {{ border-collapse: collapse; width: 100%; }}
    th, td {{ border-bottom: 1px solid #8885; padding: .65rem; text-align: left; }}
    th {{ position: sticky; top: 0; background: Canvas; }}
    .status {{ font-weight: 700; }} .matched {{ color: #16803a; }}
    .review, .not-found {{ color: #a46400; }} .error {{ color: #b42318; }}
    code {{ overflow-wrap: anywhere; }}
  </style>
</head>
<body>
  <h1>MusicBrainz enrichment</h1>
  <p class="notice"><strong>Read-only and opt-in.</strong> This report searched
  parsed artist/title text. It did not upload audio, write tags, or modify media.</p>
  <p><strong>Library:</strong> <code>{escape(str(result.root))}</code></p>
  <section class="summary" aria-label="Summary">
    <div class="card"><strong>{result.query_count}</strong> API queries</div>
    <div class="card matched">
      <strong>{counts[MatchStatus.MATCHED]}</strong> matched
    </div>
    <div class="card review"><strong>{counts[MatchStatus.REVIEW]}</strong> review</div>
    <div class="card not-found">
      <strong>{counts[MatchStatus.NOT_FOUND]}</strong> not found
    </div>
    <div class="card error"><strong>{counts[MatchStatus.ERROR]}</strong> errors</div>
    <div class="card"><strong>{counts[MatchStatus.SKIPPED]}</strong> skipped</div>
  </section>
  <table>
    <thead><tr><th>File</th><th>Parsed artist</th><th>Parsed title</th>
    <th>Status</th><th>MusicBrainz candidate</th><th>Score</th>
    <th>Message</th></tr></thead>
    <tbody>{rows}</tbody>
  </table>
</body>
</html>
"""


def write_enrichment_report(result: EnrichmentResult, output: str | Path) -> Path:
    """Write the enrichment report to the selected path."""

    destination = Path(output).expanduser().resolve()
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(render_enrichment_html(result), encoding="utf-8")
    return destination


def _render_row(item: EnrichedVideo) -> str:
    parsed = item.video.parsed
    candidate = item.candidates[0] if item.candidates else None
    if candidate:
        url = f"https://musicbrainz.org/recording/{candidate.recording_id}"
        candidate_cell = (
            f'<a href="{escape(url)}">{escape(candidate.artist_credit)} — '
            f"{escape(candidate.title)}</a>"
        )
        score = str(candidate.score)
    else:
        candidate_cell = "—"
        score = "—"
    status = item.status.value
    status_class = status.replace(" ", "-")
    return "".join(
        (
            "<tr>",
            f"<td><code>{escape(item.video.source.relative_path.as_posix())}</code></td>",
            f"<td>{escape(parsed.artist or '—')}</td>",
            f"<td>{escape(parsed.title)}</td>",
            f'<td class="status {status_class}">{escape(status)}</td>',
            f"<td>{candidate_cell}</td><td>{score}</td>",
            f"<td>{escape(item.message)}</td>",
            "</tr>",
        )
    )
