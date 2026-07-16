import logging
from typing import Any, Dict

import polars as pl

from modules.data.common_data_utils import clean_array_values
from modules.utilities.config import get_naming_params
from modules.utilities.error_messages import add_app_message_to_paramdict
from modules.utilities.helpers import (
    get_data_sample,
    print_error_details,
)
from modules.utilities.ui_notifier import ui as notifier
from modules.utilities.utils import (
    ensure_lazyframe,
    get_schema_and_column_names,
)


def merge_main_df_with_dimension_tables(
    paramDict: Dict[str, Any], df: pl.DataFrame | pl.LazyFrame
) -> tuple[pl.LazyFrame, Dict[str, Any]]:
    """Merge dimension tables with the main dataset lazily.

    Any ``DataFrame`` inputs are converted to ``LazyFrame`` so that the join
    operations avoid eager evaluation. The returned dataframe is always a
    ``LazyFrame``.
    """
    namingParams = get_naming_params()
    multipleFileUploadArray = namingParams["multipleFileUploadArray"]
    notMetConditionValue = namingParams["notMetConditionValue"]
    metConditionValue = namingParams["metConditionValue"]
    isMergedFile = namingParams["isMergedFile"]
    warningMessageType = namingParams["warningMessageType"]
    infoMessageType = namingParams["infoMessageType"]
    joinDatasetTabKey = namingParams["joinDatasetTab"]
    colNumber = 0
    booleanRadioOptions = [notMetConditionValue, metConditionValue]
    paramDict[isMergedFile] = notMetConditionValue

    df = ensure_lazyframe(df)

    if (
        multipleFileUploadArray in paramDict
        and len(paramDict[multipleFileUploadArray]) > 0
    ):
        for dataframe in paramDict[multipleFileUploadArray]:
            # convert each dimension table to a ``LazyFrame``
            dataframe = ensure_lazyframe(dataframe)

            try:
                left_columns, left_schema = get_schema_and_column_names(df)
                right_columns, _ = get_schema_and_column_names(dataframe)
                mergeKeys = set(left_columns).intersection(right_columns)
                if mergeKeys:
                    join_msg = f"found these keys: {', '.join(sorted(mergeKeys))}"
                    paramDict = add_app_message_to_paramdict(
                        join_msg,
                        infoMessageType,
                        joinDatasetTabKey,
                        paramDict,
                        isMessage=True,
                        isToast=False,
                        colNumber=colNumber,
                    )
                else:
                    left = str(left_columns)
                    left = left.replace("[", "").replace("]", "")
                    left = "Left columns: " + left
                    right = str(right_columns)
                    right = right.replace("[", "").replace("]", "")
                    right = "Right columns: " + right
                    paramDict = add_app_message_to_paramdict(
                        "Unable to join. " + left + ". " + right,
                        warningMessageType,
                        joinDatasetTabKey,
                        paramDict,
                        isMessage=True,
                        isToast=True,
                        colNumber=colNumber,
                    )
                    continue
                # abort join when duplicate key values would cause cartesian products
                dupe_check = (
                    dataframe.group_by(list(mergeKeys))
                    .agg(pl.len().alias("_n"))
                    .filter(pl.col("_n") > 1)
                    .limit(1)
                    .collect()
                )
                if dupe_check.height > 0:
                    msg = "Duplicate keys detected in dimension table. Join skipped."
                    paramDict = add_app_message_to_paramdict(
                        msg,
                        warningMessageType,
                        joinDatasetTabKey,
                        paramDict,
                        isMessage=True,
                        isToast=True,
                        colNumber=colNumber,
                    )
                    paramDict[isMergedFile] = notMetConditionValue
                    continue

                for element in mergeKeys:
                    dtype = left_schema[element]
                    if dtype == pl.Utf8:
                        df = df.with_columns(
                            pl.col(element)
                            .str.strip_chars()
                            .str.to_titlecase()
                            .str.replace_all("'", "")
                            .str.replace_all('"', "")
                        )
                        dataframe = dataframe.with_columns(
                            pl.col(element)
                            .str.strip_chars()
                            .str.to_titlecase()
                            .str.replace_all("'", "")
                            .str.replace_all('"', "")
                        )

                dataframe = dataframe.unique()
                df = df.join(dataframe, on=list(mergeKeys), how="left")
                paramDict[isMergedFile] = metConditionValue
            except Exception as e:
                logging.exception(e)
                notifier.error(
                    "Something went wrong while joining the dimension table."
                )
                errorMessage = "Unable to join dimension table. Check that the key column in the dimension table does not have duplicate values and that the columns are named the same in the two datasets."
                e = print_error_details(e)
                paramDict = add_app_message_to_paramdict(
                    e,
                    warningMessageType,
                    joinDatasetTabKey,
                    paramDict,
                    isMessage=True,
                    isToast=False,
                    colNumber=colNumber,
                )
                paramDict = add_app_message_to_paramdict(
                    errorMessage,
                    warningMessageType,
                    joinDatasetTabKey,
                    paramDict,
                    isMessage=True,
                    isToast=True,
                    colNumber=colNumber,
                )
                paramDict[isMergedFile] = notMetConditionValue
                pass

        def _drop_all_null(batch: pl.DataFrame) -> pl.DataFrame:
            columns, _ = get_schema_and_column_names(batch)
            flags = batch.select(
                [pl.col(c).is_not_null().any().alias(c) for c in columns]
            ).row(0, named=True)
            keep = [c for c, v in flags.items() if v]
            return batch.select(keep)

        df = df.map_batches(
            _drop_all_null,
            streamable=False,
            validate_output_schema=False,
        )
        columns, _ = get_schema_and_column_names(df)
        cleanedColumns = clean_array_values(columns)
        df = df.rename({old: new for old, new in zip(columns, cleanedColumns)})
        paramDict = get_data_sample(df, "joined_dataframe", False, paramDict)
    return df, paramDict
