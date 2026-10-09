"""Reuse Vera's canonical model-data report for the acquisition worker's actual boundary."""

from __future__ import annotations

import importlib.util
import os
from pathlib import Path
from typing import Any

from .contracts import AcquisitionError
from .engine import timestamp
from .storage import atomic_json

__all__ = ["write_disclosure", "vera_root"]


def vera_root() -> Path:
    component = Path(__file__).resolve().parents[2]
    candidates = (component.parent / "vera", component.parent.parent)
    for candidate in candidates:
        if (candidate / "scripts/model_data_report.py").is_file():
            return candidate
    raise AcquisitionError("vera-report-helper-unavailable")


def write_disclosure(run: Path, document_count: int) -> None:
    """Distinguish known zero worker model calls from unmeasured surrounding chat reads."""
    path = vera_root() / "scripts/model_data_report.py"
    spec = importlib.util.spec_from_file_location("vera_acquisition_data_report", path)
    if spec is None or spec.loader is None:
        raise AcquisitionError("vera-report-helper-unavailable")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    request: dict[str, Any] = {
        "schema_version": 1,
        "workflow_id": "agenzia-acquisition",
        "run_id": run.name,
        "runtime_profile": os.environ.get("VERA_ACQUISITION_HOST", "other-host"),
        "language": "it",
        "created_at": timestamp(),
        "professional_purpose": "Acquisire originali e riepiloghi del portale per il successivo riesame professionale.",
        "phases": [
            {
                "phase_id": "local-acquisition",
                "purpose": "Leggere il portale e verificare gli originali localmente.",
                "outcome": "no_case_data",
                "evidence_basis": "workflow_receipt",
                "source_extent": [],
                "locally_processed": [
                    {
                        "unit": "files",
                        "quantity": document_count,
                        "label": "originali acquisiti o riverificati",
                        "basis": "measured",
                    }
                ],
                "model_visible": [],
                "remained_local": [
                    {
                        "unit": "files",
                        "quantity": document_count,
                        "label": "originali conservati dal worker",
                        "basis": "measured",
                    }
                ],
                "reason": "Il worker non chiama modelli. Non salva password, PIN, cookie o profili browser. I riepiloghi del portale restano nei file locali.",
                "evidence_files": (
                    ["events.jsonl"] if (run / "events.jsonl").exists() else []
                ),
            },
            {
                "phase_id": "surrounding-chat",
                "purpose": "Preparazione e riesame nella conversazione Vera.",
                "outcome": "not_measurable",
                "evidence_basis": "not_measurable",
                "source_extent": [],
                "locally_processed": [],
                "model_visible": [],
                "remained_local": [],
                "reason": "Il worker non osserva i parametri, riepiloghi o documenti effettivamente letti dal modello della chat. La conversazione deve registrare separatamente le letture effettuate.",
                "evidence_files": [],
            },
        ],
        "improvement_assessment": {"status": "not_assessed", "candidates": []},
    }
    report, markdown = module.build_model_data_report(request, evidence_root=run)
    atomic_json(run / "model_data_report.json", report)
    (run / "model_data_report.md").write_text(markdown, encoding="utf-8")
    (run / "model_data_report.md").chmod(0o600)
    atomic_json(run / "model_data_worker_input.json", request)
