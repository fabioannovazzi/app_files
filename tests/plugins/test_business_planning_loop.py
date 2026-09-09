"""Planning decisions persist across real compiler runs; no semantic scoring."""

from __future__ import annotations

import hashlib
import json
import shutil
import subprocess
import sys
from copy import deepcopy
from pathlib import Path

import pytest

from tests.plugins.test_business_planning_shared import (
    FIXTURE,
    SCRIPT_ROOT,
    PlanningError,
    _clara_workspace,
    bind_plugin_imports,
    build_plan,
    case_data,
    compile_html,
    write_package,
)


def prepared_case() -> dict:
    """A small declared synthetic launch with one consistent scenario."""
    case = case_data()
    case["observations"] = []
    case["resolutions"] = []
    case["assessment"]["charts"] = []
    return case


def parent_case(tmp_path: Path) -> tuple[dict, dict]:
    shutil.copytree(FIXTURE / "sources", tmp_path / "sources")
    case = prepared_case()
    parent = build_plan(case, source_root=tmp_path)
    write_package(parent, source_root=tmp_path, output=tmp_path / "initial")
    return case, parent


def next_case(
    case: dict, parent: dict, root: Path, output_name: str, cycle_id: str
) -> dict:
    """Register the exact archived parent; simulate a new actual synthetic review."""
    case = deepcopy(case)
    old_ids = {s["id"] for s in case["sources"] if s["role"] == "prior_plan"}
    case["sources"] = [s for s in case["sources"] if s["id"] not in old_ids]
    case["evidence"] = [
        e for e in case["evidence"] if not set(e["source_ids"]) & old_ids
    ]
    path = root / output_name / "business_plan.json"
    source = deepcopy(case["sources"][0])
    source.update(
        id="parent",
        path=str(path.relative_to(root)),
        role="prior_plan",
        sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
        version=parent["case"]["cycle"]["id"],
    )
    case["sources"].append(source)
    evidence = deepcopy((case["evidence"] or case["assumptions"])[0])
    evidence.update(
        id="parent-record",
        source_ids=["parent"],
        description="Prior local planning snapshot, not new market evidence.",
    )
    case["evidence"].append(evidence)
    case["cycle"].update(
        id=cycle_id,
        parent_source_id="parent",
        question="Does the revised evidence change the launch decision?",
        reassessed_ids=[n["id"] for n in case["narrative"]],
    )
    case["review"] = {**case["review"], "reviewed_at": "2026-09-09T14:00:00+02:00"}
    return case


def financing_case(instrument: str = "bank_debt") -> dict:
    from planning_financing import FINANCING_SECTIONS

    case = prepared_case()
    existing = case["narrative"][0]
    section_ids = {}
    for section in FINANCING_SECTIONS[instrument]:
        identifier = "funding-" + section
        case["narrative"].append(
            {
                **deepcopy(existing),
                "id": identifier,
                "text": "Synthetic assessment for " + section.replace("_", " ") + ".",
                "claims": {},
            }
        )
        section_ids[section] = [identifier]
    case["financing"] = {
        "purpose": "financing",
        "assessments": [
            {
                "id": "launch-funding",
                "instrument": instrument,
                "provider": "Synthetic financier",
                "request_ids": case["assessment"]["sections"]["cash"],
                "rationale_ids": case["assessment"]["recommendation"],
                "conclusion": "revise_request",
                "sections": section_ids,
                "scenario_ids": ["base", "downside"],
                "coverage_end_period": "2027-03",
            }
        ],
    }
    return case


def test_revision_preserves_parent_and_records_changed_assumption(
    tmp_path: Path,
) -> None:
    case, parent = parent_case(tmp_path)
    original = (tmp_path / "initial/business_plan.json").read_bytes()
    revised = next_case(case, parent, tmp_path, "initial", "price-test")
    revised["assumptions"][0][
        "rationale"
    ] = "New customer interviews change the pricing hypothesis."

    plan = build_plan(revised, source_root=tmp_path)
    write_package(plan, source_root=tmp_path, output=tmp_path / "price-test")

    assert plan["status"] == "ready_for_professional_review"
    assert plan["planning_cycle"]["history"][0]["id"] == "initial"
    assert "assumptions" in {c["field"] for c in plan["planning_cycle"]["changes"]}
    assert (tmp_path / "initial/business_plan.json").read_bytes() == original
    assert (
        "Next test or action"
        in (tmp_path / "price-test/business_plan_review.html").read_text()
    )


def test_changed_evidence_withholds_unreconsidered_conclusions(tmp_path: Path) -> None:
    case, parent = parent_case(tmp_path)
    revised = next_case(case, parent, tmp_path, "initial", "competitor")
    revised["evidence"][0]["description"] = "A competitor has launched an alternative."
    revised["cycle"]["reassessed_ids"] = []

    plan = build_plan(revised, source_root=tmp_path)

    assert plan["status"] == "partial"
    assert plan["accepted_narrative"] == []
    assert "Changed planning basis requires reconsideration" in " ".join(
        plan["unresolved_matters"]
    )
    visible = compile_html(plan, source_root=tmp_path).split(
        '<script type="application/json"'
    )[0]
    assert "Redesign the launch before committing further funds" not in visible


def test_reconsideration_does_not_reuse_old_professional_approval(
    tmp_path: Path,
) -> None:
    case, parent = parent_case(tmp_path)
    revised = next_case(case, parent, tmp_path, "initial", "updated")
    revised["review"] = case["review"]

    plan = build_plan(revised, source_root=tmp_path)

    assert plan["status"] == "partial"
    assert plan["accepted_narrative"][0]["provisional"] is True
    assert "renewed professional review" in " ".join(plan["unresolved_matters"])


@pytest.mark.parametrize(
    "problem",
    ["foreign", "hash", "duplicate_id", "missing_parent", "unregistered_parent"],
)
def test_invalid_parent_cannot_create_revision(tmp_path: Path, problem: str) -> None:
    case, parent = parent_case(tmp_path)
    revised = next_case(case, parent, tmp_path, "initial", "updated")
    if problem == "foreign":
        revised["case_id"] = "another-client"
    elif problem == "hash":
        source = revised["sources"][-1]
        path = tmp_path / source["path"]
        corrupt = json.loads(path.read_text())
        corrupt["case"]["planning_objective"] = "Tampered"
        path.write_text(json.dumps(corrupt))
        source["sha256"] = hashlib.sha256(path.read_bytes()).hexdigest()
    elif problem == "duplicate_id":
        revised["cycle"]["id"] = "initial"
    elif problem == "missing_parent":
        revised["cycle"]["parent_source_id"] = "missing"
    else:
        revised["cycle"]["parent_source_id"] = None

    with pytest.raises(PlanningError):
        build_plan(revised, source_root=tmp_path)


def test_parent_cannot_launder_internal_sources_to_bank(tmp_path: Path) -> None:
    case, parent = parent_case(tmp_path)
    revised = next_case(case, parent, tmp_path, "initial", "bank")
    revised["audience"] = "bank"
    for source in revised["sources"]:
        source["intended_audience"] = ["bank"]
        source["confidentiality"] = {
            "classification": "public",
            "allowed_audiences": ["bank"],
        }

    with pytest.raises(PlanningError, match="Audience restriction"):
        build_plan(revised, source_root=tmp_path)


@pytest.mark.parametrize("instrument", ["bank_debt", "venture_equity"])
def test_financing_assessment_uses_same_model_in_both_products(instrument: str) -> None:
    case = financing_case(instrument)

    vera = build_plan(case, owner="Vera", source_root=FIXTURE)
    clara = build_plan(case, owner="Clara", source_root=FIXTURE)

    assert vera == clara
    assert vera["status"] == "ready_for_professional_review"
    assert vera["financing_assessments"][0]["coverage_complete"] is True
    assert (
        "base/2027-03/ending_cash"
        in vera["financing_assessments"][0]["calculation_ids"]
    )
    assert "Financing assessment" in compile_html(vera, source_root=FIXTURE)


@pytest.mark.parametrize(
    "problem", ["horizon", "repayment", "provider", "section", "scenario"]
)
def test_missing_financing_support_stays_partial(problem: str) -> None:
    case = financing_case()
    request = case["financing"]["assessments"][0]
    request["conclusion"] = "prepare_request"
    if problem == "horizon":
        request["coverage_end_period"] = "2030-01"
    elif problem == "repayment":
        case["financial"]["scenarios"][0]["schedule"][0]["debt_repayments"] = None
    elif problem == "provider":
        request["provider"] = None
    elif problem == "section":
        request["sections"]["downside"] = []
    else:
        request["scenario_ids"] = []

    plan = build_plan(case, source_root=FIXTURE)

    assert plan["status"] == "partial"
    assert "Financing conclusion pending evidence and review" in compile_html(
        plan, source_root=FIXTURE
    )


def test_positive_debt_coverage_does_not_override_model_unsuitability() -> None:
    case = financing_case()
    case["financing"]["assessments"][0]["conclusion"] = "not_suitable"

    plan = build_plan(case, source_root=FIXTURE)

    assert plan["case"]["financing"]["assessments"][0]["conclusion"] == "not_suitable"
    assert "Requested financing is not suitable" in compile_html(
        plan, source_root=FIXTURE
    )


def test_equity_assessment_does_not_require_debt_repayment_ratio() -> None:
    case = financing_case("venture_equity")

    plan = build_plan(case, source_root=FIXTURE)

    assert not any(
        i.endswith("/dscr") for i in plan["financing_assessments"][0]["calculation_ids"]
    )


@pytest.mark.parametrize("field", ["cycle", "financing"])
def test_omitted_decision_context_cannot_finalize(field: str) -> None:
    case = prepared_case()
    case.pop(field)

    plan = build_plan(case, source_root=FIXTURE)

    assert plan["status"] == "partial"


def test_clara_registered_cli_preserves_three_successive_cycles(tmp_path: Path) -> None:
    case = prepared_case()
    workspace, case_path, output = _clara_workspace(tmp_path, case)
    shutil.copytree(FIXTURE / "sources", workspace / "sources")
    parent = None
    for cycle_id in ("initial", "price", "competitor"):
        if parent:
            case = next_case(
                case, parent, workspace, "business-plan/" + previous_id, cycle_id
            )
            case["review"]["reviewed_at"] = (
                "2026-09-09T15:00:00+02:00"
                if cycle_id == "competitor"
                else "2026-09-09T14:00:00+02:00"
            )
        case_path.write_text(json.dumps(case))
        result = subprocess.run(
            [
                sys.executable,
                str(SCRIPT_ROOT / "run_strategic_plan.py"),
                "--case",
                str(case_path),
                "--case-workspace",
                str(workspace),
                "--source-root",
                str(workspace),
                "--output-dir",
                str(output / cycle_id),
            ],
            capture_output=True,
            text=True,
            check=False,
        )
        assert result.returncode == 0, result.stderr
        parent = json.loads((output / cycle_id / "business_plan.json").read_text())
        previous_id = cycle_id

    assert [row["id"] for row in parent["planning_cycle"]["history"]] == [
        "initial",
        "price",
    ]
    assert (output / "initial/business_plan_review.html").is_file()
    assert (output / "price/business_plan_review.html").is_file()
    assert (output / "competitor/business_plan_review.html").is_file()


def pricing_case(stage: str) -> dict:
    """Fixed synthetic business decisions with independently specified cash outcomes."""
    case = financing_case("bank_debt" if stage != "equity" else "venture_equity")
    units, price, revenue, cost, profit = {
        "initial": ("100", "10", "1000", "600", "-100"),
        "price": ("100", "12", "1200", "600", "100"),
        "competitor": ("80", "12", "960", "480", "-20"),
        "equity": ("80", "12", "960", "480", "-20"),
    }[stage]
    source_path = FIXTURE / "sources/pricing-evaluation.txt"
    source = deepcopy(case["sources"][0])
    source.update(
        id="pricing-evaluation",
        path="sources/pricing-evaluation.txt",
        role="model_hypothesis",
        version="synthetic-iteration-evaluation",
        sha256=hashlib.sha256(source_path.read_bytes()).hexdigest(),
    )
    case["sources"] = [source]
    case["evidence"] = []
    case["decisions"] = []
    case["assumptions"][0]["source_ids"] = ["pricing-evaluation"]
    case["cycle"]["trigger_ids"] = ["cash-timing"]
    case["financial"]["opening_refs"] = {
        k: ["cash-timing"] for k in case["financial"]["opening_refs"]
    }
    case["entity_name"] = "Synthetic refill subscription"
    case["company_stage"] = "Synthetic startup before commercial launch"
    case["limitations"] = [
        "Synthetic developer evaluation; no real customer research, lender offer or investor interest is claimed.",
        "The simplified operating and cash assumptions cover only the stated pilot horizon; a live plan needs full business evidence and actual financing terms.",
    ]
    case["planning_objective"] = (
        "Test pricing and competitor response before choosing financing."
    )
    for field in case["financial"]["opening_balance"]:
        case["financial"]["opening_balance"][field] = (
            "50" if field in {"cash", "equity"} else "0"
        )
    case["financial"]["scenarios"] = [case["financial"]["scenarios"][0]]
    for row in case["financial"]["scenarios"][0]["schedule"]:
        row["input_refs"] = {k: ["cash-timing"] for k in row["input_refs"]}
        row.update(
            revenue=revenue,
            cogs=cost,
            variable_cogs=cost,
            equity_contributions="0",
            debt_draws="200" if row["period"] == "2027-01" else "0",
            debt_repayments="0" if row["period"] == "2027-01" else "100",
        )
        if stage == "equity":
            row.update(
                debt_draws="0",
                debt_repayments="0",
                interest_expense="0",
                equity_contributions="200" if row["period"] == "2027-01" else "0",
            )
    case["commercial"] = [
        {
            "scenario": "base",
            "period": p,
            "units": units,
            "net_price": price,
            "variable_cost_per_unit": "6",
            "fixed_cost": "500",
            "basis_ids": ["cash-timing"],
            "cost_scope": "Synthetic direct fulfilment and fixed operating costs; interest is in the cash model.",
        }
        for p in case["periods"]
    ]
    case["assumptions"][0]["description"] = {
        "initial": "Initial subscription price and demand are untested hypotheses.",
        "price": "Synthetic pilot orders support the proposed price for the pilot segment; wider adoption remains uncertain.",
        "competitor": "A hypothetical rival offer could reduce retained subscriptions; the demand response is a hypothesis to test.",
        "equity": "Equity replaces short-term borrowing to fund a pilot; repeat demand and a venture-scale market remain unproven.",
    }[stage]
    case["assumptions"][0]["rationale"] = "Declared synthetic round: " + stage
    # Remove unused historical chart prose instead of carrying old numerical claims.
    case["narrative"] = [n for n in case["narrative"] if not n["id"].endswith("-chart")]
    for entry in case["narrative"]:
        entry["basis_ids"] = ["cash-timing"]
        if entry["id"] == "profit-risk":
            entry["text"] = (
                "Monthly operating result under the current commercial assumptions: {{ebitda}}."
            )
            entry["claims"]["ebitda"]["value"] = profit
        elif entry["id"] == "recommendation":
            entry["text"] = {
                "initial": "Test paid demand before launch: the initial price does not cover operating costs.",
                "price": "Continue a bounded price pilot: its conditional operating margin improves, but acceptance beyond the pilot segment is unproven.",
                "competitor": "Revise the launch and loan request: the assumed customer loss restores operating losses and leaves a repayment shortfall.",
                "equity": "Use the pilot to test retention and acquisition before seeking institutional equity; removing repayments does not repair the operating loss.",
            }[stage]
        elif entry["id"] == "business":
            entry["text"] = (
                "A synthetic refill subscription serves recurring household demand; no real customer evidence is claimed by this evaluation."
            )
        elif entry["id"] == "market":
            entry["text"] = case["assumptions"][0]["description"]
        elif entry["id"] == "cash-view":
            entry["text"] = (
                "Compare the cash schedule with the funding arrival and repayment obligations before committing to the launch."
            )
    request = case["financing"]["assessments"][0]
    request["scenario_ids"] = ["base"]
    request["conclusion"] = "not_suitable" if stage == "equity" else "revise_request"
    case["cycle"]["id"] = stage
    case["cycle"]["question"] = {
        "initial": "Can this subscription support the proposed short-term loan?",
        "price": "Can the pilot price support the launch and loan repayments?",
        "competitor": "What if a competing offer reduces retained subscriptions?",
        "equity": "Would equity fund the test, and is this suitable for a VC?",
    }[stage]
    return case


def test_pricing_competition_and_financing_loop_changes_cash_not_just_prose(
    tmp_path: Path,
) -> None:
    shutil.copytree(FIXTURE / "sources", tmp_path / "sources")
    outputs = {}
    previous = None
    for stage in ("initial", "price", "competitor", "equity"):
        case = pricing_case(stage)
        if previous:
            case = next_case(
                case, previous, tmp_path, previous["case"]["cycle"]["id"], stage
            )
            case["cycle"]["question"] = pricing_case(stage)["cycle"]["question"]
        case["review"]["reviewed_at"] = {
            "initial": "2026-09-09T12:00:00+02:00",
            "price": "2026-09-09T13:00:00+02:00",
            "competitor": "2026-09-09T14:00:00+02:00",
            "equity": "2026-09-09T15:00:00+02:00",
        }[stage]
        previous = build_plan(case, source_root=tmp_path)
        write_package(previous, source_root=tmp_path, output=tmp_path / stage)
        outputs[stage] = previous

    assert (
        outputs["initial"]["calculations"]["base/2027-03/ending_cash"]["value"]
        == "-280"
    )
    assert (
        outputs["price"]["calculations"]["base/2027-03/ending_cash"]["value"] == "320"
    )
    assert (
        outputs["competitor"]["calculations"]["base/2027-03/ending_cash"]["value"]
        == "-40"
    )
    assert (
        outputs["equity"]["calculations"]["base/2027-03/ending_cash"]["value"] == "190"
    )
    assert (
        outputs["equity"]["case"]["financing"]["assessments"][0]["conclusion"]
        == "not_suitable"
    )
    assert outputs["equity"]["calculations"]["base/2027-01/ebitda"]["value"] == "-20"
    assert [r["id"] for r in outputs["equity"]["planning_cycle"]["history"]] == [
        "initial",
        "price",
        "competitor",
    ]


def test_italian_cycle_and_financing_labels_are_localized() -> None:
    case = financing_case()
    case["presentation"] = {
        "language": "it",
        "tables": [],
        "actions": [],
        "source_notes": [],
    }

    report = compile_html(build_plan(case, source_root=FIXTURE), source_root=FIXTURE)

    assert "Domanda di questa iterazione" in report
    assert "Valutazione del finanziamento" in report
    assert "Rimborso con la cassa operativa" in report


def test_reused_financing_verdict_is_withheld_with_its_stale_basis(
    tmp_path: Path,
) -> None:
    shutil.copytree(FIXTURE / "sources", tmp_path / "sources")
    case = financing_case()
    parent = build_plan(case, source_root=tmp_path)
    write_package(parent, source_root=tmp_path, output=tmp_path / "initial")
    case = next_case(case, parent, tmp_path, "initial", "rethink")
    case["cycle"]["reassessed_ids"] = []

    report = compile_html(build_plan(case, source_root=tmp_path), source_root=tmp_path)

    visible = report.split('<script type="application/json"')[0]
    assert "Financing conclusion pending evidence and review" in visible
    assert "<h4>Revise the request</h4>" not in visible
    assert "Recommendation pending evidence and review" in visible


def test_clara_in_process_cli_writes_financing_report(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.syspath_prepend(str(SCRIPT_ROOT.parents[1] / "_shared/vendor/modules"))
    from planning_cli import run

    case = financing_case()
    workspace, case_path, output = _clara_workspace(tmp_path, case)
    shutil.copytree(FIXTURE / "sources", workspace / "sources")

    result = run(
        "Clara",
        [
            "--case",
            str(case_path),
            "--case-workspace",
            str(workspace),
            "--source-root",
            str(workspace),
            "--output-dir",
            str(output / "credit-review"),
        ],
    )

    assert result == 0
    assert (
        json.loads((output / "credit-review/financing_assessments.json").read_text())[
            0
        ]["coverage_complete"]
        is True
    )


@pytest.mark.parametrize("outside", [False, True])
def test_clara_cli_rejects_symlink_or_escaped_revision_output(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, outside: bool
) -> None:
    monkeypatch.syspath_prepend(str(SCRIPT_ROOT.parents[1] / "_shared/vendor/modules"))
    from planning_cli import run

    workspace, case_path, output = _clara_workspace(tmp_path, financing_case())
    shutil.copytree(FIXTURE / "sources", workspace / "sources")
    target = tmp_path / "elsewhere"
    target.mkdir()
    if not outside:
        output.mkdir()
        (output / "linked").symlink_to(target, target_is_directory=True)
        target = output / "linked/revision"

    with pytest.raises(SystemExit):
        run(
            "Clara",
            [
                "--case",
                str(case_path),
                "--case-workspace",
                str(workspace),
                "--output-dir",
                str(target),
            ],
        )


@pytest.mark.parametrize("include_parent_receipt", [True, False])
def test_vera_resumed_plan_requires_exact_registered_parent_receipt(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, include_parent_receipt: bool
) -> None:
    from tests.plugins.test_business_planning_shared import _load_customer_ledger

    monkeypatch.syspath_prepend(str(SCRIPT_ROOT.parents[1] / "_shared/vendor/modules"))
    from planning_cli import run

    evidence_root = tmp_path / "evidence"
    evidence_root.mkdir()
    case, parent = parent_case(evidence_root)
    case = next_case(case, parent, evidence_root, "initial", "resumed")
    ledger = _load_customer_ledger()
    client_root = tmp_path / "Customer"
    client_root.mkdir()
    client_id = "client_111111111111111111111111"
    ledger.create_client_manifest(client_root, client_id)
    engagement_id = ledger.create_engagement(client_root, client_id, "Planning")[
        "engagement_id"
    ]
    input_ids = []
    for source in case["sources"]:
        imported = ledger.import_document(
            client_root,
            client_id,
            engagement_id,
            evidence_root / source["path"],
            "source",
        )
        receipt = imported["receipt"]
        source["path"] = f"imports/{receipt['input_id']}/{receipt['stored_name']}"
        if include_parent_receipt or source["role"] != "prior_plan":
            input_ids.append(receipt["input_id"])
    authored = tmp_path / "resumed-case.json"
    authored.write_text(json.dumps(case))
    case_receipt = ledger.import_document(
        client_root, client_id, engagement_id, authored, "source"
    )["receipt"]
    prepared = ledger.prepare_run(
        client_root,
        client_id,
        engagement_id,
        "business-planning",
        "0.3.0",
        input_ids=[case_receipt["input_id"], *input_ids],
    )
    running = ledger.start_run(client_root, engagement_id, prepared["run"]["run_id"])
    case_path = next(
        b["path"]
        for b in running["context"]["input_bindings"]
        if b["binding_id"] == case_receipt["input_id"]
    )
    output = Path(running["output_dir"]) / "plan"
    args = [
        "--case",
        case_path,
        "--source-root",
        running["context"]["input_dir"],
        "--output-dir",
        str(output),
        "--client-engagement",
        running["context_path"],
    ]

    if include_parent_receipt:
        result = run("Vera", args)
        assert result == 0
        compiled = json.loads((output / "business_plan.json").read_text())
        assert (
            compiled["planning_cycle"]["parent_content_sha256"]
            == parent["content_sha256"]
        )
    else:
        with pytest.raises(SystemExit):
            run("Vera", args)
        assert not output.exists()
