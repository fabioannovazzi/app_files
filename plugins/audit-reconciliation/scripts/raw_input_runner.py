"""Raw input ingestion for generic audit reconciliation workpapers.

This module is intentionally generic. It does not know customer names,
counterparties, invoice numbers, banks, or factor operators. Engagement-specific
details must be passed through ``assumptions``.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta
from decimal import Decimal, InvalidOperation
from functools import lru_cache
import hashlib
import io
import json
import os
import re
import sys
import zipfile
from pathlib import Path
from typing import Any, Callable, Iterable

try:
    import fitz  # type: ignore
except (
    Exception
) as exc:  # pragma: no cover - optional dependency import failures are reported at runtime
    fitz = None  # type: ignore
    FITZ_IMPORT_ERROR: Exception | None = exc
else:
    FITZ_IMPORT_ERROR = None

try:
    from openpyxl import load_workbook
except (
    Exception
) as exc:  # pragma: no cover - optional dependency import failures are reported at runtime
    load_workbook = None  # type: ignore
    OPENPYXL_IMPORT_ERROR: Exception | None = exc
else:
    OPENPYXL_IMPORT_ERROR = None

try:
    import pdfplumber
except (
    Exception
) as exc:  # pragma: no cover - optional dependency import failures are reported at runtime
    pdfplumber = None  # type: ignore
    PDFPLUMBER_IMPORT_ERROR: Exception | None = exc
else:
    PDFPLUMBER_IMPORT_ERROR = None

try:
    from .reconciliation_helpers import (
        clean_text,
        document_key,
        parse_decimal,
        parse_date,
        reconcile_open_items,
        reconciliation_checks,
        checks_pass,
    )
    from .reconciliation_workflow import build_reconciliation_artifacts
    from .review_session import write_review_session_artifacts
    from .build_missing_evidence_requests import (
        build_missing_evidence_request_pack,
        write_missing_evidence_workbook,
    )
    from .locale_support import (
        any_keyword_in,
        configured_language,
        keyword_tuple,
        language_candidates,
        normalize_language,
    )
except ImportError:  # pragma: no cover - direct import support
    scripts_dir = Path(__file__).resolve().parent
    if str(scripts_dir) not in sys.path:
        sys.path.insert(0, str(scripts_dir))
    from reconciliation_helpers import (  # type: ignore
        clean_text,
        document_key,
        parse_decimal,
        parse_date,
        reconcile_open_items,
        reconciliation_checks,
        checks_pass,
    )
    from reconciliation_workflow import build_reconciliation_artifacts  # type: ignore
    import importlib.util

    _review_session_path = Path(__file__).resolve().parent / "review_session.py"
    _review_session_spec = importlib.util.spec_from_file_location(
        "mparanza_audit_reconciliation_review_session",
        _review_session_path,
    )
    assert _review_session_spec and _review_session_spec.loader
    _review_session = importlib.util.module_from_spec(_review_session_spec)
    sys.modules[_review_session_spec.name] = _review_session
    _review_session_spec.loader.exec_module(_review_session)
    write_review_session_artifacts = _review_session.write_review_session_artifacts
    from build_missing_evidence_requests import (  # type: ignore
        build_missing_evidence_request_pack,
        write_missing_evidence_workbook,
    )
    from locale_support import any_keyword_in, configured_language, keyword_tuple, language_candidates, normalize_language  # type: ignore


DATE_DMY4_RE = re.compile(r"\b\d{2}/\d{2}/\d{4}\b")
DATE_DMY2_RE = re.compile(r"\b\d{2}/\d{2}/\d{2}\b")
AMOUNT_IT_RE = re.compile(r"-?\d{1,3}(?:[.,]\d{3})*[.,]\d{2}-?|-?\d+[.,]\d{2}-?")
OPEN_ITEM_DOC_RE = re.compile(r"\b\d{2}[A-Z]{2}\d{2}/\d{3,}\b")
LEDGER_DOC_LINE_RE = re.compile(
    r"(?P<date>\d{2}/\d{2}/\d{4})\s+(?P<doc>[A-Z0-9./-]{2,})\b",
    re.I,
)
LEDGER_SETTLEMENT_RE = re.compile(
    r"\b(?:N\.?|NO\.?)\s*(?P<doc>[A-Z0-9./-]+)\s+(?:del|dated?|du|fecha)\s+(?P<date>\d{6,8})\b",
    re.I,
)
GIT_WORKSPACE_ROOT = Path(__file__).resolve().parents[3]


def _is_relative_to(candidate: Path, parent: Path) -> bool:
    try:
        candidate.relative_to(parent)
    except ValueError:
        return False
    return True


def validate_run_output_dir(output_dir: str | Path, *, input_dir: str | Path) -> Path:
    """Return a resolved output directory, rejecting Git/GitHub Pages locations."""

    resolved = Path(output_dir).expanduser().resolve()
    workspace_root = GIT_WORKSPACE_ROOT.resolve()
    if _is_relative_to(resolved, workspace_root):
        recommended = Path(input_dir).expanduser().resolve().parent / "output"
        raise ValueError(
            "Audit Reconciliation output_dir must be outside the Git workspace; "
            f"got {resolved}. Use a sibling output directory such as {recommended}."
        )
    return resolved


def validate_run_cache_dir(cache_dir: str | Path, *, input_dir: str | Path) -> Path:
    """Return a resolved cache directory, rejecting repo-local run caches."""

    resolved = Path(cache_dir).expanduser().resolve()
    workspace_root = GIT_WORKSPACE_ROOT.resolve()
    if _is_relative_to(resolved, workspace_root):
        recommended = (
            Path(input_dir).expanduser().resolve().parent
            / "output"
            / ".audit_reconciliation_cache"
        )
        raise ValueError(
            "Audit Reconciliation cache_dir must be outside the Git workspace; "
            f"got {resolved}. Use an output-local cache such as {recommended}."
        )
    return resolved


JOURNAL_HEADER_RE = re.compile(
    r"^(?P<date>\d{2}/\d{2}/\d{4})\s+(?P<causale>[A-Z][A-Z ]+?)(?:\s+A\s+-|\s+\d+\s+-|\s{2,}|$)"
)
JOURNAL_ACCOUNT_RE = re.compile(
    r"^\s*(?P<line>\d{1,8})\s+(?P<account>\d+\s*/\s*\d+\s*/\s*\d+)\s+"
)
BANK_ROW_RE = re.compile(
    r"^(?P<date>\d{2}/\d{2}/\d{2})\s+"
    r"(?P<value_date>\d{2}/\d{2}/\d{2})\s+"
    r"(?P<amount>\d{1,3}(?:[.,]\d{3})*[.,]\d{2})\s+"
    r"(?P<description>.+)$"
)
PAYMENT_ORDER_HEADER_RE = re.compile(
    r"\b(?:Distinta|Payment\s+Order|Payment\s+Batch|Remittance\s+Order|Ordre\s+de\s+Paiement|Lot\s+de\s+Paiement|Orden\s+de\s+Pago|Remesa\s+de\s+Pago|Lote\s+de\s+Pago)"
    r"\s+0*(?P<batch>\d+)\s+(?:Del|Dated?|Date|Du|Fecha)\s+(?P<date>\d{2}/\d{2}/\d{4})",
    re.I,
)
PAYMENT_ORDER_TOTAL_RE = re.compile(
    r"\b(?:Totale\s+Distinta|Total\s+Payment\s+Order|Total\s+Batch|Batch\s+Total|Total\s+Ordre|Total\s+Remise|Total\s+Lot|Total\s+Orden|Total\s+Remesa|Total\s+Lote)"
    r"\s+(?P<amount>-?\d{1,3}(?:[.,]\d{3})*[.,]\d{2}-?|-?\d+[.,]\d{2}-?)",
    re.I,
)
PAYMENT_ORDER_LINE_RE = re.compile(
    r"\b(?P<counterparty_doc>\d{1,7}[-/]\d{2})\s+"
    r"(?:(?:Fattura|Invoice|Facture|Factura)\s+)?"
    r"(?P<counterparty_date>\d{2}/\d{2}/\d{4})\s+"
    r"(?P<document_no>\d{1,7}[-/]\d{2})\s+"
    r"(?P<document_date>\d{2}/\d{2}/\d{4})\s+"
    r"(?P<withholding>-?\d{1,3}(?:[.,]\d{3})*[.,]\d{2}-?|-?\d+[.,]\d{2}-?)\s+"
    r"(?P<invoice_amount>-?\d{1,3}(?:[.,]\d{3})*[.,]\d{2}-?|-?\d+[.,]\d{2}-?)\s+"
    r"(?P<withholding_amount>-?\d{1,3}(?:[.,]\d{3})*[.,]\d{2}-?|-?\d+[.,]\d{2}-?)",
    re.I,
)
PAYMENT_BATCH_RE = re.compile(
    r"\b(?:DIST(?:INTA)?\.?\s*(?:PAG(?:AMENTO|\.TO)?|PG)?\.?|PAYMENT\s+BATCH|BATCH|REMITTANCE|REMESA|LOTE|LOT)\s*(?:NR\.?|NO\.?)?\s*(?P<ref>\d{1,5}(?:\s*-\s*\d{1,5})?)",
    re.I,
)
PDF_PAGE_CACHE_VERSION = "raw_pdf_pages_v2"
OPENING_ENTRY_TERMS = (
    "apertura esercizio",
    "riapertura",
    "saldo iniziale",
    "opening balance",
    "opening entry",
    "balance brought forward",
    "a-nouveau",
    "à-nouveau",
    "apertura ejercicio",
    "saldo inicial",
)
BANK_ACCOUNT_TERMS = (
    "banca",
    "banco",
    "bank",
    "banque",
    "kontoauszug",
    "bankkonto",
    "conto corrente",
    "c/c",
)


@dataclass
class SourcePage:
    source_file: str
    source_role: str
    source_page: int
    extraction_method: str
    text_length: int
    line_count: int
    text: str


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def source_inventory(
    input_dir: str | Path, assumptions: dict[str, Any] | None = None
) -> list[dict[str, Any]]:
    root = Path(input_dir)
    language = configured_language(assumptions, purpose="document")
    rows: list[dict[str, Any]] = []
    for path in sorted(
        p for p in root.iterdir() if p.is_file() and not p.name.startswith(".")
    ):
        rows.append(
            {
                "source_file": path.name,
                "source_role": infer_source_role(path, language=language),
                "suffix": path.suffix.lower(),
                "size_bytes": path.stat().st_size,
                "sha256": sha256_file(path),
            }
        )
    return rows


def infer_source_role(
    path: str | Path, sample_text: str = "", language: object | None = None
) -> str:
    name = Path(path).name.lower()
    text = f"{name} {sample_text}".lower()
    candidates = language_candidates(language)
    for candidate in candidates:
        if any_keyword_in(text, keyword_tuple(candidate, "role_keywords", "ledger")):
            return "ledger"
    role_order = (
        "open_items",
        "bank_statement",
        "journal",
        "payment_order",
        "ledger",
        "factoring_statement",
    )
    for role in role_order:
        for candidate in candidates:
            if any_keyword_in(text, keyword_tuple(candidate, "role_keywords", role)):
                return role
    for candidate in candidates:
        if any_keyword_in(
            text, keyword_tuple(candidate, "evidence_keywords", "factoring")
        ):
            return "factoring_statement"
    return "unknown"


def configure_ocr_environment(cache_dir: Path) -> None:
    (cache_dir / "paddlex").mkdir(parents=True, exist_ok=True)
    (cache_dir / "matplotlib").mkdir(parents=True, exist_ok=True)
    os.environ.setdefault("PADDLE_PDX_CACHE_HOME", str(cache_dir / "paddlex"))
    # Deterministic source selection: BOS is Paddle's direct model host and
    # avoids Hugging Face/Xet range failures observed during OCR bootstrap.
    os.environ.setdefault("PADDLE_PDX_MODEL_SOURCE", "bos")
    os.environ.setdefault("PADDLE_PDX_DISABLE_MODEL_SOURCE_CHECK", "True")
    os.environ.setdefault("MPLCONFIGDIR", str(cache_dir / "matplotlib"))
    os.environ.setdefault("FLAGS_use_mkldnn", "0")


def _ocr_language(language: object | None) -> str:
    text = clean_text(language).lower().replace("_", "-")
    code = text.split("-", 1)[0]
    return code if code in {"de", "en", "fr", "it"} else "en"


def _shared_ocr_text_from_image_bytes(
    image_bytes: bytes,
    *,
    lang: str,
    text_recognition_model_name: str | None = None,
) -> str | None:
    try:
        from modules.slides.ocr import (  # type: ignore
            extract_raw_ocr_from_image_bytes,
            extract_text_from_raw_ocr_result,
        )
    except Exception:
        return None

    raw = extract_raw_ocr_from_image_bytes(
        image_bytes,
        lang=lang,
        preprocess_profile="document_scan",
        allow_preprocess_fallback=True,
        text_recognition_model_name=text_recognition_model_name,
    )
    return extract_text_from_raw_ocr_result(raw)


@lru_cache(maxsize=8)
def _get_local_paddle_ocr(
    lang: str, text_recognition_model_name: str | None = None
) -> object:
    try:
        from paddleocr import PaddleOCR  # type: ignore
    except Exception as exc:  # pragma: no cover - depends on optional OCR install
        raise RuntimeError(
            "PaddleOCR is required for scanned PDF OCR. Install the plugin "
            "optional OCR dependencies from requirements-ocr.txt."
        ) from exc

    modern_kwargs: dict[str, object] = {
        "lang": lang,
        "use_doc_orientation_classify": False,
        "use_doc_unwarping": False,
        "use_textline_orientation": False,
    }
    if text_recognition_model_name:
        modern_kwargs["text_recognition_model_name"] = text_recognition_model_name
    try:
        return PaddleOCR(**modern_kwargs)
    except TypeError:
        legacy_kwargs: dict[str, object] = {
            "lang": lang,
            "show_log": False,
            "use_angle_cls": False,
        }
        return PaddleOCR(**legacy_kwargs)


def _raw_ocr_text(raw: object) -> str:
    texts: list[str] = []

    def collect(value: object) -> None:
        if value is None:
            return
        if isinstance(value, dict):
            for key in ("rec_texts", "texts"):
                nested = value.get(key)
                if isinstance(nested, list):
                    for item in nested:
                        if isinstance(item, str) and clean_text(item):
                            texts.append(clean_text(item))
                    return
            text = value.get("text")
            if isinstance(text, str) and clean_text(text):
                texts.append(clean_text(text))
                return
            for nested in value.values():
                collect(nested)
            return
        if isinstance(value, (list, tuple)):
            if (
                len(value) >= 2
                and isinstance(value[1], (list, tuple))
                and value[1]
                and isinstance(value[1][0], str)
            ):
                text = clean_text(value[1][0])
                if text:
                    texts.append(text)
                return
            for nested in value:
                collect(nested)

    collect(raw)
    return "\n".join(texts)


def _local_paddle_ocr_text_from_image_bytes(
    image_bytes: bytes,
    *,
    lang: str,
    text_recognition_model_name: str | None = None,
) -> str:
    from PIL import Image  # type: ignore
    import numpy as np  # type: ignore

    image = Image.open(io.BytesIO(image_bytes)).convert("RGB")
    engine = _get_local_paddle_ocr(
        lang, text_recognition_model_name=text_recognition_model_name
    )
    image_array = np.asarray(image)
    if hasattr(engine, "ocr"):
        raw = engine.ocr(image_array, cls=True)
    elif hasattr(engine, "predict"):
        raw = engine.predict(image_array)
    else:
        raise RuntimeError("No compatible PaddleOCR inference method is available.")
    return _raw_ocr_text(raw)


def _ocr_page_text(
    pdf_path: Path,
    page_index: int,
    cache_dir: Path,
    dpi_scale: float = 2.0,
    language: object | None = None,
) -> str:
    if fitz is None:
        detail = f": {FITZ_IMPORT_ERROR}" if FITZ_IMPORT_ERROR else ""
        raise RuntimeError(
            "PyMuPDF (fitz) is required for OCR on scanned PDFs. "
            "Install the plugin base dependencies from requirements.txt"
            f"{detail}"
        )
    configure_ocr_environment(cache_dir)
    doc = fitz.open(pdf_path)
    page = doc[page_index]
    pix = page.get_pixmap(matrix=fitz.Matrix(dpi_scale, dpi_scale), alpha=False)
    image_bytes = pix.tobytes("png")
    lang = _ocr_language(language)
    shared_text = _shared_ocr_text_from_image_bytes(
        image_bytes,
        lang=lang,
        text_recognition_model_name="PP-OCRv5_server_rec",
    )
    if shared_text is not None:
        return shared_text
    return _local_paddle_ocr_text_from_image_bytes(
        image_bytes,
        lang=lang,
        text_recognition_model_name="PP-OCRv5_server_rec",
    )


def _pdf_page_cache_path(
    path: Path, cache_dir: Path, *, ocr_scanned: bool, dpi_scale: float
) -> Path:
    content_hash = sha256_file(path)
    cache_key = hashlib.sha256(
        json.dumps(
            {
                "version": PDF_PAGE_CACHE_VERSION,
                "source_file": path.name,
                "content_sha256": content_hash,
                "ocr_scanned": ocr_scanned,
                "dpi_scale": dpi_scale,
            },
            sort_keys=True,
        ).encode("utf-8")
    ).hexdigest()
    return cache_dir / "pdf_pages" / f"{cache_key}.json"


def _read_pdf_page_cache(cache_path: Path, source_name: str) -> list[SourcePage] | None:
    if not cache_path.exists():
        return None
    payload = json.loads(cache_path.read_text(encoding="utf-8"))
    if payload.get("version") != PDF_PAGE_CACHE_VERSION:
        return None
    rows = payload.get("pages")
    if not isinstance(rows, list):
        return None
    pages: list[SourcePage] = []
    for row in rows:
        if not isinstance(row, dict):
            return None
        page = SourcePage(
            **{field: row.get(field, "") for field in SourcePage.__dataclass_fields__}
        )
        page.source_file = source_name
        pages.append(page)
    return pages


def _write_pdf_page_cache(cache_path: Path, pages: list[SourcePage]) -> None:
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = cache_path.with_suffix(".tmp")
    tmp_path.write_text(
        json.dumps(
            {
                "version": PDF_PAGE_CACHE_VERSION,
                "pages": [asdict(page) for page in pages],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    tmp_path.replace(cache_path)


def extract_pdf_pages(
    path: Path,
    cache_dir: Path,
    *,
    ocr_scanned: bool = True,
    use_cache: bool = True,
    dpi_scale: float = 2.0,
    language: object | None = None,
    progress_every_pages: int = 10,
    progress_callback: Callable[[dict[str, Any]], None] | None = None,
) -> list[SourcePage]:
    if pdfplumber is None:
        detail = f": {PDFPLUMBER_IMPORT_ERROR}" if PDFPLUMBER_IMPORT_ERROR else ""
        raise RuntimeError(f"pdfplumber is required for PDF extraction{detail}")
    cache_path = _pdf_page_cache_path(
        path, cache_dir, ocr_scanned=ocr_scanned, dpi_scale=dpi_scale
    )
    if use_cache:
        cached_pages = _read_pdf_page_cache(cache_path, path.name)
        if cached_pages is not None:
            if progress_callback:
                progress_callback(
                    {
                        "event": "pdf_cache_hit",
                        "source_file": path.name,
                        "page_count": len(cached_pages),
                    }
                )
            return cached_pages
    pages: list[SourcePage] = []
    with pdfplumber.open(path) as pdf:
        page_count = len(pdf.pages)
        if progress_callback:
            progress_callback(
                {
                    "event": "pdf_file_start",
                    "source_file": path.name,
                    "page_count": page_count,
                }
            )
        total_text_length = 0
        ocr_page_count = 0
        progress_every = max(1, int(progress_every_pages or 1))
        for index, page in enumerate(pdf.pages):
            text = page.extract_text() or ""
            method = "pdf_text"
            if ocr_scanned and len(text.strip()) < 40:
                ocr_page_count += 1
                if progress_callback:
                    progress_callback(
                        {
                            "event": "ocr_page_start",
                            "source_file": path.name,
                            "source_page": index + 1,
                            "page_count": page_count,
                        }
                    )
                text = _ocr_page_text(
                    path,
                    index,
                    cache_dir,
                    dpi_scale=dpi_scale,
                    language=language,
                )
                method = "paddle_ocr"
                if progress_callback:
                    progress_callback(
                        {
                            "event": "ocr_page_done",
                            "source_file": path.name,
                            "source_page": index + 1,
                            "page_count": page_count,
                            "text_length": len(text),
                        }
                    )
            role = infer_source_role(path, text[:1500])
            lines = [line for line in text.splitlines() if clean_text(line)]
            total_text_length += len(text)
            pages.append(
                SourcePage(
                    source_file=path.name,
                    source_role=role,
                    source_page=index + 1,
                    extraction_method=method,
                    text_length=len(text),
                    line_count=len(lines),
                    text=text,
                )
            )
            source_page = index + 1
            if progress_callback and (
                source_page == page_count
                or source_page == 1
                or source_page % progress_every == 0
            ):
                progress_callback(
                    {
                        "event": "pdf_page_done",
                        "source_file": path.name,
                        "source_page": source_page,
                        "page_count": page_count,
                        "extraction_method": method,
                        "text_length": len(text),
                        "line_count": len(lines),
                    }
                )
        if progress_callback:
            progress_callback(
                {
                    "event": "pdf_file_done",
                    "source_file": path.name,
                    "page_count": page_count,
                    "ocr_page_count": ocr_page_count,
                    "text_length": total_text_length,
                }
            )
    if use_cache:
        _write_pdf_page_cache(cache_path, pages)
    return pages


def parse_money(value: object) -> Decimal | None:
    text = clean_text(value)
    if text.endswith("-"):
        parsed = parse_money(text[:-1])
        return -parsed if parsed is not None else None
    parsed = parse_decimal(text)
    return parsed


def amount_string(value: object) -> str:
    parsed = parse_money(value)
    return f"{parsed:.2f}" if parsed is not None else ""


def iso_date(value: object) -> str:
    text = clean_text(value)
    parsed = parse_date(text)
    if parsed:
        return parsed
    match = re.fullmatch(r"(\d{2})/(\d{2})/(\d{2})", text)
    if match:
        day, month, year = match.groups()
        try:
            return (
                datetime.strptime(f"{day}/{month}/20{year}", "%d/%m/%Y")
                .date()
                .isoformat()
            )
        except ValueError:
            return ""
    if re.fullmatch(r"\d{8}", text):
        try:
            return datetime.strptime(text, "%d%m%Y").date().isoformat()
        except ValueError:
            return ""
    if re.fullmatch(r"\d{6}", text):
        try:
            return datetime.strptime(text, "%d%m%y").date().isoformat()
        except ValueError:
            return ""
    return ""


def normalize_open_item_document(raw_doc: str, doc_date: str) -> str:
    text = clean_text(raw_doc).upper().replace(" ", "")
    match = re.match(r"^(?P<yy>\d{2})(?P<kind>[A-Z]{2})\d{2}/0*(?P<num>\d+)$", text)
    if match:
        return document_key(
            f"{int(match.group('num'))}-{match.group('kind')}", doc_date
        )
    return document_key(text, doc_date)


def parse_open_items(
    pages: list[SourcePage], assumptions: dict[str, Any]
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    source_side_map = assumptions.get("open_item_source_sides") or {}
    language = configured_language(assumptions, purpose="document")
    customer_terms = keyword_tuple(language, "side_keywords", "customer")
    supplier_terms = keyword_tuple(language, "side_keywords", "supplier")
    for page in pages:
        if page.source_role != "open_items":
            continue
        side = source_side_map.get(page.source_file)
        if not side:
            lower = page.text.lower() + " " + page.source_file.lower()
            side = (
                "customer"
                if any_keyword_in(lower, customer_terms)
                else ("supplier" if any_keyword_in(lower, supplier_terms) else "")
            )
        lines = [
            clean_text(line) for line in page.text.splitlines() if clean_text(line)
        ]
        line_index = 0
        while line_index < len(lines):
            line = lines[line_index]
            if not OPEN_ITEM_DOC_RE.fullmatch(line):
                line_index += 1
                continue
            doc_no = line
            doc_date = ""
            amount = ""
            balance = ""
            if line_index + 3 < len(lines):
                doc_date = iso_date(lines[line_index + 1])
                amount = amount_string(lines[line_index + 2])
                balance = amount_string(lines[line_index + 3])
            if doc_date and amount:
                document_no = doc_no
                rows.append(
                    {
                        "record_id": f"open:{page.source_file}:p{page.source_page}:l{line_index + 1}",
                        "source_file": page.source_file,
                        "source_page": page.source_page,
                        "source_row": line_index + 1,
                        "source_role": "open_items",
                        "source_side": side,
                        "expected_side": side,
                        "document_no": document_no,
                        "document_date": doc_date,
                        "posting_date": doc_date,
                        "amount": amount,
                        "balance": balance or amount,
                        "currency": assumptions.get("currency", "EUR"),
                        "description": doc_no,
                        "evidence_type": "open_item",
                        "document_key": normalize_open_item_document(doc_no, doc_date),
                    }
                )
                line_index += 4
                continue
            line_index += 1
    return rows


def parse_ledger_or_factoring_pages(
    pages: list[SourcePage], assumptions: dict[str, Any]
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    counterparty_keywords = [
        str(v).lower() for v in assumptions.get("counterparty_keywords", [])
    ]
    factor_keywords = [
        str(v).lower() for v in assumptions.get("factoring_operator_keywords", [])
    ]
    language = configured_language(assumptions, purpose="document")
    invoice_terms = keyword_tuple(language, "evidence_keywords", "invoice")
    closure_terms = keyword_tuple(language, "evidence_keywords", "closure")
    compensation_terms = keyword_tuple(
        language, "evidence_keywords", "compensation"
    ) + keyword_tuple(language, "evidence_keywords", "netting")
    for page in pages:
        if page.source_role not in {"ledger", "factoring_statement"}:
            continue
        lines = [
            clean_text(line) for line in page.text.splitlines() if clean_text(line)
        ]
        current_header = ""
        for idx, line in enumerate(lines, start=1):
            lower = line.lower()
            if any_keyword_in(
                lower, invoice_terms + closure_terms + compensation_terms
            ):
                current_header = line
            doc_match = LEDGER_DOC_LINE_RE.search(line) or LEDGER_SETTLEMENT_RE.search(
                line
            )
            if not doc_match:
                continue
            doc_no = clean_text(doc_match.group("doc"))
            doc_date = iso_date(doc_match.group("date"))
            amounts = AMOUNT_IT_RE.findall(line)
            if not amounts and idx < len(lines):
                amounts = AMOUNT_IT_RE.findall(lines[idx])
            amount = amount_string(
                amounts[-2] if len(amounts) >= 2 else (amounts[-1] if amounts else "")
            )
            text_window = " ".join(lines[max(0, idx - 3) : min(len(lines), idx + 3)])
            classification_text = f"{current_header} {line}".lower()
            evidence_type = "internal_booking"
            if any_keyword_in(classification_text, closure_terms + compensation_terms):
                evidence_type = "internal_closure"
            if any_keyword_in(classification_text, compensation_terms):
                evidence_type = "compensation"
            if page.source_role == "factoring_statement":
                evidence_type = "external_factoring"
            elif any(
                keyword and keyword in text_window.lower()
                for keyword in factor_keywords
            ):
                evidence_type = "factoring_bridge"
            counterparty_context = f"{page.source_file} {text_window}".lower()
            if counterparty_keywords and not any(
                keyword in counterparty_context for keyword in counterparty_keywords
            ):
                if evidence_type == "internal_booking":
                    continue
            rows.append(
                {
                    "record_id": f"evidence:{page.source_file}:p{page.source_page}:l{idx}",
                    "source_file": page.source_file,
                    "source_page": page.source_page,
                    "source_row": idx,
                    "source_role": page.source_role,
                    "document_no": doc_no,
                    "document_date": doc_date,
                    "posting_date": doc_date,
                    "amount": amount,
                    "currency": assumptions.get("currency", "EUR"),
                    "description": text_window or current_header,
                    "evidence_type": evidence_type,
                    "document_key": document_key(doc_no, doc_date),
                }
            )
    return rows


LEDGER_BALANCE_RE = re.compile(
    r"\b20\d{2}\s+"
    r"(?P<amount>-?\d{1,3}(?:[.,]\d{3})*[.,]\d{2}-?|-?\d+[.,]\d{2}-?)\s+"
    r"(?P<balance>-?\d{1,3}(?:[.,]\d{3})*[.,]\d{2}-?|-?\d+[.,]\d{2}-?)\s*"
    r"(?P<sign>[+-])"
)


def parse_ledger_account_header(text: str) -> tuple[str, str]:
    for line in text.splitlines():
        match = re.search(
            r"\bConto:\s*(?P<account>\d+\s*/\s*\d+\s*/\s*\d+)\s+(?P<name>.+)$",
            clean_text(line),
            re.I,
        )
        if match:
            return clean_text(match.group("account")), clean_text(match.group("name"))
    return "", ""


def signed_balance(amount: Decimal, sign: str) -> Decimal:
    return amount if sign == "+" else -amount


def last_ledger_balance(text: str) -> tuple[Decimal | None, str]:
    matches = list(LEDGER_BALANCE_RE.finditer(text))
    if not matches:
        return None, ""
    match = matches[-1]
    balance = parse_money(match.group("balance"))
    if balance is None:
        return None, ""
    sign = match.group("sign")
    return signed_balance(balance, sign), sign


def first_ledger_balance_after(text: str, marker: str) -> tuple[Decimal | None, str]:
    lower = text.lower()
    idx = lower.find(marker.lower())
    if idx < 0:
        return None, ""
    match = LEDGER_BALANCE_RE.search(text[idx : idx + 800])
    if not match:
        return None, ""
    balance = parse_money(match.group("balance"))
    if balance is None:
        return None, ""
    sign = match.group("sign")
    return signed_balance(balance, sign), sign


def parse_ledger_balance_pages(
    pages: list[SourcePage], assumptions: dict[str, Any]
) -> list[dict[str, Any]]:
    counterparty_keywords = [
        clean_text(keyword).lower()
        for keyword in assumptions.get("counterparty_keywords", [])
        if clean_text(keyword)
    ]
    grouped: dict[tuple[str, str, str], list[SourcePage]] = defaultdict(list)
    for page in pages:
        if page.source_role != "ledger":
            continue
        account, account_name = parse_ledger_account_header(page.text)
        if not account:
            continue
        if counterparty_keywords and not any(
            keyword in account_name.lower() for keyword in counterparty_keywords
        ):
            continue
        grouped[(page.source_file, account, account_name)].append(page)

    rows: list[dict[str, Any]] = []
    for (source_file, account, account_name), account_pages in grouped.items():
        account_pages = sorted(account_pages, key=lambda item: item.source_page)
        text = "\n".join(page.text for page in account_pages)
        opening, opening_sign = first_ledger_balance_after(text, "apertura esercizio")
        lower = text.lower()
        cutoff_idx = lower.find("chiusura esercizio")
        if cutoff_idx < 0:
            cutoff_idx = lower.find("dare avere totali")
        closing_text = text[:cutoff_idx] if cutoff_idx >= 0 else text
        closing, closing_sign = last_ledger_balance(closing_text)
        if opening is None and closing is None:
            continue
        rows.append(
            {
                "source_file": source_file,
                "source_role": "ledger",
                "source_pages": f"{account_pages[0].source_page}-{account_pages[-1].source_page}",
                "account": account,
                "account_name": account_name,
                "opening_balance_signed_debit_minus_credit": f"{(opening or Decimal('0.00')):.2f}",
                "opening_balance_sign": opening_sign,
                "closing_balance_signed_debit_minus_credit": f"{(closing or Decimal('0.00')):.2f}",
                "closing_balance_sign": closing_sign,
                "currency": assumptions.get("currency", "EUR"),
                "basis": "Ledger opening and last running balance before closing/totals.",
            }
        )

    total_opening = sum(
        (
            parse_money(row["opening_balance_signed_debit_minus_credit"])
            or Decimal("0.00")
        )
        for row in rows
    )
    total_closing = sum(
        (
            parse_money(row["closing_balance_signed_debit_minus_credit"])
            or Decimal("0.00")
        )
        for row in rows
    )
    if rows:
        rows.insert(
            0,
            {
                "source_file": "TOTAL",
                "source_role": "ledger",
                "source_pages": "",
                "account": "TOTAL",
                "account_name": "All matched counterparty ledgers",
                "opening_balance_signed_debit_minus_credit": f"{total_opening:.2f}",
                "opening_balance_sign": "+" if total_opening >= 0 else "-",
                "closing_balance_signed_debit_minus_credit": f"{total_closing:.2f}",
                "closing_balance_sign": "+" if total_closing >= 0 else "-",
                "currency": assumptions.get("currency", "EUR"),
                "basis": "Sum of matched ledger balances.",
            },
        )
    return rows


def parse_bank_statement_pages(
    pages: list[SourcePage], assumptions: dict[str, Any]
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    counterparty_keywords = [
        str(v).lower() for v in assumptions.get("counterparty_keywords", [])
    ]
    factor_keywords = [
        str(v).lower() for v in assumptions.get("factoring_operator_keywords", [])
    ]
    for page in pages:
        if page.source_role != "bank_statement":
            continue
        lines = [
            clean_text(line) for line in page.text.splitlines() if clean_text(line)
        ]
        current = ""
        current_start = 0
        for idx, line in enumerate(lines, start=1):
            if DATE_DMY2_RE.match(line):
                if current:
                    rows.extend(
                        _bank_row_from_text(
                            page,
                            current,
                            current_start,
                            assumptions,
                            counterparty_keywords,
                            factor_keywords,
                        )
                    )
                current = line
                current_start = idx
            elif current:
                current += " " + line
        if current:
            rows.extend(
                _bank_row_from_text(
                    page,
                    current,
                    current_start,
                    assumptions,
                    counterparty_keywords,
                    factor_keywords,
                )
            )
    return rows


def _bank_row_from_text(
    page: SourcePage,
    text: str,
    source_row: int,
    assumptions: dict[str, Any],
    counterparty_keywords: list[str],
    factor_keywords: list[str] | None = None,
) -> list[dict[str, Any]]:
    match = BANK_ROW_RE.search(text)
    if not match:
        return []
    description = clean_text(match.group("description"))
    factor_keywords = factor_keywords or []
    lower_description = description.lower()
    if (
        counterparty_keywords
        and not any(keyword in lower_description for keyword in counterparty_keywords)
        and not any(keyword in lower_description for keyword in factor_keywords)
    ):
        return []
    posting_date = iso_date(match.group("date"))
    value_date = iso_date(match.group("value_date"))
    amount = amount_string(match.group("amount"))
    batch_ids = extract_payment_batch_ids(description)
    doc_refs = extract_invoice_refs(description, posting_date)
    if not doc_refs:
        doc_refs = [("", "")]
    rows: list[dict[str, Any]] = []
    for doc_no, doc_date in doc_refs:
        rows.append(
            {
                "record_id": f"bank:{page.source_file}:p{page.source_page}:l{source_row}:{doc_no or 'unallocated'}",
                "source_file": page.source_file,
                "source_page": page.source_page,
                "source_row": source_row,
                "source_role": "bank_statement",
                "document_no": doc_no,
                "document_date": doc_date,
                "posting_date": posting_date,
                "value_date": value_date,
                "amount": amount,
                "bank_amount": amount,
                "batch_id": batch_ids[0] if batch_ids else "",
                "batch_ids": ";".join(batch_ids),
                "group_id": batch_ids[0] if batch_ids else "",
                "group_ids": ";".join(batch_ids),
                "currency": assumptions.get("currency", "EUR"),
                "description": description,
                "evidence_type": (
                    "external_bank" if doc_no else "unallocated_external_bank"
                ),
                "document_key": document_key(doc_no, doc_date) if doc_no else "",
            }
        )
    return rows


def extract_invoice_refs(text: str, fallback_date: str = "") -> list[tuple[str, str]]:
    refs: list[tuple[str, str]] = []
    for match in re.finditer(
        r"\b(?:N\.?|NO\.?|NUM(?:ERO)?|FATT\.?|FATTURA|INVOICE|INV\.?|FACTURE|FACTURA)?\s*"
        r"(\d{1,7}(?:[-/][A-Z0-9]{1,8})?)\s+(?:del|dated?|du|fecha)\s+(\d{6,8})\b",
        text,
        re.I,
    ):
        refs.append((match.group(1), iso_date(match.group(2))))
    for match in re.finditer(r"\b(\d{1,7}[-/](?:FE|NE|FF|V\d+))\b", text, re.I):
        refs.append((match.group(1), fallback_date))
    for match in re.finditer(
        r"\b(?:FATT(?:URA|URE|\.?)|INVOICE|INV\.?|FACTURE|FACTURA)\s*(?:N\.?|NO\.?)?\s*(\d{1,7})(?![-/]\d)\b",
        text,
        re.I,
    ):
        refs.append((match.group(1), fallback_date))
    for match in re.finditer(
        r"\bFT\.?\s*(?:N\.?)?\s*(\d{1,7}(?:[-/]\d{2})?)(?=\s|[-–—]|$)", text, re.I
    ):
        refs.append((match.group(1), fallback_date))
    seen: set[tuple[str, str]] = set()
    out: list[tuple[str, str]] = []
    for doc_no, doc_date in refs:
        key = (clean_text(doc_no), doc_date)
        if key not in seen:
            seen.add(key)
            out.append(key)
    return out


def expand_numeric_range(value: str, *, max_span: int = 50) -> list[int]:
    value = clean_text(value).replace(" ", "")
    if "-" not in value:
        return [int(value)] if value.isdigit() else []
    start_text, end_text = value.split("-", 1)
    if not (start_text.isdigit() and end_text.isdigit()):
        return []
    start = int(start_text)
    end = int(end_text)
    if end < start or end - start > max_span:
        return []
    return list(range(start, end + 1))


def extract_payment_batch_ids(text: str) -> list[str]:
    ids: list[str] = []
    seen: set[str] = set()
    for match in PAYMENT_BATCH_RE.finditer(text):
        for number in expand_numeric_range(match.group("ref")):
            key = f"distinta:{number}"
            if key not in seen:
                seen.add(key)
                ids.append(key)
    return ids


def parse_journal_xlsx(path: Path, assumptions: dict[str, Any]) -> list[dict[str, Any]]:
    if load_workbook is None:
        raise RuntimeError("openpyxl is required for XLSX journal extraction")
    rows: list[dict[str, Any]] = []
    language = configured_language(assumptions, purpose="document")
    closure_terms = keyword_tuple(language, "evidence_keywords", "closure")
    compensation_terms = keyword_tuple(
        language, "evidence_keywords", "compensation"
    ) + keyword_tuple(language, "evidence_keywords", "netting")
    workbook = load_workbook(path, read_only=True, data_only=True)
    for sheet in workbook.worksheets:
        current_date = ""
        current_causale = ""
        for row_index, row in enumerate(sheet.iter_rows(values_only=True), start=1):
            values = [clean_text(value) for value in row]
            joined = " ".join(value for value in values if value)
            if not joined:
                continue
            header = JOURNAL_HEADER_RE.search(joined)
            if header:
                current_date = iso_date(header.group("date"))
                current_causale = clean_text(header.group("causale"))
                continue
            line_no = values[0] if values else ""
            if not re.fullmatch(r"\d{1,8}", line_no):
                continue
            account = next(
                (
                    value
                    for value in values
                    if re.fullmatch(r"\d+\s*/\s*\d+\s*/\s*\d+", value)
                ),
                "",
            )
            text_values = [
                value
                for value in values
                if value and value != line_no and value != account
            ]
            description = " ".join(text_values)
            doc_refs = extract_invoice_refs(description, current_date)
            if not doc_refs:
                doc_match = re.search(r"\bn([A-Z0-9./-]{2,})\b", description, re.I)
                if doc_match:
                    doc_refs = [(doc_match.group(1), current_date)]
            if not doc_refs:
                continue
            amounts = [parse_money(value) for value in values]
            numeric_amounts = [value for value in amounts if value is not None]
            amount = f"{numeric_amounts[-1]:.2f}" if numeric_amounts else ""
            lower_text = f"{current_causale} {description}".lower()
            evidence_type = "internal_accounting"
            if any_keyword_in(lower_text, closure_terms + compensation_terms):
                evidence_type = "internal_closure"
            if any_keyword_in(lower_text, compensation_terms):
                evidence_type = "compensation"
            if any(
                str(keyword).lower() in lower_text
                for keyword in assumptions.get("factoring_operator_keywords", [])
            ):
                evidence_type = "factoring_bridge"
            for doc_no, doc_date in doc_refs:
                rows.append(
                    {
                        "record_id": f"journal:{path.name}:{sheet.title}:r{row_index}:{doc_no}",
                        "source_file": path.name,
                        "source_sheet": sheet.title,
                        "source_row": row_index,
                        "source_role": "journal",
                        "document_no": doc_no,
                        "document_date": doc_date or current_date,
                        "posting_date": current_date,
                        "amount": amount,
                        "currency": assumptions.get("currency", "EUR"),
                        "description": f"{current_causale} {description}".strip(),
                        "evidence_type": evidence_type,
                        "document_key": document_key(doc_no, doc_date or current_date),
                    }
                )
    return rows


def journal_money_cell(value: object) -> Decimal | None:
    if isinstance(value, bool) or value is None:
        return None
    if isinstance(value, (int, float, Decimal)):
        return Decimal(str(value)).quantize(Decimal("0.01"))
    text = clean_text(value)
    if not text or not AMOUNT_IT_RE.fullmatch(text):
        return None
    return parse_money(text)


def journal_layout_for_sheet(sheet: Any) -> dict[str, int]:
    layouts: dict[tuple[int, int, int], int] = defaultdict(int)
    for row in sheet.iter_rows(values_only=True):
        values = [clean_text(value) for value in row]
        layout = journal_layout_from_header_values(values)
        if layout:
            layouts[
                (layout["operation_col"], layout["debit_col"], layout["credit_col"])
            ] += 1
    if not layouts:
        return {"operation_col": 1, "debit_col": 0, "credit_col": 0}
    operation_col, debit_col, credit_col = sorted(
        layouts.items(), key=lambda item: (-item[1], item[0])
    )[0][0]
    return {
        "operation_col": operation_col,
        "debit_col": debit_col,
        "credit_col": credit_col,
    }


def journal_layout_from_header_values(values: list[str]) -> dict[str, int]:
    operation_col = 0
    debit_col = 0
    credit_col = 0
    for idx, value in enumerate(values, start=1):
        lower = value.lower()
        if "descrizione dell'operazione" in lower or "operation description" in lower:
            operation_col = idx
        if lower in {"dare", "debit"}:
            debit_col = idx
        if lower in {"avere", "credit"}:
            credit_col = idx
    if operation_col and debit_col and credit_col:
        return {
            "operation_col": operation_col,
            "debit_col": debit_col,
            "credit_col": credit_col,
        }
    return {}


def journal_amount_sides(
    row: tuple[Any, ...], layout: dict[str, int]
) -> tuple[Decimal, Decimal]:
    debit = Decimal("0.00")
    credit = Decimal("0.00")
    debit_col = layout.get("debit_col", 0)
    credit_col = layout.get("credit_col", 0)
    operation_col = layout.get("operation_col", 1)
    midpoint = ((debit_col + credit_col) / 2) if debit_col and credit_col else None
    for idx, value in enumerate(row, start=1):
        if idx <= operation_col:
            continue
        amount = journal_money_cell(value)
        if amount is None:
            continue
        if credit_col and (
            idx == credit_col or (midpoint is not None and idx > midpoint)
        ):
            credit += amount
        else:
            debit += amount
    return debit.quantize(Decimal("0.01")), credit.quantize(Decimal("0.01"))


def journal_row_text_values(
    row: tuple[Any, ...], start_col: int, end_col: int
) -> list[str]:
    return [
        clean_text(value)
        for idx, value in enumerate(row, start=1)
        if start_col <= idx < end_col and clean_text(value)
    ]


def parse_journal_rollforward_xlsx(
    path: Path, assumptions: dict[str, Any]
) -> list[dict[str, Any]]:
    if load_workbook is None:
        raise RuntimeError(
            "openpyxl is required for XLSX journal roll-forward extraction"
        )
    counterparty_keywords = [
        clean_text(keyword).lower()
        for keyword in assumptions.get("counterparty_keywords", [])
        if clean_text(keyword)
    ]
    if not counterparty_keywords:
        return []
    workbook = load_workbook(path, read_only=True, data_only=True)
    rows: list[dict[str, Any]] = []
    for sheet in workbook.worksheets:
        layout = journal_layout_for_sheet(sheet)
        current_date = ""
        current_causale = ""
        for row_index, row in enumerate(sheet.iter_rows(values_only=True), start=1):
            values = [clean_text(value) for value in row]
            joined = " ".join(value for value in values if value)
            if not joined:
                continue
            row_layout = journal_layout_from_header_values(values)
            if row_layout:
                layout = row_layout
                continue
            operation_col = layout.get("operation_col", 1)
            debit_col = layout.get("debit_col", 0)
            credit_col = layout.get("credit_col", 0)
            header = JOURNAL_HEADER_RE.search(joined)
            if header:
                current_date = iso_date(header.group("date"))
                current_causale = clean_text(header.group("causale"))
                continue
            line_no = values[0] if values else ""
            if not re.fullmatch(r"\d{1,8}", line_no):
                continue
            account_cell = next(
                (
                    (idx, value)
                    for idx, value in enumerate(values, start=1)
                    if re.fullmatch(r"\d+\s*/\s*\d+\s*/\s*\d+", value)
                ),
                None,
            )
            if not account_cell:
                continue
            account_col, account = account_cell
            account_name_values = journal_row_text_values(
                row, account_col + 1, operation_col
            )
            account_name = account_name_values[0] if account_name_values else ""
            description_values = journal_row_text_values(
                row,
                operation_col,
                min([col for col in (debit_col, credit_col) if col] or [len(row) + 1]),
            )
            description = " ".join(description_values)
            if assumptions.get("rollforward_match_descriptions", False):
                match_text = f"{account_name} {description} {current_causale}".lower()
            else:
                match_text = account_name.lower()
            if not any(keyword in match_text for keyword in counterparty_keywords):
                continue
            debit, credit = journal_amount_sides(row, layout)
            if debit == Decimal("0.00") and credit == Decimal("0.00"):
                continue
            movement_text = f"{current_causale} {description}".lower()
            movement_type = (
                "opening"
                if any(term in movement_text for term in OPENING_ENTRY_TERMS)
                else "period_movement"
            )
            signed = (debit - credit).quantize(Decimal("0.01"))
            rows.append(
                {
                    "record_id": f"journal_rollforward:{path.name}:{sheet.title}:r{row_index}",
                    "source_file": path.name,
                    "source_sheet": sheet.title,
                    "source_row": row_index,
                    "source_role": "journal",
                    "posting_date": current_date,
                    "causale": current_causale,
                    "account": account,
                    "account_name": account_name,
                    "description": description,
                    "movement_type": movement_type,
                    "debit_amount": f"{debit:.2f}",
                    "credit_amount": f"{credit:.2f}",
                    "signed_debit_minus_credit": f"{signed:.2f}",
                    "currency": assumptions.get("currency", "EUR"),
                    "debit_column": debit_col,
                    "credit_column": credit_col,
                    "operation_column": operation_col,
                }
            )
    return rows


def summarize_journal_rollforward(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    buckets: dict[tuple[str, str], dict[str, Any]] = {}

    def add_to_bucket(key: tuple[str, str], row: dict[str, Any]) -> None:
        bucket = buckets.setdefault(
            key,
            {
                "account": key[0],
                "account_name": key[1],
                "rows": 0,
                "opening_debit": Decimal("0.00"),
                "opening_credit": Decimal("0.00"),
                "period_debit": Decimal("0.00"),
                "period_credit": Decimal("0.00"),
            },
        )
        movement_type = clean_text(row.get("movement_type"))
        debit = parse_money(row.get("debit_amount")) or Decimal("0.00")
        credit = parse_money(row.get("credit_amount")) or Decimal("0.00")
        bucket["rows"] += 1
        if movement_type == "opening":
            bucket["opening_debit"] += debit
            bucket["opening_credit"] += credit
        else:
            bucket["period_debit"] += debit
            bucket["period_credit"] += credit

    for row in rows:
        add_to_bucket(
            (clean_text(row.get("account")), clean_text(row.get("account_name"))), row
        )
        add_to_bucket(("TOTAL", "All matched counterparty journal accounts"), row)

    summary: list[dict[str, Any]] = []
    for bucket in buckets.values():
        opening_net = bucket["opening_debit"] - bucket["opening_credit"]
        period_net = bucket["period_debit"] - bucket["period_credit"]
        closing_net = opening_net + period_net
        summary.append(
            {
                "account": bucket["account"],
                "account_name": bucket["account_name"],
                "rows": bucket["rows"],
                "opening_debit": f"{bucket['opening_debit']:.2f}",
                "opening_credit": f"{bucket['opening_credit']:.2f}",
                "opening_net_debit_minus_credit": f"{opening_net:.2f}",
                "period_debit": f"{bucket['period_debit']:.2f}",
                "period_credit": f"{bucket['period_credit']:.2f}",
                "period_net_debit_minus_credit": f"{period_net:.2f}",
                "closing_net_debit_minus_credit": f"{closing_net:.2f}",
            }
        )
    return sorted(
        summary,
        key=lambda row: (
            row["account"] != "TOTAL",
            row["account"],
            row["account_name"],
        ),
    )


def is_bank_like_ledger_row(row: dict[str, Any]) -> bool:
    text = f"{row.get('source_file', '')} {row.get('account_name', '')}".lower()
    return any(term in text for term in BANK_ACCOUNT_TERMS)


def rollforward_counterparty_keywords(
    ledger_balance_rows: list[dict[str, Any]],
    assumptions: dict[str, Any],
) -> list[str]:
    """Infer conservative journal filter keywords from non-bank ledger accounts."""

    seen: set[str] = set()
    keywords: list[str] = []

    def add(value: object) -> None:
        keyword = clean_text(value).lower()
        if len(keyword) < 3 or keyword in seen:
            return
        seen.add(keyword)
        keywords.append(keyword)

    for keyword in assumptions.get("counterparty_keywords", []):
        add(keyword)
    if keywords:
        return keywords

    for row in ledger_balance_rows:
        if clean_text(row.get("account")) == "TOTAL" or is_bank_like_ledger_row(row):
            continue
        add(row.get("account_name"))
    return keywords


def matched_ledger_balance_rows(
    ledger_balance_rows: list[dict[str, Any]],
    journal_rollforward_summary: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    journal_accounts = {
        clean_text(row.get("account"))
        for row in journal_rollforward_summary
        if clean_text(row.get("account")) != "TOTAL"
    }
    if journal_accounts:
        return [
            row
            for row in ledger_balance_rows
            if clean_text(row.get("account")) in journal_accounts
            and clean_text(row.get("account")) != "TOTAL"
        ]
    return [
        row
        for row in ledger_balance_rows
        if clean_text(row.get("account")) != "TOTAL"
        and not is_bank_like_ledger_row(row)
    ]


def rollforward_decimal(value: object) -> Decimal:
    return parse_money(value) or Decimal("0.00")


def rollforward_status(
    opening_diff: Decimal | None, closing_diff: Decimal | None, tolerance: Decimal
) -> str:
    if opening_diff is None or closing_diff is None:
        return "MISSING_JOURNAL_OR_LEDGER"
    if abs(opening_diff) <= tolerance and abs(closing_diff) <= tolerance:
        return "PASS"
    return "DIFFERENCE"


def rollforward_check_note(status: str) -> str:
    if status == "PASS":
        return "Saldo iniziale e saldo finale del giornale riconciliano con il mastro entro tolleranza."
    if status == "MISSING_JOURNAL_OR_LEDGER":
        return "Manca il conto nel giornale o nel mastro; verificare parole chiave e layout dei file."
    return (
        "Il saldo ricostruito dal giornale non coincide con il saldo finale del mastro."
    )


def build_account_rollforward_check(
    ledger_balance_rows: list[dict[str, Any]],
    journal_rollforward_summary: list[dict[str, Any]],
    assumptions: dict[str, Any],
) -> list[dict[str, Any]]:
    """Compare journal roll-forward totals to ledger opening/closing balances."""

    if not ledger_balance_rows and not journal_rollforward_summary:
        return []

    tolerance = parse_money(
        assumptions.get("rollforward_amount_tolerance")
        or assumptions.get("amount_tolerance")
        or "0.01"
    ) or Decimal("0.01")
    journal_by_account = {
        clean_text(row.get("account")): row for row in journal_rollforward_summary
    }
    ledger_rows = matched_ledger_balance_rows(
        ledger_balance_rows, journal_rollforward_summary
    )
    rows: list[dict[str, Any]] = []

    compared_accounts: set[str] = set()
    for ledger in ledger_rows:
        account = clean_text(ledger.get("account"))
        compared_accounts.add(account)
        journal = journal_by_account.get(account)
        ledger_opening = rollforward_decimal(
            ledger.get("opening_balance_signed_debit_minus_credit")
        )
        ledger_closing = rollforward_decimal(
            ledger.get("closing_balance_signed_debit_minus_credit")
        )
        if journal:
            journal_opening = rollforward_decimal(
                journal.get("opening_net_debit_minus_credit")
            )
            journal_period = rollforward_decimal(
                journal.get("period_net_debit_minus_credit")
            )
            journal_closing = rollforward_decimal(
                journal.get("closing_net_debit_minus_credit")
            )
            opening_diff: Decimal | None = (journal_opening - ledger_opening).quantize(
                Decimal("0.01")
            )
            closing_diff: Decimal | None = (journal_closing - ledger_closing).quantize(
                Decimal("0.01")
            )
            status = rollforward_status(opening_diff, closing_diff, tolerance)
        else:
            journal_opening = Decimal("0.00")
            journal_period = Decimal("0.00")
            journal_closing = Decimal("0.00")
            opening_diff = None
            closing_diff = None
            status = "MISSING_JOURNAL_OR_LEDGER"
        rows.append(
            {
                "account": account,
                "account_name": clean_text(ledger.get("account_name")),
                "ledger_source_file": clean_text(ledger.get("source_file")),
                "ledger_source_pages": clean_text(ledger.get("source_pages")),
                "journal_rows": int(journal.get("rows", 0)) if journal else 0,
                "ledger_opening_balance": f"{ledger_opening:.2f}",
                "journal_opening_balance": f"{journal_opening:.2f}",
                "opening_difference_journal_minus_ledger": (
                    "" if opening_diff is None else f"{opening_diff:.2f}"
                ),
                "journal_period_net_movement": f"{journal_period:.2f}",
                "journal_recalculated_closing": f"{journal_closing:.2f}",
                "ledger_closing_balance": f"{ledger_closing:.2f}",
                "closing_difference_journal_minus_ledger": (
                    "" if closing_diff is None else f"{closing_diff:.2f}"
                ),
                "status": status,
                "review_note": rollforward_check_note(status),
            }
        )

    for journal in journal_rollforward_summary:
        account = clean_text(journal.get("account"))
        if account == "TOTAL" or account in compared_accounts:
            continue
        status = "MISSING_JOURNAL_OR_LEDGER"
        rows.append(
            {
                "account": account,
                "account_name": clean_text(journal.get("account_name")),
                "ledger_source_file": "",
                "ledger_source_pages": "",
                "journal_rows": int(journal.get("rows", 0)),
                "ledger_opening_balance": "",
                "journal_opening_balance": journal.get(
                    "opening_net_debit_minus_credit", "0.00"
                ),
                "opening_difference_journal_minus_ledger": "",
                "journal_period_net_movement": journal.get(
                    "period_net_debit_minus_credit", "0.00"
                ),
                "journal_recalculated_closing": journal.get(
                    "closing_net_debit_minus_credit", "0.00"
                ),
                "ledger_closing_balance": "",
                "closing_difference_journal_minus_ledger": "",
                "status": status,
                "review_note": rollforward_check_note(status),
            }
        )

    if rows:
        journal_total = journal_by_account.get("TOTAL", {})
        ledger_opening_total = sum(
            (
                rollforward_decimal(row.get("ledger_opening_balance"))
                for row in rows
                if row.get("ledger_opening_balance")
            ),
            Decimal("0.00"),
        )
        ledger_closing_total = sum(
            (
                rollforward_decimal(row.get("ledger_closing_balance"))
                for row in rows
                if row.get("ledger_closing_balance")
            ),
            Decimal("0.00"),
        )
        journal_opening_total = rollforward_decimal(
            journal_total.get("opening_net_debit_minus_credit")
        )
        journal_period_total = rollforward_decimal(
            journal_total.get("period_net_debit_minus_credit")
        )
        journal_closing_total = rollforward_decimal(
            journal_total.get("closing_net_debit_minus_credit")
        )
        opening_diff_total = (journal_opening_total - ledger_opening_total).quantize(
            Decimal("0.01")
        )
        closing_diff_total = (journal_closing_total - ledger_closing_total).quantize(
            Decimal("0.01")
        )
        status = rollforward_status(opening_diff_total, closing_diff_total, tolerance)
        rows.insert(
            0,
            {
                "account": "TOTAL",
                "account_name": "Conti confrontati",
                "ledger_source_file": "",
                "ledger_source_pages": "",
                "journal_rows": int(journal_total.get("rows", 0) or 0),
                "ledger_opening_balance": f"{ledger_opening_total:.2f}",
                "journal_opening_balance": f"{journal_opening_total:.2f}",
                "opening_difference_journal_minus_ledger": f"{opening_diff_total:.2f}",
                "journal_period_net_movement": f"{journal_period_total:.2f}",
                "journal_recalculated_closing": f"{journal_closing_total:.2f}",
                "ledger_closing_balance": f"{ledger_closing_total:.2f}",
                "closing_difference_journal_minus_ledger": f"{closing_diff_total:.2f}",
                "status": status,
                "review_note": rollforward_check_note(status),
            },
        )
    return rows


def journal_evidence_type(text: str, assumptions: dict[str, Any]) -> str:
    lower_text = text.lower()
    language = configured_language(assumptions, purpose="document")
    closure_terms = keyword_tuple(language, "evidence_keywords", "closure")
    compensation_terms = keyword_tuple(
        language, "evidence_keywords", "compensation"
    ) + keyword_tuple(language, "evidence_keywords", "netting")
    evidence_type = "internal_accounting"
    if any_keyword_in(lower_text, closure_terms + compensation_terms):
        evidence_type = "internal_closure"
    if any_keyword_in(lower_text, compensation_terms):
        evidence_type = "compensation"
    if any(
        str(keyword).lower() in lower_text
        for keyword in assumptions.get("factoring_operator_keywords", [])
    ):
        evidence_type = "factoring_bridge"
    return evidence_type


def parse_journal_pages(
    pages: list[SourcePage], assumptions: dict[str, Any]
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for page in pages:
        if page.source_role != "journal":
            continue
        current_date = ""
        current_causale = ""
        lines = [
            clean_text(line) for line in page.text.splitlines() if clean_text(line)
        ]
        for idx, line in enumerate(lines, start=1):
            header = JOURNAL_HEADER_RE.search(line)
            if header:
                current_date = iso_date(header.group("date"))
                current_causale = clean_text(header.group("causale"))
                continue
            account = ""
            match = JOURNAL_ACCOUNT_RE.search(line)
            description = line
            if match:
                account = clean_text(match.group("account"))
                description = clean_text(line[match.end() :])
            doc_refs = extract_invoice_refs(description, current_date)
            if not doc_refs:
                doc_match = re.search(r"\bn([A-Z0-9./-]{2,})\b", description, re.I)
                if doc_match:
                    doc_refs = [(doc_match.group(1), current_date)]
            if not doc_refs:
                continue
            amounts = AMOUNT_IT_RE.findall(description)
            amount = amount_string(amounts[-1] if amounts else "")
            full_description = f"{current_causale} {description}".strip()
            evidence_type = journal_evidence_type(full_description, assumptions)
            for doc_no, doc_date in doc_refs:
                rows.append(
                    {
                        "record_id": f"journal_pdf:{page.source_file}:p{page.source_page}:l{idx}:{doc_no}",
                        "source_file": page.source_file,
                        "source_page": page.source_page,
                        "source_row": idx,
                        "source_role": "journal",
                        "account": account,
                        "document_no": doc_no,
                        "document_date": doc_date or current_date,
                        "posting_date": current_date,
                        "amount": amount,
                        "currency": assumptions.get("currency", "EUR"),
                        "description": full_description,
                        "evidence_type": evidence_type,
                        "document_key": document_key(doc_no, doc_date or current_date),
                    }
                )
    return rows


def parse_payment_order_zip(
    path: Path, assumptions: dict[str, Any]
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    with zipfile.ZipFile(path) as zf:
        for member in sorted(zf.namelist()):
            if member.endswith("/") or not member.lower().endswith(
                (".doc", ".html", ".htm", ".txt")
            ):
                continue
            raw = zf.read(member).decode("utf-8", errors="replace")
            text = re.sub(r"<[^>]+>", " ", raw)
            text = clean_text(text)
            header = PAYMENT_ORDER_HEADER_RE.search(text)
            batch_no = str(int(header.group("batch"))) if header else ""
            batch_id = f"distinta:{batch_no}" if batch_no else ""
            order_date = iso_date(header.group("date")) if header else ""
            valuta = ""
            valuta_match = re.search(
                r"\b(?:Valuta|Value\s+Date|Date\s+de\s+Valeur|Fecha\s+Valor)\s+(\d{2}/\d{2}/\d{4})",
                text,
                re.I,
            )
            if valuta_match:
                valuta = iso_date(valuta_match.group(1))
            total_matches = list(PAYMENT_ORDER_TOTAL_RE.finditer(text))
            batch_total = (
                amount_string(total_matches[-1].group("amount"))
                if total_matches
                else ""
            )
            for idx, match in enumerate(PAYMENT_ORDER_LINE_RE.finditer(text), start=1):
                doc_no = clean_text(match.group("document_no"))
                doc_date = iso_date(match.group("document_date"))
                counterparty_doc = clean_text(match.group("counterparty_doc"))
                counterparty_date = iso_date(match.group("counterparty_date"))
                rows.append(
                    {
                        "record_id": f"payment_order:{path.name}:{member}:{idx}",
                        "source_file": f"{path.name}!{member}",
                        "source_role": "payment_order",
                        "document_no": doc_no,
                        "document_date": doc_date,
                        "posting_date": valuta or order_date,
                        "value_date": valuta,
                        "payment_order_date": order_date,
                        "counterparty_document_no": counterparty_doc,
                        "counterparty_document_date": counterparty_date,
                        "amount": amount_string(match.group("invoice_amount")),
                        "batch_total": batch_total,
                        "group_total": batch_total,
                        "batch_id": batch_id,
                        "group_id": batch_id,
                        "currency": assumptions.get("currency", "EUR"),
                        "description": text[:1000],
                        "evidence_type": "payment_order_bridge",
                        "document_key": document_key(doc_no, doc_date),
                    }
                )
    return rows


def extract_normalized_records(
    input_dir: str | Path,
    assumptions: dict[str, Any] | None = None,
    *,
    output_dir: str | Path | None = None,
) -> dict[str, Any]:
    active = dict(assumptions or {})
    root = Path(input_dir)
    out_dir = validate_run_output_dir(
        Path(output_dir) if output_dir else root.parent / "output",
        input_dir=root,
    )
    cache_dir = validate_run_cache_dir(
        active.get("cache_dir")
        or active.get("ocr_cache_dir")
        or out_dir / ".audit_reconciliation_cache",
        input_dir=root,
    )
    cache_dir.mkdir(parents=True, exist_ok=True)

    inventory = source_inventory(root, active)
    all_pages: list[SourcePage] = []
    evidence_rows: list[dict[str, Any]] = []
    journal_rollforward_rows: list[dict[str, Any]] = []
    journal_paths: list[Path] = []
    extraction_errors: list[dict[str, Any]] = []
    files = sorted(
        p for p in root.iterdir() if p.is_file() and not p.name.startswith(".")
    )
    language = configured_language(active, purpose="document")
    spreadsheet_roles = {
        infer_source_role(path, language=language)
        for path in files
        if path.suffix.lower() in {".xlsx", ".xlsm", ".xls", ".csv"}
    }
    prefer_spreadsheet_for_roles = set(
        active.get("prefer_spreadsheet_for_roles", ["journal"])
    )

    def progress_callback(event: dict[str, Any]) -> None:
        if not active.get("verbose_extraction"):
            return
        if event.get("event") == "pdf_file_start":
            print(
                "[audit-reconciliation] PDF start "
                f"{event.get('source_file')} pages={event.get('page_count')}",
                flush=True,
            )
        elif event.get("event") == "pdf_page_done":
            print(
                "[audit-reconciliation] PDF progress "
                f"{event.get('source_file')} "
                f"page {event.get('source_page')}/{event.get('page_count')} "
                f"method={event.get('extraction_method')} "
                f"text_chars={event.get('text_length')}",
                flush=True,
            )
        elif event.get("event") == "pdf_file_done":
            print(
                "[audit-reconciliation] PDF done "
                f"{event.get('source_file')} pages={event.get('page_count')} "
                f"ocr_pages={event.get('ocr_page_count')} "
                f"text_chars={event.get('text_length')}",
                flush=True,
            )
        elif event.get("event") == "ocr_page_start":
            print(
                "[audit-reconciliation] OCR page "
                f"{event.get('source_page')}/{event.get('page_count')} "
                f"{event.get('source_file')}",
                flush=True,
            )
        elif event.get("event") == "ocr_page_done":
            print(
                "[audit-reconciliation] OCR done "
                f"{event.get('source_page')}/{event.get('page_count')} "
                f"{event.get('source_file')} "
                f"text_chars={event.get('text_length')}",
                flush=True,
            )
        elif event.get("event") == "pdf_cache_hit":
            print(
                "[audit-reconciliation] cache hit "
                f"{event.get('source_file')} pages={event.get('page_count')}",
                flush=True,
            )

    for path in files:
        try:
            role_from_name = infer_source_role(path, language=language)
            if active.get("verbose_extraction"):
                print(
                    f"[audit-reconciliation] extracting {path.name} as {role_from_name}",
                    flush=True,
                )
            if (
                path.suffix.lower() == ".pdf"
                and role_from_name in prefer_spreadsheet_for_roles
                and role_from_name in spreadsheet_roles
            ):
                extraction_errors.append(
                    {
                        "source_file": path.name,
                        "status": "skipped",
                        "reason": f"Skipped duplicate {role_from_name} PDF because spreadsheet source is available.",
                    }
                )
                if active.get("verbose_extraction"):
                    print(
                        f"[audit-reconciliation] skipped {path.name}: spreadsheet source available",
                        flush=True,
                    )
                continue
            if path.suffix.lower() == ".pdf":
                pages = extract_pdf_pages(
                    path,
                    cache_dir,
                    language=language,
                    progress_every_pages=int(
                        active.get("pdf_progress_every_pages", 10)
                    ),
                    progress_callback=progress_callback,
                )
                all_pages.extend(pages)
                evidence_rows.extend(parse_journal_pages(pages, active))
                evidence_rows.extend(parse_ledger_or_factoring_pages(pages, active))
                evidence_rows.extend(parse_bank_statement_pages(pages, active))
            elif (
                path.suffix.lower() in {".xlsx", ".xlsm"}
                and role_from_name == "journal"
            ):
                evidence_rows.extend(parse_journal_xlsx(path, active))
                journal_paths.append(path)
            elif path.suffix.lower() == ".zip":
                evidence_rows.extend(parse_payment_order_zip(path, active))
            if active.get("verbose_extraction"):
                print(
                    f"[audit-reconciliation] done {path.name}: open_items={len(open_items) if 'open_items' in locals() else 'pending'} evidence_rows={len(evidence_rows)} pages={len(all_pages)}",
                    flush=True,
                )
        except (
            Exception
        ) as exc:  # keep run auditable instead of hiding extraction failures
            extraction_errors.append(
                {"source_file": path.name, "error": f"{type(exc).__name__}: {exc}"}
            )
            if active.get("verbose_extraction"):
                print(
                    f"[audit-reconciliation] error {path.name}: {type(exc).__name__}: {exc}",
                    flush=True,
                )

    open_items = parse_open_items(all_pages, active)
    ledger_balance_rows = parse_ledger_balance_pages(all_pages, active)
    rollforward_keywords = rollforward_counterparty_keywords(
        ledger_balance_rows, active
    )
    if journal_paths and rollforward_keywords:
        rollforward_assumptions = {
            **active,
            "counterparty_keywords": rollforward_keywords,
        }
        for journal_path in journal_paths:
            journal_rollforward_rows.extend(
                parse_journal_rollforward_xlsx(journal_path, rollforward_assumptions)
            )
    journal_rollforward_summary = summarize_journal_rollforward(
        journal_rollforward_rows
    )
    account_rollforward_check = build_account_rollforward_check(
        ledger_balance_rows,
        journal_rollforward_summary,
        active,
    )
    normalized_records = [*open_items, *evidence_rows]
    page_rows = [asdict(page) for page in all_pages]
    return {
        "source_inventory": inventory,
        "source_pages": page_rows,
        "open_items": open_items,
        "evidence_rows": evidence_rows,
        "ledger_balance_rows": ledger_balance_rows,
        "account_rollforward_check": account_rollforward_check,
        "journal_rollforward_rows": journal_rollforward_rows,
        "journal_rollforward_summary": journal_rollforward_summary,
        "normalized_records": normalized_records,
        "extraction_errors": extraction_errors,
        "cache_dir": str(cache_dir),
    }


def write_json(path: Path, payload: Any) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, default=str), encoding="utf-8"
    )
    return path


def run_raw_input_reconciliation(
    *,
    input_dir: str | Path,
    output_dir: str | Path,
    assumptions: dict[str, Any] | None = None,
    title: str = "Relazione di riconciliazione contabile",
    narrative: str = "",
    language: str = "it",
) -> dict[str, Any]:
    requested_language = normalize_language(
        (assumptions or {}).get("locale") or language
    )
    active = {
        "scope_year": None,
        "cutoff_date": None,
        "report_language": requested_language,
        "document_language": requested_language,
        "currency": "EUR",
        "post_cutoff_events_excluded": True,
        "payment_orders_are_bank_evidence": False,
        "factoring_pro_soluto_closes_item": True,
        "compensation_requires_bank": False,
        **(assumptions or {}),
    }
    out_dir = validate_run_output_dir(output_dir, input_dir=input_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    extracted = extract_normalized_records(input_dir, active, output_dir=out_dir)
    review_rows = None
    review_rows_path = active.get("review_rows_path")
    if review_rows_path:
        review_rows = json.loads(Path(review_rows_path).read_text(encoding="utf-8"))

    result = build_reconciliation_artifacts(
        output_dir=out_dir,
        open_items=extracted["open_items"],
        evidence_rows=extracted["evidence_rows"],
        assumptions=active,
        source_inventory=extracted["source_inventory"],
        normalized_records=extracted["normalized_records"],
        ledger_balance_rows=extracted["ledger_balance_rows"],
        account_rollforward_check=extracted.get("account_rollforward_check", []),
        aggregate_rollforward_rows=extracted["journal_rollforward_rows"],
        aggregate_rollforward_summary=extracted["journal_rollforward_summary"],
        metadata={
            "Input folder": str(input_dir),
            "Run timestamp": datetime.now().isoformat(timespec="seconds"),
        },
        title=title,
        narrative=narrative,
        language=active.get("report_language", requested_language),
        excel_name="riconciliazione_audit.xlsx",
        word_name="relazione_riconciliazione_audit.docx",
        fail_on_check_errors=False,
        review_rows=review_rows,
        challenged_rows=active.get("challenged_rows"),
        review_seed=active.get("review_seed", "audit-reconciliation-review"),
        review_high_value_count=int(active.get("review_high_value_count", 10)),
        review_random_count=int(active.get("review_random_count", 20)),
        require_completed_review=bool(active.get("require_completed_review", False)),
    )
    missing_evidence_pack = build_missing_evidence_request_pack(
        result["reconciliation_rows"],
        source_inventory=extracted["source_inventory"],
        normalized_records=extracted["normalized_records"],
        entity_name=active.get("entity_name") or active.get("company_name") or "",
        counterparty_name=active.get("counterparty_name")
        or active.get("counterparty")
        or "",
        cutoff_date=active.get("cutoff_date"),
        language=active.get("report_language", requested_language),
    )
    missing_evidence_requests_path = write_missing_evidence_workbook(
        out_dir / "richieste_mirate_evidenze.xlsx",
        missing_evidence_pack,
    )
    review_status_counts: dict[str, int] = defaultdict(int)
    for row in result["review_rows"]:
        review_status_counts[
            clean_text(row.get("review_status")).upper() or "MISSING"
        ] += 1

    source_pages_path = out_dir / "source_pages.json"
    manifest = {
        "input_dir": str(input_dir),
        "output_dir": str(out_dir),
        "cache_dir": extracted["cache_dir"],
        "source_pages_path": str(source_pages_path),
        "assumptions": active,
        "counts": {
            "source_files": len(extracted["source_inventory"]),
            "source_pages": len(extracted["source_pages"]),
            "open_items": len(extracted["open_items"]),
            "evidence_rows": len(extracted["evidence_rows"]),
            "ledger_balance_rows": len(extracted["ledger_balance_rows"]),
            "account_rollforward_check_rows": len(
                extracted.get("account_rollforward_check", [])
            ),
            "journal_rollforward_rows": len(extracted["journal_rollforward_rows"]),
            "journal_rollforward_summary_rows": len(
                extracted["journal_rollforward_summary"]
            ),
            "reconciliation_rows": len(result["reconciliation_rows"]),
            "bank_allocation_candidates": len(result["bank_allocation_candidates"]),
            "external_evidence_rows": len(result["external_evidence_detail"]),
            "external_evidence_summary_rows": len(result["external_evidence_summary"]),
            "post_cutoff_candidates": len(result["post_cutoff_candidates"]),
            "aging_summary_rows": len(result["aging_summary"]),
            "review_signal_rows": len(result["review_signals"]),
            "evidence_concentration_rows": len(result["evidence_concentration"]),
            "document_source_map_rows": len(result["document_source_map"]),
            "reversal_candidate_rows": len(result["reversal_candidates"]),
            "cutoff_window_movement_rows": len(result["cutoff_window_movements"]),
            "review_rows": len(result["review_rows"]),
            "review_status_counts": dict(sorted(review_status_counts.items())),
            "missing_evidence_request_rows": sum(
                len(rows) for rows in missing_evidence_pack.request_sections.values()
            ),
            "extraction_errors": len(extracted["extraction_errors"]),
        },
        "checks": result["checks"],
        "checks_pass": result["checks_pass"],
        "excel_path": result["excel_path"],
        "accountant_report_path": result["accountant_report_path"],
        "word_path": result["word_path"],
        "missing_evidence_requests_path": str(missing_evidence_requests_path),
    }
    write_json(out_dir / "run_manifest.json", manifest)
    write_json(out_dir / "extraction_errors.json", extracted["extraction_errors"])
    write_json(source_pages_path, extracted["source_pages"])
    write_json(out_dir / "normalized_records.json", extracted["normalized_records"])
    write_json(
        out_dir / "bank_allocation_candidates.json",
        result["bank_allocation_candidates"],
    )
    write_json(
        out_dir / "external_evidence_detail.json", result["external_evidence_detail"]
    )
    write_json(
        out_dir / "external_evidence_summary.json", result["external_evidence_summary"]
    )
    write_json(out_dir / "ledger_balance_rows.json", extracted["ledger_balance_rows"])
    write_json(
        out_dir / "account_rollforward_check.json",
        extracted.get("account_rollforward_check", []),
    )
    write_json(
        out_dir / "journal_rollforward_rows.json", extracted["journal_rollforward_rows"]
    )
    write_json(
        out_dir / "journal_rollforward_summary.json",
        extracted["journal_rollforward_summary"],
    )
    write_json(
        out_dir / "post_cutoff_candidates.json", result["post_cutoff_candidates"]
    )
    write_json(out_dir / "aging_summary.json", result["aging_summary"])
    write_json(out_dir / "review_signals.json", result["review_signals"])
    write_json(
        out_dir / "evidence_concentration.json", result["evidence_concentration"]
    )
    write_json(out_dir / "document_source_map.json", result["document_source_map"])
    write_json(out_dir / "reversal_candidates.json", result["reversal_candidates"])
    write_json(
        out_dir / "cutoff_window_movements.json", result["cutoff_window_movements"]
    )
    write_json(out_dir / "codex_review_packet.json", result["review_rows"])
    existing_review_session = result.get("review_session") or {}
    review_session = write_review_session_artifacts(
        out_dir,
        run_id=str(existing_review_session.get("run_id") or ""),
        run_intake_path=Path(existing_review_session["run_intake_path"]),
        result={
            **result,
            "assumptions": active,
            "missing_evidence_requests_path": str(missing_evidence_requests_path),
        },
        source_inventory=extracted["source_inventory"],
        source_paths=[input_dir],
        missing_evidence_requests_path=missing_evidence_requests_path,
        language=active.get("report_language", requested_language),
    )
    manifest["review_session"] = {
        "run_id": review_session.run_id,
        "run_intake_path": str(review_session.run_intake_path),
        "review_payload_path": str(review_session.review_payload_path),
        "ui_decisions_path": str(review_session.ui_decisions_path),
        "review_html_path": str(review_session.review_html_path),
        "final_artifacts_path": str(review_session.final_artifacts_path),
        "review_item_count": review_session.review_item_count,
    }
    write_json(out_dir / "run_manifest.json", manifest)
    return {
        **result,
        **extracted,
        "manifest": manifest,
        "missing_evidence_requests_path": str(missing_evidence_requests_path),
        "missing_evidence_request_pack": missing_evidence_pack,
    }
