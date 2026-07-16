"""Mechanical policy for scenario labels and resolved period context."""

from __future__ import annotations

import re
from typing import Any, Mapping

from .period_contract import (
    ACTUAL_LABELS,
    BUDGET_LABELS,
    COMPARISON_CURRENT_LABELS,
    COMPARISON_PREVIOUS_LABELS,
    FORECAST_LABELS,
    PLAN_LABELS,
    normalize_scenario_label,
)

__all__ = [
    "has_resolved_period_context",
    "is_scenario_label",
    "looks_like_resolved_period_label",
    "period_label_policy_texts",
    "scenario_tokens_from_text",
    "validate_period_label_policy",
]

_SCENARIO_LABELS = (
    ACTUAL_LABELS
    | BUDGET_LABELS
    | COMPARISON_CURRENT_LABELS
    | COMPARISON_PREVIOUS_LABELS
    | FORECAST_LABELS
    | PLAN_LABELS
)
_GENERIC_PERIOD_LABELS = {
    "all",
    "allperiods",
    "baseline",
    "comparison",
    "current",
    "currentperiod",
    "period",
    "periodone",
    "periodzero",
    "previous",
    "prior",
}
_MONTH_PATTERN = (
    r"jan(?:uary)?|feb(?:ruary)?|mar(?:ch)?|apr(?:il)?|may|jun(?:e)?|"
    r"jul(?:y)?|aug(?:ust)?|sep(?:tember)?|oct(?:ober)?|nov(?:ember)?|"
    r"dec(?:ember)?"
)
_PERIOD_PATTERNS = (
    re.compile(r"\b\d{4}-\d{2}(?:-\d{2})?\b"),
    re.compile(r"[’']\d{2}-\d{2}\b"),
    re.compile(r"\bFY\d{2,4}\b", re.IGNORECASE),
    re.compile(r"\b(?:\d{4}Q[1-4]|Q[1-4]\s*\d{4})\b", re.IGNORECASE),
    re.compile(rf"\b(?:{_MONTH_PATTERN})[-\s_/]*\d{{2,4}}\b", re.IGNORECASE),
    re.compile(rf"[~_](?:{_MONTH_PATTERN})[-\s_/]*\d{{2,4}}\b", re.IGNORECASE),
    re.compile(r"\b(?:rolling|prior_year|previous)_\d+[mdw]_", re.IGNORECASE),
)
_TOKEN_PATTERN = re.compile(r"[A-Za-z0-9]+")
_PAIR_PATTERN = re.compile(
    r"(?P<left>[A-Za-z0-9’'~_.-]+)\s+(?:to|vs|versus)\s+"
    r"(?P<right>[A-Za-z0-9’'~_.-]+)",
    re.IGNORECASE,
)


def is_scenario_label(value: Any) -> bool:
    """Return whether ``value`` is an exact scenario/comparison label."""

    text = str(value or "").strip()
    return bool(text) and normalize_scenario_label(text) in _SCENARIO_LABELS


def scenario_tokens_from_text(value: Any) -> list[str]:
    """Return exact scenario tokens present in display text."""

    tokens: list[str] = []
    for match in _TOKEN_PATTERN.findall(str(value or "")):
        if is_scenario_label(match) and match not in tokens:
            tokens.append(match)
    return tokens


def looks_like_resolved_period_label(value: Any) -> bool:
    """Return whether text looks like a concrete period/window label."""

    text = _clean_text(value)
    if not text:
        return False
    normalized = normalize_scenario_label(text)
    if normalized in _SCENARIO_LABELS or normalized in _GENERIC_PERIOD_LABELS:
        return False
    if any(pattern.search(text) for pattern in _PERIOD_PATTERNS):
        return True
    if re.search(r"\b\d{4}\b", text) and re.search(
        r"\b(?:YTD|year to date|through|ending|calendar|fiscal)\b",
        text,
        flags=re.IGNORECASE,
    ):
        return True
    return False


def period_label_policy_texts(context: Mapping[str, Any]) -> list[str]:
    """Return display fields where period/scenario labels are expected."""

    texts: list[str] = []
    title_contract = context.get("title_contract")
    if isinstance(title_contract, Mapping):
        _append_text(texts, title_contract.get("when"))
    title_lines = context.get("chart_title_lines")
    if isinstance(title_lines, list) and title_lines:
        _append_text(texts, title_lines[-1])
    if not texts:
        _append_text(texts, context.get("chart_title"))
        _append_text(texts, context.get("title"))
    comparison = context.get("comparison")
    if isinstance(comparison, Mapping):
        for key in (
            "baseline_period",
            "comparison_period",
            "previous_period",
            "current_period",
            "baseline_label",
            "comparison_label",
            "previous_label",
            "current_label",
        ):
            _append_text(texts, comparison.get(key))
    for value in _selected_period_values(context):
        _append_text(texts, value)
    return texts


def has_resolved_period_context(context: Mapping[str, Any]) -> bool:
    """Return whether context contains a concrete period/window reference."""

    if _mapping_has_resolved_period(context.get("period_window")):
        return True
    options = context.get("options")
    if isinstance(options, Mapping) and _mapping_has_resolved_period(
        options.get("period_window")
    ):
        return True
    if _mapping_has_resolved_period(context.get("period_adapter")):
        return True
    if _mapping_has_resolved_period(context.get("comparison")):
        return True
    for value in _selected_period_values(context):
        if looks_like_resolved_period_label(value):
            return True
    periods = context.get("periods")
    if isinstance(periods, list) and any(
        looks_like_resolved_period_label(value) for value in periods
    ):
        return True
    scenarios_by_period = context.get("scenarios_by_period")
    if isinstance(scenarios_by_period, Mapping) and any(
        looks_like_resolved_period_label(key) for key in scenarios_by_period
    ):
        return True
    return any(
        looks_like_resolved_period_label(text)
        for text in period_label_policy_texts(context)
    )


def validate_period_label_policy(context: Mapping[str, Any]) -> dict[str, Any]:
    """Validate that scenario labels are backed by concrete period evidence."""

    texts = period_label_policy_texts(context)
    selected_periods = _selected_period_values(context)
    display_texts = [text for text in texts if text not in selected_periods]
    scenario_tokens = _dedupe(
        token for text in texts for token in scenario_tokens_from_text(text)
    )
    resolved = has_resolved_period_context(context)
    issues: list[dict[str, Any]] = []

    same_period_line = _same_period_comparison_line(texts)
    if same_period_line:
        issues.append(
            {
                "code": "same_period_comparison_label",
                "detail": "A period/scenario comparison uses the same label on both sides.",
                "text": same_period_line,
            }
        )
    if _has_bare_actual_label(display_texts, selected_periods) and not resolved:
        issues.append(
            {
                "code": "bare_actual_without_period_context",
                "detail": "A single AC/actual label is not a resolved period.",
            }
        )
    if _scenario_only_selection(selected_periods) and not resolved:
        issues.append(
            {
                "code": "scenario_periods_without_resolved_period_context",
                "detail": "Selected periods contain only scenario labels.",
                "selected_periods": selected_periods,
            }
        )
    if scenario_tokens and not resolved:
        issues.append(
            {
                "code": "scenario_labels_without_resolved_period_context",
                "detail": "Scenario labels require a resolved period/window.",
                "scenario_tokens": scenario_tokens,
            }
        )

    status = "period_label_policy_not_applicable"
    if issues:
        status = "period_label_policy_failed"
    elif scenario_tokens or selected_periods or resolved:
        status = "period_label_policy_ok"
    return {
        "status": status,
        "issues": issues,
        "scenario_tokens": scenario_tokens,
        "selected_periods": selected_periods,
        "resolved_period_context": resolved,
        "checked_texts": texts,
    }


def _append_text(values: list[str], value: Any) -> None:
    text = _clean_text(value)
    if text and text not in values:
        values.append(text)


def _clean_text(value: Any) -> str:
    return re.sub(r"<[^>]+>", "", str(value or "")).strip()


def _selected_period_values(context: Mapping[str, Any]) -> list[str]:
    values: list[str] = []
    for source in (context, context.get("period_adapter")):
        if not isinstance(source, Mapping):
            continue
        selected = source.get("selected_periods")
        if not isinstance(selected, list):
            continue
        for value in selected:
            text = _clean_text(value)
            if text and text not in values:
                values.append(text)
    return values


def _mapping_has_resolved_period(value: Any) -> bool:
    if not isinstance(value, Mapping):
        return False
    for key in (
        "display_label",
        "period_label",
        "period",
        "start_date",
        "end_date",
        "source_min_date",
        "source_max_date",
        "date",
    ):
        if looks_like_resolved_period_label(value.get(key)):
            return True
        if key in {"start_date", "end_date", "source_min_date", "source_max_date"}:
            date_value = _clean_text(value.get(key))
            if re.fullmatch(r"\d{4}-\d{2}(?:-\d{2})?", date_value):
                return True
    for key in ("selected_periods", "available_periods", "input_periods"):
        nested_values = value.get(key)
        if isinstance(nested_values, list) and any(
            looks_like_resolved_period_label(item) for item in nested_values
        ):
            return True
    for nested in value.values():
        if isinstance(nested, Mapping) and _mapping_has_resolved_period(nested):
            return True
    return False


def _scenario_only_selection(selected_periods: list[str]) -> bool:
    return bool(selected_periods) and all(
        is_scenario_label(value) for value in selected_periods
    )


def _has_bare_actual_label(texts: list[str], selected_periods: list[str]) -> bool:
    if (
        len(selected_periods) == 1
        and normalize_scenario_label(selected_periods[0]) in ACTUAL_LABELS
    ):
        return True
    return any(normalize_scenario_label(text) in ACTUAL_LABELS for text in texts)


def _same_period_comparison_line(texts: list[str]) -> str | None:
    for text in texts:
        for match in _PAIR_PATTERN.finditer(text):
            left = _comparison_side_label(match.group("left"))
            right = _comparison_side_label(match.group("right"))
            if left and right and left == right:
                return text
    return None


def _comparison_side_label(value: str) -> str:
    return normalize_scenario_label(value.strip(" |,;:()[]{}"))


def _dedupe(values: Any) -> list[Any]:
    result: list[Any] = []
    for value in values:
        if value not in result:
            result.append(value)
    return result
