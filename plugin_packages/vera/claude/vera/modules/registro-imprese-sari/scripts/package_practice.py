"""Package a validated Registro Imprese/DIRE plan for professional review."""

from __future__ import annotations

import argparse
import json
import logging
from pathlib import Path
from typing import Any

from case_core import (
    PLUGIN_NAME,
    AssuranceContractError,
    ensure_safe_output_dir,
    iso_now,
    load_json_object,
    load_running_case_context,
    require_case_artifact_run,
    sha256_file,
    write_private_json,
    write_private_text,
)
from registry_display import handoff, status, text

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
            text(language, "Riferimento interno"),
            intake["client_reference"],
            text(language, "registrato"),
        ],
    ]
    identity = intake.get("client_identity")
    if not isinstance(identity, dict):
        return rows
    labels = (
        ("name", text(language, "Cliente / soggetto")),
        ("tax_code", text(language, "Codice fiscale")),
        ("vat_number", text(language, "Partita IVA")),
        ("email", text(language, "Email")),
        ("pec", "PEC"),
        ("phone", text(language, "Telefono")),
        ("address", text(language, "Indirizzo")),
    )
    rows.extend(
        [
            label,
            identity[field],
            text(language, "dato del fascicolo"),
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
    lines = [
        f"# {text(language, 'checklist_title')}",
        "",
        text(language, DISCLAIMER),
        "",
        plan["case_summary"],
        "",
        text(language, "## Perimetro del caso"),
        "",
        *_markdown_table(
            [text(language, "Voce"), text(language, "Valore"), text(language, "Stato")],
            [
                *_case_scope_rows(intake, language=language),
                [
                    text(language, "Camera competente"),
                    chamber["name"],
                    status(language, chamber["confirmation_status"]),
                ],
                [
                    "SARI",
                    status(language, chamber["tenant"]),
                    status(language, chamber["confirmation_status"]),
                ],
                [
                    text(language, "Forma giuridica"),
                    intake["subject"]["legal_form"],
                    status(language, intake["subject"]["confirmation_status"]),
                ],
                [
                    text(language, "Attività"),
                    intake["activity"]["description"],
                    status(language, intake["activity"]["classification_status"]),
                ],
                [
                    text(language, "Operazione"),
                    operation["description"],
                    status(language, operation["confirmation_status"]),
                ],
                [
                    text(language, "Data effetto"),
                    operation["effective_date"],
                    status(language, operation["confirmation_status"]),
                ],
                [
                    text(language, "Posizioni considerate"),
                    ", ".join(operation["position_types"]),
                    status(language, operation["confirmation_status"]),
                ],
            ],
        ),
        "",
        text(language, "## Quesito professionale"),
        "",
        intake["professional_question"],
        "",
        (text(language, "## Fonti ufficiali selezionate")),
        "",
    ]
    for source in sources["sources"]:
        title = (
            source.get("title") or source.get("chamber_title") or source["source_id"]
        )
        url = source.get("official_url") or source.get("source_url")
        territory = (
            source.get("territorial_applicability")
            or source.get("chamber_title")
            or "—"
        )
        source_date = (
            source.get("updated_date")
            or source.get("retrieved_at")
            or source.get("registered_at")
            or "—"
        )
        lines.extend(
            [
                f"- [{title}]({url})" if url else f"- {title}",
                f"  {text(language, 'Territorio')}: {territory}; {text(language, 'Data fonte/acquisizione')}: {source_date}. ID: {source['source_id']}.",
                "",
            ]
        )
    for key, title in [(key, text(language, title)) for key, title in PLAN_SECTIONS]:
        lines.extend([f"## {title}", ""])
        items = plan.get(key) or []
        if not items:
            lines.extend(
                [
                    (text(language, "_Nessuna voce proposta._")),
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
                    f"### {item['title']}",
                    "",
                    item["detail"],
                    "",
                    *(
                        [
                            f"{text(language, 'proposed_value')}: {item['proposed_value']}",
                            "",
                        ]
                        if item.get("proposed_value") is not None
                        else []
                    ),
                    *(
                        [f"- {text(language, 'Sistema/area')}: {item['system']}"]
                        if item.get("system")
                        else []
                    ),
                    f"- {text(language, 'Stato revisione')}: "
                    f"{status(language, item['review_status'])}",
                    f"- {text(language, 'Fonti')}: {_item_sources(item)}",
                    "",
                    f"<details><summary>{text(language, 'technical_evidence')}</summary>",
                    "",
                    f"- ID: {item['id']}",
                    f"- {text(language, 'Fatti del caso')}: "
                    f"{', '.join(item.get('case_fact_ids') or []) or (text(language, 'nessuno indicato'))}",
                    "",
                    "</details>",
                    "",
                ]
            )
    lines.extend(
        [
            (text(language, "## Domanda da inviare al supporto SARI (bozza)")),
            "",
            plan["sari_question_draft"],
            "",
        ]
    )
    if plan["limitations"]:
        lines.extend(
            [
                text(language, "## Limiti"),
                "",
                *(f"- {item}" for item in plan["limitations"]),
                "",
            ]
        )
    lines.extend(
        [
            (text(language, "## Esito dei controlli meccanici")),
            "",
            f"- {text(language, 'Stato')}: {status(language, audit['status'])}",
            f"- {text(language, 'Errori')}: {audit['error_count']}",
            f"- {text(language, 'Blocchi')}: {audit['blocker_count']}",
            (
                text(
                    language,
                    "- Nessuna classificazione giuridica è stata scelta dagli script.",
                )
            ),
            "",
        ]
    )
    return "\n".join(lines)


def _sari_question_markdown(
    intake: dict[str, Any], plan: dict[str, Any], *, language: str
) -> str:
    chamber = intake["competent_chamber"]
    return "\n".join(
        [
            (text(language, "# Quesito per il supporto SARI — bozza")),
            "",
            f"{text(language, 'Destinatario proposto')}: " f"{chamber['name']}",
            f"{text(language, 'Riferimento del caso')}: "
            f"{intake['client_reference']}",
            "",
            text(language, "## Quesito"),
            "",
            plan["sari_question_draft"],
            "",
            (
                text(
                    language,
                    "_Far approvare il testo dal professionista prima di qualsiasi invio manuale. Vera non invia il quesito._",
                )
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
    items: list[dict[str, Any]] = []
    for source in sources["sources"]:
        source_id = source["source_id"]
        items.append(
            {
                "id": f"source-{source_id}",
                "item_type": "official_source",
                "title": source.get("title")
                or (f"{text(language, 'Fonte ufficiale')} {source_id}"),
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
            "title": (text(language, "Controlli meccanici della pratica")),
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
    output_reference = (
        "outputs"
        if payload.get("path_reference") == "run_root_relative"
        else output_dir.as_posix()
    )
    trace.append(
        {
            "step_id": f"package_practice_{len(trace) + 1}",
            "kind": "deterministic_packaging",
            "command": [
                "python",
                "scripts/package_practice.py",
                "--output-dir",
                output_reference,
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
    handoff_lines = handoff(language)
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
                f"{text(language, 'validation_status')}: {status(language, audit['status'])}."
            ),
            (
                text(
                    language,
                    "A selected SARI or institutional source still requires professional applicability review.",
                )
            ),
        ],
        "next_actions": (
            [
                text(
                    language,
                    "Resolve every recorded blocker and visually confirm any OCR-derived text.",
                ),
                text(
                    language,
                    "Complete the validate/render/save/apply professional review handoff.",
                ),
                text(
                    language,
                    "Keep portal access, signature, and submission in the studio's separate authorized process.",
                ),
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
    parser.add_argument("--client-engagement", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        input_paths = [
            args.output_dir / name
            for name in (
                "run_intake.json",
                "case_intake_validated.json",
                "practice_plan_validated.json",
                "official_sources.json",
                "practice_validation_audit.json",
            )
        ]
        inventory_path = args.output_dir / "local_evidence_inventory.json"
        if inventory_path.exists():
            input_paths.append(inventory_path)
        context = load_running_case_context(
            args.client_engagement,
            input_paths=input_paths,
            output_dir=args.output_dir,
        )
        for path in input_paths:
            require_case_artifact_run(path, run_id=context["run_id"])
        result = package_practice(args.output_dir)
    except (AssuranceContractError, OSError, ValueError, json.JSONDecodeError) as exc:
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
