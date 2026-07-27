# fmt: off
# isort: skip_file
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


from modules.charting.adjust_position import (
    get_waterfall_plot_height_and_width,
    move_labels_up,
    set_width_and_height,
)
from modules.charting.chart_primitives import (
    add_message_as_annotation,
    add_title_as_annotation,
    change_array_of_metrics_if_cost_analysis,
    enable_draw_shapes,
    get_user_message,
)
from modules.charting.draw_charts_utils import get_polars_value_at_index
from modules.charting.make_titles import make_stacked_pareto_and_pareto_chart_title
from modules.utilities import utils
from modules.utilities.utils import (
    ensure_lazyframe,
    get_row_count,
    get_schema_and_column_names,
)
from modules.utilities.config import (
    get_config_params,
    get_metric_array_params,
    get_naming_params,
)

try:  # pragma: no cover - optional dependency during testing
    get_uniform_text_min_size = utils.get_uniform_text_min_size
except Exception as e:  # pragma: no cover - fallback if missing
    logging.exception(e)
    ui.error("Something went wrong while importing chart helper.")
    def get_uniform_text_min_size(config_params: dict, naming_params: dict) -> int:
        key = naming_params["uniformTextMinSize"]
        return int(config_params[key])




def update_pareto_layout_and_get_messages(fig,period,chartDict,paramDict,metric,showYTicklabels,bargap,df):
    namingParams=get_naming_params()
    showRank=namingParams["showRank"]
    metricsToPlot=namingParams["metricsToPlot"]
    chosenChart=namingParams["chosenChart"] 
    countColumn=namingParams["countColumn"]
    showOnly=namingParams["showOnly"]
    showAll=namingParams["showAll"]
    showTop=namingParams["showTop"]
    showBottom=namingParams["showBottom"]
    chosenChart=chartDict[chosenChart]
    onlyShow=""
    if chartDict[showOnly]==showTop:
        onlyShow=" top 30 "
    elif chartDict[showOnly]==showBottom:
        onlyShow=" bottom 30 "    
    title,paramDict,chartDict=make_stacked_pareto_and_pareto_chart_title(df,chosenChart,paramDict,onlyShow+chartDict[countColumn],chartDict[metricsToPlot][0],chartDict,period,None)
    fig,maxLength,width,chartDict=update_pareto_layout(fig,chartDict,paramDict,metric,showYTicklabels,bargap,df)
    if chartDict[showRank]:
        fig.update_yaxes( 
                           autorange="reversed",                    
                           ) 
    else:    
        pass   
    fig,message=get_user_message(fig,chosenChart,period,None,paramDict,chartDict,df,width,None)
    fig=add_title_as_annotation(fig,title,chosenChart,paramDict)
    fig=add_message_as_annotation(fig,message,None,chosenChart,chartDict,chartDict)
    fig=enable_draw_shapes(fig)    
    return fig,paramDict

def update_histogram_layout(fig,numberOfItemsInCol): 
    namingParams=get_naming_params()
    configParams=get_config_params()
    font=configParams[namingParams["fontChoice"]] 
    fontSize=configParams[namingParams["fontSizeText"]] 
    font=configParams[namingParams["fontChoice"]]     
    goldenRatio=configParams[namingParams["goldenRatio"]] 
    maxHeight=600
    if numberOfItemsInCol==1: 
        baseHeight=500
    else:
        baseHeight=300
    width=int(baseHeight*goldenRatio)
    if baseHeight*numberOfItemsInCol < maxHeight:
        height=baseHeight*numberOfItemsInCol
    else:
        height=maxHeight
    width=int(height*goldenRatio)                                       
    fig.update_layout(
            template='simple_white', 
            width=width,
            height=height,
            font=dict(
                                size=fontSize,
                                ),            
            margin={
                      "r": 0,
                      "l": 0,
                      "b": 0,
                      "pad":0,
                      "autoexpand":True
                  },
            showlegend=True,  
            legend_title_text='', 
            paper_bgcolor='rgba(0,0,0,0)',
            plot_bgcolor='rgba(0,0,0,0)' ,            
            )
    fig.update_xaxes(
                           zeroline= False, 
                           visible= True,
                           ticks= '',
                           showticklabels= True,
                           zerolinecolor='white',
                           automargin= True,
                           title=dict(font=dict(size=fontSize)),
                           
                           )  
    fig.update_yaxes(
                           zeroline= False, 
                           visible= False,
                           title="",
                           ticks= '',
                           showticklabels= False,
                           linecolor='white',
                           automargin=True,
                        )
    return fig


def update_multitier_bar_layout(fig,df,column,metric,periodOrder,uniqueItems,height,width,chartDict,paramDict):
    namingParams=get_naming_params()
    configParams=get_config_params()
    plotSmallMultiplesKey=namingParams["plotSmallMultiplesOtherCharts"]
    fontSize=configParams[namingParams["fontSizeText"]] 
    font=configParams[namingParams["fontChoice"]] 
    goldenRatio=configParams[namingParams["goldenRatio"]]    
    uniformTextMinSize=get_uniform_text_min_size(configParams, namingParams)  
    totalName=namingParams["totalName"]
    numberOfTop=namingParams["numberOfTop"]
    selectDimensionsToPlot=namingParams["selectDimensionsToPlot"]
    rowName=namingParams["rowName"]
    colName=namingParams["columnName"]
    xAxisDimension=namingParams["xAxisDimension"]
    if plotSmallMultiplesKey in chartDict and chartDict[plotSmallMultiplesKey]:
        if len(uniqueItems) ==1:
            height=210
            width=width/2
        else:           
            numberOfItems=df.height
            numberOfCharts=chartDict[rowName] 
            
    else: 
        if len(uniqueItems) ==1:
            height=210
        else:    
            height=200+(23*(len(uniqueItems)))        
    if isinstance(df, pl.LazyFrame):
        period_one_values = (
            df.select(pl.col(periodOrder[1]).drop_nulls())
            .collect(engine="streaming")
            .to_series()
        )
    else:
        period_one_values = df.select(pl.col(periodOrder[1]).drop_nulls()).to_series()
    ymin_value = period_one_values.min()
    ymax_value = period_one_values.max()
    if ymin_value is None:
        ymin_value = 0
    if ymax_value is None:
        ymax_value = 0
    ymin = ymin_value / 1.3
    ymax = ymax_value / 1.3
    fig.update_layout(
                template='simple_white', 
                width=width,
                height=height,
                margin={

                          "autoexpand":True,
                      }, 
                uniformtext=dict(mode="hide", minsize=uniformTextMinSize),
                #showlegend=False,       
                legend={'traceorder':'normal'},
                legend_title_text='', 
                paper_bgcolor='rgba(0,0,0,0)',
                plot_bgcolor='rgba(0,0,0,0)'  ,          
                )
    if plotSmallMultiplesKey not in chartDict or not chartDict[plotSmallMultiplesKey]:
        fig.update_yaxes(
                                   showticklabels=True, 
                                   zeroline= False, 
                                   visible= True,
                                   ticks= '',
                                   zerolinecolor='grey',
                                   rangemode="tozero",
                                   automargin = True,
                                   col=1
                                       ) 
        fig.update_yaxes(
                                   showticklabels=False, 
                                   zeroline= False, 
                                   visible= False,
                                   ticks= '',
                                   rangemode="tozero",
                                   col=2,
                                   
                                       ) 
        fig.update_yaxes(
                                   showticklabels=False, 
                                   zeroline= False, 
                                   visible= False,
                                   ticks= '',
                                   rangemode="tozero",
                                   col=3
                                       )                                  
        fig.update_xaxes(
                                   rangemode="tozero",
                                   zeroline= True, 
                                   automargin=True,
                                   ticks= '',
                                   showticklabels= False,
                                   zerolinecolor='grey',
                                   linecolor='white',
                                )
        fig.update_xaxes(
                                   col=2,
                                   range=[-ymax, ymax],
                                )
    else:        
        fig.update_yaxes(
                               showticklabels=True, 
                               zeroline= False, 
                               visible= True,
                               linecolor="lightgrey",
                               linewidth=0.1,
                               zerolinewidth=0.1,
                               ticks= '',
                               zerolinecolor='white',
                               rangemode="tozero",
                               automargin = True,
                               col=2,
                                   ) 
        fig.update_yaxes(
                               showticklabels=True, 
                               zeroline= False, 
                               visible= True,
                               linecolor="grey",
                               linewidth=0.1,
                               zerolinewidth=0.1,
                               ticks= '',
                               zerolinecolor='white',
                               rangemode="tozero",
                               automargin = True,
                               col=1,
                                   )         
                                  
        fig.update_xaxes(
                               rangemode="tozero",
                               zeroline= True, 
                               automargin=True,
                               ticks= '',
                               showticklabels= False,
                               zerolinecolor='grey',
                               linecolor='white',
                            )
        fig=move_labels_up(fig,chartDict,uniqueItems)
    return fig

def update_waterfall_layout_variable_dimension(df,fig,chartDict): 
    namingParams=get_naming_params()
    configParams=get_config_params()
    font=configParams[namingParams["fontChoice"]]
    fontSize=configParams[namingParams["fontSizeText"]]  
    uniformTextMinSize=get_uniform_text_min_size(configParams, namingParams)   
    runOneDimensionalAnalysis=namingParams["runOneDimensionalAnalysis"]
    horizontalWaterfallChart=namingParams["horizontalWaterfallChart"]
    measureName=namingParams["measureName"]
    varianceAmountName=namingParams["varianceAmountName"]
    varianceInPercent=namingParams["varianceInPercent"]
    df_lazy = df if isinstance(df, pl.LazyFrame) else df.lazy()
    initialValue = get_polars_value_at_index(df_lazy, varianceAmountName, 0)
    finalValue = get_polars_value_at_index(df_lazy, varianceAmountName, -1)
    padValue=0 
    height,width,maxStringLength=get_waterfall_plot_height_and_width(df,chartDict,None,None)
    if initialValue <=0 or finalValue <=0:
      padValue=50
    constant=8
    fig.update_layout(
            template='simple_white', 
            font=dict(
                        size=fontSize,
                                ),
            width=width,
            height=height,           
            margin={
                      "r": 30,
                       "l": 0,
                      "b": 20,
                      "pad":padValue,
                      "autoexpand":True,
                  },
            uniformtext=dict(mode="hide", minsize=uniformTextMinSize),      
            showlegend=False,   
            paper_bgcolor='rgba(0,0,0,0)',
            plot_bgcolor='rgba(0,0,0,0)' ,
            )
    fig.update_xaxes(
                           automargin=True,
                           zeroline= True, 
                           visible= True,
                           ticks= '',
                           showticklabels= False,
                           zerolinecolor='black',
                           linewidth=0,
                           zerolinewidth=1,
                           linecolor='white',
                           )  
    
    if varianceInPercent in chartDict and chartDict[varianceInPercent] :
        fig.update_yaxes(
                ticks= '',
                showticklabels= True,
                linecolor='black',
                zeroline=True, # Ensures the zero line is visible
                zerolinecolor='black',   # Changes the color of the zero line to black
                zerolinewidth=1          # Optionally, you can adjust the thickness of the zero line
            )

    else:
        fig.update_yaxes(
                            #automargin=True,
                         ticks= '',
                         showticklabels= True,
                         linecolor='white',
                        )
    return fig


def update_waterfall_layout_one_dimension(df,fig,chartDict): 
    namingParams=get_naming_params()
    configParams=get_config_params()
    font=configParams[namingParams["fontChoice"]]   
    fontSize=configParams[namingParams["fontSizeText"]] 
    uniformTextMinSize=get_uniform_text_min_size(configParams, namingParams)  
    runOneDimensionalAnalysis=namingParams["runOneDimensionalAnalysis"]
    horizontalWaterfallChart=namingParams["horizontalWaterfallChart"]
    measureName=namingParams["measureName"]
    varianceAmountName=namingParams["varianceAmountName"]
    df_lazy = df if isinstance(df, pl.LazyFrame) else df.lazy()
    initialValue = get_polars_value_at_index(df_lazy, varianceAmountName, 0)
    finalValue = get_polars_value_at_index(df_lazy, varianceAmountName, -1)
    padValue=0
    height,width,maxStringLength=get_waterfall_plot_height_and_width(df,chartDict,None,None)
    if initialValue <=0 or finalValue <=0:
      padValue=50
    fig.update_layout(
            template='simple_white', 
            font=dict(
                                size=fontSize,
                                ),
            width=width,
            height=height,         
            margin={
                      "r":  30,
                       "l":0,
                      "b": 20,
                      "pad":padValue,
                      "autoexpand":True,
                  },
            uniformtext=dict(mode="hide", minsize=uniformTextMinSize),      
            showlegend=False,   
            paper_bgcolor='rgba(0,0,0,0)',
            plot_bgcolor='rgba(0,0,0,0)' ,
            )
    fig.update_xaxes(
                           automargin=True,
                           zeroline= True, 
                           visible= True,
                           ticks= '',
                           showticklabels= False,
                           zerolinecolor='black',
                           zerolinewidth=1,
                           linecolor='white',
                           )  
    fig.update_yaxes(
                            #automargin=True,
                           ticks= '',
                         showticklabels= True
                        )
    return fig

def update_waterfall_layout_small_multiples(df,fig,chartDict,numberOfRows,numberOfCols): 
    namingParams=get_naming_params()
    configParams=get_config_params()
    font=configParams[namingParams["fontChoice"]] 
    fontSize=configParams[namingParams["fontSizeText"]]  
    font=configParams[namingParams["fontChoice"]]
    runOneDimensionalAnalysis=namingParams["runOneDimensionalAnalysis"]
    horizontalWaterfallChart=namingParams["horizontalWaterfallChart"]
    measureName=namingParams["measureName"]
    varianceAmountName=namingParams["varianceAmountName"]
    df_lazy = df if isinstance(df, pl.LazyFrame) else df.lazy()
    initialValue = get_polars_value_at_index(df_lazy, varianceAmountName, 0)
    finalValue = get_polars_value_at_index(df_lazy, varianceAmountName, -1)
    padValue=0
    height,width,maxStringLength=get_waterfall_plot_height_and_width(df,chartDict,numberOfRows,numberOfCols)
    if initialValue <=0 or finalValue <=0:
      padValue=50
    constant=2  
    layoutDict={
                "smallMultiples":{
                     "width":width,
                     "height":height,
                      "r": 30,
                      "l": maxStringLength*constant,
                      "b": 20,
                      "pad":20,
                      "autoexpand":True },                        
                        }
    fig.update_layout(
            template='simple_white', 
            width=width,
            height=height,
            margin={
                      "r": 30,
                      "l": maxStringLength*constant,
                      "b": 20,
                      "pad":20,
                      "autoexpand":True, 
                  },
            showlegend=False,
            paper_bgcolor='rgba(0,0,0,0)',
            plot_bgcolor='rgba(0,0,0,0)'                                
            )  
    fig.update_xaxes(
                           zeroline= True, 
                           visible= True,
                           ticks= '',
                           showticklabels= False,
                           zerolinecolor='black',
                           zerolinewidth=1,
                           linecolor='white',
                           )  
    fig.update_yaxes(
                           automargin=True,
                           ticks= '',
                        )
    return fig,width

def update_kernel_density_layout(fig,numberOfItemsInCol): 
    namingParams=get_naming_params()
    configParams=get_config_params()
    font=configParams[namingParams["fontChoice"]] 
    fontSize=configParams[namingParams["fontSizeText"]]      
    goldenRatio=configParams[namingParams["goldenRatio"]] 
    maxHeight=600
    if numberOfItemsInCol==1: 
        baseHeight=500
    else:
        baseHeight=300
    width=int(baseHeight*goldenRatio)
    if baseHeight*numberOfItemsInCol < maxHeight:
        height=baseHeight*numberOfItemsInCol
    else:
        height=maxHeight
    width=int(height*goldenRatio)                                     
    fig.update_layout(
            template='simple_white', 
            width=width,
            height=height,
            font=dict(
                                size=fontSize,
                                ),
            margin={
                      "r": 0,
                      "l": 0,
                      "b": 0,
                      "pad":0,
                      "autoexpand":True
                  },
            showlegend=True,  
            legend_title_text='', 
            paper_bgcolor='rgba(0,0,0,0)',
            plot_bgcolor='rgba(0,0,0,0)' ,             
            )
    fig.update_xaxes(
                           zeroline= False, 
                           visible= True,
                           ticks= '',
                           showticklabels= True,
                           zerolinecolor='white',
                           automargin= True,
                           title=dict(font=dict(size=fontSize)),
                           
                           )  
    fig.update_yaxes(
                           zeroline= False, 
                           visible= False,
                           title="",
                           ticks= '',
                           showticklabels= False,
                           linecolor='white',
                           automargin=True,
                        )
    return fig

def update_stripplot_layout(fig,numberOfItemsInCol): 
    namingParams=get_naming_params()
    configParams=get_config_params()
    font=configParams[namingParams["fontChoice"]] 
    fontSize=configParams[namingParams["fontSizeText"]]      
    goldenRatio=configParams[namingParams["goldenRatio"]] 
    maxHeight=600
    if numberOfItemsInCol==1: 
        baseHeight=500
    else:
        baseHeight=300
    width=int(baseHeight*goldenRatio)
    if baseHeight*numberOfItemsInCol < maxHeight:
        height=baseHeight*numberOfItemsInCol
    else:
        height=maxHeight
    width=int(height*goldenRatio)                                       
    fig.update_layout(
            template='simple_white', 
            width=width,
            height=height,
            font=dict(
                                size=fontSize,
                                ),            
            margin={
                      "r": 0,
                      "l": 0,
                      "b": 0,
                      "pad":0,
                      "autoexpand":True
                  },
            showlegend=True,  
            legend_title_text='', 
            paper_bgcolor='rgba(0,0,0,0)',
            plot_bgcolor='rgba(0,0,0,0)' ,             
            )
    fig.update_xaxes(
                           zeroline= False, 
                           visible= True,
                           ticks= '',
                           showticklabels= True,
                           zerolinecolor='white',
                           automargin= True,
                           title=dict(font=dict(size=fontSize)),
                           
                           )  
    fig.update_yaxes(
                           zeroline= False, 
                           visible= False,
                           title="",
                           ticks= '',
                           showticklabels= False,
                           linecolor='white',
                           automargin=True,
                        )
    return fig

def update_boxplot_layout(fig,numberOfItemsInCol): 
    namingParams=get_naming_params()
    configParams=get_config_params()
    font=configParams[namingParams["fontChoice"]] 
    fontSize=configParams[namingParams["fontSizeText"]]      
    goldenRatio=configParams[namingParams["goldenRatio"]] 
    maxHeight=600
    if numberOfItemsInCol==1: 
        baseHeight=500
    else:
        baseHeight=400
    width=int(baseHeight*goldenRatio)
    if baseHeight*numberOfItemsInCol < maxHeight:
        height=baseHeight*numberOfItemsInCol
    else:
        height=maxHeight
    width=int(height*goldenRatio)                                       
    fig.update_layout(
            template='simple_white', 
            width=width,
            height=height,
            font=dict(
                                size=fontSize,
                                ),            
            margin={
                      "autoexpand":True
                  },
            showlegend=True,  
            legend_title_text='', 
            paper_bgcolor='rgba(0,0,0,0)',
            plot_bgcolor='rgba(0,0,0,0)' ,  
            )
    fig.update_xaxes(
                           zeroline= False, 
                           visible= True,
                           ticks= '',
                           showticklabels= True,
                           zerolinecolor='white',
                           automargin= True,
                           title=dict(font=dict(size=fontSize)),
                           
                           )  
    fig.update_yaxes(
                           zeroline= False, 
                           visible= False,
                           title="",
                           ticks= '',
                           showticklabels= False,
                           linecolor='white',
                           automargin=True,
                        )
    return fig,width

def update_ecdf_layout(fig,numberOfItemsInCol): 
    namingParams=get_naming_params()
    configParams=get_config_params()
    font=configParams[namingParams["fontChoice"]] 
    fontSize=configParams[namingParams["fontSizeText"]]      
    goldenRatio=configParams[namingParams["goldenRatio"]] 
    maxHeight=600
    if numberOfItemsInCol==1: 
        baseHeight=500
    else:
        baseHeight=300
    width=int(baseHeight*goldenRatio)
    if baseHeight*numberOfItemsInCol < maxHeight:
        height=baseHeight*numberOfItemsInCol
    else:
        height=maxHeight
    width=int(height*goldenRatio)                                       
    fig.update_layout(
            template='simple_white', 
            width=width,
            height=height,
            margin={
                      "r": 0,
                      "l": 0,
                      "b": 0,
                      "pad":0,
                      "autoexpand":True
                  },
            showlegend=True,  
            legend_title_text='', 
            paper_bgcolor='rgba(0,0,0,0)',
            plot_bgcolor='rgba(0,0,0,0)' ,             
            )
    fig.update_xaxes(
                           zeroline= False, 
                           visible= True,
                           ticks= '',
                           showticklabels= True,
                           zerolinecolor='white',
                           automargin= True,
                           title=dict(font=dict(size=fontSize)),
                           
                           )  
    fig.update_yaxes(
                           zeroline= False, 
                           visible= True,
                           ticks= '',
                           showticklabels= True,
                           linecolor='white',
                           automargin=True,
                           title=dict(text="%",font=dict(size=fontSize)),
                        )
    return fig


def update_area_chart_layout(fig,chosenChart):
    namingParams=get_naming_params()
    configParams=get_config_params()
    goldenRatio=configParams[namingParams["goldenRatio"]] 
    uniformTextMinSize=get_uniform_text_min_size(configParams, namingParams)  
    areaChart=namingParams["areaChart"]
    font=configParams[namingParams["fontChoice"]]
    fontSize=configParams[namingParams["fontSizeText"]]     
    numberOfTicks=5
    showgrid=False
    height=600
    width=height*goldenRatio
    tickvals=None
    tickmode=None
    ticktext=None
    fig.update_layout(
            template='simple_white', 
            width=width,
            height=height,                 
            uniformtext=dict(mode="hide", minsize=uniformTextMinSize),      
            showlegend=False,   
            paper_bgcolor='rgba(0,0,0,0)',
            plot_bgcolor='rgba(0,0,0,0)' ,
            margin={
                    "autoexpand":True,
                    "r": 110,
                }, 
            )
    fig.update_yaxes(
        showgrid=showgrid,
        rangemode="tozero",
        #mirror=mirror,
        linecolor="white",
        tickvals= tickvals,
        tickmode= tickmode,
        ticktext= ticktext,  
        showticklabels=False,
        #nticks=numberOfTicks,
        ticks=""
        )
    fig.update_xaxes(
        showgrid=showgrid,
        #mirror=mirror,
        linecolor="lightgrey",
        tickmode="auto",
        ticks=""
        )
    return fig

def update_dot_chart_layout(fig,chosenChart):
    namingParams=get_naming_params()
    configParams=get_config_params()
    uniformTextMinSize=get_uniform_text_min_size(configParams, namingParams)  
    goldenRatio=configParams[namingParams["goldenRatio"]] 
    annotationDict=configParams[namingParams["annotationDict"]] 
    totalName=namingParams["totalName"]
    fontSize=configParams[namingParams["fontSizeText"]] 
    font=configParams[namingParams["fontChoice"]]    
    numberOfTicks=5
    showgrid=False
    height=600
    height=height+(annotationDict[chosenChart]["topMargin"]-100)
    width=height*goldenRatio
    tickvals=None
    tickmode=None
    ticktext=None
    fig.update_layout(    
            template='plotly_white', 
            width=width,
            height=height,                 
            uniformtext=dict(mode="hide", minsize=uniformTextMinSize),      
            showlegend=False,   
            paper_bgcolor='rgba(0,0,0,0)',
            plot_bgcolor='rgba(0,0,0,0)' ,
            margin={
                    "autoexpand":True,
                },     
            )
    fig.update_yaxes(
        showgrid=showgrid,
        rangemode="tozero",
        #mirror=mirror,
        linecolor="white",
        tickvals= tickvals,
        tickmode= tickmode,
        ticktext= ticktext,  
        showticklabels=True,
        #nticks=numberOfTicks,
        ticks=""
        )
    fig.update_xaxes(
        showgrid=showgrid,
        #mirror=mirror,
        zeroline=True,
        zerolinecolor="lightgrey",
        linecolor="lightgrey",
        tickmode=tickmode,
        showticklabels=False,
        ticks=""
        )
    return fig  

def update_yaxes_bar_width_plot_horizontal(figure,ticktext,tickformat,rangeArray,visible,showticklabels,subplot):
    figure.update_yaxes(
        linecolor='white',
        ticks='',
        ticktext= ticktext, 
        tickformat=tickformat, 
        range=rangeArray, 
        visible=visible, 
        showticklabels=showticklabels, 
        row=subplot.get('row'), 
        col=subplot.get('col')
                        ) 
    return figure          

def update_xaxes_bar_width_plot_horizontal(figure,tickvals,ticktext,tickrange,subplot,chartDict):
    configParams=get_config_params()
    namingParams=get_naming_params()
    font=configParams[namingParams["fontChoice"]]
    fontSize=configParams[namingParams["fontSizeText"]]  
    plotSmallMultiplesKey=namingParams["plotSmallMultiplesOtherCharts"] 
    chosenChartKey=namingParams["chosenChart"]
    stackedBarChart=namingParams["stackedBarChart"]
    showticklabels=True
    if chartDict.get(chosenChartKey) == stackedBarChart:
        tickvals=None
        ticktext=None
        tickrange=None
        showticklabels=False
    if plotSmallMultiplesKey in chartDict and chartDict[plotSmallMultiplesKey]:
        tickrange=None
    figure.update_xaxes(
        tickvals=tickvals,
        ticks='',
        zerolinecolor='lightgrey',
        linecolor='white',
        ticktext= ticktext, #OK
        showticklabels=showticklabels,
        range=tickrange,
         **subplot
    )
    return figure  

def update_layout_bar_width_plot(figure,df,chosenChart,numberOfCols,chartDict,paramDict,barmode,bargap):
    configParams=get_config_params()
    namingParams=get_naming_params()
    font=configParams[namingParams["fontChoice"]]
    fontSize=configParams[namingParams["fontSizeText"]]
    stackedColumnChart=namingParams["stackedColumnChart"] 
    synthesisPlot=namingParams["synthesisPlot"]
    height,width=set_width_and_height(df,chosenChart,numberOfCols,chartDict,paramDict)
    figure.update_layout(   
            template='simple_white', 
            height=height, 
            width=width, 
            barmode=barmode, 
            bargap=bargap,
            showlegend=False,
            )
    figure.update_annotations(font=dict(size=fontSize))
    if chosenChart in [stackedColumnChart] and synthesisPlot in chartDict and chartDict[synthesisPlot]:
        figure.update_layout(
            xaxis=dict(
            #automargin=True,
            #title_standoff=0,  # Reduce this value to move the title closer to the axis
            side='top'  # This moves the title to the top
                ),
        )      
    return figure


def update_yaxes_bar_width_plot_vertical(figure,tickvals,ticktext,tickformat,rangeArray,visible,showticklabels,row,col):
    figure.update_yaxes(
        tickvals=tickvals,
        ticks='',
        ticktext= ticktext, 
        tickformat=tickformat, 
        range=rangeArray, 
        visible=visible, 
        showticklabels=showticklabels, 
        linecolor='white',
        row=row, 
        col=col,
                        ) 
    return figure

def update_xaxes_bar_width_plot_vertical(
    figure, tickvals, ticktext, tickrange, row, col, showticklabels: bool | None = None
):
    configParams=get_config_params()
    namingParams=get_naming_params()
    font=configParams[namingParams["fontChoice"]] 
    fontSize=configParams[namingParams["fontSizeText"]] 
    update_kwargs = dict(
        tickvals=tickvals,
        ticks="",
        zerolinecolor="lightgrey",
        linecolor="white",
        ticktext=ticktext,
        range=tickrange,
        row=row,
        col=col,
    )
    if showticklabels is not None:
        update_kwargs["showticklabels"] = showticklabels
    figure.update_xaxes(**update_kwargs)
    return figure

def update_pareto_layout(fig,chartDict,paramDict,metric,showYTicklabels,bargap,df): 
    namingParams=get_naming_params()
    configParams=get_config_params()
    uniformTextMinSize=get_uniform_text_min_size(configParams, namingParams)
    font=configParams[namingParams["fontChoice"]] 
    fontSize=configParams[namingParams["fontSizeText"]]     
    metricsToPlotKey=namingParams["metricsToPlot"]
    showAbsoluteValues=namingParams["showAbsoluteValues"]
    showRank=namingParams["showRank"]
    metricsToPlot=chartDict[metricsToPlotKey]
    metricsToPlot=change_array_of_metrics_if_cost_analysis(metricsToPlot,chartDict)
    numberOfMetrics=len(metricsToPlot)
    numberOfItems = get_row_count(df)
    # Prefer helper for schema/columns to avoid direct property access
    cols, _ = get_schema_and_column_names(df)
    # In Polars, there is no implicit index; measure label length from the dimension column.
    dim_col = namingParams["dimensionName"]
    lf = ensure_lazyframe(df)
    if dim_col in cols:
        maxLength = int(
            lf.select(pl.col(dim_col).cast(pl.Utf8).str.len_chars().max())
            .collect()
            .item()
            or 0
        )
    else:
        # Use the first column if the dimension column is absent
        first_col = cols[0] if cols else None
        maxLength = (
            int(
                lf.select(pl.col(first_col).cast(pl.Utf8).str.len_chars().max())
                .collect()
                .item()
                or 0
            )
            if first_col
            else 0
        )
    singlePlotWidth=700
    if not chartDict[showRank]:
        if maxLength<=20:
            singlePlotWidth=350
            if numberOfMetrics==1:
                singlePlotWidth=singlePlotWidth+300   
        elif maxLength<=30:
            singlePlotWidth=400
            if numberOfMetrics==1:
                singlePlotWidth=singlePlotWidth+250         
        elif maxLength<=40:   
            singlePlotWidth=450  
            if numberOfMetrics==1:
                singlePlotWidth=singlePlotWidth+100               
        elif maxLength<=50:   
            singlePlotWidth=500
        elif maxLength<=80:   
            singlePlotWidth=600    
        else:  
            singlePlotWidth=700                
    if numberOfItems<=10:
        height=450
    elif numberOfItems<=20:  
        height=900  
    elif numberOfItems<=30:  
        height=900     
    else:  
        height=900 
    if chartDict[showRank]:
        singlePlotWidth=singlePlotWidth-350     
    elif chartDict[showAbsoluteValues]:
        singlePlotWidth=singlePlotWidth-100                       
    elif showYTicklabels:
        singlePlotWidth=singlePlotWidth+100
    # Use a Polars expression to check for any negative values
    elif lf.select((pl.col(metric) < 0).any()).collect().item():
        singlePlotWidth=singlePlotWidth+200  
    width=singlePlotWidth*numberOfMetrics    
    fig.update_layout(
            template='simple_white', 
            width=width,
            height=height,
            margin={
                      "r": 20,
                      "l": 0,
                      "t": 130, #40  60
                      "b": 0,
                      "pad":0,
                          "autoexpand":True,
                      },
            uniformtext=dict(mode="hide", minsize=uniformTextMinSize),                               
            legend={'traceorder':'normal'},
            paper_bgcolor='rgba(0,0,0,0)',
            plot_bgcolor='rgba(0,0,0,0)' ,
            showlegend=False, 
            hovermode='x', 
            #barmode="relative", 
            bargap=bargap,

            xaxis2={
                    'rangemode': "tozero",
                    "showticklabels":showYTicklabels,
                    'overlaying': 'y',
                    'position': 1, 
                    

                              }                          
            )
    fig.update_yaxes(
                           title=dict(font=dict(size=fontSize)),
                           zeroline= False, 
                           visible= True,
                           ticks= '',
                           showticklabels= True,
                           zerolinecolor='Grey', 
                           col=1                    
                           ) 
    fig.update_xaxes(
                           title=dict(font=dict(size=fontSize)),
                   
                           )
    count=1
    for metric in metricsToPlot:
        if not chartDict[showAbsoluteValues]:
            xTitle=metric+ " % of total"
            tickvals= np.arange(0, 1.1, .2)
            tickmode= 'array'
            ticktext= [str(i) + '%' for i in range(0, 101, 20)]
        else:
            xTitle=metric
            tickvals= None
            tickmode= None
            ticktext= None
        if count > 1:
                fig.update_yaxes(
                           zeroline= False, 
                           visible= False,
                           ticks= '',
                           showticklabels= False,
                           zerolinecolor='Grey', 
                           title=dict(font=dict(size=fontSize)),
                           col=count                    
                           ) 

        fig.update_xaxes(
                               #title= xTitle,
                               overlaying= 'y',
                               rangemode="tozero",
                               side= "bottom",
                               zeroline= True, 
                               automargin=True,
                               showticklabels= showYTicklabels,
                               ticks= '',
                               linecolor='Lightgrey',
                               tickvals= tickvals,
                               tickmode= tickmode,
                               ticktext= ticktext, 
                               title=dict(text=xTitle,font=dict(size=fontSize)),                              
                               col=count
                            )
        
        count=count+1
    return fig,maxLength,width,chartDict

def update_bubble_chart_layout(fig,chosenChart,chartDict,showLegend,column,numberOfRows):
    namingParams=get_naming_params()
    configParams=get_config_params()  
    font=configParams[namingParams["fontChoice"]]
    fontSize=configParams[namingParams["fontSizeText"]] 
    uniformTextMinSize=get_uniform_text_min_size(configParams, namingParams)  
    motionChart=namingParams["motionChart"]
    totalName=namingParams["totalName"]
    yAxisMetric=namingParams["yAxisMetric"]
    xAxisMetric=namingParams["xAxisMetric"]
    yAxisDimension=namingParams["yAxisDimension"]
    smallMultiplesColumn=namingParams["smallMultiplesColumn"]
    xDimension=chartDict[xAxisMetric]
    yDimension=chartDict[yAxisMetric]
    numberOfTicks=5
    mirror=True
    showgrid=False
    width=800
    height=width
    if column != totalName:
        width=1000
        height=width/2*numberOfRows  
    if (yAxisDimension in chartDict and column == totalName) or (yAxisDimension in chartDict and smallMultiplesColumn in chartDict and chartDict[smallMultiplesColumn] != chartDict[yAxisDimension]):
        width=width+100  
    if chosenChart in [motionChart]:
        width,height=1000,1000  
    fig.update_layout(
            template='simple_white', 
            width=width,
            height=height,                 
            uniformtext=dict(mode="hide", minsize=uniformTextMinSize),      
            showlegend=showLegend,   
            paper_bgcolor='rgba(0,0,0,0)',
            plot_bgcolor='rgba(0,0,0,0)' ,
            )
    fig.update_yaxes(
        showgrid=showgrid,
        mirror=mirror,
        linecolor="lightgrey",
        tickmode="auto",
        nticks=numberOfTicks,
        ticks="",
        title=dict(font=dict(size=fontSize))
        )
    fig.update_xaxes(
        showgrid=showgrid,
        mirror=mirror,
        linecolor="lightgrey",
        tickmode="auto",
        nticks=numberOfTicks,
        ticks="",
        title=dict(font=dict(size=fontSize))
        )
    return fig

def update_scatter_chart_layout(fig,chartDict,column,showLegend,datashader,numberOfRows):
    namingParams=get_naming_params()
    configParams=get_config_params()
    uniformTextMinSize=get_uniform_text_min_size(configParams, namingParams)  
    motionChart=namingParams["motionChart"]
    totalName=namingParams["totalName"]
    font=configParams[namingParams["fontChoice"]]
    fontSize=configParams[namingParams["fontSizeText"]] 
    yAxisMetric=namingParams["yAxisMetric"]
    xAxisMetric=namingParams["xAxisMetric"]
    yAxisDimension=namingParams["yAxisDimension"]
    smallMultiplesColumn=namingParams["smallMultiplesColumn"]
    totalName=namingParams["totalName"]
    xDimension=chartDict[xAxisMetric]
    yDimension=chartDict[yAxisMetric]
    coloraxis=None
    if datashader:
        coloraxis={'colorscale':'greys'}
    numberOfTicks=5
    mirror=True
    showgrid=False
    width=800
    height=width
    if column != totalName:
        width=1000
        height=width/2*numberOfRows  
    if (yAxisDimension in chartDict and column == totalName) or (yAxisDimension in chartDict and smallMultiplesColumn in chartDict and chartDict[smallMultiplesColumn] != chartDict[yAxisDimension]):
        width=width+100     
    if datashader:
        fig.update_traces(
                    hoverongaps=False,
                    )          
    fig.update_layout(
            template='simple_white', 
            width=width,
            height=height,                  
            uniformtext=dict(mode="hide", minsize=uniformTextMinSize),      
            showlegend=True,   
            paper_bgcolor='rgba(0,0,0,0)',
            plot_bgcolor='rgba(0,0,0,0)' ,
            xaxis_title=xDimension,
            yaxis_title=yDimension, 
            coloraxis=coloraxis, 
            )

    if datashader:
        fig.update_layout(coloraxis_showscale=False)  # hide colorbar  
    fig.update_yaxes(
        showgrid=showgrid,
        mirror=mirror,
        linecolor="lightgrey",
        tickmode="auto",
        nticks=numberOfTicks,
        ticks="",
        title=dict(font=dict(size=fontSize))
        )
    fig.update_xaxes(
        showgrid=showgrid,
        mirror=mirror,
        linecolor="lightgrey",
        tickmode="auto",
        nticks=numberOfTicks,
        ticks="",
        title=dict(font=dict(size=fontSize))
        )
    return fig


def update_alternative_combination_chart_layout(fig,chosenChart):
    namingParams=get_naming_params()
    configParams=get_config_params()
    uniformTextMinSize=get_uniform_text_min_size(configParams, namingParams)  
    varianceAmount=namingParams["varianceAmountName"]
    dimension=namingParams["dimensionName"]
    font=configParams[namingParams["fontChoice"]]
    fontSize=configParams[namingParams["fontSizeText"]] 
    numberOfTicks=5
    mirror=True
    showgrid=False
    height=800
    width=height*1.8
    fig.update_layout(
            template='simple_white', 
            width=width,
            height=height,
            xaxis_title=varianceAmount,
            yaxis_title=dimension,                
            uniformtext=dict(mode="hide", minsize=uniformTextMinSize),      
            showlegend=False,   
            paper_bgcolor='rgba(0,0,0,0)',
            plot_bgcolor='rgba(0,0,0,0)' ,
            )
    fig.update_yaxes(
        showgrid=showgrid,
        mirror=mirror,
        linecolor="lightgrey",
        tickmode="auto",
        #nticks=numberOfTicks,
        ticks=""
        )
    fig.update_xaxes(
        showgrid=showgrid,
        mirror=mirror,
        linecolor="lightgrey",
        tickmode="auto",
        nticks=numberOfTicks,
        ticks=""
        )
    return fig



def update_stacked_column_layout(fig,metric):
    configParams=get_config_params()
    namingParams=get_naming_params()
    metricArrayParams=get_metric_array_params()
    priceMetricsArray=metricArrayParams[namingParams["priceMetricsArray"]]
    percentMetricsArray=metricArrayParams[namingParams["percentMetricsArray"]]
    growthMetricArray=metricArrayParams[namingParams["growthMetricArray"]]
    valueMetricsArray=metricArrayParams[namingParams["valueMetricsArray"]]
    volumeMetricsArray=metricArrayParams[namingParams["volumeMetricsArray"]]
    noSumMetricsArray=metricArrayParams[namingParams["noSumMetricsArray"]] 
    uniformTextMinSize=get_uniform_text_min_size(configParams, namingParams) 
    mode="hide"
    if metric in noSumMetricsArray:
        mode="show"
    fig.update_layout(
                                  uniformtext=dict(mode=mode, minsize=uniformTextMinSize),
                                  paper_bgcolor='rgba(0,0,0,0)',
                                  plot_bgcolor='rgba(0,0,0,0)',
                                  margin={
                                                  "autoexpand":True,
                                              },    
                              )
    return fig



  
    


def update_horizontal_waterfall_layout(df,fig,height,width,paramDict,chartDict,plotWithPins):
    namingParams=get_naming_params()
    configParams=get_config_params()
    uniformTextMinSize=get_uniform_text_min_size(configParams, namingParams)  
    runOneDimensionalAnalysis=namingParams["runOneDimensionalAnalysis"]
    horizontalWaterfallChart=namingParams["horizontalWaterfallChart"]
    plotSmallMultiplesKey=namingParams["plotSmallMultiplesOtherCharts"] 
    measureName=namingParams["measureName"]
    varianceAmountName=namingParams["varianceAmountName"]
    maxStringLength=30
    df_lazy = df if isinstance(df, pl.LazyFrame) else df.lazy()
    initialValue = get_polars_value_at_index(df_lazy, varianceAmountName, 0)
    finalValue = get_polars_value_at_index(df_lazy, varianceAmountName, -1)
    padValue=0
    if initialValue <=0 or finalValue <=0:
      padValue=50
    constant=8
    if not plotWithPins and plotSmallMultiplesKey in chartDict and chartDict[plotSmallMultiplesKey]:
        width=width*.7
    else:    
        width=width*.4
    fig.update_layout(
            template='simple_white', 
            width=width+(maxStringLength*constant),
            height=height,                
            margin={
                      "r": 30,
                       "l":  0,
                      "b": 20,
                      "pad":padValue,
                      "autoexpand":True,
                  },
            uniformtext=dict(mode="hide", minsize=uniformTextMinSize),      
            showlegend=False,   
            paper_bgcolor='rgba(0,0,0,0)',
            plot_bgcolor='rgba(0,0,0,0)' ,
            )
    fig.update_yaxes(
                        showticklabels=False, 
                        zeroline= False, 
                        visible= False,
                        ticks= '',
                        rangemode="tozero",
                                       )
    fig.update_yaxes(
                           automargin=True,
                           zeroline= True, 
                           visible= True,
                           ticks= '',
                           showticklabels= False,
                           zerolinecolor='lightgrey',
                           zerolinewidth=0.1,
                           linecolor='white',
                           )                 
    
    if plotWithPins or (plotSmallMultiplesKey not in chartDict or not chartDict[plotSmallMultiplesKey]):
        fig.update_xaxes(
                                   showticklabels=False, 
                                   zeroline= False, 
                                   visible= False,
                                   ticks= '',
                                   zerolinecolor='grey',
                                   linecolor='grey',                           
                                   rangemode="tozero",
                                   row=1
                                       )          
        
        fig.update_xaxes(
                              automargin=True,
                              zeroline= False, 
                              ticks= '',
                              showticklabels= True,
                              zerolinecolor='white',
                              linecolor='white',                           
                              rangemode="tozero",
                              row=2,
                            )
    else:
        fig.update_xaxes(
                              automargin=True,
                              zeroline= False, 
                              ticks= '',
                              showticklabels= True,
                              zerolinecolor='white',
                              linecolor='grey',                           
                              rangemode="tozero",
                            )    
    return fig

def update_stacked_bar_layout(fig,chartDict):
    configParams=get_config_params()
    namingParams=get_naming_params()
    uniformTextMinSize=get_uniform_text_min_size(configParams, namingParams) 
    plotSmallMultiplesKey=namingParams["plotSmallMultiplesOtherCharts"]  
    chosenChartKey=namingParams["chosenChart"]
    annotationDict=configParams[namingParams["annotationDict"]]
    chosenChart=chartDict[chosenChartKey]
    textMode="hide"
    fig.update_layout(
                    uniformtext=dict(mode=textMode, minsize=uniformTextMinSize),
                    paper_bgcolor='rgba(0,0,0,0)',
                    plot_bgcolor='rgba(0,0,0,0)' ,
                    margin={
                                "t":annotationDict[chosenChart]["topMargin"],
                                "autoexpand":True,
                            },  
                              )  
    return fig

def update_timeline_chart_layout(fig,height,width,chosenChart):
    namingParams=get_naming_params()
    configParams=get_config_params()
    annotationDict=configParams[namingParams["annotationDict"]] 
    goldenRatio=configParams[namingParams["goldenRatio"]] 
    uniformTextMinSize=get_uniform_text_min_size(configParams, namingParams)  
    timelineChart=namingParams["timelineChart"]
    totalName=namingParams["totalName"]
    font=configParams[namingParams["fontChoice"]]
    fontSize=configParams[namingParams["fontSizeText"]]     
    numberOfTicks=5
    showgrid=False
    height=height+(annotationDict[chosenChart]["topMargin"]-100)
    tickvals=None
    tickmode=None
    ticktext=None
    fig.update_layout(
            template='simple_white', 
            width=width,
            height=height,                  
            uniformtext=dict(mode="hide", minsize=uniformTextMinSize),      
            showlegend=False,   
            paper_bgcolor='rgba(0,0,0,0)',
            plot_bgcolor='rgba(0,0,0,0)' ,
            margin={
                    "autoexpand":True,
                }, 
            )
    fig.update_yaxes(
        showgrid=showgrid,
        rangemode="tozero",
        #mirror=mirror,
        linecolor="white",
        tickvals= tickvals,
        tickmode= tickmode,
        ticktext= ticktext,  
        showticklabels=False,
        #nticks=numberOfTicks,
        ticks=""
        )
    fig.update_xaxes(
        showgrid=showgrid,
        #mirror=mirror,
        linecolor="lightgrey",
        tickmode="auto",
        ticks=""
        )
    return fig

def update_cy_ac_layout(fig,height,width,paramDict,chartDict,plotWithPins): 
    namingParams=get_naming_params()
    configParams=get_config_params()
    font=configParams[namingParams["fontChoice"]]  
    fontSize=configParams[namingParams["fontSizeText"]]     
    periodName=namingParams["periodName"]
    timelineChart=namingParams["timelineChart"]
    chosenChart=namingParams["chosenChart"]
    plotSmallMultiplesKey=namingParams["plotSmallMultiplesOtherCharts"] 
    chosenChart=chartDict[chosenChart]
    showYTicklabels=False
    if not plotWithPins and plotSmallMultiplesKey in chartDict and chartDict[plotSmallMultiplesKey]:
        pass
    else:    
        width=width*.8
    fig.update_layout(
            template='simple_white', 
            width=width,
            height=height,
            margin={
                      "t":70,
                      "r": 0,
                      "l": 0,
                      "b": 0,
                      "pad":0,
                      "autoexpand":True,
                  },                                 
            #showlegend=False,  
            legend={'traceorder':'normal'},
            #legend_title_text='', 
            paper_bgcolor='rgba(0,0,0,0)',
            plot_bgcolor='rgba(0,0,0,0)'               
            )
    fig.update_xaxes(
                           zeroline= True, 
                           visible= True,
                           ticks= '',
                           showticklabels= True,
                           zerolinecolor='Grey',                       
                           )  
    fig.update_yaxes(
                           rangemode="tozero",
                           zeroline= False, 
                           automargin=True,
                           ticks= '',
                           showticklabels= showYTicklabels,
                           linecolor='white',
                        )
    
    return fig

def update_multitier_column_layout(df,fig,height,width,paramDict,chartDict,plotWithPins):
    namingParams=get_naming_params()
    configParams=get_config_params()
    plotSmallMultiplesKey=namingParams["plotSmallMultiplesOtherCharts"] 
    fontSize=configParams[namingParams["fontSizeText"]] 
    font=configParams[namingParams["fontChoice"]]
    goldenRatio=configParams[namingParams["goldenRatio"]]     
    uniformTextMinSize=get_uniform_text_min_size(configParams, namingParams)  
    acName=namingParams["acName"] 
    pyName=namingParams["pyName"]  
    plName=namingParams["plName"]
    totalName=namingParams["totalName"]
    chosenChart=namingParams["chosenChart"]  
    chosenChart=chartDict[chosenChart]
    period_value_columns = [
        column
        for column in [acName, pyName, plName]
        if column in get_schema_and_column_names(df)[0]
    ]
    period_extrema = [
        abs(value)
        for column in period_value_columns
        for value in [df[column].min(), df[column].max()]
        if value is not None
    ]
    ymax = (max(period_extrema) / 1.3) if period_extrema else 1
    if not plotWithPins and plotSmallMultiplesKey in chartDict and chartDict[plotSmallMultiplesKey]:
        width=width*.7
    else:    
        width=width*.6    
    fig.update_layout(
                template='simple_white', 
                width=width,
                height=height,
                margin={
                      "r": 30,
                       "l":  0,
                      "b": 20,
                    "pad":0,
                    "autoexpand":True,
                      },
                uniformtext=dict(mode="show", minsize=uniformTextMinSize),
                #showlegend=False,       
                legend={'traceorder':'normal'},
                legend_title_text='', 
                paper_bgcolor='rgba(0,0,0,0)',
                plot_bgcolor='rgba(0,0,0,0)'  ,          
                )
    fig.update_yaxes(
                                   rangemode="tozero",
                                   zeroline= True, 
                                   automargin=True,
                                   ticks= '',
                                   showticklabels= False,
                                   zerolinecolor='grey',
                                   linecolor='white',
                                )    
    if plotWithPins or (plotSmallMultiplesKey not in chartDict or not chartDict[plotSmallMultiplesKey]):
        fig.update_xaxes(
                                   showticklabels=True, 
                                   zeroline= False, 
                                   visible= True,
                                   ticks= '',
                                   zerolinecolor='grey',
                                   linecolor='grey',
                                   rangemode="tozero",
                                   row=3
                                       ) 
        
        fig.update_xaxes(
                                   showticklabels=False, 
                                   zeroline= False, 
                                   visible= False,
                                   ticks= '',
                                   zerolinecolor='grey',
                                   linecolor='grey',                          
                                   rangemode="tozero",
                                   row=2,
                                   
                                       ) 
        fig.update_xaxes(
                                   showticklabels=False, 
                                   zeroline= False, 
                                   visible= False,
                                   ticks= '',
                                   zerolinecolor='grey',
                                   linecolor='grey',                           
                                   rangemode="tozero",
                                   row=1
                                       )                                  

        fig.update_yaxes(
                                   row=2,
                                   range=[-ymax, ymax],
                                )
    else:
        fig.update_xaxes(
                              automargin=False,
                              zeroline= False, 
                              ticks= '',
                              zerolinecolor='white',
                              linecolor='grey',                           
                              rangemode="tozero",
                            )   
    return fig

def update_slope_chart_layout(fig,chosenChart,height,width):
    namingParams=get_naming_params()
    configParams=get_config_params()
    annotationDict=configParams[namingParams["annotationDict"]] 
    goldenRatio=configParams[namingParams["goldenRatio"]] 
    uniformTextMinSize=get_uniform_text_min_size(configParams, namingParams)  
    timelineChart=namingParams["timelineChart"]
    slopeChart=namingParams["slopeChart"]
    totalName=namingParams["totalName"]
    font=configParams[namingParams["fontChoice"]]
    fontSize=configParams[namingParams["fontSizeText"]]     
    numberOfTicks=5
    showgrid=False
    tickvals=None
    tickmode=None
    ticktext=None
    fig.update_layout(
            template='simple_white', 
            width=width,
            height=height,                  
            uniformtext=dict(mode="hide", minsize=uniformTextMinSize),      
            showlegend=False,   
            paper_bgcolor='rgba(0,0,0,0)',
            plot_bgcolor='rgba(0,0,0,0)' ,
            margin={
                    "autoexpand":True,
                }, 
            )
    fig.update_yaxes(
        showgrid=showgrid,
        rangemode="tozero",
        #mirror=mirror,
        linecolor="white",
        tickvals= tickvals,
        tickmode= tickmode,
        ticktext= ticktext,  
        showticklabels=False,
        #nticks=numberOfTicks,
        ticks=""
        )
    fig.update_xaxes(
        showgrid=showgrid,
        #mirror=mirror,
        linecolor="lightgrey",
        tickmode="auto",
        ticks=""
        )
    return fig
