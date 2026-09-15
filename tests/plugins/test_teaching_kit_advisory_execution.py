"""Run Clara teaching sources through current local advisory helpers.

Fixed model-authored interpretations below apply only to these fictional cases.
They are not shipped answers, semantic classifiers, learner confirmations or
professional approvals. Native voice and live model behaviour need host review.
"""

from __future__ import annotations

import hashlib
import importlib.util
import json
import re
import sys
from pathlib import Path
from urllib.parse import unquote

import pytest

from tests.plugins._teaching_release import record_native_check

ROOT = Path(__file__).resolve().parents[2]
CLARA = ROOT / "plugins/clara"


def _read(path):
    return json.loads(path.read_text(encoding="utf-8"))


def _write(path, payload):
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _load(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def _kit(tmp_path, monkeypatch, workflow, language, phase):
    monkeypatch.syspath_prepend(str(ROOT / "plugins/_shared/vendor/modules"))
    from courseware.library import CourseLibrary

    kit = CourseLibrary(CLARA, {workflow}).render(workflow, language, tmp_path / "kit")
    return {
        Path(file).stem.rsplit("-", 1)[0]: Path(file)
        for file in kit["source_files" if phase == "demo" else "practice_files"]
    }


def _contract(files, language, *, revised=False):
    """A reviewed interpretation of these exact authored notes, for regression only."""
    text = _read(ROOT / "tests/fixtures/teaching_advisory/planning.json")[language]
    phase = "practice" if revised else "demo"
    objective = text[f"decision_{phase}"]
    deliverable = text[f"deliverable_{phase}"]
    source_ids = list(files)
    schema = _read(CLARA / "contracts/advisory_contract.v1.schema.json")
    dimensions = [
        item["const"]
        for item in schema["$defs"]["validation_profile"]["properties"][
            "review_dimensions"
        ]["prefixItems"]
    ]
    # All substantive paragraphs were reviewed while authoring this fixture.
    # Exact paragraphs retain the localized details; headings are navigational.
    facts = [
        {"category": "fact", "text": line, "source_anchor": line, "input_id": key}
        for key, path in files.items()
        if key != "external-memo"
        for line in path.read_text(encoding="utf-8").splitlines()
        if line and not line.startswith("#")
    ]
    return {
        "schema_version": "1.0",
        "contract_status": "ready_for_handoff",
        "decision": objective,
        "purpose": text["purpose"],
        "audience": text["audience"],
        "deliverable_type": deliverable,
        "output_language": language,
        "scope_included": [
            objective,
            text["included"],
        ],
        "scope_excluded": [text["excluded"]],
        "available_inputs": [
            {
                "id": key,
                "description": text["input_labels"][key],
                "status": "available",
                "source_ref": path.name,
            }
            for key, path in files.items()
        ],
        "evidence_requirements": [
            {
                "id": "supplied-context",
                "requirement": text["requirement_current"],
                "rationale": text["rationale_current"],
                "status": "available",
                "input_ids": source_ids,
            },
            {
                "id": "pilot-feasibility",
                "requirement": text["requirement_missing"],
                "rationale": text["rationale_missing"],
                "status": "missing",
                "input_ids": [],
            },
        ],
        "analysis_plan": [
            {
                "id": "assess",
                "objective": objective,
                "method": text["method"],
                "input_ids": source_ids,
                "output": deliverable,
            }
        ],
        "assumptions": [],
        "unresolved_questions": [
            {
                "question": text["question"],
                "why_it_matters": text["question_reason"],
                "blocking": False,
            }
        ],
        "success_criteria": text["criteria"],
        "selected_clara_workflow": "clara:advisory-case-director",
        "validation_profile": {"review_dimensions": dimensions, "format_checks": []},
        "validation_scope": {
            "coverage": "all_material_content",
            "included_sections": [text["coverage"]],
            "excluded_sections": [],
            "limitations": [text["limitation"]],
        },
        "correction_policy": {
            "mode": "separate_artifact",
            "preserve_original": True,
            "allowed": True,
            "approval_required_before_delivery": True,
        },
        "professional_judgement_policy": {
            "owner": text["owner"],
            "model_role": text["model_role"],
            "approval_required_before_delivery": True,
        },
        "source_facts": facts,
        "explicit_questions": [
            {"question": line, "input_id": "assignment"}
            for line in files["assignment"].read_text(encoding="utf-8").splitlines()
            if "?" in line
        ],
        "generation_handoff": {
            "workflow": "clara:advisory-case-director",
            "objective": objective,
            "input_ids": source_ids,
            "instructions": text["instructions"],
            "expected_outputs": [deliverable],
            "preserve_specialist_authority": True,
        },
        "model_review": {
            "method": "model_led_assignment_contract_review",
            "dimensions": {
                key: "conforms"
                for key in schema["$defs"]["model_review"]["properties"]["dimensions"][
                    "required"
                ]
            },
            "overall_status": "conforms",
        },
    }


def _run_planner_case(tmp_path, monkeypatch, language, phase, prior_plan=None):
    """Run the native packager and exercise the ordinary host-authored delivery."""
    files = _kit(tmp_path, monkeypatch, "advisory-brief-planner", language, phase)
    contract = _contract(files, language, revised=phase == "practice")
    draft = tmp_path / "draft_advisory_contract.json"
    _write(draft, contract)
    validator = _load(
        CLARA / "scripts/validate_advisory_contract.py",
        "kit_advisory_contract_validator",
    )
    canonical, report_path, errors = validator.package_advisory_contract(
        draft, tmp_path / "plan", source_paths=files
    )
    assert errors == []
    assert _read(report_path)["status"] == "passed"
    assert (
        _read(canonical)["generation_handoff"]["workflow"]
        == "clara:advisory-case-director"
    )
    assert len(_read(report_path)["source_files"]) == len(files)
    assert _read(canonical)["deliverable_type"] == contract["deliverable_type"]
    text = _read(ROOT / "tests/fixtures/teaching_advisory/planning.json")[language]
    headings = text["headings"]
    outline = [
        f"# {headings['title']}",
        f"## {headings['decision']}",
        contract["decision"],
        contract["deliverable_type"],
        contract["audience"],
        f"## {headings['basis']}",
        text[f"basis_{phase}"],
        f"## {headings['scope']}",
        f"**{headings['included']}:** {text['included']}",
        f"**{headings['excluded']}:** {text['excluded']}",
        text["limitation"],
        f"## {headings['sources']}",
        "\n".join(
            f"- [{text['input_labels'][key]}]({path})" for key, path in files.items()
        ),
        f"## {headings['work']}",
        "\n".join(
            f"{index}. {step}"
            for index, step in enumerate(text[f"steps_{phase}"], start=1)
        ),
        f"## {headings['question']}",
        text["question"],
        text["question_reason"],
        f"## {headings['next']}",
        text[f"next_{phase}"],
        f"## {headings['records']}",
        f"- [{headings['contract']}]({canonical.name})\n"
        f"- [{headings['validation']}]({report_path.name})\n"
        f"- [{headings['review']}](codex_run_review.md)",
    ]
    if prior_plan is not None:
        outline.append(f"[{text['input_labels']['assignment']}]({prior_plan})")
    summary = canonical.parent / "assignment_plan.md"
    summary.write_text("\n\n".join(outline) + "\n", encoding="utf-8")
    (canonical.parent / "codex_run_review.md").write_text(
        f"# {headings['review']}\n\n{text['review_note']}\n\n"
        f"[{headings['contract']}]({canonical.name})\n\n"
        f"[{headings['validation']}]({report_path.name})\n",
        encoding="utf-8",
    )
    assert _read(canonical)["output_language"] == language
    assert all(item["input_id"] in files for item in _read(canonical)["source_facts"])
    return canonical.parent


@pytest.mark.parametrize("language", ["it", "en", "fr", "de", "es"])
@pytest.mark.parametrize("phase", ["demo", "practice"])
def test_planner_kit_packages_current_source_bound_assignment(
    tmp_path, monkeypatch, record_property, language, phase
):
    initial = _run_planner_case(tmp_path / "demo", monkeypatch, language, "demo")
    snapshot = {p: p.read_bytes() for p in initial.iterdir() if p.is_file()}
    if phase == "practice":
        current = _run_planner_case(
            tmp_path / "practice",
            monkeypatch,
            language,
            "practice",
            prior_plan=initial / "assignment_plan.md",
        )
        assert {p: p.read_bytes() for p in snapshot} == snapshot
        assert (
            _read(current / "advisory_contract.json")["decision"]
            != _read(initial / "advisory_contract.json")["decision"]
        )
        assert {"revised-assignment", "update"} <= {
            item["id"]
            for item in _read(current / "advisory_contract.json")["available_inputs"]
        }
    record_native_check(
        record_property,
        root=ROOT,
        product="clara",
        workflow="advisory-brief-planner",
        language=language,
        phase=phase,
    )


def _memo_review(inventory, language, *, updated):
    """Reviewed interpretations of these exact fictional notes, not runtime rules."""
    text = _read(ROOT / "tests/fixtures/teaching_advisory/memo_review.json")[language]
    phase = "practice" if updated else "demo"
    source_refs = ["source-0001", "source-0002"] + (["source-0003"] if updated else [])
    vehicle_refs = ["source-0002"] + (["source-0003"] if updated else [])
    vehicle = text[f"vehicle_{phase}"]
    statuses = {
        "contract_conformance": "partially_conforms",
        "factual_source_support": "contradicted",
        "calculations_data_provenance": "not_applicable",
        "reasoning_assumptions": "does_not_conform",
        "contradictions_missing_evidence": "does_not_conform",
        "recommendation_evidence_decision_fit": "does_not_conform",
        "professional_judgement_boundaries": "judgment_required",
        "correction_needs": "does_not_conform",
        "residual_uncertainty": "partially_conforms",
        "delivery_readiness": "does_not_conform",
    }
    judgments = {
        key: value.replace("{vehicle}", vehicle)
        for key, value in text["dimensions"].items()
    }
    dimensions = {
        key: {
            "status": status,
            "analysis": judgments[key],
            "evidence_refs": [] if status == "not_applicable" else source_refs,
            "issues": [] if status == "not_applicable" else [judgments[key]],
            "correction_status": (
                "not_needed" if status == "not_applicable" else "proposed"
            ),
            "professional_review_required": key == "professional_judgement_boundaries",
        }
        for key, status in statuses.items()
    }
    customer_analysis = (
        text["dimensions"]["factual_source_support"].replace("{vehicle}", "").strip()
    )
    declared = [
        (
            "launch",
            "unsupported",
            "gap",
            judgments["recommendation_evidence_decision_fit"],
            source_refs,
        ),
        ("demand", "contradicted", "gap", customer_analysis, ["source-0002"]),
        (
            "vehicle",
            "contradicted" if updated else "partial",
            "gap",
            vehicle,
            vehicle_refs,
        ),
        (
            "preconditions",
            "adequate",
            "sound",
            text["preconditions_analysis"],
            ["source-0001", "source-0002"],
        ),
        (
            "booking-sequence",
            "unsupported",
            "gap",
            text["booking_analysis"],
            ["source-0001", "source-0002"],
        ),
    ]
    claims = [
        {
            "id": key,
            "statement": text["quotes"][key],
            "deliverable_locations": [
                text[
                    (
                        "second_location"
                        if key in {"preconditions", "booking-sequence"}
                        else "first_location"
                    )
                ]
            ],
            "evidence_ids": refs,
            "dependency_claim_ids": [],
            "support_status": support,
            "reasoning_status": reasoning,
            "contradiction_resolution": (
                explanation if support == "contradicted" else ""
            ),
            "analysis": explanation,
            "recheck": {
                "required": False,
                "kind": "none",
                "status": "not_required",
                "evidence_ids": [],
                "analysis": text["recheck_note"],
            },
            "resolution": {
                "status": "no_change" if key == "preconditions" else "pending",
                "explanation": explanation,
            },
        }
        for key, support, reasoning, explanation, refs in declared
    ]
    findings = [
        (
            "launch-not-supported",
            "recommendation_evidence_decision_fit",
            judgments["recommendation_evidence_decision_fit"],
            text["actions"]["launch"],
            source_refs,
        ),
        (
            "demand-overstated",
            "factual_source_support",
            customer_analysis,
            text["actions"]["demand"],
            ["source-0002"],
        ),
        (
            "vehicle-conditions",
            "contradictions_missing_evidence",
            vehicle,
            text["actions"][f"vehicle_{phase}"],
            vehicle_refs,
        ),
    ]
    return {
        "schema_version": "1.3",
        "language": language,
        "advisory_contract_sha256": inventory["advisory_contract_sha256"],
        "deliverable_sha256": inventory["source_sha256"],
        "coverage_inventory_sha256": inventory["coverage_inventory_sha256"],
        "lineage_inventory_sha256": inventory["lineage"]["lineage_inventory_sha256"],
        "coverage_review": {
            "selection_method": "model_led_materiality_review",
            "scope": "all_material_content",
            "reviewed_sections": [text["coverage_section"]],
            "omitted_sections": [],
            "considered_unit_ids": ["unit-0001"],
            "omitted_unit_ids": [],
            "unit_assessments": [
                {
                    "unit_id": "unit-0001",
                    "status": "reviewed_material_claims",
                    "material_claim_ids": [],
                    "untracked_claim_ids": [item[0] for item in declared],
                    "analysis": text["coverage_note"],
                }
            ],
            "limitations": [text["history_limit"]],
            "analysis": text["coverage_analysis"],
        },
        "lineage_review": {
            "provenance_mode": "matched_support",
            "selection_method": "model_led_claim_chain_review",
            "reviewed_claim_ids": [],
            "chain_assessments": [],
            "untracked_material_claims": claims,
            "limitations": [text["provenance_limit"]],
            "analysis": text["coverage_analysis"],
        },
        "dimension_reviews": dimensions,
        "findings": [
            {
                "id": key,
                "dimension": dimension,
                "finding": finding,
                "status": "does_not_conform",
                "evidence_refs": refs,
                "correction_action": action,
                "correction_status": "proposed",
                "professional_review_required": True,
            }
            for key, dimension, finding, action, refs in findings
        ],
        "format_specific_checks": [],
        "correction": {
            "status": "required",
            "summary": text["correction_summary"],
            "corrected_artifact": "",
            "corrected_artifact_sha256": "",
            "corrected_inventory_sha256": "",
            "corrected_review_sha256": "",
            "unresolved_changes": [judgments["correction_needs"]],
        },
        "approvals": {
            "professional_judgement": {
                "status": "pending",
                "approved_by": "",
                "evidence_refs": [],
            },
            "correction": {"status": "pending", "approved_by": "", "evidence_refs": []},
        },
        "overall_assessment": {
            "outcome": "not_ready",
            "analysis": judgments["delivery_readiness"],
            "residual_uncertainties": [text["remaining"]],
            "professional_review_items": [text["owner_action"]],
        },
        "delivery_readiness": {
            "status": "not_ready",
            "conditions": [text["condition"]],
        },
    }


def _run_validator_case(tmp_path, files, language, phase, prior_package=None):
    """Review these selected sources in a distinct, retained native output folder."""
    tmp_path.mkdir(parents=True, exist_ok=True)
    contract_path = tmp_path / "advisory_contract.json"
    _write(contract_path, _contract(files, language))
    validator = _load(
        CLARA / "skills/advisory-deliverable-validator/scripts/advisory_validation.py",
        "kit_current_advisory_validation",
    )
    memo = files["external-memo"]
    before = memo.read_bytes()
    support = [files["assignment"], files["notes"]]
    if phase == "practice":
        support.append(files["update"])
    output = tmp_path / "validation"
    prepared = validator.prepare_validation(
        memo, contract_path, output, source_files=support
    )
    inventory = _read(prepared["deliverable_inventory"])
    assert len(_read(prepared["coverage_inventory"])["units"]) == 1
    review = _memo_review(inventory, language, updated=phase == "practice")
    draft = tmp_path / "review-draft.json"
    _write(draft, review)
    paths, audit = validator.package_validation(
        prepared["deliverable_inventory"], draft, contract_path, output
    )
    assert audit["record_complete"] is True, audit
    packaged = _read(paths["review"])
    assert packaged["delivery_readiness"]["status"] == "not_ready"
    assert packaged["approvals"]["professional_judgement"]["status"] == "pending"
    assert packaged["lineage_review"]["provenance_mode"] == "matched_support"
    assert paths["package"].is_file()
    assert memo.read_bytes() == before
    text = _read(ROOT / "tests/fixtures/teaching_advisory/memo_review.json")[language]
    claims = packaged["lineage_review"]["untracked_material_claims"]
    assert len(claims) == 5
    assert all(
        claim["statement"] in memo.read_text(encoding="utf-8") for claim in claims
    )
    assert {claim["id"] for claim in claims} == set(text["quotes"])
    assert text["booking_analysis"] in paths["package"].read_text(encoding="utf-8")
    card = [
        f"# {text['title']}",
        packaged["overall_assessment"]["analysis"],
        "\n".join(
            f"- {finding['correction_action']}" for finding in packaged["findings"]
        ),
        text["condition"],
        text["owner_action"],
        f"[{text['package_label']}]({paths['package'].name})",
        f"[{text['original_label']}]({memo})",
    ]
    if prior_package is not None:
        card.append(f"[{text['prior_label']}]({prior_package})")
    card.extend(
        [
            f"## {text['records_label']}",
            "\n".join(
                f"- [{path.name}]({path.name})"
                for path in [
                    *prepared.values(),
                    paths["review"],
                    paths["audit"],
                    paths["recheck_tasks"],
                ]
            ),
        ]
    )
    (output / "artifact_card.md").write_text("\n\n".join(card) + "\n", encoding="utf-8")
    (output / "codex_run_review.md").write_text(
        f"# {text['review_title']}\n\n{text['review_note']}\n\n"
        f"{text['remaining']}\n\n{text['owner_action']}\n\n"
        f"[{text['package_label']}]({paths['package'].name})\n\n"
        f"[{text['original_label']}]({memo})\n\n"
        f"[{paths['audit'].name}]({paths['audit'].name})\n",
        encoding="utf-8",
    )
    for name in ["artifact_card.md", "codex_run_review.md", paths["package"].name]:
        document = output / name
        targets = re.findall(r"\]\(([^)]+)\)", document.read_text(encoding="utf-8"))
        assert targets, document
        assert all((output / unquote(target)).is_file() for target in targets), document
    return paths


@pytest.mark.parametrize("language", ["it", "en", "fr", "de", "es"])
@pytest.mark.parametrize("phase", ["demo", "practice"])
def test_validator_kit_produces_source_bound_review_without_approval(
    tmp_path, monkeypatch, record_property, language, phase
):
    files = _kit(
        tmp_path, monkeypatch, "advisory-deliverable-validator", language, phase
    )
    initial_files = {key: path for key, path in files.items() if key != "update"}
    initial = _run_validator_case(tmp_path / "demo", initial_files, language, "demo")
    preserved = {
        path: path.read_bytes()
        for path in (tmp_path / "demo").rglob("*")
        if path.is_file()
    }
    current = initial
    if phase == "practice":
        current = _run_validator_case(
            tmp_path / "practice",
            files,
            language,
            phase,
            prior_package=initial["package"],
        )
        first_review = _read(initial["review"])
        updated_review = _read(current["review"])
        assert (
            first_review["deliverable_sha256"] == updated_review["deliverable_sha256"]
        )
        first_vehicle = next(
            item
            for item in first_review["lineage_review"]["untracked_material_claims"]
            if item["id"] == "vehicle"
        )
        updated_vehicle = next(
            item
            for item in updated_review["lineage_review"]["untracked_material_claims"]
            if item["id"] == "vehicle"
        )
        assert first_vehicle["support_status"] == "partial"
        assert updated_vehicle["support_status"] == "contradicted"
        assert all(path.read_bytes() == data for path, data in preserved.items())
        assert current["package"] != initial["package"]
    record_property("teaching_output", str(current["package"].parent))
    record_native_check(
        record_property,
        root=ROOT,
        product="clara",
        workflow="advisory-deliverable-validator",
        language=language,
        phase=phase,
    )


WORKPAPERS = {
    "it": (
        "Valutare un pilota su prenotazione, subordinato alle verifiche operative, prima di un servizio quotidiano.\n\nLe note riportano interesse condizionato di Anna e Carla e la preferenza di Bruno per la consegna in negozio. Non dimostrano prenotazioni né domanda complessiva. La disponibilità del mezzo riguarda soltanto il mercoledì sera.\n\nProssimo lavoro: definire percorso, prezzo e costi e verificare la disponibilità effettiva a prenotare. La titolare decide se procedere; nessun impegno è assunto.",
        "Prima di programmare il pilota occorre verificare una soluzione di trasporto. Il servizio quotidiano resta privo di supporto sufficiente.\n\nLa nuova nota ritira la disponibilità del mezzo nel periodo previsto. Il prestito ipotizzato non è concordato. Le dichiarazioni dei clienti restano invariate e non equivalgono a prenotazioni.\n\nIl prossimo passo prioritario è chiarire mezzo, disponibilità e costi, poi verificare le altre condizioni del pilota. La versione precedente rimane nello storico; nessun contatto o impegno è stato effettuato.",
    ),
    "en": (
        "Assess an appointment-based pilot, subject to operational checks, before a daily service.\n\nAnna and Carla express conditional interest; Bruno prefers bringing his bicycle to the shop. The notes establish neither bookings nor wider demand. Vehicle availability covers Wednesday evenings only.\n\nNext work: define route, price and costs and test actual willingness to book. The owner decides whether to proceed; no commitment has been made.",
        "Establish a transport solution before scheduling the pilot. The daily service still lacks sufficient support.\n\nThe new note withdraws vehicle availability during the planned period. The possible loan is not agreed. Customer statements remain unchanged and do not constitute bookings.\n\nThe immediate priority is to clarify vehicle, availability and costs, then the remaining pilot conditions. The earlier version stays in history; no contact or commitment has been made.",
    ),
    "fr": (
        "Évaluer un pilote sur rendez-vous, sous réserve des vérifications opérationnelles, avant un service quotidien.\n\nAnna et Carla expriment un intérêt conditionnel ; Bruno préfère apporter son vélo. Les notes ne démontrent ni réservation ni demande globale. Le véhicule est disponible uniquement le mercredi soir.\n\nProchain travail : définir itinéraire, prix et coûts et vérifier la disposition réelle à réserver. La dirigeante décide ; aucun engagement n’est pris.",
        "Vérifier une solution de transport avant de programmer le pilote. Le service quotidien reste insuffisamment étayé.\n\nLa nouvelle note retire la disponibilité du véhicule pendant la période prévue. Le prêt envisagé n’est pas convenu. Les déclarations clients restent inchangées et ne sont pas des réservations.\n\nLa priorité est de clarifier véhicule, disponibilité et coûts, puis les autres conditions du pilote. La version précédente reste dans l’historique ; aucun contact ni engagement n’a été effectué.",
    ),
    "de": (
        "Zunächst einen Pilotversuch nach Terminvereinbarung unter betrieblichen Vorbehalten prüfen, bevor ein täglicher Service erwogen wird.\n\nAnna und Carla äußern bedingtes Interesse; Bruno bringt sein Fahrrad lieber selbst. Die Notizen belegen weder Buchungen noch Gesamtnachfrage. Das Fahrzeug steht nur mittwochabends bereit.\n\nNächste Arbeit: Route, Preis und Kosten klären und tatsächliche Buchungsbereitschaft prüfen. Die Inhaberin entscheidet; es wurde nichts zugesagt.",
        "Vor der Terminierung des Pilotversuchs eine Transportlösung prüfen. Für den täglichen Service fehlt weiterhin ausreichende Grundlage.\n\nDie neue Notiz hebt die Fahrzeugverfügbarkeit im geplanten Zeitraum auf. Die mögliche Ausleihe ist nicht vereinbart. Kundenaussagen bleiben unverändert und sind keine Buchungen.\n\nVorrangig Fahrzeug, Verfügbarkeit und Kosten klären, dann die weiteren Pilotbedingungen. Die Vorversion bleibt in der Historie; es gab keine Kontakte oder Zusagen.",
    ),
    "es": (
        "Evaluar un piloto con cita previa, sujeto a comprobaciones operativas, antes de un servicio diario.\n\nAnna y Carla expresan interés condicionado; Bruno prefiere llevar su bicicleta. Las notas no demuestran reservas ni demanda general. El vehículo solo está disponible los miércoles por la tarde.\n\nPróximo trabajo: definir ruta, precio y costes y verificar la disposición real a reservar. La propietaria decide; no se ha asumido ningún compromiso.",
        "Comprobar una solución de transporte antes de programar el piloto. El servicio diario sigue sin respaldo suficiente.\n\nLa nueva nota retira la disponibilidad del vehículo durante el periodo previsto. El posible préstamo no está acordado. Las declaraciones de clientes no cambian y no son reservas.\n\nLa prioridad es aclarar vehículo, disponibilidad y costes y después las demás condiciones. La versión anterior queda en el historial; no se han realizado contactos ni compromisos.",
    ),
}


def _case_return(case, registered, *, update, language):
    """Declare exact observed inputs and a bounded model-authored conclusion."""
    phase = "update" if update else "initial"
    lesson_phase = "practice" if update else "demo"
    text = _read(ROOT / "tests/fixtures/teaching_advisory/case_direction.json")[
        language
    ]
    recorded_at = "2026-09-14T09:00:00+00:00" if update else "2026-09-14T08:00:00+00:00"
    evidence = []
    sources = []
    for key, copied in registered.items():
        if update and key != "update":
            continue  # Earlier immutable receipts remain in the same case.
        path = copied.destination_path
        artifact = {
            "path": path.relative_to(case).as_posix(),
            "path_reference": "case_relative",
            "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
            "byte_count": path.stat().st_size,
        }
        sources.append({**artifact, "role": "other"})
        evidence.append(
            {
                "id": "ev-" + key,
                "evidence_type": "local_document",
                "recorded_at": recorded_at,
                "recorded_by": "clara:advisory-case-director",
                "capture_status": "captured",
                "source": {
                    "material_ids": [copied.registered_material["id"]],
                    "url": "",
                    "locator": text["locator"],
                    "artifact_refs": [artifact],
                },
                "observation": text["evidence"][key]["observation"],
                "scope": text["scope"],
                "limitations": [text["limit"]],
                "verification": {
                    "status": "identity_verified",
                    "checked_at": recorded_at,
                    "method": text["verification"],
                    "notes": [],
                },
                "rechecks_evidence_id": "",
                "supersedes_evidence_id": "",
            }
        )
    statement = WORKPAPERS[language][1 if update else 0]
    claim = {
        "id": "cl-" + phase,
        "statement": statement,
        "claim_type": "conclusion",
        "recorded_at": recorded_at,
        "recorded_by": "clara:advisory-case-director",
        "provenance": {
            "workflow": "clara:advisory-case-director",
            "step": text[f"change_{lesson_phase}"],
            "artifact": "",
            "locator": text["title"],
        },
        "evidence_links": [
            {
                "evidence_id": f"ev-{key}",
                "relationship": "context" if key == "assignment" else "supports",
                "analysis": text["evidence"][key][
                    "analysis_update" if update and key == "notes" else "analysis"
                ],
                "proves": text["evidence"][key]["proves"],
                "does_not_prove": text["evidence"][key]["does_not_prove"],
                "directness": "contextual" if key == "assignment" else "indirect",
                "reliability": "high" if key == "assignment" else "medium",
                "corroboration": "single_source",
                "bias_or_limitation": text["evidence"][key]["bias"],
            }
            for key in registered
        ],
        "dependency": {
            "mode": "none",
            "claim_ids": [],
            "derivation_type": "reasoning",
            "explanation": text[f"reasoning_{lesson_phase}"],
            "calculation_evidence_id": "",
        },
        "decision_use": "direct",
        "decision_implication": text[f"implication_{lesson_phase}"],
        "missing_evidence_that_would_change_position": text[f"question_{lesson_phase}"],
        "uncertainty": [text["uncertainty"]],
        "professional_judgement_required": True,
        "appearances": [],
        "state": "active",
        "supersedes_claim_id": "cl-initial" if update else "",
    }
    return {
        "schema_version": "1.0",
        "return_id": "return-" + phase,
        "return_type": "analysis_branch",
        "branch": {
            "workflow": "clara:advisory-case-director",
            "question_id": "",
            "question": text["question"],
            "answer": statement,
        },
        "answer_effect": "changes" if update else "strengthens",
        "result_claim_ids": [claim["id"]],
        "source_artifacts": sources,
        "limitations": claim["uncertainty"],
        "evidence_receipts": evidence,
        "claims": [claim],
        "judgement_entries": [],
        "question_updates": [],
        "new_questions": [
            {
                "question": text[f"question_{lesson_phase}"],
                "why_it_matters": text["why"],
                "source_entry_ids": [],
                "source_judgement_indexes": [],
            }
        ],
        "validation_binding": None,
    }


def _case_workpaper(case, registered, language, phase):
    """Ordinary host-authored delivery using the current case's retained sources."""
    text = _read(ROOT / "tests/fixtures/teaching_advisory/case_direction.json")[
        language
    ]
    planning = _read(ROOT / "tests/fixtures/teaching_advisory/planning.json")[language]
    return (
        "\n\n".join(
            [
                f"# {text['title']}",
                WORKPAPERS[language][1 if phase == "practice" else 0],
                f"## {text['question_heading']}",
                text[f"question_{phase}"],
                text["why"],
                f"## {text['sources_heading']}",
                "\n".join(
                    f"- [{planning['input_labels'][key]}]({copied.destination_path.as_posix()})"
                    for key, copied in registered.items()
                ),
                f"[{text['map_label']}]({(case / 'advisory_evidence_map.md').as_posix()})",
            ]
        )
        + "\n"
    )


@pytest.mark.parametrize("language", ["it", "en", "fr", "de", "es"])
@pytest.mark.parametrize("phase", ["demo", "practice"])
def test_case_director_kit_updates_actual_case_and_preserves_workpaper_history(
    tmp_path, monkeypatch, record_property, language, phase
):
    files = _kit(tmp_path, monkeypatch, "advisory-case-director", language, phase)
    text = _read(ROOT / "tests/fixtures/teaching_advisory/case_direction.json")[
        language
    ]
    planning = _read(ROOT / "tests/fixtures/teaching_advisory/planning.json")[language]
    monkeypatch.syspath_prepend(str(CLARA / "scripts"))
    core = _load(CLARA / "scripts/advisor_case_core.py", "kit_advisory_case_core")
    case = tmp_path / "case"
    core.initialize_case(
        case,
        client=text["client"],
        project=text["project"],
        objective=planning["decision_demo"],
        audience=planning["audience"],
        output_language=language,
    )
    registered = {
        key: core.copy_case_file(case, files[key], kind="source", register=True)
        for key in ("assignment", "notes")
    }
    first = _case_return(case, registered, update=False, language=language)
    core.record_case_direction_return(case, first)
    staged = tmp_path / "workpaper-draft.md"
    staged.write_text(
        _case_workpaper(case, registered, language, "demo"), encoding="utf-8"
    )
    baseline = core.commit_advisory_workpaper(
        case,
        staged,
        referenced_claim_ids=["cl-initial"],
        change_summary=text["change_demo"],
    )
    initial_bytes = (case / "advisory_workpaper.md").read_bytes()
    initial_evidence = _read(case / "advisory_evidence_register.json")["evidence"]
    current = baseline
    delivery = [f"# {text['title']}", f"[{text['title']}](advisory_workpaper.md)"]
    if phase == "practice":
        registered["update"] = core.copy_case_file(
            case, files["update"], kind="source", register=True
        )
        core.record_case_direction_return(
            case, _case_return(case, registered, update=True, language=language)
        )
        staged.write_text(
            _case_workpaper(case, registered, language, phase), encoding="utf-8"
        )
        current = core.commit_advisory_workpaper(
            case,
            staged,
            referenced_claim_ids=["cl-update"],
            change_summary=text["change_practice"],
        )
        assert current["prior_workpaper"]["sha256"] == baseline["workpaper"]["sha256"]
        prior_path = case / current["prior_workpaper"]["history_path"]
        assert prior_path.read_bytes() == initial_bytes
        delivery.append(
            f"[{text['prior_label']}]({prior_path.relative_to(case).as_posix()})"
        )
        assert (
            _read(case / "advisory_evidence_register.json")["evidence"][:2]
            == initial_evidence
        )
    (case / "artifact_card.md").write_text(
        "\n\n".join(delivery) + "\n", encoding="utf-8"
    )
    (case / "codex_run_review.md").write_text(
        f"# {text['review_title']}\n\n{text[f'review_{phase}']}\n\n"
        f"[{text['title']}](advisory_workpaper.md)\n\n"
        f"[{text['map_label']}](advisory_evidence_map.md)\n",
        encoding="utf-8",
    )
    assert core.validate_case_workspace(case) == []
    assert sorted(current["lineage"]["referenced_evidence_ids"]) == sorted(
        f"ev-{key}" for key in registered
    )
    assert (case / "advisory_workpaper.md").read_text(
        encoding="utf-8"
    ) == _case_workpaper(case, registered, language, phase)
    claims = _read(case / "advisory_claim_register.json")["claims"]
    assert [claim["id"] for claim in claims if claim["state"] == "active"] == [
        "cl-update" if phase == "practice" else "cl-initial"
    ]
    if phase == "practice":
        assert claims[0]["state"] == "superseded"
        assert claims[1]["supersedes_claim_id"] == "cl-initial"
        assert claims[1]["dependency"]["claim_ids"] == []
    evidence_map = (case / "advisory_evidence_map.md").read_text(encoding="utf-8")
    assert text[f"implication_{phase}"] in evidence_map
    assert text[f"question_{phase}"] in evidence_map
    assert all(
        copied.destination_path.name in evidence_map for copied in registered.values()
    )
    delivered = [
        case / name
        for name in (
            "advisory_workpaper.md",
            "artifact_card.md",
            "advisory_evidence_map.md",
            "codex_run_review.md",
        )
    ]
    if phase == "practice":
        delivered.append(prior_path)
    for document in delivered:
        targets = re.findall(r"\]\(([^)]+)\)", document.read_text(encoding="utf-8"))
        assert targets, document
        assert all(
            (document.parent / unquote(target)).is_file() for target in targets
        ), document
    record_property("teaching_output", str(case))
    record_native_check(
        record_property,
        root=ROOT,
        product="clara",
        workflow="advisory-case-director",
        language=language,
        phase=phase,
    )
