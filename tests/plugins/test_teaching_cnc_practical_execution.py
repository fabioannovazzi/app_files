"""Execute the practical CNC kit; professional prose remains explicit test fixtures.

No network, hosted approval, learner participation or legal currency is simulated.
"""

from __future__ import annotations

import csv
import hashlib
import json
import subprocess
import sys
from collections.abc import Callable, Sequence
from pathlib import Path
from typing import Any

import pytest

from tests.plugins._teaching_release import prepared_kit, record_native_check
from tests.plugins.test_cnc_journeys import save
from tests.plugins.test_composizione_negoziata import (
    ROOT,
    SCRIPT,
    cnc,
    ledger,
    node,
    request,
)
from tests.plugins.test_teaching_kit_execution import (
    _bound_case,
    _complete_teaching_case,
    _read,
    _run,
    _write,
)

__all__ = [
    "test_practical_cnc_kit_executes_role_specific_negative_handoff",
    "test_practical_cnc_registration_keeps_one_workflow_and_selectable_exercises",
]


def _financial(
    root: Path, parent: dict[str, Any], balance_id: str, monkeypatch: pytest.MonkeyPatch
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Execute the existing financial kernel on this case's real imported CSV."""
    monkeypatch.syspath_prepend(str(ROOT / "plugins/_shared/vendor/modules"))
    from vera_financial_analysis import (
        build_data_package_manifest,
        build_dataset_contract,
        build_fdd_case,
    )

    context = parent["context"]
    prepared = ledger.prepare_run(
        root,
        context["client_id"],
        context["engagement_id"],
        "financial-analysis",
        context["workflow_version"],
        input_ids=[balance_id],
        new_run=True,
    )
    run = ledger.start_run(root, context["engagement_id"], prepared["run"]["run_id"])
    source = Path(run["context"]["input_bindings"][0]["path"])
    original = source.read_bytes()
    with source.open(encoding="utf-8", newline="") as stream:
        rows = list(csv.DictReader(stream))
    assert len(rows) == 4
    dates = {row["as_of_date"] for row in rows}
    assert len(dates) == 1
    as_of = dates.pop()
    output = Path(run["output_dir"])
    prepared_source = output / source.name
    prepared_source.write_bytes(original)
    assert prepared_source.read_bytes() == original
    package = build_data_package_manifest(
        package_id="package.teaching.v1",
        snapshot_id="snapshot.teaching.v1",
        reporting_perimeter={
            "entity_refs": ["entity.arco_cnc"],
            "period_start": as_of,
            "period_end": as_of,
            "currency_refs": ["EUR"],
        },
        sensitivity="confidential",
        sources=[
            {
                "source_id": "source.balances",
                "artifact_ref": "artifact.balances",
                "file_name": source.name,
                "locator": source.name,
                "byte_count": len(original),
                "sha256": hashlib.sha256(original).hexdigest(),
                "snapshot_id": "snapshot.teaching.v1",
                "dataset_contract_ref": "dataset.balances.v1",
            }
        ],
    )
    dataset = build_dataset_contract(
        dataset_contract_id="dataset.balances.v1",
        dataset_id="balances",
        version="v1",
        grain="one identified balance at the stated date",
        keys=["row_id"],
        fields=[
            {
                "name": "row_id",
                "concept_id": "row.identity",
                "data_type": "text",
                "nullable": False,
                "unit": "identifier",
                "currency": None,
                "aggregation": "none",
                "period_role": "none",
            },
            {
                "name": "amount",
                "concept_id": "financial.amount",
                "data_type": "decimal",
                "nullable": False,
                "unit": "EUR_units",
                "currency": "EUR",
                "aggregation": "sum",
                "period_role": "period_end",
            },
        ],
        period={
            "calendar": "gregorian",
            "grain": "month",
            "start": as_of,
            "end": as_of,
        },
        source_artifact_refs=["artifact.balances"],
    )
    # Explicit interpretation of the supplied fictional request in this test.
    # Native learners review their choices; this receipt is never in a kit.
    classification = {
        "loan": "debt",
        "cash": "cash",
        "deposit": "excluded",
        "payables": "excluded",
    }
    review = {
        "status": "reviewed",
        "reviewed_on": "2026-09-14",
        "reviewer_ref": "reviewer.teaching_fixture",
        "basis": "Test-only interpretation of the authored loan and available-cash definition.",
    }
    case = build_fdd_case(
        case_id="case.teaching",
        scope_id="scope.arco",
        entity_refs=["entity.arco_cnc"],
        pack_id="net_debt",
        currency="EUR",
        unit="EUR_units",
        reporting_period={"start": as_of, "end": as_of},
        package=package,
        datasets=[dataset],
        request_id="request.net_debt.v1",
        review=review,
        reviewed_decisions=[{"decision_ref": "decision.definition", **review}],
        inputs={
            "as_of_date": as_of,
            "items": [
                {
                    "item_id": "item." + row["row_id"],
                    "economic_effect_id": "effect." + row["row_id"],
                    "description": row["description"],
                    "as_of_date": as_of,
                    "classification": classification[row["row_id"]],
                    "amount": row["amount"],
                    "included": classification[row["row_id"]] != "excluded",
                    "decision_ref": "decision.definition",
                    "evidence_refs": ["artifact.balances"],
                }
                for row in rows
            ],
        },
    )
    stack = case["contract_stack"]
    bundle = {
        "schema_version": "vera.fdd_execution_bundle.v2",
        "fdd_case": case,
        **{
            key: stack[key]
            for key in ("package", "datasets", "relationships", "crosswalks", "request")
        },
    }
    # Use the current canonical serializer, not a separately invented seal.
    from tests.plugins._financial_analysis_test_loader import (
        load_financial_analysis_scripts,
    )

    modules = load_financial_analysis_scripts(
        ROOT / "plugins/financial-analysis/scripts"
    )
    bundle["content_sha256"] = modules.kernel.canonical_json_sha256(bundle)
    case_path = output / "case.json"
    _write(case_path, bundle)
    prepared = output / "prepared"
    _run(
        "plugins/financial-analysis/scripts/run_pack.py",
        "--pack",
        "net_debt",
        "--case",
        case_path,
        "--output-dir",
        prepared,
        "--client-engagement",
        run["context_path"],
    )
    receipt = _read(prepared / "pack_execution_receipt.json")
    result = _read(prepared / "fdd_result.json")
    assert receipt["status"] == "passed"
    assert receipt["report_ready"] is False
    assert {item["metric_id"]: item["value"] for item in result["metrics"]}[
        "net_debt"
    ] == "70000"
    assert result["source_tie_out"]["status"] == "not_assessed"
    assert (prepared / "financial_analysis_contract_audit.json").is_file()
    assert (prepared / "model_use_manifest.json").is_file()
    assert source.read_bytes() == original
    _complete_teaching_case(
        run, root, artifact_ids={"prepared/fdd_result.json": "financial"}
    )
    return run, result


def _specialist(
    root: Path,
    parent: dict[str, Any],
    workflow: str,
    input_ids: Sequence[str] = (),
    upstream: Sequence[dict[str, Any]] = (),
) -> dict[str, Any]:
    """Start a managed run with only the selected evidence and sealed results."""
    context = parent["context"]
    prepared = ledger.prepare_run(
        root,
        context["client_id"],
        context["engagement_id"],
        workflow,
        context["workflow_version"],
        input_ids=list(input_ids),
        upstream_artifacts=list(upstream),
        new_run=True,
    )
    return ledger.start_run(root, context["engagement_id"], prepared["run"]["run_id"])


def _treasury(
    root: Path, parent: dict[str, Any], folder: Path
) -> tuple[dict[str, Any], dict[str, Any], Path]:
    """Use the kit's exact tables through the current treasury CLI."""
    context = parent["context"]
    imports = [
        ledger.import_document(
            root, context["client_id"], context["engagement_id"], path, "source"
        )["receipt"]
        for path in sorted(folder.glob("*.csv"))
    ]
    manifest = folder.parent / ("manifest-" + folder.name + ".json")
    _write(
        manifest,
        {
            "schema_version": "vera.treasury_manifest.v1",
            "company_id": "officina-arco-cnc-fictional",
            "company_name": "Officina Arco CNC — caso fittizio",
            "currency": "EUR",
            "as_of": "2026-10-31",
            "horizon_end": "2027-01-31",
            "coverage": "Only supplied positions; missing aging, collectability, other flows and evidence of completeness.",
            "tables": {
                Path(row["path"]).stem.split("-", 1)[-1]: {
                    "path": "imports/" + row["input_id"] + "/" + Path(row["path"]).name
                }
                for row in imports
            },
            "invoice_files": [],
            "previous": None,
        },
    )
    manifest_id = ledger.import_document(
        root, context["client_id"], context["engagement_id"], manifest, "source"
    )["receipt"]["input_id"]
    run = _specialist(
        root,
        parent,
        "treasury-forecast",
        [row["input_id"] for row in imports] + [manifest_id],
    )
    bound = next(
        row["path"]
        for row in run["context"]["input_bindings"]
        if row["binding_id"] == manifest_id
    )
    _run(
        "plugins/treasury-forecast/scripts/run_treasury.py",
        "prepare",
        "--client-engagement",
        run["context_path"],
        "--manifest",
        bound,
    )
    from treasury_session import current_record

    _, result = current_record(Path(run["output_dir"]))
    relative = Path("versions") / result["record_sha256"] / "forecast.json"
    _complete_teaching_case(run, root, artifact_ids={relative.as_posix(): "forecast"})
    return run, result, Path(run["output_dir"]) / relative


def _research_gap(
    root: Path, parent: dict[str, Any], brief_id: str, language: str
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Execute existing research inspection honestly without network acquisition."""
    planning = _specialist(root, parent, "prompt-optimizer", [brief_id])
    planning_output = Path(planning["output_dir"])
    question = Path(planning["context"]["input_bindings"][0]["path"])
    _run(
        "plugins/prompt-optimizer/scripts/inspect_question.py",
        question,
        "--client-engagement",
        planning["context_path"],
        "--output-dir",
        planning_output,
        "--language",
        language,
    )
    assert (planning_output / "question_inventory.json").is_file()
    _complete_teaching_case(planning, root)
    run = _specialist(root, parent, "deep-research-validator", [brief_id])
    output = Path(run["output_dir"])
    brief = Path(run["context"]["input_bindings"][0]["path"])
    # This is an availability check, not an invented current-law answer or review.
    _run(
        "plugins/deep-research-validator/scripts/inspect_document.py",
        brief,
        "--output-dir",
        output,
        "--client-engagement",
        run["context_path"],
    )
    _run(
        "plugins/deep-research-validator/scripts/inspect_sources.py",
        output / "document_inventory.json",
        "--output-dir",
        output,
        "--client-engagement",
        run["context_path"],
        "--no-fetch",
    )
    inventory = _read(output / "source_inventory.json")
    assert inventory["url_count"] == 2
    assert all(row["status"] == "listed_not_fetched" for row in inventory["sources"])
    _complete_teaching_case(
        run, root, artifact_ids={"source_inventory.json": "research_gap"}
    )
    return run, inventory


def _calculated(
    run: dict[str, Any],
    identifier: str,
    workflow: str,
    content: str,
    dependencies: tuple[str, ...] = (),
) -> dict[str, Any]:
    """Cite the actual declared specialist result in a synthetic case node."""
    binding = next(
        row
        for row in run["context"]["input_bindings"]
        if row.get("upstream_workflow_id") == workflow
    )
    item = node(identifier, kind="analysis", content=content, dependencies=dependencies)
    item["classification"] = "calculated"
    item["citations"] = [
        {
            "binding_id": binding["binding_id"],
            "locator": (
                "metrics.net_debt"
                if workflow == "financial-analysis"
                else "minimum_daily_cash; events"
            ),
        }
    ]
    return item


@prepared_kit("vera/composizione-negoziata")
@pytest.mark.parametrize("language", ["it", "en", "fr", "de", "es"])
@pytest.mark.parametrize(
    "phase,role,table_phase",
    [("demo", "advisor", "practice"), ("practice", "esperto", "independent")],
)
def test_practical_cnc_kit_executes_role_specific_negative_handoff(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    record_property: Callable[[str, str], None],
    language: str,
    phase: str,
    role: str,
    table_phase: str,
) -> None:
    """Run one role-specific exercise without granting professional authority."""
    monkeypatch.setitem(sys.modules, "client_ledger", ledger)
    monkeypatch.syspath_prepend(str(ROOT / "plugins/treasury-forecast/scripts"))
    run = _bound_case(
        tmp_path, monkeypatch, cnc.WORKFLOW, cnc.WORKFLOW, "demo", language=language
    )
    root = tmp_path / "case"
    sources = run["context"]["input_bindings"]
    source = next(
        row
        for row in sources
        if Path(row["path"]).suffix == ".md"
        and not Path(row["path"]).name.startswith("research-")
    )
    balance = next(row for row in sources if Path(row["path"]).name == "balances.csv")
    brief = next(
        row for row in sources if Path(row["path"]).name.startswith("research-")
    )
    source_ids = [row["binding_id"] for row in sources]
    document = node(
        "document", kind="document", content=Path(source["path"]).read_text()
    )
    document["classification"] = "documented"
    document["citations"] = [
        {
            "binding_id": source["binding_id"],
            "locator": "Fictional initial case; complete document",
        }
    ]
    gap = node(
        "missing_aging",
        kind="gap",
        content="Missing aging and collectability evidence; not zero.",
    )
    gap["classification"] = "missing"
    save(
        run,
        request(
            document,
            node(
                "collection",
                dependencies=("document",),
                content="Unconfirmed receipt on 2026-11-15",
            ),
            gap,
        ),
        role,
    )
    _complete_teaching_case(run, root)
    financial, result = _financial(root, run, balance["binding_id"], monkeypatch)
    treasury, baseline, baseline_path = _treasury(
        root, run, tmp_path / "kit/files/treasury-demo"
    )
    research, availability = _research_gap(root, run, brief["binding_id"], language)
    upstream = [
        {"run_id": item["run"]["run_id"], "artifact_id": artifact, "role": "source"}
        for item, artifact in [
            (financial, "financial"),
            (treasury, "forecast"),
            (research, "research_gap"),
        ]
    ]
    run = _specialist(root, run, cnc.WORKFLOW, source_ids, upstream)
    research_binding = next(
        row
        for row in run["context"]["input_bindings"]
        if row.get("upstream_workflow_id") == "deep-research-validator"
    )
    research_gap = node(
        "law_gap",
        kind="gap",
        content="Current primary law not acquired by this offline execution. Research brief remains open, not a legal answer.",
    )
    research_gap["classification"] = "unverified"
    research_gap["citations"] = [
        {
            "binding_id": research_binding["binding_id"],
            "locator": "sources[].access_status; no-fetch",
        }
    ]
    proposal = node(
        "proposal",
        kind="draft",
        dependencies=("forecast", "net_debt", "missing_aging", "law_gap"),
        content=(
            "Synthetic advisor conditional proposal; verify collection and law before deciding."
            if role == "advisor"
            else "Synthetic expert neutral questions to both parties; no company strategy or verified appointment."
        ),
    )
    first = save(
        run,
        request(
            _calculated(
                run,
                "net_debt",
                "financial-analysis",
                "Net debt EUR 70000; scope excludes deposit and trade payables.",
            ),
            _calculated(
                run,
                "forecast",
                "treasury-forecast",
                "Minimum cash EUR 50000; receipt unconfirmed.",
                ("collection",),
            ),
            research_gap,
            proposal,
            revision=1,
            key="baseline",
        ),
        role,
    )
    assert baseline["minimum_daily_cash"] == "50000.00"
    assert first["payload"]["reviews"] == []
    baseline_bytes = baseline_path.read_bytes()
    original_version = first["payload"]["nodes"]["proposal"]["version"]
    _complete_teaching_case(run, root)
    folder = (
        tmp_path / "kit/files" / ("practice" if role == "advisor" else "independent")
    )
    change_path = next(folder.glob("*.md"))
    context = run["context"]
    receipt = ledger.import_document(
        root, context["client_id"], context["engagement_id"], change_path, "source"
    )["receipt"]
    source_ids.append(receipt["input_id"])
    run = _specialist(root, run, cnc.WORKFLOW, source_ids)
    event = node("change", kind="document", content=change_path.read_text())
    event["classification"] = "documented"
    event["citations"] = [
        {
            "binding_id": receipt["input_id"],
            "locator": "Fictional receipt delay and negotiation refusal",
        }
    ]
    changed = save(
        run,
        request(
            event,
            node(
                "collection",
                dependencies=("document", "change"),
                content="Receipt now "
                + ("2027-01-15" if role == "advisor" else "2027-02-15")
                + "; collectability unverified",
            ),
            revision=2,
            key="delay",
        ),
        role,
    )
    assert changed["payload"]["stale_nodes"] == ["forecast", "proposal"]
    assert changed["payload"]["nodes"]["proposal"]["version"] == original_version
    assert changed["payload"]["reviews"] == []
    _complete_teaching_case(run, root)
    revised, actual, actual_path = _treasury(
        root, run, tmp_path / "kit/files" / ("treasury-" + table_phase)
    )
    assert actual["minimum_daily_cash"] == "-30000.00"
    assert baseline_path.read_bytes() == baseline_bytes
    run = _specialist(
        root,
        run,
        cnc.WORKFLOW,
        source_ids,
        [
            {
                "run_id": revised["run"]["run_id"],
                "artifact_id": "forecast",
                "role": "source",
            }
        ],
    )
    outcome = node(
        "outcome",
        kind="fact",
        dependencies=("change",),
        content="Creditor refusal; no agreement evidenced in selected fictional documents.",
    )
    outcome["classification"] = "documented"
    proposal = node(
        "proposal",
        kind="draft",
        dependencies=("forecast", "net_debt", "law_gap", "outcome"),
        content=(
            "Reconsider the conditional proposal: no committed coverage evidenced."
            if role == "advisor"
            else "Neutral evaluation and questions to the parties; no company advocacy."
        ),
    )
    report = node(
        "final_report",
        kind="draft",
        dependencies=(
            "proposal",
            "forecast",
            "net_debt",
            "outcome",
            "law_gap",
            "missing_aging",
        ),
        content=(
            "Synthetic advisor report to company."
            if role == "advisor"
            else "Synthetic independent expert final report; appointment and independence unverified."
        )
        + " Minimum cash changes from EUR 50000 to EUR -30000; net debt EUR 70000 has a different scope. No agreement evidenced. Aging, collectability and current legal research remain unresolved. No filing receipts supplied; no signature, filing or legal closure asserted. Owners must obtain evidence and verify applicable deadlines. This prose is a test fixture, not professional acceptance.",
    )
    final_request = request(
        _calculated(
            run,
            "forecast",
            "treasury-forecast",
            "Revised minimum cash EUR -30000.",
            ("collection",),
        ),
        outcome,
        proposal,
        report,
        revision=3,
        key="negative-report",
    )
    final_request["closure"] = {
        "outcome": "no_agreement",
        "report_id": "final_report",
        "basis_ids": ["forecast", "net_debt", "outcome"],
        "receipt_ids": [],
        "residual_tasks": [
            {
                "node_id": "missing_aging",
                "owner": (
                    "Company advisor"
                    if role == "advisor"
                    else "Independent expert: request permitted evidence"
                ),
                "due_basis": "To agree; no invented statutory deadline",
            },
            {
                "node_id": "law_gap",
                "owner": "Professional for this role",
                "due_basis": "Check current primary sources before legal decisions",
            },
        ],
    }
    final = save(run, final_request, role)
    assert final["payload"]["role"] == role
    assert final["payload"]["stale_nodes"] == []
    assert final["payload"]["reviews"] == []
    assert final["payload"]["external_action_authorized"] is False
    assert cnc.closure_status(final["payload"]) == "draft_handoff"
    assert final["payload"]["nodes"]["proposal"]["version"] != original_version
    assert final["payload"]["nodes"]["law_gap"]["classification"] == "unverified"
    memo = Path(run["output_dir"]) / "cnc-revision-000004.md"
    assert "EUR -30000" in memo.read_text()
    assert "no_agreement" in memo.read_text()
    _complete_teaching_case(run, root)
    resumed = subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "--client-engagement",
            run["context_path"],
            "--resume",
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    assert resumed.returncode == 0, resumed.stderr
    assert final["content_sha256"] in resumed.stderr
    assert "no_agreement" in resumed.stderr
    artifacts = [
        memo,
        actual_path,
        Path(financial["output_dir"]) / "prepared/fdd_result.json",
        Path(research["output_dir"]) / "source_inventory.json",
        Path(run["output_dir"]) / "workflow-revision-000004.json",
        Path(run["output_dir"]) / "model_data_report.md",
    ]
    assert all(path.is_file() for path in artifacts)
    _write(
        tmp_path / "practical-evidence.json",
        {
            "role": role,
            "language": language,
            "phase": phase,
            "artifacts": [
                {
                    "name": path.name,
                    "path": str(path),
                    "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
                }
                for path in artifacts
            ],
        },
    )
    record_native_check(
        record_property,
        root=ROOT,
        product="vera",
        workflow=cnc.WORKFLOW,
        language=language,
        phase=phase,
    )


def test_practical_cnc_registration_keeps_one_workflow_and_selectable_exercises(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The existing entry exposes coherent inputs without preapproved outputs."""
    monkeypatch.syspath_prepend(str(ROOT / "plugins/_shared/vendor/modules"))
    from courseware.library import CourseLibrary

    index = _read(ROOT / "plugins/vera/assets/courses/index.json")
    assert list(index["courses"]).count("composizione-negoziata") == 1
    library = CourseLibrary(ROOT / "plugins/vera", {cnc.WORKFLOW})
    for language in ("it", "en", "fr", "de", "es"):
        course = library.load(cnc.WORKFLOW, language)
        assert course["execution"]["local_tutorial"] is True
        assert course["execution"]["mode"] == "current_native_workflow"
        own = [row for row in course["files"] if language in row["languages"]]
        assert sum(row["path"].startswith("files/independent/") for row in own) == 1
        assert sum(row["path"].startswith("files/treasury-demo/") for row in own) == 6
        assert (
            sum(row["path"].startswith("files/treasury-practice/") for row in own) == 6
        )
        assert (
            sum(row["path"].startswith("files/treasury-independent/") for row in own)
            == 6
        )
        assert not any(
            "receipt" in Path(row["path"]).name or "result" in Path(row["path"]).name
            for row in own
        )
