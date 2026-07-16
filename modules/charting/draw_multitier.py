# isort: off
# fmt: off
import copy
import logging
import math

import numpy as np
import plotly.graph_objects as go
import polars as pl
from plotly.subplots import make_subplots


from modules.charting.chart_helpers import (
    get_pinhead_outliers,
    set_up_tab_for_show_or_download_chart,
)
from modules.charting.chart_primitives import (
    add_message_as_annotation,
    add_sign_to_labels,
    add_title_as_annotation,
    enable_draw_shapes,
    get_color_choice,
    get_color_dictionary,
    get_color_sequence,
    get_user_message,
    make_text_position_array,
    millify_dataframe,
    reset_row_and_column_counters,
)
from modules.charting.draw_charts_utils import (
    add_empty_rows_to_df,
    add_legends_to_horizontal_waterflow,
    add_negative_outlier_pins_to_column,
    add_percent_change_markers_to_column,
    add_positive_outlier_pins_to_column,
    add_separator_on_axis,
    get_maximum_number_of_items_in_small_multiples,
    get_text_template,
    keep_same_scale_for_all_plots,
)
from modules.charting.make_titles import (
    make_horizontal_waterfall_chart_title,
    make_multitier_bar_chart_title,
)
from modules.charting.prepare_charts import (
    check_if_key_in_dict,
    prepare_dataframe_for_forecast,
    resize_bars_and_recalculate_differences,
)
from modules.charting.setup_fig import (
    setup_fig_for_multitier_bar_charts,
    setup_fig_for_multitier_column_charts,
)
from modules.charting.update_layouts import (
    update_multitier_bar_layout,
    update_multitier_column_layout,
)
from modules.data.common_data_utils import show_only_largest
from modules.data.misc_charts_data_prep import (
    prepare_data_for_multitier_bar_plot,
    prepare_data_for_multitier_column_plot,
)
from modules.data.multidimensional_charts_prep import (
    add_empty_rows_if_hierarchical,
    add_empty_rows_if_not_hierarchical,
    sort_dataframe_in_correct_order,
)
from modules.utilities.config import (
    get_config_params,
    get_naming_params,
)
from modules.utilities.helpers import (
    drop_columns,
    duplicate_dataframe,
    get_periods_array,
    unique,
)
from modules.utilities import utils
from modules.utilities.utils import (
    get_schema_and_column_names,
    is_valid_lazyframe,
    ensure_polars_df,
    get_row_count,
)
from modules.utilities.ui_notifier import Notifier, NullNotifier
try:
    from modules.charting.polars_helpers import to_lists, unique_values_lazy
except Exception as e:  # pragma: no cover - fallback for tests lacking helper
    logging.exception(e)
    from modules.charting.polars_helpers import to_lists

    def unique_values_lazy(*_args, **_kwargs):
        return []


def _resolve_notifier(notifier: Notifier | None) -> Notifier:
    return notifier or NullNotifier()


def _normalize_multitier_export_frame(
    frame: pl.DataFrame | pl.LazyFrame,
    label_columns: list[str],
) -> pl.DataFrame | pl.LazyFrame:
    """Cast numeric export columns consistently before vertical concatenation."""

    columns, schema = get_schema_and_column_names(frame)
    label_column_set = set(label_columns)
    numeric_types = {
        pl.Int8,
        pl.Int16,
        pl.Int32,
        pl.Int64,
        pl.UInt8,
        pl.UInt16,
        pl.UInt32,
        pl.UInt64,
        pl.Float32,
        pl.Float64,
    }
    expressions = [
        pl.col(column).cast(pl.Float64).alias(column)
        for column in columns
        if column not in label_column_set and schema.get(column) in numeric_types
    ]
    if not expressions:
        return frame
    return frame.with_columns(expressions)


def _rank_repeat_array_by_size(
    dfCopy,
    repeatArray,
    chosenDimension,
    metricArray,
    periodColumn=None,
    periodOrder=None,
):
    namingParams = get_naming_params()
    aggregateOtherItemsName = namingParams["aggregateOtherItemsName"]
    repeatArray = list(repeatArray)
    if not repeatArray or not chosenDimension:
        return repeatArray
    otherItems = [
        item for item in repeatArray if aggregateOtherItemsName in str(item)
    ]
    normalItems = [
        item for item in repeatArray if aggregateOtherItemsName not in str(item)
    ]
    columns, _ = get_schema_and_column_names(dfCopy)
    if chosenDimension not in columns:
        return [*normalItems, *otherItems]
    metric = next((item for item in metricArray if item in columns), None)
    if metric is None:
        monetaryName = namingParams["monetaryLocalCurrencyName"]
        metric = monetaryName if monetaryName in columns else None
    if metric is None:
        return [*normalItems, *otherItems]

    lf = utils.ensure_lazyframe(dfCopy).filter(pl.col(chosenDimension).is_in(normalItems))
    if periodColumn and periodOrder and periodColumn in columns:
        currentPeriod = periodOrder[-1]
        currentLf = lf.filter(pl.col(periodColumn) == currentPeriod)
        if get_row_count(currentLf) > 0:
            lf = currentLf

    ranked = (
        lf
        .group_by(chosenDimension)
        .agg(pl.col(metric).sum().alias("__panel_size"))
        .sort([pl.col("__panel_size"), pl.col(chosenDimension)], descending=[True, False])
        .select(chosenDimension)
        .collect()
        .to_series()
        .to_list()
    )
    missingItems = [item for item in normalItems if item not in ranked]
    return [*ranked, *missingItems, *otherItems]


def _rank_multitier_bar_panels_by_plotted_current_period(
    dfCopy,
    repeatArray,
    chosenDimension,
    secondDimension,
    xColumn,
    metric,
    valueCols,
    chartDict,
    paramDict,
    periodOrder,
    globalUniqueItems,
):
    namingParams = get_naming_params()
    aggregateOtherItemsName = namingParams["aggregateOtherItemsName"]
    aggregateOtherItemsKey = namingParams["aggregateOtherItems"]
    globalUniqueItemsArrayKey = namingParams["globalUniqueItemsArray"]
    repeatArray = list(repeatArray)
    if not repeatArray:
        return repeatArray

    otherItems = [
        item for item in repeatArray if aggregateOtherItemsName in str(item)
    ]
    normalItems = [
        item for item in repeatArray if aggregateOtherItemsName not in str(item)
    ]
    panelScores = []
    for panel in normalItems:
        panelParamDict = copy.deepcopy(paramDict)
        panelParamDict[globalUniqueItemsArrayKey] = globalUniqueItems
        panelFrame = duplicate_dataframe(dfCopy).filter(pl.col(chosenDimension) == panel)
        hasGlobalOtherItem = any(
            aggregateOtherItemsName in str(item) for item in globalUniqueItems
        )
        aggregateOtherItems = chartDict["X"][aggregateOtherItemsKey]
        if globalUniqueItems and not (aggregateOtherItems and hasGlobalOtherItem):
            panelFrame = panelFrame.filter(pl.col(secondDimension).is_in(globalUniqueItems))
        if get_row_count(panelFrame) == 0:
            panelScores.append((panel, 0.0))
            continue
        prepared, _uniqueItems, _panelParamDict = prepare_data_for_multitier_bar_plot(
            panelFrame,
            secondDimension,
            xColumn,
            metric,
            valueCols,
            chartDict,
            panelParamDict,
            "X",
        )
        columns, _ = get_schema_and_column_names(prepared)
        scoreColumn = next(
            (period for period in reversed(periodOrder) if period in columns),
            None,
        )
        if scoreColumn is None:
            score = 0.0
        else:
            rawScore = (
                utils.ensure_lazyframe(prepared)
                .select(pl.col(scoreColumn).fill_null(0).sum())
                .collect()
                .item()
            )
            score = float(rawScore or 0.0)
        panelScores.append((panel, score))

    ranked = [
        panel
        for panel, _score in sorted(panelScores, key=lambda item: (-item[1], str(item[0])))
    ]
    missingItems = [item for item in normalItems if item not in ranked]
    return [*ranked, *missingItems, *otherItems]


def _lift_multitier_small_multiple_title(fig, title, chartDict):
    namingParams = get_naming_params()
    plotSmallMultiplesKey = namingParams["plotSmallMultiplesOtherCharts"]
    chosenChartKey = namingParams["chosenChart"]
    multitierBarChart = namingParams["multitierBarChart"]
    if (
        plotSmallMultiplesKey not in chartDict
        or not chartDict[plotSmallMultiplesKey]
        or chartDict[chosenChartKey] != multitierBarChart
    ):
        return fig

    for annotation in reversed(fig.layout.annotations or ()):
        if str(annotation.text) == str(title):
            annotation.y = 1.11
            annotation.yanchor = "bottom"
            break

    margin = fig.layout.margin.to_plotly_json() if fig.layout.margin else {}
    margin["t"] = max(int(margin.get("t") or 0), 95)
    margin["autoexpand"] = True
    fig.update_layout(margin=margin)
    return fig


































def adjust_multitier_column_plot(fig,df,key,metric,title,height,width,paramDict,chartDict,plotWithPins):
    namingParams=get_naming_params()
    configParams=get_config_params()
    fontSize=configParams[namingParams["fontSizeText"]] 
    font=configParams[namingParams["fontChoice"]]  
    chosenChart=namingParams["chosenChart"]
    chosenChart=chartDict[chosenChart]
    fig=update_multitier_column_layout(df,fig,height,width,paramDict,chartDict,plotWithPins) 
    fig,message=get_user_message(fig,chosenChart,metric,key,paramDict,chartDict,df,width,None)
    fig=add_message_as_annotation(fig,message,None,chosenChart,chartDict,paramDict)
    fig=add_title_as_annotation(fig,title,chosenChart,chartDict)
    fig=enable_draw_shapes(fig)
    fig.update_annotations(font=dict(size=fontSize,family=font))   
    return fig 


def add_absolute_value_bars_to_multitier_column(
    fig,
    df,
    metric,
    paramDict,
    offset,
    constant,
    colorSequenceArray,
    lineWidth,
    row,
    col,
    chartDict,
):
    """Add absolute PY/AC value bars to a multitier column chart."""
    lf = utils.ensure_lazyframe(df)
    namingParams = get_naming_params()
    configParams = get_config_params()
    columns, _ = get_schema_and_column_names(lf)
    fontSize = configParams[namingParams["fontSizeText"]]
    font = configParams[namingParams["fontChoice"]]
    dateName = namingParams["dateName"]
    labelName = namingParams["labelName"]
    pyName = namingParams["pyName"]
    acName = namingParams["acName"]
    plName = namingParams["plName"]
    fcName = namingParams["fcName"]
    averageName = namingParams["averageName"]
    workColumnTwo = namingParams["workColumnTwo"]
    plotSmallMultiplesKey = namingParams["plotSmallMultiplesOtherCharts"]
    multitierColumnChart = namingParams["multitierColumnChart"]
    horizontalWaterfallChart = namingParams["horizontalWaterfallChart"]
    compareScenarios = namingParams["compareScenarios"]
    compareScenariosOrPeriods = namingParams["compareScenariosOrPeriods"]
    chosenChart = namingParams["chosenChart"]
    absoluteName = namingParams["absoluteName"]
    measureName = namingParams["measureName"]
    chosenChart = chartDict[chosenChart]
    texttemplate = " %{customdata:,.3s}"

    # ---- All transformations are applied lazily and materialized once ----
    anchos = [0.68] * constant
    orientation = "v"

    if plName in columns:
        pyName = plName
    if acName in columns:
        lf, chartDict = millify_dataframe(lf, acName, None, labelName, chartDict)
    else:
        lf = lf.with_columns(pl.lit(None).alias(labelName))

    if pyName in columns:
        lf, chartDict = millify_dataframe(lf, pyName, None, workColumnTwo, chartDict)
    else:
        lf = lf.with_columns(pl.lit(None).alias(workColumnTwo))

    if chosenChart in [multitierColumnChart]:
        lf = lf.with_columns(
            pl.when(pl.col(dateName).is_not_null())
            .then(pl.concat_str([pl.lit("  "), pl.col(dateName)]))
            .otherwise(pl.col(dateName))
            .alias(dateName)
        )

    if fcName in columns:
        lf = lf.with_columns(
            pl.when(pl.col(fcName) > 0)
            .then(pl.lit(None))
            .otherwise(pl.col(labelName))
            .alias(labelName)
        )

    colorDict = get_color_dictionary(chartDict)
    texttemplate, textformat = get_text_template(chartDict)

    if plotSmallMultiplesKey in chartDict and chartDict[plotSmallMultiplesKey] and chosenChart == horizontalWaterfallChart:
        lf = lf.with_columns(
            pl.when(pl.col(measureName) == absoluteName)
            .then(pl.lit(np.nan))
            .otherwise(pl.col(pyName))
            .alias(pyName)
        )

    lf = lf.with_columns(
        pl.when(pl.col(labelName).cast(pl.Utf8).is_in(["0", "0.0", ""]))
        .then(pl.lit(None))
        .otherwise(pl.col(labelName))
        .alias(labelName)
    )

    if acName in columns:
        lf = lf.with_columns(
            pl.when(pl.col(acName) == 0)
            .then(pl.lit(None))
            .otherwise(pl.col(acName))
            .alias(acName)
        )

    # Materialize once after all lazy transformations
    columns, _ = get_schema_and_column_names(lf)
    df = lf.collect(engine="streaming")

    if pyName in columns:
        fig.add_trace(
            go.Bar(
                x=df[dateName],
                y=df[pyName],
                marker=dict(
                    color=colorSequenceArray[0],
                    line=dict(color=colorDict["lightGreyColor"], width=lineWidth),
                ),
                width=anchos,
                name=pyName,
                orientation=orientation,
                hovertext=df[workColumnTwo],
                showlegend=False,
            ),
            row=row,
            col=col,
        )

    if compareScenariosOrPeriods in chartDict and chartDict[compareScenariosOrPeriods] == compareScenarios:
        has_fc = (
            df.select(pl.col(fcName).sum().alias("_sum")).collect().to_series(0).item()
            if fcName in columns
            else 0
        )
        if fcName in columns and has_fc > 0:
            fig = add_forecast_bars_to_multitier_column(
                fig,
                df,
                lineWidth,
                offset,
                constant,
                colorSequenceArray,
                metric,
                chartDict,
                row,
                col,
            )

    text = df[labelName]
    if plotSmallMultiplesKey in chartDict and chartDict[plotSmallMultiplesKey] and chosenChart == multitierColumnChart:
        text = ""
        texttemplate = None

    if acName in columns:
        fig.add_trace(
            go.Bar(
                x=df[dateName],
                y=df[acName],
                marker=dict(
                    color=colorSequenceArray[1],
                    line=dict(color=colorSequenceArray[1], width=lineWidth),
                ),
                offset=offset,
                text=text,
                texttemplate=texttemplate,
                hovertext=df[labelName],
                textposition="outside",
                width=anchos,
                name=acName,
                orientation=orientation,
                showlegend=False,
                cliponaxis=False,
            ),
            row=row,
            col=col,
        )

    return fig, df, chartDict

def add_forecast_bars_to_multitier_column(
    fig,
    dfCopy,
    lineWidth,
    offset,
    constant,
    colorSequenceArray,
    metric,
    chartDict,
    row,
    col,
):
    namingParams = get_naming_params()
    configParams = get_config_params()
    chosenChart = namingParams["chosenChart"]
    fontSize = configParams[namingParams["fontSizeText"]]
    font = configParams[namingParams["fontChoice"]]
    dateName = namingParams["dateName"]
    labelName = namingParams["labelName"]
    acName = namingParams["acName"]
    plName = namingParams["plName"]
    fcName = namingParams["fcName"]
    colorName = namingParams["colorName"]
    averageName = namingParams["averageName"]
    differenceInValue = namingParams["differenceInValue"]
    differenceInPercent = namingParams["differenceInPercent"]
    discountName = namingParams["discountName"]
    indirectCostsName = namingParams["indirectCostsName"]
    varianceAmountName = namingParams["varianceAmountName"]
    plotSmallMultiplesKey = namingParams["plotSmallMultiplesOtherCharts"]
    horizontalWaterfallChart = namingParams["horizontalWaterfallChart"]
    cogsName = namingParams["cogsName"]
    workColumn = namingParams["workColumn"]
    workColumnThree = namingParams["workColumnThree"]
    workColumnFour = namingParams["workColumnFour"]
    workColumnSix = namingParams["workColumnSix"]

    chosenChart = chartDict[chosenChart]
    anchos = [0.68] * constant
    orientation = "v"
    reverseColorMetricsArray = [discountName, indirectCostsName, cogsName]

    # Work entirely with LazyFrames to avoid multiple materialisations
    lf = utils.ensure_lazyframe(dfCopy)
    columns, _ = get_schema_and_column_names(lf)

    if chosenChart in [horizontalWaterfallChart]:
        fc_sum_lf = lf.select(pl.col(fcName).sum().alias("__fc_sum"))
        lf = (
            lf.join(fc_sum_lf, how="cross")
            .with_columns(
                pl.lit(None).alias(workColumnFour),
                pl.lit(None).alias(workColumnSix),
            )
            .with_columns(
                pl.when(pl.col(workColumn) == acName)
                .then(pl.col(varianceAmountName))
                .otherwise(pl.col(workColumnFour))
                .alias(workColumnFour),
                pl.when(pl.col(workColumn) == acName)
                .then(pl.col("__fc_sum") + pl.col(varianceAmountName))
                .otherwise(pl.col(workColumnSix))
                .alias(workColumnSix),
                pl.when(pl.col(workColumn) == acName)
                .then(pl.lit(acName))
                .otherwise(pl.col(dateName))
                .alias(dateName),
            )
            .drop("__fc_sum")
        )

    lf = lf.with_columns(pl.lit(None).alias(workColumnThree))
    lf = lf.with_columns(
        pl.when((pl.col(fcName) > 0) & (pl.col(dateName) != averageName))
        .then(pl.col(fcName) - pl.col(plName))
        .otherwise(pl.col(differenceInValue))
        .alias(differenceInValue)
    )
    lf = lf.with_columns(
        pl.when((pl.col(fcName) > 0) & (pl.col(plName) > 0) & (pl.col(dateName) != averageName))
        .then(((pl.col(fcName) - pl.col(plName)) / pl.col(plName) * 100).round(0))
        .otherwise(pl.col(differenceInPercent))
        .alias(differenceInPercent)
    )
    lf = lf.with_columns(
        pl.when((pl.col(fcName) > 0) & (pl.col(dateName) != averageName))
        .then(1)
        .otherwise(pl.col(workColumnThree))
        .alias(workColumnThree)
    )

    if metric not in reverseColorMetricsArray:
        lf = lf.with_columns(
            pl.when(pl.col(workColumnThree) == 1)
            .then(1)
            .otherwise(pl.col(colorName))
            .alias(colorName)
        )
        lf = lf.with_columns(
            pl.when((pl.col(workColumnThree) == 1) & (pl.col(fcName) > pl.col(plName)))
            .then(0)
            .otherwise(pl.col(colorName))
            .alias(colorName)
        )
    else:
        lf = lf.with_columns(
            pl.when(pl.col(workColumnThree) == 1)
            .then(0)
            .otherwise(pl.col(colorName))
            .alias(colorName)
        )
        lf = lf.with_columns(
            pl.when((pl.col(workColumnThree) == 1) & (pl.col(fcName) > pl.col(plName)))
            .then(1)
            .otherwise(pl.col(colorName))
            .alias(colorName)
        )

    if chosenChart in horizontalWaterfallChart:
        lf, chartDict = millify_dataframe(lf, fcName, None, labelName, chartDict)
    else:
        lf = drop_columns(lf, [workColumnThree])

    lf = lf.with_columns(
        pl.when(pl.col(labelName) == "0.0")
        .then(pl.lit(None))
        .otherwise(pl.col(labelName))
        .alias(labelName)
    )
    lf = lf.with_columns(
        pl.when(pl.col(labelName) == 0)
        .then(pl.lit(None))
        .otherwise(pl.col(labelName))
        .alias(labelName),
        pl.when(pl.col(fcName) == 0)
        .then(pl.lit(None))
        .otherwise(pl.col(fcName))
        .alias(fcName),
    )

    if plotSmallMultiplesKey in chartDict and chartDict[plotSmallMultiplesKey]:
        pass
    else:
        lf, chartDict = millify_dataframe(lf, fcName, None, labelName, chartDict)

    texttemplate, textformat = get_text_template(chartDict)

    # Collect once and compute row count lazily
    df = lf.collect(engine="streaming")
    _row_count = get_row_count(df)
    text = df[labelName]

    fig.add_trace(
        go.Bar(
            x=df[dateName],
            y=df[fcName],
            marker_pattern_shape="/",
            marker_pattern_bgcolor=colorSequenceArray[0],
            marker_pattern_fgcolor=colorSequenceArray[1],
            marker_pattern_fgopacity=1,
            marker_pattern_size=2.5,
            marker=dict(line=dict(color=colorSequenceArray[1], width=lineWidth)),
            offset=offset,
            width=anchos,
            name=acName,
            orientation=orientation,
            showlegend=False,
            cliponaxis=False,
            text=text,
            texttemplate=texttemplate,
            hovertext=df[labelName],
            textposition="outside",
        ),
        row=row,
        col=col,
    )

    if chosenChart in [horizontalWaterfallChart]:
        anchos = [0.79] * constant
        offset = -0.364
        text = df[labelName]
        fig.add_trace(
            go.Bar(
                x=df[dateName],
                y=df[workColumnSix],
                marker_pattern_shape="/",
                marker_pattern_bgcolor=colorSequenceArray[0],
                marker_pattern_fgcolor=colorSequenceArray[1],
                marker_pattern_fgopacity=1,
                marker_pattern_size=2.5,
                marker=dict(line=dict(color=colorSequenceArray[1], width=lineWidth)),
                offset=offset,
                width=anchos,
                name=acName,
                orientation=orientation,
                showlegend=False,
                cliponaxis=False,
                text=text,
                texttemplate=texttemplate,
                hovertext=df[labelName],
                textposition="outside",
            ),
            row=row,
            col=col,
        )
        fig.add_trace(
            go.Bar(
                x=df[dateName],
                y=df[workColumnFour],
                marker=dict(
                    color=colorSequenceArray[1],
                    line=dict(color=colorSequenceArray[1], width=lineWidth),
                ),
                offset=offset,
                textposition="outside",
                textfont_color="black",
                textangle=0,
                text=None,
                texttemplate=texttemplate,
                hovertext=df[labelName],
                width=anchos,
                name=acName,
                orientation=orientation,
                showlegend=False,
                cliponaxis=False,
            ),
            row=row,
            col=col,
        )
        fig = add_legends_to_horizontal_waterflow(fig, df, chartDict, row, col)

    return fig, df
def add_forecast_absolute_change_markers_to_multitier_column(fig,df,colorChoice,constant,chartDict,row,col):
    namingParams=get_naming_params()
    configParams=get_config_params()
    fontSize=configParams[namingParams["fontSizeText"]]   
    font=configParams[namingParams["fontChoice"]] 
    dateName=namingParams["dateName"]  
    colorName=namingParams["colorName"]    
    fcName=namingParams["fcName"]    
    averageName=namingParams["averageName"]    
    differenceInValue=namingParams["differenceInValue"]
    differenceInPercent=namingParams["differenceInPercent"]
    workColumn=namingParams["workColumn"] 
    labelName=namingParams["labelName"] 
    multitierColumnChart=namingParams["multitierColumnChart"] 
    anchosDiff = [0.68] * constant
    orientation="v"
    lf = utils.ensure_lazyframe(df).with_columns(pl.lit(None).alias(workColumn))
    lf = lf.with_columns(
        pl.when((pl.col(fcName) > 0) & (pl.col(dateName) != averageName))
        .then(pl.col(differenceInValue))
        .otherwise(pl.col(workColumn))
        .alias(workColumn)
    )
    lf = lf.with_columns(
        pl.when((pl.col(fcName) != 0) & (pl.col(dateName) != averageName))
        .then(pl.lit(None))
        .otherwise(pl.col(differenceInValue))
        .alias(differenceInValue)
    )
    lf = lf.with_columns(
        pl.when((pl.col(fcName) == 0) & (pl.col(dateName) != averageName))
        .then(pl.lit(None))
        .otherwise(pl.col(labelName))
        .alias(labelName)
    )
    lf, myDict = add_sign_to_labels(
        lf, multitierColumnChart, differenceInValue, 1, False, chartDict
    )
    df = lf.collect(engine="streaming")
    lineWidth=1
    colorList=list(map(colorChoice, df[colorName]))
    fig.add_trace(go.Bar(
                            x = df[dateName], 
                            y = df[workColumn],
                            text=df[labelName],
                            textposition='outside',
                            offset=-.205,                         
                            marker=dict(
                                color=colorList,
                                line=dict(color=colorList, width=lineWidth),
                                pattern=dict(
                                    shape="/",
                                    fgopacity=1,
                                    size=2.5,
                                    bgcolor="#FFFFFF",
                                    fgcolor="#FFFFFF",
                                    fillmode="replace"
                                    )),                         
                            width = anchosDiff,         
                            orientation=orientation,
                            showlegend=False,
                                 ),
                                row=row, col=col
                                 )
    return fig,df

            
def add_legends_to_multitier_column(
    figure: go.Figure,
    df: pl.DataFrame | pl.LazyFrame,
    chartDict: dict,
    pyName: str,
    fcName: str,
    constant: int,
    row: int,
    col: int,
) -> go.Figure:
    """Add legend annotations for multitier column charts."""

    namingParams = get_naming_params()
    plotSmallMultiplesKey = namingParams["plotSmallMultiplesOtherCharts"]
    deltaName = namingParams["deltaName"]
    acName = namingParams["acName"]

    columns, _ = get_schema_and_column_names(df)

    select_fields: list[str] = [c for c in (pyName, acName, fcName) if c and c in columns]
    lf = utils.ensure_lazyframe(df)

    exprs: list[pl.Expr] = []
    if pyName in select_fields:
        exprs.append((pl.col(pyName).first() * 0.5).alias("_py_y"))
    if acName in select_fields:
        exprs.append(pl.col(acName).first().alias("_ac_y"))
    if fcName and fcName in select_fields:
        exprs.append(
            pl.when(pl.len() > 2)
            .then(pl.col(fcName).tail(3).first())
            .otherwise(pl.col(fcName).first())
            .mul(0.5)
            .alias("_fc_y")
        )
        exprs.append(
            pl.when(pl.len() > 2).then(pl.len() - 2).otherwise(pl.lit(0)).alias("_fc_x")
        )

    collected = lf.select(exprs).collect(engine="streaming")

    if pyName in select_fields:
        align = "center"
        yShift = 0
        yref = "y"
        y = collected[0, "_py_y"]
        xref = "x"
        x = 0
        ax = x
        xShift = -20
        figure.add_annotation(
            text=pyName,
            showarrow=False,
            align=align,
            yshift=yShift,
            yref=yref,
            y=y,
            ax=ax,
            x=x,
            xref=xref,
            xshift=xShift,
            hovertext=pyName,
            row=row,
            col=col,
        )

    if acName in select_fields:
        align = "center"
        yShift = 0
        yref = "y"
        y = collected[0, "_ac_y"]
        xref = "x"
        x = 0
        ax = x
        xShift = -17
        figure.add_annotation(
            text=acName,
            showarrow=False,
            align=align,
            yshift=yShift,
            yref=yref,
            y=y,
            ax=ax,
            x=x,
            xref=xref,
            xshift=xShift,
            hovertext=acName,
            row=row,
            col=col,
        )

    if fcName and fcName in select_fields:
        align = "center"
        yShift = 0
        yref = "y"
        y = collected[0, "_fc_y"]
        xref = "x"
        x = int(collected[0, "_fc_x"])
        ax = x
        xShift = -10
        figure.add_annotation(
            text=fcName,
            showarrow=False,
            align=align,
            yshift=yShift,
            yref=yref,
            y=y,
            ax=ax,
            x=x,
            xref=xref,
            xshift=xShift,
            hovertext=fcName,
            row=row,
            col=col,
        )
    align="center"
    yShift=10 
    yref="paper"
    y=0         
    xref="x"       
    x=0
    ax=x 
    xShift=-22 
    if plotSmallMultiplesKey in chartDict and chartDict[plotSmallMultiplesKey]:
        pass
    else:    
        figure.add_annotation(
            text=deltaName+"%",
            #font=dict(size=8,),
            showarrow = False,
            align=align,
            yshift=yShift,
            yref=yref, 
            y=y,
            ax=ax,
            x=x,
            xref=xref, 
            xshift=xShift,
            hovertext=pyName,
            row=1,col=col,
                       )
        xshift=-25    
        figure.add_annotation(
            text=deltaName,
            #font=dict(size=8,),
            showarrow = False,
            align=align,
            yshift=yShift,
            yref=yref, 
            y=y,
            ax=ax,
            x=x,
            xref=xref, 
            xshift=xShift,
            hovertext=pyName,
            row=2,col=col,
                       ) 
    return figure

def add_absolute_change_markers_to_multitier_column(fig,df,colorChoice,constant,offset,chartDict,row,col):
    namingParams=get_naming_params()
    configParams=get_config_params()
    fontSize=configParams[namingParams["fontSizeText"]]
    font=configParams[namingParams["fontChoice"]]
    dateName=namingParams["dateName"]  
    colorName=namingParams["colorName"]    
    differenceInValue=namingParams["differenceInValue"]
    labelName=namingParams["labelName"]
    multitierColumnChart=namingParams["multitierColumnChart"] 
    anchosDiff = [0.68] * constant
    orientation="v"
    df,myDict=add_sign_to_labels(df,multitierColumnChart,differenceInValue,1,False,chartDict,)
    fig.add_trace(go.Bar(
                            x = df[dateName], 
                            y = df[differenceInValue],
                            text=df[labelName],
                            textposition='outside',                               
                            marker=dict(
                                color=list(map(colorChoice, df[colorName]))
                                    ), 
                            width = anchosDiff,
                            name = differenceInValue,           
                            orientation=orientation,
                            offset=offset,
                            showlegend=False,
                            cliponaxis = False,
                                 ),
                                row=row, col=col
                                 )

    return fig,chartDict







def add_annotations_to_multitier_column_plot(
    fig,
    df,
    metric,
    colorDict,
    chartDict,
    paramDict,
    row,
    col,
    plotWithPins,
):
    namingParams=get_naming_params()     
    pyName=namingParams["pyName"]  
    plName=namingParams["plName"]
    fcName=namingParams["fcName"]
    workColumnTwo=namingParams["workColumnTwo"]
    workColumn=namingParams["workColumn"]
    labelName=namingParams["labelName"]
    plotSmallMultiplesKey=namingParams["plotSmallMultiplesOtherCharts"]
    compareScenarios=namingParams["compareScenarios"]
    compareScenariosOrPeriods=namingParams["compareScenariosOrPeriods"]
    colorSequenceArray,lineWidth=get_color_sequence(df,paramDict,chartDict)
    colorChoice=get_color_choice(chartDict) 
    columns,schema=get_schema_and_column_names(df)
    if plotWithPins or plotSmallMultiplesKey not in chartDict or not chartDict[plotSmallMultiplesKey]:
        row,col=3,1
    if plName in columns:
        pyName=plName 
    constant=24 
    offset=-0.2 #offset=0.0005 
    fig,df,chartDict=add_absolute_value_bars_to_multitier_column(fig,df,metric,paramDict,offset,constant,colorSequenceArray,lineWidth,row,col,chartDict) 
    if plotSmallMultiplesKey in chartDict and chartDict[plotSmallMultiplesKey]: 
        # Polars: initialize work column with nulls (avoid pandas-style NaN)
        df = df.with_columns(pl.lit(None).alias(workColumn))
        columns,schema=get_schema_and_column_names(df)
        has_fc = (
            df.select(pl.col(fcName).sum().alias("_sum")).collect().to_series(0).item()
            if fcName in columns
            else 0
        )
        if fcName in columns and has_fc > 0:
            df,chartDict=millify_dataframe(df,fcName,None,workColumn,chartDict)
            df = df.with_columns(
                pl.when(pl.col(fcName) != 0)
                .then(pl.col(workColumn))
                .otherwise(pl.col(labelName))
                .alias(labelName)
            )
        fig=add_variance_annotations_to_multitier_column(df,fig,chartDict,pyName,row,col)
        fig=add_separator_on_axis(fig,df,0,"y domain",row,col)
    forecast=False
    if compareScenariosOrPeriods in chartDict and chartDict[compareScenariosOrPeriods]==compareScenarios:
        columns,schema=get_schema_and_column_names(df)
        has_fc = (
            df.select(pl.col(fcName).sum().alias("_sum")).collect().to_series(0).item()
            if fcName in columns
            else 0
        )
        if fcName in columns and has_fc > 0:
          forecast=True
        else:
            fcName=None
    else:
        fcName=None
    if plotWithPins or plotSmallMultiplesKey not in chartDict or not chartDict[plotSmallMultiplesKey]: 
        if forecast:
            fig,df=add_forecast_absolute_change_markers_to_multitier_column(fig,df,colorChoice,constant,chartDict,2,col)
        fig=add_separator_on_axis(fig,df,-.000001,"paper",1,col)    
        fig,chartDict=add_absolute_change_markers_to_multitier_column(fig,df,colorChoice,constant,offset,chartDict,2,col)            
        df, largestArray, smallestArray, chartDict = get_pinhead_outliers(df, chartDict)
        df = ensure_polars_df(df)
        fig=add_separator_on_axis(fig,df,0,"y",2,col) 
        fig=add_percent_change_markers_to_column(fig,df,colorChoice,lineWidth,constant)   
        fig=add_positive_outlier_pins_to_column(fig,df,largestArray,colorDict,1)
        fig=add_negative_outlier_pins_to_column(fig,df,smallestArray,colorDict,1)  
        fig=add_legends_to_multitier_column(fig,df,chartDict,pyName,fcName,constant,row,col)           
    else:
        pass
        fig=add_legends_to_multitier_column(fig,df,chartDict,pyName,fcName,constant,row,col)
    fig=add_separator_on_axis(fig,df,0,"y domain",row,col)
    return fig, df, chartDict

def draw_multitier_column_chart(dfCopy,chosenDimension,metricArray,repeatArray,paramDict,chartDict):
    """
    in order to show green where it goes better and red where worse, e need to build a dataframe
    with the differences
    """
    namingParams=get_naming_params()
    configParams=get_config_params()
    fontSize=configParams[namingParams["fontSizeText"]] 
    font=configParams[namingParams["fontChoice"]]
    trendComparisonByPeriodChart=namingParams["trendComparisonByPeriodChart"] 
    numberOfPlots=namingParams["numberOfPlots"]
    chosenChart=namingParams["chosenChart"]
    periodName=namingParams["periodName"]
    plName=namingParams["plName"]
    pyName=namingParams["pyName"]  
    acName=namingParams["acName"]
    plotSmallMultiplesKey=namingParams["plotSmallMultiplesOtherCharts"]    
    chosenChart=chartDict[chosenChart]
    configPlotlyDict=configParams["configPlotlyDict"]
    exportDataArray=[] 
    configPlotlyDict=configPlotlyDict[chosenChart]
    colorDict=get_color_dictionary(chartDict)
    numberOfMetrics=len(metricArray)
    count,countRows,countCols=1,1,1
    plotWithPins=False
    if chosenDimension == None and numberOfMetrics ==1:
        plotWithPins=True     
    key=None
    if is_valid_lazyframe(dfCopy):
        dfCopy = utils.ensure_lazyframe(dfCopy)
        repeatArrayToPlot = list(repeatArray)
        columns, schema = get_schema_and_column_names(dfCopy)
        if plotSmallMultiplesKey in chartDict and chartDict[plotSmallMultiplesKey]:
            fig, height, width, numberOfCols, numberOfRows = setup_fig_for_multitier_column_charts(
                repeatArrayToPlot, chosenDimension, paramDict, chartDict, plotWithPins
            )
        if chosenDimension in columns:
            paramDict[numberOfPlots] = len(repeatArray)
            # fullFig=False
            # metricType=False
            # same scale does not work here because Other Rank > is plotted as last
            for column in repeatArray:
                df = dfCopy.filter(pl.col(chosenDimension) == column)
                periodsArray = get_periods_array(df)
                if plName in periodsArray:
                    pyName = plName
                df = drop_columns(df, [chosenDimension])
                for metric in metricArray:
                    if plotSmallMultiplesKey not in chartDict or not chartDict[plotSmallMultiplesKey]:
                        (
                            fig,
                            height,
                            width,
                            numberOfCols,
                            numberOfRows,
                        ) = setup_fig_for_multitier_column_charts(
                            repeatArrayToPlot,
                            chosenDimension,
                            paramDict,
                            chartDict,
                            plotWithPins,
                        )
                    df = prepare_data_for_multitier_column_plot(
                        df, column, metric, chartDict, paramDict
                    )
                    exportDataArray.append(df)
                    fig, df_plot, chartDict = add_annotations_to_multitier_column_plot(
                        fig,
                        df,
                        metric,
                        colorDict,
                        chartDict,
                        paramDict,
                        countRows,
                        countCols,
                        plotWithPins,
                    )
                    (
                        count,
                        countRows,
                        countCols,
                        chartDict,
                    ) = reset_row_and_column_counters(
                        count, countCols, countRows, numberOfCols, numberOfRows, chartDict
                    )
                    fig.update_annotations(font=dict(size=fontSize, family=font))
                    if plotSmallMultiplesKey not in chartDict or not chartDict[plotSmallMultiplesKey]:
                        key = chosenDimension + column
                        titleColumn = chosenDimension + ": " + column
                        (
                            title,
                            paramDict,
                            chartDict,
                        ) = make_horizontal_waterfall_chart_title(
                            df,
                            chosenChart,
                            paramDict,
                            titleColumn,
                            metric,
                            chartDict,
                            pyName,
                            acName,
                        )
                        # fig,fullFig,metricType=keep_same_scale_for_all_plots(fig,metric,metricType,fullFig,"Y")
                        # same scale does not work here because Other Rank > is plotted as last
                        fig = adjust_multitier_column_plot(
                            fig,
                            df_plot,
                            key,
                            metric,
                            title,
                            height,
                            width,
                            paramDict,
                            chartDict,
                            plotWithPins,
                        )
                        paramDict = set_up_tab_for_show_or_download_chart(
                            df_plot,
                            fig,
                            configPlotlyDict,
                            chartDict,
                            chosenDimension + column + metric,
                            False,
                            None,
                            chosenDimension,
                            paramDict,
                        )
        else:
            paramDict[numberOfPlots] = len(metricArray)
            has_pl = dfCopy.select(pl.col(periodName).eq(plName).any())
            if has_pl.collect().to_series(0).item():
                pyName = plName
            for metric in metricArray:
                df = dfCopy
                if plotSmallMultiplesKey not in chartDict or not chartDict[plotSmallMultiplesKey]:
                    (
                        fig,
                        height,
                        width,
                        numberOfCols,
                        numberOfRows,
                    ) = setup_fig_for_multitier_column_charts(
                        repeatArrayToPlot,
                        chosenDimension,
                        paramDict,
                        chartDict,
                        plotWithPins,
                    )
                df = prepare_data_for_multitier_column_plot(
                    df, chosenDimension, metric, chartDict, paramDict
                )
                fig, df_plot, chartDict = add_annotations_to_multitier_column_plot(
                    fig,
                    df,
                    metric,
                    colorDict,
                    chartDict,
                    paramDict,
                    countRows,
                    countCols,
                    plotWithPins,
                )
                (
                    count,
                    countRows,
                    countCols,
                    chartDict,
                ) = reset_row_and_column_counters(
                    count, countCols, countRows, numberOfCols, numberOfRows, chartDict
                )
                fig.update_annotations(font=dict(size=fontSize, family=font))
                if plotSmallMultiplesKey not in chartDict or not chartDict[plotSmallMultiplesKey]:
                    (
                        title,
                        paramDict,
                        chartDict,
                    ) = make_horizontal_waterfall_chart_title(
                        df,
                        chosenChart,
                        paramDict,
                        "",
                        metric,
                        chartDict,
                        pyName,
                        acName,
                    )
                    fig = adjust_multitier_column_plot(
                        fig,
                        df_plot,
                        key,
                        metric,
                        title,
                        height,
                        width,
                        paramDict,
                        chartDict,
                        plotWithPins,
                    )
                    key = metric
                    if chosenDimension:
                        key = chosenDimension + metric
                    paramDict = set_up_tab_for_show_or_download_chart(
                        df_plot,
                        fig,
                        configPlotlyDict,
                        chartDict,
                        key,
                        False,
                        None,
                        chosenDimension,
                        paramDict,
                    )
        if plotSmallMultiplesKey in chartDict and chartDict[plotSmallMultiplesKey]:
            key = chosenDimension
            (
                title,
                paramDict,
                chartDict,
            ) = make_horizontal_waterfall_chart_title(
                df,
                chosenChart,
                paramDict,
                key,
                metric,
                chartDict,
                pyName,
                acName,
            )
            fig = adjust_multitier_column_plot(
                fig,
                df_plot,
                key,
                metric,
                title,
                height,
                width,
                paramDict,
                chartDict,
                plotWithPins,
            )
            key = metric
            if chosenDimension:
                key = chosenDimension + metric
                if len(exportDataArray) > 1:
                    df_plot = pl.concat(exportDataArray, how="vertical")
            paramDict = set_up_tab_for_show_or_download_chart(
                df_plot,
                fig,
                configPlotlyDict,
                chartDict,
                key,
                False,
                None,
                chosenDimension,
                paramDict,
            )
    return paramDict   


def adjust_multitier_bar_plot(fig,df,key,column,metric,title,periodOrder,uniqueItems,height,width,paramDict,chartDict):
    namingParams=get_naming_params()
    configParams=get_config_params()
    fontSize=configParams[namingParams["fontSizeText"]] 
    font=configParams[namingParams["fontChoice"]]
    chosenChart=namingParams["chosenChart"] 
    chosenChart=chartDict[chosenChart]
    fig=update_multitier_bar_layout(fig,df,column,metric,periodOrder,uniqueItems,height,width,chartDict,paramDict)
    lf = utils.ensure_lazyframe(df)
    max_len = (
        lf.select(pl.col(column).cast(pl.Utf8).str.len_chars().max())
        .collect()
        .item()
    )
    fig.update_annotations(font=dict(size=fontSize,family=font))
    fig,message=get_user_message(fig,chosenChart,"_None",key,paramDict,chartDict,df,max_len,None)
    fig=add_message_as_annotation(fig,message,column,chosenChart,chartDict,paramDict)
    fig=add_title_as_annotation(fig,title,chosenChart,chartDict)
    fig=_lift_multitier_small_multiple_title(fig,title,chartDict)
    fig=enable_draw_shapes(fig)
    return fig 

def add_forecast_bars_to_multitier_bar(fig,df,column,periodOrder,lineWidth,anchos,colorSequenceArray,text,row,col,chartDict):
    namingParams=get_naming_params()
    dateName=namingParams["dateName"] 
    labelName=namingParams["labelName"] 
    workColumn=namingParams["workColumn"] 
    acName=namingParams["acName"]
    plName=namingParams["plName"]
    fcName=namingParams["fcName"] 
    plotSmallMultiplesKey=namingParams["plotSmallMultiplesOtherCharts"]
    texttemplate,textformat=get_text_template(chartDict)
    if plotSmallMultiplesKey in chartDict and chartDict[plotSmallMultiplesKey]:
        texttemplate=None
    orientation="h" 
    fig.add_trace(go.Bar(
                            y = df[column],
                            x = df[fcName],
                            marker_pattern_shape="/",
                            marker_pattern_bgcolor=colorSequenceArray[0],
                            marker_pattern_fgcolor=colorSequenceArray[1],
                            marker_pattern_fgopacity=1,
                            marker_pattern_size=2.5,
                            marker=dict(
                            line=dict(color=colorSequenceArray[1], width=lineWidth)
                                        ),                             
                            offset = -0.35, 
                            width = anchos,
                            text=text,
                            textposition="outside",
                            texttemplate=texttemplate,
                            name = fcName,
                            customdata=df[fcName],
                            hovertemplate=texttemplate,
                            cliponaxis = False,
                            showlegend=False,
                            orientation='h',
                                 ),
                                 row=row, col=col,
                                 )
    return fig 

def add_absolute_value_bars_to_multitier_bar(
    fig: go.Figure,
    df: pl.DataFrame | pl.LazyFrame,
    column: str,
    periodOrder: list[str],
    lineWidth: float,
    anchos: float | int,
    offset: float,
    colorSequenceArray: list[str],
    paramDict: dict,
    row: int,
    col: int,
    chartDict: dict,
) -> tuple[go.Figure, pl.DataFrame, dict]:
    """Add PY/AC bars to a multitier bar chart lazily."""
    namingParams = get_naming_params()
    fcName = namingParams["fcName"]
    plName = namingParams["plName"]
    acName = namingParams["acName"]
    workColumn = namingParams["workColumn"]
    labelName = namingParams["labelName"]
    plotSmallMultiplesKey = namingParams["plotSmallMultiplesOtherCharts"]
    multitierBarChart = namingParams["multitierBarChart"]
    chosenChart = chartDict[namingParams["chosenChart"]]
    colorDict = get_color_dictionary(chartDict)

    lf = utils.ensure_lazyframe(df)
    columns, _ = get_schema_and_column_names(lf)

    if fcName not in columns:
        lf, chartDict = millify_dataframe(lf, periodOrder[1], None, labelName, chartDict)
        columns, _ = get_schema_and_column_names(lf)

    exprs: list[pl.Expr] = []
    if periodOrder[0] not in columns:
        exprs.append(pl.lit(0).alias(periodOrder[0]))
    if periodOrder[1] not in columns:
        exprs.append(pl.lit(0).alias(periodOrder[1]))
    if exprs:
        lf = lf.with_columns(exprs)

    df = lf.collect(engine="streaming")
    columns, _ = get_schema_and_column_names(df)
    text = df[labelName]
    texttemplate, _ = get_text_template(chartDict)

    if plotSmallMultiplesKey in chartDict and chartDict[plotSmallMultiplesKey] and chosenChart == multitierBarChart:
        text = None
        texttemplate = None

    if fcName in columns and workColumn in columns:
        customdataActual = df[workColumn]
        hovertemplate = ""
    else:
        customdataActual = df[periodOrder[1]]
        hovertemplate = " %{customdata:,.3s}"

    firstYear = df[periodOrder[0]]
    secondYear = df[periodOrder[1]]
    if fcName in columns and plName in columns:
        firstYear = df[plName]
        secondYear = df[acName]

    lineColor = colorDict["lightGreyColor"]
    if plName in columns:
        lineColor = colorDict["blackColor"]
    fig.add_trace(go.Bar(
                                y = df[column], 
                                x = firstYear,
                                marker=dict(
                                    color=colorSequenceArray[0],
                                    line=dict(color=lineColor, width=lineWidth)
                                            ),
                                offset = offset,  
                                hovertemplate=" %{x:,.3s}",
                                width = anchos,
                                name = periodOrder[0],           
                                orientation='h',
                                showlegend=False,
                                     ),
                                row=row, 
                                col=col,
                                     )
    if fcName in columns:
        fig=add_forecast_bars_to_multitier_bar(fig,df,column,periodOrder,lineWidth,anchos,colorSequenceArray,text,row,col,chartDict)
        text=None
        texttemplate=None
        lineWidth=0
    fig.add_trace(go.Bar(
                                y = df[column],
                                x = secondYear,
                                marker_color=colorSequenceArray[1],
                                text=text,
                                hovertext=df[periodOrder[1]],
                                hovertemplate=" %{x:,.3s}",
                                texttemplate=texttemplate,
                                textposition='outside',
                                marker=dict(
                                        line=dict(color=colorDict["blackColor"], width=lineWidth)),                          
                                width = anchos,
                                name = periodOrder[1],
                                cliponaxis=False,
                                showlegend=False,
                                orientation='h',
                                     ),
                                     row=row, 
                                     col=col
                                     )
    return fig,df,chartDict

def add_change_markers_to_multitier_bar(fig,df,column,colorChoice,anchosDiff,forecast,chartDict):
    namingParams=get_naming_params()
    differenceInValue=namingParams["differenceInValue"] 
    colorName=namingParams["colorName"]
    labelName=namingParams["labelName"]  
    multitierBarChart=namingParams["multitierBarChart"]   
    df,chartDict=add_sign_to_labels(df,multitierBarChart,differenceInValue,1,False,chartDict)
    if not forecast: 
        fig.add_trace(go.Bar(
                                y = df[column], 
                                x = df[differenceInValue],
                                text=df[labelName],
                                textposition='outside',                               
                                marker=dict(
                                    color=list(map(colorChoice, df[colorName]))
                                        ),
                                width = anchosDiff,
                                name = differenceInValue,           
                                orientation='h',
                                showlegend=False
                                     ),
                                    row=1, col=2
                                     )
    else:
        lineWidth=1
        colorList=list(map(colorChoice, df[colorName]))
        fig.add_trace(go.Bar(
                                y = df[column], 
                                x = df[differenceInValue],
                                text=df[labelName],
                                textposition='outside',                               
                                marker=dict(
                                    color=colorList,
                                    line=dict(color=colorList, width=lineWidth),
                                    pattern=dict(
                                    shape="/",
                                    fgopacity=1,
                                    size=2.5,
                                    bgcolor="#FFFFFF",
                                    fgcolor="#FFFFFF",
                                    fillmode="replace"
                                    )),
                                width = anchosDiff,
                                name = differenceInValue,           
                                orientation='h',
                                showlegend=False
                                     ),
                                    row=1, col=2
                                     )
    return fig,chartDict

def add_variance_annotations_to_multitier_bar(
    dfCopy: pl.DataFrame | pl.LazyFrame,
    column: str,
    fig: go.Figure,
    chartDict: dict,
    pyName: str,
    row: int,
    col: int,
    notifier: Notifier | None = None,
) -> go.Figure:
    """Add forecast rectangles and labels to the variance bar chart."""

    notify = _resolve_notifier(notifier)
    namingParams = get_naming_params()
    configParams = get_config_params()
    fontSize = configParams[namingParams["fontSizeText"]]
    font = configParams[namingParams["fontChoice"]]
    differenceInPercent = namingParams["differenceInPercent"]
    differenceInValue = namingParams["differenceInValue"]
    colorName = namingParams["colorName"]
    labelName = namingParams["labelName"]
    acName = namingParams["acName"]
    fcName = namingParams["fcName"]
    plName = namingParams["plName"]
    selectedPeriods = namingParams["selectedPeriods"]
    periodOrder = chartDict[selectedPeriods]
    totalVarianceAggregation = namingParams["totalVarianceAggregation"]
    colorDict = get_color_dictionary(chartDict)
    lineWidth = 0
    lineColor = colorDict["lightGreyColor"]
    redGreenColorDict = {
        0: colorDict["greenColor"],
        1: colorDict["redColor"],
        2: colorDict["transparentColor"],
    }

    df = duplicate_dataframe(dfCopy)
    df = df.with_columns(
        pl.col(colorName).fill_null(2),
        pl.col(labelName).cast(pl.Utf8),
    )
    df = df.with_columns(
        pl.when(
            pl.col(differenceInValue).is_null()
            & pl.col(differenceInPercent).is_null()
        )
        .then(pl.lit(""))
        .otherwise(pl.col(labelName))
        .alias(labelName)
    )

    columns, _ = get_schema_and_column_names(df)
    pyName = periodOrder[0]
    if pyName not in columns:
        pyName = periodOrder[0]

    texttemplate, textformat = get_text_template(chartDict)

    lf = utils.ensure_lazyframe(df).with_row_index(name="_idx")
    if fcName in columns:
        lf = lf.with_columns(
            pl.col(plName).alias("_x0"),
            pl.col(fcName).alias("_x1"),
        )
    else:
        lf = lf.with_columns(
            pl.col(pyName).alias("_x0"),
            (pl.col(pyName) + pl.col(differenceInValue)).alias("_x1"),
        )
    lf = lf.with_columns(pl.col(labelName).alias("_ann"))

    data = lf.select(["_idx", "_x0", "_x1", colorName, "_ann"]).collect()

    for idx, x0, x1, cval, text in zip(
        data["_idx"], data["_x0"], data["_x1"], data[colorName], data["_ann"]
    ):
        fig.add_shape(
            fillcolor=redGreenColorDict[cval],
            type="rect",
            layer="above",
            opacity=1,
            line_width=lineWidth,
            y0=idx - 0.2,
            y1=idx + 0.34,
            x0=x0,
            x1=x1,
            yref="y",
            xref="paper",
            row=row,
            col=col,
        )
        fig.add_annotation(
            text=text,
            showarrow=False,
            y=idx,
            ay=0,
            yshift=1,
            axref="x",
            x=x1,
            ax="x",
            ayref="y",
            xref="paper",
            xshift=16,
            align="center",
            row=row,
            col=col,
        )

    fig.update_annotations(font=dict(size=fontSize, family=font))
    return fig

def add_legends_to_multitier_bar(
    figure: go.Figure,
    df: pl.DataFrame | pl.LazyFrame,
    colname: str,
    periodOrder: list[str],
    uniqueItems: list[str],
    forecast: bool,
    row: int,
    col: int,
    chartDict: dict,
) -> go.Figure:
    """Add legend annotations for multitier bar charts.

    Parameters
    ----------
    figure:
        Plotly figure to annotate.
    df:
        Source data as ``DataFrame`` or ``LazyFrame``.
    colname:
        Column to annotate (unused but kept for API compatibility).
    periodOrder:
        Ordered list with period column names.
    uniqueItems:
        Unique category labels.
    forecast:
        Whether forecast values are present.
    row:
        Subplot row index.
    col:
        Subplot column index.
    chartDict:
        Chart configuration dictionary.

    Returns
    -------
    go.Figure
        Annotated figure.
    """

    namingParams = get_naming_params()
    fcName = namingParams["fcName"]
    acName = namingParams["acName"]
    plName = namingParams["plName"]
    plotSmallMultiplesKey = namingParams["plotSmallMultiplesOtherCharts"]
    multitierBarChart = namingParams["multitierBarChart"]
    chosenChart = namingParams["chosenChart"]
    chosenChart = chartDict[chosenChart]
    try:
        columns, _ = get_schema_and_column_names(df)
        lf = utils.ensure_lazyframe(df)

        exprs: list[pl.Expr] = []
        if acName in columns:
            exprs.append(pl.col(acName).first().alias("ac_first"))
        if fcName in columns:
            exprs.append(pl.col(fcName).first().alias("fc_first"))
        if periodOrder[1] in columns:
            exprs.append(pl.col(periodOrder[1]).first().alias("p1_first"))
        if plName in columns:
            exprs.append(pl.col(plName).last().alias("pl_last"))
        if periodOrder[0] in columns:
            exprs.append(pl.col(periodOrder[0]).last().alias("p0_last"))

        vals = (
            lf.select(exprs)
            .collect(engine="streaming")
        )
        val_columns, _ = get_schema_and_column_names(vals)
        val = lambda name: vals[name][0] if name in val_columns else 0

        ac_first = val("ac_first")
        fc_first = val("fc_first")
        p1_first = val("p1_first")
        pl_last = val("pl_last")
        p0_last = val("p0_last")

        align = "center"
        if len(uniqueItems) == 1:
            yShiftP1 = -10
            yShiftP0 = +15
        elif len(uniqueItems) <= 6:
            yShiftP1 = -10
            yShiftP0 = +15
        else:
            yShiftP1 = -5
            yShiftP0 = +11

        yref = "paper"
        y = 0
        xref = "x"
        if forecast:
            x = ac_first * 0.5
            label = acName
        else:
            x = p1_first * 0.5
            label = periodOrder[1]
        ax=x
        xShift=0
        if plotSmallMultiplesKey in chartDict and chartDict[plotSmallMultiplesKey] and chosenChart == multitierBarChart:
            xShift=0
            y=0
            x=0.36
            ax=x
            xref="x domain"
            yShiftDown=-11
            yref="y domain" 
            figure.add_annotation(
                text=label,
                showarrow = False,
                align=align,
                yshift=yShiftDown,
                yref=yref, 
                y=y,
                ax=ax,
                x=x,
                xref=xref, 
                xshift=xShift,
                hovertext=periodOrder[1],
                row=row,
                col=col,
                           )
        else:
                figure.add_annotation(
                text=label,
                showarrow = False,
                align=align,
                yshift=yShiftP1,
                yref=yref, 
                y=y,
                ax=ax,
                x=x,
                xref=xref, 
                xshift=xShift,
                hovertext=periodOrder[1],
                           )
    except Exception as e:  # nosec B110
        logging.exception(e)
        notify.error("Something went wrong while annotating the chart.")
    try:
        if forecast:
            x = pl_last * 0.5
            label = plName
        else:
            x = p0_last * 0.5
            label = periodOrder[0]
        align="center"
        yref="paper"
        y=1         
        xref="x"       
        ax=x 
        xShift=0 
        if plotSmallMultiplesKey in chartDict and chartDict[plotSmallMultiplesKey] and chosenChart == multitierBarChart: 
            y=1
            x=0.36
            ax=x
            xref="x domain"
            yShiftUp=4
            yref="y domain"   
            figure.add_annotation(
                text=label,
                showarrow = False,
                align=align,
                yshift=yShiftUp,
                yref=yref, 
                y=y,
                ax=ax,
                x=x,
                xref=xref, 
                xshift=xShift,
                hovertext=periodOrder[0],
                row=row,
                col=col,                
                           )
        else:
            figure.add_annotation(
                text=label,
                showarrow = False,
                align=align,
                yshift=yShiftP0,
                yref=yref, 
                y=y,
                ax=ax,
                x=x,
                xref=xref, 
                xshift=xShift,
                hovertext=periodOrder[0],               
                           )                                              
        if forecast:
            label = fcName
            yref = "y domain"
            y = 0
            xref = "x"
            x = (fc_first - ac_first) * 0.5 + ac_first
            ax=x 
            yShift=yShiftP1
            xShift=0 
            if plotSmallMultiplesKey in chartDict and chartDict[plotSmallMultiplesKey] and chosenChart == multitierBarChart: 
                xShift=0 
            figure.add_annotation(
                    text=label,
                    showarrow = False,
                    align=align,
                    yshift=yShiftDown,
                    yref=yref, 
                    y=y,
                    ax=ax,
                    x=x,
                    xref=xref, 
                    xshift=xShift,
                    hovertext=periodOrder[1],
                    row=row,
                    col=col,                    
    
                           )
    except Exception as e:  # nosec B110
        logging.exception(e)
        notify.error("Something went wrong while annotating the chart.")
    return figure

def add_variance_annotations_to_multitier_column(
    dfCopy: pl.DataFrame | pl.LazyFrame,
    fig: go.Figure,
    chartDict: dict,
    pyName: str,
    row: int,
    col: int,
    notifier: Notifier | None = None,
) -> go.Figure:
    """Add forecast rectangles and labels to the variance column chart."""
    namingParams=get_naming_params()
    configParams=get_config_params()
    fontSize=configParams[namingParams["fontSizeText"]] 
    font=configParams[namingParams["fontChoice"]]  
    differenceInValue=namingParams["differenceInValue"]
    colorName=namingParams["colorName"]
    labelName=namingParams["labelName"] 
    acName=namingParams["acName"] 
    plName=namingParams["plName"]    
    fcName=namingParams["fcName"]      
    totalVarianceAggregation=namingParams["totalVarianceAggregation"] 
    colorDict=get_color_dictionary(chartDict) 
    lineWidth=0
    lineColor=colorDict["lightGreyColor"]
    redGreenColorDict={0:colorDict["greenColor"],1:colorDict["redColor"],2:colorDict["transparentColor"]}
    lf = utils.ensure_lazyframe(dfCopy)
    columns, _ = get_schema_and_column_names(lf)

    exprs = [
        pl.col(colorName).fill_null(2).alias(colorName),
        (
            pl.when(pl.col(labelName) == "0.0")
            .then(pl.lit(""))
            .otherwise(pl.col(labelName))
            .cast(pl.Utf8)
            .alias(labelName)
        ),
    ]
    if fcName in columns:
        exprs.append(
            pl.when(pl.col(fcName) > 0)
            .then(pl.col(fcName) - pl.col(plName))
            .otherwise(pl.col(differenceInValue))
            .alias(differenceInValue)
        )
    lf = lf.with_columns(exprs)
    lf = (
        lf.with_row_index(name="_idx")
        .with_columns(
            (pl.col("_idx") - 0.2).alias("_x0"),
            (pl.col("_idx") + 0.34).alias("_x1"),
            pl.col(pyName).alias("_y0"),
            (pl.col(pyName) + pl.col(differenceInValue)).alias("_y1"),
            (pl.col("_idx") + 0.15).alias("_ann_x"),
        )
    )
    lists = to_lists(
        lf,
        [
            colorName,
            labelName,
            "_x0",
            "_x1",
            "_y0",
            "_y1",
            "_ann_x",
        ],
    )

    for cval, label_val, x0, x1, y0, y1, ann_x in zip(
        lists[colorName],
        lists[labelName],
        lists["_x0"],
        lists["_x1"],
        lists["_y0"],
        lists["_y1"],
        lists["_ann_x"],
    ):
        fig.add_shape(
            fillcolor=redGreenColorDict[cval],
            type="rect",
            layer="above",
            opacity=1,
            line_width=lineWidth,
            x0=x0,
            x1=x1,
            xref="paper",
            y0=y0,
            y1=y1,
            yref="y",
            row=row,
            col=col,
        )
        if str(label_val) not in ["Nan", "nan", np.nan, "0", None, "None"]:
            fig.add_annotation(
                text=label_val,
                showarrow=False,
                yshift=9,
                x=ann_x,
                ax=0,
                xref="paper",
                ayref="y",
                y=y1,
                ay="y",
                axref="x",
                align="center",
                row=row,
                col=col,
            )
    fig.update_annotations(font=dict(size=fontSize,family=font))   
    return fig 

def add_percent_change_markers_to_bar(fig,df,column,colorChoice,anchosPercent,colNumber):
    namingParams=get_naming_params()
    configParams=get_config_params()
    fontSize=configParams[namingParams["fontSizeText"]] 
    font=configParams[namingParams["fontChoice"]]
    colorName=namingParams["colorName"] 
    labelName=namingParams["labelName"] 
    differenceInPercent=namingParams["differenceInPercent"]
    orientation='h'
    textposition=make_text_position_array(df,orientation)
    fig.add_trace(go.Scatter(
                            y = df[column], 
                            x = df[differenceInPercent],
                            text=df[labelName],
                            mode = 'markers+text',
                            marker_symbol="square",
                            marker_color ='black',
                            marker_size  = 7,
                            textposition=textposition,
                            cliponaxis = False,
                            orientation=orientation,
                            showlegend=False,
                              ),
                            row=1, col=colNumber
                            )
    fig.add_trace(go.Bar(
                            y = df[column], 
                            x = df[differenceInPercent],                             
                            marker=dict(
                                color=list(map(colorChoice, df[colorName]))
                                    ),
                            width = .1,
                            name = differenceInPercent,           
                            orientation=orientation,
                            showlegend=False,
                            cliponaxis = False,
                                 ),
                            row=1, col=colNumber
          
                                 )
    return fig


def add_annotations_to_multitier_bar_chart(fig,df,uniqueItemsNumber,uniqueItems,paramDict,chartDict,column,metric,row,col):
    namingParams=get_naming_params()
    differenceInValue=namingParams["differenceInValue"]
    fcName=namingParams["fcName"]   
    acName=namingParams["acName"]   
    plName=namingParams["plName"] 
    pyName=namingParams["pyName"]  
    labelName=namingParams["labelName"]  
    compareScenarios=namingParams["compareScenarios"]
    compareScenariosOrPeriods=namingParams["compareScenariosOrPeriods"]  
    chosenChart=namingParams["chosenChart"]
    plotSmallMultiplesKey=namingParams["plotSmallMultiplesOtherCharts"]
    selectedPeriods=namingParams["selectedPeriods"]
    stackedColumnMetric=namingParams["stackedColumnMetric"]
    colorName=namingParams["colorName"]
    periodOrder=chartDict[selectedPeriods] 
    chosenChart=chartDict[chosenChart]         
    colorSequenceArray,lineWidth=get_color_sequence(df,paramDict,chartDict)
    colorChoice=get_color_choice(chartDict)
    anchos = [0.68] * uniqueItemsNumber
    anchosDiff = [0.68/1.0] * uniqueItemsNumber
    anchosPercent = [0.68/10] * uniqueItemsNumber
    columns,schema=get_schema_and_column_names(df)
    colorDict=get_color_dictionary(chartDict)
    chartDict[stackedColumnMetric]=metric
    if plotSmallMultiplesKey not in chartDict or not chartDict[plotSmallMultiplesKey]:
        row,col=1,1
    if plName in columns:
        pyName=plName         
    if compareScenariosOrPeriods in chartDict and chartDict[compareScenariosOrPeriods]==compareScenarios:
        columns,schema=get_schema_and_column_names(df)
        has_fc = (
            df.select(pl.col(fcName).sum().alias("_sum")).collect().to_series(0).item()
            if fcName in columns
            else 0
        )
        if fcName in columns and has_fc > 0:
            df=resize_bars_and_recalculate_differences(df,metric)
    forecast=False
    if compareScenariosOrPeriods in chartDict and chartDict[compareScenariosOrPeriods]==compareScenarios:
        columns,schema=get_schema_and_column_names(df)
        has_fc = (
            df.select(pl.col(fcName).sum().alias("_sum")).collect().to_series(0).item()
            if fcName in columns
            else 0
        )
        if fcName in columns and has_fc > 0:
            df=prepare_dataframe_for_forecast(df)
            df,chartDict=millify_dataframe(df,fcName,None,labelName,chartDict)
            forecast=True
        else:
            fcName=None
    else:
        fcName=None  
    offset = -.15        
    fig,df,chartDict=add_absolute_value_bars_to_multitier_bar(fig,df,column,periodOrder,lineWidth,anchos,offset,colorSequenceArray,paramDict,row,col,chartDict)
    if plotSmallMultiplesKey in chartDict and chartDict[plotSmallMultiplesKey]:  
        pass
        fig=add_variance_annotations_to_multitier_bar(df,column,fig,chartDict,pyName,row,col)
    if plotSmallMultiplesKey in chartDict and chartDict[plotSmallMultiplesKey]: 
        pass
    else:   
        fig,chartDict=add_change_markers_to_multitier_bar(fig,df,column,colorChoice,anchosDiff,forecast,chartDict)
        lf, largestArray, smallestArray, chartDict = get_pinhead_outliers(df, chartDict)
        lf = utils.ensure_lazyframe(lf)
        cols_to_collect = [column, differenceInPercent, labelName, colorName]
        subset = pl.DataFrame(to_lists(lf, cols_to_collect))
        fig = add_percent_change_markers_to_bar(fig, subset, column, colorChoice, anchosPercent, 3)
        fig = add_positive_outlier_pins_to_bar(fig, lf, largestArray, colorDict, 3)
        fig = add_negative_outlier_pins_to_bar(fig, lf, smallestArray, colorDict, 3)
        df = lf
    fig=add_legends_to_multitier_bar(fig,df,column,periodOrder,uniqueItems,forecast,row,col,chartDict)    
    return fig,chartDict

def add_positive_outlier_pins_to_bar(
    fig: go.Figure,
    df: pl.DataFrame | pl.LazyFrame,
    largestArray: list,
    colorDict: dict,
    colNumber: int,
) -> go.Figure:
    """Attach arrow pins for the largest positive outlier."""

    namingParams = get_naming_params()
    configParams = get_config_params()
    fontSize = configParams[namingParams["fontSizeText"]]
    font = configParams[namingParams["fontChoice"]]
    differenceInPercent = namingParams["differenceInPercent"]

    lf = utils.ensure_lazyframe(df)
    max_diff = (
        lf.select(pl.col(differenceInPercent).max()).collect().to_series(0).item()
    )

    if len(largestArray) > 1:
        color = colorDict["greenColor"]
        if largestArray[2] == 1:
            color = colorDict["redColor"]
        rounded_value = int(round(float(largestArray[1]), 0))
        label = str(rounded_value)
        if rounded_value > 0:
            label = "+" + label + "%"
        label = "<i>" + label + "</i>"
        fig.add_shape(
            type="line",
            opacity=1,
            line_width=2,
            line_color=color,
            y1=largestArray[0],
            y0=largestArray[0],
            yref="paper",
            x1=0,
            x0=max_diff * 1.2,
            xref="x",
            row=1,
            col=colNumber,
        )
        fig.add_annotation(
            showarrow=True,
            arrowcolor=color,
            arrowhead=2,
            arrowsize=3,
            arrowwidth=1,
            xanchor="center",
            y=largestArray[0],
            ay=0,
            yref="paper",
            ayref="y",
            x=max_diff * 1.6,
            ax=-10,
            xref="x",
            axref="x",
            align="center",
            row=1,
            col=colNumber,
        )
        fig.add_annotation(
            text=label,
            showarrow=False,
            xshift=-5,
            y=largestArray[0],
            ay=0,
            yref="paper",
            ayref="y",
            x=max_diff * 1.2,
            xref="x",
            axref="x",
            align="center",
            row=1,
            col=colNumber,
        )
    return fig

def add_negative_outlier_pins_to_bar(
    fig: go.Figure,
    df: pl.DataFrame | pl.LazyFrame,
    smallestArray: list,
    colorDict: dict,
    colNumber: int,
) -> go.Figure:
    """Attach arrow pins for the largest negative outlier."""

    namingParams = get_naming_params()
    configParams = get_config_params()
    fontSize = configParams[namingParams["fontSizeText"]]
    font = configParams[namingParams["fontChoice"]]
    differenceInPercent = namingParams["differenceInPercent"]

    lf = utils.ensure_lazyframe(df)
    max_diff = (
        lf.select(pl.col(differenceInPercent).max()).collect().to_series(0).item()
    )

    if len(smallestArray) > 1:
        color = colorDict["greenColor"]
        if smallestArray[2] == 1:
            color = colorDict["redColor"]
        label = str(int(round(float(smallestArray[1]), 0)))
        label = "<i>" + label + "%" + "</i>"
        fig.add_shape(
            type="line",
            opacity=1,
            line_width=2,
            line_color=color,
            y1=smallestArray[0],
            y0=smallestArray[0],
            yref="paper",
            x1=0,
            x0=-max_diff * 1.2,
            xref="x",
            row=1,
            col=colNumber,
        )

        fig.add_annotation(
                showarrow = True,
                arrowcolor=color,
                arrowhead=2,
                arrowsize=3,
                arrowwidth=1,
                xanchor="center",
                y=smallestArray[0],  # arrows' head
                ay=0,  # arrows' tail
                yref='paper',
                ayref='y',    
                x=-max_diff * 1.6,  # arrows' head
                ax=10,  # arrows' tail
                xref='x',
                axref='x',
                align="center",
                row=1,
                col=colNumber,            
                           )      
        if 1==2: 
            fig.add_annotation(
                text="----",
                font=dict(
                                color="white",
                                ),
                showarrow = False,
                #xanchor="center",
                xshift=-5,
                yshift=1,
                y=smallestArray[0],  # arrows' head
                ay=0,  # arrows' tail
                yref='paper',
                ayref='y',    
                x=-max_diff * 1.2,  # arrows' head
                xref='x',
                axref='x',
                align="center",
                row=1,
                col=colNumber,            
                           )        
        fig.add_annotation(
                text=label,
                showarrow = False,
                #xanchor="center",
                xshift=-5,
                y=smallestArray[0],  # arrows' head
                ay=0,  # arrows' tail
                yref='paper',
                ayref='y',    
                x=-max_diff * 1.2,  # arrows' head
                xref='x',
                axref='x',
                align="center",
                row=1,
                col=colNumber,            
                           )   
    fig.update_annotations(font=dict(size=fontSize,family=font))                                                     
    return fig 

def draw_multitier_bar_chart(dfCopy,chosenDimension,xColumn,metricsToPlot,valueCols,paramDict,chartDictCopy):
    namingParams=get_naming_params()
    configParams=get_config_params()
    chosenChart=namingParams["chosenChart"]
    configPlotlyDict=configParams["configPlotlyDict"]
    acName=namingParams["acName"]   
    pyName=namingParams["pyName"]
    totalName=namingParams["totalName"]
    colorName=namingParams["colorName"]
    periodName=namingParams["periodName"]    
    selectedPeriods=namingParams["selectedPeriods"] 
    plotSmallMultiplesKey=namingParams["plotSmallMultiplesOtherCharts"] 
    selectDimensionsToPlot=namingParams["selectDimensionsToPlot"]
    xAxisDimension=namingParams["xAxisDimension"]
    fatherAndChildDimensions=namingParams["fatherAndChildDimensions"]
    globalUniqueItemsArrayKey=namingParams["globalUniqueItemsArray"]
    showTopForEachItem=namingParams["showTopForEachItem"]
    numberOfPlottedSmallMultiplesKey=namingParams["numberOfPlottedSmallMultiples"]
    itemName=namingParams["itemName"]
    dimensionName=namingParams["dimensionName"]
    chartDict=copy.deepcopy(chartDictCopy)
    columnsToPlot=chartDict[selectDimensionsToPlot]  
    periodOrder=chartDict[selectedPeriods] 
    chosenChart=chartDict[chosenChart]
    configPlotlyDict=configPlotlyDict[chosenChart] 
    if len(columnsToPlot)>1:
        chartDict[numberOfPlottedSmallMultiplesKey]=len(columnsToPlot)-1 
    frameArray=[] 
    fullFig=False
    metricType=False
    if plotSmallMultiplesKey in chartDict and chartDict[plotSmallMultiplesKey] and chosenDimension == totalName:  
        fig,height,width,numberOfCols,numberOfRows=setup_fig_for_multitier_bar_charts(metricsToPlot,chosenDimension,paramDict,chartDict)
    columns,schema=get_schema_and_column_names(dfCopy) 
    count,countRows,countCols=1,1,1
    for metric in metricsToPlot:
        df=duplicate_dataframe(dfCopy)
        if (plotSmallMultiplesKey not in chartDict or not chartDict[plotSmallMultiplesKey]):
            axis=check_if_key_in_dict("Y","X",chartDict)
            df1,uniqueItems,paramDict=prepare_data_for_multitier_bar_plot(df,chosenDimension,xColumn,metric,valueCols,chartDict,paramDict,axis)
        elif chosenDimension == totalName:
            axis=check_if_key_in_dict("Y","X",chartDict)
            if plotSmallMultiplesKey in chartDict or chartDict[plotSmallMultiplesKey]:
                axis=check_if_key_in_dict("X","Y",chartDict)    
            df1,uniqueItems,paramDict=prepare_data_for_multitier_bar_plot(df,chosenDimension,xColumn,metric,valueCols,chartDict,paramDict,axis)
        if is_valid_lazyframe(df):
            if plotSmallMultiplesKey not in chartDict or not chartDict[plotSmallMultiplesKey]:
                fig,height,width,numberOfCols,numberOfRows=setup_fig_for_multitier_bar_charts(uniqueItems,chosenDimension,paramDict,chartDict)
                fig,chartDict=add_annotations_to_multitier_bar_chart(fig,df1,len(uniqueItems),uniqueItems,paramDict,chartDict,chosenDimension,metric,countRows,countCols)
            elif chosenDimension == totalName:
                fig,chartDict=add_annotations_to_multitier_bar_chart(fig,df1,len(uniqueItems),uniqueItems,paramDict,chartDict,chosenDimension,metric,countRows,countCols)
                count,countRows,countCols,chartDict=reset_row_and_column_counters(count,countCols,countRows,numberOfCols,numberOfRows,chartDict)
            elif xAxisDimension in chartDict:
                secondDimension=chartDict[xAxisDimension]
                dfDump,secondDimensionItems,aggregateOtherItemsName,valueCols=show_only_largest(df,chosenDimension,secondDimension,periodName,valueCols,chartDict,paramDict,"Y") 
                dfDump,globalUniqueItems,globalAggregateOtherItemsName,valueCols=show_only_largest(df,secondDimension,None,periodName,valueCols,chartDict,paramDict,"X") 
                secondDimensionItems = _rank_multitier_bar_panels_by_plotted_current_period(
                    df,
                    secondDimensionItems,
                    chosenDimension,
                    secondDimension,
                    xColumn,
                    metric,
                    valueCols,
                    chartDict,
                    paramDict,
                    periodOrder,
                    globalUniqueItems,
                )
                fig,height,width,numberOfCols,numberOfRows=setup_fig_for_multitier_bar_charts(secondDimensionItems,chosenDimension,paramDict,chartDict)
                count,countRows,countCols=1,1,1
                fatherAndChildItems=[]    
                for smallMultiplesDimension in secondDimensionItems:
                    dfCopy = duplicate_dataframe(df)
                    if smallMultiplesDimension == secondDimensionItems[-1]:
                        df1 = (
                            dfCopy
                            .filter(~pl.col(chosenDimension).is_in(secondDimensionItems[:-1]))
                            .with_columns(pl.lit(secondDimensionItems[-1]).alias(chosenDimension))
                        )
                    else:
                        df1 = dfCopy.filter(pl.col(chosenDimension) == smallMultiplesDimension)
                    if (fatherAndChildDimensions in chartDict and chartDict[fatherAndChildDimensions]) or chartDict[showTopForEachItem]:    
                        dfDump,fatherAndChildItems,globalAggregateOtherItemsName,valueCols=show_only_largest(df1,secondDimension,None,periodName,valueCols,chartDict,paramDict,"X") 
                        #if showTopForEachItem in chartDict and chartDict[showTopForEachItem]:
                        #    globalUniqueItems=fatherAndChildItems
                    else:
                        paramDict[globalUniqueItemsArrayKey]=globalUniqueItems    
                    df1, filteredUniqueItems, paramDict = prepare_data_for_multitier_bar_plot(
                        df1,
                        secondDimension,
                        xColumn,
                        metric,
                        valueCols,
                        chartDict,
                        paramDict,
                        "X",
                    )
                    df1, rankingArray = sort_dataframe_in_correct_order(
                        df1,
                        chartDict,
                        globalUniqueItems,
                        fatherAndChildItems,
                        globalAggregateOtherItemsName,
                    )

                    filteredUniqueItems = unique_values_lazy(secondDimension, df1)
                    reversedList = list(reversed(rankingArray))
                    numberOfRows = len(globalUniqueItems)
                    dfDim = duplicate_dataframe(df1)
                    if fatherAndChildDimensions in chartDict and chartDict[fatherAndChildDimensions]:
                        df1 = add_empty_rows_if_hierarchical(
                            df1,
                            numberOfRows,
                            reversedList,
                            globalUniqueItems,
                            chartDict,
                            False,
                        )
                    elif chartDict[showTopForEachItem]:
                        df1 = add_empty_rows_if_hierarchical(
                            df1,
                            numberOfRows,
                            reversedList,
                            globalUniqueItems,
                            chartDict,
                            False,
                        )
                    else:
                        df1 = add_empty_rows_if_not_hierarchical(
                            df1,
                            chartDict,
                            secondDimension,
                            reversedList,
                            filteredUniqueItems,
                            rankingArray,
                        )
                    columns, _ = get_schema_and_column_names(dfDim)
                    dfDim = (
                        dfDim.with_columns(
                            pl.lit(smallMultiplesDimension).alias(chosenDimension)
                        )
                        .select([chosenDimension] + [c for c in columns if c != chosenDimension])
                    )
                    dfDim = _normalize_multitier_export_frame(
                        dfDim,
                        [chosenDimension, secondDimension],
                    )
                    frameArray.append(dfDim)
                    fig, chartDict = add_annotations_to_multitier_bar_chart(
                        fig,
                        df1,
                        numberOfRows,
                        secondDimensionItems,
                        paramDict,
                        chartDict,
                        secondDimension,
                        metric,
                        countRows,
                        countCols,
                    )
                    count, countRows, countCols, chartDict = reset_row_and_column_counters(
                        count,
                        countCols,
                        countRows,
                        numberOfCols,
                        numberOfRows,
                        chartDict,
                    )
                chosenDimension=secondDimension
                uniqueItems=secondDimensionItems
            else:
                columnsToPlotNoTotal=[]
                for element in columnsToPlot:
                    if element != totalName:
                      columnsToPlotNoTotal.append(element)                    
                fig,height,width,numberOfCols,numberOfRows=setup_fig_for_multitier_bar_charts(columnsToPlotNoTotal,chosenDimension,paramDict,chartDict)
                count,countRows,countCols=1,1,1
                maxItems=get_maximum_number_of_items_in_small_multiples(df,columnsToPlotNoTotal,chartDict)
                for column in columnsToPlotNoTotal:
                    df1=duplicate_dataframe(df)
                    df1,uniqueItems,paramDict=prepare_data_for_multitier_bar_plot(df1,column,xColumn,metric,valueCols,chartDict,paramDict,"X")  
                    dfDim=duplicate_dataframe(df1)
                    dfDim = dfDim.rename({column: itemName})
                    columns,_=get_schema_and_column_names(dfDim)
                    dfDim=(
                        dfDim.with_columns(pl.lit(column).alias(dimensionName))
                        .select([dimensionName]+[c for c in columns if c!=dimensionName])
                    )
                    dfDim = _normalize_multitier_export_frame(
                        dfDim,
                        [dimensionName, itemName],
                    )
                    frameArray.append(dfDim)
                    df1=add_empty_rows_to_df(df1,column,len(uniqueItems),maxItems)
                    fig,chartDict=add_annotations_to_multitier_bar_chart(fig,df1,maxItems+1,uniqueItems,paramDict,chartDict,column,metric,countRows,countCols) 
                    chosenDimension=column    
                    count,countRows,countCols,chartDict=reset_row_and_column_counters(count,countCols,countRows,numberOfCols,numberOfRows,chartDict)
            if plotSmallMultiplesKey not in chartDict or not chartDict[plotSmallMultiplesKey]:                  
                fig,fullFig,metricType=keep_same_scale_for_all_plots(fig,metric,metricType,fullFig,"X")                    
                title,paramDict,chartDict=make_multitier_bar_chart_title(df1,chosenChart,paramDict,chosenDimension,metric,chartDict,pyName,acName) 
                key=chosenDimension+metric
                fig=adjust_multitier_bar_plot(fig,df1,key,chosenDimension,metric,title,periodOrder,uniqueItems,height,width,paramDict,chartDict) 
                dfExport=duplicate_dataframe(df1) 
                chartDict[dimensionName]=chosenDimension
                paramDict=set_up_tab_for_show_or_download_chart(dfExport,fig,configPlotlyDict,chartDict,chosenDimension+metric,False,None,chosenDimension,paramDict)             
    if plotSmallMultiplesKey in chartDict and chartDict[plotSmallMultiplesKey]: 
        key=chosenDimension                
        title,paramDict,chartDict=make_multitier_bar_chart_title(df1,chosenChart,paramDict,chosenDimension,metric,chartDict,pyName,acName)
        fig=adjust_multitier_bar_plot(fig,df1,key,chosenDimension,metric,title,periodOrder,uniqueItems,height,width,paramDict,chartDict)
        if len(frameArray) > 1:
            dfExport = pl.concat(frameArray, how="vertical")
        else:
            dfExport = df1
        paramDict = set_up_tab_for_show_or_download_chart(
            dfExport,
            fig,
            configPlotlyDict,
            chartDict,
            chosenDimension + metric,
            False,
            None,
            chosenDimension,
            paramDict,
        )        
    return paramDict
# fmt: on
# fmt: on
# isort: on
# fmt: on
# isort: on
