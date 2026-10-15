"""Catch final-byte drift before any Vera release replaces a good package."""

from __future__ import annotations

import importlib.util
import json
import os
import shutil
import stat
import subprocess
import sys
from dataclasses import replace
from pathlib import Path
from zipfile import ZipFile, ZipInfo

import pytest

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


@pytest.mark.skipif(shutil.which("zip") is None, reason="System ZIP path requires zip")
def test_system_zip_has_stable_file_times_despite_later_staged_content(
    tmp_path, monkeypatch
):
    builder = load_builder("build_codex_plugin_zip")
    original_writer = builder.write_entries_to_directory

    def stage_with_later_content(root, entries):
        original_writer(root, entries)
        os.utime(root / "vera/execution-files.json", (1700000000, 1700000000))
        os.utime(root / "vera/skill.md", (1800000000, 1800000000))

    monkeypatch.setattr(builder, "write_entries_to_directory", stage_with_later_content)
    archive_path = tmp_path / "package.zip"
    builder.write_system_zip(
        archive_path,
        {"vera/execution-files.json": b"index", "vera/skill.md": b"content"},
        "vera",
    )

    with ZipFile(archive_path) as archive:
        assert (
            archive.getinfo("vera/skill.md").date_time
            == archive.getinfo("vera/execution-files.json").date_time
        )
        assert archive.read("vera/skill.md") == b"content"


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
            archive.writestr(ZipInfo(name, (1980, 1, 1, 0, 0, 0)), content)


def alter_skill(entries):
    name = next(
        name
        for name in entries
        if name.endswith("journal-sampling/SKILL.md") and "/modules/" not in name
    )
    entries[name] += b"\nSynthetic final edit after sealing.\n"
    return name


@pytest.mark.parametrize("host", HOSTS)
def test_finished_archive_passes_all_assured_modules(host):
    _, root = release_entries(host)

    assert verify_vera_execution_zip(ROOT / HOSTS[host][0], root) is None


def test_utf8_course_manifests_pass_with_a_non_utf8_host_default(monkeypatch):
    read_text = Path.read_text

    def legacy_default(path, encoding=None, errors=None):
        return read_text(path, encoding=encoding or "cp1252", errors=errors)

    monkeypatch.setattr(Path, "read_text", legacy_default)

    assert verify_vera_execution_zip(ROOT / HOSTS["cowork"][0], ".") is None


@pytest.mark.parametrize("host", HOSTS)
def test_final_skill_edit_is_rejected_by_the_packaged_verifier(tmp_path, host):
    entries, root = release_entries(host)
    alter_skill(entries)
    archive = tmp_path / "stale-index.zip"
    write_zip(archive, entries)

    with pytest.raises(
        ValueError,
        match="Installation content mismatch: .*journal-sampling/SKILL.md",
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


def test_course_hash_drift_is_rejected_even_when_execution_index_matches(tmp_path):
    entries, root = release_entries("cowork")
    alter_skill(entries)
    load_builder("build_codex_plugin_zip").add_vera_execution_manifest(entries)
    archive = tmp_path / "stale-course.zip"
    write_zip(archive, entries)

    with pytest.raises(ValueError, match="Course source hash mismatch"):
        verify_vera_execution_zip(archive, root)


@pytest.mark.parametrize(
    ("source", "message"),
    [
        ("missing.py", "Missing course source"),
        ("../outside.py", "Unsafe course source path"),
    ],
)
def test_invalid_course_source_blocks_release(tmp_path, source, message):
    entries, root = release_entries("cowork")
    course_path = "assets/courses/journal-sampling/course.json"
    course = json.loads(entries[course_path])
    course["sources"][0]["path"] = source
    entries[course_path] = json.dumps(course).encode()
    load_builder("build_codex_plugin_zip").add_vera_execution_manifest(entries)
    archive = tmp_path / "invalid-course.zip"
    write_zip(archive, entries)

    with pytest.raises(ValueError, match=message):
        verify_vera_execution_zip(archive, root)


def test_index_older_than_indexed_member_blocks_release_even_with_matching_hashes(
    tmp_path,
):
    entries, root = release_entries("cowork")
    archive = tmp_path / "older-index.zip"
    with ZipFile(archive, "w") as handle:
        for name, content in entries.items():
            date = (
                (1980, 1, 2, 0, 0, 0) if name == "README.md" else (1980, 1, 1, 0, 0, 0)
            )
            handle.writestr(ZipInfo(name, date), content)

    with pytest.raises(ValueError, match="execution-files.json is older.*README.md"):
        verify_vera_execution_zip(archive, root)


def test_finished_archive_executes_each_real_cli_in_isolation(monkeypatch):
    original = subprocess.run
    commands = []

    def record(command, **kwargs):
        if "--module" in command:
            commands.append(command)
        return original(command, **kwargs)

    monkeypatch.setattr("scripts.verify_vera_package.subprocess.run", record)

    verify_vera_execution_zip(ROOT / HOSTS["cowork"][0], ".")

    assert [command[-1] for command in commands] == [
        "check-entries",
        "concordato-plan-review",
        "journal-bank-reconciliation",
        "journal-sampling",
        "open-item-reconciliation",
        "report-builder",
    ]
    assert all("-I" in command and "-B" in command for command in commands)


@pytest.mark.parametrize(
    "failed_module",
    [
        "check-entries",
        "concordato-plan-review",
        "journal-bank-reconciliation",
        "journal-sampling",
        "open-item-reconciliation",
        "report-builder",
    ],
)
def test_nonzero_cli_exit_blocks_release(monkeypatch, failed_module):
    original = subprocess.run

    def fail_one_cli(command, **kwargs):
        if "--module" in command and command[-1] == failed_module:
            return subprocess.CompletedProcess(command, 7, "", "synthetic CLI failure")
        return original(command, **kwargs)

    monkeypatch.setattr("scripts.verify_vera_package.subprocess.run", fail_one_cli)

    with pytest.raises(
        ValueError, match=f"CLI verification failed: {failed_module}.*exit 7"
    ):
        verify_vera_execution_zip(ROOT / HOSTS["cowork"][0], ".")


def test_hung_cli_blocks_release(monkeypatch):
    original = subprocess.run

    def hang_cli(command, **kwargs):
        if "--module" in command:
            raise subprocess.TimeoutExpired(command, kwargs["timeout"])
        return original(command, **kwargs)

    monkeypatch.setattr("scripts.verify_vera_package.subprocess.run", hang_cli)

    with pytest.raises(ValueError, match="CLI verification timed out: check-entries"):
        verify_vera_execution_zip(ROOT / HOSTS["cowork"][0], ".")
