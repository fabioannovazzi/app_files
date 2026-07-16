from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping, Sequence

import polars as pl

LOGGER = logging.getLogger(__name__)

APP_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_EXPLICIT_RULES_PATH = (
    APP_ROOT / "config" / "pdp_explicit_declaration_rules.json"
)
DEFAULT_ACTIVATION_DEFAULTS = {
    "min_reviewed_samples": 30,
    "min_precision": 0.98,
    "broad_pattern_requires_justification": True,
}
PLACEHOLDER_VALUES = {
    "",
    "n/a",
    "na",
    "none",
    "unknown",
    "n/a (not stated)",
    "not stated",
}


@dataclass(frozen=True)
class _CompiledSignal:
    rule_id: str
    value_label: str
    include_pattern: re.Pattern[str]
    exclude_patterns: tuple[re.Pattern[str], ...]
    required_path_tokens: tuple[str, ...]
    priority: int


ExplicitEvidence = dict[str, Any]
ExplicitEvidenceMap = dict[tuple[Any, ...], dict[str, ExplicitEvidence]]


__all__ = [
    "DEFAULT_ACTIVATION_DEFAULTS",
    "DEFAULT_EXPLICIT_RULES_PATH",
    "collect_explicit_declaration_rule_taxonomy_impacts",
    "load_explicit_declaration_rules",
    "validate_explicit_declaration_rules",
    "classify_explicit_declarations",
    "classify_explicit_declarations_with_evidence",
]


def _normalize_key(value: object | None) -> str:
    if value is None:
        return ""
    text = str(value).strip().lower()
    if not text:
        return ""
    return "_".join(text.split())


def _extract_leaf_labels(nodes: Sequence[Mapping[str, object]] | None) -> list[str]:
    labels: list[str] = []
    if not nodes:
        return labels
    for node in nodes:
        children = node.get("children")
        if isinstance(children, Sequence) and not isinstance(
            children, (str, bytes, bytearray)
        ):
            labels.extend(_extract_leaf_labels(children))  # type: ignore[arg-type]
            continue
        label = str(node.get("label") or "").strip()
        if label:
            labels.append(label)
    return labels


def _leaf_status(node: Mapping[str, object]) -> str:
    node_id = _normalize_key(node.get("id"))
    if node_id in {"unknown", "other"}:
        return "active"
    status = str(node.get("status") or "active").strip().lower()
    return status or "active"


def _taxonomy_value_lookup(
    taxonomy: Mapping[str, object],
) -> dict[str, dict[str, dict[str, dict[str, str]]]]:
    lookup: dict[str, dict[str, dict[str, dict[str, str]]]] = {}
    for category in taxonomy.get("categories", []) or []:
        if not isinstance(category, Mapping):
            continue
        category_keys = {
            _normalize_key(category.get("id")),
            _normalize_key(category.get("label")),
        }
        category_keys.discard("")
        if not category_keys:
            continue
        attr_map: dict[str, dict[str, str]] = {}
        for attr in category.get("attributes", []) or []:
            if not isinstance(attr, Mapping):
                continue
            attr_keys = {
                _normalize_key(attr.get("id")),
                _normalize_key(attr.get("label")),
            }
            attr_keys.discard("")
            if not attr_keys:
                continue
            labels = _extract_leaf_labels(attr.get("nodes"))
            value_lookup: dict[str, dict[str, str]] = {}
            for node in attr.get("nodes", []) or []:
                if not isinstance(node, Mapping):
                    continue
                children = node.get("children")
                if isinstance(children, Sequence) and not isinstance(
                    children, (str, bytes, bytearray)
                ):
                    for child in children:
                        if not isinstance(child, Mapping):
                            continue
                        label = str(child.get("label") or "").strip()
                        if not label:
                            continue
                        value_lookup[_normalize_key(label)] = {
                            "label": label,
                            "status": _leaf_status(child),
                        }
                    continue
                label = str(node.get("label") or "").strip()
                if not label:
                    continue
                value_lookup[_normalize_key(label)] = {
                    "label": label,
                    "status": _leaf_status(node),
                }
            for label in labels:
                normalized_label = _normalize_key(label)
                if normalized_label not in value_lookup and label:
                    value_lookup[normalized_label] = {
                        "label": label,
                        "status": "active",
                    }
            if not value_lookup:
                continue
            for attr_key in attr_keys:
                attr_map[attr_key] = value_lookup
        if not attr_map:
            continue
        for category_key in category_keys:
            lookup[category_key] = attr_map
    return lookup


def _compile_pattern(
    *,
    match_type: str,
    pattern: str,
    case_sensitive: bool,
    word_boundary: bool,
) -> re.Pattern[str]:
    if match_type == "regex":
        flags = 0 if case_sensitive else re.IGNORECASE
        return re.compile(pattern, flags=flags)
    escaped = re.escape(pattern)
    if word_boundary:
        escaped = rf"(?<!\w){escaped}(?!\w)"
    flags = 0 if case_sensitive else re.IGNORECASE
    return re.compile(escaped, flags=flags)


def _is_broad_pattern(match_type: str, pattern: str) -> bool:
    tokens = re.findall(r"[a-z0-9]+", pattern.casefold())
    if match_type == "regex":
        return len(tokens) <= 1
    return len(tokens) <= 1


def load_explicit_declaration_rules(
    path: Path | None = None,
) -> dict[str, Any]:
    config_path = path or DEFAULT_EXPLICIT_RULES_PATH
    if not config_path.is_file():
        return _apply_default_activation_policy(
            {
                "version": "0.0.0",
                "updated_at": "",
                "categories": {},
                "metadata": {},
            }
        )
    try:
        with config_path.open(encoding="utf-8") as handle:
            loaded = json.load(handle)
    except json.JSONDecodeError as exc:
        raise ValueError(
            f"Invalid explicit declaration rules JSON at {config_path}"
        ) from exc
    if not isinstance(loaded, dict):
        raise ValueError("Explicit declaration rules must be a JSON object.")
    return _apply_default_activation_policy(loaded)


def _apply_default_activation_policy(
    rules: Mapping[str, object],
) -> dict[str, Any]:
    normalized = dict(rules)
    metadata_raw = normalized.get("metadata")
    metadata = dict(metadata_raw) if isinstance(metadata_raw, Mapping) else {}
    activation_raw = metadata.get("activation_defaults")
    activation = dict(activation_raw) if isinstance(activation_raw, Mapping) else {}

    min_samples = activation.get("min_reviewed_samples")
    if not isinstance(min_samples, int) or min_samples < 1:
        activation["min_reviewed_samples"] = DEFAULT_ACTIVATION_DEFAULTS[
            "min_reviewed_samples"
        ]
    min_precision = activation.get("min_precision")
    if not isinstance(min_precision, (int, float)) or not (0 <= min_precision <= 1):
        activation["min_precision"] = DEFAULT_ACTIVATION_DEFAULTS["min_precision"]
    requires_justification = activation.get("broad_pattern_requires_justification")
    if not isinstance(requires_justification, bool):
        activation["broad_pattern_requires_justification"] = (
            DEFAULT_ACTIVATION_DEFAULTS["broad_pattern_requires_justification"]
        )

    metadata["activation_defaults"] = activation
    normalized["metadata"] = metadata
    return normalized


def validate_explicit_declaration_rules(
    rules: Mapping[str, object],
    taxonomy: Mapping[str, object],
) -> None:
    required_top = {"version", "updated_at", "categories", "metadata"}
    missing = [key for key in required_top if key not in rules]
    if missing:
        raise ValueError(f"Explicit declaration rules missing keys: {missing}")
    categories_obj = rules.get("categories")
    if not isinstance(categories_obj, Mapping):
        raise ValueError("'categories' must be an object.")

    taxonomy_lookup = _taxonomy_value_lookup(taxonomy)
    seen_rule_ids: set[str] = set()
    seen_signatures: dict[tuple[str, str, str], str] = {}
    metadata_obj = rules.get("metadata")
    metadata = dict(metadata_obj) if isinstance(metadata_obj, Mapping) else {}
    defaults_obj = metadata.get("activation_defaults")
    defaults = (
        dict(defaults_obj)
        if isinstance(defaults_obj, Mapping)
        else dict(DEFAULT_ACTIVATION_DEFAULTS)
    )
    min_reviewed_samples = defaults.get("min_reviewed_samples")
    if (
        not isinstance(min_reviewed_samples, int)
        or min_reviewed_samples < 1
    ):
        min_reviewed_samples = DEFAULT_ACTIVATION_DEFAULTS["min_reviewed_samples"]
    min_precision = defaults.get("min_precision")
    if not isinstance(min_precision, (int, float)) or not (0 <= min_precision <= 1):
        min_precision = DEFAULT_ACTIVATION_DEFAULTS["min_precision"]
    requires_justification = defaults.get("broad_pattern_requires_justification")
    if not isinstance(requires_justification, bool):
        requires_justification = DEFAULT_ACTIVATION_DEFAULTS[
            "broad_pattern_requires_justification"
        ]

    for category_key, category_payload in categories_obj.items():
        normalized_category = _normalize_key(category_key)
        if normalized_category not in taxonomy_lookup:
            raise ValueError(
                f"Unknown category '{category_key}' in explicit declaration rules."
            )
        if not isinstance(category_payload, Mapping):
            raise ValueError(f"Category '{category_key}' must be an object.")
        attributes_obj = category_payload.get("attributes")
        if not isinstance(attributes_obj, Mapping):
            raise ValueError(
                f"Category '{category_key}' must include an 'attributes' object."
            )

        for attribute_key, attribute_payload in attributes_obj.items():
            normalized_attribute = _normalize_key(attribute_key)
            category_attributes = taxonomy_lookup[normalized_category]
            if normalized_attribute not in category_attributes:
                raise ValueError(
                    f"Unknown attribute '{attribute_key}' for category '{category_key}'."
                )
            if not isinstance(attribute_payload, Mapping):
                raise ValueError(
                    f"Attribute '{attribute_key}' in category '{category_key}' must be an object."
                )
            values_obj = attribute_payload.get("values")
            if not isinstance(values_obj, Mapping):
                raise ValueError(
                    f"Attribute '{attribute_key}' in category '{category_key}' must include a 'values' object."
                )

            taxonomy_values = category_attributes[normalized_attribute]
            for value_key, value_payload in values_obj.items():
                if not isinstance(value_payload, Mapping):
                    raise ValueError(
                        f"Value '{value_key}' for {category_key}/{attribute_key} must be an object."
                    )
                normalized_value = _normalize_key(value_key)
                if normalized_value not in taxonomy_values:
                    raise ValueError(
                        "Unknown canonical value "
                        f"'{value_key}' for {category_key}/{attribute_key}."
                    )
                taxonomy_value = taxonomy_values[normalized_value]
                if taxonomy_value.get("status") != "active":
                    raise ValueError(
                        "Canonical value "
                        f"'{value_key}' for {category_key}/{attribute_key} is not active."
                    )
                signals = value_payload.get("certainty_signals")
                if not isinstance(signals, Sequence) or isinstance(
                    signals, (str, bytes)
                ):
                    raise ValueError(
                        f"'certainty_signals' for {category_key}/{attribute_key}/{value_key} must be a list."
                    )

                for signal in signals:
                    if not isinstance(signal, Mapping):
                        raise ValueError(
                            "Each certainty signal must be an object "
                            f"({category_key}/{attribute_key}/{value_key})."
                        )
                    rule_id = str(signal.get("rule_id") or "").strip()
                    if not rule_id:
                        raise ValueError(
                            f"Missing rule_id in {category_key}/{attribute_key}/{value_key}."
                        )
                    if rule_id in seen_rule_ids:
                        raise ValueError(f"Duplicate rule_id '{rule_id}'.")
                    seen_rule_ids.add(rule_id)

                    status = str(signal.get("status") or "active").strip().lower()
                    if status not in {"active", "inactive"}:
                        raise ValueError(
                            f"Invalid status '{status}' for rule '{rule_id}'."
                        )

                    match_type = str(signal.get("type") or "").strip().lower()
                    if match_type not in {"phrase", "regex"}:
                        raise ValueError(
                            f"Invalid type '{match_type}' for rule '{rule_id}'."
                        )
                    pattern = str(signal.get("pattern") or "").strip()
                    if not pattern:
                        raise ValueError(f"Empty pattern for rule '{rule_id}'.")

                    case_sensitive = bool(signal.get("case_sensitive", False))
                    word_boundary = bool(signal.get("word_boundary", True))
                    try:
                        _compile_pattern(
                            match_type=match_type,
                            pattern=pattern,
                            case_sensitive=case_sensitive,
                            word_boundary=word_boundary,
                        )
                    except re.error as exc:
                        raise ValueError(
                            f"Invalid regex/pattern for rule '{rule_id}': {exc}"
                        ) from exc

                    if status == "active":
                        reviewed_samples = signal.get("reviewed_samples")
                        if (
                            not isinstance(reviewed_samples, int)
                            or reviewed_samples < min_reviewed_samples
                        ):
                            raise ValueError(
                                "Active rule "
                                f"'{rule_id}' must include reviewed_samples >= "
                                f"{min_reviewed_samples}."
                            )
                        observed_precision = signal.get("observed_precision")
                        if (
                            not isinstance(observed_precision, (int, float))
                            or observed_precision < min_precision
                        ):
                            raise ValueError(
                                "Active rule "
                                f"'{rule_id}' must include observed_precision >= "
                                f"{float(min_precision):.2f}."
                            )
                        if (
                            requires_justification
                            and _is_broad_pattern(match_type, pattern)
                        ):
                            reviewer_justification = str(
                                signal.get("reviewer_justification") or ""
                            ).strip()
                            if not reviewer_justification:
                                raise ValueError(
                                    f"Broad active rule '{rule_id}' requires reviewer_justification."
                                )

                    exclude_patterns = signal.get("exclude_patterns", [])
                    if not isinstance(exclude_patterns, Sequence) or isinstance(
                        exclude_patterns, (str, bytes)
                    ):
                        raise ValueError(
                            f"exclude_patterns must be a list for rule '{rule_id}'."
                        )
                    for exclude_pattern in exclude_patterns:
                        exclude_text = str(exclude_pattern).strip()
                        if not exclude_text:
                            continue
                        try:
                            _compile_pattern(
                                match_type=match_type,
                                pattern=exclude_text,
                                case_sensitive=case_sensitive,
                                word_boundary=word_boundary,
                            )
                        except re.error as exc:
                            raise ValueError(
                                f"Invalid exclude pattern for rule '{rule_id}': {exc}"
                            ) from exc

                    signature = (
                        normalized_category,
                        normalized_attribute,
                        _normalize_key(pattern),
                    )
                    previous_value = seen_signatures.get(signature)
                    if previous_value and previous_value != normalized_value:
                        raise ValueError(
                            "Conflicting certainty signal pattern "
                            f"'{pattern}' for {category_key}/{attribute_key}: "
                            f"{previous_value} vs {normalized_value}."
                        )
                    seen_signatures[signature] = normalized_value


def collect_explicit_declaration_rule_taxonomy_impacts(
    rules: Mapping[str, object],
    taxonomy: Mapping[str, object],
) -> list[dict[str, Any]]:
    """Collect explicit rules whose taxonomy target is missing or non-active."""

    impacts: list[dict[str, Any]] = []
    categories_obj = rules.get("categories")
    if not isinstance(categories_obj, Mapping):
        return impacts

    taxonomy_lookup = _taxonomy_value_lookup(taxonomy)
    for category_key, category_payload in categories_obj.items():
        if not isinstance(category_payload, Mapping):
            continue
        normalized_category = _normalize_key(category_key)
        attributes_obj = category_payload.get("attributes")
        if not isinstance(attributes_obj, Mapping):
            continue

        for attribute_key, attribute_payload in attributes_obj.items():
            if not isinstance(attribute_payload, Mapping):
                continue
            normalized_attribute = _normalize_key(attribute_key)
            values_obj = attribute_payload.get("values")
            if not isinstance(values_obj, Mapping):
                continue

            for value_key, value_payload in values_obj.items():
                if not isinstance(value_payload, Mapping):
                    continue
                normalized_value = _normalize_key(value_key)
                signals = value_payload.get("certainty_signals")
                if not isinstance(signals, Sequence) or isinstance(
                    signals, (str, bytes)
                ):
                    continue

                impact_reason = ""
                taxonomy_status = ""
                if normalized_category not in taxonomy_lookup:
                    impact_reason = "unknown_category"
                else:
                    category_values = taxonomy_lookup[normalized_category]
                    if normalized_attribute not in category_values:
                        impact_reason = "unknown_attribute"
                    else:
                        value_lookup = category_values[normalized_attribute]
                        if normalized_value not in value_lookup:
                            impact_reason = "unknown_canonical_value"
                        else:
                            taxonomy_status = str(
                                value_lookup[normalized_value].get("status") or ""
                            ).strip().lower()
                            if taxonomy_status != "active":
                                impact_reason = "inactive_canonical_value"

                if not impact_reason:
                    continue

                for signal in signals:
                    if not isinstance(signal, Mapping):
                        continue
                    impacts.append(
                        {
                            "rule_id": str(signal.get("rule_id") or "").strip(),
                            "signal_status": str(signal.get("status") or "active")
                            .strip()
                            .lower(),
                            "category_key": normalized_category,
                            "attribute_id": normalized_attribute,
                            "value_key": normalized_value,
                            "value_label": str(value_key).strip(),
                            "reason": impact_reason,
                            "taxonomy_status": taxonomy_status or None,
                        }
                    )

    return sorted(
        impacts,
        key=lambda item: (
            str(item.get("category_key") or ""),
            str(item.get("attribute_id") or ""),
            str(item.get("value_key") or ""),
            str(item.get("rule_id") or ""),
        ),
    )


def _compile_signals(
    rules: Mapping[str, object],
    taxonomy: Mapping[str, object],
) -> dict[str, dict[str, dict[str, list[_CompiledSignal]]]]:
    validate_explicit_declaration_rules(rules, taxonomy)
    taxonomy_lookup = _taxonomy_value_lookup(taxonomy)
    compiled: dict[str, dict[str, dict[str, list[_CompiledSignal]]]] = {}
    categories_obj = rules.get("categories", {})
    if not isinstance(categories_obj, Mapping):
        return compiled

    for category_key, category_payload in categories_obj.items():
        if not isinstance(category_payload, Mapping):
            continue
        normalized_category = _normalize_key(category_key)
        if normalized_category not in taxonomy_lookup:
            continue
        attributes_obj = category_payload.get("attributes")
        if not isinstance(attributes_obj, Mapping):
            continue
        for attribute_key, attribute_payload in attributes_obj.items():
            if not isinstance(attribute_payload, Mapping):
                continue
            normalized_attribute = _normalize_key(attribute_key)
            values_obj = attribute_payload.get("values")
            if not isinstance(values_obj, Mapping):
                continue
            for value_key, value_payload in values_obj.items():
                if not isinstance(value_payload, Mapping):
                    continue
                signals = value_payload.get("certainty_signals")
                if not isinstance(signals, Sequence) or isinstance(
                    signals, (str, bytes)
                ):
                    continue
                for signal in signals:
                    if not isinstance(signal, Mapping):
                        continue
                    status = str(signal.get("status") or "active").strip().lower()
                    if status != "active":
                        continue
                    rule_id = str(signal.get("rule_id") or "").strip()
                    match_type = str(signal.get("type") or "").strip().lower()
                    pattern = str(signal.get("pattern") or "").strip()
                    if (
                        not rule_id
                        or not pattern
                        or match_type not in {"phrase", "regex"}
                    ):
                        continue
                    case_sensitive = bool(signal.get("case_sensitive", False))
                    word_boundary = bool(signal.get("word_boundary", True))
                    include_pattern = _compile_pattern(
                        match_type=match_type,
                        pattern=pattern,
                        case_sensitive=case_sensitive,
                        word_boundary=word_boundary,
                    )
                    excludes_raw = signal.get("exclude_patterns", [])
                    exclude_patterns: list[re.Pattern[str]] = []
                    if isinstance(excludes_raw, Sequence) and not isinstance(
                        excludes_raw, (str, bytes)
                    ):
                        for exclude in excludes_raw:
                            exclude_text = str(exclude).strip()
                            if not exclude_text:
                                continue
                            exclude_patterns.append(
                                _compile_pattern(
                                    match_type=match_type,
                                    pattern=exclude_text,
                                    case_sensitive=case_sensitive,
                                    word_boundary=word_boundary,
                                )
                            )
                    required_raw = signal.get("required_path_tokens", [])
                    required_path_tokens: tuple[str, ...] = tuple()
                    if isinstance(required_raw, Sequence) and not isinstance(
                        required_raw, (str, bytes)
                    ):
                        required_path_tokens = tuple(
                            _normalize_key(item)
                            for item in required_raw
                            if _normalize_key(item)
                        )
                    priority_raw = signal.get("priority", 100)
                    try:
                        priority = int(priority_raw)
                    except (TypeError, ValueError):
                        priority = 100
                    canonical_value = taxonomy_lookup[normalized_category][
                        normalized_attribute
                    ][_normalize_key(value_key)]["label"]
                    compiled_signal = _CompiledSignal(
                        rule_id=rule_id,
                        value_label=canonical_value,
                        include_pattern=include_pattern,
                        exclude_patterns=tuple(exclude_patterns),
                        required_path_tokens=required_path_tokens,
                        priority=priority,
                    )
                    compiled.setdefault(normalized_category, {}).setdefault(
                        normalized_attribute, {}
                    ).setdefault(canonical_value, []).append(compiled_signal)

    for category_rules in compiled.values():
        for attribute_rules in category_rules.values():
            for value_key, signals in attribute_rules.items():
                attribute_rules[value_key] = sorted(
                    signals, key=lambda item: item.priority
                )
    return compiled


def _is_placeholder(value: object | None) -> bool:
    if value is None:
        return True
    text = str(value).strip().lower()
    return text in PLACEHOLDER_VALUES


def _signal_matches(
    signal: _CompiledSignal,
    segments: Sequence[tuple[str, str]],
) -> bool:
    for segment_path, segment_text in segments:
        normalized_path = _normalize_key(segment_path)
        if signal.required_path_tokens:
            if not any(
                token in normalized_path for token in signal.required_path_tokens
            ):
                continue
        if not signal.include_pattern.search(segment_text):
            continue
        if any(exclude.search(segment_text) for exclude in signal.exclude_patterns):
            continue
        return True
    return False


def _match_signal_evidence(
    signal: _CompiledSignal,
    segments: Sequence[tuple[str, str]],
) -> ExplicitEvidence | None:
    for segment_path, segment_text in segments:
        normalized_path = _normalize_key(segment_path)
        if signal.required_path_tokens and not any(
            token in normalized_path for token in signal.required_path_tokens
        ):
            continue
        match = signal.include_pattern.search(segment_text)
        if match is None:
            continue
        if any(exclude.search(segment_text) for exclude in signal.exclude_patterns):
            continue
        start = max(0, match.start() - 60)
        end = min(len(segment_text), match.end() + 60)
        snippet = re.sub(r"\s+", " ", segment_text[start:end]).strip()
        return {
            "rule_id": signal.rule_id,
            "segment": segment_path,
            "snippet": snippet,
        }
    return None


def classify_explicit_declarations_with_evidence(
    df: pl.DataFrame,
    *,
    key_columns: Sequence[str],
    category_column: str,
    text_columns: Sequence[str],
    attr_map: Mapping[str, Sequence[str]],
    taxonomy: Mapping[str, object],
    rules: Mapping[str, object],
) -> tuple[pl.DataFrame, ExplicitEvidenceMap]:
    if df.is_empty():
        return pl.DataFrame(), {}
    for key in key_columns:
        if key not in df.columns:
            raise ValueError(f"Missing key column '{key}' for explicit declarations.")
    if category_column not in df.columns:
        raise ValueError(
            f"Missing category column '{category_column}' for explicit declarations."
        )
    available_text_columns = [column for column in text_columns if column in df.columns]
    if not available_text_columns:
        return pl.DataFrame(), {}

    compiled = _compile_signals(rules, taxonomy)
    if not compiled:
        return pl.DataFrame(), {}

    records: list[dict[str, object]] = []
    evidence_map: ExplicitEvidenceMap = {}
    for row in df.to_dicts():
        category_key = _normalize_key(row.get(category_column))
        if not category_key:
            continue
        category_rules = compiled.get(category_key)
        if not category_rules:
            continue
        candidate_attrs = [str(attr).strip() for attr in attr_map.get(category_key, [])]
        if not candidate_attrs:
            continue
        segments: list[tuple[str, str]] = []
        for column in available_text_columns:
            value = row.get(column)
            if _is_placeholder(value):
                continue
            text = str(value).strip()
            if text:
                segments.append((column, text))
        if not segments:
            continue

        output: dict[str, object] = {key: row.get(key) for key in key_columns}
        row_key = tuple(row.get(key) for key in key_columns)
        row_evidence: dict[str, ExplicitEvidence] = {}
        matched_any_attribute = False
        for attribute_id in candidate_attrs:
            normalized_attribute = _normalize_key(attribute_id)
            value_rules = category_rules.get(normalized_attribute)
            if not value_rules:
                continue

            matched_by_value: dict[str, ExplicitEvidence] = {}
            for canonical_value, signals in value_rules.items():
                matched_evidence: ExplicitEvidence | None = None
                for signal in signals:
                    matched_evidence = _match_signal_evidence(signal, segments)
                    if matched_evidence is not None:
                        break
                if matched_evidence is not None:
                    matched_by_value[canonical_value] = matched_evidence

            if len(matched_by_value) == 1:
                matched_value, matched_evidence = next(iter(matched_by_value.items()))
                output[attribute_id] = matched_value
                row_evidence[attribute_id] = {
                    "decision": "matched",
                    "matched_value": matched_value,
                    **matched_evidence,
                }
            elif len(matched_by_value) > 1:
                output[attribute_id] = "N/A"
                row_evidence[attribute_id] = {
                    "decision": "conflict",
                    "conflict_values": sorted(matched_by_value.keys()),
                    "matches": matched_by_value,
                }
            else:
                output[attribute_id] = "N/A"
                row_evidence[attribute_id] = {"decision": "no_match"}
            matched_any_attribute = True
        if matched_any_attribute:
            records.append(output)
            if row_evidence:
                evidence_map[row_key] = row_evidence

    if not records:
        return pl.DataFrame(), {}
    return pl.DataFrame(records, strict=False, infer_schema_length=None), evidence_map


def classify_explicit_declarations(
    df: pl.DataFrame,
    *,
    key_columns: Sequence[str],
    category_column: str,
    text_columns: Sequence[str],
    attr_map: Mapping[str, Sequence[str]],
    taxonomy: Mapping[str, object],
    rules: Mapping[str, object],
) -> pl.DataFrame:
    classified, _ = classify_explicit_declarations_with_evidence(
        df,
        key_columns=key_columns,
        category_column=category_column,
        text_columns=text_columns,
        attr_map=attr_map,
        taxonomy=taxonomy,
        rules=rules,
    )
    return classified
