from modules.utilities.config import get_naming_params


def add_app_message_to_paramdict(
    message, messageType, tabName, paramDict, isMessage, isToast, colNumber
):
    namingParams = get_naming_params()
    appMessageArrayKey = namingParams["appMessageArray"]
    appMessageContent = namingParams["appMessageContent"]
    appMessageType = namingParams["appMessageType"]
    showAppMessageAsToastKey = namingParams["showAppMessageAsToast"]
    showAppMessageAsStatusKey = namingParams["showAppMessageAsStatus"]
    appMessageTabKey = namingParams["appMessageTab"]
    appMessageColumnKey = namingParams["appMessageColumn"]
    errorMessageType = namingParams["errorMessageType"]
    warningMessageType = namingParams["warningMessageType"]
    infoMessageType = namingParams["infoMessageType"]
    successMessageType = namingParams["successMessageType"]
    writeMessageType = namingParams["writeMessageType"]
    textMessageType = namingParams["textMessageType"]
    captionMessageType = namingParams["captionMessageType"]
    appMessageIconType = namingParams["appMessageIconType"]
    errorIcon = namingParams["errorIcon"]
    warningIcon = namingParams["warningIcon"]
    infoIcon = namingParams["infoIcon"]
    successIcon = namingParams["successIcon"]
    loadDataTabKey = namingParams["loadDataTab"]
    planDataTabKey = namingParams["planDataTab"]
    setTimePeriodTabKey = namingParams["setTimePeriodTab"]
    filterDataTabKey = namingParams["filterDataTab"]
    setVarianceOptionsTabKey = namingParams["setVarianceOptionsTab"]
    messageArray = [
        infoMessageType,
        warningMessageType,
        errorMessageType,
        writeMessageType,
        textMessageType,
        captionMessageType,
    ]
    iconDict = {
        successMessageType: successIcon,
        infoMessageType: infoIcon,
        warningMessageType: warningIcon,
        errorMessageType: errorIcon,
        writeMessageType: None,
        textMessageType: None,
        captionMessageType: None,
    }
    if appMessageArrayKey not in paramDict:
        paramDict[appMessageArrayKey] = []
    newAppMessageDict = {
        appMessageContent: message,
        appMessageType: messageType,
        showAppMessageAsStatusKey: isMessage,
        showAppMessageAsToastKey: isToast,
        appMessageIconType: iconDict[messageType],
        appMessageTabKey: tabName,
        appMessageColumnKey: colNumber,
    }
    if newAppMessageDict not in paramDict[appMessageArrayKey]:
        paramDict[appMessageArrayKey].append(newAppMessageDict)
    return paramDict


def add_error_message_in_conversation_tab(paramDict, message):
    namingParams = get_naming_params()
    errorMessageType = namingParams["errorMessageType"]
    conversationTabKey = namingParams["conversationTab"]
    colNumber = 0
    paramDict = add_app_message_to_paramdict(
        message,
        errorMessageType,
        conversationTabKey,
        paramDict,
        isMessage=True,
        isToast=True,
        colNumber=colNumber,
    )
    return paramDict


def add_warning_message_in_conversation_tab(paramDict, message):
    namingParams = get_naming_params()
    warningMessageType = namingParams["warningMessageType"]
    conversationTabKey = namingParams["conversationTab"]
    colNumber = 0
    paramDict = add_app_message_to_paramdict(
        message,
        warningMessageType,
        conversationTabKey,
        paramDict,
        isMessage=True,
        isToast=True,
        colNumber=colNumber,
    )
    return paramDict


def add_info_message_in_conversation_tab(paramDict, message):
    namingParams = get_naming_params()
    infoMessageType = namingParams["infoMessageType"]
    conversationTabKey = namingParams["conversationTab"]
    colNumber = 0
    paramDict = add_app_message_to_paramdict(
        message,
        infoMessageType,
        conversationTabKey,
        paramDict,
        isMessage=True,
        isToast=True,
        colNumber=colNumber,
    )
    return paramDict


def add_error_message_in_load_data_tab(paramDict, message):
    namingParams = get_naming_params()
    errorMessageType = namingParams["errorMessageType"]
    loadDataTabKey = namingParams["loadDataTab"]
    colNumber = 0
    paramDict = add_app_message_to_paramdict(
        message,
        errorMessageType,
        loadDataTabKey,
        paramDict,
        isMessage=True,
        isToast=True,
        colNumber=colNumber,
    )
    return paramDict


def add_warning_message_in_load_data_tab(paramDict, message):
    namingParams = get_naming_params()
    warningMessageType = namingParams["warningMessageType"]
    loadDataTabKey = namingParams["loadDataTab"]
    colNumber = 0
    paramDict = add_app_message_to_paramdict(
        message,
        warningMessageType,
        loadDataTabKey,
        paramDict,
        isMessage=True,
        isToast=True,
        colNumber=colNumber,
    )
    return paramDict


def add_info_message_in_load_data_tab(paramDict, message):
    namingParams = get_naming_params()
    infoMessageType = namingParams["infoMessageType"]
    loadDataTabKey = namingParams["loadDataTab"]
    colNumber = 0
    paramDict = add_app_message_to_paramdict(
        message,
        infoMessageType,
        loadDataTabKey,
        paramDict,
        isMessage=True,
        isToast=True,
        colNumber=colNumber,
    )
    return paramDict


def add_success_message_in_load_data_tab(paramDict, message):
    namingParams = get_naming_params()
    successMessageType = namingParams["successMessageType"]
    loadDataTabKey = namingParams["loadDataTab"]
    colNumber = 0
    paramDict = add_app_message_to_paramdict(
        message,
        successMessageType,
        loadDataTabKey,
        paramDict,
        isMessage=True,
        isToast=True,
        colNumber=colNumber,
    )
    return paramDict


def add_error_message_in_enrich_data_tab(paramDict, message):
    namingParams = get_naming_params()
    errorMessageType = namingParams["errorMessageType"]
    enrichDataTabKey = namingParams["enrichDataTab"]
    colNumber = 0
    paramDict = add_app_message_to_paramdict(
        message,
        errorMessageType,
        enrichDataTabKey,
        paramDict,
        isMessage=True,
        isToast=True,
        colNumber=colNumber,
    )
    return paramDict


def add_warning_message_in_enrich_data_tab(paramDict, message):
    namingParams = get_naming_params()
    warningMessageType = namingParams["warningMessageType"]
    enrichDataTabKey = namingParams["enrichDataTab"]
    colNumber = 0
    paramDict = add_app_message_to_paramdict(
        message,
        warningMessageType,
        enrichDataTabKey,
        paramDict,
        isMessage=True,
        isToast=True,
        colNumber=colNumber,
    )
    return paramDict


def add_info_message_in_enrich_data_tab(paramDict, message):
    namingParams = get_naming_params()
    infoMessageType = namingParams["infoMessageType"]
    enrichDataTabKey = namingParams["enrichDataTab"]
    colNumber = 0
    paramDict = add_app_message_to_paramdict(
        message,
        infoMessageType,
        enrichDataTabKey,
        paramDict,
        isMessage=True,
        isToast=True,
        colNumber=colNumber,
    )
    return paramDict


def add_success_message_in_enrich_data_tab(paramDict, message):
    namingParams = get_naming_params()
    successMessageType = namingParams["successMessageType"]
    enrichDataTabKey = namingParams["enrichDataTab"]
    colNumber = 0
    paramDict = add_app_message_to_paramdict(
        message,
        successMessageType,
        enrichDataTabKey,
        paramDict,
        isMessage=True,
        isToast=True,
        colNumber=colNumber,
    )
    return paramDict


def add_info_message_in_ask_gpt_tab(paramDict, message):
    namingParams = get_naming_params()
    infoMessageType = namingParams["infoMessageType"]
    askGPTTabKey = namingParams["openAITab"]
    colNumber = 0
    paramDict = add_app_message_to_paramdict(
        message,
        infoMessageType,
        askGPTTabKey,
        paramDict,
        isMessage=True,
        isToast=True,
        colNumber=colNumber,
    )
    return paramDict


def add_error_message_in_plan_dataset_tab(paramDict, message):
    namingParams = get_naming_params()
    errorMessageType = namingParams["errorMessageType"]
    planDataTabKey = namingParams["planDataTab"]
    colNumber = 0
    paramDict = add_app_message_to_paramdict(
        message,
        errorMessageType,
        planDataTabKey,
        paramDict,
        isMessage=True,
        isToast=True,
        colNumber=colNumber,
    )
    return paramDict


def add_warning_message_in_plan_dataset_tab(paramDict, message):
    namingParams = get_naming_params()
    warningMessageType = namingParams["warningMessageType"]
    planDataTabKey = namingParams["planDataTab"]
    colNumber = 0
    paramDict = add_app_message_to_paramdict(
        message,
        warningMessageType,
        planDataTabKey,
        paramDict,
        isMessage=True,
        isToast=True,
        colNumber=colNumber,
    )
    return paramDict


def add_info_message_in_plan_dataset_tab(paramDict, message):
    namingParams = get_naming_params()
    infoMessageType = namingParams["infoMessageType"]
    planDataTabKey = namingParams["planDataTab"]
    colNumber = 0
    paramDict = add_app_message_to_paramdict(
        message,
        infoMessageType,
        planDataTabKey,
        paramDict,
        isMessage=True,
        isToast=True,
        colNumber=colNumber,
    )
    return paramDict


def add_success_message_in_plan_dataset_tab(paramDict, message):
    namingParams = get_naming_params()
    successMessageType = namingParams["successMessageType"]
    planDataTabKey = namingParams["planDataTab"]
    colNumber = 0
    paramDict = add_app_message_to_paramdict(
        message,
        successMessageType,
        planDataTabKey,
        paramDict,
        isMessage=True,
        isToast=True,
        colNumber=colNumber,
    )
    return paramDict


def add_error_message_in_plot_charts_tab(paramDict, message):
    namingParams = get_naming_params()
    errorMessageType = namingParams["errorMessageType"]
    plotChartsTabKey = namingParams["plotChartsTab"]
    colNumber = 0
    paramDict = add_app_message_to_paramdict(
        message,
        errorMessageType,
        plotChartsTabKey,
        paramDict,
        isMessage=True,
        isToast=True,
        colNumber=colNumber,
    )
    return paramDict


def add_warning_message_in_plot_charts_tab(paramDict, message):
    namingParams = get_naming_params()
    warningMessageType = namingParams["warningMessageType"]
    plotChartsTabKey = namingParams["plotChartsTab"]
    colNumber = 0
    paramDict = add_app_message_to_paramdict(
        message,
        warningMessageType,
        plotChartsTabKey,
        paramDict,
        isMessage=True,
        isToast=True,
        colNumber=colNumber,
    )
    return paramDict


def add_info_message_in_plot_charts_tab(paramDict, message):
    namingParams = get_naming_params()
    infoMessageType = namingParams["infoMessageType"]
    plotChartsTabKey = namingParams["plotChartsTab"]
    colNumber = 0
    paramDict = add_app_message_to_paramdict(
        message,
        infoMessageType,
        plotChartsTabKey,
        paramDict,
        isMessage=True,
        isToast=True,
        colNumber=colNumber,
    )
    return paramDict


def add_success_message_in_plot_charts_tab(paramDict, message):
    namingParams = get_naming_params()
    successMessageType = namingParams["successMessageType"]
    plotChartsTabKey = namingParams["plotChartsTab"]
    colNumber = 0
    paramDict = add_app_message_to_paramdict(
        message,
        successMessageType,
        plotChartsTabKey,
        paramDict,
        isMessage=True,
        isToast=True,
        colNumber=colNumber,
    )
    return paramDict


def add_error_message_in_filter_dataset_tab(paramDict, message):
    namingParams = get_naming_params()
    errorMessageType = namingParams["errorMessageType"]
    filterDataTabKey = namingParams["filterDataTab"]
    colNumber = 0
    paramDict = add_app_message_to_paramdict(
        message,
        errorMessageType,
        filterDataTabKey,
        paramDict,
        isMessage=True,
        isToast=True,
        colNumber=colNumber,
    )
    return paramDict


def add_warning_message_in_filter_dataset_tab(paramDict, message):
    namingParams = get_naming_params()
    warningMessageType = namingParams["warningMessageType"]
    filterDataTabKey = namingParams["filterDataTab"]
    colNumber = 0
    paramDict = add_app_message_to_paramdict(
        message,
        warningMessageType,
        filterDataTabKey,
        paramDict,
        isMessage=True,
        isToast=True,
        colNumber=colNumber,
    )
    return paramDict


def add_info_message_in_filter_dataset_tab(paramDict, message):
    namingParams = get_naming_params()
    infoMessageType = namingParams["infoMessageType"]
    filterDataTabKey = namingParams["filterDataTab"]
    colNumber = 0
    paramDict = add_app_message_to_paramdict(
        message,
        infoMessageType,
        filterDataTabKey,
        paramDict,
        isMessage=True,
        isToast=True,
        colNumber=colNumber,
    )
    return paramDict


def add_success_message_in_filter_dataset_tab(paramDict, message):
    namingParams = get_naming_params()
    successMessageType = namingParams["successMessageType"]
    filterDataTabKey = namingParams["filterDataTab"]
    colNumber = 0
    paramDict = add_app_message_to_paramdict(
        message,
        successMessageType,
        filterDataTabKey,
        paramDict,
        isMessage=True,
        isToast=True,
        colNumber=colNumber,
    )
    return paramDict


def add_error_message_in_period_options_tab(paramDict, message):
    namingParams = get_naming_params()
    errorMessageType = namingParams["errorMessageType"]
    setTimePeriodTabKey = namingParams["setTimePeriodTab"]
    colNumber = 0
    paramDict = add_app_message_to_paramdict(
        message,
        errorMessageType,
        setTimePeriodTabKey,
        paramDict,
        isMessage=True,
        isToast=True,
        colNumber=colNumber,
    )
    return paramDict


def add_warning_message_in_period_options_tab(paramDict, message):
    namingParams = get_naming_params()
    warningMessageType = namingParams["warningMessageType"]
    setTimePeriodTabKey = namingParams["setTimePeriodTab"]
    colNumber = 0
    paramDict = add_app_message_to_paramdict(
        message,
        warningMessageType,
        setTimePeriodTabKey,
        paramDict,
        isMessage=True,
        isToast=True,
        colNumber=colNumber,
    )
    return paramDict


def add_info_message_in_period_options_tab(paramDict, message):
    namingParams = get_naming_params()
    infoMessageType = namingParams["infoMessageType"]
    setTimePeriodTabKey = namingParams["setTimePeriodTab"]
    colNumber = 0
    paramDict = add_app_message_to_paramdict(
        message,
        infoMessageType,
        setTimePeriodTabKey,
        paramDict,
        isMessage=True,
        isToast=True,
        colNumber=colNumber,
    )
    return paramDict


def add_success_message_in_period_options_tab(paramDict, message):
    namingParams = get_naming_params()
    successMessageType = namingParams["successMessageType"]
    setTimePeriodTabKey = namingParams["setTimePeriodTab"]
    colNumber = 0
    paramDict = add_app_message_to_paramdict(
        message,
        successMessageType,
        setTimePeriodTabKey,
        paramDict,
        isMessage=True,
        isToast=True,
        colNumber=colNumber,
    )
    return paramDict


def add_write_message_in_period_options_tab(paramDict, message):
    namingParams = get_naming_params()
    writeMessageType = namingParams["writeMessageType"]
    setTimePeriodTabKey = namingParams["setTimePeriodTab"]
    colNumber = 0
    paramDict = add_app_message_to_paramdict(
        message,
        writeMessageType,
        setTimePeriodTabKey,
        paramDict,
        isMessage=True,
        isToast=True,
        colNumber=colNumber,
    )
    return paramDict


def add_error_message_in_variance_options_tab(paramDict, message):
    namingParams = get_naming_params()
    errorMessageType = namingParams["warningMessageType"]
    setVarianceOptionsTabKey = namingParams["setVarianceOptionsTab"]
    colNumber = 0
    paramDict = add_app_message_to_paramdict(
        message,
        warningMessageType,
        setVarianceOptionsTabKey,
        paramDict,
        isMessage=True,
        isToast=True,
        colNumber=colNumber,
    )
    return paramDict


def add_warning_message_in_variance_options_tab(paramDict, message):
    namingParams = get_naming_params()
    warningMessageType = namingParams["warningMessageType"]
    setVarianceOptionsTabKey = namingParams["setVarianceOptionsTab"]
    colNumber = 0
    paramDict = add_app_message_to_paramdict(
        message,
        warningMessageType,
        setVarianceOptionsTabKey,
        paramDict,
        isMessage=True,
        isToast=True,
        colNumber=colNumber,
    )
    return paramDict


def add_info_message_in_variance_options_tab(paramDict, message):
    namingParams = get_naming_params()
    infoMessageType = namingParams["infoMessageType"]
    setVarianceOptionsTabKey = namingParams["setVarianceOptionsTab"]
    colNumber = 0
    paramDict = add_app_message_to_paramdict(
        message,
        infoMessageType,
        setVarianceOptionsTabKey,
        paramDict,
        isMessage=True,
        isToast=True,
        colNumber=colNumber,
    )
    return paramDict


def add_success_message_in_variance_options_tab(paramDict, message):
    namingParams = get_naming_params()
    successMessageType = namingParams["successMessageType"]
    setVarianceOptionsTabKey = namingParams["setVarianceOptionsTab"]
    colNumber = 0
    paramDict = add_app_message_to_paramdict(
        message,
        successMessageType,
        setVarianceOptionsTabKey,
        paramDict,
        isMessage=True,
        isToast=True,
        colNumber=colNumber,
    )
    return paramDict


def add_write_message_in_variance_options_tab(paramDict, message):
    namingParams = get_naming_params()
    writeMessageType = namingParams["writeMessageType"]
    setVarianceOptionsTabKey = namingParams["setVarianceOptionsTab"]
    colNumber = 0
    paramDict = add_app_message_to_paramdict(
        message,
        writeMessageType,
        setVarianceOptionsTabKey,
        paramDict,
        isMessage=True,
        isToast=True,
        colNumber=colNumber,
    )
    return paramDict


def add_empty_dataset_error_message_in_plot_charts_tab(paramDict):
    namingParams = get_naming_params()
    errorMessageType = namingParams["errorMessageType"]
    plotChartsTabKey = namingParams["plotChartsTab"]
    colNumber = 0
    errorMessage = (
        "Empty dataset. No data to plot. Try changing plotting or filtering parameters"
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
    return paramDict
