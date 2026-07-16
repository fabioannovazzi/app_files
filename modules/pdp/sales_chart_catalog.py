from __future__ import annotations

import json
from collections.abc import Mapping as MappingABC
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal, Mapping, cast

__all__ = [
    "ActionKind",
    "EvidenceRole",
    "Lens",
    "SalesChartCatalog",
    "SalesChartCatalogAction",
    "SalesChartCatalogCondition",
    "SalesChartCatalogRule",
    "SalesChartPattern",
    "ScopeSupport",
    "TimeScope",
    "build_sales_chart_patterns",
    "load_sales_chart_catalog",
    "resolve_sales_chart_options",
]

ActionKind = Literal["plot", "table"]
ConditionOp = Literal["eq", "gt", "lt", "contains", "contains_only"]
Lens = Literal[
    "growth_size",
    "price_value_capture",
    "brand_shifts",
    "fragmentation_concentration",
    "attribute_mix",
    "retailer_divergence",
]
EvidenceRole = Literal["primary", "supporting", "special_case"]
TimeScope = Literal["trend", "snapshot", "change", "decomposition"]
ScopeSupport = Literal["single_category", "category_vs_market", "cross_category"]


@dataclass(frozen=True, slots=True)
class SalesChartCatalogCondition:
    field: str
    op: ConditionOp
    value: Any


@dataclass(frozen=True, slots=True)
class SalesChartCatalogAction:
    action: str
    kind: ActionKind
    chart_key: str
    label: str
    rendering: str
    chart_type: str
    variants: tuple[str, ...]
    supports_small_multiples: bool
    brief_enabled: bool
    lenses: tuple[Lens, ...]
    evidence_role: EvidenceRole
    time_scope: TimeScope
    scope_support: tuple[ScopeSupport, ...]
    use_when: str
    avoid_when: str
    required_parameters: tuple[str, ...]
    optional_parameters: tuple[str, ...]
    request_overrides: Mapping[str, Any]


@dataclass(frozen=True, slots=True)
class SalesChartCatalogRule:
    rule_id: str
    rule_type: Literal["plot", "error"]
    conditions: tuple[SalesChartCatalogCondition, ...]
    action: str | None
    intent: str
    goal: str
    message: str


@dataclass(frozen=True, slots=True)
class SalesChartCatalog:
    version: int
    actions: Mapping[str, SalesChartCatalogAction]
    rules: tuple[SalesChartCatalogRule, ...]


@dataclass(frozen=True, slots=True)
class SalesChartPattern:
    pattern_id: str
    conditions: tuple[SalesChartCatalogCondition, ...]
    chart_actions: tuple[SalesChartCatalogAction, ...]


def _catalog_path() -> Path:
    return Path(__file__).resolve().with_name("sales_chart_catalog_rules.json")


def _load_catalog_payload() -> dict[str, Any]:
    payload = json.loads(_catalog_path().read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("Sales chart catalog payload must be a JSON object.")
    return payload


def _parse_condition(raw: Mapping[str, Any]) -> SalesChartCatalogCondition:
    field = str(raw.get("field") or "").strip()
    op = str(raw.get("op") or "eq").strip().lower()
    if not field:
        raise ValueError("Sales chart catalog condition is missing a field.")
    if op not in {"eq", "gt", "lt", "contains", "contains_only"}:
        raise ValueError(f"Unsupported sales chart condition operator: {op}")
    return SalesChartCatalogCondition(
        field=field,
        op=op,  # type: ignore[arg-type]
        value=raw.get("value"),
    )


def _parse_string_tuple(raw: Any, *, field_name: str) -> tuple[str, ...]:
    if raw is None:
        return ()
    if not isinstance(raw, list):
        raise ValueError(f"{field_name} must be a list.")
    return tuple(str(value).strip() for value in raw if str(value).strip())


def load_sales_chart_catalog() -> SalesChartCatalog:
    payload = _load_catalog_payload()
    version = int(payload.get("version") or 1)
    raw_actions = payload.get("actions")
    raw_rules = payload.get("rules")
    if not isinstance(raw_actions, dict):
        raise ValueError("Sales chart catalog actions must be a JSON object.")
    if not isinstance(raw_rules, list):
        raise ValueError("Sales chart catalog rules must be a JSON array.")

    actions: dict[str, SalesChartCatalogAction] = {}
    for action_name, raw_action in raw_actions.items():
        if not isinstance(raw_action, dict):
            raise ValueError(f"Sales chart action {action_name!r} must be an object.")
        normalized_action = str(action_name or "").strip()
        if not normalized_action:
            raise ValueError("Sales chart action names must be non-empty.")
        kind = str(raw_action.get("kind") or "plot").strip().lower()
        if kind not in {"plot", "table"}:
            raise ValueError(
                f"Sales chart action {normalized_action!r} has invalid kind {kind!r}."
            )
        action_kind = cast(ActionKind, kind)
        variants = raw_action.get("variants") or []
        if not isinstance(variants, list):
            raise ValueError(
                f"Sales chart action {normalized_action!r} variants must be a list."
            )
        request_overrides = raw_action.get("request_overrides") or {}
        if not isinstance(request_overrides, dict):
            raise ValueError(
                f"Sales chart action {normalized_action!r} request_overrides must be an object."
            )
        required_parameters = _parse_string_tuple(
            raw_action.get("required_parameters"),
            field_name=f"{normalized_action}.required_parameters",
        )
        optional_parameters = _parse_string_tuple(
            raw_action.get("optional_parameters"),
            field_name=f"{normalized_action}.optional_parameters",
        )
        raw_lenses = raw_action.get("lenses") or []
        if not isinstance(raw_lenses, list):
            raise ValueError(
                f"Sales chart action {normalized_action!r} lenses must be a list."
            )
        lenses = tuple(str(value).strip() for value in raw_lenses if str(value).strip())
        valid_lenses = {
            "growth_size",
            "price_value_capture",
            "brand_shifts",
            "fragmentation_concentration",
            "attribute_mix",
            "retailer_divergence",
        }
        if not lenses or any(value not in valid_lenses for value in lenses):
            raise ValueError(
                f"Sales chart action {normalized_action!r} has invalid lenses {lenses!r}."
            )
        evidence_role = str(raw_action.get("evidence_role") or "").strip().lower()
        if evidence_role not in {"primary", "supporting", "special_case"}:
            raise ValueError(
                f"Sales chart action {normalized_action!r} has invalid evidence_role {evidence_role!r}."
            )
        time_scope = str(raw_action.get("time_scope") or "").strip().lower()
        if time_scope not in {"trend", "snapshot", "change", "decomposition"}:
            raise ValueError(
                f"Sales chart action {normalized_action!r} has invalid time_scope {time_scope!r}."
            )
        raw_scope_support = raw_action.get("scope_support") or []
        if not isinstance(raw_scope_support, list):
            raise ValueError(
                f"Sales chart action {normalized_action!r} scope_support must be a list."
            )
        scope_support = tuple(
            str(value).strip() for value in raw_scope_support if str(value).strip()
        )
        valid_scope_support = {
            "single_category",
            "category_vs_market",
            "cross_category",
        }
        if not scope_support or any(
            value not in valid_scope_support for value in scope_support
        ):
            raise ValueError(
                f"Sales chart action {normalized_action!r} has invalid scope_support {scope_support!r}."
            )
        actions[normalized_action] = SalesChartCatalogAction(
            action=normalized_action,
            kind=action_kind,
            chart_key=str(raw_action.get("chart_key") or "").strip()
            or normalized_action,
            label=str(raw_action.get("label") or normalized_action).strip(),
            rendering=str(raw_action.get("rendering") or "").strip() or "server_chart",
            chart_type=str(raw_action.get("chart_type") or "").strip()
            or normalized_action,
            variants=tuple(
                str(value).strip() for value in variants if str(value).strip()
            ),
            supports_small_multiples=bool(raw_action.get("supports_small_multiples")),
            brief_enabled=bool(raw_action.get("brief_enabled")),
            lenses=lenses,  # type: ignore[arg-type]
            evidence_role=evidence_role,  # type: ignore[arg-type]
            time_scope=time_scope,  # type: ignore[arg-type]
            scope_support=scope_support,  # type: ignore[arg-type]
            use_when=str(raw_action.get("use_when") or "").strip(),
            avoid_when=str(raw_action.get("avoid_when") or "").strip(),
            required_parameters=required_parameters,
            optional_parameters=optional_parameters,
            request_overrides=dict(request_overrides),
        )

    rules: list[SalesChartCatalogRule] = []
    for index, raw_rule in enumerate(raw_rules):
        if not isinstance(raw_rule, dict):
            raise ValueError(
                f"Sales chart catalog rule at index {index} must be an object."
            )
        rule_type = str(raw_rule.get("type") or "").strip().lower()
        if rule_type not in {"plot", "error"}:
            raise ValueError(
                f"Sales chart catalog rule {raw_rule.get('id')!r} has invalid type {rule_type!r}."
            )
        conditions_raw = raw_rule.get("all") or []
        if not isinstance(conditions_raw, list):
            raise ValueError(
                f"Sales chart catalog rule {raw_rule.get('id')!r} conditions must be a list."
            )
        action_name = (
            str(raw_rule.get("action") or "").strip() if rule_type == "plot" else ""
        )
        if rule_type == "plot" and action_name not in actions:
            raise ValueError(
                f"Sales chart catalog rule {raw_rule.get('id')!r} references unknown action {action_name!r}."
            )
        rules.append(
            SalesChartCatalogRule(
                rule_id=str(raw_rule.get("id") or f"rule_{index}").strip(),
                rule_type=rule_type,  # type: ignore[arg-type]
                conditions=tuple(
                    _parse_condition(raw_condition)
                    for raw_condition in conditions_raw
                    if isinstance(raw_condition, MappingABC)
                ),
                action=action_name or None,
                intent=str(raw_rule.get("intent") or "").strip(),
                goal=str(raw_rule.get("goal") or "").strip(),
                message=str(raw_rule.get("message") or "").strip(),
            )
        )

    return SalesChartCatalog(version=version, actions=actions, rules=tuple(rules))


def _evaluate_condition(
    context: Mapping[str, Any], condition: SalesChartCatalogCondition
) -> bool:
    actual = context.get(condition.field)
    expected = condition.value
    if condition.op == "eq":
        return actual == expected
    if condition.op == "gt":
        return float(actual or 0) > float(expected or 0)
    if condition.op == "lt":
        return float(actual or 0) < float(expected or 0)
    if condition.op == "contains":
        return isinstance(actual, list) and expected in actual
    if condition.op == "contains_only":
        if not isinstance(actual, list) or not isinstance(expected, list):
            return False
        actual_set = set(actual)
        expected_set = set(expected)
        return actual_set == expected_set
    return False


def resolve_sales_chart_options(
    context: Mapping[str, Any],
) -> tuple[list[SalesChartCatalogRule], SalesChartCatalogRule | None]:
    catalog = load_sales_chart_catalog()
    matched_plot_rules: list[SalesChartCatalogRule] = []
    blocking_error_rule: SalesChartCatalogRule | None = None
    for rule in catalog.rules:
        matched = all(
            _evaluate_condition(context, condition) for condition in rule.conditions
        )
        if not matched:
            continue
        if (
            rule.rule_type == "error"
            and not matched_plot_rules
            and blocking_error_rule is None
        ):
            blocking_error_rule = rule
            continue
        if rule.rule_type == "plot":
            matched_plot_rules.append(rule)
    if blocking_error_rule is not None:
        return [], blocking_error_rule
    if not matched_plot_rules:
        return [], SalesChartCatalogRule(
            rule_id="fallback_no_chart",
            rule_type="error",
            conditions=tuple(),
            action=None,
            intent="",
            goal="",
            message="No chart available for the current selection.",
        )
    return matched_plot_rules, None


def build_sales_chart_patterns() -> list[SalesChartPattern]:
    catalog = load_sales_chart_catalog()
    grouped: dict[str, list[SalesChartCatalogRule]] = {}
    for rule in catalog.rules:
        if rule.rule_type != "plot":
            continue
        key = json.dumps(
            [
                {"field": condition.field, "op": condition.op, "value": condition.value}
                for condition in rule.conditions
            ],
            sort_keys=True,
        )
        grouped.setdefault(key, []).append(rule)

    patterns: list[SalesChartPattern] = []
    for index, rules in enumerate(grouped.values(), start=1):
        first_rule = rules[0]
        chart_actions = tuple(
            catalog.actions[rule.action]
            for rule in rules
            if rule.action is not None and rule.action in catalog.actions
        )
        patterns.append(
            SalesChartPattern(
                pattern_id=f"pattern_{index:02d}",
                conditions=first_rule.conditions,
                chart_actions=chart_actions,
            )
        )
    return patterns
