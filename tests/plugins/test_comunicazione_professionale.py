from __future__ import annotations

import hashlib
import importlib
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest
from PIL import Image

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


def _profile() -> dict[str, object]:
    return {
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
            "source_note": "Fonti e aggiornamento disponibili presso lo Studio.",
            "cta": "Contattate lo Studio per verificare la situazione specifica.",
            "show_update_date": True,
        },
        "social": {
            "preferred_format": "portrait_carousel",
            "opening_style": "Un fatto concreto, senza allarmismo.",
            "closing_style": "Invito a verificare l'applicabilità con il professionista.",
            "hashtags": ["#fisco", "#imprese"],
            "show_source_note": True,
        },
    }


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
                "sections": [],
            },
            {
                "channel": "website_article",
                "title": "Nuova misura: dalla data alla verifica concreta",
                "body": "Il provvedimento ufficiale porta la misura nella fase operativa.",
                "claim_ids": claim_ids,
                "audience_note": "Imprese che cercano un primo orientamento.",
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
            "title": "Nuova misura, verifica concreta",
            "slides": [
                {
                    "kind": "cover",
                    "eyebrow": "Aggiornamento professionale",
                    "title": "Una nuova data. Prima, una verifica concreta.",
                    "body": "La misura entra nella fase operativa il 30 settembre 2026.",
                    "bullets": [],
                    "highlight": "30.09.2026",
                    "source_ids": source_ids,
                },
                {
                    "kind": "audience",
                    "eyebrow": "Perimetro",
                    "title": "Non riguarda automaticamente ogni impresa",
                    "body": "Soggetto, attività e documentazione determinano il percorso di verifica.",
                    "bullets": [
                        "Confermare il perimetro",
                        "Evitare conclusioni standard",
                    ],
                    "highlight": "",
                    "source_ids": source_ids,
                },
                {
                    "kind": "action",
                    "eyebrow": "Passo utile",
                    "title": "Preparare i documenti, poi decidere",
                    "body": "Lo Studio può verificare l'applicabilità prima della decorrenza.",
                    "bullets": ["Raccogliere le evidenze", "Valutare il caso concreto"],
                    "highlight": "",
                    "source_ids": source_ids,
                },
            ],
        },
    }


def _clone(payload: dict[str, object]) -> dict[str, object]:
    return json.loads(json.dumps(payload))


def _recorded_publish_run(
    tmp_path: Path,
    *,
    channels: list[str],
    visual_requested: bool,
    contribution: dict[str, object] | None = None,
    brand: dict[str, str] | None = None,
    routes: dict[str, dict[str, object]] | None = None,
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
    prepared_contribution["channel_drafts"] = [
        draft
        for draft in prepared_contribution["channel_drafts"]
        if draft["channel"] in channels
    ]
    if not visual_requested:
        prepared_contribution["visual_story"] = {"title": "", "slides": []}
    intake_payload: dict[str, object] = {
        "schema_version": 1,
        "run_id": prepared_contribution["run_id"],
        "reference_date": "2026-08-08",
        "language": "it",
        "jurisdiction": "Italia",
        "objective": "Spiegare la misura senza assumere applicabilità automatica.",
        "audience": "Clienti impresa potenzialmente interessati",
        "channels": channels,
        "visual_requested": visual_requested,
        "source_inputs": [
            {
                "id": "SRC-001",
                "path": str(source),
                "title": "Provvedimento ufficiale sulla misura",
                "authority_role": "primary",
            }
        ],
        "history_inputs": [
            {"id": "HIST-001", "path": str(history), "channel": "client_circular"}
        ],
        "brand_profile": brand or _brand(),
        "external_routes": routes or _routes(),
    }
    intake = _write_json(tmp_path / "intake.json", intake_payload)
    contribution_path = _write_json(
        tmp_path / "contribution.json", prepared_contribution
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
    run_dir = workspace / "runs" / str(prepared_contribution["run_id"])
    _run(
        "record_contribution.py",
        "--run-dir",
        str(run_dir),
        "--contribution",
        str(contribution_path),
        "--provider",
        "test-provider",
        "--model",
        "test-model",
        "--template-version",
        "professional-communication-v1",
        "--recorded-by",
        "test-operator",
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
    contribution = _write_json(tmp_path / "contribution.json", _publish_contribution())

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
    run_dir = workspace / "runs" / "norma-2026-001"
    _run(
        "record_contribution.py",
        "--run-dir",
        str(run_dir),
        "--contribution",
        str(contribution),
        "--provider",
        "test-provider",
        "--model",
        "test-model",
        "--template-version",
        "professional-communication-v1",
        "--recorded-by",
        "test-operator",
    )
    _accept_required_reviews(run_dir)
    _run("promote_studio_profile.py", "--run-dir", str(run_dir))
    _run("render_visuals.py", "--run-dir", str(run_dir))
    _accept_rendered_output(run_dir)
    _run("package_communications.py", "--run-dir", str(run_dir))
    _accept_packaged_output(run_dir)
    _run("validate_run.py", "--run-dir", str(run_dir))
    final = json.loads((run_dir / "final_artifacts.json").read_text(encoding="utf-8"))
    email = (run_dir / "drafts" / "client_email.txt").read_text(encoding="utf-8")
    website = (run_dir / "drafts" / "website_article.html").read_text(encoding="utf-8")
    linkedin = (run_dir / "drafts" / "linkedin.txt").read_text(encoding="utf-8")
    assert final["status"] == "final_ready"
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
            "visual_story": {"title": "", "slides": []},
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
    run_dir = workspace / "runs" / "no-slop-2026-001"
    _run(
        "record_contribution.py",
        "--run-dir",
        str(run_dir),
        "--contribution",
        str(contribution),
        "--provider",
        "test-provider",
        "--model",
        "test-model",
        "--template-version",
        "professional-communication-v1",
        "--recorded-by",
        "test-operator",
    )
    _accept_required_reviews(run_dir)
    _run("package_communications.py", "--run-dir", str(run_dir))
    _accept_packaged_output(run_dir)
    _run("validate_run.py", "--run-dir", str(run_dir))
    final = json.loads((run_dir / "final_artifacts.json").read_text(encoding="utf-8"))
    assert final["status"] == "no_publication_recommended"
    assert (run_dir / "no-publication-recommendation.md").is_file()
    assert not (run_dir / "drafts").exists()


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
