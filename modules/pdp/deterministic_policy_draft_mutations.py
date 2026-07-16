from __future__ import annotations

import copy
from typing import Any, Mapping

__all__ = [
    "APPLICABLE_DETERMINISTIC_POLICY_CANDIDATE_TYPES",
    "apply_deterministic_policy_queue_item",
]


APPLICABLE_DETERMINISTIC_POLICY_CANDIDATE_TYPES = frozenset(
    {"disable_bare_label", "block_bad_source", "add_deterministic_expression"}
)


def _normalize_key(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip().lower().replace(" ", "_")


def _normalize_text(value: Any) -> str:
    if value is None:
        return ""
    return " ".join(str(value).strip().lower().split())


def _normalize_list(values: Any) -> list[str]:
    cleaned: list[str] = []
    seen: set[str] = set()
    for value in values or []:
        normalized = _normalize_key(value)
        if not normalized or normalized in seen:
            continue
        cleaned.append(normalized)
        seen.add(normalized)
    return cleaned


def apply_deterministic_policy_queue_item(
    config: Mapping[str, Any],
    item: Mapping[str, Any],
    *,
    aggregated: Mapping[str, Any] | None = None,
) -> tuple[dict[str, Any], dict[str, Any]]:
    candidate_type = _normalize_key(item.get("candidate_type"))
    if candidate_type not in APPLICABLE_DETERMINISTIC_POLICY_CANDIDATE_TYPES:
        raise ValueError(
            "Draft apply currently supports only: "
            + ", ".join(sorted(APPLICABLE_DETERMINISTIC_POLICY_CANDIDATE_TYPES))
        )

    next_config = copy.deepcopy(dict(config))
    category_key = _normalize_key(item.get("category_key"))
    attribute_id = _normalize_key(item.get("attribute_id"))
    value_id = _normalize_key(item.get("value_id"))
    categories = next_config.get("categories") or {}
    if not isinstance(categories, dict):
        raise ValueError("Policy categories are missing from the base config.")
    category_block = categories.get(category_key)
    if not isinstance(category_block, dict):
        raise ValueError(f"{category_key} is missing from the deterministic policy.")
    attributes = category_block.get("attributes") or {}
    if not isinstance(attributes, dict):
        raise ValueError(f"{category_key}.attributes is missing from the deterministic policy.")
    attribute_block = attributes.get(attribute_id)
    if not isinstance(attribute_block, dict):
        raise ValueError(
            f"{category_key}/{attribute_id} is missing from the deterministic policy."
        )

    if candidate_type == "disable_bare_label":
        values = attribute_block.get("values") or {}
        if not isinstance(values, dict):
            raise ValueError(
                f"{category_key}/{attribute_id}.values is missing from the deterministic policy."
            )
        value_block = values.get(value_id)
        if not isinstance(value_block, dict):
            raise ValueError(
                f"{category_key}/{attribute_id}/{value_id} is missing from the deterministic policy."
            )
        if not bool(value_block.get("allow_label")):
            raise ValueError("This candidate no longer changes the current deterministic draft.")
        value_block["allow_label"] = False
        return next_config, {
            "candidate_type": candidate_type,
            "category_key": category_key,
            "attribute_id": attribute_id,
            "value_id": value_id,
            "change": "allow_label_disabled",
        }

    if candidate_type == "block_bad_source":
        source_channel = _normalize_key((aggregated or {}).get("source_channel"))
        if not source_channel:
            raise ValueError("The candidate is missing its source channel.")
        allowed_sources = _normalize_list(attribute_block.get("allowed_sources"))
        blocked_sources = _normalize_list(attribute_block.get("blocked_sources"))
        next_allowed = [value for value in allowed_sources if value != source_channel]
        next_blocked = _normalize_list([*blocked_sources, source_channel])
        if next_allowed == allowed_sources and next_blocked == blocked_sources:
            raise ValueError("This candidate no longer changes the current deterministic draft.")
        attribute_block["allowed_sources"] = next_allowed
        attribute_block["blocked_sources"] = next_blocked
        return next_config, {
            "candidate_type": candidate_type,
            "category_key": category_key,
            "attribute_id": attribute_id,
            "source_channel": source_channel,
            "change": "source_blocked",
        }

    if candidate_type == "add_deterministic_expression":
        evidence_summary = (aggregated or {}).get("evidence_summary_json") or {}
        phrase = _normalize_text(
            evidence_summary.get("phrase")
            if isinstance(evidence_summary, Mapping)
            else None
        )
        if not phrase:
            raise ValueError("The candidate is missing its phrase evidence.")
        values = attribute_block.get("values")
        if values is None:
            values = {}
            attribute_block["values"] = values
        if not isinstance(values, dict):
            raise ValueError(
                f"{category_key}/{attribute_id}.values is missing from the deterministic policy."
            )
        value_block = values.get(value_id)
        if value_block is None:
            value_block = {
                "allow_label": False,
                "deterministic_expressions": [],
                "required_context_any": [],
                "negative_patterns": [],
            }
            values[value_id] = value_block
        if not isinstance(value_block, dict):
            raise ValueError(
                f"{category_key}/{attribute_id}/{value_id} is invalid in the deterministic policy."
            )
        deterministic_expressions = _normalize_list(
            value_block.get("deterministic_expressions")
        )
        if phrase in deterministic_expressions:
            raise ValueError("This candidate no longer changes the current deterministic draft.")
        value_block["deterministic_expressions"] = [
            *deterministic_expressions,
            phrase,
        ]
        value_block.setdefault("allow_label", False)
        value_block.setdefault("required_context_any", [])
        value_block.setdefault("negative_patterns", [])
        return next_config, {
            "candidate_type": candidate_type,
            "category_key": category_key,
            "attribute_id": attribute_id,
            "value_id": value_id,
            "phrase": phrase,
            "change": "deterministic_expression_added",
        }

    raise ValueError(f"Unsupported candidate type: {candidate_type}")
