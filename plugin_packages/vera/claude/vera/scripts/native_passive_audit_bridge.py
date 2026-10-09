"""Isolated passive-audit foundation; no source paths or model substitutions from UI."""

from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path
from types import SimpleNamespace

__all__ = ["main"]


def main() -> None:
    """Reload authoritative receipts before preparing or inspecting an exact job."""
    root = Path(sys.argv[1])
    if root.name != "passive-invoice-audit" or root.is_symlink():
        raise PermissionError("Unsupported passive-invoice producer")
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
    from native_passive_audit import (
        build_plan,
        implementation,
        inspect_job,
        object_file,
    )
    from vera_assurance import load_client_engagement_context_file

    request = json.loads(sys.stdin.read(2_000_001))
    if not isinstance(request, dict) or set(request) - {
        "operation",
        "context",
        "recipe",
        "args",
    }:
        raise ValueError("Unknown passive-invoice request")
    if request["operation"] == "info":
        runtime = cowork_worker.configured_runtime()
        sys.stdout.write(
            json.dumps({"implementation": implementation(producer), "runtime": runtime})
        )
        return
    if request["operation"] not in {"plan", "inspect"}:
        # Long execution will be exposed only through the supervised native
        # launcher; this foundation cannot bypass durable intent/authorization.
        raise ValueError("Unsupported passive-invoice foundation action")
    context = load_client_engagement_context_file(
        Path(request["context"]),
        expected_workflow_id="passive-invoice-audit",
        allowed_statuses=("running", "ready_for_review", "completed"),
    )
    plan = build_plan(
        producer,
        context,
        request["recipe"],
        SimpleNamespace(
            configured_runtime=cowork_worker.configured_runtime,
            load_worker_selection=luna_worker.load_worker_selection,
        ),
    )
    if request["operation"] == "plan":
        ledger = producer.load_ledger(
            plan["paths"]["ledger"],
            plan["paths"]["ledger_mapping"],
            sheet=request["recipe"]["controls"]["ledger_sheet"],
        )
        with tempfile.TemporaryDirectory(prefix="vera-passive-intake-") as temporary:
            invoices = producer.parse_invoice_population(
                plan["invoice_source"], Path(temporary).resolve()
            )
            items, orphans = producer.match_population(
                invoices, ledger, plan["config"].amount_tolerance
            )
        if not invoices:
            raise ValueError("Invoice population is empty")
        result = {
            "job_ref": plan["fingerprint"],
            "run_id": context["run_id"],
            "recipe": request["recipe"],
            "output": context["output_dir"],
            "worker_runtime": plan["config"].worker_runtime,
            "worker_model": plan["config"].worker_model,
            "professional_approval": False,
            "mapping": object_file(plan["paths"]["ledger_mapping"]),
            "ledger_row_count": len(ledger),
            "population": len(invoices),
            "match_counts": {
                state: sum(row["match_state"] == state for row in items)
                for state in (
                    "matched",
                    "ambiguous_match",
                    "invoice_not_found_in_ledger",
                    "duplicate_candidate",
                )
            },
            "ledger_orphan_count": len(orphans),
        }
    else:
        result = inspect_job(producer, plan, request.get("args", {}))
    # Rehydrate again to refuse source/run changes while reading the producer.
    if context != load_client_engagement_context_file(
        Path(request["context"]),
        expected_workflow_id="passive-invoice-audit",
        allowed_statuses=("running", "ready_for_review", "completed"),
    ):
        raise ValueError("Passive-invoice run changed during inspection")
    sys.stdout.write(json.dumps(result, ensure_ascii=False))


if __name__ == "__main__":
    main()
