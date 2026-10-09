"""Synthetic CH-GE groups through real Archive receipts and maintained audit.

The extract and review are declared fictional test evidence. No model invocation,
human professional acceptance or native source-group authoring is qualified here.
"""

from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from tests.plugins.test_vera_client_workflow_filesystem import _load_customer_ledger
from tests.plugins.test_vera_native_passive_audit import (  # noqa: F401
    audit_workspace,
    bridge,
)

__all__ = []


@pytest.fixture
def geneva_group(audit_workspace, vera_workflow_workspace, request):
    """Seal a fictional preparation group, then select actual upstream artifacts."""
    audit = audit_workspace
    preparation = vera_workflow_workspace(
        "client-file-preparation", engagement_id="fictional-reviewed-source-group"
    )
    group = preparation["output_dir"] / "reviewed-group"
    group.mkdir()
    extraction = audit.fixture._reviewed_geneva_invoice(group)
    original = group / "invoice.txt"
    originals = group / "originals"
    originals.mkdir()
    original.rename(originals / original.name)
    original = originals / original.name
    value = json.loads(extraction.read_text())
    value["invoices"][0]["source_path"] = "originals/invoice.txt"
    # This attribution is intentionally fictional; do not reuse it for real work.
    value["professional_review"]["reviewer_ref"] = "fictional-test-reviewer"
    variant = getattr(request, "param", "ordinary")
    if variant == "traversal":
        value["invoices"][0]["source_path"] = "../invoice.txt"
    content = {k: v for k, v in value.items() if k != "professional_review"}
    value["professional_review"]["content_sha256"] = hashlib.sha256(
        json.dumps(
            content, ensure_ascii=False, sort_keys=True, separators=(",", ":")
        ).encode()
    ).hexdigest()
    if variant == "unreviewed":
        value.pop("professional_review")
    elif variant == "review_tamper":
        value["professional_review"]["content_sha256"] = "0" * 64
    extraction.write_text(json.dumps(value))
    rows = audit.fixture._ledger_rows(
        supplier_vat="CHE123456789",
        gross="108.10",
        taxable="100.00",
        vat="8.10",
        payable="-108.10",
    )
    for row in rows:
        row["currency"] = "CHF"
    audit.fixture._write_ledger(preparation["output_dir"] / "ledger.csv", rows)
    audit.fixture._write_mapping(preparation["output_dir"] / "mapping.json")
    before = {p.name: p.read_bytes() for p in (extraction, original)}
    work = vera_workflow_workspace(
        "passive-invoice-audit",
        engagement_id="fictional-reviewed-source-group",
        upstream_workspace=preparation,
    )
    bindings = {Path(r["path"]).name: r for r in work["context"]["input_bindings"]}
    recipe = copy.deepcopy(audit.recipe)
    recipe["inputs"] = {
        "invoices": [bindings["reviewed.json"]["binding_id"]],
        "ledger": bindings["ledger.csv"]["binding_id"],
        "ledger_mapping": bindings["mapping.json"]["binding_id"],
    }
    return SimpleNamespace(
        audit=audit,
        preparation=preparation,
        original=original,
        extraction=extraction,
        before=before,
        work=work,
        bindings=bindings,
        recipe=recipe,
    )


def plan(group, context=None):
    """Call the same source boundary used by the isolated native bridge."""
    return group.audit.native.build_plan(
        group.audit.producer,
        context or group.work["context"],
        group.recipe,
        group.audit.workers,
    )


def test_native_reviewed_geneva_group_reuses_exact_archive_sources_and_packet_lineage(
    geneva_group,
):
    group = geneva_group

    summary = group.audit.native.run_job(
        group.audit.producer, plan(group), group.audit.fixture.FixtureRunner({})
    )

    output = group.work["output_dir"]
    population = json.loads((output / "full_population.jsonl").read_text())
    assert summary["matched"] == 1
    assert population["invoice"]["source_format"] == "reviewed_document"
    assert population["invoice"]["source_identifier"] == "originals/invoice.txt"
    assert (
        population["invoice"]["source_sha256"]
        == hashlib.sha256(group.before["invoice.txt"]).hexdigest()
    )
    assert population["invoice"]["currency"] == "CHF"
    assert group.extraction.read_bytes() == group.before["reviewed.json"]
    assert group.original.read_bytes() == group.before["invoice.txt"]
    assert group.bindings["invoice.txt"]["kind"] == "upstream_artifact"
    assert (
        group.bindings["invoice.txt"]["upstream_run_id"] == group.preparation["run_id"]
    )
    assert Path(group.bindings["invoice.txt"]["path"]).parent == (
        Path(group.bindings["reviewed.json"]["path"]).parent / "originals"
    )
    inspected = group.audit.native.inspect_job(
        group.audit.producer, plan(group), {"view": "population"}
    )
    assert inspected["professional_approval"] is False
    assert (
        json.loads(Path(group.work["context"]["run_manifest_path"]).read_text())[
            "status"
        ]
        == "running"
    )


def test_native_reviewed_geneva_group_rejects_original_omitted_from_actual_run_receipts(
    geneva_group,
):
    group = geneva_group
    ledger = _load_customer_ledger()
    work = group.work
    references = [
        {
            "run_id": binding["upstream_run_id"],
            "artifact_id": binding["upstream_artifact_id"],
            "role": "source",
        }
        for name, binding in group.bindings.items()
        if name != "invoice.txt"
    ]
    prepared = ledger.prepare_run(
        work["client_root"],
        work["client_id"],
        work["engagement_id"],
        "passive-invoice-audit",
        "test-version",
        upstream_artifacts=references,
        idempotency_key="fictional-omitted-original",
    )
    running = ledger.start_run(
        work["client_root"], work["engagement_id"], prepared["run"]["run_id"]
    )

    with pytest.raises(PermissionError, match="document is not registered"):
        plan(group, running["context"])

    assert not list(Path(running["output_dir"]).iterdir())


def test_isolated_native_plan_accepts_reviewed_geneva_upstream_group_without_worker(
    geneva_group,
):
    group = geneva_group

    result = bridge(group, operation="plan")

    assert result["population"] == 1
    assert result["match_counts"]["matched"] == 1
    assert result["ledger_orphan_count"] == 0
    assert result["professional_approval"] is False
    assert not list(group.work["output_dir"].iterdir())


@pytest.mark.parametrize("geneva_group", ["unreviewed", "review_tamper"], indirect=True)
def test_native_reviewed_geneva_group_rejects_absent_or_changed_extraction_review(
    geneva_group,
):
    group = geneva_group

    with pytest.raises(ValueError, match="decision bound to its exact content"):
        group.audit.native.run_job(
            group.audit.producer, plan(group), group.audit.fixture.FixtureRunner({})
        )

    assert not (group.work["output_dir"] / "audit.sqlite3").exists()
    assert group.extraction.read_bytes() == group.before["reviewed.json"]


@pytest.mark.parametrize("geneva_group", ["traversal"], indirect=True)
def test_native_reviewed_geneva_group_rejects_locator_outside_its_group(geneva_group):
    group = geneva_group

    with pytest.raises(PermissionError, match="leaves its population"):
        plan(group)

    assert not list(group.work["output_dir"].iterdir())


def test_archive_reviewed_geneva_group_rejects_changed_sealed_original_before_new_run(
    geneva_group,
):
    group = geneva_group
    ledger = _load_customer_ledger()
    work = group.work
    group.original.write_text("Changed fictional original after Archive seal")
    binding = group.bindings["invoice.txt"]

    with pytest.raises(ledger.LedgerError):
        ledger.prepare_run(
            work["client_root"],
            work["client_id"],
            work["engagement_id"],
            "passive-invoice-audit",
            "test-version",
            upstream_artifacts=[
                {
                    "run_id": binding["upstream_run_id"],
                    "artifact_id": binding["upstream_artifact_id"],
                    "role": "source",
                }
            ],
            idempotency_key="fictional-changed-original",
        )

    assert group.extraction.read_bytes() == group.before["reviewed.json"]
