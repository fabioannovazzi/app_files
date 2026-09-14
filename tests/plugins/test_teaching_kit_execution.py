"""Execute the packaged teaching inputs through current, unmocked pipelines.

These tests establish input compatibility and actual artifact generation. They
do not simulate a learner, certify professional judgement or test native voice.
"""

from __future__ import annotations

import csv
import hashlib
import importlib.util
import json
import mimetypes
import subprocess
import sys
from decimal import Decimal
from pathlib import Path

import pytest

from tests.plugins._teaching_release import record_native_check

ROOT = Path(__file__).resolve().parents[2]


def _read(path):
    return json.loads(path.read_text(encoding="utf-8"))


def _write(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False), encoding="utf-8")


def _run(program, *args):
    result = subprocess.run(
        [sys.executable, str(ROOT / program), *map(str, args)],
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=60,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr


def _bound_case(
    tmp_path,
    monkeypatch,
    workflow,
    ledger_workflow,
    phase,
    product="vera",
    language="it",
):
    monkeypatch.syspath_prepend(str(ROOT / "plugins/_shared/vendor/modules"))
    from courseware.library import CourseLibrary

    kit = CourseLibrary(ROOT / "plugins" / product, {workflow}).render(
        workflow, language, tmp_path / "kit"
    )
    sources = kit["source_files" if phase == "demo" else "practice_files"]
    spec = importlib.util.spec_from_file_location(
        "kit_execution_ledger", ROOT / "plugins/studio-archive/scripts/client_ledger.py"
    )
    ledger = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(ledger)
    (tmp_path / ".vera-onboarding-local-only").write_text(
        "Mechanical teaching-kit verification; no user profile or telemetry.\n",
        encoding="utf-8",
    )
    case = tmp_path / "case"
    case.mkdir()
    client = "client_0123456789abcdef01234567"
    ledger.create_client_manifest(case, client)
    engagement = ledger.create_engagement(case, client, "Fictional kit verification")[
        "engagement_id"
    ]
    imported = [
        ledger.import_document(
            case,
            client,
            engagement,
            Path(source),
            (
                "journal"
                if ledger_workflow == "journal-sampling"
                and Path(source).suffix.lower() in {".csv", ".xlsx", ".xls"}
                else "source"
            ),
        )
        for source in sources
    ]
    if ledger_workflow == "treasury-forecast":
        tables = {
            Path(source).stem: {
                "path": "imports/"
                + item["receipt"]["input_id"]
                + "/"
                + Path(item["receipt"]["path"]).name
            }
            for source, item in zip(sources, imported, strict=True)
            if Path(source).suffix == ".csv"
        }
        manifest_path = case / "manifest.json"
        _write(
            manifest_path,
            {
                "schema_version": "vera.treasury_manifest.v1",
                "company_id": "officina-arco-fictional",
                "company_name": "Officina Arco — caso fittizio",
                "currency": "EUR",
                "as_of": "2026-03-31",
                "horizon_end": "2026-05-31",
                "coverage": "One bank account and the supplied outstanding and planned flows only; no unbilled future sales or tax calculation.",
                "tables": tables,
                "invoice_files": [],
                "previous": None,
            },
        )
        imported.append(
            ledger.import_document(case, client, engagement, manifest_path, "source")
        )
    version = _read(ROOT / "plugins" / product / ".codex-plugin/plugin.json")["version"]
    run = ledger.prepare_run(
        case,
        client,
        engagement,
        ledger_workflow,
        version,
        input_ids=[item["receipt"]["input_id"] for item in imported],
        purpose="Local fictional kit verification; no professional approval",
    )
    return ledger.start_run(case, engagement, run["run"]["run_id"])


def _complete_teaching_case(run, client_root):
    """Seal actual local test artifacts so a later run can import the result."""
    from tests.model_data_helpers import write_no_model_report

    spec = importlib.util.spec_from_file_location(
        "teaching_completion_ledger",
        ROOT / "plugins/studio-archive/scripts/client_ledger.py",
    )
    ledger = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(ledger)
    output = Path(run["output_dir"])
    context = run["context"]
    declarations = [
        {
            "artifact_id": f"internal.teaching.{index}",
            "path": path.relative_to(output).as_posix(),
            "purpose": "Preserve actual fictional teaching verification output",
            "audience": "review",
            "media_type": mimetypes.guess_type(path.name)[0]
            or "application/octet-stream",
        }
        for index, path in enumerate(
            sorted(p for p in output.rglob("*") if p.is_file())
        )
    ]
    declarations.extend(
        write_no_model_report(output, context["workflow_id"], context["run_id"])
    )
    ledger.finalize_run(
        client_root, context["engagement_id"], context["run_id"], declarations
    )
    completed = ledger.complete_run(
        client_root, context["engagement_id"], context["run_id"]
    )
    assert completed["run"]["status"] == "completed"
    return ledger


@pytest.mark.parametrize("language", ["it", "en", "fr", "de", "es"])
def test_assetti_kit_runs_assessment_and_same_case_follow_up(
    tmp_path, monkeypatch, language
):
    run = _bound_case(
        tmp_path,
        monkeypatch,
        "adeguati-assetti",
        "adeguati-assetti",
        "demo",
        language=language,
    )
    client_root = tmp_path / "case"
    words = {
        "it": [
            "Responsabilità, chiusura mensile e uso delle informazioni per gli incassi; altri processi non valutati.",
            "Officina Arco: una sede e dodici addetti, con contabilità esterna e responsabilità interne descritte.",
            "Valutare il processo esistente e una sostituzione praticabile, senza imporre una struttura più complessa del necessario.",
            "La procedura definisce invio, consegna e riesame; non nomina un sostituto di Sara.",
            "Nel ciclo di febbraio sono documentati invio, consegna e decisione; la promessa del cliente non prova il pagamento.",
            "Nel ciclo di marzo invio e consegna sono tardivi dopo l’assenza di Sara; il riesame non è ancora annotato.",
            "Il primo ciclo dimostra uso delle informazioni in quel periodo; la continuità e la sostituzione rimangono da verificare.",
            "La nuova evidenza mostra un ritardo effettivo nel ciclo esaminato. Il precedente ciclo riuscito resta valido, ma non risolve la debolezza emersa durante l’assenza.",
            "Concordare la sostituzione per invio documenti e accesso allo scadenziario e verificarla nel prossimo ciclo.",
            "Proposta per Elena, da concordare con Sara e lo studio; nessun incarico assegnato automaticamente.",
            "Da concordare prima della prossima assenza e verificare al successivo riepilogo.",
            "Conferma delle responsabilità, accesso e prova datata di invio, consegna e riesame.",
            "Chi può sostituire Sara e con quali accessi durante un’assenza?",
            "Gli altri processi e la continuità fuori dai cicli forniti non sono valutati. Nessuna certificazione o decisione professionale è registrata.",
        ],
        "en": [
            "Responsibilities, monthly closing and collection information; other processes are not assessed.",
            "Officina Arco: one site and twelve staff, with external accounting and stated internal responsibilities.",
            "Assess the existing process and a workable substitute without imposing unnecessary complexity.",
            "The procedure defines dispatch, delivery and review but names no substitute for Sara.",
            "The February cycle records dispatch, delivery and a decision; a customer promise does not prove payment.",
            "March-cycle dispatch and delivery are late after Sara’s absence; the review is not yet recorded.",
            "The first cycle demonstrates use of information in that period; continuity and substitution still need evidence.",
            "New evidence shows an actual delay in the reviewed cycle. The earlier successful cycle remains valid but does not resolve the weakness during absence.",
            "Agree cover for document dispatch and access to due dates, then check it in the next cycle.",
            "Proposed for Elena, to agree with Sara and the practice; no task is assigned automatically.",
            "To agree before the next absence and check at the next monthly summary.",
            "Confirmed responsibilities, access and dated dispatch, delivery and review evidence.",
            "Who can cover Sara’s tasks, and with which access, during an absence?",
            "Other processes and continuity outside supplied cycles are not assessed. No certification or professional decision is recorded.",
        ],
        "fr": [
            "Responsabilités, clôture mensuelle et informations de recouvrement ; autres processus non évalués.",
            "Officina Arco : un site, douze collaborateurs, comptabilité externe et responsabilités internes décrites.",
            "Évaluer le processus existant et un remplacement praticable sans complexité inutile.",
            "La procédure définit envoi, livraison et revue sans nommer de remplaçant de Sara.",
            "Le cycle de février documente envoi, livraison et décision ; une promesse ne prouve pas le paiement.",
            "Dans le cycle de mars, envoi et livraison sont tardifs après l’absence de Sara ; la revue n’est pas encore notée.",
            "Le premier cycle démontre l’utilisation des informations sur cette période ; continuité et remplacement restent à vérifier.",
            "Les nouvelles preuves montrent un retard réel sur le cycle examiné. Le succès précédent reste valable sans résoudre la faiblesse pendant l’absence.",
            "Convenir du remplacement pour l’envoi et l’accès à l’échéancier puis le vérifier au prochain cycle.",
            "Proposition pour Elena, à convenir avec Sara et le cabinet ; aucune tâche attribuée automatiquement.",
            "À convenir avant la prochaine absence et vérifier à la prochaine synthèse.",
            "Responsabilités confirmées, accès et preuves datées d’envoi, livraison et revue.",
            "Qui peut remplacer Sara et avec quels accès pendant son absence ?",
            "Autres processus et continuité hors cycles fournis non évalués. Aucune certification ni décision professionnelle enregistrée.",
        ],
        "de": [
            "Zuständigkeiten, Monatsabschluss und Forderungsinformationen; andere Prozesse nicht beurteilt.",
            "Officina Arco: ein Standort, zwölf Beschäftigte, externe Buchhaltung und beschriebene interne Zuständigkeiten.",
            "Vorhandenen Prozess und praktikable Vertretung ohne unnötige Komplexität beurteilen.",
            "Das Verfahren regelt Versand, Lieferung und Prüfung, nennt aber keine Vertretung für Sara.",
            "Der Februarzyklus dokumentiert Versand, Lieferung und Entscheidung; die Kundenzusage belegt keine Zahlung.",
            "Im Märzzyklus erfolgen Versand und Lieferung nach Saras Abwesenheit verspätet; die Prüfung ist noch nicht dokumentiert.",
            "Der erste Zyklus belegt Informationsnutzung in diesem Zeitraum; Kontinuität und Vertretung bleiben zu prüfen.",
            "Neue Nachweise zeigen eine tatsächliche Verzögerung im geprüften Zyklus. Der frühere Erfolg bleibt gültig, löst aber die Schwäche während der Abwesenheit nicht.",
            "Vertretung für Unterlagenversand und Fälligkeitszugriff vereinbaren und im nächsten Zyklus prüfen.",
            "Vorschlag für Elena, mit Sara und der Kanzlei abzustimmen; keine automatische Aufgabenzuweisung.",
            "Vor der nächsten Abwesenheit vereinbaren und bei der nächsten Monatsübersicht prüfen.",
            "Bestätigte Zuständigkeiten, Zugriff und datierte Versand-, Liefer- und Prüfnachweise.",
            "Wer kann Sara während einer Abwesenheit mit welchen Zugriffsrechten vertreten?",
            "Andere Prozesse und Kontinuität außerhalb gelieferter Zyklen nicht beurteilt. Keine Zertifizierung oder fachliche Entscheidung erfasst.",
        ],
        "es": [
            "Responsabilidades, cierre mensual e información de cobros; otros procesos no evaluados.",
            "Officina Arco: una sede, doce personas, contabilidad externa y responsabilidades internas descritas.",
            "Evaluar proceso existente y sustitución viable sin complejidad innecesaria.",
            "El procedimiento define envío, entrega y revisión sin nombrar sustituto de Sara.",
            "El ciclo de febrero documenta envío, entrega y decisión; una promesa no prueba el pago.",
            "En el ciclo de marzo, envío y entrega se retrasan tras la ausencia de Sara; la revisión aún no consta.",
            "El primer ciclo demuestra uso de información en ese período; continuidad y sustitución requieren pruebas.",
            "Las nuevas pruebas muestran un retraso real en el ciclo revisado. El éxito anterior sigue válido, pero no resuelve la debilidad durante la ausencia.",
            "Acordar sustitución para enviar documentos y acceder a vencimientos y comprobarla en el próximo ciclo.",
            "Propuesta para Elena, a acordar con Sara y el despacho; no se asignan tareas automáticamente.",
            "Acordar antes de la próxima ausencia y verificar con el siguiente resumen.",
            "Responsabilidades confirmadas, acceso y pruebas fechadas de envío, entrega y revisión.",
            "¿Quién puede sustituir a Sara y con qué accesos durante una ausencia?",
            "Otros procesos y continuidad fuera de los ciclos aportados no evaluados. No se registra certificación ni decisión profesional.",
        ],
    }[language]
    previous = None
    for phase in ("demo", "practice"):
        output = Path(run["output_dir"])
        input_root = Path(run["context"]["run_root"]) / "inputs"
        paths = [Path(item["path"]) for item in run["context"]["input_bindings"]]
        sources = [
            {
                "id": f"S{index}",
                "path": path.relative_to(input_root).as_posix(),
                "title": path.name,
                "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
            }
            for index, path in enumerate(paths)
        ]
        by_name = {
            path.name: source["id"] for path, source in zip(paths, sources, strict=True)
        }
        policy_citation = {
            "source_id": by_name[f"procedure-{language}.md"],
            "locator": "Paragraph 1",
        }
        operation_citation = {
            "source_id": by_name[
                f"{'update' if previous else 'operation'}-{language}.md"
            ],
            "locator": "Paragraph 1",
        }
        finding_citations = [policy_citation, operation_citation]
        operation = words[5 if previous else 4]
        assessment = words[7 if previous else 6]
        review = {
            "schema_version": 1,
            "jurisdiction": "IT",
            "as_of": "2026-04-30" if previous else "2026-03-31",
            "scope": words[0],
            "company_context": words[1],
            "proportionality_basis": words[2],
            "sources": sources,
            "legal_basis": [
                {
                    "title": "CNDCEC — Assetti organizzativi, amministrativi e contabili: check-list operative",
                    "url": "https://commercialisti.it/documenti-studio/assetti-organizzativi-amministrativi-e-contabili-check-list-operative/",
                    "locator": "Publication dated 25 July 2023",
                    "checked_at": "2026-09-14",
                    "applicability": "Official professional-source entry checked; mechanical fictional fixture, no article-level legal opinion.",
                }
            ],
            "observations": [
                {
                    "id": "O1",
                    "area": "Monthly procedure",
                    "description": words[3],
                    "proportionality": words[2],
                    "assessment": words[3],
                    "evidence_state": "documented",
                    "citations": [policy_citation],
                },
                {
                    "id": "O2",
                    "area": "Observed cycle",
                    "description": operation,
                    "proportionality": words[2],
                    "assessment": assessment,
                    "evidence_state": "operating_evidence",
                    "citations": [operation_citation],
                },
            ],
            "findings": [
                {
                    "id": "F1",
                    "observation_ids": ["O1", "O2"],
                    "observation": words[3],
                    "interpretation": assessment,
                    "alternatives": words[6],
                    "follow_up": words[12],
                    "citations": finding_citations,
                }
            ],
            "actions": [
                {
                    "id": "A1",
                    "finding_ids": ["F1"],
                    "proposal": words[8],
                    "owner": words[9],
                    "timing": words[10],
                    "priority_reason": assessment,
                    "completion_evidence_needed": words[11],
                    "status": "proposed",
                }
            ],
            "assessment": assessment,
            "assessment_citations": finding_citations,
            "limitations": words[13],
            "intelligent_review": {
                "version": 1,
                "coverage": [
                    {
                        "id": "C1",
                        "area": "Responsibilities and monthly information",
                        "status": "assessed",
                        "reason": words[0],
                        "observation_ids": ["O1", "O2"],
                    },
                    {
                        "id": "C2",
                        "area": "Other processes and prospective cash",
                        "status": "unresolved",
                        "reason": words[13],
                        "observation_ids": [],
                    },
                ],
                "processes": [
                    {
                        "id": "P1",
                        "process": words[0],
                        "risk": assessment,
                        "responsibility": words[1],
                        "control": words[3],
                        "information_flow": operation,
                        "operation": operation,
                        "gap": words[12],
                        "observation_ids": ["O1", "O2"],
                    }
                ],
                "questions": [
                    {
                        "id": "Q1",
                        "question": words[12],
                        "why_it_matters": assessment,
                        "evidence_needed": words[11],
                        "status": words[10],
                        "observation_ids": ["O1", "O2"],
                    }
                ],
                "chronology": [
                    {
                        "id": "T1",
                        "event_date": "2026-04-28" if previous else "2026-03-24",
                        "known_at": (
                            "Report receipt dated 2026-04-28; individual delivery time not recorded"
                            if previous
                            else "2026-03-24"
                        ),
                        "recipient": (
                            "Company; individual recipient not recorded"
                            if previous
                            else "Elena Bianchi"
                        ),
                        "event": operation,
                        "response": assessment,
                        "uncertainty": words[13],
                        "observation_ids": ["O2"],
                    }
                ],
                "decision_brief": assessment + " " + words[8],
                "action_ids": ["A1"],
                "next_review": words[10] + " " + words[11],
            },
        }
        if previous:
            review["previous"] = {
                "source_id": by_name[previous[0].name],
                "record_sha256": previous[2],
            }
            review["changes_since_previous"] = words[7]
            review["prior_action_review"] = {
                "A1": {
                    "status": "open",
                    "assessment": words[7],
                    "citations": [operation_citation],
                    "current_action_ids": ["A1"],
                }
            }
        request = output / "review_input.json"
        _write(request, review)
        _run(
            "plugins/adeguati-assetti/scripts/assetti_review.py",
            "--client-engagement",
            run["context_path"],
            "--review",
            request,
        )
        path = next(output.glob("adeguati-assetti-*.json"))
        record = _read(path)
        assert record["status"] == "draft_for_review"
        assert next(output.glob("adeguati-assetti-*.md")).stat().st_size > 2000
        ledger = _complete_teaching_case(run, client_root)
        if previous:
            assert record["previous_record_sha256"] == previous[2]
            assert previous[0].read_bytes() == previous[1]
            assert record["review"]["prior_action_review"]["A1"]["status"] == "open"
        else:
            previous = (path, path.read_bytes(), record["record_sha256"])
            client, engagement = (
                run["context"]["client_id"],
                run["context"]["engagement_id"],
            )
            practice = list((tmp_path / "kit/files/practice").glob("*.md"))
            imports = [
                ledger.import_document(client_root, client, engagement, item, "source")
                for item in [*practice, path]
            ]
            prepared = ledger.prepare_run(
                client_root,
                client,
                engagement,
                "adeguati-assetti",
                run["context"]["workflow_version"],
                input_ids=[item["receipt"]["input_id"] for item in imports],
            )
            run = ledger.start_run(client_root, engagement, prepared["run"]["run_id"])


@pytest.mark.parametrize("language", ["it", "en", "fr", "de", "es"])
def test_aml_kit_saves_initial_and_linked_current_review(
    tmp_path, monkeypatch, language
):
    """Create both real records; fixture prose never becomes learner approval."""
    run = _bound_case(
        tmp_path, monkeypatch, "aml-review", "aml-review", "demo", language=language
    )
    client_root = tmp_path / "case"
    texts = {
        "it": [
            "Revisione del dossier fittizio di Officina Arco e del finanziamento soci.",
            "Le quote e i poteri sono dichiarati; mancano riscontri indipendenti.",
            "Il dossier non consente ancora una conclusione sull’identificazione e il controllo.",
            "Le informazioni potrebbero essere corrette; l’assenza di documenti non prova irregolarità.",
            "Verificare identità, poteri e catena di controllo con evidenze pertinenti.",
            "Contratto e pagamento del finanziamento coincidono per parti e importo. Le persone e il controllo richiedono verifica; nessun giudizio di sospetto o accettazione è espresso.",
            "La nuova dichiarazione include Marta Riva e cambia la quota di Paolo. Il finanziamento rimane documentato dalle stesse fonti; servono riscontri sulla cessione e sulla nuova socia.",
        ],
        "en": [
            "Review of Officina Arco’s fictional file and shareholder loan.",
            "Ownership and authority are declared; independent corroboration is missing.",
            "The file does not yet support a conclusion on identification and control.",
            "The statements may be correct; missing documents do not prove wrongdoing.",
            "Verify identity, authority and control links with relevant evidence.",
            "Loan agreement and payment agree on parties and amount. People and control need verification; no suspicion or acceptance decision is expressed.",
            "The new declaration adds Marta Riva and changes Paolo’s share. The loan remains supported by the same sources; transfer and new-owner evidence is needed.",
        ],
        "fr": [
            "Revue du dossier fictif d’Officina Arco et du prêt d’associé.",
            "Participations et pouvoirs sont déclarés ; les corroborations indépendantes manquent.",
            "Le dossier ne permet pas encore de conclure sur l’identification et le contrôle.",
            "Les déclarations peuvent être exactes ; les pièces manquantes ne prouvent pas une irrégularité.",
            "Vérifier identité, pouvoirs et liens de contrôle avec les preuves pertinentes.",
            "Contrat et paiement concordent sur parties et montant. Personnes et contrôle restent à vérifier ; aucune décision de soupçon ou d’acceptation n’est exprimée.",
            "La nouvelle déclaration ajoute Marta Riva et modifie la participation de Paolo. Le prêt reste étayé par les mêmes sources ; il faut vérifier cession et nouvelle associée.",
        ],
        "de": [
            "Prüfung der fiktiven Akte von Officina Arco und des Gesellschafterdarlehens.",
            "Beteiligungen und Befugnisse sind angegeben; unabhängige Bestätigungen fehlen.",
            "Die Akte erlaubt noch keine Schlussfolgerung zu Identifikation und Kontrolle.",
            "Die Angaben können richtig sein; fehlende Unterlagen beweisen keinen Verstoß.",
            "Identität, Befugnisse und Kontrollverbindungen anhand geeigneter Nachweise prüfen.",
            "Darlehensvertrag und Zahlung stimmen bei Parteien und Betrag überein. Personen und Kontrolle sind zu prüfen; keine Verdachts- oder Annahmeentscheidung wird getroffen.",
            "Die neue Erklärung ergänzt Marta Riva und ändert Paolos Anteil. Das Darlehen bleibt durch dieselben Quellen belegt; Übertragung und neue Gesellschafterin benötigen Nachweise.",
        ],
        "es": [
            "Revisión del expediente ficticio de Officina Arco y del préstamo de socio.",
            "Participaciones y poderes están declarados; faltan corroboraciones independientes.",
            "El expediente aún no permite concluir sobre identificación y control.",
            "Las declaraciones podrían ser correctas; la ausencia de documentos no prueba irregularidad.",
            "Verificar identidad, poderes y vínculos de control con pruebas pertinentes.",
            "Contrato y pago coinciden en partes e importe. Personas y control requieren verificación; no se expresa decisión de sospecha ni aceptación.",
            "La nueva declaración añade a Marta Riva y cambia la cuota de Paolo. El préstamo sigue respaldado por las mismas fuentes; se requieren pruebas sobre transmisión y nueva socia.",
        ],
    }[language]
    previous = None
    for phase in ("demo", "practice"):
        output = Path(run["output_dir"])
        input_root = Path(run["context"]["run_root"]) / "inputs"
        paths = [Path(item["path"]) for item in run["context"]["input_bindings"]]
        sources = [
            {
                "id": f"S{index}",
                "path": path.relative_to(input_root).as_posix(),
                "title": path.name,
                "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
            }
            for index, path in enumerate(paths)
        ]
        by_name = {
            path.name: source["id"] for path, source in zip(paths, sources, strict=True)
        }
        ownership = by_name[
            f"ownership{'-update' if phase == 'practice' else ''}-{language}.md"
        ]
        loan = by_name[f"loan-{language}.md"]
        review = {
            "schema_version": 1,
            "jurisdiction": "IT",
            "as_of": "2026-08-31" if phase == "demo" else "2026-09-10",
            "scope": texts[0],
            "sources": sources,
            "legal_basis": [
                {
                    "title": "CNDCEC — Antiriciclaggio",
                    "url": "https://commercialisti.it/norme-per-la-professione/norme-tecniche/antiriciclaggio/",
                    "locator": "Regole tecniche and Strumenti operativi",
                    "checked_at": "2026-09-14",
                    "applicability": "Official professional-source inventory checked for this Italian practice fixture; no article-level legal conclusion.",
                }
            ],
            "findings": [
                {
                    "id": "F1",
                    "observation": texts[1],
                    "interpretation": texts[2],
                    "alternatives": texts[3],
                    "follow_up": texts[4],
                    "citations": [{"source_id": ownership, "locator": "Paragraph 1"}],
                }
            ],
            "assessment": texts[5],
            "assessment_citations": [
                {"source_id": loan, "locator": "Paragraph 1"},
                {"source_id": ownership, "locator": "Paragraph 1"},
            ],
            "limitations": "Test-only authored interpretation; no live model, screening, legal-currentness certification or professional decision. Current sources must be checked during the actual lesson.",
        }
        if previous:
            review["previous"] = {
                "source_id": by_name[previous[0].name],
                "record_sha256": previous[2],
            }
            review["changes_since_previous"] = texts[6]
        request = output / "review_input.json"
        _write(request, review)
        _run(
            "plugins/aml-review/scripts/aml_review.py",
            "--client-engagement",
            run["context_path"],
            "--review",
            request,
        )
        record_path = next(output.glob("aml-review-*.json"))
        record = _read(record_path)
        assert record["status"] == "draft_for_review"
        assert record["calculation"] is None
        assert next(output.glob("aml-review-*.md")).stat().st_size > 1000
        ledger = _complete_teaching_case(run, client_root)
        if previous:
            assert record["previous_record_sha256"] == previous[2]
            assert previous[0].read_bytes() == previous[1]
            assert "Marta Riva" in next(output.glob("aml-review-*.md")).read_text()
        else:
            previous = (record_path, record_path.read_bytes(), record["record_sha256"])
            client = run["context"]["client_id"]
            engagement = run["context"]["engagement_id"]
            practice = list((tmp_path / "kit/files/practice").glob("*.md"))
            imports = [
                ledger.import_document(client_root, client, engagement, path, "source")
                for path in [*practice, record_path]
            ]
            prepared = ledger.prepare_run(
                client_root,
                client,
                engagement,
                "aml-review",
                run["context"]["workflow_version"],
                input_ids=[item["receipt"]["input_id"] for item in imports],
            )
            run = ledger.start_run(client_root, engagement, prepared["run"]["run_id"])


@pytest.mark.parametrize("language", ["it", "en", "fr", "de", "es"])
@pytest.mark.parametrize(
    "phase,end,profit,cash_movement",
    [
        ("demo", "2026-02-28", "53000", "7000"),
        ("practice", "2026-03-31", "85000", "15000"),
    ],
)
def test_financial_report_kit_builds_current_source_bound_document(
    tmp_path, monkeypatch, language, phase, end, profit, cash_movement
):
    """Review this known fixture in the test, then build the normal report."""
    monkeypatch.syspath_prepend(str(ROOT / "tests/plugins"))
    from test_report_builder_plugin import _numeric_review_args, load_core

    run = _bound_case(
        tmp_path,
        monkeypatch,
        "financial-report-builder",
        "report-builder",
        phase,
        language=language,
    )
    source = next(
        Path(item["path"])
        for item in run["context"]["input_bindings"]
        if Path(item["path"]).suffix == ".xlsx"
    )
    original = source.read_bytes()
    work = Path(run["output_dir"])
    output = work / "report"
    core = load_core()
    inspection = core.inspect_inputs(
        source,
        work / "inspection",
        language=language,
        document_language=language,
        report_type="management_report",
    )
    recipe = inspection.suggested_recipe
    recipe["entity"] = "Officina Arco"
    recipe["period"] = f"2026-01-01 to {end}"
    # These are explicit interpretations of the authored fixture, not a
    # generic classifier, a saved learner decision or a shipped approval.
    assignments = {
        "Income Statement": ("income_statement", 5),
        "Balance Sheet": ("balance_sheet", 9),
        "Cash Flow": ("cash_flow", 5),
    }
    for section in recipe["sections"].values():
        section["assigned_table"] = ""
    for table in inspection.inspection["tables"]:
        section, subtotal_row = assignments[table["sheet_name"]]
        recipe["sections"][section]["assigned_table"] = table["table_id"]
        recipe = core.review_numeric_measure_columns(
            inspection.inspection,
            recipe,
            section_key=section,
            **_numeric_review_args(
                inspection.inspection,
                table["table_id"],
                ["Amount EUR"],
                excluded_cell_rows={"Amount EUR": {subtotal_row}},
            ),
            reviewer_ref="reviewer.teaching_fixture",
            reviewed_on="2026-09-14",
            numeric_locale="en",
            currency="EUR",
            unit="currency",
            scale="1",
            parse_policy="strict_all_nonblank_v1",
        )
    recipe_path = work / "reviewed_recipe.json"
    _write(recipe_path, recipe)
    core.build_report(
        source,
        output,
        recipe_path=recipe_path,
        language=language,
        document_language=language,
        report_type="management_report",
        run_id=run["context"]["run_id"],
        client_engagement=run["context"],
    )
    evidence = _read(output / "numeric_evidence_ledger.json")
    assert {entry["value"] for entry in evidence["entries"]} == {
        profit,
        "0",
        cash_movement,
    }
    assert len(evidence["entries"]) == 3
    assert all(
        entry["source"]["value"] == entry["value"] for entry in evidence["entries"]
    )
    assert {
        item["artifact_ref"]
        for entry in evidence["entries"]
        for item in entry["outputs"]
    } == {
        "output.report_docx",
        "output.report_draft",
        "output.report_tables",
    }
    assert (output / "report.docx").stat().st_size > 10000
    assert (output / "report_tables.xlsx").is_file()
    assert (output / "review_payload.json").is_file()
    assert (output / "final_artifacts.json").is_file()
    assert source.read_bytes() == original


@pytest.mark.parametrize("product", ["vera", "clara"])
@pytest.mark.parametrize("language", ["it", "en"])
def test_business_plan_kit_runs_and_revises_the_owning_product_case(
    tmp_path, monkeypatch, product, language
):
    from tests.plugins._business_teaching import planning_case

    monkeypatch.syspath_prepend(str(ROOT / "plugins/_shared/vendor/modules"))
    from courseware.library import CourseLibrary

    previous = None
    if product == "vera":
        run = _bound_case(
            tmp_path,
            monkeypatch,
            "business-planning",
            "business-planning",
            "demo",
            language=language,
        )
    else:
        from tests.plugins.test_business_planning import _clara_workspace

        kit = CourseLibrary(ROOT / "plugins/clara", {"business-planning"}).render(
            "business-planning", language, tmp_path / "kit"
        )
        workspace, request, base_output = _clara_workspace(
            tmp_path,
            {
                "entity_name": "Ciclo Arco",
                "planning_objective": "Assess the fictional pilot",
                "audience": "internal",
            },
        )
        (workspace / "inputs").mkdir()
        (workspace / ".clara-onboarding-local-only").write_text(
            "Fictional local lesson\n"
        )
    for phase in ("demo", "practice"):
        if product == "vera":
            output = Path(run["output_dir"])
            source_root = Path(run["context"]["run_root"]) / "inputs"
            paths = [Path(item["path"]) for item in run["context"]["input_bindings"]]
            request = output / "business_plan_case.json"
            report = output / "plan"
            args = ["--client-engagement", run["context_path"]]
            entry = "run_business_plan.py"
        else:
            source_root = workspace
            paths = []
            for source in kit["source_files" if phase == "demo" else "practice_files"]:
                path = workspace / "inputs" / Path(source).name
                path.write_bytes(Path(source).read_bytes())
                paths.append(path)
            if previous:
                parent = workspace / "inputs/prior-plan.json"
                parent.write_bytes(previous[1])
                paths.append(parent)
            report = base_output / phase
            args = ["--case-workspace", workspace]
            entry = "run_strategic_plan.py"
        case = planning_case(
            paths, source_root, language, previous[2] if previous else None
        )
        _write(request, case)
        if product == "clara":
            _write(
                workspace / "material_registry.json",
                {
                    "schema_version": 1,
                    "materials": [
                        {"path": s["path"], "sha256": s["sha256"], "role": s["role"]}
                        for s in case["sources"]
                    ],
                },
            )
        result = subprocess.run(
            [
                sys.executable,
                str(ROOT / "plugins/business-planning/scripts" / entry),
                "--case",
                str(request),
                "--source-root",
                str(source_root),
                "--output-dir",
                str(report),
                *map(str, args),
            ],
            capture_output=True,
            text=True,
            check=False,
            timeout=60,
        )
        assert result.returncode == 2, result.stdout + result.stderr
        plan_path = report / "business_plan.json"
        assert plan_path.is_file(), result.stdout + result.stderr
        plan = _read(plan_path)
        assert plan["status"] == "partial"
        assert len(plan["accepted_narrative"]) == 10
        assert all(n["provisional"] for n in plan["accepted_narrative"])
        assert plan["case"]["review"] == {"status": "pending"}
        assert (
            plan["calculations"]["pilot/2027-01/commercial_operating_result"]["value"]
            == "-260"
        )
        assert (
            plan["calculations"]["pilot/2027-03/commercial_operating_result"]["value"]
            == "280"
        )
        assert plan["case"]["assessment"]["decision"] == (
            "redesign" if previous else "test"
        )
        html = (report / "business_plan_review.html").read_text(encoding="utf-8")
        assert (
            "Ipotesi economiche del test"
            if language == "it"
            else "Pilot economics assumptions"
        ) in html
        assert "-260" in html and "280" in html
        if product == "vera":
            ledger = _complete_teaching_case(run, tmp_path / "case")
        if previous:
            assert previous[0].read_bytes() == previous[1]
            assert (
                plan["planning_cycle"]["parent_content_sha256"]
                == previous[2]["content_sha256"]
            )
            assert plan["planning_cycle"]["withheld_narrative_ids"] == []
            assert ("sabato" if language == "it" else "Saturday") in html
        else:
            previous = (plan_path, plan_path.read_bytes(), plan)
            if product == "vera":
                client = run["context"]["client_id"]
                engagement = run["context"]["engagement_id"]
                parent = tmp_path / "prior-plan.json"
                parent.write_bytes(previous[1])
                imported = [
                    ledger.import_document(
                        tmp_path / "case", client, engagement, p, "source"
                    )
                    for p in [
                        *sorted((tmp_path / "kit/files/practice").iterdir()),
                        parent,
                    ]
                ]
                prepared = ledger.prepare_run(
                    tmp_path / "case",
                    client,
                    engagement,
                    "business-planning",
                    _read(ROOT / "plugins/vera/.codex-plugin/plugin.json")["version"],
                    input_ids=[i["receipt"]["input_id"] for i in imported],
                    purpose="Revise the same fictional planning case from new supplied evidence",
                )
                run = ledger.start_run(
                    tmp_path / "case", engagement, prepared["run"]["run_id"]
                )


@pytest.mark.parametrize("language", ["it", "en", "fr", "de", "es"])
@pytest.mark.parametrize("phase,expected", [("demo", "38000"), ("practice", "31000")])
def test_financial_analysis_kit_runs_current_net_debt_pack(
    tmp_path, monkeypatch, language, phase, expected
):
    monkeypatch.syspath_prepend(str(ROOT / "plugins/_shared/vendor/modules"))
    from vera_financial_analysis import (
        build_data_package_manifest,
        build_dataset_contract,
        build_fdd_case,
    )

    run = _bound_case(
        tmp_path,
        monkeypatch,
        "financial-analysis",
        "financial-analysis",
        phase,
        language=language,
    )
    source = next(
        Path(item["path"])
        for item in run["context"]["input_bindings"]
        if Path(item["path"]).suffix == ".csv"
    )
    original = source.read_bytes()
    with source.open(encoding="utf-8", newline="") as stream:
        rows = list(csv.DictReader(stream))
    assert len(rows) == 4
    dates = {row["as_of_date"] for row in rows}
    assert len(dates) == 1
    as_of = dates.pop()
    output = Path(run["output_dir"])
    prepared_source = output / source.name
    prepared_source.write_bytes(original)
    assert prepared_source.read_bytes() == original
    package = build_data_package_manifest(
        package_id="package.teaching.v1",
        snapshot_id="snapshot.teaching.v1",
        reporting_perimeter={
            "entity_refs": ["entity.arco"],
            "period_start": as_of,
            "period_end": as_of,
            "currency_refs": ["EUR"],
        },
        sensitivity="confidential",
        sources=[
            {
                "source_id": "source.balances",
                "artifact_ref": "artifact.balances",
                "file_name": source.name,
                "locator": source.name,
                "byte_count": len(original),
                "sha256": hashlib.sha256(original).hexdigest(),
                "snapshot_id": "snapshot.teaching.v1",
                "dataset_contract_ref": "dataset.balances.v1",
            }
        ],
    )
    dataset = build_dataset_contract(
        dataset_contract_id="dataset.balances.v1",
        dataset_id="balances",
        version="v1",
        grain="one identified balance at the stated date",
        keys=["row_id"],
        fields=[
            {
                "name": "row_id",
                "concept_id": "row.identity",
                "data_type": "text",
                "nullable": False,
                "unit": "identifier",
                "currency": None,
                "aggregation": "none",
                "period_role": "none",
            },
            {
                "name": "amount",
                "concept_id": "financial.amount",
                "data_type": "decimal",
                "nullable": False,
                "unit": "EUR_units",
                "currency": "EUR",
                "aggregation": "sum",
                "period_role": "period_end",
            },
        ],
        period={
            "calendar": "gregorian",
            "grain": "month",
            "start": as_of,
            "end": as_of,
        },
        source_artifact_refs=["artifact.balances"],
    )
    # Explicit interpretation of the supplied fictional request in this test.
    # Native learners review their choices; this receipt is never in a kit.
    classification = {
        "loan": "debt",
        "cash": "cash",
        "deposit": "excluded",
        "payables": "excluded",
    }
    review = {
        "status": "reviewed",
        "reviewed_on": "2026-09-14",
        "reviewer_ref": "reviewer.teaching_fixture",
        "basis": "Test-only interpretation of the authored loan and available-cash definition.",
    }
    case = build_fdd_case(
        case_id="case.teaching",
        scope_id="scope.arco",
        entity_refs=["entity.arco"],
        pack_id="net_debt",
        currency="EUR",
        unit="EUR_units",
        reporting_period={"start": as_of, "end": as_of},
        package=package,
        datasets=[dataset],
        request_id="request.net_debt.v1",
        review=review,
        reviewed_decisions=[{"decision_ref": "decision.definition", **review}],
        inputs={
            "as_of_date": as_of,
            "items": [
                {
                    "item_id": "item." + row["row_id"],
                    "economic_effect_id": "effect." + row["row_id"],
                    "description": row["description"],
                    "as_of_date": as_of,
                    "classification": classification[row["row_id"]],
                    "amount": row["amount"],
                    "included": classification[row["row_id"]] != "excluded",
                    "decision_ref": "decision.definition",
                    "evidence_refs": ["artifact.balances"],
                }
                for row in rows
            ],
        },
    )
    stack = case["contract_stack"]
    bundle = {
        "schema_version": "vera.fdd_execution_bundle.v2",
        "fdd_case": case,
        **{
            key: stack[key]
            for key in ("package", "datasets", "relationships", "crosswalks", "request")
        },
    }
    # Use the current canonical serializer, not a separately invented seal.
    from tests.plugins._financial_analysis_test_loader import (
        load_financial_analysis_scripts,
    )

    modules = load_financial_analysis_scripts(
        ROOT / "plugins/financial-analysis/scripts"
    )
    bundle["content_sha256"] = modules.kernel.canonical_json_sha256(bundle)
    case_path = output / "case.json"
    _write(case_path, bundle)
    prepared = output / "prepared"
    _run(
        "plugins/financial-analysis/scripts/run_pack.py",
        "--pack",
        "net_debt",
        "--case",
        case_path,
        "--output-dir",
        prepared,
        "--client-engagement",
        run["context_path"],
    )
    receipt = _read(prepared / "pack_execution_receipt.json")
    result = _read(prepared / "fdd_result.json")
    assert receipt["status"] == "passed"
    assert receipt["report_ready"] is False
    assert {item["metric_id"]: item["value"] for item in result["metrics"]}[
        "net_debt"
    ] == expected
    assert result["source_tie_out"]["status"] == "not_assessed"
    assert (prepared / "financial_analysis_contract_audit.json").is_file()
    assert (prepared / "model_use_manifest.json").is_file()
    assert source.read_bytes() == original


@pytest.mark.parametrize(
    "phase,baseline,actual", [("demo", 47000, 53000), ("practice", 77000, 85000)]
)
def test_variance_kit_runs_current_full_amount_comparison(
    tmp_path, monkeypatch, phase, baseline, actual
):
    run = _bound_case(
        tmp_path, monkeypatch, "variance-analysis", "variance-analysis", phase
    )
    source = next(
        item["path"]
        for item in run["context"]["input_bindings"]
        if item["path"].endswith(".csv")
    )
    output = Path(run["output_dir"])
    scripts = "plugins/variance-analysis/scripts/"
    _run(
        scripts + "inspect_inputs.py",
        source,
        "--output-dir",
        output / "inspection",
        "--language",
        "it",
        "--client-engagement",
        run["context_path"],
    )
    recipe = _read(output / "inspection/suggested_recipe.json")
    assert recipe["mappings"]["baseline_period"] == "PL"
    assert recipe["mappings"]["comparison_period"] == "AC"
    # Fixed interpretation of this authored fixture, not a production mapping
    # heuristic or a review approval distributed with the lesson.
    recipe["mappings"].update(
        amount_column="Amount", units_column=None, dimensions=["Category", "Month"]
    )
    recipe["accounting_review"] = {
        "perimeter": {
            "status": "established",
            "description": "Fictional Officina Arco only; identical supplied 2026 months.",
        },
        "source_tie_out": {
            "baseline_source_total": baseline,
            "comparison_source_total": actual,
            "tolerance": 0.01,
        },
        "favorable_adverse_convention": {
            "status": "established",
            "description": "Positive revenue and negative costs; higher operating profit favorable.",
        },
        "materiality": {"status": "not_applied"},
    }
    reviewed_recipe = output / "reviewed-recipe.json"
    _write(reviewed_recipe, recipe)
    _run(
        scripts + "run_variance.py",
        source,
        "--output-dir",
        output / "variance",
        "--recipe",
        reviewed_recipe,
        "--currency",
        "EUR",
        "--language",
        "it",
        "--client-engagement",
        run["context_path"],
    )
    for filename in (
        "model_use_manifest.json",
        "variance_audit.json",
        "waterfall.png",
        "root_cause_sweep_summary.json",
        "root_cause_client_report.docx",
        "root_cause_client_report.md",
        "review_payload.json",
        "final_artifacts.json",
    ):
        artifact = output / "variance" / filename
        assert artifact.is_file() and artifact.stat().st_size > 0
    audit = _read(output / "variance/variance_audit.json")
    assert "approved_for_client_use" not in json.dumps(audit)


@pytest.mark.parametrize("language", ["it", "en", "fr", "de", "es"])
@pytest.mark.parametrize("phase,population", [("demo", 13), ("practice", 15)])
def test_journal_sampling_kit_normalizes_and_samples_current_bound_source(
    tmp_path, monkeypatch, language, phase, population
):
    run = _bound_case(
        tmp_path,
        monkeypatch,
        "journal-sampling",
        "journal-sampling",
        phase,
        language=language,
    )
    _sample_teaching_journal(run, monkeypatch, language, population=population)


def _sample_teaching_journal(
    run, monkeypatch, language, *, population, size=5, include_accounts=None
):
    source = Path(
        next(
            i["path"]
            for i in run["context"]["input_bindings"]
            if i["role"] == "journal"
        )
    )
    original = source.read_bytes()
    output = Path(run["output_dir"])
    normalization = output / "normalization"
    scripts = "plugins/journal-sampling/scripts/"
    common = (
        "--client-engagement",
        run["context_path"],
        "--language",
        language,
        "--document-language",
        "en",
    )
    _run(scripts + "inspect_journal.py", source, "--output-dir", normalization, *common)
    recipe_path = normalization / "suggested_recipe.json"
    recipe = _read(recipe_path)
    entry = recipe["files"][source.name]
    # These source meanings are authored in context-<language>.md. The fixed
    # regression review is not shipped as an approved recipe for the learner.
    entry["mapping"].update(movement_number="Entry", line_number="Line")
    entry.update(
        posting_identity="movement_number_and_line_number",
        decimal_separator=".",
        thousands_separator=None,
        excluded_monetary_columns=[],
        carry_forward_fields=[],
    )
    proposed = output / "mapped-recipe.json"
    _write(proposed, recipe)
    _run(
        scripts + "inspect_journal.py",
        source,
        "--output-dir",
        normalization,
        "--recipe",
        proposed,
        *common,
    )
    # Use the current receipt constructor on the exact newly inspected mapping.
    monkeypatch.syspath_prepend(str(ROOT / "tests/plugins"))
    from test_journal_sampling_plugin import _approve_suggested_recipe

    _approve_suggested_recipe(recipe_path)
    _run(
        scripts + "normalize_journal.py",
        source,
        "--output-dir",
        normalization,
        "--recipe",
        recipe_path,
        *common,
    )
    _run(
        scripts + "run_sample.py",
        normalization / "normalized_journal.csv",
        "--output-dir",
        output / "sample",
        "--method",
        "random",
        "--size",
        str(size),
        *(["--include-accounts", include_accounts] if include_accounts else []),
        *common,
    )
    with (normalization / "normalized_journal.csv").open(
        encoding="utf-8-sig", newline=""
    ) as stream:
        normalized = list(csv.DictReader(stream))
    with (output / "sample/journal_sample.csv").open(
        encoding="utf-8-sig", newline=""
    ) as stream:
        sampled = list(csv.DictReader(stream))
    assert len(normalized) == population
    assert len(sampled) == size
    assert all(row in normalized for row in sampled)
    assert source.read_bytes() == original
    for filename in (
        "journal_sample.xlsx",
        "sampling_audit.json",
        "sample_reproducibility.json",
        "sample_material_value_ledger.json",
        "sample_assurance_gates.json",
        "sample_assurance_envelope.json",
        "sample_output_receipts.json",
        "model_review_context.json",
        "final_artifacts.json",
    ):
        path = output / "sample" / filename
        assert path.is_file() and path.stat().st_size > 0


@pytest.mark.parametrize("language", ["it", "en", "fr", "de", "es"])
@pytest.mark.parametrize("phase,count", [("demo", 3), ("practice", 4)])
def test_purchase_invoice_kit_inputs_match_actual_bookings(
    tmp_path, monkeypatch, language, phase, count
):
    """Check source compatibility only; the native reviewer is a separate check."""
    monkeypatch.syspath_prepend(str(ROOT / "plugins/_shared/vendor/modules"))
    from courseware.library import CourseLibrary

    kit = CourseLibrary(ROOT / "plugins/vera", {"purchase-invoice-review"}).render(
        "purchase-invoice-review", language, tmp_path / "kit"
    )
    sources = kit["source_files" if phase == "demo" else "practice_files"]
    ledger = next(Path(p) for p in sources if p.endswith(".csv"))
    invoices = next(Path(p).parent for p in sources if p.endswith(".xml"))
    with ledger.open(encoding="utf-8", newline="") as stream:
        headers = csv.DictReader(stream).fieldnames
    mapping = tmp_path / "mapping.json"
    # The kit declares these canonical source fields. No reviewed mapping is
    # precomputed for the native teacher or distributed as an approved input.
    _write(mapping, {**{key: key for key in headers}, "number_format": "canonical"})
    spec = importlib.util.spec_from_file_location(
        "kit_passive_audit_core",
        ROOT / "plugins/passive-invoice-audit/scripts/audit_core.py",
    )
    core = importlib.util.module_from_spec(spec)
    monkeypatch.setitem(sys.modules, spec.name, core)
    spec.loader.exec_module(core)
    loaded = core.load_ledger(ledger, mapping)
    parsed = core.parse_invoice_population(invoices, tmp_path / "parsed")
    items, orphans = core.match_population(parsed, loaded, core.CENT)
    assert len(loaded) == count * 3
    assert len(parsed) == count
    assert len(items) == count
    assert orphans == []
    assert all(item["match_state"] == "matched" for item in items)
    assert all("invoice_number_exact" in item["match_evidence"] for item in items)


@pytest.mark.parametrize(
    "phase,total,row_count", [("demo", "119000", 9), ("practice", "117000", 12)]
)
def test_centrale_rischi_kit_runs_actual_inspection_analysis_and_delivery(
    tmp_path, monkeypatch, phase, total, row_count
):
    run = _bound_case(
        tmp_path, monkeypatch, "centrale-rischi-review", "centrale-rischi-review", phase
    )
    source = next(
        item["path"]
        for item in run["context"]["input_bindings"]
        if item["path"].endswith(".csv")
    )
    output = Path(run["output_dir"])
    context = run["context_path"]
    scripts = "plugins/centrale-rischi-review/scripts/"
    _run(
        scripts + "inspect_inputs.py",
        "--input",
        source,
        "--output-dir",
        output / "inspection",
        "--client-engagement",
        context,
    )
    inventory = _read(output / "inspection/inspection.json")
    assert inventory["tables"][0]["row_count"] == row_count
    # The kit declares these meanings explicitly in caso.md. This fixed review
    # belongs only to this fictional regression case; it is never a classifier
    # or a professional approval copied into a user's lesson.
    recipe = {
        "schema_version": "vera.centrale_rischi_recipe.v2",
        "workflow_id": "centrale-rischi-review",
        "inventory_sha256": inventory["inventory_sha256"],
        "entity": "Officina Arco Srl — fictional kit",
        "currency": "EUR",
        "analysis_mode": "trend",
        "analysis_objective": "Explain current bank exposure and monthly movement.",
        "audience": "professional",
        "source_kind": "tabular_export",
        "source_document_sha256": "",
        "table_id": inventory["tables"][0]["table_id"],
        "columns": {
            "reference_month": "Mese",
            "intermediary": "Intermediario",
            "risk_category": "Categoria",
            "original_duration": "Durata originaria",
            "residual_duration": "Durata residua",
            "granted": "Accordato",
            "operational_granted": "Operativo",
            "used": "Utilizzato",
            "guarantee_type": "Garanzia",
            "guaranteed_amount": "Garantito",
            "prejudicial_event": "Pregiudizievole",
        },
        "value_mappings": {
            "original_term": {"Fino a 1 anno": "short", "Oltre 5 anni": "long"},
            "residual_term": {
                "Fino a 1 anno": "within_one_year",
                "Oltre 1 anno": "over_one_year",
            },
            "exposure_family": {
                "A revoca": "performing",
                "A scadenza": "performing",
                "Autoliquidante": "performing",
            },
        },
        "control_totals": {"used": total},
        "control_tolerance": "0.01",
        "mapping_review": {
            "status": "reviewed",
            "reviewer": "Declared fictional fixture meanings",
            "reviewed_at": "2026-09-14T07:00:00+02:00",
        },
    }
    recipe_path = output / "inspection/reviewed_recipe.json"
    _write(recipe_path, recipe)
    _run(
        scripts + "run_analysis.py",
        "--input",
        source,
        "--recipe",
        recipe_path,
        "--output-dir",
        output / "analysis",
        "--client-engagement",
        context,
    )
    analysis_path = output / "analysis/centrale_rischi_analysis.json"
    analysis = _read(analysis_path)
    assert analysis["status"] == "complete"
    metrics = {item["metric_id"]: item for item in analysis["metrics"]}
    assert metrics["cr.total_used"]["value"] == total
    assert metrics["financial.dscr"]["availability"] == "unavailable"
    assert analysis["controls"][0]["status"] == "passed"
    commentary = _read(output / "analysis/commentary_template.json")
    commentary["observations"] = [
        {
            "text": f"The fictional current total is EUR {total}.",
            "evidence_refs": ["metric:cr.total_used"],
        }
    ]
    commentary["limitations"] = [
        "Mechanical kit regression only; native teaching and professional review are unverified."
    ]
    commentary_path = output / "analysis/commentary.json"
    _write(commentary_path, commentary)
    _run(
        scripts + "finalize_analysis.py",
        "--analysis",
        analysis_path,
        "--commentary",
        commentary_path,
        "--output-dir",
        output / "review",
        "--client-engagement",
        context,
    )
    assert (output / "analysis/centrale_rischi_analysis.xlsx").stat().st_size > 0
    assert (output / "review/centrale_rischi_dashboard_reviewed.html").is_file()
    assert (
        _read(output / "review/commentary_receipt.json")["status"]
        == "draft_pending_professional_review"
    )
    assert _read(tmp_path / "kit/course-provenance.json")["execution_receipt"] is False


@pytest.mark.parametrize(
    "phase,numbers",
    [
        ("demo", ["DEMO-001", "DEMO-002", "DEMO-003"]),
        ("practice", ["DEMO-001", "DEMO-002", "DEMO-003", "DEMO-004"]),
    ],
)
@pytest.mark.parametrize("language", ["it", "en", "fr", "de", "es"])
def test_xml_kit_runs_actual_managed_parser_with_demo_and_practice_files(
    tmp_path, monkeypatch, phase, numbers, language, record_property
):
    run = _bound_case(
        tmp_path,
        monkeypatch,
        "fatture-xml-check",
        "client-file-preparation",
        phase,
        language=language,
    )
    output = Path(run["output_dir"]) / "invoices"
    _run(
        "plugins/client-file-preparation/scripts/parse_fatturapa_xml.py",
        run["context"]["input_dir"],
        "--year",
        "2026",
        "--out",
        output,
        "--client-engagement",
        run["context_path"],
    )
    with (output / "fatture_summary.csv").open(encoding="utf-8", newline="") as stream:
        rows = list(csv.DictReader(stream))
    assert sorted(row["invoice_number"] for row in rows) == numbers
    assert {row["currency"] for row in rows} == {"EUR"}
    assert sum(Decimal(row["total_amount"]) for row in rows) == Decimal(
        "2440.00" if phase == "demo" else "3416.00"
    )
    assert {row["invoice_date"][:7] for row in rows} == (
        {"2026-03"} if phase == "demo" else {"2026-03", "2026-04"}
    )
    assert (output / "formal_anomalies.md").is_file()
    _complete_teaching_case(run, tmp_path / "case")
    record_native_check(
        record_property,
        root=ROOT,
        product="vera",
        workflow="fatture-xml-check",
        language=language,
        phase=phase,
    )


@pytest.mark.parametrize("product", ["vera", "clara"])
@pytest.mark.parametrize(
    "phase,end,actual,budget,variance",
    [
        ("demo", "2026-02-28", "53000", "47000", "6000"),
        ("practice", "2026-03-31", "85000", "77000", "8000"),
    ],
)
def test_budget_kits_run_the_owning_product_report_pipeline(
    tmp_path, monkeypatch, product, phase, end, actual, budget, variance
):
    if product == "vera":
        run = _bound_case(
            tmp_path,
            monkeypatch,
            "management-control-pack",
            "management-control-pack",
            phase,
        )
        source = next(
            item["path"]
            for item in run["context"]["input_bindings"]
            if item["path"].endswith(".xlsx")
        )
        output = Path(run["output_dir"])
        _run(
            "plugins/management-control-pack/scripts/inspect_inputs.py",
            "--input",
            source,
            "--output-dir",
            output / "inspection",
            "--client-engagement",
            run["context_path"],
        )
    else:
        monkeypatch.syspath_prepend(str(ROOT / "plugins/_shared/vendor/modules"))
        from courseware.library import CourseLibrary

        kit = CourseLibrary(ROOT / "plugins/clara", {"reporting-engine"}).render(
            "reporting-engine", "it", tmp_path / "kit"
        )
        source = next(
            p
            for p in kit["source_files" if phase == "demo" else "practice_files"]
            if p.endswith(".xlsx")
        )
        output = tmp_path / "clara-report"
        spec = importlib.util.spec_from_file_location(
            "kit_budget_report",
            ROOT / "plugins/clara/modules/reporting-engine/scripts/budget_report.py",
        )
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        assert (
            module.main(
                [
                    "inspect",
                    "--input",
                    source,
                    "--output-dir",
                    str(output / "inspection"),
                ]
            )
            == 0
        )
    inventory = _read(output / "inspection/inspection.json")
    tables = {t["table_label"]: t["table_id"] for t in inventory["tables"]}
    recipe = {
        "schema_version": "vera.management_control_recipe.v1",
        "workflow_id": "management-control-pack",
        "inventory_sha256": inventory["inventory_sha256"],
        "entity": "Arco — fictional teaching data",
        "reporting_period": {"start": "2026-01-01", "end": end, "cutoff": end},
        "currency": "EUR",
        "fiscal_year_start_month": 1,
        "number_format": "dot_decimal",
        "date_format": "%Y-%m-%d",
        "tables": {
            "general_ledger": {
                "table_id": tables["GL"],
                "columns": {
                    "date": "Date",
                    "account_code": "Account",
                    "category": "Category",
                    "amount": "Amount",
                },
            },
            "budget": {
                "table_id": tables["Budget"],
                "columns": {"date": "Date", "category": "Category", "amount": "Amount"},
            },
        },
        "category_roles": {
            "Revenue": "revenue",
            "COGS": "cogs",
            "Operating expenses": "operating_expense",
        },
        "category_multipliers": {},
        "aging_buckets": [30, 60, 90],
        "top_customers": 10,
        "control_totals": {"general_ledger": actual, "budget": budget},
        "control_tolerance": "0.01",
        "mapping_review": {
            "status": "reviewed",
            "reviewer": "Declared fictional kit meanings only",
            "reviewed_at": "2026-09-14T07:00:00+02:00",
        },
        "audience": "public_demo",
    }
    recipe_path = output / "reviewed_recipe.json"
    _write(recipe_path, recipe)
    args = [
        "--input",
        source,
        "--recipe",
        str(recipe_path),
        "--output-dir",
        str(output / "report"),
    ]
    if product == "vera":
        _run(
            "plugins/management-control-pack/scripts/run_pack.py",
            *args,
            "--client-engagement",
            run["context_path"],
        )
    else:
        assert module.main(["run", *args]) == 0
    pack = _read(output / "report/management_control_pack.json")
    assert pack["status"] != "blocked"
    assert pack["metrics"]["budget.total.ebitda_variance"]["value"] == variance
    assert (output / "report/management_control_pack.xlsx").stat().st_size > 0
    assert (output / "report/management_control_dashboard.html").is_file()


def test_treasury_kit_inputs_produce_real_reviewable_forecast_without_acceptance(
    tmp_path, monkeypatch
):
    run = _bound_case(
        tmp_path, monkeypatch, "treasury-forecast", "treasury-forecast", "demo"
    )
    manifest = next(
        item["path"]
        for item in run["context"]["input_bindings"]
        if item["path"].endswith("manifest.json")
    )
    _run(
        "plugins/treasury-forecast/scripts/run_treasury.py",
        "prepare",
        "--client-engagement",
        run["context_path"],
        "--manifest",
        manifest,
    )
    output = Path(run["output_dir"])
    artifacts = _read(output / "final_artifacts.json")
    forecast = _read(output / artifacts["forecast"])
    assert forecast["company_name"] == "Officina Arco — caso fittizio"
    assert len(forecast["events"]) == 5
    assert not forecast["review"]
    assert (output / artifacts["report"]).is_file()
    assert (output / artifacts["workbook"]).stat().st_size > 0


@pytest.mark.parametrize("phase,evidence_count", [("demo", 3), ("practice", 4)])
def test_lucia_kit_inputs_become_bound_evidence_in_the_actual_matter_package(
    tmp_path, monkeypatch, phase, evidence_count
):
    run = _bound_case(
        tmp_path,
        monkeypatch,
        "apertura-pratica",
        "apertura-pratica",
        phase,
        product="lucia",
    )
    output = Path(run["output_dir"])
    scripts = "plugins/apertura-pratica/scripts/"
    _run(
        scripts + "initialize_workspace.py",
        output,
        "--opening-mode",
        "new_client_new_matter",
        "--client-reference",
        "beta-fictional",
        "--matter-reference",
        "delivery-fictional",
        "--language",
        "it",
    )
    for item in run["context"]["input_bindings"]:
        evidence_role = {
            "register.csv": "firm_record",
            "update-it.md": "correspondence",
        }.get(Path(item["path"]).name, "client_supplied")
        _run(
            scripts + "add_evidence.py",
            output,
            item["path"],
            "--role",
            evidence_role,
        )
    intake_path = output / "matter_intake.json"
    intake = _read(intake_path)
    intake["client"]["display_name"] = "Beta Laboratorio Srl"
    intake["client"]["identity_status"] = "reported"
    intake["client"]["evidence_ids"] = [
        item["evidence_id"]
        for item in intake["evidence_register"]
        if item["original_name"] == "request-it.md"
    ]
    intake["parties"][0].update(
        display_name="Beta Laboratorio Srl",
        identity_status="reported",
        evidence_ids=intake["client"]["evidence_ids"],
        assessment_basis="Client named in the supplied fictional request.",
    )
    intake["matter"].update(
        title="Consegna di componenti — caso fittizio",
        objective="Preparare il dossier per la revisione dell’avvocato",
        requested_work="Organizzare la controversia di fornitura con Gamma Forniture",
        summary="La richiesta fittizia descrive 100 componenti ordinati, 80 consegnati e un anticipo di EUR 3.000. Nessuna decisione professionale è stata fornita.",
    )
    _write(intake_path, intake)
    _run(scripts + "prepare_review.py", output)
    evidence = _read(intake_path)["evidence_register"]
    assert len(evidence) == evidence_count
    assert all((output / item["stored_path"]).is_file() for item in evidence)
    assert "Beta Laboratorio" in (output / "matter_opening_memo.md").read_text(
        encoding="utf-8"
    )
    assert _read(output / "validation_report.json")["status"] != "ready_to_open"
    assert not (output / "applied_decisions.json").exists()


@pytest.mark.parametrize("phase,expected", [("demo", 2), ("practice", 3)])
def test_bank_reconciliation_kit_runs_current_comparison(
    tmp_path, monkeypatch, phase, expected
):
    run = _bound_case(
        tmp_path,
        monkeypatch,
        "journal-bank-reconciliation",
        "journal-bank-reconciliation",
        phase,
    )
    files = {
        Path(item["path"]).name: Path(item["path"])
        for item in run["context"]["input_bindings"]
    }
    month = "march" if phase == "demo" else "april"
    bank = files[f"bank-{month}.csv"]
    journal = files[f"bank-ledger-{month}.csv"]
    output = Path(run["output_dir"])
    scripts = "plugins/journal-bank-reconciliation/scripts/"
    inspection = output / "inspection"
    _run(
        scripts + "inspect_inputs.py",
        bank,
        journal,
        "--client-engagement",
        run["context_path"],
        "--output-dir",
        inspection,
        "--language",
        "it",
    )
    monkeypatch.syspath_prepend(str(ROOT / scripts))
    spec = importlib.util.spec_from_file_location(
        "journal_bank_core", ROOT / scripts / "journal_bank_core.py"
    )
    core = importlib.util.module_from_spec(spec)
    monkeypatch.setitem(sys.modules, spec.name, core)
    spec.loader.exec_module(core)
    recipe_path = inspection / "suggested_recipe.json"
    recipe = _read(recipe_path)
    # Fixed fictional case authority only: exact individual outgoing payments,
    # no tolerance, no reused evidence. Never shipped as a learner's approval.
    policy = {
        **recipe["relationship"]["policy"],
        "amount_tolerance": "0",
        "date_window_days": 0,
    }
    recipe["matching"]["amount_tolerance"] = "0"
    recipe["matching"]["date_window_days"] = 0
    refs = [
        row["artifact_id"]
        for row in _read(inspection / "input_receipts.json")["receipts"]
        if row["artifact_id"].startswith(("source.bank.", "source.journal."))
    ]
    recipe["relationship"] = {
        "policy": policy,
        "review_content_sha256": core.canonical_json_sha256({"policy": policy}),
        "decision": core.build_relationship_review_receipt(
            decision_id="decision.relationship",
            reviewer_ref="reviewer.teaching_fixture",
            reviewed_on="2026-09-14",
            source_artifact_refs=refs,
            policy=policy,
        ),
    }
    _write(recipe_path, recipe)
    result = output / "reconciliation"
    _run(
        scripts + "run_reconciliation.py",
        bank,
        journal,
        "--client-engagement",
        run["context_path"],
        "--output-dir",
        result,
        "--recipe",
        recipe_path,
        "--language",
        "it",
        "--tolerance",
        "0",
        "--date-window-days",
        "0",
    )
    audit = _read(result / "reconciliation_audit.json")
    assert audit["matched_count"] == expected
    assert audit["unmatched_bank_count"] == 0
    assert audit["unmatched_journal_count"] == 0
    assert list(result.glob("*.xlsx"))
    assert (result / "review_notes.md").is_file()
    assert (
        _read(result / "assurance_gates.json")["gates"]["source"]["status"] == "passed"
    )


@pytest.mark.parametrize("phase,closed", [("demo", 2), ("practice", 3)])
@pytest.mark.parametrize("language", ["it", "en", "fr", "de", "es"])
def test_open_item_kit_runs_current_pdf_ingestion_and_workpapers(
    tmp_path, monkeypatch, phase, closed, language
):
    run = _bound_case(
        tmp_path,
        monkeypatch,
        "open-item-reconciliation",
        "open-item-reconciliation",
        phase,
        language=language,
    )
    output = Path(run["output_dir"])
    input_root = Path(run["context"]["input_dir"])
    decisions = {}
    for item in run["context"]["input_bindings"]:
        source = Path(item["path"])
        is_population = source.name == f"open-items-{language}.pdf"
        decisions[source.relative_to(input_root).as_posix()] = {
            "role": "open_items" if is_population else "bank_statement",
            "adapter_family": (
                "open_items_text_v1" if is_population else "bank_statement_text_v1"
            ),
            "reviewer_ref": "reviewer.teaching_fixture",
            "reviewed_on": "2026-09-14",
            "perimeter": {
                "entity_ref": "entity.arco",
                "party_ref": "party.servizi_esempio",
                "currency": "EUR",
                "unit": "currency_amount",
                "direction_policy": "supplier",
                "allocation_policy": "one_to_one",
            },
            "money": {
                "decimal_separator": ",",
                "thousands_separator": ".",
                "reported_unit": "EUR",
                "reported_increment": "0.01",
            },
            "date": {"order": "day_first"},
        }
    assumptions = {
        "scope_year": "2026",
        "cutoff_date": "2026-03-31" if phase == "demo" else "2026-04-30",
        "assurance_run_date": "2026-09-14",
        "post_cutoff_events_excluded": True,
        "reviewed_source_decisions": decisions,
        "counterparty_keywords": ["servizi esempio"],
        "ocr_scanned": False,
    }
    # Use the workflow's supported Python entrypoint. Its validated output tree
    # is closed; a test parameter file is not a workflow deliverable.
    # A fresh interpreter also prevents pytest module cleanup from reloading
    # PyMuPDF's native extension between language cases.
    execution = subprocess.run(
        [
            sys.executable,
            "-I",
            "-B",
            "-c",
            """
import importlib.util, json, sys
spec = importlib.util.spec_from_file_location('kit_open_item_runner', sys.argv[1])
runner = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = runner
spec.loader.exec_module(runner)
context = runner.load_client_engagement_context_file(
    sys.argv[2], expected_workflow_id='open-item-reconciliation')
runner.run_raw_input_reconciliation(
    input_dir=context['input_dir'], prepared_client_engagement=context,
    assumptions=json.loads(sys.argv[3]), language=sys.argv[4],
    title='Officina Arco - fictional teaching case')
""",
            str(ROOT / "plugins/open-item-reconciliation/scripts/raw_input_runner.py"),
            run["context_path"],
            json.dumps(assumptions),
            language,
        ],
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=60,
        check=False,
    )
    assert execution.returncode == 0, execution.stdout + execution.stderr
    assert (output / "riconciliazione_audit.xlsx").is_file()
    assert (output / "relazione_riconciliazione_audit.docx").is_file()
    assert (output / "review_ui.html").is_file()
    canonical = _read(output / "assurance_final_outputs/reconciliation_results.json")
    assert not canonical["source_processing"]["extraction_errors"]
    rows = canonical["reconciliation_rows"]
    assert len(rows) == 3
    assert sum(row["reconciliation_status"] == "closed" for row in rows) == closed
    assert (
        sum(row["reconciliation_status"] == "unresolved" for row in rows) == 3 - closed
    )
    if phase == "practice":
        third = next(row for row in rows if row["document_key"] == "3FF|2026")
        assert third["supporting_bank_date"] == "2026-04-04"
    assert _read(output / "final_artifacts.json")["status"] != "final_ready"


@pytest.mark.parametrize("phase", ["demo", "practice"])
@pytest.mark.parametrize("language", ["it", "en", "fr", "de", "es"])
def test_new_client_kit_runs_actual_dossier_from_reported_facts(
    tmp_path, monkeypatch, phase, language, record_property
):
    run = _bound_case(
        tmp_path, monkeypatch, "new-client", "new-client", phase, language=language
    )
    output = Path(run["output_dir"])
    scripts = "plugins/new-client/scripts/"
    _run(
        scripts + "initialize_case.py",
        "--case-dir",
        output,
        "--client-engagement",
        run["context_path"],
        "--client-reference",
        "ARCO-DEMO",
        "--assessment-date",
        "2026-09-14",
        "--language",
        language,
    )
    path = output / "new_client_input.json"
    intake = _read(path)
    evidence = []
    for item in run["context"]["input_bindings"]:
        source = Path(item["path"])
        evidence.append(
            {
                "evidence_id": (
                    "profile"
                    if source.name.startswith("profile-")
                    else "contact-update"
                ),
                "evidence_type": "fictional_interview_notes",
                "status": "available",
                "obtained_on": "2026-09-14",
                "expires_on": None,
                "local_path": str(source),
                "sha256": hashlib.sha256(source.read_bytes()).hexdigest(),
            }
        )
    intake["evidence_register"] = evidence
    intake["client_file_preparation_binding"]["evidence_ids"] = [
        row["evidence_id"] for row in evidence
    ]
    # These are declared teaching facts, not confirmed legal or identity findings.
    facts = {
        "registered_identity": "Officina Arco Srl",
        "registered_address": "Via Esempio 10, Milano, Italia",
        "business_activity": {
            "it": "Officina meccanica - caso fittizio",
            "en": "Mechanical workshop - fictional case",
            "fr": "Atelier mécanique - cas fictif",
            "de": "Mechanische Werkstatt - fiktiver Fall",
            "es": "Taller mecánico - caso ficticio",
        }[language],
        "representative_reported": "Elena Esempio",
        "shareholdings_reported": "Elena Esempio 60%; Paolo Prova 40%",
    }
    intake["party_facts"] = [
        {
            "fact_id": "party-fact-01" if index == 0 else f"party-fact-{index + 1:02}",
            "fact_code": key,
            "value": value,
            "verification_status": "reported",
            "evidence_ids": ["profile"],
        }
        for index, (key, value) in enumerate(facts.items())
    ]
    if phase == "practice":
        intake["party_facts"].append(
            {
                "fact_id": "contact-fact",
                "fact_code": "administrative_contact",
                "value": "Sara Campione; sara@arco.example; document exchange only",
                "verification_status": "reported",
                "evidence_ids": ["contact-update"],
            }
        )
    intake["engagement"]["services"][0]["description"] = {
        "it": "Tenuta contabile mensile e preparazione del bilancio 2026.",
        "en": "Monthly bookkeeping and preparation of the 2026 financial statements.",
        "fr": "Tenue comptable mensuelle et préparation des comptes annuels 2026.",
        "de": "Monatliche Buchführung und Vorbereitung des Jahresabschlusses 2026.",
        "es": "Contabilidad mensual y preparación de las cuentas anuales de 2026.",
    }[language]
    _write(path, intake)
    _run(
        scripts + "package_new_client.py",
        "--input",
        path,
        "--client-engagement",
        run["context_path"],
        "--output-dir",
        output,
    )
    assert (output / "studio_new_client_memo.md").is_file()
    assert (output / "client_missing_information_draft.md").is_file()
    assert (output / "document_plan.json").is_file()
    assert (output / "monitoring_plan.json").is_file()
    saved = _read(output / "case_facts_validated.json")
    assert "Officina Arco Srl" in json.dumps(saved)
    assert ("Sara Campione" in json.dumps(saved)) == (phase == "practice")
    final = _read(output / "final_artifacts.json")
    assert final["professional_review_required"] is True
    assert final["relationship_activation_performed"] is False
    assert final["signature_performed"] is False
    for action in ("seal", "validate"):
        _run(
            scripts + "delivery_manifest.py",
            action,
            "--client-engagement",
            run["context_path"],
            "--output-dir",
            output,
        )
    record_native_check(
        record_property,
        root=ROOT,
        product="vera",
        workflow="new-client",
        language=language,
        phase=phase,
    )


@pytest.mark.parametrize("phase,expected_documents", [("demo", 2), ("practice", 3)])
@pytest.mark.parametrize("language", ["it", "en", "fr", "de", "es"])
def test_fiscal_data_kit_runs_actual_preparation_and_extraction(
    tmp_path, monkeypatch, phase, expected_documents, language, record_property
):
    run = _bound_case(
        tmp_path,
        monkeypatch,
        "dati-fiscali-strutturati",
        "client-file-preparation",
        phase,
        language=language,
    )
    output = Path(run["output_dir"])
    _run(
        "plugins/client-file-preparation/scripts/build_file_preparation_outputs.py",
        run["context"]["input_dir"],
        "--client-engagement",
        run["context_path"],
        "--year",
        "2026",
        "--jurisdiction",
        "italy",
        "--language",
        language,
        "--no-ocr",
    )
    with (output / "extracted/structured_fiscal_fields.csv").open(
        encoding="utf-8-sig", newline=""
    ) as stream:
        fields = list(csv.DictReader(stream))
    assert len({row["relative_path"] for row in fields}) == expected_documents
    codes = {row["field_code"]: row["normalized_value"] for row in fields}
    assert codes["redditi_lavoro_dipendente"] == "28000.00"
    assert codes["ritenute_irpef"] == "5000.00"
    debit_values = {
        row["normalized_value"]
        for row in fields
        if row["field_code"] == "importo_debito"
    }
    assert debit_values == ({"1200.00"} if phase == "demo" else {"1200.00", "900.00"})
    assert (output / "08_dati_fiscali_strutturati.md").is_file()
    assert (output / "extracted/extraction_report.md").is_file()
    handoff = _read(output / "model_handoff.json")
    assert handoff
    _complete_teaching_case(run, tmp_path / "case")
    record_native_check(
        record_property,
        root=ROOT,
        product="vera",
        workflow="dati-fiscali-strutturati",
        language=language,
        phase=phase,
    )


@pytest.mark.parametrize("phase,documents", [("demo", 1), ("practice", 2)])
@pytest.mark.parametrize("language", ["it", "en", "fr", "de", "es"])
def test_notice_kit_runs_actual_intake_and_keeps_source_dates(
    tmp_path, monkeypatch, phase, documents, language
):
    run = _bound_case(
        tmp_path,
        monkeypatch,
        "avviso-intake",
        "client-file-preparation",
        phase,
        language=language,
    )
    output = Path(run["output_dir"])
    _run(
        "plugins/client-file-preparation/scripts/build_file_preparation_outputs.py",
        run["context"]["input_dir"],
        "--client-engagement",
        run["context_path"],
        "--year",
        "2026",
        "--jurisdiction",
        "italy",
        "--language",
        language,
        "--no-ocr",
    )
    extracted = [
        json.loads(line)
        for line in (output / "extracted/documents.jsonl")
        .read_text(encoding="utf-8")
        .splitlines()
        if line
    ]
    assert len(extracted) == documents
    table = (output / "avviso/deadlines_and_amounts.csv").read_text(encoding="utf-8")
    assert "02/04/2026" in table
    assert "30/04/2026" in table
    assert "DEMO-NOTICE-01" in table
    assert (output / "avviso/avviso_intake_memo.md").is_file()
    assert (output / "model_handoff.json").is_file()
    assert _read(output / "final_artifacts.json")["status"] != "final_ready"


EMAIL_REQUESTS = {
    "it": (
        "Conferma se hai altre CU per la campagna 2026.",
        "Conferma se ci hai consegnato tutti gli F24 della campagna 2026.",
    ),
    "en": (
        "Please confirm whether you have other CUs for the 2026 campaign.",
        "Please confirm whether you have supplied all F24s for the 2026 campaign.",
    ),
    "fr": (
        "Merci de confirmer si vous avez d’autres CU pour la campagne 2026.",
        "Merci de confirmer si tous les F24 de la campagne 2026 ont été transmis.",
    ),
    "de": (
        "Bitte bestätigen Sie, ob weitere CU für die Kampagne 2026 vorliegen.",
        "Bitte bestätigen Sie, ob sämtliche F24 für die Kampagne 2026 übermittelt wurden.",
    ),
    "es": (
        "Confirma si tienes otras CU para la campaña de 2026.",
        "Confirma si has entregado todos los F24 de la campaña de 2026.",
    ),
}
EMAIL_FRAME = {
    "it": (
        "Bozza email cliente",
        "Oggetto: Conferme sui documenti ricevuti",
        "Buongiorno CLIENT-001,",
        "Grazie,\nLo studio",
    ),
    "en": (
        "Client email draft",
        "Subject: Confirmation of documents received",
        "Hello CLIENT-001,",
        "Thank you,\nThe practice",
    ),
    "fr": (
        "Projet de courriel au client",
        "Objet : Confirmation des documents reçus",
        "Bonjour CLIENT-001,",
        "Merci,\nLe cabinet",
    ),
    "de": (
        "Entwurf der Mandanten-E-Mail",
        "Betreff: Bestätigung der erhaltenen Unterlagen",
        "Guten Tag CLIENT-001,",
        "Vielen Dank,\nDie Kanzlei",
    ),
    "es": (
        "Borrador de correo al cliente",
        "Asunto: Confirmación de documentos recibidos",
        "Hola CLIENT-001:",
        "Gracias,\nEl despacho",
    ),
}


def _client_review_tool(output, context, name, decisions):
    import shutil

    node = shutil.which("node")
    assert node, "The declared Node runtime is required for persistent review."
    request = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "tools/call",
        "params": {
            "name": name,
            "arguments": {
                "client_engagement": str(context),
                "run_intake": _read(output / "run_intake.json"),
                "review_payload": _read(output / "review_payload.json"),
                "final_artifacts": _read(output / "final_artifacts.json"),
                "ui_decisions": _read(output / "ui_decisions.json"),
                "decisions": decisions,
                "reviewer": "fictional-kit-regression-reviewer",
                "decision_source": "synthetic-regression-fixture",
            },
        },
    }
    process = subprocess.run(
        [node, str(ROOT / "plugins/client-file-preparation/mcp/server.cjs"), "--stdio"],
        input=json.dumps(request) + "\n",
        capture_output=True,
        text=True,
        timeout=60,
        cwd=ROOT,
        check=False,
    )
    assert process.returncode == 0, process.stderr
    response = next(
        json.loads(line)
        for line in process.stdout.splitlines()
        if json.loads(line).get("id") == 1
    )
    result = response["result"]["structuredContent"]
    assert result["ok"] is True, result
    return result


def _reviewed_email_requests(output):
    handoff = _read(output / "model_handoff.json")
    items = []
    for page in handoff["pagination"]["pages"]:
        path = output / page["path"]
        assert hashlib.sha256(path.read_bytes()).hexdigest() == page["sha256"]
        items.extend(_read(path)["items"])
    return [item for item in items if item["kind"] == "email_request"]


@pytest.mark.parametrize("language", ["it", "en", "fr", "de", "es"])
@pytest.mark.parametrize("phase", ["demo", "practice"])
def test_client_email_kit_runs_intake_review_and_sealed_draft_replacement(
    tmp_path, monkeypatch, language, phase
):
    run = _bound_case(
        tmp_path,
        monkeypatch,
        "email-cliente",
        "client-file-preparation",
        phase,
        language=language,
    )
    output = Path(run["output_dir"])
    _run(
        "plugins/client-file-preparation/scripts/build_file_preparation_outputs.py",
        run["context"]["input_dir"],
        "--client-engagement",
        run["context_path"],
        "--year",
        "2026",
        "--jurisdiction",
        "italy",
        "--language",
        language,
        "--no-ocr",
    )
    assert _reviewed_email_requests(output) == []
    payload = _read(output / "review_payload.json")
    missing = [
        item
        for item in payload["items"]
        if item["item_type"] == "missing_document_request"
    ]
    cu = next(item for item in missing if "CU" in item["data"]["request_text"])
    f24 = next(item for item in missing if "F24" in item["data"]["request_text"])
    decisions = []
    # Model-authored review for these exact fictional sources. The practice
    # reply closes the F24 question; the CU question is still open. These
    # fixture decisions are not bundled or copied into a learner's session.
    for item in payload["items"]:
        decision = {"item_id": item["id"], "action": "accept"}
        if item["item_type"] == "missing_document_request":
            decision["action"] = "reject"
        if item["id"] == cu["id"] or (item["id"] == f24["id"] and phase == "demo"):
            decision.update(
                action="request_more_documents",
                requested_documents=[
                    EMAIL_REQUESTS[language][0 if item["id"] == cu["id"] else 1]
                ],
            )
        if item["id"] == "draft-client-email":
            decision["action"] = "skip"
        decisions.append(decision)
    for action in ("save", "apply"):
        _client_review_tool(
            output,
            run["context_path"],
            f"{action}_client_file_preparation_decisions",
            decisions,
        )
    requests = _reviewed_email_requests(output)
    assert len(requests) == (2 if phase == "demo" else 1)
    assert all(item["client_reference"] == "CLIENT-001" for item in requests)
    title, subject, greeting, closing = EMAIL_FRAME[language]
    # This test draft consumes only the actual reviewed request page items.
    replacement = (
        f"# {title}\n\n{subject}\n\n{greeting}\n\n"
        + "\n".join("- " + item["request_text"] for item in requests)
        + f"\n\n{closing}\n"
    )
    before = (output / "04_bozza_email_cliente.md").read_bytes()
    for decision in decisions:
        if decision["item_id"] == "draft-client-email":
            decision.update(action="edit", edit_value=replacement)
    for action in ("save", "apply"):
        _client_review_tool(
            output,
            run["context_path"],
            f"{action}_client_file_preparation_decisions",
            decisions,
        )
    assert (output / "04_bozza_email_cliente.md").read_text() == replacement
    final = _read(output / "final_artifacts.json")
    record = next(
        item for item in final["outputs"] if item["path"] == "04_bozza_email_cliente.md"
    )
    assert record["sha256"] == hashlib.sha256(replacement.encode()).hexdigest()
    assert any(
        path.read_bytes() == before
        for path in output.rglob("*.md")
        if path.name != "04_bozza_email_cliente.md"
    )
    assert (EMAIL_REQUESTS[language][1] in replacement) == (phase == "demo")


@pytest.mark.parametrize("language", ["it", "en", "fr", "de", "es"])
@pytest.mark.parametrize(
    "phase,growth,net_sales,margin",
    [
        ("demo", "10", "95095", "35035"),
        ("practice", "5", "90772.5", "33442.5"),
    ],
)
def test_sales_plan_kit_runs_current_reviewed_assumptions(
    tmp_path, monkeypatch, language, phase, growth, net_sales, margin
):
    run = _bound_case(
        tmp_path, monkeypatch, "sales-plan", "sales-plan", phase, language=language
    )
    output = Path(run["output_dir"])
    source = next(
        Path(item["path"])
        for item in run["context"]["input_bindings"]
        if Path(item["path"]).suffix == ".csv"
    )
    original = source.read_bytes()
    (output / source.name).write_bytes(original)
    case = _read(ROOT / "plugins/sales-plan/evals/synthetic/case.json")
    case["case_id"] = "ciclo-arco-teaching"
    case["purpose"] = (
        "Execute the fictional sales-plan request; test-only interpretation."
    )
    case["preparation_recipe"]["dimension_columns"] = ["product"]
    case["preparation_recipe"]["period_mapping"] = [
        {"source_period": "2026-01", "target_period": "2027-01"},
        {"source_period": "2026-02", "target_period": "2027-02"},
    ]
    case["files"]["actual_sales"] = {
        "path": source.name,
        "sha256": hashlib.sha256(original).hexdigest(),
    }
    case["reviewed_assumptions"] = {
        "status": "reviewed",
        "reviewed_by": "reviewer.teaching_fixture",
        "reviewed_at": "2026-09-14",
        "review_basis": "Test-only reading of the units-growth request; no learner approval.",
        "assumptions": [
            {
                "assumption_id": "units-growth",
                "driver": "units_pct",
                "change_pct": growth,
                "scope": {"product": ["Urban bicycle", "Trekking bicycle"]},
                "effective_periods": ["2027-01", "2027-02"],
                "priority": 100,
                "rationale": "Requested scenario: unchanged unit prices; discounts and COGS proportional to sales.",
            }
        ],
    }
    request = output / "case.json"
    _write(request, case)
    plan = output / "plan"
    _run(
        "plugins/sales-plan/scripts/run_plan.py",
        "--case",
        request,
        "--client-engagement",
        run["context_path"],
        "--output-dir",
        plan,
    )
    receipt = _read(plan / "plan_execution_receipt.json")
    assert receipt["status"] == "passed"
    assert receipt["report_ready"] is False
    with (plan / "scenario_summary.csv").open(encoding="utf-8", newline="") as stream:
        totals = {
            row["metric"]: row
            for row in csv.DictReader(stream)
            if row["summary_level"] == "total"
        }
    assert totals["net_sales_reporting"]["actual"] == "86450"
    assert totals["net_sales_reporting"]["plan"] == net_sales
    assert totals["gross_margin_reporting"]["plan"] == margin
    assert totals["net_sales_reporting"]["delta_pct_rounded_4dp"] == growth
    with (plan / "assumption_application_ledger.csv").open(
        encoding="utf-8", newline=""
    ) as stream:
        applied = list(csv.DictReader(stream))
    assert len(applied) == 4
    assert {row["assumption_id"] for row in applied} == {"units-growth"}
    assert {row["change_pct"] for row in applied} == {growth}
    assert {row["status"] for row in applied} == {"applied"}
    assert (plan / "model_use_manifest.json").is_file()
    _complete_teaching_case(run, tmp_path / "case")
    assert source.read_bytes() == original
