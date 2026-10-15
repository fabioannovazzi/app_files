"""Catch final-byte drift before any Vera release replaces a good package."""

from __future__ import annotations

import importlib.util
import stat
import subprocess
import sys
from dataclasses import replace
from pathlib import Path
from zipfile import ZipFile, ZipInfo

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))
from scripts.verify_vera_package import verify_vera_execution_zip

__all__ = []
HOSTS = {
    "codex": ("plugin_packages/vera/vera-plugin.zip", "vera/plugins/vera"),
    "chatgpt": ("plugin_packages/vera/vera-chatgpt-upload.zip", "."),
    "cowork": ("plugin_packages/vera/vera-claude-plugin.zip", "."),
    "antigravity": ("static/shared/vera/downloads/vera-antigravity-plugin.zip", "vera"),
}


def packaged_skill_cases():
    """Enumerate shipped skill entrypoints, including embedded modules."""
    cases = []
    for host, (filename, _) in HOSTS.items():
        with ZipFile(ROOT / filename) as archive:
            cases.extend(
                (host, name)
                for name in archive.namelist()
                if name.endswith("/SKILL.md")
            )
    return cases


@pytest.mark.parametrize("host,skill", packaged_skill_cases())
def test_finished_skill_yaml_requires_no_install_time_repair(host, skill):
    # YAML syntax is a mechanical host contract. A digest-consistent ZIP may
    # still be rewritten by the host when a description contains an unquoted colon.
    with ZipFile(ROOT / HOSTS[host][0]) as archive:
        source = archive.read(skill).decode("utf-8")
    frontmatter = source.split("\n---\n", 1)[0].removeprefix("---\n")

    metadata = yaml.safe_load(frontmatter)

    assert isinstance(metadata["name"], str)
    assert isinstance(metadata["description"], str)


def load_builder(name):
    spec = importlib.util.spec_from_file_location(name, ROOT / "scripts" / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def release_entries(host):
    filename, root = HOSTS[host]
    with ZipFile(ROOT / filename) as archive:
        entries = {
            name: archive.read(name)
            for name in archive.namelist()
            if not name.endswith("/")
        }
    # Derive the Codex bundle root from its actual layout.
    index = next(name for name in entries if name.endswith("execution-files.json"))
    root = str(Path(index).parent)
    return entries, root


def write_zip(path, entries):
    with ZipFile(path, "w") as archive:
        for name, content in entries.items():
            archive.writestr(name, content)


def alter_skill(entries):
    name = next(
        name
        for name in entries
        if name.endswith("contenzioso-tributario/SKILL.md") and "/modules/" not in name
    )
    entries[name] += b"\nSynthetic final edit after sealing.\n"
    return name


@pytest.mark.parametrize("host", HOSTS)
def test_finished_archive_passes_all_assured_modules(host):
    _, root = release_entries(host)

    assert verify_vera_execution_zip(ROOT / HOSTS[host][0], root) is None


@pytest.mark.parametrize("host", HOSTS)
def test_final_skill_edit_is_rejected_by_the_packaged_verifier(tmp_path, host):
    entries, root = release_entries(host)
    alter_skill(entries)
    archive = tmp_path / "stale-index.zip"
    write_zip(archive, entries)

    with pytest.raises(
        ValueError,
        match="Installation content mismatch: .*contenzioso-tributario/SKILL.md",
    ):
        verify_vera_execution_zip(archive, root)


@pytest.mark.parametrize("host", HOSTS)
def test_builder_rejects_stale_index_before_replacing_any_release(
    tmp_path, monkeypatch, host
):
    entries, _ = release_entries(host)
    alter_skill(entries)
    output = tmp_path / "release.zip"
    output.write_bytes(b"previous release")
    public = tmp_path / "public.zip"
    public.write_bytes(b"previous public release")
    directory = tmp_path / "unpacked"
    directory.mkdir()
    marker = directory / "previous.txt"
    marker.write_text("previous directory")
    metadata = tmp_path / "release.json"
    metadata.write_bytes(b"previous metadata")
    if host == "cowork":
        builder = load_builder("build_claude_plugin_zip")
        _, packages = builder.load_configuration()
        package = replace(
            next(p for p in packages if p.plugin == "vera"),
            output_directory=directory,
            output_zip=output,
            public_zip=public,
        )
        monkeypatch.setattr(builder, "claude_package_entries", lambda _: entries)
        monkeypatch.setattr(
            builder._load_codex_builder(), "verify_packaged_mcp", lambda *a, **k: []
        )
        build = lambda: builder.build_package(package)
    elif host == "antigravity":
        builder = load_builder("build_antigravity_plugin")
        monkeypatch.setattr(builder, "package_entries", lambda _: entries)
        monkeypatch.setattr(builder, "verify_packaged_mcp", lambda *a, **k: [])
        build = lambda: builder.build_package(output, metadata)
    else:
        builder = load_builder("build_codex_plugin_zip")
        package = replace(
            next(p for p in builder.load_bundles() if p.name == "vera"),
            output_zip=output,
        )
        monkeypatch.setattr(builder, "verify_packaged_mcp", lambda *a, **k: [])
        if host == "codex":
            monkeypatch.setattr(builder, "expected_zip_entries", lambda _: entries)
            build = lambda: builder.build_package(package)
        else:
            monkeypatch.setattr(builder, "chatgpt_upload_entries", lambda _: entries)
            build = lambda: builder.build_chatgpt_upload(package, output)

    with pytest.raises(ValueError, match="Installation content mismatch"):
        build()

    assert output.read_bytes() == b"previous release"
    assert public.read_bytes() == b"previous public release"
    assert marker.read_text() == "previous directory"
    assert metadata.read_bytes() == b"previous metadata"


@pytest.mark.parametrize(
    "missing", ["execution-files.json", "scripts/verified_execution.py"]
)
def test_missing_integrity_component_blocks_release(tmp_path, missing):
    entries, root = release_entries("cowork")
    del entries[missing]
    archive = tmp_path / "missing.zip"
    write_zip(archive, entries)

    with pytest.raises(ValueError, match="no .*execution"):
        verify_vera_execution_zip(archive, root)


@pytest.mark.parametrize("unsafe", ["../escape", "/absolute", "symlink"])
def test_unsafe_zip_entries_are_rejected_before_execution(tmp_path, unsafe):
    archive = tmp_path / "unsafe.zip"
    with ZipFile(archive, "w") as handle:
        entry = ZipInfo(unsafe)
        if unsafe == "symlink":
            entry.external_attr = (stat.S_IFLNK | 0o777) << 16
        handle.writestr(entry, b"target")

    with pytest.raises(ValueError, match="Unsafe ZIP entry|Symlink in ZIP"):
        verify_vera_execution_zip(archive, ".")


def test_unsafe_plugin_root_is_rejected(tmp_path):
    archive = tmp_path / "empty.zip"
    write_zip(archive, {})

    with pytest.raises(ValueError, match="Unsafe plugin root"):
        verify_vera_execution_zip(archive, "../outside")


def test_hung_verifier_fails_the_release(tmp_path, monkeypatch):
    archive = tmp_path / "timeout.zip"
    write_zip(archive, {"scripts/verified_execution.py": b"# fixture"})

    def timeout(*args, **kwargs):
        raise subprocess.TimeoutExpired("verification", kwargs["timeout"])

    monkeypatch.setattr("scripts.verify_vera_package.subprocess.run", timeout)

    with pytest.raises(ValueError, match="timed out"):
        verify_vera_execution_zip(archive, ".")


@pytest.mark.parametrize(
    "component",
    [
        "check-entries",
        "concordato-plan-review",
        "journal-sampling",
        "open-item-reconciliation",
    ],
)
@pytest.mark.parametrize("change", ["mixed", "extra", "missing"])
def test_chatgpt_module_contract_rejects_invalid_layout_even_with_fresh_index(
    tmp_path, component, change
):
    entries, root = release_entries("chatgpt")
    prefix = f"modules/{component}/"
    if change == "mixed":
        entries[prefix + ".app.json"] = b"{}"
    elif change == "extra":
        entries[prefix + "scripts/unexpected.py"] = b"# unexpected implementation"
    else:
        del entries[prefix + "scripts/review_mcp_server.cjs"]
    builder = load_builder("build_codex_plugin_zip")
    builder.add_vera_execution_manifest(entries)
    archive = tmp_path / "invalid-module.zip"
    write_zip(archive, entries)

    with pytest.raises(ValueError, match="Module integrity check failed"):
        verify_vera_execution_zip(archive, root)
