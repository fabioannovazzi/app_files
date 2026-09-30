"""Real archive integration and adverse Patent Box acceptance cases."""

from __future__ import annotations

import copy
import importlib.util
import json
import sys
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest

ROOT = Path(__file__).resolve().parents[2]
PLUGIN = ROOT / "plugins/patent-box-review"


def load_module(name: str, path: Path) -> ModuleType:
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def workflow() -> ModuleType:
    return load_module(
        "patent_box_workflow_test", PLUGIN / "scripts/patent_box_workflow.py"
    )


def running_case(
    tmp_path: Path,
    workflow: ModuleType,
    *,
    demo: bool = True,
    mixed: bool = False,
    ledger_text: str | None = None,
    archive_script: Path | None = None,
) -> dict[str, Any]:
    archive = load_module(
        "patent_box_archive_test",
        archive_script or ROOT / "plugins/studio-archive/scripts/archive_core.py",
    )
    archive_root = tmp_path / "studio"
    (archive_root / "Synthetic software company").mkdir(parents=True)
    state = tmp_path / "private-state"
    configured = archive.configure_archive(archive_root, state_dir=state)
    client = archive.set_studio_client_identity(
        configured["scopes"][0]["scope_id"],
        legal_names=["Synthetic software company"],
        state_dir=state,
    )["client"]
    engagement = archive.create_studio_client_engagement(
        client["client_id"], "Patent Box synthetic acceptance", state_dir=state
    )["engagement"]
    evidence = tmp_path / "synthetic.txt"
    evidence.write_text((PLUGIN / "examples/evidence/synthetic.txt").read_text())
    ledger = tmp_path / "ledger.csv"
    ledger.write_text(
        "cost_id,ledger_row_key,period_id,account,category,book_amount,income_max,irap_max\nC1,GL.1,P2025,Synthetic cost,PERSONNEL,100000.00,100000.00,80000.00\n"
    )
    if mixed:
        ledger.write_text(
            ledger.read_text()
            + "C2,GL.2,P2025,Synthetic cost,PERSONNEL,100000.00,100000.00,80000.00\n"
        )
    if ledger_text is not None:
        ledger.write_text(ledger_text)
    input_ids = [
        archive.import_studio_client_document(
            client["client_id"],
            source,
            "source",
            engagement_id=engagement["engagement_id"],
            state_dir=state,
        )["input_id"]
        for source in (evidence, ledger)
    ]
    prepared = archive.prepare_studio_client_workflow(
        engagement["engagement_id"],
        "patent-box-review",
        input_ids=input_ids,
        state_dir=state,
    )
    archive.start_studio_client_workflow(
        client["client_id"],
        engagement["engagement_id"],
        prepared["run"]["run_id"],
        state_dir=state,
    )
    context_path = Path(prepared["client_engagement_path"])
    session = workflow.initialize(context_path, as_of="2026-09-23", demo=demo)
    output = Path(prepared["client_engagement"]["output_dir"])
    return {
        "context": context_path,
        "session": session,
        "output": output,
        "archive": archive,
        "state": state,
        "client": client,
        "engagement": engagement,
        "prepared": prepared,
    }


def model_proposal(case_run: dict[str, Any], workflow: ModuleType) -> dict[str, Any]:
    """Explicit synthetic proposal fixture, never a document interpretation engine."""
    session = case_run["session"]
    evidence = [
        {key: record[key] for key in ("evidence_id", "path", "sha256", "description")}
        for record in session["inputs"]
    ]
    source = next(row for row in evidence if row["description"] == "synthetic.txt")
    ledger = next(row for row in evidence if row["description"] == "ledger.csv")
    imported = workflow.import_ledger(
        case_run["context"], evidence_id=ledger["evidence_id"]
    )
    case = json.loads((PLUGIN / "examples/case.ordinary.json").read_text())
    case.update(
        case_id=session["run_id"],
        demo=session["demo"],
        evidence=evidence,
        costs=imported["costs"],
    )
    rules = json.loads((PLUGIN / "examples/rules.demo.json").read_text())
    rules["demo"] = session["demo"]
    rules["sources"][0].update(
        snapshot_evidence_id=source["evidence_id"], snapshot_sha256=source["sha256"]
    )
    keys = [
        "case/PB.SUBJECT",
        "case/PB.EXCLUSIONS",
        "case/PB.OPTION",
        "case/PB.TRANSITION",
        "case/PB.DUPLICATES",
        "case/PB.EXTRAORDINARY",
        "case/PB.DECLARATION",
        "case/PB.ADVERSARIAL",
        "case/PB.SOURCES",
        "ip:IP.SOFT/PB.IP.SOFTWARE",
        "ip:IP.SOFT/PB.RIGHTS",
        "ip:IP.SOFT/PB.USE",
        "ip:IP.SOFT/PB.ACTIVITY",
        "allocation:A1/PB.COST",
        "allocation:A1/PB.PERSONNEL",
        "allocation:A1/PB.LINKAGE",
        "allocation:A1/PB.ALLOCATION",
        "allocation:A1/PB.INCENTIVES",
        "allocation:A1/PB.RD.CREDIT",
    ]
    controls = [
        {
            "key": key,
            "status": "PASS",
            "conclusion": "Explicit synthetic acceptance decision; no real legal conclusion.",
            "evidence_ids": [source["evidence_id"], ledger["evidence_id"]],
            "source_ids": ["DEMO.SOURCE"],
        }
        for key in keys
    ]
    return {
        "case": case,
        "rules": rules,
        "controls": controls,
        "narratives": [
            {
                "section": "A",
                "text": "Synthetic software and project used only for technical acceptance.",
                "evidence_ids": [source["evidence_id"]],
                "locator": "synthetic.txt, complete fixture",
            },
            {
                "section": "B",
                "text": "Selected ledger row GL.1: 100000.00 EUR book and income base; 80000.00 EUR IRAP base, proposed for synthetic allocation.",
                "evidence_ids": [ledger["evidence_id"]],
                "locator": "CSV row 2, ledger_row_key GL.1",
            },
        ],
    }


def reviewed(
    case_run: dict[str, Any], workflow: ModuleType, proposal: dict[str, Any]
) -> str:
    digest = workflow.propose(case_run["context"], proposal)["proposal_digest"]
    workflow.review(
        case_run["context"],
        digest=digest,
        reviewer="SYNTHETIC_REVIEWER",
        confirmation_ref="automated-acceptance-fixture",
        confirmed=True,
        synthetic=case_run["session"]["demo"],
    )
    return digest


def test_ordinary_case_creates_dossier_from_bound_ledger_and_review(
    tmp_path: Path, workflow: ModuleType
) -> None:
    run = running_case(tmp_path, workflow)
    digest = reviewed(run, workflow, model_proposal(run, workflow))

    output = workflow.calculate_draft(run["context"], digest=digest)

    assert output["result"]["additional_deduction"] == {
        "income": "110000.00",
        "irap": "88000.00",
    }
    assert output["result"]["bases"]["INCLUDED"] == {
        "income": "100000.00",
        "irap": "80000.00",
    }
    assert output["result"]["tax_saving"] is None
    folder = Path(output["output_dir"])
    assert {p.name for p in folder.iterdir()} >= {
        "case_summary.md",
        "missing_documents.md",
        "control_matrix.csv",
        "cost_reconciliation.csv",
        "result.json",
        "workpaper.md",
        "fascicolo_A_B.md",
        "manifest.json",
    }
    assert "GL.1" in (folder / "cost_reconciliation.csv").read_text()
    assert "## Sezione A" in (folder / "fascicolo_A_B.md").read_text()
    assert "## Sezione B" in (folder / "fascicolo_A_B.md").read_text()
    assert "NOT_TESTED" not in (folder / "control_matrix.csv").read_text()


@pytest.mark.parametrize("state", ["BLOCKED", "WARNING", "NOT_TESTED"])
def test_open_child_suspends_despite_prefilled_global_pass(
    tmp_path: Path, workflow: ModuleType, state: str
) -> None:
    run = running_case(tmp_path, workflow)
    proposal = model_proposal(run, workflow)
    next(row for row in proposal["controls"] if row["key"] == "case/PB.EXCLUSIONS")[
        "status"
    ] = state
    digest = reviewed(run, workflow, proposal)

    result = workflow.calculate_draft(run["context"], digest=digest)["result"]

    assert result["bases"]["SUSPENDED"]["income"] == "100000.00"
    assert result["additional_deduction"]["income"] == "0.00"


def test_missing_child_suspends_without_concluding_failure(
    tmp_path: Path, workflow: ModuleType
) -> None:
    run = running_case(tmp_path, workflow)
    proposal = model_proposal(run, workflow)
    proposal["controls"] = [
        row for row in proposal["controls"] if row["key"] != "case/PB.EXCLUSIONS"
    ]
    digest = reviewed(run, workflow, proposal)

    result = workflow.calculate_draft(run["context"], digest=digest)["result"]

    assert result["lines"][0]["status"] == "SUSPENDED"
    assert "SUBJECT:NOT_TESTED" in result["lines"][0]["reasons"]


def test_partial_component_does_not_suspend_other_component(
    tmp_path: Path, workflow: ModuleType
) -> None:
    run = running_case(tmp_path, workflow, mixed=True)
    proposal = model_proposal(run, workflow)
    proposal["case"]["ledger_control_total"] = "200000.00"
    allocation = copy.deepcopy(proposal["case"]["allocations"][0])
    allocation.update(allocation_id="A2", cost_id="C2")
    proposal["case"]["allocations"].append(allocation)
    digest = reviewed(run, workflow, proposal)

    result = workflow.calculate_draft(run["context"], digest=digest)["result"]

    assert result["bases"]["INCLUDED"]["income"] == "100000.00"
    assert result["bases"]["SUSPENDED"]["income"] == "100000.00"
    assert result["additional_deduction"]["income"] == "110000.00"


def test_unknown_evidence_cannot_support_pass(
    tmp_path: Path, workflow: ModuleType
) -> None:
    run = running_case(tmp_path, workflow)
    proposal = model_proposal(run, workflow)
    proposal["controls"][0]["evidence_ids"] = ["OTHER.CLIENT"]

    with pytest.raises(ValueError, match="evidence/source"):
        workflow.propose(run["context"], proposal)


def test_draft_rules_block_calculation(tmp_path: Path, workflow: ModuleType) -> None:
    run = running_case(tmp_path, workflow)
    proposal = model_proposal(run, workflow)
    proposal["rules"]["status"] = "DRAFT"
    digest = reviewed(run, workflow, proposal)

    with pytest.raises(ValueError, match="professional review"):
        workflow.calculate_draft(run["context"], digest=digest)


def test_duplicate_ledger_row_rejected_even_with_new_cost_id(
    tmp_path: Path, workflow: ModuleType
) -> None:
    run = running_case(tmp_path, workflow)
    proposal = model_proposal(run, workflow)
    proposal["case"]["costs"].append({**proposal["case"]["costs"][0], "cost_id": "C2"})

    with pytest.raises(ValueError, match="Duplicate ledger_row_key"):
        workflow.propose(run["context"], proposal)


def test_overallocation_is_not_silently_clipped(
    tmp_path: Path, workflow: ModuleType
) -> None:
    run = running_case(tmp_path, workflow)
    proposal = model_proposal(run, workflow)
    proposal["case"]["allocations"][0]["income_amount"] = "100000.01"
    digest = reviewed(run, workflow, proposal)

    with pytest.raises(ValueError, match="Overallocation"):
        workflow.calculate_draft(run["context"], digest=digest)


def test_changed_selected_input_invalidates_review(
    tmp_path: Path, workflow: ModuleType
) -> None:
    run = running_case(tmp_path, workflow)
    digest = reviewed(run, workflow, model_proposal(run, workflow))
    Path(run["session"]["inputs"][0]["selected_path"]).write_text(
        "Changed after review"
    )

    with pytest.raises(ValueError):
        workflow.calculate_draft(run["context"], digest=digest)


def test_changed_proposal_cannot_reuse_decision(
    tmp_path: Path, workflow: ModuleType
) -> None:
    run = running_case(tmp_path, workflow)
    proposal = model_proposal(run, workflow)
    digest = reviewed(run, workflow, proposal)
    proposal["case"]["allocations"][0]["income_amount"] = "90000.00"
    changed = workflow.propose(run["context"], proposal)["proposal_digest"]

    with pytest.raises(ValueError, match="regular JSON"):
        workflow.calculate_draft(run["context"], digest=changed)
    assert (run["output"] / f"decision_{digest}.json").exists()


def test_blank_reviewer_cannot_confirm(tmp_path: Path, workflow: ModuleType) -> None:
    run = running_case(tmp_path, workflow)
    digest = workflow.propose(run["context"], model_proposal(run, workflow))[
        "proposal_digest"
    ]

    with pytest.raises(ValueError, match="reviewer"):
        workflow.review(
            run["context"],
            digest=digest,
            reviewer="  ",
            confirmation_ref="fixture",
            confirmed=True,
            synthetic=True,
        )


def test_no_confirmation_does_not_write_decision(
    tmp_path: Path, workflow: ModuleType
) -> None:
    run = running_case(tmp_path, workflow)
    digest = workflow.propose(run["context"], model_proposal(run, workflow))[
        "proposal_digest"
    ]

    with pytest.raises(ValueError, match="Explicit confirmation"):
        workflow.review(
            run["context"],
            digest=digest,
            reviewer="fixture",
            confirmation_ref="fixture",
            confirmed=False,
            synthetic=True,
        )
    assert not (run["output"] / f"decision_{digest}.json").exists()


def test_real_calculation_cannot_use_synthetic_acceptance(
    tmp_path: Path, workflow: ModuleType
) -> None:
    run = running_case(tmp_path, workflow, demo=False)
    digest = reviewed(run, workflow, model_proposal(run, workflow))

    with pytest.raises(ValueError, match="authenticated professional"):
        workflow.calculate_draft(run["context"], digest=digest)


def test_another_client_session_is_rejected(
    tmp_path: Path, workflow: ModuleType
) -> None:
    first = running_case(tmp_path / "first", workflow)
    second = running_case(tmp_path / "second", workflow)
    (second["output"] / "patent_box_session.json").write_bytes(
        (first["output"] / "patent_box_session.json").read_bytes()
    )

    with pytest.raises(ValueError, match="another run"):
        workflow.initialize(second["context"], as_of="2026-09-23", demo=True)


def test_cancelled_run_cannot_write_workflow_artifacts(
    tmp_path: Path, workflow: ModuleType
) -> None:
    run = running_case(tmp_path, workflow)
    run["archive"].cancel_studio_client_workflow(
        run["client"]["client_id"],
        run["engagement"]["engagement_id"],
        run["session"]["run_id"],
        state_dir=run["state"],
    )

    with pytest.raises(ValueError):
        workflow.initialize(run["context"], as_of="2026-09-23", demo=True)


def test_result_directory_is_never_overwritten(
    tmp_path: Path, workflow: ModuleType
) -> None:
    run = running_case(tmp_path, workflow)
    digest = reviewed(run, workflow, model_proposal(run, workflow))
    first = workflow.calculate_draft(run["context"], digest=digest)

    with pytest.raises(FileExistsError):
        workflow.calculate_draft(run["context"], digest=digest)
    assert (
        json.loads((Path(first["output_dir"]) / "result.json").read_text())[
            "additional_deduction"
        ]["income"]
        == "110000.00"
    )


@pytest.mark.parametrize(
    "command", ["initialize", "import-ledger", "propose", "review", "calculate"]
)
def test_host_cli_completes_each_public_action(
    tmp_path: Path,
    workflow: ModuleType,
    capsys: pytest.CaptureFixture[str],
    command: str,
) -> None:
    run = running_case(tmp_path, workflow)
    arguments = ["--client-engagement", str(run["context"]), command]
    if command == "initialize":
        arguments += ["--as-of", "2026-09-23", "--demo"]
    elif command == "import-ledger":
        evidence = next(
            row
            for row in run["session"]["inputs"]
            if row["description"] == "ledger.csv"
        )
        arguments += ["--evidence-id", evidence["evidence_id"]]
    else:
        proposal = model_proposal(run, workflow)
        if command == "propose":
            path = run["output"] / "model_proposal.json"
            path.write_text(json.dumps(proposal))
            arguments += ["--proposal", str(path)]
        elif command == "review":
            digest = workflow.propose(run["context"], proposal)["proposal_digest"]
            arguments += [
                "--digest",
                digest,
                "--reviewer",
                "SYNTHETIC",
                "--confirmation-ref",
                "cli-fixture",
                "--confirmed",
                "--synthetic",
            ]
        else:
            digest = reviewed(run, workflow, proposal)
            arguments += ["--digest", digest]

    exit_code = workflow.main(arguments)

    assert exit_code == 0
    assert isinstance(json.loads(capsys.readouterr().out), dict)


def test_dependency_preflight_uses_existing_python_runtime() -> None:
    checker = load_module(
        "patent_box_dependency_test", PLUGIN / "scripts/check_dependencies.py"
    )

    exit_code = checker.main([])

    assert exit_code == 0


def test_invented_cost_row_cannot_pass_with_matching_evidence_id(
    tmp_path: Path, workflow: ModuleType
) -> None:
    run = running_case(tmp_path, workflow)
    proposal = model_proposal(run, workflow)
    proposal["case"]["costs"][0]["book_amount"] = "100001.00"

    with pytest.raises(ValueError, match="differs from selected mapped ledger"):
        workflow.propose(run["context"], proposal)


def test_missing_evidence_on_positive_decision_is_rejected(
    tmp_path: Path, workflow: ModuleType
) -> None:
    run = running_case(tmp_path, workflow)
    proposal = model_proposal(run, workflow)
    proposal["controls"][0]["evidence_ids"] = []

    with pytest.raises(ValueError, match="requires evidence and sources"):
        workflow.propose(run["context"], proposal)


def test_result_manifest_links_prior_version_without_overwrite(
    tmp_path: Path, workflow: ModuleType
) -> None:
    run = running_case(tmp_path, workflow)
    proposal = model_proposal(run, workflow)
    first = workflow.calculate_draft(
        run["context"], digest=reviewed(run, workflow, proposal)
    )
    proposal["case"]["allocations"][0]["income_amount"] = "90000.00"
    digest = reviewed(run, workflow, proposal)

    revised = workflow.calculate_draft(run["context"], digest=digest)

    assert revised["result"]["additional_deduction"]["income"] == "99000.00"
    assert json.loads((Path(revised["output_dir"]) / "manifest.json").read_text())[
        "previous_results"
    ] == [Path(first["output_dir"]).name]


@pytest.mark.parametrize(
    "status,reviewer", [("PASS", "  "), ("FAIL", None), ("FAIL", "  ")]
)
def test_reference_core_does_not_admit_or_exclude_without_review(
    workflow: ModuleType, status: str, reviewer: str | None
) -> None:
    case = json.loads((PLUGIN / "examples/case.ordinary.json").read_text())
    rules = json.loads((PLUGIN / "examples/rules.demo.json").read_text())
    case["controls"][0].update(status=status, reviewer=reviewer)

    result = workflow.calculate(
        case, rules, evidence_root=PLUGIN / "examples/evidence", as_of="2026-09-23"
    )

    assert result["lines"][0]["status"] == "SUSPENDED"


@pytest.mark.parametrize("ip_type", ["PATENT", "DESIGN"])
def test_specialist_ip_branch_reaches_bound_calculation(
    tmp_path: Path, workflow: ModuleType, ip_type: str
) -> None:
    run = running_case(tmp_path, workflow)
    proposal = model_proposal(run, workflow)
    proposal["case"]["ips"][0]["type"] = ip_type
    next(c for c in proposal["controls"] if c["key"] == "ip:IP.SOFT/PB.IP.SOFTWARE")[
        "key"
    ] = ("ip:IP.SOFT/PB.IP." + ip_type)
    digest = reviewed(run, workflow, proposal)

    result = workflow.calculate_draft(run["context"], digest=digest)["result"]

    assert result["lines"][0]["status"] == "INCLUDED"
    assert result["additional_deduction"]["income"] == "110000.00"


@pytest.mark.parametrize(
    "period,status", [("P2017", "INCLUDED"), ("P2016", "EXCLUDED")]
)
def test_premial_branch_uses_exact_fiscal_window_in_archive_run(
    tmp_path: Path, workflow: ModuleType, period: str, status: str
) -> None:
    ledger = (
        "cost_id,ledger_row_key,period_id,account,category,book_amount,income_max,irap_max\n"
        + f"C1,GL.1,{period},Synthetic cost,PERSONNEL,100000.00,100000.00,80000.00\n"
    )
    run = running_case(tmp_path, workflow, ledger_text=ledger)
    proposal = model_proposal(run, workflow)
    historical = json.loads((PLUGIN / "examples/case.premial.json").read_text())
    proposal["case"]["periods"] = historical["periods"]
    proposal["case"]["ips"][0]["premial_event"] = historical["ips"][0]["premial_event"]
    proposal["case"]["ips"][0]["premial_event"]["evidence_ids"] = ["E0001"]
    proposal["case"]["allocations"][0]["mode"] = "PREMIAL"
    proposal["controls"] += [
        dict(proposal["controls"][0], key="ip:IP.SOFT/" + key)
        for key in ("PB.PREMIAL", "PB.PREMIAL.SOFTWARE")
    ]
    digest = reviewed(run, workflow, proposal)

    result = workflow.calculate_draft(run["context"], digest=digest)["result"]

    assert result["lines"][0]["status"] == status


def test_missing_extraordinary_review_suspends_case(
    tmp_path: Path, workflow: ModuleType
) -> None:
    run = running_case(tmp_path, workflow)
    proposal = model_proposal(run, workflow)
    proposal["controls"] = [
        r for r in proposal["controls"] if r["key"] != "case/PB.EXTRAORDINARY"
    ]
    digest = reviewed(run, workflow, proposal)

    result = workflow.calculate_draft(run["context"], digest=digest)["result"]

    assert result["lines"][0]["status"] == "SUSPENDED"
    assert "HISTORY:NOT_TESTED" in result["lines"][0]["reasons"]


def test_penalty_details_do_not_suspend_substantive_calculation(
    tmp_path: Path, workflow: ModuleType
) -> None:
    run = running_case(tmp_path, workflow)
    proposal = model_proposal(run, workflow)
    proposal["case"]["penalty_protection"]["requested"] = True
    proposal["controls"] += [
        dict(proposal["controls"][0], key="penalty/" + key)
        for key in (
            "PB.DOC.A",
            "PB.DOC.B",
            "PB.DOC.SIGN",
            "PB.DOC.TIME",
            "PB.DECLARATION",
            "PB.DOC.RETENTION",
        )
    ]
    next(r for r in proposal["controls"] if r["key"] == "penalty/PB.DOC.TIME")[
        "status"
    ] = "BLOCKED"
    digest = reviewed(run, workflow, proposal)

    result = workflow.calculate_draft(run["context"], digest=digest)["result"]

    assert result["lines"][0]["status"] == "INCLUDED"
    assert result["penalty_protection"]["status"] == "NOT_READY"
    assert "TIMESTAMP:BLOCKED" in result["penalty_protection"]["reasons"]
