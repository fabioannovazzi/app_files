from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Sequence

try:
    from .report_gates import build_report_assurance_state
except ImportError:  # pragma: no cover - supports direct script imports
    from report_gates import build_report_assurance_state

__all__ = [
    "ReviewSessionResult",
    "RunIntakeResult",
    "build_output_records",
    "refresh_final_artifacts",
    "refresh_review_payload",
    "write_review_session_artifacts",
    "write_run_intake",
]

SCHEMA_VERSION = "1.0"
PLUGIN_NAME = "report-builder"
WORKFLOW_NAME = "report-builder"

DOCX_REQUIRED_TEXT: dict[str, dict[str, str]] = {
    "executive_summary": {
        "en": "Executive summary",
        "it": "Sintesi",
        "fr": "Synthese",
        "de": "Zusammenfassung",
        "es": "Resumen ejecutivo",
    },
    "audit_appendix": {
        "en": "Audit appendix",
        "it": "Appendice audit",
        "fr": "Annexe d'audit",
        "de": "Audit-Anhang",
        "es": "Anexo de auditoría",
    },
    "report_status": {
        "en": "Report status",
        "it": "Stato report",
        "fr": "Statut du rapport",
        "de": "Berichtsstatus",
        "es": "Estado del informe",
    },
    "model_api_calls": {
        "en": "Model API calls from scripts",
        "it": "Chiamate API modello dagli script",
        "fr": "Appels API modele par les scripts",
        "de": "Modell-API-Aufrufe aus Skripten",
        "es": "Llamadas a la API del modelo desde los scripts",
    },
    "assigned_sections": {
        "en": "Assigned sections",
        "it": "Sezioni assegnate",
        "fr": "Sections assignees",
        "de": "Zugeordnete Abschnitte",
        "es": "Secciones asignadas",
    },
    "missing_sections": {
        "en": "Missing sections",
        "it": "Sezioni mancanti",
        "fr": "Sections manquantes",
        "de": "Fehlende Abschnitte",
        "es": "Secciones pendientes",
    },
    "source": {
        "en": "Source",
        "it": "Fonte",
        "fr": "Source",
        "de": "Quelle",
        "es": "Fuente",
    },
    "rows": {
        "en": "Rows",
        "it": "Righe",
        "fr": "Lignes",
        "de": "Zeilen",
        "es": "Filas",
    },
    "input_path": {
        "en": "Input path",
        "it": "Percorso di input",
        "fr": "Chemin d'entree",
        "de": "Eingabepfad",
        "es": "Ruta de entrada",
    },
    "tables_discovered": {
        "en": "Tables discovered",
        "it": "Tabelle rilevate",
        "fr": "Tableaux detectes",
        "de": "Erkannte Tabellen",
        "es": "Tablas detectadas",
    },
}

REPORT_TABLES_SUMMARY_SHEET = "summary"
REPORT_TABLES_SUMMARY_HEADERS = [
    "section",
    "status",
    "assigned_table",
    "rows",
    "columns",
]
REPORT_TABLES_PREVIEW_CELL_COLUMN_LIMIT = 4
ALLOWED_REPORT_OUTPUTS = (
    "report_tables.json",
    "report_tables.xlsx",
    "report_analysis.json",
    "report_draft.md",
    "report.docx",
    "report_audit.json",
    "used_recipe.json",
    "numeric_evidence_ledger.json",
    "source_receipts.json",
    "review_handoff.md",
)


@dataclass(frozen=True)
class RunIntakeResult:
    """Run intake artifact written before deterministic report build."""

    run_id: str
    path: Path


@dataclass(frozen=True)
class ReviewSessionResult:
    """Review-session artifacts for one report-builder run."""

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


def _run_id(input_path: Path) -> str:
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S%f")
    return f"{PLUGIN_NAME}-{_safe_slug(input_path.stem)}-{timestamp}"


def _write_json(path: Path, payload: dict[str, Any]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, default=str) + "\n",
        encoding="utf-8",
    )
    return path


def _canonical_json_sha256(payload: dict[str, Any]) -> str:
    """Bind mutable review state to the exact current review payload."""

    encoded = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


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


def _is_spanish(language: object) -> bool:
    return (
        str(language or "").strip().lower().replace("_", "-").split("-", 1)[0] == "es"
    )


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
            {"field": "title", "label": "Elemento del informe"},
            {"field": "recommended_action", "label": "Acción sugerida"},
            {"field": "source_path", "label": "Fuente"},
            {"field": "output_path", "label": "Salida"},
            {"field": "status", "label": "Estado"},
        ]
    return [
        {"field": "item_type", "label": "Type"},
        {"field": "title", "label": "Report item"},
        {"field": "recommended_action", "label": "Suggested action"},
        {"field": "source_path", "label": "Source"},
        {"field": "output_path", "label": "Output"},
        {"field": "status", "label": "Status"},
    ]


def _section_items(analysis: dict[str, Any], language: str) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    for index, section in enumerate(analysis.get("sections", []), start=1):
        if not isinstance(section, dict):
            continue
        section_key = _clean_text(section.get("section")) or f"section-{index}"
        status = _clean_text(section.get("status")) or "unknown"
        has_comment = bool(_clean_text(section.get("codex_comment")))
        recommended_action = (
            "accept" if status == "assigned" and has_comment else "edit"
        )
        if status != "assigned":
            recommended_action = "mark_unclear"
        title = _clean_text(section.get("title")) or section_key
        if _is_spanish(language):
            display_status = {
                "assigned": "asignada",
                "unassigned": "sin asignar",
            }.get(status, status)
        else:
            display_status = status
        source_parts = [
            _clean_text(section.get("source_file")),
            _clean_text(section.get("sheet_name")),
            _clean_text(section.get("assigned_table")),
        ]
        items.append(
            _base_item(
                f"report-section-{index}",
                "report_section",
                f"{title} ({display_status})",
                source_path=" / ".join(part for part in source_parts if part) or None,
                output_path="report_draft.md",
                allowed_actions=(
                    "accept",
                    "edit",
                    "mark_unclear",
                    "request_more_documents",
                    "skip",
                ),
                recommended_action=recommended_action,
                evidence=[
                    {
                        "kind": "section_status",
                        "section": section_key,
                        "status": status,
                        "row_count": section.get("row_count", 0),
                        "column_count": section.get("column_count", 0),
                        "numeric_measure_candidate_count": len(
                            section.get("numeric_measure_candidates", []) or []
                        ),
                        "numeric_measure_status": section.get("numeric_measure_status"),
                        "has_codex_comment": has_comment,
                    }
                ],
                data={
                    "section": section_key,
                    "title": title,
                    "status": status,
                    "target_artifact": "report.docx",
                    "target_path": f"sections.{section_key}.codex_comment",
                    "target_field": "codex_comment",
                    "assigned_table": section.get("assigned_table"),
                    "source_file": section.get("source_file"),
                    "sheet_name": section.get("sheet_name"),
                    "row_count": section.get("row_count", 0),
                    "column_count": section.get("column_count", 0),
                    "numeric_columns": (section.get("numeric_columns") or [])[:8],
                    "numeric_measure_candidates": (
                        section.get("numeric_measure_candidates") or []
                    )[:12],
                    "numeric_measure_status": section.get("numeric_measure_status"),
                    "numeric_measure_limitation": section.get(
                        "numeric_measure_limitation"
                    ),
                    "preview_rows": (section.get("preview_rows") or [])[:5],
                    "codex_comment": section.get("codex_comment", ""),
                },
            )
        )
    return items


def _table_evidence_items(
    analysis: dict[str, Any],
    tables: Sequence[dict[str, Any]] = (),
    *,
    language: str,
) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    available_table_ids = [
        _clean_text(table.get("table_id"))
        for table in tables
        if isinstance(table, dict) and _clean_text(table.get("table_id"))
    ]
    if not available_table_ids:
        available_table_ids = [
            _clean_text(section.get("assigned_table"))
            for section in analysis.get("sections", [])
            if isinstance(section, dict) and _clean_text(section.get("assigned_table"))
        ]
    available_table_ids = list(dict.fromkeys(available_table_ids))
    for index, section in enumerate(analysis.get("sections", []), start=1):
        if not isinstance(section, dict) or section.get("status") != "assigned":
            continue
        table_id = _clean_text(section.get("assigned_table"))
        if not table_id:
            continue
        section_key = _clean_text(section.get("section"))
        title = _clean_text(section.get("title")) or _clean_text(section.get("section"))
        requested_document = (
            f"Tabla de origen alternativa o anexo justificativo para la sección {section_key} del informe"
            if _is_spanish(language)
            else f"Alternative source table or support schedule for report section {section_key}"
        )
        items.append(
            _base_item(
                f"table-evidence-{index}",
                "table_evidence",
                (
                    f"Tabla de evidencias para {title}"
                    if _is_spanish(language)
                    else f"Evidence table for {title}"
                ),
                source_path=table_id,
                output_path="report_tables.json",
                allowed_actions=(
                    "accept",
                    "edit",
                    "mark_unclear",
                    "request_more_documents",
                    "skip",
                ),
                recommended_action="accept",
                evidence=[
                    {
                        "kind": "table_evidence",
                        "section": section_key,
                        "table_id": table_id,
                        "source_file": section.get("source_file"),
                        "sheet_name": section.get("sheet_name"),
                        "row_count": section.get("row_count", 0),
                        "column_count": section.get("column_count", 0),
                        "preview_rows": (section.get("preview_rows") or [])[:3],
                    }
                ],
                data={
                    "section": section_key,
                    "table_id": table_id,
                    "target_artifact": "report.docx",
                    "target_path": f"sections.{section_key}.assigned_table",
                    "target_field": "assigned_table",
                    "edit_value_hint": (
                        "Use un table_id exacto de available_table_ids."
                        if _is_spanish(language)
                        else "Use one exact table_id from available_table_ids."
                    ),
                    "available_table_ids": available_table_ids,
                    "requested_document": requested_document,
                    "required_document": requested_document,
                    "source_file": section.get("source_file"),
                    "source_table": section.get("sheet_name") or table_id,
                    "record_id": section_key,
                    "reason": (
                        "La persona revisora marcó la tabla de origen asignada como poco clara o insuficiente."
                        if _is_spanish(language)
                        else "Reviewer marked the mapped source table as unclear or insufficient."
                    ),
                    "numeric_columns": (section.get("numeric_columns") or [])[:8],
                    "numeric_measure_candidates": (
                        section.get("numeric_measure_candidates") or []
                    )[:12],
                    "numeric_measure_status": section.get("numeric_measure_status"),
                    "preview_rows": (section.get("preview_rows") or [])[:5],
                },
            )
        )
    return items


def _source_qualification_failure_items(
    tables: Sequence[dict[str, Any]],
    *,
    language: str,
) -> list[dict[str, Any]]:
    """Return non-dismissible blockers for unreadable or unsupported sources."""

    failures = [
        table
        for table in tables
        if isinstance(table, dict)
        and (
            _clean_text(table.get("kind")) == "error"
            or bool(_clean_text(table.get("error")))
            or int(table.get("row_count") or 0) == 0
        )
    ]
    items: list[dict[str, Any]] = []
    for index, table in enumerate(failures, start=1):
        source_file = _clean_text(table.get("source_file")) or f"source-{index}"
        reason = (
            _clean_text(table.get("error")) or "Source contains no reportable rows."
        )
        requested_document = (
            f"Una versione leggibile o OCR verificato di {source_file}"
            if _clean_text(language) == "it"
            else f"A readable export or verified OCR version of {source_file}"
        )
        items.append(
            _base_item(
                f"source-qualification-failure-{index}",
                "review_issue",
                f"Unsupported report source: {source_file}",
                source_path=source_file,
                output_path="report_tables.json",
                allowed_actions=("mark_unclear", "request_more_documents"),
                recommended_action="request_more_documents",
                evidence=[
                    {
                        "kind": "source_qualification_failure",
                        "source_file": source_file,
                        "status": "unsupported_source_layout",
                        "reason": reason,
                    }
                ],
                data={
                    "source_file": source_file,
                    "reason": reason,
                    "requested_document": requested_document,
                    "required_document": requested_document,
                    "source_table": source_file,
                    "record_id": source_file,
                },
            )
        )
    return items


def _issue_items(
    analysis: dict[str, Any], audit: dict[str, Any], language: str
) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    missing_sections = audit.get("missing_sections") or []
    if isinstance(missing_sections, list):
        for index, section_key in enumerate(missing_sections, start=1):
            section_label = _clean_text(section_key) or f"section-{index}"
            requested_document = (
                f"Tabla de origen o soporte narrativo para la sección {section_label} del informe"
                if _is_spanish(language)
                else f"Source table or narrative support for report section {section_label}"
            )
            followup_context = {
                "section": section_label,
                "requested_document": requested_document,
                "required_document": requested_document,
                "reason": (
                    "No hay ninguna tabla de origen determinista asignada a esta sección del informe."
                    if _is_spanish(language)
                    else "No deterministic source table is mapped to this report section."
                ),
                "source_table": "unassigned",
                "record_id": section_label,
                "period": analysis.get("period"),
                "entity": analysis.get("entity"),
            }
            followup_context = {
                key: value
                for key, value in followup_context.items()
                if _clean_text(value)
            }
            items.append(
                _base_item(
                    f"missing-section-{index}",
                    "review_issue",
                    (
                        f"Falta la asignación de la sección: {section_label}"
                        if _is_spanish(language)
                        else f"Missing section mapping: {section_label}"
                    ),
                    output_path="used_recipe.json",
                    allowed_actions=(
                        "mark_unclear",
                        "request_more_documents",
                        "skip",
                    ),
                    recommended_action="mark_unclear",
                    evidence=[
                        {
                            "kind": "missing_section",
                            "section": section_key,
                            "missing_section_count": audit.get(
                                "missing_section_count", 0
                            ),
                            "requested_document": requested_document,
                            "required_document": requested_document,
                            "reason": followup_context["reason"],
                            "source_table": followup_context["source_table"],
                            "record_id": section_label,
                            "period": followup_context.get("period"),
                            "entity": followup_context.get("entity"),
                        }
                    ],
                    data=followup_context,
                )
            )

    narrative_gaps = [
        section
        for section in analysis.get("sections", [])
        if isinstance(section, dict)
        and section.get("status") == "assigned"
        and not _clean_text(section.get("codex_comment"))
    ]
    for index, section in enumerate(narrative_gaps, start=1):
        title = _clean_text(section.get("title")) or _clean_text(section.get("section"))
        items.append(
            _base_item(
                f"narrative-gap-{index}",
                "review_issue",
                (
                    f"Narrativa pendiente: {title}"
                    if _is_spanish(language)
                    else f"Narrative pending: {title}"
                ),
                output_path="used_recipe.json",
                allowed_actions=("edit", "mark_unclear", "skip"),
                recommended_action="edit",
                evidence=[
                    {
                        "kind": "narrative_gap",
                        "section": section.get("section"),
                        "assigned_table": section.get("assigned_table"),
                    }
                ],
                data={
                    "section": section.get("section"),
                    "target_artifact": "report.docx",
                    "target_path": (
                        f"sections.{_clean_text(section.get('section'))}.codex_comment"
                    ),
                    "target_field": "codex_comment",
                    "assigned_table": section.get("assigned_table"),
                },
            )
        )
    numeric_pending = [
        section
        for section in analysis.get("sections", [])
        if isinstance(section, dict)
        and section.get("numeric_measure_status") == "needs_review"
    ]
    for index, section in enumerate(numeric_pending, start=1):
        section_key = _clean_text(section.get("section")) or f"section-{index}"
        items.append(
            _base_item(
                f"numeric-measure-review-{index}",
                "review_issue",
                (
                    f"Revisión de medidas numéricas pendiente: {section_key}"
                    if _is_spanish(language)
                    else f"Numeric measure review pending: {section_key}"
                ),
                output_path="used_recipe.json",
                allowed_actions=("mark_unclear", "request_more_documents", "skip"),
                recommended_action="mark_unclear",
                evidence=[
                    {
                        "kind": "numeric_measure_review_pending",
                        "section": section_key,
                        "candidate_count": len(
                            section.get("numeric_measure_candidates") or []
                        ),
                    }
                ],
                data={
                    "section": section_key,
                    "reason": (
                        "Las columnas numéricas candidatas no tienen un contrato semántico revisado y vinculado a la fuente."
                        if _is_spanish(language)
                        else "Candidate numeric columns do not have a reviewed, source-bound semantic contract."
                    ),
                    "source_table": section.get("assigned_table"),
                    "record_id": section_key,
                },
            )
        )
    return items


def _artifact_items(
    paths: dict[str, Path], output_dir: Path, language: str
) -> list[dict[str, Any]]:
    spanish = _is_spanish(language)
    labels = {
        "report_draft": (
            "report_artifact",
            "Borrador del informe en Markdown" if spanish else "Markdown report draft",
        ),
        "report_docx": (
            "report_artifact",
            "Informe de Word" if spanish else "Word report",
        ),
        "report_analysis": (
            "report_artifact",
            "JSON de análisis del informe" if spanish else "Report analysis JSON",
        ),
        "report_audit": (
            "report_artifact",
            "JSON de auditoría del informe" if spanish else "Report audit JSON",
        ),
        "report_tables": (
            "report_artifact",
            "JSON de tablas del informe" if spanish else "Report tables JSON",
        ),
        "report_tables_xlsx": (
            "report_artifact",
            "Libro de tablas del informe" if spanish else "Report tables workbook",
        ),
        "used_recipe": (
            "report_artifact",
            "JSON de la receta utilizada" if spanish else "Used recipe JSON",
        ),
        "numeric_evidence": (
            "report_artifact",
            (
                "Libro mayor de evidencia numérica"
                if spanish
                else "Numeric evidence ledger"
            ),
        ),
        "source_receipts": (
            "report_artifact",
            ("Recibos de fuentes numéricas" if spanish else "Numeric source receipts"),
        ),
    }
    items: list[dict[str, Any]] = []
    for index, (field, (item_type, title)) in enumerate(labels.items(), start=1):
        path_value = paths.get(field)
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
                allowed_actions=("accept", "mark_unclear", "skip"),
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


def _localized_docx_text(key: str, language: str) -> str:
    labels = DOCX_REQUIRED_TEXT.get(key, {})
    return labels.get(language) or labels.get("en") or key.replace("_", " ").title()


def _section_titles(analysis: dict[str, Any], limit: int = 6) -> list[str]:
    titles: list[str] = []
    for section in analysis.get("sections", []):
        if not isinstance(section, dict):
            continue
        title = _clean_text(section.get("title"))
        if title:
            titles.append(title)
        if len(titles) >= limit:
            break
    return titles


def _report_docx_required_text(
    analysis: dict[str, Any], audit: dict[str, Any]
) -> list[str]:
    language = _clean_text(analysis.get("language")) or "en"
    keys = [
        "executive_summary",
        "audit_appendix",
        "report_status",
        "model_api_calls",
        "assigned_sections",
        "input_path",
        "tables_discovered",
    ]
    if int(audit.get("missing_section_count") or 0) > 0:
        keys.append("missing_sections")
    required = [_localized_docx_text(key, language) for key in keys]
    required.extend(_section_titles(analysis))
    return required


def _report_markdown_required_text(analysis: dict[str, Any]) -> list[str]:
    language = _clean_text(analysis.get("language")) or "en"
    required = [f"## {_localized_docx_text('executive_summary', language)}"]
    required.extend(f"## {title}" for title in _section_titles(analysis))
    if any(
        isinstance(section, dict) and section.get("status") == "assigned"
        for section in analysis.get("sections", [])
    ):
        required.extend(
            [
                f"{_localized_docx_text('source', language)}:",
                f"{_localized_docx_text('rows', language)}:",
            ]
        )
    return required


def _cell_text(value: Any) -> str:
    if value is None:
        return ""
    return " ".join(str(value).strip().split())


def _safe_sheet_name(name: str, fallback: str) -> str:
    cleaned = re.sub(r"[\[\]:*?/\\]", " ", name).strip() or fallback
    return cleaned[:31]


def _excel_column_name(index: int) -> str:
    name = ""
    while index > 0:
        index, remainder = divmod(index - 1, 26)
        name = chr(65 + remainder) + name
    return name


def _selected_preview_section(analysis: dict[str, Any]) -> dict[str, Any] | None:
    for section in analysis.get("sections", []):
        if not isinstance(section, dict):
            continue
        if not _clean_text(section.get("assigned_table")):
            continue
        rows = section.get("preview_rows")
        if isinstance(rows, list) and rows and isinstance(rows[0], dict):
            return section
    return None


def _report_tables_preview_sheet_name(section: dict[str, Any]) -> str:
    section_name = _clean_text(section.get("section"))
    return _safe_sheet_name(section_name, "section1")


def _report_tables_preview_headers(
    analysis: dict[str, Any],
) -> dict[str, list[str]]:
    section = _selected_preview_section(analysis)
    if section is None:
        return {}
    rows = section.get("preview_rows") or []
    headers = list(rows[0].keys()) if rows and isinstance(rows[0], dict) else []
    if not headers:
        return {}
    return {_report_tables_preview_sheet_name(section): headers}


def _report_tables_preview_cells(
    analysis: dict[str, Any],
) -> dict[str, dict[str, str]]:
    section = _selected_preview_section(analysis)
    if section is None:
        return {}
    rows = section.get("preview_rows") or []
    if not rows or not isinstance(rows[0], dict):
        return {}
    headers = list(rows[0].keys())[:REPORT_TABLES_PREVIEW_CELL_COLUMN_LIMIT]
    first_row = rows[0]
    cells: dict[str, str] = {}
    for index, header in enumerate(headers, start=1):
        column = _excel_column_name(index)
        header_text = _cell_text(header)
        value_text = _cell_text(first_row.get(header))
        if header_text:
            cells[f"{column}1"] = header_text
        if value_text:
            cells[f"{column}2"] = value_text
    return {_report_tables_preview_sheet_name(section): cells} if cells else {}


def _report_tables_required_cells(
    analysis: dict[str, Any],
) -> dict[str, dict[str, str]]:
    cells: dict[str, str] = {}
    sections = [
        (index, section)
        for index, section in enumerate(analysis.get("sections", []), start=2)
        if isinstance(section, dict)
    ]
    selected = next(
        (
            (index, section)
            for index, section in sections
            if _clean_text(section.get("assigned_table"))
        ),
        sections[0] if sections else None,
    )
    if not selected:
        return {}
    row_number, first_section = selected
    for cell_ref, value in {
        f"A{row_number}": first_section.get("section"),
        f"B{row_number}": first_section.get("status"),
        f"C{row_number}": first_section.get("assigned_table"),
        f"D{row_number}": first_section.get("row_count"),
        f"E{row_number}": first_section.get("column_count"),
    }.items():
        text = _cell_text(value)
        if text:
            cells[cell_ref] = text
    required_cells = {REPORT_TABLES_SUMMARY_SHEET: cells} if cells else {}
    required_cells.update(_report_tables_preview_cells(analysis))
    return required_cells


def _output_records(
    output_dir: Path, audit: dict[str, Any], analysis: dict[str, Any]
) -> list[dict[str, Any]]:
    outputs: list[dict[str, Any]] = []
    for relative in ALLOWED_REPORT_OUTPUTS:
        path = output_dir / relative
        if not path.is_file() or path.is_symlink():
            continue
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        output = {
            "path": relative,
            "size_bytes": path.stat().st_size,
            "sha256": digest,
            "kind": path.suffix.lower().lstrip(".") or "file",
            "status": "written",
        }
        if relative == "report_tables.xlsx":
            preview_headers = _report_tables_preview_headers(analysis)
            required_sheets = [REPORT_TABLES_SUMMARY_SHEET]
            required_sheets.extend(
                sheet for sheet in preview_headers if sheet not in required_sheets
            )
            output["required_sheets"] = required_sheets
            output["required_sheet_headers"] = {
                REPORT_TABLES_SUMMARY_SHEET: REPORT_TABLES_SUMMARY_HEADERS
            }
            output["required_sheet_headers"].update(preview_headers)
            required_cells = _report_tables_required_cells(analysis)
            if required_cells:
                output["required_cells"] = required_cells
            output["qa_checks"] = [
                "office_zip",
                "workbook_xml",
                "required_sheets",
                "required_sheet_headers",
            ]
            if required_cells:
                output["qa_checks"].append("required_cells")
        elif relative == "report_tables.json":
            output["records_key"] = "tables"
            output["row_count"] = int(audit.get("table_count", 0))
            output["required_columns"] = [
                "table_id",
                "source_file",
                "row_count",
                "column_count",
            ]
        elif relative == "report_draft.md":
            output["required_text"] = _report_markdown_required_text(analysis)
            output["qa_checks"] = ["nonempty_text", "required_text"]
        elif relative == "report.docx":
            output["required_text"] = _report_docx_required_text(analysis, audit)
            output["qa_checks"] = ["nonempty_text", "required_text"]
        elif relative == "review_handoff.md":
            output.update(
                _review_handoff_output_record(
                    path,
                    str(analysis.get("language") or "en"),
                )
            )
            output["size_bytes"] = path.stat().st_size
            output["sha256"] = digest
        outputs.append(output)
    return outputs


def build_output_records(
    output_dir: Path, audit: dict[str, Any], analysis: dict[str, Any]
) -> list[dict[str, Any]]:
    """Build final artifact records with workflow-specific QA metadata."""

    return _output_records(output_dir, audit, analysis)


def refresh_final_artifacts(
    output_dir: Path,
    *,
    audit: dict[str, Any],
    analysis: dict[str, Any],
) -> Path:
    """Rebuild the public gallery only from current allowlisted artifacts."""

    output_dir = Path(output_dir)
    final_path = output_dir / "final_artifacts.json"
    payload = json.loads(final_path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("final_artifacts.json must be an object")
    outputs = _output_records(output_dir, audit, analysis)
    handoff_path = output_dir / "review_handoff.md"
    if handoff_path.is_file():
        outputs = [
            output for output in outputs if output.get("path") != handoff_path.name
        ]
        record = _review_handoff_output_record(
            handoff_path,
            str(analysis.get("language") or "en"),
        )
        record["size_bytes"] = handoff_path.stat().st_size
        record["sha256"] = hashlib.sha256(handoff_path.read_bytes()).hexdigest()
        outputs.append(record)
    payload["outputs"] = outputs
    return _write_json(final_path, payload)


def write_run_intake(
    output_dir: Path,
    *,
    input_path: Path,
    recipe_path: Path | None,
    language: str,
    document_language: str,
    report_type: str,
    run_id: str | None = None,
    client_engagement: Mapping[str, Any] | None = None,
) -> RunIntakeResult:
    """Write run intake before deterministic report rendering."""

    effective_run_id = run_id or _run_id(input_path)
    run_root_value = (
        client_engagement.get("run_root")
        if isinstance(client_engagement, Mapping)
        else None
    )
    managed_run = isinstance(run_root_value, str) and bool(run_root_value.strip())
    output_reference = output_dir.as_posix()
    if managed_run:
        run_root = Path(run_root_value).expanduser().resolve()
        try:
            relative_output = output_dir.expanduser().resolve().relative_to(run_root)
        except ValueError as exc:
            raise ValueError("Report Builder output is outside the run root.") from exc
        if not relative_output.parts:
            raise ValueError("Report Builder output must identify a run artifact.")
        output_reference = relative_output.as_posix()
    spanish = _is_spanish(language)
    local_files_read = [input_path.name]
    if recipe_path is not None:
        local_files_read.append(recipe_path.name)
    payload = {
        "schema_version": SCHEMA_VERSION,
        "plugin": PLUGIN_NAME,
        "workflow": WORKFLOW_NAME,
        "run_id": effective_run_id,
        **({"path_reference": "run_root_relative"} if managed_run else {}),
        "created_at": _utc_now(),
        "language": language,
        "document_language": document_language,
        "input_paths": [input_path.name],
        "output_dir": output_reference,
        "inferred_task": "report_builder_review_payload",
        "assumptions": {
            "report_type": report_type,
            "language": language,
            "document_language": document_language,
            "recipe_path": recipe_path.name if recipe_path else None,
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
            "local_files_read": local_files_read,
            "external_connectors_used": [],
            "upload_paths_used": [],
            "remote_sql_execution_used": False,
            "hosted_notebook_execution_used": False,
            "notes": [
                (
                    "Los scripts del informe leen localmente las tablas de origen y los archivos de receta opcionales antes de generar los artefactos de revisión."
                    if spanish
                    else "Report scripts read source tables and optional recipe files locally before writing review artifacts."
                ),
                (
                    "De forma predeterminada no se utiliza ningún conector externo, ruta de carga, SQL remoto ni cuaderno alojado."
                    if spanish
                    else "No external connector, upload path, remote SQL, or hosted notebook execution is used by default."
                ),
            ],
        },
        "status": "ready_for_report_build",
    }
    return RunIntakeResult(
        run_id=effective_run_id,
        path=_write_json(output_dir / "run_intake.json", payload),
    )


def _build_review_payload(
    output_dir: Path,
    *,
    run_id: str,
    run_intake_path: Path,
    analysis: dict[str, Any],
    audit: dict[str, Any],
    recipe: dict[str, Any],
    paths: dict[str, Path],
    tables: Sequence[dict[str, Any]] = (),
) -> dict[str, Any]:
    language = str(analysis.get("language", recipe.get("language", "en")))
    items: list[dict[str, Any]] = []
    items.extend(_section_items(analysis, language))
    items.extend(_table_evidence_items(analysis, tables=tables, language=language))
    items.extend(_source_qualification_failure_items(tables, language=language))
    items.extend(_issue_items(analysis, audit, language))
    items.extend(_artifact_items(paths, output_dir, language))
    numeric_paths_exist = all(
        key in paths and Path(paths[key]).is_file()
        for key in ("numeric_evidence", "source_receipts")
    )
    return {
        "schema_version": SCHEMA_VERSION,
        "plugin": PLUGIN_NAME,
        "workflow": WORKFLOW_NAME,
        "run_id": run_id,
        "created_at": _utc_now(),
        "language": language,
        "document_language": analysis.get(
            "document_language", recipe.get("document_language", "auto")
        ),
        "source_paths": [],
        "review_type": "report_builder_review",
        "items": items,
        "item_count": len(items),
        "columns": _review_columns(language),
        "source_artifacts": {
            "run_intake": _as_output_ref(run_intake_path, output_dir),
            "report_draft": "report_draft.md",
            "report_docx": "report.docx",
            "report_analysis": "report_analysis.json",
            "report_audit": "report_audit.json",
            "report_tables": "report_tables.json",
            "report_tables_xlsx": "report_tables.xlsx",
            "used_recipe": "used_recipe.json",
            **(
                {
                    "numeric_evidence": _as_output_ref(
                        paths["numeric_evidence"], output_dir
                    ),
                    "source_receipts": _as_output_ref(
                        paths["source_receipts"], output_dir
                    ),
                }
                if numeric_paths_exist
                else {}
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
            "report_status": audit.get("status"),
            "report_type": analysis.get("report_type", recipe.get("report_type")),
            "entity": analysis.get("entity"),
            "period": analysis.get("period"),
            "table_count": audit.get("table_count", 0),
            "assigned_section_count": audit.get("assigned_section_count", 0),
            "missing_section_count": audit.get("missing_section_count", 0),
            "numeric_measure_pending_section_count": len(
                [
                    section
                    for section in analysis.get("sections", [])
                    if isinstance(section, dict)
                    and section.get("numeric_measure_status") == "needs_review"
                ]
            ),
            "codex_narrative_sections": audit.get("codex_narrative_sections", 0),
            "artifact_count": len(
                [path for path in paths.values() if Path(path).is_file()]
            ),
        },
    }


def refresh_review_payload(
    output_dir: Path,
    *,
    analysis: dict[str, Any],
    audit: dict[str, Any],
    recipe: dict[str, Any],
    paths: dict[str, Path],
    tables: Sequence[dict[str, Any]] = (),
) -> Path:
    """Regenerate review evidence after a source-mapping change."""

    output_dir = Path(output_dir)
    current = json.loads(
        (output_dir / "review_payload.json").read_text(encoding="utf-8")
    )
    if not isinstance(current, dict):
        raise ValueError("review_payload.json must be an object")
    payload = _build_review_payload(
        output_dir,
        run_id=str(current.get("run_id") or ""),
        run_intake_path=output_dir / "run_intake.json",
        analysis=analysis,
        audit=audit,
        recipe=recipe,
        paths=paths,
        tables=tables,
    )
    payload["status"] = "ready_for_review_after_regeneration"
    path = _write_json(output_dir / "review_payload.json", payload)
    _write_json(
        output_dir / "ui_decisions.json",
        {
            "schema_version": SCHEMA_VERSION,
            "plugin": PLUGIN_NAME,
            "workflow": WORKFLOW_NAME,
            "run_id": payload["run_id"],
            "review_payload_sha256": _canonical_json_sha256(payload),
            "decided_at": None,
            "decision_source": "not_collected_after_regeneration",
            "review_payload_path": path.name,
            "decisions": [],
            "decision_count": 0,
            "item_count": payload["item_count"],
            "status": "pending_review",
        },
    )
    return path


def write_review_session_artifacts(
    output_dir: Path,
    *,
    run_id: str,
    run_intake_path: Path,
    analysis: dict[str, Any],
    audit: dict[str, Any],
    recipe: dict[str, Any],
    paths: dict[str, Path],
    tables: Sequence[dict[str, Any]] = (),
) -> ReviewSessionResult:
    """Write report review payload, pending decisions, and artifact inventory."""

    language = str(analysis.get("language", recipe.get("language", "en")))
    review_payload = _build_review_payload(
        output_dir,
        run_id=run_id,
        run_intake_path=run_intake_path,
        analysis=analysis,
        audit=audit,
        recipe=recipe,
        paths=paths,
        tables=tables,
    )
    items = review_payload["items"]
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
            "review_payload_sha256": _canonical_json_sha256(review_payload),
            "decided_at": None,
            "decision_source": "not_collected",
            "review_payload_path": review_payload_path.name,
            "decisions": [],
            "decision_count": 0,
            "item_count": len(items),
            "status": "pending_review",
        },
    )

    review_handoff_path = _write_review_handoff_card(
        output_dir,
        run_id=run_id,
        title=("Generador de informes" if _is_spanish(language) else "Report Builder"),
        validate_tool="validate_report_builder_review",
        render_tool="render_report_builder_review",
        save_tool="save_report_builder_decisions",
        apply_tool="apply_report_builder_decisions",
        language=language,
    )
    outputs = _output_records(output_dir, audit, analysis)
    outputs = [
        output
        for output in outputs
        if not (
            isinstance(output, dict) and output.get("path") == review_handoff_path.name
        )
    ]
    outputs.append(_review_handoff_output_record(review_handoff_path, language))

    spanish = _is_spanish(language)
    assurance = build_report_assurance_state(analysis, tables)

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
                (
                    "Codex sigue siendo responsable del juicio narrativo y de las conclusiones del informe."
                    if spanish
                    else "Codex remains responsible for narrative judgment and report conclusions."
                ),
                (
                    "Revise las secciones sin asignar y los comentarios pendientes de Codex antes de cualquier uso externo."
                    if spanish
                    else "Review unassigned sections and Codex-pending comments before external use."
                ),
                (
                    "ui_decisions.json queda pendiente hasta que Codex, el widget MCP o la revisión alternativa registren las decisiones."
                    if spanish
                    else "ui_decisions.json is pending until Codex, the MCP widget, or fallback review records decisions."
                ),
            ],
            "next_actions": [
                (
                    "Ejecute validate_report_builder_review y, cuando MCP esté disponible, render_report_builder_review."
                    if spanish
                    else "Call validate_report_builder_review, then render_report_builder_review when MCP is available."
                ),
                (
                    "Edite suggested_recipe.json o used_recipe.json y vuelva a ejecutar build_report.py cuando deba corregir asignaciones o comentarios."
                    if spanish
                    else "Edit suggested_recipe.json or used_recipe.json and rerun build_report.py when mappings or comments need correction."
                ),
                (
                    "Use report.docx para la entrega en Word solo después de registrar las decisiones de revisión."
                    if spanish
                    else "Use report.docx for Word delivery only after review decisions are recorded."
                ),
            ],
            "assurance": assurance,
            "report_ready": assurance["report_ready"],
            "status": "written_pending_review",
        },
    )
    _append_execution_trace(
        run_intake_path,
        final_artifacts_path,
        command=["python", "plugins/report-builder/scripts/build_report.py"],
    )

    return ReviewSessionResult(
        run_id=run_id,
        run_intake_path=run_intake_path,
        review_payload_path=review_payload_path,
        ui_decisions_path=ui_decisions_path,
        final_artifacts_path=final_artifacts_path,
        review_item_count=len(items),
    )
