"""Export a scoped case review and an evidence-bounded local model-data report."""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path
from typing import Any

from fusione_case import CaseStore, now, plain_path
from fusione_dossier import write_workpapers
from fusione_model import CaseError

__all__ = ["export_report"]


def _cell(value: Any) -> str:
    return str(value).replace("|", "\\|").replace("\n", " ").replace("\r", " ")


def _report_builder() -> Any:
    root = Path(__file__).resolve().parents[1]
    candidates = (
        root.parent / "vera" / "scripts" / "model_data_report.py",
        root.parents[1] / "scripts" / "model_data_report.py",
        root / "vendor" / "modules" / "model_data_report.py",
    )
    for path in candidates:
        if path.is_file():
            spec = importlib.util.spec_from_file_location(
                "fusione_model_data_report", path
            )
            if spec is None or spec.loader is None:
                continue
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
            return module.build_model_data_report
    raise CaseError("The canonical Vera model-data report helper is unavailable.")


def export_report(
    store: CaseStore, destination: Path, *, runtime_profile: str = "openai-codex"
) -> dict[str, str]:
    """Write a fresh review directory without overwriting a prior report."""
    builder = _report_builder()
    report = store.report()
    destination = destination.expanduser().absolute()
    plain_path(destination.parent, directory=True)
    destination.mkdir(mode=0o700)
    case_path = destination / "case-report.json"
    case_path.write_text(
        json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    lines = [
        "# Fusione guidata — fascicolo di revisione",
        "",
        (
            "Synthetic demonstration."
            if report["synthetic"]
            else "Draft for professional review."
        ),
        "",
        report["scope"],
        "",
        "| Object | Type | Version | Work status | Review | Open issues |",
        "|---|---|---:|---|---|---|",
    ]
    for item in report["records"]:
        record, status = item["record"], item["status"]
        values = [
            record["id"],
            record["kind"],
            record["version"],
            record["work_status"],
            status["review_state"],
            "; ".join(status["issues"]),
        ]
        lines.append("| " + " | ".join(_cell(value) for value in values) + " |")
    lines.extend(
        [
            "",
            "The JSON report preserves every accessible revision, exact evidence references, approval content and recorded change impacts. Approvals cover their named scope and version only.",
            "",
            "Local actor and company checks do not authenticate identities, encrypt files or restrict direct filesystem access. P1 workpapers execute only their declared calculations and calendar conventions. They do not authorize legal execution, signatures or filings.",
            "",
            "## What data reaches the model",
            "",
            "Case identities, archive identities and receipt paths, ownership, selected evidence, valuations, balances, shareholder allocations, calendar dates, fiscal registers, source/rule content, drafts and approvals may be read by the selected Claude or Cowork runtime. Nothing is automatically anonymized. The helper uses local files and makes no model API or network calls; this does not imply local-only model processing. See model_data_report.md for what can actually be established for this export.",
        ]
    )
    markdown_path = destination / "case-report.md"
    markdown_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    synthetic = report["synthetic"]
    measurement = {
        "unit": "items",
        "quantity": len(report["records"]),
        "label": "Accessible case records",
        "basis": "measured",
    }
    request = {
        "schema_version": 1,
        "workflow_id": "fusione-guidata",
        "run_id": report["operation_id"],
        "runtime_profile": runtime_profile,
        "language": "en",
        "created_at": now(),
        "professional_purpose": "Review versioned merger-case evidence, P1 exchange and accounting workpapers, event calendars, scoped decisions and change dependencies.",
        "phases": [
            {
                "phase_id": "case-review",
                "purpose": "Export the records accessible to the selected actor.",
                "outcome": "no_case_data" if synthetic else "not_measurable",
                "evidence_basis": "workflow_receipt" if synthetic else "not_measurable",
                "source_extent": [measurement],
                "locally_processed": [measurement],
                "model_visible": [],
                "remained_local": [],
                "reason": (
                    "All fixtures are explicitly synthetic; no client material is used."
                    if synthetic
                    else "The export proves local processing, but cannot observe which records or files the host placed in model context. The orchestrator must record additional observed phases without claiming provider telemetry."
                ),
                "evidence_files": ["case-report.json"],
            }
        ],
        "improvement_assessment": {"status": "not_assessed", "candidates": []},
    }
    model_report, model_markdown = builder(request, evidence_root=destination)
    (destination / "model_data_report.json").write_text(
        json.dumps(model_report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    (destination / "model_data_report.md").write_text(model_markdown, encoding="utf-8")
    workpapers = write_workpapers(report, destination)
    return {
        **workpapers,
        "case_report": str(markdown_path),
        "case_json": str(case_path),
        "model_data_report": str(destination / "model_data_report.md"),
        "server_receipt": "not_requested",
    }
