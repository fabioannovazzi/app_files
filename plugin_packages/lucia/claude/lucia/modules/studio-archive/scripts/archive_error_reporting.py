"""Retain Archive's exact failed responses for their explicitly selected run."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Mapping

__all__ = ["record_error"]


def record_error(
    arguments: Mapping[str, Any],
    payload: dict[str, Any],
    *,
    channel: str,
    state_dir: Path | None = None,
) -> bool:
    """Bind by verified client, engagement and run IDs, never by the last chat run."""
    import archive_core as core
    import client_ledger as ledger

    identities = tuple(
        arguments.get(key) for key in ("client_id", "engagement_id", "run_id")
    )
    if not all(isinstance(value, str) and value for value in identities):
        return False
    client_id, engagement_id, run_id = identities
    try:
        folder = core.get_studio_client_folder(client_id, state_dir=state_dir)[
            "client_folder"
        ]
        client_root = Path(folder["client_root"])
        engagement = ledger.load_engagement_manifest(client_root, engagement_id)
        root, run_path, _, _ = ledger._load_run_paths(
            client_root, engagement_id, run_id
        )
        # Failure diagnostics still belong to this run when an input is missing.
        # Verify sealed ownership here without reopening the failing input tree.
        run = ledger._validate_run_manifest(
            ledger._read_json(run_path, label="run manifest")
        )
    except (core.ArchiveError, ledger.LedgerError):
        # Invalid/unregistered identities have no report owner. Do not search for
        # another active run, retry old receipts or create reporting state.
        return False
    if (
        engagement["client_id"] != client_id
        or (run["client_id"], run["engagement_id"], run["run_id"]) != identities
    ):
        return False
    if not ledger._reporting_runtime().selective_reporting_enabled():
        return False
    from archive_report_store import RunStore
    from archive_reporting import record_send
    from selective_reporting import report_pipeline

    if report_pipeline(run["workflow_id"]) is None:
        return False
    store = RunStore(root)
    if not store.path.is_file():
        return False  # A prepared run has no started collection to amend.
    state = store.state()
    if state is None or state["collection_closed"]:
        return False
    if (state["run_id"], state["workflow_id"]) != (run_id, run["workflow_id"]):
        raise ValueError("Error reporting state belongs to another Archive run")
    # Error text may include client values or paths. Record the actual response;
    # never declare arbitrary diagnostics to be source-free metadata.
    record_send(
        root,
        payload,
        channel=channel + ":studio-archive:error",
        expected_revision=state["report_revision"],
    )
    return True
