"""Automatic reports owned by Studio Archive start/end writes.

Every selected run produces a local report. Evidence collection failures are
reported as failures of measurement, never as exemptions from reporting.
"""

from __future__ import annotations

import hashlib
import json
import re
import secrets
import sqlite3
from pathlib import Path
from typing import Any, Mapping

from archive_report_measurements import (
    direct_read_selection,
    measure_source,
    read_selection,
)
from archive_report_store import (
    RunStore,
    atomic_json,
    canonical,
    digest,
    now,
    registry_for_run,
    serialized_run,
)
from selective_reporting import report_pipeline

__all__ = [
    "begin_run",
    "snapshot_run",
    "finish_run",
    "record_send",
    "read_artifact",
    "validate_report",
    "render_report",
]

REPORT_SCHEMA = 4
REPORT_FILES = (
    "model_data_report.json",
    "model_data_report.md",
    "model_data_receipt_request.json",
    "model_data_receipt.json",
    "model_data_receipt.html",
)


def _identity() -> str:
    from operational_incidents import reporting_credentials

    return reporting_credentials()["installation_id"]


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
            "measurement_scope": "vera_sent_data",
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
            "measurement_scope": "vera_sent_data",
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
    try:
        registry_for_run(root).register(run["run_id"], root)
    except (ValueError, OSError, sqlite3.Error):
        store.error("receipt_retry_registration_failed")
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
    packet = {
        **result,
        "vera_reporting": {
            "run_id": state["run_id"],
            "token": token,
            "kind": "archive_metadata",
        },
    }
    record_send(
        Path(loaded["run_root"]), packet, channel="archive_metadata", event_id=token
    )
    return packet


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
        if not value.strip():
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
    """Return an exact run artifact and record what Vera sends before returning."""
    store = RunStore(Path(loaded["run_root"]))
    state = store.state()
    if state is None or state["finished_at"] is not None:
        raise ValueError(
            "Data reads require this Archive run's active reporting record"
        )
    path = path.expanduser()
    if not path.is_absolute():
        # Resolve against the selected run, never the resident service's cwd.
        path = Path(loaded["run_root"]) / path
    path = path.absolute()
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
    packet = {
        "data": data,
        "vera_reporting": {"run_id": state["run_id"], "token": token},
    }
    record_send(
        Path(loaded["run_root"]), packet, channel="archive_read", event_id=token
    )
    return packet


@serialized_run
def record_send(
    root: Path,
    response: Any,
    *,
    channel: str,
    event_id: str | None = None,
    request: Any = None,
    expected_revision: int | None = None,
) -> None:
    """Persist Vera's outgoing payload at its own boundary, independent of the host.

    Exact payload hashes and source coordinates are mechanical evidence. This
    function never observes host tools, transcripts or provider receipt.
    """
    store = RunStore(root)
    state = store.state()
    if state is None or state["collection_closed"]:
        raise ValueError("Outgoing data requires an active Archive reporting record")
    if expected_revision is not None and state["report_revision"] != expected_revision:
        raise ValueError("Archive revision changed before its result was sent")
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
    projections = [item for item in retained if item["kind"] == "prepared_projection"]
    table_projections = {
        (item["artifact_path"], item["artifact_sha256"]): item
        for item in retained
        if item["kind"] == "prepared_table_projection"
    }
    unmapped = False
    whole_projection = next(
        (item for item in projections if item["data_sha256"] == digest(response)),
        None,
    )
    if whole_projection is not None:
        selections.extend(whole_projection["selections"])
    # Producers can register a complete MCP envelope or worker submission. Its
    # exact digest covers all fields; changed envelopes still take the ordinary
    # per-piece path and cannot inherit the original declaration.
    for piece in [] if whole_projection is not None else _pieces(response):
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
                    artifact_selection = {
                        **selection,
                        "basis": "vera_registered_packet",
                    }
                    selections.append(artifact_selection)
                    projection = next(
                        (
                            item
                            for item in projections
                            if item["artifact_sha256"] == selection["source_sha256"]
                        ),
                        None,
                    )
                    projected_source = next(
                        (
                            source
                            for source in store.sources()
                            if source["source_id"] == selection["source_id"]
                            and source["sha256"] == selection["source_sha256"]
                        ),
                        None,
                    )
                    if (
                        projection is not None
                        and projected_source is not None
                        and selection["unit"] in {"documents", "lines"}
                        and selection["start"] == 0
                        and selection["stop"] == projected_source["quantity"]
                        and selection["columns"] == [0]
                    ):
                        artifact_selection["source_lineage_verified"] = True
                        selections.extend(projection["selections"])
                    table = (
                        table_projections.get(
                            (projected_source["path"], selection["source_sha256"])
                        )
                        if projected_source is not None
                        else None
                    )
                    if (
                        table is not None
                        and projected_source is not None
                        and table["unit"] == selection["unit"]
                        and len(table["cells"]) == projected_source["quantity"]
                        and table["columns"] == projected_source["columns"]
                    ):
                        # The exact file hash binds the producer's output-cell
                        # map. Only cells actually returned can add input origins.
                        selected_cells = [
                            row[column]
                            for row in table["cells"][
                                selection["start"] : selection["stop"]
                            ]
                            for column in selection["columns"]
                        ]
                        artifact_selection["source_lineage_verified"] = all(
                            cell is not None for cell in selected_cells
                        )
                        selections.extend(
                            origin
                            for cell in selected_cells
                            if cell is not None
                            for origin in cell
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
        if digest(piece) in metadata.values():
            mapped = True
        if (
            isinstance(piece, str)
            and piece
            and all(
                digest(line) in metadata.values()
                for line in piece.splitlines(keepends=True)
            )
        ):
            # A CLI transport can join several independently declared status
            # lines. Every byte must still belong to a producer declaration;
            # one extra line keeps the whole payload explicitly unmapped.
            mapped = True
        for projection in projections:
            if digest(piece) == projection["data_sha256"]:
                selections.extend(projection["selections"])
                mapped = True
        for source in [] if mapped else store.sources():
            selection = direct_read_selection(source, request, piece)
            if selection is not None:
                selections.append(selection)
                mapped = True
        unmapped |= not mapped
    text = (
        response if isinstance(response, str) else canonical(response).decode("utf-8")
    )
    # Payload content stays in the local evidence ledger; the report keeps counts
    # and hashes. The receipt service never receives the payload.
    payload = {
        "kind": "vera_send",
        "channel": channel,
        "response_sha256": digest(response),
        "characters": len(text),
        "bytes": len(text.encode("utf-8")),
        "selections": selections,
        "unmapped": unmapped,
        "evidence_basis": "vera_outgoing_payload",
        "local_response": response,
    }
    store.event("send:" + (event_id or secrets.token_hex(24)), payload)


def _report(
    loaded: Mapping[str, Any], store: RunStore, state: dict[str, Any]
) -> dict[str, Any]:
    events = [item for item in store.events() if item["kind"] == "vera_send"]
    errors = list(state["errors"])
    if any(item["unmapped"] for item in events):
        errors.append("sent_data_has_no_source_coordinates")
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
        if (
            source["role"] == "output"
            and _union_count(row_intervals)
            and any(
                selection["source_id"] == source["source_id"]
                and not selection.get("source_lineage_verified", False)
                for event in events
                for selection in event["selections"]
            )
        ):
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
                "sent_quantity": _union_count(row_intervals),
                "sent_cells": sum(
                    _union_count(intervals) for intervals in column_intervals.values()
                ),
                "not_sent_quantity": None,
                "not_sent_cells": None,
            }
        )
    complete = not errors
    if complete:
        for source in sources:
            source["not_sent_quantity"] = (
                source["source_quantity"] - source["sent_quantity"]
            )
            source["not_sent_cells"] = (
                source["source_cells"] - source["sent_cells"]
                if source["source_cells"] is not None
                else None
            )
    body = {
        **state,
        "collection_status": "complete" if complete else "incomplete",
        "errors": sorted(set(errors)),
        "sources": sources,
        "emissions": [
            {key: value for key, value in event.items() if key != "local_response"}
            for event in events
        ],
        "sent_characters": sum(event["characters"] for event in events),
        "sent_bytes": sum(event["bytes"] for event in events),
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
        state["finished_at"] = loaded["run"]["updated_at"]
        state["outcome"] = loaded["run"]["status"]
        store.save(state)
    state["collection_closed"] = True
    store.save(state)
    queue_available = True
    try:
        registry_for_run(root).close(state["run_id"])
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
            registry_for_run(root).receipt_result(
                root, result["server_receipt"]["status"]
            )
        except (ValueError, OSError, sqlite3.Error):
            # The durable queue remains pending; an idempotent retry is safe.
            pass
    return result


def _legacy_shape(report: Mapping[str, Any]) -> dict[str, Any]:
    """Reuse mechanical validation while retaining the new scope in saved bytes."""
    aliases = {
        "sent_quantity": "observed_quantity",
        "sent_cells": "observed_cells",
        "not_sent_quantity": "remaining_local",
        "not_sent_cells": "remaining_local_cells",
    }
    value = dict(report)
    value.pop("measurement_scope")
    value["schema_version"] = 3
    value["closing_calls"] = {}
    value["sources"] = [
        {aliases.get(key, key): item for key, item in source.items()}
        for source in value["sources"]
    ]
    for current, previous in (
        ("emissions", "tool_results"),
        ("sent_bytes", "model_context_bytes"),
        ("sent_characters", "model_context_characters"),
    ):
        value[previous] = value.pop(current)
    value.pop("report_id")
    value["report_id"] = "archive_report_" + digest(value)[:24]
    return value


def validate_report(value: Any) -> dict[str, Any]:
    """Validate the exact saved report, including its declared sending boundary."""
    from archive_report_legacy import validate_report as validate_legacy

    if isinstance(value, dict) and value.get("schema_version") == 3:
        return validate_legacy(value)
    if (
        not isinstance(value, dict)
        or value.get("schema_version") != REPORT_SCHEMA
        or value.get("measurement_scope") != "vera_sent_data"
    ):
        raise ValueError("Not a Vera outgoing-data report")
    body = {key: item for key, item in value.items() if key != "report_id"}
    if value.get("report_id") != "archive_report_" + digest(body)[:24]:
        raise ValueError("Vera report content hash does not match")
    try:
        validate_legacy(_legacy_shape(value))
    except (KeyError, TypeError) as exc:
        raise ValueError("Invalid Vera outgoing-data report fields") from exc
    for event in value["emissions"]:
        if (
            event.get("kind") != "vera_send"
            or event.get("evidence_basis") != "vera_outgoing_payload"
        ):
            raise ValueError("A Vera report requires Vera's own sending records")
    return value


_SENDING_COPY = {
    "it": (
        "Dati inviati da Vera al modello",
        "Inviate da Vera",
        "Non inviate da Vera",
        "Invii registrati",
        "Questo report misura esclusivamente i dati emessi da Vera durante questa esecuzione. Non ispeziona la chat o le attività di altri strumenti.",
        "Misurazione incompleta: una parte dei dati inviati non dispone di coordinate verificabili nella fonte.",
    ),
    "en": (
        "Data Vera sent to the model",
        "Sent by Vera",
        "Not sent by Vera",
        "Recorded sends",
        "This report measures only data emitted by Vera during this run. It does not inspect the chat or other tools' activity.",
        "Incomplete measurement: some sent data lacks verifiable source coordinates.",
    ),
    "fr": (
        "Données envoyées au modèle par Vera",
        "Envoyées par Vera",
        "Non envoyées par Vera",
        "Envois enregistrés",
        "Ce rapport mesure uniquement les données émises par Vera pendant cette exécution. Il n’inspecte ni la conversation ni les autres outils.",
        "Mesure incomplète : certaines données envoyées ne disposent pas de coordonnées vérifiables dans la source.",
    ),
    "de": (
        "Von Vera an das Modell gesendete Daten",
        "Von Vera gesendet",
        "Von Vera nicht gesendet",
        "Erfasste Sendungen",
        "Dieser Bericht misst ausschließlich die von Vera während dieser Ausführung ausgegebenen Daten. Er untersucht weder den Chat noch die Aktivitäten anderer Werkzeuge.",
        "Unvollständige Messung: Für einige gesendete Daten fehlen überprüfbare Quellkoordinaten.",
    ),
    "es": (
        "Datos enviados al modelo por Vera",
        "Enviados por Vera",
        "No enviados por Vera",
        "Envíos registrados",
        "Este informe mide únicamente los datos emitidos por Vera durante esta ejecución. No inspecciona el chat ni la actividad de otras herramientas.",
        "Medición incompleta: algunos datos enviados carecen de coordenadas verificables en la fuente.",
    ),
}


def render_report(report: Mapping[str, Any]) -> str:
    """Explain Vera's exact sending scope without claiming host observation."""
    import html

    from archive_report_legacy import _REPORT_COPY
    from archive_report_legacy import render_report as render_legacy

    if report["schema_version"] == 3:
        return render_legacy(report)
    language = report["language"] if report["language"] in _SENDING_COPY else "en"
    c = _REPORT_COPY[language]
    s = _SENDING_COPY[language]
    lines = [
        f"# {s[0]}",
        "",
        s[4],
        "",
        f"{c[1]}: **{report['workflow_id']}**",
        f"{c[2]}: `{report['run_id']}` · Vera userID: `{report['user_id']}`",
        f"{c[3]}: {report['started_at']} · {c[4]}: {report['finished_at'] or c[5]}",
        f"{c[6]}: {report['outcome']} · {c[7]}: {report['collection_status']}",
        "",
        f"| {c[8]} | {c[9]} | {c[10]} | {s[1]} | {s[2]} |",
        "|---|---|---:|---:|---:|",
    ]
    for source in report["sources"]:
        label = (
            html.escape(source["label"])
            .replace("|", "&#124;")
            .replace("\n", " ")
            .replace("\r", " ")
        )
        remainder = (
            source["not_sent_quantity"]
            if source["not_sent_quantity"] is not None
            else c[13]
        )
        lines.append(
            f"| {label} | {source['unit']} | {source['source_quantity']} | {source['sent_quantity']} | {remainder} |"
        )
        if source["source_cells"] is not None:
            cells = (
                source["not_sent_cells"]
                if source["not_sent_cells"] is not None
                else c[13]
            )
            lines.append(
                f"| ↳ {label} | {c[14]} | {source['source_cells']} | {source['sent_cells']} | {cells} |"
            )
    lines.extend(
        [
            "",
            f"{s[3]}: {len(report['emissions'])}; {report['sent_characters']} {c[16]}.",
        ]
    )
    if report["errors"]:
        lines.extend(
            ["", f"**{s[5]}**", "", *(f"- `{error}`" for error in report["errors"])]
        )
    lines.extend(["", c[18], ""])
    return "\n".join(lines)
