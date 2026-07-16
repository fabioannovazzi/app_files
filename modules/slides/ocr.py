from __future__ import annotations

"""OCR helpers for slide images using PaddleOCR."""

import base64
import io
import logging
import os
import re
import time
from functools import lru_cache
from numbers import Real
from pathlib import Path
from statistics import median
from typing import Any, Callable

import numpy as np
from PIL import Image, ImageFilter, ImageOps, UnidentifiedImageError
from src.slides.layout_semantics import (
    BULLET_BLOCK_TYPES,
    LAYOUT_SEMANTIC_TYPES,
    VISUAL_BLOCK_TYPES,
    block_sort_key,
    normalize_block_type,
    normalize_render_mode,
)

_PROJECT_ROOT = Path(__file__).resolve().parents[2]
_DEFAULT_PADDLEX_CACHE_HOME = _PROJECT_ROOT / ".cache" / "paddlex"
_DEFAULT_MATPLOTLIB_CONFIG_HOME = _PROJECT_ROOT / ".cache" / "matplotlib"


def _configure_paddle_import_environment() -> None:
    os.environ.setdefault(
        "PADDLE_PDX_CACHE_HOME",
        str(_DEFAULT_PADDLEX_CACHE_HOME),
    )
    os.environ.setdefault("PADDLE_PDX_DISABLE_MODEL_SOURCE_CHECK", "True")
    os.environ.setdefault("MPLCONFIGDIR", str(_DEFAULT_MATPLOTLIB_CONFIG_HOME))
    # Paddle 3.x can fail on some CPU oneDNN PIR paths during OCR inference.
    # Keep deterministic defaults here and allow explicit env override.
    os.environ.setdefault("FLAGS_use_mkldnn", "0")


_configure_paddle_import_environment()

try:
    import paddleocr as _paddleocr  # type: ignore[import]

    LayoutDetection = getattr(_paddleocr, "LayoutDetection", None)
    PaddleOCR = getattr(_paddleocr, "PaddleOCR", None)
    PPStructure = getattr(_paddleocr, "PPStructure", None)
    if PPStructure is None:
        PPStructure = getattr(_paddleocr, "PPStructureV3", None)

    _PADDLEOCR_IMPORT_ERROR: Exception | None = None
    _PPSTRUCTURE_IMPORT_ERROR: Exception | None = None
except (
    ImportError,
    OSError,
) as exc:  # pragma: no cover - exercised via monkeypatch tests
    _paddleocr = None
    LayoutDetection = None
    PaddleOCR = None
    PPStructure = None
    _PADDLEOCR_IMPORT_ERROR = exc
    _PPSTRUCTURE_IMPORT_ERROR = exc

__all__ = [
    "SlideOcrEngineUnavailableError",
    "SLIDE_LAYOUT_BLOCK_SCHEMA",
    "SLIDE_LAYOUT_PAYLOAD_SCHEMA",
    "SLIDE_TEXT_LINE_SCHEMA",
    "SLIDE_TEXT_PAYLOAD_SCHEMA",
    "extract_layout_summary_from_raw_layout",
    "extract_lines_from_data_url",
    "extract_lines_from_image_bytes",
    "extract_lines_from_image_path",
    "extract_lines_from_raw_ocr_result",
    "extract_raw_layout_from_data_url",
    "extract_raw_layout_from_image_bytes",
    "extract_raw_layout_from_image_path",
    "extract_raw_ocr_from_data_url",
    "extract_raw_ocr_from_image_bytes",
    "extract_raw_ocr_from_image_path",
    "summarize_layout_blocks",
    "extract_structured_ocr_from_data_url",
    "extract_structured_ocr_from_image_bytes",
    "extract_structured_ocr_from_image_path",
    "extract_text_from_data_url",
    "extract_text_from_image_bytes",
    "extract_text_from_image_path",
    "extract_text_from_raw_ocr_result",
]

LOGGER = logging.getLogger(__name__)

_PADDLE_LANG_MAP = {
    "eng": "en",
    "ita": "it",
    "fra": "fr",
    "deu": "de",
    "en": "en",
    "it": "it",
    "fr": "fr",
    "de": "de",
}

_LAYOUT_TYPE_ALIASES = {
    "title": "title",
    "header": "title",
    "doc_title": "title",
    "text": "text",
    "paragraph": "text",
    "caption": "text",
    "reference": "text",
    "footer": "text",
    "list": "list",
    "table": "table",
    "figure": "figure",
    "image": "figure",
    "chart": "figure",
    "equation": "figure",
}

_LAYOUT_RESULT_COLLECTION_KEYS = (
    "res",
    "parsing_res_list",
    "layout_det_res",
    "region_det_res",
    "table_res_list",
    "formula_res_list",
    "seal_res_list",
    "chart_res_list",
)

_BULLET_PREFIX_PATTERN = re.compile(r"^\s*(?:[-*•·▪◦]|\d+[.)]|[A-Za-z][.)])\s*")

_OCR_PREPROCESS_PROFILE_NONE = "none"
_OCR_PREPROCESS_PROFILE_DOCUMENT_SCAN = "document_scan"
_PADDLE_PIPELINE_DEPENDENCY_ERROR_SNIPPET = (
    "dependency error occurred during pipeline creation"
)


class SlideOcrEngineUnavailableError(RuntimeError):
    """Raised when PaddleOCR cannot be imported or initialized."""


def _emit_ocr_step_event(
    callback: Callable[[str, dict[str, object]], None] | None,
    event: str,
    details: dict[str, object],
) -> None:
    if callback is None:
        return
    event_name = str(event or "").strip()
    if not event_name:
        return
    try:
        callback(event_name, details)
    except (TypeError, ValueError, OSError) as exc:
        LOGGER.warning("Ignoring OCR step callback error: %s", exc)


def _with_paddle_dependency_hint(message: str) -> str:
    detail = str(message or "").strip()
    if _PADDLE_PIPELINE_DEPENDENCY_ERROR_SNIPPET in detail.lower():
        return (
            f"{detail} Install PaddleOCR pipeline dependencies "
            "(for PaddleOCR 3 this usually means `paddlex[ocr]`)."
        )
    return detail


SLIDE_TEXT_LINE_SCHEMA = {
    "type": "object",
    "properties": {
        "slide_id": {"type": "string"},
        "slide_number": {"type": "integer", "minimum": 1},
        "text": {"type": "string"},
        "bbox": {
            "type": "object",
            "properties": {
                "x": {"type": "number"},
                "y": {"type": "number"},
                "w": {"type": "number"},
                "h": {"type": "number"},
            },
            "required": ["x", "y", "w", "h"],
        },
        "confidence": {"type": ["number", "null"], "minimum": 0, "maximum": 1},
        "line_id": {"type": "string"},
    },
    "required": ["text"],
    "anyOf": [{"required": ["slide_id"]}, {"required": ["slide_number"]}],
}

SLIDE_TEXT_PAYLOAD_SCHEMA = {
    "type": "object",
    "properties": {
        "lines": {"type": "array", "items": SLIDE_TEXT_LINE_SCHEMA},
    },
    "required": ["lines"],
}

SLIDE_LAYOUT_BLOCK_SCHEMA = {
    "type": "object",
    "properties": {
        "block_id": {"type": "string"},
        "type": {
            "type": "string",
            "enum": sorted(LAYOUT_SEMANTIC_TYPES),
        },
        "detected_type": {"type": ["string", "null"]},
        "text": {"type": "string"},
        "items": {"type": "array", "items": {"type": "string"}},
        "group_id": {"type": ["string", "null"]},
        "group_kind": {"type": ["string", "null"]},
        "parent_id": {"type": ["string", "null"]},
        "list_level": {"type": ["integer", "null"], "minimum": 0},
        "reading_order": {"type": ["integer", "null"], "minimum": 0},
        "render_mode": {"type": ["string", "null"]},
        "bbox": {
            "type": ["object", "null"],
            "properties": {
                "x": {"type": "number"},
                "y": {"type": "number"},
                "w": {"type": "number"},
                "h": {"type": "number"},
            },
        },
        "confidence": {"type": ["number", "null"], "minimum": 0, "maximum": 1},
    },
    "required": ["block_id", "type", "text"],
}

SLIDE_LAYOUT_PAYLOAD_SCHEMA = {
    "type": "object",
    "properties": {
        "lines": {"type": "array", "items": SLIDE_TEXT_LINE_SCHEMA},
        "blocks": {"type": "array", "items": SLIDE_LAYOUT_BLOCK_SCHEMA},
        "title_text": {"type": "string"},
        "bullet_texts": {"type": "array", "items": {"type": "string"}},
        "figure_regions": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "x": {"type": "number"},
                    "y": {"type": "number"},
                    "w": {"type": "number"},
                    "h": {"type": "number"},
                },
                "required": ["x", "y", "w", "h"],
            },
        },
    },
    "required": ["lines", "blocks", "title_text", "bullet_texts", "figure_regions"],
}


def _normalize_text_line(text: Any) -> str:
    return " ".join(str(text or "").split())


def _decode_data_url(data_url: str) -> bytes:
    if not data_url.startswith("data:") or "," not in data_url:
        raise ValueError("Invalid image data URL.")
    _, encoded = data_url.split(",", 1)
    return base64.b64decode(encoded)


def _is_numeric_value(value: object) -> bool:
    return isinstance(value, Real) and not isinstance(value, bool)


def _as_sequence_list(value: object) -> list[object] | None:
    if isinstance(value, np.ndarray):
        converted = value.tolist()
        if isinstance(converted, list):
            return converted
        if isinstance(converted, tuple):
            return list(converted)
        return [converted]
    if isinstance(value, list):
        return value
    if isinstance(value, tuple):
        return list(value)
    return None


def _as_mapping_dict(value: object) -> dict[str, object] | None:
    if isinstance(value, dict):
        return value

    items_callable = getattr(value, "items", None)
    if callable(items_callable):
        try:
            return {str(key): item for key, item in items_callable()}
        except (TypeError, ValueError):
            return None

    model_dump_callable = getattr(value, "model_dump", None)
    if callable(model_dump_callable):
        try:
            dumped = model_dump_callable(mode="python")
        except TypeError:
            try:
                dumped = model_dump_callable()
            except (TypeError, ValueError):
                dumped = None
        if isinstance(dumped, dict):
            return dumped

    to_dict_callable = getattr(value, "to_dict", None)
    if callable(to_dict_callable):
        try:
            dumped = to_dict_callable()
        except (TypeError, ValueError):
            dumped = None
        if isinstance(dumped, dict):
            return dumped

    return None


def _first_non_none(*values: object) -> object | None:
    for value in values:
        if value is not None:
            return value
    return None


def _jsonify_ocr_value(value: object) -> object:
    if value is None or isinstance(value, (str, bool, int, float)):
        return value
    if isinstance(value, np.generic):
        return value.item()

    mapped = _as_mapping_dict(value)
    if mapped is not None:
        return {str(key): _jsonify_ocr_value(item) for key, item in mapped.items()}

    sequence = _as_sequence_list(value)
    if sequence is not None:
        return [_jsonify_ocr_value(item) for item in sequence]

    return str(value)


def _resolve_paddle_lang(lang: str) -> str:
    normalized = str(lang or "eng").strip().lower()
    if not normalized:
        return "en"
    return _PADDLE_LANG_MAP.get(normalized, normalized)


def _resolve_preprocess_profile(preprocess_profile: str | None) -> str:
    normalized = str(preprocess_profile or _OCR_PREPROCESS_PROFILE_NONE).strip().lower()
    if normalized in {
        _OCR_PREPROCESS_PROFILE_NONE,
        _OCR_PREPROCESS_PROFILE_DOCUMENT_SCAN,
    }:
        return normalized
    LOGGER.warning(
        "Unknown OCR preprocess profile '%s'; defaulting to '%s'.",
        preprocess_profile,
        _OCR_PREPROCESS_PROFILE_NONE,
    )
    return _OCR_PREPROCESS_PROFILE_NONE


def _otsu_threshold(pixel_data: np.ndarray) -> int:
    flat = np.asarray(pixel_data, dtype=np.uint8).ravel()
    if flat.size == 0:
        return 127

    histogram = np.bincount(flat, minlength=256).astype(np.float64)
    total = float(histogram.sum())
    if total <= 0:
        return 127

    sum_total = float(np.dot(np.arange(256, dtype=np.float64), histogram))
    sum_background = 0.0
    weight_background = 0.0
    best_threshold = 127
    best_variance = -1.0

    for level in range(256):
        weight_background += histogram[level]
        if weight_background <= 0:
            continue
        weight_foreground = total - weight_background
        if weight_foreground <= 0:
            break
        sum_background += float(level) * histogram[level]
        mean_background = sum_background / weight_background
        mean_foreground = (sum_total - sum_background) / weight_foreground
        between_class_variance = (
            weight_background
            * weight_foreground
            * (mean_background - mean_foreground) ** 2
        )
        if between_class_variance > best_variance:
            best_variance = between_class_variance
            best_threshold = level
    return best_threshold


def _preprocess_image_for_ocr(
    image: Image.Image, *, preprocess_profile: str
) -> Image.Image:
    profile = _resolve_preprocess_profile(preprocess_profile)
    if profile == _OCR_PREPROCESS_PROFILE_NONE:
        return image.convert("RGB")

    grayscale = ImageOps.grayscale(image.convert("RGB"))
    contrasted = ImageOps.autocontrast(grayscale, cutoff=1)
    denoised = contrasted.filter(ImageFilter.MedianFilter(size=3))
    pixel_data = np.asarray(denoised, dtype=np.uint8)
    threshold = _otsu_threshold(pixel_data)
    binary_data = np.where(pixel_data >= threshold, 255, 0).astype(np.uint8)
    return Image.fromarray(binary_data, mode="L").convert("RGB")


def _normalize_confidence(value: object) -> float | None:
    if not _is_numeric_value(value):
        return None
    confidence = float(value)
    if confidence < 0:
        return None
    if confidence > 1:
        confidence /= 100.0
    return max(0.0, min(1.0, confidence))


def _bbox_from_polygon(raw_points: object) -> dict[str, float] | None:
    points = _as_sequence_list(raw_points)
    if points is None:
        return None
    xs: list[float] = []
    ys: list[float] = []
    for point in points:
        point_values = _as_sequence_list(point)
        if point_values is None or len(point_values) < 2:
            continue
        x_raw, y_raw = point_values[0], point_values[1]
        if not _is_numeric_value(x_raw) or not _is_numeric_value(y_raw):
            continue
        xs.append(float(x_raw))
        ys.append(float(y_raw))
    if len(xs) < 2 or len(ys) < 2:
        return None
    min_x = min(xs)
    max_x = max(xs)
    min_y = min(ys)
    max_y = max(ys)
    if max_x <= min_x or max_y <= min_y:
        return None
    return {"x": min_x, "y": min_y, "w": max_x - min_x, "h": max_y - min_y}


def _bbox_from_layout_bbox(raw_bbox: object) -> dict[str, float] | None:
    if isinstance(raw_bbox, dict):
        x = raw_bbox.get("x")
        y = raw_bbox.get("y")
        w = raw_bbox.get("w")
        h = raw_bbox.get("h")
        if (
            all(_is_numeric_value(value) for value in (x, y, w, h))
            and float(w) > 0
            and float(h) > 0
        ):
            return {"x": float(x), "y": float(y), "w": float(w), "h": float(h)}

    raw_bbox_values = _as_sequence_list(raw_bbox)
    if raw_bbox_values is not None:
        if len(raw_bbox_values) == 4 and all(
            _is_numeric_value(value) for value in raw_bbox_values
        ):
            x0, y0, x1, y1 = [float(value) for value in raw_bbox_values]
            if x1 > x0 and y1 > y0:
                return {"x": x0, "y": y0, "w": x1 - x0, "h": y1 - y0}
        polygon_bbox = _bbox_from_polygon(raw_bbox_values)
        if polygon_bbox is not None:
            return polygon_bbox
    return None


@lru_cache(maxsize=16)
def _get_paddle_ocr(
    lang: str,
    text_recognition_model_name: str | None = None,
):
    if PaddleOCR is None:
        detail = "PaddleOCR is not installed."
        if _PADDLEOCR_IMPORT_ERROR is not None:
            detail = f"{detail} {_PADDLEOCR_IMPORT_ERROR}"
        raise SlideOcrEngineUnavailableError(detail)
    base_ocr_kwargs: dict[str, object] = {
        "lang": lang,
        "enable_mkldnn": False,
        "use_doc_orientation_classify": False,
        "use_doc_unwarping": False,
        "use_textline_orientation": False,
    }
    if text_recognition_model_name:
        base_ocr_kwargs["text_recognition_model_name"] = text_recognition_model_name
    fallback_ocr_kwargs = dict(base_ocr_kwargs)
    fallback_ocr_kwargs.pop("enable_mkldnn", None)
    ocr_kwargs_options: tuple[dict[str, object], ...] = (
        base_ocr_kwargs,
        fallback_ocr_kwargs,
        {
            "lang": lang,
            "enable_mkldnn": False,
            "use_doc_orientation_classify": False,
            "use_doc_unwarping": False,
            "use_textline_orientation": False,
        },
        {
            "lang": lang,
        },
    )
    last_error: Exception | None = None
    for kwargs in ocr_kwargs_options:
        try:
            return PaddleOCR(**kwargs)
        except (RuntimeError, OSError, TypeError, ValueError) as exc:
            last_error = exc
            continue
    raise SlideOcrEngineUnavailableError(
        "Failed to initialize PaddleOCR for language "
        f"'{lang}': {_with_paddle_dependency_hint(str(last_error or 'unknown error'))}"
    )


@lru_cache(maxsize=8)
def _get_paddle_layout(lang: str):
    # Layout analysis is a separate stage from OCR. Prefer the pure layout
    # detector so deck processing does not rerun text recognition here.
    if LayoutDetection is not None:
        layout_detector_kwargs_options: tuple[dict[str, object], ...] = (
            {
                "show_log": False,
                "enable_mkldnn": False,
            },
            {
                "enable_mkldnn": False,
            },
            {
                "show_log": False,
            },
            {},
        )
        last_error: Exception | None = None
        for kwargs in layout_detector_kwargs_options:
            try:
                return LayoutDetection(**kwargs)
            except (RuntimeError, OSError, TypeError, ValueError) as exc:
                last_error = exc
                continue
        raise SlideOcrEngineUnavailableError(
            "Failed to initialize PaddleOCR layout detector: "
            f"{_with_paddle_dependency_hint(str(last_error or 'unknown error'))}"
        )

    if PPStructure is None:
        detail = "PaddleOCR layout engine is not installed."
        if _PPSTRUCTURE_IMPORT_ERROR is not None:
            detail = f"{detail} {_PPSTRUCTURE_IMPORT_ERROR}"
        raise SlideOcrEngineUnavailableError(detail)

    layout_kwargs_options: tuple[dict[str, object], ...] = (
        {
            "show_log": False,
            "lang": lang,
            "layout": True,
            "ocr": False,
            "table": False,
            "enable_mkldnn": False,
        },
        {
            "show_log": False,
            "lang": lang,
            "layout": True,
            "ocr": False,
            "enable_mkldnn": False,
        },
    )
    last_error: Exception | None = None
    for kwargs in layout_kwargs_options:
        try:
            return PPStructure(**kwargs)
        except (RuntimeError, OSError, TypeError, ValueError) as exc:
            last_error = exc
            continue
    raise SlideOcrEngineUnavailableError(
        "Failed to initialize PaddleOCR layout engine for language "
        f"'{lang}': {_with_paddle_dependency_hint(str(last_error or 'unknown error'))}"
    )


def _looks_like_paddle_candidate(value: object) -> bool:
    candidate_values = _as_sequence_list(value)
    if candidate_values is None or len(candidate_values) < 2:
        return False
    points = _as_sequence_list(candidate_values[0])
    text_meta = candidate_values[1]
    if points is None:
        return False
    if isinstance(text_meta, str):
        return True
    text_meta_values = _as_sequence_list(text_meta)
    if text_meta_values:
        return isinstance(text_meta_values[0], str)
    return False


def _flatten_paddle_result(raw_result: object) -> list[object]:
    raw_items = _as_sequence_list(raw_result)
    if raw_items is None:
        return []
    if len(raw_items) == 1:
        first = _as_sequence_list(raw_items[0])
        if first and _looks_like_paddle_candidate(first[0]):
            return [item for item in first if _looks_like_paddle_candidate(item)]
    flattened: list[object] = []
    for item in raw_items:
        if _looks_like_paddle_candidate(item):
            flattened.append(item)
            continue
        item_values = _as_sequence_list(item)
        if item_values is not None:
            flattened.extend(
                nested for nested in item_values if _looks_like_paddle_candidate(nested)
            )
    return flattened


def _flatten_layout_result(raw_result: object) -> list[dict[str, object]]:
    def _looks_like_layout_block_candidate(value: dict[str, object]) -> bool:
        return any(
            key in value
            for key in (
                "type",
                "block_label",
                "layout_label",
                "bbox",
                "box",
                "region",
                "text_region",
                "layout_bbox",
                "res",
                "text",
                "content",
                "block_content",
                "label",
            )
        )

    flattened: list[dict[str, object]] = []
    seen_ids: set[int] = set()

    def _append_candidate(value: dict[str, object]) -> None:
        identity = id(value)
        if identity in seen_ids:
            return
        seen_ids.add(identity)
        flattened.append(value)

    def _walk(value: object) -> None:
        value_dict = _as_mapping_dict(value)
        if value_dict is not None:
            if _looks_like_layout_block_candidate(value_dict):
                _append_candidate(value_dict)
            for key in _LAYOUT_RESULT_COLLECTION_KEYS:
                nested = value_dict.get(key)
                if nested is None:
                    continue
                _walk(nested)
            for key, nested in value_dict.items():
                if key in _LAYOUT_RESULT_COLLECTION_KEYS:
                    continue
                if (
                    _as_mapping_dict(nested) is not None
                    or _as_sequence_list(nested) is not None
                ):
                    _walk(nested)
            return
        values = _as_sequence_list(value)
        if values is None:
            return
        for item in values:
            _walk(item)

    _walk(raw_result)
    return flattened


def _parse_paddle_candidate(
    candidate: object,
) -> tuple[str, dict[str, float], float | None] | None:
    if not _looks_like_paddle_candidate(candidate):
        return None
    candidate_values = _as_sequence_list(candidate)
    if candidate_values is None or len(candidate_values) < 2:
        return None
    raw_points = candidate_values[0]
    raw_text_meta = candidate_values[1]
    bbox = _bbox_from_polygon(raw_points)
    if bbox is None:
        return None

    text = ""
    confidence: float | None = None
    raw_text_meta_values = _as_sequence_list(raw_text_meta)
    if raw_text_meta_values is not None:
        if raw_text_meta_values:
            text = str(raw_text_meta_values[0] or "")
        if len(raw_text_meta_values) > 1:
            confidence = _normalize_confidence(raw_text_meta_values[1])
    elif isinstance(raw_text_meta, str):
        text = raw_text_meta

    normalized_text = _normalize_text_line(text)
    if not normalized_text:
        return None
    return normalized_text, bbox, confidence


def _append_line_entry(
    lines: list[dict[str, object]],
    *,
    text: object,
    bbox: dict[str, float] | None,
    confidence: float | None,
    slide_id: str | None,
    slide_number: int | None,
) -> None:
    if bbox is None:
        return
    normalized_text = _normalize_text_line(text)
    if not normalized_text:
        return
    line_id = f"line-{len(lines)}"
    entry: dict[str, object] = {
        "id": line_id,
        "line_id": line_id,
        "text": normalized_text,
        "bbox": bbox,
        "confidence": confidence,
    }
    if slide_id:
        entry["slide_id"] = slide_id
    if slide_number is not None:
        entry["slide_number"] = slide_number
    lines.append(entry)


def _extract_lines_from_dict_result(
    raw_result: object,
    *,
    slide_id: str | None,
    slide_number: int | None,
) -> list[dict[str, object]]:
    if isinstance(raw_result, dict):
        records: list[dict[str, object]] = [raw_result]
    elif _as_sequence_list(raw_result) is not None:
        records = [
            item
            for item in _as_sequence_list(raw_result) or []
            if isinstance(item, dict)
        ]
    else:
        return []

    lines: list[dict[str, object]] = []
    for record in records:
        polys_raw = _first_non_none(
            record.get("dt_polys"),
            record.get("polys"),
            record.get("boxes"),
        )
        texts_raw = _first_non_none(record.get("rec_texts"), record.get("texts"))
        scores_raw = _first_non_none(record.get("rec_scores"), record.get("scores"))
        polys_values = _as_sequence_list(polys_raw)
        texts_values = _as_sequence_list(texts_raw)
        scores_values = _as_sequence_list(scores_raw)

        emitted = False
        if polys_values is not None and texts_values is not None:
            limit = min(len(polys_values), len(texts_values))
            for index in range(limit):
                bbox = _bbox_from_polygon(
                    polys_values[index]
                ) or _bbox_from_layout_bbox(polys_values[index])
                confidence = None
                if scores_values is not None and index < len(scores_values):
                    confidence = _normalize_confidence(scores_values[index])
                _append_line_entry(
                    lines,
                    text=texts_values[index],
                    bbox=bbox,
                    confidence=confidence,
                    slide_id=slide_id,
                    slide_number=slide_number,
                )
            emitted = limit > 0

        if emitted:
            continue

        bbox = _bbox_from_polygon(
            _first_non_none(record.get("dt_poly"), record.get("poly"))
        ) or _bbox_from_layout_bbox(
            _first_non_none(
                record.get("bbox"),
                record.get("box"),
                record.get("region"),
                record.get("dt_poly"),
                record.get("poly"),
            )
        )
        confidence = _normalize_confidence(
            _first_non_none(
                record.get("rec_score"),
                record.get("score"),
                record.get("confidence"),
            )
        )
        _append_line_entry(
            lines,
            text=_first_non_none(
                record.get("rec_text"),
                record.get("text"),
                record.get("transcription"),
                "",
            ),
            bbox=bbox,
            confidence=confidence,
            slide_id=slide_id,
            slide_number=slide_number,
        )
    return lines


def _normalize_layout_type(raw_type: object) -> str:
    normalized = str(raw_type or "").strip().lower().replace(" ", "_")
    if not normalized:
        return "unknown"
    return _LAYOUT_TYPE_ALIASES.get(normalized, "unknown")


def _extract_text_item(raw_item: object) -> tuple[str, float | None]:
    text = ""
    confidence: float | None = None
    if isinstance(raw_item, dict):
        text = _normalize_text_line(
            _first_non_none(
                raw_item.get("text"),
                raw_item.get("transcription"),
                raw_item.get("label"),
                raw_item.get("content"),
                "",
            )
        )
        confidence = _normalize_confidence(
            _first_non_none(
                raw_item.get("confidence"),
                raw_item.get("score"),
                raw_item.get("probability"),
            )
        )
    elif _as_sequence_list(raw_item) is not None:
        raw_item_values = _as_sequence_list(raw_item) or []
        if raw_item_values:
            text = _normalize_text_line(raw_item_values[0])
        if len(raw_item_values) > 1:
            confidence = _normalize_confidence(raw_item_values[1])
    elif isinstance(raw_item, str):
        text = _normalize_text_line(raw_item)
    return text, confidence


def _extract_layout_block_text_and_items(
    raw_result: object,
) -> tuple[str, list[str], float | None]:
    if raw_result is None:
        return "", [], None

    text_items: list[str] = []
    confidences: list[float] = []

    if isinstance(raw_result, list):
        for candidate in raw_result:
            text, confidence = _extract_text_item(candidate)
            if text:
                text_items.append(text)
            if confidence is not None:
                confidences.append(confidence)
    else:
        text, confidence = _extract_text_item(raw_result)
        if text:
            text_items.append(text)
        if confidence is not None:
            confidences.append(confidence)

    block_text = "\n".join(text_items).strip()
    confidence_avg = sum(confidences) / float(len(confidences)) if confidences else None
    return block_text, text_items, confidence_avg


def _normalize_bullet_item(value: str) -> str:
    cleaned = _BULLET_PREFIX_PATTERN.sub("", str(value or "")).strip()
    return _normalize_text_line(cleaned)


def _normalize_bullet_block_text(value: str) -> str:
    segments = [
        segment.strip() for segment in str(value or "").splitlines() if segment.strip()
    ]
    compact = " ".join(segments).strip()
    return _normalize_bullet_item(compact)


def _resolve_style_title_ratio(style_hint: dict[str, object] | None) -> float | None:
    if not isinstance(style_hint, dict):
        return None
    raw_ratio = style_hint.get("title_to_body_ratio")
    if isinstance(raw_ratio, (int, float)) and float(raw_ratio) > 1:
        return float(raw_ratio)
    title_size = style_hint.get("title_size_pt")
    body_size = style_hint.get("body_size_pt")
    if isinstance(title_size, (int, float)) and isinstance(body_size, (int, float)):
        title_val = float(title_size)
        body_val = float(body_size)
        if title_val > 0 and body_val > 0:
            return title_val / body_val
    return None


def _score_title_block(
    block: dict[str, object],
    *,
    expected_ratio: float | None,
    baseline_height: float | None,
    max_bottom: float | None,
) -> float:
    text = _normalize_text_line(block.get("text"))
    if not text:
        return -1e9
    score = 0.0
    if str(block.get("type") or "") == "title":
        score += 3.0

    bbox = block.get("bbox")
    if isinstance(bbox, dict):
        y_raw = bbox.get("y")
        h_raw = bbox.get("h")
        if isinstance(y_raw, (int, float)) and isinstance(h_raw, (int, float)):
            y = float(y_raw)
            h = float(h_raw)
            if h > 0 and baseline_height and baseline_height > 0:
                observed_ratio = h / baseline_height
                if expected_ratio:
                    score += max(0.0, 2.0 - abs(observed_ratio - expected_ratio) * 2.5)
                elif observed_ratio >= 1.2:
                    score += min(1.5, observed_ratio - 1.0)
            if max_bottom and max_bottom > 0:
                score += max(0.0, 1.0 - (y / max_bottom))
    return score


def _coerce_summary_bbox(
    block: dict[str, object],
) -> tuple[float, float, float, float] | None:
    bbox = block.get("bbox")
    if not isinstance(bbox, dict):
        return None
    if not all(isinstance(bbox.get(key), (int, float)) for key in ("x", "y", "w", "h")):
        return None
    x = float(bbox["x"])
    y = float(bbox["y"])
    w = float(bbox["w"])
    h = float(bbox["h"])
    if w <= 0 or h <= 0:
        return None
    return x, y, w, h


def _expand_multiline_title_text(
    *,
    sorted_blocks: list[dict[str, object]],
    anchor_block: dict[str, object],
    baseline_height: float | None,
    fallback_text: str,
) -> str:
    anchor_bbox = _coerce_summary_bbox(anchor_block)
    if anchor_bbox is None:
        return fallback_text
    anchor_x, anchor_y, anchor_w, anchor_h = anchor_bbox
    baseline = baseline_height if baseline_height and baseline_height > 0 else anchor_h
    band_top = max(0.0, anchor_y - max(12.0, anchor_h * 0.50))
    band_bottom = anchor_y + max(anchor_h * 2.8, baseline * 3.0, 72.0)
    col_left = anchor_x - max(24.0, anchor_w * 0.12)
    col_right = anchor_x + anchor_w + max(24.0, anchor_w * 0.12)

    candidates: list[tuple[float, float, float, str]] = []
    for block in sorted_blocks:
        text = _normalize_text_line(block.get("text"))
        if not text:
            continue
        if _BULLET_PREFIX_PATTERN.match(text):
            continue
        block_type = str(block.get("type") or "").strip().lower()
        if block_type in {"figure", "table"}:
            continue
        bbox = _coerce_summary_bbox(block)
        if bbox is None:
            continue
        bx, by, bw, bh = bbox
        if block_type != "title":
            relative_height = bh / max(anchor_h, 1.0)
            if relative_height < 0.72 or relative_height > 1.45:
                continue
        if (by + bh) < band_top or by > band_bottom:
            continue
        overlap_w = max(0.0, min(col_right, bx + bw) - max(col_left, bx))
        overlap_ratio = overlap_w / max(bw, 1.0)
        center_x = bx + (bw / 2.0)
        if overlap_ratio < 0.30 and not (col_left <= center_x <= col_right):
            continue
        candidates.append((by, bx, bh, text))

    if not candidates:
        return fallback_text

    ordered_candidates = sorted(candidates, key=lambda item: (item[0], item[1]))
    selected_lines: list[tuple[float, float, str]] = []
    previous_bottom: float | None = None
    previous_height: float | None = None
    for by, bx, bh, text in ordered_candidates:
        if not selected_lines:
            selected_lines.append((by, bx, text))
            previous_bottom = by + bh
            previous_height = bh
            continue
        assert previous_bottom is not None
        gap = by - previous_bottom
        reference_height = (
            previous_height
            if previous_height is not None and previous_height > 0
            else baseline
        )
        allowed_gap = max(34.0, reference_height * 1.65)
        if gap > allowed_gap:
            break
        selected_lines.append((by, bx, text))
        previous_bottom = max(previous_bottom, by + bh)
        previous_height = max(reference_height, bh)
        if len(selected_lines) >= 4:
            break

    if not selected_lines:
        return fallback_text

    deduped_lines: list[str] = []
    seen_lines: set[str] = set()
    for _y, _x, text in selected_lines:
        key = text.lower()
        if key in seen_lines:
            continue
        seen_lines.add(key)
        deduped_lines.append(text)
    if not deduped_lines:
        return fallback_text
    if len(deduped_lines) == 1:
        return deduped_lines[0]
    return "\n".join(deduped_lines)


def _derive_layout_summary(
    blocks: list[dict[str, object]],
    *,
    style_hint: dict[str, object] | None = None,
) -> tuple[str, list[str], list[dict[str, float]]]:
    sorted_blocks = sorted(blocks, key=block_sort_key)

    title_text = ""
    expected_ratio = _resolve_style_title_ratio(style_hint)
    max_bottom: float | None = None
    body_block_heights: list[float] = []
    any_text_block_heights: list[float] = []
    for block in sorted_blocks:
        bbox = block.get("bbox")
        text = _normalize_text_line(block.get("text"))
        if not text or not isinstance(bbox, dict):
            continue
        y_raw = bbox.get("y")
        h_raw = bbox.get("h")
        if not isinstance(y_raw, (int, float)) or not isinstance(h_raw, (int, float)):
            continue
        y = float(y_raw)
        h = float(h_raw)
        if h <= 0:
            continue
        any_text_block_heights.append(h)
        block_type = normalize_block_type(block.get("type"))
        if block_type in {"body_text", "bullet_item", "group_label"}:
            body_block_heights.append(h)
        bottom = y + h
        max_bottom = bottom if max_bottom is None else max(max_bottom, bottom)

    baseline_height: float | None = None
    if body_block_heights:
        baseline_height = float(median(body_block_heights))
    elif any_text_block_heights:
        baseline_height = float(median(any_text_block_heights))

    explicit_title_blocks = [
        block
        for block in sorted_blocks
        if normalize_block_type(block.get("type")) == "title"
        and _normalize_text_line(block.get("text"))
    ]
    chosen_title_block: dict[str, object] | None = None
    if explicit_title_blocks:
        if expected_ratio is not None:
            chosen = max(
                explicit_title_blocks,
                key=lambda block: _score_title_block(
                    block,
                    expected_ratio=expected_ratio,
                    baseline_height=baseline_height,
                    max_bottom=max_bottom,
                ),
            )
            title_text = _normalize_text_line(chosen.get("text"))
            chosen_title_block = chosen
        else:
            chosen_title_block = explicit_title_blocks[0]
            title_text = _normalize_text_line(chosen_title_block.get("text"))

    if not title_text and expected_ratio is not None:
        text_blocks = [
            block for block in sorted_blocks if _normalize_text_line(block.get("text"))
        ]
        if text_blocks:
            chosen = max(
                text_blocks,
                key=lambda block: _score_title_block(
                    block,
                    expected_ratio=expected_ratio,
                    baseline_height=baseline_height,
                    max_bottom=max_bottom,
                ),
            )
            title_text = _normalize_text_line(chosen.get("text"))
            chosen_title_block = chosen

    if not title_text:
        for block in sorted_blocks:
            text = _normalize_text_line(block.get("text"))
            if text:
                title_text = text
                chosen_title_block = block
                break
    if title_text and chosen_title_block is not None:
        title_text = _expand_multiline_title_text(
            sorted_blocks=sorted_blocks,
            anchor_block=chosen_title_block,
            baseline_height=baseline_height,
            fallback_text=title_text,
        )

    bullet_texts: list[str] = []
    seen_bullets: set[str] = set()
    for block in sorted_blocks:
        block_type = normalize_block_type(block.get("type"))
        if (
            normalize_render_mode(block.get("render_mode") or block.get("renderMode"))
            == "group_as_image"
        ):
            continue
        text = str(block.get("text") or "")
        candidate_items = (
            block.get("items")
            if isinstance(block.get("items"), list)
            else text.splitlines()
        )
        if block_type in BULLET_BLOCK_TYPES:
            normalized_items = [
                _normalize_bullet_item(str(raw_item or ""))
                for raw_item in candidate_items
            ]
            if not any(normalized_items):
                normalized_items = [_normalize_bullet_block_text(text)]
            for item in normalized_items:
                if not item:
                    continue
                key = item.lower()
                if key in seen_bullets:
                    continue
                seen_bullets.add(key)
                bullet_texts.append(item)
            continue
        if any(
            _BULLET_PREFIX_PATTERN.match(str(item or "")) for item in candidate_items
        ):
            for raw_item in candidate_items:
                item = _normalize_bullet_item(str(raw_item or ""))
                if not item:
                    continue
                key = item.lower()
                if key in seen_bullets:
                    continue
                seen_bullets.add(key)
                bullet_texts.append(item)

    figure_regions: list[dict[str, float]] = []
    grouped_regions: dict[str, list[dict[str, float]]] = {}
    for block in sorted_blocks:
        bbox = block.get("bbox")
        if not isinstance(bbox, dict):
            continue
        if not all(
            isinstance(bbox.get(key), (int, float)) for key in ("x", "y", "w", "h")
        ):
            continue
        normalized_bbox = {
            "x": float(bbox["x"]),
            "y": float(bbox["y"]),
            "w": float(bbox["w"]),
            "h": float(bbox["h"]),
        }
        render_mode = normalize_render_mode(
            block.get("render_mode") or block.get("renderMode")
        )
        group_id = str(block.get("group_id") or block.get("groupId") or "").strip()
        block_type = normalize_block_type(block.get("type"))
        if render_mode == "group_as_image" and group_id:
            grouped_regions.setdefault(group_id, []).append(normalized_bbox)
            continue
        if block_type not in VISUAL_BLOCK_TYPES:
            continue
        figure_regions.append(normalized_bbox)

    for group_id in sorted(grouped_regions):
        regions = grouped_regions[group_id]
        left = min(region["x"] for region in regions)
        top = min(region["y"] for region in regions)
        right = max(region["x"] + region["w"] for region in regions)
        bottom = max(region["y"] + region["h"] for region in regions)
        figure_regions.append(
            {
                "x": left,
                "y": top,
                "w": max(1.0, right - left),
                "h": max(1.0, bottom - top),
            }
        )

    return title_text, bullet_texts, figure_regions


def summarize_layout_blocks(
    blocks: list[dict[str, object]],
    *,
    style_hint: dict[str, object] | None = None,
) -> dict[str, object]:
    title_text, bullet_texts, figure_regions = _derive_layout_summary(
        blocks,
        style_hint=style_hint,
    )
    return {
        "blocks": blocks,
        "title_text": title_text,
        "bullet_texts": bullet_texts,
        "figure_regions": figure_regions,
    }


def _extract_lines_from_raw_result(
    raw_result: object,
    *,
    slide_id: str | None,
    slide_number: int | None,
) -> list[dict[str, object]]:
    dict_lines = _extract_lines_from_dict_result(
        raw_result,
        slide_id=slide_id,
        slide_number=slide_number,
    )
    if dict_lines:
        return dict_lines

    candidates = _flatten_paddle_result(raw_result)
    lines: list[dict[str, object]] = []
    for candidate in candidates:
        parsed = _parse_paddle_candidate(candidate)
        if parsed is None:
            continue
        text, bbox, confidence = parsed
        _append_line_entry(
            lines,
            text=text,
            bbox=bbox,
            confidence=confidence,
            slide_id=slide_id,
            slide_number=slide_number,
        )
    return lines


def _run_paddle_ocr(
    ocr_engine: Any, image_rgb: np.ndarray, *, paddle_lang: str
) -> object:
    attempt_errors: list[Exception] = []

    ocr_callable = getattr(ocr_engine, "ocr", None)
    if callable(ocr_callable):
        try:
            return ocr_callable(image_rgb)
        except TypeError:
            try:
                return ocr_callable(image_rgb, cls=True)
            except (
                RuntimeError,
                OSError,
                TypeError,
                ValueError,
                AttributeError,
            ) as exc:
                attempt_errors.append(exc)
        except (RuntimeError, OSError, TypeError, ValueError, AttributeError) as exc:
            attempt_errors.append(exc)

    predict_callable = getattr(ocr_engine, "predict", None)
    if callable(predict_callable):
        for candidate_input in (image_rgb, [image_rgb]):
            try:
                return predict_callable(candidate_input)
            except (
                RuntimeError,
                OSError,
                TypeError,
                ValueError,
                AttributeError,
            ) as exc:
                attempt_errors.append(exc)

    error_text = "; ".join(str(err) for err in attempt_errors if str(err))
    if not error_text:
        error_text = "No compatible OCR callable found on PaddleOCR engine."
    raise SlideOcrEngineUnavailableError(
        f"PaddleOCR inference failed for language '{paddle_lang}': {error_text}"
    )


def _ocr_quality_metrics(
    lines: list[dict[str, object]],
) -> tuple[int, int, float | None]:
    line_count = 0
    char_count = 0
    confidences: list[float] = []
    for line in lines:
        text = str(line.get("text") or "").strip()
        if not text:
            continue
        line_count += 1
        char_count += sum(1 for char in text if char.isalnum())
        confidence = line.get("confidence")
        if isinstance(confidence, (int, float)):
            confidences.append(float(confidence))
    confidence_median = float(median(confidences)) if confidences else None
    return line_count, char_count, confidence_median


def _ocr_result_is_weak(lines: list[dict[str, object]]) -> bool:
    line_count, char_count, confidence = _ocr_quality_metrics(lines)
    if line_count <= 1:
        return True
    if char_count < 40:
        return True
    if confidence is not None and confidence < 0.45:
        return True
    return False


def _prefer_preprocessed_result(
    *,
    current_lines: list[dict[str, object]],
    candidate_lines: list[dict[str, object]],
) -> bool:
    current_line_count, current_char_count, current_confidence = _ocr_quality_metrics(
        current_lines
    )
    candidate_line_count, candidate_char_count, candidate_confidence = (
        _ocr_quality_metrics(candidate_lines)
    )
    if candidate_char_count <= 0:
        return False
    if current_char_count <= 0 and candidate_char_count > 0:
        return True
    if candidate_char_count >= current_char_count + 12:
        return True
    if (
        candidate_line_count >= current_line_count + 2
        and candidate_char_count >= current_char_count
    ):
        return True
    if (
        candidate_confidence is not None
        and current_confidence is not None
        and candidate_char_count >= current_char_count
        and candidate_confidence >= current_confidence + 0.08
    ):
        return True
    return False


def _extract_raw_ocr_from_image(
    image: Image.Image,
    lang: str,
    *,
    preprocess_profile: str = _OCR_PREPROCESS_PROFILE_NONE,
    allow_preprocess_fallback: bool = False,
    text_recognition_model_name: str | None = None,
) -> object:
    paddle_lang = _resolve_paddle_lang(lang)
    ocr_engine = _get_paddle_ocr(
        paddle_lang,
        text_recognition_model_name=text_recognition_model_name,
    )

    baseline_rgb = np.asarray(image.convert("RGB"))
    raw_result = _run_paddle_ocr(ocr_engine, baseline_rgb, paddle_lang=paddle_lang)
    lines = _extract_lines_from_raw_result(
        raw_result,
        slide_id=None,
        slide_number=None,
    )

    resolved_profile = _resolve_preprocess_profile(preprocess_profile)
    if (
        allow_preprocess_fallback
        and resolved_profile != _OCR_PREPROCESS_PROFILE_NONE
        and _ocr_result_is_weak(lines)
    ):
        preprocessed = _preprocess_image_for_ocr(
            image, preprocess_profile=resolved_profile
        )
        preprocessed_rgb = np.asarray(preprocessed)
        preprocessed_result = _run_paddle_ocr(
            ocr_engine, preprocessed_rgb, paddle_lang=paddle_lang
        )
        candidate_lines = _extract_lines_from_raw_result(
            preprocessed_result,
            slide_id=None,
            slide_number=None,
        )
        if _prefer_preprocessed_result(
            current_lines=lines, candidate_lines=candidate_lines
        ):
            raw_result = preprocessed_result
    return _jsonify_ocr_value(raw_result)


def extract_text_from_raw_ocr_result(raw_result: object) -> str:
    lines = _extract_lines_from_raw_result(
        raw_result,
        slide_id=None,
        slide_number=None,
    )
    text_lines = [
        str(line.get("text") or "").strip()
        for line in lines
        if isinstance(line, dict) and str(line.get("text") or "").strip()
    ]
    return "\n".join(text_lines).strip()


def extract_lines_from_raw_ocr_result(
    raw_result: object,
    *,
    slide_id: str | None = None,
    slide_number: int | None = None,
) -> list[dict[str, object]]:
    return _extract_lines_from_raw_result(
        raw_result,
        slide_id=slide_id,
        slide_number=slide_number,
    )


def _extract_lines_from_image(
    image: Image.Image,
    lang: str,
    *,
    slide_id: str | None,
    slide_number: int | None,
    preprocess_profile: str = _OCR_PREPROCESS_PROFILE_NONE,
    allow_preprocess_fallback: bool = False,
) -> list[dict[str, object]]:
    raw_result = _extract_raw_ocr_from_image(
        image,
        lang,
        preprocess_profile=preprocess_profile,
        allow_preprocess_fallback=allow_preprocess_fallback,
    )
    return _extract_lines_from_raw_result(
        raw_result,
        slide_id=slide_id,
        slide_number=slide_number,
    )


def _run_paddle_layout(
    layout_engine: Any,
    image_rgb: np.ndarray,
    *,
    paddle_lang: str,
) -> object:
    attempt_errors: list[Exception] = []

    for candidate_input in (image_rgb, [image_rgb]):
        try:
            return layout_engine(candidate_input)
        except (RuntimeError, OSError, TypeError, ValueError, AttributeError) as exc:
            attempt_errors.append(exc)

    predict_callable = getattr(layout_engine, "predict", None)
    if callable(predict_callable):
        for candidate_input in (image_rgb, [image_rgb]):
            try:
                return predict_callable(candidate_input)
            except (
                RuntimeError,
                OSError,
                TypeError,
                ValueError,
                AttributeError,
            ) as exc:
                attempt_errors.append(exc)

    error_text = "; ".join(str(err) for err in attempt_errors if str(err))
    if not error_text:
        error_text = "No compatible layout callable found on PaddleOCR layout engine."
    raise SlideOcrEngineUnavailableError(
        f"PaddleOCR layout inference failed for language '{paddle_lang}': {error_text}"
    )


def _extract_layout_blocks_from_raw_result(
    raw_result: object,
    *,
    slide_id: str | None,
    slide_number: int | None,
) -> list[dict[str, object]]:
    blocks: list[dict[str, object]] = []
    for raw_block in _flatten_layout_result(raw_result):
        block_type = _normalize_layout_type(
            _first_non_none(
                raw_block.get("type"),
                raw_block.get("block_label"),
                raw_block.get("layout_label"),
                raw_block.get("category"),
                raw_block.get("label"),
            )
        )
        bbox = _bbox_from_layout_bbox(
            _first_non_none(
                raw_block.get("bbox"),
                raw_block.get("box"),
                raw_block.get("region"),
                raw_block.get("text_region"),
                raw_block.get("layout_bbox"),
                raw_block.get("layout_box"),
                raw_block.get("coordinate"),
                raw_block.get("coordinates"),
            )
        )
        text, items, inner_confidence = _extract_layout_block_text_and_items(
            _first_non_none(
                raw_block.get("res"),
                raw_block.get("block_content"),
                raw_block.get("content"),
                raw_block.get("texts"),
                raw_block.get("ocr_res"),
            )
        )
        if not text:
            text = _normalize_text_line(
                _first_non_none(
                    raw_block.get("text"),
                    raw_block.get("content"),
                    raw_block.get("block_content"),
                    "",
                )
            )
        if block_type != "list":
            items = []

        confidence = inner_confidence
        if confidence is None:
            confidence = _normalize_confidence(
                _first_non_none(
                    raw_block.get("confidence"),
                    raw_block.get("score"),
                    raw_block.get("probability"),
                    raw_block.get("layout_score"),
                    raw_block.get("det_score"),
                )
            )

        if block_type == "unknown" and bbox is None and not text:
            continue

        block_id = f"block-{len(blocks)}"
        entry: dict[str, object] = {
            "id": block_id,
            "block_id": block_id,
            "type": block_type,
            "text": text,
            "items": items,
            "bbox": bbox,
            "confidence": confidence,
        }
        if slide_id:
            entry["slide_id"] = slide_id
        if slide_number is not None:
            entry["slide_number"] = slide_number
        blocks.append(entry)
    return blocks


def _extract_raw_layout_from_image(
    image: Image.Image,
    lang: str,
) -> object:
    paddle_lang = _resolve_paddle_lang(lang)
    layout_engine = _get_paddle_layout(paddle_lang)
    image_rgb = np.asarray(image.convert("RGB"))
    raw_result = _run_paddle_layout(layout_engine, image_rgb, paddle_lang=paddle_lang)
    return _jsonify_ocr_value(raw_result)


def _extract_layout_blocks_from_image(
    image: Image.Image,
    lang: str,
    *,
    slide_id: str | None,
    slide_number: int | None,
) -> list[dict[str, object]]:
    raw_result = _extract_raw_layout_from_image(image, lang)
    return _extract_layout_blocks_from_raw_result(
        raw_result,
        slide_id=slide_id,
        slide_number=slide_number,
    )


def extract_layout_summary_from_raw_layout(
    raw_layout: object,
    *,
    slide_id: str | None = None,
    slide_number: int | None = None,
    style_hint: dict[str, object] | None = None,
) -> dict[str, object]:
    blocks = _extract_layout_blocks_from_raw_result(
        raw_layout,
        slide_id=slide_id,
        slide_number=slide_number,
    )
    title_text, bullet_texts, figure_regions = _derive_layout_summary(
        blocks,
        style_hint=style_hint,
    )
    return {
        "blocks": blocks,
        "title_text": title_text,
        "bullet_texts": bullet_texts,
        "figure_regions": figure_regions,
    }


def _extract_structured_ocr_from_image(
    image: Image.Image,
    lang: str,
    *,
    slide_id: str | None,
    slide_number: int | None,
    style_hint: dict[str, object] | None = None,
    include_layout: bool = True,
    preprocess_profile: str = _OCR_PREPROCESS_PROFILE_NONE,
    allow_preprocess_fallback: bool = False,
    step_callback: Callable[[str, dict[str, object]], None] | None = None,
) -> dict[str, object]:
    step_base: dict[str, object] = {}
    if slide_id:
        step_base["slideId"] = slide_id
    if slide_number is not None:
        step_base["slideNumber"] = int(slide_number)
    step_base["lang"] = str(lang)

    lines_started_at = time.perf_counter()
    _emit_ocr_step_event(
        step_callback,
        "lines_start",
        {**step_base, "phase": "lines"},
    )
    raw_ocr = _extract_raw_ocr_from_image(
        image,
        lang,
        preprocess_profile=preprocess_profile,
        allow_preprocess_fallback=allow_preprocess_fallback,
    )
    lines = _extract_lines_from_raw_result(
        raw_ocr,
        slide_id=slide_id,
        slide_number=slide_number,
    )
    ocr_text = extract_text_from_raw_ocr_result(raw_ocr)
    _emit_ocr_step_event(
        step_callback,
        "lines_done",
        {
            **step_base,
            "phase": "lines",
            "elapsedMs": round((time.perf_counter() - lines_started_at) * 1000.0, 1),
            "lineCount": len(lines),
        },
    )

    if include_layout:
        layout_started_at = time.perf_counter()
        _emit_ocr_step_event(
            step_callback,
            "layout_start",
            {**step_base, "phase": "layout"},
        )
        raw_layout = _extract_raw_layout_from_image(
            image,
            lang,
        )
        layout_summary = extract_layout_summary_from_raw_layout(
            raw_layout,
            slide_id=slide_id,
            slide_number=slide_number,
            style_hint=style_hint,
        )
        blocks = (
            layout_summary.get("blocks")
            if isinstance(layout_summary.get("blocks"), list)
            else []
        )
        _emit_ocr_step_event(
            step_callback,
            "layout_done",
            {
                **step_base,
                "phase": "layout",
                "elapsedMs": round(
                    (time.perf_counter() - layout_started_at) * 1000.0, 1
                ),
                "blockCount": len(blocks),
            },
        )

        summary_started_at = time.perf_counter()
        title_text = str(layout_summary.get("title_text") or "").strip()
        bullet_texts = (
            layout_summary.get("bullet_texts")
            if isinstance(layout_summary.get("bullet_texts"), list)
            else []
        )
        figure_regions = (
            layout_summary.get("figure_regions")
            if isinstance(layout_summary.get("figure_regions"), list)
            else []
        )
        _emit_ocr_step_event(
            step_callback,
            "summary_done",
            {
                **step_base,
                "phase": "summary",
                "elapsedMs": round(
                    (time.perf_counter() - summary_started_at) * 1000.0, 1
                ),
                "figureRegionCount": len(figure_regions),
                "bulletCount": len(bullet_texts),
                "hasTitle": bool(title_text),
            },
        )
    else:
        raw_layout = None
        blocks = []
        title_text = ""
        bullet_texts = []
        figure_regions = []

    return {
        "raw_ocr": raw_ocr,
        "raw_layout": raw_layout,
        "ocr_text": ocr_text,
        "lines": lines,
        "blocks": blocks,
        "title_text": title_text,
        "bullet_texts": bullet_texts,
        "figure_regions": figure_regions,
    }


def extract_raw_ocr_from_data_url(
    data_url: str,
    lang: str = "eng",
    *,
    preprocess_profile: str = _OCR_PREPROCESS_PROFILE_NONE,
    allow_preprocess_fallback: bool = False,
    text_recognition_model_name: str | None = None,
) -> object:
    try:
        image_bytes = _decode_data_url(data_url)
    except (ValueError, base64.binascii.Error) as exc:
        LOGGER.warning("Invalid image data URL supplied for OCR.", exc_info=exc)
        raise
    return extract_raw_ocr_from_image_bytes(
        image_bytes,
        lang,
        preprocess_profile=preprocess_profile,
        allow_preprocess_fallback=allow_preprocess_fallback,
        text_recognition_model_name=text_recognition_model_name,
    )


def extract_raw_ocr_from_image_bytes(
    image_bytes: bytes,
    lang: str = "eng",
    *,
    preprocess_profile: str = _OCR_PREPROCESS_PROFILE_NONE,
    allow_preprocess_fallback: bool = False,
    text_recognition_model_name: str | None = None,
) -> object:
    try:
        image = Image.open(io.BytesIO(image_bytes))
    except UnidentifiedImageError as exc:
        LOGGER.warning("Unable to decode image for OCR.", exc_info=exc)
        raise
    return _extract_raw_ocr_from_image(
        image,
        lang,
        preprocess_profile=preprocess_profile,
        allow_preprocess_fallback=allow_preprocess_fallback,
        text_recognition_model_name=text_recognition_model_name,
    )


def extract_raw_ocr_from_image_path(
    image_path: Path,
    lang: str = "eng",
    *,
    preprocess_profile: str = _OCR_PREPROCESS_PROFILE_NONE,
    allow_preprocess_fallback: bool = False,
    text_recognition_model_name: str | None = None,
) -> object:
    try:
        with Image.open(image_path) as image:
            return _extract_raw_ocr_from_image(
                image,
                lang,
                preprocess_profile=preprocess_profile,
                allow_preprocess_fallback=allow_preprocess_fallback,
                text_recognition_model_name=text_recognition_model_name,
            )
    except UnidentifiedImageError as exc:
        LOGGER.warning("Unable to decode image for OCR.", exc_info=exc)
        raise


def extract_raw_layout_from_data_url(
    data_url: str,
    lang: str = "eng",
) -> object:
    try:
        image_bytes = _decode_data_url(data_url)
    except (ValueError, base64.binascii.Error) as exc:
        LOGGER.warning("Invalid image data URL supplied for OCR.", exc_info=exc)
        raise
    return extract_raw_layout_from_image_bytes(image_bytes, lang)


def extract_raw_layout_from_image_bytes(
    image_bytes: bytes,
    lang: str = "eng",
) -> object:
    try:
        image = Image.open(io.BytesIO(image_bytes))
    except UnidentifiedImageError as exc:
        LOGGER.warning("Unable to decode image for OCR.", exc_info=exc)
        raise
    return _extract_raw_layout_from_image(image, lang)


def extract_raw_layout_from_image_path(
    image_path: Path,
    lang: str = "eng",
) -> object:
    try:
        with Image.open(image_path) as image:
            return _extract_raw_layout_from_image(image, lang)
    except UnidentifiedImageError as exc:
        LOGGER.warning("Unable to decode image for OCR.", exc_info=exc)
        raise


def extract_structured_ocr_from_data_url(
    data_url: str,
    lang: str = "eng",
    *,
    slide_id: str | None = None,
    slide_number: int | None = None,
    style_hint: dict[str, object] | None = None,
    include_layout: bool = True,
    preprocess_profile: str = _OCR_PREPROCESS_PROFILE_NONE,
    allow_preprocess_fallback: bool = False,
    step_callback: Callable[[str, dict[str, object]], None] | None = None,
) -> dict[str, object]:
    """Extract structured OCR (lines + layout blocks) from a data URL image."""
    try:
        image_bytes = _decode_data_url(data_url)
    except (ValueError, base64.binascii.Error) as exc:
        LOGGER.warning("Invalid image data URL supplied for OCR.", exc_info=exc)
        raise
    try:
        image = Image.open(io.BytesIO(image_bytes))
    except UnidentifiedImageError as exc:
        LOGGER.warning("Unable to decode image for OCR.", exc_info=exc)
        raise
    return _extract_structured_ocr_from_image(
        image,
        lang,
        slide_id=slide_id,
        slide_number=slide_number,
        style_hint=style_hint,
        include_layout=include_layout,
        preprocess_profile=preprocess_profile,
        allow_preprocess_fallback=allow_preprocess_fallback,
        step_callback=step_callback,
    )


def extract_structured_ocr_from_image_bytes(
    image_bytes: bytes,
    lang: str = "eng",
    *,
    slide_id: str | None = None,
    slide_number: int | None = None,
    style_hint: dict[str, object] | None = None,
    include_layout: bool = True,
    preprocess_profile: str = _OCR_PREPROCESS_PROFILE_NONE,
    allow_preprocess_fallback: bool = False,
    step_callback: Callable[[str, dict[str, object]], None] | None = None,
) -> dict[str, object]:
    """Extract structured OCR (lines + layout blocks) from raw image bytes."""
    try:
        image = Image.open(io.BytesIO(image_bytes))
    except UnidentifiedImageError as exc:
        LOGGER.warning("Unable to decode image for OCR.", exc_info=exc)
        raise
    return _extract_structured_ocr_from_image(
        image,
        lang,
        slide_id=slide_id,
        slide_number=slide_number,
        style_hint=style_hint,
        include_layout=include_layout,
        preprocess_profile=preprocess_profile,
        allow_preprocess_fallback=allow_preprocess_fallback,
        step_callback=step_callback,
    )


def extract_structured_ocr_from_image_path(
    image_path: Path,
    lang: str = "eng",
    *,
    slide_id: str | None = None,
    slide_number: int | None = None,
    style_hint: dict[str, object] | None = None,
    include_layout: bool = True,
    preprocess_profile: str = _OCR_PREPROCESS_PROFILE_NONE,
    allow_preprocess_fallback: bool = False,
    step_callback: Callable[[str, dict[str, object]], None] | None = None,
) -> dict[str, object]:
    """Extract structured OCR (lines + layout blocks) from an on-disk image."""
    try:
        with Image.open(image_path) as image:
            return _extract_structured_ocr_from_image(
                image,
                lang,
                slide_id=slide_id,
                slide_number=slide_number,
                style_hint=style_hint,
                include_layout=include_layout,
                preprocess_profile=preprocess_profile,
                allow_preprocess_fallback=allow_preprocess_fallback,
                step_callback=step_callback,
            )
    except UnidentifiedImageError as exc:
        LOGGER.warning("Unable to decode image for OCR.", exc_info=exc)
        raise


def extract_lines_from_data_url(
    data_url: str,
    lang: str = "eng",
    *,
    slide_id: str | None = None,
    slide_number: int | None = None,
    preprocess_profile: str = _OCR_PREPROCESS_PROFILE_NONE,
    allow_preprocess_fallback: bool = False,
) -> list[dict[str, object]]:
    """Extract OCR lines from a data URL-encoded image."""
    raw_result = extract_raw_ocr_from_data_url(
        data_url,
        lang,
        preprocess_profile=preprocess_profile,
        allow_preprocess_fallback=allow_preprocess_fallback,
    )
    return _extract_lines_from_raw_result(
        raw_result,
        slide_id=slide_id,
        slide_number=slide_number,
    )


def extract_lines_from_image_bytes(
    image_bytes: bytes,
    lang: str = "eng",
    *,
    slide_id: str | None = None,
    slide_number: int | None = None,
    preprocess_profile: str = _OCR_PREPROCESS_PROFILE_NONE,
    allow_preprocess_fallback: bool = False,
) -> list[dict[str, object]]:
    """Extract OCR lines from raw image bytes."""
    raw_result = extract_raw_ocr_from_image_bytes(
        image_bytes,
        lang,
        preprocess_profile=preprocess_profile,
        allow_preprocess_fallback=allow_preprocess_fallback,
    )
    return _extract_lines_from_raw_result(
        raw_result,
        slide_id=slide_id,
        slide_number=slide_number,
    )


def extract_lines_from_image_path(
    image_path: Path,
    lang: str = "eng",
    *,
    slide_id: str | None = None,
    slide_number: int | None = None,
    preprocess_profile: str = _OCR_PREPROCESS_PROFILE_NONE,
    allow_preprocess_fallback: bool = False,
) -> list[dict[str, object]]:
    """Extract OCR lines from an on-disk image."""
    raw_result = extract_raw_ocr_from_image_path(
        image_path,
        lang,
        preprocess_profile=preprocess_profile,
        allow_preprocess_fallback=allow_preprocess_fallback,
    )
    return _extract_lines_from_raw_result(
        raw_result,
        slide_id=slide_id,
        slide_number=slide_number,
    )


def extract_text_from_data_url(
    data_url: str,
    lang: str = "eng",
    *,
    preprocess_profile: str = _OCR_PREPROCESS_PROFILE_NONE,
    allow_preprocess_fallback: bool = False,
) -> str:
    raw_result = extract_raw_ocr_from_data_url(
        data_url,
        lang,
        preprocess_profile=preprocess_profile,
        allow_preprocess_fallback=allow_preprocess_fallback,
    )
    return extract_text_from_raw_ocr_result(raw_result)


def extract_text_from_image_bytes(
    image_bytes: bytes,
    lang: str = "eng",
    *,
    preprocess_profile: str = _OCR_PREPROCESS_PROFILE_NONE,
    allow_preprocess_fallback: bool = False,
) -> str:
    raw_result = extract_raw_ocr_from_image_bytes(
        image_bytes,
        lang,
        preprocess_profile=preprocess_profile,
        allow_preprocess_fallback=allow_preprocess_fallback,
    )
    return extract_text_from_raw_ocr_result(raw_result)


def extract_text_from_image_path(
    image_path: Path,
    lang: str = "eng",
    *,
    preprocess_profile: str = _OCR_PREPROCESS_PROFILE_NONE,
    allow_preprocess_fallback: bool = False,
) -> str:
    raw_result = extract_raw_ocr_from_image_path(
        image_path,
        lang,
        preprocess_profile=preprocess_profile,
        allow_preprocess_fallback=allow_preprocess_fallback,
    )
    return extract_text_from_raw_ocr_result(raw_result)
