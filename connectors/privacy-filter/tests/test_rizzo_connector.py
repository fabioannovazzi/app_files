"""Loopback transport, privacy contracts and Rizzo MCP behavior."""

from __future__ import annotations

import asyncio
import importlib.util
import io
import json
import sys
import threading
import tomllib
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from types import SimpleNamespace

import pytest
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from mparanza_privacy_filter import rizzo_api
from mparanza_privacy_filter.contracts import FilterError
from mparanza_privacy_filter.service import FilterService, Settings

__all__: list[str] = []


@pytest.fixture
def api():
    state = SimpleNamespace(
        status=200,
        health={
            "status": "ok",
            "model_loaded": True,
            "app_version": "2.0.0",
            "model_version": "1.5.0",
            "device": "cpu",
            "ignored": "secret",
        },
        result={
            "anonymized_text": "[FULLNAME_1] writes.",
            "by_label": {"FULLNAME": 1},
            "mapping_enabled": False,
            "mapping": {},
            "excluded_tags": [],
            "n_chars": 12,
            "n_entities": 1,
            "source_text": "Anna writes.",
            "segments": [{"t": "Anna"}],
        },
        requests=[],
    )

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            state.requests.append(("GET", self.path))
            self.reply(state.health)

        def do_POST(self):
            body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
            state.requests.append(("POST", self.path, body))
            self.reply(state.result)

        def reply(self, body):
            data = body if isinstance(body, bytes) else json.dumps(body).encode()
            self.send_response(state.status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(data)))
            self.send_header("Location", "https://example.com/must-not-follow")
            self.end_headers()
            self.wfile.write(data)

        def log_message(self, *args):
            pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    state.port = server.server_port
    try:
        yield state
    finally:
        server.shutdown()
        server.server_close()
        thread.join()


def test_local_request_disables_mapping_and_discards_sensitive_fields(api, monkeypatch):
    monkeypatch.setenv("HTTP_PROXY", "http://127.0.0.1:1")
    monkeypatch.setenv("ALL_PROXY", "http://127.0.0.1:1")
    result = rizzo_api.analyze(" Anna writes. ", api.port)
    assert api.requests == [
        (
            "POST",
            "/analyze",
            {"text": "Anna writes.", "include_mapping": False, "exclude_tags": []},
        )
    ]
    assert result.redacted_text == "[FULLNAME_1] writes."
    assert result.detection_counts == {"FULLNAME": 1}
    assert "Anna" not in str(result)


@pytest.mark.parametrize(
    "field,value",
    [
        ("mapping_enabled", True),
        ("mapping", {"[FULLNAME_1]": "Anna"}),
        ("excluded_tags", ["EMAIL"]),
        ("n_chars", 999),
        ("n_chars", True),
        ("n_entities", 0),
        ("by_label", {"Anna": 1}),
        ("by_label", {"FULLNAME": -1}),
        ("by_label", {"FULLNAME": True}),
        ("anonymized_text", None),
        ("anonymized_text", ""),
    ],
)
def test_invalid_upstream_contract_fails_with_fixed_error(api, field, value):
    api.result[field] = value
    with pytest.raises(FilterError, match="^invalid_rizzo_response$"):
        rizzo_api.analyze("Anna writes.", api.port)


@pytest.mark.parametrize("status", [302, 307, 400, 500, 503])
def test_redirects_and_upstream_errors_are_not_followed_or_exposed(api, status):
    api.status = status
    api.result = {"error": "Anna original document"}
    with pytest.raises(FilterError, match="^rizzo_unavailable$"):
        rizzo_api.analyze("Anna writes.", api.port)
    assert len(api.requests) == 1


@pytest.mark.parametrize("port", [0, -1, 65536, True, "https://example.com"])
def test_only_integer_local_ports_are_accepted(port):
    with pytest.raises(FilterError, match="^invalid_rizzo_port$"):
        rizzo_api.health(port)


def test_response_size_is_bounded(api, monkeypatch):
    monkeypatch.setattr(rizzo_api, "MAX_RESPONSE_BYTES", 16)
    with pytest.raises(FilterError, match="^invalid_rizzo_response$"):
        rizzo_api.health(api.port)


def test_health_returns_only_validated_metadata(api):
    assert rizzo_api.health(api.port) == {
        "model_ready": True,
        "app_version": "2.0.0",
        "model_version": "1.5.0",
        "device": "cpu",
    }


@pytest.mark.parametrize("body", [b"original document in a non-JSON error", []])
def test_non_json_or_non_object_responses_are_sanitized(api, body):
    api.health = body
    with pytest.raises(FilterError, match="^invalid_rizzo_response$"):
        rizzo_api.health(api.port)


@pytest.mark.parametrize(
    "operation", ["success", "outside", "unavailable", "malformed"]
)
def test_worker_returns_only_filtered_text_or_fixed_errors(
    tmp_path, api, monkeypatch, operation
):
    from mparanza_privacy_filter import rizzo_worker

    path = tmp_path / "sample.txt"
    path.write_text("Anna writes.")
    request = {"path": str(path), "input_root": str(tmp_path), "rizzo_port": api.port}
    if operation == "outside":
        request["input_root"] = str(tmp_path / "other")
    if operation == "unavailable":
        api.status = 500
    stream = io.StringIO()
    monkeypatch.setattr(
        sys,
        "stdin",
        io.StringIO("{" if operation == "malformed" else json.dumps(request)),
    )
    monkeypatch.setattr(sys, "stdout", stream)
    rizzo_worker.main()
    expected = {
        "success": {
            "redacted_text": "[FULLNAME_1] writes.",
            "detection_counts": {"FULLNAME": 1},
            "source_characters": 12,
        },
        "outside": {"error": "outside_input_directory"},
        "unavailable": {"error": "rizzo_unavailable"},
        "malformed": {"error": "processing_failed"},
    }
    assert json.loads(stream.getvalue()) == expected[operation]
    assert "Anna" not in stream.getvalue()


@pytest.mark.parametrize(
    "field,value",
    [("app_version", "Anna"), ("model_version", None), ("device", "secret path")],
)
def test_health_rejects_unrestricted_metadata(api, field, value):
    api.health[field] = value
    with pytest.raises(FilterError, match="^invalid_rizzo_response$"):
        rizzo_api.health(api.port)


def test_unavailable_service_status_is_actionable_and_sanitized(tmp_path, api):
    api.health["model_loaded"] = False
    service = FilterService(
        Settings(
            tmp_path, tmp_path / "out", tmp_path, engine="rizzo", rizzo_port=api.port
        )
    )
    result = service.status()
    assert result["model_ready"] is False
    assert result["error"] == "rizzo_unavailable"
    assert "secret" not in json.dumps(result)


def test_stdio_file_batch_and_read_preserve_originals_and_exclude_raw_fields(
    tmp_path, api
):
    source, output = tmp_path / "input", tmp_path / "output"
    source.mkdir()
    original = source / "sample.txt"
    original.write_text("Anna writes.")

    async def exercise():
        params = StdioServerParameters(
            command=sys.executable,
            args=[
                "-I",
                "-m",
                "mparanza_privacy_filter.server",
                "--engine",
                "rizzo",
                "--input-dir",
                str(source),
                "--output-dir",
                str(output),
                "--rizzo-port",
                str(api.port),
            ],
        )
        async with stdio_client(params) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()
                listing = await session.list_tools()
                status = await session.call_tool("rizzo_pii_status", {})
                batch = await session.call_tool(
                    "rizzo_pii_batch", {"paths": ["sample.txt", "missing-secret.txt"]}
                )
                receipt = json.loads(batch.content[0].text)["results"][0]
                result = await session.call_tool(
                    "rizzo_pii_read", {"artifact_id": receipt["artifact_id"]}
                )
                return listing, status, batch, result, receipt

    listing, status, batch, result, receipt = asyncio.run(exercise())
    assert {t.name for t in listing.tools} == {
        "rizzo_pii_status",
        "rizzo_pii_file",
        "rizzo_pii_batch",
        "rizzo_pii_read",
    }
    assert json.loads(status.content[0].text)["model_ready"]
    assert receipt["engine"] == "rizzo"
    assert "Anna" not in batch.model_dump_json() + result.model_dump_json()
    assert "missing-secret" not in batch.model_dump_json()
    assert json.loads(result.content[0].text)["redacted_text"] == "[FULLNAME_1] writes."
    assert original.read_text() == "Anna writes."
    assert Path(receipt["output_path"]).read_text() == "[FULLNAME_1] writes."
    restarted = FilterService(
        Settings(source, output, tmp_path, engine="rizzo", rizzo_port=api.port)
    )
    assert (
        restarted.read_result(receipt["artifact_id"])["redacted_text"]
        == "[FULLNAME_1] writes."
    )


def test_rizzo_installer_does_not_install_models_or_change_user_configuration(
    tmp_path, monkeypatch
):
    spec = importlib.util.spec_from_file_location(
        "privacy_install", Path(__file__).parents[1] / "install.py"
    )
    installer = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(installer)
    source, runtime = tmp_path / "input", tmp_path / "runtime"
    source.mkdir()
    commands = []
    monkeypatch.setattr(
        installer.venv,
        "EnvBuilder",
        lambda **k: SimpleNamespace(create=lambda p: p.mkdir()),
    )
    monkeypatch.setattr(
        installer.subprocess, "run", lambda command, **k: commands.append(command)
    )
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "install.py",
            "--engine",
            "rizzo",
            "--runtime-dir",
            str(runtime),
            "--input-dir",
            str(source),
            "--output-dir",
            str(tmp_path / "output"),
            "--rizzo-port",
            "5010",
        ],
    )
    installer.main()
    config = tomllib.loads((runtime / "codex-mcp.toml").read_text())
    assert set(config["mcp_servers"]) == {"rizzo_pii"}
    assert config["mcp_servers"]["rizzo_pii"]["args"][-2:] == ["--rizzo-port", "5010"]
    assert "--model-dir" not in config["mcp_servers"]["rizzo_pii"]["args"]
    assert len(commands) == 1
    assert commands[0][5].endswith("requirements.txt")
    assert not (runtime / "model").exists()
