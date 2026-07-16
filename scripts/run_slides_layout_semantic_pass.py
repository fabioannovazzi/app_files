from __future__ import annotations

import argparse
import logging
import sys
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path
from typing import Iterator

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import modules.llm.model_router as model_router
import modules.utilities.config as config_module
from modules.slides.api import _build_slide_analysis_payload, _normalize_layout_payload
from src.slides.layout_semantics import normalize_block_type
from src.slides.layout_service import build_deck_layout_payload
from src.slides.ocr_payload import normalize_ocr_payload
from src.slides.ocr_service import build_deck_ocr_payload
from src.slides.storage import DeckStorage

LOGGER = logging.getLogger(__name__)
_SLIDE_ROOT = Path("slide_decks")


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Rerun the realistic slide-processing subset pipeline on selected slides: "
            "raw layout, VLM semantic layout correction, OCR, and merged slide analysis. "
            "When no explicit slides are provided, the script selects slides whose current "
            "layout payload still contains unknown blocks."
        )
    )
    parser.add_argument("--deck-id", required=True, help="Deck identifier")
    parser.add_argument("--lang", default="eng", help="Language code (default: eng)")
    parser.add_argument(
        "--page-number",
        action="append",
        dest="page_numbers",
        type=int,
        default=[],
        help="Specific page number to update. Repeat to pass multiple pages.",
    )
    parser.add_argument(
        "--slide-id",
        action="append",
        dest="slide_ids",
        default=[],
        help="Specific slide id to update. Repeat to pass multiple slides.",
    )
    return parser.parse_args()


def _selected_slide_ids_from_args(
    deck,
    *,
    page_numbers: list[int],
    slide_ids: list[str],
) -> list[str]:
    selected_ids = {str(slide_id).strip() for slide_id in slide_ids if str(slide_id).strip()}
    page_set = {int(page_number) for page_number in page_numbers if int(page_number) >= 1}
    if page_set:
        for index, slide in enumerate(deck.slides, start=1):
            if index in page_set:
                selected_ids.add(slide.id)
    return [slide.id for slide in deck.slides if slide.id in selected_ids]


def _slide_id_from_payload(raw_slide: dict[str, object]) -> str:
    return str(raw_slide.get("slide_id") or raw_slide.get("slideId") or "").strip()


def _slide_has_unknown_block(raw_slide: dict[str, object]) -> bool:
    raw_blocks = raw_slide.get("blocks") if isinstance(raw_slide.get("blocks"), list) else []
    return any(
        isinstance(raw_block, dict)
        and normalize_block_type(raw_block.get("type")) == "unknown"
        for raw_block in raw_blocks
    )


def _select_unknown_slide_ids(deck, existing_layout: dict[str, object]) -> list[str]:
    raw_slides = (
        existing_layout.get("slides")
        if isinstance(existing_layout.get("slides"), list)
        else []
    )
    unknown_ids = {
        _slide_id_from_payload(raw_slide)
        for raw_slide in raw_slides
        if isinstance(raw_slide, dict)
        and _slide_id_from_payload(raw_slide)
        and _slide_has_unknown_block(raw_slide)
    }
    return [slide.id for slide in deck.slides if slide.id in unknown_ids]


def _resolve_selected_slide_ids(
    deck,
    *,
    existing_layout: dict[str, object] | None,
    page_numbers: list[int],
    slide_ids: list[str],
) -> list[str]:
    explicit_selection = _selected_slide_ids_from_args(
        deck,
        page_numbers=page_numbers,
        slide_ids=slide_ids,
    )
    if explicit_selection:
        return explicit_selection
    if not isinstance(existing_layout, dict):
        raise RuntimeError(
            "layout.json is required to auto-select slides with unknown blocks."
        )
    return _select_unknown_slide_ids(deck, existing_layout)


def _merge_layout_payload(
    *,
    deck,
    existing_payload: dict[str, object] | None,
    updated_payload: dict[str, object],
    lang: str,
) -> dict[str, object]:
    existing_slides = (
        existing_payload.get("slides")
        if isinstance(existing_payload, dict) and isinstance(existing_payload.get("slides"), list)
        else []
    )
    updated_slides = (
        updated_payload.get("slides")
        if isinstance(updated_payload.get("slides"), list)
        else []
    )
    merged_by_id: dict[str, dict[str, object]] = {
        _slide_id_from_payload(raw_slide): raw_slide
        for raw_slide in existing_slides
        if isinstance(raw_slide, dict) and _slide_id_from_payload(raw_slide)
    }
    for raw_slide in updated_slides:
        if not isinstance(raw_slide, dict):
            continue
        slide_id = _slide_id_from_payload(raw_slide)
        if not slide_id:
            continue
        merged_by_id[slide_id] = raw_slide
    ordered_slides = [
        merged_by_id[slide.id]
        for slide in deck.slides
        if slide.id in merged_by_id
    ]
    return _normalize_layout_payload(
        {
            "deck_id": deck.deck_id,
            "lang": lang,
            "generated_at": datetime.now(UTC).isoformat(),
            "slides": ordered_slides,
        },
        deck_id=deck.deck_id,
        lang=lang,
    )


def _merge_ocr_payload(
    *,
    deck,
    existing_payload: dict[str, object] | None,
    updated_payload: dict[str, object],
    lang: str,
) -> dict[str, object]:
    existing_slides = (
        existing_payload.get("slides")
        if isinstance(existing_payload, dict) and isinstance(existing_payload.get("slides"), list)
        else []
    )
    updated_slides = (
        updated_payload.get("slides")
        if isinstance(updated_payload.get("slides"), list)
        else []
    )
    merged_by_id: dict[str, dict[str, object]] = {
        _slide_id_from_payload(raw_slide): raw_slide
        for raw_slide in existing_slides
        if isinstance(raw_slide, dict) and _slide_id_from_payload(raw_slide)
    }
    for raw_slide in updated_slides:
        if not isinstance(raw_slide, dict):
            continue
        slide_id = _slide_id_from_payload(raw_slide)
        if not slide_id:
            continue
        merged_by_id[slide_id] = raw_slide
    ordered_slides = [
        merged_by_id[slide.id]
        for slide in deck.slides
        if slide.id in merged_by_id
    ]
    resolved_ocr_strategy = (
        updated_payload.get("ocr_strategy")
        or updated_payload.get("ocrStrategy")
        or (
            existing_payload.get("ocr_strategy") or existing_payload.get("ocrStrategy")
            if isinstance(existing_payload, dict)
            else None
        )
    )
    resolved_prompt_style = (
        updated_payload.get("prompt_style")
        or updated_payload.get("promptStyle")
        or (
            existing_payload.get("prompt_style") or existing_payload.get("promptStyle")
            if isinstance(existing_payload, dict)
            else None
        )
    )
    resolved_style_hint = (
        updated_payload.get("style_hint")
        or updated_payload.get("styleHint")
        or (
            existing_payload.get("style_hint") or existing_payload.get("styleHint")
            if isinstance(existing_payload, dict)
            else None
        )
    )
    return normalize_ocr_payload(
        {
            "deck_id": deck.deck_id,
            "lang": lang,
            "ocr_strategy": resolved_ocr_strategy,
            "prompt_style": resolved_prompt_style,
            "style_hint": resolved_style_hint,
            "generated_at": datetime.now(UTC).isoformat(),
            "slides": ordered_slides,
        },
        deck_id=deck.deck_id,
        lang=lang,
    )


@contextmanager
def _batch_mode_enabled() -> Iterator[None]:
    original_config_get_run_params = config_module.get_run_params
    original_model_router_get_run_params = model_router.get_run_params

    def _patched_get_run_params() -> dict[str, object]:
        params = original_config_get_run_params()
        params["llmBatchMode"] = True
        return params

    config_module.get_run_params = _patched_get_run_params  # type: ignore[assignment]
    model_router.get_run_params = _patched_get_run_params  # type: ignore[assignment]
    try:
        yield
    finally:
        config_module.get_run_params = original_config_get_run_params  # type: ignore[assignment]
        model_router.get_run_params = original_model_router_get_run_params  # type: ignore[assignment]


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    args = _parse_args()

    storage = DeckStorage(_SLIDE_ROOT)
    deck = storage.load_deck(args.deck_id)
    deck_path = (storage.root / args.deck_id).resolve()
    existing_layout = storage.load_layout_payload(args.deck_id)
    if not isinstance(existing_layout, dict):
        raise RuntimeError(
            f"Deck {args.deck_id} does not have an existing layout.json to update realistically."
        )
    selected_slide_ids = _resolve_selected_slide_ids(
        deck,
        existing_layout=existing_layout,
        page_numbers=args.page_numbers,
        slide_ids=args.slide_ids,
    )
    if not selected_slide_ids:
        LOGGER.info("No matching slides found for deck %s.", args.deck_id)
        return 0

    LOGGER.info(
        "Running realistic subset slide-processing pipeline for deck %s on %s slide(s).",
        args.deck_id,
        len(selected_slide_ids),
    )
    LOGGER.info("Selected slides: %s", ", ".join(selected_slide_ids))

    selected_ids = set(selected_slide_ids)
    with _batch_mode_enabled():
        LOGGER.info("Step 1/3: rerunning raw layout + VLM semantic layout correction.")
        updated_layout_subset = build_deck_layout_payload(
            deck,
            deck_path,
            lang=args.lang,
            slide_ids=selected_ids,
        )
        LOGGER.info("Step 2/3: rerunning OCR and downstream OCR-local LLM/VLM steps.")
        updated_ocr_subset = build_deck_ocr_payload(
            deck,
            deck_path,
            lang=args.lang,
            include_bboxes=True,
            layout_payload=updated_layout_subset,
        )

    merged_layout = _merge_layout_payload(
        deck=deck,
        existing_payload=existing_layout,
        updated_payload=updated_layout_subset,
        lang=args.lang,
    )
    storage.save_layout_payload(args.deck_id, merged_layout)
    merged_ocr = _merge_ocr_payload(
        deck=deck,
        existing_payload=storage.load_ocr_payload(args.deck_id),
        updated_payload=updated_ocr_subset,
        lang=args.lang,
    )
    storage.save_ocr_payload(args.deck_id, merged_ocr)
    LOGGER.info("Step 3/3: rebuilding merged slide analysis.")
    merged_analysis = _build_slide_analysis_payload(
        merged_layout,
        merged_ocr,
        deck_id=args.deck_id,
        lang=args.lang,
    )
    if merged_analysis is not None:
        storage.save_slide_analysis_payload(args.deck_id, merged_analysis)

    updated_layout_ids = [
        _slide_id_from_payload(raw_slide)
        for raw_slide in (
            updated_layout_subset.get("slides")
            if isinstance(updated_layout_subset.get("slides"), list)
            else []
        )
        if isinstance(raw_slide, dict) and _slide_id_from_payload(raw_slide)
    ]
    LOGGER.info(
        "Updated %s slide(s): %s",
        len(updated_layout_ids),
        ", ".join(updated_layout_ids),
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
