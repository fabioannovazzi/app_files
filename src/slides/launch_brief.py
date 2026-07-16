from __future__ import annotations

from typing import Mapping

from src.slides.launch_report_ast import validate_launch_report_payload

__all__ = [
    "build_report_payload_from_launch_brief",
    "validate_launch_brief_payload",
]

_ALLOWED_BRIEF_ROLES = {
    "cover",
    "launch_tiles",
    "comparison",
}


def validate_launch_brief_payload(
    payload: Mapping[str, object],
) -> dict[str, object]:
    """Validate and normalize a model-authored launch brief payload."""

    slides = payload.get("slides")
    if not isinstance(slides, list) or not slides:
        raise ValueError("Launch brief must include a non-empty 'slides' list.")

    normalized_payload = dict(payload)
    normalized_slides: list[dict[str, object]] = []
    for index, slide in enumerate(slides, start=1):
        if not isinstance(slide, Mapping):
            raise ValueError(f"Brief slide {index} must be a JSON object.")
        normalized_slides.append(_validate_brief_slide(index=index, slide=slide))
    normalized_payload["slides"] = normalized_slides
    return normalized_payload


def build_report_payload_from_launch_brief(
    payload: Mapping[str, object],
) -> dict[str, object]:
    """Compile a validated launch brief into the richer report payload."""

    validated_payload = validate_launch_brief_payload(payload)
    compiled_slides = [
        _compile_brief_slide(slide)
        for slide in validated_payload["slides"]
        if isinstance(slide, Mapping)
    ]
    report_payload = {
        "deckName": str(
            validated_payload.get("deckName")
            or validated_payload.get("deck_name")
            or validated_payload.get("title")
            or "launch-report"
        ).strip(),
        "templateKey": str(
            validated_payload.get("templateKey")
            or validated_payload.get("template_key")
            or "uniform"
        ).strip()
        or "uniform",
        "promptStyle": str(
            validated_payload.get("promptStyle")
            or validated_payload.get("prompt_style")
            or "uniform"
        ).strip()
        or "uniform",
        "slides": compiled_slides,
    }
    return validate_launch_report_payload(report_payload)


def _validate_brief_slide(
    *, index: int, slide: Mapping[str, object]
) -> dict[str, object]:
    normalized_slide = dict(slide)
    role = _read_text(slide.get("role")).lower()
    title = _read_text(slide.get("title"))
    body = _read_text_or_list(slide.get("body"))

    if role not in _ALLOWED_BRIEF_ROLES:
        raise ValueError(f"Brief slide {index} uses unsupported role '{role}'.")
    if not title:
        raise ValueError(f"Brief slide {index} is missing a title.")

    if role == "cover":
        if not body:
            raise ValueError(f"Brief slide {index} cover role requires body text.")
        return normalized_slide

    if role == "launch_tiles":
        products = _read_mapping_list(slide.get("products"))
        if len(products) < 2:
            raise ValueError(
                f"Brief slide {index} launch_tiles role requires at least two products."
            )
        for product_index, product in enumerate(products, start=1):
            if not _read_text(product.get("product")):
                raise ValueError(
                    f"Brief slide {index} product {product_index} is missing a product name."
                )
        if not body:
            raise ValueError(
                f"Brief slide {index} launch_tiles role requires body text."
            )
        return normalized_slide

    if role == "comparison":
        left = _read_mapping(slide.get("left"))
        right = _read_mapping(slide.get("right"))
        if not _read_text(left.get("heading")) or not _read_text_list(
            left.get("items")
        ):
            raise ValueError(
                f"Brief slide {index} comparison role requires a populated left column."
            )
        if not _read_text(right.get("heading")) or not _read_text_list(
            right.get("items")
        ):
            raise ValueError(
                f"Brief slide {index} comparison role requires a populated right column."
            )
        if not body:
            raise ValueError(f"Brief slide {index} comparison role requires body text.")
        return normalized_slide

    return normalized_slide


def _compile_brief_slide(slide: Mapping[str, object]) -> dict[str, object]:
    role = _read_text(slide.get("role")).lower()
    slide_id = _read_text(slide.get("slideId") or slide.get("slide_id"))
    title = _read_text(slide.get("title"))
    body = _read_text_or_list(slide.get("body"))
    base_payload: dict[str, object] = {
        "slideId": slide_id or "",
        "title": title,
    }

    if role == "cover":
        base_payload["body"] = body
        footer_text = _read_text(slide.get("footerText") or slide.get("footer_text"))
        if footer_text:
            base_payload["footerText"] = footer_text
        return base_payload

    if role == "launch_tiles":
        base_payload["layoutVariant"] = "text_visual_bottom"
        base_payload["body"] = body
        implication = _read_text(slide.get("implication"))
        if implication:
            base_payload["implication"] = implication
        base_payload["nativeVisual"] = {
            "kind": "launch_product_tiles",
            "tiles": [
                _compile_brief_product(product)
                for product in _read_mapping_list(slide.get("products"))
            ],
        }
        return base_payload

    left = _read_mapping(slide.get("left"))
    right = _read_mapping(slide.get("right"))
    base_payload["body"] = body
    base_payload["comparisonColumns"] = [
        {
            "title": _read_text(left.get("heading")),
            "items": _read_text_list(left.get("items")),
        },
        {
            "title": _read_text(right.get("heading")),
            "items": _read_text_list(right.get("items")),
        },
    ]
    callout_title = _read_text(slide.get("calloutTitle") or slide.get("callout_title"))
    callout_body = _read_text(slide.get("calloutBody") or slide.get("callout_body"))
    if callout_title:
        base_payload["calloutTitle"] = callout_title
    if callout_body:
        base_payload["calloutBody"] = callout_body
    return base_payload


def _compile_brief_product(product: Mapping[str, object]) -> dict[str, object]:
    payload: dict[str, object] = {
        "brand": _read_text(product.get("brand")),
        "product": _read_text(product.get("product")),
        "body": _read_text(product.get("body") or product.get("note")),
        "tags": _read_text_list(product.get("tags")),
    }
    badge = _read_text(product.get("badge"))
    if badge:
        payload["badge"] = badge
    accent_raw = (
        product.get("accentRgb")
        if isinstance(product.get("accentRgb"), list)
        else product.get("accent_rgb")
    )
    if isinstance(accent_raw, list) and len(accent_raw) >= 3:
        payload["accentRgb"] = [int(value) for value in accent_raw[:3]]
    return payload


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
