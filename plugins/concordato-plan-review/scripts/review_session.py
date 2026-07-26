from __future__ import annotations

import hashlib
import json
import re
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
from typing import Any, Mapping, Sequence

SCRIPT_DIR = Path(__file__).resolve().parent


def _ensure_vendor_import_path() -> None:
    """Expose component-local or repository-shared Vera vendor modules."""

    component_root = SCRIPT_DIR.parent
    candidates = (
        component_root / "vendor" / "modules",
        component_root.parent / "_shared" / "vendor" / "modules",
    )
    for candidate in candidates:
        if candidate.is_dir() and str(candidate) not in sys.path:
            sys.path.insert(0, str(candidate))


_ensure_vendor_import_path()
from vera_assurance import (  # noqa: E402
    MoneyValidationError,
    canonical_json_sha256,
    decimal_text,
    parse_canonical_decimal,
    parse_localized_decimal,
)

__all__ = [
    "ReviewSessionResult",
    "RunIntakeResult",
    "write_review_session_artifacts",
    "write_run_intake",
]

SCHEMA_VERSION = "1.0"
PLUGIN_NAME = "concordato-plan-review"
WORKFLOW_NAME = "concordato-plan-review"
MAX_INVENTORY_ITEMS = 300
MAX_PLAN_AMOUNT_ITEMS = 400
MAX_EXTRACTION_ERROR_ITEMS = 100
MAX_SEMANTIC_QUESTION_ITEMS = 100
MAX_SEMANTIC_ISSUE_ITEMS = 200
MAX_CREDITOR_CLASS_ITEMS = 200
WORKPAPER_SHEET_HEADERS = {
    "Inventory": [
        "path",
        "relative_path",
        "name",
        "suffix",
        "size_bytes",
        "supported",
        "suggested_role",
        "reviewed_role",
        "source_artifact_ref",
        "capture_status",
        "reviewed_currency",
        "reviewed_unit",
    ],
    "Amount candidates": [
        "candidate_id",
        "source_file",
        "source_artifact_ref",
        "source_role",
        "location",
        "amount",
        "currency",
        "unit",
        "token",
        "context",
    ],
    "Candidate matches": [
        "plan_source_file",
        "plan_source_artifact_ref",
        "plan_location",
        "plan_amount",
        "plan_currency",
        "plan_unit",
        "plan_context",
        "support_source_file",
        "support_source_artifact_ref",
        "support_role",
        "support_location",
        "support_amount",
        "support_currency",
        "support_unit",
        "support_context",
        "difference",
        "abs_difference",
        "tolerance",
        "within_tolerance",
        "calculation_formula_id",
        "context_token_overlap",
        "match_status",
    ],
}
WORKPAPER_SHEETS = list(WORKPAPER_SHEET_HEADERS)
SPANISH_WORKPAPER_SHEET_NAMES = {
    "Inventory": "Inventario",
    "Amount candidates": "Importes candidatos",
    "Candidate matches": "Coincidencias candidatas",
}


@dataclass(frozen=True)
class RunIntakeResult:
    """Run intake artifact written after source inventory."""

    run_id: str
    path: Path


@dataclass(frozen=True)
class ReviewSessionResult:
    """Review-session artifacts for one concordato plan run."""

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


def _run_id(input_dir: Path) -> str:
    timestamp = re.sub(r"[^0-9]", "", _utc_now())
    return f"{PLUGIN_NAME}-{_safe_slug(input_dir.name)}-{timestamp}"


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
    language: str,
) -> Path:
    path = output_dir / "review_handoff.md"
    if _is_spanish(language):
        lines = [
            f"# Entrega para revisión: {title}",
            "",
            f"- ID de ejecución: `{run_id}`",
            "- Datos de revisión: `review_payload.json`",
            "- Datos de entrada de la ejecución: `run_intake.json`",
            "- Decisiones pendientes: `ui_decisions.json`",
            "- Decisiones aplicadas: `applied_decisions.json`",
            "- Artefactos finales: `final_artifacts.json`",
            "",
            "## Revisión en Codex",
            f"1. Valide los datos con `{validate_tool}`.",
            f"2. Muestre el espacio de revisión con `{render_tool}`.",
            f"3. Guarde las acciones de revisión con `{save_tool}`.",
            f"4. Aplique las acciones de revisión con `{apply_tool}`.",
            "",
            "El guardado y la aplicación persistentes requieren la interfaz de revisión MCP o del servidor local. "
            "La alternativa HTML estática solo permite copiar o descargar el JSON de decisiones.",
            "",
            "<!-- Review Handoff -->",
        ]
    else:
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


def _review_handoff_output_record(path: Path, language: str) -> dict[str, Any]:
    return {
        "path": path.name,
        "size_bytes": path.stat().st_size,
        "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
        "kind": "md",
        "status": "written",
        "required_text": [
            "Entrega para revisión" if _is_spanish(language) else "Review Handoff",
            *(["Review Handoff"] if _is_spanish(language) else []),
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


def _as_output_ref(path: Path, output_dir: Path) -> str:
    try:
        return path.relative_to(output_dir).as_posix()
    except ValueError:
        return path.as_posix()


def _role_counts(inventory: Sequence[dict[str, Any]]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for row in inventory:
        role = str(row.get("suggested_role") or "unclassified")
        counts[role] = counts.get(role, 0) + 1
    return dict(sorted(counts.items(), key=lambda item: item[0]))


def _amount(value: object) -> Decimal:
    try:
        if isinstance(value, str):
            return parse_canonical_decimal(
                value,
                label="concordato review amount",
            )
        if isinstance(value, float):
            raise MoneyValidationError(
                "concordato review amount must not use a binary float"
            )
        return parse_localized_decimal(
            value,
            label="concordato review amount",
        )
    except MoneyValidationError as exc:
        raise ValueError(str(exc)) from exc


def _format_amount(value: object) -> str:
    number = _amount(value)
    return f"{number:,.2f}"


def _is_spanish(language: object) -> bool:
    return _language_code(language) == "es"


def _language_code(language: object) -> str:
    code = str(language or "it").strip().lower().replace("_", "-").split("-", 1)[0]
    return code if code in {"de", "en", "es", "fr", "it"} else "it"


def _candidate_key(candidate: Any) -> tuple[str, str, str, Decimal]:
    return (
        str(getattr(candidate, "source_artifact_ref", "")),
        str(getattr(candidate, "source_file", "")),
        str(getattr(candidate, "location", "")),
        _amount(getattr(candidate, "amount", 0)),
    )


def _candidate_identity(candidate: Any) -> str:
    content = "|".join(
        (
            str(getattr(candidate, "source_artifact_ref", "")),
            str(getattr(candidate, "location", "")),
            str(getattr(candidate, "token", "")),
            decimal_text(_amount(getattr(candidate, "amount", 0))),
        )
    )
    return "candidate." + hashlib.sha256(content.encode("utf-8")).hexdigest()


def _match_key(match: dict[str, Any]) -> tuple[str, str, str, Decimal]:
    return (
        str(match.get("plan_source_artifact_ref") or ""),
        str(match.get("plan_source_file") or ""),
        str(match.get("plan_location") or ""),
        _amount(match.get("plan_amount")),
    )


def _candidate_data(candidate: Any) -> dict[str, Any]:
    return {
        "candidate_id": str(getattr(candidate, "candidate_id", ""))
        or _candidate_identity(candidate),
        "source_file": str(getattr(candidate, "source_file", "")),
        "source_artifact_ref": str(getattr(candidate, "source_artifact_ref", "")),
        "source_role": str(getattr(candidate, "source_role", "")),
        "location": str(getattr(candidate, "location", "")),
        "amount": decimal_text(_amount(getattr(candidate, "amount", 0))),
        "currency": str(getattr(candidate, "currency", "")),
        "unit": str(getattr(candidate, "unit", "")),
        "token": str(getattr(candidate, "token", "")),
        "context": str(getattr(candidate, "context", "")),
    }


def _required_cell_text(value: object) -> str:
    if value is None:
        return ""
    return " ".join(str(value).strip().split())


def _column_letters(index: int) -> str:
    letters = ""
    while index > 0:
        index, remainder = divmod(index - 1, 26)
        letters = chr(65 + remainder) + letters
    return letters


def _selected_required_cells(
    row: Mapping[str, Any],
    headers: Sequence[str],
    selected_headers: Sequence[str],
) -> dict[str, str]:
    cells: dict[str, str] = {}
    for header in selected_headers:
        if header not in headers:
            continue
        column = _column_letters(headers.index(header) + 1)
        header_text = _required_cell_text(header)
        value_text = _required_cell_text(row.get(header))
        if header_text:
            cells[f"{column}1"] = header_text
        if value_text:
            cells[f"{column}2"] = value_text
    return cells


def _required_cells_for_sheet(
    rows: Sequence[Mapping[str, Any]],
    headers: Sequence[str],
    selected_headers: Sequence[str],
) -> dict[str, str]:
    if not rows:
        return {"A1": "message", "A2": "No rows generated"}
    return _selected_required_cells(rows[0], headers, selected_headers)


def _workpaper_required_sheet_headers(
    *,
    inventory: Sequence[dict[str, Any]],
    candidates: Sequence[Any],
    matches: Sequence[dict[str, Any]],
) -> dict[str, list[str]]:
    candidate_rows = [_candidate_data(candidate) for candidate in candidates]
    rows_by_sheet: dict[str, Sequence[Mapping[str, Any]]] = {
        "Inventory": inventory,
        "Amount candidates": candidate_rows,
        "Candidate matches": matches,
    }
    return {
        sheet: WORKPAPER_SHEET_HEADERS[sheet] if rows_by_sheet[sheet] else ["message"]
        for sheet in WORKPAPER_SHEETS
    }


def _workpaper_required_cells(
    *,
    inventory: Sequence[dict[str, Any]],
    candidates: Sequence[Any],
    matches: Sequence[dict[str, Any]],
) -> dict[str, dict[str, str]]:
    candidate_rows = [_candidate_data(candidate) for candidate in candidates]
    return {
        "Inventory": _required_cells_for_sheet(
            inventory,
            WORKPAPER_SHEET_HEADERS["Inventory"],
            ("relative_path", "name", "suggested_role"),
        ),
        "Amount candidates": _required_cells_for_sheet(
            candidate_rows,
            WORKPAPER_SHEET_HEADERS["Amount candidates"],
            ("source_file", "source_role", "location", "amount"),
        ),
        "Candidate matches": _required_cells_for_sheet(
            matches,
            WORKPAPER_SHEET_HEADERS["Candidate matches"],
            (
                "plan_source_file",
                "plan_amount",
                "support_source_file",
                "support_amount",
                "match_status",
            ),
        ),
    }


def _unique_plan_candidates(candidates: Sequence[Any]) -> list[Any]:
    seen: set[tuple[str, str, str, Decimal]] = set()
    unique: list[Any] = []
    for candidate in candidates:
        if str(getattr(candidate, "source_role", "")) != "concordato_plan":
            continue
        key = _candidate_key(candidate)
        if key in seen:
            continue
        seen.add(key)
        unique.append(candidate)
    return sorted(
        unique,
        key=lambda item: _amount(getattr(item, "amount", 0)).copy_abs(),
        reverse=True,
    )


def _best_match_by_plan_key(
    matches: Sequence[dict[str, Any]],
) -> dict[tuple[str, str, str, Decimal], dict[str, Any]]:
    best: dict[tuple[str, str, str, Decimal], dict[str, Any]] = {}
    for row in matches:
        key = _match_key(row)
        current = best.get(key)
        if current is None:
            best[key] = dict(row)
            continue
        row_score = (
            _amount(row.get("abs_difference")),
            -_amount(row.get("context_token_overlap")),
        )
        current_score = (
            _amount(current.get("abs_difference")),
            -_amount(current.get("context_token_overlap")),
        )
        if row_score < current_score:
            best[key] = dict(row)
    return best


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


def _review_columns(language: str) -> list[dict[str, str]]:
    if _is_spanish(language):
        return [
            {"field": "item_type", "label": "Tipo"},
            {"field": "title", "label": "Elemento"},
            {"field": "recommended_action", "label": "Acción sugerida"},
            {"field": "source_path", "label": "Fuente"},
            {"field": "output_path", "label": "Salida"},
            {"field": "status", "label": "Estado"},
        ]
    return [
        {"field": "item_type", "label": "Tipo"},
        {"field": "title", "label": "Elemento"},
        {"field": "recommended_action", "label": "Azione suggerita"},
        {"field": "source_path", "label": "Fonte"},
        {"field": "output_path", "label": "Output"},
        {"field": "status", "label": "Stato"},
    ]


def _errors_by_source(
    extraction_errors: Sequence[dict[str, str]],
) -> dict[str, list[dict[str, str]]]:
    errors: dict[str, list[dict[str, str]]] = {}
    for error in extraction_errors:
        source_file = str(error.get("source_file") or "")
        errors.setdefault(source_file, []).append(dict(error))
    return errors


def _source_inventory_items(
    inventory: Sequence[dict[str, Any]],
    extraction_errors: Sequence[dict[str, str]],
    language: str,
) -> list[dict[str, Any]]:
    error_lookup = _errors_by_source(extraction_errors)
    items: list[dict[str, Any]] = []
    for index, row in enumerate(inventory[:MAX_INVENTORY_ITEMS], start=1):
        fallback = f"fuente {index}" if _is_spanish(language) else f"source {index}"
        name = str(row.get("name") or row.get("relative_path") or fallback)
        suggested_role = str(row.get("suggested_role") or "unclassified")
        supported = bool(row.get("supported"))
        source_errors = error_lookup.get(name, [])
        needs_attention = (
            not supported or suggested_role == "unclassified" or bool(source_errors)
        )
        items.append(
            _base_item(
                f"source-{index}",
                "source_inventory",
                name,
                source_path=str(row.get("path") or row.get("relative_path") or ""),
                allowed_actions=("accept", "edit", "mark_unclear", "skip"),
                recommended_action="mark_unclear" if needs_attention else "accept",
                evidence=[
                    {
                        "kind": "extraction_error",
                        "source_file": error.get("source_file"),
                        "error": error.get("error"),
                    }
                    for error in source_errors
                ],
                data=dict(row),
            )
        )
    if len(inventory) > MAX_INVENTORY_ITEMS:
        items.append(
            _base_item(
                "source-inventory-truncated",
                "source_role_attention",
                (
                    "Inventario de fuentes truncado en el widget"
                    if _is_spanish(language)
                    else "Inventario sorgenti troncato nel widget"
                ),
                output_path="inventory.json",
                allowed_actions=("accept", "mark_unclear", "skip"),
                recommended_action="mark_unclear",
                data={
                    "shown_count": MAX_INVENTORY_ITEMS,
                    "total_count": len(inventory),
                    "full_inventory": "inventory.json",
                },
            )
        )
    return items


def _semantic_items(
    *,
    semantic_status: str,
    case_model: Mapping[str, Any] | None,
    semantic_derived: Mapping[str, Any],
    semantic_error: str | None,
    language: str,
) -> list[dict[str, Any]]:
    """Build review rows from professional meaning, not filename heuristics."""

    spanish = _is_spanish(language)
    items = [
        _base_item(
            "semantic-case-status",
            "semantic_case_status",
            (
                "Estado del modelo del concordato preventivo"
                if spanish
                else "Stato del modello di concordato preventivo"
            ),
            output_path="concordato_case_model.json",
            allowed_actions=("accept", "edit", "mark_unclear", "skip"),
            recommended_action=(
                "accept" if semantic_status == "reviewed" else "mark_unclear"
            ),
            evidence=[],
            data={
                "status": semantic_status,
                "error": semantic_error or "",
                "review_note": (
                    "El modelo revisado estructura procedimiento, documentos, acreedores, tratamiento, liquidez y cuestiones profesionales."
                    if spanish
                    else "Il modello riesaminato struttura procedura, documenti, creditori, trattamento, liquidità e questioni professionali."
                ),
            },
        )
    ]
    if case_model is None:
        return items

    procedure = case_model["procedure"]
    items.append(
        _base_item(
            "procedure-identity",
            "procedure_identity",
            (
                f"{procedure.get('debtor_name') or 'Debitore non identificato'} · "
                f"{procedure.get('plan_type')} · {procedure.get('stage')}"
            ),
            output_path="concordato_case_model.json",
            allowed_actions=("accept", "edit", "mark_unclear", "skip"),
            recommended_action=(
                "accept"
                if procedure.get("identification_status") == "complete"
                else "mark_unclear"
            ),
            data=dict(procedure),
        )
    )
    for index, row in enumerate(
        case_model["review_questions"][:MAX_SEMANTIC_QUESTION_ITEMS],
        start=1,
    ):
        assessment = str(row.get("assessment") or "unclear")
        items.append(
            _base_item(
                f"semantic-question-{index}",
                "semantic_review_question",
                str(row.get("question") or row.get("area") or f"Question {index}"),
                output_path="concordato_semantic_review.md",
                allowed_actions=(
                    "accept",
                    "edit",
                    "mark_unclear",
                    "request_more_documents",
                    "skip",
                ),
                recommended_action=(
                    "accept"
                    if assessment in {"addressed", "not_applicable"}
                    else (
                        "request_more_documents"
                        if assessment == "gap"
                        else "mark_unclear"
                    )
                ),
                evidence=list(row.get("evidence_refs") or []),
                data=dict(row),
            )
        )
    for index, row in enumerate(
        case_model["issues"][:MAX_SEMANTIC_ISSUE_ITEMS],
        start=1,
    ):
        items.append(
            _base_item(
                f"semantic-issue-{index}",
                "semantic_issue",
                str(row.get("statement") or f"Issue {index}"),
                output_path="concordato_semantic_review.md",
                allowed_actions=(
                    "accept",
                    "edit",
                    "mark_unclear",
                    "request_more_documents",
                    "skip",
                ),
                recommended_action=(
                    "accept"
                    if row.get("status") == "resolved"
                    else (
                        "request_more_documents"
                        if row.get("status") == "open"
                        else "mark_unclear"
                    )
                ),
                evidence=list(row.get("evidence_refs") or []),
                data=dict(row),
            )
        )
    for index, row in enumerate(
        list(semantic_derived.get("classes") or [])[:MAX_CREDITOR_CLASS_ITEMS],
        start=1,
    ):
        items.append(
            _base_item(
                f"creditor-class-{index}",
                "creditor_class_treatment",
                (
                    f"{row.get('class_id')} · {row.get('priority')} · "
                    f"{row.get('proposed_recovery_pct') or '—'}%"
                ),
                output_path="creditor_class_summary.csv",
                allowed_actions=("accept", "edit", "mark_unclear", "skip"),
                recommended_action="mark_unclear",
                data=dict(row)
                | {
                    "review_note": (
                        "The aggregation is exact; class, priority, and treatment "
                        "remain reviewer judgments."
                    )
                },
            )
        )
    for index, row in enumerate(semantic_derived.get("checks") or [], start=1):
        items.append(
            _base_item(
                f"mechanical-check-{index}",
                "mechanical_consistency_check",
                str(row.get("check_id") or f"Mechanical check {index}"),
                output_path="concordato_semantic_checks.json",
                allowed_actions=("accept", "edit", "mark_unclear", "skip"),
                recommended_action=(
                    "accept" if row.get("status") == "passed" else "mark_unclear"
                ),
                data=dict(row),
            )
        )
    return items


def _plan_amount_items(
    candidates: Sequence[Any],
    matches: Sequence[dict[str, Any]],
    language: str,
) -> list[dict[str, Any]]:
    best_matches = _best_match_by_plan_key(matches)
    items: list[dict[str, Any]] = []
    unique_plan_candidates = _unique_plan_candidates(candidates)
    for index, candidate in enumerate(
        unique_plan_candidates[:MAX_PLAN_AMOUNT_ITEMS],
        start=1,
    ):
        key = _candidate_key(candidate)
        match = best_matches.get(key)
        candidate_data = _candidate_data(candidate)
        title = (
            f"{candidate_data['source_file']} {candidate_data['location']} "
            f"{_format_amount(candidate_data['amount'])}"
        )
        if match is None:
            requested_document = (
                (
                    "Justificante o anexo explicativo para el importe del plan del concordato preventivo "
                    f"{_format_amount(candidate_data['amount'])} en "
                    f"{candidate_data['source_file']}, {candidate_data['location']}"
                )
                if _is_spanish(language)
                else (
                    "Support document or explanatory schedule for concordato plan amount "
                    f"{_format_amount(candidate_data['amount'])} in "
                    f"{candidate_data['source_file']} at {candidate_data['location']}"
                )
            )
            followup_data = {
                "requested_document": requested_document,
                "required_document": requested_document,
                "source_file": candidate_data["source_file"],
                "source_table": candidate_data["location"],
                "record_id": candidate_data["location"],
                "amount": _format_amount(candidate_data["amount"]),
                "reason": (
                    "Ningún importe justificativo determinista coincide con este importe del plan dentro de la tolerancia."
                    if _is_spanish(language)
                    else "No deterministic support amount matched this plan amount within tolerance."
                ),
            }
            items.append(
                _base_item(
                    f"unmatched-plan-amount-{index}",
                    "unmatched_plan_amount",
                    title,
                    source_path=candidate_data["source_file"],
                    output_path="amount_candidates.csv",
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
                            "kind": "plan_context",
                            "text": candidate_data["context"],
                            "requested_document": requested_document,
                            "required_document": requested_document,
                            "source_file": candidate_data["source_file"],
                            "source_table": candidate_data["location"],
                            "record_id": candidate_data["location"],
                            "amount": _format_amount(candidate_data["amount"]),
                            "reason": followup_data["reason"],
                        }
                    ],
                    data=candidate_data
                    | {
                        "match_status": "no_candidate_amount_match",
                        "review_note": (
                            (
                                "Ningún importe de origen coincide dentro de la tolerancia. La persona revisora debe clasificarlo como no justificado, prospectivo, reclasificado o ajeno a las evidencias disponibles."
                                if _is_spanish(language)
                                else "No source amount matched within tolerance. Reviewer must classify whether this is unsupported, prospective, reclassified, or outside the available evidence."
                            )
                        ),
                    }
                    | followup_data,
                )
            )
            continue
        items.append(
            _base_item(
                f"candidate-match-{index}",
                "candidate_amount_match",
                title,
                source_path=candidate_data["source_file"],
                output_path="exact_amount_matches.csv",
                allowed_actions=("accept", "edit", "mark_unclear", "skip"),
                recommended_action="mark_unclear",
                evidence=[
                    {
                        "kind": "plan_context",
                        "text": candidate_data["context"],
                    },
                    {
                        "kind": "candidate_support_context",
                        "source_file": match.get("support_source_file"),
                        "source_role": match.get("support_role"),
                        "location": match.get("support_location"),
                        "text": match.get("support_context"),
                    },
                ],
                data=candidate_data
                | {
                    "match_status": "candidate_amount_match",
                    "support_source_file": match.get("support_source_file"),
                    "support_role": match.get("support_role"),
                    "support_location": match.get("support_location"),
                    "support_amount": match.get("support_amount"),
                    "difference": match.get("difference"),
                    "abs_difference": match.get("abs_difference"),
                    "context_token_overlap": match.get("context_token_overlap"),
                    "review_note": (
                        (
                            "Esta es solo una coincidencia mecánica por importe. La persona revisora debe confirmar el rol de la fuente, el contexto y si justifica la afirmación del plan."
                            if _is_spanish(language)
                            else "This is a mechanical amount match only. Reviewer must confirm source role, context, and whether it supports the plan claim."
                        )
                    ),
                },
            )
        )
    if len(unique_plan_candidates) > MAX_PLAN_AMOUNT_ITEMS:
        items.append(
            _base_item(
                "plan-amounts-truncated",
                "source_role_attention",
                (
                    "Importes del plan truncados en el widget"
                    if _is_spanish(language)
                    else "Importi di piano troncati nel widget"
                ),
                output_path="amount_candidates.csv",
                allowed_actions=("accept", "mark_unclear", "skip"),
                recommended_action="mark_unclear",
                data={
                    "shown_count": MAX_PLAN_AMOUNT_ITEMS,
                    "total_count": len(unique_plan_candidates),
                    "full_candidates": "amount_candidates.csv",
                    "full_matches": "exact_amount_matches.csv",
                },
            )
        )
    return items


def _extraction_error_items(
    extraction_errors: Sequence[dict[str, str]],
    language: str,
) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    for index, error in enumerate(
        extraction_errors[:MAX_EXTRACTION_ERROR_ITEMS],
        start=1,
    ):
        source_file = str(
            error.get("source_file")
            or (
                f"Error de extracción {index}"
                if _is_spanish(language)
                else f"Errore estrazione {index}"
            )
        )
        requested_document = (
            f"Archivo de origen legible o copia convertida de {source_file}"
            if _is_spanish(language)
            else f"Readable source file or converted copy for {source_file}"
        )
        reason = str(
            error.get("error")
            or (
                "No se pudo extraer el contenido de este archivo de origen."
                if _is_spanish(language)
                else "Extraction failed for this source file."
            )
        )
        data = dict(error) | {
            "requested_document": requested_document,
            "required_document": requested_document,
            "source_file": source_file,
            "reason": reason,
            "record_id": source_file,
        }
        items.append(
            _base_item(
                f"extraction-error-{index}",
                "extraction_error",
                source_file,
                output_path="run_audit.json",
                allowed_actions=(
                    "edit",
                    "mark_unclear",
                    "request_more_documents",
                    "skip",
                ),
                recommended_action="request_more_documents",
                evidence=[
                    {
                        "kind": "error",
                        "error": error.get("error"),
                        "requested_document": requested_document,
                        "required_document": requested_document,
                        "source_file": source_file,
                        "reason": reason,
                        "record_id": source_file,
                    }
                ],
                data=data,
            )
        )
    return items


def _artifact_items(output_dir: Path, language: str) -> list[dict[str, Any]]:
    spanish = _is_spanish(language)
    artifacts = [
        (
            "semantic-review",
            "review_artifact",
            (
                "Revisión semántica del concordato preventivo"
                if spanish
                else "Revisione semantica del concordato preventivo"
            ),
            "concordato_semantic_review.md",
            "mark_unclear",
        ),
        (
            "concordato-workpaper",
            "review_artifact",
            (
                "Libro de trabajo del concordato preventivo"
                if spanish
                else "Workbook del concordato preventivo"
            ),
            "concordato_review_workpaper.xlsx",
            "mark_unclear",
        ),
        (
            "review-packet",
            "review_artifact",
            (
                "Paquete de inspección y control"
                if spanish
                else "Pacchetto di ispezione e controllo"
            ),
            "review_packet.md",
            "accept",
        ),
        (
            "tie-out-workpaper",
            "review_artifact",
            (
                "Anexo numérico de conciliación"
                if spanish
                else "Appendice numerica di tie-out"
            ),
            "concordato_tie_out_workpaper.xlsx",
            "mark_unclear",
        ),
        (
            "summary-docx",
            "review_artifact",
            (
                "Resumen del concordato preventivo en Word"
                if spanish
                else "Sintesi del concordato preventivo in Word"
            ),
            "concordato_preventivo_review_summary.docx",
            "mark_unclear",
        ),
        (
            "numeric-summary-docx",
            "review_artifact",
            ("Resumen numérico en Word" if spanish else "Appendice numerica in Word"),
            "concordato_review_summary.docx",
            "mark_unclear",
        ),
        (
            "codex-review-memo",
            "codex_review_memo",
            (
                "Memorando de revisión de auditoría de Codex"
                if spanish
                else "Memo di revisione professionale Codex"
            ),
            "codex_run_review.md",
            "mark_unclear",
        ),
    ]
    items: list[dict[str, Any]] = []
    for item_id, item_type, title, relative_path, recommended_action in artifacts:
        path = output_dir / relative_path
        items.append(
            _base_item(
                item_id,
                item_type,
                title,
                output_path=relative_path,
                allowed_actions=("accept", "edit", "mark_unclear", "skip"),
                recommended_action=(
                    recommended_action if path.exists() else "mark_unclear"
                ),
                data={
                    "path": relative_path,
                    "exists": path.exists(),
                    "size_bytes": path.stat().st_size if path.exists() else 0,
                    "review_note": (
                        (
                            "Codex redacta este memorando después de revisar las salidas deterministas y las decisiones de revisión."
                            if spanish
                            else "Codex writes this memo after reviewing the deterministic outputs and any reviewer decisions."
                        )
                        if item_type == "codex_review_memo"
                        else (
                            "Artefacto determinista generado para su revisión."
                            if spanish
                            else "Generated deterministic artifact for review."
                        )
                    ),
                },
            )
        )
    return items


def _output_records(
    output_dir: Path,
    audit: dict[str, Any],
    *,
    inventory: Sequence[dict[str, Any]],
    candidates: Sequence[Any],
    matches: Sequence[dict[str, Any]],
    semantic_status: str,
    semantic_derived: Mapping[str, Any],
) -> list[dict[str, Any]]:
    review_files = {
        "run_intake.json",
        "review_payload.json",
        "ui_decisions.json",
        "final_artifacts.json",
    }
    language_code = _language_code(audit.get("language"))
    packet_required_text = {
        "it": [
            "# Pacchetto di revisione del concordato preventivo",
            "## Revisione professionale richiesta",
            "## Appendice deterministica di tie-out",
        ],
        "es": [
            "# Paquete de revisión del concordato preventivo",
            "## Revisión profesional requerida",
            "## Anexo determinista de conciliación numérica",
        ],
    }.get(
        language_code,
        [
            "# Concordato Preventivo review packet",
            "## Professional review required",
            "## Deterministic numerical tie-out appendix",
        ],
    )
    semantic_required_text = {
        "it": [
            "Revisione del concordato preventivo",
            "Stato del modello semantico",
            "Appendice di tie-out numerico",
        ],
        "en": [
            "Concordato Preventivo Review",
            "Semantic model status",
            "Numerical tie-out appendix",
        ],
        "fr": [
            "Revue du concordato preventivo",
            "Statut du modèle sémantique",
            "Annexe de rapprochement numérique",
        ],
        "de": [
            "Prüfung des Concordato Preventivo",
            "Status des semantischen Modells",
            "Anhang zum Zahlenabgleich",
        ],
        "es": [
            "Revisión del concordato preventivo",
            "Estado del modelo semántico",
            "Anexo de conciliación numérica",
        ],
    }[language_code]
    required_text_by_path = {
        "review_packet.md": packet_required_text,
        "concordato_preventivo_review_summary.docx": semantic_required_text,
        "concordato_review_summary.docx": (
            [
                "Anexo numérico del concordato preventivo",
                "Conclusión operativa",
                "Aspectos que deben explicarse en el memorando de revisión",
                "Archivos analizados",
            ]
            if language_code == "es"
            else [
                "Appendice numerica del concordato preventivo",
                "Conclusione operativa",
                "Da spiegare nel memo del revisore",
            ]
        ),
        "concordato_semantic_review.md": [
            f"#{'#' if index else ''} {text}"
            for index, text in enumerate(semantic_required_text)
        ],
    }
    outputs: list[dict[str, Any]] = []
    for path in sorted(output_dir.rglob("*")):
        if not path.is_file() or path.name in review_files:
            continue
        relative = path.relative_to(output_dir).as_posix()
        output = {
            "path": relative,
            "size_bytes": path.stat().st_size,
            "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
            "kind": path.suffix.lower().lstrip(".") or "file",
            "status": "written",
        }
        if relative == "concordato_tie_out_workpaper.xlsx":
            sheet_names = (
                SPANISH_WORKPAPER_SHEET_NAMES
                if language_code == "es"
                else {name: name for name in WORKPAPER_SHEETS}
            )
            output["required_sheets"] = [sheet_names[name] for name in WORKPAPER_SHEETS]
            required_headers = _workpaper_required_sheet_headers(
                inventory=inventory,
                candidates=candidates,
                matches=matches,
            )
            output["required_sheet_headers"] = {
                sheet_names[name]: headers for name, headers in required_headers.items()
            }
            required_cells = _workpaper_required_cells(
                inventory=inventory,
                candidates=candidates,
                matches=matches,
            )
            if language_code == "es":
                required_cells = {
                    name: {
                        cell: (
                            "No se generaron filas"
                            if value == "No rows generated"
                            else value
                        )
                        for cell, value in cells.items()
                    }
                    for name, cells in required_cells.items()
                }
            output["required_cells"] = {
                sheet_names[name]: cells for name, cells in required_cells.items()
            }
            output["qa_checks"] = [
                "office_zip",
                "workbook_xml",
                "worksheet_xml",
                "required_sheets",
                "required_sheet_headers",
                "required_cells",
            ]
        elif relative == "concordato_review_workpaper.xlsx":
            output["required_sheets"] = [
                "Overview",
                "Documents",
                "Creditors",
                "Classes",
                "Sources Uses",
                "Liquidity",
                "Review Questions",
                "Issues",
                "Mechanical Checks",
                "Numeric Tie-Out",
            ]
            output["required_sheet_headers"] = {
                "Overview": ["metric", "value"],
                "Documents": ["relative_path", "roles", "authoritative_for"],
                "Creditors": ["creditor_id", "creditor_name", "claim_amount"],
                "Classes": ["class_id", "priority", "creditor_count"],
                "Sources Uses": ["item_id", "side", "category"],
                "Liquidity": ["period_id", "period", "opening_cash"],
                "Review Questions": ["question_id", "area", "question"],
                "Issues": ["issue_id", "area", "statement"],
                "Mechanical Checks": ["check_id", "status", "observation"],
                "Numeric Tie-Out": [
                    "plan_source_file",
                    "plan_location",
                    "plan_amount",
                ],
            }
            output["required_cells"] = {
                "Overview": {
                    "A1": "metric",
                    "B1": "value",
                    "A2": "semantic_model_status",
                    "B2": semantic_status,
                }
            }
            output["qa_checks"] = [
                "office_zip",
                "workbook_xml",
                "worksheet_xml",
                "required_sheets",
                "required_sheet_headers",
                "required_cells",
            ]
        elif relative == "exact_amount_matches.csv":
            output["row_count"] = int(audit.get("candidate_match_count", 0))
            output["required_columns"] = [
                "plan_amount",
                "support_amount",
                "difference",
                "match_status",
            ]
        elif relative == "creditor_treatment.csv":
            output["row_count"] = len(semantic_derived.get("creditors") or [])
            output["required_columns"] = [
                "creditor_id",
                "claim_amount",
                "class_id",
                "proposed_total_amount",
                "liquidation_recovery_amount",
            ]
        elif relative == "creditor_class_summary.csv":
            output["row_count"] = len(semantic_derived.get("classes") or [])
            output["required_columns"] = [
                "class_id",
                "priority",
                "claim_amount",
                "proposed_recovery_pct",
            ]
        elif relative == "sources_and_uses.csv":
            output["row_count"] = len(semantic_derived.get("sources_and_uses") or [])
            output["required_columns"] = [
                "item_id",
                "side",
                "category",
                "amount",
            ]
        elif relative == "liquidity_schedule.csv":
            output["row_count"] = len(semantic_derived.get("liquidity") or [])
            output["required_columns"] = [
                "period_id",
                "opening_cash",
                "reported_closing_cash",
                "calculated_closing_cash",
                "bridge_difference",
            ]
        required_text = required_text_by_path.get(relative)
        if required_text:
            output["required_text"] = required_text
            output["qa_checks"] = ["nonempty_text", "required_text"]
        outputs.append(output)
    return outputs


def write_run_intake(
    output_dir: Path,
    input_dir: Path,
    *,
    reference_date: str,
    language: str,
    document_language: str,
    tolerance: object,
    max_rows_per_sheet: int,
    inventory: Sequence[dict[str, Any]],
) -> RunIntakeResult:
    """Write the intake contract once folder scope has been inventoried."""

    run_id = _run_id(input_dir)
    spanish = _is_spanish(language)
    payload = {
        "schema_version": SCHEMA_VERSION,
        "plugin": PLUGIN_NAME,
        "workflow": WORKFLOW_NAME,
        "run_id": run_id,
        "created_at": _utc_now(),
        "language": language,
        "document_language": document_language,
        "input_paths": [input_dir.as_posix()],
        "output_dir": output_dir.as_posix(),
        "inferred_task": "concordato_preventivo_review",
        "assumptions": {
            "reference_date": reference_date,
            "tolerance": decimal_text(_amount(tolerance)),
            "max_rows_per_sheet": max_rows_per_sheet,
            "currency": "EUR",
            "source_role_counts": _role_counts(inventory),
            "file_count": len(inventory),
        },
        "unresolved_questions": [],
        "dependency_check": {
            "status": "not_run_by_script",
            "note": (
                "Codex debe ejecutar scripts/check_dependencies.py antes de los scripts auxiliares."
                if spanish
                else "Codex should run scripts/check_dependencies.py before helper scripts."
            ),
        },
        "data_posture": {
            "local_files_read": [input_dir.as_posix()],
            "external_connectors_used": [],
            "upload_paths_used": [],
            "remote_sql_execution_used": False,
            "hosted_notebook_execution_used": False,
            "notes": [
                (
                    "Los scripts capturan el expediente local, validan un modelo semántico revisado y calculan anexos aritméticos reproducibles."
                    if spanish
                    else "Gli script catturano il fascicolo locale, convalidano un modello semantico riesaminato e calcolano appendici aritmetiche riproducibili."
                ),
                (
                    "De forma predeterminada no se utiliza ningún conector externo, ruta de carga, SQL remoto ni cuaderno alojado."
                    if spanish
                    else "No external connector, upload path, remote SQL, or hosted notebook execution is used by default."
                ),
            ],
        },
        "status": "ready_for_extraction",
    }
    return RunIntakeResult(
        run_id=run_id,
        path=_write_json(output_dir / "run_intake.json", payload),
    )


def write_review_session_artifacts(
    output_dir: Path,
    input_dir: Path,
    *,
    run_id: str,
    run_intake_path: Path,
    reference_date: str,
    language: str,
    document_language: str,
    tolerance: object,
    max_rows_per_sheet: int,
    inventory: Sequence[dict[str, Any]],
    candidates: Sequence[Any],
    matches: Sequence[dict[str, Any]],
    extraction_errors: Sequence[dict[str, str]],
    audit: dict[str, Any],
    semantic_status: str,
    semantic_case_model: Mapping[str, Any] | None,
    semantic_derived: Mapping[str, Any],
    semantic_error: str | None,
) -> ReviewSessionResult:
    """Write review payload, pending decisions, and final artifact index."""

    plan_candidates = _unique_plan_candidates(candidates)
    matched_keys = set(_best_match_by_plan_key(matches))
    unmatched_plan_count = sum(
        1
        for candidate in plan_candidates
        if _candidate_key(candidate) not in matched_keys
    )
    items: list[dict[str, Any]] = []
    items.extend(
        _semantic_items(
            semantic_status=semantic_status,
            case_model=semantic_case_model,
            semantic_derived=semantic_derived,
            semantic_error=semantic_error,
            language=language,
        )
    )
    items.extend(_source_inventory_items(inventory, extraction_errors, language))
    items.extend(_plan_amount_items(candidates, matches, language))
    items.extend(_extraction_error_items(extraction_errors, language))
    items.extend(_artifact_items(output_dir, language))

    review_payload_content = {
        "schema_version": SCHEMA_VERSION,
        "plugin": PLUGIN_NAME,
        "workflow": WORKFLOW_NAME,
        "run_id": run_id,
        "created_at": _utc_now(),
        "language": language,
        "document_language": document_language,
        "source_paths": [input_dir.as_posix()],
        "review_type": "concordato_preventivo_review",
        "items": items,
        "item_count": len(items),
        "columns": _review_columns(language),
        "source_artifacts": {
            "run_intake": _as_output_ref(run_intake_path, output_dir),
            "inventory": "inventory.json",
            "source_pages": "source_pages.json",
            "workbook_sheets": "workbook_sheets.json",
            "amount_candidates": "amount_candidates.csv",
            "exact_amount_matches": "exact_amount_matches.csv",
            "workpaper": "concordato_tie_out_workpaper.xlsx",
            "summary_docx": "concordato_preventivo_review_summary.docx",
            "numeric_summary_docx": "concordato_review_summary.docx",
            "review_packet": "review_packet.md",
            "run_audit": "run_audit.json",
            "assurance_envelope": "assurance_envelope.json",
            "assurance_gates": "assurance_gates.json",
            "source_qualifications": "source_qualifications.json",
            "numeric_evidence_ledger": "numeric_evidence_ledger.json",
            "case_model_template": "suggested_concordato_case_model.json",
            "case_model": "concordato_case_model.json",
            "semantic_checks": "concordato_semantic_checks.json",
            "creditor_treatment": "creditor_treatment.csv",
            "creditor_class_summary": "creditor_class_summary.csv",
            "sources_and_uses": "sources_and_uses.csv",
            "liquidity_schedule": "liquidity_schedule.csv",
            "semantic_workpaper": "concordato_review_workpaper.xlsx",
            "semantic_review": "concordato_semantic_review.md",
            "workflow_output_closure": "workflow_output_closure.json",
        },
        "allowed_actions": [
            "accept",
            "reject",
            "edit",
            "mark_unclear",
            "request_more_documents",
            "skip",
        ],
        "status": (
            "ready_for_review"
            if semantic_status == "reviewed"
            else "semantic_model_required"
        ),
        "assurance": {
            "envelope_path": "assurance_envelope.json",
            "envelope_content_sha256": (
                (audit.get("assurance_envelope") or {}).get("content_sha256")
                if isinstance(audit.get("assurance_envelope"), dict)
                else None
            ),
            "source_qualification_status": audit.get("source_qualification_status"),
            "gate_register": audit.get("assurance_gates"),
            "final_ready": False,
        },
        "summary": {
            "file_count": len(inventory),
            "supported_file_count": audit.get("supported_file_count", 0),
            "source_role_counts": _role_counts(inventory),
            "semantic_model_status": semantic_status,
            "procedure": (
                dict(semantic_case_model["procedure"])
                if semantic_case_model is not None
                else None
            ),
            "semantic_summary": dict(semantic_derived.get("summary") or {}),
            "semantic_check_count": len(semantic_derived.get("checks") or []),
            "semantic_issue_count": (
                len(semantic_case_model["issues"])
                if semantic_case_model is not None
                else 0
            ),
            "creditor_count": len(semantic_derived.get("creditors") or []),
            "creditor_class_count": len(semantic_derived.get("classes") or []),
            "plan_amount_candidate_count": len(plan_candidates),
            "selected_plan_amount_count": min(
                len(plan_candidates),
                MAX_PLAN_AMOUNT_ITEMS,
            ),
            "candidate_match_count": len(matches),
            "matched_plan_amount_count": len(matched_keys),
            "unmatched_plan_amount_count": unmatched_plan_count,
            "extraction_error_count": len(extraction_errors),
            "reference_date": reference_date,
            "language": language,
            "document_language": document_language,
            "tolerance": decimal_text(_amount(tolerance)),
            "max_rows_per_sheet": max_rows_per_sheet,
        },
    }
    review_payload = {
        **review_payload_content,
        "content_sha256": canonical_json_sha256(review_payload_content),
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
            "review_payload_content_sha256": review_payload["content_sha256"],
            "decisions": [],
            "decision_count": 0,
            "status": "pending_review",
        },
    )

    review_handoff_path = _write_review_handoff_card(
        output_dir,
        run_id=run_id,
        title=(
            "Revisión del concordato preventivo"
            if _is_spanish(language)
            else "Concordato Preventivo"
        ),
        validate_tool="validate_concordato_plan_review",
        render_tool="render_concordato_plan_review",
        save_tool="save_concordato_plan_decisions",
        apply_tool="apply_concordato_plan_decisions",
        language=language,
    )
    outputs = _output_records(
        output_dir,
        audit,
        inventory=inventory,
        candidates=candidates,
        matches=matches,
        semantic_status=semantic_status,
        semantic_derived=semantic_derived,
    )
    outputs = [
        output
        for output in outputs
        if not (
            isinstance(output, dict) and output.get("path") == review_handoff_path.name
        )
    ]
    outputs.append(_review_handoff_output_record(review_handoff_path, language))

    spanish = _is_spanish(language)

    final_artifacts_path = _write_json(
        output_dir / "final_artifacts.json",
        {
            "schema_version": SCHEMA_VERSION,
            "plugin": PLUGIN_NAME,
            "workflow": WORKFLOW_NAME,
            "run_id": run_id,
            "completed_at": _utc_now(),
            "review_payload": {
                "path": review_payload_path.name,
                "content_sha256": review_payload["content_sha256"],
            },
            "assurance": review_payload["assurance"],
            "outputs": outputs,
            "caveats": [
                (
                    "El modelo semántico registra juicios profesionales revisados; no es un dictamen jurídico ni una atestación del plan."
                    if spanish
                    else "Il modello semantico registra giudizi professionali riesaminati; non è un parere legale né un'attestazione del piano."
                ),
                (
                    "Las coincidencias exactas por importe son solo evidencias candidatas."
                    if spanish
                    else "Le corrispondenze esatte per importo sono soltanto evidenze candidate."
                ),
                (
                    "ui_decisions.json queda pendiente hasta que Codex, la interfaz MCP o la revisión alternativa registren las decisiones."
                    if spanish
                    else "ui_decisions.json is pending until Codex, MCP UI, or fallback review records decisions."
                ),
            ],
            "next_actions": [
                (
                    "Revise review_payload.json en el widget MCP cuando esté disponible."
                    if spanish
                    else "Review review_payload.json in the MCP widget when available."
                ),
                (
                    "Use las decisiones aceptadas o editadas al redactar codex_run_review.md."
                    if spanish
                    else "Use accepted/edited decisions when writing codex_run_review.md."
                ),
                (
                    "Revise procedimiento, acreedores, tratamiento, liquidez, preguntas y cuestiones antes del anexo numérico."
                    if spanish
                    else "Riesaminare procedura, creditori, trattamento, liquidità, domande e questioni prima dell'appendice numerica."
                ),
            ],
            "status": "written_pending_review",
            "final_ready": False,
        },
    )
    _append_execution_trace(
        run_intake_path,
        final_artifacts_path,
        command=[
            "python",
            "plugins/concordato-plan-review/scripts/run_concordato_review.py",
        ],
    )

    return ReviewSessionResult(
        run_intake_path=run_intake_path,
        review_payload_path=review_payload_path,
        ui_decisions_path=ui_decisions_path,
        final_artifacts_path=final_artifacts_path,
        review_item_count=len(items),
    )
