from __future__ import annotations

import importlib.util
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path
from types import ModuleType

import pytest

ROOT = Path(__file__).resolve().parents[2]
PLUGIN_ROOT = ROOT / "plugins" / "archive-organization"


def _load_module(name: str, path: Path) -> ModuleType:
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


scenario = _load_module(
    "archive_organization_plugin_scenario",
    PLUGIN_ROOT / "tests" / "test_archive_organization.py",
)
core = scenario.organizer
contract = _load_module(
    "archive_organization_plugin_contract",
    ROOT / "scripts" / "validate_plugin_review_contract.py",
)


def _node_executable() -> str:
    system_node = shutil.which("node")
    if system_node:
        return system_node
    bundled = (
        Path.home()
        / ".cache/codex-runtimes/codex-primary-runtime/dependencies/node/bin/node"
    )
    if bundled.is_file():
        return str(bundled)
    pytest.skip("Node.js is required for the Archive Organization MCP test")


def _rpc_call(
    process: subprocess.Popen[str],
    request_id: int,
    name: str,
    arguments: dict[str, object],
) -> dict[str, object]:
    assert process.stdin is not None and process.stdout is not None
    process.stdin.write(
        json.dumps(
            {
                "jsonrpc": "2.0",
                "id": request_id,
                "method": "tools/call",
                "params": {"name": name, "arguments": arguments},
            }
        )
        + "\n"
    )
    process.stdin.flush()
    return json.loads(process.stdout.readline())["result"]


def test_generated_archive_organization_review_contract(tmp_path: Path) -> None:
    context_path, snapshot, _ = scenario._prepared_run(tmp_path)

    result = core.build_review_package(
        context_path,
        scenario._proposals(tmp_path, snapshot),
    )

    output_dir = Path(result["output_dir"])
    for artifact_name in (
        "run_intake.json",
        "review_payload.json",
        "ui_decisions.json",
        "final_artifacts.json",
    ):
        assert (output_dir / artifact_name).is_file()
    report = contract.validate_contract(output_dir)
    assert report.ok, report.errors


def test_mcp_uses_hash_bound_review_reference_after_single_payload_exposure(
    tmp_path: Path,
) -> None:
    context_path, snapshot, _ = scenario._prepared_run(tmp_path)
    prepared = core.build_review_package(
        context_path,
        scenario._proposals(tmp_path, snapshot),
    )
    review_payload = json.loads(Path(prepared["review_payload_path"]).read_text())
    process = subprocess.Popen(
        [_node_executable(), str(PLUGIN_ROOT / "mcp" / "server.cjs")],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        env={
            **os.environ,
            "VIRTUAL_ENV": str(Path(sys.executable).parent.parent),
        },
    )
    try:
        validated = _rpc_call(
            process,
            1,
            "validate_archive_organization_review",
            {
                "client_engagement": str(context_path),
                "review_payload": review_payload,
            },
        )
        reference = validated["structuredContent"]["review_reference"]["reference"]
        rendered = _rpc_call(
            process,
            2,
            "render_archive_organization_review",
            {"review_reference": reference},
        )
        decisions = [
            {"item_id": item["id"], "action": "accept"}
            for item in review_payload["items"]
        ]
        saved = _rpc_call(
            process,
            3,
            "save_archive_organization_decisions",
            {
                "review_reference": reference,
                "decisions": decisions,
                "reviewer": "pytest-reviewer",
            },
        )
        approved = _rpc_call(
            process,
            4,
            "apply_archive_organization_decisions",
            {
                "review_reference": reference,
                "decisions": decisions,
                "reviewer": "pytest-reviewer",
            },
        )
    finally:
        process.terminate()
        process.wait(timeout=10)

    assert validated["structuredContent"]["ok"] is True
    assert (
        validated["structuredContent"]["review_reference"]["expires_in_seconds"]
        == 14_400
    )
    assert rendered["structuredContent"]["review_payload"] == review_payload
    assert rendered["structuredContent"]["review_reference"] == reference
    assert saved["structuredContent"]["status"] == "reviewed"
    assert approved["structuredContent"]["status"] == "ready_to_apply"
    assert (
        approved["structuredContent"]["execution_requires_separate_explicit_approval"]
        is True
    )
    repeated_results = json.dumps(
        {
            "validated": validated["content"],
            "saved": saved["structuredContent"],
            "approved": approved["structuredContent"],
        }
    )
    assert "review_payload" not in repeated_results
    assert str(context_path) not in repeated_results
    assert prepared["output_dir"] not in repeated_results


def test_mcp_unbound_supplied_plan_reference_remains_review_only(
    tmp_path: Path,
) -> None:
    context_path, snapshot, _ = scenario._prepared_run(tmp_path)
    prepared = core.build_review_package(
        context_path,
        scenario._proposals(tmp_path, snapshot),
    )
    review_payload = json.loads(Path(prepared["review_payload_path"]).read_text())
    process = subprocess.Popen(
        [_node_executable(), str(PLUGIN_ROOT / "mcp" / "server.cjs")],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    try:
        validated = _rpc_call(
            process,
            1,
            "validate_archive_organization_review",
            {"review_payload": review_payload},
        )
        reference = validated["structuredContent"]["review_reference"]["reference"]
        rendered = _rpc_call(
            process,
            2,
            "render_archive_organization_review",
            {"review_reference": reference},
        )
    finally:
        process.terminate()
        process.wait(timeout=10)

    assert (
        validated["structuredContent"]["review_reference"]["persistence_enabled"]
        is False
    )
    assert rendered["structuredContent"]["review_payload"] == review_payload
    assert rendered["structuredContent"]["persistence_enabled"] is False
