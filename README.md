# Music Video Organizer

Music Video Organizer (MVO) scans a music-video library, interprets filenames,
scores the quality of each interpretation, and writes a standalone HTML report.
Version 0.9 development remains read-only. Its execution preflight validates a
folder plan against the current filesystem and identifies blockers before any
future move feature is considered. MVO does not rename, move, or delete media.

## Filename conventions

The parser works best with filenames shaped like:

```text
Artist - Title (Official Video) [1080p].mkv
Artist feat. Guest - Title.mp4
Artist - Title (feat. Guest) (Live).webm
```

Surrounded hyphens, en dashes, em dashes, and vertical bars are recognized as
artist/title separators. Technical tags such as resolutions and codecs are
ignored. Meaningful variants such as `Live`, `Acoustic`, and `Remix` are kept.

## Install and run

Python 3.12 or newer is required.

```shell
python -m pip install -e '.[dev]'
mvo /path/to/music-videos --output report.html
mvo /path/to/music-videos --plan --output dry-run.html
mvo /path/to/music-videos --duplicates --output duplicates.html
mvo /path/to/music-videos --musicbrainz --max-queries 25 --output musicbrainz.html
ACOUSTID_CLIENT_KEY=... mvo /path/to/music-videos --acoustid --max-fingerprints 5 --output acoustid.html
mvo /path/to/music-videos --artwork --max-artwork 10 --output artwork.html
mvo /path/to/music-videos --preflight --output preflight.html
pytest
```

The only file MVO writes is the report path explicitly supplied by the user.
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
use the separate personal user API key. MVO uses POST
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
