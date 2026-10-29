"""Product packages preserve MCP capabilities and direct-script workflows."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path
from zipfile import ZipFile

import pytest

from tests.plugins.test_codex_plugin_packages import load_builder
from tests.plugins.test_reconciliation_operation import request_for
from tests.plugins.test_vera_customer_folder_ledger import (
    archive_core,
    archive_script_imports,
    client_case,
)

__all__: list[str] = []
ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture(autouse=True)
def packaged_archive_session(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """Share an explicit synthetic session between fixtures and CLI subprocesses."""
    monkeypatch.setenv("VERA_STUDIO_ARCHIVE_SESSION_ID", str(tmp_path))


@pytest.mark.parametrize("product", ["vera", "clara", "lucia"])
@pytest.mark.parametrize("surface", ["download", "upload"])
def test_package_preserves_source_mcp_capabilities(product, surface):
    """Prevent shipping fewer MCP tools than the source plugin exposes."""
    builder = load_builder()
    target = next(
        target
        for target in [*builder.load_bundles(), *builder.load_packages()]
        if target.target_name == product
    )
    prefix = f"{target.package_root}/plugins/{product}/"
    source = {
        name.removeprefix(prefix): content
        for name, content in builder.source_zip_entries(target).items()
        if name.startswith(prefix)
    }
    if surface == "download":
        entries = {
            name.removeprefix(prefix): content
            for name, content in builder.expected_zip_entries(target).items()
            if name.startswith(prefix)
        }
    else:
        entries = builder.chatgpt_upload_entries(target)

    mcp_files = {
        name: content
        for name, content in source.items()
        if (name.endswith((".mcp.json", ".app.json")) or "mcp" in name.split("/"))
        and not (surface == "upload" and name == ".app.json")
    }
    assert mcp_files
    assert {name: entries[name] for name in mcp_files} == mcp_files
    servers = json.loads(entries[".mcp.json"])["mcpServers"]
    assert any(server.get("command") == "node" for server in servers.values())
    assert f"{product}Incidents" not in servers
    assert all(
        "url" not in server and "serverUrl" not in server for server in servers.values()
    )
    source_declarations = {
        name: {
            key: value
            for key, value in json.loads(content).items()
            if key
            in ({"mcpServers"} if surface == "upload" else {"mcpServers", "apps"})
        }
        for name, content in source.items()
        if name.endswith(".codex-plugin/plugin.json")
    }
    assert {
        name: {
            key: value
            for key, value in json.loads(entries[name]).items()
            if key in {"mcpServers", "apps"}
        }
        for name in source_declarations
    } == source_declarations
    assert not any(name.endswith("scripts/review_mcp_server.cjs") for name in entries)


def _run(
    command: list[str], evidence: Path, env: dict[str, str], *, isolated: bool = True
) -> dict:
    completed = subprocess.run(
        [sys.executable, *(["-I"] if isolated else []), "-B", *command],
        env=env,
        capture_output=True,
        text=True,
        timeout=120,
    )
    evidence.with_suffix(".stdout").write_text(completed.stdout)
    evidence.with_suffix(".stderr").write_text(completed.stderr)
    assert completed.returncode == 0, completed.stderr
    return json.loads(completed.stdout)


@pytest.mark.parametrize(
    ("product", "pipeline", "event_product"),
    [
        ("vera", "open-item-reconciliation", None),
        ("clara", "business-planning", "clara"),
        ("lucia", "revisione-contratti", "lucia"),
    ],
)
def test_packaged_reporting_cli_retains_task_without_native_mcp(
    product, pipeline, event_product, tmp_path
):
    with ZipFile(ROOT / f"plugin_packages/{product}/{product}-plugin.zip") as archive:
        archive.extractall(tmp_path / "installed")
    plugin = tmp_path / f"installed/{product}-codex-plugin/plugins/{product}"
    helper = str(plugin / "scripts/workflow_usage.py")
    run_id = "5b6d7d35-0fe2-4ac4-84e4-c5a2da3eb6a0"
    env = {
        **os.environ,
        "MPARANZA_INCIDENT_STATE_DIR": str(tmp_path / "incident-state"),
        "MPARANZA_INCIDENT_DELIVERY": "local-only",
        "MPARANZA_INCIDENT_HOST": "codex",
    }
    begin = [
        helper,
        "start",
        "--run-id",
        run_id,
        "--pipeline",
        pipeline,
        "--host",
        "codex",
        "--sample-kind",
        "agent_test",
    ]

    # The documented reporting CLI uses ordinary Python script imports. -I
    # removes its own scripts directory and is not part of that launch contract.
    started = _run(begin, tmp_path / "start", env, isolated=False)
    reopened = _run(begin, tmp_path / "reopened", env, isolated=False)
    _run(
        [helper, "record", "--run-id", run_id, "--kind", "completed"],
        tmp_path / "completion",
        env,
        isolated=False,
    )
    retained = _run(
        [helper, "status", "--run-id", run_id], tmp_path / "status", env, isolated=False
    )

    assert started["run_id"] == reopened["run_id"] == retained["run_id"] == run_id
    assert [item["event"]["kind"] for item in retained["local_events"]] == [
        "started",
        "completed",
    ]
    assert retained["local_events"][0]["event"]["sample_kind"] == "agent_test"
    assert retained["local_events"][0]["event"]["pipeline"] == pipeline
    assert retained["local_events"][0]["event"].get("product") == event_product
    assert retained["queued"] == 2
    assert retained["remote"] is None
    assert (tmp_path / "incident-state/workflow-usage.sqlite3").is_file()


def test_packaged_script_review_preserves_unpaid_balance_and_real_completion_gate(
    client_case, tmp_path
):
    with ZipFile(ROOT / "plugin_packages/vera/vera-plugin.zip") as package:
        package.extractall(tmp_path / "installed")
    installed = tmp_path / "installed/vera-codex-plugin/plugins/vera"
    operation = installed / "modules/studio-archive/scripts/reconcile_open_items.py"
    scripts = installed / "modules/open-item-reconciliation/scripts"
    request = request_for(client_case, tmp_path)
    request["sources"] = request["sources"][:1]
    request_path = tmp_path / "request.json"
    request_path.write_text(json.dumps(request))
    original = Path(request["sources"][0]["path"]).read_bytes()
    env = {
        **os.environ,
        "MPARANZA_RUNTIME_ROOT": str(tmp_path / "runtime"),
        "MPARANZA_INCIDENT_STATE_DIR": str(tmp_path / "incident-state"),
        "MPARANZA_INCIDENT_DELIVERY": "local-only",
        "VERA_REPORTING_STATE_DIR": str(tmp_path / "reporting-state"),
    }
    command = [
        str(operation),
        "--request",
        str(request_path),
        "--state-dir",
        str(client_case.state_dir),
    ]

    draft = _run(command, tmp_path / "draft", env)

    assert draft["status"] == "review_required"
    assert draft["report_ready"] is False
    output = Path(draft["output_dir"])
    checkpoint = json.loads(
        (output.parent / "reconciliation-review-checkpoint.json").read_text()
    )["content_sha256"]
    review = json.loads((output / "review_payload.json").read_text())
    decision_path = tmp_path / "decisions.json"
    decision_path.write_text(
        json.dumps(
            {
                "reviewer": "agent.codex.synthetic",
                "decision_source": "codex_agent",
                "expected_predecessor_checkpoint": checkpoint,
                "decisions": [
                    {
                        "item_id": item["id"],
                        "action": "accept",
                        "note": "Technical agent review: no payment evidence; preserve unpaid balance. No human approval.",
                    }
                    for item in review["items"]
                ],
            }
        )
    )
    applied = _run(
        [
            "-c",
            "import sys,json;from pathlib import Path;sys.path.insert(0,sys.argv[1]);import review_server;print(json.dumps(review_server.apply_decisions(Path(sys.argv[2]),json.loads(Path(sys.argv[3]).read_text()))))",
            str(scripts),
            str(output),
            str(decision_path),
        ],
        tmp_path / "applied",
        env,
    )
    assert applied["application_status"] == "awaiting_regeneration"
    assert (
        json.loads((output / "final_artifacts.json").read_text())["assurance"][
            "report_ready"
        ]
        is False
    )
    context = output.parent.parent / "context.json"
    regenerated = _run(
        [
            str(scripts / "raw_input_runner.py"),
            "--client-engagement",
            str(context),
            "--output-subdirectory",
            "reconciliation",
            "--expected-predecessor-checkpoint",
            checkpoint,
        ],
        tmp_path / "regenerated",
        env,
    )
    assert regenerated["regenerated"] is True
    finished = _run(
        command + ["--finish-run", draft["run_id"]], tmp_path / "finished", env
    )
    assert finished["status"] == "completed"
    assert finished["report_ready"] is True
    canonical = json.loads(
        (output / "assurance_final_outputs/reconciliation_results.json").read_text()
    )
    assert canonical["reconciliation_rows"][0]["reconciliation_status"] == "unresolved"
    assert canonical["reconciliation_rows"][0]["amount"] == "1220"
    assert canonical["review_rows"][0]["review_status"] == "PASS"
    assert "agent.codex.synthetic" in json.dumps(canonical["review_rows"])
    assert Path(request["sources"][0]["path"]).read_bytes() == original
    assert finished["artifacts"] and all(
        Path(path).is_file() for path in finished["artifacts"]
    )
    assert (output / "assurance_transition_history" / checkpoint).is_dir()
