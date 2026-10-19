"""Count producer-selected source cells only when Vera actually returns the packet."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from openpyxl import Workbook

from tests.plugins.test_archive_automatic_reporting import (
    archive_core,
    archive_script_imports,
    client_case,
    reporting_runtime,
    start,
)
from tests.plugins.test_report_builder_plugin import load_core


@pytest.mark.parametrize("kind", ["csv", "xlsx"])
@pytest.mark.parametrize("send", [False, True])
def test_report_builder_preview_counts_only_sent_unredacted_source_cells(
    archive_core,
    client_case,
    tmp_path,
    kind,
    send,
):
    from archive_reporting import read_artifact, snapshot_run

    source = tmp_path / ("population." + kind)
    if kind == "csv":
        source.write_text("label,amount\n" + "Company,123\n" * 1000)
    else:
        workbook = Workbook()
        hidden = workbook.active
        hidden.title = "Private"
        hidden.sheet_state = "hidden"
        hidden.append(["PRIVATE_SOURCE"])
        sheet = workbook.create_sheet("Population")
        sheet.append(["label", "amount"])
        for _ in range(1000):
            sheet.append(["Company", 123])
        workbook.save(source)
    imported = archive_core.import_studio_client_document(
        client_case.client_id,
        source,
        "journal",
        engagement_id=client_case.engagement_id,
        state_dir=client_case.state_dir,
    )
    client_case.imported = imported
    loaded = start(archive_core, client_case, "report-builder")
    output = Path(loaded["output_dir"])
    load_core().inspect_inputs(
        Path(loaded["context"]["input_bindings"][0]["path"]), output
    )

    if send:
        read_artifact(loaded, output / "inspection.json")
    snapshot = snapshot_run(loaded)

    report = json.loads(Path(snapshot["report_path"]).read_text())
    measured = next(item for item in report["sources"] if item["role"] == "input")
    assert report["collection_status"] == "complete", report["errors"]
    assert measured["source_quantity"] == (1000 if kind == "csv" else 1002)
    assert measured["sent_quantity"] == ((8 if kind == "csv" else 9) if send else 0)
    assert measured["sent_cells"] == ((8 if kind == "csv" else 10) if send else 0)
    assert measured["not_sent_quantity"] == (
        (992 if kind == "csv" else 993) if send else measured["source_quantity"]
    )


def test_empty_read_of_prepared_packet_does_not_count_its_source_rows(
    archive_core, client_case, tmp_path
):
    from archive_reporting import read_artifact, snapshot_run

    source = tmp_path / "population.csv"
    source.write_text("label,amount\nCompany,123\n")
    client_case.imported = archive_core.import_studio_client_document(
        client_case.client_id,
        source,
        "journal",
        engagement_id=client_case.engagement_id,
        state_dir=client_case.state_dir,
    )
    loaded = start(archive_core, client_case, "report-builder")
    output = Path(loaded["output_dir"])
    load_core().inspect_inputs(
        Path(loaded["context"]["input_bindings"][0]["path"]), output
    )

    result = read_artifact(loaded, output / "inspection.json", limit=0)
    report = json.loads(Path(snapshot_run(loaded)["report_path"]).read_text())

    assert result["data"]["rows"] == []
    assert report["collection_status"] == "complete", report["errors"]
    assert (
        next(item for item in report["sources"] if item["role"] == "input")[
            "sent_quantity"
        ]
        == 0
    )


def test_report_builder_expansion_adds_exact_cells_without_double_counting(
    archive_core, client_case, tmp_path
):
    from archive_reporting import read_artifact, snapshot_run

    source = tmp_path / "population.csv"
    source.write_text("label,amount\n" + "Company,123\n" * 1000)
    client_case.imported = archive_core.import_studio_client_document(
        client_case.client_id,
        source,
        "journal",
        engagement_id=client_case.engagement_id,
        state_dir=client_case.state_dir,
    )
    loaded = start(archive_core, client_case, "report-builder")
    output = Path(loaded["output_dir"])
    core = load_core()
    core.inspect_inputs(Path(loaded["context"]["input_bindings"][0]["path"]), output)
    control_path = output / "inspection_control.json"
    control = json.loads(control_path.read_text())
    packet = core.build_model_context_expansion(
        control,
        table_id=control["tables"][0]["table_id"],
        header_row=1,
        columns=["amount"],
        row_start=21,
        row_limit=2,
        purpose="Synthetic exact-column inspection",
    )
    path = output / "expansion.json"
    core.write_json(path, packet)
    core.register_expansion_projection(path, control_path, packet)

    read_artifact(loaded, output / "inspection.json")
    read_artifact(loaded, path)
    read_artifact(loaded, path)
    report = json.loads(Path(snapshot_run(loaded)["report_path"]).read_text())

    measured = next(item for item in report["sources"] if item["role"] == "input")
    assert report["collection_status"] == "complete", report["errors"]
    assert measured["sent_quantity"] == 10
    assert measured["sent_cells"] == 10
    assert measured["not_sent_quantity"] == 990
