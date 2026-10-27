"""Actual native MCP selections must write their outgoing payload inside the run."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from tests.plugins.test_archive_automatic_reporting import (
    archive_script_imports,
    reporting_runtime,
)
from tests.plugins.test_vera_native_workspace import (
    SERVER,
    bank_workspace,
    report_workspace,
    sampling_workspace,
    vera_workflow_workspace,
    vouching_workspace,
)


def assert_native_send(case, item_type, *, recorder_failure=None, tmp_path=None):
    from archive_report_store import RunStore, digest

    service, binding = case[:2]
    loaded = service.load_binding(binding)
    view = service.dispatch("vera_workspace_view", {"work_ref": binding["work_ref"]})
    selected = next(
        item
        for item in view["items"]
        if item_type is None or item["item_type"] == item_type
    )
    args = {
        "work_ref": binding["work_ref"],
        "revision": view["revision"],
        "item_id": selected["id"],
    }
    request = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "tools/call",
        "params": {"name": "vera_workspace_explain", "arguments": args},
    }
    store = RunStore(Path(loaded["run_root"]))
    previous = {event["event_id"] for event in store.events()}

    command = ["node", str(SERVER)]
    if recorder_failure:
        shim = tmp_path / "unavailable-recorder.cjs"
        shim.write_text(
            "const cp = require('node:child_process'); const original = cp.spawnSync;"
            "cp.spawnSync = (command, args, options) => {"
            "const request = options?.input && JSON.parse(options.input);"
            f"if (request?.tool === {json.dumps(recorder_failure)}) "
            "return {status: 1, stderr: 'Synthetic recorder unavailable'};"
            "return original(command, args, options); };"
        )
        command = ["node", "--require", str(shim), str(SERVER)]
    completed = subprocess.run(
        command,
        input=json.dumps(request) + "\n",
        text=True,
        capture_output=True,
        env=os.environ.copy(),
        timeout=60,
    )

    assert completed.returncode == 0, completed.stderr
    result = json.loads(completed.stdout)["result"]
    assert result.get("isError") is not True, result
    assert result["structuredContent"]["work_ref"] == binding["work_ref"]
    assert result["structuredContent"]["untrusted_evidence"]
    if recorder_failure:
        assert result["_meta"]["reporting"]["status"] == "unavailable"
        assert result["_meta"]["reporting"]["response_delivered"] is True
        return
    emissions = [
        event
        for event in store.events()
        if event["event_id"] not in previous and event["kind"] == "vera_send"
    ]
    assert len(emissions) == 1
    assert emissions[0]["channel"] == "mcp:" + loaded["run"]["workflow_id"]
    assert emissions[0]["response_sha256"] == digest(result)


def test_native_sampling_selection_is_recorded(sampling_workspace):
    assert_native_send(sampling_workspace, "sampled_entry")


@pytest.mark.parametrize("failure", ["__bind_model_output", "__record_model_output"])
def test_native_workspace_delivers_selected_evidence_when_reporting_fails(
    sampling_workspace, tmp_path, failure
):
    assert_native_send(
        sampling_workspace, "sampled_entry", recorder_failure=failure, tmp_path=tmp_path
    )


def test_native_vouching_selection_is_recorded(vouching_workspace):
    # Exercise the actual assurance preflight with a useful failure diagnostic
    # before its MCP layer intentionally sanitizes local exception details.
    from local_helper_environment import local_helper_environment

    component = SERVER.parents[2] / "check-entries"
    preflight = subprocess.run(
        [
            sys.executable,
            "-I",
            "-B",
            str(component / "scripts/apply_review_edits.py"),
            "--output-dir",
            str(vouching_workspace[3]),
            "--preflight-only",
        ],
        capture_output=True,
        text=True,
        timeout=60,
        env=local_helper_environment(python=sys.executable),
    )
    assert preflight.returncode == 0, preflight.stdout + preflight.stderr
    assert_native_send(vouching_workspace, "supported_entry")


def test_native_bank_selection_is_recorded(bank_workspace):
    assert_native_send(bank_workspace, None)


def test_native_report_section_is_recorded(report_workspace):
    assert_native_send(report_workspace, "report_section")


def test_native_selected_run_records_its_error_response(sampling_workspace):
    from archive_report_store import RunStore, digest

    service, binding = sampling_workspace[:2]
    loaded = service.load_binding(binding)
    view = service.dispatch("vera_workspace_view", {"work_ref": binding["work_ref"]})
    store = RunStore(Path(loaded["run_root"]))
    previous = {event["event_id"] for event in store.events()}
    request = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "tools/call",
        "params": {
            "name": "vera_workspace_explain",
            "arguments": {
                "work_ref": binding["work_ref"],
                "revision": view["revision"],
                "item_id": "missing-selection",
            },
        },
    }

    completed = subprocess.run(
        ["node", str(SERVER)],
        input=json.dumps(request) + "\n",
        text=True,
        capture_output=True,
        env=os.environ.copy(),
        timeout=60,
    )

    assert completed.returncode == 0, completed.stderr
    result = json.loads(completed.stdout)["result"]
    assert result["isError"] is True
    events = [
        e
        for e in store.events()
        if e["event_id"] not in previous and e["kind"] == "vera_send"
    ]
    assert len(events) == 1
    assert events[0]["response_sha256"] == digest(
        {key: value for key, value in result.items() if key != "_meta"}
    )
