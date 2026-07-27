from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import sys
import tempfile
from datetime import date
from pathlib import Path
from typing import Any, Mapping, Sequence

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from new_client_core import (  # noqa: E402
    EXPECTED_ARTIFACTS,
    ITALY_COUNTRY_PACK,
    SCHEMA_VERSION,
    ValidationError,
    build_applicability_plan,
    build_case_facts,
    build_document_plan,
    build_export_domain_blockers,
    build_missing_evidence,
    build_monitoring_plan,
    build_review_payload,
    build_temporal_validity,
    calculate_aml,
    canonical_json_hash,
    ensure_private_output_directory,
    load_json,
    load_source_registry,
    sha256_file,
    utc_now,
    validate_contract,
    validate_new_client_input,
    validate_source_references,
    verify_client_file_preparation_binding,
    verify_evidence_register,
    verify_template_references,
    write_private_json,
    write_private_text,
)

__all__ = ["build_parser", "main", "package_new_client"]

PLUGIN_ROOT = SCRIPT_DIR.parent
DEFAULT_SOURCE_REGISTRY = PLUGIN_ROOT / "references" / "source-registry.json"

_LOCALE_TEXT = {
    "it": {
        "memo_title": "Memo studio — nuovo cliente",
        "run_id": "ID esecuzione",
        "client_reference": "Riferimento cliente",
        "engagement": "Incarico",
        "package_status": "Stato del fascicolo",
        "jurisdiction": "Giurisdizione professionale",
        "country_pack": "Configurazione nazionale",
        "aml_heading": "Calcolo antiriciclaggio",
        "calculated_band": "Fascia calcolata",
        "table_1_status": "Stato della Tabella 1",
        "baseline_treatment": "Trattamento di base",
        "formula": "Formula",
        "evidence_heading": "Evidenze e decisioni",
        "open_items": "Informazioni aperte",
        "aml_status": "Stato del flusso AML",
        "monitoring_status": "Stato del monitoraggio",
        "documents": "Documenti",
        "review_boundary": "Perimetro della revisione",
        "missing_title": "Bozza — richiesta informazioni nuovo cliente",
        "draft_notice": "Bozza dello studio. Verificare e personalizzare prima dell'invio.",
        "provide": "Fornire o chiarire quanto segue:",
        "none_missing": "Non sono state rilevate mancanze meccaniche. Il professionista deve comunque verificare completezza e pertinenza.",
        "secure_channel": "Non inviare documenti di identità tramite canali non approvati. Utilizzare il metodo di raccolta sicuro indicato dallo studio.",
        "handoff_title": "Passaggio alla revisione — nuovo cliente",
        "review_sequence": "Sequenza di revisione",
        "review_payload": "Dati da revisionare",
        "pending_decisions": "Decisioni da registrare",
        "applied_decisions": "Decisioni applicate",
        "applied_decisions_note": "creato dal servizio di revisione",
        "final_manifest": "Manifesto finale degli artefatti",
        "review_tools": "Strumenti di revisione",
        "table1_note": "L’applicabilità della Tabella 1 è una decisione esplicita del professionista con base registrata; una valutazione irrisolta blocca l’esito.",
        "arithmetic_note": "È un supporto aritmetico. Punteggi, esclusioni, indicatori e trattamento finale richiedono revisione professionale.",
        "boundary_note": "Nessun mandato, informativa privacy o AI, clausola ex art. 28 o modulo AML è stato prodotto o dichiarato definitivo. Il fascicolo registra soltanto applicabilità e riferimenti a modelli verificati per il piano documentale professionale.",
        "handoff_steps": [
            "Validare `review_payload.json` con lo strumento di revisione del plugin.",
            "Rivedere applicabilità, input e indicatori AML, evidenze mancanti, documenti e piano di monitoraggio.",
            "Salvare le decisioni esplicite in `ui_decisions.json`.",
            "Applicare le decisioni tramite il servizio di revisione persistente.",
        ],
        "handoff_boundary": "Il fascicolo statico è una bozza: non attiva il cliente, non firma documenti e non assume una decisione professionale di conformità.",
    },
    "en": {
        "memo_title": "Studio new-client memo",
        "run_id": "Run ID",
        "client_reference": "Client reference",
        "engagement": "Engagement",
        "package_status": "Package status",
        "jurisdiction": "Professional jurisdiction",
        "country_pack": "Country pack",
        "aml_heading": "AML calculation",
        "calculated_band": "Calculated band",
        "table_1_status": "Table 1 status",
        "baseline_treatment": "Baseline treatment",
        "formula": "Formula",
        "evidence_heading": "Evidence and decisions",
        "open_items": "Open information items",
        "aml_status": "AML workflow status",
        "monitoring_status": "Monitoring status",
        "documents": "Documents",
        "review_boundary": "Review boundary",
        "missing_title": "Draft — request for missing new-client information",
        "draft_notice": "This is a studio draft. Review and personalize it before sending.",
        "provide": "Please provide or clarify the following:",
        "none_missing": "No mechanically missing items were detected. A professional must still review completeness and relevance.",
        "secure_channel": "Do not send identity documents through an unapproved channel. Use the studio's designated secure collection method.",
        "handoff_title": "New Client Review Handoff",
        "review_sequence": "Review sequence",
        "review_payload": "Review payload",
        "pending_decisions": "Pending decisions",
        "applied_decisions": "Applied decisions",
        "applied_decisions_note": "created by the review service",
        "final_manifest": "Final artifact manifest",
        "review_tools": "Review tools",
        "table1_note": "Table 1 applicability is an explicit professional decision with a recorded basis; an unresolved assessment blocks the treatment outcome.",
        "arithmetic_note": "This is arithmetic support. Factor scores, exclusions, trigger findings and final treatment require professional review.",
        "boundary_note": "No mandate, privacy or AI notice, Article 28 terms or AML form has been rendered or declared final. The package records only applicability and verified template references for the professional document plan.",
        "handoff_steps": [
            "Validate `review_payload.json` with the plugin review tool.",
            "Review applicability, AML inputs and triggers, missing evidence, documents and the monitoring schedule.",
            "Save explicit decisions to `ui_decisions.json`.",
            "Apply decisions through the persistent review service.",
        ],
        "handoff_boundary": "The static package is a draft. It does not activate a client, sign a document or make a professional compliance determination.",
    },
    "fr": {
        "memo_title": "Note du cabinet — nouveau client",
        "run_id": "ID d’exécution",
        "client_reference": "Référence client",
        "engagement": "Mission",
        "package_status": "État du dossier",
        "jurisdiction": "Juridiction professionnelle",
        "country_pack": "Configuration nationale",
        "aml_heading": "Calcul LCB-FT",
        "calculated_band": "Niveau calculé",
        "table_1_status": "État du tableau 1",
        "baseline_treatment": "Mesure de vigilance de référence",
        "formula": "Formule",
        "evidence_heading": "Justificatifs et décisions",
        "open_items": "Informations en attente",
        "aml_status": "État du processus LCB-FT",
        "monitoring_status": "État du suivi",
        "documents": "Documents",
        "review_boundary": "Périmètre de la revue",
        "missing_title": "Brouillon — demande d’informations pour un nouveau client",
        "draft_notice": "Brouillon du cabinet. À vérifier et personnaliser avant envoi.",
        "provide": "Veuillez fournir ou préciser les éléments suivants :",
        "none_missing": "Aucun élément manquant n’a été détecté mécaniquement. Le professionnel doit néanmoins vérifier l’exhaustivité et la pertinence.",
        "secure_channel": "N’envoyez pas de pièce d’identité par un canal non approuvé. Utilisez le moyen de collecte sécurisé indiqué par le cabinet.",
        "handoff_title": "Transmission pour revue — nouveau client",
        "review_sequence": "Séquence de revue",
        "review_payload": "Données à examiner",
        "pending_decisions": "Décisions à enregistrer",
        "applied_decisions": "Décisions appliquées",
        "applied_decisions_note": "créé par le service de revue",
        "final_manifest": "Manifeste final des artefacts",
        "review_tools": "Outils de revue",
        "table1_note": "L’applicabilité du tableau 1 relève d’une décision explicite du professionnel, fondée et enregistrée ; une évaluation non résolue bloque le résultat.",
        "arithmetic_note": "Il s’agit d’une aide au calcul. Les scores, exclusions, indicateurs et le traitement final exigent une revue professionnelle.",
        "boundary_note": "Aucun mandat, avis de confidentialité ou d’IA, clause de l’article 28 ou formulaire LCB-FT n’a été produit ni déclaré définitif. Le dossier ne consigne que l’applicabilité et les références vérifiées aux modèles du plan documentaire professionnel.",
        "handoff_steps": [
            "Valider `review_payload.json` avec l’outil de revue du plugin.",
            "Examiner l’applicabilité, les données et indicateurs LCB-FT, les justificatifs manquants, les documents et le calendrier de suivi.",
            "Enregistrer les décisions explicites dans `ui_decisions.json`.",
            "Appliquer les décisions avec le service de revue persistante.",
        ],
        "handoff_boundary": "Le dossier statique est un brouillon. Il n’active pas le client, ne signe aucun document et ne prend aucune décision professionnelle de conformité.",
    },
    "de": {
        "memo_title": "Kanzleivermerk — neuer Mandant",
        "run_id": "Lauf-ID",
        "client_reference": "Mandantenreferenz",
        "engagement": "Auftrag",
        "package_status": "Aktenstatus",
        "jurisdiction": "Berufsrechtliche Zuständigkeit",
        "country_pack": "Länderkonfiguration",
        "aml_heading": "Geldwäsche-Risikoberechnung",
        "calculated_band": "Berechnete Risikostufe",
        "table_1_status": "Status der Tabelle 1",
        "baseline_treatment": "Grundlegende Sorgfaltsmaßnahme",
        "formula": "Formel",
        "evidence_heading": "Nachweise und Entscheidungen",
        "open_items": "Offene Angaben",
        "aml_status": "Status des AML-Ablaufs",
        "monitoring_status": "Überwachungsstatus",
        "documents": "Dokumente",
        "review_boundary": "Prüfungsumfang",
        "missing_title": "Entwurf — Anforderung fehlender Angaben zum neuen Mandanten",
        "draft_notice": "Kanzleientwurf. Vor dem Versand prüfen und anpassen.",
        "provide": "Bitte folgende Angaben oder Unterlagen bereitstellen bzw. klären:",
        "none_missing": "Es wurden keine mechanisch fehlenden Punkte festgestellt. Vollständigkeit und Relevanz sind dennoch fachlich zu prüfen.",
        "secure_channel": "Identitätsdokumente nicht über einen nicht freigegebenen Kanal senden. Den von der Kanzlei bestimmten sicheren Übermittlungsweg verwenden.",
        "handoff_title": "Übergabe zur Prüfung — neuer Mandant",
        "review_sequence": "Prüfungsablauf",
        "review_payload": "Prüfdaten",
        "pending_decisions": "Zu erfassende Entscheidungen",
        "applied_decisions": "Angewandte Entscheidungen",
        "applied_decisions_note": "vom Prüfservice erstellt",
        "final_manifest": "Abschließendes Artefaktverzeichnis",
        "review_tools": "Prüfwerkzeuge",
        "table1_note": "Die Anwendbarkeit von Tabelle 1 ist eine ausdrückliche, begründete Entscheidung des Berufsträgers; eine offene Beurteilung blockiert das Ergebnis.",
        "arithmetic_note": "Dies ist eine Rechenhilfe. Bewertungen, Ausschlüsse, Auslöser und die endgültige Behandlung erfordern eine fachliche Prüfung.",
        "boundary_note": "Weder Mandat noch Datenschutz- oder KI-Hinweis, Vereinbarung nach Artikel 28 oder AML-Formular wurden erstellt oder als endgültig erklärt. Die Akte enthält nur Anwendbarkeit und geprüfte Vorlagenverweise für den fachlichen Dokumentenplan.",
        "handoff_steps": [
            "`review_payload.json` mit dem Prüfwerkzeug des Plugins validieren.",
            "Anwendbarkeit, AML-Eingaben und -Auslöser, fehlende Nachweise, Dokumente und Überwachungsplan prüfen.",
            "Ausdrückliche Entscheidungen in `ui_decisions.json` speichern.",
            "Entscheidungen über den persistenten Prüfservice anwenden.",
        ],
        "handoff_boundary": "Die statische Akte ist ein Entwurf. Sie aktiviert keinen Mandanten, unterzeichnet kein Dokument und trifft keine fachliche Compliance-Entscheidung.",
    },
    "es": {
        "memo_title": "Memoria del despacho — nuevo cliente",
        "run_id": "ID de ejecución",
        "client_reference": "Referencia del cliente",
        "engagement": "Encargo",
        "package_status": "Estado del expediente",
        "jurisdiction": "Jurisdicción profesional",
        "country_pack": "Configuración nacional",
        "aml_heading": "Cálculo de prevención del blanqueo",
        "calculated_band": "Nivel calculado",
        "table_1_status": "Estado de la tabla 1",
        "baseline_treatment": "Medida de diligencia de referencia",
        "formula": "Fórmula",
        "evidence_heading": "Evidencias y decisiones",
        "open_items": "Información pendiente",
        "aml_status": "Estado del proceso de prevención del blanqueo",
        "monitoring_status": "Estado del seguimiento",
        "documents": "Documentos",
        "review_boundary": "Alcance de la revisión",
        "missing_title": "Borrador — solicitud de información pendiente del nuevo cliente",
        "draft_notice": "Borrador del despacho. Revíselo y personalícelo antes de enviarlo.",
        "provide": "Proporcione o aclare lo siguiente:",
        "none_missing": "No se detectaron elementos mecánicamente pendientes. El profesional debe comprobar igualmente la integridad y la pertinencia.",
        "secure_channel": "No envíe documentos de identidad por un canal no autorizado. Utilice el método de recogida segura indicado por el despacho.",
        "handoff_title": "Entrega para revisión — nuevo cliente",
        "review_sequence": "Secuencia de revisión",
        "review_payload": "Datos de revisión",
        "pending_decisions": "Decisiones pendientes",
        "applied_decisions": "Decisiones aplicadas",
        "applied_decisions_note": "creado por el servicio de revisión",
        "final_manifest": "Manifiesto final de artefactos",
        "review_tools": "Herramientas de revisión",
        "table1_note": "La aplicabilidad de la tabla 1 es una decisión profesional expresa con una base registrada; una evaluación sin resolver bloquea el resultado.",
        "arithmetic_note": "Es un apoyo aritmético. Las puntuaciones, exclusiones, indicadores y el tratamiento final requieren revisión profesional.",
        "boundary_note": "No se ha generado ni declarado definitivo ningún mandato, aviso de privacidad o de IA, cláusula del artículo 28 ni formulario de prevención del blanqueo. El expediente solo registra la aplicabilidad y las referencias verificadas a plantillas para el plan documental profesional.",
        "handoff_steps": [
            "Validar `review_payload.json` con la herramienta de revisión del plugin.",
            "Revisar la aplicabilidad, los datos e indicadores de prevención del blanqueo, las evidencias pendientes, los documentos y el calendario de seguimiento.",
            "Guardar las decisiones explícitas en `ui_decisions.json`.",
            "Aplicar las decisiones mediante el servicio de revisión persistente.",
        ],
        "handoff_boundary": "El expediente estático es un borrador. No activa al cliente, no firma documentos ni adopta una decisión profesional de cumplimiento.",
    },
}

_FINAL_MANIFEST_COPY = {
    "en": {
        "explicit_non_outcomes": [
            "No client lifecycle activation",
            "No signature or execution of documents",
            "No professional compliance conclusion",
        ],
        "caveats": [
            "All semantic applicability and AML findings require professional review.",
            (
                "The document plan records verified template references; it does not "
                "render, merge, populate, sign, or send document content."
            ),
        ],
        "next_actions": [
            "Resolve missing or unclear information.",
            "Review every review_payload.json item.",
            "Save and apply explicit professional decisions through the review service.",
        ],
    },
    "es": {
        "explicit_non_outcomes": [
            "No se activa el ciclo de vida del cliente",
            "No se firma ni formaliza ningún documento",
            "No se emite una conclusión profesional de cumplimiento",
        ],
        "caveats": [
            "Todas las conclusiones semánticas sobre aplicabilidad y prevención del blanqueo requieren revisión profesional.",
            (
                "El plan documental registra referencias verificadas a plantillas; "
                "no genera, combina, rellena, firma ni envía el contenido de los documentos."
            ),
        ],
        "next_actions": [
            "Resuelva la información pendiente o poco clara.",
            "Revise cada elemento de review_payload.json.",
            "Guarde y aplique las decisiones profesionales expresas mediante el servicio de revisión.",
        ],
    },
}

_DISPLAY_COPY: dict[str, dict[str | None, dict[str, str]]] = {
    "engagement_kind": {
        "ongoing": {
            "it": "continuativo",
            "en": "ongoing",
            "fr": "continue",
            "de": "laufend",
        },
        "one_off": {
            "it": "occasionale",
            "en": "one-off",
            "fr": "ponctuelle",
            "de": "einmalig",
        },
    },
    "package_status": {
        "draft_for_professional_review": {
            "it": "bozza per revisione professionale",
            "en": "draft for professional review",
            "fr": "brouillon soumis à une revue professionnelle",
            "de": "Entwurf zur fachlichen Prüfung",
        },
    },
    "jurisdiction": {
        "IT": {"it": "Italia", "en": "Italy", "fr": "Italie", "de": "Italien"},
    },
    "country_pack": {
        ITALY_COUNTRY_PACK: {
            "it": "Italia — configurazione professionale 2026",
            "en": "Italy — 2026 professional setup",
            "fr": "Italie — configuration professionnelle 2026",
            "de": "Italien — Berufsmodul 2026",
        },
    },
    "risk_band": {
        "not_significant": {
            "it": "non significativo",
            "en": "not significant",
            "fr": "non significatif",
            "de": "nicht signifikant",
        },
        "low_significance": {
            "it": "poco significativo",
            "en": "low significance",
            "fr": "peu significatif",
            "de": "gering signifikant",
        },
        "medium_significance": {
            "it": "abbastanza significativo",
            "en": "medium significance",
            "fr": "assez significatif",
            "de": "mittel signifikant",
        },
        "high_significance": {
            "it": "molto significativo",
            "en": "high significance",
            "fr": "très significatif",
            "de": "hoch signifikant",
        },
    },
    "table_1_status": {
        "yes": {
            "it": "applicabile",
            "en": "applicable",
            "fr": "applicable",
            "de": "anwendbar",
        },
        "no": {
            "it": "non applicabile",
            "en": "not applicable",
            "fr": "non applicable",
            "de": "nicht anwendbar",
        },
        "unknown": {
            "it": "da determinare",
            "en": "not yet determined",
            "fr": "à déterminer",
            "de": "noch zu bestimmen",
        },
    },
    "review_status": {
        "confirmed": {
            "it": "confermato dal professionista",
            "en": "professionally confirmed",
            "fr": "confirmé par le professionnel",
            "de": "fachlich bestätigt",
        },
        "proposed": {
            "it": "proposto, da revisionare",
            "en": "proposed, pending review",
            "fr": "proposé, en attente de revue",
            "de": "vorgeschlagen, Prüfung ausstehend",
        },
    },
    "verification_mode": {
        None: {
            "it": "da determinare",
            "en": "not yet determined",
            "fr": "à déterminer",
            "de": "noch zu bestimmen",
        },
        "conduct_rule": {
            "it": "regola di condotta applicabile",
            "en": "applicable conduct rule",
            "fr": "règle de conduite applicable",
            "de": "anwendbare Verhaltensregel",
        },
        "simplified": {
            "it": "verifica semplificata",
            "en": "simplified verification",
            "fr": "vigilance simplifiée",
            "de": "vereinfachte Prüfung",
        },
        "ordinary": {
            "it": "verifica ordinaria",
            "en": "ordinary verification",
            "fr": "vigilance normale",
            "de": "reguläre Prüfung",
        },
        "enhanced": {
            "it": "verifica rafforzata",
            "en": "enhanced verification",
            "fr": "vigilance renforcée",
            "de": "verstärkte Prüfung",
        },
    },
    "aml_status": {
        "blocked_unresolved_table_1": {
            "it": "bloccato: valutazione della Tabella 1 irrisolta",
            "en": "blocked: Table 1 assessment unresolved",
            "fr": "bloqué : évaluation du tableau 1 non résolue",
            "de": "blockiert: Beurteilung der Tabelle 1 offen",
        },
        "blocked_unknown_mandatory_trigger": {
            "it": "bloccato: indicatore obbligatorio da chiarire",
            "en": "blocked: mandatory trigger unresolved",
            "fr": "bloqué : facteur obligatoire non résolu",
            "de": "blockiert: verpflichtender Auslöser offen",
        },
        "blocked_unconfirmed_positive_trigger": {
            "it": "bloccato: indicatore positivo da confermare",
            "en": "blocked: positive trigger awaiting confirmation",
            "fr": "bloqué : facteur positif en attente de confirmation",
            "de": "blockiert: positiver Auslöser noch zu bestätigen",
        },
        "calculated_for_professional_review": {
            "it": "calcolato per la revisione professionale",
            "en": "calculated for professional review",
            "fr": "calculé pour revue professionnelle",
            "de": "für die fachliche Prüfung berechnet",
        },
    },
    "monitoring_status": {
        "not_scheduled_one_off": {
            "it": "non pianificato per incarico occasionale",
            "en": "not scheduled for a one-off engagement",
            "fr": "non planifié pour une mission ponctuelle",
            "de": "bei einmaligem Auftrag nicht geplant",
        },
        "blocked_table_1_assessment": {
            "it": "bloccato in attesa della valutazione della Tabella 1",
            "en": "blocked pending the Table 1 assessment",
            "fr": "bloqué dans l’attente de l’évaluation du tableau 1",
            "de": "bis zur Beurteilung der Tabelle 1 blockiert",
        },
        "not_scheduled_conduct_rule": {
            "it": "cadenza da definire secondo la regola di condotta",
            "en": "cadence to be set under the conduct rule",
            "fr": "périodicité à définir selon la règle de conduite",
            "de": "Turnus nach der Verhaltensregel festzulegen",
        },
        "draft_schedule_for_professional_review": {
            "it": "bozza di calendario per revisione professionale",
            "en": "draft schedule for professional review",
            "fr": "projet de calendrier soumis à revue professionnelle",
            "de": "Terminplanentwurf zur fachlichen Prüfung",
        },
        "blocked_enhanced_interval_selection": {
            "it": "bloccato: scegliere una cadenza rafforzata",
            "en": "blocked: enhanced-review interval required",
            "fr": "bloqué : périodicité renforcée à choisir",
            "de": "blockiert: Intervall für verstärkte Prüfung erforderlich",
        },
    },
    "document_type": {
        "mandate": {
            "it": "incarico professionale",
            "en": "professional engagement",
            "fr": "lettre de mission",
            "de": "Berufsauftrag",
        },
        "privacy_notice": {
            "it": "informativa privacy",
            "en": "privacy notice",
            "fr": "information sur la protection des données",
            "de": "Datenschutzhinweis",
        },
        "ai_transparency_notice": {
            "it": "informativa sull’uso dell’IA",
            "en": "AI transparency notice",
            "fr": "information sur l’utilisation de l’IA",
            "de": "Hinweis zum KI-Einsatz",
        },
        "article_28_terms": {
            "it": "nomina ai sensi dell’articolo 28",
            "en": "Article 28 terms",
            "fr": "clauses de l’article 28",
            "de": "Vereinbarung nach Artikel 28",
        },
        "aml_assessment": {
            "it": "valutazione antiriciclaggio",
            "en": "AML assessment",
            "fr": "évaluation LCB-FT",
            "de": "AML-Risikobewertung",
        },
    },
    "document_status": {
        "template_reference_required": {
            "it": "riferimento a un modello necessario",
            "en": "template reference required",
            "fr": "référence à un modèle requise",
            "de": "Vorlagenreferenz erforderlich",
        },
        "template_reference_verification_required": {
            "it": "verifica del modello necessaria",
            "en": "template verification required",
            "fr": "vérification du modèle requise",
            "de": "Vorlagenprüfung erforderlich",
        },
        "approved_reusable_reference_available": {
            "it": "riferimento approvato e riutilizzabile disponibile",
            "en": "approved reusable reference available",
            "fr": "référence approuvée et réutilisable disponible",
            "de": "freigegebene wiederverwendbare Referenz vorhanden",
        },
        "template_reference_not_ready": {
            "it": "riferimento al modello non pronto",
            "en": "template reference not ready",
            "fr": "référence au modèle non prête",
            "de": "Vorlagenreferenz noch nicht bereit",
        },
        "not_planned_by_confirmed_applicability": {
            "it": "non previsto in base all’applicabilità confermata",
            "en": "not planned under confirmed applicability",
            "fr": "non prévu selon l’applicabilité confirmée",
            "de": "aufgrund bestätigter Anwendbarkeit nicht vorgesehen",
        },
        "applicability_review_required": {
            "it": "revisione dell’applicabilità necessaria",
            "en": "applicability review required",
            "fr": "revue de l’applicabilité requise",
            "de": "Prüfung der Anwendbarkeit erforderlich",
        },
    },
    "missing_item_type": {
        "evidence_record": {
            "it": "documento o evidenza",
            "en": "document or evidence",
            "fr": "document ou justificatif",
            "de": "Dokument oder Nachweis",
        },
        "tax_fact": {
            "it": "dato fiscale",
            "en": "tax detail",
            "fr": "donnée fiscale",
            "de": "Steuerangabe",
        },
        "party_fact": {
            "it": "dato anagrafico o professionale",
            "en": "client profile detail",
            "fr": "donnée sur le profil du client",
            "de": "Mandantenangabe",
        },
        "identity_document": {
            "it": "documento di identità del cliente",
            "en": "client identity document",
            "fr": "pièce d’identité du client",
            "de": "Identitätsdokument des Mandanten",
        },
        "representative": {
            "it": "rappresentante o esecutore",
            "en": "representative or executor",
            "fr": "représentant ou exécutant",
            "de": "Vertreter oder ausführende Person",
        },
        "beneficial_owner": {
            "it": "titolare effettivo",
            "en": "beneficial owner",
            "fr": "bénéficiaire effectif",
            "de": "wirtschaftlich berechtigte Person",
        },
        "representative_posture": {
            "it": "rappresentanza ed esecutore",
            "en": "representation and executor posture",
            "fr": "représentation et exécutant",
            "de": "Vertretung und ausführende Person",
        },
        "ownership_status": {
            "it": "titolarità effettiva",
            "en": "beneficial-ownership posture",
            "fr": "situation des bénéficiaires effectifs",
            "de": "wirtschaftliche Berechtigung",
        },
        "screening_result": {
            "it": "verifica PEP, sanzioni o Paesi",
            "en": "PEP, sanctions or country screening",
            "fr": "vérification PPE, sanctions ou pays",
            "de": "PEP-, Sanktions- oder Länderprüfung",
        },
        "privacy_processing": {
            "it": "decisione privacy",
            "en": "privacy decision",
            "fr": "décision relative à la protection des données",
            "de": "Datenschutzentscheidung",
        },
        "applicability": {
            "it": "applicabilità documentale",
            "en": "document applicability",
            "fr": "applicabilité documentaire",
            "de": "Dokumentenanwendbarkeit",
        },
        "aml_assessment": {
            "it": "valutazione antiriciclaggio",
            "en": "AML assessment",
            "fr": "évaluation LCB-FT",
            "de": "AML-Risikobewertung",
        },
        "aml_trigger": {
            "it": "indicatore antiriciclaggio",
            "en": "AML trigger",
            "fr": "facteur LCB-FT",
            "de": "AML-Auslöser",
        },
        "engagement_terms": {
            "it": "condizioni dell’incarico",
            "en": "engagement terms",
            "fr": "conditions de la mission",
            "de": "Auftragsbedingungen",
        },
        "client_file_preparation_binding": {
            "it": "fascicolo documentale preparatorio",
            "en": "prepared client-file package",
            "fr": "dossier client préparatoire",
            "de": "vorbereitende Mandantenakte",
        },
    },
    "missing_reason": {
        "supporting_evidence_not_verified": {
            "it": "le evidenze di supporto non risultano verificate",
            "en": "the supporting evidence has not been verified",
            "fr": "les justificatifs à l’appui n’ont pas été vérifiés",
            "de": "die zugehörigen Nachweise sind nicht geprüft",
        },
        "evidence_status_requested": {
            "it": "è stato richiesto ma non risulta ancora ricevuto",
            "en": "it has been requested but has not yet been received",
            "fr": "il a été demandé mais n’a pas encore été reçu",
            "de": "es wurde angefordert, ist aber noch nicht eingegangen",
        },
        "evidence_status_missing": {
            "it": "non risulta disponibile",
            "en": "it is not currently available",
            "fr": "il n’est pas disponible",
            "de": "es liegt derzeit nicht vor",
        },
        "evidence_status_stale": {
            "it": "deve essere aggiornato",
            "en": "it needs to be updated",
            "fr": "il doit être actualisé",
            "de": "es muss aktualisiert werden",
        },
        "evidence_expired": {
            "it": "la validità risulta scaduta",
            "en": "its recorded validity has expired",
            "fr": "sa validité enregistrée a expiré",
            "de": "die erfasste Gültigkeit ist abgelaufen",
        },
        "verification_status_unknown": {
            "it": "il dato deve essere fornito e verificato",
            "en": "the detail must be provided and verified",
            "fr": "la donnée doit être fournie et vérifiée",
            "de": "die Angabe muss vorgelegt und geprüft werden",
        },
        "verification_status_reported": {
            "it": "il dato dichiarato deve essere verificato",
            "en": "the reported detail must be verified",
            "fr": "la donnée déclarée doit être vérifiée",
            "de": "die mitgeteilte Angabe muss geprüft werden",
        },
        "identity_verification_status_unknown": {
            "it": "la verifica dell’identità deve essere completata",
            "en": "identity verification must be completed",
            "fr": "la vérification d’identité doit être achevée",
            "de": "die Identitätsprüfung muss abgeschlossen werden",
        },
        "identity_verification_status_reported": {
            "it": "la verifica dell’identità dichiarata deve essere confermata",
            "en": "the reported identity verification must be confirmed",
            "fr": "la vérification d’identité déclarée doit être confirmée",
            "de": "die mitgeteilte Identitätsprüfung muss bestätigt werden",
        },
        "identity_verification_status_not_applicable": {
            "it": "occorre confermare perché il documento di identità non è applicabile",
            "en": "the reason an identity document is not applicable must be confirmed",
            "fr": "le motif de non-applicabilité de la pièce d’identité doit être confirmé",
            "de": "der Grund für die Nichtanwendbarkeit eines Identitätsdokuments ist zu bestätigen",
        },
        "identity_document_expired": {
            "it": "il documento di identità risulta scaduto",
            "en": "the identity document has expired",
            "fr": "la pièce d’identité a expiré",
            "de": "das Identitätsdokument ist abgelaufen",
        },
        "representative_or_executor_posture_pending": {
            "it": "rappresentanti ed esecutore devono essere definiti",
            "en": "the representatives and executor must be resolved",
            "fr": "les représentants et l’exécutant doivent être définis",
            "de": "Vertreter und ausführende Person müssen geklärt werden",
        },
        "beneficial_ownership_posture_pending": {
            "it": "la titolarità effettiva deve essere definita",
            "en": "the beneficial-ownership posture must be resolved",
            "fr": "la situation des bénéficiaires effectifs doit être définie",
            "de": "die wirtschaftliche Berechtigung muss geklärt werden",
        },
        "professional_resolution_pending": {
            "it": "è necessaria una risoluzione professionale documentata",
            "en": "a documented professional resolution is required",
            "fr": "une résolution professionnelle documentée est requise",
            "de": "eine dokumentierte fachliche Klärung ist erforderlich",
        },
        "professional_confirmation_pending": {
            "it": "è necessaria la conferma del professionista",
            "en": "professional confirmation is required",
            "fr": "la confirmation du professionnel est requise",
            "de": "eine fachliche Bestätigung ist erforderlich",
        },
        "professional_resolution_do_not_proceed": {
            "it": "la decisione professionale registrata indica di non procedere",
            "en": "the recorded professional decision is not to proceed",
            "fr": "la décision professionnelle enregistrée indique de ne pas poursuivre",
            "de": "die erfasste fachliche Entscheidung lautet, nicht fortzufahren",
        },
        "privacy_processing_decision_pending": {
            "it": "la decisione sul trattamento dei dati deve essere completata",
            "en": "the privacy-processing decision must be completed",
            "fr": "la décision relative au traitement des données doit être finalisée",
            "de": "die Entscheidung zur Datenverarbeitung muss abgeschlossen werden",
        },
        "applicability_unclear": {
            "it": "l’applicabilità deve essere chiarita",
            "en": "applicability must be clarified",
            "fr": "l’applicabilité doit être clarifiée",
            "de": "die Anwendbarkeit muss geklärt werden",
        },
        "table_1_status_unknown": {
            "it": "l’applicabilità della Tabella 1 deve essere definita",
            "en": "Table 1 applicability must be resolved",
            "fr": "l’applicabilité du tableau 1 doit être déterminée",
            "de": "die Anwendbarkeit der Tabelle 1 muss geklärt werden",
        },
        "mandatory_trigger_status_unknown": {
            "it": "lo stato dell’indicatore obbligatorio deve essere definito",
            "en": "the mandatory trigger status must be resolved",
            "fr": "l’état du facteur obligatoire doit être déterminé",
            "de": "der Status des verpflichtenden Auslösers muss geklärt werden",
        },
        "positive_trigger_requires_confirmation": {
            "it": "l’indicatore positivo deve essere confermato dal professionista",
            "en": "the positive trigger requires professional confirmation",
            "fr": "le facteur positif doit être confirmé par le professionnel",
            "de": "der positive Auslöser muss fachlich bestätigt werden",
        },
        "engagement_terms_incomplete": {
            "it": "le condizioni dell’incarico devono essere completate",
            "en": "the engagement terms must be completed",
            "fr": "les conditions de la mission doivent être complétées",
            "de": "die Auftragsbedingungen müssen vervollständigt werden",
        },
        "bound_client_file_preparation_run_not_final_ready": {
            "it": "il fascicolo preparatorio collegato non è pronto per l’uso professionale",
            "en": "the linked prepared client-file package is not final-ready",
            "fr": "le dossier client préparatoire lié n’est pas prêt pour l’usage professionnel",
            "de": "die verknüpfte vorbereitende Mandantenakte ist noch nicht freigegeben",
        },
    },
}

_SPANISH_DISPLAY_COPY: dict[str, dict[str | None, str]] = {
    "engagement_kind": {
        "ongoing": "continuo",
        "one_off": "ocasional",
    },
    "package_status": {
        "draft_for_professional_review": "borrador para revisión profesional",
    },
    "jurisdiction": {"IT": "Italia"},
    "country_pack": {
        ITALY_COUNTRY_PACK: "Italia — configuración profesional 2026",
    },
    "risk_band": {
        "not_significant": "no significativo",
        "low_significance": "poco significativo",
        "medium_significance": "bastante significativo",
        "high_significance": "muy significativo",
    },
    "table_1_status": {
        "yes": "aplicable",
        "no": "no aplicable",
        "unknown": "por determinar",
    },
    "review_status": {
        "confirmed": "confirmado por el profesional",
        "proposed": "propuesto, pendiente de revisión",
    },
    "verification_mode": {
        None: "por determinar",
        "conduct_rule": "regla de conducta aplicable",
        "simplified": "verificación simplificada",
        "ordinary": "verificación ordinaria",
        "enhanced": "verificación reforzada",
    },
    "aml_status": {
        "blocked_unresolved_table_1": "bloqueado: evaluación de la tabla 1 sin resolver",
        "blocked_unknown_mandatory_trigger": "bloqueado: indicador obligatorio sin resolver",
        "blocked_unconfirmed_positive_trigger": "bloqueado: indicador positivo pendiente de confirmación",
        "calculated_for_professional_review": "calculado para revisión profesional",
    },
    "monitoring_status": {
        "not_scheduled_one_off": "no programado para un encargo ocasional",
        "blocked_table_1_assessment": "bloqueado a la espera de la evaluación de la tabla 1",
        "not_scheduled_conduct_rule": "periodicidad por definir conforme a la regla de conducta",
        "draft_schedule_for_professional_review": "borrador de calendario para revisión profesional",
        "blocked_enhanced_interval_selection": "bloqueado: se requiere una periodicidad reforzada",
    },
    "document_type": {
        "mandate": "encargo profesional",
        "privacy_notice": "aviso de privacidad",
        "ai_transparency_notice": "aviso sobre el uso de IA",
        "article_28_terms": "cláusulas del artículo 28",
        "aml_assessment": "evaluación de prevención del blanqueo",
    },
    "document_status": {
        "template_reference_required": "se requiere una referencia a una plantilla",
        "template_reference_verification_required": "se requiere verificar la plantilla",
        "approved_reusable_reference_available": "referencia reutilizable aprobada disponible",
        "template_reference_not_ready": "la referencia a la plantilla no está preparada",
        "not_planned_by_confirmed_applicability": "no previsto según la aplicabilidad confirmada",
        "applicability_review_required": "se requiere revisar la aplicabilidad",
    },
    "missing_item_type": {
        "evidence_record": "documento o evidencia",
        "tax_fact": "dato fiscal",
        "party_fact": "dato del perfil del cliente",
        "identity_document": "documento de identidad del cliente",
        "representative": "representante o ejecutor",
        "beneficial_owner": "titular real",
        "representative_posture": "representación y ejecutor",
        "ownership_status": "situación de la titularidad real",
        "screening_result": "verificación PEP, sanciones o países",
        "privacy_processing": "decisión sobre privacidad",
        "applicability": "aplicabilidad documental",
        "aml_assessment": "evaluación de prevención del blanqueo",
        "aml_trigger": "indicador de prevención del blanqueo",
        "engagement_terms": "condiciones del encargo",
        "client_file_preparation_binding": "expediente preparatorio del cliente",
    },
    "missing_reason": {
        "supporting_evidence_not_verified": "las evidencias de respaldo no se han verificado",
        "evidence_status_requested": "se ha solicitado, pero todavía no se ha recibido",
        "evidence_status_missing": "no está disponible actualmente",
        "evidence_status_stale": "debe actualizarse",
        "evidence_expired": "su vigencia registrada ha caducado",
        "verification_status_unknown": "el dato debe proporcionarse y verificarse",
        "verification_status_reported": "el dato declarado debe verificarse",
        "identity_verification_status_unknown": "debe completarse la verificación de identidad",
        "identity_verification_status_reported": "debe confirmarse la verificación de identidad declarada",
        "identity_verification_status_not_applicable": "debe confirmarse por qué no es aplicable el documento de identidad",
        "identity_document_expired": "el documento de identidad ha caducado",
        "representative_or_executor_posture_pending": "deben definirse los representantes y el ejecutor",
        "beneficial_ownership_posture_pending": "debe definirse la situación de la titularidad real",
        "professional_resolution_pending": "se requiere una resolución profesional documentada",
        "professional_confirmation_pending": "se requiere confirmación profesional",
        "professional_resolution_do_not_proceed": "la decisión profesional registrada indica que no se debe continuar",
        "privacy_processing_decision_pending": "debe completarse la decisión sobre el tratamiento de datos",
        "applicability_unclear": "debe aclararse la aplicabilidad",
        "table_1_status_unknown": "debe resolverse la aplicabilidad de la tabla 1",
        "mandatory_trigger_status_unknown": "debe resolverse el estado del indicador obligatorio",
        "positive_trigger_requires_confirmation": "el indicador positivo requiere confirmación profesional",
        "engagement_terms_incomplete": "deben completarse las condiciones del encargo",
        "bound_client_file_preparation_run_not_final_ready": "el expediente preparatorio vinculado no está listo para su uso profesional",
    },
}

if set(_SPANISH_DISPLAY_COPY) != set(_DISPLAY_COPY):
    raise RuntimeError("Spanish display-copy categories must match the canonical set")
for _category, _translations in _SPANISH_DISPLAY_COPY.items():
    if set(_translations) != set(_DISPLAY_COPY[_category]):
        raise RuntimeError(
            f"Spanish display-copy values are incomplete for {_category!r}"
        )
    for _value, _translation in _translations.items():
        _DISPLAY_COPY[_category][_value]["es"] = _translation


def _display_value(category: str, value: str | None, language: str) -> str:
    """Map contract codes to reviewed display copy without leaking raw codes."""

    # These are closed workflow enums, so failing on unmapped copy is safer and
    # mechanically auditable than silently exposing a machine code to a client.
    try:
        return _DISPLAY_COPY[category][value][language]
    except KeyError as exc:
        raise ValidationError(
            f"Missing {language!r} display copy for {category} value {value!r}."
        ) from exc


def _run_id(generated_at: str, input_hash: str) -> str:
    timestamp = re.sub(r"[^0-9]", "", generated_at)
    return f"new-client-{timestamp}-{input_hash[:12]}"


def _write_memo(
    path: Path,
    *,
    intake: Mapping[str, Any],
    aml_result: Mapping[str, Any],
    missing: Mapping[str, Any],
    documents: Mapping[str, Any],
    monitoring: Mapping[str, Any],
    run_id: str,
) -> Path:
    language = str(intake["language"])
    text = _LOCALE_TEXT[language]
    document_statuses = ", ".join(
        f"{_display_value('document_type', record['document_type'], language)}: "
        f"{_display_value('document_status', record['status'], language)}"
        for record in documents["documents"]
    )
    table_1 = aml_result["table_1_assessment"]
    lines = [
        f"# {text['memo_title']}",
        "",
        f"- {text['run_id']}: `{run_id}`",
        f"- {text['client_reference']}: `{intake['client_reference']}`",
        f"- {text['engagement']}: "
        f"{_display_value('engagement_kind', intake['engagement']['kind'], language)}",
        f"- {text['package_status']}: "
        f"{_display_value('package_status', 'draft_for_professional_review', language)}",
        f"- {text['jurisdiction']}: "
        f"{_display_value('jurisdiction', intake['jurisdiction'], language)}",
        f"- {text['country_pack']}: "
        f"{_display_value('country_pack', ITALY_COUNTRY_PACK, language)}",
        "",
        f"## {text['aml_heading']}",
        "",
        f"- RI: `{aml_result['inherent_risk']}`",
        f"- RS: `{aml_result['specific_risk']}`",
        f"- RE: `{aml_result['effective_risk']}`",
        f"- {text['calculated_band']}: "
        f"{_display_value('risk_band', aml_result['calculated_band']['code'], language)}",
        f"- {text['table_1_status']}: "
        f"{_display_value('table_1_status', table_1['status'], language)} "
        f"({_display_value('review_status', table_1['review_status'], language)})",
        f"- {text['baseline_treatment']}: "
        f"{_display_value('verification_mode', aml_result['baseline_verification_mode'], language)}",
        f"- {text['table1_note']}",
        f"- {text['formula']}: `RE = (RI × 30%) + (RS × 70%)`",
        f"- {text['arithmetic_note']}",
        "",
        f"## {text['evidence_heading']}",
        "",
        f"- {text['open_items']}: `{missing['count']}`",
        f"- {text['aml_status']}: "
        f"{_display_value('aml_status', aml_result['status'], language)}",
        f"- {text['monitoring_status']}: "
        f"{_display_value('monitoring_status', monitoring['status'], language)}",
        f"- {text['documents']}: {document_statuses}",
        "",
        f"## {text['review_boundary']}",
        "",
        text["boundary_note"],
    ]
    return write_private_text(path, "\n".join(lines))


def _write_client_missing_information_draft(
    path: Path,
    *,
    client_reference: str,
    missing: Mapping[str, Any],
    language: str,
) -> Path:
    text = _LOCALE_TEXT[language]
    lines = [
        f"# {text['missing_title']}",
        "",
        f"{text['client_reference']}: `{client_reference}`",
        "",
        text["draft_notice"],
        "",
    ]
    if missing["items"]:
        lines.extend([text["provide"], ""])
        for item in missing["items"]:
            lines.append(
                f"- {_display_value('missing_item_type', item['item_type'], language)}: "
                f"{_display_value('missing_reason', item['reason'], language)}."
            )
    else:
        lines.append(text["none_missing"])
    lines.extend(
        [
            "",
            text["secure_channel"],
        ]
    )
    return write_private_text(path, "\n".join(lines))


def _write_review_handoff(path: Path, *, run_id: str, language: str) -> Path:
    text = _LOCALE_TEXT[language]
    steps = text["handoff_steps"]
    return write_private_text(
        path,
        "\n".join(
            [
                f"# {text['handoff_title']}",
                "<!-- review-contract: Review Handoff -->",
                "",
                f"- {text['run_id']}: `{run_id}`",
                f"- {text['review_payload']}: `review_payload.json`",
                f"- {text['pending_decisions']}: `ui_decisions.json`",
                f"- {text['applied_decisions']}: `applied_decisions.json` "
                f"({text['applied_decisions_note']})",
                f"- {text['final_manifest']}: `final_artifacts.json`",
                "",
                f"## {text['review_sequence']}",
                "",
                f"1. {steps[0]}",
                f"2. {steps[1]}",
                f"3. {steps[2]}",
                f"4. {steps[3]}",
                "",
                f"{text['review_tools']}: `validate_new_client_review`, "
                "`render_new_client_review`, "
                "`save_new_client_decisions`, and "
                "`apply_new_client_decisions`.",
                "",
                text["handoff_boundary"],
            ]
        ),
    )


def _artifact_record(path: Path, *, language: str) -> dict[str, Any]:
    record: dict[str, Any] = {
        "path": path.name,
        "kind": path.suffix.removeprefix("."),
        "status": "written_pending_review",
        "size_bytes": path.stat().st_size,
        "sha256": sha256_file(path),
    }
    if path.name == "review_handoff.md":
        record["required_text"] = [
            "Review Handoff",
            _LOCALE_TEXT[language]["handoff_title"],
            "review_payload.json",
            "ui_decisions.json",
            "applied_decisions.json",
            "final_artifacts.json",
        ]
        record["qa_checks"] = ["nonempty_text", "required_text"]
    return record


def _package_new_client_into(
    input_path: Path,
    output_dir: Path,
    *,
    source_registry_path: Path = DEFAULT_SOURCE_REGISTRY,
    generated_at: str | None = None,
    reported_output_dir: Path | None = None,
) -> dict[str, Any]:
    """Build a complete, private and reviewable new-client package."""

    generated_at_value = generated_at or utc_now()
    resolved_input = input_path.expanduser().resolve()
    intake = validate_new_client_input(load_json(resolved_input))
    language = str(intake["language"])
    final_manifest_copy = _FINAL_MANIFEST_COPY.get(language, _FINAL_MANIFEST_COPY["en"])
    source_registry = load_source_registry(source_registry_path.expanduser().resolve())
    validate_source_references(intake, source_registry)
    resolved_output = ensure_private_output_directory(output_dir)
    reported_output = (
        resolved_output
        if reported_output_dir is None
        else reported_output_dir.expanduser().resolve(strict=False)
    )
    existing = [
        name for name in EXPECTED_ARTIFACTS if (resolved_output / name).exists()
    ]
    if existing:
        raise ValidationError(
            "Output directory already contains new-client artifacts. Preserve that "
            "review history and package the changed case in a new run directory: "
            + ", ".join(existing)
        )

    input_hash = canonical_json_hash(intake)
    run_id = _run_id(generated_at_value, input_hash)
    evidence_verifications = verify_evidence_register(
        intake, base_dir=resolved_input.parent
    )
    client_file_preparation_verification = verify_client_file_preparation_binding(
        intake, base_dir=resolved_input.parent
    )
    as_of = date.fromisoformat(generated_at_value[:10])
    template_verifications = verify_template_references(
        intake,
        source_registry,
        base_dir=resolved_input.parent,
        as_of=as_of,
    )
    aml_result = calculate_aml(intake["aml"])
    case_facts = build_case_facts(
        intake,
        generated_at=generated_at_value,
        client_file_preparation_verification=client_file_preparation_verification,
        evidence_verifications=evidence_verifications,
    )
    applicability = build_applicability_plan(intake, generated_at=generated_at_value)
    missing = build_missing_evidence(
        intake,
        aml_result,
        generated_at=generated_at_value,
        as_of=as_of,
        client_file_preparation_verification=client_file_preparation_verification,
    )
    documents = build_document_plan(
        intake,
        generated_at=generated_at_value,
        template_verifications=template_verifications,
    )
    temporal_validity = build_temporal_validity(
        intake,
        source_registry,
        generated_at=generated_at_value,
        document_plan=documents,
    )
    monitoring = build_monitoring_plan(
        intake, aml_result, generated_at=generated_at_value
    )
    export_domain_blockers = build_export_domain_blockers(
        missing, aml_result, documents, monitoring
    )
    registry_artifact = {
        **source_registry,
        "packaged_at": generated_at_value,
        "registry_hash": canonical_json_hash(source_registry),
    }
    review_payload = build_review_payload(
        intake,
        aml_result,
        missing,
        documents,
        monitoring,
        source_registry,
        run_id=run_id,
        generated_at=generated_at_value,
        case_facts_artifact=case_facts,
        applicability_artifact=applicability,
        source_registry_artifact=registry_artifact,
        client_file_preparation_verification=client_file_preparation_verification,
        temporal_validity=temporal_validity,
    )
    aml_draft = {
        "schema_version": SCHEMA_VERSION,
        "generated_at": generated_at_value,
        "status": "draft_for_professional_review",
        "professional_review_required": True,
        "client_reference": intake["client_reference"],
        "assessment_date": intake["aml"]["assessment_date"],
        "inherent_risk_status": intake["aml"]["inherent_risk_status"],
        "factors_a": intake["aml"]["factors_a"],
        "factors_b": intake["aml"]["factors_b"],
        "section_b_mode": intake["aml"]["section_b_mode"],
        "section_b_exclusion_confirmation": intake["aml"].get(
            "section_b_exclusion_confirmation"
        ),
        "table_1_assessment": intake["aml"]["table_1_assessment"],
        "mandatory_enhanced_triggers": intake["aml"]["mandatory_enhanced_triggers"],
        "calculation_summary": {
            "effective_risk": aml_result["effective_risk"],
            "calculated_band": aml_result["calculated_band"],
            "baseline_verification_mode": aml_result["baseline_verification_mode"],
            "minimum_verification_mode_for_review": aml_result[
                "minimum_verification_mode_for_review"
            ],
        },
    }
    local_files_read = [
        resolved_input.as_posix(),
        source_registry_path.expanduser().resolve().as_posix(),
    ]
    local_files_read.extend(
        verification["resolved_path"]
        for verification in evidence_verifications
        if verification.get("resolved_path") is not None
    )
    if client_file_preparation_verification.get("bound_manifest_path") is not None:
        local_files_read.append(
            client_file_preparation_verification["bound_manifest_path"]
        )
    local_files_read.extend(
        record["resolved_path"]
        for record in client_file_preparation_verification.get("verified_outputs", [])
    )
    local_files_read.extend(
        verification["resolved_path"] for verification in template_verifications
    )
    local_files_read = list(dict.fromkeys(local_files_read))
    run_intake = {
        "schema_version": SCHEMA_VERSION,
        "plugin": "new-client",
        "workflow": "new-client",
        "run_id": run_id,
        "generated_at": generated_at_value,
        "created_at": generated_at_value,
        "status": "ready_for_review",
        "jurisdiction": intake["jurisdiction"],
        "country_pack": ITALY_COUNTRY_PACK,
        "language": intake["language"],
        "temporal_validity": temporal_validity,
        "client_reference": intake["client_reference"],
        "input_paths": [resolved_input.as_posix()],
        "output_dir": reported_output.as_posix(),
        "inferred_task": "prepare_reviewable_professional_new_client",
        "assumptions": [
            "Input factor values and applicability records are professional inputs, "
            "not conclusions produced by the deterministic engine."
        ],
        "unresolved_questions": [item["item_id"] for item in missing["items"]],
        "dependency_check": {
            "status": "ready",
            "dependencies": "python_standard_library_only",
        },
        "input": {
            "path": resolved_input.as_posix(),
            "sha256": sha256_file(resolved_input),
            "canonical_payload_sha256": input_hash,
        },
        "source_registry": {
            "path": source_registry_path.expanduser().resolve().as_posix(),
            "sha256": sha256_file(source_registry_path.expanduser().resolve()),
            "canonical_payload_sha256": canonical_json_hash(source_registry),
        },
        "data_posture": {
            "local_files_read": local_files_read,
            "external_connectors_used": [],
            "upload_paths_used": [],
            "remote_sql_execution_used": False,
            "hosted_notebook_execution_used": False,
            "output_directory_mode": "owner_only_0700",
            "artifact_file_mode": "owner_only_0600",
            "review_payload": "private_professional_review",
            "professional_case_data": "included_in_private_review_when_useful",
            "external_uploads": [],
        },
        "execution_trace": [
            {
                "step_id": "validate_input_contract",
                "kind": "deterministic_schema_and_reference_validation",
                "status": "passed",
                "execution_location": "local_python_process",
                "command": ["package_new_client.py", "--input", "<local-input>"],
                "inputs": [
                    *local_files_read,
                ],
                "outputs": ["case_facts_validated.json", "source_registry.json"],
            },
            {
                "step_id": "calculate_aml_arithmetic",
                "kind": "deterministic_formula",
                "status": aml_result["status"],
                "professional_review_required": True,
                "execution_location": "local_python_process",
                "command": ["package_new_client.py", "calculate_aml"],
                "inputs": ["case_facts_validated.json"],
                "outputs": [
                    "aml_assessment_draft.json",
                    "aml_calculation_audit.json",
                    "monitoring_plan.json",
                ],
            },
            {
                "step_id": "build_review_artifacts",
                "kind": "deterministic_packaging",
                "status": "passed",
                "professional_review_required": True,
                "execution_location": "local_python_process",
                "command": ["package_new_client.py", "build_review_artifacts"],
                "inputs": [
                    "case_facts_validated.json",
                    "source_registry.json",
                    "aml_calculation_audit.json",
                ],
                "outputs": list(EXPECTED_ARTIFACTS),
            },
        ],
    }
    ui_decisions = {
        "schema_version": SCHEMA_VERSION,
        "contract_version": SCHEMA_VERSION,
        "plugin": "new-client",
        "workflow": "new-client",
        "run_id": run_id,
        "updated_at": generated_at_value,
        "decided_at": None,
        "decision_source": "professional_review_workbench",
        "review_payload_path": "review_payload.json",
        "status": "pending",
        "decisions": [],
        "decision_count": 0,
    }

    written_paths = [
        write_private_json(resolved_output / "run_intake.json", run_intake),
        write_private_json(resolved_output / "case_facts_validated.json", case_facts),
        write_private_json(resolved_output / "source_registry.json", registry_artifact),
        write_private_json(
            resolved_output / "applicability_plan_validated.json", applicability
        ),
        write_private_json(resolved_output / "aml_assessment_draft.json", aml_draft),
        write_private_json(resolved_output / "aml_calculation_audit.json", aml_result),
        write_private_json(resolved_output / "missing_evidence.json", missing),
        write_private_json(resolved_output / "document_plan.json", documents),
        write_private_json(resolved_output / "monitoring_plan.json", monitoring),
        _write_memo(
            resolved_output / "studio_new_client_memo.md",
            intake=intake,
            aml_result=aml_result,
            missing=missing,
            documents=documents,
            monitoring=monitoring,
            run_id=run_id,
        ),
        _write_client_missing_information_draft(
            resolved_output / "client_missing_information_draft.md",
            client_reference=intake["client_reference"],
            missing=missing,
            language=intake["language"],
        ),
        write_private_json(resolved_output / "review_payload.json", review_payload),
        write_private_json(resolved_output / "ui_decisions.json", ui_decisions),
        _write_review_handoff(
            resolved_output / "review_handoff.md",
            run_id=run_id,
            language=intake["language"],
        ),
    ]
    output_records = [
        _artifact_record(path, language=intake["language"]) for path in written_paths
    ]
    artifact_blockers = [
        {
            "code": "required_output_empty",
            "reference": record["path"],
            "scope": "relationship_export",
        }
        for record in output_records
        if record["size_bytes"] <= 0
    ]
    review_blockers: list[dict[str, str]] = []
    for item in review_payload["items"]:
        if item["item_type"] == "marketing_consent":
            scope = "marketing_use"
        elif item["item_type"] == "document_applicability":
            scope = f"document:{item['data']['topic']}"
        else:
            scope = "relationship_export"
        review_blockers.append(
            {
                "code": "professional_review_pending",
                "reference": item["id"],
                "scope": scope,
            }
        )
    marketing = intake["marketing_consent"]
    marketing_only_blockers: list[dict[str, str]] = []
    marketing_code: str | None = None
    if marketing["request_status"] == "not_requested":
        marketing_code = "marketing_not_requested"
    elif marketing["review_status"] != "confirmed":
        marketing_code = "marketing_choice_pending"
    elif marketing["choice"] == "refused":
        marketing_code = "marketing_refused"
    elif marketing["choice"] == "withdrawn":
        marketing_code = "marketing_withdrawn"
    if marketing_code is not None:
        marketing_only_blockers.append(
            {
                "code": marketing_code,
                "reference": "marketing:consent",
                "scope": "marketing_use",
            }
        )
    required_outputs = [record["path"] for record in output_records]
    relationship_review_blockers = [
        blocker for blocker in review_blockers if blocker["scope"] != "marketing_use"
    ]
    manifest_status = (
        "blocked" if export_domain_blockers or artifact_blockers else "pending_review"
    )
    export_gate = {
        "contract_version": SCHEMA_VERSION,
        "export_scope": "owner_only_professional_review_dossier",
        "evaluated_at": generated_at_value,
        "review_revision": review_payload["review_revision"],
        "status": manifest_status,
        "relationship_ready": False,
        "domain_blockers": export_domain_blockers,
        "review_blockers": review_blockers,
        "artifact_blockers": artifact_blockers,
        "marketing_only_blockers": marketing_only_blockers,
        "required_outputs": required_outputs,
        "basis_hashes": dict(review_payload["basis_hashes"]),
    }
    manifest = {
        "schema_version": SCHEMA_VERSION,
        "plugin": "new-client",
        "workflow": "new-client",
        "run_id": run_id,
        "generated_at": generated_at_value,
        "status": manifest_status,
        "temporal_validity": temporal_validity,
        "professional_review_required": True,
        "signature_performed": False,
        "client_communication_sent": False,
        "relationship_activation_performed": False,
        "export_gate": export_gate,
        "artifacts": output_records,
        "outputs": output_records,
        "package_hash": canonical_json_hash(
            {path.name: sha256_file(path) for path in written_paths}
        ),
        "explicit_non_outcomes": final_manifest_copy["explicit_non_outcomes"],
        "caveats": final_manifest_copy["caveats"],
        "next_actions": final_manifest_copy["next_actions"],
        "blockers": [
            *export_domain_blockers,
            *artifact_blockers,
            *relationship_review_blockers,
        ],
    }
    manifest_path = write_private_json(
        resolved_output / "final_artifacts.json", manifest
    )
    validation = validate_contract(resolved_output)
    return {
        "run_id": run_id,
        "status": manifest_status,
        "output_dir": resolved_output,
        "manifest_path": manifest_path,
        "artifact_count": validation["artifact_count"],
    }


def package_new_client(
    input_path: Path,
    output_dir: Path,
    *,
    source_registry_path: Path = DEFAULT_SOURCE_REGISTRY,
    generated_at: str | None = None,
) -> dict[str, Any]:
    """Build and validate in a sibling staging directory, then publish atomically."""

    requested_output = output_dir.expanduser().absolute()
    resolved_input = input_path.expanduser().resolve()
    input_shares_output = (
        resolved_input.parent == requested_output.resolve(strict=False)
        and resolved_input.name == "new_client_input.json"
    )
    output_existed = requested_output.exists()
    final_output = ensure_private_output_directory(
        requested_output,
        allowed_existing=("new_client_input.json",) if input_shares_output else (),
    )
    staging_output = Path(
        tempfile.mkdtemp(
            prefix=f".{final_output.name}.",
            suffix=".tmp",
            dir=final_output.parent,
        )
    )
    staging_output.chmod(0o700)
    published = False
    backup_output: Path | None = None
    try:
        result = _package_new_client_into(
            input_path,
            staging_output,
            source_registry_path=source_registry_path,
            generated_at=generated_at,
            reported_output_dir=final_output,
        )
        if input_shares_output:
            packaged_input_hash = load_json(staging_output / "run_intake.json")[
                "input"
            ]["sha256"]
            if sha256_file(resolved_input) != packaged_input_hash:
                raise ValidationError(
                    "new_client_input.json changed while the package was being built."
                )
            retained_input = staging_output / resolved_input.name
            shutil.copy2(resolved_input, retained_input)
            retained_input.chmod(0o600)
            if sha256_file(retained_input) != packaged_input_hash:
                raise ValidationError(
                    "The retained new_client_input.json copy failed byte verification."
                )
            backup_output = Path(
                tempfile.mkdtemp(
                    prefix=f".{final_output.name}.",
                    suffix=".backup",
                    dir=final_output.parent,
                )
            )
            backup_output.rmdir()
            os.replace(final_output, backup_output)
        else:
            final_output.rmdir()
        try:
            os.replace(staging_output, final_output)
        except OSError:
            if backup_output is not None:
                os.replace(backup_output, final_output)
                backup_output = None
            else:
                final_output.mkdir(mode=0o700)
            raise
        published = True
        if backup_output is not None:
            shutil.rmtree(backup_output)
            backup_output = None
    finally:
        if not published:
            shutil.rmtree(staging_output, ignore_errors=True)
            if backup_output is not None and backup_output.exists():
                if not final_output.exists():
                    os.replace(backup_output, final_output)
                else:
                    shutil.rmtree(backup_output, ignore_errors=True)
            if not output_existed and final_output.exists():
                try:
                    final_output.rmdir()
                except OSError:
                    pass
    result["output_dir"] = final_output
    result["manifest_path"] = final_output / "final_artifacts.json"
    return result


def build_parser() -> argparse.ArgumentParser:
    """Build the command-line parser."""

    parser = argparse.ArgumentParser(
        description="Build a private, reviewable Vera new-client package."
    )
    parser.add_argument("--input", required=True, type=Path)
    parser.add_argument("--output-dir", required=True, type=Path)
    parser.add_argument(
        "--source-registry",
        type=Path,
        default=DEFAULT_SOURCE_REGISTRY,
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    """Run the packaging command."""

    args = build_parser().parse_args(argv)
    try:
        result = package_new_client(
            args.input,
            args.output_dir,
            source_registry_path=args.source_registry,
        )
    except ValidationError as exc:
        sys.stdout.write(json.dumps({"status": "error", "error": str(exc)}) + "\n")
        return 2
    sys.stdout.write(
        json.dumps(
            {
                **result,
                "output_dir": result["output_dir"].as_posix(),
                "manifest_path": result["manifest_path"].as_posix(),
            },
            ensure_ascii=False,
        )
        + "\n"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
