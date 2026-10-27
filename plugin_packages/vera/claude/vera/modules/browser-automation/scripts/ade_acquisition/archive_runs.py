"""Bind each acquisition client to an Archive run before the local worker starts."""

from __future__ import annotations

import json
import sqlite3
import sys
from dataclasses import asdict
from functools import wraps
from pathlib import Path
from typing import Any
from uuid import uuid4

from .contracts import AcquisitionError, Plan
from .storage import Store, atomic_json, read_json

__all__ = [
    "prepare_runs",
    "finish_runs",
    "record_acquired_event",
    "record_status_payload",
]


def _loaded_binding(archive: Any, binding: dict[str, Any]) -> dict[str, Any]:
    """Use the selected run's immutable identity, including an explicit restore."""
    root = Path(binding["context_path"]).parents[5]
    try:
        loaded = archive.ledger._load_run_identity(
            root, binding["engagement_id"], binding["run_id"]
        )
    except (OSError, archive.ledger.LedgerError):
        root = archive._selected_ledger_root(
            binding["client_id"],
            binding["engagement_id"],
            run_id=binding["run_id"],
            state_dir=archive._state_dir(None),
        )
        loaded = archive.ledger._load_run_identity(
            root, binding["engagement_id"], binding["run_id"]
        )
    if (
        loaded["run"]["client_id"] != binding["client_id"]
        or loaded["run"]["workflow_id"] != "agenzia-acquisition"
    ):
        raise AcquisitionError("archive-client-identity-mismatch")
    return loaded


def _reporting_boundary(function):
    """A measurement outage must not cancel a saved acquisition or its delivery."""

    @wraps(function)
    def wrapped(run, *args, **kwargs):
        try:
            return function(run, *args, **kwargs)
        except (
            OSError,
            ValueError,
            KeyError,
            TypeError,
            sqlite3.Error,
            ImportError,
        ) as error:
            gap = {
                "status": "unavailable",
                "measurement_gap": True,
                "stage": function.__name__,
                "reason": type(error).__name__,
                "gap_saved": False,
            }
            try:
                directory = run / "reporting-issues"
                directory.mkdir(mode=0o700, exist_ok=True)
                atomic_json(
                    directory / (uuid4().hex + ".json"), {**gap, "gap_saved": True}
                )
                gap["gap_saved"] = True
            except (OSError, ValueError):
                pass
            # Attribute an incomplete report only to verified acquisition runs.
            try:
                archive = _archive()
                archive.ledger._reporting_runtime()
                from archive_reporting_failure import reporting_failure

                for binding in read_json(run / "archive-runs.json").values():
                    try:
                        loaded = _loaded_binding(archive, binding)
                    except (OSError, ValueError, KeyError, TypeError):
                        continue  # A foreign/unavailable binding cannot hide other gaps.
                    reporting_failure(
                        "agenzia-acquisition",
                        {},
                        error,
                        stage=function.__name__,
                        root=Path(loaded["run_root"]),
                    )
            except (
                OSError,
                ValueError,
                KeyError,
                TypeError,
                sqlite3.Error,
                ImportError,
            ):
                pass  # The independent worker gap still records unavailable attribution.
            try:
                sys.stderr.write(json.dumps(gap) + "\n")
            except OSError:
                pass
            return gap

    return wrapped


@_reporting_boundary
def record_status_payload(
    run: Path, summary: dict[str, Any], payload: Any, *, channel: str
) -> None:
    """Record the producer's status/count projection in each bound client run.

    Acquisition never includes downloaded document contents in this projection;
    per-client app-only details are excluded by the caller before this boundary.
    """
    path = run / "archive-runs.json"
    if not path.is_file():
        return
    archive = _archive()
    archive.ledger._reporting_runtime()
    from archive_report_store import RunStore, digest, run_lock
    from archive_reporting import record_send

    for binding in read_json(path).values():
        loaded = _loaded_binding(archive, binding)
        root = Path(loaded["run_root"])
        with run_lock(root):
            store = RunStore(root)
            state = store.state()
            if state is None:
                raise AcquisitionError("archive-reporting-start-missing")
            if state["collection_closed"]:
                continue
            store.event(
                "metadata:" + digest(summary),
                {"kind": "prepared_metadata", "data_sha256": digest(summary)},
            )
            record_send(root, payload, channel=channel + ":agenzia-acquisition")


@_reporting_boundary
def record_acquired_event(run: Path, storage: Store, event: dict[str, Any]) -> None:
    """Measure originals at acquisition, under their existing client Archive run."""
    bindings_path = run / "archive-runs.json"
    if not bindings_path.is_file() or not event.get("record", {}).get("artifacts"):
        return
    binding = read_json(bindings_path)[event["client"]]
    archive = _archive()
    archive.ledger._reporting_runtime()  # Resolve the installed product runtime.
    from archive_report_measurements import measure_source
    from archive_report_store import RunStore, digest, run_lock

    root = Path(_loaded_binding(archive, binding)["run_root"])
    with run_lock(root):
        collector = RunStore(root)
        if not storage.verified(event["record"]):
            collector.error("acquired_source_verification_failed")
            return
        for artifact in event["record"]["artifacts"]:
            path = storage.safe_path(artifact["path"])
            source = measure_source(
                path,
                source_id="acquired_"
                + digest({"path": str(path), "sha256": artifact["sha256"]})[:24],
            )
            if source["sha256"] != artifact["sha256"]:
                collector.error("acquired_source_verification_failed")
                continue
            collector.source(source)


def _archive():
    scripts = Path(__file__).resolve().parents[3] / "studio-archive/scripts"
    if not scripts.is_dir():
        raise AcquisitionError("studio-archive-component-unavailable")
    if str(scripts) not in sys.path:
        sys.path.insert(0, str(scripts))
    import archive_core

    return archive_core


def prepare_runs(run: Path, plan: Plan) -> None:
    """Persist idempotent per-client bindings, never combine client evidence."""
    archive = _archive()
    try:
        _prepare_runs(archive, run, plan)
    except (archive.ArchiveError, archive.ledger.LedgerError) as exc:
        raise AcquisitionError("archive-run-preparation-failed") from exc


def _prepare_runs(archive: Any, run: Path, plan: Plan) -> None:
    if any(
        not client.archive_client_id or not client.archive_engagement_id
        for client in plan.clients
    ):
        raise AcquisitionError("archive-binding-required")
    bindings_path = run / "archive-runs.json"
    bindings = read_json(bindings_path) if bindings_path.exists() else {}
    # Check every selected identity and engagement before importing any plan.
    for client in plan.clients:
        if client.vat_number in bindings:
            binding = bindings[client.vat_number]
            if (
                binding["client_id"] != client.archive_client_id
                or binding["engagement_id"] != client.archive_engagement_id
            ):
                raise AcquisitionError("archive-client-identity-mismatch")
            loaded = _loaded_binding(archive, binding)
            binding["context_path"] = str(Path(loaded["run_root"]) / "context.json")
            continue
        resolved = archive.resolve_studio_client_identity(
            "tax_identifier", client.tax_code
        )
        if (
            resolved.get("resolution_status") != "exact_match"
            or resolved["matches"][0]["client_id"] != client.archive_client_id
        ):
            raise AcquisitionError("archive-client-identity-mismatch")
        root = Path(
            archive.get_studio_client_folder(client.archive_client_id)["client_folder"][
                "client_root"
            ]
        )
        engagement = archive.ledger.load_engagement_manifest(
            root, client.archive_engagement_id
        )
        if (
            engagement["client_id"] != client.archive_client_id
            or engagement["status"] != "open"
        ):
            raise AcquisitionError("archive-engagement-not-open")
    for client in plan.clients:
        if client.vat_number in bindings:
            binding = bindings[client.vat_number]
            archive.start_studio_client_workflow(
                binding["client_id"], binding["engagement_id"], binding["run_id"]
            )
            atomic_json(bindings_path, bindings)
            continue
        folder = run / "archive-plans" / client.archive_client_id
        folder.mkdir(parents=True, exist_ok=True, mode=0o700)
        plan_file = folder / "plan.json"
        atomic_json(plan_file, {**plan.payload(), "clients": [asdict(client)]})
        imported = archive.import_studio_client_document(
            client.archive_client_id,
            source_path=plan_file,
            role="source",
            engagement_id=client.archive_engagement_id,
        )
        receipt = imported["input_receipt"]
        prepared = archive.prepare_studio_client_workflow(
            client.archive_engagement_id,
            "agenzia-acquisition",
            input_ids=[receipt["input_id"]],
            idempotency_key="agenzia:" + run.name + ":" + client.archive_client_id,
        )
        archive.start_studio_client_workflow(
            client.archive_client_id,
            client.archive_engagement_id,
            prepared["run"]["run_id"],
        )
        bindings[client.vat_number] = {
            "client_id": client.archive_client_id,
            "engagement_id": client.archive_engagement_id,
            "run_id": prepared["run"]["run_id"],
            "context_path": prepared["client_engagement_path"],
        }
        atomic_json(bindings_path, bindings)


def finish_runs(run: Path, state: dict[str, Any]) -> None:
    """Retain each client's worker evidence and its Archive outcome."""
    binding_path = run / "archive-runs.json"
    if not binding_path.is_file():
        return
    archive = _archive()
    try:
        _finish_runs(archive, run, state)
    except (archive.ArchiveError, archive.ledger.LedgerError) as exc:
        raise AcquisitionError("archive-run-evidence-failed") from exc


def _finish_runs(archive: Any, run: Path, state: dict[str, Any]) -> None:
    binding_path = run / "archive-runs.json"
    from .engine import load_events

    events = load_events(run)
    for vat, binding in read_json(binding_path).items():
        loaded = _loaded_binding(archive, binding)
        if loaded["run"]["status"] in {"ready_for_review", "completed", "cancelled"}:
            continue
        if loaded["run"]["status"] == "failed":
            archive.start_studio_client_workflow(
                binding["client_id"], binding["engagement_id"], binding["run_id"]
            )
        output = Path(loaded["output_dir"])
        client_events = [event for event in events if event.get("client") == vat]
        atomic_json(
            output / "acquisition-evidence.json",
            {"state": state["state"], "events": client_events},
        )
        if state["state"] == "cancelled":
            archive.cancel_studio_client_workflow(
                binding["client_id"], binding["engagement_id"], binding["run_id"]
            )
        elif state["state"] == "failed":
            archive.fail_studio_client_workflow(
                binding["client_id"],
                binding["engagement_id"],
                binding["run_id"],
                "acquisition-worker-did-not-complete",
            )
        # Successful local acquisition is not the end of model review. Leave the
        # Archive run running until that review records its reads and finalizes.
