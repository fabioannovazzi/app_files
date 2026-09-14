"""Execute fictional INPS inputs; fixture review is never a learner approval."""

from __future__ import annotations

from pathlib import Path

import pytest

from tests.plugins.test_teaching_kit_execution import (
    _bound_case,
    _complete_teaching_case,
    _read,
    _run,
    _write,
)

WORDS = {
    "it": [
        "Che cosa documentano le fonti sulla posizione contributiva del periodo?",
        "Inizio del rapporto dichiarato",
        "Fine del rapporto dichiarato",
        "Data della scheda esaminata",
        "Periodi riportati nella scheda fittizia",
        "L’INPS descrive l’estratto come un riepilogo dei contributi registrati a favore del lavoratore.",
        "Funzione dell’estratto contributivo",
        "Nella scheda didattica esaminata aprile non è elencato. La dichiarazione del datore comprende quel mese: occorre chiarire la differenza con documentazione adeguata, senza presumere un mancato versamento.",
        "La scheda didattica aggiornata elenca il periodo completo. La differenza osservata nella prima scheda non permane in questa versione; non sono documentati momento e causa dell’aggiornamento.",
        "Confronto documentale",
        "Acquisire il documento ufficiale completo e la documentazione utile del rapporto, verificando il periodo con il professionista.",
        "Verificare il documento ufficiale completo e chiarire l’origine dell’aggiornamento, senza attribuirgli cause non documentate.",
        "Analisi di fonti fittizie e fonte pubblica consultata; interpretazione da rivedere, non attestazione contributiva.",
    ],
    "en": [
        "What do the sources establish about the contribution record for the period?",
        "Reported employment start",
        "Reported employment end",
        "Date of the examined record",
        "Periods in the fictional record",
        "INPS describes the statement as a summary of contributions recorded for the worker.",
        "Purpose of the contribution statement",
        "April is not listed in the teaching record. The employer statement includes that month; clarify the difference with suitable documents without presuming non-payment.",
        "The updated teaching record lists the complete period. The discrepancy seen in the earlier record does not remain in this version; the timing and reason for the update are undocumented.",
        "Document comparison",
        "Obtain the complete official record and relevant employment documents and review the period with the professional.",
        "Check the complete official record and clarify the origin of the update without assigning undocumented causes.",
        "Fictional case evidence and an inspected public source; interpretation for review, not contribution certification.",
    ],
    "fr": [
        "Que montrent les sources sur la position contributive de la période ?",
        "Début d’emploi déclaré",
        "Fin d’emploi déclarée",
        "Date du relevé examiné",
        "Périodes du relevé fictif",
        "L’INPS décrit le relevé comme un récapitulatif des cotisations enregistrées pour le travailleur.",
        "Fonction du relevé contributif",
        "Avril n’est pas indiqué dans le relevé pédagogique. La déclaration de l’employeur inclut ce mois ; clarifier l’écart avec les documents utiles sans présumer un défaut de paiement.",
        "Le relevé pédagogique actualisé indique toute la période. L’écart observé précédemment ne subsiste pas dans cette version ; date et cause de l’actualisation restent non documentées.",
        "Comparaison documentaire",
        "Obtenir le relevé officiel complet et les documents d’emploi utiles, puis examiner la période avec le professionnel.",
        "Vérifier le relevé officiel complet et clarifier l’origine de l’actualisation sans inventer de cause.",
        "Preuves fictives et source publique consultée ; interprétation à revoir, sans certification contributive.",
    ],
    "de": [
        "Was belegen die Quellen zur Beitragsposition im Zeitraum?",
        "Erklärter Beschäftigungsbeginn",
        "Erklärtes Beschäftigungsende",
        "Datum der geprüften Übersicht",
        "Zeiträume in der fiktiven Übersicht",
        "INPS beschreibt den Auszug als Übersicht der für die beschäftigte Person registrierten Beiträge.",
        "Zweck des Beitragsauszugs",
        "April ist in der Lehrübersicht nicht aufgeführt. Die Arbeitgebererklärung umfasst diesen Monat; die Abweichung ist mit passenden Unterlagen zu klären, ohne Nichtzahlung zu unterstellen.",
        "Die aktualisierte Lehrübersicht führt den gesamten Zeitraum auf. Die frühere Abweichung besteht in dieser Fassung nicht fort; Zeitpunkt und Ursache der Aktualisierung sind nicht belegt.",
        "Dokumentenvergleich",
        "Den vollständigen offiziellen Auszug und relevante Beschäftigungsunterlagen beschaffen und den Zeitraum fachlich prüfen.",
        "Den vollständigen offiziellen Auszug prüfen und die Herkunft der Aktualisierung klären, ohne unbelegte Ursachen zu behaupten.",
        "Fiktive Fallbelege und geprüfte öffentliche Quelle; Interpretation zur Prüfung, keine Beitragsbescheinigung.",
    ],
    "es": [
        "¿Qué acreditan las fuentes sobre la posición contributiva del periodo?",
        "Inicio del empleo declarado",
        "Fin del empleo declarado",
        "Fecha del registro examinado",
        "Periodos del registro ficticio",
        "INPS describe el extracto como un resumen de las cotizaciones registradas a favor del trabajador.",
        "Función del extracto contributivo",
        "Abril no figura en el registro didáctico. La declaración del empleador incluye ese mes; hay que aclarar la diferencia con documentos adecuados sin presumir impago.",
        "El registro didáctico actualizado enumera todo el periodo. La diferencia anterior no persiste en esta versión; no constan el momento ni la causa de la actualización.",
        "Comparación documental",
        "Obtener el registro oficial completo y los documentos laborales pertinentes y revisar el periodo con el profesional.",
        "Verificar el registro oficial completo y aclarar el origen de la actualización sin atribuir causas no documentadas.",
        "Evidencias ficticias y fuente pública consultada; interpretación para revisar, sin certificación contributiva.",
    ],
}

OFFICIAL = "https://www.inps.it/it/it/dettaglio-scheda.it.schede-servizio-strumento.schede-servizi.consultazione-estratto-conto-contributivo-previdenziale-50119.consultazione-estratto-conto-contributivo-previdenziale.html"

SUPPORT = {
    "it": [
        "La sezione Cos’è descrive il contenuto dell’estratto; non prova diritti o versamenti del caso.",
        "Il confronto riguarda esclusivamente le righe acquisite e il periodo dichiarato dal datore.",
    ],
    "en": [
        "The What it is section describes the statement; it does not establish case entitlements or payments.",
        "The comparison covers only the captured rows and the employment period reported by the employer.",
    ],
    "fr": [
        "La rubrique de présentation décrit le relevé ; elle ne prouve aucun droit ni versement dans ce cas.",
        "La comparaison porte uniquement sur les lignes recueillies et la période déclarée par l’employeur.",
    ],
    "de": [
        "Die Beschreibung erläutert den Auszug; sie belegt keine Ansprüche oder Zahlungen in diesem Fall.",
        "Der Vergleich betrifft ausschließlich die erfassten Zeilen und den vom Arbeitgeber erklärten Zeitraum.",
    ],
    "es": [
        "La descripción explica el extracto; no acredita derechos ni pagos de este caso.",
        "La comparación abarca únicamente las filas recogidas y el periodo declarado por el empleador.",
    ],
}


@pytest.mark.parametrize("language", ["it", "en", "fr", "de", "es"])
@pytest.mark.parametrize("phase", ["demo", "practice"])
def test_inps_kit_runs_inventory_evidence_and_professional_draft(
    tmp_path, monkeypatch, language, phase
):
    run = _bound_case(
        tmp_path,
        monkeypatch,
        "previdenza-inps",
        "previdenza-inps",
        phase,
        language=language,
    )
    output = Path(run["output_dir"])
    args = ["--client-engagement", run["context_path"], "--output-dir", output]
    _run(
        "plugins/previdenza-inps/scripts/inventory_case.py",
        Path(run["context"]["run_root"]) / "inputs",
        *args,
        "--language",
        language,
        "--reference-date",
        "2026-09-14",
    )
    inventory = _read(output / "file_inventory.json")
    assert inventory["readable_document_count"] == 4
    assert inventory["ocr"]["network_used"] is False
    documents = {Path(d["relative_path"]).name: d for d in inventory["documents"]}
    fragments = {f["document_id"]: f for f in inventory["evidence_fragments"]}
    employer = documents[f"employment-{language}.md"]["document_id"]
    position = documents[f"contribution-periods-{language}.csv"]["document_id"]
    w = WORDS[language]
    records = {
        "case_id": "marta-contribution-teaching",
        "language": language,
        "professional_question": w[0],
        "material_decisions": {},
        "decision_log": [],
        "facts": [],
        "timeline": [],
        "open_questions": [w[10 if phase == "demo" else 11]],
    }
    for i, gate in enumerate(
        (
            "professional_question_confirmed",
            "framework_confirmed",
            "period_scope_confirmed",
            "ambiguous_terms_resolved",
        )
    ):
        records["material_decisions"][gate] = True
        records["decision_log"].append(
            {
                "decision_id": f"D-{i}",
                "gate": gate,
                "decision": True,
                "decided_by_id": "test-fixture-reviewer",
                "decided_by_role": "professional_reviewer",
                "recorded_at": "2026-09-14T10:00:00+00:00",
                "basis": "Synthetic test-only confirmation of the question and scope explicitly supplied in the kit; not a learner approval.",
            }
        )
    date = "2026-08-01" if phase == "demo" else "2026-09-01"
    for i, (doc, value) in enumerate(
        [
            (employer, "2025-01-01"),
            (employer, "2025-06-30"),
            (position, date),
            (position, None),
        ],
        start=1,
    ):
        fragment = fragments[doc]
        quote = (output / fragment["text_path"]).read_text(encoding="utf-8").strip()
        detail = (
            value
            if value
            else (
                "2025-01-01 – 2025-03-31; 2025-05-01 – 2025-06-30"
                if phase == "demo"
                else "2025-01-01 – 2025-06-30"
            )
        )
        records["facts"].append(
            {
                "fact_id": f"F-{i}",
                "statement": f"{w[i]}: {detail}",
                "review_label": w[i],
                "value": value or quote,
                "value_type": "date" if value else "text",
                "subject_ids": ["marta"],
                "evidence": [
                    {"document_id": doc, "locator": fragment["locator"], "quote": quote}
                ],
                "review_status": "confirmed",
                "conflict_group": None,
            }
        )
        if value:
            records["timeline"].append(
                {
                    "event_id": f"E-{i}",
                    "date": value,
                    "date_precision": "day",
                    "description": w[i],
                    "source_fact_ids": [f"F-{i}"],
                    "review_status": "confirmed",
                    "conflict_group": None,
                }
            )
    request = output / "case_records_draft.json"
    _write(request, records)
    _run(
        "plugins/previdenza-inps/scripts/validate_case_records.py",
        request,
        output / "file_inventory.json",
        *args,
    )
    claims = {
        "language": language,
        "overall_assessment": w[12],
        "claims": [],
        "missing_evidence": records["open_questions"],
    }
    for i, (text, label) in enumerate(
        [(w[5], w[6]), (w[7 if phase == "demo" else 8], w[9])]
    ):
        source = {
            "source_id": f"S-{i}",
            "reference": OFFICIAL if i == 0 else fragments[position]["evidence_id"],
            "temporal_role": "research_cutoff_authority",
            "retrieved_at": "2026-09-14T10:00:00+00:00",
            "version_note": (
                "Public INPS page read on 2026-09-14, last updated 2025-06-04; time is a fixed test timestamp, not a fresh fetch."
                if i == 0
                else "Current supplied fictional record; case evidence, not legal authority."
            ),
            "support_note": SUPPORT[language][i],
            "snapshot_sha256": None,
        }
        claims["claims"].append(
            {
                "claim_id": f"CL-{i}",
                "claim_text": text,
                "review_label": label,
                "claim_type": "rule" if i == 0 else "case_application",
                "verdict": "supported",
                "sources": [source],
                "source_support": source["support_note"],
                "reasoning_review": w[12],
                "evidence_dependencies": [] if i == 0 else ["F-1", "F-2", "F-4"],
                "period_scope": {
                    "status": "confirmed",
                    "start": "2026-09-14" if i == 0 else "2025-01-01",
                    "end": "2026-09-14" if i == 0 else "2025-06-30",
                    "note": "Service description at the review date; employment-period comparison separately bound to supplied facts.",
                },
                "research_cutoff_date": "2026-09-14",
                "professional_review_status": "pending",
            }
        )
    claims_path = output / "claims_review.json"
    _write(claims_path, claims)
    _run(
        "plugins/previdenza-inps/scripts/package_case.py",
        output / "case_records_validated.json",
        claims_path,
        *args,
    )
    final = _read(output / "final_artifacts.json")
    assert final["run_id"] == run["context"]["run_id"]
    assert final["status"] == "ready_for_professional_review"
    assert (output / "studio_memo.docx").is_file()
    memo = (output / "studio_memo.md").read_text(encoding="utf-8")
    assert w[7 if phase == "demo" else 8] in memo
    assert (
        w[10 if phase == "demo" else 11]
        in (output / "document_requests.md").read_text()
    )
    assert (output / "timeline.csv").is_file()
    assert (output / "evidence_matrix.csv").is_file()
    assert not (output / "calculation_results.json").exists()
    assert all(c["professional_review_status"] == "pending" for c in claims["claims"])
    _complete_teaching_case(run, tmp_path / "case")
