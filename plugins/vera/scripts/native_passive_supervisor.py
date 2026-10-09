"""Long-running owned audit supervisor; preserve actual producer output after faults."""

from __future__ import annotations

import json
import os
import re
import signal
import sys
from contextlib import contextmanager
from pathlib import Path
from types import SimpleNamespace
from typing import Iterator

__all__ = ["main"]


@contextmanager
def producer_guard(path: Path, identity: str) -> Iterator[None]:
    """Serialize against all native output writes using an identifiable owned guard."""
    with path.open("xb") as stream:
        stream.write(identity.encode())
    path.chmod(0o600)
    try:
        yield
    finally:
        if path.read_bytes() != identity.encode():
            raise ValueError("Invoice producer guard changed; preserve uncertain job")
        path.unlink()


def producer_owned(name: str) -> bool:
    """Fixed public producer namespaces, never a semantic artifact classifier."""
    return (
        name
        in {
            "audit.sqlite3",
            "audit.sqlite3-wal",
            "audit.sqlite3-shm",
            "full_population.jsonl",
            "ledger_entries_without_invoice.jsonl",
            "run_summary.json",
            "run_summary.md",
            "exception_workpaper.xlsx",
        }
        or name.startswith(".invoice_staging/")
        or bool(re.match(r"luna_chunks/chunk-[0-9a-f]{16}/", name))
    )


def main() -> None:
    """Hold a live OS lease through the actual public worker and post-write replay."""
    root, path = Path(sys.argv[1]), Path(sys.argv[2])
    if root.name != "passive-invoice-audit":
        raise PermissionError("Unsupported producer")
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    sys.path.insert(0, str(root / "scripts"))
    for vendor in (
        root / "vendor/modules",
        root.parent / "_shared/vendor/modules",
        root.parent.parent / "vendor/modules",
    ):
        if (vendor / "vera_assurance").is_dir():
            sys.path.insert(0, str(vendor))
            break
    import audit_core as producer
    import cowork_worker
    import luna_worker
    import native_workspace as api
    from native_passive_audit import build_plan, inspect_job, job_population, run_job
    from native_passive_service import current, lease, read_record, save_record, scoped

    request = read_record(path, api)
    if request is None or request["status"] != "accepted":
        raise ValueError("Missing or already consumed invoice intent")
    binding, identity = request["binding"], request["operation_ref"]
    loaded = api.load_binding(binding)
    private = api.ui_state_directory(Path(loaded["output_dir"]), create=False)
    if path != private / ("passive-operation-" + identity + ".json") or request[
        "scope"
    ] != scoped(binding):
        raise PermissionError("Invoice intent belongs to another scope")

    def interrupted(signum: int, frame: object) -> None:
        # Python unwinding waits for the public executor/capsule to drain before
        # releasing ownership. A hard kill remains uncertain, never auto-resumed.
        raise KeyboardInterrupt("Audit supervisor termination requested")

    signal.signal(signal.SIGTERM, interrupted)
    result = None
    with lease(private / ("passive-lease-" + identity + ".lock"), create=True):
        try:
            with producer_guard(private / "write.lock", identity):
                value = current(root, binding, loaded, api)
                if (
                    loaded["run"] != request["loaded_run"]
                    or loaded["input_manifest"] != request["input_manifest"]
                    or loaded["run"]["status"] != "running"
                    or value["implementation"] != request["implementation"]
                    or value["population"] != request["population"]
                    or job_population(Path(loaded["output_dir"]))
                    != request["population"]
                ):
                    raise ValueError(
                        "Invoice launch source, implementation or output changed"
                    )
                if read_record(path, api)["status"] != "accepted":
                    raise ValueError("Invoice launch intent was already consumed")
                save_record(
                    path, {**request, "status": "running", "pid": os.getpid()}, api
                )
                sys.stdout.write(
                    json.dumps({"operation_ref": identity, "status": "running"}) + "\n"
                )
                sys.stdout.flush()
                sys.stdout.close()
                workers = SimpleNamespace(
                    configured_runtime=cowork_worker.configured_runtime,
                    load_worker_selection=luna_worker.load_worker_selection,
                )
                plan = build_plan(
                    producer, loaded["context"], request["recipe"], workers
                )
                if plan["fingerprint"] != request["job_ref"]:
                    raise ValueError("Invoice job fingerprint changed before worker")
                error = None
                try:
                    run_job(
                        producer,
                        plan,
                        (
                            cowork_worker.run_cowork_chunk
                            if plan["config"].worker_runtime == "cowork"
                            else luna_worker.run_luna_chunk
                        ),
                    )
                except producer.AuditError as exc:
                    error = str(exc)
                if (
                    api.load_binding(binding) != loaded
                    or current(root, binding, loaded, api)["implementation"]
                    != request["implementation"]
                ):
                    raise ValueError(
                        "Invoice run or implementation changed during worker"
                    )
                inspected = inspect_job(producer, plan, {})
                population = job_population(Path(loaded["output_dir"]))
                if any(
                    not producer_owned(name)
                    and request["population"].get(name) != digest
                    for name, digest in population.items()
                ) or any(
                    not producer_owned(name) and population.get(name) != digest
                    for name, digest in request["population"].items()
                ):
                    raise ValueError(
                        "Concurrent unrelated invoice output change; preserve uncertain job"
                    )
                if (
                    inspected["status"]
                    not in {"completed", "failed", "awaiting_semantic_review"}
                    or error
                    and inspected["status"] != "failed"
                ):
                    raise ValueError(
                        "Producer did not reach a verified terminal audit state"
                    )
                verified = {
                    "status": inspected["status"],
                    "error": error,
                    "population": population,
                    "inspection_revision": inspected["revision"],
                    "professional_approval": False,
                    "archive_completed": False,
                }
            # A verified producer result does not excuse a changed write guard.
            # Commit terminal success only after the ownership guard exits cleanly.
            result = verified
        finally:
            # Unexpected faults and hard process loss never authorize a restart.
            # No authoritative producer output, SQLite or chunk is rolled back.
            save_record(
                path,
                {
                    **request,
                    **(
                        result
                        or {
                            "status": "uncertain",
                            "error": "Supervisor ended without a verified producer result; inspect its diagnostic log and existing worker/chunk evidence.",
                        }
                    ),
                },
                api,
            )


if __name__ == "__main__":
    main()
