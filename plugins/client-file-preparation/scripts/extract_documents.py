from __future__ import annotations

import argparse
import csv
import hashlib
import importlib.util
import json
import logging
import re
import stat
import zipfile
from dataclasses import asdict, dataclass
from email import policy
from email.parser import BytesParser
from html.parser import HTMLParser
from pathlib import Path
from typing import Iterable, Sequence
from xml.etree import ElementTree as ET

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
DOCX_EXTENSIONS = {".docx"}
XLSX_EXTENSIONS = {".xlsx"}
EMAIL_EXTENSIONS = {".eml"}
READABLE_EXTENSIONS = (
    TEXT_EXTENSIONS
    | PDF_EXTENSIONS
    | IMAGE_EXTENSIONS
    | DOCX_EXTENSIONS
    | XLSX_EXTENSIONS
    | EMAIL_EXTENSIONS
)
MAX_ARCHIVE_MEMBER_BYTES = 20 * 1024 * 1024
MAX_ARCHIVE_TOTAL_BYTES = 80 * 1024 * 1024
MAX_ARCHIVE_MEMBERS = 2_000
MAX_ARCHIVE_COMPRESSION_RATIO = 200
MAX_EMAIL_BYTES = 30 * 1024 * 1024
MAX_TEXT_BYTES = 20 * 1024 * 1024
MAX_PDF_BYTES = 100 * 1024 * 1024

DIAGNOSTIC_PREFIX_COPY = {
    "percorso sorgente non locale o non normalizzato": {
        "en": "source path is not run-local or normalized",
        "fr": "le chemin source n’est pas local au run ou normalisé",
        "de": "Quellpfad ist nicht lauflokal oder normalisiert",
        "es": "la ruta de origen no es local a la ejecución o no está normalizada",
    },
    "collegamento simbolico sorgente non consentito": {
        "en": "source symbolic link is not allowed",
        "fr": "le lien symbolique source n’est pas autorisé",
        "de": "symbolischer Quelllink ist nicht zulässig",
        "es": "no se permite el enlace simbólico de origen",
    },
    "percorso sorgente esterno alla cartella cliente": {
        "en": "source path is outside the client folder",
        "fr": "le chemin source se trouve hors du dossier client",
        "de": "Quellpfad liegt außerhalb des Mandantenordners",
        "es": "la ruta de origen está fuera de la carpeta del cliente",
    },
    "la sorgente non è un file regolare": {
        "en": "source is not a regular file",
        "fr": "la source n’est pas un fichier ordinaire",
        "de": "Quelle ist keine reguläre Datei",
        "es": "el origen no es un archivo normal",
    },
    "lettura DOCX fallita": {
        "en": "DOCX reading failed",
        "fr": "échec de lecture du DOCX",
        "de": "DOCX konnte nicht gelesen werden",
        "es": "no se ha podido leer el DOCX",
    },
    "lettura XLSX fallita": {
        "en": "XLSX reading failed",
        "fr": "échec de lecture du XLSX",
        "de": "XLSX konnte nicht gelesen werden",
        "es": "no se ha podido leer el XLSX",
    },
    "lettura EML fallita": {
        "en": "EML reading failed",
        "fr": "échec de lecture de l’EML",
        "de": "EML konnte nicht gelesen werden",
        "es": "no se ha podido leer el EML",
    },
    "lettura testo fallita": {
        "en": "text reading failed",
        "fr": "échec de lecture du texte",
        "de": "Text konnte nicht gelesen werden",
        "es": "no se ha podido leer el texto",
    },
    "email troppo grande": {
        "en": "email exceeds the size limit",
        "fr": "l’e-mail dépasse la limite de taille",
        "de": "E-Mail überschreitet die Größenbegrenzung",
        "es": "el correo supera el límite de tamaño",
    },
    "file di testo troppo grande": {
        "en": "text file exceeds the size limit",
        "fr": "le fichier texte dépasse la limite de taille",
        "de": "Textdatei überschreitet die Größenbegrenzung",
        "es": "el archivo de texto supera el límite de tamaño",
    },
    "file di testo oltre il limite di": {
        "en": "text file exceeds the limit of",
        "fr": "le fichier texte dépasse la limite de",
        "de": "Textdatei überschreitet die Grenze von",
        "es": "el archivo de texto supera el límite de",
    },
    "testo assente o troppo breve": {
        "en": "text is absent or too short",
        "fr": "le texte est absent ou trop court",
        "de": "Text fehlt oder ist zu kurz",
        "es": "el texto está ausente o es demasiado breve",
    },
    "PDF troppo grande": {
        "en": "PDF exceeds the size limit",
        "fr": "le PDF dépasse la limite de taille",
        "de": "PDF überschreitet die Größenbegrenzung",
        "es": "el PDF supera el límite de tamaño",
    },
    "allegati EML non estratti": {
        "en": "EML attachments not extracted",
        "fr": "pièces jointes EML non extraites",
        "de": "EML-Anhänge nicht extrahiert",
        "es": "no se han extraído los adjuntos EML",
    },
    "pdfplumber non disponibile": {
        "en": "pdfplumber unavailable",
        "fr": "pdfplumber indisponible",
        "de": "pdfplumber nicht verfügbar",
        "es": "pdfplumber no está disponible",
    },
    "pdfplumber fallito": {
        "en": "pdfplumber failed",
        "fr": "échec de pdfplumber",
        "de": "pdfplumber fehlgeschlagen",
        "es": "pdfplumber ha fallado",
    },
    "PyMuPDF non disponibile": {
        "en": "PyMuPDF unavailable",
        "fr": "PyMuPDF indisponible",
        "de": "PyMuPDF nicht verfügbar",
        "es": "PyMuPDF no está disponible",
    },
    "PyMuPDF fallito": {
        "en": "PyMuPDF failed",
        "fr": "échec de PyMuPDF",
        "de": "PyMuPDF fehlgeschlagen",
        "es": "PyMuPDF ha fallado",
    },
    "rendering PyMuPDF non disponibile": {
        "en": "PyMuPDF rendering unavailable",
        "fr": "rendu PyMuPDF indisponible",
        "de": "PyMuPDF-Rendering nicht verfügbar",
        "es": "el renderizado de PyMuPDF no está disponible",
    },
    "rendering PyMuPDF fallito": {
        "en": "PyMuPDF rendering failed",
        "fr": "échec du rendu PyMuPDF",
        "de": "PyMuPDF-Rendering fehlgeschlagen",
        "es": "el renderizado de PyMuPDF ha fallado",
    },
    "PaddleOCR non disponibile": {
        "en": "PaddleOCR unavailable",
        "fr": "PaddleOCR indisponible",
        "de": "PaddleOCR nicht verfügbar",
        "es": "PaddleOCR no está disponible",
    },
    "PaddleOCR init fallito": {
        "en": "PaddleOCR initialization failed",
        "fr": "échec de l’initialisation de PaddleOCR",
        "de": "PaddleOCR-Initialisierung fehlgeschlagen",
        "es": "no se ha podido inicializar PaddleOCR",
    },
    "PaddleOCR fallito": {
        "en": "PaddleOCR failed",
        "fr": "échec de PaddleOCR",
        "de": "PaddleOCR fehlgeschlagen",
        "es": "PaddleOCR ha fallado",
    },
    "Pillow non disponibile": {
        "en": "Pillow unavailable",
        "fr": "Pillow indisponible",
        "de": "Pillow nicht verfügbar",
        "es": "Pillow no está disponible",
    },
    "OCR immagine fallito": {
        "en": "image OCR failed",
        "fr": "échec de l’OCR de l’image",
        "de": "Bild-OCR fehlgeschlagen",
        "es": "el OCR de la imagen ha fallado",
    },
    "nessuna pagina rasterizzata": {
        "en": "no page was rasterized",
        "fr": "aucune page n’a été rastérisée",
        "de": "keine Seite wurde gerastert",
        "es": "no se ha rasterizado ninguna página",
    },
    "OCR non ha prodotto testo utile": {
        "en": "OCR produced no usable text",
        "fr": "l’OCR n’a produit aucun texte exploitable",
        "de": "OCR hat keinen nutzbaren Text erzeugt",
        "es": "el OCR no ha producido texto utilizable",
    },
    "estensione non supportata per estrazione locale": {
        "en": "extension unsupported for local extraction",
        "fr": "extension non prise en charge pour l’extraction locale",
        "de": "Erweiterung für lokale Extraktion nicht unterstützt",
        "es": "extensión no compatible con la extracción local",
    },
    "membro OOXML troppo grande": {
        "en": "OOXML member exceeds the size limit",
        "fr": "le membre OOXML dépasse la limite de taille",
        "de": "OOXML-Bestandteil überschreitet die Größenbegrenzung",
        "es": "el componente OOXML supera el límite de tamaño",
    },
    "membro OOXML cifrato non supportato": {
        "en": "encrypted OOXML member unsupported",
        "fr": "membre OOXML chiffré non pris en charge",
        "de": "verschlüsselter OOXML-Bestandteil nicht unterstützt",
        "es": "el componente OOXML cifrado no es compatible",
    },
    "rapporto di compressione OOXML eccessivo": {
        "en": "OOXML compression ratio exceeds the limit",
        "fr": "le taux de compression OOXML dépasse la limite",
        "de": "OOXML-Kompressionsverhältnis überschreitet die Grenze",
        "es": "la relación de compresión OOXML supera el límite",
    },
    "archivio OOXML con troppi membri": {
        "en": "OOXML archive contains too many members",
        "fr": "l’archive OOXML contient trop de membres",
        "de": "OOXML-Archiv enthält zu viele Bestandteile",
        "es": "el archivo OOXML contiene demasiados componentes",
    },
    "archivio OOXML con nomi membro duplicati": {
        "en": "OOXML archive contains duplicate member names",
        "fr": "l’archive OOXML contient des noms de membres en double",
        "de": "OOXML-Archiv enthält doppelte Bestandteilnamen",
        "es": "el archivo OOXML contiene nombres de componentes duplicados",
    },
    "archivio OOXML espanso troppo grande": {
        "en": "expanded OOXML archive exceeds the size limit",
        "fr": "l’archive OOXML décompressée dépasse la limite de taille",
        "de": "entpacktes OOXML-Archiv überschreitet die Größenbegrenzung",
        "es": "el archivo OOXML descomprimido supera el límite de tamaño",
    },
}


def _localized_diagnostic(value: str, language: str) -> str:
    """Localize known extraction diagnostics while preserving technical detail."""

    if language == "it" or not value:
        return value
    page_limit = re.fullmatch(
        r"estrazione testo limitata alle prime (\d+) di (\d+) pagine",
        value,
    )
    if page_limit:
        read_pages, total_pages = page_limit.groups()
        return {
            "en": f"text extraction limited to the first {read_pages} of {total_pages} pages",
            "fr": f"extraction de texte limitée aux {read_pages} premières pages sur {total_pages}",
            "de": f"Textextraktion auf die ersten {read_pages} von {total_pages} Seiten begrenzt",
            "es": f"extracción de texto limitada a las primeras {read_pages} de {total_pages} páginas",
        }[language]
    ocr_limit = re.fullmatch(
        r"OCR limitato alle prime (\d+) di (\d+) pagine",
        value,
    )
    if ocr_limit:
        read_pages, total_pages = ocr_limit.groups()
        return {
            "en": f"OCR limited to the first {read_pages} of {total_pages} pages",
            "fr": f"OCR limité aux {read_pages} premières pages sur {total_pages}",
            "de": f"OCR auf die ersten {read_pages} von {total_pages} Seiten begrenzt",
            "es": f"OCR limitado a las primeras {read_pages} de {total_pages} páginas",
        }[language]
    unsafe_xml = re.fullmatch(
        r"(?P<source>.+): dichiarazioni DTD/entity non consentite",
        value,
    )
    if unsafe_xml:
        source = unsafe_xml.group("source")
        return {
            "en": f"{source}: DTD/entity declarations are not allowed",
            "fr": f"{source} : les déclarations DTD/entity ne sont pas autorisées",
            "de": f"{source}: DTD-/Entity-Deklarationen sind nicht zulässig",
            "es": f"{source}: no se permiten declaraciones DTD/entity",
        }[language]
    for prefix in sorted(DIAGNOSTIC_PREFIX_COPY, key=len, reverse=True):
        if value == prefix or value.startswith(
            (f"{prefix}:", f"{prefix} ", f"{prefix}(")
        ):
            translated = DIAGNOSTIC_PREFIX_COPY[prefix][language]
            suffix = value[len(prefix) :]
            if suffix.startswith(": "):
                detail = _localized_diagnostic(suffix[2:], language)
                return f"{translated}: {detail}"
            return f"{translated}{suffix}"
    return value


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
    safe = re.sub(r"[^A-Za-z0-9_.-]+", "_", relative_path).strip("._")
    digest = hashlib.sha256(relative_path.encode("utf-8")).hexdigest()
    return f"{(safe or 'document')[:120]}-{digest}.txt"


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


def _xml_local_name(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def _safe_xml_root(payload: bytes, *, source: str) -> ET.Element:
    """Parse bounded local XML without accepting DTD/entity declarations."""

    if re.search(rb"<!\s*(?:DOCTYPE|ENTITY)\b", payload, flags=re.IGNORECASE):
        raise ValueError(f"{source}: dichiarazioni DTD/entity non consentite")
    return ET.fromstring(payload)


def _read_zip_member(archive: zipfile.ZipFile, name: str) -> bytes:
    """Read a selected OOXML member with mechanically verifiable size limits."""

    info = archive.getinfo(name)
    if info.file_size > MAX_ARCHIVE_MEMBER_BYTES:
        raise ValueError(f"membro OOXML troppo grande ({info.file_size} byte): {name}")
    if info.flag_bits & 0x1:
        raise ValueError(f"membro OOXML cifrato non supportato: {name}")
    compression_ratio = info.file_size / max(info.compress_size, 1)
    if compression_ratio > MAX_ARCHIVE_COMPRESSION_RATIO:
        raise ValueError(
            f"rapporto di compressione OOXML eccessivo ({compression_ratio:.1f}): "
            f"{name}"
        )
    return archive.read(info)


def _validate_ooxml_archive(archive: zipfile.ZipFile) -> None:
    members = [info for info in archive.infolist() if not info.is_dir()]
    if len(members) > MAX_ARCHIVE_MEMBERS:
        raise ValueError(f"archivio OOXML con troppi membri ({len(members)})")
    names = [info.filename for info in members]
    if len(names) != len(set(names)):
        raise ValueError("archivio OOXML con nomi membro duplicati")
    total_size = sum(info.file_size for info in members)
    if total_size > MAX_ARCHIVE_TOTAL_BYTES:
        raise ValueError(f"archivio OOXML espanso troppo grande ({total_size} byte)")
    for info in members:
        if info.file_size > MAX_ARCHIVE_MEMBER_BYTES:
            raise ValueError(
                f"membro OOXML troppo grande ({info.file_size} byte): {info.filename}"
            )
        compression_ratio = info.file_size / max(info.compress_size, 1)
        if compression_ratio > MAX_ARCHIVE_COMPRESSION_RATIO:
            raise ValueError(
                "rapporto di compressione OOXML eccessivo "
                f"({compression_ratio:.1f}): {info.filename}"
            )


def _resolve_source_file(root: Path, relative_path: str) -> Path:
    """Resolve one run-local regular file without following symbolic links."""

    root_path = root.expanduser().resolve(strict=True)
    path_value = Path(relative_path)
    if (
        path_value.is_absolute()
        or relative_path != path_value.as_posix()
        or any(part in {"", ".", ".."} for part in path_value.parts)
    ):
        raise ValueError("percorso sorgente non locale o non normalizzato")
    candidate = root_path
    for part in path_value.parts:
        candidate /= part
        if candidate.is_symlink():
            raise ValueError("collegamento simbolico sorgente non consentito")
    resolved = candidate.resolve(strict=True)
    if not resolved.is_relative_to(root_path):
        raise ValueError("percorso sorgente esterno alla cartella cliente")
    if not stat.S_ISREG(resolved.lstat().st_mode):
        raise ValueError("la sorgente non è un file regolare")
    return resolved


def _word_xml_text(root: ET.Element) -> str:
    chunks: list[str] = []
    for node in root.iter():
        name = _xml_local_name(node.tag)
        if name == "t" and node.text:
            chunks.append(node.text)
        elif name == "tab":
            chunks.append("\t")
        elif name in {"br", "cr", "p"}:
            chunks.append("\n")
    return " ".join(part for part in chunks if part).strip()


def _extract_docx(path: Path) -> tuple[str, str]:
    try:
        with zipfile.ZipFile(path) as archive:
            _validate_ooxml_archive(archive)
            names = {info.filename for info in archive.infolist() if not info.is_dir()}
            selected = ["word/document.xml"]
            selected.extend(
                sorted(
                    name
                    for name in names
                    if re.fullmatch(r"word/(?:header|footer)\d+\.xml", name)
                )
            )
            texts: list[str] = []
            for name in selected:
                if name not in names:
                    continue
                payload = _read_zip_member(archive, name)
                root = _safe_xml_root(payload, source=name)
                text = _word_xml_text(root)
                if text:
                    texts.append(text)
            return "\n\n".join(texts), ""
    except (OSError, KeyError, ValueError, zipfile.BadZipFile, ET.ParseError) as exc:
        return "", f"lettura DOCX fallita: {exc}"


def _shared_strings(root: ET.Element) -> list[str]:
    strings: list[str] = []
    for item in root.iter():
        if _xml_local_name(item.tag) != "si":
            continue
        strings.append(
            " ".join(
                node.text or ""
                for node in item.iter()
                if _xml_local_name(node.tag) == "t" and node.text
            ).strip()
        )
    return strings


def _worksheet_text(root: ET.Element, shared: Sequence[str]) -> str:
    lines: list[str] = []
    for row in root.iter():
        if _xml_local_name(row.tag) != "row":
            continue
        values: list[str] = []
        for cell in row:
            if _xml_local_name(cell.tag) != "c":
                continue
            cell_type = cell.attrib.get("t", "")
            cell_ref = cell.attrib.get("r", "")
            value_node = next(
                (node for node in cell if _xml_local_name(node.tag) == "v"),
                None,
            )
            formula_node = next(
                (node for node in cell if _xml_local_name(node.tag) == "f"),
                None,
            )
            if cell_type == "inlineStr":
                value = " ".join(
                    node.text or ""
                    for node in cell.iter()
                    if _xml_local_name(node.tag) == "t" and node.text
                ).strip()
            else:
                raw_value = value_node.text if value_node is not None else ""
                if cell_type == "s" and raw_value:
                    try:
                        value = shared[int(raw_value)]
                    except (IndexError, ValueError):
                        value = raw_value
                elif cell_type == "b":
                    value = "TRUE" if raw_value == "1" else "FALSE"
                else:
                    value = raw_value
            if not value and formula_node is not None and formula_node.text:
                value = f"={formula_node.text}"
            if value:
                values.append(f"{cell_ref}={value}" if cell_ref else value)
        if values:
            lines.append("\t".join(values))
    return "\n".join(lines)


def _extract_xlsx(path: Path) -> tuple[str, str]:
    try:
        with zipfile.ZipFile(path) as archive:
            _validate_ooxml_archive(archive)
            names = {info.filename for info in archive.infolist() if not info.is_dir()}
            shared: list[str] = []
            if "xl/sharedStrings.xml" in names:
                shared_root = _safe_xml_root(
                    _read_zip_member(archive, "xl/sharedStrings.xml"),
                    source="xl/sharedStrings.xml",
                )
                shared = _shared_strings(shared_root)
            sheet_names = sorted(
                name
                for name in names
                if re.fullmatch(r"xl/worksheets/sheet\d+\.xml", name)
            )
            sheets: list[str] = []
            for name in sheet_names:
                sheet_root = _safe_xml_root(
                    _read_zip_member(archive, name),
                    source=name,
                )
                text = _worksheet_text(sheet_root, shared)
                if text:
                    sheets.append(f"[{Path(name).stem}]\n{text}")
            return "\n\n".join(sheets), ""
    except (OSError, KeyError, ValueError, zipfile.BadZipFile, ET.ParseError) as exc:
        return "", f"lettura XLSX fallita: {exc}"


class _HtmlTextExtractor(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.parts: list[str] = []

    def handle_data(self, data: str) -> None:
        if data.strip():
            self.parts.append(data)


def _html_to_text(value: str) -> str:
    parser = _HtmlTextExtractor()
    parser.feed(value)
    parser.close()
    return " ".join(parser.parts)


def _extract_eml(path: Path) -> tuple[str, str]:
    try:
        if path.stat().st_size > MAX_EMAIL_BYTES:
            return "", f"email troppo grande ({path.stat().st_size} byte)"
        message = BytesParser(policy=policy.default).parsebytes(path.read_bytes())
        parts = [
            f"Subject: {message.get('subject', '')}",
            f"From: {message.get('from', '')}",
            f"To: {message.get('to', '')}",
            f"Date: {message.get('date', '')}",
        ]
        bodies: list[str] = []
        attachment_count = 0
        for part in message.walk():
            if part.is_multipart():
                continue
            if part.get_content_disposition() == "attachment" or part.get_filename():
                attachment_count += 1
                continue
            content_type = part.get_content_type()
            if content_type not in {"text/plain", "text/html"}:
                continue
            try:
                content = part.get_content()
            except (LookupError, UnicodeError):
                payload = part.get_payload(decode=True) or b""
                content = payload.decode("utf-8", errors="replace")
            text = content if isinstance(content, str) else str(content)
            bodies.append(_html_to_text(text) if content_type == "text/html" else text)
        note = (
            f"allegati EML non estratti: {attachment_count}" if attachment_count else ""
        )
        return "\n".join(parts + bodies), note
    except (OSError, ValueError) as exc:
        return "", f"lettura EML fallita: {exc}"


def _extract_with_pdfplumber(path: Path, max_pages: int) -> tuple[str, int, str]:
    try:
        import pdfplumber  # type: ignore[import-not-found]
    except Exception as exc:
        return "", 0, f"pdfplumber non disponibile: {exc}"

    try:
        page_texts: list[str] = []
        with pdfplumber.open(path) as pdf:
            total_pages = len(pdf.pages)
            for page in pdf.pages[:max_pages]:
                page_texts.append(page.extract_text() or "")
        note = (
            f"estrazione testo limitata alle prime {len(page_texts)} di "
            f"{total_pages} pagine"
            if total_pages > len(page_texts)
            else ""
        )
        return "\n\n".join(page_texts), len(page_texts), note
    except Exception as exc:
        return "", 0, f"pdfplumber fallito: {exc}"


def _extract_with_fitz(path: Path, max_pages: int) -> tuple[str, int, str]:
    try:
        import fitz  # type: ignore[import-not-found]
    except Exception as exc:
        return "", 0, f"PyMuPDF non disponibile: {exc}"

    try:
        page_texts: list[str] = []
        with fitz.open(path) as doc:
            total_pages = len(doc)
            for index in range(min(total_pages, max_pages)):
                page_texts.append(doc[index].get_text() or "")
        note = (
            f"estrazione testo limitata alle prime {len(page_texts)} di "
            f"{total_pages} pagine"
            if total_pages > len(page_texts)
            else ""
        )
        return "\n\n".join(page_texts), len(page_texts), note
    except Exception as exc:
        return "", 0, f"PyMuPDF fallito: {exc}"


def _render_pdf_pages(path: Path, max_pages: int) -> tuple[list[object], int, str]:
    try:
        import fitz  # type: ignore[import-not-found]
        from PIL import Image  # type: ignore[import-not-found]
    except Exception as exc:
        return [], 0, f"rendering PyMuPDF non disponibile: {exc}"

    try:
        images: list[object] = []
        with fitz.open(path) as doc:
            total_pages = len(doc)
            for index in range(min(total_pages, max_pages)):
                page = doc[index]
                pix = page.get_pixmap(matrix=fitz.Matrix(300.0 / 72.0, 300.0 / 72.0))
                mode = "RGB" if pix.alpha == 0 else "RGBA"
                images.append(
                    Image.frombytes(mode, [pix.width, pix.height], pix.samples)
                )
        return images, total_pages, ""
    except Exception as exc:
        return [], 0, f"rendering PyMuPDF fallito: {exc}"


class _PaddleOcrSession:
    """Lazily initialize one local OCR engine and reuse it for the entire run."""

    def __init__(self, lang: str) -> None:
        self.lang = lang
        self.engine: object | None = None
        self.initialized = False
        self.init_error = ""

    def _initialize(self) -> None:
        if self.initialized:
            return
        self.initialized = True
        try:
            from paddleocr import PaddleOCR  # type: ignore[import-not-found]
        except Exception as exc:
            self.init_error = f"PaddleOCR non disponibile: {exc}"
            return
        try:
            self.engine = PaddleOCR(lang=self.lang, show_log=False)
        except TypeError:
            try:
                self.engine = PaddleOCR(lang=self.lang)
            except Exception as exc:
                self.init_error = f"PaddleOCR init fallito: {exc}"
        except Exception as exc:
            self.init_error = f"PaddleOCR init fallito: {exc}"

    def extract(self, image: object) -> tuple[str, str]:
        self._initialize()
        if self.engine is None:
            return "", self.init_error or "PaddleOCR non disponibile"

        try:
            result = self.engine.ocr(image)  # type: ignore[attr-defined]
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


def _extract_pdf_ocr(
    path: Path,
    max_pages: int,
    ocr_session: _PaddleOcrSession,
) -> tuple[str, int, int, str]:
    images, total_pages, render_error = _render_pdf_pages(path, max_pages=max_pages)
    if not images:
        return "", 0, total_pages, render_error or "nessuna pagina rasterizzata"

    page_texts: list[str] = []
    errors: list[str] = []
    for image in images:
        text, error = ocr_session.extract(image)
        page_texts.append(text)
        if error:
            errors.append(error)
    return (
        "\n\n".join(page_texts),
        len(images),
        total_pages,
        "; ".join(errors[:2]),
    )


def _extract_image_ocr(
    path: Path,
    ocr_session: _PaddleOcrSession,
) -> tuple[str, int, str]:
    try:
        from PIL import Image  # type: ignore[import-not-found]
    except Exception as exc:
        return "", 0, f"Pillow non disponibile: {exc}"

    try:
        with Image.open(path) as image:
            text, error = ocr_session.extract(image)
        return text, 1, error
    except Exception as exc:
        return "", 0, f"OCR immagine fallito: {exc}"


def _plain_text_fallback(path: Path) -> tuple[str, str]:
    try:
        if path.stat().st_size > MAX_TEXT_BYTES:
            return "", f"file di testo troppo grande ({path.stat().st_size} byte)"
        with path.open("rb") as handle:
            payload = handle.read(MAX_TEXT_BYTES + 1)
        if len(payload) > MAX_TEXT_BYTES:
            return "", f"file di testo oltre il limite di {MAX_TEXT_BYTES} byte"
        text = payload.decode("utf-8", errors="ignore")
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
    ocr_session: _PaddleOcrSession,
    max_pages: int,
    language: str,
) -> DocumentEvidence:
    extension = record.extension.lower()
    text = ""
    page_count = 0
    method = "unsupported"
    notes: list[str] = []
    needs_ocr = False
    ocr_available = _optional_module_available("paddleocr")

    if not record.sha256:
        return DocumentEvidence(
            relative_path=record.relative_path,
            file_name=record.file_name,
            extension=extension,
            category=record.category,
            extraction_method="unsafe_source_path",
            readable=False,
            needs_ocr=False,
            ocr_available=ocr_available,
            page_count=0,
            char_count=0,
            text_path="",
            confidence="bassa",
            detected_fields_json="{}",
            notes=(
                _localized_diagnostic(
                    "collegamento simbolico sorgente non consentito",
                    language,
                ),
            ),
        )

    try:
        path = _resolve_source_file(root, record.relative_path)
    except (OSError, ValueError) as exc:
        return DocumentEvidence(
            relative_path=record.relative_path,
            file_name=record.file_name,
            extension=extension,
            category=record.category,
            extraction_method="unsafe_source_path",
            readable=False,
            needs_ocr=False,
            ocr_available=ocr_available,
            page_count=0,
            char_count=0,
            text_path="",
            confidence="bassa",
            detected_fields_json="{}",
            notes=(_localized_diagnostic(str(exc), language),),
        )

    if extension in TEXT_EXTENSIONS:
        text, error = _plain_text_fallback(path)
        method = "plain_text" if text else "error"
        if error:
            notes.append(error)
    elif extension in DOCX_EXTENSIONS:
        text, error = _extract_docx(path)
        method = "docx_ooxml" if _text_is_useful(text) else "docx_unreadable"
        if error:
            notes.append(error)
    elif extension in XLSX_EXTENSIONS:
        text, error = _extract_xlsx(path)
        method = "xlsx_ooxml" if _text_is_useful(text) else "xlsx_unreadable"
        if error:
            notes.append(error)
    elif extension in EMAIL_EXTENSIONS:
        text, error = _extract_eml(path)
        method = "eml_stdlib" if _text_is_useful(text) else "eml_unreadable"
        if error:
            notes.append(error)
    elif extension in PDF_EXTENSIONS:
        if path.stat().st_size > MAX_PDF_BYTES:
            notes.append(f"PDF troppo grande ({path.stat().st_size} byte)")
            method = "pdf_too_large"
            text = ""
            page_count = 0
            error = ""
        else:
            text, page_count, error = _extract_with_pdfplumber(path, max_pages)
            method = "pdfplumber"
        if error:
            notes.append(error)
        if path.stat().st_size <= MAX_PDF_BYTES and not _text_is_useful(text):
            text_fitz, page_count_fitz, error_fitz = _extract_with_fitz(path, max_pages)
            if _text_is_useful(text_fitz):
                text = text_fitz
                page_count = page_count_fitz
                method = "pymupdf"
            elif error_fitz:
                notes.append(error_fitz)
        if path.stat().st_size <= MAX_PDF_BYTES and not _text_is_useful(text):
            fallback_text, fallback_error = _plain_text_fallback(path)
            if fallback_text:
                text = fallback_text
                method = "plain_text_fallback"
            elif fallback_error:
                notes.append(fallback_error)
        if path.stat().st_size <= MAX_PDF_BYTES and not _text_is_useful(text):
            needs_ocr = True
            if enable_ocr:
                ocr_text, ocr_pages, total_pages, ocr_error = _extract_pdf_ocr(
                    path,
                    max_pages=max_pages,
                    ocr_session=ocr_session,
                )
                if total_pages > ocr_pages:
                    notes.append(
                        f"OCR limitato alle prime {ocr_pages} di {total_pages} pagine"
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
            text, page_count, error = _extract_image_ocr(
                path,
                ocr_session=ocr_session,
            )
            method = "paddle_ocr" if _text_is_useful(text) else "ocr_failed"
            if error:
                notes.append(error)
        else:
            method = "ocr_disabled"
    else:
        method = "unsupported_msg" if extension == ".msg" else "unsupported_extension"
        notes.append(
            f"estensione non supportata per estrazione locale: {extension or '(nessuna)'}"
        )

    readable = _text_is_useful(text)
    text_path = _write_text(output_dir / "pdf_text", record.relative_path, text)
    confidence = (
        "alta"
        if readable
        and method
        in {
            "pdfplumber",
            "pymupdf",
            "plain_text",
            "docx_ooxml",
            "xlsx_ooxml",
            "eml_stdlib",
        }
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
        notes=tuple(
            dict.fromkeys(
                _localized_diagnostic(note, language) for note in notes if note
            )
        ),
    )


def extract_documents(
    records: Sequence[FileRecord],
    root: Path | str,
    output_dir: Path | str,
    enable_ocr: bool = True,
    lang: str = "it",
    max_pages: int = 50,
    *,
    language: str = "it",
) -> list[DocumentEvidence]:
    """Extract local text evidence from readable customer documents."""

    root_path = Path(root)
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)
    evidence: list[DocumentEvidence] = []
    ocr_session = _PaddleOcrSession(lang)
    for record in records:
        evidence.append(
            _extract_one(
                record,
                root_path,
                output_path,
                enable_ocr=enable_ocr,
                ocr_session=ocr_session,
                max_pages=max_pages,
                language=language,
            )
        )
    write_documents_jsonl(evidence, output_path / "documents.jsonl")
    write_extraction_inventory_csv(evidence, output_path / "document_extraction.csv")
    write_extraction_report(
        evidence,
        output_path / "extraction_report.md",
        language=language,
    )
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
    *,
    language: str = "it",
) -> Path:
    """Write a readable text extraction report."""

    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    readable = [record for record in evidence if record.readable]
    unreadable = [record for record in evidence if not record.readable]
    copy = {
        "it": {
            "title": "Estrazione testo documenti",
            "attempted": "Documenti tentati",
            "readable": "Documenti leggibili",
            "unreadable": "Documenti non leggibili",
            "verify": "Da verificare / OCR necessario",
            "extracted": "Testo estratto",
            "characters": "caratteri",
            "confidence": "confidenza",
        },
        "en": {
            "title": "Document text extraction",
            "attempted": "Documents attempted",
            "readable": "Readable documents",
            "unreadable": "Unreadable documents",
            "verify": "To verify / OCR required",
            "extracted": "Extracted text",
            "characters": "characters",
            "confidence": "confidence",
        },
        "fr": {
            "title": "Extraction du texte des documents",
            "attempted": "Documents traités",
            "readable": "Documents lisibles",
            "unreadable": "Documents illisibles",
            "verify": "À vérifier / OCR nécessaire",
            "extracted": "Texte extrait",
            "characters": "caractères",
            "confidence": "confiance",
        },
        "de": {
            "title": "Textextraktion aus Dokumenten",
            "attempted": "Verarbeitete Dokumente",
            "readable": "Lesbare Dokumente",
            "unreadable": "Nicht lesbare Dokumente",
            "verify": "Zu prüfen / OCR erforderlich",
            "extracted": "Extrahierter Text",
            "characters": "Zeichen",
            "confidence": "Konfidenz",
        },
        "es": {
            "title": "Extracción de texto de documentos",
            "attempted": "Documentos procesados",
            "readable": "Documentos legibles",
            "unreadable": "Documentos no legibles",
            "verify": "Pendiente de verificar / OCR necesario",
            "extracted": "Texto extraído",
            "characters": "caracteres",
            "confidence": "confianza",
        },
    }[language]
    confidence_copy = {
        "it": {"alta": "alta", "media": "media", "bassa": "bassa"},
        "en": {"alta": "high", "media": "medium", "bassa": "low"},
        "fr": {"alta": "élevée", "media": "moyenne", "bassa": "faible"},
        "de": {"alta": "hoch", "media": "mittel", "bassa": "niedrig"},
        "es": {"alta": "alta", "media": "media", "bassa": "baja"},
    }[language]
    lines = [
        f"# {copy['title']}",
        "",
        f"- {copy['attempted']}: {len(evidence)}",
        f"- {copy['readable']}: {len(readable)}",
        f"- {copy['unreadable']}: {len(unreadable)}",
        "",
    ]
    if unreadable:
        lines.extend([f"## {copy['verify']}", ""])
        for record in unreadable:
            note = f" — {', '.join(record.notes)}" if record.notes else ""
            lines.append(
                f"- `{record.relative_path}`: {record.extraction_method}{note}"
            )
        lines.append("")
    if readable:
        lines.extend([f"## {copy['extracted']}", ""])
        for record in readable:
            lines.append(
                f"- `{record.relative_path}`: {record.extraction_method}, "
                f"{record.char_count} {copy['characters']}, {copy['confidence']} "
                f"{confidence_copy.get(record.confidence, record.confidence)}"
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
        "--language",
        choices=("it", "en", "fr", "de", "es"),
        default="it",
        help="Lingua del report di estrazione.",
    )
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
        language=args.language,
    )
    LOGGER.info("Estratti %s documenti in %s", len(evidence), out_dir)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
