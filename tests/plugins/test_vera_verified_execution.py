from __future__ import annotations

import hashlib
import importlib.util
import json
import shutil
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

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
    (root / ".codex-plugin").mkdir()
    (root / ".codex-plugin/plugin.json").write_text(
        json.dumps({"name": "vera", "version": "0.1.407"})
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
        "reporting_product.py",
    ):
        shutil.copyfile(ROOT / "plugins/vera/scripts" / name, scripts / name)

    (scripts.parent / ".codex-plugin").mkdir()
    (scripts.parent / ".codex-plugin/plugin.json").write_text(
        json.dumps({"name": "vera", "version": "0.1.407"})
    )

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

    with pytest.raises(ValueError, match="execution digest index; update"):
        recovery.prepare_execution_root(root, "journal-bank-reconciliation")


def test_unrelated_module_preserves_existing_launch(tmp_path):
    recovery = load_recovery()
    root = tmp_path / "no-copy"
    (root / ".codex-plugin").mkdir(parents=True)
    (root / ".codex-plugin/plugin.json").write_text(
        json.dumps({"name": "vera", "version": "0.1.407"})
    )

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
    reports = []

    def record_failure(workflow, stage, message, **details):
        reports.append((workflow, stage, details))
        return {"reporting": "test-isolated"}

    # This deliberately failed helper must never send fixture data to production.
    monkeypatch.setitem(
        sys.modules,
        "operational_incidents",
        SimpleNamespace(
            report_failure=record_failure,
            report_pdf_recovery=lambda *args: None,
            record_success=lambda *args: None,
            execution_identity=lambda *args: {
                "operation_id": "00000000-0000-0000-0000-000000000001"
            },
            record_execution_progress=lambda *args: None,
            diagnostic_directory=lambda: tmp_path,
            retain_diagnostic=lambda path, receipt: path,
        ),
    )
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

    def run(prepared, arguments, **kwargs):
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
        assert len(reports) == 1
        assert reports[0][:2] == (
            "journal-bank-reconciliation",
            "helper:inspect_inputs.py",
        )
        details = reports[0][2]
        assert details["error_type"] == "HelperExit"
        assert details["exit_code"] == 17
        assert details["measurements"] == {
            "diagnostic_review_pending": True,
            "stderr_bytes": 0,
        }
        assert details["capture_state"] == "unavailable"
        assert (
            details["technical_diagnostics"][0]["error_code"]
            == "reporting.evidence-missing"
        )
        assert result == 17
        assert len(delegated) == 1
        assert delegated[0][0] != root
        assert delegated[0][1] == arguments
        assert not delegated[0][0].exists()
    finally:
        if delegated:
            shutil.rmtree(delegated[0][0], ignore_errors=True)


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


def test_host_description_quoting_preserves_verified_execution(tmp_path):
    """Reproduce Cowork's observed YAML repair before running real integrity checks."""
    recovery = load_recovery()
    root = installation(tmp_path)
    skill = root / "skills/business-planning/SKILL.md"
    skill.parent.mkdir(parents=True)
    shutil.copyfile(ROOT / "plugins/vera/skills/business-planning/SKILL.md", skill)
    write_index(root)
    text = skill.read_text(encoding="utf-8")
    description_line = next(
        line for line in text.splitlines() if line.startswith("description: ")
    )
    description = description_line.removeprefix("description: ")
    # The installed 0.1.359 file differs only by quotes around this colon-bearing
    # scalar. A valid source scalar must remain unchanged by that host repair.
    if not description.startswith('"'):
        skill.write_text(
            text.replace(description_line, "description: " + json.dumps(description)),
            encoding="utf-8",
        )

    prepared = recovery.prepare_execution_root(root, "journal-bank-reconciliation")

    assert prepared == root
    assert json.loads(description).startswith("Prepare one business plan")


@pytest.mark.parametrize("snapshot", [False, True])
def test_owned_copy_release_preserves_installation_and_alias(tmp_path, snapshot):
    recovery = load_recovery()
    root = installation(tmp_path)
    source = (
        root / "modules/journal-bank-reconciliation/scripts/implementation_bootstrap.py"
    )
    alias = tmp_path / "host-alias"
    alias.hardlink_to(source)
    original = alias.read_bytes()
    prepared = recovery.prepare_execution_root(
        root, "journal-bank-reconciliation", snapshot=snapshot
    )
    assert prepared.exists()

    recovery.release_execution_root(prepared)
    recovery.release_execution_root(prepared)
    recovery.release_execution_root(root)

    assert not prepared.exists()
    assert source.read_bytes() == original
    assert alias.read_bytes() == original
    assert source.stat().st_nlink == 2


def test_cleanup_never_removes_borrowed_temporary_or_symlink_target(tmp_path):
    recovery = load_recovery()
    borrowed = tmp_path / "vera-verified-not-owned"
    borrowed.mkdir()
    data = borrowed / "keep.txt"
    data.write_text("client output")
    link = tmp_path / "alias"
    link.symlink_to(borrowed, target_is_directory=True)

    recovery.release_execution_root(borrowed)
    recovery.release_execution_root(link)

    assert data.read_text() == "client output"
    assert link.is_symlink()


def test_hardlinked_preflight_leaves_no_copy(tmp_path, monkeypatch, capsys):
    recovery = load_recovery()
    root = installation(tmp_path)
    (tmp_path / "alias").hardlink_to(root / "components.json")
    temporary = tmp_path / "temp"
    temporary.mkdir()
    monkeypatch.setattr(recovery.tempfile, "gettempdir", lambda: str(temporary))
    monkeypatch.setattr(
        recovery, "__file__", str(root / "scripts/verified_execution.py")
    )

    assert recovery.main(["--module", "journal-bank-reconciliation"]) == 0

    assert json.loads(capsys.readouterr().out) == {"execution_root": str(root)}
    assert not list(temporary.glob("vera-*"))
    assert not list((temporary / ".vera-execution-leases").glob("*"))
    assert (root / "components.json").stat().st_nlink == 2


@pytest.mark.parametrize("failure", [RuntimeError, KeyboardInterrupt])
def test_interrupted_copy_preparation_leaves_no_partial_tree(
    tmp_path, monkeypatch, failure
):
    recovery = load_recovery()
    root = installation(tmp_path)
    (tmp_path / "alias").hardlink_to(root / "components.json")
    temporary = tmp_path / "temp"
    temporary.mkdir()
    monkeypatch.setattr(recovery.tempfile, "gettempdir", lambda: str(temporary))

    def fail(*args):
        raise failure("interrupted validation")

    monkeypatch.setattr(recovery, "_validate_module", fail)
    with pytest.raises(failure):
        recovery.prepare_execution_root(root, "journal-bank-reconciliation")

    assert not list(temporary.glob("vera-*"))
    assert not list((temporary / ".vera-execution-leases").glob("*"))
    assert root.exists()


def test_process_exit_releases_library_copy(tmp_path):
    root = installation(tmp_path)
    (tmp_path / "alias").hardlink_to(root / "components.json")
    code = (
        "import runpy,sys; from pathlib import Path; "
        "v=runpy.run_path(sys.argv[1]); "
        "p=v['prepare_execution_root'](Path(sys.argv[2]), 'journal-bank-reconciliation'); "
        "print(p, flush=True); assert p.exists()"
    )
    result = subprocess.run(
        [sys.executable, "-B", "-c", code, str(SCRIPT), str(root)],
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0, result.stderr
    assert not Path(result.stdout.strip()).exists()
    assert root.exists()


def test_locked_copy_cleanup_is_retried_without_changing_result(tmp_path, monkeypatch):
    recovery = load_recovery()
    root = installation(tmp_path)
    prepared = recovery.prepare_execution_root(
        root, "journal-bank-reconciliation", snapshot=True
    )
    remove = recovery.shutil.rmtree

    def locked(*args, **kwargs):
        raise PermissionError("file still open on Windows")

    monkeypatch.setattr(recovery.shutil, "rmtree", locked)
    recovery.release_execution_root(prepared)
    assert prepared.exists()
    monkeypatch.setattr(recovery.shutil, "rmtree", remove)

    recovery.release_execution_root(prepared)

    assert not prepared.exists()
    assert root.exists()


def test_cleanup_rejects_replaced_owned_directory(tmp_path):
    recovery = load_recovery()
    root = installation(tmp_path)
    prepared = recovery.prepare_execution_root(
        root, "journal-bank-reconciliation", snapshot=True
    )
    original = prepared.with_name(prepared.name + "-moved")
    prepared.rename(original)
    prepared.mkdir()
    output = prepared / "keep.txt"
    output.write_text("unrelated output")
    try:
        recovery.release_execution_root(prepared)
        assert output.read_text() == "unrelated output"
        assert original.exists()
    finally:
        shutil.rmtree(prepared)
        shutil.rmtree(original)


@pytest.mark.parametrize("outcome", [0, 17, RuntimeError, KeyboardInterrupt])
def test_managed_run_releases_copy_on_every_exit(tmp_path, monkeypatch, outcome):
    root = installation(tmp_path)
    (tmp_path / "alias").hardlink_to(root / "components.json")
    monkeypatch.syspath_prepend(str(SCRIPT.parent))
    spec = importlib.util.spec_from_file_location(
        "managed_copy_lifetime_test", SCRIPT.parent / "managed_python_runtime.py"
    )
    launcher = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(launcher)
    monkeypatch.setattr(
        launcher, "__file__", str(root / "scripts/managed_python_runtime.py")
    )
    observed = []

    def run(prepared, *args):
        observed.append(prepared)
        assert prepared.exists()
        assert prepared != root
        if isinstance(outcome, type):
            raise outcome("helper interrupted")
        return outcome

    monkeypatch.setattr(launcher, "run_verified_helper", run)
    args = [
        "--module",
        "journal-bank-reconciliation",
        "run",
        "scripts/inspect_inputs.py",
    ]
    if isinstance(outcome, type):
        with pytest.raises(outcome):
            launcher.main(args)
    else:
        assert launcher.main(args) == outcome

    assert len(observed) == 1
    assert not observed[0].exists()
    assert root.exists()


@pytest.mark.skipif(sys.platform == "win32", reason="POSIX kernel leases")
def test_orphan_recovery_preserves_live_borrowed_replaced_and_symlink_roots(
    tmp_path, monkeypatch
):
    recovery = load_recovery()
    temporary = tmp_path / "temporary"
    temporary.mkdir()
    monkeypatch.setattr(recovery.tempfile, "gettempdir", lambda: str(temporary))
    live = temporary / "vera-verified-live"
    live.mkdir()
    (live / "code").write_text("live code")
    recovery.own_execution_root(live)
    borrowed = temporary / "vera-verified-borrowed"
    borrowed.mkdir()
    (borrowed / "client").write_text("preserve client material")
    replaced = temporary / "vera-verified-replaced"
    replaced.mkdir()
    recovery.own_execution_root(replaced)
    descriptor = recovery._LEASES.pop(replaced)
    import os

    os.close(descriptor)
    saved = temporary / "saved-original"
    replaced.rename(saved)
    replaced.mkdir()
    (replaced / "client").write_text("replacement")
    linked = temporary / "vera-verified-linked"
    linked.mkdir()
    recovery.own_execution_root(linked)
    os.close(recovery._LEASES.pop(linked))
    linked.rmdir()
    linked.symlink_to(borrowed, target_is_directory=True)

    recovery.recover_abandoned_execution_roots()

    assert (live / "code").read_text() == "live code"
    assert (borrowed / "client").read_text() == "preserve client material"
    assert (replaced / "client").read_text() == "replacement"
    assert linked.is_symlink()
    recovery.release_execution_root(live)


@pytest.mark.skipif(sys.platform == "win32", reason="POSIX inherited kernel lease")
def test_owner_cleanup_cannot_remove_code_held_by_detached_worker(
    tmp_path, monkeypatch
):
    import os
    import tempfile

    recovery = load_recovery()
    monkeypatch.setattr(recovery.tempfile, "gettempdir", lambda: str(tmp_path))
    root = Path(tempfile.mkdtemp(prefix="vera-verified-", dir=tmp_path))
    (root / "code").write_text("running")
    recovery.own_execution_root(root)
    worker = subprocess.Popen(
        [sys.executable, "-c", "import sys; sys.stdin.read()"],
        stdin=subprocess.PIPE,
        pass_fds=recovery.execution_lease_fds(root),
    )
    try:
        recovery.release_execution_root(root)
        recovery.recover_abandoned_execution_roots()
        assert (root / "code").read_text() == "running"
    finally:
        worker.communicate(timeout=10)
    recovery.recover_abandoned_execution_roots()
    assert not root.exists()
