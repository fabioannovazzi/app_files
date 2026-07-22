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
    "workbook_sheet_name",
    "write_review_session_artifacts",
    "write_run_intake",
]

SCHEMA_VERSION = "1.0"
PLUGIN_NAME = "journal-sampling"
WORKFLOW_NAME = "journal-sampling"
MAX_SAMPLE_ITEMS = 750

_REVIEW_COPY: dict[str, dict[str, Any]] = {
    "en": {
        "product_title": "Journal Sampling",
        "handoff_title": "Review Handoff",
        "run_id": "Run ID",
        "review_payload": "Review payload",
        "run_intake": "Run intake",
        "pending_decisions": "Pending decisions",
        "applied_decisions": "Applied decisions",
        "final_artifacts": "Final artifacts",
        "review_in_codex": "Review In Codex",
        "validate_step": "Validate the payload with `{tool}`.",
        "render_step": "Render the review workbench with `{tool}`.",
        "save_step": "Save reviewer actions with `{tool}`.",
        "apply_step": "Apply reviewer actions with `{tool}`.",
        "handoff_notice": (
            "Persistent save/apply requires the MCP or local-server review "
            "surface. Static HTML fallback can copy or download decision JSON only."
        ),
        "columns": (
            "Type",
            "Entry or artifact",
            "Suggested action",
            "Source",
            "Output",
            "Status",
        ),
        "sampled_entry": "Sampled entry {index}",
        "page": "page",
        "row": "row",
        "sample_control": "{method} sample: {sample_size} of {population}",
        "methods": {
            "random": "random",
            "systematic": "systematic",
            "stratified": "stratified",
            "mus": "monetary-unit",
        },
        "artifact_titles": {
            "csv": "Journal sample CSV",
            "xlsx": "Journal sample workbook",
            "audit": "Sampling audit JSON",
        },
        "workbook_sheet": "Sheet1",
        "dependency_note": (
            "Codex should run scripts/check_dependencies.py before helper scripts."
        ),
        "data_posture_notes": [
            "Sampling scripts read the normalized journal CSV locally and write bounded sample review artifacts.",
            "No external connector, upload path, remote SQL, or hosted notebook execution is used by default.",
        ],
        "caveats": [
            "The deterministic sample is governed by sampling_audit.json; review does not change the sample without rerunning.",
            "The MCP review payload is bounded; use CSV/XLSX/JSON outputs as the complete evidence set.",
            "ui_decisions.json is pending until Codex, the MCP widget, or fallback review records decisions.",
        ],
        "next_actions": [
            "Call validate_journal_sampling_review, then render_journal_sampling_review when MCP is available.",
            "Review sampling parameters, filters, population counts, and sampled entries before delivery.",
            "Change method, size, filters, or mappings and rerun when the sample basis is wrong.",
        ],
    },
    "es": {
        "product_title": "Muestreo del diario",
        "handoff_title": "Entrega para revisión",
        "run_id": "ID de ejecución",
        "review_payload": "Datos de revisión",
        "run_intake": "Datos de ejecución",
        "pending_decisions": "Decisiones pendientes",
        "applied_decisions": "Decisiones aplicadas",
        "final_artifacts": "Artefactos finales",
        "review_in_codex": "Revisión en Codex",
        "validate_step": "Valide los datos con `{tool}`.",
        "render_step": "Abra el área de revisión con `{tool}`.",
        "save_step": "Guarde las decisiones del revisor con `{tool}`.",
        "apply_step": "Aplique las decisiones del revisor con `{tool}`.",
        "handoff_notice": (
            "El guardado y la aplicación persistentes requieren la superficie MCP "
            "o el servidor local. El modo HTML estático solo permite copiar o "
            "descargar el JSON de decisiones."
        ),
        "columns": (
            "Tipo",
            "Asiento o artefacto",
            "Acción sugerida",
            "Fuente",
            "Salida",
            "Estado",
        ),
        "sampled_entry": "Asiento muestreado {index}",
        "page": "página",
        "row": "fila",
        "sample_control": "Muestra {method}: {sample_size} de {population}",
        "methods": {
            "random": "aleatoria",
            "systematic": "sistemática",
            "stratified": "estratificada",
            "mus": "por unidad monetaria",
        },
        "artifact_titles": {
            "csv": "CSV de la muestra del diario",
            "xlsx": "Libro Excel de la muestra del diario",
            "audit": "JSON de auditoría del muestreo",
        },
        "workbook_sheet": "Muestra del diario",
        "dependency_note": (
            "Codex debe ejecutar scripts/check_dependencies.py antes de los scripts auxiliares."
        ),
        "data_posture_notes": [
            "Los scripts de muestreo leen localmente el CSV del diario normalizado y generan artefactos acotados para la revisión de la muestra.",
            "De forma predeterminada no se utilizan conectores externos, rutas de carga, SQL remoto ni cuadernos alojados.",
        ],
        "caveats": [
            "La muestra determinista se rige por sampling_audit.json; la revisión no modifica la muestra sin volver a ejecutar el proceso.",
            "Los datos de revisión MCP están acotados; utilice las salidas CSV, XLSX y JSON como conjunto completo de evidencias.",
            "ui_decisions.json permanece pendiente hasta que Codex, el widget MCP o la revisión alternativa registren las decisiones.",
        ],
        "next_actions": [
            "Ejecute validate_journal_sampling_review y, cuando MCP esté disponible, render_journal_sampling_review.",
            "Revise los parámetros, los filtros, los recuentos de la población y los asientos muestreados antes de la entrega.",
            "Cambie el método, el tamaño, los filtros o las asignaciones y vuelva a ejecutar el proceso si la base de muestreo es incorrecta.",
        ],
    },
}


def _normalize_language(language: object | None) -> str:
    text = str(language or "en").strip().lower().replace("_", "-")
    code = text.split("-", 1)[0]
    return code if code in _REVIEW_COPY else "en"


def _review_copy(language: object | None) -> dict[str, Any]:
    return _REVIEW_COPY[_normalize_language(language)]


def workbook_sheet_name(language: object | None) -> str:
    """Return the localized workbook sheet title for a review language."""

    return str(_review_copy(language)["workbook_sheet"])


@dataclass(frozen=True)
class RunIntakeResult:
    """Run intake artifact written before journal sampling."""

    run_id: str
    path: Path


@dataclass(frozen=True)
class ReviewSessionResult:
    """Review-session artifacts for one journal sampling run."""

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


def _run_id(normalized_csv: Path) -> str:
    timestamp = re.sub(r"[^0-9]", "", _utc_now())
    return f"{PLUGIN_NAME}-{_safe_slug(normalized_csv.stem)}-{timestamp}"


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
    language: str,
    validate_tool: str,
    render_tool: str,
    save_tool: str,
    apply_tool: str,
) -> Path:
    copy = _review_copy(language)
    path = output_dir / "review_handoff.md"
    lines = [
        f"# {copy['product_title']} · {copy['handoff_title']}",
        "<!-- review-contract: Review Handoff -->",
        "",
        f"- {copy['run_id']}: `{run_id}`",
        f"- {copy['review_payload']}: `review_payload.json`",
        f"- {copy['run_intake']}: `run_intake.json`",
        f"- {copy['pending_decisions']}: `ui_decisions.json`",
        f"- {copy['applied_decisions']}: `applied_decisions.json`",
        f"- {copy['final_artifacts']}: `final_artifacts.json`",
        "",
        f"## {copy['review_in_codex']}",
        f"1. {copy['validate_step'].format(tool=validate_tool)}",
        f"2. {copy['render_step'].format(tool=render_tool)}",
        f"3. {copy['save_step'].format(tool=save_tool)}",
        f"4. {copy['apply_step'].format(tool=apply_tool)}",
        "",
        copy["handoff_notice"],
    ]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


def _review_handoff_output_record(path: Path, language: str) -> dict[str, Any]:
    copy = _review_copy(language)
    localized_required_text = (
        [copy["handoff_title"], copy["review_in_codex"]]
        if _normalize_language(language) == "es"
        else []
    )
    return {
        "path": path.name,
        "kind": "md",
        "status": "written",
        "required_text": [
            "Review Handoff",
            *localized_required_text,
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


def _review_columns(language: str) -> list[dict[str, str]]:
    labels = _review_copy(language)["columns"]
    fields = (
        "item_type",
        "title",
        "recommended_action",
        "source_path",
        "output_path",
        "status",
    )
    return [
        {"field": field, "label": str(label)}
        for field, label in zip(fields, labels, strict=True)
    ]


def _entry_title(row: dict[str, Any], index: int, language: str) -> str:
    parts = [
        _clean_text(row.get("entry_date")),
        _clean_text(row.get("movement_number") or row.get("line_number")),
        _clean_text(row.get("account")),
        _clean_text(row.get("amount_signed") or row.get("amount_abs")),
        _clean_text(row.get("line_desc") or row.get("account_desc")),
    ]
    return " | ".join(part for part in parts if part) or str(
        _review_copy(language)["sampled_entry"]
    ).format(index=index)


def _sample_items(
    sample_rows: Sequence[dict[str, Any]], language: str
) -> list[dict[str, Any]]:
    copy = _review_copy(language)
    return [
        _base_item(
            f"sampled-entry-{index}",
            "sampled_entry",
            _entry_title(row, index, language),
            source_path="; ".join(
                part
                for part in (
                    _clean_text(row.get("source_file")),
                    (
                        f"{copy['page']} {_clean_text(row.get('source_page'))}"
                        if _clean_text(row.get("source_page"))
                        else ""
                    ),
                    (
                        f"{copy['row']} {_clean_text(row.get('source_row'))}"
                        if _clean_text(row.get("source_row"))
                        else ""
                    ),
                )
                if part
            )
            or None,
            output_path="journal_sample.csv",
            allowed_actions=("accept", "edit", "mark_unclear", "skip"),
            recommended_action="accept",
            evidence=[
                {
                    "kind": "sampled_entry",
                    "account": row.get("account"),
                    "amount_abs": row.get("amount_abs"),
                    "movement_number": row.get("movement_number"),
                    "source_file": row.get("source_file"),
                    "source_row": row.get("source_row"),
                }
            ],
            data=dict(row),
        )
        for index, row in enumerate(sample_rows[:MAX_SAMPLE_ITEMS], start=1)
    ]


def _control_items(audit: dict[str, Any], language: str) -> list[dict[str, Any]]:
    copy = _review_copy(language)
    sample_size = int(audit.get("sample_size") or 0)
    requested = int(audit.get("requested_size") or 0)
    population = int(audit.get("population_size_after_filters") or 0)
    action = "accept"
    if population == 0 or sample_size < min(requested, population):
        action = "mark_unclear"
    method = str(audit.get("method") or "sample")
    method_label = copy["methods"].get(method, method)
    return [
        _base_item(
            "sampling-control",
            "sampling_control",
            str(copy["sample_control"]).format(
                method=method_label,
                sample_size=sample_size,
                population=population,
            ),
            output_path="sampling_audit.json",
            allowed_actions=("accept", "edit", "mark_unclear", "skip"),
            recommended_action=action,
            evidence=[
                {
                    "kind": "sampling_parameters",
                    "method": audit.get("method"),
                    "seed": audit.get("seed"),
                    "requested_size": requested,
                    "population_size_after_filters": population,
                    "filters": audit.get("filters"),
                }
            ],
            data={
                "method": audit.get("method"),
                "requested_size": requested,
                "sample_size": sample_size,
                "population_size_after_filters": population,
                "filters": audit.get("filters"),
            },
        )
    ]


def _artifact_items(
    audit: dict[str, Any], output_dir: Path, language: str
) -> list[dict[str, Any]]:
    outputs = audit.get("outputs") if isinstance(audit.get("outputs"), dict) else {}
    titles = _review_copy(language)["artifact_titles"]
    labels = {
        "csv": ("sample_artifact", titles["csv"]),
        "xlsx": ("sample_artifact", titles["xlsx"]),
        "audit": ("review_artifact", titles["audit"]),
    }
    outputs = {**outputs, "audit": (output_dir / "sampling_audit.json").as_posix()}
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


SAMPLE_TABLE_COLUMNS = [
    "entry_date",
    "movement_number",
    "line_number",
    "account",
    "account_desc",
    "line_desc",
    "debit",
    "credit",
    "amount_signed",
    "amount_abs",
    "source_file",
    "source_sheet",
    "source_page",
    "source_row",
]
SAMPLE_REQUIRED_COLUMNS = [
    "entry_date",
    "account",
    "account_desc",
    "line_desc",
    "amount_abs",
    "source_file",
    "source_row",
]


def _column_letters(index: int) -> str:
    letters = ""
    while index > 0:
        index, remainder = divmod(index - 1, 26)
        letters = chr(65 + remainder) + letters
    return letters


def _cell_reference(field: str, row: int) -> str:
    return f"{_column_letters(SAMPLE_TABLE_COLUMNS.index(field) + 1)}{row}"


def _add_cell_check(cells: dict[str, str], reference: str, value: object) -> None:
    text = _clean_text(value)
    if text:
        cells[reference] = text


def _sample_required_text(sample_rows: Sequence[dict[str, Any]]) -> list[str]:
    fragments = SAMPLE_REQUIRED_COLUMNS.copy()
    if sample_rows and isinstance(sample_rows[0], dict):
        first_row = sample_rows[0]
        for field in [
            "entry_date",
            "account",
            "account_desc",
            "line_desc",
            "source_file",
        ]:
            value = _clean_text(first_row.get(field))
            if value:
                fragments.append(value)
    return list(dict.fromkeys(fragments))


def _sample_required_cells(
    sample_rows: Sequence[dict[str, Any]], language: str
) -> dict[str, dict[str, str]]:
    cells: dict[str, str] = {}
    fields = [
        "entry_date",
        "account",
        "account_desc",
        "line_desc",
        "source_file",
        "source_row",
    ]
    for field in fields:
        cells[_cell_reference(field, 1)] = field
    if sample_rows and isinstance(sample_rows[0], dict):
        first_row = sample_rows[0]
        for field in fields:
            _add_cell_check(cells, _cell_reference(field, 2), first_row.get(field))
    return {workbook_sheet_name(language): cells}


def _output_records(
    output_dir: Path,
    audit: dict[str, Any],
    sample_rows: Sequence[dict[str, Any]],
    language: str,
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
        if relative == "journal_sample.csv":
            output["row_count"] = int(audit.get("sample_size", 0))
            output["required_columns"] = SAMPLE_REQUIRED_COLUMNS
            output["required_text"] = _sample_required_text(sample_rows)
            output["qa_checks"] = [
                "csv_parse",
                "row_count",
                "required_columns",
                "required_text",
            ]
        elif relative == "journal_sample.xlsx":
            sheet_name = workbook_sheet_name(language)
            output["source_row_count"] = int(audit.get("sample_size", 0))
            output["required_sheets"] = [sheet_name]
            output["required_sheet_headers"] = {sheet_name: SAMPLE_REQUIRED_COLUMNS}
            output["required_cells"] = _sample_required_cells(sample_rows, language)
            output["qa_checks"] = [
                "office_zip",
                "workbook_xml",
                "required_sheets",
                "required_sheet_headers",
                "required_cells",
            ]
        outputs.append(output)
    return outputs


def write_run_intake(
    output_dir: Path,
    *,
    normalized_csv: Path,
    method: str,
    size: int,
    group_column: str,
    include_accounts: Sequence[str],
    exclude_accounts: Sequence[str],
    date_start: str | None,
    date_end: str | None,
    min_abs: float | None,
    keyword: str | None,
    language: str,
) -> RunIntakeResult:
    """Write run intake before deterministic sample selection."""

    language_code = _normalize_language(language)
    copy = _review_copy(language_code)
    run_id = _run_id(normalized_csv)
    payload = {
        "schema_version": SCHEMA_VERSION,
        "plugin": PLUGIN_NAME,
        "workflow": WORKFLOW_NAME,
        "run_id": run_id,
        "created_at": _utc_now(),
        "language": language_code,
        "input_paths": [normalized_csv.as_posix()],
        "output_dir": output_dir.as_posix(),
        "inferred_task": "journal_sampling_review_payload",
        "assumptions": {
            "normalized_csv": normalized_csv.as_posix(),
            "method": method,
            "requested_size": size,
            "seed": 42 if method.strip().lower() == "random" else None,
            "group_column": group_column,
            "include_accounts": list(include_accounts),
            "exclude_accounts": list(exclude_accounts),
            "date_start": date_start,
            "date_end": date_end,
            "min_abs": min_abs,
            "keyword": keyword,
            "language": language_code,
            "currency": "EUR",
        },
        "unresolved_questions": [],
        "dependency_check": {
            "status": "not_run_by_script",
            "note": copy["dependency_note"],
        },
        "data_posture": {
            "local_files_read": [normalized_csv.as_posix()],
            "external_connectors_used": [],
            "upload_paths_used": [],
            "remote_sql_execution_used": False,
            "hosted_notebook_execution_used": False,
            "notes": list(copy["data_posture_notes"]),
        },
        "status": "ready_for_sampling_run",
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
    sample: Any,
    audit: dict[str, Any],
) -> ReviewSessionResult:
    """Write review payload, pending decisions, and final artifact inventory."""

    language = _normalize_language(audit.get("language"))
    copy = _review_copy(language)
    sample_rows = _rows(sample)
    items: list[dict[str, Any]] = []
    items.extend(_control_items(audit, language))
    items.extend(_sample_items(sample_rows, language))
    items.extend(_artifact_items(audit, output_dir, language))

    review_payload = {
        "schema_version": SCHEMA_VERSION,
        "plugin": PLUGIN_NAME,
        "workflow": WORKFLOW_NAME,
        "run_id": run_id,
        "created_at": _utc_now(),
        "language": language,
        "source_paths": [audit.get("normalized_csv")],
        "review_type": "journal_sampling_review",
        "items": items,
        "item_count": len(items),
        "columns": _review_columns(language),
        "source_artifacts": {
            "run_intake": _as_output_ref(run_intake_path, output_dir),
            "sampling_audit": "sampling_audit.json",
            "journal_sample_csv": "journal_sample.csv",
            "journal_sample_xlsx": _as_output_ref(
                (
                    (audit.get("outputs") or {}).get("xlsx")
                    if isinstance(audit.get("outputs"), dict)
                    else None
                ),
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
            "method": audit.get("method"),
            "seed": audit.get("seed"),
            "requested_size": audit.get("requested_size"),
            "population_size_before_filters": audit.get(
                "population_size_before_filters"
            ),
            "population_size_after_filters": audit.get("population_size_after_filters"),
            "sample_size": audit.get("sample_size", len(sample_rows)),
            "filters": audit.get("filters", {}),
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
        language=language,
        validate_tool="validate_journal_sampling_review",
        render_tool="render_journal_sampling_review",
        save_tool="save_journal_sampling_decisions",
        apply_tool="apply_journal_sampling_decisions",
    )
    outputs = _output_records(output_dir, audit, sample_rows, language)
    outputs = [
        output
        for output in outputs
        if not (
            isinstance(output, dict) and output.get("path") == review_handoff_path.name
        )
    ]
    outputs.append(_review_handoff_output_record(review_handoff_path, language))

    final_artifacts_path = _write_json(
        output_dir / "final_artifacts.json",
        {
            "schema_version": SCHEMA_VERSION,
            "plugin": PLUGIN_NAME,
            "workflow": WORKFLOW_NAME,
            "run_id": run_id,
            "completed_at": _utc_now(),
            "outputs": outputs,
            "caveats": list(copy["caveats"]),
            "next_actions": list(copy["next_actions"]),
            "status": "written_pending_review",
        },
    )
    _append_execution_trace(
        run_intake_path,
        final_artifacts_path,
        command=["python", "plugins/journal-sampling/scripts/run_sample.py"],
    )

    return ReviewSessionResult(
        run_id=run_id,
        run_intake_path=run_intake_path,
        review_payload_path=review_payload_path,
        ui_decisions_path=ui_decisions_path,
        final_artifacts_path=final_artifacts_path,
        review_item_count=len(items),
    )
