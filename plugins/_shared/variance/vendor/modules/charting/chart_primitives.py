# fmt: off
# isort: skip_file
import copy
import logging
import math
from typing import Mapping, Tuple, Union

import numpy as np
import plotly.graph_objects as go
import polars as pl
from plotly.subplots import make_subplots

from modules.layout.memoization import check_collect, get_hashed_key
from modules.utilities.session_context import session_state
from modules.utilities.ui_notifier import ui
from modules.utilities.config import (
    get_config_params,
    get_metric_array_params,
    get_naming_params,
)
from modules.utilities.helpers import (
    drop_columns,
    unique,
)
from modules.layout.layout_helpers import make_two_col_width_array
from modules.utilities.utils import get_schema_and_column_names
from modules.charting.polars_helpers import get_unique_categories

BAIN_HIGHLIGHT_COLOR = "#CB2026"




















def preparare_parameters_for_each_variance_calculation(chartDict,element):
    namingParams=get_naming_params() 
    varianceAggregationKey=namingParams["varianceAggregation"] 
    runOneDimensionalAnalysis=namingParams["runOneDimensionalAnalysis"]
    colorDict=get_color_dictionary(chartDict)
    message=runOneDimensionalAnalysis
    chartDict[varianceAggregationKey]=element
    return chartDict,colorDict,message

def check_if_plan_or_py(labelArray): 
    """
    if plan we want to color in white if py in grey
    """
    configParams=get_config_params()
    namingParams=get_naming_params()
    planStemArray=configParams[namingParams["planStemArray"]]
    isExpectedData=False
    returnedArray=[]
    for label in labelArray:
      label=str(label)
      for element in planStemArray:
            if element in label.lower():
                  isExpectedData=True
    return isExpectedData,label


def save_values_to_dictionary(paramDict,df,dfDates,dfPeriods,dfAllPeriods,dfPlan,indexCols,valueCols,chartDict,toDrop,originalValueCols,colDict,tabDict,automateDict,planPlaybackDict):
    valueDict={ 
                "1":paramDict,
                "2":df, 
                "3":dfDates, 
                "4":dfPeriods, 
                "5":dfAllPeriods, 
                "6":dfPlan, 
                "7":indexCols, 
                "8":valueCols, 
                "9":chartDict, 
                "10":toDrop, 
                "11":originalValueCols, 
                "12":colDict, 
                "13":tabDict, 
                "14":automateDict, 
                "15":planPlaybackDict,                                                                                 
                }
    return valueDict

 

def change_array_of_metrics_if_cost_analysis(array,chartDict):
    namingParams=get_naming_params()
    datasetTypeKey=namingParams["datasetTypeName"]
    companySales=namingParams["companySales"]
    scanMarketData=namingParams["scanMarketData"]
    companyExpenses=namingParams["companyExpenses"]
    costsName=namingParams["costsName"]
    amountName=namingParams["monetaryLocalCurrencyName"]
    pricePerUnitName=namingParams["pricePerUnitName"]
    pricePerVolumeName=namingParams["pricePerVolumeName"]
    costPerUnitName=namingParams["costPerUnitName"]
    costPerVolumeName=namingParams["costPerVolumeName"] 
    pricePerUnitNetDiscountName=namingParams["pricePerUnitNetDiscountName"]
    costPerUnitNetDiscountName=namingParams["costPerUnitNetDiscountName"]
    pricePerVolumeNetDiscountName=namingParams["pricePerVolumeNetDiscountName"]
    costPerVolumeNetDiscountName=namingParams["costPerVolumeNetDiscountName"]  
    netUnitsPriceChangeName=namingParams["netUnitsPriceChangeName"]
    netUnitsCostChangeName=namingParams["netUnitsCostChangeName"]
    netVolumeCostChangeName=namingParams["netVolumeCostChangeName"]
    netVolumePriceChangeName=namingParams["netVolumePriceChangeName"]  
    metricDict={
            amountName:costsName,
            pricePerUnitName:costPerUnitName,
            pricePerVolumeName:costPerVolumeName,
            pricePerUnitNetDiscountName:costPerUnitNetDiscountName,
            pricePerVolumeNetDiscountName:costPerVolumeNetDiscountName, 
            netUnitsPriceChangeName:netUnitsCostChangeName,
            netVolumePriceChangeName:netVolumeCostChangeName,            
    }
    newArray=[]
    if len(array)>0:
        if datasetTypeKey in chartDict and chartDict[datasetTypeKey] in [companyExpenses]: 
            for metric in array:
                try:
                    metric=metric.strip()
                except Exception as e:
                    logging.exception("metric formatting error: %s", e)
                    ui.error("Something went wrong while formatting metrics.")
                if metric in metricDict:
                    metric=metricDict[metric]
                elif amountName in metric:
                    metric=metric.replace(amountName,costsName)
                newArray.append(metric)
            return newArray
        else:
            return array
    else:
        return array

def reset_row_and_column_counters(count,countCols,countRows,numberOfCols,numberOfRows,chartDict):
    """
    we reset the countCols counter if the have finished the row
    """
    namingParams=get_naming_params()
    rowName=namingParams["rowName"]
    columnName=namingParams["columnName"]
    plotSmallMultiplesKey=namingParams["plotSmallMultiplesOtherCharts"] 
    chosenChart=namingParams["chosenChart"]
    stackedBarChart=namingParams["stackedBarChart"]
    chosenChart=chartDict[chosenChart] 
    if chosenChart in [stackedBarChart]:
        if rowName in chartDict:
            countRows=chartDict[rowName]
        if columnName in chartDict:
            countCols=chartDict[columnName]        
    if plotSmallMultiplesKey in chartDict and chartDict[plotSmallMultiplesKey]:
        if countCols < numberOfCols:
          countCols=countCols+1
        else: 
          countCols=1     
          countRows=countRows+1            
    count=count+1
    chartDict[rowName],chartDict[columnName]=countRows,countCols
    return count,countRows,countCols,chartDict

def split_message_in_rows(message,fig):
    width=fig.layout.width
    minLength=int(width/9)
    for element in [1,2,3,4,5,6,7]:
        start=(minLength*element)
        index=message[start:].find(' ')
        if index != -1:
            index=start+index
            message=message[:index]+"<br>"+message[index:]
        else:
            break        
    return message

def add_title_as_annotation(fig,title,chosenChart,chartDict):
    namingParams=get_naming_params()
    configParams=get_config_params()
    fontSize=configParams[namingParams["fontSizeText"]]
    font=configParams[namingParams["fontChoice"]] 
    annotationDict=configParams[namingParams["annotationDict"]] 
    colorDict=get_color_dictionary(chartDict) 
    fig.add_annotation(
        text = title,
        xref = "paper",
        yref = "paper",
        x = annotationDict[chosenChart]["x"],
        y = annotationDict[chosenChart]["y"],
        align = annotationDict[chosenChart]["align"],
        xanchor = annotationDict[chosenChart]["xAnchor"],
        yanchor = annotationDict[chosenChart]["yAnchor"],
        showarrow = False,
        font = dict(
                    size=fontSize,
                    color = colorDict[annotationDict[chosenChart]["color"]],    
                                        )
                            )
    return fig 

def add_message_as_annotation(fig,message,column,chosenChart,chartDict,paramDict):
    namingParams=get_naming_params()
    configParams=get_config_params()
    font=configParams[namingParams["fontChoice"]] 
    fontSizeMessage=configParams[namingParams["fontSizeMessage"]] 
    fontSize=configParams[namingParams["fontSizeText"]] 
    annotationDict=configParams[namingParams["annotationDict"]] 
    alternativeCombinationsChart=namingParams["alternativeCombinationsChart"]
    totalName=namingParams["totalName"]
    areaChart=namingParams["areaChart"]
    barmekkoChart=namingParams["barmekkoChart"]
    boxplotChart=namingParams["boxplotChart"]
    bubbleChart=namingParams["bubbleChart"]
    dotChart=namingParams["dotChart"] 
    ecdfChart=namingParams["ecdfChart"]
    kernelDensityChart=namingParams["kernelDensityChart"]
    histogramChart=namingParams["histogramChart"]
    horizontalWaterfallChart=namingParams["horizontalWaterfallChart"]
    marimekkoChart=namingParams["marimekkoChart"] 
    motionChart=namingParams["motionChart"]
    multitierBarChart=namingParams["multitierBarChart"]
    multitierColumnChart=namingParams["multitierColumnChart"]
    paretoChart=namingParams["paretoChart"]
    scatterChart=namingParams["scatterChart"]
    slopeChart=namingParams["slopeChart"]
    stackedBarChart=namingParams["stackedBarChart"]
    stackedColumnChart=namingParams["stackedColumnChart"]
    stackedParetoChart=namingParams["stackedParetoChart"]
    stripplotChart=namingParams["stripplotChart"]
    timelineChart=namingParams["timelineChart"]
    plotSmallMultiplesKey=namingParams["plotSmallMultiplesOtherCharts"]    
    trendComparisonChart=namingParams["trendComparisonChart"]
    trendComparisonByPeriodChart=namingParams["trendComparisonByPeriodChart"]
    verticalWaterfallChart=namingParams["verticalWaterfallChart"]
    addMessage=False
    colorDict=get_color_dictionary(chartDict) 
    if message and addMessage: 
        message=split_message_in_rows(message,fig) 
        fig.update_layout(
                            margin={
                                "t": annotationDict[chosenChart]["topMargin"],
                                },              
                                )
        y=annotationDict[chosenChart]["y"]+annotationDict[chosenChart]["yshift"]
        if column and column == totalName:
            y=annotationDict[chosenChart]["y"]+(1.4) 
        elif chartDict and plotSmallMultiplesKey in chartDict and chartDict[plotSmallMultiplesKey]:
            y=annotationDict[chosenChart]["y"]+(annotationDict[chosenChart]["yshift"]*.1)
            if column and column == totalName:
                y=annotationDict[chosenChart]["y"]+(annotationDict[chosenChart]["yshift"]*.5)  
        fig.add_annotation(
            text = message,
            xref = "paper",
            yref = "paper",
            x = annotationDict[chosenChart]["x"],
            y = y,
            align = annotationDict[chosenChart]["align"],
            xanchor = annotationDict[chosenChart]["xAnchor"],
            yanchor = annotationDict[chosenChart]["yAnchor"],
            showarrow = False,
            font = dict(
                        size =fontSizeMessage, 
                        color = colorDict[annotationDict[chosenChart]["color"]],
                                            )
                                )
        color="lightgrey"
        lineWidth=0.5
        addLine=False
        if addLine:
            if chosenChart in [alternativeCombinationsChart,areaChart,barmekkoChart,boxplotChart,bubbleChart,ecdfChart,histogramChart,horizontalWaterfallChart,
                                kernelDensityChart,marimekkoChart,motionChart,multitierBarChart,
                               multitierColumnChart, paretoChart,scatterChart,slopeChart,stackedBarChart,stackedColumnChart,
                               stackedParetoChart,stripplotChart,
                               timelineChart,trendComparisonChart,trendComparisonByPeriodChart,verticalWaterfallChart]:             
                constant=.05
                y=1.+annotationDict[chosenChart]["yshift"]+constant
                if column and column == totalName:
                    y=annotationDict[chosenChart]["y"]+(1.4) 
                elif chartDict and plotSmallMultiplesKey in chartDict and chartDict[plotSmallMultiplesKey]:
                    y=annotationDict[chosenChart]["y"]+(annotationDict[chosenChart]["yshift"]*.1)
                    if column and column == totalName:
                        y=annotationDict[chosenChart]["y"]+(annotationDict[chosenChart]["yshift"]*.5)
                yref="paper"
                fig.add_shape(
                            type="line",
                            fillcolor=color,
                            opacity=1, 
                            line_width=lineWidth,
                            line_color=color,
                            x0=0, x1=1, xref="paper",
                            y0=y, 
                            y1=y, 
                            yref=yref,
                                )                
            elif chosenChart in [dotChart]:
                y = annotationDict[chosenChart]["y"]+annotationDict[chosenChart]["yshift"]
                yref="y domain"
                fig.add_hline(
                            y=y,
                            opacity=1, 
                            line_width=lineWidth,
                            line_color=color,
                            yref=yref,
                            )                                       
    return fig

def get_user_message(fig,chosenChart,period,column,paramDict,chartDict,df,maxLength,numberOfItemsInCol):
    """
    permits to add annotation under title in chart
    """ 
    namingParams=get_naming_params()
    configParams=get_config_params()
    font=configParams[namingParams["fontChoice"]]
    fontSize=configParams[namingParams["fontSizeText"]]  
    annotationDict=configParams[namingParams["annotationDict"]] 
    addMessageLabel=namingParams["addMessageLabel"]
    submitPlotLabel=namingParams["submitPlotLabel"] 
    columnHash=paramDict[namingParams["columnHash"]]
    showMessageWidget=False
    message=False
    colorDict=get_color_dictionary(chartDict)
    colArray=make_two_col_width_array()
    if showMessageWidget: 
        with colArray[0]: 
            chartKey=chosenChart+period
            if column:
                chartKey=chosenChart+column    
            hashKey=get_hashed_key(chartKey,columnHash)
            if hashKey in session_state:
                message=session_state[hashKey]
            else:
                message=False
            messageLength=0    
            if message:    
                messageLength=len(message)    
            value0="Add a message to the chart by typing it in the text box. Print long messages on more lines by adding a BR HTML tag"
            value1=""
            value=value1
            helpMessage="Hit "+submitPlotLabel+" each time you finished writing a message to record it"
            userInput = ui.text_input(label=addMessageLabel, value=value, max_chars=annotationDict[chosenChart]["maxChars"], 
                        key=hashKey,help=helpMessage,label_visibility="visible")   
    return fig,message
  
def apply_color(val):
    """
    Takes a scalar and returns a string with
    the css property `'color: red'` for negative
    strings, black otherwise.
    """
    color = 'black' 
    if val in colorGlobalDict:
        color=colorGlobalDict[val]
    else:
        color = 'black' 
    return 'color: %s' % color
  
def set_other_color_to_grey(rankedArray,aggregateOtherItemsName,colorArray,chartDict,shift):
    namingParams=get_naming_params()
    colorDict=get_color_dictionary(chartDict)
    otherColor=colorDict["veryLightGreyColor"] 
    testArray=[]
    testString=aggregateOtherItemsName.lower().replace(" ", "")
    for element in rankedArray:
        testArray.append(str(element).lower().replace(" ", ""))
    count=0
    isOther=False
    for item in testArray:
        if testString in item:
            otherIndex=count
            isOther=True
        else:
            pass
        count=count+1    
    if isOther: 
        if otherIndex >0 :
            colorArray.insert(otherIndex+shift,otherColor)
        elif len(rankedArray) > len(colorArray):
            colorArray.append(otherColor)
    return colorArray 

def track_used_colors(usedColorDict,array,aggregateOtherItemsName,colorArray):
    if not colorArray:
        return usedColorDict
    countColors = len(usedColorDict)
    palette_len = len(colorArray)
    for element in array:
        if aggregateOtherItemsName and aggregateOtherItemsName not in str(element):
            if element not in usedColorDict:
                usedColorDict[element] = colorArray[countColors % palette_len]
                countColors += 1
    return usedColorDict

def insert_highlight_color(column,rankedArray,colorArray,paramDict,chartDict):
    namingParams=get_naming_params()
    highlightedDimension=namingParams["highlightedDimension"]
    totalName=namingParams["totalName"]
    colorDict=get_color_dictionary(chartDict)
    highlightColor=get_hightlight_color(chartDict,colorDict) 
    lowerRankedArray=[]
    lowerHighlightedArray=[]
    if column != totalName or not column:
        if highlightedDimension in chartDict and len(chartDict[highlightedDimension])>0:
            highlightedDimensionArray=chartDict[highlightedDimension]
            for element in rankedArray:
                lowerRankedArray.append(element.lower())    
            for element in highlightedDimensionArray:
                lowerHighlightedArray.append(element.lower()) 
            if len(lowerHighlightedArray) <= len(colorArray):
                for element in lowerHighlightedArray:
                    if element in lowerRankedArray:
                        found=lowerRankedArray.index(element)
                        colorArray[found]=highlightColor                           
    return colorArray 

# Function to convert RGB to hex
def rgb_to_hex(rgb_color):
    return '#{:02x}{:02x}{:02x}'.format(int(rgb_color[0]), int(rgb_color[1]), int(rgb_color[2]))



def hex_to_rgb(hex_color):
    hex_color = hex_color.lstrip('#')
    return tuple(int(hex_color[i:i+2], 16) for i in (0, 2, 4))


def modify_color_array(hex_colors, counter):
    if counter == 0: 
        return hex_colors
    else:
        return [modify_color(color, counter) for color in hex_colors]

def modify_color(hex_color, counter):
    rgb = hex_to_rgb(hex_color)
    hls = colorsys.rgb_to_hls(rgb[0] / 255, rgb[1] / 255, rgb[2] / 255)
    # Shift to distinct hue groups but keep subtle variations within the family
    if counter == 6:  # Keep the original hue, but subtle adjustments in lightness or saturation
        hls = (hls[0], min(1, hls[1] + 0.05), max(0, hls[2] - 0.05))
    elif counter == 2:  # Shift to a more orange/red tone with subtle saturation changes
        hls = ((hls[0] + 0.08) % 1, hls[1], hls[2] + 0.03)
    elif counter == 3:  # Shift to a yellow/green hue family but keep saturation close to the original
        hls = ((hls[0] + 0.15) % 1, hls[1], hls[2] + 0.02)
    elif counter == 4:  # Shift towards the green family with slight saturation boost
        hls = ((hls[0] + 0.25) % 1, hls[1] + 0.05, hls[2])
    elif counter == 5:  # Shift towards blue but reduce lightness to create contrast
        hls = ((hls[0] + 0.4) % 1, hls[1], hls[2] - 0.05)
    elif counter == 1:  # Shift towards purple but with minimal changes to saturation/lightness
        hls = ((hls[0] + 0.55) % 1, hls[1], hls[2])
    else:  # For more than 6 columns, keep a random but subtle hue shift
        hls = ((hls[0] + random.uniform(0.0, 0.05)) % 1, hls[1], hls[2])

    # Ensuring proper rounding for RGB values between 0 and 255
    rgb_adjusted = [max(0, min(255, round(c * 255))) for c in colorsys.hls_to_rgb(hls[0], hls[1], hls[2])]
    return rgb_to_hex(rgb_adjusted)


def set_decimals_and_percent_suffix(df: pl.LazyFrame, metric, outColumn, chartDict):
    namingParams        = get_naming_params()
    metricArrayParams   = get_metric_array_params()
    percentMetricsArray = metricArrayParams[namingParams["percentMetricsArray"]]
    stackedColumnMetric = namingParams["stackedColumnMetric"]
    plotValuesAsChoice  = namingParams["plotValuesAsChoice"]
    showValuesAs        = namingParams["showValuesAs"]
    absolute            = namingParams["absolute"]
    percentOfColumnTotal= namingParams["percentOfColumnTotal"]
    percentOfRowTotal   = namingParams["percentOfRowTotal"]
    percentOfTotal      = namingParams["percentOfTotal"]
    chosenChart         = namingParams["chosenChart"]
    paretoChart         = namingParams["paretoChart"]
    stackedParetoChart  = namingParams["stackedParetoChart"]
    showAbsoluteValues  = namingParams["showAbsoluteValues"]
    columns, schema = get_schema_and_column_names(df)
    decimals = 1
    
    if metric not in columns:
        # Possibly do something or just pass
        pass

    # Similar logic to your original code:
    if metric in percentMetricsArray or (
        stackedColumnMetric in chartDict
        and chartDict[stackedColumnMetric] in percentMetricsArray
        and metric == chartDict[stackedColumnMetric]
    ):
        decimals      = 1
        percentSuffix = "%"
        multiplier    = 1
    elif (chartDict and plotValuesAsChoice in chartDict and chartDict[plotValuesAsChoice] != absolute):
        decimals      = 0
        percentSuffix = "%"
        multiplier    = 1
    elif (chartDict and showValuesAs in chartDict and chartDict[showValuesAs] in [percentOfTotal, percentOfRowTotal, percentOfColumnTotal]):
        decimals      = 0
        percentSuffix = "%"
        multiplier    = 1
    elif (chartDict and chosenChart in chartDict and chartDict[chosenChart] in [stackedParetoChart]):
        if outColumn == namingParams["workColumn"]:
            decimals      = 0
            percentSuffix = ""
            multiplier    = 1
        else:
            decimals      = 0
            percentSuffix = "%"
            multiplier    = 1
    elif (chartDict and chosenChart in chartDict and chartDict[chosenChart] in [paretoChart]):
        if showAbsoluteValues in chartDict and chartDict[showAbsoluteValues]:
            decimals      = 0
            percentSuffix = ""
            multiplier    = 1
        else:
            decimals      = 0
            percentSuffix = "%"
            multiplier    = 1
    else:
        decimals      = 1
        percentSuffix = ""
        multiplier    = 1

    return metric, decimals, percentSuffix, multiplier

def round_cast_string(col: str, decimals: int, is_int: bool = True) -> pl.Expr:
    """
    Rounds a column to 'decimals' places, casts to int or float, then to string.
    """
    rounded = pl.col(col).round(decimals)
    if is_int:
        return rounded.cast(pl.Int64).cast(pl.Utf8)
    else:
        return rounded.cast(pl.Float64).cast(pl.Utf8)

def SetColorRedToGreen(x):
    colorDict={
                  "redColor":"#FF0000",#"#C04040",
                  "greenColor":"#7ACA00",
                  "greyColor":"#404040",#
                  "lightGreyColor":"#a6a6a6",
                  "veryLightGreyColor":"#D9D9D9",
                  "veryVeryLightGreyColor":"#e6e6e6",                  
                  "bainhighlightColor":BAIN_HIGHLIGHT_COLOR,
                  "whiteColor":"#FFFFFF",
                  "blackColor":"#343434",
                  "almostBlackColor":"#2b2b2b",
                  "blueColor":"#0065FF",
          }
    if(x < 1):
        return colorDict["greenColor"]
    else:
        return colorDict["redColor"]

def enable_draw_shapes(fig):
    fig.update_layout(
                  dragmode='drawrect',
                  # style of new shapes
                  newshape=dict(
                                line_color='#1E90FF',
                                line_width=3,
                                )
                                )
    return fig  

def SetColorGreenToRed(x):
    colorDict={
                  "redColor":"#7ACA00",
                  "greenColor":"#FF0000",#"#C04040",
                  "greyColor":"#404040",#"#404040"  "#7F7F7F"
                  "lightGreyColor":"#a6a6a6",
                  "veryLightGreyColor":"#D9D9D9",
                  "veryVeryLightGreyColor":"#e6e6e6",                  
                  "bainhighlightColor":BAIN_HIGHLIGHT_COLOR,
                  "whiteColor":"#FFFFFF",
                  "blackColor":"#343434",
                  "almostBlackColor":"#2b2b2b",
                  "blueColor":"#0065FF",
          }
    if(x < 1):
        return colorDict["redColor"]
    else:
        return colorDict["greenColor"]

def get_hightlight_color(chartDict,colorDict):
    namingParams=get_naming_params()
    colorpalette=namingParams["colorpalette"]
    bainColorpalette=namingParams["bainColorpalette"]
    highlightColor=colorDict["blueColor"] 
    if colorpalette in chartDict and chartDict[colorpalette] in [bainColorpalette]:
        highlightColor=colorDict["bainhighlightColor"] 
    return highlightColor

def SetColorBlueToOrange(x):
    colorDict={
            "redColor":"#FF7F0E",
            "greenColor":"#1F77B4",
             "greyColor":"#404040",#"#404040"  "#7F7F7F"
              "lightGreyColor":"#a6a6a6", 
              "veryLightGreyColor":"#D9D9D9", 
            "veryVeryLightGreyColor":"#e6e6e6",                              
             "bainhighlightColor":BAIN_HIGHLIGHT_COLOR,
              "whiteColor":"#FFFFFF", 
            "blackColor":"#343434",  
            "almostBlackColor":"#2b2b2b",
            "blueColor":"#0065FF",  
          }
    if(x < 1):
        return colorDict["redColor"]
    else:
        return colorDict["greenColor"]

def get_color_array(colorDict,chartDict):
    namingParams=get_naming_params()
    colorpalette=namingParams["colorpalette"]
    cirqueColorpalette=namingParams["cirqueColorpalette"]
    if colorpalette in chartDict:
        colorArray=colorDict[chartDict[colorpalette]]
    else:
        colorArray=colorDict[cirqueColorpalette]
    return colorArray

def assign_same_colors_to_all_charts(colorArray,usedColorDict,sortedItems,aggregateOtherItemsName):
    """
    need to make sure that if one item has a color in period 0 it keeps the same colore the ozher period
    """
    usedColorsArray=[]
    notUsedColorsArray=[]
    newColorArray=[]
    for element in usedColorDict:
        if element not in sortedItems:
            notUsedColorsArray.append(usedColorDict[element])
        else:
            usedColorsArray.append(usedColorDict[element])
    for color in colorArray:
        if color not in usedColorsArray and color not in notUsedColorsArray:
            notUsedColorsArray.insert(0,color)                   
    count=0
    for element in sortedItems:
        if element in usedColorDict:
            newColorArray.append(usedColorDict[element])
        elif aggregateOtherItemsName and aggregateOtherItemsName not in element: 
            if len(notUsedColorsArray)> count:
                newColorArray.append(notUsedColorsArray[count])
                count=count+1
    for element in colorArray:
        if element not in newColorArray:
            newColorArray.append(element)                 
    return newColorArray


def get_color_dictionary(chartDict):
    """
    changes color palette based on user choice
    """    
    namingParams=get_naming_params()
    colorChoice=namingParams["colorChoice"] 
    redToGreen=namingParams["redToGreen"] 
    greenToRed=namingParams["greenToRed"] 
    blueToOrange=namingParams["blueToOrange"] 
    cirqueColorpalette=namingParams["cirqueColorpalette"] 
    modernColorpalette=namingParams["modernColorpalette"] 
    blueAndGreenColorpalette=namingParams["blueAndGreenColorpalette"] 
    khakiAndDenimColorpalette=namingParams["khakiAndDenimColorpalette"]      
    poloColorpalette=namingParams["poloColorpalette"]      
    heatingUpColorpalette=namingParams["heatingUpColorpalette"]    
    tableauColorpalette=namingParams["tableauColorpalette"] 
    thinkcellColorpalette=namingParams["thinkcellColorpalette"]  
    bainColorpalette=namingParams["bainColorpalette"]
    mckinseyColorpalette=namingParams["mckinseyColorpalette"]
    bcgColorpalette=namingParams["bcgColorpalette"]
    occColorpalette=namingParams["occColorpalette"]
    deloitteColorpalette=namingParams["deloitteColorpalette"] 
    powerbiColorpalette=namingParams["powerbiColorpalette"] 
    symphonyColorpalette=namingParams["symphonyColorpalette"] 
    IBCSColorpalette=namingParams["IBCSColorpalette"] 
    greysColorpalette=namingParams["greysColorpalette"] 
    bluesColorpalette=namingParams["bluesColorpalette"] 
    orangesColorpalette=namingParams["orangesColorpalette"] 
    purplesColorpalette=namingParams["purplesColorpalette"] 
    brownsColorpalette=namingParams["brownsColorpalette"] 
    if colorChoice in chartDict and chartDict[colorChoice] == redToGreen:
      colorDict={
                  "redColor":"#FF0000",#"#C04040",
                  "greenColor":"#7ACA00",#"#7ACA00"# "#8CB400"
                  "greyColor":"#404040",#"#404040"  "#7F7F7F"
                  "lightGreyColor":"#a6a6a6",
                  "veryLightGreyColor":"#D9D9D9",
                  "veryVeryLightGreyColor":"#e6e6e6",                  
                  "bainhighlightColor":BAIN_HIGHLIGHT_COLOR,
                  "whiteColor":"#FFFFFF",
                  "blackColor":"#343434",
                  "almostBlackColor":"#2b2b2b",
                  "blueColor":"#0065FF",
                  "transparentColor":"#FFFFFF",
          }
    elif colorChoice in chartDict and chartDict[colorChoice] == greenToRed:
      colorDict={
                  "redColor":"#7ACA00",
                  "greenColor":"#FF0000",#"#C04040",
                  "greyColor":"#404040",
                  "lightGreyColor":"#a6a6a6",
                  "veryLightGreyColor":"#D9D9D9",
                  "veryVeryLightGreyColor":"#e6e6e6",                       
                  "bainhighlightColor":BAIN_HIGHLIGHT_COLOR,
                  "whiteColor":"#FFFFFF",  
                  "blackColor":"#343434",
                  "almostBlackColor":"#2b2b2b", 
                  "blueColor":"#0065FF", 
                  "transparentColor":"#FFFFFF",                                                                    
    }
    elif colorChoice in chartDict and chartDict[colorChoice] == blueToOrange:
      colorDict={
            "redColor":"#FF7F0E",
            "greenColor":"#1F77B4",
             "greyColor":"#404040",#"#404040"  "#7F7F7F"
              "lightGreyColor":"#a6a6a6", 
              "veryLightGreyColor":"#D9D9D9", 
            "veryVeryLightGreyColor":"#e6e6e6",                              
             "bainhighlightColor":BAIN_HIGHLIGHT_COLOR,
              "whiteColor":"#FFFFFF", 
            "blackColor":"#343434",  
            "almostBlackColor":"#2b2b2b",
            "blueColor":"#0065FF",     
            "transparentColor":"#FFFFFF",                                           
            }
    else:
       colorDict={
                  "redColor":"#FF0000",#"#C04040",
                  "greenColor":"#7ACA00",##7ACA00"# "#8CB400"
                  "greyColor":"#404040",#"#404040"  "#7F7F7F"
                  "lightGreyColor":"#A6A6A6", 
                  "veryLightGreyColor":"#D9D9D9",  
                  "veryVeryLightGreyColor":"#E6E6E6",                                      
                  "bainhighlightColor":BAIN_HIGHLIGHT_COLOR,
                  "whiteColor":"#FFFFFF",
                  "blackColor":"#343434",
                  "almostBlackColor":"#2b2b2b",  
                  "blueColor":"#0065FF", 
                  "transparentColor":"#FFFFFF",                                 
          } 

    colorDict[cirqueColorpalette]=["#343434","#4E6551","#88A98C","#4395A7","#0F4E59","#5A3C4B",   
                                    "#B06B8B","#DDA567","#9F6027","#BE8E31","#EED069",
                                    "#4F5971", 
                            ]                         
    colorDict[modernColorpalette]=[ "#343434","#3C511B","#83905A","#7C982E","#C7EA5B","#854210",
                                    "#DA8545","#FFC293","#3C4255","#184243","#43C5D2",
                                    "#74E5E6", 
                            ] 
    colorDict[blueAndGreenColorpalette]=[ "#343434","#1B3643","#3B5C68","#597F8E","#7BA3AE","#ACD5E5",   
                                         "#776846","#6E7743","#4F5971", "#8B9450","#C4CA78",
                                         "#e7e9c9",
                            ]    
    colorDict[khakiAndDenimColorpalette]=[ "#343434","#2E2A18","#47462E","#777A4E","#AFB178","#e7e9c9",  
                                            "#2C373E","#607484","#9CBAD0","#8ca7bb","#CED7DD",
                                            "#6D7A9D",
                            ]  

    colorDict[poloColorpalette]=["#343434","#506B4E","#71917C","#685F4D","#A48C73","#2D4343",   
                                "#EFC84E","#BA8F2A","#CD685C","#923620","#5F838C",
                                "#4F5971",
                            ]  
    colorDict[heatingUpColorpalette]=["#245a58","#409781","#F3854D","#08425A", "#2A7D9B",  
                                        "#BFD83E","#52C4D8","#FFB93F","#a5e0eb","#dcf313",
                                        "#67BB48",
                            ]    
    colorDict[tableauColorpalette]=[ 
                                "#343434","#5778a4","#e49444","#79706e","#85b6b2","#d4a6c8",
                                "#e7ca60","#a87c9f","#f1a2a9","#967662","#b8b0ac",
                                "#9ecae9", 
                                "#e15759","#ff9d9a","#bab0ac","#d37295",
                                "#fabfd2","#b07aa1","#d4a6c8","#9d7660","#d7b5a6",                            
                            ] 
    colorDict[tableauColorpalette]=[ 
                               "#343434", "#5778a4","#e49444","#79706e","#85b6b2","#d4a6c8",
                                "#e7ca60","#a87c9f","#f1a2a9","#967662","#b8b0ac",
                                "#9ecae9",                             
                            ]                         
    colorDict[thinkcellColorpalette]=[ 
                                "#343434","#6da900","#2c4863","#787675","#9FC95C","#4f7403", 
                                "#034f7e","#00776f","#343434","#c0c2c1","#708cb5",
                                "#9cb1cc",                          
                            ]  
    colorDict[powerbiColorpalette]=[ 
                                "#343434","#12239E","#E66C37","#6B007B","#E044A7","#4b3231",
                                "#744EC2","#D9B300","#D64550","#eddeff","#bfe4ed",
                                "#FE6DB6", 
                                 ] 
    colorDict[symphonyColorpalette]=[ 
                                "#343434","#2159D6","#2A4870","#3FA9F5","#303442","#CCCCCC",
                                "#FF3F72","#7C42CE","#F7931E","#AF4141","#A499B3",
                                "#FFE100", 
                                 ]                             
    colorDict[IBCSColorpalette]=[ 
                                 "#343434","#808080","#FF7900","#AA8C00", "#FF008C","#b35500",
                                 "#9f7692","#5e4d00","#b30062","#514d89","#ddb600",
                                 "#dbacb0",
                                 ]
    colorDict[bainColorpalette]=[ 
                                "#343434","#999A9A","#818284","#58585A","#95A7B6","#748B9E", 
                                "#506E86","#B86D9B","#A43D7A","#891D59","#AB8933",
                                "#E9CD49",                          
                            ] 
    colorDict[mckinseyColorpalette]=[ 
                               "#343434", "#002960","#868685","#0065bd","#b5b38c","#009aa6", 
                                "#939d98","#006983","#7d9aaa","#D4ba00","#ad005b",
                                "#66307c",                          
                            ]   
    colorDict[bcgColorpalette]=[ 
                                "#343434","#00291C","#337B68","#025645","#BDD9CD","#D9B95B",
                                "#E6B437","#808080","#B3B3B3","#4D4D4D","#0076B8",
                                "#ADC0D7",                           
                            ] 
    colorDict[occColorpalette]=[ 
                                "#343434","#0053A1","#A7A9AC","#01B09C","#52C9E9","#BAD531",
                                "#7A3F97","#B9AD99","#E86C5D","#FFB25A","#666668",
                                "#B9E6DC",                           
                            ]
    colorDict[deloitteColorpalette]=[ 
                                "#343434","#1B6D77","#00ABAB","#43B02A","#86BC25","#C4D600",
                                "#7F897E","#ECF1B9","#80D5D5","#95a300","#D0D0CE",
                                "#6e7743",                           
                            ]                        
    colorDict[greysColorpalette]=[ 
                                 "#343434","#bdbdbd","#2F5574","#969696","#506D85",
                                 "#737373", "#738A9D", "#999999", "#96A7B6", "#666666", 
                                 "#B9C5CE", 
                            ]                                                                                                                                                                                                                                                                                                                                                                                                                          
    colorDict[bluesColorpalette]=[ 
                                 "#343434","#084594","#c6dbef","#2171b5","#9ecae1","#4292c6",
                                  "#CDE9FE","#6baed6","#B3F5FF","#008DA6","#ECF6FD",
                                 "#506D85",  
                                 ]                                                 
    colorDict[orangesColorpalette]=[ 
                                 "#343434","#8c2d04", "#fdd0a2","#d94801","#fdae6b","#f16913",
                                 "#fd8d3c","#CA6602","#FEEC9A","#F59B00","#FFE785",
                                 "#FFCD00",  
                                 ]                                  
    colorDict[purplesColorpalette]=[ 
                                 "#343434","#4a1486","#dadaeb","#6a51a3","#bcbddc", "#807dba",
                                 "#9e9ac8","#403294","#C0B6F2","#5243AA","#998DD9",
                                 "#6554C0",  
                                    ]                                                             
    colorDict[brownsColorpalette]=[ 
                                 "#343434","#660000","#CC6633","#663300","#CC9933", "#996600",
                                 "#996666","#8A0F0F","#E16666","#CA6602","#FFCD00", 
                                 "#F59B00", 
                            ] 

    colorDict["pastel"]=[
                                 "#aec7e8","#ffbb78","#98df8a","#ff9896","#c5b0d5",
                                 "#c49c94","#f7b6d2","#c7c7c7","#dbdb8d","#9edae5",
                            ]
    colorDict["bold"]=[
                                 "#1f77b4","#ff7f0e","#2ca02c","#d62728","#9467bd",
                                 "#8c564b","#e377c2","#7f7f7f","#bcbd22","#17becf",
                            ]
    colorDict["muted"]=[
                                 "#4b5563","#9ca3af","#6b7280","#d1d5db","#94a3b8",
                                 "#cbd5e1","#c4b5fd","#fbbf24","#fb7185","#22d3ee",
                            ]
                                                
    return colorDict



def add_sign_to_labels(
    df: Union[pl.DataFrame, pl.LazyFrame],
    chosenChart,
    metric,
    decimals,
    italic,
    chartDictCopy,
):
    namingParams=get_naming_params()
    labelName=namingParams["labelName"]
    differenceInPercent=namingParams["differenceInPercent"]
    verticalWaterfallChart=namingParams["verticalWaterfallChart"]
    horizontalWaterfallChart=namingParams["horizontalWaterfallChart"]
    varianceType=namingParams["varianceTypeName"]
    plotValuesAsChoice=namingParams["plotValuesAsChoice"]
    varianceAnalysisChart=namingParams["varianceAnalysisChart"]
    percentOfTotalDataset=namingParams["percentOfTotalDataset"]
    metConditionValue=namingParams["metConditionValue"]
    keepDecimalsAtZero=namingParams["keepDecimalsAtZero"]
    absolute=namingParams["absolute"]
    columns,_=get_schema_and_column_names(df)
    chartDict=copy.deepcopy(chartDictCopy)
    if varianceAnalysisChart in chartDict and chartDict[varianceAnalysisChart]: 
        chartDict[plotValuesAsChoice]=absolute
    if decimals >0:
        df,chartDict=millify_dataframe(df,metric,None,labelName,chartDict)
    elif decimals ==0:
        chartDict[plotValuesAsChoice]=percentOfTotalDataset
        chartDict[keepDecimalsAtZero]=metConditionValue
        df,chartDict=millify_dataframe(df,metric,None,labelName,chartDict)
    df=_assign_polars(df,labelName,pl.col(labelName).cast(pl.Utf8))
    if chosenChart in [verticalWaterfallChart] and varianceType in columns:
        cond=(pl.col(metric)>0)&(pl.col(varianceType)!="")
    elif chosenChart in [verticalWaterfallChart,horizontalWaterfallChart] and differenceInPercent in columns:
        cond=(pl.col(metric)>0)&pl.col(differenceInPercent).is_not_null()
    else:
        cond=pl.col(metric)>0
    expr=pl.when(cond).then(pl.concat_str([pl.lit("+"),pl.col(labelName)])).otherwise(pl.col(labelName))
    if italic:
        expr=pl.concat_str([pl.lit("<i>"),expr,pl.lit("<i>")])
    expr=pl.when(pl.col(metric).is_null()).then(pl.lit("")).otherwise(expr)
    df=_assign_polars(df,labelName,expr.cast(pl.Utf8))
    return df,chartDict

# helpers -------------------------------------------------------------
def _accepted_charts(np: dict) -> list[str]:
    return [
        np["stackedColumnChart"], np["stackedBarChart"],
        np["multitierColumnChart"], np["multitierBarChart"],
        np["horizontalWaterfallChart"], np["trendComparisonChart"],
        np["timelineChart"], np["areaChart"],
        np["slopeChart"], np["dotChart"],
        np["trendComparisonByPeriodChart"], np["marimekkoChart"],
    ]

_mill = {"t": 1_000_000_000_000,
         "b": 1_000_000_000,
         "m": 1_000_000,
         "k": 1_000,
         "": 1}



def adjust_decimals_IBCS(lf: pl.LazyFrame) -> pl.LazyFrame:
    namingParams = get_naming_params()
    np = namingParams                        # ← alias fixed

    # 1. mill divisor looked‑up lazily --------------------------------
    mill_divisor = (
        pl.col("prefix")
        .apply(lambda value: _mill.get(value, _mill[""]))
        .cast(pl.Int64, strict=False)
    )

    # 2. decimals expression ------------------------------------------
    decimals_expr = (
        pl.when(pl.col(np["keepDecimalsAtZero"]).fill_null(False))
          .then(pl.lit(np["notMetConditionValue"]))
          .otherwise(
              pl.when(pl.col(np["chosenChart"]).is_in(_accepted_charts(np)))
                .then(
                    (
                        3 - (
                            (pl.col("maxValue") / mill_divisor)
                              .cast(pl.Utf8)
                              .str.find(".")
                              .cast(pl.Int64)          # ← numeric cast added
                        )
                    ).clip(0, None)
                )
                .otherwise(pl.lit(np["notMetConditionValue"]))
          )
    )

    # 3. attach result (still lazy) -----------------------------------
    return lf.with_columns(decimals_expr.alias(np["IBCSdecimalName"]))

 

def change_metric_if_cost_analysis(metric,chartDict):
    namingParams=get_naming_params()
    datasetTypeKey=namingParams["datasetTypeName"]
    companySales=namingParams["companySales"]
    scanMarketData=namingParams["scanMarketData"]
    companyExpenses=namingParams["companyExpenses"]
    costsName=namingParams["costsName"]
    amountName=namingParams["monetaryLocalCurrencyName"]
    pricePerUnitName=namingParams["pricePerUnitName"]
    pricePerVolumeName=namingParams["pricePerVolumeName"]
    costPerUnitName=namingParams["costPerUnitName"]
    costPerVolumeName=namingParams["costPerVolumeName"] 
    priceName=namingParams["priceName"] 
    costName=namingParams["costName"]  
    metricDict={
            amountName:costsName,
            pricePerUnitName:costPerUnitName,
            pricePerVolumeName:costPerVolumeName,
    }
    if metric:
        if datasetTypeKey in chartDict and chartDict[datasetTypeKey] in [companyExpenses]:
            try:
                metric=metric.strip()
            except Exception as e:
                logging.exception("metric formatting error: %s", e)
                ui.error("Something went wrong while formatting metrics.")
            if metric in metricDict:
                metric=metricDict[metric]
            elif amountName in metric:
                metric=metric.replace(amountName,costsName)
            if priceName in metric:
                metric=metric.replace(priceName,costName)               
    return metric 

def divide_by_value_prefix(value,chartDict,metric): 
    namingParams=get_naming_params()
    notMetConditionValue=namingParams["notMetConditionValue"]
    metConditionValue=namingParams["metConditionValue"]
    valuePrefixName=namingParams["valuePrefixName"]   
    chosenChart=namingParams["chosenChart"]
    horizontalWaterfallChart=namingParams["horizontalWaterfallChart"] 
    valuePrefixDict=namingParams["valuePrefixDict"]    
    IBCSdecimalName=namingParams["IBCSdecimalName"]  
    millDict = {'t':1000000000000,'b':1000000000,'m':1000000,'k':1000,'':1}
    notFound=metConditionValue
    prefix=""
    roundValue=1 
    if metric:
        if valuePrefixDict in chartDict:
            if metric in chartDict[valuePrefixDict]:
                chartDict[valuePrefixName]=chartDict[valuePrefixDict][metric]
    if value and valuePrefixName in chartDict and chartDict[valuePrefixName]:
        value=value/millDict[chartDict[valuePrefixName]]
        if IBCSdecimalName in chartDict and chartDict[IBCSdecimalName] and chartDict[IBCSdecimalName]>=0:
            roundValue=chartDict[IBCSdecimalName]
        elif value>0.0001 and str(value).index(".")>2:
            roundValue=0    
        if isinstance(value, (pl.DataFrame, pl.LazyFrame)):
            value = value.with_columns(pl.all().round(roundValue))
            if roundValue == 0:
                value = value.with_columns(pl.all().cast(pl.Int64))
        else:
            value = round(value, roundValue)
            if roundValue == 0:
                value = int(value)
    else:  
        value=round(value,roundValue)                 
    return value


def millify(n,decimals):
    millnames = ['','k','m','b','t']
    millnames = ['','','','','']
    n = float(n)
    try:
        millidx = max(0,min(len(millnames)-1,
                        int(math.floor(0 if n == 0 else math.log10(abs(n))/3))))
    except Exception as e:
        logging.exception("metric formatting error: %s", e)
        ui.error("Something went wrong while formatting metrics.")
    millidx=0
    if decimals==0:
        return '{:.0f}{}'.format(n / 10**(3 * millidx), millnames[millidx])
    else:
        return '{:.1f}{}'.format(n / 10**(3 * millidx), millnames[millidx])

def add_workcolumns_to_millify(
    df: pl.LazyFrame,
    metric: str,
    outColumn: str,
    secondMetric: str,
    chartDict: dict
):
    namingParams       = get_naming_params()
    metricArrayParams  = get_metric_array_params()

    percentMetricsArray= metricArrayParams[namingParams["percentMetricsArray"]]
    growthMetricArray  = metricArrayParams[namingParams["growthMetricArray"]]
    stackedColumnMetric= namingParams["stackedColumnMetric"]
    chosenChart        = namingParams["chosenChart"]
    showValuesAs       = namingParams["showValuesAs"]
    percentOfColumnTotal = namingParams["percentOfColumnTotal"]
    percentOfRowTotal  = namingParams["percentOfRowTotal"]
    percentOfTotal     = namingParams["percentOfTotal"]
    showAbsoluteValues = namingParams["showAbsoluteValues"]
    stackPareto        = namingParams["stackedParetoChart"]
    pareto             = namingParams["paretoChart"]
    stackedBarChart    = namingParams["stackedBarChart"]
    metricsToPlot      = namingParams["metricsToPlot"]

    workColumnThree    = namingParams["workColumnThree"]
    workColumnFive     = namingParams["workColumnFive"]

    df = df.with_columns([
        pl.lit(0.0).alias(workColumnThree),   # initialize as float 0
        pl.lit(None).alias(workColumnFive)    # initialize as null
    ])

    columns, schema =get_schema_and_column_names(df)

    # Example: if ``metric`` is in ``percentMetricsArray`` we multiply it by
    # ``100`` and store the result in ``workColumnThree`` whenever ``metric`` is
    # present. This is implemented with ``pl.when``.

    # We'll do a chunk of the logic as your code had, all with 'when/then/otherwise'.
    # This can become quite verbose. Each "elif" can be a separate .with_columns(...) 
    # or you can nest logic. For simplicity, we might do a single chain of if/elif 
    # in Python, building a final expression to assign to workColumnThree.

    # Start with an expression that defaults to pl.col(workColumnThree)
    expr = pl.col(workColumnThree)

    # Based on your code, let's check each condition in sequence:
    if (metric in growthMetricArray + percentMetricsArray
        and chosenChart in chartDict
        and chartDict[chosenChart] in [stackedBarChart]
        and metric == chartDict[metricsToPlot][1]
    ):
        # expr => df[metric]
        expr = pl.when(pl.col(metric).is_not_null()) \
                 .then(pl.col(metric)) \
                 .otherwise(pl.col(workColumnThree))
        # fill null => 0 later
    elif (
        metric in percentMetricsArray
        or (
            stackedColumnMetric in chartDict
            and chartDict[stackedColumnMetric] in percentMetricsArray
            and metric == chartDict[stackedColumnMetric]
        )
    ):
        # multiply by 100
        expr = pl.when(pl.col(metric).is_not_null()) \
                 .then(pl.col(metric)*100) \
                 .otherwise(pl.col(workColumnThree))
    elif secondMetric and chosenChart in chartDict and showValuesAs in chartDict and chartDict[showValuesAs] == percentOfTotal:
        expr = (pl.col(metric)*pl.col(secondMetric))/pl.col(metric).sum()*100
    elif secondMetric and chosenChart in chartDict and showValuesAs in chartDict and chartDict[showValuesAs] == percentOfRowTotal:
        expr = (pl.col(metric)*pl.col(secondMetric))/pl.col(metric)*100
    elif secondMetric and chosenChart in chartDict and showValuesAs in chartDict and chartDict[showValuesAs] == percentOfColumnTotal:
        # multiply then divide by sum
        temp_expr = pl.col(metric) * pl.col(secondMetric)
        # Previously a conditional assignment checked ``workColumnThree != 0``.
        # Here we emulate that behaviour with ``pl.when`` for LazyFrames.
        expr = pl.when(temp_expr != 0) \
                 .then( (temp_expr / temp_expr.sum())*100 ) \
                 .otherwise(pl.lit(0.0))
    elif chosenChart in chartDict and chartDict[chosenChart] in [stackPareto]:
        if outColumn == namingParams["workColumn"]:
            # Fill ``workColumnThree`` with ``metric`` values when available
            # using ``pl.when``.
            expr = pl.when(pl.col(metric).is_not_null()) \
                     .then(pl.col(metric)) \
                     .otherwise(pl.col(workColumnThree))
        else:
            # multiply by 100
            expr = pl.when(pl.col(metric).is_not_null()) \
                     .then(pl.col(metric)*100) \
                     .otherwise(pl.col(workColumnThree))
    elif chosenChart in chartDict and chartDict[chosenChart] in [pareto]:
        if showAbsoluteValues in chartDict and chartDict[showAbsoluteValues]:
            expr = pl.when(pl.col(metric).is_not_null()) \
                     .then(pl.col(metric)) \
                     .otherwise(pl.col(workColumnThree))
        else:
            expr = pl.when(pl.col(metric).is_not_null()) \
                     .then(pl.col(metric)*100) \
                     .otherwise(pl.col(workColumnThree))
    elif secondMetric and chosenChart in chartDict and chartDict[chosenChart] not in [stackedBarChart]:
        expr = (pl.col(metric)*pl.col(secondMetric))
    elif secondMetric and chosenChart in chartDict and chartDict[chosenChart] in [stackedBarChart]:
        expr = pl.col(secondMetric)
    else:
        # default => fill from df[metric]
        expr = pl.when(pl.col(metric).is_not_null()) \
                 .then(pl.col(metric)) \
                 .otherwise(pl.col(workColumnThree))

    # Now apply the expression and fill null
    df = df.with_columns(expr.alias(workColumnThree))
    df = df.with_columns(pl.col(workColumnThree).fill_nan(0).fill_null(0))

    return df

def rename_columns_for_millify(df: pl.LazyFrame) -> pl.LazyFrame:
    namingParams = get_naming_params()
    acName       = namingParams["acName"] 
    pyName       = namingParams["pyName"] 
    plName       = namingParams["plName"]
    yearBeforePyName = namingParams["yearBeforePyName"]          

    renameDict = {
        acName.title(): acName,
        pyName.title(): pyName,
        plName.title(): plName,
        yearBeforePyName.title(): yearBeforePyName,
    }

    # Filter out old-name keys that do not exist
    existing_cols, schema =get_schema_and_column_names(df)
    renameDictFiltered = {
        old: new for old, new in renameDict.items() if old in existing_cols
    }

    # If nothing to rename, just return df
    if not renameDictFiltered:
        return df

    # Now rename only existing columns
    return df.rename(renameDictFiltered)




def get_number_prefix(
    lf: pl.LazyFrame,
    value_col: str,
    chartDict: dict,
    decimals: int,
    metric: str | None = None,
) -> tuple[str, dict, int]:
    if isinstance(lf, pl.DataFrame):
        lf = lf.lazy()
    np = get_naming_params()
    valuePrefixName, valuePrefixMetric, valuePrefixDict = (
        np["valuePrefixName"], np["valuePrefixMetric"], np["valuePrefixDict"]
    )

    mill_bounds = {"t": 1_000_000_000_000, "b": 1_000_000_000,
                   "m": 1_000_000, "k": 1_000, "": 0}

    # 1️⃣ build lazy frame with maxValue + prefix
    lazy = (
        lf.select(pl.col(value_col).abs().max().alias("maxValue"))
        .with_columns(
            pl.when(pl.col("maxValue") > mill_bounds["t"]).then(pl.lit("t"))
            .when(pl.col("maxValue") > mill_bounds["b"]).then(pl.lit("b"))
            .when(pl.col("maxValue") > mill_bounds["m"]).then(pl.lit("m"))
            .when(pl.col("maxValue") > mill_bounds["k"]).then(pl.lit("k"))
            .otherwise(pl.lit(""))
            .alias("prefix")
        )
    )

    keep_zero_col = np["keepDecimalsAtZero"]
    chart_col = np["chosenChart"]
    lazy = lazy.with_columns(
        pl.lit(chartDict.get(keep_zero_col, False)).alias(keep_zero_col),
        pl.lit(chartDict.get(chart_col, "")).alias(chart_col),
    )

    # 2️⃣ collect ONE row (maxValue, prefix)
    df_row = lazy.select("maxValue", "prefix").collect()
    if df_row.height:
        max_val, prefix = df_row.row(0)
    else:
        max_val = 0
        prefix = ""

    # 3️⃣ derive decimals without Polars expr helpers (compat with older versions)
    decimals_out = decimals
    if chartDict.get(keep_zero_col, False):
        decimals_out = decimals
    elif chartDict.get(chart_col, "") in _accepted_charts(np):
        divisor = mill_bounds.get(prefix, 1) or 1
        scaled = abs(float(max_val or 0)) / divisor
        digits = len(str(int(scaled))) if scaled >= 1 else 1
        decimals_out = max(0, 3 - digits)

    # 4️⃣ update chartDict exactly like the old function
    chartDict[valuePrefixName] = prefix
    if metric:
        chartDict[valuePrefixMetric] = metric
        chartDict.setdefault(valuePrefixDict, {})[metric] = prefix

    return prefix, chartDict, decimals_out

def calculate_millify_values(
    df: Union[pl.DataFrame, pl.LazyFrame],
    metric: str,
    decimals: int,
    percent_suffix: str,
    multiplier: float,
    out_column: str,
    chart_dict: Mapping,
    prefix: str,
):
    """
    Polars equivalent of `calculate_millify_values`.

    Parameters
    ----------
    df              : pl.DataFrame | pl.LazyFrame   (returned with the same type)
    metric          : metric under analysis
    decimals        : #decimals for round()
    percent_suffix  : '%' or ''  (kept for back‑compat with your code)
    multiplier      : numeric multiplier applied after division
    out_column      : usually `workColumnThree`
    chart_dict      : dict with chart settings
    prefix          : prefix forced by caller ('' | 'k' | 'm' | …)

    Notes
    -----


    * Former inplace assignments on DataFrames were replaced with
      ``with_columns`` so the API works with LazyFrames too.
    """

    naming = get_naming_params()

    # unpack only the names we touch in this routine
    work_col3  = naming["workColumnThree"]
    work_col5  = naming["workColumnFive"]
    stacked_col_metric  = naming["stackedColumnMetric"]
    plot_values_as      = naming["plotValuesAsChoice"]
    show_values_as      = naming["showValuesAs"]
    absolute            = naming["absolute"]
    percent_of_col_tot  = naming["percentOfColumnTotal"]
    percent_of_row_tot  = naming["percentOfRowTotal"]
    percent_of_tot      = naming["percentOfTotal"]
    chosen_chart_key    = naming["chosenChart"]
    pareto_chart        = naming["paretoChart"]
    stacked_pareto      = naming["stackedParetoChart"]
    stacked_col_chart   = naming["stackedColumnChart"]
    stacked_bar_chart   = naming["stackedBarChart"]
    horiz_waterfall     = naming["horizontalWaterfallChart"]
    marimekko_chart     = naming["marimekkoChart"]
    show_abs_values     = naming["showAbsoluteValues"]

    # mapping exponent ➜ suffix
    mill_dict = {12: "t", 9: "b", 6: "m", 3: "k", 0: ""}

    chosen_chart = chart_dict.get(chosen_chart_key, "")

    # ------------------------------------------------------------------
    # Iterate over possible magnitude buckets until the caller‑requested
    # prefix (or '') is found; then apply the matching rules.
    # ------------------------------------------------------------------
    for exp, suf in mill_dict.items():
        if suf not in [prefix, False, ""]:
            continue

        divider  = 10 ** exp
        min_val  = 10 ** exp
        suffix   = suf

        divider, min_val, suffix = get_divider_and_suffix(
            exp, divider, suffix, min_val,
            metric, out_column, chart_dict
        )

        # α)  ----- % cases -------------------------------------------------
        if percent_suffix == "%":
            if (
                chosen_chart in [stacked_col_chart, stacked_bar_chart]
                and chart_dict.get(plot_values_as) != absolute
            ) or (
                chosen_chart == marimekko_chart
                and chart_dict.get(show_values_as) != absolute
            ):
                # Show integers + '%' (stacked situations)
                df = _assign_polars(
                    df, work_col5,
                    pl.format(
                        "{}%",
                        pl.col(work_col3).round(0).cast(pl.Int64)
                    )
                )

            elif decimals == 0:
                # Integer, no suffix
                df = _assign_polars(
                    df, work_col5,
                    pl.col(work_col3).round(0).cast(pl.Int64).cast(pl.Utf8)
                )
            else:
                # float → string
                df = _assign_polars(
                    df, work_col5,
                    pl.col(work_col3).round(decimals).cast(pl.Utf8)
                )

        # β)  ----- raw number (no %, exp==0) -------------------------------
        elif exp == 0:
            df = _assign_polars(df, work_col5, pl.col(work_col3).round(1))

        # γ)  ----- generic branch – delegate to helper ---------------------
        else:
            df = apply_suffix_for_multiply(
                df, exp, metric, decimals, percent_suffix, multiplier,
                divider, min_val, suffix, chart_dict
            )
        if divider != 1:
            break      
    return df

 

def get_divider_and_suffix(
    element: int,
    divider: int,
    suffix: str,
    min_value: int,
    metric: str,
    out_column: str,
    chart_dict: Mapping,
) -> Tuple[int, int, str]:
    naming = get_naming_params()
    mparam = get_metric_array_params()

    percent_metrics   = mparam[naming["percentMetricsArray"]]
    plot_values_as    = naming["plotValuesAsChoice"]
    absolute          = naming["absolute"]
    show_values_as    = naming["showValuesAs"]
    pct_col_tot       = naming["percentOfColumnTotal"]
    pct_row_tot       = naming["percentOfRowTotal"]
    pct_tot           = naming["percentOfTotal"]
    chosen_chart_key  = naming["chosenChart"]
    pareto_chart      = naming["paretoChart"]
    stacked_pareto    = naming["stackedParetoChart"]
    work_column       = naming["workColumn"]

    # ――― Percent metrics or stacked‑column percent metric
    if (
        metric in percent_metrics
        or (
            naming["stackedColumnMetric"] in chart_dict
            and chart_dict[naming["stackedColumnMetric"]] in percent_metrics
            and metric == chart_dict[naming["stackedColumnMetric"]]
        )
    ):
        divider = min_value = 1
        suffix = ""

    # ――― user selected "% of …" display
    elif show_values_as in chart_dict and chart_dict[show_values_as] != absolute:
        divider = min_value = 1
        suffix = ""

    elif chart_dict.get(show_values_as) in [pct_tot, pct_row_tot, pct_col_tot]:
        divider = min_value = 1
        suffix = ""

    # ――― (Stacked) Pareto or classic Pareto tweaks
    elif chart_dict.get(chosen_chart_key) in [stacked_pareto]:
        if out_column == work_column:
            pass        # decimals handled upstream
        else:
            divider = 1
            min_value = 0
            suffix = ""
    elif chart_dict.get(chosen_chart_key) in [pareto_chart]:
        if not chart_dict.get(naming["showAbsoluteValues"], False):
            divider = 1
            min_value = 0
            suffix = ""

    # ――― “plain numbers” bucket
    elif element == 0:
        divider = 1
        min_value = 0
        suffix = ""

    return divider, min_value, suffix


def apply_suffix_for_multiply(
    df: Union[pl.DataFrame, pl.LazyFrame],
    element: int,
    metric: str,
    decimals: int,
    percent_suffix: str,
    multiplier: float,
    divider: float,
    min_value: float,
    suffix: str,
    chart_dict: Mapping,
):
    """Helper implemented with Polars expressions.
    Only the string‑building logic changed; the decision
    tree is the same.
    """
    naming = get_naming_params()
    mparam = get_metric_array_params()

    percent_metrics   = mparam[naming["percentMetricsArray"]]
    variance_amount   = naming["varianceAmountName"]
    work_col3         = naming["workColumnThree"]
    work_col5         = naming["workColumnFive"]
    stacked_col_metric = naming["stackedColumnMetric"]
    
    w3 = pl.col(work_col3)
    w5 = pl.col(work_col5)

    # ------------------------------------------------------------------
    # Helper macros  (avoid repeating long expressions)
    # ------------------------------------------------------------------
    def _fmt_number(expr: pl.Expr) -> pl.Expr:
        """Round, apply multiplier/divider and cast to Utf8."""
        rounded = (expr / divider * multiplier).round(decimals)
        if decimals == 0:
            rounded = rounded.cast(pl.Int64)
        return rounded.cast(pl.Utf8)

    def _assign_val(pos_condition: pl.Expr, value_expr: pl.Expr):
        """
        Assign <value_expr> ONLY where <work_col5> is null
        and <pos_condition> is true.  Otherwise keep old value.
        """
        nonlocal df
        df = _assign_polars(df, work_col5,
            pl.when(pos_condition & w5.is_null())
              .then(value_expr)
              .otherwise(w5)
        )

    # ------------------------------------------------------------------
    # Branch 1 – percent metrics / stacked‑percent metric
    # ------------------------------------------------------------------
    

    if (
        metric in percent_metrics
        or (
            stacked_col_metric in chart_dict
            and chart_dict[stacked_col_metric] in percent_metrics
            and metric == chart_dict[stacked_col_metric]
        )
    ):
        _assign_val(
            w3 >  min_value,
            pl.lit("+") + _fmt_number(w3) + pl.lit(suffix + percent_suffix)
        )
        _assign_val(
            w3 < -min_value,
            _fmt_number(w3) + pl.lit(suffix + percent_suffix)
        )

    # ------------------------------------------------------------------
    # Branch 2 – variance amount metric
    # ------------------------------------------------------------------
    elif metric == variance_amount:
        _assign_val(
            w3 >  min_value,
            pl.lit("+") + _fmt_number(w3) + pl.lit(suffix + percent_suffix)
        )
        _assign_val(
            w3 < -min_value,
            _fmt_number(w3) + pl.lit(suffix + percent_suffix)
        )

    # ------------------------------------------------------------------
    # Branch 3 – number output (no '%' suffix)
    # ------------------------------------------------------------------
    elif percent_suffix != "%":
        if decimals == 0:
            df = _assign_polars(
                df, work_col5,
                pl.when(w5.is_null())
                  .then(_fmt_number(w3).cast(pl.Int64).cast(pl.Utf8) + pl.lit(percent_suffix))
                  .otherwise(w5)
            )
        else:

            df = _assign_polars(
                df, work_col5,
                pl.when(w5.is_null())
                  .then(_fmt_number(w3).cast(pl.Float64))
                  .otherwise(w5)
            )
    # ------------------------------------------------------------------
    # Branch 4 – generic
    # ------------------------------------------------------------------
    else:
        _assign_val(
            w3 >  min_value,
            _fmt_number(w3).cast(pl.Int64).cast(pl.Utf8) + pl.lit(suffix + percent_suffix)
        )
        _assign_val(
            w3 < -min_value,
            _fmt_number(w3).cast(pl.Int64).cast(pl.Utf8) + pl.lit(suffix + percent_suffix)
        )
    return df


# ---------------------------------------------------------------------------
# Utility: overwrite or create a column via Polars expression
# ---------------------------------------------------------------------------
def _assign_polars(
    df: Union[pl.DataFrame, pl.LazyFrame],
    column_name: str,
    expr: pl.Expr
) -> Union[pl.DataFrame, pl.LazyFrame]:
    """
    Helper that works for both eager and lazy frames.
    `expr` is a Polars expression that yields the new column.
    """
    if isinstance(df, pl.LazyFrame):
        return df.with_columns(expr.alias(column_name))
    else:
        # eager .with_columns returns a *new* frame – keep functional style
        return df.with_columns(expr.alias(column_name)) 


def get_correct_multiplier(
    df: pl.LazyFrame,
    chartDict: dict,
    decimals: int,
    metric: str,
) -> tuple[str, dict, int]:
    """
    Same public contract as the old function but 100 % Polars‑lazy.

    Parameters
    ----------
    df        : Polars LazyFrame holding the data to be charted
    chartDict : mutable dictionary carrying chart state
    decimals  : initial decimals (may be overridden)
    metric    : metric/column to prioritise when possible

    Returns
    -------
    prefix, updated_chartDict, updated_decimals
    """
    # ───────────────── naming helpers ───────────────── #
    n = get_naming_params()
    chosenChart              = chartDict.get(n["chosenChart"], False)
    valuePrefixName          = n["valuePrefixName"]
    IBCSdecimalName          = n["IBCSdecimalName"]

    # ─── Which numeric column (or expression) drives the multiplier? ─── #
    amount_col = None

    if (
        chosenChart
        in [
            n["stackedColumnChart"],
            n["marimekkoChart"],
            n["stackedBarChart"],
            n["barmekkoChart"],
            n["horizontalWaterfallChart"],
            n["multitierColumnChart"],
            n["trendComparisonByPeriodChart"],
        ]
        or chartDict.get(n["varianceAnalysisChart"], False)
    ):
        # priority list, mimicking the old chain of if‑elif
        columns,schema=get_schema_and_column_names(df) 
        for candidate in [
            metric,
            n["valueName"],
            n["totalName"],
            n["varianceAmountName"],
            n["acName"],
            n["pyName"],
        ]:
            if candidate in columns:
                amount_col = candidate
                break
    elif chosenChart == n["multitierBarChart"]:
        # need a row‑wise max across selected periods
        selected = chartDict[n["selectedPeriods"]]
        df = df.with_columns(
            pl.max_horizontal(*[pl.col(c) for c in selected]).alias("__row_max")
        )
        amount_col = "__row_max"

    if amount_col is None:
        raise ValueError("No numeric column found to determine value prefix")

    # ─── Decide whether to reuse an existing prefix ─── #
    keep_prefix = (
        chartDict.get(n["plotSmallMultiplesOtherCharts"], False)
        or chosenChart in [n["stackedColumnChart"], n["dotChart"]]
    )
    if n["metricsToPlot"] in chartDict and len(chartDict[n["metricsToPlot"]]) > 1:
        keep_prefix = False

    if keep_prefix and valuePrefixName in chartDict:
        prefix = chartDict[valuePrefixName]
        if IBCSdecimalName in chartDict and chartDict[IBCSdecimalName] >= 0:
            decimals = chartDict[IBCSdecimalName]
        return prefix, chartDict, decimals
    # ─── Fresh calculation via fully‑lazy helper ─── #
  
    prefix, chartDict, decimals = get_number_prefix(
        df, amount_col, chartDict, decimals, metric
    )
    return prefix, chartDict, decimals



def millify_dataframe(
    df: pl.LazyFrame,
    metric: str,
    secondMetric: str,
    outColumn: str,
    chartDictCopy: dict
):
    namingParams   = get_naming_params()
    workColumnThree= namingParams["workColumnThree"]
    workColumnFive = namingParams["workColumnFive"]

    # Make a copy of chartDict
    chartDict = copy.deepcopy(chartDictCopy)

    # 1) rename columns
    df = rename_columns_for_millify(df)        

    # 2) set decimals, percentSuffix, multiplier
    metric, decimals, percentSuffix, multiplier = set_decimals_and_percent_suffix(
        df, metric, outColumn, chartDict
    )
               
    # 3) get prefix (requires partial collect to find max)
    prefix, chartDict, decimals = get_correct_multiplier(
        df, chartDict, decimals, metric
    )

    # 4) add any work columns
    df = add_workcolumns_to_millify(df, metric, outColumn, secondMetric, chartDict)
   
    # 5) calculate final millify values
    df = calculate_millify_values(
        df,
        metric,
        decimals,
        percentSuffix,
        multiplier,
        outColumn,
        chartDict,
        prefix
    )



    # 6) fill final result column from workColumnFive
    df = df.with_columns(pl.col(workColumnFive).fill_null("").alias(workColumnFive))
    df = df.with_columns(pl.col(workColumnFive).alias(outColumn))

    # 7) drop columns
    df = drop_columns(df, [workColumnThree, workColumnFive])
    # Return the lazy frame + updated chartDict
    return df, chartDict
  







def get_parents_stacked_pareto(chartDict,getChildren,paramDict):
    namingParams=get_naming_params() 
    xAxisDimension=namingParams["xAxisDimension"]
    hierarchical=namingParams["hierarchicalName"]
    countColumn=namingParams["countColumn"]
    choiceArray=[]
    parentArray=[]
    childArray=[]    
    if getChildren: 
        if hierarchical in paramDict:
            for hierarchy in paramDict[hierarchical]: 
                hierarchyArray=list(paramDict[hierarchical][hierarchy])
                del hierarchyArray[0]  
                childArray=childArray+hierarchyArray
            childArray=list(set(childArray))
            choiceArray=childArray
    else:        
        if hierarchical in paramDict:   
            for hierarchy in paramDict[hierarchical]: 
                if chartDict[countColumn] in paramDict[hierarchical][hierarchy]: 
                    childIndex=list(paramDict[hierarchical][hierarchy]).index(chartDict[countColumn])
                    if childIndex>0 and len(paramDict[hierarchical][hierarchy]) >1:
                       parentArray=parentArray+list(paramDict[hierarchical][hierarchy])[:childIndex] 
            parentArray=list(set(parentArray))  
        choiceArray=choiceArray+parentArray 
    return choiceArray    

def get_parents_upsetChart_and_vennChart(chartDict,chosenChart,paramDict):
    namingParams=get_naming_params() 
    xAxisDimension=namingParams["xAxisDimension"]
    hierarchical=namingParams["hierarchicalName"]
    choiceArray=[]
    dropArray=[]  
    workArray=[] 
    notParentArray=[] 
    if hierarchical in paramDict: 
        for hierarchy in paramDict[hierarchical]:
            if chartDict[xAxisDimension] in paramDict[hierarchical][hierarchy]:
                setHierarchy=list(paramDict[hierarchical][hierarchy])
                fatherIndex=setHierarchy.index(chartDict[xAxisDimension])
                dropArray=setHierarchy[fatherIndex+1:]
        for hierarchy in paramDict[hierarchical]:
            if chartDict[xAxisDimension] not in paramDict[hierarchical][hierarchy]:
                newList=list(paramDict[hierarchical][hierarchy])
                notParentArray=notParentArray+newList
        workArray=list(set(notParentArray)) 
        for element in workArray:
            if element not in dropArray:
                choiceArray.append(element)            
    return choiceArray

def get_parents_stacked_bar_and_marimekko(chartDict,chosenChart,paramDict):
    namingParams=get_naming_params() 
    xAxisDimension=namingParams["xAxisDimension"]
    yAxisDimension=namingParams["yAxisDimension"]
    hierarchical=namingParams["hierarchicalName"]
    choiceArray=[]
    parentArray=[]    
    choiceArray=False
    if hierarchical in paramDict:
        for hierarchy in paramDict[hierarchical]:
            if chartDict[xAxisDimension] in paramDict[hierarchical][hierarchy] and chartDict[yAxisDimension] in paramDict[hierarchical][hierarchy]:
                choiceArray=True
    return choiceArray


def get_parents_bubble_and_scatter(chartDict,chosenChart,paramDict):
    namingParams=get_naming_params() 
    bubbleChart=namingParams["bubbleChart"]
    numberOfTop=namingParams["numberOfTop"]
    xAxisDimension=namingParams["xAxisDimension"]
    hierarchical=namingParams["hierarchicalName"]
    choiceArray=[]
    parentArray=[]    
    if chosenChart in [bubbleChart] and chartDict["X"][numberOfTop]<11:
        choiceArray.append(chartDict[xAxisDimension])
    if hierarchical in paramDict:   
        for hierarchy in paramDict[hierarchical]:
            if chartDict[xAxisDimension] in paramDict[hierarchical][hierarchy]: 
                childIndex=list(paramDict[hierarchical][hierarchy]).index(chartDict[xAxisDimension])
                if childIndex>0 and len(paramDict[hierarchical][hierarchy]) >1:
                    parentArray=parentArray+list(paramDict[hierarchical][hierarchy])[:childIndex] 
        parentArray=list(set(parentArray))
    choiceArray=choiceArray+parentArray
    return choiceArray

def check_if_parents_in_indexCols(choiceArray,indexCols):
    checkedArray=[]
    if len(indexCols)>0:
        for element in choiceArray:
            if element in indexCols:
                checkedArray.append(element)
    return checkedArray

def get_parents_of_dimension(chartDict,chosenChart,indexCols,paramDict,getChildren):
    namingParams=get_naming_params() 
    bubbleChart=namingParams["bubbleChart"]
    motionChart=namingParams["motionChart"]
    scatterChart=namingParams["scatterChart"]
    upsetChart=namingParams["upsetChart"]
    vennChart=namingParams["vennChart"]
    stackedColumnChart=namingParams["stackedColumnChart"]
    stackedBarChart=namingParams["stackedBarChart"]    
    stackedParetoChart=namingParams["stackedParetoChart"]  
    marimekkoChart=namingParams["marimekkoChart"] 
    choiceArray=[]
    if chosenChart in [bubbleChart,motionChart,scatterChart]:
        choiceArray=get_parents_bubble_and_scatter(chartDict,chosenChart,paramDict)
    elif chosenChart in [stackedParetoChart]: 
        choiceArray=get_parents_stacked_pareto(chartDict,getChildren,paramDict)
    elif chosenChart in [upsetChart,vennChart]: 
        choiceArray=get_parents_upsetChart_and_vennChart(chartDict,chosenChart,paramDict)
    elif chosenChart in [stackedBarChart,marimekkoChart]:
        choiceArray=get_parents_stacked_bar_and_marimekko(chartDict,chosenChart,paramDict)    
    choiceArray=check_if_parents_in_indexCols(choiceArray,indexCols)
    return choiceArray



def get_colors_for_observations(choiceArray,chartDict,paramDict,chosenChart):
    namingParams=get_naming_params() 
    topWordDictKey=namingParams["topWordDict"]
    xAxisDimension=namingParams["xAxisDimension"]
    nothingFilteredName=namingParams["nothingFilteredName"]
    colorpalette=namingParams["colorpalette"]
    XnumberOfTop=namingParams["XnumberOfTop"]
    scatterChart=namingParams["scatterChart"]
    bubbleChart=namingParams["bubbleChart"]
    if chosenChart in [scatterChart]:
        if xAxisDimension in chartDict and chartDict[xAxisDimension]==nothingFilteredName:
            for element in paramDict[topWordDictKey]:
                if len(paramDict[topWordDictKey][element])<=10:
                    choiceArray.append(element)
            choiceArray=list(set(choiceArray))        
        if len(choiceArray)>0 and nothingFilteredName not in choiceArray:
            choiceArray.insert(len(choiceArray), nothingFilteredName)                
    if chosenChart in [bubbleChart]:
        if xAxisDimension in chartDict and chartDict[xAxisDimension]!=nothingFilteredName and chartDict[xAxisDimension] not in choiceArray:
            choiceArray.append(chartDict[xAxisDimension]) 
        choiceArray=list(set(choiceArray))     
        if len(choiceArray)>0 and nothingFilteredName not in choiceArray:
            choiceArray.insert(len(choiceArray), nothingFilteredName)
        colorDict=get_color_dictionary(chartDict)   
        if XnumberOfTop in chartDict and chartDict[XnumberOfTop]>len(colorDict[chartDict[colorpalette]])-2:
            if xAxisDimension in chartDict and chartDict[xAxisDimension]!=nothingFilteredName:
                if chartDict[xAxisDimension] in choiceArray:
                    choiceArray.remove(chartDict[xAxisDimension])                       
    return choiceArray


def find_possible_data_column_metrics(chartDict):
    namingParams=get_naming_params()
    nothingFilteredName=namingParams["nothingFilteredName"]
    metricsToPlot=namingParams["metricsToPlot"]
    monetaryLocalCurrencyName=namingParams["monetaryLocalCurrencyName"]
    averageAmount=namingParams["averageAmount"]
    unitsName=namingParams["unitsName"]
    volumeName=namingParams["volumeName"]
    averageUnits=namingParams["averageUnits"]
    averageVolume=namingParams["averageVolume"]
    pricePerUnitName=namingParams["pricePerUnitName"]
    pricePerVolumeName=namingParams["pricePerVolumeName"]
    discountName=namingParams["discountName"]   
    discountInPercentName=namingParams["discountInPercentName"]
    netOfDiscountName=namingParams["netOfDiscountName"]
    averageAmountAfterDiscount=namingParams["averageAmountAfterDiscount"]
    marginName=namingParams["marginName"]            
    marginInPercentName=namingParams["marginInPercentName"]
    marginInPercentOfNetSalesName=namingParams["marginInPercentOfNetSalesName"]
    averageMargin=namingParams["averageMargin"]
    pricePerUnitNetDiscountName=namingParams["pricePerUnitNetDiscountName"]
    pricePerVolumeNetDiscountName=namingParams["pricePerVolumeNetDiscountName"]     
    metricsToShowInDataColumnArray=[nothingFilteredName]
    metricsToPlot=chartDict[metricsToPlot] 
    if monetaryLocalCurrencyName in metricsToPlot:
        metricsToShowInDataColumnArray.append(averageAmount)
    if unitsName in metricsToPlot:
        metricsToShowInDataColumnArray.append(averageUnits) 
    if volumeName in metricsToPlot:
        metricsToShowInDataColumnArray.append(averageVolume)     
    if monetaryLocalCurrencyName in metricsToPlot and unitsName in metricsToPlot:
        metricsToShowInDataColumnArray.append(pricePerUnitName)  
    if netOfDiscountName in metricsToPlot and unitsName in metricsToPlot:
        metricsToShowInDataColumnArray.append(pricePerUnitNetDiscountName)
    if monetaryLocalCurrencyName in metricsToPlot and volumeName in metricsToPlot:
        metricsToShowInDataColumnArray.append(pricePerVolumeName)  
    if netOfDiscountName in metricsToPlot and volumeName in metricsToPlot:
        metricsToShowInDataColumnArray.append(pricePerVolumeNetDiscountName)
    if discountName in metricsToPlot and monetaryLocalCurrencyName in metricsToPlot:
        metricsToShowInDataColumnArray.append(discountInPercentName)
    if netOfDiscountName in metricsToPlot:
        metricsToShowInDataColumnArray.append(averageAmountAfterDiscount)
    if marginName in metricsToPlot and monetaryLocalCurrencyName in metricsToPlot:
        metricsToShowInDataColumnArray.append(averageMargin) 
        metricsToShowInDataColumnArray.append(marginInPercentName) 
    if marginName in metricsToPlot and netOfDiscountName in metricsToPlot:
        metricsToShowInDataColumnArray.append(averageMargin) 
        metricsToShowInDataColumnArray.append(marginInPercentOfNetSalesName)
    metricsToShowInDataColumnArray=list(set(metricsToShowInDataColumnArray)) 
    return  metricsToShowInDataColumnArray 

def get_color_choice(chartDict):
    namingParams=get_naming_params()
    colorChoice=namingParams["colorChoice"] 
    redToGreen=namingParams["redToGreen"]     
    greenToRed=namingParams["greenToRed"] 
    if colorChoice in chartDict and chartDict[colorChoice] == redToGreen:
        colorChoice=SetColorRedToGreen
    elif colorChoice in chartDict and chartDict[colorChoice] == greenToRed:
        colorChoice=SetColorGreenToRed  
    else:    
        colorChoice=SetColorBlueToOrange 
    return colorChoice  

def get_max_and_min_value(df, metric, chartDict, paramDict, periodsArray):
    """
    Compute row-wise min/max for selected period columns and a color flag.

    DataFrame operations implemented with Polars:
    - Column renaming via ``rename``
    - Missing period columns added with ``with_columns`` and nulls
    - Row-wise min/max via ``pl.min_horizontal``/``pl.max_horizontal``
    - Conditional color via ``pl.when(...).then(...).otherwise(...)``
    """
    namingParams = get_naming_params()
    minValue = namingParams["minValue"]
    maxValue = namingParams["maxValue"]
    separatorString = namingParams["separatorString"]
    colorName = namingParams["colorName"]
    discountName = namingParams["discountName"]
    indirectCostsName = namingParams["indirectCostsName"]
    cogsName = namingParams["cogsName"]
    periodChoice = namingParams["periodChoice"]
    weekName = namingParams["weekName"]
    quarterName = namingParams["quarterName"]
    multitierColumnChart = namingParams["multitierColumnChart"]
    horizontalWaterfallChart = namingParams["horizontalWaterfallChart"]
    chosenChartKey = namingParams["chosenChart"]
    discountInPercentName = namingParams["discountInPercentName"]

    chosenChart = chartDict[chosenChartKey]
    reverseColorMetricsArray = [
        discountName,
        discountInPercentName,
        indirectCostsName,
        cogsName,
    ]

    # 1) Rename columns stripping the metric prefix and normalising case
    columns, _ = get_schema_and_column_names(df)
    rename_map: dict[str, str] = {}
    for old in columns:
        new = old.replace(metric + separatorString, "")
        if new.upper() in periodsArray:
            if periodChoice in chartDict and chartDict[periodChoice] in [
                weekName,
                quarterName,
            ]:
                new = new.upper()
        rename_map[old] = new

    if isinstance(df, pl.LazyFrame) or isinstance(df, pl.DataFrame):
        df = df.rename(rename_map)

    # 2) Ensure all required period columns exist
    columns, _ = get_schema_and_column_names(df)
    missing = [p for p in periodsArray if p not in columns]
    if missing:
        df = df.with_columns([pl.lit(None).alias(p) for p in missing])

    # 3) Compute row-wise min/max when applicable
    if chosenChart not in [multitierColumnChart, horizontalWaterfallChart]:
        value_exprs = [
            pl.col(p).cast(pl.Float64, strict=False) for p in periodsArray
        ]
        df = df.with_columns(
            pl.min_horizontal(*value_exprs).alias(minValue),
            pl.max_horizontal(*value_exprs).alias(maxValue),
        )

    # 4) Build color flag (1/0) based on direction; null comparisons -> 0
    first, second = periodsArray[0], periodsArray[1]
    gt_expr = (pl.col(first) > pl.col(second)).fill_null(False)
    if metric not in reverseColorMetricsArray:
        color_expr = pl.when(gt_expr).then(pl.lit(1)).otherwise(pl.lit(0))
    else:
        color_expr = pl.when(gt_expr).then(pl.lit(0)).otherwise(pl.lit(1))
    df = df.with_columns(color_expr.cast(pl.Int64).alias(colorName))

    return df, periodsArray


def prepare_arrays_to_add_traces(df,colors,value_cols,subplot,paramDict,chartDict):
    namingParams=get_naming_params()
    figureName=namingParams["figureName"] 
    plotSmallMultiplesKey=namingParams["plotSmallMultiplesOtherCharts"]
    stackedColumnChart=namingParams["stackedColumnChart"]
    periodName=namingParams["periodName"]
    selectedPeriods=namingParams["selectedPeriods"]
    chosenChartKey=namingParams["chosenChart"]
    chosenChart=chartDict[chosenChartKey]
    categories=[]
    if chosenChart in [stackedColumnChart]:
        categories=chartDict[selectedPeriods]
    else:
        categories = get_unique_categories(df)
        check_collect("AAA", "categories", categories)  
    numberOfCols=len(categories)
    if not colors:
        colors = [None] * len(value_cols)
    elif len(colors) < len(value_cols):
        repeats = (len(value_cols) + len(colors) - 1) // len(colors)
        colors = (colors * repeats)[: len(value_cols)]
    if plotSmallMultiplesKey not in chartDict or not chartDict[plotSmallMultiplesKey]:
        figure = subplot.pop('figure', go.Figure())
    elif figureName in paramDict and paramDict[figureName]:
        figure=paramDict[figureName]
    else:
        figure = subplot.pop('figure', go.Figure())
    return categories,numberOfCols,colors,figure

def make_text_position_array(df: pl.DataFrame | pl.LazyFrame, orientation: str) -> list[str]:
    """Return text positions for pinheads in multitier charts."""

    namingParams = get_naming_params()
    differenceInPercent = namingParams["differenceInPercent"]

    df_pl = (
        pl.DataFrame(df)
        if not isinstance(df, (pl.DataFrame, pl.LazyFrame))
        else df
    )
    lf = df_pl.lazy() if isinstance(df_pl, pl.DataFrame) else df_pl

    left = "middle left" if orientation == "h" else "bottom center"
    right = "middle right" if orientation == "h" else "top center"

    expr = (
        pl.when(pl.col(differenceInPercent) < 0)
        .then(pl.lit(left))
        .otherwise(pl.lit(right))
        .alias("textpos")
    )

    return lf.select(expr).collect()["textpos"].to_list()

def get_subplot_number(row, col):
    n_cols=2
    return (row - 1) * n_cols + col

def multiply_other_metric_for_scale(df, overlayMetric, chartDict, row, col):
    namingParams = get_naming_params()
    indexOrderKey = namingParams["indexOrder"]
    scalingFactorKey = namingParams["scalingFactor"]
    offsetKey = namingParams["offset"]
    chartNumber = get_subplot_number(row, col)

    # Track a simple row order (by position) for small multiples; avoid relying on an explicit index
    if chartNumber == 1:
        chartDict.pop(indexOrderKey, None)
        # store a default positional order list to mirror a default RangeIndex
        try:
            from modules.utilities.utils import get_row_count

            nrows = get_row_count(df)
        except Exception as e:
            logging.exception(e)
            # Fallback: attempt eager cast
            nrows = pl.DataFrame(df).height if not isinstance(df, pl.DataFrame) else df.height
        chartDict[indexOrderKey] = list(range(nrows))
    else:
        order = chartDict.get(indexOrderKey)
        if order is not None and isinstance(df, pl.DataFrame):
            # Reorder by positional take when eager
            try:
                df = df.take(order)
            except Exception as e:
                logging.exception(e)
                pass  # keep current order if shapes differ

    scalingFactor = chartDict.get(scalingFactorKey, 1)
    offset = chartDict.get(offsetKey, 0)

    # Polars assignment using expressions
    df = (
        df.with_columns(
            (pl.col(overlayMetric) * pl.lit(scalingFactor) + pl.lit(offset))
            .round(0)
            .alias(overlayMetric)
        )
        .fill_null(None)
    )
    return df


 

def get_color_sequence(df,paramDict,chartDict):
    namingParams=get_naming_params()
    selectedPeriods=namingParams["selectedPeriods"] 
    isYearBeforePy=namingParams["isYearBeforePy"] 
    chosenChart=namingParams["chosenChart"]
    histogramChart=namingParams["histogramChart"]
    ecdfChart=namingParams["ecdfChart"]
    boxplotChart=namingParams["boxplotChart"]
    stripplotChart=namingParams["stripplotChart"]
    kernelDensityChart=namingParams["kernelDensityChart"]
    colorDict=get_color_dictionary(chartDict) 
    periodOrder=chartDict[selectedPeriods]
    isExpectedData,planName=check_if_plan_or_py(periodOrder)
    if isExpectedData:
        colorSequenceArray=[colorDict["whiteColor"],colorDict["blackColor"]]
        if chosenChart in chartDict and chartDict[chosenChart] in [ecdfChart,histogramChart,boxplotChart,stripplotChart,kernelDensityChart]:    
            colorSequenceArray=[colorDict["blackColor"],colorDict["veryLightGreyColor"]]
        lineWidth=1 
    elif isYearBeforePy in paramDict and paramDict[isYearBeforePy]:  
        colorSequenceArray=[colorDict["veryLightGreyColor"],colorDict["blackColor"]]  
        lineWidth=0 
    elif chosenChart in chartDict and chartDict[chosenChart]  in [ecdfChart,histogramChart,boxplotChart,stripplotChart,kernelDensityChart]:
        colorSequenceArray=[colorDict["blackColor"],colorDict["lightGreyColor"]] 
        lineWidth=0       
    else:
        colorSequenceArray=[colorDict["lightGreyColor"],colorDict["blackColor"]]  
        lineWidth=0
    return colorSequenceArray,lineWidth
