"""Release regressions against extracted ZIPs, never checkout launchers."""

from __future__ import annotations

import importlib.util
import json
import sys
from dataclasses import replace
from pathlib import Path
from types import ModuleType
from zipfile import ZipFile

import pytest

__all__ = []

ROOT = Path(__file__).resolve().parents[2]


def load_builder(name: str) -> ModuleType:
    spec = importlib.util.spec_from_file_location(name, ROOT / "scripts" / f"{name}.py")
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def cowork_entries() -> dict[str, bytes]:
    builder = load_builder("build_claude_plugin_zip")
    _, packages = builder.load_configuration()
    vera = next(package for package in packages if package.plugin == "vera")
    return builder.claude_package_entries(vera)


def write_zip(path: Path, entries: dict[str, bytes]) -> None:
    with ZipFile(path, "w") as archive:
        for name, content in entries.items():
            archive.writestr(name, content)


@pytest.mark.parametrize("surface", ["cowork", "codex"])
def test_vera_zip_all_registered_servers_initialize_and_list_tools(
    surface: str, cowork_entries: dict[str, bytes], tmp_path: Path
) -> None:
    builder = load_builder("build_codex_plugin_zip")
    if surface == "cowork":
        entries = cowork_entries
        root = "."
        config = ".mcp.json"
    else:
        vera = next(
            package for package in builder.load_bundles() if package.name == "vera"
        )
        entries = builder.expected_zip_entries(vera)
        root = f"{vera.package_root}/plugins/vera"
        config = f"{root}/.mcp.json"
    archive = tmp_path / "vera.zip"
    write_zip(archive, entries)
    registered = json.loads((ROOT / "plugins" / "vera" / ".mcp.json").read_text())[
        "mcpServers"
    ]
    assert set(json.loads(entries[config])["mcpServers"]) == set(registered)
    assert registered

    errors = builder.verify_packaged_mcp(archive, [root])

    assert errors == []


@pytest.mark.parametrize(
    "missing_path",
    [
        "modules/financial-analysis/.codex-plugin/plugin.json",
        "modules/journal-bank-reconciliation/vendor/modules/vera_assurance/contracts.py",
    ],
)
def test_release_gate_rejects_missing_runtime_files(
    missing_path: str, cowork_entries: dict[str, bytes], tmp_path: Path
) -> None:
    builder = load_builder("build_codex_plugin_zip")
    entries = dict(cowork_entries)
    del entries[missing_path]
    archive = tmp_path / "broken.zip"
    write_zip(archive, entries)

    errors = builder.verify_packaged_mcp(archive, ["."])

    assert len(errors) == 1
    assert "packaged MCP startup failed" in errors[0]


def test_release_gate_preserves_exact_implementation_checks(
    cowork_entries: dict[str, bytes], tmp_path: Path
) -> None:
    builder = load_builder("build_codex_plugin_zip")
    entries = dict(cowork_entries)
    entries["modules/check-entries/scripts/unreceipted.py"] = b"# unexpected code\n"
    archive = tmp_path / "extra-file.zip"
    write_zip(archive, entries)

    errors = builder.verify_packaged_mcp(archive, ["."])

    assert "implementation filesystem does not match the exact contract" in errors[0]


def test_cowork_build_failure_preserves_existing_distributables(
    cowork_entries: dict[str, bytes], tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    builder = load_builder("build_claude_plugin_zip")
    _, packages = builder.load_configuration()
    vera = replace(
        next(package for package in packages if package.plugin == "vera"),
        output_directory=tmp_path / "directory",
        output_zip=tmp_path / "package.zip",
        public_zip=tmp_path / "public.zip",
    )
    vera.output_directory.mkdir()
    marker = vera.output_directory / "previous.txt"
    marker.write_text("previous release")
    vera.output_zip.write_bytes(b"previous archive")
    vera.public_zip.write_bytes(b"previous public archive")
    entries = dict(cowork_entries)
    del entries["modules/studio-archive/.codex-plugin/plugin.json"]
    monkeypatch.setattr(builder, "claude_package_entries", lambda _: entries)

    with pytest.raises(ValueError, match="packaged MCP startup failed"):
        builder.build_package(vera)

    assert marker.read_text() == "previous release"
    assert vera.output_zip.read_bytes() == b"previous archive"
    assert vera.public_zip.read_bytes() == b"previous public archive"


def test_release_gate_requires_node(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    builder = load_builder("build_codex_plugin_zip")
    monkeypatch.setattr(builder.shutil, "which", lambda _: None)

    errors = builder.verify_packaged_mcp(tmp_path / "unopened.zip", ["."])

    assert errors == ["Node.js is required for the packaged MCP release check"]


def test_release_gate_rejects_a_missing_server_configuration(tmp_path: Path) -> None:
    builder = load_builder("build_codex_plugin_zip")
    archive = tmp_path / "missing-configuration.zip"
    write_zip(archive, {"README.md": b"No launcher configuration"})

    errors = builder.verify_packaged_mcp(archive, ["."])

    assert errors == [".: packaged MCP configuration is missing"]


def test_initialize_success_is_insufficient_when_tools_list_fails(
    tmp_path: Path,
) -> None:
    builder = load_builder("build_codex_plugin_zip")
    server = b"""
const readline = require("node:readline");
readline.createInterface({input:process.stdin}).on("line", line => {
  const request = JSON.parse(line);
  if (!request.id) return;
  const payload = request.method === "initialize"
    ? {result:{protocolVersion:"2024-11-05",capabilities:{tools:{}},serverInfo:{name:"broken",version:"1"}}}
    : {error:{code:-32603,message:"tools cannot load"}};
  process.stdout.write(JSON.stringify({jsonrpc:"2.0",id:request.id,...payload})+"\\n");
});
"""
    entries = {
        ".mcp.json": json.dumps(
            {"mcpServers": {"broken": {"command": "node", "args": ["server.cjs"]}}}
        ).encode(),
        "server.cjs": server,
    }
    archive = tmp_path / "broken-tools.zip"
    write_zip(archive, entries)

    errors = builder.verify_packaged_mcp(archive, ["."])

    assert "Invalid or incomplete tools/list response" in errors[0]


def test_unresponsive_server_fails_release_instead_of_hanging(tmp_path: Path) -> None:
    builder = load_builder("build_codex_plugin_zip")
    archive = tmp_path / "unresponsive.zip"
    write_zip(
        archive,
        {
            ".mcp.json": json.dumps(
                {"mcpServers": {"hung": {"command": "node", "args": ["server.cjs"]}}}
            ).encode(),
            "server.cjs": b"setInterval(() => {}, 1000);",
        },
    )

    errors = builder.verify_packaged_mcp(archive, ["."])

    assert "MCP handshake timed out" in errors[0]
