import logging
# fmt: off
# isort: skip_file
import polars as pl
from modules.utilities.ui_notifier import ui
from modules.utilities.session_context import session_state
import logging

from modules.charting.chart_primitives import (
    change_array_of_metrics_if_cost_analysis,
    change_metric_if_cost_analysis,
)
from modules.data.common_data_utils import (
    check_if_other_in_columns,
    check_if_other_in_rows,
    rank_others_as_last,
)
from modules.layout.memoization import get_hashed_key
from modules.llm.chart_interpretation_prompts import (
    get_barmekko_prompt,
    get_horizontal_waterfall_prompt,
    get_marimekko_prompt,
    get_multitier_bar_prompt,
    get_stacked_bar_prompt,
    get_stacked_column_prompt,
    get_stacked_pareto_prompt,
    get_timeline_chart_prompt,
)
from modules.llm.prompt_builders import (
    add_prompt_date,
    add_prompt_filter,
)
from modules.llm.prompt_helpers import (
    explain_currency_and_abbreviations,
    get_context,
    traslate_ibcs_period_symbols,
)
from modules.llm.ui_helpers import upload_plot_image
from modules.utilities.config import (
    get_naming_params,
    get_variance_aggregation_params,
)
from modules.utilities.error_messages import add_app_message_to_paramdict
from modules.utilities.helpers import (
    change_column_names_if_cost_analysis,
    drop_columns,
    duplicate_dataframe,
    print_error_details,
    replace_ibcs_date_symbol,
    unique,
)
from modules.layout.layout_helpers import make_three_col_width_array
from modules.utilities.utils import (
    get_schema_and_column_names,
    is_valid_lazyframe,
    ensure_polars_df,
)


def clean_dataframe_for_Ai(dfCopy,metric,column,chartDict):
    namingParams=get_naming_params()
    countName=namingParams["countName"]
    absolute=namingParams["absolute"]
    plotValuesAsChoice=namingParams["plotValuesAsChoice"]
    periodName=namingParams["periodName"]
    synthesisPlot=namingParams["synthesisPlot"]
    metricsToPlot=namingParams["metricsToPlot"]
    plotSmallMultiplesKey=namingParams["plotSmallMultiplesOtherCharts"]
    plotOverlayChart=namingParams["plotOverlayChart"]  
    df=duplicate_dataframe(dfCopy)
    if not isinstance(df, pl.DataFrame):
        df = pl.DataFrame(df)
    if not isinstance(df, pl.DataFrame):
        df = pl.DataFrame(df)
    if not isinstance(df, pl.DataFrame):
        df = pl.DataFrame(df)
    if not isinstance(df, pl.DataFrame):
        df = pl.DataFrame(df)
    if plotValuesAsChoice in chartDict and chartDict[plotValuesAsChoice] ==absolute:
        if plotSmallMultiplesKey in chartDict and chartDict[plotSmallMultiplesKey]:
            if metricsToPlot in chartDict and len(chartDict[metricsToPlot])==2 and plotOverlayChart in chartDict and chartDict[plotOverlayChart]:
                pass
            else:
                toKeep=[metric,column,periodName]
                toDrop=[]
                columns,schema=get_schema_and_column_names(df)
                for column in columns:
                    if column not in toKeep:
                        toDrop.append(column)           
                df=drop_columns(df,toDrop)
        elif metricsToPlot in chartDict and len(chartDict[metricsToPlot])==2 and plotOverlayChart in chartDict and chartDict[plotOverlayChart]:
            pass
        else:
            df=drop_columns(df,[countName,metric])  
    else:
        df=drop_columns(df,[countName,metric])
    if synthesisPlot in chartDict and chartDict[synthesisPlot]:
        df = df.with_columns([
            pl.when(pl.col(c) == 0).then("").otherwise(pl.col(c)).alias(c)
            for c in get_schema_and_column_names(df)[0]
        ])
    else:
        df = df.fill_null(0)
        df = df.with_columns([
            pl.when(pl.col(c) == 0).then("").otherwise(pl.col(c)).alias(c)
            for c in get_schema_and_column_names(df)[0]
        ])
    return df


def check_if_period(chartDict):
    namingParams=get_naming_params()
    periodChoice=namingParams["periodChoice"]
    if periodChoice in chartDict and chartDict[periodChoice]:
        pass
    else:
        chartDict[periodChoice]=""
    return chartDict

def extract_non_blank_rows(dfCopy):
    namingParams = get_naming_params()
    varianceType = namingParams["varianceTypeName"]
    df = duplicate_dataframe(dfCopy)
    if not isinstance(df, pl.DataFrame):
        df = pl.DataFrame(df)
    # Use helper to get columns and select explicitly (avoid pandas-style 2D indexing)
    columns, _schema = get_schema_and_column_names(df)
    varianceIndex = columns.index(varianceType)
    selected_cols = columns[:varianceIndex]
    # Exclude first and last rows, keeping length non-negative
    length = max(df.height - 2, 0)
    df = df.slice(1, length).select(selected_cols)
    nonBlankRowsArray = []
    for row in df.iter_rows(named=True):
        rowDict = {k: v for k, v in row.items() if v not in [None, ""]}
        if rowDict:
            nonBlankRowsArray.append(rowDict)
    return nonBlankRowsArray

def rename_metric_for_AI(df,paramDict,chartDict):
    namingParams=get_naming_params()
    greenToRed=namingParams["greenToRed"]
    colorChoice=namingParams["colorChoice"]
    metricsToPlot=namingParams["metricsToPlot"]
    singleMetric=namingParams["singleMetric"]
    chosenChart=namingParams["chosenChart"]
    stackedBarChart=namingParams["stackedBarChart"]
    stackedColumnChart=namingParams["stackedColumnChart"]
    valueName=namingParams["valueName"]
    totalName=namingParams["totalName"]
    costsName=namingParams["costsName"]
    periodName=namingParams["periodName"]
    dimensionName=namingParams["dimensionName"]
    synthesisPlot=namingParams["synthesisPlot"]
    monetaryLocalCurrencyName=namingParams["monetaryLocalCurrencyName"] 
    overlayChartMetricKey=namingParams["overlayChartMetric"] 
    overlayChartFullDfKey=namingParams["overlayChartFullDf"]
    overlayChartDfKey=namingParams["overlayChartDf"] 
    overlayChartDimensionKey=namingParams["overlayChartDimension"] 
    xAxisDimensionKey=namingParams["xAxisDimension"]
    smallMultiplesColumnKey=namingParams["smallMultiplesColumn"]
    valueName=namingParams["valueName"]
    if not isinstance(df, pl.DataFrame):
        df = pl.DataFrame(df)
    if metricsToPlot in chartDict:        
        metric=chartDict[metricsToPlot][0]
    elif singleMetric in chartDict:        
        metric=chartDict[singleMetric]
    if chartDict[colorChoice] in [greenToRed] and metric in [monetaryLocalCurrencyName]:
        metric=costsName
    if chartDict[chosenChart] in [stackedBarChart]:
        columns, schema = get_schema_and_column_names(df)
        if valueName in columns and metric in columns:
            df = drop_columns(df, [valueName])
    else:
        metric = metric.lower()
        df = df.rename({valueName: metric})

    if synthesisPlot in chartDict and chartDict[synthesisPlot]:
        df = df.rename({periodName: dimensionName})

    if overlayChartMetricKey in chartDict and (
        overlayChartFullDfKey in chartDict or overlayChartDfKey in chartDict
    ):
        df = df.rename({totalName: metric})
        if (
            overlayChartDimensionKey in chartDict
            and chartDict[overlayChartDimensionKey] not in [totalName]
            and chartDict[chosenChart] in [stackedBarChart]
        ):
            df2 = chartDict[overlayChartFullDfKey]
            if not isinstance(df2, pl.DataFrame):
                df2 = pl.DataFrame(df2)
            df = pl.DataFrame(df).join(
                df2,
                on=[chartDict[xAxisDimensionKey], chartDict[smallMultiplesColumnKey]],
                how="left",
            )
        elif (
            overlayChartMetricKey in chartDict
            and overlayChartDfKey in chartDict
            and chartDict[chosenChart] in [stackedColumnChart, stackedBarChart]
        ):
            df2 = chartDict[overlayChartDfKey]
            df = pl.concat([pl.DataFrame(df), pl.DataFrame(df2)], how="horizontal")
    return df,metric

def get_area_prompt(df,chartDict):
    if not isinstance(df, pl.DataFrame):
        df = pl.DataFrame(df)
    namingParams=get_naming_params()
    yAxisDimension=namingParams["yAxisDimension"]
    areaChart=namingParams["areaChart"]
    positionLegends=namingParams["positionLegends"]
    nothingFilteredName=namingParams["nothingFilteredName"]
    showAverageValue=namingParams["showAverageValueName"]  
    smallMultiplesCharts=namingParams["plotSmallMultiplesOtherCharts"]
    smallMultiplesColumn=namingParams["smallMultiplesColumn"]
    aggregateOtherItemsName=namingParams["aggregateOtherItemsName"]
    showValuesAs=namingParams["showValuesAs"] 
    metricsToPlot=namingParams["metricsToPlot"] 
    plotValuesAsChoice=namingParams["plotValuesAsChoice"]
    absolute=namingParams["absolute"] 
    numberOfTop=namingParams["numberOfTop"]
    selectedPeriods=namingParams["selectedPeriods"]
    selectDimensionsToPlot=namingParams["selectDimensionsToPlot"]   
    numberOfPlottedSmallMultiplesKey=namingParams["numberOfPlottedSmallMultiples"]
    plotTitleText=namingParams["plotTitleText"]    
    title=chartDict[plotTitleText]
    title=title.replace("<BR>"," ")
    promptDescription="""The **"""+areaChart+"""** chart shows the evolution of """+chartDict[metricsToPlot][0]+""" by """+chartDict[selectDimensionsToPlot][1]+""" over time. For clarity, only the first, last, highest and lowest values of each """+areaChart+""" chart are labeled. """
    promptChart=""
    promptOtherColumn=""
    promptNormalized=""
    if 1==1:
        promptOther=""
        promptAverage=""
        isOtherColumnRank=check_if_other_in_columns(df)
        if isOtherColumnRank:
            otherRank="x"
            if 'X' in chartDict:
                otherRank=str(chartDict["X"][numberOfTop])
                promptOther=""" The smaller """+chartDict[selectDimensionsToPlot][1]+""" items are aggregated together in a '"""+aggregateOtherItemsName+""" """+otherRank+"""' element."""
        if plotValuesAsChoice in chartDict and chartDict[plotValuesAsChoice] != absolute:
            promptNormalized=""" All values are normalized and shown in percent."""
        if smallMultiplesCharts in chartDict and chartDict[smallMultiplesCharts] and smallMultiplesColumn in chartDict:
            promptChart="""This image shows a IBCS **"""+areaChart+"""** chart, with """+str(chartDict[numberOfPlottedSmallMultiplesKey])+""" small multiples plots plotted by """+chartDict[smallMultiplesColumn]+""". """+promptDescription+""". """
        else:
            promptChart="""This image shows a IBCS **"""+areaChart+"""** chart. """+promptDescription+""" Legends are positioned """+chartDict[positionLegends]+""" of plots.""" 
    promptFact=""" Only provide fact-based evidences that can be derived from the data presented to you. Do not make inferences or assumptions beyond the data presented in the chart."""   
    promptChart=promptChart+promptNormalized+promptOther+promptFact        
    return promptChart


def get_strip_plot_prompt(df,chartDict):
    if not isinstance(df, pl.DataFrame):
        df = pl.DataFrame(df)
    namingParams=get_naming_params()
    yAxisDimension=namingParams["yAxisDimension"] 
    xAxisDimension=namingParams["xAxisDimension"]    
    stripplotChart=namingParams["stripplotChart"] 
    nothingFilteredName=namingParams["nothingFilteredName"]
    xAxisMetric=namingParams["xAxisMetric"]
    showAverageValue=namingParams["showAverageValueName"]  
    smallMultiplesCharts=namingParams["plotSmallMultiplesOtherCharts"]
    smallMultiplesColumn=namingParams["smallMultiplesColumn"]
    aggregateOtherItemsName=namingParams["aggregateOtherItemsName"]
    showValuesAs=namingParams["showValuesAs"] 
    absolute=namingParams["absolute"] 
    numberOfTop=namingParams["numberOfTop"]
    selectedPeriods=namingParams["selectedPeriods"]
    plotTitleText=namingParams["plotTitleText"]    
    #title=chartDict[plotTitleText]
    #title=title.replace("<BR>"," ")        
    numberOfPlottedSmallMultiplesKey=namingParams["numberOfPlottedSmallMultiples"]
    promptDescription="""The **"""+stripplotChart+"""** chart is a scatter plot where the x axis represents a categorical variable. 
                    A small random jitter value is applied to each data point such that the separation between points becomes clearer. """
    promptChart=""
    promptOtherColumn=""
    if 1==1:
        promptOther=""
        promptAverage=""
        aggregationDimension=chartDict[xAxisDimension]
        if chartDict[xAxisDimension] in [None, nothingFilteredName]:
            aggregationDimension="observation"
        if smallMultiplesCharts not in chartDict or not chartDict[smallMultiplesCharts]:
            promptChart="""This image shows a **"""+stripplotChart+"""** chart in """+chartDict[xAxisMetric]+""" aggregated by """+aggregationDimension+""". """+promptDescription+""" The darker """+stripplotChart+""" chart shows the """+chartDict[selectedPeriods][1]+""" period data while the lighter """+stripplotChart+""" chart shows the """+chartDict[selectedPeriods][0]+""" period data.""" 
        elif smallMultiplesCharts in chartDict and chartDict[smallMultiplesCharts] and smallMultiplesColumn in chartDict:
            promptChart="""This image shows a **"""+stripplotChart+"""** chart in  """+chartDict[xAxisMetric]+""" aggregated by """+aggregationDimension+""", with """+str(chartDict[numberOfPlottedSmallMultiplesKey])+""" small multiples plots plotted by """+chartDict[smallMultiplesColumn]+""". """+promptDescription+""" The darker """+stripplotChart+""" charts show the """+chartDict[selectedPeriods][1]+""" period data while the lighter """+stripplotChart+""" charts show the """+chartDict[selectedPeriods][0]+""" period data."""                
    promptFact=""" Only provide fact-based evidences that can be derived from the data presented to you. Do not make inferences or assumptions beyond the data presented in the chart."""   
    promptChart=promptChart+promptFact          
    return promptChart


def get_kernel_density_prompt(df,chartDict,fileName):
    if not isinstance(df, pl.DataFrame):
        df = pl.DataFrame(df)
    namingParams=get_naming_params()
    yAxisDimension=namingParams["yAxisDimension"] 
    xAxisDimension=namingParams["xAxisDimension"]    
    kernelDensity=namingParams["kernelDensityChart"] 
    nothingFilteredName=namingParams["nothingFilteredName"]
    xAxisMetric=namingParams["xAxisMetric"]
    showAverageValue=namingParams["showAverageValueName"]  
    smallMultiplesCharts=namingParams["plotSmallMultiplesOtherCharts"]
    smallMultiplesColumn=namingParams["smallMultiplesColumn"]
    aggregateOtherItemsName=namingParams["aggregateOtherItemsName"]
    showValuesAs=namingParams["showValuesAs"] 
    absolute=namingParams["absolute"] 
    numberOfTop=namingParams["numberOfTop"]
    plotTitleText=namingParams["plotTitleText"]    
    #title=chartDict[plotTitleText]
    #title=title.replace("<BR>"," ")       
    numberOfPlottedSmallMultiplesKey=namingParams["numberOfPlottedSmallMultiples"]
    promptDescription="""The **"""+kernelDensity+"""** chart shows the distribution of numerical data."""
    promptChart=""
    promptOtherColumn=""
    promptContext,companyOrIndustry,contextMetric=get_context(chartDict,chartDict[xAxisMetric])
    firstPeriod,secondPeriod=traslate_ibcs_period_symbols(chartDict) 
    title=chartDict[plotTitleText]
    title=replace_ibcs_date_symbol(title,chartDict)
    isSmallMultiples=False
    if fileName.count("__") == 2:
        isSmallMultiples=True
    if not isSmallMultiples:
        toReplace="by "+chartDict[smallMultiplesColumn]
        title=title.replace(toReplace,"")
    promptOther=""
    promptAverage=""
    aggregationDimension=chartDict[xAxisDimension]
    if chartDict[xAxisDimension] in [None, nothingFilteredName]:
        aggregationDimension="observation"
    if isSmallMultiples:
        promptChart="""This image shows a **"""+kernelDensity+"""** chart with the following title: '"""+title+""". The chart plots  """+contextMetric+""" aggregated by """+aggregationDimension+""", with """+str(chartDict[numberOfPlottedSmallMultiplesKey])+""" small multiples plots plotted by """+chartDict[smallMultiplesColumn]+""". """+promptDescription+""" The darker """+kernelDensity+""" charts show the """+secondPeriod+""" period data while the lighter """+kernelDensity+""" charts show the """+firstPeriod+""" period data."""                

    else:
        promptChart="""This image shows a **"""+kernelDensity+"""** chart with the following title: '"""+title+""". The chart plots """+contextMetric+""" aggregated by """+aggregationDimension+""". """+promptDescription+""" The darker """+kernelDensity+""" chart shows the """+secondPeriod+""" period data while the lighter """+kernelDensity+""" chart shows the """+firstPeriod+""" period data.""" 
    promptFact=""" Only provide fact-based evidences that can be derived from the data presented to you. Do not make inferences or assumptions beyond the data presented in the chart."""   
    promptChart=promptChart+promptFact          
    return promptChart

def get_histogram_chart_prompt(df,chartDict):
    if not isinstance(df, pl.DataFrame):
        df = pl.DataFrame(df)
    namingParams=get_naming_params()
    yAxisDimension=namingParams["yAxisDimension"] 
    xAxisDimension=namingParams["xAxisDimension"]    
    histogramChart=namingParams["histogramChart"] 
    nothingFilteredName=namingParams["nothingFilteredName"]
    xAxisMetric=namingParams["xAxisMetric"]
    showAverageValue=namingParams["showAverageValueName"]  
    smallMultiplesCharts=namingParams["plotSmallMultiplesOtherCharts"]
    smallMultiplesColumn=namingParams["smallMultiplesColumn"]
    aggregateOtherItemsName=namingParams["aggregateOtherItemsName"]
    showValuesAs=namingParams["showValuesAs"] 
    absolute=namingParams["absolute"] 
    numberOfTop=namingParams["numberOfTop"]
    selectedPeriods=namingParams["selectedPeriods"]    
    numberOfPlottedSmallMultiplesKey=namingParams["numberOfPlottedSmallMultiples"]
    plotTitleText=namingParams["plotTitleText"]    
    #title=chartDict[plotTitleText]
    #title=title.replace("<BR>"," ")
    promptDescription="""The **"""+histogramChart+"""** chart is a representation of the distribution of numerical data 
                    (for example prices), where the data are binned and the count for each bin is represented by the height of each column."""
    promptChart=""
    promptOtherColumn=""
    if 1==1:
        promptOther=""
        promptAverage=""
        aggregationDimension=chartDict[xAxisDimension]
        if chartDict[xAxisDimension] in [None, nothingFilteredName]:
            aggregationDimension="observation"
        if smallMultiplesCharts not in chartDict or not chartDict[smallMultiplesCharts]:
            promptChart="""This image shows a **"""+histogramChart+"""** chart in """+chartDict[xAxisMetric]+""" aggregated by """+aggregationDimension+""". """+promptDescription+""" The darker """+histogramChart+""" chart shows the """+chartDict[selectedPeriods][1]+""" period data while the lighter """+histogramChart+""" chart shows the """+chartDict[selectedPeriods][0]+""" period data.""" 
        elif smallMultiplesCharts in chartDict and chartDict[smallMultiplesCharts] and smallMultiplesColumn in chartDict:
            promptChart="""This image shows a **"""+histogramChart+"""** chart in  """+chartDict[xAxisMetric]+""" aggregated by """+aggregationDimension+""", with """+str(chartDict[numberOfPlottedSmallMultiplesKey])+""" small multiples plots plotted by """+chartDict[smallMultiplesColumn]+""". """+promptDescription+""" The darker """+histogramChart+""" charts show the """+chartDict[selectedPeriods][1]+""" period data while the lighter """+histogramChart+""" charts show the """+chartDict[selectedPeriods][0]+""" period data."""                
    promptFact=""" Only provide fact-based evidences that can be derived from the data presented to you. Do not make inferences or assumptions beyond the data presented in the chart."""   
    promptChart=promptChart+promptFact          
    return promptChart

def get_ecdf_chart_prompt(df,chartDict):
    if not isinstance(df, pl.DataFrame):
        df = pl.DataFrame(df)
    namingParams=get_naming_params()
    yAxisDimension=namingParams["yAxisDimension"] 
    xAxisDimension=namingParams["xAxisDimension"]    
    ecdfChart=namingParams["ecdfChart"]
    nothingFilteredName=namingParams["nothingFilteredName"]
    xAxisMetric=namingParams["xAxisMetric"]
    showAverageValue=namingParams["showAverageValueName"]  
    smallMultiplesCharts=namingParams["plotSmallMultiplesOtherCharts"]
    smallMultiplesColumn=namingParams["smallMultiplesColumn"]
    aggregateOtherItemsName=namingParams["aggregateOtherItemsName"]
    showValuesAs=namingParams["showValuesAs"] 
    absolute=namingParams["absolute"] 
    numberOfTop=namingParams["numberOfTop"]
    selectedPeriods=namingParams["selectedPeriods"]  
    plotTitleText=namingParams["plotTitleText"]    
    #title=chartDict[plotTitleText]
    #title=title.replace("<BR>"," ")      
    numberOfPlottedSmallMultiplesKey=namingParams["numberOfPlottedSmallMultiples"]
    promptDescription="""The **"""+ecdfChart+"""** chart is a representation of the distribution of numerical data 
                    (for example prices): it shows, at any specified point of the measured variable, the fraction of 
                    observations of the measured variable that are less than or equal to the specified value.  """            
    promptChart=""
    promptOtherColumn=""
    if 1==1:
        promptOther=""
        promptAverage=""
        aggregationDimension=chartDict[xAxisDimension]
        if chartDict[xAxisDimension] in [None, nothingFilteredName]:
            aggregationDimension="observation"
        if smallMultiplesCharts not in chartDict or not chartDict[smallMultiplesCharts]:
            promptChart="""This image shows a **"""+ecdfChart+"""** chart in """+chartDict[xAxisMetric]+""" aggregated by """+aggregationDimension+""". """+promptDescription+""" The darker """+ecdfChart+""" chart shows the """+chartDict[selectedPeriods][1]+""" period data while the lighter """+ecdfChart+""" chart shows the """+chartDict[selectedPeriods][0]+""" period data.""" 
        elif smallMultiplesCharts in chartDict and chartDict[smallMultiplesCharts] and smallMultiplesColumn in chartDict:
            promptChart="""This image shows a **"""+ecdfChart+"""** chart in  """+chartDict[xAxisMetric]+""" aggregated by """+aggregationDimension+""", with """+str(chartDict[numberOfPlottedSmallMultiplesKey])+""" small multiples plots plotted by """+chartDict[smallMultiplesColumn]+""". """+promptDescription+""" The darker """+ecdfChart+""" charts show the """+chartDict[selectedPeriods][1]+""" period data while the lighter """+ecdfChart+""" charts show the """+chartDict[selectedPeriods][0]+""" period data."""                
    promptFact=""" Only provide fact-based evidences that can be derived from the data presented to you. Do not make inferences or assumptions beyond the data presented in the chart."""   
    promptChart=promptChart+promptFact          
    return promptChart

def get_boxplot_prompt(df,chartDict):
    if not isinstance(df, pl.DataFrame):
        df = pl.DataFrame(df)
    namingParams=get_naming_params()
    yAxisDimension=namingParams["yAxisDimension"] 
    xAxisDimension=namingParams["xAxisDimension"]    
    boxplotChart=namingParams["boxplotChart"] 
    nothingFilteredName=namingParams["nothingFilteredName"]
    xAxisMetric=namingParams["xAxisMetric"]
    showAverageValue=namingParams["showAverageValueName"]  
    smallMultiplesCharts=namingParams["plotSmallMultiplesOtherCharts"]
    smallMultiplesColumn=namingParams["smallMultiplesColumn"]
    aggregateOtherItemsName=namingParams["aggregateOtherItemsName"]
    showValuesAs=namingParams["showValuesAs"] 
    absolute=namingParams["absolute"] 
    numberOfTop=namingParams["numberOfTop"]
    selectedPeriods=namingParams["selectedPeriods"] 
    plotTitleText=namingParams["plotTitleText"]    
    #title=chartDict[plotTitleText]
    #title=title.replace("<BR>"," ")       
    numberOfPlottedSmallMultiplesKey=namingParams["numberOfPlottedSmallMultiples"]
    promptDescription="""The **"""+boxplotChart+"""** chart is a statistical representation of the distribution of a variable through its quartiles.
                   The ends of the box represent the lower and upper quartiles, while the median (second quartile) is marked by a line inside 
                   the box. """
    promptChart=""
    promptOtherColumn=""
    promptContext,companyOrIndustry,contextMetric=get_context(chartDict,chartDict[xAxisMetric])
    if 1==1:
        promptOther=""
        promptAverage=""
        aggregationDimension=chartDict[xAxisDimension]
        if chartDict[xAxisDimension] in [None, nothingFilteredName]:
            aggregationDimension="observation"
        if smallMultiplesCharts not in chartDict or not chartDict[smallMultiplesCharts]:
            promptChart="""This image shows a **"""+boxplotChart+"""** chart in """+contextMetric+""" aggregated by """+aggregationDimension+""". """+promptDescription+""" The darker """+boxplotChart+""" chart shows the """+chartDict[selectedPeriods][1]+""" period data while the lighter """+boxplotChart+""" chart shows the """+chartDict[selectedPeriods][0]+""" period data.""" 
        elif smallMultiplesCharts in chartDict and chartDict[smallMultiplesCharts] and smallMultiplesColumn in chartDict:
            promptChart="""This image shows a **"""+boxplotChart+"""** chart in  """+contextMetric+""" aggregated by """+aggregationDimension+""", with """+str(chartDict[numberOfPlottedSmallMultiplesKey])+""" small multiples plots plotted by """+chartDict[smallMultiplesColumn]+""". """+promptDescription+""" The darker """+boxplotChart+""" charts show the """+chartDict[selectedPeriods][1]+""" period data while the lighter """+boxplotChart+""" charts show the """+chartDict[selectedPeriods][0]+""" period data."""                
    promptFact=""" Only provide fact-based evidences that can be derived from the data presented to you. Do not make inferences or assumptions beyond the data presented in the chart."""   
    promptChart=promptChart+promptFact          
    return promptChart

def get_scatter_prompt(df,chartDict,fileName):
    if not isinstance(df, pl.DataFrame):
        df = pl.DataFrame(df)
    namingParams=get_naming_params()
    yAxisDimension=namingParams["yAxisDimension"] 
    xAxisDimension=namingParams["xAxisDimension"]  
    scatterChart=namingParams["scatterChart"] 
    nothingFilteredName=namingParams["nothingFilteredName"]
    yAxisMetricKey=namingParams["yAxisMetric"]
    xAxisMetricKey=namingParams["xAxisMetric"]
    showAverageValue=namingParams["showAverageValueName"]  
    smallMultiplesCharts=namingParams["plotSmallMultiplesOtherCharts"]
    smallMultiplesColumn=namingParams["smallMultiplesColumn"]
    aggregateOtherItemsName=namingParams["aggregateOtherItemsName"]
    nothingFilteredName=namingParams["nothingFilteredName"]
    notMetConditionValue=namingParams["notMetConditionValue"]
    showValuesAs=namingParams["showValuesAs"] 
    absolute=namingParams["absolute"] 
    numberOfTop=namingParams["numberOfTop"]
    plotTotalBubble=namingParams["plotTotalBubble"]
    isolineMetricKey=namingParams["isolineMetric"]
    showIsoLine=namingParams["showIsoLine"]
    plotAsHeatmap=namingParams["plotAsHeatmap"] 
    numberOfPlottedSmallMultiplesKey=namingParams["numberOfPlottedSmallMultiples"]
    plotTitleText=namingParams["plotTitleText"] 
    subplotTitlesKey=namingParams["subplotTitles"]   
    title=chartDict[plotTitleText]
    promptTotal,promptChart,promptLabels="","",""
    promptOtherColumn,promptDescription="",""
    promptIsoline,promptNormalized,plotTotal,promptColor,promptAverage="","","","",""
    yAxisMetric=change_metric_if_cost_analysis(chartDict[yAxisMetricKey],chartDict) 
    xAxisMetric=change_metric_if_cost_analysis(chartDict[xAxisMetricKey],chartDict) 
    isolineMetric=change_metric_if_cost_analysis(chartDict[isolineMetricKey],chartDict)      
    contextMetric=yAxisMetric+" and "+xAxisMetric
    promptContext,companyOrIndustry,contextMetric=get_context(chartDict,contextMetric)
    title=replace_ibcs_date_symbol(title,chartDict) 
    promptContext,df=explain_currency_and_abbreviations(df,chartDict,promptContext,contextMetric) 
    promptContext=add_prompt_date(promptContext,chartDict)
    promptFilter=add_prompt_filter(chartDict)
    isSmallMultiples=False
    if fileName.count("__") == 2:
        isSmallMultiples=True
    if not isSmallMultiples:
        toReplace="and "+chartDict[smallMultiplesColumn]
        title=title.replace(toReplace,"")
    if plotAsHeatmap in chartDict and chartDict[plotAsHeatmap]:
        if not isSmallMultiples:
            promptChart=""" This **"""+scatterChart+"""** chart has the following title: '"""+title+"""'."""+promptContext+""""""+promptFilter+""". The chart shows the relationship between two metrics ("""+yAxisMetric+""", """+xAxisMetric+""") as a heatmap. On the vertical axis, the **"""+scatterChart+"""** chart shows the items ranked by """+yAxisMetric+""". On the horizontal axis the **"""+scatterChart+"""** chart shows the items ranked by """+xAxisMetric+"""."""                  
        elif isSmallMultiples:
            promptChart="""This **"""+scatterChart+"""** chart shows the relationship between two metrics ("""+yAxisMetric+""", """+xAxisMetric+""") as a heatmap, with """+str(chartDict[numberOfPlottedSmallMultiplesKey])+""" small multiples plots plotted by """+chartDict[smallMultiplesColumn]+""". """+promptDescription+""" On the vertical axis, the **"""+scatterChart+"""** chart shows the items ranked by """+yAxisMetric+""". On the horizontal axis the **"""+scatterChart+"""** chart shows the items ranked by """+xAxisMetric+"""."""                  
    else:
        dotDimension=chartDict[xAxisDimension]
        if chartDict[xAxisDimension] in [None, nothingFilteredName]:
            dotDimension="observation"
        promptDescription=""" The **"""+scatterChart+"""** chart has the following title: '"""+title+"""'."""+promptContext+""""""+promptFilter+""". The chart shows the relationship between two metrics ("""+yAxisMetric+""", """+xAxisMetric+""").""" 
        if showIsoLine in chartDict and chartDict[showIsoLine]:
            promptIsoline= """ The isolines show a third metric, """+isolineMetric+""", that results from the multiplication of """+yAxisMetric+""" and """+xAxisMetric+""". The value of """+isolineMetric+""" for each isoline is shown in right of each isoline. """  
        if showValuesAs in chartDict and chartDict[showValuesAs] != absolute:
            promptNormalized=""" All values are normalized and shown in percent."""
        if chartDict[yAxisDimension] not in [None, nothingFilteredName,notMetConditionValue]:
            promptColor=""" Color maps the """+chartDict[yAxisDimension]+""" of each dot."""  
        if not isSmallMultiples:
            promptChart="""This image shows an IBCS **"""+scatterChart+"""** chart by """+dotDimension+""". """+promptDescription+""" On the vertical axis, the **"""+scatterChart+"""** chart shows the items ranked by """+yAxisMetric+""". On the horizontal axis the **"""+scatterChart+"""** chart shows the items ranked by """+xAxisMetric+"""."""  
            if is_valid_lazyframe(df):    
                promptLabels=""" Labels are shown for some, possibly relevant, items. For your convenience the labels and their values are shown here:\n{}""".format(df)+"""."""  
        elif isSmallMultiples:
            subplotTitles=chartDict[subplotTitlesKey]  
            subplotTitles=str(subplotTitles) 
            subplotTitles=subplotTitles.replace("[","").replace("]","").replace("'","")
            promptChart="""This image shows an IBCS small multiples **"""+scatterChart+"""** chart by  """+dotDimension+""", with """+str(chartDict[numberOfPlottedSmallMultiplesKey])+""" small multiples plots ("""+subplotTitles+""") plotted by """+chartDict[smallMultiplesColumn]+""". """+promptDescription+""" On the vertical axis, the **"""+scatterChart+"""** chart shows the items ranked by """+yAxisMetric+""". On the horizontal axis the **"""+scatterChart+"""** chart shows the items ranked by """+xAxisMetric+"""."""                  
            if is_valid_lazyframe(df):    
                promptLabels=""" Labels are shown for some, possibly relevant, items. For your convenience the labels and their values are shown here, stacked on top of each other by  """+chartDict[smallMultiplesColumn]+""":\n{}""".format(df)+"""."""     
    promptFact=""" Only provide fact-based evidences that can be derived from the data presented to you. Do not make inferences or assumptions beyond the data presented in the chart."""   
    promptChart=promptChart+promptOtherColumn+promptNormalized+promptColor+promptIsoline+promptLabels+promptFact 
    promptChart=promptChart.replace("..",".")      
    return promptChart,df      

def get_variance_prompt_root_cause_analysis(dfCopy,chartDict):
    namingParams=get_naming_params()
    varianceAggregationParams=get_variance_aggregation_params()
    cogsAggregationArray=varianceAggregationParams[namingParams["cogsAggregationArray"]]
    salesAggregationArray=varianceAggregationParams[namingParams["salesAggregationArray"]]
    discountsAggregationArray=varianceAggregationParams[namingParams["discountsAggregationArray"]]  
    plotTitleText=namingParams["plotTitleText"]
    varianceAggregation=namingParams["varianceAggregation"]
    processingChoice=namingParams["processingChoice"]
    workColumn=namingParams["workColumn"]     
    workColumnTwo=namingParams["workColumnTwo"]
    measureName=namingParams["measureName"] 
    marginName=namingParams["marginName"]
    amountName=namingParams["monetaryLocalCurrencyName"]
    netOfDiscountName=namingParams["netOfDiscountName"] 
    varianceAmountName=namingParams["varianceAmountName"] 
    varianceType=namingParams["varianceTypeName"]
    periodChoice=namingParams["periodChoice"]  
    residualName=namingParams["residualName"]  
    scenarioName=namingParams["scenarioName"]
    df=duplicate_dataframe(dfCopy)
    varianceTypeArray=df[varianceType].to_list()
    varianceTypeArray=varianceTypeArray[1:-1]
    numberOfVarianceTypeRows=len(varianceTypeArray)
    if numberOfVarianceTypeRows>1:
        varianceTypes=str(varianceTypeArray)    
        varianceTypes=varianceTypes.replace("[","").replace("]","").replace("'","")
    else:    
        varianceTypes=varianceTypeArray[0] 
    nonBlankRowsArray = extract_non_blank_rows(df)
    numberOfDicts=len(nonBlankRowsArray)
    if numberOfDicts>1:
        nonBlankRowsArray=str(nonBlankRowsArray)    
        nonBlankRowsArray=nonBlankRowsArray.replace("[","").replace("]","").replace("'","")
    else:
        nonBlankRowsArray=nonBlankRowsArray[0]    
    rowsArray=df[workColumn].to_list()
    rowsArray=rowsArray[1:-1]
    numberOfRows=len(rowsArray)
    if numberOfRows>1:
        rows=str(rowsArray)    
        rows=rows.replace("[","").replace("]","").replace("'","").replace(","," and") 
    else:
        rows=rowsArray[0] 
    metric=amountName
    if chartDict[varianceAggregation] in cogsAggregationArray:
        metric=marginName
    elif chartDict[varianceAggregation] in discountsAggregationArray:
        metric=netOfDiscountName        
    title=chartDict[plotTitleText] 
    promptContext,companyOrIndustry,contextMetric=get_context(chartDict,metric)
    title=replace_ibcs_date_symbol(title,chartDict)
    promptContext,df=explain_currency_and_abbreviations(df,chartDict,promptContext,contextMetric) 
    promptFilter=add_prompt_filter(chartDict)       
    topRowValue = df[varianceAmountName][0]
    bottomRowValue = df[varianceAmountName][-1]
    varianceAmountArray=df[varianceAmountName].to_list()
    varianceAmountArray=varianceAmountArray[1:-1]
    numberOfVariances=len(varianceAmountArray)
    if numberOfVariances>1:
        variances=str(varianceAmountArray)    
        variances=variances.replace("[","").replace("]","").replace("'","") 
    else:
        variances=varianceAmountArray[0]     
    dropCols=[measureName,workColumnTwo]
    df=drop_columns(df,dropCols)
    firstPeriod,secondPeriod=traslate_ibcs_period_symbols(chartDict) 
    if isinstance(chartDict[periodChoice], bool):
        chartDict[periodChoice]=scenarioName   
    promptDf=" The dataset is as follows :\n{}".format(df)
    promptDescription=""" You are provided the dataset of a **"""+str(chartDict[processingChoice])+"""** chart titled: '"""+str(title)+"""'."""+promptContext+""""""+promptFilter+"""
    The dataset provides insights on """+str(chartDict[varianceAggregation])+""" variance outlining the contribution a dimension-item pair 
    or of combinations of dimension-item pairs to the overall change in """+contextMetric+""". The dimension-item pair or combinations of dimension-item pairs 
    of each variance row are ranked by the absolute value of their contribution to variance.    
    The contribution of each variance row is net of the cumulative effect of the preceding variance rows. As way of example, assume that 
    the first variance row has a dimension-item pair equal to "China-Country", and a positive variance of +100. Now assume that the 
    second variance row has two dimension-item pairs - "Supermarket-Channel" and "Product-Oranges" - and negative variance of -50. 
    This means that all sales in China, including sales of Oranges in Supermarkets, have increased by 100. However sales of Oranges 
    in Supermarkets outside China have fallen by 50.      
    The dataset contains: 
    (1) The name of the first period: """+str(chartDict[periodChoice])+""" """+firstPeriod+""", its value: """+str(topRowValue)+""", and the variance metric: """+contextMetric+""" ;    
    (2) The dimension-item pair or combinations of dimension-item pairs of each of the """+str(numberOfDicts)+""" variance rows: """+str(nonBlankRowsArray)+""". 
    Each dictionary shows the dimension-item pair or combination of dimension-item pairs of a variance row. The key of each dictionary is the dimension, 
    the value is the item;   
    (3) The variance type of each of the """+str(numberOfDicts)+""" variance rows: """+str(varianceTypes)+""";    
    (4) If the sum of the variances does not match with the total difference between """+secondPeriod+""" 
    and """+firstPeriod+""" """+contextMetric+""", there will be a """+str(residualName)+""" value;  
    (5) The value of the  """+str(contextMetric)+""" variance for each of the """+str(numberOfRows)+""" variance rows (including the """+residualName+"""  if present): """+variances+""" .  
    (6) The name of the second period: """+str(chartDict[periodChoice])+""" """+secondPeriod+""", its value: """+str(bottomRowValue)+""", 
    and the variance metric: """+str(contextMetric)+""".    
    Conduct a thorough analysis of the structured  """+str(contextMetric)+""" bridge data, focusing on the sequential impact of 
    each variance row:      
    (1) Start the analysis by assessing the initial """+str(contextMetric)+""" figures of """+str(chartDict[periodChoice])+""" """+firstPeriod+""";  
    (2) Progress through each of the """+str(numberOfDicts)+""" variance rows, which represents distinct combinations of dimension-item pairs.
    Evaluate the variance impact of each combination considering its specific set of dimension-item pairs;  
    (3) Keep in mind that each row's impact is net of the impact of the previous rows;       
    (4) Ignore the """+str(residualName)+""" value if present;   
    (5) Assess the final """+str(contextMetric)+""" figures of """+str(chartDict[periodChoice])+""" """+secondPeriod+""";      
    (6) Look for underlying patterns and insights that explain the interplay and cumulative effect of these combinations of dimension-item pairs 
    on the overall """+contextMetric+""" performance;     
    (7) Summarize the overall trend from """+firstPeriod+""" """+str(chartDict[periodChoice])+""" to 
    """+secondPeriod+""" """+str(chartDict[periodChoice])+""".   
    """
    #promptOne="Provide textual interpretation of data, followed by analysis and insights. "
    promptOne=" "
    promptFact="""\n\n Only provide fact-based evidences that can be derived from the data presented to you. Do not make inferences or assumptions beyond the data presented in the chart.\n\n"""
    promptChart=promptOne+promptDescription+promptFact
    return promptChart,df

def get_variance_prompt_multiple_calculations(dfCopy,chartDict):
    namingParams=get_naming_params()
    varianceAggregationParams=get_variance_aggregation_params()
    cogsAggregationArray=varianceAggregationParams[namingParams["cogsAggregationArray"]]
    salesAggregationArray=varianceAggregationParams[namingParams["salesAggregationArray"]]
    discountsAggregationArray=varianceAggregationParams[namingParams["discountsAggregationArray"]]  
    plotTitleText=namingParams["plotTitleText"]
    varianceAggregation=namingParams["varianceAggregation"]
    processingChoice=namingParams["processingChoice"]
    workColumn=namingParams["workColumn"]     
    workColumnTwo=namingParams["workColumnTwo"]
    measureName=namingParams["measureName"] 
    marginName=namingParams["marginName"]
    amountName=namingParams["monetaryLocalCurrencyName"]
    netOfDiscountName=namingParams["netOfDiscountName"] 
    varianceAmountName=namingParams["varianceAmountName"] 
    varianceType=namingParams["varianceTypeName"]
    periodChoice=namingParams["periodChoice"]
    runningTotalName=namingParams["runningTotalName"]
    selectedPeriodsKey=namingParams["selectedPeriods"]
    varianceAggregationOptionsArray=namingParams["varianceAggregationOptionsArray"]
    varianceComponent=namingParams["varianceComponent"]
    residualName=namingParams["residualName"]
    numberOfCalculations=str(len(chartDict[varianceAggregationOptionsArray]))
    if len(chartDict[varianceAggregationOptionsArray])>1:
        varianceAggregations=str(chartDict[varianceAggregationOptionsArray]) 
        varianceAggregations=varianceAggregations.replace("[","").replace("]","").replace("',",";").replace("'","")
    else:
        varianceAggregations=chartDict[varianceAggregationOptionsArray][0]
    df=duplicate_dataframe(dfCopy)
    if not isinstance(df, pl.DataFrame):
        df = pl.DataFrame(df)
    renameDict={workColumn:varianceComponent}
    df = df.rename(renameDict)
    rowsArray=df[varianceComponent].unique().to_list()
    rowsArray=rowsArray[1:-1]
    numberOfRows=len(rowsArray)
    if numberOfRows>1:
        rows=str(rowsArray)    
        rows=rows.replace("[","").replace("]","").replace("'","").replace(","," and") 
    else:
        rows=rowsArray[0]   
    dropCols=[measureName,workColumnTwo,runningTotalName]
    df=drop_columns(df,dropCols)
    metric=amountName
    metric=change_metric_if_cost_analysis(metric,chartDict) 
    if chartDict[varianceAggregation] in cogsAggregationArray:
        metric=marginName
        promptAggregations="""**"""+chartDict[varianceAggregationOptionsArray][0].capitalize()+"""** returns the """+metric+""" variance value split into three components: (1) price variance, (2) units and mix variance and (3) margin rate variance. **"""+chartDict[varianceAggregationOptionsArray][1].capitalize()+"""** returns the """+metric+""" variance value split into three components: (1) price variance, (2) units and mix variance and (3) cost variance. **"""+chartDict[varianceAggregationOptionsArray][2].capitalize()+"""** returns the """+metric+""" variance value split into four components: (1) price variance, (2) units variance, (3) mix variance and (4) costs variance. """ 
    elif chartDict[varianceAggregation] in discountsAggregationArray:
        metric=netOfDiscountName
        promptAggregations=""  
    else:
        promptAggregations="""**"""+chartDict[varianceAggregationOptionsArray][0].capitalize()+"""** returns the total """+metric+""" variance value. **"""+chartDict[varianceAggregationOptionsArray][1].capitalize()+"""** returns the """+metric+""" variance value split into two components: (1) price variance and  (2) units plus mix variance. **"""+chartDict[varianceAggregationOptionsArray][2].capitalize()+"""** returns the """+metric+""" variance value split into three components: (1) price variance, (2) units variance and (3) mix variance. """
    chartDict=check_if_period(chartDict)
    firstPeriod,secondPeriod="",""
    if len(chartDict[periodChoice])>1:
        firstPeriod,secondPeriod=chartDict[selectedPeriodsKey][0],chartDict[selectedPeriodsKey][1]             
    title=chartDict[plotTitleText]
    index=""
    promptContext,companyOrIndustry,contextMetric=get_context(chartDict,metric)
    title=replace_ibcs_date_symbol(title,chartDict)
    promptContext,df=explain_currency_and_abbreviations(df,chartDict,promptContext,contextMetric)
    promptFilter=add_prompt_filter(chartDict)
    promptDf=" The dataset is as follows :\n{}".format(df)
    firstPeriod,secondPeriod=traslate_ibcs_period_symbols(chartDict) 
    promptDescription=""" You are provided a dataset with """+numberOfCalculations+""" different aggregations of """+contextMetric.lower()+""" stacked on top of each other. The chart is titled: '"""+title+"""'."""+promptContext+""""""+promptFilter+"""" Variance is calculated between periods """+firstPeriod+""" and """+secondPeriod+""". The variance metric is """+metric+""".  
    The dataset provides insights on the total variance value and on the breakdown the different variance components using """+numberOfCalculations+""" different variance aggregation methods: """+varianceAggregations+""". """+promptAggregations+"""   
    The top row of each stacked-up variance calculation dataset shows, in the """+varianceAmountName+""" column, the value of """+contextMetric+""" in period """+firstPeriod+""".
    The bottom row of each variance calculation shows, in the """+varianceAmountName+""" column, the value of """+contextMetric+""" in period """+secondPeriod+""". 
    The other rows of each variance calculation show, in the """+varianceAmountName+""" column, the value of the different components (if any) of """+contextMetric+""". 
    If the sum of the components of a variance calculation does not match the total variance value, a """+residualName+""" element is automatically added. Ignore variance calculations that have a material  """+residualName+""" component. 
    The name of the period and the name of the variance component is shown in the """+varianceComponent+""" column. The variance aggregation method is shown in the corresponding row of the """+varianceType+""" column of the dataset.
    """
    promptDescription=promptDescription+promptDf
    promptOne="""\n\n Compare the variance value breakdown across the different calculations to identify which components impact the overall variance.\n\n"""
    promptFact="""\n\n Only provide fact-based evidences that can be derived from the data presented to you. Do not make inferences or assumptions beyond the data presented in the chart.\n\n"""
    promptChart=promptDescription+promptOne+promptFact 
    return promptChart,df

def get_variance_prompt_small_multiples(dfCopy,chartDict):
    namingParams=get_naming_params()
    varianceAggregationParams=get_variance_aggregation_params()
    cogsAggregationArray=varianceAggregationParams[namingParams["cogsAggregationArray"]]
    salesAggregationArray=varianceAggregationParams[namingParams["salesAggregationArray"]]
    discountsAggregationArray=varianceAggregationParams[namingParams["discountsAggregationArray"]]  
    plotTitleText=namingParams["plotTitleText"]
    varianceAggregation=namingParams["varianceAggregation"]
    processingChoice=namingParams["processingChoice"]
    workColumn=namingParams["workColumn"]     
    workColumnTwo=namingParams["workColumnTwo"]
    measureName=namingParams["measureName"] 
    marginName=namingParams["marginName"]
    amountName=namingParams["monetaryLocalCurrencyName"]
    netOfDiscountName=namingParams["netOfDiscountName"] 
    varianceAmountName=namingParams["varianceAmountName"] 
    varianceType=namingParams["varianceTypeName"]
    periodChoice=namingParams["periodChoice"]
    mainDimensionKey=namingParams["mainDimension"] 
    smallMultiplesWaterfall=namingParams["smallMultiplesWaterfall"]
    aggregateOtherWaterfallsName=namingParams["aggregateOtherWaterfallsName"]
    df=duplicate_dataframe(dfCopy)
    dimensionArray=df[chartDict[mainDimensionKey][0]].unique().to_list()
    isOtherColumnRank= False
    if aggregateOtherWaterfallsName in dimensionArray:
        isOtherColumnRank= True        
    numberOfDimensions=len(dimensionArray)
    if numberOfDimensions>1:
        dimensions=str(dimensionArray)    
        dimensions=dimensions.replace("[","").replace("]","").replace("'","") 
    else:
        dimensions=dimensionArray[0]
    rowsArray=df[workColumn].unique().to_list()
    rowsArray=rowsArray[1:-1]
    numberOfRows=len(rowsArray)
    if numberOfRows>1:
        rows=str(rowsArray)    
        rows=rows.replace("[","").replace("]","").replace("'","").replace(","," and") 
    else:
        rows=rowsArray[0]  
    dropCols=[measureName,workColumnTwo]
    df=drop_columns(df,dropCols)
    metric=amountName
    if chartDict[varianceAggregation] in cogsAggregationArray:
        metric=marginName
    elif chartDict[varianceAggregation] in discountsAggregationArray:
        metric=netOfDiscountName        
    title=chartDict[plotTitleText] 
    firstPeriod,secondPeriod=traslate_ibcs_period_symbols(chartDict) 
    promptOther=""
    chartDict=check_if_period(chartDict)  
    if isOtherColumnRank:
        promptOther=""" The '"""+aggregateOtherWaterfallsName+"""' item represents the aggregation of the other smaller items. """
    promptContext,companyOrIndustry,contextMetric=get_context(chartDict,metric)
    title=replace_ibcs_date_symbol(title,chartDict)
    promptContext,df=explain_currency_and_abbreviations(df,chartDict,promptContext,contextMetric) 
    promptFilter=add_prompt_filter(chartDict)  
    promptDf=" The dataset is as follows :\n{}".format(df)
    promptDescription=""" You are provided the dataset of a small multiples **"""+chartDict[processingChoice]+""" 
    by """+chartDict[mainDimensionKey][0]+"""** chart titled: '"""+title+"""'."""+promptContext+""""""+promptFilter+"""
    The dataset provides insights on """+chartDict[varianceAggregation]+""" variance. The variance metric is """+contextMetric+""". 
    The dataset contains the """+chartDict[periodChoice]+""" """+firstPeriod+""" values, 
    the """+rows+""" variance values and the """+chartDict[periodChoice]+""" """+secondPeriod+""" values for each dimension.
    The """+str(numberOfDimensions)+""" small multiple dimensions are: """+dimensions+"""."""+promptOther+"""
    The """+str(numberOfDimensions)+""" datasets of the different small multiples dimensions are stacked of top of each other. 
    The """+chartDict[mainDimensionKey][0]+""" column of the dataset indicates the small multiple dimension. 
    The top row of the """+varianceAmountName+""" column of each dataset shows the value of """+contextMetric+""" in period """+firstPeriod+""". 
    The bottom row of each """+varianceAmountName+""" column of each dataset shows the value of """+contextMetric+""" in period """+secondPeriod+""". 
    The """+rows+""" row(s) of the """+varianceAmountName+""" column of each dataset show(s) the value of the different components (if any) of """+contextMetric+""" variance. 
    The variance type is shown in the corresponding row of the """+varianceType+""" column of the dataset.
    """
    promptDescription=promptDescription+promptDf
    #promptOne="Provide textual interpretation of data, followed by analysis and insights. "
    promptOne=" "
    promptMaterial=""" Ignore non material dimensions, non material """+contextMetric+""" values and non material variance values. """
    promptFact="""\n\n Only provide fact-based evidences that can be derived from the data presented to you. """+promptMaterial+"""Do not make inferences or assumptions beyond the data presented in the chart.\n\n"""
    promptChart=promptOne+promptDescription+promptFact     
    return promptChart,df

def get_variance_prompt_not_small_multiples(dfCopy,chartDict):
    namingParams=get_naming_params()
    varianceAggregationParams=get_variance_aggregation_params()
    cogsAggregationArray=varianceAggregationParams[namingParams["cogsAggregationArray"]]
    salesAggregationArray=varianceAggregationParams[namingParams["salesAggregationArray"]]
    discountsAggregationArray=varianceAggregationParams[namingParams["discountsAggregationArray"]]  
    plotTitleText=namingParams["plotTitleText"]
    varianceAggregation=namingParams["varianceAggregation"]
    processingChoice=namingParams["processingChoice"]
    workColumn=namingParams["workColumn"]     
    workColumnTwo=namingParams["workColumnTwo"]
    measureName=namingParams["measureName"] 
    marginName=namingParams["marginName"]
    amountName=namingParams["monetaryLocalCurrencyName"]
    netOfDiscountName=namingParams["netOfDiscountName"] 
    varianceAmountName=namingParams["varianceAmountName"] 
    varianceType=namingParams["varianceTypeName"]
    periodChoice=namingParams["periodChoice"]  
    df=duplicate_dataframe(dfCopy)
    rowsArray=df[workColumn].unique().to_list()
    rowsArray=rowsArray[1:-1]
    numberOfRows=len(rowsArray)
    if numberOfRows>1:
        rows=str(rowsArray)    
        rows=rows.replace("[","").replace("]","").replace("'","").replace(","," and") 
    else:
        rows=rowsArray[0]  
    dropCols=[measureName,workColumnTwo]
    df=drop_columns(df,dropCols)
    metric=amountName
    if chartDict[varianceAggregation] in cogsAggregationArray:
        metric=marginName
    elif chartDict[varianceAggregation] in discountsAggregationArray:
        metric=netOfDiscountName  
    chartDict=check_if_period(chartDict)            
    title=chartDict[plotTitleText]
    index=""
    promptContext,companyOrIndustry,contextMetric=get_context(chartDict,metric)
    title=replace_ibcs_date_symbol(title,chartDict)
    promptContext,df=explain_currency_and_abbreviations(df,chartDict,promptContext,contextMetric)
    promptFilter=add_prompt_filter(chartDict)
    promptDf=" The dataset is as follows :\n{}".format(df)
    firstPeriod,secondPeriod=traslate_ibcs_period_symbols(chartDict) 
    promptDescription=""" You are provided the dataset of a **"""+chartDict[processingChoice]+"""** chart titled: '"""+title+"""'."""+promptContext+""""""+promptFilter+"""
    The dataset provides insights on """+chartDict[varianceAggregation]+""" variance. The variance metric is """+metric+""". 
    The dataset contains the """+chartDict[periodChoice]+""" """+firstPeriod+""" values, 
    the """+rows+""" variance values and the """+chartDict[periodChoice]+""" """+secondPeriod+""" values. 
    The top row of the """+varianceAmountName+""" column of the dataset shows the value of """+metric+""" in period """+firstPeriod+""". 
    The bottom row of the """+varianceAmountName+""" column of the dataset shows the value of """+metric+""" in period """+secondPeriod+""". 
    The """+rows+""" row(s) of the """+varianceAmountName+""" column of the dataset show(s) the value of the different components (if any) of """+metric+""" variance. 
    The variance type is shown in the corresponding row of the """+varianceType+""" column of the dataset.
    """
    promptDescription=promptDescription+promptDf
    #promptOne="Provide textual interpretation of data, followed by analysis and insights. "
    promptOne=" "
    promptFact="""\n\n Only provide fact-based evidences that can be derived from the data presented to you. Do not make inferences or assumptions beyond the data presented in the chart.\n\n"""
    promptChart=promptOne+promptDescription+promptFact 
    return promptChart,df

def get_synthesis_stacked_column_prompt(df,chartDict):
    namingParams=get_naming_params()
    absolute=namingParams["absolute"] 
    plotValuesAsChoice=namingParams["plotValuesAsChoice"]  
    yAxisDimension=namingParams["yAxisDimension"] 
    stackedColumnChart=namingParams["stackedColumnChart"]
    itemName=namingParams["itemName"]
    valueName=namingParams["valueName"]
    dimensionName=namingParams["dimensionName"]
    periodChoice=namingParams["periodChoice"]
    aggregateOtherItemsName=namingParams["aggregateOtherItemsName"]
    metricsToPlot=namingParams["metricsToPlot"] 
    numberOfTop=namingParams["numberOfTop"]         
    selectDimensionsToPlot=namingParams["selectDimensionsToPlot"]  
    numberOfPlottedSmallMultiplesKey=namingParams["numberOfPlottedSmallMultiples"]
    plotTitleText=namingParams["plotTitleText"]  
    title=chartDict[plotTitleText]
    dimensions=str(chartDict[selectDimensionsToPlot][1:])
    dimensions=dimensions.replace("[","").replace("]","").replace("'","")
    dimension=""
    promptOther=""
    itemDetail=""
    if not isinstance(df, pl.DataFrame):
        df = pl.DataFrame(df)
    columns,schema=get_schema_and_column_names(df)
    isOtherRowRank=check_if_other_in_rows(df,itemName) 
    promptColumns="""The dataset shows the """
    chartDict=check_if_period(chartDict)
    promptContext,companyOrIndustry,contextMetric=get_context(chartDict,chartDict[metricsToPlot][0])
    promptFilter=add_prompt_filter(chartDict)
    title=replace_ibcs_date_symbol(title,chartDict) 
    promptContext,df=explain_currency_and_abbreviations(df,chartDict,promptContext,contextMetric)     
    firstPeriod,secondPeriod=traslate_ibcs_period_symbols(chartDict)  
    promptDf=" The dataset is as follows :\n{}".format(df)     
    promptDescription=""" The provided **"""+stackedColumnChart+"""** chart dataset has the following title: '"""+title+"""'."""+promptContext+""""""+promptFilter+"""
    It presents the distribution of """+chartDict[periodChoice]+""" """+secondPeriod+""" """+contextMetric+""" 
    across """+str(len(chartDict[selectDimensionsToPlot]))+""" business dimensions: """+dimensions+""".
    The data contains """+str(len(chartDict[selectDimensionsToPlot]))+""" datasets by """+dimensionName+""" stacked on top of each other.
    The data is shown in absolute value ("""+valueName+""" column) and as percent of total."""                 
    if isOtherRowRank:
        otherRowRank="x"
        if 'X' in chartDict:
            otherRowRank=str(chartDict["X"][numberOfTop])
        promptOther=""" The smaller items are aggregated in the '"""+aggregateOtherItemsName+""" """+otherRowRank+"""' element.""" 
    promptChart=promptDescription+promptOther
    promptFact=""" Only provide fact-based evidences that can be derived from the data presented to you. Do not make inferences or assumptions beyond the data presented in the chart."""   
    promptMaterial=""" Focus on important, material items. """
    promptChart=promptChart+promptDf+promptMaterial+promptFact  
    return promptChart,df

def get_bubble_prompt(dfCopy,chartDict):
    namingParams=get_naming_params()
    yAxisDimensionKey=namingParams["yAxisDimension"] 
    xAxisDimensionKey=namingParams["xAxisDimension"]
    yAxisMetricKey=namingParams["yAxisMetric"] 
    xAxisMetricKey=namingParams["xAxisMetric"]     
    bubbleSizeKey=namingParams["bubbleSize"]     
    bubbleChart=namingParams["bubbleChart"] 
    nothingFilteredName=namingParams["nothingFilteredName"]
    singleMetric=namingParams["singleMetric"]
    totalName=namingParams["totalName"]
    showAverageValue=namingParams["showAverageValueName"]     
    aggregateOtherItemsName=namingParams["aggregateOtherItemsName"]
    numberOfTop=namingParams["numberOfTop"]
    numberOfPlottedSmallMultiplesKey=namingParams["numberOfPlottedSmallMultiples"]
    smallMultiplesColumnKey=namingParams["smallMultiplesColumn"]
    plotSmallMultiplesKey=namingParams["plotSmallMultiplesOtherCharts"]
    plotTitleText=namingParams["plotTitleText"]   
    aggregateOtherItemsNameKey=namingParams["aggregateOtherItemsName"]     
    bubbleSize=chartDict[bubbleSizeKey]
    yAxisMetric=chartDict[yAxisMetricKey]
    xAxisMetric=chartDict[xAxisMetricKey]
    xAxisDimension=chartDict[xAxisDimensionKey]
    title=chartDict[plotTitleText]
    columnTotal="Column "+totalName
    rowTotal="Row "+totalName
    toKeepArray=[bubbleSize,yAxisMetric,xAxisMetric,xAxisDimension]
    toDrop=[]
    colorDimension=False
    smallMultiplesColumn=""
    df=duplicate_dataframe(dfCopy)
    if not isinstance(df, pl.DataFrame):
        df = pl.DataFrame(df)
    df=change_column_names_if_cost_analysis(df,chartDict)
    toKeepArray=change_array_of_metrics_if_cost_analysis(toKeepArray,chartDict)
    bubbleSize=change_metric_if_cost_analysis(bubbleSize,chartDict) 
    yAxisMetric=change_metric_if_cost_analysis(yAxisMetric,chartDict) 
    xAxisMetric=change_metric_if_cost_analysis(xAxisMetric,chartDict)  
    contextMetric=bubbleSize+", "+yAxisMetric+" and "+xAxisMetric
    promptContext,companyOrIndustry,contextMetric=get_context(chartDict,contextMetric)
    title=replace_ibcs_date_symbol(title,chartDict)
    promptContext,df=explain_currency_and_abbreviations(df,chartDict,promptContext,contextMetric)
    promptContext=add_prompt_date(promptContext,chartDict)
    promptFilter=add_prompt_filter(chartDict)
    if smallMultiplesColumnKey in chartDict and chartDict[smallMultiplesColumnKey]:
        smallMultiplesColumn=chartDict[smallMultiplesColumnKey]
    if plotSmallMultiplesKey in chartDict and chartDict[plotSmallMultiplesKey]:
        if smallMultiplesColumn not in toKeepArray:
            toKeepArray.append(smallMultiplesColumn)
    if yAxisDimensionKey in chartDict and chartDict[yAxisDimensionKey] and chartDict[yAxisDimensionKey] != nothingFilteredName:
        yAxisDimension=chartDict[yAxisDimensionKey]
        if yAxisDimension not in toKeepArray:
            toKeepArray.append(yAxisDimension)
            colorDimension=yAxisDimension
    columns,schema=get_schema_and_column_names(df)
    for element in columns:
        if element not in toKeepArray and element:
            toDrop.append(element)      
    if len(toDrop) >0:
        df=drop_columns(df,toDrop)   
    isOtherRowRank=check_if_other_in_rows(df,xAxisDimension)   
    promptChart=""
    promptOther=""
    promptColor=""
    if colorDimension:
        promptColor=""" The """+colorDimension+""" column shows the """+colorDimension+""" of each item. """
    if isOtherRowRank:
        otherRowRank="x"
        if 'X' in chartDict:
            otherRowRank=str(chartDict["X"][numberOfTop])
        promptOther=""" The smaller """+xAxisDimension+""" items are aggregated in the '"""+aggregateOtherItemsName+""" """+otherRowRank+"""' element.""" 
    if smallMultiplesColumn in columns and plotSmallMultiplesKey in chartDict and chartDict[plotSmallMultiplesKey]:
        frameArray=[]
        smallMultiplesArray=df[smallMultiplesColumn].unique().to_list()
        numberOfSmallMultiples=len(smallMultiplesArray)
        smallMultiplesList=str(smallMultiplesArray).replace("[","").replace("]","")
        for element in smallMultiplesArray:
            dfFiltered=df.filter(pl.col(smallMultiplesColumn) == element)
            if dfFiltered.height>0:
                dfFiltered=dfFiltered.sort(bubbleSize, descending=True)
                dfFiltered=rank_others_as_last(dfFiltered,aggregateOtherItemsNameKey,99)
                frameArray.append(dfFiltered)
        df = pl.concat(frameArray, how="vertical") if frameArray else pl.DataFrame()
        numberOfColumns=len(columns)
        columnNames=str(columns).replace("[","").replace("]","")
        promptDescription=""" The provided small multiples **"""+bubbleChart+"""** chart dataset has the following title: '"""+title+"""'."""+promptContext+""""""+promptFilter+"""
        The small multiples """+bubbleChart+""" chart is plotted by """+xAxisDimension+""".
        The data contains """+str(numberOfSmallMultiples)+""" small multiples datasets by """+smallMultiplesColumn+""" stacked on top of each other: """+smallMultiplesList+""".
        The dataset shows the """+bubbleSize+""", the """+yAxisMetric+""" and the """+xAxisMetric+""" of each item for each """+smallMultiplesColumn+""". """
        promptChart=promptDescription
    else:
        df=df.sort(bubbleSize, descending=True)
        df=rank_others_as_last(df,aggregateOtherItemsNameKey,99)
        columns,schema=get_schema_and_column_names(df)
        promptDescription=""" The provided **"""+bubbleChart+"""** chart dataset has the following title: '"""+title+"""'."""+promptContext+""""""+promptFilter+"""
        The """+bubbleChart+""" chart is plotted by """+xAxisDimension+""".
        The dataset shows the """+bubbleSize+""", the """+yAxisMetric+""" and the """+xAxisMetric+""" of each item. """
        promptChart=promptDescription
    promptFact="""\n\n\n Only provide fact-based evidences that can be derived from the data presented to you. Do not make inferences or assumptions beyond the data presented in the chart."""             
    promptDf="\n\nThe dataset is as follows :\n{}".format(df)     
    promptChart=promptChart+promptOther+promptColor+promptDf+promptFact             
    return promptChart,df 

def get_pareto_prompt(df,chartDict):
    namingParams=get_naming_params()
    yAxisDimension=namingParams["yAxisDimension"]   
    paretoChart=namingParams["paretoChart"]
    nothingFilteredName=namingParams["nothingFilteredName"]
    showAverageValue=namingParams["showAverageValueName"]  
    smallMultiplesCharts=namingParams["plotSmallMultiplesOtherCharts"]
    smallMultiplesColumn=namingParams["smallMultiplesColumn"]
    aggregateOtherItemsName=namingParams["aggregateOtherItemsName"]
    countColumn=namingParams["countColumn"] 
    metricsToPlotKey=namingParams["metricsToPlot"] 
    absolute=namingParams["absolute"] 
    numberOfTop=namingParams["numberOfTop"]
    selectedPeriods=namingParams["selectedPeriods"]  
    selectDimensionsToPlot=namingParams["selectDimensionsToPlot"]  
    numberOfPlottedSmallMultiplesKey=namingParams["numberOfPlottedSmallMultiples"]
    plotCommentText=namingParams["plotCommentText"]
    plotConcentrationText=namingParams["plotConcentrationText"] 
    plotTitleText=namingParams["plotTitleText"]    
    title=chartDict[plotTitleText]
    if not isinstance(df, pl.DataFrame):
        df = pl.DataFrame(df)
    metricsToPlot=change_array_of_metrics_if_cost_analysis(chartDict[metricsToPlotKey],chartDict)
    contextMetric=metricsToPlot[0]
    if len(metricsToPlot)==2:
        contextMetric=metricsToPlot[0]+" and "+metricsToPlot[1]
    elif len(metricsToPlot)==3:
        contextMetric=metricsToPlot[0]+" , "+metricsToPlot[1]+" and "+metricsToPlot[2]    
    contextMetric="the concentration of "+contextMetric    
    promptContext,companyOrIndustry,contextMetric=get_context(chartDict,contextMetric)
    title=replace_ibcs_date_symbol(title,chartDict)
    promptContext,df=explain_currency_and_abbreviations(df,chartDict,promptContext,contextMetric)
    promptContext=add_prompt_date(promptContext,chartDict)
    promptFilter=add_prompt_filter(chartDict)
    concentration=chartDict[plotConcentrationText] 
    promptDescription="""A **"""+paretoChart+"""** chart is a type of chart that can contain both a line graph and bars, where 
    the cumulative total is represented by the line and individual values are represented in descending order by bars. 
    The """+paretoChart+""" chart is utilized in the analysis of data to focus on the most significant among a set of factors in a dataset.    
    You are presented with a """+paretoChart+""" chart. The title of the chart is '"""+title+"""'."""+promptContext+""""""+promptFilter+"""
    The chart is structured into """+str(len(metricsToPlot))+""" subcharts, set one alongside the other.
    The axis of all three charts is identically sorted by descending """+chartDict[countColumn]+""" """+metricsToPlot[0]+""".
    If the number of """+chartDict[countColumn]+"""s is low, horizontal bar charts are also plotted along the Y axis showing the """+metricsToPlot[0]+""" of every """+chartDict[countColumn]+""".    
    The first subchart shows cumulative """+chartDict[countColumn]+""" """+metricsToPlot[0]+""". 
    The vertical Y-axis shows the number of """+chartDict[countColumn]+"""s, and the X-axis shows the cumulative percentage of """+metricsToPlot[0]+""" on the total """+metricsToPlot[0]+""".
    The plotted line shows cumulative """+metricsToPlot[0]+""". The line is sorted by the """+chartDict[countColumn]+"""s contributing the most """+metricsToPlot[0]+""". 
    The line is made up of three segments, colored in three different colors:   
        (i) The first segment of the line shows the top """+chartDict[countColumn]+"""s contributing to 80% of """+metricsToPlot[0]+""" ('A' """+chartDict[countColumn]+""" """+metricsToPlot[0]+""" class);    
        (ii) The second segment of the line is plotted in a different color and illustrates the next set of """+chartDict[countColumn]+"""s contributing to an additional 15% of """+metricsToPlot[0]+""" ('B' """+chartDict[countColumn]+""" """+metricsToPlot[0]+""" class);    
        (iii) The third segment of the line is plotted in a third color and plots the least important """+chartDict[countColumn]+"""s that, all together, contribute to 5% of """+metricsToPlot[0]+""" ('C' """+chartDict[countColumn]+""" """+metricsToPlot[0]+""" class );        
        (iv) If any """+chartDict[countColumn]+"""s have negative """+metricsToPlot[0]+""", these will be represented by a fourth segment of the line, shown in red.   
    Here is the concentration by """+metricsToPlot[0]+""": """+chartDict[plotCommentText][0]+""".   
    """+concentration+""""""
    promptDf=""
    promptThirdMetric=""
    promptSecondMetric=""
    if len(metricsToPlot)>=2: 
        promptSecondMetric="""The second subchart utilizes the same Y-axis and is identically sorted. The line displays the cumulative """+metricsToPlot[1]+""" corresponding to the cumulative """+metricsToPlot[0]+""" levels.
        The colors correspond to the A, B, and C """+metricsToPlot[1]+""" classes of each """+chartDict[countColumn]+""".
        This is the concentration by """+metricsToPlot[1]+""": """+chartDict[plotCommentText][1]+""".    
        The """+chartDict[countColumn]+""" ranking (descending """+metricsToPlot[0]+""") is the same across all subcharts.
        Therefore if the """+chartDict[countColumn]+"""s that make up a 80% of """+metricsToPlot[0]+""" make up 
        a higher than 80% percentage of """+metricsToPlot[1]+""", then the """+metricsToPlot[1]+""" concentration
        is higher than the """+metricsToPlot[0]+""" concentration and the top """+chartDict[countColumn]+"""s have a higher share of """+metricsToPlot[1]+""" compared to their share of """+metricsToPlot[0]+""". 
        If the """+chartDict[countColumn]+"""s that make up a 80% of """+metricsToPlot[1]+""" make up a lower 
        than 80% percentage of """+metricsToPlot[1]+""", the opposite is true.  
        If this line graph does not have a smooth, monotonic, growth pattern, but is jagged, with a sawtooth pattern this means that 
        some """+chartDict[countColumn]+"""s have negative """+metricsToPlot[1]+""". If this line graph does not have 
        a consistent color scheme but displays a mixture of colors this means that some  """+chartDict[countColumn]+"""s with similar levels of """+metricsToPlot[0]+""" 
        have very different levels of  """+metricsToPlot[1]+"""."""    
    if len(metricsToPlot)==3: 
        promptThirdMetric="""The third subchart utilizes the same Y-axis and is identically sorted. The line displays the cumulative """+metricsToPlot[2]+""" corresponding to the cumulative """+metricsToPlot[0]+""" levels.
        The colors correspond to the A, B, and C """+metricsToPlot[2]+""" classes of each """+chartDict[countColumn]+""".
        This is the concentration by """+metricsToPlot[2]+""": """+chartDict[plotCommentText][2]+""".    
        The """+chartDict[countColumn]+""" ranking (descending """+metricsToPlot[0]+""") is the same across all subcharts.
        Therefore if the """+chartDict[countColumn]+"""s that make up a 80% of """+metricsToPlot[0]+""" make up 
        a higher than 80% percentage of """+metricsToPlot[2]+""", then the """+metricsToPlot[2]+""" concentration
        is higher than the """+metricsToPlot[0]+""" concentration and the top """+chartDict[countColumn]+"""s have a higher share of """+metricsToPlot[2]+""" compared to their share of """+metricsToPlot[0]+""". 
        If the """+chartDict[countColumn]+"""s that make up a 80% of """+metricsToPlot[1]+""" make up a lower 
        than 80% percentage of """+metricsToPlot[2]+""", the opposite is true.  
        If this line graph does not have a smooth, monotonic, growth pattern, but is jagged, with a sawtooth pattern this means that 
        some """+chartDict[countColumn]+"""s have negative """+metricsToPlot[2]+""". If this line graph does not have 
        a consistent color scheme but displays a mixture of colors this means that some  """+chartDict[countColumn]+"""s with similar levels of """+metricsToPlot[0]+""" 
        have very different levels of  """+metricsToPlot[2]+""". 
        The third subchart utilizes the same Y-axis and is identically sorted. The line displays the cumulative """+metricsToPlot[2]+""" corresponding to the cumulative """+metricsToPlot[0]+""" levels. """   
    if len(metricsToPlot)==3: 
        promptApproach="""Proceed as follows:   
        (i) Provide textual interpretation of the data presented in the first subchart, detailing the number  """+chartDict[countColumn]+"""s in each class, as well as the correct 'intense', 'typical', 'moderate' or 'weak'  """+metricsToPlot[0]+""" concentration;     
        (ii) Provide textual interpretation of the data presented in the second subchart. Compare the concentration by """+metricsToPlot[1]+""" to the concentration values by """+metricsToPlot[0]+""". Check for jagged patterns and mixed color schemes;       
        (iii) Provide textual interpretation of the data presented in the third subchart. Compare the concentration by """+metricsToPlot[2]+""" to the concentration values by """+metricsToPlot[0]+""". Check for jagged patterns and mixed color schemes;  
        (iv) For each subchart and each class of """+chartDict[countColumn]+"""s, only provide fact-based evidences that can be derived from the chart presented to you. Do not make inferences or assumptions beyond the data presented in the chart.              
        """
    elif len(metricsToPlot)==2: 
        promptApproach="""Proceed as follows:   
        (i) Provide textual interpretation of the data presented in the first subchart, detailing the number  """+chartDict[countColumn]+"""s in each class, as well as the correct 'intense', 'typical', 'moderate' or 'weak'  """+metricsToPlot[0]+""" concentration;     
        (ii) Provide textual interpretation of the data presented in the second subchart. Compare the concentration by """+metricsToPlot[1]+""" to the concentration values by """+metricsToPlot[0]+""". Check for jagged patterns and mixed color schemes;       
        (iii) For each subchart and each class of """+chartDict[countColumn]+"""s, only provide fact-based evidences that can be derived from the chart presented to you. Do not make inferences or assumptions beyond the data presented in the chart.              
        """
    else:
        promptApproach="""Proceed as follows:   
        (i) Provide textual interpretation of the data presented in the first subchart, detailing the number  """+chartDict[countColumn]+"""s in each class, as well as the correct 'intense', 'typical', 'moderate' or 'weak'  """+metricsToPlot[0]+""" concentration;     
        (ii) For the chart and each class of """+chartDict[countColumn]+"""s, only provide fact-based evidences that can be derived from the chart presented to you. Do not make inferences or assumptions beyond the data presented in the chart.              
        """
    if is_valid_lazyframe(df):
        promptDf=""" In order to avoid error of visual interpretation of the provided image, the values in the charts are shown here:\n{}""".format(df)+"""."""     
    promptChart=promptDescription+promptSecondMetric+promptThirdMetric+promptDf+promptApproach
    return promptChart,df

def get_upset_prompt(df,chartDict):
    namingParams=get_naming_params()
    yAxisDimension=namingParams["yAxisDimension"]   
    upsetChart=namingParams["upsetChart"] 
    nothingFilteredName=namingParams["nothingFilteredName"]
    showAverageValue=namingParams["showAverageValueName"]  
    smallMultiplesCharts=namingParams["plotSmallMultiplesOtherCharts"]
    smallMultiplesColumn=namingParams["smallMultiplesColumn"]
    aggregateOtherItemsName=namingParams["aggregateOtherItemsName"]
    showValuesAs=namingParams["showValuesAs"] 
    metricsToPlot=namingParams["metricsToPlot"] 
    absolute=namingParams["absolute"] 
    numberOfTop=namingParams["numberOfTop"]
    selectedPeriods=namingParams["selectedPeriods"]  
    selectDimensionsToPlot=namingParams["selectDimensionsToPlot"]  
    numberOfPlottedSmallMultiplesKey=namingParams["numberOfPlottedSmallMultiples"]
    plotTitleText=namingParams["plotTitleText"]    
    if not isinstance(df, pl.DataFrame):
        df = pl.DataFrame(df)
    title=chartDict[plotTitleText]
    promptContext,companyOrIndustry,contextMetric=get_context(chartDict,False)
    title=replace_ibcs_date_symbol(title,chartDict) 
    promptContext,df=explain_currency_and_abbreviations(df,chartDict,promptContext,contextMetric)
    promptContext=add_prompt_date(promptContext,chartDict)
    promptFilter=add_prompt_filter(chartDict)
    promptDescription=""" The provided **"""+upsetChart+"""** chart image has the following title: '"""+title+"""'."""+promptContext+""""""+promptFilter+"""
        An **"""+upsetChart+"""** chart is a visualization tool used primarily for analyzing and understanding complex sets of intersections in large datasets. In an UpSet plot, the horizontal layout is a common presentation. Here's how to interpret it:
        Sets and Set Sizes: On the left side of the plot you will find the list of sets (categories or groups) in your data. Alongside, you will find a bar chart representing the size of each set – how many elements or data points it contains.    
        Intersections: The main part of the plot shows the intersections between these sets. Each column in this area represents a combination of sets. For instance, if there are sets A, B, and C, you would see columns representing A∩B, A∩C, B∩C, A∩B∩C, etc.
        Intersection Sizes: The height of the bars in the intersection area indicates the size of each intersection – how many elements are common between the sets involved.
        Indicators for Set Inclusion in Intersections: Below the intersection bars, there are often dots or lines that indicate which sets are included in each intersection. For example, a column with dots under A and B but not C indicates the intersection of A and B (excluding C).
        Sorting and Ordering: The arrangement of the sets and their intersections can be sorted in various ways – by set size, intersection size, or even based on a particular pattern in the data. This can help in identifying the most significant relationships or patterns.  """
    promptFact=""" Only provide fact-based evidences that can be derived from the data presented to you. Do not make inferences or assumptions beyond the data presented in the chart."""   
    promptChart=promptDescription+promptFact
    return promptChart,df

def get_multitier_column_prompt(df,chartDict):
    namingParams=get_naming_params()
    yAxisDimension=namingParams["yAxisDimension"]   
    multitierColumnChart=namingParams["multitierColumnChart"] 
    nothingFilteredName=namingParams["nothingFilteredName"]
    showAverageValue=namingParams["showAverageValueName"]  
    smallMultiplesCharts=namingParams["plotSmallMultiplesOtherCharts"]
    smallMultiplesColumn=namingParams["smallMultiplesColumn"]
    aggregateOtherItemsName=namingParams["aggregateOtherItemsName"]
    showValuesAs=namingParams["showValuesAs"] 
    metricsToPlot=namingParams["metricsToPlot"] 
    absolute=namingParams["absolute"] 
    numberOfTop=namingParams["numberOfTop"]
    selectedPeriods=namingParams["selectedPeriods"]  
    selectDimensionsToPlot=namingParams["selectDimensionsToPlot"]  
    numberOfPlottedSmallMultiplesKey=namingParams["numberOfPlottedSmallMultiples"]
    plotTitleText=namingParams["plotTitleText"]    
    if not isinstance(df, pl.DataFrame):
        df = pl.DataFrame(df)
    title=chartDict[plotTitleText]
    title=title.replace("<BR>"," ")    
    promptDescription="""The **"""+multitierColumnChart+"""** chart compares two scenarios or periods over time showing  """+chartDict[metricsToPlot][0]+""" montly values for each scenario/period as well as the average total value. The monthly values are shown as partially overlapping columns. The most recent period is shown in black, while the previous period is shown in grey, with bar plotte underneath the black bars with a slight shift. 
    """
    promptChart=""
    if 1==1:
        promptOther,promptAverage="",""
        isOtherColumnRank=check_if_other_in_columns(df)
        if smallMultiplesCharts in chartDict and chartDict[smallMultiplesCharts] and selectDimensionsToPlot in chartDict and len(chartDict[selectDimensionsToPlot])>1:
            promptOther=""" If a 'Other rank > x' small multiples plot is shown, it shows the aggregation of all remaining smaller items. """
            promptVariance=""" The chart shows absolute variances (with red - for 'bad' variances - and green - for 'good' variances - difference markers)."""
            promptChart="""This image shows a IBCS **"""+multitierColumnChart+"""** chart, with """+str(chartDict[numberOfPlottedSmallMultiplesKey])+""" small multiples plots plotted by """+chartDict[selectDimensionsToPlot][1]+""". """+promptDescription+""" """+promptVariance+""" """
        else:
            promptVariance=""" The chart shows both absolute (with red or green columns) and percent (with red and green pins) variances."""
            promptChart="""This image shows a IBCS **"""+multitierColumnChart+"""** chart. """+promptDescription+""" """+promptVariance+""" """   
    promptFact=""" Only provide fact-based evidences that can be derived from the data presented to you. Do not make inferences or assumptions beyond the data presented in the chart."""   
    promptChart=promptChart+promptOther+promptFact
    return promptChart

def get_chart_prompt_user(df,chartDict,fileName):
    """
    Display short explanation of plot type
    """   
    namingParams=get_naming_params() 
    alternativeCombinationsChart=namingParams["alternativeCombinationsChart"]
    timelineChart=namingParams["timelineChart"]
    stackedColumnChart=namingParams["stackedColumnChart"] 
    stackedBarChart=namingParams["stackedBarChart"]  
    barChart=namingParams["barChart"]  
    multitierBarChart=namingParams["multitierBarChart"]
    multitierColumnChart=namingParams["multitierColumnChart"] 
    horizontalWaterfallChart=namingParams["horizontalWaterfallChart"]       
    paretoChart=namingParams["paretoChart"] 
    stackedParetoChart=namingParams["stackedParetoChart"] 
    areaChart=namingParams["areaChart"]
    slopeChart=namingParams["slopeChart"]
    vennChart=namingParams["vennChart"]
    upsetChart=namingParams["upsetChart"]
    dotChart=namingParams["dotChart"]
    kernelDensity=namingParams["kernelDensityChart"]
    histogramChart=namingParams["histogramChart"]
    boxplotChart=namingParams["boxplotChart"]
    stripplotChart=namingParams["stripplotChart"]   
    ecdfChart=namingParams["ecdfChart"]
    motionChart=namingParams["motionChart"]
    scatterChart=namingParams["scatterChart"]
    chosenChart=namingParams["chosenChart"]
    submitPlotLabel=namingParams["submitPlotLabel"]
    trendComparisonByPeriodChart=namingParams["trendComparisonByPeriodChart"]
    marimekkoChart=namingParams["marimekkoChart"]
    trendComparisonChart=namingParams["trendComparisonChart"] 
    varianceAnalysisChartKey=namingParams["varianceAnalysisChart"]
    processingChoice=namingParams["processingChoice"]
    runOneDimensionalAnalysis=namingParams["runOneDimensionalAnalysis"]     
    promptChart=""
    if chosenChart in chartDict:
          if chartDict[chosenChart] == alternativeCombinationsChart:
                  ui.caption(message+"""✳️The **"""+alternativeCombinationsChart+"""** chart shows, for each dimension of a given row result, the variance value that results 
                   by changing the filter on that specific dimension.""")
          elif chartDict[chosenChart] == areaChart:
            promptChart=get_area_prompt(df,chartDict)
          elif chartDict[chosenChart] == boxplotChart:
            promptChart=get_boxplot_prompt(df,chartDict)            
          elif chartDict[chosenChart] == dotChart:
                  ui.caption("""✳️The **"""+dotChart+"""** chart is a composite chart with circles and lines. 
                   It is ideal for illustrating change while retaining the information about the absolute values.""")
          elif chartDict[chosenChart] == ecdfChart:
            promptChart=get_ecdf_chart_prompt(df,chartDict)
          elif chartDict[chosenChart] == histogramChart:
            promptChart=get_histogram_chart_prompt(df,chartDict)     
          elif chartDict[chosenChart] == kernelDensity:
            promptChart=get_kernel_density_prompt(df,chartDict,fileName)  
          elif chartDict[chosenChart] == motionChart:
                  ui.caption("""✳️The **"""+motionChart+"""** chart shows three metrics (for instance price, units sales and revenues) over time in a Gapminder-like graph. 
                              A plot is generated for each dimension.""")                                                            
          elif chartDict[chosenChart] == multitierColumnChart:
            promptChart=get_multitier_column_prompt(df,chartDict)
          elif chartDict[chosenChart] == paretoChart:
            promptChart,df=get_pareto_prompt(df,chartDict)            
          elif chartDict[chosenChart] == scatterChart:
                promptChart,df=get_scatter_prompt(df,chartDict,fileName)             
          elif chartDict[chosenChart] == slopeChart:
                  ui.caption(message+"""✳️The **"""+slopeChart+"""** chart shows the value of the available metrics in t0 and t1 in absolute value or as % of the total.
                   A set of plots is generated for each dimension.""")                  
          elif chartDict[chosenChart] == stripplotChart:
            promptChart=get_strip_plot_prompt(df,chartDict)   
          elif chartDict[chosenChart] == trendComparisonChart:
                  ui.caption("""✳️The **"""+trendComparisonChart+"""** plot compares two timelines showing the differences with red and green areas. 
                  Click on the ➕ expander below for more options.                    
                              """)
          elif chartDict[chosenChart] == trendComparisonByPeriodChart:
                  ui.caption("""✳️The **"""+trendComparisonByPeriodChart+"""** chart shows this year vs previous year 
                              performance along different time spans.  """)                                              
          elif chartDict[chosenChart] == upsetChart:
            promptChart,df=get_upset_prompt(df,chartDict)           
          elif chartDict[chosenChart] == vennChart:
                  ui.caption("""✳️The **"""+vennChart+"""** plot uses circles to show the relationships among things. 
                    Circles that overlap have a commonality while circles that do not overlap do not share those traits.                   
                              """)               
    elif varianceAnalysisChartKey in chartDict and chartDict[varianceAnalysisChartKey] and chartDict[processingChoice] in [runOneDimensionalAnalysis]:
        pass
    promptComment=" Provide textual interpretation of the data seen in the chart, followed by analysis and insights. "
    promptUser=promptComment+promptChart
    #ui.caption(promptUser)
    if chosenChart in chartDict and chartDict[chosenChart] in []:
        ui.caption(promptUser)
    return promptUser

def get_image_prompt(imgBytes,df,chartDict,paramDict,fileName,uploadedfileName):
    if not isinstance(df, pl.DataFrame):
        df = pl.DataFrame(df)
    namingParams=get_naming_params()
    chosenChart=namingParams["chosenChart"]
    vennChart=namingParams["vennChart"]
    upsetChart=namingParams["upsetChart"]
    smallMultiplesCharts=namingParams["plotSmallMultiplesOtherCharts"]
    errorMessageType=namingParams["errorMessageType"]
    plotChartsTabKey=namingParams["plotChartsTab"]
    chartImagePromptDict=namingParams["chartImagePromptDict"]
    colNumber=0   
    fileFormat="png"
    response={}
    if fileName+"."+fileFormat==uploadedfileName:
        promptUser=get_chart_prompt_user(df,chartDict,fileName)
        ui.caption(promptUser)
        add_prompt_chart_image_to_dictionary(promptUser,imgBytes,fileName)
        #1111111111111111
    else:
        message="The uploaded chart does not correspond to the plotted chart. You uploaded the "+uploadedfileName+" file instead of "+fileName+"."+fileFormat
        ui.caption(":red["+message+"]")      
    return paramDict

def get_comments_from_data_fragment(
    fig, df, chosenDimension, chartDict, paramDict, fileName
):
    df = ensure_polars_df(df)
    namingParams=get_naming_params()
    columnHash=paramDict[namingParams["columnHash"]] 
    getChartCommentLabel=namingParams["getChartCommentLabel"]  
    smallMultiplesCharts=namingParams["plotSmallMultiplesOtherCharts"]
    submitCommentName=namingParams["submitCommentName"]
    varianceAnalysisChartKey=namingParams["varianceAnalysisChart"]
    processingChoice=namingParams["processingChoice"]
    runOneDimensionalAnalysis=namingParams["runOneDimensionalAnalysis"]
    chartDataPromptDict=namingParams["chartDataPromptDict"]
    errorInFragment=namingParams["errorInFragment"]
    hashString=str(chartDict)
    hashKey=get_hashed_key(hashString,columnHash)          
    value=False
    response="" 
    submitted=False 
    disabled=False 
    if chartDataPromptDict in session_state:
        if fileName in session_state[chartDataPromptDict] and len(session_state[chartDataPromptDict][fileName])>0:
            disabled=False                      
    colArray=make_three_col_width_array()
    tooltip="""Add plot to report.""" 
    message="""✳️Add plot to report."""
    submitted=ui.button(label=getChartCommentLabel,help=tooltip,key=hashKey,disabled=disabled,type="primary")
    ui.caption(message) 
    if errorInFragment in session_state:
        del session_state[errorInFragment]
    if chartDataPromptDict not in session_state:
        session_state[chartDataPromptDict]={}  
    smallMultiplesKey="_No"
    if smallMultiplesCharts in chartDict and chartDict[smallMultiplesCharts]:
        smallMultiplesKey="_Yes"       
    if submitted and (fileName not in session_state[chartDataPromptDict]):
        session_state[submitCommentName] = True
        try:
            paramDict=get_data_prompt(df,paramDict,chartDict,chosenDimension,fileName)
        except Exception as e:
            e=print_error_details(e)
            logging.exception(e)
            ui.error("Something went wrong in get_comments_from_data_fragment.")
            session_state[errorInFragment]=True     
    elif submitted and fileName in session_state[chartDataPromptDict] and len(session_state[chartDataPromptDict][fileName])==0:
        session_state[submitCommentName] = True
        try:
            paramDict=get_data_prompt(df,paramDict,chartDict,chosenDimension,fileName)
        except Exception as e:
            e=print_error_details(e)
            logging.exception(e)
            ui.error("Something went wrong in get_comments_from_data_fragment.")
            session_state[errorInFragment]=True            
    elif submitted and fileName in session_state[chartDataPromptDict] and len(session_state[chartDataPromptDict][fileName])>0 :
        message="""**Plot not added. Plot already in file!**"""
        ui.caption(":red["+message+"]")
        pass
    else:
        pass
    isError=False
    if errorInFragment in session_state and session_state[errorInFragment]:            
        message="""**Error in fragment. Plot not loaded**"""
        ui.caption(":red["+message+"]")            
    return None 

def add_prompt_chart_data_to_dictionary(promptUser,fileName):
    namingParams=get_naming_params()
    chartImagePromptDict=namingParams["chartImagePromptDict"]
    chartDataPromptDict=namingParams["chartDataPromptDict"]
    if chartDataPromptDict not in session_state:
        session_state[chartDataPromptDict]={} 
    if len(promptUser)>0 and fileName not in session_state[chartDataPromptDict]:
        session_state[chartDataPromptDict][fileName]=promptUser
        numberOfPrompts=len(session_state[chartDataPromptDict])
        if chartImagePromptDict in session_state:
            numberOfPrompts=numberOfPrompts+len(session_state[chartImagePromptDict])
        numberOfPrompts=str(numberOfPrompts)
        message="""**Prompt #"""+numberOfPrompts+""" added!** Did you remember to save the plot?"""
        ui.caption(":green["+message+"]")
    elif len(promptUser)>0 and fileName in session_state[chartDataPromptDict]:   
        message="""**Prompt not added. Already present!**"""
        ui.caption(":red["+message+"]")
    return None

def add_prompt_chart_image_to_dictionary(promptUser,imgBytes,fileName):
    namingParams=get_naming_params()
    chartImagePromptDict=namingParams["chartImagePromptDict"]
    chartImageBytesDict=namingParams["chartImageBytesDict"]
    chartDataPromptDict=namingParams["chartDataPromptDict"]
    if chartImagePromptDict not in session_state:
        session_state[chartImagePromptDict]={} 
    if chartImageBytesDict not in session_state:
        session_state[chartImageBytesDict]={}         
    if len(promptUser)>0 and fileName not in session_state[chartImagePromptDict]:
        session_state[chartImagePromptDict][fileName]=promptUser
        session_state[chartImageBytesDict][fileName]=imgBytes
        numberOfPrompts=len(session_state[chartImagePromptDict])
        if chartDataPromptDict in session_state:
            numberOfPrompts=numberOfPrompts+len(session_state[chartDataPromptDict])        
        numberOfPrompts=str(numberOfPrompts)
        message="""**Prompt image #"""+numberOfPrompts+""" added!**"""
        ui.caption(":green["+message+"]")
    elif len(promptUser)>0 and fileName in session_state[chartImagePromptDict]:   
        message="""**Prompt image not added. Already present!**"""
        ui.caption(":red["+message+"]")
    return None

def get_data_prompt(dfCopy,paramDict,chartDict,column,fileName):
    namingParams=get_naming_params()
    selectDimensionsToPlot=namingParams["selectDimensionsToPlot"]
    totalName=namingParams["totalName"]
    errorMessageType=namingParams["errorMessageType"]
    plotChartsTabKey=namingParams["plotChartsTab"]
    barmekkoChart=namingParams["barmekkoChart"]  
    bubbleChart=namingParams["bubbleChart"]  
    horizontalWaterfallChart=namingParams["horizontalWaterfallChart"] 
    marimekkoChart=namingParams["marimekkoChart"] 
    multitierBarChart=namingParams["multitierBarChart"] 
    metricsToPlot=namingParams["metricsToPlot"] 
    stackedColumnChart=namingParams["stackedColumnChart"] 
    stackedParetoChart=namingParams["stackedParetoChart"] 
    timelineChart=namingParams["timelineChart"]
    stackedBarChart=namingParams["stackedBarChart"]  
    chosenChart=namingParams["chosenChart"]
    varianceAnalysisChartKey=namingParams["varianceAnalysisChart"]
    processingChoice=namingParams["processingChoice"]
    runOneDimensionalAnalysis=namingParams["runOneDimensionalAnalysis"]
    runVariableDimensionalAnalysis=namingParams["runVariableDimensionalAnalysis"]
    plotSmallMultiplesWaterfall=namingParams["plotSmallMultiplesWaterfall"]   
    synthesisPlot=namingParams["synthesisPlot"] 
    varianceDifferentCalculations=namingParams["varianceDifferentCalculations"] 
    if chosenChart in chartDict:           
        chosenChart=chartDict[chosenChart]
    else:
        chosenChart=False    
    colNumber=0
    df = duplicate_dataframe(dfCopy)
    if not isinstance(df, pl.DataFrame):
        df = pl.DataFrame(df)
    if chosenChart in [stackedColumnChart] and synthesisPlot in chartDict and chartDict[synthesisPlot]:
        pass
    elif chosenChart in [stackedColumnChart,stackedParetoChart,timelineChart] or chosenChart in [stackedBarChart] and len(chartDict[metricsToPlot])==2:
        df,metric=rename_metric_for_AI(df,paramDict,chartDict)         
        df=clean_dataframe_for_Ai(df,metric,column,chartDict)   
    if varianceAnalysisChartKey in chartDict and chartDict[varianceAnalysisChartKey] and chartDict[processingChoice] in [runOneDimensionalAnalysis]:
        if varianceDifferentCalculations in chartDict and chartDict[varianceDifferentCalculations]:
            promptUser,df=get_variance_prompt_multiple_calculations(df,chartDict)
        elif plotSmallMultiplesWaterfall in chartDict and chartDict[plotSmallMultiplesWaterfall]:
            promptUser,df=get_variance_prompt_small_multiples(df,chartDict)
        else:
            promptUser,df=get_variance_prompt_not_small_multiples(df,chartDict)   
    elif varianceAnalysisChartKey in chartDict and chartDict[varianceAnalysisChartKey] and chartDict[processingChoice] in [runVariableDimensionalAnalysis]:
        promptUser,df=get_variance_prompt_root_cause_analysis(df,chartDict)     
    elif chosenChart in [stackedColumnChart] and synthesisPlot in chartDict and chartDict[synthesisPlot]:
        promptUser,df=get_synthesis_stacked_column_prompt(df,chartDict) 
    elif chosenChart in [stackedColumnChart]: 
        promptUser,firstPeriod,lastPeriod,df=get_stacked_column_prompt(df,metric,column,paramDict,chartDict)
    elif chosenChart in [bubbleChart]:
        promptUser,df=get_bubble_prompt(df,chartDict) 
    elif chosenChart in [barmekkoChart]:
        promptUser,df=get_barmekko_prompt(df,chartDict)
    elif chosenChart in [horizontalWaterfallChart]:
        promptUser,df=get_horizontal_waterfall_prompt(df,chartDict)            
    elif chosenChart in [stackedParetoChart]:
        promptUser,df=get_stacked_pareto_prompt(df,chartDict)
    elif chosenChart in [timelineChart]:
        promptUser,df=get_timeline_chart_prompt(df,chartDict)    
    elif chosenChart in [stackedBarChart]:
        promptUser,df=get_stacked_bar_prompt(df,chartDict)
    elif chosenChart in [marimekkoChart]:
        promptUser,df=get_marimekko_prompt(df,chartDict)  
    elif chosenChart in [multitierBarChart]:
        promptUser,df=get_multitier_bar_prompt(df,chartDict) 
    promptComment="Provide textual interpretation of the data seen in the dataset, followed by analysis and insights. "
    promptUser=promptComment+promptUser
    ui.write(df)
    ui.caption(promptUser)
    #ui.caption(promptSystem)
    try:
        pass
        add_prompt_chart_data_to_dictionary(promptUser,fileName)
    except Exception as e:
        logging.exception(e)
        e=print_error_details(e)
        paramDict=add_app_message_to_paramdict(e,errorMessageType,plotChartsTabKey,paramDict,isMessage=True,isToast=True,colNumber=colNumber) 
        message="Unable to add prompt to dictionary."
        paramDict=add_app_message_to_paramdict(message,errorMessageType,plotChartsTabKey,paramDict,isMessage=True,isToast=True,colNumber=colNumber)
        pass 
    return paramDict

def get_comments_from_data(fig,df,chosenDimension,chartDict,paramDict,fileName):
    if not isinstance(df, pl.DataFrame):
        df = pl.DataFrame(df)
    namingParams=get_naming_params()
    columnHash=paramDict[namingParams["columnHash"]] 
    getChartCommentLabel=namingParams["getChartCommentLabel"]  
    smallMultiplesCharts=namingParams["plotSmallMultiplesOtherCharts"]
    submitCommentName=namingParams["submitCommentName"]
    varianceAnalysisChartKey=namingParams["varianceAnalysisChart"]
    processingChoice=namingParams["processingChoice"]
    runOneDimensionalAnalysis=namingParams["runOneDimensionalAnalysis"]
    chartDataPromptDict=namingParams["chartDataPromptDict"]
    errorInFragment=namingParams["errorInFragment"]
    hashString=str(chartDict)
    hashKey=get_hashed_key(hashString,columnHash)          
    value=False
    response="" 
    submitted=False 
    disabled=False 
    if chartDataPromptDict in session_state:
        if fileName in session_state[chartDataPromptDict] and len(session_state[chartDataPromptDict][fileName])>0:
            disabled=False                      
    colArray=make_three_col_width_array()
    tooltip="""Add plot to report.""" 
    message="""✳️Add plot to report."""
    submitted=ui.button(label=getChartCommentLabel,help=tooltip,key=hashKey,disabled=disabled,type="primary")
    ui.caption(message) 
    if errorInFragment in session_state:
        del session_state[errorInFragment]
    if chartDataPromptDict not in session_state:
        session_state[chartDataPromptDict]={}  
    smallMultiplesKey="_No"
    if smallMultiplesCharts in chartDict and chartDict[smallMultiplesCharts]:
        smallMultiplesKey="_Yes"       
    if submitted and (fileName not in session_state[chartDataPromptDict]):
        session_state[submitCommentName] = True
        try:
            paramDict=get_data_prompt(df,paramDict,chartDict,chosenDimension,fileName)
        except Exception as e:
            logging.exception(e)
            ui.error("Something went wrong while generating the data prompt.")
            session_state[errorInFragment]=True
    elif submitted and fileName in session_state[chartDataPromptDict] and len(session_state[chartDataPromptDict][fileName])==0:
        session_state[submitCommentName] = True
        try:
            paramDict=get_data_prompt(df,paramDict,chartDict,chosenDimension,fileName)
        except Exception as e:
            logging.exception(e)
            ui.error("Something went wrong while generating the data prompt.")
            session_state[errorInFragment]=True
    elif submitted and fileName in session_state[chartDataPromptDict] and len(session_state[chartDataPromptDict][fileName])>0 :
        message="""**Plot not added. Plot already in file!**"""
        paramDict=get_data_prompt(df,paramDict,chartDict,chosenDimension,fileName)
        ui.caption(":red["+message+"]")
        pass
    else:
        pass
    isError=False
    if errorInFragment in session_state and session_state[errorInFragment]:            
        message="""**Error in fragment. Plot not loaded**"""
        ui.caption(":red["+message+"]")            
    return None 

def get_comments_from_images(fig, df, chartDict, paramDict, fileName):
    """Return ``paramDict`` after processing comments for ``df``.

    Accept both ``DataFrame`` and ``LazyFrame`` inputs.
    """
    df = ensure_polars_df(df)
    namingParams=get_naming_params()
    columnHash=paramDict[namingParams["columnHash"]] 
    chosenChart=namingParams["chosenChart"]
    chartImagePromptDict=namingParams["chartImagePromptDict"]
    horizontalWaterfallChart=namingParams["horizontalWaterfallChart"] 
    multitierColumnChart=namingParams["multitierColumnChart"] 
    multitierBarChart=namingParams["multitierBarChart"]    
    smallMultiplesCharts=namingParams["plotSmallMultiplesOtherCharts"]
    submitCommentName=namingParams["submitCommentName"] 
    hashString=str(fileName)
    hashKey=get_hashed_key(hashString,columnHash) 
    value=False
    response="" 
    submitted=False 
    disabled=False 
    if chartImagePromptDict in session_state:
        if fileName in session_state[chartImagePromptDict] and len(session_state[chartImagePromptDict][fileName])>0 and "I'm sorry" not in session_state[chartImagePromptDict][fileName] :
            disabled=False 
    submitted,imgBytes,uploadedfileName=upload_plot_image(hashKey)
    if chartImagePromptDict not in session_state:
        session_state[chartImagePromptDict]={}  
    smallMultiplesKey="_No"
    if smallMultiplesCharts in chartDict and chartDict[smallMultiplesCharts]:
        smallMultiplesKey="_Yes" 
    if submitted and (fileName in session_state[chartImagePromptDict] and "I'm sorry" not in session_state[chartImagePromptDict][fileName]):
        session_state[submitCommentName] = True
        paramDict=get_image_prompt(imgBytes,df,chartDict,paramDict,fileName,uploadedfileName)
    elif submitted and (fileName in session_state[chartImagePromptDict] and "I'm sorry" in session_state[chartImagePromptDict][fileName]):
        session_state[submitCommentName] = True
        paramDict=get_image_prompt(imgBytes,df,chartDict,paramDict,fileName,uploadedfileName)
    elif submitted and fileName in session_state[chartImagePromptDict] and len(session_state[chartImagePromptDict][fileName])==0:
        if hashKey not in session_state:
            session_state[hashKey]=True                   
        session_state[submitCommentName] = True
        paramDict=get_image_prompt(imgBytes,df,chartDict,paramDict,fileName,uploadedfileName)
    elif submitted :
        session_state[submitCommentName] = True
        paramDict=get_image_prompt(imgBytes,df,chartDict,paramDict,fileName,uploadedfileName)                            
    elif fileName in session_state[chartImagePromptDict] and len(session_state[chartImagePromptDict][fileName])>0:
        message="""**Plot not added. Plot already in file!**"""
        ui.caption(":red["+message+"]")
        pass
    else:
        pass    
    return paramDict  
