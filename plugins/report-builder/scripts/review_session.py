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
    "build_output_records",
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
    },
    "audit_appendix": {
        "en": "Audit appendix",
        "it": "Appendice audit",
        "fr": "Annexe d'audit",
        "de": "Audit-Anhang",
    },
    "report_status": {
        "en": "Report status",
        "it": "Stato report",
        "fr": "Statut du rapport",
        "de": "Berichtsstatus",
    },
    "model_api_calls": {
        "en": "Model API calls from scripts",
        "it": "Chiamate API modello dagli script",
        "fr": "Appels API modele par les scripts",
        "de": "Modell-API-Aufrufe aus Skripten",
    },
    "assigned_sections": {
        "en": "Assigned sections",
        "it": "Sezioni assegnate",
        "fr": "Sections assignees",
        "de": "Zugeordnete Abschnitte",
    },
    "missing_sections": {
        "en": "Missing sections",
        "it": "Sezioni mancanti",
        "fr": "Sections manquantes",
        "de": "Fehlende Abschnitte",
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
    timestamp = re.sub(r"[^0-9]", "", _utc_now())
    return f"{PLUGIN_NAME}-{_safe_slug(input_path.stem)}-{timestamp}"


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
        {"field": "title", "label": "Report item"},
        {"field": "recommended_action", "label": "Suggested action"},
        {"field": "source_path", "label": "Source"},
        {"field": "output_path", "label": "Output"},
        {"field": "status", "label": "Status"},
    ]


def _section_items(analysis: dict[str, Any]) -> list[dict[str, Any]]:
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
        source_parts = [
            _clean_text(section.get("source_file")),
            _clean_text(section.get("sheet_name")),
            _clean_text(section.get("assigned_table")),
        ]
        items.append(
            _base_item(
                f"report-section-{index}",
                "report_section",
                f"{title} ({status})",
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
                        "numeric_column_count": len(
                            section.get("numeric_columns", []) or []
                        ),
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
                    "preview_rows": (section.get("preview_rows") or [])[:5],
                    "codex_comment": section.get("codex_comment", ""),
                },
            )
        )
    return items


def _table_evidence_items(
    analysis: dict[str, Any],
    tables: Sequence[dict[str, Any]] = (),
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
        requested_document = f"Alternative source table or support schedule for report section {section_key}"
        items.append(
            _base_item(
                f"table-evidence-{index}",
                "table_evidence",
                f"Evidence table for {title}",
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
                    "edit_value_hint": "Use one exact table_id from available_table_ids.",
                    "available_table_ids": available_table_ids,
                    "requested_document": requested_document,
                    "required_document": requested_document,
                    "source_file": section.get("source_file"),
                    "source_table": section.get("sheet_name") or table_id,
                    "record_id": section_key,
                    "reason": "Reviewer marked the mapped source table as unclear or insufficient.",
                    "numeric_columns": (section.get("numeric_columns") or [])[:8],
                    "preview_rows": (section.get("preview_rows") or [])[:5],
                },
            )
        )
    return items


def _issue_items(
    analysis: dict[str, Any], audit: dict[str, Any]
) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    missing_sections = audit.get("missing_sections") or []
    if isinstance(missing_sections, list):
        for index, section_key in enumerate(missing_sections, start=1):
            section_label = _clean_text(section_key) or f"section-{index}"
            requested_document = (
                f"Source table or narrative support for report section {section_label}"
            )
            followup_context = {
                "section": section_label,
                "requested_document": requested_document,
                "required_document": requested_document,
                "reason": "No deterministic source table is mapped to this report section.",
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
                    f"Missing section mapping: {section_label}",
                    output_path="used_recipe.json",
                    allowed_actions=(
                        "edit",
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
                f"Narrative pending: {title}",
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
    return items


def _artifact_items(paths: dict[str, Path], output_dir: Path) -> list[dict[str, Any]]:
    labels = {
        "report_draft": ("report_artifact", "Markdown report draft"),
        "report_docx": ("report_artifact", "Word report"),
        "report_analysis": ("report_artifact", "Report analysis JSON"),
        "report_audit": ("report_artifact", "Report audit JSON"),
        "report_tables": ("report_artifact", "Report tables JSON"),
        "report_tables_xlsx": ("report_artifact", "Report tables workbook"),
        "used_recipe": ("report_artifact", "Used recipe JSON"),
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
    ]
    if int(audit.get("missing_section_count") or 0) > 0:
        keys.append("missing_sections")
    required = [_localized_docx_text(key, language) for key in keys]
    required.extend(_section_titles(analysis))
    return required


def _report_markdown_required_text(analysis: dict[str, Any]) -> list[str]:
    required = ["## Executive summary"]
    required.extend(f"## {title}" for title in _section_titles(analysis))
    if any(
        isinstance(section, dict) and section.get("status") == "assigned"
        for section in analysis.get("sections", [])
    ):
        required.extend(["Source:", "Rows:"])
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
        outputs.append(output)
    return outputs


def build_output_records(
    output_dir: Path, audit: dict[str, Any], analysis: dict[str, Any]
) -> list[dict[str, Any]]:
    """Build final artifact records with workflow-specific QA metadata."""

    return _output_records(output_dir, audit, analysis)


def write_run_intake(
    output_dir: Path,
    *,
    input_path: Path,
    recipe_path: Path | None,
    language: str,
    document_language: str,
    report_type: str,
) -> RunIntakeResult:
    """Write run intake before deterministic report rendering."""

    run_id = _run_id(input_path)
    local_files_read = [input_path.as_posix()]
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
        "input_paths": [input_path.as_posix()],
        "output_dir": output_dir.as_posix(),
        "inferred_task": "report_builder_review_payload",
        "assumptions": {
            "report_type": report_type,
            "language": language,
            "document_language": document_language,
            "recipe_path": recipe_path.as_posix() if recipe_path else None,
        },
        "unresolved_questions": [],
        "dependency_check": {
            "status": "not_run_by_script",
            "note": "Codex should run scripts/check_dependencies.py before helper scripts.",
        },
        "data_posture": {
            "local_files_read": local_files_read,
            "external_connectors_used": [],
            "upload_paths_used": [],
            "remote_sql_execution_used": False,
            "hosted_notebook_execution_used": False,
            "notes": [
                "Report scripts read source tables and optional recipe files locally before writing review artifacts.",
                "No external connector, upload path, remote SQL, or hosted notebook execution is used by default.",
            ],
        },
        "status": "ready_for_report_build",
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
    analysis: dict[str, Any],
    audit: dict[str, Any],
    recipe: dict[str, Any],
    paths: dict[str, Path],
    tables: Sequence[dict[str, Any]] = (),
) -> ReviewSessionResult:
    """Write report review payload, pending decisions, and artifact inventory."""

    items: list[dict[str, Any]] = []
    items.extend(_section_items(analysis))
    items.extend(_table_evidence_items(analysis, tables=tables))
    items.extend(_issue_items(analysis, audit))
    items.extend(_artifact_items(paths, output_dir))

    review_payload = {
        "schema_version": SCHEMA_VERSION,
        "plugin": PLUGIN_NAME,
        "workflow": WORKFLOW_NAME,
        "run_id": run_id,
        "created_at": _utc_now(),
        "language": analysis.get("language", recipe.get("language", "en")),
        "document_language": analysis.get(
            "document_language", recipe.get("document_language", "auto")
        ),
        "source_paths": [],
        "review_type": "report_builder_review",
        "items": items,
        "item_count": len(items),
        "columns": _review_columns(),
        "source_artifacts": {
            "run_intake": _as_output_ref(run_intake_path, output_dir),
            "report_draft": "report_draft.md",
            "report_docx": "report.docx",
            "report_analysis": "report_analysis.json",
            "report_audit": "report_audit.json",
            "report_tables": "report_tables.json",
            "report_tables_xlsx": "report_tables.xlsx",
            "used_recipe": "used_recipe.json",
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
            "codex_narrative_sections": audit.get("codex_narrative_sections", 0),
            "artifact_count": len(paths),
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
        title="Report Builder",
        validate_tool="validate_report_builder_review",
        render_tool="render_report_builder_review",
        save_tool="save_report_builder_decisions",
        apply_tool="apply_report_builder_decisions",
    )
    outputs = _output_records(output_dir, audit, analysis)
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
                "Codex remains responsible for narrative judgment and report conclusions.",
                "Review unassigned sections and Codex-pending comments before external use.",
                "ui_decisions.json is pending until Codex, the MCP widget, or fallback review records decisions.",
            ],
            "next_actions": [
                "Call validate_report_builder_review, then render_report_builder_review when MCP is available.",
                "Edit suggested_recipe.json or used_recipe.json and rerun build_report.py when mappings or comments need correction.",
                "Use report.docx for Word delivery only after review decisions are recorded.",
            ],
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
