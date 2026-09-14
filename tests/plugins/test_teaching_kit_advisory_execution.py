"""Run Clara teaching sources through current local advisory helpers.

Fixed model-authored interpretations below apply only to these fictional cases.
They are not shipped answers, semantic classifiers, learner confirmations or
professional approvals. Native voice and live model behaviour need host review.
"""

from __future__ import annotations

import hashlib
import importlib.util
import json
import sys
from pathlib import Path

import pytest

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
    objective = "Compare an appointment-based collection pilot with immediate daily service for Ciclo Arco."
    deliverable = (
        "Short owner memo with recommendation, reasons, limitations and next step."
    )
    if revised:
        objective = "Plan the checks needed to establish feasibility of an appointment-based pilot; do not give a launch recommendation."
        deliverable = "Short action list for the owner covering vehicle, route, price and willingness to book."
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
        "purpose": "Support the owner with a bounded assessment from the supplied notes.",
        "audience": "Owner of Ciclo Arco",
        "deliverable_type": deliverable,
        "output_language": language,
        "scope_included": [
            objective,
            "Customer comments, operational availability and decision-changing evidence gaps.",
        ],
        "scope_excluded": [
            "Financial forecast, wider demand estimate, customer contact, external research, spending or launch commitments."
        ],
        "available_inputs": [
            {
                "id": key,
                "description": key,
                "status": "available",
                "source_ref": path.name,
            }
            for key, path in files.items()
        ],
        "evidence_requirements": [
            {
                "id": "supplied-context",
                "requirement": "Use the assignment and supplied customer and operational notes.",
                "rationale": "They define the decision and the limited evidence available.",
                "status": "available",
                "input_ids": source_ids,
            },
            {
                "id": "pilot-feasibility",
                "requirement": "Establish prices, route, costs, capacity and willingness to book before implementation.",
                "rationale": "Interest and a provisional vehicle arrangement do not prove demand or feasibility.",
                "status": "missing",
                "input_ids": [],
            },
        ],
        "analysis_plan": [
            {
                "id": "assess",
                "objective": objective,
                "method": "Compare the requested options against actual statements and operational limits; identify what would change the conclusion.",
                "input_ids": source_ids,
                "output": deliverable,
            }
        ],
        "assumptions": [],
        "unresolved_questions": [
            {
                "question": "What price, route, costs, vehicle availability and booking interest would support a pilot?",
                "why_it_matters": "These are implementation prerequisites; a qualified assessment can identify them now.",
                "blocking": False,
            }
        ],
        "success_criteria": [
            "Preserve the owner’s current objective and scope.",
            "Separate customer statements from demand evidence and operating proposals from agreed capacity.",
            "State the next checks and avoid invented figures or authority.",
        ],
        "selected_clara_workflow": "clara:advisory-case-director",
        "validation_profile": {"review_dimensions": dimensions, "format_checks": []},
        "validation_scope": {
            "coverage": "all_material_content",
            "included_sections": ["Entire short memo or action list"],
            "excluded_sections": [],
            "limitations": [
                "Supplied fictional notes only; no market survey or financial model."
            ],
        },
        "correction_policy": {
            "mode": "separate_artifact",
            "preserve_original": True,
            "allowed": True,
            "approval_required_before_delivery": True,
        },
        "professional_judgement_policy": {
            "owner": "Owner and consulting professional",
            "model_role": "Assess the supplied evidence and propose bounded advice; do not authorize implementation.",
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
            "instructions": [
                "Read the current own-product workflow.",
                "Preserve every supplied fact and limitation, including any revised assignment and vehicle update.",
                "No external activity or professional approval is authorized by this teaching fixture.",
            ],
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


@pytest.mark.parametrize("language", ["it", "en", "fr", "de", "es"])
@pytest.mark.parametrize("phase", ["demo", "practice"])
def test_planner_kit_packages_current_source_bound_assignment(
    tmp_path, monkeypatch, language, phase
):
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


def _memo_review(inventory, language, *, updated):
    """Model-authored assessment of the complete short, fictional memo."""
    source_refs = ["source-0001", "source-0002"] + (["source-0003"] if updated else [])
    vehicle = (
        "The new owner note explicitly withdraws vehicle availability. A possible loan is not agreed."
        if updated
        else "The vehicle note supports Wednesday appointments only; it does not establish a daily service."
    )
    judgments = {
        "contract_conformance": (
            "partially_conforms",
            "The memo addresses collection but omits the requested comparison with a limited pilot.",
        ),
        "factual_source_support": (
            "contradicted",
            "The customer notes contain conditional interest and a preference for self-delivery, with no bookings or agreed price. "
            + vehicle,
        ),
        "calculations_data_provenance": (
            "not_applicable",
            "This short qualitative memo contains no calculated figures or financial forecast.",
        ),
        "reasoning_assumptions": (
            "does_not_conform",
            "Interest from informal conversations does not establish demand or justify a daily launch.",
        ),
        "contradictions_missing_evidence": (
            "does_not_conform",
            "Price, costs, route and actual booking interest remain missing. "
            + vehicle,
        ),
        "recommendation_evidence_decision_fit": (
            "does_not_conform",
            "The supplied evidence does not justify immediate daily launch; compare a conditional pilot and its prerequisites.",
        ),
        "professional_judgement_boundaries": (
            "judgment_required",
            "The owner and consulting professional must review the corrected advice; no implementation approval exists.",
        ),
        "correction_needs": (
            "does_not_conform",
            "Revise the comparison, demand claim and vehicle conditions in a separate artifact, then review it.",
        ),
        "residual_uncertainty": (
            "partially_conforms",
            "The memo mentions price, route and costs but does not explain how the gaps limit its recommendation.",
        ),
        "delivery_readiness": (
            "does_not_conform",
            "The memo is not ready for decision use until the unsupported recommendation and claims are corrected.",
        ),
    }
    dimensions = {
        key: {
            "status": status,
            "analysis": analysis,
            "evidence_refs": source_refs,
            "issues": [] if status == "not_applicable" else [analysis],
            "correction_status": (
                "not_needed" if status == "not_applicable" else "proposed"
            ),
            "professional_review_required": key == "professional_judgement_boundaries",
        }
        for key, (status, analysis) in judgments.items()
    }
    declared = [
        (
            "launch",
            "Launch the daily service immediately.",
            "unsupported",
            "gap",
            judgments["recommendation_evidence_decision_fit"][1],
        ),
        (
            "demand",
            "Interviewed customers confirmed usage and demand is established.",
            "contradicted",
            "gap",
            judgments["reasoning_assumptions"][1],
        ),
        (
            "vehicle",
            "The shop vehicle enables collections to be arranged.",
            "contradicted" if updated else "partial",
            "gap",
            vehicle,
        ),
        (
            "preconditions",
            "Price, route and costs still need defining before launch.",
            "adequate",
            "sound",
            "The owner notes and assignment explicitly retain these gaps, but they do not support launch before verification.",
        ),
    ]
    claims = [
        {
            "id": key,
            "statement": statement,
            "deliverable_locations": [
                (
                    "Proposal, first paragraph"
                    if key != "preconditions"
                    else "Proposal, second paragraph"
                )
            ],
            "evidence_ids": source_refs,
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
                "analysis": "The supplied fictional sources are complete for this bounded comparison; no public factual claim needs an external recheck.",
            },
            "resolution": {
                "status": "no_change" if key == "preconditions" else "pending",
                "explanation": explanation,
            },
        }
        for key, statement, support, reasoning, explanation in declared
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
            "reviewed_sections": [
                "Entire short memo, including its proposed launch and stated preconditions"
            ],
            "omitted_sections": [],
            "considered_unit_ids": ["unit-0001"],
            "omitted_unit_ids": [],
            "unit_assessments": [
                {
                    "unit_id": "unit-0001",
                    "status": "reviewed_material_claims",
                    "material_claim_ids": [],
                    "untracked_claim_ids": [item[0] for item in declared],
                    "analysis": "Reviewed the full memo. Its final teaching disclaimer describes the supplied document, not evidence for the recommendation.",
                }
            ],
            "limitations": ["Original drafting history is unavailable."],
            "analysis": "All substantive passages were compared with the assignment and notes.",
        },
        "lineage_review": {
            "provenance_mode": "matched_support",
            "selection_method": "model_led_claim_chain_review",
            "reviewed_claim_ids": [],
            "chain_assessments": [],
            "untracked_material_claims": claims,
            "limitations": [
                "This is reconstructed support, not original generation provenance."
            ],
            "analysis": "The complete short external memo was reviewed against the selected fictional sources.",
        },
        "dimension_reviews": dimensions,
        "findings": [
            {
                "id": "launch-not-supported",
                "dimension": "recommendation_evidence_decision_fit",
                "finding": judgments["recommendation_evidence_decision_fit"][1],
                "status": "does_not_conform",
                "evidence_refs": source_refs,
                "correction_action": "Compare the requested alternatives, qualify customer interest and preserve actual vehicle conditions.",
                "correction_status": "proposed",
                "professional_review_required": True,
            }
        ],
        "format_specific_checks": [],
        "correction": {
            "status": "required",
            "summary": "A separate correction and new review are needed; neither was requested as an automatic approval.",
            "corrected_artifact": "",
            "corrected_artifact_sha256": "",
            "corrected_inventory_sha256": "",
            "corrected_review_sha256": "",
            "unresolved_changes": [
                "Revise the launch recommendation, demand claim and vehicle conditions."
            ],
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
            "analysis": judgments["delivery_readiness"][1],
            "residual_uncertainties": [
                "Prices, route, costs, actual bookings and vehicle arrangements remain unverified."
            ],
            "professional_review_items": [
                "Review the revised advice and decide whether to arrange a pilot."
            ],
        },
        "delivery_readiness": {
            "status": "not_ready",
            "conditions": [
                "Correct the memo separately and review the correction before decision use."
            ],
        },
    }


@pytest.mark.parametrize("language", ["it", "en", "fr", "de", "es"])
@pytest.mark.parametrize("phase", ["demo", "practice"])
def test_validator_kit_produces_source_bound_review_without_approval(
    tmp_path, monkeypatch, language, phase
):
    files = _kit(
        tmp_path, monkeypatch, "advisory-deliverable-validator", language, phase
    )
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
    evidence = []
    sources = []
    for key, copied in registered.items():
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
                "recorded_at": "2026-09-14T08:00:00+00:00",
                "recorded_by": "clara:advisory-case-director",
                "capture_status": "captured",
                "source": {
                    "material_ids": [copied.registered_material["id"]],
                    "url": "",
                    "locator": "Complete short fictional note",
                    "artifact_refs": [artifact],
                },
                "observation": path.read_text(encoding="utf-8").strip(),
                "scope": "The supplied fictional note only.",
                "limitations": [
                    "Statements in these teaching notes are not independently verified external facts."
                ],
                "verification": {
                    "status": "identity_verified",
                    "checked_at": "2026-09-14T08:00:00+00:00",
                    "method": "Read the exact source and retained its hash.",
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
        "recorded_at": "2026-09-14T08:00:00+00:00",
        "recorded_by": "clara:advisory-case-director",
        "provenance": {
            "workflow": "clara:advisory-case-director",
            "step": phase,
            "artifact": "",
            "locator": "Current assessment",
        },
        "evidence_links": [
            {
                "evidence_id": item["id"],
                "relationship": "supports",
                "analysis": "The source defines the assignment or the operating and customer limits used in this conditional assessment.",
                "proves": "What was supplied or stated within this fictional case.",
                "does_not_prove": "Demand, implementation readiness or professional approval.",
            }
            for item in evidence
        ],
        "dependency": {
            "mode": "all_of" if update else "none",
            "claim_ids": ["cl-initial"] if update else [],
            "derivation_type": "reasoning",
            "explanation": (
                "Reassess the prior conditional view with the new vehicle information."
                if update
                else "Compare the supplied statements and operating limits with the requested alternatives."
            ),
            "calculation_evidence_id": "",
        },
        "decision_use": "direct",
        "uncertainty": [
            "Actual bookings, route, price, costs and vehicle arrangements remain unverified."
        ],
        "professional_judgement_required": True,
        "appearances": [],
        "state": "active",
        "supersedes_claim_id": "",
    }
    return {
        "schema_version": "1.0",
        "return_id": "return-" + phase,
        "return_type": "analysis_branch",
        "branch": {
            "workflow": "clara:advisory-case-director",
            "question_id": "",
            "question": "What should the owner do next given the currently supplied evidence?",
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
                "question": (
                    "What transport arrangement can actually support a pilot?"
                    if update
                    else "What price, route, costs and booking interest would support a pilot?"
                ),
                "why_it_matters": "The owner needs these prerequisites before implementation.",
                "source_entry_ids": [],
                "source_judgement_indexes": [],
            }
        ],
        "validation_binding": None,
    }


@pytest.mark.parametrize("language", ["it", "en", "fr", "de", "es"])
def test_case_director_kit_updates_actual_case_and_preserves_workpaper_history(
    tmp_path, monkeypatch, language
):
    files = _kit(tmp_path, monkeypatch, "advisory-case-director", language, "practice")
    monkeypatch.syspath_prepend(str(CLARA / "scripts"))
    core = _load(CLARA / "scripts/advisor_case_core.py", "kit_advisory_case_core")
    case = tmp_path / "case"
    core.initialize_case(
        case,
        client="Ciclo Arco — fictional kit",
        project="Collection pilot",
        objective="Assess collection options from the supplied notes.",
        audience="Owner",
        output_language=language,
    )
    registered = {
        key: core.copy_case_file(case, files[key], kind="source", register=True)
        for key in ("assignment", "notes")
    }
    first = _case_return(case, registered, update=False, language=language)
    core.record_case_direction_return(case, first)
    staged = tmp_path / "workpaper-draft.md"
    staged.write_text(WORKPAPERS[language][0], encoding="utf-8")
    baseline = core.commit_advisory_workpaper(
        case,
        staged,
        referenced_claim_ids=["cl-initial"],
        change_summary="Initial assessment from the supplied assignment and notes.",
    )
    initial_bytes = (case / "advisory_workpaper.md").read_bytes()
    update = core.copy_case_file(case, files["update"], kind="source", register=True)
    core.record_case_direction_return(
        case, _case_return(case, {"update": update}, update=True, language=language)
    )
    staged.write_text(WORKPAPERS[language][1], encoding="utf-8")
    current = core.commit_advisory_workpaper(
        case,
        staged,
        referenced_claim_ids=["cl-update"],
        change_summary="Vehicle availability changed; resolve transport before scheduling a pilot.",
    )
    assert core.validate_case_workspace(case) == []
    assert current["prior_workpaper"]["sha256"] == baseline["workpaper"]["sha256"]
    assert (
        case / current["prior_workpaper"]["history_path"]
    ).read_bytes() == initial_bytes
    assert sorted(current["lineage"]["referenced_evidence_ids"]) == [
        "ev-assignment",
        "ev-notes",
        "ev-update",
    ]
    assert (case / "advisory_workpaper.md").read_text(encoding="utf-8") == WORKPAPERS[
        language
    ][1]
    assert (case / "advisory_evidence_map.md").is_file()
