from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from modules.pdp.postgres_compat import (
    PostgresCommitStateUnknownError,
    PostgresCompatConnection,
    connect_pdp_database,
    pdp_database_exists,
    require_pdp_postgres_url,
    translate_portable_sql_to_postgres,
)


class OperationalError(Exception):
    pass


class _FakeCursor:
    description = None
    rowcount = 1

    def __init__(self, connection: _FakeConnection):
        self.connection = connection
        self.rows = [("ok",)]

    def execute(self, sql: str, params: Any = None) -> None:
        self.connection.operations.append(("execute", sql, params))
        if self.connection.fail_next_execute:
            self.connection.fail_next_execute = False
            raise OperationalError("server closed the connection unexpectedly")

    def executemany(self, sql: str, rows: Any) -> None:
        materialized_rows = tuple(rows)
        self.connection.operations.append(("executemany", sql, materialized_rows))
        if self.connection.fail_next_execute:
            self.connection.fail_next_execute = False
            raise OperationalError("could not send data to server")

    def fetchone(self) -> tuple[str]:
        if self.connection.fail_next_fetchone:
            self.connection.fail_next_fetchone = False
            raise OperationalError("server closed the connection during fetchone")
        return self.rows[0]

    def fetchall(self) -> list[tuple[str]]:
        if self.connection.fail_next_fetchall:
            self.connection.fail_next_fetchall = False
            raise OperationalError("server closed the connection during fetchall")
        return list(self.rows)

    def close(self) -> None:
        self.connection.cursor_closed = True


class _FakeConnection:
    def __init__(
        self,
        *,
        fail_next_execute: bool = False,
        fail_next_fetchone: bool = False,
        fail_next_fetchall: bool = False,
        fail_commit: bool = False,
    ):
        self.fail_next_execute = fail_next_execute
        self.fail_next_fetchone = fail_next_fetchone
        self.fail_next_fetchall = fail_next_fetchall
        self.fail_commit = fail_commit
        self.operations: list[tuple[str, str, Any]] = []
        self.closed = False
        self.committed = False
        self.rolled_back = False
        self.cursor_closed = False

    def cursor(self, **_kwargs: Any) -> _FakeCursor:
        return _FakeCursor(self)

    def commit(self) -> None:
        if self.fail_commit:
            raise OperationalError("connection lost during commit")
        self.committed = True

    def rollback(self) -> None:
        self.rolled_back = True

    def close(self) -> None:
        self.closed = True


def test_require_pdp_postgres_url_raises_without_database_url(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("PDP_DATABASE_URL", raising=False)
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.delenv("PDP_STORE_BACKEND", raising=False)

    with pytest.raises(RuntimeError, match="requires the Postgres store"):
        require_pdp_postgres_url()


def test_connect_pdp_database_requires_postgres(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.delenv("PDP_DATABASE_URL", raising=False)
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.delenv("PDP_STORE_BACKEND", raising=False)

    with pytest.raises(RuntimeError, match="PDP Postgres is not configured"):
        connect_pdp_database(tmp_path / "pdp_store")


def test_pdp_database_exists_requires_postgres_env(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    pdp_store_path = tmp_path / "pdp_store"
    pdp_store_path.touch()
    monkeypatch.delenv("PDP_DATABASE_URL", raising=False)
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.delenv("PDP_STORE_BACKEND", raising=False)

    assert pdp_database_exists(pdp_store_path) is False


def test_translate_portable_sql_to_postgres_replaces_placeholders() -> None:
    sql = "SELECT * FROM parent_products WHERE retailer = ? AND title_raw != '?'"

    translated = translate_portable_sql_to_postgres(sql)

    assert translated == (
        "SELECT * FROM parent_products WHERE retailer = %s AND title_raw != '?'"
    )


def test_translate_portable_sql_to_postgres_maps_insert_or_ignore() -> None:
    sql = """
        INSERT OR IGNORE INTO parent_products (
            retailer, parent_product_id, title_raw
        ) VALUES (?, ?, ?)
    """

    translated = translate_portable_sql_to_postgres(sql)

    assert translated.startswith("INSERT INTO parent_products")
    assert "VALUES (%s, %s, %s)" in translated
    assert translated.endswith("ON CONFLICT DO NOTHING")


def test_translate_portable_sql_to_postgres_maps_insert_or_replace() -> None:
    sql = """
        INSERT OR REPLACE INTO run_logs (
            run_id, retailer, profile, parsed_count
        ) VALUES (?, ?, ?, ?)
    """

    translated = translate_portable_sql_to_postgres(sql)

    assert translated.startswith("INSERT INTO run_logs")
    assert "ON CONFLICT (run_id) DO UPDATE SET" in translated
    assert "retailer = excluded.retailer" in translated
    assert "profile = excluded.profile" in translated
    assert "run_id = excluded.run_id" not in translated


def test_postgres_connection_retries_initial_connect(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    connections = [_FakeConnection()]
    attempts = 0

    def fake_connect(_database_url: str) -> _FakeConnection:
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            raise OperationalError("connection refused")
        return connections[0]

    monkeypatch.setenv("PDP_POSTGRES_RETRY_BACKOFF_SECONDS", "0")
    monkeypatch.setattr("modules.pdp.postgres_compat._connect_psycopg", fake_connect)

    conn = PostgresCompatConnection("dbname=test")
    conn.close()

    assert attempts == 2
    assert connections[0].closed is True


def test_postgres_connection_replays_uncommitted_transaction_after_execute_loss(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    first = _FakeConnection(fail_next_execute=True)
    second = _FakeConnection()
    connections = [first, second]

    def fake_connect(_database_url: str) -> _FakeConnection:
        return connections.pop(0)

    monkeypatch.setenv("PDP_POSTGRES_RETRY_BACKOFF_SECONDS", "0")
    monkeypatch.setattr("modules.pdp.postgres_compat._connect_psycopg", fake_connect)

    conn = PostgresCompatConnection("dbname=test")
    conn.execute(
        """
        INSERT OR REPLACE INTO run_logs (
            run_id, retailer, profile, parsed_count
        ) VALUES (?, ?, ?, ?)
        """,
        ("run-1", "ulta", "ulta_lipstick", 1),
    )
    conn.commit()

    assert first.closed is True
    assert second.committed is True
    assert len(second.operations) == 1
    assert second.operations[0][0] == "execute"
    assert "ON CONFLICT (run_id) DO UPDATE SET" in second.operations[0][1]


def test_postgres_connection_replays_uncommitted_executemany_after_connection_loss(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    first = _FakeConnection(fail_next_execute=True)
    second = _FakeConnection()
    connections = [first, second]

    def fake_connect(_database_url: str) -> _FakeConnection:
        return connections.pop(0)

    monkeypatch.setenv("PDP_POSTGRES_RETRY_BACKOFF_SECONDS", "0")
    monkeypatch.setattr("modules.pdp.postgres_compat._connect_psycopg", fake_connect)

    conn = PostgresCompatConnection("dbname=test")
    conn.executemany(
        """
        INSERT OR REPLACE INTO run_logs (
            run_id, retailer, profile, parsed_count
        ) VALUES (?, ?, ?, ?)
        """,
        [
            ("run-1", "ulta", "ulta_lipstick", 1),
            ("run-2", "ulta", "ulta_blush", 2),
        ],
    )
    conn.commit()

    assert first.closed is True
    assert second.committed is True
    assert second.operations[0][0] == "executemany"
    assert second.operations[0][2] == (
        ("run-1", "ulta", "ulta_lipstick", 1),
        ("run-2", "ulta", "ulta_blush", 2),
    )


def test_postgres_connection_disabled_replay_propagates_transient_execute_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    connection = _FakeConnection(fail_next_execute=True)
    connect_attempts = 0

    def fake_connect(_database_url: str) -> _FakeConnection:
        nonlocal connect_attempts
        connect_attempts += 1
        return connection

    monkeypatch.setenv("PDP_POSTGRES_RETRY_BACKOFF_SECONDS", "0")
    monkeypatch.setattr("modules.pdp.postgres_compat._connect_psycopg", fake_connect)
    conn = PostgresCompatConnection("dbname=test")
    conn.disable_transaction_replay()

    with pytest.raises(OperationalError, match="server closed"):
        conn.execute("INSERT INTO run_logs (run_id) VALUES (?)", ("run-1",))

    assert connect_attempts == 1
    assert connection.closed is True
    assert len(connection.operations) == 1


@pytest.mark.parametrize(
    ("fetch_method", "failure_flag"),
    [
        pytest.param("fetchone", "fail_next_fetchone", id="fetchone"),
        pytest.param("fetchall", "fail_next_fetchall", id="fetchall"),
    ],
)
def test_postgres_connection_disabled_replay_propagates_transient_fetch_error(
    monkeypatch: pytest.MonkeyPatch,
    fetch_method: str,
    failure_flag: str,
) -> None:
    connection = _FakeConnection(**{failure_flag: True})
    connect_attempts = 0

    def fake_connect(_database_url: str) -> _FakeConnection:
        nonlocal connect_attempts
        connect_attempts += 1
        return connection

    monkeypatch.setenv("PDP_POSTGRES_RETRY_BACKOFF_SECONDS", "0")
    monkeypatch.setattr("modules.pdp.postgres_compat._connect_psycopg", fake_connect)
    conn = PostgresCompatConnection("dbname=test")
    conn.disable_transaction_replay()
    cursor = conn.execute("SELECT 1")

    with pytest.raises(OperationalError, match="server closed"):
        getattr(cursor, fetch_method)()

    assert connect_attempts == 1
    assert connection.closed is True
    assert len(connection.operations) == 1


def test_postgres_connection_does_not_retry_unknown_commit_state(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    connection = _FakeConnection(fail_commit=True)

    def fake_connect(_database_url: str) -> _FakeConnection:
        return connection

    monkeypatch.setenv("PDP_POSTGRES_RETRY_BACKOFF_SECONDS", "0")
    monkeypatch.setattr("modules.pdp.postgres_compat._connect_psycopg", fake_connect)

    conn = PostgresCompatConnection("dbname=test")
    conn.execute("INSERT INTO run_logs (run_id) VALUES (?)", ("run-1",))

    with pytest.raises(PostgresCommitStateUnknownError):
        conn.commit()

    assert connection.closed is True
