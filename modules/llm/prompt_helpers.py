import logging
from modules.utilities.ui_notifier import ui
from modules.utilities.session_context import session_state
import polars as pl
import datetime as dt
import json
import re
import copy
import unicodedata
from contextlib import nullcontext

from modules.charting.chart_primitives import change_metric_if_cost_analysis
from modules.data.common_data_utils import add_bold
from modules.utilities.config import (
    get_config_params,
    get_metric_array_params,
    get_naming_params,
)
from modules.utilities.helpers import (
    add_status_message_to_paramDict,
    drop_columns,
    duplicate_dataframe,
    get_period_length,
)
from modules.utilities.utils import (
    get_schema_and_column_names,
    is_valid_lazyframe,
)












def clean_df_for_prompt(dfCopy,chartDict):
    namingParams=get_naming_params()
    configParams=get_config_params()
    paretoChartManyItems=configParams["paretoChartManyItems"]
    countColumnKey=namingParams["countColumn"]
    metricsToPlotKey=namingParams["metricsToPlot"]
    countRank=namingParams["countRank"] 
    colorName=namingParams["colorName"]
    df = duplicate_dataframe(dfCopy)
    if isinstance(df, pl.LazyFrame):
        df = df.collect()
    df = df.sort(countRank)
    df = df.head(30000)
    downloadBigDataset=True
    if downloadBigDataset or df.height <= paretoChartManyItems:
        columns,schema=get_schema_and_column_names(df) 
        countColumn=chartDict[countColumnKey]
        metricsToPlot=chartDict[metricsToPlotKey]
        toKeep=[countColumn,countRank]+metricsToPlot
        toDrop=[]
        for column in columns:
            if colorName  in column:
                toDrop.append(column)
        df = drop_columns(df, toDrop)
        df = df.sort(countRank)
    else:
        df = pl.DataFrame([])
    return df


def replace_currency_symbols(text):
    # Step 1: Replace currency symbols to prevent LaTeX interpretation in UI
    text = text.replace('$', 'USD')
    text = text.replace('€', 'EUR')
    text = text.replace('£', 'GBP')
    text = text.replace('¥', 'JPY')
    text = text.replace('₹', 'INR')
    text = text.replace('₩', 'KRW')
    text = text.replace('₽', 'RUB')
    text = text.replace('฿', 'THB')
    text = text.replace('₫', 'VND')
    text = text.replace('₦', 'NGN')
    return text

def extract_industry_and_company_from_dict(executiveSummaryDict):
    namingParams=get_naming_params()
    companyDescriptionKey=namingParams["companyDescription"]
    industryDescriptionKey=namingParams["industryDescription"]
    industryKey=namingParams["industry"]
    companyNameKey=namingParams["companyName"]
    chosenLanguageKey=namingParams["chosenLanguage"] 
    indicationsKey=namingParams["indications"]  
    questionsKey=namingParams["questions"] 
    answersKey=namingParams["answers"]
    cleanedDict={}
    if executiveSummaryDict != None and len(executiveSummaryDict)>0:
        for element in executiveSummaryDict:
            if element == industryKey:
                session_state[industryKey]=executiveSummaryDict[element]
            elif element == industryDescriptionKey:
                session_state[industryDescriptionKey]=executiveSummaryDict[element]
            elif element == companyNameKey:
                session_state[companyNameKey]=executiveSummaryDict[element]
            elif element == companyDescriptionKey:
                session_state[companyDescriptionKey]=executiveSummaryDict[element]
            elif element == chosenLanguageKey:
                session_state[chosenLanguageKey]=executiveSummaryDict[element]
            elif element == indicationsKey:
                session_state[indicationsKey]=executiveSummaryDict[element]
            elif element == questionsKey:
                executiveSummaryDict[element]=clean_llm_dictionary(executiveSummaryDict[element])
                session_state[questionsKey]=executiveSummaryDict[element]
            elif element == answersKey:
                executiveSummaryDict[element]=clean_llm_dictionary(executiveSummaryDict[element])
                session_state[answersKey]=executiveSummaryDict[element]
            else:
                executiveSummaryDict[element]=clean_llm_dictionary(executiveSummaryDict[element])
                cleanedDict[element]=executiveSummaryDict[element]
    return cleanedDict

def clean_llm_text(text: str) -> str:
    """Clean LLM output text while preserving useful special characters.
    
    Args:
        text (str): Input text to clean.
    Returns:
        str: Cleaned text.
    """
    if not isinstance(text, str):
        return text
    
    try:
        text=replace_currency_symbols(text)
        #text = text.encode('latin1').decode('utf-8')
        #text = text.encode().decode('unicode_escape')
        # Step 1: Normalize Unicode to standard characters
        text = text.encode('utf-8', errors='replace').decode('utf-8')
        
        text = unicodedata.normalize("NFC", text)        

        # Step 1: Replace currency symbols to prevent LaTeX interpretation in UI
        #was here
        
        # Step 2: Encode to UTF-8 and ignore errors to remove invalid characters
        text = text.encode('utf-8', 'ignore').decode('utf-8')
        
        # Step 3: Normalize whitespace
        text = ' '.join(text.split())

        text = text.replace('\\', '')
        text = text.replace('\\\\', '')
        
        return text.strip()
        
    except Exception as e:
        logging.exception(e)
        ui.error("Something went wrong in clean_llm_text")
        return text

def clean_llm_dictionary(llm_response):
    """
    Clean all text values in the LLM response dictionary
    """
    if isinstance(llm_response, dict):
        return {k: clean_llm_dictionary(v) for k, v in llm_response.items()}
    elif isinstance(llm_response, list):
        return [clean_llm_dictionary(item) for item in llm_response]
    elif isinstance(llm_response, str):
        return clean_llm_text(llm_response)
    else:
        return llm_response

def check_comments_if_cost_analysys(oldDict,chartDict):
    namingParams=get_naming_params()
    greenToRed=namingParams["greenToRed"]
    colorChoice=namingParams["colorChoice"]
    newDict={}
    if colorChoice in chartDict and chartDict[colorChoice]==greenToRed:
        for element in oldDict:
            newDict[element]=oldDict[element].replace("sales","costs").replace("Sales","Costs").replace("revenues","costs").replace("Revenues","Costs").replace("revenue","costs").replace("Revenue","Costs")
        return newDict
    else:
        return oldDict

def synchronize_keys(original_dict, llm_output_dict, col=None):
    """
    Synchronize the keys in llm_output_dict with those in original_dict based on unique codes.
    Parameters:
    - original_dict (dict): The original dictionary with correct keys.
    - llm_output_dict (dict): The dictionary returned by the LLM with potentially modified keys.
    Returns:
    - dict: A new dictionary with keys synchronized to those in original_dict.
    """
    # Step 1: Create a mapping from unique codes to original keys
    context_manager = col if col is not None else nullcontext()
    with context_manager:
        unique_code_to_original_key = {}
        for key in original_dict.keys():
            # Extract the unique code (string after the last '__')
            parts = key.rsplit('__', 1)
            if len(parts) == 2:
                unique_code = parts[1]
                unique_code_to_original_key[unique_code] = key
            else:
                ui.warning(f"Warning: Key '{key}' does not contain '__'. Skipping.")
                continue  # Skip keys that don't match the expected format
        # Step 2: Initialize a new dictionary to store synchronized data
        synchronized_dict = {}
        # Step 3: Iterate over the LLM's output dictionary
        for llm_key, value in llm_output_dict.items():
            if llm_key in original_dict:
                # The key exists in the original dictionary; add it as is
                synchronized_dict[llm_key] = value
            else:
                # Key doesn't exist; extract the unique code
                parts = llm_key.rsplit('__', 1)
                if len(parts) == 2:
                    # LLM key contains '__'; extract unique code
                    unique_code = parts[1]
                else:
                    # LLM key does not contain '__'; it might be a unique code
                    unique_code = llm_key
                # Check if the unique code exists in the original dictionary
                if unique_code in unique_code_to_original_key:
                    # Replace the LLM's key with the original key
                    original_key = unique_code_to_original_key[unique_code]
                    synchronized_dict[original_key] = value
                else:
                    ui.warning(f"Warning: Unique code '{unique_code}' not found in original dictionary.")
                    ui.json(llm_output_dict)
                    # Optionally, include the key as is or skip it
                    # synchronized_dict[llm_key] = value
    return synchronized_dict


def classify_charts_for_story():
    namingParams=get_naming_params()
    atAGlance=namingParams["atAGlance"]
    salesBreakdown=namingParams["salesBreakdown"]
    dataInsights=namingParams["dataInsights"]      
    trends=namingParams["trends"]        
    areaChart=namingParams["areaChart"] 
    areaBarChart=namingParams["areaBarChart"] 
    barmekkoChart=namingParams["barmekkoChart"]
    bubbleChart=namingParams["bubbleChart"]
    boxplotChart=namingParams["boxplotChart"]
    dotChart=namingParams["dotChart"]   
    histogramChart=namingParams["histogramChart"] 
    kernelDensity=namingParams["kernelDensityChart"]  
    ecdfChart=namingParams["ecdfChart"]
    horizontalWaterfallChart=namingParams["horizontalWaterfallChart"]       
    marimekkoChart=namingParams["marimekkoChart"]
    multitierBarChart=namingParams["multitierBarChart"] 
    multitierColumnChart=namingParams["multitierColumnChart"]
    paretoChart=namingParams["paretoChart"] 
    scatterChart=namingParams["scatterChart"]
    slopeChart=namingParams["slopeChart"]    
    stackedBarChart=namingParams["stackedBarChart"]    
    stackedColumnChart=namingParams["stackedColumnChart"] 
    stackedParetoChart=namingParams["stackedParetoChart"]
    stripplotChart=namingParams["stripplotChart"]  
    summaryStackedColumnChart=namingParams["summaryStackedColumnChart"]
    timelineChart=namingParams["timelineChart"]
    trendComparisonChart=namingParams["trendComparisonChart"]    
    trendComparisonByPeriodChart=namingParams["trendComparisonByPeriodChart"]  
    upsetChart=namingParams["upsetChart"]
    vennChart=namingParams["vennChart"]
    verticalWaterfallChart=namingParams["verticalWaterfallChart"]
    storyDict={
                areaChart:trends,
                areaBarChart:salesBreakdown,
                barmekkoChart:salesBreakdown,
                bubbleChart:dataInsights,
                boxplotChart:dataInsights,
                dotChart:trends,
                histogramChart:dataInsights,
                kernelDensity:dataInsights,
                ecdfChart:dataInsights,
                horizontalWaterfallChart:trends,       
                marimekkoChart:salesBreakdown,
                multitierBarChart:atAGlance,
                multitierColumnChart:trends,
                paretoChart:dataInsights,
                scatterChart:dataInsights,
                slopeChart:trends,  
                stackedBarChart:salesBreakdown,    
                stackedColumnChart:trends,
                stackedParetoChart:dataInsights,
                stripplotChart:dataInsights,
                summaryStackedColumnChart:atAGlance,
                timelineChart:trends,
                trendComparisonChart:trends,
                trendComparisonByPeriodChart:trends, 
                upsetChart:dataInsights,
                vennChart:dataInsights,
                verticalWaterfallChart:atAGlance,
                    }
    underscoreDict={}
    for element in storyDict:
        newElement=element.replace(" ","_")
        underscoreDict[newElement]=storyDict[element]   
    return underscoreDict

def classify_comment_dictionary(commentDict):
    namingParams=get_naming_params()
    atAGlance=namingParams["atAGlance"]
    salesBreakdown=namingParams["salesBreakdown"]
    dataInsights=namingParams["dataInsights"]
    trends=namingParams["trends"]   
    classifierDict=classify_charts_for_story()
    newDict={}
    storyDict={
            atAGlance:{},
            salesBreakdown:{},
            dataInsights:{},            
            trends:{},            
    }
    for element in commentDict:
        cleanedElement=element.replace(" ","_")
        key=cleanedElement.split("__")
        key=key[0]
        story=classifierDict[key]
        if element in commentDict:
            storyDict[story][cleanedElement]=commentDict[element]              
    return storyDict


def handle_date_messages(df, paramDict, chartDict):
    namingParams=get_naming_params()
    compareWithYearBeforeKey=namingParams["compareWithYearBefore"] 
    periodToDateKey=namingParams["periodToDate"] 
    dateName=namingParams["dateName"]
    dateColFoundKey=namingParams["dateColFound"]  
    columns,schema=get_schema_and_column_names(df)     
    # Retrieve period info if needed
    if compareWithYearBeforeKey in chartDict and chartDict[compareWithYearBeforeKey]:
        paramDict = handle_compare_year_before(df, paramDict, chartDict)
    elif periodToDateKey in chartDict and chartDict[periodToDateKey]:
        paramDict = handle_period_to_date(df, paramDict)
    else:
        # If date exists in columns
        if dateName in columns or (dateColFoundKey in paramDict and paramDict[dateColFoundKey]):
            paramDict = handle_general_dates(df, paramDict)
    return paramDict

def handle_compare_year_before(df, paramDict, chartDict):
    namingParams=get_naming_params()
    tyYaDatesKey=namingParams["tyYaDates"]
    mostRecentPeriodKey=namingParams["mostRecentPeriod"]  
    mostRecentDatePromptMessageKey=namingParams["mostRecentDatePromptMessage"]
    leastRecentDatePromptMessageKey=namingParams["leastRecentDatePromptMessage"]    
    paramDict, mostRecentDate, leastRecentDate, periodLengthInMonths = get_period_length(df, paramDict, False)
    tyYaDates=paramDict[tyYaDatesKey]
    mostRecentPeriodIndex = chartDict[mostRecentPeriodKey]
    if mostRecentPeriodIndex and len(tyYaDates) >= abs(mostRecentPeriodIndex):
        mr_date = tyYaDates[mostRecentPeriodIndex]
        statusMessage = f"Most recent date: **{str(mr_date)}**. "
        paramDict = add_status_message_to_paramDict(paramDict, statusMessage, 2)
        paramDict[mostRecentDatePromptMessageKey] = statusMessage
    paramDict = write_least_and_most_recent_dates(paramDict, mostRecentDate, leastRecentDate)
    return paramDict

def handle_period_to_date(df, paramDict):
    paramDict, mostRecentDate, leastRecentDate, periodLengthInMonths = get_period_length(df, paramDict, False)
    paramDict = write_least_and_most_recent_dates(paramDict, mostRecentDate, leastRecentDate)
    return paramDict

def handle_general_dates(df, paramDict, mostRecentDatePromptMessage, leastRecentDatePromptMessage):
    paramDict, mostRecentDate, leastRecentDate, periodLengthInMonths = get_period_length(df, paramDict, False)
    paramDict = write_least_and_most_recent_dates(paramDict, mostRecentDate, leastRecentDate)
    return paramDict

def write_least_and_most_recent_dates(paramDict, mostRecentDate, leastRecentDate):
    namingParams=get_naming_params()
    mostRecentDatePromptMessageKey=namingParams["mostRecentDatePromptMessage"]
    leastRecentDatePromptMessageKey=namingParams["leastRecentDatePromptMessage"] 
    if mostRecentDate:
        mr_date = str(mostRecentDate.date())
        statusMessage = f"Most recent date: **{mr_date}**. "
        paramDict = add_status_message_to_paramDict(paramDict, statusMessage, 2)
        paramDict[mostRecentDatePromptMessageKey] = statusMessage

    if leastRecentDate:
        lr_date = str(leastRecentDate.date())
        statusMessage = f"Oldest date: **{lr_date}**. "
        paramDict = add_status_message_to_paramDict(paramDict, statusMessage, 2)
        paramDict[leastRecentDatePromptMessageKey] = statusMessage
    return paramDict

def transform_str_dictionary_to_dict(originalDict):
    originalDict=originalDict.strip()
    originalDict = re.sub(r'\s{2,}', ' ', originalDict)
    originalDict=originalDict.replace("{","").replace("}","")
    originalDict=originalDict.replace('","','", "')
    dataArray=originalDict.split('", "')
    newDict={}
    for element in dataArray:        
        element=element.replace("```json\n", "").replace("```", "")
        element=element.strip()
        element=element.split('": "')
        if len(element)>1:
            element[0]=element[0].replace('"','')
            element[1]=element[1].replace('"','')                    
            newDict[element[0]]=element[1]
        else:
            ui.error("problem with "+element+" missing second part")            
    originalDict=copy.deepcopy(newDict)
    return originalDict

def find_min_max_page_numbers(numberedDict):
    if len(numberedDict)>0:
        numberList=list(numberedDict)
        minPage=numberList[0]
        if int(minPage)>1:
            minPage=int(minPage)-1
        maxPage=numberList[-1]
        pageRange=""" (p."""+str(minPage)+""" to """+str(maxPage)+""")."""
    else:
        pageRange="""(p.x)"""            
    return pageRange

def translate_first_and_last_period_symbols(firstPeriod,secondPeriod):
    namingParams=get_naming_params()
    acName=namingParams["acName"] 
    plName=namingParams["plName"] 
    pyName=namingParams["pyName"] 
    fcName=namingParams["fcName"]
    if acName in firstPeriod:           
        firstPeriod=firstPeriod.replace(acName,"**Actual** (AC) ")
    if pyName in firstPeriod:           
        firstPeriod=firstPeriod.replace(pyName,"**Previous Year** (PY) ")        
    if plName in firstPeriod:           
        firstPeriod=firstPeriod.replace(plName,"**Plan** (PL) ")
    if fcName in firstPeriod:           
        firstPeriod=firstPeriod.replace(fcName,"**Forecast** (FC) ")   
    if acName in secondPeriod:           
        secondPeriod=secondPeriod.replace(acName,"**Actual** (AC) ")
    if pyName in secondPeriod:           
        secondPeriod=secondPeriod.replace(pyName,"**Previous Year** (PY) ")        
    if plName in secondPeriod:           
        secondPeriod=secondPeriod.replace(plName,"**Plan** (PL) ")
    if fcName in secondPeriod:           
        secondPeriod=secondPeriod.replace(fcName,"**Forecast** (FC) ")
    return firstPeriod,secondPeriod

def traslate_ibcs_period_symbols(chartDict):
    namingParams=get_naming_params()
    selectedPeriods=namingParams["selectedPeriods"]
    acName=namingParams["acName"] 
    plName=namingParams["plName"] 
    pyName=namingParams["pyName"] 
    fcName=namingParams["fcName"]
    firstPeriod,secondPeriod="",""
    if selectedPeriods in chartDict:
        firstPeriod=str(chartDict[selectedPeriods][0])   
        if acName in firstPeriod:           
            firstPeriod=firstPeriod.replace(acName,"**Actual** (AC) ")
        if pyName in firstPeriod:           
            firstPeriod=firstPeriod.replace(pyName,"**Previous Year** (PY) ")        
        if plName in firstPeriod:           
            firstPeriod=firstPeriod.replace(plName,"**Plan** (PL) ")
        if fcName in firstPeriod:           
            firstPeriod=firstPeriod.replace(fcName,"**Forecast** (FC) ")   
        if len(chartDict[selectedPeriods])>1:
            secondPeriod=str(chartDict[selectedPeriods][1])
            if acName in secondPeriod:           
                secondPeriod=secondPeriod.replace(acName,"**Actual** (AC) ")
            if pyName in secondPeriod:           
                secondPeriod=secondPeriod.replace(pyName,"**Previous Year** (PY) ")        
            if plName in secondPeriod:           
                secondPeriod=secondPeriod.replace(plName,"**Plan** (PL) ")
            if fcName in secondPeriod:           
                secondPeriod=secondPeriod.replace(fcName,"**Forecast** (FC) ")
    return firstPeriod,secondPeriod

def add_backup_slides_to_dict(responseDict,commentDict):
    namingParams=get_naming_params()
    backupName=namingParams["backupName"]
    newDict={}
    if isinstance(responseDict, str):
        responseDict=responseDict.replace("}","")
        responseDict=responseDict.replace("{","")
        lines = responseDict.strip().split('\n')
        # Convert each line into a key-value pair in a dictionary
        data_dict = {}
        for line in lines:
            line=line.strip()
            try:
                if len(line)>0 and ':' in line:
                    if ': ' in line:
                        # Splitting each line at the colon
                        key, value = line.split(': ', 1)
                    else:
                        key, value = line.split(':', 1)
                    # Removing quotation marks and extra whitespace
                    key = key.strip('" ')
                    value = value.strip('" ')
                    value=value.replace('",',"")
                    # Adding the key-value pair to the dictionary
                    newDict[key] = value
            except Exception as e:
                logging.exception(e)
                ui.error("Something went wrong in add_backup_slides_to_dict.")
        # Displaying the resulting dictionary
        responseDict=newDict
    indexText=make_index_text(backupName)    
    if len(commentDict)>0:
        responseDict[backupName]=indexText
        for element in commentDict:
            if element not in responseDict:
                responseDict[element]=commentDict[element]                                      
    return responseDict

def make_index_text(chapterName):
    namingParams=get_naming_params()
    sectionSummaryName=namingParams["sectionSummaryName"]
    executiveSummaryName=namingParams["executiveSummaryName"]
    atAGlance=namingParams["atAGlance"]
    salesBreakdown=namingParams["salesBreakdown"]
    dataInsights=namingParams["dataInsights"]    
    trends=namingParams["trends"]
    backup=namingParams["backupName"]
    chapterArray=[executiveSummaryName,sectionSummaryName,atAGlance,salesBreakdown,dataInsights,trends,backup]     
    indexText=""
    for element in chapterArray:
        if element==chapterName:
            element=element.capitalize()
            element=add_bold(element)
        else: 
            element=element.capitalize()  
        indexText=indexText+element+"\n"
    return indexText        
                   
def make_numbered_dict(response,count):
    numberedDict={}
    for element in response:
        numberedDict[str(count)]=response[element]
        count=count+1
    count=count+2
    return numberedDict,count

def add_title_page(response,chartDict):
    namingParams=get_naming_params()
    titleName=namingParams["titleName"]
    companyNameKey=namingParams["companyName"] 
    selectedPeriods=namingParams["selectedPeriods"]
    datasetTypeKey=namingParams["datasetTypeName"]
    companySales=namingParams["companySales"]
    scanMarketData=namingParams["scanMarketData"]
    companyExpenses=namingParams["companyExpenses"] 
    periods=chartDict[selectedPeriods][0]+" vs "+chartDict[selectedPeriods][1]
    companyName=chartDict[companyNameKey]
    currentDate = dt.datetime.today().strftime('%d %B %Y')
    title="""Sales Report"""
    if chartDict[datasetTypeKey]==companyExpenses:
        title="""Cost Analysis"""
    elif chartDict[datasetTypeKey]==scanMarketData:
        title="""Market Analysis"""
    entityAndPeriod="""**"""+companyName+""", """+periods+"""**"""
    dateInfo="Prepared: """+currentDate+""""""
    titleText=""""""+title+"""\n"""+entityAndPeriod+"""\n"""+dateInfo+""""""           
    newDict = {titleName:titleText,
            }
    newDict.update(response)
    return newDict   


def add_ibcs_explanation(response):
    namingParams=get_naming_params()
    ibcsGuide=namingParams["ibcsGuide"]

    ibcsText="""This report uses charts designed according to the **International Business Communication Standards** (IBCS) to ensure clarity, consistency, and information density.\n
    
Key elements:\n

1. **Consistent chart design**: All charts follow a uniform design, making it easier for readers to understand and compare data across different visualizations. This includes consistent use of fonts, sizes, and positioning of elements.\n
    
2. **Simplified and focused content**: Charts are designed to be easily readable, with a focus on essential information. Unnecessary decorative elements are avoided to maintain clarity.\n

3. **Proper labeling and titling**: Each chart includes clear, descriptive titles and labels to ensure that the data is easily understood without additional context.\n

4. **Standardized notation**: IBCS-compliant charts use standardized notation for elements such as time periods, units, and scenarios, making the information more accessible and comparable.\n

The following conventions are used throughout the report:\n\n

- **Black** represents actual values for the current year
- **Grey** represents data from the previous year
- **Red** indicates negative or "bad" performance
- **Green** indicates positive or "good" performance
- **"PY"** is used to denote the previous year values
- **"AC"** refers to the actual current year values
- **Underscore "_"** is used to represent year-to-date data
- **Tilde "~"** indicates a rolling year or 12-month period

    """       
    newDict = {ibcsGuide:ibcsText,
            }
    newDict.update(response)
    return newDict

def add_section_summary_at_top_of_dictionary(response,element,summary,pageRange,summaryDict,indexText,summaryDictSections):
    namingParams=get_naming_params()
    summaryName=namingParams["summaryName"] 
    newName=summaryName+"_"+element
    newDict = {element:indexText,
               newName:summary,
            }
    newDict.update(response)
    summaryDict[pageRange]=summary
    summaryDictSections[element]=summary
    return newDict,summaryDict,summaryDictSections

def add_other_summaries_at_top_of_dictionary(response,element,summary,indexText):
    namingParams=get_naming_params()
    summaryName=namingParams["summaryName"] 
    newName=summaryName+"_"+element
    newDict = {element:indexText,
               newName:summary,
            }
    newDict.update(response)
    return newDict 

def extract_chart_items_from_dict(responseDict):
    namingParams=get_naming_params()
    executiveSummaryName=namingParams["executiveSummaryName"]
    sectionSummaryName=namingParams["sectionSummaryName"]
    summaryName=namingParams["summaryName"]
    atAGlance=namingParams["atAGlance"]
    salesBreakdown=namingParams["salesBreakdown"]
    dataInsights=namingParams["dataInsights"]
    backupName=namingParams["backupName"]
    trends=namingParams["trends"]
    titleName=namingParams["titleName"]
    ibcsGuide=namingParams["ibcsGuide"]
    chapterNameArray=[sectionSummaryName,summaryName,atAGlance,salesBreakdown,dataInsights,trends]
    slideDict={}
    if responseDict != None and len(responseDict)>0:    
        for element in responseDict:             
            if element == backupName:
                break
            else:
                isChapterName=False
                for chapterName in chapterNameArray:
                    if element in [titleName,ibcsGuide]:
                        isChapterName=True
                        break
                    elif summaryName+"_"+executiveSummaryName in element:
                        isChapterName=True
                        break 
                    elif chapterName in element:
                        isChapterName=True
                if not isChapterName:
                    slideDict[element]=responseDict[element] 
    return slideDict

def add_industry_and_company_to_dict(summaryDict,suggestedQuestionDict,answerDict):
    namingParams=get_naming_params()
    companyDescriptionKey=namingParams["companyDescription"]
    industryDescriptionKey=namingParams["industryDescription"]
    industryKey=namingParams["industry"]
    chosenLanguageKey=namingParams["chosenLanguage"] 
    indicationsKey=namingParams["indications"]
    questionsKey=namingParams["questions"]  
    answersKey=namingParams["answers"]  
    newDict={}
    if summaryDict != None and len(summaryDict)>0:    
        if industryKey in session_state:    
            newDict[industryKey]=session_state[industryKey]
        if companyDescriptionKey in session_state and session_state[companyDescriptionKey]:    
            newDict[companyDescriptionKey]=session_state[companyDescriptionKey]
        elif industryDescriptionKey in session_state and session_state[industryDescriptionKey]:    
            newDict[industryDescriptionKey]=session_state[industryDescriptionKey]
        if indicationsKey in session_state and session_state[indicationsKey]:    
            newDict[indicationsKey]=session_state[indicationsKey] 
        if chosenLanguageKey in session_state and session_state[chosenLanguageKey]:    
            newDict[chosenLanguageKey]=session_state[chosenLanguageKey] 
        newDict[questionsKey]=suggestedQuestionDict    
        newDict[answersKey]=answerDict   
        for element in summaryDict:
            newDict[element]=summaryDict[element]
    return newDict

def get_context(chartDict,metric):
    namingParams=get_naming_params()
    metricArrayParams=get_metric_array_params()
    percentMetricsArray=metricArrayParams[namingParams["percentMetricsArray"]]
    growthMetricArray=metricArrayParams[namingParams["growthMetricArray"]]
    valueMetricsArray=metricArrayParams[namingParams["valueMetricsArray"]] 
    priceMetricsArray=metricArrayParams[namingParams["priceMetricsArray"]] 
    companySales=namingParams["companySales"]
    scanMarketData=namingParams["scanMarketData"]
    companyExpenses=namingParams["companyExpenses"] 
    industryKey=namingParams["industry"]
    companyNameKey=namingParams["companyName"]
    likeForLikeKey=namingParams["likeForLikeName"]
    chosenCohortColumn=namingParams["chosenCohortColumn"]
    datasetTypeKey=namingParams["datasetTypeName"]
    monetaryName=namingParams["monetaryLocalCurrencyName"]
    costsName=namingParams["costsName"]
    varianceAggregationOptionsArray=namingParams["varianceAggregationOptionsArray"]
    promptContext=""
    inPercentTag=""
    industry=False
    companyOrIndustry=False
    if not metric:
        metric ="data"
    elif metric in growthMetricArray or metric in percentMetricsArray:
        inPercentTag=" in percent "
    elif likeForLikeKey in chartDict and chartDict[likeForLikeKey]:
        metric =metric+"** on a **like-for-like "+chartDict[chosenCohortColumn]+" basis"
    elif varianceAggregationOptionsArray in chartDict and len(chartDict[varianceAggregationOptionsArray])>1:
        metric=metric+" variance"
    metric=change_metric_if_cost_analysis(metric,chartDict)        
    if datasetTypeKey in chartDict and chartDict[datasetTypeKey] in [scanMarketData]:
        if industryKey in session_state and session_state[industryKey]:
            industry=session_state[industryKey]
        elif companyNameKey in chartDict and chartDict[companyNameKey]:
            industry=chartDict[companyNameKey]
        if industry and len(industry)>0:    
            promptContext=""" The dataset shows **"""+metric+"""** """+inPercentTag+""" for the **"""+industry+"""** sector"""
        companyOrIndustry="sector" 
    elif datasetTypeKey in chartDict and chartDict[datasetTypeKey] in [companySales,companyExpenses]:    
        if companyNameKey in chartDict and chartDict[companyNameKey]:
            industry=chartDict[companyNameKey]   
        if industry and len(industry)>0:    
            promptContext=""" The dataset shows **"""+metric+"""** """+inPercentTag+""" for the **"""+industry+"""** company""" 
        companyOrIndustry="company"  
    return promptContext,companyOrIndustry,metric

def explain_currency_and_abbreviations(df,chartDict,promptContext,metric):
    namingParams=get_naming_params()
    metricArrayParams=get_metric_array_params()
    percentMetricsArray=metricArrayParams[namingParams["percentMetricsArray"]]
    growthMetricArray=metricArrayParams[namingParams["growthMetricArray"]]
    valueMetricsArray=metricArrayParams[namingParams["valueMetricsArray"]] 
    priceMetricsArray=metricArrayParams[namingParams["priceMetricsArray"]] 
    fullCurrencyNameKey=namingParams["fullCurrencyName"]
    valuePrefixNameKey=namingParams["valuePrefixName"]
    nothingFilteredName=namingParams["nothingFilteredName"] 
    plotTitleText=namingParams["plotTitleText"] 
    currencyChoice=namingParams["currencyChoice"]
    valuePrefixDict=namingParams["valuePrefixDict"] 
    metricTextKey=namingParams["metricText"]
    valuePrefixDictKey=namingParams["valuePrefixDict"] 
    chosenChart=namingParams["chosenChart"]
    bubbleChart=namingParams["bubbleChart"]
    scatterChart=namingParams["scatterChart"]
    stackedBarChart=namingParams["stackedBarChart"]
    varianceAnalysisChart=namingParams["varianceAnalysisChart"]
    stackedColumnChart=namingParams["stackedColumnChart"]
    marimekkoChart=namingParams["marimekkoChart"]
    multitierBarChart=namingParams["multitierBarChart"]
    plotValuesAsChoice=namingParams["plotValuesAsChoice"]
    multitierBarChart=namingParams["multitierBarChart"]
    synthesisPlot=namingParams["synthesisPlot"]
    absolute=namingParams["absolute"]
    columnTotalKey=namingParams["columnTotal"]
    valueName=namingParams["valueName"]
    percentName=namingParams["percentName"]
    bubbleSizeKey=namingParams["bubbleSize"]
    yAxisMetricKey=namingParams["yAxisMetric"]
    xAxisMetricKey=namingParams["xAxisMetric"]
    datasetTypeKey=namingParams["datasetTypeName"]
    companyExpenses=namingParams["companyExpenses"] 
    monetaryName=namingParams["monetaryLocalCurrencyName"]
    costsName=namingParams["costsName"]   
    abbreviationDict={
                    "":"number",
                    "k":"thousand",
                    "m":"million",
                    "b":"billion",
                    "t":"trillion",
                    }
    divideDict = {'t':1000000000000,'b':1000000000,'m':1000000,'k':1000,'':1}
    dividerRounding=3 
    divideChartArray=[stackedColumnChart,multitierBarChart,marimekkoChart,stackedBarChart]                 
    fullValueName=""
    fullCurrencyName=""
    explainer=""
    isCurrency=False
    if currencyChoice in chartDict and chartDict[currencyChoice] not in [nothingFilteredName]:
        if plotTitleText in chartDict and chartDict[currencyChoice] in chartDict[plotTitleText]:
            isCurrency=True 
    if chosenChart in chartDict and chartDict[chosenChart] in [stackedColumnChart]:
        df = df.fill_null(0)
    elif chosenChart in chartDict and chartDict[chosenChart] in [stackedBarChart]:
        df = df.with_columns(pl.all().replace("", 0).fill_null(0))
    if metricTextKey in chartDict and chartDict[metricTextKey]:
        metricText=change_metric_if_cost_analysis(chartDict[metricTextKey],chartDict)        
        explainer=". "+metricText
        if is_valid_lazyframe(df):
            columns,schema=get_schema_and_column_names(df)
            for column in columns:
                if valuePrefixDict in chartDict and chartDict[valuePrefixDict]:
                    if column in chartDict[valuePrefixDict]:
                        abbreviation=chartDict[valuePrefixDict][column]
                        divider=divideDict[abbreviation]
                        df = df.with_columns(
                            pl.when((pl.col(column).cast(pl.Float64, strict=False) > 0) |
                                    (pl.col(column).cast(pl.Float64, strict=False) < 0))
                            .then(pl.col(column).cast(pl.Float64, strict=False) / divider)
                            .otherwise(pl.col(column).cast(pl.Float64, strict=False))
                            .fill_null(1e-18)
                            .round(dividerRounding)
                            .alias(column)
                        )
                        #df[column]=df[column].fillna("  ")
                    elif column.title() in chartDict[valuePrefixDict]:
                        abbreviation=chartDict[valuePrefixDict][column.title()]
                        divider=divideDict[abbreviation]
                        df = df.with_columns(
                            (pl.col(column).cast(pl.Float64, strict=False) / divider).alias(column)
                        )
    else:
        if valuePrefixNameKey in chartDict and chartDict[valuePrefixNameKey] in ["","k","m","b","t"] and "in percent" not in promptContext:
            fullValueName=abbreviationDict[chartDict[valuePrefixNameKey]]
            dividerValueName=divideDict[chartDict[valuePrefixNameKey]]
            if is_valid_lazyframe(df):
                columns,schema=get_schema_and_column_names(df)
                if synthesisPlot in chartDict and chartDict[synthesisPlot] and plotValuesAsChoice in chartDict and chartDict[plotValuesAsChoice] not in [absolute]:
                    if columnTotalKey in chartDict and chartDict[columnTotalKey] and valueName in columns and percentName in columns:
                        df = df.with_columns(
                            (chartDict[columnTotalKey] * pl.col(percentName) / 100)
                            .round(1)
                            .alias(valueName)
                        )
                elif (varianceAnalysisChart in chartDict and chartDict[varianceAnalysisChart])  or (chosenChart in chartDict and chartDict[chosenChart] in divideChartArray ):
                    if chosenChart in chartDict and chartDict[chosenChart] in [stackedColumnChart]:
                        df = df.with_columns(pl.all().replace("", 0).fill_null(0))
                    for column in columns:
                        dt = df[column].dtype
                        if dt.is_numeric() and "%" not in column and "percent" not in column and "Percent" not in column and column not in percentMetricsArray+growthMetricArray:
                            df = df.with_columns(
                                (pl.col(column) / dividerValueName).alias(column)
                            )
        if isCurrency and fullCurrencyNameKey in chartDict and chartDict[fullCurrencyNameKey] not in [nothingFilteredName]:
            fullCurrencyName=chartDict[fullCurrencyNameKey]
        if chosenChart in chartDict and chartDict[chosenChart] in [bubbleChart]:
            if chartDict[bubbleSizeKey] in valueMetricsArray+priceMetricsArray or  chartDict[yAxisMetricKey] in valueMetricsArray+priceMetricsArray or  chartDict[xAxisMetricKey] in valueMetricsArray+priceMetricsArray: 
                fullCurrencyName=chartDict[fullCurrencyNameKey]
                explainer=". All monetary values are in **"+fullCurrencyName+"s**."
            else:
                explainer="." 
        elif chosenChart in chartDict and chartDict[chosenChart] in [scatterChart]:
            if chartDict[yAxisMetricKey] in valueMetricsArray+priceMetricsArray or  chartDict[xAxisMetricKey] in valueMetricsArray+priceMetricsArray:         
                fullCurrencyName=chartDict[fullCurrencyNameKey]
                explainer=". All monetary values are in **"+fullCurrencyName+"s**."   
            else:
                explainer="."                          
        elif isCurrency and len(fullValueName)>0 and len(fullCurrencyName)>0:
            explainer=". All values are in **"+fullValueName+"s** of **"+fullCurrencyName+"s**."
        elif len(fullCurrencyName)>0:
            explainer=". All values are in **"+fullCurrencyName+"s**."
        elif len(fullValueName)>0:
            explainer=". All values are in **"+fullValueName+"s**."
        elif metric in percentMetricsArray+growthMetricArray:
            explainer=". All values are in **percent**."
        else:
            explainer="." 
    promptContext=promptContext+explainer
    return promptContext,df
