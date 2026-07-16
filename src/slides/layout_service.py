from __future__ import annotations

import base64
import io
import logging
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Callable

from bs4 import BeautifulSoup  # type: ignore[import]
from openai import OpenAIError
from PIL import Image

import modules.utilities.config as config_module
from modules.llm.batch_runner import run_step_json
from modules.llm.llm_call_wrapper import init_llm_wrapper
from modules.slides.ocr import (
    extract_layout_summary_from_raw_layout,
    extract_raw_layout_from_image_path,
    summarize_layout_blocks,
)
from modules.utilities.session_context import SessionContext
from src.slides.layout_semantics import (
    BLOCK_SORT_FALLBACK,
    GROUP_RENDER_MODES,
    LAYOUT_SEMANTIC_TYPES,
    block_sort_key,
    default_render_mode_for_type,
    normalize_block_type,
    normalize_group_kind,
    normalize_list_level,
    normalize_optional_string,
    normalize_reading_order,
    normalize_render_mode,
)
from src.slides.models import Deck, Slide
from src.slides.ocr_cleanup import clean_ocr_text

__all__ = [
    "SlideLayoutOpenAIError",
    "apply_semantic_layout_corrections_to_payload",
    "build_deck_layout_payload",
]

LOGGER = logging.getLogger(__name__)
_SEMANTIC_LAYOUT_MAX_IMAGE_SIDE = 1600
_GROUP_AS_IMAGE_TYPES = {"figure", "metric", "exhibit_label", "decorative"}
_SEMANTIC_LAYOUT_SYSTEM_PROMPT = (
    "You are correcting semantic layout labels for presentation slides. "
    "Return JSON only with a top-level blocks array. "
    "For each provided blockId, choose exactly one type from: "
    "title, body_text, bullet_item, group_label, footer_meta, implication_banner, callout_banner, table_title, metric, figure, exhibit_label, table, decorative. "
    "Do not return unknown. Relabel only the provided blockIds; do not invent new boxes. "
    "Use groupId to keep blocks in the same exhibit together. "
    "Use renderMode values native, group_as_image, or ignore. "
    "Use group_as_image when a figure, metric, or label should stay visually attached to a nearby exhibit. "
    "Use listLevel as a 0-based nesting level for bullets. "
    "Use parentId only when a block is clearly subordinate to another block. "
    "Big numeric callouts such as 30M, 500W, or 4,5M are metrics. "
    "Text embedded in or tightly attached to diagrams, comparison panels, and annotated images is exhibit_label. "
    "Small attribution/date text near the bottom of a cover slide is footer_meta. "
    "A bottom-strip conclusion or recommendation is implication_banner. "
    "A boxed conclusion/callout banner is callout_banner. "
    "A short caption immediately above a table is table_title. "
    "Separators, arrows, and non-informational decoration are decorative."
)


class SlideLayoutOpenAIError(RuntimeError):
    """Raised when OpenAI-backed layout semantic correction fails."""


def _extract_slide_image_path(deck: Deck, deck_path: Path, slide: Slide) -> Path | None:
    soup = BeautifulSoup(slide.body_html or "", "html.parser")
    image = soup.find("img")
    if image is None:
        return None
    src = str(image.get("src") or image.get("data-src") or "").strip()
    if not src:
        return None
    prefix = f"/slides/deck/{deck.deck_id}/assets/"
    if src.startswith(prefix):
        relative = src[len(prefix) :]
    else:
        relative = src.lstrip("/")
    if relative.startswith("assets/"):
        relative = relative[len("assets/") :]
    if not relative:
        return None
    candidate = (deck_path / "assets" / Path(relative)).resolve()
    assets_root = (deck_path / "assets").resolve()
    try:
        candidate.relative_to(assets_root)
    except ValueError:
        LOGGER.warning(
            "Ignoring unsafe slide asset path for %s: %s", slide.id, candidate
        )
        return None
    if not candidate.exists():
        return None
    return candidate


def _normalize_bbox(raw_bbox: object) -> dict[str, float] | None:
    if not isinstance(raw_bbox, dict):
        return None
    x = raw_bbox.get("x")
    y = raw_bbox.get("y")
    w = raw_bbox.get("w")
    h = raw_bbox.get("h")
    if not all(isinstance(value, (int, float)) for value in (x, y, w, h)):
        return None
    return {
        "x": float(x),
        "y": float(y),
        "w": float(w),
        "h": float(h),
    }


def _finalize_semantic_block(block: dict[str, object]) -> dict[str, object]:
    finalized = dict(block)
    finalized["text"] = clean_ocr_text(str(finalized.get("text") or ""))
    finalized["items"] = [
        clean_ocr_text(str(item))
        for item in (
            finalized.get("items") if isinstance(finalized.get("items"), list) else []
        )
        if clean_ocr_text(str(item))
    ]
    finalized["detected_type"] = (
        str(finalized.get("detected_type") or finalized.get("type") or "unknown")
        .strip()
        .lower()
        .replace("-", "_")
        or "unknown"
    )
    block_type = normalize_block_type(finalized.get("type"))
    group_id = normalize_optional_string(
        finalized.get("group_id") or finalized.get("groupId")
    )
    group_kind = normalize_group_kind(
        finalized.get("group_kind") or finalized.get("groupKind")
    )
    parent_id = normalize_optional_string(
        finalized.get("parent_id") or finalized.get("parentId")
    )
    list_level = normalize_list_level(
        finalized.get("list_level")
        if "list_level" in finalized
        else finalized.get("listLevel")
    )
    reading_order = normalize_reading_order(
        finalized.get("reading_order")
        if "reading_order" in finalized
        else finalized.get("readingOrder")
    )
    render_mode = normalize_render_mode(
        finalized.get("render_mode")
        if "render_mode" in finalized
        else finalized.get("renderMode")
    )
    if block_type == "unknown":
        if group_id:
            block_type = "exhibit_label" if finalized["text"] else "decorative"
        elif finalized["text"]:
            block_type = "body_text"
        else:
            block_type = "decorative"
    if block_type in {"bullet_item", "group_label"} and list_level is None:
        list_level = 0
    if render_mode is None:
        if group_id and block_type in _GROUP_AS_IMAGE_TYPES:
            render_mode = "group_as_image"
        else:
            render_mode = default_render_mode_for_type(block_type)
    if block_type == "decorative":
        render_mode = "ignore"
    if render_mode == "group_as_image" and group_id is None:
        group_id = str(finalized.get("block_id") or "")
    if block_type == "bullet_item" and not finalized["items"] and finalized["text"]:
        finalized["items"] = [finalized["text"]]

    finalized["type"] = block_type
    finalized["render_mode"] = render_mode
    if group_id is not None:
        finalized["group_id"] = group_id
    else:
        finalized.pop("group_id", None)
    if group_kind is not None:
        finalized["group_kind"] = group_kind
    else:
        finalized.pop("group_kind", None)
    if parent_id is not None:
        finalized["parent_id"] = parent_id
    else:
        finalized.pop("parent_id", None)
    if list_level is not None:
        finalized["list_level"] = list_level
    else:
        finalized.pop("list_level", None)
    if reading_order is not None:
        finalized["reading_order"] = reading_order
    else:
        finalized.pop("reading_order", None)
    return finalized


def _normalize_block(raw_block: dict[str, object], index: int) -> dict[str, object]:
    items = raw_block.get("items") if isinstance(raw_block.get("items"), list) else []
    cleaned_items = [str(item).strip() for item in items if str(item).strip()]
    payload: dict[str, object] = {
        "block_id": str(
            raw_block.get("block_id") or raw_block.get("id") or f"block-{index}"
        ),
        "type": normalize_block_type(raw_block.get("type")),
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
        "text": str(raw_block.get("text") or "").strip(),
        "items": cleaned_items,
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
    if render_mode is not None:
        payload["render_mode"] = render_mode
    bbox = _normalize_bbox(raw_block.get("bbox"))
    if bbox is not None:
        payload["bbox"] = bbox
    confidence = raw_block.get("confidence")
    if isinstance(confidence, (int, float)):
        payload["confidence"] = float(confidence)
    return _finalize_semantic_block(payload)


def _normalize_figure_regions(raw_regions: object) -> list[dict[str, float]]:
    if not isinstance(raw_regions, list):
        return []
    regions: list[dict[str, float]] = []
    for raw_region in raw_regions:
        if not isinstance(raw_region, dict):
            continue
        x = raw_region.get("x")
        y = raw_region.get("y")
        w = raw_region.get("w")
        h = raw_region.get("h")
        if not all(isinstance(value, (int, float)) for value in (x, y, w, h)):
            continue
        regions.append(
            {
                "x": float(x),
                "y": float(y),
                "w": float(w),
                "h": float(h),
            }
        )
    return regions


def _bbox_area(raw_bbox: dict[str, float] | None) -> float:
    if raw_bbox is None:
        return 0.0
    return max(0.0, float(raw_bbox["w"])) * max(0.0, float(raw_bbox["h"]))


def _intersection_area(
    left_bbox: dict[str, float] | None,
    right_bbox: dict[str, float] | None,
) -> float:
    if left_bbox is None or right_bbox is None:
        return 0.0
    left = max(float(left_bbox["x"]), float(right_bbox["x"]))
    top = max(float(left_bbox["y"]), float(right_bbox["y"]))
    right = min(
        float(left_bbox["x"] + left_bbox["w"]),
        float(right_bbox["x"] + right_bbox["w"]),
    )
    bottom = min(
        float(left_bbox["y"] + left_bbox["h"]),
        float(right_bbox["y"] + right_bbox["h"]),
    )
    if right <= left or bottom <= top:
        return 0.0
    return (right - left) * (bottom - top)


def _prune_layout_blocks(blocks: list[dict[str, object]]) -> list[dict[str, object]]:
    pruned: list[dict[str, object]] = []
    for block in blocks:
        block_type = str(block.get("detected_type") or block.get("type") or "unknown")
        bbox = _normalize_bbox(block.get("bbox"))
        area = _bbox_area(bbox)
        if block_type == "unknown" and area < 1200.0:
            continue
        if block_type == "unknown" and bbox is not None:
            overlaps_known = any(
                str(existing.get("detected_type") or existing.get("type") or "unknown")
                != "unknown"
                and (
                    _intersection_area(bbox, _normalize_bbox(existing.get("bbox")))
                    / max(area, 1.0)
                )
                >= 0.9
                for existing in blocks
                if existing is not block
            )
            if overlaps_known:
                continue
        pruned.append(block)
    return pruned


def _build_local_llm_wrapper() -> object:
    session = SessionContext.from_state({})
    init_llm_wrapper("", session=session)
    return session.state["llm_wrapper"]


def _html_text(value: str) -> str:
    if not value:
        return ""
    return clean_ocr_text(BeautifulSoup(value, "html.parser").get_text(" ", strip=True))


def _image_to_data_url(image: Image.Image) -> str:
    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    encoded = base64.b64encode(buffer.getvalue()).decode("ascii")
    return f"data:image/png;base64,{encoded}"


def _load_slide_data_url(image_path: Path) -> str:
    with Image.open(image_path) as image:
        rgb = image.convert("RGB")
        max_side = max(rgb.size)
        if max_side > _SEMANTIC_LAYOUT_MAX_IMAGE_SIDE:
            scale = _SEMANTIC_LAYOUT_MAX_IMAGE_SIDE / float(max_side)
            rgb = rgb.resize(
                (
                    max(1, int(round(rgb.width * scale))),
                    max(1, int(round(rgb.height * scale))),
                )
            )
        return _image_to_data_url(rgb)


def _block_prompt_payload(block: dict[str, object]) -> dict[str, object]:
    payload: dict[str, object] = {
        "blockId": str(block.get("block_id") or ""),
        "currentType": normalize_block_type(block.get("type")),
        "detectedType": str(
            block.get("detected_type") or block.get("type") or "unknown"
        ),
        "text": clean_ocr_text(str(block.get("text") or "")),
    }
    items = block.get("items") if isinstance(block.get("items"), list) else []
    if items:
        payload["items"] = [
            clean_ocr_text(str(item)) for item in items if clean_ocr_text(str(item))
        ]
    bbox = _normalize_bbox(block.get("bbox"))
    if bbox is not None:
        payload["bbox"] = bbox
    confidence = block.get("confidence")
    if isinstance(confidence, (int, float)):
        payload["confidence"] = float(confidence)
    return payload


def _build_semantic_layout_prompt(
    *,
    slide: Slide,
    slide_number: int,
    lang: str,
    blocks: list[dict[str, object]],
) -> str:
    title_hint = _html_text(slide.title_html)
    body_hint = _html_text(slide.body_html)[:400]
    block_payload = [
        _block_prompt_payload(block) for block in sorted(blocks, key=block_sort_key)
    ]
    return (
        "Correct the semantic role of each slide layout block.\n"
        f"Language: {lang}\n"
        f"HTML title hint: {title_hint or 'n/a'}\n"
        f"HTML body hint: {body_hint or 'n/a'}\n"
        f"Slide number: {slide_number}\n"
        "Return JSON with this shape:\n"
        '{"blocks":[{"blockId":"...","type":"title|body_text|bullet_item|group_label|footer_meta|implication_banner|callout_banner|table_title|metric|figure|exhibit_label|table|decorative","groupId":"... or null","groupKind":"... or null","parentId":"... or null","listLevel":0,"readingOrder":0,"renderMode":"native|group_as_image|ignore"}]}\n'
        "Existing blocks:\n"
        f"{block_payload}"
    )


def _semantic_block_corrections_from_response(
    response: object,
) -> dict[str, dict[str, object]]:
    if not isinstance(response, dict):
        return {}
    raw_blocks = (
        response.get("blocks")
        if isinstance(response.get("blocks"), list)
        else response.get("layoutBlocks")
    )
    if not isinstance(raw_blocks, list):
        return {}
    corrections: dict[str, dict[str, object]] = {}
    for raw_block in raw_blocks:
        if not isinstance(raw_block, dict):
            continue
        block_id = normalize_optional_string(
            raw_block.get("blockId") or raw_block.get("block_id") or raw_block.get("id")
        )
        if block_id is None:
            continue
        correction: dict[str, object] = {}
        block_type = normalize_block_type(raw_block.get("type"))
        if block_type in LAYOUT_SEMANTIC_TYPES:
            correction["type"] = block_type
        group_id = normalize_optional_string(
            raw_block.get("groupId") or raw_block.get("group_id")
        )
        if group_id is not None:
            correction["group_id"] = group_id
        group_kind = normalize_group_kind(
            raw_block.get("groupKind") or raw_block.get("group_kind")
        )
        if group_kind is not None:
            correction["group_kind"] = group_kind
        parent_id = normalize_optional_string(
            raw_block.get("parentId") or raw_block.get("parent_id")
        )
        if parent_id is not None:
            correction["parent_id"] = parent_id
        list_level = normalize_list_level(
            raw_block.get("listLevel") or raw_block.get("list_level")
        )
        if list_level is not None:
            correction["list_level"] = list_level
        reading_order = normalize_reading_order(
            raw_block.get("readingOrder") or raw_block.get("reading_order")
        )
        if reading_order is not None:
            correction["reading_order"] = reading_order
        render_mode = normalize_render_mode(
            raw_block.get("renderMode") or raw_block.get("render_mode")
        )
        if render_mode in GROUP_RENDER_MODES:
            correction["render_mode"] = render_mode
        corrections[block_id] = correction
    return corrections


def _assign_default_reading_order(
    blocks: list[dict[str, object]],
) -> list[dict[str, object]]:
    sorted_blocks = sorted(blocks, key=block_sort_key)
    for index, block in enumerate(sorted_blocks):
        if normalize_reading_order(block.get("reading_order")) is None:
            block["reading_order"] = index
    return sorted(
        sorted_blocks,
        key=lambda block: (
            (
                normalize_reading_order(block.get("reading_order"))
                if normalize_reading_order(block.get("reading_order")) is not None
                else BLOCK_SORT_FALLBACK
            ),
            *block_sort_key(block),
        ),
    )


def _apply_semantic_layout_corrections(
    *,
    deck: Deck,
    inspectable: list[dict[str, object]],
    lang: str,
) -> None:
    if not inspectable:
        return

    naming_params = config_module.get_naming_params()
    query_step = naming_params["slideLayoutSemanticCorrectionQuery"]
    prompts: list[dict[str, object]] = []
    prompt_entries: list[dict[str, object]] = []
    for entry in inspectable:
        image_path = entry["image_path"]
        slide = entry["slide"]
        blocks = entry["blocks"]
        if not isinstance(image_path, Path) or not blocks:
            continue
        try:
            image_data_url = _load_slide_data_url(image_path)
        except (OSError, ValueError) as exc:
            LOGGER.warning(
                "Skipping semantic layout correction for %s: %s",
                slide.id,
                exc,
            )
            continue
        prompts.append(
            {
                "user_content": [
                    {
                        "type": "input_text",
                        "text": _build_semantic_layout_prompt(
                            slide=slide,
                            slide_number=int(entry["slide_number"]),
                            lang=lang,
                            blocks=blocks,
                        ),
                    },
                    {
                        "type": "input_image",
                        "image_url": image_data_url,
                    },
                ]
            }
        )
        prompt_entries.append(entry)
    if not prompts:
        return
    try:
        llm_wrapper = _build_local_llm_wrapper()
    except Exception as exc:  # pragma: no cover - runtime safeguard
        raise SlideLayoutOpenAIError(
            "OpenAI wrapper initialization failed during slide layout semantic correction."
        ) from exc
    try:
        responses = run_step_json(
            llm_wrapper,
            query_step,
            _SEMANTIC_LAYOUT_SYSTEM_PROMPT,
            prompts,
            retry_missing=1,
        )
    except (OSError, RuntimeError, TypeError, ValueError, OpenAIError) as exc:
        raise SlideLayoutOpenAIError(
            "OpenAI call failed during slide layout semantic correction."
        ) from exc
    if len(responses) != len(prompt_entries):
        LOGGER.warning(
            "Skipping layout semantic correction because response count (%s) does not match slides (%s).",
            len(responses),
            len(prompt_entries),
        )
        return
    for entry, response in zip(prompt_entries, responses):
        corrections = _semantic_block_corrections_from_response(response)
        corrected_blocks: list[dict[str, object]] = []
        for block in entry["blocks"]:
            block_id = str(block.get("block_id") or "")
            merged = dict(block)
            if block_id in corrections:
                merged.update(corrections[block_id])
            corrected_blocks.append(_finalize_semantic_block(merged))
        entry["blocks"] = _assign_default_reading_order(corrected_blocks)


def _summarize_blocks(
    *,
    blocks: list[dict[str, object]],
    fallback_title_text: str,
    fallback_bullet_texts: list[str],
    fallback_figure_regions: list[dict[str, float]],
) -> tuple[str, list[str], list[dict[str, float]]]:
    summary = summarize_layout_blocks(blocks)
    title_text = (
        clean_ocr_text(str(summary.get("title_text") or "")) or fallback_title_text
    )
    bullet_texts = [
        clean_ocr_text(str(item))
        for item in (
            summary.get("bullet_texts")
            if isinstance(summary.get("bullet_texts"), list)
            else []
        )
        if clean_ocr_text(str(item))
    ]
    if not bullet_texts:
        bullet_texts = fallback_bullet_texts
    figure_regions = _normalize_figure_regions(summary.get("figure_regions"))
    if not figure_regions:
        figure_regions = fallback_figure_regions
    return title_text, bullet_texts, figure_regions


def _resolve_payload_image_path(
    deck_path: Path, raw_slide: dict[str, object]
) -> Path | None:
    asset_path = str(
        raw_slide.get("asset_path") or raw_slide.get("assetPath") or ""
    ).strip()
    if not asset_path:
        return None
    candidate = (deck_path / asset_path).resolve()
    try:
        candidate.relative_to(deck_path)
    except ValueError:
        LOGGER.warning(
            "Ignoring unsafe layout asset path for semantic correction: %s", candidate
        )
        return None
    return candidate if candidate.exists() else None


def apply_semantic_layout_corrections_to_payload(
    deck: Deck,
    deck_path: Path,
    layout_payload: dict[str, object],
    *,
    lang: str = "eng",
    slide_ids: set[str] | None = None,
) -> dict[str, object]:
    """Apply only the semantic VLM pass to an existing layout payload."""
    deck_path = Path(deck_path).resolve()
    selected_ids = (
        {str(slide_id).strip() for slide_id in slide_ids if str(slide_id).strip()}
        if slide_ids is not None
        else None
    )
    slide_by_id = {slide.id: slide for slide in deck.slides}
    raw_slides = (
        layout_payload.get("slides")
        if isinstance(layout_payload.get("slides"), list)
        else []
    )
    inspectable: list[dict[str, object]] = []
    for raw_slide in raw_slides:
        if not isinstance(raw_slide, dict):
            continue
        slide_id = str(
            raw_slide.get("slide_id") or raw_slide.get("slideId") or ""
        ).strip()
        if not slide_id:
            continue
        if selected_ids is not None and slide_id not in selected_ids:
            continue
        slide = slide_by_id.get(slide_id)
        image_path = _resolve_payload_image_path(deck_path, raw_slide)
        raw_blocks = (
            raw_slide.get("blocks") if isinstance(raw_slide.get("blocks"), list) else []
        )
        if slide is None or image_path is None:
            continue
        blocks = [
            _normalize_block(raw_block, block_index)
            for block_index, raw_block in enumerate(raw_blocks)
            if isinstance(raw_block, dict)
        ]
        inspectable.append(
            {
                "slide": slide,
                "slide_number": int(
                    raw_slide.get("slide_number") or raw_slide.get("slideNumber") or 1
                ),
                "page_number": int(
                    raw_slide.get("page_number") or raw_slide.get("pageNumber") or 1
                ),
                "image_path": image_path,
                "blocks": _prune_layout_blocks(blocks),
                "fallback_title_text": clean_ocr_text(
                    str(raw_slide.get("title_text") or raw_slide.get("titleText") or "")
                ),
                "fallback_bullet_texts": [
                    clean_ocr_text(str(item))
                    for item in (
                        raw_slide.get("bullet_texts")
                        if isinstance(raw_slide.get("bullet_texts"), list)
                        else (
                            raw_slide.get("bulletTexts")
                            if isinstance(raw_slide.get("bulletTexts"), list)
                            else []
                        )
                    )
                    if clean_ocr_text(str(item))
                ],
                "fallback_figure_regions": _normalize_figure_regions(
                    raw_slide.get("figure_regions")
                    if isinstance(raw_slide.get("figure_regions"), list)
                    else raw_slide.get("figureRegions")
                ),
            }
        )
    _apply_semantic_layout_corrections(deck=deck, inspectable=inspectable, lang=lang)

    slides_payload: list[dict[str, object]] = []
    for entry in inspectable:
        slide = entry["slide"]
        image_path = entry["image_path"]
        blocks = _assign_default_reading_order(
            [
                _finalize_semantic_block(dict(block))
                for block in entry["blocks"]
                if isinstance(block, dict)
            ]
        )
        title_text, bullet_texts, figure_regions = _summarize_blocks(
            blocks=blocks,
            fallback_title_text=str(entry["fallback_title_text"] or ""),
            fallback_bullet_texts=list(entry["fallback_bullet_texts"]),
            fallback_figure_regions=list(entry["fallback_figure_regions"]),
        )
        slides_payload.append(
            {
                "slide_id": slide.id,
                "slide_number": int(entry["slide_number"]),
                "page_number": int(entry["page_number"]),
                "asset_path": str(image_path.relative_to(deck_path)),
                "blocks": blocks,
                "title_text": title_text,
                "bullet_texts": bullet_texts,
                "figure_regions": figure_regions,
            }
        )
    return {
        "deck_id": deck.deck_id,
        "lang": lang,
        "generated_at": datetime.now(UTC).isoformat(),
        "slides": slides_payload,
    }


def build_deck_layout_payload(
    deck: Deck,
    deck_path: Path,
    *,
    lang: str = "eng",
    apply_semantic_correction: bool = True,
    progress_callback: Callable[[int, int], None] | None = None,
    slide_ids: set[str] | None = None,
) -> dict[str, object]:
    """Build a persisted layout payload for every inspectable slide in a deck."""
    deck_path = Path(deck_path).resolve()
    selected_ids = (
        {str(slide_id).strip() for slide_id in slide_ids if str(slide_id).strip()}
        if slide_ids is not None
        else None
    )

    inspectable: list[dict[str, object]] = []
    for index, slide in enumerate(deck.slides):
        if selected_ids is not None and slide.id not in selected_ids:
            continue
        image_path = _extract_slide_image_path(deck, deck_path, slide)
        if image_path is None:
            continue
        raw_layout = extract_raw_layout_from_image_path(image_path, lang)
        layout_summary = extract_layout_summary_from_raw_layout(
            raw_layout,
            slide_id=slide.id,
            slide_number=index + 1,
        )
        raw_blocks = (
            layout_summary.get("blocks")
            if isinstance(layout_summary.get("blocks"), list)
            else []
        )
        blocks = [
            _normalize_block(raw_block, block_index)
            for block_index, raw_block in enumerate(raw_blocks)
            if isinstance(raw_block, dict)
        ]
        inspectable.append(
            {
                "slide": slide,
                "slide_number": index + 1,
                "page_number": index + 1,
                "image_path": image_path,
                "blocks": _prune_layout_blocks(blocks),
                "fallback_title_text": clean_ocr_text(
                    str(layout_summary.get("title_text") or "")
                ),
                "fallback_bullet_texts": [
                    clean_ocr_text(str(item))
                    for item in (
                        layout_summary.get("bullet_texts")
                        if isinstance(layout_summary.get("bullet_texts"), list)
                        else []
                    )
                    if clean_ocr_text(str(item))
                ],
                "fallback_figure_regions": _normalize_figure_regions(
                    layout_summary.get("figure_regions")
                ),
            }
        )

    total = len(inspectable)
    if progress_callback is not None:
        progress_callback(0, total)
    if apply_semantic_correction:
        _apply_semantic_layout_corrections(
            deck=deck, inspectable=inspectable, lang=lang
        )

    slides_payload: list[dict[str, object]] = []
    for built_count, entry in enumerate(inspectable, start=1):
        slide = entry["slide"]
        image_path = entry["image_path"]
        blocks = _assign_default_reading_order(
            [
                _finalize_semantic_block(dict(block))
                for block in entry["blocks"]
                if isinstance(block, dict)
            ]
        )
        title_text, bullet_texts, figure_regions = _summarize_blocks(
            blocks=blocks,
            fallback_title_text=str(entry["fallback_title_text"] or ""),
            fallback_bullet_texts=list(entry["fallback_bullet_texts"]),
            fallback_figure_regions=list(entry["fallback_figure_regions"]),
        )
        slides_payload.append(
            {
                "slide_id": slide.id,
                "slide_number": int(entry["slide_number"]),
                "page_number": int(entry["page_number"]),
                "asset_path": str(image_path.relative_to(deck_path)),
                "blocks": blocks,
                "title_text": title_text,
                "bullet_texts": bullet_texts,
                "figure_regions": figure_regions,
            }
        )
        if progress_callback is not None:
            progress_callback(built_count, total)
    return {
        "deck_id": deck.deck_id,
        "lang": lang,
        "generated_at": datetime.now(UTC).isoformat(),
        "slides": slides_payload,
    }
