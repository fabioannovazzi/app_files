"""Diagnostic helpers consume the actual portable Archive context."""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest

from tests.plugins.test_archive_automatic_reporting import reporting_runtime, start
from tests.plugins.test_operational_incident_client import client
from tests.plugins.test_vera_customer_folder_ledger import (
    archive_core,
    archive_script_imports,
    client_case,
)

ROOT = Path(__file__).resolve().parents[2]


def portable_episode(core, case):
    loaded = start(core, case, "journal-bank-reconciliation")
    context = Path(loaded["run_root"]) / "context.json"
    output = Path(loaded["output_dir"])
    arguments = [
        "run",
        "inspect_inputs.py",
        "--client-engagement",
        str(context),
        "--output-dir",
        str(output),
    ]
    return loaded, context, output, arguments


def test_csv_inspection_needs_no_pdf_incident_with_portable_context(
    tmp_path, monkeypatch, archive_core, client_case
):
    reporter, store, _ = client(tmp_path, monkeypatch)
    _, context, output, arguments = portable_episode(archive_core, client_case)
    original = context.read_bytes()
    (output / "inspection.json").write_text(
        '{"journal":{"files":[{"parser":"tabular","qualification_status":"needs_review"}]}}'
    )
    execution = reporter.execution_identity("journal-bank-reconciliation", arguments)

    reporter.report_pdf_recovery("journal-bank-reconciliation", arguments, execution)

    assert store.queue() == []
    assert context.read_bytes() == original
    assert "output_dir" not in json.loads(original)


def test_pdf_failure_reporting_accepts_portable_context(
    tmp_path, monkeypatch, archive_core, client_case
):
    reporter, store, _ = client(tmp_path, monkeypatch)
    monkeypatch.setenv("MPARANZA_INCIDENT_DELIVERY", "automatic")
    _, _, output, arguments = portable_episode(archive_core, client_case)
    (output / "inspection.json").write_text(
        json.dumps(
            {
                "journal": {
                    "files": [
                        {
                            "registration_diagnostics": {
                                "accepted": False,
                                "reason": "registration_pdf_incomplete_or_unbalanced",
                                "rejected_rows": [
                                    {"reason": "unclaimed_source_amount"}
                                ],
                            }
                        }
                    ]
                }
            }
        )
    )
    execution = reporter.execution_identity("journal-bank-reconciliation", arguments)

    reporter.report_pdf_recovery("journal-bank-reconciliation", arguments, execution)

    assert len(store.queue()) == 1
    assert "unclaimed_source_amount" in json.dumps(store.queue())


def test_portable_diagnostic_context_rejects_other_run_output(
    tmp_path, monkeypatch, archive_core, client_case
):
    reporter, store, _ = client(tmp_path, monkeypatch)
    _, _, _, arguments = portable_episode(archive_core, client_case)
    arguments[-1] = str(tmp_path / "other-output")
    execution = reporter.execution_identity("journal-bank-reconciliation", arguments)

    with pytest.raises(ValueError, match="same bound workflow"):
        reporter.report_pdf_recovery(
            "journal-bank-reconciliation", arguments, execution
        )

    assert store.queue() == []


def test_killed_worker_retains_diagnostic_with_portable_context(
    tmp_path, monkeypatch, archive_core, client_case
):
    client(tmp_path, monkeypatch)
    loaded, context, output, arguments = portable_episode(archive_core, client_case)
    original = context.read_bytes()
    path = ROOT / "plugins/vera/scripts/managed_python_runtime.py"
    spec = importlib.util.spec_from_file_location("portable_diagnostic_launcher", path)
    launcher = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(launcher)
    monkeypatch.setattr(launcher, "_execute_with_diagnostics", lambda *_: (-9, None))

    result = launcher.run_verified_helper(
        tmp_path, arguments, "journal-bank-reconciliation"
    )

    diagnostic = json.loads((output / "execution_failure.json").read_text())
    assert result == -9
    assert diagnostic["run_id"] == loaded["run"]["run_id"]
    assert diagnostic["failure_kind"] == "forced_termination"
    assert diagnostic["memory_exhaustion_confirmed"] is False
    assert context.read_bytes() == original
