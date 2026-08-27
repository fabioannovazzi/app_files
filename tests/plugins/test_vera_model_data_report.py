from __future__ import annotations

import copy
import importlib.util
import json
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
SCRIPT_PATH = ROOT / "plugins" / "vera" / "scripts" / "model_data_report.py"
ROUTER_PATH = ROOT / "plugins" / "vera" / "skills" / "vera" / "SKILL.md"
CONTRACT_PATH = (
    ROOT
    / "plugins"
    / "vera"
    / "skills"
    / "vera"
    / "references"
    / "model-data-report-contract.md"
)


def _load_module():
    spec = importlib.util.spec_from_file_location("vera_model_data_report", SCRIPT_PATH)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _measurement(
    unit: str,
    quantity: int,
    label: str,
    *,
    basis: str = "measured",
) -> dict[str, object]:
    return {
        "unit": unit,
        "quantity": quantity,
        "label": label,
        "basis": basis,
    }


def _reduced_request() -> dict[str, object]:
    return {
        "schema_version": 1,
        "workflow_id": "variance-analysis",
        "run_id": "run_0123456789abcdef01234567",
        "runtime_profile": "openai-codex",
        "language": "it",
        "created_at": "2026-08-27T12:00:00+02:00",
        "professional_purpose": "Confrontare Actual e Budget con mapping rivisto.",
        "phases": [
            {
                "phase_id": "mapping",
                "purpose": "Rivedere il significato delle colonne candidate.",
                "outcome": "reduced_projection",
                "evidence_basis": "exact_payload_receipt",
                "source_extent": [
                    _measurement("rows", 10_000, "righe della fonte"),
                    _measurement("columns", 14, "colonne della fonte"),
                ],
                "locally_processed": [
                    _measurement("rows", 10_000, "righe inventariate"),
                    _measurement("columns", 14, "colonne profilate"),
                ],
                "model_visible": [
                    _measurement("rows", 10, "righe candidate"),
                    _measurement("columns", 8, "colonne candidate"),
                ],
                "remained_local": [
                    _measurement("rows", 9_990, "righe non mostrate"),
                    _measurement("columns", 6, "colonne non mostrate"),
                ],
                "reason": "Il modello doveva stabilire il mapping semantico.",
                "evidence_files": ["mapping_payload.json"],
            }
        ],
        "improvement_assessment": {
            "status": "candidate",
            "candidates": [
                {
                    "candidate_id": "omit-unused-columns-after-mapping",
                    "phase_ids": ["mapping"],
                    "change": "Escludere due colonne dopo la conferma del mapping.",
                    "evidence": [
                        "Nessun calcolo o controllo successivo dipende dalle due colonne."
                    ],
                    "estimated_reduction": [
                        _measurement(
                            "columns",
                            2,
                            "colonne potenzialmente escluse",
                            basis="derived",
                        )
                    ],
                    "quality_safeguard": (
                        "Confrontare casi rappresentativi e mantenere il drill-down esatto."
                    ),
                    "status": "candidate_needs_validation",
                    "validation_evidence": [],
                }
            ],
        },
    }


def _full_document_request(language: str = "en") -> dict[str, object]:
    return {
        "schema_version": 1,
        "workflow_id": "concordato-plan-review",
        "run_id": "run_89abcdef0123456789abcdef",
        "runtime_profile": "anthropic-cowork",
        "language": language,
        "created_at": "2026-08-27T10:00:00+00:00",
        "professional_purpose": "Review the complete plan and its internal consistency.",
        "phases": [
            {
                "phase_id": "semantic-review",
                "purpose": "Read the complete plan as one connected document.",
                "outcome": "full_context_required",
                "evidence_basis": "workflow_receipt",
                "source_extent": [
                    _measurement("files", 1, "selected plan"),
                    _measurement("pages", 84, "selected plan pages"),
                ],
                "locally_processed": [
                    _measurement("files", 1, "hash-bound source"),
                ],
                "model_visible": [
                    _measurement("files", 1, "complete selected plan"),
                    _measurement("pages", 84, "complete selected plan pages"),
                ],
                "remained_local": [],
                "reason": "Section relationships could not be reviewed from isolated excerpts.",
                "evidence_files": [],
            }
        ],
        "improvement_assessment": {
            "status": "not_assessed",
            "candidates": [],
        },
    }


def test_reduced_projection_builds_hash_bound_localized_report(tmp_path: Path) -> None:
    module = _load_module()
    payload_path = tmp_path / "mapping_payload.json"
    payload_path.write_text('{"rows": 10, "columns": 8}\n', encoding="utf-8")

    report, markdown = module.build_model_data_report(
        _reduced_request(), evidence_root=tmp_path
    )

    assert report["report_id"].startswith("model_data_")
    assert report["evidence"]["files"][0]["path"] == "mapping_payload.json"
    assert report["evidence"]["files"][0]["bytes"] == payload_path.stat().st_size
    assert "Report sui dati arrivati al modello" in markdown
    assert "10,000 rows" in markdown
    assert "Possibile miglioramento" in markdown
    assert module.validate_model_data_report(report)["report_id"] == report["report_id"]


@pytest.mark.parametrize("language", ["it", "en", "fr", "de", "es"])
def test_full_document_is_valid_without_improvement_section(
    tmp_path: Path, language: str
) -> None:
    module = _load_module()
    improvement_headings = {
        "it": "Possibile miglioramento",
        "en": "Potential improvement",
        "fr": "Amélioration possible",
        "de": "Mögliche Verbesserung",
        "es": "Posible mejora",
    }
    full_context_labels = {
        "it": "Contesto completo necessario",
        "en": "Full context required",
        "fr": "Contexte complet nécessaire",
        "de": "Vollständiger Kontext erforderlich",
        "es": "Contexto completo necesario",
    }

    report, markdown = module.build_model_data_report(
        _full_document_request(language), evidence_root=tmp_path
    )

    assert report["phases"][0]["outcome"] == "full_context_required"
    assert report["improvement_assessment"]["status"] == "not_assessed"
    assert improvement_headings[language] not in markdown
    assert full_context_labels[language] in markdown


def test_chatgpt_is_an_explicit_runtime_profile(tmp_path: Path) -> None:
    module = _load_module()
    request = _full_document_request()
    request["runtime_profile"] = "openai-chatgpt"

    report, _ = module.build_model_data_report(request, evidence_root=tmp_path)

    assert report["runtime_profile"] == "openai-chatgpt"


def test_candidate_without_run_evidence_is_rejected(tmp_path: Path) -> None:
    module = _load_module()
    request = _full_document_request()
    request["improvement_assessment"] = {
        "status": "candidate",
        "candidates": [
            {
                "candidate_id": "unsupported",
                "phase_ids": ["semantic-review"],
                "change": "Remove pages.",
                "evidence": [],
                "estimated_reduction": [],
                "quality_safeguard": "Review representative cases.",
                "status": "candidate_needs_validation",
                "validation_evidence": [],
            }
        ],
    }

    with pytest.raises(module.ModelDataReportError, match="evidence must not be empty"):
        module.build_model_data_report(request, evidence_root=tmp_path)


def test_exact_payload_basis_requires_existing_regular_file(tmp_path: Path) -> None:
    module = _load_module()

    with pytest.raises(module.ModelDataReportError, match="regular evidence file"):
        module.build_model_data_report(_reduced_request(), evidence_root=tmp_path)


def test_report_validation_rejects_tampered_evidence_receipt(tmp_path: Path) -> None:
    module = _load_module()
    (tmp_path / "mapping_payload.json").write_text("{}\n", encoding="utf-8")
    report, _ = module.build_model_data_report(
        _reduced_request(), evidence_root=tmp_path
    )
    tampered = copy.deepcopy(report)
    tampered["evidence"]["files"][0]["bytes"] += 1

    with pytest.raises(module.ModelDataReportError, match="receipt hash"):
        module.validate_model_data_report(tampered)


def test_report_validation_rejects_changed_payload_file(tmp_path: Path) -> None:
    module = _load_module()
    payload_path = tmp_path / "mapping_payload.json"
    payload_path.write_text("{}\n", encoding="utf-8")
    report, _ = module.build_model_data_report(
        _reduced_request(), evidence_root=tmp_path
    )
    payload_path.write_text('{"changed": true}\n', encoding="utf-8")

    with pytest.raises(module.ModelDataReportError, match="evidence file changed"):
        module.validate_model_data_report(report, evidence_root=tmp_path)


def test_cli_writes_json_and_markdown_idempotently(tmp_path: Path) -> None:
    payload_path = tmp_path / "mapping_payload.json"
    payload_path.write_text("{}\n", encoding="utf-8")
    request_path = tmp_path / "model_data_report_input.json"
    request_path.write_text(
        json.dumps(_reduced_request(), ensure_ascii=False), encoding="utf-8"
    )
    command = [
        sys.executable,
        str(SCRIPT_PATH),
        "build",
        "--input",
        str(request_path),
        "--evidence-root",
        str(tmp_path),
        "--output-dir",
        str(tmp_path),
    ]

    first = subprocess.run(command, check=False, capture_output=True, text=True)
    second = subprocess.run(command, check=False, capture_output=True, text=True)

    assert first.returncode == 0, first.stderr
    assert second.returncode == 0, second.stderr
    report_path = tmp_path / "model_data_report.json"
    report = json.loads(report_path.read_text(encoding="utf-8"))
    assert report["workflow_id"] == "variance-analysis"
    assert (tmp_path / "model_data_report.md").is_file()


def test_router_requires_report_for_every_substantive_run() -> None:
    router = ROUTER_PATH.read_text(encoding="utf-8")
    contract = CONTRACT_PATH.read_text(encoding="utf-8")

    assert "After every substantive Vera run" in router
    assert "model_data_report.json" in router
    assert "complete document or population" in router.lower()
    assert "after every substantive Vera run" in contract
    assert '"runtime_profile": "openai-chatgpt"' in contract
    assert "candidate_needs_validation" in contract
