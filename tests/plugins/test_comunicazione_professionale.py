from __future__ import annotations

import hashlib
import html as html_lib
import importlib
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest
from PIL import Image
from pypdf import PdfReader

ROOT = Path(__file__).resolve().parents[2]
PLUGIN = ROOT / "plugins" / "comunicazione-professionale"
SCRIPTS = PLUGIN / "scripts"


def _write_json(path: Path, payload: dict[str, object]) -> Path:
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def _run_result(script: str, *arguments: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(SCRIPTS / script), *arguments],
        cwd=PLUGIN,
        check=False,
        capture_output=True,
        text=True,
    )


def _run(script: str, *arguments: str) -> None:
    completed = _run_result(script, *arguments)
    assert completed.returncode == 0, completed.stderr or completed.stdout


def _routes() -> dict[str, dict[str, object]]:
    return {
        "public_research": {"selected": False},
        "history_connector": {"selected": False},
        "creative_production": {"selected": False},
        "send_or_publish": {"selected": False},
    }


def _brand() -> dict[str, str]:
    return {
        "studio_name": "Studio Aurora",
        "primary_color": "#002060",
        "accent_color": "#00B0F0",
        "background_color": "#FFFFFF",
        "text_color": "#171816",
        "contact_line": "studioaurora.example · Milano",
    }


def _profile_paths(value: object, prefix: str) -> list[str]:
    if not isinstance(value, dict):
        return [prefix]
    paths: list[str] = []
    for key, child in value.items():
        child_prefix = f"{prefix}.{key}" if prefix else key
        paths.extend(_profile_paths(child, child_prefix))
    return paths


def _profile() -> dict[str, object]:
    profile: dict[str, object] = {
        "derived_from_history_ids": ["HIST-001"],
        "voice": {
            "audience_stance": "Competente, diretto e rispettoso del tempo del cliente.",
            "rhythm": "Periodi brevi alternati a passaggi tecnici spiegati.",
            "technical_density": "Terminologia precisa con conseguenze operative esplicite.",
            "formality": "Professionale e sobria, senza formule promozionali.",
            "openings": "Apre dal cambiamento concreto e dal destinatario interessato.",
            "closings": "Chiude sui passi da valutare con lo studio.",
            "formatting": "Titoli informativi, sezioni numerate e liste brevi.",
            "avoid": ["urgenza artificiale", "claim assoluti", "emoji decorative"],
        },
        "document": {
            "page_size": "A4",
            "font_family": "Instrument Sans",
            "layout": {
                "left_margin_mm": 20,
                "right_margin_mm": 20,
                "top_margin_mm": 34,
                "bottom_margin_mm": 19,
                "logo_width_mm": 45,
                "logo_height_mm": 16,
                "contact_rail_width_mm": 38,
                "body_font_size_pt": 9.6,
                "body_leading_pt": 13.4,
                "subject_font_size_pt": 13,
                "heading_font_size_pt": 10.2,
                "rule_width_pt": 0.8,
            },
            "recipient_pattern": "Gentili Clienti",
            "circular_label": "CIRCOLARE",
            "numbering_pattern": "{number}/{year}",
            "date_pattern": "Milano, {date}",
            "subject_prefix": "OGGETTO:",
            "section_style": "numbered_uppercase",
            "use_contact_rail": True,
            "contact_rail_lines": [
                "Studio Aurora",
                "Dottori Commercialisti",
                "studioaurora.example",
                "Milano",
            ],
            "footer_pattern": "Studio Aurora · pag. {page}",
            "closing": "Lo Studio resta a disposizione per gli approfondimenti del caso.",
            "signature_lines": ["Studio Aurora", "Dottori Commercialisti"],
        },
        "email": {
            "subject_pattern": "Studio Aurora | {subject}",
            "salutation": "Gentile Cliente,",
            "closing": "Restiamo a disposizione.",
            "signature_lines": ["Studio Aurora", "Dottori Commercialisti"],
            "attachment_note": "In allegato trova la circolare di approfondimento.",
        },
        "website": {
            "byline_pattern": "A cura di {studio}",
            "date_pattern": "{date}",
            "heading_style": "editorial",
            "source_heading": "Fonti",
            "cta": "Contattate lo Studio per verificare la situazione specifica.",
            "show_update_date": True,
        },
        "social": {
            "preferred_format": "portrait_carousel",
            "opening_style": "Un fatto concreto, senza allarmismo.",
            "closing_style": "Invito a verificare l'applicabilità con il professionista.",
            "hashtags": ["#fisco", "#imprese"],
            "show_source_note": True,
            "carousel_identity_placement": "close_only",
        },
    }
    profile["field_provenance"] = [
        {
            "field_paths": [
                *_profile_paths(profile["voice"], "voice"),
                *_profile_paths(profile["document"], "document"),
            ],
            "basis": "observed_history",
            "history_ids": ["HIST-001"],
            "analysis": "La circolare selezionata mostra direttamente tono, gerarchia documentale e convenzioni tipografiche.",
        },
        {
            "field_paths": [
                *_profile_paths(profile["email"], "email"),
                *_profile_paths(profile["website"], "website"),
                *_profile_paths(profile["social"], "social"),
            ],
            "basis": "vera_default_proposal",
            "history_ids": [],
            "analysis": "Questi canali non sono osservabili nella storia selezionata e restano proposte Vera da adottare solo con approvazione professionale.",
        },
    ]
    return profile


def _new_studio_profile() -> dict[str, object]:
    """Build a first-run profile that makes no history-derived claim."""

    profile = _clone(_profile())
    profile["derived_from_history_ids"] = []
    profile["field_provenance"] = [
        {
            "field_paths": [
                *_profile_paths(profile["voice"], "voice"),
                *_profile_paths(profile["document"], "document"),
                *_profile_paths(profile["email"], "email"),
                *_profile_paths(profile["website"], "website"),
                *_profile_paths(profile["social"], "social"),
            ],
            "basis": "vera_default_proposal",
            "history_ids": [],
            "analysis": "Il nuovo Studio non ha esempi selezionati: tutte le convenzioni restano proposte Vera da approvare o correggere.",
        }
    ]
    return profile


def _publish_contribution() -> dict[str, object]:
    claim_ids = ["CLAIM-001"]
    source_ids = ["SRC-001"]
    return {
        "schema_version": 1,
        "run_id": "norma-2026-001",
        "recommendation": "publish",
        "recommendation_reason": "La misura introduce una data operativa vicina e richiede una verifica concreta da parte delle imprese interessate.",
        "editorial_value": {
            "reason_now": "È disponibile il provvedimento ufficiale con decorrenza definita.",
            "audience_value": "Le imprese possono capire se devono attivare una verifica interna.",
            "distinct_angle": "La comunicazione separa obbligo generale e verifica del caso concreto.",
            "practical_use": "Indica documenti e decisioni da preparare prima della decorrenza.",
            "source_specific_information": "La decorrenza e il perimetro derivano dal provvedimento ufficiale selezionato.",
            "decision_enabled": "Consente di decidere se avviare una verifica documentale con lo Studio.",
            "decision_limit": "Non conclude l'applicabilità e non sostituisce la verifica della posizione concreta.",
            "banality_check": "Il contenuto non si limita a raccomandare prudenza, ma lega data, perimetro e documenti alla fonte.",
            "repetition_check": "Gli esempi selezionati non trattano questa misura né questa scadenza.",
            "publication_judgment": "Il beneficio informativo supera il rischio di ripetizione, con caveat espliciti.",
        },
        "studio_profile_proposal": _profile(),
        "source_assessments": [
            {
                "source_id": "SRC-001",
                "semantic_role": "controlling",
                "authority_assessment": "Provvedimento ufficiale che definisce misura e decorrenza.",
                "limitations": "L'applicabilità resta da verificare sulla posizione concreta.",
            },
            {
                "source_id": "HIST-001",
                "semantic_role": "style_only",
                "authority_assessment": "Esempio approvato utile solo per voce e impaginazione.",
                "limitations": "Non è una fonte normativa e non supporta i claim.",
            },
        ],
        "claims": [
            {
                "id": "CLAIM-001",
                "statement": "La misura entra nella fase operativa dal 30 settembre 2026 per i soggetti rientranti nel perimetro.",
                "source_ids": source_ids,
                "temporal_qualification": "Quadro verificato alla data del 8 agosto 2026.",
                "uncertainty": "Il perimetro del singolo destinatario richiede verifica.",
                "professional_judgment": "Il commercialista conferma l'applicabilità al cliente.",
            }
        ],
        "master_brief": {
            "what_changed": "Il provvedimento definisce l'avvio operativo della nuova misura.",
            "who_may_be_affected": "Imprese che rientrano nel perimetro soggettivo e oggettivo.",
            "effective_dates": ["30 settembre 2026"],
            "practical_implications": [
                "Verificare il perimetro",
                "Raccogliere la documentazione",
            ],
            "actions": ["Confrontarsi con lo Studio prima della decorrenza"],
            "caveats": ["La comunicazione non sostituisce la verifica individuale"],
        },
        "channel_drafts": [
            {
                "channel": "client_email",
                "title": "Nuova misura: cosa verificare",
                "subject": "Nuova misura: cosa verificare entro settembre",
                "body": "Il provvedimento entra nella fase operativa dal 30 settembre 2026. Prima di assumere iniziative occorre verificare se la misura riguarda la vostra impresa.",
                "claim_ids": claim_ids,
                "audience_note": "Clienti impresa potenzialmente interessati.",
                "public_source_notes": [
                    {
                        "source_ids": source_ids,
                        "text": "Agenzia delle Entrate — Provvedimento n. 12345/2026 dell'8 agosto 2026",
                    }
                ],
                "sections": [],
            },
            {
                "channel": "client_circular",
                "title": "Nuova misura: verifiche operative",
                "subject": "Nuova misura e verifiche operative",
                "body": "Sintesi tecnica della nuova misura e delle verifiche richieste.",
                "claim_ids": claim_ids,
                "audience_note": "Clienti impresa potenzialmente interessati.",
                "circular_number": "08/2026",
                "recipient_line": "Gentili Clienti",
                "date_line": "Milano, 8 agosto 2026",
                "public_source_notes": [
                    {
                        "source_ids": source_ids,
                        "text": "Agenzia delle Entrate — Provvedimento n. 12345/2026 dell'8 agosto 2026",
                    }
                ],
                "sections": [
                    {
                        "heading": "Cosa cambia",
                        "body": "Il provvedimento definisce l'avvio operativo dal 30 settembre 2026.",
                        "bullets": [],
                    },
                    {
                        "heading": "Chi deve verificare",
                        "body": "La verifica riguarda imprese nel perimetro, da confermare caso per caso.",
                        "bullets": [
                            "Perimetro soggettivo",
                            "Documentazione disponibile",
                        ],
                    },
                    {
                        "heading": "Cosa fare",
                        "body": "Raccogliere i documenti e confrontarsi con lo Studio prima della decorrenza.",
                        "bullets": ["Non assumere automaticamente l'applicabilità"],
                    },
                ],
            },
            {
                "channel": "linkedin",
                "title": "Una nuova data non basta: serve capire a chi si applica",
                "body": "Dal 30 settembre 2026 la misura entra nella fase operativa. Il punto utile non è creare allarme, ma verificare perimetro e documenti. Fonte ufficiale; applicabilità da valutare caso per caso.",
                "claim_ids": claim_ids,
                "audience_note": "Imprese e professionisti.",
                "public_source_notes": [
                    {
                        "source_ids": source_ids,
                        "text": "Agenzia delle Entrate — Provvedimento n. 12345/2026 dell'8 agosto 2026",
                    }
                ],
                "sections": [],
            },
            {
                "channel": "website_article",
                "title": "Nuova misura: dalla data alla verifica concreta",
                "body": "Il provvedimento ufficiale porta la misura nella fase operativa.",
                "claim_ids": claim_ids,
                "audience_note": "Imprese che cercano un primo orientamento.",
                "public_source_notes": [
                    {
                        "source_ids": source_ids,
                        "text": "Agenzia delle Entrate — Provvedimento n. 12345/2026 dell'8 agosto 2026",
                    }
                ],
                "sections": [
                    {
                        "heading": "Cosa cambia",
                        "body": "Dal 30 settembre 2026 la misura entra nella fase operativa.",
                        "bullets": [],
                    },
                    {
                        "heading": "La verifica utile",
                        "body": "Perimetro e applicabilità vanno confermati sulla posizione concreta.",
                        "bullets": ["Soggetto", "Attività", "Documentazione"],
                    },
                ],
            },
        ],
        "visual_story": {
            "decision": "render",
            "decision_reason": "Il visuale organizza perimetro e preparazione documentale oltre la sintesi del post.",
            "incremental_value": "Aggiunge una sequenza di verifica e un perimetro operativo che il post non dettaglia.",
            "title": "Nuova misura, verifica concreta",
            "slides": [
                {
                    "kind": "cover",
                    "layout_variant": "editorial_cover",
                    "eyebrow": "Aggiornamento professionale",
                    "title": "Una nuova data. Prima, una verifica concreta.",
                    "body": "La misura entra nella fase operativa il 30 settembre 2026.",
                    "bullets": [],
                    "highlight": "30.09.2026",
                    "source_ids": source_ids,
                    "source_note": "Fonte: Agenzia delle Entrate — Provvedimento n. 12345/2026 dell'8 agosto 2026",
                    "reader_use": "Collocare la decorrenza prima di avviare la verifica operativa.",
                    "relationship_to_post": "adds_source_detail",
                },
                {
                    "kind": "audience",
                    "layout_variant": "scope_register",
                    "eyebrow": "Perimetro",
                    "title": "Non riguarda automaticamente ogni impresa",
                    "body": "Soggetto, attività e documentazione determinano il percorso di verifica.",
                    "bullets": [
                        "Confermare il perimetro",
                        "Evitare conclusioni standard",
                    ],
                    "highlight": "",
                    "source_ids": source_ids,
                    "source_note": "Fonte: Agenzia delle Entrate — Provvedimento n. 12345/2026 dell'8 agosto 2026",
                    "reader_use": "Separare il perimetro generale dalla verifica della singola impresa.",
                    "relationship_to_post": "adds_decision_tool",
                },
                {
                    "kind": "action",
                    "layout_variant": "evidence_dossier",
                    "eyebrow": "Passo utile",
                    "title": "Preparare i documenti, poi decidere",
                    "body": "Lo Studio può verificare l'applicabilità prima della decorrenza.",
                    "bullets": ["Raccogliere le evidenze", "Valutare il caso concreto"],
                    "highlight": "",
                    "source_ids": source_ids,
                    "source_note": "Fonte: Agenzia delle Entrate — Provvedimento n. 12345/2026 dell'8 agosto 2026",
                    "reader_use": "Preparare i documenti necessari per il confronto professionale.",
                    "relationship_to_post": "adds_sequence",
                },
            ],
        },
    }


def _clone(payload: dict[str, object]) -> dict[str, object]:
    return json.loads(json.dumps(payload))


def _canonical_digest(payload: dict[str, object]) -> str:
    return hashlib.sha256(
        json.dumps(
            payload,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    ).hexdigest()


def _prompt_digest(name: str) -> str:
    return hashlib.sha256((PLUGIN / "prompts" / name).read_bytes()).hexdigest()


def _history_pseudonymization(run_dir: Path) -> dict[str, object]:
    intake = json.loads((run_dir / "run_intake.json").read_text(encoding="utf-8"))
    source_register = json.loads(
        (run_dir / "source_register.json").read_text(encoding="utf-8")
    )
    packet = json.loads(
        (run_dir / "history_pseudonymization_packet.json").read_text(encoding="utf-8")
    )
    semantic_values = {
        "Mario Rossi": ("person", "[PERSON_1]"),
        "Alfa S.r.l.": ("organization", "[ORGANIZATION_1]"),
        "Studio Aurora": ("organization", "[ORGANIZATION_2]"),
    }
    documents: list[dict[str, object]] = []
    mapping_by_value: dict[str, dict[str, object]] = {}
    packet_by_id = {row["id"]: row for row in packet["history_documents"]}
    for row in source_register["history"]:
        text = Path(packet_by_id[row["id"]]["path"]).read_text(encoding="utf-8")
        for original, (category, placeholder) in semantic_values.items():
            if original not in text:
                continue
            text = text.replace(original, placeholder)
            mapping = mapping_by_value.setdefault(
                original,
                {
                    "category": category,
                    "original_value": original,
                    "placeholder": placeholder,
                    "history_ids": [],
                },
            )
            mapping["history_ids"].append(row["id"])
        documents.append(
            {
                "history_id": row["id"],
                "channel": row["channel"],
                "pseudonymized_document": text,
                "transformations_summary": "Pseudonimizzati i riferimenti contestuali mantenendo il documento completo.",
                "residual_identification_risk": "Resta il rischio semantico residuo proprio della pseudonimizzazione.",
            }
        )
    return {
        "schema_version": 1,
        "run_id": intake["run_id"],
        "input_digest": intake["input_digest"],
        "purpose": "complete_document_pseudonymization_for_studio_voice_and_format_learning",
        "history_items": documents,
        "identity_mapping": list(mapping_by_value.values()),
        "pseudonymization_assessment": {
            "mechanical_placeholders_preserved": True,
            "contextual_direct_identifiers_pseudonymized": True,
            "indirect_identifiers_generalized": True,
            "identifying_case_facts_generalized": True,
            "complete_document_structure_preserved": True,
            "technical_content_excluded_as_authority": True,
            "identity_mapping_separated_from_documents": True,
            "ready_for_downstream_use": True,
            "residual_risk": "I documenti restano pseudonimizzati, non anonimi.",
        },
        "limitations": [
            "Il record descrive lo stile osservato e non dimostra correttezza tecnica o successo editoriale."
        ],
    }


def _record_history_pseudonymization(run_dir: Path, tmp_path: Path) -> Path | None:
    source_register = json.loads(
        (run_dir / "source_register.json").read_text(encoding="utf-8")
    )
    if not source_register["history"]:
        return None
    pseudonymization = _write_json(
        tmp_path / f"{run_dir.name}-history-pseudonymization.json",
        _history_pseudonymization(run_dir),
    )
    _run(
        "record_history_pseudonymization.py",
        "--run-dir",
        str(run_dir),
        "--pseudonymization",
        str(pseudonymization),
        "--provider",
        "test-provider",
        "--model",
        "test-history-model",
        "--session-id",
        "test-history-session-001",
        "--recorded-by",
        "test-operator",
    )
    return run_dir / "history_pseudonymization_record.json"


def _answer_contract(
    contribution: dict[str, object],
    *,
    audience: str = "Clienti impresa potenzialmente interessati",
    output_language: str = "it",
    jurisdiction: str = "Italia",
) -> dict[str, object]:
    contract: dict[str, object] = {
        "schema_version": 1,
        "run_id": contribution["run_id"],
        "question_domain": "tax",
        "document_type": "professional_communication_package",
        "purpose": "Decidere se la misura merita comunicazione e preparare contenuti professionali verificabili.",
        "audience": audience,
        "output_language": output_language,
        "jurisdiction": jurisdiction,
        "jurisdiction_status": "confirmed",
        "generation_route": "codex_direct",
        "evidence_display": "source_record_only",
        "validation_profile": "source_identity_support_reasoning_and_judgment",
        "validation_scope": "all_material_claims",
        "correction_policy": "correct_when_supported",
        "judgment_policy": "flag_for_professional_review",
        "generation_instructions": {
            "source_hierarchy": [
                "Provvedimento ufficiale selezionato prima di ogni commento secondario"
            ],
            "preserve": [
                "Date, perimetro, eccezioni, modalità e limiti del giudizio professionale"
            ],
            "must_distinguish": [
                "Orientamento generale e applicabilità alla singola impresa"
            ],
            "prohibited": [
                "Autorità inventate, urgenza artificiale e conclusioni non supportate"
            ],
        },
    }
    contract["contract_digest"] = _canonical_digest(contract)
    return contract


def _claim_assurance(
    contribution: dict[str, object], answer_contract: dict[str, object]
) -> dict[str, object]:
    claim_rows: list[dict[str, object]] = []
    for claim in contribution["claims"]:
        claim_rows.append(
            {
                "claim_id": claim["id"],
                "source_checks": [
                    {
                        "source_id": source_id,
                        "identity_status": "matches_registered_source",
                        "identity_analysis": "Lo snapshot registrato corrisponde al provvedimento ufficiale dichiarato nel run.",
                        "support_analysis": "La fonte registrata contiene la decorrenza e il perimetro qualificato riportati nel claim.",
                    }
                    for source_id in claim["source_ids"]
                ],
                "support": {
                    "status": "supported",
                    "analysis": "Il claim conserva data, modalità e limite di applicabilità presenti nella fonte ufficiale registrata.",
                },
                "reasoning": {
                    "status": "sound",
                    "analysis": "La comunicazione deriva dalla decorrenza verificata soltanto la necessità di una verifica, non l'applicabilità automatica.",
                    "supported_premises": [
                        "La fonte registra la decorrenza operativa."
                    ],
                    "missing_premises": [],
                },
                "professional_judgment": {
                    "status": "professional_judgment_required",
                    "analysis": "L'applicabilità alla singola impresa dipende da fatti che il commercialista deve verificare.",
                    "professional_review_items": [
                        "Confermare il perimetro della singola impresa."
                    ],
                },
                "issues": [
                    {
                        "type": "judgment_dependent",
                        "explanation": "L'applicabilità individuale non può essere conclusa dalla comunicazione generale.",
                        "treatment": "professional_review",
                    }
                ],
                "disposition": "retain",
                "reviewer_action": "accept",
            }
        )
    outcome = (
        "no_publication_supported"
        if contribution["recommendation"] == "no_publish"
        else "ready_for_professional_review"
    )
    return {
        "schema_version": 1,
        "run_id": contribution["run_id"],
        "assessed_contribution_digest": _canonical_digest(contribution),
        "answer_contract_digest": answer_contract["contract_digest"],
        "assessment_protocol": {
            "method": "isolated_host_session_exact_artifact_review",
            "assessor_session_id": "test-claim-session-001",
            "assessment_template_version": "professional-communication-claim-assurance-v2",
            "template_sha256": _prompt_digest("claim-assurance-v2.md"),
            "generation_transcript_seen": False,
            "completed_at": "2026-08-08T11:30:00+00:00",
        },
        "validation_method": "model_led_source_support_reasoning_and_judgment_review",
        "coverage_review": {
            "scope": "all_material_claims",
            "reviewed_claim_ids": [claim["id"] for claim in contribution["claims"]],
            "omitted_claim_ids": [],
            "analysis": "L'intero contributo è stato letto e ogni claim materiale è stato selezionato per la verifica separata.",
        },
        "contract_review": {
            "purpose": {
                "status": "conforms",
                "analysis": "Il contributo risponde all'obiettivo editoriale registrato.",
            },
            "document_type": {
                "status": "conforms",
                "analysis": "Il contributo prepara un pacchetto di comunicazione professionale.",
            },
            "audience": {
                "status": "conforms",
                "analysis": "Il linguaggio e i limiti sono adatti ai clienti impresa indicati.",
            },
            "output_language": {
                "status": "conforms",
                "analysis": "La lingua del pacchetto corrisponde al contratto registrato.",
            },
            "jurisdiction": {
                "status": "conforms",
                "analysis": "La giurisdizione italiana resta esplicita e circoscritta.",
            },
            "source_hierarchy": {
                "status": "conforms",
                "analysis": "La fonte ufficiale selezionata precede ogni commento secondario.",
            },
            "preservation": {
                "status": "conforms",
                "analysis": "Date, modalità, perimetro e limiti sono conservati nel pacchetto.",
            },
            "required_distinctions": {
                "status": "conforms",
                "analysis": "Il contributo distingue orientamento generale e applicabilità individuale.",
            },
            "prohibited_content": {
                "status": "conforms",
                "analysis": "Non risultano autorità inventate, urgenza artificiale o conclusioni non supportate.",
            },
            "evidence_display": {
                "status": "conforms",
                "analysis": "Le fonti restano nel record tecnico e nelle note pubbliche previste.",
            },
            "validation_scope": {
                "status": "conforms",
                "analysis": "La revisione copre tutti i claim materiali una volta e nell'ordine.",
            },
            "correction_policy": {
                "status": "conforms",
                "analysis": "Ogni difetto correggibile deve essere corretto prima dell'accettazione.",
            },
            "judgment_policy": {
                "status": "conforms",
                "analysis": "L'applicabilità individuale resta assegnata alla revisione professionale.",
            },
            "reviewer_action": "accept",
        },
        "claims": claim_rows,
        "overall_assessment": {
            "outcome": outcome,
            "analysis": "Le affermazioni materiali risultano supportate e i limiti di applicabilità restano affidati alla revisione professionale.",
            "residual_uncertainties": [],
            "professional_review_items": (
                ["Confermare l'applicabilità alle singole imprese."]
                if claim_rows
                else []
            ),
        },
    }


def _editorial_assessment(
    contribution: dict[str, object],
    *,
    verdict: str = "ready",
    answer_contract: dict[str, object] | None = None,
) -> dict[str, object]:
    visual_story = contribution["visual_story"]
    visual_decision = visual_story["decision"]
    bound_answer_contract = answer_contract or _answer_contract(contribution)
    claim_assurance = _claim_assurance(contribution, bound_answer_contract)
    return {
        "schema_version": 1,
        "run_id": contribution["run_id"],
        "assessed_contribution_digest": _canonical_digest(contribution),
        "claim_assurance_digest": _canonical_digest(claim_assurance),
        "assessment_protocol": {
            "method": "blind_adversarial_exact_artifact_review",
            "assessor_session_id": "test-editorial-session-001",
            "assessment_template_version": "professional-communication-editorial-v4",
            "template_sha256": _prompt_digest("editorial-assessment-v4.md"),
            "generation_transcript_seen": False,
            "generator_prompt_reused": False,
            "comparison_class": "strong_practitioner_authored_publication",
            "completed_at": "2026-08-08T12:00:00+00:00",
        },
        "verdict": verdict,
        "interestingness_judgment": "La bozza collega una decorrenza ufficiale a una verifica concreta e non si limita a un richiamo generico alla prudenza.",
        "source_specific_value": "Data, perimetro e passaggi derivano dalla fonte ufficiale selezionata.",
        "public_evidence_readability": "La nota pubblica identifica l'autorità, il provvedimento e la data necessari a ritrovare la fonte, senza esporre identificatori interni.",
        "reader_payoff": "Il lettore ottiene una data verificata, il limite dell'informazione e un percorso concreto per preparare la verifica.",
        "expertise_beyond_summary": "La bozza distingue il fatto normativo dalla conclusione sul singolo caso e traduce questa distinzione in una sequenza professionale circoscritta.",
        "genericity_challenge": "Senza la fonte non sarebbe possibile indicare la decorrenza; senza il giudizio professionale mancherebbe il confine tra orientamento e applicabilità.",
        "counterfactual_value": "Senza questa comunicazione il destinatario non avrebbe nello stesso punto la data, il perimetro della verifica e il limite della conclusione preliminare.",
        "weakest_element": "La formula sul confronto con lo Studio è convenzionale; resta accettabile soltanto perché segue fatti e verifiche specifiche già esposte.",
        "practical_use": "Il destinatario può preparare documenti e una verifica circoscritta con lo Studio.",
        "professional_limit": "La bozza non conclude l'applicabilità e mantiene il giudizio sul caso al professionista.",
        "banality_risk": "Il rischio è controllato perché la comunicazione espone fatti specifici e un passo operativo delimitato.",
        "channel_assessments": [
            {
                "channel": draft["channel"],
                "verdict": "ready" if verdict == "ready" else "revise",
                "reader_payoff": f"Il canale {draft['channel']} porta la decorrenza e il limite professionale al suo pubblico specifico.",
                "weakest_point": "La chiusura resta convenzionale e non deve diventare il centro del messaggio.",
            }
            for draft in contribution["channel_drafts"]
        ],
        "visual_verdict": visual_decision,
        "visual_incremental_value": (
            visual_story["incremental_value"] if visual_decision == "render" else ""
        ),
        "slide_assessments": [
            {
                "slide_index": index,
                "verdict": (
                    "adds_structure"
                    if slide["kind"] in {"cover", "close"}
                    else "adds_information"
                ),
                "information_delta": slide["reader_use"],
                "reader_payoff": f"La slide rende utilizzabile questo passaggio: {slide['reader_use']}",
            }
            for index, slide in enumerate(visual_story["slides"], start=1)
        ],
        "required_changes": [] if verdict == "ready" else ["Rivedere l'angolo"],
    }


def _qualify_editorial_assessor(workspace: Path, tmp_path: Path) -> None:
    expectations = json.loads(
        (PLUGIN / "evals" / "editorial_quality_expected.json").read_text(
            encoding="utf-8"
        )
    )["expectations"]
    results = _write_json(
        tmp_path / "editorial-benchmark-results.json",
        {
            "schema_version": 1,
            "provider": "test-provider",
            "model": "test-editor-model",
            "assessment_template_version": "professional-communication-editorial-v4",
            "template_sha256": _prompt_digest("editorial-assessment-v4.md"),
            "assessor_session_id": "test-benchmark-session-001",
            "evaluated_at": "2026-08-08T11:00:00+00:00",
            "judgments": [
                {
                    "case_id": case["case_id"],
                    "verdict": case["expected_verdict"],
                    "analysis": "Il giudizio confronta valore specifico, utilità professionale e rischio di genericità con il benchmark richiesto.",
                }
                for case in expectations
            ],
        },
    )
    _run(
        "qualify_editorial_assessor.py",
        "--workspace",
        str(workspace),
        "--results",
        str(results),
        "--recorded-by",
        "test-operator",
    )


def _assurance_paths(
    tmp_path: Path,
    contribution: dict[str, object],
    *,
    answer_contract: dict[str, object] | None = None,
) -> tuple[Path, Path]:
    bound_answer_contract = answer_contract or _answer_contract(contribution)
    answer_path = _write_json(tmp_path / "answer-contract.json", bound_answer_contract)
    assurance_path = _write_json(
        tmp_path / "claim-assurance.json",
        _claim_assurance(contribution, bound_answer_contract),
    )
    return answer_path, assurance_path


def _recorded_publish_run(
    tmp_path: Path,
    *,
    channels: list[str],
    visual_requested: bool,
    contribution: dict[str, object] | None = None,
    brand: dict[str, str] | None = None,
    routes: dict[str, dict[str, object]] | None = None,
    language: str = "it",
    include_history: bool = True,
    studio_format_brief: str = "",
) -> tuple[Path, Path, dict[str, object]]:
    workspace = tmp_path / "studio-workspace"
    source = tmp_path / "official-source.txt"
    history = tmp_path / "approved-history.txt"
    source.write_text(
        "Provvedimento ufficiale. Decorrenza operativa: 30 settembre 2026.",
        encoding="utf-8",
    )
    history.write_text(
        "Gentili Clienti\nOGGETTO: Aggiornamento\n1 COSA CAMBIA\nStudio Aurora",
        encoding="utf-8",
    )
    prepared_contribution = _clone(contribution or _publish_contribution())
    if not include_history:
        prepared_contribution["studio_profile_proposal"] = _new_studio_profile()
        prepared_contribution["source_assessments"] = [
            row
            for row in prepared_contribution["source_assessments"]
            if row["source_id"] != "HIST-001"
        ]
    prepared_contribution["channel_drafts"] = [
        draft
        for draft in prepared_contribution["channel_drafts"]
        if draft["channel"] in channels
    ]
    if not visual_requested:
        prepared_contribution["visual_story"] = {
            "decision": "omit",
            "decision_reason": "Nessun visuale è richiesto per questo run e il testo resta autosufficiente.",
            "incremental_value": "",
            "title": "",
            "slides": [],
        }
    intake_payload: dict[str, object] = {
        "schema_version": 1,
        "run_id": prepared_contribution["run_id"],
        "reference_date": "2026-08-08",
        "language": language,
        "jurisdiction": "Italia",
        "objective": "Spiegare la misura senza assumere applicabilità automatica.",
        "audience": "Clienti impresa potenzialmente interessati",
        "studio_format_brief": studio_format_brief,
        "channels": channels,
        "visual_requested": visual_requested,
        "source_inputs": [
            {
                "id": "SRC-001",
                "path": str(source),
                "title": "Provvedimento ufficiale sulla misura",
                "authority_role": "primary",
                "public_url": "https://example.test/provvedimento-12345-2026",
            }
        ],
        "history_inputs": (
            [
                {
                    "id": "HIST-001",
                    "path": str(history),
                    "channel": "client_circular",
                }
            ]
            if include_history
            else []
        ),
        "brand_profile": brand or _brand(),
        "external_routes": routes or _routes(),
    }
    intake = _write_json(tmp_path / "intake.json", intake_payload)
    contribution_path = _write_json(
        tmp_path / "contribution.json", prepared_contribution
    )
    answer_contract = _answer_contract(
        prepared_contribution,
        output_language=language,
    )
    assessment_path = _write_json(
        tmp_path / "editorial-assessment.json",
        _editorial_assessment(
            prepared_contribution,
            answer_contract=answer_contract,
        ),
    )
    answer_path, assurance_path = _assurance_paths(
        tmp_path,
        prepared_contribution,
        answer_contract=answer_contract,
    )
    _run(
        "initialize_workspace.py",
        "--workspace",
        str(workspace),
        "--workspace-id",
        "studio-aurora",
        "--owner",
        "Studio Aurora",
        "--retention-owner",
        "Studio Aurora",
        "--confirmed-by-user",
    )
    _qualify_editorial_assessor(workspace, tmp_path)
    _run("prepare_run.py", "--workspace", str(workspace), "--intake", str(intake))
    run_dir = workspace / "runs" / str(prepared_contribution["run_id"])
    _record_history_pseudonymization(run_dir, tmp_path)
    _run(
        "record_contribution.py",
        "--run-dir",
        str(run_dir),
        "--contribution",
        str(contribution_path),
        "--answer-contract",
        str(answer_path),
        "--claim-assurance",
        str(assurance_path),
        "--editorial-assessment",
        str(assessment_path),
        "--provider",
        "test-provider",
        "--model",
        "test-model",
        "--template-version",
        "professional-communication-v3",
        "--generation-session-id",
        "test-generation-session-001",
        "--recorded-by",
        "test-operator",
        "--assessment-provider",
        "test-provider",
        "--assessment-model",
        "test-editor-model",
        "--claim-assessment-provider",
        "test-provider",
        "--claim-assessment-model",
        "test-claim-model",
    )
    return workspace, run_dir, prepared_contribution


def _accept_required_reviews(run_dir: Path) -> None:
    workbench = json.loads(
        (run_dir / "content_workbench.json").read_text(encoding="utf-8")
    )
    for scope in workbench["required_review_scopes"]:
        _run(
            "record_review.py",
            "--run-dir",
            str(run_dir),
            "--scope",
            scope,
            "--decision",
            "accepted",
            "--reviewer",
            "Dott.ssa Revisore",
            "--confirmed-by-user",
        )


def _accept_rendered_output(run_dir: Path) -> None:
    manifest = json.loads(
        (run_dir / "visual_manifest.json").read_text(encoding="utf-8")
    )
    slides = [
        output for output in manifest["outputs"] if output["kind"] == "carousel_slide"
    ]
    documents = [
        output
        for output in manifest["outputs"]
        if output["kind"] == "client_circular_pdf"
    ]
    assessment = _write_json(
        run_dir / "visual-assessment-input.json",
        {
            "schema_version": 1,
            "run_id": manifest["run_id"],
            "assessed_manifest_digest": manifest["manifest_digest"],
            "assessment_protocol": {
                "method": "isolated_host_session_exact_render_review",
                "assessor_session_id": "test-visual-release-session-001",
                "assessment_template_version": "professional-visual-editor-v2",
                "template_sha256": _prompt_digest("visual-assessment-v2.md"),
                "generation_transcript_seen": False,
                "editorial_transcript_seen": False,
                "completed_at": "2026-08-08T13:00:00+00:00",
            },
            "render_state": "accepted_semantics",
            "verdict": "ready",
            "post_comparison": "Le immagini aggiungono struttura e dettagli operativi oltre la bozza testuale selezionata per il canale.",
            "information_density": "Ogni slide mantiene un solo compito e una quantità di testo leggibile nel formato verticale previsto.",
            "source_readability": "Le note fonte sono pubbliche, leggibili e non espongono identificatori tecnici interni.",
            "identity_judgment": "L'identità dello Studio compare soltanto nelle posizioni previste dal profilo accettato.",
            "visual_quality": "Gerarchia, spaziatura, contrasto e dimensioni tipografiche risultano leggibili nelle immagini esatte.",
            "weakest_slide": "La chiusura è la slide meno informativa ma conserva un compito distinto e un limite professionale necessario.",
            "slide_assessments": [
                {
                    "slide_index": index,
                    "verdict": (
                        "supports_sequence"
                        if index in {1, len(slides)}
                        else "adds_value"
                    ),
                    "visible_judgment": "La slide svolge un compito distinto e resta leggibile nell'immagine esatta generata dal test.",
                    "required_change": "",
                }
                for index, _slide in enumerate(slides, start=1)
            ],
            "document_assessments": [
                {
                    "path": document["path"],
                    "assessed_page_count": document["layout_validation"]["page_count"],
                    "verdict": "ready",
                    "pagination_judgment": "Ogni pagina usa margini coerenti e mantiene sezioni, chiusura e numerazione in un ordine leggibile.",
                    "legibility_judgment": "Corpo, titoli, fonti, contatti e firma restano completi e leggibili nel PDF esatto.",
                    "identity_judgment": "Logo, contatti, piè di pagina e firma rispettano il profilo Studio accettato.",
                    "required_change": "",
                }
                for document in documents
            ],
            "required_changes": [],
        },
    )
    _run(
        "record_visual_assessment.py",
        "--run-dir",
        str(run_dir),
        "--assessment",
        str(assessment),
        "--provider",
        "test-provider",
        "--model",
        "test-visual-editor-model",
    )
    _run(
        "record_review.py",
        "--run-dir",
        str(run_dir),
        "--scope",
        "rendered_output",
        "--decision",
        "accepted",
        "--reviewer",
        "Dott.ssa Revisore",
        "--confirmed-by-user",
        "--quality-checklist-confirmed",
    )


def _accept_packaged_output(run_dir: Path) -> None:
    _run(
        "record_review.py",
        "--run-dir",
        str(run_dir),
        "--scope",
        "packaged_output",
        "--decision",
        "accepted",
        "--reviewer",
        "Dott.ssa Revisore",
        "--confirmed-by-user",
    )


def test_professional_communication_builds_studio_formatted_multichannel_package(
    tmp_path: Path,
) -> None:
    workspace = tmp_path / "studio-workspace"
    source = tmp_path / "official-source.txt"
    history = tmp_path / "approved-circular.txt"
    source.write_text(
        "Provvedimento ufficiale. Decorrenza operativa: 30 settembre 2026.",
        encoding="utf-8",
    )
    history.write_text(
        "Gentili Clienti\nOGGETTO: Aggiornamento\n1 COSA CAMBIA\nStudio Aurora",
        encoding="utf-8",
    )
    intake = _write_json(
        tmp_path / "intake.json",
        {
            "schema_version": 1,
            "run_id": "norma-2026-001",
            "reference_date": "2026-08-08",
            "language": "it",
            "jurisdiction": "Italia",
            "objective": "Spiegare la misura senza assumere che si applichi a ogni cliente.",
            "audience": "Clienti impresa potenzialmente interessati",
            "channels": [
                "client_email",
                "client_circular",
                "linkedin",
                "website_article",
            ],
            "visual_requested": True,
            "source_inputs": [
                {
                    "id": "SRC-001",
                    "path": str(source),
                    "title": "Provvedimento ufficiale sulla misura",
                    "authority_role": "primary",
                    "public_url": "https://example.test/provvedimento-12345-2026",
                    "published_at": "2026-08-01",
                }
            ],
            "history_inputs": [
                {"id": "HIST-001", "path": str(history), "channel": "client_circular"}
            ],
            "brand_profile": _brand(),
            "external_routes": _routes(),
        },
    )
    contribution_payload = _publish_contribution()
    contribution = _write_json(tmp_path / "contribution.json", contribution_payload)
    assessment = _write_json(
        tmp_path / "editorial-assessment.json",
        _editorial_assessment(contribution_payload),
    )
    answer_path, assurance_path = _assurance_paths(tmp_path, contribution_payload)

    _run(
        "initialize_workspace.py",
        "--workspace",
        str(workspace),
        "--workspace-id",
        "studio-aurora",
        "--owner",
        "Studio Aurora",
        "--retention-owner",
        "Studio Aurora",
        "--confirmed-by-user",
    )
    _qualify_editorial_assessor(workspace, tmp_path)
    _run("prepare_run.py", "--workspace", str(workspace), "--intake", str(intake))
    run_dir = workspace / "runs" / "norma-2026-001"
    task_packet = json.loads(
        (run_dir / "model_task_packet.json").read_text(encoding="utf-8")
    )
    assert task_packet["source_snapshots"][0]["public_url"] == (
        "https://example.test/provvedimento-12345-2026"
    )
    assert set(task_packet["artifact_schemas"]) == {
        "answer_contract",
        "claim_assurance",
        "editorial_assessment",
        "history_pseudonymization",
        "model_contribution",
        "visual_assessment",
    }
    assert task_packet["history_context"]["status"] == "preparation_required"
    assert task_packet["history_context"]["raw_history_paths_included"] is False
    assert "history_snapshots" not in task_packet
    blocked = _run_result(
        "record_contribution.py",
        "--run-dir",
        str(run_dir),
        "--contribution",
        str(contribution),
        "--answer-contract",
        str(answer_path),
        "--claim-assurance",
        str(assurance_path),
        "--editorial-assessment",
        str(assessment),
        "--provider",
        "test-provider",
        "--model",
        "test-model",
        "--template-version",
        "professional-communication-v3",
        "--generation-session-id",
        "test-generation-session-001",
        "--recorded-by",
        "test-operator",
        "--assessment-provider",
        "test-provider",
        "--assessment-model",
        "test-editor-model",
        "--claim-assessment-provider",
        "test-provider",
        "--claim-assessment-model",
        "test-claim-model",
    )
    assert blocked.returncode == 1
    assert "requires recorded pseudonymization" in blocked.stderr
    preparation_path = _record_history_pseudonymization(run_dir, tmp_path)
    assert preparation_path is not None
    assert preparation_path.exists()
    task_packet = json.loads(
        (run_dir / "model_task_packet.json").read_text(encoding="utf-8")
    )
    assert task_packet["history_context"]["status"] == "ready"
    assert task_packet["history_context"]["raw_history_paths_included"] is False
    assert task_packet["history_context"]["identity_mapping_included"] is False
    assert task_packet["history_context"]["record_digest"]
    pseudonymized_path = Path(
        task_packet["history_context"]["pseudonymized_documents"][0]["path"]
    )
    assert pseudonymized_path.is_file()
    assert "[ORGANIZATION_2]" in pseudonymized_path.read_text(encoding="utf-8")
    assert "history_identity_map.json" not in json.dumps(
        task_packet["history_context"]["pseudonymized_documents"]
    )
    _run(
        "record_contribution.py",
        "--run-dir",
        str(run_dir),
        "--contribution",
        str(contribution),
        "--answer-contract",
        str(answer_path),
        "--claim-assurance",
        str(assurance_path),
        "--editorial-assessment",
        str(assessment),
        "--provider",
        "test-provider",
        "--model",
        "test-model",
        "--template-version",
        "professional-communication-v3",
        "--generation-session-id",
        "test-generation-session-001",
        "--recorded-by",
        "test-operator",
        "--assessment-provider",
        "test-provider",
        "--assessment-model",
        "test-editor-model",
        "--claim-assessment-provider",
        "test-provider",
        "--claim-assessment-model",
        "test-claim-model",
    )
    _accept_required_reviews(run_dir)
    _run("promote_studio_profile.py", "--run-dir", str(run_dir))
    _run("render_visuals.py", "--run-dir", str(run_dir))
    _accept_rendered_output(run_dir)
    _run("package_communications.py", "--run-dir", str(run_dir))
    _accept_packaged_output(run_dir)
    _run("validate_run.py", "--run-dir", str(run_dir))
    final = json.loads((run_dir / "final_artifacts.json").read_text(encoding="utf-8"))
    output_kinds = {output["kind"] for output in final["outputs"]}
    email = (run_dir / "drafts" / "client_email.txt").read_text(encoding="utf-8")
    website = (run_dir / "drafts" / "website_article.html").read_text(encoding="utf-8")
    linkedin = (run_dir / "drafts" / "linkedin.txt").read_text(encoding="utf-8")
    assert final["status"] == "final_ready"
    assert "editorial_model_assessment" in output_kinds
    assert "visual_model_assessment" in output_kinds
    assert "## Independent editorial assessment" in (
        run_dir / "technical_basis.md"
    ).read_text(encoding="utf-8")
    assert "Studio Aurora | Nuova misura" in email
    assert "Gentile Cliente," in email
    assert "Dottori Commercialisti" in email
    assert "In allegato trova la circolare" in email
    assert "<article>" in website
    assert "A cura di Studio Aurora" in website
    assert "Il provvedimento ufficiale porta la misura" in website
    assert "La verifica utile" in website
    assert "#fisco #imprese" in linkedin
    assert (run_dir / "visuals" / "circolare-clienti.pdf").read_bytes()[:5] == b"%PDF-"
    with Image.open(run_dir / "visuals" / "slide-01.png") as slide:
        assert slide.size == (1080, 1350)
    assert (workspace / "studio_profile.json").is_file()


def test_no_publish_is_a_complete_reviewable_outcome(tmp_path: Path) -> None:
    workspace = tmp_path / "studio-workspace"
    source = tmp_path / "official-source.txt"
    history = tmp_path / "approved-post.txt"
    source.write_text(
        "Nessuna novità rispetto al testo già comunicato.", encoding="utf-8"
    )
    history.write_text(
        "Aggiornamento già pubblicato dallo Studio Aurora.", encoding="utf-8"
    )
    intake = _write_json(
        tmp_path / "intake.json",
        {
            "schema_version": 1,
            "run_id": "no-slop-2026-001",
            "reference_date": "2026-08-08",
            "language": "it",
            "jurisdiction": "Italia",
            "objective": "Valutare se esiste un aggiornamento utile da pubblicare oggi.",
            "audience": "Clienti impresa dello studio",
            "channels": ["website_article"],
            "visual_requested": False,
            "source_inputs": [
                {
                    "id": "SRC-001",
                    "path": str(source),
                    "title": "Testo ufficiale invariato",
                    "authority_role": "primary",
                }
            ],
            "history_inputs": [
                {"id": "HIST-001", "path": str(history), "channel": "website_article"}
            ],
            "brand_profile": _brand(),
            "external_routes": _routes(),
        },
    )
    contribution = _write_json(
        tmp_path / "contribution.json",
        {
            "schema_version": 1,
            "run_id": "no-slop-2026-001",
            "recommendation": "no_publish",
            "recommendation_reason": "La fonte non introduce elementi nuovi rispetto alla comunicazione già approvata; pubblicare oggi ripeterebbe lo stesso contenuto senza una nuova decisione utile per i clienti.",
            "editorial_value": {
                "reason_now": "Non emerge un evento nuovo o una scadenza modificata.",
                "audience_value": "La ripetizione non cambia le azioni disponibili al cliente.",
                "distinct_angle": "Non è emerso un angolo distinto sostenuto dalla fonte.",
                "practical_use": "Nessuna nuova verifica è richiesta rispetto al post precedente.",
                "source_specific_information": "La fonte conferma soltanto l'assenza di novità rispetto al testo già comunicato.",
                "decision_enabled": "Consente allo Studio di decidere consapevolmente di non pubblicare un duplicato.",
                "decision_limit": "La valutazione riguarda esclusivamente le fonti e lo storico selezionati per questo run.",
                "banality_check": "Una nuova comunicazione sarebbe una ripetizione priva di un fatto o di una decisione nuova.",
                "repetition_check": "Il contenuto sostanziale è già presente nell'esempio selezionato.",
                "publication_judgment": "Non pubblicare tutela il tempo e la fiducia del lettore.",
            },
            "studio_profile_proposal": _profile(),
            "source_assessments": [
                {
                    "source_id": "SRC-001",
                    "semantic_role": "controlling",
                    "authority_assessment": "Testo ufficiale pertinente al confronto temporale.",
                    "limitations": "Non contiene una nuova disposizione o scadenza.",
                },
                {
                    "source_id": "HIST-001",
                    "semantic_role": "style_only",
                    "authority_assessment": "Comunicazione approvata utile al controllo di ripetizione e al profilo.",
                    "limitations": "Non costituisce fonte normativa.",
                },
            ],
            "claims": [],
            "master_brief": None,
            "channel_drafts": [],
            "visual_story": {
                "decision": "omit",
                "decision_reason": "Non esiste informazione nuova da rendere visivamente.",
                "incremental_value": "",
                "title": "",
                "slides": [],
            },
        },
    )
    contribution_payload = json.loads(contribution.read_text(encoding="utf-8"))
    no_publish_contract = _answer_contract(
        contribution_payload, audience="Clienti impresa dello studio"
    )
    assessment = _write_json(
        tmp_path / "editorial-assessment.json",
        _editorial_assessment(
            contribution_payload, answer_contract=no_publish_contract
        ),
    )
    answer_path, assurance_path = _assurance_paths(
        tmp_path,
        contribution_payload,
        answer_contract=no_publish_contract,
    )

    _run(
        "initialize_workspace.py",
        "--workspace",
        str(workspace),
        "--workspace-id",
        "studio-aurora",
        "--owner",
        "Studio Aurora",
        "--retention-owner",
        "Studio Aurora",
        "--confirmed-by-user",
    )
    _qualify_editorial_assessor(workspace, tmp_path)
    _run("prepare_run.py", "--workspace", str(workspace), "--intake", str(intake))
    run_dir = workspace / "runs" / "no-slop-2026-001"
    _record_history_pseudonymization(run_dir, tmp_path)
    _run(
        "record_contribution.py",
        "--run-dir",
        str(run_dir),
        "--contribution",
        str(contribution),
        "--answer-contract",
        str(answer_path),
        "--claim-assurance",
        str(assurance_path),
        "--editorial-assessment",
        str(assessment),
        "--provider",
        "test-provider",
        "--model",
        "test-model",
        "--template-version",
        "professional-communication-v3",
        "--generation-session-id",
        "test-generation-session-001",
        "--recorded-by",
        "test-operator",
        "--assessment-provider",
        "test-provider",
        "--assessment-model",
        "test-editor-model",
        "--claim-assessment-provider",
        "test-provider",
        "--claim-assessment-model",
        "test-claim-model",
    )
    _accept_required_reviews(run_dir)
    _run("package_communications.py", "--run-dir", str(run_dir))
    _accept_packaged_output(run_dir)
    _run("validate_run.py", "--run-dir", str(run_dir))
    final = json.loads((run_dir / "final_artifacts.json").read_text(encoding="utf-8"))
    assert final["status"] == "no_publication_recommended"
    assert (run_dir / "no-publication-recommendation.md").is_file()
    assert not (run_dir / "drafts").exists()


def test_history_pseudonymization_rejects_incomplete_or_not_ready_documents(
    tmp_path: Path,
) -> None:
    workspace = tmp_path / "studio-workspace"
    source = tmp_path / "source.txt"
    first_history = tmp_path / "first-history.txt"
    second_history = tmp_path / "second-history.txt"
    unselected_history = tmp_path / "unselected-history.txt"
    source.write_text("Fonte ufficiale selezionata.", encoding="utf-8")
    first_history.write_text(
        "Gentile Mario Rossi, email mario.rossi@example.com, tel. +39 347 123 4567, "
        "codice fiscale RSSMRA80A01H501U, IBAN IT60X0542811101000000123456, "
        "pratica PR-2026/123. Scadenza 30 settembre 2026; importo 12.500,00 euro.",
        encoding="utf-8",
    )
    second_history.write_text("Gentile Alfa S.r.l., caso riservato.", encoding="utf-8")
    unselected_history.write_text(
        "Questo documento non è stato scelto e non deve entrare nel run.",
        encoding="utf-8",
    )
    intake = _write_json(
        tmp_path / "intake.json",
        {
            "schema_version": 1,
            "run_id": "history-privacy-2026-001",
            "reference_date": "2026-08-08",
            "language": "it",
            "jurisdiction": "Italia",
            "objective": "Preparare una comunicazione usando soltanto esempi scelti.",
            "audience": "Clienti impresa",
            "channels": ["client_email"],
            "visual_requested": False,
            "source_inputs": [
                {
                    "id": "SRC-001",
                    "path": str(source),
                    "title": "Fonte ufficiale",
                    "authority_role": "primary",
                }
            ],
            "history_inputs": [
                {
                    "id": "HIST-001",
                    "path": str(first_history),
                    "channel": "client_email",
                },
                {
                    "id": "HIST-002",
                    "path": str(second_history),
                    "channel": "client_email",
                },
            ],
            "brand_profile": _brand(),
            "external_routes": _routes(),
        },
    )
    _run(
        "initialize_workspace.py",
        "--workspace",
        str(workspace),
        "--workspace-id",
        "studio-aurora",
        "--owner",
        "Studio Aurora",
        "--retention-owner",
        "Studio Aurora",
        "--confirmed-by-user",
    )
    _run("prepare_run.py", "--workspace", str(workspace), "--intake", str(intake))
    run_dir = workspace / "runs" / "history-privacy-2026-001"
    source_register_text = (run_dir / "source_register.json").read_text(
        encoding="utf-8"
    )
    assert unselected_history.name not in source_register_text
    assert str(unselected_history) not in source_register_text
    packet = json.loads(
        (run_dir / "history_pseudonymization_packet.json").read_text(encoding="utf-8")
    )
    first_model_input = Path(packet["history_documents"][0]["path"]).read_text(
        encoding="utf-8"
    )
    assert "mario.rossi@example.com" not in first_model_input
    assert "+39 347 123 4567" not in first_model_input
    assert "RSSMRA80A01H501U" not in first_model_input
    assert "IT60X0542811101000000123456" not in first_model_input
    assert "PR-2026/123" not in first_model_input
    for placeholder in (
        "[EMAIL_1]",
        "[PHONE_1]",
        "[TAX_ID_1]",
        "[ACCOUNT_1]",
        "[CASE_1]",
    ):
        assert placeholder in first_model_input
    assert "30 settembre 2026" in first_model_input
    assert "12.500,00 euro" in first_model_input
    initial_identity_map = (run_dir / "history_identity_map.json").read_text(
        encoding="utf-8"
    )
    assert "mario.rossi@example.com" in initial_identity_map
    assert "RSSMRA80A01H501U" in initial_identity_map
    assert 'identity_mapping_included": false' in (
        run_dir / "history_pseudonymization_packet.json"
    ).read_text(encoding="utf-8")
    preparation = _history_pseudonymization(run_dir)
    preparation["history_items"] = preparation["history_items"][:1]
    incomplete_path = _write_json(tmp_path / "incomplete-history.json", preparation)

    incomplete = _run_result(
        "record_history_pseudonymization.py",
        "--run-dir",
        str(run_dir),
        "--pseudonymization",
        str(incomplete_path),
        "--provider",
        "test-provider",
        "--model",
        "test-history-model",
        "--session-id",
        "test-history-session-001",
        "--recorded-by",
        "test-operator",
    )

    assert incomplete.returncode == 1
    assert "cover every selected history item" in incomplete.stderr
    not_ready = _history_pseudonymization(run_dir)
    not_ready["pseudonymization_assessment"]["indirect_identifiers_generalized"] = False
    not_ready_path = _write_json(tmp_path / "not-ready-history.json", not_ready)
    rejected = _run_result(
        "record_history_pseudonymization.py",
        "--run-dir",
        str(run_dir),
        "--pseudonymization",
        str(not_ready_path),
        "--provider",
        "test-provider",
        "--model",
        "test-history-model",
        "--session-id",
        "test-history-session-002",
        "--recorded-by",
        "test-operator",
    )
    assert rejected.returncode == 1
    assert "not ready for downstream" in rejected.stderr
    assert not (run_dir / "history_pseudonymization_record.json").exists()


def test_prepare_run_blocks_history_connector_before_model_access(
    tmp_path: Path,
) -> None:
    workspace = tmp_path / "studio-workspace"
    source = tmp_path / "source.txt"
    history = tmp_path / "history.txt"
    source.write_text("Fonte ufficiale selezionata.", encoding="utf-8")
    history.write_text("Gentile Mario Rossi.", encoding="utf-8")
    routes = _routes()
    routes["history_connector"] = {
        "selected": True,
        "destination": "Mailbox selected by the professional",
        "approved_by": "Studio Aurora",
        "approved_at": "2026-08-08T10:00:00+00:00",
    }
    intake = _write_json(
        tmp_path / "intake-history-connector.json",
        {
            "schema_version": 1,
            "run_id": "history-connector-blocked-001",
            "reference_date": "2026-08-08",
            "language": "it",
            "jurisdiction": "Italia",
            "objective": "Preparare una comunicazione usando un esempio scelto.",
            "audience": "Clienti impresa",
            "channels": ["client_email"],
            "visual_requested": False,
            "source_inputs": [
                {
                    "id": "SRC-001",
                    "path": str(source),
                    "title": "Fonte ufficiale",
                    "authority_role": "primary",
                }
            ],
            "history_inputs": [
                {"id": "HIST-001", "path": str(history), "channel": "client_email"}
            ],
            "brand_profile": _brand(),
            "external_routes": routes,
        },
    )
    _run(
        "initialize_workspace.py",
        "--workspace",
        str(workspace),
        "--workspace-id",
        "studio-aurora",
        "--owner",
        "Studio Aurora",
        "--retention-owner",
        "Studio Aurora",
        "--confirmed-by-user",
    )

    blocked = _run_result(
        "prepare_run.py", "--workspace", str(workspace), "--intake", str(intake)
    )

    assert blocked.returncode == 1
    assert (
        "history_connector" in blocked.stderr or "history-connector" in blocked.stderr
    )
    assert not (workspace / "runs" / "history-connector-blocked-001").exists()


def test_requested_visual_can_be_omitted_when_editor_finds_no_incremental_value(
    tmp_path: Path,
) -> None:
    contribution = _clone(_publish_contribution())
    contribution["visual_story"] = {
        "decision": "omit",
        "decision_reason": "Il post è autosufficiente e un carosello lo parafraserebbe senza aggiungere un nuovo strumento di decisione.",
        "incremental_value": "",
        "title": "",
        "slides": [],
    }
    _, run_dir, _ = _recorded_publish_run(
        tmp_path,
        channels=["linkedin"],
        visual_requested=True,
        contribution=contribution,
    )
    workbench = json.loads(
        (run_dir / "content_workbench.json").read_text(encoding="utf-8")
    )
    assert workbench["post_generation_review_scopes"] == ["packaged_output"]

    _accept_required_reviews(run_dir)
    _run("package_communications.py", "--run-dir", str(run_dir))
    _accept_packaged_output(run_dir)
    _run("validate_run.py", "--run-dir", str(run_dir))

    final = json.loads((run_dir / "final_artifacts.json").read_text(encoding="utf-8"))
    assert final["status"] == "final_ready"
    assert not (run_dir / "visual_manifest.json").exists()
    assert not (run_dir / "visuals").exists()


def test_independent_editorial_revision_blocks_contribution_recording(
    tmp_path: Path,
) -> None:
    _, run_dir, contribution = _recorded_publish_run(
        tmp_path, channels=["client_email"], visual_requested=False
    )
    contribution_path = _write_json(tmp_path / "revision.json", contribution)
    assessment_path = _write_json(
        tmp_path / "revision-assessment.json",
        _editorial_assessment(contribution, verdict="revise"),
    )
    answer_path, assurance_path = _assurance_paths(tmp_path, contribution)

    completed = _run_result(
        "record_contribution.py",
        "--run-dir",
        str(run_dir),
        "--contribution",
        str(contribution_path),
        "--answer-contract",
        str(answer_path),
        "--claim-assurance",
        str(assurance_path),
        "--editorial-assessment",
        str(assessment_path),
        "--provider",
        "test-provider",
        "--model",
        "test-model",
        "--template-version",
        "professional-communication-v3",
        "--generation-session-id",
        "test-generation-session-001",
        "--recorded-by",
        "test-operator",
        "--assessment-provider",
        "test-provider",
        "--assessment-model",
        "test-editor-model",
        "--claim-assessment-provider",
        "test-provider",
        "--claim-assessment-model",
        "test-claim-model",
    )

    assert completed.returncode == 1
    assert "must be ready" in completed.stderr


def test_public_source_note_cannot_expose_internal_traceability_id(
    tmp_path: Path,
) -> None:
    channels = [
        "client_email",
        "client_circular",
        "linkedin",
        "website_article",
    ]
    _, run_dir, _ = _recorded_publish_run(
        tmp_path, channels=channels, visual_requested=True
    )
    contribution = _clone(_publish_contribution())
    contribution["visual_story"]["slides"][0]["source_note"] = "Fonte: SRC-001"
    contribution_path = _write_json(tmp_path / "leaking.json", contribution)
    assessment_path = _write_json(
        tmp_path / "leaking-assessment.json",
        _editorial_assessment(contribution),
    )
    answer_path, assurance_path = _assurance_paths(tmp_path, contribution)

    completed = _run_result(
        "record_contribution.py",
        "--run-dir",
        str(run_dir),
        "--contribution",
        str(contribution_path),
        "--answer-contract",
        str(answer_path),
        "--claim-assurance",
        str(assurance_path),
        "--editorial-assessment",
        str(assessment_path),
        "--provider",
        "test-provider",
        "--model",
        "test-model",
        "--template-version",
        "professional-communication-v3",
        "--generation-session-id",
        "test-generation-session-001",
        "--recorded-by",
        "test-operator",
        "--assessment-provider",
        "test-provider",
        "--assessment-model",
        "test-editor-model",
        "--claim-assessment-provider",
        "test-provider",
        "--claim-assessment-model",
        "test-claim-model",
    )

    assert completed.returncode == 1
    assert "exposes internal ids" in completed.stderr


def test_changed_workbench_bytes_invalidate_professional_reviews(
    tmp_path: Path,
) -> None:
    _, run_dir, _ = _recorded_publish_run(
        tmp_path, channels=["client_email"], visual_requested=False
    )
    _accept_required_reviews(run_dir)
    workbench_path = run_dir / "content_workbench.json"
    workbench = json.loads(workbench_path.read_text(encoding="utf-8"))
    workbench["contribution"]["channel_drafts"][0][
        "body"
    ] = "Testo alterato dopo l'approvazione."
    _write_json(workbench_path, workbench)

    completed = _run_result("package_communications.py", "--run-dir", str(run_dir))

    assert completed.returncode == 1
    assert "immutable version snapshot" in completed.stderr


def test_changed_source_and_rewritten_register_still_invalidate_run(
    tmp_path: Path,
) -> None:
    _, run_dir, _ = _recorded_publish_run(
        tmp_path, channels=["client_email"], visual_requested=False
    )
    _accept_required_reviews(run_dir)
    register_path = run_dir / "source_register.json"
    register = json.loads(register_path.read_text(encoding="utf-8"))
    snapshot = Path(register["sources"][0]["snapshot_path"])
    snapshot.write_text("Fonte sostituita dopo la revisione.", encoding="utf-8")
    register["sources"][0]["sha256"] = hashlib.sha256(snapshot.read_bytes()).hexdigest()
    register["sources"][0]["size_bytes"] = snapshot.stat().st_size
    _write_json(register_path, register)

    completed = _run_result("package_communications.py", "--run-dir", str(run_dir))

    assert completed.returncode == 1
    assert "Prepared input digest mismatch" in completed.stderr


def test_validation_finalizes_package_and_delivery_rechecks_current_bytes(
    tmp_path: Path,
) -> None:
    routes = _routes()
    routes["send_or_publish"] = {
        "selected": True,
        "destination": "clienti@example.test",
        "approved_by": "Dott.ssa Revisore",
        "approved_at": "2026-08-08T10:00:00+00:00",
    }
    _, run_dir, _ = _recorded_publish_run(
        tmp_path,
        channels=["client_email"],
        visual_requested=False,
        routes=routes,
    )
    _accept_required_reviews(run_dir)
    _run("package_communications.py", "--run-dir", str(run_dir))
    pending = json.loads((run_dir / "final_artifacts.json").read_text(encoding="utf-8"))
    assert pending["status"] == "validation_pending"
    before_validation = _run_result(
        "record_external_delivery.py",
        "--run-dir",
        str(run_dir),
        "--action",
        "email_sent",
        "--destination",
        "clienti@example.test",
        "--visible-receipt",
        "message-id:synthetic-001",
        "--confirmed-by",
        "Dott.ssa Revisore",
        "--confirmed-by-user",
    )
    assert before_validation.returncode == 1
    assert "validated final_ready" in before_validation.stderr

    missing_package_review = _run_result("validate_run.py", "--run-dir", str(run_dir))
    assert missing_package_review.returncode == 1
    assert "packaged_output" in missing_package_review.stderr
    _accept_packaged_output(run_dir)
    _run("validate_run.py", "--run-dir", str(run_dir))
    finalized = json.loads(
        (run_dir / "final_artifacts.json").read_text(encoding="utf-8")
    )
    assert finalized["status"] == "final_ready"
    assert (
        finalized["validation_receipt"]["package_digest"] == finalized["package_digest"]
    )
    _run(
        "record_external_delivery.py",
        "--run-dir",
        str(run_dir),
        "--action",
        "email_sent",
        "--destination",
        "clienti@example.test",
        "--visible-receipt",
        "message-id:synthetic-001",
        "--confirmed-by",
        "Dott.ssa Revisore",
        "--confirmed-by-user",
    )
    delivery = json.loads(
        (run_dir / "external_delivery.json").read_text(encoding="utf-8")
    )
    assert delivery["package_digest"] == finalized["package_digest"]
    assert (
        delivery["validation_receipt_digest"]
        == finalized["validation_receipt"]["receipt_digest"]
    )
    _run("validate_run.py", "--run-dir", str(run_dir))
    revalidated = json.loads(
        (run_dir / "final_artifacts.json").read_text(encoding="utf-8")
    )
    assert (
        revalidated["validation_receipt"]["receipt_digest"]
        == delivery["validation_receipt_digest"]
    )

    email_path = run_dir / "drafts" / "client_email.txt"
    email_path.write_text("altered after validation", encoding="utf-8")
    after_tamper = _run_result(
        "record_external_delivery.py",
        "--run-dir",
        str(run_dir),
        "--action",
        "email_sent",
        "--destination",
        "clienti@example.test",
        "--visible-receipt",
        "message-id:synthetic-001",
        "--confirmed-by",
        "Dott.ssa Revisore",
        "--confirmed-by-user",
    )
    assert after_tamper.returncode == 1
    assert "Final output" in after_tamper.stderr


def test_all_structured_sections_survive_and_email_has_no_false_attachment(
    tmp_path: Path,
) -> None:
    contribution = _clone(_publish_contribution())
    email = contribution["channel_drafts"][0]
    email["sections"] = [
        {
            "heading": "Verifica preliminare",
            "body": "Controllare il perimetro prima di assumere iniziative.",
            "bullets": ["Soggetto", "Attività"],
        }
    ]
    contribution["channel_drafts"] = [email]
    for channel, title in (
        ("newsletter", "Approfondimento mensile"),
        ("client_alert", "Avviso operativo"),
        ("faq", "Domande frequenti"),
    ):
        contribution["channel_drafts"].append(
            {
                "channel": channel,
                "title": title,
                "body": f"Introduzione {channel} da conservare.",
                "claim_ids": ["CLAIM-001"],
                "audience_note": "Clienti impresa potenzialmente interessati.",
                "public_source_notes": [
                    {
                        "source_ids": ["SRC-001"],
                        "text": "Agenzia delle Entrate — Provvedimento n. 12345/2026 dell'8 agosto 2026",
                    }
                ],
                "sections": [
                    {
                        "heading": f"Sezione {channel}",
                        "body": f"Corpo strutturato {channel} da conservare.",
                        "bullets": [f"Azione {channel}"],
                    }
                ],
            }
        )
    channels = ["client_email", "newsletter", "client_alert", "faq"]
    _, run_dir, _ = _recorded_publish_run(
        tmp_path,
        channels=channels,
        visual_requested=False,
        contribution=contribution,
    )
    _accept_required_reviews(run_dir)
    _run("package_communications.py", "--run-dir", str(run_dir))
    _accept_packaged_output(run_dir)
    _run("validate_run.py", "--run-dir", str(run_dir))

    email_text = (run_dir / "drafts" / "client_email.txt").read_text(encoding="utf-8")
    assert "Verifica preliminare" in email_text
    assert "- Soggetto" in email_text
    assert "In allegato" not in email_text
    for channel in ("newsletter", "client_alert", "faq"):
        text = (run_dir / "drafts" / f"{channel}.md").read_text(encoding="utf-8")
        assert f"Introduzione {channel} da conservare." in text
        assert f"Sezione {channel}" in text
        assert f"Corpo strutturato {channel} da conservare." in text
        assert f"- Azione {channel}" in text


def test_studio_profile_persists_logo_and_rejects_unreviewed_brand_drift(
    tmp_path: Path,
) -> None:
    logo = tmp_path / "studio-logo.png"
    Image.new("RGB", (240, 80), "#002060").save(logo)
    brand = _brand()
    brand["logo_path"] = str(logo)
    workspace, run_dir, _ = _recorded_publish_run(
        tmp_path,
        channels=["client_email"],
        visual_requested=False,
        brand=brand,
    )
    _accept_required_reviews(run_dir)
    _run("promote_studio_profile.py", "--run-dir", str(run_dir))
    stored = json.loads((workspace / "studio_profile.json").read_text(encoding="utf-8"))
    stored_logo = workspace / stored["brand_assets"]["logo"]["workspace_relative_path"]
    assert stored_logo.is_file()
    assert stored["format_digest"]

    source = tmp_path / "second-source.txt"
    source.write_text("Seconda fonte ufficiale.", encoding="utf-8")
    second_intake = _write_json(
        tmp_path / "second-intake.json",
        {
            "schema_version": 1,
            "run_id": "norma-2026-002",
            "reference_date": "2026-08-08",
            "language": "it",
            "jurisdiction": "Italia",
            "objective": "Preparare una seconda comunicazione nello stesso formato.",
            "audience": "Clienti impresa",
            "channels": ["client_email"],
            "visual_requested": False,
            "source_inputs": [
                {
                    "id": "SRC-002",
                    "path": str(source),
                    "title": "Seconda fonte",
                    "authority_role": "primary",
                }
            ],
            "history_inputs": [],
            "brand_profile": _brand(),
            "external_routes": _routes(),
        },
    )
    _run(
        "prepare_run.py",
        "--workspace",
        str(workspace),
        "--intake",
        str(second_intake),
    )
    second_register = json.loads(
        (workspace / "runs" / "norma-2026-002" / "source_register.json").read_text(
            encoding="utf-8"
        )
    )
    assert (
        second_register["brand_logo"]["sha256"]
        == stored["brand_assets"]["logo"]["sha256"]
    )

    changed_brand = _brand()
    changed_brand["primary_color"] = "#990000"
    changed_intake_payload = json.loads(second_intake.read_text(encoding="utf-8"))
    changed_intake_payload["run_id"] = "norma-2026-003"
    changed_intake_payload["brand_profile"] = changed_brand
    changed_intake = _write_json(
        tmp_path / "changed-intake.json", changed_intake_payload
    )
    rejected = _run_result(
        "prepare_run.py",
        "--workspace",
        str(workspace),
        "--intake",
        str(changed_intake),
    )
    assert rejected.returncode == 1
    assert "Brand settings differ" in rejected.stderr
    assert not (workspace / "runs" / "norma-2026-003").exists()


def test_failed_preparation_is_cleanly_retryable(tmp_path: Path) -> None:
    workspace = tmp_path / "studio-workspace"
    source = tmp_path / "source.txt"
    history = tmp_path / "history.txt"
    invalid_logo = tmp_path / "logo.svg"
    source.write_text("Fonte ufficiale.", encoding="utf-8")
    history.write_text("Comunicazione approvata.", encoding="utf-8")
    invalid_logo.write_text("<svg/>", encoding="utf-8")
    brand = _brand()
    brand["logo_path"] = str(invalid_logo)
    intake_payload = {
        "schema_version": 1,
        "run_id": "retry-2026-001",
        "reference_date": "2026-08-08",
        "language": "it",
        "jurisdiction": "Italia",
        "objective": "Verificare che la preparazione sia ripetibile dopo un errore.",
        "audience": "Clienti impresa",
        "channels": ["client_email"],
        "visual_requested": False,
        "source_inputs": [
            {
                "id": "SRC-001",
                "path": str(source),
                "title": "Fonte",
                "authority_role": "primary",
            }
        ],
        "history_inputs": [
            {"id": "HIST-001", "path": str(history), "channel": "client_email"}
        ],
        "brand_profile": brand,
        "external_routes": _routes(),
    }
    intake = _write_json(tmp_path / "retry-intake.json", intake_payload)
    _run(
        "initialize_workspace.py",
        "--workspace",
        str(workspace),
        "--workspace-id",
        "studio-aurora",
        "--owner",
        "Studio Aurora",
        "--retention-owner",
        "Studio Aurora",
        "--confirmed-by-user",
    )
    failed = _run_result(
        "prepare_run.py", "--workspace", str(workspace), "--intake", str(intake)
    )
    assert failed.returncode == 1
    assert not (workspace / "runs" / "retry-2026-001").exists()
    assert not any(
        path.name.startswith(".retry-2026-001.preparing-")
        for path in (workspace / "runs").iterdir()
    )

    valid_logo = tmp_path / "logo.png"
    Image.new("RGB", (120, 40), "#002060").save(valid_logo)
    intake_payload["brand_profile"]["logo_path"] = str(valid_logo)
    _write_json(intake, intake_payload)
    _run("prepare_run.py", "--workspace", str(workspace), "--intake", str(intake))
    assert (workspace / "runs" / "retry-2026-001" / "run_intake.json").is_file()


def test_rendered_output_requires_exact_separate_acceptance(tmp_path: Path) -> None:
    _, run_dir, _ = _recorded_publish_run(
        tmp_path, channels=["client_circular"], visual_requested=False
    )
    _accept_required_reviews(run_dir)
    _run("render_visuals.py", "--run-dir", str(run_dir))
    unreviewed = _run_result("package_communications.py", "--run-dir", str(run_dir))
    assert unreviewed.returncode == 1
    assert "rendered_output" in unreviewed.stderr

    _accept_rendered_output(run_dir)
    manifest_path = run_dir / "visual_manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    circular = next(
        output
        for output in manifest["outputs"]
        if output["kind"] == "client_circular_pdf"
    )
    circular_path = run_dir / circular["path"]
    circular_path.write_bytes(circular_path.read_bytes() + b"\n")
    circular["sha256"] = hashlib.sha256(circular_path.read_bytes()).hexdigest()
    circular["size_bytes"] = circular_path.stat().st_size
    manifest_without_digest = {
        key: value for key, value in manifest.items() if key != "manifest_digest"
    }
    manifest["manifest_digest"] = hashlib.sha256(
        json.dumps(
            manifest_without_digest,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    ).hexdigest()
    _write_json(manifest_path, manifest)
    changed_after_review = _run_result(
        "package_communications.py", "--run-dir", str(run_dir)
    )
    assert changed_after_review.returncode == 1
    assert "rendered_output" in changed_after_review.stderr


def test_rendered_output_acceptance_requires_explicit_model_led_checklist(
    tmp_path: Path,
) -> None:
    _, run_dir, _ = _recorded_publish_run(
        tmp_path, channels=["client_email"], visual_requested=True
    )
    _accept_required_reviews(run_dir)
    _run("render_visuals.py", "--run-dir", str(run_dir))

    completed = _run_result(
        "record_review.py",
        "--run-dir",
        str(run_dir),
        "--scope",
        "rendered_output",
        "--decision",
        "accepted",
        "--reviewer",
        "Dott.ssa Revisore",
        "--confirmed-by-user",
    )

    assert completed.returncode == 1
    assert "quality-checklist-confirmed" in completed.stderr

    without_model_review = _run_result(
        "record_review.py",
        "--run-dir",
        str(run_dir),
        "--scope",
        "rendered_output",
        "--decision",
        "accepted",
        "--reviewer",
        "Dott.ssa Revisore",
        "--confirmed-by-user",
        "--quality-checklist-confirmed",
    )
    assert without_model_review.returncode == 1
    assert "visual_assessment_record.json" in without_model_review.stderr


def test_qa_preview_is_available_before_review_but_cannot_be_packaged(
    tmp_path: Path,
) -> None:
    _, run_dir, _ = _recorded_publish_run(
        tmp_path, channels=["client_email"], visual_requested=True
    )

    _run("render_visuals.py", "--run-dir", str(run_dir), "--qa-preview")

    preview_manifest = json.loads(
        (run_dir / "visual_preview_manifest.json").read_text(encoding="utf-8")
    )
    assert preview_manifest["render_state"] == "qa_preview"
    assert (run_dir / "visuals-preview" / "slide-01.png").is_file()
    assert not (run_dir / "visual_manifest.json").exists()
    slides = [
        output
        for output in preview_manifest["outputs"]
        if output["kind"] == "carousel_slide"
    ]
    assessment = _write_json(
        run_dir / "preview-assessment-input.json",
        {
            "schema_version": 1,
            "run_id": preview_manifest["run_id"],
            "assessed_manifest_digest": preview_manifest["manifest_digest"],
            "assessment_protocol": {
                "method": "isolated_host_session_exact_render_review",
                "assessor_session_id": "test-visual-preview-session-001",
                "assessment_template_version": "professional-visual-editor-v2",
                "template_sha256": _prompt_digest("visual-assessment-v2.md"),
                "generation_transcript_seen": False,
                "editorial_transcript_seen": False,
                "completed_at": "2026-08-08T12:30:00+00:00",
            },
            "render_state": "qa_preview",
            "verdict": "revise",
            "post_comparison": "La preview ripete parte della bozza e non dimostra ancora un vantaggio sufficiente per il lettore del carosello.",
            "information_density": "Una slide usa molto spazio per una conclusione debole mentre le altre mantengono una densità più utile.",
            "source_readability": "Le note fonte risultano leggibili e non mostrano identificatori tecnici interni al workflow.",
            "identity_judgment": "Il nome dello Studio compare soltanto nella chiusura secondo il profilo selezionato per il test.",
            "visual_quality": "La tipografia è leggibile ma il giudizio editoriale sulla slide debole impedisce di considerare pronta la sequenza.",
            "weakest_slide": "La seconda slide è la più debole perché presenta una conclusione troppo vicina alla bozza senza un'informazione ulteriore.",
            "slide_assessments": [
                {
                    "slide_index": index,
                    "verdict": "weak" if index == 2 else "adds_value",
                    "visible_judgment": "La slide richiede una decisione semantica basata sull'immagine esatta, non su conteggi o parole chiave.",
                    "required_change": (
                        "Sostituire la parafrasi con un dettaglio verificabile."
                        if index == 2
                        else ""
                    ),
                }
                for index, _slide in enumerate(slides, start=1)
            ],
            "document_assessments": [],
            "required_changes": [
                "Sostituire la seconda slide con informazione incrementale verificabile."
            ],
        },
    )
    _run(
        "record_visual_assessment.py",
        "--run-dir",
        str(run_dir),
        "--assessment",
        str(assessment),
        "--provider",
        "test-provider",
        "--model",
        "test-visual-editor-model",
        "--qa-preview",
    )
    recorded = json.loads(
        (run_dir / "visual_preview_assessment_record.json").read_text(encoding="utf-8")
    )
    assert recorded["assessment"]["verdict"] == "revise"
    blocked = _run_result("package_communications.py", "--run-dir", str(run_dir))
    assert blocked.returncode == 1
    assert "Fresh accepted review required" in blocked.stderr


def test_close_only_identity_and_public_sources_are_recorded_per_slide(
    tmp_path: Path,
) -> None:
    _, run_dir, _ = _recorded_publish_run(
        tmp_path, channels=["client_email"], visual_requested=True
    )
    _accept_required_reviews(run_dir)
    _run("render_visuals.py", "--run-dir", str(run_dir))

    manifest = json.loads(
        (run_dir / "visual_manifest.json").read_text(encoding="utf-8")
    )
    slides = [
        output for output in manifest["outputs"] if output["kind"] == "carousel_slide"
    ]
    assert [slide["layout_validation"]["identity_visible"] for slide in slides] == [
        False,
        False,
        True,
    ]
    assert all(
        "SRC-" not in slide["layout_validation"]["public_source_note"]
        for slide in slides
    )
    assert all(
        slide["layout_validation"]["public_source_note"].startswith("Fonte:")
        for slide in slides
    )
    assert manifest["quality_gate"]["model_led_review_required"] is True
    review = (run_dir / "visuals" / "visual-review.md").read_text(encoding="utf-8")
    assert "Mechanical checks cannot answer these questions" in review
    assert "generic AI carousel" in review


def test_unsupported_visual_glyph_fails_before_writing_partial_outputs(
    tmp_path: Path,
) -> None:
    contribution = _clone(_publish_contribution())
    contribution["visual_story"]["slides"][0][
        "title"
    ] = "Garanzia pubblica ≠ contributo a fondo perduto"
    _, run_dir, _ = _recorded_publish_run(
        tmp_path,
        channels=["client_email"],
        visual_requested=True,
        contribution=contribution,
    )
    _accept_required_reviews(run_dir)

    completed = _run_result("render_visuals.py", "--run-dir", str(run_dir))

    assert completed.returncode == 1
    assert "unsupported font glyphs" in completed.stderr
    assert "U+2260" in completed.stderr
    assert not (run_dir / "visual_manifest.json").exists()
    assert not (run_dir / "visuals").exists()


def test_long_unbroken_visual_text_is_never_accepted_with_overflow(
    tmp_path: Path,
) -> None:
    contribution = _clone(_publish_contribution())
    contribution["visual_story"]["slides"][0]["body"] = "W" * 400
    _, run_dir, _ = _recorded_publish_run(
        tmp_path,
        channels=["client_email"],
        visual_requested=True,
        contribution=contribution,
    )
    _accept_required_reviews(run_dir)
    completed = _run_result("render_visuals.py", "--run-dir", str(run_dir))

    assert completed.returncode == 1
    assert "without clipping" in completed.stderr
    assert not (run_dir / "visual_manifest.json").exists()


@pytest.mark.skipif(os.name == "nt", reason="POSIX lock probe")
def test_concurrent_review_writer_is_rejected_without_losing_state(
    tmp_path: Path,
) -> None:
    _, run_dir, _ = _recorded_publish_run(
        tmp_path, channels=["client_email"], visual_requested=False
    )
    lock_module = importlib.import_module("fcntl")
    lock_path = run_dir / ".comunicazione-professionale.lock"
    with lock_path.open("a+", encoding="utf-8") as lock_handle:
        lock_module.flock(
            lock_handle.fileno(), lock_module.LOCK_EX | lock_module.LOCK_NB
        )
        blocked = _run_result(
            "record_review.py",
            "--run-dir",
            str(run_dir),
            "--scope",
            "recommendation",
            "--decision",
            "accepted",
            "--reviewer",
            "Dott.ssa Revisore",
            "--confirmed-by-user",
        )
        lock_module.flock(lock_handle.fileno(), lock_module.LOCK_UN)
    assert blocked.returncode == 1
    assert "mutation is in progress" in blocked.stderr
    review_log = json.loads((run_dir / "review_log.json").read_text(encoding="utf-8"))
    assert review_log["events"] == []


def test_creative_direction_handoff_is_exact_bound_and_non_publishable(
    tmp_path: Path,
) -> None:
    routes = _routes()
    routes["creative_production"] = {
        "selected": True,
        "destination": "Creative Production board in the selected Codex workspace",
        "approved_by": "Dott.ssa Revisore",
        "approved_at": "2026-08-08T15:00:00+00:00",
    }
    _, run_dir, contribution = _recorded_publish_run(
        tmp_path,
        channels=["linkedin"],
        visual_requested=True,
        routes=routes,
    )

    _run(
        "prepare_creative_direction_handoff.py",
        "--run-dir",
        str(run_dir),
        "--directions",
        "5",
    )

    handoff = json.loads(
        (run_dir / "creative-direction" / "handoff-v001.json").read_text(
            encoding="utf-8"
        )
    )
    handoff_text = json.dumps(handoff, ensure_ascii=False)
    assert handoff["route"]["skill"] == "creative-production:produce"
    assert handoff["route"]["board_tool"] == "creative_production_board"
    assert handoff["production_request"] == {
        "direction_count": 5,
        "target_width_px": 1080,
        "target_height_px": 1350,
        "output_kind": "art_direction_references",
        "publishable": False,
        "human_selection_required": True,
        "final_renderer": "vera_deterministic_renderer",
    }
    assert [row["title"] for row in handoff["exact_content"]] == [
        slide["title"] for slide in contribution["visual_story"]["slides"]
    ]
    assert (
        handoff["studio_visual_context"]["social"]["carousel_identity_placement"]
        == "close_only"
    )
    assert "SRC-001" not in handoff_text
    assert "HIST-001" not in handoff_text
    assert handoff["fallback"] == {
        "when_unavailable": "use_internal_visual_system",
        "renderer": "vera_deterministic_renderer",
        "run_must_continue": True,
    }
    assert len(handoff["handoff_digest"]) == 64
    markdown = (run_dir / "creative-direction" / "handoff-v001.md").read_text(
        encoding="utf-8"
    )
    assert "non-publishable art-direction brief" in markdown
    assert "Vera owns exact content" in markdown


def test_creative_direction_handoff_requires_explicit_route_selection(
    tmp_path: Path,
) -> None:
    _, run_dir, _ = _recorded_publish_run(
        tmp_path,
        channels=["linkedin"],
        visual_requested=True,
    )

    completed = _run_result(
        "prepare_creative_direction_handoff.py",
        "--run-dir",
        str(run_dir),
    )

    assert completed.returncode == 1
    assert "was not explicitly selected" in completed.stderr
    assert not (run_dir / "creative-direction").exists()


@pytest.mark.parametrize("false_ready_case", ["EQ-001", "EQ-007"])
def test_editorial_assessor_with_false_ready_does_not_qualify(
    tmp_path: Path, false_ready_case: str
) -> None:
    workspace = tmp_path / "studio-workspace"
    _run(
        "initialize_workspace.py",
        "--workspace",
        str(workspace),
        "--workspace-id",
        "studio-aurora",
        "--owner",
        "Studio Aurora",
        "--retention-owner",
        "Studio Aurora",
        "--confirmed-by-user",
    )
    expectations = json.loads(
        (PLUGIN / "evals" / "editorial_quality_expected.json").read_text(
            encoding="utf-8"
        )
    )["expectations"]
    judgments = [
        {
            "case_id": row["case_id"],
            "verdict": (
                "ready"
                if row["case_id"] == false_ready_case
                else row["expected_verdict"]
            ),
            "analysis": "Il giudizio è stato prodotto sul caso esatto, ma questo fixture simula un falso ready sul contenuto generico.",
        }
        for row in expectations
    ]
    results = _write_json(
        tmp_path / "failed-benchmark.json",
        {
            "schema_version": 1,
            "provider": "test-provider",
            "model": "weak-editor-model",
            "assessment_template_version": "professional-communication-editorial-v4",
            "template_sha256": _prompt_digest("editorial-assessment-v4.md"),
            "assessor_session_id": "weak-benchmark-session-001",
            "evaluated_at": "2026-08-08T11:00:00+00:00",
            "judgments": judgments,
        },
    )

    completed = _run_result(
        "qualify_editorial_assessor.py",
        "--workspace",
        str(workspace),
        "--results",
        str(results),
        "--recorded-by",
        "test-operator",
    )

    assert completed.returncode == 1
    assert f"false_ready=['{false_ready_case}']" in completed.stderr
    record = json.loads(
        (workspace / "editorial_assessor_qualification.json").read_text(
            encoding="utf-8"
        )
    )
    assert record["status"] == "not_qualified"
    assert record["metrics"]["false_ready_count"] == 1


def test_claim_assurance_blocks_unsupported_live_claim(
    tmp_path: Path,
) -> None:
    _, run_dir, contribution = _recorded_publish_run(
        tmp_path, channels=["client_email"], visual_requested=False
    )
    answer_contract = _answer_contract(contribution)
    claim_assurance = _claim_assurance(contribution, answer_contract)
    claim_assurance["claims"][0]["support"] = {
        "status": "not_supported",
        "analysis": "La fonte registrata non contiene il perimetro affermato e il claim richiede una revisione sostanziale prima dell'uso.",
    }
    assessment = _editorial_assessment(contribution)
    assessment["claim_assurance_digest"] = _canonical_digest(claim_assurance)
    contribution_path = _write_json(
        tmp_path / "unsupported-contribution.json", contribution
    )
    answer_path = _write_json(
        tmp_path / "unsupported-answer-contract.json", answer_contract
    )
    assurance_path = _write_json(
        tmp_path / "unsupported-claim-assurance.json", claim_assurance
    )
    assessment_path = _write_json(tmp_path / "unsupported-editorial.json", assessment)

    completed = _run_result(
        "record_contribution.py",
        "--run-dir",
        str(run_dir),
        "--contribution",
        str(contribution_path),
        "--answer-contract",
        str(answer_path),
        "--claim-assurance",
        str(assurance_path),
        "--editorial-assessment",
        str(assessment_path),
        "--provider",
        "test-provider",
        "--model",
        "test-model",
        "--template-version",
        "professional-communication-v3",
        "--generation-session-id",
        "test-generation-session-001",
        "--recorded-by",
        "test-operator",
        "--assessment-provider",
        "test-provider",
        "--assessment-model",
        "test-editor-model",
        "--claim-assessment-provider",
        "test-provider",
        "--claim-assessment-model",
        "test-claim-model",
    )

    assert completed.returncode == 1
    assert "unresolved support: CLAIM-001" in completed.stderr


def test_studio_profile_requires_field_level_evidence_coverage(
    tmp_path: Path,
) -> None:
    _, run_dir, contribution = _recorded_publish_run(
        tmp_path, channels=["client_email"], visual_requested=False
    )
    profile = contribution["studio_profile_proposal"]
    profile["field_provenance"][0]["field_paths"].remove(
        "document.layout.logo_width_mm"
    )
    contribution_path = _write_json(tmp_path / "incomplete-profile.json", contribution)
    answer_path, assurance_path = _assurance_paths(tmp_path, contribution)
    assessment_path = _write_json(
        tmp_path / "incomplete-profile-editorial.json",
        _editorial_assessment(contribution),
    )

    completed = _run_result(
        "record_contribution.py",
        "--run-dir",
        str(run_dir),
        "--contribution",
        str(contribution_path),
        "--answer-contract",
        str(answer_path),
        "--claim-assurance",
        str(assurance_path),
        "--editorial-assessment",
        str(assessment_path),
        "--provider",
        "test-provider",
        "--model",
        "test-model",
        "--template-version",
        "professional-communication-v3",
        "--generation-session-id",
        "test-generation-session-001",
        "--recorded-by",
        "test-operator",
        "--assessment-provider",
        "test-provider",
        "--assessment-model",
        "test-editor-model",
        "--claim-assessment-provider",
        "test-provider",
        "--claim-assessment-model",
        "test-claim-model",
    )

    assert completed.returncode == 1
    assert "field provenance must cover every field exactly" in completed.stderr


def test_review_bundle_records_one_confirmation_session_for_all_semantic_scopes(
    tmp_path: Path,
) -> None:
    _, run_dir, _ = _recorded_publish_run(
        tmp_path, channels=["client_email"], visual_requested=False
    )
    workbench = json.loads(
        (run_dir / "content_workbench.json").read_text(encoding="utf-8")
    )
    bundle = _write_json(
        tmp_path / "review-bundle.json",
        {
            "schema_version": 1,
            "run_id": workbench["run_id"],
            "decisions": [
                {"scope": scope, "decision": "accepted", "note": ""}
                for scope in workbench["required_review_scopes"]
            ],
        },
    )

    _run(
        "record_review.py",
        "--run-dir",
        str(run_dir),
        "--bundle",
        str(bundle),
        "--reviewer",
        "Dott.ssa Revisore",
        "--confirmed-by-user",
    )

    review_log = json.loads((run_dir / "review_log.json").read_text(encoding="utf-8"))
    assert len(review_log["events"]) == len(workbench["required_review_scopes"])
    assert len({event["review_session_id"] for event in review_log["events"]}) == 1
    assert {event["scope"] for event in review_log["events"]} == set(
        workbench["required_review_scopes"]
    )


def test_failed_creative_direction_capture_leaves_no_partial_snapshot(
    tmp_path: Path,
) -> None:
    routes = _routes()
    routes["creative_production"] = {
        "selected": True,
        "destination": "Creative Production board in the selected Codex workspace",
        "approved_by": "Dott.ssa Revisore",
        "approved_at": "2026-08-08T15:00:00+00:00",
    }
    _, run_dir, _ = _recorded_publish_run(
        tmp_path,
        channels=["linkedin"],
        visual_requested=True,
        routes=routes,
    )
    _run(
        "prepare_creative_direction_handoff.py",
        "--run-dir",
        str(run_dir),
        "--directions",
        "4",
    )
    handoff = json.loads(
        (run_dir / "creative-direction" / "handoff-v001.json").read_text(
            encoding="utf-8"
        )
    )
    directions: list[dict[str, object]] = []
    for index in range(1, 5):
        path = tmp_path / f"capture-{index}.png"
        size = (1080, 1350) if index < 4 else (900, 900)
        Image.new("RGB", size, "#E9F2FF").save(path)
        directions.append(
            {
                "item_id": f"capture-{index}",
                "item_revision": index,
                "title": f"Capture direction {index}",
                "image_path": str(path),
            }
        )
    selection = _write_json(
        tmp_path / "invalid-creative-selection.json",
        {
            "schema_version": 1,
            "run_id": handoff["run_id"],
            "handoff_digest": handoff["handoff_digest"],
            "outcome": "selected",
            "selection": {
                "board_id": "board-vera-failed-capture",
                "board_revision": 1,
                "directions": directions,
                "selected_item_id": "capture-2",
                "selection_rationale": "La direzione selezionata chiarisce la gerarchia senza modificare il contributo editoriale approvato.",
                "translation": {
                    "art_direction_summary": "Cornice editoriale sottile e ritmo arioso con testo vivo e fonti leggibili.",
                    "exact_content_preserved": True,
                    "source_preservation_confirmed": True,
                    "contribution_change_required": False,
                    "contribution_change_explanation": "",
                    "tokens": {
                        "frame_style": "inset",
                        "accent_geometry": "side_bar",
                        "rule_style": "double",
                        "row_marker": "bar",
                        "spacing_rhythm": "airy",
                        "header_treatment": "split",
                    },
                },
            },
        },
    )

    completed = _run_result(
        "record_creative_direction_decision.py",
        "--run-dir",
        str(run_dir),
        "--decision",
        str(selection),
        "--recorded-by",
        "test-operator",
        "--confirmed-by-user",
    )

    assert completed.returncode == 1
    assert "1080 x 1350" in completed.stderr
    assert not (run_dir / "creative-direction" / "decision-v001.json").exists()
    assert not (run_dir / "creative-direction" / "references" / "v001").exists()


def test_creative_direction_selection_changes_renderer_and_completes_lifecycle(
    tmp_path: Path,
) -> None:
    selected_root = tmp_path / "selected"
    fallback_root = tmp_path / "fallback"
    selected_root.mkdir()
    fallback_root.mkdir()
    routes = _routes()
    routes["creative_production"] = {
        "selected": True,
        "destination": "Creative Production board in the selected Codex workspace",
        "approved_by": "Dott.ssa Revisore",
        "approved_at": "2026-08-08T15:00:00+00:00",
    }
    _, selected_run, _ = _recorded_publish_run(
        selected_root,
        channels=["linkedin"],
        visual_requested=True,
        routes=routes,
    )
    _run(
        "prepare_creative_direction_handoff.py",
        "--run-dir",
        str(selected_run),
        "--directions",
        "4",
    )
    handoff = json.loads(
        (selected_run / "creative-direction" / "handoff-v001.json").read_text(
            encoding="utf-8"
        )
    )
    directions: list[dict[str, object]] = []
    for index, color in enumerate(
        ("#E9F2FF", "#FFF0DC", "#E7F7EF", "#F3ECFF"), start=1
    ):
        path = selected_root / f"direction-{index}.png"
        Image.new("RGB", (1080, 1350), color).save(path)
        directions.append(
            {
                "item_id": f"direction-{index}",
                "item_revision": index,
                "title": f"Editorial direction {index}",
                "image_path": str(path),
            }
        )
    selection = _write_json(
        selected_root / "creative-selection.json",
        {
            "schema_version": 1,
            "run_id": handoff["run_id"],
            "handoff_digest": handoff["handoff_digest"],
            "outcome": "selected",
            "selection": {
                "board_id": "board-vera-test-001",
                "board_revision": 9,
                "directions": directions,
                "selected_item_id": "direction-2",
                "selection_rationale": "La seconda direzione rende più netta la gerarchia editoriale senza aggiungere fatti né trasformare il carosello in decorazione.",
                "translation": {
                    "art_direction_summary": "Sistema editoriale con cornice sottile, accento laterale e ritmo arioso, mantenendo il testo vivo e le fonti leggibili.",
                    "exact_content_preserved": True,
                    "source_preservation_confirmed": True,
                    "contribution_change_required": False,
                    "contribution_change_explanation": "",
                    "tokens": {
                        "frame_style": "inset",
                        "accent_geometry": "side_bar",
                        "rule_style": "double",
                        "row_marker": "bar",
                        "spacing_rhythm": "airy",
                        "header_treatment": "split",
                    },
                },
            },
        },
    )
    _run(
        "record_creative_direction_decision.py",
        "--run-dir",
        str(selected_run),
        "--decision",
        str(selection),
        "--recorded-by",
        "test-operator",
        "--confirmed-by-user",
    )
    selected_workbench = json.loads(
        (selected_run / "content_workbench.json").read_text(encoding="utf-8")
    )
    bundle = _write_json(
        selected_root / "review-bundle.json",
        {
            "schema_version": 1,
            "run_id": selected_workbench["run_id"],
            "decisions": [
                {"scope": scope, "decision": "accepted", "note": ""}
                for scope in selected_workbench["required_review_scopes"]
            ],
        },
    )
    _run(
        "record_review.py",
        "--run-dir",
        str(selected_run),
        "--bundle",
        str(bundle),
        "--reviewer",
        "Dott.ssa Revisore",
        "--confirmed-by-user",
    )
    _run("render_visuals.py", "--run-dir", str(selected_run))
    _accept_rendered_output(selected_run)
    _run("package_communications.py", "--run-dir", str(selected_run))
    _accept_packaged_output(selected_run)
    _run("validate_run.py", "--run-dir", str(selected_run))
    selected_manifest = json.loads(
        (selected_run / "visual_manifest.json").read_text(encoding="utf-8")
    )
    selected_slide_hash = next(
        output["sha256"]
        for output in selected_manifest["outputs"]
        if output["path"].endswith("slide-02.png")
    )
    assert selected_manifest["creative_direction"]["route_status"] == "selected"
    assert selected_manifest["creative_direction"]["selected_item_id"] == "direction-2"
    selected_decision = json.loads(
        (selected_run / "creative-direction" / "decision-v001.json").read_text(
            encoding="utf-8"
        )
    )
    assert all(
        row["snapshot_path"].startswith("creative-direction/references/v001/")
        for row in selected_decision["selection"]["directions"]
    )
    assert (
        json.loads((selected_run / "final_artifacts.json").read_text(encoding="utf-8"))[
            "status"
        ]
        == "final_ready"
    )

    _, fallback_run, _ = _recorded_publish_run(
        fallback_root,
        channels=["linkedin"],
        visual_requested=True,
        routes=routes,
    )
    _run(
        "prepare_creative_direction_handoff.py",
        "--run-dir",
        str(fallback_run),
        "--directions",
        "4",
    )
    fallback_handoff = json.loads(
        (fallback_run / "creative-direction" / "handoff-v001.json").read_text(
            encoding="utf-8"
        )
    )
    fallback = _write_json(
        fallback_root / "creative-fallback.json",
        {
            "schema_version": 1,
            "run_id": fallback_handoff["run_id"],
            "handoff_digest": fallback_handoff["handoff_digest"],
            "outcome": "fallback",
            "selection": {
                "reason": "tool_unavailable",
                "details": "Il board non è disponibile nel runtime corrente; il run continua con il sistema visuale interno.",
            },
        },
    )
    _run(
        "record_creative_direction_decision.py",
        "--run-dir",
        str(fallback_run),
        "--decision",
        str(fallback),
        "--recorded-by",
        "test-operator",
        "--confirmed-by-user",
    )
    _run("render_visuals.py", "--run-dir", str(fallback_run), "--qa-preview")
    fallback_manifest = json.loads(
        (fallback_run / "visual_preview_manifest.json").read_text(encoding="utf-8")
    )
    fallback_slide_hash = next(
        output["sha256"]
        for output in fallback_manifest["outputs"]
        if output["path"].endswith("slide-02.png")
    )
    assert fallback_manifest["creative_direction"]["route_status"] == "fallback"
    assert selected_slide_hash != fallback_slide_hash


def _record_test_creative_selection(
    root: Path,
    run_dir: Path,
    *,
    tokens: dict[str, str],
) -> None:
    _run(
        "prepare_creative_direction_handoff.py",
        "--run-dir",
        str(run_dir),
        "--directions",
        "4",
    )
    handoff = json.loads(
        (run_dir / "creative-direction" / "handoff-v001.json").read_text(
            encoding="utf-8"
        )
    )
    directions: list[dict[str, object]] = []
    for index in range(1, 5):
        path = root / f"token-direction-{index}.png"
        Image.new("RGB", (1080, 1350), f"#{index}{index}3355").save(path)
        directions.append(
            {
                "item_id": f"token-direction-{index}",
                "item_revision": index,
                "title": f"Token direction {index}",
                "image_path": str(path),
            }
        )
    decision = _write_json(
        root / "token-selection.json",
        {
            "schema_version": 1,
            "run_id": handoff["run_id"],
            "handoff_digest": handoff["handoff_digest"],
            "outcome": "selected",
            "selection": {
                "board_id": f"board-{root.name}",
                "board_revision": 1,
                "directions": directions,
                "selected_item_id": "token-direction-1",
                "selection_rationale": "La direzione consente di verificare isolatamente che ogni token supportato modifichi il render esatto.",
                "translation": {
                    "art_direction_summary": "Direzione editoriale di prova con contenuto bloccato e variazione isolata dei token del renderer.",
                    "exact_content_preserved": True,
                    "source_preservation_confirmed": True,
                    "contribution_change_required": False,
                    "contribution_change_explanation": "",
                    "tokens": tokens,
                },
            },
        },
    )
    _run(
        "record_creative_direction_decision.py",
        "--run-dir",
        str(run_dir),
        "--decision",
        str(decision),
        "--recorded-by",
        "test-operator",
        "--confirmed-by-user",
    )


def test_creative_row_marker_and_spacing_rhythm_each_change_exact_bytes(
    tmp_path: Path,
) -> None:
    routes = _routes()
    routes["creative_production"] = {
        "selected": True,
        "destination": "Creative Production test board",
        "approved_by": "Dott.ssa Revisore",
        "approved_at": "2026-08-08T15:00:00+00:00",
    }
    common = {
        "frame_style": "hairline",
        "accent_geometry": "underline",
        "rule_style": "single",
        "row_marker": "numeral",
        "spacing_rhythm": "compact",
        "header_treatment": "solid",
    }
    hashes: list[str] = []
    token_sets = [
        common,
        {**common, "row_marker": "bar"},
        {**common, "spacing_rhythm": "airy"},
    ]
    for index, tokens in enumerate(token_sets, start=1):
        case_root = tmp_path / f"tokens-{index}"
        case_root.mkdir()
        _, run_dir, _ = _recorded_publish_run(
            case_root,
            channels=["linkedin"],
            visual_requested=True,
            routes=routes,
        )
        _record_test_creative_selection(case_root, run_dir, tokens=tokens)
        _run("render_visuals.py", "--run-dir", str(run_dir), "--qa-preview")
        manifest = json.loads(
            (run_dir / "visual_preview_manifest.json").read_text(encoding="utf-8")
        )
        assert manifest["quality_gate"]["creative_tokens_consumed"] == sorted(tokens)
        hashes.append(
            next(
                row["sha256"]
                for row in manifest["outputs"]
                if row["path"].endswith("slide-02.png")
            )
        )

    assert len(set(hashes)) == 3


def test_creative_manifest_does_not_claim_inapplicable_row_marker(
    tmp_path: Path,
) -> None:
    routes = _routes()
    routes["creative_production"] = {
        "selected": True,
        "destination": "Creative Production test board",
        "approved_by": "Dott.ssa Revisore",
        "approved_at": "2026-08-08T15:00:00+00:00",
    }
    contribution = _publish_contribution()
    for slide in contribution["visual_story"]["slides"]:
        slide["bullets"] = []
    _, run_dir, _ = _recorded_publish_run(
        tmp_path,
        channels=["linkedin"],
        visual_requested=True,
        routes=routes,
        contribution=contribution,
    )
    tokens = {
        "frame_style": "hairline",
        "accent_geometry": "underline",
        "rule_style": "single",
        "row_marker": "bar",
        "spacing_rhythm": "compact",
        "header_treatment": "solid",
    }
    _record_test_creative_selection(tmp_path, run_dir, tokens=tokens)

    _run("render_visuals.py", "--run-dir", str(run_dir), "--qa-preview")

    manifest = json.loads(
        (run_dir / "visual_preview_manifest.json").read_text(encoding="utf-8")
    )
    quality_gate = manifest["quality_gate"]
    assert quality_gate["creative_tokens_not_applicable"] == ["row_marker"]
    assert quality_gate["creative_tokens_consumed"] == sorted(
        name for name in tokens if name != "row_marker"
    )


def test_superseded_final_render_can_be_rendered_and_packaged_again(
    tmp_path: Path,
) -> None:
    _, run_dir, contribution = _recorded_publish_run(
        tmp_path,
        channels=["linkedin"],
        visual_requested=True,
    )
    _accept_required_reviews(run_dir)
    _run("render_visuals.py", "--run-dir", str(run_dir))
    _accept_rendered_output(run_dir)
    _run("package_communications.py", "--run-dir", str(run_dir))
    _accept_packaged_output(run_dir)
    _run("validate_run.py", "--run-dir", str(run_dir))
    first_manifest = json.loads(
        (run_dir / "visual_manifest.json").read_text(encoding="utf-8")
    )

    _run(
        "record_review.py",
        "--run-dir",
        str(run_dir),
        "--scope",
        "copy",
        "--decision",
        "returned",
        "--reviewer",
        "Dott.ssa Revisore",
        "--confirmed-by-user",
    )
    revised = _clone(contribution)
    revised["channel_drafts"][0][
        "title"
    ] = "Una data ufficiale, tre verifiche prima di concludere"
    answer = _answer_contract(revised)
    assurance = _claim_assurance(revised, answer)
    assurance["assessment_protocol"]["assessor_session_id"] = "test-claim-session-002"
    editorial = _editorial_assessment(revised, answer_contract=answer)
    editorial["assessment_protocol"][
        "assessor_session_id"
    ] = "test-editorial-session-002"
    editorial["claim_assurance_digest"] = _canonical_digest(assurance)
    contribution_path = _write_json(tmp_path / "revised-contribution.json", revised)
    answer_path = _write_json(tmp_path / "revised-answer.json", answer)
    assurance_path = _write_json(tmp_path / "revised-assurance.json", assurance)
    editorial_path = _write_json(tmp_path / "revised-editorial.json", editorial)

    _run(
        "record_contribution.py",
        "--run-dir",
        str(run_dir),
        "--contribution",
        str(contribution_path),
        "--answer-contract",
        str(answer_path),
        "--claim-assurance",
        str(assurance_path),
        "--editorial-assessment",
        str(editorial_path),
        "--provider",
        "test-provider",
        "--model",
        "test-model",
        "--template-version",
        "professional-communication-v3",
        "--generation-session-id",
        "test-generation-session-002",
        "--recorded-by",
        "test-operator",
        "--assessment-provider",
        "test-provider",
        "--assessment-model",
        "test-editor-model",
        "--claim-assessment-provider",
        "test-provider",
        "--claim-assessment-model",
        "test-claim-model",
        "--supersede",
    )

    archived_manifest = json.loads(
        (run_dir / "versions" / "artifacts-v001" / "visual_manifest.json").read_text(
            encoding="utf-8"
        )
    )
    assert archived_manifest["manifest_digest"] == first_manifest["manifest_digest"]
    assert (run_dir / "versions" / "artifacts-v001" / "drafts").is_dir()
    assert not (run_dir / "visual_manifest.json").exists()

    _accept_required_reviews(run_dir)
    _run("render_visuals.py", "--run-dir", str(run_dir))
    _accept_rendered_output(run_dir)
    _run("package_communications.py", "--run-dir", str(run_dir))
    _accept_packaged_output(run_dir)
    _run("validate_run.py", "--run-dir", str(run_dir))
    final = json.loads((run_dir / "final_artifacts.json").read_text(encoding="utf-8"))
    assert final["status"] == "final_ready"
    assert (
        json.loads((run_dir / "content_workbench.json").read_text(encoding="utf-8"))[
            "version"
        ]
        == 2
    )


def test_model_passes_reject_reused_host_session(
    tmp_path: Path,
) -> None:
    _, run_dir, contribution = _recorded_publish_run(
        tmp_path,
        channels=["client_email"],
        visual_requested=False,
    )
    _run(
        "record_review.py",
        "--run-dir",
        str(run_dir),
        "--scope",
        "copy",
        "--decision",
        "returned",
        "--reviewer",
        "Dott.ssa Revisore",
        "--confirmed-by-user",
    )
    answer = _answer_contract(contribution)
    assurance = _claim_assurance(contribution, answer)
    assurance["assessment_protocol"][
        "assessor_session_id"
    ] = "test-generation-session-002"
    editorial = _editorial_assessment(contribution, answer_contract=answer)
    editorial["assessment_protocol"][
        "assessor_session_id"
    ] = "test-editorial-session-002"
    editorial["claim_assurance_digest"] = _canonical_digest(assurance)

    completed = _run_result(
        "record_contribution.py",
        "--run-dir",
        str(run_dir),
        "--contribution",
        str(_write_json(tmp_path / "same-session-contribution.json", contribution)),
        "--answer-contract",
        str(_write_json(tmp_path / "same-session-answer.json", answer)),
        "--claim-assurance",
        str(_write_json(tmp_path / "same-session-assurance.json", assurance)),
        "--editorial-assessment",
        str(_write_json(tmp_path / "same-session-editorial.json", editorial)),
        "--provider",
        "test-provider",
        "--model",
        "test-model",
        "--template-version",
        "professional-communication-v3",
        "--generation-session-id",
        "test-generation-session-002",
        "--recorded-by",
        "test-operator",
        "--assessment-provider",
        "test-provider",
        "--assessment-model",
        "test-editor-model",
        "--claim-assessment-provider",
        "test-provider",
        "--claim-assessment-model",
        "test-claim-model",
        "--supersede",
    )

    assert completed.returncode == 1
    assert "must use distinct host sessions" in completed.stderr


def test_changed_editorial_template_digest_requires_fresh_qualification(
    tmp_path: Path,
) -> None:
    workspace = tmp_path / "studio-workspace"
    _run(
        "initialize_workspace.py",
        "--workspace",
        str(workspace),
        "--workspace-id",
        "studio-aurora",
        "--owner",
        "Studio Aurora",
        "--retention-owner",
        "Studio Aurora",
        "--confirmed-by-user",
    )
    expectations = json.loads(
        (PLUGIN / "evals" / "editorial_quality_expected.json").read_text(
            encoding="utf-8"
        )
    )["expectations"]
    results = _write_json(
        tmp_path / "stale-template-benchmark.json",
        {
            "schema_version": 1,
            "provider": "test-provider",
            "model": "test-editor-model",
            "assessment_template_version": "professional-communication-editorial-v4",
            "template_sha256": "0" * 64,
            "assessor_session_id": "stale-template-session-001",
            "evaluated_at": "2026-08-08T11:00:00+00:00",
            "judgments": [
                {
                    "case_id": row["case_id"],
                    "verdict": row["expected_verdict"],
                    "analysis": "Il test usa i risultati attesi ma un digest di template deliberatamente non corrente.",
                }
                for row in expectations
            ],
        },
    )

    completed = _run_result(
        "qualify_editorial_assessor.py",
        "--workspace",
        str(workspace),
        "--results",
        str(results),
        "--recorded-by",
        "test-operator",
    )

    assert completed.returncode == 1
    assert "template digest mismatch" in completed.stderr


def test_new_studio_without_history_can_adopt_a_reviewed_vera_profile(
    tmp_path: Path,
) -> None:
    _, run_dir, contribution = _recorded_publish_run(
        tmp_path,
        channels=["website_article"],
        visual_requested=False,
        include_history=False,
        studio_format_brief="Studio sobrio, titoli informativi e fonti pubbliche identificabili.",
    )
    profile = contribution["studio_profile_proposal"]
    assert profile["derived_from_history_ids"] == []
    assert {row["basis"] for row in profile["field_provenance"]} == {
        "vera_default_proposal"
    }
    _accept_required_reviews(run_dir)
    _run("promote_studio_profile.py", "--run-dir", str(run_dir))
    _run("package_communications.py", "--run-dir", str(run_dir))
    _accept_packaged_output(run_dir)
    _run("validate_run.py", "--run-dir", str(run_dir))
    assert (run_dir.parent.parent / "studio_profile.json").is_file()


def test_packaging_preserves_reviewed_public_sources_and_output_language(
    tmp_path: Path,
) -> None:
    contribution = _clone(_publish_contribution())
    contribution["studio_profile_proposal"]["website"]["source_heading"] = "Sources"
    newsletter = _clone(contribution["channel_drafts"][3])
    newsletter["channel"] = "newsletter"
    newsletter["title"] = "Measure update: facts and verification"
    contribution["channel_drafts"].append(newsletter)
    for draft in contribution["channel_drafts"]:
        for note in draft["public_source_notes"]:
            note["public_url"] = "https://example.test/provvedimento-12345-2026"
    exact_source = (
        "Agenzia delle Entrate — Provvedimento n. 12345/2026 dell'8 agosto 2026"
    )
    _, run_dir, _ = _recorded_publish_run(
        tmp_path,
        channels=["client_email", "linkedin", "newsletter", "website_article"],
        visual_requested=True,
        contribution=contribution,
        language="en",
    )
    _run("render_visuals.py", "--run-dir", str(run_dir), "--qa-preview")
    preview = (run_dir / "visuals-preview" / "visual-preview.html").read_text(
        encoding="utf-8"
    )
    assert '<html lang="en">' in preview
    _accept_required_reviews(run_dir)
    _run("render_visuals.py", "--run-dir", str(run_dir))
    _accept_rendered_output(run_dir)
    _run("package_communications.py", "--run-dir", str(run_dir))
    for relative in (
        "drafts/client_email.txt",
        "drafts/linkedin.txt",
        "drafts/newsletter.md",
        "drafts/website_article.html",
    ):
        assert exact_source in html_lib.unescape(
            (run_dir / relative).read_text(encoding="utf-8")
        )
    email = (run_dir / "drafts" / "client_email.txt").read_text(encoding="utf-8")
    newsletter = (run_dir / "drafts" / "newsletter.md").read_text(encoding="utf-8")
    website = (run_dir / "drafts" / "website_article.html").read_text(encoding="utf-8")
    assert email.startswith("Subject:")
    assert "## Sources" in newsletter
    assert '<html lang="en">' in website
    assert 'href="https://example.test/provvedimento-12345-2026"' in website
    assert "Fonti e aggiornamento disponibili" not in website


def test_circular_wraps_long_contact_text_without_silent_truncation(
    tmp_path: Path,
) -> None:
    contribution = _clone(_publish_contribution())
    long_contact = "studio-" + "commercialistiassociati" * 8 + ".example"
    contribution["studio_profile_proposal"]["document"]["contact_rail_lines"] = [
        "Studio Aurora",
        long_contact,
    ]
    _, run_dir, _ = _recorded_publish_run(
        tmp_path,
        channels=["client_circular"],
        visual_requested=False,
        contribution=contribution,
    )
    _accept_required_reviews(run_dir)
    _run("render_visuals.py", "--run-dir", str(run_dir))
    manifest = json.loads(
        (run_dir / "visual_manifest.json").read_text(encoding="utf-8")
    )
    circular = next(
        row for row in manifest["outputs"] if row["kind"] == "client_circular_pdf"
    )
    validation = circular["layout_validation"]
    assert validation["silent_truncation"] is False
    assert validation["contact_rail_exact"] is True
    extracted = "".join(
        page.extract_text() or ""
        for page in PdfReader(str(run_dir / circular["path"])).pages
    )
    assert "".join(
        character for character in long_contact if character.isalnum()
    ) in "".join(character for character in extracted if character.isalnum())


def test_circular_rejects_contact_rail_that_cannot_fit(
    tmp_path: Path,
) -> None:
    contribution = _clone(_publish_contribution())
    contribution["studio_profile_proposal"]["document"]["contact_rail_lines"] = [
        f"{index:02d}-" + "commercialistiassociati" * 12 for index in range(40)
    ]
    _, run_dir, _ = _recorded_publish_run(
        tmp_path,
        channels=["client_circular"],
        visual_requested=False,
        contribution=contribution,
    )
    _accept_required_reviews(run_dir)

    completed = _run_result("render_visuals.py", "--run-dir", str(run_dir))

    assert completed.returncode == 1
    assert "contact rail cannot fit" in completed.stderr
    assert not (run_dir / "visual_manifest.json").exists()
    assert not (run_dir / "visuals" / "circolare-clienti.pdf").exists()


def test_claim_assurance_must_review_every_answer_contract_dimension(
    tmp_path: Path,
) -> None:
    _, run_dir, contribution = _recorded_publish_run(
        tmp_path,
        channels=["client_email"],
        visual_requested=False,
    )
    _run(
        "record_review.py",
        "--run-dir",
        str(run_dir),
        "--scope",
        "claims",
        "--decision",
        "returned",
        "--reviewer",
        "Dott.ssa Revisore",
        "--confirmed-by-user",
    )
    answer = _answer_contract(contribution)
    assurance = _claim_assurance(contribution, answer)
    del assurance["contract_review"]["source_hierarchy"]
    editorial = _editorial_assessment(contribution, answer_contract=answer)
    editorial["claim_assurance_digest"] = _canonical_digest(assurance)

    completed = _run_result(
        "record_contribution.py",
        "--run-dir",
        str(run_dir),
        "--contribution",
        str(_write_json(tmp_path / "contract-contribution.json", contribution)),
        "--answer-contract",
        str(_write_json(tmp_path / "contract-answer.json", answer)),
        "--claim-assurance",
        str(_write_json(tmp_path / "contract-assurance.json", assurance)),
        "--editorial-assessment",
        str(_write_json(tmp_path / "contract-editorial.json", editorial)),
        "--provider",
        "test-provider",
        "--model",
        "test-model",
        "--template-version",
        "professional-communication-v3",
        "--generation-session-id",
        "test-generation-session-002",
        "--recorded-by",
        "test-operator",
        "--assessment-provider",
        "test-provider",
        "--assessment-model",
        "test-editor-model",
        "--claim-assessment-provider",
        "test-provider",
        "--claim-assessment-model",
        "test-claim-model",
        "--supersede",
    )

    assert completed.returncode == 1
    assert "source_hierarchy" in completed.stderr
