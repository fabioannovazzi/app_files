from __future__ import annotations

import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

ROOT = Path(__file__).resolve().parents[2]


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def case(tmp_path):
    ledger = load(
        "esg_test_ledger", ROOT / "plugins/studio-archive/scripts/client_ledger.py"
    )
    esg = load(
        "esg_test_core", ROOT / "plugins/esg-reporting-assurance/scripts/esg_case.py"
    )
    root = tmp_path / "client"
    root.mkdir()
    client = "client_" + "a" * 24
    ledger.create_client_manifest(root, client)
    engagement = ledger.create_engagement(root, client, "Synthetic ESG")[
        "engagement_id"
    ]
    source = tmp_path / "energy.csv"
    source.write_text("period,kwh\n2026,0\n2025,\n")
    receipt = ledger.import_document(root, client, engagement, source, "source")[
        "receipt"
    ]
    prepared = ledger.prepare_run(
        root, client, engagement, esg.WORKFLOW, "0.1.0", input_ids=[receipt["input_id"]]
    )
    ledger.start_run(root, engagement, prepared["run"]["run_id"])
    context = Path(prepared["context_path"])
    request = {
        "case_id": "esg-2026",
        "idempotency_key": "start",
        "previous_context": None,
        "record": {
            "service": "preparation",
            "reporting_basis": "voluntary",
            "period": {"start": "2026-01-01", "end": "2026-12-31"},
            "jurisdiction": "IT",
            "framework_version": None,
            "assurance_level": "not_applicable",
            "synthetic": True,
        },
    }
    result = esg.execute(context, "start_case", request)
    return SimpleNamespace(
        esg=esg,
        ledger=ledger,
        root=root,
        client=client,
        engagement=engagement,
        receipt=receipt,
        prepared=prepared,
        context=context,
        request=request,
        result=result,
        source=source,
        output=Path(prepared["output_dir"]),
    )


def bind_request(case, **updates):
    return {
        "id": "energy",
        "idempotency_key": "bind",
        "expected_state_sha256": case.esg.resume_case(case.context)["state_sha256"],
        "input_id": case.receipt["input_id"],
        "locator": {"row": 1, "column": "kwh"},
        "observation": {
            "status": "observed",
            "value": "0",
            "unit": "kWh",
            "rationale": "Supplied synthetic cell",
            "disclosure_id": None,
            "metric_id": "energy",
        },
        **updates,
    }


def mutate(case, command, payload):
    return case.esg.execute(
        case.context,
        command,
        {
            "expected_state_sha256": case.esg.resume_case(case.context)["state_sha256"],
            **payload,
        },
    )


def decision(case, reference):
    return mutate(
        case,
        "record_decision",
        {
            "id": "review",
            "idempotency_key": "review",
            "dependencies": [reference],
            "record": {
                "type": "scope",
                "decided_by": "Synthetic reviewer",
                "decided_on": "2026-09-29",
                "outcome": "approved",
                "decision": "Accept the input mapping",
                "rationale": "Compared selected source cell",
            },
        },
    )


def draft(case, reference, claim="partial_draft"):
    return mutate(
        case,
        "build_deliverables",
        {
            "id": "memo",
            "idempotency_key": "draft",
            "dependencies": [reference],
            "claim": claim,
            "title": "Synthetic evidence memo",
            "content": "Energy: 0 kWh in the supplied cell. Coverage is partial.",
        },
    )


def test_start_replay_recovers_same_case_without_duplicate_versions(case):
    replay = case.esg.execute(case.context, "start_case", case.request)
    assert replay["status"] == "replayed"
    assert replay["reference"] == case.result["reference"]
    assert case.esg.resume_case(case.context)["revision"] == 1


def test_bind_csv_cell_persists_locator_raw_text_and_numeric_zero(case):
    result = case.esg.execute(case.context, "bind_evidence", bind_request(case))
    recovered = case.esg.resume_case(case.context)["objects"][-1]
    assert recovered["reference"] == result["reference"]
    assert recovered["record"]["excerpt"] == "0"
    assert recovered["record"]["observation"]["value"] == "0"
    assert recovered["record"]["locator"] == {"row": 1, "column": "kwh"}


@pytest.mark.parametrize("status", ["not_available", "not_applicable"])
def test_absence_remains_null_with_explicit_reason(case, status):
    request = bind_request(case, locator={"row": 2, "column": "kwh"})
    request["observation"].update(
        status=status,
        value=None,
        rationale="Reviewer documents absence or non-applicability",
    )
    case.esg.execute(case.context, "bind_evidence", request)
    assert (
        case.esg.resume_case(case.context)["objects"][-1]["record"]["observation"][
            "value"
        ]
        is None
    )


@pytest.mark.parametrize("value", [0, 1.25, "01", "1.0", "-0", "NaN", "1e3", None])
def test_observed_values_require_canonical_decimal_strings(case, value):
    request = bind_request(case)
    request["observation"]["value"] = value
    with pytest.raises(case.esg.ESGError):
        case.esg.execute(case.context, "bind_evidence", request)


def test_empty_source_cannot_be_observed_zero(case):
    with pytest.raises(case.esg.ESGError, match="empty cell"):
        case.esg.execute(
            case.context,
            "bind_evidence",
            bind_request(case, locator={"row": 2, "column": "kwh"}),
        )


@pytest.mark.parametrize(
    "locator",
    [
        {"row": 90, "column": "kwh"},
        {"row": 0, "column": "kwh"},
        {"row": 1, "column": "missing"},
        {"line": 1},
        {"path": "../../secret"},
    ],
)
def test_bad_locators_fail_without_advancing_state(case, locator):
    with pytest.raises(case.esg.ESGError):
        case.esg.execute(
            case.context, "bind_evidence", bind_request(case, locator=locator)
        )
    assert case.esg.resume_case(case.context)["revision"] == 1


def test_conflicting_idempotency_key_rejects_new_payload(case):
    request = bind_request(case)
    case.esg.execute(case.context, "bind_evidence", request)
    request["observation"]["rationale"] = "Changed request"
    with pytest.raises(case.esg.ESGError, match="Idempotency"):
        case.esg.execute(case.context, "bind_evidence", request)


def test_retry_after_later_mutation_returns_original_reference(case):
    request = bind_request(case)
    original = case.esg.execute(case.context, "bind_evidence", request)
    decision(case, original["reference"])
    result = case.esg.execute(case.context, "bind_evidence", request)
    assert result["status"] == "replayed"
    assert result["reference"] == original["reference"]


def test_stale_writer_cannot_overwrite_new_decision(case):
    request = bind_request(case)
    case.esg.execute(case.context, "bind_evidence", request)
    request["idempotency_key"] = "later-writer"
    with pytest.raises(case.esg.ESGError, match="State changed"):
        case.esg.execute(case.context, "bind_evidence", request)


@pytest.mark.parametrize(
    "field,value",
    [
        ("client_id", "another-client"),
        ("engagement_id", "another-engagement"),
        ("id", "missing"),
        ("sha256", "0" * 64),
    ],
)
def test_decision_rejects_cross_case_or_missing_reference(case, field, value):
    reference = dict(case.result["reference"], **{field: value})
    with pytest.raises(case.esg.ESGError):
        decision(case, reference)


def test_new_evidence_version_invalidates_transitive_decision_and_draft(case):
    bound = case.esg.execute(case.context, "bind_evidence", bind_request(case))
    reviewed = decision(case, bound["reference"])
    artifact = draft(case, reviewed["reference"])
    case.source.write_text("period,kwh\n2026,15\n")
    new_input = case.ledger.import_document(
        case.root, case.client, case.engagement, case.source, "source"
    )["receipt"]
    next_run = case.ledger.prepare_run(
        case.root,
        case.client,
        case.engagement,
        case.esg.WORKFLOW,
        "0.1.0",
        input_ids=[case.receipt["input_id"], new_input["input_id"]],
    )
    case.ledger.start_run(case.root, case.engagement, next_run["run"]["run_id"])
    next_context = Path(next_run["context_path"])
    case.esg.execute(
        next_context,
        "start_case",
        {**case.request, "previous_context": str(case.context)},
    )
    request = bind_request(
        case,
        idempotency_key="v2",
        input_id=new_input["input_id"],
        expected_state_sha256=case.esg.resume_case(next_context)["state_sha256"],
    )
    request["observation"]["value"] = "15"
    case.esg.execute(next_context, "bind_evidence", request)
    state = case.esg.resume_case(next_context)
    assert state["objects"][1]["current"] is False
    assert state["objects"][2]["current"] is False
    assert state["objects"][3]["current"] is False
    assert state["objects"][-1]["current"] is True
    assert state["objects"][3]["reference"] == artifact["reference"]
    assert case.esg.resume_case(case.context)["objects"][-1]["current"] is True


def test_stale_reference_cannot_approve_new_version(case):
    bound = case.esg.execute(case.context, "bind_evidence", bind_request(case))
    case.esg.execute(
        case.context, "bind_evidence", bind_request(case, idempotency_key="new-version")
    )
    with pytest.raises(case.esg.ESGError, match="stale"):
        decision(case, bound["reference"])


@pytest.mark.parametrize("claim", ["compliant", "assurance", "ready_for_delivery"])
def test_no_unqualified_conformity_or_assurance_export(case, claim):
    with pytest.raises(case.esg.ESGError, match="unavailable"):
        draft(case, case.result["reference"], claim=claim)


def test_draft_writes_readable_and_structured_immutable_files(case):
    result = draft(case, case.result["reference"])
    prefix = "esg-draft-" + result["reference"]["sha256"]
    assert "PARTIAL FOUNDATION DRAFT" in (case.output / (prefix + ".md")).read_text()
    assert (
        json.loads((case.output / (prefix + ".json")).read_text())["record"]["claim"]
        == "partial_draft"
    )


@pytest.mark.parametrize("target", ["input", "state", "artifact"])
def test_changed_bytes_block_resume(case, target):
    artifact = draft(case, case.result["reference"])
    paths = {
        "input": Path(case.receipt["path"]),
        "state": case.output / "esg_state.json",
        "artifact": case.output
        / ("esg-draft-" + artifact["reference"]["sha256"] + ".md"),
    }
    paths[target].write_text("{}")
    with pytest.raises((case.esg.ESGError, case.esg.AssuranceContractError)):
        case.esg.resume_case(case.context)


def test_symlinked_state_is_rejected(case, tmp_path):
    state = case.output / "esg_state.json"
    outside = tmp_path / "outside.json"
    state.rename(outside)
    state.symlink_to(outside)
    with pytest.raises(case.esg.ESGError, match="symbolic link"):
        case.esg.resume_case(case.context)


def test_parallel_write_lock_rejects_mutation(case):
    (case.output / ".esg-write.lock").write_text("in progress")
    with pytest.raises(case.esg.ESGError, match="write is pending"):
        case.esg.execute(case.context, "bind_evidence", bind_request(case))


def test_service_and_reporting_basis_are_separate(case):
    other = {
        **case.request["record"],
        "service": "assurance",
        "reporting_basis": "voluntary",
        "assurance_level": "limited",
    }
    run = case.ledger.prepare_run(
        case.root,
        case.client,
        case.engagement,
        case.esg.WORKFLOW,
        "0.1.0",
        input_ids=[case.receipt["input_id"]],
        new_run=True,
    )
    case.ledger.start_run(case.root, case.engagement, run["run"]["run_id"])
    context = Path(run["context_path"])
    case.esg.execute(context, "start_case", {**case.request, "record": other})
    assert (
        case.esg.resume_case(context)["objects"][0]["record"]["reporting_basis"]
        == "voluntary"
    )


def test_blank_reviewer_cannot_create_approval(case):
    with pytest.raises(case.esg.ESGError):
        mutate(
            case,
            "record_decision",
            {
                "id": "bad-review",
                "idempotency_key": "bad-review",
                "dependencies": [case.result["reference"]],
                "record": {
                    "type": "scope",
                    "decided_by": "  ",
                    "decided_on": "2026-09-29",
                    "outcome": "approved",
                    "decision": "Accept",
                    "rationale": "Compared input",
                },
            },
        )


def test_unselected_input_cannot_be_bound(case):
    with pytest.raises(case.esg.ESGError, match="not selected"):
        case.esg.execute(
            case.context,
            "bind_evidence",
            bind_request(case, input_id="../../another-client"),
        )


def test_cli_resume_returns_state_without_new_revision(case, capsys):
    result = case.esg.main(["resume_case", "--context", str(case.context)])
    assert result == 0
    assert json.loads(capsys.readouterr().out)["revision"] == 1


def test_cli_mutation_requires_request(case):
    assert case.esg.main(["bind_evidence", "--context", str(case.context)]) == 1


def test_synthetic_demo_preserves_history_and_rejects_cross_engagement(
    tmp_path, monkeypatch
):
    monkeypatch.syspath_prepend(str(ROOT / "plugins/esg-reporting-assurance/scripts"))
    demo = load(
        "esg_demo_test", ROOT / "plugins/esg-reporting-assurance/scripts/demo_esg.py"
    )

    result = demo.run_demo(tmp_path / "synthetic-demo")

    assert result["status"] == "passed"
    assert result["checks"] == {
        "replay_without_duplicates": True,
        "cross_engagement_rejected": True,
        "prior_approval_stale": True,
        "dependent_draft_stale": True,
        "new_observation_current": True,
        "missing_and_not_applicable_distinct": True,
    }
    assert json.loads(Path(result["result"]).read_text())["synthetic"] is True


def test_esg_foundation_is_not_offered_as_a_qualified_lesson():
    policy = load(
        "esg_teaching_policy_test",
        ROOT / "plugins/_shared/vendor/modules/courseware/policy.py",
    )

    reason = policy.local_unavailability("vera", "esg-reporting-assurance")

    assert "no qualified prepared lesson" in reason
    assert policy.local_unavailability("vera", "treasury-forecast") is None


def test_dependency_checker_accepts_declared_requirements(monkeypatch):
    checker = load(
        "esg_dependencies_test",
        ROOT / "plugins/esg-reporting-assurance/scripts/check_dependencies.py",
    )
    monkeypatch.setattr(checker.importlib.metadata, "version", lambda name: "4.23.0")
    monkeypatch.setattr(
        "sys.argv", ["check_dependencies.py", "--requirements", "requirements.txt"]
    )

    assert checker.main() == 0


@pytest.mark.parametrize("version", ["4.22.0", "5.0.0"])
def test_dependency_checker_rejects_versions_outside_declared_bounds(
    version, monkeypatch
):
    checker = load(
        "esg_dependencies_test",
        ROOT / "plugins/esg-reporting-assurance/scripts/check_dependencies.py",
    )
    monkeypatch.setattr(checker.importlib.metadata, "version", lambda name: version)
    monkeypatch.setattr(
        "sys.argv", ["check_dependencies.py", "--requirements", "requirements.txt"]
    )

    with pytest.raises(SystemExit, match="managed environment"):
        checker.main()


@pytest.mark.parametrize("flag", ["catalogue_complete", "legal_review_approved"])
def test_source_registration_rejects_unqualified_catalogue_claims(case, flag):
    record = {
        "title": "Synthetic criteria",
        "publisher": "Synthetic publisher",
        "url": "https://example.invalid/criteria",
        "version": "demo-1",
        "applicability_period": {"start": "2026-01-01", "end": "2026-12-31"},
        "review_status": "unverified_seed",
        "catalogue_complete": False,
        "legal_review_approved": False,
        "locator": "Section 1",
        "rationale": "Synthetic unqualified source for a gate test",
    }
    record[flag] = True

    with pytest.raises(case.esg.ESGError, match="Catalogue qualification"):
        mutate(
            case,
            "register_source",
            {"id": "criteria", "idempotency_key": "criteria-1", "record": record},
        )


@pytest.mark.parametrize("character", ["x", "é"])
def test_state_limit_rejects_draft_without_changing_saved_case(case, character):
    state_path = case.output / "esg_state.json"
    previous_state = state_path.read_bytes()
    previous_files = set(case.output.iterdir())
    state_limit_bytes = 8 * 1024 * 1024
    request_overhead_margin = 1024
    near_limit_bytes = state_limit_bytes - request_overhead_margin
    content = character * (near_limit_bytes // len(character.encode("utf-8")))
    request = {
        "expected_state_sha256": case.result["state_sha256"],
        "id": "large-memo",
        "idempotency_key": "large-memo",
        "dependencies": [case.result["reference"]],
        "claim": "partial_draft",
        "title": "Synthetic state size limit",
        "content": content,
    }
    assert (
        len(json.dumps(request, ensure_ascii=False).encode("utf-8")) < state_limit_bytes
    )

    with pytest.raises(case.esg.ESGError, match="ESG state exceeds"):
        case.esg.execute(case.context, "build_deliverables", request)

    assert state_path.read_bytes() == previous_state
    assert set(case.output.iterdir()) == previous_files
    assert case.esg.resume_case(case.context)["revision"] == 1
