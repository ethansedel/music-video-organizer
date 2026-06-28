# Music Video Organizer (MVO)

## Purpose

Music Video Organizer is a safe-first application for organizing music video libraries for Jellyfin and ErsatzTV.

## Current Milestone

Version 0.6

Focus only on:

- Scanner
- Tokenizer
- Parser
- Confidence engine
- HTML reports
- Folder planner
- Dry-run organization report
- Read-only duplicate detection
- Opt-in MusicBrainz filename enrichment
- Unit tests

Do NOT implement:

- File moves
- File renames
- File deletion
- AcoustID
- Artwork downloads

## Safety

This project must NEVER modify user media unless an execution mode is explicitly added in a future version.

All current behavior is scan/report only.

## Code Style

- Python 3.12+
- Type hints
- Docstrings
- Ruff
- Black
- Pytest
- Small modules
- Small pull requests

## Goal

Build the best music video organizer available for Jellyfin and ErsatzTV.
