# Music Video Organizer

Music Video Organizer (MVO) scans a music-video library, interprets filenames,
scores the quality of each interpretation, and writes a standalone HTML report.
Version 0.4 is deliberately read-only: it never renames, moves, or deletes
media. Its planner only previews proposed Jellyfin-friendly paths.

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
pytest
```

The only file MVO writes is the report path explicitly supplied by the user.
The dry-run planner marks uncertain metadata for review and detects destination
collisions before any future execution feature is considered.
