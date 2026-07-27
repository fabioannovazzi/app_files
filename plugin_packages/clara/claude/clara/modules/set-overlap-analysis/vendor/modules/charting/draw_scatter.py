# fmt: off
# isort: skip_file
import os
import tempfile
from pathlib import Path
import polars as pl
import numpy as np
import plotly.graph_objects as go
from plotly.subplots import make_subplots

_numba_cache_dir = Path(tempfile.gettempdir()) / "mparanza-numba-cache"
_numba_cache_dir.mkdir(parents=True, exist_ok=True)
os.environ.setdefault("NUMBA_CACHE_DIR", str(_numba_cache_dir))

import datashader as ds
import plotly.express as px
import math
import copy
import logging
from modules.utilities.ui_notifier import ui
from sklearn.cluster import DBSCAN
from sklearn.linear_model import LinearRegression
from sklearn.metrics import silhouette_score
from sklearn.preprocessing import StandardScaler

from modules.charting.chart_primitives import (
    get_color_array,
    get_color_dictionary,
    get_hightlight_color,
    millify,
)
from modules.charting.draw_bubble import (
    _bubble_axis_range,
    _safe_float,
    _select_bubble_label_positions,
    add_split_lines,
)
from modules.utilities.config import (
    get_config_params,
    get_naming_params,
)
from modules.utilities.helpers import (
    drop_columns,
    duplicate_dataframe,
    unique,
)
from modules.charting.polars_helpers import unique_values_lazy, to_lists

try:
    from modules.utilities.utils import (
        ensure_lazyframe,
        get_schema_and_column_names,
        is_valid_lazyframe,
    )
except Exception as e:  # pragma: no cover - fallback if missing
    logging.exception(e)
    ui.error(
                "Something went wrong while importing draw_scatter dependencies."
            )
    from modules.utilities.utils import (
        get_schema_and_column_names,
        is_valid_lazyframe,
    )

    def ensure_lazyframe(obj: pl.DataFrame) -> pl.LazyFrame:
        return obj.lazy()






























def add_scatter_traces(
    fig,
    df: pl.DataFrame | pl.LazyFrame,
    chartDict,
    paramDict,
    name,
    showLegend,
    size,
    hovertext,
    countRows,
    countCols,
    webGL,
    legendTitle,
):
    namingParams=get_naming_params()
    yAxisMetric=namingParams["yAxisMetric"]
    xAxisMetric=namingParams["xAxisMetric"]
    colorName=namingParams["colorName"]
    colorDict=get_color_dictionary(chartDict)
    xAxisMetric=chartDict[xAxisMetric]
    yAxisMetric=chartDict[yAxisMetric]

    columns, _ = get_schema_and_column_names(df)
    required_cols = [xAxisMetric, yAxisMetric]
    if colorName in columns:
        required_cols.append(colorName)
    if isinstance(df, pl.DataFrame):
        # Prefer explicit column selection to avoid ambiguous DataFrame indexing
        df_plot = df.select(required_cols)
    else:
        df_plot = ensure_lazyframe(df).select(required_cols).collect(engine="streaming")
    if not webGL:
        fig.add_trace(go.Scatter(
                                x=df_plot[xAxisMetric],
                                y = df_plot[yAxisMetric],
                                name=name,
                                legendgrouptitle=dict(
                                    text=legendTitle,
                                    ),
                                showlegend = showLegend,
                                mode = 'markers',
                                marker = dict(
                                            size=size,
                                            color=df_plot[colorName],
                                            line=dict(width=0.5,
                                                        color=colorDict["greyColor"],)
                                            ),
                                hovertext=hovertext,
                                             ),
                                row=countRows,
                                col=countCols,
                                        )
    else:  
        fig.add_trace(go.Scattergl(
                                x=df_plot[xAxisMetric],
                                y = df_plot[yAxisMetric],
                                name=name,
                                legendgrouptitle=dict(
                                    text=legendTitle,
                                    ),
                                showlegend = showLegend,
                                mode = 'markers',
                                marker = dict(
                                            size=size,
                                            color=df_plot[colorName],
                                            line=dict(width=0.5,
                                                        color=colorDict["greyColor"],)
                                            ),
                                hovertext=hovertext,
                                             ),
                                row=countRows,
                                col=countCols,
                                        )
    return fig 


def draw_scatter_chart_datashader(
    df: pl.DataFrame | pl.LazyFrame, colorDimension, chartDict
):
    """Render a scatter plot using Datashader.

    The function accepts either a ``DataFrame`` or ``LazyFrame`` and keeps all
    transformations lazy. After collecting the data, it converts the resulting
    Polars ``DataFrame`` to pandas immediately before creating ``ds.Canvas``
    points.
    """
    try:
        from modules.utilities.utils import ensure_lazyframe
    except Exception as e:
        ui.error("Something went wrong with draw_scatter_chart_datashader.")
        logging.exception("draw_scatter import error: %s", e)

        def ensure_lazyframe(obj: pl.DataFrame | pl.LazyFrame) -> pl.LazyFrame:
            return obj.lazy() if isinstance(obj, pl.DataFrame) else obj
    
    namingParams=get_naming_params()
    configParams=get_config_params()
    font=configParams[namingParams["fontChoice"]] 
    fontSize=configParams[namingParams["fontSizeText"]] 
    totalName=namingParams["totalName"]
    plotValuesAsChoice=namingParams["plotValuesAsChoice"]
    absolute=namingParams["absolute"]
    monetaryName=namingParams["monetaryLocalCurrencyName"]
    yAxisMetric=namingParams["yAxisMetric"]
    xAxisMetric=namingParams["xAxisMetric"]
    selectedPeriods=namingParams["selectedPeriods"]
    chartSubType=namingParams["chartSubType"]
    periodOrder=chartDict[selectedPeriods]
    xDimension = chartDict[xAxisMetric]
    yDimension = chartDict[yAxisMetric]
    lf = ensure_lazyframe(df)
    lf = (
        lf.select(pl.col([xDimension, yDimension]))
        .drop_nulls(subset=[xDimension, yDimension])
    )

    x_max, y_max = (
        lf.select(pl.max(xDimension), pl.max(yDimension))
        .collect(engine="streaming")
        .row(0)
    )
    x_max = 0 if x_max is None else x_max
    y_max = 0 if y_max is None else y_max

    df_plot_pd = lf.collect(engine="streaming").to_pandas()
    plot_width = int(100)
    plot_height = int(100)
    colorScale = "greys"
    cvs = ds.Canvas(
        plot_width=plot_width,
        plot_height=plot_height,
        x_range=(0, x_max),
        y_range=(0, y_max),
    )

    if df_plot_pd[xDimension].sum() != 0 and df_plot_pd[yDimension].sum() != 0:
        agg = cvs.points(df_plot_pd, xDimension, yDimension, agg=ds.count())
        zero_mask = agg.values == 0
        agg.values = np.log10(agg.values, where=np.logical_not(zero_mask))
        agg.values[zero_mask] = np.nan
        fig = px.imshow(
            agg, 
            color_continuous_scale=colorScale,
            origin='lower', 
            #labels={'color':'Log10(count)'},
            aspect='equal',
            )
    else:
        fig=False              
    return fig

def draw_small_multiples_scatter_colored(fig,df,chartDict,paramDict,name,showLegend,markerSize,countRows,countCols,webGL,legendTitle,count):
    namingParams = get_naming_params()
    yAxisDimension = namingParams["yAxisDimension"]
    xAxisDimension = namingParams["xAxisDimension"]
    highlightedDimension = namingParams["highlightedDimension"]
    colorName = namingParams["colorName"]
    nothingFilteredName = namingParams["nothingFilteredName"]
    otherName = namingParams["otherName"]
    colorDict = get_color_dictionary(chartDict)
    colorArray = get_color_array(colorDict, chartDict)
    colorDimension = chartDict[yAxisDimension]
    dotDimension = chartDict[xAxisDimension]
    highlightColor = get_hightlight_color(chartDict, colorDict)

    lf = ensure_lazyframe(df)
    columns, _ = get_schema_and_column_names(lf)
    if colorName in columns:
        lf = lf.drop(colorName)

    highlight_list = chartDict.get(highlightedDimension, [])

    color_lookup = (
        lf.select(pl.col(colorDimension).unique(maintain_order=True))
        .with_row_count("row_nr")
        .join(
            pl.DataFrame({"row_nr": list(range(len(colorArray))), colorName: colorArray}).lazy(),
            on="row_nr",
            how="left",
        )
        .with_columns(
            pl.when(pl.col(colorDimension).is_in(highlight_list))
            .then(pl.lit(highlightColor))
            .otherwise(pl.col(colorName))
            .fill_null(colorDict["veryLightGreyColor"])
            .alias(colorName),
            pl.when(pl.col("row_nr") >= len(colorArray))
            .then(pl.lit(otherName))
            .otherwise(pl.col(colorDimension))
            .alias(colorDimension),
        )
        .select([colorDimension, colorName])
    )

    lf = lf.join(color_lookup, on=colorDimension, how="left")

    grouped_df = (
        lf.group_by(colorDimension, maintain_order=True)
        .agg(pl.all())
        .sort(colorDimension)
        .collect(engine="streaming")
    )

    showLegendFlag = showLegend
    for idx, row in enumerate(grouped_df.iter_rows(named=True)):
        element = row[colorDimension]
        df1 = pl.DataFrame({k: v for k, v in row.items() if k != colorDimension})
        hover_col = dotDimension if dotDimension != nothingFilteredName else colorDimension
        hovertext = df1[hover_col]
        if count == 1 and idx == 0:
            showLegendFlag = True
            legendTitle = colorDimension
        if len(colorArray) < idx:
            showLegendFlag = False
        fig = add_scatter_traces(
            fig,
            df1,
            chartDict,
            paramDict,
            element,
            showLegendFlag,
            markerSize,
            hovertext,
            countRows,
            countCols,
            webGL,
            legendTitle,
        )
    fig, lf = add_labels_to_scatter(fig, lf, chartDict, countRows, countCols, True)
    return fig, showLegendFlag, lf

def draw_total_and_small_multiples_scatter_not_colored(fig,df,chartDict,paramDict,name,showLegend,markerSize,hovertext,webGL,legendTitle,countRows,countCols):
    fig=add_scatter_traces(fig,df,chartDict,paramDict,name,showLegend,markerSize,hovertext,countRows,countCols,webGL,legendTitle) 
    fig,df=add_labels_to_scatter(fig,df,chartDict,countRows,countCols,False)
    return fig,df

def draw_scatter_chart(fig,df,paramDict,periodOrder,uniqueItems,aggregateOtherItemsName,column,chartDict,countRows,countCols,webGL,count):
    """
    actually draws bubble chart
    """
    namingParams=get_naming_params()  
    logXAxis=namingParams["logXAxis"]
    logYAxis=namingParams["logYAxis"]
    yAxisDimension=namingParams["yAxisDimension"]
    totalName=namingParams["totalName"]
    showTrendLine=namingParams["showTrendLine"]
    colorName=namingParams["colorName"]
    xAxisDimension=namingParams["xAxisDimension"]
    nothingFilteredName=namingParams["nothingFilteredName"]
    notMetConditionValue=namingParams["notMetConditionValue"]
    colorDict=get_color_dictionary(chartDict)
    colorDimension=chartDict[yAxisDimension]
    dotDimension=chartDict[xAxisDimension]
    if isinstance(df, pl.LazyFrame):
        lf = df.with_columns(pl.lit(colorDict["lightGreyColor"]).alias(colorName))
        columns, schema = get_schema_and_column_names(lf)
        df = lf.collect(engine="streaming")
    else:
        df = df.with_columns(pl.lit(colorDict["lightGreyColor"]).alias(colorName))
        columns, schema = get_schema_and_column_names(df)
    hovertext, showLegend, name = None, False, None
    legendTitle, markerSize = None, 10 
    traceArray=[totalName]
    columns,schema=get_schema_and_column_names(df)    
    dfForGeometry = df
    dfLabels = df
    if column==totalName and colorDimension in columns and colorDimension not in [nothingFilteredName,False,notMetConditionValue]:
        fig,dfLabels=draw_total_scatter_colored(fig,df,chartDict,paramDict,uniqueItems,aggregateOtherItemsName,markerSize,countRows,countCols,webGL)  
    else:
        if dotDimension != nothingFilteredName:
            hovertext=df[dotDimension]
        colorItems=[]
        columns,schema=get_schema_and_column_names(df)
        if not colorDimension or column==colorDimension: 
            if len(uniqueItems)>=count and count>=1:
                name=uniqueItems[count-1]   
            fig,dfLabels=draw_total_and_small_multiples_scatter_not_colored(fig,df,chartDict,paramDict,name,showLegend,markerSize,hovertext,webGL,legendTitle,countRows,countCols)
        elif colorDimension in columns:
            fig,showLegend,dfLabels=draw_small_multiples_scatter_colored(fig,df,chartDict,paramDict,name,showLegend,markerSize,countRows,countCols,webGL,legendTitle,count)
    if not chartDict[logXAxis] and not chartDict[logYAxis]:
        fig=add_isolines(fig,dfForGeometry,chartDict,colorDict,countRows,countCols)                   
        if showTrendLine in chartDict and chartDict[showTrendLine] and dfForGeometry.height > 10:
            fig = add_trend_line(fig, dfForGeometry, chartDict, paramDict, countRows, countCols)
    fig=add_split_lines(fig)                                                                        
    return fig,showLegend,dfLabels 


def add_trend_line(fig,df,chartDict,paramDict,countRows,countCols):
    namingParams=get_naming_params()
    xAxisMetric=namingParams["xAxisMetric"]
    yAxisMetric=namingParams["yAxisMetric"]
    xAxisMetric=chartDict[xAxisMetric]
    yAxisMetric=chartDict[yAxisMetric]
    colorDict=get_color_dictionary(chartDict)
    err_size_regr = LinearRegression()
    err_size_res = err_size_regr.fit(np.array(df[xAxisMetric]).reshape(-1,1), np.array(df[yAxisMetric]))
    err_fit = err_size_regr.predict(np.array(df[xAxisMetric]).reshape(-1,1)) 
    highlightColor=get_hightlight_color(chartDict,colorDict) 
    fig.add_trace(go.Scatter(
                                x=df[xAxisMetric], 
                                y=err_fit, 
                                mode = "lines",
                                name="Error fit", 
                                showlegend=False,
                                line=dict(width=0.5,
                                        color=highlightColor),
                                ), 
                    row=countRows,
                    col=countCols,
                                        )                                                                  
    return fig

def add_isolines(fig,df,chartDict,colorDict,countRows,countCols):
    namingParams=get_naming_params()
    showIsoLine=namingParams["showIsoLine"]
    positionLegends=namingParams["positionLegends"]
    legendsAtRight=namingParams["legendsAtRight"]
    legendsAtLeft=namingParams["legendsAtLeft"]
    plotSmallMultiplesKey=namingParams["plotSmallMultiplesOtherCharts"]
    highlightColor=get_hightlight_color(chartDict,colorDict)
    if showIsoLine in chartDict and chartDict[showIsoLine]:        
        annotate_isolines = chartDict.get(plotSmallMultiplesKey) is not True
        steps=40
        xshift=10
        if chartDict[positionLegends]==legendsAtLeft:
            xshift=-xshift
        runs=(1,2,3,4)
        numberOfRuns=len(runs)
        for run in runs:              
            xArray,yArray,valueArray=get_isoline_data(df,chartDict,steps,run,numberOfRuns)
            fig.add_trace(go.Scatter(x=xArray, 
                                        y = yArray,
                                        text=valueArray,
                                        showlegend = False,
                                        mode = 'lines',
                                        line=dict(width=0.5,
                                            color=highlightColor ),
                                                     ),
                                        row=countRows,
                                        col=countCols,
                                                ) 
            count=0
            for value in valueArray:
                if value!="" and annotate_isolines:
                    fig.add_annotation(
                        showarrow = False,
                        text=valueArray[count], 
                        align="center",
                        xshift=xshift,
                        yshift=(run - ((numberOfRuns + 1) / 2)) * 10,
                        ax=xArray[count],
                        x=xArray[count], 
                        xref="x",
                        ay=yArray[count], 
                        y=yArray[count], 
                        yref="y",
                        row=countRows,
                        col=countCols,
                              )
                count=count+1
    return fig    


def get_isoline_data(
    dfCopy: pl.DataFrame | pl.LazyFrame,
    chartDict: dict,
    steps: int,
    run: int,
    numberRuns: int,
) -> tuple[list[float], list[float], list[str]]:
    lf = ensure_lazyframe(dfCopy)
    namingParams=get_naming_params()
    yAxisMetric=namingParams["yAxisMetric"]     
    xAxisMetric=namingParams["xAxisMetric"]
    positionLegends=namingParams["positionLegends"]
    legendsAtRight=namingParams["legendsAtRight"]
    legendsAtLeft=namingParams["legendsAtLeft"]
    marginInPercentName=namingParams["marginInPercentName"]
    marginInPercentOfNetSalesName=namingParams["marginInPercentOfNetSalesName"]
    isolineMetric=namingParams["isolineMetric"]
    valuePrefixDict=namingParams["valuePrefixDict"]
    yAxisMetric=chartDict[yAxisMetric]
    xAxisMetric=chartDict[xAxisMetric]
    positionLegends=chartDict[positionLegends]
    metricArray=[yAxisMetric,xAxisMetric]
    isoline_metric = chartDict.get(isolineMetric)
    value_prefix_dict = dict(chartDict.get(valuePrefixDict, {}))
    value_prefix = value_prefix_dict.get(isoline_metric, "")
    lf = lf.filter((pl.col(yAxisMetric) >= 0) & (pl.col(xAxisMetric) >= 0))
    stats = (
        lf.select(
            pl.max(xAxisMetric).alias("xMax"),
            pl.min(xAxisMetric).alias("xMin"),
            pl.max(yAxisMetric).alias("yMax"),
            pl.min(yAxisMetric).alias("yMin"),
            (pl.col(xAxisMetric) * pl.col(yAxisMetric)).max().alias("valueMax"),
            (pl.col(xAxisMetric) * pl.col(yAxisMetric)).min().alias("valueMin"),
        )
        .collect()
        .row(0)
    )
    xMax, xMin, yMax, yMin, valueMax, valueMin = stats
    xDiff=xMax-xMin
    xJump=xDiff/steps
    yDiff=yMax-yMin
    yJump=xDiff/steps
    valueDiff=valueMax-valueMin
    valueJump=valueDiff/(steps)
    valueStep=valueDiff/(numberRuns+1)
    valueTarget=valueMin+(valueStep*run)
    valueTarget=round(valueTarget,0)
    xCumul=0.0
    xArray: list[float] = []
    yArray: list[float] = []
    valueArray: list[str] = []
    for x in range(1, steps):
        xValue=(xMax)-(xJump+xCumul)
        yValue=valueTarget/xValue
        xCumul=xCumul+xJump
        totValue=xValue*yValue
        if xValue>xMax or yValue>yMax:
            xValue,yValue,totValue="","","" 
        xArray.append(xValue)
        yArray.append(yValue)
        if positionLegends == legendsAtLeft and x != steps-1:    
           valueArray.append("")
        elif positionLegends == legendsAtRight and x != 1:   
            valueArray.append("")
        else:
           if marginInPercentName in metricArray and totValue not in [0,""]:
                totValue=totValue/100
           elif marginInPercentOfNetSalesName in metricArray and totValue not in [0,""]:
                totValue=totValue/100
           if totValue not in [0,""]:  
                totValue=_format_isoline_value(totValue, value_prefix)
                valueArray.append(totValue)     
    return xArray,yArray,valueArray

def find_dots_to_label(
    dfCopy: pl.DataFrame | pl.LazyFrame,
    chartDict: dict,
    limitItems: bool,
) -> pl.LazyFrame:
    """Return LazyFrame of noise dots for scatter labelling."""

    namingParams = get_naming_params()
    yAxisMetric = namingParams["yAxisMetric"]
    xAxisMetric = namingParams["xAxisMetric"]
    clusterName = namingParams["clusterName"]
    isNoiseName = namingParams["xAxisDimension"]
    setFactorParameter = namingParams["setFactorParameter"]

    yAxisMetric = chartDict[yAxisMetric]
    xAxisMetric = chartDict[xAxisMetric]
    factor = chartDict[setFactorParameter]

    lf = ensure_lazyframe(dfCopy)
    scaler = StandardScaler()
    features = (
        lf.select([yAxisMetric, xAxisMetric])
        .collect(engine="streaming")
        .to_numpy()
    )
    df_scaled = scaler.fit_transform(features)
    # Parameter settings
    eps_values = np.arange(0.1, 1.0, 0.1)  # Range of eps values to test
    min_samples_values = range(2, 10)  # Range of min_samples values to test
    best_params = {'eps': 0.1, 'min_samples': 2}
    best_score = -1
    # Testing different combinations of parameters
    for eps in eps_values:
        for min_samples in min_samples_values:
            model = DBSCAN(eps=eps, min_samples=min_samples)
            labels = model.fit_predict(df_scaled)
            if len(set(labels)) > 1:  # Silhouette score can't be calculated with only one cluster
                score = silhouette_score(df_scaled, labels)
                if score > best_score:
                    best_score = score
                    best_params = {'eps': eps, 'min_samples': min_samples}
    eps=best_params['eps']
    minSamples=best_params['min_samples']
    for _ in range(10):  # Limit number of iterations to prevent infinite loop
        model = DBSCAN(eps=eps, min_samples=minSamples)
        labels = model.fit_predict(df_scaled)
        # Calculate silhouette score
        if len(set(labels)) > 1:  # Ensure there are at least two clusters
            score = silhouette_score(df_scaled, labels)
            # Adjust factor based on the result
            if score > best_score:
                best_score = score
                best_factor = factor
                factor *= 1.1  # Increase factor to make more significant changes
            else:
                factor *= 0.9  # Decrease factor to refine the changes
        
            # Update eps for next iteration
            eps *= factor
        else:
            # Adjust factor downwards if only one cluster (or noise) is found
            factor *= 0.9
            eps *= factor
    features = df_scaled
    lf_filtered = lf
    count = 1
    numberOfLabels = len(features)
    while numberOfLabels > 15 and count <= 20:
        model = DBSCAN(eps=eps, min_samples=minSamples)
        model.fit(features)
        labels = np.asarray(model.labels_)
        noise_mask = labels == -1
        lf_filtered = (
            lf_filtered.with_columns(pl.Series(labels).alias(clusterName))
            .with_columns(pl.Series(noise_mask).alias(isNoiseName))
            .filter(pl.col(isNoiseName))
        )
        features = (
            lf_filtered.select([yAxisMetric, xAxisMetric])
            .collect(engine="streaming")
            .to_numpy()
        )
        features = scaler.fit_transform(features)
        numberOfLabels = len(features)
        eps *= factor
        count += 1

    numberOfItems = 6
    if limitItems:
        dfx = lf_filtered.sort(xAxisMetric, descending=True).tail(int(numberOfItems / 2))
        dfy = lf_filtered.sort(yAxisMetric, descending=True).head(int(numberOfItems / 2))
        lf_filtered = pl.concat([dfx, dfy]).unique()

    return lf_filtered


def _format_isoline_value(value: float, value_prefix: str) -> str:
    """Return a compact isoline annotation using chart value-prefix settings."""

    prefix_divisors = {
        "k": 1_000,
        "m": 1_000_000,
        "b": 1_000_000_000,
        "t": 1_000_000_000_000,
    }
    divisor = prefix_divisors.get(value_prefix)
    if divisor:
        return f"{float(value) / divisor:.0f}{value_prefix}"
    return millify(value, 0)


def _scatter_label_offsets(x_values: list, y_values: list) -> list[tuple[int, int]]:
    """Return annotation x/y shifts that separate nearby scatter labels."""

    numeric_points: list[tuple[float, float] | None] = []
    xs: list[float] = []
    ys: list[float] = []
    for x_value, y_value in zip(x_values, y_values):
        try:
            x_float = float(x_value)
            y_float = float(y_value)
        except (TypeError, ValueError):
            numeric_points.append(None)
            continue
        if not math.isfinite(x_float) or not math.isfinite(y_float):
            numeric_points.append(None)
            continue
        numeric_points.append((x_float, y_float))
        xs.append(x_float)
        ys.append(y_float)

    if not xs or not ys:
        return [(0, 10) for _ in x_values]

    x_span = max(max(xs) - min(xs), 1.0)
    y_span = max(max(ys) - min(ys), 1.0)
    x_tolerance = x_span * 0.08
    y_tolerance = y_span * 0.06
    shift_pattern = [
        (0, 12),
        (-24, 22),
        (24, 22),
        (-36, 8),
        (36, 8),
        (-24, -12),
        (24, -12),
        (-42, 24),
        (42, 24),
    ]
    top_shift_pattern = [
        (0, -14),
        (-24, -24),
        (24, -24),
        (-36, -8),
        (36, -8),
    ]

    offsets: list[tuple[int, int]] = []
    seen_points: list[tuple[float, float]] = []
    for point in numeric_points:
        if point is None:
            offsets.append((0, 10))
            continue
        x_value, y_value = point
        nearby_count = sum(
            1
            for seen_x, seen_y in seen_points
            if abs(x_value - seen_x) <= x_tolerance
            and abs(y_value - seen_y) <= y_tolerance
        )
        x_norm = (x_value - min(xs)) / x_span
        y_norm = (y_value - min(ys)) / y_span
        pattern = top_shift_pattern if y_norm >= 0.88 else shift_pattern
        x_shift, y_shift = pattern[nearby_count % len(pattern)]
        if x_norm >= 0.88:
            x_shift = min(x_shift, -24)
        elif x_norm <= 0.08:
            x_shift = max(x_shift, 24)
        offsets.append((x_shift, y_shift))
        seen_points.append(point)
    return offsets


def _limit_scatter_label_rows(
    lf: pl.LazyFrame,
    x_metric: str,
    y_metric: str,
    max_labels: int = 10,
    min_distance: float = 0.14,
) -> pl.LazyFrame:
    """Keep a spread-out subset of labels when dense scatter labels overlap."""

    label_df = (
        lf.select([x_metric, y_metric])
        .with_row_index("__scatter_label_idx")
        .collect(engine="streaming")
    )
    if label_df.height <= max_labels:
        return lf

    rows = label_df.iter_rows(named=True)
    points: list[tuple[int, float, float]] = []
    for row in rows:
        try:
            x_value = float(row[x_metric])
            y_value = float(row[y_metric])
        except (TypeError, ValueError):
            continue
        if math.isfinite(x_value) and math.isfinite(y_value):
            points.append((int(row["__scatter_label_idx"]), x_value, y_value))

    if len(points) <= max_labels:
        return lf

    x_values = [point[1] for point in points]
    y_values = [point[2] for point in points]
    x_span = max(max(x_values) - min(x_values), 1.0)
    y_span = max(max(y_values) - min(y_values), 1.0)
    x_min = min(x_values)
    y_min = min(y_values)
    scored_points: list[tuple[float, int, float, float]] = []
    for index, x_value, y_value in points:
        x_norm = (x_value - x_min) / x_span
        y_norm = (y_value - y_min) / y_span
        edge_score = abs(x_norm - 0.5) + abs(y_norm - 0.5)
        score = (y_norm * 1.5) + (x_norm * 0.5) + (edge_score * 0.25)
        scored_points.append((score, index, x_norm, y_norm))

    selected: list[tuple[int, float, float]] = []
    low_band_limit = max(1, max_labels // 4)
    low_band_count = 0
    for _score, index, x_norm, y_norm in sorted(scored_points, reverse=True):
        if y_norm <= 0.08 and low_band_count >= low_band_limit:
            continue
        if all(
            ((x_norm - selected_x) ** 2 + (y_norm - selected_y) ** 2) ** 0.5
            >= min_distance
            for _selected_index, selected_x, selected_y in selected
        ):
            selected.append((index, x_norm, y_norm))
            if y_norm <= 0.08:
                low_band_count += 1
        if len(selected) >= max_labels:
            break

    selected_indices = {index for index, _x_norm, _y_norm in selected}
    if len(selected_indices) < min(max_labels, 3):
        for _score, index, _x_norm, _y_norm in sorted(scored_points, reverse=True):
            selected_indices.add(index)
            if len(selected_indices) >= min(max_labels, 3):
                break

    return (
        lf.with_row_index("__scatter_label_idx")
        .filter(pl.col("__scatter_label_idx").is_in(sorted(selected_indices)))
        .drop("__scatter_label_idx")
    )


def _scatter_label_limit(chartDict: dict, adjust_labels: bool) -> tuple[int, float]:
    """Return per-chart label limit and spacing for adjusted scatter labels."""

    if not adjust_labels:
        return 15, 0.09
    namingParams = get_naming_params()
    plotSmallMultiplesKey = namingParams["plotSmallMultiplesOtherCharts"]
    is_small_multiple_panel = chartDict.get(plotSmallMultiplesKey) is True
    if is_small_multiple_panel:
        return 4, 0.2
    return 6, 0.16


def _select_scatter_label_positions(
    lf: pl.LazyFrame,
    label_column: str,
    x_metric: str,
    y_metric: str,
    font_size: int | float,
    max_labels: int | None = None,
) -> dict[int, tuple[int, int]]:
    """Use the bubble label collision selector for scatter labels."""

    label_df = (
        lf.select(["__scatter_label_idx", label_column, x_metric, y_metric])
        .collect(engine="streaming")
    )
    raw_rows: list[dict[str, object]] = []
    x_values: list[float] = []
    y_values: list[float] = []
    for row in label_df.iter_rows(named=True):
        x_float = _safe_float(row[x_metric])
        y_float = _safe_float(row[y_metric])
        if x_float is not None:
            x_values.append(x_float)
        if y_float is not None:
            y_values.append(y_float)
        raw_rows.append(
            {
                "row_index": int(row["__scatter_label_idx"]),
                "label": row[label_column],
                "value": "",
                "x": row[x_metric],
                "y": row[y_metric],
                "x_float": x_float,
                "y_float": y_float,
            }
        )

    x_range = _bubble_axis_range(x_values)
    y_range = _bubble_axis_range(y_values)
    x_span = max(x_range[1] - x_range[0], 1.0)
    y_span = max(y_range[1] - y_range[0], 1.0)
    best_rows_by_label: dict[str, tuple[float, dict[str, object]]] = {}
    for row in raw_rows:
        x_float = row.get("x_float")
        y_float = row.get("y_float")
        if not isinstance(x_float, (int, float)) or not isinstance(
            y_float, (int, float)
        ):
            continue
        x_norm = (float(x_float) - x_range[0]) / x_span
        y_norm = (float(y_float) - y_range[0]) / y_span
        edge_score = abs(x_norm - 0.5) + abs(y_norm - 0.5)
        priority = (y_norm * 1.5) + (x_norm * 0.5) + (edge_score * 0.25)
        row["size_float"] = priority
        row["x_norm"] = x_norm
        row["y_norm"] = y_norm
        label_key = str(row.get("label") or f"__row_{row['row_index']}")
        current = best_rows_by_label.get(label_key)
        if current is None or priority > current[0]:
            best_rows_by_label[label_key] = (priority, row)
    ranked_rows = sorted(
        best_rows_by_label.values(), key=lambda item: item[0], reverse=True
    )
    low_band_count = 0
    low_band_limit = 1
    rows: list[dict[str, object]] = []
    for _priority, row in ranked_rows:
        x_norm = row.get("x_norm")
        y_norm = row.get("y_norm")
        is_low_band = (
            isinstance(x_norm, (int, float))
            and isinstance(y_norm, (int, float))
            and x_norm <= 0.08
            and y_norm <= 0.08
        )
        if is_low_band and low_band_count >= low_band_limit:
            continue
        rows.append(row)
        if is_low_band:
            low_band_count += 1
        if max_labels is not None and len(rows) >= max_labels:
            break

    return _select_bubble_label_positions(
        rows,
        x_range=x_range,
        y_range=y_range,
        size_ref=None,
        font_size=float(font_size) * 1.2,
        show_label=True,
        show_value=False,
        collision_padding=10.0,
        allowed_edge_overflow=80.0,
    )


def add_labels_to_scatter(fig,dfCopy,chartDict,countRows,countCols,limitItems):
    namingParams=get_naming_params()
    configParams = get_config_params()
    fontSize = configParams[namingParams["fontSizeText"]]
    yAxisMetric=namingParams["yAxisMetric"]
    xAxisMetric=namingParams["xAxisMetric"]
    xAxisDimension=namingParams["xAxisDimension"]
    logXAxis=namingParams["logXAxis"]
    logYAxis=namingParams["logYAxis"]
    showScatterLabels=namingParams["showScatterLabels"]
    plotSmallMultiplesKey=namingParams["plotSmallMultiplesOtherCharts"]
    smallMultiplesColumn=namingParams["smallMultiplesColumn"]
    adjustBubbleLabels = namingParams["adjustBubbleLabels"]
    yAxisMetric=chartDict[yAxisMetric]
    xAxisMetric=chartDict[xAxisMetric]
    xAxisDimension=chartDict[xAxisDimension]
    colorDict=get_color_dictionary(chartDict)
    lf = ensure_lazyframe(dfCopy)
    lf = lf.with_columns(
        [pl.col(yAxisMetric).fill_null(0), pl.col(xAxisMetric).fill_null(0)]
    )
    if is_valid_lazyframe(lf):
        adjustLabels = chartDict.get(adjustBubbleLabels, False)
        if not adjustLabels:
            lf = find_dots_to_label(lf, chartDict, limitItems)
        columns, schema = get_schema_and_column_names(lf)
        toKeep = [xAxisDimension, yAxisMetric, xAxisMetric]
        if plotSmallMultiplesKey in chartDict and chartDict[plotSmallMultiplesKey]:
            if smallMultiplesColumn in chartDict:
                toKeep.append(chartDict[smallMultiplesColumn])
        to_drop = [c for c in columns if c not in toKeep]
        lf = drop_columns(lf, to_drop)
        yShift = 10
        if showScatterLabels in chartDict and chartDict[showScatterLabels]:
            if xAxisDimension not in [None, "None"]:
                if adjustLabels:
                    grouping_columns = [xAxisDimension]
                    small_multiples_dimension = chartDict.get(smallMultiplesColumn)
                    if (
                        plotSmallMultiplesKey in chartDict
                        and chartDict[plotSmallMultiplesKey]
                        and small_multiples_dimension in columns
                    ):
                        grouping_columns.append(small_multiples_dimension)
                    lf = lf.group_by(grouping_columns, maintain_order=True).agg(
                        [pl.col(yAxisMetric).sum(), pl.col(xAxisMetric).sum()]
                    )
                if logXAxis in chartDict and chartDict[logXAxis]:
                    lf = lf.with_columns(pl.col(xAxisMetric).log10())
                if logYAxis in chartDict and chartDict[logYAxis]:
                    lf = lf.with_columns(pl.col(yAxisMetric).log10())
                if adjustLabels:
                    max_labels, _min_distance = _scatter_label_limit(
                        chartDict, adjustLabels
                    )
                    lf = lf.with_row_index("__scatter_label_idx")
                    lf = lf.collect(engine="streaming").lazy()
                    label_offsets_by_index = _select_scatter_label_positions(
                        lf,
                        xAxisDimension,
                        xAxisMetric,
                        yAxisMetric,
                        fontSize,
                        max_labels=max_labels,
                    )
                    selected_indices = sorted(label_offsets_by_index)
                    lf = lf.filter(
                        pl.col("__scatter_label_idx").is_in(selected_indices)
                    )
                    coords_df = lf.select(
                        [
                            "__scatter_label_idx",
                            xAxisDimension,
                            yAxisMetric,
                            xAxisMetric,
                        ]
                    ).collect(engine="streaming")
                    for row in coords_df.iter_rows(named=True):
                        xShift, shiftedY = label_offsets_by_index[
                            int(row["__scatter_label_idx"])
                        ]
                        fig.add_annotation(
                            text=row[xAxisDimension],
                            showarrow=False,
                            yshift=shiftedY,
                            xshift=xShift,
                            y=row[yAxisMetric],
                            yref="y",
                            x=row[xAxisMetric],
                            ax=0,
                            xref="x",
                            font=dict(color=colorDict["blackColor"]),
                            row=countRows,
                            col=countCols,
                        )
                    lf = lf.drop("__scatter_label_idx")
                else:
                    coords_lf = lf.select([xAxisDimension, yAxisMetric, xAxisMetric])
                    lists = to_lists(
                        coords_lf, [xAxisDimension, yAxisMetric, xAxisMetric]
                    )
                    labels = lists[xAxisDimension]
                    y_vals = lists[yAxisMetric]
                    x_vals = lists[xAxisMetric]
                    label_offsets = [(0, yShift) for _ in labels]
                    for label, y_val, x_val, label_offset in zip(
                        labels, y_vals, x_vals, label_offsets
                    ):
                        xShift, shiftedY = label_offset
                        fig.add_annotation(
                            text=label,
                            showarrow=False,
                            yshift=shiftedY,
                            xshift=xShift,
                            y=y_val,
                            yref="y",
                            x=x_val,
                            ax=0,
                            xref="x",
                            font=dict(color=colorDict["blackColor"]),
                            row=countRows,
                            col=countCols,
                    )
    return fig, lf

def get_colors_for_scatter(df,element,colorArray,highlightColor,chartDict,colorDict,countItems):
    namingParams=get_naming_params()
    highlightedDimension=namingParams["highlightedDimension"]
    colorName=namingParams["colorName"]
    yAxisDimension=namingParams["yAxisDimension"]
    otherName=namingParams["otherName"]
    colorDimension=chartDict[yAxisDimension]
    mask = pl.col(colorDimension) == element
    if highlightedDimension in chartDict and element in chartDict[highlightedDimension]:
        df = df.with_columns(pl.when(mask).then(pl.lit(highlightColor)).otherwise(pl.col(colorName)).alias(colorName))
    elif len(colorArray)>countItems:
        df = df.with_columns(pl.when(mask).then(pl.lit(colorArray[countItems])).otherwise(pl.col(colorName)).alias(colorName))
    else: 
        df = df.with_columns(pl.when(mask).then(pl.lit(colorDict["veryLightGreyColor"])).otherwise(pl.col(colorName)).alias(colorName))
        df = df.with_columns(pl.when(mask).then(pl.lit(otherName)).otherwise(pl.col(colorDimension)).alias(colorDimension))
        element=otherName
    countItems=countItems+1    
    return df,element,countItems 


def draw_total_scatter_colored(
    fig,
    df: pl.DataFrame | pl.LazyFrame,
    chartDict,
    paramDict,
    uniqueItems,
    aggregateOtherItemsName,
    markerSize,
    countRows,
    countCols,
    webGL,
):
    namingParams=get_naming_params()
    dotDimension=namingParams["xAxisDimension"]
    yAxisDimension=namingParams["yAxisDimension"]
    highlightedDimension=namingParams["highlightedDimension"]
    colorName=namingParams["colorName"]
    nothingFilteredName=namingParams["nothingFilteredName"] 
    colorDict=get_color_dictionary(chartDict)
    colorArray=get_color_array(colorDict,chartDict)
    highlightColor=get_hightlight_color(chartDict,colorDict)
    dotDimension=chartDict[dotDimension]
    colorDimension=chartDict[yAxisDimension]
    otherName=namingParams["otherName"]

    lf = ensure_lazyframe(df)
    columns, _ = get_schema_and_column_names(lf)
    if colorName in columns:
        lf = lf.drop(colorName)

    highlight_list = chartDict.get(highlightedDimension, [])

    color_lookup = (
        lf.select(pl.col(colorDimension).unique(maintain_order=True))
        .with_row_count("row_nr")
        .join(
            pl.DataFrame({"row_nr": list(range(len(colorArray))), colorName: colorArray}).lazy(),
            on="row_nr",
            how="left",
        )
        .with_columns(
            pl.when(pl.col(colorDimension).is_in(highlight_list))
            .then(pl.lit(highlightColor))
            .otherwise(pl.col(colorName))
            .fill_null(colorDict["veryLightGreyColor"])
            .alias(colorName),
            pl.when(pl.col("row_nr") >= len(colorArray))
            .then(pl.lit(otherName))
            .otherwise(pl.col(colorDimension))
            .alias(colorDimension),
        )
        .select([colorDimension, colorName])
    )

    lf = lf.join(color_lookup, on=colorDimension, how="left")

    grouped = (
        lf.group_by(colorDimension, maintain_order=True)
        .agg(pl.all())
        .collect(engine="streaming")
    )

    countItems=0
    showLegend, legendTitle = True, colorDimension
    for row in grouped.iter_rows(named=True):
        element=row[colorDimension]
        df1=pl.DataFrame({k:v for k,v in row.items() if k!=colorDimension})
        col=dotDimension if dotDimension!=nothingFilteredName else colorDimension
        hovertext=df1[col]
        if len(colorArray)<countItems:
            showLegend=False
        fig=add_scatter_traces(fig,df1,chartDict,paramDict,element,showLegend,markerSize,hovertext,countRows,countCols,webGL,legendTitle)
        countItems+=1
    fig,lf=add_labels_to_scatter(fig,lf,chartDict,countRows,countCols,False)
    return fig,lf
