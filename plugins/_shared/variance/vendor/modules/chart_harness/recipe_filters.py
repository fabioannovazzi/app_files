"""Recipe-filter metadata helpers for the variance legacy vendor path."""

from __future__ import annotations

from typing import Any, Iterable, Mapping

__all__ = [
    "apply_legacy_filter_title_metadata",
    "legacy_filter_dict_from_recipe",
]

INCLUDE_KEYS = ("include", "includes", "in", "values", "eq", "equals", "only")
EXCLUDE_KEYS = ("exclude", "excludes", "not_in", "not", "neq", "not_equals")
LEGACY_INCLUDE_KEY = "toIncludeItems"
LEGACY_EXCLUDE_KEY = "toExcludeItems"


def legacy_filter_dict_from_recipe(recipe: Mapping[str, Any]) -> dict[str, Any]:
    """Return legacy ``chartDict[filterDictName]`` filter rules for titles."""

    filters = _extract_recipe_filters(recipe)
    if not filters:
        return {}
    from modules.utilities.config import get_naming_params

    names = get_naming_params()
    include_key = names["toIncludeItems"]
    exclude_key = names["toExcludeItems"]
    result: dict[str, Any] = {}
    for item in filters:
        column = str(item["column"])
        column_rule = result.setdefault(column, {})
        include = item["include"] if "include" in item else []
        exclude = item["exclude"] if "exclude" in item else []
        if include:
            column_rule.setdefault(include_key, [])
            column_rule[include_key].extend(include)
        if exclude:
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


def _extract_recipe_filters(recipe: Mapping[str, Any]) -> list[dict[str, Any]]:
    filters: list[dict[str, Any]] = []
    root_filter = _first_present(recipe, ("filters", "filter_dict"))
    if root_filter is not None:
        filters.extend(_normalize_recipe_filters(root_filter))
    options = recipe.get("options")
    if isinstance(options, Mapping):
        options_filter = _first_present(options, ("filters", "filter_dict"))
        if options_filter is not None:
            filters.extend(_normalize_recipe_filters(options_filter))
    return filters


def _normalize_recipe_filters(filters: Any) -> list[dict[str, Any]]:
    if filters is None or filters is False or filters == {} or filters == []:
        return []
    if isinstance(filters, Mapping):
        return [_normalize_column_rule(str(column), rules) for column, rules in filters.items()]
    if isinstance(filters, list):
        return [_normalize_filter_item(item) for item in filters]
    raise ValueError("Recipe filters must be an object or a list of objects.")


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
    else:
        include = rules
        exclude = None
    include_values = _as_list(include)
    exclude_values = _as_list(exclude)
    if not include_values and not exclude_values:
        raise ValueError(f"Recipe filter for '{column}' has no include/exclude values.")
    return {
        "column": column,
        "include": include_values,
        "exclude": exclude_values,
    }


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
