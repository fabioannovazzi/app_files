"""Durable storage for user-submitted Mparanza change requests."""

from __future__ import annotations

import hashlib
import hmac
import json
import os
import re
import secrets
import sqlite3
import threading
from collections.abc import Iterator, Mapping, Sequence
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timezone
from functools import lru_cache
from pathlib import Path
from typing import Any, Literal

import psycopg

from modules.pdp.postgres_compat import (
    DICT_ROW_FACTORY,
    PostgresCommitStateUnknownError,
    connect_pdp_database,
    is_postgres_enabled,
)
from modules.utilities.cache import get_cache_dir

__all__ = [
    "ChangeRequestConflictError",
    "ChangeRequestCapacityError",
    "ChangeRequestManifestError",
    "ChangeRequestNotFoundError",
    "ChangeRequestRecord",
    "ChangeRequestStore",
    "ChangeRequestStoreError",
    "ChangeRequestStoreUnavailableError",
    "get_change_request_store",
]

ChangeRequestStatus = Literal["open", "fixed"]

_CHANGE_REQUEST_ID_PATTERN = re.compile(r"^CR-(?P<number>[1-9][0-9]*)$")
_DEFAULT_MAX_RECORDS = 10_000
_MAX_RECORDS_ENV = "CHANGE_REQUEST_MAX_RECORDS"
_DEFAULT_SQLITE_FILENAME = "change_requests.sqlite3"
_SQLITE_PATH_ENV = "CHANGE_REQUEST_DB_PATH"
_POSTGRES_SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS mparanza_change_requests (
    request_no BIGSERIAL PRIMARY KEY,
    submission_id TEXT NOT NULL UNIQUE,
    plugin TEXT NOT NULL,
    plugin_version TEXT NOT NULL,
    kind TEXT NOT NULL,
    request_json TEXT NOT NULL,
    request_sha256 TEXT NOT NULL,
    status_token TEXT NOT NULL UNIQUE,
    status TEXT NOT NULL DEFAULT 'open' CHECK (status IN ('open', 'fixed')),
    interview_url TEXT,
    interview_json TEXT,
    fixed_version TEXT,
    install_url TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    fixed_at TEXT
)
"""

_SQLITE_SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS mparanza_change_requests (
    request_no INTEGER PRIMARY KEY AUTOINCREMENT,
    submission_id TEXT NOT NULL UNIQUE,
    plugin TEXT NOT NULL,
    plugin_version TEXT NOT NULL,
    kind TEXT NOT NULL,
    request_json TEXT NOT NULL,
    request_sha256 TEXT NOT NULL,
    status_token TEXT NOT NULL UNIQUE,
    status TEXT NOT NULL DEFAULT 'open' CHECK (status IN ('open', 'fixed')),
    interview_url TEXT,
    interview_json TEXT,
    fixed_version TEXT,
    install_url TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    fixed_at TEXT
)
"""


class ChangeRequestStoreError(RuntimeError):
    """Base error for the change-request store."""


class ChangeRequestStoreUnavailableError(ChangeRequestStoreError):
    """Raised when durable storage cannot complete an operation."""


class ChangeRequestConflictError(ChangeRequestStoreError):
    """Raised when an idempotency key is reused for different content."""


class ChangeRequestCapacityError(ChangeRequestStoreError):
    """Raised when the public intake has reached its configured durable bound."""


class ChangeRequestNotFoundError(ChangeRequestStoreError):
    """Raised when an operator references an unknown change request."""


class ChangeRequestManifestError(ChangeRequestStoreError):
    """Raised when a fix is not present in the local published manifest."""


@dataclass(frozen=True, slots=True)
class ChangeRequestRecord:
    """One durable change request and its release state."""

    request_no: int
    submission_id: str
    plugin: str
    plugin_version: str
    kind: str
    request: dict[str, Any]
    request_sha256: str
    status_token: str
    status: ChangeRequestStatus
    interview_url: str | None
    interview_json: str | None
    fixed_version: str | None
    install_url: str | None
    created_at: str
    updated_at: str
    fixed_at: str | None

    @property
    def change_request_id(self) -> str:
        """Return the public human-readable request identifier."""

        return f"CR-{self.request_no}"

    @property
    def fixed(self) -> bool:
        """Return whether the correction has been published."""

        return self.status == "fixed"


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _canonical_json(payload: Mapping[str, Any]) -> str:
    try:
        return json.dumps(
            payload,
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        )
    except (TypeError, ValueError) as exc:
        raise ValueError("Change-request content must be JSON serializable.") from exc


def _digest(payload_json: str) -> str:
    return hashlib.sha256(payload_json.encode("utf-8")).hexdigest()


def _request_number(change_request_id: str) -> int:
    match = _CHANGE_REQUEST_ID_PATTERN.fullmatch(change_request_id.strip().upper())
    if match is None:
        raise ChangeRequestNotFoundError("Unknown change request.")
    return int(match.group("number"))


def _default_sqlite_path() -> Path:
    configured = os.getenv(_SQLITE_PATH_ENV, "").strip()
    if configured:
        return Path(configured).expanduser()
    return get_cache_dir("change_requests") / _DEFAULT_SQLITE_FILENAME


def _default_max_records() -> int:
    raw = os.getenv(_MAX_RECORDS_ENV, "").strip()
    if not raw:
        return _DEFAULT_MAX_RECORDS
    try:
        return max(1, int(raw))
    except ValueError:
        return _DEFAULT_MAX_RECORDS


def _repo_root() -> Path:
    here = Path(__file__).resolve()
    for parent in here.parents:
        if (parent / "pyproject.toml").exists() or (parent / ".git").exists():
            return parent
    return Path.cwd()


def _default_manifest_path() -> Path:
    return _repo_root() / "static" / "shared" / "codex-plugin-versions.json"


def _published_install_url(
    *, plugin: str, published_version: str, manifest_path: Path
) -> str:
    try:
        payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise ChangeRequestManifestError(
            "Published plugin manifest is missing."
        ) from exc
    except (OSError, json.JSONDecodeError) as exc:
        raise ChangeRequestManifestError(
            "Published plugin manifest is not readable."
        ) from exc
    if not isinstance(payload, dict):
        raise ChangeRequestManifestError("Published plugin manifest is invalid.")
    plugins = payload.get("plugins")
    entry = plugins.get(plugin) if isinstance(plugins, dict) else None
    if payload.get("schema_version") != 1 or not isinstance(entry, dict):
        raise ChangeRequestManifestError(
            f"Published manifest has no valid entry for {plugin}."
        )
    manifest_version = entry.get("published_version")
    install_url = entry.get("install_url")
    if manifest_version != published_version:
        raise ChangeRequestManifestError(
            f"{plugin} {published_version} is not the locally published version."
        )
    if not isinstance(install_url, str) or not install_url.startswith(
        "https://chatgpt.com/plugins/"
    ):
        raise ChangeRequestManifestError(
            f"Published manifest has no valid install URL for {plugin}."
        )
    return install_url


class ChangeRequestStore:
    """Postgres-backed store with a SQLite fallback for local use and tests."""

    def __init__(
        self,
        *,
        sqlite_path: Path | None = None,
        max_records: int | None = None,
    ) -> None:
        self._use_postgres = sqlite_path is None and is_postgres_enabled()
        self._sqlite_path = sqlite_path or _default_sqlite_path()
        configured_max_records = (
            _default_max_records() if max_records is None else max_records
        )
        self._max_records = max(1, configured_max_records)
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
                    connection.execute(
                        _POSTGRES_SCHEMA_SQL
                        if self._use_postgres
                        else _SQLITE_SCHEMA_SQL
                    )
                    self._ensure_optional_columns(connection)
            except (
                OSError,
                sqlite3.Error,
                psycopg.Error,
                PostgresCommitStateUnknownError,
            ) as exc:
                raise ChangeRequestStoreUnavailableError(
                    "Change-request storage is unavailable."
                ) from exc
            self._schema_ready = True

    def _ensure_optional_columns(self, connection: Any) -> None:
        """Add interview columns when upgrading an existing development store."""

        if self._use_postgres:
            connection.execute(
                "ALTER TABLE mparanza_change_requests "
                "ADD COLUMN IF NOT EXISTS interview_url TEXT"
            )
            connection.execute(
                "ALTER TABLE mparanza_change_requests "
                "ADD COLUMN IF NOT EXISTS interview_json TEXT"
            )
            return
        columns = {
            str(row["name"])
            for row in connection.execute(
                "PRAGMA table_info(mparanza_change_requests)"
            ).fetchall()
        }
        if "interview_url" not in columns:
            connection.execute(
                "ALTER TABLE mparanza_change_requests ADD COLUMN interview_url TEXT"
            )
        if "interview_json" not in columns:
            connection.execute(
                "ALTER TABLE mparanza_change_requests ADD COLUMN interview_json TEXT"
            )

    @staticmethod
    def _record_from_row(row: Mapping[str, Any] | sqlite3.Row) -> ChangeRequestRecord:
        values = dict(row)
        try:
            request = json.loads(str(values["request_json"]))
        except (KeyError, TypeError, json.JSONDecodeError) as exc:
            raise ChangeRequestStoreUnavailableError(
                "Stored change-request content is invalid."
            ) from exc
        if not isinstance(request, dict):
            raise ChangeRequestStoreUnavailableError(
                "Stored change-request content is invalid."
            )
        status = str(values.get("status") or "")
        if status not in {"open", "fixed"}:
            raise ChangeRequestStoreUnavailableError(
                "Stored change-request status is invalid."
            )
        return ChangeRequestRecord(
            request_no=int(values["request_no"]),
            submission_id=str(values["submission_id"]),
            plugin=str(values["plugin"]),
            plugin_version=str(values["plugin_version"]),
            kind=str(values["kind"]),
            request=request,
            request_sha256=str(values["request_sha256"]),
            status_token=str(values["status_token"]),
            status=status,
            interview_url=(
                str(values["interview_url"])
                if values.get("interview_url") is not None
                else None
            ),
            interview_json=(
                str(values["interview_json"])
                if values.get("interview_json") is not None
                else None
            ),
            fixed_version=(
                str(values["fixed_version"])
                if values.get("fixed_version") is not None
                else None
            ),
            install_url=(
                str(values["install_url"])
                if values.get("install_url") is not None
                else None
            ),
            created_at=str(values["created_at"]),
            updated_at=str(values["updated_at"]),
            fixed_at=(
                str(values["fixed_at"]) if values.get("fixed_at") is not None else None
            ),
        )

    @staticmethod
    def _select_number(connection: Any, request_no: int) -> Any:
        return connection.execute(
            "SELECT * FROM mparanza_change_requests WHERE request_no = ?",
            (request_no,),
        ).fetchone()

    @staticmethod
    def _select_submission(connection: Any, submission_id: str) -> Any:
        return connection.execute(
            "SELECT * FROM mparanza_change_requests WHERE submission_id = ?",
            (submission_id,),
        ).fetchone()

    def _lock_submission_admission(self, connection: Any) -> None:
        """Serialize capacity checks because the public intake needs a hard bound."""

        if self._use_postgres:
            connection.disable_transaction_replay()
            connection.execute(
                "LOCK TABLE mparanza_change_requests IN SHARE ROW EXCLUSIVE MODE"
            )
            return
        connection.execute("BEGIN IMMEDIATE")

    @staticmethod
    def _require_voice_interview_record(
        record: ChangeRequestRecord,
        *,
        interview_url: str | None = None,
    ) -> None:
        details = record.request.get("request")
        is_voice_interview = (
            record.kind == "capability"
            and isinstance(details, Mapping)
            and details.get("source") == "voice_interview"
        )
        if not is_voice_interview:
            raise ChangeRequestConflictError(
                "Change request is not a voice-interview capability request."
            )
        if interview_url is not None and record.interview_url != interview_url:
            raise ChangeRequestConflictError(
                "Interview completion does not match the bound change request."
            )

    def submit(self, payload: Mapping[str, Any]) -> ChangeRequestRecord:
        """Insert *payload* once and return its stable receipt record."""

        self._ensure_schema()
        payload_json = _canonical_json(payload)
        request_sha256 = _digest(payload_json)
        submission_id = str(payload.get("submission_id") or "").strip()
        plugin = str(payload.get("plugin") or "").strip()
        plugin_version = str(payload.get("plugin_version") or "").strip()
        kind = str(payload.get("kind") or "").strip()
        if not all((submission_id, plugin, plugin_version, kind)):
            raise ValueError("Change-request envelope is incomplete.")
        status_token = secrets.token_urlsafe(32)
        timestamp = _utc_now()
        insert_sql = """
            INSERT INTO mparanza_change_requests (
                submission_id, plugin, plugin_version, kind, request_json,
                request_sha256, status_token, status, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, 'open', ?, ?)
            ON CONFLICT (submission_id) DO NOTHING
            RETURNING request_no
        """
        try:
            with self._connect() as connection:
                self._lock_submission_admission(connection)
                existing_row = self._select_submission(connection, submission_id)
                if existing_row is not None:
                    existing = self._record_from_row(existing_row)
                    if not hmac.compare_digest(existing.request_sha256, request_sha256):
                        raise ChangeRequestConflictError(
                            "submission_id was already used for different content."
                        )
                    return existing
                count_row = connection.execute(
                    "SELECT COUNT(*) AS record_count FROM mparanza_change_requests"
                ).fetchone()
                record_count = int(dict(count_row)["record_count"])
                if record_count >= self._max_records:
                    raise ChangeRequestCapacityError(
                        "Change-request intake is temporarily at capacity."
                    )
                inserted = connection.execute(
                    insert_sql,
                    (
                        submission_id,
                        plugin,
                        plugin_version,
                        kind,
                        payload_json,
                        request_sha256,
                        status_token,
                        timestamp,
                        timestamp,
                    ),
                ).fetchone()
                if inserted is not None:
                    inserted_values = dict(inserted)
                    row = self._select_number(
                        connection, int(inserted_values["request_no"])
                    )
                else:
                    row = self._select_submission(connection, submission_id)
                if row is None:
                    raise ChangeRequestStoreUnavailableError(
                        "Change-request receipt could not be read after submission."
                    )
                record = self._record_from_row(row)
                if not hmac.compare_digest(record.request_sha256, request_sha256):
                    raise ChangeRequestConflictError(
                        "submission_id was already used for different content."
                    )
                return record
        except (
            OSError,
            sqlite3.Error,
            psycopg.Error,
            PostgresCommitStateUnknownError,
        ) as exc:
            raise ChangeRequestStoreUnavailableError(
                "Change-request storage is unavailable."
            ) from exc

    def get(self, change_request_id: str) -> ChangeRequestRecord | None:
        """Return one operator-visible record, if it exists."""

        try:
            request_no = _request_number(change_request_id)
        except ChangeRequestNotFoundError:
            return None
        self._ensure_schema()
        try:
            with self._connect() as connection:
                row = self._select_number(connection, request_no)
                return self._record_from_row(row) if row is not None else None
        except (
            OSError,
            sqlite3.Error,
            psycopg.Error,
            PostgresCommitStateUnknownError,
        ) as exc:
            raise ChangeRequestStoreUnavailableError(
                "Change-request storage is unavailable."
            ) from exc

    def poll(
        self, change_request_id: str, status_token: str
    ) -> ChangeRequestRecord | None:
        """Return a record only when its private status token matches."""

        return self.poll_many([(change_request_id, status_token)])[0]

    def poll_many(
        self, lookups: Sequence[tuple[str, str]]
    ) -> list[ChangeRequestRecord | None]:
        """Resolve a bounded status batch with one database connection."""

        parsed_numbers: list[int | None] = []
        for change_request_id, _status_token in lookups:
            try:
                parsed_numbers.append(_request_number(change_request_id))
            except ChangeRequestNotFoundError:
                parsed_numbers.append(None)
        request_numbers = sorted(
            {number for number in parsed_numbers if number is not None}
        )
        if not request_numbers:
            return [None for _lookup in lookups]
        self._ensure_schema()
        placeholders = ", ".join("?" for _number in request_numbers)
        try:
            with self._connect() as connection:
                # The interpolation contains only generated ``?`` placeholders;
                # request numbers remain driver-bound parameters.
                rows = connection.execute(
                    "SELECT * FROM mparanza_change_requests "
                    f"WHERE request_no IN ({placeholders})",  # nosec B608
                    tuple(request_numbers),
                ).fetchall()
                records = {
                    record.request_no: record
                    for record in (self._record_from_row(row) for row in rows)
                }
        except (
            OSError,
            sqlite3.Error,
            psycopg.Error,
            PostgresCommitStateUnknownError,
        ) as exc:
            raise ChangeRequestStoreUnavailableError(
                "Change-request storage is unavailable."
            ) from exc
        results: list[ChangeRequestRecord | None] = []
        for number, (_change_request_id, status_token) in zip(
            parsed_numbers, lookups, strict=True
        ):
            record = records.get(number) if number is not None else None
            if record is None or not hmac.compare_digest(
                record.status_token, status_token
            ):
                results.append(None)
            else:
                results.append(record)
        return results

    def list_open(self, *, limit: int = 100) -> list[ChangeRequestRecord]:
        """Return the oldest open requests for operator processing."""

        self._ensure_schema()
        safe_limit = min(max(int(limit), 1), 1_000)
        try:
            with self._connect() as connection:
                rows = connection.execute(
                    """
                    SELECT * FROM mparanza_change_requests
                    WHERE status = 'open'
                    ORDER BY request_no ASC
                    LIMIT ?
                    """,
                    (safe_limit,),
                ).fetchall()
                return [self._record_from_row(row) for row in rows]
        except (
            OSError,
            sqlite3.Error,
            psycopg.Error,
            PostgresCommitStateUnknownError,
        ) as exc:
            raise ChangeRequestStoreUnavailableError(
                "Change-request storage is unavailable."
            ) from exc

    def set_interview_url_if_absent(
        self, change_request_id: str, interview_url: str
    ) -> ChangeRequestRecord:
        """Bind the first hosted interview link to a capability request."""

        request_no = _request_number(change_request_id)
        clean_url = interview_url.strip()
        if not clean_url:
            raise ValueError("Interview URL is required.")
        self._ensure_schema()
        timestamp = _utc_now()
        try:
            with self._connect() as connection:
                row = self._select_number(connection, request_no)
                if row is None:
                    raise ChangeRequestNotFoundError("Unknown change request.")
                current = self._record_from_row(row)
                self._require_voice_interview_record(current)
                connection.execute(
                    """
                    UPDATE mparanza_change_requests
                    SET interview_url = ?, updated_at = ?
                    WHERE request_no = ? AND interview_url IS NULL
                    """,
                    (clean_url, timestamp, request_no),
                )
                row = self._select_number(connection, request_no)
                if row is None:
                    raise ChangeRequestNotFoundError("Unknown change request.")
                return self._record_from_row(row)
        except (
            OSError,
            sqlite3.Error,
            psycopg.Error,
            PostgresCommitStateUnknownError,
        ) as exc:
            raise ChangeRequestStoreUnavailableError(
                "Change-request storage is unavailable."
            ) from exc

    def attach_interview_completion(
        self,
        change_request_id: str,
        payload: Mapping[str, Any],
        *,
        interview_url: str,
    ) -> ChangeRequestRecord:
        """Attach one idempotent hosted-interview completion to its request."""

        request_no = _request_number(change_request_id)
        clean_url = interview_url.strip()
        if not clean_url:
            raise ValueError("Interview URL is required.")
        interview_json = _canonical_json(payload)
        self._ensure_schema()
        timestamp = _utc_now()
        try:
            with self._connect() as connection:
                row = self._select_number(connection, request_no)
                if row is None:
                    raise ChangeRequestNotFoundError("Unknown change request.")
                current = self._record_from_row(row)
                self._require_voice_interview_record(current, interview_url=clean_url)
                connection.execute(
                    """
                    UPDATE mparanza_change_requests
                    SET interview_json = ?, updated_at = ?
                    WHERE request_no = ? AND interview_json IS NULL
                    """,
                    (interview_json, timestamp, request_no),
                )
                row = self._select_number(connection, request_no)
                if row is None:
                    raise ChangeRequestNotFoundError("Unknown change request.")
                record = self._record_from_row(row)
                if record.interview_json != interview_json:
                    raise ChangeRequestConflictError(
                        "Change request already has a different interview completion."
                    )
                return record
        except (
            OSError,
            sqlite3.Error,
            psycopg.Error,
            PostgresCommitStateUnknownError,
        ) as exc:
            raise ChangeRequestStoreUnavailableError(
                "Change-request storage is unavailable."
            ) from exc

    def mark_fixed(
        self,
        change_request_id: str,
        *,
        published_version: str,
        manifest_path: Path | None = None,
    ) -> ChangeRequestRecord:
        """Mark a request fixed only after its plugin release is published."""

        request_no = _request_number(change_request_id)
        version = published_version.strip()
        if not version:
            raise ChangeRequestManifestError("Published version is required.")
        self._ensure_schema()
        current = self.get(change_request_id)
        if current is None:
            raise ChangeRequestNotFoundError("Unknown change request.")
        install_url = _published_install_url(
            plugin=current.plugin,
            published_version=version,
            manifest_path=manifest_path or _default_manifest_path(),
        )
        if current.fixed:
            if current.fixed_version != version or current.install_url != install_url:
                raise ChangeRequestConflictError(
                    "Change request was already fixed by another published release."
                )
            return current
        timestamp = _utc_now()
        try:
            with self._connect() as connection:
                connection.execute(
                    """
                    UPDATE mparanza_change_requests
                    SET status = 'fixed', fixed_version = ?, install_url = ?,
                        fixed_at = ?, updated_at = ?
                    WHERE request_no = ? AND status = 'open'
                    """,
                    (version, install_url, timestamp, timestamp, request_no),
                )
                row = self._select_number(connection, request_no)
                if row is None:
                    raise ChangeRequestNotFoundError("Unknown change request.")
                updated = self._record_from_row(row)
                if (
                    not updated.fixed
                    or updated.fixed_version != version
                    or updated.install_url != install_url
                ):
                    raise ChangeRequestConflictError(
                        "Change request was fixed concurrently by another release."
                    )
                return updated
        except (
            OSError,
            sqlite3.Error,
            psycopg.Error,
            PostgresCommitStateUnknownError,
        ) as exc:
            raise ChangeRequestStoreUnavailableError(
                "Change-request storage is unavailable."
            ) from exc


@lru_cache(maxsize=1)
def get_change_request_store() -> ChangeRequestStore:
    """Return the process-wide change-request store."""

    return ChangeRequestStore()
