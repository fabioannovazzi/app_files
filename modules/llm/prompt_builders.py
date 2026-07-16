from modules.utilities.config import get_naming_params
from modules.utilities.helpers import simplify_chart_dictionary_keys
from modules.utilities.session_context import session_state












def add_prompt_date(string,chartDict):
    namingParams=get_naming_params()
    toPlotPeriod=namingParams["toPlotPeriod"] 
    promptPeriod=""" Data refers to the """+chartDict[toPlotPeriod]+""" period. """ 
    string=string+promptPeriod
    return string

def add_prompt_filter(chartDict):
    namingParams=get_naming_params()
    filterStringKey=namingParams["filterString"]
    promptFilter="" 
    if filterStringKey in chartDict and len(chartDict[filterStringKey])>0:
        promptFilter=""" The dataset is filtered as follows: """+chartDict[filterStringKey]+""". """ 
    return promptFilter


def get_comment_summary_prompt(commentDict, element, promptDict, context=None):
    namingParams=get_naming_params()
    industryDescriptionKey=namingParams["industryDescription"]
    companyDescriptionKey=namingParams["companyDescription"]
    industryKey=namingParams["industry"] 
    companyNameKey=namingParams["companyName"]
    atAGlance=namingParams["atAGlance"]
    salesBreakdown=namingParams["salesBreakdown"]
    dataInsights=namingParams["dataInsights"]    
    trends=namingParams["trends"]
    datasetTypeKey=namingParams["datasetTypeName"]
    companySales=namingParams["companySales"]
    scanMarketData=namingParams["scanMarketData"]
    companyExpenses=namingParams["companyExpenses"]
    indicationsKey=namingParams["indications"] 
    promptIndication,indications="",""
    if indicationsKey in promptDict:
       indications=promptDict[indicationsKey]  
    industry=False    
    sectionDict={
                atAGlance: "business at a glance",
                salesBreakdown: "sales breakdown",
                dataInsights: "sales drivers",
                trends: "sales trends over time",
                }     
    focus=sectionDict[element]    
    if len(commentDict)>0:
        comments=str(commentDict)
    else:
        comments=""  
    promptContextYes= " Take into consideration the contextual information you have about the company and the industry." 
    industry = ""
    companyDescription = ""
    industryDescription = ""
    companyName = ""
    promptCompany = ""
    promptContext = ""
    if context:
        companyName = context.get("companyName", "")
        industry = context.get("industry", "")
        companyDescription = context.get("companyDescription", "")
        industryDescription = context.get("industryDescription", "")
        if industry and len(industry)>0 and len(companyName)>0 and len(companyDescription)>0:
            promptCompany=""""""+companyName+""". """+companyName+""" operates in the """+industry+""" Industry. """+companyDescription+""""""
            promptContext=promptContextYes
        elif industry and len(industry)>0 and len(companyName)>0 and  len(industryDescription)>0:
            promptCompany=""""""+companyName+""". """+industryDescription+""""""
            promptContext=promptContextYes
    elif promptDict[datasetTypeKey] == companySales:
        promptCompany= """ a company."""
    elif promptDict[datasetTypeKey] == scanMarketData:
        promptCompany= """ in a market."""
        sectionDict={
                atAGlance: "market at a glance",
                salesBreakdown: "market breakdown",
                dataInsights: "market drivers",
                trends: "market trends over time",
                }           
    elif promptDict[datasetTypeKey] == companyExpenses:
        promptCompany= """ the purchases of a company.""" 
        sectionDict={
                atAGlance: "purchases at a glance",
                salesBreakdown: "cost breakdown",
                dataInsights: "cost drivers",
                trends: "cost trends over time",
                } 
    if indications:
        promptIndication= f"""Take into consideration the following contextual information: {indications}."""                
    promptSummary = f"""
        You are provided this dictionary:\\
        """+comments+"""\\\n
        The dictionary contains comments of charts that describe the sales of """+promptCompany+"""        
        """"""\\
        Each key is the name of a image file of a plot, and each value is the comment associated with that plot. 
        Your task is to:   
        (1) Go through each comment;  
        (2) Identify key trends;      
        (3) Extract patterns and insights across different comments;   
        (4) Weave the comments into a cohesive and meaningful narrative focused at explaining the """+focus+""";    
        (5) Based of the uncovered narrative, return a fact-based story describing the main findings and the major insights;   
        (6) Split your story into a set of segments, each based on one or more comments;  
        (7) For each segment, identify the source in the provided dictionary, as well as the corresponding key. For every segment of your story you must identify on source and one source only.    
        (8) Return a JSON in which each key is the source key, as just defined, and each value is the story segment. Do not create new keys or modify the existing ones. Every key of the returned JSON has to precisely and exactly correspond to a key of the provided dictionary.  
        Reference only the comments - and their keys - that help build your story.   
        Keep your response factual. """+promptContext+""""""+promptIndication+""" Write the response directly without introduction: do not start with something like 
        'the main finding from the provided comments is that the business has experienced X', but rather directly with 
        'the business has experienced X' . 
        Only return the final Json file, with no comments or other wording.
        """       
    return promptSummary
 

def get_section_summary(numberedDict,element):
    if len(numberedDict)>0:
        numberedDict=str(numberedDict)
    else:
        numberedDict=""     
    promptSummary = f"""
        You are provided this dictionary:\\
        """+numberedDict+"""\\
        where each key is a page number and its value is the text detailing the '"""+element.title()+"""' section of the company's sales report.   
        """"""\\
        Summarize the key points in a one page summary. The summary length should be less than five paragraphs. 
        Ensure each point in the summary includes a reference to the original page number. The reference must be in the format '(p.n)', where 'n' is the original page number
        Only return the text with no title."""
    return promptSummary

def get_executive_summary_prompt(slideDict, promptDict, chartDict, context=None):
    namingParams=get_naming_params()
    datasetTypeKey=namingParams["datasetTypeName"]
    companySales=namingParams["companySales"]
    scanMarketData=namingParams["scanMarketData"]
    companyExpenses=namingParams["companyExpenses"]
    companyDescriptionKey=namingParams["companyDescription"]
    industryDescriptionKey=namingParams["industryDescription"]
    industryKey=namingParams["industry"]
    companyNameKey=namingParams["companyName"] 
    indicationsKey=namingParams["indications"]
    promptCompany = get_prompt_company(chartDict, context)
    promptIndication,indications="",""
    if indicationsKey in promptDict:
       indications=promptDict[indicationsKey]
    if indications:
        promptIndication = f"""Take into consideration the following contextual information: {indications}."""
    companyDescription = context.get("companyDescription", "") if context else ""
    industry = context.get("industry", "") if context else ""
    if companyDescription:
        promptSummary=f"""
        You are provided this dictionary:
        """+str(slideDict)+"""
        The dictionary contains a set of analyses of the sales of """+promptCompany+""".
        """
    elif industry:
        promptSummary=f"""
        You are provided this dictionary:
        """+str(slideDict)+"""
        The dictionary contains a set of analyses of the syndicated scan data of """+promptCompany+""".

        """
    else:
        promptSummary=f"""
        You are provided this dictionary:
        """+str(slideDict)+"""
        The dictionary contains a set of analyis of the expenses of """+promptCompany+""".
        """
    promptDictionary="""
    The key of each element of the dictionary is the file name of the plot image, while the value represents the comment to the plot.
    Write a summary of the findings, illustrating the main insights. Limit the use of bullet points, and make the text interesting and well written.   
    For each paragraph of the summary find the element in the provided JSON file that references the most important information of the paragraph.
    Return a JSON file, in strict JSON format, where each key is the key of the referenced element in the provided JSON file and each element is the text of the paragraph.
    Make sure you are referencing the correct key as it is written in the dictionary. Never make keys up. Each and every key must be a key of the provided dictionary.
    Make sure that all keys and values are properly enclosed in double quotes, and that the JSON has proper commas, colons, and braces. Do not add any text or blancs outside of the JSON structure. 
    Example: {"key1 image name": "Sales grey 10%","key2 image name": "Widget sales were very strong"}.  
    """
    promptSummary=promptSummary+" "+promptDictionary+promptIndication
    promptSummary=promptSummary.replace("..",".")
    return promptSummary



def get_suggested_questions_prompt(executiveSummaryDict, commentDict, chartDict, context=None):
    namingParams=get_naming_params()
    datasetTypeKey=namingParams["datasetTypeName"]
    companySales=namingParams["companySales"]
    scanMarketData=namingParams["scanMarketData"]
    companyExpenses=namingParams["companyExpenses"]
    companyDescriptionKey=namingParams["companyDescription"]
    industryDescriptionKey=namingParams["industryDescription"]
    industryKey=namingParams["industry"]
    companyNameKey=namingParams["companyName"] 
    indicationsKey=namingParams["indications"]
    promptCompany = get_prompt_company(chartDict, context)
    companyDescription = context.get("companyDescription", "") if context else ""
    industry = context.get("industry", "") if context else ""
    if companyDescription:
        promptComments=f"""
        You are provided two dictionaries, a full dataset dictionary that contains all the analysis, and a summary dictionary, that contains the summary of the report.

        1) This is the first dictionary:     
          """+str(commentDict)+"""
          This dictionary contains a set of analyses of the sales of """+promptCompany+""".

        """
    elif industry:
        promptComments=f"""
        You are provided two dictionaries, a full dataset dictionary that contains all the analysis, and a summary dictionary, that contains the summary of the report.

        1) This is the first dictionary:   
          """+str(commentDict)+"""
          This dictionary contains a set of analyses of the syndicated scan data of """+promptCompany+""".
        
        """
    else:
        promptComments=f"""
        You are provided two dictionaries, a full dataset dictionary that contains all the analysis, and a summary dictionary, that contains the summary of the report.

        1) This is the first dictionary:  
          """+str(commentDict)+"""
          This dictionary contains a set of analyis of the expenses of """+promptCompany+""".

        """
    promptSummary="""
        
        2) This is the second dictionary:  
        """+str(executiveSummaryDict)+"""  
        This dictionary distills the main findings and strategic insights from the full dataset.

        Using the summary dictionary as a guide, formulate eight insightful analytical questions that can be directly explored using information from the full dataset. 

        Draw from the full dataset dictionary and ensure the questions are not already addressed in the summary but instead delve into aspects that could guide deeper insights. 
        
        These questions should:

        1. Encourage a deeper understanding of the data by examining specific segments, relationships, or metrics available in the dataset.
        2. Focus on uncovering insights about current performance, patterns, or contributing factors within the existing data, rather than proposing business improvements or hypothetical strategies.

        Ensure that each question is grounded in the data provided in the full dataset dictionary and can be explored based on this information.    

        Return the questions in JSON format as follows:
        {
                "1": "First question here",
                "2": "Second question here",
                "3": "Third question here",
                "4": "Fourth question here"
                "5": "Fifth question here"
        }

        Only output this JSON object, without additional text or explanation.
        """  
    promptQuestions=promptComments+" "+promptSummary
    promptQuestions=promptSummary.replace("..",".")
    return promptQuestions

def get_prompt_to_answer_question(userInput, commentDict, chartDict, col, context=None):
    namingParams=get_naming_params()
    reportSummaryKey=namingParams["reportSummary"]
    simplifiedDictKey=namingParams["simplifiedDict"]
    conversationHistoryKey=namingParams["conversationHistory"]
    notMetConditionValue=namingParams["notMetConditionValue"] 
    metConditionValue=namingParams["metConditionValue"]
    companyDescriptionKey=namingParams["companyDescription"]
    industryKey=namingParams["industry"] 
    summaryReadyKey=namingParams["summaryReady"]
    indicationsKey=namingParams["indications"]
    questionName=namingParams["question"]
    answerName=namingParams["answer"]
    promptHistory=""
    promptCompany = get_prompt_company(chartDict, context)
    if commentDict or (session_state[summaryReadyKey] and len(session_state[reportSummaryKey])>0): 
        if userInput and len(userInput)>0:
            promptIndication,indications="",False
            if indicationsKey in session_state and session_state[indicationsKey] and len(session_state[indicationsKey])>0:
                indications=session_state[indicationsKey] 
            if indications:
                promptIndication= f"""Take into consideration the following contextual information: {indications}.""" 
            company="company"
            if commentDict:
                slideDict=commentDict
            else:
                slideDict=session_state[simplifiedDictKey]
            companyDescription = context.get("companyDescription", "") if context else ""
            industry = context.get("industry", "") if context else ""
            if companyDescription:
                promptConversation=f"""
                You are provided this dictionary:
                """+str(slideDict)+"""
                The dictionary contains a set of analyses of the sales of """+promptCompany+""".
                """
            elif industry:
                company="market"
                promptConversation=f"""
                You are provided this dictionary:
                """+str(slideDict)+"""
                The dictionary contains a set of analyses of the syndicated scan data of """+promptCompany+""".
        
                """
            else:
                promptConversation=f"""
                You are provided this dictionary:  
                """+str(slideDict)+"""  
                The dictionary contains a set of analyis of the expenses of """+promptCompany+""".                      
                """
            promptDictionary="""
            The key of each element of the dictionary is the file name of the plot image, while the value represents the comment to the plot.
            Answer the following question """+userInput+""" leveraging on the provided dictionary and on your knowledge of the """+company+""" . 
            Limit the use of bullet points, and make the text interesting and well written. 
            For each paragraph of the summary find the element in the provided JSON file that references the most important information of the paragraph.
            Return a JSON file, in strict JSON format, where each key is the key of the referenced element in the provided JSON file and each element is the text of the paragraph.
            Do not reference the name of the dictionary key your text: do not include references such as "as seen in key 2" or "(key 2)". 
            Make sure you are referencing the correct key as it is written in the dictionary. Never make keys up. Each and every key must be a key of the provided dictionary.
            Make sure that all keys and values are properly enclosed in double quotes, and that the JSON has proper commas, colons, and braces.  Do not add any text or blancs outside of the JSON structure. 
            Example: {"1": "Sales grew 10%","2": "Widget sales were very strong", "3": "Margins also grew significantly"}.
            """
            if conversationHistoryKey in session_state and len(session_state[conversationHistoryKey])>0:
                last_exchange = session_state[conversationHistoryKey][-1]
                simplifiedAnswer,keyMappingDict=simplify_chart_dictionary_keys(last_exchange[answerName])
                promptHistory=f"""
                Use the information from the previous answer to inform your answer.  
                
                Previous Conversation Context:
                
                Question: {last_exchange[questionName]}
                Answer: {simplifiedAnswer}   

                Important: Do not repeat information from the previous answer. Instead, provide new, complementary insights or drill down into additional details not covered in the previous response.                 
                """
            promptConversation=promptConversation+" "+promptDictionary+" "+promptIndication+" "+promptHistory

            promptQuestion=promptConversation.replace("..",".")
            return promptQuestion
        else:
            return None,None
    else:
        return None,None

def get_prompt_system_for_chart_data():
    promptSystem="""
    You are ChartMaster, an AI assistant powered by a top line model.
    - ChartMaster is fine-tuned specifically to assist with requests involving the analysis of sales data.
    - Sales data have been validated to be within your capabilities to answer about.
    - ChartMaster always analyzes to the best of its abilities, never reporting failure nor denying an attempt at data analysis.
    - ChartMaster skills include data formatting, textual or table presentation, and business analysis and insights.
    """.strip()
    return promptSystem

def get_prompt_system_for_chart_image():
    promptSystem="""
    You are ImageMaster, an AI assistant powered by a top line model with computer vision.
    - ImageMaster is fine-tuned specifically to assist with requests involving image analysis based on the content of an image. Images may include charts, plots, graphics, presentations…
    - Image inputs have been validated to be within your capabilities to answer about.
    - ImageMaster always analyzes to the best of its abilities, never reporting failure nor denying an attempt at image recognition.
    - ImageMaster skills include image text extraction, data formatting, textual or table presentation, and business analysis and insights.
    """ 
    promptSystem.strip()
    return promptSystem


def get_prompt_company(promptDict, context=None):
    namingParams=get_naming_params()
    companyNameKey=namingParams["companyName"]
    industryKey=namingParams["industry"]
    datasetTypeKey=namingParams["datasetTypeName"]
    industryDescriptionKey=namingParams["industryDescription"]
    companyDescriptionKey=namingParams["companyDescription"]
    companySales=namingParams["companySales"]
    scanMarketData=namingParams["scanMarketData"]
    companyExpenses=namingParams["companyExpenses"]
    industry = ""
    companyDescription = ""
    industryDescription = ""
    companyName = ""
    promptCompany = ""
    if context:
        companyName = context.get("companyName", "")
        industry = context.get("industry", "")
        companyDescription = context.get("companyDescription", "")
        industryDescription = context.get("industryDescription", "")
    if companyName and len(companyName)>0 and industry and len(industry)>0 and len(companyDescription)>0: 
        promptCompany=""""""+companyName+""". """+companyName+""" operates in the """+industry+""" Industry. """+companyDescription+""""""
    elif len(companyDescription)>0: 
        promptCompany=""""""+companyDescription+""""""
    elif industry and len(industry)>0 and len(industryDescription)>0: 
        promptCompany="""the """+industry+""" market. """+industryDescription+""""""
    elif len(promptDict)>0:
        if datasetTypeKey in promptDict and promptDict[datasetTypeKey] == companySales:
            promptCompany= """ a company."""
        elif datasetTypeKey in promptDict and promptDict[datasetTypeKey] == scanMarketData:
            promptCompany= """ in a market."""          
        elif datasetTypeKey in promptDict and promptDict[datasetTypeKey] == companyExpenses:
            promptCompany= """ the purchases of a company.""" 
    return promptCompany
