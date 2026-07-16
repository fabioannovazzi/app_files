from __future__ import annotations

import os
import re
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, Sequence

POSTGRES_BACKEND_VALUE = "postgres"
DEFAULT_POSTGRES_RETRY_ATTEMPTS = 3
DEFAULT_POSTGRES_RETRY_BACKOFF_SECONDS = 0.5
DICT_ROW_FACTORY: object = object()

_QUESTION_MARK_REPLACEMENT = "%s"
_POSTGRES_TRANSIENT_MESSAGE_RE = re.compile(
    "|".join(
        [
            "connection",
            "server closed",
            "terminating connection",
            "could not receive data",
            "could not send data",
            "broken pipe",
            "connection refused",
            "operation timed out",
            "operation not permitted",
            "ssl syscall",
            "eof detected",
        ]
    ),
    flags=re.IGNORECASE,
)
_READ_ONLY_SQL_RE = re.compile(
    r"^\s*(SELECT|WITH|PRAGMA|EXPLAIN|SHOW)\b",
    flags=re.IGNORECASE,
)

_INSERT_OR_IGNORE_RE = re.compile(
    r"^\s*INSERT\s+OR\s+IGNORE\s+INTO\s+",
    flags=re.IGNORECASE,
)
_INSERT_OR_REPLACE_RE = re.compile(
    r"^\s*INSERT\s+OR\s+REPLACE\s+INTO\s+",
    flags=re.IGNORECASE,
)
_INSERT_TABLE_COLUMNS_RE = re.compile(
    r"^\s*INSERT\s+INTO\s+(?P<table>[A-Za-z_][A-Za-z0-9_]*)\s*\((?P<columns>.*?)\)\s*VALUES\s*\(",
    flags=re.IGNORECASE | re.DOTALL,
)

_PRIMARY_KEYS: dict[str, tuple[str, ...]] = {
    "canonical_products": ("canonical_id",),
    "parent_products": ("retailer", "parent_product_id"),
    "pdp_attribute_cache": ("name",),
    "pdp_attribute_values": (
        "retailer",
        "row_type",
        "parent_product_id",
        "variant_id",
        "category_key",
        "attribute_id",
        "source",
    ),
    "pdp_attributes_deterministic": (
        "retailer",
        "row_type",
        "parent_product_id",
        "variant_id",
        "category_key",
        "attribute_id",
    ),
    "pdp_attributes_deterministic_explicit": (
        "retailer",
        "row_type",
        "parent_product_id",
        "variant_id",
        "category_key",
        "attribute_id",
    ),
    "pdp_attributes_llm": (
        "retailer",
        "row_type",
        "parent_product_id",
        "variant_id",
        "category_key",
        "attribute_id",
    ),
    "pdp_deterministic_policy_config_versions": ("version",),
    "pdp_deterministic_policy_drafts": ("draft_name",),
    "pdp_explicit_precision_metrics": ("run_id", "category_key", "attribute_id"),
    "pdp_explicit_rule_candidates": ("candidate_id",),
    "pdp_explicit_rule_config_versions": ("version",),
    "pdp_failures": ("run_id", "retailer", "pdp_url"),
    "pdp_taxonomy_config_versions": ("version",),
    "pdp_taxonomy_drafts": ("draft_name",),
    "retailer_filter_observations": (
        "crawl_ts",
        "retailer",
        "category_key",
        "filter_family",
        "filter_value",
        "pdp_url",
        "page",
        "position",
    ),
    "retailer_filter_surfaces": (
        "crawl_ts",
        "retailer",
        "category_key",
        "filter_family",
        "filter_value",
        "filter_url",
    ),
    "retailer_listing_observations": (
        "crawl_ts",
        "retailer",
        "category_key",
        "source_surface",
        "sort_mode",
        "page",
        "position",
        "pdp_url",
    ),
    "retailer_sitemap_observations": ("crawl_ts", "retailer", "sitemap_source", "url"),
    "review_queue_items": ("queue_item_id",),
    "run_logs": ("run_id",),
    "variants": ("retailer", "variant_id"),
}


def pdp_postgres_url_from_env() -> str | None:
    """Return the configured PDP Postgres URL, if Postgres is enabled."""

    backend = os.environ.get("PDP_STORE_BACKEND", "").strip().lower()
    pdp_url = os.environ.get("PDP_DATABASE_URL", "").strip()
    if pdp_url:
        return pdp_url
    if backend == POSTGRES_BACKEND_VALUE:
        return os.environ.get("DATABASE_URL", "").strip() or None
    return None


def is_postgres_enabled() -> bool:
    """Return whether the PDP store should use Postgres."""

    return bool(pdp_postgres_url_from_env())


def require_pdp_postgres_url() -> str:
    """Return the PDP Postgres URL or fail fast."""

    database_url = pdp_postgres_url_from_env()
    if database_url:
        return database_url
    raise RuntimeError(
        "PDP Postgres is not configured. Set PDP_DATABASE_URL or set "
        "PDP_STORE_BACKEND=postgres with DATABASE_URL, and make sure the SSH tunnel "
        "is active. The PDP workflow requires the Postgres store."
    )


class PostgresCommitStateUnknownError(RuntimeError):
    """Raised when a connection is lost while waiting for COMMIT."""


@dataclass(frozen=True, slots=True)
class _RecordedOperation:
    sql: str
    params: Sequence[Any] | None
    many: bool = False


def _postgres_retry_attempts() -> int:
    raw = os.environ.get("PDP_POSTGRES_RETRY_ATTEMPTS", "").strip()
    if not raw:
        return DEFAULT_POSTGRES_RETRY_ATTEMPTS
    try:
        return max(1, int(raw))
    except ValueError:
        return DEFAULT_POSTGRES_RETRY_ATTEMPTS


def _postgres_retry_backoff_seconds() -> float:
    raw = os.environ.get("PDP_POSTGRES_RETRY_BACKOFF_SECONDS", "").strip()
    if not raw:
        return DEFAULT_POSTGRES_RETRY_BACKOFF_SECONDS
    try:
        return max(0.0, float(raw))
    except ValueError:
        return DEFAULT_POSTGRES_RETRY_BACKOFF_SECONDS


def is_transient_postgres_error(exc: BaseException) -> bool:
    """Return whether an exception looks like a retryable connection failure."""

    exception_name = exc.__class__.__name__.lower()
    if exception_name in {"operationalerror", "interfaceerror"}:
        return True
    try:
        import psycopg
    except ModuleNotFoundError:  # pragma: no cover - psycopg is optional in tests.
        psycopg = None  # type: ignore[assignment]
    if psycopg is not None and isinstance(
        exc, (psycopg.OperationalError, psycopg.InterfaceError)
    ):
        return True
    return bool(_POSTGRES_TRANSIENT_MESSAGE_RE.search(str(exc)))


def _connect_psycopg(database_url: str) -> Any:
    import psycopg

    return psycopg.connect(database_url)


def _sleep_before_retry(attempt: int) -> None:
    delay = _postgres_retry_backoff_seconds()
    if delay <= 0:
        return
    time.sleep(delay * attempt)


def _connect_with_retry(database_url: str) -> Any:
    attempts = _postgres_retry_attempts()
    for attempt in range(1, attempts + 1):
        try:
            return _connect_psycopg(database_url)
        except Exception as exc:
            if attempt >= attempts or not is_transient_postgres_error(exc):
                raise
            _sleep_before_retry(attempt)
    raise RuntimeError("Postgres connection retry loop exhausted.")


def pdp_database_exists(pdp_store_path: str | Path) -> bool:
    """Return whether the configured PDP database is available."""

    _ = Path(pdp_store_path)
    return is_postgres_enabled()


def _translate_placeholders(sql: str) -> str:
    result: list[str] = []
    in_single_quote = False
    in_double_quote = False
    index = 0
    while index < len(sql):
        char = sql[index]
        if char == "'" and not in_double_quote:
            result.append(char)
            if in_single_quote and index + 1 < len(sql) and sql[index + 1] == "'":
                index += 1
                result.append(sql[index])
            else:
                in_single_quote = not in_single_quote
        elif char == '"' and not in_single_quote:
            in_double_quote = not in_double_quote
            result.append(char)
        elif char == "?" and not in_single_quote and not in_double_quote:
            result.append(_QUESTION_MARK_REPLACEMENT)
        else:
            result.append(char)
        index += 1
    return "".join(result)


def _split_insert_columns(columns_sql: str) -> tuple[str, ...]:
    return tuple(
        column.strip().strip('"') for column in columns_sql.split(",") if column.strip()
    )


def _append_replace_upsert(sql: str) -> str:
    match = _INSERT_TABLE_COLUMNS_RE.search(sql)
    if match is None:
        raise ValueError(f"Cannot translate INSERT OR REPLACE statement: {sql[:120]}")
    table = match.group("table")
    primary_keys = _PRIMARY_KEYS.get(table)
    if not primary_keys:
        raise ValueError(f"Missing Postgres primary key metadata for table {table}.")
    columns = _split_insert_columns(match.group("columns"))
    update_columns = [column for column in columns if column not in primary_keys]
    conflict_target = ", ".join(primary_keys)
    if not update_columns:
        return f"{sql} ON CONFLICT ({conflict_target}) DO NOTHING"
    assignments = ", ".join(
        f"{column} = excluded.{column}" for column in update_columns
    )
    return f"{sql} ON CONFLICT ({conflict_target}) DO UPDATE SET {assignments}"


def translate_portable_sql_to_postgres(sql: str) -> str:
    """Translate the portable SQL subset used by PDPStore to Postgres SQL."""

    translated = sql.strip()
    insert_or_ignore = _INSERT_OR_IGNORE_RE.search(translated) is not None
    insert_or_replace = _INSERT_OR_REPLACE_RE.search(translated) is not None
    translated = _INSERT_OR_IGNORE_RE.sub("INSERT INTO ", translated, count=1)
    translated = _INSERT_OR_REPLACE_RE.sub("INSERT INTO ", translated, count=1)
    translated = _translate_placeholders(translated)
    if insert_or_ignore:
        translated = f"{translated} ON CONFLICT DO NOTHING"
    if insert_or_replace:
        translated = _append_replace_upsert(translated)
    return translated


def _clean_value(value: object) -> object:
    if isinstance(value, str) and "\x00" in value:
        return value.replace("\x00", "")
    return value


def _clean_params(params: Sequence[Any] | None) -> Sequence[Any] | None:
    if params is None:
        return None
    return tuple(_clean_value(value) for value in params)


class PostgresCompatCursor:
    """Small cursor wrapper exposing the DB-API cursor subset used by PDP code."""

    def __init__(
        self,
        connection: PostgresCompatConnection,
        cursor: Any,
        operation: _RecordedOperation | None = None,
    ):
        self._connection = connection
        self._cursor = cursor
        self._operation = operation

    @property
    def rowcount(self) -> int:
        return int(self._cursor.rowcount or 0)

    @property
    def description(self) -> Any:
        return self._cursor.description

    def execute(
        self,
        sql: str,
        params: Sequence[Any] | None = None,
    ) -> PostgresCompatCursor:
        operation = _RecordedOperation(
            sql=translate_portable_sql_to_postgres(sql),
            params=_clean_params(params),
        )
        self._cursor = self._connection._execute_operation(  # noqa: SLF001
            operation,
            cursor=self._cursor,
        )
        self._operation = operation
        return self

    def fetchone(self) -> Any:
        try:
            return self._cursor.fetchone()
        except Exception as exc:
            if self._operation is None or not is_transient_postgres_error(exc):
                raise
            if not self._connection._transaction_replay_enabled:  # noqa: SLF001
                self._connection._close_broken_connection()  # noqa: SLF001
                raise
            self._cursor = self._connection._replay_read_operation(  # noqa: SLF001
                self._operation
            )
            return self._cursor.fetchone()

    def fetchall(self) -> list[Any]:
        try:
            return list(self._cursor.fetchall())
        except Exception as exc:
            if self._operation is None or not is_transient_postgres_error(exc):
                raise
            if not self._connection._transaction_replay_enabled:  # noqa: SLF001
                self._connection._close_broken_connection()  # noqa: SLF001
                raise
            self._cursor = self._connection._replay_read_operation(  # noqa: SLF001
                self._operation
            )
            return list(self._cursor.fetchall())

    def close(self) -> None:
        self._cursor.close()


class PostgresCompatConnection:
    """Connection wrapper exposing the DB-API connection subset used by PDP code."""

    row_factory: object | None = None

    def __init__(self, database_url: str):
        self._database_url = database_url
        self._conn = _connect_with_retry(database_url)
        self._transaction_log: list[_RecordedOperation] = []
        self._transaction_replay_enabled = True

    def __enter__(self) -> PostgresCompatConnection:
        return self

    def __exit__(
        self,
        exc_type: object,
        exc: object,
        traceback: object,
    ) -> None:
        try:
            if exc_type is None:
                self.commit()
            else:
                try:
                    self._conn.rollback()
                except Exception:
                    pass
        finally:
            self.close()

    def cursor(self) -> PostgresCompatCursor:
        return PostgresCompatCursor(self, self._new_cursor())

    def disable_transaction_replay(self) -> None:
        """Propagate transient errors instead of replaying this transaction."""

        if self._transaction_log:
            raise RuntimeError(
                "Transaction replay must be disabled before the first mutation"
            )
        self._transaction_replay_enabled = False

    def _new_cursor(self) -> Any:
        if self.row_factory is DICT_ROW_FACTORY:
            from psycopg.rows import dict_row

            return self._conn.cursor(row_factory=dict_row)
        return self._conn.cursor()

    def _is_mutating_operation(self, operation: _RecordedOperation) -> bool:
        return not _READ_ONLY_SQL_RE.search(operation.sql)

    def _execute_cursor_operation(
        self,
        cursor: Any,
        operation: _RecordedOperation,
    ) -> Any:
        if operation.many:
            cursor.executemany(operation.sql, operation.params or [])
        elif operation.params is None:
            cursor.execute(operation.sql)
        else:
            cursor.execute(operation.sql, operation.params)
        return cursor

    def _close_broken_connection(self) -> None:
        try:
            self._conn.close()
        except Exception:
            pass

    def _replace_connection(self) -> None:
        self._close_broken_connection()
        self._conn = _connect_with_retry(self._database_url)

    def _replay_operations(
        self,
        operations: Sequence[_RecordedOperation],
    ) -> Any:
        attempts = _postgres_retry_attempts()
        for attempt in range(1, attempts + 1):
            try:
                self._replace_connection()
                replay_cursor = None
                for operation in operations:
                    replay_cursor = self._execute_cursor_operation(
                        self._new_cursor(),
                        operation,
                    )
                return replay_cursor or self._new_cursor()
            except Exception as exc:
                self._close_broken_connection()
                if attempt >= attempts or not is_transient_postgres_error(exc):
                    raise
                _sleep_before_retry(attempt)
        raise RuntimeError("Postgres replay retry loop exhausted.")

    def _execute_operation(
        self,
        operation: _RecordedOperation,
        *,
        cursor: Any | None = None,
    ) -> Any:
        target_cursor = cursor or self._new_cursor()
        mutating = self._is_mutating_operation(operation)
        try:
            executed_cursor = self._execute_cursor_operation(target_cursor, operation)
        except Exception as exc:
            if not is_transient_postgres_error(exc):
                raise
            if not self._transaction_replay_enabled:
                self._close_broken_connection()
                raise
            replay_operations = (
                [*self._transaction_log, operation]
                if mutating or self._transaction_log
                else [operation]
            )
            executed_cursor = self._replay_operations(replay_operations)
        if mutating:
            self._transaction_log.append(operation)
        return executed_cursor

    def _replay_read_operation(self, operation: _RecordedOperation) -> Any:
        return self._replay_operations([*self._transaction_log, operation])

    def execute(
        self,
        sql: str,
        params: Sequence[Any] | None = None,
    ) -> PostgresCompatCursor:
        cursor = self.cursor()
        return cursor.execute(sql, params)

    def executemany(
        self, sql: str, rows: Iterable[Sequence[Any]]
    ) -> PostgresCompatCursor:
        cursor = self.cursor()
        operation = _RecordedOperation(
            sql=translate_portable_sql_to_postgres(sql),
            params=tuple(_clean_params(row) or () for row in rows),
            many=True,
        )
        cursor._cursor = self._execute_operation(operation, cursor=cursor._cursor)
        cursor._operation = operation
        return cursor

    def commit(self) -> None:
        try:
            self._conn.commit()
        except Exception as exc:
            if not is_transient_postgres_error(exc):
                raise
            self._close_broken_connection()
            raise PostgresCommitStateUnknownError(
                "Postgres connection was lost while waiting for COMMIT. "
                "The transaction may or may not have committed; verify the "
                "expected rows before rerunning the job."
            ) from exc
        self._transaction_log.clear()

    def close(self) -> None:
        self._conn.close()


def connect_pdp_database(
    pdp_store_path: str | Path,
) -> PostgresCompatConnection:
    """Return a Postgres connection for PDP runtime data."""

    _ = Path(pdp_store_path)
    return PostgresCompatConnection(require_pdp_postgres_url())


__all__ = [
    "DICT_ROW_FACTORY",
    "POSTGRES_BACKEND_VALUE",
    "PostgresCommitStateUnknownError",
    "PostgresCompatConnection",
    "PostgresCompatCursor",
    "connect_pdp_database",
    "is_postgres_enabled",
    "is_transient_postgres_error",
    "pdp_database_exists",
    "pdp_postgres_url_from_env",
    "require_pdp_postgres_url",
    "translate_portable_sql_to_postgres",
]
