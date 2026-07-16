from __future__ import annotations

import json
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Sequence

__all__ = [
    "ReviewSessionResult",
    "RunIntakeResult",
    "write_review_session_artifacts",
    "write_run_intake",
]

SCHEMA_VERSION = "1.0"
PLUGIN_NAME = "check-entries"
WORKFLOW_NAME = "check-entries"
MAX_RESULT_ITEMS = 1500
MAX_PDF_ITEMS = 500


@dataclass(frozen=True)
class RunIntakeResult:
    """Run intake artifact written once inputs and recipe are known."""

    run_id: str
    path: Path


@dataclass(frozen=True)
class ReviewSessionResult:
    """Review-session artifacts for a Check Entries run."""

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


def _run_id(journal: Path) -> str:
    timestamp = re.sub(r"[^0-9]", "", _utc_now())
    return f"{PLUGIN_NAME}-{_safe_slug(journal.stem)}-{timestamp}"


def _write_json(path: Path, payload: dict[str, Any]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
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


def _as_output_ref(path: Path | None, output_dir: Path) -> str | None:
    if path is None:
        return None
    try:
        return path.relative_to(output_dir).as_posix()
    except ValueError:
        return path.as_posix()


def _clean_text(value: Any) -> str:
    return str(value or "").strip()


def _status_counts(rows: Sequence[dict[str, Any]]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for row in rows:
        status = str(row.get("status") or "unknown")
        counts[status] = counts.get(status, 0) + 1
    return dict(sorted(counts.items(), key=lambda item: item[0]))


def _missing_mapping(mapping: dict[str, Any]) -> list[str]:
    missing = []
    if not mapping.get("movement_number"):
        missing.append("movement_number")
    if not (
        mapping.get("amount")
        or (mapping.get("debit_amount") and mapping.get("credit_amount"))
    ):
        missing.append("amount_or_debit_credit")
    return missing


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
        {"field": "title", "label": "Entry"},
        {"field": "recommended_action", "label": "Suggested action"},
        {"field": "source_path", "label": "Source"},
        {"field": "output_path", "label": "Output"},
        {"field": "status", "label": "Status"},
    ]


def _result_item_type(status: str) -> str:
    if status == "ok":
        return "supported_entry"
    if status == "missing_support":
        return "missing_support"
    if status == "mismatch":
        return "mismatch"
    if status == "manual_review":
        return "manual_review"
    return "entry_check_result"


def _recommended_action(status: str) -> str:
    if status == "ok":
        return "accept"
    if status == "missing_support":
        return "request_more_documents"
    if status in {"mismatch", "manual_review"}:
        return "mark_unclear"
    return "mark_unclear"


def _entry_title(row: dict[str, Any], index: int) -> str:
    movement = str(row.get("movement_number") or f"row {index}")
    amount = row.get("amount_abs")
    date = row.get("entry_date")
    parts = [movement]
    if amount not in (None, ""):
        parts.append(str(amount))
    if date:
        parts.append(str(date))
    return " | ".join(parts)


def _requested_support_document(row: dict[str, Any]) -> str:
    movement = _clean_text(row.get("movement_number"))
    if movement:
        return f"Supporting PDF for movement {movement}"
    return "Supporting PDF for unmatched journal entry"


def _entry_items(rows: Sequence[dict[str, Any]]) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    for index, row in enumerate(rows[:MAX_RESULT_ITEMS], start=1):
        status = str(row.get("status") or "unknown")
        data = dict(row)
        data["target_artifact"] = "check_results.csv"
        data["target_id_field"] = "source_row"
        data["target_record_id"] = str(row.get("source_row") or index)
        data["target_field"] = "review_notes"
        data["edit_hint"] = (
            "Editing this row updates review_notes in check_results.csv for the "
            "matching source_row."
        )
        evidence = [
            {
                "kind": "deterministic_checks",
                "checks_run": row.get("checks_run"),
                "mismatches": row.get("mismatches"),
                "review_notes": row.get("review_notes"),
                "matched_pdf": row.get("matched_pdf"),
            }
        ]
        if row.get("amount_found") not in (None, ""):
            evidence.append({"kind": "amount_found", "value": row.get("amount_found")})
        if row.get("date_found"):
            evidence.append({"kind": "date_found", "value": row.get("date_found")})
        if row.get("beneficiary_found"):
            evidence.append(
                {"kind": "beneficiary_found", "value": row.get("beneficiary_found")}
            )
        if status == "missing_support":
            requested_document = _requested_support_document(row)
            data["requested_document"] = requested_document
            data["reason"] = "No supporting PDF matched the movement number."
            evidence.append(
                {
                    "kind": "missing_document_request",
                    "requested_document": requested_document,
                    "reason": data["reason"],
                    "status": "needs_evidence",
                }
            )
        items.append(
            _base_item(
                f"entry-{index}",
                _result_item_type(status),
                _entry_title(row, index),
                source_path=str(row.get("source_file") or ""),
                output_path="check_results.csv",
                allowed_actions=(
                    "accept",
                    "edit",
                    "mark_unclear",
                    "request_more_documents",
                    "skip",
                ),
                recommended_action=_recommended_action(status),
                evidence=evidence,
                data=data,
            )
        )
    if len(rows) > MAX_RESULT_ITEMS:
        items.append(
            _base_item(
                "check-results-truncated",
                "review_artifact",
                "Check results truncated in widget",
                output_path="check_results.csv",
                allowed_actions=("accept", "mark_unclear", "skip"),
                recommended_action="mark_unclear",
                data={
                    "shown_count": MAX_RESULT_ITEMS,
                    "total_count": len(rows),
                    "full_results": "check_results.csv",
                },
            )
        )
    return items


def _pdf_items(pdf_inventory: Sequence[dict[str, Any]]) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    for index, row in enumerate(pdf_inventory[:MAX_PDF_ITEMS], start=1):
        extractable = bool(row.get("extractable_text"))
        error = row.get("error")
        items.append(
            _base_item(
                f"pdf-{index}",
                "pdf_inventory",
                str(row.get("filename") or f"PDF {index}"),
                source_path=str(row.get("path") or ""),
                output_path="pdf_inventory.json",
                allowed_actions=("accept", "edit", "mark_unclear", "skip"),
                recommended_action=(
                    "mark_unclear" if error or not extractable else "accept"
                ),
                evidence=[
                    {
                        "kind": "pdf_text_extraction",
                        "extractable_text": extractable,
                        "text_chars": row.get("text_chars"),
                        "error": error,
                    }
                ],
                data=dict(row),
            )
        )
    if len(pdf_inventory) > MAX_PDF_ITEMS:
        items.append(
            _base_item(
                "pdf-inventory-truncated",
                "review_artifact",
                "PDF inventory truncated in widget",
                output_path="pdf_inventory.json",
                allowed_actions=("accept", "mark_unclear", "skip"),
                recommended_action="mark_unclear",
                data={
                    "shown_count": MAX_PDF_ITEMS,
                    "total_count": len(pdf_inventory),
                    "full_inventory": "pdf_inventory.json",
                },
            )
        )
    return items


def _mapping_items(mapping: dict[str, Any]) -> list[dict[str, Any]]:
    missing = _missing_mapping(mapping)
    if not missing:
        return []
    return [
        _base_item(
            "mapping-required-fields",
            "mapping_issue",
            "Missing or weak required journal mapping",
            output_path="check_audit.json",
            allowed_actions=("edit", "mark_unclear", "skip"),
            recommended_action="mark_unclear",
            data={"mapping": mapping, "missing": missing},
        )
    ]


def _artifact_items(output_dir: Path) -> list[dict[str, Any]]:
    artifacts = [
        (
            "normalized-entries",
            "review_artifact",
            "Normalized entries",
            "normalized_entries.csv",
        ),
        (
            "check-results-csv",
            "review_artifact",
            "Check results CSV",
            "check_results.csv",
        ),
        (
            "check-results-xlsx",
            "review_artifact",
            "Check results workbook",
            "check_results.xlsx",
        ),
        (
            "pdf-inventory-json",
            "review_artifact",
            "PDF inventory",
            "pdf_inventory.json",
        ),
        ("check-audit-json", "review_artifact", "Check audit JSON", "check_audit.json"),
        ("review-notes-md", "review_artifact", "Review notes", "review_notes.md"),
    ]
    items: list[dict[str, Any]] = []
    for item_id, item_type, title, relative_path in artifacts:
        path = output_dir / relative_path
        items.append(
            _base_item(
                item_id,
                item_type,
                title,
                output_path=relative_path,
                allowed_actions=("accept", "edit", "mark_unclear", "skip"),
                recommended_action="accept" if path.exists() else "mark_unclear",
                data={
                    "path": relative_path,
                    "exists": path.exists(),
                    "size_bytes": path.stat().st_size if path.exists() else 0,
                },
            )
        )
    return items


CHECK_RESULTS_WORKBOOK_SHEET = "Sheet1"
CHECK_RESULTS_WORKBOOK_COLUMNS = [
    "movement_number",
    "entry_date",
    "description",
    "beneficiary_expected",
    "amount_signed",
    "amount_abs",
    "source_file",
    "source_row",
    "status",
    "matched_pdf",
    "checks_run",
    "mismatches",
    "review_notes",
    "amount_found",
    "date_found",
    "beneficiary_found",
]


def _column_letters(index: int) -> str:
    letters = ""
    while index > 0:
        index, remainder = divmod(index - 1, 26)
        letters = chr(65 + remainder) + letters
    return letters


def _add_cell_check(cells: dict[str, str], reference: str, value: object) -> None:
    text = _clean_text(value)
    if text:
        cells[reference] = text


def _check_results_workbook_required_cells(
    result_rows: Sequence[dict[str, Any]],
) -> dict[str, dict[str, str]]:
    cells: dict[str, str] = {}
    fields = [
        "movement_number",
        "source_row",
        "status",
        "matched_pdf",
        "checks_run",
    ]
    for field in fields:
        if field not in CHECK_RESULTS_WORKBOOK_COLUMNS:
            continue
        column = _column_letters(CHECK_RESULTS_WORKBOOK_COLUMNS.index(field) + 1)
        cells[f"{column}1"] = field
    if result_rows and isinstance(result_rows[0], dict):
        first_row = result_rows[0]
        for field in fields:
            column = _column_letters(CHECK_RESULTS_WORKBOOK_COLUMNS.index(field) + 1)
            _add_cell_check(cells, f"{column}2", first_row.get(field))
    return {CHECK_RESULTS_WORKBOOK_SHEET: cells}


def _output_records(
    output_dir: Path,
    audit: dict[str, Any],
    result_rows: Sequence[dict[str, Any]],
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
        if relative == "check_results.csv":
            output["row_count"] = int(audit.get("result_row_count", 0))
            output["required_columns"] = [
                "movement_number",
                "status",
                "matched_pdf",
            ]
        elif relative == "check_results.xlsx":
            output["source_row_count"] = int(audit.get("result_row_count", 0))
            output["required_sheets"] = [CHECK_RESULTS_WORKBOOK_SHEET]
            output["required_sheet_headers"] = {
                CHECK_RESULTS_WORKBOOK_SHEET: [
                    "movement_number",
                    "source_row",
                    "status",
                    "matched_pdf",
                    "checks_run",
                ]
            }
            output["required_cells"] = _check_results_workbook_required_cells(
                result_rows
            )
            output["qa_checks"] = [
                "office_zip",
                "workbook_xml",
                "required_sheets",
                "required_sheet_headers",
                "required_cells",
            ]
        elif relative == "review_notes.md":
            output["required_text"] = [
                "# Check Entries Review Notes",
                "## Status Counts",
                "## Review Policy",
            ]
            output["qa_checks"] = ["nonempty_text", "required_text"]
        outputs.append(output)
    return outputs


def write_run_intake(
    output_dir: Path,
    journal: Path,
    pdf_path: Path,
    *,
    recipe_path: Path | None,
    language: str,
    document_language: str,
    amount_tolerance: float,
    date_window_days: int,
    mapping: dict[str, Any],
    journal_row_count: int,
    pdf_count: int,
) -> RunIntakeResult:
    """Write the run intake contract for review and replay."""

    run_id = _run_id(journal)
    local_files_read = [journal.as_posix(), pdf_path.as_posix()]
    if recipe_path is not None:
        local_files_read.append(recipe_path.as_posix())
    payload = {
        "schema_version": SCHEMA_VERSION,
        "plugin": PLUGIN_NAME,
        "workflow": WORKFLOW_NAME,
        "run_id": run_id,
        "created_at": _utc_now(),
        "language": language,
        "document_language": document_language,
        "input_paths": [journal.as_posix(), pdf_path.as_posix()],
        "output_dir": output_dir.as_posix(),
        "inferred_task": "journal_entry_support_check",
        "assumptions": {
            "amount_tolerance": amount_tolerance,
            "date_window_days": date_window_days,
            "currency": "EUR",
            "mapping": mapping,
            "journal_row_count": journal_row_count,
            "pdf_count": pdf_count,
            "recipe_path": recipe_path.as_posix() if recipe_path else None,
        },
        "unresolved_questions": [
            {
                "field": field,
                "question": "Confirm the journal mapping before treating the check as complete.",
            }
            for field in _missing_mapping(mapping)
        ],
        "dependency_check": {
            "status": "not_run",
            "missing_dependency_count": None,
            "notes": [
                "This review-session writer records local deterministic inputs; dependency checks are handled by plugin setup or explicit dependency scripts."
            ],
        },
        "data_posture": {
            "local_files_read": local_files_read,
            "model_excerpts_sent": [],
            "external_connectors_used": [],
            "upload_paths_used": [],
            "remote_sql_execution_used": False,
            "hosted_notebook_execution_used": False,
            "notes": [
                "Deterministic scripts read the journal, support PDFs, and optional recipe locally.",
                "No external connector, upload path, remote SQL, or hosted notebook execution is used by default.",
            ],
        },
        "status": "ready_for_review",
    }
    return RunIntakeResult(
        run_id=run_id,
        path=_write_json(output_dir / "run_intake.json", payload),
    )


def write_review_session_artifacts(
    output_dir: Path,
    journal: Path,
    pdf_path: Path,
    *,
    run_id: str,
    run_intake_path: Path,
    recipe_path: Path | None,
    language: str,
    document_language: str,
    amount_tolerance: float,
    date_window_days: int,
    mapping: dict[str, Any],
    result_rows: Sequence[dict[str, Any]],
    pdf_inventory: Sequence[dict[str, Any]],
    audit: dict[str, Any],
) -> ReviewSessionResult:
    """Write review payload, pending decisions, and final artifact index."""

    status_counts = _status_counts(result_rows)
    items: list[dict[str, Any]] = []
    items.extend(_mapping_items(mapping))
    items.extend(_entry_items(result_rows))
    items.extend(_pdf_items(pdf_inventory))
    items.extend(_artifact_items(output_dir))

    review_payload = {
        "schema_version": SCHEMA_VERSION,
        "plugin": PLUGIN_NAME,
        "workflow": WORKFLOW_NAME,
        "run_id": run_id,
        "created_at": _utc_now(),
        "source_paths": [journal.as_posix(), pdf_path.as_posix()],
        "review_type": "journal_entry_support_review",
        "items": items,
        "item_count": len(items),
        "columns": _review_columns(),
        "evidence": {
            "run_intake": _as_output_ref(run_intake_path, output_dir),
            "recipe": _as_output_ref(recipe_path, output_dir),
            "normalized_entries": "normalized_entries.csv",
            "check_results_csv": "check_results.csv",
            "check_results_xlsx": "check_results.xlsx",
            "pdf_inventory": "pdf_inventory.json",
            "check_audit": "check_audit.json",
            "review_notes": "review_notes.md",
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
            "journal_row_count": audit.get("journal_row_count", len(result_rows)),
            "pdf_count": audit.get("pdf_count", len(pdf_inventory)),
            "result_row_count": audit.get("result_row_count", len(result_rows)),
            "status_counts": status_counts,
            "ok_count": status_counts.get("ok", 0),
            "missing_support_count": status_counts.get("missing_support", 0),
            "mismatch_count": status_counts.get("mismatch", 0),
            "manual_review_count": status_counts.get("manual_review", 0),
            "pdf_text_error_count": sum(1 for row in pdf_inventory if row.get("error")),
            "unextractable_pdf_count": sum(
                1 for row in pdf_inventory if not row.get("extractable_text")
            ),
            "language": language,
            "document_language": document_language,
            "amount_tolerance": amount_tolerance,
            "date_window_days": date_window_days,
            "mapping_missing": _missing_mapping(mapping),
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
        title="Check Entries",
        validate_tool="validate_check_entries_review",
        render_tool="render_check_entries_review",
        save_tool="save_check_entries_decisions",
        apply_tool="apply_check_entries_decisions",
    )
    outputs = _output_records(output_dir, audit, result_rows)
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
                "The scripts only compare deterministic evidence; Codex must explain unresolved cases and judgment.",
                "ui_decisions.json is pending until Codex, MCP UI, or fallback review records decisions.",
            ],
            "next_actions": [
                "Review mismatch, missing_support, and manual_review rows before final delivery.",
                "Use accepted/edited decisions when writing codex_run_review.md or final chat summary.",
            ],
            "status": "written_pending_review",
        },
    )
    _append_execution_trace(
        run_intake_path,
        final_artifacts_path,
        command=["python", "plugins/check-entries/scripts/run_checks.py"],
    )

    return ReviewSessionResult(
        run_intake_path=run_intake_path,
        review_payload_path=review_payload_path,
        ui_decisions_path=ui_decisions_path,
        final_artifacts_path=final_artifacts_path,
        review_item_count=len(items),
    )
