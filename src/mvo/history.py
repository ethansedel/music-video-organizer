"""Persistent, append-only activity history with narrowly scoped undo."""

from __future__ import annotations

import json
import os
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

from mvo.executor import PlanExecutor


class ActivityHistory:
    """Record library moves and safely reverse a selected move once."""

    filename = ".mvo-history.jsonl"

    def __init__(self, root: Path) -> None:
        self.root = root.resolve()
        self.path = self.root / self.filename

    def record(
        self,
        action: str,
        source: str,
        destination: str,
        *,
        size_bytes: int,
        reversible: bool = True,
        related_id: str | None = None,
    ) -> dict[str, object]:
        """Append and fsync one activity record."""

        record: dict[str, object] = {
            "id": uuid4().hex,
            "timestamp": datetime.now(UTC).isoformat(),
            "action": action,
            "source": self._relative(source),
            "destination": self._relative(destination),
            "size_bytes": size_bytes,
            "reversible": reversible,
        }
        if related_id is not None:
            record["related_id"] = related_id
        with self.path.open("a", encoding="utf-8") as handle:
            json.dump(record, handle, ensure_ascii=False)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        return record

    def records(self) -> list[dict[str, object]]:
        """Return newest-first valid history records with live undo status."""

        if not self.path.exists():
            return []
        records: list[dict[str, object]] = []
        undone = set()
        for line in self.path.read_text(encoding="utf-8").splitlines():
            try:
                value = json.loads(line)
            except json.JSONDecodeError:
                continue
            if not isinstance(value, dict) or not isinstance(value.get("id"), str):
                continue
            if isinstance(value.get("related_id"), str):
                undone.add(value["related_id"])
            records.append(value)
        for record in records:
            record["can_undo"] = (
                bool(record.get("reversible")) and record["id"] not in undone
            )
        return list(reversed(records))

    def undo(self, record_id: object) -> dict[str, object]:
        """Reverse one recorded move after revalidating both exact paths."""

        if not isinstance(record_id, str):
            raise ValueError("history record id must be text")
        record = next(
            (item for item in self.records() if item["id"] == record_id), None
        )
        if record is None or not record.get("can_undo"):
            raise ValueError("this history action is no longer undoable")
        source = self._path(record["destination"])
        destination = self._path(record["source"])
        if source.is_symlink() or not source.is_file():
            raise ValueError("the moved file is no longer at its recorded destination")
        if destination.exists() or destination.is_symlink():
            raise FileExistsError(f"undo destination already exists: {destination}")
        destination.parent.mkdir(parents=True, exist_ok=True)
        size = source.stat().st_size
        if size != record.get("size_bytes"):
            raise ValueError("the moved file changed after this action")
        PlanExecutor._move_exclusive(source, destination)
        try:
            return self.record(
                "undo",
                record["destination"],
                record["source"],
                size_bytes=size,
                reversible=False,
                related_id=record_id,
            )
        except OSError:
            PlanExecutor._move_exclusive(destination, source)
            raise

    def _path(self, relative: object) -> Path:
        value = self._relative(relative)
        path = (self.root / value).resolve(strict=False)
        if not path.is_relative_to(self.root):
            raise ValueError("history path escapes the library")
        return path

    @staticmethod
    def _relative(value: object) -> str:
        if not isinstance(value, str) or not value or value.startswith("/"):
            raise ValueError("history paths must be relative")
        path = Path(value)
        if any(part in {"", ".", ".."} for part in path.parts):
            raise ValueError("history path escapes the library")
        return path.as_posix()
