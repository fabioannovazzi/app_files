"""A source-faithful, test-only composition of the fictional workshop brief."""

from __future__ import annotations

import hashlib
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = ROOT / "plugins/clara/skills/html-deck/scripts"


def command(name, *args):
    result = subprocess.run(
        [sys.executable, str(SCRIPTS / name), *map(str, args)],
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    return result


def write(path, payload):
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )


WORDS = {
    "it": [
        "Proposta per ricevere le richieste",
        "Officina Arco · Discussione interna",
        "Una scheda comune da provare con il personale",
        "Proposta fittizia, ancora da discutere",
        "La richiesta deve essere comprensibile",
        "Oggi",
        "Informazioni sparse",
        "Contatto",
        "A volte manca un recapito.",
        "Problema",
        "La descrizione può richiedere un chiarimento.",
        "Proposta",
        "Una scheda comune",
        "Raccogliere recapito e modo per ricontattare il cliente.",
        "Descrivere ciò che il cliente segnala, senza diagnosi inventate.",
        "Chiarire la richiesta prima di procedere",
        ["Ricevere", "Chiarire", "Valutare", "Confermare"],
        [
            "Richiesta del cliente",
            "Informazioni mancanti",
            "Valutazione di Paolo",
            "Preventivo al cliente",
        ],
        [
            "Registrare bicicletta, problema e recapito.",
            "Chiedere cosa manca prima della valutazione.",
            "Valutare il lavoro e preparare il preventivo.",
            "Attendere conferma prima del lavoro e delle aggiunte.",
        ],
        "Concordare chi segue la richiesta",
        "Sara raccoglierebbe e chiarirebbe le richieste. Paolo valuterebbe il lavoro e preparerebbe il preventivo.",
        "Ruoli proposti, da concordare prima della prova.",
        "Decidere se provare la scheda",
        ["Concordare", "Riesaminare"],
        [
            "Definire ruoli e condizioni prima della prova.",
            "Raccogliere i riscontri e correggere la scheda dopo la prova.",
        ],
        "La riunione deve concordare chi raccoglierà i riscontri.",
        "Chiarire una richiesta incompleta",
        "«La bici fa rumore»: chiedere recapito, quando si sente il rumore e quale parte sembra coinvolta.",
        "Chiedere informazioni senza diagnosticare il guasto.",
        "Raccogliere i dubbi prima di una prova",
        ["Ascoltare", "Chiarire"],
        [
            "Raccogliere prima le domande del personale sulla scheda.",
            "Chiarire i dubbi prima di decidere se provare il percorso.",
        ],
        "La prova non è ancora decisa.",
    ],
    "en": [
        "A proposal for receiving requests",
        "Officina Arco · Internal discussion",
        "A shared form to trial with the team",
        "Fictional proposal for discussion",
        "Make the request understandable",
        "Today",
        "Scattered information",
        "Contact",
        "A contact detail is sometimes missing.",
        "Problem",
        "The description may need clarification.",
        "Proposal",
        "A shared form",
        "Record contact details and an agreed way to reply.",
        "Describe what the customer reports; do not invent a diagnosis.",
        "Clarify the request before proceeding",
        ["Receive", "Clarify", "Assess", "Confirm"],
        [
            "Customer request",
            "Missing information",
            "Paolo's assessment",
            "Quote to the customer",
        ],
        [
            "Record bicycle, problem and contact details.",
            "Ask for missing information before assessment.",
            "Assess the work and prepare the quote.",
            "Await confirmation before work and any additions.",
        ],
        "Agree who follows the request",
        "Sara would gather and clarify requests. Paolo would assess the work and prepare the quote.",
        "Proposed roles to agree before the trial.",
        "Decide whether to trial the form",
        ["Agree", "Review"],
        [
            "Set roles and conditions before the trial.",
            "Collect feedback and revise the form after the trial.",
        ],
        "The meeting must agree who will collect feedback.",
        "Clarify an incomplete request",
        "“The bike makes a noise”: ask for contact details, when it occurs and which part seems involved.",
        "Gather information without diagnosing the fault.",
        "Collect questions before a trial",
        ["Listen", "Clarify"],
        [
            "First gather staff questions about the form.",
            "Resolve questions before deciding whether to trial the process.",
        ],
        "A trial has not been decided.",
    ],
    "fr": [
        "Une proposition pour recevoir les demandes",
        "Officina Arco · Discussion interne",
        "Une fiche commune à tester avec le personnel",
        "Proposition fictive à discuter",
        "Rendre la demande compréhensible",
        "Aujourd’hui",
        "Des informations dispersées",
        "Contact",
        "Il manque parfois un moyen de joindre le client.",
        "Problème",
        "La description demande parfois une précision.",
        "Proposition",
        "Une fiche commune",
        "Noter les coordonnées et le moyen convenu pour répondre.",
        "Décrire ce que signale le client, sans inventer de diagnostic.",
        "Clarifier la demande avant d’agir",
        ["Recueillir", "Clarifier", "Évaluer", "Confirmer"],
        [
            "Demande du client",
            "Informations manquantes",
            "Évaluation de Paolo",
            "Devis au client",
        ],
        [
            "Noter vélo, problème et coordonnées.",
            "Demander les précisions avant l’évaluation.",
            "Évaluer le travail et préparer le devis.",
            "Attendre confirmation pour le travail et ses ajouts.",
        ],
        "Convenir du suivi de la demande",
        "Sara recueillerait et clarifierait les demandes. Paolo évaluerait le travail et préparerait le devis.",
        "Rôles proposés à convenir avant le test.",
        "Décider s’il faut tester la fiche",
        ["Convenir", "Réexaminer"],
        [
            "Définir les rôles et conditions avant le test.",
            "Recueillir les retours et revoir la fiche après le test.",
        ],
        "La réunion doit désigner qui recueillera les retours.",
        "Clarifier une demande incomplète",
        "« Le vélo fait du bruit » : demander les coordonnées, quand le bruit apparaît et quelle partie semble concernée.",
        "Recueillir des informations sans diagnostiquer la panne.",
        "Recueillir les questions avant un test",
        ["Écouter", "Clarifier"],
        [
            "Recueillir d’abord les questions du personnel sur la fiche.",
            "Clarifier les questions avant de décider d’un test.",
        ],
        "Le test n’est pas encore décidé.",
    ],
    "de": [
        "Vorschlag zur Annahme von Anfragen",
        "Officina Arco · Interne Besprechung",
        "Ein gemeinsames Formular mit dem Team erproben",
        "Fiktiver Vorschlag zur Diskussion",
        "Die Anfrage verständlich machen",
        "Heute",
        "Verteilte Informationen",
        "Kontakt",
        "Manchmal fehlen Kontaktdaten.",
        "Problem",
        "Die Beschreibung muss gelegentlich geklärt werden.",
        "Vorschlag",
        "Ein gemeinsames Formular",
        "Kontaktdaten und vereinbarten Rückmeldeweg festhalten.",
        "Die Kundenbeschreibung aufnehmen, keine Diagnose erfinden.",
        "Die Anfrage vor Arbeitsbeginn klären",
        ["Aufnehmen", "Klären", "Beurteilen", "Bestätigen"],
        [
            "Kundenanfrage",
            "Fehlende Angaben",
            "Paolos Beurteilung",
            "Kostenvoranschlag",
        ],
        [
            "Fahrrad, Problem und Kontaktdaten aufnehmen.",
            "Fehlende Angaben vor der Beurteilung erfragen.",
            "Arbeit beurteilen und Kostenvoranschlag erstellen.",
            "Bestätigung vor Arbeiten und Ergänzungen abwarten.",
        ],
        "Die Zuständigkeiten vereinbaren",
        "Sara soll Anfragen aufnehmen und klären. Paolo soll die Arbeit beurteilen und den Kostenvoranschlag erstellen.",
        "Vorgeschlagene Rollen vor dem Versuch vereinbaren.",
        "Über einen Formularversuch entscheiden",
        ["Vereinbaren", "Prüfen"],
        [
            "Rollen und Bedingungen vor dem Versuch festlegen.",
            "Rückmeldungen sammeln und das Formular danach überarbeiten.",
        ],
        "In der Besprechung festlegen, wer Rückmeldungen sammelt.",
        "Eine unvollständige Anfrage klären",
        "„Das Fahrrad macht Geräusche“: Kontaktdaten, Zeitpunkt und möglicherweise betroffenen Fahrradteil erfragen.",
        "Informationen sammeln, ohne eine Diagnose zu stellen.",
        "Vor einem Versuch Fragen sammeln",
        ["Zuhören", "Klären"],
        [
            "Zunächst Fragen des Teams zum Formular sammeln.",
            "Fragen klären, bevor über einen Versuch entschieden wird.",
        ],
        "Ein Versuch ist noch nicht beschlossen.",
    ],
    "es": [
        "Propuesta para recibir solicitudes",
        "Officina Arco · Debate interno",
        "Una ficha común para probar con el equipo",
        "Propuesta ficticia para debatir",
        "Hacer comprensible la solicitud",
        "Hoy",
        "Información dispersa",
        "Contacto",
        "A veces falta un contacto.",
        "Problema",
        "La descripción puede necesitar aclaraciones.",
        "Propuesta",
        "Una ficha común",
        "Recoger contacto y medio acordado para responder.",
        "Describir lo que señala el cliente, sin inventar diagnósticos.",
        "Aclarar la solicitud antes de actuar",
        ["Recibir", "Aclarar", "Evaluar", "Confirmar"],
        [
            "Solicitud del cliente",
            "Información pendiente",
            "Evaluación de Paolo",
            "Presupuesto al cliente",
        ],
        [
            "Registrar bicicleta, problema y contacto.",
            "Pedir información pendiente antes de evaluar.",
            "Evaluar el trabajo y preparar el presupuesto.",
            "Esperar confirmación antes del trabajo y sus ampliaciones.",
        ],
        "Acordar quién sigue la solicitud",
        "Sara recogería y aclararía solicitudes. Paolo evaluaría el trabajo y prepararía el presupuesto.",
        "Funciones propuestas que acordar antes de la prueba.",
        "Decidir si probar la ficha",
        ["Acordar", "Revisar"],
        [
            "Definir funciones y condiciones antes de la prueba.",
            "Recoger comentarios y revisar la ficha tras la prueba.",
        ],
        "La reunión debe acordar quién recogerá los comentarios.",
        "Aclarar una solicitud incompleta",
        "«La bicicleta hace ruido»: pedir contacto, cuándo ocurre y qué parte parece afectada.",
        "Recoger información sin diagnosticar la avería.",
        "Recoger dudas antes de una prueba",
        ["Escuchar", "Aclarar"],
        [
            "Recoger primero las preguntas del personal sobre la ficha.",
            "Aclarar dudas antes de decidir si probar el proceso.",
        ],
        "La prueba aún no está decidida.",
    ],
}


def author_deck(source: Path, work: Path, language: str, exercise: Path | None = None):
    """Compose a standalone talk; no advisory case, numeric facts or external calls."""
    w = WORDS[language]
    command(
        "init_html_deck.py",
        "--work-dir",
        work,
        "--title",
        w[0],
        "--subtitle",
        w[2],
        "--author",
        "Officina Arco",
        "--eyebrow",
        w[1],
        "--language",
        language,
    )
    local = work / source.name
    local.write_bytes(source.read_bytes())
    sources = [
        dict(
            id="brief",
            label=w[3],
            kind="document",
            locator=source.name,
            sha256=hashlib.sha256(local.read_bytes()).hexdigest(),
            publish_locator=False,
        )
    ]
    if exercise:
        (work / exercise.name).write_bytes(exercise.read_bytes())
        sources.append(
            dict(
                id="exercise",
                label=w[26],
                kind="document",
                locator=exercise.name,
                sha256=hashlib.sha256(exercise.read_bytes()).hexdigest(),
                publish_locator=False,
            )
        )
    slides = []
    chapters = {
        "it": [
            "Proposta",
            "Richiesta",
            "Passaggi",
            "Responsabilità",
            "Esempio",
            "Decisione",
        ],
        "en": [
            "Proposal",
            "Request",
            "Process",
            "Responsibilities",
            "Example",
            "Decision",
        ],
        "fr": [
            "Proposition",
            "Demande",
            "Étapes",
            "Responsabilités",
            "Exemple",
            "Décision",
        ],
        "de": [
            "Vorschlag",
            "Anfrage",
            "Ablauf",
            "Zuständigkeiten",
            "Beispiel",
            "Entscheidung",
        ],
        "es": [
            "Propuesta",
            "Solicitud",
            "Pasos",
            "Responsabilidades",
            "Ejemplo",
            "Decisión",
        ],
    }[language]
    chapter_names = dict(
        zip(
            (
                "opening",
                "request",
                "process",
                "responsibilities",
                "example",
                "decision",
            ),
            chapters,
            strict=True,
        )
    )

    def add(sid, layout, title, slots, tone="light", refs=None):
        slides.append(
            dict(
                id=sid,
                layout_id=layout,
                title=title,
                chapter=sid,
                chapter_label=chapter_names[sid],
                tone=tone,
                notes=w[3] + ". " + title,
                source_refs=refs or ["brief"],
                claim_refs=["claim-" + sid],
                slots={"eyebrow": w[1], "title": title, "source_note": w[3], **slots},
            )
        )

    add(
        "opening",
        "editorial-cover",
        w[0],
        {"subtitle": w[2], "author": "Officina Arco"},
        "dark",
    )
    add(
        "request",
        "paired-comparison",
        w[4],
        {
            "left_label": w[5],
            "left_title": w[6],
            "left_items": [
                {"label": w[7], "body": w[8]},
                {"label": w[9], "body": w[10]},
            ],
            "right_label": w[11],
            "right_title": w[12],
            "right_items": [
                {"label": w[7], "body": w[13]},
                {"label": w[9], "body": w[14]},
            ],
        },
    )
    add(
        "process",
        "process-flow",
        w[15],
        {
            "steps": [
                {"label": label, "title": title, "body": body, "_fragment": index + 1}
                for index, (label, title, body) in enumerate(
                    zip("ABCD", w[17], w[18], strict=True)
                )
            ]
        },
    )
    add(
        "responsibilities",
        "assertion",
        w[19],
        {"body": w[20], "implication": w[21]},
        "dark",
    )
    if exercise:
        add(
            "example",
            "assertion",
            w[26],
            {"body": w[27], "implication": w[28]},
            refs=["brief", "exercise"],
        )
    add(
        "decision",
        "closing-decision",
        w[22],
        {
            "actions": [
                {"verb": verb, "body": body}
                for verb, body in zip(w[23], w[24], strict=True)
            ],
            "closing_line": w[25],
        },
    )
    plan = {
        "schema_version": "clara.html_deck_plan.v1",
        "allow_bespoke_html": False,
        "slides": slides,
    }
    ledger = {
        "schema_version": "clara.html_deck_ledger.v1",
        "sources": sources,
        "slides": [
            {
                "slide_id": s["id"],
                "basis_status": "source-backed",
                "basis_note": "",
                "claims": [
                    {
                        "id": s["claim_refs"][0],
                        "statement": s["title"],
                        "classification": "judgement",
                        "basis_status": "source-backed",
                        "basis_note": "",
                        "source_ids": s["source_refs"],
                        "qualification": w[3],
                    }
                ],
            }
            for s in slides
        ],
    }
    write(work / "deck-plan.json", plan)
    write(work / "content-ledger.json", ledger)
    command(
        "compose_html_deck.py", work / "deck-plan.json", "--output-dir", work, "--force"
    )
    return work


def build_deck(work: Path, output: Path):
    command(
        "build_html_deck.py",
        work,
        "--output-root",
        output,
        "--package",
        output.parent / (output.name + ".zip"),
        "--report",
        output.parent / (output.name + "-validation.json"),
    )
    return next(output.glob("*/index.html"))
