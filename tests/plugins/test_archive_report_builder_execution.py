"""Execute both Report Builder pipeline identities through the public CLI."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

from tests.plugins.test_archive_automatic_reporting import (
    archive_core,
    archive_script_imports,
    client_case,
    reporting_runtime,
    start,
)

SCRIPTS = Path(__file__).resolve().parents[2] / "plugins/report-builder/scripts"


@pytest.mark.parametrize(
    "workflow,report_type",
    [
        ("report-builder", "management_report"),
        ("report-enti-locali", "local_government_review"),
    ],
)
def test_report_builder_cli_retains_its_professional_seal_after_archive_completion(
    archive_core, client_case, tmp_path, workflow, report_type
):
    source = tmp_path / "statement.csv"
    source.write_text("line,amount\nRevenue,1234.50\nCost,-234.50\n", encoding="utf-8")
    client_case.imported = archive_core.import_studio_client_document(
        client_case.client_id,
        source,
        "journal",
        engagement_id=client_case.engagement_id,
        state_dir=client_case.state_dir,
    )
    loaded = start(archive_core, client_case, workflow)
    output = Path(loaded["output_dir"])
    context = Path(loaded["run_root"]) / "context.json"
    initial_report = json.loads(
        (output / "model_data_report.json").read_text(encoding="utf-8")
    )
    assert initial_report["outcome"] == "running"

    built = subprocess.run(
        [
            sys.executable,
            "-I",
            "-B",
            str(SCRIPTS / "build_report.py"),
            loaded["context"]["input_bindings"][0]["path"],
            "--output-dir",
            str(output),
            "--client-engagement",
            str(context),
            "--report-type",
            report_type,
        ],
        capture_output=True,
        text=True,
        check=False,
        timeout=45,
    )

    assert built.returncode == 0, built.stderr
    review = json.loads((output / "review_payload.json").read_text(encoding="utf-8"))
    item = next(item for item in review["items"] if "accept" in item["allowed_actions"])
    request = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "tools/call",
        "params": {
            "name": "save_report_builder_decisions",
            "arguments": {
                "client_engagement": str(context),
                "review_payload": review,
                "run_intake": json.loads(
                    (output / "run_intake.json").read_text(encoding="utf-8")
                ),
                "decisions": [{"item_id": item["id"], "action": "accept"}],
            },
        },
    }
    saved = subprocess.run(
        ["node", str(SCRIPTS.parent / "mcp/server.cjs")],
        input=json.dumps(request) + "\n",
        capture_output=True,
        text=True,
        check=False,
        timeout=45,
    )
    assert saved.returncode == 0, saved.stderr
    response = json.loads(saved.stdout)["result"]
    assert response["structuredContent"]["ok"] is True, response
    integrity_before = (output / "review_integrity.json").read_bytes()
    declarations = [
        {
            "artifact_id": f"output-{index}",
            "path": path.relative_to(output).as_posix(),
            "purpose": "Synthetic report execution",
            "audience": "review",
            "media_type": "application/octet-stream",
        }
        for index, path in enumerate(sorted(output.rglob("*")))
        if path.is_file()
    ]
    archive_core.ledger.finalize_run(
        client_case.client_root,
        client_case.engagement_id,
        loaded["run"]["run_id"],
        declarations,
    )
    archive_core.ledger.complete_run(
        client_case.client_root, client_case.engagement_id, loaded["run"]["run_id"]
    )
    report = json.loads((output / "model_data_report.json").read_text(encoding="utf-8"))
    assert report["workflow_id"] == workflow
    assert report["outcome"] == "completed"
    assert report["collection_status"] == "incomplete"
    assert (output / "review_integrity.json").read_bytes() == integrity_before
    replayed = subprocess.run(
        [
            sys.executable,
            "-I",
            "-B",
            str(SCRIPTS / "validate_review_integrity.py"),
            "--output-dir",
            str(output),
        ],
        input="{}",
        capture_output=True,
        text=True,
        check=False,
        timeout=45,
    )
    assert replayed.returncode == 0, replayed.stderr
    assert json.loads(replayed.stdout)["ok"] is True
