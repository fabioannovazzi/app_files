from __future__ import annotations

import json
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Sequence

from excel_sanitization import sanitize_excel_string

__all__ = [
    "ReviewSessionResult",
    "RunIntakeResult",
    "write_review_session_artifacts",
    "write_run_intake",
]

SCHEMA_VERSION = "1.0"
PLUGIN_NAME = "journal-bank-reconciliation"
WORKFLOW_NAME = "journal-bank-reconciliation"
MAX_MATCH_ITEMS = 200
MAX_UNMATCHED_ITEMS = 500


@dataclass(frozen=True)
class RunIntakeResult:
    """Run intake artifact written before journal-bank reconciliation."""

    run_id: str
    path: Path


@dataclass(frozen=True)
class ReviewSessionResult:
    """Review-session artifacts for one journal-bank reconciliation run."""

    run_id: str
    run_intake_path: Path
    review_payload_path: Path
    ui_decisions_path: Path
    final_artifacts_path: Path
    review_item_count: int


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _safe_slug(value: str) -> str:
    slug = re.sub(r"[^a-zA-Z0-9_.-]+", "-", value).strip("-._").lower()
    return slug or "run"


def _run_id(bank_path: Path, journal_path: Path) -> str:
    timestamp = re.sub(r"[^0-9]", "", _utc_now())
    return (
        f"{PLUGIN_NAME}-{_safe_slug(bank_path.stem)}-"
        f"{_safe_slug(journal_path.stem)}-{timestamp}"
    )


def _write_json(path: Path, payload: dict[str, Any]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, default=str) + "\n",
        encoding="utf-8",
    )
    return path


def _write_review_handoff_card(
    output_dir: Path,
    *,
    run_id: str,
    title: str,
    validate_tool: str,
    render_tool: str,
    save_tool: str,
    apply_tool: str,
) -> Path:
    path = output_dir / "review_handoff.md"
    lines = [
        f"# {title} Review Handoff",
        "",
        f"- Run ID: `{run_id}`",
        "- Review payload: `review_payload.json`",
        "- Run intake: `run_intake.json`",
        "- Pending decisions: `ui_decisions.json`",
        "- Applied decisions: `applied_decisions.json`",
        "- Final artifacts: `final_artifacts.json`",
        "",
        "## Review In Codex",
        f"1. Validate the payload with `{validate_tool}`.",
        f"2. Render the review workbench with `{render_tool}`.",
        f"3. Save reviewer actions with `{save_tool}`.",
        f"4. Apply reviewer actions with `{apply_tool}`.",
        "",
        "Persistent save/apply requires the MCP or local-server review surface. "
        "Static HTML fallback can copy or download decision JSON only.",
    ]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


def _review_handoff_output_record(path: Path) -> dict[str, Any]:
    return {
        "path": path.name,
        "kind": "md",
        "status": "written",
        "required_text": [
            "Review Handoff",
            "review_payload.json",
            "ui_decisions.json",
            "applied_decisions.json",
            "final_artifacts.json",
        ],
        "qa_checks": ["nonempty_text", "required_text"],
    }


def _local_output_refs(final_artifacts_path: Path) -> list[str]:
    refs = [
        "run_intake.json",
        "review_payload.json",
        "ui_decisions.json",
        "final_artifacts.json",
    ]
    payload = json.loads(final_artifacts_path.read_text(encoding="utf-8"))
    outputs = payload.get("outputs")
    if isinstance(outputs, list):
        for output in outputs:
            if not isinstance(output, dict):
                continue
            path_value = output.get("path")
            if (
                isinstance(path_value, str)
                and path_value.strip()
                and "://" not in path_value
            ):
                refs.append(path_value.strip())
    return list(dict.fromkeys(refs))


def _append_execution_trace(
    run_intake_path: Path,
    final_artifacts_path: Path,
    *,
    command: Sequence[str],
) -> None:
    payload = json.loads(run_intake_path.read_text(encoding="utf-8"))
    data_posture = payload.get("data_posture")
    local_files = (
        data_posture.get("local_files_read") if isinstance(data_posture, dict) else None
    )
    inputs = (
        local_files if isinstance(local_files, list) else payload.get("input_paths", [])
    )
    payload["execution_trace"] = [
        {
            "step_id": f"{WORKFLOW_NAME}_review_session",
            "kind": "deterministic_review_session",
            "status": "passed",
            "execution_location": "local_codex_workspace",
            "command": list(command),
            "inputs": [str(entry) for entry in inputs if entry],
            "outputs": _local_output_refs(final_artifacts_path),
        }
    ]
    _write_json(run_intake_path, payload)


def _as_output_ref(path: str | Path | None, output_dir: Path) -> str | None:
    if path is None:
        return None
    candidate = Path(path)
    try:
        return candidate.relative_to(output_dir).as_posix()
    except ValueError:
        return candidate.as_posix()


def _clean_text(value: Any) -> str:
    return " ".join(str(value or "").strip().split())


def _rows(frame: Any) -> list[dict[str, Any]]:
    if frame is None:
        return []
    to_dicts = getattr(frame, "to_dicts", None)
    if callable(to_dicts):
        return [row for row in to_dicts() if isinstance(row, dict)]
    if isinstance(frame, list):
        return [row for row in frame if isinstance(row, dict)]
    return []


def _base_item(
    item_id: str,
    item_type: str,
    title: str,
    *,
    allowed_actions: Sequence[str],
    recommended_action: str,
    source_path: str | None = None,
    output_path: str | None = None,
    evidence: Sequence[dict[str, Any]] = (),
    data: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return {
        "id": item_id,
        "item_type": item_type,
        "title": title,
        "source_path": source_path,
        "output_path": output_path,
        "allowed_actions": list(allowed_actions),
        "recommended_action": recommended_action,
        "evidence": list(evidence),
        "data": data or {},
        "status": "needs_review",
    }


def _review_columns() -> list[dict[str, str]]:
    return [
        {"field": "item_type", "label": "Type"},
        {"field": "title", "label": "Movement"},
        {"field": "recommended_action", "label": "Suggested action"},
        {"field": "source_path", "label": "Source"},
        {"field": "output_path", "label": "Output"},
        {"field": "status", "label": "Status"},
    ]


def _transaction_title(row: dict[str, Any], fallback: str) -> str:
    parts = [
        _clean_text(row.get("transaction_date")),
        _clean_text(row.get("amount_signed") or row.get("amount_abs")),
        _clean_text(row.get("reference") or row.get("movement_number")),
        _clean_text(row.get("beneficiary") or row.get("description")),
    ]
    return " | ".join(part for part in parts if part) or fallback


def _match_title(row: dict[str, Any], index: int) -> str:
    parts = [
        _clean_text(row.get("bank_amount")),
        _clean_text(row.get("shared_references")),
        _clean_text(row.get("stage")),
    ]
    return " | ".join(part for part in parts if part) or f"Matched pair {index}"


def _requested_reconciliation_evidence(
    row: dict[str, Any], side: str
) -> tuple[str, str]:
    reference = _clean_text(row.get("reference") or row.get("movement_number"))
    amount = _clean_text(row.get("amount_signed") or row.get("amount_abs"))
    descriptor = reference or amount or "unmatched transaction"
    if side == "bank":
        return (
            f"Journal or ledger support for bank transaction {descriptor}",
            "Bank transaction has no deterministic journal match.",
        )
    return (
        f"Bank statement or payment evidence for journal transaction {descriptor}",
        "Journal transaction has no deterministic bank match.",
    )


def _unmatched_items(
    rows: Sequence[dict[str, Any]],
    *,
    side: str,
    output_path: str,
) -> list[dict[str, Any]]:
    item_type = "unmatched_bank" if side == "bank" else "unmatched_journal"
    source_label = "Bank" if side == "bank" else "Journal"
    items: list[dict[str, Any]] = []
    for index, row in enumerate(rows[:MAX_UNMATCHED_ITEMS], start=1):
        requested_document, reason = _requested_reconciliation_evidence(row, side)
        data = dict(row)
        data["requested_document"] = requested_document
        data["reason"] = reason
        items.append(
            _base_item(
                f"{item_type}-{index}",
                item_type,
                _transaction_title(row, f"{source_label} row {index}"),
                source_path="; ".join(
                    part
                    for part in (
                        _clean_text(row.get("source_file")),
                        (
                            f"row {_clean_text(row.get('source_row'))}"
                            if _clean_text(row.get("source_row"))
                            else ""
                        ),
                    )
                    if part
                )
                or None,
                output_path=output_path,
                allowed_actions=(
                    "accept",
                    "edit",
                    "mark_unclear",
                    "request_more_documents",
                    "skip",
                ),
                recommended_action="request_more_documents",
                evidence=[
                    {
                        "kind": "unmatched_transaction",
                        "side": side,
                        "transaction_id": row.get("transaction_id"),
                        "amount_abs": row.get("amount_abs"),
                        "reference": row.get("reference"),
                        "movement_number": row.get("movement_number"),
                    },
                    {
                        "kind": "missing_reconciliation_evidence",
                        "side": side,
                        "requested_document": requested_document,
                        "reason": reason,
                        "status": "needs_evidence",
                    },
                ],
                data=data,
            )
        )
    if len(rows) > MAX_UNMATCHED_ITEMS:
        items.append(
            _base_item(
                f"{item_type}-truncated",
                "review_artifact",
                f"{source_label} unmatched rows truncated in widget",
                output_path=output_path,
                allowed_actions=("accept", "mark_unclear", "skip"),
                recommended_action="mark_unclear",
                data={
                    "shown_count": MAX_UNMATCHED_ITEMS,
                    "total_count": len(rows),
                    "full_results": output_path,
                },
            )
        )
    return items


def _match_items(rows: Sequence[dict[str, Any]]) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    for index, row in enumerate(rows[:MAX_MATCH_ITEMS], start=1):
        data = dict(row)
        data["target_artifact"] = "reconciliation_matches.csv"
        data["target_id_field"] = "bank_transaction_id"
        data["target_record_id"] = str(row.get("bank_transaction_id") or "")
        data["target_field"] = "review_note"
        data["edit_hint"] = (
            "Editing this matched pair updates review_note in "
            "reconciliation_matches.csv for the matching bank_transaction_id."
        )
        items.append(
            _base_item(
                f"matched-pair-{index}",
                "matched_pair",
                _match_title(row, index),
                output_path="reconciliation_matches.csv",
                allowed_actions=("accept", "edit", "mark_unclear", "skip"),
                recommended_action="accept",
                evidence=[
                    {
                        "kind": "deterministic_match",
                        "stage": row.get("stage"),
                        "amount_delta": row.get("amount_delta"),
                        "date_diff_days": row.get("date_diff_days"),
                        "shared_references": row.get("shared_references"),
                    }
                ],
                data=data,
            )
        )
    return items


def _artifact_items(audit: dict[str, Any], output_dir: Path) -> list[dict[str, Any]]:
    outputs = audit.get("outputs") if isinstance(audit.get("outputs"), dict) else {}
    labels = {
        "normalized_bank_csv": ("review_artifact", "Normalized bank CSV"),
        "normalized_journal_csv": ("review_artifact", "Normalized journal CSV"),
        "reconciliation_matches_csv": ("review_artifact", "Reconciliation matches CSV"),
        "unmatched_bank_csv": ("review_artifact", "Unmatched bank CSV"),
        "unmatched_journal_csv": ("review_artifact", "Unmatched journal CSV"),
        "workbook_xlsx": ("workpaper_artifact", "Journal-bank reconciliation workbook"),
        "audit_json": ("review_artifact", "Reconciliation audit JSON"),
        "review_notes_md": ("review_artifact", "Review notes"),
    }
    items: list[dict[str, Any]] = []
    for index, (field, (item_type, title)) in enumerate(labels.items(), start=1):
        path_value = outputs.get(field)
        if not path_value:
            continue
        path_ref = _as_output_ref(path_value, output_dir)
        exists = Path(path_value).exists()
        items.append(
            _base_item(
                f"artifact-{index}",
                item_type,
                title,
                output_path=path_ref,
                allowed_actions=("accept", "edit", "mark_unclear", "skip"),
                recommended_action="accept" if exists else "mark_unclear",
                evidence=[
                    {
                        "kind": "artifact_status",
                        "field": field,
                        "path": path_ref,
                        "exists": exists,
                    }
                ],
                data={"field": field, "path": path_ref, "exists": exists},
            )
        )
    return items


MATCH_WORKBOOK_COLUMNS = [
    "status",
    "stage",
    "bank_transaction_id",
    "journal_transaction_id",
    "bank_date",
    "journal_date",
    "date_diff_days",
    "bank_amount",
    "journal_amount",
    "amount_delta",
    "bank_description",
    "journal_description",
    "shared_references",
    "review_note",
]
TRANSACTION_WORKBOOK_COLUMNS = [
    "side",
    "transaction_id",
    "transaction_date",
    "amount_signed",
    "amount_abs",
    "description",
    "beneficiary",
    "reference",
    "movement_number",
    "account",
    "source_file",
    "source_row",
]
NON_MOVEMENT_WORKBOOK_COLUMNS = [
    "side",
    "source_file",
    "source_row",
    "classification",
    "reason",
    "transaction_date",
    "amount_signed",
    "amount_abs",
    "description",
]
WORKBOOK_REQUIRED_HEADERS = {
    "matches": [
        "status",
        "stage",
        "bank_transaction_id",
        "journal_transaction_id",
        "amount_delta",
        "shared_references",
    ],
    "unmatched_bank": [
        "side",
        "transaction_id",
        "transaction_date",
        "amount_abs",
        "reference",
    ],
    "unmatched_journal": [
        "side",
        "transaction_id",
        "transaction_date",
        "amount_abs",
        "reference",
    ],
    "bank_pdf_non_movements": [
        "source_file",
        "source_row",
        "classification",
        "description",
        "amount_abs",
    ],
}


def _column_letters(index: int) -> str:
    letters = ""
    while index > 0:
        index, remainder = divmod(index - 1, 26)
        letters = chr(65 + remainder) + letters
    return letters


def _cell_reference(columns: Sequence[str], field: str, row: int) -> str:
    return f"{_column_letters(list(columns).index(field) + 1)}{row}"


def _add_cell_check(cells: dict[str, str], reference: str, value: object) -> None:
    text = sanitize_excel_string(_clean_text(value))
    if text:
        cells[reference] = text


def _required_sheet_cells(
    *,
    columns: Sequence[str],
    fields: Sequence[str],
    first_row: dict[str, Any] | None,
) -> dict[str, str]:
    cells: dict[str, str] = {}
    for field in fields:
        if field not in columns:
            continue
        cells[_cell_reference(columns, field, 1)] = field
        if first_row:
            _add_cell_check(
                cells, _cell_reference(columns, field, 2), first_row.get(field)
            )
    return cells


def _workbook_required_cells(
    match_rows: Sequence[dict[str, Any]],
    unmatched_bank_rows: Sequence[dict[str, Any]],
    unmatched_journal_rows: Sequence[dict[str, Any]],
    bank_pdf_non_movement_rows: Sequence[dict[str, Any]],
) -> dict[str, dict[str, str]]:
    return {
        "matches": _required_sheet_cells(
            columns=MATCH_WORKBOOK_COLUMNS,
            fields=[
                "status",
                "stage",
                "bank_transaction_id",
                "journal_transaction_id",
                "shared_references",
            ],
            first_row=match_rows[0] if match_rows else None,
        ),
        "unmatched_bank": _required_sheet_cells(
            columns=TRANSACTION_WORKBOOK_COLUMNS,
            fields=["side", "transaction_id", "transaction_date", "reference"],
            first_row=unmatched_bank_rows[0] if unmatched_bank_rows else None,
        ),
        "unmatched_journal": _required_sheet_cells(
            columns=TRANSACTION_WORKBOOK_COLUMNS,
            fields=["side", "transaction_id", "transaction_date", "reference"],
            first_row=unmatched_journal_rows[0] if unmatched_journal_rows else None,
        ),
        "bank_pdf_non_movements": _required_sheet_cells(
            columns=NON_MOVEMENT_WORKBOOK_COLUMNS,
            fields=[
                "source_file",
                "source_row",
                "classification",
                "description",
                "amount_abs",
            ],
            first_row=(
                bank_pdf_non_movement_rows[0] if bank_pdf_non_movement_rows else None
            ),
        ),
    }


def _output_records(
    output_dir: Path,
    audit: dict[str, Any],
    *,
    match_rows: Sequence[dict[str, Any]],
    unmatched_bank_rows: Sequence[dict[str, Any]],
    unmatched_journal_rows: Sequence[dict[str, Any]],
    bank_pdf_non_movement_rows: Sequence[dict[str, Any]],
) -> list[dict[str, Any]]:
    review_files = {
        "run_intake.json",
        "review_payload.json",
        "ui_decisions.json",
        "final_artifacts.json",
    }
    outputs: list[dict[str, Any]] = []
    for path in sorted(output_dir.rglob("*")):
        if not path.is_file() or path.name in review_files:
            continue
        relative = path.relative_to(output_dir).as_posix()
        output = {
            "path": relative,
            "size_bytes": path.stat().st_size,
            "kind": path.suffix.lower().lstrip(".") or "file",
            "status": "written",
        }
        if relative == "journal_bank_reconciliation.xlsx":
            output["required_sheets"] = [
                "matches",
                "unmatched_bank",
                "unmatched_journal",
                "bank_pdf_non_movements",
            ]
            output["required_sheet_headers"] = WORKBOOK_REQUIRED_HEADERS
            output["required_cells"] = _workbook_required_cells(
                match_rows,
                unmatched_bank_rows,
                unmatched_journal_rows,
                bank_pdf_non_movement_rows,
            )
            output["source_row_counts"] = {
                "matches": int(audit.get("matched_count", 0)),
                "unmatched_bank": int(audit.get("unmatched_bank_count", 0)),
                "unmatched_journal": int(audit.get("unmatched_journal_count", 0)),
                "bank_pdf_non_movements": int(
                    audit.get("bank_pdf_non_movement_row_count", 0)
                ),
            }
            output["qa_checks"] = [
                "office_zip",
                "workbook_xml",
                "required_sheets",
                "required_sheet_headers",
                "required_cells",
            ]
        elif relative == "reconciliation_matches.csv":
            output["row_count"] = int(audit.get("matched_count", 0))
            output["required_columns"] = [
                "status",
                "bank_transaction_id",
                "journal_transaction_id",
                "amount_delta",
            ]
        elif relative == "unmatched_bank.csv":
            output["row_count"] = int(audit.get("unmatched_bank_count", 0))
            output["required_columns"] = [
                "transaction_id",
                "transaction_date",
                "amount_abs",
            ]
        elif relative == "unmatched_journal.csv":
            output["row_count"] = int(audit.get("unmatched_journal_count", 0))
            output["required_columns"] = [
                "transaction_id",
                "transaction_date",
                "amount_abs",
            ]
        elif relative == "bank_pdf_non_movement_rows.csv":
            output["row_count"] = int(audit.get("bank_pdf_non_movement_row_count", 0))
            output["required_columns"] = [
                "source_file",
                "source_row",
                "classification",
                "description",
                "amount_abs",
            ]
        elif relative == "review_notes.md":
            output["required_text"] = [
                "# Journal-Bank Reconciliation Review Notes",
                "## Stage Counts",
                "## Review Policy",
            ]
            output["qa_checks"] = ["nonempty_text", "required_text"]
        outputs.append(output)
    return outputs


def write_run_intake(
    output_dir: Path,
    *,
    bank_path: Path,
    journal_path: Path,
    recipe_path: Path | None,
    sample_path: Path | None,
    language: str,
    document_language: str,
    tolerance: float,
    date_window_days: int,
) -> RunIntakeResult:
    """Write run intake before deterministic matching."""

    run_id = _run_id(bank_path, journal_path)
    local_files_read = [bank_path.as_posix(), journal_path.as_posix()]
    if recipe_path is not None:
        local_files_read.append(recipe_path.as_posix())
    if sample_path is not None:
        local_files_read.append(sample_path.as_posix())
    payload = {
        "schema_version": SCHEMA_VERSION,
        "plugin": PLUGIN_NAME,
        "workflow": WORKFLOW_NAME,
        "run_id": run_id,
        "created_at": _utc_now(),
        "language": language,
        "input_paths": [
            bank_path.as_posix(),
            journal_path.as_posix(),
            *([sample_path.as_posix()] if sample_path else []),
        ],
        "output_dir": output_dir.as_posix(),
        "inferred_task": "journal_bank_reconciliation_review_payload",
        "assumptions": {
            "bank_path": bank_path.as_posix(),
            "journal_path": journal_path.as_posix(),
            "sample_path": sample_path.as_posix() if sample_path else None,
            "recipe_path": recipe_path.as_posix() if recipe_path else None,
            "language": language,
            "document_language": document_language,
            "currency": "EUR",
            "tolerance": tolerance,
            "date_window_days": date_window_days,
        },
        "unresolved_questions": [],
        "dependency_check": {
            "status": "not_run_by_script",
            "note": "Codex should run scripts/check_dependencies.py before helper scripts.",
        },
        "data_posture": {
            "local_files_read": local_files_read,
            "model_excerpts_sent": [],
            "external_connectors_used": [],
            "upload_paths_used": [],
            "remote_sql_execution_used": False,
            "hosted_notebook_execution_used": False,
            "notes": [
                "Matching scripts read bank, journal, optional recipe, and optional sample files locally.",
                "No external connector, upload path, remote SQL, or hosted notebook execution is used by default.",
            ],
        },
        "status": "ready_for_reconciliation_run",
    }
    return RunIntakeResult(
        run_id=run_id,
        path=_write_json(output_dir / "run_intake.json", payload),
    )


def write_review_session_artifacts(
    output_dir: Path,
    *,
    run_id: str,
    run_intake_path: Path,
    matches: Any,
    unmatched_bank: Any,
    unmatched_journal: Any,
    audit: dict[str, Any],
    bank_pdf_non_movements: Any = None,
) -> ReviewSessionResult:
    """Write review payload, pending decisions, and final artifacts."""

    match_rows = _rows(matches)
    unmatched_bank_rows = _rows(unmatched_bank)
    unmatched_journal_rows = _rows(unmatched_journal)
    bank_pdf_non_movement_rows = _rows(bank_pdf_non_movements)
    items: list[dict[str, Any]] = []
    items.extend(
        _unmatched_items(
            unmatched_bank_rows,
            side="bank",
            output_path="unmatched_bank.csv",
        )
    )
    items.extend(
        _unmatched_items(
            unmatched_journal_rows,
            side="journal",
            output_path="unmatched_journal.csv",
        )
    )
    items.extend(_match_items(match_rows))
    items.extend(_artifact_items(audit, output_dir))

    review_payload = {
        "schema_version": SCHEMA_VERSION,
        "plugin": PLUGIN_NAME,
        "workflow": WORKFLOW_NAME,
        "run_id": run_id,
        "created_at": _utc_now(),
        "language": audit.get("language", "en"),
        "source_paths": [
            audit.get("bank_path"),
            audit.get("journal_path"),
            audit.get("sample_path"),
        ],
        "review_type": "journal_bank_reconciliation_review",
        "items": items,
        "item_count": len(items),
        "columns": _review_columns(),
        "evidence": {
            "run_intake": _as_output_ref(run_intake_path, output_dir),
            "audit": "reconciliation_audit.json",
            "review_notes": "review_notes.md",
            "matches": "reconciliation_matches.csv",
            "unmatched_bank": "unmatched_bank.csv",
            "unmatched_journal": "unmatched_journal.csv",
            "bank_pdf_non_movements": "bank_pdf_non_movement_rows.csv",
            "workbook": "journal_bank_reconciliation.xlsx",
        },
        "allowed_actions": [
            "accept",
            "reject",
            "edit",
            "mark_unclear",
            "request_more_documents",
            "skip",
        ],
        "status": "ready_for_review",
        "summary": {
            "bank_row_count": audit.get("bank_row_count", len(match_rows)),
            "journal_row_count": audit.get("journal_row_count", 0),
            "matched_count": audit.get("matched_count", len(match_rows)),
            "unmatched_bank_count": audit.get(
                "unmatched_bank_count", len(unmatched_bank_rows)
            ),
            "unmatched_journal_count": audit.get(
                "unmatched_journal_count", len(unmatched_journal_rows)
            ),
            "bank_pdf_non_movement_row_count": audit.get(
                "bank_pdf_non_movement_row_count", len(bank_pdf_non_movement_rows)
            ),
            "bank_pdf_non_movement_classifications": audit.get(
                "bank_pdf_non_movement_classifications", {}
            ),
            "stage_counts": audit.get("stage_counts", {}),
            "sample_movement_count": audit.get("sample_movement_count", 0),
            "tolerance": audit.get("tolerance"),
            "date_window_days": audit.get("date_window_days"),
        },
    }
    review_payload_path = _write_json(
        output_dir / "review_payload.json",
        review_payload,
    )

    ui_decisions_path = _write_json(
        output_dir / "ui_decisions.json",
        {
            "schema_version": SCHEMA_VERSION,
            "plugin": PLUGIN_NAME,
            "workflow": WORKFLOW_NAME,
            "run_id": run_id,
            "decided_at": None,
            "decision_source": "not_collected",
            "review_payload_path": review_payload_path.name,
            "decisions": [],
            "decision_count": 0,
            "status": "pending_review",
        },
    )

    review_handoff_path = _write_review_handoff_card(
        output_dir,
        run_id=run_id,
        title="Journal-Bank Reconciliation",
        validate_tool="validate_journal_bank_review",
        render_tool="render_journal_bank_review",
        save_tool="save_journal_bank_decisions",
        apply_tool="apply_journal_bank_decisions",
    )
    outputs = _output_records(
        output_dir,
        audit,
        match_rows=match_rows,
        unmatched_bank_rows=unmatched_bank_rows,
        unmatched_journal_rows=unmatched_journal_rows,
        bank_pdf_non_movement_rows=bank_pdf_non_movement_rows,
    )
    outputs = [
        output
        for output in outputs
        if not (
            isinstance(output, dict) and output.get("path") == review_handoff_path.name
        )
    ]
    outputs.append(_review_handoff_output_record(review_handoff_path))

    final_artifacts_path = _write_json(
        output_dir / "final_artifacts.json",
        {
            "schema_version": SCHEMA_VERSION,
            "plugin": PLUGIN_NAME,
            "workflow": WORKFLOW_NAME,
            "run_id": run_id,
            "completed_at": _utc_now(),
            "outputs": outputs,
            "caveats": [
                "Deterministic matches are accepted only by the script rules; unmatched rows require explicit Codex or reviewer interpretation.",
                "The MCP review payload is bounded; use CSV/XLSX/JSON outputs as the complete evidence set.",
                "ui_decisions.json is pending until Codex, the MCP widget, or fallback review records decisions.",
            ],
            "next_actions": [
                "Call validate_journal_bank_review, then render_journal_bank_review when MCP is available.",
                "Review unmatched bank and journal rows before treating the package as complete.",
                "Do not promote ambiguous rows to matched without changing deterministic rules and rerunning.",
            ],
            "status": "written_pending_review",
        },
    )
    _append_execution_trace(
        run_intake_path,
        final_artifacts_path,
        command=[
            "python",
            "plugins/journal-bank-reconciliation/scripts/run_reconciliation.py",
        ],
    )

    return ReviewSessionResult(
        run_id=run_id,
        run_intake_path=run_intake_path,
        review_payload_path=review_payload_path,
        ui_decisions_path=ui_decisions_path,
        final_artifacts_path=final_artifacts_path,
        review_item_count=len(items),
    )
