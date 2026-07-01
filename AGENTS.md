# Liner Notes

## Purpose

Liner Notes is a safe-first application for organizing music video libraries for Jellyfin and ErsatzTV.

## Current Milestone

Version 1.3

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
- Local previews, thumbnails, and quality inspection
- Manual MusicBrainz review searches
- Explicitly confirmed review-editor execution
- Explicitly confirmed, recoverable duplicate quarantine
- Liner Notes Trash review, restore, and explicitly confirmed emptying
- Password-protected Docker Compose deployment
- Themed session-cookie sign-in
- Automatic and manual library rescanning
- Jellyfin NFO preview and export
- TrueNAS readiness checks
- Persistent activity history and safe undo
- Bulk video selection
- Unit tests

Do NOT implement:

- Ungated file mutations
- File deletion outside `.mvo-trash`
- Artwork downloads beside media

## Safety

This project must NEVER modify user media outside the explicit execution mode.

Execution requires the exact `MOVE_FILES` confirmation phrase, immediate
preflight validation, exclusive non-overwriting moves, and rollback on failure.
Duplicate removal means moving a revalidated conflict copy into recoverable
`.mvo-trash` storage. The exact `EMPTY_LINER_NOTES_TRASH` confirmation remains
required before bulk permanent deletion.

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
