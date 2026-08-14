from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Sequence

__all__ = [
    "ReviewSessionResult",
    "RunIntakeResult",
    "synchronize_final_artifact_sizes",
    "write_review_session_artifacts",
    "write_run_intake",
]

SCHEMA_VERSION = "1.0"
PLUGIN_NAME = "deep-research-validator"
WORKFLOW_NAME = "deep-research-validator"
MAX_CLAIM_ITEMS = 750

_REVIEW_COPY: dict[str, dict[str, Any]] = {
    "en": {
        "product_title": "Answer Validator",
        "handoff_title": "Review Handoff",
        "run_id": "Run ID",
        "review_payload": "Review payload",
        "run_intake": "Run intake",
        "pending_decisions": "Pending decisions",
        "applied_decisions": "Applied decisions",
        "final_artifacts": "Final artifacts",
        "review_in_codex": "Professional Review",
        "steps": (
            "Validate the hash-bound local review reference with `{tool}`.",
            "Render the review workbench with the returned token using `{tool}`.",
            "Save reviewer actions with `{tool}`.",
            "Apply reviewer actions with `{tool}`.",
        ),
        "handoff_notice": (
            "Persistent save/apply requires the MCP or local-server review "
            "surface. Static HTML fallback can copy or download decision JSON only."
        ),
        "columns": (
            "Type",
            "Claim or artifact",
            "Suggested action",
            "Source",
            "Output",
            "Status",
        ),
        "claim": "Claim",
        "untitled_claim": "Untitled claim",
        "answer_contract_review": "Answer-contract conformance",
        "coverage_review": "Claim-selection coverage",
        "edit_hint": (
            "Editing this claim writes the reviewer correction to proposed_fix "
            "in claims_review.json for the matching claim_index. It does not "
            "regenerate the reviewed or corrected answer."
        ),
        "artifacts": {
            "answer_contract": "Answer contract JSON",
            "claims_review": "Claims review JSON",
            "validation_audit": "Validation audit JSON",
            "validated_document": "Validated document Markdown",
            "validated_document_docx": "Validated document DOCX",
            "validation_package": "Validation package Markdown",
        },
        "package_required": [
            "# Answer Validation Record",
            "## Assurance Boundary",
            "## Answer Contract",
            "## Answer-Contract Review",
            "## Review Coverage",
            "## Document Inventory",
            "## Claim Assessments",
        ],
        "dependency_note": "Claude should run scripts/check_dependencies.py before helper scripts.",
        "data_notes": [
            "Validation package scripts read local document inventory, source inventory, and claim review files.",
            "Review payloads expose bounded claim/source evidence for UI review.",
            "No external connector, upload path, remote SQL, or hosted notebook execution is used by default.",
        ],
        "caveats": [
            "Source identity, semantic support, reasoning, and legal-judgment boundaries are model-authored; fixed checks validate only record structure and mechanical observations in the specifically cited source snapshot.",
            "The MCP review payload is bounded; use JSON and Markdown outputs as the complete validation evidence set.",
            "ui_decisions.json is pending until Claude, the MCP widget, or fallback review records decisions.",
        ],
        "next_actions": [
            "Call validate_deep_research_review, then render_deep_research_review when MCP is available.",
            "Review source-identity, semantic-support, reasoning, contract, coverage, and professional-judgment items before delivery.",
            "Repair claims_review_draft.json or answer_contract.json and rerun packaging when validation_audit.json fails.",
        ],
    },
    "es": {
        "product_title": "Validación de respuestas",
        "handoff_title": "Entrega para revisión",
        "run_id": "ID de ejecución",
        "review_payload": "Datos de revisión",
        "run_intake": "Datos de ejecución",
        "pending_decisions": "Decisiones pendientes",
        "applied_decisions": "Decisiones aplicadas",
        "final_artifacts": "Artefactos finales",
        "review_in_codex": "Revisión profesional",
        "steps": (
            "Valide la referencia local vinculada por hash con `{tool}`.",
            "Abra el área de revisión con el token devuelto usando `{tool}`.",
            "Guarde las acciones del revisor con `{tool}`.",
            "Aplique las acciones del revisor con `{tool}`.",
        ),
        "handoff_notice": (
            "El guardado y la aplicación persistentes requieren la superficie MCP "
            "o el servidor local. El modo HTML estático solo permite copiar o "
            "descargar el JSON de decisiones."
        ),
        "columns": (
            "Tipo",
            "Afirmación o artefacto",
            "Acción sugerida",
            "Fuente",
            "Salida",
            "Estado",
        ),
        "claim": "Afirmación",
        "untitled_claim": "Afirmación sin título",
        "answer_contract_review": "Conformidad con el contrato de respuesta",
        "coverage_review": "Cobertura de selección de afirmaciones",
        "edit_hint": (
            "Al editar esta afirmación, la corrección del revisor se escribe en "
            "proposed_fix dentro de claims_review.json para el claim_index correspondiente. "
            "Esto no regenera la respuesta revisada o corregida."
        ),
        "artifacts": {
            "answer_contract": "JSON del contrato de respuesta",
            "claims_review": "JSON de revisión de afirmaciones",
            "validation_audit": "JSON de auditoría de validación",
            "validated_document": "Documento validado en Markdown",
            "validated_document_docx": "Documento validado en DOCX",
            "validation_package": "Paquete de validación en Markdown",
        },
        "package_required": [
            "# Registro de validación de la respuesta",
            "## Límite de aseguramiento",
            "## Contrato de respuesta",
            "## Revisión del contrato de respuesta",
            "## Cobertura de la revisión",
            "## Inventario del documento",
            "## Evaluaciones de las afirmaciones",
        ],
        "dependency_note": "Claude debe ejecutar scripts/check_dependencies.py antes de los scripts auxiliares.",
        "data_notes": [
            "Los scripts del paquete leen los inventarios locales del documento y de las fuentes, además de la revisión de afirmaciones.",
            "Los datos de revisión exponen un conjunto acotado de evidencias de afirmaciones y fuentes para la interfaz.",
            "De forma predeterminada no se utilizan conectores externos, rutas de carga, SQL remoto ni cuadernos alojados.",
        ],
        "caveats": [
            "La identidad de la fuente, el respaldo semántico, el razonamiento y los límites del juicio profesional los redacta el modelo; los controles fijos validan solo la estructura del registro y las observaciones mecánicas en la fuente citada.",
            "Los datos de revisión MCP están acotados; utilice las salidas JSON y Markdown como conjunto completo de evidencias de validación.",
            "ui_decisions.json permanece pendiente hasta que Claude, el widget MCP o la revisión alternativa registren las decisiones.",
        ],
        "next_actions": [
            "Ejecute validate_deep_research_review y, cuando MCP esté disponible, render_deep_research_review.",
            "Revise antes de la entrega la identidad de las fuentes, el respaldo semántico, el razonamiento, el contrato, la cobertura y el juicio profesional.",
            "Corrija claims_review_draft.json y vuelva a generar el paquete si validation_audit.json falla.",
        ],
    },
}


def _language_code(value: object | None) -> str:
    text = str(value or "en").strip().lower().replace("_", "-")
    return "es" if text.startswith("es") else "en"


def _copy(value: object | None) -> dict[str, Any]:
    return _REVIEW_COPY[_language_code(value)]


@dataclass(frozen=True)
class RunIntakeResult:
    """Run intake artifact written before validation packaging."""

    run_id: str
    path: Path


@dataclass(frozen=True)
class ReviewSessionResult:
    """Review-session artifacts for one answer-validation run."""

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


def _run_id(document_inventory_path: Path) -> str:
    timestamp = re.sub(r"[^0-9]", "", _utc_now())
    return f"{PLUGIN_NAME}-{_safe_slug(document_inventory_path.stem)}-{timestamp}"


def _write_json(path: Path, payload: dict[str, Any]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, default=str) + "\n",
        encoding="utf-8",
    )
    return path


def synchronize_final_artifact_sizes(final_artifacts_path: Path) -> None:
    """Refresh declared byte sizes after downstream artifacts reach final form."""

    payload = json.loads(final_artifacts_path.read_text(encoding="utf-8"))
    outputs = payload.get("outputs")
    if not isinstance(outputs, list):
        raise ValueError("final_artifacts.json outputs must be a list")
    output_dir = final_artifacts_path.parent.resolve()
    for output in outputs:
        if not isinstance(output, dict) or "size_bytes" not in output:
            continue
        relative = output.get("path")
        if not isinstance(relative, str) or not relative.strip():
            raise ValueError("final artifact output path must be a non-empty string")
        artifact_path = (output_dir / relative).resolve()
        if not artifact_path.is_relative_to(output_dir) or not artifact_path.is_file():
            raise ValueError(f"final artifact output is missing: {relative}")
        output["size_bytes"] = artifact_path.stat().st_size
    _write_json(final_artifacts_path, payload)


def _write_review_handoff_card(
    output_dir: Path,
    *,
    run_id: str,
    validate_tool: str,
    render_tool: str,
    save_tool: str,
    apply_tool: str,
    language: str,
) -> Path:
    copy = _copy(language)
    steps = copy["steps"]
    path = output_dir / "review_handoff.md"
    lines = [
        f"# {copy['product_title']} · {copy['handoff_title']}",
        "",
        f"- {copy['run_id']}: `{run_id}`",
        f"- {copy['review_payload']}: `review_payload.json`",
        f"- {copy['run_intake']}: `run_intake.json`",
        f"- {copy['pending_decisions']}: `ui_decisions.json`",
        f"- {copy['applied_decisions']}: `applied_decisions.json`",
        f"- {copy['final_artifacts']}: `final_artifacts.json`",
        "",
        f"## {copy['review_in_codex']}",
        f"1. {steps[0].format(tool=validate_tool)}",
        f"2. {steps[1].format(tool=render_tool)}",
        f"3. {steps[2].format(tool=save_tool)}",
        f"4. {steps[3].format(tool=apply_tool)}",
        "",
        copy["handoff_notice"],
    ]
    if _language_code(language) == "es":
        lines.insert(1, "<!-- Review Handoff -->")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


def _review_handoff_output_record(path: Path, language: str) -> dict[str, Any]:
    copy = _copy(language)
    required_text = [
        "Review Handoff",
        "review_payload.json",
        "ui_decisions.json",
        "applied_decisions.json",
        "final_artifacts.json",
    ]
    if _language_code(language) == "es":
        required_text[1:1] = [copy["handoff_title"], copy["review_in_codex"]]
    return {
        "path": path.name,
        "kind": "md",
        "status": "written",
        "required_text": required_text,
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
            "execution_location": "cowork_connected_folder",
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


def _run_path_reference(
    path: Path,
    client_engagement: dict[str, Any] | None,
) -> str:
    """Return an absolute unmanaged path or a portable managed-run reference."""

    if client_engagement is None:
        return path.as_posix()
    run_root_value = client_engagement.get("run_root")
    if not isinstance(run_root_value, str) or not run_root_value.strip():
        raise ValueError("Managed Answer Validator context has no run_root.")
    run_root = Path(run_root_value).expanduser().resolve(strict=True)
    resolved = path.expanduser().resolve(strict=True)
    try:
        relative = resolved.relative_to(run_root)
    except ValueError as exc:
        raise ValueError("Answer Validator path is outside the current run.") from exc
    if not relative.parts:
        raise ValueError("Answer Validator path must identify a run artifact.")
    return relative.as_posix()


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


def _review_columns(language: str) -> list[dict[str, str]]:
    labels = _copy(language)["columns"]
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


def _claim_item_type(verdict: str) -> str:
    if verdict == "supported":
        return "supported_claim"
    if verdict == "partially_supported":
        return "partially_supported_claim"
    if verdict == "not_supported":
        return "unsupported_claim"
    if verdict == "contradicted":
        return "contradicted_claim"
    if verdict == "uncertain":
        return "uncertain_claim"
    return "claim_review"


def _claim_title(claim: dict[str, Any], index: int, language: str) -> str:
    copy = _copy(language)
    claim_index = claim.get("claim_index") or index
    text = _clean_text(claim.get("claim_text"))
    if len(text) > 110:
        text = text[:107].rstrip() + "..."
    return f"{copy['claim']} {claim_index}: {text or copy['untitled_claim']}"


def _claim_items(
    claims_review: dict[str, Any], audit: dict[str, Any], language: str
) -> list[dict[str, Any]]:
    copy = _copy(language)
    claims = claims_review.get("claims", [])
    if not isinstance(claims, list):
        return []
    observations = {
        str(entry.get("claim_index")): entry
        for entry in audit.get("claim_observations", [])
        if isinstance(entry, dict)
    }
    items: list[dict[str, Any]] = []
    for index, claim in enumerate(claims[:MAX_CLAIM_ITEMS], start=1):
        if not isinstance(claim, dict):
            continue
        support = claim.get("support")
        support_status = (
            _clean_text(support.get("status")) if isinstance(support, dict) else ""
        )
        claim_data = dict(claim)
        claim_index = claim.get("claim_index") or index
        if claim.get("claim_index") is not None:
            claim_data.update(
                {
                    "target_artifact": "claims_review.json",
                    "target_records_key": "claims",
                    "target_id_field": "claim_index",
                    "target_record_id": str(claim_index),
                    "target_field": "proposed_fix",
                    "edit_hint": copy["edit_hint"],
                }
            )
        items.append(
            _base_item(
                f"claim-{claim_index}",
                _claim_item_type(support_status),
                _claim_title(claim, index, language),
                output_path="claims_review.json",
                allowed_actions=(
                    "accept",
                    "reject",
                    "edit",
                    "mark_unclear",
                    "request_more_documents",
                    "skip",
                ),
                recommended_action=_clean_text(claim.get("reviewer_action"))
                or "mark_unclear",
                evidence=[
                    {
                        "kind": "mechanical_source_observations",
                        "claim_ref": {
                            "artifact": "claims_review.json",
                            "records_key": "claims",
                            "id_field": "claim_index",
                            "record_id": str(claim_index),
                        },
                        "observations": observations.get(str(claim_index), {}),
                    }
                ],
                data=claim_data,
            )
        )
    return items


def _scope_items(claims_review: dict[str, Any], language: str) -> list[dict[str, Any]]:
    """Expose model-authored contract and coverage decisions for review."""

    copy = _copy(language)
    items: list[dict[str, Any]] = []
    for item_id, item_type, title_key, field in (
        (
            "answer-contract-review",
            "answer_contract_review",
            "answer_contract_review",
            "contract_review",
        ),
        (
            "claim-selection-coverage",
            "coverage_review",
            "coverage_review",
            "coverage_review",
        ),
    ):
        assessment = claims_review.get(field)
        if not isinstance(assessment, dict):
            continue
        items.append(
            _base_item(
                item_id,
                item_type,
                str(copy[title_key]),
                output_path="claims_review.json",
                allowed_actions=(
                    "accept",
                    "reject",
                    "edit",
                    "mark_unclear",
                    "request_more_documents",
                    "skip",
                ),
                recommended_action=_clean_text(assessment.get("reviewer_action"))
                or "mark_unclear",
                evidence=[
                    {
                        "kind": item_type,
                        "assessment_ref": {
                            "artifact": "claims_review.json",
                            "field": field,
                        },
                    }
                ],
                data={field: assessment},
            )
        )
    return items


def _audit_items(audit: dict[str, Any]) -> list[dict[str, Any]]:
    failed = audit.get("failed_checks", [])
    if not isinstance(failed, list):
        return []
    return [
        _base_item(
            f"audit-check-{index}",
            "audit_check",
            str(check),
            output_path="validation_audit.json",
            allowed_actions=("accept", "reject", "edit", "mark_unclear", "skip"),
            recommended_action="reject",
            evidence=[
                {
                    "kind": "validation_audit_check",
                    "status": "fail",
                    "check": check,
                    "invalid_claim_indices": audit.get("invalid_claim_indices"),
                    "missing_claim_text_indices": audit.get(
                        "missing_claim_text_indices"
                    ),
                    "missing_review_indices": audit.get("missing_review_indices"),
                }
            ],
            data={"check": check, "audit_ref": "validation_audit.json"},
        )
        for index, check in enumerate(failed, start=1)
    ]


def _artifact_items(
    paths: dict[str, Path], output_dir: Path, language: str
) -> list[dict[str, Any]]:
    labels = _copy(language)["artifacts"]
    items: list[dict[str, Any]] = []
    for index, (field, title) in enumerate(labels.items(), start=1):
        path_value = paths.get(field)
        if not path_value:
            continue
        path_ref = _as_output_ref(path_value, output_dir)
        exists = Path(path_value).exists()
        items.append(
            _base_item(
                f"artifact-{index}",
                "validation_artifact",
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


def _output_records(output_dir: Path, language: str) -> list[dict[str, Any]]:
    review_files = {
        "run_intake.json",
        "review_payload.json",
        "ui_decisions.json",
        "final_artifacts.json",
    }
    required_text_by_path = {
        "validation_package.md": _copy(language)["package_required"]
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
        required_text = required_text_by_path.get(relative)
        if required_text:
            output["required_text"] = required_text
            output["qa_checks"] = ["nonempty_text", "required_text"]
        outputs.append(output)
    return outputs


def write_run_intake(
    output_dir: Path,
    *,
    document_inventory_path: Path,
    source_inventory_path: Path,
    claims_review_path: Path,
    answer_contract_path: Path,
    document_inventory: dict[str, Any],
    source_inventory: dict[str, Any],
    claims_review: dict[str, Any],
    answer_contract: dict[str, Any],
    client_engagement: dict[str, Any] | None = None,
    client_run_id: str | None = None,
) -> RunIntakeResult:
    """Write run intake before validation package review."""

    context_run_id = (
        str(client_engagement["run_id"]) if client_engagement is not None else None
    )
    if client_run_id is not None and context_run_id not in {None, client_run_id}:
        raise ValueError("Answer Validator run ID does not match its client context.")
    run_id = context_run_id or client_run_id or _run_id(document_inventory_path)
    language = _language_code(claims_review.get("language"))
    copy = _copy(language)
    input_refs = [
        _run_path_reference(path, client_engagement)
        for path in (
            document_inventory_path,
            source_inventory_path,
            claims_review_path,
            answer_contract_path,
        )
    ]
    output_ref = _run_path_reference(output_dir, client_engagement)
    payload = {
        "schema_version": SCHEMA_VERSION,
        "plugin": PLUGIN_NAME,
        "workflow": WORKFLOW_NAME,
        "run_id": run_id,
        **(
            {"path_reference": "run_root_relative"}
            if client_engagement is not None
            else {}
        ),
        "created_at": _utc_now(),
        "language": language,
        "input_paths": input_refs,
        "output_dir": output_ref,
        "inferred_task": "answer_validation_review_payload",
        "assumptions": {
            "document_source_name": document_inventory.get("source_name"),
            "document_word_count": document_inventory.get("word_count"),
            "document_url_count": len(document_inventory.get("urls", []) or []),
            "source_count": len(source_inventory.get("sources", []) or []),
            "claim_count": len(claims_review.get("claims", []) or []),
            "validation_objective": claims_review.get("validation_objective"),
            "generation_route": answer_contract.get("generation_route"),
            "document_type": answer_contract.get("document_type"),
            "validation_profile": answer_contract.get("validation_profile"),
        },
        "unresolved_questions": [],
        "dependency_check": {
            "status": "not_run_by_script",
            "note": copy["dependency_note"],
        },
        "data_posture": {
            "local_files_read": input_refs,
            "external_connectors_used": [],
            "upload_paths_used": [],
            "remote_sql_execution_used": False,
            "hosted_notebook_execution_used": False,
            "notes": copy["data_notes"],
        },
        "status": "ready_for_validation_package",
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
    document_inventory_path: Path,
    source_inventory_path: Path,
    claims_review_path: Path,
    answer_contract_path: Path,
    document_inventory: dict[str, Any],
    source_inventory: dict[str, Any],
    claims_review: dict[str, Any],
    answer_contract: dict[str, Any],
    audit: dict[str, Any],
    paths: dict[str, Path],
    client_engagement: dict[str, Any] | None = None,
) -> ReviewSessionResult:
    """Write review payload, pending decisions, and final artifacts."""

    language = _language_code(claims_review.get("language"))
    copy = _copy(language)
    items: list[dict[str, Any]] = []
    items.extend(_audit_items(audit))
    items.extend(_scope_items(claims_review, language))
    items.extend(_claim_items(claims_review, audit, language))
    items.extend(_artifact_items(paths, output_dir, language))
    input_refs = [
        _run_path_reference(path, client_engagement)
        for path in (
            document_inventory_path,
            source_inventory_path,
            claims_review_path,
            answer_contract_path,
        )
    ]

    review_payload = {
        "schema_version": SCHEMA_VERSION,
        "plugin": PLUGIN_NAME,
        "workflow": WORKFLOW_NAME,
        "run_id": run_id,
        **(
            {"path_reference": "run_root_relative"}
            if client_engagement is not None
            else {}
        ),
        "created_at": _utc_now(),
        "language": language,
        "source_paths": [
            document_inventory.get("source_name"),
            *(document_inventory.get("urls", []) or []),
        ],
        "review_type": "answer_validation_review",
        "items": items,
        "item_count": len(items),
        "columns": _review_columns(language),
        "source_artifacts": {
            "run_intake": _as_output_ref(run_intake_path, output_dir),
            "document_inventory": input_refs[0],
            "source_inventory": input_refs[1],
            "claims_review_input": input_refs[2],
            "answer_contract_input": input_refs[3],
            "answer_contract": _as_output_ref(
                paths.get("answer_contract"),
                output_dir,
            ),
            "claims_review": _as_output_ref(paths.get("claims_review"), output_dir),
            "validation_audit": "validation_audit.json",
            "validated_document": _as_output_ref(
                paths.get("validated_document"), output_dir
            ),
            "validation_package": "validation_package.md",
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
            "record_integrity_status": audit.get("record_integrity_status"),
            "delivery_readiness": audit.get("delivery_readiness"),
            "failed_check_count": len(audit.get("failed_checks", []) or []),
            "claim_count": audit.get("claim_count", 0),
            "support_attention_count": len(
                audit.get("support_attention_claim_indices", []) or []
            ),
            "source_count": audit.get("source_count", 0),
            "document_url_count": audit.get("document_url_count", 0),
            "source_identity_attention_count": len(
                audit.get("source_identity_attention_claim_indices", []) or []
            ),
            "reasoning_attention_count": len(
                audit.get("reasoning_attention_claim_indices", []) or []
            ),
            "judgment_dependent_count": len(
                audit.get("judgment_dependent_claim_indices", []) or []
            ),
            "generation_route": answer_contract.get("generation_route"),
            "document_type": answer_contract.get("document_type"),
        },
    }
    review_payload_path = _write_json(
        output_dir / "review_payload.json",
        review_payload,
    )

    review_payload_sha256 = hashlib.sha256(review_payload_path.read_bytes()).hexdigest()
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
            "review_payload_sha256": review_payload_sha256,
            "decisions": [],
            "decision_count": 0,
            "status": "pending_review",
        },
    )

    review_handoff_path = _write_review_handoff_card(
        output_dir,
        run_id=run_id,
        validate_tool="validate_deep_research_review",
        render_tool="render_deep_research_review",
        save_tool="save_deep_research_decisions",
        apply_tool="apply_deep_research_decisions",
        language=language,
    )
    outputs = _output_records(output_dir, language)
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
            "review_payload_sha256": review_payload_sha256,
            "outputs": outputs,
            "caveats": copy["caveats"],
            "next_actions": copy["next_actions"],
            "status": "written_pending_review",
        },
    )
    _append_execution_trace(
        run_intake_path,
        final_artifacts_path,
        command=[
            "python",
            "plugins/deep-research-validator/scripts/package_validation.py",
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
