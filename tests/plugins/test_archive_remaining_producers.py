"""Actual selected producer paths, with real Archive contexts and fictional inputs."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from tests.conftest import vera_workflow_workspace
from tests.plugins.test_archive_automatic_reporting import (
    archive_core,
    archive_script_imports,
    client_case,
    reporting_runtime,
    start,
)
from tests.plugins.test_archive_native_emissions import assert_native_send
from tests.plugins.test_vera_native_archive_lifecycle import rpc_program
from tests.plugins.test_vera_native_passive_audit import audit_workspace
from tests.plugins.test_vera_native_passive_service import passive_service, prepare
from tests.plugins.test_vera_native_workspace import (
    archived_review_binding,
    configure,
    open_items,
    workspace_module,
)

ROOT = Path(__file__).resolve().parents[2]


def test_open_item_selected_context_records_exact_mcp_response(tmp_path, monkeypatch):
    output, _ = open_items._portable_audit_transaction_case(tmp_path)
    binding, root_output = archived_review_binding(output, "open-item-reconciliation")
    configure(monkeypatch, tmp_path, [binding])
    assert_native_send((workspace_module(), binding, root_output), None)


def test_passive_selected_population_member_records_only_model_response(
    passive_service,
):
    from archive_report_store import RunStore, digest

    work, _, env, fields, _ = passive_service
    store = RunStore(work.output.parent)
    previous = {event["event_id"] for event in store.events()}
    result = rpc_program(
        env,
        prepare(fields)
        + """
const view=payload(call('vera_workspace_passive_view',{work_ref:qualified.work_ref,revision:qualified.revision,source_ref:qualified.data.selection.source_ref,view:'population'}));
const result=call('vera_workspace_passive_explain',{work_ref:view.work_ref,revision:view.revision,source_ref:view.data.selection.source_ref,view:'population',item_id:view.items[0].id});
""",
    )
    assert result.get("isError") is not True, result
    assert result["structuredContent"]["untrusted_evidence"]
    events = [
        e
        for e in store.events()
        if e["event_id"] not in previous and e["kind"] == "vera_send"
    ]
    assert len(events) == 1
    assert events[0]["channel"] == "mcp:passive-invoice-audit"
    assert events[0]["response_sha256"] == digest(result)


def test_fatture_xml_actual_cli_records_with_selected_archive_identity(
    vera_workflow_workspace, tmp_path, monkeypatch
):
    from archive_report_store import RunStore, digest

    scripts = ROOT / "plugins/passive-invoice-audit/scripts"
    monkeypatch.syspath_prepend(str(scripts))
    import importlib.util

    spec = importlib.util.spec_from_file_location(
        "xml_reporting_fixture", scripts.parent / "tests/test_passive_invoice_audit.py"
    )
    fixture = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(fixture)
    source = tmp_path / "fictional.xml"
    fixture._write_invoice(source)
    case = vera_workflow_workspace(
        "fatture-xml-check", input_files={source.name: source.read_text()}
    )
    completed = subprocess.run(
        [
            sys.executable,
            str(
                ROOT
                / "plugins/client-file-preparation/scripts/build_file_preparation_outputs.py"
            ),
            str(case["input_dir"]),
            "--client-engagement",
            str(case["context_path"]),
            "--year",
            "2026",
            "--out",
            str(case["output_dir"]),
        ],
        capture_output=True,
        text=True,
        timeout=60,
    )

    assert completed.returncode == 0, completed.stderr
    assert (case["output_dir"] / "extracted/fatture_xml.jsonl").is_file()
    events = [
        e
        for e in RunStore(case["output_dir"].parent).events()
        if e.get("channel") == "cli:client-file-preparation"
    ]
    assert len(events) == 1
    assert events[0]["response_sha256"] == digest(
        {
            "stdout": completed.stdout,
            "stderr": completed.stderr,
        }
    )
    binding, output = archived_review_binding(case["output_dir"], "fatture-xml-check")
    configure(monkeypatch, tmp_path, [binding])
    assert_native_send((workspace_module(), binding, output), None)


def test_local_government_report_keeps_run_identity_in_native_workspace(
    vera_workflow_workspace, tmp_path, monkeypatch
):
    from tests.plugins.test_report_builder_plugin import load_core

    case = vera_workflow_workspace(
        "report-enti-locali", input_files={"budget.csv": "line,amount\nA,10\nB,20\n"}
    )
    load_core().build_report(
        case["input_paths"][0],
        case["output_dir"],
        report_type="local_government_review",
        language="it",
        document_language="auto",
        run_id=case["run_id"],
        client_engagement=case["context"],
    )
    binding, output = archived_review_binding(case["output_dir"], "report-enti-locali")
    configure(monkeypatch, tmp_path, [binding])
    assert_native_send((workspace_module(), binding, output), "report_section")


def test_centrale_rischi_actual_pdf_inspection_records_its_cli_output(
    archive_core, client_case, tmp_path
):
    from archive_report_store import RunStore, digest

    from tests.plugins.test_centrale_rischi_review import _write_native_pdf_fixture

    source = tmp_path / "fictional-cr.pdf"
    _write_native_pdf_fixture(source)
    client_case.imported = archive_core.import_studio_client_document(
        client_case.client_id,
        source,
        "source",
        engagement_id=client_case.engagement_id,
        state_dir=client_case.state_dir,
    )
    loaded = start(archive_core, client_case, "centrale-rischi-review")
    output = Path(loaded["output_dir"])
    completed = subprocess.run(
        [
            sys.executable,
            str(ROOT / "plugins/centrale-rischi-review/scripts/inspect_inputs.py"),
            "--input",
            loaded["context"]["input_bindings"][0]["path"],
            "--client-engagement",
            loaded["context_path"],
            "--output-dir",
            str(output),
        ],
        capture_output=True,
        text=True,
        timeout=60,
    )

    assert completed.returncode == 0, completed.stderr
    assert (output / "centrale_rischi_normalized.xlsx").is_file()
    events = [
        e
        for e in RunStore(Path(loaded["run_root"])).events()
        if e.get("channel") == "cli:centrale-rischi-review"
    ]
    assert len(events) == 1
    assert events[0]["response_sha256"] == digest(
        {
            "stdout": completed.stdout,
            "stderr": completed.stderr,
        }
    )
