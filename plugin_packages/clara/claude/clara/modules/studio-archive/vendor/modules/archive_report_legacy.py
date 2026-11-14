"""Read retained schema-3 reports without changing their historical meaning."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Mapping

from archive_report_store import digest
from selective_reporting import report_pipeline

__all__ = ["validate_report", "render_report"]
REPORT_SCHEMA = 3


def validate_report(value: Any) -> dict[str, Any]:
    """Reject changed bytes and invalid execution bindings before receipt creation."""
    if (
        not isinstance(value, dict)
        or value.get("schema_version") != REPORT_SCHEMA
        or value.get("product") != "vera"
    ):
        raise ValueError("Not an automatic Archive report")
    required = {
        "schema_version",
        "product",
        "run_id",
        "workflow_id",
        "user_id",
        "report_revision",
        "started_at",
        "finished_at",
        "outcome",
        "language",
        "errors",
        "collection_closed",
        "closing_calls",
        "collection_status",
        "sources",
        "tool_results",
        "model_context_characters",
        "model_context_bytes",
        "report_id",
    }
    if set(value) != required:
        raise ValueError("Automatic Archive report fields are invalid")
    if (
        report_pipeline(value.get("workflow_id", "")) is None
        or re.fullmatch(r"run_[0-9a-f]{24}", value.get("run_id", "")) is None
    ):
        raise ValueError("Report lacks a selected Archive execution")
    from uuid import UUID

    if value["user_id"] is not None:
        UUID(value["user_id"])
    elif "vera_machine_identity_unavailable" not in value["errors"]:
        raise ValueError("Missing Vera userID must be reported as an identity failure")
    body = {key: item for key, item in value.items() if key != "report_id"}
    if value.get("report_id") != "archive_report_" + digest(body)[:24]:
        raise ValueError("Archive report content hash does not match")
    if value["collection_status"] not in {"complete", "incomplete"}:
        raise ValueError("Invalid reporting collection status")
    if type(value["report_revision"]) is not int or value["report_revision"] < 1:
        raise ValueError("Report revision must be a positive integer")
    if (
        value["outcome"] not in {"running", "completed", "failed", "cancelled"}
        or type(value["collection_closed"]) is not bool
    ):
        raise ValueError("Invalid Archive reporting lifecycle")
    if value["collection_closed"] and (
        value["finished_at"] is None or value["outcome"] == "running"
    ):
        raise ValueError("Only a terminal Archive execution can close reporting")
    if not isinstance(value["errors"], list) or any(
        not isinstance(error, str) or not error for error in value["errors"]
    ):
        raise ValueError("Invalid collection failure evidence")
    if (value["collection_status"] == "complete") != (not value["errors"]):
        raise ValueError("Collection failures cannot be described as complete")
    source_ids = set()
    for source in value["sources"]:
        if source["source_id"] in source_ids:
            raise ValueError("Duplicate report source identity")
        source_ids.add(source["source_id"])
        for field in (
            "source_quantity",
            "observed_quantity",
            "observed_cells",
            "source_bytes",
        ):
            if type(source[field]) is not int or source[field] < 0:
                raise ValueError("Source measurements must be non-negative integers")
        if source["observed_quantity"] > source["source_quantity"]:
            raise ValueError("Observed source units exceed their population")
        if (
            source["source_cells"] is not None
            and source["observed_cells"] > source["source_cells"]
        ):
            raise ValueError("Observed source cells exceed their population")
        if value["collection_status"] == "complete":
            if (
                source["remaining_local"]
                != source["source_quantity"] - source["observed_quantity"]
            ):
                raise ValueError("Local source remainder does not match observed units")
        elif (
            source["remaining_local"] is not None
            or source["remaining_local_cells"] is not None
        ):
            raise ValueError("Incomplete collection cannot assert a local remainder")
    if value["model_context_bytes"] != sum(
        event["bytes"] for event in value["tool_results"]
    ) or value["model_context_characters"] != sum(
        event["characters"] for event in value["tool_results"]
    ):
        raise ValueError("Model-context totals differ from retained events")
    return value


_REPORT_COPY = {
    "it": (
        "Report dei dati al modello",
        "Processo",
        "Esecuzione",
        "Inizio",
        "Fine",
        "in corso",
        "Esito",
        "Rilevazione",
        "Fonte locale",
        "Unità",
        "Disponibili",
        "Osservate nel contesto del modello",
        "Rimaste locali",
        "non determinabile",
        "Celle",
        "Risultati osservati",
        "caratteri",
        "Rilevazione incompleta: i conteggi osservati non dimostrano che gli altri dati siano rimasti locali.",
        "Il report e le evidenze restano su questa macchina. Il server riceve l’impronta del report con Vera userID, esecuzione, revisione e versione del prodotto.",
    ),
    "en": (
        "Model-data report",
        "Pipeline",
        "Run",
        "Started",
        "Finished",
        "in progress",
        "Outcome",
        "Collection",
        "Local source",
        "Unit",
        "Available",
        "Observed in model context",
        "Remaining local",
        "unknown",
        "Cells",
        "Observed results",
        "characters",
        "Incomplete collection: observed counts do not establish that the other data remained local.",
        "The report and evidence remain on this machine. The server receives the report hash with Vera userID, run, revision and product version.",
    ),
    "fr": (
        "Rapport des données au modèle",
        "Processus",
        "Exécution",
        "Début",
        "Fin",
        "en cours",
        "Résultat",
        "Collecte",
        "Source locale",
        "Unité",
        "Disponibles",
        "Observées dans le contexte du modèle",
        "Restées locales",
        "indéterminé",
        "Cellules",
        "Résultats observés",
        "caractères",
        "Collecte incomplète : les décomptes observés ne prouvent pas que les autres données sont restées locales.",
        "Le rapport et les preuves restent sur cette machine. Le serveur reçoit l’empreinte du rapport avec Vera userID, l’exécution, la révision et la version du produit.",
    ),
    "de": (
        "Bericht zu Modelldaten",
        "Prozess",
        "Ausführung",
        "Beginn",
        "Ende",
        "läuft",
        "Ergebnis",
        "Erfassung",
        "Lokale Quelle",
        "Einheit",
        "Verfügbar",
        "Im Modellkontext beobachtet",
        "Lokal verblieben",
        "unbekannt",
        "Zellen",
        "Beobachtete Ergebnisse",
        "Zeichen",
        "Unvollständige Erfassung: Beobachtete Zählwerte belegen nicht, dass die übrigen Daten lokal geblieben sind.",
        "Bericht und Nachweise bleiben auf diesem Gerät. Der Server erhält den Berichtshash mit Vera userID, Ausführung, Revision und Produktversion.",
    ),
    "es": (
        "Informe de datos al modelo",
        "Proceso",
        "Ejecución",
        "Inicio",
        "Fin",
        "en curso",
        "Resultado",
        "Recogida",
        "Fuente local",
        "Unidad",
        "Disponibles",
        "Observadas en el contexto del modelo",
        "Permanecieron locales",
        "desconocido",
        "Celdas",
        "Resultados observados",
        "caracteres",
        "Recogida incompleta: los recuentos observados no demuestran que los demás datos permanecieran locales.",
        "El informe y las pruebas permanecen en esta máquina. El servidor recibe la huella del informe con Vera userID, ejecución, revisión y versión del producto.",
    ),
}
_REASONS_IT = {
    "final_host_result_pending": "In attesa del risultato dello strumento che ha concluso l’esecuzione.",
    "host_tool_observation_missing": "Mancano osservazioni degli strumenti del modello; verificare che gli hook del plugin siano attivi e autorizzati.",
    "concurrent_run_scope_ambiguous": "Più esecuzioni sono attive nella stessa chat; non è possibile attribuire tutte le letture a una sola esecuzione.",
    "some_tool_output_has_no_source_coordinates": "Parte del contenuto mostrato al modello non è riconducibile a righe o documenti della popolazione misurata.",
    "source_measurement_unavailable": "Una fonte non può essere misurata con gli adattatori disponibili.",
    "derived_output_lineage_unavailable": "È stato letto un risultato derivato, senza un collegamento verificabile alle righe originali.",
    "vera_machine_identity_unavailable": "Vera userID non è disponibile; il report non può ancora essere associato alla macchina sul server.",
    "host_collection_failed": "La raccolta automatica ha registrato un errore.",
    "additional_user_context_not_measured": "Durante l’esecuzione sono arrivati nuovi messaggi o allegati, non inclusi nei conteggi delle fonti.",
    "hosted_tool_output_not_measured": "Uno strumento remoto ha restituito contenuto non misurato.",
}


def render_report(report: Mapping[str, Any]) -> str:
    """Render counts, identifiable local sources and explicit measurement limits."""
    c = _REPORT_COPY.get(report["language"], _REPORT_COPY["en"])
    lines = [
        f"# {c[0]}",
        "",
        f"{c[1]}: **{report['workflow_id']}**",
        f"{c[2]}: `{report['run_id']}` · Vera userID: `{report['user_id']}`",
        f"{c[3]}: {report['started_at']} · {c[4]}: {report['finished_at'] or c[5]}",
        f"{c[6]}: {report['outcome']} · {c[7]}: {report['collection_status']}",
        "",
        f"| {c[8]} | {c[9]} | {c[10]} | {c[11]} | {c[12]} |",
        "|---|---|---:|---:|---:|",
    ]
    import html

    for source in report["sources"]:
        label = (
            html.escape(source["label"])
            .replace("|", "&#124;")
            .replace("\n", " ")
            .replace("\r", " ")
        )
        remaining = (
            source["remaining_local"]
            if source["remaining_local"] is not None
            else c[13]
        )
        lines.append(
            f"| {label} | {source['unit']} | {source['source_quantity']} | {source['observed_quantity']} | {remaining} |"
        )
        if source["source_cells"] is not None:
            remaining_cells = (
                source["remaining_local_cells"]
                if source["remaining_local_cells"] is not None
                else c[13]
            )
            lines.append(
                f"| ↳ {label} | {c[14]} | {source['source_cells']} | {source['observed_cells']} | {remaining_cells} |"
            )
    lines.extend(
        [
            "",
            f"{c[15]}: {len(report['tool_results'])}; {report['model_context_characters']} {c[16]}.",
        ]
    )
    if report["errors"]:
        lines.extend(["", f"**{c[17]}**", ""])
        for error in report["errors"]:
            reason = (
                _REASONS_IT.get(error.split(":", 1)[0])
                if report["language"] == "it"
                else None
            )
            lines.append(f"- {reason} (`{error}`)" if reason else f"- `{error}`")
    lines.extend(["", c[18], ""])
    return "\n".join(lines)
