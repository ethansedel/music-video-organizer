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
tags and file size. Choosing it keeps that copy and moves the other conflicting
copies to hidden `.mvo-trash` storage. The comparison panel can also quarantine
one unwanted copy directly. This is recoverable quarantine, not permanent
deletion; every move is recorded in
`.mvo-trash/audit.jsonl`, and Liner Notes excludes that folder from future scans.
The **Liner Notes Trash** view supports previews, one-click restore, individual
permanent deletion after a browser warning, and bulk emptying with the exact
`EMPTY_LINER_NOTES_TRASH` phrase. Permanent deletion is never available for
active library files.
**Commit saved changes** moves only
saved, ready corrections after the exact `MOVE_FILES` confirmation and writes
`.mvo-review-execution.html` as an audit report. It keeps the same no-overwrite,
immediate-revalidation, and rollback guarantees as command-line execution.

Corrections are stored in `.mvo-overrides.json` at the library root. Later
analysis, plan, preflight, and execution commands load that file automatically.
Use `--overrides /another/path.json` when the corrections file should live
somewhere else. The editor listens only on this computer by default; press
Control-C in the terminal when finished.

The review workspace automatically rescans every five minutes and also provides
a manual **Refresh library** button. Select multiple organized videos to export
adjacent, non-overwriting Jellyfin `.nfo` sidecars; videos with a pending move
must be organized first so a sidecar is never left behind. **History & undo** records organization
and quarantine moves in `.mvo-history.jsonl` and reverses a move only when its
recorded destination is unchanged and the original path is free. **Server
readiness** checks dataset access, free space, ffmpeg, ffprobe, and the active
container UID/GID, and reminds TrueNAS users to configure periodic snapshots.

## Docker Compose and Dockge

Docker Compose runs Liner Notes continuously on a server with ffmpeg and
ffprobe included. Dockge users can create a stack by pasting `compose.yaml`,
then paste the values from `.env.example` into Dockge's environment editor.
Set `MUSIC_VIDEO_PATH` to the path as seen by the Docker server, not a path on
another computer.

For command-line Docker Compose, clone the repository on the Docker server,
then configure it:

```shell
cp .env.example .env
```

Edit `.env` and set:

- `MUSIC_VIDEO_PATH` to the absolute server path containing the videos.
- `LINER_NOTES_PASSWORD` to a long password of at least eight characters.
- `PUID` and `PGID` to the numeric owner of the video library. Run `id` on the
  server to find them.

### TrueNAS SCALE with Dockge

Create or choose a TrueNAS dataset for the music-video library, such as
`/mnt/tank/media/musicvideos`. Its ACL must give a TrueNAS user and group
read/write access. Set `MUSIC_VIDEO_PATH` to that full `/mnt/...` path and set
`PUID` and `PGID` to that user's numeric IDs; do not assume the example value
of `1000` matches the server.

In Dockge, create a stack, paste `compose.yaml`, and add the `.env.example`
values in Dockge's environment editor. Deploy the stack, then open
`http://TRUENAS-IP:8765/`. The login username is `liner-notes` and the password
is the `LINER_NOTES_PASSWORD` value. Liner Notes writes only through the mounted
dataset; its container filesystem remains read-only.

Start the service:

```shell
docker compose up -d
docker compose logs -f liner-notes
```

Open `http://SERVER-IP:8765/`, use `liner-notes` as the username, and use the
password from `.env`. The library mount must be writable for saving corrections,
organizing files, and using Liner Notes Trash. The container itself runs without
Linux capabilities and with a read-only root filesystem.

The ready-made image supports 64-bit Intel/AMD and ARM servers. Liner Notes uses
a themed password form and an HTTP-only session cookie, but plain HTTP still
does not encrypt traffic. Keep the default deployment
on a trusted private network. For access outside that network, set
`LINER_NOTES_BIND=127.0.0.1` and place Liner Notes behind an HTTPS reverse proxy
or VPN. To update after pulling new source:

```shell
docker compose pull
docker compose up -d
```
