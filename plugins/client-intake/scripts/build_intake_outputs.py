from __future__ import annotations

import argparse
import csv
import logging
import re
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
    CATEGORY_CU,
    CATEGORY_F24,
    CATEGORY_FATTURE_XML,
    CATEGORY_MUTUO,
    CATEGORY_NON_CLASSIFICATI,
    CATEGORY_REDDITI_PF,
    CATEGORY_RICEVUTE_SANITARIE,
    FileRecord,
    scan_folder,
    write_index_markdown,
    write_inventory_csv,
)

# isort: on

__all__ = ["BuildResult", "build_intake_outputs"]

LOGGER = logging.getLogger(__name__)
PLUGIN_ROOT = SCRIPT_DIR.parent
TEMPLATE_DIR = PLUGIN_ROOT / "templates"


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
) -> tuple[int, bool]:
    available, missing = check_dependencies(require_ocr=require_ocr)
    lines = [
        "# Controllo ambiente",
        "",
        f"- OCR richiesto: {'sì' if require_ocr else 'no'}",
        f"- Dipendenze disponibili: {len(available)}",
        f"- Dipendenze mancanti: {len(missing)}",
        "",
    ]
    if available:
        lines.extend(["## Disponibili", ""])
        lines.extend(
            f"- {dependency.label}: {dependency.required_for}"
            for dependency in available
        )
        lines.append("")
    if missing:
        lines.extend(["## Mancanti", ""])
        lines.extend(
            f"- {dependency.label}: {dependency.required_for}" for dependency in missing
        )
        lines.extend(["", "## Comandi suggeriti", ""])
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
        lines.append("Ambiente pronto per le funzioni richieste.")
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
) -> list[str]:
    categories = _category_map(records)
    items: list[str] = []

    if _has_italian_tax_context(categories, evidence_texts):
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

    else:
        if categories:
            items.append(
                "Cartella non italiana rilevata: controllare completezza documentale "
                "rispetto alla giurisdizione indicata nel run."
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


def _build_professional_questions(
    records: Sequence[FileRecord],
    missing_items: Sequence[str],
) -> list[str]:
    categories = _category_map(records)
    questions = [
        "Il perimetro reddituale del cliente è completo rispetto ai documenti ricevuti?",
        "Ci sono documenti da escludere dal fascicolo perché non pertinenti all'anno o alla pratica?",
    ]
    if categories.get(CATEGORY_RICEVUTE_SANITARIE):
        questions.append(
            "Le spese sanitarie richiedono verifica su intestazione, tracciabilità "
            "e corrispondenza con la precompilata?"
        )
    if categories.get(CATEGORY_AVVISI):
        questions.append(
            "L'avviso/comunicazione richiede una valutazione sostanziale, una risposta "
            "o recupero documentale ulteriore?"
        )
    if missing_items:
        questions.append(
            "Quali mancanze devono essere richieste al cliente e quali possono essere "
            "risolte internamente dallo studio?"
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


def _load_template(name: str) -> Template:
    return Template((TEMPLATE_DIR / name).read_text(encoding="utf-8"))


def _write_memo(
    output_path: Path,
    client_name: str,
    target_year: int | None,
    records: Sequence[FileRecord],
    missing_items: Sequence[str],
    professional_questions: Sequence[str],
    duplicate_candidates: Sequence[DuplicateCandidate],
    xml_records: Sequence[InvoiceXmlRecord],
) -> Path:
    categories = _category_map(records)
    category_lines = "\n".join(
        f"- {category}: {len(items)}"
        for category, items in sorted(categories.items(), key=lambda item: item[0])
    )
    anomalies = (
        [f"Duplicati potenziali: {len(duplicate_candidates)} file da verificare."]
        if duplicate_candidates
        else []
    )
    anomalies.extend(
        f"`{record.relative_path}`: {', '.join(record.anomalies)}"
        for record in xml_records
        if record.anomalies
    )
    if not anomalies:
        anomalies.append("Nessuna anomalia formale evidente nei controlli automatici.")

    template = _load_template("memo_istruttoria.md")
    output_path.write_text(
        template.substitute(
            client_name=client_name,
            target_year=str(target_year or "non indicato"),
            file_count=str(len(records)),
            category_lines=category_lines or "- Nessuna categoria individuata.",
            missing_lines="\n".join(f"- {item}" for item in missing_items)
            or "- Nessun elemento mancante evidente nei controlli automatici.",
            anomaly_lines="\n".join(f"- {item}" for item in anomalies),
            professional_question_lines="\n".join(
                f"- {item}" for item in professional_questions
            ),
            client_question_lines="\n".join(
                f"- {item}" for item in _client_questions(missing_items)
            ),
        ),
        encoding="utf-8",
    )
    return output_path


def _client_questions(missing_items: Sequence[str]) -> list[str]:
    requests: list[str] = []
    joined = " ".join(missing_items).lower()

    def add_once(text: str) -> None:
        if text not in requests:
            requests.append(text)

    if "non è stata individuata una cu" in joined:
        add_once(
            "inviare la Certificazione Unica oppure confermare che non è pertinente "
            "per questa pratica;"
        )
    if "presente una cu" in joined:
        add_once(
            "confermare che non vi siano altre CU o ulteriori documenti reddituali "
            "non ancora trasmessi;"
        )
    if (
        "redditi esteri" in joined
        or "locazioni" in joined
        or "attività autonoma" in joined
        or "partecipazioni" in joined
        or "perimetro reddituale" in joined
    ):
        add_once(
            "confermare eventuali redditi esteri, locazioni, attività autonoma o "
            "partecipazioni non presenti nel fascicolo;"
        )
    if "mutuo" in joined:
        add_once("inviare la certificazione degli interessi passivi del mutuo;")
    if "sanitar" in joined:
        add_once("confermare se le spese sanitarie inviate sono complete;")
    if "f24" in joined:
        add_once(
            "inviare eventuali F24 mancanti o confermare che quelli inviati sono "
            "completi;"
        )
    if "anno non coerente" in joined:
        add_once(
            "confermare se i file riferiti ad anni diversi sono pertinenti alla "
            "pratica in corso;"
        )
    if "non classificati" in joined:
        add_once(
            "chiarire la natura dei documenti non classificati indicati dallo studio;"
        )
    if "xml" in joined and ("malformat" in joined or "non sono leggibili" in joined):
        add_once("reinviare eventuali fatture XML non leggibili o malformate;")
    if "pdf" in joined or "immagini" in joined or "ocr" in joined:
        add_once(
            "inviare una copia più leggibile dei documenti che risultano scansionati "
            "o non letti correttamente;"
        )

    return requests


def _write_email(
    output_path: Path,
    client_name: str,
    missing_items: Sequence[str],
) -> Path:
    template = _load_template("email_documenti_mancanti.md")
    questions = _client_questions(missing_items)
    if not questions:
        output_path.write_text(
            "# Bozza email cliente\n\n"
            "Nessuna richiesta cliente generata automaticamente dai controlli "
            "formali. Valutare internamente se inviare una comunicazione.\n",
            encoding="utf-8",
        )
        return output_path
    output_path.write_text(
        template.substitute(
            client_name=client_name,
            question_lines="\n".join(f"- {item}" for item in questions),
        ),
        encoding="utf-8",
    )
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
) -> int:
    notice_records = [
        record for record in records if record.category == CATEGORY_AVVISI
    ]
    notice_dir = output_dir / "avviso"
    notice_dir.mkdir(parents=True, exist_ok=True)

    rows: list[dict[str, str]] = []
    memo_lines = [
        "# Avviso / comunicazione - scheda di prima lettura",
        "",
        "Evidenzia elementi pratici per la revisione.",
        "",
    ]

    if not notice_records:
        memo_lines.append("Nessun avviso o comunicazione individuato nel fascicolo.")
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
                f"- Date individuate: {', '.join(dates) if dates else 'da verificare'}",
                f"- Importi individuati: {', '.join(amounts) if amounts else 'da verificare'}",
                f"- Protocollo: {', '.join(protocols) if protocols else 'da verificare'}",
                "- Documenti da recuperare: da indicare dopo revisione del fascicolo.",
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
) -> Path:
    lines = ["# Anomalie formali", ""]
    year_notes = [record for record in records if record.notes]
    if (
        not year_notes
        and not duplicate_candidates
        and not any(r.anomalies for r in xml_records)
    ):
        lines.append("Nessuna anomalia formale evidente nei controlli automatici.")
    if year_notes:
        lines.extend(["## Note da inventario", ""])
        for record in year_notes:
            lines.append(f"- `{record.relative_path}`: {', '.join(record.notes)}")
        lines.append("")
    if duplicate_candidates:
        lines.extend(["## Duplicati potenziali", ""])
        for candidate in duplicate_candidates:
            lines.append(
                f"- `{candidate.relative_path}` — {candidate.duplicate_type} "
                f"({candidate.group_key})"
            )
        lines.append("")
    xml_with_anomalies = [record for record in xml_records if record.anomalies]
    if xml_with_anomalies:
        lines.extend(["## E-fattura XML", ""])
        for record in xml_with_anomalies:
            lines.append(f"- `{record.relative_path}`: {', '.join(record.anomalies)}")
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
    duplicate_candidates: Sequence[DuplicateCandidate],
    xml_records: Sequence[InvoiceXmlRecord],
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
    lines.extend(f"- {item}" for item in _client_questions(missing_items))
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


def build_intake_outputs(
    folder: Path | str,
    target_year: int | None = None,
    output_dir: Path | str | None = None,
    enable_ocr: bool = True,
    ocr_lang: str = "it",
) -> BuildResult:
    """Run the prototype first-intake workflow on a customer folder."""

    root = Path(folder).expanduser().resolve()
    out_dir = Path(output_dir).expanduser().resolve() if output_dir else root / "out"
    out_dir.mkdir(parents=True, exist_ok=True)

    records = scan_folder(root, target_year=target_year, output_dir=out_dir)
    client_name = _infer_client_name(root, target_year)
    require_ocr = any(
        record.extension.lower() in {".pdf", ".png", ".jpg", ".jpeg", ".tif", ".tiff"}
        for record in records
    )
    missing_dependency_count, _ = _write_environment_report(
        out_dir / "00_environment_check.md",
        require_ocr=require_ocr and enable_ocr,
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
        ocr_lang=ocr_lang,
    )
    write_index_markdown(records, out_dir / "00_fascicolo_index.md", root, target_year)
    write_inventory_csv(records, out_dir / "01_document_inventory.csv")
    document_evidence = extract_documents(
        records,
        root,
        out_dir / "extracted",
        enable_ocr=enable_ocr,
        lang=ocr_lang,
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
    )

    paths = [root / record.relative_path for record in records]
    duplicate_candidates = find_duplicate_candidates(paths, root)
    write_file_duplicate_csv(duplicate_candidates, out_dir / "duplicate_candidates.csv")

    xml_paths = [
        root / record.relative_path
        for record in records
        if record.category == CATEGORY_FATTURE_XML or record.extension == ".xml"
    ]
    xml_records = parse_xml_files(xml_paths, root, target_year=target_year)
    fatture_dir = out_dir / "fatture"
    write_summary_csv(xml_records, fatture_dir / "fatture_summary.csv")
    write_summary_jsonl(xml_records, out_dir / "extracted" / "fatture_xml.jsonl")
    write_xml_duplicate_csv(xml_records, fatture_dir / "duplicate_candidates.csv")
    write_formal_anomalies_markdown(xml_records, fatture_dir / "formal_anomalies.md")

    missing_items = _build_missing_items(
        records,
        duplicate_candidates,
        xml_records,
        document_evidence,
        evidence_texts,
        out_dir,
        target_year,
    )
    professional_questions = _build_professional_questions(records, missing_items)
    client_questions = _client_questions(missing_items)
    _write_markdown_list(
        out_dir / "02_documenti_mancanti_o_incerti.md",
        "Documenti mancanti o incerti",
        "Elenco operativo costruito da classificazione, parsing e testo estratto.",
        missing_items,
        "Nessuna mancanza evidente nei controlli automatici.",
    )
    _write_markdown_list(
        out_dir / "03_domande_interne_studio.md",
        "Domande interne dello studio",
        "Punti operativi emersi dalla classificazione e dagli estratti disponibili.",
        professional_questions,
        "Nessuna domanda generata automaticamente.",
    )

    _write_email(out_dir / "04_bozza_email_cliente.md", client_name, missing_items)
    _write_combined_anomalies(
        out_dir / "05_anomalie_formali.md",
        records,
        duplicate_candidates,
        xml_records,
    )
    _write_memo(
        out_dir / "06_memo_istruttoria.md",
        client_name,
        target_year,
        records,
        missing_items,
        professional_questions,
        duplicate_candidates,
        xml_records,
    )
    notice_count = _write_notice_outputs(records, root, out_dir, evidence_texts)
    _write_studio_synthesis(
        out_dir / "07_scheda_codex_per_studio.md",
        client_name,
        target_year,
        records,
        document_evidence,
        structured_fields,
        missing_items,
        professional_questions,
        duplicate_candidates,
        xml_records,
    )
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
        help="Cartella output. Default: <folder>/out",
    )
    parser.add_argument("--no-ocr", action="store_true", help="Disabilita OCR locale.")
    parser.add_argument("--ocr-lang", default="it", help="Lingua OCR Paddle.")
    return parser.parse_args()


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    args = _parse_args()
    result = build_intake_outputs(
        args.folder,
        args.year,
        args.out,
        enable_ocr=not args.no_ocr,
        ocr_lang=args.ocr_lang,
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
