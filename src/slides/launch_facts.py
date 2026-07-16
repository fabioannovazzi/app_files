from __future__ import annotations

from typing import Mapping

__all__ = ["validate_launch_facts_payload"]


def validate_launch_facts_payload(
    payload: Mapping[str, object],
) -> dict[str, object]:
    """Validate and normalize the upstream facts contract for launch analysis."""

    retailer = _read_text(payload.get("retailer"))
    category = _read_text(payload.get("category"))
    question = _read_text(payload.get("question") or payload.get("objective"))
    summary_metrics = _read_mapping_list(
        payload.get("summaryMetrics")
        if payload.get("summaryMetrics") is not None
        else payload.get("summary_metrics")
    )
    attribute_signals = _read_mapping_list(
        payload.get("attributeSignals")
        if payload.get("attributeSignals") is not None
        else payload.get("attribute_signals")
    )
    launch_examples = _read_mapping_list(
        payload.get("launchExamples")
        if payload.get("launchExamples") is not None
        else payload.get("launch_examples")
    )

    if not retailer:
        raise ValueError("Launch facts must include a non-empty 'retailer'.")
    if not category:
        raise ValueError("Launch facts must include a non-empty 'category'.")
    if not question:
        raise ValueError("Launch facts must include a non-empty 'question'.")
    if not (summary_metrics or attribute_signals or launch_examples):
        raise ValueError(
            "Launch facts must include summary metrics, attribute signals, or launch examples."
        )

    for index, metric in enumerate(summary_metrics, start=1):
        if not _read_text(metric.get("label")):
            raise ValueError(f"Launch facts summary metric {index} is missing a label.")
        if not _read_text(metric.get("value")):
            raise ValueError(f"Launch facts summary metric {index} is missing a value.")
    for index, signal in enumerate(attribute_signals, start=1):
        if not _read_text(signal.get("attribute")):
            raise ValueError(
                f"Launch facts attribute signal {index} is missing an attribute."
            )
        if not (
            _read_text(signal.get("finding"))
            or _read_text(signal.get("summary"))
            or _read_text(signal.get("verdict"))
        ):
            raise ValueError(
                f"Launch facts attribute signal {index} is missing a finding."
            )
    for index, example in enumerate(launch_examples, start=1):
        if not _read_text(example.get("product") or example.get("title")):
            raise ValueError(
                f"Launch facts launch example {index} is missing a product/title."
            )

    return dict(payload)


def _read_text(value: object) -> str:
    return str(value or "").strip()


def _read_mapping_list(value: object) -> list[Mapping[str, object]]:
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, Mapping)]
