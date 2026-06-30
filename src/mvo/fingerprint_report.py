"""HTML report for opt-in acoustic fingerprint identification."""

from __future__ import annotations

from html import escape
from pathlib import Path

from mvo.models import FingerprintedVideo, FingerprintResult, MatchStatus


def render_fingerprint_html(result: FingerprintResult) -> str:
    """Render acoustic matches without exposing fingerprint values."""

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
  <title>Liner Notes AcoustID report</title>
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
  <h1>Acoustic identification</h1>
  <p class="notice"><strong>Read-only and opt-in.</strong> Chromaprint ran
  locally. Only compact fingerprints and durations were sent to AcoustID; audio,
  filenames, and paths were not uploaded. No fingerprints were submitted.</p>
  <p><strong>Library:</strong> <code>{escape(str(result.root))}</code></p>
  <section class="summary" aria-label="Summary">
    <div class="card"><strong>{result.fingerprint_count}</strong> fingerprinted</div>
    <div class="card"><strong>{result.lookup_count}</strong> API lookups</div>
    <div class="card matched">
      <strong>{counts[MatchStatus.MATCHED]}</strong> matched
    </div>
    <div class="card review"><strong>{counts[MatchStatus.REVIEW]}</strong> review</div>
    <div class="card error"><strong>{counts[MatchStatus.ERROR]}</strong> errors</div>
    <div class="card"><strong>{counts[MatchStatus.SKIPPED]}</strong> skipped</div>
  </section>
  <table>
    <thead><tr><th>File</th><th>Status</th><th>Duration</th><th>Score</th>
    <th>Recording</th><th>AcoustID</th><th>Message</th></tr></thead>
    <tbody>{rows}</tbody>
  </table>
</body>
</html>
"""


def write_fingerprint_report(result: FingerprintResult, output: str | Path) -> Path:
    """Write the acoustic identification report to the selected path."""

    destination = Path(output).expanduser().resolve()
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(render_fingerprint_html(result), encoding="utf-8")
    return destination


def _render_row(item: FingerprintedVideo) -> str:
    candidate = item.candidates[0] if item.candidates else None
    recording = candidate.recordings[0] if candidate and candidate.recordings else None
    if recording:
        recording_url = f"https://musicbrainz.org/recording/{recording.recording_id}"
        credit = " & ".join(recording.artists)
        recording_cell = (
            f'<a href="{escape(recording_url)}">{escape(credit)} — '
            f"{escape(recording.title or 'Untitled')}</a>"
        )
    else:
        recording_cell = "—"
    if candidate:
        acoustid_url = f"https://acoustid.org/track/{candidate.acoustid_id}"
        acoustid_cell = (
            f'<a href="{escape(acoustid_url)}">{escape(candidate.acoustid_id)}</a>'
        )
        score = f"{candidate.score:.0%}"
    else:
        acoustid_cell = "—"
        score = "—"
    status = item.status.value
    status_class = status.replace(" ", "-")
    duration = f"{item.duration} s" if item.duration is not None else "—"
    return "".join(
        (
            "<tr>",
            f"<td><code>{escape(item.video.source.relative_path.as_posix())}</code></td>",
            f'<td class="status {status_class}">{escape(status)}</td>',
            f"<td>{duration}</td><td>{score}</td><td>{recording_cell}</td>",
            f"<td>{acoustid_cell}</td><td>{escape(item.message)}</td>",
            "</tr>",
        )
    )
