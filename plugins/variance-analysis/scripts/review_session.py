from __future__ import annotations

import json
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Sequence

from accounting_controls import accounting_intake_questions

__all__ = [
    "ReviewSessionResult",
    "RunIntakeResult",
    "write_review_session_artifacts",
    "write_run_intake",
]

SCHEMA_VERSION = "1.0"
PLUGIN_NAME = "variance-analysis"
WORKFLOW_NAME = "variance-analysis"
MAX_DRIVER_ROWS = 50
MAX_ARTIFACT_ITEMS = 200
MAX_FOLLOWUP_ITEMS = 50

_REVIEW_COPY: dict[str, dict[str, Any]] = {
    "en": {
        "product_title": "Variance Analysis",
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
        "columns": (
            "Type",
            "Element",
            "Suggested action",
            "Source",
            "Output",
            "Status",
        ),
        "driver_row": "Driver row {index}",
        "driver_rows_truncated": "Variance driver rows truncated in widget",
        "artifact": "Artifact",
        "followup": "Follow-up {index}",
        "context_title": "Standard variance context",
        "accounting_title": "Accounting controls and review status",
        "dependency_note": (
            "Codex should run scripts/check_dependencies.py before helper scripts."
        ),
        "data_posture_notes": [
            "Variance scripts read the source table and optional recipe locally and write bounded review artifacts.",
            "No external connector, upload path, remote SQL, or hosted notebook execution is used by default.",
        ],
        "caveats": [
            "Chart payloads are bounded for review; use variance_results.csv and context files as the full source set.",
            "ui_decisions.json is pending until Codex, MCP UI, or fallback review records decisions.",
        ],
        "next_actions": [
            "Render review_payload.json with the MCP widget when available.",
            "Use the standard variance context before interpreting chart pixels.",
            "Write codex_business_analysis.md from reviewed source artifacts and caveats.",
        ],
    },
    "es": {
        "product_title": "Análisis de variaciones",
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
        "columns": (
            "Tipo",
            "Elemento",
            "Acción sugerida",
            "Fuente",
            "Salida",
            "Estado",
        ),
        "driver_row": "Fila de factor {index}",
        "driver_rows_truncated": (
            "Filas de factores de variación acotadas en el widget"
        ),
        "artifact": "Artefacto",
        "followup": "Seguimiento {index}",
        "context_title": "Contexto estándar de variaciones",
        "accounting_title": "Controles contables y estado de revisión",
        "dependency_note": (
            "Codex debe ejecutar scripts/check_dependencies.py antes de los scripts auxiliares."
        ),
        "data_posture_notes": [
            "Los scripts de variaciones leen localmente la tabla fuente y la receta opcional y generan artefactos acotados para la revisión.",
            "De forma predeterminada no se utilizan conectores externos, rutas de carga, SQL remoto ni cuadernos alojados.",
        ],
        "caveats": [
            "Los datos de los gráficos están acotados para la revisión; utilice variance_results.csv y los archivos de contexto como conjunto completo de fuentes.",
            "ui_decisions.json permanece pendiente hasta que Codex, la interfaz MCP o la revisión alternativa registren las decisiones.",
        ],
        "next_actions": [
            "Cuando esté disponible, abra review_payload.json con el widget MCP.",
            "Utilice el contexto estándar de variaciones antes de interpretar los píxeles de los gráficos.",
            "Redacte codex_business_analysis.md a partir de los artefactos fuente revisados y las salvedades.",
        ],
    },
    "it": {
        "product_title": "Analisi delle varianze",
        "handoff_title": "Consegna per la revisione",
        "run_id": "ID esecuzione",
        "review_payload": "Pacchetto di revisione",
        "run_intake": "Dati iniziali dell’esecuzione",
        "pending_decisions": "Decisioni in sospeso",
        "applied_decisions": "Decisioni applicate",
        "final_artifacts": "Artefatti finali",
        "review_in_codex": "Revisione in Codex",
        "validate_step": "Convalida il pacchetto con `{tool}`.",
        "render_step": "Apri l’area di revisione con `{tool}`.",
        "save_step": "Salva le decisioni del revisore con `{tool}`.",
        "apply_step": "Applica le decisioni del revisore con `{tool}`.",
        "columns": (
            "Tipo",
            "Elemento",
            "Azione suggerita",
            "Fonte",
            "Output",
            "Stato",
        ),
        "driver_row": "Riga driver {index}",
        "driver_rows_truncated": "Righe driver limitate nel widget",
        "artifact": "Artefatto",
        "followup": "Approfondimento {index}",
        "context_title": "Contesto standard delle varianze",
        "accounting_title": "Controlli contabili e stato della revisione",
        "dependency_note": (
            "Codex deve eseguire scripts/check_dependencies.py prima degli script ausiliari."
        ),
        "data_posture_notes": [
            "Gli script leggono localmente la tabella sorgente e la ricetta opzionale e producono artefatti limitati per la revisione.",
            "Per impostazione predefinita non vengono usati connettori esterni, percorsi di caricamento, SQL remoto o notebook ospitati.",
        ],
        "caveats": [
            "I dati dei grafici sono limitati per la revisione; usare variance_results.csv e i file di contesto come fonti complete.",
            "ui_decisions.json resta in sospeso finché Codex, l’interfaccia MCP o la revisione alternativa non registrano le decisioni.",
        ],
        "next_actions": [
            "Aprire review_payload.json con il widget MCP quando disponibile.",
            "Usare il contesto standard prima di interpretare i grafici.",
            "Redigere codex_business_analysis.md dagli artefatti sorgente e dalle riserve esaminate.",
        ],
    },
    "fr": {
        "product_title": "Analyse des écarts",
        "handoff_title": "Dossier de revue",
        "run_id": "ID d’exécution",
        "review_payload": "Données de revue",
        "run_intake": "Données initiales",
        "pending_decisions": "Décisions en attente",
        "applied_decisions": "Décisions appliquées",
        "final_artifacts": "Livrables finaux",
        "review_in_codex": "Revue dans Codex",
        "validate_step": "Validez les données avec `{tool}`.",
        "render_step": "Ouvrez l’espace de revue avec `{tool}`.",
        "save_step": "Enregistrez les décisions avec `{tool}`.",
        "apply_step": "Appliquez les décisions avec `{tool}`.",
        "columns": ("Type", "Élément", "Action proposée", "Source", "Sortie", "Statut"),
        "driver_row": "Ligne de facteur {index}",
        "driver_rows_truncated": "Lignes de facteurs limitées dans le widget",
        "artifact": "Livrable",
        "followup": "Suivi {index}",
        "context_title": "Contexte standard des écarts",
        "accounting_title": "Contrôles comptables et état de la revue",
        "dependency_note": "Codex doit exécuter scripts/check_dependencies.py avant les scripts auxiliaires.",
        "data_posture_notes": [
            "Les scripts lisent localement la table source et la recette facultative et produisent des éléments bornés pour la revue.",
            "Aucun connecteur externe, chargement, SQL distant ou notebook hébergé n’est utilisé par défaut.",
        ],
        "caveats": [
            "Les données de graphiques sont bornées pour la revue; utilisez variance_results.csv et les fichiers de contexte comme sources complètes.",
            "ui_decisions.json reste en attente jusqu’à l’enregistrement des décisions de revue.",
        ],
        "next_actions": [
            "Ouvrir review_payload.json avec le widget MCP lorsqu’il est disponible.",
            "Utiliser le contexte standard avant d’interpréter les graphiques.",
            "Rédiger codex_business_analysis.md à partir des sources revues et des réserves.",
        ],
    },
    "de": {
        "product_title": "Abweichungsanalyse",
        "handoff_title": "Prüfungsübergabe",
        "run_id": "Ausführungs-ID",
        "review_payload": "Prüfdaten",
        "run_intake": "Ausgangsdaten",
        "pending_decisions": "Offene Entscheidungen",
        "applied_decisions": "Angewandte Entscheidungen",
        "final_artifacts": "Endgültige Artefakte",
        "review_in_codex": "Prüfung in Codex",
        "validate_step": "Validieren Sie die Daten mit `{tool}`.",
        "render_step": "Öffnen Sie den Prüfbereich mit `{tool}`.",
        "save_step": "Speichern Sie die Prüferentscheidungen mit `{tool}`.",
        "apply_step": "Wenden Sie die Prüferentscheidungen mit `{tool}` an.",
        "columns": (
            "Typ",
            "Element",
            "Vorgeschlagene Aktion",
            "Quelle",
            "Ausgabe",
            "Status",
        ),
        "driver_row": "Treiberzeile {index}",
        "driver_rows_truncated": "Treiberzeilen im Widget begrenzt",
        "artifact": "Artefakt",
        "followup": "Nachverfolgung {index}",
        "context_title": "Standardkontext der Abweichung",
        "accounting_title": "Buchhalterische Kontrollen und Prüfstatus",
        "dependency_note": "Codex muss scripts/check_dependencies.py vor den Hilfsskripten ausführen.",
        "data_posture_notes": [
            "Die Skripte lesen Quelltabelle und optionale Rezeptur lokal und schreiben begrenzte Prüfartefakte.",
            "Standardmäßig werden keine externen Konnektoren, Uploadpfade, Remote-SQL- oder gehosteten Notebooks verwendet.",
        ],
        "caveats": [
            "Diagrammdaten sind für die Prüfung begrenzt; variance_results.csv und Kontextdateien bilden die vollständige Quellenbasis.",
            "ui_decisions.json bleibt offen, bis Prüfentscheidungen gespeichert wurden.",
        ],
        "next_actions": [
            "review_payload.json nach Verfügbarkeit im MCP-Widget öffnen.",
            "Vor der Diagramminterpretation den Standardkontext verwenden.",
            "codex_business_analysis.md aus geprüften Quellen und Vorbehalten erstellen.",
        ],
    },
}


def _normalize_language(language: object | None) -> str:
    text = str(language or "en").strip().lower().replace("_", "-")
    code = text.split("-", 1)[0]
    return code if code in _REVIEW_COPY else "en"


def _review_copy(language: object | None) -> dict[str, Any]:
    return _REVIEW_COPY[_normalize_language(language)]


_ACCOUNTING_QUESTION_TRANSLATIONS = {
    "it": {
        "Confirm the entity and consolidation perimeter.": "Confermare il perimetro societario e di consolidamento.",
        "Provide approved baseline and comparison source totals for tie-out.": "Fornire i totali approvati della fonte per base e confronto.",
        "Confirm the favorable/adverse sign convention.": "Confermare la convenzione favorevole/sfavorevole.",
        "Confirm materiality or explicitly record that it is not applied.": "Confermare la materialità o registrare esplicitamente che non è applicata.",
        "Complete the applied materiality threshold and basis.": "Completare la soglia di materialità applicata e il relativo criterio.",
        "Resolve the failed source-total tie-out.": "Risolvere la quadratura non riuscita con i totali della fonte.",
        "Resolve the component-bridge reconciliation control.": "Risolvere il controllo di chiusura del bridge dei componenti.",
    },
    "es": {
        "Confirm the entity and consolidation perimeter.": "Confirme el perímetro de entidad y consolidación.",
        "Provide approved baseline and comparison source totals for tie-out.": "Proporcione los totales fuente aprobados de base y comparación.",
        "Confirm the favorable/adverse sign convention.": "Confirme la convención favorable/desfavorable.",
        "Confirm materiality or explicitly record that it is not applied.": "Confirme la materialidad o registre expresamente que no se aplica.",
        "Complete the applied materiality threshold and basis.": "Complete el umbral de materialidad aplicado y su base.",
        "Resolve the failed source-total tie-out.": "Resuelva la conciliación fallida con los totales fuente.",
        "Resolve the component-bridge reconciliation control.": "Resuelva el control de cierre del puente de componentes.",
    },
    "fr": {
        "Confirm the entity and consolidation perimeter.": "Confirmer le périmètre d’entité et de consolidation.",
        "Provide approved baseline and comparison source totals for tie-out.": "Fournir les totaux source approuvés de référence et de comparaison.",
        "Confirm the favorable/adverse sign convention.": "Confirmer la convention favorable/défavorable.",
        "Confirm materiality or explicitly record that it is not applied.": "Confirmer le seuil de signification ou indiquer qu’il ne s’applique pas.",
        "Complete the applied materiality threshold and basis.": "Compléter le seuil de signification appliqué et sa base.",
        "Resolve the failed source-total tie-out.": "Résoudre l’échec du rapprochement avec les totaux source.",
        "Resolve the component-bridge reconciliation control.": "Résoudre le contrôle de bouclage du pont des composantes.",
    },
    "de": {
        "Confirm the entity and consolidation perimeter.": "Unternehmens- und Konsolidierungskreis bestätigen.",
        "Provide approved baseline and comparison source totals for tie-out.": "Freigegebene Quellsummen für Basis und Vergleich angeben.",
        "Confirm the favorable/adverse sign convention.": "Konvention für günstige/ungünstige Abweichungen bestätigen.",
        "Confirm materiality or explicitly record that it is not applied.": "Wesentlichkeit bestätigen oder ausdrücklich als nicht angewendet kennzeichnen.",
        "Complete the applied materiality threshold and basis.": "Angewendete Wesentlichkeitsschwelle und Grundlage vervollständigen.",
        "Resolve the failed source-total tie-out.": "Fehlgeschlagenen Abgleich mit Quellsummen klären.",
        "Resolve the component-bridge reconciliation control.": "Abstimmungskontrolle der Komponentenbrücke klären.",
    },
}


def _localize_accounting_questions(
    questions: Sequence[str], language: str
) -> list[str]:
    translations = _ACCOUNTING_QUESTION_TRANSLATIONS.get(language, {})
    return [translations.get(question, question) for question in questions]


@dataclass(frozen=True)
class RunIntakeResult:
    """Run intake artifact written before the heavy variance run."""

    run_id: str
    path: Path


@dataclass(frozen=True)
class ReviewSessionResult:
    """Review-session artifacts for one variance-analysis run."""

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
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return path


def _write_review_handoff_card(
    output_dir: Path,
    *,
    run_id: str,
    language: str,
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
        f"1. {copy['validate_step'].format(tool='validate_variance_analysis_review')}",
        f"2. {copy['render_step'].format(tool='render_variance_analysis_review')}",
        f"3. {copy['save_step'].format(tool='save_variance_analysis_decisions')}",
        f"4. {copy['apply_step'].format(tool='apply_variance_analysis_decisions')}",
    ]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


def _review_handoff_output_record(path: Path, language: str) -> dict[str, Any]:
    copy = _review_copy(language)
    localized_required_text = (
        [copy["handoff_title"], copy["review_in_codex"]]
        if _normalize_language(language) != "en"
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


def _load_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return payload if isinstance(payload, dict) else {}


def _as_output_ref(path: Path | None, output_dir: Path) -> str | None:
    if path is None:
        return None
    try:
        return path.relative_to(output_dir).as_posix()
    except ValueError:
        return path.as_posix()


def _portable_client_engagement(
    client_engagement: dict[str, Any] | None,
) -> dict[str, Any] | None:
    """Remove runtime-only absolute paths from a persisted managed context."""

    if (
        not isinstance(client_engagement, dict)
        or client_engagement.get("schema_version") != "vera.client_workflow_context.v2"
    ):
        return client_engagement
    portable_fields = (
        "schema_version",
        "client_id",
        "engagement_id",
        "workflow_id",
        "workflow_version",
        "run_id",
        "label",
        "purpose",
        "created_at",
        "input_manifest",
        "input_manifest_sha256",
        "run_relative_path",
        "output_relative_path",
        "content_sha256",
    )
    return {field: client_engagement[field] for field in portable_fields}


def _run_path_reference(
    path: Path,
    client_engagement: dict[str, Any] | None,
) -> str:
    """Return an absolute unmanaged path or a portable managed-run reference."""

    if client_engagement is None:
        return path.as_posix()
    run_root_value = client_engagement.get("run_root")
    if not isinstance(run_root_value, str) or not run_root_value.strip():
        raise ValueError("Managed Variance Analysis context has no run_root.")
    run_root = Path(run_root_value).expanduser().resolve(strict=True)
    resolved = path.expanduser().resolve(strict=True)
    try:
        relative = resolved.relative_to(run_root)
    except ValueError as exc:
        raise ValueError("Variance Analysis path is outside the current run.") from exc
    if not relative.parts:
        raise ValueError("Variance Analysis path must identify a run artifact.")
    return relative.as_posix()


def _data_posture(
    input_path: Path,
    recipe_path: Path | None,
    language: str,
    client_engagement: dict[str, Any] | None = None,
) -> dict[str, Any]:
    local_files = [_run_path_reference(input_path, client_engagement)]
    if recipe_path is not None:
        local_files.append(_run_path_reference(recipe_path, client_engagement))
    return {
        "local_files_read": local_files,
        "external_connectors_used": [],
        "upload_paths_used": [],
        "remote_sql_execution_used": False,
        "hosted_notebook_execution_used": False,
        "calculation_mode": "local_deterministic_scripts",
        "notes": list(_review_copy(language)["data_posture_notes"]),
    }


def _base_item(
    item_id: str,
    item_type: str,
    title: str,
    *,
    allowed_actions: Sequence[str],
    recommended_action: str,
    source_path: str | None = None,
    output_path: str | None = None,
    references: Sequence[dict[str, Any]] = (),
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
        "references": list(references),
        "data": data or {},
        "status": "needs_review",
    }


def _review_columns(language: str) -> list[dict[str, str]]:
    fields = (
        "item_type",
        "title",
        "recommended_action",
        "source_path",
        "output_path",
        "status",
    )
    labels = _review_copy(language)["columns"]
    return [
        {"field": field, "label": str(label)}
        for field, label in zip(fields, labels, strict=True)
    ]


def _num(value: Any) -> float:
    try:
        return float(value or 0.0)
    except (TypeError, ValueError):
        return 0.0


def _top_driver_rows(result_rows: Sequence[dict[str, Any]]) -> list[dict[str, Any]]:
    rows = sorted(
        result_rows,
        key=lambda row: abs(_num(row.get("total_delta"))),
        reverse=True,
    )
    return list(rows[:MAX_DRIVER_ROWS])


def _driver_items(
    result_rows: Sequence[dict[str, Any]], language: str
) -> list[dict[str, Any]]:
    copy = _review_copy(language)
    items: list[dict[str, Any]] = []
    for index, row in enumerate(_top_driver_rows(result_rows), start=1):
        dimensions = [
            key
            for key in row
            if key
            not in {
                "amount_baseline",
                "amount_comparison",
                "total_delta",
                "price_variance",
                "volume_variance",
                "mix_variance",
                "component_reconciliation_delta",
                "net_delta",
                "margin_delta",
            }
            and not key.startswith("margin_")
        ]
        title_parts = [
            str(row.get(dimension))
            for dimension in dimensions[:3]
            if row.get(dimension) not in (None, "")
        ]
        title = " / ".join(title_parts) or str(copy["driver_row"]).format(index=index)
        items.append(
            _base_item(
                f"variance-driver-{index}",
                "variance_driver",
                title,
                output_path="variance_results.csv",
                allowed_actions=("accept", "edit", "mark_unclear", "skip"),
                recommended_action=(
                    "mark_unclear"
                    if abs(_num(row.get("component_reconciliation_delta"))) > 0.01
                    else "accept"
                ),
                references=[
                    {
                        "kind": "variance_components",
                        "total_delta": row.get("total_delta"),
                        "price_variance": row.get("price_variance"),
                        "volume_variance": row.get("volume_variance"),
                        "mix_variance": row.get("mix_variance"),
                        "component_reconciliation_delta": row.get(
                            "component_reconciliation_delta"
                        ),
                    }
                ],
                data=dict(row),
            )
        )
    if len(result_rows) > MAX_DRIVER_ROWS:
        items.append(
            _base_item(
                "variance-drivers-truncated",
                "review_artifact",
                str(copy["driver_rows_truncated"]),
                output_path="variance_results.csv",
                allowed_actions=("accept", "mark_unclear", "skip"),
                recommended_action="mark_unclear",
                data={
                    "shown_count": MAX_DRIVER_ROWS,
                    "total_count": len(result_rows),
                    "full_results": "variance_results.csv",
                },
            )
        )
    return items


def _artifact_item_type(record: dict[str, Any]) -> str:
    kind = str(record.get("kind") or "")
    if kind in {"charts", "png", "html"}:
        return "chart_artifact"
    if kind in {"contexts", "json"}:
        return "context_artifact"
    if kind in {"briefs", "reports", "tables", "md", "docx", "csv", "xlsx"}:
        return "report_artifact"
    return "review_artifact"


def _artifact_title(record: dict[str, Any], language: str) -> str:
    chart_type = record.get("chart_type")
    artifact_id = record.get("artifact_id")
    return str(
        chart_type
        or artifact_id
        or record.get("path")
        or _review_copy(language)["artifact"]
    )


def _artifact_items(manifest: dict[str, Any], language: str) -> list[dict[str, Any]]:
    records = [
        record for record in manifest.get("artifacts", []) if isinstance(record, dict)
    ][:MAX_ARTIFACT_ITEMS]
    items: list[dict[str, Any]] = []
    draft_report = manifest.get("client_report_status") != "approved_for_client_use"
    for index, record in enumerate(records, start=1):
        item_type = _artifact_item_type(record)
        missing = record.get("status") not in {"copied", "written"}
        path = str(record.get("pack_path") or record.get("path") or "")
        requires_professional_review = draft_report and path.startswith(
            "root_cause_client_report"
        )
        items.append(
            _base_item(
                f"artifact-{index}",
                item_type,
                _artifact_title(record, language),
                source_path=str(record.get("source_path") or ""),
                output_path=path,
                allowed_actions=("accept", "edit", "mark_unclear", "skip"),
                recommended_action=(
                    "mark_unclear"
                    if missing or requires_professional_review
                    else "accept"
                ),
                data=dict(record),
            )
        )
    return items


def _followup_items(followups: dict[str, Any], language: str) -> list[dict[str, Any]]:
    requests = [
        item for item in followups.get("requests", []) if isinstance(item, dict)
    ][:MAX_FOLLOWUP_ITEMS]
    return [
        _base_item(
            f"followup-{index}",
            "followup_request",
            str(
                request.get("request_id")
                or str(_review_copy(language)["followup"]).format(index=index)
            ),
            output_path="",
            allowed_actions=("accept", "reject", "edit", "mark_unclear", "skip"),
            recommended_action="mark_unclear",
            data=dict(request),
        )
        for index, request in enumerate(requests, start=1)
    ]


def _output_records(output_dir: Path) -> list[dict[str, Any]]:
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
        outputs.append(
            {
                "path": relative,
                "size_bytes": path.stat().st_size,
                "kind": path.suffix.lower().lstrip(".") or "file",
                "status": "written",
            }
        )
    return outputs


def _standard_context_summary(standard_context: dict[str, Any]) -> dict[str, Any]:
    totals = standard_context.get("totals") or {}
    dominant = standard_context.get("dominant_component") or {}
    return {
        "total_delta": totals.get("total_delta"),
        "amount_baseline": totals.get("amount_baseline"),
        "amount_comparison": totals.get("amount_comparison"),
        "component_sum": totals.get("component_sum"),
        "other_residual": totals.get("other_residual"),
        "dominant_component": dominant,
    }


def write_run_intake(
    output_dir: Path,
    input_path: Path,
    *,
    recipe_path: Path | None,
    recipe: dict[str, Any],
    source_row_count: int,
    client_engagement: dict[str, Any] | None = None,
) -> RunIntakeResult:
    """Write run intake before the heavy legacy variance calculation."""

    language = _normalize_language(recipe.get("language"))
    copy = _review_copy(language)
    context_run_id = (
        str(client_engagement["run_id"]) if client_engagement is not None else None
    )
    run_id = context_run_id or _run_id(input_path)
    options = recipe.get("options") or {}
    mappings = recipe.get("mappings") or {}
    accounting_review = recipe.get("accounting_review") or {}
    unresolved_questions = _localize_accounting_questions(
        accounting_intake_questions(accounting_review),
        language,
    )
    input_ref = _run_path_reference(input_path, client_engagement)
    output_ref = _run_path_reference(output_dir, client_engagement)
    recipe_ref = (
        _run_path_reference(recipe_path, client_engagement)
        if recipe_path is not None
        else None
    )
    payload = {
        "schema_version": SCHEMA_VERSION,
        "plugin": PLUGIN_NAME,
        "workflow": WORKFLOW_NAME,
        "run_id": run_id,
        "client_engagement": _portable_client_engagement(client_engagement),
        **(
            {"path_reference": "run_root_relative"}
            if client_engagement is not None
            else {}
        ),
        "created_at": _utc_now(),
        "language": language,
        "input_paths": [input_ref],
        "output_dir": output_ref,
        "inferred_task": "variance_chart_report_payload",
        "data_posture": _data_posture(
            input_path,
            recipe_path,
            language,
            client_engagement,
        ),
        "assumptions": {
            "source_row_count": source_row_count,
            "recipe_path": recipe_ref,
            "mappings": mappings,
            "comparison_basis": options.get("comparison_basis"),
            "period_comparison_mode": options.get("period_comparison_mode"),
            "currency": options.get("currency") or "EUR",
            "root_cause_bridge": options.get("root_cause_bridge"),
            "root_cause_bridge_alternative_sweep": options.get(
                "root_cause_bridge_alternative_sweep"
            ),
            "root_cause_component_bridge": options.get("root_cause_component_bridge"),
            "waterfall_chart": options.get("waterfall_chart"),
            "waterfall_small_multiples": options.get("waterfall_small_multiples"),
            "accounting_review": accounting_review,
        },
        "unresolved_questions": unresolved_questions,
        "dependency_check": {
            "status": "not_run_by_script",
            "note": copy["dependency_note"],
        },
        "status": "ready_for_variance_run",
    }
    return RunIntakeResult(
        run_id=run_id,
        path=_write_json(output_dir / "run_intake.json", payload),
    )


def write_review_session_artifacts(
    output_dir: Path,
    input_path: Path,
    *,
    run_id: str,
    run_intake_path: Path,
    recipe_path: Path | None,
    recipe: dict[str, Any],
    result_rows: Sequence[dict[str, Any]],
    audit: dict[str, Any],
    client_engagement: dict[str, Any] | None = None,
) -> ReviewSessionResult:
    """Write chart/report review payload, pending decisions, and artifacts."""

    language = _normalize_language(recipe.get("language"))
    copy = _review_copy(language)
    outputs = _output_records(output_dir)
    standard_context = _load_json(output_dir / "standard_variance_context.json")
    standard_summary = _standard_context_summary(standard_context)
    accounting_readiness = audit.get("accounting_readiness") or {}
    accounting_status = str(accounting_readiness.get("accounting_status") or "partial")
    client_report_status = str(
        accounting_readiness.get("client_report_status")
        or "draft_pending_professional_review"
    )
    items: list[dict[str, Any]] = []
    items.extend(_driver_items(result_rows, language))
    items.extend(
        _artifact_items(
            {
                "artifacts": outputs,
                "client_report_status": client_report_status,
            },
            language,
        )
    )
    items.append(
        _base_item(
            "accounting-readiness",
            "context_artifact",
            str(copy["accounting_title"]),
            output_path="variance_audit.json",
            allowed_actions=(
                "accept",
                "edit",
                "mark_unclear",
                "request_more_documents",
            ),
            recommended_action=(
                "accept"
                if client_report_status == "approved_for_client_use"
                else "mark_unclear"
            ),
            data=accounting_readiness,
        )
    )
    items.append(
        _base_item(
            "standard-variance-context",
            "context_artifact",
            str(copy["context_title"]),
            output_path="standard_variance_context.json",
            allowed_actions=("accept", "edit", "mark_unclear", "skip"),
            recommended_action="accept" if standard_context else "mark_unclear",
            data=standard_context,
        )
    )

    chart_count = sum(
        1
        for item in outputs
        if isinstance(item, dict) and item.get("kind") in {"png", "html"}
    )
    table_count = sum(
        1
        for item in outputs
        if isinstance(item, dict) and item.get("kind") in {"csv", "xlsx"}
    )
    mappings = recipe.get("mappings") or {}
    options = recipe.get("options") or {}
    source_ref = _run_path_reference(input_path, client_engagement)
    review_payload = {
        "schema_version": SCHEMA_VERSION,
        "plugin": PLUGIN_NAME,
        "workflow": WORKFLOW_NAME,
        "run_id": run_id,
        "client_engagement": _portable_client_engagement(client_engagement),
        "created_at": _utc_now(),
        "language": language,
        "source_paths": [source_ref],
        "review_type": "variance_chart_report_review",
        "items": items,
        "item_count": len(items),
        "columns": _review_columns(language),
        "source_artifacts": {
            "run_intake": _as_output_ref(run_intake_path, output_dir),
            "recipe": _as_output_ref(recipe_path, output_dir),
            "used_recipe": "used_recipe.json",
            "variance_results": "variance_results.csv",
            "variance_audit": "variance_audit.json",
            "variance_summary": "variance_summary.md",
            "standard_context": "standard_variance_context.json",
        },
        "allowed_actions": [
            "accept",
            "reject",
            "edit",
            "mark_unclear",
            "request_more_documents",
            "skip",
        ],
        "status": (
            "blocked"
            if accounting_status == "blocked"
            else "ready_for_professional_review"
        ),
        "summary": {
            "result_row_count": len(result_rows),
            "chart_count": chart_count,
            "table_count": table_count,
            "comparison_basis": options.get("comparison_basis"),
            "period_comparison_mode": options.get("period_comparison_mode"),
            "baseline_period": mappings.get("baseline_period"),
            "comparison_period": mappings.get("comparison_period"),
            "amount_column": mappings.get("amount_column"),
            "dimensions": mappings.get("dimensions") or [],
            "currency": options.get("currency") or "EUR",
            "accounting_readiness": accounting_readiness,
            **standard_summary,
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
    )
    outputs = _output_records(output_dir)
    outputs = [
        output
        for output in outputs
        if not (
            isinstance(output, dict) and output.get("path") == review_handoff_path.name
        )
    ]
    outputs.append(_review_handoff_output_record(review_handoff_path, language))

    unresolved_items = _localize_accounting_questions(
        [
            str(item)
            for item in accounting_readiness.get("unresolved_items", [])
            if str(item).strip()
        ],
        language,
    )
    final_artifacts_path = _write_json(
        output_dir / "final_artifacts.json",
        {
            "schema_version": SCHEMA_VERSION,
            "plugin": PLUGIN_NAME,
            "workflow": WORKFLOW_NAME,
            "run_id": run_id,
            "completed_at": _utc_now(),
            "outputs": outputs,
            "caveats": [*list(copy["caveats"]), *unresolved_items],
            "next_actions": list(copy["next_actions"]),
            "accounting_readiness": accounting_readiness,
            "status": (
                "blocked"
                if accounting_status == "blocked"
                else "written_pending_review"
            ),
        },
    )
    _append_execution_trace(
        run_intake_path,
        final_artifacts_path,
        command=["python", "plugins/variance-analysis/scripts/run_variance.py"],
    )

    return ReviewSessionResult(
        run_intake_path=run_intake_path,
        review_payload_path=review_payload_path,
        ui_decisions_path=ui_decisions_path,
        final_artifacts_path=final_artifacts_path,
        review_item_count=len(items),
    )
