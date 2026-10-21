"""Native handoff regressions; synthetic records are not host acceptance."""

from __future__ import annotations

import importlib
import json
from pathlib import Path

import pytest

SCRIPTS = (
    Path(__file__).resolve().parents[2] / "plugins/journal-bank-reconciliation/scripts"
)


@pytest.fixture
def native(monkeypatch):
    monkeypatch.syspath_prepend(str(SCRIPTS))
    return importlib.import_module("native_host_worker")


def arguments(tmp_path, host):
    from worker_capabilities import select_worker

    return dict(
        prompt="Use this synthetic evidence only.",
        output_schema={"type": "object"},
        output_dir=tmp_path,
        workflow_id="open-item-reconciliation",
        packet_sha256="a" * 64,
        worker_selection=select_worker("open-item-reconciliation", host=host),
    )


def completed_record(request, response=None):
    config = request["configuration"]
    return {
        "schema_version": "vera.native_host_worker_record.v1",
        "provenance": "parent_observed_native_tool",
        "request_sha256": request["content_sha256"],
        "invocation": request["invocation"],
        "capabilities": {
            "host": config["host"],
            "tool": config["tool"],
            "agent": config["agent"],
            "model_choices": [config["model"]],
            "declared_tools": config["declared_tools"],
            "fresh_context": True,
            "runtime": "synthetic-host-version",
        },
        "completion": {
            "invocation_id": "synthetic-child-1",
            "status": "completed",
            "tool_uses": 0,
            "parent_history_inherited": False,
            "resumed": False,
            "response_text": json.dumps(response or {"decisions": []}),
            "model_observed": None,
        },
    }


@pytest.mark.parametrize("host", ["cowork", "antigravity"])
def test_preparation_runs_no_worker_and_requires_actual_completion(
    native, tmp_path, host
):
    with pytest.raises(native.NativeWorkerPending, match="NATIVE_WORKER_PENDING"):
        native.run_worker(**arguments(tmp_path, host))
    assert (tmp_path / "native_host_request.json").is_file()
    assert not (tmp_path / "luna_launch_receipt.json").exists()


@pytest.mark.parametrize("host", ["cowork", "antigravity"])
def test_native_completion_replays_without_codex_canaries_or_provider_claim(
    native, tmp_path, host
):
    args = arguments(tmp_path, host)
    with pytest.raises(native.NativeWorkerPending):
        native.run_worker(**args)
    request = json.loads((tmp_path / "native_host_request.json").read_text())
    (tmp_path / "native_host_record.json").write_text(
        json.dumps(completed_record(request))
    )
    result = native.run_worker(**args)
    receipt = json.loads(result["launch_receipt"].read_text())
    summary = native.validate_receipt(
        receipt,
        workflow_id=args["workflow_id"],
        packet_sha256=args["packet_sha256"],
        prompt=args["prompt"],
        output_schema=args["output_schema"],
        response=result["response_payload"],
    )
    assert summary["thread_id"] == "synthetic-child-1"
    assert receipt["runtime_attestation"]["provider_attestation"] is False
    assert receipt["runtime_attestation"]["os_isolation_probed"] is False
    assert "canaries" not in receipt


@pytest.mark.parametrize(
    "field,value",
    [
        ("tool_uses", 1),
        ("tool_uses", False),
        ("status", "running"),
        ("resumed", True),
        ("parent_history_inherited", True),
        ("invocation_id", ""),
    ],
)
def test_out_of_packet_or_incomplete_child_cannot_supply_a_result(
    native, tmp_path, field, value
):
    args = arguments(tmp_path, "cowork")
    with pytest.raises(native.NativeWorkerPending):
        native.run_worker(**args)
    request = json.loads((tmp_path / "native_host_request.json").read_text())
    record = completed_record(request)
    record["completion"][field] = value
    (tmp_path / "native_host_record.json").write_text(json.dumps(record))
    with pytest.raises(ValueError, match="incomplete, reused, or used tools"):
        native.run_worker(**args)
    assert not (tmp_path / "luna_launch_receipt.json").exists()


@pytest.mark.parametrize("mutation", ["packet", "model", "capabilities", "response"])
def test_changed_packet_invocation_capabilities_or_response_is_rejected(
    native, tmp_path, mutation
):
    args = arguments(tmp_path, "antigravity")
    with pytest.raises(native.NativeWorkerPending):
        native.run_worker(**args)
    request = json.loads((tmp_path / "native_host_request.json").read_text())
    record = completed_record(request)
    if mutation == "packet":
        record["request_sha256"] = "b" * 64
    elif mutation == "model":
        record["invocation"]["parameters"]["Model"] = "inherit"
    elif mutation == "capabilities":
        record["capabilities"]["declared_tools"] = ["run_command"]
    else:
        record["completion"]["response_text"] = "not JSON"
    (tmp_path / "native_host_record.json").write_text(json.dumps(record))
    with pytest.raises(ValueError):
        native.run_worker(**args)


def test_resume_cannot_overwrite_another_request(native, tmp_path):
    args = arguments(tmp_path, "cowork")
    with pytest.raises(native.NativeWorkerPending):
        native.run_worker(**args)
    args["prompt"] = "Changed evidence"
    with pytest.raises(ValueError, match="artifact changed"):
        native.run_worker(**args)
