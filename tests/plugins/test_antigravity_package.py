"""The public Antigravity ZIP must retain its source bytes and exact version."""

from __future__ import annotations

import importlib
import json
from pathlib import Path
from zipfile import ZipFile

import pytest


def builder_case(tmp_path: Path, monkeypatch):
    """Provide a small package and replace process startup with a local stub."""
    monkeypatch.syspath_prepend(str(Path(__file__).resolve().parents[2] / "scripts"))
    builder = importlib.import_module("build_antigravity_plugin")
    entries = {
        "vera/.codex-plugin/plugin.json": b'{"name":"vera","version":"0.1.333"}',
        "vera/skills/vera/SKILL.md": b"source skill",
    }
    monkeypatch.setattr(builder, "package_entries", lambda: entries)
    monkeypatch.setattr(builder, "verify_packaged_mcp", lambda *args, **kwargs: [])
    output = tmp_path / "vera.zip"
    metadata = tmp_path / "vera.json"
    builder.build_package(output, metadata)
    return builder, output, metadata


def test_rebuild_produces_identical_download_and_matching_version(
    tmp_path, monkeypatch
):
    builder, output, metadata = builder_case(tmp_path, monkeypatch)
    previous = output.read_bytes()

    builder.build_package(output, metadata)

    assert output.read_bytes() == previous
    assert json.loads(metadata.read_text()) == {"name": "vera", "version": "0.1.333"}


def test_check_rejects_modified_skill_even_with_same_version(tmp_path, monkeypatch):
    builder, output, metadata = builder_case(tmp_path, monkeypatch)
    with ZipFile(output) as archive:
        manifest = archive.read("vera/.codex-plugin/plugin.json")
    with ZipFile(output, "w") as archive:
        archive.writestr("vera/.codex-plugin/plugin.json", manifest)
        archive.writestr("vera/skills/vera/SKILL.md", "stale skill")

    with pytest.raises(ValueError, match="verification failed"):
        builder.verify_package(output, metadata)


def test_check_rejects_incorrect_website_version(tmp_path, monkeypatch):
    builder, output, metadata = builder_case(tmp_path, monkeypatch)
    metadata.write_text('{"name":"vera","version":"0.1.268"}')

    with pytest.raises(ValueError, match="download version does not match"):
        builder.verify_package(output, metadata)


def test_check_exercises_antigravity_config_and_rejects_broken_server(
    tmp_path, monkeypatch
):
    builder, output, metadata = builder_case(tmp_path, monkeypatch)

    def broken_server(path, roots, config_name):
        assert config_name == "mcp_config.json"
        return ["server failed to start"]

    monkeypatch.setattr(builder, "verify_packaged_mcp", broken_server)

    with pytest.raises(ValueError, match="server failed to start"):
        builder.verify_package(output, metadata)
