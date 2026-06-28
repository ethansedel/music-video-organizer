# Music Video Organizer

Music Video Organizer (MVO) scans a music-video library, interprets filenames,
scores the quality of each interpretation, and writes a standalone HTML report.
Version 0.6 remains read-only. MusicBrainz enrichment is explicitly
opt-in and searches only parsed artist/title text; it does not upload audio,
write tags, or modify media.

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
