"""Native apps speak MCP without leaking selected form/report data to chat."""

from __future__ import annotations

import importlib.util
import io
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]


@pytest.mark.parametrize(
    "product,script",
    [("lucia", "method_mcp"), ("lucia", "matter_mcp"), ("clara", "report_mcp")],
)
def test_native_app_protocol_discovery_errors_and_app_only_authority(
    monkeypatch, product, script
):
    sys.path.insert(0, str(ROOT / "plugins/lucia/scripts"))
    spec = importlib.util.spec_from_file_location(
        "protocol_" + script, ROOT / f"plugins/{product}/scripts/{script}.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    uri = module.URI
    messages = [
        {"method": "initialize", "params": {"protocolVersion": "2024-11-05"}},
        {"method": "ping"},
        {"method": "tools/list"},
        {"method": "resources/list"},
        {"method": "resources/templates/list"},
        {"method": "resources/read", "params": {"uri": uri}},
        {"method": "resources/read", "params": {"uri": "ui://unknown/other"}},
        {"method": "tools/call", "params": {"name": "unknown", "arguments": {}}},
    ]
    tool_names = {
        "method_mcp": "lucia_method_open",
        "matter_mcp": "lucia_matter_open",
        "report_mcp": "clara_report_open",
    }
    messages.append(
        {
            "method": "tools/call",
            "params": {
                "name": tool_names[script],
                "arguments": {"unexpected": "private-marker-should-not-leak"},
            },
        }
    )
    stream = (
        "malformed\n[]\n" + json.dumps({"method": "notifications/initialized"}) + "\n"
    )
    stream += "".join(
        json.dumps({"jsonrpc": "2.0", "id": index, **message}) + "\n"
        for index, message in enumerate(messages)
    )
    output = io.StringIO()
    monkeypatch.setattr(sys, "stdin", io.StringIO(stream))
    monkeypatch.setattr(sys, "stdout", output)
    module.main()
    responses = [json.loads(line) for line in output.getvalue().splitlines()]
    assert len(responses) == len(messages)
    assert responses[0]["result"]["protocolVersion"] == "2024-11-05"
    tools = responses[2]["result"]["tools"]
    assert tools[0]["_meta"]["ui"]["resourceUri"] == uri
    assert all(tool["_meta"]["ui"]["visibility"] == ["app"] for tool in tools[1:])
    assert responses[4]["result"] == {"resourceTemplates": []}
    assert (
        responses[5]["result"]["contents"][0]["mimeType"] == "text/html;profile=mcp-app"
    )
    assert all(response["result"]["isError"] for response in responses[6:])
    assert "private-marker-should-not-leak" not in output.getvalue()
