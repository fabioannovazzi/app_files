"""Metric semantic contracts for chart requests.

Metric semantics are deterministic because chart grammars have mechanical
requirements: stacked and bridge charts require additive/stackable measures,
bubble area requires an area-safe size metric, and BarMekko area must have a
declared width x height interpretation. The rules here validate chart grammar;
they do not decide which source data is insightful.
"""

from __future__ import annotations

from typing import Any, Mapping

__all__ = [
    "MetricSemanticsError",
    "normalize_metric_semantics",
    "validate_metric_requirements",
    "validate_metric_relationships",
]

BOOLEAN_FIELDS = ("numeric", "stackable", "additive", "non_negative")
CONTRACT_TEXT_FIELDS = (
    "value_type",
    "aggregation",
    "requires_weight_metric",
    "denominator_metric",
    "metric_role",
    "semantic_role",
)
RELATIONSHIP_TYPE_MULTIPLICATIVE_AREA = "multiplicative_area"


class MetricSemanticsError(ValueError):
    """Raised when metric semantics do not satisfy a chart capability."""


def _metric_name(value: Any) -> str | None:
    if isinstance(value, str) and value:
        return value
    if isinstance(value, Mapping):
        name = value.get("name") or value.get("metric") or value.get("column")
        if isinstance(name, str) and name:
            return name
    return None


def _normalize_contract(metric: str, contract: Mapping[str, Any]) -> dict[str, Any]:
    normalized: dict[str, Any] = {"metric": metric}
    for field in BOOLEAN_FIELDS:
        if field in contract:
            normalized[field] = bool(contract[field])
    for field in CONTRACT_TEXT_FIELDS:
        value = contract.get(field)
        if value not in (None, "", [], {}):
            normalized[field] = value
    return normalized


def normalize_metric_semantics(payload: Any) -> dict[str, dict[str, Any]]:
    """Return metric name -> semantic contract.

    Accepted shapes:
    - {"Sales": {"numeric": true, "additive": true, "stackable": true}}
    - [{"metric": "Sales", "numeric": true, ...}]
    """

    if payload in (None, False, {}, []):
        return {}
    if isinstance(payload, Mapping):
        result: dict[str, dict[str, Any]] = {}
        for key, value in payload.items():
            if isinstance(value, Mapping):
                metric = _metric_name(value) or str(key)
                result[metric] = _normalize_contract(metric, value)
            elif isinstance(value, bool):
                metric = str(key)
                result[metric] = {
                    "metric": metric,
                    "numeric": value,
                    "additive": value,
                    "stackable": value,
                    "non_negative": value,
                }
            else:
                raise MetricSemanticsError(
                    f"Metric semantics for '{key}' must be an object."
                )
        return result
    if isinstance(payload, list):
        result = {}
        for index, item in enumerate(payload, start=1):
            if not isinstance(item, Mapping):
                raise MetricSemanticsError(
                    f"metric_semantics[{index}] must be an object."
                )
            metric = _metric_name(item)
            if metric is None:
                raise MetricSemanticsError(
                    f"metric_semantics[{index}] must declare metric/name/column."
                )
            result[metric] = _normalize_contract(metric, item)
        return result
    raise MetricSemanticsError("metric_semantics must be an object or list.")


def _metric_values(parameters: Mapping[str, Any], field: str) -> list[str]:
    value = parameters.get(field)
    if value in (None, "", [], {}):
        return []
    if isinstance(value, list):
        return [metric for item in value for metric in _metric_values({"_": item}, "_")]
    metric = _metric_name(value)
    return [metric] if metric is not None else []


def _check_flag(
    *,
    capability_id: str,
    metric: str,
    field: str,
    contract: Mapping[str, Any],
) -> None:
    if contract.get(field) is not True:
        raise MetricSemanticsError(
            f"{capability_id} requires metric '{metric}' with {field}=true."
        )


def _string_set(value: Any, *, location: str) -> set[str]:
    if value in (None, "", [], {}):
        return set()
    if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
        raise MetricSemanticsError(f"{location} must be a list of strings.")
    return {item.strip().lower() for item in value if item.strip()}


def _contract_value_type(contract: Mapping[str, Any]) -> str | None:
    value = contract.get("value_type")
    return str(value).strip().lower() if value not in (None, "") else None


def _contract_roles(contract: Mapping[str, Any]) -> set[str]:
    roles = set()
    for field in ("metric_role", "semantic_role"):
        value = contract.get(field)
        if value not in (None, "", [], {}):
            roles.add(str(value).strip().lower())
    return roles


def _check_value_type(
    *,
    capability_id: str,
    metric: str,
    requirement: Mapping[str, Any],
    contract: Mapping[str, Any],
) -> None:
    value_type = _contract_value_type(contract)
    allowed = _string_set(
        requirement.get("allowed_value_types"),
        location=f"{capability_id}.allowed_value_types",
    )
    blocked = _string_set(
        requirement.get("blocked_value_types"),
        location=f"{capability_id}.blocked_value_types",
    )
    if allowed and value_type not in allowed:
        allowed_text = ", ".join(sorted(allowed))
        actual = value_type or "missing"
        raise MetricSemanticsError(
            f"{capability_id} requires metric '{metric}' with value_type in "
            f"[{allowed_text}], got {actual}."
        )
    if blocked and value_type in blocked:
        raise MetricSemanticsError(
            f"{capability_id} rejects metric '{metric}' with value_type={value_type}."
        )


def _check_roles(
    *,
    capability_id: str,
    metric: str,
    requirement: Mapping[str, Any],
    contract: Mapping[str, Any],
) -> None:
    roles = _contract_roles(contract)
    allowed = _string_set(
        requirement.get("allowed_metric_roles"),
        location=f"{capability_id}.allowed_metric_roles",
    )
    blocked = _string_set(
        requirement.get("blocked_metric_roles"),
        location=f"{capability_id}.blocked_metric_roles",
    )
    if allowed and not (roles & allowed):
        allowed_text = ", ".join(sorted(allowed))
        actual = ", ".join(sorted(roles)) if roles else "missing"
        raise MetricSemanticsError(
            f"{capability_id} requires metric '{metric}' with metric_role in "
            f"[{allowed_text}], got {actual}."
        )
    blocked_roles = roles & blocked
    if blocked_roles:
        blocked_text = ", ".join(sorted(blocked_roles))
        raise MetricSemanticsError(
            f"{capability_id} rejects metric '{metric}' with metric_role={blocked_text}."
        )


def validate_metric_requirements(
    parameters: Mapping[str, Any],
    metric_requirements: Mapping[str, Any] | None,
    *,
    capability_id: str,
) -> dict[str, Any]:
    """Validate request metric semantics against capability requirements."""

    if not metric_requirements:
        return {}
    semantics = normalize_metric_semantics(parameters.get("metric_semantics"))
    validated: dict[str, Any] = {}
    for field, requirement in metric_requirements.items():
        if not isinstance(requirement, Mapping):
            raise MetricSemanticsError(
                f"{capability_id}.metric_requirements.{field} must be an object."
            )
        metrics = _metric_values(parameters, str(field))
        if not metrics:
            if requirement.get("required", True):
                raise MetricSemanticsError(
                    f"{capability_id} requires metric parameter '{field}'."
                )
            continue
        for metric in metrics:
            contract = semantics.get(metric)
            if contract is None:
                raise MetricSemanticsError(
                    f"{capability_id} requires metric_semantics for '{metric}'."
                )
            for flag in BOOLEAN_FIELDS:
                if requirement.get(flag) is True:
                    _check_flag(
                        capability_id=capability_id,
                        metric=metric,
                        field=flag,
                        contract=contract,
                    )
            _check_value_type(
                capability_id=capability_id,
                metric=metric,
                requirement=requirement,
                contract=contract,
            )
            _check_roles(
                capability_id=capability_id,
                metric=metric,
                requirement=requirement,
                contract=contract,
            )
            validated[metric] = contract
    return validated


def _relationship_items(metric_relationships: Any) -> list[Mapping[str, Any]]:
    if metric_relationships in (None, False, {}, []):
        return []
    if not isinstance(metric_relationships, list):
        raise MetricSemanticsError("metric_relationships must be a list.")
    result: list[Mapping[str, Any]] = []
    for index, item in enumerate(metric_relationships, start=1):
        if not isinstance(item, Mapping):
            raise MetricSemanticsError(
                f"metric_relationships[{index}] must be an object."
            )
        result.append(item)
    return result


def _required_string(
    parameters: Mapping[str, Any],
    field: str,
    *,
    capability_id: str,
) -> str:
    value = parameters.get(field)
    if not isinstance(value, str) or not value.strip():
        raise MetricSemanticsError(
            f"{capability_id} requires relationship parameter '{field}'."
        )
    return value.strip()


def validate_metric_relationships(
    parameters: Mapping[str, Any],
    metric_relationships: Any,
    *,
    capability_id: str,
    validated_metric_semantics: Mapping[str, Any] | None = None,
) -> list[dict[str, str]]:
    """Validate relationships between metric roles, such as BarMekko area.

    ``area_represents`` is a semantic label, not an input column. If a plugin has
    real data for that metric later, it can add a separate arithmetic check.
    """

    relationships: list[dict[str, str]] = []
    semantics = normalize_metric_semantics(parameters.get("metric_semantics"))
    if validated_metric_semantics:
        semantics.update(dict(validated_metric_semantics))
    for relationship in _relationship_items(metric_relationships):
        relationship_type = relationship.get("relationship_type")
        if relationship_type != RELATIONSHIP_TYPE_MULTIPLICATIVE_AREA:
            raise MetricSemanticsError(
                f"{capability_id} has unsupported metric relationship: "
                f"{relationship_type}."
            )
        width_field = relationship.get("width_metric_field")
        height_field = relationship.get("height_metric_field")
        area_label_field = relationship.get("area_label_field")
        if not all(
            isinstance(field, str) and field
            for field in (width_field, height_field, area_label_field)
        ):
            raise MetricSemanticsError(
                f"{capability_id} multiplicative_area relationship must declare "
                "width_metric_field, height_metric_field, and area_label_field."
            )
        width_metric = _required_string(
            parameters,
            width_field,
            capability_id=capability_id,
        )
        height_metric = _required_string(
            parameters,
            height_field,
            capability_id=capability_id,
        )
        area_label = _required_string(
            parameters,
            area_label_field,
            capability_id=capability_id,
        )
        missing_semantics = [
            metric for metric in (width_metric, height_metric) if metric not in semantics
        ]
        if missing_semantics:
            raise MetricSemanticsError(
                f"{capability_id} requires metric_semantics for relationship "
                f"metric(s): {', '.join(missing_semantics)}."
            )
        relationships.append(
            {
                "relationship_type": RELATIONSHIP_TYPE_MULTIPLICATIVE_AREA,
                "width_metric": width_metric,
                "height_metric": height_metric,
                "area_represents": area_label,
                "formula": f"{width_metric} * {height_metric} = {area_label}",
            }
        )
    return relationships
