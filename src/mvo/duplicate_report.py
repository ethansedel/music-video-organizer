"""Standalone HTML reporting for read-only duplicate findings."""

from __future__ import annotations

from html import escape
from pathlib import Path

from mvo.models import DuplicateGroup, DuplicateKind, DuplicateResult


def render_duplicate_html(result: DuplicateResult) -> str:
    """Render confirmed and possible duplicates as an escaped HTML report."""

    exact = sum(group.kind is DuplicateKind.EXACT for group in result.groups)
    metadata = sum(group.kind is DuplicateKind.METADATA for group in result.groups)
    recoverable = sum(group.recoverable_bytes for group in result.groups)
    groups = "\n".join(_render_group(group) for group in result.groups)
    if not groups:
        groups = '<p class="empty">No duplicates found.</p>'
    issues = "".join(
        f"<li><code>{escape(str(issue.path))}</code>: {escape(issue.message)}</li>"
        for issue in result.issues
    )
    issue_section = (
        f"<section><h2>Read issues</h2><ul>{issues}</ul></section>" if issues else ""
    )
    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Liner Notes duplicate report</title>
  <style>
    :root {{ color-scheme: light dark; font-family: system-ui, sans-serif; }}
    body {{ margin: 0 auto; max-width: 96rem; padding: 2rem; }}
    .notice {{ border: 2px solid #2878bd; border-radius: .6rem; padding: 1rem; }}
    .summary {{ display: flex; gap: .75rem; flex-wrap: wrap; margin: 1.5rem 0; }}
    .card, .group {{ border: 1px solid #8886; border-radius: .6rem; padding: 1rem; }}
    .group {{ margin: 1rem 0; }} .group h2 {{ margin-top: 0; }}
    .exact {{ color: #b42318; }} .metadata-match {{ color: #a46400; }}
    table {{ border-collapse: collapse; width: 100%; }}
    th, td {{ border-bottom: 1px solid #8885; padding: .65rem; text-align: left; }}
    .empty {{ text-align: center; padding: 3rem; }}
    code {{ overflow-wrap: anywhere; }}
  </style>
</head>
<body>
  <h1>Duplicate detection</h1>
  <p class="notice"><strong>Read-only report.</strong> No files have been deleted,
  moved, renamed, or otherwise modified. Metadata matches require human review.</p>
  <p><strong>Library:</strong> <code>{escape(str(result.root))}</code></p>
  <section class="summary" aria-label="Summary">
    <div class="card exact"><strong>{exact}</strong> exact groups</div>
    <div class="card metadata-match"><strong>{metadata}</strong> metadata matches</div>
    <div class="card">
      <strong>{_format_size(recoverable)}</strong> potential savings
    </div>
  </section>
  {groups}
  {issue_section}
</body>
</html>
"""


def write_duplicate_report(result: DuplicateResult, output: str | Path) -> Path:
    """Write duplicate findings to the exact user-selected report path."""

    destination = Path(output).expanduser().resolve()
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(render_duplicate_html(result), encoding="utf-8")
    return destination


def _render_group(group: DuplicateGroup) -> str:
    kind_class = group.kind.value.replace(" ", "-")
    rows = "".join(
        "<tr>"
        f"<td><code>{escape(video.source.relative_path.as_posix())}</code></td>"
        f"<td>{_format_size(video.source.size_bytes)}</td>"
        f"<td>{escape(video.parsed.artist or '—')}</td>"
        f"<td>{escape(video.parsed.title)}</td>"
        "</tr>"
        for video in group.videos
    )
    savings = (
        f" · potential savings {_format_size(group.recoverable_bytes)}"
        if group.kind is DuplicateKind.EXACT
        else " · review before taking any action"
    )
    return (
        f'<section class="group {kind_class}">'
        f"<h2>{escape(group.kind.value.title())}: "
        f"{escape(group.signature)}</h2><p>{len(group.videos)} files{savings}</p>"
        "<table><thead><tr><th>Path</th><th>Size</th><th>Artist</th>"
        f"<th>Title</th></tr></thead><tbody>{rows}</tbody></table></section>"
    )


def _format_size(size_bytes: int) -> str:
    value = float(size_bytes)
    for unit in ("B", "KiB", "MiB", "GiB", "TiB"):
        if value < 1024 or unit == "TiB":
            return f"{value:.0f} {unit}" if unit == "B" else f"{value:.1f} {unit}"
        value /= 1024
    raise AssertionError("unreachable")
