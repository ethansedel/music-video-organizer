"""Read-only safety validation for proposed organization plans."""

from __future__ import annotations

from pathlib import Path

from mvo.models import (
    OrganizationPlan,
    PlannedVideo,
    PlanStatus,
    PreflightItem,
    PreflightResult,
    PreflightStatus,
)


class PlanPreflight:
    """Validate current filesystem facts without changing the library."""

    def validate(self, plan: OrganizationPlan) -> PreflightResult:
        """Return an execution-readiness snapshot for every planned item."""

        root = plan.root.resolve()
        items = tuple(self._validate_item(root, item) for item in plan.items)
        return PreflightResult(root, items, plan.issues)

    def _validate_item(self, root: Path, item: PlannedVideo) -> PreflightItem:
        blockers: list[str] = []
        source = item.video.source.path

        if item.status is not PlanStatus.READY:
            blockers.append(f"plan status is {item.status.value}")
        if source.is_symlink():
            blockers.append("source is a symbolic link")
        elif not source.is_file():
            blockers.append("source file is missing")
        else:
            try:
                stat = source.stat()
                scanned = item.video.source
                if stat.st_size != scanned.size_bytes:
                    blockers.append("source size changed after scanning")
                if scanned.modified_ns and stat.st_mtime_ns != scanned.modified_ns:
                    blockers.append("source modification time changed after scanning")
                if scanned.device and stat.st_dev != scanned.device:
                    blockers.append("source filesystem changed after scanning")
                if scanned.inode and stat.st_ino != scanned.inode:
                    blockers.append("source identity changed after scanning")
            except OSError as error:
                blockers.append(f"source could not be checked: {error}")

        destination, destination_error = self._destination(root, item.destination)
        if destination_error:
            blockers.append(destination_error)
        elif destination is not None:
            source_key = self._path_key(source)
            destination_key = self._path_key(destination)
            if source_key == destination_key:
                if blockers:
                    return PreflightItem(item, PreflightStatus.BLOCKED, tuple(blockers))
                return PreflightItem(
                    item,
                    PreflightStatus.UNCHANGED,
                    ("source already matches the proposed destination",),
                )
            if destination.exists():
                blockers.append("destination already exists")
            else:
                obstruction = self._directory_obstruction(root, destination.parent)
                if obstruction is not None:
                    blockers.append(
                        f"destination parent is not a directory: {obstruction}"
                    )

        if blockers:
            return PreflightItem(item, PreflightStatus.BLOCKED, tuple(blockers))
        return PreflightItem(
            item,
            PreflightStatus.READY,
            ("source and destination passed all safety checks",),
        )

    @staticmethod
    def _destination(root: Path, relative: Path) -> tuple[Path | None, str | None]:
        if relative.is_absolute() or ".." in relative.parts:
            return None, "destination is not a safe relative path"
        destination = (root / relative).resolve(strict=False)
        if not destination.is_relative_to(root):
            return None, "destination escapes the library root"
        return destination, None

    @staticmethod
    def _directory_obstruction(root: Path, parent: Path) -> Path | None:
        current = parent
        while current != root and not current.exists():
            current = current.parent
        if current.exists() and not current.is_dir():
            return current
        return None

    @staticmethod
    def _path_key(path: Path) -> str:
        return str(path.resolve(strict=False)).casefold()
