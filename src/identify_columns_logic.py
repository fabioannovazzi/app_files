from __future__ import annotations

import polars as pl

from modules.utilities.config import get_config_params, get_naming_params

__all__ = [
    "monetary_col_found",
    "show_input_data",
    "volume_col_found",
    "units_col_found",
    "date_col_found",
    "period_col_found",
    "discount_col_found",
    "cogs_col_found",
    "indirect_costs_col_found",
]


def monetary_col_found(
    param_dict: dict,
) -> tuple[dict, list[tuple[str, str, str | None]]]:
    """Return messages related to monetary column detection.

    Expects ``cogsColFound`` indicator in ``param_dict``.
    """
    naming = get_naming_params()
    config = get_config_params()
    monetary_col_found = naming["monetaryLocalCurrencyColFound"]
    likely_cols = naming["likelyLocalCurrencyValueCols"]
    stem_dict = config[naming["stemDict"]]
    stem_array = naming["stemArray"]
    monetary_stem = naming["monetaryLocalCurrencyStemDict"]
    success_icon = naming["successIcon"]
    error_icon = naming["errorIcon"]
    warning_icon = naming["warningIcon"]
    impossible = naming["impossibleToProcessFile"]

    messages: list[tuple[str, str, str | None]] = []

    if monetary_col_found in param_dict:
        name_list = (
            str(stem_dict[monetary_stem][stem_array]).replace("[", "").replace("]", "")
        )
        if param_dict[monetary_col_found] and len(param_dict[likely_cols][0]) > 0:
            messages.append(
                (
                    "success",
                    f"The **{param_dict[likely_cols][0]}** column was tagged as the *gross monetary value* column (before discounts) of the dataset.",
                    success_icon,
                )
            )
            messages.append(
                (
                    "caption",
                    "If this is not correct, rename the monetary value column and reload the file.\n"
                    "The monetary column must be in **plain number format** (no thousand separators, no currency 💲 signs, zero written as 0 not as -).\n"
                    "The name of the monetary value column **must contain** one of these stems:",
                    None,
                )
            )
            messages.append(("caption", f"*{name_list}*", None))
            messages.append(("caption", "\n", None))
            messages.append(("caption", "\n", None))
        else:
            if param_dict[naming["cogsColFound"]]:
                messages.append(
                    (
                        "warning",
                        "We were unable to identify the *monetary value* column in the dataset. Processing will continue using the cost column only.",
                        warning_icon,
                    )
                )
                messages.append(
                    (
                        "caption",
                        "If your dataset has a sales column, rename it and reload the file. The name of the monetary value column must contain one of these stems:",
                        None,
                    )
                )
                messages.append(("caption", f"*{name_list}*", None))
                messages.append(("caption", "\n", None))
                messages.append(("caption", "\n", None))
            else:
                param_dict[impossible] = True
                messages.append(
                    (
                        "error",
                        "We were unable to identify the *monetary value* column in the dataset.\n"
                        "The app requires a monetary value column.\n"
                        "The monetary column must be in **plain number format** (no thousand separators, no currency 💲 format, zero written as 0 not as -).",
                        error_icon,
                    )
                )
                messages.append(
                    (
                        "caption",
                        "Rename the monetary value column (or change its formatting to **plain number format**) and reload the file.\n"
                        "The name of the monetary value column **must contain** one of these stems:",
                        None,
                    )
                )
                messages.append(("caption", f"*{name_list}*", None))
                messages.append(("caption", "\n", None))
                messages.append(("caption", "\n", None))
    return param_dict, messages


def show_input_data(
    df: pl.LazyFrame, param_dict: dict
) -> tuple[pl.LazyFrame, dict, list[tuple[str, str, str | None]]]:
    """Return messages for detected columns."""
    naming = get_naming_params()
    messages: list[tuple[str, str, str | None]] = []
    if pl.LazyFrame in {type(df)}:
        for func in (
            monetary_col_found,
            volume_col_found,
            units_col_found,
            date_col_found,
            period_col_found,
            discount_col_found,
            cogs_col_found,
            indirect_costs_col_found,
        ):
            param_dict, msgs = func(param_dict)
            messages.extend(msgs)
    if (
        naming["impossibleToProcessFile"] in param_dict
        and param_dict[naming["impossibleToProcessFile"]]
    ):
        df = pl.LazyFrame()
    return df, param_dict, messages


def volume_col_found(
    param_dict: dict,
) -> tuple[dict, list[tuple[str, str, str | None]]]:
    """Return messages for volume column detection."""

    naming = get_naming_params()
    config = get_config_params()
    found = naming["volumeColFound"]
    likely = naming["likelyVolumeCols"]
    stem_dict = config[naming["stemDict"]]
    stem_array = naming["stemArray"]
    stem_key = naming["volumeStemDict"]
    success_icon = naming["successIcon"]

    messages: list[tuple[str, str, str | None]] = []

    if found in param_dict:
        name_list = (
            str(stem_dict[stem_key][stem_array]).replace("[", "").replace("]", "")
        )
        if param_dict[found] and len(param_dict[likely]) > 0:
            messages.append(
                (
                    "success",
                    f"The **{param_dict[likely][0]}** column was tagged as the *volume* column of the dataset.",
                    success_icon,
                )
            )
            messages.append(
                (
                    "caption",
                    "If this is not correct, rename the volume column and reload the file.\n"
                    "The volume column must be in **plain number format** (no thousand separators, zero written as 0 not as -).\n"
                    "The name of the volume column **must contain** one of these stems:",
                    None,
                )
            )
            messages.append(("caption", f"*{name_list}*", None))
            messages.append(("caption", "\n", None))
            messages.append(("caption", "\n", None))
        else:
            messages.append(
                (
                    "caption",
                    "We were unable to identify a  *volume* column in the dataset.\nThis might be OK. The app **does not require** a volume column.",
                    None,
                )
            )
            messages.append(
                (
                    "caption",
                    "If your dataset indeed has a volume column, rename it (or change its formatting to **plain number format**) and reload the file.\n"
                    "The volume column must be in **absolute** value with positive sign.\n"
                    "The name of the volume column **must contain** one of these stems:",
                    None,
                )
            )
            messages.append(("caption", f"*{name_list}*", None))
            messages.append(("caption", "\n", None))
            messages.append(("caption", "\n", None))
    return param_dict, messages


def units_col_found(
    param_dict: dict,
) -> tuple[dict, list[tuple[str, str, str | None]]]:
    """Return messages for units column detection."""

    naming = get_naming_params()
    config = get_config_params()
    found = naming["unitsColFound"]
    likely = naming["likelyUnitsCols"]
    stem_dict = config[naming["stemDict"]]
    stem_array = naming["stemArray"]
    stem_key = naming["unitsStemDict"]
    success_icon = naming["successIcon"]

    messages: list[tuple[str, str, str | None]] = []

    if found in param_dict:
        name_list = (
            str(stem_dict[stem_key][stem_array]).replace("[", "").replace("]", "")
        )
        if param_dict[found] and len(param_dict[likely]) > 0:
            messages.append(
                (
                    "success",
                    f"The **{param_dict[likely][0]}** column was tagged as the *units* column of the dataset.",
                    success_icon,
                )
            )
            messages.append(
                (
                    "caption",
                    "If this is not correct, rename the units column and reload the file.\n"
                    "The units column must be in **plain number format** (no thousand separators, zero written as 0 not as -).\n"
                    "The name of the units column **must contain** one of these stems:",
                    None,
                )
            )
            messages.append(("caption", f"*{name_list}*", None))
            messages.append(("caption", "\n", None))
            messages.append(("caption", "\n", None))
        else:
            messages.append(
                (
                    "caption",
                    "We were unable to identify a  *units* column in the dataset.\nThis might be OK. The app **does not require** a units column.",
                    None,
                )
            )
            messages.append(
                (
                    "caption",
                    "If your dataset indeed has a units column, rename it (or change its formatting to **plain number format**) and reload the file.\n"
                    "The units column must be in **absolute** value with positive sign.\n"
                    "The name of the units column **must contain** one of these stems:",
                    None,
                )
            )
            messages.append(("caption", f"*{name_list}*", None))
            messages.append(("caption", "\n", None))
            messages.append(("caption", "\n", None))
    return param_dict, messages


def date_col_found(
    param_dict: dict,
) -> tuple[dict, list[tuple[str, str, str | None]]]:
    """Return messages for date column detection.

    Expects ``numberOfPeriodsFound`` indicator in ``param_dict``.
    """

    naming = get_naming_params()
    config = get_config_params()
    found = naming["dateColFound"]
    likely = naming["likelyDateCols"]
    stem_dict = config[naming["stemDict"]]
    stem_array = naming["stemArray"]
    stem_key = naming["dateStemDict"]
    success_icon = naming["successIcon"]
    error_icon = naming["errorIcon"]

    messages: list[tuple[str, str, str | None]] = []

    if found in param_dict:
        name_list = (
            str(stem_dict[stem_key][stem_array]).replace("[", "").replace("]", "")
        )
        periods_found = param_dict.get(naming["numberOfPeriodsFound"], 0)
        if param_dict[found] and len(param_dict[likely]) > 0 and periods_found >= 1:
            messages.append(
                (
                    "success",
                    f"The **{param_dict[likely][0]}** column was tagged as the *date* column of the dataset.",
                    success_icon,
                )
            )
            messages.append(
                (
                    "caption",
                    "If this is not correct, rename the date column and reload the file.\nThe date column must be in plain date format (no time info) and its name **must contain** one of these stems:",
                    None,
                )
            )
            messages.append(("caption", f"*{name_list}*", None))
            messages.append(("caption", "\n", None))
            messages.append(("caption", "\n", None))
            if periods_found == 1:
                warning_icon = naming["warningIcon"]
                messages.append(
                    (
                        "warning",
                        "We identified a date column. However, given the 'Date Aggregation' parameter choice, we found only one period.\nYear-over-year charts will not be plotted.",
                        warning_icon,
                    )
                )
        elif not param_dict[naming["periodColFound"]]:
            param_dict[naming["impossibleToProcessFile"]] = True
            messages.append(
                (
                    "error",
                    "We were unable to identify the *date* column in the dataset.\nThe app requires either a date column in date format (no time info) or a period column with two values (e.g. “pre-post”, “2018 vs 2019”, “budget vs actuals”,... ).",
                    error_icon,
                )
            )
            messages.append(
                (
                    "caption",
                    "If your dataset indeed has a date column, rename it (or change its formatting to plain data, no time info format) and reload the file.\nThe date column must be in **date** format (no time info).\nThe name of the date column **must contain** one of these stems:",
                    None,
                )
            )
            messages.append(("caption", f"*{name_list}*", None))
            messages.append(("caption", "\n", None))
            messages.append(("caption", "\n", None))
    return param_dict, messages


def period_col_found(
    param_dict: dict,
) -> tuple[dict, list[tuple[str, str, str | None]]]:
    """Return messages for period column detection.

    Expects ``numberOfPeriodsFound`` indicator in ``param_dict``.
    """

    naming = get_naming_params()
    config = get_config_params()
    found = naming["periodColFound"]
    likely = naming["likelyPeriodCols"]
    stem_dict = config[naming["stemDict"]]
    stem_array = naming["stemArray"]
    stem_key = naming["periodStemDict"]
    success_icon = naming["successIcon"]
    error_icon = naming["errorIcon"]

    messages: list[tuple[str, str, str | None]] = []

    if found in param_dict:
        name_list = (
            str(stem_dict[stem_key][stem_array]).replace("[", "").replace("]", "")
        )
        periods_found = param_dict.get(naming["numberOfPeriodsFound"], 0)
        if param_dict[found] and len(param_dict[likely]) > 0 and periods_found >= 1:
            messages.append(
                (
                    "success",
                    f"The **{param_dict[likely][0]}** column was tagged as the *period* column of the dataset.",
                    success_icon,
                )
            )
            messages.append(
                (
                    "caption",
                    "If this is not correct, rename the period column and reload the file.\nThe period column must have at **least two values** (e.g. “pre,post”, “2018,2019”, “budget,actuals”,... ).\nThe name of the period column **must contain** one of these stems:",
                    None,
                )
            )
            messages.append(("caption", f"*{name_list}*", None))
            messages.append(("caption", "\n", None))
            messages.append(("caption", "\n", None))
            if not param_dict[naming["dateColFound"]] and periods_found == 1:
                warning_icon = naming["warningIcon"]
                messages.append(
                    (
                        "warning",
                        "We identified a date column. However, given the 'Date Aggregation' parameter choice, we found only one period.\nYear-over-year charts will not be plotted.",
                        warning_icon,
                    )
                )
        elif not param_dict[naming["dateColFound"]]:
            param_dict[naming["impossibleToProcessFile"]] = True
            messages.append(
                (
                    "error",
                    "We were unable to identify the  *period* column in the dataset.\nThe app requires either a period column with two values (e.g. “pre-post”, “2018 vs 2019”, “budget vs actuals”,... ) or a date column",
                    error_icon,
                )
            )
            messages.append(
                (
                    "caption",
                    "If your dataset indeed has a period column, rename it and reload the file.\nThe name of the period column **must contain** one of these stems:",
                    None,
                )
            )
            messages.append(("caption", f"*{name_list}*", None))
            messages.append(("caption", "\n", None))
            messages.append(("caption", "\n", None))
    return param_dict, messages


def discount_col_found(
    param_dict: dict,
) -> tuple[dict, list[tuple[str, str, str | None]]]:
    """Return messages for discount column detection."""

    naming = get_naming_params()
    config = get_config_params()
    found = naming["discountColFound"]
    likely = naming["likelyDiscountCols"]
    stem_dict = config[naming["stemDict"]]
    stem_array = naming["stemArray"]
    stem_key = naming["discountStemDict"]
    success_icon = naming["successIcon"]

    messages: list[tuple[str, str, str | None]] = []

    if found in param_dict:
        name_list = (
            str(stem_dict[stem_key][stem_array]).replace("[", "").replace("]", "")
        )
        if param_dict[found] and len(param_dict[likely]) > 0:
            messages.append(
                (
                    "success",
                    f"The **{param_dict[likely][0]}** column was tagged as the *discount and commissions* column of the dataset.",
                    success_icon,
                )
            )
            messages.append(
                (
                    "caption",
                    "If this is not correct, rename the discount column and reload the file.\nThe discount column must be in **plain number format** (no thousand separators, no currency 💲 format, zero written as 0 not as -).\nDiscounts must be in **absolute (not percent)** value with **positive sign**.\nThe name of the discount column **must contain** one of these stems:",
                    None,
                )
            )
            messages.append(("caption", f"*{name_list}*", None))
            messages.append(("caption", "\n", None))
            messages.append(("caption", "\n", None))
        else:
            messages.append(
                (
                    "caption",
                    "We were unable to identify a *discount* column in the dataset.\nThis is OK. The app **does not require** a discount column.\nDiscounts must be in **absolute (not percent)** value with **positive sign**.",
                    None,
                )
            )
            messages.append(
                (
                    "caption",
                    "If your dataset indeed has a discount column, rename it and reload the file.\nDiscounts must be in **absolute (not percent)** value with positive sign.\nThe name of the discount column **must contain** one of these stems:",
                    None,
                )
            )
            messages.append(("caption", f"*{name_list}*", None))
            messages.append(("caption", "\n", None))
            messages.append(("caption", "\n", None))
    return param_dict, messages


def cogs_col_found(
    param_dict: dict,
) -> tuple[dict, list[tuple[str, str, str | None]]]:
    """Return messages for COGS column detection."""

    naming = get_naming_params()
    config = get_config_params()
    found = naming["cogsColFound"]
    likely = naming["likelyCogsCols"]
    stem_dict = config[naming["stemDict"]]
    stem_array = naming["stemArray"]
    stem_key = naming["cogsStemDict"]
    success_icon = naming["successIcon"]

    messages: list[tuple[str, str, str | None]] = []

    if found in param_dict:
        name_list = (
            str(stem_dict[stem_key][stem_array]).replace("[", "").replace("]", "")
        )
        if param_dict[found] and len(param_dict[likely]) > 0:
            messages.append(
                (
                    "success",
                    f"The **{param_dict[likely][0]}** column was tagged as the *COGS* column of the dataset.",
                    success_icon,
                )
            )
            messages.append(
                (
                    "caption",
                    "If this is not correct, rename the COGS column and reload the file.\n"
                    "The COGS column must be in **plain number format** (no thousand separators, no currency 💲 format, zero written as 0 not as -).\n"
                    "COGS column must be in **absolute (not percent)** value with **positive** sign.\n"
                    "The name of the COGS column **must contain** one of these stems:",
                    None,
                )
            )
            messages.append(("caption", f"*{name_list}*", None))
            messages.append(("caption", "\n", None))
            messages.append(("caption", "\n", None))
        else:
            messages.append(
                (
                    "caption",
                    "We were unable to identify a *COGS* column in the dataset.\n"
                    "This is OK. The app **does not require** a COGS column.\n"
                    "The COGS column must be in **plain number format**, not in currency 💲 format.",
                    None,
                )
            )
            messages.append(
                (
                    "caption",
                    "If your dataset indeed has COGS column, rename it and reload the file.\n"
                    "The COGS column must be in **plain number format** (no thousand separators, no currency 💲 format, zero written as 0 not as -).\n"
                    "COGS column must be in **absolute (not percent)** value with **positive** sign.\n"
                    "The COGS column **must contain** one of these stems:",
                    None,
                )
            )
            messages.append(("caption", f"*{name_list}*", None))
            messages.append(("caption", "\n", None))
            messages.append(("caption", "\n", None))
    return param_dict, messages


def indirect_costs_col_found(
    param_dict: dict,
) -> tuple[dict, list[tuple[str, str, str | None]]]:
    """Return messages for indirect costs column detection."""

    naming = get_naming_params()
    config = get_config_params()
    found = naming["indirectCostsColFound"]
    likely = naming["likelyIndirectCostsCols"]
    stem_dict = config[naming["stemDict"]]
    stem_array = naming["stemArray"]
    stem_key = naming["indirectCostsStemDict"]
    success_icon = naming["successIcon"]

    messages: list[tuple[str, str, str | None]] = []

    if found in param_dict:
        name_list = (
            str(stem_dict[stem_key][stem_array]).replace("[", "").replace("]", "")
        )
        if param_dict[found] and len(param_dict[likely]) > 0:
            messages.append(
                (
                    "success",
                    f"The **{param_dict[likely][0]}** column was tagged as the *indirect costs* column of the dataset.",
                    success_icon,
                )
            )
            messages.append(
                (
                    "caption",
                    "If this is not correct, rename the indirect costs column and reload the file.\n"
                    "The indirect costs column must be in **plain number format** (no thousand separators, no currency 💲 format, zero written as 0 not as -).\n"
                    "Indirect costs column must be in **absolute (not percent)** value with **positive** sign.\n"
                    "The name of the indirect costs column **must contain** one of these stems:",
                    None,
                )
            )
            messages.append(("caption", f"*{name_list}*", None))
            messages.append(("caption", "\n", None))
            messages.append(("caption", "\n", None))
        else:
            messages.append(
                (
                    "caption",
                    "We were unable to identify an *indirect costs* column in the dataset.\n"
                    "This is OK. The app **does not require** an indirect costs column.\n"
                    "The indirect costs column must be in **plain number format**, not in currency 💲 format.",
                    None,
                )
            )
            messages.append(
                (
                    "caption",
                    "If your dataset indeed has indirect costs column, rename it and reload the file.\n"
                    "The indirect costs column must be in **plain number format** (no thousand separators, no currency 💲 format, zero written as 0 not as -).\n"
                    "Indirect costs column must be in **absolute (not percent)** value with **positive** sign.\n"
                    "The indirect costs column **must contain** one of these stems:",
                    None,
                )
            )
            messages.append(("caption", f"*{name_list}*", None))
            messages.append(("caption", "\n", None))
            messages.append(("caption", "\n", None))
    return param_dict, messages
