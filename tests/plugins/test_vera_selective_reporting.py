from __future__ import annotations

import json
from pathlib import Path

import pytest

from tests.plugins.test_vera_customer_folder_ledger import (
    archive_core,
    archive_script_imports,
    client_case,
)
from tests.plugins.test_vera_model_data_report import _load_module, _reduced_request

ROOT = Path(__file__).resolve().parents[2]


def _start(archive_core, case, workflow="variance-analysis"):
    prepared = archive_core.prepare_studio_client_workflow(
        case.engagement_id,
        workflow,
        input_ids=[case.imported["input_id"]],
        state_dir=case.state_dir,
    )
    run_id = prepared["run"]["run_id"]
    archive_core.start_studio_client_workflow(
        case.client_id, case.engagement_id, run_id, state_dir=case.state_dir
    )
    output = Path(prepared["client_engagement"]["output_dir"])
    (output / "result.txt").write_text("Reviewed synthetic calculation\n")
    return run_id, output


def _evidence(output, run_id):
    request = _reduced_request()
    request["run_id"] = run_id
    (output / "mapping_payload.json").write_text('{"rows":10}\n')
    (output / "model_data_report_input.json").write_text(json.dumps(request))
    (output / "model_data_report_options.json").write_text('{"local_only":true}')
    return request


def _declarations(output):
    return [
        {
            "artifact_id": "result." + path.name.replace("_", "-"),
            "path": path.name,
            "purpose": "Retain synthetic calculation evidence.",
            "audience": "internal",
            "media_type": (
                "application/json" if path.suffix == ".json" else "text/plain"
            ),
        }
        for path in sorted(output.iterdir())
        if path.name
        not in {
            "model_data_report_input.json",
            "model_data_report_options.json",
            "model_data_report.json",
            "model_data_report.md",
            "privacy_contract.json",
        }
    ]


def _finish(archive_core, case, run_id, output):
    return archive_core.finalize_studio_client_workflow(
        case.client_id,
        case.engagement_id,
        run_id,
        _declarations(output),
        state_dir=case.state_dir,
    )


def test_fixed_scope_matches_published_catalogue_and_excludes_shared_intake():
    from selective_reporting import REPORT_PIPELINES, report_pipeline

    catalogue = json.loads(
        (ROOT / "plugins/vera/usage/pipelines.json").read_text(encoding="utf-8")
    )
    assert len(REPORT_PIPELINES) == 13
    assert set(catalogue["model_data_reporting"]["pipelines"]) == REPORT_PIPELINES
    assert report_pipeline("client-file-preparation") is None
    assert report_pipeline("new-client") is None
    assert report_pipeline("fatture-xml-check") == "fatture-xml-check"
    assert report_pipeline("check-entries") == "vouching"


def test_only_selected_public_function_pages_describe_archive_reporting():
    public = json.loads(
        (ROOT / "static/shared/privacy-contracts/vera.json").read_text(encoding="utf-8")
    )
    selected = {
        page
        for page, data in public["pages"].items()
        if any(
            paragraph.startswith("Studio Archive delimita")
            for paragraph in data["copy"].get("it", [])
        )
    }
    assert selected == {
        "journal-bank-reconciliation",
        "riconciliazione-partite",
        "journal-sampling",
        "check-entries",
        "fatture-xml-check",
        "passive-invoice-audit",
        "centrale-rischi-review",
        "report-builder",
        "report-enti-locali",
        "management-control-pack",
        "variance-analysis",
        "agenzia-acquisition",
        "archive-organization",
    }
    for page in selected:
        assert all(
            any(
                "Studio Archive" in paragraph
                for paragraph in public["pages"][page]["copy"][locale]
            )
            for locale in ("it", "en", "fr", "de", "es")
        )


def test_other_products_keep_their_existing_archive_report_requirement(
    archive_core, client_case, monkeypatch
):
    monkeypatch.setattr(
        archive_core.ledger._reporting_runtime(),
        "selective_reporting_enabled",
        lambda: False,
    )
    run_id, output = _start(archive_core, client_case, "financial-analysis")

    with pytest.raises(archive_core.ArchiveError, match="requires both"):
        _finish(archive_core, client_case, run_id, output)


def test_archive_finalization_builds_bound_report_without_a_separate_trigger(
    archive_core, client_case
):
    run_id, output = _start(archive_core, client_case)
    _evidence(output, run_id)

    result = _finish(archive_core, client_case, run_id, output)

    report = json.loads((output / "model_data_report.json").read_text(encoding="utf-8"))
    assert report["run_id"] == run_id
    assert result["reporting"]["status"] == "available"
    assert result["reporting"]["started_at"]
    assert result["reporting"]["finished_at"] is None
    assert "model_data_report.md" in {
        a["path"] for a in result["artifact_manifest"]["artifacts"]
    }
    assert result["status"] == "ready_for_review"


def test_excluded_pipeline_completes_without_report_or_receipt(
    archive_core, client_case
):
    run_id, output = _start(archive_core, client_case, "financial-analysis")

    result = _finish(archive_core, client_case, run_id, output)

    assert result["reporting"]["reason"] == "pipeline_not_selected"
    assert not (output / "model_data_report.json").exists()
    assert not (output / "model_data_receipt_request.json").exists()
    assert result["status"] == "ready_for_review"


@pytest.mark.parametrize("evidence", ["missing", "all_visible"])
def test_agent_authored_measurements_do_not_replace_vera_sending_records(
    archive_core, client_case, evidence
):
    run_id, output = _start(archive_core, client_case)
    if evidence == "all_visible":
        request = _evidence(output, run_id)
        phase = request["phases"][0]
        phase["outcome"] = "full_context_required"
        phase["model_visible"] = phase["source_extent"]
        phase["remained_local"] = []
        (output / "model_data_report_input.json").write_text(json.dumps(request))

    result = _finish(archive_core, client_case, run_id, output)

    report = json.loads((output / "model_data_report.json").read_text(encoding="utf-8"))
    assert result["reporting"]["status"] == "available"
    assert report["collection_status"] == "complete"
    assert report["sources"][0]["sent_quantity"] == 0
    assert report["sources"][0]["not_sent_quantity"] == 1


def test_authored_foreign_run_evidence_cannot_change_automatic_report(
    archive_core, client_case
):
    run_id, output = _start(archive_core, client_case)
    _evidence(output, "run_" + "a" * 24)

    _finish(archive_core, client_case, run_id, output)
    report = json.loads((output / "model_data_report.json").read_text(encoding="utf-8"))
    assert report["run_id"] == run_id
    assert report["collection_status"] == "complete"
    assert report["sources"][0]["sent_quantity"] == 0


def test_direct_report_command_refuses_an_unbound_output(tmp_path, capsys):
    module = _load_module(enforce_scope=True)
    _evidence(tmp_path, "run_" + "a" * 24)

    code = module.main(
        [
            "build",
            "--input",
            str(tmp_path / "model_data_report_input.json"),
            "--output-dir",
            str(tmp_path),
            "--local-only",
        ]
    )

    assert code == 2
    assert "Archive" in capsys.readouterr().err
    assert not (tmp_path / "model_data_report.json").exists()


def test_direct_excluded_report_command_skips_without_network(tmp_path, capsys):
    module = _load_module(enforce_scope=True)
    request = _evidence(tmp_path, "run_" + "a" * 24)
    request["workflow_id"] = "quesito-legale-fiscale"
    (tmp_path / "model_data_report_input.json").write_text(json.dumps(request))

    code = module.main(
        [
            "build",
            "--input",
            str(tmp_path / "model_data_report_input.json"),
            "--output-dir",
            str(tmp_path),
        ]
    )

    assert code == 0
    assert json.loads(capsys.readouterr().out)["reason"] == "pipeline_not_selected"
    assert not (tmp_path / "model_data_report.json").exists()


@pytest.mark.parametrize(
    "workflow,engine",
    [
        ("fatture-xml-check", "client-file-preparation"),
        ("report-enti-locali", "report-builder"),
        ("agenzia-acquisition", "agenzia-acquisition"),
        ("journal-bank-reconciliation", "journal-bank-reconciliation"),
        ("open-item-reconciliation", "open-item-reconciliation"),
        ("journal-sampling", "journal-sampling"),
        ("check-entries", "check-entries"),
        ("passive-invoice-audit", "passive-invoice-audit"),
        ("centrale-rischi-review", "centrale-rischi-review"),
        ("report-builder", "report-builder"),
        ("management-control-pack", "management-control-pack"),
        ("variance-analysis", "variance-analysis"),
        ("archive-organization", "archive-organization"),
    ],
)
def test_selected_entrypoints_have_exact_archive_lifecycle(
    archive_core, client_case, workflow, engine
):
    run_id, output = _start(archive_core, client_case, workflow)
    from vera_assurance import load_client_engagement_context_file

    context = load_client_engagement_context_file(
        output.parent / "context.json", expected_workflow_id=engine
    )

    assert context["workflow_id"] == workflow
    assert context["run_id"] == run_id
    request = _evidence(output, run_id)
    request["workflow_id"] = workflow
    (output / "model_data_report_input.json").write_text(json.dumps(request))
    result = _finish(archive_core, client_case, run_id, output)
    assert result["reporting"]["status"] == "available"


def test_failed_run_report_is_preserved_when_the_same_run_resumes(
    archive_core, client_case
):
    run_id, output = _start(archive_core, client_case)
    _evidence(output, run_id)
    archive_core.fail_studio_client_workflow(
        client_case.client_id,
        client_case.engagement_id,
        run_id,
        "synthetic interruption",
        state_dir=client_case.state_dir,
    )
    previous = (output / "model_data_report.json").read_bytes()

    resumed = archive_core.start_studio_client_workflow(
        client_case.client_id,
        client_case.engagement_id,
        run_id,
        state_dir=client_case.state_dir,
    )

    retained = list(
        (output.parent / "reporting/history").glob("*/model_data_report.json")
    )
    assert resumed["run"]["run_id"] == run_id
    assert retained[0].read_bytes() == previous
    current = json.loads(
        (output / "model_data_report.json").read_text(encoding="utf-8")
    )
    assert current["report_revision"] == 2
    assert current["outcome"] == "running"


@pytest.mark.parametrize("later_outcome", ["full_context_required", "not_measurable"])
def test_later_full_or_unknown_send_cannot_reuse_an_earlier_reduction(
    archive_core, client_case, later_outcome
):
    run_id, output = _start(archive_core, client_case)
    from archive_reporting import read_artifact, record_send

    loaded = archive_core.ledger.load_run(
        client_case.client_root, client_case.engagement_id, run_id
    )
    source = Path(loaded["context"]["input_bindings"][0]["path"])
    read_artifact(loaded, source, limit=0)
    if later_outcome == "not_measurable":
        record_send(
            Path(loaded["run_root"]),
            "Unmapped derived data",
            channel="cli:variance-analysis",
        )
    else:
        read_artifact(loaded, source)

    result = _finish(archive_core, client_case, run_id, output)

    report = json.loads((output / "model_data_report.json").read_text(encoding="utf-8"))
    assert result["reporting"]["status"] == "available"
    expected = {
        "full_context_required": ("complete", 0),
        "not_measurable": ("incomplete", None),
    }[later_outcome]
    assert (
        report["collection_status"],
        report["sources"][0]["not_sent_quantity"],
    ) == expected


def test_acquisition_worker_uses_a_client_bound_run_and_waits_for_model_review(
    archive_core, client_case, monkeypatch, tmp_path
):
    monkeypatch.syspath_prepend(str(ROOT / "plugins/browser-automation/scripts"))
    from ade_acquisition import archive_runs, contracts, disclosure

    monkeypatch.setattr(archive_runs, "_archive", lambda: archive_core)
    real_state_dir = archive_core._state_dir
    monkeypatch.setattr(
        archive_core,
        "_state_dir",
        lambda value=None: real_state_dir(value or client_case.state_dir),
    )
    plan = contracts.Plan.parse(
        {
            "schema_version": "vera-agenzia-plan/v1",
            "clients": [
                {
                    "name": "Zecca SPA",
                    "tax_code": "01234567890",
                    "vat_number": "01234567890",
                    "archive_client_id": client_case.client_id,
                    "archive_engagement_id": client_case.engagement_id,
                }
            ],
            "date_from": "2026-01-01",
            "date_to": "2026-01-31",
            "operations": ["ricevute"],
        }
    )
    worker = tmp_path / "worker"
    worker.mkdir()
    archive_runs.prepare_runs(worker, plan)
    binding = json.loads((worker / "archive-runs.json").read_text(encoding="utf-8"))[
        "01234567890"
    ]
    (worker / "events.jsonl").write_text(
        json.dumps({"client": "01234567890", "kind": "invoice", "status": "downloaded"})
        + "\n"
    )
    disclosure.write_disclosure(worker, 1)

    archive_runs.finish_runs(worker, {"state": "complete"})

    loaded = archive_core.ledger.load_run(
        client_case.client_root, client_case.engagement_id, binding["run_id"]
    )
    output = Path(loaded["output_dir"])
    report = json.loads((output / "model_data_report.json").read_text(encoding="utf-8"))
    assert loaded["run"]["status"] == "running"
    assert report["run_id"] == binding["run_id"]
    assert report["finished_at"] is None
    assert not (output / "model_data_report_input.json").exists()


def test_finalization_retry_returns_same_report_without_rewriting_it(
    archive_core, client_case
):
    run_id, output = _start(archive_core, client_case)
    _evidence(output, run_id)
    _finish(archive_core, client_case, run_id, output)
    previous = (output / "model_data_report.json").read_bytes()

    replay = _finish(archive_core, client_case, run_id, output)

    assert (output / "model_data_report.json").read_bytes() == previous
    assert replay["reporting"]["display_markdown"] == (
        output / "model_data_report.md"
    ).read_text(encoding="utf-8")


def test_resuming_review_ready_run_preserves_the_old_seal_outside_active_outputs(
    archive_core, client_case
):
    run_id, output = _start(archive_core, client_case)
    _evidence(output, run_id)
    _finish(archive_core, client_case, run_id, output)

    archive_core.start_studio_client_workflow(
        client_case.client_id,
        client_case.engagement_id,
        run_id,
        state_dir=client_case.state_dir,
    )

    assert not (output.parent / "artifact_manifest.json").exists()
    assert (
        len(
            list((output.parent / "reporting-history").glob("*/artifact_manifest.json"))
        )
        == 1
    )
    request = _evidence(output, run_id)
    request["professional_purpose"] = "Repeat review with cumulative evidence."
    (output / "model_data_report_input.json").write_text(json.dumps(request))
    assert (
        _finish(archive_core, client_case, run_id, output)["reporting"]["status"]
        == "available"
    )
