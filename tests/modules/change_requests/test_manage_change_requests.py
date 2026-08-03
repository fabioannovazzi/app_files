from __future__ import annotations

import json
from pathlib import Path
from uuid import uuid4

from modules.change_requests.store import ChangeRequestStore
from scripts import manage_change_requests


def _submission() -> dict[str, object]:
    return {
        "schema_version": 1,
        "submission_id": str(uuid4()),
        "kind": "problem",
        "plugin": "clara",
        "plugin_version": "1.0.0",
        "request": {"observed": "Synthetic failure", "expected": "Success"},
    }


def test_cli_lists_shows_and_marks_a_published_fix(
    tmp_path: Path, capsys, monkeypatch
) -> None:
    monkeypatch.setattr(
        manage_change_requests, "load_env_from_secrets_file", lambda: {}
    )
    database_path = tmp_path / "change-requests.sqlite3"
    record = ChangeRequestStore(sqlite_path=database_path).submit(_submission())
    manifest_path = tmp_path / "versions.json"
    manifest_path.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "plugins": {
                    "clara": {
                        "published_version": "1.1.0",
                        "install_url": "https://chatgpt.com/plugins/clara",
                    }
                },
            }
        ),
        encoding="utf-8",
    )

    listed_exit = manage_change_requests.main(
        ["--sqlite-path", str(database_path), "list"]
    )
    listed = json.loads(capsys.readouterr().out)
    shown_exit = manage_change_requests.main(
        ["--sqlite-path", str(database_path), "show", record.change_request_id]
    )
    shown = json.loads(capsys.readouterr().out)
    fixed_exit = manage_change_requests.main(
        [
            "--sqlite-path",
            str(database_path),
            "fixed",
            record.change_request_id,
            "--published-version",
            "1.1.0",
            "--manifest",
            str(manifest_path),
        ]
    )
    fixed = json.loads(capsys.readouterr().out)

    assert listed_exit == shown_exit == fixed_exit == 0
    assert listed[0]["change_request_id"] == record.change_request_id
    assert "status_token" not in listed[0]
    assert shown["request"]["request"]["observed"] == "Synthetic failure"
    assert fixed["status"] == "fixed"
    assert fixed["fixed_version"] == "1.1.0"


def test_cli_consider_sets_request_aside(tmp_path: Path, capsys, monkeypatch) -> None:
    monkeypatch.setattr(
        manage_change_requests, "load_env_from_secrets_file", lambda: {}
    )
    database_path = tmp_path / "change-requests.sqlite3"
    store = ChangeRequestStore(sqlite_path=database_path)
    record = store.submit(_submission())

    exit_code = manage_change_requests.main(
        ["--sqlite-path", str(database_path), "consider", record.change_request_id]
    )
    payload = json.loads(capsys.readouterr().out)

    assert exit_code == 0
    assert payload["status"] == "open"
    assert payload["triage_state"] == "considering"
    assert store.list_open() == []


def test_cli_lists_considering_requests(tmp_path: Path, capsys, monkeypatch) -> None:
    monkeypatch.setattr(
        manage_change_requests, "load_env_from_secrets_file", lambda: {}
    )
    database_path = tmp_path / "change-requests.sqlite3"
    store = ChangeRequestStore(sqlite_path=database_path)
    record = store.submit(_submission())
    store.set_triage_state(record.change_request_id, "considering")

    exit_code = manage_change_requests.main(
        [
            "--sqlite-path",
            str(database_path),
            "list",
            "--triage-state",
            "considering",
        ]
    )
    payload = json.loads(capsys.readouterr().out)

    assert exit_code == 0
    assert [item["change_request_id"] for item in payload] == [record.change_request_id]
    assert payload[0]["triage_state"] == "considering"


def test_cli_activate_returns_request_to_active_queue(
    tmp_path: Path, capsys, monkeypatch
) -> None:
    monkeypatch.setattr(
        manage_change_requests, "load_env_from_secrets_file", lambda: {}
    )
    database_path = tmp_path / "change-requests.sqlite3"
    store = ChangeRequestStore(sqlite_path=database_path)
    record = store.submit(_submission())
    store.set_triage_state(record.change_request_id, "considering")

    exit_code = manage_change_requests.main(
        ["--sqlite-path", str(database_path), "activate", record.change_request_id]
    )
    payload = json.loads(capsys.readouterr().out)

    assert exit_code == 0
    assert payload["status"] == "open"
    assert payload["triage_state"] == "active"
    assert store.list_open() == [store.get(record.change_request_id)]


def test_cli_needs_info_records_public_question(
    tmp_path: Path, capsys, monkeypatch
) -> None:
    monkeypatch.setattr(
        manage_change_requests, "load_env_from_secrets_file", lambda: {}
    )
    database_path = tmp_path / "change-requests.sqlite3"
    store = ChangeRequestStore(sqlite_path=database_path)
    record = store.submit(_submission())

    exit_code = manage_change_requests.main(
        [
            "--sqlite-path",
            str(database_path),
            "needs-info",
            record.change_request_id,
            "--question",
            "Provide the exact sanitized response.",
        ]
    )
    payload = json.loads(capsys.readouterr().out)

    assert exit_code == 0
    assert payload["disposition"] == "needs_info"
    assert payload["needs_info_question"] == "Provide the exact sanitized response."


def test_cli_close_records_non_fix_disposition(
    tmp_path: Path, capsys, monkeypatch
) -> None:
    monkeypatch.setattr(
        manage_change_requests, "load_env_from_secrets_file", lambda: {}
    )
    database_path = tmp_path / "change-requests.sqlite3"
    record = ChangeRequestStore(sqlite_path=database_path).submit(_submission())

    exit_code = manage_change_requests.main(
        [
            "--sqlite-path",
            str(database_path),
            "close",
            record.change_request_id,
            "--disposition",
            "external",
            "--note",
            "Reproduced and routed to the external runtime owner.",
        ]
    )
    payload = json.loads(capsys.readouterr().out)

    assert exit_code == 0
    assert payload["status"] == "open"
    assert payload["disposition"] == "external"
    assert payload["fixed_version"] is None


def test_cli_reopen_restores_active_investigation(
    tmp_path: Path, capsys, monkeypatch
) -> None:
    monkeypatch.setattr(
        manage_change_requests, "load_env_from_secrets_file", lambda: {}
    )
    database_path = tmp_path / "change-requests.sqlite3"
    store = ChangeRequestStore(sqlite_path=database_path)
    record = store.submit(_submission())
    store.close_without_fix(
        record.change_request_id,
        disposition="non_actionable",
        note="Initial classification was unsupported.",
    )

    exit_code = manage_change_requests.main(
        ["--sqlite-path", str(database_path), "reopen", record.change_request_id]
    )
    payload = json.loads(capsys.readouterr().out)

    assert exit_code == 0
    assert payload["disposition"] == "unresolved"
    assert payload["triage_state"] == "active"
    assert store.list_open() == [store.get(record.change_request_id)]
