"""Native replies count actual delivery, retaining unknown content as gaps."""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path
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


def test_first_delivery_after_run_closure_remains_explicitly_blocked(
    archive_core, client_case, tmp_path, monkeypatch
):
    from archive_report_store import RunStore

    loaded = start(archive_core, client_case)
    module, args = retained_job(tmp_path, monkeypatch, loaded, "Undelivered value")
    store = RunStore(Path(loaded["run_root"]))
    state = store.state()
    store.save({**state, "collection_closed": True})
    before = store.events()

    with pytest.raises(ValueError, match="closed or changed"):
        module.execute(args)

    assert store.events() == before


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
