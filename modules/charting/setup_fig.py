import numpy as np
import polars as pl
from modules.utilities.ui_notifier import ui
import datetime as dt 
import plotly.graph_objects as go
import plotly.express as px
from plotly.subplots import make_subplots
import copy
import math
import logging


from modules.charting.chart_primitives import change_metric_if_cost_analysis
from modules.utilities.config import (
    get_config_params,
    get_naming_params,
)
from modules.utilities.utils import get_schema_and_column_names

def setup_fig_for_stacked_column_charts(df,repeatArray,chosenDimension,paramDict,chartDict):
    """
    we need to set up the subplots fig based on the number of subplots we want to draw
    """
    namingParams=get_naming_params()
    configParams=get_config_params() 
    goldenRatio=configParams[namingParams["goldenRatio"]] 
    chosenChart=namingParams["chosenChart"]
    plotSmallMultiplesKey=namingParams["plotSmallMultiplesOtherCharts"]   
    deltaName=namingParams["deltaName"]
    figureName=namingParams["figureName"]
    chosenChart=chartDict[chosenChart]
    verticalSpacingDict={1:0,2:0.08,3:0.06,4:0.05,5:0.05,6:0.04,}
    horizontalSpacing=0.01
    subplotTitles=None 
    if plotSmallMultiplesKey in chartDict and chartDict[plotSmallMultiplesKey]:
        numberOfItems=len(repeatArray)
        numberOfCols=2  
        plotSmallMultiples=True  
        sharedYaxes="all"            
        numberOfCols=2
        numberOfRows=int(math.ceil(numberOfItems/numberOfCols))
        if numberOfItems < numberOfCols:
            numberOfRows=1 
        specs=[]
        rowHeights=[]  
        if len(repeatArray)> 1:
            subplotTitles=repeatArray   
        showItems=subplotTitles
    else:
        numberOfCols=1
        numberOfRows=1
        sharedYaxes=None
        verticalSpacing=.05 
    if numberOfRows in verticalSpacingDict:
        verticalSpacing=verticalSpacingDict[numberOfRows]    
    else:
        verticalSpacing=verticalSpacingDict[len(verticalSpacingDict)] 
    fig = make_subplots(
                        rows=numberOfRows, 
                          cols=numberOfCols,
                          shared_xaxes="all",
                          shared_yaxes=sharedYaxes,
                          vertical_spacing=verticalSpacing,
                          horizontal_spacing=horizontalSpacing,
                          subplot_titles=subplotTitles,
                              )
    paramDict[figureName]=fig
    return paramDict,numberOfCols,numberOfRows

def setup_fig_for_multitier_bar_charts(repeatArray,chosenDimension,paramDict,chartDict):
    """
    we need to set up the subplots fig based on the number of subplots we want to draw
    """
    namingParams=get_naming_params()
    configParams=get_config_params() 
    goldenRatio=configParams[namingParams["goldenRatio"]] 
    chosenChart=namingParams["chosenChart"]
    plotSmallMultiplesKey=namingParams["plotSmallMultiplesOtherCharts"]   
    xAxisDimension=namingParams["xAxisDimension"]
    deltaName=namingParams["deltaName"]
    totalName=namingParams["totalName"]
    fatherAndChildDimensions=namingParams["fatherAndChildDimensions"] 
    showTopForEachItem=namingParams["showTopForEachItem"]
    numberOfTopKey=namingParams["numberOfTop"]
    chosenChart=chartDict[chosenChart]
    verticalSpacingDict={1:0,2:0.18,3:0.10,4:0.08,5:0.06,6:0.06,}
    subplotTitles=None 
    if plotSmallMultiplesKey in chartDict and chartDict[plotSmallMultiplesKey]:
        numberOfItems=len(repeatArray) 
        numberOfCols=2
        numberOfRows=int(math.ceil(numberOfItems/numberOfCols))         
        plotSmallMultiples=True   
        sharedYaxes=None
        if xAxisDimension in chartDict:
            if (fatherAndChildDimensions in chartDict and chartDict[fatherAndChildDimensions]) or chartDict[showTopForEachItem]:
                sharedYaxes=None
            else:
                sharedYaxes="rows"     
        sharedXaxes='all'
        if numberOfItems < numberOfCols:
            numberOfRows=1 
        titleSpace=150    
        numberOfTop=chartDict["X"][numberOfTopKey]    
        separationSpace=20
        if chosenDimension==totalName:
            singleRowSpace=20
            height=titleSpace+(singleRowSpace*numberOfRows)+(separationSpace*(numberOfRows-1))   
            width=(height*goldenRatio)*numberOfCols*2.2    
            verticalSpacing=0.0   
            horizontalSpacing=0.15                        
        else:
            singleRowSpace=25
            height=titleSpace+(singleRowSpace*(numberOfTop+1)*numberOfRows)+(separationSpace*numberOfRows-1) 
            width=(titleSpace+(separationSpace*(numberOfRows-1))+(singleRowSpace*(numberOfTop+1)))*goldenRatio*numberOfCols*1.1
            horizontalSpacing=0.35   
            if numberOfRows in verticalSpacingDict:
                verticalSpacing=verticalSpacingDict[numberOfRows]  
            else:  
                verticalSpacing=0.03           
        if len(repeatArray)> 1:
            subplotTitles=repeatArray 
            costSubplotTitles=[] 
            for element in subplotTitles:
                metric=change_metric_if_cost_analysis(element,chartDict)
                costSubplotTitles.append(metric)
            if subplotTitles != costSubplotTitles:
                subplotTitles = costSubplotTitles     
        showItems=subplotTitles
        fig = make_subplots(rows=numberOfRows, 
                           cols=numberOfCols,
                          shared_xaxes=sharedXaxes,
                          shared_yaxes=sharedYaxes,
                          vertical_spacing=verticalSpacing,
                          horizontal_spacing=horizontalSpacing,
                          subplot_titles=subplotTitles,
                              )                         
    else:
        numberOfCols=3
        numberOfRows=1
        sharedYaxes=True  
        #sharedXaxes=True        
        height=None
        width=None
        colWidths=[0.4, 0.4,0.2]  
        showItems=["",deltaName,deltaName+"%"]
        verticalSpacing=.05      
        fig = make_subplots(
            rows=numberOfRows, 
            cols=numberOfCols,
            shared_yaxes=sharedYaxes,
            column_widths =colWidths,
            subplot_titles=showItems,
            #vertical_spacing=verticalSpacing,
            #specs=specs,
            #shared_xaxes=sharedXaxes,        
            )                   
    return fig,height,width,numberOfCols,numberOfRows

def setup_fig_for_horizontal_waterfall_charts(repeatArray,chosenDimension,chartDict,plotWithPins):
    """
    we need to set up the subplots fig based on the number of subplots we want to draw
    """
    namingParams=get_naming_params()
    configParams=get_config_params() 
    goldenRatio=configParams[namingParams["goldenRatio"]] 
    filterDates=namingParams["filterDates"]
    chosenChart=namingParams["chosenChart"]
    plotSmallMultiplesKey=namingParams["plotSmallMultiplesOtherCharts"]   
    deltaName=namingParams["deltaName"]
    chosenChart=chartDict[chosenChart]
    verticalSpacingDict={1:0,2:0.08,3:0.06,4:0.05,5:0.05,6:0.04,}
    horizontalSpacing=0.01
    subplotTitles=None 
    if not plotWithPins and plotSmallMultiplesKey in chartDict and chartDict[plotSmallMultiplesKey]:
        numberOfItems=len(repeatArray)
        numberOfCols=2  
        height=400   
        plotSmallMultiples=True  
        sharedYaxes="all"
        sharedXaxes="all"        
        numberOfCols=2
        numberOfRows=int(math.ceil(numberOfItems/numberOfCols))
        if numberOfItems < numberOfCols:
            numberOfRows=1 
        width=(height*goldenRatio)*numberOfCols
        specs=[]
        rowHeights=[]
        if numberOfRows>1:
            height=height*(1+numberOfRows/3)    
        if len(repeatArray)> 1:
            subplotTitles=repeatArray   
        showItems=subplotTitles
        if numberOfRows in verticalSpacingDict:
            verticalSpacing=verticalSpacingDict[numberOfRows]    
        else:
            verticalSpacing=verticalSpacingDict[len(verticalSpacingDict)] 
        fig = make_subplots(rows=numberOfRows, 
                          cols=numberOfCols,
                          shared_xaxes=sharedXaxes,
                          shared_yaxes=sharedYaxes,
                          vertical_spacing=verticalSpacing,
                          horizontal_spacing=horizontalSpacing,
                          subplot_titles=subplotTitles,
                              )    
    else:
        numberOfCols=1
        numberOfRows=2
        sharedYaxes=None
        sharedXaxes=True        
        height=500 
        width=(height*goldenRatio)*(numberOfCols)
        specs=[
               [{}],
               [{"type": "waterfall"}]
               ]
        rowHeights=[.2,.8]   
        showItems=[deltaName+"%",""] 
        verticalSpacing=.05      
        fig = make_subplots(
            rows=numberOfRows, 
            cols=numberOfCols,
            shared_xaxes=sharedXaxes,
            shared_yaxes=sharedYaxes,
            vertical_spacing=verticalSpacing,
            specs=specs,
            row_heights =rowHeights,
            subplot_titles=None
            )                                    
    return fig,height,width,numberOfCols,numberOfRows

def setup_venn_figure(fig,title,font,fontSize,plot):
    if plot:
        plt.title(
            title,
            fontname=font,
            #fontweight="bold",
            fontsize=fontSize,
            pad=15);
        ui.pyplot(fig)
    return None

def setup_upset_figure(plt,title):
    namingParams=get_naming_params()
    configParams=get_config_params()
    font=configParams[namingParams["fontChoice"]] 
    fontSize=configParams[namingParams["fontSizeText"]]
    plt.grid(visible=None)
    plt.xticks([])
    plt.yticks([])   
    plt.title(
            title,
            fontname=font,
            #fontweight="bold",
            fontsize=fontSize,
            pad=15);                    
    ui.pyplot(clear_figure=False)    
    return plt

def setup_fig_for_timeline_charts(repeatArray,chosenDimension,paramDict,chartDict):
    """
    we need to set up the subplots fig based on the number of subplots we want to draw
    """
    namingParams=get_naming_params()
    configParams=get_config_params() 
    goldenRatio=configParams[namingParams["goldenRatio"]] 
    timelineChart=namingParams["timelineChart"]
    filterDates=namingParams["filterDates"]
    chosenChart=namingParams["chosenChart"]
    plotSmallMultiplesKey=namingParams["plotSmallMultiplesOtherCharts"]   
    chosenChart=chartDict[chosenChart]
    verticalSpacingDict={1:0,2:0.08,3:0.06,4:0.05,5:0.05,6:0.04,}
    horizontalSpacing=0.01
    subplotTitles=None
    if chosenChart in [timelineChart] and filterDates in chartDict and chartDict[filterDates]: 
        horizontalSpacing=0.03  
    if plotSmallMultiplesKey in chartDict and chartDict[plotSmallMultiplesKey]:
        numberOfItems=len(repeatArray)
        numberOfCols=2  
        height=400   
        if numberOfItems < numberOfCols:
            numberOfCols=numberOfItems 
        plotSmallMultiples=True  
        sharedYaxes="all"
        numberOfRows=numberOfItems
        numberOfRows=int(math.ceil(numberOfItems/numberOfCols))
        width=(height*goldenRatio)*numberOfCols
        if numberOfRows>1:
            height=height*(1+numberOfRows/3)    
        if len(repeatArray)> 1:
            subplotTitles=repeatArray
    else:
        numberOfCols=1
        numberOfRows=1
        sharedYaxes=None
        height=500 
        width=(height*goldenRatio)*numberOfCols
    if numberOfRows in verticalSpacingDict:
        verticalSpacing=verticalSpacingDict[numberOfRows]    
    else:
        verticalSpacing=verticalSpacingDict[len(verticalSpacingDict)] 
    fig = make_subplots(rows=numberOfRows, 
                          cols=numberOfCols,
                          shared_xaxes="all",
                          shared_yaxes=sharedYaxes,
                          vertical_spacing=verticalSpacing,
                          horizontal_spacing=horizontalSpacing,
                          subplot_titles=subplotTitles,
                              )                           
    return fig,height,width,numberOfCols,numberOfRows 

def setup_fig_for_multitier_column_charts(repeatArray,chosenDimension,paramDict,chartDict,plotWithPins):
    """
    we need to set up the subplots fig based on the number of subplots we want to draw
    """
    namingParams=get_naming_params()
    configParams=get_config_params() 
    goldenRatio=configParams[namingParams["goldenRatio"]] 
    chosenChart=namingParams["chosenChart"]
    plotSmallMultiplesKey=namingParams["plotSmallMultiplesOtherCharts"]   
    chosenChart=chartDict[chosenChart]
    verticalSpacingDict={1:0,2:0.08,3:0.06,4:0.05,5:0.05,6:0.04,}
    horizontalSpacing=0.04
    subplotTitles=None 
    if not plotWithPins and plotSmallMultiplesKey in chartDict and chartDict[plotSmallMultiplesKey]:
        numberOfItems=len(repeatArray)
        numberOfCols=2  
        height=400   
        plotSmallMultiples=True  
        sharedYaxes="all"
        sharedXaxes="all"        
        numberOfCols=2
        numberOfRows=int(math.ceil(numberOfItems/numberOfCols))
        if numberOfItems < numberOfCols:
            numberOfRows=1 
        width=(height*goldenRatio)*numberOfCols
        if numberOfRows>1:
            height=height*(1+numberOfRows/3)    
        if len(repeatArray)> 1:
            subplotTitles=repeatArray   
        showItems=subplotTitles
        if numberOfRows in verticalSpacingDict:
            verticalSpacing=verticalSpacingDict[numberOfRows]    
        else:
            verticalSpacing=verticalSpacingDict[len(verticalSpacingDict)] 
        fig = make_subplots(rows=numberOfRows, 
                          cols=numberOfCols,
                          shared_xaxes=sharedXaxes,
                          shared_yaxes=sharedYaxes,
                          vertical_spacing=verticalSpacing,
                          horizontal_spacing=horizontalSpacing,
                          subplot_titles=subplotTitles,
                              )                         
    else:
        numberOfCols=1
        numberOfRows=3
        sharedYaxes=None
        sharedXaxes=True        
        height=500 
        width=(height*goldenRatio)*numberOfCols
        specs=[
               [{}],
               [{}],
               [{}],
               ]
        rowHeights=[0.2, 0.4,0.4]   
        verticalSpacing=.05      
        fig = make_subplots(
            rows=numberOfRows, 
            cols=numberOfCols,
            shared_xaxes=sharedXaxes,
            shared_yaxes=sharedYaxes,
            vertical_spacing=verticalSpacing,
            specs=specs,
            row_heights =rowHeights,
            )     
    return fig,height,width,numberOfCols,numberOfRows 

def setup_fig_for_slope_charts(repeatArray,chosenDimension,paramDict,chartDict):
    """
    we need to set up the subplots fig based on the number of subplots we want to draw
    """
    namingParams=get_naming_params()
    configParams=get_config_params() 
    goldenRatio=configParams[namingParams["goldenRatio"]] 
    timelineChart=namingParams["timelineChart"]
    filterDates=namingParams["filterDates"]
    chosenChart=namingParams["chosenChart"]
    plotSmallMultiplesKey=namingParams["plotSmallMultiplesOtherCharts"]   
    chosenChart=chartDict[chosenChart]
    verticalSpacingDict={1:0,2:0.02,3:0.06,4:0.05,5:0.05,6:0.04,}
    horizontalSpacing=0.005
    subplotTitles=None
    if chosenChart in [timelineChart] and filterDates in chartDict and chartDict[filterDates]: 
        horizontalSpacing=0.001  
    if plotSmallMultiplesKey in chartDict and chartDict[plotSmallMultiplesKey]:
        numberOfItems=len(repeatArray)
        numberOfCols=numberOfItems 
        width=250    
        if numberOfItems < numberOfCols:
            numberOfCols=numberOfItems 
        plotSmallMultiples=True  
        sharedYaxes="all"
        numberOfRows=1
        height=(width*((goldenRatio*2)-1))
        width=width*numberOfCols
        if numberOfCols ==1:
            width=width*1.5        
        elif numberOfCols <3:
            width=width*1.15
        if len(repeatArray)> 1:
            subplotTitles=repeatArray
    else:
        numberOfCols=1
        numberOfRows=1
        sharedYaxes=None
        width=500 
        height=(width*goldenRatio)
        width=width*numberOfCols 
    if numberOfRows in verticalSpacingDict:
        verticalSpacing=verticalSpacingDict[numberOfRows]    
    else:
        verticalSpacing=verticalSpacingDict[len(verticalSpacingDict)] 
    fig = make_subplots(rows=numberOfRows, 
                          cols=numberOfCols,
                          shared_xaxes="all",
                          shared_yaxes=sharedYaxes,
                          vertical_spacing=verticalSpacing,
                          horizontal_spacing=horizontalSpacing,
                          subplot_titles=subplotTitles,
                              )   
    return fig,height,width,numberOfCols,numberOfRows  

def add_by_to_syn_plot_col_labels(df: pl.LazyFrame) -> pl.LazyFrame:
    """
    Prefix each column name with "by " using Polars rename mapping.

    This operates lazily and avoids any pandas-style operations.
    """
    # Build an old->new column name map like {"A": "by A", ...}
    columns, _ = get_schema_and_column_names(df)
    rename_map = {col: f"by {col}" for col in columns}
    return df.rename(rename_map)

def setup_fig_for_stacked_bar_charts(df,column,repeatArray,chosenDimension,paramDict,chartDict):
    """
    we need to set up the subplots fig based on the number of subplots we want to draw
    """
    namingParams=get_naming_params()
    configParams=get_config_params() 
    goldenRatio=configParams[namingParams["goldenRatio"]] 
    chosenChart=namingParams["chosenChart"]
    deltaName=namingParams["deltaName"]
    figureName=namingParams["figureName"]
    fatherAndChildDimensions=namingParams["fatherAndChildDimensions"] 
    showTopForEachItem=namingParams["showTopForEachItem"] 
    yAxisDimension=namingParams["yAxisDimension"] 
    totalName=namingParams["totalName"] 
    numberOfRowsKey=namingParams["numberOfRows"] 
    numberOfColsKey=namingParams["numberOfCols"]   
    chosenChart=chartDict[chosenChart]
    verticalSpacingDict={1:0,2:0.08,3:0.06,4:0.05,5:0.05,6:0.04,}
    horizontalSpacing=0.01
    subplotTitles=None 
    if column != totalName:
        numberOfItems=len(repeatArray)
        numberOfCols=2  
        plotSmallMultiples=True  
        sharedYaxes="all" 
        if yAxisDimension in chartDict:
            if (fatherAndChildDimensions in chartDict and chartDict[fatherAndChildDimensions]) or chartDict[showTopForEachItem]:
                sharedYaxes=None
            else:
                sharedYaxes="rows"          
        numberOfCols=2
        numberOfRows=int(math.ceil(numberOfItems/numberOfCols))
        if numberOfItems < numberOfCols:
            numberOfRows=1 
        specs=[]
        rowHeights=[]  
        if len(repeatArray)> 1:
            subplotTitles=repeatArray   
        showItems=subplotTitles
        horizontalSpacing=0.1
    else:
        numberOfCols=1
        numberOfRows=1
        sharedYaxes=None
        verticalSpacing=.05 
    if numberOfRows in verticalSpacingDict:
        verticalSpacing=verticalSpacingDict[numberOfRows]    
    else:
        verticalSpacing=verticalSpacingDict[len(verticalSpacingDict)]                
    fig = make_subplots(
                        rows=numberOfRows, 
                          cols=numberOfCols,
                          shared_xaxes="all",
                          shared_yaxes=sharedYaxes,
                          vertical_spacing=verticalSpacing,
                          horizontal_spacing=horizontalSpacing,
                          subplot_titles=subplotTitles,
                              )
    paramDict[figureName]=fig
    paramDict[numberOfRowsKey]=numberOfRows
    paramDict[numberOfColsKey]=numberOfCols        
    return paramDict,numberOfCols,numberOfRows 

def setup_fig_for_actual_vs_previous_year_charts(repeatArray,chosenDimension,paramDict,chartDict,plotWithPins):
    """
    we need to set up the subplots fig based on the number of subplots we want to draw
    """
    namingParams=get_naming_params()
    configParams=get_config_params() 
    goldenRatio=configParams[namingParams["goldenRatio"]] 
    chosenChart=namingParams["chosenChart"]
    plotSmallMultiplesKey=namingParams["plotSmallMultiplesOtherCharts"]   
    chosenChart=chartDict[chosenChart]
    verticalSpacingDict={1:0,2:0.08,3:0.06,4:0.05,5:0.05,6:0.04,}
    horizontalSpacing=0.01
    subplotTitles=None  
    if not plotWithPins and plotSmallMultiplesKey in chartDict and chartDict[plotSmallMultiplesKey]:
        numberOfItems=len(repeatArray)
        numberOfCols=2  
        height=400   
        if numberOfItems < numberOfCols:
            numberOfCols=numberOfItems 
        plotSmallMultiples=True  
        sharedYaxes="all"
        numberOfCols=2
        numberOfRows=numberOfItems
        numberOfRows=int(math.ceil(numberOfItems/numberOfCols))
        width=(height*goldenRatio)*numberOfCols
        if numberOfRows>1:
            height=height*(1+numberOfRows/3)    
        if len(repeatArray)> 1:
            subplotTitles=repeatArray
    else:
        numberOfCols=1
        numberOfRows=1
        sharedYaxes=None
        height=500 
        width=(height*goldenRatio)*numberOfCols
    if numberOfRows in verticalSpacingDict:
        verticalSpacing=verticalSpacingDict[numberOfRows]    
    else:
        verticalSpacing=verticalSpacingDict[len(verticalSpacingDict)] 
    fig = make_subplots(rows=numberOfRows, 
                          cols=numberOfCols,
                          shared_xaxes="all",
                          shared_yaxes=sharedYaxes,
                          vertical_spacing=verticalSpacing,
                          horizontal_spacing=horizontalSpacing,
                          subplot_titles=subplotTitles,
                              )                           
    return fig,height,width,numberOfCols,numberOfRows

def add_integrated_legends_to_trend_plot(fig,df,countRows,countCols,yArray):
    fig.add_annotation(
                                    text=yArray[0],
                                    showarrow = False,
                                    align="center",
                                    yshift=0,
                                    y=df.get_column(yArray[0]).first(),
                                    yref="y", 
                                    x=0,
                                    ax=0,
                                    xshift=-30,
                                    xref="paper", 
                                    hovertext=yArray[0],
                                    row=countRows,col=countCols
                               )
    fig.add_annotation(
                            text=yArray[1],
                            showarrow = False,
                            align="center",
                            yshift=0,
                            y=df.get_column(yArray[1]).first(),
                            yref="y", 
                            x=0,
                            ax=0,
                            xshift=-30,
                            xref="paper", 
                            hovertext=yArray[1],
                            row=countRows,col=countCols
                       )
    return fig

def setup_fig_for_mekko_charts(df,column,repeatArray,chosenDimension,paramDict,chartDict):
    """
    we need to set up the subplots fig based on the number of subplots we want to draw
    """
    namingParams=get_naming_params()
    configParams=get_config_params() 
    goldenRatio=configParams[namingParams["goldenRatio"]] 
    chosenChart=namingParams["chosenChart"]
    deltaName=namingParams["deltaName"]
    figureName=namingParams["figureName"]
    fatherAndChildDimensions=namingParams["fatherAndChildDimensions"] 
    showTopForEachItem=namingParams["showTopForEachItem"] 
    yAxisDimension=namingParams["yAxisDimension"] 
    totalName=namingParams["totalName"] 
    numberOfRowsKey=namingParams["numberOfRows"] 
    numberOfColsKey=namingParams["numberOfCols"]   
    chosenChart=chartDict[chosenChart]
    verticalSpacingDict={1:0,2:0.06,3:0.05,4:0.04,5:0.04,6:0.03,}
    horizontalSpacing=0.01
    subplotTitles=None 
    sharedXaxes=None
    sharedYaxes=None
    if column != totalName:
        numberOfItems=len(repeatArray)
        numberOfCols=2  
        plotSmallMultiples=True  
        numberOfCols=2
        numberOfRows=int(math.ceil(numberOfItems/numberOfCols))
        if numberOfItems < numberOfCols:
            numberOfRows=1 
        specs=[]
        rowHeights=[]  
        if len(repeatArray)> 1:
            subplotTitles=repeatArray   
        showItems=subplotTitles
        horizontalSpacing=0.12
    else:
        numberOfCols=1
        numberOfRows=1
        sharedYaxes=None
        verticalSpacing=.05 
    if numberOfRows in verticalSpacingDict:
        verticalSpacing=verticalSpacingDict[numberOfRows]    
    else:
        verticalSpacing=verticalSpacingDict[len(verticalSpacingDict)]    
    fig = make_subplots(
        rows=numberOfRows, 
        cols=numberOfCols,
        shared_xaxes=sharedXaxes,
        shared_yaxes=sharedYaxes,
        vertical_spacing=verticalSpacing,
        horizontal_spacing=horizontalSpacing,
        subplot_titles=subplotTitles,
    )
    if subplotTitles:
        title_annotations = [ann for ann in fig.layout.annotations if ann.text in subplotTitles]
        for idx, ann in enumerate(title_annotations):
            axis_index = idx + 1
            xaxis_key = "xaxis" if axis_index == 1 else f"xaxis{axis_index}"
            xaxis = getattr(fig.layout, xaxis_key, None)
            domain = getattr(xaxis, "domain", None) if xaxis else None
            if domain and len(domain) == 2:
                axis_ref = xaxis_key.replace("axis", "")
                ann.x = 0.5
                ann.xref = f"{axis_ref} domain"
            ann.xanchor = "center"
            ann.align = "center"
    paramDict[figureName]=fig
    paramDict[numberOfRowsKey]=numberOfRows
    paramDict[numberOfColsKey]=numberOfCols        
    return paramDict,numberOfCols,numberOfRows
