"""Execute construction from shipped fictional inputs; never simulate a learner.

Explicit synthetic decision evidence is manufactured only inside this test's
local archive. It is never distributed as an approval or professional pilot.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from tests.plugins.test_teaching_kit_execution import (
    ROOT,
    _bound_case,
    _complete_teaching_case,
)

__all__ = ["execute_construction", "execute_financial_lab"]

AT = "2026-03-31T12:00:00+00:00"

WORDS = {
    "it": [
        "Chiusura mensile",
        "Consegne tardive",
        "Sostituto da concordare",
        "Controllare completezza",
        "Inviare allo studio",
        "Rivedere report e anomalie",
        "Periodo",
        "Data invio",
        "Preparatore",
        "Report",
        "Decisione",
        "Prova di chiusura",
    ],
    "en": [
        "Monthly close",
        "Late deliveries",
        "Substitute to agree",
        "Check completeness",
        "Send to the accountant",
        "Review report and exceptions",
        "Period",
        "Dispatch date",
        "Preparer",
        "Report",
        "Decision",
        "Closure evidence",
    ],
    "fr": [
        "Clôture mensuelle",
        "Livraisons tardives",
        "Remplaçant à convenir",
        "Vérifier la complétude",
        "Envoyer au comptable",
        "Revoir rapport et anomalies",
        "Période",
        "Date d’envoi",
        "Préparateur",
        "Rapport",
        "Décision",
        "Preuve de résolution",
    ],
    "de": [
        "Monatsabschluss",
        "Verspätete Lieferung",
        "Vertretung zu vereinbaren",
        "Vollständigkeit prüfen",
        "An Kanzlei senden",
        "Bericht und Anomalien prüfen",
        "Zeitraum",
        "Versanddatum",
        "Ersteller",
        "Bericht",
        "Entscheidung",
        "Abschlussbeleg",
    ],
    "es": [
        "Cierre mensual",
        "Entregas tardías",
        "Sustituto por acordar",
        "Comprobar integridad",
        "Enviar al asesor",
        "Revisar informe y anomalías",
        "Período",
        "Fecha de envío",
        "Preparador",
        "Informe",
        "Decisión",
        "Prueba de resolución",
    ],
}


def execute_construction(
    tmp_path: Path, monkeypatch, language: str, phase: str
) -> tuple[dict, Path]:
    """Run the native CLI and persist resume, manual, and operating boundaries."""
    from docx import Document
    from pypdf import PdfReader

    scripts = ROOT / "plugins/adeguati-assetti/scripts"
    monkeypatch.syspath_prepend(str(scripts))
    from assetti_construction import main
    from construction_core import assessment_basis, digest, evaluate, manual_status
    from construction_intake import parse_markdown, render_markdown
    from construction_store import CaseStore

    run = _bound_case(
        tmp_path,
        monkeypatch,
        "adeguati-assetti",
        "adeguati-assetti",
        "demo",
        language=language,
    )
    w = WORDS[language]
    facts = json.loads(
        (tmp_path / "kit/files/input/construction-facts.json").read_text()
    )
    assert facts["fictional"] and not facts["professional_approval"]
    assert not facts["company_adoption"]
    assert facts["unverified_collection"] is None
    guide = (tmp_path / f"kit/files/input/construction-{language}.md").read_text()
    assert "BASE-1" in guide and "0/1/2/3/4" in guide

    def store():
        return CaseStore(
            Path(run["output_dir"]) / "assetti-construction.sqlite3",
            client_id=run["context"]["client_id"],
            engagement_id=run["context"]["engagement_id"],
        )

    def cli(*args):
        assert main(["--client-engagement", run["context_path"], *map(str, args)]) == 0

    def apply(kind, payload):
        state = store().read()
        envelope = Path(run["output_dir"]) / "event.json"
        envelope.write_text(
            json.dumps(
                {
                    "request_id": f"teaching-{state['revision']}-{kind}",
                    "expected_revision": state["revision"],
                    "actor": "Synthetic automated test operator",
                    "at": AT,
                    "event": {"kind": kind, "payload": payload},
                },
                ensure_ascii=False,
            )
        )
        cli("apply", "--event", envelope)
        return store().read()

    def evidence(identifier, path, criteria, classification="document"):
        return apply(
            "evidence",
            {
                "id": identifier,
                "source_id": identifier,
                "path": path.relative_to(
                    Path(run["context"]["run_root"]) / "inputs"
                ).as_posix(),
                "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
                "locator": "Complete fictional source",
                "evidence_class": classification,
                "limitations": "Fictional teaching input; no real-company proof",
                "criterion_ids": criteria,
                "event_date": facts["as_of"],
                "acquired_at": AT,
                "period": "2026-02",
                "author": None,
            },
        )

    def next_run(extra):
        nonlocal run
        ledger = _complete_teaching_case(run, tmp_path / "case")
        context = run["context"]
        originals = [Path(x["path"]) for x in context["input_bindings"]]
        imports = [
            ledger.import_document(
                tmp_path / "case",
                context["client_id"],
                context["engagement_id"],
                path,
                "source",
            )
            for path in [*originals, *extra]
        ]
        prepared = ledger.prepare_run(
            tmp_path / "case",
            context["client_id"],
            context["engagement_id"],
            "adeguati-assetti",
            context["workflow_version"],
            input_ids=list(dict.fromkeys(x["receipt"]["input_id"] for x in imports)),
        )
        run = ledger.start_run(
            tmp_path / "case", context["engagement_id"], prepared["run"]["run_id"]
        )
        return {
            Path(x["path"]).name: Path(x["path"])
            for x in run["context"]["input_bindings"]
        }

    cli(
        "open",
        "--case-id",
        "officina-arco-teaching",
        "--entity-name",
        facts["entity"] + " — fictional",
        "--actor",
        "Synthetic automated test operator",
    )
    apply(
        "scope",
        {
            "description": w[0],
            "proportionality": "Twelve staff, one site; one scoped control",
            "limitations": "Fictional company; other processes unassessed",
        },
    )
    paths = {
        Path(x["path"]).name: Path(x["path"]) for x in run["context"]["input_bindings"]
    }
    evidence("FEB", paths[f"operation-{language}.md"], ["C09"], "execution")
    apply("cursor", {"summary": w[0], "next_step": w[2]})
    questions = Path(run["output_dir"]) / "questions.json"
    questions.write_text(
        json.dumps(
            [
                {"id": "SUBSTITUTE", "question": w[2] + "?", "criterion_ids": ["C02"]},
                {"id": "PAYMENT", "question": w[11] + "?", "criterion_ids": ["C09"]},
            ],
            ensure_ascii=False,
        )
    )
    cli("form", "--questions", questions)
    form = next(Path(run["output_dir"]).glob("visita-*.html"))
    html = form.read_text()
    assert "connect-src 'none'" in html and "localStorage" not in html
    config = json.loads(
        html.split('id="configuration">', 1)[1].split("</script>", 1)[0]
    )
    intake = {
        **{
            key: config[key]
            for key in (
                "schema_version",
                "practice_id",
                "client_id",
                "engagement_id",
                "questionnaire_version",
            )
        },
        "session_id": "synthetic-intake",
        "revision": 1,
        "parent_sha256": None,
        "mode": "html",
        "position": 0,
        "answers": [
            {
                "question_id": q["id"],
                "question": q["question"],
                "criterion_ids": q["criterion_ids"],
                "original": "",
                "status": "unknown",
                "notes": "",
                "attachment_refs": [],
            }
            for q in config["questions"]
        ],
    }
    # This is a manufactured export for a mechanical round-trip, not learner input.
    intake["declared_author"] = "Synthetic test fixture"
    intake["date"] = facts["interview_date"]
    intake["answers"][0].update(
        original=w[2], status="to_verify", attachment_refs=[facts["missing_attachment"]]
    )
    intake["answers"][1].update(original="", status="unknown")
    returned = tmp_path / "returned-interview.md"
    returned.write_text(render_markdown(intake))
    assert parse_markdown(returned.read_text())["answers"][1]["status"] == "unknown"
    initial = store().read()
    snapshot = (
        Path(run["output_dir"])
        / f"assetti-construction-{initial['snapshot_sha256']}.json"
    )
    retained_bytes = snapshot.read_bytes()
    # Synthetic decisions are test-only original evidence, never kit inputs.
    decisions = tmp_path / "synthetic-decisions.txt"
    decisions.write_text(
        "AUTOMATED SYNTHETIC FIXTURE ONLY. Qualification and reasoned adjustment explicitly recorded for testing. Manual M1 reviewed and adopted for a simulated cycle only. No real professional, learner, authenticated signature or company approval.\n"
    )
    paths = next_run([snapshot, returned, decisions])
    cli("resume", "--snapshot", paths[snapshot.name])
    assert store().read()["cursor"]["next_step"] == w[2]
    evidence("INTERVIEW", paths[returned.name], ["C02", "C09"], "statement")
    state = apply(
        "intake_import",
        {"source_id": "INTERVIEW", "content": paths[returned.name].read_text()},
    )
    assert any(
        x["original"] == w[2]
        and x["unresolved_attachment_refs"] == [facts["missing_attachment"]]
        for x in state["answers"].values()
    )
    evidence("TEST-DECISION", paths[decisions.name], [], "decision")
    apply(
        "assessment",
        {
            "id": "C09",
            "rationale": w[0],
            "adequacy_judgment": "One dated cycle, continuity unknown",
            "applicability": "applicable",
            "evidence_stage": "partial",
            "claimed_level": 3,
            "target_score": 3,
            "material_contradiction": False,
            "evidence_refs": ["FEB"],
        },
    )
    state = store().read()
    assert next(x for x in evaluate(state)["rows"] if x["id"] == "C09")["base"] is None
    state = apply(
        "qualification_review",
        {
            "criterion_id": "C09",
            "basis_sha256": assessment_basis(state, "C09"),
            "statement": "Explicit test-only qualification, not professional acceptance",
            "evidence_refs": ["TEST-DECISION"],
        },
    )
    apply(
        "score_decision",
        {
            "id": "D1",
            "criterion_id": "C09",
            "status": "recorded",
            "basis_sha256": assessment_basis(state, "C09"),
            "before_score": 1,
            "after_score": 2,
            "reason_code": "proportionality",
            "rationale": "Test-only proposal of compensating director review",
            "alternative_considered": "Wait for more operating cycles",
            "residual_risk": "One cycle, substitute unknown",
            "action_impact": "Keep action open",
            "review_trigger": "Next cycle or evidence",
            "statement": "Explicit automated synthetic decision; no learner decision",
            "evidence_refs": ["TEST-DECISION", "FEB"],
        },
    )
    apply(
        "finding",
        {
            "id": "F1",
            "criterion_ids": ["C02", "C09"],
            "evidence_refs": ["INTERVIEW", "FEB"],
            "observation": w[2],
            "interpretation": w[1],
            "consequence": w[1],
            "alternatives": "Partial invoice collection may continue",
            "priority_reason": "Monthly decision timeliness",
        },
    )
    control = {
        "id": "P1",
        "criterion_ids": ["C02", "C09"],
        "finding_ids": ["F1"],
        "title": w[0],
        "risk": w[1],
        "outcome": w[5],
        "owner": "Sara",
        "decision_owner": "Elena",
        "substitute": w[2],
        "role_status": "proposed",
        "inputs": f"procedure-{language}.md",
        "steps": w[3:6],
        "outputs": w[9] + " → Elena",
        "frequency": "Monthly / mensile",
        "timing_status": "proposed",
        "exceptions": w[1],
        "response_time": "To agree / da concordare",
        "archive": "Same engagement / stesso dossier",
        "execution_evidence": w[11],
        "register_fields": w[6:],
    }
    apply("control", control)
    apply(
        "action",
        {
            "id": "A1",
            "control_id": "P1",
            "finding_ids": ["F1"],
            "proposal": w[2],
            "owner": "Elena",
            "owner_status": "proposed",
            "timing": "To agree",
            "timing_status": "proposed",
            "priority_reason": w[1],
            "completion_criterion": w[11],
            "completion_kind": "operation",
            "status": "proposed",
        },
    )
    state = apply(
        "manual_compile",
        {
            "id": "M1",
            "control_ids": ["P1"],
            "introduction": w[0] + " — fictional teaching case",
            "limitations": "One process; synthetic validation, not a real-company pilot",
        },
    )
    before = evaluate(state)
    cli("manual", "--manual-id", "M1")
    folder = next(Path(run["output_dir"]).glob("manuale-*"))
    assert manual_status(state, "M1") == "draft"
    assert state["adoptions"] == {} and state["executions"] == {}
    assert w[0] in "\n".join(
        p.text for p in Document(folder / "manuale.docx").paragraphs
    )
    assert w[0] in "\n".join(
        p.extract_text() for p in PdfReader(folder / "manuale.pdf").pages
    )
    assert w[6] in (folder / "registro-01.csv").read_text(encoding="utf-8-sig")
    assert w[0] in (folder / "manuale.md").read_text()
    state = apply(
        "manual_review",
        {
            "manual_id": "M1",
            "manual_sha256": state["manuals"]["M1"]["manual_sha256"],
            "statement": "Explicit synthetic review for automated check only",
            "evidence_refs": ["TEST-DECISION"],
            "finding_dispositions": {
                "F1": "Control proposed; operating action remains open"
            },
        },
    )
    assert (
        manual_status(state, "M1") == "professionally_reviewed"
        and not state["adoptions"]
    )
    state = apply(
        "adoption",
        {
            "id": "AD1",
            "manual_id": "M1",
            "manual_sha256": state["manuals"]["M1"]["manual_sha256"],
            "competent_person": "Synthetic fixture actor",
            "decision": "Test-only simulated adoption",
            "effective_date": "2026-03-31",
            "reservations": "Simulation only",
            "statement": "Explicit synthetic fixture, no company approval",
            "evidence_refs": ["TEST-DECISION"],
        },
    )
    assert manual_status(state, "M1") == "adopted"
    state = apply(
        "execution",
        {
            "id": "X1",
            "control_id": "P1",
            "manual_id": "M1",
            "control_sha256": digest(state["controls"]["P1"]),
            "period": "2026-03",
            "cycle": "simulation-1",
            "executor": "Synthetic fixture",
            "exceptions": w[2],
            "recipient": "Elena",
            "decision": "Investigate",
            "closure": "Unresolved",
            "kind": "simulation",
            "evidence_refs": ["FEB", "TEST-DECISION"],
        },
    )
    state = apply(
        "operation_review",
        {
            "id": "R1",
            "execution_ids": ["X1"],
            "scope": w[0],
            "sample": "One simulated cycle",
            "conclusion": "Design only; no operating effectiveness",
            "limitations": "No company-wide or real-company conclusion",
            "next_review": "Next cycle",
            "outcome": "design_only",
            "action_dispositions": {"A1": "Open; no real operating evidence"},
            "statement": "Explicit synthetic fixture review",
            "evidence_refs": ["TEST-DECISION"],
        },
    )
    assert not state["operation_reviews"]["R1"]["sample_contains_real_executions_only"]
    assert state["actions"]["A1"]["status"] == "proposed"
    assert evaluate(state)["base"] == before["base"]
    apply(
        "objective",
        {
            "id": "O1",
            "description": w[5],
            "perspective": "process",
            "owner": "Elena",
            "owner_status": "proposed",
            "scope": w[0],
            "period": "2026-02",
            "evidence_refs": ["FEB"],
        },
    )
    kpi = {
        "id": "K1",
        "objective_id": "O1",
        "definition": "Timely delivery / punctualité / puntualità",
        "formula": "timely cycles / observed cycles * 100",
        "formula_version": "1",
        "operation": "percent",
        "unit": "%",
        "population": facts["population"],
        "data_owner": "Sara",
        "frequency": "Monthly",
        "period": "2026-02",
        "cutoff": "2026-03-31",
        "null_policy": "Missing numerator or zero denominator: no value",
        "direction": "higher",
        "evidence_refs": ["FEB"],
        "target_status": "proposed",
    }
    state = apply("kpi", kpi)
    observation = {
        "id": "OBS1",
        "kpi_id": "K1",
        "contract_sha256": digest(state["kpis"]["K1"]),
        "period": "2026-02",
        "population": facts["population"],
        "coverage": "One fictional cycle only",
        "available_at": "2026-03-31",
        "review_status": "draft",
        "evidence_refs": ["FEB"],
        "numerator": facts["timely_cycles"],
        "denominator": facts["observed_cycles"],
    }
    state = apply("kpi_observation", observation)
    assert state["kpi_observations"]["OBS1"]["result"]["value"] == "100"
    state = apply(
        "kpi_observation",
        {
            **observation,
            "id": "OBS-MISSING",
            "numerator": None,
            "missing_reason": "Collection not supplied",
        },
    )
    assert state["kpi_observations"]["OBS-MISSING"]["result"]["value"] is None
    state = apply(
        "kpi_observation",
        {
            **observation,
            "id": "OBS-ZERO",
            "denominator": "0",
            "missing_reason": "No observed population",
        },
    )
    assert state["kpi_observations"]["OBS-ZERO"]["result"]["value"] is None
    if phase == "practice":
        state = store().read()
        previous = (
            Path(run["output_dir"])
            / f"assetti-construction-{state['snapshot_sha256']}.json"
        )
        previous_bytes = previous.read_bytes()
        practice_paths = list((tmp_path / "kit/files/practice").glob("*"))
        paths = next_run([previous, *practice_paths])
        cli("resume", "--snapshot", paths[previous.name])
        state = evidence(
            "APRIL", paths[f"update-{language}.md"], ["C02", "C09"], "execution"
        )
        row = next(x for x in evaluate(state)["rows"] if x["id"] == "C09")
        assert row["base"] is None and row["decision_status"] == "stale"
        apply(
            "control",
            {**control, "substitute": "Paolo — proposed limited access; not accepted"},
        )
        assert manual_status(store().read(), "M1") == "needs_review"
        state = apply(
            "manual_compile",
            {
                "id": "M2",
                "control_ids": ["P1"],
                "introduction": w[0] + " — revised draft",
                "limitations": "Review and any new adoption pending",
            },
        )
        assert manual_status(state, "M2") == "draft"
        assert previous.read_bytes() == previous_bytes
        cli("manual", "--manual-id", "M2")
        old_observation = digest(state["kpi_observations"]["OBS1"])
        apply(
            "kpi",
            {
                **kpi,
                "formula": "timely documents / observed documents * 100",
                "formula_version": "2",
                "population": "documents",
            },
        )
        state = store().read()
        state = apply(
            "kpi_observation",
            {
                **observation,
                "id": "OBS2",
                "contract_sha256": digest(state["kpis"]["K1"]),
                "population": "documents",
                "numerator": None,
                "missing_reason": "Document sample not supplied",
            },
        )
        assert digest(state["kpi_observations"]["OBS1"]) == old_observation
        assert state["kpi_observations"]["OBS2"]["contract"]["formula_version"] == "2"
    assert snapshot.read_bytes() == retained_bytes
    cli("status")
    _complete_teaching_case(run, tmp_path / "case")
    return run, folder


def execute_financial_lab(tmp_path: Path, monkeypatch, language: str) -> Path:
    """Build real v3 plans from kit facts and export reviewed Budget/Forecast rows."""
    import copy

    import pytest

    monkeypatch.syspath_prepend(str(ROOT / "plugins/adeguati-assetti/scripts"))
    monkeypatch.syspath_prepend(str(ROOT / "plugins/business-planning/scripts"))
    from assetti_construction import main
    from construction_adapters import budget_rows
    from construction_core import digest
    from construction_store import CaseStore
    from planning_workflow import build_plan

    run = _bound_case(
        tmp_path,
        monkeypatch,
        "adeguati-assetti",
        "adeguati-assetti",
        "demo",
        language=language,
    )
    output = Path(run["output_dir"])
    inputs = Path(run["context"]["run_root"]) / "inputs"
    raw_path = next(
        Path(x["path"])
        for x in run["context"]["input_bindings"]
        if Path(x["path"]).name == "financial-facts.json"
    )
    raw = json.loads(raw_path.read_text())
    assert raw["fictional"] and not raw["approval_supplied"]
    # Reuse the v3 test authoring shape, not its old source bytes or financial values.
    case = json.loads((ROOT / "tests/fixtures/business_planning/case.json").read_text())
    case["case_id"] = "assetti-financial-teaching"
    case["entity_name"] = raw["entity"]
    case["financial"]["opening_balance"] = raw["opening_balance"]
    for row, facts in zip(
        case["financial"]["scenarios"][0]["schedule"], raw["base_schedule"], strict=True
    ):
        row.update(facts)
    for source in case["sources"]:
        source["path"] = raw_path.relative_to(inputs).as_posix()
        source["sha256"] = hashlib.sha256(raw_path.read_bytes()).hexdigest()
    case["sources"] = [case["sources"][0]]
    for row in [*case["evidence"], *case["assumptions"], *case["observations"]]:
        row["source_ids"] = ["client"]
    case["observations"] = []
    case["resolutions"] = []
    case["assessment"]["charts"] = [
        c
        for c in case["assessment"]["charts"]
        if c["chart_id"] != "reported-adjusted-base"
    ]
    plan = build_plan(case, source_root=inputs)
    assert plan["status"] == "ready_for_professional_review", plan["unresolved_matters"]
    binding = {
        "case_id": case["case_id"],
        "cycle": case["cycle"],
        "scenario_id": "base",
        "currency": raw["currency"],
        "periods": raw["periods"],
        "review_status": "reviewed",
        "reviewer": "Synthetic automated test reviewer",
        "review_statement": "Explicit test-only financial acceptance; not a professional pilot",
        "limitations": raw["limitations"],
    }
    mapping = {
        "plan_sha256": plan["content_sha256"],
        "scenario": "Budget",
        "reviewer": binding["reviewer"],
        "decision": "Synthetic test-only mapping review",
        "mapping_version": "1",
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
    with pytest.raises(ValueError, match="review"):
        budget_rows(plan, {**binding, "review_status": "draft"}, mapping)
    with pytest.raises(ValueError, match="partial|blocked"):
        budget_rows(
            {
                **plan,
                "status": "partial",
                "content_sha256": digest(
                    {
                        **{k: v for k, v in plan.items() if k != "content_sha256"},
                        "status": "partial",
                    }
                ),
            },
            binding,
            mapping,
        )
    with pytest.raises(ValueError, match="reconcile"):
        budget_rows(
            plan, binding, {**mapping, "control_totals": {"2027-01/ebitda": "0"}}
        )
    revised_case = copy.deepcopy(case)
    revised_case["financial"]["scenarios"][0]["schedule"][0]["operating_expenses"] = (
        raw["forecast_change"]["operating_expenses"]
    )
    # A new scenario with no silently replayed conflict-resolution decisions.
    revised_case = json.loads(json.dumps(revised_case).replace('"base', '"forecast'))
    revised_case["observations"] = []
    revised_case["resolutions"] = []
    forecast = build_plan(revised_case, source_root=inputs)
    assert forecast["status"] == "blocked"
    # Re-author the changed narrative against the new calculations, preserving the Budget.
    for item in revised_case["narrative"]:
        for claim in item["claims"].values():
            if "calculation_id" in claim:
                claim["value"] = forecast["calculations"][claim["calculation_id"]][
                    "value"
                ]
    for chart in revised_case["assessment"]["charts"]:
        chart["chart_id"] = chart["chart_id"].replace("-base", "-forecast")
    forecast = build_plan(revised_case, source_root=inputs)
    assert forecast["status"] == "ready_for_professional_review", forecast[
        "unresolved_matters"
    ]
    assert forecast["calculations"]["forecast/2027-01/ebitda"]["value"] == "-150"
    plans = []
    for name, document in [("budget-plan", plan), ("forecast-plan", forecast)]:
        path = output / f"{name}.json"
        path.write_text(json.dumps(document, ensure_ascii=False))
        plans.append(path)
    ledger = _complete_teaching_case(run, tmp_path / "case")
    context = run["context"]
    imports = [
        ledger.import_document(
            tmp_path / "case",
            context["client_id"],
            context["engagement_id"],
            path,
            "source",
        )
        for path in [raw_path, *plans]
    ]
    prepared = ledger.prepare_run(
        tmp_path / "case",
        context["client_id"],
        context["engagement_id"],
        "adeguati-assetti",
        context["workflow_version"],
        input_ids=list(dict.fromkeys(x["receipt"]["input_id"] for x in imports)),
    )
    run = ledger.start_run(
        tmp_path / "case", context["engagement_id"], prepared["run"]["run_id"]
    )
    output = Path(run["output_dir"])
    inputs = Path(run["context"]["run_root"]) / "inputs"
    base = ["--client-engagement", run["context_path"]]
    assert (
        main(
            [
                *base,
                "open",
                "--case-id",
                "financial-lab",
                "--entity-name",
                raw["entity"],
                "--actor",
                "Synthetic test reviewer",
            ]
        )
        == 0
    )

    def apply(kind, payload):
        state = CaseStore(
            output / "assetti-construction.sqlite3",
            client_id=context["client_id"],
            engagement_id=context["engagement_id"],
        ).read()
        path = output / "event.json"
        path.write_text(
            json.dumps(
                {
                    "request_id": f"finance-{state['revision']}",
                    "expected_revision": state["revision"],
                    "actor": "Synthetic test reviewer",
                    "at": AT,
                    "event": {"kind": kind, "payload": payload},
                }
            )
        )
        assert main([*base, "apply", "--event", str(path)]) == 0

    first_bytes = None
    for name, doc, scenario, version in [
        ("budget-plan", plan, "Budget", "1"),
        ("forecast-plan", forecast, "Forecast", "2"),
    ]:
        source = next(
            Path(x["path"])
            for x in run["context"]["input_bindings"]
            if Path(x["path"]).name == name + ".json"
        )
        sha = hashlib.sha256(source.read_bytes()).hexdigest()
        apply(
            "evidence",
            {
                "id": name,
                "source_id": name,
                "path": source.relative_to(inputs).as_posix(),
                "sha256": sha,
                "locator": "Complete v3 plan",
                "evidence_class": "document",
                "limitations": raw["limitations"],
                "criterion_ids": [],
                "event_date": None,
                "acquired_at": AT,
                "period": None,
                "author": "Synthetic test",
            },
        )
        selected = {
            **binding,
            "scenario_id": "base" if scenario == "Budget" else "forecast",
        }
        apply(
            "artifact",
            {
                **selected,
                "id": name,
                "workflow_id": "business-planning",
                "module_version": "v3",
                "run_id": name,
                "artifact_id": name,
                "source_id": name,
                "sha256": sha,
                "client_id": context["client_id"],
                "engagement_id": context["engagement_id"],
                "scope": raw["limitations"],
                "adapter_status": "native_contract_verified",
                "document": doc,
            },
        )
        request = copy.deepcopy(mapping)
        request.update(
            plan_sha256=doc["content_sha256"],
            scenario=scenario,
            mapping_version=version,
        )
        if scenario == "Forecast":
            request["rows"][0]["calculation_id"] = "forecast/2027-01/ebitda"
            request["control_totals"] = {"2027-01/ebitda": "-150"}
        path = output / f"mapping-{version}.json"
        path.write_text(json.dumps(request))
        assert (
            main([*base, "budget", "--artifact-id", name, "--mapping", str(path)]) == 0
        )
        if scenario == "Budget":
            first = next(output.glob("budget-*.csv"))
            first_bytes = first.read_bytes()
        else:
            assert first.read_bytes() == first_bytes
    rows = [json.loads(p.read_text())["rows"][0] for p in output.glob("budget-*.json")]
    assert {(r["scenario"], r["amount"]) for r in rows} == {
        ("Budget", "-100"),
        ("Forecast", "-150"),
    }
    _complete_teaching_case(run, tmp_path / "case")
    return output
