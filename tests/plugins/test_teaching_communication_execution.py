"""Native integration runs with explicit synthetic professional confirmations.

Inputs/contributions and their independently authored assessments are the actual
local teaching checks. Approval transitions are test fixtures, never evidence of
learner understanding or real professional confirmation. Nothing is transmitted.
"""

from __future__ import annotations

import hashlib
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from tests.plugins._teaching_release import record_native_check

REPO = Path(__file__).resolve().parents[2]
SCRIPTS = REPO / "plugins/comunicazione-professionale/scripts"
SOURCE = REPO / "tests/fixtures/teaching_communication"
MANIFEST = json.loads((SOURCE / "manifest.json").read_text(encoding="utf-8"))
ROWS = MANIFEST["cases"]
FICTIONAL_LABELS = {
    "it": "Esercitazione didattica:",
    "en": "Teaching exercise:",
    "fr": "Exercice pédagogique :",
    "de": "Übungsmaterial:",
    "es": "Ejercicio didáctico:",
}


def native(script, *args, check=True):
    result = subprocess.run(
        [sys.executable, str(SCRIPTS / script), *map(str, args)],
        text=True,
        capture_output=True,
        encoding="utf-8",
        timeout=60,
    )
    if check:
        assert result.returncode == 0, result.stdout + result.stderr
    return result


def read(p):
    return json.loads(p.read_text(encoding="utf-8"))


def write(p, data):
    p.write_text(
        json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    return p


@pytest.mark.parametrize("row", ROWS, ids=[r["run_id"] for r in ROWS])
def test_native_communication_package_with_synthetic_review_transitions(
    tmp_path, row, record_property
):
    (tmp_path / ".vera-onboarding-local-only").write_text(
        "Fictional integration check. Native user/profile/feedback state is not used.\n"
    )
    write(
        tmp_path / "TEST-FIXTURE-NOT-HUMAN-APPROVAL.json",
        {
            "purpose": "Native integration verification",
            "all_professional_confirmations": "synthetic test inputs",
            "learner_understanding": "not assessed",
            "published": False,
        },
    )
    workspace = tmp_path / "workspace"
    native(
        "initialize_workspace.py",
        "--workspace",
        workspace,
        "--workspace-id",
        "synthetic-communication-teaching-check",
        "--owner",
        "Synthetic integration-test firm, not an actual professional",
        "--retention-owner",
        "Local test operator",
        "--authorized-by",
        "Fictional release verification requested by product owner",
        "--confirmed-by-user",
    )
    native(
        "qualify_editorial_assessor.py",
        "--workspace",
        workspace,
        "--results",
        SOURCE / "editorial_benchmark.json",
        "--recorded-by",
        "Regression test copying the actually executed independent qualification",
    )
    run_id = row["run_id"]
    old = SOURCE / run_id
    for name, expected in row["files"].items():
        assert hashlib.sha256((old / name).read_bytes()).hexdigest() == expected
    for source in row["sources"]:
        assert (
            hashlib.sha256((REPO / source["path"]).read_bytes()).hexdigest()
            == source["sha256"]
        )
    for relative, expected in MANIFEST["kit_inputs"][row["product"]].items():
        assert hashlib.sha256((REPO / relative).read_bytes()).hexdigest() == expected
    assert (
        hashlib.sha256((SOURCE / "editorial_benchmark.json").read_bytes()).hexdigest()
        == MANIFEST["benchmark_sha256"]
    )
    intake = read(old / "intake.json")
    historical = read(old / "historical_run_intake.json")
    for key in (
        "objective",
        "audience",
        "language",
        "jurisdiction",
        "studio_format_brief",
        "brand_profile",
    ):
        assert intake[key] == historical[key]
    for source in intake["source_inputs"]:
        source["path"] = str(REPO / source["path"])
    native(
        "prepare_run.py",
        "--workspace",
        workspace,
        "--intake",
        write(tmp_path / "intake.json", intake),
    )
    run = workspace / "runs" / run_id
    for name in (
        "model_contribution.json",
        "answer_contract.json",
        "claim_assurance.json",
        "editorial_assessment.json",
    ):
        shutil.copyfile(old / name, run / name)
    native(
        "prepare_model_phase.py",
        "--run-dir",
        run,
        "--phase",
        "claim_assurance",
        "--contribution",
        run / "model_contribution.json",
        "--answer-contract",
        run / "answer_contract.json",
    )
    native(
        "prepare_model_phase.py",
        "--run-dir",
        run,
        "--phase",
        "editorial_assessment",
        "--contribution",
        run / "model_contribution.json",
        "--claim-assurance",
        run / "claim_assurance.json",
    )
    generator = row["generation_session_id"]
    provenance = []
    for prefix in ("", "claim-assessment-", "assessment-"):
        provenance.extend(
            [
                f"--{prefix}provider",
                "OpenAI",
                f"--{prefix}model",
                "GPT-6 (exact serving model identifier unavailable)",
            ]
        )
    native(
        "record_contribution.py",
        "--run-dir",
        run,
        "--contribution",
        run / "model_contribution.json",
        "--answer-contract",
        run / "answer_contract.json",
        "--claim-assurance",
        run / "claim_assurance.json",
        "--editorial-assessment",
        run / "editorial_assessment.json",
        *provenance,
        "--template-version",
        "professional-communication-v3",
        "--generation-session-id",
        generator,
        "--recorded-by",
        "Test fixture, original independent model artifacts retained unchanged",
    )
    workbench = read(run / "content_workbench.json")
    assert workbench["post_generation_review_scopes"] == ["packaged_output"]
    blocked = native("package_communications.py", "--run-dir", run, check=False)
    assert blocked.returncode != 0
    note = "Synthetic integration-test professional acceptance. Not a real user confirmation or lesson-completion record."
    bundle = write(
        tmp_path / "synthetic-semantic-review.json",
        {
            "schema_version": 1,
            "run_id": run_id,
            "decisions": [
                {"scope": scope, "decision": "accepted", "note": note}
                for scope in workbench["required_review_scopes"]
            ],
        },
    )
    native(
        "record_review.py",
        "--run-dir",
        run,
        "--bundle",
        bundle,
        "--reviewer",
        "SYNTHETIC TEST REVIEWER (not a real professional)",
        "--confirmed-by-user",
    )
    native("promote_studio_profile.py", "--run-dir", run)
    native("package_communications.py", "--run-dir", run)
    assert read(run / "final_artifacts.json")["status"] == "validation_pending"
    faq = (run / "drafts/faq.md").read_text(encoding="utf-8")
    candidate = read(run / "model_contribution.json")
    assert candidate["channel_drafts"][0]["title"] in faq
    assert "https://www.edpb.europa.eu/" in faq
    assert len(faq) > 1500
    faq_draft = next(d for d in candidate["channel_drafts"] if d["channel"] == "faq")
    questions = re.findall(
        r"^(?:### (.+)|\*\*(.+)\*\*)$", faq_draft["body"], re.MULTILINE
    )
    questions = [heading or bold for heading, bold in questions]
    assert len(questions) == len(set(questions)) == 6
    # The renderer emits both body and sections. This guards the actual prior
    # defect where each reviewed question and answer was printed twice.
    assert all(faq.count(question) == 1 for question in questions)
    assert faq.count(faq_draft["body"]) == 1
    assert FICTIONAL_LABELS[row["language"]] in faq
    if row["phase"] == "practice":
        email = (run / "drafts/client_email.txt").read_text(encoding="utf-8")
        profile = candidate["studio_profile_proposal"]["email"]
        draft = next(
            d for d in candidate["channel_drafts"] if d["channel"] == "client_email"
        )
        assert draft["subject"] in email.splitlines()[0]
        assert f"\n{draft['title']}\n" not in email
        assert email.count(profile["salutation"]) == 1
        assert email.count(profile["closing"]) == 1
        assert draft["body"] in email
        assert FICTIONAL_LABELS[row["language"]] in email
    assert not (run / "visual_manifest.json").exists()
    assert not (run / "visuals").exists()
    before = hashlib.sha256((run / "drafts/faq.md").read_bytes()).hexdigest()
    native(
        "record_review.py",
        "--run-dir",
        run,
        "--scope",
        "packaged_output",
        "--decision",
        "accepted",
        "--reviewer",
        "SYNTHETIC TEST REVIEWER (not a real professional)",
        "--note",
        note,
        "--confirmed-by-user",
    )
    native("validate_run.py", "--run-dir", run)
    final = read(run / "final_artifacts.json")
    assert final["status"] == "final_ready"
    assert before == hashlib.sha256((run / "drafts/faq.md").read_bytes()).hexdigest()
    assert all(not route["selected"] for route in intake["external_routes"].values())

    record_native_check(
        record_property,
        root=REPO,
        product=row["product"],
        workflow="comunicazione-professionale",
        language=row["language"],
        phase=row["phase"],
    )
