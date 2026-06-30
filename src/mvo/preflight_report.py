"""Standalone HTML reporting for read-only execution preflights."""

from __future__ import annotations

from html import escape
from pathlib import Path

from mvo.models import PreflightItem, PreflightResult, PreflightStatus


def render_preflight_html(result: PreflightResult) -> str:
    """Render an escaped report that contains no execution controls."""

    counts = {
        status: sum(item.status is status for item in result.items)
        for status in PreflightStatus
    }
    rows = "\n".join(_render_row(item) for item in result.items)
    if not rows:
        rows = '<tr><td colspan="5" class="empty">No video files found.</td></tr>'
    issues = "".join(
        f"<li><code>{escape(str(issue.path))}</code>: {escape(issue.message)}</li>"
        for issue in result.issues
    )
    issue_section = (
        f"<section><h2>Scan issues</h2><ul>{issues}</ul></section>" if issues else ""
    )
    verdict = "No known blockers" if result.safe_to_execute else "Not ready"
    verdict_class = "ready" if result.safe_to_execute else "blocked"
    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Liner Notes preflight</title>
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
    .ready {{ color: #16803a; }} .unchanged {{ color: #2878bd; }}
    .blocked {{ color: #b42318; }}
    .empty {{ text-align: center; padding: 3rem; }}
    code {{ overflow-wrap: anywhere; }}
  </style>
</head>
<body>
  <h1>Liner Notes preflight</h1>
  <p class="notice"><strong>Safety snapshot only.</strong> This report does not
  rename, move, delete, or otherwise modify media.</p>
  <p><strong>Library:</strong> <code>{escape(str(result.root))}</code></p>
  <section class="summary" aria-label="Summary">
    <div class="card {verdict_class}"><strong>{verdict}</strong></div>
    <div class="card ready"><strong>{counts[PreflightStatus.READY]}</strong> ready</div>
    <div class="card unchanged">
      <strong>{counts[PreflightStatus.UNCHANGED]}</strong> unchanged
    </div>
    <div class="card blocked">
      <strong>{counts[PreflightStatus.BLOCKED]}</strong> blocked
    </div>
  </section>
  <p>Results are valid only for this scan. A future execution mode must check
  every condition again immediately before touching a file.</p>
  <table>
    <thead><tr>
      <th>Current path</th><th>Proposed path</th><th>Preflight</th>
      <th>Plan status</th><th>Checks</th>
    </tr></thead>
    <tbody>{rows}</tbody>
  </table>
  {issue_section}
</body>
</html>
"""


def write_preflight_report(result: PreflightResult, output: str | Path) -> Path:
    """Write a preflight report to the exact user-selected destination."""

    destination = Path(output).expanduser().resolve()
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(render_preflight_html(result), encoding="utf-8")
    return destination


def _render_row(item: PreflightItem) -> str:
    planned = item.planned
    status = item.status.value
    return "".join(
        (
            "<tr>",
            f"<td><code>{escape(planned.video.source.relative_path.as_posix())}</code></td>",
            f"<td><code>{escape(planned.destination.as_posix())}</code></td>",
            f'<td class="status {status}">{status}</td>',
            f"<td>{planned.status.value}</td>",
            f"<td>{escape('; '.join(item.checks))}</td>",
            "</tr>",
        )
    )
