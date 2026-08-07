#!/usr/bin/env python3
"""Extract reviewable table geometry from readable or scanned trial-balance PDFs.

This module is deliberately limited to mechanical document work: page rendering,
text/OCR token capture, visual row grouping, and table geometry. It never decides
what an accounting column means and never turns extracted values into canonical
facts; ``xbrl_case`` performs schema matching and requires professional review.
"""

from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from statistics import median
from typing import Any, Callable, Iterable, Mapping, Sequence

__all__ = [
    "OcrSetupRequired",
    "OcrWord",
    "extract_pdf_tables",
]

MIN_NATIVE_TEXT_CHARS = 40
OCR_CONFIDENCE_REVIEW_THRESHOLD = 0.90
MAX_PDF_PAGES = 500
OCR_SETUP_MESSAGE = (
    "OCR_SETUP_REQUIRED: PaddleOCR is required to read this document. "
    "Shall Claude install it now? The download is about 500 MB."
)


class OcrSetupRequired(ValueError):
    """Signal that a scanned PDF needs the optional managed OCR runtime."""


@dataclass(frozen=True)
class OcrWord:
    """One OCR token with page-space geometry and recognition confidence."""

    text: str
    bbox: tuple[float, float, float, float]
    confidence: float


def _clean_text(value: object) -> str:
    return " ".join(str(value or "").split())


def _bbox_union(
    boxes: Sequence[tuple[float, float, float, float]],
) -> tuple[float, float, float, float]:
    return (
        min(item[0] for item in boxes),
        min(item[1] for item in boxes),
        max(item[2] for item in boxes),
        max(item[3] for item in boxes),
    )


def _normalized_bbox(value: object) -> tuple[float, float, float, float] | None:
    """Normalize common PaddleOCR rectangle and polygon shapes."""

    if not isinstance(value, Sequence) or isinstance(value, (str, bytes, bytearray)):
        return None
    if len(value) == 4 and all(isinstance(item, (int, float)) for item in value):
        x0, y0, x1, y1 = (float(item) for item in value)
        if x1 > x0 and y1 > y0:
            return (x0, y0, x1, y1)
        return None
    points: list[tuple[float, float]] = []
    for point in value:
        if (
            isinstance(point, Sequence)
            and not isinstance(point, (str, bytes, bytearray))
            and len(point) >= 2
            and isinstance(point[0], (int, float))
            and isinstance(point[1], (int, float))
        ):
            points.append((float(point[0]), float(point[1])))
    if not points:
        return None
    x_values = [point[0] for point in points]
    y_values = [point[1] for point in points]
    if max(x_values) <= min(x_values) or max(y_values) <= min(y_values):
        return None
    return (min(x_values), min(y_values), max(x_values), max(y_values))


def _mapping_words(value: Mapping[str, Any]) -> list[OcrWord]:
    texts = value.get("rec_texts")
    if texts is None:
        texts = value.get("texts")
    if not isinstance(texts, Sequence) or isinstance(texts, (str, bytes, bytearray)):
        return []
    scores = value.get("rec_scores")
    if scores is None:
        scores = value.get("scores")
    if scores is None:
        scores = []
    boxes: object = None
    for key in ("rec_boxes", "dt_polys", "rec_polys", "boxes"):
        candidate = value.get(key)
        if candidate is not None:
            boxes = candidate
            break
    if boxes is None:
        boxes = []
    if not isinstance(boxes, Sequence) or isinstance(boxes, (str, bytes, bytearray)):
        return []
    words: list[OcrWord] = []
    for index, text in enumerate(texts):
        cleaned = _clean_text(text)
        if not cleaned or index >= len(boxes):
            continue
        bbox = _normalized_bbox(boxes[index])
        if bbox is None:
            continue
        score = scores[index] if index < len(scores) else 0.0
        confidence = float(score) if isinstance(score, (int, float)) else 0.0
        words.append(OcrWord(cleaned, bbox, max(0.0, min(confidence, 1.0))))
    return words


def _collect_ocr_words(raw: object) -> list[OcrWord]:
    """Collect words from current mapping and legacy nested PaddleOCR results."""

    if raw is None:
        return []
    if isinstance(raw, Mapping):
        direct = _mapping_words(raw)
        if direct:
            return direct
        words: list[OcrWord] = []
        for nested in raw.values():
            words.extend(_collect_ocr_words(nested))
        return words
    if isinstance(raw, Iterable) and not isinstance(raw, (str, bytes, bytearray)):
        values = list(raw)
        if (
            len(values) >= 2
            and isinstance(values[0], Sequence)
            and not isinstance(values[0], (str, bytes, bytearray))
            and isinstance(values[1], Sequence)
            and not isinstance(values[1], (str, bytes, bytearray))
            and len(values[1]) >= 1
        ):
            bbox = _normalized_bbox(values[0])
            text = _clean_text(values[1][0])
            score = values[1][1] if len(values[1]) > 1 else 0.0
            if bbox is not None and text:
                confidence = float(score) if isinstance(score, (int, float)) else 0.0
                return [OcrWord(text, bbox, max(0.0, min(confidence, 1.0)))]
        words = []
        for nested in values:
            words.extend(_collect_ocr_words(nested))
        return words
    json_value = getattr(raw, "json", None)
    if isinstance(json_value, Mapping):
        return _collect_ocr_words(json_value)
    to_dict = getattr(raw, "to_dict", None)
    if callable(to_dict):
        converted = to_dict()
        if isinstance(converted, Mapping):
            return _collect_ocr_words(converted)
    return []


@lru_cache(maxsize=4)
def _ocr_engine(language: str) -> object:
    requirements_path = Path(__file__).resolve().parents[1] / "requirements-ocr.txt"
    try:
        from managed_ocr_runtime import activate_ocr_runtime
    except ImportError as exc:
        raise OcrSetupRequired(OCR_SETUP_MESSAGE) from exc
    if activate_ocr_runtime(requirements_path) is None:
        raise OcrSetupRequired(OCR_SETUP_MESSAGE)
    try:
        from paddleocr import PaddleOCR  # type: ignore[import-not-found]
    except (ImportError, ModuleNotFoundError) as exc:
        raise OcrSetupRequired(OCR_SETUP_MESSAGE) from exc
    normalized_language = language if language in {"it", "en"} else "it"
    modern: dict[str, object] = {
        "text_detection_model_name": "PP-OCRv5_mobile_det",
        "text_recognition_model_name": (
            "latin_PP-OCRv5_mobile_rec"
            if normalized_language == "it"
            else "en_PP-OCRv5_mobile_rec"
        ),
        "use_doc_orientation_classify": False,
        "use_doc_unwarping": False,
        "use_textline_orientation": False,
        "enable_mkldnn": False,
    }
    try:
        return PaddleOCR(**modern)
    except TypeError:
        return PaddleOCR(
            lang=normalized_language,
            use_angle_cls=False,
            show_log=False,
            enable_mkldnn=False,
        )


def _ocr_page_words(
    path: Path,
    page_index: int,
    *,
    language: str,
    render_scale: float = 2.0,
) -> list[OcrWord]:
    try:
        import fitz  # type: ignore[import-not-found]
        import numpy as np  # type: ignore[import-not-found]
        from PIL import Image  # type: ignore[import-not-found]
    except (ImportError, ModuleNotFoundError) as exc:
        raise OcrSetupRequired(OCR_SETUP_MESSAGE) from exc
    engine = _ocr_engine(language)
    with fitz.open(path) as document:
        page = document.load_page(page_index)
        pixmap = page.get_pixmap(
            matrix=fitz.Matrix(render_scale, render_scale), alpha=False
        )
        image = Image.frombytes("RGB", (pixmap.width, pixmap.height), pixmap.samples)
        image_array = np.asarray(image)
    predict = getattr(engine, "predict", None)
    if callable(predict):
        raw = predict(image_array)
    else:
        ocr = getattr(engine, "ocr", None)
        if not callable(ocr):
            raise RuntimeError("No compatible PaddleOCR inference method is available")
        raw = ocr(image_array, cls=False)
    words = _collect_ocr_words(raw)
    return [
        OcrWord(
            word.text,
            tuple(coordinate / render_scale for coordinate in word.bbox),
            word.confidence,
        )
        for word in words
    ]


def _word_row_groups(words: Sequence[OcrWord]) -> list[list[OcrWord]]:
    if not words:
        return []
    heights = [word.bbox[3] - word.bbox[1] for word in words]
    tolerance = max(2.0, median(heights) * 0.60)
    ordered = sorted(
        words,
        key=lambda item: (
            (item.bbox[1] + item.bbox[3]) / 2,
            item.bbox[0],
        ),
    )
    groups: list[list[OcrWord]] = []
    centers: list[float] = []
    for word in ordered:
        center = (word.bbox[1] + word.bbox[3]) / 2
        if not groups or abs(center - centers[-1]) > tolerance:
            groups.append([word])
            centers.append(center)
        else:
            groups[-1].append(word)
            centers[-1] = sum(
                (item.bbox[1] + item.bbox[3]) / 2 for item in groups[-1]
            ) / len(groups[-1])
    return [sorted(group, key=lambda item: item.bbox[0]) for group in groups]


def _visual_row_cells(words: Sequence[OcrWord]) -> list[dict[str, Any]]:
    if not words:
        return []
    heights = [word.bbox[3] - word.bbox[1] for word in words]
    # Keep words as separate geometry tokens here. Multi-word cells are joined
    # later against the header-column boundaries; joining on ordinary word
    # spacing at this stage can irreversibly collapse adjacent narrow columns.
    merge_gap = max(1.0, median(heights) * 0.15)
    groups: list[list[OcrWord]] = []
    for word in words:
        if not groups or word.bbox[0] - groups[-1][-1].bbox[2] > merge_gap:
            groups.append([word])
        else:
            groups[-1].append(word)
    return [
        {
            "raw_value": " ".join(item.text for item in group),
            "bbox": list(_bbox_union([item.bbox for item in group])),
            "confidence": min(item.confidence for item in group),
        }
        for group in groups
    ]


def _visual_table(
    words: Sequence[OcrWord],
    *,
    page_number: int,
    method: str,
) -> dict[str, Any] | None:
    rows = [
        {
            "row_index": index,
            "cells": _visual_row_cells(group),
        }
        for index, group in enumerate(_word_row_groups(words), start=1)
        if group
    ]
    if len(rows) < 2 or max((len(row["cells"]) for row in rows), default=0) < 4:
        return None
    boxes = [
        tuple(float(value) for value in cell["bbox"])
        for row in rows
        for cell in row["cells"]
    ]
    return {
        "table_id": f"pdf_p{page_number:04d}_visual",
        "page": page_number,
        "table_index": 1,
        "layout": "VISUAL",
        "method": method,
        "bbox": list(_bbox_union(boxes)),
        "rows": rows,
    }


def _native_word(value: Mapping[str, Any]) -> OcrWord | None:
    text = _clean_text(value.get("text"))
    bbox = _normalized_bbox(
        (value.get("x0"), value.get("top"), value.get("x1"), value.get("bottom"))
    )
    return OcrWord(text, bbox, 1.0) if text and bbox is not None else None


def _grid_tables(page: Any, page_number: int) -> list[dict[str, Any]]:
    settings = {
        "vertical_strategy": "lines",
        "horizontal_strategy": "lines",
        "snap_tolerance": 3,
        "join_tolerance": 3,
        "intersection_tolerance": 3,
    }
    tables: list[dict[str, Any]] = []
    for table_index, table in enumerate(page.find_tables(settings), start=1):
        extracted = table.extract(x_tolerance=2, y_tolerance=2)
        rows: list[dict[str, Any]] = []
        for row_index, (row, values) in enumerate(
            zip(table.rows, extracted, strict=True), start=1
        ):
            cells = []
            for cell_bbox, value in zip(row.cells, values, strict=True):
                cells.append(
                    {
                        "raw_value": _clean_text(value),
                        "bbox": (
                            None
                            if cell_bbox is None
                            else [float(item) for item in cell_bbox]
                        ),
                        "confidence": 1.0,
                    }
                )
            rows.append({"row_index": row_index, "cells": cells})
        if len(rows) < 2 or max((len(row["cells"]) for row in rows), default=0) < 4:
            continue
        tables.append(
            {
                "table_id": f"pdf_p{page_number:04d}_t{table_index:03d}",
                "page": page_number,
                "table_index": table_index,
                "layout": "GRID",
                "method": "PDF_TEXT_TABLE",
                "bbox": [float(item) for item in table.bbox],
                "rows": rows,
            }
        )
    return tables


def extract_pdf_tables(
    path: Path,
    *,
    ocr_enabled: bool = True,
    ocr_language: str = "it",
    max_bytes: int,
    ocr_word_provider: Callable[..., list[OcrWord]] | None = None,
) -> dict[str, Any]:
    """Return bounded page/table geometry without assigning accounting meaning."""

    if path.is_symlink() or not path.is_file() or path.suffix.lower() != ".pdf":
        raise ValueError("PDF trial balance must be a regular local PDF file")
    if path.stat().st_size > max_bytes:
        raise ValueError("PDF trial balance exceeds the configured input size limit")
    try:
        import pdfplumber  # type: ignore[import-not-found]
    except (ImportError, ModuleNotFoundError) as exc:
        raise RuntimeError("pdfplumber is required for PDF ingestion") from exc
    provider = ocr_word_provider or _ocr_page_words
    tables: list[dict[str, Any]] = []
    page_methods: list[dict[str, Any]] = []
    with pdfplumber.open(path) as pdf:
        if len(pdf.pages) > MAX_PDF_PAGES:
            raise ValueError("PDF trial balance exceeds the 500-page limit")
        for page_index, page in enumerate(pdf.pages):
            page_number = page_index + 1
            text = page.extract_text() or ""
            native_tables = _grid_tables(page, page_number)
            if native_tables:
                tables.extend(native_tables)
                page_methods.append(
                    {
                        "page": page_number,
                        "method": "PDF_TEXT_TABLE",
                        "table_count": len(native_tables),
                    }
                )
                continue
            native_words = [
                word
                for value in page.extract_words(
                    x_tolerance=2,
                    y_tolerance=3,
                    keep_blank_chars=False,
                    use_text_flow=False,
                )
                if (word := _native_word(value)) is not None
            ]
            visual = (
                _visual_table(
                    native_words,
                    page_number=page_number,
                    method="PDF_TEXT_LAYOUT",
                )
                if len(text.strip()) >= MIN_NATIVE_TEXT_CHARS
                else None
            )
            if visual is not None:
                tables.append(visual)
                page_methods.append(
                    {
                        "page": page_number,
                        "method": "PDF_TEXT_LAYOUT",
                        "table_count": 1,
                    }
                )
                continue
            if not ocr_enabled:
                page_methods.append(
                    {"page": page_number, "method": "OCR_REQUIRED", "table_count": 0}
                )
                continue
            words = provider(
                path,
                page_index,
                language=ocr_language,
            )
            ocr_table = _visual_table(
                words,
                page_number=page_number,
                method="PADDLE_OCR_LAYOUT",
            )
            if ocr_table is not None:
                tables.append(ocr_table)
            page_methods.append(
                {
                    "page": page_number,
                    "method": "PADDLE_OCR_LAYOUT",
                    "table_count": 1 if ocr_table is not None else 0,
                }
            )
        page_count = len(pdf.pages)
    if any(item["method"] == "OCR_REQUIRED" for item in page_methods):
        # A partial PDF is not a complete accounting source. Requiring OCR for
        # every unreadable page is mechanically verifiable and prevents silent
        # omission before professional review begins.
        raise OcrSetupRequired(OCR_SETUP_MESSAGE)
    if not tables:
        raise ValueError("No reviewable table was found in the PDF trial balance")
    methods = sorted({str(item["method"]) for item in page_methods})
    return {
        "schema_version": 1,
        "parser_profile": "pdf-trial-balance-layout-v1",
        "page_count": page_count,
        "page_methods": page_methods,
        "methods": methods,
        "tables": tables,
        "ocr_used": "PADDLE_OCR_LAYOUT" in methods,
        "ocr_review_threshold": OCR_CONFIDENCE_REVIEW_THRESHOLD,
    }
