"""Automatic reports owned by Studio Archive start/end writes.

Every selected run produces a local report. Evidence collection failures are
reported as failures of measurement, never as exemptions from reporting.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import secrets
import sqlite3
from pathlib import Path
from typing import Any, Mapping

from archive_report_measurements import (
    direct_read_selection,
    measure_source,
    model_texts,
    read_selection,
)
from archive_report_store import (
    Registry,
    RunStore,
    atomic_json,
    canonical,
    digest,
    now,
    serialized_run,
)
from selective_reporting import report_pipeline

__all__ = [
    "begin_run",
    "snapshot_run",
    "finish_run",
    "observe_tool",
    "read_artifact",
    "validate_report",
    "render_report",
]

REPORT_SCHEMA = 3
REPORT_FILES = (
    "model_data_report.json",
    "model_data_report.md",
    "model_data_receipt_request.json",
    "model_data_receipt.json",
    "model_data_receipt.html",
)


def _identity() -> str:
    from operational_incidents import local_context

    return local_context()["credentials"]["installation_id"]


@serialized_run
def begin_run(loaded: Mapping[str, Any]) -> dict[str, Any]:
    """Create a reporting record at the durable running transition, before reads."""
    run = loaded["run"]
    if report_pipeline(run["workflow_id"]) is None:
        return {"status": "not_applicable", "reason": "pipeline_not_selected"}
    root = Path(loaded["run_root"])
    store = RunStore(root)
    state = store.state()
    if state is not None and (state["run_id"], state["workflow_id"]) != (
        run["run_id"],
        run["workflow_id"],
    ):
        raise ValueError("Reporting state belongs to another Archive execution")
    if state is None:
        errors = []
        try:
            user_id = _identity()
        except (ValueError, OSError, sqlite3.Error, ImportError):
            user_id = None
            errors.append("vera_machine_identity_unavailable")
        state = {
            "schema_version": REPORT_SCHEMA,
            "product": "vera",
            "run_id": run["run_id"],
            "workflow_id": run["workflow_id"],
            "user_id": user_id,
            "report_revision": 1,
            "started_at": run["updated_at"],
            "finished_at": None,
            "outcome": "running",
            "language": loaded["context"].get("language", "it"),
            "errors": errors,
            "collection_closed": False,
            "closing_calls": {},
        }
    elif state["finished_at"] is not None:
        history = store.root / "history" / str(state["report_revision"])
        for name in REPORT_FILES:
            path = Path(loaded["output_dir"]) / name
            if path.is_file():
                history.mkdir(parents=True, exist_ok=True, mode=0o700)
                path.rename(history / name)
        state = {
            **state,
            "report_revision": state["report_revision"] + 1,
            "finished_at": None,
            "outcome": "running",
            "collection_closed": False,
            "closing_calls": {},
        }
    store.save(state)
    for binding in loaded["context"]["input_bindings"]:
        try:
            source = measure_source(
                Path(binding["path"]), source_id=binding["binding_id"]
            )
            source["aliases"] = sorted({binding["path"], binding["source_path"]})
            store.source(source)
        except (ValueError, OSError):
            store.error("source_measurement_unavailable:" + binding["binding_id"])
    session = os.environ.get("CODEX_THREAD_ID") or os.environ.get(
        "VERA_STUDIO_ARCHIVE_SESSION_ID"
    )
    try:
        Registry().register(run["run_id"], root, session)
    except (ValueError, OSError, sqlite3.Error):
        store.error("host_collection_registration_failed")
    return snapshot_run(loaded)


@serialized_run
def metadata_result(
    loaded: Mapping[str, Any], result: dict[str, Any]
) -> dict[str, Any]:
    """Mark exact Archive lifecycle metadata without authoring exposure evidence."""
    if report_pipeline(loaded["run"]["workflow_id"]) is None:
        return result
    store = RunStore(Path(loaded["run_root"]))
    state = store.state()
    if state is None or state["collection_closed"]:
        return result
    token = secrets.token_hex(24)
    store.event(
        "metadata:" + token,
        {"kind": "prepared_metadata", "data_sha256": digest(result)},
    )
    return {
        **result,
        "vera_reporting": {
            "run_id": state["run_id"],
            "token": token,
            "kind": "archive_metadata",
        },
    }


def _pieces(value: Any) -> list[Any]:
    """Unwrap documented host transport envelopes, preserving unknown content."""
    if isinstance(value, list):
        return [piece for item in value for piece in _pieces(item)]
    if isinstance(value, dict):
        if isinstance(value.get("content"), list):
            pieces = _pieces(value["content"])
            if "structuredContent" in value:
                pieces.extend(_pieces(value["structuredContent"]))
            extra = {
                key: item
                for key, item in value.items()
                if key not in {"content", "structuredContent", "isError"}
            }
            if extra:
                pieces.append(extra)
            return pieces
        if value.get("type") in {"text", "input_text"} and isinstance(
            value.get("text"), str
        ):
            return _pieces(value["text"])
        if "output" in value and set(value) <= {
            "chunk_id",
            "wall_time_seconds",
            "exit_code",
            "original_token_count",
            "output",
            "session_id",
        }:
            return _pieces(value["output"])
        if "stdout" in value and set(value) <= {
            "stdout",
            "stderr",
            "interrupted",
            "isImage",
            "exit_code",
            "exitCode",
        }:
            return _pieces(value["stdout"]) + _pieces(value.get("stderr", ""))
        return [value]
    if isinstance(value, str):
        if not value.strip() or re.fullmatch(
            r"Script completed\nWall time [0-9.]+ seconds\nOutput:\n?", value
        ):
            return []
        try:
            parsed = json.loads(value)
        except ValueError:
            return [value]
        return _pieces(parsed) if parsed != value else [value]
    return [value]


@serialized_run
def read_artifact(
    loaded: Mapping[str, Any],
    path: Path,
    *,
    offset: int = 0,
    limit: int | None = None,
    columns: list[int] | None = None,
) -> dict[str, Any]:
    """Read an exact run artifact and prepare its automatically observed coordinates."""
    store = RunStore(Path(loaded["run_root"]))
    state = store.state()
    if state is None or state["finished_at"] is not None:
        raise ValueError(
            "Data reads require this Archive run's active reporting record"
        )
    path = path.expanduser().absolute()
    sources = store.sources()
    source = next(
        (item for item in sources if str(path) in item.get("aliases", [item["path"]])),
        None,
    )
    if (
        source
        and source["role"] == "output"
        and hashlib.sha256(path.read_bytes()).hexdigest() != source["sha256"]
    ):
        source = None
    if source is None:
        output = Path(loaded["output_dir"]).resolve()
        if path.is_symlink() or not path.resolve().is_relative_to(output):
            raise ValueError("Read must use a bound input or this run's output")
        version = hashlib.sha256(path.read_bytes()).hexdigest()
        source = measure_source(
            path,
            source_id="artifact_"
            + hashlib.sha256(
                (str(path.relative_to(output)) + version).encode()
            ).hexdigest()[:24],
            role="output",
        )
        store.source(source)
    data, evidence = read_selection(source, offset=offset, limit=limit, columns=columns)
    token = secrets.token_hex(24)
    store.event("packet:" + token, {"kind": "prepared_packet", "selection": evidence})
    return {"data": data, "vera_reporting": {"run_id": state["run_id"], "token": token}}


@serialized_run
def observe_tool(
    root: Path, event: Mapping[str, Any], *, ambiguous: bool = False
) -> None:
    """Record actual returned content, including direct reads outside Vera helpers."""
    store = RunStore(root)
    state = store.state()
    if state is None or state["collection_closed"]:
        return
    response = event.get("tool_response")
    selections: list[dict[str, Any]] = []
    retained = store.events()
    prepared = {
        item["event_id"].removeprefix("packet:"): item["selection"]
        for item in retained
        if item["kind"] == "prepared_packet"
    }
    metadata = {
        item["event_id"].removeprefix("metadata:"): item["data_sha256"]
        for item in retained
        if item["kind"] == "prepared_metadata"
    }
    unmapped = False
    for piece in _pieces(response):
        mapped = False
        if isinstance(piece, dict) and isinstance(piece.get("vera_reporting"), dict):
            binding = piece["vera_reporting"]
            if binding.get("run_id") == state["run_id"]:
                selection = prepared.get(binding.get("token"))
                if (
                    selection
                    and set(piece) == {"data", "vera_reporting"}
                    and digest(piece["data"]) == selection["data_sha256"]
                ):
                    selections.append(
                        {**selection, "basis": "observed_registered_packet"}
                    )
                    mapped = True
                if metadata.get(binding.get("token")) == digest(
                    {
                        key: value
                        for key, value in piece.items()
                        if key != "vera_reporting"
                    }
                ):
                    mapped = True
        for source in store.sources():
            for alias in source.get("aliases", [source["path"]]):
                observed = direct_read_selection(
                    {**source, "path": alias}, event.get("tool_input"), piece
                )
                if observed is not None:
                    selections.append(observed)
                    mapped = True
                    break
        unmapped |= not mapped
    texts = model_texts(response)
    # A tool event preserves its real evidence locally. Counts in the report do
    # not include its case text, command arguments, filenames or absolute paths.
    payload = {
        "kind": "tool_result",
        "tool": str(event.get("tool_name", "unknown")),
        "response_sha256": digest(response),
        "characters": sum(len(text) for text in texts),
        "bytes": sum(len(text.encode("utf-8")) for text in texts),
        "selections": selections,
        "ambiguous_scope": ambiguous,
        "unmapped": unmapped,
        "evidence_basis": event.get("evidence_basis", "host_post_tool_result"),
        "local_response": response,
    }
    store.event(
        "tool:" + str(event["session_id"]) + ":" + str(event["tool_use_id"]), payload
    )


def _report(
    loaded: Mapping[str, Any], store: RunStore, state: dict[str, Any]
) -> dict[str, Any]:
    events = [item for item in store.events() if item["kind"] == "tool_result"]
    errors = list(state["errors"])
    if state["finished_at"] is not None and not state["collection_closed"]:
        errors.append("final_host_result_pending")
    if not events:
        errors.append("host_tool_observation_missing")
    if any(item["ambiguous_scope"] for item in events):
        errors.append("concurrent_run_scope_ambiguous")
    if any(item["unmapped"] for item in events):
        errors.append("some_tool_output_has_no_source_coordinates")
    sources = []
    for source in store.sources():
        row_intervals = []
        column_intervals: dict[int, list[tuple[int, int]]] = {}
        for event in events:
            for selection in event["selections"]:
                if (
                    selection["source_id"] != source["source_id"]
                    or selection["source_sha256"] != source["sha256"]
                ):
                    continue
                interval = (selection["start"], selection["stop"])
                if not 0 <= interval[0] <= interval[1] <= source["quantity"] or any(
                    not 0 <= column < (source["columns"] or 1)
                    for column in selection["columns"]
                ):
                    raise ValueError(
                        "Observed selection is outside its measured source"
                    )
                if selection["columns"]:
                    row_intervals.append(interval)
                for column in selection["columns"]:
                    column_intervals.setdefault(column, []).append(interval)
        if source["measurement_error"]:
            errors.append("source_measurement_unavailable:" + source["source_id"])
        if source["role"] == "output" and row_intervals:
            # A normalized or derived artifact can repeat original source data.
            # Its measured size alone cannot establish an input-local remainder.
            errors.append("derived_output_lineage_unavailable:" + source["source_id"])
        sources.append(
            {
                "source_id": source["source_id"],
                "label": Path(source["path"]).name,
                "role": source["role"],
                "source_sha256": source["sha256"],
                "source_bytes": source["bytes"],
                "unit": source["unit"],
                "source_quantity": source["quantity"],
                "source_cells": source["cells"],
                "observed_quantity": _union_count(row_intervals),
                "observed_cells": sum(
                    _union_count(intervals) for intervals in column_intervals.values()
                ),
                "remaining_local": None,
                "remaining_local_cells": None,
            }
        )
    complete = not errors
    if complete:
        for source in sources:
            source["remaining_local"] = (
                source["source_quantity"] - source["observed_quantity"]
            )
            source["remaining_local_cells"] = (
                source["source_cells"] - source["observed_cells"]
                if source["source_cells"] is not None
                else None
            )
    body = {
        **state,
        "collection_status": "complete" if complete else "incomplete",
        "errors": sorted(set(errors)),
        "sources": sources,
        "tool_results": [
            {key: value for key, value in event.items() if key != "local_response"}
            for event in events
        ],
        "model_context_characters": sum(event["characters"] for event in events),
        "model_context_bytes": sum(event["bytes"] for event in events),
    }
    return {**body, "report_id": "archive_report_" + digest(body)[:24]}


def _union_count(intervals: list[tuple[int, int]]) -> int:
    """Count unique physical units without allocating one object per cell."""
    count = 0
    covered_until = 0
    for start, stop in sorted(intervals):
        count += max(0, stop - max(start, covered_until))
        covered_until = max(covered_until, stop)
    return count


@serialized_run
def snapshot_run(loaded: Mapping[str, Any]) -> dict[str, Any]:
    """Save a readable local report even when measurements are incomplete."""
    store = RunStore(Path(loaded["run_root"]))
    state = store.state()
    if state is None:
        raise ValueError("Archive start did not initialize reporting")
    report = _report(loaded, store, state)
    output = Path(loaded["output_dir"])
    atomic_json(output / "model_data_report.json", report)
    markdown = render_report(report)
    target = output / "model_data_report.md"
    if target.is_symlink():
        raise ValueError("Report Markdown must not be a symlink")
    from archive_report_store import atomic_bytes

    atomic_bytes(target, markdown.encode("utf-8"))
    return {
        "status": "available",
        "collection_status": report["collection_status"],
        "report_id": report["report_id"],
        "report_path": str(output / "model_data_report.json"),
        "display_markdown": markdown,
        "server_receipt": {"status": "not_requested", "reason": "run_active"},
    }


@serialized_run
def finish_run(loaded: Mapping[str, Any]) -> dict[str, Any]:
    """Close the reporting record at the same durable terminal Archive write."""
    store = RunStore(Path(loaded["run_root"]))
    state = store.state()
    if state is None:
        begin_run(loaded)
        state = store.state()
        state["errors"].append("archive_start_evidence_missing")
    if loaded["run"]["status"] not in {"completed", "failed", "cancelled"}:
        if loaded["run"]["status"] == "ready_for_review":
            path = Path(loaded["run_root"]) / "model_data_reporting.json"
            if path.is_file():
                return json.loads(path.read_text(encoding="utf-8"))
        return snapshot_run(loaded)
    from archive_report_seal import checkpoint, reseal

    root = Path(loaded["run_root"])
    baseline = checkpoint(root)
    if state["finished_at"] is None:
        from archive_report_transcript import closing_calls

        state["closing_calls"] = closing_calls(root)
        # Transcript collection may have retained a measurement failure.
        state["errors"] = store.state()["errors"]
        state["finished_at"] = loaded["run"]["updated_at"]
        state["outcome"] = loaded["run"]["status"]
        store.save(state)
    from archive_report_transcript import barrier_complete

    if not barrier_complete(root, state["closing_calls"]):
        result = snapshot_run(loaded)
        result["server_receipt"] = {
            "status": "pending",
            "reason": "final_host_result_pending",
        }
        reseal(root, baseline)
        atomic_json(root / "model_data_reporting.json", result)
        return result
    state["collection_closed"] = True
    store.save(state)
    queue_available = True
    try:
        Registry().close(state["run_id"])
    except (ValueError, OSError, sqlite3.Error):
        queue_available = False
        store.error("receipt_retry_queue_unavailable")
    result = snapshot_run(loaded)
    from archive_report_receipt import stamp_report

    result["server_receipt"] = stamp_report(Path(result["report_path"]))
    reseal(root, baseline)
    atomic_json(Path(loaded["run_root"]) / "model_data_reporting.json", result)
    if queue_available:
        try:
            Registry().receipt_result(root, result["server_receipt"]["status"])
        except (ValueError, OSError, sqlite3.Error):
            # The durable queue remains pending; an idempotent retry is safe.
            pass
    return result


@serialized_run
def close_observed_run(root: Path) -> None:
    """Finish a pending terminal write after its outer result is actually visible."""
    state = RunStore(root).state()
    run = json.loads((root / "run.json").read_text(encoding="utf-8"))
    if (
        state
        and run["status"] in {"completed", "failed", "cancelled"}
        and not state["collection_closed"]
    ):
        if state["finished_at"] is None:
            RunStore(root).error("terminal_collection_recovered_after_interruption")
        from archive_report_transcript import refresh

        for path in (root / "reporting").glob("host-*.json"):
            refresh(root, json.loads(path.read_text(encoding="utf-8"))["session"])
        finish_run(
            {
                "run_root": str(root),
                "output_dir": str(root / "outputs"),
                "run": run,
            }
        )


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
