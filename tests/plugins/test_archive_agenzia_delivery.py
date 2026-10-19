"""Agenzia's actual MCP status projection records against its client Archive run."""

from __future__ import annotations

import json
import os
import sqlite3
import subprocess
import sys
from pathlib import Path

from tests.plugins.test_archive_automatic_reporting import (
    archive_core,
    archive_script_imports,
    client_case,
    finish,
    reporting_runtime,
)

COMPONENT = Path(__file__).resolve().parents[2] / "plugins/browser-automation"


def test_agenzia_mcp_status_records_counts_without_app_only_clients(
    archive_core, client_case, monkeypatch, tmp_path
):
    from archive_report_store import digest

    monkeypatch.syspath_prepend(str(COMPONENT / "scripts"))
    from ade_acquisition import archive_runs, contracts

    monkeypatch.setattr(archive_runs, "_archive", lambda: archive_core)
    state_directory = archive_core._state_dir
    monkeypatch.setattr(
        archive_core,
        "_state_dir",
        lambda value=None: state_directory(value or client_case.state_dir),
    )
    plan = contracts.Plan.parse(
        {
            "schema_version": "vera-agenzia-plan/v1",
            "clients": [
                {
                    "name": "PRIVATE_CLIENT_NAME",
                    "tax_code": "01234567890",
                    "vat_number": "01234567890",
                    "archive_client_id": client_case.client_id,
                    "archive_engagement_id": client_case.engagement_id,
                }
            ],
            "date_from": "2026-01-01",
            "date_to": "2026-01-31",
            "operations": ["ricevute"],
        }
    )
    source = tmp_path / "plan.json"
    source.write_text(json.dumps(plan.payload()))
    output = tmp_path / "acquisition"
    worker = output / "runs" / ("a" * 32)
    worker.mkdir(parents=True)
    (worker / "plan.json").write_text(source.read_text())
    (worker / "status.json").write_text(
        json.dumps({"state": "awaiting_review", "scopes": [{"client": "01234567890"}]})
    )
    archive_runs.prepare_runs(worker, plan)
    binding = json.loads((worker / "archive-runs.json").read_text())["01234567890"]
    script = tmp_path / "status.cjs"
    script.write_text(
        f"const server=require({json.dumps(str(COMPONENT / 'mcp/server.cjs'))});"
        f"const opened=server.callTool('agenzia_workspace_open',{{plan_path:{json.dumps(str(source))},output_directory:{json.dumps(str(output))}}});"
        f"const result=server.callTool('agenzia_workspace_status',{{workspace_ref:opened.structuredContent.workspace_ref,run_id:{json.dumps(worker.name)}}});"
        "process.stdout.write(JSON.stringify(result));"
    )

    completed = subprocess.run(
        ["node", str(script)],
        capture_output=True,
        text=True,
        timeout=30,
        env={**os.environ, "PYTHON": sys.executable},
    )

    assert completed.returncode == 0, completed.stderr
    response = json.loads(completed.stdout)
    assert response["_meta"]["agenzia"]["scopes"][0]["client"] == "01234567890"
    model = {key: value for key, value in response.items() if key != "_meta"}
    loaded = archive_core.ledger.load_run(
        client_case.client_root, client_case.engagement_id, binding["run_id"]
    )
    with sqlite3.connect(
        Path(loaded["run_root"]) / "reporting/events.sqlite3"
    ) as connection:
        sends = [
            json.loads(row[0])
            for row in connection.execute("SELECT payload FROM events")
        ]
    sends = [
        event for event in sends if event.get("channel") == "mcp:agenzia-acquisition"
    ]
    assert sends[-1]["response_sha256"] == digest(model)
    assert "PRIVATE_CLIENT_NAME" not in json.dumps(sends)
    assert "01234567890" not in json.dumps(sends)
    final = finish(archive_core, client_case, loaded)
    assert final["collection_status"] == "complete", final["errors"]
    assert final["sources"][0]["not_sent_quantity"] == 1
