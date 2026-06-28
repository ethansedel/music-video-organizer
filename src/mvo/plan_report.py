"""Standalone HTML reporting for read-only organization plans."""

from __future__ import annotations

from html import escape
from pathlib import Path

from mvo.models import OrganizationPlan, PlannedVideo, PlanStatus


def render_plan_html(plan: OrganizationPlan) -> str:
    """Render an escaped dry-run report with no execution controls."""

    counts = {
        status: sum(item.status is status for item in plan.items)
        for status in PlanStatus
    }
    rows = "\n".join(_render_plan_row(item) for item in plan.items)
    if not rows:
        rows = '<tr><td colspan="7" class="empty">No video files found.</td></tr>'
    issues = "".join(
        f"<li><code>{escape(str(issue.path))}</code>: {escape(issue.message)}</li>"
        for issue in plan.issues
    )
    issue_section = (
        f"<section><h2>Scan issues</h2><ul>{issues}</ul></section>" if issues else ""
    )
    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Music Video Organizer dry-run plan</title>
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
    .ready {{ color: #16803a; }} .review {{ color: #a46400; }}
    .conflict {{ color: #b42318; }}
    .empty {{ text-align: center; padding: 3rem; }}
    code {{ overflow-wrap: anywhere; }}
  </style>
</head>
<body>
  <h1>Music Video Organizer dry-run</h1>
  <p class="notice"><strong>Preview only.</strong> No media has been renamed,
  moved, deleted, or otherwise modified.</p>
  <p><strong>Library:</strong> <code>{escape(str(plan.root))}</code></p>
  <section class="summary" aria-label="Summary">
    <div class="card"><strong>{len(plan.items)}</strong> videos</div>
    <div class="card ready"><strong>{counts[PlanStatus.READY]}</strong> ready</div>
    <div class="card review"><strong>{counts[PlanStatus.REVIEW]}</strong> review</div>
    <div class="card conflict">
      <strong>{counts[PlanStatus.CONFLICT]}</strong> conflicts
    </div>
  </section>
  <table>
    <thead><tr>
      <th>Current path</th><th>Proposed path</th><th>Status</th>
      <th>Artist</th><th>Title</th><th>Confidence</th><th>Notes</th>
    </tr></thead>
    <tbody>{rows}</tbody>
  </table>
  {issue_section}
</body>
</html>
"""


def write_plan_report(plan: OrganizationPlan, output: str | Path) -> Path:
    """Write a dry-run report to the exact user-selected destination."""

    destination = Path(output).expanduser().resolve()
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(render_plan_html(plan), encoding="utf-8")
    return destination


def _render_plan_row(item: PlannedVideo) -> str:
    parsed = item.video.parsed
    status = item.status.value
    return "".join(
        (
            "<tr>",
            f"<td><code>{escape(item.video.source.relative_path.as_posix())}</code></td>",
            f"<td><code>{escape(item.destination.as_posix())}</code></td>",
            f'<td class="status {status}">{status}</td>',
            f"<td>{escape(parsed.artist or '—')}</td>",
            f"<td>{escape(parsed.title)}</td>",
            f"<td>{parsed.confidence.score:.0%}</td>",
            f"<td>{escape('; '.join(item.notes) or '—')}</td>",
            "</tr>",
        )
    )
