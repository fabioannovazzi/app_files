from __future__ import annotations

import json
import shlex
import subprocess
import sys
from pathlib import Path

import pytest

from tests.plugins.test_vera_customer_folder_ledger import (
    archive_core,
    archive_script_imports,
    client_case,
)
from tests.plugins.test_vera_studio_archive_component import isolated_mcp_launcher

PIPELINES = (
    "journal-bank-reconciliation",
    "open-item-reconciliation",
    "journal-sampling",
    "vouching",
    "fatture-xml-check",
    "purchase-invoice-review",
    "centrale-rischi-review",
    "financial-report-builder",
    "report-enti-locali",
    "management-control-pack",
    "variance-analysis",
    "agenzia-acquisition",
    "archive-organization",
)
USER_ID = "397d2de9-0ec5-4db8-a01a-b91ae41d13b0"


@pytest.fixture(autouse=True)
def reporting_runtime(tmp_path, monkeypatch, archive_script_imports):
    import archive_report_receipt
    import archive_reporting

    original_stamp = archive_report_receipt.stamp_report

    monkeypatch.setenv("VERA_REPORTING_STATE_DIR", str(tmp_path / "reporting-state"))
    monkeypatch.setenv("CODEX_THREAD_ID", "test-session")
    monkeypatch.setenv(
        "VERA_STUDIO_ARCHIVE_SESSION_ID", str(tmp_path / "private-state")
    )
    monkeypatch.setattr(archive_reporting, "_identity", lambda: USER_ID)
    monkeypatch.setattr(
        archive_report_receipt,
        "stamp_report",
        lambda path: {"status": "pending", "reason": "offline_test"},
    )
    yield original_stamp


def start(core, case, workflow="variance-analysis"):
    workflow = {
        "vouching": "check-entries",
        "purchase-invoice-review": "passive-invoice-audit",
        "financial-report-builder": "report-builder",
    }.get(workflow, workflow)
    prepared = core.prepare_studio_client_workflow(
        case.engagement_id,
        workflow,
        input_ids=[case.imported["input_id"]],
        state_dir=case.state_dir,
    )
    run_id = prepared["run"]["run_id"]
    core.start_studio_client_workflow(
        case.client_id, case.engagement_id, run_id, state_dir=case.state_dir
    )
    return core.ledger.load_run(case.client_root, case.engagement_id, run_id)


def read_observed(loaded, **selection):
    from archive_report_hook import handle
    from archive_reporting import read_artifact

    path = Path(loaded["context"]["input_bindings"][0]["path"])
    packet = read_artifact(loaded, path, **selection)
    handle(
        {
            "hook_event_name": "PostToolUse",
            "session_id": "test-session",
            "tool_use_id": packet["vera_reporting"]["token"],
            "tool_name": "mcp__veraStudioArchive__read_studio_run_artifact",
            "tool_input": {"run_id": loaded["run"]["run_id"]},
            "tool_response": packet,
        }
    )


def finish(core, case, loaded):
    output = Path(loaded["output_dir"])
    (output / "result.txt").write_text("Local professional result\n")
    core.finalize_studio_client_workflow(
        case.client_id,
        case.engagement_id,
        loaded["run"]["run_id"],
        [
            {
                "artifact_id": "result",
                "path": "result.txt",
                "purpose": "Professional result",
                "audience": "review",
                "media_type": "text/plain",
            }
        ],
        state_dir=case.state_dir,
    )
    core.complete_studio_client_workflow(
        case.client_id,
        case.engagement_id,
        loaded["run"]["run_id"],
        state_dir=case.state_dir,
    )
    return json.loads((output / "model_data_report.json").read_text())


@pytest.mark.parametrize("workflow", PIPELINES)
def test_selected_archive_run_always_creates_report_at_start_and_terminal_write(
    archive_core, client_case, workflow
):
    loaded = start(archive_core, client_case, workflow)
    output = Path(loaded["output_dir"])
    initial = json.loads((output / "model_data_report.json").read_text())
    assert initial["outcome"] == "running"
    assert initial["user_id"] == USER_ID
    assert not (output / "model_data_report_input.json").exists()

    report = finish(archive_core, client_case, loaded)

    assert report["outcome"] == "completed"
    assert report["run_id"] == loaded["run"]["run_id"]
    assert report["collection_status"] == "incomplete"
    assert report["sources"][0]["remaining_local"] is None
    archive_core.ledger.validate_run_artifacts(
        client_case.client_root, client_case.engagement_id, report["run_id"]
    )


def test_full_exposure_still_creates_report_and_zero_local_remainder(
    archive_core, client_case
):
    loaded = start(archive_core, client_case)
    read_observed(loaded)

    report = finish(archive_core, client_case, loaded)

    assert report["collection_status"] == "complete"
    assert report["sources"][0]["observed_quantity"] == 1
    assert report["sources"][0]["remaining_local"] == 0


@pytest.mark.parametrize("terminal", ["failed", "cancelled"])
def test_failure_and_cancellation_retain_an_incomplete_report(
    archive_core, client_case, terminal
):
    loaded = start(archive_core, client_case)
    action = (
        archive_core.ledger.fail_run
        if terminal == "failed"
        else archive_core.ledger.cancel_run
    )
    args = [client_case.client_root, client_case.engagement_id, loaded["run"]["run_id"]]
    if terminal == "failed":
        args.append("Synthetic interruption")

    action(*args)

    report = json.loads(
        (Path(loaded["output_dir"]) / "model_data_report.json").read_text()
    )
    assert report["outcome"] == terminal
    assert report["finished_at"] is not None


@pytest.mark.parametrize(
    "workflow", ["financial-analysis", "new-client", "contenzioso-tributario"]
)
def test_unselected_archive_runs_do_not_create_reports(
    archive_core, client_case, workflow
):
    loaded = start(archive_core, client_case, workflow)

    assert not (Path(loaded["output_dir"]) / "model_data_report.json").exists()


def csv_case(core, case, tmp_path):
    source = tmp_path / "population.csv"
    source.write_text(
        "id,amount\n" + "".join(f"{index},{index * 2}\n" for index in range(10000))
    )
    imported = core.import_studio_client_document(
        case.client_id,
        source,
        "journal",
        engagement_id=case.engagement_id,
        state_dir=case.state_dir,
    )
    case.imported = imported
    return start(core, case)


def test_later_whole_file_read_counts_all_ten_thousand_rows_without_double_counting(
    archive_core, client_case, tmp_path
):
    from archive_report_hook import handle

    loaded = csv_case(archive_core, client_case, tmp_path)
    read_observed(loaded, limit=100)
    read_observed(loaded, limit=100)
    path = Path(loaded["context"]["input_bindings"][0]["path"])
    handle(
        {
            "hook_event_name": "PostToolUse",
            "session_id": "test-session",
            "tool_use_id": "later-read",
            "tool_name": "Bash",
            "tool_input": {"command": f"cat '{path}'"},
            "tool_response": {"stdout": path.read_text()},
        }
    )

    report = finish(archive_core, client_case, loaded)

    assert report["sources"][0]["source_quantity"] == 10000
    assert report["sources"][0]["observed_quantity"] == 10000
    assert report["sources"][0]["observed_cells"] == 20000
    assert report["sources"][0]["remaining_local"] == 0


def transcript_line(path, payload):
    with path.open("a") as stream:
        stream.write(json.dumps({"type": "response_item", "payload": payload}) + "\n")


def test_codex_internal_result_is_not_counted_until_emitted_to_model(
    archive_core, client_case, tmp_path
):
    from archive_report_hook import handle
    from archive_report_transcript import attach, refresh
    from archive_reporting import read_artifact, snapshot_run

    loaded = start(archive_core, client_case)
    root = Path(loaded["run_root"])
    transcript = tmp_path / "host.jsonl"
    transcript_line(
        transcript,
        {
            "type": "custom_tool_call",
            "call_id": "outer1",
            "name": "exec",
            "input": "tools.read();",
        },
    )
    attach(root, "test-session", transcript)
    handle(
        {
            "hook_event_name": "PreToolUse",
            "session_id": "test-session",
            "turn_id": "turn1",
            "transcript_path": str(transcript),
            "tool_name": "mcp__read",
            "tool_use_id": "inner1",
            "tool_input": {"run_id": loaded["run"]["run_id"]},
        }
    )
    packet = read_artifact(loaded, Path(loaded["context"]["input_bindings"][0]["path"]))
    handle(
        {
            "hook_event_name": "PostToolUse",
            "session_id": "test-session",
            "turn_id": "turn1",
            "tool_name": "mcp__read",
            "tool_use_id": "inner1",
            "tool_response": packet,
        }
    )
    # Empty output is an internal read. No original data entered model context.
    transcript_line(
        transcript,
        {"type": "custom_tool_call_output", "call_id": "outer1", "output": []},
    )
    refresh(root, "test-session")
    snapshot_run(loaded)
    before = json.loads(
        (Path(loaded["output_dir"]) / "model_data_report.json").read_text()
    )
    assert before["sources"][0]["observed_quantity"] == 0
    transcript_line(
        transcript,
        {
            "type": "custom_tool_call",
            "call_id": "outer2",
            "name": "exec",
            "input": "text(packet);",
        },
    )
    transcript_line(
        transcript,
        {
            "type": "custom_tool_call_output",
            "call_id": "outer2",
            "output": [{"type": "input_text", "text": json.dumps(packet)}],
        },
    )

    refresh(root, "test-session")
    snapshot_run(loaded)

    after = json.loads(
        (Path(loaded["output_dir"]) / "model_data_report.json").read_text()
    )
    assert after["sources"][0]["observed_quantity"] == 1
    assert after["collection_status"] == "complete"


def test_terminal_write_waits_for_outer_result_before_hashing(
    archive_core, client_case, tmp_path
):
    from archive_report_hook import handle
    from archive_report_transcript import attach
    from archive_reporting import read_artifact

    loaded = start(archive_core, client_case)
    root = Path(loaded["run_root"])
    transcript = tmp_path / "host.jsonl"
    transcript_line(
        transcript,
        {
            "type": "custom_tool_call",
            "call_id": "read-and-complete",
            "name": "exec",
            "input": "read(); complete();",
        },
    )
    attach(root, "test-session", transcript)
    packet = read_artifact(loaded, Path(loaded["context"]["input_bindings"][0]["path"]))
    provisional = finish(archive_core, client_case, loaded)
    assert provisional["collection_closed"] is False
    assert not (root / "outputs/model_data_receipt_request.json").exists()
    transcript_line(
        transcript,
        {
            "type": "custom_tool_call_output",
            "call_id": "read-and-complete",
            "output": [{"type": "input_text", "text": json.dumps(packet)}],
        },
    )

    transcript_line(
        transcript,
        {"type": "message", "role": "user", "content": "Unrelated later task"},
    )
    handle({"hook_event_name": "SessionStart", "session_id": "different-session"})

    report = json.loads((root / "outputs/model_data_report.json").read_text())
    assert report["collection_closed"] is True
    assert report["sources"][0]["observed_quantity"] == 1
    assert report["collection_status"] == "complete"
    archive_core.ledger.validate_run_artifacts(
        client_case.client_root, client_case.engagement_id, report["run_id"]
    )


def test_terminal_report_retries_real_authenticated_proof_without_changing_work(
    archive_core, client_case, tmp_path, monkeypatch, reporting_runtime
):
    import archive_report_receipt
    import archive_reporting
    import operational_incidents
    from archive_report_store import Registry

    from tests.modules.run_receipts.test_archive_binding import archive_client

    client, owner, _, receipts, signer = archive_client(tmp_path, monkeypatch)
    monkeypatch.setattr(
        archive_reporting, "_identity", lambda: str(owner.installation_id)
    )
    monkeypatch.setattr(archive_report_receipt, "stamp_report", reporting_runtime)
    monkeypatch.setattr(
        operational_incidents,
        "local_context",
        lambda: {"credentials": owner.model_dump(mode="json")},
    )
    requests = []

    def transport(operation, envelope):
        assert operation == "archive-stamp"
        requests.append(envelope["receipt_request"])
        response = client.post(
            "/api/operational-incidents/archive-stamp", json=envelope
        )
        response.raise_for_status()
        return response.json()

    def offline(operation, envelope):
        raise OSError("Synthetic offline connection")

    monkeypatch.setattr(operational_incidents, "workflow_transport", offline)
    loaded = start(archive_core, client_case)
    read_observed(loaded)
    report = finish(archive_core, client_case, loaded)
    root = Path(loaded["run_root"])
    report_path = root / "outputs/model_data_report.json"
    before = report_path.read_bytes()
    professional_before = (root / "outputs/result.txt").read_bytes()
    assert (
        json.loads((root / "model_data_reporting.json").read_text())["server_receipt"][
            "status"
        ]
        == "pending"
    )
    monkeypatch.setattr(operational_incidents, "workflow_transport", transport)

    archive_report_receipt.retry_pending(Registry())

    receipt = json.loads((root / "outputs/model_data_receipt.json").read_text())
    assert receipt["user_id"] == report["user_id"]
    assert receipt["archive_run_id"] == report["run_id"]
    assert report_path.read_bytes() == before
    assert (root / "outputs/result.txt").read_bytes() == professional_before
    assert set(requests[0]) == {
        "schema_version",
        "product",
        "receipt_id",
        "plugin_version",
        "report_sha256",
        "user_id",
        "archive_run_id",
        "report_revision",
    }
    assert Registry().pending_receipts() == []
    record = receipts.get(receipt["receipt_id"])
    assert signer.verify(record.signed_payload, record.signature)
    archive_core.ledger.validate_run_artifacts(
        client_case.client_root, client_case.engagement_id, report["run_id"]
    )

    import io
    from types import SimpleNamespace
    from urllib.parse import urlsplit

    import notarized_run_receipt

    standalone = tmp_path / "copied-report.json"
    standalone.write_bytes(before)

    def open_verified(url, timeout):
        parsed = urlsplit(url)
        response = client.get(parsed.path + "?" + parsed.query)
        response.raise_for_status()
        return io.BytesIO(response.content)

    monkeypatch.setattr(
        archive_report_receipt.urllib.request,
        "build_opener",
        lambda *args: SimpleNamespace(open=open_verified),
    )
    monkeypatch.setattr(
        notarized_run_receipt,
        "_plugin_version",
        lambda root: pytest.fail(
            "Verification must not depend on the current plugin version"
        ),
    )

    verified = archive_report_receipt.verify_report(
        standalone, user_id=report["user_id"]
    )
    assert verified["report_sha256"] == receipt["report_sha256"]
    with pytest.raises(ValueError, match="another Vera userID"):
        archive_report_receipt.verify_report(standalone, user_id=USER_ID)
    standalone.write_bytes(before + b"\n")
    with pytest.raises(ValueError, match="canonical"):
        archive_report_receipt.verify_report(standalone, user_id=report["user_id"])


def test_late_receipt_cannot_reseal_modified_professional_output(
    archive_core, client_case
):
    from archive_report_receipt import retry_pending
    from archive_report_store import Registry

    loaded = start(archive_core, client_case)
    finish(archive_core, client_case, loaded)
    (Path(loaded["output_dir"]) / "result.txt").write_text(
        "Altered professional result"
    )

    with pytest.raises(ValueError, match="changed|match"):
        retry_pending(Registry())


def test_retry_does_not_recreate_a_removed_run(archive_core, client_case):
    import shutil

    from archive_report_receipt import retry_pending
    from archive_report_store import Registry

    loaded = start(archive_core, client_case)
    finish(archive_core, client_case, loaded)
    root = Path(loaded["run_root"])
    shutil.rmtree(root)

    retry_pending(Registry())

    assert not root.exists()
    assert Registry().pending_receipts() == []


def test_read_rejects_empty_column_selection(archive_core, client_case):
    from archive_reporting import read_artifact

    loaded = start(archive_core, client_case)

    with pytest.raises(ValueError, match="at least one"):
        read_artifact(
            loaded, Path(loaded["context"]["input_bindings"][0]["path"]), columns=[]
        )


def test_local_only_report_makes_no_transport_call(
    archive_core, client_case, monkeypatch, reporting_runtime
):
    import archive_report_receipt
    import operational_incidents

    monkeypatch.setattr(archive_report_receipt, "stamp_report", reporting_runtime)
    monkeypatch.setattr(
        operational_incidents,
        "workflow_transport",
        lambda *args: pytest.fail("Local-only run attempted transport"),
    )
    loaded = start(archive_core, client_case)
    (Path(loaded["output_dir"]) / "model_data_report_options.json").write_text(
        '{"local_only":true}'
    )

    report = finish(archive_core, client_case, loaded)

    status = json.loads(
        (Path(loaded["run_root"]) / "model_data_reporting.json").read_text()
    )
    assert report["collection_closed"] is True
    assert status["server_receipt"] == {
        "status": "not_requested",
        "reason": "local_only",
    }


def test_xlsx_selection_preserves_physical_rows_columns_and_formula(tmp_path):
    from archive_report_measurements import measure_source, read_selection
    from openpyxl import Workbook

    path = tmp_path / "source.xlsx"
    book = Workbook()
    book.active.append(["Account", "Value"])
    book.active.append(["A", "=2+3"])
    book.create_sheet("Second").append(["B", 7])
    book.save(path)
    source = measure_source(path, source_id="book")

    data, evidence = read_selection(source, offset=1, limit=1, columns=[1])

    assert source["quantity"] == 3
    assert source["cells"] == 6
    assert data["rows"] == [["=2+3"]]
    assert evidence["start"] == 1
    assert evidence["stop"] == 2
    assert evidence["columns"] == [1]


def test_scanned_or_empty_pdf_cannot_claim_measured_exposure(tmp_path):
    from archive_report_measurements import measure_source, read_selection
    from pypdf import PdfWriter

    path = tmp_path / "scan.pdf"
    writer = PdfWriter()
    writer.add_blank_page(width=200, height=200)
    writer.write(path)
    source = measure_source(path, source_id="scan")

    with pytest.raises(ValueError, match="no complete measurement"):
        read_selection(source)

    assert source["measurement_error"] is not None


def test_exact_head_read_counts_only_returned_csv_records(
    archive_core, client_case, tmp_path
):
    from archive_report_hook import handle

    loaded = csv_case(archive_core, client_case, tmp_path)
    path = Path(loaded["context"]["input_bindings"][0]["path"])
    shown = "".join(path.read_text().splitlines(keepends=True)[:101])
    handle(
        {
            "hook_event_name": "PostToolUse",
            "session_id": "test-session",
            "tool_use_id": "head-read",
            "tool_name": "Bash",
            "tool_input": {"command": f"head -n 101 '{path}'"},
            "tool_response": {"stdout": shown},
        }
    )

    report = finish(archive_core, client_case, loaded)

    assert report["sources"][0]["observed_quantity"] == 100
    assert report["sources"][0]["remaining_local"] == 9900


def test_unmapped_extra_output_prevents_false_local_remainder(
    archive_core, client_case
):
    from archive_report_hook import handle
    from archive_reporting import read_artifact

    loaded = start(archive_core, client_case)
    packet = read_artifact(loaded, Path(loaded["context"]["input_bindings"][0]["path"]))
    handle(
        {
            "hook_event_name": "PostToolUse",
            "session_id": "test-session",
            "tool_use_id": "extra",
            "tool_name": "mcp-read",
            "tool_input": {"run_id": loaded["run"]["run_id"]},
            "tool_response": {
                "content": [{"type": "text", "text": json.dumps(packet)}],
                "_meta": {"untracked_sensitive_field": "additional data"},
            },
        }
    )

    report = finish(archive_core, client_case, loaded)

    assert report["collection_status"] == "incomplete"
    assert report["sources"][0]["remaining_local"] is None
    assert report["sources"][0]["observed_quantity"] == 1


def test_changed_registered_packet_cannot_claim_original_rows(
    archive_core, client_case
):
    from archive_report_hook import handle
    from archive_reporting import read_artifact

    loaded = start(archive_core, client_case)
    packet = read_artifact(loaded, Path(loaded["context"]["input_bindings"][0]["path"]))
    packet["data"]["rows"] = [["different bytes"]]
    handle(
        {
            "hook_event_name": "PostToolUse",
            "session_id": "test-session",
            "tool_use_id": "changed",
            "tool_name": "mcp-read",
            "tool_input": {},
            "tool_response": packet,
        }
    )

    report = finish(archive_core, client_case, loaded)

    assert report["sources"][0]["observed_quantity"] == 0
    assert report["collection_status"] == "incomplete"


def test_hook_cli_failure_is_explicit_without_echoing_source_data(monkeypatch, capsys):
    import io

    import archive_report_hook

    monkeypatch.setattr(
        archive_report_hook.sys,
        "stdin",
        io.StringIO(
            json.dumps(
                {
                    "hook_event_name": "PostToolUse",
                    "session_id": "test-session",
                    "tool_input": "PRIVATE SOURCE",
                }
            )
        ),
    )

    result = archive_report_hook.main()

    output = capsys.readouterr().out
    assert result == 0
    assert "collection failed" in json.loads(output)["systemMessage"]
    assert "PRIVATE SOURCE" not in output


def test_stop_hook_retries_pending_proof(archive_core, client_case, monkeypatch):
    import archive_report_receipt
    from archive_report_hook import handle
    from archive_report_store import Registry

    loaded = start(archive_core, client_case)
    finish(archive_core, client_case, loaded)
    monkeypatch.setattr(
        archive_report_receipt,
        "stamp_report",
        lambda path: {"status": "not_requested", "reason": "local_only"},
    )

    handle({"hook_event_name": "Stop", "session_id": "test-session"})

    assert Registry().pending_receipts() == []


def test_host_python_observes_direct_read_and_reseals_pending_receipt(
    archive_core, client_case, tmp_path
):
    from archive_report_store import Registry, RunStore

    loaded = csv_case(archive_core, client_case, tmp_path)
    source = Path(loaded["context"]["input_bindings"][0]["path"])
    hook = (
        Path(__file__).resolve().parents[2]
        / "plugins/vera/scripts/archive_report_hook.py"
    )
    host_python = Path("/usr/bin/python3")
    executable = str(host_python) if host_python.is_file() else sys.executable
    event = {
        "hook_event_name": "PostToolUse",
        "session_id": "test-session",
        "tool_use_id": "host-python-direct-read",
        "tool_name": "exec_command",
        "tool_input": {
            "cmd": "cat " + shlex.quote(str(source)),
            "run_id": loaded["run"]["run_id"],
        },
        "tool_response": source.read_text(),
    }

    observed = subprocess.run(
        [executable, "-B", str(hook)],
        input=json.dumps(event),
        text=True,
        capture_output=True,
        check=True,
        timeout=30,
    )
    report = finish(archive_core, client_case, loaded)
    retried = subprocess.run(
        [executable, "-B", str(hook)],
        input=json.dumps({"hook_event_name": "Stop", "session_id": "test-session"}),
        text=True,
        capture_output=True,
        check=True,
        timeout=30,
    )

    assert json.loads(observed.stdout) == {}
    assert json.loads(retried.stdout) == {}
    assert report["sources"][0]["observed_quantity"] == 10000
    assert RunStore(Path(loaded["run_root"])).state()["collection_closed"] is True
    # The child has its own isolated identity, so the proof stays pending.
    assert Registry().pending_receipts() == [Path(loaded["run_root"])]
    archive_core.ledger.validate_run_artifacts(
        client_case.client_root, client_case.engagement_id, report["run_id"]
    )


def test_identity_failure_keeps_local_report(archive_core, client_case, monkeypatch):
    import archive_reporting

    def unavailable():
        raise OSError("No identity storage")

    monkeypatch.setattr(archive_reporting, "_identity", unavailable)
    loaded = start(archive_core, client_case)

    report = finish(archive_core, client_case, loaded)

    assert report["user_id"] is None
    assert "vera_machine_identity_unavailable" in report["errors"]
    assert report["collection_status"] == "incomplete"


@pytest.mark.parametrize("changed", [False, True])
def test_acquisition_registers_only_verified_originals_in_its_archive_run(
    archive_core, client_case, tmp_path, monkeypatch, changed
):
    from archive_report_store import RunStore

    monkeypatch.syspath_prepend(
        str(Path(__file__).resolve().parents[2] / "plugins/browser-automation/scripts")
    )
    from ade_acquisition import archive_runs, contracts, storage

    monkeypatch.setattr(archive_runs, "_archive", lambda: archive_core)
    loaded = start(archive_core, client_case, "agenzia-acquisition")
    worker = tmp_path / "acquisition-worker"
    worker.mkdir()
    (worker / "archive-runs.json").write_text(
        json.dumps(
            {
                "01234567890": {
                    "context_path": str(Path(loaded["run_root"]) / "context.json")
                }
            }
        )
    )
    retained = storage.Store(tmp_path / "retained-originals")
    client = contracts.Client.parse(
        {
            "name": "Synthetic client",
            "tax_code": "01234567890",
            "vat_number": "01234567890",
        }
    )
    record = retained.retain(
        client,
        "ricevute",
        "synthetic-download",
        2026,
        1,
        "original.xml",
        b"<invoice>private original</invoice>",
        {},
    )
    if changed:
        retained.safe_path(record["artifacts"][0]["path"]).write_bytes(b"changed")

    archive_runs.record_acquired_event(
        worker, retained, {"client": client.vat_number, "record": record}
    )

    sources = RunStore(Path(loaded["run_root"])).sources()
    assert len(sources) == (1 if changed else 2)
    assert (
        any(item["source_id"].startswith("acquired_") for item in sources)
        is not changed
    )


def test_stop_recovers_terminal_write_interrupted_before_report_finalization(
    archive_core, client_case, monkeypatch
):
    from archive_report_hook import handle
    from archive_report_store import RunStore

    loaded = start(archive_core, client_case)
    root = Path(loaded["run_root"])
    runtime = archive_core.ledger._reporting_runtime()

    def interrupted(value):
        raise OSError("Interrupted immediately after durable terminal write")

    with monkeypatch.context() as patch:
        patch.setattr(runtime, "finish_report", interrupted)
        patch.setattr(archive_core.ledger, "_reporting_runtime", lambda: runtime)
        with pytest.raises(OSError, match="Interrupted"):
            archive_core.ledger.fail_run(
                client_case.client_root,
                client_case.engagement_id,
                loaded["run"]["run_id"],
                "Synthetic failure",
            )
    assert RunStore(root).state()["finished_at"] is None
    assert json.loads((root / "run.json").read_text())["status"] == "failed"

    handle({"hook_event_name": "SessionStart", "session_id": "different-session"})

    report = json.loads((root / "outputs/model_data_report.json").read_text())
    assert report["outcome"] == "failed"
    assert report["collection_closed"] is True


def test_mcp_entrypoint_reads_exact_selection_and_observer_counts_returned_packet(
    archive_core, client_case, tmp_path, isolated_mcp_launcher
):
    from archive_report_hook import handle

    from tests.plugins.test_vera_studio_archive_component import _mcp_tool

    loaded = csv_case(archive_core, client_case, tmp_path)
    arguments = {
        "client_id": client_case.client_id,
        "engagement_id": client_case.engagement_id,
        "run_id": loaded["run"]["run_id"],
        "path": loaded["context"]["input_bindings"][0]["path"],
        "offset": 10,
        "limit": 2,
        "columns": [1],
    }

    archive_core._release_state_leases()
    response = _mcp_tool(
        "read_studio_run_artifact", arguments, state_dir=client_case.state_dir
    )

    assert response["isError"] is False, response
    packet = json.loads(response["content"][0]["text"])
    assert packet["data"]["rows"] == [["20"], ["22"]]
    handle(
        {
            "hook_event_name": "PostToolUse",
            "session_id": "test-session",
            "tool_use_id": "actual-mcp",
            "tool_name": "read_studio_run_artifact",
            "tool_input": arguments,
            "tool_response": response,
        }
    )
    report = finish(archive_core, client_case, loaded)
    assert report["sources"][0]["observed_quantity"] == 2
    assert report["sources"][0]["observed_cells"] == 2
