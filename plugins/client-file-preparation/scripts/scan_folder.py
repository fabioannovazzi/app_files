from __future__ import annotations

import argparse
import csv
import logging
import re
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
    "classify_file",
    "extract_years",
    "scan_folder",
    "write_index_markdown",
    "write_inventory_csv",
]

LOGGER = logging.getLogger(__name__)

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


def classify_file(
    path: Path, root: Path, target_year: int | None = None
) -> tuple[str, str, tuple[str, ...]]:
    """Classify a file by path, extension, and conservative filename rules."""

    relative = path.relative_to(root)
    searchable = normalize_text(f"{relative.parent} {path.stem} {path.suffix}")
    extension = path.suffix.lower()
    notes: list[str] = []

    if extension == ".xml":
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
) -> list[FileRecord]:
    """Scan a customer folder and return classified file records."""

    root_path = Path(root).expanduser().resolve()
    if not root_path.exists() or not root_path.is_dir():
        raise NotADirectoryError(f"Cartella non valida: {root_path}")

    output_path = Path(output_dir).expanduser().resolve() if output_dir else None
    records: list[FileRecord] = []

    for path in sorted(root_path.rglob("*")):
        if not path.is_file() or _should_skip(path, root_path, output_path):
            continue

        category, confidence, notes = classify_file(path, root_path, target_year)
        stat = path.stat()
        modified = datetime.fromtimestamp(stat.st_mtime).replace(microsecond=0)
        records.append(
            FileRecord(
                relative_path=path.relative_to(root_path).as_posix(),
                file_name=path.name,
                extension=path.suffix.lower(),
                size_bytes=stat.st_size,
                modified_iso=modified.isoformat(),
                category=category,
                confidence=confidence,
                years=extract_years(path.relative_to(root_path).as_posix()),
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
) -> Path:
    """Write a readable markdown index for the customer folder."""

    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    root_path = Path(root)
    year_text = str(target_year) if target_year is not None else "non indicato"
    counts = _category_counts(records)

    lines: list[str] = [
        "# Indice fascicolo",
        "",
        f"- Cartella: `{root_path}`",
        f"- Anno target: {year_text}",
        f"- File analizzati: {len(records)}",
        "",
        "## Categorie individuate",
        "",
    ]
    if counts:
        lines.extend(f"- {category}: {count}" for category, count in counts.items())
    else:
        lines.append("- Nessun file trovato.")

    lines.extend(["", "## Dettaglio file", ""])
    for record in records:
        note = f" — {', '.join(record.notes)}" if record.notes else ""
        lines.append(
            f"- `{record.relative_path}` — {record.category} "
            f"({record.confidence}){note}"
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
        help="Cartella output. Default: <folder>/out",
    )
    return parser.parse_args()


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    args = _parse_args()
    out_dir = args.out or args.folder / "out"
    records = scan_folder(args.folder, target_year=args.year, output_dir=out_dir)
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
