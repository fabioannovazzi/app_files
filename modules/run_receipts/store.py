"""Durable minimal storage for server-stamped Vera run receipts."""

from __future__ import annotations

import hmac
import os
import sqlite3
import threading
from collections.abc import Iterator, Mapping
from contextlib import contextmanager
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any

import psycopg

from modules.pdp.postgres_compat import (
    DICT_ROW_FACTORY,
    PostgresCommitStateUnknownError,
    connect_pdp_database,
    is_postgres_enabled,
)
from modules.utilities.cache import get_cache_dir

__all__ = [
    "RunReceiptConflictError",
    "RunReceiptRecord",
    "RunReceiptStore",
    "RunReceiptStoreUnavailableError",
    "get_run_receipt_store",
]

_SQLITE_PATH_ENV = "VERA_RUN_RECEIPT_DB_PATH"
_DEFAULT_SQLITE_FILENAME = "vera_run_receipts.sqlite3"
_SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS mparanza_vera_run_receipts (
    receipt_id TEXT PRIMARY KEY,
    plugin_version TEXT NOT NULL,
    report_sha256 TEXT NOT NULL,
    stamped_at TEXT NOT NULL,
    key_id TEXT NOT NULL,
    signature TEXT NOT NULL
)
"""


class RunReceiptStoreUnavailableError(RuntimeError):
    """Raised when the durable receipt record cannot be read or written."""


class RunReceiptConflictError(RuntimeError):
    """Raised when one opaque receipt ID is reused for different evidence."""


@dataclass(frozen=True, slots=True)
class RunReceiptRecord:
    """The complete and intentionally minimal server-side receipt record."""

    receipt_id: str
    plugin_version: str
    report_sha256: str
    stamped_at: str
    key_id: str
    signature: str

    @property
    def signed_payload(self) -> dict[str, Any]:
        """Return exactly the fields covered by the Ed25519 signature."""

        return {
            "schema_version": 1,
            "receipt_id": self.receipt_id,
            "plugin_version": self.plugin_version,
            "report_sha256": self.report_sha256,
            "stamped_at": self.stamped_at,
            "key_id": self.key_id,
        }


def _default_sqlite_path() -> Path:
    configured = os.environ.get(_SQLITE_PATH_ENV, "").strip()
    if configured:
        return Path(configured).expanduser()
    return get_cache_dir("vera_run_receipts") / _DEFAULT_SQLITE_FILENAME


class RunReceiptStore:
    """Postgres-backed store with a SQLite fallback for local use and tests."""

    def __init__(self, *, sqlite_path: Path | None = None) -> None:
        self._use_postgres = sqlite_path is None and is_postgres_enabled()
        self._sqlite_path = sqlite_path or _default_sqlite_path()
        self._schema_ready = False
        self._schema_lock = threading.Lock()

    @contextmanager
    def _connect(self) -> Iterator[Any]:
        if self._use_postgres:
            with connect_pdp_database(Path(".")) as connection:
                connection.row_factory = DICT_ROW_FACTORY
                yield connection
            return
        self._sqlite_path.parent.mkdir(parents=True, exist_ok=True)
        connection = sqlite3.connect(self._sqlite_path, timeout=30.0)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA busy_timeout = 30000")
        connection.execute("PRAGMA journal_mode = WAL")
        try:
            with connection:
                yield connection
        finally:
            connection.close()

    def _ensure_schema(self) -> None:
        if self._schema_ready:
            return
        with self._schema_lock:
            if self._schema_ready:
                return
            try:
                with self._connect() as connection:
                    connection.execute(_SCHEMA_SQL)
            except (
                OSError,
                sqlite3.Error,
                psycopg.Error,
                PostgresCommitStateUnknownError,
            ) as exc:
                raise RunReceiptStoreUnavailableError(
                    "Run-receipt storage is unavailable."
                ) from exc
            self._schema_ready = True

    @staticmethod
    def _record(row: Mapping[str, Any] | sqlite3.Row) -> RunReceiptRecord:
        values = dict(row)
        return RunReceiptRecord(
            receipt_id=str(values["receipt_id"]),
            plugin_version=str(values["plugin_version"]),
            report_sha256=str(values["report_sha256"]),
            stamped_at=str(values["stamped_at"]),
            key_id=str(values["key_id"]),
            signature=str(values["signature"]),
        )

    @staticmethod
    def _same_evidence(left: RunReceiptRecord, right: RunReceiptRecord) -> bool:
        return hmac.compare_digest(
            left.report_sha256, right.report_sha256
        ) and hmac.compare_digest(left.plugin_version, right.plugin_version)

    def stamp(self, candidate: RunReceiptRecord) -> RunReceiptRecord:
        """Persist one signed record idempotently and return the durable record."""

        self._ensure_schema()
        sql = """
            INSERT INTO mparanza_vera_run_receipts (
                receipt_id, plugin_version, report_sha256,
                stamped_at, key_id, signature
            ) VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT (receipt_id) DO NOTHING
            RETURNING receipt_id
        """
        try:
            with self._connect() as connection:
                connection.disable_transaction_replay() if self._use_postgres else None
                connection.execute(
                    sql,
                    (
                        candidate.receipt_id,
                        candidate.plugin_version,
                        candidate.report_sha256,
                        candidate.stamped_at,
                        candidate.key_id,
                        candidate.signature,
                    ),
                ).fetchone()
                row = connection.execute(
                    "SELECT * FROM mparanza_vera_run_receipts WHERE receipt_id = ?",
                    (candidate.receipt_id,),
                ).fetchone()
                if row is None:
                    raise RunReceiptStoreUnavailableError(
                        "Run receipt could not be read after stamping."
                    )
                record = self._record(row)
                if not self._same_evidence(record, candidate):
                    raise RunReceiptConflictError(
                        "receipt_id was already used for different run evidence."
                    )
                return record
        except RunReceiptConflictError:
            raise
        except RunReceiptStoreUnavailableError:
            raise
        except (
            OSError,
            sqlite3.Error,
            psycopg.Error,
            PostgresCommitStateUnknownError,
        ) as exc:
            raise RunReceiptStoreUnavailableError(
                "Run-receipt storage is unavailable."
            ) from exc

    def get(self, receipt_id: str) -> RunReceiptRecord | None:
        """Return one public receipt proof by its opaque identifier."""

        self._ensure_schema()
        try:
            with self._connect() as connection:
                row = connection.execute(
                    "SELECT * FROM mparanza_vera_run_receipts WHERE receipt_id = ?",
                    (receipt_id,),
                ).fetchone()
                return self._record(row) if row is not None else None
        except (
            OSError,
            sqlite3.Error,
            psycopg.Error,
            PostgresCommitStateUnknownError,
        ) as exc:
            raise RunReceiptStoreUnavailableError(
                "Run-receipt storage is unavailable."
            ) from exc


@lru_cache(maxsize=1)
def get_run_receipt_store() -> RunReceiptStore:
    """Return the process-wide durable run-receipt store."""

    return RunReceiptStore()
