"""Native replies count actual delivery, retaining unknown content as gaps."""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4

import pytest

from tests.plugins.test_archive_automatic_reporting import (
    archive_core,
    archive_script_imports,
    client_case,
    reporting_runtime,
    start,
)

__all__: list[str] = []
SCRIPT = (
    Path(__file__).resolve().parents[2] / "plugins/vera/scripts/native_execution.py"
)


def submit_native_arguments(
    tmp_path,
    monkeypatch,
    component,
    arguments,
    *,
    script="scripts/check_dependencies.py",
):
    """Exercise the real request boundary; execute the producer separately."""
    spec = importlib.util.spec_from_file_location("native_argument_test", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    jobs = tmp_path / "argument-jobs"
    jobs.mkdir(exist_ok=True)
    monkeypatch.setattr(module, "_jobs", lambda: jobs)

    def completed_worker(command, **kwargs):
        job = Path(command[-1])
        (job / "result.json").write_text(
            json.dumps({"state": "completed", "returncode": 0})
        )
        (job / "stdout.txt").write_text("")
        (job / "stderr.txt").write_text("")
        return SimpleNamespace(wait=lambda: 0)

    with monkeypatch.context() as scoped:
        scoped.setattr(module.subprocess, "Popen", completed_worker)
        return module.execute(
            {
                "operation": "run",
                "job_id": str(uuid4()),
                "component": component,
                "script": script,
                "arguments": arguments,
            }
        )


def test_native_request_retains_exact_model_text_without_claiming_file_exposure(
    archive_core, client_case, tmp_path, monkeypatch
):
    from archive_projection import model_argument_origin
    from archive_report_store import RunStore

    loaded = start(archive_core, client_case)
    output = Path(loaded["output_dir"])
    text = "A model-authored title with 1,200.00 already in context"
    store = RunStore(Path(loaded["run_root"]))
    before = [event for event in store.events() if event["kind"] == "vera_send"]

    submit_native_arguments(
        tmp_path,
        monkeypatch,
        "variance-analysis",
        ["--output-dir", str(output), "--title", text],
    )

    assert model_argument_origin("variance-analysis", output, text) == []
    assert model_argument_origin("variance-analysis", output, text + " changed") is None
    assert model_argument_origin("open-item-reconciliation", output, text) is None
    events = store.events()
    declarations = [
        event for event in events if event["kind"] == "model_supplied_arguments"
    ]
    assert len(declarations) == 1
    assert text not in json.dumps(declarations)
    sends = [event for event in events if event["kind"] == "vera_send"]
    assert len(sends) == len(before) + 1  # Only the native reply adds a send.
    assert sends[-1]["selections"] == []
    prepared = archive_core.prepare_studio_client_workflow(
        client_case.engagement_id,
        "variance-analysis",
        input_ids=[client_case.imported["input_id"]],
        new_run=True,
        state_dir=client_case.state_dir,
    )
    another_id = prepared["run"]["run_id"]
    archive_core.start_studio_client_workflow(
        client_case.client_id,
        client_case.engagement_id,
        another_id,
        state_dir=client_case.state_dir,
    )
    another = archive_core.ledger.load_run(
        client_case.client_root, client_case.engagement_id, another_id
    )
    assert another_id != loaded["run"]["run_id"]
    assert (
        model_argument_origin("variance-analysis", Path(another["output_dir"]), text)
        is None
    )


def retained_job(tmp_path, monkeypatch, loaded, stdout, stderr=""):
    """Represent a completed worker whose stdout has not reached the model."""
    spec = importlib.util.spec_from_file_location("native_execution_test", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    jobs = tmp_path / "native-jobs"
    job_id = str(uuid4())
    job = jobs / job_id
    job.mkdir(parents=True)
    monkeypatch.setattr(module, "_jobs", lambda: jobs)
    from archive_emit import bind_output

    arguments = ["--output-dir", loaded["output_dir"]]
    component = loaded["run"]["workflow_id"]
    request = {
        "component": component,
        "script": "scripts/check_dependencies.py",
        "arguments": arguments,
        "binding": bind_output(component, arguments),
    }
    (job / "request.json").write_text(json.dumps(request))
    (job / "result.json").write_text(
        json.dumps({"state": "completed", "returncode": 0})
    )
    (job / "stdout.txt").write_bytes(stdout.encode("utf-8"))
    (job / "stderr.txt").write_bytes(stderr.encode("utf-8"))
    return module, {"operation": "status", "job_id": job_id}


@pytest.mark.parametrize("extra", ["", "Unknown client value\n"])
def test_only_returned_payload_is_counted_and_unknown_text_is_not_metadata(
    archive_core, client_case, tmp_path, monkeypatch, extra
):
    from archive_projection import register_metadata
    from archive_report_store import RunStore, digest

    loaded = start(archive_core, client_case)
    store = RunStore(Path(loaded["run_root"]))
    status = "Known producer completion\n"
    register_metadata("variance-analysis", Path(loaded["output_dir"]), status)
    module, args = retained_job(tmp_path, monkeypatch, loaded, status + extra)
    before = [event for event in store.events() if event["kind"] == "vera_send"]

    result = module.execute(args)

    sends = [event for event in store.events() if event["kind"] == "vera_send"]
    assert len(sends) == len(before) + 1
    sent = next(event for event in sends if event["channel"] == "mcp:variance-analysis")
    assert sent["response_sha256"] == digest(result)
    assert sent["unmapped"] is bool(extra)
    assert result["structuredContent"]["output"][1]["stdout"] == status + extra


def test_completed_result_can_be_reopened_without_rewriting_its_closed_report(
    archive_core, client_case, tmp_path, monkeypatch
):
    from archive_report_store import RunStore

    loaded = start(archive_core, client_case)
    module, args = retained_job(tmp_path, monkeypatch, loaded, "")
    delivered = module.execute(args)
    store = RunStore(Path(loaded["run_root"]))
    state = store.state()
    store.save({**state, "collection_closed": True})
    before = store.path.read_bytes()

    reopened = module.execute(args)

    assert reopened == delivered
    assert store.path.read_bytes() == before


def test_first_delivery_after_report_closure_preserves_work_and_reports_gap(
    archive_core, client_case, tmp_path, monkeypatch
):
    from archive_report_store import RunStore

    loaded = start(archive_core, client_case)
    module, args = retained_job(tmp_path, monkeypatch, loaded, "Undelivered value")
    store = RunStore(Path(loaded["run_root"]))
    state = store.state()
    store.save({**state, "collection_closed": True})
    before = store.events()

    result = module.execute(args)

    assert store.events() == before
    assert result["structuredContent"]["output"][1]["stdout"] == "Undelivered value"
    assert result["structuredContent"]["reporting"]["status"] == "unavailable"
    assert "isError" not in result


def test_completed_native_job_is_delivered_when_reporting_write_fails(
    archive_core, client_case, tmp_path, monkeypatch
):
    from archive_report_store import RunStore

    loaded = start(archive_core, client_case)
    module, args = retained_job(tmp_path, monkeypatch, loaded, "Completed work")

    def unavailable(*args, **kwargs):
        raise OSError("Synthetic full disk")

    monkeypatch.setattr(RunStore, "event", unavailable)
    result = module.execute(args)

    metadata, streams = result["structuredContent"]["output"]
    assert metadata["state"] == "completed"
    assert metadata["returncode"] == 0
    assert metadata["job_id"] == args["job_id"]
    assert streams["stdout"] == "Completed work"
    assert result["structuredContent"]["reporting"]["status"] == "unavailable"
    assert "isError" not in result


def test_native_job_starts_and_delivers_without_collector_start_record(
    archive_core, client_case, tmp_path, monkeypatch
):
    from archive_report_store import RunStore

    loaded = start(archive_core, client_case)
    monkeypatch.setattr(RunStore, "state", lambda self: None)

    result = submit_native_arguments(
        tmp_path,
        monkeypatch,
        "variance-analysis",
        ["--output-dir", loaded["output_dir"]],
    )

    assert result["structuredContent"]["output"][0]["state"] == "completed"
    assert result["structuredContent"]["output"][0]["returncode"] == 0
    assert result["structuredContent"]["reporting"]["status"] == "unavailable"
    assert "isError" not in result


@pytest.mark.parametrize(
    "operation, worker_state",
    [("cancel", "running"), ("cancel", "cancelled"), ("status", "cancelled")],
)
def test_cancel_after_archive_closure_returns_status_without_source_output(
    archive_core, client_case, tmp_path, monkeypatch, operation, worker_state
):
    from archive_report_store import RunStore

    loaded = start(archive_core, client_case)
    module, args = retained_job(
        tmp_path, monkeypatch, loaded, "Undelivered client output", "Private diagnostic"
    )
    job = module._jobs() / args["job_id"]
    if worker_state == "running":
        (job / "result.json").unlink()
        (job / "heartbeat").touch()
    else:
        (job / "result.json").write_text(
            json.dumps({"state": "cancelled", "returncode": -9})
        )
    store = RunStore(Path(loaded["run_root"]))
    store.save({**store.state(), "collection_closed": True})
    before = store.path.read_bytes()

    result = module.execute({**args, "operation": operation})

    assert "isError" not in result
    assert len(result["structuredContent"]["output"]) == 1
    status = result["structuredContent"]["output"][0]
    assert status["job_id"] == args["job_id"]
    assert status["state"] == worker_state
    assert "stdout" not in status and "stderr" not in status
    assert "Undelivered client output" not in json.dumps(result)
    assert "Private diagnostic" not in json.dumps(result)
    assert store.path.read_bytes() == before


@pytest.mark.parametrize("line_ending", ["\n", "\r\n"])
def test_running_preview_returns_available_text_without_claiming_completion(
    archive_core, client_case, tmp_path, monkeypatch, line_ending
):
    loaded = start(archive_core, client_case, "open-item-reconciliation")
    module, args = retained_job(
        tmp_path, monkeypatch, loaded, f"Preview ready{line_ending}"
    )
    job = module._jobs() / args["job_id"]
    (job / "result.json").unlink()
    (job / "heartbeat").touch()
    request = json.loads((job / "request.json").read_text())
    request["script"] = "scripts/review_server.py"
    (job / "request.json").write_text(json.dumps(request))
    (job / "stderr.txt").write_bytes("Local startup\nPartial ".encode() + b"\xe2")

    result = module.execute(args)

    metadata, streams = result["structuredContent"]["output"]
    assert metadata["state"] == "running"
    assert "returncode" not in metadata
    assert streams == {
        "stdout": f"Preview ready{line_ending}",
        "stderr": "Local startup\n",
    }
