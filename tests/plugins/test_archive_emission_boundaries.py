"""Exercise Vera's actual CLI/MCP delivery boundaries without host hooks."""

from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from pathlib import Path

import pytest

from tests.plugins.test_archive_automatic_reporting import (
    PIPELINES,
    archive_core,
    archive_script_imports,
    client_case,
    finish,
    reporting_runtime,
    start,
)

ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = ROOT / "plugins/vera/scripts"


@pytest.mark.parametrize("line_ending", ["\r\n", "\r", "\n"])
def test_full_source_text_matches_universal_newlines_without_changing_saved_payload(
    archive_core, client_case, tmp_path, line_ending
):
    from archive_emit import record_output
    from archive_report_store import RunStore, digest

    source = tmp_path / "line-endings.txt"
    source.write_bytes(
        ("First line" + line_ending + "Second line" + line_ending).encode()
    )
    client_case.imported = archive_core.import_studio_client_document(
        client_case.client_id,
        source,
        "source",
        engagement_id=client_case.engagement_id,
        state_dir=client_case.state_dir,
    )
    loaded = start(archive_core, client_case, "report-builder")
    payload = {"content": [{"type": "text", "text": "First line\nSecond line\n"}]}

    record_output(
        "report-builder",
        {"client_engagement": loaded["context_path"]},
        payload,
        channel="mcp",
    )

    events = RunStore(Path(loaded["run_root"])).events()
    sends = [event for event in events if event.get("channel") == "mcp:report-builder"]
    assert sends[-1]["response_sha256"] == digest(payload)
    assert sends[-1]["unmapped"] is False
    report = finish(archive_core, client_case, loaded)
    assert report["collection_status"] == "complete", report["errors"]
    assert report["sources"][0]["sent_quantity"] == 2
    assert report["sources"][0]["not_sent_quantity"] == 0


@pytest.mark.parametrize("pipeline", PIPELINES)
def test_each_selected_component_records_its_actual_outgoing_source(
    archive_core, client_case, pipeline
):
    from archive_emit import record_output

    loaded = start(archive_core, client_case, pipeline)
    source = Path(loaded["context"]["input_bindings"][0]["path"])
    component = {
        "fatture-xml-check": "client-file-preparation",
        "agenzia-acquisition": "browser-automation",
        "report-enti-locali": "report-builder",
    }.get(pipeline, loaded["run"]["workflow_id"])

    record_output(
        component,
        {"client_engagement": str(Path(loaded["run_root"]) / "context.json")},
        {
            "content": [{"type": "text", "text": source.read_text()}],
            "_meta": {"app_only": "PRIVATE_UI_DATA"},
        },
        channel="mcp",
    )
    report = finish(archive_core, client_case, loaded)

    assert report["collection_status"] == "complete", report["errors"]
    assert report["sources"][0]["sent_quantity"] == 1
    assert report["sources"][0]["not_sent_quantity"] == 0
    assert (
        b"PRIVATE_UI_DATA"
        not in (Path(loaded["run_root"]) / "reporting/events.sqlite3").read_bytes()
    )


def test_cli_returns_exact_output_only_after_its_record_is_saved(
    archive_core, client_case, tmp_path
):
    from archive_report_store import RunStore

    loaded = start(archive_core, client_case, "report-builder")
    context = str(Path(loaded["run_root"]) / "context.json")
    source = loaded["context"]["input_bindings"][0]["path"]
    launcher = tmp_path / "cli_boundary.py"
    launcher.write_text(
        "import sys\nfrom pathlib import Path\n"
        f"sys.path.insert(0, {str(SCRIPTS)!r})\n"
        "from archive_cli import run_command\n"
        f"raise SystemExit(run_command([sys.executable, '-c', 'import sys;sys.stdout.write(open(sys.argv[1]).read())', {source!r}], "
        f"plugin_root=Path({str(ROOT / 'plugins/vera')!r}), component='report-builder', arguments=[{context!r}], check=False).returncode)\n"
    )

    result = subprocess.run(
        [sys.executable, str(launcher)], capture_output=True, timeout=30
    )

    assert result.returncode == 0, result.stderr
    assert result.stdout == Path(source).read_bytes()
    events = [
        event
        for event in RunStore(Path(loaded["run_root"])).events()
        if event.get("channel") == "cli:report-builder"
    ]
    assert len(events) == 1
    assert events[0]["unmapped"] is False
    assert events[0]["selections"][0]["stop"] == 1


@pytest.mark.parametrize("recording_available", [True, False])
def test_mcp_bridge_records_model_payload_and_keeps_app_metadata_out(
    archive_core, client_case, tmp_path, recording_available
):
    from archive_report_store import RunStore, digest

    loaded = start(archive_core, client_case, "report-builder")
    source = Path(loaded["context"]["input_bindings"][0]["path"])
    payload = {
        "content": [{"type": "text", "text": source.read_text()}],
        "_meta": {"ui": "ONLY_IN_APP"},
    }
    worker = tmp_path / "producer.cjs"
    worker.write_text(
        "require('node:readline').createInterface({input:process.stdin}).on('line',line=>{const m=JSON.parse(line);process.stdout.write(JSON.stringify({jsonrpc:'2.0',id:m.id,result:"
        + json.dumps(payload)
        + "})+'\\n');});"
    )
    launcher = tmp_path / "bridge.cjs"
    launcher.write_text(
        "const {spawn}=require('node:child_process');\n"
        f"const {{bridge}}=require({json.dumps(str(SCRIPTS / 'archive_emission_mcp.cjs'))});\n"
        f"const child=spawn(process.execPath,[{json.dumps(str(worker))}],{{stdio:['pipe','pipe','inherit']}});\n"
        f"bridge(child,'report-builder',{json.dumps(str(ROOT / 'plugins/vera'))});\n"
    )
    request = {
        "jsonrpc": "2.0",
        "id": 42,
        "method": "tools/call",
        "params": {
            "name": "review",
            "arguments": {
                "client_engagement": str(Path(loaded["run_root"]) / "context.json")
            },
        },
    }
    recorder = sys.executable
    if not recording_available:
        broken = tmp_path / "unavailable-recorder"
        broken.write_text("#!/bin/sh\nexit 1\n")
        broken.chmod(0o700)
        recorder = str(broken)

    result = subprocess.run(
        ["node", str(launcher)],
        input=json.dumps(request) + "\n",
        capture_output=True,
        text=True,
        env={**os.environ, "VERA_REPORTING_PYTHON": recorder},
        timeout=30,
    )

    assert result.returncode == 0, result.stderr
    if not recording_available:
        assert json.loads(result.stdout)["result"]["isError"] is True
        assert source.read_text().strip() not in result.stdout
        assert "ONLY_IN_APP" not in result.stdout
        return
    assert json.loads(result.stdout)["result"] == payload
    events = [
        event
        for event in RunStore(Path(loaded["run_root"])).events()
        if event.get("channel") == "mcp:report-builder"
    ]
    assert len(events) == 1
    assert events[0]["response_sha256"] == digest({"content": payload["content"]})
    assert events[0]["unmapped"] is False


def test_changed_packet_cannot_reuse_an_already_recorded_token(
    archive_core, client_case
):
    from archive_emit import record_output
    from archive_report_store import RunStore
    from archive_reporting import read_artifact

    loaded = start(archive_core, client_case, "report-builder")
    packet = read_artifact(loaded, Path(loaded["context"]["input_bindings"][0]["path"]))
    packet["data"] = {"secret": "DIFFERENT_CASE_DATA"}

    record_output(
        "report-builder",
        {"output_dir": loaded["output_dir"]},
        {"content": [{"type": "text", "text": json.dumps(packet)}]},
        channel="mcp",
    )

    events = [
        event
        for event in RunStore(Path(loaded["run_root"])).events()
        if event.get("channel") == "mcp:report-builder"
    ]
    assert len(events) == 1
    assert events[0]["unmapped"] is True


def test_token_only_mcp_requests_preserve_their_own_run(
    archive_core, client_case, tmp_path
):
    from archive_report_store import RunStore, digest

    first = start(archive_core, client_case, "report-builder")
    second = start(archive_core, client_case, "report-enti-locali")
    assert first["run_root"] != second["run_root"]
    worker = tmp_path / "token-producer.cjs"
    worker.write_text(
        """
const rl = require('node:readline').createInterface({input: process.stdin});
rl.on('line', line => {
  const m = JSON.parse(line), a = m.params.arguments;
  const data = a.client_engagement ? {review_reference: {persistence_token: a.token}}
    : {selected: a.persistence_token};
  process.stdout.write(JSON.stringify({jsonrpc:'2.0', id:m.id,
    result:{structuredContent:data, content:[{type:'text',text:JSON.stringify(data)}]}})+'\\n');
});
"""
    )
    launcher = tmp_path / "token-bridge.cjs"
    launcher.write_text(
        "const {spawn}=require('node:child_process');\n"
        f"const {{bridge}}=require({json.dumps(str(SCRIPTS / 'archive_emission_mcp.cjs'))});\n"
        f"const child=spawn(process.execPath,[{json.dumps(str(worker))}],{{stdio:['pipe','pipe','inherit']}});\n"
        f"bridge(child,'report-builder',{json.dumps(str(ROOT / 'plugins/vera'))});\n"
    )

    def request(number, arguments):
        return json.dumps(
            {
                "jsonrpc": "2.0",
                "id": number,
                "method": "tools/call",
                "params": {"name": "review", "arguments": arguments},
            }
        )

    requests = [
        request(1, {"client_engagement": first["context_path"], "token": "first"}),
        request(2, {"client_engagement": second["context_path"], "token": "second"}),
        request(3, {"persistence_token": "second"}),
        request(4, {"persistence_token": "first"}),
    ]
    result = subprocess.run(
        ["node", str(launcher)],
        input="\n".join(requests) + "\n",
        capture_output=True,
        text=True,
        env={**os.environ, "VERA_REPORTING_PYTHON": sys.executable},
        timeout=30,
    )

    assert result.returncode == 0, result.stderr
    responses = [json.loads(line)["result"] for line in result.stdout.splitlines()]
    first_hashes = {
        event["response_sha256"]
        for event in RunStore(Path(first["run_root"])).events()
        if event.get("channel") == "mcp:report-builder"
    }
    second_hashes = {
        event["response_sha256"]
        for event in RunStore(Path(second["run_root"])).events()
        if event.get("channel") == "mcp:report-builder"
    }
    assert first_hashes == {digest(responses[0]), digest(responses[3])}
    assert second_hashes == {digest(responses[1]), digest(responses[2])}


def test_mcp_withholds_a_result_when_archive_closed_while_it_was_running(
    archive_core, client_case, tmp_path
):
    loaded = start(archive_core, client_case, "report-builder")
    ready, release = tmp_path / "ready", tmp_path / "release"
    worker = tmp_path / "delayed-producer.cjs"
    worker.write_text(
        "const fs=require('node:fs');require('node:readline').createInterface({input:process.stdin}).on('line',line=>{"
        f"fs.writeFileSync({json.dumps(str(ready))},'ready');"
        "const m=JSON.parse(line);const timer=setInterval(()=>{"
        f"if(!fs.existsSync({json.dumps(str(release))}))return;"
        "clearInterval(timer);process.stdout.write(JSON.stringify({jsonrpc:'2.0',id:m.id,"
        "result:{content:[{type:'text',text:'WITHHELD_CASE_VALUE'}]}})+'\\n');},10);});"
    )
    launcher = tmp_path / "delayed-bridge.cjs"
    launcher.write_text(
        "const {spawn}=require('node:child_process');\n"
        f"const {{bridge}}=require({json.dumps(str(SCRIPTS / 'archive_emission_mcp.cjs'))});\n"
        f"const child=spawn(process.execPath,[{json.dumps(str(worker))}],{{stdio:['pipe','pipe','inherit']}});\n"
        f"bridge(child,'report-builder',{json.dumps(str(ROOT / 'plugins/vera'))});\n"
    )
    request = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "tools/call",
        "params": {
            "name": "review",
            "arguments": {"client_engagement": loaded["context_path"]},
        },
    }
    with subprocess.Popen(
        ["node", str(launcher)],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        env={**os.environ, "VERA_REPORTING_PYTHON": sys.executable},
    ) as process:
        try:
            process.stdin.write(json.dumps(request) + "\n")
            process.stdin.flush()
            deadline = time.monotonic() + 10
            while not ready.exists() and time.monotonic() < deadline:
                time.sleep(0.01)
            assert ready.exists(), "Producer did not start"
            final = finish(archive_core, client_case, loaded)
        finally:
            release.touch()
            stdout, stderr = process.communicate(timeout=20)

    assert process.returncode == 0, stderr
    assert json.loads(stdout)["result"]["isError"] is True
    assert "WITHHELD_CASE_VALUE" not in stdout + stderr
    assert final["collection_status"] == "complete"
    assert final["sources"][0]["sent_quantity"] == 0
