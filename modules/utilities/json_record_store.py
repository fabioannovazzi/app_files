from __future__ import annotations

import json
import re
import threading
from collections.abc import Callable, Iterable
from pathlib import Path
from typing import Any

__all__ = ["JsonRecordStore", "JsonTableConnection"]


class JsonRecordStore:
    """Small atomic JSON object store keyed by string IDs."""

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()

    def all(self) -> list[dict[str, Any]]:
        with self._lock:
            return [dict(record) for record in self._read().values()]

    def get(self, record_id: str) -> dict[str, Any] | None:
        with self._lock:
            record = self._read().get(str(record_id))
            return dict(record) if record is not None else None

    def upsert(self, record_id: str, record: dict[str, Any]) -> None:
        with self._lock:
            records = self._read()
            records[str(record_id)] = dict(record)
            self._write(records)

    def update(
        self,
        record_id: str,
        updater: Callable[[dict[str, Any]], dict[str, Any] | None],
    ) -> dict[str, Any] | None:
        with self._lock:
            records = self._read()
            current = records.get(str(record_id))
            if current is None:
                return None
            updated = updater(dict(current))
            if updated is None:
                return None
            records[str(record_id)] = dict(updated)
            self._write(records)
            return dict(updated)

    def delete_where(self, predicate: Callable[[dict[str, Any]], bool]) -> int:
        with self._lock:
            records = self._read()
            kept = {
                record_id: record
                for record_id, record in records.items()
                if not predicate(dict(record))
            }
            removed = len(records) - len(kept)
            if removed:
                self._write(kept)
            return removed

    def clear(self) -> None:
        with self._lock:
            self._write({})

    def replace_all(self, records: Iterable[tuple[str, dict[str, Any]]]) -> None:
        with self._lock:
            self._write({str(record_id): dict(record) for record_id, record in records})

    def _read(self) -> dict[str, dict[str, Any]]:
        if not self.path.exists():
            return {}
        try:
            payload = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return {}
        if not isinstance(payload, dict):
            return {}
        records = payload.get("records", payload)
        if not isinstance(records, dict):
            return {}
        return {
            str(record_id): dict(record)
            for record_id, record in records.items()
            if isinstance(record, dict)
        }

    def _write(self, records: dict[str, dict[str, Any]]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary_path = self.path.with_suffix(f"{self.path.suffix}.tmp")
        payload = {"records": records}
        temporary_path.write_text(
            json.dumps(payload, ensure_ascii=False, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        temporary_path.replace(self.path)


class JsonTableCursor:
    def __init__(self, rows: list[dict[str, Any]] | None = None) -> None:
        self._rows = rows or []

    def fetchone(self) -> dict[str, Any] | None:
        return dict(self._rows[0]) if self._rows else None

    def fetchall(self) -> list[dict[str, Any]]:
        return [dict(row) for row in self._rows]


class JsonTableConnection:
    """Tiny DB-API-style adapter for local job-store call sites."""

    def __init__(self, path: str | Path, *, primary_key: str = "job_id") -> None:
        self._store = JsonRecordStore(path)
        self._primary_key = primary_key
        self.row_factory = None

    def __enter__(self) -> "JsonTableConnection":
        return self

    def __exit__(self, *_args: object) -> None:
        return None

    def execute(
        self, sql: str, params: tuple[Any, ...] | list[Any] | None = None
    ) -> JsonTableCursor:
        parameters = tuple(params or ())
        normalized = " ".join(sql.strip().split())
        upper = normalized.upper()
        if not normalized:
            return JsonTableCursor()
        if upper.startswith(("CREATE ", "ALTER ", "PRAGMA ", "DROP ")):
            return JsonTableCursor()
        if upper.startswith("INSERT "):
            return self._insert(normalized, parameters)
        if upper.startswith("SELECT "):
            return self._select(normalized, parameters)
        if upper.startswith("UPDATE "):
            return self._update(normalized, parameters)
        if upper.startswith("DELETE "):
            return self._delete(normalized, parameters)
        return JsonTableCursor()

    def _insert(self, sql: str, params: tuple[Any, ...]) -> JsonTableCursor:
        match = re.search(r"\((?P<columns>[^)]+)\)\s+VALUES\s*\(", sql, re.I)
        if not match:
            return JsonTableCursor()
        columns = [column.strip() for column in match.group("columns").split(",")]
        record = {column: params[index] for index, column in enumerate(columns)}
        record_id = str(record.get(self._primary_key) or "")
        if record_id:
            self._store.upsert(record_id, record)
        return JsonTableCursor()

    def _select(self, sql: str, params: tuple[Any, ...]) -> JsonTableCursor:
        upper = sql.upper()
        if f"WHERE {self._primary_key.upper()} = ?" in upper and params:
            record = self._store.get(str(params[0]))
            return JsonTableCursor(self._project_rows(sql, [record] if record else []))
        rows = self._store.all()
        if "WHERE STATUS IN ('PENDING', 'RUNNING')" in upper:
            rows = [
                row
                for row in rows
                if str(row.get("status") or "") in {"pending", "running"}
            ]
        if "WHERE STATUS = 'PENDING'" in upper:
            rows = [row for row in rows if row.get("status") == "pending"]
        if "ORDER BY UPDATED_AT DESC" in upper:
            rows = sorted(
                rows,
                key=lambda row: float(row.get("updated_at") or 0),
                reverse=True,
            )
        elif "ORDER BY CREATED_AT ASC" in upper:
            rows = sorted(rows, key=lambda row: float(row.get("created_at") or 0))
        if "LIMIT ?" in upper and params:
            try:
                limit = max(0, int(params[-1]))
            except (TypeError, ValueError):
                limit = len(rows)
            rows = rows[:limit]
        return JsonTableCursor(self._project_rows(sql, rows))

    @staticmethod
    def _project_rows(sql: str, rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
        match = re.search(r"^SELECT\s+(?P<columns>.*?)\s+FROM\s+", sql, re.I)
        if match is None:
            return rows
        raw_columns = match.group("columns").strip()
        if raw_columns == "*":
            return rows
        columns = [
            column.strip().split()[-1].strip('"')
            for column in raw_columns.split(",")
            if column.strip()
        ]
        return [{column: row.get(column) for column in columns} for row in rows]

    def _update(self, sql: str, params: tuple[Any, ...]) -> JsonTableCursor:
        upper = sql.upper()
        if "WHERE" not in upper or not params:
            return JsonTableCursor()
        record_id = str(params[-1])
        row = self._store.get(record_id)
        if row is None:
            return JsonTableCursor()
        updated = dict(row)
        if "SET NOTIFICATION_CONTEXT = ?" in upper:
            updated["notification_context"] = params[0]
            updated["updated_at"] = params[1]
        elif (
            "SET STATUS = ?, RESULT = ?, ERROR = ?, RUNNER_PID = ?, UPDATED_AT = ?"
            in upper
        ):
            updated["status"] = params[0]
            updated["result"] = params[1]
            updated["error"] = params[2]
            updated["runner_pid"] = params[3]
            updated["updated_at"] = params[4]
        elif "SET STATUS = ?, ERROR = ?, RUNNER_PID = ?, UPDATED_AT = ?" in upper:
            updated["status"] = params[0]
            updated["error"] = params[1]
            updated["runner_pid"] = params[2]
            updated["updated_at"] = params[3]
        elif "SET STATUS = ?, RUNNER_PID = ?, UPDATED_AT = ?" in upper:
            updated["status"] = params[0]
            updated["runner_pid"] = params[1]
            updated["updated_at"] = params[2]
        elif "SET STATUS = ?, RESULT = ?, ERROR = ?," in upper:
            status = params[0]
            updated["status"] = status
            updated["result"] = params[1]
            updated["error"] = params[2]
            if status in {"completed", "failed", "cancelled"}:
                updated["runner_pid"] = None
            updated["updated_at"] = params[-2]
        elif (
            "SET STATUS = ?, SESSION_ID = ?, RESULT = ?, ERROR = ?, UPDATED_AT = ?"
            in upper
        ):
            updated["status"] = params[0]
            updated["session_id"] = params[1]
            updated["result"] = params[2]
            updated["error"] = params[3]
            updated["updated_at"] = params[4]
        else:
            return JsonTableCursor()
        self._store.upsert(record_id, updated)
        return JsonTableCursor()

    def _delete(self, sql: str, params: tuple[Any, ...]) -> JsonTableCursor:
        if "UPDATED_AT < ?" in sql.upper() and params:
            cutoff = float(params[0])
            self._store.delete_where(
                lambda row: float(row.get("updated_at") or 0) < cutoff
            )
        return JsonTableCursor()
