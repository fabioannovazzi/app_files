"""Waterfall chart drawing utilities.

This module relies on **Polars**. When counting rows in a DataFrame or
LazyFrame, prefer using ``frame.height`` or ``get_row_count``.
"""

import polars as pl
import numpy as np
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import math
import copy



from modules.charting.chart_helpers import (
    get_pinhead_outliers,
    set_up_tab_for_show_or_download_chart,
)
from modules.charting.chart_primitives import (
    add_message_as_annotation,
    add_sign_to_labels,
    add_title_as_annotation,
    check_if_plan_or_py,
    divide_by_value_prefix,
    enable_draw_shapes,
    get_color_choice,
    get_color_dictionary,
    get_color_sequence,
    get_user_message,
    millify_dataframe,
    reset_row_and_column_counters,
)
from modules.charting.draw_charts_utils import (
    add_negative_outlier_pins_to_column,
    add_percent_change_markers_to_column,
    add_positive_outlier_pins_to_column,
    get_text_template,
)
from modules.charting.draw_multitier import (
    add_absolute_value_bars_to_multitier_column,
    add_negative_outlier_pins_to_bar,
    add_percent_change_markers_to_bar,
    add_positive_outlier_pins_to_bar,
)
from modules.charting.make_titles import make_horizontal_waterfall_chart_title
from modules.charting.setup_fig import setup_fig_for_horizontal_waterfall_charts
from modules.charting.update_layouts import update_horizontal_waterfall_layout
from modules.data.misc_charts_data_prep import create_color_column
from modules.data.waterfall_data_prep import (
    get_waterfall_number_format,
    prepare_data_for_horizontal_waterfall_plot,
    prepare_horizontal_waterfall_data_for_openAi,
)
from modules.utilities.config import (
    get_config_params,
    get_naming_params,
    get_variance_aggregation_params,
)
from modules.utilities.helpers import (
    drop_columns,
    duplicate_dataframe,
    get_periods_array,
    unique,
)
from modules.utilities.utils import (
    get_schema_and_column_names,
    is_valid_lazyframe,
    get_row_count,
    ensure_polars_df,
)
























def color_first_bar_vertical(df,fig,paramDict,chartDict,colorDict,run):
    """
    colors first bar based on if planned or previous data
    """
    namingParams=get_naming_params()
    showInitialAndFinalValues=namingParams["showInitialAndFinalValues"] 
    varianceAmountName=namingParams["varianceAmountName"]
    workColumn=namingParams["workColumn"]
    drilldownReportRunName=namingParams["drilldownReportRunName"] 
    totalVarianceAggregation=namingParams["totalVarianceAggregation"]
    isYearBeforePy=namingParams["isYearBeforePy"] 
    marginVarianceAggregation=namingParams["marginVarianceAggregation"] 
    varianceAggregation=namingParams["varianceAggregation"]
    netOfDiscountAggregation=namingParams["netOfDiscountAggregation"] 
    initialAndFinalValuesCanBeShown=True
    if chartDict[varianceAggregation] not in [totalVarianceAggregation,netOfDiscountAggregation,marginVarianceAggregation] and drilldownReportRunName in run:
        initialAndFinalValuesCanBeShown=False  
    if showInitialAndFinalValues in chartDict and chartDict[showInitialAndFinalValues] and initialAndFinalValuesCanBeShown: 
          # Retrieve first label/value in a Polars-friendly way (works for DataFrame or LazyFrame)
          lf = df.lazy() if isinstance(df, pl.DataFrame) else df
          _vals = (
              lf.select(
                  pl.col(workColumn).first().alias("__first_label"),
                  pl.col(varianceAmountName).first().alias("__first_var"),
              )
              .collect(engine="streaming")
          )
          firstLabel = _vals["__first_label"][0]
          firstVar = _vals["__first_var"][0]
          isExpectedData,planName=check_if_plan_or_py([firstLabel])  
          firstBarColor,lineWidth,lineColor=set_semantic_bar_color(isExpectedData,colorDict,paramDict) 
          fig.add_shape(type="rect",fillcolor=firstBarColor,opacity=1, 
                  line_width=lineWidth,line_color=lineColor,
                  y0=-0.4, y1=0.4, yref="y",
                  x0=0, x1=firstVar, xref="x",
                  row=1,col=1
                        )
    return fig

def set_semantic_bar_color(isExpectedData,colorDict,paramDict):
    namingParams=get_naming_params()
    isYearBeforePy=namingParams["isYearBeforePy"]     
    if isExpectedData:
        firstBarColor,lineWidth,lineColor=colorDict["whiteColor"],0.5,colorDict["lightGreyColor"]
    elif isYearBeforePy in paramDict and paramDict[isYearBeforePy]:
        firstBarColor,lineWidth,lineColor=colorDict["veryLightGreyColor"],0.5,colorDict["veryLightGreyColor"]   
    else:
        firstBarColor,lineWidth,lineColor=colorDict["lightGreyColor"],0.5,colorDict["lightGreyColor"]
    return firstBarColor,lineWidth,lineColor   

def add_total_variance_arrow_horizontal(df,fig,paramDict,chartDict,colorDict,run,metric,row,col):
    """
    we add the red or green arrow total variance annotation
    """
    namingParams=get_naming_params()
    configParams=get_config_params()
    font=configParams[namingParams["fontChoice"]] 
    fontSize=configParams[namingParams["fontSizeText"]]
    varianceAmountName=namingParams["varianceAmountName"]
    showInitialAndFinalValues=namingParams["showInitialAndFinalValues"] 
    drilldownReportRunName=namingParams["drilldownReportRunName"]
    fcName=namingParams["fcName"]
    acName=namingParams["acName"]    
    firstBarColor,lineWidth,lineColor=colorDict["whiteColor"],0.5,colorDict["lightGreyColor"]
    columns, schema = get_schema_and_column_names(df)
    lf = df.lazy() if isinstance(df, pl.DataFrame) else df
    values = (
        lf.select(
            pl.col(varianceAmountName).first().alias("_p0"),
            pl.col(varianceAmountName).last().alias("_p1"),
        )
        .collect(engine="streaming")
    )
    periodZeroValue = values["_p0"][0]
    periodOneValue = values["_p1"][0]
    if fcName in columns:
        sums = (
            lf.select(
                pl.col(acName).sum().alias("_ac_sum"),
                pl.col(fcName).sum().alias("_fc_sum"),
            )
            .collect(engine="streaming")
        )
        periodOneValue = sums["_ac_sum"][0] + sums["_fc_sum"][0]
    totalVarianceAggregation=namingParams["totalVarianceAggregation"] 
    marginVarianceAggregation=namingParams["marginVarianceAggregation"] 
    varianceAggregation=namingParams["varianceAggregation"] 
    discountName=namingParams["discountName"] 
    indirectCostsName=namingParams["indirectCostsName"] 
    deltaName=namingParams["deltaName"]
    cogsName=namingParams["cogsName"] 
    reverseColorMetricsArray=[discountName,indirectCostsName,cogsName]  
    initialAndFinalValuesCanBeShown=True
    if varianceAggregation in chartDict:
        if chartDict[varianceAggregation] not in [totalVarianceAggregation,marginVarianceAggregation] and drilldownReportRunName in run:
            initialAndFinalValuesCanBeShown=False 
    if showInitialAndFinalValues in chartDict and chartDict[showInitialAndFinalValues] and initialAndFinalValuesCanBeShown: 
          if metric in reverseColorMetricsArray:
              if periodOneValue >= periodZeroValue:
                arrowColor=colorDict["redColor"]
              else:
                arrowColor=colorDict["greenColor"] 
          else:    
              if periodOneValue >= periodZeroValue:
                arrowColor=colorDict["greenColor"]
              else:
                arrowColor=colorDict["redColor"]   
          fig.add_shape(type="line",opacity=1, 
                        line_width=lineWidth,line_color=lineColor,
                        x0=-.4, x1=df.height, xref="paper",
                        y0=periodZeroValue, y1=periodZeroValue, yref="y",
                        row=row, col=col,
                              ) 
          fig.add_shape(type="line",opacity=1, 
                        line_width=lineWidth,line_color=lineColor,
                        x0=df.height - 1, x1=df.height, xref="paper",
                        y0=periodOneValue, y1=periodOneValue, yref="y",
                        row=row, col=col,
                              )
          fig.add_shape(
                        type="line",
                        opacity=1, 
                        line_width=5,line_color=arrowColor,
                        x1=df.height, x0=df.height, xref="paper",
                        y1=periodZeroValue, y0=periodOneValue, yref="y",
                        row=row, col=col,
                             )
          if periodZeroValue !=0:
            percentChange=((periodOneValue-periodZeroValue)/periodZeroValue)*100
            difference=(periodOneValue-periodZeroValue)
            difference=divide_by_value_prefix(difference,chartDict,False)
            difference=deltaName+" "+str(difference)
            if not math.isnan(percentChange):
                percentChange="<i>("+str(int(round(percentChange,0)))+"%)</i>"
            else:
                percentChange=""
            changevalue=difference+"<br>"+percentChange
            fig.add_annotation(
                        showarrow = False,
                        text=changevalue, 
                        align="center",
                        font=dict(
                                family=font,
                                size=fontSize,
                            ),
                        yshift=-10,
                        xshift=20,
                        ax=df.height, x=df.height, xref="paper",
                        ay=periodZeroValue, y=periodOneValue, 
                        yref="y",ayref="y",
                        row=row, col=col,
                              ) 
          else:
            periodZeroValue=deltaName+" nan"                 
    return fig

def color_first_bar_horizontal(df,fig,paramDict,chartDict,colorDict,run,row,col):
    """t
    colors first bar based on if planned or previous data
    """
    namingParams=get_naming_params()
    showInitialAndFinalValues=namingParams["showInitialAndFinalValues"] 
    varianceAmountName=namingParams["varianceAmountName"]
    workColumn=namingParams["workColumn"]
    drilldownReportRunName=namingParams["drilldownReportRunName"] 
    totalVarianceAggregation=namingParams["totalVarianceAggregation"] 
    marginVarianceAggregation=namingParams["marginVarianceAggregation"] 
    varianceAggregation=namingParams["varianceAggregation"] 
    initialAndFinalValuesCanBeShown=True
    if varianceAggregation in chartDict:
        if chartDict[varianceAggregation] not in [totalVarianceAggregation,marginVarianceAggregation] and drilldownReportRunName in run:
            initialAndFinalValuesCanBeShown=False  
    if showInitialAndFinalValues in chartDict and chartDict[showInitialAndFinalValues] and initialAndFinalValuesCanBeShown: 
          # Retrieve first label/value in a Polars-friendly way (works for DataFrame or LazyFrame)
          lf = df.lazy() if isinstance(df, pl.DataFrame) else df
          _vals = (
              lf.select(
                  pl.col(workColumn).first().alias("__first_label"),
                  pl.col(varianceAmountName).first().alias("__first_var"),
              )
              .collect(engine="streaming")
          )
          firstLabel = _vals["__first_label"][0]
          firstVar = _vals["__first_var"][0]
          isExpectedData,planName=check_if_plan_or_py([firstLabel])  
          if isExpectedData:
            firstBarColor,lineWidth,lineColor=colorDict["whiteColor"],0.5,colorDict["lightGreyColor"]
          else:
            firstBarColor,lineWidth,lineColor=colorDict["lightGreyColor"],0.5,colorDict["lightGreyColor"]
          fig.add_shape(type="rect",fillcolor=firstBarColor,opacity=1, 
                  line_width=lineWidth,line_color=lineColor,
                  x0=-0.4, x1=0.4, xref="x",
                  y0=0, y1=firstVar, yref="y",
                  row=row,col=col,
                        )
    return fig 

def add_annotations_to_horizontal_waterfall_plot(fig,dfCopy,metric,colorDict,chartDict,paramDict,row,col,plotWithPins):
    """Plot a horizontal waterfall chart with annotations.

    Row counts within this function rely on ``df.height`` to follow Polars
    idioms.
    """
    namingParams=get_naming_params()
    configParams=get_config_params()
    periodsArray=configParams["periodsArray"]
    runVariableDimensionalAnalysis=namingParams["runVariableDimensionalAnalysis"]
    measureName=namingParams["measureName"]
    varianceAmountName=namingParams["varianceAmountName"]
    varianceTypeName=namingParams["varianceTypeName"]
    workColumn=namingParams["workColumn"]
    workColumnTwo=namingParams["workColumnTwo"] 
    processingChoice=namingParams["processingChoice"] 
    horizontalWaterfallChart=namingParams["horizontalWaterfallChart"] 
    totalVarianceAggregation=namingParams["totalVarianceAggregation"]
    marginVarianceAggregation=namingParams["marginVarianceAggregation"]
    varianceAggregation=namingParams["varianceAggregation"]
    variancePercentChangeName=namingParams["variancePercentChangeName"]
    marginVariance=namingParams["marginVariance"]  
    drilldownReportRunName=namingParams["drilldownReportRunName"]  
    separatorString=namingParams["separatorString"] 
    amountName=namingParams["monetaryLocalCurrencyName"] 
    marginName=namingParams["marginName"] 
    plotSmallMultiplesKey=namingParams["plotSmallMultiplesOtherCharts"] 
    varianceInPercent=namingParams["varianceInPercent"]
    shareOfTotalMarket=namingParams["shareOfTotalMarket"] 
    selectedPeriods=namingParams["selectedPeriods"]
    filterDates=namingParams["filterDates"]
    dateName=namingParams["dateName"] 
    acName=namingParams["acName"]
    pyName=namingParams["pyName"]
    plName=namingParams["plName"]
    fcName=namingParams["fcName"]
    labelName=namingParams["labelName"]
    discountName=namingParams["discountName"] 
    indirectCostsName=namingParams["indirectCostsName"] 
    cogsName=namingParams["cogsName"]  
    compareScenariosOrPeriods=namingParams["compareScenariosOrPeriods"] 
    compareScenarios=namingParams["compareScenarios"]
    periodOrder=chartDict[selectedPeriods]
    reverseColorMetricsArray=[discountName,indirectCostsName,cogsName] 
    if plotWithPins or plotSmallMultiplesKey not in chartDict or not chartDict[plotSmallMultiplesKey]:
        row,col=2,1
    df=duplicate_dataframe(dfCopy) 
    orientation="v"
    columns,schema=get_schema_and_column_names(df)
    if filterDates in chartDict and chartDict[filterDates]:
        if fcName in columns:
            yArray=[plName,fcName,acName]
        else:
            yArray=[plName,acName]
    else:
        yArray=[pyName,acName]               
    df=create_color_column(df,metric,yArray,horizontalWaterfallChart,paramDict,chartDict) 
    colorSequenceArray,lineWidth=get_color_sequence(df,paramDict,chartDict)
    colorChoice=get_color_choice(chartDict)
    if metric in reverseColorMetricsArray:
        decreasingColorDict={"marker":{"color":colorDict["greenColor"]}}
        increasingColorDict={"marker":{"color":colorDict["redColor"]}}
    else:
        decreasingColorDict={"marker":{"color":colorDict["redColor"]}}
        increasingColorDict={"marker":{"color":colorDict["greenColor"]}}   
    df,chartDict=add_sign_to_labels(df,horizontalWaterfallChart,workColumnTwo,1,False,chartDict) 
    if compareScenariosOrPeriods in chartDict and chartDict[compareScenariosOrPeriods]==compareScenarios:
        columns,schema=get_schema_and_column_names(df) 
    texttemplate,textformat=get_text_template(chartDict)  
    df = df.with_columns(
        pl.when(pl.col(dateName) != "")
        .then(pl.concat_str([pl.lit("  "), pl.col(workColumn)]))
        .otherwise(pl.col(workColumn))
        .alias(workColumn),
        pl.when(pl.col(dateName) != "")
        .then(pl.concat_str([pl.lit("  "), pl.col(dateName)]))
        .otherwise(pl.col(dateName))
        .alias(dateName),
    )
    fig.add_trace(go.Waterfall(
            orientation = orientation, 
            measure = df[measureName],
            x =df[workColumn],
            y = df[varianceAmountName],
            textinfo="text",
            text =df[labelName],
            texttemplate=texttemplate,
            decreasing = decreasingColorDict,
            increasing = increasingColorDict,
            totals = {"marker":{"color":colorSequenceArray[1]}},#colorDict["greyColor"]}},
            connector = {"mode":"between", "line":{"width":1, "color":"rgb(169,169,169)", "dash":"solid"}},
            textposition = "outside",
            cliponaxis = False,
         ),
        row=row, col=col) 
    anchos = [0.68] * get_row_count(df)    
    periodOrder=[yArray[0],yArray[1]] 
    dfCopy = duplicate_dataframe(df)
    last_idx = pl.len() - 1
    dfCopy = (
        dfCopy.with_row_index("_idx")
        .with_columns(
            pl.when((pl.col("_idx") == 0) | (pl.col("_idx") == last_idx))
            .then(pl.lit(None))
            .otherwise(pl.col(yArray[0]))
            .alias(yArray[0]),
            pl.when((pl.col("_idx") == 0) | (pl.col("_idx") == last_idx))
            .then(pl.lit(None))
            .otherwise(pl.col(yArray[1]))
            .alias(yArray[1]),
        )
        .drop("_idx")
    )
    showAbsoluteValueBars=True
    anchosPercent = [0.48/4] * get_row_count(dfCopy)    
    if plotWithPins or plotSmallMultiplesKey not in chartDict or not chartDict[plotSmallMultiplesKey]:
        df, largestArray, smallestArray, chartDict = get_pinhead_outliers(dfCopy, chartDict)
        df = ensure_polars_df(df)
        fig = add_percent_change_markers_to_column(fig, df, colorChoice, lineWidth, 24)
        fig=add_positive_outlier_pins_to_column(fig,df,largestArray,colorDict,1)
        fig=add_negative_outlier_pins_to_column(fig,df,smallestArray,colorDict,1)
        fig=add_label_to_horizontal_waterflow(fig,1)  
    else:     
        pass  
    colorSequenceArray,lineWidth=get_color_sequence(df,paramDict,chartDict) 
    constant=24 
    offset=-0.2 
    fig,df,chartDict=add_absolute_value_bars_to_multitier_column(fig,df,metric,paramDict,offset,constant,colorSequenceArray,lineWidth,row,col,chartDict)  
    if get_row_count(df)>=12:
        pass
        fig=add_total_variance_arrow_horizontal(df,fig,paramDict,chartDict,colorDict,horizontalWaterfallChart,metric,row,col)        
    fig=color_first_bar_horizontal(df,fig,paramDict,chartDict,colorDict,horizontalWaterfallChart,row,col)
    return fig,chartDict        

def adjust_horizontal_waterfall_plot(fig,df,key,metric,title,height,width,paramDict,chartDict,plotWithPins):
    namingParams=get_naming_params()
    configParams=get_config_params()
    font=configParams[namingParams["fontChoice"]]  
    chosenChart=namingParams["chosenChart"]
    chosenChart=chartDict[chosenChart]
    fig=update_horizontal_waterfall_layout(df,fig,height,width,paramDict,chartDict,plotWithPins) 
    fig,message=get_user_message(fig,chosenChart,metric,key,paramDict,chartDict,df,width,None)
    fig=add_message_as_annotation(fig,message,None,chosenChart,chartDict,paramDict)
    fig=add_title_as_annotation(fig,title,chosenChart,chartDict)
    fig.update_annotations(font=dict(size=10,family=font))
    fig=enable_draw_shapes(fig)
    return fig  

def draw_horizontal_waterfall_chart(dfCopy,chosenDimension,metricArray,repeatArray,paramDict,chartDict):
    """Build and plot a horizontal waterfall chart.

    Row counts and array lengths are computed using ``frame.height`` where
    applicable to maintain Polars style.
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
    configPlotlyDict=configPlotlyDict[chosenChart]
    exportDataArray=[] 
    colorDict=get_color_dictionary(chartDict)
    numberOfMetrics=len(metricArray)
    key=None
    if is_valid_lazyframe(dfCopy): 
      repeatArrayToPlot=[]
      for element in repeatArray:
        repeatArrayToPlot.append(element) 
      columns,schema=get_schema_and_column_names(dfCopy)
      count,countRows,countCols=1,1,1 
      plotWithPins=False
      if chosenDimension == None and numberOfMetrics ==1:
        plotWithPins=True 
      if plotSmallMultiplesKey in chartDict and chartDict[plotSmallMultiplesKey]:
            fig,height,width,numberOfCols,numberOfRows=setup_fig_for_horizontal_waterfall_charts(repeatArrayToPlot,chosenDimension,chartDict,plotWithPins) 
      if chosenDimension in columns: 
            paramDict[numberOfPlots]=len(repeatArray)
            #fullFig=False
            #metricType=False
            #same scale does not work here because Other Rank > is plotted as last
            for column in repeatArray:
                  df=duplicate_dataframe(dfCopy)
                  periodsArray=get_periods_array(df)
                  df = df.filter(pl.col(chosenDimension) == column)
                  if plName in periodsArray:
                    pyName=plName
                  df=drop_columns(df,[chosenDimension])
                  for metric in metricArray:
                    if plotSmallMultiplesKey not in chartDict or not chartDict[plotSmallMultiplesKey]:
                        fig,height,width,numberOfCols,numberOfRows=setup_fig_for_horizontal_waterfall_charts(repeatArrayToPlot,chosenDimension,chartDict,plotWithPins)
                    df,paramDict=prepare_data_for_horizontal_waterfall_plot(df,column,metric,paramDict,chartDict)
                    dfDim=duplicate_dataframe(df)
                    # Add chosenDimension as a new column (Polars) and place it first
                    dfDim = dfDim.with_columns(pl.lit(column).alias(chosenDimension))
                    cols, _ = get_schema_and_column_names(dfDim)
                    if cols and cols[0] != chosenDimension:
                        dfDim = dfDim.select([chosenDimension] + [c for c in cols if c != chosenDimension])
                    dfDim=prepare_horizontal_waterfall_data_for_openAi(dfDim,chartDict)
                    exportDataArray.append(dfDim)
                    fig,chartDict=add_annotations_to_horizontal_waterfall_plot(fig,df,metric,colorDict,chartDict,paramDict,countRows,countCols,plotWithPins)
                    count,countRows,countCols,chartDict=reset_row_and_column_counters(count,countCols,countRows,numberOfCols,numberOfRows,chartDict)
                    if plotSmallMultiplesKey not in chartDict or not chartDict[plotSmallMultiplesKey]:
                        key=chosenDimension+column
                        titleColumn=chosenDimension+": "+column   
                        title,paramDict,chartDict=make_horizontal_waterfall_chart_title(df,chosenChart,paramDict,titleColumn,metric,chartDict,pyName,acName)
                            #fig,fullFig,metricType=keep_same_scale_for_all_plots(fig,metric,metricType,fullFig,"Y")
                            #same scale does not work here because Other Rank > is plotted as last)     
                        fig=adjust_horizontal_waterfall_plot(fig,df,key,metric,title,height,width,paramDict,chartDict,plotWithPins)
                        df1=duplicate_dataframe(df)
                        # Add chosenDimension as a new column (Polars) and place it first
                        df1 = df1.with_columns(pl.lit(column).alias(chosenDimension))
                        cols1, _ = get_schema_and_column_names(df1)
                        if cols1 and cols1[0] != chosenDimension:
                            df1 = df1.select([chosenDimension] + [c for c in cols1 if c != chosenDimension])
                        df1=prepare_horizontal_waterfall_data_for_openAi(df1,chartDict)
                        paramDict=set_up_tab_for_show_or_download_chart(df1,fig,configPlotlyDict,chartDict,title,False,None,chosenDimension,paramDict)
      else: 
            paramDict[numberOfPlots]=len(metricArray) 
            periodsArray=dfCopy[periodName].unique().to_list()
            if plName in periodsArray:
                    pyName=plName                   
            for metric in metricArray:
                df=duplicate_dataframe(dfCopy)
                if plotSmallMultiplesKey not in chartDict or not chartDict[plotSmallMultiplesKey] or numberOfMetrics ==1:   
                    fig,height,width,numberOfCols,numberOfRows=setup_fig_for_horizontal_waterfall_charts(repeatArrayToPlot,chosenDimension,chartDict,plotWithPins)   
                df,paramDict=prepare_data_for_horizontal_waterfall_plot(df,chosenDimension,metric,paramDict,chartDict)
                fig,chartDict=add_annotations_to_horizontal_waterfall_plot(fig,df,metric,colorDict,chartDict,paramDict,countRows,countCols,plotWithPins)
                count,countRows,countCols,chartDict=reset_row_and_column_counters(count,countCols,countRows,numberOfCols,numberOfRows,chartDict)
                fig.update_annotations(font=dict(size=fontSize,family=font))
                if plotSmallMultiplesKey not in chartDict or not chartDict[plotSmallMultiplesKey]:
                    title,paramDict,chartDict=make_horizontal_waterfall_chart_title(df,chosenChart,paramDict,"",metric,chartDict,pyName,acName)                    
                    fig=adjust_horizontal_waterfall_plot(fig,df,key,metric,title,height,width,paramDict,chartDict,plotWithPins)
                    df1=duplicate_dataframe(df)
                    df1=prepare_horizontal_waterfall_data_for_openAi(df1,chartDict)
                    paramDict=set_up_tab_for_show_or_download_chart(df1,fig,configPlotlyDict,chartDict,title,False,None,chosenDimension,paramDict)
      if plotSmallMultiplesKey in chartDict and chartDict[plotSmallMultiplesKey]: 
        key=chosenDimension                 
        title,paramDict,chartDict=make_horizontal_waterfall_chart_title(df,chosenChart,paramDict,key,metric,chartDict,pyName,acName)           
        fig=adjust_horizontal_waterfall_plot(fig,df,key,metric,title,height,width,paramDict,chartDict,plotWithPins)
        if chosenDimension in columns and len(exportDataArray) > 1:
            df1 = pl.concat(exportDataArray)
        else:
            df1=duplicate_dataframe(df)
            df1=prepare_horizontal_waterfall_data_for_openAi(df1,chartDict)            
        paramDict=set_up_tab_for_show_or_download_chart(df1,fig,configPlotlyDict,chartDict,title,False,None,chosenDimension,paramDict)           
    return paramDict


def draw_vertical_waterfall_chart(dfCopy,colorDict,paramDict,chartDict,run):
    """Plot a vertical waterfall chart.

    Internally we use ``df.height`` when the number of rows is needed.
    """
    namingParams=get_naming_params()
    configParams=get_config_params()
    varianceAggregationParams=get_variance_aggregation_params()
    cogsAggregationArray=varianceAggregationParams[namingParams["cogsAggregationArray"]]
    discountsAggregationArray=varianceAggregationParams[namingParams["discountsAggregationArray"]]
    periodsArray=configParams["periodsArray"]
    runVariableDimensionalAnalysis=namingParams["runVariableDimensionalAnalysis"]
    measureName=namingParams["measureName"]
    varianceAmountName=namingParams["varianceAmountName"]
    varianceTypeName=namingParams["varianceTypeName"]
    workColumn=namingParams["workColumn"]
    workColumnTwo=namingParams["workColumnTwo"] 
    showInitialAndFinalValues=namingParams["showInitialAndFinalValues"] 
    processingChoice=namingParams["processingChoice"] 
    verticalWaterfallChart=namingParams["verticalWaterfallChart"] 
    totalVarianceAggregation=namingParams["totalVarianceAggregation"]
    marginVarianceAggregation=namingParams["marginVarianceAggregation"]
    netOfDiscountAggregation=namingParams["netOfDiscountAggregation"]
    varianceAggregation=namingParams["varianceAggregation"]
    priceAndUnitsAggregation=namingParams["priceAndUnitsAggregation"]
    variancePercentChangeName=namingParams["variancePercentChangeName"]   
    marginVariance=namingParams["marginVariance"]  
    drilldownReportRunName=namingParams["drilldownReportRunName"]  
    separatorString=namingParams["separatorString"] 
    amountName=namingParams["monetaryLocalCurrencyName"] 
    marginName=namingParams["marginName"]
    netOfDiscountName=namingParams["netOfDiscountName"] 
    plotSmallMultiples=namingParams["plotSmallMultiplesWaterfall"] 
    varianceInPercent=namingParams["varianceInPercent"]
    shareOfTotalMarket=namingParams["shareOfTotalMarket"]
    runOneDimensionalAnalysis=namingParams["runOneDimensionalAnalysis"] 
    metConditionValue=namingParams["metConditionValue"] 
    notMetConditionValue=namingParams["notMetConditionValue"]  
    mainDimension=namingParams["mainDimension"]
    shareOfTotalMarket=namingParams["shareOfTotalMarket"]
    deltaName=namingParams["deltaName"] 
    labelName=namingParams["labelName"] 
    df=duplicate_dataframe(dfCopy)       
    numberFormat,varianceSum=get_waterfall_number_format(df,run) 
    numberOfRows=1
    numberOfCols=1
    addTable=False
    showItems=[""]
    specs=[
           [{"type": "waterfall"}],
           ]
    columnWidths=[1] 
    orientation="h"
    showPercent=notMetConditionValue 
    if chartDict[varianceInPercent]:
        showPercent=notMetConditionValue
    elif chartDict[shareOfTotalMarket]:
        showPercent=notMetConditionValue
    elif plotSmallMultiples in chartDict and chartDict[plotSmallMultiples]:
        showPercent=notMetConditionValue 
    elif chartDict[processingChoice] in [runOneDimensionalAnalysis] and chartDict[varianceAggregation] in [totalVarianceAggregation,netOfDiscountAggregation,marginVarianceAggregation] and mainDimension in chartDict:   
        showPercent=metConditionValue   
    elif chartDict[processingChoice] in [runVariableDimensionalAnalysis] and chartDict[varianceAggregation] in [totalVarianceAggregation,netOfDiscountAggregation,marginVarianceAggregation]:   
        showPercent=metConditionValue  
    if showPercent:  
        df=create_color_column(df,None,None,verticalWaterfallChart,paramDict,chartDict)  
        specs=[
               [{"type": "waterfall"},{}],
               ]
        columnWidths=[.75,.25]   
        numberOfCols=2
        showItems=["",deltaName+"%"]
    if addTable:
        numberOfRows=2
        specs=[
           [{"type": "waterfall"}],
           [{"type": "table"}],
           ]         
    colorSequenceArray,lineWidth=get_color_sequence(df,paramDict,chartDict) 
    fig = make_subplots(
            rows=numberOfRows, 
            cols=numberOfCols,
            shared_xaxes=True,
            horizontal_spacing=0.2,
            specs=specs,
            column_widths=columnWidths,
            subplot_titles=showItems
            )                     
    df,chartDict=add_sign_to_labels(df,verticalWaterfallChart,workColumnTwo,1,False,chartDict) 
    fig.add_trace(go.Waterfall(
        orientation = orientation, 
        measure = df[measureName],
        y =df[workColumn],
        x = df[varianceAmountName],
        textinfo="text",
        text =df[labelName],
        decreasing = {"marker":{"color":colorDict["redColor"]}},
        increasing = {"marker":{"color":colorDict["greenColor"]}},
        totals = {"marker":{"color":colorSequenceArray[1]}},#colorDict["greyColor"]}},
        connector = {"mode":"between", "line":{"width":1, "color":"rgb(169,169,169)", "dash":"solid"}},
        textposition = "outside",
        cliponaxis = False,
     ),
    row=1, col=1)  
    initialAndFinalValuesCanBeShown=True
    if chartDict[varianceAggregation] not in [totalVarianceAggregation,netOfDiscountAggregation,marginVarianceAggregation] and drilldownReportRunName in run:
        initialAndFinalValuesCanBeShown=False         
    if not chartDict[varianceInPercent]:
        if showInitialAndFinalValues in chartDict and chartDict[showInitialAndFinalValues] and initialAndFinalValuesCanBeShown:
            columns,schema=get_schema_and_column_names(df) 
            if chartDict[varianceAggregation] in cogsAggregationArray:   
                periodZeroValue=marginName+separatorString+periodsArray[0]
                periodOneValue=marginName+separatorString+periodsArray[1]   
            elif chartDict[varianceAggregation] in discountsAggregationArray:  
                periodZeroValue=netOfDiscountName+separatorString+periodsArray[0]
                periodOneValue=netOfDiscountName+separatorString+periodsArray[1] 
            else:
                periodZeroValue=amountName+separatorString+periodsArray[0]
                periodOneValue=amountName+separatorString+periodsArray[1] 
            periodOrder=[periodZeroValue,periodOneValue] 
            if periodZeroValue in columns and periodOneValue in columns:
                last_idx = pl.len() - 1
                df = (
                    df.with_row_index("_idx")
                    .with_columns(
                        pl.when((pl.col("_idx") == 0) | (pl.col("_idx") == last_idx))
                        .then(pl.lit(None))
                        .otherwise(pl.col(periodZeroValue))
                        .alias(periodZeroValue),
                        pl.when((pl.col("_idx") == 0) | (pl.col("_idx") == last_idx))
                        .then(pl.lit(None))
                        .otherwise(pl.col(periodOneValue))
                        .alias(periodOneValue),
                    )
                    .drop("_idx")
                )
            showAbsoluteValueBars=True
            if (shareOfTotalMarket in chartDict and chartDict[shareOfTotalMarket]) or (varianceInPercent in chartDict and chartDict[varianceInPercent]):        
                showAbsoluteValueBars=False    
            if showAbsoluteValueBars and periodZeroValue in columns:
                pass
                fig=add_absolute_value_bars_to_vertical_waterfall(fig,df,workColumn,periodOrder,lineWidth,colorSequenceArray,paramDict,chartDict)
        anchosPercent = [0.48/5] * get_row_count(df)
        if drilldownReportRunName in run:
            anchosPercent = [0.48/5] * get_row_count(df)
        colorChoice=get_color_choice(chartDict)
        if showPercent:
            if chartDict[processingChoice] in [runOneDimensionalAnalysis]:
                anchosPercent=[0.48/10] * get_row_count(df)
            df, largestArray, smallestArray, myDict = get_pinhead_outliers(df, chartDict)
            df = ensure_polars_df(df)
            fig = add_percent_change_markers_to_bar(fig, df, workColumn, colorChoice, anchosPercent, 2)
            fig = add_positive_outlier_pins_to_bar(fig, df, largestArray, colorDict, 2)
            fig = add_negative_outlier_pins_to_bar(fig, df, smallestArray, colorDict, 2)
        fig.update_yaxes(
                                   showticklabels=False, 
                                   zeroline= False, 
                                   visible= False,
                                   ticks= '',
                                   rangemode="tozero",
                                   col=2
                                       )
    else:
        pass
    return fig,numberFormat,chartDict

def add_label_to_horizontal_waterflow(fig,col):
    namingParams=get_naming_params()
    deltaName=namingParams["deltaName"]
    align="center"
    yShift=10 
    yref="paper"
    y=0         
    xref="x"       
    x=0
    ax=x 
    xShift=-22 
    fig.add_annotation(
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
            row=1,col=col,
                       )
    return fig


def add_absolute_value_bars_to_vertical_waterfall(fig,df,column,periodOrder,lineWidth,colorSequenceArray,paramDict,chartDict):
    namingParams=get_naming_params() 
    fcName=namingParams["fcName"]   
    workColumn=namingParams["workColumn"] 
    labelName=namingParams["labelName"]   
    #texttemplate=" %{customdata:,.3s}"
    #hovertemplate=' %{customdata:,.3s}
    constant=24 
    offset=-0.2 
    anchos = [0.68] * get_row_count(df) 
    colorDict=get_color_dictionary(chartDict)
    columns,schema=get_schema_and_column_names(df)   
    if fcName in columns and workColumn in columns:
        customdataActual=df[workColumn]
        hovertemplate=""
        df,myDict=millify_dataframe(df,workColumn,None,labelName,chartDict)
    else: 
        customdataActual=df[periodOrder[1]]  
        hovertemplate=' %{customdata:,.3s}'
        df,myDict=millify_dataframe(df,periodOrder[1],None,labelName,chartDict)    
    fig.add_trace(go.Bar(
                            y = df[column], 
                            x = df[periodOrder[0]],
                            marker=dict(
                            color=colorSequenceArray[0],
                            line=dict(color=colorDict["lightGreyColor"], width=lineWidth)
                                        ),
                            customdata=df[periodOrder[0]],
                            hovertext=df[periodOrder[0]],
                            width = anchos,
                            name = periodOrder[0],           
                            orientation='h',
                            showlegend=False,
                                 ),
                            row=1, col=1
                                 )
    fig.add_trace(go.Bar(
                            y = df[column],
                            x = df[periodOrder[1]],
                            marker_color=colorSequenceArray[1],
                            offset = offset,
                            text=df[labelName],
                            hovertext=df[labelName],
                            textposition='outside',                          
                            width = anchos,
                            name = periodOrder[1],
                            cliponaxis=False,
                            showlegend=False,
                            orientation='h',
                                 ),
                                 row=1, col=1
                                 )
    return fig
