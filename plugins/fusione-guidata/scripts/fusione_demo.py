"""Exercise P0 with synthetic entities, missing evidence and a changed liability."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from fusione_case import CaseStore, reference
from fusione_model import CaseError
from fusione_report import export_report

__all__ = ["run_demo"]


def run_demo(destination: Path) -> dict[str, Any]:
    """Persist acquisition, approval, selective reopening and negative controls."""
    destination = destination.expanduser().resolve()
    destination.mkdir(mode=0o700, parents=True, exist_ok=False)
    source = destination / "synthetic-inputs"
    source.mkdir()
    (source / "liability.txt").write_text(
        "SYNTHETIC: potential liability EUR 100.00; later revised to EUR 150.00.\n",
        encoding="utf-8",
    )
    (source / "source.txt").write_text(
        "SYNTHETIC rule source. No real legal proposition.\n", encoding="utf-8"
    )
    store = CaseStore.create(
        destination / "case",
        "demo_reviewer",
        {
            "operation_type": "fusione",
            "objectives": "SYNTHETIC P0 demonstration",
            "jurisdictions": ["IT"],
            "planned_date": "2026-12-01",
            "actual_date": None,
        },
        synthetic=True,
    )
    entities = []
    for entity_id in ("alpha", "beta"):
        entities.append(
            store.put(
                entity_id,
                "Entity",
                {
                    "name": f"SYNTHETIC {entity_id}",
                    "legal_form": "synthetic",
                    "role": "participant",
                    "residence": "IT",
                    "accounting_framework": "unreviewed",
                    "source_roots": [str(source)],
                },
                scope=[entity_id],
                dependencies=[],
                expected_version=0,
            )
        )
    store.put(
        "ownership",
        "OwnershipEdge",
        {
            "holder": "alpha",
            "company": "beta",
            "ratio": "1/1",
            "rights": "Synthetic ordinary rights, not a legal branch decision",
            "as_of": "2026-09-29",
        },
        scope=["alpha", "beta"],
        dependencies=[reference(r) for r in entities],
        expected_version=0,
    )
    evidence = store.import_evidence(
        "liability_evidence",
        "beta",
        source / "liability.txt",
        locator="line 1",
        description="Synthetic liability evidence",
    )
    fact_data = {
        "description": "Synthetic potential liability",
        "fact_status": "known",
        "value_kind": "decimal",
        "value": "100.00",
        "unit": "EUR",
        "as_of": "2026-09-29",
    }
    fact = store.put(
        "liability",
        "Fact",
        fact_data,
        scope=["beta"],
        dependencies=[reference(evidence)],
        expected_version=0,
    )
    unknown = store.put(
        "consent",
        "Fact",
        {
            "description": "Whether the synthetic lender consented",
            "fact_status": "unknown",
            "value_kind": "boolean",
            "value": None,
            "unit": "boolean",
            "as_of": "2026-09-29",
        },
        scope=["alpha"],
        dependencies=[],
        expected_version=0,
    )
    snapshot = store.import_evidence(
        "source_snapshot",
        "alpha",
        source / "source.txt",
        locator="whole document",
        description="Synthetic source snapshot",
    )
    source_record = store.put(
        "source",
        "SourceVersion",
        {
            "title": "Synthetic source",
            "url": "https://example.invalid/synthetic-rule",
            "checked_on": "2026-09-29",
            "access_status": "retrieved",
            "error": None,
            "source_version": "synthetic-v1",
        },
        scope=["alpha"],
        dependencies=[reference(snapshot)],
        expected_version=0,
    )
    rule_data = {
        "statement": "Synthetic rule for testing review mechanics only.",
        "citation": "SYNTHETIC section 1",
        "review_status": "candidate",
        "published_on": "2026-01-01",
        "effective_from": "2026-01-01",
        "effective_to": None,
        "applicable_from": "2026-01-01",
        "applicable_to": None,
        "transitional_notes": "No legal meaning",
        "scope": "Synthetic test only",
        "preconditions": ["Synthetic input"],
        "exceptions": [],
        "test_refs": ["P0-DEMO"],
    }
    rule = store.put(
        "rule",
        "RuleVersion",
        rule_data,
        scope=["alpha"],
        dependencies=[reference(source_record)],
        expected_version=0,
    )
    checks = {
        "candidate_not_approved": store.status("rule")["review_state"] == "unapproved"
    }
    drafts = store.root / "drafts"
    drafts.mkdir()
    (drafts / "review.md").write_text(
        "Synthetic draft; liability EUR 100.00. No calculation or legal opinion.\n",
        encoding="utf-8",
    )
    artifact = store.artifact(
        "valuation_note",
        drafts / "review.md",
        scope=["beta"],
        dependencies=[reference(fact)],
        recipient="Synthetic reviewer",
    )
    store.approve(
        "approval_before",
        reference(artifact),
        professional_role="Synthetic reviewer",
        scope_text="Fixture content only",
        confirmation="Synthetic explicit approval for testing",
    )
    store.artifact(
        "blocked_note",
        drafts / "review.md",
        scope=["alpha"],
        dependencies=[reference(unknown)],
        recipient="Synthetic reviewer",
    )
    store.artifact(
        "rule_note",
        drafts / "review.md",
        scope=["alpha"],
        dependencies=[reference(rule)],
        recipient="Synthetic reviewer",
    )
    try:
        store.approve(
            "must_not_exist",
            reference(store.read("blocked_note")),
            professional_role="Synthetic reviewer",
            scope_text="Fixture",
            confirmation="Synthetic approval attempt",
        )
    except CaseError:
        checks["unknown_blocks_dependent_approval"] = True
    else:
        checks["unknown_blocks_dependent_approval"] = False
    checks["unapproved_rule_blocks_dependents"] = (
        "rule_unapproved:rule" in store.status("rule_note")["issues"]
    )
    before = export_report(store, destination / "before")
    store.put(
        "liability",
        "Fact",
        {**fact_data, "value": "150.00"},
        scope=["beta"],
        dependencies=[reference(evidence)],
        expected_version=1,
    )
    store.put(
        "source",
        "SourceVersion",
        {
            **source_record["data"],
            "access_status": "failed",
            "error": "Synthetic HTTP 503",
            "source_version": "attempt-2",
        },
        scope=["alpha"],
        dependencies=[],
        expected_version=1,
    )
    store.put(
        "mlbo",
        "BranchDecision",
        {
            "branch": "MLBO",
            "rationale": "Synthetic user request; classification is not inferred by the helper",
            "conditions": "Dedicated legal and numerical implementation required",
            "support_status": "unsupported",
        },
        scope=["alpha", "beta"],
        dependencies=[],
        expected_version=0,
    )
    checks.update(
        {
            "dependent_draft_reopened": store.status("valuation_note")["review_state"]
            == "needs_review",
            "approval_history_preserved": store.read("approval_before")["data"][
                "target"
            ]
            == reference(artifact),
            "old_fact_preserved": store.read("liability", 1)["data"]["value"]
            == "100.00",
            "independent_ownership_unchanged": store.status("ownership")["issues"]
            == [],
            "failed_source_recorded": store.read("source")["data"]["access_status"]
            == "failed",
            "old_source_preserved": store.read("source", 1)["data"]["access_status"]
            == "retrieved",
            "unsupported_branch_visible": "unsupported_branch:mlbo"
            in store.status("mlbo")["issues"],
        }
    )
    store.grant("alpha_reader", role="reader", entities=["alpha"])
    restricted = CaseStore(store.root, "alpha_reader")
    try:
        restricted.document_bytes("liability_evidence")
    except CaseError:
        checks["company_access_denied"] = True
    else:
        checks["company_access_denied"] = False
    checks["scoped_report_hides_other_company"] = "liability_evidence" not in {
        item["record"]["id"] for item in restricted.report()["records"]
    }
    after = export_report(store, destination / "after")
    result = {
        "synthetic": True,
        "checks": checks,
        "passed": all(checks.values()),
        "failed": [key for key, passed in checks.items() if not passed],
        "not_run": [
            "legal merger branches",
            "contributor numerical formulas",
            "live Studio Archive adapter",
            "professional client acceptance",
            "filing and signatures",
        ],
        "before": before,
        "after": after,
    }
    (destination / "demo-results.json").write_text(
        json.dumps(result, indent=2) + "\n", encoding="utf-8"
    )
    return result
