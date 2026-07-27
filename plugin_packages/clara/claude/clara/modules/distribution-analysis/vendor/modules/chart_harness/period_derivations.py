"""Deterministic period/cohort derivations for chart-family plugins."""

from __future__ import annotations

from typing import Any, Iterable, Mapping

import polars as pl

from modules.utilities.helpers import get_schema_and_column_names
from modules.utilities.utils import get_row_count

__all__ = [
    "add_comparison_cohort_columns",
    "apply_recipe_cohorts",
    "apply_period_derivations",
    "filter_like_for_like_entities",
    "normalize_recipe_cohort_contract",
    "normalize_like_for_like_spec",
    "normalize_period_derivation_specs",
    "preserve_recipe_cohorts",
    "recipe_cohort_dimension_names",
    "recipe_cohort_period_labels",
    "recipe_cohort_source_dimensions",
]

DEFAULT_CURRENT_PERIOD = "AC"
DEFAULT_PREVIOUS_PERIOD = "PY"
DEFAULT_SINCE_LABEL = "Since"
DEFAULT_LOST_LABEL = "Lost"
DEFAULT_ACTIVE_LABEL = "Active"
DEFAULT_INACTIVE_LABEL = "No activity"
DEFAULT_COHORT_VISIBLE_PERIOD_COUNT = 3
ACTIVITY_THRESHOLD = 0.0


def normalize_period_derivation_specs(
    specs: Any,
) -> list[dict[str, Any]]:
    """Return normalized derived-dimension specs.

    These specs are deterministic because they describe mechanical AC/PY
    presence checks over an entity column, not semantic business judgment.
    """

    if specs is None or specs is False:
        return []
    if isinstance(specs, Mapping):
        items: Iterable[Any] = [specs]
    elif isinstance(specs, list):
        items = specs
    else:
        raise ValueError("options.derived_dimensions must be a list of objects.")

    normalized: list[dict[str, Any]] = []
    for raw_item in items:
        if not isinstance(raw_item, Mapping):
            raise ValueError("Each derived dimension spec must be an object.")
        item = dict(raw_item)
        source_dimension = item.get("source_dimension") or item.get("dimension")
        if not source_dimension:
            raise ValueError("Derived dimension spec requires source_dimension.")
        kind = str(item.get("kind") or "since").lower().replace("-", "_")
        if kind in {"cohort", "chosen_cohort"}:
            kind = "since"
        if kind in {"lost_and_dropped", "lost_dropped"}:
            kind = "lost"
        if kind not in {"since", "lost"}:
            raise ValueError(f"Unsupported derived dimension kind: {kind}")
        suffix = "_Since" if kind == "since" else "_Lost"
        name = item.get("name") or f"{source_dimension}{suffix}"
        normalized.append(
            {
                **item,
                "source_dimension": str(source_dimension),
                "name": str(name),
                "output_column": str(name),
                "kind": kind,
                "cohort_mode": kind,
            }
        )
    return normalized


def normalize_like_for_like_spec(spec: Any) -> dict[str, Any] | None:
    """Return a normalized like-for-like spec or ``None``."""

    if spec is None or spec is False:
        return None
    if isinstance(spec, str):
        return {"source_dimension": spec}
    if not isinstance(spec, Mapping):
        raise ValueError("options.like_for_like must be an object or column name.")
    source_dimension = (
        spec.get("source_dimension") or spec.get("dimension") or spec.get("column")
    )
    if not source_dimension:
        raise ValueError("Like-for-like spec requires source_dimension.")
    return {
        **dict(spec),
        "source_dimension": str(source_dimension),
        "cohort_mode": "like_for_like",
    }


def normalize_recipe_cohort_contract(
    recipe: Mapping[str, Any] | None,
) -> dict[str, Any]:
    """Return the plot-defining cohort contract from a chart recipe.

    Cohort contracts are deterministic because they are explicit period/entity
    activity rules over stable columns. The normalized payload is also used for
    chart-definition hashing, so it avoids generic keys such as ``kind`` that
    are ignored by the report validator as visual artifact metadata.
    """

    if not isinstance(recipe, Mapping):
        return {}
    options = (
        recipe.get("options") if isinstance(recipe.get("options"), Mapping) else {}
    )
    derived_dimensions: list[dict[str, Any]] = []
    like_for_like: dict[str, Any] | None = None
    periods: dict[str, Any] | None = None

    for source in (recipe, options):
        if not isinstance(source, Mapping):
            continue
        for key in ("cohort_definition", "cohort_contract", "cohorts"):
            payload = source.get(key)
            if payload is None or payload is False or payload == {} or payload == []:
                continue
            payload_derived, payload_like, payload_periods = _normalize_cohort_payload(
                payload
            )
            derived_dimensions.extend(payload_derived)
            if payload_like is not None:
                like_for_like = payload_like
            if payload_periods is not None:
                periods = payload_periods
        if source.get("derived_dimensions") not in (None, False, [], {}):
            derived_dimensions.extend(
                normalize_period_derivation_specs(source.get("derived_dimensions"))
            )
        if source.get("like_for_like") not in (None, False, [], {}):
            like_for_like = normalize_like_for_like_spec(source.get("like_for_like"))

    contract: dict[str, Any] = {}
    if derived_dimensions:
        contract["derived_dimensions"] = _dedupe_dicts(derived_dimensions)
    if like_for_like is not None:
        contract["like_for_like"] = like_for_like
    if periods:
        contract["periods"] = periods
    return contract


def preserve_recipe_cohorts(
    recipe: dict[str, Any],
    existing_recipe: Mapping[str, Any] | None,
) -> dict[str, Any]:
    """Preserve cohort options from a caller-provided recipe during inference."""

    if not existing_recipe:
        return recipe
    options = recipe.setdefault("options", {})
    existing_options = (
        existing_recipe.get("options")
        if isinstance(existing_recipe.get("options"), Mapping)
        else {}
    )
    root_keys = ("cohorts", "cohort_definition", "cohort_contract")
    option_keys = (
        "cohorts",
        "cohort_definition",
        "cohort_contract",
        "derived_dimensions",
        "like_for_like",
        "cohort_current_period",
        "cohort_previous_period",
        "current_period_label",
        "previous_period_label",
    )
    for key in root_keys:
        if key in existing_recipe and key not in recipe:
            recipe[key] = existing_recipe[key]
    for key in option_keys:
        if key in existing_options and key not in options:
            options[key] = existing_options[key]
    return recipe


def recipe_cohort_source_dimensions(recipe: Mapping[str, Any] | None) -> list[str]:
    """Return raw entity columns required by the recipe cohort contract."""

    contract = normalize_recipe_cohort_contract(recipe)
    sources: list[str] = []
    for spec in contract.get("derived_dimensions") or []:
        source_dimension = str(spec["source_dimension"])
        if source_dimension not in sources:
            sources.append(source_dimension)
    like_for_like = contract.get("like_for_like")
    if isinstance(like_for_like, Mapping):
        source_dimension = str(like_for_like["source_dimension"])
        if source_dimension not in sources:
            sources.append(source_dimension)
    return sources


def recipe_cohort_dimension_names(recipe: Mapping[str, Any] | None) -> set[str]:
    """Return cohort columns that will be generated by the recipe."""

    contract = normalize_recipe_cohort_contract(recipe)
    return {
        str(spec["name"])
        for spec in contract.get("derived_dimensions") or []
        if spec.get("name")
    }


def recipe_cohort_period_labels(
    recipe: Mapping[str, Any] | None,
    *,
    default_current: str = DEFAULT_CURRENT_PERIOD,
    default_previous: str = DEFAULT_PREVIOUS_PERIOD,
) -> tuple[str, str]:
    """Return effective current/previous period labels for cohort logic."""

    options = recipe.get("options") if isinstance(recipe, Mapping) else {}
    options = options if isinstance(options, Mapping) else {}
    contract = normalize_recipe_cohort_contract(recipe)
    like_for_like = contract.get("like_for_like")
    current = _first_present(
        options,
        (
            "cohort_current_period",
            "cohort_comparison_period",
            "current_period",
            "current_period_label",
            "comparison_period",
            "comparison_period_label",
        ),
    )
    previous = _first_present(
        options,
        (
            "cohort_previous_period",
            "cohort_baseline_period",
            "previous_period",
            "previous_period_label",
            "baseline_period",
            "baseline_period_label",
        ),
    )
    if isinstance(like_for_like, Mapping):
        current = like_for_like.get("current_period") or current
        previous = like_for_like.get("previous_period") or previous
    periods = contract.get("periods")
    if isinstance(periods, Mapping):
        current = periods.get("current_period") or current
        previous = periods.get("previous_period") or previous
    return str(current or default_current), str(previous or default_previous)


def apply_recipe_cohorts(
    frame: pl.DataFrame,
    recipe: dict[str, Any],
    *,
    period_column: str,
    value_column: str,
    current_period: str = DEFAULT_CURRENT_PERIOD,
    previous_period: str = DEFAULT_PREVIOUS_PERIOD,
) -> tuple[pl.DataFrame, dict[str, Any]]:
    """Apply requested recipe cohorts and record the effective contract."""

    contract = normalize_recipe_cohort_contract(recipe)
    if not contract:
        audit = {"status": "skipped", "reason": "not_requested"}
        recipe.setdefault("options", {})["recipe_cohort_audit"] = audit
        return frame, audit
    if not period_column or not value_column:
        raise ValueError("Recipe cohorts require period_column and value_column.")
    required = [period_column, value_column, *recipe_cohort_source_dimensions(recipe)]
    _require_columns(frame, required)
    current_period = str(current_period)
    previous_period = str(previous_period)
    present_periods = {
        str(value)
        for value in frame.select(pl.col(period_column).cast(pl.Utf8).unique())
        .to_series()
        .to_list()
        if value is not None
    }
    missing_periods = [
        period
        for period in (previous_period, current_period)
        if period not in present_periods
    ]
    if missing_periods:
        raise ValueError(
            "Recipe cohorts require both comparison periods in the prepared data; "
            f"missing {missing_periods} in column {period_column}."
        )
    effective_contract = {
        **contract,
        "activity_rule": f"{value_column} > {ACTIVITY_THRESHOLD}",
        "periods": {
            "period_column": period_column,
            "value_column": value_column,
            "current_period": current_period,
            "previous_period": previous_period,
        },
    }
    result, audit = apply_period_derivations(
        frame,
        period_column=period_column,
        value_column=value_column,
        current_period=current_period,
        previous_period=previous_period,
        derived_dimensions=contract.get("derived_dimensions"),
        like_for_like=contract.get("like_for_like"),
    )
    audit["cohort_definition"] = effective_contract
    options = recipe.setdefault("options", {})
    options["cohort_definition"] = effective_contract
    options["recipe_cohort_audit"] = audit
    return result, audit


def add_comparison_cohort_columns(
    frame: pl.DataFrame,
    specs: Any,
    *,
    period_column: str,
    value_column: str,
    current_period: str = DEFAULT_CURRENT_PERIOD,
    previous_period: str = DEFAULT_PREVIOUS_PERIOD,
) -> tuple[pl.DataFrame, dict[str, Any]]:
    """Add derived cohort/lost columns from explicit AC/PY activity.

    Activity is a positive metric value in the requested period. This is a
    mechanically verifiable rule, so it belongs in preparation rather than in
    the interpretation layer.
    """

    normalized_specs = normalize_period_derivation_specs(specs)
    result = frame
    audits: list[dict[str, Any]] = []
    for index, spec in enumerate(normalized_specs):
        result, audit = _add_one_comparison_column(
            result,
            spec,
            period_column=period_column,
            value_column=value_column,
            current_period=current_period,
            previous_period=previous_period,
            index=index,
        )
        audits.append(audit)
    return result, {"status": "written", "derived_dimensions": audits}


def filter_like_for_like_entities(
    frame: pl.DataFrame,
    like_for_like: Any,
    *,
    period_column: str,
    value_column: str,
    current_period: str = DEFAULT_CURRENT_PERIOD,
    previous_period: str = DEFAULT_PREVIOUS_PERIOD,
) -> tuple[pl.DataFrame, dict[str, Any]]:
    """Keep entities with positive metric activity in both comparison periods."""

    spec = normalize_like_for_like_spec(like_for_like)
    if spec is None:
        return frame, {"status": "skipped", "reason": "not_requested"}
    source_dimension = str(spec["source_dimension"])
    _require_columns(frame, [source_dimension, period_column, value_column])
    entity_key = "__chart_harness_like_for_like_entity"
    keyed = _with_entity_key(frame, source_dimension, entity_key)
    activity = _activity_by_entity(
        keyed,
        entity_key=entity_key,
        period_column=period_column,
        value_column=value_column,
        current_period=current_period,
        previous_period=previous_period,
    )
    retained_entities = activity.filter(
        pl.col("_has_current") & pl.col("_has_previous")
    ).select(entity_key)
    filtered = keyed.join(retained_entities, on=entity_key, how="inner")
    filtered = _drop_existing(filtered, [entity_key])
    entity_count = get_row_count(activity)
    retained_count = get_row_count(retained_entities)
    return filtered, {
        "status": "written",
        "source_dimension": source_dimension,
        "period_column": period_column,
        "value_column": value_column,
        "current_period": current_period,
        "previous_period": previous_period,
        "activity_rule": f"{value_column} > {ACTIVITY_THRESHOLD}",
        "entity_count": entity_count,
        "retained_entity_count": retained_count,
        "removed_entity_count": entity_count - retained_count,
        "rows_before": get_row_count(frame),
        "rows_after": get_row_count(filtered),
    }


def apply_period_derivations(
    frame: pl.DataFrame,
    *,
    period_column: str,
    value_column: str,
    current_period: str = DEFAULT_CURRENT_PERIOD,
    previous_period: str = DEFAULT_PREVIOUS_PERIOD,
    derived_dimensions: Any = None,
    like_for_like: Any = None,
) -> tuple[pl.DataFrame, dict[str, Any]]:
    """Apply requested period derivations and return an audit."""

    result, derived_audit = add_comparison_cohort_columns(
        frame,
        derived_dimensions,
        period_column=period_column,
        value_column=value_column,
        current_period=current_period,
        previous_period=previous_period,
    )
    result, like_for_like_audit = filter_like_for_like_entities(
        result,
        like_for_like,
        period_column=period_column,
        value_column=value_column,
        current_period=current_period,
        previous_period=previous_period,
    )
    return result, {
        "status": "written",
        "cohort_columns": derived_audit,
        "like_for_like": like_for_like_audit,
        "rows_before": get_row_count(frame),
        "rows_after": get_row_count(result),
    }


def _add_one_comparison_column(
    frame: pl.DataFrame,
    spec: Mapping[str, Any],
    *,
    period_column: str,
    value_column: str,
    current_period: str,
    previous_period: str,
    index: int,
) -> tuple[pl.DataFrame, dict[str, Any]]:
    source_dimension = str(spec["source_dimension"])
    output_column = str(spec["name"])
    kind = str(spec["kind"])
    _require_columns(frame, [source_dimension, period_column, value_column])
    entity_key = f"__chart_harness_entity_{index}"
    keyed = _with_entity_key(frame, source_dimension, entity_key)
    periods = _ordered_period_values(
        keyed,
        period_column=period_column,
        current_period=current_period,
        previous_period=previous_period,
    )
    visible_periods = _recent_visible_periods(
        periods,
        current_period=current_period,
        visible_period_count=_visible_period_count(spec),
    )
    older_cutoff_rank = periods.index(visible_periods[0]) if visible_periods else 0
    activity = _activity_window_by_entity(
        keyed,
        entity_key=entity_key,
        period_column=period_column,
        value_column=value_column,
        current_period=current_period,
        periods=periods,
    )

    if kind == "since":
        label_expr = _since_label_expr(
            visible_periods=visible_periods,
            older_cutoff_rank=older_cutoff_rank,
            since_label=str(spec.get("since_label") or DEFAULT_SINCE_LABEL),
            inactive_label=str(spec.get("inactive_label") or DEFAULT_INACTIVE_LABEL),
        )
    else:
        label_expr = _lost_label_expr(
            visible_periods=visible_periods,
            older_cutoff_rank=older_cutoff_rank,
            lost_label=str(spec.get("lost_label") or DEFAULT_LOST_LABEL),
            active_label=str(spec.get("active_label") or DEFAULT_ACTIVE_LABEL),
            inactive_label=str(spec.get("inactive_label") or DEFAULT_INACTIVE_LABEL),
        )

    result = keyed.join(activity, on=entity_key, how="left").with_columns(
        label_expr.alias(output_column)
    )
    result = _drop_existing(
        result,
        [
            entity_key,
            "__chart_harness_first_active_period",
            "__chart_harness_first_active_rank",
            "__chart_harness_last_active_period",
            "__chart_harness_last_active_rank",
            "__chart_harness_has_current",
        ],
    )
    label_counts = (
        result.group_by(output_column)
        .agg(pl.len().alias("row_count"))
        .sort(output_column)
        .to_dicts()
    )
    entity_count = get_row_count(activity)
    return result, {
        "status": "written",
        "kind": kind,
        "cohort_mode": kind,
        "source_dimension": source_dimension,
        "output_column": output_column,
        "period_column": period_column,
        "value_column": value_column,
        "current_period": current_period,
        "previous_period": previous_period,
        "visible_periods": visible_periods,
        "older_period_bucket": (
            f"before {visible_periods[0]}"
            if visible_periods and older_cutoff_rank > 0
            else None
        ),
        "activity_rule": f"{value_column} > {ACTIVITY_THRESHOLD}",
        "entity_count": entity_count,
        "label_counts": label_counts,
    }


def _activity_by_entity(
    frame: pl.DataFrame,
    *,
    entity_key: str,
    period_column: str,
    value_column: str,
    current_period: str,
    previous_period: str,
) -> pl.DataFrame:
    active_expr = pl.col(value_column).cast(pl.Float64).fill_null(0.0)
    return frame.group_by(entity_key).agg(
        [
            (
                (pl.col(period_column).cast(pl.Utf8) == current_period)
                & (active_expr > ACTIVITY_THRESHOLD)
            )
            .any()
            .alias("_has_current"),
            (
                (pl.col(period_column).cast(pl.Utf8) == previous_period)
                & (active_expr > ACTIVITY_THRESHOLD)
            )
            .any()
            .alias("_has_previous"),
        ]
    )


def _activity_window_by_entity(
    frame: pl.DataFrame,
    *,
    entity_key: str,
    period_column: str,
    value_column: str,
    current_period: str,
    periods: list[str],
) -> pl.DataFrame:
    period_rank = pl.DataFrame(
        {
            period_column: periods,
            "__chart_harness_period_rank": list(range(len(periods))),
        }
    )
    active_expr = pl.col(value_column).cast(pl.Float64).fill_null(0.0)
    active = (
        frame.select([entity_key, period_column, value_column])
        .with_columns(pl.col(period_column).cast(pl.Utf8))
        .filter(active_expr > ACTIVITY_THRESHOLD)
        .select([entity_key, period_column])
        .unique()
        .join(period_rank, on=period_column, how="left")
    )
    entities = frame.select(entity_key).unique()
    if active.is_empty():
        return entities.with_columns(
            pl.lit(None, dtype=pl.Utf8).alias("__chart_harness_first_active_period"),
            pl.lit(None, dtype=pl.Int64).alias("__chart_harness_first_active_rank"),
            pl.lit(None, dtype=pl.Utf8).alias("__chart_harness_last_active_period"),
            pl.lit(None, dtype=pl.Int64).alias("__chart_harness_last_active_rank"),
            pl.lit(False).alias("__chart_harness_has_current"),
        )
    summary = active.group_by(entity_key).agg(
        [
            pl.col(period_column)
            .sort_by(pl.col("__chart_harness_period_rank"))
            .first()
            .alias("__chart_harness_first_active_period"),
            pl.col("__chart_harness_period_rank")
            .min()
            .alias("__chart_harness_first_active_rank"),
            pl.col(period_column)
            .sort_by(pl.col("__chart_harness_period_rank"))
            .last()
            .alias("__chart_harness_last_active_period"),
            pl.col("__chart_harness_period_rank")
            .max()
            .alias("__chart_harness_last_active_rank"),
            (pl.col(period_column) == current_period)
            .any()
            .alias("__chart_harness_has_current"),
        ]
    )
    return entities.join(summary, on=entity_key, how="left").with_columns(
        pl.col("__chart_harness_has_current").fill_null(False)
    )


def _since_label_expr(
    *,
    visible_periods: list[str],
    older_cutoff_rank: int,
    since_label: str,
    inactive_label: str,
) -> pl.Expr:
    first_period = "__chart_harness_first_active_period"
    first_rank = "__chart_harness_first_active_rank"
    prefix = f"{since_label} "
    expr = pl.when(pl.col(first_period).is_null()).then(pl.lit(inactive_label))
    if visible_periods and older_cutoff_rank > 0:
        expr = expr.when(pl.col(first_rank) < older_cutoff_rank).then(
            pl.lit(f"Before {visible_periods[0]}")
        )
    return expr.otherwise(pl.lit(prefix) + pl.col(first_period).cast(pl.Utf8))


def _lost_label_expr(
    *,
    visible_periods: list[str],
    older_cutoff_rank: int,
    lost_label: str,
    active_label: str,
    inactive_label: str,
) -> pl.Expr:
    last_period = "__chart_harness_last_active_period"
    last_rank = "__chart_harness_last_active_rank"
    has_current = "__chart_harness_has_current"
    after_prefix = f"{lost_label} after "
    expr = (
        pl.when(pl.col(has_current))
        .then(pl.lit(active_label))
        .when(pl.col(last_period).is_null())
        .then(pl.lit(inactive_label))
    )
    if visible_periods and older_cutoff_rank > 0:
        expr = expr.when(pl.col(last_rank) < older_cutoff_rank).then(
            pl.lit(f"{lost_label} before {visible_periods[0]}")
        )
    return expr.otherwise(pl.lit(after_prefix) + pl.col(last_period).cast(pl.Utf8))


def _visible_period_count(spec: Mapping[str, Any]) -> int:
    raw_value = (
        spec.get("visible_period_count")
        or spec.get("cohort_visible_period_count")
        or DEFAULT_COHORT_VISIBLE_PERIOD_COUNT
    )
    try:
        return max(1, int(raw_value))
    except (TypeError, ValueError):
        return DEFAULT_COHORT_VISIBLE_PERIOD_COUNT


def _ordered_period_values(
    frame: pl.DataFrame,
    *,
    period_column: str,
    current_period: str,
    previous_period: str,
) -> list[str]:
    raw_values = [
        str(value)
        for value in frame.select(pl.col(period_column).cast(pl.Utf8)).to_series()
        if value is not None
    ]
    values = list(dict.fromkeys(raw_values))
    if not values:
        return [previous_period, current_period]
    if all(_period_sort_key(value)[0] == 0 for value in values):
        values = sorted(values, key=_period_sort_key)
    if (
        current_period in values
        and previous_period in values
        and values.index(previous_period) > values.index(current_period)
    ):
        other_values = [
            value for value in values if value not in {previous_period, current_period}
        ]
        values = [*other_values, previous_period, current_period]
    return values


def _period_sort_key(value: str) -> tuple[int, int | str]:
    try:
        return (0, int(value))
    except ValueError:
        return (1, value)


def _recent_visible_periods(
    periods: list[str],
    *,
    current_period: str,
    visible_period_count: int,
) -> list[str]:
    if not periods:
        return [current_period]
    current_index = periods.index(current_period) if current_period in periods else -1
    end_index = current_index + 1 if current_index >= 0 else len(periods)
    start_index = max(0, end_index - visible_period_count)
    return periods[start_index:end_index]


def _with_entity_key(
    frame: pl.DataFrame, source_dimension: str, entity_key: str
) -> pl.DataFrame:
    return frame.with_columns(
        pl.col(source_dimension)
        .cast(pl.Utf8)
        .fill_null("Unspecified")
        .alias(entity_key)
    )


def _require_columns(frame: pl.DataFrame, required_columns: list[str]) -> None:
    columns, _schema = get_schema_and_column_names(frame)
    missing = [column for column in required_columns if column not in columns]
    if missing:
        raise ValueError(f"Missing required period derivation columns: {missing}")


def _drop_existing(frame: pl.DataFrame, columns: list[str]) -> pl.DataFrame:
    existing_columns, _schema = get_schema_and_column_names(frame)
    drop_columns = [column for column in columns if column in existing_columns]
    return frame.drop(drop_columns) if drop_columns else frame


def _normalize_cohort_payload(
    payload: Any,
) -> tuple[list[dict[str, Any]], dict[str, Any] | None, dict[str, Any] | None]:
    derived_dimensions: list[dict[str, Any]] = []
    like_for_like: dict[str, Any] | None = None
    periods: dict[str, Any] | None = None
    if isinstance(payload, list):
        for item in payload:
            item_derived, item_like, item_periods = _normalize_cohort_payload(item)
            derived_dimensions.extend(item_derived)
            if item_like is not None:
                like_for_like = item_like
            if item_periods is not None:
                periods = item_periods
        return derived_dimensions, like_for_like, periods
    if isinstance(payload, str):
        return [], normalize_like_for_like_spec(payload), None
    if not isinstance(payload, Mapping):
        raise ValueError("Recipe cohorts must be an object, list, or column name.")

    if isinstance(payload.get("periods"), Mapping):
        periods = {str(key): value for key, value in payload["periods"].items()}
    elif any(
        key in payload
        for key in (
            "period_column",
            "value_column",
            "current_period",
            "previous_period",
        )
    ):
        periods = {
            str(key): payload[key]
            for key in (
                "period_column",
                "value_column",
                "current_period",
                "previous_period",
            )
            if key in payload and payload[key] not in (None, "")
        }

    if payload.get("derived_dimensions") not in (None, False, [], {}):
        derived_dimensions.extend(
            normalize_period_derivation_specs(payload.get("derived_dimensions"))
        )
    if payload.get("like_for_like") not in (None, False, [], {}):
        like_for_like = normalize_like_for_like_spec(payload.get("like_for_like"))

    source_dimension = (
        payload.get("source_dimension")
        or payload.get("dimension")
        or payload.get("column")
    )
    if source_dimension:
        mode = (
            payload.get("cohort_mode")
            or payload.get("mode")
            or payload.get("kind")
            or payload.get("type")
            or "since"
        )
        normalized_mode = str(mode).lower().replace("-", "_").replace(" ", "_")
        if normalized_mode in {"like_for_like", "lfl"}:
            like_for_like = normalize_like_for_like_spec(payload)
        else:
            derived_dimensions.extend(normalize_period_derivation_specs(payload))
        return derived_dimensions, like_for_like, periods

    if not derived_dimensions and like_for_like is None:
        for key, value in payload.items():
            if key in {
                "periods",
                "period_column",
                "value_column",
                "current_period",
                "previous_period",
            }:
                continue
            if isinstance(value, str) and value.lower().replace("-", "_") in {
                "like_for_like",
                "lfl",
            }:
                like_for_like = normalize_like_for_like_spec({"source_dimension": key})
            elif isinstance(value, Mapping):
                item = {"source_dimension": key, **dict(value)}
                item_derived, item_like, _item_periods = _normalize_cohort_payload(item)
                derived_dimensions.extend(item_derived)
                if item_like is not None:
                    like_for_like = item_like
    return derived_dimensions, like_for_like, periods


def _dedupe_dicts(values: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    deduped: list[dict[str, Any]] = []
    seen: set[str] = set()
    for value in values:
        key = repr(sorted(value.items()))
        if key in seen:
            continue
        seen.add(key)
        deduped.append(value)
    return deduped


def _first_present(source: Mapping[str, Any], keys: Iterable[str]) -> Any:
    for key in keys:
        value = source.get(key)
        if value not in (None, "", [], {}):
            return value
    return None
