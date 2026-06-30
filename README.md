# Liner Notes

Liner Notes scans a music-video library, interprets filenames,
scores the quality of each interpretation, and writes a standalone HTML report.
Version 1.0 added a deliberately gated execution mode. It moves only
preflight-ready files, never overwrites a destination, stops on the first move
failure, rolls back earlier moves, and records every outcome in an HTML audit.
Permanent deletion is restricted to files already reviewed in Liner Notes Trash.

## Filename conventions

The parser works best with filenames shaped like:

```text
Artist - Title (Official Video) [1080p].mkv
Artist feat. Guest - Title.mp4
Artist - Title (feat. Guest) (Live).webm
```

Surrounded hyphens, en dashes, em dashes, and vertical bars are recognized as
artist/title separators. A colon followed by a space is also recognized, as in
`Paramore: Misery Business`. Technical tags such as resolutions and codecs are
ignored. Meaningful variants such as `Live`, `Acoustic`, and `Remix` are kept.

## Install and run

Python 3.12 or newer is required.

```shell
python -m pip install -e '.[dev]'
liner-notes /path/to/music-videos --output report.html
liner-notes /path/to/music-videos --plan --output dry-run.html
liner-notes /path/to/music-videos --duplicates --output duplicates.html
liner-notes /path/to/music-videos --musicbrainz --max-queries 25 --output musicbrainz.html
ACOUSTID_CLIENT_KEY=... liner-notes /path/to/music-videos --acoustid --max-fingerprints 5 --output acoustid.html
liner-notes /path/to/music-videos --artwork --max-artwork 10 --output artwork.html
liner-notes /path/to/music-videos --preflight --output preflight.html
liner-notes /path/to/music-videos --review
liner-notes /path/to/test-library --execute --confirm-execution MOVE_FILES --output execution.html
pytest
```

The `mvo` command remains available as a compatibility alias. Analysis modes
write only the requested report; review mode may also write its corrections,
audit, and Trash files after explicit user actions.
The dry-run planner marks uncertain metadata for review and detects destination
collisions before any future execution feature is considered.

Duplicate detection hashes only files that share a size. This avoids reading
every unique file while still confirming exact copies with SHA-256. Metadata
matches are reported separately and always require human review.

MusicBrainz mode identifies itself with a project URL, caches repeated searches
in memory, enforces at least one second between API requests, and caps live
queries at 25 by default. Increase `--max-queries` deliberately for larger runs.

AcoustID mode requires the official `fpcalc` utility from Chromaprint and an
application client key in the `ACOUSTID_CLIENT_KEY` environment variable. Do not
use the separate personal user API key. Liner Notes uses POST
lookups only—there is intentionally no fingerprint submission feature—and caps
work at five files by default.

Artwork mode uses parsed artist/title text to find a MusicBrainz release group,
then requests image metadata from the Cover Art Archive. The generated report
loads remote thumbnails lazily when opened; it does not create local artwork
files. Work is capped at ten eligible videos by default.

Preflight mode rebuilds the organization plan and checks that sources still
exist at the scanned size, destinations stay inside the library, destination
paths are unobstructed, and review or collision items remain blocked. The HTML
is a snapshot only; a future execution mode must repeat every check immediately
before touching a file.

Execution is intentionally difficult to trigger accidentally. `--execute` must
be paired with the exact `--confirm-execution MOVE_FILES` phrase and an HTML
audit path. Blocked or unchanged items are skipped. Ready files are moved using
an exclusive operation that cannot overwrite an existing path. Filesystems that
do not support hard links fall back to copy-verify-delete. If any move fails,
Liner Notes stops and reverses earlier moves from that run. Always review a fresh
preflight report and test execution on a small copy before executing against a
full library.

## Review skipped videos

Run `liner-notes /path/to/music-videos --review` to open a local web editor containing
videos that need review or have destination conflicts. Switch to **All library
videos** to inspect files that are already organized. Each entry includes a
generated thumbnail, a playable preview, optional ffprobe quality details, and
a manual MusicBrainz search. Correct the artist, title, featured artists,
version, or year and choose **Save correction**.

For destination conflicts, Liner Notes recommends a preferred copy using resolution
tags and file size. Choosing it preserves the other copies with distinct
`Alternate` labels. The comparison panel can instead move an unwanted copy to
hidden `.mvo-trash` storage after the exact `TRASH_FILE` confirmation. This is
recoverable quarantine, not permanent deletion; every move is recorded in
`.mvo-trash/audit.jsonl`, and Liner Notes excludes that folder from future scans.
The **Liner Notes Trash** view supports previews, restore with `RESTORE_FILE`, individual
permanent deletion with `DELETE_FOREVER`, and bulk emptying with
`EMPTY_LINER_NOTES_TRASH`. Permanent deletion is never available for active library
files.
**Commit saved changes** moves only
saved, ready corrections after the exact `MOVE_FILES` confirmation and writes
`.mvo-review-execution.html` as an audit report. It keeps the same no-overwrite,
immediate-revalidation, and rollback guarantees as command-line execution.

Corrections are stored in `.mvo-overrides.json` at the library root. Later
analysis, plan, preflight, and execution commands load that file automatically.
Use `--overrides /another/path.json` when the corrections file should live
somewhere else. The editor listens only on this computer; press Control-C in the
terminal when finished.
