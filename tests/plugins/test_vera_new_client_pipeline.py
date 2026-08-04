from __future__ import annotations

import importlib.util
import json
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any, Callable

import pytest

ROOT = Path(__file__).resolve().parents[2]
FILE_PREPARATION_ROOT = ROOT / "plugins" / "client-file-preparation"
NEW_CLIENT_ROOT = ROOT / "plugins" / "new-client"


def _node_binary() -> str:
    node = shutil.which("node")
    if node is not None:
        return node
    candidates = sorted(
        (Path.home() / ".cache" / "codex-runtimes").glob("*/dependencies/node/bin/node")
    )
    if not candidates:
        pytest.skip("Node.js is required for the end-to-end review handoff test.")
    return candidates[-1].as_posix()


def _run_python(script: Path, *args: str) -> dict[str, Any] | None:
    completed = subprocess.run(
        [sys.executable, script.as_posix(), *args],
        cwd=script.parent.parent,
        capture_output=True,
        check=True,
        text=True,
        timeout=30,
    )
    lines = [line for line in completed.stdout.splitlines() if line.strip()]
    return json.loads(lines[-1]) if lines else None


def _run_python_failure(script: Path, *args: str) -> dict[str, Any]:
    completed = subprocess.run(
        [sys.executable, script.as_posix(), *args],
        cwd=script.parent.parent,
        capture_output=True,
        check=False,
        text=True,
        timeout=30,
    )
    assert completed.returncode == 2, completed.stderr
    lines = [line for line in completed.stdout.splitlines() if line.strip()]
    assert lines
    return json.loads(lines[-1])


def _load_python_module(name: str, script: Path) -> Any:
    spec = importlib.util.spec_from_file_location(name, script)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def _apply_phase_one_review(
    output_dir: Path,
    client_engagement: Path,
) -> dict[str, Any]:
    run_intake = json.loads(
        (output_dir / "run_intake.json").read_text(encoding="utf-8")
    )
    review_payload = json.loads(
        (output_dir / "review_payload.json").read_text(encoding="utf-8")
    )
    final_artifacts = json.loads(
        (output_dir / "final_artifacts.json").read_text(encoding="utf-8")
    )
    decisions = [
        {"item_id": item["id"], "action": "accept"} for item in review_payload["items"]
    ]
    request = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "tools/call",
        "params": {
            "name": "apply_client_file_preparation_decisions",
            "arguments": {
                "client_engagement": client_engagement.as_posix(),
                "run_intake": run_intake,
                "review_payload": review_payload,
                "final_artifacts": final_artifacts,
                "reviewer": "reviewer-e2e",
                "decisions": decisions,
            },
        },
    }
    completed = subprocess.run(
        [
            _node_binary(),
            (FILE_PREPARATION_ROOT / "mcp" / "server.cjs").as_posix(),
            "--stdio",
        ],
        cwd=FILE_PREPARATION_ROOT,
        input=json.dumps(request) + "\n",
        capture_output=True,
        check=True,
        text=True,
        timeout=30,
    )
    response = json.loads(completed.stdout.strip().splitlines()[-1])
    return response["result"]["structuredContent"]


def test_new_client_pipeline_promotes_a_sealed_reviewed_phase_one_run(
    vera_workflow_workspace: Callable[..., dict[str, Any]],
) -> None:
    engagement_id = "new-client-e2e"
    phase_one = vera_workflow_workspace(
        "client-file-preparation",
        engagement_id=engagement_id,
        input_files={
            "CU_2025.txt": (
                "Certificazione Unica 2025. " "Codice fiscale TSTUSR80A01H501U."
            )
        },
    )
    customer_dir = phase_one["input_dir"]
    phase_one_dir = phase_one["output_dir"]

    _run_python(
        FILE_PREPARATION_ROOT / "scripts" / "build_file_preparation_outputs.py",
        customer_dir.as_posix(),
        "--year",
        "2025",
        "--out",
        phase_one_dir.as_posix(),
        "--client-engagement",
        phase_one["context_path"].as_posix(),
        "--no-ocr",
        "--jurisdiction",
        "italy",
        "--language",
        "en",
    )
    phase_one_intake = json.loads(
        (phase_one_dir / "run_intake.json").read_text(encoding="utf-8")
    )
    phase_one_review = json.loads(
        (phase_one_dir / "review_payload.json").read_text(encoding="utf-8")
    )
    assert phase_one_intake["run_id"] == phase_one["run_id"]
    assert phase_one_review["run_id"] == phase_one["run_id"]
    phase_one_application = _apply_phase_one_review(
        phase_one_dir,
        phase_one["context_path"],
    )

    assert phase_one_application["application_status"] == "final_ready"
    sealed_manifest = json.loads(
        (phase_one_dir / "final_artifacts.json").read_text(encoding="utf-8")
    )
    assert sealed_manifest["integrity"]["algorithm"] == "sha256"

    phase_two = vera_workflow_workspace(
        "new-client",
        engagement_id=engagement_id,
        upstream_workspace=phase_one,
    )
    phase_two_dir = phase_two["output_dir"]
    phase_one_manifest = phase_two["input_by_name"]["final_artifacts.json"]
    promotion = _run_python(
        NEW_CLIENT_ROOT / "scripts" / "promote_client_file_preparation.py",
        "--final-artifacts",
        phase_one_manifest.as_posix(),
        "--case-dir",
        phase_two_dir.as_posix(),
        "--client-engagement",
        phase_two["context_path"].as_posix(),
        "--client-reference",
        "CLIENT-001",
    )

    assert promotion is not None
    assert promotion["status"] == "new_client_input_promoted"
    intake_path = phase_two_dir / "new_client_input.json"
    intake = json.loads(intake_path.read_text(encoding="utf-8"))
    assert intake["language"] == "en"
    assert intake["jurisdiction"] == "IT"
    assert intake["tax_facts"]["codice_fiscale"] == {
        "value": "TSTUSR80A01H501U",
        "verification_status": "reported",
        "evidence_ids": ["phase1-reviewed-decisions"],
    }
    binding = intake["client_file_preparation_binding"]
    assert binding["final_artifacts_path_reference"] == "run_root_relative"
    assert not Path(binding["final_artifacts_path"]).is_absolute()
    assert intake["evidence_register"][0]["local_path_reference"] == (
        "run_root_relative"
    )

    intake_path.write_text(
        json.dumps(intake, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    packaged = _run_python(
        NEW_CLIENT_ROOT / "scripts" / "package_new_client.py",
        "--input",
        intake_path.as_posix(),
        "--output-dir",
        phase_two_dir.as_posix(),
        "--client-engagement",
        phase_two["context_path"].as_posix(),
    )

    assert packaged is not None
    assert packaged["status"] in {"blocked", "written_pending_review"}
    phase_two_intake = json.loads(
        (phase_two_dir / "run_intake.json").read_text(encoding="utf-8")
    )
    phase_two_review = json.loads(
        (phase_two_dir / "review_payload.json").read_text(encoding="utf-8")
    )
    assert phase_two_intake["run_id"] == phase_two["run_id"]
    assert phase_two_review["run_id"] == phase_two["run_id"]
    case_facts = json.loads(
        (phase_two_dir / "case_facts_validated.json").read_text(encoding="utf-8")
    )
    assert (
        case_facts["client_file_preparation_verification"]["verification_status"]
        == "verified_final_ready"
    )
    for artifact in phase_two_dir.rglob("*.json"):
        durable_json = artifact.read_text(encoding="utf-8")
        assert phase_two["client_root"].as_posix() not in durable_json
        assert NEW_CLIENT_ROOT.as_posix() not in durable_json


def test_new_client_promotion_rejects_a_directly_imported_phase_one_manifest(
    vera_workflow_workspace: Callable[..., dict[str, Any]],
) -> None:
    workspace = vera_workflow_workspace(
        "new-client",
        input_files={"final_artifacts.json": "{}\n"},
    )

    result = _run_python_failure(
        NEW_CLIENT_ROOT / "scripts" / "promote_client_file_preparation.py",
        "--final-artifacts",
        workspace["input_by_name"]["final_artifacts.json"].as_posix(),
        "--case-dir",
        workspace["output_dir"].as_posix(),
        "--client-engagement",
        workspace["context_path"].as_posix(),
        "--client-reference",
        "CLIENT-IMPORTED-PHASE-ONE",
    )

    assert result["status"] == "error"
    assert "upstream-artifact handoff" in result["error"]
    assert not (workspace["output_dir"] / "new_client_input.json").exists()


def test_new_client_promotion_rejects_another_workflows_artifact(
    vera_workflow_workspace: Callable[..., dict[str, Any]],
) -> None:
    engagement_id = "wrong-upstream-workflow"
    upstream = vera_workflow_workspace(
        "financial-analysis",
        engagement_id=engagement_id,
    )
    (upstream["output_dir"] / "final_artifacts.json").write_text(
        json.dumps({"run_id": upstream["run_id"]}) + "\n",
        encoding="utf-8",
    )
    workspace = vera_workflow_workspace(
        "new-client",
        engagement_id=engagement_id,
        upstream_workspace=upstream,
    )

    result = _run_python_failure(
        NEW_CLIENT_ROOT / "scripts" / "promote_client_file_preparation.py",
        "--final-artifacts",
        workspace["input_by_name"]["final_artifacts.json"].as_posix(),
        "--case-dir",
        workspace["output_dir"].as_posix(),
        "--client-engagement",
        workspace["context_path"].as_posix(),
        "--client-reference",
        "CLIENT-WRONG-WORKFLOW",
    )

    assert result["status"] == "error"
    assert "upstream-artifact handoff" in result["error"]
    assert not (workspace["output_dir"] / "new_client_input.json").exists()


def test_client_file_preparation_mcp_rejects_ledger_run_id_mismatch_without_write(
    vera_workflow_workspace: Callable[..., dict[str, Any]],
) -> None:
    workspace = vera_workflow_workspace(
        "client-file-preparation",
        input_files={"CU_2025.txt": "Certificazione Unica 2025."},
    )
    builder = _load_python_module(
        "client_file_preparation_mcp_run_id_mismatch",
        FILE_PREPARATION_ROOT / "scripts" / "build_file_preparation_outputs.py",
    )
    builder.build_file_preparation_outputs(
        workspace["input_dir"],
        target_year=2025,
        output_dir=workspace["output_dir"],
        enable_ocr=False,
        language="en",
        run_id="client-file-preparation-mismatched-run",
    )
    output_dir = Path(workspace["output_dir"])
    ui_path = output_dir / "ui_decisions.json"
    final_path = output_dir / "final_artifacts.json"
    ui_before = ui_path.read_bytes()
    final_before = final_path.read_bytes()

    result = _apply_phase_one_review(output_dir, workspace["context_path"])

    assert result["ok"] is False
    assert "customer-run preflight returned an invalid result" in result["error"]
    assert ui_path.read_bytes() == ui_before
    assert final_path.read_bytes() == final_before
