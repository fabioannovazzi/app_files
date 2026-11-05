"""Retiring an inspector must retain validation, decisions and model-policy checks."""

from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]


@pytest.mark.parametrize("component", ["prompt-optimizer", "deep-research-validator"])
def test_native_review_engine_keeps_business_tools_without_ui_resources(
    tmp_path, component
):
    worker = subprocess.Popen(
        ["node", str(ROOT / "plugins/lucia/scripts/review_engine_mcp.cjs"), component],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        text=True,
        env={**os.environ, "HOME": str(tmp_path), "USERPROFILE": str(tmp_path)},
    )

    def rpc(method, params=None):
        worker.stdin.write(
            json.dumps(
                {"jsonrpc": "2.0", "id": 1, "method": method, "params": params or {}}
            )
            + "\n"
        )
        worker.stdin.flush()
        return json.loads(worker.stdout.readline())

    try:
        initialized = rpc(
            "initialize",
            {
                "protocolVersion": "2024-11-05",
                "capabilities": {},
                "clientInfo": {"name": "native-engine-test", "version": "1"},
            },
        )["result"]
        assert "resources" not in initialized["capabilities"]
        tools = rpc("tools/list")["result"]["tools"]
        names = [tool["name"] for tool in tools]
        assert any(name.startswith("validate_") for name in names)
        assert any(name.startswith("save_") for name in names)
        assert any(name.startswith("apply_") for name in names)
        assert not any(name.startswith("render_") for name in names)
        assert all(
            not tool.get("_meta", {}).get("ui", {}).get("resourceUri") for tool in tools
        )
        assert rpc("resources/list")["result"] == {"resources": []}
        rejected = rpc(
            "tools/call", {"name": "render_prompt_optimizer_review", "arguments": {}}
        )
        assert rejected["error"]["code"] == -32601
    finally:
        worker.stdin.close()
        worker.wait(timeout=10)
