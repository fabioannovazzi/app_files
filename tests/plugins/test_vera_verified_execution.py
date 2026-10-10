from __future__ import annotations

import hashlib
import importlib.util
import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "plugins/vera/scripts/verified_execution.py"


def load_recovery():
    spec = importlib.util.spec_from_file_location("vera_recovery_test", SCRIPT)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def installation(tmp_path: Path, component: str = "journal-bank-reconciliation"):
    root = tmp_path / "installed-vera"
    shutil.copytree(
        ROOT / "plugins" / component,
        root / "modules" / component,
        ignore=shutil.ignore_patterns("__pycache__", "*.pyc", "*.pyo"),
    )
    shutil.copytree(
        ROOT / "plugins/_shared/vendor/modules/vera_assurance",
        root / "vendor/modules/vera_assurance",
        ignore=shutil.ignore_patterns("__pycache__", "*.pyc", "*.pyo"),
    )
    shutil.copytree(
        ROOT / "plugins/_shared/vendor/modules/vera_journal_pdf",
        root / "vendor/modules/vera_journal_pdf",
        ignore=shutil.ignore_patterns("__pycache__", "*.pyc", "*.pyo"),
    )
    (root / "components.json").write_text(
        json.dumps({"plugins": [component]}), encoding="utf-8"
    )
    write_index(root)
    return root


def write_index(root: Path):
    files = {
        path.relative_to(root).as_posix(): hashlib.sha256(path.read_bytes()).hexdigest()
        for path in root.rglob("*")
        if path.is_file() and path.name != "execution-files.json"
    }
    (root / "execution-files.json").write_text(
        json.dumps({"schema_version": 1, "files": files})
    )


def test_clean_installation_keeps_original_root(tmp_path):
    recovery = load_recovery()
    root = installation(tmp_path)

    prepared = recovery.prepare_execution_root(root, "journal-bank-reconciliation")

    assert prepared == root


def test_managed_launcher_loads_by_path_outside_its_script_directory(tmp_path):
    scripts = tmp_path / "installed-vera" / "scripts"
    scripts.mkdir(parents=True)
    for name in (
        "managed_python_runtime.py",
        "_managed_python_runtime.py",
        "verified_execution.py",
    ):
        shutil.copyfile(ROOT / "plugins/vera/scripts" / name, scripts / name)

    result = subprocess.run(
        [
            sys.executable,
            "-I",
            "-B",
            "-c",
            "import runpy, sys; runtime=runpy.run_path(sys.argv[1]); "
            "runtime['main'](['--help'])",
            str(scripts / "managed_python_runtime.py"),
        ],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    assert "usage:" in result.stdout


@pytest.mark.parametrize("component", sorted(load_recovery().ASSURED_MODULES))
def test_hardlink_recovery_passes_unchanged_real_module_validator(tmp_path, component):
    recovery = load_recovery()
    root = installation(tmp_path, component)
    source = root / "modules" / component / "scripts/implementation_bootstrap.py"
    alias = tmp_path / "host-cache-alias"
    alias.hardlink_to(source)
    original = alias.read_bytes()

    prepared = recovery.prepare_execution_root(root, component)

    try:
        copied = prepared / source.relative_to(root)
        assert prepared != root
        assert copied.stat().st_nlink == 1
        assert copied.read_bytes() == original
        assert source.stat().st_nlink == 2
        assert alias.read_bytes() == original
        # Real module entrypoints still enforce their original boundary.
        result = subprocess.run(
            [
                sys.executable,
                "-B",
                str(copied.parent / "check_dependencies.py"),
                "--help",
            ],
            capture_output=True,
            text=True,
            check=False,
        )
        assert result.returncode == 0, result.stderr
        assert "usage:" in result.stdout
    finally:
        shutil.rmtree(prepared)


def test_shared_assurance_hardlink_is_materialized(tmp_path):
    recovery = load_recovery()
    root = installation(tmp_path)
    relative = "vendor/modules/vera_assurance/contracts.py"
    alias = tmp_path / "shared-alias"
    alias.hardlink_to(root / relative)

    prepared = recovery.prepare_execution_root(root, "journal-bank-reconciliation")

    try:
        assert (prepared / relative).stat().st_nlink == 1
        assert alias.stat().st_nlink == 2
    finally:
        shutil.rmtree(prepared)


@pytest.mark.parametrize(
    "mutation", ["altered", "missing", "extra", "extra_directory", "symlink", "fifo"]
)
def test_unsafe_installation_stops_before_executing_code(
    tmp_path, monkeypatch, mutation
):
    recovery = load_recovery()
    root = installation(tmp_path)
    source = root / "modules/journal-bank-reconciliation/scripts/inspect_inputs.py"
    if mutation == "altered":
        source.write_text("raise RuntimeError('must not execute')")
    elif mutation == "missing":
        source.unlink()
    elif mutation == "extra":
        (source.parent / "unexpected.py").write_text("# extra code")
    elif mutation == "extra_directory":
        (source.parent / "unexpected-directory").mkdir()
    elif mutation == "symlink":
        external = tmp_path / "external"
        source.rename(external)
        source.symlink_to(external)
    else:
        import os

        if not hasattr(os, "mkfifo"):
            pytest.skip("OS has no FIFO support")
        source.unlink()
        os.mkfifo(source)
    executed = []
    monkeypatch.setattr(
        recovery, "_validate_module", lambda *args: executed.append(args)
    )

    with pytest.raises(ValueError):
        recovery.prepare_execution_root(root, "journal-bank-reconciliation")

    assert executed == []


def test_write_denial_leaves_installation_unchanged(tmp_path, monkeypatch):
    recovery = load_recovery()
    root = installation(tmp_path)
    source = (
        root / "modules/journal-bank-reconciliation/scripts/implementation_bootstrap.py"
    )
    alias = tmp_path / "alias"
    alias.hardlink_to(source)
    original = source.read_bytes()

    def denied(**kwargs):
        raise PermissionError("host denied private storage")

    monkeypatch.setattr(recovery.tempfile, "mkdtemp", denied)

    with pytest.raises(PermissionError, match="host denied"):
        recovery.prepare_execution_root(root, "journal-bank-reconciliation")

    assert source.read_bytes() == original
    assert source.stat().st_nlink == 2


@pytest.mark.parametrize(
    "name", ["../outside", "/outside", "C:/outside", "a\\b", "a/./b"]
)
def test_manifest_rejects_paths_outside_exact_package(tmp_path, name):
    recovery = load_recovery()
    root = installation(tmp_path)
    (root / "execution-files.json").write_text(
        json.dumps({"schema_version": 1, "files": {name: "0" * 64}})
    )

    with pytest.raises(ValueError, match="index entry"):
        recovery.prepare_execution_root(root, "journal-bank-reconciliation")


def test_missing_index_requires_update(tmp_path):
    recovery = load_recovery()
    root = installation(tmp_path)
    (root / "execution-files.json").unlink()

    with pytest.raises(ValueError, match="update Vera"):
        recovery.prepare_execution_root(root, "journal-bank-reconciliation")


def test_unrelated_module_preserves_existing_launch(tmp_path):
    recovery = load_recovery()
    root = tmp_path / "no-copy"

    assert recovery.prepare_execution_root(root, "studio-archive") == root


def test_hardlinked_index_is_copied_without_touching_alias(tmp_path):
    recovery = load_recovery()
    root = installation(tmp_path)
    alias = tmp_path / "manifest-alias"
    alias.hardlink_to(root / recovery.MANIFEST)

    prepared = recovery.prepare_execution_root(root, "journal-bank-reconciliation")

    try:
        assert (prepared / recovery.MANIFEST).stat().st_nlink == 1
        assert alias.stat().st_nlink == 2
    finally:
        shutil.rmtree(prepared)


def test_failed_validation_removes_only_private_copy(tmp_path, monkeypatch):
    recovery = load_recovery()
    root = installation(tmp_path)
    alias = tmp_path / "alias"
    source = (
        root / "modules/journal-bank-reconciliation/scripts/implementation_bootstrap.py"
    )
    alias.hardlink_to(source)
    created = []

    def rejected(private, module):
        created.append(private)
        raise ValueError("original validator rejected copy")

    monkeypatch.setattr(recovery, "_validate_module", rejected)

    with pytest.raises(ValueError, match="original validator"):
        recovery.prepare_execution_root(root, "journal-bank-reconciliation")

    assert len(created) == 1
    assert not created[0].exists()
    assert source.exists()
    assert alias.stat().st_nlink == 2


def test_symlinked_installation_ancestor_is_rejected(tmp_path):
    recovery = load_recovery()
    root = installation(tmp_path)
    alias = tmp_path / "linked-directory"
    alias.symlink_to(root, target_is_directory=True)

    with pytest.raises(ValueError, match="real directory"):
        recovery.prepare_execution_root(alias, "journal-bank-reconciliation")


def test_managed_cli_delegates_to_private_root_and_keeps_helper_arguments(
    tmp_path, monkeypatch
):
    recovery = load_recovery()
    root = installation(tmp_path)
    alias = tmp_path / "alias"
    alias.hardlink_to(
        root / "modules/journal-bank-reconciliation/scripts/implementation_bootstrap.py"
    )
    monkeypatch.syspath_prepend(str(SCRIPT.parent))
    spec = importlib.util.spec_from_file_location(
        "vera_managed_recovery_test", SCRIPT.parent / "managed_python_runtime.py"
    )
    assert spec and spec.loader
    launcher = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(launcher)
    monkeypatch.setattr(
        launcher, "__file__", str(root / "scripts/managed_python_runtime.py")
    )
    delegated = []

    def run(prepared, arguments):
        delegated.append((prepared, arguments))
        return 17

    monkeypatch.setattr(launcher._IMPLEMENTATION, "main", run)
    arguments = [
        "--module",
        "journal-bank-reconciliation",
        "run",
        "scripts/inspect_inputs.py",
        "--module",
        "a-helper-option",
    ]

    result = launcher.main(arguments)

    try:
        assert result == 17
        assert len(delegated) == 1
        assert delegated[0][0] != root
        assert delegated[0][1] == arguments
    finally:
        if delegated:
            shutil.rmtree(delegated[0][0])


def test_preflight_cli_returns_verified_root(tmp_path, monkeypatch, capsys):
    recovery = load_recovery()
    root = installation(tmp_path)
    monkeypatch.setattr(
        recovery, "__file__", str(root / "scripts/verified_execution.py")
    )

    result = recovery.main(["--module", "journal-bank-reconciliation"])

    assert result == 0
    assert json.loads(capsys.readouterr().out) == {"execution_root": str(root)}


def test_preflight_cli_reports_corrupt_index_without_execution(
    tmp_path, monkeypatch, caplog
):
    recovery = load_recovery()
    root = installation(tmp_path)
    (root / recovery.MANIFEST).write_text("[]")
    monkeypatch.setattr(
        recovery, "__file__", str(root / "scripts/verified_execution.py")
    )

    result = recovery.main(["--module", "journal-bank-reconciliation"])

    assert result == 1
    assert "Invalid execution digest index" in caplog.text


@pytest.mark.parametrize("component", sorted(load_recovery().ASSURED_MODULES))
def test_numeric_host_use_markers_preserve_real_component_validation(
    tmp_path, component
):
    recovery = load_recovery()
    root = installation(tmp_path, component)
    markers = root / ".in_use"
    markers.mkdir()
    (markers / "71").write_text("host bookkeeping")
    (markers / "123").write_text("")

    prepared = recovery.prepare_execution_root(root, component)

    assert prepared == root
    assert (markers / "71").read_text() == "host bookkeeping"


@pytest.mark.parametrize(
    "mutation",
    [
        "code",
        "unicode",
        "nested",
        "symlink",
        "hardlink",
        "directory_symlink",
        "nested_marker",
        "altered_code",
    ],
)
def test_host_marker_exception_does_not_hide_unsafe_installation(
    tmp_path, monkeypatch, mutation
):
    recovery = load_recovery()
    root = installation(tmp_path)
    markers = root / ".in_use"
    markers.mkdir()
    marker = markers / "71"
    marker.write_text("")
    if mutation == "code":
        (markers / "unexpected.py").write_text("# must not execute")
    elif mutation == "unicode":
        (markers / "７１").write_text("")
    elif mutation == "nested":
        (markers / "72").mkdir()
    elif mutation == "symlink":
        marker.unlink()
        marker.symlink_to(root / "components.json")
    elif mutation == "hardlink":
        (tmp_path / "marker-alias").hardlink_to(marker)
    elif mutation == "directory_symlink":
        marker.unlink()
        markers.rmdir()
        markers.symlink_to(root / "modules", target_is_directory=True)
    elif mutation == "nested_marker":
        nested = root / "modules/journal-bank-reconciliation/.in_use"
        nested.mkdir()
        (nested / "71").write_text("")
    else:
        (
            root / "modules/journal-bank-reconciliation/scripts/inspect_inputs.py"
        ).write_text("# altered")
    executed = []
    monkeypatch.setattr(
        recovery, "_validate_module", lambda *args: executed.append(args)
    )

    with pytest.raises(ValueError):
        recovery.prepare_execution_root(root, "journal-bank-reconciliation")

    assert executed == []


def test_host_markers_are_excluded_from_hardlink_recovery_copy(tmp_path):
    recovery = load_recovery()
    root = installation(tmp_path)
    markers = root / ".in_use"
    markers.mkdir()
    (markers / "71").write_text("lease")
    source = (
        root / "modules/journal-bank-reconciliation/scripts/implementation_bootstrap.py"
    )
    (tmp_path / "host-alias").hardlink_to(source)

    prepared = recovery.prepare_execution_root(root, "journal-bank-reconciliation")

    try:
        assert prepared != root
        assert not (prepared / ".in_use").exists()
        assert (markers / "71").read_text() == "lease"
    finally:
        shutil.rmtree(prepared)
