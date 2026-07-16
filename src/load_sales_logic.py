from __future__ import annotations

import datetime as dt
import logging
import tempfile
from pathlib import Path
from typing import List, Tuple

import polars as pl

from modules.data.identify_columns import find_and_parse_datecolumns
from modules.layout.memoization import session_memoize_check_upload
from modules.utilities.config import (
    get_config_params,
    get_dataset_params,
    get_file_params,
    get_naming_params,
)
from modules.utilities.error_messages import (
    add_app_message_to_paramdict,
    add_error_message_in_load_data_tab,
    add_info_message_in_load_data_tab,
    add_warning_message_in_load_data_tab,
)
from modules.utilities.fastexcel import suppress_fastexcel_dtype_warnings
from modules.utilities.helpers import get_file_error_message, print_error_details
from modules.utilities.utils import get_schema_and_column_names, is_valid_lazyframe

__all__ = [
    "convert_decimal_columns_lazy",
    "encode_uploaded_file",
    "parse_csv",
    "parse_excel",
    "parse_parquet",
    "parse_uploaded_file",
    "load_file_from_disk",
    "get_files_from_upload_or_disk",
    "check_activation_token",
    "initialize_paramdict",
    "parse_dimension_datasets",
]


def convert_decimal_columns_lazy(lf: pl.LazyFrame) -> pl.LazyFrame:
    """Return ``lf`` with Decimal columns converted to ``Float64``."""

    schema = lf.collect_schema()
    converted: List[pl.Expr] = []
    for col, dtype in schema.items():
        if str(dtype).startswith("Decimal"):
            converted.append(pl.col(col).cast(pl.Float64).alias(col))
        else:
            converted.append(pl.col(col))
    return lf.select(converted)


def encode_uploaded_file(
    uploaded_file: UploadedFile | None,
    error_message: str,
    message: str,
    param_dict: dict,
) -> tuple[UploadedFile | None, dict]:
    """Validate ``uploaded_file`` and update ``param_dict``.

    Accepted file types are ``csv``, ``xlsx`` and ``parquet``. On success the
    original file object is returned. Otherwise ``None`` is returned and
    ``param_dict`` is populated with descriptive error messages.
    """

    naming = get_naming_params()
    uploaded_type = naming["uploadedFileType"]
    uploaded_name = naming["uploadedFileName"]
    error_type = naming["errorMessageType"]
    caption_type = naming["captionMessageType"]
    load_tab = naming["loadDataTab"]

    result: UploadedFile | None = None
    col_number = 1
    if uploaded_file is not None:
        file_name = uploaded_file.name
        suffix = Path(file_name).suffix.lstrip(".")
        param_dict[uploaded_type] = suffix
        param_dict[uploaded_name] = Path(file_name).stem
        if suffix and suffix in {"xlsx", "parquet", "csv"}:
            result = uploaded_file
        else:
            first_message = (
                "Unrecognized file type. The uploaded file must be either CSV or XLSX."
            )
            param_dict = add_app_message_to_paramdict(
                first_message,
                error_type,
                load_tab,
                param_dict,
                isMessage=True,
                isToast=False,
                colNumber=col_number,
            )
            param_dict = add_app_message_to_paramdict(
                error_message,
                error_type,
                load_tab,
                param_dict,
                isMessage=True,
                isToast=True,
                colNumber=col_number,
            )
            param_dict = add_app_message_to_paramdict(
                message,
                caption_type,
                load_tab,
                param_dict,
                isMessage=True,
                isToast=False,
                colNumber=col_number,
            )
    return result, param_dict


def parse_csv(
    data: UploadedFile, separator: str, param_dict: dict
) -> Tuple[pl.LazyFrame, dict, str]:
    """Return ``LazyFrame`` from ``data`` and parse-error message."""

    parse_msg = ""
    try:
        with tempfile.NamedTemporaryFile(suffix=".csv", delete=False) as tmp:
            tmp.write(data.getvalue())
            df = pl.scan_csv(tmp.name, separator=separator, ignore_errors=True)
    except Exception as e:
        logging.exception(e)
        parse_msg = "Problem parsing the CSV file."
        param_dict = add_error_message_in_load_data_tab(param_dict, parse_msg)
        df = pl.LazyFrame()
    df, param_dict = find_and_parse_datecolumns(df, param_dict)
    return df, param_dict, parse_msg


def parse_excel(
    data: UploadedFile,
    param_dict: dict,
    *,
    schema_overrides: dict[str | int, pl.DataType] | None = None,
) -> Tuple[pl.LazyFrame, dict, str]:
    """Return ``LazyFrame`` from Excel ``data`` and parse-error message.

    Parameters
    ----------
    data:
        Uploaded Excel file.
    param_dict:
        Parameter dictionary mutated with error details.
    schema_overrides:
        Optional mapping of column names or indices to ``polars`` dtypes passed
        to :func:`polars.read_excel` when automatic inference needs guidance.
    """

    parse_msg = ""
    try:
        with suppress_fastexcel_dtype_warnings():
            df = pl.read_excel(
                data, infer_schema_length=None, schema_overrides=schema_overrides
            ).lazy()
    except Exception as e:
        logging.exception(e)
        parse_msg = "Problem parsing the Excel file."
        param_dict = add_error_message_in_load_data_tab(param_dict, parse_msg)
        df = pl.LazyFrame()
    df, param_dict = find_and_parse_datecolumns(df, param_dict)
    return df, param_dict, parse_msg


def parse_parquet(
    data: UploadedFile, param_dict: dict
) -> Tuple[pl.LazyFrame, dict, str]:
    """Return ``LazyFrame`` from Parquet ``data`` and parse-error message."""

    parse_msg = ""
    try:
        with tempfile.NamedTemporaryFile(suffix=".parquet", delete=False) as tmp:
            tmp.write(data.getvalue())
            df = pl.scan_parquet(tmp.name)
    except Exception as e:
        logging.exception(e)
        parse_msg = "Problem parsing the Parquet file."
        param_dict = add_error_message_in_load_data_tab(param_dict, parse_msg)
        df = pl.LazyFrame()
    df, param_dict = find_and_parse_datecolumns(df, param_dict)
    df = convert_decimal_columns_lazy(df)
    return df, param_dict, parse_msg


@session_memoize_check_upload
def parse_uploaded_file(
    dataUploaded: UploadedFile, paramDict: dict
) -> Tuple[pl.LazyFrame, dict]:
    """Parse an uploaded file based on ``paramDict`` settings."""
    namingParams = get_naming_params()
    fileSeparatorKey = namingParams["fileSeparator"]
    uploadedFileType = namingParams["uploadedFileType"]

    file_type = paramDict.get(uploadedFileType)
    separator = paramDict.get(fileSeparatorKey)
    df: pl.LazyFrame
    parse_msg = ""

    if file_type == "csv" and separator:
        df, paramDict, parse_msg = parse_csv(dataUploaded, separator, paramDict)
    elif file_type == "xlsx":
        df, paramDict, parse_msg = parse_excel(dataUploaded, paramDict)
        columns, _ = get_schema_and_column_names(df)
        if len(columns) == 1:
            raise ValueError("excel_parse")
    elif file_type == "parquet":
        df, paramDict, parse_msg = parse_parquet(dataUploaded, paramDict)
        columns, _ = get_schema_and_column_names(df)
        if len(columns) == 1:
            raise ValueError("parquet_parse")
    else:
        df = pl.LazyFrame()

    paramDict["fileParseError"] = parse_msg
    return df, paramDict


def load_file_from_disk(paramDict: dict) -> Tuple[pl.LazyFrame, dict]:
    """Load a dataset from disk using values in ``paramDict``."""

    namingParams = get_naming_params()
    fileParams = get_file_params()
    folderName = fileParams["folderName"]
    fileFormatKey = namingParams["fileFormat"]
    encodingUTF8 = fileParams["encodingUTF8"]
    inputFolderName = fileParams["inputFolderName"]
    errorMessageType = namingParams["errorMessageType"]
    loadDataTabKey = namingParams["loadDataTab"]
    inputFileName = paramDict[namingParams["datasetName"]]
    fileFormat = paramDict[fileFormatKey]
    path = f"{folderName}/{inputFolderName}/{inputFileName}"
    colNumber = 0

    if fileFormat == "csv":
        try:
            df = pl.scan_csv(
                f"{path}.csv",
                encoding=encodingUTF8,
                ignore_errors=True,
                separator=",",
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
            paramDict = add_app_message_to_paramdict(
                "Error in data format. Unable to read file",
                errorMessageType,
                loadDataTabKey,
                paramDict,
                isMessage=True,
                isToast=True,
                colNumber=colNumber,
            )
            df = pl.LazyFrame()
    else:
        df = pl.LazyFrame()
    return df, paramDict


def get_files_from_upload_or_disk(
    paramDict: dict, dataUploadedDict: dict
) -> Tuple[pl.LazyFrame, dict]:
    """Return dataset loaded from upload or disk based on ``paramDict``."""
    namingParams = get_naming_params()
    isDataUploaded = namingParams["isDataUploaded"]
    datasetName = namingParams["datasetName"]
    dataUploadedKey = namingParams["dataUploaded"]

    if (
        dataUploadedDict
        and dataUploadedKey in dataUploadedDict
        and dataUploadedDict[dataUploadedKey]
    ):
        dataUploaded = dataUploadedDict[dataUploadedKey]
        df, paramDict = parse_uploaded_file(dataUploaded, paramDict)
    elif datasetName in paramDict:
        df, paramDict = load_file_from_disk(paramDict)
        paramDict["fileParseError"] = ""
    else:
        df = pl.LazyFrame()
        paramDict["fileParseError"] = ""
    if dataUploadedDict and dataUploadedKey in dataUploadedDict:
        paramDict[isDataUploaded] = True
    if (
        dataUploadedDict
        and dataUploadedKey in dataUploadedDict
        and dataUploadedDict[dataUploadedKey]
        and not is_valid_lazyframe(df)
    ):
        msgs = [
            "Dataset connection lost or issues reading dataset.",
            "If you have already successfully loaded your file, try reloading it. Remember to always wait until the app has stopped running before hitting Submit",
            "If this is the first time you load your file, try using Excel instead of CSV.",
            "If that fails, click on 🔍Detected columns to see which columns have been mapped.",
            "Make sure your date column is in date format, and that your amount column is in plain number format (no thousand separators, no currency 💲 symbols, zero written as 0 not as -).",
            "Check column separator choice. Check that your amount column and your period/date columns are named correctly.",
            "If your file is CSV, check the column separator choice, and make sure the file is saved in UTF8 format",
        ]
        for m in msgs:
            paramDict = add_info_message_in_load_data_tab(paramDict, m)
    return df, paramDict


def check_activation_token(paramDict: dict) -> dict:
    """Validate activation token and update ``paramDict``."""
    configParams = get_config_params()
    today = configParams["today"]
    namingParams = get_naming_params()
    activationToken = namingParams["activationToken"]
    notMetConditionValue = namingParams["notMetConditionValue"]
    metConditionValue = namingParams["metConditionValue"]
    fileUploadDisabled = namingParams["fileUploadDisabled"]
    activationTokenDict = {"potchi": dt.datetime(2025, 12, 31)}
    if activationToken in paramDict:
        if not paramDict[activationToken]:
            paramDict[fileUploadDisabled] = metConditionValue
        token = paramDict[activationToken]
        if token in activationTokenDict:
            daysLeft = (activationTokenDict[token] - today).days
            if daysLeft > 0:
                paramDict[fileUploadDisabled] = notMetConditionValue
                if daysLeft < 10:
                    msg = f"Your activation token will expire in {daysLeft} days."
                    paramDict = add_info_message_in_load_data_tab(paramDict, msg)
            else:
                paramDict = add_warning_message_in_load_data_tab(
                    paramDict, "Your activation token has expired."
                )
        elif token and len(token) > 0:
            paramDict = add_warning_message_in_load_data_tab(
                paramDict, "Invalid token."
            )
            paramDict = add_info_message_in_load_data_tab(
                paramDict, "For further information, contact support."
            )
            paramDict[fileUploadDisabled] = metConditionValue
    return paramDict


def initialize_paramdict(fileCode: str, paramDict: dict) -> dict:
    """Initialize ``paramDict`` for the dataset identified by ``fileCode``."""

    namingParams = get_naming_params()
    datasetParams = get_dataset_params()
    fileCodeName = namingParams["fileCodeName"]
    fileFormat = namingParams["fileFormat"]
    fileUploadDisabledKey = namingParams["fileUploadDisabled"]
    fileUploadDisabled = paramDict[fileUploadDisabledKey]
    paramDict = datasetParams[fileCode]
    paramDict[fileCodeName] = fileCode
    paramDict[fileUploadDisabledKey] = fileUploadDisabled
    paramDict[fileFormat] = paramDict.get(fileFormat, "csv")
    return paramDict


def parse_dimension_datasets(paramDict: dict) -> dict:
    """Parse multiple uploaded dimension datasets."""

    namingParams = get_naming_params()
    fileSeparatorKey = namingParams["fileSeparator"]
    multipleFileUploadArray = namingParams["multipleFileUploadArray"]
    chosenFileSeparator = paramDict.get(fileSeparatorKey)
    dfArray = []
    if chosenFileSeparator and multipleFileUploadArray in paramDict:
        for element in paramDict[multipleFileUploadArray]:
            try:
                with tempfile.NamedTemporaryFile(
                    suffix=".csv", delete=False, mode="w"
                ) as tmp:
                    tmp.write(element.getvalue())
                    tmp_path = tmp.name
                df_lf = pl.scan_csv(
                    tmp_path,
                    ignore_errors=True,
                    separator=chosenFileSeparator,
                )
                try:
                    columns, _ = get_schema_and_column_names(df_lf)
                    row_count = df_lf.select(pl.len()).collect(engine="streaming")[0, 0]
                    null_counts = df_lf.select(pl.all().null_count()).collect()
                    cols = [c for c in columns if null_counts[c][0] != row_count]
                    df_lf = df_lf.select(cols)
                except Exception as e:
                    logging.exception(e)
                    df_lf = df_lf
                dfArray.append(df_lf)
            except Exception as e:
                logging.exception(e)
                dfArray.append(pl.LazyFrame())
            columns, _ = get_schema_and_column_names(dfArray[-1])
            if len(columns) == 1:
                msg = "Problem parsing the CSV file. Click on the + sign under the upload widget and choose the right column separator."
                paramDict = add_error_message_in_load_data_tab(paramDict, msg)
                dfArray[-1] = pl.LazyFrame()
        paramDict[multipleFileUploadArray] = dfArray
    else:
        paramDict[multipleFileUploadArray] = dfArray
    return paramDict
