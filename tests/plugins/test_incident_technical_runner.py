"""Exercise actual failed helper processes, not fabricated exit-only envelopes."""

from __future__ import annotations

import importlib.util
import json
import os
import subprocess
import sys
from pathlib import Path
from uuid import uuid4

import pytest

RUNNER = (
    Path(__file__).resolve().parents[2] / "plugins/vera/scripts/technical_runner.py"
)


def test_component_checker_executes_once_without_reentering_vera_checker(
    tmp_path, monkeypatch
):
    """Same filenames in separate roots must resolve to the selected component."""
    spec = importlib.util.spec_from_file_location(
        "component_checker_runtime", RUNNER.with_name("_managed_python_runtime.py")
    )
    runtime = importlib.util.module_from_spec(spec)
    monkeypatch.setitem(sys.modules, spec.name, runtime)
    spec.loader.exec_module(runtime)
    root = tmp_path / "vera"
    (root / "scripts").mkdir(parents=True)
    (root / "scripts/check_dependencies.py").write_text(
        "raise RuntimeError('ROOT CHECKER MUST NEVER RUN')"
    )
    (root / "scripts/technical_runner.py").write_bytes(RUNNER.read_bytes())
    (root / "components.json").write_text(json.dumps({"plugins": ["test-component"]}))
    component = root / "modules/test-component"
    (component / "scripts").mkdir(parents=True)
    (component / "requirements.txt").write_text("")
    (component / "scripts/check_dependencies.py").write_text(
        "raise RuntimeError('Required component dependency missing')"
    )
    monkeypatch.setattr(
        runtime, "ensure_runtime", lambda *_a, **_k: (True, tmp_path, "ready")
    )
    monkeypatch.setattr(runtime, "runtime_python", lambda *_a: Path(sys.executable))
    monkeypatch.setattr(runtime, "runtime_environment", lambda *_a: None)
    event = tmp_path / "event.json"

    result = runtime.main(
        root,
        ["--module", "test-component", "run", "scripts/check_dependencies.py"],
        diagnostic_path=event,
    )

    data = json.loads(event.read_text())
    assert result == 1
    assert data["events"][0]["message"] == "Required component dependency missing"
    assert "ROOT CHECKER" not in event.read_text()


def execute(tmp_path, source, arguments=()):
    helper = tmp_path / "helper.py"
    helper.write_text(source, encoding="utf-8")
    event = tmp_path / "technical.json"
    completed = subprocess.run(
        [
            sys.executable,
            str(RUNNER),
            str(tmp_path),
            str(event),
            str(helper),
            *arguments,
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    return completed, json.loads(event.read_text()) if event.exists() else None


def test_required_argument_error_reaches_structured_event_with_missing_flag(tmp_path):
    completed, data = execute(
        tmp_path,
        "import argparse\np=argparse.ArgumentParser()\np.add_argument('--client-engagement',required=True)\np.parse_args()\n",
    )

    assert completed.returncode == 2
    assert data["capture_complete"] is True
    assert (
        data["events"][0]["message"] == "Missing required options: --client-engagement"
    )


def test_runner_preserves_helper_logging_configuration_and_info_output(tmp_path):
    completed, data = execute(
        tmp_path,
        "import logging\nlogging.basicConfig(level=logging.INFO,format='RESULT %(message)s')\nlogging.info('matched=2')\n",
    )

    assert completed.returncode == 0
    assert completed.stderr == "RESULT matched=2\n"
    assert data is None


def test_application_validation_error_is_distinct_from_argument_error(tmp_path):
    source = "import argparse\np=argparse.ArgumentParser()\ntry:\n    raise ValueError('Research artifact bindings missing')\nexcept ValueError as error:\n    p.error(str(error))\n"
    completed, data = execute(tmp_path, source)

    assert completed.returncode == 2
    assert data["capture_complete"] is True
    assert data["events"][0]["error_type"] == "ValueError"
    assert data["events"][0]["message"] == "Research artifact bindings missing"
    assert data["events"][0]["technical_frames"][0]["line"] == 4


def test_unexpected_exception_preserves_source_chain_and_real_exit(tmp_path):
    completed, data = execute(
        tmp_path,
        "raise RuntimeError('Dependency receipt does not match the installed recipe')\n",
    )

    assert completed.returncode == 1
    assert data["capture_complete"] is True
    assert (
        data["events"][0]["message"]
        == "Dependency receipt does not match the installed recipe"
    )
    assert data["events"][0]["technical_frames"][0]["file"] == "helper.py"


def test_logged_exception_records_caught_underlying_cause(tmp_path):
    source = "import logging\ntry:\n    raise ValueError('Required research artifact role missing or repeated')\nexcept ValueError as error:\n    logging.error('%s',error)\n    raise SystemExit(1)\n"
    completed, data = execute(tmp_path, source)

    assert completed.returncode == 1
    assert (
        data["events"][0]["message"]
        == "Required research artifact role missing or repeated"
    )


def test_dynamic_exception_values_remain_private_and_capture_is_pending(tmp_path):
    private_value = "CLIENT_PRIVATE_CASE_TEXT"
    completed, data = execute(
        tmp_path,
        "import sys\nraise ValueError(f'Artifact changed: {sys.argv[1]}')\n",
        [private_value],
    )

    assert completed.returncode == 1
    assert private_value in completed.stderr
    assert private_value not in json.dumps(data)
    assert data["events"][0]["message"] == "Artifact changed: {value}"
    assert data["capture_complete"] is False


def test_plain_exit_remains_explicitly_incomplete(tmp_path):
    completed, data = execute(tmp_path, "raise SystemExit(17)\n")

    assert completed.returncode == 17
    assert data["capture_complete"] is False


def test_success_preserves_professional_stdout_without_creating_failure_event(tmp_path):
    completed, data = execute(tmp_path, "print('professional result')\n")

    assert completed.returncode == 0
    assert completed.stdout == "professional result\n"
    assert data is None


@pytest.mark.parametrize(
    "argument",
    ["PRIVATE_CASE", "/Users/example/private/client", "password=PRIVATE_TOKEN"],
)
def test_parser_never_serializes_argument_values(tmp_path, argument):
    completed, data = execute(
        tmp_path,
        "import argparse\np=argparse.ArgumentParser()\np.add_argument('--action',choices=['bind','verify'])\np.parse_args()\n",
        ["--action", argument],
    )

    assert completed.returncode == 2
    assert argument not in json.dumps(data)
    assert data["capture_complete"] is False


def archive_command(tmp_path, arguments, *, injected_failure=None):
    """Exercise the real Archive CLI handler with isolated synthetic state."""
    root = RUNNER.parents[3]
    cli = root / "plugins/studio-archive/scripts/studio_archive.py"
    destination = tmp_path / f"archive-{uuid4().hex}.technical.json"
    environment = {
        **os.environ,
        "VERA_STUDIO_ARCHIVE_STATE_DIR": str((tmp_path / "state").resolve()),
        "VERA_STUDIO_ARCHIVE_PROFILE_DIR": str((tmp_path / "profile").resolve()),
        "VERA_STUDIO_ARCHIVE_SESSION_ID": "handled-error-regression",
    }
    command = [
        sys.executable,
        str(RUNNER),
        str(root),
        str(destination),
        str(cli),
        *arguments,
    ]
    if injected_failure:
        # Replace only the selected core call in this child. The published CLI,
        # exception handler and technical collector execute unchanged.
        driver = (
            "import runpy,sys\n"
            f"sys.path.insert(0,{str(cli.parent)!r})\n"
            "import archive_core,sqlite3\n"
            "def fail(**kwargs):\n"
            f"    raise {injected_failure}\n"
            "archive_core.refresh_archive=fail\n"
            f"sys.argv={command[1:]!r}\n"
            f"runpy.run_path({str(RUNNER)!r},run_name='__main__')\n"
        )
        command = [sys.executable, "-c", driver]
    completed = subprocess.run(
        command, env=environment, capture_output=True, text=True, check=False
    )
    data = json.loads(destination.read_text()) if destination.exists() else None
    return completed, data


def test_real_archive_handled_error_retains_cause_without_changing_json(tmp_path):
    completed, data = archive_command(tmp_path, ["refresh"])

    assert completed.returncode == 1
    assert json.loads(completed.stdout)["error"]["code"] == "archive_not_configured"
    assert "ArchiveNotConfiguredError" in completed.stderr
    assert data["capture_complete"] is True
    assert data["events"][0]["error_type"] == "ArchiveNotConfiguredError"
    assert data["events"][0]["message"] == (
        "Studio Archive is not configured. Start the guided folder setup first."
    )
    assert data["events"][0]["technical_frames"][-1]["file"].endswith("archive_core.py")


@pytest.mark.parametrize(
    ("failure", "expected_type", "expected_code"),
    [
        (
            "archive_core.ArchiveError('PRIVATE_CASE_VALUE')",
            "ArchiveError",
            "archive_error",
        ),
        (
            "OSError(13, 'PRIVATE_CASE_VALUE')",
            "PermissionError",
            "archive_operation_failed",
        ),
        ("ValueError('PRIVATE_CASE_VALUE')", "ValueError", "archive_operation_failed"),
        ("sqlite3.Error('PRIVATE_CASE_VALUE')", "Error", "archive_operation_failed"),
    ],
)
def test_all_archive_caught_error_classes_reach_diagnostics_with_private_review(
    tmp_path, failure, expected_type, expected_code
):
    completed, data = archive_command(tmp_path, ["refresh"], injected_failure=failure)

    assert completed.returncode == 1
    assert json.loads(completed.stdout)["error"]["code"] == expected_code
    assert "PRIVATE_CASE_VALUE" in completed.stderr
    assert "PRIVATE_CASE_VALUE" not in json.dumps(data)
    assert data["events"][0]["error_type"] == expected_type
    assert data["events"][0]["technical_frames"][0]["file"].endswith(
        "studio_archive.py"
    )


def test_successful_archive_command_does_not_emit_failure(tmp_path):
    archive = tmp_path / "archive"
    archive.mkdir()

    completed, data = archive_command(
        tmp_path,
        [
            "configure",
            "--archive-root",
            str(archive.resolve()),
            "--host-folder-access-approved",
        ],
    )

    assert completed.returncode == 0
    assert "error" not in json.loads(completed.stdout)
    assert completed.stderr == ""
    assert data is None
