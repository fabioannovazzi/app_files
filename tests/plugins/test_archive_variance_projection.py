"""Verify actual Variance output against its selected source records."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from tests.plugins.test_archive_automatic_reporting import (
    archive_core,
    archive_script_imports,
    client_case,
    reporting_runtime,
    start,
)

SCRIPTS = Path(__file__).resolve().parents[2] / "plugins/variance-analysis/scripts"


def test_variance_targeted_inspection_counts_only_delivered_source_columns(
    archive_core, client_case, tmp_path
):
    from archive_reporting import read_artifact, snapshot_run

    source = tmp_path / "population.csv"
    source.write_text("label,amount,private_note\n" + "Company,123,LOCAL_ONLY\n" * 100)
    client_case.imported = archive_core.import_studio_client_document(
        client_case.client_id,
        source,
        "journal",
        engagement_id=client_case.engagement_id,
        state_dir=client_case.state_dir,
    )
    loaded = start(archive_core, client_case, "variance-analysis")
    artifact = Path(loaded["output_dir"]) / "column-preview.json"
    completed = subprocess.run(
        [
            sys.executable,
            "-B",
            str(SCRIPTS / "inspect_column_values.py"),
            "--input",
            loaded["context"]["input_bindings"][0]["path"],
            "--output",
            str(artifact),
            "--column",
            "amount",
            "--client-engagement",
            str(Path(loaded["run_root"]) / "context.json"),
        ],
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert completed.returncode == 0, completed.stderr
    assert json.loads(completed.stdout) == {"ok": True, "sample_rows": 10}
    before = json.loads(Path(snapshot_run(loaded)["report_path"]).read_text())
    assert before["collection_status"] == "complete", before["errors"]
    assert before["sources"][0]["sent_quantity"] == 0

    returned = read_artifact(loaded, artifact)
    after = json.loads(Path(snapshot_run(loaded)["report_path"]).read_text())

    measured = next(item for item in after["sources"] if item["role"] == "input")
    assert after["collection_status"] == "complete", after["errors"]
    assert measured["source_quantity"] == 100
    assert measured["sent_quantity"] == 10
    assert measured["sent_cells"] == 10
    assert measured["not_sent_quantity"] == 90
    assert measured["not_sent_cells"] == 290
    assert "LOCAL_ONLY" not in json.dumps(returned)


def test_variance_drilldown_preserves_noncontiguous_source_positions(
    archive_core, client_case, tmp_path, monkeypatch
):
    from archive_report_store import RunStore
    from archive_reporting import read_artifact, snapshot_run

    from tests.plugins.test_variance_analysis_plugin import load_core

    monkeypatch.syspath_prepend(str(SCRIPTS))
    core = load_core()
    from model_use import extract_source_rows

    source = tmp_path / "sales.csv"
    source.write_text(
        "product,category,period,sales,units,discount,cogs\n"
        "A,Cat,2023,100,10,5,60\n"
        "B,Dog,2023,200,20,10,120\n"
        "A,Cat,2024,150,12,6,84\n"
        "B,Dog,2024,180,18,12,110\n"
    )
    client_case.imported = archive_core.import_studio_client_document(
        client_case.client_id,
        source,
        "journal",
        engagement_id=client_case.engagement_id,
        state_dir=client_case.state_dir,
    )
    loaded = start(archive_core, client_case, "variance-analysis")
    input_path = Path(loaded["context"]["input_bindings"][0]["path"])
    output = Path(loaded["output_dir"])
    core.run_variance_analysis(
        input_path,
        output,
        language="en",
        artifact_mode="data_only",
        waterfall_chart=False,
        waterfall_small_multiples=False,
        root_cause_bridge=False,
        root_cause_bridge_alternative_sweep=False,
        total_by_dimension_bridge=False,
        exploded_variance_bridge=False,
    )
    prepared = extract_source_rows(
        manifest_path=output / "model_use_manifest.json",
        input_path=input_path,
        recipe_path=output / "used_recipe.json",
        reason="Check product A source amounts.",
        where=["product=A"],
        columns=["sales"],
    )
    # The third source row was already sent: the drilldown must not count it twice.
    read_artifact(loaded, input_path, offset=2, limit=1, columns=[3])

    returned = read_artifact(loaded, Path(prepared["artifact_path"]))
    report = json.loads(Path(snapshot_run(loaded)["report_path"]).read_text())

    measured = next(item for item in report["sources"] if item["role"] == "input")
    assert json.loads(returned["data"]["rows"][0][0])["rows"] == [
        {"sales": 100},
        {"sales": 150},
    ]
    assert report["collection_status"] == "complete", report["errors"]
    assert measured["source_quantity"] == 4
    assert measured["sent_quantity"] == 2
    assert measured["sent_cells"] == 2
    assert measured["not_sent_quantity"] == 2
    assert measured["not_sent_cells"] == 26
    assert (
        len(
            [
                e
                for e in RunStore(Path(loaded["run_root"])).events()
                if e["kind"] == "vera_send" and e["channel"] == "archive_read"
            ]
        )
        == 2
    )
