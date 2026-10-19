"""Export the scoped merger review and professional workpapers."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from fusione_case import CaseStore, plain_path
from fusione_dossier import write_workpapers

__all__ = ["export_report"]


def _cell(value: Any) -> str:
    return str(value).replace("|", "\\|").replace("\n", " ").replace("\r", " ")


def export_report(
    store: CaseStore, destination: Path, *, runtime_profile: str = "openai-codex"
) -> dict[str, str]:
    """Write a fresh review directory without overwriting a prior report."""
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
            "Case identities, archive identities and receipt paths, ownership, selected evidence, valuations, balances, shareholder allocations, calendar dates, fiscal registers, source/rule content, drafts and approvals may be read by the selected Codex or Cowork runtime. Nothing is automatically anonymized. The helper uses local files and makes no model API or network calls; this does not imply local-only model processing.",
        ]
    )
    markdown_path = destination / "case-report.md"
    markdown_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    workpapers = write_workpapers(report, destination)
    return {
        **workpapers,
        "case_report": str(markdown_path),
        "case_json": str(case_path),
        "server_receipt": "not_requested",
    }
