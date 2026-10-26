"""Source coordinates exist before the first semantic send, even if output fails."""

from __future__ import annotations

from pathlib import Path

import pytest

from tests.open_item_reconciliation.test_audit_assurance import (
    SCRIPTS,
    load_script_module,
)
from tests.open_item_reconciliation.test_reviewed_tabular_adapter import spec
from tests.plugins.test_archive_automatic_reporting import (
    archive_core,
    archive_script_imports,
    client_case,
    reporting_runtime,
)

__all__: list[str] = []


@pytest.mark.parametrize("fail_production", [False, True])
def test_semantic_submission_has_coordinates_before_document_production(
    archive_core, client_case, monkeypatch, tmp_path, fail_production
):
    from archive_report_store import RunStore
    from archive_reporting import snapshot_run

    runner = load_script_module(
        "semantic_reporting_raw", SCRIPTS / "raw_input_runner.py"
    )
    import semantic_resolution

    sources = {
        "population.csv": "InvoiceX;DateX;ValueX;PartyX\nF001;01/07/2026;915.00;Cliente Alfa\n",
        "bank.csv": "MovementX;PostedX;ValueX;PartyX;DescriptionX\nT001;13/07/2026;915.00;Cliente Alfa;bonifico a vostro favore\n",
    }
    input_ids = []
    for name, text in sources.items():
        path = tmp_path / name
        path.write_text(text)
        imported = archive_core.import_studio_client_document(
            client_case.client_id,
            path,
            "source",
            engagement_id=client_case.engagement_id,
            state_dir=client_case.state_dir,
        )
        input_ids.append(imported["input_id"])
    prepared = archive_core.prepare_studio_client_workflow(
        client_case.engagement_id,
        "open-item-reconciliation",
        input_ids=input_ids,
        purpose="synthetic semantic reporting regression",
        state_dir=client_case.state_dir,
    )
    run_id = prepared["run"]["run_id"]
    archive_core.start_studio_client_workflow(
        client_case.client_id,
        client_case.engagement_id,
        run_id,
        state_dir=client_case.state_dir,
    )
    loaded = archive_core.ledger.load_run(
        client_case.client_root, client_case.engagement_id, run_id
    )
    choices = {}
    for binding in loaded["context"]["input_bindings"]:
        path = Path(binding["path"])
        population = path.name == "population.csv"
        choice = spec(path, "open_items" if population else "bank_statement")
        choice["perimeter"]["party_ref"] = None
        choice["tabular"]["last_data_row"] = 2
        choice["tabular"]["columns"]["party_ref"] = "PartyX"
        if not population:
            del choice["tabular"]["columns"]["document_no"]
            del choice["tabular"]["columns"]["document_date"]
            choice["tabular"]["columns"]["description"] = "DescriptionX"
            choice["tabular"]["columns"]["source_record_id"] = "MovementX"
        choices[str(path)] = choice

    capsule = semantic_resolution._capsule()
    monkeypatch.setattr(capsule, "discover_worker_selection", lambda *_: {})

    def worker(**kwargs):
        capsule._record_model_submission(
            kwargs["output_dir"],
            prompt=kwargs["prompt"],
            output_schema=kwargs["output_schema"],
            model="test-model",
            workflow_id=kwargs["workflow_id"],
            source_records=kwargs["source_records"],
        )
        raise ValueError("Synthetic worker abstention")

    monkeypatch.setattr(capsule, "run_isolated_native_worker", worker)
    extract = runner.extract_normalized_records

    def checked_extract(*args, **kwargs):
        extracted = extract(*args, **kwargs)
        assert extracted["extraction_errors"] == []
        return extracted

    monkeypatch.setattr(runner, "extract_normalized_records", checked_extract)
    if fail_production:

        def failed_output(**kwargs):
            raise ValueError("Synthetic document failure after submission")

        monkeypatch.setattr(runner, "build_reconciliation_artifacts", failed_output)

    def run():
        return runner.run_raw_input_reconciliation(
            input_dir=loaded["context"]["input_dir"],
            prepared_client_engagement=loaded["context"],
            assumptions={
                "assurance_run_date": "2026-10-26",
                "scope_year": 2026,
                "cutoff_date": "2026-07-01",
                "post_cutoff_events_excluded": False,
                "amount_tolerance": "0.00",
                "reviewed_source_decisions": choices,
            },
            output_subdirectory="reconciliation",
        )

    if fail_production:
        with pytest.raises(ValueError, match="Synthetic document failure"):
            run()
    else:
        run()

    events = RunStore(Path(loaded["run_root"])).events()
    submissions = [
        event
        for event in events
        if event["kind"] == "vera_send" and event["channel"].startswith("model_worker:")
    ]
    assert len(submissions) == 1
    assert submissions[0]["unmapped"] is False
    assert len(submissions[0]["selections"]) == 2
    snapshot = snapshot_run(loaded)
    import json

    report = json.loads(Path(snapshot["report_path"]).read_text())
    assert report["collection_status"] == "complete"
    assert report["errors"] == []
    assert [source["sent_quantity"] for source in report["sources"]] == [1, 1]
