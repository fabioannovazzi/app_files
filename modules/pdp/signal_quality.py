from __future__ import annotations

import json
import re
import unicodedata
from functools import lru_cache
from pathlib import Path
from typing import Any, Mapping, Sequence

APP_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_SIGNAL_QUALITY_CONFIG = APP_ROOT / "config" / "pdp_signal_quality.json"

__all__ = [
    "DEFAULT_SIGNAL_QUALITY_CONFIG",
    "category_has_signal_quality_rules",
    "component_is_category_center",
    "component_is_base_rate",
    "component_is_discriminating",
    "component_signal_role",
    "normalize_signal_components",
    "normalize_signal_text",
    "parse_signal_bundle_key",
    "signal_component_family",
    "signal_insight_metadata",
    "signal_quality_rules_for_category",
]


def normalize_signal_text(value: Any) -> str:
    """Return a lowercase ASCII-ish key for category signal matching."""

    if value is None:
        return ""
    text = str(value).strip()
    if not text:
        return ""
    text = unicodedata.normalize("NFKD", text)
    text = text.encode("ascii", "ignore").decode("ascii")
    text = text.replace("&", " and ").replace("_", " ")
    text = re.sub(r"[^a-zA-Z0-9]+", " ", text)
    return re.sub(r"\s+", " ", text).strip().casefold()


def signal_component_family(attribute: Any) -> str:
    """Normalize attribute-family aliases before signal quality rules run."""

    normalized = normalize_signal_text(attribute)
    aliases = {
        "applicator type": "form",
        "benefits": "benefits",
        "benefits claims": "benefits",
        "buildable coverage": "coverage",
        "color family": "color",
        "color lips": "color",
        "color payoff": "coverage",
        "ethical claims": "claims",
        "ethical regulatory claims": "claims",
        "finish effect": "finish",
        "format": "form",
        "key benefits": "benefits",
        "preference": "claims",
        "product type": "form",
        "regulatory claims": "claims",
        "shade family": "color",
    }
    return aliases.get(normalized, normalized)


def _normalize_component_value_map(raw: Any) -> dict[str, set[str]]:
    if not isinstance(raw, Mapping):
        return {}
    out: dict[str, set[str]] = {}
    for attribute, values in raw.items():
        family = signal_component_family(attribute)
        if isinstance(values, str):
            raw_values = [values]
        elif isinstance(values, Sequence):
            raw_values = list(values)
        else:
            raw_values = []
        normalized_values = {
            normalized_value
            for value in raw_values
            if (normalized_value := normalize_signal_text(value))
        }
        if normalized_values:
            out[family] = normalized_values
    return out


def _normalize_attribute_set(raw: Any) -> set[str]:
    if isinstance(raw, str):
        values = [raw]
    elif isinstance(raw, Sequence):
        values = list(raw)
    else:
        values = []
    return {family for value in values if (family := signal_component_family(value))}


@lru_cache(maxsize=8)
def _load_signal_quality_config(config_path: str | None = None) -> dict[str, Any]:
    path = Path(config_path) if config_path else DEFAULT_SIGNAL_QUALITY_CONFIG
    if not path.exists():
        return {}
    payload = json.loads(path.read_text(encoding="utf-8"))
    return payload if isinstance(payload, dict) else {}


def _category_aliases(category_key: str, rules: Mapping[str, Any]) -> set[str]:
    aliases = {normalize_signal_text(category_key)}
    aliases.add(normalize_signal_text(category_key).replace(" ", "_"))
    raw_aliases = rules.get("aliases", [])
    if isinstance(raw_aliases, str):
        raw_aliases = [raw_aliases]
    if isinstance(raw_aliases, Sequence):
        for alias in raw_aliases:
            normalized = normalize_signal_text(alias)
            if normalized:
                aliases.add(normalized)
                aliases.add(normalized.replace(" ", "_"))
    return aliases


def signal_quality_rules_for_category(
    category_key: Any,
    *,
    config_path: str | None = None,
) -> Mapping[str, Any]:
    """Return signal-quality rules for one category, or an empty mapping."""

    normalized = normalize_signal_text(category_key)
    if not normalized:
        return {}
    category_candidates = {normalized, normalized.replace(" ", "_")}
    categories = _load_signal_quality_config(config_path).get("categories", {})
    if not isinstance(categories, Mapping):
        return {}
    for configured_key, rules in categories.items():
        if not isinstance(rules, Mapping):
            continue
        configured_aliases = _category_aliases(str(configured_key), rules)
        if category_candidates & configured_aliases:
            return rules
    return {}


def category_has_signal_quality_rules(
    category_key: Any,
    *,
    config_path: str | None = None,
) -> bool:
    return bool(
        signal_quality_rules_for_category(category_key, config_path=config_path)
    )


def parse_signal_bundle_key(bundle_key: Any) -> tuple[tuple[str, str], ...]:
    """Parse a `family=value + family=value` bundle key into normalized components."""

    text = str(bundle_key).strip() if bundle_key is not None else ""
    if not text:
        return ()
    components: list[tuple[str, str]] = []
    seen: set[tuple[str, str]] = set()
    for segment in text.split(" + "):
        attribute, separator, value = segment.partition("=")
        if separator != "=":
            continue
        family = signal_component_family(attribute)
        normalized_value = normalize_signal_text(value)
        if not family or not normalized_value:
            continue
        component = (family, normalized_value)
        if component in seen:
            continue
        seen.add(component)
        components.append(component)
    return tuple(sorted(components, key=lambda item: (item[0], item[1])))


def normalize_signal_components(
    components: Sequence[Mapping[str, Any] | Sequence[Any]],
) -> tuple[tuple[str, str], ...]:
    """Normalize component mappings or `(attribute, value)` pairs."""

    normalized: list[tuple[str, str]] = []
    seen: set[tuple[str, str]] = set()
    for component in components:
        if isinstance(component, Mapping):
            attribute = component.get("attribute")
            value = component.get("value")
        elif len(component) >= 2:
            attribute = component[0]
            value = component[1]
        else:
            continue
        family = signal_component_family(attribute)
        normalized_value = normalize_signal_text(value)
        if not family or not normalized_value:
            continue
        key = (family, normalized_value)
        if key in seen:
            continue
        seen.add(key)
        normalized.append(key)
    return tuple(sorted(normalized, key=lambda item: (item[0], item[1])))


def component_is_base_rate(
    category_key: Any,
    component: Mapping[str, Any] | Sequence[Any],
    *,
    config_path: str | None = None,
) -> bool:
    rules = signal_quality_rules_for_category(category_key, config_path=config_path)
    normalized = normalize_signal_components([component])
    if not rules or not normalized:
        return False
    family, value = normalized[0]
    category_center_values = _normalize_component_value_map(
        rules.get("category_center_component_values")
        or rules.get("base_rate_component_values")
    )
    return value in category_center_values.get(family, set())


def component_is_category_center(
    category_key: Any,
    component: Mapping[str, Any] | Sequence[Any],
    *,
    config_path: str | None = None,
) -> bool:
    """Return whether a component describes the broad category center."""

    return component_is_base_rate(
        category_key,
        component,
        config_path=config_path,
    )


def component_is_discriminating(
    category_key: Any,
    component: Mapping[str, Any] | Sequence[Any],
    *,
    config_path: str | None = None,
) -> bool:
    rules = signal_quality_rules_for_category(category_key, config_path=config_path)
    normalized = normalize_signal_components([component])
    if not rules or not normalized:
        return False
    family, value = normalized[0]
    if component_is_category_center(
        category_key,
        component,
        config_path=config_path,
    ):
        return False
    discriminating_values = _normalize_component_value_map(
        rules.get("discriminating_component_values")
    )
    if value in discriminating_values.get(family, set()):
        return True
    non_base_discriminating_attributes = _normalize_attribute_set(
        rules.get("non_base_value_discriminating_attributes")
    )
    if family in non_base_discriminating_attributes:
        return True
    discriminating_attributes = _normalize_attribute_set(
        rules.get("discriminating_attributes")
    )
    return family in discriminating_attributes


def component_signal_role(
    category_key: Any,
    component: Mapping[str, Any] | Sequence[Any],
    *,
    config_path: str | None = None,
) -> str:
    """Classify one component as category-center, differentiating, or unclassified."""

    if component_is_category_center(
        category_key,
        component,
        config_path=config_path,
    ):
        return "category_center"
    if component_is_discriminating(
        category_key,
        component,
        config_path=config_path,
    ):
        return "differentiating"
    return "unclassified"


def _safe_float(value: Any, default: float) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _safe_int(value: Any, default: int) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def signal_insight_metadata(
    *,
    category_key: Any,
    components: Sequence[Mapping[str, Any] | Sequence[Any]],
    base_score: float,
    signal_layers: Sequence[str],
    layer_bonus_by_layer: Mapping[str, float] | None = None,
    combined_layer_bonus: float = 8.0,
    config_path: str | None = None,
) -> dict[str, Any]:
    """Return usefulness labels and adjusted score for one category signal."""

    rules = signal_quality_rules_for_category(category_key, config_path=config_path)
    normalized_components = normalize_signal_components(components)
    if not rules:
        return {
            "signal_usefulness": "selected_signal",
            "signal_role": "unclassified_signal",
            "discriminating_component_count": None,
            "category_center_component_count": None,
            "base_rate_component_count": None,
            "insight_adjusted_signal_score": round(base_score, 6),
            "signal_quality_note": None,
            "signal_role_note": None,
        }

    category_center_count = sum(
        1
        for component in normalized_components
        if component_is_category_center(
            category_key,
            component,
            config_path=config_path,
        )
    )
    discriminating_count = sum(
        1
        for component in normalized_components
        if component_is_discriminating(
            category_key,
            component,
            config_path=config_path,
        )
    )
    if discriminating_count == 0:
        multiplier = _safe_float(
            rules.get("category_center_score_multiplier")
            or rules.get("base_rate_score_multiplier"),
            0.05,
        )
        note = rules.get("category_center_context_note") or rules.get(
            "base_rate_context_note"
        )
        return {
            "signal_usefulness": "base_rate_context",
            "signal_role": "category_center",
            "discriminating_component_count": discriminating_count,
            "category_center_component_count": category_center_count,
            "base_rate_component_count": category_center_count,
            "insight_adjusted_signal_score": round(base_score * multiplier, 6),
            "signal_quality_note": note,
            "signal_role_note": note,
        }

    bonuses = dict(layer_bonus_by_layer or {"innovation": 8.0})
    normalized_layers = [
        normalize_signal_text(layer).replace(" ", "_") for layer in signal_layers
    ]
    layer_bonus = sum(bonuses.get(layer, 0.0) for layer in normalized_layers)
    if len(set(normalized_layers)) > 1:
        layer_bonus += combined_layer_bonus
    discriminating_multiplier = _safe_float(
        rules.get("discriminating_score_multiplier"), 0.18
    )
    category_center_penalty = _safe_float(
        rules.get("category_center_component_penalty")
        or rules.get("base_rate_component_penalty"),
        12.0,
    )
    adjusted = (
        base_score * (1.0 + discriminating_multiplier * discriminating_count)
        + layer_bonus
        - category_center_penalty * category_center_count
    )
    headline_min = _safe_int(rules.get("headline_min_discriminating_components"), 2)
    usefulness = (
        "headline_signal"
        if discriminating_count >= headline_min
        else "supporting_signal"
    )
    signal_role = (
        "differentiating"
        if discriminating_count >= headline_min
        else "supporting_differentiation"
    )
    note = rules.get("differentiating_signal_note") or rules.get("selected_signal_note")
    return {
        "signal_usefulness": usefulness,
        "signal_role": signal_role,
        "discriminating_component_count": discriminating_count,
        "category_center_component_count": category_center_count,
        "base_rate_component_count": category_center_count,
        "insight_adjusted_signal_score": round(adjusted, 6),
        "signal_quality_note": note,
        "signal_role_note": note,
    }
