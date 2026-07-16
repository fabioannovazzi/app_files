from __future__ import annotations

import copy
import datetime as dt
import logging
import sys
from pathlib import Path
import polars as pl
from dateutil.relativedelta import relativedelta

if "modules.utilities.utils" in sys.modules:
    utils = sys.modules["modules.utilities.utils"]
else:  # pragma: no cover
    try:
        import modules.utilities.utils as utils
    except ModuleNotFoundError:  # pragma: no cover
        sys.path.append(str(Path(__file__).resolve().parents[2]))
        import modules.utilities.utils as utils

from modules.charting.chart_primitives import check_if_plan_or_py
from modules.layout.memoization import check_collect
from modules.layout.session_manager import SessionManager
from modules.utilities.config import (
    get_config_params,
    get_naming_params,
    get_run_params,
)
from modules.utilities.date_utils import parse_date_column
from modules.utilities.error_messages import (
    add_app_message_to_paramdict,
    add_error_message_in_load_data_tab,
    add_info_message_in_period_options_tab,
    add_warning_message_in_load_data_tab,
    add_warning_message_in_period_options_tab,
    add_write_message_in_period_options_tab,
)
from modules.utilities.helpers import (
    drop_columns,
    duplicate_dataframe,
    get_dataset_specific_parameter,
    get_date_columns_from_schema,
    get_period_length,
    get_periods_array,
    measure_time,
    print_error_details,
    unique,
)
from modules.utilities.ui_notifier import ui as notifier
from src.date_helpers import start_of_month, start_of_quarter
from src.period_aggregators import (
    calculate_period_to_date_same_year,
    calculate_period_to_date_year_ago,
    calculate_rolling_period,
)

logger = logging.getLogger(__name__)


def build_initial_index_array(
    df: pl.DataFrame | pl.LazyFrame, paramDict: dict
) -> tuple[pl.LazyFrame, list[str], list[str], dict]:
    """
    we want to separate the buildup of the index array in a separate function
    so we can use feed different indexes to the function that indexes the df
    here the order of the columns in the index does not matter
    we also set all indexcolumns to object to avoid fake numeric columns
    """
    was_lazy = isinstance(df, pl.LazyFrame)
    df = df.lazy() if not was_lazy else df

    namingParams = get_naming_params()
    configParams = get_config_params()
    stemArray = namingParams["stemArray"]
    periodName = namingParams["periodName"]
    dataPreparation = namingParams["dataPreparationName"]
    indexArrayBuilt = namingParams["indexArrayBuiltName"]
    cleanedNewIndexCols = namingParams["cleanedNewIndexColsName"]
    toDropStemArray = configParams[namingParams["toDropStemArray"]]
    metricsColsDict = configParams[namingParams["metricsColsDict"]]
    nonMetricNumericColumns = namingParams["nonMetricNumericColumns"]
    columns, schema = utils.get_schema_and_column_names(df)
    indexCols = []
    valueCols = []
    toDrop = []
    columns, schema = utils.get_schema_and_column_names(df)
    for column in columns:
        if column not in metricsColsDict:
            if schema.get(column) != pl.Utf8:
                toDrop = check_if_stems_in_string(column, toDropStemArray, toDrop)
            if paramDict[namingParams["allDimensionsString"]]:
                if schema.get(column) == pl.Utf8 or column == periodName:
                    indexCols.append(column)
            else:
                indexCols.append(column)
        elif metricsColsDict[column]:
            valueCols.append(column)
        else:
            toDrop.append(column)
    newIndexCols = []
    for indexCol in indexCols:
        if indexCol not in toDrop:
            newIndexCols.append(indexCol)
    df = drop_columns(df, toDrop)
    columns, schema = utils.get_schema_and_column_names(df)
    paramDict[nonMetricNumericColumns] = []
    for column in columns:
        if column not in valueCols + newIndexCols:
            paramDict[nonMetricNumericColumns].append(column)
    measure_time(dataPreparation, indexArrayBuilt, False)
    df = df.with_columns(
        [
            pl.col(column).cast(pl.Utf8).alias(column)
            for column in newIndexCols
            if column in columns
        ]
    )
    measure_time(dataPreparation, cleanedNewIndexCols, False)
    return df, newIndexCols, valueCols, paramDict


try:
    from src.identify_columns_logic import cogs_col_found as logic_cogs_col_found
    from src.identify_columns_logic import date_col_found as logic_date_col_found
    from src.identify_columns_logic import (
        discount_col_found as logic_discount_col_found,
    )
    from src.identify_columns_logic import (
        indirect_costs_col_found as logic_indirect_costs_col_found,
    )
    from src.identify_columns_logic import (
        monetary_col_found as logic_monetary_col_found,
    )
    from src.identify_columns_logic import period_col_found as logic_period_col_found
    from src.identify_columns_logic import units_col_found as logic_units_col_found
    from src.identify_columns_logic import volume_col_found as logic_volume_col_found
except Exception as e:  # pragma: no cover - missing in test stubs
    logging.exception(e)
    notifier.error("Something went wrong.")
    logic_cogs_col_found = lambda param: (param, [])
    logic_date_col_found = lambda param: (param, [])
    logic_discount_col_found = lambda param: (param, [])
    logic_indirect_costs_col_found = lambda param: (param, [])
    logic_monetary_col_found = lambda param: (param, [])
    logic_period_col_found = lambda param: (param, [])
    logic_units_col_found = lambda param: (param, [])
    logic_volume_col_found = lambda param: (param, [])


def monetary_col_found(paramDict, ui: "IdentifyColumnsUI" | None = None):
    """Display messages about the monetary column."""

    if ui is None:
        from ui.identify_columns_ui import IdentifyColumnsUI

        ui = IdentifyColumnsUI()
    paramDict, messages = logic_monetary_col_found(paramDict)
    ui.show_messages(messages)
    return paramDict, messages


def volume_col_found(paramDict, ui: "IdentifyColumnsUI" | None = None):
    """Display messages about the volume column."""

    if ui is None:
        from ui.identify_columns_ui import IdentifyColumnsUI

        ui = IdentifyColumnsUI()
    paramDict, messages = logic_volume_col_found(paramDict)
    ui.show_messages(messages)
    return paramDict, messages


def units_col_found(paramDict, ui: "IdentifyColumnsUI" | None = None):
    """Display messages about the units column."""

    if ui is None:
        from ui.identify_columns_ui import IdentifyColumnsUI

        ui = IdentifyColumnsUI()
    paramDict, messages = logic_units_col_found(paramDict)
    ui.show_messages(messages)
    return paramDict, messages


def date_col_found(paramDict, ui: "IdentifyColumnsUI" | None = None):
    """Display messages about detected date column."""

    if ui is None:
        from ui.identify_columns_ui import IdentifyColumnsUI

        ui = IdentifyColumnsUI()
    paramDict, messages = logic_date_col_found(paramDict)
    ui.show_messages(messages)
    return paramDict, messages


def period_col_found(
    df,
    paramDict,
    ui: "IdentifyColumnsUI" | None = None,
    preserve_date_col: bool = False,
):
    """Display messages about detected period column.

    Parameters
    ----------
    df: pl.LazyFrame | pl.DataFrame
        Dataset under analysis.
    paramDict: dict
        Parameter dictionary used across data preparation.
    ui: IdentifyColumnsUI | None, optional
        UI helper for rendering messages.
    preserve_date_col: bool, optional
        When ``True`` the original date column is kept in the dataframe.
    """

    if ui is None:
        from ui.identify_columns_ui import IdentifyColumnsUI

        ui = IdentifyColumnsUI()
    paramDict, messages = logic_period_col_found(paramDict)
    ui.show_messages(messages)

    naming = get_naming_params()
    if (
        naming["periodColFound"] in paramDict
        and paramDict[naming["periodColFound"]]
        and len(paramDict.get(naming["likelyPeriodCols"], [])) > 0
        and paramDict.get(naming["numberOfPeriodsFound"], 0) >= 1
    ):
        if not preserve_date_col:
            df = drop_columns(df, [naming["dateName"]])
    return df, paramDict, messages


def discount_col_found(paramDict, ui: "IdentifyColumnsUI" | None = None):
    """Display messages about discount column."""

    if ui is None:
        from ui.identify_columns_ui import IdentifyColumnsUI

        ui = IdentifyColumnsUI()
    paramDict, messages = logic_discount_col_found(paramDict)
    ui.show_messages(messages)
    return paramDict, messages


def cogs_col_found(paramDict, ui: "IdentifyColumnsUI" | None = None):
    """Display messages about the COGS column."""

    if ui is None:
        from ui.identify_columns_ui import IdentifyColumnsUI

        ui = IdentifyColumnsUI()

    paramDict, messages = logic_cogs_col_found(paramDict)
    ui.show_messages(messages)
    return paramDict, messages


def indirect_costs_col_found(paramDict, ui: "IdentifyColumnsUI" | None = None):
    """Display messages about the indirect costs column."""

    if ui is None:
        from ui.identify_columns_ui import IdentifyColumnsUI

        ui = IdentifyColumnsUI()

    paramDict, messages = logic_indirect_costs_col_found(paramDict)
    ui.show_messages(messages)
    return paramDict, messages


def category_weighted_distribution_col_found(paramDict):
    """
    messages to cwd monetary columns
    """
    namingParams = get_naming_params()
    configParams = get_config_params()
    categoryWeightedDistributionName = namingParams["categoryWeightedDistributionName"]
    cwdColFound = namingParams["cwdColFound"]
    likelyCwdCols = namingParams["likelyCwdCols"]
    successIcon = namingParams["successIcon"]
    categoryWeightedDistributionStemDict = namingParams[
        "categoryWeightedDistributionStemDict"
    ]
    stemArray = namingParams["stemArray"]
    stemDict = namingParams["stemDict"]
    stemDict = configParams[stemDict]
    if cwdColFound in paramDict:
        nameList = (
            str(stemDict[categoryWeightedDistributionStemDict][stemArray])
            .replace("[", "")
            .replace("]", "")
        )
        if paramDict[cwdColFound] and len(paramDict[likelyCwdCols]) > 0:
            notifier.success(
                "The **"
                + str(paramDict[likelyCwdCols][0])
                + "** column was tagged as the *category weighted distribution* driver column of the dataset.",
                icon=successIcon,
            )
            notifier.caption(
                """If this is not correct, rename the category weighted distribution column and reload the file.
                    The category weighted distribution column must be in **plain number format** (no thousand separators, no % signs, zero written as 0 not as -).
                    The name of the category weighted distribution column **must contain** one of these stems:
                    """
            )
            notifier.caption("*" + nameList + "*")
            notifier.caption("""  \n""")
            notifier.caption("""  \n""")
        else:
            notifier.caption(
                """We were unable to identify a *category weighted distribution* driver column in the dataset.
                    This is OK. The app **does not require** a category weighted distribution column. 
                    """
            )
            notifier.caption(
                """If your dataset indeed has a category weighted distribution column, rename it and reload the file.
                    The category weighted distribution column must be in **absolute (not percent)** value with positive sign.
                    The name of the category weighted distribution column **must contain** one of these stems:
                    """
            )
            notifier.caption("*" + nameList + "*")
            notifier.caption("""  \n""")
            notifier.caption("""  \n""")
    return paramDict


def checkouts_col_found(paramDict):
    """
    messages to identify driver col
    """
    namingParams = get_naming_params()
    configParams = get_config_params()
    checkoutsName = namingParams["checkoutsName"]
    checkoutsColFound = namingParams["checkoutsColFound"]
    likelyCheckoutsCols = namingParams["likelyCheckoutsCols"]
    checkoutsStemDict = namingParams["checkoutsStemDict"]
    successIcon = namingParams["successIcon"]
    stemArray = namingParams["stemArray"]
    stemDict = namingParams["stemDict"]
    stemDict = configParams[stemDict]
    if checkoutsColFound in paramDict:
        nameList = (
            str(stemDict[checkoutsStemDict][stemArray])
            .replace("[", "")
            .replace("]", "")
        )
        if paramDict[checkoutsColFound] and len(paramDict[likelyCheckoutsCols]) > 0:
            notifier.success(
                "The **"
                + str(paramDict[likelyCheckoutsCols][0])
                + "** was tagged as the *checkouts* driver column of the dataset.",
                icon=successIcon,
            )
            notifier.caption(
                """If this is not correct, rename the checkouts column and reload the file.
                    The checkouts column must be in **plain number format** (no thousand separators, zero written as 0 not as -).
                    The name of the checkouts column **must contain** one of these stems:
                    """
            )
            notifier.caption("*" + nameList + "*")
            notifier.caption("""  \n""")
            notifier.caption("""  \n""")
        else:
            notifier.caption(
                """We were unable to identify a *checkouts* driver column in the dataset.
                    This is OK. The app **does not require** a check out column. 
                    """
            )
            notifier.caption(
                """If your dataset indeed has a checkouts column, rename it and reload the file.
                    The checkouts column must be in **absolute (not percent)** value with positive sign.
                    The name of the checkouts column **must contain** one of these stems:
                    """
            )
            notifier.caption("*" + nameList + "*")
            notifier.caption("""  \n""")
            notifier.caption("""  \n""")
    return paramDict


def visits_col_found(paramDict):
    """
    messages to identify driver col
    """
    namingParams = get_naming_params()
    configParams = get_config_params()
    visitsName = namingParams["visitsName"]
    visitsColFound = namingParams["visitsColFound"]
    likelyVisitsCols = namingParams["likelyVisitsCols"]
    visitsStemDict = namingParams["visitsStemDict"]
    successIcon = namingParams["successIcon"]
    stemArray = namingParams["stemArray"]
    stemDict = namingParams["stemDict"]
    stemDict = configParams[stemDict]
    if visitsColFound in paramDict:
        nameList = (
            str(stemDict[visitsStemDict][stemArray]).replace("[", "").replace("]", "")
        )
        if paramDict[visitsColFound] and len(paramDict[likelyVisitsCols]) > 0:
            notifier.success(
                "The **"
                + str(paramDict[likelyVisitsCols][0])
                + "** was tagged as the *visits* driver column of the dataset.",
                icon=successIcon,
            )
            notifier.caption(
                """If this is not correct, rename the visits column and reload the file.
                    The visits column must be in **plain number format** (no thousand separators, zero written as 0 not as -).
                    The name of the visits column **must contain** one of these stems:
                    """
            )
            notifier.caption("*" + nameList + "*")
            notifier.caption("""  \n""")
            notifier.caption("""  \n""")
        else:
            notifier.caption(
                """We were unable to identify a *visits* drive column in the dataset.
                    This is OK. The app **does not require** a check out column. 
                    """
            )
            notifier.caption(
                """If your dataset indeed has a visits column, rename it and reload the file.
                    The visits column must be in **absolute (not percent)** value with positive sign.
                    The name of the visits column **must contain** one of these stems:
                    """
            )
            notifier.caption("*" + nameList + "*")
            notifier.caption("""  \n""")
            notifier.caption("""  \n""")
    return paramDict


def promo_amount_col_found(paramDict):
    """
    messages to identify discount columns
    """
    namingParams = get_naming_params()
    configParams = get_config_params()
    monetaryPromoLocalCurrencyName = namingParams["monetaryPromoLocalCurrencyName"]
    monetaryPromoLocalCurrencyColFound = namingParams[
        "monetaryPromoLocalCurrencyColFound"
    ]
    likelyPromoLocalCurrencyValueCols = namingParams[
        "likelyPromoLocalCurrencyValueCols"
    ]
    monetaryPromoLocalCurrencyStemDict = namingParams[
        "monetaryPromoLocalCurrencyStemDict"
    ]
    successIcon = namingParams["successIcon"]
    stemArray = namingParams["stemArray"]
    stemDict = namingParams["stemDict"]
    stemDict = configParams[stemDict]
    if monetaryPromoLocalCurrencyColFound in paramDict:
        nameList = (
            str(stemDict[monetaryPromoLocalCurrencyStemDict][stemArray])
            .replace("[", "")
            .replace("]", "")
        )
        if (
            paramDict[monetaryPromoLocalCurrencyColFound]
            and len(paramDict[likelyPromoLocalCurrencyValueCols]) > 0
        ):
            notifier.success(
                "The **"
                + str(paramDict[likelyPromoLocalCurrencyValueCols][0])
                + "** column was tagged as the *promo amount* column of the dataset.",
                icon=successIcon,
            )
            notifier.caption(
                """If this is not correct, rename the promo amount column and reload the file.
                    The promo amount column must be in **plain number format** (no thousand separators, no currency 💲 format, zero written as 0 not as -).
                    The name of the promo amount column **must contain** one of these stems:
                    """
            )
            notifier.caption("*" + nameList + "*")
            notifier.caption("""  \n""")
            notifier.caption("""  \n""")
        else:
            notifier.caption(
                """We were unable to identify a *promo amount* column in the dataset.
                    This is OK. The app **does not require** a promo amount column. 
                    """
            )
            notifier.caption(
                """If your dataset indeed has a promo amount column, rename it and reload the file.
                    The name of the promo amount column **must contain** one of these stems:
                    """
            )
            notifier.caption("*" + nameList + "*")
            notifier.caption("""  \n""")
            notifier.caption("""  \n""")
    return paramDict


def no_promo_amount_col_found(paramDict):
    """
    messages to identify discount columns
    """
    namingParams = get_naming_params()
    configParams = get_config_params()
    monetaryNoPromoLocalCurrencyName = namingParams["monetaryNoPromoLocalCurrencyName"]
    monetaryNoPromoLocalCurrencyColFound = namingParams[
        "monetaryNoPromoLocalCurrencyColFound"
    ]
    likelyNoPromoLocalCurrencyValueCols = namingParams[
        "likelyNoPromoLocalCurrencyValueCols"
    ]
    monetaryNoPromoLocalCurrencyStemDict = namingParams[
        "monetaryNoPromoLocalCurrencyStemDict"
    ]
    successIcon = namingParams["successIcon"]
    stemArray = namingParams["stemArray"]
    stemDict = namingParams["stemDict"]
    stemDict = configParams[stemDict]
    if monetaryNoPromoLocalCurrencyColFound in paramDict:
        nameList = (
            str(stemDict[monetaryNoPromoLocalCurrencyStemDict][stemArray])
            .replace("[", "")
            .replace("]", "")
        )
        if (
            paramDict[monetaryNoPromoLocalCurrencyColFound]
            and len(paramDict[likelyNoPromoLocalCurrencyValueCols]) > 0
        ):
            notifier.success(
                "The **"
                + str(paramDict[likelyNoPromoLocalCurrencyValueCols][0])
                + "** column was tagged as the *no promo amount* column of the dataset.",
                icon=successIcon,
            )
            notifier.caption(
                """If this is not correct, rename the no promo amount column and reload the file.
                    The no promo amount column must be in **plain number format** (no thousand separators, no currency 💲 format, zero written as 0 not as -).
                    The name of the no promo amount column **must contain** one of these stems:
                    """
            )
            notifier.caption("*" + nameList + "*")
            notifier.caption("""  \n""")
            notifier.caption("""  \n""")
        else:
            notifier.caption(
                """We were unable to identify a *no promo amount* column in the dataset.
                    This is OK. The app **does not require** a no promo amount column. 
                    """
            )
            notifier.caption(
                """If your dataset indeed has a no promo amount column, rename it and reload the file.
                    The name of the no promo amount column **must contain** one of these stems:
                    """
            )
            notifier.caption("*" + nameList + "*")
            notifier.caption("""  \n""")
            notifier.caption("""  \n""")
    return paramDict


def promo_units_col_found(paramDict):
    """
    messages to identify discount columns
    """
    namingParams = get_naming_params()
    configParams = get_config_params()
    unitsPromoName = namingParams["unitsPromoName"]
    unitPromoColFound = namingParams["unitPromoColFound"]
    likelyPromoUnitsCols = namingParams["likelyPromoUnitsCols"]
    unitsPromoStemDict = namingParams["unitsPromoStemDict"]
    successIcon = namingParams["successIcon"]
    stemArray = namingParams["stemArray"]
    stemDict = namingParams["stemDict"]
    stemDict = configParams[stemDict]
    if unitPromoColFound in paramDict:
        nameList = (
            str(stemDict[unitsPromoStemDict][stemArray])
            .replace("[", "")
            .replace("]", "")
        )
        if paramDict[unitPromoColFound] and len(paramDict[likelyPromoUnitsCols]) > 0:
            notifier.success(
                "The **"
                + str(paramDict[likelyPromoUnitsCols][0])
                + "** column was tagged as the *promo units* column of the dataset.",
                icon=successIcon,
            )
            notifier.caption(
                """If this is not correct, rename the promo units column and reload the file.
                    The promo units column must be in **plain number format** (no thousand separators, no currency 💲 format, zero written as 0 not as -).
                    The name of the promo units column **must contain** one of these stems:
                    """
            )
            notifier.caption("*" + nameList + "*")
            notifier.caption("""  \n""")
            notifier.caption("""  \n""")
        else:
            notifier.caption(
                """We were unable to identify a *promo units* column in the dataset.
                    This is OK. The app **does not require** a promo units column. 
                    """
            )
            notifier.caption(
                """If your dataset indeed has a promo units column, rename it and reload the file.
                    The name of the promo units column **must contain** one of these stems:
                    """
            )
            notifier.caption("*" + nameList + "*")
            notifier.caption("""  \n""")
            notifier.caption("""  \n""")
    return paramDict


def no_promo_units_col_found(paramDict):
    """
    messages to identify discount columns
    """
    namingParams = get_naming_params()
    configParams = get_config_params()
    unitsNoPromoName = namingParams["unitsNoPromoName"]
    unitNoPromoColFound = namingParams["unitNoPromoColFound"]
    likelyNoPromoUnitsCols = namingParams["likelyNoPromoUnitsCols"]
    unitsNoPromoStemDict = namingParams["unitsNoPromoStemDict"]
    successIcon = namingParams["successIcon"]
    stemArray = namingParams["stemArray"]
    stemDict = namingParams["stemDict"]
    stemDict = configParams[stemDict]
    if unitNoPromoColFound in paramDict:
        nameList = (
            str(stemDict[unitsNoPromoStemDict][stemArray])
            .replace("[", "")
            .replace("]", "")
        )
        if (
            paramDict[unitNoPromoColFound]
            and len(paramDict[likelyNoPromoUnitsCols]) > 0
        ):
            notifier.success(
                "The **"
                + str(paramDict[likelyNoPromoUnitsCols][0])
                + "** column was tagged as the *no promo units* column of the dataset.",
                icon=successIcon,
            )
            notifier.caption(
                """If this is not correct, rename the no promo units column and reload the file.
                    The no promo units column must be in **plain number format** (no thousand separators, no currency 💲 format, zero written as 0 not as -).
                    The name of the no promo units column **must contain** one of these stems:
                    """
            )
            notifier.caption("*" + nameList + "*")
            notifier.caption("""  \n""")
            notifier.caption("""  \n""")
        else:
            notifier.caption(
                """We were unable to identify a *no promo units* column in the dataset.
                    This is OK. The app **does not require** a no promo units column. 
                    """
            )
            notifier.caption(
                """If your dataset indeed has a no promo units column, rename it and reload the file.
                    The name of the no promo units column **must contain** one of these stems:
                    """
            )
            notifier.caption("*" + nameList + "*")
            notifier.caption("""  \n""")
            notifier.caption("""  \n""")
    return paramDict


from src.identify_columns_logic import show_input_data as logic_show_input_data


def show_input_data(
    df: pl.LazyFrame, paramDict: dict
) -> tuple[pl.LazyFrame, dict, list[tuple[str, str, str | None]]]:
    """Return messages about detected columns without rendering UI."""

    namingParams = get_naming_params()
    impossibleToProcessFile = namingParams["impossibleToProcessFile"]
    stemDict = namingParams["stemDict"]

    messages: list[tuple[str, str, str | None]] = []
    if utils.is_valid_lazyframe(df):
        df, paramDict, messages = logic_show_input_data(df, paramDict)

    if impossibleToProcessFile in paramDict and paramDict[impossibleToProcessFile]:
        df = pl.LazyFrame()

    paramDict.pop(stemDict, None)
    return df, paramDict, messages


def check_for_datecolumns_in_schema(df):
    columns, schema = utils.get_schema_and_column_names(df)
    dateColumns = get_date_columns_from_schema(schema)
    return dateColumns, columns


def find_and_parse_datecolumns(
    df, paramDict, session_manager: SessionManager | None = None
):
    configParams = get_config_params()
    namingParams = get_naming_params()
    dateStemDict = namingParams["dateStemDict"]
    stemDict = namingParams["stemDict"]
    dateColFound = namingParams["dateColFound"]
    likelyDateColsKey = namingParams["likelyDateCols"]
    notMetConditionValue = namingParams["notMetConditionValue"]
    metConditionValue = namingParams["metConditionValue"]
    impossibleToProcessFile = namingParams["impossibleToProcessFile"]
    stemDict = configParams[stemDict]
    stemDict = stemDict[dateStemDict]
    stemArray = stemDict[namingParams["stemArray"]]
    notStemArray = stemDict[namingParams["notStemArray"]]
    possibleDateCols = []
    likelyDateCols = []
    paramDict[dateColFound] = notMetConditionValue
    dateColumns, columns = check_for_datecolumns_in_schema(df)
    session_manager = session_manager or SessionManager()
    if len(dateColumns) == 0:
        for column in columns:
            possibleDateCols, toDrop = check_if_col_name_in_array(
                column, stemArray, notStemArray, possibleDateCols, []
            )
        if len(possibleDateCols) > 0:
            for dateCol in possibleDateCols:
                try:
                    df = parse_date_column(
                        df,
                        dateCol,
                        session_manager=session_manager,
                        drop_invalid=False,
                    )
                    likelyDateCols.append(dateCol)
                except Exception as e:  # pragma: no cover - rare date formats
                    logging.exception(e)
                    msg = print_error_details(e)
                    paramDict = add_error_message_in_load_data_tab(paramDict, msg)
                    paramDict[impossibleToProcessFile] = True
                    paramDict["dateParseError"] = msg
            paramDict[likelyDateColsKey] = likelyDateCols
            if len(likelyDateCols) > 0:
                paramDict[dateColFound] = metConditionValue
    else:
        paramDict[likelyDateColsKey] = dateColumns
        paramDict[dateColFound] = metConditionValue
    return df, paramDict


def check_if_stems_in_string(string, checkArray, resultArray):
    """
    we check if a given string contains a stem that belongs to an array
    """
    for stem in checkArray:
        if stem.lower() in string.lower():
            if string not in resultArray:
                resultArray.append(string)
    return resultArray


def check_if_col_name_in_array(
    column, stemArray, notStemArray, possibleColsArray, toDrop
):
    """
    checking if column name matches some stem that identifies column type
    """
    possibleColsArray = check_if_stems_in_string(column, stemArray, possibleColsArray)
    toDrop = check_if_stems_in_string(column, notStemArray, toDrop)
    return possibleColsArray, toDrop


def fill_na_columns(df, column, fillValue):
    """Fill null values in ``column`` with ``fillValue``."""

    return df.with_columns(pl.col(column).fill_null(fillValue))


def detect_column_name(
    df, metricName, stemsDict, paramDict, checkIfNumeric, checkIfDate, toFloat
):
    """
    we try to find the columns that contain the dollar, the value metrics
    we have two array. The first of stems that should match the second of stems that should not
    match, for value and volume metrics
    We also delete columns such as unit price that we do not want
    """
    runParams = get_run_params()
    checkDateColName = runParams["checkDateColName"]
    namingParams = get_naming_params()
    possibleColsArray = []
    noColsArray = []
    likelyColsArray = []
    toDrop = []
    dateName = namingParams["dateName"]
    periodName = namingParams["periodName"]
    periodColFound = namingParams["periodColFound"]
    uploadedFileType = namingParams["uploadedFileType"]
    nothingThereString = namingParams["nothingThereString"]
    errorMessageType = namingParams["errorMessageType"]
    loadDataTabKey = namingParams["loadDataTab"]
    impossibleToProcessFile = namingParams["impossibleToProcessFile"]
    stemArray = stemsDict[namingParams["stemArray"]]
    notStemArray = stemsDict[namingParams["notStemArray"]]
    getIndex = stemsDict[namingParams["getIndex"]]
    numericTypesArray = [
        pl.Int8,
        pl.Int16,
        pl.Int32,
        pl.Int64,
        pl.UInt8,
        pl.UInt16,
        pl.UInt32,
        pl.UInt64,
        pl.Float32,
        pl.Float64,
    ]
    columns, schema = utils.get_schema_and_column_names(df)
    colNumber = 0
    schemaDict = dict(schema) if schema else {}
    for column in columns:
        possibleColsArray, toDrop = check_if_col_name_in_array(
            column, stemArray, notStemArray, possibleColsArray, toDrop
        )
    for possibleCol in possibleColsArray:
        for notStem in notStemArray:
            if notStem in possibleCol:
                noColsArray.append(possibleCol)
    for possibleCol in possibleColsArray:
        if possibleCol not in noColsArray:
            likelyColsArray.append(possibleCol)
            likelyColsArray = list(set(likelyColsArray))
    isFound = True
    found_cols = paramDict.get(namingParams["foundColsArray"], [])
    # Case 1: the metric column already exists and hasn’t been used
    if metricName in columns and metricName not in found_cols:
        paramDict[namingParams['foundColsArray']].append(metricName)
        if toFloat:
            df = fill_na_columns(df, metricName, 0)
            try:
                df = df.with_columns(
                    pl.col(metricName).cast(pl.Float64).alias(metricName)
                )
            except Exception as e:
                logging.exception(e)
                e = print_error_details(e)
                paramDict = add_app_message_to_paramdict(
                    e,
                    errorMessageType,
                    loadDataTabKey,
                    paramDict,
                    isMessage=True,
                    isToast=True,
                    colNumber=colNumber,
                )
                message = "Unable to parse numeric column. Make sure it is in plain number format"
                paramDict = add_app_message_to_paramdict(
                    message,
                    errorMessageType,
                    loadDataTabKey,
                    paramDict,
                    isMessage=True,
                    isToast=True,
                    colNumber=colNumber,
                )
                paramDict[impossibleToProcessFile] = True
    elif (len(likelyColsArray) > getIndex and
          likelyColsArray[getIndex] not in found_cols):
        candidate_col = likelyColsArray[getIndex]
        if schema.get(candidate_col) in numericTypesArray:
            df = df.rename({candidate_col: metricName}).with_columns(
                pl.col(metricName).fill_null(0).alias(metricName)
            )
        else:
            df = df.rename({candidate_col: metricName})
        paramDict[namingParams['foundColsArray']].append(candidate_col)
        if toFloat:
            try:
                df = df.with_columns(
                    pl.col(metricName).cast(pl.Float64).alias(metricName)
                )
            except Exception as e:
                logging.exception(e)
                e = print_error_details(e)
                paramDict = add_app_message_to_paramdict(
                    e,
                    errorMessageType,
                    loadDataTabKey,
                    paramDict,
                    isMessage=True,
                    isToast=True,
                    colNumber=colNumber,
                )
                message = "Unable to parse numeric column. Make sure it is in plain number format"
                paramDict = add_app_message_to_paramdict(
                    message,
                    errorMessageType,
                    loadDataTabKey,
                    paramDict,
                    isMessage=True,
                    isToast=True,
                    colNumber=colNumber,
                )
                paramDict[impossibleToProcessFile] = True
    else:
        isFound = False
    if len(likelyColsArray) == 0:
        isFound = False
    return df, isFound, likelyColsArray, paramDict


def detect_column(
    df,
    paramDict,
    columnName,
    columnStemDict,
    colFound,
    likelyCols,
    checkIfNumeric,
    checkIfDate,
    toFloat,
):
    """
    putting functions together
    """
    namingParams = get_naming_params()
    columnStems, paramDict = get_dataset_specific_parameter(
        paramDict, namingParams["stemDict"], columnStemDict
    )
    df, isColFound, likelyColsArray, paramDict = detect_column_name(
        df, columnName, columnStems, paramDict, checkIfNumeric, checkIfDate, toFloat
    )
    paramDict[colFound], paramDict[likelyCols] = isColFound, likelyColsArray
    return paramDict, df


def insert_calculated_difference_column(df, fromCol, subtractCol, resultCol):
    """
    we recalculate, and insert if they are not already there, calculated columns such as net sales or margin after cogs
    so we do not have to worry if they are missing or wrongly calculated
    """
    columns, schema = utils.get_schema_and_column_names(df)
    if subtractCol in columns:
        if fromCol in columns:
            df = df.with_columns(
                (pl.col(fromCol) - pl.col(subtractCol)).alias(resultCol)
            )
    return df


def find_distribution_metric_columns(df, paramDict):
    """
    we try to find the columns that contain the dollar, the value and the date metrics
    based on stem matching. First we check if we already have the right columns
    """
    namingParams = get_naming_params()
    categoryWeightedDistributionName = namingParams["categoryWeightedDistributionName"]
    totalDistributionPointsName = namingParams["totalDistributionPointsName"]
    baselineValueMetricName = namingParams["baselineValueMetricName"]
    baselineUnitsMetricName = namingParams["baselineUnitsMetricName"]
    likelyCwdCols = namingParams["likelyCwdCols"]
    likelyTdpCols = namingParams["likelyTdpCols"]
    likelyBaselineValueCols = namingParams["likelyBaselineValueCols"]
    likelyBaselineUnitsCols = namingParams["likelyBaselineUnitsCols"]
    cwdColFound = namingParams["cwdColFound"]
    tdpColFound = namingParams["tdpColFound"]
    baselineValueColFound = namingParams["baselineValueColFound"]
    baselineUnitsColFound = namingParams["baselineUnitsColFound"]
    categoryWeightedDistributionStemDict = namingParams[
        "categoryWeightedDistributionStemDict"
    ]
    totalDistributionPointsStemDict = namingParams["totalDistributionPointsStemDict"]
    baselineValueStemDict = namingParams["baselineValueStemDict"]
    baselineunitsStemDict = namingParams["baselineunitsStemDict"]
    paramDict[namingParams["foundColsArray"]] = []
    paramDict, df = detect_column(
        df,
        paramDict,
        categoryWeightedDistributionName,
        categoryWeightedDistributionStemDict,
        cwdColFound,
        likelyCwdCols,
        True,
        False,
        True,
    )
    paramDict, df = detect_column(
        df,
        paramDict,
        totalDistributionPointsName,
        totalDistributionPointsStemDict,
        tdpColFound,
        likelyTdpCols,
        True,
        False,
        True,
    )
    paramDict, df = detect_column(
        df,
        paramDict,
        baselineValueMetricName,
        baselineValueStemDict,
        baselineValueColFound,
        likelyBaselineValueCols,
        True,
        False,
        True,
    )
    paramDict, df = detect_column(
        df,
        paramDict,
        baselineUnitsMetricName,
        baselineunitsStemDict,
        baselineUnitsColFound,
        likelyBaselineUnitsCols,
        True,
        False,
        True,
    )
    return df, paramDict


def find_checkout_columns(df, paramDict):
    """
    we try to find the columns that contain the dollar, the value and the date metrics
    based on stem matching. First we check if we already have the right columns
    """
    namingParams = get_naming_params()
    checkoutsName = namingParams["checkoutsName"]
    likelyCheckoutsCols = namingParams["likelyCheckoutsCols"]
    checkoutsColFound = namingParams["checkoutsColFound"]
    checkoutsStemDict = namingParams["checkoutsStemDict"]
    paramDict[namingParams["foundColsArray"]] = []
    paramDict, df = detect_column(
        df,
        paramDict,
        checkoutsName,
        checkoutsStemDict,
        checkoutsColFound,
        likelyCheckoutsCols,
        True,
        False,
        True,
    )
    return df, paramDict


def find_visits_columns(df, paramDict):
    """
    we try to find the columns that contain the dollar, the value and the date metrics
    based on stem matching. First we check if we already have the right columns
    """
    namingParams = get_naming_params()
    visitsName = namingParams["visitsName"]
    likelyVisitsCols = namingParams["likelyVisitsCols"]
    visitsColFound = namingParams["visitsColFound"]
    visitsStemDict = namingParams["visitsStemDict"]
    paramDict[namingParams["foundColsArray"]] = []
    paramDict, df = detect_column(
        df,
        paramDict,
        visitsName,
        visitsStemDict,
        visitsColFound,
        likelyVisitsCols,
        True,
        False,
        True,
    )
    return df, paramDict


def find_volume_columns(df, paramDict):
    """
    we try to find the columns that contain the dollar, the value and the date metrics
    based on stem matching. First we check if we already have the right columns
    """
    namingParams = get_naming_params()
    unitsName = namingParams["unitsName"]
    volumeName = namingParams["volumeName"]
    unitsPromoName = namingParams["unitsPromoName"]
    unitsNoPromoName = namingParams["unitsNoPromoName"]
    likelyUnitsCols = namingParams["likelyUnitsCols"]
    likelyVolumeCols = namingParams["likelyVolumeCols"]
    likelyPromoUnitsCols = namingParams["likelyPromoUnitsCols"]
    likelyNoPromoUnitsCols = namingParams["likelyNoPromoUnitsCols"]
    unitsColFound = namingParams["unitsColFound"]
    volumeColFound = namingParams["volumeColFound"]
    unitPromoColFound = namingParams["unitPromoColFound"]
    unitNoPromoColFound = namingParams["unitNoPromoColFound"]
    unitsStemDict = namingParams["unitsStemDict"]
    volumeStemDict = namingParams["volumeStemDict"]
    unitsPromoStemDict = namingParams["unitsPromoStemDict"]
    unitsNoPromoStemDict = namingParams["unitsNoPromoStemDict"]
    paramDict[namingParams["foundColsArray"]] = []
    paramDict, df = detect_column(
        df,
        paramDict,
        unitsName,
        unitsStemDict,
        unitsColFound,
        likelyUnitsCols,
        True,
        False,
        True,
    )
    paramDict, df = detect_column(
        df,
        paramDict,
        volumeName,
        volumeStemDict,
        volumeColFound,
        likelyVolumeCols,
        True,
        False,
        True,
    )
    paramDict, df = detect_column(
        df,
        paramDict,
        unitsPromoName,
        unitsPromoStemDict,
        unitPromoColFound,
        likelyPromoUnitsCols,
        True,
        False,
        True,
    )
    paramDict, df = detect_column(
        df,
        paramDict,
        unitsNoPromoName,
        unitsNoPromoStemDict,
        unitNoPromoColFound,
        likelyNoPromoUnitsCols,
        True,
        False,
        True,
    )
    return df, paramDict


def find_monetary_columns(df, paramDict):
    """
    we try to find the columns that contain the dollar, the value and the date metrics
    based on stem matching. First we check if we already have the right columns
    """
    namingParams = get_naming_params()
    monetaryName = namingParams["monetaryLocalCurrencyName"]
    monetaryPromoLocalCurrencyName = namingParams["monetaryPromoLocalCurrencyName"]
    monetaryNoPromoLocalCurrencyName = namingParams["monetaryNoPromoLocalCurrencyName"]
    monetaryDollarCurrencyName = namingParams["monetaryDollarCurrencyName"]
    monetaryPromoDollarCurrencyName = namingParams["monetaryPromoDollarCurrencyName"]
    monetaryNoPromoDollarCurrencyName = namingParams[
        "monetaryNoPromoDollarCurrencyName"
    ]
    likelyValueCols = namingParams["likelyLocalCurrencyValueCols"]
    likelyPromoLocalCurrencyValueCols = namingParams[
        "likelyPromoLocalCurrencyValueCols"
    ]
    likelyNoPromoLocalCurrencyValueCols = namingParams[
        "likelyNoPromoLocalCurrencyValueCols"
    ]
    likelyDollarCurrencyValueCols = namingParams["likelyDollarCurrencyValueCols"]
    likelyPromoDollarCurrencyValueCols = namingParams[
        "likelyPromoDollarCurrencyValueCols"
    ]
    likelyNoPromoDollarCurrencyValueCols = namingParams[
        "likelyNoPromoDollarCurrencyValueCols"
    ]
    monetaryColFound = namingParams["monetaryLocalCurrencyColFound"]
    monetaryPromoLocalCurrencyColFound = namingParams[
        "monetaryPromoLocalCurrencyColFound"
    ]
    monetaryNoPromoLocalCurrencyColFound = namingParams[
        "monetaryNoPromoLocalCurrencyColFound"
    ]
    monetaryDollarCurrencyColFound = namingParams["monetaryDollarCurrencyColFound"]
    monetaryPromoDollarCurrencyColFound = namingParams[
        "monetaryPromoDollarCurrencyColFound"
    ]
    monetaryNoPromoDollarCurrencyColFound = namingParams[
        "monetaryNoPromoDollarCurrencyColFound"
    ]
    monetaryStemDict = namingParams["monetaryLocalCurrencyStemDict"]
    monetaryPromoLocalCurrencyStemDict = namingParams[
        "monetaryPromoLocalCurrencyStemDict"
    ]
    monetaryNoPromoLocalCurrencyStemDict = namingParams[
        "monetaryNoPromoLocalCurrencyStemDict"
    ]
    monetaryDollarCurrencyStemDict = namingParams["monetaryDollarCurrencyStemDict"]
    monetaryPromoDollarCurrencyStemDict = namingParams[
        "monetaryPromoDollarCurrencyStemDict"
    ]
    monetaryNoPromoDollarCurrencyStemDict = namingParams[
        "monetaryNoPromoDollarCurrencyStemDict"
    ]
    paramDict[namingParams["foundColsArray"]] = []
    paramDict, df = detect_column(
        df,
        paramDict,
        monetaryName,
        monetaryStemDict,
        monetaryColFound,
        likelyValueCols,
        True,
        False,
        True,
    )
    paramDict, df = detect_column(
        df,
        paramDict,
        monetaryDollarCurrencyName,
        monetaryDollarCurrencyStemDict,
        monetaryDollarCurrencyColFound,
        likelyDollarCurrencyValueCols,
        True,
        False,
        True,
    )
    paramDict, df = detect_column(
        df,
        paramDict,
        monetaryPromoDollarCurrencyName,
        monetaryPromoDollarCurrencyStemDict,
        monetaryPromoDollarCurrencyColFound,
        likelyPromoDollarCurrencyValueCols,
        True,
        False,
        True,
    )
    paramDict, df = detect_column(
        df,
        paramDict,
        monetaryNoPromoDollarCurrencyName,
        monetaryNoPromoDollarCurrencyStemDict,
        monetaryNoPromoDollarCurrencyColFound,
        likelyNoPromoDollarCurrencyValueCols,
        True,
        False,
        True,
    )
    paramDict, df = detect_column(
        df,
        paramDict,
        monetaryPromoLocalCurrencyName,
        monetaryPromoLocalCurrencyStemDict,
        monetaryPromoLocalCurrencyColFound,
        likelyPromoLocalCurrencyValueCols,
        True,
        False,
        True,
    )
    paramDict, df = detect_column(
        df,
        paramDict,
        monetaryNoPromoLocalCurrencyName,
        monetaryNoPromoLocalCurrencyStemDict,
        monetaryNoPromoLocalCurrencyColFound,
        likelyNoPromoLocalCurrencyValueCols,
        True,
        False,
        True,
    )
    if paramDict[monetaryColFound] or paramDict.get(
        namingParams["cogsColFound"], False
    ):
        pass
    else:
        paramDict[namingParams["impossibleToProcessFile"]] = True
    return df, paramDict


def find_discount_and_cogs_columns(df, paramDict):
    """
    we try to find the columns that contain the dollar, the value and the date metrics
    based on stem matching. First we check if we already have the right columns
    """
    namingParams = get_naming_params()
    monetaryName = namingParams["monetaryLocalCurrencyName"]
    discountName = namingParams["discountName"]
    netOfDiscountName = namingParams["netOfDiscountName"]
    cogsName = namingParams["cogsName"]
    marginName = namingParams["marginName"]
    monetaryColFound = namingParams["monetaryLocalCurrencyColFound"]
    impossibleToProcessFile = namingParams["impossibleToProcessFile"]
    likelyDiscountCols = namingParams["likelyDiscountCols"]
    likelyNetOfDiscountCols = namingParams["likelyNetOfDiscountCols"]
    likelyCogsCols = namingParams["likelyCogsCols"]
    likelyMarginCols = namingParams["likelyMarginCols"]
    discountColFound = namingParams["discountColFound"]
    netOfDiscountColFound = namingParams["netOfDiscountColFound"]
    cogsColFound = namingParams["cogsColFound"]
    marginColFound = namingParams["marginColFound"]
    discountStemDict = namingParams["discountStemDict"]
    netOfDiscountStemDict = namingParams["netOfDiscountStemDict"]
    cogsStemDict = namingParams["cogsStemDict"]
    marginStemDict = namingParams["marginStemDict"]
    indirectCostsName = namingParams["indirectCostsName"]
    indirectCostsStemDict = namingParams["indirectCostsStemDict"]
    indirectCostsColFound = namingParams["indirectCostsColFound"]
    likelyIndirectCostsCols = namingParams["likelyIndirectCostsCols"]
    netMarginName = namingParams["netMarginName"]
    netMarginStemDict = namingParams["netMarginStemDict"]
    netMarginColFound = namingParams["netMarginColFound"]
    likelyNetMarginCols = namingParams["likelyNetMarginCols"]
    paramDict[namingParams["foundColsArray"]] = []
    paramDict, df = detect_column(
        df,
        paramDict,
        discountName,
        discountStemDict,
        discountColFound,
        likelyDiscountCols,
        True,
        False,
        True,
    )
    paramDict, df = detect_column(
        df,
        paramDict,
        netOfDiscountName,
        netOfDiscountStemDict,
        netOfDiscountColFound,
        likelyNetOfDiscountCols,
        True,
        False,
        True,
    )
    paramDict, df = detect_column(
        df,
        paramDict,
        indirectCostsName,
        indirectCostsStemDict,
        indirectCostsColFound,
        likelyIndirectCostsCols,
        True,
        False,
        True,
    )
    paramDict, df = detect_column(
        df,
        paramDict,
        netMarginName,
        netMarginStemDict,
        netMarginColFound,
        likelyNetMarginCols,
        True,
        False,
        True,
    )
    paramDict, df = detect_column(
        df,
        paramDict,
        cogsName,
        cogsStemDict,
        cogsColFound,
        likelyCogsCols,
        True,
        False,
        True,
    )
    paramDict, df = detect_column(
        df,
        paramDict,
        marginName,
        marginStemDict,
        marginColFound,
        likelyMarginCols,
        True,
        False,
        True,
    )
    columns_status = [
        (monetaryName, paramDict.get(monetaryColFound)),
        (discountName, paramDict.get(discountColFound)),
        (netOfDiscountName, paramDict.get(netOfDiscountColFound)),
        (cogsName, paramDict.get(cogsColFound)),
        (marginName, paramDict.get(marginColFound)),
    ]
    found_cols = [name for name, found in columns_status if found]
    missing_cols = [name for name, found in columns_status if not found]
    logger.debug("Found monetary columns: %s", ", ".join(found_cols) or "none")
    logger.debug("Missing monetary columns: %s", ", ".join(missing_cols) or "none")
    columns, schema = utils.get_schema_and_column_names(df)
    if cogsName in columns and discountName in columns:
        df = insert_calculated_difference_column(
            df, monetaryName, discountName, netOfDiscountName
        )
        df = insert_calculated_difference_column(
            df, netOfDiscountName, cogsName, marginName
        )
    elif cogsName in columns:
        df = insert_calculated_difference_column(df, monetaryName, cogsName, marginName)
    elif discountName in columns:
        df = insert_calculated_difference_column(
            df, monetaryName, discountName, netOfDiscountName
        )
    if marginName in columns and indirectCostsName in columns:
        df = insert_calculated_difference_column(
            df, marginName, indirectCostsName, netMarginName
        )
    baseline_found = paramDict.get(monetaryColFound) or paramDict.get(cogsColFound)
    paramDict[impossibleToProcessFile] = not baseline_found
    return df, paramDict


def find_date_and_period_columns(df, paramDict):
    """
    we try to find the columns that contain the dollar, the value and the date metrics
    based on stem matching. First we check if we already have the right columns
    """
    namingParams = get_naming_params()
    dateName = namingParams["dateName"]
    periodName = namingParams["periodName"]
    likelyDateCols = namingParams["likelyDateCols"]
    likelyPeriodCols = namingParams["likelyPeriodCols"]
    periodName = namingParams["periodName"]
    dateColFound = namingParams["dateColFound"]
    periodColFound = namingParams["periodColFound"]
    dateStemDict = namingParams["dateStemDict"]
    periodStemDict = namingParams["periodStemDict"]
    paramDict[namingParams["foundColsArray"]] = []
    paramDict[namingParams["impossibleToProcessFile"]] = False
    errorMessageType = namingParams["errorMessageType"]
    loadDataTabKey = namingParams["loadDataTab"]
    paramDict, df = detect_column(
        df,
        paramDict,
        periodName,
        periodStemDict,
        periodColFound,
        likelyPeriodCols,
        False,
        False,
        False,
    )
    paramDict, df = detect_column(
        df,
        paramDict,
        dateName,
        dateStemDict,
        dateColFound,
        likelyDateCols,
        False,
        True,
        False,
    )
    if paramDict[periodColFound]:
        try:
            df = df.with_columns(
                pl.col(periodName).str.to_uppercase().alias(periodName)
            )
        except Exception as e:  # noqa: BLE001
            logging.exception(e)
            e = print_error_details(e)
            paramDict = add_app_message_to_paramdict(
                e,
                errorMessageType,
                loadDataTabKey,
                paramDict,
                isMessage=True,
                isToast=True,
                colNumber=0,
            )
    elif paramDict[dateColFound]:
        pass
    else:
        paramDict[namingParams["impossibleToProcessFile"]] = True
    return df, paramDict


def manage_trailing_minus(df: pl.LazyFrame, column: str) -> pl.LazyFrame:
    # Check if the column is in the schema
    columns, schema = utils.get_schema_and_column_names(df)
    if column not in schema:
        notifier.warning(f"Column '{column}' not found. Skipping.")
        return df

    # If the column is not a string, skip the fix
    if schema[column] != pl.Utf8:
        pass
        return df

    # If it's string, then apply your trailing-minus fix
    try:
        updated_df = df.with_columns(
            pl.col(column)
            .str.replace(r"^(.+)([-+])$", r"$2$1")  # move trailing sign to front
            .cast(pl.Float64)
            .alias(column)
        )

        notifier.caption(
            f"The **{column}** column was converted from trailing sign (e.g. `20-`) "
            "to leading sign (e.g. `-20`) and cast to float."
        )
        return updated_df

    except Exception as e:
        logging.exception(e)
        notifier.warning(f"Could not manage trailing minus for column `{column}`: {e}")
        return df


def check_for_string_metric_cols(df, paramDict):
    """
    this check if there are "numeric" columns with names such as "amount", "units", and so on
    that are in string format for some reason (for instance trailing minus in SAP negative values)
    and then it can modify the columns and make them numeric
    """
    namingParams = get_naming_params()
    configParams = get_config_params()
    unitsStemDict = namingParams["unitsStemDict"]
    volumeStemDict = namingParams["volumeStemDict"]
    monetaryLocalCurrencyStemDict = namingParams["monetaryLocalCurrencyStemDict"]
    discountStemDict = namingParams["discountStemDict"]
    cogsStemDict = namingParams["cogsStemDict"]
    stemArray = namingParams["stemArray"]
    notStemArray = namingParams["notStemArray"]
    stemDict = namingParams["stemDict"]
    stemDict = configParams[stemDict]
    columns, schema = utils.get_schema_and_column_names(df)
    numericDictArray = [
        unitsStemDict,
        volumeStemDict,
        monetaryLocalCurrencyStemDict,
        discountStemDict,
        cogsStemDict,
    ]
    schemaDict = {}
    schemaDict = dict(df.collect_schema())
    for column in columns:
        is_string = schemaDict[column]
        if is_string:
            for wordDict in numericDictArray:
                if wordDict in stemDict:
                    if column in stemDict[wordDict][stemArray]:
                        if column not in stemDict[wordDict][notStemArray]:
                            df = manage_trailing_minus(df, column)
                        else:
                            pass
                    else:
                        pass
    return df, paramDict


def delete_rows_with_all_zeroes(df, paramDict):
    """
    no need to keep rows where both amount and quantity are zero
    we do not do this for ROI calculation because otherwise the division is wrong
    we also drop all the rows where the amount and the unit column have opposite sign
    """
    namingParams = get_naming_params()
    unitsName = namingParams["unitsName"]
    volumeName = namingParams["volumeName"]
    monetaryName = namingParams["monetaryLocalCurrencyName"]
    unitsColFound = namingParams["unitsColFound"]
    volumeColFound = namingParams["volumeColFound"]
    metConditionValue = namingParams["metConditionValue"]
    monetaryColFound = namingParams["monetaryLocalCurrencyColFound"]
    isunitsColFound = paramDict[unitsColFound]
    isvolumeColFound = paramDict[volumeColFound]
    ismonetaryColFound = paramDict[monetaryColFound]
    if isunitsColFound and ismonetaryColFound:
        df = df.filter(
            ((pl.col(unitsName) != 0) | (pl.col(monetaryName) != 0))
            & (
                ((pl.col(unitsName) >= 0) & (pl.col(monetaryName) >= 0))
                | ((pl.col(unitsName) <= 0) & (pl.col(monetaryName) <= 0))
            )
        )
    if isvolumeColFound and ismonetaryColFound:
        df = df.filter(
            ((pl.col(volumeName) != 0) | (pl.col(monetaryName) != 0))
            & (
                ((pl.col(volumeName) >= 0) & (pl.col(monetaryName) >= 0))
                | ((pl.col(volumeName) <= 0) & (pl.col(monetaryName) <= 0))
            )
        )
    if not utils.is_valid_lazyframe(df):
        if isunitsColFound:
            message = "The app automatically deletes the rows that have both amount and units column equal to zero or with opposite sign."
            paramDict = add_warning_message_in_load_data_tab(paramDict, message)
        if isvolumeColFound:
            message = "The app automatically deletes the rows that have both amount and volume column equal to zero or with opposite sign."
            paramDict = add_warning_message_in_load_data_tab(paramDict, message)
        message = "All rows have both the amount or the units/volume column equal to zero, or with opposite sign"
        paramDict = add_warning_message_in_load_data_tab(paramDict, message)
    elif ismonetaryColFound:
        df = df.filter(pl.col(monetaryName) != 0)
    return df


def clean_PL_rows(dfCopy, paramDict, chartDict):
    """
    if there is scenario data in the dataset, we take out the PL rows in order to show time line trend data
    """
    namingParams = get_naming_params()
    configParams = get_config_params()
    planStemArray = configParams[namingParams["planStemArray"]]
    timelineChart = namingParams["timelineChart"]
    selectedPeriods = namingParams["selectedPeriods"]
    areaChart = namingParams["areaChart"]
    multitierColumnChart = namingParams["multitierColumnChart"]
    horizontalWaterfallChart = namingParams["horizontalWaterfallChart"]
    stackedColumnChart = namingParams["stackedColumnChart"]
    trendComparisonByPeriodChart = namingParams["trendComparisonByPeriodChart"]
    periodName = namingParams["periodName"]
    scenarioName = namingParams["scenarioName"]
    mostRecentDateKey = namingParams["mostRecentDate"]
    pyName = namingParams["pyName"]
    plName = namingParams["plName"]
    fcName = namingParams["fcName"]
    acName = namingParams["acName"]
    dateName = namingParams["dateName"]
    metConditionValue = namingParams["metConditionValue"]
    comparePeriods = namingParams["comparePeriods"]
    compareScenariosOrPeriods = namingParams["compareScenariosOrPeriods"]
    compareWithYearBefore = namingParams["compareWithYearBefore"]
    periodColFound = namingParams["periodColFound"]
    filterDates = namingParams["filterDates"]
    notMetConditionValue = namingParams["notMetConditionValue"]
    chosenChart = namingParams["chosenChart"]
    if chosenChart in chartDict:
        chosenChart = chartDict[chosenChart]
    keepFurePlanValues = notMetConditionValue
    if (
        compareScenariosOrPeriods in chartDict
        and chartDict[compareScenariosOrPeriods] == comparePeriods
    ):
        df = duplicate_dataframe(dfCopy)
        if isinstance(df, pl.DataFrame):
            df = df.lazy()
        uniquePeriods = get_periods_array(df)
        isExpectedData, planName = check_if_plan_or_py(uniquePeriods)
        if plName in uniquePeriods and isExpectedData:
            dfAC = df.filter(pl.col(periodName) == acName)
            mostRecentACDate = dfAC.select(pl.col(dateName).max()).item()
            dfPL = df.filter(pl.col(periodName) == plName)
            mostRecentPLDate = dfPL.select(pl.col(dateName).max()).item()
            if (
                mostRecentPLDate > mostRecentACDate
            ):  # and chosenChart in [stackedColumnChart]:
                if (
                    compareWithYearBefore in chartDict
                    and not chartDict[compareWithYearBefore]
                ):
                    df = df.filter(
                        (pl.col(periodName).is_in([acName]))
                        | (pl.col(dateName) > mostRecentACDate)
                    ).with_columns(pl.col(periodName).alias(scenarioName))
                else:
                    df = df.filter(~pl.col(periodName).is_in([plName, fcName]))
            else:
                df = df.filter(~pl.col(periodName).is_in([plName, fcName]))
            df = drop_columns(df, [periodName])
            paramDict[periodColFound], chartDict[filterDates] = (
                notMetConditionValue,
                notMetConditionValue,
            )
            return df.lazy() if isinstance(df, pl.DataFrame) else df
        else:
            message = "Unable to find and delete PL/Budget rows"
            paramDict = add_warning_message_in_period_options_tab(paramDict, message)
            message = "PL/Budget rows must be named with one of the following stems in upper or lower case"
            paramDict = add_warning_message_in_period_options_tab(paramDict, message)
            paramDict = add_write_message_in_period_options_tab(
                paramDict, planStemArray
            )
            message = (
                "Rename PL/Budget rows or set Compare widget to Scenarios and rerun"
            )
            paramDict = add_warning_message_in_period_options_tab(paramDict, message)
            return dfCopy.lazy() if isinstance(dfCopy, pl.DataFrame) else dfCopy
    else:
        return dfCopy.lazy() if isinstance(dfCopy, pl.DataFrame) else dfCopy


def set_dataframe_to_compare_periods(dfCopy, paramDict, chartDict):
    namingParams = get_naming_params()
    comparePeriods = namingParams["comparePeriods"]
    compareScenariosOrPeriods = namingParams["compareScenariosOrPeriods"]
    periodName = namingParams["periodName"]
    if (
        compareScenariosOrPeriods in chartDict
        and chartDict[compareScenariosOrPeriods] == comparePeriods
    ):
        df = clean_PL_rows(dfCopy, paramDict, chartDict)
        return df
    else:
        return dfCopy


def check_if_date_column_exists(df, paramDict, chartDict):
    """Return a dataset for time filtering.

    When a date column is present we duplicate ``df`` so date filters can be
    applied independently of the main pipeline.  If no date column exists but a
    period column does, a duplicate is still returned to allow period based
    operations to continue.  Otherwise an empty ``LazyFrame`` is produced.
    """
    namingParams = get_naming_params()
    dateColFound = namingParams["dateColFound"]
    periodColFound = namingParams["periodColFound"]
    filterDates = namingParams["filterDates"]
    metConditionValue = namingParams["metConditionValue"]
    if dateColFound in paramDict and paramDict[dateColFound]:
        if (
            not paramDict[periodColFound]
            or filterDates in chartDict
            and chartDict[filterDates] == metConditionValue
        ):
            dfDates = duplicate_dataframe(df)
        else:
            dfDates = pl.LazyFrame()
    elif paramDict.get(periodColFound):
        dfDates = duplicate_dataframe(df)
    else:
        dfDates = pl.LazyFrame()
    return dfDates


def filter_dataframe_in_date_range(df, chartDict):
    """
    filtering the dataframe based on the chosen date range
    """
    namingParams = get_naming_params()
    dateName = namingParams["dateName"]
    dateRangeArray = namingParams["dateRangeArray"]
    filterDates = namingParams["filterDates"]
    if filterDates in chartDict and chartDict[filterDates]:
        dateRangeArray = chartDict[dateRangeArray]
        min_date = pl.Series([dateRangeArray[0]]).str.to_datetime()[0]
        max_date = pl.Series([dateRangeArray[1]]).str.to_datetime()[0]
        if min_date < max_date:
            if not isinstance(df, (pl.DataFrame, pl.LazyFrame)):
                df = pl.DataFrame(df)
            df = df.filter(
                (pl.col(dateName) >= min_date) & (pl.col(dateName) <= max_date)
            )
    return df


def get_comparison_period(paramDict, chartDict):
    """
    we somehow get the time metric (by month, by year, by week,by quarter, by day)
    on how to split the dataset along time
    """
    namingParams = get_naming_params()
    datePeriodName = namingParams["datePeriodName"]
    weekName = namingParams["weekName"]
    monthName = namingParams["monthName"]
    quarterName = namingParams["quarterName"]
    yearName = namingParams["yearName"]
    periodChoice = namingParams["periodChoice"]
    metricDict = {
        "W": weekName,
        "M": monthName,
        "Q": quarterName,
        "Y": yearName,
    }
    if periodChoice in chartDict and chartDict[periodChoice]:
        paramDict[datePeriodName] = chartDict[periodChoice]
    else:
        paramDict[datePeriodName] = None
    return paramDict


def calculate_fiscal_year_lazy(date_col, start_month):
    """Calculate fiscal year based on the start month."""
    return (
        pl.when(pl.col(date_col).dt.month() >= start_month)
        .then(pl.col(date_col).dt.year() + 1)
        .otherwise(pl.col(date_col).dt.year())
    )


def calculate_fiscal_quarter_lazy(month_col, start_month):
    """Calculate fiscal quarter based on the start month."""
    shifted_month = (month_col - start_month) % 12 + 1
    return ((shifted_month - 1) // 3 + 1).alias("FQ")


def ensure_datetime_column(lf, date_name, date_format):
    """
    Ensure the specified column is in Datetime format.
    If not, convert it from string using the given date format.
    """
    columns, schema = utils.get_schema_and_column_names(lf)
    # Check the schema to determine the column's data type
    if schema[date_name] != pl.Datetime:
        # If not Datetime, cast to string and parse as Datetime
        lf = lf.with_columns(
            pl.col(date_name)
            .cast(pl.Utf8)
            .str.strptime(pl.Datetime, format=date_format, strict=False)
            .alias(date_name)
        )
    return lf


def detect_date_format(
    lf: pl.LazyFrame, date_name: str, sample_size: int = 5, default: str = "%Y-%m-%d"
) -> str:
    """Infer the date format for ``date_name`` by sampling a few rows."""
    _, schema = utils.get_schema_and_column_names(lf)
    dtype = schema.get(date_name) if schema else None
    if dtype in (pl.Datetime, pl.Date):
        return default

    try:
        sample = (
            lf.select(pl.col(date_name).drop_nulls())
            .limit(sample_size)
            .collect(engine="streaming")
        )
    except Exception as e:
        try:  # pragma: no cover - logging only
            notifier.error("Something went wrong.")
        except Exception as e:  # pragma: no cover - notifier unavailable
            logging.exception(e)
        return default

    candidates = ["%Y-%m-%d", "%m/%d/%Y", "%m-%d-%Y", "%d/%m/%Y", "%d-%m-%Y"]
    for fmt in candidates:
        parsed = sample.select(
            pl.col(date_name).str.strptime(pl.Date, fmt, strict=False)
        )
        if parsed.filter(pl.col(date_name).is_null()).height == 0:
            return fmt

    return default


def assign_fiscal_period(df, paramDict, chartDict):
    namingParams = get_naming_params()
    dateName = namingParams["dateName"]
    dateFormat = detect_date_format(df, dateName)
    periodName = namingParams["periodName"]
    fiscalStartMonth = namingParams["fiscalStartMonth"]
    quarterName = namingParams["quarterName"]
    yearName = namingParams["yearName"]
    datePeriodName = namingParams["datePeriodName"]
    startMonth = chartDict[fiscalStartMonth]
    period = paramDict[datePeriodName]
    # Ensure the date column is in datetime format
    # Ensure the column is a string before applying .str.strptime

    df = ensure_datetime_column(df, dateName, dateFormat)

    if period == yearName:
        # Calculate fiscal year
        df = df.with_columns(
            calculate_fiscal_year_lazy(dateName, startMonth).alias(periodName)
        ).with_columns(
            pl.format("’FY{}", pl.col(periodName).cast(pl.Utf8).str.slice(-2)).alias(
                periodName
            )
        )
    elif period == quarterName:
        # Calculate fiscal quarter
        df = df.with_columns(
            calculate_fiscal_year_lazy(dateName, startMonth).alias("FY"),
            calculate_fiscal_quarter_lazy(pl.col(dateName).dt.month(), startMonth),
        ).with_columns(
            pl.format(
                "’{}’FQ{}", pl.col("FY").cast(pl.Utf8).str.slice(-2), pl.col("FQ")
            ).alias(periodName)
        )

    df = drop_columns(df, ["FY", "FQ"])
    return df


def convert_date_to_period(df, paramDict, chartDict):
    """
    if we find a date column, we convert it into period based on the requested period
    """
    namingParams = get_naming_params()
    weekName = namingParams["weekName"]
    monthName = namingParams["monthName"]
    quarterName = namingParams["quarterName"]
    yearName = namingParams["yearName"]
    periodName = namingParams["periodName"]
    datePeriodName = namingParams["datePeriodName"]
    dateName = namingParams["dateName"]
    periodColFound = namingParams["periodColFound"]
    metConditionValue = namingParams["metConditionValue"]
    notMetConditionValue = namingParams["notMetConditionValue"]
    fiscalYear = namingParams["fiscalYear"]
    period = paramDict[datePeriodName]
    # Ensure date column is in Datetime format before applying .dt operations
    date_format = detect_date_format(df, dateName)
    df = ensure_datetime_column(df, dateName, date_format)
    if 1 == 1:  # try:
        if (
            fiscalYear in chartDict
            and chartDict[fiscalYear]
            and period in [quarterName, yearName]
        ):
            df = assign_fiscal_period(df, paramDict, chartDict)
        else:
            if period == weekName:
                df = df.with_columns(
                    # Combine formatting and prefix in one operation
                    pl.format(
                        "’{}",
                        pl.col(dateName).dt.strftime("%y-W%V"),  # Format as year-week
                    ).alias(periodName)
                )
            elif period == monthName:
                df = df.with_columns(
                    [
                        # Compute month and year inline
                        pl.format(
                            "’{}-{}",
                            pl.col(dateName)
                            .dt.year()
                            .cast(pl.Utf8)
                            .str.slice(-2),  # Year (last 2 digits)
                            pl.col(dateName)
                            .dt.month()
                            .cast(pl.Utf8)
                            .str.zfill(2),  # Month (2 digits)
                        ).alias(periodName)
                    ]
                )
            elif period == quarterName:
                df = df.with_columns(
                    pl.format(
                        "’{}-Q{}",
                        pl.col(dateName).dt.strftime(
                            "%y"
                        ),  # Last two digits of the year
                        ((pl.col(dateName).dt.month() - 1) // 3 + 1).cast(
                            pl.Utf8
                        ),  # Calculate quarter
                    ).alias(periodName)
                )
            elif period == yearName:
                df = df.with_columns(
                    pl.format(
                        "’{}", pl.col(dateName).dt.year().cast(pl.Utf8).str.slice(-2)
                    ).alias(periodName)
                )
            else:
                df = df.with_columns(
                    pl.format(
                        "’{}", pl.col(dateName).dt.year().cast(pl.Utf8).str.slice(-2)
                    ).alias(periodName)
                )
                paramDict[datePeriodName] = yearName
        paramDict[periodColFound] = metConditionValue
    else:  # except:
        paramDict[periodColFound] = notMetConditionValue
    return df, paramDict


def change_date_field_to_relevant_period(df, paramDict, chartDict):
    """
    we convert the date column (if it exists) in a period column.
    we look for a period column in the date column does not exist
    If we found a period column, we delete the data columns
    """
    namingParams = get_naming_params()
    periodName = namingParams["periodName"]
    dateName = namingParams["dateName"]
    likelyPeriodCols = namingParams["likelyPeriodCols"]
    periodColFound = namingParams["periodColFound"]
    numericTypesArray = [
        pl.Int8,
        pl.Int16,
        pl.Int32,
        pl.Int64,
        pl.UInt8,
        pl.UInt16,
        pl.UInt32,
        pl.UInt64,
        pl.Float32,
        pl.Float64,
    ]
    columns, schema = utils.get_schema_and_column_names(df)
    if dateName in columns and not paramDict[periodColFound]:
        df, paramDict = convert_date_to_period(df, paramDict, chartDict)
    columns, schema = utils.get_schema_and_column_names(df)
    if paramDict[periodColFound]:
        df = df.filter(pl.col(periodName).is_not_null())
    columns, schema = utils.get_schema_and_column_names(df)
    if periodName in columns and schema.get(periodName) in numericTypesArray:
        df = df.with_columns(pl.col(periodName).cast(pl.Int32).alias(periodName))
    return df, paramDict


def check_if_can_process_dates(df, paramDict):
    namingParams = get_naming_params()
    impossibleToProcessFile = namingParams["impossibleToProcessFile"]
    dateColFound = namingParams["dateColFound"]
    notMetConditionValue = namingParams["notMetConditionValue"]
    metConditionValue = namingParams["metConditionValue"]
    impossibleToProcessFile = paramDict[impossibleToProcessFile]
    isDateColFound = paramDict[dateColFound]
    processDates = notMetConditionValue
    if not impossibleToProcessFile and utils.is_valid_lazyframe(df) and isDateColFound:
        processDates = metConditionValue
    return processDates


def set_date_parameters(df, paramDict):
    namingParams = get_naming_params()
    notMetConditionValue = namingParams["notMetConditionValue"]
    compareWithYearBefore = notMetConditionValue
    paramDict, mostRecentDate, leastRecentDate, periodLengthInMonths = (
        get_period_length(df, paramDict, False)
    )
    periodLengthInMonths = int(round(periodLengthInMonths, 0))
    mostRecentMonth = mostRecentDate.strftime("%B")
    return compareWithYearBefore, paramDict, periodLengthInMonths, mostRecentMonth


def manage_date_filters(dfDates, chartDict, paramDict, periodLengthInMonths):
    namingParams = get_naming_params()
    filterDates = namingParams["filterDates"]
    if filterDates in chartDict and chartDict[filterDates]:
        (
            copyDict,
            mostRecentDatesDate,
            leastRecentDatesDate,
            periodDatesLengthInMonths,
        ) = get_period_length(dfDates, paramDict, True)
        periodDatesLengthInMonths = int(round(periodLengthInMonths, 0))
        numberOfMonths = max(periodDatesLengthInMonths, periodLengthInMonths)
    else:
        numberOfMonths = periodLengthInMonths
    return numberOfMonths


def check_if_more_than_twenty_four_months(paramDict, numberOfMonths):
    namingParams = get_naming_params()
    notMetConditionValue = namingParams["notMetConditionValue"]
    metConditionValue = namingParams["metConditionValue"]
    twentyfourMonthsInDataset = namingParams["twentyfourMonthsInDataset"]
    paramDict[twentyfourMonthsInDataset] = notMetConditionValue
    if numberOfMonths >= 24:
        paramDict[twentyfourMonthsInDataset] = metConditionValue
    return paramDict


def check_compare_with_year_before(chartDict, paramDict, periodLengthInMonths):
    namingParams = get_naming_params()
    compareWithYearBeforeKey = namingParams["compareWithYearBefore"]
    setTimePeriodTabKey = namingParams["setTimePeriodTab"]
    datePeriodName = namingParams["datePeriodName"]
    monthName = namingParams["monthName"]
    quarterName = namingParams["quarterName"]
    notMetConditionValue = namingParams["notMetConditionValue"]
    infoMessageType = namingParams["infoMessageType"]
    setTimePeriodTabLabel = namingParams["setTimePeriodTabLabel"]
    if compareWithYearBeforeKey in chartDict and chartDict[compareWithYearBeforeKey]:
        if (
            datePeriodName in paramDict
            and paramDict[datePeriodName] == monthName
            and periodLengthInMonths <= 13
        ) or (
            datePeriodName in paramDict
            and paramDict[datePeriodName] == quarterName
            and periodLengthInMonths <= 23
        ):
            chartDict[compareWithYearBeforeKey] = notMetConditionValue
            message = (
                "Only "
                + str(periodLengthInMonths)
                + " months in dataset. 'Compare with rolling period' set to False"
            )
            paramDict = add_app_message_to_paramdict(
                message,
                infoMessageType,
                setTimePeriodTabKey,
                paramDict,
                isMessage=True,
                isToast=True,
                colNumber=1,
            )
    return chartDict, paramDict


def process_yearly_aggregation(df, dfDates, paramDict, chartDict):
    """
    we want to compare the most recent 12 months to the 12 months of the year before
    """
    processDates = check_if_can_process_dates(df, paramDict)
    periodLengthInMonths, mostRecentMonth = False, False
    if processDates:
        compareWithYearBefore, paramDict, periodLengthInMonths, mostRecentMonth = (
            set_date_parameters(df, paramDict)
        )
        numberOfMonths = manage_date_filters(
            dfDates, chartDict, paramDict, periodLengthInMonths
        )
        paramDict = check_if_more_than_twenty_four_months(paramDict, numberOfMonths)
        chartDict, paramDict = check_compare_with_year_before(
            chartDict, paramDict, periodLengthInMonths
        )
    return chartDict, paramDict, periodLengthInMonths, mostRecentMonth, processDates


def find_columns_and_manage_dates(df, paramDict, chartDict):
    """
    runs profiler and finds value and date columns
    """
    namingParams = get_naming_params()
    errorMessageType = namingParams["errorMessageType"]
    loadDataTabKey = namingParams["loadDataTab"]
    df, paramDict = check_for_string_metric_cols(df, paramDict)
    df, paramDict = find_volume_columns(df, paramDict)
    df, paramDict = find_monetary_columns(df, paramDict)
    df, paramDict = find_discount_and_cogs_columns(df, paramDict)
    df, paramDict = find_distribution_metric_columns(df, paramDict)
    df, paramDict = find_checkout_columns(df, paramDict)
    df, paramDict = find_visits_columns(df, paramDict)
    df = delete_rows_with_all_zeroes(df, paramDict)
    dfPlan = pl.LazyFrame()
    if utils.is_valid_lazyframe(df):
        df = set_dataframe_to_compare_periods(df, paramDict, chartDict)
        dfDates = check_if_date_column_exists(df, paramDict, chartDict)
        df = filter_dataframe_in_date_range(df, chartDict)
        dfDates = filter_dataframe_in_date_range(dfDates, chartDict)
        paramDict = get_comparison_period(paramDict, chartDict)
        df, paramDict = change_date_field_to_relevant_period(df, paramDict, chartDict)
        chartDict, paramDict, periodLengthInMonths, mostRecentMonth, processDates = (
            process_yearly_aggregation(df, dfDates, paramDict, chartDict)
        )
    else:
        dfDates = pl.LazyFrame()
        dfPlan = pl.LazyFrame()
        message = "Empty dataset, unable to process"
        paramDict = add_app_message_to_paramdict(
            message,
            errorMessageType,
            loadDataTabKey,
            paramDict,
            isMessage=True,
            isToast=True,
            colNumber=0,
        )
        periodLengthInMonths, mostRecentMonth, processDates = None, None, None
    return (
        df,
        dfDates,
        paramDict,
        chartDict,
        periodLengthInMonths,
        mostRecentMonth,
        processDates,
    )


def change_time_aggregation(df, paramDict, chartDict, newTimeAggregation, automateDict):
    """
    if we have only one year in the dataframe the time aggregation parameter cannot be year. So we force it to month
    """
    namingParams = get_naming_params()
    periodName = namingParams["periodName"]
    datePeriodName = namingParams["datePeriodName"]
    monthName = namingParams["monthName"]
    yearName = namingParams["yearName"]
    quarterName = namingParams["quarterName"]
    dateName = namingParams["dateName"]
    workColumn = namingParams["workColumn"]
    periodColFound = namingParams["periodColFound"]
    filterDates = namingParams["filterDates"]
    metConditionValue = namingParams["metConditionValue"]
    compareWithYearBeforeKey = namingParams["compareWithYearBefore"]
    periodToDateKey = namingParams["periodToDate"]
    notMetConditionValue = namingParams["notMetConditionValue"]
    metConditionValue = namingParams["metConditionValue"]
    changeAggregationPeriod = namingParams["changeAggregationPeriod"]
    changedTimeAggregation = namingParams["changedTimeAggregation"]
    from modules.layout.set_up_widgets import get_period_aggregation_change_choice

    message = notMetConditionValue
    periods = get_periods_array(df)
    paramDict, mostRecentDate, leastRecentDate, periodLengthInMonths = (
        get_period_length(df, paramDict, False)
    )
    if paramDict[datePeriodName] == yearName:
        if not (
            filterDates in chartDict and chartDict[filterDates] == metConditionValue
        ):
            if newTimeAggregation == monthName:
                chartDict = get_period_aggregation_change_choice(
                    chartDict, monthName, automateDict
                )
                if chartDict[changeAggregationPeriod]:
                    message = (
                        "Dataset contains "
                        + str(int(round(periodLengthInMonths, 0)))
                        + " months which is less than 13 months."
                    )
                    paramDict[datePeriodName] = monthName
                    chartDict[compareWithYearBeforeKey] = notMetConditionValue
                    chartDict[periodToDateKey] = notMetConditionValue
                    df = df.with_columns(
                        [
                            pl.col(dateName)
                            .dt.month()
                            .cast(pl.Utf8)
                            .str.zfill(2)
                            .alias(periodName),
                            pl.col(dateName).dt.year().alias(workColumn),
                        ]
                    ).with_columns(
                        pl.concat_str(
                            [
                                pl.lit("’"),
                                pl.col(workColumn).cast(pl.Utf8).str.slice(-2),
                                pl.lit("-"),
                                pl.col(periodName),
                            ]
                        ).alias(periodName)
                    )
                    message = (
                        message
                        + " 'Date Aggregation' parameter set to month. You can set the parameter back to year in the Period Options tab."
                    )
                    paramDict[changedTimeAggregation] = metConditionValue
            elif newTimeAggregation == quarterName:
                chartDict = get_period_aggregation_change_choice(
                    chartDict, monthName, automateDict
                )
                if chartDict[changeAggregationPeriod]:
                    message = (
                        "Dataset contains "
                        + str(int(round(periodLengthInMonths, 0)))
                        + " months which is less than 24 months."
                    )
                    paramDict[datePeriodName] = quarterName
                    chartDict[compareWithYearBeforeKey] = notMetConditionValue
                    chartDict[periodToDateKey] = notMetConditionValue
                    df = df.with_columns(
                        pl.format(
                            "’{}-Q{}",
                            pl.col(dateName).dt.strftime("%y"),
                            ((pl.col(dateName).dt.month() - 1) // 3 + 1).cast(pl.Utf8),
                        ).alias(periodName)
                    )
                    message = (
                        message
                        + " 'Date Aggregation' parameter set to quarter. You can set the parameter back to year in the Period Options tab."
                    )
                    paramDict[changedTimeAggregation] = metConditionValue
            if message:
                paramDict = add_warning_message_in_period_options_tab(
                    paramDict, message
                )
            df = drop_columns(df, [workColumn])
    return df, paramDict, chartDict


def show_message_most_recent_month_not_december(mostRecentMonth, paramDict, chartDict):
    namingParams = get_naming_params()
    mostRecentPeriod = namingParams["mostRecentPeriod"]
    setTimePeriodTabKey = namingParams["setTimePeriodTab"]
    warningMessageType = namingParams["warningMessageType"]
    setTimePeriodTabLabel = namingParams["setTimePeriodTabLabel"]
    fiscalYear = namingParams["fiscalYear"]
    if fiscalYear in chartDict and chartDict[fiscalYear]:
        pass
    elif mostRecentPeriod in chartDict and chartDict[mostRecentPeriod] == -1:
        message = (
            "Comparison set on 'Calendar year' but most recent month "
            + mostRecentMonth
            + ", not December."
        )
        paramDict = add_app_message_to_paramdict(
            message,
            warningMessageType,
            setTimePeriodTabKey,
            paramDict,
            isMessage=True,
            isToast=True,
            colNumber=1,
        )
        message = "You might be comparing periods of different length."
        paramDict = add_app_message_to_paramdict(
            message,
            warningMessageType,
            setTimePeriodTabKey,
            paramDict,
            isMessage=True,
            isToast=True,
            colNumber=1,
        )
        message = "Consider changing setting to 'Year-to-Date' or to 'Rolling Periods'."
        paramDict = add_app_message_to_paramdict(
            message,
            warningMessageType,
            setTimePeriodTabKey,
            paramDict,
            isMessage=True,
            isToast=False,
            colNumber=1,
        )
        message = (
            "Consider changing setting to 'Year-to-Date' or to 'Rolling Periods' in the "
            + setTimePeriodTabLabel
            + " tab."
        )
        paramDict = add_app_message_to_paramdict(
            message,
            warningMessageType,
            setTimePeriodTabKey,
            paramDict,
            isMessage=False,
            isToast=True,
            colNumber=1,
        )
    return paramDict


def show_message_less_than_twenty_four_months(periodLengthInMonths, paramDict):
    namingParams = get_naming_params()
    datePeriodName = namingParams["datePeriodName"]
    quarterName = namingParams["quarterName"]
    monthName = namingParams["monthName"]
    yearName = namingParams["yearName"]
    infoMessageType = namingParams["infoMessageType"]
    setTimePeriodTabKey = namingParams["setTimePeriodTab"]
    if (
        datePeriodName in paramDict
        and paramDict[datePeriodName] == yearName
        and periodLengthInMonths < 24
    ):
        message = (
            "Dataset contains only "
            + str(periodLengthInMonths)
            + " months. Rolling year calculation requires 24 months."
        )
        paramDict = add_app_message_to_paramdict(
            message,
            infoMessageType,
            setTimePeriodTabKey,
            paramDict,
            isMessage=True,
            isToast=True,
            colNumber=0,
        )
        message = "You might be comparing periods of different length. Consider changing setting to 'Year-to-Date'."
        paramDict = add_app_message_to_paramdict(
            message,
            infoMessageType,
            setTimePeriodTabKey,
            paramDict,
            isMessage=True,
            isToast=True,
            colNumber=0,
        )
    if (
        datePeriodName in paramDict
        and paramDict[datePeriodName] == quarterName
        and periodLengthInMonths < 15
    ):
        message = (
            "Dataset contains only "
            + str(periodLengthInMonths)
            + " months. Rolling quarter calculation requires 15 months."
        )
        paramDict = add_app_message_to_paramdict(
            message,
            infoMessageType,
            setTimePeriodTabKey,
            paramDict,
            isMessage=True,
            isToast=True,
            colNumber=0,
        )
        message = "You might be comparing periods of different length. Consider changing setting to 'Quarter-to-Date'."
        paramDict = add_app_message_to_paramdict(
            message,
            infoMessageType,
            setTimePeriodTabKey,
            paramDict,
            isMessage=True,
            isToast=True,
            colNumber=0,
        )
    if (
        datePeriodName in paramDict
        and paramDict[datePeriodName] == monthName
        and periodLengthInMonths < 13
    ):
        message = (
            "Dataset contains only "
            + str(periodLengthInMonths)
            + " months. Rolling month calculation requires 13 months."
        )
        paramDict = add_app_message_to_paramdict(
            message,
            infoMessageType,
            setTimePeriodTabKey,
            paramDict,
            isMessage=True,
            isToast=True,
            colNumber=0,
        )
        message = "You might be comparing periods of different length. Consider changing setting to 'Month-to-Date'."
        paramDict = add_app_message_to_paramdict(
            message,
            infoMessageType,
            setTimePeriodTabKey,
            paramDict,
            isMessage=True,
            isToast=True,
            colNumber=0,
        )
    return paramDict


def check_if_date_aggregation_is_year(
    df,
    chartDict,
    paramDict,
    periodLengthInMonths,
    mostRecentMonth,
    automateDict,
    processDates,
):
    namingParams = get_naming_params()
    datePeriodName = namingParams["datePeriodName"]
    yearName = namingParams["yearName"]
    monthName = namingParams["monthName"]
    quarterName = namingParams["quarterName"]
    decemberName = namingParams["decemberName"]
    periodToDateKey = namingParams["periodToDate"]
    compareWithYearBeforeKey = namingParams["compareWithYearBefore"]
    canPlotYearToYear = namingParams["canPlotYearToYear"]
    notMetConditionValue = namingParams["notMetConditionValue"]
    if processDates:
        if datePeriodName in paramDict and paramDict[datePeriodName] == yearName:
            if periodLengthInMonths <= 13:
                df, paramDict, chartDict = change_time_aggregation(
                    df, paramDict, chartDict, monthName, automateDict
                )
            elif periodLengthInMonths <= 23 and not chartDict[periodToDateKey]:
                df, paramDict, chartDict = change_time_aggregation(
                    df, paramDict, chartDict, quarterName, automateDict
                )
            elif mostRecentMonth != decemberName:
                if (
                    not chartDict[compareWithYearBeforeKey]
                    and not chartDict[periodToDateKey]
                ):
                    paramDict = show_message_most_recent_month_not_december(
                        mostRecentMonth, paramDict, chartDict
                    )
                if not chartDict[compareWithYearBeforeKey]:
                    chartDict[canPlotYearToYear] = notMetConditionValue
            if (
                compareWithYearBeforeKey in chartDict
                and chartDict[compareWithYearBeforeKey]
            ):
                paramDict = show_message_less_than_twenty_four_months(
                    periodLengthInMonths, paramDict
                )
    return chartDict, paramDict


def calculate_periods(
    df,
    paramDict,
    chartDict,
    tyYaDatesArray,
    session_manager: SessionManager | None = None,
):
    namingParams = get_naming_params()
    session_manager = session_manager or SessionManager()
    datePeriodName = namingParams["datePeriodName"]
    yearName = namingParams["yearName"]
    compareWithYearBeforeKey = namingParams["compareWithYearBefore"]
    periodToDateKey = namingParams["periodToDate"]
    if (
        paramDict[datePeriodName] == yearName
        and compareWithYearBeforeKey in chartDict
        and chartDict[compareWithYearBeforeKey]
    ):
        df, paramDict, tyYaDatesArray, chartDict = calculate_rolling_period(
            df, tyYaDatesArray, paramDict, chartDict
        )
        if periodToDateKey in chartDict and chartDict[periodToDateKey]:
            df, paramDict = calculate_period_to_date_year_ago(
                df, paramDict, session_manager=session_manager
            )
    elif periodToDateKey in chartDict and chartDict[periodToDateKey]:
        if paramDict[datePeriodName] == yearName:
            df, paramDict = calculate_period_to_date_year_ago(
                df, paramDict, session_manager=session_manager
            )
        elif (
            compareWithYearBeforeKey in chartDict
            and chartDict[compareWithYearBeforeKey]
        ):
            df, paramDict = calculate_period_to_date_year_ago(
                df, paramDict, session_manager=session_manager
            )
        else:
            df, paramDict = calculate_period_to_date_same_year(
                df, paramDict, session_manager=session_manager
            )
    return df, paramDict, tyYaDatesArray, chartDict


def group_this_year_and_year_ago(
    dfCopy,
    paramDict,
    chartDict,
    processDates,
    session_manager: SessionManager | None = None,
    preserve_date_col: bool = False,
):
    """Compare the latest 12 months to the same period a year ago.

    Parameters
    ----------
    dfCopy: pl.LazyFrame | pl.DataFrame
        Source dataframe.
    paramDict: dict
        Parameter dictionary used across data preparation.
    chartDict: dict
        Chart settings used by downstream modules.
    processDates: bool
        Whether the dataframe already contains calculated date periods.
    session_manager: SessionManager | None, optional
        Session manager instance.
    preserve_date_col: bool, optional
        When ``True`` the original date column is kept in ``df``.
    """
    namingParams = get_naming_params()
    tyYaDates = namingParams["tyYaDates"]
    dateName = namingParams["dateName"]
    tyYaDatesArray = []
    session_manager = session_manager or SessionManager()
    df = duplicate_dataframe(dfCopy)
    if processDates:
        df, paramDict, tyYaDatesArray, chartDict = calculate_periods(
            df, paramDict, chartDict, tyYaDatesArray, session_manager=session_manager
        )
        sortedtyYaDatesArray = sorted(tyYaDatesArray)
        paramDict[tyYaDates] = sortedtyYaDatesArray
    dfPlan = duplicate_dataframe(df)
    if not preserve_date_col:
        df = drop_columns(df, [dateName])
    return df, dfPlan, paramDict


def apply_filter_and_copy_df(df, selectedPeriodsArray, paramDict, chartDict):
    """
    if the users has requested comparison to the corresponding period of the year before, we check
    if we have that period in the datased
    """
    namingParams = get_naming_params()
    periodName = namingParams["periodName"]
    fcName = namingParams["fcName"]
    compareScenariosOrPeriods = namingParams["compareScenariosOrPeriods"]
    compareScenarios = namingParams["compareScenarios"]
    periodsArray = copy.deepcopy(selectedPeriodsArray)
    if (
        compareScenariosOrPeriods in chartDict
        and chartDict[compareScenariosOrPeriods] == compareScenarios
    ):
        # Duplicate the dataframe (lazy equivalent)
        dfPeriods = df.clone()

        # Filter df by periodsArray
        df = df.filter(pl.col(periodName).is_in(periodsArray))

        # Exclude rows where periodName is fcName
        df = df.filter(~pl.col(periodName).is_in([fcName]))

        # Append fcName to periodsArray if not present
        if fcName not in periodsArray:
            periodsArray.append(fcName)

        # Filter dfPeriods by the updated periodsArray
        dfPeriods = dfPeriods.filter(pl.col(periodName).is_in(periodsArray))

    else:
        # Filter df by periodsArray
        df = df.filter(pl.col(periodName).is_in(periodsArray))

        # Duplicate after filtering
        dfPeriods = df.clone()

        # Exclude rows where periodName is fcName
        df = df.filter(~pl.col(periodName).is_in([fcName]))

    return df, dfPeriods


def check_if_year_before_period_exists(sortedPeriods, mostRecentPeriodIndex, paramDict):
    """
    if the users has requested comparison to the corresponding period of the year before, we check
    if we have that period in the datased
    """
    namingParams = get_naming_params()
    datePeriodName = paramDict[namingParams["datePeriodName"]]
    weekName = namingParams["weekName"]
    monthName = namingParams["monthName"]
    quarterName = namingParams["quarterName"]
    metricDict = {
        weekName: 51,
        monthName: 11,
        quarterName: 3,
    }
    periods = copy.deepcopy(sortedPeriods)
    periods = periods[0:mostRecentPeriodIndex]
    if len(periods) >= metricDict[datePeriodName]:
        yearBeforePeriodIndex = metricDict[datePeriodName]
    else:
        yearBeforePeriodIndex = 0
    return yearBeforePeriodIndex


def transform_integer_periods(df, periodsArray, paramDict):
    """
    when importing from excel the period column is parsed as a huge integer
    """
    namingParams = get_naming_params()
    uploadedFileType = namingParams["uploadedFileType"]
    periodName = namingParams["periodName"]
    columns, schema = utils.get_schema_and_column_names(df)
    if uploadedFileType in paramDict and paramDict[uploadedFileType] == "xlsx":
        if schema.get(periodName) == pl.Datetime:
            try:
                cleanedperiodsArray = []
                for element in periodsArray:
                    element = dt.datetime.fromtimestamp(int(element) / 1e9)
                    cleanedperiodsArray.append(str(element.date()))
                periodsArray = cleanedperiodsArray
                df = df.with_columns(
                    pl.col(periodName).dt.strftime("%Y-%m-%d").alias(periodName)
                )
            except Exception as e:
                logging.exception(e)
                exc = print_error_details(e)
                errorMessageType = namingParams["errorMessageType"]
                loadDataTabKey = namingParams["loadDataTab"]
                paramDict = add_app_message_to_paramdict(
                    e,
                    errorMessageType,
                    loadDataTabKey,
                    paramDict,
                    isMessage=True,
                    isToast=True,
                    colNumber=0,
                )
                df = df.with_columns(pl.col(periodName).cast(pl.Utf8).alias(periodName))
    else:
        df = df.with_columns(pl.col(periodName).cast(pl.Utf8).alias(periodName))

    return df, periodsArray


def check_if_year_before_previous_year(paramDict, chartDict):
    namingParams = get_naming_params()
    dateColFound = namingParams["dateColFound"]
    datePeriodName = namingParams["datePeriodName"]
    selectedPeriods = namingParams["selectedPeriods"]
    notMetConditionValue = namingParams["notMetConditionValue"]
    metConditionValue = namingParams["metConditionValue"]
    isYearBeforePy = namingParams["isYearBeforePy"]
    paramDict[isYearBeforePy] = notMetConditionValue
    if (dateColFound not in paramDict and datePeriodName not in paramDict) or not (
        paramDict[dateColFound] and not paramDict[datePeriodName]
    ):
        if selectedPeriods in chartDict:
            if (
                len(chartDict[selectedPeriods][0]) == 5
                and len(chartDict[selectedPeriods][1]) == 5
            ):
                firstPeriod = chartDict[selectedPeriods][0][1:]
                secondPeriod = chartDict[selectedPeriods][1][1:]
                try:
                    firstPeriod = int(firstPeriod)
                    secondPeriod = int(secondPeriod)
                except Exception as e:
                    logging.exception(e)
                    exc = print_error_details(e)
                    errorMessageType = namingParams["errorMessageType"]
                    loadDataTabKey = namingParams["loadDataTab"]
                    paramDict = add_app_message_to_paramdict(
                        e,
                        errorMessageType,
                        loadDataTabKey,
                        paramDict,
                        isMessage=True,
                        isToast=True,
                        colNumber=0,
                    )
                    firstPeriod, secondPeriod = 0, 0
                if secondPeriod - firstPeriod >= 2:
                    paramDict[isYearBeforePy] = metConditionValue
            elif (
                len(chartDict[selectedPeriods][0]) == 4
                and len(chartDict[selectedPeriods][1]) == 4
            ):
                try:
                    firstPeriod = int(chartDict[selectedPeriods][0])
                    secondPeriod = int(chartDict[selectedPeriods][1])
                except Exception as e:
                    logging.exception(e)
                    exc = print_error_details(e)
                    errorMessageType = namingParams["errorMessageType"]
                    loadDataTabKey = namingParams["loadDataTab"]
                    paramDict = add_app_message_to_paramdict(
                        e,
                        errorMessageType,
                        loadDataTabKey,
                        paramDict,
                        isMessage=True,
                        isToast=True,
                        colNumber=0,
                    )
                    firstPeriod, secondPeriod = 0, 0
                if secondPeriod - firstPeriod >= 2:
                    paramDict[isYearBeforePy] = metConditionValue
    return paramDict


def filter_out_useless_periods(df, paramDict, chartDict):
    """
    if we have a period column and it has more than two values we want to keep only
    two periods. Conventionally, we keep the two most recent periods
    """
    namingParams = get_naming_params()
    periodName = namingParams["periodName"]
    periodColFound = namingParams["periodColFound"]
    allPeriodsList = namingParams["allPeriodsList"]
    selectedPeriods = namingParams["selectedPeriods"]
    numberOfPeriodsFound = namingParams["numberOfPeriodsFound"]
    mostRecentPeriod = namingParams["mostRecentPeriod"]
    compareWithYearBefore = namingParams["compareWithYearBefore"]
    datePeriodName = namingParams["datePeriodName"]
    periodName = namingParams["periodName"]
    yearName = namingParams["yearName"]
    fcName = namingParams["fcName"]
    plName = namingParams["plName"]
    currentYearName = namingParams["currentYearName"]
    notMetConditionValue = namingParams["notMetConditionValue"]
    metConditionValue = namingParams["metConditionValue"]
    tyYaDates = namingParams["tyYaDates"]
    periodToDate = namingParams["periodToDate"]
    changedTimeAggregation = namingParams["changedTimeAggregation"]
    isPeriodColFound = paramDict[periodColFound]
    applyFilter = False
    selectedPeriodsArray = []
    columns, schema = utils.get_schema_and_column_names(df)
    if isPeriodColFound or periodName in columns:
        paramDict[periodColFound] = isPeriodColFound
        if periodName in columns:
            df = df.with_columns(pl.col(periodName).cast(pl.Utf8).alias(periodName))
        reverseSort = False
        periods = get_periods_array(df)
        if fcName in periods:
            periods.remove(fcName)
        if plName in periods:
            reverseSort = True
        if compareWithYearBefore in chartDict and chartDict[compareWithYearBefore]:
            if (
                datePeriodName in paramDict
                and paramDict[datePeriodName] == yearName
                and currentYearName in periods
            ):
                reverseSort = True
        chosenDatePeriodName = paramDict[datePeriodName]
        periods = [str(i) for i in periods]
        sortedPeriods = sorted(periods, reverse=reverseSort)
        numberOfPeriods = len(periods)

        paramDict[numberOfPeriodsFound] = numberOfPeriods
        if numberOfPeriods > 1 and mostRecentPeriod in chartDict:
            mostRecentPeriod = chartDict[mostRecentPeriod]
            mostRecentPeriodIndex, paramDict = get_dataset_specific_parameter(
                paramDict, namingParams["mostRecentPeriodIndex"], False
            )
            if numberOfPeriods > abs(mostRecentPeriod):
                mostRecentPeriodIndex = mostRecentPeriod
            else:
                mostRecentPeriodIndex = -(numberOfPeriods - 1)
            yearBeforePeriodIndex = 0
            if compareWithYearBefore in chartDict and chartDict[compareWithYearBefore]:
                if datePeriodName in paramDict and paramDict[datePeriodName]:
                    if paramDict[datePeriodName] != yearName:
                        yearBeforePeriodIndex = check_if_year_before_period_exists(
                            sortedPeriods, mostRecentPeriodIndex, paramDict
                        )
            otherPeriodIndex = mostRecentPeriodIndex - yearBeforePeriodIndex - 1
            if len(sortedPeriods) < abs(otherPeriodIndex):
                otherPeriodIndex = mostRecentPeriodIndex - 1
                if periodToDate not in chartDict or not chartDict[periodToDate]:
                    chartDict[compareWithYearBefore] = notMetConditionValue
                    paramDict[changedTimeAggregation] = metConditionValue
                    message = "Dataset contains less than 24 months of data. 'Date Aggregation' parameter set to month, 'Compare to Rolling Period' parameter forced to False. You can set the parameter back to year in the Period Options tab. "
                    add_info_message_in_period_options_tab(paramDict, message)
            df, sortedPeriods = transform_integer_periods(df, sortedPeriods, paramDict)
            selectedPeriodsArray = [
                sortedPeriods[otherPeriodIndex],
                sortedPeriods[mostRecentPeriodIndex],
            ]
            chartDict[mostRecentPeriod] = mostRecentPeriodIndex
            paramDict[allPeriodsList] = sortedPeriods
            paramDict[selectedPeriods] = selectedPeriodsArray
            chartDict[selectedPeriods] = selectedPeriodsArray
            dfAllPeriods = duplicate_dataframe(df)
            dfAllPeriods = dfAllPeriods.sort(by=periodName, descending=False)
            df, dfPeriods = apply_filter_and_copy_df(
                df, selectedPeriodsArray, paramDict, chartDict
            )
            paramDict = check_if_year_before_previous_year(paramDict, chartDict)
            return df, dfPeriods, dfAllPeriods, paramDict, chartDict
        elif numberOfPeriods == 1 and mostRecentPeriod in chartDict:
            df, sortedPeriods = transform_integer_periods(df, sortedPeriods, paramDict)
            selectedPeriodsArray = sortedPeriods
            mostRecentPeriodIndex = 0
            chartDict[mostRecentPeriod] = mostRecentPeriodIndex
            paramDict[allPeriodsList] = sortedPeriods
            paramDict[selectedPeriods] = selectedPeriodsArray
            chartDict[selectedPeriods] = selectedPeriodsArray
            dfAllPeriods = duplicate_dataframe(df)
            df, dfPeriods = apply_filter_and_copy_df(
                df, selectedPeriodsArray, paramDict, chartDict
            )
            return df, dfPeriods, dfAllPeriods, paramDict, chartDict
        else:
            dfPeriods, dfAllPeriods = pl.LazyFrame(), pl.LazyFrame()
            return df, dfPeriods, dfAllPeriods, paramDict, chartDict
    else:
        dfPeriods, dfAllPeriods = pl.LazyFrame(), pl.LazyFrame()
        return df, dfPeriods, dfAllPeriods, paramDict, chartDict
