from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from uuid import uuid4

import pytest

from modules.change_requests.store import (
    ChangeRequestConflictError,
    ChangeRequestManifestError,
    ChangeRequestStore,
)


def _submission(
    *,
    submission_id: str | None = None,
    plugin: str = "clara",
    kind: str = "problem",
) -> dict[str, object]:
    return {
        "schema_version": 1,
        "submission_id": submission_id or str(uuid4()),
        "kind": kind,
        "plugin": plugin,
        "plugin_version": "1.0.0",
        "request": {
            "observed": "The synthetic input was rejected.",
            "expected": "The synthetic input should be accepted.",
        },
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
    record = store.submit(_submission(kind="capability"))

    linked = store.set_interview_url_if_absent(
        record.change_request_id,
        "https://mparanza.com/case-notes/interview/first",
    )
    retried_link = store.set_interview_url_if_absent(
        record.change_request_id,
        "https://mparanza.com/case-notes/interview/retry",
    )
    completion = {"summary": "Add a compact comparison table."}
    completed = store.attach_interview_completion(record.change_request_id, completion)
    retried_completion = store.attach_interview_completion(
        record.change_request_id, completion
    )

    assert linked.interview_url.endswith("/first")
    assert retried_link.interview_url == linked.interview_url
    assert json.loads(completed.interview_json or "{}") == completion
    assert retried_completion.interview_json == completed.interview_json
    with pytest.raises(ChangeRequestConflictError, match="different interview"):
        store.attach_interview_completion(
            record.change_request_id,
            {"summary": "A conflicting completion."},
        )


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
