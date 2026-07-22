from __future__ import annotations

import argparse
import csv
import hashlib
import logging
import re
import secrets
import unicodedata
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Iterable, Sequence

__all__ = [
    "CATEGORY_730",
    "CATEGORY_AVVISI",
    "CATEGORY_CH_BANK_TAX",
    "CATEGORY_CH_GE_TAX",
    "CATEGORY_CH_SALARY_CERTIFICATE",
    "CATEGORY_CH_TAX_ASSESSMENT",
    "CATEGORY_CH_TAX_RETURN",
    "CATEGORY_CH_ZH_TAX",
    "CATEGORY_CONTRATTI",
    "CATEGORY_CU",
    "CATEGORY_F24",
    "CATEGORY_FATTURE_XML",
    "CATEGORY_MUTUO",
    "CATEGORY_NON_CLASSIFICATI",
    "CATEGORY_REDDITI_PF",
    "CATEGORY_RICEVUTE_SANITARIE",
    "CATEGORY_UK_BANK_TAX",
    "CATEGORY_UK_HMRC_NOTICE",
    "CATEGORY_UK_PAYSLIP",
    "CATEGORY_UK_SELF_ASSESSMENT",
    "CATEGORY_UK_YEAR_END_PAYROLL",
    "FileRecord",
    "MAX_SOURCE_ENTRIES",
    "MAX_SOURCE_FILE_BYTES",
    "MAX_SOURCE_FILES",
    "MAX_SOURCE_TOTAL_BYTES",
    "classify_file",
    "extract_years",
    "scan_folder",
    "verify_source_snapshot",
    "write_index_markdown",
    "write_inventory_csv",
]

LOGGER = logging.getLogger(__name__)
MAX_SOURCE_ENTRIES = 20_000
MAX_SOURCE_FILES = 5_000
MAX_SOURCE_FILE_BYTES = 256 * 1024 * 1024
MAX_SOURCE_TOTAL_BYTES = 2 * 1024 * 1024 * 1024

CATEGORY_CU = "CU"
CATEGORY_730 = "730 / precompilata"
CATEGORY_REDDITI_PF = "Redditi PF"
CATEGORY_F24 = "F24"
CATEGORY_FATTURE_XML = "fatture elettroniche XML"
CATEGORY_RICEVUTE_SANITARIE = "ricevute sanitarie"
CATEGORY_MUTUO = "mutuo"
CATEGORY_AFFITTO = "affitto / locazione"
CATEGORY_ASSICURAZIONI = "assicurazioni"
CATEGORY_PREVIDENZA = "previdenza"
CATEGORY_AVVISI = "avvisi / comunicazioni"
CATEGORY_CONTRATTI = "contratti"
CATEGORY_CH_GE_TAX = "Geneva tax documents"
CATEGORY_CH_ZH_TAX = "Zurich tax documents"
CATEGORY_CH_TAX_RETURN = "CH tax return / déclaration fiscale / Steuererklärung"
CATEGORY_CH_TAX_ASSESSMENT = "CH tax assessment / taxation"
CATEGORY_CH_SALARY_CERTIFICATE = "CH salary certificate / Lohnausweis"
CATEGORY_CH_BANK_TAX = "CH bank and withholding tax certificates"
CATEGORY_UK_YEAR_END_PAYROLL = "UK P60 / P45 / P11D"
CATEGORY_UK_PAYSLIP = "UK payslip"
CATEGORY_UK_SELF_ASSESSMENT = "UK Self Assessment"
CATEGORY_UK_HMRC_NOTICE = "UK HMRC notices"
CATEGORY_UK_BANK_TAX = "UK bank and investment tax certificates"
CATEGORY_NON_CLASSIFICATI = "documenti non classificati"

YEAR_RE = re.compile(r"(?<!\d)(20[0-4]\d)(?!\d)")


@dataclass(frozen=True)
class FileRecord:
    """One document discovered in a customer folder."""

    relative_path: str
    file_name: str
    extension: str
    size_bytes: int
    modified_iso: str
    sha256: str
    category: str
    confidence: str
    years: tuple[int, ...]
    notes: tuple[str, ...]

    def as_row(self) -> dict[str, str | int]:
        """Return a CSV-friendly representation."""

        return {
            "relative_path": self.relative_path,
            "file_name": self.file_name,
            "extension": self.extension,
            "size_bytes": self.size_bytes,
            "modified_iso": self.modified_iso,
            "sha256": self.sha256,
            "category": self.category,
            "confidence": self.confidence,
            "years": ";".join(str(year) for year in self.years),
            "notes": " | ".join(self.notes),
        }


def normalize_text(value: str) -> str:
    """Normalize text for filename heuristics."""

    without_accents = unicodedata.normalize("NFKD", value).encode("ascii", "ignore")
    normalized = without_accents.decode("ascii").lower()
    return re.sub(r"[^a-z0-9]+", " ", normalized).strip()


def extract_years(value: str) -> tuple[int, ...]:
    """Extract plausible fiscal years from a path or filename."""

    return tuple(sorted({int(match) for match in YEAR_RE.findall(value)}))


def _matches(text: str, patterns: Sequence[str]) -> bool:
    return any(re.search(pattern, text) for pattern in patterns)


def _looks_like_fatturapa_xml(path: Path) -> bool:
    """Recognize the FatturaElettronica root in a bounded local prefix."""

    if path.is_symlink() or not path.is_file():
        return False
    try:
        with path.open("rb") as handle:
            prefix = handle.read(128 * 1024)
    except OSError:
        return False
    return bool(
        re.search(
            rb"<(?:[A-Za-z_][A-Za-z0-9_.-]*:)?FatturaElettronica(?:\s|>)",
            prefix,
            flags=re.IGNORECASE,
        )
    )


def _sha256_regular_file(path: Path) -> str:
    """Hash one regular source file without loading it into memory."""

    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def classify_file(
    path: Path,
    root: Path,
    target_year: int | None = None,
    *,
    jurisdiction: str = "italy",
) -> tuple[str, str, tuple[str, ...]]:
    """Classify a file by path, extension, and conservative filename rules."""

    relative = path.relative_to(root)
    searchable = normalize_text(f"{relative.parent} {path.stem} {path.suffix}")
    extension = path.suffix.lower()
    notes: list[str] = []

    if (
        extension == ".xml"
        and jurisdiction in {"italy", "mixed"}
        and _looks_like_fatturapa_xml(path)
    ):
        category = CATEGORY_FATTURE_XML
        confidence = "media"
    elif _matches(
        searchable,
        [
            r"\bgeneve\b",
            r"\bgeneva\b",
            r"\bgenf\b",
            r"\bafc\b",
            r"administration fiscale cantonale",
            r"etat de geneve",
            r"\bge\b.*\bimpot",
        ],
    ):
        category = CATEGORY_CH_GE_TAX
        confidence = "media"
    elif _matches(
        searchable,
        [
            r"\bzurich\b",
            r"\bzuerich\b",
            r"\bzh\b.*\bsteuer",
            r"kantonales steueramt",
            r"steueramt zurich",
            r"steueramt zuerich",
        ],
    ):
        category = CATEGORY_CH_ZH_TAX
        confidence = "media"
    elif _matches(
        searchable,
        [
            r"certificat de salaire",
            r"certificato di salario",
            r"\blohnausweis\b",
            r"salary certificate",
        ],
    ):
        category = CATEGORY_CH_SALARY_CERTIFICATE
        confidence = "alta"
    elif _matches(
        searchable,
        [
            r"declaration d impot",
            r"declaration fiscale",
            r"declaration tax",
            r"\bsteuererklarung\b",
            r"\bsteuererkl[aä]rung\b",
            r"dichiarazione fiscale",
        ],
    ):
        category = CATEGORY_CH_TAX_RETURN
        confidence = "media"
    elif _matches(
        searchable,
        [
            r"avis de taxation",
            r"bordereau",
            r"\bveranlagung",
            r"einschatzungsentscheid",
            r"\btax assessment\b",
        ],
    ):
        category = CATEGORY_CH_TAX_ASSESSMENT
        confidence = "media"
    elif _matches(
        searchable,
        [
            r"attestation fiscale",
            r"releve fiscal",
            r"releve de portefeuille",
            r"steuerbescheinigung",
            r"\bzinsausweis\b",
            r"verrechnungssteuer",
        ],
    ):
        category = CATEGORY_CH_BANK_TAX
        confidence = "media"
    elif _matches(searchable, [r"\bp60\b", r"\bp45\b", r"\bp11d\b"]):
        category = CATEGORY_UK_YEAR_END_PAYROLL
        confidence = "alta"
    elif _matches(searchable, [r"\bpayslip\b", r"pay slip", r"payroll slip"]):
        category = CATEGORY_UK_PAYSLIP
        confidence = "media"
    elif _matches(
        searchable,
        [
            r"self assessment",
            r"\bsa100\b",
            r"\bsa302\b",
            r"\butr\b",
            r"\buk tax return\b",
        ],
    ):
        category = CATEGORY_UK_SELF_ASSESSMENT
        confidence = "media"
    elif _matches(
        searchable,
        [
            r"\bhmrc\b",
            r"paye coding notice",
            r"tax code notice",
            r"simple assessment",
            r"notice to file",
        ],
    ):
        category = CATEGORY_UK_HMRC_NOTICE
        confidence = "media"
    elif _matches(
        searchable,
        [
            r"interest certificate",
            r"dividend voucher",
            r"consolidated tax voucher",
            r"tax certificate",
        ],
    ):
        category = CATEGORY_UK_BANK_TAX
        confidence = "media"
    elif _matches(searchable, [r"\bcu\b", r"certificazione unica", r"cud"]):
        category = CATEGORY_CU
        confidence = "alta"
    elif _matches(searchable, [r"\b730\b", r"precompilata"]):
        category = CATEGORY_730
        confidence = "alta"
    elif _matches(searchable, [r"redditi", r"\bpf\b", r"unico"]):
        category = CATEGORY_REDDITI_PF
        confidence = "media"
    elif _matches(searchable, [r"\bf24\b", r"delega"]):
        category = CATEGORY_F24
        confidence = "alta"
    elif _matches(searchable, [r"sanitar", r"medic", r"farmac", r"scontrin"]):
        category = CATEGORY_RICEVUTE_SANITARIE
        confidence = "media"
    elif _matches(searchable, [r"mutuo", r"interessi passivi", r"interess"]):
        category = CATEGORY_MUTUO
        confidence = "media"
    elif _matches(searchable, [r"affitto", r"locazion", r"canone"]):
        category = CATEGORY_AFFITTO
        confidence = "media"
    elif _matches(searchable, [r"assicuraz", r"polizza"]):
        category = CATEGORY_ASSICURAZIONI
        confidence = "media"
    elif _matches(searchable, [r"previd", r"inps", r"cassa"]):
        category = CATEGORY_PREVIDENZA
        confidence = "media"
    elif _matches(searchable, [r"avviso", r"agenzia", r"comunicaz", r"cartella"]):
        category = CATEGORY_AVVISI
        confidence = "media"
    elif _matches(searchable, [r"contratto", r"scrittura privata"]):
        category = CATEGORY_CONTRATTI
        confidence = "media"
    else:
        category = CATEGORY_NON_CLASSIFICATI
        confidence = "bassa"
        notes.append("classificazione non certa")

    years = extract_years(str(relative))
    if target_year is not None and years and target_year not in years:
        notes.append(f"anno non coerente con target {target_year}")

    if extension in {".jpg", ".jpeg", ".png", ".heic"}:
        notes.append("immagine: possibile ricevuta o documento scansionato")
    if extension == ".xml" and category != CATEGORY_FATTURE_XML:
        notes.append("XML generico: struttura FatturaPA non individuata")

    return category, confidence, tuple(notes)


def _should_skip(path: Path, root: Path, output_dir: Path | None) -> bool:
    if any(part in {".git", "__pycache__", ".DS_Store"} for part in path.parts):
        return True
    if output_dir is not None:
        try:
            path.relative_to(output_dir)
        except ValueError:
            return False
        return True
    return False


def scan_folder(
    root: Path | str,
    target_year: int | None = None,
    output_dir: Path | str | None = None,
    *,
    jurisdiction: str = "italy",
    language: str = "it",
) -> list[FileRecord]:
    """Scan a customer folder and return classified file records."""

    root_path = Path(root).expanduser().resolve()
    if not root_path.exists() or not root_path.is_dir():
        raise NotADirectoryError(f"Cartella non valida: {root_path}")

    output_path = Path(output_dir).expanduser().resolve() if output_dir else None
    records: list[FileRecord] = []
    inspected_entry_count = 0
    regular_source_bytes = 0
    error_copy = {
        "it": {
            "entries": "La cartella cliente supera il limite di elementi ispezionabili",
            "files": "La cartella cliente supera il limite di file",
            "file_size": "Il file sorgente supera il limite di dimensione",
            "total_size": "I file sorgente superano il limite complessivo di dimensione",
        },
        "en": {
            "entries": "The client folder exceeds the inspected-entry limit",
            "files": "The client folder exceeds the file-count limit",
            "file_size": "The source file exceeds the per-file size limit",
            "total_size": "The source files exceed the total-size limit",
        },
        "fr": {
            "entries": "Le dossier client dépasse la limite d’éléments inspectés",
            "files": "Le dossier client dépasse la limite de fichiers",
            "file_size": "Le fichier source dépasse la limite de taille par fichier",
            "total_size": "Les fichiers source dépassent la limite de taille totale",
        },
        "de": {
            "entries": "Der Mandantenordner überschreitet die Grenze der geprüften Einträge",
            "files": "Der Mandantenordner überschreitet die Dateianzahlgrenze",
            "file_size": "Die Quelldatei überschreitet die Größenbegrenzung pro Datei",
            "total_size": "Die Quelldateien überschreiten die Gesamtgrößenbegrenzung",
        },
        "es": {
            "entries": "La carpeta del cliente supera el límite de elementos inspeccionables",
            "files": "La carpeta del cliente supera el límite de archivos",
            "file_size": "El archivo fuente supera el límite de tamaño por archivo",
            "total_size": "Los archivos fuente superan el límite de tamaño total",
        },
    }.get(language)
    if error_copy is None:
        raise ValueError(f"Unsupported language: {language}")

    for path in sorted(root_path.rglob("*")):
        inspected_entry_count += 1
        if inspected_entry_count > MAX_SOURCE_ENTRIES:
            raise ValueError(f"{error_copy['entries']}: {MAX_SOURCE_ENTRIES}")
        if _should_skip(path, root_path, output_path):
            continue

        relative = path.relative_to(root_path)
        cursor = root_path
        contains_symlink = False
        for part in relative.parts:
            cursor /= part
            if cursor.is_symlink():
                contains_symlink = True
                break
        if not contains_symlink and not path.is_file():
            continue

        category, confidence, notes = classify_file(
            path,
            root_path,
            target_year,
            jurisdiction=jurisdiction,
        )
        stat = path.lstat() if contains_symlink else path.stat()
        if contains_symlink:
            category = CATEGORY_NON_CLASSIFICATI
            confidence = "bassa"
            notes = (*notes, "collegamento simbolico non seguito")
        if len(records) >= MAX_SOURCE_FILES:
            raise ValueError(f"{error_copy['files']}: {MAX_SOURCE_FILES}")
        if not contains_symlink:
            if stat.st_size > MAX_SOURCE_FILE_BYTES:
                raise ValueError(
                    f"{error_copy['file_size']}: {relative.as_posix()} "
                    f"({stat.st_size} > {MAX_SOURCE_FILE_BYTES} byte)"
                )
            regular_source_bytes += stat.st_size
            if regular_source_bytes > MAX_SOURCE_TOTAL_BYTES:
                raise ValueError(
                    f"{error_copy['total_size']}: "
                    f"{regular_source_bytes} > {MAX_SOURCE_TOTAL_BYTES} byte"
                )
        modified = datetime.fromtimestamp(stat.st_mtime).replace(microsecond=0)
        source_hash = "" if contains_symlink else _sha256_regular_file(path)
        records.append(
            FileRecord(
                relative_path=relative.as_posix(),
                file_name=path.name,
                extension=path.suffix.lower(),
                size_bytes=stat.st_size,
                modified_iso=modified.isoformat(),
                sha256=source_hash,
                category=category,
                confidence=confidence,
                years=extract_years(relative.as_posix()),
                notes=notes,
            )
        )

    return records


def write_inventory_csv(records: Iterable[FileRecord], output_path: Path | str) -> Path:
    """Write a CSV inventory for the scanned folder."""

    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    rows = [record.as_row() for record in records]
    fieldnames = [
        "relative_path",
        "file_name",
        "extension",
        "size_bytes",
        "modified_iso",
        "sha256",
        "category",
        "confidence",
        "years",
        "notes",
    ]
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)
    return path


def verify_source_snapshot(records: Sequence[FileRecord], root: Path | str) -> None:
    """Fail if a source changed type or content after the initial scan."""

    root_path = Path(root).expanduser().resolve()
    for record in records:
        source_path = root_path / record.relative_path
        cursor = root_path
        contains_symlink = False
        for part in Path(record.relative_path).parts:
            cursor /= part
            if cursor.is_symlink():
                contains_symlink = True
                if not record.sha256:
                    break
                raise RuntimeError(
                    f"Il file sorgente è diventato un link simbolico durante il run: {record.relative_path}"
                )
        if not record.sha256:
            if not contains_symlink:
                raise RuntimeError(
                    "Il collegamento simbolico sorgente è cambiato tipo durante "
                    f"il run: {record.relative_path}"
                )
            continue
        if not source_path.is_file():
            raise RuntimeError(
                f"Il file sorgente non è più disponibile durante il run: {record.relative_path}"
            )
        if source_path.stat().st_size != record.size_bytes:
            raise RuntimeError(
                f"Il file sorgente è cambiato durante il run: {record.relative_path}"
            )
        if _sha256_regular_file(source_path) != record.sha256:
            raise RuntimeError(
                f"Il file sorgente è cambiato durante il run: {record.relative_path}"
            )


def _category_counts(records: Sequence[FileRecord]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for record in records:
        counts[record.category] = counts.get(record.category, 0) + 1
    return dict(sorted(counts.items(), key=lambda item: item[0].lower()))


def write_index_markdown(
    records: Sequence[FileRecord],
    output_path: Path | str,
    root: Path | str,
    target_year: int | None = None,
    *,
    language: str = "it",
) -> Path:
    """Write a readable markdown index for the customer folder."""

    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    root_path = Path(root)
    labels = {
        "it": {
            "title": "Indice fascicolo",
            "folder": "Cartella",
            "year": "Anno target",
            "year_missing": "non indicato",
            "files": "File analizzati",
            "categories": "Categorie individuate",
            "none": "Nessun file trovato.",
            "detail": "Dettaglio file",
        },
        "en": {
            "title": "Client file index",
            "folder": "Local folder",
            "year": "Target year",
            "year_missing": "not specified",
            "files": "Files reviewed",
            "categories": "Categories identified",
            "none": "No files found.",
            "detail": "File details",
        },
        "fr": {
            "title": "Index du dossier client",
            "folder": "Dossier local",
            "year": "Année cible",
            "year_missing": "non indiquée",
            "files": "Fichiers examinés",
            "categories": "Catégories identifiées",
            "none": "Aucun fichier trouvé.",
            "detail": "Détail des fichiers",
        },
        "de": {
            "title": "Index der Mandantenakte",
            "folder": "Lokaler Ordner",
            "year": "Zieljahr",
            "year_missing": "nicht angegeben",
            "files": "Geprüfte Dateien",
            "categories": "Erkannte Kategorien",
            "none": "Keine Dateien gefunden.",
            "detail": "Dateidetails",
        },
        "es": {
            "title": "Índice del expediente del cliente",
            "folder": "Carpeta local",
            "year": "Año objetivo",
            "year_missing": "no especificado",
            "files": "Archivos revisados",
            "categories": "Categorías identificadas",
            "none": "No se encontraron archivos.",
            "detail": "Detalle de archivos",
        },
    }[language]
    category_labels = {
        "en": {
            CATEGORY_FATTURE_XML: "electronic invoices (XML)",
            CATEGORY_RICEVUTE_SANITARIE: "medical receipts",
            CATEGORY_MUTUO: "mortgage",
            CATEGORY_AVVISI: "notices / communications",
            CATEGORY_CONTRATTI: "contracts",
            CATEGORY_NON_CLASSIFICATI: "unclassified documents",
        },
        "fr": {
            CATEGORY_FATTURE_XML: "factures électroniques XML",
            CATEGORY_RICEVUTE_SANITARIE: "reçus médicaux",
            CATEGORY_MUTUO: "prêt hypothécaire",
            CATEGORY_AVVISI: "avis / communications",
            CATEGORY_CONTRATTI: "contrats",
            CATEGORY_NON_CLASSIFICATI: "documents non classés",
        },
        "de": {
            CATEGORY_FATTURE_XML: "elektronische Rechnungen (XML)",
            CATEGORY_RICEVUTE_SANITARIE: "Gesundheitsbelege",
            CATEGORY_MUTUO: "Hypothek",
            CATEGORY_AVVISI: "Bescheide / Mitteilungen",
            CATEGORY_CONTRATTI: "Verträge",
            CATEGORY_NON_CLASSIFICATI: "nicht klassifizierte Dokumente",
        },
        "es": {
            CATEGORY_FATTURE_XML: "facturas electrónicas XML",
            CATEGORY_RICEVUTE_SANITARIE: "justificantes médicos",
            CATEGORY_MUTUO: "hipoteca",
            CATEGORY_AVVISI: "avisos / comunicaciones",
            CATEGORY_CONTRATTI: "contratos",
            CATEGORY_NON_CLASSIFICATI: "documentos sin clasificar",
        },
    }.get(language, {})
    year_text = str(target_year) if target_year is not None else labels["year_missing"]
    counts = _category_counts(records)

    lines: list[str] = [
        f"# {labels['title']}",
        "",
        f"- {labels['folder']}: `{root_path}`",
        f"- {labels['year']}: {year_text}",
        f"- {labels['files']}: {len(records)}",
        "",
        f"## {labels['categories']}",
        "",
    ]
    if counts:
        lines.extend(
            f"- {category_labels.get(category, category)}: {count}"
            for category, count in counts.items()
        )
    else:
        lines.append(f"- {labels['none']}")

    lines.extend(["", f"## {labels['detail']}", ""])
    confidence_labels = {
        "it": {"alta": "alta", "media": "media", "bassa": "bassa"},
        "en": {"alta": "high", "media": "medium", "bassa": "low"},
        "fr": {"alta": "élevée", "media": "moyenne", "bassa": "faible"},
        "de": {"alta": "hoch", "media": "mittel", "bassa": "niedrig"},
        "es": {"alta": "alta", "media": "media", "bassa": "baja"},
    }[language]
    for record in records:
        localized_notes: list[str] = []
        for note_value in record.notes:
            if note_value == "classificazione non certa":
                localized_notes.append(
                    {
                        "it": note_value,
                        "en": "classification uncertain",
                        "fr": "classification incertaine",
                        "de": "Klassifizierung unklar",
                        "es": "clasificación incierta",
                    }[language]
                )
            elif note_value.startswith("anno non coerente"):
                localized_notes.append(
                    {
                        "it": note_value,
                        "en": f"year differs from target {target_year}",
                        "fr": f"année différente de la cible {target_year}",
                        "de": f"Jahr weicht vom Zieljahr {target_year} ab",
                        "es": f"el año difiere del objetivo {target_year}",
                    }[language]
                )
            elif note_value.startswith("immagine"):
                localized_notes.append(
                    {
                        "it": note_value,
                        "en": "image: possible receipt or scanned document",
                        "fr": "image : reçu possible ou document numérisé",
                        "de": "Bild: möglicher Beleg oder gescanntes Dokument",
                        "es": "imagen: posible justificante o documento escaneado",
                    }[language]
                )
            else:
                localized_notes.append(note_value)
        note = f" — {', '.join(localized_notes)}" if localized_notes else ""
        lines.append(
            f"- `{record.relative_path}` — {category_labels.get(record.category, record.category)} "
            f"({confidence_labels.get(record.confidence, record.confidence)}){note}"
        )

    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Scansiona una cartella cliente e produce indice e inventario CSV."
    )
    parser.add_argument("folder", type=Path, help="Cartella cliente da analizzare.")
    parser.add_argument("--year", type=int, default=None, help="Anno fiscale target.")
    parser.add_argument(
        "--out",
        type=Path,
        default=None,
        help="Cartella output. Default: sibling output/client-file-preparation-<id>.",
    )
    parser.add_argument(
        "--jurisdiction",
        choices=("italy", "geneva", "zurich", "uk", "mixed"),
        default="italy",
        help="Giurisdizione usata per classificare i file XML.",
    )
    return parser.parse_args()


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    args = _parse_args()
    out_dir = (
        args.out
        or args.folder.parent
        / "output"
        / f"client-file-preparation-{secrets.token_hex(8)}"
    )
    records = scan_folder(
        args.folder,
        target_year=args.year,
        output_dir=out_dir,
        jurisdiction=args.jurisdiction,
    )
    write_inventory_csv(records, out_dir / "01_document_inventory.csv")
    write_index_markdown(
        records,
        out_dir / "00_fascicolo_index.md",
        args.folder,
        target_year=args.year,
    )
    LOGGER.info("Analizzati %s file. Output in %s", len(records), out_dir)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
