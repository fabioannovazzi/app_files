"""Create an isolated synthetic ESG foundation demo without real-client data."""

from __future__ import annotations

import argparse
import importlib.util
import json
import logging
from pathlib import Path

from esg_case import WORKFLOW, ESGError, execute, resume_case

__all__ = ["main", "run_demo"]


def run_demo(destination: Path) -> dict:
    """Demonstrate recovery, exact provenance, stale dependencies and isolation."""
    destination = destination.expanduser().resolve()
    if destination.exists():
        raise ESGError(
            "Choose a new demo directory; existing work is never overwritten"
        )
    module_root = Path(__file__).resolve().parents[1]
    if destination.is_relative_to(module_root):
        raise ESGError("Demo output must be outside the installed component")
    spec = importlib.util.spec_from_file_location(
        "esg_demo_ledger",
        module_root.parent / "studio-archive/scripts/client_ledger.py",
    )
    ledger = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(ledger)
    destination.mkdir(parents=True)
    root = destination / "synthetic-client"
    root.mkdir()
    client = "client_" + "e" * 24
    ledger.create_client_manifest(root, client)
    engagement = ledger.create_engagement(
        root, client, "Synthetic ESG foundation demo"
    )["engagement_id"]
    source = destination / "energy.csv"
    source.write_text("period,kwh\n2026,0\n2025,\n", encoding="utf-8")
    original = ledger.import_document(root, client, engagement, source, "source")[
        "receipt"
    ]
    prepared = ledger.prepare_run(
        root,
        client,
        engagement,
        WORKFLOW,
        "0.1.0",
        input_ids=[original["input_id"]],
        idempotency_key="demo-first-run",
    )
    ledger.start_run(root, engagement, prepared["run"]["run_id"])
    context = Path(prepared["context_path"])
    start = {
        "idempotency_key": "case",
        "case_id": "esg-synthetic-2026",
        "previous_context": None,
        "record": {
            "service": "preparation",
            "reporting_basis": "unresolved",
            "period": {"start": "2026-01-01", "end": "2026-12-31"},
            "jurisdiction": "IT",
            "framework_version": None,
            "assurance_level": "not_applicable",
            "synthetic": True,
        },
    }
    execute(context, "start_case", start)

    def mutation(command: str, request: dict) -> dict:
        return execute(
            context,
            command,
            {"expected_state_sha256": resume_case(context)["state_sha256"], **request},
        )

    observation = {
        "status": "observed",
        "value": "0",
        "unit": "kWh",
        "rationale": "Read the synthetic input cell",
        "disclosure_id": None,
        "metric_id": "energy",
    }
    bind = {
        "id": "energy",
        "idempotency_key": "energy-v1",
        "input_id": original["input_id"],
        "locator": {"row": 1, "column": "kwh"},
        "observation": observation,
    }
    evidence = mutation("bind_evidence", bind)
    missing = mutation(
        "bind_evidence",
        {
            **bind,
            "id": "prior-year",
            "idempotency_key": "missing",
            "locator": {"row": 2, "column": "kwh"},
            "observation": {
                **observation,
                "status": "not_available",
                "value": None,
                "rationale": "The supplied prior-year cell is empty",
            },
        },
    )
    not_applicable = mutation(
        "bind_evidence",
        {
            **bind,
            "id": "excluded-observation",
            "idempotency_key": "not-applicable",
            "locator": {"row": 2, "column": "kwh"},
            "observation": {
                **observation,
                "status": "not_applicable",
                "value": None,
                "rationale": "Synthetic reviewer declaration for this demo only",
            },
        },
    )
    source_ref = mutation(
        "register_source",
        {
            "id": "synthetic-criteria",
            "idempotency_key": "source",
            "record": {
                "title": "Synthetic criteria, not an ESG standard",
                "publisher": "Demo",
                "url": "https://example.invalid/synthetic-criteria",
                "version": "demo-1",
                "applicability_period": start["record"]["period"],
                "review_status": "unverified_seed",
                "catalogue_complete": False,
                "legal_review_approved": False,
                "locator": "Demo only",
                "rationale": "No legal applicability asserted",
            },
        },
    )
    review = {
        "id": "mapping-review",
        "idempotency_key": "review",
        "dependencies": [evidence["reference"], source_ref["reference"]],
        "record": {
            "type": "scope",
            "decided_by": "SYNTHETIC REVIEWER",
            "decided_on": "2026-09-29",
            "outcome": "approved",
            "decision": "Accept the synthetic mapping for demonstration",
            "rationale": "Source cell and missing-data separation inspected",
        },
    }
    approved = mutation("record_decision", review)
    artifact = mutation(
        "build_deliverables",
        {
            "id": "evidence-memo",
            "idempotency_key": "draft",
            "claim": "partial_draft",
            "title": "Synthetic ESG evidence memo",
            "content": "Supplied current-year cell: 0 kWh. Prior-year value: missing. No framework, catalogue or compliance conclusion is approved.",
            "dependencies": [
                approved["reference"],
                missing["reference"],
                not_applicable["reference"],
            ],
        },
    )
    before = resume_case(context)
    replay = execute(context, "start_case", start)
    foreign_rejected = False
    try:
        mutation(
            "record_decision",
            {
                **review,
                "idempotency_key": "wrong-engagement",
                "dependencies": [
                    {**evidence["reference"], "engagement_id": "eng_" + "f" * 24}
                ],
            },
        )
    except ESGError:
        foreign_rejected = True
    old_context = context
    source.write_text("period,kwh\n2026,15\n2025,\n", encoding="utf-8")
    updated = ledger.import_document(root, client, engagement, source, "source")[
        "receipt"
    ]
    successor = ledger.prepare_run(
        root,
        client,
        engagement,
        WORKFLOW,
        "0.1.0",
        input_ids=[original["input_id"], updated["input_id"]],
        idempotency_key="demo-update-run",
    )
    ledger.start_run(root, engagement, successor["run"]["run_id"])
    context = Path(successor["context_path"])
    execute(context, "start_case", {**start, "previous_context": str(old_context)})
    mutation(
        "bind_evidence",
        {
            **bind,
            "idempotency_key": "energy-v2",
            "input_id": updated["input_id"],
            "observation": {**observation, "value": "15"},
        },
    )
    after = resume_case(context)
    obsolete = [item["reference"] for item in after["objects"] if not item["current"]]
    checks = {
        "replay_without_duplicates": replay["status"] == "replayed"
        and resume_case(old_context)["revision"] == before["revision"],
        "cross_engagement_rejected": foreign_rejected,
        "prior_approval_stale": approved["reference"] in obsolete,
        "dependent_draft_stale": artifact["reference"] in obsolete,
        "new_observation_current": after["objects"][-1]["current"],
        "missing_and_not_applicable_distinct": before["objects"][2]["record"][
            "observation"
        ]["status"]
        == "not_available"
        and before["objects"][3]["record"]["observation"]["status"] == "not_applicable",
    }
    result = {
        "synthetic": True,
        "checks": checks,
        "first_context": str(old_context),
        "current_context": str(context),
        "current_state": after,
        "limitations": "Foundation demonstration only. No model-read attestation, professional opinion, release, publication or live-client acceptance.",
    }
    (destination / "demo_result.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=2) + "\n"
    )
    (destination / "README.md").write_text(
        "# Synthetic ESG foundation demo\n\n"
        + "\n".join(f"- {name}: {passed}" for name, passed in checks.items())
        + "\n\nCurrent context: "
        + str(context)
        + "\n\nThe former memo and approval are obsolete in the successor. Both runs and original inputs are retained.\n"
    )
    if not all(checks.values()):
        raise ESGError(
            "Synthetic acceptance checks failed; inspect saved demo_result.json"
        )
    return {
        "status": "passed",
        "checks": checks,
        "result": str(destination / "demo_result.json"),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = run_demo(args.output)
    logging.info("Synthetic demo: %s", json.dumps(result))
    return 0


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    raise SystemExit(main())
