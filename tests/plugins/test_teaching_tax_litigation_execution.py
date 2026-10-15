"""Run the authored tax lesson through real evidence and resumable case helpers.

Narrative, stage selection and review choices are explicit regression fixtures.
These checks do not perform legal research, certify deadlines, run Word or prove
learner participation. Live lessons execute the selected product's full method.
"""

from __future__ import annotations

import hashlib
import importlib.util
import json
from pathlib import Path

import pytest

from tests.plugins._teaching_release import prepared_kit, record_native_check
from tests.plugins.test_teaching_kit_execution import (
    _bound_case,
    _complete_teaching_case,
    _read,
    _run,
    _write,
)

__all__ = [
    "test_tax_course_preserves_evidence_unknown_terms_and_prior_run",
    "test_withdrawn_tax_course_is_absent_from_release_catalogue",
]

ROOT = Path(__file__).resolve().parents[2]
WORKFLOW = "contenzioso-tributario"
# Both product adapters use these same canonical helpers, bundled in each host.
HELPERS = "plugins/lucia/scripts/"
LANGUAGES = ["it", "en", "fr", "de", "es"]


def _execute(run, product, language, phase, case):
    output = Path(run["output_dir"])
    inputs = sorted((Path(run["context"]["run_root"]) / "inputs").rglob("*"))
    files = [
        path
        for path in inputs
        if path.is_file()
        and path.suffix in {".txt", ".md"}
        and "upstream" not in path.parts
    ]
    matter = output / "tax-matter"
    args = ["prepare", "--run-dir", matter, "--workflow", "revisione-documentale"]
    for path in files:
        args.extend(["--file", path])
    _run(HELPERS + "legal_documents.py", *args, "--topic", "Case evidence")
    pack = _read(matter / "evidence.json")
    review = _read(matter / "review.json")
    review["context"].update(
        represented_party="Officina Cedro S.r.l. — caso fittizio",
        jurisdiction="Italia; primo grado; nessuna norma attestata dal test",
        relationship="Solo prova tecnica didattica, nessun mandato professionale",
        formation="Avviso IRES 2024 e ricevute fittizie",
        forum="Competenza da verificare nella lavorazione professionale",
        legal_basis="Fonti attuali da acquisire nel percorso nativo di ricerca",
        firm_instructions="Nessun modello Word fornito",
        instructions="Inventariare prove e mantenere visibili le lacune",
        language=language,
    )
    for source in pack["sources"]:
        review["coverage"][source["id"]]["reviewed_anchors"] = [
            unit["anchor"] for unit in source["units"]
        ]
    for item in review["items"]:
        source = next(s for s in pack["sources"] if s["id"] == item["source_id"])
        unit = source["units"][0]
        item.update(
            status="supported",
            summary=unit["text"],
            reasoning="Inventario testuale di input fittizi; nessuna conclusione giuridica.",
            proposal="Verificare originali e regole attuali prima di confermare i termini.",
            citations=[{"source_id": source["id"], **unit, "quote": unit["text"]}],
        )
        item["citations"][0].pop("text")
    _write(matter / "review.json", review)
    _run(
        HELPERS + "legal_documents.py",
        "render",
        "--run-dir",
        matter,
        "--review",
        matter / "review.json",
        "--product",
        product.title(),
    )
    _run(
        HELPERS + "legal_matter.py",
        "init",
        "--run-dir",
        matter,
        "--kind",
        WORKFLOW,
        "--purpose",
        "Officina Cedro — esercitazione tributaria",
    )
    state = _read(matter / "matter.json")
    state["language"] = language
    draft = matter / "bozza-intake.md"
    draft.write_text(
        "# Bozza di lavoro didattica — primo grado italiano\n\n"
        "Officina Cedro S.r.l.; avviso AVV-DEMO-24 del 28 settembre 2026.\n"
        "Periodo 2024; IRES dichiarata EUR 2.880; costi contestati EUR 12.000.\n"
        "Fatti dichiarati nell’avviso, senza accertamento della fondatezza.\n"
        "Fatture, contratto e prestazioni ancora da documentare.\n"
        + (
            "Consegna dichiarata: 2 ottobre 2026 alle 09:14.\n"
            if phase == "practice"
            else "Manca prova di avvenuta consegna.\n"
        )
        + "Disciplina, transizioni, competenza, termini e motivi da ricercare e rivedere.\n"
        "Nessun precedente, scadenza finale, firma, notifica o deposito attestati.\n",
        encoding="utf-8",
    )
    state["stages"] = [
        {
            "id": "evidence",
            "label": "Organizzare prove e prima bozza",
            "status": "done",
            "note": "Output tecnico fittizio; ricerca giuridica ancora da eseguire",
            "outputs": ["review.html", "bozza-intake.md"],
        },
        {
            "id": "delivery",
            "label": "Acquisire prova della consegna",
            "status": "done" if phase == "practice" else "pending",
            "note": (
                "Ricevuta fittizia aggiunta"
                if phase == "practice"
                else "Ricevuta mancante"
            ),
            "outputs": ["review.html"] if phase == "practice" else [],
        },
        {
            "id": "law",
            "label": "Verificare disciplina e termini",
            "status": "pending",
            "note": "Il test non svolge ricerca legale",
            "outputs": [],
        },
        {
            "id": "filing",
            "label": "Verificare eventuale deposito",
            "status": "pending",
            "note": "Nessuna prova di azione esterna",
            "outputs": [],
        },
    ]
    citation = []
    if phase == "practice":
        source, unit = next(
            (s, u)
            for s in pack["sources"]
            for u in s["units"]
            if "Avvenuta consegna dichiarata nella ricevuta:" in u["text"]
        )
        citation = [
            {"source_id": source["id"], "anchor": unit["anchor"], "quote": unit["text"]}
        ]
    state["questions"] = [
        {
            "id": "delivery-proof",
            "question": "Quale ricevuta prova la consegna?",
            "reason": "Accettazione e consegna sono eventi documentali distinti",
            "blocks": ["delivery"],
            "status": "answered" if phase == "practice" else "open",
            "answer": (
                "Ricevuta fittizia del 2 ottobre 2026" if phase == "practice" else ""
            ),
            "citations": citation,
        },
        {
            "id": "law-review",
            "question": "Quale disciplina attuale è applicabile?",
            "reason": "La prova di consegna non è un termine giuridico verificato",
            "blocks": ["law"],
            "status": "open",
            "answer": "",
            "citations": [],
        },
        {
            "id": "filing-proof",
            "question": "È disponibile una ricevuta di deposito?",
            "reason": "La bozza non prova un’attività giudiziaria esterna",
            "blocks": ["filing"],
            "status": "open",
            "answer": "",
            "citations": [],
        },
    ]
    state["calendar"] = [
        {
            "id": "notice-delivery",
            "event": "Consegna dell’avviso — prova da verificare",
            "event_date": "2026-10-02" if phase == "practice" else "",
            "due_date": "",
            "status": "conditional" if phase == "practice" else "unknown",
            "basis": "Fonte fittizia; disciplina e presupposti restano da verificare",
            "reviewer_ref": "regression-fixture",
            "citations": citation,
        }
    ]
    _write(matter / "proposed-state.json", state)
    _run(
        HELPERS + "legal_matter.py",
        "save",
        "--run-dir",
        matter,
        "--state",
        matter / "proposed-state.json",
        "--expected-revision",
        "0",
    )
    _run(HELPERS + "legal_matter.py", "render", "--run-dir", matter)
    current = json.loads(_command_status(matter))
    assert current["changed_outputs"] == []
    assert current["blocked_stages"]["filing"] == ["filing-proof"]
    assert current["blocked_stages"]["law"] == ["law-review"]
    assert ("delivery" not in current["blocked_stages"]) == (phase == "practice")
    saved = _read(matter / "matter.json")
    assert saved["calendar"][0]["due_date"] == ""
    assert saved["calendar"][0]["event_date"] == (
        "2026-10-02" if phase == "practice" else ""
    )
    assert _read(matter / "matter-history/revision-0000.json")["revision"] == 0
    assert "EUR 2.880" in draft.read_text()
    assert "EUR 12.000" in draft.read_text()
    assert (matter / "review.xlsx").is_file()
    assert (matter / "matter.html").is_file()
    _complete_teaching_case(
        run,
        case,
        artifact_ids={
            "tax-matter/matter.json": "internal.tax.state",
            "tax-matter/bozza-intake.md": "internal.tax.draft",
        },
    )
    return matter


def _command_status(matter):
    import subprocess
    import sys

    result = subprocess.run(
        [
            sys.executable,
            str(ROOT / HELPERS / "legal_matter.py"),
            "status",
            "--run-dir",
            str(matter),
        ],
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    return result.stderr.strip()


@prepared_kit("vera/contenzioso-tributario", "lucia/contenzioso-tributario")
@pytest.mark.parametrize("product", ["vera", "lucia"])
@pytest.mark.parametrize("language", LANGUAGES)
@pytest.mark.parametrize("phase", ["demo", "practice"])
def test_tax_course_preserves_evidence_unknown_terms_and_prior_run(
    tmp_path, monkeypatch, record_property, product, language, phase
):
    demo = _bound_case(
        tmp_path / "demo", monkeypatch, WORKFLOW, WORKFLOW, "demo", product, language
    )
    matter = _execute(demo, product, language, "demo", tmp_path / "demo/case")
    if phase == "practice":
        from courseware.library import CourseLibrary

        spec = importlib.util
        module_spec = spec.spec_from_file_location(
            "tax_course_ledger",
            ROOT / "plugins/studio-archive/scripts/client_ledger.py",
        )
        ledger = spec.module_from_spec(module_spec)
        module_spec.loader.exec_module(ledger)
        previous = {
            p: p.read_bytes()
            for p in Path(demo["output_dir"]).rglob("*")
            if p.is_file()
        }
        kit = CourseLibrary(ROOT / "plugins" / product, {WORKFLOW}).render(
            WORKFLOW, language, tmp_path / "practice-kit"
        )
        case = tmp_path / "demo/case"
        context = demo["context"]
        imported = [
            ledger.import_document(
                case, context["client_id"], context["engagement_id"], Path(p), "source"
            )
            for p in kit["practice_files"]
        ]
        prepared = ledger.prepare_run(
            case,
            context["client_id"],
            context["engagement_id"],
            WORKFLOW,
            _read(ROOT / "plugins" / product / ".codex-plugin/plugin.json")["version"],
            input_ids=[item["receipt"]["input_id"] for item in imported],
            upstream_artifacts=[
                {
                    "run_id": context["run_id"],
                    "artifact_id": "internal.tax.state",
                    "role": "previous-state",
                }
            ],
            purpose="Second fictional receipt; preserve previous outputs",
        )
        run = ledger.start_run(
            case, context["engagement_id"], prepared["run"]["run_id"]
        )
        upstream = next(Path(run["context"]["input_dir"]).rglob("matter.json"))
        assert _read(upstream)["calendar"][0]["status"] == "unknown"
        matter = _execute(run, product, language, "practice", case)
        assert run["context"]["engagement_id"] == context["engagement_id"]
        assert run["context"]["run_id"] != context["run_id"]
        assert all(path.read_bytes() == data for path, data in previous.items())
    _write(
        tmp_path / "reviewed-artifacts.json",
        {
            "product": product,
            "language": language,
            "phase": phase,
            "artifacts": [
                {
                    "name": name,
                    "sha256": hashlib.sha256((matter / name).read_bytes()).hexdigest(),
                }
                for name in ["review.csv", "bozza-intake.md", "matter.html"]
            ],
        },
    )
    record_native_check(
        record_property,
        root=ROOT,
        product=product,
        workflow=WORKFLOW,
        language=language,
        phase=phase,
    )


@pytest.mark.parametrize("product", ["vera", "lucia"])
def test_withdrawn_tax_course_is_absent_from_release_catalogue(product: str) -> None:
    """Withdraw lesson delivery while retaining its authored professional workflow."""
    plan = _read(ROOT / "scripts/course_materials/release_plan.json")
    catalogue = _read(ROOT / "plugins" / product / "assets/courses/index.json")
    authored = _read(ROOT / "scripts/course_materials/kits.json")
    key = f"{product}/{WORKFLOW}"

    assert key in plan["excluded"]
    assert key not in plan["prepared"]
    assert key in authored
    assert WORKFLOW not in catalogue["courses"]
    assert not (ROOT / "plugins" / product / "assets/courses" / WORKFLOW).exists()
    assert (ROOT / "plugins" / product / "skills" / WORKFLOW / "SKILL.md").is_file()
