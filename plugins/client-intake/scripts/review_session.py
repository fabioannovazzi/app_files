from __future__ import annotations

import json
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Sequence

from detect_duplicates import DuplicateCandidate
from extract_documents import DocumentEvidence
from parse_fatturapa_xml import InvoiceXmlRecord
from parse_fiscal_forms import FiscalField
from scan_folder import CATEGORY_NON_CLASSIFICATI, FileRecord

__all__ = [
    "ReviewSessionResult",
    "RunIntakeResult",
    "write_review_session_artifacts",
    "write_run_intake",
]

SCHEMA_VERSION = "1.0"
PLUGIN_NAME = "client-intake"
WORKFLOW_NAME = "fascicolo-intake"
MAX_PREVIEW_CHARS = 2000
INVENTORY_REQUIRED_COLUMNS = [
    "relative_path",
    "file_name",
    "extension",
    "size_bytes",
    "modified_iso",
    "category",
    "confidence",
    "years",
    "notes",
]
STRUCTURED_FIELDS_REQUIRED_COLUMNS = [
    "relative_path",
    "file_name",
    "document_kind",
    "field_code",
    "label",
    "value",
    "confidence",
]
XML_SUMMARY_REQUIRED_COLUMNS = [
    "relative_path",
    "file_name",
    "supplier_vat",
    "invoice_date",
    "invoice_number",
    "total_amount",
    "malformed",
]


@dataclass(frozen=True)
class RunIntakeResult:
    """Run intake artifact written before the heavier extraction steps."""

    run_id: str
    path: Path


@dataclass(frozen=True)
class ReviewSessionResult:
    """Review-session artifacts for a client-intake run."""

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


def _run_id(root: Path) -> str:
    timestamp = re.sub(r"[^0-9]", "", _utc_now())
    return f"{PLUGIN_NAME}-{_safe_slug(root.name)}-{timestamp}"


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


def _category_counts(records: Sequence[FileRecord]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for record in records:
        counts[record.category] = counts.get(record.category, 0) + 1
    return dict(sorted(counts.items(), key=lambda item: item[0]))


def _as_output_ref(path: Path, output_dir: Path) -> str:
    try:
        return path.relative_to(output_dir).as_posix()
    except ValueError:
        return path.as_posix()


def _read_preview(path: Path, limit: int = MAX_PREVIEW_CHARS) -> str:
    try:
        return path.read_text(encoding="utf-8", errors="ignore")[:limit].strip()
    except OSError:
        return ""


def _evidence_by_path(
    document_evidence: Sequence[DocumentEvidence],
) -> dict[str, DocumentEvidence]:
    return {item.relative_path: item for item in document_evidence}


def _fiscal_field_counts(fields: Sequence[FiscalField]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for field in fields:
        counts[field.relative_path] = counts.get(field.relative_path, 0) + 1
    return counts


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


def _document_item(
    index: int,
    record: FileRecord,
    root: Path,
    output_dir: Path,
    evidence: DocumentEvidence | None,
    fiscal_field_count: int,
) -> dict[str, Any]:
    evidence_refs: list[dict[str, Any]] = []
    if evidence and evidence.text_path:
        text_path = output_dir / evidence.text_path
        evidence_refs.append(
            {
                "kind": "extracted_text",
                "path": _as_output_ref(text_path, output_dir),
                "preview": _read_preview(text_path, limit=600),
            }
        )
    if evidence:
        evidence_refs.append(
            {
                "kind": "extraction_result",
                "readable": evidence.readable,
                "method": evidence.extraction_method,
                "confidence": evidence.confidence,
                "notes": list(evidence.notes),
            }
        )
    source_path = root / record.relative_path
    needs_attention = (
        record.category == CATEGORY_NON_CLASSIFICATI
        or record.confidence != "alta"
        or bool(record.notes)
        or (evidence is not None and not evidence.readable)
    )
    return _base_item(
        f"document-{index}",
        "document_inventory",
        record.relative_path,
        source_path=source_path.as_posix(),
        allowed_actions=("accept", "edit", "mark_unclear", "skip"),
        recommended_action="mark_unclear" if needs_attention else "accept",
        evidence=evidence_refs,
        data=record.as_row()
        | {
            "readable": evidence.readable if evidence else None,
            "extraction_method": evidence.extraction_method if evidence else None,
            "text_path": evidence.text_path if evidence else "",
            "structured_field_count": fiscal_field_count,
        },
    )


def _uncertain_document_items(
    records: Sequence[FileRecord],
    evidence_lookup: dict[str, DocumentEvidence],
    root: Path,
    target_year: int | None,
) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    for index, record in enumerate(records, start=1):
        evidence = evidence_lookup.get(record.relative_path)
        reasons: list[str] = []
        if record.category == CATEGORY_NON_CLASSIFICATI:
            reasons.append("documento_non_classificato")
        if record.confidence != "alta":
            reasons.append("classificazione_non_alta")
        if record.notes:
            reasons.extend(record.notes)
        if target_year is not None and record.years and target_year not in record.years:
            reasons.append("anno_fuori_target")
        if evidence is not None and not evidence.readable:
            reasons.append("testo_non_leggibile")
        if not reasons:
            continue
        items.append(
            _base_item(
                f"uncertain-file-{index}",
                "uncertain_file",
                record.relative_path,
                source_path=(root / record.relative_path).as_posix(),
                allowed_actions=("accept", "edit", "mark_unclear", "skip"),
                recommended_action="mark_unclear",
                data={
                    "category": record.category,
                    "confidence": record.confidence,
                    "reasons": reasons,
                    "years": list(record.years),
                },
            )
        )
    return items


def _missing_document_items(missing_items: Sequence[str]) -> list[dict[str, Any]]:
    return [
        _base_item(
            f"missing-document-{index}",
            "missing_document_request",
            f"Richiesta mancante/incerta {index}",
            allowed_actions=("accept", "reject", "edit", "request_more_documents"),
            recommended_action="accept",
            output_path="02_documenti_mancanti_o_incerti.md",
            data={"request_text": item},
        )
        for index, item in enumerate(missing_items, start=1)
    ]


def _fiscal_field_items(fields: Sequence[FiscalField]) -> list[dict[str, Any]]:
    return [
        _base_item(
            f"fiscal-field-{index}",
            "extracted_fiscal_field",
            f"{field.document_kind}: {field.label}",
            source_path=field.relative_path,
            output_path="extracted/structured_fiscal_fields.csv",
            allowed_actions=("accept", "edit", "mark_unclear", "skip"),
            recommended_action=(
                "accept" if field.confidence in {"alta", "media"} else "mark_unclear"
            ),
            evidence=[
                {
                    "kind": "snippet",
                    "text": field.evidence,
                    "warnings": list(field.warnings),
                }
            ],
            data=field.as_row(),
        )
        for index, field in enumerate(fields, start=1)
    ]


def _draft_item(
    item_id: str,
    item_type: str,
    title: str,
    output_dir: Path,
    relative_path: str,
) -> dict[str, Any]:
    path = output_dir / relative_path
    return _base_item(
        item_id,
        item_type,
        title,
        output_path=relative_path,
        allowed_actions=("accept", "edit", "mark_unclear", "skip"),
        recommended_action="accept" if path.exists() else "mark_unclear",
        data={
            "path": relative_path,
            "exists": path.exists(),
            "preview": _read_preview(path),
        },
    )


def _duplicate_items(
    candidates: Sequence[DuplicateCandidate],
) -> list[dict[str, Any]]:
    return [
        _base_item(
            f"duplicate-{index}",
            "duplicate_warning",
            candidate.relative_path,
            source_path=candidate.relative_path,
            output_path="duplicate_candidates.csv",
            allowed_actions=("accept", "reject", "mark_unclear", "skip"),
            recommended_action="mark_unclear",
            data=candidate.as_row(),
        )
        for index, candidate in enumerate(candidates, start=1)
    ]


def _xml_anomaly_items(records: Sequence[InvoiceXmlRecord]) -> list[dict[str, Any]]:
    return [
        _base_item(
            f"xml-anomaly-{index}",
            "formal_xml_anomaly",
            record.relative_path,
            source_path=record.relative_path,
            output_path="fatture/formal_anomalies.md",
            allowed_actions=("accept", "edit", "mark_unclear", "skip"),
            recommended_action="mark_unclear",
            data=record.as_json(),
        )
        for index, record in enumerate(records, start=1)
        if record.malformed or record.anomalies
    ]


def _review_columns() -> list[dict[str, str]]:
    return [
        {"field": "item_type", "label": "Tipo"},
        {"field": "title", "label": "Elemento"},
        {"field": "recommended_action", "label": "Azione suggerita"},
        {"field": "source_path", "label": "Fonte"},
        {"field": "output_path", "label": "Output"},
        {"field": "status", "label": "Stato"},
    ]


def _clean_text(value: Any) -> str:
    return " ".join(str(value or "").strip().split())


def _first_clean(values: Sequence[Any]) -> str:
    for value in values:
        text = _clean_text(value)
        if text:
            return text
    return ""


def _first_record_path(records: Sequence[FileRecord]) -> str:
    return _first_clean([record.relative_path for record in records])


def _first_field_text(fields: Sequence[FiscalField]) -> str:
    for field in fields:
        text = _clean_text(field.field_code or field.label or field.document_kind)
        if text:
            return text
    return ""


def _append_if_text(target: list[str], value: Any) -> None:
    text = _clean_text(value)
    if text and text not in target:
        target.append(text)


def _required_text_by_path(
    *,
    client_name: str,
    target_year: int | None,
    records: Sequence[FileRecord],
    missing_items: Sequence[str],
    professional_questions: Sequence[str],
    client_questions: Sequence[str],
    structured_fields: Sequence[FiscalField],
) -> dict[str, list[str]]:
    year_text = str(target_year) if target_year is not None else "non indicato"
    first_record = _first_record_path(records)
    first_missing = _first_clean(missing_items)
    first_professional_question = _first_clean(professional_questions)
    first_client_question = _first_clean(client_questions)
    first_field = _first_field_text(structured_fields)

    required = {
        "00_environment_check.md": ["# Controllo ambiente"],
        "00_fascicolo_index.md": [
            "# Indice fascicolo",
            f"Anno target: {year_text}",
            f"File analizzati: {len(records)}",
        ],
        "02_documenti_mancanti_o_incerti.md": ["# Documenti mancanti o incerti"],
        "03_domande_interne_studio.md": ["# Domande interne dello studio"],
        "04_bozza_email_cliente.md": [],
        "06_memo_istruttoria.md": [
            "# Memo di istruttoria clienti",
            f"Cliente {client_name}",
            f"Anno {year_text}",
            f"File analizzati: {len(records)}.",
            "## Documenti ricevuti",
            "## Elementi mancanti o incerti",
        ],
        "07_scheda_codex_per_studio.md": [
            "# Scheda per lo studio",
            client_name,
            year_text,
            "## Sintesi del fascicolo",
            f"File analizzati: {len(records)}",
            f"Campi fiscali strutturati estratti: {len(structured_fields)}",
            "## Punti mancanti o incerti",
        ],
        "08_dati_fiscali_strutturati.md": [
            "# Dati fiscali strutturati",
            f"Campi estratti: {len(structured_fields)}",
        ],
    }

    _append_if_text(required["00_fascicolo_index.md"], first_record)
    _append_if_text(required["02_documenti_mancanti_o_incerti.md"], first_missing)
    _append_if_text(
        required["03_domande_interne_studio.md"], first_professional_question
    )
    if first_client_question:
        required["04_bozza_email_cliente.md"] = [
            "Oggetto: Documenti e chiarimenti per completare l'istruttoria",
            client_name,
            first_client_question,
        ]
    else:
        required["04_bozza_email_cliente.md"] = [
            "# Bozza email cliente",
            "Nessuna richiesta cliente generata automaticamente",
        ]
    _append_if_text(required["06_memo_istruttoria.md"], first_missing)
    _append_if_text(required["06_memo_istruttoria.md"], first_professional_question)
    _append_if_text(required["06_memo_istruttoria.md"], first_client_question)
    _append_if_text(required["07_scheda_codex_per_studio.md"], first_missing)
    _append_if_text(
        required["07_scheda_codex_per_studio.md"], first_professional_question
    )
    _append_if_text(required["07_scheda_codex_per_studio.md"], first_client_question)
    _append_if_text(required["08_dati_fiscali_strutturati.md"], first_field)
    return required


def _output_records(
    output_dir: Path,
    *,
    client_name: str,
    target_year: int | None,
    records: Sequence[FileRecord],
    missing_items: Sequence[str],
    professional_questions: Sequence[str],
    client_questions: Sequence[str],
    structured_fields: Sequence[FiscalField],
    xml_records: Sequence[InvoiceXmlRecord],
) -> list[dict[str, Any]]:
    outputs: list[dict[str, Any]] = []
    review_files = {
        "run_intake.json",
        "review_payload.json",
        "ui_decisions.json",
        "final_artifacts.json",
    }
    required_text_by_path = _required_text_by_path(
        client_name=client_name,
        target_year=target_year,
        records=records,
        missing_items=missing_items,
        professional_questions=professional_questions,
        client_questions=client_questions,
        structured_fields=structured_fields,
    )
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
        required_text = required_text_by_path.get(relative)
        if required_text:
            output["required_text"] = required_text
            output["qa_checks"] = ["nonempty_text", "required_text"]
        if relative == "01_document_inventory.csv":
            output["row_count"] = len(records)
            output["required_columns"] = INVENTORY_REQUIRED_COLUMNS
        elif relative == "extracted/structured_fiscal_fields.csv":
            output["row_count"] = len(structured_fields)
            output["required_columns"] = STRUCTURED_FIELDS_REQUIRED_COLUMNS
        elif relative == "extracted/structured_fiscal_fields.jsonl":
            output["row_count"] = len(structured_fields)
            output["required_columns"] = STRUCTURED_FIELDS_REQUIRED_COLUMNS
        elif relative == "fatture/fatture_summary.csv":
            output["row_count"] = len(xml_records)
            output["required_columns"] = XML_SUMMARY_REQUIRED_COLUMNS
        outputs.append(output)
    return outputs


def write_run_intake(
    output_dir: Path,
    root: Path,
    *,
    target_year: int | None,
    client_name: str,
    records: Sequence[FileRecord],
    missing_dependency_count: int,
    require_ocr: bool,
    enable_ocr: bool,
    ocr_lang: str,
) -> RunIntakeResult:
    """Write the intake contract as soon as folder scope is known."""

    run_id = _run_id(root)
    data_posture_notes = [
        "Scripts inspect local customer-folder files and write bounded review artifacts for UI review.",
        "No external connector, upload path, remote SQL, or hosted notebook execution is used by default.",
    ]
    if enable_ocr or require_ocr:
        data_posture_notes.append(
            "OCR, when enabled or required, reads local document files before bounded review artifacts are written."
        )
    payload = {
        "schema_version": SCHEMA_VERSION,
        "plugin": PLUGIN_NAME,
        "workflow": WORKFLOW_NAME,
        "run_id": run_id,
        "created_at": _utc_now(),
        "language": "it",
        "input_paths": [root.as_posix()],
        "output_dir": output_dir.as_posix(),
        "inferred_task": "first_customer_folder_intake",
        "assumptions": {
            "client_name": client_name,
            "target_year": target_year,
            "ocr_requested": enable_ocr,
            "ocr_language": ocr_lang,
            "ocr_required_by_file_types": require_ocr,
            "category_counts": _category_counts(records),
            "file_count": len(records),
        },
        "unresolved_questions": [],
        "dependency_check": {
            "missing_dependency_count": missing_dependency_count,
            "status": (
                "ok" if missing_dependency_count == 0 else "missing_optional_or_core"
            ),
        },
        "data_posture": {
            "local_files_read": [root.as_posix()],
            "model_excerpts_sent": [],
            "external_connectors_used": [],
            "upload_paths_used": [],
            "remote_sql_execution_used": False,
            "hosted_notebook_execution_used": False,
            "notes": data_posture_notes,
        },
        "status": "ready_for_extraction",
    }
    return RunIntakeResult(
        run_id=run_id,
        path=_write_json(output_dir / "run_intake.json", payload),
    )


def write_review_session_artifacts(
    output_dir: Path,
    root: Path,
    *,
    run_id: str,
    run_intake_path: Path,
    target_year: int | None,
    client_name: str,
    records: Sequence[FileRecord],
    document_evidence: Sequence[DocumentEvidence],
    structured_fields: Sequence[FiscalField],
    missing_items: Sequence[str],
    professional_questions: Sequence[str],
    client_questions: Sequence[str],
    duplicate_candidates: Sequence[DuplicateCandidate],
    xml_records: Sequence[InvoiceXmlRecord],
) -> ReviewSessionResult:
    """Write review payload, pending decisions, and final artifact index."""

    evidence_lookup = _evidence_by_path(document_evidence)
    field_counts = _fiscal_field_counts(structured_fields)
    items: list[dict[str, Any]] = []
    items.extend(
        _document_item(
            index,
            record,
            root,
            output_dir,
            evidence_lookup.get(record.relative_path),
            field_counts.get(record.relative_path, 0),
        )
        for index, record in enumerate(records, start=1)
    )
    items.extend(_uncertain_document_items(records, evidence_lookup, root, target_year))
    items.extend(_missing_document_items(missing_items))
    items.extend(_fiscal_field_items(structured_fields))
    items.extend(_duplicate_items(duplicate_candidates))
    items.extend(_xml_anomaly_items(xml_records))
    items.append(
        _draft_item(
            "draft-memo",
            "draft_memo_section",
            "Memo istruttoria per lo studio",
            output_dir,
            "06_memo_istruttoria.md",
        )
    )
    items.append(
        _draft_item(
            "draft-client-email",
            "draft_client_email",
            "Bozza email cliente",
            output_dir,
            "04_bozza_email_cliente.md",
        )
    )

    review_payload = {
        "schema_version": SCHEMA_VERSION,
        "plugin": PLUGIN_NAME,
        "workflow": WORKFLOW_NAME,
        "run_id": run_id,
        "created_at": _utc_now(),
        "source_paths": [root.as_posix()],
        "review_type": "client_intake_folder_review",
        "items": items,
        "item_count": len(items),
        "columns": _review_columns(),
        "evidence": {
            "run_intake": _as_output_ref(run_intake_path, output_dir),
            "document_inventory": "01_document_inventory.csv",
            "missing_documents": "02_documenti_mancanti_o_incerti.md",
            "structured_fiscal_fields": "extracted/structured_fiscal_fields.csv",
            "memo": "06_memo_istruttoria.md",
            "client_email": "04_bozza_email_cliente.md",
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
            "file_count": len(records),
            "uncertain_file_count": sum(
                1 for item in items if item["item_type"] == "uncertain_file"
            ),
            "missing_document_count": len(missing_items),
            "structured_field_count": len(structured_fields),
            "duplicate_count": len(duplicate_candidates),
            "xml_anomaly_count": sum(1 for record in xml_records if record.anomalies),
            "professional_questions": list(professional_questions),
        },
    }
    review_payload_path = _write_json(
        output_dir / "review_payload.json", review_payload
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
        title="Client Intake",
        validate_tool="validate_client_intake_review",
        render_tool="render_client_intake_review",
        save_tool="save_client_intake_decisions",
        apply_tool="apply_client_intake_decisions",
    )
    outputs = _output_records(
        output_dir,
        client_name=client_name,
        target_year=target_year,
        records=records,
        missing_items=missing_items,
        professional_questions=professional_questions,
        client_questions=client_questions,
        structured_fields=structured_fields,
        xml_records=xml_records,
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
                "ui_decisions.json is pending until a Codex review, local UI, or fallback review records user decisions."
            ],
            "next_actions": [
                "Review review_payload.json before revising the studio memo or client email.",
                "Persist any accept/edit/reject decisions in ui_decisions.json when a review step is run.",
            ],
            "status": "written_pending_review",
        },
    )
    _append_execution_trace(
        run_intake_path,
        final_artifacts_path,
        command=["python", "plugins/client-intake/scripts/build_intake_outputs.py"],
    )

    return ReviewSessionResult(
        run_intake_path=run_intake_path,
        review_payload_path=review_payload_path,
        ui_decisions_path=ui_decisions_path,
        final_artifacts_path=final_artifacts_path,
        review_item_count=len(items),
    )
