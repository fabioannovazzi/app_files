"""Run fictional practice inputs through current registry preparation and review.

The authored plan and widget choices are regression fixtures, not a professional
or learner approval. No portal or network action is performed by these checks.
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest

from tests.plugins.test_teaching_kit_execution import (
    _bound_case,
    _complete_teaching_case,
    _read,
    _run,
    _write,
)

ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = "plugins/registro-imprese-sari/scripts/"
TEXT = {
    "it": {
        "summary": "Preparare la variazione della PEC aziendale di Officina Riva S.r.l. sulla base della richiesta fittizia. Nessuna pratica è stata depositata.",
        "request": "Variazione della PEC aziendale; nessun’altra variazione dichiarata.",
        "fact": "Società a responsabilità limitata con sede a Milano; dati dichiarati da verificare.",
        "position": "Valutare la variazione del domicilio digitale della società nel Registro Imprese.",
        "route": "Predisporre il percorso di variazione dopo verifica delle indicazioni attuali e dell’incarico; non compilare o inviare nel portale. Modelli e campi DIRE specifici restano da verificare.",
        "documents": "Acquisire visura aggiornata, prova dell’attivazione e titolarità della PEC e documentazione dell’incarico. Le note didattiche non li sostituiscono.",
        "field": "Indirizzo PEC e data dichiarati dal cliente, da verificare prima della compilazione.",
        "risk": "La disponibilità effettiva del nuovo indirizzo non è documentata; evitare un deposito basato soltanto sulla richiesta.",
        "missing": "Manca la prova di attivazione del nuovo indirizzo.",
        "question": "Per la sola variazione della PEC aziendale di una S.r.l. con sede nel territorio, quali indicazioni attuali occorre verificare prima della predisposizione della pratica?",
        "limit": "Caso fittizio, fonti iniziali pubbliche, nessuna scheda SARI selezionata; dettagli applicativi e disponibilità PEC da verificare. Nessun accesso o deposito.",
    },
    "en": {
        "summary": "Prepare the company PEC change for fictional Officina Riva S.r.l. from its supplied request. No filing has been submitted.",
        "request": "Company PEC address change; no other change is stated.",
        "fact": "Limited-liability company based in Milan; declared facts need verification.",
        "position": "Assess the company digital-address change in Registro Imprese.",
        "route": "Prepare the change procedure after checking current guidance and the engagement; do not fill in or submit on the portal. Exact DIRE forms and fields remain to be checked.",
        "documents": "Obtain a current registry extract, evidence of PEC activation and ownership, and engagement documentation. Lesson notes do not replace these.",
        "field": "Client-stated PEC address and date, to be verified before compilation.",
        "risk": "Actual availability of the new address is undocumented; the request alone is insufficient for filing.",
        "missing": "Evidence of the new address activation is missing.",
        "question": "For only a company PEC change by a locally based S.r.l., which current guidance must be checked before preparing the practice?",
        "limit": "Fictional case and initial public sources; no SARI card selected. Application details and PEC availability remain to be checked. No login or filing.",
    },
    "fr": {
        "summary": "Préparer le changement de PEC de la société fictive Officina Riva S.r.l. à partir de sa demande. Aucun dépôt effectué.",
        "request": "Changement de PEC de la société ; aucune autre modification déclarée.",
        "fact": "Société à responsabilité limitée établie à Milan ; faits déclarés à vérifier.",
        "position": "Examiner le changement du domicile numérique de la société au Registro Imprese.",
        "route": "Préparer le parcours après vérification des indications actuelles et du mandat, sans saisir ni transmettre sur le portail. Modèles et champs DIRE précis restent à vérifier.",
        "documents": "Obtenir un extrait actuel du registre, la preuve d’activation et de titularité de la PEC et les pièces du mandat. Les notes pédagogiques ne les remplacent pas.",
        "field": "Adresse PEC et date déclarées par le client, à vérifier avant saisie.",
        "risk": "La disponibilité effective de la nouvelle adresse n’est pas documentée ; ne pas déposer sur la seule demande.",
        "missing": "La preuve d’activation de la nouvelle adresse manque.",
        "question": "Pour le seul changement de PEC d’une S.r.l. établie sur le territoire, quelles indications actuelles vérifier avant de préparer le dossier ?",
        "limit": "Cas fictif et références publiques initiales ; aucune fiche SARI sélectionnée. Modalités et disponibilité PEC à vérifier. Aucune connexion ni aucun dépôt.",
    },
    "de": {
        "summary": "Änderung der Firmen-PEC von Officina Riva S.r.l. anhand des fiktiven Auftrags vorbereiten. Nichts wurde eingereicht.",
        "request": "Änderung der Firmen-PEC; keine weitere Änderung angegeben.",
        "fact": "Gesellschaft mit beschränkter Haftung mit Sitz in Mailand; Angaben müssen geprüft werden.",
        "position": "Änderung der digitalen Unternehmensadresse im Registro Imprese prüfen.",
        "route": "Änderung nach Prüfung aktueller Hinweise und des Auftrags vorbereiten; keine Eingabe oder Übermittlung im Portal. Genaue DIRE-Formulare und Felder sind noch zu prüfen.",
        "documents": "Aktuellen Registerauszug, Beleg über Aktivierung und Inhaberschaft der PEC sowie Auftragsunterlagen beschaffen. Unterrichtsnotizen ersetzen diese nicht.",
        "field": "Vom Mandanten genannte PEC-Adresse und Datum vor der Eingabe prüfen.",
        "risk": "Die tatsächliche Verfügbarkeit der neuen Adresse ist nicht belegt; der Auftrag allein reicht für eine Einreichung nicht aus.",
        "missing": "Der Aktivierungsnachweis für die neue Adresse fehlt.",
        "question": "Welche aktuellen Hinweise sind für die ausschließliche Änderung der Firmen-PEC einer örtlichen S.r.l. vor der Vorbereitung zu prüfen?",
        "limit": "Fiktiver Fall und öffentliche Ausgangsquellen; keine SARI-Karte ausgewählt. Einzelheiten und PEC-Verfügbarkeit sind zu prüfen. Kein Login und keine Einreichung.",
    },
    "es": {
        "summary": "Preparar el cambio de PEC de la sociedad ficticia Officina Riva S.r.l. a partir del encargo aportado. No se ha presentado ningún trámite.",
        "request": "Cambio de PEC empresarial; no se declara otra modificación.",
        "fact": "Sociedad de responsabilidad limitada con sede en Milán; datos declarados que verificar.",
        "position": "Examinar el cambio del domicilio digital de la sociedad en el Registro Imprese.",
        "route": "Preparar el recorrido tras comprobar indicaciones actuales y encargo, sin rellenar ni enviar en el portal. Modelos y campos DIRE exactos siguen pendientes de comprobación.",
        "documents": "Obtener extracto registral actual, prueba de activación y titularidad de la PEC y documentación del encargo. Las notas didácticas no los sustituyen.",
        "field": "PEC y fecha declaradas por el cliente, que verificar antes de rellenar.",
        "risk": "No se documenta la disponibilidad efectiva de la nueva dirección; el encargo solo no basta para presentar el trámite.",
        "missing": "Falta la prueba de activación de la nueva dirección.",
        "question": "Para cambiar únicamente la PEC empresarial de una S.r.l. con sede en el territorio, ¿qué indicaciones actuales deben verificarse antes de preparar el trámite?",
        "limit": "Caso ficticio y referencias públicas iniciales; ninguna ficha SARI seleccionada. Detalles y disponibilidad PEC pendientes. Sin acceso ni presentación.",
    },
}


TITLES = {
    "it": [
        "Società e sede",
        "Posizione Registro Imprese",
        "Preparazione della pratica",
        "Documenti da acquisire",
        "Dati proposti",
        "Controllo prima del deposito",
        "Attivazione PEC da documentare",
    ],
    "en": [
        "Company and registered office",
        "Registro Imprese position",
        "Practice preparation",
        "Documents to obtain",
        "Proposed data",
        "Pre-filing check",
        "PEC activation evidence needed",
    ],
    "fr": [
        "Société et siège",
        "Position au Registro Imprese",
        "Préparation du dossier",
        "Pièces à obtenir",
        "Données proposées",
        "Contrôle avant dépôt",
        "Activation PEC à documenter",
    ],
    "de": [
        "Unternehmen und Sitz",
        "Registro-Imprese-Position",
        "Vorbereitung des Vorgangs",
        "Benötigte Unterlagen",
        "Vorgeschlagene Angaben",
        "Prüfung vor Einreichung",
        "PEC-Aktivierung belegen",
    ],
    "es": [
        "Sociedad y domicilio",
        "Posición Registro Imprese",
        "Preparación del trámite",
        "Documentos que obtener",
        "Datos propuestos",
        "Control previo a presentación",
        "Documentar la activación PEC",
    ],
}
ACTIVITY = {
    "it": "Manutenzione di macchinari, secondo la richiesta fittizia",
    "en": "Machinery maintenance, as stated in the fictional input",
    "fr": "Entretien de machines, selon la demande fictive",
    "de": "Maschinenwartung laut fiktivem Auftrag",
    "es": "Mantenimiento de maquinaria, según el encargo ficticio",
}


@pytest.mark.parametrize("language", TEXT)
@pytest.mark.parametrize("phase", ["demo", "practice"])
def test_registro_kit_uses_current_plan_package_and_preserves_pending_review(
    tmp_path, monkeypatch, language, phase
):
    run = _bound_case(
        tmp_path,
        monkeypatch,
        "registro-imprese-sari",
        "registro-imprese-sari",
        phase,
        language=language,
    )
    output = Path(run["output_dir"])
    inputs = Path(run["context"]["run_root"]) / "inputs"
    args = ["--client-engagement", run["context_path"], "--output-dir", output]
    _run(
        SCRIPTS + "initialize_case.py",
        *args,
        "--reference-date",
        "2026-09-14",
        "--client-reference",
        "OFFICINA-RIVA-FICTIONAL",
        "--language",
        language,
    )
    _run(SCRIPTS + "inventory_case.py", inputs, *args, "--no-ocr")
    text = TEXT[language]
    company = next(inputs.rglob(f"company-{language}.md")).read_text()
    current = (
        company
        if phase == "demo"
        else next(inputs.rglob(f"update-{language}.md")).read_text()
    )
    address = (
        "societa@riva-nuova.invalid"
        if phase == "demo"
        else "amministrazione@riva-nuova.invalid"
    )
    date = "2026-09-21" if phase == "demo" else "2026-09-28"
    assert address in current
    intake = _read(output / "case_intake_draft.json")
    intake.update(
        {
            "client_identity": {"name": "Officina Riva S.r.l.", "pec": address},
            "competent_chamber": {
                "tenant": "unselected",
                "name": "Camera di commercio Milano Monza Brianza Lodi",
                "territorial_basis": "Milano; fictional company facts",
                "confirmation_status": "needs_professional_review",
            },
            "subject": {
                "legal_form": "S.r.l.",
                "confirmation_status": "needs_professional_review",
            },
            "activity": {
                "description": ACTIVITY[language],
                "classification_status": "needs_professional_review",
                "ateco_proposal": None,
            },
            "requested_operation": {
                "description": text["request"],
                "position_types": ["registro_imprese"],
                "effective_date": date,
                "confirmation_status": "needs_professional_review",
            },
            "professional_question": text["summary"],
        }
    )
    _write(output / "case_intake_draft.json", intake)
    refs = _read(next(inputs.rglob("source-index.json")))["references"]
    for ref in refs:
        _run(
            SCRIPTS + "register_official_source.py",
            *args,
            "--source-id",
            ref["id"],
            "--source-type",
            (
                "official_registro_imprese_guidance"
                if ref["id"] == "RI-COMPANIES"
                else "official_cciaa_guidance"
            ),
            "--title",
            ref["title"],
            "--official-url",
            ref["url"],
            "--publisher",
            ref["publisher"],
            "--territorial-applicability",
            ref["territory"],
            "--authorization-basis",
            "browser_assisted_metadata",
            "--authorization-reference",
            "PUBLIC-REFERENCE-CHECKED-2026-09-14",
            "--selected-by",
            "Test-authored model selection; professional applicability pending",
        )

    titles = dict(
        zip(
            ("fact", "position", "route", "documents", "field", "risk", "missing"),
            TITLES[language],
            strict=True,
        )
    )

    def item(key, section, *, status="proposed", value=None):
        return {
            "id": key.upper(),
            "title": titles[section],
            "detail": text[section],
            "source_ids": ["CASE-INTAKE", "RI-COMPANIES"],
            "case_fact_ids": [
                "CASE-CLIENT",
                "CASE-CHAMBER",
                "CASE-OPERATION",
                "CASE-EFFECTIVE-DATE",
            ],
            "review_status": status,
            "proposed_value": value,
        }

    plan = _read(output / "practice_plan_draft.json")
    plan.update(
        {
            "case_summary": text["summary"],
            "classification_proposals": [item("fact", "fact")],
            "position_matrix": [item("position", "position")],
            "dire_steps": [item("route", "route")],
            "required_documents": [item("documents", "documents")],
            "application_fields": [
                item("pec", "field", value=address),
                item("effective-date", "field", value=date),
            ],
            "risks": [item("risk", "risk")],
            "missing_information": [item("missing", "missing", status="blocked")],
            "sari_question_draft": text["question"],
            "limitations": [text["limit"]],
            "professional_review": {"status": "pending"},
        }
    )
    _write(output / "practice_plan_draft.json", plan)
    _run(
        SCRIPTS + "validate_practice_case.py",
        *args,
        "--case-intake",
        output / "case_intake_draft.json",
        "--practice-plan",
        output / "practice_plan_draft.json",
        "--official-sources",
        output / "official_sources.json",
        "--local-inventory",
        output / "local_evidence_inventory.json",
    )
    _run(SCRIPTS + "package_practice.py", *args)
    audit = _read(output / "practice_validation_audit.json")
    final = _read(output / "final_artifacts.json")
    assert audit["status"] == "passed_with_blockers"
    assert final["status"] == "partial_review"
    assert final["ready_to_file"] is False
    assert (output / "studio_checklist.md").is_file()
    assert address in (output / "studio_checklist.md").read_text()
    assert (
        _read(output / "dire_practice_plan.json")["professional_review"]["status"]
        == "pending"
    )
    assert _read(output / "ui_decisions.json")["status"] == "pending_review"
    assert _read(output / "official_sources.json")["source_count"] == 2
    _exercise_review(run, output)
    _complete_teaching_case(run, tmp_path / "case")


def _exercise_review(run, output):
    """Exercise an explicit synthetic request for documents via normal opaque references."""
    from tests.plugins.test_registro_imprese_sari_plugin import _node_or_skip

    process = subprocess.Popen(
        [
            _node_or_skip(),
            str(ROOT / "plugins/registro-imprese-sari/mcp/server.cjs"),
            "--stdio",
        ],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    assert process.stdin and process.stdout and process.stderr
    sequence = 0

    def call(name, arguments):
        nonlocal sequence
        sequence += 1
        process.stdin.write(
            json.dumps(
                {
                    "jsonrpc": "2.0",
                    "id": sequence,
                    "method": "tools/call",
                    "params": {"name": name, "arguments": arguments},
                }
            )
            + "\n"
        )
        process.stdin.flush()
        response = json.loads(process.stdout.readline())
        result = response["result"]
        assert not result.get("isError"), result
        return result["structuredContent"]

    try:
        review = _read(output / "review_payload.json")
        validated = call(
            "validate_registro_imprese_sari_review",
            {
                "client_engagement": str(run["context_path"]),
                "run_intake": _read(output / "run_intake.json"),
                "review_payload": review,
            },
        )
        token = validated["review_reference"]["persistence_token"]
        rendered = call(
            "render_registro_imprese_sari_review", {"persistence_token": token}
        )
        assert rendered["persistence_available"] is True
        decision = {
            "item_id": "plan-MISSING",
            "action": "request_more_documents",
            "requested_documents": [
                "Synthetic request for the missing PEC activation evidence"
            ],
            "note": "Synthetic integration-test request; no real professional or learner action.",
        }
        widget = {
            "persistence_token": rendered["persistence_token"],
            "decisions": [decision],
            "decision_source": "mcp_widget",
        }
        saved = call("save_registro_imprese_sari_decisions", widget)
        applied = call("apply_registro_imprese_sari_decisions", widget)
        assert saved["persisted"] is True
        assert applied["persisted"] is True
    finally:
        process.stdin.close()
        result = process.wait(timeout=10)
        errors = process.stderr.read()
    assert result == 0, errors
    assert _read(output / "final_artifacts.json")["ready_to_file"] is False
    assert (output / "applied_decisions.json").is_file()
