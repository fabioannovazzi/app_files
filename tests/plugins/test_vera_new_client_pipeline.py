from __future__ import annotations

import json
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

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


def _apply_phase_one_review(output_dir: Path) -> dict[str, Any]:
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
    tmp_path: Path,
) -> None:
    customer_dir = tmp_path / "customer"
    customer_dir.mkdir()
    (customer_dir / "CU_2025.txt").write_text(
        "Certificazione Unica 2025. Codice fiscale TSTUSR80A01H501U.",
        encoding="utf-8",
    )
    phase_one_dir = tmp_path / "phase-one"

    _run_python(
        FILE_PREPARATION_ROOT / "scripts" / "build_file_preparation_outputs.py",
        customer_dir.as_posix(),
        "--year",
        "2025",
        "--out",
        phase_one_dir.as_posix(),
        "--no-ocr",
        "--jurisdiction",
        "italy",
        "--language",
        "en",
    )
    phase_one_application = _apply_phase_one_review(phase_one_dir)

    assert phase_one_application["application_status"] == "final_ready"
    sealed_manifest = json.loads(
        (phase_one_dir / "final_artifacts.json").read_text(encoding="utf-8")
    )
    assert sealed_manifest["integrity"]["algorithm"] == "sha256"

    phase_two_dir = tmp_path / "phase-two"
    promotion = _run_python(
        NEW_CLIENT_ROOT / "scripts" / "promote_client_file_preparation.py",
        "--final-artifacts",
        (phase_one_dir / "final_artifacts.json").as_posix(),
        "--case-dir",
        phase_two_dir.as_posix(),
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

    intake["processing_authority"] = {
        "status": "authorized",
        "scope": "new_client_professional_setup",
        "runtime": "local_codex_workspace",
        "minimization": "structured_facts_and_selected_excerpts",
        "external_transfer_authorized": False,
        "authorized_by": "reviewer-e2e",
        "authorized_by_role": "professional",
        "authorized_at": "2026-07-21T12:00:00Z",
    }
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
    )

    assert packaged is not None
    assert packaged["status"] in {"blocked", "written_pending_review"}
    case_facts = json.loads(
        (phase_two_dir / "case_facts_validated.json").read_text(encoding="utf-8")
    )
    assert (
        case_facts["client_file_preparation_verification"]["verification_status"]
        == "verified_final_ready"
    )
