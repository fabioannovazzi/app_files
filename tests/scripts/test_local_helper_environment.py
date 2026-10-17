from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from pathlib import Path

import pytest

from scripts.local_helper_environment import local_helper_environment

ROOT = Path(__file__).resolve().parents[2]


@pytest.mark.parametrize("platform", ["macos", "windows", "linux"])
def test_child_environment_excludes_credentials_and_preserves_platform_paths(
    platform: str,
) -> None:
    host = {
        "PATH": "/bin",
        "HOME": "/home/user",
        "VIRTUAL_ENV": "/venv",
        "MPARANZA_REVIEW_NODE": "/node",
        "LANG": "en_US.UTF-8",
        "GITHUB_TOKEN": "fake-token",
        "OPENAI_API_KEY": "fake-key",
    }
    if platform == "windows":
        host.update(
            {
                "Path": "C:/bin",
                "SystemRoot": "C:/Windows",
                "USERPROFILE": "C:/Users/user",
            }
        )
    actual = local_helper_environment(python="chosen-python", environ=host)
    allowed = set(
        json.loads((ROOT / "scripts/local_helper_environment.json").read_text())
    )
    assert {key.upper() for key in actual} <= allowed
    assert "GITHUB_TOKEN" not in actual
    assert "OPENAI_API_KEY" not in actual
    assert "TEMP" not in actual
    assert actual["PYTHON"] == "chosen-python"
    assert actual["MPARANZA_REVIEW_NODE"] == "/node"
    if platform == "windows":
        assert actual["SystemRoot"] == "C:/Windows"
        assert actual["Path"] == "C:/bin"


def test_node_child_environment_matches_shared_allowlist() -> None:
    host = {
        "PATH": "/bin",
        "SystemRoot": "C:/Windows",
        "PYTHON": sys.executable,
        "GITHUB_TOKEN": "fake-token",
        "OPENAI_API_KEY": "fake-key",
    }
    code = "const h=require('./scripts/local_helper_environment.cjs'); process.stdout.write(JSON.stringify(h.localHelperEnvironment(JSON.parse(process.argv[1]))));"
    result = subprocess.run(
        ["node", "-e", code, json.dumps(host)],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=True,
    )
    assert json.loads(result.stdout) == local_helper_environment(environ=host)


def test_check_entries_generated_helpers_match_canonical_source() -> None:
    assert (
        ROOT / "plugins/check-entries/scripts/local_helper_environment.json"
    ).read_bytes() == (ROOT / "scripts/local_helper_environment.json").read_bytes()
    assert (
        ROOT / "plugins/check-entries/scripts/local_helper_environment.cjs"
    ).read_bytes() == (ROOT / "scripts/local_helper_environment.cjs").read_bytes()


def test_review_child_receives_no_credentials(monkeypatch, tmp_path: Path) -> None:
    spec = importlib.util.spec_from_file_location(
        "environment_test_workbench", ROOT / "scripts/serve_review_workbench.py"
    )
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    monkeypatch.setenv("GITHUB_TOKEN", "fake-token")
    monkeypatch.setenv("OPENAI_API_KEY", "fake-key")
    monkeypatch.setattr(module, "_node_executable", lambda: "node")
    captured = {}

    def run(*args, **kwargs):
        captured.update(kwargs["env"])
        return subprocess.CompletedProcess(
            args, 0, '{"id":1,"result":{"content":[]}}', ""
        )

    monkeypatch.setattr(module.subprocess, "run", run)
    workbench = module.LocalReviewWorkbench(tmp_path, tmp_path)
    monkeypatch.setattr(module, "_server_tool_args", lambda *_: {})
    monkeypatch.setattr(module, "_with_vera_customer_context", lambda *_: {})
    monkeypatch.setattr(
        module, "_adapter", lambda *_: {"saveTool": "save", "applyTool": "apply"}
    )
    module.call_review_tool(workbench, "save", {})
    allowed = set(
        json.loads((ROOT / "scripts/local_helper_environment.json").read_text())
    )
    assert {key.upper() for key in captured} <= allowed
    assert "GITHUB_TOKEN" not in captured
    assert "OPENAI_API_KEY" not in captured


def test_filtered_node_environment_starts_selected_python(monkeypatch) -> None:
    monkeypatch.setenv("GITHUB_TOKEN", "fake-token")
    monkeypatch.setenv("OPENAI_API_KEY", "fake-key")
    monkeypatch.setenv("PYTHON", sys.executable)
    code = """
const {spawnSync} = require('node:child_process');
const {localHelperEnvironment} = require('./scripts/local_helper_environment.cjs');
const child = spawnSync(process.env.PYTHON, ['-I', '-B', '-c',
  'import json, os, sys; sys.stdout.write(json.dumps({"python": sys.executable, "github": "GITHUB_TOKEN" in os.environ, "openai": "OPENAI_API_KEY" in os.environ}))'],
  {env: localHelperEnvironment(), encoding: 'utf8'});
if (child.error) throw child.error;
process.stdout.write(child.stdout);
process.stderr.write(child.stderr);
process.exit(child.status);
"""
    result = subprocess.run(
        ["node", "-e", code], cwd=ROOT, text=True, capture_output=True, check=True
    )
    assert json.loads(result.stdout) == {
        "python": sys.executable,
        "github": False,
        "openai": False,
    }
