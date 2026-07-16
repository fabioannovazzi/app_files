from __future__ import annotations

from typing import Mapping

from src.slides.launch_brief import validate_launch_brief_payload

__all__ = [
    "build_launch_brief_from_category_insights",
    "validate_category_insights_payload",
]


def validate_category_insights_payload(
    payload: Mapping[str, object],
) -> dict[str, object]:
    """Validate and normalize a model-authored category insights payload."""

    thesis = _read_text(payload.get("thesis"))
    summary = _read_text_or_list(payload.get("summary"))
    evidence_examples = _read_mapping_list(
        payload.get("evidenceExamples")
        if payload.get("evidenceExamples") is not None
        else payload.get("evidence_examples")
    )
    surviving_signals = _read_text_list(
        payload.get("survivingSignals")
        if payload.get("survivingSignals") is not None
        else payload.get("surviving_signals")
    )
    dropped_signals = _read_text_list(
        payload.get("droppedSignals")
        if payload.get("droppedSignals") is not None
        else payload.get("dropped_signals")
    )
    caveats = _read_text_list(payload.get("caveats"))

    if not thesis:
        raise ValueError("Category insights must include a non-empty 'thesis'.")
    if not summary:
        raise ValueError("Category insights must include a non-empty 'summary'.")
    if len(evidence_examples) < 2:
        raise ValueError(
            "Category insights must include at least two 'evidenceExamples'."
        )
    for index, example in enumerate(evidence_examples, start=1):
        if not _read_text(example.get("product") or example.get("title")):
            raise ValueError(
                f"Category insights evidence example {index} is missing a product/title."
            )
    if not surviving_signals:
        raise ValueError(
            "Category insights must include at least one surviving signal."
        )
    if not dropped_signals and not caveats:
        raise ValueError(
            "Category insights must include at least one dropped signal or caveat."
        )

    return dict(payload)


def build_launch_brief_from_category_insights(
    payload: Mapping[str, object],
) -> dict[str, object]:
    """Compile category insights into the launch brief contract."""

    validated_payload = validate_category_insights_payload(payload)
    slide_titles = _read_mapping(
        validated_payload.get("slideTitles")
        if validated_payload.get("slideTitles") is not None
        else validated_payload.get("slide_titles")
    )
    surviving_signals = _read_text_list(
        validated_payload.get("survivingSignals")
        if validated_payload.get("survivingSignals") is not None
        else validated_payload.get("surviving_signals")
    )
    dropped_signals = _read_text_list(
        validated_payload.get("droppedSignals")
        if validated_payload.get("droppedSignals") is not None
        else validated_payload.get("dropped_signals")
    )
    caveats = _read_text_list(validated_payload.get("caveats"))
    right_column_items = dropped_signals or caveats
    right_column_heading = (
        _read_text(validated_payload.get("droppedLabel"))
        or _read_text(validated_payload.get("dropped_label"))
        or ("Failed" if dropped_signals else "Needs caution")
    )

    deck_name = (
        _read_text(validated_payload.get("deckName"))
        or _read_text(validated_payload.get("deck_name"))
        or _default_deck_name(validated_payload)
    )
    bottom_line = (
        _read_text(validated_payload.get("bottomLine"))
        or _read_text(validated_payload.get("bottom_line"))
        or _read_text(validated_payload.get("implication"))
        or _read_text(validated_payload.get("thesis"))
    )
    evidence_intro = (
        _read_text(validated_payload.get("evidenceIntro"))
        or _read_text(validated_payload.get("evidence_intro"))
        or "Illustrative launches grounding the current read."
    )
    footer_text = (
        _read_text(validated_payload.get("footerText"))
        or _read_text(validated_payload.get("footer_text"))
        or _default_footer_text(validated_payload)
    )
    callout_title = (
        _read_text(validated_payload.get("calloutTitle"))
        or _read_text(validated_payload.get("callout_title"))
        or "Bottom line"
    )
    template_key = (
        _read_text(validated_payload.get("templateKey"))
        or _read_text(validated_payload.get("template_key"))
        or "uniform"
    )
    prompt_style = (
        _read_text(validated_payload.get("promptStyle"))
        or _read_text(validated_payload.get("prompt_style"))
        or "uniform"
    )

    brief_payload = {
        "version": "launch_brief/1",
        "deckName": deck_name,
        "templateKey": template_key,
        "promptStyle": prompt_style,
        "slides": [
            {
                "role": "cover",
                "title": _read_text(validated_payload.get("thesis")),
                "body": _read_body_list(validated_payload.get("summary")),
                "footerText": footer_text,
            },
            {
                "role": "launch_tiles",
                "title": _read_text(slide_titles.get("evidence"))
                or "Illustrative launches",
                "body": evidence_intro,
                "implication": _normalize_implication(bottom_line),
                "products": [
                    _compile_product_example(example)
                    for example in _read_mapping_list(
                        validated_payload.get("evidenceExamples")
                        if validated_payload.get("evidenceExamples") is not None
                        else validated_payload.get("evidence_examples")
                    )
                ],
            },
            {
                "role": "comparison",
                "title": _read_text(slide_titles.get("comparison"))
                or "What survived vs what failed",
                "body": bottom_line,
                "left": {
                    "heading": _read_text(validated_payload.get("survivingLabel"))
                    or _read_text(validated_payload.get("surviving_label"))
                    or "Survived",
                    "items": surviving_signals,
                },
                "right": {
                    "heading": right_column_heading,
                    "items": right_column_items,
                },
                "calloutTitle": callout_title,
                "calloutBody": bottom_line,
            },
        ],
    }
    return validate_launch_brief_payload(brief_payload)


def _compile_product_example(example: Mapping[str, object]) -> dict[str, object]:
    payload: dict[str, object] = {
        "brand": _read_text(example.get("brand")),
        "product": _read_text(example.get("product") or example.get("title")),
        "body": _read_text(
            example.get("body") or example.get("note") or example.get("whyItMatters")
        ),
        "tags": _read_text_list(example.get("tags")),
    }
    badge = _read_text(example.get("badge") or example.get("label"))
    if badge:
        payload["badge"] = badge
    return payload


def _default_deck_name(payload: Mapping[str, object]) -> str:
    retailer = _read_text(payload.get("retailer"))
    category = _read_text(payload.get("category"))
    parts = [part for part in (retailer, category, "launch report") if part]
    return " ".join(parts) or "launch-report"


def _default_footer_text(payload: Mapping[str, object]) -> str:
    retailer = _read_text(payload.get("retailer"))
    category = _read_text(payload.get("category"))
    window = _read_text(
        payload.get("observationWindow")
        if payload.get("observationWindow") is not None
        else payload.get("observation_window")
    )
    parts = [part for part in (retailer, category, window) if part]
    return " | ".join(parts)


def _normalize_implication(text: str) -> str:
    normalized = text.strip()
    if not normalized:
        return ""
    if normalized.lower().startswith("implication:"):
        return normalized
    return f"Implication: {normalized}"


def _read_text(value: object) -> str:
    return str(value or "").strip()


def _read_text_list(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    return [text for text in (_read_text(item) for item in value) if text]


def _read_body_list(value: object) -> list[str]:
    if isinstance(value, list):
        return _read_text_list(value)
    text = _read_text(value)
    return [text] if text else []


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
