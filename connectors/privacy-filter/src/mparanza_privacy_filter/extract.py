"""Extract document text mechanically, without recreating document layout."""

from __future__ import annotations

from io import BytesIO
from pathlib import Path
from zipfile import ZipFile

from defusedxml.ElementTree import fromstring
from pypdf import PdfReader

from .contracts import FORMATS, FilterError

__all__ = ["extract_text"]

MAX_BYTES = 25 * 1024 * 1024
MAX_CHARACTERS = 500_000
MAX_XML_BYTES = 64 * 1024 * 1024
WORD = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"


def extract_text(path: Path) -> str:
    """Read supported text; reject empty/scanned pages rather than omit them."""
    if path.suffix.lower() not in FORMATS:
        raise FilterError("unsupported_format")
    with path.open("rb") as handle:
        raw = handle.read(MAX_BYTES + 1)
    if len(raw) > MAX_BYTES:
        raise FilterError("file_too_large")
    suffix = path.suffix.lower()
    if suffix in (".txt", ".md", ".markdown"):
        text = raw.decode("utf-8-sig")
    elif suffix == ".pdf":
        reader = PdfReader(BytesIO(raw))
        if reader.is_encrypted:
            raise FilterError("encrypted_pdf")
        pages = []
        for page in reader.pages:
            page_text = page.extract_text() or ""
            # A scan or blank page cannot be treated as successfully extracted.
            if not page_text.strip():
                raise FilterError("pdf_page_without_text_requires_review_or_ocr")
            pages.append(page_text)
        text = "\n\n".join(pages)
    else:
        text = _docx_text(raw)
    if not text.strip():
        raise FilterError("empty_document")
    if len(text) > MAX_CHARACTERS:
        raise FilterError("text_too_large")
    return text


def _docx_text(raw: bytes) -> str:
    """Include body, tables, text boxes, headers, footers, notes and comments."""
    with ZipFile(BytesIO(raw)) as archive:
        if "word/document.xml" not in archive.namelist():
            raise FilterError("invalid_docx")
        if sum(item.file_size for item in archive.infolist()) > MAX_XML_BYTES:
            raise FilterError("docx_expansion_too_large")
        parts = ["word/document.xml"] + sorted(
            name
            for name in archive.namelist()
            if name.startswith("word/")
            and name.endswith(".xml")
            and (
                name.startswith(("word/header", "word/footer"))
                or name
                in ("word/footnotes.xml", "word/endnotes.xml", "word/comments.xml")
            )
        )
        chunks = []
        for name in parts:
            root = fromstring(archive.read(name))
            for node in root.iter():
                if node.tag in (WORD + "t", WORD + "delText"):
                    chunks.append(node.text or "")
                elif node.tag in (WORD + "p", WORD + "br", WORD + "cr"):
                    chunks.append("\n")
                elif node.tag == WORD + "tab":
                    chunks.append("\t")
            chunks.append("\n")
        return "".join(chunks)
