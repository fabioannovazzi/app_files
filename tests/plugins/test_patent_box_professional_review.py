"""Actual archive, source-receipt and signature integration using synthetic data."""

from __future__ import annotations

import copy
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import pytest
from cryptography.hazmat.primitives import hashes

sys.path.insert(
    0, str(Path(__file__).resolve().parents[2] / "plugins/patent-box-review/tests")
)
sys.path.insert(0, str(Path(__file__).resolve().parent))
from patent_box import source_acquisition as sources
from patent_box.authorization import request_bytes
from patent_box.contracts import ContractError, canonical_hash
from patent_box.professional_review import verify_control_review
from patent_box.source_transport import PublicResponse
from test_authorization import signed
from test_formalities import AFTER, BEFORE, authority
from test_patent_box_workflow import model_proposal, running_case, workflow
from test_source_acquisition import plan, review

NOW = datetime(2026, 9, 23, 12, tzinfo=timezone.utc)


@pytest.fixture
def review_case(tmp_path, workflow, authority, monkeypatch):
    run = running_case(tmp_path, workflow)
    payload = model_proposal(run, workflow)
    digest = workflow.propose(run["context"], payload)["proposal_digest"]
    proposal = json.loads((run["output"] / f"proposal_{digest}.json").read_text())
    source = proposal["rules"]["sources"][0]
    original = next(
        row
        for row in run["session"]["inputs"]
        if row["evidence_id"] == source["snapshot_evidence_id"]
    )
    raw = (run["output"] / original["path"]).read_bytes()
    monkeypatch.setattr(sources, "_now", lambda: NOW.isoformat())
    scan = Path(
        sources.open_scan(
            plan("https://institution.example/document"), tmp_path / "public"
        )["directory"]
    )
    receipt = sources.acquire(
        scan,
        scope_id="PUBLIC",
        url="https://institution.example/document",
        kind="DOCUMENT",
        fetcher=lambda url, **kwargs: PublicResponse(url, "text/plain", raw),
    )
    coverage = review(receipt)
    coverage["source_selections"][0]["source_id"] = source["source_id"]
    sources.finish_scan(scan, coverage)
    prepared = workflow.prepare_professional_review(
        run["context"], digest=digest, source_scan=scan, at=NOW
    )
    request = prepared["request"]
    a = authority
    fingerprint = a["signer_cert"].fingerprint(hashes.SHA256()).hex()
    policy = {
        "schema_version": "1.0",
        "policy_id": "TEST.POLICY",
        "authority_name": "Synthetic firm",
        "demo": True,
        "admin_certificate_sha256": [fingerprint],
        "revoked_certificate_sha256": [],
        "revoked_mandate_ids": [],
    }
    grant = {
        "schema_version": "1.0",
        "mandate_id": "TEST.MANDATE",
        "policy_id": "TEST.POLICY",
        "demo": True,
        "scope": request["scope"],
        "reviewer_name": "Synthetic reviewer",
        "professional_reference": "Synthetic acceptance only",
        "reviewer_certificate_sha256": fingerprint,
        "actions": [
            "REVIEW_CONTROLS",
            "REVIEW_RULES",
            "APPROVE_DOSSIER",
            "REOPEN_CASE",
        ],
        "valid_from": BEFORE.isoformat(),
        "valid_until": AFTER.isoformat(),
        "powers_evidence": [{"reference": "TEST.AUTHORITY", "sha256": "1" * 64}],
    }
    admin = tmp_path / "admin"
    admin.mkdir()
    config = admin / "configuration.json"
    config.write_text(
        json.dumps(
            {
                "policy": policy,
                "openssl": str(a["openssl"]),
                "trusted_roots": str(a["ca"]),
                "crls": str(a["crl"]),
            }
        )
    )
    monkeypatch.setenv("VERA_PATENT_BOX_AUTHORITY_CONFIG", str(config))
    mandate = admin / "mandate.json"
    mandate.write_bytes(request_bytes(grant))
    mandate_signature = admin / "mandate.p7s"
    mandate_signature.write_bytes(
        signed(mandate.read_bytes(), a["signer_cert"], a["signer_key"], a["root_cert"])
    )
    signature = admin / "review.p7s"
    signature.write_bytes(
        signed(
            request_bytes(request), a["signer_cert"], a["signer_key"], a["root_cert"]
        )
    )
    return {
        **run,
        "digest": digest,
        "proposal": proposal,
        "scan": scan,
        "prepared_review": prepared,
        "signature": signature,
        "mandate": mandate,
        "mandate_signature": mandate_signature,
        "configuration": config,
    }


def accept(workflow, case):
    return workflow.accept_professional_review(
        case["context"],
        digest=case["digest"],
        request_digest=case["prepared_review"]["request_digest"],
        signature=case["signature"],
        mandate=case["mandate"],
        mandate_signature=case["mandate_signature"],
        at=NOW,
    )


def test_authenticated_review_is_preserved_and_reverified_in_exact_archive_run(
    workflow, review_case
):
    case = review_case
    accepted = accept(workflow, case)
    context = {
        "client_id": case["client"]["client_id"],
        "engagement_id": case["engagement"]["engagement_id"],
    }
    verified = verify_control_review(
        context, case["session"], case["output"], case["proposal"], at=NOW
    )
    assert verified == accepted
    assert accepted["identity_assurance"] == "CERTIFICATE_AND_FIRM_SIGNED_MANDATE"
    assert (case["output"] / f"authenticated_decision_{case['digest']}.json").is_file()


def test_professional_review_rechecks_original_source_bytes(workflow, review_case):
    case = review_case
    original = Path(case["session"]["inputs"][0]["selected_path"])
    original.write_bytes(original.read_bytes() + b"Changed after review")
    with pytest.raises(ValueError, match="no longer matches its receipt"):
        accept(workflow, case)


def test_professional_review_cannot_replace_existing_decision(workflow, review_case):
    case = review_case
    accept(workflow, case)
    path = case["output"] / f"authenticated_decision_{case['digest']}.json"
    original = path.read_bytes()
    with pytest.raises(ValueError, match="already exists"):
        accept(workflow, case)
    assert path.read_bytes() == original


def test_professional_review_requires_separate_host_configuration(
    workflow, review_case, monkeypatch
):
    monkeypatch.delenv("VERA_PATENT_BOX_AUTHORITY_CONFIG")
    with pytest.raises(ValueError, match="not configured"):
        accept(workflow, review_case)


def test_professional_review_cannot_take_authority_configuration_from_case_output(
    workflow, review_case, monkeypatch
):
    case = review_case
    config = case["output"] / "forged-authority.json"
    config.write_bytes(case["configuration"].read_bytes())
    monkeypatch.setenv("VERA_PATENT_BOX_AUTHORITY_CONFIG", str(config))
    with pytest.raises(ValueError, match="separate host-admin"):
        accept(workflow, case)


def test_professional_review_rejects_stale_source_preflight(workflow, review_case):
    from datetime import timedelta

    case = review_case
    with pytest.raises(ValueError, match="24 hours"):
        workflow.prepare_professional_review(
            case["context"],
            digest=case["digest"],
            source_scan=case["scan"],
            at=NOW + timedelta(days=2),
        )


def test_professional_review_rejects_changed_preflight_record(workflow, review_case):
    case = review_case
    path = Path(case["prepared_review"]["directory"]) / "source_preflight.json"
    raw = json.loads(path.read_text())
    raw["exhaustive_legal_monitoring"] = True
    path.write_text(json.dumps(raw))
    with pytest.raises(ValueError, match="bindings changed"):
        accept(workflow, case)


def test_professional_review_rejects_changed_signature_after_acceptance(
    workflow, review_case
):
    case = review_case
    accept(workflow, case)
    path = (
        case["output"]
        / f"professional_evidence_{case['prepared_review']['request_digest']}"
        / "request_signature"
    )
    path.write_bytes(b"Forged signature")
    context = {
        "client_id": case["client"]["client_id"],
        "engagement_id": case["engagement"]["engagement_id"],
    }
    with pytest.raises(ValueError, match="signature_integrity"):
        verify_control_review(
            context, case["session"], case["output"], case["proposal"], at=NOW
        )


def test_authenticated_archive_flow_calculates_and_signs_exact_final_version(
    workflow, review_case, authority
):
    case = review_case
    accept(workflow, case)
    calculated = workflow.calculate_draft(
        case["context"], digest=case["digest"], at=NOW
    )
    prepared = workflow.prepare_professional_review(
        case["context"],
        digest=case["digest"],
        source_scan=case["scan"],
        action="APPROVE_DOSSIER",
        at=NOW,
    )
    signature = case["signature"].parent / "final-review.p7s"
    signature.write_bytes(
        signed(
            request_bytes(prepared["request"]),
            authority["signer_cert"],
            authority["signer_key"],
            authority["root_cert"],
        )
    )
    accepted = workflow.accept_professional_review(
        case["context"],
        digest=case["digest"],
        request_digest=prepared["request_digest"],
        signature=signature,
        mandate=case["mandate"],
        mandate_signature=case["mandate_signature"],
        at=NOW,
    )
    assert accepted["confirmation_ref"] == prepared["request_digest"]
    assert (case["output"] / f"professional_approval_{case['digest']}.json").is_file()
    assert (Path(calculated["output_dir"]) / "fascicolo_A_B.pdf").is_file()
    assert prepared["request"]["bindings"]["result_sha256"] is not None
    assert prepared["request"]["demo"] is True


def test_final_approval_rejects_changed_output_file(workflow, review_case, authority):
    case = review_case
    accept(workflow, case)
    calculated = workflow.calculate_draft(
        case["context"], digest=case["digest"], at=NOW
    )
    prepared = workflow.prepare_professional_review(
        case["context"],
        digest=case["digest"],
        source_scan=case["scan"],
        action="APPROVE_DOSSIER",
        at=NOW,
    )
    signature = case["signature"].parent / "final-review.p7s"
    signature.write_bytes(
        signed(
            request_bytes(prepared["request"]),
            authority["signer_cert"],
            authority["signer_key"],
            authority["root_cert"],
        )
    )
    (Path(calculated["output_dir"]) / "result.json").write_text('{"changed":true}')
    with pytest.raises(ValueError, match="artifacts changed"):
        workflow.accept_professional_review(
            case["context"],
            digest=case["digest"],
            request_digest=prepared["request_digest"],
            signature=signature,
            mandate=case["mandate"],
            mandate_signature=case["mandate_signature"],
            at=NOW,
        )


def test_calculation_rechecks_current_mandate_revocation(workflow, review_case):
    case = review_case
    accept(workflow, case)
    configuration = json.loads(case["configuration"].read_text())
    configuration["policy"]["revoked_mandate_ids"] = ["TEST.MANDATE"]
    case["configuration"].write_text(json.dumps(configuration))
    with pytest.raises(ValueError, match="revoked"):
        workflow.calculate_draft(case["context"], digest=case["digest"], at=NOW)


def test_calculation_rejects_forged_authenticated_identity_label(workflow, review_case):
    case = review_case
    accept(workflow, case)
    decision = case["output"] / f"authenticated_decision_{case['digest']}.json"
    value = json.loads(decision.read_text())
    value["identity_assurance"] = "FORGED"
    decision.write_text(json.dumps(value))
    with pytest.raises(ValueError, match="authenticated evidence"):
        workflow.calculate_draft(case["context"], digest=case["digest"], at=NOW)


def test_formalities_cli_preserves_failed_crypto_result_for_selected_evidence(
    workflow, review_case, authority, capsys
):
    case = review_case
    evidence = case["session"]["inputs"]
    plan_path = case["output"] / "formalities-plan.json"
    plan_path.write_text(
        json.dumps(
            {
                "schema_version": "1.0",
                "format": "CMS_DETACHED",
                "document_evidence_id": evidence[0]["evidence_id"],
                "signature_evidence_id": evidence[1]["evidence_id"],
            }
        )
    )
    result = workflow.main(
        [
            "--client-engagement",
            str(case["context"]),
            "verify-formalities",
            "--plan",
            str(plan_path),
            "--openssl",
            str(authority["openssl"]),
        ]
    )
    saved = json.loads(capsys.readouterr().out)
    assert result == 0
    assert saved["verification"]["signature_integrity"]["status"] == "FAIL"
    assert (Path(saved["output_dir"]) / "verification.json").is_file()


def test_formalities_rejects_evidence_from_another_run(
    workflow, review_case, authority
):
    plan = {
        "schema_version": "1.0",
        "format": "CMS_DETACHED",
        "document_evidence_id": "E9999",
        "signature_evidence_id": "E0001",
    }
    with pytest.raises(ValueError, match="only this run"):
        workflow.verify_formalities(
            review_case["context"], plan, openssl=authority["openssl"]
        )


def sign_and_accept(workflow, case, prepared, authority, *, digest=None):
    signature = case["signature"].parent / (prepared["request_digest"] + ".p7s")
    signature.write_bytes(
        signed(
            request_bytes(prepared["request"]),
            authority["signer_cert"],
            authority["signer_key"],
            authority["root_cert"],
        )
    )
    return workflow.accept_professional_review(
        case["context"],
        digest=digest or case["digest"],
        request_digest=prepared["request_digest"],
        signature=signature,
        mandate=case["mandate"],
        mandate_signature=case["mandate_signature"],
        at=NOW,
    )


@pytest.fixture
def approved_case(workflow, review_case, authority):
    case = review_case
    accept(workflow, case)
    workflow.calculate_draft(case["context"], digest=case["digest"], at=NOW)
    prepared = workflow.prepare_professional_review(
        case["context"],
        digest=case["digest"],
        source_scan=case["scan"],
        action="APPROVE_DOSSIER",
        at=NOW,
    )
    sign_and_accept(workflow, case, prepared, authority)
    proposal = {
        key: copy.deepcopy(case["proposal"][key])
        for key in ("case", "rules", "controls", "narratives")
    }
    proposal["controls"][0]["conclusion"] += " Revised after documented review."
    revised = workflow.propose(case["context"], proposal)["proposal_digest"]
    return {**case, "revised": revised, "final_request": prepared}


def reopen_request(workflow, case, **overrides):
    options = dict(
        digest=case["revised"],
        source_scan=case["scan"],
        action="REOPEN_CASE",
        previous_digest=case["digest"],
        reason="Review the documented change without replacing prior artifacts.",
        at=NOW,
    )
    options.update(overrides)
    return workflow.prepare_professional_review(case["context"], **options)


def test_reopening_preserves_signed_version_and_requires_new_control_review(
    workflow, approved_case, authority
):
    case = approved_case
    prior = case["output"] / f"professional_approval_{case['digest']}.json"
    old_bytes = prior.read_bytes()
    request = reopen_request(workflow, case)
    record = sign_and_accept(workflow, case, request, authority, digest=case["revised"])
    prepared = workflow.prepare_professional_review(
        case["context"], digest=case["revised"], source_scan=case["scan"], at=NOW
    )
    sign_and_accept(workflow, case, prepared, authority, digest=case["revised"])
    result = workflow.calculate_draft(case["context"], digest=case["revised"], at=NOW)
    assert prior.read_bytes() == old_bytes
    assert record["proposal_digest"] == case["revised"]
    assert (case["output"] / f"professional_reopening_{case['revised']}.json").is_file()
    assert Path(result["output_dir"]).name == f"calculation_{case['revised']}"
    assert not (
        case["output"] / f"professional_approval_{case['revised']}.json"
    ).exists()


def test_changed_approved_case_cannot_bypass_reopening(workflow, approved_case):
    case = approved_case
    with pytest.raises(ValueError, match="authenticated reopening"):
        workflow.prepare_professional_review(
            case["context"], digest=case["revised"], source_scan=case["scan"], at=NOW
        )


def test_synthetic_calculation_cannot_bypass_existing_professional_approval(
    workflow, approved_case
):
    case = approved_case
    workflow.review(
        case["context"],
        digest=case["revised"],
        reviewer="Synthetic reviewer",
        confirmation_ref="synthetic",
        confirmed=True,
        synthetic=True,
    )
    with pytest.raises(ValueError, match="authenticated reopening"):
        workflow.calculate_draft(case["context"], digest=case["revised"], at=NOW)


def test_reopening_needs_the_explicit_action_in_current_mandate(
    workflow, approved_case, authority
):
    case = approved_case
    grant = json.loads(case["mandate"].read_text())
    grant["actions"].remove("REOPEN_CASE")
    case["mandate"].write_bytes(request_bytes(grant))
    case["mandate_signature"].write_bytes(
        signed(
            request_bytes(grant),
            authority["signer_cert"],
            authority["signer_key"],
            authority["root_cert"],
        )
    )
    prepared = reopen_request(workflow, case)
    with pytest.raises(ValueError, match="every requested review action"):
        sign_and_accept(workflow, case, prepared, authority, digest=case["revised"])


@pytest.mark.parametrize(
    "overrides, message",
    [
        ({"reason": " "}, "previous approved version and a reason"),
        ({"previous_digest": None}, "previous approved version and a reason"),
        ({"action": "REVIEW_CONTROLS", "digest": "current"}, "only to reopening"),
    ],
)
def test_reopening_rejects_incomplete_or_misapplied_linkage(
    workflow, approved_case, overrides, message
):
    case = approved_case
    if overrides.get("digest") == "current":
        overrides = {**overrides, "digest": case["digest"]}
    with pytest.raises(ValueError, match=message):
        reopen_request(workflow, case, **overrides)


def test_reopening_rejects_same_version(workflow, approved_case):
    with pytest.raises(ValueError, match="different proposed version"):
        reopen_request(workflow, approved_case, digest=approved_case["digest"])


def test_reopening_rejects_tampered_prior_signed_result(workflow, approved_case):
    case = approved_case
    result = case["output"] / f"calculation_{case['digest']}" / "result.json"
    result.write_text('{"tampered":true}')
    with pytest.raises(ValueError, match="artifacts changed"):
        reopen_request(workflow, case)


def test_reopening_rechecks_prior_evidence_after_request_preparation(
    workflow, approved_case, authority
):
    case = approved_case
    prepared = reopen_request(workflow, case)
    path = (
        case["output"]
        / f"professional_evidence_{case['final_request']['request_digest']}"
        / "request_signature"
    )
    path.write_bytes(b"changed")
    with pytest.raises(ValueError, match="Prior signed evidence changed"):
        sign_and_accept(workflow, case, prepared, authority, digest=case["revised"])


def test_reopening_rejects_changed_prior_approval_metadata(workflow, approved_case):
    case = approved_case
    path = case["output"] / f"professional_approval_{case['digest']}.json"
    record = json.loads(path.read_text())
    record["reviewer"] = "Substituted name"
    path.write_text(json.dumps(record))
    with pytest.raises(ValueError, match="retained evidence"):
        reopen_request(workflow, case)


@pytest.mark.parametrize("change", ["symlink", "extra_directory"])
def test_final_review_rejects_redirected_or_undeclared_artifact_container(
    workflow, review_case, change
):
    case = review_case
    accept(workflow, case)
    result = workflow.calculate_draft(case["context"], digest=case["digest"], at=NOW)
    directory = Path(result["output_dir"])
    if change == "symlink":
        other = directory.with_name("redirected-calculation")
        directory.rename(other)
        directory.symlink_to(other, target_is_directory=True)
    else:
        (directory / "undeclared").mkdir()
    with pytest.raises(ValueError, match="regular directory|artifacts changed"):
        workflow.prepare_professional_review(
            case["context"],
            digest=case["digest"],
            source_scan=case["scan"],
            action="APPROVE_DOSSIER",
            at=NOW,
        )


def test_accept_review_rejects_symlinked_request_directory(workflow, review_case):
    case = review_case
    directory = Path(case["prepared_review"]["directory"])
    other = directory.with_name("redirected-request")
    directory.rename(other)
    directory.symlink_to(other, target_is_directory=True)
    with pytest.raises(ValueError, match="bounded regular"):
        accept(workflow, case)


@pytest.fixture
def successor_case(workflow, approved_case):
    from tests.model_data_helpers import write_no_model_report

    case = approved_case
    archive = case["archive"]
    write_no_model_report(
        case["output"], "patent-box-review", case["session"]["run_id"]
    )
    declarations = [
        {
            "artifact_id": f"patent_box_{index}",
            "path": path.relative_to(case["output"]).as_posix(),
            "purpose": "Synthetic approved-version handoff acceptance",
            "audience": "internal",
            "media_type": "application/octet-stream",
        }
        for index, path in enumerate(
            sorted(path for path in case["output"].rglob("*") if path.is_file())
        )
    ]
    finalized = archive.finalize_studio_client_workflow(
        case["client"]["client_id"],
        case["engagement"]["engagement_id"],
        case["session"]["run_id"],
        declarations,
        state_dir=case["state"],
    )
    archive.complete_studio_client_workflow(
        case["client"]["client_id"],
        case["engagement"]["engagement_id"],
        case["session"]["run_id"],
        state_dir=case["state"],
    )
    prepared = archive.prepare_studio_client_workflow(
        case["engagement"]["engagement_id"],
        "patent-box-review",
        input_ids=[
            row["binding_id"] for row in case["prepared"]["input_manifest"]["inputs"]
        ],
        upstream_artifacts=[
            {
                "run_id": case["session"]["run_id"],
                "artifact_id": row["artifact_id"],
                "role": "patent-box-prior-version",
            }
            for row in finalized["artifact_manifest"]["artifacts"]
        ],
        new_run=True,
        state_dir=case["state"],
    )
    archive.start_studio_client_workflow(
        case["client"]["client_id"],
        case["engagement"]["engagement_id"],
        prepared["run"]["run_id"],
        state_dir=case["state"],
    )
    context = Path(prepared["client_engagement_path"])
    session = workflow.initialize(context, as_of=NOW.date().isoformat(), demo=True)
    successor = {
        **case,
        "context": context,
        "session": session,
        "output": Path(prepared["client_engagement"]["output_dir"]),
        "prior_case": case,
    }
    proposal = model_proposal(successor, workflow)
    successor["revised"] = workflow.propose(context, proposal)["proposal_digest"]
    return successor


def test_completed_archive_version_reopens_in_new_run_without_mutating_old_run(
    workflow, successor_case, authority
):
    case = successor_case
    prior = case["prior_case"]
    approval = prior["output"] / f"professional_approval_{prior['digest']}.json"
    before = approval.read_bytes()
    prepared = reopen_request(workflow, case)
    accepted = sign_and_accept(
        workflow, case, prepared, authority, digest=case["revised"]
    )
    assert accepted["run_id"] != prior["session"]["run_id"]
    assert approval.read_bytes() == before
    assert prepared["request"]["bindings"][
        "prior_approval_sha256"
    ] == workflow.file_hash(approval)
    assert (case["output"] / f"professional_reopening_{case['revised']}.json").is_file()


def test_selected_upstream_approval_requires_reopening_even_in_new_archive_run(
    workflow, successor_case
):
    case = successor_case
    with pytest.raises(ValueError, match="authenticated reopening"):
        workflow.prepare_professional_review(
            case["context"], digest=case["revised"], source_scan=case["scan"], at=NOW
        )


def test_reopening_rejects_changed_archived_upstream_approval(workflow, successor_case):
    case = successor_case
    path = case["prior_case"]["output"] / f"professional_approval_{case['digest']}.json"
    path.write_text('{"changed":true}')
    with pytest.raises(ValueError, match="receipt|artifact|changed|upstream"):
        reopen_request(workflow, case)
