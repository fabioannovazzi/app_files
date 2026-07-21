from __future__ import annotations

import importlib.util
import json
import shutil
import stat
import subprocess
import sys
from pathlib import Path
from typing import Any
from zipfile import ZipFile

import pytest

from scripts.validate_plugin_review_contract import (
    validate_contract as validate_shared_contract,
)

ROOT = Path(__file__).resolve().parents[2]
PLUGIN_ROOT = ROOT / "plugins" / "new-client"
VERA_ROOT = ROOT / "plugins" / "vera"
BUILD_SCRIPT = ROOT / "scripts" / "build_codex_plugin_zip.py"


def _load_module(name: str, path: Path) -> Any:
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def _load_core() -> Any:
    return _load_module(
        "new_client_core_contract_test",
        PLUGIN_ROOT / "scripts" / "new_client_core.py",
    )


def _node_binary() -> str:
    node = shutil.which("node")
    if node is None:
        pytest.skip("Node.js is required for the new-client MCP tests.")
    return node


def _call_mcp(messages: list[dict[str, Any]]) -> dict[int, dict[str, Any]]:
    completed = subprocess.run(
        [_node_binary(), str(PLUGIN_ROOT / "mcp" / "server.cjs"), "--stdio"],
        cwd=PLUGIN_ROOT,
        input="\n".join(json.dumps(message) for message in messages) + "\n",
        capture_output=True,
        check=True,
        text=True,
        timeout=20,
    )
    responses = [
        json.loads(line) for line in completed.stdout.splitlines() if line.strip()
    ]
    return {response["id"]: response for response in responses}


def _start_mcp_session() -> subprocess.Popen[str]:
    return subprocess.Popen(
        [_node_binary(), str(PLUGIN_ROOT / "mcp" / "server.cjs"), "--stdio"],
        cwd=PLUGIN_ROOT,
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )


def _exchange_mcp(
    process: subprocess.Popen[str],
    message: dict[str, Any],
) -> dict[str, Any]:
    assert process.stdin is not None
    assert process.stdout is not None
    process.stdin.write(json.dumps(message) + "\n")
    process.stdin.flush()
    response = process.stdout.readline()
    assert response, "MCP server closed before returning a response"
    return json.loads(response)


def _stop_mcp_session(process: subprocess.Popen[str]) -> None:
    assert process.stdin is not None
    process.stdin.close()
    try:
        process.wait(timeout=5)
    except subprocess.TimeoutExpired:
        process.terminate()
        process.wait(timeout=5)


def _generate_package(tmp_path: Path) -> Path:
    output_dir = tmp_path / "private-new-client"
    initialized = subprocess.run(
        [
            sys.executable,
            str(PLUGIN_ROOT / "scripts" / "initialize_case.py"),
            "--case-dir",
            str(output_dir),
            "--client-reference",
            "CLIENT-OPAQUE-001",
            "--assessment-date",
            "2026-07-20",
        ],
        cwd=PLUGIN_ROOT,
        capture_output=True,
        check=True,
        text=True,
    )
    assert json.loads(initialized.stdout)["status"] == "new_client_input_initialized"
    packaged = subprocess.run(
        [
            sys.executable,
            str(PLUGIN_ROOT / "scripts" / "package_new_client.py"),
            "--input",
            str(output_dir / "new_client_input.json"),
            "--output-dir",
            str(output_dir),
        ],
        cwd=PLUGIN_ROOT,
        capture_output=True,
        check=True,
        text=True,
    )
    assert json.loads(packaged.stdout)["status"] == "blocked"
    return output_dir


def _tool_call(
    request_id: int,
    name: str,
    arguments: dict[str, Any],
) -> dict[str, Any]:
    return {
        "jsonrpc": "2.0",
        "id": request_id,
        "method": "tools/call",
        "params": {"name": name, "arguments": arguments},
    }


def _strict_review_payload() -> dict[str, Any]:
    digest = "a" * 64
    source_paths = {
        "facts": "case_facts_validated.json",
        "sources": "source_registry.json",
        "applicability": "applicability_plan_validated.json",
        "aml": "aml_calculation_audit.json",
        "documents": "document_plan.json",
        "monitoring": "monitoring_plan.json",
    }
    return {
        "schema_version": "1.1",
        "contract_version": "1.1",
        "plugin": "new-client",
        "workflow": "new-client",
        "run_id": "ready-export-run",
        "review_revision": 1,
        "review_type": "professional_new_client",
        "status": "pending_review",
        "item_count": 1,
        "items": [
            {
                "id": "party-fact-01",
                "item_type": "party_fact",
                "title": "Party fact",
                "status": "needs_review",
                "allowed_actions": [
                    "accept",
                    "reject",
                    "edit",
                    "mark_unclear",
                    "skip",
                ],
                "recommended_action": "accept",
                "data": {"confirmation_status": "verified"},
            }
        ],
        "source_artifacts": {
            key: {"path": file_name, "type": "local_artifact", "sha256": digest}
            for key, file_name in source_paths.items()
        },
        "basis_hashes": {
            "new_client_input": digest,
            "aml": digest,
            "documents": digest,
            "monitoring": digest,
            "sources": digest,
        },
        "privacy_notice": (
            "Pseudonymous professional review; direct identifiers stay local."
        ),
        "professional_review_required": True,
        "signature_performed": False,
        "client_communication_sent": False,
        "relationship_activation_performed": False,
    }


def _accepted_decisions(
    review_payload: dict[str, Any],
    *,
    rejected_item_id: str | None = None,
) -> list[dict[str, str]]:
    """Build one explicit professional decision for every review item."""

    return [
        {
            "item_id": item["id"],
            "action": "reject" if item["id"] == rejected_item_id else "accept",
        }
        for item in review_payload["items"]
    ]


def _mark_persistent_gate_ready(output_dir: Path) -> None:
    """Model a previously applied review without changing domain artifacts."""

    final_path = output_dir / "final_artifacts.json"
    final_artifacts = json.loads(final_path.read_text(encoding="utf-8"))
    gate = final_artifacts["export_gate"]
    gate["status"] = "ready_for_professional_export"
    gate["relationship_ready"] = True
    gate["domain_blockers"] = []
    gate["review_blockers"] = []
    gate["artifact_blockers"] = []
    final_artifacts["status"] = "ready_for_professional_export"
    final_artifacts["blockers"] = []
    final_path.write_text(
        json.dumps(final_artifacts, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    final_path.chmod(0o600)


def _validation_error(review_payload: dict[str, Any]) -> str:
    response = _call_mcp(
        [
            _tool_call(
                1,
                "validate_new_client_review",
                {"review_payload": review_payload},
            )
        ]
    )[1]["result"]
    assert response["isError"] is True
    return response["structuredContent"]["error"]


def test_vera_declares_new_client_component_skill_and_mcp_route() -> None:
    components = json.loads((VERA_ROOT / "components.json").read_text(encoding="utf-8"))
    mcp = json.loads((VERA_ROOT / ".mcp.json").read_text(encoding="utf-8"))
    routed_modules = {server["args"][-1] for server in mcp["mcpServers"].values()}

    assert "new-client" in components["plugins"]
    assert "client-file-preparation" in components["plugins"]
    assert {"new-client", "client-file-preparation"} <= routed_modules
    assert components["workflow_roles"]["new-client"]["internal_engines"] == [
        "client-file-preparation"
    ]
    assert components["workflow_roles"]["client-file-preparation"] == {
        "kind": "internal_engine",
        "parent_workflow": "new-client",
    }
    assert {
        "newClientFilePreparation",
        "newClientProfessionalSetup",
    } <= set(mcp["mcpServers"])
    wrapper = VERA_ROOT / "skills" / "new-client" / "SKILL.md"
    wrapper_text = wrapper.read_text(encoding="utf-8")
    assert "modules/new-client" in wrapper_text
    assert "modules/client-file-preparation" in wrapper_text
    assert "skills/new-client/SKILL.md" in wrapper_text
    assert "skills/client-file-preparation/SKILL.md" in wrapper_text
    assert "validate_client_file_preparation_review" in wrapper_text
    assert not (VERA_ROOT / "skills" / "client-file-preparation").exists()


def test_vera_delegates_new_client_dependency_check() -> None:
    result = subprocess.run(
        [
            sys.executable,
            str(VERA_ROOT / "scripts" / "check_dependencies.py"),
            "--module",
            "new-client",
        ],
        cwd=VERA_ROOT,
        capture_output=True,
        check=False,
        text=True,
    )

    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout)["status"] == "ready"


def test_vera_delegates_new_client_file_preparation_dependency_check() -> None:
    result = subprocess.run(
        [
            sys.executable,
            str(VERA_ROOT / "scripts" / "check_dependencies.py"),
            "--module",
            "client-file-preparation",
        ],
        cwd=VERA_ROOT,
        capture_output=True,
        check=False,
        text=True,
    )

    assert result.returncode == 0, result.stderr
    assert "Ambiente pronto." in result.stdout


def test_vera_zip_expected_entries_embed_new_client_component() -> None:
    builder = _load_module("build_vera_new_client", BUILD_SCRIPT)
    bundle = next(bundle for bundle in builder.load_bundles() if bundle.name == "vera")

    entries = builder.expected_zip_entries(bundle)

    prefix = "vera-codex-plugin/plugins/vera/modules/new-client/"
    for relative_path in (
        "skills/new-client/SKILL.md",
        "scripts/initialize_case.py",
        "scripts/package_new_client.py",
        "scripts/new_client_core.py",
        "schemas/new_client_input.schema.json",
        "references/source-registry.json",
        "mcp/server.cjs",
        "assets/new-client-review-widget.html",
    ):
        assert prefix + relative_path in entries

    engine_prefix = "vera-codex-plugin/plugins/vera/modules/client-file-preparation/"
    for relative_path in (
        "skills/client-file-preparation/SKILL.md",
        "scripts/build_file_preparation_outputs.py",
        "mcp/server.cjs",
        "assets/client-file-preparation-review-widget.html",
    ):
        assert engine_prefix + relative_path in entries


def test_packaged_vera_runs_new_client_through_dispatcher(
    tmp_path: Path,
) -> None:
    builder = _load_module("build_packaged_vera_new_client", BUILD_SCRIPT)
    bundle = next(bundle for bundle in builder.load_bundles() if bundle.name == "vera")
    extraction_root = tmp_path / "extracted-vera"
    with ZipFile(bundle.output_zip) as archive:
        archive.extractall(extraction_root)
    vera_root = extraction_root / bundle.package_root / "plugins" / "vera"

    dependencies = subprocess.run(
        [
            sys.executable,
            str(vera_root / "scripts" / "check_dependencies.py"),
            "--module",
            "new-client",
        ],
        cwd=vera_root,
        capture_output=True,
        check=True,
        text=True,
    )
    dependency_report = json.loads(dependencies.stdout)
    request = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "tools/list",
        "params": {},
    }
    mcp = subprocess.run(
        [
            _node_binary(),
            str(vera_root / "scripts" / "run_component_mcp.cjs"),
            "new-client",
        ],
        cwd=vera_root,
        input=json.dumps(request) + "\n",
        capture_output=True,
        check=True,
        text=True,
        timeout=20,
    )
    response = json.loads(mcp.stdout.strip())
    tool_names = {tool["name"] for tool in response["result"]["tools"]}

    assert dependency_report["status"] == "ready"
    assert {
        "validate_new_client_review",
        "render_new_client_review",
        "save_new_client_decisions",
        "apply_new_client_decisions",
    } <= tool_names


def test_packaged_vera_runs_new_client_file_preparation_phase(
    tmp_path: Path,
) -> None:
    builder = _load_module("build_packaged_vera_file_preparation", BUILD_SCRIPT)
    bundle = next(bundle for bundle in builder.load_bundles() if bundle.name == "vera")
    extraction_root = tmp_path / "extracted-vera"
    with ZipFile(bundle.output_zip) as archive:
        archive.extractall(extraction_root)
    vera_root = extraction_root / bundle.package_root / "plugins" / "vera"
    request = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "tools/list",
        "params": {},
    }
    mcp = subprocess.run(
        [
            _node_binary(),
            str(vera_root / "scripts" / "run_component_mcp.cjs"),
            "client-file-preparation",
        ],
        cwd=vera_root,
        input=json.dumps(request) + "\n",
        capture_output=True,
        check=True,
        text=True,
        timeout=20,
    )
    response = json.loads(mcp.stdout.strip())
    tool_names = {tool["name"] for tool in response["result"]["tools"]}

    assert {
        "validate_client_file_preparation_review",
        "render_client_file_preparation_review",
        "save_client_file_preparation_decisions",
        "apply_client_file_preparation_decisions",
    } <= tool_names


def test_new_client_generated_workflow_passes_both_contracts(
    tmp_path: Path,
) -> None:
    output_dir = _generate_package(tmp_path)
    core = _load_core()

    # Keep this explicit generation signal for the review-contract coverage audit.
    assert callable(core.build_monitoring_plan)
    run_intake = json.loads(
        (output_dir / "run_intake.json").read_text(encoding="utf-8")
    )
    review_payload = json.loads(
        (output_dir / "review_payload.json").read_text(encoding="utf-8")
    )
    ui_decisions = json.loads(
        (output_dir / "ui_decisions.json").read_text(encoding="utf-8")
    )
    final_artifacts = json.loads(
        (output_dir / "final_artifacts.json").read_text(encoding="utf-8")
    )

    assert core.validate_contract(output_dir)["artifact_count"] == 15
    shared = validate_shared_contract(
        output_dir,
        strict_data_posture=True,
        strict_execution_trace=True,
        strict_output_paths=True,
        strict_output_content=True,
    )
    assert shared.ok, shared.errors
    assert run_intake["plugin"] == "new-client"
    assert review_payload["item_count"] == len(review_payload["items"])
    assert ui_decisions["status"] == "pending"
    assert final_artifacts["professional_review_required"] is True
    assert stat.S_IMODE(output_dir.stat().st_mode) == 0o700


def test_new_client_render_exposes_only_safe_output_basenames(
    tmp_path: Path,
) -> None:
    output_dir = _generate_package(tmp_path)
    run_intake = json.loads(
        (output_dir / "run_intake.json").read_text(encoding="utf-8")
    )
    review_payload = json.loads(
        (output_dir / "review_payload.json").read_text(encoding="utf-8")
    )
    ui_decisions = json.loads(
        (output_dir / "ui_decisions.json").read_text(encoding="utf-8")
    )
    final_artifacts = json.loads(
        (output_dir / "final_artifacts.json").read_text(encoding="utf-8")
    )

    rendered = _call_mcp(
        [
            _tool_call(
                1,
                "render_new_client_review",
                {
                    "run_intake": run_intake,
                    "review_payload": review_payload,
                    "ui_decisions": ui_decisions,
                    "final_artifacts": final_artifacts,
                },
            )
        ]
    )[1]["result"]["structuredContent"]

    public_final = rendered["final_artifacts"]
    assert public_final["output_count"] == len(final_artifacts["outputs"])
    assert {record["path"] for record in public_final["outputs"]} == {
        record["path"] for record in final_artifacts["outputs"]
    }
    assert output_dir.as_posix() not in json.dumps(rendered)


def test_widget_visible_payload_persists_with_opaque_token(tmp_path: Path) -> None:
    output_dir = _generate_package(tmp_path)
    run_intake = json.loads(
        (output_dir / "run_intake.json").read_text(encoding="utf-8")
    )
    review_payload = json.loads(
        (output_dir / "review_payload.json").read_text(encoding="utf-8")
    )
    ui_decisions = json.loads(
        (output_dir / "ui_decisions.json").read_text(encoding="utf-8")
    )
    final_artifacts = json.loads(
        (output_dir / "final_artifacts.json").read_text(encoding="utf-8")
    )
    item_id = review_payload["items"][0]["id"]
    decisions = [{"item_id": item_id, "action": "accept"}]
    process = _start_mcp_session()

    try:
        rendered_response = _exchange_mcp(
            process,
            _tool_call(
                1,
                "render_new_client_review",
                {
                    "run_intake": run_intake,
                    "review_payload": review_payload,
                    "ui_decisions": ui_decisions,
                    "final_artifacts": final_artifacts,
                },
            ),
        )
        rendered = rendered_response["result"]["structuredContent"]
        token = rendered["decision_policy"]["persistence_token"]
        assert rendered["decision_policy"]["can_persist"] is True
        assert rendered["run_intake"]["language"] == "it"
        assert len(token) == 43
        assert output_dir.as_posix() not in json.dumps(rendered)

        save_response = _exchange_mcp(
            process,
            _tool_call(
                2,
                "save_new_client_decisions",
                {
                    "run_intake": rendered["run_intake"],
                    "persistence_token": token,
                    "review_payload": rendered["review_payload"],
                    "ui_decisions": rendered["ui_decisions"],
                    "decisions": decisions,
                    "decision_source": "mcp_widget",
                    "expected_decision_revision": 0,
                },
            ),
        )
        saved = save_response["result"]["structuredContent"]
        assert saved.get("persisted") is True, saved
        assert saved["ui_decisions"]["decision_revision"] == 1

        apply_response = _exchange_mcp(
            process,
            _tool_call(
                3,
                "apply_new_client_decisions",
                {
                    "run_intake": rendered["run_intake"],
                    "persistence_token": token,
                    "review_payload": rendered["review_payload"],
                    "ui_decisions": saved["ui_decisions"],
                    "decisions": decisions,
                    "decision_source": "mcp_widget",
                    "expected_decision_revision": 1,
                },
            ),
        )
        applied = apply_response["result"]["structuredContent"]
    finally:
        _stop_mcp_session(process)

    assert applied["persisted"] is True
    assert (output_dir / "applied_decisions.json").is_file()
    assert (output_dir / applied["review_history_path"]).is_file()


def test_privacy_minimized_reload_reuses_saved_decision_details(
    tmp_path: Path,
) -> None:
    output_dir = _generate_package(tmp_path)
    run_intake = json.loads(
        (output_dir / "run_intake.json").read_text(encoding="utf-8")
    )
    review_payload = json.loads(
        (output_dir / "review_payload.json").read_text(encoding="utf-8")
    )
    ui_decisions = json.loads(
        (output_dir / "ui_decisions.json").read_text(encoding="utf-8")
    )
    final_artifacts = json.loads(
        (output_dir / "final_artifacts.json").read_text(encoding="utf-8")
    )
    semantic_item = next(
        item
        for item in review_payload["items"]
        if item["item_type"] == "aml_risk_factor"
    )
    missing_item = next(
        item
        for item in review_payload["items"]
        if item["item_type"] == "missing_evidence"
    )
    semantic_note = "Professional rationale retained across a minimized reload."
    edit_value = "Use risk factor score 3 after professional review."
    document_note = "Obtain the listed evidence before completing the review."
    requested_documents = ["Current identity document", "Ownership evidence"]
    detailed_decisions = [
        {
            "item_id": semantic_item["id"],
            "action": "edit",
            "reviewer_note": semantic_note,
            "edit_value": edit_value,
        },
        {
            "item_id": missing_item["id"],
            "action": "request_more_documents",
            "reviewer_note": document_note,
            "requested_documents": requested_documents,
        },
    ]
    process = _start_mcp_session()

    try:
        first_render = _exchange_mcp(
            process,
            _tool_call(
                1,
                "render_new_client_review",
                {
                    "run_intake": run_intake,
                    "review_payload": review_payload,
                    "ui_decisions": ui_decisions,
                    "final_artifacts": final_artifacts,
                },
            ),
        )["result"]["structuredContent"]
        first_save = _exchange_mcp(
            process,
            _tool_call(
                2,
                "save_new_client_decisions",
                {
                    "run_intake": first_render["run_intake"],
                    "persistence_token": first_render["decision_policy"][
                        "persistence_token"
                    ],
                    "review_payload": first_render["review_payload"],
                    "ui_decisions": first_render["ui_decisions"],
                    "decisions": detailed_decisions,
                    "expected_decision_revision": 0,
                },
            ),
        )["result"]["structuredContent"]
        second_render = _exchange_mcp(
            process,
            _tool_call(
                3,
                "render_new_client_review",
                {
                    "run_intake": run_intake,
                    "review_payload": review_payload,
                    "ui_decisions": first_save["ui_decisions"],
                },
            ),
        )["result"]["structuredContent"]
        minimized_decisions = second_render["ui_decisions"]["decisions"]
        reuse_decisions = [
            {
                "item_id": decision["item_id"],
                "action": decision["action"],
                "reuse_saved_details": True,
            }
            for decision in minimized_decisions
        ]
        second_save = _exchange_mcp(
            process,
            _tool_call(
                4,
                "save_new_client_decisions",
                {
                    "run_intake": second_render["run_intake"],
                    "persistence_token": second_render["decision_policy"][
                        "persistence_token"
                    ],
                    "review_payload": second_render["review_payload"],
                    "ui_decisions": second_render["ui_decisions"],
                    "decisions": reuse_decisions,
                    "expected_decision_revision": 1,
                },
            ),
        )["result"]["structuredContent"]
        applied = _exchange_mcp(
            process,
            _tool_call(
                5,
                "apply_new_client_decisions",
                {
                    "run_intake": second_render["run_intake"],
                    "persistence_token": second_render["decision_policy"][
                        "persistence_token"
                    ],
                    "review_payload": second_render["review_payload"],
                    "ui_decisions": second_save["ui_decisions"],
                    "decisions": reuse_decisions,
                    "expected_decision_revision": 2,
                },
            ),
        )["result"]["structuredContent"]
    finally:
        _stop_mcp_session(process)

    assert first_save["persisted"] is True
    assert all(
        set(decision) == {"item_id", "action", "status"}
        for decision in minimized_decisions
    )
    assert second_save["persisted"] is True
    assert applied["persisted"] is True
    applied_by_id = {
        decision["item_id"]: decision
        for decision in applied["applied_decisions"]["decisions"]
    }
    assert applied_by_id[semantic_item["id"]]["reviewer_note"] == semantic_note
    assert applied_by_id[semantic_item["id"]]["edit_value"] == edit_value
    assert applied_by_id[missing_item["id"]]["reviewer_note"] == document_note
    assert (
        applied_by_id[missing_item["id"]]["requested_documents"] == requested_documents
    )
    persisted = json.loads(
        (output_dir / "applied_decisions.json").read_text(encoding="utf-8")
    )
    assert persisted["decisions"] == applied["applied_decisions"]["decisions"]


def test_save_invalidates_ready_gate_until_new_decisions_are_applied(
    tmp_path: Path,
) -> None:
    output_dir = _generate_package(tmp_path)
    core = _load_core()
    _mark_persistent_gate_ready(output_dir)
    run_intake = json.loads(
        (output_dir / "run_intake.json").read_text(encoding="utf-8")
    )
    review_payload = json.loads(
        (output_dir / "review_payload.json").read_text(encoding="utf-8")
    )
    rejected_item_id = review_payload["items"][0]["id"]

    rejected_save = _call_mcp(
        [
            _tool_call(
                1,
                "save_new_client_decisions",
                {
                    "run_intake": run_intake,
                    "review_payload": review_payload,
                    "decisions": _accepted_decisions(
                        review_payload,
                        rejected_item_id=rejected_item_id,
                    ),
                    "expected_decision_revision": 0,
                },
            )
        ]
    )[1]["result"]["structuredContent"]
    rejected_final = json.loads(
        (output_dir / "final_artifacts.json").read_text(encoding="utf-8")
    )

    assert rejected_save["persisted"] is True
    assert rejected_final["status"] == "blocked"
    assert rejected_final["export_gate"]["status"] == "blocked"
    assert rejected_final["export_gate"]["relationship_ready"] is False
    assert core.validate_contract(output_dir)["status"] == (
        "contract_validated_for_professional_review"
    )

    accepted_save = _call_mcp(
        [
            _tool_call(
                1,
                "save_new_client_decisions",
                {
                    "run_intake": run_intake,
                    "review_payload": review_payload,
                    "decisions": _accepted_decisions(review_payload),
                    "expected_decision_revision": 1,
                },
            )
        ]
    )[1]["result"]["structuredContent"]
    accepted_final = json.loads(
        (output_dir / "final_artifacts.json").read_text(encoding="utf-8")
    )

    assert accepted_save["persisted"] is True
    assert accepted_final["status"] == "pending_review"
    assert accepted_final["export_gate"]["status"] == "pending_review"
    assert accepted_final["export_gate"]["relationship_ready"] is False
    assert core.validate_contract(output_dir)["status"] == (
        "contract_validated_for_professional_review"
    )


def test_persistent_ready_gate_requires_professional_reviewer_alias(
    tmp_path: Path,
) -> None:
    output_dir = _generate_package(tmp_path)
    core = _load_core()
    _mark_persistent_gate_ready(output_dir)
    run_intake = json.loads(
        (output_dir / "run_intake.json").read_text(encoding="utf-8")
    )
    review_payload = json.loads(
        (output_dir / "review_payload.json").read_text(encoding="utf-8")
    )
    accepted = _accepted_decisions(review_payload)

    without_reviewer = _call_mcp(
        [
            _tool_call(
                1,
                "apply_new_client_decisions",
                {
                    "run_intake": run_intake,
                    "review_payload": review_payload,
                    "decisions": accepted,
                    "expected_decision_revision": 0,
                },
            )
        ]
    )[1]["result"]["structuredContent"]

    assert without_reviewer["application_status"] == "blocked"
    assert (
        without_reviewer["final_artifacts"]["export_gate"]["relationship_ready"]
        is False
    )
    assert core.validate_contract(output_dir)["status"] == (
        "contract_validated_for_professional_review"
    )

    with_reviewer = _call_mcp(
        [
            _tool_call(
                1,
                "apply_new_client_decisions",
                {
                    "run_intake": run_intake,
                    "review_payload": review_payload,
                    "decisions": accepted,
                    "reviewer": "reviewer-fg",
                    "expected_decision_revision": 1,
                },
            )
        ]
    )[1]["result"]["structuredContent"]

    assert with_reviewer["application_status"] == "ready_for_professional_export"
    assert with_reviewer["ui_decisions"]["reviewer"] == "reviewer-fg"
    assert with_reviewer["applied_decisions"]["reviewer"] == "reviewer-fg"
    assert with_reviewer["final_artifacts"]["export_gate"]["relationship_ready"] is True
    assert core.validate_contract(output_dir)["status"] == (
        "contract_validated_for_professional_review"
    )


def test_oldest_persistence_token_survives_lookup_at_capacity(
    tmp_path: Path,
) -> None:
    output_dir = _generate_package(tmp_path)
    run_intake = json.loads(
        (output_dir / "run_intake.json").read_text(encoding="utf-8")
    )
    review_payload = json.loads(
        (output_dir / "review_payload.json").read_text(encoding="utf-8")
    )
    ui_decisions = json.loads(
        (output_dir / "ui_decisions.json").read_text(encoding="utf-8")
    )
    final_artifacts = json.loads(
        (output_dir / "final_artifacts.json").read_text(encoding="utf-8")
    )
    process = _start_mcp_session()

    try:
        rendered_payloads = []
        for request_id in range(1, 129):
            rendered_payloads.append(
                _exchange_mcp(
                    process,
                    _tool_call(
                        request_id,
                        "render_new_client_review",
                        {
                            "run_intake": run_intake,
                            "review_payload": review_payload,
                            "ui_decisions": ui_decisions,
                            "final_artifacts": final_artifacts,
                        },
                    ),
                )["result"]["structuredContent"]
            )
        oldest = rendered_payloads[0]
        oldest_token = oldest["decision_policy"]["persistence_token"]
        assert (
            len(
                {
                    payload["decision_policy"]["persistence_token"]
                    for payload in rendered_payloads
                }
            )
            == 128
        )
        saved_response = _exchange_mcp(
            process,
            _tool_call(
                129,
                "save_new_client_decisions",
                {
                    "run_intake": oldest["run_intake"],
                    "persistence_token": oldest_token,
                    "review_payload": oldest["review_payload"],
                    "ui_decisions": oldest["ui_decisions"],
                    "decisions": [
                        {
                            "item_id": review_payload["items"][0]["id"],
                            "action": "accept",
                        }
                    ],
                    "expected_decision_revision": 0,
                },
            ),
        )["result"]
    finally:
        _stop_mcp_session(process)

    assert saved_response["isError"] is False
    assert saved_response["structuredContent"]["persisted"] is True


def test_persistence_token_rejects_altered_review_and_direct_path_mismatch(
    tmp_path: Path,
) -> None:
    output_dir = _generate_package(tmp_path)
    alternate_output_dir = _generate_package(tmp_path / "alternate")
    run_intake = json.loads(
        (output_dir / "run_intake.json").read_text(encoding="utf-8")
    )
    review_payload = json.loads(
        (output_dir / "review_payload.json").read_text(encoding="utf-8")
    )
    process = _start_mcp_session()

    try:
        rendered = _exchange_mcp(
            process,
            _tool_call(
                1,
                "render_new_client_review",
                {
                    "run_intake": run_intake,
                    "review_payload": review_payload,
                },
            ),
        )["result"]["structuredContent"]
        token = rendered["decision_policy"]["persistence_token"]
        altered_review = json.loads(json.dumps(review_payload))
        altered_review["privacy_notice"] += " Professional reviewer view."
        altered_response = _exchange_mcp(
            process,
            _tool_call(
                2,
                "save_new_client_decisions",
                {
                    "run_intake": rendered["run_intake"],
                    "persistence_token": token,
                    "review_payload": altered_review,
                    "decisions": [
                        {
                            "item_id": altered_review["items"][0]["id"],
                            "action": "accept",
                        }
                    ],
                },
            ),
        )["result"]
        mismatched_run_intake = {
            **run_intake,
            "output_dir": str(alternate_output_dir),
        }
        mismatch_response = _exchange_mcp(
            process,
            _tool_call(
                3,
                "save_new_client_decisions",
                {
                    "run_intake": mismatched_run_intake,
                    "persistence_token": token,
                    "review_payload": review_payload,
                    "decisions": [
                        {
                            "item_id": review_payload["items"][0]["id"],
                            "action": "accept",
                        }
                    ],
                },
            ),
        )["result"]
    finally:
        _stop_mcp_session(process)

    assert altered_response["isError"] is True
    assert (
        "persistence_token does not match this review run"
        in altered_response["structuredContent"]["error"]
    )
    assert mismatch_response["isError"] is True
    assert (
        "persistence_token and run_intake.output_dir do not match"
        in mismatch_response["structuredContent"]["error"]
    )


def test_widget_persistence_rejects_unknown_token(tmp_path: Path) -> None:
    output_dir = _generate_package(tmp_path)
    review_payload = json.loads(
        (output_dir / "review_payload.json").read_text(encoding="utf-8")
    )
    response = _call_mcp(
        [
            _tool_call(
                1,
                "save_new_client_decisions",
                {
                    "run_intake": {
                        "plugin": "new-client",
                        "workflow": "new-client",
                        "run_id": review_payload["run_id"],
                    },
                    "persistence_token": "A" * 43,
                    "review_payload": review_payload,
                    "decisions": [
                        {
                            "item_id": review_payload["items"][0]["id"],
                            "action": "accept",
                        }
                    ],
                },
            )
        ]
    )[1]["result"]

    assert response["isError"] is True
    assert "unknown or expired" in response["structuredContent"]["error"]


def test_new_client_mcp_enforces_semantic_and_document_request_notes(
    tmp_path: Path,
) -> None:
    output_dir = _generate_package(tmp_path)
    run_intake = json.loads(
        (output_dir / "run_intake.json").read_text(encoding="utf-8")
    )
    review_payload = json.loads(
        (output_dir / "review_payload.json").read_text(encoding="utf-8")
    )
    final_artifacts = json.loads(
        (output_dir / "final_artifacts.json").read_text(encoding="utf-8")
    )
    semantic_item = next(
        item
        for item in review_payload["items"]
        if item["item_type"] == "aml_risk_factor"
    )
    missing_item = next(
        item
        for item in review_payload["items"]
        if item["item_type"] == "missing_evidence"
    )
    common = {
        "run_intake": run_intake,
        "review_payload": review_payload,
        "final_artifacts": final_artifacts,
    }

    responses = _call_mcp(
        [
            _tool_call(
                1,
                "validate_new_client_review",
                {"review_payload": review_payload},
            ),
            _tool_call(
                2,
                "save_new_client_decisions",
                {
                    **common,
                    "decisions": [
                        {
                            "item_id": semantic_item["id"],
                            "action": "edit",
                            "edit_value": "Use score 3 after professional review.",
                        }
                    ],
                },
            ),
            _tool_call(
                3,
                "save_new_client_decisions",
                {
                    **common,
                    "decisions": [
                        {
                            "item_id": missing_item["id"],
                            "action": "request_more_documents",
                            "reviewer_note": "Evidence is still missing.",
                        }
                    ],
                },
            ),
        ]
    )

    assert responses[1]["result"]["structuredContent"]["ok"] is True
    assert responses[2]["result"]["isError"] is True
    assert (
        "reviewer_note is required"
        in responses[2]["result"]["structuredContent"]["error"]
    )
    assert responses[3]["result"]["isError"] is True
    assert (
        "requested_documents is required"
        in responses[3]["result"]["structuredContent"]["error"]
    )


def test_new_client_mcp_rejects_open_ended_review_status() -> None:
    review_payload = _strict_review_payload()
    review_payload["status"] = "compliant"

    error = _validation_error(review_payload)

    assert "review_payload.status is not supported" in error


def test_new_client_mcp_requires_current_contract_version() -> None:
    review_payload = _strict_review_payload()
    review_payload["contract_version"] = "1.0"

    error = _validation_error(review_payload)

    assert 'review_payload.contract_version must be "1.1"' in error


def test_new_client_mcp_rejects_unknown_item_data() -> None:
    review_payload = _strict_review_payload()
    review_payload["items"][0]["data"]["customer_alias"] = "CLIENT-ALT"

    error = _validation_error(review_payload)

    assert "review_payload.items[0].data.customer_alias is not allowed" in error


@pytest.mark.parametrize(
    "item_type", ["generated_document", "document_clause", "export_gate"]
)
def test_new_client_mcp_rejects_non_decision_item_contracts(
    item_type: str,
) -> None:
    review_payload = _strict_review_payload()
    review_payload["items"][0]["item_type"] = item_type

    error = _validation_error(review_payload)

    assert f"item_type is not supported: {item_type}" in error


def test_new_client_mcp_requires_all_source_artifact_bindings() -> None:
    review_payload = _strict_review_payload()
    del review_payload["source_artifacts"]["monitoring"]

    error = _validation_error(review_payload)

    assert "missing required keys: monitoring" in error


def test_new_client_mcp_requires_complete_basis_hashes() -> None:
    review_payload = _strict_review_payload()
    del review_payload["basis_hashes"]["sources"]

    error = _validation_error(review_payload)

    assert "missing required keys: sources" in error


@pytest.mark.parametrize(
    ("item_type", "data"),
    [
        (
            "client_file_preparation_binding",
            {
                "binding_mode": "standalone_evidence",
                "verification_status": "pending_review",
                "final_ready": False,
                "reviewed_client_file_preparation": False,
                "manifest_sha256": None,
                "relationship_blocker": True,
            },
        ),
        (
            "screening_result",
            {
                "screening_alias": "SCREENING-01",
                "subject_alias": "SUBJECT-01",
                "screening_type": "pep",
                "source_recorded": True,
                "checked_at": "2026-07-20T10:30:00Z",
                "outcome": "clear",
                "confirmation_status": "verified",
                "resolution_status": None,
                "relationship_decision": None,
                "resolution_evidence_count": 0,
                "raw_result_excluded": True,
            },
        ),
        (
            "privacy_processing",
            {
                "decision_alias": "PROCESSING-01",
                "purpose_recorded": True,
                "role": "controller",
                "legal_basis_code": None,
                "processor_authority_recorded": False,
                "retention_status": "pending_review",
                "review_status": "pending_review",
                "source_count": 1,
            },
        ),
        (
            "marketing_consent",
            {
                "scope": "separate_marketing_choice",
                "request_status": "not_requested",
                "choice": None,
                "purpose_count": 1,
                "channel_count": 0,
                "review_status": "pending_review",
                "relationship_export_blocking": False,
            },
        ),
        (
            "document_plan",
            {
                "documents": [
                    {
                        "document_type": "mandate",
                        "status": "template_reference_required",
                        "template_reference_id": None,
                    }
                ]
            },
        ),
    ],
)
def test_new_client_mcp_accepts_declared_compliance_item_contracts(
    item_type: str,
    data: dict[str, Any],
) -> None:
    review_payload = _strict_review_payload()
    review_payload["items"][0]["item_type"] = item_type
    review_payload["items"][0]["data"] = data

    response = _call_mcp(
        [
            _tool_call(
                1,
                "validate_new_client_review",
                {"review_payload": review_payload},
            )
        ]
    )[1]["result"]["structuredContent"]

    assert response["ok"] is True


def test_new_client_stateful_tools_are_not_declared_idempotent() -> None:
    response = _call_mcp(
        [
            {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "tools/list",
                "params": {},
            }
        ]
    )[1]["result"]
    tools_by_name = {tool["name"]: tool for tool in response["tools"]}

    for tool_name in (
        "render_new_client_review",
        "save_new_client_decisions",
        "apply_new_client_decisions",
    ):
        assert tools_by_name[tool_name]["annotations"]["idempotentHint"] is False


def test_new_client_mcp_rejects_output_inside_source_package() -> None:
    review_payload = _strict_review_payload()

    response = _call_mcp(
        [
            _tool_call(
                1,
                "save_new_client_decisions",
                {
                    "run_intake": {
                        "schema_version": "1.1",
                        "plugin": "new-client",
                        "workflow": "new-client",
                        "run_id": review_payload["run_id"],
                        "output_dir": str(PLUGIN_ROOT),
                    },
                    "review_payload": review_payload,
                    "decisions": [{"item_id": "party-fact-01", "action": "accept"}],
                },
            )
        ]
    )[1]["result"]

    assert response["isError"] is True
    assert (
        "outside the plugin package and source repository"
        in response["structuredContent"]["error"]
    )


def test_new_client_save_apply_preserves_integrity_and_history(
    tmp_path: Path,
) -> None:
    output_dir = _generate_package(tmp_path)
    core = _load_core()
    run_intake = json.loads(
        (output_dir / "run_intake.json").read_text(encoding="utf-8")
    )
    review_payload = json.loads(
        (output_dir / "review_payload.json").read_text(encoding="utf-8")
    )
    final_artifacts = json.loads(
        (output_dir / "final_artifacts.json").read_text(encoding="utf-8")
    )
    item_id = review_payload["items"][0]["id"]
    common = {
        "run_intake": run_intake,
        "review_payload": review_payload,
        "final_artifacts": final_artifacts,
        "decisions": [{"item_id": item_id, "action": "accept"}],
        "decision_source": "pytest_professional_review",
    }

    saved = _call_mcp([_tool_call(1, "save_new_client_decisions", common)])[1][
        "result"
    ]["structuredContent"]

    assert saved["ok"] is True
    assert saved["persisted"] is True
    assert core.validate_contract(output_dir)["status"] == (
        "contract_validated_for_professional_review"
    )

    refreshed_final = json.loads(
        (output_dir / "final_artifacts.json").read_text(encoding="utf-8")
    )
    refreshed_ui_decisions = json.loads(
        (output_dir / "ui_decisions.json").read_text(encoding="utf-8")
    )
    applied = _call_mcp(
        [
            _tool_call(
                1,
                "apply_new_client_decisions",
                {
                    **common,
                    "ui_decisions": refreshed_ui_decisions,
                    "final_artifacts": refreshed_final,
                    "expected_decision_revision": 1,
                },
            )
        ]
    )[1]["result"]["structuredContent"]

    assert applied["ok"] is True
    assert applied["application_status"] == "blocked"
    assert applied["domain_artifacts_modified"] is False
    history_path = output_dir / applied["review_history_path"]
    assert history_path.is_file()
    assert stat.S_IMODE(history_path.stat().st_mode) == 0o600
    assert core.validate_contract(output_dir)["status"] == (
        "contract_validated_for_professional_review"
    )
    final = json.loads(
        (output_dir / "final_artifacts.json").read_text(encoding="utf-8")
    )
    original_gate = final_artifacts["export_gate"]
    updated_gate = final["export_gate"]
    assert final["review_application"]["history_path"] == history_path.name
    assert updated_gate["domain_blockers"] == original_gate["domain_blockers"]
    assert updated_gate["artifact_blockers"] == original_gate["artifact_blockers"]
    assert (
        updated_gate["marketing_only_blockers"]
        == original_gate["marketing_only_blockers"]
    )
    assert updated_gate["basis_hashes"] == original_gate["basis_hashes"]
    assert updated_gate["required_outputs"] == original_gate["required_outputs"]
    assert set(updated_gate["required_outputs"]) <= {
        record["path"] for record in final["outputs"]
    }
    assert updated_gate["relationship_ready"] is False
    assert final["signature_performed"] is False
    assert final["client_communication_sent"] is False
    assert final["relationship_activation_performed"] is False


def test_new_client_save_rejects_stale_decision_revision(
    tmp_path: Path,
) -> None:
    output_dir = _generate_package(tmp_path)
    run_intake = json.loads(
        (output_dir / "run_intake.json").read_text(encoding="utf-8")
    )
    review_payload = json.loads(
        (output_dir / "review_payload.json").read_text(encoding="utf-8")
    )
    ui_decisions = json.loads(
        (output_dir / "ui_decisions.json").read_text(encoding="utf-8")
    )
    final_artifacts = json.loads(
        (output_dir / "final_artifacts.json").read_text(encoding="utf-8")
    )
    arguments = {
        "run_intake": run_intake,
        "review_payload": review_payload,
        "ui_decisions": ui_decisions,
        "final_artifacts": final_artifacts,
        "decisions": [
            {"item_id": review_payload["items"][0]["id"], "action": "accept"}
        ],
        "decision_source": "pytest_professional_review",
        "expected_decision_revision": 0,
    }

    first = _call_mcp([_tool_call(1, "save_new_client_decisions", arguments)])[1][
        "result"
    ]["structuredContent"]
    ui_after_first = (output_dir / "ui_decisions.json").read_bytes()
    final_after_first = (output_dir / "final_artifacts.json").read_bytes()
    stale = _call_mcp([_tool_call(1, "save_new_client_decisions", arguments)])[1][
        "result"
    ]

    assert first["ok"] is True
    assert first["ui_decisions"]["decision_revision"] == 1
    assert stale["isError"] is True
    assert (
        "stale decision revision: expected 0, current 1"
        in stale["structuredContent"]["error"]
    )
    assert (output_dir / "ui_decisions.json").read_bytes() == ui_after_first
    assert (output_dir / "final_artifacts.json").read_bytes() == final_after_first


def test_new_client_save_rejects_tampered_local_artifact_before_writing(
    tmp_path: Path,
) -> None:
    output_dir = _generate_package(tmp_path)
    run_intake = json.loads(
        (output_dir / "run_intake.json").read_text(encoding="utf-8")
    )
    review_payload = json.loads(
        (output_dir / "review_payload.json").read_text(encoding="utf-8")
    )
    ui_decisions = json.loads(
        (output_dir / "ui_decisions.json").read_text(encoding="utf-8")
    )
    final_artifacts = json.loads(
        (output_dir / "final_artifacts.json").read_text(encoding="utf-8")
    )
    ui_before = (output_dir / "ui_decisions.json").read_bytes()
    final_before = (output_dir / "final_artifacts.json").read_bytes()
    document_plan_path = output_dir / "document_plan.json"
    document_plan = json.loads(document_plan_path.read_text(encoding="utf-8"))
    document_plan["tampered_test_marker"] = True
    document_plan_path.write_text(
        json.dumps(document_plan, indent=2) + "\n",
        encoding="utf-8",
    )
    document_plan_path.chmod(0o600)

    response = _call_mcp(
        [
            _tool_call(
                1,
                "save_new_client_decisions",
                {
                    "run_intake": run_intake,
                    "review_payload": review_payload,
                    "ui_decisions": ui_decisions,
                    "final_artifacts": final_artifacts,
                    "decisions": [
                        {
                            "item_id": review_payload["items"][0]["id"],
                            "action": "accept",
                        }
                    ],
                    "decision_source": "pytest_professional_review",
                    "expected_decision_revision": 0,
                },
            )
        ]
    )[1]["result"]

    assert response["isError"] is True
    assert (
        "manifest output hash mismatch: document_plan.json"
        in response["structuredContent"]["error"]
    )
    assert (output_dir / "ui_decisions.json").read_bytes() == ui_before
    assert (output_dir / "final_artifacts.json").read_bytes() == final_before


def test_new_client_save_rejects_incomplete_export_gate_before_writing(
    tmp_path: Path,
) -> None:
    output_dir = _generate_package(tmp_path)
    run_intake = json.loads(
        (output_dir / "run_intake.json").read_text(encoding="utf-8")
    )
    review_payload = json.loads(
        (output_dir / "review_payload.json").read_text(encoding="utf-8")
    )
    ui_decisions = json.loads(
        (output_dir / "ui_decisions.json").read_text(encoding="utf-8")
    )
    final_artifacts_path = output_dir / "final_artifacts.json"
    final_artifacts = json.loads(final_artifacts_path.read_text(encoding="utf-8"))
    final_artifacts["export_gate"]["required_outputs"] = []
    final_artifacts_path.write_text(
        json.dumps(final_artifacts, indent=2) + "\n",
        encoding="utf-8",
    )
    final_artifacts_path.chmod(0o600)
    ui_before = (output_dir / "ui_decisions.json").read_bytes()
    invalid_final_before = final_artifacts_path.read_bytes()

    response = _call_mcp(
        [
            _tool_call(
                1,
                "save_new_client_decisions",
                {
                    "run_intake": run_intake,
                    "review_payload": review_payload,
                    "ui_decisions": ui_decisions,
                    "final_artifacts": final_artifacts,
                    "decisions": [
                        {
                            "item_id": review_payload["items"][0]["id"],
                            "action": "accept",
                        }
                    ],
                    "decision_source": "pytest_professional_review",
                    "expected_decision_revision": 0,
                },
            )
        ]
    )[1]["result"]

    assert response["isError"] is True
    assert (
        "export_gate.required_outputs must be non-empty"
        in response["structuredContent"]["error"]
    )
    assert (output_dir / "ui_decisions.json").read_bytes() == ui_before
    assert final_artifacts_path.read_bytes() == invalid_final_before


def test_new_client_preview_cannot_claim_professional_export_readiness() -> None:
    review_payload = _strict_review_payload()
    final_artifacts = {
        "schema_version": "1.1",
        "contract_version": "1.1",
        "plugin": "new-client",
        "workflow": "new-client",
        "run_id": review_payload["run_id"],
        "status": "pending_review",
        "outputs": [
            {
                "path": "review_payload.json",
                "kind": "json",
                "status": "written_pending_review",
                "size_bytes": 1,
                "sha256": "b" * 64,
            }
        ],
        "blockers": [],
        "export_gate": {
            "contract_version": "1.1",
            "export_scope": "owner_only_professional_review_dossier",
            "evaluated_at": "2026-07-20T10:30:00Z",
            "review_revision": 1,
            "status": "pending_review",
            "relationship_ready": False,
            "domain_blockers": [],
            "review_blockers": [
                {
                    "code": "professional_review_pending",
                    "reference": "party-fact-01",
                    "scope": "relationship_export",
                }
            ],
            "artifact_blockers": [],
            "marketing_only_blockers": [],
            "required_outputs": [
                "run_intake.json",
                "case_facts_validated.json",
                "source_registry.json",
                "applicability_plan_validated.json",
                "aml_assessment_draft.json",
                "aml_calculation_audit.json",
                "missing_evidence.json",
                "document_plan.json",
                "monitoring_plan.json",
                "studio_new_client_memo.md",
                "client_missing_information_draft.md",
                "review_payload.json",
                "ui_decisions.json",
                "review_handoff.md",
            ],
            "basis_hashes": review_payload["basis_hashes"],
        },
        "professional_review_required": True,
        "signature_performed": False,
        "client_communication_sent": False,
        "relationship_activation_performed": False,
    }
    response = _call_mcp(
        [
            _tool_call(
                1,
                "apply_new_client_decisions",
                {
                    "review_payload": review_payload,
                    "final_artifacts": final_artifacts,
                    "decisions": [{"item_id": "party-fact-01", "action": "accept"}],
                    "decision_source": "professional_review",
                },
            )
        ]
    )[1]["result"]["structuredContent"]

    assert response["ok"] is True
    assert response["application_status"] == "partial_review_applied"
    assert response["persisted"] is False
    assert response["domain_artifacts_modified"] is False
    final = response["final_artifacts"]
    assert final["status"] == "pending_review"
    assert final["export_gate"]["status"] == "pending_review"
    assert final["export_gate"]["relationship_ready"] is False
    assert final["professional_review_required"] is True
    assert final["signature_performed"] is False
    assert final["client_communication_sent"] is False
    assert final["relationship_activation_performed"] is False


def test_new_client_edit_requires_revision_before_export() -> None:
    review_payload = _strict_review_payload()

    response = _call_mcp(
        [
            _tool_call(
                1,
                "apply_new_client_decisions",
                {
                    "review_payload": review_payload,
                    "decisions": [
                        {
                            "item_id": "party-fact-01",
                            "action": "edit",
                            "edit_value": "Use the revised verified classification.",
                        }
                    ],
                    "decision_source": "professional_review",
                },
            )
        ]
    )[1]["result"]["structuredContent"]

    assert response["ok"] is True
    assert response["application_status"] == "proposals_ready"
    assert response["revision_required"] is True
    assert response["edited_item_ids"] == ["party-fact-01"]
    assert response["domain_artifacts_modified"] is False
    assert response["final_artifacts"]["status"] == "proposals_ready"


def test_new_client_marketing_blocker_does_not_block_relationship() -> None:
    review_payload = _strict_review_payload()
    review_payload["items"].append(
        {
            "id": "marketing-consent-01",
            "item_type": "marketing_consent",
            "title": "Separate marketing consent",
            "status": "needs_review",
            "allowed_actions": [
                "accept",
                "reject",
                "edit",
                "mark_unclear",
                "request_more_documents",
                "skip",
            ],
            "recommended_action": "mark_unclear",
            "data": {
                "scope": "marketing_only",
                "request_status": "requested",
                "choice": None,
                "purpose_count": 1,
                "channel_count": 1,
                "review_status": "pending_review",
                "relationship_export_blocking": False,
            },
        }
    )
    review_payload["item_count"] = 2

    response = _call_mcp(
        [
            _tool_call(
                1,
                "apply_new_client_decisions",
                {
                    "review_payload": review_payload,
                    "decisions": [
                        {"item_id": "party-fact-01", "action": "accept"},
                        {"item_id": "marketing-consent-01", "action": "reject"},
                    ],
                    "decision_source": "professional_review",
                },
            )
        ]
    )[1]["result"]["structuredContent"]

    assert response["ok"] is True
    assert response["application_status"] == "partial_review_applied"
    assert response["blocker_count"] == 0
    assert response["marketing_use_blocker_count"] == 1
    assert response["applied_decisions"]["blockers"][0]["scope"] == "marketing_use"


def test_new_client_widget_state_excludes_free_text_decisions() -> None:
    adapter = json.loads(
        (PLUGIN_ROOT / "assets" / "review-workbench-adapter.json").read_text(
            encoding="utf-8"
        )
    )
    widget = (PLUGIN_ROOT / "assets" / "new-client-review-widget.html").read_text(
        encoding="utf-8"
    )

    assert adapter["persistDecisionTextInWidgetState"] is False
    assert adapter["useDecisionRevision"] is True
    assert adapter["schemaVersion"] == "1.1"
    assert 'schema_version: "1.1"' in widget
    assert 'schema_version: "1.0"' not in widget
    assert "decisions: decisionsForWidgetState()" in widget
    assert "return { item_id: decision.item_id, action: decision.action };" in widget
    assert "decisions: state.decisions" not in widget
    assert "expected_decision_revision" in widget
    assert (
        "if (result.ui_decisions) state.payload.ui_decisions = result.ui_decisions;"
        in widget
    )


def test_new_client_public_page_explains_one_operational_journey() -> None:
    page = (ROOT / "static" / "shared" / "new-client" / "index.html").read_text(
        encoding="utf-8"
    )

    for snippet in (
        "Vera · Nuovo cliente",
        "Un solo percorso",
        "Organizza ciò che è arrivato",
        "Completa ciò che manca",
        "Imposta il rapporto",
        "Struttura i piani documentali e l’AML",
        "Mantiene il fascicolo aggiornato",
        "RI 30% + RS 70%",
        "Mandato",
        "Privacy",
        "Informativa AI",
        "Fascicolo AML",
        "Il fascicolo mostra dove siamo e che cosa viene dopo.",
        'id="prompt-example"',
    ):
        assert snippet.casefold() in page.casefold()
    assert 'class="journey-step__number"' not in page
    for numbered_label in ("01 ·", "02 ·", "03 ·", "04 ·", "05 ·"):
        assert numbered_label not in page
    for unsupported_claim in (
        "i documenti preparati",
        "prepared documents",
        "documents préparés",
        "vorbereitete dokumente",
        "incarico e privacy preparati",
        "engagement and privacy prepared",
        "mission et privacy préparées",
        "auftrag und datenschutz vorbereitet",
    ):
        assert unsupported_claim not in page.casefold()
    assert "client-intake" not in page
    assert "client-onboarding" not in page
    assert "localStorage" not in page
    assert "linear-gradient" not in page
