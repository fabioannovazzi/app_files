# pdf_utils.py – richer PDF ⇒ Markdown extractor
# ---------------------------------------------------------------
# Fully offline helper that converts a PDF upload into Markdown with:
#   • page‑breaks (\f),
#   • inferred headings ( # / ## ),
#   • bullet / numbered lists,
#   • **bold** spans (font contains "Bold"),
#   • hidden link annotations → [anchor](url),
#   • foot‑notes inlined as clickable refs.
#
# It returns **only** a string so downstream code that expects plain
# Markdown keeps working.  No external storage, no temp files.

from __future__ import annotations

import html
import logging
import re
import statistics
import unicodedata
from io import BytesIO
from typing import Dict, Iterable, List, NamedTuple

import fitz
import pdfplumber
from pdf2image import convert_from_bytes
from PIL import Image

from modules.utilities.ui_notifier import ui

logging.getLogger("pdfminer").setLevel(logging.ERROR)

__all__ = [
    "extract_pdf_rich",
    "extract_pdf_text_with_ocr",
    "PDFExtractionResult",
    "ExtractionAttempt",
]


class ExtractionAttempt(NamedTuple):
    """Represents a single extraction attempt."""

    method: str
    success: bool
    error: str | None = None


class PDFExtractionResult(NamedTuple):
    """Text result with extraction method, attempt log and failure step."""

    text: str
    method: str
    attempts: List[ExtractionAttempt]
    step_failed: str


BULLET_GLYPHS = {"•", "▪", "‣", "–", "—", "∙"}

# --------------------------------------------------------------------
# low‑level helpers ---------------------------------------------------
# --------------------------------------------------------------------


_SUP = "¹²³⁴⁵⁶⁷⁸⁹⁰"
_SUP_RE = re.compile(r"(?<=\w)([" + _SUP + r"])(?=\w)")
_SUP_MAP = str.maketrans(_SUP, "1234567890")  # ¹→1 …


def _compile_result(
    text: str, method: str, attempts: List[ExtractionAttempt]
) -> PDFExtractionResult:
    """Return a ``PDFExtractionResult`` with the last failed step."""

    step_failed = "" if text.strip() else (attempts[-1].method if attempts else "")
    return PDFExtractionResult(text, method, attempts, step_failed)


def _page_words(page) -> Iterable[Dict]:
    """Yield word-dicts with coords & font info.

    Some pdfplumber versions don't include font size/font name by default.
    Request them via ``extra_attrs`` and guard if still missing.
    """
    for w in page.extract_words(
        x_tolerance=1.5,
        y_tolerance=3,
        keep_blank_chars=False,
        use_text_flow=False,
        extra_attrs=["size", "fontname"],
    ):
        yield {
            "text": w["text"],
            "x": w["x0"],
            "y": w["top"],
            "size": w.get("size"),
            "font": w.get("fontname", ""),
        }


def _group_lines(words: List[Dict], y_tol=2.0):
    """Cluster words into visual lines (return sorted list)."""
    buckets = {}
    for w in words:
        key = next((k for k in buckets if abs(k - w["y"]) <= y_tol), None)
        buckets.setdefault(key if key else w["y"], []).append(w)
    return [(k, sorted(v, key=lambda w: w["x"])) for k, v in sorted(buckets.items())]


# ---------- link merge --------------------------------------------------


def _merge_links(pdf_bytes: bytes, lines: list[str]) -> list[str]:
    """Insert hyperlinks into ``lines`` using PyMuPDF annotations.

    This mirrors the previous pypdf-based approach but relies solely on
    ``fitz`` (PyMuPDF), which is already a core dependency.  Each ``/URI``
    annotation is mapped to an approximate line number based on its vertical
    position, assuming a 12‑pt line height.
    """

    out = lines[:]
    ln = 0
    with fitz.open(stream=pdf_bytes, filetype="pdf") as doc:
        for page in doc:
            for link in page.get_links():
                uri = link.get("uri")
                rect = link.get("from")
                if not uri or rect is None:
                    continue
                # convert top-based coordinates to bottom-based like the pypdf code
                y0 = page.mediabox.y1 - rect.y1
                line_idx = ln + int(y0 // 12)
                if 0 <= line_idx < len(out):
                    line = out[line_idx]
                    if uri not in line and " " in line:
                        pre, word = line.rsplit(" ", 1)
                        out[line_idx] = f"{pre} [{word}]({uri})"
            ln += int(page.mediabox.y1 // 12) + 2  # 2 for blank lines
    return out


def ocr_page(image: Image.Image, lang: str = "eng") -> str:
    """Return OCR text from *image* using the shared PaddleOCR extractor."""

    return _extract_paddle_ocr_text(image, lang=lang)


def _render_pdf_pages_with_fitz(
    pdf_bytes: bytes, max_pages: int = 50
) -> list[Image.Image]:
    """Render PDF pages to PIL images using PyMuPDF."""

    images: list[Image.Image] = []
    zoom = fitz.Matrix(300.0 / 72.0, 300.0 / 72.0)  # ~300 DPI rasterization
    with fitz.open(stream=pdf_bytes, filetype="pdf") as doc:
        for page in doc[:max_pages]:
            pix = page.get_pixmap(matrix=zoom, alpha=False)
            image = Image.open(BytesIO(pix.tobytes("png")))
            image.load()
            images.append(image)
    return images


def _extract_paddle_ocr_text(image: Image.Image, lang: str = "eng") -> str:
    """Extract OCR text from a page image using the shared slide PaddleOCR stack."""

    from modules.slides.ocr import extract_text_from_image_bytes

    image_buf = BytesIO()
    image.save(image_buf, format="PNG")
    return extract_text_from_image_bytes(
        image_buf.getvalue(),
        lang=lang,
        preprocess_profile="document_scan",
        allow_preprocess_fallback=True,
    )


# ---------- main --------------------------------------------------------
def extract_pdf_rich(file_like, *, max_pages=50) -> str:
    raw_bytes = file_like.read()
    file_like.seek(0)

    md_lines: List[str] = []

    with pdfplumber.open(file_like) as pdf:
        for page in pdf.pages[:max_pages]:
            words = list(_page_words(page))
            for y, wline in _group_lines(words):
                txt = " ".join(w["text"] for w in wline)

                # superscript citations → add blanks + normal digits
                txt = _SUP_RE.sub(
                    lambda m: f" [{m.group(1).translate(_SUP_MAP)}] ", txt
                )

                # ligatures, NB-SP, html entities
                txt = html.unescape(txt).replace("\u00a0", " ")
                txt = unicodedata.normalize("NFKD", txt)

                # heading / bold heuristics (size-based; guard if size missing)
                _sizes = [
                    w.get("size")
                    for w in wline
                    if isinstance(w.get("size"), (int, float))
                ]
                if _sizes:
                    med = statistics.median(_sizes)
                    max_sz = max(_sizes)
                    if max_sz >= 1.4 * med:
                        txt = "# " + txt.lstrip()
                    elif max_sz >= 1.2 * med:
                        txt = "## " + txt.lstrip()
                if all("Bold" in w["font"] or "Semi" in w["font"] for w in wline):
                    txt = f"**{txt.strip()}**"

                md_lines.append(txt)
            md_lines.append("")  # visual para break → blank line

    # inject hyperlinks from /URI annotations
    md_lines = _merge_links(raw_bytes, md_lines)

    md = "\n".join(md_lines).strip()

    # safety valve: fall back to pdfminer only if almost no spaces
    if len(md) < 100 or md.count(" ") < len(md) // 200:
        try:
            from pdfminer.high_level import extract_text

            md = extract_text(BytesIO(raw_bytes), maxpages=max_pages) or md
        except Exception as e:
            logging.exception(e)
            ui.error("Something went wrong while extracting text from the PDF.")
            return md

    return md


def _extract_pdf_text_with_ocr_once(
    pdf_bytes: bytes, max_pages: int = 50, llm_wrapper=None, lang: str = "eng"
) -> PDFExtractionResult:
    """Single pass PDF text extraction with local PaddleOCR fallback.

    ``llm_wrapper`` is accepted for caller compatibility and intentionally
    ignored. OCR must not call hosted model APIs.
    """
    attempts: List[ExtractionAttempt] = []
    text_content = ""
    method = ""

    try:
        with pdfplumber.open(BytesIO(pdf_bytes)) as pdf:
            for page in pdf.pages[:max_pages]:
                page_text = page.extract_text() or ""
                if page_text:
                    text_content += page_text + "\n"
        success = bool(text_content.strip())
        attempts.append(ExtractionAttempt("pdfplumber", success))
        if success:
            return _compile_result(text_content, "pdfplumber", attempts)
    except Exception as e:  # pragma: no cover - rare I/O errors
        logging.exception(e)
        attempts.append(ExtractionAttempt("pdfplumber", False, str(e)))
        text_content = ""

    try:
        doc = fitz.open(stream=pdf_bytes, filetype="pdf")
        extracted_pages = [page.get_text() for page in doc][:max_pages]
        doc.close()
        text_content = "\n".join(extracted_pages)
        success = bool(text_content.strip())
        attempts.append(ExtractionAttempt("fitz", success))
        if success:
            return _compile_result(text_content, "fitz", attempts)
    except Exception as e:  # pragma: no cover - PyMuPDF load failure
        logging.exception(e)
        attempts.append(ExtractionAttempt("fitz", False, str(e)))
        text_content = ""

    def _run_paddle_ocr_on_pages(
        page_images: list[Image.Image],
    ) -> tuple[list[str], list[str], bool, bool]:
        page_texts: list[str] = []
        errors: list[str] = []
        used = False
        for img in page_images:
            try:
                paddle_txt = _extract_paddle_ocr_text(img, lang=lang)
                if paddle_txt.strip():
                    used = True
                page_texts.append(paddle_txt)
            except Exception as e:  # pragma: no cover - optional engine unavailable
                errors.append(str(e))
                page_texts.append("")
        success = any(t.strip() for t in page_texts)
        return page_texts, errors, success, used

    pages: list[Image.Image] = []
    raster_source = ""
    try:
        pages = _render_pdf_pages_with_fitz(pdf_bytes, max_pages=max_pages)
        attempts.append(ExtractionAttempt("fitz_raster", bool(pages)))
        if pages:
            raster_source = "fitz"
    except Exception as e:  # pragma: no cover - unexpected raster failure
        logging.exception(e)
        attempts.append(ExtractionAttempt("fitz_raster", False, str(e)))

    if not pages:
        try:
            pages = convert_from_bytes(pdf_bytes, dpi=300)[:max_pages]
            attempts.append(ExtractionAttempt("pdf2image_raster", bool(pages)))
            if pages:
                raster_source = "pdf2image"
        except Exception as e:  # pragma: no cover - poppler/conversion failures
            logging.exception(e)
            attempts.append(ExtractionAttempt("pdf2image_raster", False, str(e)))

    if not pages:
        attempts.append(
            ExtractionAttempt("ocr", False, "No rasterized pages available for OCR.")
        )
        return _compile_result(text_content, method or "error", attempts)

    ocr_text_pages, paddle_errors, paddle_success, used_paddle = (
        _run_paddle_ocr_on_pages(pages)
    )

    # If OCR on PyMuPDF rasters is empty, try pdf2image rasters before giving up.
    if not paddle_success and raster_source == "fitz":
        fallback_pages: list[Image.Image] = []
        try:
            fallback_pages = convert_from_bytes(pdf_bytes, dpi=300)[:max_pages]
            attempts.append(ExtractionAttempt("pdf2image_raster", bool(fallback_pages)))
        except Exception as e:  # pragma: no cover - poppler/conversion failures
            logging.exception(e)
            attempts.append(ExtractionAttempt("pdf2image_raster", False, str(e)))

        if fallback_pages:
            (
                fallback_texts,
                fallback_errors,
                fallback_success,
                fallback_used,
            ) = _run_paddle_ocr_on_pages(fallback_pages)
            paddle_errors.extend(fallback_errors)
            if fallback_success:
                ocr_text_pages = fallback_texts
                paddle_success = True
                used_paddle = fallback_used

    attempts.append(
        ExtractionAttempt(
            "paddle_ocr",
            paddle_success,
            (
                None
                if paddle_success or not paddle_errors
                else "; ".join(paddle_errors[:2])
            ),
        )
    )
    method = "paddle_ocr" if used_paddle else "error"

    text_content = "\n\n".join(ocr_text_pages)
    if not text_content.strip():
        method = "error"
    return _compile_result(text_content, method or "ocr", attempts)


def extract_pdf_text_with_ocr(
    pdf_bytes: bytes,
    max_pages: int = 50,
    llm_wrapper=None,
    lang: str = "eng",
    retries: int = 3,
) -> PDFExtractionResult:
    """Return extracted text with optional retry attempts.

    ``retries`` controls how many times the extraction pipeline is executed.
    The process stops early as soon as text is successfully extracted.
    ``llm_wrapper`` is ignored so OCR remains local-only.
    """
    all_attempts: List[ExtractionAttempt] = []
    final_text = ""
    method = ""
    for _ in range(max(retries, 1)):
        result = _extract_pdf_text_with_ocr_once(
            pdf_bytes, max_pages=max_pages, llm_wrapper=llm_wrapper, lang=lang
        )
        all_attempts.extend(result.attempts)
        method = result.method
        if result.text.strip():
            final_text = result.text
            break
    step_failed = (
        "" if final_text.strip() else (all_attempts[-1].method if all_attempts else "")
    )
    return PDFExtractionResult(final_text, method or "error", all_attempts, step_failed)
