from __future__ import annotations

import base64
import io
import logging
from pathlib import Path
from typing import Any

from bs4 import BeautifulSoup  # type: ignore[import]
from PIL import Image, UnidentifiedImageError

from modules.llm.batch_runner import run_step_json
from modules.llm.model_router import should_use_batch
from modules.utilities.config import get_naming_params
from src.slides.models import Deck, Slide
from src.slides.ocr_payload import normalize_ocr_payload

__all__ = ["classify_deck_chart_regions"]

LOGGER = logging.getLogger(__name__)

_ALLOWED_CHART_TYPES = {
    "slope",
    "area",
    "bar",
    "mekko",
    "combo",
    "table",
    "other",
    "unknown",
}

_SYSTEM_PROMPT = (
    "Classify the chart family in each image crop. "
    "Return valid JSON with keys chartType and confidence. "
    "chartType must be one of: slope, area, bar, mekko, combo, table, other, unknown. "
    "confidence must be a number between 0 and 1."
)


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


def _coerce_bbox(raw_bbox: object) -> tuple[float, float, float, float] | None:
    if not isinstance(raw_bbox, dict):
        return None
    x = raw_bbox.get("x")
    y = raw_bbox.get("y")
    w = raw_bbox.get("w")
    h = raw_bbox.get("h")
    if not all(isinstance(value, (int, float)) for value in (x, y, w, h)):
        return None
    return float(x), float(y), float(w), float(h)


def _crop_region_to_data_url(
    image_path: Path,
    bbox: tuple[float, float, float, float],
) -> str:
    with Image.open(image_path) as image:
        rgb = image.convert("RGB")
        img_w, img_h = rgb.size
        x, y, w, h = bbox
        left = max(0, min(int(round(x)), img_w - 1))
        top = max(0, min(int(round(y)), img_h - 1))
        right = max(left + 1, min(int(round(x + w)), img_w))
        bottom = max(top + 1, min(int(round(y + h)), img_h))
        cropped = rgb.crop((left, top, right, bottom))
        with io.BytesIO() as buffer:
            cropped.save(buffer, format="PNG")
            encoded = base64.b64encode(buffer.getvalue()).decode("ascii")
    return f"data:image/png;base64,{encoded}"


def _coerce_chart_type(value: object) -> str:
    normalized = str(value or "").strip().lower()
    return normalized if normalized in _ALLOWED_CHART_TYPES else "unknown"


def _coerce_confidence(value: object) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    confidence = float(value)
    if confidence < 0:
        return None
    if confidence > 1:
        confidence = confidence / 100.0
    if confidence < 0 or confidence > 1:
        return None
    return confidence


def classify_deck_chart_regions(
    llm_wrapper: Any,
    *,
    deck: Deck,
    deck_path: Path,
    ocr_payload: dict[str, object],
) -> dict[str, list[dict[str, object]]]:
    """Classify OCR figure regions into chart families via a single batch workflow."""

    naming_params = get_naming_params()
    query_step = naming_params["slidesChartTypeQuery"]
    if not should_use_batch(query_step):
        raise RuntimeError(
            f"Batch mode is required for {query_step}, but current runtime disabled it."
        )

    normalized = normalize_ocr_payload(ocr_payload, deck_id=deck.deck_id)
    slide_by_id = {slide.id: slide for slide in deck.slides}

    prompts: list[dict[str, object]] = []
    references: list[tuple[str, int, dict[str, object]]] = []
    for slide_payload in normalized.get("slides", []):
        if not isinstance(slide_payload, dict):
            continue
        slide_id = str(slide_payload.get("slide_id") or "")
        if not slide_id:
            continue
        slide = slide_by_id.get(slide_id)
        if slide is None:
            continue
        image_path = _extract_slide_image_path(deck, deck_path, slide)
        if image_path is None:
            continue
        title_text = str(slide_payload.get("title_text") or "").strip()
        ocr_text = str(slide_payload.get("ocr_text") or "").strip()
        figure_regions = (
            slide_payload.get("figure_regions")
            if isinstance(slide_payload.get("figure_regions"), list)
            else []
        )
        for region_index, region in enumerate(figure_regions):
            bbox = _coerce_bbox(region)
            if bbox is None:
                continue
            try:
                image_data_url = _crop_region_to_data_url(image_path, bbox)
            except (UnidentifiedImageError, OSError, ValueError) as exc:
                LOGGER.warning(
                    "Chart type classifier skipped crop for slide %s region %s: %s",
                    slide_id,
                    region_index,
                    exc,
                )
                continue
            prompt_text = (
                "Classify this chart crop.\n"
                f"Slide title: {title_text or 'n/a'}\n"
                f"OCR text excerpt: {ocr_text[:500] or 'n/a'}"
            )
            prompts.append(
                {
                    "user_content": [
                        {"type": "input_text", "text": prompt_text},
                        {"type": "input_image", "image_url": image_data_url},
                    ]
                }
            )
            references.append((slide_id, region_index, region))

    if not prompts:
        return {}

    responses = run_step_json(
        llm_wrapper,
        query_step,
        _SYSTEM_PROMPT,
        prompts,
        retry_missing=1,
    )

    by_slide: dict[str, list[dict[str, object]]] = {}
    for idx, (slide_id, region_index, region) in enumerate(references):
        response = responses[idx] if idx < len(responses) else {}
        chart_type = "unknown"
        confidence = None
        if isinstance(response, dict):
            chart_type = _coerce_chart_type(
                response.get("chartType")
                or response.get("chart_type")
                or response.get("type")
            )
            confidence = _coerce_confidence(response.get("confidence"))
        by_slide.setdefault(slide_id, []).append(
            {
                "region_index": region_index,
                "bbox": region,
                "chart_type": chart_type,
                "confidence": confidence,
            }
        )

    for slide_id in by_slide:
        by_slide[slide_id] = sorted(
            by_slide[slide_id], key=lambda item: int(item["region_index"])
        )

    return by_slide
