"""Integrity stops must reach incident intake without executing damaged code."""

from __future__ import annotations

import hashlib
import importlib.util
import io
import json
import os
import shutil
import subprocess
import sys
import urllib.error
from pathlib import Path

import pytest

from modules.operational_incidents.contracts import Credentials, Report
from modules.operational_incidents.store import IncidentStore

ROOT = Path(__file__).resolve().parents[2]
TARGET = "skills/contenzioso-tributario/SKILL.md"


def installed_copy(tmp_path, host="codex"):
    root = tmp_path / "installed"
    (root / "scripts").mkdir(parents=True)
    for name in (
        "verified_execution.py",
        "operational_incidents.py",
        "reporting_product.py",
        "managed_python_runtime.py",
        "_managed_python_runtime.py",
        "check_dependencies.py",
    ):
        shutil.copyfile(ROOT / "plugins/vera/scripts" / name, root / "scripts" / name)
    for suffix in ("py", "json"):
        filename = f"local_helper_environment.{suffix}"
        shutil.copyfile(ROOT / "scripts" / filename, root / "scripts" / filename)
    metadata = (
        ".codex-plugin/plugin.json" if host == "codex" else ".claude-plugin/plugin.json"
    )
    (root / metadata).parent.mkdir(parents=True)
    (root / metadata).write_text(json.dumps({"name": "vera", "version": "0.1.387"}))
    (root / "components.json").write_text(json.dumps({"plugins": ["journal-sampling"]}))
    (root / "modules/journal-sampling").mkdir(parents=True)
    (root / "modules/journal-sampling/placeholder").write_text("synthetic component")
    (root / TARGET).parent.mkdir(parents=True)
    (root / TARGET).write_text("original synthetic skill")
    index = {
        p.relative_to(root).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
        for p in root.rglob("*")
        if p.is_file()
    }
    (root / "execution-files.json").write_text(
        json.dumps({"schema_version": 1, "files": index})
    )
    (root / TARGET).write_text("changed synthetic skill")
    return root, index


def entrypoint(root, name, monkeypatch):
    monkeypatch.syspath_prepend(str(root / "scripts"))
    for key, filename in (
        ("verified_execution", "verified_execution.py"),
        ("managed_python_runtime", "managed_python_runtime.py"),
        ("integrity_entry", name),
    ):
        spec = importlib.util.spec_from_file_location(key, root / "scripts" / filename)
        module = importlib.util.module_from_spec(spec)
        monkeypatch.setitem(sys.modules, key, module)
        spec.loader.exec_module(module)
    return module


def transport(tmp_path, monkeypatch, offline=False):
    state = tmp_path / "private-incidents"
    monkeypatch.setenv("MPARANZA_INCIDENT_STATE_DIR", str(state))
    monkeypatch.delenv("CLAUDE_PLUGIN_ROOT", raising=False)
    monkeypatch.delenv("MPARANZA_INCIDENT_HOST", raising=False)
    store = IncidentStore(tmp_path / "service.sqlite3")

    class Opener:
        def open(self, request, timeout):
            if offline:
                raise urllib.error.URLError("synthetic service outage")
            value = json.loads(request.data)
            credentials = Credentials.model_validate(value["credentials"])
            if request.full_url.endswith("/register"):
                response = store.register(credentials)
            else:
                response = store.report(
                    credentials, Report.model_validate(value["report"])
                )
            return io.BytesIO(json.dumps(response).encode())

    monkeypatch.setattr("urllib.request.build_opener", lambda *_: Opener())

    def isolated_reporter(command, **options):
        # Run the fixed child program with the test's in-process fake transport.
        # A separate real-process regression verifies Python import isolation.
        assert command[1:4] == ["-I", "-B", "-c"]
        output = io.StringIO()
        with monkeypatch.context() as child:
            child.setattr(sys, "argv", ["-c", command[-1]])
            child.setattr(sys, "stdin", io.StringIO(options["input"]))
            child.setattr(sys, "stdout", output)
            exec(command[-2], {})  # fixed, owned child program; never diagnostics
        return subprocess.CompletedProcess(command, 0, output.getvalue(), "")

    monkeypatch.setattr(subprocess, "run", isolated_reporter)
    return store, state


@pytest.mark.parametrize(
    "name,args",
    [
        ("verified_execution.py", ["--module", "journal-sampling"]),
        ("check_dependencies.py", ["--module", "journal-sampling"]),
        ("managed_python_runtime.py", ["--module", "journal-sampling", "status"]),
    ],
)
@pytest.mark.parametrize("host", ["codex", "cowork"])
def test_every_preflight_delivers_exact_mismatch_and_stays_blocked(
    tmp_path, monkeypatch, caplog, name, args, host
):
    root, index = installed_copy(tmp_path, host)
    store, state = transport(tmp_path, monkeypatch)
    module = entrypoint(root, name, monkeypatch)
    before = (root / TARGET).read_bytes()

    result = module.main(args)

    assert result == 1
    assert (root / TARGET).read_bytes() == before
    incident = store.queue()[0]
    report = incident["reports"][0]
    assert report["host"] == host
    assert report["stage"] == "installation-preparation"
    assert report["workflow"] == "journal-sampling"
    assert index[TARGET] in report["diagnostics"][0]["message"]
    assert hashlib.sha256(before).hexdigest() in report["diagnostics"][0]["message"]
    assert TARGET in report["diagnostics"][0]["message"]
    assert str(tmp_path) not in json.dumps(report)
    saved = json.loads((state / "state.json").read_text())
    assert saved["outbox"] == []
    assert saved["receipts"][0]["report_id"] == report["report_id"]
    assert "VERA_INSTALLATION_INCIDENT" in caplog.text
    assert "VERA_BROWSER_INCIDENT_REQUIRED" not in caplog.text
    assert incident["status"] == "open"
    assert incident["outcomes"] == []


def test_outage_retains_same_original_report_and_exposes_browser_route(
    tmp_path, monkeypatch, caplog
):
    root, _ = installed_copy(tmp_path)
    _, state = transport(tmp_path, monkeypatch, offline=True)
    module = entrypoint(root, "verified_execution.py", monkeypatch)

    first = module.main(["--module", "journal-sampling"])
    saved = json.loads((state / "state.json").read_text())
    second = module.main(["--module", "journal-sampling"])

    assert first == second == 1
    assert json.loads((state / "state.json").read_text())["outbox"] == saved["outbox"]
    assert len(saved["outbox"]) == 1
    emitted = next(
        record.message
        for record in caplog.records
        if record.message.startswith("VERA_INSTALLATION_INCIDENT:")
    )
    receipt = json.loads(emitted.split(": ", 1)[1])
    assert receipt["outbox_path"] == str(state / "state.json")
    assert "installation_key" not in emitted
    assert (
        receipt["report"]["report_id"]
        == saved["outbox"][0]["payload"]["report"]["report_id"]
    )
    assert '"reporting": "queued"' in caplog.text
    assert "VERA_BROWSER_INCIDENT_REQUIRED" in caplog.text


@pytest.mark.parametrize(
    "damaged",
    [
        "scripts/operational_incidents.py",
        "scripts/verified_execution.py",
        ".codex-plugin/plugin.json",
        "execution-files.json",
    ],
)
def test_unverifiable_reporter_never_runs_and_requires_remote_route(
    tmp_path, monkeypatch, caplog, damaged
):
    root, _ = installed_copy(tmp_path)
    store, state = transport(tmp_path, monkeypatch)
    module = entrypoint(root, "verified_execution.py", monkeypatch)
    sentinel = tmp_path / "unverified-code-executed"
    if damaged.endswith(".py"):
        with (root / damaged).open("a") as f:
            f.write(f'\nPath({str(sentinel)!r}).write_text("unsafe")\n')
    else:
        (root / damaged).write_text("{}")

    result = module.main(["--module", "journal-sampling"])

    assert result == 1
    assert not sentinel.exists()
    assert not (state / "state.json").exists()
    assert store.queue() == []
    assert "VERA_BROWSER_INCIDENT_REQUIRED" in caplog.text


def test_missing_inventory_entry_reports_no_arbitrary_filename_or_contents(
    tmp_path, monkeypatch
):
    root, _ = installed_copy(tmp_path)
    store, _ = transport(tmp_path, monkeypatch)
    module = entrypoint(root, "verified_execution.py", monkeypatch)
    (root / "private-personal-name.txt").write_text("private synthetic material")

    result = module.main(["--module", "journal-sampling"])

    assert result == 1
    payload = json.dumps(store.queue()[0]["reports"])
    assert "private-personal-name" not in payload
    assert "private synthetic material" not in payload
    assert str(tmp_path) not in payload


def test_execution_instructions_require_automatic_reporting_without_consent_gate():
    text = (
        ROOT / "plugins/vera/skills/vera/references/execution-recovery.md"
    ).read_text()
    assert "Do not transmit diagnostics without user authorization" not in text
    assert "recorded: true" in text
    assert "Do not ask the professional to send logs" in text


@pytest.mark.parametrize("location", ["script-directory", "cwd", "pythonpath"])
def test_real_reporter_process_excludes_unindexed_stdlib_shadows(tmp_path, location):
    root, _ = installed_copy(tmp_path)
    working = tmp_path / "working"
    working.mkdir()
    shadow = root / "scripts" if location == "script-directory" else working
    sentinel = tmp_path / "unindexed-module-executed"
    (shadow / "secrets.py").write_text(
        f"from pathlib import Path\nPath({str(sentinel)!r}).write_text('unsafe')\n"
        "raise ImportError('synthetic unindexed dependency')\n"
    )
    state = tmp_path / "blocked-state"
    state.write_text("fixture denies state creation before any network call")
    environment = {**os.environ, "MPARANZA_INCIDENT_STATE_DIR": str(state)}
    if location == "pythonpath":
        environment["PYTHONPATH"] = str(shadow)

    result = subprocess.run(
        [
            sys.executable,
            "-B",
            str(root / "scripts/verified_execution.py"),
            "--module",
            "journal-sampling",
        ],
        cwd=working,
        env=environment,
        capture_output=True,
        text=True,
        check=False,
        timeout=15,
    )

    assert result.returncode == 1
    assert not sentinel.exists()
    assert "VERA_BROWSER_INCIDENT_REQUIRED" in result.stderr
    assert '"reporting": "local-state-unavailable"' in result.stderr
