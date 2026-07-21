from __future__ import annotations

import argparse
import csv
import importlib.util
import json
import logging
import re
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Iterable, Sequence

from scan_folder import FileRecord

__all__ = [
    "DocumentEvidence",
    "extract_documents",
    "write_documents_jsonl",
    "write_extraction_inventory_csv",
    "write_extraction_report",
]

LOGGER = logging.getLogger(__name__)

TEXT_EXTENSIONS = {".txt", ".md", ".csv"}
PDF_EXTENSIONS = {".pdf"}
IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".tif", ".tiff"}
READABLE_EXTENSIONS = TEXT_EXTENSIONS | PDF_EXTENSIONS | IMAGE_EXTENSIONS


@dataclass(frozen=True)
class DocumentEvidence:
    """Text evidence extracted from one file in the customer folder."""

    relative_path: str
    file_name: str
    extension: str
    category: str
    extraction_method: str
    readable: bool
    needs_ocr: bool
    ocr_available: bool
    page_count: int
    char_count: int
    text_path: str
    confidence: str
    detected_fields_json: str
    notes: tuple[str, ...]

    def as_json(self) -> dict[str, object]:
        """Return a JSON-serializable representation."""

        return asdict(self)

    def as_row(self) -> dict[str, str | int | bool]:
        """Return a CSV-friendly representation."""

        return {
            "relative_path": self.relative_path,
            "file_name": self.file_name,
            "extension": self.extension,
            "category": self.category,
            "extraction_method": self.extraction_method,
            "readable": self.readable,
            "needs_ocr": self.needs_ocr,
            "ocr_available": self.ocr_available,
            "page_count": self.page_count,
            "char_count": self.char_count,
            "text_path": self.text_path,
            "confidence": self.confidence,
            "detected_fields_json": self.detected_fields_json,
            "notes": " | ".join(self.notes),
        }


def _safe_text_name(relative_path: str) -> str:
    safe = re.sub(r"[^A-Za-z0-9_.-]+", "_", relative_path)
    return f"{safe}.txt"


def _normalize_text(text: str) -> str:
    return re.sub(r"[ \t]+", " ", text.replace("\r", "\n")).strip()


def _text_is_useful(text: str) -> bool:
    compact = _normalize_text(text)
    if len(compact) < 40:
        return False
    alpha = sum(1 for char in compact if char.isalpha())
    return alpha >= max(20, len(compact) // 8)


def _optional_module_available(module_name: str) -> bool:
    return importlib.util.find_spec(module_name) is not None


def _extract_with_pdfplumber(path: Path) -> tuple[str, int, str]:
    try:
        import pdfplumber  # type: ignore[import-not-found]
    except Exception as exc:
        return "", 0, f"pdfplumber non disponibile: {exc}"

    try:
        page_texts: list[str] = []
        with pdfplumber.open(path) as pdf:
            for page in pdf.pages:
                page_texts.append(page.extract_text() or "")
        return "\n\n".join(page_texts), len(page_texts), ""
    except Exception as exc:
        return "", 0, f"pdfplumber fallito: {exc}"


def _extract_with_fitz(path: Path) -> tuple[str, int, str]:
    try:
        import fitz  # type: ignore[import-not-found]
    except Exception as exc:
        return "", 0, f"PyMuPDF non disponibile: {exc}"

    try:
        page_texts: list[str] = []
        with fitz.open(path) as doc:
            for page in doc:
                page_texts.append(page.get_text() or "")
        return "\n\n".join(page_texts), len(page_texts), ""
    except Exception as exc:
        return "", 0, f"PyMuPDF fallito: {exc}"


def _render_pdf_pages(path: Path, max_pages: int) -> tuple[list[object], str]:
    try:
        import fitz  # type: ignore[import-not-found]
        from PIL import Image  # type: ignore[import-not-found]
    except Exception as exc:
        return [], f"rendering PyMuPDF non disponibile: {exc}"

    try:
        images: list[object] = []
        with fitz.open(path) as doc:
            for page in list(doc)[:max_pages]:
                pix = page.get_pixmap(matrix=fitz.Matrix(300.0 / 72.0, 300.0 / 72.0))
                mode = "RGB" if pix.alpha == 0 else "RGBA"
                images.append(
                    Image.frombytes(mode, [pix.width, pix.height], pix.samples)
                )
        return images, ""
    except Exception as exc:
        return [], f"rendering PyMuPDF fallito: {exc}"


def _paddle_ocr_image(image: object, lang: str) -> tuple[str, str]:
    try:
        from paddleocr import PaddleOCR  # type: ignore[import-not-found]
    except Exception as exc:
        return "", f"PaddleOCR non disponibile: {exc}"

    try:
        ocr = PaddleOCR(lang=lang, show_log=False)
    except TypeError:
        try:
            ocr = PaddleOCR(lang=lang)
        except Exception as exc:
            return "", f"PaddleOCR init fallito: {exc}"
    except Exception as exc:
        return "", f"PaddleOCR init fallito: {exc}"

    try:
        result = ocr.ocr(image)
    except Exception as exc:
        return "", f"PaddleOCR fallito: {exc}"

    lines: list[str] = []
    for page in result or []:
        for item in page or []:
            if isinstance(item, (list, tuple)) and len(item) >= 2:
                text_part = item[1]
                if isinstance(text_part, (list, tuple)) and text_part:
                    lines.append(str(text_part[0]))
    return "\n".join(lines), ""


def _extract_pdf_ocr(path: Path, max_pages: int, lang: str) -> tuple[str, int, str]:
    images, render_error = _render_pdf_pages(path, max_pages=max_pages)
    if not images:
        return "", 0, render_error or "nessuna pagina rasterizzata"

    page_texts: list[str] = []
    errors: list[str] = []
    for image in images:
        text, error = _paddle_ocr_image(image, lang=lang)
        page_texts.append(text)
        if error:
            errors.append(error)
    return "\n\n".join(page_texts), len(images), "; ".join(errors[:2])


def _extract_image_ocr(path: Path, lang: str) -> tuple[str, int, str]:
    try:
        from PIL import Image  # type: ignore[import-not-found]
    except Exception as exc:
        return "", 0, f"Pillow non disponibile: {exc}"

    try:
        with Image.open(path) as image:
            text, error = _paddle_ocr_image(image, lang=lang)
        return text, 1, error
    except Exception as exc:
        return "", 0, f"OCR immagine fallito: {exc}"


def _plain_text_fallback(path: Path) -> tuple[str, str]:
    try:
        text = path.read_text(encoding="utf-8", errors="ignore")
    except OSError as exc:
        return "", f"lettura testo fallita: {exc}"
    if _text_is_useful(text):
        return text, ""
    return "", "testo assente o troppo breve"


def _detect_fields(text: str) -> dict[str, list[str]]:
    patterns = {
        "codici_fiscali": r"\b[A-Z]{6}\d{2}[A-Z]\d{2}[A-Z]\d{3}[A-Z]\b",
        "partite_iva": r"\b\d{11}\b",
        "anni": r"\b20[0-4]\d\b",
        "importi": r"(?:€\s*)?\b\d{1,3}(?:\.\d{3})*,\d{2}\b",
        "protocolli": r"\b(?:protocollo|prot\.?)\s*[: n.]?\s*([A-Z0-9/-]{5,})",
    }
    indicators = {
        "certificazione_unica": r"certificazione\s+unica|\bcu\b|sostituto\s+d[' ]imposta",
        "f24": r"\bf24\b|codice\s+tributo|sezione\s+erario",
        "730": r"\b730\b|dichiarazione\s+precompilata",
        "redditi_pf": r"redditi\s+persone\s+fisiche|redditi\s+pf|\bpf\b",
        "mutuo": r"mutuo|interessi\s+passivi",
        "spese_sanitarie": r"spes[ae]\s+sanitari[ae]|farmacia|medic[oi]|scontrino",
        "avviso": r"agenzia\s+delle\s+entrate|avviso|comunicazione",
    }
    fields: dict[str, list[str]] = {}
    for label, pattern in patterns.items():
        values = sorted(
            {
                match if isinstance(match, str) else match[0]
                for match in re.findall(pattern, text, re.I)
            }
        )
        if values:
            fields[label] = values[:20]
    matched_indicators = [
        label for label, pattern in indicators.items() if re.search(pattern, text, re.I)
    ]
    if matched_indicators:
        fields["indicatori_documento"] = matched_indicators
    if re.search(indicators["f24"], text, re.I):
        codes = sorted(set(re.findall(r"\b\d{4}\b", text)))
        if codes:
            fields["codici_tributo_possibili"] = codes[:20]
    return fields


def _write_text(text_dir: Path, relative_path: str, text: str) -> str:
    if not text.strip():
        return ""
    text_dir.mkdir(parents=True, exist_ok=True)
    text_path = text_dir / _safe_text_name(relative_path)
    text_path.write_text(_normalize_text(text) + "\n", encoding="utf-8")
    return text_path.relative_to(text_dir.parent).as_posix()


def _extract_one(
    record: FileRecord,
    root: Path,
    output_dir: Path,
    enable_ocr: bool,
    lang: str,
    max_pages: int,
) -> DocumentEvidence:
    path = root / record.relative_path
    extension = record.extension.lower()
    text = ""
    page_count = 0
    method = "unsupported"
    notes: list[str] = []
    needs_ocr = False
    ocr_available = _optional_module_available("paddleocr")

    if extension in TEXT_EXTENSIONS:
        text, error = _plain_text_fallback(path)
        method = "plain_text" if text else "error"
        if error:
            notes.append(error)
    elif extension in PDF_EXTENSIONS:
        text, page_count, error = _extract_with_pdfplumber(path)
        method = "pdfplumber"
        if error:
            notes.append(error)
        if not _text_is_useful(text):
            text_fitz, page_count_fitz, error_fitz = _extract_with_fitz(path)
            if _text_is_useful(text_fitz):
                text = text_fitz
                page_count = page_count_fitz
                method = "pymupdf"
            elif error_fitz:
                notes.append(error_fitz)
        if not _text_is_useful(text):
            fallback_text, fallback_error = _plain_text_fallback(path)
            if fallback_text:
                text = fallback_text
                method = "plain_text_fallback"
            elif fallback_error:
                notes.append(fallback_error)
        if not _text_is_useful(text):
            needs_ocr = True
            if enable_ocr:
                ocr_text, ocr_pages, ocr_error = _extract_pdf_ocr(
                    path,
                    max_pages=max_pages,
                    lang=lang,
                )
                if _text_is_useful(ocr_text):
                    text = ocr_text
                    page_count = ocr_pages
                    method = "paddle_ocr"
                else:
                    method = "ocr_failed" if ocr_available else "ocr_missing"
                    notes.append(ocr_error or "OCR non ha prodotto testo utile")
            else:
                method = "ocr_disabled"
    elif extension in IMAGE_EXTENSIONS:
        needs_ocr = True
        if enable_ocr:
            text, page_count, error = _extract_image_ocr(path, lang=lang)
            method = "paddle_ocr" if _text_is_useful(text) else "ocr_failed"
            if error:
                notes.append(error)
        else:
            method = "ocr_disabled"
    else:
        notes.append("estensione non gestita per estrazione testo")

    readable = _text_is_useful(text)
    text_path = _write_text(output_dir / "pdf_text", record.relative_path, text)
    confidence = (
        "alta"
        if readable and method in {"pdfplumber", "pymupdf", "plain_text"}
        else "media" if readable else "bassa"
    )
    fields = _detect_fields(text) if readable else {}
    return DocumentEvidence(
        relative_path=record.relative_path,
        file_name=record.file_name,
        extension=extension,
        category=record.category,
        extraction_method=method,
        readable=readable,
        needs_ocr=needs_ocr,
        ocr_available=ocr_available,
        page_count=page_count,
        char_count=len(_normalize_text(text)),
        text_path=text_path,
        confidence=confidence,
        detected_fields_json=json.dumps(fields, ensure_ascii=False, sort_keys=True),
        notes=tuple(dict.fromkeys(note for note in notes if note)),
    )


def extract_documents(
    records: Sequence[FileRecord],
    root: Path | str,
    output_dir: Path | str,
    enable_ocr: bool = True,
    lang: str = "it",
    max_pages: int = 50,
) -> list[DocumentEvidence]:
    """Extract local text evidence from readable customer documents."""

    root_path = Path(root)
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)
    evidence: list[DocumentEvidence] = []
    for record in records:
        if record.extension.lower() not in READABLE_EXTENSIONS:
            continue
        evidence.append(
            _extract_one(
                record,
                root_path,
                output_path,
                enable_ocr=enable_ocr,
                lang=lang,
                max_pages=max_pages,
            )
        )
    write_documents_jsonl(evidence, output_path / "documents.jsonl")
    write_extraction_inventory_csv(evidence, output_path / "document_extraction.csv")
    write_extraction_report(evidence, output_path / "extraction_report.md")
    return evidence


def write_documents_jsonl(
    evidence: Iterable[DocumentEvidence],
    output_path: Path | str,
) -> Path:
    """Write one JSON evidence object per line."""

    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for record in evidence:
            handle.write(json.dumps(record.as_json(), ensure_ascii=False) + "\n")
    return path


def write_extraction_inventory_csv(
    evidence: Iterable[DocumentEvidence],
    output_path: Path | str,
) -> Path:
    """Write a CSV inventory of text extraction attempts."""

    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = [
        "relative_path",
        "file_name",
        "extension",
        "category",
        "extraction_method",
        "readable",
        "needs_ocr",
        "ocr_available",
        "page_count",
        "char_count",
        "text_path",
        "confidence",
        "detected_fields_json",
        "notes",
    ]
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for record in evidence:
            writer.writerow(record.as_row())
    return path


def write_extraction_report(
    evidence: Sequence[DocumentEvidence],
    output_path: Path | str,
) -> Path:
    """Write a readable text extraction report."""

    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    readable = [record for record in evidence if record.readable]
    unreadable = [record for record in evidence if not record.readable]
    lines = [
        "# Estrazione testo documenti",
        "",
        f"- Documenti tentati: {len(evidence)}",
        f"- Documenti leggibili: {len(readable)}",
        f"- Documenti non leggibili: {len(unreadable)}",
        "",
    ]
    if unreadable:
        lines.extend(["## Da verificare / OCR necessario", ""])
        for record in unreadable:
            note = f" — {', '.join(record.notes)}" if record.notes else ""
            lines.append(
                f"- `{record.relative_path}`: {record.extraction_method}{note}"
            )
        lines.append("")
    if readable:
        lines.extend(["## Testo estratto", ""])
        for record in readable:
            lines.append(
                f"- `{record.relative_path}`: {record.extraction_method}, "
                f"{record.char_count} caratteri, confidenza {record.confidence}"
            )
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Estrae testo locale da PDF e immagini di una cartella cliente."
    )
    parser.add_argument("folder", type=Path, help="Cartella cliente.")
    parser.add_argument("--out", type=Path, default=None, help="Cartella output.")
    parser.add_argument("--no-ocr", action="store_true", help="Disabilita OCR.")
    parser.add_argument("--lang", default="it", help="Lingua OCR Paddle.")
    parser.add_argument(
        "--max-pages",
        type=int,
        default=50,
        help="Pagine massime per PDF.",
    )
    return parser.parse_args()


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    args = _parse_args()
    from scan_folder import scan_folder

    records = scan_folder(args.folder, output_dir=args.out)
    out_dir = args.out or args.folder / "out" / "extracted"
    evidence = extract_documents(
        records,
        args.folder,
        out_dir,
        enable_ocr=not args.no_ocr,
        lang=args.lang,
        max_pages=args.max_pages,
    )
    LOGGER.info("Estratti %s documenti in %s", len(evidence), out_dir)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
