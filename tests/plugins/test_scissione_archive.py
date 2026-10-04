"""Exercise real Studio Archive receipts, immutable outputs and rejection paths."""

from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "plugins/scissione-guidata/scripts"))

from run_scissione import execute, read_revision
from scissione_core import ScissioneError
from vera_assurance import AssuranceContractError

from tests.plugins.test_scissione_guidata import case, review_request, row
from tests.plugins.test_vera_client_workflow_filesystem import _load_customer_ledger


def workspace(tmp_path: Path) -> dict:
    ledger = _load_customer_ledger()
    client = tmp_path / "Client"
    client.mkdir()
    client_id = "client_111111111111111111111111"
    ledger.create_client_manifest(client, client_id)
    engagement = ledger.create_engagement(client, client_id, "Synthetic scissione")[
        "engagement_id"
    ]
    source = tmp_path / "synthetic-evidence.txt"
    source.write_text(
        "Synthetic operation evidence; no real company or legal approval."
    )
    receipt = ledger.import_document(client, client_id, engagement, source, "source")[
        "receipt"
    ]
    prepared = ledger.prepare_run(
        client,
        client_id,
        engagement,
        "scissione-guidata",
        "0.1.0",
        input_ids=[receipt["input_id"]],
    )
    running = ledger.start_run(client, engagement, prepared["run"]["run_id"])
    data = case()
    data["evidence"][0][
        "path"
    ] = f"imports/{receipt['input_id']}/{Path(receipt['relative_path']).name}"
    data["evidence"][0]["sha256"] = hashlib.sha256(source.read_bytes()).hexdigest()
    request = Path(running["output_dir"]) / "proposal.json"
    request.write_text(json.dumps({"case": data}))
    return {
        **running,
        "request": request,
        "case": data,
        "ledger": ledger,
        "client": client,
        "engagement": engagement,
    }


def prepared(workspace: dict) -> dict:
    return execute(Path(workspace["context_path"]), "prepare", workspace["request"])


def test_real_archive_prepare_review_and_historical_replay(tmp_path):
    work = workspace(tmp_path)
    draft = prepared(work)
    output = Path(work["output_dir"])
    review = output / "review-request.json"
    review.write_text(
        json.dumps(
            review_request(
                draft,
                [
                    item["id"]
                    for item in work["case"]["records"]
                    if item["kind"] != "document"
                ],
            )
        )
    )

    result = execute(Path(work["context_path"]), "review", review)

    assert result["status"] == "partial"
    assert result["schedule"]["owners"][0]["economic_transferred"] == "180000.00"
    assert read_revision(output, draft["revision_sha256"])["approvals"] == {}
    assert read_revision(output)["revision_sha256"] == result["revision_sha256"]
    assert (
        output / "scissione_versions" / result["revision_sha256"] / "review.html"
    ).is_file()


def test_real_archive_finalize_closes_writes_and_preserves_readback(tmp_path):
    from tests.model_data_helpers import write_no_model_report

    work = workspace(tmp_path)
    draft = prepared(work)
    output = Path(work["output_dir"])
    run_id = work["context"]["run_id"]
    write_no_model_report(output, "scissione-guidata", run_id)
    declarations = [
        {
            "artifact_id": f"scissione_{index}",
            "path": path.relative_to(output).as_posix(),
            "purpose": "Synthetic integration acceptance",
            "audience": "internal",
            "media_type": "application/octet-stream",
        }
        for index, path in enumerate(
            sorted(p for p in output.rglob("*") if p.is_file())
        )
    ]
    work["ledger"].finalize_run(
        work["client"], work["engagement"], run_id, declarations
    )

    with pytest.raises(AssuranceContractError):
        execute(Path(work["context_path"]), "revise", work["request"])

    assert (
        execute(Path(work["context_path"]), "show")["revision_sha256"]
        == draft["revision_sha256"]
    )


def test_t31_foreign_file_inside_run_inputs_still_fails_membership(tmp_path):
    work = workspace(tmp_path)
    foreign = Path(work["context"]["run_root"]) / "inputs" / "foreign.txt"
    foreign.write_text("Not imported or receipted")
    work["case"]["evidence"][0].update(
        path="foreign.txt", sha256=hashlib.sha256(foreign.read_bytes()).hexdigest()
    )
    work["request"].write_text(json.dumps({"case": work["case"]}))
    with pytest.raises(AssuranceContractError):
        prepared(work)


def test_changed_artifact_is_detected_before_review(tmp_path):
    work = workspace(tmp_path)
    revision = prepared(work)
    output = Path(work["output_dir"])
    (
        output / "scissione_versions" / revision["revision_sha256"] / "review.md"
    ).write_text("changed")
    with pytest.raises(ScissioneError, match="immutable"):
        read_revision(output)


def test_request_outside_bound_output_is_rejected(tmp_path):
    work = workspace(tmp_path)
    path = tmp_path / "external-request.json"
    path.write_text(work["request"].read_text())
    with pytest.raises(ScissioneError, match="inside this run"):
        execute(Path(work["context_path"]), "prepare", path)


def test_stale_revision_is_rejected(tmp_path):
    work = workspace(tmp_path)
    draft = prepared(work)
    request = Path(work["output_dir"]) / "revise.json"
    request.write_text(json.dumps({"case": work["case"], "revision_sha256": "0" * 64}))
    with pytest.raises(ScissioneError, match="Stale"):
        execute(Path(work["context_path"]), "revise", request)


def test_concurrent_writer_is_rejected_without_removing_its_lock(tmp_path):
    work = workspace(tmp_path)
    lock = Path(work["output_dir"]) / ".scissione.lock"
    lock.touch()
    with pytest.raises(ScissioneError, match="Another write"):
        prepared(work)
    assert lock.is_file()


def test_continuation_preserves_reviews_from_finalized_same_engagement(tmp_path):
    from tests.model_data_helpers import write_no_model_report

    work = workspace(tmp_path)
    draft = prepared(work)
    output = Path(work["output_dir"])
    review = output / "review-request.json"
    review.write_text(json.dumps(review_request(draft, ["ownership"])))
    previous = execute(Path(work["context_path"]), "review", review)
    run_id = work["context"]["run_id"]
    write_no_model_report(output, "scissione-guidata", run_id)
    revision_path = f"scissione_versions/{previous['revision_sha256']}/revision.json"
    declarations = [
        {
            "artifact_id": (
                "previous"
                if path.relative_to(output).as_posix() == revision_path
                else f"artifact_{index}"
            ),
            "path": path.relative_to(output).as_posix(),
            "purpose": "Synthetic continuation",
            "audience": "internal",
            "media_type": "application/octet-stream",
        }
        for index, path in enumerate(
            sorted(p for p in output.rglob("*") if p.is_file())
        )
    ]
    work["ledger"].finalize_run(
        work["client"], work["engagement"], run_id, declarations
    )
    imported = next(
        item for item in work["context"]["input_bindings"] if item["kind"] == "import"
    )
    downstream = work["ledger"].prepare_run(
        work["client"],
        "client_111111111111111111111111",
        work["engagement"],
        "scissione-guidata",
        "0.1.0",
        input_ids=[imported["binding_id"]],
        upstream_artifacts=[
            {"run_id": run_id, "artifact_id": "previous", "role": "case"}
        ],
        new_run=True,
    )
    running = work["ledger"].start_run(
        work["client"], work["engagement"], downstream["run"]["run_id"]
    )
    binding = next(
        item
        for item in running["context"]["input_bindings"]
        if item["kind"] == "upstream_artifact"
    )
    proposal = Path(running["output_dir"]) / "continuation.json"
    proposal.write_text(
        json.dumps(
            {
                "case": work["case"],
                "previous_revision_path": Path(binding["path"])
                .relative_to(Path(running["context"]["run_root"]) / "inputs")
                .as_posix(),
            }
        )
    )

    continued = execute(Path(running["context_path"]), "prepare", proposal)

    assert continued["approvals"] == previous["approvals"]
    assert continued["previous_sha256"] == previous["revision_sha256"]
    assert continued["change_impact"]["invalidated_approval_ids"] == []


def test_ordinary_import_cannot_claim_finalized_revision_provenance(tmp_path):
    work = workspace(tmp_path)
    work["request"].write_text(
        json.dumps(
            {
                "case": work["case"],
                "previous_revision_path": work["case"]["evidence"][0]["path"],
            }
        )
    )
    with pytest.raises(ScissioneError, match="finalized same-engagement"):
        prepared(work)


def test_html_report_escapes_case_content(tmp_path):
    work = workspace(tmp_path)
    work["case"]["purpose"] = '<script>alert("case")</script>'
    work["request"].write_text(json.dumps({"case": work["case"]}))
    result = prepared(work)
    report = (
        Path(work["output_dir"])
        / "scissione_versions"
        / result["revision_sha256"]
        / "review.html"
    ).read_text()
    assert "<script>" not in report
    assert "&lt;script&gt;" in report
