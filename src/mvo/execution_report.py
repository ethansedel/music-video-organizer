"""HTML audit reporting for explicitly confirmed organization runs."""

from __future__ import annotations

from html import escape
from pathlib import Path

from mvo.models import ExecutionItem, ExecutionResult, ExecutionStatus


def render_execution_html(result: ExecutionResult) -> str:
    """Render a complete escaped execution audit."""

    counts = {
        status: sum(item.status is status for item in result.items)
        for status in ExecutionStatus
    }
    rows = "\n".join(_render_row(item) for item in result.items)
    if not rows:
        rows = '<tr><td colspan="5" class="empty">No video files found.</td></tr>'
    if result.rolled_back and not result.rollback_complete:
        headline = "Execution stopped; rollback incomplete"
    elif result.rolled_back:
        headline = "Execution rolled back"
    else:
        headline = "Execution completed"
    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Music Video Organizer execution audit</title>
  <style>
    :root {{ color-scheme: light dark; font-family: system-ui, sans-serif; }}
    body {{ margin: 0 auto; max-width: 110rem; padding: 2rem; }}
    .notice {{ border: 2px solid #2878bd; border-radius: .6rem; padding: 1rem; }}
    .summary {{ display: flex; gap: .75rem; flex-wrap: wrap; margin: 1.5rem 0; }}
    .card {{ border: 1px solid #8886; border-radius: .6rem; padding: .8rem 1rem; }}
    table {{ border-collapse: collapse; width: 100%; }}
    th, td {{ border-bottom: 1px solid #8885; padding: .65rem; text-align: left; }}
    th {{ position: sticky; top: 0; background: Canvas; }}
    .status {{ font-weight: 700; text-transform: capitalize; }}
    .moved {{ color: #16803a; }} .unchanged, .skipped {{ color: #58606b; }}
    .failed {{ color: #b42318; }} .rolled-back {{ color: #a46400; }}
    .empty {{ text-align: center; padding: 3rem; }}
    code {{ overflow-wrap: anywhere; }}
  </style>
</head>
<body>
  <h1>{headline}</h1>
  <p class="notice">MVO never overwrites destination files. Any failure stops
  later moves and triggers rollback of moves completed by this run.</p>
  <p><strong>Library:</strong> <code>{escape(str(result.root))}</code></p>
  <section class="summary" aria-label="Summary">
    <div class="card moved"><strong>{counts[ExecutionStatus.MOVED]}</strong> moved</div>
    <div class="card unchanged">
      <strong>{counts[ExecutionStatus.UNCHANGED]}</strong> unchanged
    </div>
    <div class="card skipped">
      <strong>{counts[ExecutionStatus.SKIPPED]}</strong> skipped
    </div>
    <div class="card failed">
      <strong>{counts[ExecutionStatus.FAILED]}</strong> failed
    </div>
    <div class="card rolled-back">
      <strong>{counts[ExecutionStatus.ROLLED_BACK]}</strong> rolled back
    </div>
  </section>
  <table>
    <thead><tr>
      <th>Original path</th><th>Destination</th><th>Outcome</th>
      <th>Artist — title</th><th>Message</th>
    </tr></thead>
    <tbody>{rows}</tbody>
  </table>
</body>
</html>
"""


def write_execution_report(result: ExecutionResult, output: str | Path) -> Path:
    """Write the execution audit to the exact selected destination."""

    destination = Path(output).expanduser().resolve()
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(render_execution_html(result), encoding="utf-8")
    return destination


def _render_row(item: ExecutionItem) -> str:
    planned = item.planned
    parsed = planned.video.parsed
    status = item.status.value
    css_status = status.replace(" ", "-")
    identity = f"{parsed.artist or 'Unknown Artist'} — {parsed.title}"
    return "".join(
        (
            "<tr>",
            f"<td><code>{escape(planned.video.source.relative_path.as_posix())}</code></td>",
            f"<td><code>{escape(planned.destination.as_posix())}</code></td>",
            f'<td class="status {css_status}">{status}</td>',
            f"<td>{escape(identity)}</td>",
            f"<td>{escape(item.message)}</td>",
            "</tr>",
        )
    )
