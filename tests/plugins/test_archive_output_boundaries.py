"""Archive sidecars coexist with closed professional output trees."""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest

from tests.plugins.test_archive_automatic_reporting import (
    archive_core,
    archive_script_imports,
    client_case,
    reporting_runtime,
    start,
)

ROOT = Path(__file__).resolve().parents[2]
RUNTIME = (
    ROOT / "plugins/_shared/vendor/modules/vera_assurance/review_output_transaction.cjs"
)
PAIR = {"model_data_report.json", "model_data_report.md"}


def node_paths(output: Path, workflow: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [
            "node",
            "-e",
            "const runtime=require(process.argv[1]);"
            "process.stdout.write(JSON.stringify(runtime.archiveReportingPaths(process.argv[2], [process.argv[3]])));",
            str(RUNTIME),
            str(output),
            workflow,
        ],
        capture_output=True,
        text=True,
        check=False,
        timeout=10,
    )


@pytest.mark.parametrize(
    "workflow",
    [
        "open-item-reconciliation",
        "check-entries",
        "journal-sampling",
        "report-builder",
        "report-enti-locali",
    ],
)
def test_professional_boundaries_recognize_only_same_run_archive_sidecars(
    archive_core, client_case, workflow
):
    from vera_assurance.contracts import archive_reporting_paths

    loaded = start(archive_core, client_case, workflow)
    output = Path(loaded["output_dir"])

    observed = archive_reporting_paths(output, expected_workflow_ids=(workflow,))

    assert observed == PAIR
    native = node_paths(output, workflow)
    assert native.returncode == 0, native.stderr
    assert set(json.loads(native.stdout)) == PAIR


@pytest.mark.parametrize(
    "fault", ["foreign_run", "foreign_workflow", "missing_pair", "symlink"]
)
def test_reporting_name_does_not_exempt_foreign_or_unsafe_output(
    archive_core, client_case, tmp_path, fault
):
    from vera_assurance.contracts import archive_reporting_paths

    loaded = start(archive_core, client_case, "report-builder")
    output = Path(loaded["output_dir"])
    report_path = output / "model_data_report.json"
    report = json.loads(report_path.read_text(encoding="utf-8"))
    if fault == "foreign_run":
        report["run_id"] = "run_" + "0" * 24
        report_path.write_text(json.dumps(report), encoding="utf-8")
    elif fault == "foreign_workflow":
        report["workflow_id"] = "variance-analysis"
        report_path.write_text(json.dumps(report), encoding="utf-8")
    elif fault == "missing_pair":
        (output / "model_data_report.md").unlink()
    else:
        destination = tmp_path / "copied-report.json"
        report_path.rename(destination)
        try:
            report_path.symlink_to(destination)
        except OSError:
            pytest.skip("Host does not grant symlink creation")

    with pytest.raises(ValueError):
        archive_reporting_paths(output, expected_workflow_ids=("report-builder",))
    assert node_paths(output, "report-builder").returncode != 0


@pytest.mark.parametrize("changed", [False, True])
def test_review_transaction_preserves_archive_sidecar_bytes(
    archive_core, client_case, changed
):
    from vera_assurance.contracts import archive_reporting_paths

    loaded = start(archive_core, client_case, "report-builder")
    output = Path(loaded["output_dir"])
    working = output.parent / ".generated-review-transaction-test" / "working"
    shutil.copytree(output, working)
    if changed:
        (working / "model_data_report.md").write_text("Changed", encoding="utf-8")

    if changed:
        with pytest.raises(ValueError, match="changed Archive"):
            archive_reporting_paths(working, expected_workflow_ids=("report-builder",))
        assert node_paths(working, "report-builder").returncode != 0
    else:
        assert (
            archive_reporting_paths(working, expected_workflow_ids=("report-builder",))
            == PAIR
        )
        native = node_paths(working, "report-builder")
        assert native.returncode == 0, native.stderr
        assert set(json.loads(native.stdout)) == PAIR
