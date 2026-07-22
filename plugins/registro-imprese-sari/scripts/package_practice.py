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
PLAN_SECTIONS = (
    ("classification_proposals", "Qualificazioni da confermare"),
    ("position_matrix", "Matrice delle posizioni e degli enti"),
    ("dire_steps", "Percorso proposto in DIRE"),
    ("required_documents", "Documenti e allegati"),
    ("application_fields", "Campi da predisporre"),
    ("risks", "Rischi e controlli"),
    ("missing_information", "Informazioni mancanti"),
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


def _case_scope_rows(intake: dict[str, Any]) -> list[list[object]]:
    """Return private case details selected for the professional workpaper."""

    rows: list[list[object]] = [
        ["Riferimento interno", intake["client_reference"], "registrato"],
    ]
    identity = intake.get("client_identity")
    if not isinstance(identity, dict):
        return rows
    labels = (
        ("name", "Cliente / soggetto"),
        ("tax_code", "Codice fiscale"),
        ("vat_number", "Partita IVA"),
        ("email", "Email"),
        ("pec", "PEC"),
        ("phone", "Telefono"),
        ("address", "Indirizzo"),
    )
    rows.extend(
        [label, identity[field], "dato del fascicolo"]
        for field, label in labels
        if identity.get(field)
    )
    return rows


def _checklist_markdown(
    intake: dict[str, Any],
    plan: dict[str, Any],
    sources: dict[str, Any],
    audit: dict[str, Any],
) -> str:
    chamber = intake["competent_chamber"]
    operation = intake["requested_operation"]
    lines = [
        f"# {DISCLAIMER}",
        "",
        "## Perimetro del caso",
        "",
        *_markdown_table(
            ["Voce", "Valore", "Stato"],
            [
                *_case_scope_rows(intake),
                ["Camera competente", chamber["name"], chamber["confirmation_status"]],
                ["Tenant SARI", chamber["tenant"], chamber["confirmation_status"]],
                [
                    "Forma giuridica",
                    intake["subject"]["legal_form"],
                    intake["subject"]["confirmation_status"],
                ],
                [
                    "Attività",
                    intake["activity"]["description"],
                    intake["activity"]["classification_status"],
                ],
                [
                    "Operazione",
                    operation["description"],
                    operation["confirmation_status"],
                ],
                [
                    "Data effetto",
                    operation["effective_date"],
                    operation["confirmation_status"],
                ],
                [
                    "Posizioni considerate",
                    ", ".join(operation["position_types"]),
                    operation["confirmation_status"],
                ],
            ],
        ),
        "",
        "## Quesito professionale",
        "",
        intake["professional_question"],
        "",
        "## Fonti ufficiali selezionate",
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
            ["ID", "Titolo", "Territorio", "Data fonte/acquisizione", "URL"],
            source_rows,
        )
    )
    lines.extend(["", "## Sintesi del caso", "", plan["case_summary"], ""])
    for key, title in PLAN_SECTIONS:
        lines.extend([f"## {title}", ""])
        items = plan.get(key) or []
        if not items:
            lines.extend(["_Nessuna voce proposta._", ""])
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
                    f"- Sistema/area: {item.get('system') or 'non indicato'}",
                    f"- Stato revisione: {item['review_status']}",
                    f"- Fonti: {_item_sources(item)}",
                    f"- Fatti del caso: {', '.join(item.get('case_fact_ids') or []) or 'nessuno indicato'}",
                    "",
                ]
            )
    lines.extend(
        [
            "## Domanda da inviare al supporto SARI (bozza)",
            "",
            plan["sari_question_draft"],
            "",
        ]
    )
    if plan["limitations"]:
        lines.extend(
            [
                "## Limiti",
                "",
                *(f"- {item}" for item in plan["limitations"]),
                "",
            ]
        )
    lines.extend(
        [
            "## Esito dei controlli meccanici",
            "",
            f"- Stato: {audit['status']}",
            f"- Errori: {audit['error_count']}",
            f"- Blocchi: {audit['blocker_count']}",
            "- Nessuna classificazione giuridica è stata scelta dagli script.",
            "",
        ]
    )
    return "\n".join(lines)


def _sari_question_markdown(intake: dict[str, Any], plan: dict[str, Any]) -> str:
    chamber = intake["competent_chamber"]
    return "\n".join(
        [
            "# Quesito per il supporto SARI — bozza",
            "",
            f"Destinatario proposto: {chamber['name']}",
            f"Riferimento del caso: {intake['client_reference']}",
            "",
            "## Quesito",
            "",
            plan["sari_question_draft"],
            "",
            "_Far approvare il testo dal professionista prima di qualsiasi invio manuale. Vera non invia il quesito._",
            "",
        ]
    )


def _review_items(
    plan: dict[str, Any],
    sources: dict[str, Any],
    audit: dict[str, Any],
) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    for source in sources["sources"]:
        source_id = source["source_id"]
        items.append(
            {
                "id": f"source-{source_id}",
                "item_type": "official_source",
                "title": source.get("title") or f"Fonte ufficiale {source_id}",
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
            "title": "Controlli meccanici della pratica",
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
        _checklist_markdown(intake, plan, sources, audit),
    )
    question_path = write_private_text(
        output_dir / "sari_question_draft.md",
        _sari_question_markdown(intake, plan),
    )
    review_items = _review_items(plan, sources, audit)
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
    handoff_path = write_private_text(
        output_dir / "review_handoff.md",
        "\n".join(
            [
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
        ),
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
            required_text=REVIEW_HANDOFF_REQUIRED_TEXT,
        ),
        _artifact_record(audit_path, output_dir, kind="json"),
    ]
    blockers = [
        {
            "code": issue["code"],
            "path": issue["path"],
            "message": issue["message"],
        }
        for issue in audit["issues"]
        if issue["severity"] == "blocker"
    ]
    final_artifacts = {
        "schema_version": "1.0",
        "plugin": PLUGIN_NAME,
        "workflow": PLUGIN_NAME,
        "run_id": intake["run_id"],
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
            f"Mechanical validation status: {audit['status']}.",
            "A selected SARI or institutional source still requires professional applicability review.",
        ],
        "next_actions": [
            "Resolve every recorded blocker and visually confirm any OCR-derived text.",
            "Complete the validate/render/save/apply professional review handoff.",
            "Keep portal access, signature, and submission in the studio's separate authorized process.",
        ],
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
