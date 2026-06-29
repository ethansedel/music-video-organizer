"""Explicit, non-overwriting execution of validated organization plans."""

from __future__ import annotations

import os
import shutil
from contextlib import suppress
from dataclasses import replace
from errno import ENOTSUP, EOPNOTSUPP, EPERM, EXDEV
from pathlib import Path

from mvo.models import (
    ExecutionItem,
    ExecutionResult,
    ExecutionStatus,
    OrganizationPlan,
    PreflightStatus,
)
from mvo.preflight import PlanPreflight


class PlanExecutor:
    """Move ready files with immediate checks, no overwrites, and rollback."""

    def __init__(self, preflight: PlanPreflight | None = None) -> None:
        self._preflight = preflight or PlanPreflight()

    def execute(self, plan: OrganizationPlan) -> ExecutionResult:
        """Execute ready actions; roll back the run if any move fails."""

        initial = self._preflight.validate(plan)
        outcomes: list[ExecutionItem | None] = [None] * len(plan.items)
        ready_indexes: list[int] = []
        for index, item in enumerate(initial.items):
            if item.status is PreflightStatus.BLOCKED:
                outcomes[index] = ExecutionItem(
                    item.planned,
                    ExecutionStatus.SKIPPED,
                    "; ".join(item.checks),
                )
            elif item.status is PreflightStatus.UNCHANGED:
                outcomes[index] = ExecutionItem(
                    item.planned,
                    ExecutionStatus.UNCHANGED,
                    "already at the proposed destination",
                )
            else:
                ready_indexes.append(index)

        moved_indexes: list[int] = []
        created_directories: list[Path] = []
        for position, index in enumerate(ready_indexes):
            planned = plan.items[index]
            current = self._preflight.validate(
                OrganizationPlan(plan.root, (planned,), ())
            ).items[0]
            if current.status is not PreflightStatus.READY:
                message = "immediate revalidation failed: " + "; ".join(current.checks)
                outcomes[index] = ExecutionItem(
                    planned, ExecutionStatus.FAILED, message
                )
                self._stop_remaining(outcomes, plan, ready_indexes[position + 1 :])
                rollback_complete = self._rollback(
                    plan, outcomes, moved_indexes, created_directories
                )
                return ExecutionResult(
                    plan.root,
                    tuple(outcomes),
                    bool(moved_indexes),
                    rollback_complete,
                )
            source = planned.video.source.path
            destination = plan.root / planned.destination
            try:
                created_directories.extend(self._create_parents(plan.root, destination))
                self._move_exclusive(source, destination)
            except OSError as error:
                outcomes[index] = ExecutionItem(
                    planned, ExecutionStatus.FAILED, f"move failed: {error}"
                )
                self._stop_remaining(outcomes, plan, ready_indexes[position + 1 :])
                rollback_complete = self._rollback(
                    plan, outcomes, moved_indexes, created_directories
                )
                return ExecutionResult(
                    plan.root,
                    tuple(outcomes),
                    bool(moved_indexes),
                    rollback_complete,
                )
            outcomes[index] = ExecutionItem(
                planned, ExecutionStatus.MOVED, "moved without overwriting"
            )
            moved_indexes.append(index)

        return ExecutionResult(plan.root, tuple(outcomes), False)

    @staticmethod
    def _move_exclusive(source: Path, destination: Path) -> None:
        """Move a regular file without overwriting an existing destination."""

        try:
            os.link(source, destination, follow_symlinks=False)
        except OSError as error:
            if error.errno not in {ENOTSUP, EOPNOTSUPP, EPERM, EXDEV}:
                raise
            PlanExecutor._copy_unlink_exclusive(source, destination)
            return
        try:
            source.unlink()
        except OSError:
            destination.unlink(missing_ok=True)
            raise

    @staticmethod
    def _copy_unlink_exclusive(source: Path, destination: Path) -> None:
        """Fallback for filesystems that do not support hard links."""

        before = source.stat()
        try:
            with (
                source.open("rb") as source_file,
                destination.open("xb") as destination_file,
            ):
                shutil.copyfileobj(source_file, destination_file, length=1024 * 1024)
                destination_file.flush()
                os.fsync(destination_file.fileno())
            shutil.copystat(source, destination, follow_symlinks=False)
            after = source.stat()
            if (
                after.st_dev != before.st_dev
                or after.st_ino != before.st_ino
                or after.st_size != before.st_size
                or after.st_mtime_ns != before.st_mtime_ns
            ):
                raise OSError("source changed during copy")
            if destination.stat().st_size != before.st_size:
                raise OSError("copied size does not match source")
            source.unlink()
        except OSError:
            destination.unlink(missing_ok=True)
            raise

    @staticmethod
    def _create_parents(root: Path, destination: Path) -> list[Path]:
        missing: list[Path] = []
        current = destination.parent
        while current != root and not current.exists():
            missing.append(current)
            current = current.parent
        destination.parent.mkdir(parents=True, exist_ok=True)
        return list(reversed(missing))

    def _rollback(
        self,
        plan: OrganizationPlan,
        outcomes: list[ExecutionItem | None],
        moved_indexes: list[int],
        created_directories: list[Path],
    ) -> bool:
        rollback_ok = True
        for index in reversed(moved_indexes):
            planned = plan.items[index]
            source = planned.video.source.path
            destination = plan.root / planned.destination
            try:
                self._move_exclusive(destination, source)
            except OSError as error:
                outcomes[index] = ExecutionItem(
                    planned,
                    ExecutionStatus.FAILED,
                    f"rollback failed: {error}",
                )
                rollback_ok = False
            else:
                outcomes[index] = replace(
                    outcomes[index],
                    status=ExecutionStatus.ROLLED_BACK,
                    message="move reversed after a later failure",
                )
        for directory in reversed(created_directories):
            with suppress(OSError):
                directory.rmdir()
        return rollback_ok

    @staticmethod
    def _stop_remaining(
        outcomes: list[ExecutionItem | None],
        plan: OrganizationPlan,
        indexes: list[int],
    ) -> None:
        for index in indexes:
            outcomes[index] = ExecutionItem(
                plan.items[index],
                ExecutionStatus.SKIPPED,
                "not attempted after an earlier failure",
            )
