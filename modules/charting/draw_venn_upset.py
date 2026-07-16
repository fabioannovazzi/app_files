# isort: off
# fmt: off
import polars as pl
from modules.utilities.ui_notifier import ui
import plotly.graph_objects as go
import copy
from io import BytesIO
import logging
from matplotlib_venn import venn2
from matplotlib_venn import venn3


from modules.charting.chart_primitives import (
    get_color_array,
    get_color_dictionary,
    insert_highlight_color,
)
from modules.charting.make_titles import make_venn_and_upset_charts_title
from modules.charting.setup_fig import setup_venn_figure
from modules.charting.upset_plot import plot_upset
from modules.data.common_data_utils import show_only_largest
from modules.data.misc_charts_data_prep import (
    prepare_data_for_upset_plot,
    prepare_data_for_venn_plot,
)

from modules.llm.confirm_plots import get_comments_from_images
from modules.utilities.config import (
    get_config_params,
    get_naming_params,
)
from modules.utilities.error_messages import (
    add_app_message_to_paramdict,
    add_empty_dataset_error_message_in_plot_charts_tab,
)
from modules.utilities.helpers import (
    check_if_periods_in_columns,
    clean_chartDict,
    duplicate_dataframe,
    print_error_details,
    get_image_name_hash,
)
from modules.layout.layout_helpers import make_four_col_width_array
from modules.utilities.utils import (
    ensure_lazyframe,
    get_row_count,
    is_valid_lazyframe,
)


































def set_col_array_for_upset(df,chartDict):
    namingParams=get_naming_params()
    plotSmallMultiplesKey=namingParams["plotSmallMultiplesOtherCharts"]
    numberOfRows=df.height
    if plotSmallMultiplesKey in chartDict and chartDict[plotSmallMultiplesKey]:
        colWidthArray=[1,1,1,1]   
    elif numberOfRows >100 :
        colWidthArray=[2,1,1,1]
    elif numberOfRows >50 :    
        colWidthArray=[1.5,1,1,1]
    else:    
        colWidthArray=[1,1,1,1]           
    colArray = ui.columns(colWidthArray)
    return colArray


def prepare_upset_chart_data(
    dfCopy, valueCols, chartDict, paramDict, period
) -> tuple[pl.DataFrame, pl.LazyFrame, str, str, str]:
    """Return data required for rendering an UpSet chart."""

    namingParams = get_naming_params()
    yAxisDimension = namingParams["yAxisDimension"]
    xAxisDimension = namingParams["xAxisDimension"]
    periodName = namingParams["periodName"]

    yColumn = chartDict[yAxisDimension]
    xColumn = chartDict[xAxisDimension]

    dfCopy, uniqueItems, _agg, _vals = show_only_largest(
        dfCopy,
        xColumn,
        yColumn,
        periodName,
        valueCols,
        chartDict,
        paramDict,
        "X",
    )

    df = duplicate_dataframe(dfCopy)
    df, period = check_if_periods_in_columns(df, period)
    df_new = prepare_data_for_upset_plot(df, xColumn, yColumn, period, uniqueItems)
    df_new_lazy = ensure_lazyframe(df_new)

    return df, df_new_lazy, xColumn, yColumn, period


def render_upset_chart(
    df_copy, value_cols, chart_dict, param_dict, period
) -> tuple[go.Figure, pl.DataFrame, pl.LazyFrame, str, str, str]:
    """Prepare data and return an UpSet chart figure."""

    df, df_new_lazy, x_col, y_col, period = prepare_upset_chart_data(
        df_copy, value_cols, chart_dict, param_dict, period
    )

    fig = go.Figure()
    circle_metric = ""
    if get_row_count(df_new_lazy) > 0:
        fig, circle_metric = draw_upset_chart(df_new_lazy, x_col, y_col, chart_dict)

    return fig, df, df_new_lazy, y_col, circle_metric, period


def organize_venn_chart(dfCopy,valueCols,chartDict,paramDict,period,text):
    namingParams=get_naming_params()    
    yAxisDimension=namingParams["yAxisDimension"]
    xAxisDimension=namingParams["xAxisDimension"]
    selectedPeriods=namingParams["selectedPeriods"]
    nothingThereString=namingParams["nothingThereString"]
    periodName=namingParams["periodName"]
    yColumn=chartDict[yAxisDimension]
    xColumn=chartDict[xAxisDimension]
    periodOrder=chartDict[selectedPeriods] 
    chosenChart=namingParams["chosenChart"]
    chosenChart=chartDict[chosenChart]
    dfCopy,uniqueItems,aggregateOtherItemsName,valueCols=show_only_largest(dfCopy,xColumn,yColumn,periodName,valueCols,chartDict,paramDict,"X")
    numberOfCircles=len(uniqueItems)
    if numberOfCircles >3 and aggregateOtherItemsName in uniqueItems:
        uniqueItems.remove(aggregateOtherItemsName)
        numberOfCircles=len(uniqueItems)
    colorDict=get_color_dictionary(chartDict)
    colorArray=get_color_array(colorDict,chartDict)
    colorArray=insert_highlight_color(xColumn,uniqueItems,colorArray,paramDict,chartDict) 
    colArray=make_four_col_width_array()
    with colArray[0]:
        if is_valid_lazyframe(dfCopy):
            df = duplicate_dataframe(dfCopy)
            df = df.filter(pl.col(yColumn) != nothingThereString)
            df, period = check_if_periods_in_columns(df, period)
            dfFiltered = df.filter(pl.col(periodName) == period)
            if dfFiltered.height > 0:
                setDict=prepare_data_for_venn_plot(dfFiltered,xColumn,yColumn,uniqueItems)
                fig,circleMetric,font,fontSize,plot=draw_venn_chart(numberOfCircles,setDict,colorArray,chartDict)
                title,paramDict,chartDict=make_venn_and_upset_charts_title(df,chosenChart,paramDict,yColumn,circleMetric,chartDict,period,text)
                setup_venn_figure(fig,title,font,fontSize,plot)
        else:
            paramDict=add_empty_dataset_error_message_in_plot_charts_tab(paramDict)              
    return paramDict

def draw_venn_chart(numberOfCircles,setDict,colorArray,chartDict):
    namingParams=get_naming_params()
    configParams=get_config_params()
    font=configParams[namingParams["fontChoice"]] 
    fontSize=configParams[namingParams["fontSizeText"]]  
    xAxisDimension=namingParams["xAxisDimension"]
    xColumn=chartDict[xAxisDimension]
    plt.rcParams["font.family"] = font
    fig, ax = plt.subplots(figsize=(7,7))
    dataArray=[]
    labelArray=[]
    if numberOfCircles==2:
        for element in setDict:
            labelArray.append(element)
            dataArray.append(setDict[element])
        vd=venn2(dataArray,set_labels=(labelArray),
                set_colors=(colorArray[0], colorArray[1]), alpha = 0.5,
                )
    elif numberOfCircles==3:
        for element in setDict:
            labelArray.append(element)
            dataArray.append(setDict[element])
        vd=venn3(dataArray,set_labels=(labelArray),
            set_colors=(colorArray[0], colorArray[1],colorArray[2]), alpha = 0.5,
            )
    if numberOfCircles in [2,3]: 
        plot=True  
        for text in vd.set_labels:  #change label size
            text.set_fontsize(fontSize)
            text.set_fontfamily(font)    
    else: 
        plot=False
    circleMetric=copy.deepcopy(xColumn)    
    circleMetric=circleMetric.replace("_","")               
    return fig,circleMetric,font,fontSize,plot

def save_upset_chart(fileName):
    img_buffer = BytesIO()
    plt.savefig(img_buffer, format='png', dpi=1200, bbox_inches='tight')
    img_buffer.seek(0)

    # Use ui.download_button to create a download link for the image
    label=" Download image"
    download_image_data(img_buffer,label,fileName)
    return None


def organize_upset_chart(dfCopy,valueCols,chartDict,paramDict,period,text,element):
    namingParams = get_naming_params()
    plotSmallMultiplesKey = namingParams["plotSmallMultiplesOtherCharts"]
    smallMultiplesColumnKey = namingParams["smallMultiplesColumn"]
    chosenChartKey = namingParams["chosenChart"]
    errorMessageType = namingParams["errorMessageType"]
    plotChartsTabKey = namingParams["plotChartsTab"]
    upsetChart = namingParams["upsetChart"]

    colNumber = 0
    chosenChart = chartDict[chosenChartKey]

    fig, df, dfNew, yColumn, circleMetric, period = render_upset_chart(
        dfCopy, valueCols, chartDict, paramDict, period
    )
    text=text.replace(" ","").replace(":","_")
    fileName=upsetChart+text
    if dfNew.height>0 :
        colArray=set_col_array_for_upset(df,chartDict)
        with colArray[0]:
            try:
                hashDict=clean_chartDict(chartDict,True,False,None)
                if not element:
                    hashDict[plotSmallMultiplesKey]=False
                    if smallMultiplesColumnKey in hashDict:
                        del hashDict[smallMultiplesColumnKey]
                hashkey,paramDict=get_image_name_hash(hashDict,False,paramDict)
                if len(hashkey)>1:
                    fileName=fileName+"__"+str(hashkey)
                # ``fig`` already created by ``render_upset_chart``
                title,paramDict,chartDict=make_venn_and_upset_charts_title(dfNew,chosenChart,paramDict,yColumn,circleMetric,chartDict,period,text)

                fig.update_layout(
                    title={
                        "text": title,
                        "x": 0.01,
                        "xanchor": "left",
                        "font": {"size": 12},
                    },
                    margin={"l": 35, "r": 25, "t": 96, "b": 45},
                )
                text=text.replace(" ","").replace(":","").replace(": ","")
                paramDict=get_comments_from_images(fig,dfNew,chartDict,paramDict,fileName)
            except Exception as e:
                logging.exception(e)
                errorMessage="Error in plotting. Minimum intersection size parameter setting might be too high." 
                e=print_error_details(e)
                paramDict=add_app_message_to_paramdict(e,errorMessageType,plotChartsTabKey,paramDict,isMessage=True,isToast=False,colNumber=colNumber) 
                paramDict=add_app_message_to_paramdict(errorMessage,errorMessageType,plotChartsTabKey,paramDict,isMessage=True,isToast=True,colNumber=colNumber)   
    else:
        paramDict=add_empty_dataset_error_message_in_plot_charts_tab(paramDict)                    
    return paramDict

def draw_upset_chart(
    df: pl.DataFrame | pl.LazyFrame,
    xColumn: str,
    yColumn: str,
    chartDict: dict,
) -> tuple[go.Figure, str]:
    """Return an UpSet chart figure and metric label.

    Parameters
    ----------
    df:
        ``polars`` ``DataFrame`` or ``LazyFrame`` containing boolean set columns.
    xColumn:
        Name of the x-axis column used for deriving the metric label.
    yColumn:
        Name of the y-axis column for highlighting.
    chartDict:
        Chart configuration dictionary.

    Returns
    -------
    tuple[go.Figure, str]
        The resulting Plotly figure and the derived metric name.
    """

    lf = df.lazy() if isinstance(df, pl.DataFrame) else df
    fig = plot_upset(lf, chartDict)

    circleMetric = copy.deepcopy(xColumn).replace("_", "")

    return fig, circleMetric
