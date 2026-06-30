"""Explicitly confirmed, recoverable quarantine for unwanted duplicate copies."""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from mvo.config import VIDEO_EXTENSIONS
from mvo.executor import PlanExecutor
from mvo.models import VideoFile


@dataclass(frozen=True, slots=True)
class QuarantineResult:
    """Audit-ready result of moving one duplicate into Liner Notes Trash."""

    source: Path
    destination: Path
    size_bytes: int


class DuplicateQuarantine:
    """Move a revalidated duplicate to hidden, recoverable library storage."""

    directory_name = ".mvo-trash"

    def quarantine(
        self,
        root: Path,
        video: VideoFile,
        *,
        confirmation: object,
    ) -> QuarantineResult:
        """Quarantine one exact scanned file after the `TRASH_FILE` phrase."""

        if confirmation != "TRASH_FILE":
            raise ValueError("type TRASH_FILE to move this copy to Liner Notes Trash")
        self._revalidate(video)
        trash_root = root / self.directory_name
        destination = trash_root / video.relative_path
        if not destination.resolve(strict=False).is_relative_to(trash_root.resolve()):
            raise ValueError("trash destination escapes the library")
        if destination.exists():
            raise FileExistsError(
                f"Liner Notes Trash already contains: {video.relative_path}"
            )
        destination.parent.mkdir(parents=True, exist_ok=True)
        PlanExecutor._move_exclusive(video.path, destination)
        result = QuarantineResult(video.path, destination, video.size_bytes)
        try:
            self._append_audit(
                trash_root,
                {
                    "action": "quarantine",
                    "source": result.source.relative_to(root).as_posix(),
                    "destination": result.destination.relative_to(root).as_posix(),
                    "size_bytes": result.size_bytes,
                },
            )
        except OSError:
            PlanExecutor._move_exclusive(destination, video.path)
            raise
        return result

    def list_files(self, root: Path) -> tuple[Path, ...]:
        """List supported, regular video files in Liner Notes Trash."""

        trash_root = root / self.directory_name
        if not trash_root.is_dir():
            return ()
        files = (
            path
            for path in trash_root.rglob("*")
            if path.is_file()
            and not path.is_symlink()
            and path.suffix.casefold() in VIDEO_EXTENSIONS
        )
        return tuple(sorted(files, key=lambda path: path.as_posix().casefold()))

    def restore(
        self, root: Path, relative_path: object, *, confirmation: object
    ) -> Path:
        """Restore one quarantined file to its original non-overwriting path."""

        if confirmation != "RESTORE_FILE":
            raise ValueError("type RESTORE_FILE to restore this copy")
        source = self.resolve(root, relative_path)
        trash_root = root / self.directory_name
        destination = root / source.relative_to(trash_root)
        if destination.exists():
            raise FileExistsError(f"restore destination already exists: {destination}")
        destination.parent.mkdir(parents=True, exist_ok=True)
        size = source.stat().st_size
        PlanExecutor._move_exclusive(source, destination)
        try:
            self._append_audit(
                trash_root,
                {
                    "action": "restore",
                    "source": source.relative_to(root).as_posix(),
                    "destination": destination.relative_to(root).as_posix(),
                    "size_bytes": size,
                },
            )
        except OSError:
            PlanExecutor._move_exclusive(destination, source)
            raise
        return destination

    def delete_permanently(
        self, root: Path, relative_path: object, *, confirmation: object
    ) -> int:
        """Permanently unlink one file already inside Liner Notes Trash."""

        if confirmation != "DELETE_FOREVER":
            raise ValueError("type DELETE_FOREVER to permanently delete this file")
        path = self.resolve(root, relative_path)
        trash_root = root / self.directory_name
        size = path.stat().st_size
        record = {
            "action": "delete permanently",
            "source": path.relative_to(root).as_posix(),
            "size_bytes": size,
        }
        self._append_audit(trash_root, {**record, "status": "started"})
        path.unlink()
        self._append_audit(trash_root, {**record, "status": "completed"})
        return size

    def empty(self, root: Path, *, confirmation: object) -> tuple[int, int, list[str]]:
        """Delete every current trash video, reporting partial failures explicitly."""

        if confirmation != "EMPTY_LINER_NOTES_TRASH":
            raise ValueError(
                "type EMPTY_LINER_NOTES_TRASH to permanently empty Liner Notes Trash"
            )
        deleted = 0
        deleted_bytes = 0
        errors: list[str] = []
        for path in self.list_files(root):
            relative = path.relative_to(root).as_posix()
            try:
                deleted_bytes += self.delete_permanently(
                    root, relative, confirmation="DELETE_FOREVER"
                )
            except OSError as error:
                errors.append(f"{relative}: {error}")
            else:
                deleted += 1
        return deleted, deleted_bytes, errors

    def resolve(self, root: Path, relative_path: object) -> Path:
        """Resolve one exact trash-relative video path without traversal."""

        if not isinstance(relative_path, str):
            raise ValueError("trash path must be text")
        trash_root = (root / self.directory_name).resolve()
        candidate = root / relative_path
        if candidate.is_symlink():
            raise ValueError("trash file cannot be a symbolic link")
        path = candidate.resolve(strict=False)
        if not path.is_relative_to(trash_root):
            raise ValueError("file is not inside Liner Notes Trash")
        if (
            path.is_symlink()
            or not path.is_file()
            or path.suffix.casefold() not in VIDEO_EXTENSIONS
        ):
            raise ValueError("trash file is missing or unsupported")
        return path

    @staticmethod
    def _revalidate(video: VideoFile) -> None:
        if video.path.is_symlink() or not video.path.is_file():
            raise ValueError("duplicate source is missing or is a symbolic link")
        stat = video.path.stat()
        if (
            stat.st_size != video.size_bytes
            or (video.modified_ns and stat.st_mtime_ns != video.modified_ns)
            or (video.device and stat.st_dev != video.device)
            or (video.inode and stat.st_ino != video.inode)
        ):
            raise ValueError("duplicate source changed after scanning")

    @staticmethod
    def _append_audit(trash_root: Path, record: dict[str, object]) -> None:
        record = {"timestamp": datetime.now(UTC).isoformat(), **record}
        with (trash_root / "audit.jsonl").open("a", encoding="utf-8") as handle:
            json.dump(record, handle, ensure_ascii=False)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
