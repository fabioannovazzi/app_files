from __future__ import annotations

from typing import Mapping
from urllib.parse import urlparse

__all__ = ["validate_launch_report_payload"]

_ALLOWED_LAYOUT_VARIANTS = {
    "section_header_agenda",
    "cover_with_footer",
    "comparison_columns",
    "title_only_centered",
    "bullets_full_width",
    "text_full_width",
    "visual_full_width",
    "table_focus",
    "text_visual_right",
    "text_visual_bottom",
    "bullets_visual_right",
    "bullets_visual_bottom",
}
_ALLOWED_KINDS = {
    "",
    "section_header",
    "cover_with_footer",
    "comparison_columns",
    "title_only",
    "bullets_only",
    "text_only",
    "visual_only",
    "bullets_visual",
    "text_visual",
}
_ALLOWED_NATIVE_VISUAL_KINDS = {
    "cards_row",
    "launch_product_tiles",
}


def validate_launch_report_payload(
    payload: Mapping[str, object],
) -> dict[str, object]:
    """Validate and normalize a launch-report AST payload."""

    slides = payload.get("slides")
    if not isinstance(slides, list) or not slides:
        raise ValueError("Launch report payload must include a non-empty 'slides' list.")

    normalized_payload = dict(payload)
    normalized_slides: list[dict[str, object]] = []
    for index, slide in enumerate(slides, start=1):
        if not isinstance(slide, Mapping):
            raise ValueError(f"Slide {index} must be a JSON object.")
        normalized_slides.append(_validate_slide_payload(index=index, slide=slide))
    normalized_payload["slides"] = normalized_slides
    return normalized_payload


def _validate_slide_payload(
    *,
    index: int,
    slide: Mapping[str, object],
) -> dict[str, object]:
    normalized_slide = dict(slide)
    title = _read_text(slide.get("title"))
    body = _read_text_or_list(slide.get("body"))
    bullets = _read_text_list(slide.get("bullets"))
    footer_text = _read_text(slide.get("footerText") or slide.get("footer_text"))
    implication = _read_text(slide.get("implication") or slide.get("implicationText"))
    layout_variant = _read_text(
        slide.get("layoutVariant") or slide.get("layout_variant")
    )
    kind = _read_text(slide.get("kind"))
    visual_path = _read_text(slide.get("visualPath") or slide.get("visual_path"))
    comparison_columns = _read_mapping_list(
        slide.get("comparisonColumns")
        if slide.get("comparisonColumns") is not None
        else slide.get("comparison_columns")
    )
    native_visual = _read_mapping(
        slide.get("nativeVisual")
        if slide.get("nativeVisual") is not None
        else slide.get("native_visual")
    )

    if layout_variant and layout_variant not in _ALLOWED_LAYOUT_VARIANTS:
        raise ValueError(
            f"Slide {index} uses unsupported layoutVariant '{layout_variant}'."
        )
    if kind and kind not in _ALLOWED_KINDS:
        raise ValueError(f"Slide {index} uses unsupported kind '{kind}'.")
    if visual_path:
        _validate_relative_visual_path(index=index, visual_path=visual_path)
    if comparison_columns:
        _validate_comparison_columns(index=index, columns=comparison_columns)
    if native_visual:
        _validate_native_visual(index=index, native_visual=native_visual)
    if not any(
        (
            title,
            body,
            bullets,
            footer_text,
            implication,
            visual_path,
            comparison_columns,
            native_visual,
        )
    ):
        raise ValueError(
            f"Slide {index} must include at least one content field such as title, body, bullets, visual, or comparisonColumns."
        )
    return normalized_slide


def _validate_relative_visual_path(*, index: int, visual_path: str) -> None:
    parsed = urlparse(visual_path)
    if parsed.scheme or parsed.netloc:
        raise ValueError(
            f"Slide {index} visualPath must be a local relative path, not a URL."
        )
    if visual_path.startswith("/") or visual_path.startswith("\\"):
        raise ValueError(
            f"Slide {index} visualPath must be relative to the deck directory."
        )


def _validate_comparison_columns(
    *,
    index: int,
    columns: list[Mapping[str, object]],
) -> None:
    if len(columns) < 2:
        raise ValueError(
            f"Slide {index} comparisonColumns must include at least two columns."
        )
    for column_index, column in enumerate(columns, start=1):
        title = _read_text(column.get("title") or column.get("label"))
        items = _read_text_list(column.get("items"))
        if not title:
            raise ValueError(
                f"Slide {index} comparison column {column_index} is missing a title."
            )
        if not items:
            raise ValueError(
                f"Slide {index} comparison column {column_index} must include non-empty items."
            )


def _validate_native_visual(
    *,
    index: int,
    native_visual: Mapping[str, object],
) -> None:
    kind = _read_text(native_visual.get("kind"))
    if kind not in _ALLOWED_NATIVE_VISUAL_KINDS:
        raise ValueError(
            f"Slide {index} nativeVisual kind '{kind}' is not supported."
        )
    if kind == "cards_row":
        cards = _read_mapping_list(native_visual.get("cards"))
        if not cards:
            raise ValueError(
                f"Slide {index} nativeVisual cards_row must include at least one card."
            )
        for card_index, card in enumerate(cards, start=1):
            if not _read_text(card.get("title")):
                raise ValueError(
                    f"Slide {index} cards_row card {card_index} is missing a title."
                )
    if kind == "launch_product_tiles":
        tiles = _read_mapping_list(native_visual.get("tiles"))
        if len(tiles) < 2:
            raise ValueError(
                f"Slide {index} nativeVisual launch_product_tiles must include at least two tiles."
            )
        for tile_index, tile in enumerate(tiles, start=1):
            if not _read_text(tile.get("product") or tile.get("title")):
                raise ValueError(
                    f"Slide {index} launch_product_tiles tile {tile_index} is missing a product/title."
                )


def _read_text(value: object) -> str:
    return str(value or "").strip()


def _read_text_list(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    return [text for text in (_read_text(item) for item in value) if text]


def _read_text_or_list(value: object) -> str:
    if isinstance(value, list):
        return "\n\n".join(_read_text_list(value))
    return _read_text(value)


def _read_mapping(value: object) -> Mapping[str, object]:
    return value if isinstance(value, Mapping) else {}


def _read_mapping_list(value: object) -> list[Mapping[str, object]]:
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, Mapping)]
