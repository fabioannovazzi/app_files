"""Bind each acquisition client to an Archive run before the local worker starts."""

from __future__ import annotations

import sys
from dataclasses import asdict
from pathlib import Path
from typing import Any

from .contracts import AcquisitionError, Plan
from .storage import atomic_json, read_json

__all__ = ["prepare_runs", "finish_runs"]


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
        if client.vat_number in bindings:
            binding = bindings[client.vat_number]
            if (
                binding["client_id"] != client.archive_client_id
                or binding["engagement_id"] != client.archive_engagement_id
            ):
                raise AcquisitionError("archive-client-identity-mismatch")
    for client in plan.clients:
        if client.vat_number in bindings:
            binding = bindings[client.vat_number]
            archive.start_studio_client_workflow(
                binding["client_id"], binding["engagement_id"], binding["run_id"]
            )
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
        loaded = archive.ledger.load_run(
            Path(binding["context_path"]).parents[5],
            binding["engagement_id"],
            binding["run_id"],
        )
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
        request_path = run / "model_data_worker_input.json"
        if request_path.is_file():
            request = read_json(request_path)
            request["run_id"] = binding["run_id"]
            phase = request["phases"][0]
            count = sum(
                event.get("status") in {"downloaded", "verified_existing"}
                for event in client_events
                if event.get("kind") == "invoice"
            )
            measurement = {
                "unit": "files",
                "quantity": count,
                "label": "originali acquisiti o riverificati",
                "basis": "measured",
            }
            phase["source_extent"] = [measurement]
            phase["locally_processed"] = [measurement]
            phase["remained_local"] = [measurement]
            phase["evidence_files"] = ["acquisition-evidence.json"]
            atomic_json(output / "model_data_report_input.json", request)
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
