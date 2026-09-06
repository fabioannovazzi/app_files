"""Release evidence must fail closed on stale ZIPs and unrelated failures."""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path
from zipfile import ZipFile

import pytest

SCRIPT = Path(__file__).resolve().parents[2] / "scripts/check_clara_cowork_release.py"
spec = importlib.util.spec_from_file_location("clara_release_gate", SCRIPT)
assert spec and spec.loader
gate = importlib.util.module_from_spec(spec)
spec.loader.exec_module(gate)


def acceptance(tmp_path: Path) -> Path:
    """Create explicit reviewer evidence for one candidate."""
    evidence = tmp_path / "review.txt"
    evidence.write_text("Synthetic test reviewer evidence\n")
    receipt = tmp_path / "cowork.json"
    receipt.write_text(
        json.dumps(
            {
                "schema_version": 2,
                "status": "pass",
                "zip_sha256": "abc",
                "host": "Claude Cowork",
                "workflow": gate.CASE,
                "fresh_install": True,
                "fresh_session": True,
                "plugin_version": "0.1.180",
                "checks": {
                    "plugin_load": "pass",
                    "startup_hooks": "pass",
                    "synthetic_workflow": "pass",
                },
                "reviewer": "Test reviewer",
                "tested_at": "2026-09-05",
                "cowork_version": "test",
                "environment": "test VM",
                "evidence": {
                    name: {"path": evidence.name, "sha256": gate.digest(evidence)}
                    for name in (
                        "normal_answer",
                        "report",
                        "transcript",
                        "visual_review",
                        "plugin_load",
                        "startup_hooks",
                    )
                },
            }
        )
    )
    return receipt


def test_acceptance_accepts_reviewed_evidence_for_exact_zip(tmp_path: Path) -> None:
    gate.verify_acceptance(acceptance(tmp_path), "abc", passing_report())


def passing_report() -> dict:
    """Supply the candidate identity established by packaged checks."""
    return {"status": "pass", "plugin": {"name": "clara", "version": "0.1.180"}}


def test_acceptance_rejects_new_zip_even_when_version_is_unchanged(
    tmp_path: Path,
) -> None:
    with pytest.raises(ValueError, match="different ZIP"):
        gate.verify_acceptance(acceptance(tmp_path), "changed", passing_report())


def test_acceptance_rejects_failed_script_run(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="not passed"):
        gate.verify_acceptance(acceptance(tmp_path), "abc", {"status": "fail"})


def test_acceptance_rejects_modified_report(tmp_path: Path) -> None:
    receipt = acceptance(tmp_path)
    (tmp_path / "review.txt").write_text("Changed after review")
    with pytest.raises(ValueError, match="changed Cowork evidence"):
        gate.verify_acceptance(receipt, "abc", passing_report())


@pytest.mark.parametrize("entry", ["../outside.txt", "/outside.txt"])
def test_extraction_rejects_escaping_entries(tmp_path: Path, entry: str) -> None:
    archive = tmp_path / "candidate.zip"
    with ZipFile(archive, "w") as package:
        package.writestr(".claude-plugin/plugin.json", "{}")
        package.writestr(entry, "bad")
    with pytest.raises(ValueError, match="Unsafe ZIP"):
        gate.extract_package(archive, tmp_path / "extracted")


@pytest.mark.parametrize(
    ("message", "passed"),
    [("missing required role bindings", True), ("No module named polars", False)],
)
def test_negative_case_requires_the_intended_rejection(
    tmp_path: Path, message: str, passed: bool
) -> None:
    archive = tmp_path / "candidate.zip"
    archive.write_bytes(b"fixture")
    run = gate.CheckRun(archive, tmp_path, 10)
    run.root.mkdir()
    result = run.command(
        "negative",
        [sys.executable, "-c", f"raise ValueError({message!r})"],
        negative=True,
        expected_error="missing required role bindings",
    )
    assert result is passed


def test_release_refuses_promotion_without_real_cowork_receipt(tmp_path: Path) -> None:
    archive = tmp_path / "candidate.zip"
    archive.write_bytes(b"fixture")
    gate.write_json(
        tmp_path / "result.json", {"status": "pass", "zip_sha256": gate.digest(archive)}
    )
    destination = tmp_path / "public.zip"
    destination.write_bytes(b"previous release")
    result = gate.main(
        [
            str(archive),
            "--output",
            str(tmp_path),
            "--verify-release",
            "--promote-to",
            str(destination),
        ]
    )
    assert result == 1
    assert destination.read_bytes() == b"previous release"


@pytest.mark.parametrize(
    ("rows", "valid"),
    [
        ("Jan,405000,360000\nFeb,426000,379500\n", True),
        ("Jan,360000,405000\nFeb,379500,426000\n", False),
        ("Jan,405001,360000\nFeb,426000,379500\n", False),
        ("Feb,426000,379500\nJan,405000,360000\n", False),
    ],
)
def test_chart_arithmetic_rejects_swapped_periods_wrong_totals_and_order(
    tmp_path: Path, rows: str, valid: bool
) -> None:
    table = tmp_path / "monthly.csv"
    table.write_text("Date,AC,PY\n" + rows)
    if valid:
        assert gate.verify_monthly_values(table) is None
    else:
        with pytest.raises(ValueError, match="Chart totals"):
            gate.verify_monthly_values(table)


def script_evidence(root: Path, zip_hash: str, python: str) -> None:
    """Create a portable CI evidence fixture, independent of real package execution."""
    root.mkdir()
    log = root / "run.log"
    log.write_text("fixture command passed\n")
    gate.write_json(
        root / "result.json",
        {
            "status": "pass",
            "plugin": passing_report()["plugin"],
            "gate_version": gate.GATE_VERSION,
            "workflow": gate.CASE,
            "zip_sha256": zip_hash,
            "environment": {"os": "Linux", "python_minor": python},
            "steps": [{"status": "pass"}],
            "artifacts": [{"path": "run.log", "sha256": gate.digest(log)}],
        },
    )


def test_saved_evidence_rejects_changed_command_log(tmp_path: Path) -> None:
    root = tmp_path / "evidence"
    script_evidence(root, "abc", "3.12")
    (root / "run.log").write_text("changed")
    with pytest.raises(ValueError, match="evidence has changed"):
        gate.verify_saved_evidence(root, gate.read_json(root / "result.json"))


@pytest.mark.parametrize("runtime_python", ["3.10", "3.12"])
def test_promotion_accepts_one_verified_runtime_and_matching_cowork_review(
    tmp_path: Path, runtime_python: str
) -> None:
    archive = tmp_path / "candidate.zip"
    with ZipFile(archive, "w") as package:
        package.writestr(
            ".claude-plugin/plugin.json", json.dumps(passing_report()["plugin"])
        )
        package.writestr("hooks/hooks.json", '{"hooks":{"SessionStart":[{}]}}')
    receipt = acceptance(tmp_path)
    payload = gate.read_json(receipt)
    payload["zip_sha256"] = gate.digest(archive)
    gate.write_json(receipt, payload)
    script_evidence(tmp_path / "runtime", gate.digest(archive), runtime_python)
    destination = tmp_path / "public.zip"
    destination.write_bytes(b"previous release")
    args = [
        str(archive),
        "--output",
        str(tmp_path / "runtime"),
        "--verify-release",
        "--cowork-acceptance",
        str(receipt),
        "--promote-to",
        str(destination),
    ]
    result = gate.main(args)
    assert result == 0
    assert destination.read_bytes() == archive.read_bytes()
    assert gate.read_json(tmp_path / "runtime/release-verification.json")[
        "zip_sha256"
    ] == gate.digest(archive)


@pytest.mark.parametrize(
    "reference",
    [
        "./hooks/hooks.json",
        "hooks/hooks.json",
        "./hooks/../hooks/hooks.json",
        ["./hooks/hooks.json"],
    ],
)
def test_hook_registration_rejects_duplicate_automatic_path(
    tmp_path: Path, reference
) -> None:
    (tmp_path / ".claude-plugin").mkdir()
    (tmp_path / "hooks").mkdir()
    gate.write_json(tmp_path / ".claude-plugin/plugin.json", {"hooks": reference})
    gate.write_json(tmp_path / "hooks/hooks.json", {"hooks": {"SessionStart": [{}]}})
    with pytest.raises(ValueError, match="Duplicate hooks file"):
        gate.verify_hook_registration(tmp_path)


def test_hook_registration_allows_a_distinct_custom_file(tmp_path: Path) -> None:
    (tmp_path / ".claude-plugin").mkdir()
    (tmp_path / "hooks").mkdir()
    gate.write_json(
        tmp_path / ".claude-plugin/plugin.json", {"hooks": "./hooks/extra.json"}
    )
    gate.write_json(tmp_path / "hooks/hooks.json", {"hooks": {"SessionStart": [{}]}})
    assert gate.verify_hook_registration(tmp_path) is None


@pytest.mark.parametrize(
    "check", ["plugin_load", "startup_hooks", "synthetic_workflow"]
)
@pytest.mark.parametrize("status", [None, "fail", "unverified"])
def test_acceptance_requires_each_real_host_check(
    tmp_path: Path, check: str, status
) -> None:
    receipt = acceptance(tmp_path)
    payload = gate.read_json(receipt)
    payload["checks"][check] = status
    gate.write_json(receipt, payload)
    with pytest.raises(ValueError, match=check):
        gate.verify_acceptance(receipt, "abc", passing_report())


@pytest.mark.parametrize("field", ["plugin_load", "startup_hooks"])
def test_acceptance_requires_host_logs(tmp_path: Path, field: str) -> None:
    receipt = acceptance(tmp_path)
    payload = gate.read_json(receipt)
    del payload["evidence"][field]
    gate.write_json(receipt, payload)
    with pytest.raises(ValueError, match=field):
        gate.verify_acceptance(receipt, "abc", passing_report())


@pytest.mark.parametrize(
    ("field", "value"),
    [("schema_version", 1), ("fresh_session", False), ("plugin_version", "old")],
)
def test_acceptance_rejects_old_or_incomplete_host_review(
    tmp_path: Path, field: str, value
) -> None:
    receipt = acceptance(tmp_path)
    payload = gate.read_json(receipt)
    payload[field] = value
    gate.write_json(receipt, payload)
    with pytest.raises(ValueError, match="acceptance is missing"):
        gate.verify_acceptance(receipt, "abc", passing_report())


def test_direct_cli_uses_empty_bootstrap_interpreter(monkeypatch, tmp_path):
    from unittest.mock import Mock

    archive = tmp_path / "candidate.zip"
    archive.write_bytes(b"test")
    monkeypatch.setenv("CLAUDE_ENV_FILE", "/tmp/inherited-hook-env")
    run = gate.CheckRun(archive, tmp_path / "output", 60)
    command = Mock(return_value=True)
    monkeypatch.setattr(run, "command", command)

    run.direct(
        "profile", "profile_dataset.py", "relative.csv", "--output", "profile.json"
    )

    command.assert_called_once_with(
        "profile",
        [
            str(run.python),
            "modules/reporting-engine/scripts/profile_dataset.py",
            "relative.csv",
            "--output",
            "profile.json",
        ],
        negative=False,
        expected_error="missing required role bindings",
    )
    assert "CLAUDE_ENV_FILE" not in run.env
