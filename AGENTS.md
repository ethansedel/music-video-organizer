# Music Video Organizer (MVO)

## Purpose

Music Video Organizer is a safe-first application for organizing music video libraries for Jellyfin and ErsatzTV.

## Current Milestone

Version 1.1

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
- Opt-in local Chromaprint and AcoustID lookup
- Opt-in Cover Art Archive previews
- Read-only execution preflight
- Explicitly confirmed, non-overwriting execution
- Rollback and execution audit reports
- Local skipped-video review editor
- Persistent, non-media metadata overrides
- Unit tests

Do NOT implement:

- Ungated file mutations
- File deletion
- Artwork downloads beside media

## Safety

This project must NEVER modify user media outside the explicit execution mode.

Execution requires the exact `MOVE_FILES` confirmation phrase, immediate
preflight validation, exclusive non-overwriting moves, and rollback on failure.

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
