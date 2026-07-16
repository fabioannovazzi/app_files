import logging
import copy
import hashlib
from typing import Any, MutableMapping

from modules.utilities.ui_notifier import ui
from modules.utilities.session_context import (
    SessionContext,
    get_session_state,
    session_state,
)

from modules.layout.session_manager import SessionManager
from modules.llm.llm_api import remove_duplicate_charts_in_dictionary
from modules.utilities.config import (
    get_file_params,
    get_naming_params,
)
from modules.utilities.error_messages import (
    add_info_message_in_plot_charts_tab,
    add_warning_message_in_plot_charts_tab,
)
from modules.utilities.helpers import (
    clean_chartDict,
    get_automate_dict,
    get_image_name_hash,
    simplify_chart_dictionary_keys,
)
from modules.utilities.utils import (
    get_schema_and_column_names,
    is_valid_lazyframe,
)


def get_session_state_query_content(
    promptSystem,
    session_context: SessionContext | MutableMapping[str, Any] | None = None,
):
    state = get_session_state(session_context)
    namingParams = get_naming_params()
    promptUserKey = namingParams["promptUser"]
    notMetConditionValue = namingParams["notMetConditionValue"]
    sessionValue = notMetConditionValue
    if promptUserKey in state:
        sessionValue = state[promptUserKey]
    return sessionValue


def hashFor(data):
    # Prepare the project id hash
    hashId = hashlib.md5()
    hashId.update(repr(data).encode("utf-8"))
    return hashId.hexdigest()


def get_column_hash(df, paramDict):
    namingParams = get_naming_params()
    notMetConditionValue = namingParams["notMetConditionValue"]
    columnHash = namingParams["columnHash"]
    columns, schema = get_schema_and_column_names(df)
    if len(columns) > 0 and is_valid_lazyframe(df):
        paramDict[columnHash] = hashFor(columns)
    else:
        paramDict[columnHash] = notMetConditionValue
    return paramDict


def initialize_session_state_for_conversation(
    session_manager: SessionManager | None = None,
):
    session_manager = session_manager or SessionManager()
    namingParams = get_naming_params()
    summaryReadyKey = namingParams["summaryReady"]
    reportSummaryKey = namingParams["reportSummary"]
    chartDescriptionsKey = namingParams["chartDescriptions"]
    conversationHistoryKey = namingParams["conversationHistory"]
    notMetConditionValue = namingParams["notMetConditionValue"]
    metConditionValue = namingParams["metConditionValue"]
    questionsAndInputsKey = namingParams["questionsAndInputs"]
    if summaryReadyKey not in session_manager._state:
        session_manager.set(summaryReadyKey, notMetConditionValue)
        session_manager.set(reportSummaryKey, notMetConditionValue)
        session_manager.set(chartDescriptionsKey, notMetConditionValue)
    if conversationHistoryKey not in session_manager._state:
        session_manager.set(conversationHistoryKey, [])
    if questionsAndInputsKey not in session_manager._state:
        session_manager.set(questionsAndInputsKey, [])
    return None


def reset_session_state_for_conversation(session_manager: SessionManager | None = None):
    session_manager = session_manager or SessionManager()
    namingParams = get_naming_params()
    summaryReadyKey = namingParams["summaryReady"]
    reportSummaryKey = namingParams["reportSummary"]
    chartDescriptionsKey = namingParams["chartDescriptions"]
    simplifiedDictKey = namingParams["simplifiedDict"]
    keyMappingDictKey = namingParams["keyMappingDict"]
    startConversationSubmittedKey = namingParams["startConversationSubmitted"]
    conversationHistoryKey = namingParams["conversationHistory"]
    companyDescriptionKey = namingParams["companyDescription"]
    industryDescriptionKey = namingParams["industryDescription"]
    questionsAndInputsKey = namingParams["questionsAndInputs"]
    industryKey = namingParams["industry"]
    companyNameKey = namingParams["companyName"]
    groundingArray = [
        industryKey,
        companyNameKey,
        industryDescriptionKey,
        companyDescriptionKey,
    ]
    keysToDelete = [
        summaryReadyKey,
        reportSummaryKey,
        chartDescriptionsKey,
        conversationHistoryKey,
        simplifiedDictKey,
        keyMappingDictKey,
        startConversationSubmittedKey,
        questionsAndInputsKey,
    ]
    keysToDelete = keysToDelete + groundingArray
    keysDeleted = False
    for key in keysToDelete:
        if key in session_manager._state:
            session_manager.delete(key)
            keysDeleted = True
    return None


def cleanup_session_folder(extract_folder):
    """
    Delete the folder for the current session.
    """
    if extract_folder.exists():
        shutil.rmtree(extract_folder, ignore_errors=True)


def initialize_session_folder():
    """
    Initialize a unique folder for the session to store extracted files.
    """
    fileParams = get_file_params()
    extractFileFolderName = fileParams["extractFileFolderName"]
    if "session_id" not in session_state:
        session_state["session_id"] = str(uuid.uuid4())

    session_id = session_state["session_id"]
    extract_folder = Path(extractFileFolderName + "/" + session_id)
    extract_folder.mkdir(parents=True, exist_ok=True)

    # Register cleanup function to delete the folder when the session ends
    atexit.register(cleanup_session_folder, extract_folder)

    return extract_folder


def extract_automate_dict(paramDict, playbackDict, colArray):
    namingParams = get_naming_params()
    runNumber = namingParams["runNumberName"]
    totalRunsKey = namingParams["totalNberOfRunsName"]
    runsDict = namingParams["runsDict"]
    hashkeyArray = namingParams["hashkeyArrayName"]
    downloadedDictHashkey = namingParams["downloadedDictHashkey"]
    errorMessageType = namingParams["errorMessageType"]
    plotChartsTabKey = namingParams["plotChartsTab"]
    colNumber = 0
    automateDict = {}
    nberOfRuns = len(playbackDict)
    try:
        if nberOfRuns > 0:
            if runNumber not in session_state:
                session_state[runNumber] = 1
            if totalRunsKey not in session_state:
                session_state[totalRunsKey] = nberOfRuns
            if runsDict not in session_state:
                session_state[runsDict] = playbackDict
            if hashkeyArray not in session_state:
                session_state[hashkeyArray] = []
                for element in playbackDict:
                    hashkey, _ = get_image_name_hash(playbackDict[element], False, {})
                    session_state[hashkeyArray].append(hashkey)
            if downloadedDictHashkey not in session_state:
                hashkey, _ = get_image_name_hash(playbackDict, False, {})
                session_state[downloadedDictHashkey] = hashkey
            key = session_state[runNumber]
            automateDict = get_automate_dict(playbackDict, key)
    except Exception as e:
        logging.exception(e)
        errorMessage = (
            "Unable to process plot playback json file. Playback file will be ignored"
        )
        paramDict = add_app_message_to_paramdict(
            e,
            errorMessageType,
            plotChartsTabKey,
            paramDict,
            isMessage=True,
            isToast=False,
            colNumber=colNumber,
        )
        paramDict = add_app_message_to_paramdict(
            errorMessage,
            errorMessageType,
            plotChartsTabKey,
            paramDict,
            isMessage=True,
            isToast=True,
            colNumber=colNumber,
        )
        ui.error("Something went wrong.")
        automateDict = {}
        if session_state[runNumber] in session_state:
            session_state.pop([runNumber])
        if session_state[runsDict] in session_state:
            session_state.pop(runsDict)
        if hashkeyArray in session_state:
            session_state.pop(hashkeyArray)
        if totalRunsKey in session_state:
            session_state.pop(totalRunsKey)
    showDictionary = False
    if showDictionary and len(automateDict) > 0:
        ui.caption("Selected plot:")
        ui.json(automateDict, expanded=True)
    else:
        pass
    return automateDict, paramDict


def update_report_in_session_state(chartDict, colArray, paramDict):
    namingParams = get_naming_params()
    runNumber = namingParams["runNumberName"]
    runsDict = namingParams["runsDict"]
    recordRunKey = namingParams["recordRunName"]
    addNewRunKey = namingParams["addNewRunName"]
    deleteRunKey = namingParams["deleteRunName"]
    totalRunsKey = namingParams["totalNberOfRunsName"]
    hashkeyArray = namingParams["hashkeyArrayName"]
    nextRunKey = namingParams["nextRunName"]
    previousRunKey = namingParams["previousRunName"]
    downloadedDictHashkey = namingParams["downloadedDictHashkey"]
    updateCurrentRunKey = namingParams["updateCurrentRunName"]
    loadDataTabLabel = namingParams["loadDataTabLabel"]
    infoIcon = namingParams["infoIcon"]
    currentPlotNumber = 0
    toPopArray = [
        runsDict,
        hashkeyArray,
        totalRunsKey,
        runNumber,
    ]
    playbackDict = {}
    numberOfPlots = 0
    message = ""
    if chartDict and len(chartDict) > 0:
        cleanDict = clean_chartDict(chartDict, False, False, False)
        hashkey, paramDict = get_image_name_hash(cleanDict, False, paramDict)
        if recordRunKey in chartDict and chartDict[recordRunKey]:
            if runNumber not in session_state:
                session_state[runNumber] = 1
                session_state[runsDict] = {}
                session_state[runsDict][session_state[runNumber]] = cleanDict
                session_state[hashkeyArray] = []
                session_state[hashkeyArray].append(hashkey)
                message = (
                    "Run # "
                    + str(session_state[runNumber])
                    + " added to playback file. To download the playback file click the button below."
                )
            elif (
                session_state[runNumber] not in session_state[runsDict]
                or session_state[runsDict][session_state[runNumber]] != cleanDict
            ):
                if hashkey not in session_state[hashkeyArray]:
                    session_state[hashkeyArray].append(hashkey)
                    session_state[runNumber] += 1
                    session_state[runsDict][session_state[runNumber]] = cleanDict
                    message = (
                        "Run # "
                        + str(session_state[runNumber])
                        + " added to playback file. To download the playback file click the button below."
                    )
                else:
                    message = (
                        "Run already in playback file. Playback file contains "
                        + str(session_state[runNumber])
                        + " plots. To download the playback file click the button below."
                    )
            else:
                message = (
                    "Run already recorded. Playback file contains "
                    + str(session_state[runNumber])
                    + " plots. To download the playback file click the button below."
                )
        elif addNewRunKey in chartDict and chartDict[addNewRunKey]:
            if runNumber not in session_state:
                session_state[runNumber] = 1
                session_state[runsDict] = {}
                session_state[runsDict][session_state[runNumber]] = cleanDict
                session_state[hashkeyArray] = []
                session_state[hashkeyArray].append(hashkey)
                message = (
                    "Run # "
                    + str(session_state[runNumber])
                    + " added to playback file. To download the playback file click the button below."
                )
            elif (
                session_state[runNumber] not in session_state[runsDict]
                or session_state[runsDict][session_state[runNumber]] != cleanDict
            ):
                if hashkey not in session_state[hashkeyArray]:
                    session_state[hashkeyArray].append(hashkey)
                    chartList = []
                    chartDict = {}
                    chartIndex = 1
                    for plotNber in session_state[runsDict]:
                        chartLiui.append(session_state[runsDict][plotNber])
                    chartLiui.insert(session_state[runNumber] - 1, cleanDict)
                    for element in chartList:
                        chartDict[chartIndex] = element
                        chartIndex = chartIndex + 1
                    session_state[runsDict] = chartDict
                    message = (
                        "Run # "
                        + str(session_state[runNumber])
                        + " added to playback file. To download the playback file click the button below."
                    )
                else:
                    message = (
                        "Run already in playback file. Playback file contains "
                        + str(session_state[runNumber])
                        + " plots. To download the playback file click the button below."
                    )
            else:
                message = (
                    "Run already recorded. Playback file contains "
                    + str(session_state[runNumber])
                    + " plots. To download the playback file click the button below."
                )
        elif deleteRunKey in chartDict and chartDict[deleteRunKey]:
            if runNumber not in session_state:
                pass
            elif (
                session_state[runNumber] not in session_state[runsDict]
                or session_state[runsDict][session_state[runNumber]] != cleanDict
            ):
                if hashkey not in session_state[hashkeyArray]:
                    session_state[hashkeyArray].append(hashkey)
                    chartList = []
                    chartDict = {}
                    chartIndex = 1
                    for plotNber in session_state[runsDict]:
                        chartLiui.append(session_state[runsDict][plotNber])
                    del chartList[session_state[runNumber] - 1]
                    for element in chartList:
                        chartDict[chartIndex] = element
                        chartIndex = chartIndex + 1
                    session_state[runsDict] = chartDict
                    message = (
                        "Run # "
                        + str(session_state[runNumber])
                        + " deleted from playback file. To download the playback file click the button below."
                    )
                else:
                    message = (
                        "Run already in playback file. Playback file contains "
                        + str(session_state[runNumber])
                        + " plots. To download the playback file click the button below."
                    )
            else:
                message = (
                    "Run already recorded. Playback file contains "
                    + str(session_state[runNumber])
                    + " plots. To download the playback file click the button below."
                )
        elif totalRunsKey in session_state and runNumber in session_state:
            numberOfPlots = len(session_state[runsDict])
            currentPlotNumber = session_state[runNumber]
            if (
                nextRunKey in chartDict
                and chartDict[nextRunKey]
                and not chartDict[updateCurrentRunKey]
            ):
                session_state[runNumber] += 1
            elif (
                previousRunKey in chartDict
                and chartDict[previousRunKey]
                and not chartDict[updateCurrentRunKey]
            ):
                session_state[runNumber] -= 1
            message = (
                "Playback json file contains "
                + str(numberOfPlots)
                + " plots. Plot #**"
                + str(currentPlotNumber)
                + "** loaded."
            )
            if updateCurrentRunKey in chartDict and chartDict[updateCurrentRunKey]:
                session_state[hashkeyArray].append(hashkey)
                message = (
                    "Playback json file contains "
                    + str(numberOfPlots)
                    + " plots. Plot #**"
                    + str(currentPlotNumber)
                    + "** updated with current parameters."
                )
                if session_state[runNumber] in session_state[runsDict]:
                    session_state[runsDict].pop(session_state[runNumber])
                if str(session_state[runNumber]) in session_state[runsDict]:
                    session_state[runsDict].pop(str(currentPlotNumber))
                session_state[runsDict][session_state[runNumber]] = cleanDict
        else:
            pass
    else:
        message = ""
        for element in toPopArray:
            if element in session_state:
                session_state.pop(element)
    if len(message) > 0:
        message = infoIcon + message
        ui.info(message)
    if runsDict in session_state and len(session_state[runsDict]) > 0:
        if downloadedDictHashkey in session_state:
            hashkey, paramDict = get_image_name_hash(
                session_state[runsDict], False, paramDict
            )
            if session_state[downloadedDictHashkey] == hashkey:
                pass
            else:
                playbackDict = session_state[runsDict]
        else:
            playbackDict = session_state[runsDict]
    return playbackDict, paramDict


def load_summary_in_session_state(
    executiveSummaryDict,
    descriptionsDict,
    submitted,
    session_manager: SessionManager | None = None,
):
    session_manager = session_manager or SessionManager()
    namingParams = get_naming_params()
    summaryReadyKey = namingParams["summaryReady"]
    reportSummaryKey = namingParams["reportSummary"]
    chartDescriptionsKey = namingParams["chartDescriptions"]
    simplifiedDictKey = namingParams["simplifiedDict"]
    keyMappingDictKey = namingParams["keyMappingDict"]
    notMetConditionValue = namingParams["notMetConditionValue"]
    metConditionValue = namingParams["metConditionValue"]
    if submitted and not session_manager.get(summaryReadyKey):
        session_manager.set(summaryReadyKey, metConditionValue)
        session_manager.set(reportSummaryKey, executiveSummaryDict)
        session_manager.set(chartDescriptionsKey, descriptionsDict)
        if simplifiedDictKey not in session_manager._state or not session_manager.get(
            simplifiedDictKey
        ):
            simplifiedDict, keyMappingDict = simplify_chart_dictionary_keys(
                descriptionsDict
            )
            session_manager.set(simplifiedDictKey, simplifiedDict)
            session_manager.set(keyMappingDictKey, keyMappingDict)
    return None


def restore_keys(
    simpleDict,
    keyMappingDict,
    session_context: SessionContext | MutableMapping[str, Any] | None = None,
):
    state = get_session_state(session_context)
    namingParams = get_naming_params()
    keyMappingDictKey = namingParams["keyMappingDict"]
    if keyMappingDictKey in state:
        keyMappingDict = state[keyMappingDictKey]
    else:
        pass
    restoredDict = {}
    # Iterate through each item in simpleDict
    for simpleKey in simpleDict:
        # Look up the original key in keyMappingDict
        originalKey = keyMappingDict[simpleKey]
        # Retrieve the value from simpleDict
        value = simpleDict[simpleKey]
        # Assign it to restoredDict using the original key
        restoredDict[originalKey] = value
    return restoredDict


def check_response_keys_in_dict(
    responseDict, session_manager: SessionManager | None = None
):
    session_manager = session_manager or SessionManager()
    namingParams = get_naming_params()
    simplifiedDictKey = namingParams["simplifiedDict"]
    isError = False
    if simplifiedDictKey in session_manager._state and session_manager.get(
        simplifiedDictKey
    ):
        simplifiedDict = session_manager.get(simplifiedDictKey)
        if isinstance(responseDict, dict):
            for element in responseDict:
                if element not in simplifiedDict:
                    isError = True
                    break
            return isError
        return isError
    else:
        return isError


def load_selected_plots_in_session_state_following_times(
    responseDict, session_manager: SessionManager | None = None
):
    """Merge newly selected plots with any already stored in session."""
    session_manager = session_manager or SessionManager()
    namingParams = get_naming_params()
    alreadychosen = namingParams["alreadychosen"]

    if isinstance(responseDict, list) and len(responseDict) == 1:
        extractedDict = responseDict[0]
    elif isinstance(responseDict, list) and len(responseDict) > 1:
        extractedDict = {str(i + 1): val for i, val in enumerate(responseDict)}
    else:
        extractedDict = copy.deepcopy(responseDict)

    mergedDict = {}
    count = 1
    for element in extractedDict:
        mergedDict[str(count)] = extractedDict[element]
        count += 1

    for element in session_manager.get(alreadychosen, {}):
        mergedDict[str(count)] = session_manager.get(alreadychosen)[element]
        count += 1

    mergedDict = remove_duplicate_charts_in_dictionary(mergedDict)
    session_manager.set(alreadychosen, mergedDict)
    return None


def load_selected_plots_in_session_state_first_time(
    responseDict, promptSystem, session_manager: SessionManager | None = None
):
    """Initialize selected plots the first time charts are chosen."""
    session_manager = session_manager or SessionManager()
    namingParams = get_naming_params()
    promptUserKey = namingParams["promptUser"]
    promptSystemKey = namingParams["promptSystem"]
    firstQuery = namingParams["firstQuery"]
    alreadychosen = namingParams["alreadychosen"]

    session_manager.set(promptUserKey, firstQuery)
    session_manager.set(promptSystemKey, promptSystem)

    if isinstance(responseDict, list) and len(responseDict) == 1:
        extractedDict = responseDict[0]
    elif isinstance(responseDict, list) and len(responseDict) > 1:
        extractedDict = {str(i + 1): val for i, val in enumerate(responseDict)}
    else:
        extractedDict = responseDict

    session_manager.set(alreadychosen, extractedDict)
    return None


def update_chartdict_state(hashkey, chartDictHashName, chartDictNotChangedName):
    if chartDictHashName not in session_state:
        session_state[chartDictHashName] = hashkey
        session_state[chartDictNotChangedName] = True
    elif session_state[chartDictHashName] == hashkey:
        session_state[chartDictNotChangedName] = True
    else:
        session_state[chartDictHashName] = hashkey
        session_state[chartDictNotChangedName] = False
    return None


def check_if_chartdict_changed(chartDict, paramDict):
    namingParams = get_naming_params()
    chartDictHashName = namingParams["chartDictHashName"]
    chartDictNotChangedName = namingParams["chartDictNotChangedName"]
    hashDict = clean_chartDict(chartDict, True, False, None)
    hashkey, paramDict = get_image_name_hash(hashDict, False, paramDict)
    update_chartdict_state(hashkey, chartDictHashName, chartDictNotChangedName)
    return None
