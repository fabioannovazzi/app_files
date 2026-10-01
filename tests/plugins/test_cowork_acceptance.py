"""Regression fixtures for the verifier, never real Cowork acceptance evidence."""

from __future__ import annotations

import csv
import hashlib
import json
import subprocess
import sys
from pathlib import Path

import pytest

from scripts.cowork_acceptance import cowork_acceptance as acceptance

ROOT = Path(__file__).resolve().parents[2]
PACKAGE = ROOT / "static/shared/vera/downloads/vera-cowork-plugin.zip"


def write(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value))


def record(path, run):
    return {
        "path": path.relative_to(run).as_posix(),
        "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
    }


@pytest.fixture
def prepared(tmp_path):
    run = tmp_path / "acceptance"
    acceptance.prepare(PACKAGE, run, package_url="https://example.test/vera.zip")
    return run


def reviewed(run, case="bank", phase="demo", route="ordinary"):
    """Make labelled synthetic review files to exercise only verifier behavior."""
    name = f"{case}-{route}-{phase}"
    path = run / f"reviews/{name}.json"
    review = json.loads(path.read_text())
    workspace = run / f"workspaces/{case}/{route}/{phase}-result"
    evidence = run / f"evidence/{name}.txt"
    evidence.parent.mkdir(exist_ok=True)
    evidence.write_text("SYNTHETIC TEST FIXTURE. No Cowork execution occurred.")
    spec = json.loads((run / "cases.json").read_text())["cases"][case]
    expected = spec["expected"]["practice" if phase == "resume" else phase]
    workspace.mkdir(parents=True)
    if case == "bank":
        output = workspace / "reconciliation_audit.json"
        write(output, expected)
        matches = workspace / "reconciliation_matches.csv"
        with matches.open("w", newline="") as stream:
            fields = [
                "bank_amount",
                "journal_amount",
                "amount_delta",
                "shared_references",
                "bank_transaction_id",
                "journal_transaction_id",
                "status",
                "bank_date",
                "journal_date",
            ]
            writer = csv.DictWriter(stream, fieldnames=fields)
            writer.writeheader()
            for index, amount in enumerate(
                ["-1220", "-732", "-488"][: expected["matched_count"]]
            ):
                writer.writerow(
                    dict(
                        zip(
                            fields,
                            [
                                amount,
                                amount,
                                "0",
                                f"trn00{index + 1}",
                                f"bank-{index}",
                                f"journal-{index}",
                                "matched",
                                ["2026-03-18", "2026-03-25", "2026-04-04"][index],
                                ["2026-03-18", "2026-03-25", "2026-04-04"][index],
                            ],
                            strict=True,
                        )
                    )
                )
        mechanical = {
            "audit": output.relative_to(run).as_posix(),
            "matches": matches.relative_to(run).as_posix(),
        }
        artifacts = [
            output,
            matches,
            workspace / "review.xlsx",
            workspace / "review.md",
        ]
    elif case == "report":
        output = workspace / "numeric_evidence_ledger.json"
        write(
            output,
            {
                "entries": [
                    {
                        "evidence_id": f"fixture.{index}.sum",
                        "value": value,
                        "source_sheet": sheet,
                    }
                    for index, (sheet, value) in enumerate(expected.items())
                ]
            },
        )
        mechanical = {"numeric_ledger": output.relative_to(run).as_posix()}
        artifacts = [
            output,
            workspace / "report.docx",
            workspace / "report.xlsx",
            workspace / "report.md",
        ]
    else:
        output = workspace / "structured_fiscal_fields.csv"
        with output.open("w", newline="") as stream:
            writer = csv.writer(stream)
            writer.writerow(["relative_path", "field_code", "normalized_value"])
            for filename, fields in expected.items():
                for code, value in fields.items():
                    writer.writerow([filename, code, value])
        mechanical = {"fields": output.relative_to(run).as_posix()}
        artifacts = [output, workspace / "summary.md"]
    for artifact in artifacts:
        if not artifact.exists():
            artifact.write_text(
                "SYNTHETIC verifier artifact, not a readable workflow result."
            )
    durable = workspace / "saved-review.json"
    write(durable, {"synthetic_test_fixture": True, "note": "Retained review boundary"})
    manifest = json.loads((run / "run.json").read_text())
    review.update(
        {
            "outcome": "passed",
            "reason": "Synthetic verifier test only",
            "reviewer": "pytest synthetic fixture",
            "date": "2026-10-01T10:00:00+02:00",
            "session_id": f"fixture-{case}-{route}"
            + ("-fresh" if phase == "resume" else ""),
            "host": {
                "name": "Claude Cowork",
                "environment": "synthetic test fixture",
                "model": "synthetic",
                "installed_version": manifest["version"],
                "package_sha256": manifest["package"]["sha256"],
            },
            "checks": {
                check: {
                    "outcome": "passed",
                    "note": "Synthetic verifier test, no host judgment",
                    "evidence_paths": [evidence.relative_to(run).as_posix()],
                }
                for check in acceptance.CHECKS
            },
            "evidence": [record(evidence, run)],
            "artifacts": [record(p, run) for p in artifacts],
            "durable_records": [record(durable, run)],
            "mechanical_files": mechanical,
        }
    )
    write(path, review)
    return path, review


def test_preparation_keeps_answers_and_course_steps_outside_blind_workspace(prepared):
    workspace = prepared / "workspaces/bank/ordinary"
    request = (workspace / "request-demo.txt").read_text()
    assert "1952" not in request
    assert "matched_count" not in request
    assert not list(workspace.rglob("course.json"))
    assert not list(workspace.rglob("cases.json"))
    assert (workspace / "demo/bank-march.csv").read_bytes() == (
        prepared / "workspaces/bank/guided/demo/bank-march.csv"
    ).read_bytes()


def test_preparation_is_not_execution_or_a_release_pass(prepared):
    result = acceptance.verify(prepared)
    assert set(result["outcomes"].values()) == {"not_run"}
    assert result["core_passed"] is False
    assert result["all_passed"] is False


def test_previous_run_is_never_overwritten(prepared):
    before = (prepared / "run.json").read_bytes()
    with pytest.raises(ValueError, match="previous runs are preserved"):
        acceptance.prepare(PACKAGE, prepared, package_url="https://example.test")
    assert (prepared / "run.json").read_bytes() == before


def test_scan_is_image_only_and_retains_the_existing_fixture_lineage(prepared):
    import pymupdf

    scan = prepared / "workspaces/fiscal-scan/ordinary/demo/F24-first-scan.pdf"
    with pymupdf.open(scan) as doc:
        assert doc[0].get_text() == ""
        assert doc[0].get_images()
    derivation = json.loads(
        (prepared / "derivations/fiscal-scan-ordinary-demo.json").read_text()
    )
    original = prepared / "workspaces/fiscal/ordinary/demo/F24-first.md"
    assert derivation["source_sha256"] == record(original, prepared)["sha256"]
    assert not (scan.parent / "F24-first.md").exists()


@pytest.mark.parametrize("case", ["bank", "fiscal", "report", "fiscal-scan"])
def test_valid_scoped_review_does_not_certify_other_routes(prepared, case):
    reviewed(prepared, case)
    result = acceptance.verify(prepared)
    assert result["outcomes"][f"{case}/ordinary/demo"] == "passed"
    assert result["outcomes"][f"{case}/guided/demo"] == "not_run"
    assert result["core_passed"] is False


@pytest.mark.parametrize(
    "change",
    [
        "version",
        "host",
        "missing_check",
        "no_artifacts",
        "no_durable",
        "no_evidence",
        "missing_reviewer",
        "foreign_output",
    ],
)
def test_incomplete_or_non_cowork_pass_is_rejected(prepared, change):
    path, review = reviewed(prepared)
    if change == "version":
        review["host"]["installed_version"] = "0.0.0"
    elif change == "host":
        review["host"]["name"] = "Mac shell"
    elif change == "missing_check":
        review["checks"].pop("source_and_output_links_opened")
    elif change.startswith("no_"):
        review[
            {
                "no_artifacts": "artifacts",
                "no_durable": "durable_records",
                "no_evidence": "evidence",
            }[change]
        ] = []
    elif change == "missing_reviewer":
        review["reviewer"] = ""
    else:
        review["artifacts"].append(record(prepared / "cases.json", prepared))
    write(path, review)
    with pytest.raises(ValueError):
        acceptance.verify(prepared)


@pytest.mark.parametrize("kind", ["package", "input", "output", "evidence", "course"])
def test_changed_evidence_invalidates_review(prepared, kind):
    _, review = reviewed(prepared)
    targets = {
        "package": "package.zip",
        "input": "workspaces/bank/ordinary/demo/bank-march.csv",
        "output": review["artifacts"][0]["path"],
        "evidence": review["evidence"][0]["path"],
        "course": "courses/journal-bank-reconciliation.json",
    }
    path = prepared / targets[kind]
    path.write_bytes(path.read_bytes() + b"changed")
    with pytest.raises(ValueError):
        acceptance.verify(prepared)


@pytest.mark.parametrize("phase", ["practice", "resume"])
def test_follow_up_cannot_pass_without_prior_accepted_work(prepared, phase):
    reviewed(prepared, phase=phase)
    with pytest.raises(ValueError, match="preceding accepted run"):
        acceptance.verify(prepared)


def test_fresh_session_resume_preserves_prior_files_and_reviews(prepared):
    reviewed(prepared)
    reviewed(prepared, phase="practice")
    reviewed(prepared, phase="resume")
    result = acceptance.verify(prepared)
    assert result["outcomes"]["bank/ordinary/resume"] == "passed"


def test_resume_in_same_session_is_rejected(prepared):
    reviewed(prepared)
    reviewed(prepared, phase="practice")
    path, review = reviewed(prepared, phase="resume")
    review["session_id"] = "fixture-bank-ordinary"
    write(path, review)
    with pytest.raises(ValueError, match="new Cowork session"):
        acceptance.verify(prepared)


def test_ordinary_and_guided_routes_cannot_share_one_session(prepared):
    reviewed(prepared)
    path, review = reviewed(prepared, route="guided")
    review["session_id"] = "fixture-bank-ordinary"
    write(path, review)
    with pytest.raises(ValueError, match="independent Cowork sessions"):
        acceptance.verify(prepared)


@pytest.mark.parametrize("case", ["bank", "fiscal", "report"])
def test_wrong_actual_native_result_fails_even_with_positive_review(prepared, case):
    path, review = reviewed(prepared, case)
    output = prepared / next(iter(review["mechanical_files"].values()))
    if case == "bank":
        value = json.loads(output.read_text())
        value["matched_count"] = 99
        write(output, value)
    elif case == "report":
        write(
            output,
            {
                "entries": [
                    {
                        "evidence_id": "wrong.sum",
                        "value": "106000",
                        "source_sheet": "Income Statement",
                    }
                ]
            },
        )
    else:
        output.write_text(output.read_text().replace("28000.00", "280000.00"))
    review["artifacts"][0] = record(output, prepared)
    write(path, review)
    with pytest.raises(ValueError):
        acceptance.verify(prepared)


def test_reference_free_amount_match_is_rejected(prepared):
    path, review = reviewed(prepared)
    matches = prepared / review["mechanical_files"]["matches"]
    matches.write_text(matches.read_text().replace("trn001", ""))
    review["artifacts"][1] = record(matches, prepared)
    write(path, review)
    with pytest.raises(ValueError, match="reference evidence"):
        acceptance.verify(prepared)


def test_missing_route_cannot_reduce_release_scope(prepared):
    manifest = json.loads((prepared / "run.json").read_text())
    manifest["steps"].pop()
    write(prepared / "run.json", manifest)
    with pytest.raises(ValueError, match="Missing or duplicate"):
        acceptance.verify(prepared)


def test_symlinked_evidence_is_rejected(prepared):
    _, review = reviewed(prepared)
    evidence = prepared / review["evidence"][0]["path"]
    target = evidence.with_suffix(".original")
    evidence.rename(target)
    evidence.symlink_to(target)
    with pytest.raises(ValueError, match="symlinked"):
        acceptance.verify(prepared)


def test_failed_or_blocked_observation_is_preserved_without_fabricating_pass(prepared):
    path, review = reviewed(prepared)
    review["outcome"] = "blocked"
    review["reason"] = "Synthetic OCR capability absent"
    review["artifacts"] = []
    review["durable_records"] = []
    write(path, review)
    result = acceptance.verify(prepared)
    assert result["outcomes"]["bank/ordinary/demo"] == "blocked"


@pytest.mark.parametrize("category", ["artifacts", "durable_records"])
def test_failed_run_still_preserves_recorded_file_evidence(prepared, category):
    path, review = reviewed(prepared)
    review["outcome"] = "failed"
    review["reason"] = "Synthetic broken delivery link"
    write(path, review)
    recorded = prepared / review[category][0]["path"]
    recorded.write_text("Changed after the failure was recorded")
    with pytest.raises(ValueError, match="Evidence changed"):
        acceptance.verify(prepared)


def test_cli_release_gate_fails_when_no_host_steps_ran(prepared):
    result = subprocess.run(
        [
            sys.executable,
            str(ROOT / "scripts/cowork_acceptance/cowork_acceptance.py"),
            "verify",
            str(prepared),
            "--require-core-passed",
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 1
    assert "acceptance is incomplete" in result.stderr


@pytest.mark.parametrize(
    "field,before,after",
    [
        ("date", "2026-03-18", "2026-03-19"),
        ("reference", "trn001", "trn003"),
        ("reuse", "journal-1", "journal-0"),
    ],
)
def test_correct_counts_cannot_hide_wrong_pairs_or_reused_evidence(
    prepared, field, before, after
):
    path, review = reviewed(prepared)
    matches = prepared / review["mechanical_files"]["matches"]
    matches.write_text(matches.read_text().replace(before, after))
    review["artifacts"][1] = record(matches, prepared)
    write(path, review)
    with pytest.raises(ValueError):
        acceptance.verify(prepared)


def test_report_totals_cannot_be_swapped_between_source_tables(prepared):
    path, review = reviewed(prepared, "report")
    ledger = prepared / review["mechanical_files"]["numeric_ledger"]
    values = json.loads(ledger.read_text())
    values["entries"][0]["value"], values["entries"][1]["value"] = (
        values["entries"][1]["value"],
        values["entries"][0]["value"],
    )
    write(ledger, values)
    review["artifacts"][0] = record(ledger, prepared)
    write(path, review)
    with pytest.raises(ValueError, match="Report totals"):
        acceptance.verify(prepared)


def test_updated_work_cannot_overwrite_previous_outputs(prepared):
    _, demo = reviewed(prepared)
    reviewed(prepared, phase="practice")
    output = prepared / demo["artifacts"][0]["path"]
    output.write_text("Overwritten by the later run")
    with pytest.raises(ValueError, match="Evidence changed"):
        acceptance.verify(prepared)


def test_complete_core_attestation_does_not_certify_the_unrun_scan(prepared):
    for case in ("bank", "fiscal", "report"):
        for route in acceptance.ROUTES:
            for phase in acceptance.PHASES:
                reviewed(prepared, case, phase, route)
    result = acceptance.verify(prepared)
    assert result["core_passed"] is True
    assert result["all_passed"] is False
    assert result["outcomes"]["fiscal-scan/ordinary/demo"] == "not_run"
