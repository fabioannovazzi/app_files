"""Transport deadlines and error reporting must not discard Archive outcomes."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest

from tests.plugins.test_archive_automatic_reporting import archive_script_imports

__all__: list[str] = []
ROOT = Path(__file__).resolve().parents[2]
SERVER = ROOT / "plugins/studio-archive/mcp/server.cjs"


def _call(tmp_path, worker, *, arguments):
    shim = tmp_path / "worker.cjs"
    shim.write_text(
        "const cp = require('node:child_process');\n"
        "cp.spawnSync = (executable, args, options) => {\n" + worker + "\n};\n"
    )
    request = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "tools/call",
        "params": {
            "name": "start_studio_client_workflow",
            "arguments": arguments,
        },
    }
    completed = subprocess.run(
        ["node", "--require", str(shim), str(SERVER)],
        input=json.dumps(request) + "\n",
        capture_output=True,
        text=True,
        check=True,
        timeout=10,
    )
    return json.loads(completed.stdout)["result"]


def _identifiers():
    return {
        "client_id": "client_" + "1" * 24,
        "engagement_id": "eng_" + "2" * 24,
        "run_id": "run_" + "3" * 24,
    }


def test_archive_adapter_delivers_work_that_exceeds_former_deadline(tmp_path):
    # Simulate a worker taking six minutes without making the test sleep.
    worker = """
      if (args.includes('record-error')) return {status: 0, stdout: '{"recorded":true}'};
      const elapsed = 360000;
      if (options.timeout && elapsed > options.timeout) {
        return {error: Object.assign(new Error('Worker killed at deadline'), {code:'ETIMEDOUT'})};
      }
      return {status: 0, stdout: JSON.stringify({status:'running', run_id:'run_'+'3'.repeat(24)})};
    """

    result = _call(tmp_path, worker, arguments=_identifiers())

    assert result["isError"] is False
    assert result["structuredContent"]["run_id"] == _identifiers()["run_id"]


def test_archive_mcp_retains_actual_operation_error_when_its_recorder_fails(tmp_path):
    worker = """
      if (args.includes('record-error')) return {status: 1, stderr:'Recorder unavailable'};
      return {status: 1, stdout: JSON.stringify({error:{code:'selected_storage_unavailable',
        message:'Selected storage disconnected', details:{recoverable:true}}})};
    """

    result = _call(tmp_path, worker, arguments=_identifiers())

    assert result["isError"] is True
    assert (
        result["structuredContent"]["error"]["code"] == "selected_storage_unavailable"
    )
    assert result["structuredContent"]["error"]["details"] == {"recoverable": True}
    assert result["_meta"]["reporting"]["status"] == "unavailable"


def test_archive_cli_retains_actual_operation_error_when_its_recorder_fails(
    archive_script_imports, monkeypatch, capsys
):
    import studio_archive

    def unavailable(*args, **kwargs):
        raise studio_archive.ArchiveError("Selected storage disconnected")

    def recorder_unavailable(*args, **kwargs):
        raise OSError("Recorder unavailable")

    monkeypatch.delenv("VERA_STUDIO_ARCHIVE_MCP", raising=False)
    monkeypatch.setattr(studio_archive, "start_studio_client_workflow", unavailable)
    monkeypatch.setattr(studio_archive, "record_error", recorder_unavailable)
    identifiers = _identifiers()

    code = studio_archive.main(
        [
            "start-workflow",
            "--client-id",
            identifiers["client_id"],
            "--engagement-id",
            identifiers["engagement_id"],
            "--run-id",
            identifiers["run_id"],
        ]
    )

    result = json.loads(capsys.readouterr().out)
    assert code == 1
    assert result["error"]["message"] == "Selected storage disconnected"
    assert result["reporting"]["status"] == "unavailable"
