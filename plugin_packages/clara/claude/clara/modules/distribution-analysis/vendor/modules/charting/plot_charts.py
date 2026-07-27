# fmt: off
import copy
import logging
import math

import numpy as np
import plotly.graph_objects as go
import polars as pl
from plotly.subplots import make_subplots

from modules.charting.adjust_position import move_labels_up
from modules.charting.chart_helpers import (
    exclude_outliers_from_chart,
    make_one_dimensional_variance_subplots,
    set_up_tab_for_show_or_download_chart,
)
from modules.charting.chart_primitives import (
    add_message_as_annotation,
    add_title_as_annotation,
    assign_same_colors_to_all_charts,
    change_array_of_metrics_if_cost_analysis,
    change_metric_if_cost_analysis,
    enable_draw_shapes,
    get_color_array,
    get_color_choice,
    get_color_dictionary,
    get_color_sequence,
    get_user_message,
    insert_highlight_color,
    preparare_parameters_for_each_variance_calculation,
    set_other_color_to_grey,
    track_used_colors,
)
from modules.charting.draw_bubble import (
    color_other_bubbles_in_grey,
    draw_bubble_chart,
    draw_motion_chart,
    get_colors_for_bubble,
)
from modules.charting.draw_charts_utils import (
    check_small_multiples_total,
    get_chart_scale,
    get_polars_value_at_index,
    keep_same_scale_for_all_plots,
)
from modules.charting.draw_distribution import (
    draw_boxplot_chart,
    draw_ecdf_chart,
    draw_histogram_chart,
    draw_kernel_density_chart,
    draw_stripplot_chart,
)
from modules.charting.draw_multitier import (
    draw_multitier_bar_chart,
    draw_multitier_column_chart,
)
from modules.charting.draw_other_charts import (
    draw_actual_vs_previous_year_chart,
    draw_alternative_combination_chart_plotly,
    draw_area_chart,
)
from modules.charting.draw_pareto import draw_pareto_chart
from modules.charting.draw_scatter import (
    draw_scatter_chart,
    draw_scatter_chart_datashader,
)
from modules.charting.draw_timeline import (
    draw_dot_chart,
    draw_slope_chart,
    draw_timeline_chart,
)
from modules.charting.draw_waterfall import (
    color_first_bar_vertical,
    draw_horizontal_waterfall_chart,
    draw_vertical_waterfall_chart,
)
from modules.utilities.ui_notifier import ui

# Module logger
logger = logging.getLogger(__name__)
from modules.charting.draw_width_and_stacked_plots import (
    adjust_stacked_column_plot,
    draw_mekko_chart,
    draw_stacked_bar_chart,
    draw_stacked_column_chart,
    stacked_bar_width_plot,
)
from modules.charting.make_titles import (
    make_alternative_combinations_charts_title,
    make_bubble_or_motion_chart_title,
    make_distribution_charts_title,
    make_slope_and_dot_chart_title,
    make_stacked_column_chart_title,
    make_stacked_pareto_and_pareto_chart_title,
    make_timeline_and_area_charts_title,
    make_vertical_waterfall_chart_title,
)
from modules.charting.plotting_utilities import (
    aggregate_syn_plot_data,
    calculate_actual_vs_previous_year_index_change,
    calculate_metrics_for_data_column,
    check_if_negative_bubble_size_values,
    check_if_two_periods_in_distribution_chart,
    delete_black_vertical_lines,
    extract_values_from_dictionary,
    get_mins_and_maxes,
    get_pareto_axis,
    join_metric_dataframes,
    make_df_counts_unique_values,
    make_df_for_pareto_classes,
    make_df_for_pareto_items,
    make_dic_to_add_annotation,
    make_dic_to_add_line,
    make_dic_to_color_first_bar,
    make_integer_date_dict,
    make_syn_plot_comment_dataset,
    purge_other_runs_from_chartdict,
    reverse_waterfall_y_range,
    set_axes_to_log,
    set_number_of_cols_for_bubble_and_scatter_chart,
    tag_if_increasing_or_decreasing,
)
from modules.charting.polars_helpers import n_unique_lazy
from modules.charting.prepare_charts import (
    add_total_variance_arrow_vertical,
    add_totals_column,
    compute_share_of_total,
    group_by_dataset_for_bubble_plot,
    group_by_dataset_for_marimekko_and_barmekko,
    group_by_dataset_for_scatter_plot,
    group_by_dataset_for_stacked_bar,
    prepare_dataframe_for_total_bubble_colored,
    resample_dates,
)
from modules.charting.setup_fig import add_by_to_syn_plot_col_labels
from modules.charting.update_layouts import (
    update_alternative_combination_chart_layout,
    update_area_chart_layout,
    update_boxplot_layout,
    update_bubble_chart_layout,
    update_dot_chart_layout,
    update_ecdf_layout,
    update_histogram_layout,
    update_kernel_density_layout,
    update_pareto_layout_and_get_messages,
    update_scatter_chart_layout,
    update_stripplot_layout,
    update_waterfall_layout_one_dimension,
    update_waterfall_layout_small_multiples,
    update_waterfall_layout_variable_dimension,
)
from modules.data.common_data_utils import (
    add_missing_elements,
    check_value_column_exist,
    drop_AC_and_PY_month,
    drop_columns_with_all_blancs,
    get_growth_rate,
    get_number_of_multiples,
    get_number_of_uniques,
    insert_unit_and_volume_price_column,
    join_unique_metric_to_df,
    make_filtered_small_multiple_dataframe,
    multiply_percent_metrics_by_hundred,
    rank_others_as_last,
    show_only_largest,
    sort_small_multiples,
)
from modules.data.misc_charts_data_prep import (
    aggregate_values_in_distribution_plots,
    prepare_data_for_pareto,
    prepare_sum_dataframe_for_bubble_plot,
)
from modules.data.multidimensional_charts_prep import prepare_data_for_syn_plot
from modules.data.waterfall_data_prep import prepare_data_for_waterfall
from modules.layout.memoization import check_collect
from modules.llm.prompt_helpers import clean_df_for_prompt
from modules.utilities.config import (
    get_config_params,
    get_metric_array_params,
    get_naming_params,
)
from modules.utilities.error_messages import (
    add_empty_dataset_error_message_in_plot_charts_tab,
    add_error_message_in_plot_charts_tab,
    add_warning_message_in_plot_charts_tab,
)
from modules.utilities.helpers import (
    add_price_to_value_cols,
    change_column_names_if_cost_analysis,
    check_if_periods_in_columns,
    duplicate_dataframe,
    get_periods_array,
    place_other_rank_at_end,
    process_if_promo_data,
    unique,
)
from modules.utilities.utils import (
    ensure_lazyframe,
    get_schema_and_column_names,
    is_valid_lazyframe,
    transpose_chart_frame,
    unique_values_lazy,
)

try:  # pragma: no cover - optional dependency during testing
    from modules.utilities.utils import get_uniform_text_min_size
except Exception as e:  # pragma: no cover - fallback if missing
    logging.exception(e)
    ui.error(
        "Something went wrong while importing get_uniform_text_min_size."
    )

    def get_uniform_text_min_size(config_params: dict, naming_params: dict) -> int:
        """Return uniform text minimum size from configuration."""
        key = naming_params["uniformTextMinSize"]
        return int(config_params[key])
from modules.variance.index_handling import process_and_prepare_multidimensional_data
from modules.variance.variance_orchestrator import (
    process_variance_calculation,
    set_up_different_variance_calculations_chart,
)
from modules.variance.variance_utils import (
    group_by_and_sort_data_for_variance_calculation,
)


def plot_histogram_charts(dfCopy,indexCols,valueCols,chartDict,dateChoice,paramDict):
    """
    plots histogram charts
    """
    namingParams=get_naming_params()
    configParams=get_config_params()
    histogramChart=namingParams["histogramChart"]    
    nothingFilteredName=namingParams["nothingFilteredName"]
    entireDatasetName=namingParams["entireDatasetName"]
    rowToPlot=namingParams["rowToPlotName"]
    periodName=namingParams["periodName"]
    numberOfTop=namingParams["numberOfTop"]
    rowToPlot=chartDict[namingParams["rowToPlotName"]]
    smallMultiplesColumn=chartDict[namingParams["smallMultiplesColumn"]]  
    xAxisMetric=namingParams["xAxisMetric"]
    chosenChart=namingParams["chosenChart"]
    smallMultiplesCharts=namingParams["plotSmallMultiplesOtherCharts"]
    metConditionValue=namingParams["metConditionValue"]
    numberOfPlottedSmallMultiplesKey=namingParams["numberOfPlottedSmallMultiples"]   
    chosenChart=chartDict[chosenChart] 
    configPlotlyDict=configParams["configPlotlyDict"]
    configPlotlyDict=configPlotlyDict[histogramChart]      
    indexColsToPlot=copy.deepcopy(indexCols)                              
    if chartDict[namingParams["smallMultiplesColumn"]]:
      indexColsToPlot=[chartDict[namingParams["smallMultiplesColumn"]]]
    indexColsToPlot.insert(0,nothingFilteredName)
    if is_valid_lazyframe(dfCopy):
      for element in indexColsToPlot:
            df=duplicate_dataframe(dfCopy)      
            metric=chartDict[xAxisMetric] 
            if element == nothingFilteredName:
                if hasattr(st, "markdown"):
                    ui.markdown("---")
                colChoice=False
                uniqueItems=[]
            else:      
                df,uniqueItems,aggregateOtherItemsName,valueCols=show_only_largest(df,element,None,periodName,valueCols,chartDict,paramDict,"X")
                numberOfUniques=len(uniqueItems) 
                colChoice=True       
            if metric and element == nothingFilteredName or numberOfUniques > 1:
                if len(uniqueItems)>1:
                    chartDict[smallMultiplesCharts]=metConditionValue
                    chartDict[numberOfPlottedSmallMultiplesKey]=len(uniqueItems)
                df = ensure_lazyframe(
                    aggregate_values_in_distribution_plots(
                        df, element, valueCols, chartDict
                    )
                )
                fig, numberOfItemsInCol, cleanedPeriodOrder, dfExport = draw_histogram_chart(
                    df,
                    element,
                    metric,
                    colChoice,
                    paramDict,
                    chartDict,
                    uniqueItems,
                )
                period0,period1=check_if_two_periods_in_distribution_chart(cleanedPeriodOrder)
                title,paramDict,chartDict=make_distribution_charts_title(df,chosenChart,paramDict,element,metric,chartDict,period0,period1)                 
                fig=update_histogram_layout(fig,numberOfItemsInCol)
                fig,message=get_user_message(fig,histogramChart,"",element,paramDict,chartDict,df,None,None,)
                fig=add_message_as_annotation(fig,message,None,chosenChart,chartDict,paramDict)
                fig=add_title_as_annotation(fig,title,chosenChart,chartDict)
                fig=enable_draw_shapes(fig)                
                paramDict=set_up_tab_for_show_or_download_chart(dfExport,fig,configPlotlyDict,chartDict,element+metric,False,None,element,paramDict)           
    else:
      paramDict=add_empty_dataset_error_message_in_plot_charts_tab(paramDict)
    return paramDict                             

def plot_ecdf_charts(dfCopy,indexCols,valueCols,chartDict,dateChoice,paramDict):
    """
    plots histogram charts
    """
    namingParams=get_naming_params()
    configParams=get_config_params()
    ecdfChart=namingParams["ecdfChart"]
    nothingFilteredName=namingParams["nothingFilteredName"]
    entireDatasetName=namingParams["entireDatasetName"]
    rowToPlot=namingParams["rowToPlotName"]
    periodName=namingParams["periodName"]
    numberOfTop=namingParams["numberOfTop"]
    rowToPlot=chartDict[namingParams["rowToPlotName"]]
    smallMultiplesColumn=chartDict[namingParams["smallMultiplesColumn"]]  
    xAxisMetric=namingParams["xAxisMetric"]
    chosenChart=namingParams["chosenChart"]
    smallMultiplesCharts=namingParams["plotSmallMultiplesOtherCharts"]
    metConditionValue=namingParams["metConditionValue"]
    numberOfPlottedSmallMultiplesKey=namingParams["numberOfPlottedSmallMultiples"]   
    chosenChart=chartDict[chosenChart] 
    configPlotlyDict=configParams["configPlotlyDict"]
    configPlotlyDict=configPlotlyDict[ecdfChart]      
    indexColsToPlot=copy.deepcopy(indexCols)                              
    if chartDict[namingParams["smallMultiplesColumn"]]:
      indexColsToPlot=[chartDict[namingParams["smallMultiplesColumn"]]]
    indexColsToPlot.insert(0,nothingFilteredName)
    if is_valid_lazyframe(dfCopy):
      for element in indexColsToPlot:
            df=duplicate_dataframe(dfCopy)      
            metric=chartDict[xAxisMetric] 
            if element == nothingFilteredName:
                ui.markdown("---")
                colChoice=False
                uniqueItems=[]
            else:      
                df,uniqueItems,aggregateOtherItemsName,valueCols=show_only_largest(df,element,None,periodName,valueCols,chartDict,paramDict,"X")
                numberOfUniques=len(uniqueItems) 
                colChoice=True    
            if metric and element == nothingFilteredName or numberOfUniques > 1: 
                if len(uniqueItems)>1:
                    chartDict[smallMultiplesCharts]=metConditionValue
                    chartDict[numberOfPlottedSmallMultiplesKey]=len(uniqueItems)
                df=aggregate_values_in_distribution_plots(df,element,valueCols,chartDict)
                fig,numberOfItemsInCol,cleanedPeriodOrder,dfExport=draw_ecdf_chart(df,element,metric,colChoice,paramDict,chartDict,uniqueItems)
                period0,period1=check_if_two_periods_in_distribution_chart(cleanedPeriodOrder)            
                title,paramDict,chartDict=make_distribution_charts_title(df,chosenChart,paramDict,element,metric,chartDict,period0,period1)   
                fig=update_ecdf_layout(fig,numberOfItemsInCol)
                fig,message=get_user_message(fig,ecdfChart,"",element,paramDict,chartDict,df,None,None)
                fig=add_message_as_annotation(fig,message,None,chosenChart,chartDict,paramDict)
                fig=add_title_as_annotation(fig,title,chosenChart,chartDict)
                fig=enable_draw_shapes(fig)                
                paramDict=set_up_tab_for_show_or_download_chart(dfExport,fig,configPlotlyDict,chartDict,element+metric,False,None,element,paramDict)                  
    else:
      paramDict=add_empty_dataset_error_message_in_plot_charts_tab(paramDict)
    return paramDict     

def plot_timeline_charts(dfCopy,indexCols,valueCols,chartDict,valueColsWithPrice,xColumn,paramDict,dfDict):
    """
    plots by period chart
    """ 
    namingParams=get_naming_params()
    configParams=get_config_params()
    plotValuesAsChoice=namingParams["plotValuesAsChoice"]
    absolute=namingParams["absolute"]
    percentOfResultRow=namingParams["percentOfResultRow"]
    dateName=namingParams["dateName"]
    periodName=namingParams["periodName"]  
    totalName=namingParams["totalName"]
    rowToPlot=namingParams["rowToPlotName"]
    yAxisMetric=namingParams["yAxisMetric"]     
    filterDates=namingParams["filterDates"]
    metricsToPlot=namingParams["metricsToPlot"]
    numberOfTop=namingParams["numberOfTop"]
    chosenChart=namingParams["chosenChart"]
    timelineChart=namingParams["timelineChart"]
    notMetConditionValue=namingParams["notMetConditionValue"]
    metConditionValue=namingParams["metConditionValue"]
    selectDimensionsToPlot=namingParams["selectDimensionsToPlot"]
    smallMultiplesCharts=namingParams["plotSmallMultiplesOtherCharts"]
    metConditionValue=namingParams["metConditionValue"]
    numberOfPlottedSmallMultiplesKey=namingParams["numberOfPlottedSmallMultiples"]     
    columnsToPlot=chartDict[selectDimensionsToPlot]
    chosenChart=chartDict[chosenChart]      
    rowToPlot=chartDict[rowToPlot]
    metricsToPlot=chartDict[metricsToPlot]
    configPlotlyDict=configParams["configPlotlyDict"]
    configPlotlyDict=configPlotlyDict[timelineChart]
    count=0
    if is_valid_lazyframe(dfCopy):  
      ui.markdown("---")    
      dfCopy,indexCols=add_totals_column(dfCopy,indexCols)
      columnsToPlot.insert(0,totalName)
      fullFig=False
      metricType=False
      for column in columnsToPlot:
        if column == totalName:
            chartDict[selectDimensionsToPlot]=[totalName] 
        else:
            chartDict[selectDimensionsToPlot]=columnsToPlot      
        timeColumn=dateName    
        if column in indexCols:
            df=duplicate_dataframe(dfCopy)
            group_byCols=[column,xColumn]
            if filterDates in chartDict and chartDict[filterDates]:
                  group_byCols=[column,xColumn,periodName]                 
            df=resample_dates(df,xColumn,column,valueCols,chartDict,"sum",paramDict)  
            dfCounts,chartDict=get_number_of_uniques(df,column,timeColumn,chartDict)
            valueCols=check_value_column_exist(df,valueCols)
            df = (
                    df
                    .group_by(group_byCols)          # group_by columns
                    .agg([pl.col(col).sum() for col in valueCols])  # aggregate
                        ) 
            numberOfItemsInCol = n_unique_lazy(column, df)
            if numberOfItemsInCol > 1 or column==totalName:                   
                df,uniqueItems,aggregateOtherItemsName,valueCols=show_only_largest(df,column,None,timeColumn,valueCols,chartDict,paramDict,"X")  
                if numberOfItemsInCol>1:
                    chartDict[numberOfPlottedSmallMultiplesKey]=len(uniqueItems)                  
                df=join_unique_metric_to_df(df,dfCounts,column,timeColumn,aggregateOtherItemsName,chartDict)
                df=insert_unit_and_volume_price_column(df)
                df,paramDict,valueColsWithPrice=process_if_promo_data(df,paramDict,valueColsWithPrice)
                if plotValuesAsChoice in chartDict and chartDict[plotValuesAsChoice] != absolute:
                    df=compute_share_of_total(df,xColumn,column,valueCols,chartDict,dfDict,"mean",paramDict)
                if column==totalName:
                    fullFig,metricType,paramDict=draw_timeline_chart(df,column,metricsToPlot,metricsToPlot,paramDict,chartDict,uniqueItems,aggregateOtherItemsName,fullFig,metricType)
                else:
                    fullFig,metricType,paramDict=draw_timeline_chart(df,column,[metricsToPlot[0]],uniqueItems,paramDict,chartDict,uniqueItems,aggregateOtherItemsName,fullFig,metricType)   
                count=count+1                                                        
      if count==0:                                                           
            paramDict=add_empty_dataset_error_message_in_plot_charts_tab(paramDict)
    else:
      paramDict=add_empty_dataset_error_message_in_plot_charts_tab(paramDict)
    return paramDict





def plot_actual_vs_previous_year_charts(dfCopy,indexCols,valueCols,chartDict,valueColsWithPrice,paramDict,dfDict):
    """
    plots this year vs year ago charts
    """ 
    namingParams=get_naming_params()
    plotValuesAsChoice=namingParams["plotValuesAsChoice"]
    absolute=namingParams["absolute"]
    index=namingParams["index"]
    percentOfResultRow=namingParams["percentOfResultRow"]
    periodName=namingParams["periodName"]  
    totalName=namingParams["totalName"]
    acpyName=namingParams["acpyName"]
    plotTitleText=namingParams["plotTitleText"]
    rowToPlot=chartDict[namingParams["rowToPlotName"]]
    metricsToPlot=namingParams["metricsToPlot"]
    chartSubType=namingParams["chartSubType"]
    numberOfTop=namingParams["numberOfTop"]
    acName=namingParams["acName"] 
    plName=namingParams["plName"]  
    pyName=namingParams["pyName"]
    chosenChart=namingParams["chosenChart"]
    selectDimensionsToPlot=namingParams["selectDimensionsToPlot"]
    columnsToPlot=chartDict[selectDimensionsToPlot]
    chosenChart=chartDict[chosenChart]    
    metricsToPlot=chartDict[metricsToPlot]
    metric=metricsToPlot[0]
    columns,schema=get_schema_and_column_names(dfCopy)
    if plName in columns:
        pyName=plName
    if is_valid_lazyframe(dfCopy):       
      plottedSomething=False
      valueCols=check_value_column_exist(dfCopy,valueCols)
      df = dfCopy.group_by([periodName, acpyName]).agg(
          [pl.col(col).sum().alias(col) for col in valueCols]
      )
      plottedSomething=True
      df=insert_unit_and_volume_price_column(df)
      df,paramDict,valueColsWithPrice=process_if_promo_data(df,paramDict,valueColsWithPrice)
      if plotValuesAsChoice in chartDict and chartDict[plotValuesAsChoice] != absolute:
            df=compute_share_of_total(df,periodName,None,valueCols,chartDict,dfDict,None,paramDict)  
      if chartSubType in chartDict and chartDict[chartSubType] == index:  
            df=calculate_actual_vs_previous_year_index_change(df,None,valueColsWithPrice,paramDict)      
      paramDict=draw_actual_vs_previous_year_chart(df,None,metricsToPlot,metricsToPlot,paramDict,chartDict)
      if chartSubType in chartDict and chartDict[chartSubType] == index:
            ui.text(index.capitalize()+" - "+rowToPlot.capitalize())                 
      ui.markdown("---")   
      for column in columnsToPlot: 
        if column in columnsToPlot:
            valueCols=check_value_column_exist(dfCopy,valueCols)
            df = dfCopy.group_by([column, periodName, acpyName]).agg(
                [pl.col(col).sum().alias(col) for col in valueCols]
            )
            if isinstance(df, pl.LazyFrame):
                uniqueItems = unique_values_lazy(column, df)
            else:
                uniqueItems = df.get_column(column).unique().to_list()
            numberOfItemsInCol=len(uniqueItems)
            if numberOfItemsInCol > 1 :
                  if not plottedSomething:
                        ui.markdown("---")     
                  plottedSomething=True
                  df,uniqueItems,aggregateOtherItemsName,valueCols=show_only_largest(df,column,None,periodName,valueCols,chartDict,paramDict,"X") 
                  df=insert_unit_and_volume_price_column(df)
                  df,paramDict,valueColsWithPrice=process_if_promo_data(df,paramDict,valueColsWithPrice)
                  if plotValuesAsChoice in chartDict and chartDict[plotValuesAsChoice] != absolute:
                        df=compute_share_of_total(df,periodName,None,valueCols,chartDict,dfDict,None,paramDict)
                  if chartSubType in chartDict and chartDict[chartSubType] == index:  
                        df=calculate_actual_vs_previous_year_index_change(df,column,valueColsWithPrice,paramDict)
                  paramDict=draw_actual_vs_previous_year_chart(df,column,[metricsToPlot[0]],uniqueItems,paramDict,chartDict)
                  if chartSubType in chartDict and chartDict[chartSubType] == index:
                        ui.text(index.capitalize()+" - "+rowToPlot.capitalize()+" - "+metric.capitalize())       
                  ui.markdown("---")          
      if not plottedSomething:
            paramDict=add_empty_dataset_error_message_in_plot_charts_tab(paramDict)  
    else:  
      paramDict=add_empty_dataset_error_message_in_plot_charts_tab(paramDict)
    return paramDict,chartDict

def plot_bubble_charts(dfCopy,indexCols,valueCols,chartDict,timeColumn,paramDict,dfDict):
    """
    prepares data and plots bubble chart
    """ 
    namingParams=get_naming_params()
    configParams=get_config_params()
    font=configParams[namingParams["fontChoice"]] 
    fontSize=configParams[namingParams["fontSizeText"]]
    plotValuesAsChoice=namingParams["plotValuesAsChoice"]
    absolute=namingParams["absolute"]
    totalName=namingParams["totalName"]
    periodName=namingParams["periodName"]
    chosenChart=namingParams["chosenChart"]
    bubbleChart=namingParams["bubbleChart"]
    selectedPeriods=namingParams["selectedPeriods"]
    nothingThereString=namingParams["nothingThereString"]
    xAxisDimension=namingParams["xAxisDimension"]    
    yAxisDimension=namingParams["yAxisDimension"]  
    xAxisMetricKey=namingParams["xAxisMetric"]    
    yAxisMetricKey=namingParams["yAxisMetric"]     
    bubbleSizeKey=namingParams["bubbleSize"]    
    selectDimensionsToPlot=namingParams["selectDimensionsToPlot"]
    nothingFilteredName=namingParams["nothingFilteredName"]
    notMetConditionValue=namingParams["notMetConditionValue"]             
    toPlotPeriod=namingParams["toPlotPeriod"]
    smallMultiplesColumn=namingParams["smallMultiplesColumn"]
    smallMultiplesCharts=namingParams["plotSmallMultiplesOtherCharts"]
    metConditionValue=namingParams["metConditionValue"]
    numberOfPlottedSmallMultiplesKey=namingParams["numberOfPlottedSmallMultiples"] 
    configPlotlyDict=configParams["configPlotlyDict"]
    configPlotlyDict=configPlotlyDict[bubbleChart]
    chosenChart=chartDict[chosenChart]
    smallMultiplesColumn=chartDict[smallMultiplesColumn]
    toPlotPeriod=chartDict[toPlotPeriod]
    periodOrder=chartDict[selectedPeriods]
    chosenDimension=chartDict[xAxisDimension]
    bubbleColorDimension=chartDict[yAxisDimension]
    bubbleSizeDimension=chartDict[bubbleSizeKey]
    xAxisMetric=chartDict[xAxisMetricKey]
    yAxisMetric=chartDict[yAxisMetricKey]
    chartDictCopy=copy.deepcopy(chartDict)
    frameArray=[]
    count=0
    colorDict=get_color_dictionary(chartDict)
    colorArray=get_color_array(colorDict,chartDict)
    if yAxisMetric and xAxisMetric and bubbleSizeDimension and is_valid_lazyframe(dfCopy):
        ui.markdown("---")
        smallMultiplesColumnArray=[smallMultiplesColumn]
        dfCopy,smallMultiplesColumnArray=add_totals_column(dfCopy,smallMultiplesColumnArray)
        for column in smallMultiplesColumnArray:
            chartDict=copy.deepcopy(chartDictCopy)
            df,group_byCols=group_by_dataset_for_bubble_plot(dfCopy,column,smallMultiplesColumnArray,periodName,valueCols,chartDict)    
            if column==totalName:
                numberOfRows,numberOfCols,countRows,countCols,verticalSpacing,horizontalSpacing=1,1,1,1,0,0 
                sharedXaxes,sharedYaxes,subplotTitles="all",None,[]   
                df,uniqueItems,aggregateOtherItemsName,valueCols=show_only_largest(df,chosenDimension,None,periodName,valueCols,chartDict,paramDict,"X")    
            elif column!=totalName:
                dfDump,smallMultipleUniqueItems,smallMultipleAggregateOtherItemsName,valueCols=show_only_largest(df,smallMultiplesColumn,None,periodName,valueCols,chartDict,paramDict,"Y")     
                df1,xuniqueItems,xaggregateOtherItemsName,xvalueCols=show_only_largest(df,chosenDimension,smallMultiplesColumn,periodName,valueCols,chartDict,paramDict,"X")    
                if xaggregateOtherItemsName in xuniqueItems:
                    df=copy.deepcopy(df1)
                numberOfCols=set_number_of_cols_for_bubble_and_scatter_chart(smallMultipleUniqueItems)  
                numberOfRows=int(math.ceil(len(smallMultipleUniqueItems)/numberOfCols))
                verticalSpacing,horizontalSpacing,sharedXaxes,sharedYaxes,subplotTitles=0.08,0.07,"all","all",smallMultipleUniqueItems   
                countRows,countCols=1,1
            showLegend=True
            if column in [totalName] and bubbleColorDimension not in  [nothingFilteredName,False,notMetConditionValue]:
                df=prepare_dataframe_for_total_bubble_colored(df,dfCopy,chartDict,chosenDimension,bubbleColorDimension)
            elif column in [totalName] and bubbleColorDimension in  [nothingFilteredName,False,notMetConditionValue]: 
                pass 
            elif column not in [totalName] and bubbleColorDimension not in  [nothingFilteredName,False,notMetConditionValue]:
                df=prepare_dataframe_for_total_bubble_colored(df,dfCopy,chartDict,chosenDimension,bubbleColorDimension)
            else:
                showLegend=False
                chartDict[yAxisDimension]=None 
            df=insert_unit_and_volume_price_column(df)
            df=get_growth_rate(df,chosenDimension,periodOrder,paramDict,chartDict,False)
            df,paramDict,valueColsWithPrice=process_if_promo_data(df,paramDict,valueCols)
            df=multiply_percent_metrics_by_hundred(df)
            if plotValuesAsChoice in chartDict and chartDict[plotValuesAsChoice] != absolute:
                df = compute_share_of_total(
                    df, timeColumn, None, valueCols, chartDict, dfDict, None, paramDict
                )
                dfSum = pl.DataFrame()
            else:
                dfSum=prepare_sum_dataframe_for_bubble_plot(dfCopy,valueCols,periodOrder,toPlotPeriod,chartDict,paramDict)             
            fig=make_subplots(
                    rows=numberOfRows, 
                    cols=numberOfCols,
                    shared_xaxes=sharedXaxes,
                    shared_yaxes=sharedYaxes,
                    vertical_spacing=verticalSpacing,
                    horizontal_spacing=horizontalSpacing,
                    subplot_titles=subplotTitles,
                                  )                  
            if column==totalName:
                df,toPlotPeriod=check_if_periods_in_columns(df,toPlotPeriod)
                df = df.filter(pl.col(periodName) == toPlotPeriod)
                df = df.filter(pl.col(chosenDimension) != nothingThereString)
                df,paramDict=check_if_negative_bubble_size_values(df,chartDict,paramDict)
                df=place_other_rank_at_end(df,bubbleColorDimension,uniqueItems,periodOrder) 
                colorArray=color_other_bubbles_in_grey(df,colorArray,bubbleColorDimension,colorDict,chartDict)
                df,colorDimensionArray,plotLegend,colorArray,chartDict=get_colors_for_bubble(fig,df,column,chartDict,None,countCols,countRows,aggregateOtherItemsName,colorArray)
                dfSum=change_column_names_if_cost_analysis(dfSum,chartDict)
                df=change_column_names_if_cost_analysis(df,chartDict)
                bubbleSizeDimension=change_metric_if_cost_analysis(bubbleSizeDimension,chartDict)
                chartDict[xAxisMetricKey]=change_metric_if_cost_analysis(chartDict[xAxisMetricKey],chartDict)
                chartDict[yAxisMetricKey]=change_metric_if_cost_analysis(chartDict[yAxisMetricKey],chartDict)
                chartDict[bubbleSizeKey]=change_metric_if_cost_analysis(chartDict[bubbleSizeKey],chartDict)
                dfTotal=duplicate_dataframe(df)
                fig,sizeRef=draw_bubble_chart(fig,df,colorDimensionArray,plotLegend,chartDict,colorDict,colorArray,dfSum,column,count,countRows,countCols,None)    
                fig.update_annotations(font=dict(size=fontSize,family=font))
                title,paramDict,chartDict=make_bubble_or_motion_chart_title(df,bubbleChart,paramDict,chosenDimension,bubbleSizeDimension,chartDict,toPlotPeriod,column) 
                fig=update_bubble_chart_layout(fig,bubbleChart,chartDict,showLegend,column,numberOfRows)
                fig,message=get_user_message(fig,bubbleChart,toPlotPeriod,None,paramDict,chartDict,df,None,None)
                fig=add_title_as_annotation(fig,title,chosenChart,chartDict)
                fig=add_message_as_annotation(fig,message,None,chosenChart,chartDict,paramDict)
                fig=enable_draw_shapes(fig) 
                chartDict[smallMultiplesCharts]=notMetConditionValue
                paramDict=set_up_tab_for_show_or_download_chart(df,fig,configPlotlyDict,chartDict,chosenDimension+bubbleSizeDimension+toPlotPeriod,False,None,None,paramDict)  
            elif column!=totalName:
                dataArray=[]
                sumDataArray=[]
                plotLegendArray=[]
                dfSmallMultiples = duplicate_dataframe(df)
                dfSmallMultiples = dfSmallMultiples.with_columns(
                    pl.when(~pl.col(smallMultiplesColumn).is_in(smallMultipleUniqueItems))
                    .then(pl.lit(smallMultipleAggregateOtherItemsName))
                    .otherwise(pl.col(smallMultiplesColumn))
                    .alias(smallMultiplesColumn)
                )
                valueCols=check_value_column_exist(dfSmallMultiples,valueCols)
                dfSmallMultiples=dfSmallMultiples.group_by(group_byCols).agg([pl.col(c).sum() for c in valueCols])
                for element in smallMultipleUniqueItems:
                    chartDict=copy.deepcopy(chartDictCopy)
                    chartDict[smallMultiplesCharts]=metConditionValue
                    chartDict[numberOfPlottedSmallMultiplesKey]=len(smallMultipleUniqueItems)
                    dfFiltered = duplicate_dataframe(dfSmallMultiples)
                    dfFiltered = dfFiltered.filter(pl.col(column) == element)
                    if dfFiltered.height > 0:
                        # Rows not found in ``uniqueItems`` are assigned to
                        # ``aggregateOtherItemsName`` using Polars filtering
                        # and joins.
                        
                        valueCols=check_value_column_exist(dfFiltered,valueCols)
                        dfFiltered=dfFiltered.group_by(group_byCols).agg([pl.col(c).sum() for c in valueCols])
                        dfFiltered,paramDict=check_if_negative_bubble_size_values(dfFiltered,chartDict,paramDict)
                        dfFiltered=place_other_rank_at_end(dfFiltered,bubbleColorDimension,uniqueItems,periodOrder)
                        dfFiltered,colorDimensionArray,plotLegend,colorArray,chartDict=get_colors_for_bubble(fig,dfFiltered,column,chartDict,colorDimensionArray,countCols,countRows,aggregateOtherItemsName,colorArray)                         
                        dfFiltered=insert_unit_and_volume_price_column(dfFiltered)
                        dfFiltered=get_growth_rate(dfFiltered,chosenDimension,periodOrder,paramDict,chartDict,False)
                        dfFiltered=multiply_percent_metrics_by_hundred(dfFiltered)
                        if plotValuesAsChoice in chartDict and chartDict[plotValuesAsChoice] != absolute:
                            dfFiltered = compute_share_of_total(
                                dfFiltered,
                                timeColumn,
                                None,
                                valueCols,
                                chartDict,
                                dfDict,
                                None,
                                paramDict,
                            )
                            dfSumFiltered = pl.DataFrame()
                        else:
                            dfSumFiltered=prepare_sum_dataframe_for_bubble_plot(dfFiltered,valueCols,periodOrder,toPlotPeriod,chartDict,paramDict)
                        dfFiltered, toPlotPeriod = check_if_periods_in_columns(dfFiltered, toPlotPeriod)
                        dfFiltered = dfFiltered.filter(pl.col(periodName) == toPlotPeriod)
                        dfFiltered = dfFiltered.filter(pl.col(chosenDimension) != nothingThereString)
                        dfSumFiltered=change_column_names_if_cost_analysis(dfSumFiltered,chartDict)
                        dfFiltered=change_column_names_if_cost_analysis(dfFiltered,chartDict)
                        bubbleSizeDimension=change_metric_if_cost_analysis(bubbleSizeDimension,chartDict)
                        chartDict[xAxisMetricKey]=change_metric_if_cost_analysis(chartDict[xAxisMetricKey],chartDict)
                        chartDict[yAxisMetricKey]=change_metric_if_cost_analysis(chartDict[yAxisMetricKey],chartDict)
                        chartDict[bubbleSizeKey]=change_metric_if_cost_analysis(chartDict[bubbleSizeKey],chartDict)
                        dataArray.append(dfFiltered)
                        sumDataArray.append(dfSumFiltered)
                        plotLegendArray.append(plotLegend)
                        if countCols < numberOfCols:
                            countCols=countCols+1
                        else: 
                            countCols=1     
                            countRows=countRows+1
                        count=count+1 
                chartDict=get_mins_and_maxes(dataArray,chartDict)
                count,countRows,countCols=0,1,1
                for element in smallMultipleUniqueItems:                    
                    dfFiltered=dataArray[count]
                    dfSumFiltered=sumDataArray[count]
                    plotLegend=plotLegendArray[count]
                    # Polars-safe duplication for export/concat purposes
                    dfPlot=duplicate_dataframe(dfFiltered)
                    frameArray.append(dfPlot)               
                    fig,sizeRef=draw_bubble_chart(fig,dfFiltered,colorDimensionArray,plotLegend,chartDict,colorDict,colorArray,dfSumFiltered,column,count,countRows,countCols,sizeRef)    
                    fig.update_annotations(font=dict(size=fontSize,family=font))
                    if countCols < numberOfCols:
                        countCols=countCols+1
                    else: 
                        countCols=1     
                        countRows=countRows+1
                    count=count+1            
                fig=update_bubble_chart_layout(fig,bubbleChart,chartDict,showLegend,column,numberOfRows)
                fig.update_layout(legend_itemsizing="constant")                   
                title,paramDict,chartDict=make_bubble_or_motion_chart_title(df,bubbleChart,paramDict,chosenDimension,bubbleSizeDimension,chartDict,toPlotPeriod,column)            
                fig,message=get_user_message(fig,bubbleChart,toPlotPeriod,column,paramDict,chartDict,df,None,None)
                fig=add_title_as_annotation(fig,title,chosenChart,chartDict)
                fig=add_message_as_annotation(fig,message,None,chosenChart,chartDict,paramDict)
                fig=enable_draw_shapes(fig) 
                df = pl.concat(frameArray)
                check_small_multiples_total(df,dfTotal,None,chartDict)
        paramDict=set_up_tab_for_show_or_download_chart(df,fig,configPlotlyDict,chartDict,chosenDimension+bubbleSizeDimension+toPlotPeriod,False,None,None,paramDict)           
    else:
        ui.warning("unable to plot. Check metrics and dataset")
    return paramDict

def plot_motion_charts(dfCopy,indexCols,valueCols,chartDict,timeColumn,paramDict,dfDict):
    """
    prepares data and plots motion chart
    """ 
    namingParams=get_naming_params()
    configParams=get_config_params()
    plotValuesAsChoice=namingParams["plotValuesAsChoice"]
    resampleDates=namingParams["resampleDates"]
    absolute=namingParams["absolute"]
    dateName=namingParams["dateName"]
    periodName=namingParams["periodName"] 
    numberOfTop=namingParams["numberOfTop"]
    chosenChart=namingParams["chosenChart"]
    motionChart=namingParams["motionChart"]
    selectedPeriods=namingParams["selectedPeriods"]
    nothingThereString=namingParams["nothingThereString"]
    xAxisDimension=namingParams["xAxisDimension"]    
    yAxisDimension=namingParams["yAxisDimension"]  
    bubbleSize=namingParams["bubbleSize"]    
    selectDimensionsToPlot=namingParams["selectDimensionsToPlot"]
    nothingFilteredName=namingParams["nothingFilteredName"]
    notMetConditionValue=namingParams["notMetConditionValue"]
    marginName=namingParams["marginName"]
    marginInPercentName=namingParams["marginInPercentName"]
    marginInPercentOfNetSalesName=namingParams["marginInPercentOfNetSalesName"]
    monetaryLocalCurrencyName=namingParams["monetaryLocalCurrencyName"] 
    netOfDiscountName=namingParams["netOfDiscountName"]           
    acName=namingParams["acName"] 
    otherName=namingParams["otherName"] 
    configPlotlyDict=configParams["configPlotlyDict"]
    configPlotlyDict=configPlotlyDict[motionChart]
    chosenChart=chartDict[chosenChart]
    rowToPlot=chartDict[namingParams["rowToPlotName"]]
    periodOrder=chartDict[selectedPeriods]
    chosenDimension=chartDict[xAxisDimension]
    bubbleColorDimension=chartDict[yAxisDimension]
    bubbleSizeDimension=chartDict[bubbleSize]
    ui.markdown("---")
    plottedSomething=False
    # Prefer Polars-native unique extraction that works for DataFrame/LazyFrame
    uniqueItems = unique_values_lazy(chosenDimension, dfCopy)
    if len(uniqueItems)>1 or not plottedSomething:
        if len(uniqueItems)> 1:
            pass
        else:
            plottedSomething=True    
        group_byCols=[chosenDimension,timeColumn] 
        valueCols=check_value_column_exist(dfCopy,valueCols)   
        df = (
                    dfCopy
                    .group_by(group_byCols)          # group_by columns
                    .agg([pl.col(col).sum() for col in valueCols])  # aggregate
                )        
        df,uniqueItems,aggregateOtherItemsName,valueCols=show_only_largest(df,chosenDimension,None,dateName,valueCols,chartDict,paramDict,"X")  
        df=resample_dates(df,timeColumn,chosenDimension,valueCols,chartDict,"sum",paramDict)
        df = df.with_columns(pl.col(timeColumn).dt.strftime("%b-%Y").alias(timeColumn))
        periods=df.get_column(timeColumn).unique().to_list()
        df = insert_unit_and_volume_price_column(df)
        df,paramDict,valueColsWithPrice=process_if_promo_data(df,paramDict,valueCols)
        orderedDateList,motionChartIntToDateDict,dateToIntDict=make_integer_date_dict(periods)
        df = df.with_columns(pl.col(timeColumn).alias(periodName))
        df = df.with_columns(
            pl.col(periodName)
            .cast(str)
            .replace(dateToIntDict)
            .cast(int)
            .alias(periodName)
        )
        showLegend = True
        if bubbleColorDimension not in [nothingFilteredName, False, notMetConditionValue]:
            colorCols = [chosenDimension, bubbleColorDimension]
            dfColor = (
                dfCopy.select(colorCols)
                .unique(subset=colorCols)
                .sort(chosenDimension)
            )
            df = (
                df.sort(chosenDimension)
                .join(dfColor, on=chosenDimension, how="left")
                .with_columns(pl.col(bubbleColorDimension).fill_null(otherName))
            )
        else:
            showLegend=False
            chartDict[yAxisDimension]=None
        if marginName in valueCols:
            df = df.with_columns(
                pl.when((pl.col(marginName) != 0) & (pl.col(monetaryLocalCurrencyName) != 0))
                .then(pl.col(marginName) / pl.col(monetaryLocalCurrencyName) * 100)
                .otherwise(0)
                .round(0)
                .alias(marginInPercentName)
            )
        if marginName in valueCols and netOfDiscountName in valueCols:
            df = df.with_columns(
                pl.when((pl.col(marginName) != 0) & (pl.col(netOfDiscountName) != 0))
                .then(pl.col(marginName) / pl.col(netOfDiscountName) * 100)
                .otherwise(0)
                .round(0)
                .alias(marginInPercentOfNetSalesName)
            )
        periods=df.get_column(timeColumn).unique().to_list()
        if plotValuesAsChoice in chartDict and chartDict[plotValuesAsChoice] != absolute:
            df=compute_share_of_total(df,timeColumn,None,valueCols,chartDict,dfDict,None,paramDict)                 
        df = df.filter(pl.col(chosenDimension) != nothingThereString)
        df = df.with_row_index("_idx").drop("_idx")
        fig=draw_motion_chart(df,paramDict,periods,chartDict)
        title,paramDict,chartDict=make_bubble_or_motion_chart_title(df,motionChart,paramDict,chosenDimension,bubbleSizeDimension,chartDict,periods,chosenDimension) 
        fig=update_bubble_chart_layout(fig,motionChart,chartDict,showLegend,chosenDimension,1)
        fig,message=get_user_message(fig,motionChart,"",None,paramDict,chartDict,df,None,None)
        fig=add_message_as_annotation(fig,message,None,chosenChart,chartDict,paramDict)
        fig=add_title_as_annotation(fig,title,chosenChart,chartDict)    
        fig=enable_draw_shapes(fig)  
        paramDict=set_up_tab_for_show_or_download_chart(df,fig,configPlotlyDict,chartDict,chosenDimension+bubbleSizeDimension,False,None,None,paramDict)    
    return paramDict

def plot_scatter_charts(dfCopy,indexCols,valueCols,chartDict,valueColsWithPrice,xColumn,paramDict,dfDict):
    """
    prepares data and plots bubble chart
    """ 
    namingParams=get_naming_params()
    configParams=get_config_params()
    datashaderLimit = int(configParams[namingParams["datashaderLimit"]] or 0)
    font=configParams[namingParams["fontChoice"]]
    fontSize=configParams[namingParams["fontSizeText"]]
    webGLLimit = int(configParams[namingParams["webGLLimit"]] or 0)
    plotAsHeatmap=namingParams["plotAsHeatmap"]
    periodName=namingParams["periodName"]
    totalName=namingParams["totalName"]
    smallMultiplesColumn=namingParams["smallMultiplesColumn"]
    smallMultiplesCharts=namingParams["plotSmallMultiplesOtherCharts"]
    metConditionValue=namingParams["metConditionValue"]
    numberOfPlottedSmallMultiplesKey=namingParams["numberOfPlottedSmallMultiples"] 
    yAxisMetricKey=namingParams["yAxisMetric"]     
    xAxisMetricKey=namingParams["xAxisMetric"]  
    xAxisDimension=namingParams["xAxisDimension"] 
    scatterChart=namingParams["scatterChart"] 
    selectedPeriods=namingParams["selectedPeriods"]
    plName=namingParams["plName"]
    pyName=namingParams["pyName"]  
    chosenChart=namingParams["chosenChart"]
    toPlotPeriod=namingParams["toPlotPeriod"]
    subplotTitlesKey=namingParams["subplotTitles"]
    chosenChart=chartDict[chosenChart]   
    periodOrder=chartDict[selectedPeriods] 
    smallMultiplesColumn=chartDict[smallMultiplesColumn]
    yAxisMetric=chartDict[yAxisMetricKey]
    xAxisMetric=chartDict[xAxisMetricKey]
    plotAsHeatmap=chartDict[plotAsHeatmap]
    dotDimension=chartDict[xAxisDimension]
    configPlotlyDict=configParams["configPlotlyDict"]
    configPlotlyDict=configPlotlyDict[scatterChart]   
    numberOfRows,numberOfCols,countRows,countCols,verticalSpacing,horizontalSpacing=1,1,1,1,0,0 
    sharedXaxes,sharedYaxes,subplotTitles="all",None,[]
    chartDictCopy=copy.deepcopy(chartDict)
    frameArray = []
    labelArray = []
    dfLabels = pl.DataFrame()
    if is_valid_lazyframe(dfCopy):
      ui.markdown("---") 
      smallMultiplesColumnArray=[smallMultiplesColumn]
      dfCopy,smallMultiplesColumnArray=add_totals_column(dfCopy,smallMultiplesColumnArray)
      count=0        
      for column in smallMultiplesColumnArray:
        chartDict=copy.deepcopy(chartDictCopy)
        lf, group_byCols = group_by_dataset_for_scatter_plot(
            dfCopy, column, smallMultiplesColumnArray, xColumn, valueCols, chartDict
        )
        numberOfItemsInCol = n_unique_lazy(column, lf) or 0
        if numberOfItemsInCol > 1 or column==totalName:
            numberOfRows,uniqueItems,aggregateOtherItemsName=1,[],""
            if column != totalName:
                lf,uniqueItems,aggregateOtherItemsName,valueCols=show_only_largest(
                    lf,smallMultiplesColumn,None,xColumn,valueCols,chartDict,paramDict,"Y"
                )
                numberOfCols=set_number_of_cols_for_bubble_and_scatter_chart(uniqueItems)
                numberOfRows=int(math.ceil(len(uniqueItems)/numberOfCols))
                verticalSpacing,horizontalSpacing,sharedXaxes,sharedYaxes,subplotTitles=0.07,0.07,"all","all",uniqueItems
                chartDict[subplotTitlesKey]=subplotTitles
            lf=insert_unit_and_volume_price_column(lf)
            lf=get_growth_rate(lf,dotDimension,periodOrder,paramDict,chartDict,False)
            lf = lf.filter(pl.col(periodName) == chartDict[toPlotPeriod])
            lf = exclude_outliers_from_chart(lf, chartDict)
            df = lf.collect()
            df,paramDict,valueColsWithPrice=process_if_promo_data(df,paramDict,valueColsWithPrice)
            df=multiply_percent_metrics_by_hundred(df)
            periodsArray=get_periods_array(df)
            if plName in periodsArray:
                pyName=plName    
            fig = make_subplots(rows=numberOfRows, 
                          cols=numberOfCols,
                          shared_xaxes=sharedXaxes,
                          shared_yaxes=sharedYaxes,
                          vertical_spacing=verticalSpacing,
                          horizontal_spacing=horizontalSpacing,
                          subplot_titles=subplotTitles,
                              ) 
            title,paramDict,chartDict=make_bubble_or_motion_chart_title(df,chosenChart,paramDict,column,yAxisMetric,chartDict,periodsArray,xAxisMetric)
            webGL=False
            chartDict[xAxisMetricKey]=change_metric_if_cost_analysis(chartDict[xAxisMetricKey],chartDict)
            chartDict[yAxisMetricKey]=change_metric_if_cost_analysis(chartDict[yAxisMetricKey],chartDict)
            df=change_column_names_if_cost_analysis(df,chartDict)
            if df.height > datashaderLimit or plotAsHeatmap:
                 chartDict[plotAsHeatmap]=metConditionValue
                 showLegend=False
                 fig=plot_scatter_chart_datashader(fig,df,periodName,column,chartDict,uniqueItems,paramDict,countRows,countCols,numberOfCols,numberOfRows)              
                 fig.update_annotations(font=dict(size=fontSize,family=font))
                 fig=update_scatter_chart_layout(fig,chartDict,column,showLegend,True,numberOfRows)
                 fig=set_axes_to_log(fig,chartDict)
                 fig,message=get_user_message(fig,scatterChart,"",column,paramDict,chartDict,df,None,None)
                 fig=add_message_as_annotation(fig,message,None,chosenChart,chartDict,paramDict)
                 fig=add_title_as_annotation(fig,title,chosenChart,chartDict)
                 fig=enable_draw_shapes(fig) 
            elif column == totalName: 
                if df.height >  webGLLimit:
                    webGL=True
                fig,showLegend,dfLabels=draw_scatter_chart(fig,df,paramDict,periodOrder,uniqueItems,aggregateOtherItemsName,column,chartDict,countRows,countCols,webGL,count)                    
                fig.update_annotations(font=dict(size=fontSize,family=font))
                fig=update_scatter_chart_layout(fig,chartDict,column,showLegend,False,numberOfRows)
                fig=set_axes_to_log(fig,chartDict)
                fig,message=get_user_message(fig,scatterChart,column,column,paramDict,chartDict,df,None,None)
                fig=add_message_as_annotation(fig,message,None,chosenChart,chartDict,paramDict)
                fig=add_title_as_annotation(fig,title,chosenChart,chartDict)
                fig=enable_draw_shapes(fig) 
            else:
                chartDict[smallMultiplesCharts]=metConditionValue
                chartDict[numberOfPlottedSmallMultiplesKey]=len(uniqueItems)
                for element in uniqueItems:
                    dfFiltered = duplicate_dataframe(df)
                    dfFiltered = dfFiltered.filter(pl.col(column) == element)
                    frameArray.append(dfFiltered)
                    if df.height >  webGLLimit:
                        webGL=True
                    fig,showLegend,dfLabels=draw_scatter_chart(fig,dfFiltered,paramDict,periodOrder,uniqueItems,aggregateOtherItemsName,column,chartDict,countRows,countCols,webGL,count)
                    labelArray.append(dfLabels)
                    fig.update_annotations(font=dict(size=fontSize,family=font))
                    if countCols < numberOfCols:
                        countCols=countCols+1
                    else: 
                        countCols=1     
                        countRows=countRows+1
                    count=count+1  
                fig=update_scatter_chart_layout(fig,chartDict,column,showLegend,False,numberOfRows)
                fig=set_axes_to_log(fig,chartDict)    
                fig,message=get_user_message(fig,scatterChart,element,column,paramDict,chartDict,df,None,None)
                fig=add_message_as_annotation(fig,message,None,chosenChart,chartDict,paramDict)
                fig=add_title_as_annotation(fig,title,chosenChart,chartDict)
                fig=enable_draw_shapes(fig)
                if len(frameArray) > 0:
                    dfExport = pl.concat(frameArray)
                    check_small_multiples_total(dfExport,df,None,chartDict)
                if len(labelArray) > 0:
                    dfLabels = pl.concat(labelArray)
            paramDict=set_up_tab_for_show_or_download_chart(dfLabels,fig,configPlotlyDict,chartDict,column+yAxisMetric,False,None,None,paramDict) 
            count=count+1                                                     
      if count==0:
            paramDict=add_empty_dataset_error_message_in_plot_charts_tab(paramDict)
    else: 
      paramDict=add_empty_dataset_error_message_in_plot_charts_tab(paramDict)
    return paramDict 

def plot_one_dimensional_variance_chart_different_calculations(dfDict,indexCols,columnArray,paramDict,chartDict,valueDict):
    namingParams=get_naming_params()
    configParams=get_config_params()
    fontSize=configParams[namingParams["fontSizeText"]]  
    font=configParams[namingParams["fontChoice"]]  
    plotChartsTabKey=namingParams["plotChartsTab"]
    numberOfPlotsKey=namingParams["numberOfPlots"]
    workColumn=namingParams["workColumn"]
    selectedPeriods=namingParams["selectedPeriods"]
    varianceAmountName=namingParams["varianceAmountName"]
    varianceTypeName=namingParams["varianceTypeName"]
    acName=namingParams["acName"] 
    pyName=namingParams["pyName"]  
    plName=namingParams["plName"]
    yearBeforePyName=namingParams["yearBeforePyName"]  
    isYearBeforePy=namingParams["isYearBeforePy"]
    waterfallChart=namingParams["verticalWaterfallChart"]
    monetaryName=namingParams["monetaryLocalCurrencyName"]
    varianceAggregation=namingParams["varianceAggregation"]
    plotSmallMultiples=namingParams["plotSmallMultiplesWaterfall"]
    bridgeSubmit,chartDict,aggregationsToPlot,varianceArray,configPlotlyDict=set_up_different_variance_calculations_chart(columnArray,paramDict,chartDict)
    fig,countRows,countCols,count,numberOfCols,numberOfRows=make_one_dimensional_variance_subplots(aggregationsToPlot,numberOfCols=3)
    mainDimension=None
    sortArray=[]
    shapeArray=[]
    periodZeroLineArray=[]
    periodOneLineArray=[]
    arrowArray=[]
    annotationArrowArray=[]
    annotationTextArray=[]
    numberOfCharts=len(aggregationsToPlot)
    paramDict[numberOfPlotsKey]=numberOfCharts
    frameArray=[] 
    countCalculations=0  
    dfDict={}  
    for element in aggregationsToPlot:
        chartDict[varianceAggregation]=element
        paramDict,df,dfDates,dfPeriods,dfAllPeriods,dfPlan,indexCols,valueCols,xchartDict,toDrop,originalValueCols,colDict,tabDict,automateDict,planPlaybackDict=extract_values_from_dictionary(valueDict)
        dfDict,indexCols,originalValueCols,paramDict,chartDict=process_and_prepare_multidimensional_data(paramDict,dfDict,df,dfDates,dfPeriods,dfAllPeriods,dfPlan,indexCols,valueCols,chartDict,toDrop,originalValueCols,colDict,tabDict,automateDict,planPlaybackDict,False)                
        df,dfBase,paramDict,sumCols,group_byCols=process_variance_calculation(dfDict,paramDict,chartDict,indexCols)
        chartDict,colorDict,run=preparare_parameters_for_each_variance_calculation(chartDict,element)
        df,group_byCols,sumCols=group_by_and_sort_data_for_variance_calculation(df,group_byCols,sumCols)
        df,dfBase,paramDict=prepare_data_for_waterfall(df,group_byCols,paramDict,chartDict,run,None,None,None,None)
        df=add_missing_elements(df, varianceArray)
        df,sortArray=sort_small_multiples(df,count,sortArray)           
        df = df.with_columns(pl.col(varianceAmountName).fill_null(0).alias(varianceAmountName))
        figDet,numberFormat,chartDict=draw_vertical_waterfall_chart(df,colorDict,paramDict,chartDict,run)
        fig.add_trace(figDet['data'][0],row=countRows,col=countCols)  
        fig.update_annotations(font=dict(size=fontSize,family=font)) 
        fig=move_labels_up(fig,chartDict,aggregationsToPlot)
        shapeArray=make_dic_to_color_first_bar(df,paramDict,chartDict,colorDict,run,count,shapeArray)
        df_lazy = ensure_lazyframe(df)
        periodOneValue = get_polars_value_at_index(
            df_lazy.filter(pl.col(workColumn) == chartDict[selectedPeriods][1]),
            varianceAmountName,
            0,
        )
        periodZeroValue = get_polars_value_at_index(df_lazy, varianceAmountName, 0)
        periodZeroLineArray=make_dic_to_add_line(df,paramDict,chartDict,colorDict,run,count,periodZeroLineArray,periodZeroValue,periodZeroValue,numberOfCharts,False,True,countRows)
        periodOneLineArray=make_dic_to_add_line(df,paramDict,chartDict,colorDict,run,count,periodOneLineArray,periodOneValue,periodOneValue,numberOfCharts,False,False,countRows)
        arrowArray=make_dic_to_add_line(df,paramDict,chartDict,colorDict,run,count,arrowArray,periodZeroValue,periodOneValue,numberOfCharts,True,False,countRows)
        annotationArrowArray=make_dic_to_add_annotation(df,paramDict,chartDict,colorDict,run,count,annotationArrowArray,numberOfCharts,False,True,countRows)
        annotationTextArray=make_dic_to_add_annotation(df,paramDict,chartDict,colorDict,run,count,annotationTextArray,numberOfCharts,True,False,countRows)
        if countCols < numberOfCols:
            countCols=countCols+1
        else: 
            countCols=1     
            countRows=countRows+1
        count=count+1
        countCalculations=countCalculations+1
        dfDim=duplicate_dataframe(df)
        dfDim = dfDim.with_columns(pl.lit(element).alias(varianceTypeName))
        frameArray.append(dfDim)
    dfExport = pl.concat(frameArray)
    shapeArrayNew=shapeArray+periodZeroLineArray+ periodOneLineArray+arrowArray       
    annotationArrowArrayNew=annotationArrowArray+annotationTextArray
    fig.update_layout(
        shapes=shapeArrayNew,
        annotations=annotationArrowArrayNew,
        )
    if plName == df.get_column(workColumn)[0]:
        pyName=plName  
    elif isYearBeforePy in paramDict and paramDict[isYearBeforePy]:
        pyName=yearBeforePyName 
    title,paramDict,chartDict=make_vertical_waterfall_chart_title(df,waterfallChart,paramDict,mainDimension,monetaryName,chartDict,pyName,acName)
    fig,width=update_waterfall_layout_small_multiples(df,fig,chartDict,numberOfRows,numberOfCols)                           
    fig=reverse_waterfall_y_range(fig) 
    fig=add_title_as_annotation(fig,title,waterfallChart,chartDict)
    fig=enable_draw_shapes(fig)
    fig=delete_black_vertical_lines(fig)
    paramDict=set_up_tab_for_show_or_download_chart(dfExport,fig,configPlotlyDict,chartDict,title,True,run,None,paramDict)
    return paramDict


def plot_scatter_chart_datashader(fig,dfCopy,timeColumn,colorDimension,chartDict,uniqueItems,paramDict,countRows,countCols,numberOfCols,numberOfRows):
    """
    scatter chart with many points
    """
    namingParams=get_naming_params()
    configParams=get_config_params()
    totalName=namingParams["totalName"]
    periodName=namingParams["periodName"]
    scatterChart=namingParams["scatterChart"]
    selectedPeriods=namingParams["selectedPeriods"]
    smallMultiplesCharts=namingParams["plotSmallMultiplesOtherCharts"]
    metConditionValue=namingParams["metConditionValue"]
    numberOfPlottedSmallMultiplesKey=namingParams["numberOfPlottedSmallMultiples"]     
    configPlotlyDict=configParams["configPlotlyDict"]
    configPlotlyDict=configPlotlyDict[scatterChart]
    periodOrder=chartDict[selectedPeriods]
    verticalSpacing=.05
    horizontalSpacing=.05
    if colorDimension == totalName:
        df=duplicate_dataframe(dfCopy)
        figDet=draw_scatter_chart_datashader(df,colorDimension,chartDict)
        if figDet:
            fig.add_trace(figDet['data'][0],row=countRows,col=countCols)
        countCols=countCols+1        
    else:
        chartDict[smallMultiplesCharts]=metConditionValue
        chartDict[numberOfPlottedSmallMultiplesKey]=len(uniqueItems)
        for item in uniqueItems:
            df = duplicate_dataframe(dfCopy)
            df = df.filter(pl.col(colorDimension) == item)
            figDet=draw_scatter_chart_datashader(df,colorDimension,chartDict) 
            if figDet:                                 
                fig.add_trace(figDet['data'][0],row=countRows,col=countCols)             
            if countCols < numberOfCols:
                countCols=countCols+1
            else: 
                countCols=1     
                countRows=countRows+1               
    return fig


def plot_alternative_combinations_plotly(df,chartDict,paramDict):
    """
    structure data and do charting 
    """ 
    namingParams=get_naming_params()
    configParams=get_config_params()
    varianceAmount=namingParams["varianceAmountName"] 
    dimension=namingParams["dimensionName"]  
    absolute=namingParams["absolute"]
    chosenChart=namingParams["chosenChart"]
    alternativeCombinationsChart=namingParams["alternativeCombinationsChart"]
    avgAmountPeriodsZeroOne=namingParams["avgAmountPeriodsZeroOne"]
    rowToPlot=chartDict[namingParams["rowToPlotName"]]
    configPlotlyDict=configParams["configPlotlyDict"]
    configPlotlyDict=configPlotlyDict[alternativeCombinationsChart]
    chosenChart=chartDict[chosenChart]
    if is_valid_lazyframe(df):
          df = df.with_columns(pl.col(varianceAmount).abs().alias(absolute))
          ui.markdown("---")
          fig=draw_alternative_combination_chart_plotly(df,paramDict,chartDict)
          title,paramDict,chartDict=make_alternative_combinations_charts_title(df,alternativeCombinationsChart,paramDict,rowToPlot,None,chartDict,None,None,None)
          fig=update_alternative_combination_chart_layout(fig,alternativeCombinationsChart)  
          fig,message=get_user_message(fig,alternativeCombinationsChart,"",None,paramDict,chartDict,df,None,None)
          fig=add_title_as_annotation(fig,title,chosenChart,chartDict)
          fig=add_message_as_annotation(fig,message,None,chosenChart,chartDict,paramDict)
          fig=enable_draw_shapes(fig)
          paramDict=set_up_tab_for_show_or_download_chart(df,fig,configPlotlyDict,chartDict,title+str(rowToPlot),False,None,None,paramDict)       
    else:     
          paramDict=add_empty_dataset_error_message_in_plot_charts_tab(paramDict)  
    return paramDict


def plot_vertical_waterfall_chart(dfCopy,dfBase,indexCols,colorDict,paramDict,chartDict,run):
    """
    plots waterfall chart with plotly. User can choose if one chart of small multiples
    vertical waterfall chart
    """
    namingParams=get_naming_params()
    waterfallChart=namingParams["verticalWaterfallChart"] 
    configParams=get_config_params()
    configPlotlyDict=configParams["configPlotlyDict"]
    configPlotlyDict=configPlotlyDict[waterfallChart]
    plotSmallMultiples=namingParams["plotSmallMultiplesWaterfall"] 
    runOneDimensionalAnalysis=namingParams["runOneDimensionalAnalysis"]
    processingChoice=namingParams["processingChoice"]  
    varianceAggregation=namingParams["varianceAggregation"]
    varianceName=namingParams["varianceName"]
    numberOfSmallMultiples=namingParams["numberOfSmallMultiplesWaterfall"]
    mainDimension=namingParams["mainDimension"]
    isYearBeforePy=namingParams["isYearBeforePy"]
    workColumn=namingParams["workColumn"]
    acName=namingParams["acName"] 
    pyName=namingParams["pyName"]  
    plName=namingParams["plName"]
    varianceTypeName=namingParams["varianceTypeName"]
    varianceAnalysisChart=namingParams["varianceAnalysisChart"]
    yearBeforePyName=namingParams["yearBeforePyName"]
    monetaryName=namingParams["monetaryLocalCurrencyName"]
    mainReportRunName=namingParams["mainReportRunName"]
    fixedVarianceScaleChoice=namingParams["fixedVarianceScaleChoice"] 
    df=duplicate_dataframe(dfCopy)
    dimension=None  
    if plotSmallMultiples in chartDict and chartDict[plotSmallMultiples]:
      paramDict,chartDict=plot_waterfall_small_multiples(df,dfBase,indexCols,paramDict,chartDict,colorDict,run)
    else:
      if run == runOneDimensionalAnalysis and mainDimension in chartDict:
            dimension = chartDict[mainDimension][0]
            df = df.head(chartDict[numberOfSmallMultiples]) 
            numberOfItems=chartDict[numberOfSmallMultiples]
      else:
            numberOfItems=df.height                 
      df,dfFiltered,paramDict=prepare_data_for_waterfall(df,indexCols,paramDict,chartDict,run,None,None,None,None) 
      if is_valid_lazyframe(df):
          df,indexCols=drop_columns_with_all_blancs(df,indexCols,indexCols,[varianceTypeName]) 
          fig,numberFormat,chartDict=draw_vertical_waterfall_chart(df,colorDict,paramDict,chartDict,run)
          fig=add_total_variance_arrow_vertical(df,fig,paramDict,chartDict,colorDict,run)
          fig=color_first_bar_vertical(df,fig,paramDict,chartDict,colorDict,run)
          if plName == df.get_column(workColumn)[0]:
            pyName=plName   
          elif isYearBeforePy in paramDict and paramDict[isYearBeforePy]:
            pyName=yearBeforePyName
          title,paramDict,chartDict=make_vertical_waterfall_chart_title(df,waterfallChart,paramDict,dimension,monetaryName,chartDict,pyName,acName)
          if run == runOneDimensionalAnalysis:
            fig=update_waterfall_layout_one_dimension(df,fig,chartDict)
          else:
            pass
            fig=update_waterfall_layout_variable_dimension(df,fig,chartDict)
            if run == mainReportRunName:
                pass
            fig,paramDict=get_chart_scale(fig,chartDict,paramDict,"X",varianceName,varianceAnalysisChart,fixedVarianceScaleChoice)
          fig=reverse_waterfall_y_range(fig)
          fig,message=get_user_message(fig,waterfallChart,"",str(run),paramDict,chartDict,df,None,None)
          fig=add_message_as_annotation(fig,message,None,waterfallChart,chartDict,paramDict)
          fig=add_title_as_annotation(fig,title,waterfallChart,chartDict)          
          fig=enable_draw_shapes(fig)
          chartDictCopy=purge_other_runs_from_chartdict(chartDict,run)
          paramDict=set_up_tab_for_show_or_download_chart(df,fig,configPlotlyDict,chartDictCopy,"",True,run,None,paramDict)      
    return paramDict,chartDict 

def plot_pareto_chart(dfCopy,chartDict,paramDict):
    namingParams=get_naming_params()
    configParams=get_config_params()
    paretoChartManyItems=configParams[namingParams["paretoChartManyItems"]]
    configPlotlyDict=configParams["configPlotlyDict"]
    selectedPeriods=namingParams["selectedPeriods"]
    metricsToPlot=namingParams["metricsToPlot"]
    metricsToPlot=chartDict[metricsToPlot]
    periodOrder=chartDict[selectedPeriods]
    paretoChart=namingParams["paretoChart"] 
    showOnly=namingParams["showOnly"]
    showAll=namingParams["showAll"]
    showTop=namingParams["showTop"]
    showBottom=namingParams["showBottom"]
    toPlotPeriod=namingParams["toPlotPeriod"]  
    periodName=namingParams["periodName"]
    plotCommentText=namingParams["plotCommentText"]
    chartDict[plotCommentText]=[] 
    toPlotPeriod=chartDict[toPlotPeriod]
    configPlotlyDict=configPlotlyDict[paretoChart]
    dfDict={}
    dfCopy, period = check_if_periods_in_columns(dfCopy, toPlotPeriod)
    df = dfCopy.filter(pl.col(periodName) == period)
    if is_valid_lazyframe(df):
        count=0
        colorListDict={}
        classColorDict={}
        ratioNameArray=[]
        metricArray=[]
        count=0
        df=change_column_names_if_cost_analysis(df,chartDict)
        metricsToPlot=change_array_of_metrics_if_cost_analysis(metricsToPlot,chartDict)
        for metric in metricsToPlot:
            lf,colorList,classColorDict,metric,ratioName=prepare_data_for_pareto(
                df,period,metric,chartDict,paramDict,colorListDict,classColorDict,count
            )
            colorListDict[metric]=colorList
            if count > 0:
                lf = lf.with_columns(
                    (pl.col(metric).cum_sum() / pl.col(metric).sum()).alias(ratioName)
                )
            dfDict[metric] = lf
            count += 1
        dfJoined = join_metric_dataframes(dfDict, metricsToPlot)
        dfFull = dfJoined.clone()
        if chartDict[showOnly] ==showTop:
            dfJoined=dfJoined.tail(paretoChartManyItems)
            for metric in metricsToPlot:
                colorListDict[metric]=colorListDict[metric][-paretoChartManyItems:]   
        elif chartDict[showOnly] ==showBottom:
            dfJoined=dfJoined.head(paretoChartManyItems)
            for metric in metricsToPlot:
                colorListDict[metric]=colorListDict[metric][:paretoChartManyItems] 
        count = 1
        fig = make_subplots(
            rows=1,
            cols=len(metricsToPlot),
            shared_yaxes=True,
            shared_xaxes=True,
        )
        maxScale = False
        fullFig = False
        closestRankArray, closestIndexArray = [], []
        dfPrompt = clean_df_for_prompt(dfJoined, chartDict)
        dfJoined_lazy = dfJoined
        dfFull_lazy = dfFull
        for metric in metricsToPlot:
            fig, showYTicklabels, bargap, closestRankArray, closestIndexArray, chartDict = draw_pareto_chart(
                dfJoined_lazy,
                dfFull_lazy,
                metric,
                colorListDict[metric],
                classColorDict[metric],
                closestRankArray,
                closestIndexArray,
                chartDict,
                paramDict,
                fig,
                count,
            )
            count = count + 1
        fig = get_pareto_axis(fig, metricsToPlot, chartDict)
        fig, paramDict = update_pareto_layout_and_get_messages(
            fig, period, chartDict, paramDict, metric, showYTicklabels, bargap, dfJoined
        )
        paramDict = set_up_tab_for_show_or_download_chart(
            dfPrompt, fig, configPlotlyDict, chartDict, metricsToPlot, False, None, None, paramDict
        )
    else:
        paramDict=add_empty_dataset_error_message_in_plot_charts_tab(paramDict)        
    return paramDict  

def plot_upset_chart(dfCopy,valueCols,chartDict,paramDict):
    from modules.charting.draw_venn_upset import organize_upset_chart

    namingParams=get_naming_params()
    plotSmallMultiplesKey=namingParams["plotSmallMultiplesOtherCharts"]
    selectedPeriods=namingParams["selectedPeriods"]
    yAxisDimension=namingParams["yAxisDimension"]
    periodName=namingParams["periodName"]
    smallMultiplesColumn=namingParams["smallMultiplesColumn"]
    xAxisDimension=namingParams["xAxisDimension"] 
    toPlotPeriod=namingParams["toPlotPeriod"]
    if smallMultiplesColumn in chartDict:
        smallMultiplesColumn=chartDict[smallMultiplesColumn]
    xColumn=chartDict[xAxisDimension]    
    periodOrder=chartDict[selectedPeriods] 
    text=""    
    if is_valid_lazyframe(dfCopy):
        period = chartDict[toPlotPeriod]
        dfCopy = dfCopy.filter(pl.col(periodName) == period)
        paramDict=organize_upset_chart(dfCopy,valueCols,chartDict,paramDict,period,text,False)
        ui.markdown("---")    
        df,uniqueItems,aggregateOtherItemsName,valueCols=show_only_largest(dfCopy,smallMultiplesColumn,xColumn,periodName,valueCols,chartDict,paramDict,"Y") 
        for element in uniqueItems:
            text=smallMultiplesColumn+": "+element+" "
            dfFiltered = duplicate_dataframe(df)
            dfFiltered = dfFiltered.filter(pl.col(smallMultiplesColumn) == element)
            paramDict=organize_upset_chart(dfFiltered,valueCols,chartDict,paramDict,period,text,element)
        ui.markdown("---")    
    else:
        paramDict=add_empty_dataset_error_message_in_plot_charts_tab(paramDict)                
    return paramDict


def plot_venn_chart(dfCopy,valueCols,chartDict,paramDict):
    from modules.charting.draw_venn_upset import organize_venn_chart

    namingParams=get_naming_params()
    plotSmallMultiplesKey=namingParams["plotSmallMultiplesOtherCharts"]
    selectedPeriods=namingParams["selectedPeriods"]
    yAxisDimension=namingParams["yAxisDimension"]
    periodName=namingParams["periodName"]
    smallMultiplesColumn=namingParams["smallMultiplesColumn"]
    xAxisDimension=namingParams["xAxisDimension"] 
    toPlotPeriod=namingParams["toPlotPeriod"]
    if smallMultiplesColumn in chartDict:
        smallMultiplesColumn=chartDict[smallMultiplesColumn]
    xColumn=chartDict[xAxisDimension]    
    periodOrder=chartDict[selectedPeriods] 
    text=""   
    if is_valid_lazyframe(dfCopy):
        period = chartDict[toPlotPeriod]
        dfCopy = dfCopy.filter(pl.col(periodName) == period)
        paramDict=organize_venn_chart(dfCopy,valueCols,chartDict,paramDict,period,text)
        ui.markdown("---") 
        df,uniqueItems,aggregateOtherItemsName,valueCols=show_only_largest(dfCopy,smallMultiplesColumn,xColumn,periodName,valueCols,chartDict,paramDict,"Y") 
        for element in uniqueItems:
            text=smallMultiplesColumn+": "+element+" "
            dfFiltered = duplicate_dataframe(df)
            dfFiltered = dfFiltered.filter(pl.col(smallMultiplesColumn) == element)
            if dfFiltered.height >0:
                paramDict=organize_venn_chart(dfFiltered,valueCols,chartDict,paramDict,period,text)
        ui.markdown("---")    
    else:
        paramDict=add_empty_dataset_error_message_in_plot_charts_tab(paramDict)                  
    return paramDict

def plot_horizontal_waterfall_chart(dfCopy,indexCols,valueCols,chartDict,valueColsWithPrice,xColumn,paramDictCopy,dfDict):
    namingParams=get_naming_params()
    plotValuesAsChoice=namingParams["plotValuesAsChoice"]
    percentOfResultRow=namingParams["percentOfResultRow"]
    yAxisMetric=namingParams["yAxisMetric"] 
    totalName=namingParams["totalName"]
    periodName=namingParams["periodName"]  
    indirectCostsName=namingParams["indirectCostsName"]  
    dateName=namingParams["dateName"]        
    chosenChart=namingParams["chosenChart"] 
    rowToPlot=namingParams["rowToPlotName"]
    absolute=namingParams["absolute"]
    resampleDates=namingParams["resampleDates"]
    metricsToPlot=namingParams["metricsToPlot"]  
    chosenChart=chartDict[chosenChart]
    rowToPlot=chartDict[rowToPlot]
    selectDimensionsToPlot=namingParams["selectDimensionsToPlot"]
    canPlotYearToYearKey=namingParams["canPlotYearToYear"]
    setTimePeriodTabLabel=namingParams["setTimePeriodTabLabel"]
    numberOfPlottedSmallMultiplesKey=namingParams["numberOfPlottedSmallMultiples"]
    columnsToPlot=chartDict[selectDimensionsToPlot]
    metricsToPlot=chartDict[metricsToPlot] 
    paramDict=copy.deepcopy(paramDictCopy)
    colorSequenceArray,lineWidth=get_color_sequence(dfCopy,paramDict,chartDict)
    colorChoice=get_color_choice(chartDict)
    canPlotYearToYear=True
    if canPlotYearToYearKey in chartDict:
        canPlotYearToYear=chartDict[canPlotYearToYearKey]
    if is_valid_lazyframe(dfCopy) and canPlotYearToYear:    
        dfCopy,indexCols=add_totals_column(dfCopy,indexCols) 
        columnsToPlot.insert(0,totalName)
        count=0                                
        for column in indexCols: 
            timeColumn=dateName 
            if column in columnsToPlot:
                group_byCols=[column,xColumn,periodName]
                df=duplicate_dataframe(dfCopy)   
                df=resample_dates(df,timeColumn,column,valueCols,chartDict,"sum",paramDict)
                dfCounts,chartDict=get_number_of_uniques(df,column,timeColumn,chartDict)
                valueCols=check_value_column_exist(df,valueCols)
                df = (
                    df
                    .group_by(group_byCols)          # group_by columns
                    .agg([pl.col(col).sum() for col in valueCols])  # aggregate
                )   
                numberOfItemsInCol = n_unique_lazy(column, df)
                if numberOfItemsInCol > 1 or column==totalName:     
                    df,uniqueItems,aggregateOtherItemsName,valueCols=show_only_largest(df,column,None,timeColumn,valueCols,chartDict,paramDict,"X")  
                    if len(uniqueItems)>1:
                        chartDict[numberOfPlottedSmallMultiplesKey]=len(uniqueItems)        
                    chartDict[resampleDates]=1
                    df=drop_AC_and_PY_month(df,column,valueCols,chartDict)
                    df=join_unique_metric_to_df(df,dfCounts,column,timeColumn,aggregateOtherItemsName,chartDict)
                    df=insert_unit_and_volume_price_column(df) 
                    df,paramDict,valueColsWithPrice=process_if_promo_data(df,paramDict,valueColsWithPrice) 
                    if plotValuesAsChoice in chartDict and chartDict[plotValuesAsChoice] != absolute:
                        df=compute_share_of_total(df,xColumn,column,valueCols,chartDict,dfDict,"mean",paramDict)                             
                    if column==totalName:
                        paramDict=draw_horizontal_waterfall_chart(df,None,metricsToPlot,metricsToPlot,paramDict,chartDict)
                    else:
                        paramDict=draw_horizontal_waterfall_chart(df,column,[metricsToPlot[0]],uniqueItems,paramDict,chartDict)
                    count=count+1                                                        
        if count==0:
            paramDict=add_empty_dataset_error_message_in_plot_charts_tab(paramDict)
    elif not canPlotYearToYear:  
      message=chosenChart+" must be plotted over 12 months and the most recent month in dataset is not December. Set 'Compare with period to date' to 'False' and 'Compare with rolling period' to 'True' in the "+setTimePeriodTabLabel+" tab."
      paramDict=add_warning_message_in_plot_charts_tab(paramDict,message)  
    else:
      paramDict=add_empty_dataset_error_message_in_plot_charts_tab(paramDict) 
    return paramDict           

def plot_multitier_column_chart(dfCopy,indexCols,valueCols,chartDict,valueColsWithPrice,xColumn,paramDictCopy,dfDict):
    namingParams=get_naming_params()
    plotValuesAsChoice=namingParams["plotValuesAsChoice"]
    percentOfResultRow=namingParams["percentOfResultRow"]
    yAxisMetric=namingParams["yAxisMetric"] 
    totalName=namingParams["totalName"]
    periodName=namingParams["periodName"]  
    indirectCostsName=namingParams["indirectCostsName"]  
    dateName=namingParams["dateName"]        
    chosenChart=namingParams["chosenChart"] 
    absolute=namingParams["absolute"]
    rowToPlot=namingParams["rowToPlotName"]
    resampleDates=namingParams["resampleDates"]
    metricsToPlot=namingParams["metricsToPlot"]    
    chosenChart=chartDict[chosenChart]
    rowToPlot=chartDict[rowToPlot]
    selectDimensionsToPlot=namingParams["selectDimensionsToPlot"]
    canPlotYearToYearKey=namingParams["canPlotYearToYear"]
    setTimePeriodTabLabel=namingParams["setTimePeriodTabLabel"]
    numberOfPlottedSmallMultiplesKey=namingParams["numberOfPlottedSmallMultiples"]
    columnsToPlot=chartDict[selectDimensionsToPlot]
    metricsToPlot=chartDict[metricsToPlot] 
    paramDict=copy.deepcopy(paramDictCopy)
    colorSequenceArray,lineWidth=get_color_sequence(dfCopy,paramDict,chartDict)
    colorChoice=get_color_choice(chartDict)
    canPlotYearToYear=True
    if canPlotYearToYearKey in chartDict:
        canPlotYearToYear=chartDict[canPlotYearToYearKey]
    if is_valid_lazyframe(dfCopy) and canPlotYearToYear:    
        dfCopy,indexCols=add_totals_column(dfCopy,indexCols) 
        columnsToPlot.insert(0,totalName)
        count=0                                
        for column in indexCols: 
            timeColumn=dateName 
            if column in columnsToPlot:
                group_byCols=[column,xColumn,periodName]
                df=duplicate_dataframe(dfCopy)   
                df=resample_dates(df,timeColumn,column,valueCols,chartDict,"sum",paramDict)
                dfCounts,chartDict=get_number_of_uniques(df,column,timeColumn,chartDict)
                valueCols=check_value_column_exist(df,valueCols)
                df = (
                    df
                    .group_by(group_byCols)          # group_by columns
                    .agg([pl.col(col).sum() for col in valueCols])  # aggregate
                )  
                numberOfItemsInCol = n_unique_lazy(column, df)
                if numberOfItemsInCol > 1 or column==totalName:
                    df,uniqueItems,aggregateOtherItemsName,valueCols=show_only_largest(df,column,None,timeColumn,valueCols,chartDict,paramDict,"X")
                    if len(uniqueItems)>1:
                        chartDict[numberOfPlottedSmallMultiplesKey]=len(uniqueItems)                                       
                    chartDict[resampleDates]=1
                    df=drop_AC_and_PY_month(df,column,valueCols,chartDict)
                    df=join_unique_metric_to_df(df,dfCounts,column,timeColumn,aggregateOtherItemsName,chartDict)
                    df=insert_unit_and_volume_price_column(df) 
                    df,paramDict,valueColsWithPrice=process_if_promo_data(df,paramDict,valueColsWithPrice) 
                    if plotValuesAsChoice in chartDict and chartDict[plotValuesAsChoice] != absolute:
                        df=compute_share_of_total(df,xColumn,column,valueCols,chartDict,dfDict,"mean",paramDict)                             
                    if column==totalName:
                        paramDict=draw_multitier_column_chart(df,None,metricsToPlot,metricsToPlot,paramDict,chartDict)
                    else:
                        paramDict=draw_multitier_column_chart(df,column,[metricsToPlot[0]],uniqueItems,paramDict,chartDict)
                    count=count+1                                                        
        if count==0:
            paramDict=add_empty_dataset_error_message_in_plot_charts_tab(paramDict)
    elif not canPlotYearToYear:
      message=chosenChart+" must be plotted over 12 months and the most recent month in dataset is not December. Set 'Compare with period to date' to 'False' and 'Compare with rolling period' to 'True' in the "+setTimePeriodTabLabel+" tab."
      paramDict=add_warning_message_in_plot_charts_tab(paramDict,message)      
    else:
      paramDict=add_empty_dataset_error_message_in_plot_charts_tab(paramDict)
    return paramDict

def plot_mekko_charts(dfCopy,valueCols,chartDict,xColumn,paramDict):
    """
    plots mekko chart
    """ 
    namingParams=get_naming_params() 
    smallMultiplesColumn=namingParams["smallMultiplesColumn"]  
    plotSmallMultiplesKey=namingParams["plotSmallMultiplesOtherCharts"]
    selectedPeriods=namingParams["selectedPeriods"]
    totalName=namingParams["totalName"]    
    toPlotPeriod=namingParams["toPlotPeriod"] 
    periodName=namingParams["periodName"] 
    nothingFilteredName=namingParams["nothingFilteredName"]
    totalName=namingParams["totalName"] 
    toPlotPeriod=chartDict[toPlotPeriod]      
    smallMultiplesColumn=chartDict[smallMultiplesColumn]
    dfCopy = ensure_lazyframe(dfCopy)
    if isinstance(dfCopy, pl.DataFrame):  # guard against premature collection
        raise TypeError("dfCopy must remain a LazyFrame")

    usedColorDict = {}
    if is_valid_lazyframe(dfCopy):
        ui.markdown("---")
        if smallMultiplesColumn == nothingFilteredName:
            smallMultiplesColumn = totalName
            dfCopy = dfCopy.with_columns(pl.lit(0).alias(totalName))
            if isinstance(dfCopy, pl.DataFrame):
                raise TypeError("dfCopy collected before plotting")

        smallMultiplesColumnArray = [smallMultiplesColumn]
        dfCopy, smallMultiplesColumnArray = add_totals_column(
            dfCopy, smallMultiplesColumnArray
        )
        if chartDict.get(plotSmallMultiplesKey) and smallMultiplesColumn != totalName:
            smallMultiplesColumnArray = [
                column for column in smallMultiplesColumnArray if column != totalName
            ]
        if isinstance(dfCopy, pl.DataFrame):
            raise TypeError("dfCopy collected before plotting")

        for column in smallMultiplesColumnArray:
            df = group_by_dataset_for_marimekko_and_barmekko(
                dfCopy, column, smallMultiplesColumnArray, valueCols, chartDict
            )
            if isinstance(df, pl.DataFrame):
                raise TypeError("df collected before plotting")

            df, toPlotPeriod = check_if_periods_in_columns(df, toPlotPeriod)
            if isinstance(df, pl.DataFrame):
                raise TypeError("df collected before plotting")

            df = df.filter(pl.col(periodName) == toPlotPeriod)
            if isinstance(df, pl.DataFrame):
                raise TypeError("df collected before plotting")

            numberOfItemsInCol = n_unique_lazy(column, df)
            if numberOfItemsInCol >= 1:
                (
                    usedColorDict,
                    paramDict,
                    chartDict,
                ) = draw_mekko_chart(
                    df, column, valueCols, chartDict, paramDict, usedColorDict, xColumn
                )
            else:
                paramDict = add_empty_dataset_error_message_in_plot_charts_tab(
                    paramDict
                )
    else:
        paramDict = add_empty_dataset_error_message_in_plot_charts_tab(paramDict)
    return paramDict


def plot_stacked_pareto_chart(dfCopy,chartDict,paramDict):
    namingParams=get_naming_params()
    configParams=get_config_params()
    uniformTextMinSize = get_uniform_text_min_size(configParams, namingParams)
    paretoChartManyItems=configParams[namingParams["paretoChartManyItems"]]
    configPlotlyDict=configParams["configPlotlyDict"]
    selectedPeriods=namingParams["selectedPeriods"]
    metricsToPlot=namingParams["metricsToPlot"]
    aggregateUniquesDimension=namingParams["aggregateUniquesDimension"]
    aggregateUniquesByDimension=namingParams["aggregateUniquesByDimension"]
    valueName=namingParams["valueName"]
    colorName=namingParams["colorName"]
    oppositeSign=namingParams["oppositeSign"] 
    countName=namingParams["countName"]  
    stackedParetoChart=namingParams["stackedParetoChart"] 
    periodName=namingParams["periodName"]
    countColumn=namingParams["countColumn"]
    numberOfTop=namingParams["numberOfTop"]
    chosenChart=chartDict[namingParams["chosenChart"]]
    rank=namingParams["rankName"] 
    cumSum=namingParams["cumSum"] 
    workColumn=namingParams["workColumn"] 
    showMetricsInDataColumn=namingParams["showMetricsInDataColumn"]
    aggregateOtherItemsNameKey=namingParams["aggregateOtherItemsName"]
    countByColumnKey=namingParams["countByColumn"]    
    toPlotPeriod=namingParams["toPlotPeriod"]   
    toPlotPeriod=chartDict[toPlotPeriod]
    configPlotlyDict=configPlotlyDict[stackedParetoChart]
    metricsToPlot=chartDict[metricsToPlot]
    periodOrder=chartDict[selectedPeriods]
    dfDict={}
    usedColorDict={}
    dfCopy, period = check_if_periods_in_columns(dfCopy, toPlotPeriod)
    df = dfCopy.filter(pl.col(periodName) == period)
    if is_valid_lazyframe(df) and chartDict[countColumn]:
        countByColumn=countName+" "+chartDict[countColumn]
        chartDict[countByColumnKey]=countByColumn  
        dfCounts=make_df_counts_unique_values(df,countByColumn,chartDict)
        count=0
        colorListDict={}
        classColorDict={}
        if chartDict[aggregateUniquesByDimension]:
            dimension=chartDict[aggregateUniquesDimension]
            secondDimension=chartDict[countColumn]
            secondDimension=None
            df,uniqueItems,aggregateOtherItemsName,metricsToPlot=show_only_largest(df,chartDict[aggregateUniquesDimension],None,periodName,metricsToPlot,chartDict,paramDict,"X")
        else:
            dimension=chartDict[countColumn]
        for metric in metricsToPlot:     
            dfDict[metric],colorList,classColorDict,metric,ratioName=prepare_data_for_pareto(df,period,metric,chartDict,paramDict,colorListDict,classColorDict,count)
            colorListDict[metric]=colorList
            count=count+1    
        dfJoined=join_metric_dataframes(dfDict,metricsToPlot)
        if not chartDict[aggregateUniquesByDimension]:
            dfJoined,group_byCols,indexColumn=make_df_for_pareto_classes(dfJoined,dfCounts)
        else:
            dfJoined,group_byCols,indexColumn=make_df_for_pareto_items(dfJoined,dfCounts,countByColumn,chartDict)
        sumColsArray=metricsToPlot+[countByColumn]
        df=dfJoined.group_by(group_byCols).agg([pl.col(c).sum() for c in sumColsArray])
        df,chartDict,sumColsArray=calculate_metrics_for_data_column(df,chartDict,sumColsArray,countByColumn)
        numberOfRows=df.get_column(countByColumn).sum()
        if chartDict[aggregateUniquesByDimension]:
            df = df.sort(by=metricsToPlot[0],descending=True)
        dfPositive=duplicate_dataframe(df)    
        dfSum=df.select(sumColsArray).sum()
        df = df.with_columns(pl.col(countByColumn).alias(workColumn))
        df = df.with_columns((pl.col(countByColumn) / numberOfRows).alias(countByColumn))
        for metric in metricsToPlot:
            # Negative metric values are set to zero before normalising,
            # implemented here using conditional expressions.
            metric_total = dfPositive.get_column(metric).sum()
            df = df.with_columns((pl.col(metric) / metric_total).alias(metric))
            if metric_total < 0:
                df = df.with_columns((-pl.col(metric)).alias(metric))
        cols, schema = get_schema_and_column_names(df)
        if indexColumn in cols:
            other_cols = [c for c in cols if c != indexColumn]
            df = df.select([indexColumn, *other_cols])
        df=rank_others_as_last(df,aggregateOtherItemsNameKey,99)
        if showMetricsInDataColumn in chartDict and chartDict[showMetricsInDataColumn]:
            df = df.with_columns(pl.col(countByColumn).cum_sum().alias(cumSum))
            dfSum = dfSum.with_columns([
                pl.lit(0).alias(workColumn),
                pl.lit(0).alias(cumSum),
            ])
        else:
            dfSum = dfSum.with_columns(pl.lit(0).alias(workColumn))
        metricColumns,schema=get_schema_and_column_names(df)
        df = transpose_chart_frame(
            df,
            header_name=valueName,
            column_names=indexColumn if indexColumn in metricColumns else None,
            include_header=False,
        )
        columns,schema=get_schema_and_column_names(df)
        if valueName not in columns:
            sumColumns, _ = get_schema_and_column_names(dfSum)
            dfSumRenamed = dfSum.rename({sumColumns[0]: valueName})
            df = df.with_row_index(name="__index")
            dfSumRenamed = dfSumRenamed.with_row_index(name="__index")
            df = (
                df.join(
                    dfSumRenamed,
                    on="__index",
                    how="left",
                    suffix="_right",
                )
                .drop("__index")
            )
            cols, schema = get_schema_and_column_names(df)
            drop_cols = [c for c in cols if c.endswith("_right")]
            if drop_cols:
                df = df.drop(drop_cols)
            df = rank_others_as_last(df, workColumn, len(metricsToPlot) + 1)
        if not chartDict[aggregateUniquesByDimension]:
            classColorDict=dict(sorted(classColorDict[metricColumns[0]].items()))
            colors=list(classColorDict.values())
        elif chartDict[aggregateUniquesByDimension]:   
            colorDict=get_color_dictionary(chartDict)
            colorArray=get_color_array(colorDict,chartDict) 
            if len(usedColorDict)==0:
                usedColorDict=track_used_colors(usedColorDict,columns,aggregateOtherItemsName,colorArray)             
            else:
                colorArray=assign_same_colors_to_all_charts(colorArray,usedColorDict,columns,aggregateOtherItemsName)     
            colors=colorArray    
        colors=set_other_color_to_grey(columns,aggregateOtherItemsNameKey,colors,chartDict,0)
        colors=insert_highlight_color(None,columns,colors,paramDict,chartDict) 
        if is_valid_lazyframe(df) and len(columns)>0:
            fig,dfNegative,message,chartDict=stacked_bar_width_plot(df,chartDict,paramDict,columns, width_col=None, colors=colors)  
            title,paramDict,chartDict=make_stacked_pareto_and_pareto_chart_title(dfCopy,chosenChart,paramDict,dimension,metricColumns[0],chartDict,period,None)
            fig.update_layout(
                            uniformtext=dict(mode="show", minsize=uniformTextMinSize),
                            paper_bgcolor='rgba(0,0,0,0)',
                            plot_bgcolor='rgba(0,0,0,0)' ,
                            margin={
                                     #   "r": 0,
                                "l": 100,
                                     #    "b": 0,
                                     #   "pad":0,
                                     #"autoexpand":False,
                                    },  
                              )
            fig,message=get_user_message(fig,chosenChart,period,None,paramDict,chartDict,df,None,None)
            fig=add_title_as_annotation(fig,title,chosenChart,chartDict)
            fig=add_message_as_annotation(fig,message,None,chosenChart,chartDict,paramDict)
            fig=enable_draw_shapes(fig)
            paramDict=set_up_tab_for_show_or_download_chart(df,fig,configPlotlyDict,chartDict,sumColsArray+[chartDict[countColumn]],False,None,None,paramDict)              
    elif not chartDict[countColumn]:
        message="No hierarchical columns in dataset. Impossible to plot stacked pareto chart."
        paramDict=add_error_message_in_plot_charts_tab(paramDict,message)
    else:    
        paramDict=add_empty_dataset_error_message_in_plot_charts_tab(paramDict)    
    return paramDict 


def plot_dot_chart(dfCopy,indexCols,valueCols,chartDict,valueColsWithPrice,xColumn,paramDict,dfDict):
    """
    plots by period chart
    """ 
    namingParams=get_naming_params()
    configParams=get_config_params()
    plotValuesAsChoice=namingParams["plotValuesAsChoice"]
    absolute=namingParams["absolute"]
    percentOfResultRow=namingParams["percentOfResultRow"]
    dateName=namingParams["dateName"]
    periodName=namingParams["periodName"]  
    totalName=namingParams["totalName"]
    rowToPlot=namingParams["rowToPlotName"]
    yAxisMetric=namingParams["yAxisMetric"]     
    filterDates=namingParams["filterDates"]
    singleMetric=namingParams["singleMetric"]
    numberOfTop=namingParams["numberOfTop"]
    chosenChart=namingParams["chosenChart"]  
    dotChart=namingParams["dotChart"]
    selectDimensionsToPlot=namingParams["selectDimensionsToPlot"]
    selectedPeriods=namingParams["selectedPeriods"]
    periodOrder=chartDict[selectedPeriods]
    columnsToPlot=chartDict[selectDimensionsToPlot]
    chosenChart=chartDict[chosenChart]      
    rowToPlot=chartDict[rowToPlot]
    configPlotlyDict=configParams["configPlotlyDict"]
    configPlotlyDict=configPlotlyDict[dotChart]
    if is_valid_lazyframe(dfCopy):
      ui.markdown("---")
      plottedSomething=False    
      dfCopy,indexCols=add_totals_column(dfCopy,indexCols) 
      columnsToPlot.insert(0,totalName)
      fullFig=False
      metricType=False
      for column in columnsToPlot: 
        if column in columnsToPlot and column != totalName:
            group_byCols=[column,xColumn]
            if filterDates in chartDict and chartDict[filterDates]:
                  group_byCols=[column,xColumn]      
            dfCounts,chartDict=get_number_of_uniques(dfCopy,column,xColumn,chartDict)
            valueCols=check_value_column_exist(dfCopy,valueCols)      
            df = (
                    dfCopy
                    .group_by(group_byCols)          # group_by columns
                    .agg([pl.col(col).sum() for col in valueCols])  # aggregate
                )
            numberOfItemsInCol = n_unique_lazy(column, df)
            if numberOfItemsInCol > 1 or column==totalName or not plottedSomething :
                  plottedSomething=True   
                  df,uniqueItems,aggregateOtherItemsName,valueCols=show_only_largest(df,column,None,xColumn,valueCols,chartDict,paramDict,"X") 
                  df=join_unique_metric_to_df(df,dfCounts,column,xColumn,aggregateOtherItemsName,chartDict)               
                  df=insert_unit_and_volume_price_column(df)
                  df,paramDict,valueColsWithPrice=process_if_promo_data(df,paramDict,valueColsWithPrice)
                  if plotValuesAsChoice in chartDict and chartDict[plotValuesAsChoice] != absolute:
                        df=compute_share_of_total(df,xColumn,column,valueCols,chartDict,dfDict,"mean",paramDict)       
                  count=0 
                  for metric in [chartDict[singleMetric]]:
                        checkedPeriodOrder=[]    
                        for period in periodOrder:
                            df,period=check_if_periods_in_columns(df,period)
                            checkedPeriodOrder.append(period)                        
                        order_map = {v: i for i, v in enumerate(checkedPeriodOrder)}
                        df = df.with_columns(
                            pl.col(periodName)
                            .replace_strict(order_map, return_dtype=pl.Int64)
                            .alias("_ord")
                        )
                        df = df.sort("_ord").drop("_ord")
                        df = df.with_columns(pl.col(periodName).cast(pl.Categorical))
                        df2,chartFormat,chartDict=tag_if_increasing_or_decreasing(df,metric,column,paramDict,chartDict)                     
                        fig,df=draw_dot_chart(df2,paramDict,column,metric,xColumn,chartDict,count,uniqueItems,checkedPeriodOrder,aggregateOtherItemsName) 
                        title, paramDict, chartDict = make_slope_and_dot_chart_title(
                            df,
                            dotChart,
                            paramDict,
                            column,
                            metric,
                            chartDict,
                            checkedPeriodOrder[0],
                            checkedPeriodOrder[1],
                        )
                        fig,fullFig,metricType=keep_same_scale_for_all_plots(fig,metric,metricType,fullFig,"X")  
                        fig=update_dot_chart_layout(fig,dotChart)  
                        fig,message=get_user_message(fig,dotChart,metric,metric+column,paramDict,chartDict,df,None,None)
                        fig=add_message_as_annotation(fig,message,None,chosenChart,chartDict,paramDict)
                        fig=add_title_as_annotation(fig,title,chosenChart,chartDict)
                        fig=enable_draw_shapes(fig)
                        paramDict=set_up_tab_for_show_or_download_chart(df,fig,configPlotlyDict,chartDict,column+metric,False,None,column,paramDict)                                                 
      if not plottedSomething:        
            paramDict=add_empty_dataset_error_message_in_plot_charts_tab(paramDict)
    else:  
      paramDict=add_empty_dataset_error_message_in_plot_charts_tab(paramDict)
    return paramDict 


def plot_trend_comparison_charts(dfCopy,indexCols,valueCols,chartDict,valueColsWithPrice,xColumn,paramDict,dfDict):
    """
    plots by period chart
    """ 
    namingParams=get_naming_params()
    plotValuesAsChoice=namingParams["plotValuesAsChoice"]
    absolute=namingParams["absolute"]
    percentOfResultRow=namingParams["percentOfResultRow"]
    dateName=namingParams["dateName"]
    periodName=namingParams["periodName"]  
    totalName=namingParams["totalName"]
    rowToPlot=namingParams["rowToPlotName"]
    yAxisMetric=namingParams["yAxisMetric"]     
    metricsToPlot=namingParams["metricsToPlot"]
    numberOfTop=namingParams["numberOfTop"]
    selectedPeriods=namingParams["selectedPeriods"]
    acName=namingParams["acName"] 
    plName=namingParams["plName"]
    pyName=namingParams["pyName"]  
    chosenChart=namingParams["chosenChart"]
    resampleDates=namingParams["resampleDates"]
    selectDimensionsToPlot=namingParams["selectDimensionsToPlot"]
    columnsToPlot=chartDict[selectDimensionsToPlot]
    metricsToPlot=chartDict[metricsToPlot] 
    chosenChart=chartDict[chosenChart]   
    periodOrder=chartDict[selectedPeriods]
    rowToPlot=chartDict[rowToPlot] 
    if is_valid_lazyframe(dfCopy):
        ui.markdown("---")   
        dfCopy,indexCols=add_totals_column(dfCopy,indexCols)
        columnsToPlot.insert(0,totalName)
        count=0                
        for column in indexCols: 
            timeColumn=dateName 
            if column in columnsToPlot:
                group_byCols=[column,xColumn,periodName] 
                df=duplicate_dataframe(dfCopy)  
                df=resample_dates(df,xColumn,column,valueCols,chartDict,"sum",paramDict)
                dfCounts,chartDict=get_number_of_uniques(df,column,timeColumn,chartDict)
                valueCols=check_value_column_exist(df,valueCols) 
                df = (
                    df
                    .group_by(group_byCols)          # group_by columns
                    .agg([pl.col(col).sum() for col in valueCols])  # aggregate
                        )
                numberOfItemsInCol = n_unique_lazy(column, df)
                if numberOfItemsInCol > 1 or column==totalName:             
                    df,uniqueItems,aggregateOtherItemsName,valueCols=show_only_largest(df,column,None,timeColumn,valueCols,chartDict,paramDict,"X")  
                    chartDict[resampleDates]=1
                    df=drop_AC_and_PY_month(df,column,valueCols,chartDict)
                    df=join_unique_metric_to_df(df,dfCounts,column,timeColumn,aggregateOtherItemsName,chartDict)
                    df=insert_unit_and_volume_price_column(df) 
                    df,paramDict,valueColsWithPrice=process_if_promo_data(df,paramDict,valueColsWithPrice) 
                    if plotValuesAsChoice in chartDict and chartDict[plotValuesAsChoice] != absolute:
                        df=compute_share_of_total(df,xColumn,column,valueCols,chartDict,dfDict,"mean",paramDict)                              
                    if column==totalName:
                        paramDict=draw_actual_vs_previous_year_chart(df,None,metricsToPlot,metricsToPlot,paramDict,chartDict)
                    else:
                        paramDict=draw_actual_vs_previous_year_chart(df,column,[metricsToPlot[0]],uniqueItems,paramDict,chartDict)   
                    count=count+1                                                        
        if count==0:
            paramDict=add_empty_dataset_error_message_in_plot_charts_tab(paramDict)
    else:
      paramDict=add_empty_dataset_error_message_in_plot_charts_tab(paramDict)
    return paramDict

def plot_area_charts(dfCopy,indexCols,valueCols,chartDict,valueColsWithPrice,xColumn,paramDict,dfDict):
    """
    plots by period chart
    """ 
    namingParams=get_naming_params()
    configParams=get_config_params()
    plotValuesAsChoice=namingParams["plotValuesAsChoice"]
    absolute=namingParams["absolute"]
    percentOfResultRow=namingParams["percentOfResultRow"]
    dateName=namingParams["dateName"]
    periodName=namingParams["periodName"]  
    totalName=namingParams["totalName"]
    rowToPlot=namingParams["rowToPlotName"]
    yAxisMetric=namingParams["yAxisMetric"]     
    filterDates=namingParams["filterDates"]
    metricsToPlot=namingParams["metricsToPlot"]
    numberOfTop=namingParams["numberOfTop"]
    chosenChart=namingParams["chosenChart"]
    areaChart=namingParams["areaChart"]
    selectDimensionsToPlot=namingParams["selectDimensionsToPlot"]
    smallMultiplesCharts=namingParams["plotSmallMultiplesOtherCharts"]
    metConditionValue=namingParams["metConditionValue"]
    numberOfPlottedSmallMultiplesKey=namingParams["numberOfPlottedSmallMultiples"]     
    columnsToPlot=chartDict[selectDimensionsToPlot]
    chosenChart=chartDict[chosenChart]      
    rowToPlot=chartDict[rowToPlot]
    configPlotlyDict=configParams["configPlotlyDict"]
    configPlotlyDict=configPlotlyDict[areaChart]
    if is_valid_lazyframe(dfCopy):
      ui.markdown("---")
      plottedSomething=False  
      dfCopy,indexCols=add_totals_column(dfCopy,indexCols)
      columnsToPlot.insert(0,totalName) 
      for column in indexCols: 
        if column in columnsToPlot and column != totalName:
            group_byCols=[column,xColumn]
            timeColumn=dateName    
            if filterDates in chartDict and chartDict[filterDates]:
                  group_byCols=[column,xColumn,periodName]
            df=duplicate_dataframe(dfCopy)    
            df=resample_dates(df,xColumn,column,valueCols,chartDict,"sum",paramDict)
            dfCounts,chartDict=get_number_of_uniques(df,column,timeColumn,chartDict)
            valueCols=check_value_column_exist(df,valueCols)   
            df = (
                    df
                    .group_by(group_byCols)          # group_by columns
                    .agg([pl.col(col).sum() for col in valueCols])  # aggregate
                        ) 
            numberOfItemsInCol = n_unique_lazy(column, df)
            if numberOfItemsInCol > 1 or column==totalName or not plottedSomething :
                  if numberOfItemsInCol>1:
                        chartDict[numberOfPlottedSmallMultiplesKey]=numberOfItemsInCol 
                  plottedSomething=True
                  df,uniqueItems,aggregateOtherItemsName,valueCols=show_only_largest(df,column,None,timeColumn,valueCols,chartDict,paramDict,"X") 
                  df=join_unique_metric_to_df(df,dfCounts,column,timeColumn,aggregateOtherItemsName,chartDict)                   
                  df=insert_unit_and_volume_price_column(df)
                  df,paramDict,valueColsWithPrice=process_if_promo_data(df,paramDict,valueColsWithPrice)
                  if plotValuesAsChoice in chartDict and chartDict[plotValuesAsChoice] != absolute:
                        df=compute_share_of_total(df,xColumn,column,valueCols,chartDict,dfDict,"mean",paramDict) 
                  count=0 
                  for element in chartDict[metricsToPlot]:
                        fig,dfExport=draw_area_chart(df,paramDict,column,element,xColumn,chartDict,count,uniqueItems,aggregateOtherItemsName)
                        title,paramDict,chartDict=make_timeline_and_area_charts_title(df,areaChart,paramDict,column,element,chartDict,None,None) 
                        fig=update_area_chart_layout(fig,areaChart)  
                        fig,message=get_user_message(fig,areaChart,element,column+element,paramDict,chartDict,df,None,None)
                        fig=add_message_as_annotation(fig,message,None,chosenChart,chartDict,paramDict)
                        fig=add_title_as_annotation(fig,title,chosenChart,chartDict)
                        fig=enable_draw_shapes(fig)
                        paramDict=set_up_tab_for_show_or_download_chart(dfExport,fig,configPlotlyDict,chartDict,column+element,False,None,column,paramDict)                                                        
      if not plottedSomething:
            paramDict=add_empty_dataset_error_message_in_plot_charts_tab(paramDict)
    else:
      paramDict=add_empty_dataset_error_message_in_plot_charts_tab(paramDict)
    return paramDict  

def plot_stacked_bar_charts(dfCopy,indexCols,valueCols,chartDict,valueColsWithPrice,xColumn,paramDict,dfDict):
    """
    plots by period chart
    """ 
    namingParams=get_naming_params()
    smallMultiplesColumn=namingParams["smallMultiplesColumn"]
    nothingFilteredName=namingParams["nothingFilteredName"] 
    toPlotPeriod=namingParams["toPlotPeriod"]   
    toPlotPeriod=chartDict[toPlotPeriod]
    smallMultiplesColumn=chartDict[smallMultiplesColumn]
    usedColorDict={}
    if is_valid_lazyframe(dfCopy):
        ui.markdown("---")
        if smallMultiplesColumn == nothingFilteredName:
            smallMultiplesColumn = namingParams["totalName"]
            dfCopy = dfCopy.with_columns(pl.lit(0).alias(smallMultiplesColumn))
        smallMultiplesColumnArray=[smallMultiplesColumn]
        dfCopy,smallMultiplesColumnArray=add_totals_column(dfCopy,smallMultiplesColumnArray)
        for column in smallMultiplesColumnArray: 
            df,group_byCols=group_by_dataset_for_stacked_bar(dfCopy,column,smallMultiplesColumnArray,valueCols,chartDict)
            df,toPlotPeriod=check_if_periods_in_columns(df,toPlotPeriod)
            numberOfItemsInCol = n_unique_lazy(column, df)
            if numberOfItemsInCol>=1:  
                usedColorDict,paramDict,chartDict=draw_stacked_bar_chart(df,column,toPlotPeriod,indexCols,valueColsWithPrice,chartDict,paramDict,usedColorDict,xColumn)
            else:
                paramDict=add_empty_dataset_error_message_in_plot_charts_tab(paramDict)   
    else:
        paramDict=add_empty_dataset_error_message_in_plot_charts_tab(paramDict)                                                
    return paramDict

def plot_slope_charts(dfCopy,indexCols,valueCols,chartDict,valueColsWithPrice,xColumn,paramDict,dfDict):
    """
    plots by period chart
    """ 
    namingParams=get_naming_params()
    configParams=get_config_params()
    plotValuesAsChoice=namingParams["plotValuesAsChoice"]
    absolute=namingParams["absolute"]
    percentOfResultRow=namingParams["percentOfResultRow"]
    dateName=namingParams["dateName"]
    periodName=namingParams["periodName"]  
    totalName=namingParams["totalName"]
    rowToPlot=namingParams["rowToPlotName"]
    yAxisMetric=namingParams["yAxisMetric"]     
    filterDates=namingParams["filterDates"]
    metricsToPlot=namingParams["metricsToPlot"]
    numberOfTop=namingParams["numberOfTop"]
    chosenChart=namingParams["chosenChart"]
    slopeChart=namingParams["slopeChart"]
    selectDimensionsToPlot=namingParams["selectDimensionsToPlot"]
    selectedPeriods=namingParams["selectedPeriods"]
    periodOrder=chartDict[selectedPeriods]
    columnsToPlot=chartDict[selectDimensionsToPlot]
    chosenChart=chartDict[chosenChart]      
    rowToPlot=chartDict[rowToPlot]
    metricsToPlot=chartDict[metricsToPlot]
    count=0    
    if is_valid_lazyframe(dfCopy):
      ui.markdown("---")    
      dfCopy,indexCols=add_totals_column(dfCopy,indexCols)
      columnsToPlot.insert(0,totalName) 
      fullFig=False
      metricType=False
      for column in columnsToPlot: 
        timeColumn=dateName    
        if column in indexCols:      
            group_byCols=[column,xColumn]   
            if filterDates in chartDict and chartDict[filterDates]:
                  group_byCols=[column,xColumn]  
            dfCounts,chartDict=get_number_of_uniques(dfCopy,column,xColumn,chartDict)
            valueCols=check_value_column_exist(dfCopy,valueCols)
            df = (
                    dfCopy
                    .group_by(group_byCols)          # group_by columns
                    .agg([pl.col(col).sum() for col in valueCols])  # aggregate
                )  
            numberOfItemsInCol = n_unique_lazy(column, df)
            if numberOfItemsInCol > 1 or column==totalName:
                  df,uniqueItems,aggregateOtherItemsName,valueCols=show_only_largest(df,column,None,xColumn,valueCols,chartDict,paramDict,"X")                    
                  df=join_unique_metric_to_df(df,dfCounts,column,xColumn,aggregateOtherItemsName,chartDict)     
                  df=insert_unit_and_volume_price_column(df)
                  df,paramDict,valueColsWithPrice=process_if_promo_data(df,paramDict,valueColsWithPrice)
                  if plotValuesAsChoice in chartDict and chartDict[plotValuesAsChoice] != absolute:
                        df=compute_share_of_total(df,xColumn,column,valueCols,chartDict,dfDict,"mean",paramDict)
                  if column==totalName:
                    fullFig,metricType,paramDict=draw_slope_chart(df,column,metricsToPlot,metricsToPlot,paramDict,chartDict,uniqueItems,aggregateOtherItemsName,fullFig,metricType)
                  else:
                    fullFig,metricType,paramDict=draw_slope_chart(df,column,[metricsToPlot[0]],uniqueItems,paramDict,chartDict,uniqueItems,aggregateOtherItemsName,fullFig,metricType)  
                  count=count+1                                               
      if count==0:
            paramDict=add_empty_dataset_error_message_in_plot_charts_tab(paramDict)
    else:
      paramDict=add_empty_dataset_error_message_in_plot_charts_tab(paramDict)
    return paramDict


def plot_waterfall_small_multiples(dfCopy,dfBaseCopy,indexColsCopy,paramDict,chartDict,colorDict,run):
    namingParams=get_naming_params()
    waterfallChart=namingParams["verticalWaterfallChart"] 
    configParams=get_config_params()
    fontSize=configParams[namingParams["fontSizeText"]]  
    font=configParams[namingParams["fontChoice"]]   
    configPlotlyDict=configParams["configPlotlyDict"]
    configPlotlyDict=configPlotlyDict[waterfallChart]
    varianceTypeName=namingParams["varianceTypeName"]
    measureName=namingParams["measureName"]
    workColumn=namingParams["workColumn"]
    varianceAmountName=namingParams["varianceAmountName"]
    mainDimensionKey=namingParams["mainDimension"]
    aggregateOtherWaterfalls=namingParams["aggregateOtherWaterfalls"] 
    varianceAggregation=namingParams["varianceAggregation"]
    plotSmallMultiples=namingParams["plotSmallMultiplesWaterfall"] 
    smallMultiplesWaterfall=namingParams["smallMultiplesWaterfall"]
    numberOfSmallMultiples=namingParams["numberOfSmallMultiplesWaterfall"]
    numberOfPlots=namingParams["numberOfPlots"]
    nothingThereString=namingParams["nothingThereString"]
    waterfallChart=namingParams["verticalWaterfallChart"]
    acName=namingParams["acName"] 
    pyName=namingParams["pyName"]  
    plName=namingParams["plName"]
    monetaryName=namingParams["monetaryLocalCurrencyName"]
    yearBeforePyName=namingParams["yearBeforePyName"]  
    isYearBeforePy=namingParams["isYearBeforePy"]
    selectedPeriods=namingParams["selectedPeriods"]
    workColumn=namingParams["workColumn"] 
    mainDimension=chartDict[mainDimensionKey][0]
    showItems=get_number_of_multiples(dfCopy,mainDimension,chartDict)
    if is_valid_lazyframe(dfCopy): 
        chartDict[smallMultiplesWaterfall]=showItems
        fig,countRows,countCols,count,numberOfCols,numberOfRows=make_one_dimensional_variance_subplots(showItems,numberOfCols=3)
        df=duplicate_dataframe(dfCopy)
        # Use Polars-friendly duplication; avoid pandas .copy()
        dfBase=duplicate_dataframe(dfBaseCopy)
        sortArray=[]
        shapeArray=[]
        periodZeroLineArray=[]
        periodOneLineArray=[]
        arrowArray=[]
        annotationArrowArray=[]
        annotationTextArray=[]
        numberOfCharts=len(showItems)
        paramDict[numberOfPlots]=numberOfCharts
        frameArray=[]
        for element in showItems:
            indexCols=copy.deepcopy(indexColsCopy)  
            dfFiltered,df,indexCols=make_filtered_small_multiple_dataframe(df,mainDimension,element,indexCols,chartDict,count)
            if is_valid_lazyframe(dfFiltered) and element != nothingThereString:               
                  dfFiltered,dfBase,paramDict=prepare_data_for_waterfall(dfFiltered,indexCols,paramDict,chartDict,run,mainDimension,element,dfBase,count)
                  dfFiltered,sortArray=sort_small_multiples(dfFiltered,count,sortArray)
                  figDet,numberFormat,chartDict=draw_vertical_waterfall_chart(dfFiltered,colorDict,paramDict,chartDict,run)
                  fig.add_trace(figDet['data'][0],row=countRows,col=countCols)  
                  fig.update_annotations(font=dict(size=fontSize,family=font))
                  fig=move_labels_up(fig,chartDict,showItems)             
                  shapeArray=make_dic_to_color_first_bar(dfFiltered,paramDict,chartDict,colorDict,run,count,shapeArray)
                  df_lazy_filtered = ensure_lazyframe(dfFiltered)
                  periodOneValue = get_polars_value_at_index(
                      df_lazy_filtered.filter(pl.col(workColumn) == chartDict[selectedPeriods][1]),
                      varianceAmountName,
                      0,
                  )
                  periodZeroValue = get_polars_value_at_index(
                      df_lazy_filtered,
                      varianceAmountName,
                      0,
                  )
                  periodZeroLineArray=make_dic_to_add_line(dfFiltered,paramDict,chartDict,colorDict,run,count,periodZeroLineArray,periodZeroValue,periodZeroValue,numberOfCharts,False,True,countRows)
                  periodOneLineArray=make_dic_to_add_line(dfFiltered,paramDict,chartDict,colorDict,run,count,periodOneLineArray,periodOneValue,periodOneValue,numberOfCharts,False,False,countRows)
                  arrowArray=make_dic_to_add_line(dfFiltered,paramDict,chartDict,colorDict,run,count,arrowArray,periodZeroValue,periodOneValue,numberOfCharts,True,False,countRows)
                  annotationArrowArray=make_dic_to_add_annotation(dfFiltered,paramDict,chartDict,colorDict,run,count,annotationArrowArray,numberOfCharts,False,True,countRows)
                  annotationTextArray=make_dic_to_add_annotation(dfFiltered,paramDict,chartDict,colorDict,run,count,annotationTextArray,numberOfCharts,True,False,countRows)                 
                  if countCols < numberOfCols:
                        countCols=countCols+1
                  else: 
                        countCols=1     
                        countRows=countRows+1
                  count=count+1
                  dfDim=duplicate_dataframe(dfFiltered)
                  # Insert a column in Polars by adding and reordering
                  dfDim = dfDim.with_columns(pl.lit(element).alias(mainDimension))
                  cols, _ = get_schema_and_column_names(dfDim)
                  cols = [mainDimension] + [c for c in cols if c != mainDimension]
                  dfDim = dfDim.select(cols)
                  frameArray.append(dfDim)
        dfExport = pl.concat(frameArray)
        shapeArrayNew=shapeArray+periodZeroLineArray+ periodOneLineArray+arrowArray       
        annotationArrowArrayNew=annotationArrowArray+annotationTextArray
        fig.update_layout(
                shapes=shapeArrayNew,
                annotations=annotationArrowArrayNew
                    )     
        # Avoid pandas-like chained indexing; use Polars-safe accessor
        if plName == get_polars_value_at_index(dfFiltered, workColumn, 0):
            pyName=plName  
        elif isYearBeforePy in paramDict and paramDict[isYearBeforePy]:
            pyName=yearBeforePyName              
        title,paramDict,chartDict=make_vertical_waterfall_chart_title(df,waterfallChart,paramDict,mainDimension,monetaryName,chartDict,pyName,acName)
        fig,width=update_waterfall_layout_small_multiples(dfFiltered,fig,chartDict,numberOfRows,numberOfCols)                             
        fig=reverse_waterfall_y_range(fig) 
        fig,message=get_user_message(fig,waterfallChart,"",plotSmallMultiples,paramDict,chartDict,dfFiltered,width,None)
        fig=add_message_as_annotation(fig,message,None,waterfallChart,chartDict,paramDict)
        fig=add_title_as_annotation(fig,title,waterfallChart,chartDict)
        fig=enable_draw_shapes(fig)
        fig=delete_black_vertical_lines(fig)
        paramDict=set_up_tab_for_show_or_download_chart(dfExport,fig,configPlotlyDict,chartDict,title,True,run,None,paramDict)  
    return paramDict,chartDict 


def plot_kernel_density_charts(dfCopy,indexCols,valueCols,chartDict,dateChoice,paramDict):
    """
    plots distribution charts
    """
    namingParams=get_naming_params()
    configParams=get_config_params()
    kernelDensity=namingParams["kernelDensityChart"]
    nothingFilteredName=namingParams["nothingFilteredName"]
    entireDatasetName=namingParams["entireDatasetName"]
    rowToPlotKey=namingParams["rowToPlotName"]
    smallMultiplesColumnKey=namingParams["smallMultiplesColumn"]
    periodName=namingParams["periodName"]
    numberOfTop=namingParams["numberOfTop"]
    smallMultiplesCharts=namingParams["plotSmallMultiplesOtherCharts"]
    metConditionValue=namingParams["metConditionValue"]
    numberOfPlottedSmallMultiplesKey=namingParams["numberOfPlottedSmallMultiples"]
    xAxisMetric=namingParams["xAxisMetric"]
    chosenChart=namingParams["chosenChart"] 
    configPlotlyDict=configParams["configPlotlyDict"]  
    rowToPlot=chartDict[rowToPlotKey]
    smallMultiplesColumn=chartDict[smallMultiplesColumnKey]  
    chosenChart=chartDict[chosenChart] 
    configPlotlyDict=configPlotlyDict[kernelDensity]      
    indexColsToPlot=copy.deepcopy(indexCols)                              
    if chartDict[namingParams[smallMultiplesColumnKey]]:
      indexColsToPlot=[chartDict[smallMultiplesColumnKey]]
    indexColsToPlot.insert(0,nothingFilteredName)
    if is_valid_lazyframe(dfCopy):
        for element in indexColsToPlot:    
            df=duplicate_dataframe(dfCopy)
            metric=chartDict[xAxisMetric] 
            if element == nothingFilteredName:
                ui.markdown("---")
                colChoice=False
                uniqueItems=[]
            else:      
                df,uniqueItems,aggregateOtherItemsName,valueCols=show_only_largest(df,element,None,periodName,valueCols,chartDict,paramDict,"X")
                numberOfUniques=len(uniqueItems) 
                colChoice=True   
            if metric and element == nothingFilteredName:                         
                df=aggregate_values_in_distribution_plots(df,element,valueCols,chartDict)
                fig,numberOfItemsInCol,cleanedPeriodOrder,dfExport=draw_kernel_density_chart(df,element,metric,colChoice,paramDict,chartDict,uniqueItems)
                period0,period1=check_if_two_periods_in_distribution_chart(cleanedPeriodOrder)
                title,paramDict,chartDict=make_distribution_charts_title(df,chosenChart,paramDict,element,metric,chartDict,period0,period1)               
                fig=update_kernel_density_layout(fig,numberOfItemsInCol)
                fig,message=get_user_message(fig,kernelDensity,"",element,paramDict,chartDict,df,None,None,)
                fig=add_message_as_annotation(fig,message,None,chosenChart,chartDict,paramDict)
                fig=add_title_as_annotation(fig,title,chosenChart,chartDict)
                fig=enable_draw_shapes(fig)  
            elif metric and numberOfUniques > 1:
                chartDict[smallMultiplesCharts]=metConditionValue
                chartDict[numberOfPlottedSmallMultiplesKey]=len(uniqueItems)
                df=aggregate_values_in_distribution_plots(df,element,valueCols,chartDict)
                fig,numberOfItemsInCol,cleanedPeriodOrder,dfExport=draw_kernel_density_chart(df,element,metric,colChoice,paramDict,chartDict,uniqueItems)
                period0,period1=check_if_two_periods_in_distribution_chart(cleanedPeriodOrder)
                title,paramDict,chartDict=make_distribution_charts_title(df,chosenChart,paramDict,element,metric,chartDict,period0,period1)               
                fig=update_kernel_density_layout(fig,numberOfItemsInCol)
                fig,message=get_user_message(fig,kernelDensity,"",element,paramDict,chartDict,df,None,None,)
                fig=add_message_as_annotation(fig,message,None,chosenChart,chartDict,paramDict)
                fig=add_title_as_annotation(fig,title,chosenChart,chartDict)
                fig=enable_draw_shapes(fig)                       
            paramDict=set_up_tab_for_show_or_download_chart(dfExport,fig,configPlotlyDict,chartDict,element+metric,False,None,element,paramDict)                                  
    else:
      paramDict=add_empty_dataset_error_message_in_plot_charts_tab(paramDict)
    return paramDict

def plot_boxplot_charts(dfCopy,indexCols,valueCols,chartDict,dateChoice,paramDict):
    """
    plots histogram charts
    """
    namingParams=get_naming_params()
    configParams=get_config_params()
    boxplotChart=namingParams["boxplotChart"]   
    nothingFilteredName=namingParams["nothingFilteredName"]
    entireDatasetName=namingParams["entireDatasetName"]
    rowToPlot=namingParams["rowToPlotName"]
    periodName=namingParams["periodName"]
    numberOfTop=namingParams["numberOfTop"]
    rowToPlot=chartDict[namingParams["rowToPlotName"]]
    smallMultiplesColumn=chartDict[namingParams["smallMultiplesColumn"]]  
    xAxisMetric=namingParams["xAxisMetric"]
    chosenChart=namingParams["chosenChart"]
    smallMultiplesCharts=namingParams["plotSmallMultiplesOtherCharts"]
    metConditionValue=namingParams["metConditionValue"]
    numberOfPlottedSmallMultiplesKey=namingParams["numberOfPlottedSmallMultiples"]     
    chosenChart=chartDict[chosenChart] 
    configPlotlyDict=configParams["configPlotlyDict"]
    configPlotlyDict=configPlotlyDict[boxplotChart]      
    indexColsToPlot=copy.deepcopy(indexCols)   
    if chartDict[namingParams["smallMultiplesColumn"]]:
      indexColsToPlot=[chartDict[namingParams["smallMultiplesColumn"]]]
    indexColsToPlot.insert(0,nothingFilteredName)
    if is_valid_lazyframe(dfCopy):
      for element in indexColsToPlot:
            df=duplicate_dataframe(dfCopy)      
            metric=chartDict[xAxisMetric] 
            if element == nothingFilteredName:
                ui.markdown("---")
                colChoice=False
                uniqueItems=[]
            else:     
                df,uniqueItems,aggregateOtherItemsName,valueCols=show_only_largest(df,element,None,periodName,valueCols,chartDict,paramDict,"X")
                numberOfUniques=len(uniqueItems) 
                colChoice=True    
            if metric and element == nothingFilteredName or len(uniqueItems) > 1:
                if len(uniqueItems)>1:
                    chartDict[smallMultiplesCharts]=metConditionValue
                    chartDict[numberOfPlottedSmallMultiplesKey]=len(uniqueItems) 
                df=aggregate_values_in_distribution_plots(df,element,valueCols,chartDict)
                fig,numberOfItemsInCol,cleanedPeriodOrder,df1=draw_boxplot_chart(df,element,metric,colChoice,paramDict,chartDict,uniqueItems)
                period0,period1=check_if_two_periods_in_distribution_chart(cleanedPeriodOrder)
                title,paramDict,chartDict=make_distribution_charts_title(df,chosenChart,paramDict,element,metric,chartDict,period0,period1)                
                fig,width=update_boxplot_layout(fig,numberOfItemsInCol)
                fig,message=get_user_message(fig,boxplotChart,"",element,paramDict,chartDict,df,width,None)
                fig=add_message_as_annotation(fig,message,None,chosenChart,chartDict,paramDict)
                fig=add_title_as_annotation(fig,title,chosenChart,chartDict)
                fig=enable_draw_shapes(fig) 
                paramDict=set_up_tab_for_show_or_download_chart(df1,fig,configPlotlyDict,chartDict,element+metric,False,None,element,paramDict)                      
    else:
      paramDict=add_empty_dataset_error_message_in_plot_charts_tab(paramDict)
    return paramDict      

def plot_stripplot_charts(dfCopy,indexCols,valueCols,chartDict,dateChoice,paramDict):
    """
    plots histogram charts
    """
    namingParams=get_naming_params()
    configParams=get_config_params()
    stripplotChart=namingParams["stripplotChart"]    
    nothingFilteredName=namingParams["nothingFilteredName"]
    entireDatasetName=namingParams["entireDatasetName"]
    rowToPlot=namingParams["rowToPlotName"]
    periodName=namingParams["periodName"]
    numberOfTop=namingParams["numberOfTop"]
    rowToPlot=chartDict[namingParams["rowToPlotName"]]
    smallMultiplesColumn=chartDict[namingParams["smallMultiplesColumn"]]  
    xAxisMetric=namingParams["xAxisMetric"]
    chosenChart=namingParams["chosenChart"]
    smallMultiplesCharts=namingParams["plotSmallMultiplesOtherCharts"]
    metConditionValue=namingParams["metConditionValue"]
    numberOfPlottedSmallMultiplesKey=namingParams["numberOfPlottedSmallMultiples"]       
    chosenChart=chartDict[chosenChart]     
    configPlotlyDict=configParams["configPlotlyDict"]
    configPlotlyDict=configPlotlyDict[stripplotChart]      
    indexColsToPlot=copy.deepcopy(indexCols)                              
    if chartDict[namingParams["smallMultiplesColumn"]]:
      indexColsToPlot=[chartDict[namingParams["smallMultiplesColumn"]]]
    indexColsToPlot.insert(0,nothingFilteredName)
    if is_valid_lazyframe(dfCopy):
      for element in indexColsToPlot:
            df=duplicate_dataframe(dfCopy)      
            metric=chartDict[xAxisMetric] 
            if element == nothingFilteredName:
                ui.markdown("---")
                colChoice=False
                uniqueItems=[]
            else:      
                df,uniqueItems,aggregateOtherItemsName,valueCols=show_only_largest(df,element,None,periodName,valueCols,chartDict,paramDict,"X")
                numberOfUniques=len(uniqueItems) 
                colChoice=True    
            if metric and element == nothingFilteredName or numberOfUniques > 1:
                if len(uniqueItems)>1:
                    chartDict[smallMultiplesCharts]=metConditionValue
                    chartDict[numberOfPlottedSmallMultiplesKey]=len(uniqueItems)
                df=aggregate_values_in_distribution_plots(df,element,valueCols,chartDict)
                fig,numberOfItemsInCol,cleanedPeriodOrder,dfExport=draw_stripplot_chart(df,element,metric,colChoice,paramDict,chartDict,uniqueItems)
                period0,period1=check_if_two_periods_in_distribution_chart(cleanedPeriodOrder)
                title,paramDict,chartDict=make_distribution_charts_title(df,chosenChart,paramDict,element,metric,chartDict,period0,period1)               
                fig=update_stripplot_layout(fig,numberOfItemsInCol)
                fig,message=get_user_message(fig,stripplotChart,"",element,paramDict,chartDict,df,None,None,)
                fig=add_message_as_annotation(fig,message,None,chosenChart,chartDict,paramDict)
                fig=add_title_as_annotation(fig,title,chosenChart,chartDict)
                fig=enable_draw_shapes(fig)                
                paramDict=set_up_tab_for_show_or_download_chart(dfExport,fig,configPlotlyDict,chartDict,element+metric,False,None,element,paramDict)           
    else:
      paramDict=add_empty_dataset_error_message_in_plot_charts_tab(paramDict)
    return paramDict    

def plot_multitier_bar_chart(dfCopy,indexCols,valueCols,chartDict,valueColsWithPrice,xColumn,paramDictCopy,dfDict):
    namingParams=get_naming_params()
    configParams=get_config_params()
    chosenChart=namingParams["chosenChart"]
    metricsToPlot=namingParams["metricsToPlot"]
    singleMetric=namingParams["singleMetric"]
    chosenChart=namingParams["chosenChart"] 
    periodName=namingParams["periodName"]    
    workColumn=namingParams["workColumn"] 
    periodChoice=namingParams["periodChoice"]      
    weekName=namingParams["weekName"]  
    totalName=namingParams["totalName"]   
    acName=namingParams["acName"]   
    pyName=namingParams["pyName"]  
    selectedPeriods=namingParams["selectedPeriods"]  
    selectDimensionsToPlot=namingParams["selectDimensionsToPlot"]
    plotSmallMultiplesKey=namingParams["plotSmallMultiplesOtherCharts"] 
    datePeriodName=namingParams["datePeriodName"]
    weekName=namingParams["weekName"] 
    monthName=namingParams["monthName"]          
    quarterName=namingParams["quarterName"] 
    periodToDate=namingParams["periodToDate"] 
    setTimePeriodTabLabel=namingParams["setTimePeriodTabLabel"]  
    columnsToPlot=chartDict[selectDimensionsToPlot]  
    chosenChart=chartDict[chosenChart]  
    metricsToPlot=chartDict[metricsToPlot] 
    periodOrder=chartDict[selectedPeriods] 
    paramDict=copy.deepcopy(paramDictCopy)      
    if is_valid_lazyframe(dfCopy):
        df=duplicate_dataframe(dfCopy)
        df,indexCols=add_totals_column(df,indexCols)
        columnsToPlot.insert(0,totalName) 
        count=0
        countNoTotal=0
        for column in indexCols:   
            if df.get_column(column).n_unique() > 0 and column in columnsToPlot:
                valueColsWithPrice=add_price_to_value_cols(valueCols,df) 
                if column == totalName:
                    paramDict=draw_multitier_bar_chart(df,column,xColumn,metricsToPlot,valueColsWithPrice,paramDict,chartDict)
                elif (plotSmallMultiplesKey not in chartDict or not chartDict[plotSmallMultiplesKey]): 
                    paramDict=draw_multitier_bar_chart(df,column,xColumn,[metricsToPlot[0]],valueColsWithPrice,paramDict,chartDict)    
                elif plotSmallMultiplesKey in chartDict and chartDict[plotSmallMultiplesKey] and countNoTotal==0: 
                    paramDict=draw_multitier_bar_chart(df,column,xColumn,[metricsToPlot[0]],valueColsWithPrice,paramDict,chartDict)
                    countNoTotal=countNoTotal+1                                                         
                count=count+1
        if count==0:
            paramDict=add_empty_dataset_error_message_in_plot_charts_tab(paramDict)
    else: 
      paramDict=add_empty_dataset_error_message_in_plot_charts_tab(paramDict)        
    return paramDict


def plot_stacked_column_charts(dfCopy,indexCols,valueCols,chartDict,valueColsWithPrice,xColumn,paramDict,dfDict):
    """
    plots by period chart
    """
    namingParams=get_naming_params()
    configParams=get_config_params()
    metricArrayParams=get_metric_array_params()
    priceMetricsArray=metricArrayParams[namingParams["priceMetricsArray"]]
    percentMetricsArray=metricArrayParams[namingParams["percentMetricsArray"]]
    growthMetricArray=metricArrayParams[namingParams["growthMetricArray"]]
    valueMetricsArray=metricArrayParams[namingParams["valueMetricsArray"]]
    volumeMetricsArray=metricArrayParams[namingParams["volumeMetricsArray"]]
    noSumMetricsArray=metricArrayParams[namingParams["noSumMetricsArray"]] 
    uniformTextMinSize = get_uniform_text_min_size(configParams, namingParams)
    noSumMetricsArray=namingParams["noSumMetricsArray"] 
    noSumMetricsArray=metricArrayParams[noSumMetricsArray] 
    plotValuesAsChoice=namingParams["plotValuesAsChoice"]
    percentOfResultRow=namingParams["percentOfResultRow"]
    absolute=namingParams["absolute"]    
    chosenChart=namingParams["chosenChart"]
    metricsToPlot=namingParams["metricsToPlot"]
    periodName=namingParams["periodName"]   
    dateName=namingParams["dateName"]     
    workColumn=namingParams["workColumn"] 
    periodChoice=namingParams["periodChoice"]    
    quarterName=namingParams["quarterName"]    
    weekName=namingParams["weekName"]  
    totalName=namingParams["totalName"]     
    chosenChart=chartDict[chosenChart]
    configPlotlyDict=configParams["configPlotlyDict"]
    smallMultiplesColumn=namingParams["smallMultiplesColumn"]
    selectDimensionsToPlot=namingParams["selectDimensionsToPlot"]
    pricePerUnitName=namingParams["pricePerUnitName"]
    pricePerVolumeName=namingParams["pricePerVolumeName"]
    stackedColumnMetric=namingParams["stackedColumnMetric"]
    countMetricsAvgArrayKey=namingParams["countMetricsAvgArray"]
    countMetricsSumArrayKey=namingParams["countMetricsSumArray"]
    dfAllPeriodsName=namingParams["dfAllPeriodsName"]
    plotSmallMultiplesKey=namingParams["plotSmallMultiplesOtherCharts"] 
    datePeriodName=namingParams["datePeriodName"]
    weekName=namingParams["weekName"] 
    monthName=namingParams["monthName"]          
    quarterName=namingParams["quarterName"] 
    periodToDate=namingParams["periodToDate"] 
    setTimePeriodTabLabel=namingParams["setTimePeriodTabLabel"]   
    scenarioName=namingParams["scenarioName"]
    plName=namingParams["plName"] 
    summaryStackedColumnChart=namingParams["summaryStackedColumnChart"] 
    canPlot=True
    frameArray=[]
    if datePeriodName in chartDict and chartDict[datePeriodName] in [weekName,monthName,quarterName]:
        if periodToDate in chartDict and chartDict[periodToDate]:
            canPlot=False      
    countMetricsAvgArray=[]
    if countMetricsAvgArrayKey in chartDict:
        countMetricsAvgArray=chartDict[countMetricsAvgArrayKey]
    countMetricsSumArray=[]
    if countMetricsSumArrayKey in chartDict:
        countMetricsSumArray=chartDict[countMetricsSumArrayKey]
    metricsToPlot=chartDict[metricsToPlot]
    columnsToPlot=chartDict[selectDimensionsToPlot]
    configPlotlyDict=configPlotlyDict[chosenChart]  
    count=0
    if is_valid_lazyframe(dfCopy) and canPlot: 
      ui.markdown("---")   
      if chartDict[plotValuesAsChoice] != percentOfResultRow:
            dfCopy,indexCols=add_totals_column(dfCopy,indexCols)   
            columnsToPlot.insert(0,totalName)
      synColumnArray=[]
      synColorArray=[]
      timeColumn=periodName
      columnsArray,schema=get_schema_and_column_names(dfCopy)
      # Ensure we only use metrics that exist in the dataframe
      valueCols = check_value_column_exist(dfCopy, valueCols)
      fullFig=False
      metricType=False   
      if scenarioName in columnsArray:
        dfCopy = dfCopy.with_columns(
            pl.when(pl.col(scenarioName) == pl.lit(plName))
            .then(pl.col(periodName) + "<br>" + plName)
            .otherwise(pl.col(periodName))
            .alias(periodName)
        )
      plotted_any = False
      missing_dimensions: list[str] = []
      for column in columnsToPlot:
        df=duplicate_dataframe(dfCopy)
        # Skip silently if the selected dimension is not available in dfPeriods
        if column in indexCols and column in columnsArray:
            group_byCols=[column,xColumn]
            dfCounts,chartDict=get_number_of_uniques(df,column,timeColumn,chartDict)
            df = (
                    df
                    .group_by(group_byCols)          # group_by columns
                    .agg([pl.col(col).sum() for col in valueCols])  # aggregate
                ) 
            numberOfItemsInCol = n_unique_lazy(column, df)
            check_collect("AAP", "numberOfItemsInCol",numberOfItemsInCol)
            if is_valid_lazyframe(df):
                df,uniqueItems,aggregateOtherItemsName,valueCols=show_only_largest(df,column,None,timeColumn,valueCols,chartDict,paramDict,"X")
                df=join_unique_metric_to_df(df,dfCounts,column,timeColumn,aggregateOtherItemsName,chartDict)
                df=insert_unit_and_volume_price_column(df)
                if is_valid_lazyframe(df):   
                    df,paramDict,valueColsWithPrice=process_if_promo_data(df,paramDict,valueColsWithPrice) 
                    if plotValuesAsChoice in chartDict and chartDict[plotValuesAsChoice] != absolute:
                        dfAbsolute=duplicate_dataframe(df)
                        chartDict[absolute]=dfAbsolute
                        df=compute_share_of_total(df,xColumn,column,valueCols,chartDict,dfDict,"mean",paramDict)
                    else:
                        dfAbsolute = pl.DataFrame()
                    if column==totalName and chartDict[plotValuesAsChoice] ==absolute and (len(metricsToPlot)>1 or len(columnsToPlot)==1):   
                        fullFig,metricType,df1,chartDict,paramDict=draw_stacked_column_chart(df,column,xColumn,metricsToPlot,metricsToPlot,paramDict,chartDict,uniqueItems,aggregateOtherItemsName,fullFig,metricType,columnsToPlot)
                        plotted_any = True
                    elif column != totalName and (plotSmallMultiplesKey not in chartDict or not chartDict[plotSmallMultiplesKey]) and (metricsToPlot[0] not in noSumMetricsArray):
                        if metricsToPlot[0] not in percentMetricsArray+countMetricsAvgArray:
                            fullFig,metricType,df2,chartDict,paramDict=draw_stacked_column_chart(df,column,xColumn,[metricsToPlot[0]],uniqueItems,paramDict,chartDict,uniqueItems,aggregateOtherItemsName,fullFig,metricType,columnsToPlot)   
                            if len(columnsToPlot)>2:
                                count,frameArray,synColumnArray,synColorArray,leastRecentPeriod,mostRecentPeriod=prepare_data_for_syn_plot(df2,column,uniqueItems,aggregateOtherItemsName,frameArray,synColumnArray,synColorArray,count,paramDict,chartDict)                                  
                            plotted_any = True
                    elif plotSmallMultiplesKey in chartDict and chartDict[plotSmallMultiplesKey]:
                        fullFig,metricType,df2,chartDict,paramDict=draw_stacked_column_chart(df,column,xColumn,[metricsToPlot[0]],uniqueItems,paramDict,chartDict,uniqueItems,aggregateOtherItemsName,fullFig,metricType,columnsToPlot)   
                        plotted_any = True
                else:
                    paramDict=add_empty_dataset_error_message_in_plot_charts_tab(paramDict)
        # If the dimension is missing, skip without raising an error for every item
        else:
            if column not in missing_dimensions:
                missing_dimensions.append(column)
      if not plotted_any:
          if missing_dimensions:
              message = (
                  "Dimension column or metric column not in dataset: "
                  + ", ".join(missing_dimensions)
                  + ". Available columns: "
                  + ", ".join(columnsArray)
              )
          else:
              message="Dimension column or metric column not in dataset."
          logger.error(
              "plot-charts: missing dimensions=%s available=%s indexCols=%s value_cols=%s",
              missing_dimensions,
              columnsArray,
              indexCols,
              valueCols,
          )
          paramDict=add_error_message_in_plot_charts_tab(paramDict,message)
    elif not canPlot:
        message="Cannot plot Period to Date if date aggregation set to quarter, month or week. Change setting in the "+setTimePeriodTabLabel+" tab."
        paramDict=add_error_message_in_plot_charts_tab(paramDict,message)
    else:         
        paramDict=add_empty_dataset_error_message_in_plot_charts_tab(paramDict)

    if len(frameArray) > 1 and metricsToPlot[0] not in priceMetricsArray: 
        if plotSmallMultiplesKey not in chartDict or not chartDict[plotSmallMultiplesKey]:
            chartDict[stackedColumnMetric]=metricsToPlot[0] 
            dfExport=make_syn_plot_comment_dataset(frameArray,chartDict) 
            dfSyn,synColorArray,chartDict,synColumnArray=aggregate_syn_plot_data(chartDict,metricsToPlot[0],frameArray,synColumnArray,aggregateOtherItemsName,synColorArray,mostRecentPeriod,paramDict)   
            title,paramDict,chartDict=make_stacked_column_chart_title(dfSyn,chosenChart,paramDict,"dimension",metricsToPlot[0],chartDict,mostRecentPeriod,None)
            dfSyn=add_by_to_syn_plot_col_labels(dfSyn)
            synColumnArray=[f"by {column}" for column in synColumnArray]
            fig,dfNegative,message,chartDict=stacked_bar_width_plot(dfSyn,chartDict,paramDict,synColumnArray, width_col=None, colors=synColorArray)  
            key=column+metricsToPlot[0]+'syn'
            fig=adjust_stacked_column_plot(fig,dfSyn,key,metricsToPlot[0],title,paramDict,chartDict)
            hashkey=frameArray+[metricsToPlot[0]]
            configPlotlyDict=configParams["configPlotlyDict"]
            configPlotlyDict=configPlotlyDict[summaryStackedColumnChart]
            paramDict=set_up_tab_for_show_or_download_chart(dfExport,fig,configPlotlyDict,chartDict,hashkey,False,None,column,paramDict)     
    return paramDict

# fmt: on
