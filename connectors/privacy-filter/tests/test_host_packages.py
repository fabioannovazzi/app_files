"""Exercise the commands consumers receive, including the generated Cowork ZIP."""

from __future__ import annotations

import asyncio
import importlib.util
import json
import sys
import tomllib
from pathlib import Path
from types import SimpleNamespace
from zipfile import ZipFile

import pytest
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

__all__: list[str] = []


@pytest.fixture
def installer():
    spec = importlib.util.spec_from_file_location(
        "connector_installer", Path(__file__).parents[1] / "install.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def host_entry(runtime: Path, host: str, name: str) -> dict:
    """Read the real distribution format of each desktop host."""
    if host == "codex":
        return tomllib.loads((runtime / "codex-mcp.toml").read_text())["mcp_servers"][
            name
        ]
    if host == "antigravity":
        return json.loads((runtime / "antigravity-mcp.json").read_text())["mcpServers"][
            name
        ]
    with ZipFile(runtime / "cowork-connector.zip") as archive:
        return json.loads(archive.read(".mcp.json"))["mcpServers"][name]


@pytest.mark.parametrize(
    "engine,name",
    [("openai", "privacy_filter"), ("gliner2", "gliner2_pii"), ("rizzo", "rizzo_pii")],
)
@pytest.mark.parametrize("host", ["codex", "cowork", "antigravity"])
def test_native_host_configuration_preserves_paths_and_only_selected_engine(
    tmp_path, installer, engine, name, host
):
    python = Path("C:\\Program Files\\Python\\python.exe")
    source = Path("C:\\Studio Zürich\\Originali")
    output = tmp_path / 'Filtered "copies"'

    installer.write_host_files(tmp_path, python, source, output, engine, 5010)

    entry = host_entry(tmp_path, host, name)
    assert entry["command"] == str(python)
    assert entry["args"][3:7] == [
        "--input-dir",
        str(source),
        "--output-dir",
        str(output),
    ]
    assert "shell" not in entry
    assert "serverUrl" not in entry
    assert entry["args"][:3] == ["-I", "-m", "mparanza_privacy_filter.server"]


def test_cowork_plugin_contains_only_one_local_connector_and_no_model(
    tmp_path, installer
):
    installer.write_host_files(
        tmp_path, Path(sys.executable), tmp_path, tmp_path / "out", "rizzo", 5005
    )

    with ZipFile(tmp_path / "cowork-connector.zip") as archive:
        manifest = json.loads(archive.read(".claude-plugin/plugin.json"))
        config = json.loads(archive.read(manifest["mcpServers"].removeprefix("./")))
        names = set(archive.namelist())
    assert manifest["name"] == "mparanza-rizzo-pii"
    assert set(config["mcpServers"]) == {"rizzo_pii"}
    assert names == {
        ".claude-plugin/plugin.json",
        ".mcp.json",
        "SETUP.md",
        "skills/filter-local-documents/SKILL.md",
    }


@pytest.mark.parametrize("host", ["codex", "cowork", "antigravity"])
def test_generated_host_command_runs_real_stdio_filter_and_read(
    tmp_path, installer, api, host
):
    source = tmp_path / "Input folder"
    source.mkdir()
    original = source / "sample.txt"
    original.write_text("Anna writes.")
    installer.write_host_files(
        tmp_path,
        Path(sys.executable),
        source,
        tmp_path / "Output folder",
        "rizzo",
        api.port,
    )
    entry = host_entry(tmp_path, host, "rizzo_pii")

    async def exercise():
        params = StdioServerParameters(command=entry["command"], args=entry["args"])
        async with stdio_client(params) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()
                status = await session.call_tool("rizzo_pii_status", {})
                result = await session.call_tool(
                    "rizzo_pii_file", {"path": "sample.txt"}
                )
                receipt = json.loads(result.content[0].text)
                filtered = await session.call_tool(
                    "rizzo_pii_read", {"artifact_id": receipt["artifact_id"]}
                )
                return status, receipt, filtered

    status, receipt, filtered = asyncio.run(exercise())

    assert json.loads(status.content[0].text)["model_ready"] is True
    assert receipt["engine"] == "rizzo"
    assert (
        json.loads(filtered.content[0].text)["redacted_text"] == "[FULLNAME_1] writes."
    )
    assert original.read_text() == "Anna writes."
    assert "Anna" not in json.dumps(receipt) + filtered.model_dump_json()
    assert Path(receipt["output_path"]).is_file()


def test_configure_only_keeps_installed_runtime_and_does_not_download(
    tmp_path, monkeypatch, installer
):
    runtime = tmp_path / "runtime"
    python = (
        runtime
        / "venv"
        / ("Scripts/python.exe" if sys.platform == "win32" else "bin/python")
    )
    python.parent.mkdir(parents=True)
    python.write_bytes(b"existing runtime")
    (runtime / "engine.json").write_text('{"engine":"rizzo"}')
    monkeypatch.setattr(
        installer.subprocess, "run", lambda *a, **k: pytest.fail("Unexpected download")
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
            str(tmp_path),
            "--output-dir",
            str(tmp_path / "out"),
            "--configure-only",
        ],
    )

    installer.main()

    assert python.read_bytes() == b"existing runtime"
    assert (runtime / "cowork-connector.zip").is_file()
    assert (runtime / "antigravity-mcp.json").is_file()


@pytest.mark.parametrize("answer", ["n", "", "cancel"])
def test_guided_setup_cancellation_does_not_create_runtime_or_download(
    tmp_path, monkeypatch, installer, answer
):
    source = tmp_path / "input"
    runtime = tmp_path / "runtime"
    replies = iter(["3", str(source), str(tmp_path / "out"), answer])
    monkeypatch.setattr("builtins.input", lambda prompt: next(replies))
    monkeypatch.setattr(
        sys, "argv", ["install.py", "--setup", "--runtime-dir", str(runtime)]
    )

    with pytest.raises(SystemExit):
        installer.main()

    assert not runtime.exists()
    assert not source.exists()


def test_guided_setup_creates_selected_folders_and_all_host_files(
    tmp_path, monkeypatch, installer
):
    source, output, runtime = tmp_path / "input", tmp_path / "out", tmp_path / "runtime"
    replies = iter(["3", str(source), str(output), "y"])
    commands = []
    monkeypatch.setattr("builtins.input", lambda prompt: next(replies))
    monkeypatch.setattr(
        installer.venv,
        "EnvBuilder",
        lambda **k: SimpleNamespace(create=lambda p: p.mkdir()),
    )
    monkeypatch.setattr(
        installer.subprocess, "run", lambda command, **k: commands.append(command)
    )
    monkeypatch.setattr(
        sys, "argv", ["install.py", "--setup", "--runtime-dir", str(runtime)]
    )

    installer.main()

    assert source.is_dir()
    assert output.is_dir()
    assert len(commands) == 1
    assert (runtime / "codex-mcp.toml").is_file()
    assert (runtime / "cowork-connector.zip").is_file()
    assert (runtime / "antigravity-mcp.json").is_file()
