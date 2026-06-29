"""Read-only discovery of music-video files."""

from __future__ import annotations

import os
from pathlib import Path

from mvo.config import VIDEO_EXTENSIONS
from mvo.models import ScanIssue, ScanResult, VideoFile


class LibraryScanner:
    """Recursively discover supported video files without following symlinks."""

    def __init__(self, extensions: frozenset[str] = VIDEO_EXTENSIONS) -> None:
        self._extensions = frozenset(extension.casefold() for extension in extensions)

    def scan(self, root: str | Path) -> ScanResult:
        """Scan a directory and return sorted files plus recoverable errors."""

        library_root = Path(root).expanduser().resolve()
        if not library_root.is_dir():
            raise NotADirectoryError(f"Library root is not a directory: {library_root}")

        files: list[VideoFile] = []
        issues: list[ScanIssue] = []

        def on_error(error: OSError) -> None:
            issues.append(ScanIssue(Path(error.filename or library_root), str(error)))

        for directory, directory_names, filenames in os.walk(
            library_root, followlinks=False, onerror=on_error
        ):
            directory_names.sort(key=str.casefold)
            for filename in sorted(filenames, key=str.casefold):
                path = Path(directory, filename)
                extension = path.suffix.casefold()
                if extension not in self._extensions or path.is_symlink():
                    continue
                try:
                    stat = path.stat()
                except OSError as error:
                    issues.append(ScanIssue(path, str(error)))
                    continue
                files.append(
                    VideoFile(
                        path=path,
                        relative_path=path.relative_to(library_root),
                        size_bytes=stat.st_size,
                        extension=extension,
                        modified_ns=stat.st_mtime_ns,
                        device=stat.st_dev,
                        inode=stat.st_ino,
                    )
                )

        files.sort(key=lambda item: item.relative_path.as_posix().casefold())
        issues.sort(key=lambda item: item.path.as_posix().casefold())
        return ScanResult(root=library_root, files=tuple(files), issues=tuple(issues))
