# isort: off
# fmt: off
import polars as pl
import plotly.graph_objects as go
from plotly.subplots import make_subplots
from typing import Mapping, Sequence
import math
import copy
import logging



from modules.charting.chart_helpers import set_up_tab_for_show_or_download_chart
from modules.charting.chart_primitives import (
    add_message_as_annotation,
    add_title_as_annotation,
    enable_draw_shapes,
    get_color_array,
    get_color_dictionary,
    get_color_sequence,
    get_number_prefix,
    get_user_message,
    insert_highlight_color,
    millify_dataframe,
    reset_row_and_column_counters,
    set_other_color_to_grey,
)
from modules.charting.draw_charts_utils import (
    add_line_traces,
    add_non_cumulated_legends,
    keep_same_scale_for_all_plots,
    prepare_value_labels_for_timeline,
    get_polars_value_at_index,
)
from modules.charting.make_titles import (
    make_slope_and_dot_chart_title,
    make_timeline_and_area_charts_title,
)
from modules.charting.setup_fig import (
    setup_fig_for_slope_charts,
    setup_fig_for_timeline_charts,
)
from modules.charting.update_layouts import (
    update_slope_chart_layout,
    update_timeline_chart_layout,
)
from modules.data.common_data_utils import identify_close_value_labels
from modules.data.time_series_data_prep import (
    prepare_data_for_slope_plot,
    prepare_data_for_timeline_plot,
)
from modules.utilities.config import (
    get_config_params,
    get_naming_params,
)
from modules.utilities.error_messages import add_empty_dataset_error_message_in_plot_charts_tab
from modules.utilities.helpers import (
    check_if_periods_in_columns,
    duplicate_dataframe,
)
from modules.utilities.utils import (
    get_schema_and_column_names,
    is_valid_lazyframe,
    ensure_lazyframe,
)
from modules.charting.polars_helpers import get_max_value, to_lists

logger = logging.getLogger(__name__)

try:  # pragma: no cover - fallback for tests lacking this helper
    from modules.charting.polars_helpers import column_to_list
except (ImportError, AttributeError) as e:  # pragma: no cover - simple fallback using ``to_lists``
    logger.warning("draw_timeline import error: %s", e)

    def column_to_list(lf: pl.LazyFrame, col: str) -> list:
        """Fallback helper that converts ``col`` to a list using ``to_lists``."""
        return to_lists(lf, [col])[col]

def adjust_slope_plot(fig,df,key,metric,title,height,width,paramDict,chartDict): 
    namingParams=get_naming_params()
    chosenChart=namingParams["chosenChart"]
    chosenChart=chartDict[chosenChart]
    fig=update_slope_chart_layout(fig,chosenChart,height,width) 
    fig,message=get_user_message(fig,chosenChart,metric,key,paramDict,chartDict,df,None,None)
    fig=add_message_as_annotation(fig,message,None,chosenChart,chartDict,paramDict)
    fig=add_title_as_annotation(fig,title,chosenChart,chartDict)
    fig=enable_draw_shapes(fig)
    return fig

def adjust_timeline_plot(fig,df,key,metric,title,height,width,paramDict,chartDict): 
    namingParams=get_naming_params()
    chosenChart=namingParams["chosenChart"]
    chosenChart=chartDict[chosenChart]
    fig=update_timeline_chart_layout(fig,height,width,chosenChart)  
    fig,message=get_user_message(fig,chosenChart,metric,key,paramDict,chartDict,df,None,None)
    fig=add_message_as_annotation(fig,message,None,chosenChart,chartDict,paramDict)
    fig=add_title_as_annotation(fig,title,chosenChart,chartDict)
    fig=enable_draw_shapes(fig)
    return fig   
    
def draw_timeline_chart(
    dfCopy,
    chosenDimension,
    metricArray,
    repeatArray,
    paramDict,
    chartDict,
    uniqueItems,
    aggregateOtherItemsName,
    fullFig,
    metricType,
):
    """
    draw chart
    """
    namingParams=get_naming_params()
    configParams=get_config_params()  
    fontSize=configParams[namingParams["fontSizeText"]] 
    font=configParams[namingParams["fontChoice"]]  
    labelName=namingParams["labelName"] 
    chosenChart=namingParams["chosenChart"]        
    dateName=namingParams["dateName"] 
    totalName=namingParams["totalName"]  
    plotSmallMultiplesKey=namingParams["plotSmallMultiplesOtherCharts"] 
    numberOfPlots=namingParams["numberOfPlots"]  
    plName=namingParams["plName"]
    pyName=namingParams["pyName"]  
    acName=namingParams["acName"] 
    periodName=namingParams["periodName"] 
    smallMultiplesColumn=namingParams["smallMultiplesColumn"]
    configPlotlyDict=configParams["configPlotlyDict"]
    exportDataArray = []
    chosenChart = chartDict[chosenChart]
    configPlotlyDict = configPlotlyDict[chosenChart]
    colorDict = get_color_dictionary(chartDict)
    colorArray = get_color_array(colorDict, chartDict)

    df = ensure_lazyframe(dfCopy)
    if len(uniqueItems) > 1:
        order_map = {v: i for i, v in enumerate(uniqueItems)}
        df = (
            df.with_columns(
                pl.col(chosenDimension).replace(order_map).alias("_ord"),
                pl.col(chosenDimension).cast(pl.Categorical),
            )
            .sort(["_ord", dateName])
            .drop("_ord")
        )
        colorArray = set_other_color_to_grey(
            uniqueItems, aggregateOtherItemsName, colorArray, chartDict, 0
        )

    dfCopy = df
    key=None  
    if is_valid_lazyframe(df): 
      repeatArrayToPlot=[]
      for element in repeatArray:
            repeatArrayToPlot.append(element) 
      if plotSmallMultiplesKey in chartDict and chartDict[plotSmallMultiplesKey]:  
            fig,height,width,numberOfCols,numberOfRows=setup_fig_for_timeline_charts(repeatArrayToPlot,chosenDimension,paramDict,chartDict)
      count,countRows,countCols=1,1,1
      columns,schema=get_schema_and_column_names(df) 
      if chosenDimension in columns and chosenDimension != totalName:        
        if plotSmallMultiplesKey not in chartDict or not chartDict[plotSmallMultiplesKey]:   
            fig,height,width,numberOfCols,numberOfRows=setup_fig_for_timeline_charts(repeatArrayToPlot,chosenDimension,paramDict,chartDict)            
            for metric in metricArray:
                maxValue=get_max_value(df, metric)
                prefix,chartDict,decimals=get_number_prefix(maxValue,chartDict,None,False)
                df1 = prepare_data_for_timeline_plot(
                    df, chosenDimension, metric, uniqueItems, chartDict
                )
                colorArray = insert_highlight_color(
                    chosenDimension, uniqueItems, colorArray, paramDict, chartDict
                )
                fig = add_annotations_to_timeline(
                    df1,
                    fig,
                    uniqueItems,
                    colorArray,
                    chartDict,
                    countRows,
                    countCols,
                )
                fig,fullFig,metricType=keep_same_scale_for_all_plots(fig,metric,metricType,fullFig,"Y")
                fig.update_annotations(font=dict(size=fontSize,family=font)) 
                key=chosenDimension
                titleColumn=chosenDimension  
                title,paramDict,chartDict=make_timeline_and_area_charts_title(df1,chosenChart,paramDict,titleColumn,metric,chartDict,None,None)
                fig=adjust_timeline_plot(fig,df1,key,metric,title,height,width,paramDict,chartDict)
                paramDict=set_up_tab_for_show_or_download_chart(df1,fig,configPlotlyDict,chartDict,metric+chosenDimension,False,None,chosenDimension,paramDict)
        else:
            chartDict[smallMultiplesColumn]=chosenDimension
            maxValue=get_max_value(df, metricArray[0])
            prefix,chartDict,decimals=get_number_prefix(maxValue,chartDict,None,False)
            for column in repeatArrayToPlot:
                df1 = df.filter(pl.col(chosenDimension) == column)
                df1 = prepare_data_for_timeline_plot(
                    df1, chosenDimension, metricArray[0], uniqueItems, chartDict
                )
                exportDataArray.append(df1)
                fig = add_annotations_to_timeline(
                    df1,
                    fig,
                    [column],
                    colorArray,
                    chartDict,
                    countRows,
                    countCols,
                )
                count, countRows, countCols, chartDict = reset_row_and_column_counters(
                    count, countCols, countRows, numberOfCols, numberOfRows, chartDict
                )
                fig.update_annotations(font=dict(size=fontSize, family=font))
      else:    
            paramDict[numberOfPlots]=len(metricArray)       
            for metric in metricArray:
                maxValue=get_max_value(df, metric)
                prefix,chartDict,decimals=get_number_prefix(maxValue,chartDict,None,False)
                if plotSmallMultiplesKey not in chartDict or not chartDict[plotSmallMultiplesKey]:
                    fig,height,width,numberOfCols,numberOfRows=setup_fig_for_timeline_charts(repeatArrayToPlot,chosenDimension,paramDict,chartDict)
                df1 = prepare_data_for_timeline_plot(
                    df, chosenDimension, metric, uniqueItems, chartDict
                )
                fig = add_annotations_to_timeline(
                    df1,
                    fig,
                    uniqueItems,
                    colorArray,
                    chartDict,
                    countRows,
                    countCols,
                )
                count, countRows, countCols, chartDict = reset_row_and_column_counters(
                    count, countCols, countRows, numberOfCols, numberOfRows, chartDict
                )
                fig.update_annotations(font=dict(size=fontSize, family=font))
                if plotSmallMultiplesKey not in chartDict or not chartDict[plotSmallMultiplesKey]:
                    title,paramDict,chartDict=make_timeline_and_area_charts_title(df1,chosenChart,paramDict,"",metric,chartDict,None,None)
                    fig=adjust_timeline_plot(fig,df1,key,metric,title,height,width,paramDict,chartDict)
                    paramDict=set_up_tab_for_show_or_download_chart(df1,fig,configPlotlyDict,chartDict,metric+chosenDimension,False,None,chosenDimension,paramDict)
      if plotSmallMultiplesKey in chartDict and chartDict[plotSmallMultiplesKey]:
        key=chosenDimension                   
        title,paramDict,chartDict=make_timeline_and_area_charts_title(dfCopy,chosenChart,paramDict,key,metricArray[0],chartDict,None,None)
        fig=adjust_timeline_plot(fig,dfCopy,key,metricArray[0],title,height,width,paramDict,chartDict)
        if len(exportDataArray)>1:
            df1=pl.concat(exportDataArray,how="horizontal")
        paramDict=set_up_tab_for_show_or_download_chart(df1,fig,configPlotlyDict,chartDict,metricArray[0]+chosenDimension,False,None,chosenDimension,paramDict)
    else:
        paramDict=add_empty_dataset_error_message_in_plot_charts_tab(paramDict)      
    return fullFig,metricType,paramDict




def draw_slope_chart(dfCopy,chosenDimension,metricArray,repeatArray,paramDict,chartDict,uniqueItems,aggregateOtherItemsName,fullFig,metricType):
    """
    draw chart
    """
    namingParams=get_naming_params()
    configParams=get_config_params()    
    fontSize=configParams[namingParams["fontSizeText"]]   
    font=configParams[namingParams["fontChoice"]]
    chosenChart=namingParams["chosenChart"]        
    dateName=namingParams["dateName"] 
    totalName=namingParams["totalName"]  
    plotSmallMultiplesKey=namingParams["plotSmallMultiplesOtherCharts"] 
    numberOfPlots=namingParams["numberOfPlots"]  
    plName=namingParams["plName"]
    pyName=namingParams["pyName"]  
    acName=namingParams["acName"] 
    periodName=namingParams["periodName"]  
    chosenChart=namingParams["chosenChart"]     
    selectedPeriods=namingParams["selectedPeriods"]
    configPlotlyDict=configParams["configPlotlyDict"]
    chosenChart=chartDict[chosenChart]      
    configPlotlyDict=configPlotlyDict[chosenChart]
    periodOrder=chartDict[selectedPeriods]
    colorDict=get_color_dictionary(chartDict)
    colorArray=get_color_array(colorDict,chartDict)   
    if len(uniqueItems)>1:
        order_map = {v: i for i, v in enumerate(uniqueItems)}
        dfCopy = (
            dfCopy.with_columns(
                pl.col(chosenDimension).replace(order_map).alias("_ord"),
                pl.col(chosenDimension).cast(pl.Categorical),
            )
            .sort([periodName, "_ord"])
            .drop("_ord")
        )
        colorArray=set_other_color_to_grey(uniqueItems,aggregateOtherItemsName,colorArray,chartDict,0)
    checkedPeriodOrder=[]    
    for period in periodOrder:
        dfCopy,period=check_if_periods_in_columns(dfCopy,period)
        checkedPeriodOrder.append(period) 
    order_map_period = {v: i for i, v in enumerate(checkedPeriodOrder)}
    dfCopy = (
        dfCopy.with_columns(
            pl.col(periodName).replace(order_map_period).alias("_ord_period"),
            pl.col(periodName).cast(pl.Categorical),
        )
        .sort("_ord_period")
        .drop("_ord_period")
    )
    df=duplicate_dataframe(dfCopy)
    key=None    
    if is_valid_lazyframe(df): 
      repeatArrayToPlot=[]
      for element in repeatArray:
            repeatArrayToPlot.append(element) 
      if plotSmallMultiplesKey in chartDict and chartDict[plotSmallMultiplesKey]:  
            fig,height,width,numberOfCols,numberOfRows=setup_fig_for_slope_charts(repeatArrayToPlot,chosenDimension,paramDict,chartDict)
      count,countRows,countCols=1,1,1
      columns,schema=get_schema_and_column_names(df) 
      if chosenDimension in columns and chosenDimension != totalName:
        if plotSmallMultiplesKey not in chartDict or not chartDict[plotSmallMultiplesKey]:   
            fig,height,width,numberOfCols,numberOfRows=setup_fig_for_slope_charts(repeatArrayToPlot,chosenDimension,paramDict,chartDict)            
            for metric in metricArray:
                maxValue = get_max_value(df, metric)
                prefix, chartDict, decimals = get_number_prefix(
                    maxValue, chartDict, None, False
                )
                df1=duplicate_dataframe(df)
                df1=identify_close_value_labels(df1,metric,chosenDimension,paramDict,chartDict)
                df1=prepare_data_for_slope_plot(df1,chosenDimension,metric,uniqueItems,paramDict,chartDict)
                colorArray=insert_highlight_color(chosenDimension,uniqueItems,colorArray,paramDict,chartDict) 
                fig=add_annotations_to_timeline(df1,fig,uniqueItems,colorArray,chartDict,countRows,countCols)
                fig,fullFig,metricType=keep_same_scale_for_all_plots(fig,metric,metricType,fullFig,"Y")
                fig.update_annotations(font=dict(size=fontSize,family=font)) 
                key=chosenDimension
                titleColumn=chosenDimension  
                title,paramDict,chartDict=make_slope_and_dot_chart_title(df1,chosenChart,paramDict,titleColumn,metric,chartDict,checkedPeriodOrder[0],checkedPeriodOrder[1]) 
                fig=adjust_slope_plot(fig,df1,key,metric,title,height,width,paramDict,chartDict)
                paramDict=set_up_tab_for_show_or_download_chart(df1,fig,configPlotlyDict,chartDict,chosenDimension+metric,False,None,chosenDimension,paramDict)
        else:
            maxValue = get_max_value(df, metricArray[0])
            prefix, chartDict, decimals = get_number_prefix(
                maxValue, chartDict, None, False
            )
            for column in repeatArrayToPlot:
                df1=duplicate_dataframe(df)
                df1 = df1.filter(pl.col(chosenDimension) == column)
                df1=identify_close_value_labels(df1,metricArray[0],chosenDimension,paramDict,chartDict)
                df1=prepare_data_for_slope_plot(df1,chosenDimension,metricArray[0],uniqueItems,paramDict,chartDict)
                colorArray=insert_highlight_color(chosenDimension,uniqueItems,colorArray,paramDict,chartDict) 
                fig=add_annotations_to_timeline(df1,fig,[column],colorArray,chartDict,countRows,countCols)
                count,countRows,countCols,chartDict=reset_row_and_column_counters(count,countCols,countRows,numberOfCols,numberOfRows,chartDict)
                fig.update_annotations(font=dict(size=fontSize,family=font))  
      else: 
            paramDict[numberOfPlots]=len(metricArray)       
            for metric in metricArray:
                df1 = duplicate_dataframe(df)
                maxValue = get_max_value(df1, metric)
                prefix, chartDict, decimals = get_number_prefix(
                    maxValue, chartDict, None, False
                )
                if plotSmallMultiplesKey not in chartDict or not chartDict[plotSmallMultiplesKey]:
                    fig,height,width,numberOfCols,numberOfRows=setup_fig_for_slope_charts(repeatArrayToPlot,chosenDimension,paramDict,chartDict)  
                df1=identify_close_value_labels(df1,metric,chosenDimension,paramDict,chartDict)   
                df1=prepare_data_for_slope_plot(df1,chosenDimension,metric,uniqueItems,paramDict,chartDict)
                fig=add_annotations_to_timeline(df1,fig,uniqueItems,colorArray,chartDict,countRows,countCols)
                count,countRows,countCols,chartDict=reset_row_and_column_counters(count,countCols,countRows,numberOfCols,numberOfRows,chartDict)
                fig.update_annotations(font=dict(size=fontSize,family=font)) 
                if plotSmallMultiplesKey not in chartDict or not chartDict[plotSmallMultiplesKey]:  
                    title,paramDict,chartDict=make_slope_and_dot_chart_title(df1,chosenChart,paramDict,chosenDimension,metric,chartDict,periodOrder[0],periodOrder[1]) 
                    fig=adjust_slope_plot(fig,df1,key,metric,title,height,width,paramDict,chartDict)
                    paramDict=set_up_tab_for_show_or_download_chart(df1,fig,configPlotlyDict,chartDict,chosenDimension+metric,False,None,chosenDimension,paramDict)
      if plotSmallMultiplesKey in chartDict and chartDict[plotSmallMultiplesKey]:
        key=chosenDimension            
        title,paramDict,chartDict=make_slope_and_dot_chart_title(df1,chosenChart,paramDict,key,metricArray[0],chartDict,periodOrder[0],periodOrder[1]) 
        fig=adjust_slope_plot(fig,dfCopy,key,metricArray[0],title,height,width,paramDict,chartDict)
        paramDict=set_up_tab_for_show_or_download_chart(dfCopy,fig,configPlotlyDict,chartDict,chosenDimension+metricArray[0],False,None,chosenDimension,paramDict)
    else:
        paramDict=add_empty_dataset_error_message_in_plot_charts_tab(paramDict)      
    return fullFig,metricType,paramDict

def set_text_position_array_for_dot_plot(
    df: pl.DataFrame | pl.LazyFrame, metric: str
) -> list[str]:
    """Return label positions for dot charts."""

    naming_params = get_naming_params()
    textposition = naming_params["textposition"]
    max_value = naming_params["maxValue"]
    lf = ensure_lazyframe(df)
    if not is_valid_lazyframe(lf):
        return []

    expr = (
        pl.when(pl.col(metric) == pl.col(max_value))
        .then(pl.lit("middle right"))
        .otherwise(pl.lit("middle left"))
        .alias(textposition)
    )
    result = column_to_list(lf.select(expr), textposition)
    return result

def draw_dot_chart(
    dfCopy: pl.DataFrame | pl.LazyFrame,
    paramDict: dict,
    chosenDimension: str,
    metric: str,
    xColumn: str,
    chartDict: dict,
    count: int,
    uniqueItems: list[str],
    periodOrder: list[str],
    aggregateOtherItemsName: str,
) -> tuple[go.Figure, pl.LazyFrame]:
    """Draw dot chart for two periods."""
    from modules.utilities.utils import ensure_lazyframe
    namingParams=get_naming_params()
    configParams=get_config_params()
    fontSize=configParams[namingParams["fontSizeText"]] 
    font=configParams[namingParams["fontChoice"]] 
    labelName=namingParams["labelName"]
    yShiftName=namingParams["yShiftName"]
    xShiftName=namingParams["xShiftName"]    
    separatorString=namingParams["separatorString"]   
    chosenChart=namingParams["chosenChart"]  
    dotChart=namingParams["dotChart"]      
    periodName=namingParams["periodName"]
    maxValueKey=namingParams["maxValue"]  
    colorName=namingParams["colorName"]        
    colorDict=get_color_dictionary(chartDict)
    almostBlackColor=colorDict["almostBlackColor"] 
    greyColor=colorDict["greyColor"] 
    lightGreyColor=colorDict["lightGreyColor"]
    chosenChart=chartDict[chosenChart]
    if len(uniqueItems)>1:
        order_map = {v: i for i, v in enumerate(uniqueItems)}
        dfCopy = (
            dfCopy.with_columns(
                pl.col(chosenDimension).replace(order_map).alias("_ord"),
                pl.col(chosenDimension).cast(pl.Categorical),
            )
            .sort(["_ord", xColumn])
            .drop("_ord")
        )
    df=duplicate_dataframe(dfCopy)
    df = ensure_lazyframe(df)
    colorSequenceArray,lineWidth=get_color_sequence(df,paramDict,chartDict)
    numberOfRows=1 
    numberOfCols=1
    sharedXaxes="all"
    sharedYaxes=None
    verticalSpacing=0
    horizontalSpacing=0 
    countRows=1
    countCols=1
    subplotTitles=[]
    labelArray=[]
    yShiftArray=[]
    xShiftArray=[] 
    redGreenColorDict={0:colorDict["greenColor"],1:colorDict["redColor"]} 
    if is_valid_lazyframe(df):
        df = df.drop_nulls(subset=[chosenDimension])
        columns, schema = get_schema_and_column_names(df)
        maxValue = 0.0
        if maxValueKey in columns:
            maxValue = get_max_value(df, maxValueKey)
            prefix, chartDict, decimals = get_number_prefix(
                maxValue, chartDict, None, False
            )
        fig = make_subplots(rows=numberOfRows,
                          cols=numberOfCols,
                          shared_xaxes=sharedXaxes,
                          shared_yaxes=sharedYaxes,
                          vertical_spacing=verticalSpacing,
                          horizontal_spacing=horizontalSpacing,
                          subplot_titles=subplotTitles,
                              ) 
        counter = 0
        df0_lf = df.filter(pl.col(periodName) == periodOrder[counter])
        df0_lf, chartDict = millify_dataframe(
            df0_lf, metric, None, labelName, chartDict
        )
        df0_lf = df0_lf.with_columns(
            pl.col(metric).fill_null(0).alias(metric),
            pl.when(pl.col(labelName) == "0.0")
            .then(pl.lit(""))
            .otherwise(pl.col(labelName))
            .alias(labelName),
            pl.lit(0).alias("_period_idx"),
        )

        counter = 1
        df1_lf = (
            df.filter(pl.col(periodName) == periodOrder[counter])
            .with_row_index(name="_idx")
            .sort("_idx", descending=True)
            .drop("_idx")
        )
        df1_lf, chartDict = millify_dataframe(
            df1_lf, metric, None, labelName, chartDict
        )
        df1_lf = df1_lf.with_columns(
            pl.col(metric).fill_null(0).alias(metric),
            pl.when(pl.col(labelName) == "0.0")
            .then(pl.lit(""))
            .otherwise(pl.col(labelName))
            .alias(labelName),
            pl.lit(1).alias("_period_idx"),
        )

        combined = pl.concat([df0_lf, df1_lf])

        df0_lf = combined.filter(pl.col("_period_idx") == 0)
        df1_lf = combined.filter(pl.col("_period_idx") == 1)

        df0_lists = to_lists(
            df0_lf, [metric, chosenDimension, labelName, colorName, maxValueKey]
        )
        df1_lists = to_lists(
            df1_lf, [metric, chosenDimension, labelName, colorName, maxValueKey]
        )
        category_totals: dict[str, float] = {}
        for categories, values in (
            (df0_lists[chosenDimension], df0_lists[metric]),
            (df1_lists[chosenDimension], df1_lists[metric]),
        ):
            for category, value in zip(categories, values):
                category_key = str(category)
                category_totals[category_key] = category_totals.get(
                    category_key, 0.0
                ) + float(value or 0.0)
        ranked_categories = sorted(
            category_totals, key=lambda category: category_totals[category]
        )

        expr = (
            pl.when(pl.col(metric) == pl.col(maxValueKey))
            .then(pl.lit("middle right"))
            .otherwise(pl.lit("middle left"))
            .alias("_textpos")
        )
        textposition0 = column_to_list(df0_lf.select(expr), "_textpos")
        textposition1 = column_to_list(df1_lf.select(expr), "_textpos")

        fig.add_trace(
            go.Scatter(
                x=df0_lists[metric],
                y=df0_lists[chosenDimension],
                marker=dict(
                    color=colorSequenceArray[0],
                    size=16,
                    line=dict(width=0.5, color=greyColor),
                ),
                mode="markers+text",
                name=periodOrder[0],
                text=df0_lists[labelName],
                textposition=textposition0,
                cliponaxis=False,
                orientation="h",
            )
        )

        fig.add_trace(
            go.Scatter(
                x=df1_lists[metric],
                y=df1_lists[chosenDimension],
                marker=dict(
                    color=colorSequenceArray[1],
                    size=16,
                    line=dict(width=0.5, color=greyColor),
                ),
                mode="markers+text",
                name=periodOrder[1],
                text=df1_lists[labelName],
                textposition=textposition1,
                cliponaxis=False,
                orientation="h",
            )
        )

        metric0 = df0_lists[metric]
        metric1 = df1_lists[metric]
        len0 = len(metric0)
        len1 = len(metric1)
        df_shorter_colors = (
            df0_lists[colorName] if len0 <= len1 else df1_lists[colorName]
        )
        for i in range(min(len0, len1)):
            fig.add_shape(
                type="line",
                layer="below",
                x0=metric0[i],
                y0=df0_lists[chosenDimension][i],
                x1=metric1[i],
                y1=df1_lists[chosenDimension][i],
                xref="x",
                yref="y",
                line_color=redGreenColorDict[df_shorter_colors[i]],
            )
        if ranked_categories:
            fig.update_yaxes(
                categoryorder="array",
                categoryarray=ranked_categories,
            )
    else:
        paramDict=add_empty_dataset_error_message_in_plot_charts_tab(paramDict)                
    return fig,df


def add_annotations_to_timeline(
    df: pl.DataFrame | pl.LazyFrame,
    fig: go.Figure,
    uniqueItems: list[str],
    colorArray: list[str],
    chartDict: dict,
    countRows: int,
    countCols: int,
) -> go.Figure:
    """Add traces and annotations for a timeline chart."""

    namingParams = get_naming_params()
    chosenChart = chartDict[namingParams["chosenChart"]]
    separator = namingParams["separatorString"]
    labelName = namingParams["labelName"]
    yShiftName = namingParams["yShiftName"]
    xShiftName = namingParams["xShiftName"]
    dateName = namingParams["dateName"]

    lf = ensure_lazyframe(df)
    columns, _ = get_schema_and_column_names(lf)
    available = [c for c in uniqueItems if c in columns]

    labelArray = [f"{c}{separator}{labelName}" for c in available]
    yShiftArray = [f"{c}{separator}{yShiftName}" for c in available]
    xShiftArray = [f"{c}{separator}{xShiftName}" for c in available]

    for idx, column in enumerate(available):
        lf = prepare_value_labels_for_timeline(
            lf,
            chosenChart,
            column,
            labelArray,
            yShiftArray,
            xShiftArray,
            chartDict,
            idx,
        )

    date_cols = [dateName] if dateName in columns else []
    cols = date_cols + available + labelArray + yShiftArray + xShiftArray
    lists = to_lists(lf, cols)
    date_values = lists[dateName] if dateName in lists else []

    for idx, column in enumerate(available):
        positions = list(range(len(lists[column])))
        use_date_axis = bool(date_values) and len(date_values) == len(lists[column])
        x_values = date_values if use_date_axis else positions
        fig.add_trace(
            go.Scatter(
                x=x_values,
                y=[round(val, 1) for val in lists[column]],
                line=dict(color=colorArray[idx]),
                showlegend=False,
                mode="lines+markers",
                hovertext=column,
            ),
            row=countRows,
            col=countCols,
        )
        if use_date_axis:
            fig.update_xaxes(
                type="date",
                tickformat="%b %Y",
                nticks=6,
                row=countRows,
                col=countCols,
            )

    for idx, element in enumerate(labelArray):
        if len(uniqueItems) > 1:
            fig = add_non_cumulated_legends(
                fig,
                lists,
                chosenChart,
                uniqueItems,
                chartDict,
                countRows,
                countCols,
                idx,
            )
        fig = add_labels_to_timeline_chart(
            fig,
            lf,
            element,
            chosenChart,
            uniqueItems[idx],
            lists[labelArray[idx]],
            lists[yShiftArray[idx]],
            lists[xShiftArray[idx]],
            countRows,
            countCols,
        )

    return fig

def add_labels_to_timeline_chart(
    fig: go.Figure,
    df_lazy: pl.DataFrame | pl.LazyFrame,
    element: str,
    chosenChart: str,
    uniqueItem: str,
    labels: Sequence[str],
    yShifts: Sequence[int | float],
    xShifts: Sequence[int | float],
    countRows: int,
    countCols: int,
) -> go.Figure:
    """Add value labels on the timeline traces."""

    namingParams = get_naming_params()
    slopeChart = namingParams["slopeChart"]
    dateName = namingParams["dateName"]

    lf = ensure_lazyframe(df_lazy)
    columns, _ = get_schema_and_column_names(lf)
    date_values = []
    if dateName in columns and chosenChart not in [slopeChart]:
        date_values = column_to_list(lf, dateName)

    min_max_vals = list(labels)
    up_down_vals = list(yShifts)
    right_left_vals = list(xShifts)

    countArray = 0
    for idx, value in enumerate(min_max_vals):
        x = date_values[idx] if idx < len(date_values) else idx
        if chosenChart in [slopeChart]:
            x = countArray
            if countArray == 0:
                countArray += 1
            else:
                countArray = 0

        if value != "":
            xshift = right_left_vals[idx]
            yshift = up_down_vals[idx]
            if chosenChart in [slopeChart]:
                yshift = 0

            fig.add_annotation(
                text=value,
                showarrow=False,
                x=x,
                xshift=xshift,
                xref="x",
                align="center",
                yshift=yshift,
                y=get_polars_value_at_index(lf, uniqueItem, idx),
                yref="y",
                hovertext=str(value) + " " + element[:-6],
                row=countRows,
                col=countCols,
            )

    return fig

# fmt: on
# fmt: on
# isort: on
# fmt: on
# isort: on
