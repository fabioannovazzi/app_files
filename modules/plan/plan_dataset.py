import polars as pl
import copy
from collections.abc import Sequence
from contextlib import nullcontext


from modules.utilities.ui_notifier import ui

from modules.layout.memoization import (
    check_collect,
    get_hashed_key,
)
from modules.utilities.config import (
    get_config_params,
    get_naming_params,
)
from modules.utilities.error_messages import (
    add_error_message_in_plan_dataset_tab,
    add_warning_message_in_plan_dataset_tab,
)
from modules.utilities.helpers import (
    check_and_clean_columns,
    convert_df,
    drop_columns,
    duplicate_dataframe,
    insert_json_value,
    unique,
    get_image_name_hash,
)
from modules.layout.layout_helpers import (
    make_five_col_width_array,
    make_six_col_width_array,
    make_three_col_width_array,
)
from modules.utilities.utils import (
    get_row_count,
    get_schema_and_column_names,
    unique_values_lazy,
)

from modules.layout.set_up_widgets import (
    set_plan_or_forecast_widget,
    set_time_profile_widget,
    change_discount_and_cogs_in_proportion_to_sales,
    show_percentage_change_widget,
    set_collision_choice_widget,
    add_new_dimension,
    submit_plan_dataset,
)


def _context_from(obj):
    """Return a usable context manager even when the caller passes a list of containers."""

    candidate = obj
    if isinstance(candidate, Sequence) and not isinstance(candidate, (str, bytes)):
        candidate = next(iter(candidate), None)
    if hasattr(candidate, "__enter__") and hasattr(candidate, "__exit__"):
        return candidate  # type: ignore[return-value]
    return nullcontext()


def pull_widgets_down(colArray,applyArray):
    for column in applyArray:
        colArray[column].write("\n")
        colArray[column].write("\n") 
        colArray[column].write("\n")
        colArray[column].write("\n")  
        colArray[column].write("\n")
        colArray[column].write("\n") 
        colArray[column].write("\n") 
        colArray[column].write("\n") 
    return None 

def get_percent_change_labels(metric,label,labelPrefix,forecastType,price):
    namingParams=get_naming_params() 
    defaultForecast=namingParams["defaultForecastName"]
    percentChangeLabel=namingParams["percentChangeLabel"]
    forecastChangeLabel=namingParams["forecastChangeLabel"]
    modifierLabel=namingParams["modifierLabel"]         
    if label: 
        tooltip=forecastType+""" """+metric+""" """+price+""" forecast in %"""
        message=forecastType+""" """+metric+""" """+price+""" forecast in %""" 
        label=labelPrefix+label
        label=label.capitalize()
    else:  
        tooltip=metric+""" forecast in % for """+forecastType+"""."""
        message="""✳️"""+metric+""" forecast in % for """+forecastType+"""."""
    tooltip=tooltip.capitalize()
    message=message.capitalize()
    message="""✳️"""+message
    if forecastType != defaultForecast:
        if percentChangeLabel in label:
            label=label.replace(percentChangeLabel,modifierLabel)
        tooltip=tooltip.replace(forecastChangeLabel,modifierLabel) 
    return label,tooltip,message

def get_forecast_params(df,indexCols,valueCols,planDict,paramDict,chartDict,forecastType,itemNbr,colArray,multipleDimensions,dimensionNbr,planPlaybackDict):
    namingParams=get_naming_params()
    unitsForecastValue=namingParams["unitsForecastValue"]
    unitsForecastLabel=namingParams["unitsForecastLabel"]
    unitPriceForecastValue=namingParams["unitPriceForecastValue"]
    unitPriceForecastLabel=namingParams["unitPriceForecastLabel"]    
    volumesForecastValue=namingParams["volumesForecastValue"]
    volumePriceForecastValue=namingParams["volumePriceForecastValue"]
    volumesForecastLabel=namingParams["volumesForecastLabel"]
    volumePriceForecastLabel=namingParams["volumePriceForecastLabel"]
    salesForecastValue=namingParams["salesForecastValue"]
    salesForecastLabel=namingParams["salesForecastLabel"]
    discountsForecastValue=namingParams["discountsForecastValue"]
    discountsForecastLabel=namingParams["discountsForecastLabel"]
    cogsForecastValue=namingParams["cogsForecastValue"]
    cogsForecastLabel=namingParams["cogsForecastLabel"]
    unitsName=namingParams["unitsName"]
    volumeName=namingParams["volumeName"]
    costsName=namingParams["costsName"]
    discountName=namingParams["discountName"]
    amountName=namingParams["monetaryLocalCurrencyName"]
    defaultForecast=namingParams["defaultForecastName"]
    discountName=namingParams["discountName"]
    cogsName=namingParams["cogsName"]
    colorChoice=namingParams["colorChoice"]
    greenToRed=namingParams["greenToRed"]
    blueToOrange=namingParams["blueToOrange"]
    changeInProportionToSales=namingParams["changeInProportionToSales"]  
    leftColIndex=dimensionNbr
    rightColIndex=dimensionNbr
    showMessage=False 
    labelPrefix="" 
    disabled=False  
    if multipleDimensions:
        leftColIndex=dimensionNbr
        rightColIndex=dimensionNbr       
    elif forecastType==defaultForecast:
        leftColIndex=dimensionNbr+2
        rightColIndex=dimensionNbr+3
        showMessage=True
        labelPrefix=defaultForecaui.title()+" "   
    if forecastType == defaultForecast:
        with colArray[3]:
            planDict=change_discount_and_cogs_in_proportion_to_sales(planDict,valueCols,planPlaybackDict)   
    if unitsName in valueCols:
        label,tooltip,message=get_percent_change_labels(unitsName,unitsForecastLabel,labelPrefix,forecastType,"")
        planDict=show_percentage_change_widget(unitsForecastValue,label,message,tooltip,planDict,paramDict,colArray[leftColIndex],forecastType,showMessage,disabled,dimensionNbr,itemNbr,planPlaybackDict)         
        label,tooltip,message=get_percent_change_labels(unitsName,unitPriceForecastLabel,labelPrefix,forecastType,"price") 
        planDict=show_percentage_change_widget(unitPriceForecastValue,label,message,tooltip,planDict,paramDict,colArray[rightColIndex],forecastType,showMessage,disabled,dimensionNbr,itemNbr,planPlaybackDict)
    elif volumeName in valueCols:
        label,tooltip,message=get_percent_change_labels(volumeName,volumesForecastLabel,labelPrefix,forecastType,"")
        planDict=show_percentage_change_widget(volumesForecastValue,label,message,tooltip,planDict,paramDict,colArray[leftColIndex],forecastType,showMessage,disabled,dimensionNbr,itemNbr,planPlaybackDict)        
        label,tooltip,message=get_percent_change_labels(volumeName,volumePriceForecastLabel,labelPrefix,forecastType,"price") 
        planDict=show_percentage_change_widget(volumePriceForecastValue,label,message,tooltip,planDict,paramDict,colArray[rightColIndex],forecastType,showMessage,disabled,dimensionNbr,itemNbr,planPlaybackDict)        
    if unitsName not in valueCols and volumeName not in valueCols:
        if colorChoice in chartDict and chartDict[colorChoice] in [greenToRed,blueToOrange]:
            label,tooltip,message=get_percent_change_labels(costsName,salesForecastLabel,labelPrefix,forecastType,"")
        else:   
            label,tooltip,message=get_percent_change_labels(amountName,salesForecastLabel,labelPrefix,forecastType,"")     
        planDict=show_percentage_change_widget(salesForecastValue,label,message,tooltip,planDict,paramDict,colArray[leftColIndex],forecastType,showMessage,disabled,dimensionNbr,itemNbr,planPlaybackDict)
        label,tooltip,message=get_percent_change_labels("",volumePriceForecastLabel,labelPrefix,forecastType,"price") 
        planDict=show_percentage_change_widget(volumePriceForecastValue,label,message,tooltip,planDict,paramDict,colArray[rightColIndex],forecastType,showMessage,True,dimensionNbr,itemNbr,planPlaybackDict)                      
    if changeInProportionToSales in planDict and planDict[changeInProportionToSales]:
        if discountName not in valueCols:
            disabled=True
        label,tooltip,message=get_percent_change_labels(discountName,discountsForecastLabel,labelPrefix,forecastType,"")
        planDict=show_percentage_change_widget(discountsForecastValue,label,message,tooltip,planDict,paramDict,colArray[leftColIndex],forecastType,showMessage,disabled,dimensionNbr,itemNbr,planPlaybackDict)       
        if cogsName not in valueCols:
            disabled=True
        label,tooltip,message=get_percent_change_labels(cogsName,cogsForecastLabel,labelPrefix,forecastType,"")
        planDict=show_percentage_change_widget(cogsForecastValue,label,message,tooltip,planDict,paramDict,colArray[rightColIndex],forecastType,showMessage,disabled,dimensionNbr,itemNbr,planPlaybackDict)        
    return planDict


def forecast_category(df,column,firstKey,secondKey,colArray,paramDict,chosenValues,dimension,planPlaybackDict):
    namingParams=get_naming_params()
    preparePlanParams=namingParams["preparePlanParams"]
    notDefaultForecastName=namingParams["notDefaultForecastName"]
    conditionKeyName=namingParams["conditionName"]
    columnHash=paramDict[namingParams["columnHash"]]
    checkKey=firstKey+secondKey+column
    hashKey=get_hashed_key(checkKey,columnHash)  
    # Use Polars unique values helper to support both DataFrame and LazyFrame
    choiceArray = unique_values_lazy(column, df)
    for choice in chosenValues:
        if choice in choiceArray:
            choiceArray.remove(choice) 
    value=None
    valueDict=planPlaybackDict
    if preparePlanParams in planPlaybackDict:
        if notDefaultForecastName in planPlaybackDict[preparePlanParams]:
            valueDict=planPlaybackDict[preparePlanParams][notDefaultForecastName]  
            if firstKey in valueDict:
                valueDict=valueDict[firstKey]
                if conditionKeyName in valueDict:
                    valueDict=valueDict[conditionKeyName]
                    if secondKey in valueDict:
                        valueDict=valueDict[secondKey]                                                    
    value=insert_json_value("condition",value,valueDict,choiceArray,column,None)           
    userCatInput = colArray[dimension].multiselect(
                f"↳ Values for {column}",
                choiceArray,default=value,
                key=hashKey,max_selections=None,
                        )
    chosenValues=userCatInput+chosenValues
    return userCatInput,chosenValues 

def check_if_conditions_complete(planDict,dimensionNbr,dictKey,userCatInput,toForecastColumns):
    namingParams=get_naming_params()
    preparePlanParams=namingParams["preparePlanParams"]
    conditionKeyName=namingParams["conditionName"] 
    notDefaultForecastName=namingParams["notDefaultForecastName"]
    complete=True
    if len(toForecastColumns)>1:
        for element in planDict[preparePlanParams][notDefaultForecastName][dimensionNbr][conditionKeyName][dictKey]:
            if len(planDict[preparePlanParams][notDefaultForecastName][dimensionNbr][conditionKeyName][dictKey][element]) ==0:
                complete=False
    return complete

def update_plan_dictionary(planDict,dimensionNbr,dictKey,userCatInput,toForecastColumns,column):
    namingParams=get_naming_params()
    preparePlanParams=namingParams["preparePlanParams"]
    conditionKeyName=namingParams["conditionName"]
    notDefaultForecastName=namingParams["notDefaultForecastName"]
    if conditionKeyName not in planDict[preparePlanParams][notDefaultForecastName][dimensionNbr]:
        planDict[preparePlanParams][notDefaultForecastName][dimensionNbr][conditionKeyName]={}
    if dictKey not in planDict[preparePlanParams][notDefaultForecastName][dimensionNbr][conditionKeyName]:
        planDict[preparePlanParams][notDefaultForecastName][dimensionNbr][conditionKeyName][dictKey]={}  
    if len(toForecastColumns)>1:
        if column not in planDict[preparePlanParams][notDefaultForecastName][dimensionNbr][conditionKeyName][dictKey]:
            planDict[preparePlanParams][notDefaultForecastName][dimensionNbr][conditionKeyName][dictKey][column]={}  
        planDict[preparePlanParams][notDefaultForecastName][dimensionNbr][conditionKeyName][dictKey][column]=userCatInput
    else:
        planDict[preparePlanParams][notDefaultForecastName][dimensionNbr][conditionKeyName][dictKey]=userCatInput        
    return planDict 

def set_dimension_forecast_widgets(df,indexCols,valueCols,number,colArray,planDict,paramDict,chartDict,planPlaybackDict):
    namingParams=get_naming_params()
    configParams=get_config_params() 
    columnHash=paramDict[namingParams["columnHash"]]
    chooseColumnLabel=namingParams["chooseFilterColumnLabel"]
    nothingFilteredName=namingParams["nothingFilteredName"]
    preparePlanParams=namingParams["preparePlanParams"]
    dimensionLabel=namingParams["dimensionLabel"]
    notDefaultForecastName=namingParams["notDefaultForecastName"]
    dimensionKeyName=namingParams["dimensionName"]
    numberOfItems=configParams[namingParams["numberOfItems"]]  
    numberOfDimensions=configParams[namingParams["numberOfDimensions"]]
    chooseColumnLabel=chooseColumnLabel+" #"+str(number)
    hashKey=get_hashed_key("Column"+str(number),columnHash)
    modify=False
    disabled=False
    if notDefaultForecastName not in planDict[preparePlanParams]:
        planDict[preparePlanParams][notDefaultForecastName]={}
    for dimensionNbr in range(0, numberOfDimensions):
        if dimensionNbr not in planDict[preparePlanParams][notDefaultForecastName]:
            planDict[preparePlanParams][notDefaultForecastName][dimensionNbr]={}
        if dimensionNbr ==0 or newDimension:
            toForecastColumns,newDimension,planDict=add_new_dimension(indexCols,dimensionNbr,colArray,hashKey,planDict,planPlaybackDict)             
            if len(toForecastColumns)>0:
                if dimensionNbr==numberOfDimensions-1:
                    disabled=True     
                newDimension,planDict=add_checkbox(hashKey,dimensionKeyName,str(dimensionNbr),str(dimensionNbr),colArray[dimensionNbr],disabled,planPlaybackDict,planDict)
            chosenValues=[]
            disabled=False     
            for column in toForecastColumns:
                for item in range(0, numberOfItems):
                    if item ==0 or modify: 
                        if item==numberOfItems-1:
                            disabled=True 
                        modify=False  
                        userCatInput,chosenValues=forecast_category(df,column,str(dimensionNbr),str(item),colArray,paramDict,chosenValues,dimensionNbr,planPlaybackDict)                                                                                               
                        dictKey=item  
                        planDict=update_plan_dictionary(planDict,dimensionNbr,dictKey,userCatInput,toForecastColumns,column)
                        if len(userCatInput)>0 and len(toForecastColumns)==1:
                            planDict=get_forecast_params(df,indexCols,valueCols,planDict,paramDict,chartDict,column,item,colArray,False,dimensionNbr,planPlaybackDict)
                            modify,planDict=add_checkbox(hashKey,"item",str(dimensionNbr),str(item),colArray[dimensionNbr],disabled,planPlaybackDict,planDict)                                          
            if len(toForecastColumns)>1:
                planDict=get_forecast_params(df,indexCols,valueCols,planDict,paramDict,chartDict,toForecastColumns[0],0,colArray,True,dimensionNbr,planPlaybackDict) 
                for item in range(1, numberOfItems):
                    complete=check_if_conditions_complete(planDict,dimensionNbr,dictKey,userCatInput,toForecastColumns)
                    if complete and (item ==1 or modify):
                        modify=False                      
                        modify,planDict=add_checkbox(hashKey,"item",str(dimensionNbr),str(item),colArray[dimensionNbr],disabled,planPlaybackDict,planDict)
                    if modify:
                        for column in toForecastColumns: 
                            userCatInput,chosenValues=forecast_category(df,column,str(dimensionNbr),str(item),colArray,paramDict,[],dimensionNbr,planPlaybackDict)   
                            planDict=update_plan_dictionary(planDict,dimensionNbr,item,userCatInput,toForecastColumns,column)
                        planDict=get_forecast_params(df,indexCols,valueCols,planDict,paramDict,chartDict,toForecastColumns[0],item,colArray,True,dimensionNbr,planPlaybackDict)                        
    return df,planDict

def calculate_default_volume_and_price_change(df,forecastValueKey,planDict):
    namingParams=get_naming_params()
    metricName=namingParams["metricName"]
    metricPLName=namingParams["metricPLName"]
    preparePlanParams=namingParams["preparePlanParams"]
    defaultForecastName=namingParams["defaultForecastName"]
    unitsForecastValue=namingParams["unitsForecastValue"]
    unitsName=namingParams["unitsName"]
    unitsPL=namingParams["unitsPLName"]
    cogsForecastValue=namingParams["cogsForecastValue"]
    cogsName=namingParams["cogsName"] 
    cogsPLName=namingParams["cogsPLName"]
    discountsForecastValue=namingParams["discountsForecastValue"]
    discountName=namingParams["discountName"]
    discountPLName=namingParams["discountPLName"]
    unitPriceForecastValue=namingParams["unitPriceForecastValue"]  
    pricePerUnitName=namingParams["pricePerUnitName"] 
    unitPricePL=namingParams["unitPricePLName"]
    volumesForecastValue=namingParams["volumesForecastValue"]
    volumeName=namingParams["volumeName"] 
    volumesPL=namingParams["volumesPLName"]
    volumePriceForecastValue=namingParams["volumePriceForecastValue"]
    pricePerVolumeName=namingParams["pricePerVolumeName"]
    volumePricePL=namingParams["volumePricePLName"] 
    salesForecastValue=namingParams["salesForecastValue"]
    monetaryName=namingParams["monetaryLocalCurrencyName"]
    monetaryPLName=namingParams["monetaryLocalCurrencyPLName"]         
    metricDict={
                unitsForecastValue:{
                                metricName:unitsName,
                                metricPLName:unitsPL,
                                },
                unitPriceForecastValue:{
                                metricName:pricePerUnitName,
                                metricPLName:unitPricePL,
                                },
                volumesForecastValue:{
                                metricName:volumeName,
                                metricPLName:volumesPL,
                                }, 
                volumePriceForecastValue:{
                                metricName:pricePerVolumeName,
                                metricPLName:volumePricePL,
                                }, 
                salesForecastValue:{
                                metricName:monetaryName,
                                metricPLName:monetaryPLName,
                                },  
                
                cogsForecastValue:{
                                metricName:cogsName,
                                metricPLName:cogsPLName,
                                },

               discountsForecastValue:{
                                metricName:discountName,
                                metricPLName:discountPLName,
                                },


                }
    defaultForecastDict=planDict[preparePlanParams][defaultForecastName]
    columns,schema=get_schema_and_column_names(df) 
    if forecastValueKey in defaultForecastDict: 
        if forecastValueKey in metricDict:
            metric=metricDict[forecastValueKey][metricName]
            metricPL=metricDict[forecastValueKey][metricPLName]
            if forecastValueKey in columns:
                df = df.with_columns((pl.col(metric) * pl.col(forecastValueKey)).alias(metric))
        if defaultForecastDict[forecastValueKey] != 0:
            multiplier=(1+(defaultForecastDict[forecastValueKey]/100))
            df = df.with_columns((pl.col(metric) * pl.lit(multiplier)).alias(metricPL))
        else:
            df = df.with_columns(pl.col(metric).alias(metricPL))
    return df 

def copy_forecast_in_metric_column(df,columns,forecastValueKey,deleteArray):
    namingParams=get_naming_params()
    metricName=namingParams["metricName"]
    metricPLName=namingParams["metricPLName"]
    defaultForecastName=namingParams["defaultForecastName"]
    unitsForecastValue=namingParams["unitsForecastValue"]
    unitsName=namingParams["unitsName"]
    unitsPL=namingParams["unitsPLName"]
    unitPriceForecastValue=namingParams["unitPriceForecastValue"]  
    pricePerUnitName=namingParams["pricePerUnitName"] 
    unitPricePL=namingParams["unitPricePLName"]
    volumesForecastValue=namingParams["volumesForecastValue"]
    volumeName=namingParams["volumeName"] 
    volumesPL=namingParams["volumesPLName"]
    volumePriceForecastValue=namingParams["volumePriceForecastValue"]
    pricePerVolumeName=namingParams["pricePerVolumeName"]
    volumePricePL=namingParams["volumePricePLName"] 
    salesForecastValue=namingParams["salesForecastValue"]
    monetaryName=namingParams["monetaryLocalCurrencyName"]
    monetaryPLName=namingParams["monetaryLocalCurrencyPLName"] 
    cogsName=namingParams["cogsName"] 
    cogsPLName=namingParams["cogsPLName"]
    cogsForecastValue=namingParams["cogsForecastValue"]
    discountsForecastValue=namingParams["discountsForecastValue"]
    discountName=namingParams["discountName"]
    discountPLName=namingParams["discountPLName"]  
    metricDict={
                unitsForecastValue:{
                                metricName:unitsName,
                                metricPLName:unitsPL,
                                },
                unitPriceForecastValue:{
                                metricName:pricePerUnitName,
                                metricPLName:unitPricePL,
                                },
                volumesForecastValue:{
                                metricName:volumeName,
                                metricPLName:volumesPL,
                                }, 
                volumePriceForecastValue:{
                                metricName:pricePerVolumeName,
                                metricPLName:volumePricePL,
                                }, 
                salesForecastValue:{
                                metricName:monetaryName,
                                metricPLName:monetaryPLName,
                                },    

                cogsForecastValue:{
                                metricName:cogsName,
                                metricPLName:cogsPLName,
                                },  
                discountsForecastValue:{
                                metricName:discountName,
                                metricPLName:discountPLName,
                                },  
                }
    if forecastValueKey in metricDict:
        metric=metricDict[forecastValueKey][metricName]
        metricPL=metricDict[forecastValueKey][metricPLName]
        if forecastValueKey in columns:
           deleteArray.append(forecastValueKey)   
    if metricPL in columns:
        df = df.with_columns(pl.col(metricPL).alias(metric))
        if metricPL not in deleteArray:
            deleteArray.append(metricPL)       
    return df,deleteArray 

def calculate_default_PL_change(df,planDict):
    namingParams=get_naming_params() 
    preparePlanParams=namingParams["preparePlanParams"]
    defaultForecastName=namingParams["defaultForecastName"]
    pricePerUnitName=namingParams["pricePerUnitName"]     
    pricePerVolumeName=namingParams["pricePerVolumeName"] 
    deleteArray=[pricePerUnitName,pricePerVolumeName]
    metricArray=planDict[preparePlanParams][defaultForecastName]
    for metric in metricArray:
        df=calculate_default_volume_and_price_change(df,metric,planDict)
        columns,schema=get_schema_and_column_names(df)
        df,deleteArray=copy_forecast_in_metric_column(df,columns,metric,deleteArray)              
    return df,deleteArray,metricArray

def set_month_profile_parameters(planDict,paramDict,planPlaybackDict):
    namingParams=get_naming_params()
    timeProfile=namingParams["timeProfile"]
    timeProfileValues=namingParams["timeProfileValues"]
    custom=namingParams["custom"]
    likeBaseYear=namingParams["likeBaseYear"]
    expectedTotal=False
    monthValueArray=[]
    planDict[timeProfileValues]=False
    if timeProfile in planDict and planDict[timeProfile]==custom:
        with ui.form("setMonthForm"):
            expectedTotal=1200
            ui.caption("""Modify the values in the widgets to profile seasonality and hit the 'Check values' button. Total must equal """+str(expectedTotal))
            colArray=make_six_col_width_array()
            monthValueDict={} 
            for monthNumber in range(1, 13):
                monthValue=make_month_widget(monthNumber,paramDict,colArray,expectedTotal,planPlaybackDict)
                monthValueArray.append(monthValue)
            planDict[timeProfileValues]=monthValueArray
            labeltext="Check values" 
            checkValues = ui.form_submit_button(label=labeltext)    
            if checkValues:
                total=np.sum(planDict[timeProfileValues])
                if total != expectedTotal:
                    message="Month widget total is equal to "+str(total)+" but should be equal to "+str(expectedTotal)+". Impossible to calculate custom seasonality"
                    paramDict=add_warning_message_in_plan_dataset_tab(paramDict,message)
                    message="Time profile parameter set to 'Base'"
                    paramDict=add_warning_message_in_plan_dataset_tab(paramDict,message)
                    planDict[timeProfile]=likeBaseYear
                if set(planDict[timeProfileValues])==int(expectedTotal)/12:
                    planDict[timeProfile]=likeBaseYear 
    return planDict,expectedTotal,paramDict

def recalculate_value_metric(df,columns,valueMetric,countMetric,priceMetric):
    if countMetric in columns and priceMetric in columns:
        df = df.with_columns((pl.col(countMetric) * pl.col(priceMetric)).alias(valueMetric))
    return df 

def calculate_price_times_volume_forecast(df,deleteArray,metricArray):
    namingParams=get_naming_params()
    periodName=namingParams["periodName"]
    plName=namingParams["plName"]   
    unitsName=namingParams["unitsName"]
    volumeName=namingParams["volumeName"] 
    monetaryName=namingParams["monetaryLocalCurrencyName"] 
    pricePerUnitName=namingParams["pricePerUnitName"]     
    pricePerVolumeName=namingParams["pricePerVolumeName"]
    monetaryPLName=namingParams["monetaryLocalCurrencyPLName"]
    cogsName=namingParams["cogsName"] 
    cogsPLName=namingParams["cogsPLName"]
    cogsForecastValue=namingParams["cogsForecastValue"]
    discountsForecastValue=namingParams["discountsForecastValue"]    
    discountName=namingParams["discountName"]
    discountPLName=namingParams["discountPLName"]     
    columns,schema=get_schema_and_column_names(df)
    countMetric,priceMetric=volumeName,pricePerVolumeName
    if unitsName in columns:
        countMetric,priceMetric=unitsName,pricePerUnitName
    df=recalculate_value_metric(df,columns,monetaryPLName,countMetric,priceMetric)
    columns,schema=get_schema_and_column_names(df)
    if cogsForecastValue not in metricArray and cogsName in columns:
        if monetaryPLName in columns and monetaryName in columns:
            df = df.with_columns((pl.col(cogsName) * pl.col(monetaryPLName) / pl.col(monetaryName)).alias(cogsName))
        else:
            message="Could not calculate PL COGS values. Missing Actual or PL sales value."
            paramDict=add_error_message_in_plan_dataset_tab(paramDict,message)
    if discountsForecastValue not in metricArray and discountName in columns:
        if monetaryPLName in columns and monetaryName in columns:        
            df = df.with_columns((pl.col(discountName) * pl.col(monetaryPLName) / pl.col(monetaryName)).alias(discountName))
        else:
            message="Could not calculate PL discount values. Missing Actual or PL sales value."
            paramDict=add_error_message_in_plan_dataset_tab(paramDict,message)
    if monetaryPLName in columns:                       
        df = df.with_columns(pl.col(monetaryPLName).alias(monetaryName))
    else:    
        message="Missing PL sales value."
        paramDict=add_error_message_in_plan_dataset_tab(paramDict,message)   
    deleteArray.append(monetaryPLName)   
    df=drop_columns(df,deleteArray)
    df = df.with_columns(pl.lit(plName).alias(periodName))
    return df  

def filter_period_for_plan(df,chartDict):
    namingParams=get_naming_params()
    selectedPeriods=namingParams["selectedPeriods"] 
    periodName=namingParams["periodName"] 
    if selectedPeriods in chartDict:   
        mostRecentPeriod=str(chartDict[selectedPeriods][-1])
        # Step 1: Get unique periods
        periodsArray = (
            df.with_columns(pl.col(periodName).cast(pl.Utf8))  # Convert to string
              .select(pl.col(periodName).unique())            # Unique values
              .collect()[periodName]                          # Collect and convert
              .to_list()
        )
        check_collect("AAC", "periodsArray",periodsArray)
        # Step 2: Filter by mostRecentPeriod
        df = df.filter(pl.col(periodName) == mostRecentPeriod)
    return df 

def add_price_column_metric(df,valueCols):
    namingParams=get_naming_params()
    pricePerUnitName=namingParams["pricePerUnitName"]
    pricePerVolumeName=namingParams["pricePerVolumeName"]
    unitsName=namingParams["unitsName"]
    valueName=namingParams["valueName"]
    monetaryName=namingParams["monetaryLocalCurrencyName"]
    if unitsName in valueCols:
        df = df.with_columns((pl.col(monetaryName) / pl.col(unitsName)).alias(pricePerUnitName))
        df = df.with_columns(pl.col(pricePerUnitName).fill_null(0).alias(pricePerUnitName))
    if valueName in valueCols:
        df = df.with_columns((pl.col(monetaryName) / pl.col(valueName)).alias(pricePerVolumeName))
        df = df.with_columns(pl.col(pricePerVolumeName).fill_null(0).alias(pricePerVolumeName))
    return df  

def calculate_plan_result(dfPlan,dfActual,valueCols,planDict):
    namingParams=get_naming_params()
    amountName=namingParams["monetaryLocalCurrencyName"]
    netOfDiscountName=namingParams["netOfDiscountName"] 
    marginName=namingParams["marginName"] 
    acName=namingParams["acName"]
    planOrForecast=namingParams["planOrForecast"] 
    deltaName=namingParams["deltaName"] 
    discountName=namingParams["discountName"]
    indirectCostsName=namingParams["indirectCostsName"]
    netMarginName=namingParams["netMarginName"]
    cogsName=namingParams["cogsName"]
    unitsName=namingParams["unitsName"]
    volumeName=namingParams["volumeName"]
    pricePerUnitName=namingParams["pricePerUnitName"]
    pricePerVolumeName=namingParams["pricePerVolumeName"]
    orderedArray=[amountName,unitsName,volumeName,
                pricePerUnitName,pricePerVolumeName,discountName,netOfDiscountName,cogsName,marginName]
    reorderlist=[]    
    columns,schema=get_schema_and_column_names(dfPlan)
    if discountName in columns:
        dfPlan = dfPlan.with_columns((pl.col(amountName) - pl.col(discountName)).alias(netOfDiscountName))
    if cogsName in columns:
        if discountName in columns:
            dfPlan = dfPlan.with_columns((pl.col(amountName) - pl.col(discountName) - pl.col(cogsName)).alias(marginName))
        dfPlan = dfPlan.with_columns((pl.col(amountName) - pl.col(cogsName)).alias(marginName))
    if indirectCostsName in columns and cogsName in columns:   
        if discountName in columns:
            dfPlan = dfPlan.with_columns((pl.col(amountName) - pl.col(discountName) - pl.col(cogsName) - pl.col(indirectCostsName)).alias(netMarginName))
        dfPlan = dfPlan.with_columns((pl.col(amountName) - pl.col(cogsName) - pl.col(indirectCostsName)).alias(netMarginName))
    actual_dict = {k: v[0] for k, v in dfActual.select(valueCols).sum().to_dict().items()}
    plan_dict = {k: v[0] for k, v in dfPlan.select(valueCols).sum().to_dict().items()}

    if unitsName in columns:
        actual_dict[pricePerUnitName] = actual_dict[amountName] / actual_dict[unitsName]
        plan_dict[pricePerUnitName] = plan_dict[amountName] / plan_dict[unitsName]
        valueCols.append(pricePerUnitName)

    if volumeName in columns:
        actual_dict[pricePerVolumeName] = actual_dict[amountName] / actual_dict[volumeName]
        plan_dict[pricePerVolumeName] = plan_dict[amountName] / plan_dict[volumeName]
        valueCols.append(pricePerVolumeName)

    for element in orderedArray:
        if element in valueCols:
            reorderliui.append(element)

    rows = []
    for metric in reorderlist:
        rows.append({
            "metric": metric,
            planDict[planOrForecast]: plan_dict.get(metric, 0),
            acName: actual_dict.get(metric, 0),
        })

    dfResult = pl.DataFrame(rows)
    dfResult = dfResult.with_columns(
        (pl.col(planDict[planOrForecast]) - pl.col(acName)).alias(deltaName)
    )
    deltaPercentName = deltaName + "%"
    dfResult = dfResult.with_columns(
        pl.when(pl.col(deltaName) != 0)
        .then((pl.col(deltaName) / pl.col(acName) * 100).round(1))
        .otherwise(0)
        .alias(deltaPercentName)
    )
    ui.dataframe(dfResult)
    return None

def prepare_ac_dataset(dfCopy): 
    namingParams=get_naming_params() 
    pricePerUnitName=namingParams["pricePerUnitName"]     
    pricePerVolumeName=namingParams["pricePerVolumeName"]  
    periodName=namingParams["periodName"] 
    acName=namingParams["acName"]         
    deleteArray=[pricePerUnitName,pricePerVolumeName]    
    df=duplicate_dataframe(dfCopy) 
    df = df.with_columns(pl.lit(acName).alias(periodName))
    df=drop_columns(df,deleteArray) 
    return df

def clean_up_forecast_dictionary(planDict):
    namingParams=get_naming_params()
    preparePlanParams=namingParams["preparePlanParams"] 
    notDefaultForecastName=namingParams["notDefaultForecastName"]
    dimensionKeyName=namingParams["dimensionName"]
    forecastValueKey=namingParams["forecastValue"]
    conditionKeyName=namingParams["conditionName"]
    scenarioDict={}
    dimensionDict={}
    forecastDict={}
    if notDefaultForecastName in planDict[preparePlanParams] and planDict[preparePlanParams][notDefaultForecastName]:
        scenarioDict=copy.deepcopy(planDict[preparePlanParams][notDefaultForecastName])
    if len(scenarioDict)>0:    
        for element in scenarioDict:
            if len(scenarioDict[element])>0:
                if dimensionKeyName in scenarioDict[element]:
                    if len(scenarioDict[element][dimensionKeyName])>0:
                        dimensionDict[element]=scenarioDict[element]                    
    if len(dimensionDict)>0:    
        for element in dimensionDict:
            isConditionComplete=True
            numberOfDimensions=len(dimensionDict[element][dimensionKeyName])
            if numberOfDimensions>1: 
                dimensions=dimensionDict[element][dimensionKeyName] 
                for conditionItem in dimensionDict[element][conditionKeyName]:
                    for condition in dimensionDict[element][conditionKeyName][conditionItem]:
                        if len(dimensionDict[element][conditionKeyName][conditionItem][condition])==0:
                            isConditionComplete=False
                    if isConditionComplete and conditionItem==0:
                        forecastDict[element]=copy.deepcopy(dimensionDict[element])
                    elif not isConditionComplete and conditionItem==0:
                        pass
                    elif isConditionComplete:
                        pass
                    elif not isConditionComplete: 
                        if conditionItem in forecastDict[element][conditionKeyName]: 
                            del forecastDict[element][conditionKeyName][conditionItem]   
                        if conditionItem in forecastDict[element][forecastValueKey]: 
                            del forecastDict[element][forecastValueKey][conditionItem]                            
            if numberOfDimensions==1:
                dimension=dimensionDict[element][dimensionKeyName]
                for conditionItem in dimensionDict[element][conditionKeyName]:
                    if len(dimensionDict[element][conditionKeyName][conditionItem])==0:
                        isConditionComplete=False
                    if isConditionComplete and conditionItem==0:
                        forecastDict[element]=copy.deepcopy(dimensionDict[element])
                    elif not isConditionComplete and conditionItem==0:
                        pass                     
                    elif isConditionComplete:
                        pass
                    elif not isConditionComplete: 
                        if conditionItem in forecastDict[element][conditionKeyName]: 
                            del forecastDict[element][conditionKeyName][conditionItem]   
                        if conditionItem in forecastDict[element][forecastValueKey]: 
                            del forecastDict[element][forecastValueKey][conditionItem]         
    return forecastDict

def apply_multipliers(df,forecastDict):
    namingParams=get_naming_params()
    notDefaultForecastName=namingParams["notDefaultForecastName"]
    dimensionKeyName=namingParams["dimensionName"]
    forecastValueKey=namingParams["forecastValue"]
    conditionKeyName=namingParams["conditionName"]
    metricDict={}
    for dimension in forecastDict:
        dimArray=forecastDict[dimension][dimensionKeyName]
        for conditionItem in forecastDict[dimension][conditionKeyName]:
            conArray=forecastDict[dimension][conditionKeyName][conditionItem]
            columns,schema=get_schema_and_column_names(df)
            if len(dimArray)>1:
                forecastMetricDict=forecastDict[dimension][forecastValueKey][0]
                for metric in forecastMetricDict:
                    metricCol=str(dimension)+"_"+metric
                    metricVal=forecastMetricDict[metric]  
                    if metricVal !=0:
                        metricVal=metricVal/100
                    if metric not in metricDict:
                        metricDict[metric]=[]
                    if metricCol not in metricDict[metric]:
                        metricDict[metric].append(metricCol)   
                    if metricCol not in columns:
                        df = df.with_columns(pl.lit(None).alias(metricCol))
                    if len(dimArray)==3:
                        condition = (
                            pl.col(dimArray[0]).is_in(conArray[dimArray[0]])
                            & pl.col(dimArray[1]).is_in(conArray[dimArray[1]])
                            & pl.col(dimArray[2]).is_in(conArray[dimArray[2]])
                        )
                        df = df.with_columns(
                            pl.when(condition)
                            .then(metricVal)
                            .otherwise(pl.col(metricCol))
                            .alias(metricCol)
                        )
                    if len(dimArray)==2:
                        condition = (
                            pl.col(dimArray[0]).is_in(conArray[dimArray[0]])
                            & pl.col(dimArray[1]).is_in(conArray[dimArray[1]])
                        )
                        df = df.with_columns(
                            pl.when(condition)
                            .then(metricVal)
                            .otherwise(pl.col(metricCol))
                            .alias(metricCol)
                        )
            else: 
                forecastMetricDict=forecastDict[dimension][forecastValueKey][conditionItem]
                for metric in forecastMetricDict: 
                    metricCol=str(dimension)+"_"+metric
                    metricVal=forecastMetricDict[metric]     
                    if metricVal !=0:
                        metricVal=metricVal/100   
                    if metric not in metricDict:
                        metricDict[metric]=[]                            
                    if metricCol not in metricDict[metric]:
                        metricDict[metric].append(metricCol) 
                    if metricCol not in columns:
                        df = df.with_columns(pl.lit(None).alias(metricCol))
                    condition = pl.col(dimArray[0]).is_in(conArray)
                    df = df.with_columns(
                        pl.when(condition)
                        .then(metricVal)
                        .otherwise(pl.col(metricCol))
                        .alias(metricCol)
                    )
    return df,metricDict   

def check_matching_conditions(df,forecastDict):
    namingParams=get_naming_params()
    notDefaultForecastName=namingParams["notDefaultForecastName"]
    dimensionKeyName=namingParams["dimensionName"]
    forecastValueKey=namingParams["forecastValue"]
    conditionKeyName=namingParams["conditionName"]
    hierarchical=namingParams["hierarchicalName"]
    conditionLengthArray=[3,2]
    for dimensionOne in forecastDict:
        dimOneArray=forecastDict[dimensionOne][dimensionKeyName]
        for length in conditionLengthArray:
            if len(dimOneArray)==length:
                for dimensionTwo in forecastDict:
                    if dimensionOne != dimensionTwo:
                        dimTwoArray=forecastDict[dimensionTwo][dimensionKeyName]
                        if len(dimTwoArray)<length:
                            commonElements=list(set(dimOneArray).intersection(dimTwoArray))
                            if len(commonElements)>0:
                                forecastMetricDict=forecastDict[dimensionOne][forecastValueKey][0]
                                for element in forecastMetricDict:
                                    metricOne=str(dimensionOne)+"_"+element
                                    metricTwo=str(dimensionTwo)+"_"+element
                                    condition = (~pl.col(metricOne).is_null()) & (~pl.col(metricTwo).is_null())
                                    df = df.with_columns(
                                        pl.when(condition)
                                        .then(pl.lit(None))
                                        .otherwise(pl.col(metricTwo))
                                        .alias(metricTwo)
                                    )
    return df

def check_condition_hierarchy(df,forecastDict,paramDict):
    namingParams=get_naming_params()
    notDefaultForecastName=namingParams["notDefaultForecastName"]
    dimensionKeyName=namingParams["dimensionName"]
    forecastValueKey=namingParams["forecastValue"]
    conditionKeyName=namingParams["conditionName"]
    hierarchical=namingParams["hierarchicalName"]
    conditionLengthArray=[3,2,1]
    parentArray=[]
    checkDict={}
    if len(forecastDict)>0:
        for dimensionOne in forecastDict:
            dimOneArray=forecastDict[dimensionOne][dimensionKeyName]
            for length in conditionLengthArray:
                if len(dimOneArray)==length:
                    for dimensionTwo in forecastDict:
                        if dimensionOne != dimensionTwo:
                            dimTwoArray=forecastDict[dimensionTwo][dimensionKeyName]
                            if len(dimTwoArray) == length or length==1:
                                for possibleChild in dimTwoArray:
                                    if hierarchical in paramDict:
                                        for hierarchy in paramDict[hierarchical]: 
                                            if possibleChild in paramDict[hierarchical][hierarchy]:
                                                childIndex=list(paramDict[hierarchical][hierarchy]).index(possibleChild)
                                                if childIndex>0:
                                                    for possibleFather in dimOneArray: 
                                                        if possibleFather in paramDict[hierarchical][hierarchy]: 
                                                            fatherIndex=list(paramDict[hierarchical][hierarchy]).index(possibleFather)
                                                            if fatherIndex<childIndex:
                                                                forecastMetricDict=forecastDict[dimensionOne][forecastValueKey][0]
                                                                dimOneArrayCopy=copy.deepcopy(dimOneArray)
                                                                dimTwoArrayCopy=copy.deepcopy(dimTwoArray)
                                                                dimOneArrayCopy.remove(possibleFather)
                                                                dimTwoArrayCopy.remove(possibleChild)
                                                                if set(dimOneArrayCopy) == set(dimTwoArrayCopy) or len(set(dimOneArrayCopy))< len(set(dimTwoArrayCopy)):
                                                                    if dimensionOne in checkDict and checkDict[dimensionOne]==dimensionTwo:
                                                                        pass 
                                                                    else:
                                                                        checkDict[dimensionOne]={}
                                                                        checkDict[dimensionOne]=dimensionTwo                                                             
                                                                        for element in forecastMetricDict:
                                                                            childMetric=str(dimensionTwo)+"_"+element
                                                                            fatherMetric=str(dimensionOne)+"_"+element
                                                                            condition = (~pl.col(fatherMetric).is_null()) & (~pl.col(childMetric).is_null())
                                                                            df = df.with_columns(
                                                                                pl.when(condition)
                                                                                .then(pl.lit(None))
                                                                                .otherwise(pl.col(fatherMetric))
                                                                                .alias(fatherMetric)
                                                                            )
    else:
        pass
    return df

def multiply_modifiers(df,metricDict,planDict):
    namingParams=get_naming_params()
    preparePlanParams=namingParams["preparePlanParams"] 
    allChoice=namingParams["allChoice"] 
    collisionChoiceName=namingParams["collisionChoiceName"]
    if collisionChoiceName in planDict and planDict[collisionChoiceName]==allChoice: 
        for element in metricDict:
            df = df.with_columns(pl.lit(1.0).alias(element))
            for column in metricDict[element]: 
                df = df.with_columns(pl.col(column).fill_null(1.0).alias(column))
                df = df.with_columns((pl.col(element) * pl.col(column)).alias(element))
            df=drop_columns(df,metricDict[element])          
    return df

def get_first(df,metricDict,planDict):
    namingParams=get_naming_params()
    firstChoice=namingParams["firstChoice"] 
    collisionChoiceName=namingParams["collisionChoiceName"]
    if collisionChoiceName in planDict and planDict[collisionChoiceName]==firstChoice: 
        for element in metricDict:
            df = df.with_columns(pl.lit(None).alias(element))
            for column in metricDict[element]:
                condition = (~pl.col(column).is_null()) & (pl.col(element).is_null())
                df = df.with_columns(
                    pl.when(condition)
                    .then(pl.col(column))
                    .otherwise(pl.col(element))
                    .alias(element)
                )
            df=drop_columns(df,metricDict[element])
            df = df.with_columns(pl.col(element).fill_null(1.0).alias(element))
    return df

def group_PL_dataset_by_month(df,indexColsCopy,valueColsCopy,planDict):
    namingParams=get_naming_params()
    timeProfile=namingParams["timeProfile"] 
    dateName=namingParams["dateName"]
    monthArray=[]
    group_byCols,sumCols=[],[]
    columns,schema=get_schema_and_column_names(df)
    indexCols=copy.deepcopy(indexColsCopy)
    valueCols=copy.deepcopy(valueColsCopy)
    indexCols=indexCols
    for column in indexCols:
        if column in columns:
            group_byCols.append(column) 
    for column in valueCols:
        if column in columns:
            sumCols.append(column) 
    df = df.with_columns(
        pl.col(dateName).str.strptime(pl.Date, strict=False).dt.month_end()
    )
    # Get unique month-end dates in a Polars-friendly way (works for LazyFrame/DataFrame)
    monthArray = unique_values_lazy(dateName, df)
    monthArray.sort()
    group_byCols,sumCols=check_and_clean_columns(df,group_byCols,sumCols)   
    df=df.group_by(group_byCols).agg([pl.col(c).sum() for c in sumCols])
    return df,monthArray,group_byCols,sumCols

def make_custom_month_seasonality(df,valueCols,planDict,month,columns):
    namingParams=get_naming_params()  
    timeProfileValues=namingParams["timeProfileValues"] 
    multiplier=planDict[timeProfileValues][month]
    if multiplier != 0:
        multiplier=multiplier/100
    for metric in valueCols:
        if metric in columns:
            df = df.with_columns((pl.col(metric) * pl.lit(multiplier)).alias(metric))
    return df 

def make_flat_months(dfCopy,valueCols,monthArray,planDict,expectedTotal,group_byCols,sumCols):
    namingParams=get_naming_params() 
    custom=namingParams["custom"] 
    timeProfile=namingParams["timeProfile"] 
    dateName=namingParams["dateName"]
    timeProfileValues=namingParams["timeProfileValues"]   
    frameArray=[]  
    if len(monthArray)>=12:
        columns,schema=get_schema_and_column_names(dfCopy)  
        for metric in valueCols:
            if metric in columns:
                dfCopy = dfCopy.with_columns((pl.col(metric) / 12).alias(metric))
        for month in range(0,12):
            df=duplicate_dataframe(dfCopy)
            df = df.with_columns(pl.lit(monthArray[month]).alias(dateName))
            if planDict[timeProfileValues] and planDict[timeProfile] == custom:
                pass
                df=make_custom_month_seasonality(df,valueCols,planDict,month,columns)
            frameArray.append(df)
        df = pl.concat(frameArray, how="vertical")
        return df
    else:
        return dfCopy

def make_flat_month_df(df,indexCols,valueCols,planDict,expectedTotal):
    namingParams=get_naming_params()
    timeProfile=namingParams["timeProfile"] 
    flat=namingParams["flat"] 
    custom=namingParams["custom"] 
    planOrForecast=namingParams["planOrForecast"] 
    periodName=namingParams["periodName"]  
    if timeProfile in planDict and planDict[timeProfile] in [flat,custom]:
        df,monthArray,group_byCols,sumCols=group_PL_dataset_by_month(df,indexCols,valueCols,planDict)
        df=make_flat_months(df,valueCols,monthArray,planDict,expectedTotal,group_byCols,sumCols)
    else:
        pass    
    df = df.with_columns(pl.lit(planDict[planOrForecast]).alias(periodName))
    return df

def concatenate_ac_and_pl_datasets(frameArray):
    namingParams=get_naming_params()
    netOfDiscountName=namingParams["netOfDiscountName"] 
    marginName=namingParams["marginName"] 
    netMarginName=namingParams["netMarginName"] 
    selectedPeriods=namingParams["selectedPeriods"] 
    deleteArray=[netOfDiscountName,marginName,netMarginName]
    df = pl.concat(frameArray, how="vertical")
    df=drop_columns(df,deleteArray)
    return df

def prepare_plan_dataset(dfCopy,indexColsCopy,valueColsCopy,paramDictCopy,chartDict,container,tab,planPlaybackDict):
    namingParams=get_naming_params()
    periodColFound=namingParams["periodColFound"]
    dateColFound=namingParams["dateColFound"]
    periodName=namingParams["periodName"] 
    dateName=namingParams["dateName"] 
    defaultForecast=namingParams["defaultForecastName"]
    changeInProportionToSales=namingParams["changeInProportionToSales"] 
    planPlaybackName=namingParams["planPlaybackName"] 
    indexCols=copy.deepcopy(indexColsCopy) 
    valueCols=copy.deepcopy(valueColsCopy) 
    paramDict=copy.deepcopy(paramDictCopy)
    planDict={}     
    if periodName in indexCols:
        indexCols.remove(periodName)
    columns,schema=get_schema_and_column_names(dfCopy)  
    if dateColFound in paramDict and paramDict[dateColFound]:
     if periodName in columns:
        with _context_from(container):
            colArray=make_six_col_width_array()
            df=duplicate_dataframe(dfCopy)      
            planDict=set_plan_or_forecast_widget(planDict,colArray[0],planPlaybackDict)
            planDict=set_time_profile_widget(planDict,colArray[1],planPlaybackDict) 
            planDict=get_forecast_params(df,indexCols,valueCols,planDict,paramDict,chartDict,defaultForecast,"",colArray,False,2,planPlaybackDict)  
            planDict=set_collision_choice_widget(planDict,colArray[2],planPlaybackDict) 
            if planDict[changeInProportionToSales]:
                pull_widgets_down(colArray,[0,1,2])                                                              
            df,planDict=set_dimension_forecast_widgets(df,indexCols,valueCols,1,colArray,planDict,paramDict,chartDict,planPlaybackDict)
            with _context_from(tab):
                planDict,expectedTotal,paramDict=set_month_profile_parameters(planDict,paramDict,planPlaybackDict)
                colArray=make_five_col_width_array()
                with colArray[0]:   
                    planSubmit=submit_plan_dataset(paramDict,colArray[0])
                    if planSubmit:
                        dfFiltered=filter_period_for_plan(df,chartDict)
                        dfActual=prepare_ac_dataset(dfFiltered)
                        df=add_price_column_metric(dfFiltered,valueCols)
                        forecastDict=clean_up_forecast_dictionary(planDict)
                        df,metricDict=apply_multipliers(df,forecastDict)
                        df=check_matching_conditions(df,forecastDict)
                        df=check_condition_hierarchy(df,forecastDict,paramDict)
                        df=multiply_modifiers(df,metricDict,planDict)
                        df=get_first(df,metricDict,planDict)
                        df,deleteArray,metricArray=calculate_default_PL_change(df,planDict)
                        df=calculate_price_times_volume_forecast(df,deleteArray,metricArray)
                        dfPlan=make_flat_month_df(df,indexColsCopy,valueCols,planDict,expectedTotal)
                        df=concatenate_ac_and_pl_datasets([dfPlan,dfActual])
                colArray=make_three_col_width_array()
                with colArray[0]:            
                    if planSubmit:            
                        calculate_plan_result(dfPlan,dfActual,valueCols,planDict)
                        paramDict=download_plan_file(df,colArray[0],planDict,paramDict)
                        download_json(planDict,paramDict,colArray,planPlaybackName)
    return None

def download_plan_file(df,col,planDict,paramDict):
    namingParams=get_naming_params()
    dfPlanName=namingParams["dfPlanName"]
    dfForecastName=namingParams["dfForecastName"]
    planOrForecast=namingParams["planOrForecast"]
    fcName=namingParams["fcName"]
    plName=namingParams["plName"]
    columnOrderKey=namingParams["columnOrderName"]
    hashKey,paramDict=get_image_name_hash(planDict,False,paramDict) 
    fileName=dfPlanName+"_"+hashKey
    fileType=plName
    if columnOrderKey in paramDict and paramDict[columnOrderKey]:
        columnOrder=paramDict[columnOrderKey]
        newColsArray=[]
        columns,schema=get_schema_and_column_names(df)
        for column in columnOrder:
            if column in columns:
                newColsArray.append(column)
        for column in columns:
            if column not in newColsArray:
               newColsArray.append(column)          
        # Use Polars column selection instead of pandas-style indexing
        df = df.select(newColsArray)
    if planDict[planOrForecast]==fcName:
        fileName=dfForecastName+"_"+hashKey
        fileType=fcName
    with col: 
                downloadExpander = ui.expander("➕Download  "+fileType+" dataset")
                with downloadExpander:
                    ui.caption("""To download the plan dataset hit the button below.     
                                    """) 
                    csv = convert_df(df)
                    label="Press to Download"
                    download_text_data(csv,label,fileName) 
    return paramDict


def modify_dataframe_for_Plan(dfCopy,chartDict):
    namingParams=get_naming_params()
    chosenChart=namingParams["chosenChart"]
    marimekkoChart=namingParams["marimekkoChart"]
    barmekkoChart=namingParams["barmekkoChart"]
    stackedParetoChart=namingParams["stackedParetoChart"] 
    stackedColumnChart=namingParams["stackedColumnChart"]     
    plName=namingParams["plName"]
    workColumn=namingParams["workColumn"]
    workColumnTwo=namingParams["workColumnTwo"]
    periodName=namingParams["periodName"]
    chosenChart=chartDict[chosenChart]
    dateRangeArray=namingParams["dateRangeArray"]
    compareScenariosOrPeriods=namingParams["compareScenariosOrPeriods"]
    compareScenarios=namingParams["compareScenarios"]  
    substring="<br>"+plName
    df=duplicate_dataframe(dfCopy)
    if (
        chosenChart in [stackedColumnChart]
        and compareScenariosOrPeriods in chartDict
        and chartDict[compareScenariosOrPeriods] != compareScenarios
    ):
        filtered_df = df.filter(pl.col(periodName).str.contains(plName, literal=True))
        if get_row_count(filtered_df) > 0:
            df = df.with_row_index(workColumn)
            filtered_df = df.filter(pl.col(periodName).str.contains(substring, literal=True))
            first_idx = filtered_df.select(workColumn).to_series()[0]
            df = df.with_columns(
                pl.when(pl.col(workColumn) != first_idx)
                .then(pl.col(periodName).str.replace(substring, "", literal=True))
                .otherwise(pl.col(periodName))
                .alias(workColumnTwo)
            )
    return df
