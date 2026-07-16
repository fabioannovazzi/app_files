"""Deterministic recipe-level filters for chart-family plugins."""

from __future__ import annotations

from datetime import date, datetime
from typing import Any, Iterable, Mapping

import polars as pl

from modules.utilities.helpers import get_schema_and_column_names
from modules.utilities.utils import get_row_count

__all__ = [
    "apply_recipe_filters",
    "extract_recipe_filters",
    "apply_legacy_filter_title_metadata",
    "legacy_filter_dict_from_recipe",
    "normalize_recipe_filters",
    "preserve_recipe_filters",
]

INCLUDE_KEYS = ("include", "includes", "in", "values", "eq", "equals", "only")
EXCLUDE_KEYS = ("exclude", "excludes", "not_in", "not", "neq", "not_equals")
GREATER_THAN_KEYS = ("gt", "greater_than", "above", "min_exclusive")
GREATER_EQUAL_KEYS = (
    "gte",
    "ge",
    "greater_than_or_equal",
    "at_least",
    "minimum",
    "min",
)
LESS_THAN_KEYS = ("lt", "less_than", "below", "max_exclusive")
LESS_EQUAL_KEYS = (
    "lte",
    "le",
    "less_than_or_equal",
    "at_most",
    "maximum",
    "max",
)
TITLE_DISPLAY_KEYS = ("display_in_title", "show_in_title", "visible_in_title")
HIDDEN_TITLE_KEYS = ("hidden", "hide_from_title")
LEGACY_INCLUDE_KEY = "toIncludeItems"
LEGACY_EXCLUDE_KEY = "toExcludeItems"


def extract_recipe_filters(recipe: Mapping[str, Any]) -> list[dict[str, Any]]:
    """Return normalized filters from root recipe and options.

    Filters are deterministic because they are explicit column include/exclude
    rules. They are applied sequentially in recipe order.
    """

    filters: list[dict[str, Any]] = []
    root_filter = _first_present(recipe, ("filters", "filter_dict"))
    if root_filter is not None:
        filters.extend(
            {
                **item,
                "source": "recipe",
            }
            for item in normalize_recipe_filters(root_filter)
        )
    options = recipe.get("options")
    if isinstance(options, Mapping):
        options_filter = _first_present(options, ("filters", "filter_dict"))
        if options_filter is not None:
            filters.extend(
                {
                    **item,
                    "source": "options",
                }
                for item in normalize_recipe_filters(options_filter)
            )
    return filters


def preserve_recipe_filters(
    recipe: dict[str, Any],
    source_recipe: Mapping[str, Any] | None,
) -> dict[str, Any]:
    """Carry explicit filters from a source recipe after recipe inference."""

    if not isinstance(source_recipe, Mapping):
        return recipe
    for key in ("filters", "filter_dict"):
        if key in source_recipe and key not in recipe:
            recipe[key] = source_recipe[key]
    source_options = source_recipe.get("options")
    if isinstance(source_options, Mapping):
        target_options = recipe.setdefault("options", {})
        for key in ("filters", "filter_dict"):
            if key in source_options and key not in target_options:
                target_options[key] = source_options[key]
    return recipe


def normalize_recipe_filters(filters: Any) -> list[dict[str, Any]]:
    """Normalize accepted filter shorthands into include/exclude rules."""

    if filters is None or filters is False or filters == {} or filters == []:
        return []
    if isinstance(filters, Mapping):
        return _normalize_filter_mapping(filters)
    if isinstance(filters, list):
        return [_normalize_filter_item(item) for item in filters]
    raise ValueError("Recipe filters must be an object or a list of objects.")


def apply_recipe_filters(
    frame: pl.DataFrame,
    recipe: Mapping[str, Any],
) -> tuple[pl.DataFrame, dict[str, Any]]:
    """Apply explicit recipe filters and return the filtered frame plus audit."""

    filters = extract_recipe_filters(recipe)
    if not filters:
        return frame, {
            "status": "skipped",
            "reason": "no_recipe_filters",
            "rows_before": get_row_count(frame),
            "rows_after": get_row_count(frame),
        }

    columns, schema = get_schema_and_column_names(frame)
    result = frame
    steps: list[dict[str, Any]] = []
    for item in filters:
        column = str(item["column"])
        if column not in columns:
            raise ValueError(f"Recipe filter references missing column: {column}")
        raw_include = item["include"] if "include" in item else []
        raw_exclude = item["exclude"] if "exclude" in item else []
        include = _coerce_values(schema[column], raw_include)
        exclude = _coerce_values(schema[column], raw_exclude)
        greater_than = _coerce_comparison_value(schema[column], item, "gt")
        greater_equal = _coerce_comparison_value(schema[column], item, "gte")
        less_than = _coerce_comparison_value(schema[column], item, "lt")
        less_equal = _coerce_comparison_value(schema[column], item, "lte")
        rows_before = get_row_count(result)
        if include:
            result = result.filter(pl.col(column).is_in(include))
        if exclude:
            result = result.filter(~pl.col(column).is_in(exclude))
        if greater_than is not None:
            result = result.filter(pl.col(column) > greater_than)
        if greater_equal is not None:
            result = result.filter(pl.col(column) >= greater_equal)
        if less_than is not None:
            result = result.filter(pl.col(column) < less_than)
        if less_equal is not None:
            result = result.filter(pl.col(column) <= less_equal)
        rows_after = get_row_count(result)
        step = {
            "source": item.get("source"),
            "column": column,
            "include": include,
            "exclude": exclude,
            "rows_before": rows_before,
            "rows_after": rows_after,
            "removed_rows": rows_before - rows_after,
        }
        _copy_comparison_audit(
            step,
            gt=greater_than,
            gte=greater_equal,
            lt=less_than,
            lte=less_equal,
        )
        if item.get("display_in_title") is False:
            step["display_in_title"] = False
        steps.append(step)

    return result, {
        "status": "written",
        "filter_count": len(steps),
        "rows_before": get_row_count(frame),
        "rows_after": get_row_count(result),
        "removed_rows": get_row_count(frame) - get_row_count(result),
        "filters": steps,
    }


def legacy_filter_dict_from_recipe(recipe: Mapping[str, Any]) -> dict[str, Any]:
    """Return legacy ``chartDict[filterDictName]`` filter rules for titles."""

    filters = extract_recipe_filters(recipe)
    if not filters:
        return {}
    from modules.utilities.config import get_naming_params

    names = get_naming_params()
    include_key = names["toIncludeItems"]
    exclude_key = names["toExcludeItems"]
    result: dict[str, Any] = {}
    for item in filters:
        column = str(item["column"])
        include = item["include"] if "include" in item else []
        exclude = item["exclude"] if "exclude" in item else []
        if item.get("display_in_title") is False:
            continue
        if include:
            column_rule = result.setdefault(column, {})
            column_rule.setdefault(include_key, [])
            column_rule[include_key].extend(include)
        if exclude:
            column_rule = result.setdefault(column, {})
            column_rule.setdefault(exclude_key, [])
            column_rule[exclude_key].extend(exclude)
    return result


def apply_legacy_filter_title_metadata(
    chart: dict[str, Any],
    names: Mapping[str, str],
    recipe: Mapping[str, Any],
) -> dict[str, Any]:
    """Attach recipe filters to a legacy chart dict for title generation."""

    filter_dict = legacy_filter_dict_from_recipe(recipe)
    if not filter_dict:
        return chart
    chart[names["filterDictName"]] = filter_dict
    chart[names["filterActiveName"]] = True
    return chart


def _normalize_filter_mapping(filters: Mapping[str, Any]) -> list[dict[str, Any]]:
    normalized: list[dict[str, Any]] = []
    for column, rules in filters.items():
        if not column:
            raise ValueError("Recipe filter column names cannot be empty.")
        normalized.append(_normalize_column_rule(str(column), rules))
    return normalized


def _normalize_filter_item(item: Any) -> dict[str, Any]:
    if not isinstance(item, Mapping):
        raise ValueError("Each recipe filter item must be an object.")
    if "column" in item:
        column = item["column"]
        if not column:
            raise ValueError("Recipe filter items require a non-empty column.")
        return _normalize_column_rule(str(column), item)
    if len(item) == 1:
        column, rules = next(iter(item.items()))
        return _normalize_column_rule(str(column), rules)
    raise ValueError("Recipe filter list items require a column field.")


def _normalize_column_rule(column: str, rules: Any) -> dict[str, Any]:
    if isinstance(rules, Mapping):
        include = _first_present(rules, (*INCLUDE_KEYS, LEGACY_INCLUDE_KEY))
        exclude = _first_present(rules, (*EXCLUDE_KEYS, LEGACY_EXCLUDE_KEY))
        greater_than = _first_present(rules, GREATER_THAN_KEYS)
        greater_equal = _first_present(rules, GREATER_EQUAL_KEYS)
        less_than = _first_present(rules, LESS_THAN_KEYS)
        less_equal = _first_present(rules, LESS_EQUAL_KEYS)
        display_in_title = _display_in_title(rules)
    else:
        include = rules
        exclude = None
        greater_than = None
        greater_equal = None
        less_than = None
        less_equal = None
        display_in_title = True
    include_values = _as_list(include)
    exclude_values = _as_list(exclude)
    rule = {
        "column": column,
        "include": include_values,
        "exclude": exclude_values,
    }
    _copy_comparison_filter(
        rule,
        gt=greater_than,
        gte=greater_equal,
        lt=less_than,
        lte=less_equal,
    )
    has_filter_value = any(
        (
            bool(include_values),
            bool(exclude_values),
            "gt" in rule,
            "gte" in rule,
            "lt" in rule,
            "lte" in rule,
        )
    )
    if not display_in_title:
        rule["display_in_title"] = False
    if not has_filter_value:
        raise ValueError(
            f"Recipe filter for '{column}' has no include/exclude/comparison values."
        )
    return rule


def _copy_comparison_filter(
    target: dict[str, Any],
    *,
    gt: Any,
    gte: Any,
    lt: Any,
    lte: Any,
) -> None:
    for key, value in (("gt", gt), ("gte", gte), ("lt", lt), ("lte", lte)):
        if value is None or value == [] or value == {} or value == "":
            continue
        values = _as_list(value)
        if len(values) != 1:
            raise ValueError(f"Recipe filter comparison '{key}' requires one value.")
        target[key] = values[0]


def _copy_comparison_audit(
    target: dict[str, Any],
    *,
    gt: Any,
    gte: Any,
    lt: Any,
    lte: Any,
) -> None:
    for key, value in (("gt", gt), ("gte", gte), ("lt", lt), ("lte", lte)):
        if value is not None:
            target[key] = value


def _display_in_title(rules: Mapping[str, Any]) -> bool:
    for key in TITLE_DISPLAY_KEYS:
        if key in rules:
            return bool(rules[key])
    for key in HIDDEN_TITLE_KEYS:
        if key in rules:
            return not bool(rules[key])
    return True


def _first_present(source: Mapping[str, Any], keys: Iterable[str]) -> Any:
    for key in keys:
        if key in source:
            value = source[key]
            if value is not None and value != [] and value != {} and value != "":
                return value
    return None


def _as_list(value: Any) -> list[Any]:
    if value is None or value is False or value == []:
        return []
    if isinstance(value, list):
        return value
    if isinstance(value, tuple):
        return list(value)
    if isinstance(value, set):
        return sorted(value)
    return [value]


def _coerce_values(dtype: pl.DataType | str, values: list[Any]) -> list[Any]:
    return [_coerce_value(dtype, value) for value in values]


def _coerce_comparison_value(
    dtype: pl.DataType | str,
    item: Mapping[str, Any],
    key: str,
) -> Any:
    if key not in item:
        return None
    return _coerce_value(dtype, item[key])


def _coerce_value(dtype: pl.DataType | str, value: Any) -> Any:
    if value is None:
        return None
    dtype_text = str(dtype)
    if dtype == pl.Utf8 or dtype_text == "String":
        return str(value)
    if dtype == pl.Boolean or dtype_text == "Boolean":
        if isinstance(value, bool):
            return value
        text = str(value).strip().lower()
        if text in {"1", "true", "yes", "y"}:
            return True
        if text in {"0", "false", "no", "n"}:
            return False
        raise ValueError(f"Cannot coerce filter value to bool: {value}")
    if dtype_text.startswith(("Int", "UInt")):
        return int(value)
    if dtype_text.startswith("Float"):
        return float(value)
    if dtype == pl.Date or dtype_text == "Date":
        if isinstance(value, date) and not isinstance(value, datetime):
            return value
        return date.fromisoformat(str(value))
    if dtype == pl.Datetime or dtype_text.startswith("Datetime"):
        if isinstance(value, datetime):
            return value
        return datetime.fromisoformat(str(value))
    return value
