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


def test_new_probe_preserves_existing_gate_evidence(tmp_path: Path) -> None:
    """A supplemental probe cannot replace a completed run's report."""
    report = tmp_path / "result.json"
    original = json.dumps(passing_report()).encode()
    report.write_bytes(original)

    with pytest.raises(FileExistsError, match="use a new output directory"):
        gate.CheckRun(tmp_path / "candidate.zip", tmp_path, 10)

    assert report.read_bytes() == original


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


def coverage_receipt(root: Path, zip_hash: str = "abc") -> Path:
    """Build synthetic reviewed records; never represent these as real host runs."""
    evidence = root / "coverage-review.txt"
    evidence.write_text("Synthetic coverage fixture, not actual qualification.\n")

    def checks(names: tuple[str, ...]) -> dict:
        return {
            name: {
                "status": "pass",
                "zip_sha256": zip_hash,
                "evidence": [{"path": evidence.name, "sha256": gate.digest(evidence)}],
            }
            for name in names
        }

    path = root / "coverage.json"
    gate.write_json(
        path,
        {
            "schema_version": 1,
            "status": "pass",
            "zip_sha256": zip_hash,
            "reviewer": "Synthetic test reviewer",
            "reviewed_at": "2026-09-06",
            "workflows": {"example": checks(("normal_path", "material_failure_path"))},
            "hosts": {
                axis: checks(
                    (
                        "fresh_core_setup",
                        "optional_setup",
                        "blocked_install",
                        "failure_report",
                    )
                )
                for axis in ("Linux/3.10", "macOS/3.12", "Windows/3.10", "Windows/3.12")
            },
        },
    )
    return path


def test_promotion_without_coverage_preserves_previous_release(tmp_path: Path) -> None:
    _, destination, args = promotion_case(tmp_path)

    result = gate.main(args)

    assert result == 1
    assert destination.read_bytes() == b"previous release"
    assert (
        gate.read_json(tmp_path / "runtime/release-verification.json")["status"]
        == "unverified"
    )


@pytest.mark.parametrize("status", ["unverified", "skip", "fail", "not_applicable"])
def test_coverage_rejects_nonpassing_required_host_axis(
    tmp_path: Path, status: str
) -> None:
    path = coverage_receipt(tmp_path)
    payload = gate.read_json(path)
    payload["hosts"]["Windows/3.12"]["optional_setup"]["status"] = status
    gate.write_json(path, payload)

    with pytest.raises(ValueError, match="passing hosts/Windows/3.12/optional_setup"):
        gate.verify_coverage(path, "abc", {"example"})


def test_coverage_rejects_new_shipped_workflow_without_evidence(tmp_path: Path) -> None:
    path = coverage_receipt(tmp_path)

    with pytest.raises(ValueError, match="workflows/new-workflow"):
        gate.verify_coverage(path, "abc", {"example", "new-workflow"})


def test_coverage_rejects_missing_material_failure_path(tmp_path: Path) -> None:
    path = coverage_receipt(tmp_path)
    payload = gate.read_json(path)
    del payload["workflows"]["example"]["material_failure_path"]
    gate.write_json(path, payload)

    with pytest.raises(ValueError, match="material_failure_path"):
        gate.verify_coverage(path, "abc", {"example"})


def test_coverage_rejects_evidence_for_another_zip(tmp_path: Path) -> None:
    path = coverage_receipt(tmp_path)
    payload = gate.read_json(path)
    payload["hosts"]["Linux/3.10"]["fresh_core_setup"]["zip_sha256"] = "old"
    gate.write_json(path, payload)

    with pytest.raises(ValueError, match="passing hosts/Linux/3.10/fresh_core_setup"):
        gate.verify_coverage(path, "abc", {"example"})


def test_coverage_rejects_changed_review_evidence(tmp_path: Path) -> None:
    path = coverage_receipt(tmp_path)
    (tmp_path / "coverage-review.txt").write_text("Changed after review")

    with pytest.raises(ValueError, match="changed coverage evidence"):
        gate.verify_coverage(path, "abc", {"example"})


def test_coverage_rejects_evidence_outside_receipt_directory(tmp_path: Path) -> None:
    root = tmp_path / "review"
    root.mkdir()
    path = coverage_receipt(root)
    outside = tmp_path / "outside.txt"
    outside.write_text("Unrelated external proof")
    payload = gate.read_json(path)
    payload["workflows"]["example"]["normal_path"]["evidence"] = [
        {"path": "../outside.txt", "sha256": gate.digest(outside)}
    ]
    gate.write_json(path, payload)

    with pytest.raises(ValueError, match="changed coverage evidence"):
        gate.verify_coverage(path, "abc", {"example"})


def test_saved_evidence_rejects_changed_command_log(tmp_path: Path) -> None:
    root = tmp_path / "evidence"
    script_evidence(root, "abc", "3.12")
    (root / "run.log").write_text("changed")
    with pytest.raises(ValueError, match="evidence has changed"):
        gate.verify_saved_evidence(root, gate.read_json(root / "result.json"))


def promotion_case(
    tmp_path: Path, runtime_python: str = "3.10"
) -> tuple[Path, Path, list[str]]:
    """Create existing Linux/Cowork proof without the new coverage requirement."""
    archive = tmp_path / "candidate.zip"
    with ZipFile(archive, "w") as package:
        package.writestr(
            ".claude-plugin/plugin.json", json.dumps(passing_report()["plugin"])
        )
        package.writestr("hooks/hooks.json", '{"hooks":{"SessionStart":[{}]}}')
        package.writestr("skills/example/SKILL.md", "Synthetic workflow")
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
    return archive, destination, args


@pytest.mark.parametrize("runtime_python", ["3.10", "3.12"])
def test_promotion_requires_complete_coverage_and_matching_cowork_review(
    tmp_path: Path, runtime_python: str
) -> None:
    archive, destination, args = promotion_case(tmp_path, runtime_python)
    coverage = coverage_receipt(tmp_path, gate.digest(archive))

    result = gate.main([*args, "--coverage-evidence", str(coverage)])

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


def rejected_render(tmp_path: Path) -> Path:
    """Create the failure receipt retained by an invalid first render attempt."""
    output = tmp_path / "rejected"
    output.mkdir()
    gate.write_json(
        output / "render_manifest.json",
        {
            "status": "failed_or_interrupted",
            "runner": {"status": "failed"},
            "failure": {"message": "missing required role bindings: period_axis"},
        },
    )
    gate.write_json(
        output / "current_reporting.json",
        gate.read_json(output / "render_manifest.json"),
    )
    return output


def test_rejected_render_retains_failure_evidence(tmp_path: Path) -> None:
    output = rejected_render(tmp_path)
    (output / ".logs").mkdir()
    (output / ".logs/preflight.log").write_text("missing required role bindings")
    assert gate.verify_rejected_render(output) is None
    assert any(
        item["path"] == "rejected/render_manifest.json"
        for item in gate.evidence_index(tmp_path)
    )


@pytest.mark.parametrize(
    "artifact",
    [
        "chart.png",
        ".reporting-generations/attempt/published/chart.png",
    ],
)
def test_rejected_render_rejects_published_artifacts(
    tmp_path: Path, artifact: str
) -> None:
    output = rejected_render(tmp_path)
    path = output / artifact
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("unexpected publication")
    with pytest.raises(ValueError, match="published artifact"):
        gate.verify_rejected_render(output)


@pytest.mark.parametrize("status", ["completed", "running"])
def test_rejected_render_requires_terminal_failure(tmp_path: Path, status: str) -> None:
    output = rejected_render(tmp_path)
    manifest = gate.read_json(output / "render_manifest.json")
    manifest["status"] = status
    gate.write_json(output / "render_manifest.json", manifest)
    with pytest.raises(ValueError, match="failure receipt"):
        gate.verify_rejected_render(output)


def test_rejected_render_rejects_completed_publication_state(tmp_path: Path) -> None:
    output = rejected_render(tmp_path)
    gate.write_json(output / "current_reporting.json", {"status": "completed"})
    with pytest.raises(ValueError, match="inconsistent publication state"):
        gate.verify_rejected_render(output)


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
