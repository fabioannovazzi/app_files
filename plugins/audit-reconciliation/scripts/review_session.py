from __future__ import annotations

import json
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any, Sequence

__all__ = [
    "ReviewSessionResult",
    "RunIntakeResult",
    "write_review_session_artifacts",
    "write_run_intake",
]

SCHEMA_VERSION = "1.0"
PLUGIN_NAME = "audit-reconciliation"
WORKFLOW_NAME = "audit-reconciliation"
MAX_REVIEW_ROWS = 500
MAX_CHECK_ITEMS = 100


@dataclass(frozen=True)
class RunIntakeResult:
    """Run intake artifact written before audit reconciliation review."""

    run_id: str
    path: Path


@dataclass(frozen=True)
class ReviewSessionResult:
    """Review-session artifacts for one audit reconciliation run."""

    run_id: str
    run_intake_path: Path
    review_payload_path: Path
    ui_decisions_path: Path
    review_html_path: Path
    artifact_card_path: Path
    final_artifacts_path: Path
    review_item_count: int


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _safe_slug(value: str) -> str:
    slug = re.sub(r"[^a-zA-Z0-9_.-]+", "-", value).strip("-._").lower()
    return slug or "run"


def _run_id(source_hint: str | Path | None) -> str:
    timestamp = re.sub(r"[^0-9]", "", _utc_now())
    hint = Path(str(source_hint)).stem if source_hint else WORKFLOW_NAME
    return f"{PLUGIN_NAME}-{_safe_slug(hint)}-{timestamp}"


def _write_json(path: Path, payload: dict[str, Any]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, default=str) + "\n",
        encoding="utf-8",
    )
    return path


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


def _dependency_requirements_from_assumptions(
    assumptions: dict[str, Any],
) -> list[str]:
    raw = (
        assumptions.get("dependency_requirements")
        or assumptions.get("requirements")
        or assumptions.get("requirements_files")
        or []
    )
    if isinstance(raw, str):
        files = [raw]
    elif isinstance(raw, Sequence) and not isinstance(raw, (bytes, bytearray)):
        files = [str(value) for value in raw if _clean_text(value)]
    else:
        files = []
    if not files:
        files.append("requirements.txt")
    ocr_requested = any(
        bool(assumptions.get(key))
        for key in (
            "ocr",
            "ocr_scanned",
            "pdf_ocr",
            "requires_ocr",
            "use_ocr",
        )
    )
    if ocr_requested and "requirements-ocr.txt" not in files:
        files.append("requirements-ocr.txt")
    seen: set[str] = set()
    return [name for name in files if not (name in seen or seen.add(name))]


def _dependency_check_from_environment(assumptions: dict[str, Any]) -> dict[str, Any]:
    try:
        from .check_dependencies import build_dependency_check
    except ImportError:  # pragma: no cover - direct import support
        import importlib.util
        import sys

        dependency_path = Path(__file__).resolve().parent / "check_dependencies.py"
        spec = importlib.util.spec_from_file_location(
            "mparanza_audit_reconciliation_check_dependencies",
            dependency_path,
        )
        if spec is None or spec.loader is None:
            return {
                "status": "unavailable",
                "checked_at": _utc_now(),
                "note": "Could not load scripts/check_dependencies.py.",
            }
        module = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = module
        spec.loader.exec_module(module)
        build_dependency_check = module.build_dependency_check
    try:
        requirement_files = _dependency_requirements_from_assumptions(assumptions)
        return build_dependency_check(explicit_files=requirement_files)
    except Exception as exc:  # keep run intake writable even when checking fails
        return {
            "status": "error",
            "checked_at": _utc_now(),
            "note": f"{type(exc).__name__}: {exc}",
        }


def _load_json_object(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        return {}
    return payload if isinstance(payload, dict) else {}


def _write_standalone_review_html(
    output_dir: Path,
    *,
    run_intake: dict[str, Any],
    review_payload: dict[str, Any],
    ui_decisions: dict[str, Any],
    final_artifacts: dict[str, Any] | None = None,
) -> Path:
    """Write a run-specific HTML review page with the MCP payload embedded."""

    widget_path = (
        Path(__file__).resolve().parents[1]
        / "assets"
        / "audit-reconciliation-review-widget.html"
    )
    html = widget_path.read_text(encoding="utf-8")
    payload = {
        "widget_type": "audit_reconciliation_review",
        "run_intake": run_intake,
        "review_payload": review_payload,
        "ui_decisions": ui_decisions,
        "final_artifacts": final_artifacts,
        "decision_policy": {
            "save_tool": "save_audit_reconciliation_decisions",
            "apply_tool": "apply_audit_reconciliation_decisions",
            "can_persist": False,
            "fallback": "copy_json",
        },
    }
    injection = (
        "<script>window.openai = { toolOutput: "
        f"{json.dumps(payload, ensure_ascii=False, default=str)}, "
        "widgetState: null };</script>\n  "
    )
    needle = "  <script>\n    const CONFIG = "
    if needle not in html:
        raise ValueError("audit reconciliation widget script insertion point not found")
    html = html.replace(needle, injection + needle, 1)
    path = output_dir / "review_ui.html"
    path.write_text(html, encoding="utf-8")
    return path


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


def _num(value: Any) -> float:
    if isinstance(value, Decimal):
        return float(value)
    text = _clean_text(value).replace(" ", "")
    if not text:
        return 0.0
    if "," in text and "." in text:
        text = text.replace(".", "").replace(",", ".")
    else:
        text = text.replace(",", ".")
    try:
        return float(Decimal(text))
    except (InvalidOperation, ValueError):
        return 0.0


def _source_paths_from_inventory(
    source_inventory: Sequence[dict[str, Any]] | None,
    fallback_paths: Sequence[str | Path] = (),
) -> list[str]:
    paths: list[str] = []
    for path in fallback_paths:
        text = _clean_text(path)
        if text:
            paths.append(text)
    for source in source_inventory or []:
        if not isinstance(source, dict):
            continue
        for field in (
            "path",
            "source_path",
            "source_file",
            "file_path",
            "name",
            "file_name",
        ):
            text = _clean_text(source.get(field))
            if text:
                paths.append(text)
                break
    seen: set[str] = set()
    unique: list[str] = []
    for path in paths:
        if path not in seen:
            unique.append(path)
            seen.add(path)
    return unique[:200]


def _status_counts(rows: Sequence[dict[str, Any]], field: str) -> dict[str, int]:
    counts: dict[str, int] = {}
    for row in rows:
        status = _clean_text(row.get(field)).lower() or "missing"
        counts[status] = counts.get(status, 0) + 1
    return dict(sorted(counts.items()))


def _rollforward_exception_summary(rows: Sequence[dict[str, Any]]) -> dict[str, Any]:
    """Summarize mechanical roll-forward exceptions for reviewer handoff."""

    status_counts: dict[str, int] = {}
    exceptions: list[dict[str, Any]] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        status = _clean_text(row.get("status")) or "missing"
        status_counts[status] = status_counts.get(status, 0) + 1
        if status.upper() in {"", "PASS", "OK"}:
            continue
        exceptions.append(
            {
                "account": _clean_text(row.get("account")),
                "account_name": _clean_text(row.get("account_name")),
                "status": status,
                "opening_difference": _clean_text(
                    row.get("opening_difference_journal_minus_ledger")
                ),
                "closing_difference": _clean_text(
                    row.get("closing_difference_journal_minus_ledger")
                ),
                "review_note": _clean_text(row.get("review_note")),
            }
        )
    return {
        "row_count": sum(status_counts.values()),
        "exception_count": len(exceptions),
        "status_counts": dict(sorted(status_counts.items())),
        "exceptions": exceptions[:10],
        "truncated": len(exceptions) > 10,
    }


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
        {"field": "title", "label": "Row or artifact"},
        {"field": "recommended_action", "label": "Suggested action"},
        {"field": "source_path", "label": "Source"},
        {"field": "output_path", "label": "Output"},
        {"field": "status", "label": "Status"},
    ]


def _review_item_type(row: dict[str, Any]) -> str:
    review_status = _clean_text(row.get("review_status")).upper()
    if review_status == "FAIL":
        return "review_exception"
    status = _clean_text(
        row.get("deterministic_status") or row.get("reconciliation_status")
    ).lower()
    if status == "closed":
        return "closure_evidence_review"
    if status == "probable_payment":
        return "probable_payment_review"
    if status == "needs_evidence":
        return "missing_evidence_review"
    if status == "unresolved":
        return "unresolved_item"
    return "manual_review"


def _review_action(row: dict[str, Any]) -> str:
    review_status = _clean_text(row.get("review_status")).upper()
    if review_status == "PASS":
        return "accept"
    if review_status == "FAIL":
        return "reject"
    status = _clean_text(
        row.get("deterministic_status") or row.get("reconciliation_status")
    ).lower()
    if status in {"needs_evidence", "unresolved"}:
        return "request_more_documents"
    if status == "closed":
        return "accept"
    return "mark_unclear"


def _review_title(row: dict[str, Any], index: int) -> str:
    document = (
        _clean_text(row.get("document_no"))
        or _clean_text(row.get("document_key"))
        or _clean_text(row.get("record_id"))
        or f"Review row {index}"
    )
    amount = _num(row.get("amount") or row.get("balance") or row.get("open_amount"))
    status = _clean_text(
        row.get("deterministic_status") or row.get("reconciliation_status")
    )
    amount_text = f"{amount:,.2f}" if amount else ""
    return " | ".join(part for part in (document, amount_text, status) if part)


def _review_row_items(review_rows: Sequence[dict[str, Any]]) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    sorted_rows = sorted(
        review_rows,
        key=lambda row: (
            _clean_text(row.get("review_status")).upper() == "PASS",
            -abs(
                _num(row.get("amount") or row.get("balance") or row.get("open_amount"))
            ),
            _clean_text(row.get("review_id") or row.get("record_id")),
        ),
    )[:MAX_REVIEW_ROWS]
    for index, row in enumerate(sorted_rows, start=1):
        item_id = (
            _clean_text(row.get("review_id") or row.get("record_id"))
            or f"review-row-{index}"
        )
        target_id_field = (
            "review_id" if _clean_text(row.get("review_id")) else "record_id"
        )
        target_record_id = _clean_text(row.get(target_id_field))
        source_parts = [
            _clean_text(row.get("source_file")),
            (
                f"page {_clean_text(row.get('source_page'))}"
                if _clean_text(row.get("source_page"))
                else ""
            ),
            (
                f"row {_clean_text(row.get('source_row'))}"
                if _clean_text(row.get("source_row"))
                else ""
            ),
        ]
        source_ref = "; ".join(part for part in source_parts if part) or None
        data = dict(row)
        if target_record_id:
            data.update(
                {
                    "target_artifact": "codex_review_packet.json",
                    "target_id_field": target_id_field,
                    "target_record_id": target_record_id,
                    "target_field": "review_notes",
                    "edit_hint": (
                        "Editing this review row writes the reviewer note to "
                        "review_notes in codex_review_packet.json."
                    ),
                }
            )
        items.append(
            _base_item(
                item_id,
                _review_item_type(row),
                _review_title(row, index),
                source_path=source_ref,
                output_path="codex_review_packet.json",
                allowed_actions=(
                    "accept",
                    "reject",
                    "edit",
                    "mark_unclear",
                    "request_more_documents",
                    "skip",
                ),
                recommended_action=_review_action(row),
                evidence=[
                    {
                        "kind": "deterministic_classification",
                        "status": row.get("deterministic_status")
                        or row.get("reconciliation_status"),
                        "rule": row.get("deterministic_rule")
                        or row.get("rule_applied"),
                        "evidence_level": row.get("deterministic_evidence_level")
                        or row.get("evidence_level"),
                        "matched_evidence_type": row.get("matched_evidence_type"),
                        "matched_evidence_reference": row.get(
                            "matched_evidence_reference"
                        ),
                    },
                    {
                        "kind": "review_control",
                        "review_status": row.get("review_status"),
                        "review_selection_reason": row.get("review_selection_reason"),
                        "review_flags": row.get("review_flags"),
                        "review_instruction": row.get("review_instruction"),
                    },
                ],
                data=data,
            )
        )
    return items


def _check_items(checks: Sequence[dict[str, Any]]) -> list[dict[str, Any]]:
    failing = [
        row
        for row in checks
        if _clean_text(row.get("status")).upper() not in {"", "PASS"}
    ][:MAX_CHECK_ITEMS]
    return [
        _base_item(
            f"check-{index}",
            "check_exception",
            _clean_text(row.get("check")) or f"Check {index}",
            output_path="run_manifest.json",
            allowed_actions=("accept", "reject", "edit", "mark_unclear", "skip"),
            recommended_action=(
                "reject"
                if _clean_text(row.get("status")).upper() == "FAIL"
                else "mark_unclear"
            ),
            evidence=[
                {
                    "kind": "deterministic_check",
                    "status": row.get("status"),
                    "actual": row.get("actual"),
                    "expected": row.get("expected"),
                    "note": row.get("note"),
                }
            ],
            data=dict(row),
        )
        for index, row in enumerate(failing, start=1)
    ]


def _artifact_items(
    result: dict[str, Any],
    output_dir: Path,
    *,
    missing_evidence_requests_path: str | Path | None = None,
) -> list[dict[str, Any]]:
    artifact_specs = [
        ("excel_path", "workpaper_artifact", "Audit reconciliation workbook"),
        (
            "accountant_report_path",
            "workpaper_artifact",
            "Commercialista operating workbook",
        ),
        ("word_path", "report_artifact", "Narrative reconciliation report"),
    ]
    if missing_evidence_requests_path:
        artifact_specs.append(
            (
                "missing_evidence_requests_path",
                "evidence_request_artifact",
                "Targeted missing-evidence requests",
            )
        )
        result = {
            **result,
            "missing_evidence_requests_path": missing_evidence_requests_path,
        }

    items: list[dict[str, Any]] = []
    for index, (field, item_type, title) in enumerate(artifact_specs, start=1):
        path_value = result.get(field)
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


def _path_role_map(
    output_dir: Path,
    result: dict[str, Any],
    missing_evidence_requests_path: str | Path | None,
) -> dict[str, str]:
    paths = {
        "audit_workpaper": result.get("excel_path"),
        "accountant_workbook": result.get("accountant_report_path"),
        "word_report": result.get("word_path"),
        "missing_evidence_requests": (
            missing_evidence_requests_path
            or result.get("missing_evidence_requests_path")
        ),
    }
    role_by_path: dict[str, str] = {}
    for role, value in paths.items():
        reference = _as_output_ref(value, output_dir)
        if reference:
            role_by_path[reference] = role
    return role_by_path


def _audit_workpaper_required_sheets(language: str) -> list[str]:
    if str(language or "").lower().startswith("it"):
        return [
            "Indice",
            "Assunzioni",
            "Dettaglio riconciliazione",
            "Sintesi",
            "Controlli",
            "Revisione Codex",
        ]
    return [
        "Index",
        "Assumptions",
        "Reconciliation detail",
        "Summary",
        "Checks",
        "Review",
    ]


def _audit_workpaper_required_sheet_headers(language: str) -> dict[str, list[str]]:
    if str(language or "").lower().startswith("it"):
        return {
            "Indice": ["Foglio", "Righe"],
            "Assunzioni": ["Campo", "Valore"],
        }
    return {
        "Index": ["Sheet", "Rows"],
        "Assumptions": ["Field", "Value"],
    }


ITALIAN_CELL_FIELD_LABELS = {
    "cutoff_date": "Data di cut-off",
    "document_no": "Documento",
    "record_id": "ID riga",
    "reconciliation_status": "Esito riconciliazione",
    "rule_applied": "Regola applicata",
}


def _is_italian(language: str) -> bool:
    return str(language or "").lower().startswith("it")


def _fallback_cell_label(value: object) -> str:
    text = str(value or "").strip()
    if not text:
        return ""
    label = text.replace("_", " ")
    return label[:1].upper() + label[1:]


def _cell_field_label(field: object, language: str) -> str:
    value = str(field or "").strip()
    if not value:
        return ""
    if _is_italian(language):
        return ITALIAN_CELL_FIELD_LABELS.get(value.lower(), _fallback_cell_label(value))
    return value


def _cell_expected_text(value: object) -> str:
    if isinstance(value, (dict, list)) or value is None:
        return ""
    return str(value).strip()


def _column_letters(index: int) -> str:
    letters = ""
    while index > 0:
        index, remainder = divmod(index - 1, 26)
        letters = chr(65 + remainder) + letters
    return letters


def _add_cell_check(cells: dict[str, str], reference: str, value: object) -> None:
    expected = _cell_expected_text(value)
    if expected:
        cells[reference] = expected


def _audit_assumption_cell_checks(
    result: dict[str, Any] | None, language: str
) -> dict[str, str]:
    assumptions = result.get("assumptions") if isinstance(result, dict) else None
    if not isinstance(assumptions, dict):
        return {}
    checks: dict[str, str] = {}
    for row_offset, (field, value) in enumerate(assumptions.items(), start=2):
        if str(field) not in {"scope_year", "cutoff_date", "currency"}:
            continue
        _add_cell_check(checks, f"A{row_offset}", _cell_field_label(field, language))
        _add_cell_check(checks, f"B{row_offset}", value)
    return checks


def _first_reconciliation_detail_cell_checks(
    result: dict[str, Any] | None, language: str
) -> dict[str, str]:
    rows = result.get("reconciliation_rows") if isinstance(result, dict) else None
    if not isinstance(rows, list) or not rows or not isinstance(rows[0], dict):
        return {}
    first_row = rows[0]
    localized_headers = {
        field: _cell_field_label(field, language) for field in first_row.keys()
    }
    ordered_headers = sorted(localized_headers.values())
    checks: dict[str, str] = {}
    for field in ("document_no", "record_id"):
        if field not in first_row:
            continue
        header = localized_headers[field]
        if not header:
            continue
        column_index = ordered_headers.index(header) + 1
        column = _column_letters(column_index)
        _add_cell_check(checks, f"{column}1", header)
        _add_cell_check(checks, f"{column}2", first_row.get(field))
    return checks


def _audit_workpaper_required_cells(
    language: str, result: dict[str, Any] | None = None
) -> dict[str, dict[str, str]]:
    if str(language or "").lower().startswith("it"):
        cells = {
            "Indice": {
                "A1": "Foglio",
                "B1": "Righe",
                "A2": "Assunzioni",
                "A5": "Dettaglio riconciliazione",
            },
            "Assunzioni": {"A1": "Campo", "B1": "Valore"},
        }
        assumption_checks = _audit_assumption_cell_checks(result, language)
        if assumption_checks:
            cells["Assunzioni"].update(assumption_checks)
        detail_checks = _first_reconciliation_detail_cell_checks(result, language)
        if detail_checks:
            cells["Dettaglio riconciliazione"] = detail_checks
        return cells
    cells = {
        "Index": {
            "A1": "Sheet",
            "B1": "Rows",
            "A2": "Assumptions",
            "A5": "Reconciliation detail",
        },
        "Assumptions": {"A1": "Field", "B1": "Value"},
    }
    assumption_checks = _audit_assumption_cell_checks(result, language)
    if assumption_checks:
        cells["Assumptions"].update(assumption_checks)
    detail_checks = _first_reconciliation_detail_cell_checks(result, language)
    if detail_checks:
        cells["Reconciliation detail"] = detail_checks
    return cells


def _accountant_workbook_required_sheet_headers() -> dict[str, list[str]]:
    return {
        "Legenda": ["campo", "valore"],
        "Scheda operativa": [
            "id dettaglio",
            "partita",
            "stato riscontro",
            "azione richiesta",
        ],
        "Dettaglio riscontri": [
            "id dettaglio",
            "partita",
            "tipo evidenza",
            "riferimento fonte",
        ],
    }


def _accountant_workbook_required_cells(
    result: dict[str, Any] | None = None,
) -> dict[str, dict[str, str]]:
    cells = {
        "Legenda": {"A1": "campo", "B1": "valore"},
        "Scheda operativa": {"A1": "id dettaglio", "B1": "partita"},
        "Dettaglio riscontri": {"A1": "id dettaglio", "B1": "partita"},
    }
    rows = result.get("reconciliation_rows") if isinstance(result, dict) else None
    if isinstance(rows, list):
        cells["Legenda"]["A3"] = "Righe"
        cells["Legenda"]["B3"] = str(len(rows))
        if rows and isinstance(rows[0], dict):
            cells["Scheda operativa"]["A2"] = "R0001"
            document = rows[0].get("document_no") or rows[0].get("document_key")
            _add_cell_check(cells["Scheda operativa"], "B2", document)
    return cells


def _word_report_required_text(language: str) -> list[str]:
    if str(language or "").lower().startswith("it"):
        return [
            "Sintesi esecutiva",
            "Perimetro e metodo",
            "Come leggere gli esiti",
            "Controlli automatici",
            "Revisione manuale Codex",
            "Limiti della procedura",
            "Rinvio al file Excel",
        ]
    return [
        "Executive Summary",
        "Scope and Method",
        "How to Read the Results",
        "Automated Checks",
        "Codex Manual Review",
        "Procedure Limits",
        "Excel Reference",
    ]


def _output_quality_metadata(
    role: str | None,
    kind: str,
    language: str,
    *,
    result: dict[str, Any] | None = None,
) -> dict[str, Any]:
    if role == "audit_workpaper" and kind in {"xlsx", "xlsm"}:
        return {
            "artifact_role": role,
            "required_sheets": _audit_workpaper_required_sheets(language),
            "required_sheet_headers": _audit_workpaper_required_sheet_headers(language),
            "required_cells": _audit_workpaper_required_cells(language, result),
            "qa_checks": [
                "office_zip",
                "workbook_xml",
                "required_sheets",
                "required_sheet_headers",
                "required_cells",
            ],
        }
    if role == "accountant_workbook" and kind in {"xlsx", "xlsm"}:
        return {
            "artifact_role": role,
            "required_sheets": [
                "Legenda",
                "Scheda operativa",
                "Dettaglio riscontri",
            ],
            "required_sheet_headers": _accountant_workbook_required_sheet_headers(),
            "required_cells": _accountant_workbook_required_cells(result),
            "qa_checks": [
                "office_zip",
                "workbook_xml",
                "required_sheets",
                "required_sheet_headers",
                "required_cells",
            ],
        }
    if role == "word_report" and kind == "docx":
        return {
            "artifact_role": role,
            "required_text": _word_report_required_text(language),
            "qa_checks": ["office_zip", "word_document_xml", "required_text"],
        }
    if role == "missing_evidence_requests" and kind in {"xlsx", "xlsm"}:
        return {
            "artifact_role": role,
            "qa_checks": ["office_zip", "workbook_xml"],
        }
    return {}


def _output_records(
    output_dir: Path,
    *,
    result: dict[str, Any],
    missing_evidence_requests_path: str | Path | None = None,
    language: str = "it",
) -> list[dict[str, Any]]:
    review_files = {
        "run_intake.json",
        "review_payload.json",
        "ui_decisions.json",
        "final_artifacts.json",
    }
    role_by_path = _path_role_map(output_dir, result, missing_evidence_requests_path)
    outputs: list[dict[str, Any]] = []
    for path in sorted(output_dir.rglob("*")):
        if not path.is_file() or path.name in review_files:
            continue
        relative = path.relative_to(output_dir).as_posix()
        kind = path.suffix.lower().lstrip(".") or "file"
        output = {
            "path": relative,
            "size_bytes": path.stat().st_size,
            "kind": kind,
            "status": "written",
            **_output_quality_metadata(
                role_by_path.get(relative), kind, language, result=result
            ),
        }
        if relative == "codex_review_packet.json":
            output["required_columns"] = ["review_id", "review_notes"]
            output["qa_checks"] = list(
                dict.fromkeys(
                    [*output.get("qa_checks", []), "json_parse", "required_columns"]
                )
            )
        outputs.append(output)
    return outputs


def _quote_command_path(path: Path) -> str:
    text = path.as_posix()
    return f'"{text}"' if any(char.isspace() for char in text) else text


def _write_artifact_card(
    output_dir: Path,
    *,
    run_id: str,
    review_payload: dict[str, Any],
    result: dict[str, Any],
    missing_evidence_requests_path: str | Path | None = None,
) -> Path:
    review_items = int(review_payload.get("item_count") or 0)
    summary = review_payload.get("summary") if isinstance(review_payload, dict) else {}
    failed_check_count = (
        summary.get("failed_check_count") if isinstance(summary, dict) else None
    )
    unresolved_count = 0
    if isinstance(summary, dict):
        status_counts = summary.get("reconciliation_status_counts")
        if isinstance(status_counts, dict):
            unresolved_count = int(status_counts.get("unresolved") or 0)
    audit_workbook = _as_output_ref(result.get("excel_path"), output_dir)
    accountant_workbook = _as_output_ref(
        result.get("accountant_report_path"), output_dir
    )
    word_report = _as_output_ref(result.get("word_path"), output_dir)
    missing_requests = _as_output_ref(
        missing_evidence_requests_path or result.get("missing_evidence_requests_path"),
        output_dir,
    )
    command = f"python scripts/review_server.py {_quote_command_path(output_dir)}"
    lines = [
        "# Audit Reconciliation Artifact Card",
        "",
        f"- Run ID: `{run_id}`",
        f"- Output folder: `{output_dir.as_posix()}`",
        "- Review handoff: browser locale tramite `scripts/review_server.py`",
        f"- Command: `{command}`",
        "- Review status: `pending_review` finche non vengono salvate/applicate le decisioni",
        f"- Review items: `{review_items}`",
        f"- Failed checks: `{failed_check_count}`",
        f"- Unresolved rows: `{unresolved_count}`",
        "",
        "## Artefatti principali",
        "",
        f"- Audit workbook: `{audit_workbook or 'not_written'}`",
        f"- Scheda commercialista: `{accountant_workbook or 'not_written'}`",
        f"- Relazione Word: `{word_report or 'not_written'}`",
        f"- Richieste evidenze: `{missing_requests or 'not_written'}`",
        "- Review payload: `review_payload.json`",
        "- Decisioni: `ui_decisions.json`",
        "- Stato finale: `final_artifacts.json`",
        "- Fallback statico: `review_ui.html`",
        "",
        "## Prossima azione",
        "",
        "Aprire il server locale, comunicare esplicitamente l'URL al reviewer, "
        "raccogliere le decisioni nella pagina browser e usare Apply decisions "
        "per scrivere `ui_decisions.json`, `applied_decisions.json` e lo stato "
        "aggiornato in `final_artifacts.json`.",
    ]
    path = output_dir / "artifact_card.md"
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


def write_run_intake(
    output_dir: Path,
    *,
    assumptions: dict[str, Any],
    source_inventory: Sequence[dict[str, Any]] | None = None,
    source_paths: Sequence[str | Path] = (),
    language: str = "it",
    source_hint: str | Path | None = None,
    dependency_check: dict[str, Any] | None = None,
) -> RunIntakeResult:
    """Write the durable run-intake artifact for audit reconciliation."""

    paths = _source_paths_from_inventory(source_inventory, source_paths)
    run_id = _run_id(source_hint or (paths[0] if paths else output_dir))
    payload = {
        "schema_version": SCHEMA_VERSION,
        "plugin": PLUGIN_NAME,
        "workflow": WORKFLOW_NAME,
        "run_id": run_id,
        "created_at": _utc_now(),
        "language": language,
        "input_paths": paths,
        "output_dir": output_dir.as_posix(),
        "inferred_task": "audit_reconciliation_review_payload",
        "assumptions": {
            "scope_year": assumptions.get("scope_year"),
            "cutoff_date": assumptions.get("cutoff_date"),
            "currency": assumptions.get("currency", "EUR"),
            "report_language": assumptions.get("report_language", language),
            "document_language": assumptions.get("document_language", language),
            "post_cutoff_events_excluded": assumptions.get(
                "post_cutoff_events_excluded"
            ),
            "payment_orders_are_bank_evidence": assumptions.get(
                "payment_orders_are_bank_evidence"
            ),
            "factoring_pro_soluto_closes_item": assumptions.get(
                "factoring_pro_soluto_closes_item"
            ),
            "compensation_requires_bank": assumptions.get("compensation_requires_bank"),
            "source_file_count": len(source_inventory or []),
        },
        "unresolved_questions": [],
        "dependency_check": (
            dependency_check
            if dependency_check is not None
            else _dependency_check_from_environment(assumptions)
        ),
        "data_posture": {
            "local_files_read": paths,
            "model_excerpts_sent": [],
            "external_connectors_used": [],
            "upload_paths_used": [],
            "remote_sql_execution_used": False,
            "hosted_notebook_execution_used": False,
            "notes": [
                "Reconciliation scripts read local accounting evidence paths recorded in input_paths.",
                "Review payloads expose bounded reconciliation rows and evidence references for UI review.",
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
    result: dict[str, Any],
    source_inventory: Sequence[dict[str, Any]] | None = None,
    source_paths: Sequence[str | Path] = (),
    missing_evidence_requests_path: str | Path | None = None,
    language: str = "it",
) -> ReviewSessionResult:
    """Write review payload, pending decisions, and final artifact inventory."""

    reconciliation_rows = [
        row for row in result.get("reconciliation_rows", []) if isinstance(row, dict)
    ]
    review_rows = [
        row for row in result.get("review_rows", []) if isinstance(row, dict)
    ]
    checks = [row for row in result.get("checks", []) if isinstance(row, dict)]
    items: list[dict[str, Any]] = []
    items.extend(_review_row_items(review_rows))
    items.extend(_check_items(checks))
    items.extend(
        _artifact_items(
            result,
            output_dir,
            missing_evidence_requests_path=missing_evidence_requests_path,
        )
    )

    source_path_refs = _source_paths_from_inventory(source_inventory, source_paths)
    review_status_counts = _status_counts(review_rows, "review_status")
    reconciliation_status_counts = _status_counts(
        reconciliation_rows, "reconciliation_status"
    )
    failed_checks = [
        row
        for row in checks
        if _clean_text(row.get("status")).upper() not in {"", "PASS"}
    ]
    rollforward_summary = _rollforward_exception_summary(
        result.get("account_rollforward_check") or []
    )
    review_payload = {
        "schema_version": SCHEMA_VERSION,
        "plugin": PLUGIN_NAME,
        "workflow": WORKFLOW_NAME,
        "run_id": run_id,
        "created_at": _utc_now(),
        "language": language,
        "source_paths": source_path_refs,
        "review_type": "audit_reconciliation_review",
        "items": items,
        "item_count": len(items),
        "columns": _review_columns(),
        "evidence": {
            "run_intake": _as_output_ref(run_intake_path, output_dir),
            "audit_workbook": _as_output_ref(result.get("excel_path"), output_dir),
            "accountant_report": _as_output_ref(
                result.get("accountant_report_path"), output_dir
            ),
            "word_report": _as_output_ref(result.get("word_path"), output_dir),
            "codex_review_packet": "codex_review_packet.json",
            "run_manifest": "run_manifest.json",
            "source_pages": "source_pages.json",
            "normalized_records": "normalized_records.json",
            "missing_evidence_requests": _as_output_ref(
                missing_evidence_requests_path
                or result.get("missing_evidence_requests_path"),
                output_dir,
            ),
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
            "source_file_count": len(source_path_refs),
            "reconciliation_row_count": len(reconciliation_rows),
            "review_row_count": len(review_rows),
            "review_item_count": len(items),
            "checks_count": len(checks),
            "failed_check_count": len(failed_checks),
            "checks_pass": bool(result.get("checks_pass")),
            "reconciliation_status_counts": reconciliation_status_counts,
            "review_status_counts": review_status_counts,
            "bank_allocation_candidate_count": len(
                result.get("bank_allocation_candidates") or []
            ),
            "missing_evidence_request_written": bool(
                missing_evidence_requests_path
                or result.get("missing_evidence_requests_path")
            ),
            "rollforward_exception_count": rollforward_summary["exception_count"],
            "rollforward_status_counts": rollforward_summary["status_counts"],
            "rollforward_exceptions": rollforward_summary["exceptions"],
            "rollforward_exceptions_truncated": rollforward_summary["truncated"],
            "currency": (
                (result.get("assumptions") or {}).get("currency", "EUR")
                if isinstance(result.get("assumptions"), dict)
                else "EUR"
            ),
        },
    }
    review_payload_path = _write_json(
        output_dir / "review_payload.json",
        review_payload,
    )

    ui_decisions_payload = {
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
    }
    ui_decisions_path = _write_json(
        output_dir / "ui_decisions.json",
        ui_decisions_payload,
    )

    review_html_path = _write_standalone_review_html(
        output_dir,
        run_intake=_load_json_object(run_intake_path),
        review_payload=review_payload,
        ui_decisions=ui_decisions_payload,
    )

    caveats = [
        "The browser review payload is bounded; use the Excel workbook and JSON diagnostics as the complete audit evidence set.",
        "ui_decisions.json is pending until the local browser review server or MCP widget records decisions.",
        "Deterministic row classifications remain authoritative until reviewed issues are fixed and the workflow is rerun.",
    ]
    if rollforward_summary["exception_count"]:
        caveats.append(
            "Account roll-forward has exception rows; review account_rollforward_check.json and the workbook roll-forward sheet before final conclusions."
        )

    artifact_card_path = _write_artifact_card(
        output_dir,
        run_id=run_id,
        review_payload=review_payload,
        result=result,
        missing_evidence_requests_path=missing_evidence_requests_path,
    )

    final_artifacts_path = _write_json(
        output_dir / "final_artifacts.json",
        {
            "schema_version": SCHEMA_VERSION,
            "plugin": PLUGIN_NAME,
            "workflow": WORKFLOW_NAME,
            "run_id": run_id,
            "completed_at": _utc_now(),
            "outputs": _output_records(
                output_dir,
                result=result,
                missing_evidence_requests_path=missing_evidence_requests_path,
                language=language,
            ),
            "caveats": caveats,
            "review_handoff": {
                "primary": "local_browser_server",
                "status": "browser_review_required",
                "required_before_final_delivery": True,
                "server": {
                    "script": "scripts/review_server.py",
                    "host": "127.0.0.1",
                    "port": "auto",
                    "opens": "system_browser",
                    "required": True,
                    "command": (
                        "python scripts/review_server.py "
                        f"{_quote_command_path(output_dir)}"
                    ),
                    "writes": [
                        "ui_decisions.json",
                        "applied_decisions.json",
                        "final_artifacts.json",
                    ],
                },
                "artifact_card": {
                    "path": artifact_card_path.name,
                    "required": True,
                    "announce_to_user": True,
                },
                "mcp": {
                    "status": "optional_integrated_surface",
                    "tool_sequence": [
                        "validate_audit_reconciliation_review",
                        "render_audit_reconciliation_review",
                    ],
                    "widget_uri": "ui://widget/audit-reconciliation-review.html",
                },
                "fallback": {
                    "artifact": "review_ui.html",
                    "when": "The local review server cannot start or the browser cannot be opened.",
                    "persistence": "copy_or_download_json",
                },
            },
            "next_actions": [
                "Open the browser review server with scripts/review_server.py and explicitly tell the reviewer the localhost URL and artifact_card.md path.",
                "Use the browser page to save or apply decisions so ui_decisions.json, applied_decisions.json, and final_artifacts.json are written in the output folder.",
                "Use the MCP validate/render widget only as an optional integrated Codex surface; it is not the primary handoff for normal browser review.",
                "Use review_ui.html only when the local server cannot start or the browser cannot be opened; the static fallback cannot persist decisions by itself.",
                "Review PENDING, FAIL, unresolved, needs-evidence, and probable-payment rows before treating the package as final.",
                "Use targeted missing-evidence requests for operational follow-up when the run produced them.",
            ],
            "status": "written_pending_review",
        },
    )
    _append_execution_trace(
        run_intake_path,
        final_artifacts_path,
        command=[
            "python",
            "plugins/audit-reconciliation/scripts/reconciliation_workflow.py",
        ],
    )

    return ReviewSessionResult(
        run_id=run_id,
        run_intake_path=run_intake_path,
        review_payload_path=review_payload_path,
        ui_decisions_path=ui_decisions_path,
        review_html_path=review_html_path,
        artifact_card_path=artifact_card_path,
        final_artifacts_path=final_artifacts_path,
        review_item_count=len(items),
    )
