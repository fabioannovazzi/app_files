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
