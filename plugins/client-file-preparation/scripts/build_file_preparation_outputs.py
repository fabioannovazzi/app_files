from __future__ import annotations

import argparse
import csv
import logging
import re
import secrets
import sys
from dataclasses import dataclass
from pathlib import Path
from string import Template
from typing import Iterable, Sequence

SCRIPT_DIR = Path(__file__).resolve().parent


def _ensure_local_review_session_import() -> None:
    """Use this plugin's review-session module in multi-plugin test runs."""

    script_dir = str(SCRIPT_DIR)
    if script_dir in sys.path:
        sys.path.remove(script_dir)
    sys.path.insert(0, script_dir)
    module = sys.modules.get("review_session")
    module_file = getattr(module, "__file__", None) if module is not None else None
    if module_file and Path(module_file).resolve().is_relative_to(SCRIPT_DIR.resolve()):
        return
    if module is not None:
        del sys.modules["review_session"]


_ensure_local_review_session_import()

# isort: off
from check_environment import check_dependencies  # noqa: E402
from detect_duplicates import (  # noqa: E402
    DuplicateCandidate,
    find_duplicate_candidates,
    write_duplicate_candidates_csv as write_file_duplicate_csv,
)
from extract_documents import (  # noqa: E402
    DocumentEvidence,
    extract_documents,
)
from parse_fatturapa_xml import (  # noqa: E402
    InvoiceXmlRecord,
    localize_formal_anomaly,
    parse_xml_files,
    write_duplicate_candidates_csv as write_xml_duplicate_csv,
    write_formal_anomalies_markdown,
    write_summary_csv,
    write_summary_jsonl,
)
from parse_fiscal_forms import (  # noqa: E402
    FiscalField,
    parse_structured_fiscal_fields,
    write_fiscal_fields_csv,
    write_fiscal_fields_jsonl,
    write_fiscal_fields_summary,
)
from review_session import (  # noqa: E402
    write_review_session_artifacts,
    write_run_intake,
)
from scan_folder import (  # noqa: E402
    CATEGORY_730,
    CATEGORY_AVVISI,
    CATEGORY_CH_BANK_TAX,
    CATEGORY_CH_GE_TAX,
    CATEGORY_CH_SALARY_CERTIFICATE,
    CATEGORY_CH_TAX_ASSESSMENT,
    CATEGORY_CH_TAX_RETURN,
    CATEGORY_CH_ZH_TAX,
    CATEGORY_CU,
    CATEGORY_F24,
    CATEGORY_FATTURE_XML,
    CATEGORY_MUTUO,
    CATEGORY_NON_CLASSIFICATI,
    CATEGORY_REDDITI_PF,
    CATEGORY_RICEVUTE_SANITARIE,
    CATEGORY_UK_BANK_TAX,
    CATEGORY_UK_HMRC_NOTICE,
    CATEGORY_UK_PAYSLIP,
    CATEGORY_UK_SELF_ASSESSMENT,
    CATEGORY_UK_YEAR_END_PAYROLL,
    FileRecord,
    scan_folder,
    verify_source_snapshot,
    write_index_markdown,
    write_inventory_csv,
)

# isort: on

__all__ = [
    "BuildResult",
    "SUPPORTED_JURISDICTIONS",
    "SUPPORTED_LANGUAGES",
    "build_file_preparation_outputs",
]

LOGGER = logging.getLogger(__name__)
PLUGIN_ROOT = SCRIPT_DIR.parent
TEMPLATE_DIR = PLUGIN_ROOT / "templates"
SUPPORTED_JURISDICTIONS = ("italy", "geneva", "zurich", "uk", "mixed")
SUPPORTED_LANGUAGES = ("it", "en", "fr", "de")
OCR_LANGUAGE_BY_LANGUAGE = {
    "it": "it",
    "en": "en",
    "fr": "fr",
    "de": "german",
}

COPY = {
    "it": {
        "missing_title": "Documenti mancanti o incerti",
        "missing_intro": "Elenco operativo costruito da classificazione, parsing e testo estratto.",
        "missing_empty": "Nessuna mancanza evidente nei controlli automatici.",
        "questions_title": "Domande interne dello studio",
        "questions_intro": "Punti operativi emersi dalla classificazione e dagli estratti disponibili.",
        "questions_empty": "Nessuna domanda generata automaticamente.",
    },
    "en": {
        "missing_title": "Missing or uncertain documents",
        "missing_intro": "Operational list based on classification, parsing, and extracted text.",
        "missing_empty": "No obvious missing items were found by the automated checks.",
        "questions_title": "Questions for the firm",
        "questions_intro": "Operational points raised by classification and the available extracts.",
        "questions_empty": "No questions were generated automatically.",
    },
    "fr": {
        "missing_title": "Documents manquants ou incertains",
        "missing_intro": "Liste opérationnelle fondée sur la classification, l’analyse et le texte extrait.",
        "missing_empty": "Aucun élément manifestement manquant dans les contrôles automatiques.",
        "questions_title": "Questions internes du cabinet",
        "questions_intro": "Points opérationnels issus de la classification et des extraits disponibles.",
        "questions_empty": "Aucune question générée automatiquement.",
    },
    "de": {
        "missing_title": "Fehlende oder unklare Unterlagen",
        "missing_intro": "Arbeitsliste auf Grundlage von Klassifizierung, Auswertung und extrahiertem Text.",
        "missing_empty": "Bei den automatischen Prüfungen wurden keine offensichtlichen Lücken gefunden.",
        "questions_title": "Interne Fragen der Kanzlei",
        "questions_intro": "Arbeitspunkte aus der Klassifizierung und den verfügbaren Auszügen.",
        "questions_empty": "Es wurden keine Fragen automatisch erstellt.",
    },
}

CATEGORY_LABELS = {
    "it": {
        CATEGORY_CH_GE_TAX: "documenti fiscali di Ginevra",
        CATEGORY_CH_ZH_TAX: "documenti fiscali di Zurigo",
        CATEGORY_CH_TAX_RETURN: "dichiarazione fiscale svizzera",
        CATEGORY_CH_TAX_ASSESSMENT: "tassazione svizzera",
        CATEGORY_CH_SALARY_CERTIFICATE: "certificato di salario svizzero",
        CATEGORY_CH_BANK_TAX: "certificati fiscali bancari e d’imposta preventiva svizzeri",
        CATEGORY_UK_YEAR_END_PAYROLL: "documenti britannici P60 / P45 / P11D",
        CATEGORY_UK_PAYSLIP: "cedolino britannico",
        CATEGORY_UK_SELF_ASSESSMENT: "dichiarazione britannica Self Assessment",
        CATEGORY_UK_HMRC_NOTICE: "comunicazioni HMRC britanniche",
        CATEGORY_UK_BANK_TAX: "certificati fiscali bancari e d’investimento britannici",
    },
    "en": {
        "730 / precompilata": "Italian 730 / pre-filled return",
        "fatture elettroniche XML": "electronic invoices (XML)",
        "ricevute sanitarie": "medical receipts",
        "mutuo": "mortgage",
        "affitto / locazione": "rent / lease",
        "assicurazioni": "insurance",
        "previdenza": "social security",
        "avvisi / comunicazioni": "notices / communications",
        "contratti": "contracts",
        "documenti non classificati": "unclassified documents",
    },
    "fr": {
        "730 / precompilata": "déclaration italienne 730 / préremplie",
        "fatture elettroniche XML": "factures électroniques XML",
        "ricevute sanitarie": "reçus médicaux",
        "mutuo": "prêt hypothécaire",
        "affitto / locazione": "loyer / bail",
        "assicurazioni": "assurances",
        "previdenza": "prévoyance sociale",
        "avvisi / comunicazioni": "avis / communications",
        "contratti": "contrats",
        "documenti non classificati": "documents non classés",
        CATEGORY_CH_GE_TAX: "documents fiscaux genevois",
        CATEGORY_CH_ZH_TAX: "documents fiscaux zurichois",
        CATEGORY_CH_TAX_RETURN: "déclaration fiscale suisse",
        CATEGORY_CH_TAX_ASSESSMENT: "taxation suisse",
        CATEGORY_CH_SALARY_CERTIFICATE: "certificat de salaire suisse",
        CATEGORY_CH_BANK_TAX: "attestations fiscales bancaires et d’impôt anticipé suisses",
        CATEGORY_UK_YEAR_END_PAYROLL: "documents britanniques P60 / P45 / P11D",
        CATEGORY_UK_PAYSLIP: "bulletin de salaire britannique",
        CATEGORY_UK_SELF_ASSESSMENT: "déclaration britannique Self Assessment",
        CATEGORY_UK_HMRC_NOTICE: "avis HMRC britanniques",
        CATEGORY_UK_BANK_TAX: "attestations fiscales bancaires et d’investissement britanniques",
    },
    "de": {
        "730 / precompilata": "italienische Erklärung 730 / vorausgefüllt",
        "fatture elettroniche XML": "elektronische Rechnungen (XML)",
        "ricevute sanitarie": "Gesundheitsbelege",
        "mutuo": "Hypothek",
        "affitto / locazione": "Miete / Pacht",
        "assicurazioni": "Versicherungen",
        "previdenza": "Sozialversicherung",
        "avvisi / comunicazioni": "Bescheide / Mitteilungen",
        "contratti": "Verträge",
        "documenti non classificati": "nicht klassifizierte Dokumente",
        CATEGORY_CH_GE_TAX: "Genfer Steuerunterlagen",
        CATEGORY_CH_ZH_TAX: "Zürcher Steuerunterlagen",
        CATEGORY_CH_TAX_RETURN: "Schweizer Steuererklärung",
        CATEGORY_CH_TAX_ASSESSMENT: "Schweizer Steuerveranlagung",
        CATEGORY_CH_SALARY_CERTIFICATE: "Schweizer Lohnausweis",
        CATEGORY_CH_BANK_TAX: "Schweizer Bank- und Verrechnungssteuerbescheinigungen",
        CATEGORY_UK_YEAR_END_PAYROLL: "britische P60-/P45-/P11D-Unterlagen",
        CATEGORY_UK_PAYSLIP: "britische Lohnabrechnung",
        CATEGORY_UK_SELF_ASSESSMENT: "britische Self-Assessment-Steuererklärung",
        CATEGORY_UK_HMRC_NOTICE: "britische HMRC-Mitteilungen",
        CATEGORY_UK_BANK_TAX: "britische Bank- und Kapitalertragsteuerbescheinigungen",
    },
}


def _copy(language: str, key: str) -> str:
    return COPY[language][key]


def _category_label(category: str, language: str) -> str:
    return CATEGORY_LABELS.get(language, {}).get(category, category)


def _inventory_note_label(value: str, language: str) -> str:
    """Localize a human-facing inventory diagnostic while retaining source facts."""

    if language == "it":
        return value
    if value == "classificazione non certa":
        return {
            "en": "classification uncertain",
            "fr": "classification incertaine",
            "de": "Klassifizierung unklar",
        }[language]
    if value.startswith("anno non coerente con target "):
        year = value.removeprefix("anno non coerente con target ")
        return {
            "en": f"year differs from target {year}",
            "fr": f"année différente de la cible {year}",
            "de": f"Jahr weicht vom Zieljahr {year} ab",
        }[language]
    if value.startswith("immagine"):
        return {
            "en": "image: possible receipt or scanned document",
            "fr": "image : reçu possible ou document numérisé",
            "de": "Bild: möglicher Beleg oder gescanntes Dokument",
        }[language]
    if value.startswith("XML generico"):
        return {
            "en": "generic XML: FatturaPA structure not identified",
            "fr": "XML générique : structure FatturaPA non identifiée",
            "de": "Generisches XML: FatturaPA-Struktur nicht erkannt",
        }[language]
    if value == "collegamento simbolico non seguito":
        return {
            "en": "symbolic link not followed",
            "fr": "lien symbolique non suivi",
            "de": "symbolischer Link wurde nicht verfolgt",
        }[language]
    return value


def _duplicate_type_label(value: str, language: str) -> str:
    return (
        {
            "hash-identico": {
                "it": "hash identico",
                "en": "identical hash",
                "fr": "empreinte identique",
                "de": "identischer Hash",
            },
            "nome-dimensione-simile": {
                "it": "nome e dimensione simili",
                "en": "similar name and size",
                "fr": "nom et taille similaires",
                "de": "ähnlicher Name und ähnliche Größe",
            },
        }
        .get(value, {})
        .get(language, value)
    )


@dataclass(frozen=True)
class BuildResult:
    """Files produced by the first-intake workflow."""

    output_dir: Path
    file_count: int
    category_count: int
    missing_count: int
    duplicate_count: int
    xml_count: int
    notice_count: int
    extracted_count: int
    unreadable_count: int
    missing_dependency_count: int
    structured_field_count: int


def _infer_client_name(folder: Path, target_year: int | None) -> str:
    if target_year is not None and folder.name == str(target_year):
        return folder.parent.name
    if re.fullmatch(r"20[0-4]\d", folder.name):
        return folder.parent.name
    slug_year = re.fullmatch(r"(.+?)[-_ ](20[0-4]\d)", folder.name)
    raw_name = slug_year.group(1) if slug_year else folder.name
    if "-" in raw_name or "_" in raw_name:
        return " ".join(
            part.capitalize() for part in re.split(r"[-_]+", raw_name) if part
        )
    return raw_name


def _category_map(records: Iterable[FileRecord]) -> dict[str, list[FileRecord]]:
    categories: dict[str, list[FileRecord]] = {}
    for record in records:
        categories.setdefault(record.category, []).append(record)
    return categories


def _has_name(records: Sequence[FileRecord], pattern: str) -> bool:
    regex = re.compile(pattern, re.IGNORECASE)
    return any(regex.search(record.file_name) for record in records)


def _evidence_text_map(
    evidence: Sequence[DocumentEvidence], output_dir: Path
) -> dict[str, str]:
    texts: dict[str, str] = {}
    for item in evidence:
        if not item.text_path:
            continue
        text_path = output_dir / item.text_path
        try:
            texts[item.relative_path] = text_path.read_text(encoding="utf-8")
        except OSError:
            continue
    return texts


def _any_extracted_text(evidence_texts: dict[str, str], pattern: str) -> bool:
    regex = re.compile(pattern, re.IGNORECASE)
    return any(regex.search(text) for text in evidence_texts.values())


def _has_italian_tax_context(
    categories: dict[str, list[FileRecord]],
    evidence_texts: dict[str, str],
) -> bool:
    italian_categories = {
        CATEGORY_730,
        CATEGORY_AVVISI,
        CATEGORY_CU,
        CATEGORY_F24,
        CATEGORY_FATTURE_XML,
        CATEGORY_MUTUO,
        CATEGORY_REDDITI_PF,
        CATEGORY_RICEVUTE_SANITARIE,
    }
    if any(categories.get(category) for category in italian_categories):
        return True
    return _any_extracted_text(
        evidence_texts,
        r"certificazione\s+unica|\bf24\b|modello\s+730|redditi\s+persone\s+fisiche|fattura\s+elettronica|agenzia\s+delle\s+entrate",
    )


def _write_environment_report(
    output_path: Path,
    require_ocr: bool,
    language: str = "it",
) -> tuple[int, bool]:
    available, missing = check_dependencies(require_ocr=require_ocr)
    labels = {
        "it": {
            "title": "Controllo ambiente",
            "ocr": "OCR richiesto",
            "yes": "sì",
            "no": "no",
            "available_count": "Dipendenze disponibili",
            "missing_count": "Dipendenze mancanti",
            "available": "Disponibili",
            "missing": "Mancanti",
            "commands": "Comandi suggeriti",
            "ready": "Ambiente pronto per le funzioni richieste.",
        },
        "en": {
            "title": "Environment check",
            "ocr": "OCR required",
            "yes": "yes",
            "no": "no",
            "available_count": "Available dependencies",
            "missing_count": "Missing dependencies",
            "available": "Available",
            "missing": "Missing",
            "commands": "Suggested commands",
            "ready": "The environment is ready for the requested functions.",
        },
        "fr": {
            "title": "Contrôle de l’environnement",
            "ocr": "OCR requis",
            "yes": "oui",
            "no": "non",
            "available_count": "Dépendances disponibles",
            "missing_count": "Dépendances manquantes",
            "available": "Disponibles",
            "missing": "Manquantes",
            "commands": "Commandes suggérées",
            "ready": "L’environnement est prêt pour les fonctions demandées.",
        },
        "de": {
            "title": "Umgebungsprüfung",
            "ocr": "OCR erforderlich",
            "yes": "ja",
            "no": "nein",
            "available_count": "Verfügbare Abhängigkeiten",
            "missing_count": "Fehlende Abhängigkeiten",
            "available": "Verfügbar",
            "missing": "Fehlend",
            "commands": "Empfohlene Befehle",
            "ready": "Die Umgebung ist für die angeforderten Funktionen bereit.",
        },
    }[language]
    lines = [
        f"# {labels['title']}",
        "",
        f"- {labels['ocr']}: {labels['yes'] if require_ocr else labels['no']}",
        f"- {labels['available_count']}: {len(available)}",
        f"- {labels['missing_count']}: {len(missing)}",
        "",
    ]
    if available:
        lines.extend([f"## {labels['available']}", ""])
        lines.extend(f"- {dependency.label}" for dependency in available)
        lines.append("")
    if missing:
        lines.extend([f"## {labels['missing']}", ""])
        lines.extend(f"- {dependency.label}" for dependency in missing)
        lines.extend(["", f"## {labels['commands']}", ""])
        for hint in sorted(
            {
                dependency.install_hint
                for dependency in missing
                if dependency.install_hint
            }
        ):
            lines.append(f"- `{hint}`")
        lines.append("")
    else:
        lines.append(labels["ready"])
    output_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return len(missing), any(
        dependency.label == "PaddleOCR" for dependency in available
    )


def _build_missing_items(
    records: Sequence[FileRecord],
    duplicate_candidates: Sequence[DuplicateCandidate],
    xml_records: Sequence[InvoiceXmlRecord],
    document_evidence: Sequence[DocumentEvidence],
    evidence_texts: dict[str, str],
    output_dir: Path,
    target_year: int | None,
    jurisdiction: str = "italy",
) -> list[str]:
    categories = _category_map(records)
    items: list[str] = []

    has_italian_context = _has_italian_tax_context(categories, evidence_texts)
    if jurisdiction in {"italy", "mixed"} and has_italian_context:
        cu_records = categories.get(CATEGORY_CU, [])
        cu_found = bool(cu_records) or _any_extracted_text(
            evidence_texts,
            r"certificazione\s+unica|\bcu\b|sostituto\s+d[' ]imposta",
        )
        if not cu_found:
            items.append(
                "Non è stata individuata una CU. Verificare se il cliente deve inviarla "
                "o se non è pertinente per la pratica."
            )
        elif len(cu_records) == 1:
            items.append(
                "Presente una CU. Confermare con il cliente l'assenza di ulteriori CU, "
                "redditi esteri, locazioni, attività autonoma o partecipazioni."
            )

        mutuo_records = categories.get(CATEGORY_MUTUO, [])
        mutuo_found = bool(mutuo_records) or _any_extracted_text(
            evidence_texts,
            r"\bmutuo\b|interessi\s+passivi",
        )
        if mutuo_found and not (
            _has_name(mutuo_records, r"interess")
            or _any_extracted_text(
                evidence_texts, r"interessi\s+passivi|certificazione\s+interessi"
            )
        ):
            items.append(
                "Presente documentazione mutuo, ma non risulta individuata una "
                "certificazione interessi passivi separata."
            )

        sanitary_category = bool(categories.get(CATEGORY_RICEVUTE_SANITARIE))
        sanitary_text = _any_extracted_text(
            evidence_texts,
            r"spes[ae]\s+sanitari[ae]|farmacia|medic[oi]|scontrino",
        )
        if sanitary_category:
            items.append(
                "Ricevute sanitarie presenti: verificare intestazione, tracciabilità "
                "e presenza nella precompilata."
            )
        elif sanitary_text:
            items.append(
                "Sono presenti riferimenti a spese sanitarie nei documenti leggibili. "
                "Verificare se le ricevute o i dettagli di supporto sono nel fascicolo."
            )

        if categories.get(CATEGORY_F24) or _any_extracted_text(
            evidence_texts,
            r"\bf24\b|codice\s+tributo|sezione\s+erario",
        ):
            items.append(
                "F24 presenti, ma non è possibile stabilire automaticamente se il set "
                "sia completo o se servano ulteriori deleghe."
            )

        if categories.get(CATEGORY_730) and not cu_found:
            items.append(
                "Presente documentazione 730/precompilata senza CU individuata: "
                "verificare completezza documenti reddituali."
            )

        if categories.get(CATEGORY_REDDITI_PF) and not cu_found:
            items.append(
                "Presente documentazione Redditi PF senza CU individuata: verificare "
                "il perimetro reddituale con il cliente."
            )

    elif categories and jurisdiction == "italy":
        items.append(
            "Il fascicolo è impostato su Italia ma non contiene un contesto fiscale "
            "italiano chiaramente leggibile. Verificare il perimetro documentale."
        )
    elif categories and jurisdiction in {"geneva", "zurich", "uk"}:
        items.append(
            f"Verificare la completezza documentale rispetto alla giurisdizione "
            f"{jurisdiction} indicata nel run."
        )

    if jurisdiction == "mixed":
        items.append(
            "Giurisdizione mista: separare i documenti e le verifiche di completezza "
            "per ciascun ambito nazionale o cantonale."
        )

    if categories.get(CATEGORY_FATTURE_XML):
        items.append(
            "Fatture XML presenti: verificare eventuali anomalie formali nei riepiloghi."
        )

    outside_year = [
        record.relative_path
        for record in records
        if target_year is not None and record.years and target_year not in record.years
    ]
    if outside_year:
        items.append(
            "Sono presenti file con anno non coerente con l'anno target: "
            + ", ".join(f"`{path}`" for path in outside_year[:8])
            + ("." if len(outside_year) <= 8 else " e altri.")
        )

    if categories.get(CATEGORY_NON_CLASSIFICATI):
        items.append(
            "Sono presenti documenti non classificati: verificare se devono essere "
            "rinominati, archiviati o esclusi dal fascicolo."
        )

    malformed_xml = [record.relative_path for record in xml_records if record.malformed]
    if malformed_xml:
        items.append(
            "Alcuni XML non sono leggibili o risultano malformati: "
            + ", ".join(f"`{path}`" for path in malformed_xml[:8])
            + "."
        )

    if duplicate_candidates:
        items.append(
            "Sono presenti duplicati potenziali tra i file. Verificare prima di "
            "considerare completo l'inventario."
        )

    unreadable = [
        evidence
        for evidence in document_evidence
        if not evidence.readable and evidence.needs_ocr
    ]
    if unreadable:
        items.append(
            "Alcuni PDF o immagini non sono stati letti in modo affidabile. "
            "Vedere `extracted/extraction_report.md` "
            "e installare/abilitare OCR se necessario."
        )

    return items


MISSING_ITEM_TRANSLATIONS = {
    "en": {
        "Non è stata individuata una CU.": "No Certificazione Unica (CU) was found. Check whether the client must provide it or whether it is not relevant to this engagement.",
        "Presente una CU.": "One Certificazione Unica (CU) is present. Confirm that there are no other CUs, foreign income, rental income, self-employment income, or participations.",
        "Presente documentazione mutuo": "Mortgage documents are present, but no separate mortgage-interest certificate was identified.",
        "Ricevute sanitarie presenti": "Medical receipts are present: verify the holder, payment traceability, and inclusion in the pre-filled return.",
        "Sono presenti riferimenti a spese sanitarie": "Readable documents refer to medical expenses. Check whether the receipts or supporting details are in the file.",
        "F24 presenti": "F24 forms are present, but the automated checks cannot establish whether the set is complete or whether further forms are required.",
        "Presente documentazione 730/precompilata": "730/pre-filled-return documents are present without an identified CU; verify that the income documents are complete.",
        "Presente documentazione Redditi PF": "Redditi PF documents are present without an identified CU; verify the client's income perimeter.",
        "Il fascicolo è impostato su Italia": "The run is scoped to Italy, but no clearly readable Italian tax context was found. Review the document perimeter.",
        "Verificare la completezza documentale": "Check document completeness against the jurisdiction recorded for the run.",
        "Giurisdizione mista": "Mixed jurisdiction: separate the documents and completeness checks for each national or cantonal scope.",
        "Fatture XML presenti": "XML invoices are present; review the formal-anomaly summaries.",
        "Sono presenti documenti non classificati": "Unclassified documents are present; decide whether to rename, archive, or exclude them from the file.",
        "Sono presenti duplicati potenziali": "Potential duplicate files are present. Review them before treating the inventory as complete.",
        "Alcuni PDF o immagini": "Some PDFs or images could not be read reliably. See `extracted/extraction_report.md` and enable OCR if needed.",
    },
    "fr": {
        "Non è stata individuata una CU.": "Aucune Certificazione Unica (CU) n’a été trouvée. Vérifier si le client doit la fournir ou si elle n’est pas pertinente pour cette mission.",
        "Presente una CU.": "Une Certificazione Unica (CU) est présente. Confirmer l’absence d’autres CU, revenus étrangers, loyers, activités indépendantes ou participations.",
        "Presente documentazione mutuo": "Des documents hypothécaires sont présents, mais aucune attestation séparée des intérêts n’a été identifiée.",
        "Ricevute sanitarie presenti": "Des reçus médicaux sont présents : vérifier le titulaire, la traçabilité du paiement et leur présence dans la déclaration préremplie.",
        "Sono presenti riferimenti a spese sanitarie": "Les documents lisibles mentionnent des frais médicaux. Vérifier que les reçus ou justificatifs figurent dans le dossier.",
        "F24 presenti": "Des formulaires F24 sont présents, mais les contrôles automatiques ne permettent pas d’établir si l’ensemble est complet.",
        "Presente documentazione 730/precompilata": "Des documents 730/préremplis sont présents sans CU identifiée ; vérifier l’exhaustivité des justificatifs de revenus.",
        "Presente documentazione Redditi PF": "Des documents Redditi PF sont présents sans CU identifiée ; vérifier le périmètre des revenus du client.",
        "Il fascicolo è impostato su Italia": "L’exécution est définie pour l’Italie, mais aucun contexte fiscal italien clairement lisible n’a été trouvé. Vérifier le périmètre documentaire.",
        "Verificare la completezza documentale": "Vérifier l’exhaustivité des documents selon la juridiction enregistrée pour l’exécution.",
        "Giurisdizione mista": "Juridiction mixte : séparer les documents et les contrôles d’exhaustivité pour chaque périmètre national ou cantonal.",
        "Fatture XML presenti": "Des factures XML sont présentes ; examiner les synthèses des anomalies formelles.",
        "Sono presenti documenti non classificati": "Des documents non classés sont présents ; décider s’ils doivent être renommés, archivés ou exclus du dossier.",
        "Sono presenti duplicati potenziali": "Des doublons potentiels sont présents. Les examiner avant de considérer l’inventaire comme complet.",
        "Alcuni PDF o immagini": "Certains PDF ou images n’ont pas pu être lus de manière fiable. Voir `extracted/extraction_report.md` et activer l’OCR si nécessaire.",
    },
    "de": {
        "Non è stata individuata una CU.": "Es wurde keine Certificazione Unica (CU) gefunden. Prüfen Sie, ob der Mandant sie bereitstellen muss oder ob sie für dieses Mandat nicht relevant ist.",
        "Presente una CU.": "Eine Certificazione Unica (CU) ist vorhanden. Bestätigen Sie, dass keine weiteren CU, ausländischen Einkünfte, Mieten, selbständigen Tätigkeiten oder Beteiligungen vorliegen.",
        "Presente documentazione mutuo": "Hypothekenunterlagen sind vorhanden, aber es wurde keine separate Zinsbescheinigung gefunden.",
        "Ricevute sanitarie presenti": "Gesundheitsbelege sind vorhanden: Inhaber, Nachvollziehbarkeit der Zahlung und Aufnahme in die vorausgefüllte Erklärung prüfen.",
        "Sono presenti riferimenti a spese sanitarie": "Lesbare Dokumente enthalten Hinweise auf Gesundheitsausgaben. Prüfen Sie, ob Belege oder Nachweise in der Akte vorhanden sind.",
        "F24 presenti": "F24-Formulare sind vorhanden; die automatischen Prüfungen können jedoch nicht feststellen, ob der Satz vollständig ist.",
        "Presente documentazione 730/precompilata": "Unterlagen zur Erklärung 730 sind ohne erkannte CU vorhanden; Vollständigkeit der Einkommensunterlagen prüfen.",
        "Presente documentazione Redditi PF": "Redditi-PF-Unterlagen sind ohne erkannte CU vorhanden; Einkommensumfang des Mandanten prüfen.",
        "Il fascicolo è impostato su Italia": "Der Lauf ist auf Italien ausgerichtet, aber es wurde kein klar lesbarer italienischer Steuerkontext gefunden. Dokumentumfang prüfen.",
        "Verificare la completezza documentale": "Vollständigkeit der Unterlagen anhand der für den Lauf erfassten Jurisdiktion prüfen.",
        "Giurisdizione mista": "Gemischte Jurisdiktion: Unterlagen und Vollständigkeitsprüfungen nach nationalem oder kantonalem Bereich trennen.",
        "Fatture XML presenti": "XML-Rechnungen sind vorhanden; Zusammenfassungen der formalen Auffälligkeiten prüfen.",
        "Sono presenti documenti non classificati": "Nicht klassifizierte Dokumente sind vorhanden; entscheiden Sie, ob sie umbenannt, archiviert oder ausgeschlossen werden.",
        "Sono presenti duplicati potenziali": "Mögliche Dateiduplikate sind vorhanden. Vor Abschluss des Inventars prüfen.",
        "Alcuni PDF o immagini": "Einige PDF-Dateien oder Bilder konnten nicht zuverlässig gelesen werden. Siehe `extracted/extraction_report.md`; OCR bei Bedarf aktivieren.",
    },
}


def _localize_missing_item(item: str, language: str) -> str:
    if language == "it":
        return item
    if item.startswith("Sono presenti file con anno non coerente"):
        paths = item.split(":", 1)[1].strip() if ":" in item else ""
        prefix = {
            "en": "Files outside the target year are present:",
            "fr": "Des fichiers hors de l’année cible sont présents :",
            "de": "Dateien außerhalb des Zieljahres sind vorhanden:",
        }[language]
        return f"{prefix} {paths}"
    if item.startswith("Alcuni XML non sono leggibili"):
        paths = item.split(":", 1)[1].strip() if ":" in item else ""
        prefix = {
            "en": "Some XML files are unreadable or malformed:",
            "fr": "Certains fichiers XML sont illisibles ou mal formés :",
            "de": "Einige XML-Dateien sind unlesbar oder fehlerhaft:",
        }[language]
        return f"{prefix} {paths}"
    for prefix, translation in MISSING_ITEM_TRANSLATIONS[language].items():
        if item.startswith(prefix):
            return translation
    return {
        "en": "Review this missing or uncertain item against the local evidence.",
        "fr": "Examiner cet élément manquant ou incertain à partir des preuves locales.",
        "de": "Diesen fehlenden oder unklaren Punkt anhand der lokalen Nachweise prüfen.",
    }[language]


def _localize_missing_items(items: Sequence[str], language: str) -> list[str]:
    return [_localize_missing_item(item, language) for item in items]


def _build_professional_questions(
    records: Sequence[FileRecord],
    missing_items: Sequence[str],
    language: str = "it",
) -> list[str]:
    categories = _category_map(records)
    questions = {
        "it": [
            "Il perimetro reddituale del cliente è completo rispetto ai documenti ricevuti?",
            "Ci sono documenti da escludere dal fascicolo perché non pertinenti all'anno o alla pratica?",
        ],
        "en": [
            "Is the client's income perimeter complete against the documents received?",
            "Should any documents be excluded because they do not relate to the target year or engagement?",
        ],
        "fr": [
            "Le périmètre des revenus du client est-il complet au regard des documents reçus ?",
            "Certains documents doivent-ils être exclus parce qu’ils ne concernent pas l’année ou la mission ?",
        ],
        "de": [
            "Ist der Einkommensumfang des Mandanten anhand der erhaltenen Unterlagen vollständig?",
            "Sind Dokumente auszuschließen, weil sie nicht zum Zieljahr oder Mandat gehören?",
        ],
    }[language].copy()
    if categories.get(CATEGORY_RICEVUTE_SANITARIE):
        questions.append(
            {
                "it": "Le spese sanitarie richiedono verifica su intestazione, tracciabilità e corrispondenza con la precompilata?",
                "en": "Do the medical expenses require checks of the holder, payment traceability, and consistency with the pre-filled return?",
                "fr": "Les frais médicaux exigent-ils une vérification du titulaire, de la traçabilité du paiement et de la déclaration préremplie ?",
                "de": "Müssen Gesundheitsausgaben hinsichtlich Inhaber, Zahlungsnachvollziehbarkeit und vorausgefüllter Erklärung geprüft werden?",
            }[language]
        )
    if categories.get(CATEGORY_AVVISI):
        questions.append(
            {
                "it": "L'avviso/comunicazione richiede una valutazione sostanziale, una risposta o recupero documentale ulteriore?",
                "en": "Does the notice require substantive assessment, a response, or further document retrieval?",
                "fr": "L’avis exige-t-il une analyse de fond, une réponse ou la collecte d’autres documents ?",
                "de": "Erfordert der Bescheid eine inhaltliche Prüfung, eine Antwort oder weitere Unterlagen?",
            }[language]
        )
    if missing_items:
        questions.append(
            {
                "it": "Quali mancanze devono essere richieste al cliente e quali possono essere risolte internamente dallo studio?",
                "en": "Which missing items should be requested from the client, and which can the firm resolve internally?",
                "fr": "Quels éléments manquants faut-il demander au client et lesquels le cabinet peut-il résoudre en interne ?",
                "de": "Welche fehlenden Punkte sind beim Mandanten anzufordern und welche kann die Kanzlei intern klären?",
            }[language]
        )
    return questions


def _write_markdown_list(
    output_path: Path,
    title: str,
    intro: str,
    items: Sequence[str],
    empty_text: str,
) -> Path:
    lines = [f"# {title}", "", intro, ""]
    if items:
        lines.extend(f"- {item}" for item in items)
    else:
        lines.append(empty_text)
    output_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return output_path


def _is_within(path: Path, parent: Path) -> bool:
    try:
        path.relative_to(parent)
    except ValueError:
        return False
    return True


def _protected_output_roots() -> tuple[Path, ...]:
    roots = [PLUGIN_ROOT.resolve()]
    for candidate in (SCRIPT_DIR, *SCRIPT_DIR.parents):
        if (candidate / ".git").exists():
            roots.append(candidate.resolve())
    return tuple(dict.fromkeys(roots))


def _validated_fresh_output_dir(value: Path) -> Path:
    """Resolve a new/empty output directory without traversing symlinks."""

    requested = value.expanduser().absolute()
    for component in (requested, *requested.parents):
        if component.is_symlink():
            raise ValueError(
                f"La cartella output non può attraversare link simbolici: {requested}"
            )
    resolved = requested.resolve(strict=False)
    if any(_is_within(resolved, root) for root in _protected_output_roots()):
        raise ValueError(
            "La cartella output deve essere esterna al repository e al pacchetto "
            f"del plugin: {resolved}"
        )
    if requested.exists():
        if not requested.is_dir():
            raise NotADirectoryError(f"Cartella output non valida: {requested}")
        if next(requested.iterdir(), None) is not None:
            raise FileExistsError(
                "La cartella output deve essere nuova o vuota; spostare il run "
                f"precedente prima di continuare: {requested}"
            )
    return resolved


def _load_template(name: str) -> Template:
    return Template((TEMPLATE_DIR / name).read_text(encoding="utf-8"))


def _write_memo(
    output_path: Path,
    client_name: str,
    target_year: int | None,
    records: Sequence[FileRecord],
    missing_items: Sequence[str],
    professional_questions: Sequence[str],
    client_questions: Sequence[str],
    duplicate_candidates: Sequence[DuplicateCandidate],
    xml_records: Sequence[InvoiceXmlRecord],
    language: str = "it",
) -> Path:
    categories = _category_map(records)
    category_lines = "\n".join(
        f"- {_category_label(category, language)}: {len(items)}"
        for category, items in sorted(categories.items(), key=lambda item: item[0])
    )
    duplicate_message = {
        "it": f"Duplicati potenziali: {len(duplicate_candidates)} file da verificare.",
        "en": f"Potential duplicates: {len(duplicate_candidates)} files to review.",
        "fr": f"Doublons potentiels : {len(duplicate_candidates)} fichiers à examiner.",
        "de": f"Mögliche Duplikate: {len(duplicate_candidates)} Dateien zu prüfen.",
    }[language]
    anomalies = [duplicate_message] if duplicate_candidates else []
    anomalies.extend(
        (
            f"`{record.relative_path}`: {', '.join(record.anomalies)}"
            if language == "it"
            else {
                "en": f"`{record.relative_path}`: formal XML anomaly; see the detailed anomaly report.",
                "fr": f"`{record.relative_path}` : anomalie XML formelle ; voir le rapport détaillé.",
                "de": f"`{record.relative_path}`: formale XML-Auffälligkeit; siehe Detailbericht.",
            }[language]
        )
        for record in xml_records
        if record.anomalies
    )
    if not anomalies:
        anomalies.append(
            {
                "it": "Nessuna anomalia formale evidente nei controlli automatici.",
                "en": "No obvious formal anomalies were found by the automated checks.",
                "fr": "Aucune anomalie formelle manifeste dans les contrôles automatiques.",
                "de": "Bei den automatischen Prüfungen wurden keine offensichtlichen formalen Auffälligkeiten gefunden.",
            }[language]
        )

    values = {
        "client_name": client_name,
        "target_year": str(
            target_year
            or {
                "it": "non indicato",
                "en": "not specified",
                "fr": "non indiquée",
                "de": "nicht angegeben",
            }[language]
        ),
        "file_count": str(len(records)),
        "category_lines": category_lines
        or {
            "it": "- Nessuna categoria individuata.",
            "en": "- No category identified.",
            "fr": "- Aucune catégorie identifiée.",
            "de": "- Keine Kategorie erkannt.",
        }[language],
        "missing_lines": "\n".join(f"- {item}" for item in missing_items)
        or f"- {_copy(language, 'missing_empty')}",
        "anomaly_lines": "\n".join(f"- {item}" for item in anomalies),
        "professional_question_lines": "\n".join(
            f"- {item}" for item in professional_questions
        ),
        "client_question_lines": "\n".join(f"- {item}" for item in client_questions),
    }
    if language == "it":
        text = _load_template("memo_istruttoria.md").substitute(**values)
    else:
        headings = {
            "en": (
                "Client file-preparation memo",
                "Client",
                "Year",
                "Documents received",
                "Files reviewed",
                "Missing or uncertain items",
                "Formal anomalies",
                "Questions for the firm",
                "Questions for the client",
                "Notes",
                "This memo is a working basis for client file preparation.",
            ),
            "fr": (
                "Note de préparation du dossier client",
                "Client",
                "Année",
                "Documents reçus",
                "Fichiers examinés",
                "Éléments manquants ou incertains",
                "Anomalies formelles",
                "Questions internes du cabinet",
                "Questions à adresser au client",
                "Notes",
                "Cette note constitue une base de travail pour préparer le dossier client.",
            ),
            "de": (
                "Arbeitsvermerk zur Mandantenakte",
                "Mandant",
                "Jahr",
                "Erhaltene Unterlagen",
                "Geprüfte Dateien",
                "Fehlende oder unklare Punkte",
                "Formale Auffälligkeiten",
                "Interne Fragen der Kanzlei",
                "Fragen an den Mandanten",
                "Hinweise",
                "Dieser Vermerk ist eine Arbeitsgrundlage für die Vorbereitung der Mandantenakte.",
            ),
        }[language]
        (
            title,
            client_label,
            year_label,
            documents_heading,
            files_label,
            missing_heading,
            anomaly_heading,
            professional_heading,
            client_heading,
            notes_heading,
            note,
        ) = headings
        text = (
            f"# {title} — {client_label} {client_name} — {year_label} {values['target_year']}\n\n"
            f"## {documents_heading}\n\n{files_label}: {values['file_count']}.\n\n{values['category_lines']}\n\n"
            f"## {missing_heading}\n\n{values['missing_lines']}\n\n"
            f"## {anomaly_heading}\n\n{values['anomaly_lines']}\n\n"
            f"## {professional_heading}\n\n{values['professional_question_lines']}\n\n"
            f"## {client_heading}\n\n{values['client_question_lines']}\n\n"
            f"## {notes_heading}\n\n{note}\n"
        )
    output_path.write_text(text, encoding="utf-8")
    return output_path


def _client_questions(
    missing_items: Sequence[str],
    language: str = "it",
) -> list[str]:
    request_keys: list[str] = []
    joined = " ".join(missing_items).lower()

    def add_once(key: str) -> None:
        if key not in request_keys:
            request_keys.append(key)

    if "non è stata individuata una cu" in joined:
        add_once("send_cu")
    if "presente una cu" in joined:
        add_once("confirm_other_cu")
    if (
        "redditi esteri" in joined
        or "locazioni" in joined
        or "attività autonoma" in joined
        or "partecipazioni" in joined
        or "perimetro reddituale" in joined
    ):
        add_once("confirm_other_income")
    if "mutuo" in joined:
        add_once("send_mortgage_interest")
    if "sanitar" in joined:
        add_once("confirm_medical")
    if "f24" in joined:
        add_once("confirm_f24")
    if "anno non coerente" in joined:
        add_once("confirm_other_years")
    if "non classificati" in joined:
        add_once("clarify_unclassified")
    if "xml" in joined and ("malformat" in joined or "non sono leggibili" in joined):
        add_once("resend_xml")
    if "pdf" in joined or "immagini" in joined or "ocr" in joined:
        add_once("send_readable_copy")

    translations = {
        "it": {
            "send_cu": "inviare la Certificazione Unica oppure confermare che non è pertinente per questa pratica;",
            "confirm_other_cu": "confermare che non vi siano altre CU o ulteriori documenti reddituali non ancora trasmessi;",
            "confirm_other_income": "confermare eventuali redditi esteri, locazioni, attività autonoma o partecipazioni non presenti nel fascicolo;",
            "send_mortgage_interest": "inviare la certificazione degli interessi passivi del mutuo;",
            "confirm_medical": "confermare se le spese sanitarie inviate sono complete;",
            "confirm_f24": "inviare eventuali F24 mancanti o confermare che quelli inviati sono completi;",
            "confirm_other_years": "confermare se i file riferiti ad anni diversi sono pertinenti alla pratica in corso;",
            "clarify_unclassified": "chiarire la natura dei documenti non classificati indicati dallo studio;",
            "resend_xml": "reinviare eventuali fatture XML non leggibili o malformate;",
            "send_readable_copy": "inviare una copia più leggibile dei documenti che risultano scansionati o non letti correttamente;",
        },
        "en": {
            "send_cu": "send the Certificazione Unica (CU), or confirm that it is not relevant to this engagement;",
            "confirm_other_cu": "confirm that there are no other CUs or income documents still to be provided;",
            "confirm_other_income": "confirm any foreign income, rental income, self-employment income, or participations not included in the file;",
            "send_mortgage_interest": "send the mortgage-interest certificate;",
            "confirm_medical": "confirm whether the medical-expense documents provided are complete;",
            "confirm_f24": "send any missing F24 forms, or confirm that those already provided are complete;",
            "confirm_other_years": "confirm whether files relating to other years are relevant to the current engagement;",
            "clarify_unclassified": "clarify the nature of the unclassified documents identified by the firm;",
            "resend_xml": "resend any unreadable or malformed XML invoices;",
            "send_readable_copy": "send a clearer copy of documents that are scanned or could not be read correctly;",
        },
        "fr": {
            "send_cu": "envoyer la Certificazione Unica (CU) ou confirmer qu’elle n’est pas pertinente pour cette mission ;",
            "confirm_other_cu": "confirmer qu’il n’existe pas d’autres CU ou justificatifs de revenus à transmettre ;",
            "confirm_other_income": "confirmer les éventuels revenus étrangers, loyers, activités indépendantes ou participations absents du dossier ;",
            "send_mortgage_interest": "envoyer l’attestation des intérêts hypothécaires ;",
            "confirm_medical": "confirmer que les justificatifs de frais médicaux transmis sont complets ;",
            "confirm_f24": "envoyer les éventuels formulaires F24 manquants ou confirmer que ceux transmis sont complets ;",
            "confirm_other_years": "confirmer si les fichiers d’autres années concernent la mission en cours ;",
            "clarify_unclassified": "préciser la nature des documents non classés signalés par le cabinet ;",
            "resend_xml": "renvoyer les factures XML illisibles ou mal formées ;",
            "send_readable_copy": "envoyer une copie plus lisible des documents numérisés ou mal lus ;",
        },
        "de": {
            "send_cu": "die Certificazione Unica (CU) senden oder bestätigen, dass sie für dieses Mandat nicht relevant ist;",
            "confirm_other_cu": "bestätigen, dass keine weiteren CU oder Einkommensunterlagen ausstehen;",
            "confirm_other_income": "ausländische Einkünfte, Mieten, selbständige Tätigkeiten oder Beteiligungen bestätigen, die nicht in der Akte enthalten sind;",
            "send_mortgage_interest": "die Hypothekenzinsbescheinigung senden;",
            "confirm_medical": "bestätigen, ob die eingereichten Gesundheitsbelege vollständig sind;",
            "confirm_f24": "fehlende F24-Formulare senden oder die Vollständigkeit der eingereichten Formulare bestätigen;",
            "confirm_other_years": "bestätigen, ob Dateien anderer Jahre für das aktuelle Mandat relevant sind;",
            "clarify_unclassified": "die Art der von der Kanzlei erkannten nicht klassifizierten Dokumente erläutern;",
            "resend_xml": "unlesbare oder fehlerhafte XML-Rechnungen erneut senden;",
            "send_readable_copy": "eine besser lesbare Kopie gescannter oder nicht korrekt gelesener Dokumente senden;",
        },
    }
    return [translations[language][key] for key in request_keys]


def _write_email(
    output_path: Path,
    client_name: str,
    questions: Sequence[str],
    language: str = "it",
) -> Path:
    if not questions:
        empty = {
            "it": "# Bozza email cliente\n\nNessuna richiesta cliente generata automaticamente dai controlli formali. Valutare internamente se inviare una comunicazione.\n",
            "en": "# Draft client email\n\nThe formal checks did not generate a client request. Decide internally whether a message is needed.\n",
            "fr": "# Projet d’e-mail au client\n\nLes contrôles formels n’ont généré aucune demande au client. Décider en interne si un message est nécessaire.\n",
            "de": "# Entwurf der Mandanten-E-Mail\n\nAus den formalen Prüfungen ergab sich keine Anfrage an den Mandanten. Intern entscheiden, ob eine Nachricht erforderlich ist.\n",
        }[language]
        output_path.write_text(empty, encoding="utf-8")
        return output_path
    if language == "it":
        text = _load_template("email_documenti_mancanti.md").substitute(
            client_name=client_name,
            question_lines="\n".join(f"- {item}" for item in questions),
        )
    else:
        framing = {
            "en": (
                "Subject: Documents and clarifications needed to complete file preparation",
                "Hello",
                "We have completed an initial review of the material received. To complete file preparation, please:",
                "We will use the documents received to complete the firm's client file.",
                "Kind regards",
            ),
            "fr": (
                "Objet : Documents et précisions nécessaires pour compléter le dossier",
                "Bonjour",
                "Nous avons effectué un premier examen des éléments reçus. Pour compléter le dossier, merci de :",
                "Nous utiliserons les documents reçus pour compléter le dossier du cabinet.",
                "Cordialement",
            ),
            "de": (
                "Betreff: Unterlagen und Angaben zur Vervollständigung der Akte",
                "Guten Tag",
                "Wir haben die erhaltenen Unterlagen zunächst geprüft. Zur Vervollständigung der Akte bitten wir Sie:",
                "Wir verwenden die erhaltenen Unterlagen zur Vervollständigung der Mandantenakte.",
                "Freundliche Grüße",
            ),
        }[language]
        subject, greeting, intro, closing, signoff = framing
        text = (
            f"{subject}\n\n{greeting} {client_name},\n\n{intro}\n\n"
            + "\n".join(f"- {item}" for item in questions)
            + f"\n\n{closing}\n\n{signoff}\n"
        )
    output_path.write_text(text, encoding="utf-8")
    return output_path


DATE_RE = re.compile(r"\b(?:\d{1,2}[/-]\d{1,2}[/-]\d{2,4}|20[0-4]\d-\d{2}-\d{2})\b")
AMOUNT_RE = re.compile(r"(?:€\s*)?\b\d{1,3}(?:\.\d{3})*,\d{2}\b")
PROTOCOL_RE = re.compile(r"\b(?:protocollo|prot\.?)\s*[: n.]?\s*([A-Z0-9/-]{5,})", re.I)


def _read_preview(path: Path, limit: int = 50000) -> str:
    try:
        return path.read_text(encoding="utf-8", errors="ignore")[:limit]
    except OSError:
        return ""


def _write_notice_outputs(
    records: Sequence[FileRecord],
    root: Path,
    output_dir: Path,
    evidence_texts: dict[str, str],
    *,
    language: str = "it",
) -> int:
    notice_records = [
        record for record in records if record.category == CATEGORY_AVVISI
    ]
    notice_dir = output_dir / "avviso"
    notice_dir.mkdir(parents=True, exist_ok=True)

    rows: list[dict[str, str]] = []
    copy = {
        "it": {
            "title": "Avviso / comunicazione - scheda di prima lettura",
            "intro": "Evidenzia elementi pratici per la revisione.",
            "empty": "Nessun avviso o comunicazione individuato nel fascicolo.",
            "dates": "Date individuate",
            "amounts": "Importi individuati",
            "protocol": "Protocollo",
            "verify": "da verificare",
            "documents": "Documenti da recuperare: da indicare dopo revisione del fascicolo.",
        },
        "en": {
            "title": "Notice / communication - initial reading sheet",
            "intro": "Highlights practical elements for the firm’s review.",
            "empty": "No notice or communication was identified in the client file.",
            "dates": "Dates identified",
            "amounts": "Amounts identified",
            "protocol": "Reference",
            "verify": "to verify",
            "documents": "Documents to obtain: define after reviewing the client file.",
        },
        "fr": {
            "title": "Avis / communication - fiche de première lecture",
            "intro": "Met en évidence les éléments pratiques à examiner par le cabinet.",
            "empty": "Aucun avis ni aucune communication n’a été identifié dans le dossier.",
            "dates": "Dates relevées",
            "amounts": "Montants relevés",
            "protocol": "Référence",
            "verify": "à vérifier",
            "documents": "Documents à obtenir : à définir après examen du dossier.",
        },
        "de": {
            "title": "Bescheid / Mitteilung - Erstprüfungsblatt",
            "intro": "Hebt praktische Punkte für die Prüfung durch die Kanzlei hervor.",
            "empty": "In der Mandantenakte wurde kein Bescheid und keine Mitteilung erkannt.",
            "dates": "Erkannte Daten",
            "amounts": "Erkannte Beträge",
            "protocol": "Aktenzeichen",
            "verify": "zu prüfen",
            "documents": "Noch einzuholende Unterlagen: nach Prüfung der Akte festlegen.",
        },
    }[language]
    memo_lines = [f"# {copy['title']}", "", copy["intro"], ""]

    if not notice_records:
        memo_lines.append(copy["empty"])
    for record in notice_records:
        path = root / record.relative_path
        preview = evidence_texts.get(record.relative_path) or _read_preview(path)
        dates = DATE_RE.findall(preview + " " + record.file_name)
        amounts = AMOUNT_RE.findall(preview + " " + record.file_name)
        protocols = PROTOCOL_RE.findall(preview + " " + record.file_name)

        memo_lines.extend(
            [
                f"## `{record.relative_path}`",
                "",
                f"- {copy['dates']}: {', '.join(dates) if dates else copy['verify']}",
                f"- {copy['amounts']}: {', '.join(amounts) if amounts else copy['verify']}",
                f"- {copy['protocol']}: {', '.join(protocols) if protocols else copy['verify']}",
                f"- {copy['documents']}",
                "",
            ]
        )
        rows.extend(
            {"relative_path": record.relative_path, "type": "date", "value": value}
            for value in dates
        )
        rows.extend(
            {"relative_path": record.relative_path, "type": "amount", "value": value}
            for value in amounts
        )
        rows.extend(
            {"relative_path": record.relative_path, "type": "protocol", "value": value}
            for value in protocols
        )

    (notice_dir / "avviso_intake_memo.md").write_text(
        "\n".join(memo_lines) + "\n",
        encoding="utf-8",
    )
    with (notice_dir / "deadlines_and_amounts.csv").open(
        "w",
        newline="",
        encoding="utf-8",
    ) as handle:
        writer = csv.DictWriter(handle, fieldnames=["relative_path", "type", "value"])
        writer.writeheader()
        writer.writerows(rows)

    return len(notice_records)


def _write_combined_anomalies(
    output_path: Path,
    records: Sequence[FileRecord],
    duplicate_candidates: Sequence[DuplicateCandidate],
    xml_records: Sequence[InvoiceXmlRecord],
    *,
    language: str = "it",
) -> Path:
    copy = {
        "it": {
            "title": "Anomalie formali",
            "empty": "Nessuna anomalia formale evidente nei controlli automatici.",
            "inventory": "Note da inventario",
            "duplicates": "Duplicati potenziali",
            "xml": "E-fattura XML",
        },
        "en": {
            "title": "Formal anomalies",
            "empty": "The automated checks found no evident formal anomaly.",
            "inventory": "Inventory notes",
            "duplicates": "Potential duplicates",
            "xml": "Electronic-invoice XML",
        },
        "fr": {
            "title": "Anomalies formelles",
            "empty": "Les contrôles automatiques n’ont relevé aucune anomalie formelle manifeste.",
            "inventory": "Notes d’inventaire",
            "duplicates": "Doublons potentiels",
            "xml": "Facture électronique XML",
        },
        "de": {
            "title": "Formale Anomalien",
            "empty": "Die automatischen Prüfungen ergaben keine offensichtliche formale Anomalie.",
            "inventory": "Hinweise aus dem Inventar",
            "duplicates": "Mögliche Duplikate",
            "xml": "E-Rechnungs-XML",
        },
    }[language]
    lines = [f"# {copy['title']}", ""]
    year_notes = [record for record in records if record.notes]
    if (
        not year_notes
        and not duplicate_candidates
        and not any(r.anomalies for r in xml_records)
    ):
        lines.append(copy["empty"])
    if year_notes:
        lines.extend([f"## {copy['inventory']}", ""])
        for record in year_notes:
            notes = [_inventory_note_label(value, language) for value in record.notes]
            lines.append(f"- `{record.relative_path}`: {', '.join(notes)}")
        lines.append("")
    if duplicate_candidates:
        lines.extend([f"## {copy['duplicates']}", ""])
        for candidate in duplicate_candidates:
            lines.append(
                f"- `{candidate.relative_path}` — "
                f"{_duplicate_type_label(candidate.duplicate_type, language)} "
                f"({candidate.group_key})"
            )
        lines.append("")
    xml_with_anomalies = [record for record in xml_records if record.anomalies]
    if xml_with_anomalies:
        lines.extend([f"## {copy['xml']}", ""])
        for record in xml_with_anomalies:
            localized = [
                localize_formal_anomaly(value, language) for value in record.anomalies
            ]
            lines.append(f"- `{record.relative_path}`: {', '.join(localized)}")
    output_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return output_path


def _write_studio_synthesis(
    output_path: Path,
    client_name: str,
    target_year: int | None,
    records: Sequence[FileRecord],
    document_evidence: Sequence[DocumentEvidence],
    structured_fields: Sequence[FiscalField],
    missing_items: Sequence[str],
    professional_questions: Sequence[str],
    client_questions: Sequence[str],
    duplicate_candidates: Sequence[DuplicateCandidate],
    xml_records: Sequence[InvoiceXmlRecord],
    language: str = "it",
) -> Path:
    categories = _category_map(records)
    readable = [item for item in document_evidence if item.readable]
    unreadable = [item for item in document_evidence if not item.readable]
    structured_by_kind: dict[str, int] = {}
    for field in structured_fields:
        structured_by_kind[field.document_kind] = (
            structured_by_kind.get(field.document_kind, 0) + 1
        )
    xml_anomalies = [
        f"`{record.relative_path}`: {', '.join(record.anomalies)}"
        for record in xml_records
        if record.anomalies
    ]
    if language != "it":
        labels = {
            "en": {
                "title": "File-preparation brief for the firm",
                "year_missing": "year not specified",
                "intro": "This brief is based on locally inspected files and extracted data. It supports the firm's operational review.",
                "summary": "File summary",
                "files": "Files reviewed",
                "categories": "Categories identified",
                "readable": "Documents with extracted text",
                "unreadable": "Documents not read reliably",
                "fields": "Structured fiscal fields extracted",
                "xml": "Electronic XML invoices reviewed",
                "duplicates": "Potential duplicates",
                "found": "What was found",
                "none": "No files identified.",
                "missing": "Missing or uncertain items",
                "anomalies": "Formal anomalies",
                "no_anomaly": "No obvious formal anomalies were found by the automated checks.",
                "data": "Structured fiscal data",
                "field_word": "fields",
                "detail": "Details are in `08_dati_fiscali_strutturati.md`.",
                "no_fields": "No structured fiscal fields were extracted from readable documents.",
                "client_questions": "Questions for the client",
                "firm_questions": "Points for the firm",
                "limits": "Reading limitations",
                "limit_intro": "Some documents require OCR or manual review because they were not read reliably:",
                "read_ok": "All attempted textual documents produced usable text.",
            },
            "fr": {
                "title": "Fiche de préparation pour le cabinet",
                "year_missing": "année non indiquée",
                "intro": "Cette fiche repose sur les fichiers examinés localement et les données extraites. Elle soutient la revue opérationnelle du cabinet.",
                "summary": "Synthèse du dossier",
                "files": "Fichiers examinés",
                "categories": "Catégories identifiées",
                "readable": "Documents avec texte extrait",
                "unreadable": "Documents non lus de manière fiable",
                "fields": "Champs fiscaux structurés extraits",
                "xml": "Factures électroniques XML examinées",
                "duplicates": "Doublons potentiels",
                "found": "Éléments trouvés",
                "none": "Aucun fichier identifié.",
                "missing": "Éléments manquants ou incertains",
                "anomalies": "Anomalies formelles",
                "no_anomaly": "Aucune anomalie formelle manifeste dans les contrôles automatiques.",
                "data": "Données fiscales structurées",
                "field_word": "champs",
                "detail": "Le détail figure dans `08_dati_fiscali_strutturati.md`.",
                "no_fields": "Aucun champ fiscal structuré extrait des documents lisibles.",
                "client_questions": "Questions à adresser au client",
                "firm_questions": "Points pour le cabinet",
                "limits": "Limites de lecture",
                "limit_intro": "Certains documents nécessitent un OCR ou une revue manuelle car ils n’ont pas été lus de manière fiable :",
                "read_ok": "Tous les documents textuels tentés ont produit un texte exploitable.",
            },
            "de": {
                "title": "Arbeitsübersicht für die Kanzlei",
                "year_missing": "Jahr nicht angegeben",
                "intro": "Diese Übersicht beruht auf lokal geprüften Dateien und extrahierten Daten. Sie unterstützt die operative Prüfung der Kanzlei.",
                "summary": "Zusammenfassung der Akte",
                "files": "Geprüfte Dateien",
                "categories": "Erkannte Kategorien",
                "readable": "Dokumente mit extrahiertem Text",
                "unreadable": "Nicht zuverlässig gelesene Dokumente",
                "fields": "Extrahierte strukturierte Steuerfelder",
                "xml": "Geprüfte elektronische XML-Rechnungen",
                "duplicates": "Mögliche Duplikate",
                "found": "Gefundene Unterlagen",
                "none": "Keine Dateien erkannt.",
                "missing": "Fehlende oder unklare Punkte",
                "anomalies": "Formale Auffälligkeiten",
                "no_anomaly": "Bei den automatischen Prüfungen wurden keine offensichtlichen formalen Auffälligkeiten gefunden.",
                "data": "Strukturierte Steuerdaten",
                "field_word": "Felder",
                "detail": "Details stehen in `08_dati_fiscali_strutturati.md`.",
                "no_fields": "Aus lesbaren Dokumenten wurden keine strukturierten Steuerfelder extrahiert.",
                "client_questions": "Fragen an den Mandanten",
                "firm_questions": "Punkte für die Kanzlei",
                "limits": "Grenzen der Auslesung",
                "limit_intro": "Einige Dokumente benötigen OCR oder manuelle Prüfung, weil sie nicht zuverlässig gelesen wurden:",
                "read_ok": "Alle versuchten Textdokumente lieferten verwertbaren Text.",
            },
        }[language]
        localized_lines = [
            f"# {labels['title']} — {client_name} — {target_year or labels['year_missing']}",
            "",
            labels["intro"],
            "",
            f"## {labels['summary']}",
            "",
            f"- {labels['files']}: {len(records)}",
            f"- {labels['categories']}: {len(categories)}",
            f"- {labels['readable']}: {len(readable)}",
            f"- {labels['unreadable']}: {len(unreadable)}",
            f"- {labels['fields']}: {len(structured_fields)}",
            f"- {labels['xml']}: {len(xml_records)}",
            f"- {labels['duplicates']}: {len(duplicate_candidates)}",
            "",
            f"## {labels['found']}",
            "",
        ]
        if categories:
            localized_lines.extend(
                f"- {_category_label(category, language)}: {len(items)}"
                for category, items in sorted(categories.items())
            )
        else:
            localized_lines.append(f"- {labels['none']}")
        localized_lines.extend(["", f"## {labels['missing']}", ""])
        localized_lines.extend(f"- {item}" for item in missing_items)
        if not missing_items:
            localized_lines.append(f"- {_copy(language, 'missing_empty')}")
        localized_lines.extend(["", f"## {labels['anomalies']}", ""])
        if duplicate_candidates:
            localized_lines.append(
                f"- {labels['duplicates']}: {len(duplicate_candidates)}"
            )
        if xml_anomalies:
            localized_lines.extend(
                {
                    "en": f"- `{record.relative_path}`: formal XML anomaly; see the detailed report.",
                    "fr": f"- `{record.relative_path}` : anomalie XML formelle ; voir le rapport détaillé.",
                    "de": f"- `{record.relative_path}`: formale XML-Auffälligkeit; siehe Detailbericht.",
                }[language]
                for record in xml_records
                if record.anomalies
            )
        if not duplicate_candidates and not xml_anomalies:
            localized_lines.append(f"- {labels['no_anomaly']}")
        localized_lines.extend(["", f"## {labels['data']}", ""])
        if structured_by_kind:
            localized_lines.extend(
                f"- {kind}: {count} {labels['field_word']}"
                for kind, count in sorted(structured_by_kind.items())
            )
            localized_lines.append(f"- {labels['detail']}")
        else:
            localized_lines.append(f"- {labels['no_fields']}")
        localized_lines.extend(["", f"## {labels['client_questions']}", ""])
        localized_lines.extend(f"- {item}" for item in client_questions)
        localized_lines.extend(["", f"## {labels['firm_questions']}", ""])
        localized_lines.extend(f"- {item}" for item in professional_questions)
        localized_lines.extend(["", f"## {labels['limits']}", ""])
        if unreadable:
            localized_lines.append(f"- {labels['limit_intro']}")
            localized_lines.extend(
                f"  - `{item.relative_path}` ({item.extraction_method})"
                for item in unreadable[:20]
            )
        else:
            localized_lines.append(f"- {labels['read_ok']}")
        output_path.write_text(
            "\n".join(localized_lines) + "\n",
            encoding="utf-8",
        )
        return output_path
    lines = [
        f"# Scheda per lo studio — {client_name} — {target_year or 'anno non indicato'}",
        "",
        "Questa scheda è basata sui file e sui dati estratti localmente. "
        "Serve per istruttoria operativa dello studio.",
        "",
        "## Sintesi del fascicolo",
        "",
        f"- File analizzati: {len(records)}",
        f"- Categorie individuate: {len(categories)}",
        f"- Documenti con testo estratto: {len(readable)}",
        f"- Documenti non letti in modo affidabile: {len(unreadable)}",
        f"- Campi fiscali strutturati estratti: {len(structured_fields)}",
        f"- E-fatture XML analizzate: {len(xml_records)}",
        f"- Duplicati potenziali: {len(duplicate_candidates)}",
        "",
        "## Cosa è stato trovato",
        "",
    ]
    if categories:
        lines.extend(
            f"- {category}: {len(items)}"
            for category, items in sorted(categories.items(), key=lambda item: item[0])
        )
    else:
        lines.append("- Nessun file individuato.")
    lines.extend(["", "## Punti mancanti o incerti", ""])
    lines.extend(f"- {item}" for item in missing_items)
    if not missing_items:
        lines.append("- Nessun elemento mancante evidente nei controlli automatici.")
    lines.extend(["", "## Anomalie formali", ""])
    if duplicate_candidates:
        lines.append(f"- Duplicati potenziali tra file: {len(duplicate_candidates)}")
    if xml_anomalies:
        lines.extend(f"- {item}" for item in xml_anomalies)
    if not duplicate_candidates and not xml_anomalies:
        lines.append("- Nessuna anomalia formale evidente nei controlli automatici.")
    lines.extend(["", "## Dati fiscali strutturati", ""])
    if structured_by_kind:
        lines.extend(
            f"- {kind}: {count} campi"
            for kind, count in sorted(structured_by_kind.items())
        )
        lines.append("- Dettaglio in `08_dati_fiscali_strutturati.md`.")
    else:
        lines.append(
            "- Nessun campo fiscale strutturato estratto dai documenti leggibili."
        )
    lines.extend(["", "## Domande da fare al cliente", ""])
    lines.extend(f"- {item}" for item in client_questions)
    lines.extend(["", "## Punti per lo studio", ""])
    lines.extend(f"- {item}" for item in professional_questions)
    lines.extend(["", "## Limiti della lettura", ""])
    if unreadable:
        lines.append(
            "- Alcuni documenti richiedono OCR o verifica manuale perché non sono "
            "stati letti in modo affidabile:"
        )
        lines.extend(
            f"  - `{item.relative_path}` ({item.extraction_method})"
            for item in unreadable[:20]
        )
    else:
        lines.append("- I documenti testuali tentati sono stati letti con esito utile.")
    output_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return output_path


def build_file_preparation_outputs(
    folder: Path | str,
    target_year: int | None = None,
    output_dir: Path | str | None = None,
    enable_ocr: bool = True,
    ocr_lang: str | None = None,
    *,
    jurisdiction: str = "italy",
    language: str = "it",
    include_review_previews: bool = False,
    max_pages: int = 50,
) -> BuildResult:
    """Run the prototype first-intake workflow on a customer folder."""

    root = Path(folder).expanduser().resolve()
    # Folder existence and non-empty evidence are mechanical preconditions. Validate
    # them before creating outputs so a typo cannot become a successful empty run.
    if not root.exists() or not root.is_dir():
        raise NotADirectoryError(f"Cartella non valida: {root}")
    jurisdiction = jurisdiction.strip().lower()
    language = language.strip().lower()
    if jurisdiction not in SUPPORTED_JURISDICTIONS:
        raise ValueError(
            f"Giurisdizione non supportata: {jurisdiction}. "
            f"Valori ammessi: {', '.join(SUPPORTED_JURISDICTIONS)}"
        )
    if language not in SUPPORTED_LANGUAGES:
        raise ValueError(
            f"Lingua non supportata: {language}. "
            f"Valori ammessi: {', '.join(SUPPORTED_LANGUAGES)}"
        )
    if max_pages < 1:
        raise ValueError("max_pages deve essere almeno 1")
    effective_ocr_lang = ocr_lang or OCR_LANGUAGE_BY_LANGUAGE[language]
    requested_out_dir = (
        Path(output_dir)
        if output_dir
        else root.parent / "output" / f"client-file-preparation-{secrets.token_hex(8)}"
    )
    out_dir = _validated_fresh_output_dir(requested_out_dir)
    records = scan_folder(
        root,
        target_year=target_year,
        output_dir=out_dir,
        jurisdiction=jurisdiction,
        language=language,
    )
    if not records:
        raise ValueError(f"La cartella cliente non contiene file da analizzare: {root}")
    out_dir.mkdir(parents=True, exist_ok=True)
    out_dir.chmod(0o700)
    client_name = _infer_client_name(root, target_year)
    require_ocr = any(
        record.extension.lower() in {".pdf", ".png", ".jpg", ".jpeg", ".tif", ".tiff"}
        for record in records
    )
    missing_dependency_count, _ = _write_environment_report(
        out_dir / "00_environment_check.md",
        require_ocr=require_ocr and enable_ocr,
        language=language,
    )
    run_intake = write_run_intake(
        out_dir,
        root,
        target_year=target_year,
        client_name=client_name,
        records=records,
        missing_dependency_count=missing_dependency_count,
        require_ocr=require_ocr,
        enable_ocr=enable_ocr,
        ocr_lang=effective_ocr_lang,
        jurisdiction=jurisdiction,
        language=language,
    )
    write_index_markdown(
        records,
        out_dir / "00_fascicolo_index.md",
        root,
        target_year,
        language=language,
    )
    write_inventory_csv(records, out_dir / "01_document_inventory.csv")
    document_evidence = extract_documents(
        records,
        root,
        out_dir / "extracted",
        enable_ocr=enable_ocr,
        lang=effective_ocr_lang,
        max_pages=max_pages,
        language=language,
    )
    evidence_texts = _evidence_text_map(document_evidence, out_dir / "extracted")
    structured_fields = parse_structured_fiscal_fields(
        document_evidence,
        out_dir / "extracted",
    )
    write_fiscal_fields_csv(
        structured_fields,
        out_dir / "extracted" / "structured_fiscal_fields.csv",
    )
    write_fiscal_fields_jsonl(
        structured_fields,
        out_dir / "extracted" / "structured_fiscal_fields.jsonl",
    )
    write_fiscal_fields_summary(
        structured_fields,
        out_dir / "08_dati_fiscali_strutturati.md",
        language=language,
    )

    paths = [
        root / record.relative_path
        for record in records
        if "collegamento simbolico non seguito" not in record.notes
    ]
    duplicate_candidates = find_duplicate_candidates(paths, root)
    write_file_duplicate_csv(duplicate_candidates, out_dir / "duplicate_candidates.csv")

    xml_paths = (
        [
            root / record.relative_path
            for record in records
            if record.category == CATEGORY_FATTURE_XML
        ]
        if jurisdiction in {"italy", "mixed"}
        else []
    )
    xml_records = parse_xml_files(xml_paths, root, target_year=target_year)
    fatture_dir = out_dir / "fatture"
    write_summary_csv(xml_records, fatture_dir / "fatture_summary.csv")
    write_summary_jsonl(xml_records, out_dir / "extracted" / "fatture_xml.jsonl")
    write_xml_duplicate_csv(xml_records, fatture_dir / "duplicate_candidates.csv")
    write_formal_anomalies_markdown(
        xml_records,
        fatture_dir / "formal_anomalies.md",
        language=language,
    )

    raw_missing_items = _build_missing_items(
        records,
        duplicate_candidates,
        xml_records,
        document_evidence,
        evidence_texts,
        out_dir,
        target_year,
        jurisdiction=jurisdiction,
    )
    client_questions = _client_questions(raw_missing_items, language=language)
    missing_items = _localize_missing_items(raw_missing_items, language)
    professional_questions = _build_professional_questions(
        records,
        missing_items,
        language=language,
    )
    _write_markdown_list(
        out_dir / "02_documenti_mancanti_o_incerti.md",
        _copy(language, "missing_title"),
        _copy(language, "missing_intro"),
        missing_items,
        _copy(language, "missing_empty"),
    )
    _write_markdown_list(
        out_dir / "03_domande_interne_studio.md",
        _copy(language, "questions_title"),
        _copy(language, "questions_intro"),
        professional_questions,
        _copy(language, "questions_empty"),
    )

    _write_email(
        out_dir / "04_bozza_email_cliente.md",
        client_name,
        client_questions,
        language=language,
    )
    _write_combined_anomalies(
        out_dir / "05_anomalie_formali.md",
        records,
        duplicate_candidates,
        xml_records,
        language=language,
    )
    _write_memo(
        out_dir / "06_memo_istruttoria.md",
        client_name,
        target_year,
        records,
        missing_items,
        professional_questions,
        client_questions,
        duplicate_candidates,
        xml_records,
        language=language,
    )
    notice_count = _write_notice_outputs(
        records,
        root,
        out_dir,
        evidence_texts,
        language=language,
    )
    _write_studio_synthesis(
        out_dir / "07_scheda_codex_per_studio.md",
        client_name,
        target_year,
        records,
        document_evidence,
        structured_fields,
        missing_items,
        professional_questions,
        client_questions,
        duplicate_candidates,
        xml_records,
        language=language,
    )
    verify_source_snapshot(records, root)
    write_review_session_artifacts(
        out_dir,
        root,
        run_id=run_intake.run_id,
        run_intake_path=run_intake.path,
        target_year=target_year,
        client_name=client_name,
        records=records,
        document_evidence=document_evidence,
        structured_fields=structured_fields,
        missing_items=missing_items,
        professional_questions=professional_questions,
        client_questions=client_questions,
        duplicate_candidates=duplicate_candidates,
        xml_records=xml_records,
        jurisdiction=jurisdiction,
        language=language,
        include_previews=include_review_previews,
    )

    return BuildResult(
        output_dir=out_dir,
        file_count=len(records),
        category_count=len(_category_map(records)),
        missing_count=len(missing_items),
        duplicate_count=len(duplicate_candidates),
        xml_count=len(xml_records),
        notice_count=notice_count,
        extracted_count=len([item for item in document_evidence if item.readable]),
        unreadable_count=len([item for item in document_evidence if not item.readable]),
        missing_dependency_count=missing_dependency_count,
        structured_field_count=len(structured_fields),
    )


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Genera l'istruttoria clienti a partire da un fascicolo cliente."
    )
    parser.add_argument("folder", type=Path, help="Cartella cliente.")
    parser.add_argument("--year", type=int, default=None, help="Anno fiscale target.")
    parser.add_argument(
        "--out",
        type=Path,
        default=None,
        help=(
            "Cartella output. Default: cartella sorella "
            "output/client-file-preparation-<id casuale>"
        ),
    )
    parser.add_argument("--no-ocr", action="store_true", help="Disabilita OCR locale.")
    parser.add_argument("--ocr-lang", default=None, help="Lingua OCR Paddle.")
    parser.add_argument(
        "--jurisdiction",
        type=str.lower,
        choices=SUPPORTED_JURISDICTIONS,
        default="italy",
        help="Giurisdizione del fascicolo.",
    )
    parser.add_argument(
        "--language",
        choices=SUPPORTED_LANGUAGES,
        default="it",
        help="Lingua di lavoro del fascicolo.",
    )
    parser.add_argument(
        "--include-review-previews",
        action="store_true",
        help="Include estratti testuali nel payload di revisione locale.",
    )
    parser.add_argument(
        "--max-pages",
        type=int,
        default=50,
        help="Pagine massime lette o sottoposte a OCR per PDF.",
    )
    return parser.parse_args()


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    args = _parse_args()
    result = build_file_preparation_outputs(
        args.folder,
        args.year,
        args.out,
        enable_ocr=not args.no_ocr,
        ocr_lang=args.ocr_lang,
        jurisdiction=args.jurisdiction,
        language=args.language,
        include_review_previews=args.include_review_previews,
        max_pages=args.max_pages,
    )
    LOGGER.info("Output creati in %s", result.output_dir)
    LOGGER.info(
        "Sintesi: %s file, %s categorie, %s mancanze/incertezze, %s duplicati, %s XML, %s avvisi, %s documenti estratti, %s non leggibili, %s campi fiscali strutturati.",
        result.file_count,
        result.category_count,
        result.missing_count,
        result.duplicate_count,
        result.xml_count,
        result.notice_count,
        result.extracted_count,
        result.unreadable_count,
        result.structured_field_count,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
