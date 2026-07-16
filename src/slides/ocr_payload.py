from __future__ import annotations

import re
from datetime import UTC, datetime

from pydantic import BaseModel, ConfigDict, Field

from src.slides.layout_semantics import (
    BULLET_BLOCK_TYPES,
    VISUAL_BLOCK_TYPES,
    default_render_mode_for_type,
    normalize_block_type,
    normalize_group_kind,
    normalize_list_level,
    normalize_optional_string,
    normalize_reading_order,
    normalize_render_mode,
)
from src.slides.ocr_cleanup import clean_ocr_items, clean_ocr_text

__all__ = [
    "DeckOcrAnalysisPayload",
    "DeckOcrAnalysisFigure",
    "DeckOcrAnalysisSlide",
    "DeckOcrAnalysisToken",
    "DeckOcrBlock",
    "DeckOcrFigureRegion",
    "DeckOcrLine",
    "DeckOcrPayload",
    "DeckOcrSlide",
    "build_analysis_payload",
    "find_slide_payload",
    "normalize_ocr_payload",
]

_LEADING_BULLET_MARKER_RE = re.compile(r"^\s*[•·▪◦*-]\s*")


class DeckOcrLine(BaseModel):
    """Canonical OCR line payload for a slide."""

    line_id: str | None = Field(default=None, alias="lineId")
    text: str
    bbox: dict[str, float] | None = None
    confidence: float | None = None

    model_config = ConfigDict(populate_by_name=True)


class DeckOcrBlock(BaseModel):
    """Canonical OCR layout block payload for a slide."""

    block_id: str | None = Field(default=None, alias="blockId")
    type: str = "unknown"
    detected_type: str | None = Field(default=None, alias="detectedType")
    text: str = ""
    items: list[str] = Field(default_factory=list)
    group_id: str | None = Field(default=None, alias="groupId")
    group_kind: str | None = Field(default=None, alias="groupKind")
    parent_id: str | None = Field(default=None, alias="parentId")
    list_level: int | None = Field(default=None, alias="listLevel")
    reading_order: int | None = Field(default=None, alias="readingOrder")
    render_mode: str | None = Field(default=None, alias="renderMode")
    bbox: dict[str, float] | None = None
    confidence: float | None = None
    table_model: dict[str, object] | None = Field(default=None, alias="tableModel")
    audit_status: str | None = Field(default=None, alias="auditStatus")
    audit_reason: str | None = Field(default=None, alias="auditReason")
    audit_suggested_text: str | None = Field(default=None, alias="auditSuggestedText")
    visual_status: str | None = Field(default=None, alias="visualStatus")
    visual_reason: str | None = Field(default=None, alias="visualReason")
    visual_suggested_text: str | None = Field(
        default=None, alias="visualSuggestedText"
    )
    visual_confidence: float | None = Field(default=None, alias="visualConfidence")
    visual_text: str | None = Field(default=None, alias="visualText")
    visual_items: list[str] = Field(default_factory=list, alias="visualItems")
    visual_lines: list[dict[str, object]] = Field(default_factory=list, alias="visualLines")

    model_config = ConfigDict(populate_by_name=True)


class DeckOcrFigureRegion(BaseModel):
    """Canonical OCR figure region payload for a slide."""

    x: float
    y: float
    w: float
    h: float


class DeckOcrSlide(BaseModel):
    """Canonical OCR payload for a slide."""

    slide_id: str = Field(..., alias="slideId")
    slide_number: int = Field(..., alias="slideNumber", ge=1)
    page_number: int = Field(..., alias="pageNumber", ge=1)
    ocr_text: str = Field(..., alias="ocrText")
    raw_ocr: object | None = Field(default=None, alias="rawOcr")
    raw_layout: object | None = Field(default=None, alias="rawLayout")
    lines: list[DeckOcrLine] = Field(default_factory=list)
    blocks: list[DeckOcrBlock] = Field(default_factory=list)
    title_text: str = Field(default="", alias="titleText")
    bullet_texts: list[str] = Field(default_factory=list, alias="bulletTexts")
    figure_regions: list[DeckOcrFigureRegion] = Field(
        default_factory=list,
        alias="figureRegions",
    )

    model_config = ConfigDict(populate_by_name=True)


class DeckOcrPayload(BaseModel):
    """Canonical OCR payload for a deck."""

    deck_id: str = Field(..., alias="deckId")
    lang: str
    ocr_strategy: str | None = Field(default=None, alias="ocrStrategy")
    prompt_style: str | None = Field(default=None, alias="promptStyle")
    style_hint: dict[str, object] | None = Field(default=None, alias="styleHint")
    generated_at: str = Field(..., alias="generatedAt")
    slides: list[DeckOcrSlide] = Field(default_factory=list)

    model_config = ConfigDict(populate_by_name=True)


class DeckOcrAnalysisToken(BaseModel):
    """Numeric token parsed from OCR text."""

    value: float
    unit: str
    raw: str


class DeckOcrAnalysisFigure(BaseModel):
    region_index: int = Field(..., alias="regionIndex", ge=0)
    bbox: dict[str, float] | None = None
    chart_type: str = Field(default="unknown", alias="chartType")
    confidence: float | None = None

    model_config = ConfigDict(populate_by_name=True)


class DeckOcrAnalysisSlide(BaseModel):
    slide_id: str = Field(..., alias="slideId")
    slide_number: int = Field(..., alias="slideNumber", ge=1)
    page_number: int = Field(..., alias="pageNumber", ge=1)
    ocr_text: str = Field(..., alias="ocrText")
    tokens: list[DeckOcrAnalysisToken] = Field(default_factory=list)
    figures: list[DeckOcrAnalysisFigure] = Field(default_factory=list)

    model_config = ConfigDict(populate_by_name=True)


class DeckOcrAnalysisPayload(BaseModel):
    deck_id: str = Field(..., alias="deckId")
    lang: str
    generated_at: str = Field(..., alias="generatedAt")
    slides: list[DeckOcrAnalysisSlide] = Field(default_factory=list)

    model_config = ConfigDict(populate_by_name=True)


def _coerce_int(value: object, *, default: int) -> int:
    if isinstance(value, int) and value >= 1:
        return value
    if isinstance(value, float) and value.is_integer() and value >= 1:
        return int(value)
    try:
        parsed = int(str(value))
    except (TypeError, ValueError):
        return default
    return parsed if parsed >= 1 else default


def _normalize_bbox(value: object) -> dict[str, float] | None:
    if not isinstance(value, dict):
        return None
    if all(isinstance(value.get(key), (int, float)) for key in ("x", "y", "w", "h")):
        x = float(value["x"])
        y = float(value["y"])
        w = float(value["w"])
        h = float(value["h"])
        if w > 0 and h > 0:
            return {"x": x, "y": y, "w": w, "h": h}
    if all(
        isinstance(value.get(key), (int, float)) for key in ("x0", "y0", "x1", "y1")
    ):
        x0 = float(value["x0"])
        y0 = float(value["y0"])
        x1 = float(value["x1"])
        y1 = float(value["y1"])
        if x1 > x0 and y1 > y0:
            return {"x": x0, "y": y0, "w": x1 - x0, "h": y1 - y0}
    if all(
        isinstance(value.get(key), (int, float))
        for key in ("left", "top", "right", "bottom")
    ):
        left = float(value["left"])
        top = float(value["top"])
        right = float(value["right"])
        bottom = float(value["bottom"])
        if right > left and bottom > top:
            return {"x": left, "y": top, "w": right - left, "h": bottom - top}
    return None


def _normalize_line(raw_line: dict[str, object], *, index: int) -> dict[str, object]:
    line_id = (
        raw_line.get("line_id") or raw_line.get("lineId") or raw_line.get("id") or ""
    )
    text = clean_ocr_text(str(raw_line.get("text") or raw_line.get("content") or ""))
    bbox = (
        raw_line.get("bbox")
        or raw_line.get("bbox_img")
        or raw_line.get("box")
        or raw_line.get("boundingBox")
    )
    normalized_bbox = _normalize_bbox(bbox)
    return {
        "line_id": str(line_id) if str(line_id).strip() else f"line-{index}",
        "text": text,
        "bbox": normalized_bbox,
        "confidence": raw_line.get("confidence"),
    }


def _normalize_text_items(raw_items: object) -> list[str]:
    if not isinstance(raw_items, list):
        return []
    normalized: list[str] = []
    seen: set[str] = set()
    for item in raw_items:
        text = clean_ocr_text(str(item or ""))
        if not text:
            continue
        key = text.lower()
        if key in seen:
            continue
        seen.add(key)
        normalized.append(text)
    return normalized


def _compact_block_text(value: str) -> str:
    return " ".join(
        segment.strip() for segment in str(value or "").splitlines() if segment.strip()
    ).strip()


def _clean_bullet_text(value: object) -> str:
    cleaned = clean_ocr_text(str(value or ""))
    if not cleaned:
        return ""
    return _LEADING_BULLET_MARKER_RE.sub("", cleaned).strip()


def _bullet_sort_key(block: dict[str, object]) -> tuple[float, float]:
    bbox = _normalize_bbox(block.get("bbox"))
    if bbox is None:
        return (1e9, 1e9)
    return (float(bbox.get("y") or 0.0), float(bbox.get("x") or 0.0))


def _coerce_non_negative_float(value: object) -> float | None:
    if isinstance(value, (int, float)):
        number = float(value)
    else:
        try:
            number = float(str(value).strip())
        except (TypeError, ValueError):
            return None
    return number if number >= 0.0 else None


def _normalize_table_cell(raw_cell: object) -> dict[str, object] | None:
    if not isinstance(raw_cell, dict):
        return None
    text = clean_ocr_text(str(raw_cell.get("text") or ""))
    align = str(raw_cell.get("align") or "").strip().lower()
    if align not in {"left", "center", "right"}:
        align = "left"
    try:
        row_span = int(raw_cell.get("row_span") or raw_cell.get("rowSpan") or 1)
        col_span = int(raw_cell.get("col_span") or raw_cell.get("colSpan") or 1)
    except (TypeError, ValueError):
        return None
    if row_span < 1 or col_span < 1:
        return None
    return {
        "text": text,
        "row_span": row_span,
        "col_span": col_span,
        "is_header": bool(raw_cell.get("is_header") or raw_cell.get("isHeader")),
        "align": align,
    }


def _normalize_table_model(raw_model: object) -> dict[str, object] | None:
    if not isinstance(raw_model, dict):
        return None
    raw_rows = raw_model.get("rows") if isinstance(raw_model.get("rows"), list) else []
    normalized_rows: list[dict[str, object]] = []
    inferred_column_count = 0
    for raw_row in raw_rows:
        if not isinstance(raw_row, dict):
            continue
        raw_cells = raw_row.get("cells") if isinstance(raw_row.get("cells"), list) else []
        normalized_cells = [
            normalized
            for raw_cell in raw_cells
            for normalized in [_normalize_table_cell(raw_cell)]
            if normalized is not None
        ]
        if not normalized_cells:
            continue
        inferred_column_count = max(inferred_column_count, len(normalized_cells))
        normalized_rows.append({"cells": normalized_cells})
    if not normalized_rows:
        return None

    try:
        row_count = int(raw_model.get("row_count") or raw_model.get("rowCount") or 0)
    except (TypeError, ValueError):
        row_count = 0
    row_count = row_count if row_count >= len(normalized_rows) else len(normalized_rows)

    try:
        column_count = int(
            raw_model.get("column_count") or raw_model.get("columnCount") or 0
        )
    except (TypeError, ValueError):
        column_count = 0
    column_count = (
        column_count if column_count >= inferred_column_count else inferred_column_count
    )
    if row_count < 1 or column_count < 1:
        return None

    try:
        header_rows = int(raw_model.get("header_rows") or raw_model.get("headerRows") or 0)
    except (TypeError, ValueError):
        header_rows = 0
    header_rows = min(max(header_rows, 0), row_count)

    raw_widths = (
        raw_model.get("column_widths")
        if isinstance(raw_model.get("column_widths"), list)
        else (
            raw_model.get("columnWidths")
            if isinstance(raw_model.get("columnWidths"), list)
            else []
        )
    )
    normalized_widths = [
        number
        for item in raw_widths
        for number in [_coerce_non_negative_float(item)]
        if number is not None and number > 0.0
    ]
    if len(normalized_widths) != column_count:
        normalized_widths = [1.0 / float(column_count)] * column_count
    else:
        total_width = sum(normalized_widths)
        if total_width <= 0.0:
            normalized_widths = [1.0 / float(column_count)] * column_count
        else:
            normalized_widths = [value / total_width for value in normalized_widths]

    confidence = _coerce_non_negative_float(raw_model.get("confidence"))
    if confidence is not None and confidence > 1.0:
        confidence = 1.0
    has_merged_cells = bool(
        raw_model.get("has_merged_cells") or raw_model.get("hasMergedCells")
    )
    source = clean_ocr_text(str(raw_model.get("source") or "")) or "deterministic_simple"
    return {
        "source": source,
        "confidence": confidence,
        "row_count": row_count,
        "column_count": column_count,
        "header_rows": header_rows,
        "column_widths": normalized_widths,
        "has_merged_cells": has_merged_cells,
        "rows": normalized_rows,
    }


def _normalize_block(raw_block: dict[str, object], *, index: int) -> dict[str, object]:
    block_id = (
        raw_block.get("block_id")
        or raw_block.get("blockId")
        or raw_block.get("id")
        or ""
    )
    block_type = normalize_block_type(raw_block.get("type"))
    detected_type = normalize_optional_string(
        raw_block.get("detected_type")
        or raw_block.get("detectedType")
        or raw_block.get("type")
    )
    text = clean_ocr_text(str(raw_block.get("text") or raw_block.get("content") or ""))
    bbox = _normalize_bbox(
        raw_block.get("bbox")
        or raw_block.get("bbox_img")
        or raw_block.get("box")
        or raw_block.get("boundingBox")
    )
    items = clean_ocr_items(_normalize_text_items(raw_block.get("items")))
    if block_type in BULLET_BLOCK_TYPES:
        compact_text = _compact_block_text(text)
        if compact_text:
            items = [compact_text]
    visual_text = clean_ocr_text(
        str(raw_block.get("visual_text") or raw_block.get("visualText") or "")
    )
    visual_items = clean_ocr_items(
        _normalize_text_items(
            raw_block.get("visual_items")
            if isinstance(raw_block.get("visual_items"), list)
            else raw_block.get("visualItems")
        )
    )
    raw_visual_lines = (
        raw_block.get("visual_lines")
        if isinstance(raw_block.get("visual_lines"), list)
        else (
            raw_block.get("visualLines")
            if isinstance(raw_block.get("visualLines"), list)
            else []
        )
    )
    visual_lines = [
        _normalize_line(line, index=line_index)
        for line_index, line in enumerate(raw_visual_lines)
        if isinstance(line, dict)
    ]
    group_id = normalize_optional_string(raw_block.get("group_id") or raw_block.get("groupId"))
    group_kind = normalize_group_kind(raw_block.get("group_kind") or raw_block.get("groupKind"))
    parent_id = normalize_optional_string(raw_block.get("parent_id") or raw_block.get("parentId"))
    list_level = normalize_list_level(raw_block.get("list_level") or raw_block.get("listLevel"))
    reading_order = normalize_reading_order(
        raw_block.get("reading_order") or raw_block.get("readingOrder")
    )
    render_mode = normalize_render_mode(
        raw_block.get("render_mode") or raw_block.get("renderMode")
    )
    if render_mode is None:
        render_mode = default_render_mode_for_type(block_type)
    return {
        "block_id": str(block_id) if str(block_id).strip() else f"block-{index}",
        "type": block_type,
        "detected_type": detected_type,
        "text": text,
        "items": items,
        "visual_text": visual_text,
        "visual_items": visual_items,
        "visual_lines": visual_lines,
        "group_id": group_id,
        "group_kind": group_kind,
        "parent_id": parent_id,
        "list_level": list_level,
        "reading_order": reading_order,
        "render_mode": render_mode,
        "bbox": bbox,
        "confidence": raw_block.get("confidence"),
        "table_model": _normalize_table_model(
            raw_block.get("table_model") or raw_block.get("tableModel")
        ),
        "audit_status": str(
            raw_block.get("audit_status") or raw_block.get("auditStatus") or ""
        ).strip()
        or None,
        "audit_reason": clean_ocr_text(
            str(raw_block.get("audit_reason") or raw_block.get("auditReason") or "")
        )
        or None,
        "audit_suggested_text": clean_ocr_text(
            str(
                raw_block.get("audit_suggested_text")
                or raw_block.get("auditSuggestedText")
                or ""
            )
        )
        or None,
        "visual_status": str(
            raw_block.get("visual_status") or raw_block.get("visualStatus") or ""
        ).strip()
        or None,
        "visual_reason": clean_ocr_text(
            str(raw_block.get("visual_reason") or raw_block.get("visualReason") or "")
        )
        or None,
        "visual_suggested_text": clean_ocr_text(
            str(
                raw_block.get("visual_suggested_text")
                or raw_block.get("visualSuggestedText")
                or ""
            )
        )
        or None,
        "visual_confidence": (
            raw_block.get("visual_confidence")
            if raw_block.get("visual_confidence") is not None
            else raw_block.get("visualConfidence")
        ),
    }


def _normalize_figure_region(raw_region: object) -> dict[str, float] | None:
    if not isinstance(raw_region, dict):
        return None
    bbox = _normalize_bbox(raw_region)
    if not bbox:
        return None
    return bbox


def _normalize_raw_payload(value: object) -> object | None:
    if value is None:
        return None
    if isinstance(value, (str, bool, int, float)):
        return value
    if isinstance(value, list):
        return [_normalize_raw_payload(item) for item in value]
    if isinstance(value, dict):
        return {str(key): _normalize_raw_payload(item) for key, item in value.items()}
    return None


def _derive_title_text(
    raw_slide: dict[str, object],
    normalized_blocks: list[dict[str, object]],
) -> str:
    explicit = clean_ocr_text(
        str(raw_slide.get("title_text") or raw_slide.get("titleText") or "")
    )
    if explicit:
        return explicit
    for block in normalized_blocks:
        if normalize_block_type(block.get("type")) == "title":
            text = clean_ocr_text(str(block.get("text") or ""))
            if text:
                return text
    return ""


def _derive_bullet_texts(
    raw_slide: dict[str, object],
    normalized_blocks: list[dict[str, object]],
) -> list[str]:
    collected: list[str] = []
    seen: set[str] = set()
    list_blocks = [
        block
        for block in normalized_blocks
        if normalize_block_type(block.get("type")) in BULLET_BLOCK_TYPES
    ]
    for block in sorted(list_blocks, key=_bullet_sort_key):
        normalized_items = [
            _clean_bullet_text(item)
            for item in (
                block.get("items") if isinstance(block.get("items"), list) else []
            )
        ]
        normalized_items = [item for item in normalized_items if item]
        if normalized_items:
            for item in normalized_items:
                key = item.lower()
                if key in seen:
                    continue
                seen.add(key)
                collected.append(item)
            continue
        block_text = _clean_bullet_text(_compact_block_text(str(block.get("text") or "")))
        if block_text:
            key = block_text.lower()
            if key not in seen:
                seen.add(key)
                collected.append(block_text)
    explicit: list[str] = []
    for item in _normalize_text_items(raw_slide.get("bullet_texts") or raw_slide.get("bulletTexts")):
        cleaned_item = _clean_bullet_text(item)
        if not cleaned_item:
            continue
        key = cleaned_item.lower()
        if key in seen:
            continue
        seen.add(key)
        explicit.append(cleaned_item)
    return collected + explicit


def _derive_figure_regions(
    raw_slide: dict[str, object],
    normalized_blocks: list[dict[str, object]],
) -> list[dict[str, float]]:
    raw_regions = raw_slide.get("figure_regions") or raw_slide.get("figureRegions")
    if isinstance(raw_regions, list):
        normalized = [
            region
            for region in (_normalize_figure_region(item) for item in raw_regions)
            if region is not None
        ]
        if normalized:
            return normalized
    block_regions: list[dict[str, float]] = []
    for block in normalized_blocks:
        if normalize_render_mode(block.get("render_mode") or block.get("renderMode")) == "group_as_image":
            continue
        if normalize_block_type(block.get("type")) not in VISUAL_BLOCK_TYPES:
            continue
        bbox = _normalize_figure_region(block.get("bbox"))
        if bbox:
            block_regions.append(bbox)
    return block_regions


def normalize_ocr_payload(
    payload: dict[str, object],
    *,
    deck_id: str | None = None,
    lang: str | None = None,
) -> dict[str, object]:
    """Normalize raw OCR payloads into the canonical schema."""
    from modules.slides.ocr import (
        extract_layout_summary_from_raw_layout,
        extract_text_from_raw_ocr_result,
    )

    resolved_deck_id = deck_id or str(
        payload.get("deck_id") or payload.get("deckId") or payload.get("deck") or ""
    )
    resolved_lang = str(payload.get("lang") or lang or "eng")
    resolved_ocr_strategy_raw = (
        payload.get("ocr_strategy") or payload.get("ocrStrategy") or None
    )
    resolved_ocr_strategy = (
        str(resolved_ocr_strategy_raw).strip()
        if resolved_ocr_strategy_raw is not None
        else None
    )
    if resolved_ocr_strategy == "":
        resolved_ocr_strategy = None
    resolved_prompt_style_raw = (
        payload.get("prompt_style") or payload.get("promptStyle") or None
    )
    resolved_prompt_style = (
        str(resolved_prompt_style_raw).strip()
        if resolved_prompt_style_raw is not None
        else None
    )
    if resolved_prompt_style == "":
        resolved_prompt_style = None
    raw_style_hint = payload.get("style_hint") or payload.get("styleHint")
    resolved_style_hint = raw_style_hint if isinstance(raw_style_hint, dict) else None
    generated_at = str(payload.get("generated_at") or payload.get("generatedAt") or "")
    if not generated_at:
        generated_at = datetime.now(UTC).isoformat()

    raw_slides = (
        payload.get("slides") if isinstance(payload.get("slides"), list) else []
    )
    normalized_slides: list[dict[str, object]] = []
    for index, raw_slide in enumerate(raw_slides):
        if not isinstance(raw_slide, dict):
            continue
        slide_id = str(
            raw_slide.get("slide_id") or raw_slide.get("slideId") or ""
        ).strip()
        slide_number = _coerce_int(
            raw_slide.get("slide_number") or raw_slide.get("slideNumber"),
            default=index + 1,
        )
        page_number = _coerce_int(
            raw_slide.get("page_number") or raw_slide.get("pageNumber"),
            default=slide_number,
        )
        raw_ocr = _normalize_raw_payload(
            raw_slide["raw_ocr"] if "raw_ocr" in raw_slide else raw_slide.get("rawOcr")
        )
        raw_layout = _normalize_raw_payload(
            raw_slide["raw_layout"]
            if "raw_layout" in raw_slide
            else raw_slide.get("rawLayout")
        )
        raw_lines = (
            raw_slide.get("lines") if isinstance(raw_slide.get("lines"), list) else []
        )
        normalized_lines = [
            _normalize_line(line, index=line_index)
            for line_index, line in enumerate(raw_lines)
            if isinstance(line, dict)
        ]
        raw_blocks = (
            raw_slide.get("blocks") if isinstance(raw_slide.get("blocks"), list) else []
        )
        normalized_blocks = [
            _normalize_block(block, index=block_index)
            for block_index, block in enumerate(raw_blocks)
            if isinstance(block, dict)
        ]
        raw_text = (
            raw_slide.get("ocr_text")
            or raw_slide.get("ocrText")
            or raw_slide.get("text")
            or ""
        )
        ocr_text = clean_ocr_text(str(raw_text))
        if not ocr_text and raw_ocr is not None:
            ocr_text = clean_ocr_text(extract_text_from_raw_ocr_result(raw_ocr))
        if not ocr_text:
            ocr_text = "\n".join(
                line["text"]
                for line in normalized_lines
                if str(line.get("text") or "").strip()
            )
        if not ocr_text:
            ocr_text = "\n".join(
                str(block.get("text") or "").strip()
                for block in normalized_blocks
                if str(block.get("text") or "").strip()
            )

        title_text = _derive_title_text(raw_slide, normalized_blocks)
        bullet_texts = _derive_bullet_texts(raw_slide, normalized_blocks)
        figure_regions = _derive_figure_regions(raw_slide, normalized_blocks)
        if raw_layout is not None and not (
            title_text or bullet_texts or figure_regions
        ):
            layout_summary = extract_layout_summary_from_raw_layout(
                raw_layout,
                slide_id=slide_id or None,
                slide_number=slide_number,
            )
            title_text = str(layout_summary.get("title_text") or "").strip()
            bullet_texts = _normalize_text_items(layout_summary.get("bullet_texts"))
            figure_regions = [
                region
                for region in (
                    _normalize_figure_region(item)
                    for item in (
                        layout_summary.get("figure_regions")
                        if isinstance(layout_summary.get("figure_regions"), list)
                        else []
                    )
                )
                if region is not None
            ]
        normalized_slides.append(
            {
                "slide_id": slide_id,
                "slide_number": slide_number,
                "page_number": page_number,
                "ocr_text": ocr_text,
                # Raw Paddle payloads include huge debug structures such as
                # preprocessed image arrays and are not required downstream.
                "raw_ocr": None,
                "raw_layout": None,
                "lines": normalized_lines,
                "blocks": normalized_blocks,
                "title_text": title_text,
                "bullet_texts": bullet_texts,
                "figure_regions": figure_regions,
            }
        )

    return {
        "deck_id": resolved_deck_id,
        "lang": resolved_lang,
        "ocr_strategy": resolved_ocr_strategy,
        "prompt_style": resolved_prompt_style,
        "style_hint": resolved_style_hint,
        "generated_at": generated_at,
        "slides": normalized_slides,
    }


def find_slide_payload(
    payload: dict[str, object], slide_id: str
) -> dict[str, object] | None:
    """Return the slide payload entry for ``slide_id`` when available."""

    normalized = normalize_ocr_payload(payload)
    for slide in normalized.get("slides", []):
        if slide.get("slide_id") == slide_id:
            return slide
    return None


def _tokens_from_text(text: str) -> list[dict[str, object]]:
    from src.slides.numeric_tokens import parse_numeric_tokens

    tokens = parse_numeric_tokens(text)
    return [
        {"value": token.value, "unit": token.unit, "raw": token.raw} for token in tokens
    ]


def build_analysis_payload(
    payload: dict[str, object],
    *,
    figure_classifications: dict[str, list[dict[str, object]]] | None = None,
) -> dict[str, object]:
    """Return OCR payload with numeric tokens extracted per slide."""

    normalized = normalize_ocr_payload(payload)
    slides = normalized.get("slides", [])
    analysis_slides = []
    for slide in slides:
        slide_id = str(slide.get("slide_id") or "")
        classified_regions = (
            figure_classifications.get(slide_id, [])
            if isinstance(figure_classifications, dict)
            else []
        )
        ocr_text = str(slide.get("ocr_text") or "")
        analysis_slides.append(
            {
                "slide_id": slide_id,
                "slide_number": slide.get("slide_number"),
                "page_number": slide.get("page_number"),
                "ocr_text": ocr_text,
                "tokens": _tokens_from_text(ocr_text),
                "figures": classified_regions,
            }
        )
    return {
        "deck_id": normalized.get("deck_id", ""),
        "lang": normalized.get("lang", "eng"),
        "generated_at": normalized.get("generated_at", datetime.now(UTC).isoformat()),
        "slides": analysis_slides,
    }
