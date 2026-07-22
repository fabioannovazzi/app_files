"""Package a validated Registro Imprese/DIRE plan for professional review."""

from __future__ import annotations

import argparse
import json
import logging
from pathlib import Path
from typing import Any

from case_core import (
    PLUGIN_NAME,
    ensure_safe_output_dir,
    iso_now,
    load_json_object,
    sha256_file,
    write_private_json,
    write_private_text,
)

__all__ = ["package_practice", "main"]

LOGGER = logging.getLogger(__name__)
PLUGIN_ROOT = Path(__file__).resolve().parents[1]
DISCLAIMER = "BOZZA PER REVISIONE PROFESSIONALE — NON PRONTA PER IL DEPOSITO"
SPANISH_DISCLAIMER = (
    "BORRADOR PARA REVISIÓN PROFESIONAL — NO ESTÁ LISTO PARA SU PRESENTACIÓN"
)
PLAN_SECTIONS = (
    ("classification_proposals", "Qualificazioni da confermare"),
    ("position_matrix", "Matrice delle posizioni e degli enti"),
    ("dire_steps", "Percorso proposto in DIRE"),
    ("required_documents", "Documenti e allegati"),
    ("application_fields", "Campi da predisporre"),
    ("risks", "Rischi e controlli"),
    ("missing_information", "Informazioni mancanti"),
)
SPANISH_PLAN_SECTIONS = (
    ("classification_proposals", "Calificaciones pendientes de confirmación"),
    ("position_matrix", "Matriz de posiciones y organismos"),
    ("dire_steps", "Itinerario propuesto en DIRE"),
    ("required_documents", "Documentos y anexos"),
    ("application_fields", "Campos que deben prepararse"),
    ("risks", "Riesgos y controles"),
    ("missing_information", "Información pendiente"),
)
ITEM_TYPES = {
    "classification_proposals": "case_fact",
    "position_matrix": "practice_step",
    "dire_steps": "practice_step",
    "required_documents": "missing_information",
    "application_fields": "practice_step",
    "risks": "missing_information",
    "missing_information": "missing_information",
}
ALLOWED_ACTIONS = [
    "accept",
    "reject",
    "edit",
    "mark_unclear",
    "request_more_documents",
    "skip",
]
REVIEW_HANDOFF_REQUIRED_TEXT = [
    "Review Handoff",
    "review_payload.json",
    "ui_decisions.json",
    "applied_decisions.json",
    "final_artifacts.json",
]


def _output_language(output_dir: Path) -> str:
    """Resolve the supported language persisted by the initialized run."""

    run_intake = load_json_object(output_dir / "run_intake.json")
    value = str(run_intake.get("language") or "").strip().lower().replace("_", "-")
    primary = value.split("-", 1)[0]
    aliases = {"eng": "en", "ita": "it", "fra": "fr", "deu": "de", "spa": "es"}
    primary = aliases.get(primary, primary)
    return primary if primary in {"it", "en", "fr", "de", "es"} else "it"


def _review_handoff_required_text(language: str) -> list[str]:
    if language != "es":
        return REVIEW_HANDOFF_REQUIRED_TEXT
    return [
        "Review Handoff",
        "Entrega para revisión",
        "review_payload.json",
        "ui_decisions.json",
        "applied_decisions.json",
        "final_artifacts.json",
    ]


def _verify_hash(path: Path, expected: object, *, label: str) -> None:
    expected_text = str(expected or "").strip()
    if not path.is_file() or path.is_symlink():
        raise ValueError(f"bound {label} file is missing: {path}")
    actual = sha256_file(path)
    if not expected_text or actual != expected_text:
        raise ValueError(f"bound {label} hash does not match validation audit")


def _markdown_table(headers: list[str], rows: list[list[object]]) -> list[str]:
    def cell(value: object) -> str:
        return (
            str(value if value is not None else "—")
            .replace("|", "\\|")
            .replace("\n", " ")
        )

    return [
        "| " + " | ".join(headers) + " |",
        "| " + " | ".join("---" for _ in headers) + " |",
        *("| " + " | ".join(cell(value) for value in row) + " |" for row in rows),
    ]


def _item_sources(item: dict[str, Any]) -> str:
    sources = item.get("source_ids")
    return ", ".join(map(str, sources)) if isinstance(sources, list) else "—"


def _case_scope_rows(intake: dict[str, Any], *, language: str) -> list[list[object]]:
    """Return private case details selected for the professional workpaper."""

    rows: list[list[object]] = [
        [
            "Referencia interna" if language == "es" else "Riferimento interno",
            intake["client_reference"],
            "registrada" if language == "es" else "registrato",
        ],
    ]
    identity = intake.get("client_identity")
    if not isinstance(identity, dict):
        return rows
    labels = (
        ("name", "Cliente / sujeto" if language == "es" else "Cliente / soggetto"),
        ("tax_code", "Código fiscal" if language == "es" else "Codice fiscale"),
        ("vat_number", "Número de IVA" if language == "es" else "Partita IVA"),
        ("email", "Correo electrónico" if language == "es" else "Email"),
        ("pec", "PEC"),
        ("phone", "Teléfono" if language == "es" else "Telefono"),
        ("address", "Dirección" if language == "es" else "Indirizzo"),
    )
    rows.extend(
        [
            label,
            identity[field],
            "dato del expediente" if language == "es" else "dato del fascicolo",
        ]
        for field, label in labels
        if identity.get(field)
    )
    return rows


def _checklist_markdown(
    intake: dict[str, Any],
    plan: dict[str, Any],
    sources: dict[str, Any],
    audit: dict[str, Any],
    *,
    language: str,
) -> str:
    chamber = intake["competent_chamber"]
    operation = intake["requested_operation"]
    spanish = language == "es"
    lines = [
        f"# {SPANISH_DISCLAIMER if spanish else DISCLAIMER}",
        "",
        "## Alcance del caso" if spanish else "## Perimetro del caso",
        "",
        *_markdown_table(
            ["Concepto", "Valor", "Estado"] if spanish else ["Voce", "Valore", "Stato"],
            [
                *_case_scope_rows(intake, language=language),
                [
                    "Cámara competente" if spanish else "Camera competente",
                    chamber["name"],
                    chamber["confirmation_status"],
                ],
                ["Tenant SARI", chamber["tenant"], chamber["confirmation_status"]],
                [
                    "Forma jurídica" if spanish else "Forma giuridica",
                    intake["subject"]["legal_form"],
                    intake["subject"]["confirmation_status"],
                ],
                [
                    "Actividad" if spanish else "Attività",
                    intake["activity"]["description"],
                    intake["activity"]["classification_status"],
                ],
                [
                    "Operación" if spanish else "Operazione",
                    operation["description"],
                    operation["confirmation_status"],
                ],
                [
                    "Fecha de efecto" if spanish else "Data effetto",
                    operation["effective_date"],
                    operation["confirmation_status"],
                ],
                [
                    "Posiciones consideradas" if spanish else "Posizioni considerate",
                    ", ".join(operation["position_types"]),
                    operation["confirmation_status"],
                ],
            ],
        ),
        "",
        "## Cuestión profesional" if spanish else "## Quesito professionale",
        "",
        intake["professional_question"],
        "",
        (
            "## Fuentes oficiales seleccionadas"
            if spanish
            else "## Fonti ufficiali selezionate"
        ),
        "",
    ]
    source_rows: list[list[object]] = []
    for source in sources["sources"]:
        source_rows.append(
            [
                source.get("source_id"),
                source.get("title") or source.get("chamber_title"),
                source.get("territorial_applicability") or source.get("chamber_title"),
                source.get("updated_date")
                or source.get("retrieved_at")
                or source.get("registered_at"),
                source.get("official_url"),
            ]
        )
    lines.extend(
        _markdown_table(
            (
                ["ID", "Título", "Territorio", "Fecha de la fuente/adquisición", "URL"]
                if spanish
                else ["ID", "Titolo", "Territorio", "Data fonte/acquisizione", "URL"]
            ),
            source_rows,
        )
    )
    lines.extend(
        [
            "",
            "## Resumen del caso" if spanish else "## Sintesi del caso",
            "",
            plan["case_summary"],
            "",
        ]
    )
    for key, title in (SPANISH_PLAN_SECTIONS if spanish else PLAN_SECTIONS):
        lines.extend([f"## {title}", ""])
        items = plan.get(key) or []
        if not items:
            lines.extend(
                [
                    (
                        "_No se ha propuesto ningún elemento._"
                        if spanish
                        else "_Nessuna voce proposta._"
                    ),
                    "",
                ]
            )
            continue
        ordered = sorted(
            items,
            key=lambda item: (
                item.get("sequence") is None,
                item.get("sequence") or 0,
                str(item.get("id") or ""),
            ),
        )
        for item in ordered:
            lines.extend(
                [
                    f"### {item['id']} — {item['title']}",
                    "",
                    item["detail"],
                    "",
                    f"- {'Sistema/área' if spanish else 'Sistema/area'}: "
                    f"{item.get('system') or ('no indicado' if spanish else 'non indicato')}",
                    f"- {'Estado de la revisión' if spanish else 'Stato revisione'}: "
                    f"{item['review_status']}",
                    f"- {'Fuentes' if spanish else 'Fonti'}: {_item_sources(item)}",
                    f"- {'Hechos del caso' if spanish else 'Fatti del caso'}: "
                    f"{', '.join(item.get('case_fact_ids') or []) or ('ninguno indicado' if spanish else 'nessuno indicato')}",
                    "",
                ]
            )
    lines.extend(
        [
            (
                "## Pregunta para el servicio de soporte SARI (borrador)"
                if spanish
                else "## Domanda da inviare al supporto SARI (bozza)"
            ),
            "",
            plan["sari_question_draft"],
            "",
        ]
    )
    if plan["limitations"]:
        lines.extend(
            [
                "## Limitaciones" if spanish else "## Limiti",
                "",
                *(f"- {item}" for item in plan["limitations"]),
                "",
            ]
        )
    lines.extend(
        [
            (
                "## Resultado de los controles mecánicos"
                if spanish
                else "## Esito dei controlli meccanici"
            ),
            "",
            f"- {'Estado' if spanish else 'Stato'}: {audit['status']}",
            f"- {'Errores' if spanish else 'Errori'}: {audit['error_count']}",
            f"- {'Bloqueos' if spanish else 'Blocchi'}: {audit['blocker_count']}",
            (
                "- Los scripts no han elegido ninguna clasificación jurídica."
                if spanish
                else "- Nessuna classificazione giuridica è stata scelta dagli script."
            ),
            "",
        ]
    )
    return "\n".join(lines)


def _sari_question_markdown(
    intake: dict[str, Any], plan: dict[str, Any], *, language: str
) -> str:
    chamber = intake["competent_chamber"]
    spanish = language == "es"
    return "\n".join(
        [
            (
                "# Pregunta para el servicio de soporte SARI — borrador"
                if spanish
                else "# Quesito per il supporto SARI — bozza"
            ),
            "",
            f"{'Destinatario propuesto' if spanish else 'Destinatario proposto'}: "
            f"{chamber['name']}",
            f"{'Referencia del caso' if spanish else 'Riferimento del caso'}: "
            f"{intake['client_reference']}",
            "",
            "## Pregunta" if spanish else "## Quesito",
            "",
            plan["sari_question_draft"],
            "",
            (
                "_El profesional debe aprobar el texto antes de cualquier envío manual. Vera no envía la pregunta._"
                if spanish
                else "_Far approvare il testo dal professionista prima di qualsiasi invio manuale. Vera non invia il quesito._"
            ),
            "",
        ]
    )


def _review_items(
    plan: dict[str, Any],
    sources: dict[str, Any],
    audit: dict[str, Any],
    *,
    language: str,
) -> list[dict[str, Any]]:
    spanish = language == "es"
    items: list[dict[str, Any]] = []
    for source in sources["sources"]:
        source_id = source["source_id"]
        items.append(
            {
                "id": f"source-{source_id}",
                "item_type": "official_source",
                "title": source.get("title")
                or (
                    f"Fuente oficial {source_id}"
                    if spanish
                    else f"Fonte ufficiale {source_id}"
                ),
                "source_path": source.get("artifact_path"),
                "output_path": "official_sources.json",
                "allowed_actions": ALLOWED_ACTIONS,
                "recommended_action": "mark_unclear",
                "evidence": [],
                "data": {
                    "source_id": source_id,
                    "publisher": source.get("publisher"),
                    "territorial_applicability": source.get("territorial_applicability")
                    or source.get("chamber_title"),
                    "source_date": source.get("updated_date")
                    or source.get("retrieved_at")
                    or source.get("registered_at"),
                    "official_url": source.get("official_url")
                    or source.get("source_url"),
                    "applicability_status": source.get("applicability_status")
                    or source.get("selection_status"),
                    "target_artifact": "official_sources.json",
                    "target_id_field": "source_id",
                    "target_record_id": source_id,
                    "target_field": "selection_status",
                },
                "status": "needs_review",
            }
        )
    for array_name, _ in PLAN_SECTIONS:
        for item in plan.get(array_name) or []:
            item_id = item["id"]
            item_type = ITEM_TYPES[array_name]
            items.append(
                {
                    "id": f"plan-{item_id}",
                    "item_type": item_type,
                    "title": item["title"],
                    "source_path": "practice_plan_validated.json",
                    "output_path": "dire_practice_plan.json",
                    "allowed_actions": ALLOWED_ACTIONS,
                    "recommended_action": (
                        "accept"
                        if item["review_status"] == "confirmed"
                        else "mark_unclear"
                    ),
                    "evidence": [
                        {"source_id": source_id} for source_id in item["source_ids"]
                    ],
                    "data": {
                        "record_id": item_id,
                        "system": item.get("system"),
                        "sequence": item.get("sequence"),
                        "detail": item["detail"],
                        "proposed_value": item.get("proposed_value"),
                        "document_quotes": item.get("document_quotes") or [],
                        "review_status": item["review_status"],
                        "source_ids": item["source_ids"],
                        "case_fact_ids": item["case_fact_ids"],
                        "confirmation": item.get("confirmation"),
                        "target_artifact": "dire_practice_plan.json",
                        "target_id_field": "id",
                        "target_record_id": item_id,
                        "target_field": "detail",
                    },
                    "status": "needs_review",
                }
            )
    items.append(
        {
            "id": "audit-practice-validation",
            "item_type": "audit_check",
            "title": (
                "Controles mecánicos de la práctica"
                if spanish
                else "Controlli meccanici della pratica"
            ),
            "source_path": "practice_validation_audit.json",
            "output_path": None,
            "allowed_actions": ["accept", "mark_unclear", "skip"],
            "recommended_action": (
                "accept" if audit["status"] == "passed" else "mark_unclear"
            ),
            "evidence": [],
            "data": {
                "validation_status": audit["status"],
                "error_count": audit["error_count"],
                "blocker_count": audit["blocker_count"],
            },
            "status": "needs_review",
        }
    )
    return items


def _case_context(intake: dict[str, Any], plan: dict[str, Any]) -> dict[str, Any]:
    """Return the real private case context needed for professional review."""

    return {
        "client_reference": intake["client_reference"],
        "client_identity": intake.get("client_identity") or {},
        "competent_chamber": intake["competent_chamber"],
        "subject": intake["subject"],
        "activity": intake["activity"],
        "requested_operation": intake["requested_operation"],
        "current_positions": intake.get("current_positions") or [],
        "professional_question": intake["professional_question"],
        "case_summary": plan["case_summary"],
        "review_context": plan.get("review_context") or {},
        "sari_question_draft": plan["sari_question_draft"],
    }


def _artifact_record(
    path: Path,
    output_dir: Path,
    *,
    kind: str,
    required_text: list[str] | None = None,
) -> dict[str, Any]:
    record: dict[str, Any] = {
        "path": path.relative_to(output_dir).as_posix(),
        "kind": kind,
        "status": "written",
        "sha256": sha256_file(path),
    }
    if required_text:
        record["required_text"] = required_text
        record["qa_checks"] = ["nonempty_text", "required_text"]
    return record


def _update_run_intake(
    output_dir: Path,
    *,
    status: str,
    outputs: list[dict[str, Any]],
) -> None:
    path = output_dir / "run_intake.json"
    if not path.exists():
        return
    payload = load_json_object(path)
    trace = payload.get("execution_trace")
    if not isinstance(trace, list):
        trace = []
    trace.append(
        {
            "step_id": f"package_practice_{len(trace) + 1}",
            "kind": "deterministic_packaging",
            "command": [
                "python",
                "scripts/package_practice.py",
                "--output-dir",
                output_dir.as_posix(),
            ],
            "execution_location": "local_python",
            "status": "passed",
            "inputs": [
                "case_intake_validated.json",
                "practice_plan_validated.json",
                "official_sources.json",
                "practice_validation_audit.json",
            ],
            "outputs": [item["path"] for item in outputs],
        }
    )
    payload["execution_trace"] = trace
    payload["status"] = status
    write_private_json(path, payload)


def package_practice(output_dir: Path) -> dict[str, Any]:
    """Create review artifacts after verifying exact validation bindings."""

    output_dir = ensure_safe_output_dir(output_dir, plugin_root=PLUGIN_ROOT)
    language = _output_language(output_dir)
    intake_path = output_dir / "case_intake_validated.json"
    plan_path = output_dir / "practice_plan_validated.json"
    sources_path = output_dir / "official_sources.json"
    audit_path = output_dir / "practice_validation_audit.json"
    intake = load_json_object(intake_path)
    plan = load_json_object(plan_path)
    sources = load_json_object(sources_path)
    audit = load_json_object(audit_path)
    if audit.get("status") == "schema_error":
        raise ValueError("cannot package a case with schema errors")
    if not all(
        payload.get("plugin") == PLUGIN_NAME
        and payload.get("run_id") == intake.get("run_id")
        for payload in (plan, sources, audit)
    ):
        raise ValueError("validated inputs do not belong to the same plugin run")
    validated_bindings = audit.get("validated_bindings")
    bindings = audit.get("bindings")
    if not isinstance(validated_bindings, dict) or not isinstance(bindings, dict):
        raise ValueError("validation audit is missing exact input bindings")
    _verify_hash(
        intake_path,
        validated_bindings.get("case_intake_validated_sha256"),
        label="validated case intake",
    )
    _verify_hash(
        plan_path,
        validated_bindings.get("practice_plan_validated_sha256"),
        label="validated practice plan",
    )
    _verify_hash(
        sources_path,
        bindings.get("official_sources_sha256"),
        label="official sources",
    )
    inventory_hash = bindings.get("local_evidence_inventory_sha256")
    if inventory_hash:
        _verify_hash(
            output_dir / "local_evidence_inventory.json",
            inventory_hash,
            label="local evidence inventory",
        )

    dire_plan_path = write_private_json(output_dir / "dire_practice_plan.json", plan)
    checklist_path = write_private_text(
        output_dir / "studio_checklist.md",
        _checklist_markdown(
            intake,
            plan,
            sources,
            audit,
            language=language,
        ),
    )
    question_path = write_private_text(
        output_dir / "sari_question_draft.md",
        _sari_question_markdown(intake, plan, language=language),
    )
    review_items = _review_items(plan, sources, audit, language=language)
    package_status = (
        "ready_for_professional_review"
        if audit["status"] == "passed"
        else "partial_review"
    )
    review_payload = {
        "schema_version": "1.0",
        "plugin": PLUGIN_NAME,
        "workflow": PLUGIN_NAME,
        "run_id": intake["run_id"],
        "language": language,
        "source_paths": [
            "case_intake_validated.json",
            "practice_plan_validated.json",
            "official_sources.json",
            "practice_validation_audit.json",
        ],
        "review_type": "registro_imprese_practice_review",
        "status": package_status,
        "case_context": _case_context(intake, plan),
        "item_count": len(review_items),
        "items": review_items,
        "columns": ["id", "item_type", "title", "status"],
        "source_artifacts": [
            {"path": "official_sources.json", "source_count": sources["source_count"]},
            {"path": "practice_validation_audit.json", "status": audit["status"]},
        ],
        "allowed_actions": ALLOWED_ACTIONS,
        "filing_status": "not_filed",
        "filing_authorized": False,
    }
    review_payload_path = write_private_json(
        output_dir / "review_payload.json", review_payload
    )
    ui_decisions_path = write_private_json(
        output_dir / "ui_decisions.json",
        {
            "schema_version": "1.0",
            "plugin": PLUGIN_NAME,
            "workflow": PLUGIN_NAME,
            "run_id": intake["run_id"],
            "language": language,
            "review_payload_path": review_payload_path.name,
            "review_payload_sha256": sha256_file(review_payload_path),
            "decisions": [],
            "decision_count": 0,
            "item_count": len(review_items),
            "decided_at": None,
            "decision_source": "pending_review",
            "status": "pending_review",
        },
    )
    handoff_lines = (
        [
            "# Entrega para revisión",
            "<!-- Review Handoff -->",
            "",
            "Artefactos: review_payload.json → ui_decisions.json → applied_decisions.json → final_artifacts.json.",
            "",
            "1. Valide con `validate_registro_imprese_sari_review`.",
            "2. Abra la revisión profesional en Codex con `render_registro_imprese_sari_review`.",
            "3. Guarde las decisiones con `save_registro_imprese_sari_decisions`.",
            "4. Aplique el manifiesto de decisiones con `apply_registro_imprese_sari_decisions`.",
            "",
            "La aplicación de decisiones nunca inicia sesión, firma, presenta ni marca la práctica como lista para su presentación.",
            "",
        ]
        if language == "es"
        else [
            "# Review Handoff",
            "",
            "Artifacts: review_payload.json → ui_decisions.json → applied_decisions.json → final_artifacts.json.",
            "",
            "1. Validate with `validate_registro_imprese_sari_review`.",
            "2. Open the professional review in Codex with `render_registro_imprese_sari_review`.",
            "3. Persist choices with `save_registro_imprese_sari_decisions`.",
            "4. Apply the decision manifest with `apply_registro_imprese_sari_decisions`.",
            "",
            "Applying decisions never logs in, signs, submits, or marks the practice ready to file.",
            "",
        ]
    )
    handoff_path = write_private_text(
        output_dir / "review_handoff.md", "\n".join(handoff_lines)
    )
    outputs = [
        _artifact_record(dire_plan_path, output_dir, kind="json"),
        _artifact_record(checklist_path, output_dir, kind="md"),
        _artifact_record(question_path, output_dir, kind="md"),
        _artifact_record(review_payload_path, output_dir, kind="json"),
        _artifact_record(ui_decisions_path, output_dir, kind="json"),
        _artifact_record(
            handoff_path,
            output_dir,
            kind="md",
            required_text=_review_handoff_required_text(language),
        ),
        _artifact_record(audit_path, output_dir, kind="json"),
    ]
    blockers = [
        {
            "code": issue["code"],
            "path": issue["path"],
            "message": (
                "Este control de validación no se ha superado; consulte practice_validation_audit.json para el diagnóstico técnico."
                if language == "es"
                else issue["message"]
            ),
        }
        for issue in audit["issues"]
        if issue["severity"] == "blocker"
    ]
    final_artifacts = {
        "schema_version": "1.0",
        "plugin": PLUGIN_NAME,
        "workflow": PLUGIN_NAME,
        "run_id": intake["run_id"],
        "language": language,
        "created_at": iso_now(),
        "status": package_status,
        "professional_review_required": True,
        "ready_to_file": False,
        "filing_status": "not_filed",
        "portal_access_performed": False,
        "signature_performed": False,
        "submission_performed": False,
        "review_payload_sha256": sha256_file(review_payload_path),
        "validation_audit_sha256": sha256_file(audit_path),
        "bindings": {**bindings, **validated_bindings},
        "outputs": outputs,
        "caveats": [
            *plan["limitations"],
            (
                f"Estado de la validación mecánica: {audit['status']}."
                if language == "es"
                else f"Mechanical validation status: {audit['status']}."
            ),
            (
                "Toda fuente SARI o institucional seleccionada requiere todavía que un profesional confirme su aplicabilidad."
                if language == "es"
                else "A selected SARI or institutional source still requires professional applicability review."
            ),
        ],
        "next_actions": (
            [
                "Resuelva todos los bloqueos registrados y confirme visualmente cualquier texto obtenido mediante OCR.",
                "Complete la secuencia profesional de validación, visualización, guardado y aplicación.",
                "Mantenga el acceso al portal, la firma y la presentación dentro del proceso autorizado y separado del despacho.",
            ]
            if language == "es"
            else [
                "Resolve every recorded blocker and visually confirm any OCR-derived text.",
                "Complete the validate/render/save/apply professional review handoff.",
                "Keep portal access, signature, and submission in the studio's separate authorized process.",
            ]
        ),
        "blockers": blockers,
    }
    write_private_json(output_dir / "final_artifacts.json", final_artifacts)
    _update_run_intake(output_dir, status=package_status, outputs=outputs)
    return final_artifacts


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        result = package_practice(args.output_dir)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        LOGGER.error("PACKAGING_BLOCKED: %s", exc)
        return 2
    LOGGER.info(
        "Packaged %s with %s blockers; ready_to_file=%s",
        result["status"],
        len(result["blockers"]),
        result["ready_to_file"],
    )
    return 0


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    raise SystemExit(main())
