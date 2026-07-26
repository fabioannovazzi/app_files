import polars as pl

from modules.data.common_data_utils import (
    clean_column_labels_after_flatten_df,
    pivot_lazy,
)
from modules.utilities.config import get_naming_params
from modules.utilities.helpers import (
    drop_columns,
    duplicate_dataframe,
    flatten_cols_polars,
)
from modules.utilities.utils import (
    ensure_lazyframe,
    get_schema_and_column_names,
)


def prepare_data_for_timeline_plot(
    dfCopy, chosenDimension, metric, uniqueItems, chartDict
):
    namingParams = get_naming_params()
    dateName = namingParams["dateName"]
    periodChoice = namingParams["periodChoice"]
    yearName = namingParams["yearName"]
    periodToDate = namingParams["periodToDate"]
    invisibleCharacter = namingParams["invisibleCharacter"]
    timelineChart = namingParams["timelineChart"]
    chosenChart = namingParams["chosenChart"]
    chosenChart = chartDict[chosenChart]
    compareWithYearBefore = namingParams["compareWithYearBefore"]
    df_lazy = ensure_lazyframe(duplicate_dataframe(dfCopy))
    df_lazy = pivot_lazy(
        lf=df_lazy,
        index_col=dateName,
        pivot_col=chosenDimension,
        value_col=metric,
        agg_func="sum",
    )
    df_lazy = flatten_cols_polars(df_lazy, "")
    df_lazy, newCols = clean_column_labels_after_flatten_df(df_lazy, [metric])
    columns, _ = get_schema_and_column_names(df_lazy)
    if dateName in columns:
        df_lazy = df_lazy.sort(dateName)
    if (
        periodChoice in chartDict
        and chartDict[periodChoice] == yearName
        and chosenChart not in [timelineChart]
    ):
        if periodToDate in chartDict and not chartDict[periodToDate]:
            if (
                compareWithYearBefore in chartDict
                and not chartDict[compareWithYearBefore]
            ):
                df_lazy = df_lazy.with_columns(
                    (pl.col(dateName).cast(pl.Utf8) + invisibleCharacter).alias(
                        dateName
                    )
                )
    columns, _ = get_schema_and_column_names(df_lazy)
    check_items = [item for item in uniqueItems if item in columns]
    if check_items:
        sums = df_lazy.select([pl.col(c).sum().alias(c) for c in check_items]).collect(
            engine="streaming"
        )
        drop_cols = [c for c in check_items if -0.0001 < sums[c][0] < 0.0001]
        if drop_cols:
            df_lazy = drop_columns(df_lazy, drop_cols)
            for col in drop_cols:
                uniqueItems.remove(col)
    return ensure_lazyframe(df_lazy)


def prepare_data_for_slope_plot(
    dfCopy, chosenDimension, metric, uniqueItems, paramDict, chartDict
):
    """Pivot slope values while requiring one unambiguous label per plot cell."""

    namingParams = get_naming_params()
    periodChoice = namingParams["periodChoice"]
    yearName = namingParams["yearName"]
    periodToDate = namingParams["periodToDate"]
    periodName = namingParams["periodName"]
    labelName = namingParams["labelName"]
    invisibleCharacter = namingParams["invisibleCharacter"]
    compareWithYearBefore = namingParams["compareWithYearBefore"]
    totalName = namingParams["totalName"]
    valueCols = [metric, labelName]
    df_lazy = ensure_lazyframe(duplicate_dataframe(dfCopy))
    pivot_metric = pivot_lazy(
        lf=df_lazy,
        index_col=periodName,
        pivot_col=chosenDimension,
        value_col=metric,
        agg_func="sum",
    )
    # Metric duplicates are additive, but display labels are categorical. Collapse
    # repeated identical labels and fail when one period/dimension cell contains
    # conflicting non-null labels rather than selecting one by row order.
    label_count_col = "__slope_label_count"
    label_groups = df_lazy.group_by(
        [periodName, chosenDimension], maintain_order=True
    ).agg(
        pl.col(labelName).drop_nulls().n_unique().alias(label_count_col),
        pl.col(labelName).drop_nulls().first().alias(labelName),
    )
    conflicting_labels = (
        label_groups.filter(pl.col(label_count_col) > 1)
        .select(periodName, chosenDimension)
        .limit(1)
        .collect()
    )
    if not conflicting_labels.is_empty():
        raise ValueError(
            "Slope plot labels must agree within each period and dimension."
        )
    pivot_label = pivot_lazy(
        lf=label_groups.select(periodName, chosenDimension, labelName),
        index_col=periodName,
        pivot_col=chosenDimension,
        value_col=labelName,
        agg_func="first",
    )
    df_lazy = pivot_metric.join(pivot_label, on=periodName, how="left")
    df_lazy = flatten_cols_polars(df_lazy, "")
    df_lazy, newCols = clean_column_labels_after_flatten_df(df_lazy, [metric])
    df_lazy = df_lazy.with_columns(
        (pl.col(periodName).cast(pl.Utf8) + invisibleCharacter).alias(periodName)
    )
    columns, _ = get_schema_and_column_names(df_lazy)
    check_items = [item for item in uniqueItems if item in columns]
    if check_items:
        sums = (
            df_lazy.select([pl.col(c).sum().alias(c) for c in check_items])
            .collect(engine="streaming")
            .to_dict(as_series=False)
        )
        drop_cols = [c for c in check_items if -0.0001 < sums[c][0] < 0.0001]
        if drop_cols:
            df_lazy = drop_columns(df_lazy, drop_cols)
            for col in drop_cols:
                uniqueItems.remove(col)
    return ensure_lazyframe(df_lazy)
