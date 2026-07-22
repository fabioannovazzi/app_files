from __future__ import annotations

import base64
import io
import logging
import os
import re
import time
from datetime import UTC, datetime
from math import ceil, floor
from pathlib import Path
from statistics import median
from typing import Callable

import fitz  # type: ignore[import-not-found]
from bs4 import BeautifulSoup  # type: ignore[import]
from openai import OpenAIError
from PIL import Image, ImageOps

import modules.utilities.config as config_module
from modules.llm.batch_runner import run_step_json, run_step_text
from modules.llm.llm_call_wrapper import init_llm_wrapper
from modules.slides.ocr import (
    extract_lines_from_raw_ocr_result,
    extract_raw_ocr_from_image_bytes,
    extract_structured_ocr_from_image_bytes,
    extract_structured_ocr_from_image_path,
    extract_text_from_raw_ocr_result,
)
from modules.utilities.session_context import SessionContext
from src.slides.layout_semantics import (
    BULLET_BLOCK_TYPES,
    TEXT_BEARING_BLOCK_TYPES,
    default_render_mode_for_type,
    normalize_block_type,
    normalize_group_kind,
    normalize_list_level,
    normalize_optional_string,
    normalize_reading_order,
    normalize_render_mode,
)
from src.slides.layout_service import build_deck_layout_payload
from src.slides.models import Deck, Slide
from src.slides.notebooklm_style import load_notebooklm_style
from src.slides.ocr_cleanup import clean_ocr_items, clean_ocr_text
from src.slides.ocr_payload import normalize_ocr_payload

__all__ = [
    "OCR_STRATEGY_LAYOUT_GUIDED",
    "SlideOcrOpenAIError",
    "build_deck_ocr_payload",
    "build_filtered_deck_ocr_inputs",
    "ensure_deck_ocr_payload",
]

LOGGER = logging.getLogger(__name__)
OCR_STRATEGY_LAYOUT_GUIDED = "layout_guided_text_region_assignment_v7"
_OCR_LAYOUT_TEXT_BLOCK_TYPES = set(TEXT_BEARING_BLOCK_TYPES) | {"text", "list"}
_VISUAL_CORRECTION_MIN_CONFIDENCE = 0.9
_TABLE_MODEL_MIN_CONFIDENCE = 0.72
_TABLE_FALLBACK_MIN_CONFIDENCE = 0.6
_TABLE_STRUCTURE_BOUNDS_MIN_CONFIDENCE = 0.55
_BULLET_PREFIX_PATTERN = re.compile(r"^\s*(?:[-*•·▪◦]|\d+[.)]|[A-Za-z][.)])\s*")
_DEFINITION_PREFIX_PATTERN = re.compile(
    r"^\s*(?:"
    r"[-*•·▪◦]"
    r"|"
    r"\d+[.)]"
    r"|"
    r"[A-Za-z][.)]"
    r"|"
    r"[A-Za-z0-9][A-Za-z0-9+./-]{1,30}(?:\s*\([^)]+\))?\s*:"
    r")\s*"
)
_TABLE_NUMERIC_TEXT_RE = re.compile(r"^[\s€$£¥()%+\-–—.,:/0-9]+$")
_SLIDE_PADDLE_TEXT_RECOGNITION_MODEL = os.getenv(
    "SLIDES_PADDLE_TEXT_RECOGNITION_MODEL",
    "PP-OCRv5_server_rec",
).strip()
_SLIDE_PADDLE_TEXT_RECOGNITION_MODEL_LANGS = {
    "de",
    "deu",
    "en",
    "eng",
    "fr",
    "fra",
    "it",
    "ita",
    "es",
    "spa",
}
try:
    _SLIDES_PDF_OCR_RASTER_SCALE = max(
        1.0, float(os.getenv("SLIDES_PDF_IMPORT_RASTER_SCALE", "2"))
    )
except ValueError:
    _SLIDES_PDF_OCR_RASTER_SCALE = 2.0


def _emit_ocr_event(
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
        LOGGER.warning("Ignoring OCR event callback error: %s", exc)


def _build_ocr_style_hint(prompt_style: str) -> dict[str, object]:
    style = load_notebooklm_style(prompt_style)
    title_size = float(style.title_size_pt)
    body_size = float(style.body_size_pt)
    ratio = (title_size / body_size) if body_size > 0 else None
    return {
        "prompt_style": prompt_style,
        "font_family_primary": style.font_family_primary,
        "font_family_fallback": style.font_family_fallback,
        "title_size_pt": title_size,
        "body_size_pt": body_size,
        "title_to_body_ratio": ratio,
    }


def _build_local_llm_wrapper() -> object:
    session = SessionContext.from_state({})
    init_llm_wrapper("", session=session)
    return session.state["llm_wrapper"]


class SlideOcrOpenAIError(RuntimeError):
    """Raised when OpenAI-backed OCR enrichment fails."""


def _raise_openai_ocr_error(phase: str, exc: BaseException) -> None:
    raise SlideOcrOpenAIError(f"OpenAI call failed during {phase}.") from exc


def _resolve_ocr_language_label(lang: str) -> str:
    code = str(lang or "").strip().lower()
    if code in {"it", "ita"}:
        return "Italian"
    if code in {"en", "eng"}:
        return "English"
    if code in {"fr", "fra", "fre"}:
        return "French"
    if code in {"de", "deu", "ger"}:
        return "German"
    if code in {"es", "spa"}:
        return "Spanish"
    return code or "the original language"


def _slide_text_recognition_model_name(lang: str) -> str | None:
    code = str(lang or "").strip().lower()
    if code not in _SLIDE_PADDLE_TEXT_RECOGNITION_MODEL_LANGS:
        return None
    return _SLIDE_PADDLE_TEXT_RECOGNITION_MODEL or None


def _build_block_correction_prompt(
    *,
    lang: str,
    block_type: str,
    text: str,
) -> str:
    language_label = _resolve_ocr_language_label(lang)
    return (
        f"Source language: {language_label}\n"
        f"Block type: {block_type}\n\n"
        "Correct only obvious OCR mistakes in the text below.\n"
        "Rules:\n"
        "- Keep the same language.\n"
        "- Do not translate, summarize, explain, or paraphrase.\n"
        "- Preserve meaning, numbers, units, punctuation, and ordering.\n"
        "- If the text already looks correct, return it unchanged.\n"
        "- Return corrected text only.\n\n"
        "OCR text:\n"
        f"{text}"
    )


def _normalize_audit_status(value: object) -> str:
    normalized = str(value or "").strip().lower()
    if normalized == "suspicious":
        return "suspicious"
    return "ok"


def _normalize_visual_status(value: object) -> str:
    normalized = str(value or "").strip().lower()
    if normalized == "corrected":
        return "corrected"
    if normalized == "uncertain":
        return "uncertain"
    return "ok"


def _build_block_residual_audit_prompt(
    *,
    lang: str,
    block_type: str,
    text: str,
) -> str:
    language_label = _resolve_ocr_language_label(lang)
    return (
        f"Source language: {language_label}\n"
        f"Block type: {block_type}\n\n"
        "Decide whether the OCR text below still looks suspicious.\n"
        "Return JSON with keys: status, reason, suggested_text.\n"
        "Rules:\n"
        "- status must be either ok or suspicious.\n"
        "- Mark suspicious only for likely OCR mistakes, merged words, broken wording, casing errors, or punctuation artifacts.\n"
        "- Keep suggested_text empty unless a small, specific correction is obvious from the text alone.\n"
        "- Do not translate, summarize, or rewrite stylistically.\n\n"
        "OCR text:\n"
        f"{text}"
    )


def _build_block_visual_correction_prompt(
    *,
    lang: str,
    block_type: str,
    text: str,
    audit_reason: str,
    audit_suggested_text: str,
) -> str:
    language_label = _resolve_ocr_language_label(lang)
    prompt = (
        f"Source language: {language_label}\n"
        f"Block type: {block_type}\n\n"
        "Inspect the image crop and decide whether the current OCR text should be corrected.\n"
        "Return JSON with keys: status, reason, corrected_text, confidence.\n"
        "Rules:\n"
        "- status must be one of: ok, corrected, uncertain.\n"
        "- confidence must be a number between 0 and 1.\n"
        "- Correct only if the image clearly supports the correction.\n"
        "- Do not translate, summarize, or rewrite stylistically.\n"
        "- Preserve meaning, numbers, units, punctuation, and ordering unless the image clearly shows a different value.\n"
        "- If you are not sure, return status=uncertain and leave corrected_text empty.\n\n"
        "Current OCR text:\n"
        f"{text}\n\n"
    )
    cleaned_reason = clean_ocr_text(audit_reason)
    if cleaned_reason:
        prompt += f"Residual audit reason:\n{cleaned_reason}\n\n"
    cleaned_suggestion = clean_ocr_text(audit_suggested_text)
    if cleaned_suggestion:
        prompt += f"Text-only suggested correction:\n{cleaned_suggestion}\n\n"
    return prompt.strip()


def _numeric_signature(text: str) -> list[tuple[object, object]]:
    from src.slides.numeric_tokens import parse_numeric_tokens

    tokens = parse_numeric_tokens(text)
    return [(token.value, token.unit) for token in tokens]


def _compact_ocr_equivalence_key(text: str) -> str:
    return re.sub(r"[\W_]+", "", clean_ocr_text(text).casefold())


def _llm_correction_is_acceptable(original_text: str, corrected_text: str) -> bool:
    original = clean_ocr_text(original_text)
    corrected = clean_ocr_text(corrected_text)
    if not corrected or corrected == original:
        return False
    if _numeric_signature(original) != _numeric_signature(corrected):
        return False
    if _compact_ocr_equivalence_key(original) == _compact_ocr_equivalence_key(
        corrected
    ):
        return True
    original_words = original.split()
    corrected_words = corrected.split()
    if original_words:
        corrected_word_count = len(corrected_words)
        minimum_words = max(1, floor(len(original_words) * 0.6))
        maximum_words = max(1, ceil(len(original_words) * 1.6))
        if corrected_word_count < minimum_words or corrected_word_count > maximum_words:
            return False
    original_length = len(original)
    if original_length:
        minimum_length = max(1, floor(original_length * 0.6))
        maximum_length = max(1, ceil(original_length * 1.6))
        corrected_length = len(corrected)
        if corrected_length < minimum_length or corrected_length > maximum_length:
            return False
    return True


def _collect_block_texts_for_ocr_text(blocks: list[dict[str, object]]) -> list[str]:
    return [
        clean_ocr_text(str(block.get("text") or ""))
        for block in blocks
        if normalize_block_type(block.get("type")) in _OCR_LAYOUT_TEXT_BLOCK_TYPES
        and clean_ocr_text(str(block.get("text") or ""))
    ]


def _derive_title_text_from_blocks(blocks: list[dict[str, object]]) -> str:
    for block in blocks:
        if normalize_block_type(block.get("type")) != "title":
            continue
        text = clean_ocr_text(str(block.get("text") or ""))
        if text:
            return text
    return ""


def _derive_bullet_texts_from_blocks(blocks: list[dict[str, object]]) -> list[str]:
    bullet_texts: list[str] = []
    for block in blocks:
        if normalize_block_type(block.get("type")) not in BULLET_BLOCK_TYPES:
            continue
        items = block.get("items") if isinstance(block.get("items"), list) else []
        cleaned_items = clean_ocr_items(
            [str(item).strip() for item in items if str(item).strip()]
        )
        if cleaned_items:
            bullet_texts.extend(cleaned_items)
            continue
        text = clean_ocr_text(str(block.get("text") or ""))
        if text:
            bullet_texts.extend(
                _normalize_list_items_from_block(text, text.splitlines())
            )
    return clean_ocr_items(bullet_texts)


def _apply_llm_corrections_to_blocks(
    blocks: list[dict[str, object]],
    *,
    lang: str,
    llm_wrapper: object | None,
) -> int:
    if llm_wrapper is None:
        return 0
    candidates: list[tuple[dict[str, object], str, str]] = []
    for block in blocks:
        block_type = normalize_block_type(block.get("type"))
        if block_type not in _OCR_LAYOUT_TEXT_BLOCK_TYPES:
            continue
        block_text = clean_ocr_text(str(block.get("text") or ""))
        if not block_text:
            continue
        candidates.append((block, block_type, block_text))
    if not candidates:
        return 0

    naming_params = config_module.get_naming_params()
    query_step = naming_params["slideOcrSemanticQuery"]
    prompt_system = (
        "You are correcting OCR transcriptions from presentation slides. "
        "Return corrected text only."
    )
    prompts = [
        _build_block_correction_prompt(lang=lang, block_type=block_type, text=text)
        for _, block_type, text in candidates
    ]
    try:
        responses = run_step_text(llm_wrapper, query_step, prompt_system, prompts)
    except (OSError, RuntimeError, ValueError, TypeError, OpenAIError) as exc:
        _raise_openai_ocr_error("slide OCR semantic correction", exc)
    if len(responses) != len(candidates):
        LOGGER.warning(
            "Skipping slide OCR LLM correction because response count (%s) does not match candidates (%s).",
            len(responses),
            len(candidates),
        )
        return 0

    corrected_blocks = 0
    for (block, block_type, original_text), response in zip(candidates, responses):
        corrected_text = clean_ocr_text(str(response or ""))
        if not _llm_correction_is_acceptable(original_text, corrected_text):
            continue
        block["text"] = corrected_text
        if block_type in BULLET_BLOCK_TYPES:
            block["items"] = _normalize_list_items_from_block(
                corrected_text,
                corrected_text.splitlines(),
            )
        corrected_blocks += 1
    return corrected_blocks


def _apply_llm_residual_audit_to_blocks(
    blocks: list[dict[str, object]],
    *,
    lang: str,
    llm_wrapper: object | None,
) -> int:
    if llm_wrapper is None:
        return 0
    candidates: list[tuple[dict[str, object], str, str]] = []
    for block in blocks:
        block_type = normalize_block_type(block.get("type"))
        if block_type not in _OCR_LAYOUT_TEXT_BLOCK_TYPES:
            continue
        block_text = clean_ocr_text(str(block.get("text") or ""))
        if not block_text:
            continue
        candidates.append((block, block_type, block_text))
    if not candidates:
        return 0

    naming_params = config_module.get_naming_params()
    query_step = naming_params["slideOcrResidualAuditQuery"]
    prompt_system = (
        "You audit OCR transcriptions from presentation slides. "
        "Return JSON only with status, reason, and suggested_text."
    )
    prompts = [
        _build_block_residual_audit_prompt(lang=lang, block_type=block_type, text=text)
        for _, block_type, text in candidates
    ]
    try:
        responses = run_step_json(llm_wrapper, query_step, prompt_system, prompts)
    except (OSError, RuntimeError, ValueError, TypeError, OpenAIError) as exc:
        _raise_openai_ocr_error("slide OCR residual audit", exc)
    if len(responses) != len(candidates):
        LOGGER.warning(
            "Skipping slide OCR residual audit because response count (%s) does not match candidates (%s).",
            len(responses),
            len(candidates),
        )
        return 0

    audited_blocks = 0
    for (block, _block_type, _original_text), response in zip(candidates, responses):
        if not isinstance(response, dict):
            continue
        block["audit_status"] = _normalize_audit_status(response.get("status"))
        block["audit_reason"] = clean_ocr_text(str(response.get("reason") or ""))
        block["audit_suggested_text"] = clean_ocr_text(
            str(response.get("suggested_text") or "")
        )
        audited_blocks += 1
    return audited_blocks


def _image_to_data_url(image: Image.Image) -> str:
    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    image_b64 = base64.b64encode(buffer.getvalue()).decode("ascii")
    return f"data:image/png;base64,{image_b64}"


def _build_block_visual_crop(
    image: Image.Image,
    *,
    block: dict[str, object],
) -> Image.Image | None:
    crop_with_bbox = _build_block_visual_crop_with_bbox(image, block=block)
    if crop_with_bbox is None:
        return None
    return crop_with_bbox[0]


def _build_block_visual_crop_with_bbox(
    image: Image.Image,
    *,
    block: dict[str, object],
) -> tuple[Image.Image, tuple[int, int, int, int]] | None:
    block_type = normalize_block_type(block.get("type"))
    crop_box = _bbox_to_crop_box(block.get("bbox"), image_size=image.size)
    expanded_crop = _expand_crop_box(
        crop_box,
        image_size=image.size,
        block_type=block_type,
    )
    if expanded_crop is None:
        return None
    cropped = image.crop(expanded_crop)
    trimmed, offset_x, offset_y = _trim_near_white_margins(cropped, padding=6)
    crop_left = int(expanded_crop[0] + offset_x)
    crop_top = int(expanded_crop[1] + offset_y)
    crop_right = int(crop_left + trimmed.width)
    crop_bottom = int(crop_top + trimmed.height)
    return trimmed, (crop_left, crop_top, crop_right, crop_bottom)


def _coerce_confidence(value: object) -> float | None:
    if isinstance(value, (int, float)):
        confidence = float(value)
    else:
        try:
            confidence = float(str(value).strip())
        except (TypeError, ValueError):
            return None
    if confidence < 0.0:
        return 0.0
    if confidence > 1.0:
        return 1.0
    return confidence


def _clamp_unit_interval(value: object) -> float | None:
    try:
        normalized = float(value)
    except (TypeError, ValueError):
        return None
    if normalized < 0.0:
        return 0.0
    if normalized > 1.0:
        return 1.0
    return normalized


def _apply_vlm_corrections_to_blocks(
    blocks: list[dict[str, object]],
    *,
    lang: str,
    llm_wrapper: object | None,
    slide_image: Image.Image | None,
) -> int:
    if llm_wrapper is None or slide_image is None:
        return 0
    candidates: list[tuple[dict[str, object], str, str, Image.Image]] = []
    for block in blocks:
        block_type = normalize_block_type(block.get("type"))
        if block_type not in _OCR_LAYOUT_TEXT_BLOCK_TYPES:
            continue
        if str(block.get("audit_status") or "").strip().lower() != "suspicious":
            continue
        block_text = clean_ocr_text(str(block.get("text") or ""))
        if not block_text:
            continue
        crop = _build_block_visual_crop(slide_image, block=block)
        if crop is None:
            continue
        candidates.append((block, block_type, block_text, crop))
    if not candidates:
        return 0

    naming_params = config_module.get_naming_params()
    query_step = naming_params["slideOcrVisualCorrectionQuery"]
    prompt_system = (
        "You verify OCR transcriptions from presentation slide image crops. "
        "Return JSON only with status, reason, corrected_text, and confidence."
    )
    prompts: list[dict[str, object]] = []
    for block, block_type, text, crop in candidates:
        prompts.append(
            {
                "user_content": [
                    {
                        "type": "input_text",
                        "text": _build_block_visual_correction_prompt(
                            lang=lang,
                            block_type=block_type,
                            text=text,
                            audit_reason=str(block.get("audit_reason") or ""),
                            audit_suggested_text=str(
                                block.get("audit_suggested_text") or ""
                            ),
                        ),
                    },
                    {
                        "type": "input_image",
                        "image_url": _image_to_data_url(crop),
                    },
                ]
            }
        )

    try:
        responses = run_step_json(llm_wrapper, query_step, prompt_system, prompts)
    except (OSError, RuntimeError, ValueError, TypeError, OpenAIError) as exc:
        _raise_openai_ocr_error("slide OCR visual correction", exc)
    if len(responses) != len(candidates):
        LOGGER.warning(
            "Skipping slide OCR visual correction because response count (%s) does not match candidates (%s).",
            len(responses),
            len(candidates),
        )
        return 0

    corrected_blocks = 0
    for (block, block_type, original_text, _crop), response in zip(
        candidates, responses
    ):
        if not isinstance(response, dict):
            continue
        visual_status = _normalize_visual_status(response.get("status"))
        visual_reason = clean_ocr_text(str(response.get("reason") or ""))
        visual_suggested_text = clean_ocr_text(
            str(response.get("corrected_text") or "")
        )
        visual_confidence = _coerce_confidence(response.get("confidence"))
        block["visual_status"] = visual_status
        block["visual_reason"] = visual_reason
        if visual_suggested_text:
            block["visual_suggested_text"] = visual_suggested_text
        if visual_confidence is not None:
            block["visual_confidence"] = visual_confidence

        if visual_status != "corrected":
            continue
        if (
            visual_confidence is None
            or visual_confidence < _VISUAL_CORRECTION_MIN_CONFIDENCE
        ):
            continue
        if not _llm_correction_is_acceptable(original_text, visual_suggested_text):
            continue
        block["text"] = visual_suggested_text
        if block_type in BULLET_BLOCK_TYPES:
            block["items"] = _normalize_list_items_from_block(
                visual_suggested_text,
                visual_suggested_text.splitlines(),
            )
        corrected_blocks += 1
    return corrected_blocks


def _is_numeric_like_table_text(text: str) -> bool:
    normalized = clean_ocr_text(text)
    if not normalized:
        return False
    return _TABLE_NUMERIC_TEXT_RE.fullmatch(normalized) is not None


def _table_alignment_for_text(*, text: str, is_header: bool) -> str:
    if is_header:
        return "center"
    if _is_numeric_like_table_text(text):
        return "right"
    return "left"


def _normalize_table_column_widths(
    widths: list[float], *, column_count: int
) -> list[float]:
    positive_widths = [width for width in widths if width > 0.0]
    if len(positive_widths) != column_count:
        return [1.0 / float(column_count)] * column_count
    total = sum(positive_widths)
    if total <= 0.0:
        return [1.0 / float(column_count)] * column_count
    return [width / total for width in positive_widths]


def _table_row_numeric_ratio(texts: list[str]) -> float:
    nonempty = [text for text in texts if clean_ocr_text(text)]
    if not nonempty:
        return 0.0
    numeric_count = sum(1 for text in nonempty if _is_numeric_like_table_text(text))
    return float(numeric_count) / float(len(nonempty))


def _table_header_row_count(rows: list[list[str]]) -> int:
    if len(rows) < 2:
        return 0
    first_row = rows[0]
    if not any(clean_ocr_text(text) for text in first_row):
        return 0
    first_ratio = _table_row_numeric_ratio(first_row)
    later_ratios = [_table_row_numeric_ratio(row) for row in rows[1:]]
    if any(ratio > first_ratio for ratio in later_ratios):
        return 1
    return 1 if first_ratio < 0.5 else 0


def _normalize_table_grid(
    rows: list[list[str]],
    *,
    header_rows: int,
    column_widths: list[float],
    confidence: float,
    source: str,
) -> dict[str, object] | None:
    if not rows:
        return None
    column_count = max((len(row) for row in rows), default=0)
    row_count = len(rows)
    if row_count < 1 or column_count < 1:
        return None
    normalized_rows: list[dict[str, object]] = []
    for row_index, row in enumerate(rows):
        normalized_cells: list[dict[str, object]] = []
        padded_row = list(row) + [""] * max(0, column_count - len(row))
        for cell_text in padded_row[:column_count]:
            cleaned = clean_ocr_text(cell_text)
            is_header = row_index < header_rows
            normalized_cells.append(
                {
                    "text": cleaned,
                    "row_span": 1,
                    "col_span": 1,
                    "is_header": is_header,
                    "align": _table_alignment_for_text(
                        text=cleaned,
                        is_header=is_header,
                    ),
                }
            )
        normalized_rows.append({"cells": normalized_cells})
    return {
        "source": source,
        "confidence": max(0.0, min(float(confidence), 1.0)),
        "row_count": row_count,
        "column_count": column_count,
        "header_rows": max(0, min(header_rows, row_count)),
        "column_widths": _normalize_table_column_widths(
            column_widths,
            column_count=column_count,
        ),
        "has_merged_cells": False,
        "rows": normalized_rows,
    }


def _table_model_confidence_value(table_model: dict[str, object] | None) -> float:
    if not isinstance(table_model, dict):
        return 0.0
    confidence = _coerce_table_confidence(table_model.get("confidence"))
    return confidence if confidence is not None else 0.0


def _table_model_row_texts(table_model: dict[str, object] | None) -> list[list[str]]:
    if not isinstance(table_model, dict):
        return []
    raw_rows = table_model.get("rows")
    if not isinstance(raw_rows, list):
        return []
    rows: list[list[str]] = []
    for raw_row in raw_rows:
        if not isinstance(raw_row, dict):
            continue
        raw_cells = raw_row.get("cells")
        if not isinstance(raw_cells, list):
            continue
        rows.append(
            [
                clean_ocr_text(str(cell.get("text") or ""))
                for cell in raw_cells
                if isinstance(cell, dict)
            ]
        )
    return rows


def _table_model_is_structurally_suspicious(
    table_model: dict[str, object] | None,
) -> bool:
    if not isinstance(table_model, dict):
        return True
    rows = _table_model_row_texts(table_model)
    if not rows:
        return True
    column_count = max((len(row) for row in rows), default=0)
    if column_count < 1:
        return True

    nonempty_counts = [sum(1 for text in row if clean_ocr_text(text)) for row in rows]
    if rows and column_count >= 4:
        first_nonempty = nonempty_counts[0]
        first_row_texts = [text for text in rows[0] if clean_ocr_text(text)]
        if (
            len(rows) >= 2
            and first_nonempty <= max(1, column_count // 3)
            and nonempty_counts[1] >= max(2, column_count - 1)
            and any(len(text) >= 24 for text in first_row_texts)
        ):
            return True

    header_rows = 0
    try:
        header_rows = int(
            table_model.get("header_rows") or table_model.get("headerRows") or 0
        )
    except (TypeError, ValueError):
        header_rows = 0
    if header_rows >= 1 and rows:
        first_header = rows[0]
        header_fragments = 0
        for text in first_header:
            cleaned = clean_ocr_text(text)
            if not cleaned:
                continue
            if cleaned.endswith(",") or cleaned.startswith(("(", ")", "≤", "≥", "%")):
                header_fragments += 1
        if column_count >= 5 and header_fragments >= 2:
            return True

    return False


def _normalize_table_row_values(raw_row: object) -> list[str] | None:
    if not isinstance(raw_row, list):
        return None
    normalized: list[str] = []
    for cell in raw_row:
        if isinstance(cell, (str, int, float)):
            normalized.append(clean_ocr_text(str(cell)))
        elif cell is None:
            normalized.append("")
    return normalized


def _build_table_model_from_grid_response(
    response: dict[str, object],
    *,
    source: str,
) -> dict[str, object] | None:
    status = str(response.get("status") or "").strip().lower()
    if status not in {"ok", "uncertain"}:
        return None
    confidence = _coerce_table_confidence(response.get("confidence"))
    if confidence is None or confidence < _TABLE_FALLBACK_MIN_CONFIDENCE:
        return None
    raw_header = response.get("header")
    if not isinstance(raw_header, list):
        raw_header = response.get("headers")
    header = _normalize_table_row_values(raw_header) or []
    if not any(clean_ocr_text(item) for item in header):
        header = []
    raw_rows = response.get("rows") if isinstance(response.get("rows"), list) else []
    rows = [
        row
        for row in (
            _normalize_table_row_values(raw_row)
            for raw_row in raw_rows
            if isinstance(raw_row, list)
        )
        if row is not None and any(clean_ocr_text(cell) for cell in row)
    ]
    grid_rows = ([header] if header else []) + rows
    if not grid_rows:
        return None
    column_count = max((len(row) for row in grid_rows), default=0)
    if column_count < 1:
        return None
    return _normalize_table_grid(
        grid_rows,
        header_rows=1 if header else 0,
        column_widths=[1.0 / float(column_count)] * column_count,
        confidence=confidence,
        source=source,
    )


def _collect_table_line_entries(
    block: dict[str, object],
    lines: list[dict[str, object]],
    *,
    image_size: tuple[int, int] | None,
) -> list[dict[str, object]]:
    block_bbox = _normalize_layout_bbox(block.get("bbox"))
    if block_bbox is None:
        return []
    entries: list[dict[str, object]] = []
    for line in lines:
        text = clean_ocr_text(str(line.get("text") or ""))
        if not text:
            continue
        line_bbox = _normalize_layout_bbox(line.get("bbox"))
        if line_bbox is None:
            continue
        line_area = _bbox_area(line_bbox)
        overlap_ratio = (
            _bbox_intersection_area(line_bbox, block_bbox) / line_area
            if line_area > 0
            else 0.0
        )
        center = _bbox_center(line_bbox)
        if center is None:
            continue
        if not (
            _bbox_contains_point(block_bbox, x=center[0], y=center[1])
            or overlap_ratio >= 0.45
        ):
            continue
        entries.append(
            {
                "text": text,
                "bbox": line_bbox,
                "x": float(line_bbox["x"]),
                "y": float(line_bbox["y"]),
                "w": float(line_bbox["w"]),
                "h": float(line_bbox["h"]),
                "center_x": float(line_bbox["x"]) + (float(line_bbox["w"]) / 2.0),
                "center_y": float(line_bbox["y"]) + (float(line_bbox["h"]) / 2.0),
            }
        )
    return sorted(entries, key=lambda entry: (entry["center_y"], entry["x"]))


def _cluster_table_rows(
    entries: list[dict[str, object]],
) -> list[list[dict[str, object]]]:
    if not entries:
        return []
    median_height = median(entry["h"] for entry in entries)
    row_threshold = max(10.0, float(median_height) * 0.7)
    rows: list[list[dict[str, object]]] = []
    current_row: list[dict[str, object]] = []
    current_center = 0.0
    current_bottom = 0.0
    for entry in entries:
        if not current_row:
            current_row = [entry]
            current_center = entry["center_y"]
            current_bottom = entry["y"] + entry["h"]
            continue
        vertical_gap = entry["center_y"] - current_center
        if vertical_gap <= row_threshold or entry["y"] <= current_bottom + (
            median_height * 0.15
        ):
            current_row.append(entry)
            current_center = sum(item["center_y"] for item in current_row) / float(
                len(current_row)
            )
            current_bottom = max(current_bottom, entry["y"] + entry["h"])
            continue
        rows.append(sorted(current_row, key=lambda item: item["x"]))
        current_row = [entry]
        current_center = entry["center_y"]
        current_bottom = entry["y"] + entry["h"]
    if current_row:
        rows.append(sorted(current_row, key=lambda item: item["x"]))
    return rows


def _reference_table_row(
    rows: list[list[dict[str, object]]],
) -> list[dict[str, object]] | None:
    if not rows:
        return None
    best_index = max(
        range(len(rows)),
        key=lambda index: (len(rows[index]), -index),
    )
    return rows[best_index]


def _assign_table_row_to_columns(
    row: list[dict[str, object]],
    *,
    column_centers: list[float],
) -> tuple[list[str], int]:
    column_count = len(column_centers)
    assigned = [""] * column_count
    occupied: set[int] = set()
    collisions = 0
    for entry in row:
        ranked = sorted(
            range(column_count),
            key=lambda index: abs(entry["center_x"] - column_centers[index]),
        )
        target_index = next(
            (index for index in ranked if index not in occupied),
            ranked[0] if ranked else None,
        )
        if target_index is None:
            continue
        if target_index in occupied:
            collisions += 1
            continue
        occupied.add(target_index)
        assigned[target_index] = entry["text"]
    return assigned, collisions


def _build_deterministic_table_model(
    block: dict[str, object],
    lines: list[dict[str, object]],
    *,
    image_size: tuple[int, int] | None,
) -> dict[str, object] | None:
    entries = _collect_table_line_entries(block, lines, image_size=image_size)
    if not entries:
        return None
    rows = _cluster_table_rows(entries)
    if not rows:
        return None
    reference_row = _reference_table_row(rows)
    if reference_row is None:
        return None
    column_count = len(reference_row)
    row_count = len(rows)
    if column_count < 2 and row_count < 2:
        return None
    column_centers = [entry["center_x"] for entry in reference_row]
    column_widths = _normalize_table_column_widths(
        [max(entry["w"], 1.0) for entry in reference_row],
        column_count=column_count,
    )
    grid_rows: list[list[str]] = []
    total_collisions = 0
    for row in rows:
        assigned, collisions = _assign_table_row_to_columns(
            row,
            column_centers=column_centers,
        )
        grid_rows.append(assigned)
        total_collisions += collisions
    header_rows = _table_header_row_count(grid_rows)
    grid_fill = sum(
        1 for row in grid_rows for text in row if clean_ocr_text(text)
    ) / float(max(1, row_count * column_count))
    row_consistency = sum(min(len(row), column_count) for row in rows) / float(
        max(1, row_count * column_count)
    )
    confidence = min(
        0.95,
        0.42
        + (0.18 if row_count >= 2 else 0.0)
        + (0.18 if column_count >= 2 else 0.0)
        + (0.12 * grid_fill)
        + (0.1 * row_consistency)
        - (0.06 * total_collisions),
    )
    return _normalize_table_grid(
        grid_rows,
        header_rows=header_rows,
        column_widths=column_widths,
        confidence=confidence,
        source="deterministic_simple",
    )


def _build_table_fallback_prompt(
    *,
    lang: str,
    extracted_text: str,
) -> str:
    language_label = _resolve_ocr_language_label(lang)
    return (
        f"Source language: {language_label}\n\n"
        "Read the simple table in the slide crop and return JSON only.\n"
        "Use keys: status, reason, confidence, header, rows.\n"
        "Rules:\n"
        "- status must be ok or uncertain.\n"
        "- confidence must be between 0 and 1.\n"
        "- header must be a list of strings. Use an empty list if there is no clear header row.\n"
        "- rows must be a list of row arrays.\n"
        "- Preserve wording, numbers, units, and ordering.\n"
        "- Do not add commentary, markdown, or extra keys.\n\n"
        "Current extracted text:\n"
        f"{extracted_text}"
    )


def _coerce_table_confidence(value: object) -> float | None:
    return _coerce_confidence(value)


def _build_table_model_from_fallback_response(
    response: dict[str, object],
) -> dict[str, object] | None:
    return _build_table_model_from_grid_response(response, source="vlm_simple")


def _build_table_structure_prompt(
    *,
    lang: str,
    extracted_text: str,
) -> str:
    language_label = _resolve_ocr_language_label(lang)
    return (
        f"Source language: {language_label}\n\n"
        "Inspect the image crop and identify the actual table inside it.\n"
        "Return JSON only with keys: status, reason, confidence, table_bounds, header, rows.\n"
        "Rules:\n"
        "- status must be ok or uncertain.\n"
        "- confidence must be between 0 and 1.\n"
        "- table_bounds must be an object with normalized x, y, w, h values between 0 and 1, relative to the provided crop.\n"
        "- table_bounds must tightly cover only the table itself and exclude surrounding paragraph text, captions, and notes.\n"
        "- header must be a list of column header strings. Use an empty list if there is no clear single header row.\n"
        "- rows must be a list of row arrays in left-to-right order.\n"
        "- Keep wrapped text inside the same cell; do not split one header across multiple columns.\n"
        "- Preserve wording, numbers, units, punctuation, and ordering.\n"
        "- Use empty strings for blank cells when needed.\n"
        "- If the table bounds are clear but transcription is not, still return table_bounds and leave header/rows empty.\n"
        "- Do not add commentary, markdown, or extra keys.\n\n"
        "Current extracted text:\n"
        f"{extracted_text}"
    )


def _normalize_relative_table_bbox(raw_bbox: object) -> dict[str, float] | None:
    if not isinstance(raw_bbox, dict):
        return None
    x = _clamp_unit_interval(raw_bbox.get("x"))
    y = _clamp_unit_interval(raw_bbox.get("y"))
    w = _clamp_unit_interval(raw_bbox.get("w"))
    h = _clamp_unit_interval(raw_bbox.get("h"))
    if None not in {x, y, w, h}:
        assert x is not None and y is not None and w is not None and h is not None
        if w <= 0.0 or h <= 0.0:
            return None
        return {"x": x, "y": y, "w": w, "h": h}
    left = _clamp_unit_interval(raw_bbox.get("left"))
    top = _clamp_unit_interval(raw_bbox.get("top"))
    right = _clamp_unit_interval(raw_bbox.get("right"))
    bottom = _clamp_unit_interval(raw_bbox.get("bottom"))
    if None in {left, top, right, bottom}:
        return None
    assert (
        left is not None
        and top is not None
        and right is not None
        and bottom is not None
    )
    if right <= left or bottom <= top:
        return None
    return {"x": left, "y": top, "w": right - left, "h": bottom - top}


def _relative_table_bbox_to_absolute(
    relative_bbox: dict[str, float] | None,
    *,
    crop_box: tuple[int, int, int, int],
) -> dict[str, float] | None:
    if relative_bbox is None:
        return None
    crop_left, crop_top, crop_right, crop_bottom = crop_box
    crop_width = float(max(1, crop_right - crop_left))
    crop_height = float(max(1, crop_bottom - crop_top))
    absolute = {
        "x": float(crop_left) + (relative_bbox["x"] * crop_width),
        "y": float(crop_top) + (relative_bbox["y"] * crop_height),
        "w": relative_bbox["w"] * crop_width,
        "h": relative_bbox["h"] * crop_height,
    }
    return _normalize_layout_bbox(absolute)


def _query_table_structure_signals(
    table_blocks: list[dict[str, object]],
    *,
    lang: str,
    llm_wrapper: object | None,
    slide_image: Image.Image | None,
) -> dict[str, dict[str, object]]:
    if llm_wrapper is None or slide_image is None:
        return {}
    candidates: list[tuple[str, tuple[int, int, int, int]]] = []
    prompts: list[dict[str, object]] = []
    for block in table_blocks:
        block_id = str(block.get("block_id") or block.get("id") or "").strip()
        if not block_id:
            continue
        crop_with_bbox = _build_block_visual_crop_with_bbox(slide_image, block=block)
        if crop_with_bbox is None:
            continue
        crop, crop_box = crop_with_bbox
        extracted_text = clean_ocr_text(str(block.get("text") or ""))
        candidates.append((block_id, crop_box))
        prompts.append(
            {
                "user_content": [
                    {
                        "type": "input_text",
                        "text": _build_table_structure_prompt(
                            lang=lang,
                            extracted_text=extracted_text,
                        ),
                    },
                    {
                        "type": "input_image",
                        "image_url": _image_to_data_url(crop),
                    },
                ]
            }
        )
    if not prompts:
        return {}

    naming_params = config_module.get_naming_params()
    query_step = naming_params["readImageTableStructureQuery"]
    prompt_system = (
        "You identify and transcribe presentation tables from image crops. "
        "Return JSON only with status, reason, confidence, table_bounds, header, and rows."
    )
    try:
        responses = run_step_json(llm_wrapper, query_step, prompt_system, prompts)
    except (OSError, RuntimeError, ValueError, TypeError, OpenAIError) as exc:
        _raise_openai_ocr_error("table structure understanding", exc)
    if len(responses) != len(candidates):
        LOGGER.warning(
            "Skipping table structure understanding because response count (%s) does not match candidates (%s).",
            len(responses),
            len(candidates),
        )
        return {}

    signals: dict[str, dict[str, object]] = {}
    for (block_id, crop_box), response in zip(candidates, responses):
        if not isinstance(response, dict):
            continue
        confidence = _coerce_table_confidence(response.get("confidence"))
        if confidence is None:
            confidence = 0.0
        relative_bbox = _normalize_relative_table_bbox(
            response.get("table_bounds")
            or response.get("tableBounds")
            or response.get("bounds")
        )
        absolute_bbox = (
            _relative_table_bbox_to_absolute(relative_bbox, crop_box=crop_box)
            if confidence >= _TABLE_STRUCTURE_BOUNDS_MIN_CONFIDENCE
            else None
        )
        structured_model = _build_table_model_from_grid_response(
            response,
            source="vlm_structured",
        )
        signals[block_id] = {
            "confidence": confidence,
            "reason": clean_ocr_text(str(response.get("reason") or "")),
            "bbox": absolute_bbox,
            "table_model": structured_model,
        }
    return signals


def _build_fallback_table_model(
    block: dict[str, object],
    *,
    lang: str,
    llm_wrapper: object | None,
    slide_image: Image.Image | None,
    extracted_text: str,
) -> dict[str, object] | None:
    if llm_wrapper is None or slide_image is None:
        return None
    crop = _build_block_visual_crop(slide_image, block=block)
    if crop is None:
        return None
    naming_params = config_module.get_naming_params()
    query_step = naming_params["readImageTableQuery"]
    prompt_system = (
        "You read simple presentation tables from image crops. "
        "Return JSON only with status, reason, confidence, header, and rows."
    )
    prompts = [
        {
            "user_content": [
                {
                    "type": "input_text",
                    "text": _build_table_fallback_prompt(
                        lang=lang,
                        extracted_text=extracted_text,
                    ),
                },
                {
                    "type": "input_image",
                    "image_url": _image_to_data_url(crop),
                },
            ]
        }
    ]
    try:
        responses = run_step_json(llm_wrapper, query_step, prompt_system, prompts)
    except (OSError, RuntimeError, ValueError, TypeError, OpenAIError) as exc:
        _raise_openai_ocr_error("table OCR fallback", exc)
    if len(responses) != 1 or not isinstance(responses[0], dict):
        return None
    return _build_table_model_from_fallback_response(responses[0])


def _select_best_table_model(
    *candidates: dict[str, object] | None,
) -> dict[str, object] | None:
    valid_candidates = [
        candidate for candidate in candidates if isinstance(candidate, dict)
    ]
    if not valid_candidates:
        return None

    structured_candidates = [
        candidate
        for candidate in valid_candidates
        if clean_ocr_text(str(candidate.get("source") or "")) == "vlm_structured"
        and not _table_model_is_structurally_suspicious(candidate)
    ]
    if structured_candidates:
        return max(structured_candidates, key=_table_model_confidence_value)

    non_suspicious = [
        candidate
        for candidate in valid_candidates
        if not _table_model_is_structurally_suspicious(candidate)
    ]
    if non_suspicious:
        return max(non_suspicious, key=_table_model_confidence_value)
    return None


def _apply_table_models_to_blocks(
    blocks: list[dict[str, object]],
    *,
    lines: list[dict[str, object]],
    lang: str,
    llm_wrapper: object | None,
    slide_image_source: Image.Image | Path | None,
) -> int:
    table_blocks = [
        block for block in blocks if normalize_block_type(block.get("type")) == "table"
    ]
    if not table_blocks:
        return 0

    image_size: tuple[int, int] | None = None
    slide_image: Image.Image | None = None
    if isinstance(slide_image_source, Path):
        try:
            with Image.open(slide_image_source) as image:
                slide_image = image.convert("RGB")
        except (OSError, ValueError):
            slide_image = None
    elif isinstance(slide_image_source, Image.Image):
        slide_image = slide_image_source
    if slide_image is not None:
        image_size = slide_image.size

    structure_signals = _query_table_structure_signals(
        table_blocks,
        lang=lang,
        llm_wrapper=llm_wrapper,
        slide_image=slide_image,
    )

    modeled_blocks = 0
    for block in table_blocks:
        block_id = str(block.get("block_id") or block.get("id") or "").strip()
        structure_signal = structure_signals.get(block_id) if block_id else None
        if structure_signal is not None and isinstance(
            structure_signal.get("bbox"), dict
        ):
            block["bbox"] = structure_signal["bbox"]
        structured_model = (
            structure_signal.get("table_model")
            if isinstance(structure_signal, dict)
            and isinstance(structure_signal.get("table_model"), dict)
            else None
        )
        deterministic_model = _build_deterministic_table_model(
            block,
            lines,
            image_size=image_size,
        )
        fallback_model = None
        if structured_model is None and (
            deterministic_model is None
            or _table_model_confidence_value(deterministic_model)
            < _TABLE_MODEL_MIN_CONFIDENCE
            or _table_model_is_structurally_suspicious(deterministic_model)
        ):
            fallback_model = _build_fallback_table_model(
                block,
                lang=lang,
                llm_wrapper=llm_wrapper,
                slide_image=slide_image,
                extracted_text=clean_ocr_text(str(block.get("text") or "")),
            )
        chosen_model = _select_best_table_model(
            structured_model,
            deterministic_model,
            fallback_model,
        )
        if chosen_model is None:
            block.pop("table_model", None)
            continue
        block["table_model"] = chosen_model
        modeled_blocks += 1
    return modeled_blocks


def _normalize_layout_bbox(raw_bbox: object) -> dict[str, float] | None:
    if not isinstance(raw_bbox, dict):
        return None
    x = raw_bbox.get("x")
    y = raw_bbox.get("y")
    w = raw_bbox.get("w")
    h = raw_bbox.get("h")
    if not all(isinstance(value, (int, float)) for value in (x, y, w, h)):
        return None
    if float(w) <= 0 or float(h) <= 0:
        return None
    return {
        "x": float(x),
        "y": float(y),
        "w": float(w),
        "h": float(h),
    }


def _normalize_layout_block_for_ocr(
    raw_block: dict[str, object],
    *,
    index: int,
) -> dict[str, object]:
    block_id = (
        raw_block.get("block_id") or raw_block.get("blockId") or raw_block.get("id")
    )
    block_type = normalize_block_type(raw_block.get("type"))
    text = clean_ocr_text(str(raw_block.get("text") or ""))
    items_raw = (
        raw_block.get("items") if isinstance(raw_block.get("items"), list) else []
    )
    payload = {
        "block_id": str(block_id).strip() or f"block-{index}",
        "type": block_type,
        "detected_type": (
            str(
                raw_block.get("detected_type")
                or raw_block.get("detectedType")
                or raw_block.get("type")
                or "unknown"
            )
            .strip()
            .lower()
            .replace("-", "_")
            or "unknown"
        ),
        "text": text,
        "items": clean_ocr_items(
            [str(item).strip() for item in items_raw if str(item).strip()]
        ),
        "bbox": _normalize_layout_bbox(raw_block.get("bbox")),
        "confidence": raw_block.get("confidence"),
    }
    group_id = normalize_optional_string(
        raw_block.get("group_id") or raw_block.get("groupId")
    )
    if group_id is not None:
        payload["group_id"] = group_id
    group_kind = normalize_group_kind(
        raw_block.get("group_kind") or raw_block.get("groupKind")
    )
    if group_kind is not None:
        payload["group_kind"] = group_kind
    parent_id = normalize_optional_string(
        raw_block.get("parent_id") or raw_block.get("parentId")
    )
    if parent_id is not None:
        payload["parent_id"] = parent_id
    list_level = normalize_list_level(
        raw_block.get("list_level") or raw_block.get("listLevel")
    )
    if list_level is not None:
        payload["list_level"] = list_level
    reading_order = normalize_reading_order(
        raw_block.get("reading_order") or raw_block.get("readingOrder")
    )
    if reading_order is not None:
        payload["reading_order"] = reading_order
    render_mode = normalize_render_mode(
        raw_block.get("render_mode") or raw_block.get("renderMode")
    )
    payload["render_mode"] = (
        render_mode
        if render_mode is not None
        else default_render_mode_for_type(block_type)
    )
    return payload


def _normalize_layout_slide_for_ocr(
    raw_slide: dict[str, object],
    *,
    index: int,
) -> dict[str, object] | None:
    slide_id = str(raw_slide.get("slide_id") or raw_slide.get("slideId") or "").strip()
    if not slide_id:
        return None
    raw_blocks = (
        raw_slide.get("blocks") if isinstance(raw_slide.get("blocks"), list) else []
    )
    raw_regions = (
        raw_slide.get("figure_regions")
        if isinstance(raw_slide.get("figure_regions"), list)
        else (
            raw_slide.get("figureRegions")
            if isinstance(raw_slide.get("figureRegions"), list)
            else []
        )
    )
    return {
        "slide_id": slide_id,
        "slide_number": int(
            raw_slide.get("slide_number") or raw_slide.get("slideNumber") or index + 1
        ),
        "page_number": int(
            raw_slide.get("page_number") or raw_slide.get("pageNumber") or index + 1
        ),
        "asset_path": str(
            raw_slide.get("asset_path") or raw_slide.get("assetPath") or ""
        ).strip(),
        "blocks": [
            _normalize_layout_block_for_ocr(block, index=block_index)
            for block_index, block in enumerate(raw_blocks)
            if isinstance(block, dict)
        ],
        "title_text": str(
            raw_slide.get("title_text") or raw_slide.get("titleText") or ""
        ).strip(),
        "bullet_texts": [
            str(item).strip()
            for item in (
                raw_slide.get("bullet_texts")
                if isinstance(raw_slide.get("bullet_texts"), list)
                else (
                    raw_slide.get("bulletTexts")
                    if isinstance(raw_slide.get("bulletTexts"), list)
                    else []
                )
            )
            if str(item).strip()
        ],
        "figure_regions": [
            region
            for region in (
                _normalize_layout_bbox(region)
                for region in raw_regions
                if isinstance(region, dict)
            )
            if region is not None
        ],
    }


def _normalize_layout_payload_for_ocr(
    layout_payload: dict[str, object],
    *,
    deck_id: str,
    lang: str,
) -> dict[str, object]:
    raw_slides = (
        layout_payload.get("slides")
        if isinstance(layout_payload.get("slides"), list)
        else []
    )
    normalized_slides = [
        normalized
        for index, raw_slide in enumerate(raw_slides)
        if isinstance(raw_slide, dict)
        for normalized in [_normalize_layout_slide_for_ocr(raw_slide, index=index)]
        if normalized is not None
    ]
    return {
        "deck_id": deck_id,
        "lang": str(layout_payload.get("lang") or lang or "eng"),
        "generated_at": str(
            layout_payload.get("generated_at")
            or layout_payload.get("generatedAt")
            or datetime.now(UTC).isoformat()
        ),
        "slides": normalized_slides,
    }


def _infer_layout_slide_canvas_size(
    slide_payload: dict[str, object],
) -> tuple[int, int] | None:
    max_right = 0.0
    max_bottom = 0.0
    blocks = (
        slide_payload.get("blocks")
        if isinstance(slide_payload.get("blocks"), list)
        else []
    )
    for block in blocks:
        if not isinstance(block, dict):
            continue
        bbox = _normalize_layout_bbox(block.get("bbox"))
        if bbox is None:
            continue
        max_right = max(max_right, float(bbox["x"]) + float(bbox["w"]))
        max_bottom = max(max_bottom, float(bbox["y"]) + float(bbox["h"]))
    regions = (
        slide_payload.get("figure_regions")
        if isinstance(slide_payload.get("figure_regions"), list)
        else []
    )
    for region in regions:
        if not isinstance(region, dict):
            continue
        bbox = _normalize_layout_bbox(region)
        if bbox is None:
            continue
        max_right = max(max_right, float(bbox["x"]) + float(bbox["w"]))
        max_bottom = max(max_bottom, float(bbox["y"]) + float(bbox["h"]))
    if max_right <= 0.0 or max_bottom <= 0.0:
        return None
    return (max(1, int(ceil(max_right))), max(1, int(ceil(max_bottom))))


def _resolve_layout_slide_canvas_size(
    deck_path: Path,
    slide_payload: dict[str, object],
) -> tuple[int, int] | None:
    image_path = _resolve_layout_slide_image_path(deck_path, slide_payload)
    if image_path is not None:
        try:
            with Image.open(image_path) as image:
                return image.size
        except (OSError, ValueError) as exc:
            LOGGER.warning("Failed to inspect slide image %s: %s", image_path, exc)
    return _infer_layout_slide_canvas_size(slide_payload)


def build_filtered_deck_ocr_inputs(
    deck: Deck,
    layout_payload: dict[str, object],
    *,
    deck_id: str,
    lang: str,
    slide_ids: list[str],
) -> tuple[Deck, dict[str, object]]:
    selected_ids = {
        str(slide_id).strip() for slide_id in slide_ids if str(slide_id).strip()
    }
    filtered_deck = Deck(
        deck_id=deck.deck_id,
        prompt_style=deck.prompt_style,
        owner_email=deck.owner_email,
        shared_with=list(deck.shared_with),
        slides=[slide for slide in deck.slides if slide.id in selected_ids],
    )
    normalized_payload = _normalize_layout_payload_for_ocr(
        layout_payload,
        deck_id=deck_id,
        lang=lang,
    )
    slides = (
        normalized_payload.get("slides")
        if isinstance(normalized_payload.get("slides"), list)
        else []
    )
    filtered_payload = {
        **normalized_payload,
        "slides": [
            slide_payload
            for slide_payload in slides
            if isinstance(slide_payload, dict)
            and str(slide_payload.get("slide_id") or "").strip() in selected_ids
        ],
    }
    return filtered_deck, filtered_payload


def _extract_slide_image_path(deck: Deck, deck_path: Path, slide: Slide) -> Path | None:
    soup = BeautifulSoup(slide.body_html or "", "html.parser")
    image = soup.find("img")
    if image is None:
        return None
    src = str(image.get("src") or "")
    if not src:
        return None
    prefix = f"/slides/deck/{deck.deck_id}/assets/"
    if src.startswith(prefix):
        rel_path = src[len(prefix) :]
    else:
        rel_path = src
    rel_path = rel_path.lstrip("/")
    if rel_path.startswith("assets/"):
        rel_path = rel_path[len("assets/") :]
    if not rel_path:
        return None
    candidate = deck_path / "assets" / Path(rel_path)
    if not candidate.exists():
        return None
    return candidate


def _resolve_layout_payload_for_ocr(
    deck: Deck,
    deck_path: Path,
    *,
    lang: str,
    layout_payload: dict[str, object] | None,
) -> dict[str, object]:
    resolved_payload = (
        layout_payload
        if layout_payload is not None
        else build_deck_layout_payload(deck, deck_path, lang=lang)
    )
    return _normalize_layout_payload_for_ocr(
        resolved_payload,
        deck_id=deck.deck_id,
        lang=lang,
    )


def _resolve_layout_slide_image_path(
    deck_path: Path, slide_payload: dict[str, object]
) -> Path | None:
    asset_path = str(slide_payload.get("asset_path") or "").strip()
    if not asset_path:
        return None
    candidate = (deck_path / Path(asset_path)).resolve()
    try:
        candidate.relative_to(deck_path.resolve())
    except ValueError:
        LOGGER.warning("Ignoring unsafe layout asset path for OCR: %s", candidate)
        return None
    if not candidate.exists():
        return None
    return candidate


def _bbox_to_crop_box(
    bbox: dict[str, float] | None,
    *,
    image_size: tuple[int, int],
) -> tuple[int, int, int, int] | None:
    if bbox is None:
        return None
    width, height = image_size
    left = max(0, int(floor(float(bbox["x"]))))
    top = max(0, int(floor(float(bbox["y"]))))
    right = min(width, int(ceil(float(bbox["x"] + bbox["w"]))))
    bottom = min(height, int(ceil(float(bbox["y"] + bbox["h"]))))
    if right <= left or bottom <= top:
        return None
    return (left, top, right, bottom)


def _expand_crop_box(
    crop_box: tuple[int, int, int, int] | None,
    *,
    image_size: tuple[int, int],
    block_type: str,
) -> tuple[int, int, int, int] | None:
    if crop_box is None:
        return None
    width, height = image_size
    left, top, right, bottom = crop_box
    crop_width = max(0, right - left)
    crop_height = max(0, bottom - top)
    normalized_type = str(block_type or "").strip().lower()
    if normalized_type == "title":
        pad_x = max(24, int(round(crop_width * 0.02)))
        pad_y = max(24, int(round(crop_height * 0.12)))
    else:
        pad_x = max(20, int(round(crop_width * 0.015)))
        pad_y = max(8, int(round(crop_height * 0.04)))
    expanded_left = max(0, left - pad_x)
    expanded_top = max(0, top - pad_y)
    expanded_right = min(width, right + pad_x)
    expanded_bottom = min(height, bottom + pad_y)
    if expanded_right <= expanded_left or expanded_bottom <= expanded_top:
        return crop_box
    return (expanded_left, expanded_top, expanded_right, expanded_bottom)


def _offset_bbox(
    bbox: dict[str, object] | None,
    *,
    x_offset: float,
    y_offset: float,
) -> dict[str, float] | None:
    normalized = _normalize_layout_bbox(bbox)
    if normalized is None:
        return None
    return {
        "x": normalized["x"] + x_offset,
        "y": normalized["y"] + y_offset,
        "w": normalized["w"],
        "h": normalized["h"],
    }


def _build_text_region_crop_box(
    blocks: list[dict[str, object]],
    *,
    image_size: tuple[int, int],
) -> tuple[int, int, int, int] | None:
    candidate_boxes: list[tuple[int, int, int, int]] = []
    for block in blocks:
        block_type = normalize_block_type(block.get("type"))
        if block_type not in _OCR_LAYOUT_TEXT_BLOCK_TYPES:
            continue
        crop_box = _bbox_to_crop_box(block.get("bbox"), image_size=image_size)
        expanded_crop = _expand_crop_box(
            crop_box,
            image_size=image_size,
            block_type=block_type,
        )
        if expanded_crop is None:
            continue
        candidate_boxes.append(expanded_crop)
    if not candidate_boxes:
        return None
    left = min(box[0] for box in candidate_boxes)
    top = min(box[1] for box in candidate_boxes)
    right = max(box[2] for box in candidate_boxes)
    bottom = max(box[3] for box in candidate_boxes)
    if right <= left or bottom <= top:
        return None
    return (left, top, right, bottom)


def _bbox_area(bbox: dict[str, float] | None) -> float:
    normalized = _normalize_layout_bbox(bbox)
    if normalized is None:
        return 0.0
    return float(normalized["w"]) * float(normalized["h"])


def _bbox_center(bbox: dict[str, float] | None) -> tuple[float, float] | None:
    normalized = _normalize_layout_bbox(bbox)
    if normalized is None:
        return None
    return (
        float(normalized["x"]) + float(normalized["w"]) / 2.0,
        float(normalized["y"]) + float(normalized["h"]) / 2.0,
    )


def _bbox_contains_point(
    bbox: dict[str, float] | None,
    *,
    x: float,
    y: float,
) -> bool:
    normalized = _normalize_layout_bbox(bbox)
    if normalized is None:
        return False
    return (
        normalized["x"] <= x <= normalized["x"] + normalized["w"]
        and normalized["y"] <= y <= normalized["y"] + normalized["h"]
    )


def _bbox_intersection_area(
    left_bbox: dict[str, float] | None,
    right_bbox: dict[str, float] | None,
) -> float:
    left = _normalize_layout_bbox(left_bbox)
    right = _normalize_layout_bbox(right_bbox)
    if left is None or right is None:
        return 0.0
    x0 = max(left["x"], right["x"])
    y0 = max(left["y"], right["y"])
    x1 = min(left["x"] + left["w"], right["x"] + right["w"])
    y1 = min(left["y"] + left["h"], right["y"] + right["h"])
    if x1 <= x0 or y1 <= y0:
        return 0.0
    return (x1 - x0) * (y1 - y0)


def _expand_bbox_for_assignment(
    bbox: dict[str, float] | None,
    *,
    image_size: tuple[int, int],
    block_type: str,
) -> dict[str, float] | None:
    crop_box = _bbox_to_crop_box(bbox, image_size=image_size)
    expanded_crop = _expand_crop_box(
        crop_box,
        image_size=image_size,
        block_type=block_type,
    )
    if expanded_crop is None:
        return None
    left, top, right, bottom = expanded_crop
    if right <= left or bottom <= top:
        return None
    return {
        "x": float(left),
        "y": float(top),
        "w": float(right - left),
        "h": float(bottom - top),
    }


def _score_line_assignment(
    line_bbox: dict[str, float] | None,
    *,
    block_bbox: dict[str, float] | None,
    expanded_bbox: dict[str, float] | None,
) -> float:
    normalized_line = _normalize_layout_bbox(line_bbox)
    normalized_block = _normalize_layout_bbox(block_bbox)
    normalized_expanded = _normalize_layout_bbox(expanded_bbox)
    if (
        normalized_line is None
        or normalized_block is None
        or normalized_expanded is None
    ):
        return -1.0
    line_area = _bbox_area(normalized_line)
    if line_area <= 0:
        return -1.0
    overlap_area = _bbox_intersection_area(normalized_line, normalized_expanded)
    center = _bbox_center(normalized_line)
    center_bonus = 0.0
    if center is not None:
        cx, cy = center
        if _bbox_contains_point(normalized_block, x=cx, y=cy):
            center_bonus = 1.5
        elif _bbox_contains_point(normalized_expanded, x=cx, y=cy):
            center_bonus = 0.75
    overlap_ratio = overlap_area / line_area
    if center_bonus <= 0 and overlap_ratio < 0.2:
        return -1.0
    return center_bonus + overlap_ratio


def _assign_full_slide_lines_to_blocks(
    full_slide_lines: list[dict[str, object]],
    blocks: list[dict[str, object]],
    *,
    image_size: tuple[int, int],
) -> dict[str, list[dict[str, object]]]:
    candidates = []
    for block in blocks:
        block_type = normalize_block_type(block.get("type"))
        if block_type not in _OCR_LAYOUT_TEXT_BLOCK_TYPES:
            continue
        block_id = str(block.get("block_id") or block.get("id") or "").strip()
        block_bbox = _normalize_layout_bbox(block.get("bbox"))
        expanded_bbox = _expand_bbox_for_assignment(
            block_bbox,
            image_size=image_size,
            block_type=block_type,
        )
        if not block_id or block_bbox is None or expanded_bbox is None:
            continue
        candidates.append(
            {
                "block_id": block_id,
                "bbox": block_bbox,
                "expanded_bbox": expanded_bbox,
            }
        )
    assigned: dict[str, list[dict[str, object]]] = {
        str(block.get("block_id") or block.get("id") or "").strip(): []
        for block in blocks
        if str(block.get("block_id") or block.get("id") or "").strip()
    }
    for raw_line in full_slide_lines:
        if not isinstance(raw_line, dict):
            continue
        text = str(raw_line.get("text") or "").strip()
        line_bbox = _normalize_layout_bbox(raw_line.get("bbox"))
        if not text or line_bbox is None:
            continue
        best_block_id = ""
        best_score = -1.0
        for candidate in candidates:
            score = _score_line_assignment(
                line_bbox,
                block_bbox=candidate["bbox"],
                expanded_bbox=candidate["expanded_bbox"],
            )
            if score > best_score:
                best_score = score
                best_block_id = str(candidate["block_id"])
        if not best_block_id or best_score < 0:
            continue
        assigned.setdefault(best_block_id, []).append(
            {
                "line_id": "",
                "text": text,
                "bbox": line_bbox,
                "confidence": raw_line.get("confidence"),
            }
        )
    return assigned


def _average_line_confidence(lines: list[dict[str, object]]) -> float | None:
    confidences = [
        float(line.get("confidence"))
        for line in lines
        if isinstance(line, dict) and isinstance(line.get("confidence"), (int, float))
    ]
    if not confidences:
        return None
    return sum(confidences) / float(len(confidences))


def _horizontal_overlap_width(
    left_bbox: dict[str, float] | None,
    right_bbox: dict[str, float] | None,
) -> float:
    if left_bbox is None or right_bbox is None:
        return 0.0
    return max(
        0.0,
        min(
            float(left_bbox["x"] + left_bbox["w"]),
            float(right_bbox["x"] + right_bbox["w"]),
        )
        - max(float(left_bbox["x"]), float(right_bbox["x"])),
    )


def _find_callout_heading_candidates(
    blocks: list[dict[str, object]],
    *,
    image_size: tuple[int, int],
) -> dict[str, str]:
    image_width = max(float(image_size[0]), 1.0)
    image_height = max(float(image_size[1]), 1.0)
    callout_blocks: list[tuple[str, dict[str, float]]] = []
    for block in blocks:
        block_id = str(block.get("block_id") or block.get("id") or "").strip()
        block_type = normalize_block_type(block.get("type"))
        group_kind = normalize_group_kind(
            block.get("group_kind") or block.get("groupKind")
        )
        bbox = _normalize_layout_bbox(block.get("bbox"))
        if not block_id or bbox is None:
            continue
        if block_type == "callout_banner" or group_kind == "callout":
            callout_blocks.append((block_id, bbox))
    if not callout_blocks:
        return {}

    candidates: dict[str, str] = {}
    for block in blocks:
        block_id = str(block.get("block_id") or block.get("id") or "").strip()
        block_type = normalize_block_type(block.get("type"))
        bbox = _normalize_layout_bbox(block.get("bbox"))
        if not block_id or bbox is None or block_type not in {"decorative", "unknown"}:
            continue
        center_x = float(bbox["x"] + (bbox["w"] / 2.0))
        width_ratio = float(bbox["w"]) / image_width
        height_ratio = float(bbox["h"]) / image_height
        if center_x < image_width * 0.25 or center_x > image_width * 0.75:
            continue
        if width_ratio < 0.12 or width_ratio > 0.55:
            continue
        if height_ratio > 0.12:
            continue
        best_parent_id = ""
        best_gap = float("inf")
        for parent_id, callout_bbox in callout_blocks:
            gap = float(callout_bbox["y"] - (bbox["y"] + bbox["h"]))
            overlap_width = _horizontal_overlap_width(bbox, callout_bbox)
            overlap_ratio = overlap_width / max(
                1.0,
                min(float(bbox["w"]), float(callout_bbox["w"])),
            )
            if gap < -12.0 or gap > 140.0 or overlap_ratio < 0.2:
                continue
            if gap < best_gap:
                best_gap = gap
                best_parent_id = parent_id
        if best_parent_id:
            candidates[block_id] = best_parent_id
    return candidates


def _title_block_needs_crop_fallback(
    block: dict[str, object],
    assigned_lines: list[dict[str, object]],
) -> bool:
    text = "\n".join(
        str(line.get("text") or "").strip()
        for line in assigned_lines
        if isinstance(line, dict) and str(line.get("text") or "").strip()
    ).strip()
    if not text:
        return True
    average_confidence = _average_line_confidence(assigned_lines)
    if average_confidence is not None and average_confidence < 0.8:
        return True
    compact_text = text.replace("\n", " ").strip()
    return len(compact_text) < 12


def _ocr_single_layout_block(
    image: Image.Image,
    block: dict[str, object],
    *,
    lang: str,
) -> tuple[list[dict[str, object]], list[str], str]:
    block_bbox = block.get("bbox")
    block_type = normalize_block_type(block.get("type"))
    crop_box = _bbox_to_crop_box(block_bbox, image_size=image.size)
    crop_box = _expand_crop_box(
        crop_box,
        image_size=image.size,
        block_type=block_type,
    )
    if crop_box is None:
        return [], [], ""
    crop = image.crop(crop_box)
    crop_x_offset = float(crop_box[0])
    crop_y_offset = float(crop_box[1])
    preprocess_profile = "none"
    allow_preprocess_fallback = False
    if block_type == "title":
        crop, inner_x_offset, inner_y_offset = _trim_near_white_margins(crop)
        crop_x_offset += float(inner_x_offset)
        crop_y_offset += float(inner_y_offset)
        preprocess_profile = "document_scan"
        allow_preprocess_fallback = True
    buffer = io.BytesIO()
    crop.save(buffer, format="PNG")
    raw_ocr = extract_raw_ocr_from_image_bytes(
        buffer.getvalue(),
        lang=lang,
        preprocess_profile=preprocess_profile,
        allow_preprocess_fallback=allow_preprocess_fallback,
        text_recognition_model_name=_slide_text_recognition_model_name(lang),
    )
    translated_lines: list[dict[str, object]] = []
    line_texts: list[str] = []
    for raw_line in extract_lines_from_raw_ocr_result(raw_ocr):
        if not isinstance(raw_line, dict):
            continue
        text = clean_ocr_text(str(raw_line.get("text") or ""))
        if not text:
            continue
        line_texts.append(text)
        translated_lines.append(
            {
                "line_id": "",
                "text": text,
                "bbox": _offset_bbox(
                    raw_line.get("bbox"),
                    x_offset=crop_x_offset,
                    y_offset=crop_y_offset,
                ),
                "confidence": raw_line.get("confidence"),
            }
        )
    block_text = clean_ocr_text(extract_text_from_raw_ocr_result(raw_ocr))
    if not block_text:
        block_text = clean_ocr_text("\n".join(line_texts))
    return translated_lines, line_texts, block_text.strip()


def _normalize_list_items_from_lines(line_texts: list[str]) -> list[str]:
    items: list[str] = []
    seen: set[str] = set()
    for raw_text in line_texts:
        text = clean_ocr_text(str(raw_text or ""))
        if not text:
            continue
        normalized = _BULLET_PREFIX_PATTERN.sub("", text).strip() or text
        key = normalized.lower()
        if key in seen:
            continue
        seen.add(key)
        items.append(normalized)
    return items


def _normalize_list_items_from_block(
    block_text: str,
    line_texts: list[str],
) -> list[str]:
    compact_block_text = " ".join(
        segment.strip()
        for segment in clean_ocr_text(str(block_text or "")).splitlines()
        if segment.strip()
    ).strip()
    if compact_block_text:
        return [compact_block_text]
    return _normalize_list_items_from_lines(line_texts)


def _normalize_callout_items_from_block(
    block_text: str,
    line_texts: list[str],
) -> list[str]:
    cleaned_lines = [
        clean_ocr_text(str(text or ""))
        for text in line_texts
        if clean_ocr_text(str(text or ""))
    ]
    if len(cleaned_lines) >= 2:
        return clean_ocr_items(cleaned_lines)
    raw_lines = [
        clean_ocr_text(segment)
        for segment in str(block_text or "").splitlines()
        if clean_ocr_text(segment)
    ]
    if len(raw_lines) >= 2:
        return clean_ocr_items(raw_lines)
    compact_text = clean_ocr_text(str(block_text or ""))
    return [compact_text] if compact_text else []


def _looks_like_callout_heading_text(text: str) -> bool:
    normalized = clean_ocr_text(str(text or "")).replace("\n", " ").strip()
    if not normalized:
        return False
    words = normalized.split()
    if len(words) > 8 or len(normalized) > 72:
        return False
    if normalized.endswith((".", ";", ":")):
        return False
    return any(character.isalpha() for character in normalized)


def _trim_near_white_margins(
    image: Image.Image,
    *,
    threshold: int = 245,
    padding: int = 8,
) -> tuple[Image.Image, int, int]:
    grayscale = ImageOps.grayscale(image.convert("RGB"))
    mask = grayscale.point(lambda value: 255 if value < threshold else 0)
    content_bbox = mask.getbbox()
    if content_bbox is None:
        return image, 0, 0
    left, top, right, bottom = content_bbox
    left = max(0, left - padding)
    top = max(0, top - padding)
    right = min(image.width, right + padding)
    bottom = min(image.height, bottom + padding)
    if right <= left or bottom <= top:
        return image, 0, 0
    return image.crop((left, top, right, bottom)), left, top


def _looks_like_list_item_text(text: str) -> bool:
    compact_text = str(text or "").strip()
    if not compact_text:
        return False
    first_line = next(
        (segment.strip() for segment in compact_text.splitlines() if segment.strip()),
        "",
    )
    if not first_line:
        return False
    return bool(
        _BULLET_PREFIX_PATTERN.match(first_line)
        or _DEFINITION_PREFIX_PATTERN.match(first_line)
        or _DEFINITION_PREFIX_PATTERN.match(compact_text.replace("\n", " "))
    )


def _promote_aligned_text_blocks_to_lists(
    blocks: list[dict[str, object]],
    block_line_texts: dict[str, list[str]],
) -> None:
    alignment_x_tolerance = 40.0
    alignment_width_tolerance = 320.0
    candidates: list[dict[str, object]] = []
    for block in blocks:
        if normalize_block_type(block.get("type")) not in {"text", "body_text"}:
            continue
        bbox = _normalize_layout_bbox(block.get("bbox"))
        if bbox is None:
            continue
        candidates.append({**block, "bbox": bbox})
    if len(candidates) < 2:
        return

    alignment_clusters: list[dict[str, object]] = []
    for candidate in sorted(
        candidates,
        key=lambda block: (float(block["bbox"]["x"]), float(block["bbox"]["y"])),
    ):
        candidate_x = float(candidate["bbox"]["x"])
        candidate_w = float(candidate["bbox"]["w"])
        for cluster in alignment_clusters:
            if (
                abs(candidate_x - float(cluster["x"])) <= alignment_x_tolerance
                and abs(candidate_w - float(cluster["w"])) <= alignment_width_tolerance
            ):
                cluster_blocks = cluster["blocks"]
                cluster_blocks.append(candidate)
                cluster["x"] = sum(
                    float(block["bbox"]["x"]) for block in cluster_blocks
                ) / len(cluster_blocks)
                cluster["w"] = sum(
                    float(block["bbox"]["w"]) for block in cluster_blocks
                ) / len(cluster_blocks)
                break
        else:
            alignment_clusters.append(
                {"x": candidate_x, "w": candidate_w, "blocks": [candidate]}
            )

    aligned_ids: set[str] = set()
    for cluster in alignment_clusters:
        cluster_blocks = cluster["blocks"]
        if len(cluster_blocks) < 2:
            continue

        definition_like = [
            block
            for block in cluster_blocks
            if _looks_like_list_item_text(str(block.get("text") or ""))
        ]
        if len(definition_like) >= 2:
            promoted_blocks = cluster_blocks
        elif len(cluster_blocks) >= 3:
            promoted_blocks = cluster_blocks
        else:
            continue

        aligned_ids.update(
            str(block.get("block_id") or block.get("id") or "").strip()
            for block in promoted_blocks
        )

    if not aligned_ids:
        return
    for block in blocks:
        block_id = str(block.get("block_id") or block.get("id") or "").strip()
        if block_id not in aligned_ids:
            continue
        if normalize_block_type(block.get("type")) not in {"text", "body_text"}:
            continue
        line_texts = block_line_texts.get(block_id) or []
        item_text = str(block.get("text") or "").strip()
        normalized_items = _normalize_list_items_from_block(
            item_text,
            line_texts or [item_text],
        )
        if not normalized_items:
            continue
        block["type"] = "bullet_item"
        block["items"] = normalized_items


def _normalize_line_payload(
    line: dict[str, object],
    *,
    include_bboxes: bool,
    line_index: int,
) -> dict[str, object]:
    line_id = line.get("line_id") or line.get("id") or f"line-{line_index}"
    payload: dict[str, object] = {
        "line_id": str(line_id),
        "text": clean_ocr_text(str(line.get("text") or "")),
        "confidence": line.get("confidence"),
    }
    if include_bboxes:
        payload["bbox"] = line.get("bbox")
    return payload


def _normalize_line_payloads(
    lines: list[dict[str, object]],
    *,
    include_bboxes: bool,
) -> list[dict[str, object]]:
    return [
        _normalize_line_payload(line, include_bboxes=include_bboxes, line_index=index)
        for index, line in enumerate(lines)
    ]


def _normalize_block_payload(
    block: dict[str, object],
    *,
    include_bboxes: bool,
    block_index: int,
) -> dict[str, object]:
    block_id = block.get("block_id") or block.get("id") or f"block-{block_index}"
    payload: dict[str, object] = {
        "block_id": str(block_id),
        "type": normalize_block_type(block.get("type")),
        "text": clean_ocr_text(str(block.get("text") or "")),
        "confidence": block.get("confidence"),
    }
    detected_type = normalize_optional_string(
        block.get("detected_type") or block.get("detectedType")
    )
    if detected_type is not None:
        payload["detected_type"] = detected_type
    items = block.get("items") if isinstance(block.get("items"), list) else []
    cleaned_items = clean_ocr_items(
        [str(item).strip() for item in items if str(item).strip()]
    )
    if cleaned_items:
        payload["items"] = cleaned_items
    group_id = normalize_optional_string(block.get("group_id") or block.get("groupId"))
    if group_id is not None:
        payload["group_id"] = group_id
    group_kind = normalize_group_kind(block.get("group_kind") or block.get("groupKind"))
    if group_kind is not None:
        payload["group_kind"] = group_kind
    parent_id = normalize_optional_string(
        block.get("parent_id") or block.get("parentId")
    )
    if parent_id is not None:
        payload["parent_id"] = parent_id
    list_level = normalize_list_level(block.get("list_level") or block.get("listLevel"))
    if list_level is not None:
        payload["list_level"] = list_level
    reading_order = normalize_reading_order(
        block.get("reading_order") or block.get("readingOrder")
    )
    if reading_order is not None:
        payload["reading_order"] = reading_order
    render_mode = normalize_render_mode(
        block.get("render_mode") or block.get("renderMode")
    )
    payload["render_mode"] = (
        render_mode
        if render_mode is not None
        else default_render_mode_for_type(payload["type"])
    )
    if isinstance(block.get("table_model"), dict):
        payload["table_model"] = block["table_model"]
    audit_status = str(block.get("audit_status") or "").strip()
    if audit_status:
        payload["audit_status"] = audit_status
    audit_reason = clean_ocr_text(str(block.get("audit_reason") or ""))
    if audit_reason:
        payload["audit_reason"] = audit_reason
    audit_suggested_text = clean_ocr_text(str(block.get("audit_suggested_text") or ""))
    if audit_suggested_text:
        payload["audit_suggested_text"] = audit_suggested_text
    visual_status = str(block.get("visual_status") or "").strip()
    if visual_status:
        payload["visual_status"] = visual_status
    visual_reason = clean_ocr_text(str(block.get("visual_reason") or ""))
    if visual_reason:
        payload["visual_reason"] = visual_reason
    visual_suggested_text = clean_ocr_text(
        str(block.get("visual_suggested_text") or "")
    )
    if visual_suggested_text:
        payload["visual_suggested_text"] = visual_suggested_text
    visual_confidence = block.get("visual_confidence")
    if isinstance(visual_confidence, (int, float)):
        payload["visual_confidence"] = float(visual_confidence)
    visual_text = clean_ocr_text(str(block.get("visual_text") or ""))
    if visual_text:
        payload["visual_text"] = visual_text
    visual_items = clean_ocr_items(
        [
            str(item).strip()
            for item in (
                block.get("visual_items")
                if isinstance(block.get("visual_items"), list)
                else []
            )
            if str(item).strip()
        ]
    )
    if visual_items:
        payload["visual_items"] = visual_items
    visual_lines = [
        line
        for line in (
            block.get("visual_lines")
            if isinstance(block.get("visual_lines"), list)
            else []
        )
        if isinstance(line, dict) and str(line.get("text") or "").strip()
    ]
    if visual_lines:
        payload["visual_lines"] = visual_lines
    if include_bboxes:
        payload["bbox"] = block.get("bbox")
    return payload


def _normalize_block_payloads(
    blocks: list[dict[str, object]],
    *,
    include_bboxes: bool,
) -> list[dict[str, object]]:
    return [
        _normalize_block_payload(
            block,
            include_bboxes=include_bboxes,
            block_index=index,
        )
        for index, block in enumerate(blocks)
    ]


def _normalize_figure_regions(
    regions: list[dict[str, object]], *, include_bboxes: bool
) -> list[dict[str, float]]:
    if not include_bboxes:
        return []
    normalized: list[dict[str, float]] = []
    for raw in regions:
        if not isinstance(raw, dict):
            continue
        x = raw.get("x")
        y = raw.get("y")
        w = raw.get("w")
        h = raw.get("h")
        if not all(isinstance(value, (int, float)) for value in (x, y, w, h)):
            continue
        normalized.append(
            {
                "x": float(x),
                "y": float(y),
                "w": float(w),
                "h": float(h),
            }
        )
    return normalized


def _build_structured_ocr_from_layout_slide(
    image: Image.Image,
    layout_slide: dict[str, object],
    *,
    lang: str,
    slide_id: str,
    slide_number: int,
) -> dict[str, object]:
    normalized_blocks: list[dict[str, object]] = []
    block_line_texts: dict[str, list[str]] = {}
    resolved_lines_by_block_id: dict[str, list[dict[str, object]]] = {}
    raw_blocks = (
        layout_slide.get("blocks")
        if isinstance(layout_slide.get("blocks"), list)
        else []
    )
    normalized_layout_blocks = [
        _normalize_layout_block_for_ocr(raw_block, index=block_index)
        for block_index, raw_block in enumerate(raw_blocks)
        if isinstance(raw_block, dict)
    ]
    callout_heading_parent_ids = _find_callout_heading_candidates(
        normalized_layout_blocks,
        image_size=image.size,
    )
    text_region_crop_box = _build_text_region_crop_box(
        normalized_layout_blocks,
        image_size=image.size,
    )
    full_slide_text = ""
    full_slide_lines: list[dict[str, object]] = []
    translated_full_slide_lines: list[dict[str, object]] = []
    if text_region_crop_box is not None:
        text_region = image.crop(text_region_crop_box)
        text_region_left = float(text_region_crop_box[0])
        text_region_top = float(text_region_crop_box[1])
        image_buffer = io.BytesIO()
        text_region.save(image_buffer, format="PNG")
        full_slide_raw_ocr = extract_raw_ocr_from_image_bytes(
            image_buffer.getvalue(),
            lang,
            preprocess_profile="document_scan",
            allow_preprocess_fallback=True,
            text_recognition_model_name=_slide_text_recognition_model_name(lang),
        )
        full_slide_lines = extract_lines_from_raw_ocr_result(
            full_slide_raw_ocr,
            slide_id=slide_id,
            slide_number=slide_number,
        )
        for raw_line in full_slide_lines:
            if not isinstance(raw_line, dict):
                continue
            translated_full_slide_lines.append(
                {
                    **raw_line,
                    "bbox": _offset_bbox(
                        _normalize_layout_bbox(raw_line.get("bbox")),
                        x_offset=text_region_left,
                        y_offset=text_region_top,
                    ),
                }
            )
        full_slide_text = extract_text_from_raw_ocr_result(full_slide_raw_ocr)
    full_slide_lines = translated_full_slide_lines
    assigned_lines_by_block_id = _assign_full_slide_lines_to_blocks(
        [line for line in full_slide_lines if isinstance(line, dict)],
        normalized_layout_blocks,
        image_size=image.size,
    )

    for block in normalized_layout_blocks:
        block_id = str(block.get("block_id") or block.get("id") or "").strip()
        block_type = normalize_block_type(block.get("type"))
        assigned_lines = list(assigned_lines_by_block_id.get(block_id) or [])
        for line in assigned_lines:
            if not isinstance(line, dict):
                continue
            line["text"] = clean_ocr_text(str(line.get("text") or ""))
        line_texts = [
            clean_ocr_text(str(line.get("text") or ""))
            for line in assigned_lines
            if isinstance(line, dict) and clean_ocr_text(str(line.get("text") or ""))
        ]
        if block_type == "title" and _title_block_needs_crop_fallback(
            block, assigned_lines
        ):
            fallback_lines, fallback_line_texts, fallback_text = (
                _ocr_single_layout_block(
                    image,
                    block,
                    lang=lang,
                )
            )
            if fallback_lines or fallback_text:
                assigned_lines = fallback_lines
                line_texts = fallback_line_texts
                if fallback_text:
                    block["text"] = fallback_text
        if block_type == "callout_banner" and len(line_texts) < 2:
            fallback_lines, fallback_line_texts, fallback_text = (
                _ocr_single_layout_block(
                    image,
                    block,
                    lang=lang,
                )
            )
            if fallback_lines or fallback_text:
                if len(fallback_line_texts) >= len(line_texts):
                    assigned_lines = fallback_lines
                    line_texts = fallback_line_texts
                if fallback_text:
                    block["text"] = fallback_text
        callout_parent_id = callout_heading_parent_ids.get(block_id)
        if callout_parent_id:
            fallback_lines, fallback_line_texts, fallback_text = (
                _ocr_single_layout_block(
                    image,
                    block,
                    lang=lang,
                )
            )
            candidate_text = clean_ocr_text(str(fallback_text or ""))
            if candidate_text and _looks_like_callout_heading_text(candidate_text):
                assigned_lines = fallback_lines
                line_texts = fallback_line_texts
                block["type"] = "body_text"
                block["group_kind"] = "callout"
                block["parent_id"] = callout_parent_id
                block["render_mode"] = "native"
                block["text"] = candidate_text
                block_type = "body_text"
        if block_type in _OCR_LAYOUT_TEXT_BLOCK_TYPES:
            if block_type != "title" or not str(block.get("text") or "").strip():
                block_text = clean_ocr_text("\n".join(line_texts))
                if block_text:
                    block["text"] = block_text
            else:
                block["text"] = clean_ocr_text(str(block.get("text") or ""))
            block_line_texts[block_id] = line_texts
            if block_type == "callout_banner":
                block["items"] = _normalize_callout_items_from_block(
                    str(block.get("text") or "").strip(),
                    line_texts,
                )
            elif block_type in BULLET_BLOCK_TYPES:
                block["items"] = _normalize_list_items_from_block(
                    str(block.get("text") or "").strip(),
                    line_texts,
                )
            resolved_lines_by_block_id[block_id] = assigned_lines
        normalized_blocks.append(block)

    _promote_aligned_text_blocks_to_lists(normalized_blocks, block_line_texts)

    translated_lines = [
        {
            **line,
            "slide_id": slide_id,
            "slide_number": slide_number,
        }
        for block in normalized_blocks
        for line in (
            resolved_lines_by_block_id.get(
                str(block.get("block_id") or block.get("id") or "").strip()
            )
            or []
        )
        if isinstance(line, dict) and str(line.get("text") or "").strip()
    ]

    translated_lines.sort(
        key=lambda line: (
            float(((line.get("bbox") or {}).get("y") or 1e9)),
            float(((line.get("bbox") or {}).get("x") or 1e9)),
        )
    )
    for line_index, line in enumerate(translated_lines):
        line["line_id"] = f"line-{line_index}"
        line["slide_id"] = slide_id
        line["slide_number"] = slide_number

    ocr_text = "\n".join(
        str(line.get("text") or "").strip()
        for line in translated_lines
        if str(line.get("text") or "").strip()
    ).strip()
    if not ocr_text:
        ocr_text = clean_ocr_text(full_slide_text)
    title_text = ""
    for block in normalized_blocks:
        if normalize_block_type(block.get("type")) != "title":
            continue
        text = str(block.get("text") or "").strip()
        if text:
            title_text = clean_ocr_text(text)
            break
    if not title_text:
        title_text = clean_ocr_text(str(layout_slide.get("title_text") or ""))
    bullet_texts = [
        clean_ocr_text(item)
        for block in normalized_blocks
        if normalize_block_type(block.get("type")) in BULLET_BLOCK_TYPES
        for item in (block.get("items") if isinstance(block.get("items"), list) else [])
        if clean_ocr_text(item)
    ]
    if not bullet_texts:
        bullet_texts = [
            clean_ocr_text(str(item))
            for item in (
                layout_slide.get("bullet_texts")
                if isinstance(layout_slide.get("bullet_texts"), list)
                else []
            )
            if clean_ocr_text(str(item))
        ]

    figure_regions = _normalize_figure_regions(
        [
            region
            for region in (
                layout_slide.get("figure_regions")
                if isinstance(layout_slide.get("figure_regions"), list)
                else []
            )
            if isinstance(region, dict)
        ],
        include_bboxes=True,
    )

    return {
        "raw_ocr": None,
        "raw_layout": None,
        "ocr_text": ocr_text,
        "lines": translated_lines,
        "blocks": normalized_blocks,
        "title_text": title_text,
        "bullet_texts": bullet_texts,
        "figure_regions": figure_regions,
    }


def _assemble_slide_payload(
    slide: Slide,
    slide_number: int,
    structured_ocr: dict[str, object],
    *,
    lang: str,
    include_bboxes: bool,
    llm_wrapper: object | None = None,
    slide_image_source: Image.Image | Path | None = None,
    event_callback: Callable[[str, dict[str, object]], None] | None = None,
) -> dict[str, object]:
    raw_lines = (
        structured_ocr.get("lines")
        if isinstance(structured_ocr.get("lines"), list)
        else []
    )
    raw_blocks = (
        structured_ocr.get("blocks")
        if isinstance(structured_ocr.get("blocks"), list)
        else []
    )

    normalized_lines = _normalize_line_payloads(
        [line for line in raw_lines if isinstance(line, dict)],
        include_bboxes=include_bboxes,
    )
    geometry_lines = (
        normalized_lines
        if include_bboxes
        else _normalize_line_payloads(
            [line for line in raw_lines if isinstance(line, dict)],
            include_bboxes=True,
        )
    )
    normalized_blocks = _normalize_block_payloads(
        [block for block in raw_blocks if isinstance(block, dict)],
        include_bboxes=include_bboxes,
    )

    def _emit_stage_event(event: str, details: dict[str, object]) -> None:
        _emit_ocr_event(
            event_callback,
            event,
            {
                "slideId": slide.id,
                "slideNumber": slide_number,
                **details,
            },
        )

    semantic_started_at = time.perf_counter()
    _emit_stage_event(
        "semantic_correction_start",
        {"blockCount": len(normalized_blocks)},
    )
    corrected_blocks = _apply_llm_corrections_to_blocks(
        normalized_blocks,
        lang=lang,
        llm_wrapper=llm_wrapper,
    )
    _emit_stage_event(
        "semantic_correction_done",
        {
            "blockCount": len(normalized_blocks),
            "correctedBlockCount": corrected_blocks,
            "elapsedMs": round((time.perf_counter() - semantic_started_at) * 1000.0, 1),
        },
    )

    audit_started_at = time.perf_counter()
    _emit_stage_event(
        "residual_audit_start",
        {"blockCount": len(normalized_blocks)},
    )
    audited_blocks = _apply_llm_residual_audit_to_blocks(
        normalized_blocks,
        lang=lang,
        llm_wrapper=llm_wrapper,
    )
    _emit_stage_event(
        "residual_audit_done",
        {
            "blockCount": len(normalized_blocks),
            "auditedBlockCount": audited_blocks,
            "elapsedMs": round((time.perf_counter() - audit_started_at) * 1000.0, 1),
        },
    )

    visual_corrected_blocks = 0
    if slide_image_source is not None:
        visual_started_at = time.perf_counter()
        _emit_stage_event(
            "visual_correction_start",
            {"blockCount": len(normalized_blocks)},
        )
        if isinstance(slide_image_source, Path):
            with Image.open(slide_image_source) as slide_image:
                visual_corrected_blocks = _apply_vlm_corrections_to_blocks(
                    normalized_blocks,
                    lang=lang,
                    llm_wrapper=llm_wrapper,
                    slide_image=slide_image.convert("RGB"),
                )
        else:
            visual_corrected_blocks = _apply_vlm_corrections_to_blocks(
                normalized_blocks,
                lang=lang,
                llm_wrapper=llm_wrapper,
                slide_image=slide_image_source,
            )
        _emit_stage_event(
            "visual_correction_done",
            {
                "blockCount": len(normalized_blocks),
                "correctedBlockCount": visual_corrected_blocks,
                "elapsedMs": round(
                    (time.perf_counter() - visual_started_at) * 1000.0, 1
                ),
            },
        )

    table_started_at = time.perf_counter()
    table_block_count = sum(
        1
        for block in normalized_blocks
        if normalize_block_type(block.get("type")) == "table"
    )
    if table_block_count:
        _emit_stage_event(
            "table_model_start",
            {"blockCount": table_block_count},
        )
    modeled_blocks = _apply_table_models_to_blocks(
        normalized_blocks,
        lines=geometry_lines,
        lang=lang,
        llm_wrapper=llm_wrapper,
        slide_image_source=slide_image_source,
    )
    if table_block_count:
        _emit_stage_event(
            "table_model_done",
            {
                "blockCount": table_block_count,
                "modeledBlockCount": modeled_blocks,
                "elapsedMs": round(
                    (time.perf_counter() - table_started_at) * 1000.0, 1
                ),
            },
        )

    ocr_text = clean_ocr_text(
        str(structured_ocr.get("ocr_text") or structured_ocr.get("ocrText") or "")
    )
    if corrected_blocks > 0 or visual_corrected_blocks > 0:
        corrected_block_texts = _collect_block_texts_for_ocr_text(normalized_blocks)
        if corrected_block_texts:
            ocr_text = "\n".join(corrected_block_texts).strip()
    if not ocr_text:
        text_lines = [
            clean_ocr_text(str(line.get("text") or ""))
            for line in normalized_lines
            if clean_ocr_text(str(line.get("text") or ""))
        ]
        if not text_lines:
            text_lines = [
                clean_ocr_text(str(block.get("text") or ""))
                for block in normalized_blocks
                if clean_ocr_text(str(block.get("text") or ""))
            ]
        ocr_text = "\n".join(text_lines)

    title_text = _derive_title_text_from_blocks(normalized_blocks)
    if not title_text:
        title_text = clean_ocr_text(str(structured_ocr.get("title_text") or ""))
    bullet_texts_raw = (
        structured_ocr.get("bullet_texts")
        if isinstance(structured_ocr.get("bullet_texts"), list)
        else []
    )
    bullet_texts = _derive_bullet_texts_from_blocks(normalized_blocks)
    if not bullet_texts:
        bullet_texts = clean_ocr_items(
            [str(item).strip() for item in bullet_texts_raw if str(item).strip()]
        )

    figure_regions_raw = (
        structured_ocr.get("figure_regions")
        if isinstance(structured_ocr.get("figure_regions"), list)
        else []
    )
    figure_regions = _normalize_figure_regions(
        [region for region in figure_regions_raw if isinstance(region, dict)],
        include_bboxes=include_bboxes,
    )

    return {
        "slide_id": slide.id,
        "slide_number": slide_number,
        "page_number": slide_number,
        "ocr_text": ocr_text,
        "raw_ocr": None,
        "raw_layout": None,
        "lines": normalized_lines,
        "blocks": normalized_blocks,
        "title_text": title_text,
        "bullet_texts": bullet_texts,
        "figure_regions": figure_regions,
    }


def _ocr_from_layout_payload(
    deck: Deck,
    deck_path: Path,
    layout_payload: dict[str, object],
    *,
    lang: str,
    include_bboxes: bool,
    llm_wrapper: object | None = None,
    progress_callback: Callable[[int, int], None] | None = None,
    event_callback: Callable[[str, dict[str, object]], None] | None = None,
) -> list[dict[str, object]]:
    slide_by_id = {slide.id: slide for slide in deck.slides}
    layout_slides = (
        layout_payload.get("slides")
        if isinstance(layout_payload.get("slides"), list)
        else []
    )
    total_pages = len(layout_slides)
    slides_payload: list[dict[str, object]] = []
    if progress_callback:
        progress_callback(0, total_pages)
    for built_count, layout_slide in enumerate(layout_slides, start=1):
        if not isinstance(layout_slide, dict):
            continue
        slide_id = str(layout_slide.get("slide_id") or "").strip()
        slide = slide_by_id.get(slide_id)
        if slide is None:
            continue
        slide_number = int(layout_slide.get("slide_number") or built_count)
        image_path = _resolve_layout_slide_image_path(deck_path, layout_slide)
        if image_path is None:
            continue
        slide_base_details = {
            "deckId": deck.deck_id,
            "source": "layout_guided_assets",
            "slideId": slide.id,
            "slideNumber": slide_number,
            "assetPath": str(image_path),
        }
        _emit_ocr_event(event_callback, "slide_start", slide_base_details)
        slide_started_at = time.perf_counter()
        with Image.open(image_path) as image:
            structured_ocr = _build_structured_ocr_from_layout_slide(
                image,
                layout_slide,
                lang=lang,
                slide_id=slide.id,
                slide_number=slide_number,
            )
        slides_payload.append(
            _assemble_slide_payload(
                slide,
                slide_number,
                structured_ocr,
                lang=lang,
                include_bboxes=include_bboxes,
                llm_wrapper=llm_wrapper,
                slide_image_source=image_path,
                event_callback=event_callback,
            )
        )
        _emit_ocr_event(
            event_callback,
            "slide_done",
            {
                **slide_base_details,
                "elapsedMs": round(
                    (time.perf_counter() - slide_started_at) * 1000.0, 1
                ),
                "lineCount": len(
                    structured_ocr.get("lines")
                    if isinstance(structured_ocr.get("lines"), list)
                    else []
                ),
                "blockCount": len(
                    structured_ocr.get("blocks")
                    if isinstance(structured_ocr.get("blocks"), list)
                    else []
                ),
                "figureRegionCount": len(
                    structured_ocr.get("figure_regions")
                    if isinstance(structured_ocr.get("figure_regions"), list)
                    else []
                ),
            },
        )
        if progress_callback:
            progress_callback(built_count, total_pages)
    return slides_payload


def _ocr_from_pdf(
    deck: Deck,
    pdf_path: Path,
    *,
    lang: str,
    include_bboxes: bool,
    llm_wrapper: object | None = None,
    style_hint: dict[str, object] | None = None,
    progress_callback: Callable[[int, int], None] | None = None,
    event_callback: Callable[[str, dict[str, object]], None] | None = None,
) -> list[dict[str, object]]:
    if not pdf_path.exists():
        raise ValueError(f"PDF not found at {pdf_path}")
    try:
        doc = fitz.open(pdf_path)
    except (fitz.FileDataError, RuntimeError, ValueError) as exc:
        raise ValueError("Supplied PDF could not be opened.") from exc
    slides_payload: list[dict[str, object]] = []
    with doc:
        if doc.page_count == 0:
            raise ValueError("Uploaded PDF has no pages.")
        if doc.page_count < len(deck.slides):
            LOGGER.warning(
                "PDF page count (%s) is less than slides (%s). OCR will use available pages.",
                doc.page_count,
                len(deck.slides),
            )
        total_pages = min(doc.page_count, len(deck.slides))
        if progress_callback:
            progress_callback(0, total_pages)
        for index, slide in enumerate(deck.slides):
            if index >= doc.page_count:
                break
            slide_number = index + 1
            slide_base_details = {
                "deckId": deck.deck_id,
                "source": "pdf",
                "slideId": slide.id,
                "slideNumber": slide_number,
                "pageIndex": index,
            }
            _emit_ocr_event(event_callback, "slide_start", slide_base_details)

            def _slide_step_callback(event: str, details: dict[str, object]) -> None:
                merged = dict(slide_base_details)
                merged.update(details)
                _emit_ocr_event(event_callback, event, merged)

            slide_started_at = time.perf_counter()
            page = doc.load_page(index)
            raster_matrix = fitz.Matrix(
                _SLIDES_PDF_OCR_RASTER_SCALE, _SLIDES_PDF_OCR_RASTER_SCALE
            )
            pix = page.get_pixmap(matrix=raster_matrix, alpha=True)
            image = Image.frombytes("RGBA", (pix.width, pix.height), pix.samples)
            flattened = Image.new("RGB", image.size, (255, 255, 255))
            flattened.paste(image, mask=image.split()[-1])
            buffer = io.BytesIO()
            flattened.save(buffer, format="PNG")
            structured_ocr = extract_structured_ocr_from_image_bytes(
                buffer.getvalue(),
                lang,
                slide_id=slide.id,
                slide_number=slide_number,
                style_hint=style_hint,
                include_layout=False,
                preprocess_profile="none",
                allow_preprocess_fallback=False,
                step_callback=_slide_step_callback,
            )
            slides_payload.append(
                _assemble_slide_payload(
                    slide,
                    slide_number,
                    structured_ocr,
                    lang=lang,
                    include_bboxes=include_bboxes,
                    llm_wrapper=llm_wrapper,
                    slide_image_source=flattened,
                    event_callback=event_callback,
                )
            )
            _emit_ocr_event(
                event_callback,
                "slide_done",
                {
                    **slide_base_details,
                    "elapsedMs": round(
                        (time.perf_counter() - slide_started_at) * 1000.0, 1
                    ),
                    "lineCount": len(
                        structured_ocr.get("lines")
                        if isinstance(structured_ocr.get("lines"), list)
                        else []
                    ),
                    "blockCount": len(
                        structured_ocr.get("blocks")
                        if isinstance(structured_ocr.get("blocks"), list)
                        else []
                    ),
                    "figureRegionCount": len(
                        structured_ocr.get("figure_regions")
                        if isinstance(structured_ocr.get("figure_regions"), list)
                        else []
                    ),
                },
            )
            if progress_callback:
                progress_callback(len(slides_payload), total_pages)
    return slides_payload


def _slides_with_images(deck: Deck, deck_path: Path) -> list[tuple[int, Slide, Path]]:
    slides_with_images: list[tuple[int, Slide, Path]] = []
    for index, slide in enumerate(deck.slides):
        image_path = _extract_slide_image_path(deck, deck_path, slide)
        if image_path is None:
            continue
        slides_with_images.append((index, slide, image_path))
    return slides_with_images


def _ocr_from_assets(
    deck: Deck,
    deck_path: Path,
    *,
    lang: str,
    include_bboxes: bool,
    llm_wrapper: object | None = None,
    style_hint: dict[str, object] | None = None,
    progress_callback: Callable[[int, int], None] | None = None,
    event_callback: Callable[[str, dict[str, object]], None] | None = None,
) -> list[dict[str, object]]:
    slides_payload: list[dict[str, object]] = []
    slides_with_images = _slides_with_images(deck, deck_path)
    total_pages = len(slides_with_images)
    if progress_callback:
        progress_callback(0, total_pages)
    for index, slide, image_path in slides_with_images:
        slide_number = index + 1
        slide_base_details = {
            "deckId": deck.deck_id,
            "source": "assets",
            "slideId": slide.id,
            "slideNumber": slide_number,
            "assetPath": str(image_path),
        }
        _emit_ocr_event(event_callback, "slide_start", slide_base_details)

        def _slide_step_callback(event: str, details: dict[str, object]) -> None:
            merged = dict(slide_base_details)
            merged.update(details)
            _emit_ocr_event(event_callback, event, merged)

        slide_started_at = time.perf_counter()
        structured_ocr = extract_structured_ocr_from_image_path(
            image_path,
            lang,
            slide_id=slide.id,
            slide_number=slide_number,
            style_hint=style_hint,
            include_layout=False,
            preprocess_profile="none",
            allow_preprocess_fallback=False,
            step_callback=_slide_step_callback,
        )
        slides_payload.append(
            _assemble_slide_payload(
                slide,
                slide_number,
                structured_ocr,
                lang=lang,
                include_bboxes=include_bboxes,
                llm_wrapper=llm_wrapper,
                slide_image_source=image_path,
                event_callback=event_callback,
            )
        )
        _emit_ocr_event(
            event_callback,
            "slide_done",
            {
                **slide_base_details,
                "elapsedMs": round(
                    (time.perf_counter() - slide_started_at) * 1000.0, 1
                ),
                "lineCount": len(
                    structured_ocr.get("lines")
                    if isinstance(structured_ocr.get("lines"), list)
                    else []
                ),
                "blockCount": len(
                    structured_ocr.get("blocks")
                    if isinstance(structured_ocr.get("blocks"), list)
                    else []
                ),
                "figureRegionCount": len(
                    structured_ocr.get("figure_regions")
                    if isinstance(structured_ocr.get("figure_regions"), list)
                    else []
                ),
            },
        )
        if progress_callback:
            progress_callback(len(slides_payload), total_pages)
    return slides_payload


def _slide_payload_is_missing(payload: dict[str, object] | None) -> bool:
    if payload is None:
        return True
    lines = payload.get("lines") if isinstance(payload.get("lines"), list) else []
    has_lines = any(
        str(line.get("text") or "").strip() for line in lines if isinstance(line, dict)
    )
    ocr_text = str(payload.get("ocr_text") or payload.get("ocrText") or "").strip()
    if has_lines or ocr_text:
        return False
    blocks = payload.get("blocks") if isinstance(payload.get("blocks"), list) else []
    ocrable_blocks = [
        block
        for block in blocks
        if isinstance(block, dict)
        and normalize_block_type(block.get("type")) in _OCR_LAYOUT_TEXT_BLOCK_TYPES
    ]
    title_text = str(
        payload.get("title_text") or payload.get("titleText") or ""
    ).strip()
    bullet_texts = (
        payload.get("bullet_texts")
        if isinstance(payload.get("bullet_texts"), list)
        else (
            payload.get("bulletTexts")
            if isinstance(payload.get("bulletTexts"), list)
            else []
        )
    )
    has_bullets = any(str(item).strip() for item in bullet_texts)
    if title_text or has_bullets:
        return False
    if not ocrable_blocks:
        return False
    for block in ocrable_blocks:
        if str(block.get("text") or "").strip():
            return False
        items = block.get("items") if isinstance(block.get("items"), list) else []
        if any(str(item).strip() for item in items):
            return False
    return True


def _fill_missing_slide_payloads(
    deck: Deck,
    deck_path: Path,
    payload: dict[str, object],
    *,
    lang: str,
    include_bboxes: bool,
    layout_payload: dict[str, object] | None = None,
    style_hint: dict[str, object] | None = None,
    progress_callback: Callable[[int, int], None] | None = None,
    event_callback: Callable[[str, dict[str, object]], None] | None = None,
) -> dict[str, object]:
    llm_wrapper = _build_local_llm_wrapper()
    normalized = normalize_ocr_payload(payload, deck_id=deck.deck_id, lang=lang)
    existing_slides = {
        str(slide.get("slide_id")): slide
        for slide in normalized.get("slides", [])
        if isinstance(slide, dict)
    }
    image_map = {
        slide.id: image_path
        for _, slide, image_path in _slides_with_images(deck, deck_path)
    }
    total_missing = sum(
        1
        for slide in deck.slides
        if image_map.get(slide.id) is not None
        and _slide_payload_is_missing(existing_slides.get(slide.id))
    )
    resolved_layout_payload = (
        _resolve_layout_payload_for_ocr(
            deck,
            deck_path,
            lang=lang,
            layout_payload=layout_payload,
        )
        if total_missing > 0
        else {"slides": []}
    )
    layout_slides_by_id = {
        str(slide_payload.get("slide_id") or ""): slide_payload
        for slide_payload in (
            resolved_layout_payload.get("slides")
            if isinstance(resolved_layout_payload.get("slides"), list)
            else []
        )
        if isinstance(slide_payload, dict)
    }
    built_missing = 0
    if progress_callback is not None and total_missing > 0:
        progress_callback(0, total_missing)
    updated_slides: list[dict[str, object]] = []
    updated = False
    for index, slide in enumerate(deck.slides):
        slide_number = index + 1
        current_payload = existing_slides.get(slide.id)
        layout_slide = layout_slides_by_id.get(slide.id)
        image_path = (
            _resolve_layout_slide_image_path(deck_path, layout_slide)
            if isinstance(layout_slide, dict)
            else image_map.get(slide.id)
        )
        if image_path and _slide_payload_is_missing(current_payload):
            slide_base_details = {
                "deckId": deck.deck_id,
                "source": "assets_missing",
                "slideId": slide.id,
                "slideNumber": slide_number,
                "assetPath": str(image_path),
            }
            _emit_ocr_event(event_callback, "slide_start", slide_base_details)

            def _slide_step_callback(event: str, details: dict[str, object]) -> None:
                merged = dict(slide_base_details)
                merged.update(details)
                _emit_ocr_event(event_callback, event, merged)

            slide_started_at = time.perf_counter()
            if isinstance(layout_slide, dict):
                with Image.open(image_path) as image:
                    structured_ocr = _build_structured_ocr_from_layout_slide(
                        image,
                        layout_slide,
                        lang=lang,
                        slide_id=slide.id,
                        slide_number=slide_number,
                    )
            else:
                structured_ocr = extract_structured_ocr_from_image_path(
                    image_path,
                    lang,
                    slide_id=slide.id,
                    slide_number=slide_number,
                    style_hint=style_hint,
                    include_layout=False,
                    preprocess_profile="none",
                    allow_preprocess_fallback=False,
                    step_callback=_slide_step_callback,
                )
            current_payload = _assemble_slide_payload(
                slide,
                slide_number,
                structured_ocr,
                lang=lang,
                include_bboxes=include_bboxes,
                llm_wrapper=llm_wrapper,
                slide_image_source=image_path,
                event_callback=event_callback,
            )
            _emit_ocr_event(
                event_callback,
                "slide_done",
                {
                    **slide_base_details,
                    "elapsedMs": round(
                        (time.perf_counter() - slide_started_at) * 1000.0, 1
                    ),
                    "lineCount": len(
                        structured_ocr.get("lines")
                        if isinstance(structured_ocr.get("lines"), list)
                        else []
                    ),
                    "blockCount": len(
                        structured_ocr.get("blocks")
                        if isinstance(structured_ocr.get("blocks"), list)
                        else []
                    ),
                    "figureRegionCount": len(
                        structured_ocr.get("figure_regions")
                        if isinstance(structured_ocr.get("figure_regions"), list)
                        else []
                    ),
                },
            )
            updated = True
            built_missing += 1
            if progress_callback is not None and total_missing > 0:
                progress_callback(built_missing, total_missing)
        elif current_payload:
            current_payload = {
                **current_payload,
                "slide_number": slide_number,
                "page_number": slide_number,
            }
        else:
            continue
        updated_slides.append(current_payload)
    if not updated:
        return normalized
    return normalize_ocr_payload(
        {
            "deck_id": deck.deck_id,
            "lang": lang,
            "ocr_strategy": OCR_STRATEGY_LAYOUT_GUIDED,
            "prompt_style": deck.prompt_style,
            "style_hint": style_hint,
            "generated_at": datetime.now(UTC).isoformat(),
            "slides": updated_slides,
        },
        deck_id=deck.deck_id,
        lang=lang,
    )


def build_deck_ocr_payload(
    deck: Deck,
    deck_path: Path,
    *,
    lang: str = "eng",
    include_bboxes: bool = True,
    layout_payload: dict[str, object] | None = None,
    pdf_path: Path | None = None,
    progress_callback: Callable[[int, int], None] | None = None,
    event_callback: Callable[[str, dict[str, object]], None] | None = None,
) -> dict[str, object]:
    """Build a persisted OCR payload for a deck."""
    style_hint = _build_ocr_style_hint(deck.prompt_style)
    llm_wrapper = _build_local_llm_wrapper()
    resolved_layout_payload = _resolve_layout_payload_for_ocr(
        deck,
        deck_path,
        lang=lang,
        layout_payload=layout_payload,
    )
    layout_slides = (
        resolved_layout_payload.get("slides")
        if isinstance(resolved_layout_payload.get("slides"), list)
        else []
    )
    if layout_slides:
        slides_payload = _ocr_from_layout_payload(
            deck,
            deck_path,
            resolved_layout_payload,
            lang=lang,
            include_bboxes=include_bboxes,
            llm_wrapper=llm_wrapper,
            progress_callback=progress_callback,
            event_callback=event_callback,
        )
        ocr_strategy = OCR_STRATEGY_LAYOUT_GUIDED
    else:
        slides_payload = (
            _ocr_from_pdf(
                deck,
                pdf_path,
                lang=lang,
                include_bboxes=include_bboxes,
                llm_wrapper=llm_wrapper,
                style_hint=style_hint,
                progress_callback=progress_callback,
                event_callback=event_callback,
            )
            if pdf_path
            else _ocr_from_assets(
                deck,
                deck_path,
                lang=lang,
                include_bboxes=include_bboxes,
                llm_wrapper=llm_wrapper,
                style_hint=style_hint,
                progress_callback=progress_callback,
                event_callback=event_callback,
            )
        )
        ocr_strategy = None
    return {
        "deck_id": deck.deck_id,
        "lang": lang,
        "ocr_strategy": ocr_strategy,
        "prompt_style": deck.prompt_style,
        "style_hint": style_hint,
        "generated_at": datetime.now(UTC).isoformat(),
        "slides": slides_payload,
    }


def _resolve_pdf_path(deck_path: Path) -> Path | None:
    candidate = deck_path / "source.pdf"
    return candidate if candidate.exists() else None


def ensure_deck_ocr_payload(
    deck: Deck,
    deck_path: Path,
    *,
    lang: str = "eng",
    include_bboxes: bool = True,
    layout_payload: dict[str, object] | None = None,
    cached_payload: dict[str, object] | None = None,
    progress_callback: Callable[[int, int], None] | None = None,
    event_callback: Callable[[str, dict[str, object]], None] | None = None,
) -> dict[str, object]:
    style_hint = _build_ocr_style_hint(deck.prompt_style)
    if cached_payload is not None:
        return _fill_missing_slide_payloads(
            deck,
            deck_path,
            cached_payload,
            lang=lang,
            include_bboxes=include_bboxes,
            layout_payload=layout_payload,
            style_hint=style_hint,
            progress_callback=progress_callback,
            event_callback=event_callback,
        )

    pdf_path = _resolve_pdf_path(deck_path)
    payload = build_deck_ocr_payload(
        deck,
        deck_path,
        lang=lang,
        include_bboxes=include_bboxes,
        layout_payload=layout_payload,
        pdf_path=pdf_path,
        progress_callback=progress_callback,
        event_callback=event_callback,
    )
    return normalize_ocr_payload(payload, deck_id=deck.deck_id, lang=lang)
