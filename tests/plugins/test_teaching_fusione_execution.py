"""Execute P1 from shipped fictional inputs; never attest a learner or real approval."""

from __future__ import annotations

import hashlib
import importlib
import json
from pathlib import Path

import pytest

from tests.plugins._teaching_release import record_native_check

__all__ = ["test_fusione_kit_executes_both_branches_and_reopens_changes"]
ROOT = Path(__file__).resolve().parents[2]
KIT = ROOT / "plugins/vera/assets/courses/fusione-guidata"


@pytest.mark.parametrize("language", ["it", "en", "fr", "de", "es"])
@pytest.mark.parametrize("phase", ["demo", "practice"])
def test_fusione_kit_executes_both_branches_and_reopens_changes(
    tmp_path, monkeypatch, record_property, language, phase
):
    """Read exact kit facts, execute archive/case APIs and inspect exported results."""
    monkeypatch.syspath_prepend(str(ROOT / "plugins/fusione-guidata/scripts"))
    native = importlib.import_module("fusione_p1_demo")
    case = importlib.import_module("fusione_case")
    report = importlib.import_module("fusione_report")
    filename = "ordinary.json" if phase == "demo" else "wholly-owned.json"
    source = KIT / ("files/input" if phase == "demo" else "files/practice") / filename
    inputs = json.loads(source.read_text())
    assert inputs["synthetic"] is True
    original = native.Demo.fact
    used = set()

    def from_input(self, name, value, kind="text", company="alpha"):
        if name.startswith("section_"):
            # A separately authored test narrative; no prepared output is shipped.
            value = (
                "SYNTHETIC source-bound review section "
                + name.removeprefix("section_")
                + ": Alpha/Beta at 2026-09-30. Only the selected balance, ownership "
                "and valuation evidence is supplied. Mandate, contracts, workforce, "
                "tax treatment, statutory project fields and execution receipts "
                "require professional evidence and review; no real approval or filing."
            )
        else:
            row = inputs["facts"][name]
            used.add(name)
            company, value, kind = row["company"], row["value"], row["value_kind"]
        return original(self, name, value, kind, company)

    monkeypatch.setattr(native.Demo, "fact", from_input)
    original_paper = native.Demo.paper

    def from_convention(self, name, kind, request):
        if kind == "Deadline":
            for event in request["events"]:
                event.update(inputs["calendar_conventions"][event["id"]])
        return original_paper(self, name, kind, request)

    monkeypatch.setattr(native.Demo, "paper", from_convention)
    demo = native.prepare_case(tmp_path / "case-run", inputs["branch"])
    store = demo.store
    exchange = store.read("exchange")["data"]["result"]
    bridge = store.read("bridge")["data"]["result"]
    calendar = store.read("calendar")["data"]["result"]
    assert used == set(inputs["facts"])
    assert bridge["opening_residual"] == "0.00"
    assert store.read("dossier")["data"]["result"]["filing"] == "not_performed"
    assert "archive_receipt" in store.read("evidence_units_a")["data"]
    assert "archive_receipt" in store.read("evidence_beta_liabilities")["data"]
    if phase == "demo":
        assert exchange["exchange_ratio"] == "2/1"
        assert exchange["new_units"] == "40000/1"
        assert exchange["allocations"][1]["resulting_fraction"] == "2/5"
        assert bridge["difference_signed_debit"] == "-110000.00"
    else:
        assert exchange["exchange_ratio"] is None
        assert exchange["new_units"] == "0/1"
        assert bridge["difference_signed_debit"] == "180000.00"
    assert bridge["posting_status"] == "draft_not_posted"
    assert bridge["journal_residual"] == "0.00"
    assert bridge["automatic_goodwill"] is False
    assert bridge["opening_journal"]
    assert bridge["tax_register"][0]["tax"] == (
        "350000.00" if phase == "demo" else "500000.00"
    )
    events = {row["id"]: row for row in calendar["events"]}
    assert events["creditor_wait"]["computed_boundary"] == "2026-12-02"
    assert events["creditor_wait"]["check"] == "not_evidenced"
    assert events["annual_accounts"]["computed_boundary"] == "2026-09-30"
    assert store.read("evidence_creditor_wait_anchor_1")["scope"] == ["beta"]
    before = report.export_report(store, demo.root / "before")
    saved = Path(before["review_html"]).read_bytes()
    assert b"SYNTHETIC source-bound review section" in saved
    assert b"Quali dati arrivano al modello" in saved
    assert "not_requested" == before["server_receipt"]

    update = json.loads((KIT / "files/practice/update.json").read_text())
    # Persist the separate selected practice source in Beta's genuine archive.
    updated = original(
        demo,
        "beta_liabilities_updated",
        update["value"],
        update["value_kind"],
        update["company"],
    )
    previous = store.read(update["fact"])
    store.put(
        previous["id"],
        "Fact",
        {**previous["data"], "value": update["value"]},
        scope=previous["scope"],
        dependencies=store.read(updated["id"])["dependencies"],
        expected_version=previous["version"],
    )
    assert store.status("bridge")["review_state"] == "needs_review"
    assert store.status("dossier")["review_state"] == "needs_review"
    assert store.status("calendar")["review_state"] == "approved_for_defined_scope"
    assert store.read("approval_dossier")["data"]["target"]["version"] == 1
    assert store.read("beta_liabilities", version=1)["data"]["value"] == "-200000"
    refreshed = store.read("bridge")["data"]["request"]
    refreshed["balances_b"][1]["balance"] = case.reference(
        store.read("beta_liabilities")
    )
    blocked = store.workpaper("bridge", "BookBridge", refreshed, expected_version=1)
    assert "unbalanced_target_trial_balance" in blocked["data"]["issues"]
    assert "opening_balance_does_not_reconcile" in blocked["data"]["issues"]
    assert blocked["data"]["result"]["opening_residual"] == "-100.00"
    after = report.export_report(store, demo.root / "after")
    assert Path(before["review_html"]).read_bytes() == saved
    assert b"needs_review" in Path(after["review_html"]).read_bytes()
    # Reopen using the durable API, not the in-memory objects.
    reopened = case.CaseStore(demo.root / "case", "synthetic_reviewer")
    assert reopened.read("beta_liabilities")["version"] == 2
    inspection = {
        "language": language,
        "phase": phase,
        "input_sha256": hashlib.sha256(source.read_bytes()).hexdigest(),
        "reports": {"before": before, "after": after},
        "boundary": "Scripted synthetic confirmations only; no professional or learner acceptance.",
    }
    (tmp_path / "inspection.json").write_text(json.dumps(inspection, indent=2))
    record_native_check(
        record_property,
        root=ROOT,
        product="vera",
        workflow="fusione-guidata",
        language=language,
        phase=phase,
    )


def test_fusione_course_starts_bound_tutorial_without_professional_profile(
    tmp_path, monkeypatch
):
    """Verify first-use course selection and genuine managed intake, without progress claims."""
    import subprocess
    import sys

    monkeypatch.syspath_prepend(str(ROOT / "plugins/_shared/vendor/modules"))
    from courseware.library import CourseLibrary

    rendered = CourseLibrary(ROOT / "plugins/vera", {"fusione-guidata"}).render(
        "fusione-guidata", "it", tmp_path / "rendered"
    )
    state = tmp_path / "isolated-profile"
    request = tmp_path / "begin.json"
    request.write_text(
        json.dumps(
            {
                "workflow_id": "fusione-guidata",
                "title": "Synthetic course contract check",
                "goal": "Verify intake only",
                "mode": "show",
                "pair": {
                    "teacher_thread_id": "synthetic-teacher",
                    "worker_thread_id": "synthetic-worker",
                },
            }
        )
    )
    result = subprocess.run(
        [
            sys.executable,
            str(ROOT / "plugins/vera/scripts/local_teaching.py"),
            "begin",
            "--state-root",
            str(state),
            "--input",
            str(request),
        ],
        capture_output=True,
        text=True,
        check=True,
    )
    started = json.loads(result.stdout)
    session = started["session"]
    command = [
        sys.executable,
        str(ROOT / "plugins/vera/scripts/local_onboarding_case.py"),
        "--state-root",
        str(state),
        "--session",
        session["session_id"],
        "--thread-id",
        "synthetic-worker",
        "--workflow",
        "fusione-guidata",
        "--token",
        session["worker_token"],
        "--phase",
        "demo",
    ]
    for source in rendered["source_files"]:
        command.extend(["--source", str(source)])
    result = subprocess.run(command, capture_output=True, text=True, check=True)
    prepared = json.loads(result.stdout)
    assert prepared["tutorial"] is True
    assert prepared["local_only"] is True
    assert Path(prepared["context_path"]).is_file()
    assert Path(prepared["output_dir"]).is_relative_to(Path(session["directory"]))
    assert started["profile"] is None
    assert "demo" not in session
