from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from pathlib import Path
from uuid import uuid4

import pytest

import modules.change_requests.store as store_module
from modules.change_requests.store import (
    ChangeRequestCapacityError,
    ChangeRequestConflictError,
    ChangeRequestManifestError,
    ChangeRequestStore,
)


def _submission(
    *,
    submission_id: str | None = None,
    plugin: str = "clara",
    kind: str = "problem",
    voice_interview: bool = False,
) -> dict[str, object]:
    request = {
        "observed": "The synthetic input was rejected.",
        "expected": "The synthetic input should be accepted.",
    }
    if voice_interview:
        request["source"] = "voice_interview"
    return {
        "schema_version": 1,
        "submission_id": submission_id or str(uuid4()),
        "kind": kind,
        "plugin": plugin,
        "plugin_version": "1.0.0",
        "request": request,
    }


def _write_manifest(path: Path, *, plugin: str, version: str) -> Path:
    path.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "plugins": {
                    plugin: {
                        "published_version": version,
                        "install_url": f"https://chatgpt.com/plugins/{plugin}",
                    }
                },
            }
        ),
        encoding="utf-8",
    )
    return path


def test_submit_retry_returns_same_change_request_and_status_token(
    tmp_path: Path,
) -> None:
    store = ChangeRequestStore(sqlite_path=tmp_path / "change-requests.sqlite3")
    payload = _submission()

    first = store.submit(payload)
    retried = store.submit(payload)

    assert first.change_request_id == "CR-1"
    assert retried.change_request_id == first.change_request_id
    assert retried.status_token == first.status_token
    assert retried.request_sha256 == first.request_sha256
    assert store.list_open() == [first]


def test_submit_rejects_reused_submission_id_with_different_content(
    tmp_path: Path,
) -> None:
    store = ChangeRequestStore(sqlite_path=tmp_path / "change-requests.sqlite3")
    submission_id = str(uuid4())
    first = _submission(submission_id=submission_id)
    changed = _submission(submission_id=submission_id)
    changed["request"] = {"observed": "Different content"}
    store.submit(first)

    with pytest.raises(ChangeRequestConflictError, match="different content"):
        store.submit(changed)


def test_poll_requires_the_matching_status_token(tmp_path: Path) -> None:
    store = ChangeRequestStore(sqlite_path=tmp_path / "change-requests.sqlite3")
    record = store.submit(_submission())

    found = store.poll(record.change_request_id, record.status_token)
    missing = store.poll(record.change_request_id, "wrong-token-value-long-enough")

    assert found == record
    assert missing is None


def test_interview_link_and_completion_are_idempotently_bound(
    tmp_path: Path,
) -> None:
    store = ChangeRequestStore(sqlite_path=tmp_path / "change-requests.sqlite3")
    record = store.submit(_submission(kind="capability", voice_interview=True))
    interview_url = "https://mparanza.com/case-notes/interview/first"

    linked = store.set_interview_url_if_absent(
        record.change_request_id,
        interview_url,
    )
    retried_link = store.set_interview_url_if_absent(
        record.change_request_id,
        "https://mparanza.com/case-notes/interview/retry",
    )
    completion = {"summary": "Add a compact comparison table."}
    completed = store.attach_interview_completion(
        record.change_request_id,
        completion,
        interview_url=interview_url,
    )
    retried_completion = store.attach_interview_completion(
        record.change_request_id,
        completion,
        interview_url=interview_url,
    )

    assert linked.interview_url.endswith("/first")
    assert retried_link.interview_url == linked.interview_url
    assert json.loads(completed.interview_json or "{}") == completion
    assert retried_completion.interview_json == completed.interview_json
    with pytest.raises(ChangeRequestConflictError, match="different interview"):
        store.attach_interview_completion(
            record.change_request_id,
            {"summary": "A conflicting completion."},
            interview_url=interview_url,
        )


def test_interview_completion_requires_voice_kind_and_exact_bound_url(
    tmp_path: Path,
) -> None:
    store = ChangeRequestStore(sqlite_path=tmp_path / "change-requests.sqlite3")
    problem = store.submit(_submission())
    capability = store.submit(_submission(kind="capability", voice_interview=True))
    interview_url = "https://mparanza.com/case-notes/interview/owned"
    store.set_interview_url_if_absent(capability.change_request_id, interview_url)

    with pytest.raises(ChangeRequestConflictError, match="not a voice-interview"):
        store.set_interview_url_if_absent(problem.change_request_id, interview_url)
    with pytest.raises(ChangeRequestConflictError, match="does not match"):
        store.attach_interview_completion(
            capability.change_request_id,
            {"summary": "Injected"},
            interview_url="https://mparanza.com/case-notes/interview/attacker",
        )


def test_submit_enforces_capacity_but_keeps_idempotent_retry(tmp_path: Path) -> None:
    store = ChangeRequestStore(
        sqlite_path=tmp_path / "change-requests.sqlite3", max_records=1
    )
    payload = _submission()
    first = store.submit(payload)

    retried = store.submit(payload)

    assert retried == first
    with pytest.raises(ChangeRequestCapacityError, match="at capacity"):
        store.submit(_submission())


def test_submit_disables_postgres_replay_before_capacity_transaction(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    events: list[str] = []

    class Result:
        def __init__(self, row: dict[str, object] | None = None) -> None:
            self._row = row

        def fetchone(self) -> dict[str, object] | None:
            return self._row

    class Connection:
        def disable_transaction_replay(self) -> None:
            events.append("disable_replay")

        def execute(self, sql: str, params: tuple[object, ...] | None = None) -> Result:
            del params
            statement = " ".join(sql.split())
            if statement.startswith("LOCK TABLE"):
                events.append("lock")
                return Result()
            if "WHERE submission_id = ?" in statement:
                events.append("select_submission")
                return Result()
            if statement.startswith("SELECT COUNT(*)"):
                events.append("count")
                return Result({"record_count": 0})
            if statement.startswith("INSERT INTO"):
                events.append("insert")
                raise store_module.psycopg.OperationalError("connection lost")
            raise AssertionError(f"Unexpected SQL: {statement}")

    connection = Connection()

    @contextmanager
    def fake_connect():
        yield connection

    monkeypatch.setattr(store_module, "is_postgres_enabled", lambda: True)
    store = ChangeRequestStore()
    store._schema_ready = True
    monkeypatch.setattr(store, "_connect", fake_connect)

    with pytest.raises(store_module.ChangeRequestStoreUnavailableError):
        store.submit(_submission())

    assert events == [
        "disable_replay",
        "lock",
        "select_submission",
        "count",
        "insert",
    ]


def test_poll_many_preserves_order_and_uses_one_connection(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    store = ChangeRequestStore(sqlite_path=tmp_path / "change-requests.sqlite3")
    first = store.submit(_submission())
    second = store.submit(_submission())
    original_connect = store._connect
    connection_count = 0

    @contextmanager
    def counted_connect():
        nonlocal connection_count
        connection_count += 1
        with original_connect() as connection:
            yield connection

    monkeypatch.setattr(store, "_connect", counted_connect)

    results = store.poll_many(
        [
            (second.change_request_id, second.status_token),
            (first.change_request_id, "wrong-token"),
            (first.change_request_id, first.status_token),
            ("CR-999", "missing-token"),
        ]
    )

    assert results == [second, None, first, None]
    assert connection_count == 1


def test_mark_fixed_requires_exact_local_published_manifest(tmp_path: Path) -> None:
    store = ChangeRequestStore(sqlite_path=tmp_path / "change-requests.sqlite3")
    record = store.submit(_submission(plugin="vera"))
    manifest_path = _write_manifest(
        tmp_path / "versions.json",
        plugin="vera",
        version="1.1.0",
    )

    with pytest.raises(ChangeRequestManifestError, match="not the locally published"):
        store.mark_fixed(
            record.change_request_id,
            published_version="1.2.0",
            manifest_path=manifest_path,
        )

    fixed = store.mark_fixed(
        record.change_request_id,
        published_version="1.1.0",
        manifest_path=manifest_path,
    )
    retried = store.mark_fixed(
        record.change_request_id,
        published_version="1.1.0",
        manifest_path=manifest_path,
    )

    assert fixed.status == "fixed"
    assert fixed.fixed is True
    assert fixed.fixed_version == "1.1.0"
    assert fixed.install_url == "https://chatgpt.com/plugins/vera"
    assert retried == fixed
    assert store.list_open() == []


def test_existing_sqlite_store_adds_interview_columns(tmp_path: Path) -> None:
    database_path = tmp_path / "old.sqlite3"
    with sqlite3.connect(database_path) as connection:
        connection.execute("""
            CREATE TABLE mparanza_change_requests (
                request_no INTEGER PRIMARY KEY AUTOINCREMENT,
                submission_id TEXT NOT NULL UNIQUE,
                plugin TEXT NOT NULL,
                plugin_version TEXT NOT NULL,
                kind TEXT NOT NULL,
                request_json TEXT NOT NULL,
                request_sha256 TEXT NOT NULL,
                status_token TEXT NOT NULL UNIQUE,
                status TEXT NOT NULL,
                fixed_version TEXT,
                install_url TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                fixed_at TEXT
            )
            """)
    store = ChangeRequestStore(sqlite_path=database_path)

    record = store.submit(_submission(kind="capability"))

    assert record.interview_url is None
    assert record.interview_json is None
    with sqlite3.connect(database_path) as connection:
        columns = {
            str(row[1])
            for row in connection.execute(
                "PRAGMA table_info(mparanza_change_requests)"
            ).fetchall()
        }
    assert {"interview_url", "interview_json"}.issubset(columns)
