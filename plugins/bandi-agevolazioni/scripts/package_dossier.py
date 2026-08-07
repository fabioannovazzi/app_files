"""Render a validated private dossier for professional review."""

from __future__ import annotations

import argparse
import logging
from pathlib import Path
from typing import Any, Iterable

from case_core import (
    PLUGIN_NAME,
    canonical_json_sha256,
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
) -> dict[str, str]:
    return {
        "case_intake": canonical_json_sha256(intake),
        "source_register": canonical_json_sha256(sources),
        "application_workbench": canonical_json_sha256(workbench),
        "review_log": canonical_json_sha256(reviews),
    }


def _render_markdown(
    *,
    intake: dict[str, Any],
    sources: dict[str, Any],
    workbench: dict[str, Any],
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
                [
                    "Cliente",
                    applicant.get("legal_name"),
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
                    "Importo richiesto",
                    f"{project.get('requested_amount') or '—'} {project.get('currency') or ''}".strip(),
                    project.get("confirmation_status"),
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
            ["ID", "Tipo", "Titolo", "Ente", "Ruolo", "Stato", "SHA-256"],
            (
                [
                    source.get("source_id"),
                    source.get("source_type"),
                    source.get("title"),
                    source.get("issuer"),
                    source.get("authority_role"),
                    source.get("review_status"),
                    source.get("sha256"),
                ]
                for source in sources.get("sources", [])
            ),
        ),
        "",
        "## Requisiti e valutazioni",
        "",
    ]
    assessment_by_requirement = {
        item.get("requirement_id"): item for item in workbench.get("assessments", [])
    }
    lines.extend(
        _table(
            ["Requisito", "Categoria", "Testo", "Completezza", "Esito", "Revisione"],
            (
                [
                    requirement.get("requirement_id"),
                    requirement.get("category"),
                    requirement.get("statement"),
                    assessment_by_requirement.get(
                        requirement.get("requirement_id"), {}
                    ).get("readiness", "missing"),
                    assessment_by_requirement.get(
                        requirement.get("requirement_id"), {}
                    ).get("outcome", "not_assessed"),
                    requirement.get("review_status"),
                ]
                for requirement in workbench.get("requirements", [])
            ),
        )
    )
    sections = (
        ("Documenti", "document_checklist", "document_id", "title"),
        ("Spese", "expenses", "expense_id", "description"),
        ("Campi modulo e portale", "form_fields", "field_id", "label"),
        ("Campi narrativi", "narratives", "narrative_id", "prompt"),
    )
    for heading, key, id_field, title_field in sections:
        lines.extend(
            [
                "",
                f"## {heading}",
                "",
                *_table(
                    ["ID", "Voce", "Completezza", "Esito", "Revisione"],
                    (
                        [
                            item.get(id_field),
                            item.get(title_field),
                            item.get("readiness"),
                            item.get("outcome", "—"),
                            item.get("review_status"),
                        ]
                        for item in workbench.get(key, [])
                    ),
                ),
            ]
        )
    lines.extend(
        [
            "",
            "## Controlli di coerenza tra documenti",
            "",
            *_table(
                ["ID", "Controllo", "Esito", "Razionale", "Revisione"],
                (
                    [
                        item.get("check_id"),
                        item.get("question"),
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
                ["ID", "Controllo", "Esito", "Razionale", "Revisione"],
                (
                    [
                        item.get("check_id"),
                        item.get("question"),
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
                ["ID", "Categoria", "Gravità", "Dettaglio", "Stato"],
                (
                    [
                        item.get("issue_id"),
                        item.get("category"),
                        item.get("severity"),
                        item.get("detail"),
                        item.get("status"),
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
            "## Limiti",
            "",
            *(
                f"- {item}"
                for item in [
                    *workbench["dossier"].get("limitations", []),
                    *audit.get("limitations", []),
                    "La persona autorizzata conserva autenticazione, dichiarazioni, firma, salvataggio sul portale e trasmissione.",
                ]
            ),
            "",
        ]
    )
    return "\n".join(lines)


def package_dossier(*, output_dir: Path, client_engagement: Path) -> dict[str, Path]:
    """Render a review package only from an exact passing validation audit."""

    context = load_running_context(client_engagement, output_dir=output_dir)
    run_id = safe_identifier(context["run_id"], field="run_id")
    output_dir = output_dir.resolve()
    intake = require_run_artifact(output_dir / "case_intake.json", run_id=run_id)
    sources = require_run_artifact(output_dir / "source_register.json", run_id=run_id)
    workbench = require_run_artifact(
        output_dir / "application_workbench.json", run_id=run_id
    )
    reviews = require_run_artifact(output_dir / "review_log.json", run_id=run_id)
    audit = require_run_artifact(output_dir / "validation_audit.json", run_id=run_id)
    if audit.get("status") != "passed":
        raise ValueError("validation_audit.json must pass before packaging")
    current_hashes = _current_hashes(intake, sources, workbench, reviews)
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
            audit=audit,
        ),
    )
    dossier_sha256 = sha256_file(markdown_path)
    audit_path = output_dir / "validation_audit.json"
    audit_sha256 = sha256_file(audit_path)
    manifest = {
        "schema_version": "1.0",
        "plugin": PLUGIN_NAME,
        "run_id": run_id,
        "generated_at": iso_now(),
        "disposition": workbench["dossier"]["disposition"],
        "ready_to_file": False,
        "portal_actions_performed": False,
        "signature_actions_performed": False,
        "submission_actions_performed": False,
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
