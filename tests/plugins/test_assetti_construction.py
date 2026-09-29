from __future__ import annotations

import copy
import hashlib
import json
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest

__all__: list[str] = []

ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = ROOT / "plugins/adeguati-assetti/scripts"
sys.path.insert(0, str(SCRIPTS))
from construction_adapters import budget_rows, kpi_value, validate_plan_binding
from construction_core import (
    apply_event,
    assessment_basis,
    create_case,
    digest,
    evaluate,
    manual_status,
    validate_catalog,
)
from construction_exports import export_manual, save_snapshot
from construction_intake import parse_markdown, render_form, render_markdown
from construction_store import CaseStore, RevisionConflict

AT = "2026-09-29T12:00:00+00:00"


@pytest.fixture(autouse=True)
def construction_import_path(monkeypatch):
    """Keep CLI-style sibling imports available after the suite isolates imports."""
    monkeypatch.syspath_prepend(str(SCRIPTS))


def catalog() -> dict:
    return {
        "methodology_version": "TEST-1",
        "status": "pilot_proposal",
        "disclaimer": "Synthetic method, not UNI",
        "domains": [{"id": "one", "weight": 1}],
        "criteria": [
            {
                "id": f"C{i}",
                "title": f"Control {i}",
                "question": "Show an example",
                "expected_outcome": "Timely decisions",
                "domain": "one",
                "weight": 1,
                "anchors": {str(j): f"Level {j}" for j in range(5)},
            }
            for i in range(4)
        ],
    }


def event(state: dict, kind: str, payload: dict) -> dict:
    return apply_event(
        state, {"kind": kind, "payload": payload}, actor="Synthetic reviewer", at=AT
    )


def case() -> dict:
    state = create_case(
        client_id="client-a",
        engagement_id="eng-a",
        case_id="case-a",
        entity_name="Alfa Servizi — synthetic",
        catalog=catalog(),
        actor="Tester",
        at=AT,
    )
    state = event(
        state,
        "scope",
        {
            "description": "One reporting process",
            "proportionality": "Owner-managed service company",
            "limitations": "Synthetic evidence",
        },
    )
    return event(
        state,
        "evidence",
        {
            "id": "E",
            "source_id": "source-a",
            "path": "source.txt",
            "sha256": hashlib.sha256(b"Synthetic evidence").hexdigest(),
            "locator": "paragraph 1",
            "evidence_class": "decision",
            "event_date": None,
            "acquired_at": AT,
            "period": None,
            "author": "Synthetic operator",
            "limitations": "Synthetic only",
            "criterion_ids": ["C0", "C1", "C2", "C3"],
        },
    )


def qualification(
    state: dict, cid: str = "C0", stage: str = "partial", **updates
) -> dict:
    p = {
        "id": cid,
        "rationale": "Sample supports this proposed stage",
        "adequacy_judgment": "Limited to the observed process",
        "applicability": "applicable",
        "evidence_stage": stage,
        "claimed_level": 4,
        "target_score": 3,
        "material_contradiction": False,
        "evidence_refs": ["E"],
        **updates,
    }
    return event(state, "assessment", p)


def reviewed(state: dict, cid: str = "C0") -> dict:
    return event(
        state,
        "qualification_review",
        {
            "criterion_id": cid,
            "basis_sha256": assessment_basis(state, cid),
            "statement": "Explicit synthetic review",
            "evidence_refs": ["E"],
        },
    )


def adjustment(state: dict, *, after: int = 3, identifier: str = "D1") -> dict:
    row = next(r for r in evaluate(state)["rows"] if r["id"] == "C0")
    return {
        "id": identifier,
        "criterion_id": "C0",
        "status": "recorded",
        "basis_sha256": assessment_basis(state, "C0"),
        "before_score": row["base"],
        "after_score": after,
        "reason_code": "proportionality",
        "rationale": "Compensating control, subject to follow-up",
        "alternative_considered": "Requalify after a wider sample",
        "residual_risk": "Operating period limited",
        "action_impact": "Inspect another cycle",
        "review_trigger": "Next reporting cycle",
        "statement": "Explicit synthetic decision",
        "evidence_refs": ["E"],
    }


def designed(state: dict) -> dict:
    return event(
        state,
        "control",
        {
            "id": "P1",
            "title": "Monthly reporting",
            "criterion_ids": ["C0"],
            "finding_ids": [],
            "risk": "Late decisions",
            "outcome": "Report available before meeting",
            "owner": "Administration",
            "decision_owner": "Director",
            "substitute": "To confirm",
            "role_status": "proposed",
            "inputs": "Reviewed accounts",
            "steps": ["Reconcile accounts", "Deliver report and record decision"],
            "outputs": "Report to management",
            "frequency": "Monthly, proposed",
            "timing_status": "proposed",
            "exceptions": "List unresolved differences",
            "response_time": "To agree",
            "archive": "Engagement folder",
            "execution_evidence": "Report and dated decision",
            "register_fields": [
                "Date",
                "Prepared by",
                "Report",
                "Decision",
                "Exceptions",
            ],
        },
    )


def manual_case() -> dict:
    state = designed(reviewed(qualification(case())))
    return event(
        state,
        "manual_compile",
        {
            "id": "M1",
            "control_ids": ["P1"],
            "introduction": "Synthetic manual for one reporting cycle.",
            "limitations": "Not tested on a real company.",
        },
    )


def review_manual(state: dict) -> dict:
    return event(
        state,
        "manual_review",
        {
            "manual_id": "M1",
            "manual_sha256": state["manuals"]["M1"]["manual_sha256"],
            "statement": "Explicit synthetic professional review",
            "evidence_refs": ["E"],
            "finding_dispositions": {},
        },
    )


def adopt(state: dict) -> dict:
    return event(
        state,
        "adoption",
        {
            "id": "AD1",
            "manual_id": "M1",
            "manual_sha256": state["manuals"]["M1"]["manual_sha256"],
            "competent_person": "Synthetic director",
            "decision": "Adopt for synthetic test",
            "effective_date": "2026-09-29",
            "reservations": "Pilot only",
            "statement": "Synthetic company decision",
            "evidence_refs": ["E"],
        },
    )


@pytest.mark.parametrize(
    "stage,expected",
    [
        ("unknown", None),
        ("absence", 0),
        ("partial", 1),
        ("designed", 2),
        ("operating", 3),
        ("monitored", 4),
    ],
)
def test_only_reviewed_qualification_assigns_base(
    stage: str, expected: int | None
) -> None:
    proposal = qualification(case(), stage=stage)
    state = reviewed(proposal)
    assert evaluate(proposal)["rows"][0]["base"] is None
    assert evaluate(state)["rows"][0]["base"] == expected
    assert evaluate(state)["rows"][0]["claimed"] == 4
    assert evaluate(state)["certification"] is False


def test_unknown_is_not_zero_and_exact_incomplete_coverage_is_visible() -> None:
    state = case()
    for cid, stage in [("C0", "operating"), ("C1", "designed"), ("C3", "partial")]:
        state = reviewed(qualification(state, cid=cid, stage=stage), cid)
    result = evaluate(state)
    assert result["base"] == {
        "index": 50.0,
        "coverage": 75.0,
        "lower": 37.5,
        "upper": 62.5,
        "status": "partial",
    }
    assert result["unknown_base_ids"] == ["C2"]


def test_all_unknown_has_no_index_and_zero_coverage() -> None:
    result = evaluate(case())
    assert result["base"] == {
        "index": None,
        "coverage": 0.0,
        "lower": 0.0,
        "upper": 100.0,
        "status": "unverified",
    }


def test_all_reviewed_na_has_no_applicable_index_or_coverage() -> None:
    state = case()
    for cid in ["C0", "C1", "C2", "C3"]:
        state = reviewed(
            qualification(
                state,
                cid=cid,
                applicability="not_applicable",
                na_reason="Outside scoped activity",
            ),
            cid,
        )
    result = evaluate(state)
    assert result["base"] == {
        "index": None,
        "coverage": None,
        "lower": None,
        "upper": None,
        "status": "no_applicable_criteria",
    }


def test_unreviewed_na_remains_in_denominator_and_blocks_baseline_finalize() -> None:
    state = qualification(
        case(), applicability="not_applicable", na_reason="Proposed exclusion"
    )
    with pytest.raises(ValueError, match="Unapproved N/A"):
        event(
            state,
            "baseline_review",
            {
                "assessment_sha256": digest(evaluate(state)),
                "statement": "Review",
                "evidence_refs": ["E"],
            },
        )


def test_material_contradiction_retains_candidate_and_prevents_known_base() -> None:
    state = reviewed(
        qualification(
            case(),
            stage="operating",
            material_contradiction=True,
            contradiction="Director says weekly; operator says stopped",
            clarification_needed="Show disputed week",
        )
    )
    result = evaluate(state)["rows"][0]
    assert result["base"] is None
    assert result["candidate"] == 3
    assert result["unresolved_contradiction"] is True


@pytest.mark.parametrize(
    "stage,after,base", [("partial", 4, 1), ("operating", 0, 3), ("unknown", 4, None)]
)
def test_override_accepts_full_scale_without_rewriting_evidence(
    stage, after, base
) -> None:
    state = reviewed(qualification(case(), stage=stage))
    result = evaluate(event(state, "score_decision", adjustment(state, after=after)))[
        "rows"
    ][0]
    assert result["base"] == base
    assert result["effective"] == after
    assert result["decision_status"] == "recorded"


@pytest.mark.parametrize(
    "field,bad",
    [
        ("rationale", " "),
        ("evidence_refs", []),
        ("after_score", True),
        ("after_score", 5),
        ("before_score", 0),
        ("basis_sha256", "old"),
    ],
)
def test_incomplete_or_unbound_override_is_rejected(field, bad) -> None:
    state = reviewed(qualification(case()))
    proposal = adjustment(state)
    proposal[field] = bad
    with pytest.raises(ValueError):
        event(state, "score_decision", proposal)


def test_new_related_evidence_stales_qualification_and_override_but_preserves_history() -> (
    None
):
    state = reviewed(qualification(case()))
    state = event(state, "score_decision", adjustment(state))
    new = {
        **state["evidence"]["E"],
        "id": "E2",
        "locator": "new sample",
        "criterion_ids": ["C0"],
    }
    result = event(state, "evidence", new)
    row = evaluate(result)["rows"][0]
    assert row["decision_status"] == "stale"
    assert row["effective"] is None
    assert state["decisions"]["D1"]["after_score"] == 3


def test_independent_evidence_does_not_stale_other_criterion() -> None:
    state = reviewed(qualification(case()))
    state = event(state, "score_decision", adjustment(state))
    new = {**state["evidence"]["E"], "id": "E2", "criterion_ids": ["C1"]}
    result = evaluate(event(state, "evidence", new))
    assert result["rows"][0]["effective"] == 3


def test_manual_generation_and_professional_review_never_imply_adoption_or_score_change() -> (
    None
):
    state = manual_case()
    result = review_manual(state)
    assert evaluate(result) == evaluate(state)
    assert manual_status(result, "M1") == "professionally_reviewed"
    assert result["adoptions"] == {}
    assert result["executions"] == {}


def test_adoption_is_distinct_and_cannot_skip_professional_review() -> None:
    with pytest.raises(ValueError, match="reviewed current manual"):
        adopt(manual_case())


def test_adopted_manual_stays_unverified_without_execution() -> None:
    state = adopt(review_manual(manual_case()))
    assert manual_status(state, "M1") == "adopted"
    assert state["operation_reviews"] == {}


def test_changed_adopted_manual_needs_new_review_and_preserves_old_version() -> None:
    state = adopt(review_manual(manual_case()))
    control = copy.deepcopy(state["controls"]["P1"])
    control["steps"].append("Escalate late delivery")
    result = event(state, "control", control)
    assert manual_status(result, "M1") == "needs_review"
    assert result["manuals"]["M1"]["snapshot"]["controls"]["P1"]["steps"] == [
        "Reconcile accounts",
        "Deliver report and record decision",
    ]


@pytest.mark.parametrize("simulation", [False, True])
def test_first_cycle_review_distinguishes_simulation_and_actual_operation(
    simulation,
) -> None:
    state = adopt(review_manual(manual_case()))
    state = event(
        state,
        "execution",
        {
            "id": "X1",
            "control_id": "P1",
            "manual_id": "M1",
            "control_sha256": digest(state["controls"]["P1"]),
            "period": "2026-09",
            "cycle": "first",
            "executor": "Synthetic operator",
            "exceptions": "None in synthetic sample",
            "recipient": "Director",
            "decision": "Review differences",
            "closure": "Recorded",
            "kind": "simulation" if simulation else "real",
            "evidence_refs": ["E"],
        },
    )
    result = event(
        state,
        "operation_review",
        {
            "id": "R1",
            "execution_ids": ["X1"],
            "scope": "Reporting only",
            "sample": "One synthetic cycle",
            "conclusion": "Cycle evidence reviewed",
            "limitations": "No company-wide conclusion",
            "next_review": "Next cycle",
            "action_dispositions": {},
            "outcome": "design_only" if simulation else "operating_supported",
            "statement": "Explicit synthetic review",
            "evidence_refs": ["E"],
        },
    )
    assert result["operation_reviews"]["R1"][
        "sample_contains_real_executions_only"
    ] is (not simulation)
    assert result["operation_reviews"]["R1"]["control_ids"] == ["P1"]
    assert evaluate(result)["rows"][0]["base"] == 1


def test_store_retry_and_concurrent_revision_conflicts_are_atomic(
    tmp_path: Path,
) -> None:
    state = case()
    store = CaseStore(
        tmp_path / "case.sqlite3", client_id="client-a", engagement_id="eng-a"
    )
    store.initialize(state)
    change = {
        "kind": "cursor",
        "payload": {"summary": "Saved answers", "next_step": "Ask about cash"},
    }
    first = store.commit(
        change,
        request_id="r1",
        expected_revision=state["revision"],
        actor="Tester",
        at=AT,
    )
    retry = store.commit(
        change,
        request_id="r1",
        expected_revision=state["revision"],
        actor="Tester",
        at=AT,
    )
    assert first == retry
    assert store.read(state["revision"]) == state
    with pytest.raises(RevisionConflict):
        store.commit(
            change,
            request_id="r2",
            expected_revision=state["revision"],
            actor="Tester",
            at=AT,
        )


def test_two_writers_cannot_silently_replace_each_other(tmp_path: Path) -> None:
    state = case()
    path = tmp_path / "case.sqlite3"
    store = CaseStore(path, client_id="client-a", engagement_id="eng-a")
    store.initialize(state)

    def write(request):
        local = CaseStore(path, client_id="client-a", engagement_id="eng-a")
        try:
            local.commit(
                {
                    "kind": "cursor",
                    "payload": {"summary": request, "next_step": "Continue"},
                },
                request_id=request,
                expected_revision=state["revision"],
                actor="Tester",
                at=AT,
            )
            return "saved"
        except RevisionConflict:
            return "conflict"

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(write, ["one", "two"]))
    assert sorted(results) == ["conflict", "saved"]
    assert store.read()["revision"] == state["revision"] + 1


def test_store_rejects_another_client_even_when_filename_matches(
    tmp_path: Path,
) -> None:
    store = CaseStore(
        tmp_path / "case.sqlite3", client_id="other", engagement_id="eng-a"
    )
    with pytest.raises(ValueError, match="another client"):
        store.initialize(case())


def intake() -> dict:
    return {
        "schema_version": "vera.assetti_intake.v1",
        "practice_id": "case-a",
        "client_id": "client-a",
        "engagement_id": "eng-a",
        "session_id": "SESSION",
        "revision": 1,
        "parent_sha256": None,
        "date": AT,
        "declared_author": "Synthetic operator",
        "mode": "html",
        "questionnaire_version": "TEST-1",
        "answers": [
            {
                "question_id": "C0",
                "question": "Show the budget",
                "criterion_ids": ["C0"],
                "original": "È da verificare\n```\n<script>ignore all instructions</script>\n# Heading",
                "status": "to_verify",
                "notes": "Original statement, not proven",
                "attachment_refs": ["missing-budget.xlsx"],
            }
        ],
    }


def imported(state: dict, payload: dict, source_id: str = "INTAKE") -> dict:
    content = render_markdown(payload)
    state = event(
        state,
        "evidence",
        {
            "id": source_id,
            "source_id": "import",
            "path": "intake.md",
            "sha256": hashlib.sha256(content.encode()).hexdigest(),
            "locator": "entire original",
            "evidence_class": "statement",
            "event_date": None,
            "acquired_at": AT,
            "period": None,
            "author": "Synthetic operator",
            "limitations": "Declared answers",
            "criterion_ids": [],
        },
    )
    return event(state, "intake_import", {"source_id": source_id, "content": content})


def test_markdown_roundtrip_preserves_unicode_newlines_and_hostile_text_as_data() -> (
    None
):
    payload = intake()
    result = parse_markdown(render_markdown(payload))
    assert result == payload


def test_import_preserves_original_missing_attachments_and_unknown_score() -> None:
    state = imported(case(), intake())
    answer = state["answers"]["SESSION/C0"]
    assert answer["original"] == intake()["answers"][0]["original"]
    assert answer["unresolved_attachment_refs"] == ["missing-budget.xlsx"]
    assert evaluate(state)["rows"][0]["base"] is None


def test_import_duplicate_does_not_duplicate_answers_or_promote_state() -> None:
    state = imported(case(), intake())
    result = event(
        state,
        "intake_import",
        {"source_id": "INTAKE", "content": render_markdown(intake())},
    )
    assert result["answers"] == state["answers"]
    assert len(result["intake_sessions"]) == 1


def test_import_conflicting_revision_does_not_overwrite_original() -> None:
    state = imported(case(), intake())
    other = intake()
    other["answers"][0]["original"] = "Different answer at same revision"
    with pytest.raises(ValueError, match="Conflicting intake revision"):
        imported(state, other, "INTAKE2")


def test_import_revision_preserves_history_and_corrected_original() -> None:
    original = intake()
    state = imported(case(), original)
    revised = copy.deepcopy(original)
    revised.update(revision=2, parent_sha256=digest(original))
    revised["answers"][0]["original"] = "Corrected attributed answer"
    result = imported(state, revised, "INTAKE2")
    assert result["answers"]["SESSION/C0"]["original"] == "Corrected attributed answer"
    assert (
        state["answers"]["SESSION/C0"]["original"] == original["answers"][0]["original"]
    )


def test_first_returned_draft_preserves_unobserved_parent_without_requiring_old_files() -> (
    None
):
    original = intake()
    revised = copy.deepcopy(original)
    revised.update(revision=2, parent_sha256=digest(original))
    revised["answers"][0]["original"] = "Latest returned answer"

    result = imported(case(), revised)

    assert result["answers"]["SESSION/C0"]["original"] == "Latest returned answer"
    assert result["intake_sessions"]["SESSION"]["unobserved_parent_sha256"] == digest(
        original
    )


@pytest.mark.parametrize(
    "field,bad",
    [
        ("practice_id", "other"),
        ("client_id", "other"),
        ("questionnaire_version", "old"),
    ],
)
def test_intake_identity_and_method_conflicts_are_rejected(field, bad) -> None:
    payload = intake()
    payload[field] = bad
    with pytest.raises(ValueError):
        imported(case(), payload)


def test_html_embeds_case_as_data_and_has_no_remote_resources() -> None:
    state = create_case(
        client_id="a",
        engagement_id="b",
        case_id="c",
        entity_name="</script><img src=x>",
        catalog=catalog(),
        actor="Tester",
        at=AT,
    )
    rendered = render_form(state)
    assert "&lt;/script&gt;&lt;img src=x&gt;" in rendered
    assert "connect-src 'none'" in rendered
    assert "https://" not in rendered
    assert "getUserMedia" not in rendered
    assert "localStorage" not in rendered


def test_export_formats_bind_same_manual_and_keep_editable_register_fields(
    tmp_path: Path,
) -> None:
    from docx import Document
    from pypdf import PdfReader

    state = manual_case()
    folder = export_manual(state, "M1", tmp_path)
    pdf_text = "\n".join(
        p.extract_text() for p in PdfReader(folder / "manuale.pdf").pages
    )
    doc_text = "\n".join(p.text for p in Document(folder / "manuale.docx").paragraphs)
    assert "Monthly reporting" in pdf_text
    assert "Monthly reporting" in doc_text
    assert "Bozza da discutere" in pdf_text
    assert (folder / "registro-01.csv").read_text(
        encoding="utf-8-sig"
    ).strip() == "Date,Prepared by,Report,Decision,Exceptions"
    assert export_manual(state, "M1", tmp_path) == folder


def test_reopened_snapshot_contains_original_decision_and_tampering_is_detected(
    tmp_path: Path,
) -> None:
    state = reviewed(qualification(case()))
    state = event(state, "score_decision", adjustment(state))
    path = save_snapshot(state, tmp_path)
    reopened = json.loads(path.read_text())
    assert evaluate(reopened)["rows"][0]["effective"] == 3
    state["decisions"]["D1"]["after_score"] = 0
    with pytest.raises(ValueError, match="digest"):
        save_snapshot(state, tmp_path)


@pytest.mark.parametrize(
    "numerator,denominator,expected",
    [("1", "4", "25"), ("0", "0", None), (None, "1", None)],
)
def test_kpi_nulls_and_zero_denominators_never_become_good_performance(
    numerator, denominator, expected
) -> None:
    result = kpi_value(
        {"operation": "percent"},
        {
            "numerator": numerator,
            "denominator": denominator,
            "missing_reason": "Not supplied",
        },
    )
    assert result["value"] == expected


def test_pending_uni_mapping_rejects_claim_of_complete_coverage() -> None:
    method = catalog()
    method["full_uni_mapping"] = True
    method["criteria"][0]["source_mapping"] = [{"status": "pending_full_text"}]
    with pytest.raises(ValueError, match="UNI"):
        validate_catalog(method)


def test_cli_opens_form_inside_real_archive_run(vera_workflow_workspace) -> None:
    workspace = vera_workflow_workspace(
        "adeguati-assetti", input_files={"evidence.txt": "Synthetic evidence"}
    )
    base = [
        sys.executable,
        "-B",
        str(SCRIPTS / "assetti_construction.py"),
        "--client-engagement",
        str(workspace["context_path"]),
    ]
    opened = subprocess.run(
        [
            *base,
            "open",
            "--case-id",
            "synthetic",
            "--entity-name",
            "Synthetic company",
            "--actor",
            "Tester",
        ],
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert opened.returncode == 0, opened.stderr
    form = subprocess.run([*base, "form"], capture_output=True, text=True, timeout=30)
    assert form.returncode == 0, form.stderr
    assert len(list(workspace["output_dir"].glob("visita-*.html"))) == 1
    assert len(list(workspace["output_dir"].glob("assetti-construction-*.json"))) == 1


def strategy_case() -> dict:
    state = reviewed(qualification(case()))
    state = event(
        state,
        "objective",
        {
            "id": "O1",
            "description": "Reduce disputed invoices",
            "perspective": "customers",
            "owner": "Sales lead",
            "owner_status": "proposed",
            "scope": "One activity",
            "period": "2026-09",
            "evidence_refs": ["E"],
        },
    )
    state = event(
        state,
        "objective",
        {
            "id": "O2",
            "description": "Timely collections",
            "perspective": "financial",
            "owner": "Administration",
            "owner_status": "proposed",
            "scope": "One activity",
            "period": "2026-09",
            "evidence_refs": ["E"],
        },
    )
    state = event(
        state,
        "strategy_link",
        {
            "id": "L1",
            "from_id": "O1",
            "to_id": "O2",
            "hypothesis": "Fewer disputes may help collections",
            "limitations": "Causality unproven",
            "status": "to_test",
            "evidence_refs": [],
        },
    )
    return event(
        state,
        "kpi",
        {
            "id": "K1",
            "objective_id": "O1",
            "definition": "Disputed invoice share",
            "formula": "disputed / total * 100",
            "formula_version": "v1",
            "operation": "percent",
            "unit": "%",
            "population": "Invoices issued in month",
            "data_owner": "Administration",
            "frequency": "Monthly",
            "period": "2026-09",
            "cutoff": "2026-09-30",
            "null_policy": "Unknown and zero denominators unavailable",
            "direction": "lower",
            "evidence_refs": ["E"],
            "target_status": "proposed",
            "target": "2",
        },
    )


def observation(state: dict, identifier: str = "KO1") -> dict:
    return {
        "id": identifier,
        "kpi_id": "K1",
        "contract_sha256": digest(state["kpis"]["K1"]),
        "period": "2026-09",
        "population": "Invoices issued in month",
        "coverage": "Synthetic full set",
        "available_at": AT,
        "review_status": "reviewed",
        "evidence_refs": ["E"],
        "numerator": "4",
        "denominator": "20",
    }


def test_strategy_observation_does_not_change_evidence_score_or_approve_target() -> (
    None
):
    state = strategy_case()
    result = event(state, "kpi_observation", observation(state))
    assert result["kpi_observations"]["KO1"]["result"]["value"] == "20"
    assert result["kpi_observations"]["KO1"]["target_status"] == "proposed"
    assert evaluate(result) == evaluate(state)
    assert result["strategy_links"]["L1"]["status"] == "to_test"


def test_kpi_correction_appends_and_population_change_requires_new_series() -> None:
    state = strategy_case()
    state = event(state, "kpi_observation", observation(state))
    change = copy.deepcopy(state["kpis"]["K1"])
    change["population"] = "A different invoice population"
    with pytest.raises(ValueError, match="new series"):
        event(state, "kpi", change)
    change["formula_version"] = "v2"
    result = event(state, "kpi", change)
    assert result["kpi_observations"]["KO1"]["contract"]["formula_version"] == "v1"
    assert result["kpis"]["K1"]["formula_version"] == "v2"


def test_strategy_review_records_hypotheses_and_manual_chapter(tmp_path: Path) -> None:
    state = strategy_case()
    state = event(state, "kpi_observation", observation(state))
    state = event(
        state,
        "strategy_review",
        {
            "id": "SR1",
            "observation_ids": ["KO1"],
            "explanations": "Observed disputes",
            "hypotheses": "Cause still unverified",
            "decision": "Investigate delivery documentation",
            "next_review": "Next month",
            "action_ids": [],
            "statement": "Synthetic decision",
            "evidence_refs": ["E"],
        },
    )
    state = designed(state)
    state = event(
        state,
        "manual_compile",
        {
            "id": "M1",
            "control_ids": ["P1"],
            "introduction": "Synthetic strategy manual",
            "limitations": "Pilot only",
        },
    )
    output = export_manual(state, "M1", tmp_path)
    assert (
        "Come controlliamo la realizzazione degli obiettivi"
        in (output / "manuale.md").read_text()
    )
    assert "Ipotesi gestionale (to_test)" in (output / "manuale.md").read_text()


@pytest.fixture
def real_plan(monkeypatch) -> tuple[dict, dict]:
    monkeypatch.syspath_prepend(str(ROOT / "plugins/business-planning/scripts"))
    monkeypatch.syspath_prepend(str(ROOT / "plugins/_shared/vendor/modules"))
    from planning_workflow import build_plan

    source = ROOT / "tests/fixtures/business_planning"
    data = json.loads((source / "case.json").read_text())
    plan = build_plan(data, source_root=source)
    binding = {
        "case_id": data["case_id"],
        "cycle": data["cycle"],
        "scenario_id": "base",
        "currency": data["reporting_currency"],
        "periods": data["periods"],
        "review_status": "reviewed",
        "reviewer": "Synthetic professional",
        "review_statement": "Accepted for synthetic mapping",
        "limitations": "Monthly cash only",
    }
    return plan, binding


def mapping(plan: dict) -> dict:
    return {
        "plan_sha256": plan["content_sha256"],
        "scenario": "Budget",
        "reviewer": "Synthetic professional",
        "decision": "Freeze reviewed base scenario as budget",
        "mapping_version": "v1",
        "rows": [
            {
                "calculation_id": "base/2027-01/ebitda",
                "account_id": "EBITDA",
                "category": "ebitda",
                "sign": 1,
            }
        ],
        "control_totals": {"2027-01/ebitda": "-100"},
    }


def test_real_business_plan_v3_maps_exact_reviewed_calculations(real_plan) -> None:
    plan, binding = real_plan
    output = budget_rows(plan, binding, mapping(plan))
    assert output[0]["amount"] == "-100"
    assert output[0]["calculation_id"] == "base/2027-01/ebitda"
    assert output[0]["scenario"] == "Budget"


def test_cli_budget_persists_reviewed_mapping_and_csv_in_bound_run(
    vera_workflow_workspace, real_plan
) -> None:
    from assetti_construction import main

    plan, binding = real_plan
    workspace = vera_workflow_workspace(
        "adeguati-assetti", input_files={"plan.json": json.dumps(plan)}
    )
    base = ["--client-engagement", str(workspace["context_path"])]
    main(
        [
            *base,
            "open",
            "--case-id",
            "construction",
            "--entity-name",
            "Synthetic",
            "--actor",
            "Tester",
        ]
    )
    source = workspace["input_paths"][0]
    source_hash = hashlib.sha256(source.read_bytes()).hexdigest()
    evidence = {
        "id": "PLAN",
        "source_id": "import",
        "path": source.relative_to(
            Path(workspace["context"]["run_root"]) / "inputs"
        ).as_posix(),
        "sha256": source_hash,
        "locator": "complete JSON",
        "evidence_class": "document",
        "limitations": "Synthetic",
        "criterion_ids": [],
        "event_date": None,
        "acquired_at": AT,
        "period": None,
        "author": None,
    }
    artifact = {
        **binding,
        "id": "BP",
        "workflow_id": "business-planning",
        "module_version": "v3",
        "run_id": "synthetic-plan",
        "artifact_id": "plan",
        "source_id": "PLAN",
        "sha256": source_hash,
        "client_id": workspace["context"]["client_id"],
        "engagement_id": workspace["context"]["engagement_id"],
        "scope": "Synthetic scenario",
        "adapter_status": "native_contract_verified",
        "document": plan,
    }
    for revision, (kind, payload) in enumerate(
        [("evidence", evidence), ("artifact", artifact)]
    ):
        path = workspace["output_dir"] / f"{kind}.json"
        path.write_text(
            json.dumps(
                {
                    "request_id": kind,
                    "expected_revision": revision,
                    "actor": "Tester",
                    "at": AT,
                    "event": {"kind": kind, "payload": payload},
                }
            )
        )
        main([*base, "apply", "--event", str(path)])
    request = workspace["output_dir"] / "mapping.json"
    request.write_text(json.dumps(mapping(plan)))

    result = main([*base, "budget", "--artifact-id", "BP", "--mapping", str(request)])

    assert result == 0
    saved = json.loads(next(workspace["output_dir"].glob("budget-*.json")).read_text())
    assert saved["mapping"] == mapping(plan)
    assert saved["rows"][0]["amount"] == "-100"
    assert (
        "base/2027-01/ebitda"
        in next(workspace["output_dir"].glob("budget-*.csv")).read_text()
    )


@pytest.mark.parametrize(
    "field,bad",
    [
        ("case_id", "other"),
        ("scenario_id", "missing"),
        ("currency", "CHF"),
        ("periods", ["2020-01"]),
        ("cycle", {}),
        ("review_status", "draft"),
    ],
)
def test_plan_adapter_rejects_wrong_scope_or_unreviewed_binding(
    real_plan, field, bad
) -> None:
    plan, binding = real_plan
    binding[field] = bad
    with pytest.raises(ValueError):
        validate_plan_binding(plan, binding)


def test_plan_budget_mapping_rejects_unreconciled_totals(real_plan) -> None:
    plan, binding = real_plan
    request = mapping(plan)
    request["control_totals"]["2027-01/ebitda"] = "100"
    with pytest.raises(ValueError, match="does not reconcile"):
        budget_rows(plan, binding, request)


def test_artifact_binding_rejects_another_client_before_consuming_report() -> None:
    state = case()
    payload = {
        "id": "ART1",
        "workflow_id": "treasury-forecast",
        "module_version": "v1",
        "run_id": "run-1",
        "artifact_id": "forecast-1",
        "source_id": "E",
        "sha256": state["evidence"]["E"]["sha256"],
        "client_id": "other",
        "engagement_id": "eng-a",
        "scope": "Selected accounts",
        "periods": ["2026-09"],
        "currency": "EUR",
        "review_status": "reviewed",
        "reviewer": "Synthetic reviewer",
        "review_statement": "Reviewed",
        "limitations": "13 weeks only; no twelve-month assertion",
        "adapter_status": "reviewed_external",
    }
    with pytest.raises(ValueError, match="another client"):
        event(state, "artifact", payload)


def test_completed_document_action_does_not_imply_operating_control() -> None:
    state = designed(case())
    state = event(
        state,
        "finding",
        {
            "id": "F1",
            "criterion_ids": ["C0"],
            "evidence_refs": ["E"],
            "observation": "Late report",
            "interpretation": "Decision lacked information",
            "consequence": "Review delayed",
            "alternatives": "Verbal update may exist",
            "priority_reason": "Next meeting",
        },
    )
    result = event(
        state,
        "action",
        {
            "id": "A1",
            "control_id": "P1",
            "finding_ids": ["F1"],
            "proposal": "Draft reporting procedure",
            "owner": "Administration",
            "owner_status": "proposed",
            "timing": "To agree",
            "timing_status": "proposed",
            "priority_reason": "Before next meeting",
            "completion_criterion": "Draft ready",
            "completion_kind": "document",
            "status": "completed",
            "disposition": "Document prepared",
            "residual_risk": "Operation unverified",
            "disposition_evidence": ["E"],
        },
    )
    assert result["actions"]["A1"]["status"] == "completed"
    assert result["executions"] == {}
    assert evaluate(result)["rows"][0]["base"] is None


def test_cli_apply_and_resume_validate_real_archive_receipts(
    vera_workflow_workspace,
) -> None:
    from assetti_construction import main

    first = vera_workflow_workspace(
        "adeguati-assetti",
        engagement_id="construction-case",
        input_files={"evidence.txt": "Synthetic evidence"},
    )
    base = ["--client-engagement", str(first["context_path"])]
    main(
        [
            *base,
            "open",
            "--case-id",
            "synthetic",
            "--entity-name",
            "Synthetic company",
            "--actor",
            "Tester",
        ]
    )
    source = first["input_paths"][0]
    relative = source.relative_to(
        Path(first["context"]["run_root"]) / "inputs"
    ).as_posix()
    envelope = {
        "request_id": "add-evidence",
        "expected_revision": 0,
        "actor": "Tester",
        "at": AT,
        "event": {
            "kind": "evidence",
            "payload": {
                "id": "E",
                "source_id": "source",
                "path": relative,
                "sha256": hashlib.sha256(source.read_bytes()).hexdigest(),
                "locator": "paragraph 1",
                "evidence_class": "document",
                "limitations": "Synthetic",
                "criterion_ids": ["C01"],
                "event_date": None,
                "acquired_at": AT,
                "period": None,
                "author": None,
            },
        },
    }
    event_file = first["output_dir"] / "event.json"
    event_file.write_text(json.dumps(envelope))
    assert main([*base, "apply", "--event", str(event_file)]) == 0
    assert main([*base, "status"]) == 0
    assert main([*base, "form"]) == 0
    # This fixture imports only finalized artifacts on the upstream branch.
    # Carry the exact original bytes as an explicitly declared companion artifact.
    (first["output_dir"] / "original-evidence.txt").write_bytes(source.read_bytes())
    second = vera_workflow_workspace(
        "adeguati-assetti",
        engagement_id="construction-case",
        upstream_workspace=first,
        input_files={"evidence.txt": "Synthetic evidence"},
    )
    snapshots = [
        p
        for p in second["input_paths"]
        if p.suffix == ".json"
        and json.loads(p.read_text()).get("schema_version")
        == "vera.assetti_construction.v1"
    ]
    snapshot = max(snapshots, key=lambda p: json.loads(p.read_text())["revision"])
    assert (
        main(
            [
                "--client-engagement",
                str(second["context_path"]),
                "resume",
                "--snapshot",
                str(snapshot),
            ]
        )
        == 0
    )
    saved = next(second["output_dir"].glob("assetti-construction-*.json"))
    assert (
        json.loads(saved.read_text())["evidence"]["E"]["sha256"]
        == hashlib.sha256(b"Synthetic evidence").hexdigest()
    )
