"""Render a validated private dossier for professional review."""

from __future__ import annotations

import argparse
import json
import logging
from pathlib import Path
from typing import Any, Iterable

from case_core import (
    PLUGIN_NAME,
    canonical_json_sha256,
    case_lock,
    iso_now,
    load_running_context,
    require_run_artifact,
    safe_identifier,
    sha256_file,
    write_private_json,
    write_private_text,
)

__all__ = ["package_dossier", "main"]

LOGGER = logging.getLogger(__name__)
DISCLAIMER = "BOZZA PER REVISIONE PROFESSIONALE — NON FIRMATA E NON INVIATA"


def _cell(value: object) -> str:
    return (
        str(value if value not in (None, "") else "—")
        .replace("|", "\\|")
        .replace("\n", " ")
    )


def _table(headers: list[str], rows: Iterable[Iterable[object]]) -> list[str]:
    return [
        "| " + " | ".join(headers) + " |",
        "| " + " | ".join("---" for _ in headers) + " |",
        *("| " + " | ".join(_cell(value) for value in row) + " |" for row in rows),
    ]


def _current_hashes(
    intake: dict[str, Any],
    sources: dict[str, Any],
    workbench: dict[str, Any],
    reviews: dict[str, Any],
    run_state: dict[str, Any],
) -> dict[str, str]:
    return {
        "case_intake": canonical_json_sha256(intake),
        "source_register": canonical_json_sha256(sources),
        "application_workbench": canonical_json_sha256(workbench),
        "review_log": canonical_json_sha256(reviews),
        "run_state": canonical_json_sha256(run_state),
    }


def _render_markdown(
    *,
    intake: dict[str, Any],
    sources: dict[str, Any],
    workbench: dict[str, Any],
    reviews: dict[str, Any],
    audit: dict[str, Any],
) -> str:
    application = intake["application"]
    applicant = intake["applicant"]
    project = intake["project"]
    lines = [
        f"# {DISCLAIMER}",
        "",
        "## Perimetro",
        "",
        *_table(
            ["Voce", "Valore", "Stato"],
            [
                ["Run ID", intake.get("run_id"), "bound"],
                ["Riferimento cliente", intake.get("client_reference"), "bound"],
                ["Data di riferimento", intake.get("reference_date"), "bound"],
                [
                    "Cliente",
                    applicant.get("legal_name"),
                    applicant.get("confirmation_status"),
                ],
                [
                    "Codice fiscale",
                    applicant.get("tax_code"),
                    applicant.get("confirmation_status"),
                ],
                [
                    "Partita IVA",
                    applicant.get("vat_number"),
                    applicant.get("confirmation_status"),
                ],
                ["Bando", application.get("title"), application.get("status")],
                [
                    "Ente",
                    application.get("issuing_authority"),
                    application.get("status"),
                ],
                [
                    "Procedura",
                    application.get("procedure_id"),
                    application.get("status"),
                ],
                [
                    "Scadenza",
                    application.get("submission_deadline"),
                    application.get("status"),
                ],
                ["Progetto", project.get("title"), project.get("confirmation_status")],
                [
                    "Sintesi progetto",
                    project.get("summary"),
                    project.get("confirmation_status"),
                ],
                [
                    "Importo richiesto",
                    f"{project.get('requested_amount') or '—'} {project.get('currency') or ''}".strip(),
                    project.get("confirmation_status"),
                ],
                [
                    "Domanda professionale",
                    intake.get("professional_question"),
                    "recorded",
                ],
                [
                    "Revisione fonti",
                    sources.get("source_set_revision"),
                    "bound",
                ],
            ],
        ),
        "",
        "## Disposizione del dossier",
        "",
        f"**{workbench['dossier']['disposition']}**",
        "",
        "`ready_to_file` è sempre `false`. La disposizione non autorizza firma o invio.",
        "",
        "## Fonti registrate",
        "",
        *_table(
            [
                "ID",
                "Tipo",
                "Titolo",
                "Ente",
                "Ruolo",
                "Pubblicazione",
                "Efficacia",
                "Percorso",
                "Relazioni",
                "Stato",
                "SHA-256",
            ],
            (
                [
                    source.get("source_id"),
                    source.get("source_type"),
                    source.get("title"),
                    source.get("issuer"),
                    source.get("authority_role"),
                    source.get("publication_date"),
                    f"{source.get('effective_from') or '—'} → {source.get('effective_to') or '—'}",
                    source.get("path"),
                    "; ".join(
                        f"{item.get('kind')}:{item.get('target_source_id')}"
                        for item in source.get("relationships", [])
                    ),
                    source.get("review_status"),
                    source.get("sha256"),
                ]
                for source in sources.get("sources", [])
            ),
        ),
        "",
        "## Sintesi del caso",
        "",
        workbench.get("case_summary") or "—",
        "",
        "## Requisiti, fonti e valutazioni",
        "",
    ]
    assessment_by_requirement = {
        item.get("requirement_id"): item for item in workbench.get("assessments", [])
    }
    lines.extend(
        _table(
            [
                "Valutazione",
                "Requisito",
                "Categoria",
                "Testo",
                "Applicabilità",
                "Evidenza attesa",
                "Fonti/locator",
                "Completezza",
                "Esito",
                "Razionale",
                "Fatti",
                "Metodo",
                "Regola deterministica",
                "Revisione requisito",
                "Revisione valutazione",
            ],
            (
                [
                    assessment_by_requirement.get(
                        requirement.get("requirement_id"), {}
                    ).get("assessment_id", "—"),
                    requirement.get("requirement_id"),
                    requirement.get("category"),
                    requirement.get("statement"),
                    requirement.get("applicability"),
                    "; ".join(requirement.get("expected_evidence", [])),
                    "; ".join(
                        f"{ref.get('source_id')} @ {ref.get('locator')} | excerpt={ref.get('excerpt')} | sha256={ref.get('excerpt_sha256')}"
                        for ref in requirement.get("source_refs", [])
                    ),
                    assessment_by_requirement.get(
                        requirement.get("requirement_id"), {}
                    ).get("readiness", "missing"),
                    assessment_by_requirement.get(
                        requirement.get("requirement_id"), {}
                    ).get("outcome", "not_assessed"),
                    assessment_by_requirement.get(
                        requirement.get("requirement_id"), {}
                    ).get("rationale", "—"),
                    ", ".join(
                        assessment_by_requirement.get(
                            requirement.get("requirement_id"), {}
                        ).get("fact_ids", [])
                    ),
                    assessment_by_requirement.get(
                        requirement.get("requirement_id"), {}
                    ).get("evaluation_method", "—"),
                    json.dumps(
                        assessment_by_requirement.get(
                            requirement.get("requirement_id"), {}
                        ).get("deterministic_rule"),
                        ensure_ascii=False,
                        sort_keys=True,
                    ),
                    requirement.get("review_status"),
                    assessment_by_requirement.get(
                        requirement.get("requirement_id"), {}
                    ).get("review_status", "—"),
                ]
                for requirement in workbench.get("requirements", [])
            ),
        )
    )
    lines.extend(
        [
            "",
            "## Fatti",
            "",
            *_table(
                ["ID", "Campo", "Valore", "Data", "Tipo", "Fonti", "Revisione"],
                (
                    [
                        item.get("fact_id"),
                        item.get("field_code"),
                        json.dumps(item.get("value"), ensure_ascii=False),
                        item.get("as_of"),
                        item.get("kind"),
                        ", ".join(item.get("source_ids", [])),
                        item.get("review_status"),
                    ]
                    for item in workbench.get("facts", [])
                ),
            ),
            "",
            "## Checklist documentale",
            "",
            *_table(
                [
                    "ID",
                    "Documento",
                    "Requisiti",
                    "Fonti materiali",
                    "Stato",
                    "Razionale",
                    "Revisione",
                ],
                (
                    [
                        item.get("document_id"),
                        item.get("title"),
                        ", ".join(item.get("requirement_ids", [])),
                        ", ".join(item.get("material_source_ids", [])),
                        item.get("readiness"),
                        item.get("rationale"),
                        item.get("review_status"),
                    ]
                    for item in workbench.get("document_checklist", [])
                ),
            ),
            "",
            "## Spese",
            "",
            *_table(
                [
                    "ID",
                    "Descrizione",
                    "Importo",
                    "Valuta",
                    "Requisiti",
                    "Fonti",
                    "Stato",
                    "Esito",
                    "Razionale",
                    "Revisione",
                ],
                (
                    [
                        item.get("expense_id"),
                        item.get("description"),
                        item.get("amount"),
                        item.get("currency"),
                        ", ".join(item.get("requirement_ids", [])),
                        ", ".join(item.get("source_ids", [])),
                        item.get("readiness"),
                        item.get("outcome"),
                        item.get("rationale"),
                        item.get("review_status"),
                    ]
                    for item in workbench.get("expenses", [])
                ),
            ),
            "",
            "## Campi modulo e assistenza portale",
            "",
            *_table(
                [
                    "ID",
                    "Campo",
                    "Valore proposto",
                    "Requisiti",
                    "Fatti",
                    "Stato",
                    "Manuale",
                    "Controlli protetti",
                    "Razionale",
                    "Revisione",
                ],
                (
                    [
                        item.get("field_id"),
                        item.get("label"),
                        json.dumps(item.get("proposed_value"), ensure_ascii=False),
                        ", ".join(item.get("requirement_ids", [])),
                        ", ".join(item.get("fact_ids", [])),
                        item.get("readiness"),
                        item.get("manual_only"),
                        ", ".join(
                            name
                            for name in (
                                "declaration_control",
                                "signature_control",
                                "submission_control",
                            )
                            if item.get(name)
                        ),
                        item.get("rationale"),
                        item.get("review_status"),
                    ]
                    for item in workbench.get("form_fields", [])
                ),
            ),
            "",
            "## Campi narrativi",
            "",
        ]
    )
    for narrative in workbench.get("narratives", []):
        lines.extend(
            [
                f"### {narrative.get('narrative_id')} — {narrative.get('prompt')}",
                "",
                narrative.get("draft") or "—",
                "",
                f"Requisiti: {_cell(', '.join(narrative.get('requirement_ids', [])))}  ",
                f"Fatti: {_cell(', '.join(narrative.get('fact_ids', [])))}  ",
                f"Stato: {_cell(narrative.get('readiness'))}; revisione: {_cell(narrative.get('review_status'))}  ",
                f"Razionale: {_cell(narrative.get('rationale'))}",
                "",
            ]
        )
    lines.extend(
        [
            "",
            "## Controlli di coerenza tra documenti",
            "",
            *_table(
                [
                    "ID",
                    "Controllo",
                    "Fatti",
                    "Fonti",
                    "Esito",
                    "Razionale",
                    "Revisione",
                ],
                (
                    [
                        item.get("check_id"),
                        item.get("question"),
                        ", ".join(item.get("fact_ids", [])),
                        ", ".join(item.get("source_ids", [])),
                        item.get("outcome"),
                        item.get("rationale"),
                        item.get("review_status"),
                    ]
                    for item in workbench.get("consistency_checks", [])
                ),
            ),
            "",
            "## Simulazione del controllo dell'ente",
            "",
            f"**{workbench['authority_simulation']['overall_outcome']}** — "
            f"{workbench['authority_simulation']['reviewer_perspective']}",
            "",
            *_table(
                [
                    "ID",
                    "Controllo",
                    "Elementi coperti",
                    "Esito",
                    "Razionale",
                    "Revisione",
                ],
                (
                    [
                        item.get("check_id"),
                        item.get("question"),
                        ", ".join(item.get("related_ids", [])),
                        item.get("outcome"),
                        item.get("rationale"),
                        item.get("review_status"),
                    ]
                    for item in workbench["authority_simulation"].get("checks", [])
                ),
            ),
            "",
            "## Informazioni mancanti e red flag",
            "",
            *_table(
                [
                    "ID",
                    "Categoria",
                    "Gravità",
                    "Dettaglio",
                    "Elementi",
                    "Stato",
                    "Revisione",
                ],
                (
                    [
                        item.get("issue_id"),
                        item.get("category"),
                        item.get("severity"),
                        item.get("detail"),
                        ", ".join(item.get("related_ids", [])),
                        item.get("status"),
                        item.get("review_status"),
                    ]
                    for item in workbench.get("issues", [])
                ),
            ),
            "",
            "## Stato delle revisioni",
            "",
            *_table(
                ["Ambito", "Decisione corrente"],
                sorted(audit.get("review_states", {}).items()),
            ),
            "",
            "## Registro delle revisioni professionali",
            "",
            *_table(
                [
                    "Evento",
                    "Ambito",
                    "Decisione",
                    "Revisore",
                    "Ruolo",
                    "Base conferma",
                    "Garanzia identità",
                    "Data",
                    "Hash ambito",
                    "Note",
                ],
                (
                    [
                        item.get("event_id"),
                        item.get("scope"),
                        item.get("decision"),
                        item.get("reviewer_id"),
                        item.get("reviewer_role"),
                        item.get("confirmation_basis"),
                        item.get("identity_assurance"),
                        item.get("reviewed_at"),
                        item.get("scope_sha256"),
                        item.get("notes"),
                    ]
                    for item in reviews.get("events", [])
                ),
            ),
            "",
            "## Limiti",
            "",
            *(
                f"- {item}"
                for item in [
                    *workbench["dossier"].get("limitations", []),
                    *audit.get("limitations", []),
                    "La persona autorizzata conserva autenticazione, dichiarazioni, firma, salvataggio sul portale e trasmissione.",
                    "Gli identificativi dei revisori sono dichiarati localmente e non autenticati da questo workflow.",
                ]
            ),
            "",
        ]
    )
    return "\n".join(lines)


def package_dossier(*, output_dir: Path, client_engagement: Path) -> dict[str, Path]:
    """Render a review package only from an exact passing validation audit."""

    context = load_running_context(client_engagement, output_dir=output_dir)
    output_dir = output_dir.resolve()
    with case_lock(output_dir):
        return _package_dossier_locked(output_dir=output_dir, context=context)


def _package_dossier_locked(
    *, output_dir: Path, context: dict[str, Any]
) -> dict[str, Path]:
    """Package one immutable snapshot while cooperative writers are locked."""

    run_id = safe_identifier(context["run_id"], field="run_id")
    intake = require_run_artifact(output_dir / "case_intake.json", run_id=run_id)
    sources = require_run_artifact(output_dir / "source_register.json", run_id=run_id)
    workbench = require_run_artifact(
        output_dir / "application_workbench.json", run_id=run_id
    )
    reviews = require_run_artifact(output_dir / "review_log.json", run_id=run_id)
    run_state = require_run_artifact(output_dir / "run_state.json", run_id=run_id)
    audit = require_run_artifact(output_dir / "validation_audit.json", run_id=run_id)
    if audit.get("status") != "passed":
        raise ValueError("validation_audit.json must pass before packaging")
    current_hashes = _current_hashes(intake, sources, workbench, reviews, run_state)
    if audit.get("artifact_hashes") != current_hashes:
        raise ValueError("validated artifacts changed; rerun validation")
    if workbench.get("dossier", {}).get("ready_to_file") is not False:
        raise ValueError("ready_to_file must remain false")
    markdown_path = output_dir / "review_dossier.md"
    manifest_path = output_dir / "dossier_manifest.json"
    write_private_text(
        markdown_path,
        _render_markdown(
            intake=intake,
            sources=sources,
            workbench=workbench,
            reviews=reviews,
            audit=audit,
        ),
    )
    dossier_sha256 = sha256_file(markdown_path)
    audit_path = output_dir / "validation_audit.json"
    audit_sha256 = sha256_file(audit_path)
    final_hashes = _current_hashes(
        require_run_artifact(output_dir / "case_intake.json", run_id=run_id),
        require_run_artifact(output_dir / "source_register.json", run_id=run_id),
        require_run_artifact(output_dir / "application_workbench.json", run_id=run_id),
        require_run_artifact(output_dir / "review_log.json", run_id=run_id),
        require_run_artifact(output_dir / "run_state.json", run_id=run_id),
    )
    if final_hashes != current_hashes:
        raise ValueError("validated artifacts changed during packaging")
    manifest = {
        "schema_version": "1.2",
        "plugin": PLUGIN_NAME,
        "run_id": run_id,
        "generated_at": iso_now(),
        "disposition": workbench["dossier"]["disposition"],
        "ready_to_file": False,
        "portal_actions_performed": run_state["portal_actions_performed"],
        "signature_actions_performed": run_state["signature_actions_performed"],
        "submission_actions_performed": run_state["submission_actions_performed"],
        "source_set_revision": sources["source_set_revision"],
        "artifact_hashes": current_hashes,
        "validation_audit_sha256": canonical_json_sha256(audit),
        "artifacts": [
            {
                "artifact_id": "deliverable.review_dossier",
                "path": markdown_path.name,
                "purpose": "Private source-backed dossier for professional review",
                "audience": "professional_review",
                "media_type": "text/markdown",
                "byte_count": markdown_path.stat().st_size,
                "sha256": dossier_sha256,
            },
            {
                "artifact_id": "control.validation_audit",
                "path": "validation_audit.json",
                "purpose": "Mechanical traceability and safety validation",
                "audience": "control",
                "media_type": "application/json",
                "byte_count": audit_path.stat().st_size,
                "sha256": audit_sha256,
            },
            *(
                {
                    "artifact_id": f"evidence.{artifact_id}",
                    "path": filename,
                    "purpose": purpose,
                    "audience": "professional_review_and_audit",
                    "media_type": "application/json",
                    "byte_count": (output_dir / filename).stat().st_size,
                    "sha256": sha256_file(output_dir / filename),
                }
                for artifact_id, filename, purpose in (
                    (
                        "case_intake",
                        "case_intake.json",
                        "Bound case and applicant intake",
                    ),
                    (
                        "source_register",
                        "source_register.json",
                        "Selected source inventory and relationships",
                    ),
                    (
                        "application_workbench",
                        "application_workbench.json",
                        "Requirement-level application workbench",
                    ),
                    (
                        "review_log",
                        "review_log.json",
                        "Professional review decisions and bound hashes",
                    ),
                    (
                        "run_state",
                        "run_state.json",
                        "Workflow state and prohibited-action flags",
                    ),
                )
            ),
        ],
        "limitations": [
            "This package is not signed, filed, submitted, or guaranteed eligible."
        ],
    }
    write_private_json(manifest_path, manifest)
    return {"dossier": markdown_path, "manifest": manifest_path}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", required=True, type=Path)
    parser.add_argument("--client-engagement", required=True, type=Path)
    args = parser.parse_args(argv)
    paths = package_dossier(
        output_dir=args.output_dir,
        client_engagement=args.client_engagement,
    )
    for label, path in paths.items():
        LOGGER.info("%s: %s", label, path)
    return 0


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    raise SystemExit(main())
