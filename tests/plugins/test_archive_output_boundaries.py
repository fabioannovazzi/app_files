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


@pytest.mark.parametrize("fault", ["foreign_run", "foreign_workflow", "symlink"])
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


@pytest.mark.parametrize("missing", ["model_data_report.md", "model_data_report.json"])
def test_partial_report_does_not_enter_professional_output_closure(
    archive_core, client_case, missing, caplog
):
    from vera_assurance.contracts import archive_reporting_paths

    loaded = start(archive_core, client_case, "report-builder")
    output = Path(loaded["output_dir"])
    (output / missing).unlink()
    retained = {name: (output / name).read_bytes() for name in PAIR - {missing}}

    observed = archive_reporting_paths(
        output, expected_workflow_ids=("report-builder",)
    )

    assert observed == PAIR - {missing}
    assert "incomplete" in caplog.text
    assert {name: (output / name).read_bytes() for name in observed} == retained
    native = node_paths(output, "report-builder")
    assert native.returncode == 0, native.stderr
    assert set(json.loads(native.stdout)) == observed
    assert "incomplete" in native.stderr


def test_review_failed_commit_and_failed_rollback_retain_original_bytes(tmp_path):
    output = tmp_path / "outputs"
    output.mkdir()
    original = b"Retained professional result\n"
    (output / "result.txt").write_bytes(original)
    script = r"""
const fs = require('node:fs');
const path = require('node:path');
const runtime = require(process.argv[1]);
const output = process.argv[2];
const originalRename = fs.renameSync;
fs.renameSync = function(source, destination) {
  if (destination === output) {
    const error = new Error('Injected destination unavailable');
    error.code = 'EACCES';
    throw error;
  }
  return originalRename.apply(fs, arguments);
};
try {
  runtime.withGeneratedReviewOutputTransaction(output, ({workingOutputDir}) => {
    fs.writeFileSync(path.join(workingOutputDir, 'result.txt'), 'Reviewed revision');
    return runtime.generatedReviewTransactionEnvelope({}, ['result.txt']);
  });
  process.exitCode = 2;
} catch (error) {
  process.stdout.write(error.message);
}
"""

    observed = subprocess.run(
        ["node", "-e", script, str(RUNTIME), str(output)],
        capture_output=True,
        text=True,
        check=False,
        timeout=10,
    )

    assert observed.returncode == 0, observed.stderr
    assert "could not be restored" in observed.stdout
    retained = list(tmp_path.glob(".generated-review-recovery-*/output/result.txt"))
    assert len(retained) == 1
    assert retained[0].read_bytes() == original
    backups = list(
        tmp_path.glob(".generated-review-commit-*/trusted-backup/result.txt")
    )
    assert len(backups) == 1
    assert backups[0].read_bytes() == original


@pytest.mark.parametrize(
    ("same_output", "expected_second_result"),
    [(True, "First saved result"), (False, "Second saved result")],
)
def test_overlapping_review_cannot_erase_another_successful_save(
    tmp_path, same_output, expected_second_result
):
    output = tmp_path / "outputs"
    output.mkdir()
    (output / "result.txt").write_text("Original retained result")
    second_output = output if same_output else tmp_path / "other-outputs"
    contender = r"""
const fs=require('node:fs'),path=require('node:path');
const runtime=require(process.argv[1]);
try {
  runtime.withGeneratedReviewOutputTransaction(process.argv[2], ({workingOutputDir}) => {
    fs.writeFileSync(path.join(workingOutputDir,'result.txt'),'Second saved result');
    return runtime.generatedReviewTransactionEnvelope({saved:true},['result.txt']);
  });
  process.stdout.write(JSON.stringify({saved:true}));
} catch(error) {process.stdout.write(JSON.stringify({saved:false,error:error.message}));}
"""
    outer = r"""
const fs=require('node:fs'),path=require('node:path'),cp=require('node:child_process');
const runtime=require(process.argv[1]);
let contender;
try {
 runtime.withGeneratedReviewOutputTransaction(process.argv[2], ({workingOutputDir}) => {
   const result=cp.spawnSync(process.execPath,['-e',process.argv[3],process.argv[1],process.argv[4]],{encoding:'utf8'});
   if(result.status!==0) throw new Error(result.stderr);
   contender=JSON.parse(result.stdout);
   fs.writeFileSync(path.join(workingOutputDir,'result.txt'),'First saved result');
   return runtime.generatedReviewTransactionEnvelope({saved:true},['result.txt']);
 });
 process.stdout.write(JSON.stringify({saved:true,contender}));
} catch(error) {process.stdout.write(JSON.stringify({saved:false,error:error.message,contender}));}
"""

    observed = subprocess.run(
        ["node", "-e", outer, str(RUNTIME), str(output), contender, str(second_output)],
        capture_output=True,
        text=True,
        check=True,
        timeout=15,
    )

    result = json.loads(observed.stdout)
    assert result["saved"] is True, result
    assert result["contender"]["saved"] is (not same_output)
    assert ("already active" in result["contender"].get("error", "")) is same_output
    assert (second_output / "result.txt").read_text() == expected_second_result
    assert (output / "result.txt").read_text() == "First saved result"


REVIEW_CRASH_SCRIPT = r"""
const fs = require('node:fs');
const path = require('node:path');
const runtime = require(process.argv[1]);
const output = process.argv[2];
const phase = process.argv[3];
const rename = fs.renameSync;
fs.renameSync = function(source, destination) {
  const detach = source === output && path.basename(destination) === 'trusted-backup';
  const publish = path.basename(source) === 'candidate' && destination === output;
  if (detach && phase === 'before_detach') process.exit(96);
  const result = rename.apply(fs, arguments);
  if ((detach && phase === 'after_detach') || (publish && phase === 'after_publish')) process.exit(96);
  return result;
};
runtime.withGeneratedReviewOutputTransaction(output, ({workingOutputDir}) => {
  const before = fs.readFileSync(path.join(workingOutputDir, 'result.txt'), 'utf8');
  if (phase === 'retry' && before !== 'Original retained result') throw new Error('Original was not recovered');
  fs.writeFileSync(path.join(workingOutputDir, 'result.txt'), 'Reviewed result');
  return runtime.generatedReviewTransactionEnvelope({saved: true}, ['result.txt']);
});
"""


@pytest.mark.parametrize("phase", ["before_detach", "after_detach", "after_publish"])
def test_review_retry_recovers_original_after_process_exit(tmp_path, phase):
    output = tmp_path / ".generated-review-commit-project" / "outputs"
    output.mkdir(parents=True)
    (output / "result.txt").write_text("Original retained result", encoding="utf-8")

    crashed = subprocess.run(
        ["node", "-e", REVIEW_CRASH_SCRIPT, str(RUNTIME), str(output), phase],
        capture_output=True,
        text=True,
        check=False,
        timeout=10,
    )
    assert crashed.returncode == 96, crashed.stderr

    resumed = subprocess.run(
        ["node", "-e", REVIEW_CRASH_SCRIPT, str(RUNTIME), str(output), "retry"],
        capture_output=True,
        text=True,
        check=False,
        timeout=10,
    )

    assert resumed.returncode == 0, resumed.stderr
    assert (output / "result.txt").read_text(encoding="utf-8") == "Reviewed result"
    assert not list(output.parent.glob(".generated-review-commit-*"))


@pytest.fixture
def interrupted_review(tmp_path):
    output = tmp_path / "case" / "outputs"
    output.mkdir(parents=True)
    (output / "result.txt").write_text("Original retained result", encoding="utf-8")
    crashed = subprocess.run(
        ["node", "-e", REVIEW_CRASH_SCRIPT, str(RUNTIME), str(output), "after_detach"],
        capture_output=True,
        text=True,
        check=False,
        timeout=10,
    )
    assert crashed.returncode == 96, crashed.stderr
    return output, next(output.parent.glob(".generated-review-commit-*"))


def test_interrupted_review_preserves_modified_backup(interrupted_review):
    output, evidence = interrupted_review
    backup = evidence / "trusted-backup" / "result.txt"
    backup.write_text("Later externally modified bytes", encoding="utf-8")

    resumed = subprocess.run(
        ["node", "-e", REVIEW_CRASH_SCRIPT, str(RUNTIME), str(output), "retry"],
        capture_output=True,
        text=True,
        check=False,
        timeout=10,
    )

    assert resumed.returncode != 0
    assert not output.exists()
    assert backup.read_text(encoding="utf-8") == "Later externally modified bytes"
    assert (evidence / "candidate" / "result.txt").read_text(
        encoding="utf-8"
    ) == "Reviewed result"


def test_interrupted_review_preserves_new_canonical_output(interrupted_review):
    output, evidence = interrupted_review
    output.mkdir()
    (output / "result.txt").write_text("Later independent result", encoding="utf-8")

    resumed = subprocess.run(
        ["node", "-e", REVIEW_CRASH_SCRIPT, str(RUNTIME), str(output), "retry"],
        capture_output=True,
        text=True,
        check=False,
        timeout=10,
    )

    assert resumed.returncode != 0
    assert (output / "result.txt").read_text(
        encoding="utf-8"
    ) == "Later independent result"
    assert (evidence / "trusted-backup" / "result.txt").read_text(
        encoding="utf-8"
    ) == "Original retained result"


def test_review_retry_recovers_after_recovery_process_itself_exits(interrupted_review):
    output, _ = interrupted_review
    script = r"""
const fs = require('node:fs');
const path = require('node:path');
const runtime = require(process.argv[1]);
const output = process.argv[2];
const rename = fs.renameSync;
fs.renameSync = function(source, destination) {
  const result = rename.apply(fs, arguments);
  if (destination === output && path.basename(path.dirname(source)).startsWith('.generated-review-recovery-')) process.exit(97);
  return result;
};
runtime.generatedReviewRecoverInterruptedOutput(output);
"""
    crashed = subprocess.run(
        ["node", "-e", script, str(RUNTIME), str(output)],
        capture_output=True,
        text=True,
        check=False,
        timeout=10,
    )
    assert crashed.returncode == 97, crashed.stderr

    resumed = subprocess.run(
        ["node", "-e", REVIEW_CRASH_SCRIPT, str(RUNTIME), str(output), "retry"],
        capture_output=True,
        text=True,
        check=False,
        timeout=10,
    )

    assert resumed.returncode == 0, resumed.stderr
    assert (output / "result.txt").read_text(encoding="utf-8") == "Reviewed result"


def test_review_recovery_does_not_take_over_live_process(interrupted_review):
    import os

    output, evidence = interrupted_review
    receipt_path = evidence / "recovery.json"
    receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    receipt["pid"] = os.getpid()
    receipt_path.write_text(json.dumps(receipt), encoding="utf-8")
    before = receipt_path.read_bytes()

    resumed = subprocess.run(
        ["node", "-e", REVIEW_CRASH_SCRIPT, str(RUNTIME), str(output), "retry"],
        capture_output=True,
        text=True,
        check=False,
        timeout=10,
    )

    assert resumed.returncode != 0
    assert not output.exists()
    assert receipt_path.read_bytes() == before
    assert (evidence / "trusted-backup" / "result.txt").read_text(
        encoding="utf-8"
    ) == "Original retained result"


def test_review_recovery_follows_renamed_parent_identity(interrupted_review):
    output, _ = interrupted_review
    moved = output.parent.with_name("renamed-case")
    output.parent.rename(moved)
    output = moved / "outputs"

    resumed = subprocess.run(
        ["node", "-e", REVIEW_CRASH_SCRIPT, str(RUNTIME), str(output), "retry"],
        capture_output=True,
        text=True,
        check=False,
        timeout=10,
    )

    assert resumed.returncode == 0, resumed.stderr
    assert (output / "result.txt").read_text(encoding="utf-8") == "Reviewed result"


def test_review_recovery_rejects_evidence_moved_to_another_parent(interrupted_review):
    output, evidence = interrupted_review
    other_parent = output.parent.parent / "different-case"
    other_parent.mkdir()
    moved = other_parent / evidence.name
    evidence.rename(moved)
    other_output = other_parent / "outputs"

    resumed = subprocess.run(
        ["node", "-e", REVIEW_CRASH_SCRIPT, str(RUNTIME), str(other_output), "retry"],
        capture_output=True,
        text=True,
        check=False,
        timeout=10,
    )

    assert resumed.returncode != 0
    assert not other_output.exists()
    assert (moved / "trusted-backup" / "result.txt").read_text(
        encoding="utf-8"
    ) == "Original retained result"
