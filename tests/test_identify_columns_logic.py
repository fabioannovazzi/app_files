from __future__ import annotations

import polars as pl

from src.identify_columns_logic import (
    monetary_col_found,
    show_input_data,
    volume_col_found,
)
from modules.utilities.config import get_config_params, get_naming_params


def test_monetary_col_found_success_includes_success_and_stems():
    naming = get_naming_params()
    config = get_config_params()

    found_key = naming["monetaryLocalCurrencyColFound"]
    likely_key = naming["likelyLocalCurrencyValueCols"]
    stem_dict_key = naming["stemDict"]
    stem_key = naming["monetaryLocalCurrencyStemDict"]
    stem_array_key = naming["stemArray"]

    param_dict = {found_key: True, likely_key: ["total_sales"]}

    ret_params, messages = monetary_col_found(param_dict)

    # Assert shape and first message contract
    assert ret_params is param_dict
    assert messages and messages[0][0] == "success"
    assert naming["successIcon"] == messages[0][2]
    assert "total_sales" in messages[0][1]

    # Stems list appears as a dedicated caption line
    name_list = (
        str(config[stem_dict_key][stem_key][stem_array_key])
        .replace("[", "")
        .replace("]", "")
    )
    assert ("caption", f"*{name_list}*", None) in messages


def test_monetary_col_found_sets_impossible_and_error_when_missing_and_no_cogs():
    naming = get_naming_params()

    found_key = naming["monetaryLocalCurrencyColFound"]
    cogs_key = naming["cogsColFound"]
    impossible_key = naming["impossibleToProcessFile"]
    likely_key = naming["likelyLocalCurrencyValueCols"]

    param_dict = {found_key: False, cogs_key: False, likely_key: []}

    ret_params, messages = monetary_col_found(param_dict)

    assert ret_params[impossible_key] is True
    assert messages and messages[0][0] == "error"


def test_volume_col_found_success_and_fallback_messages():
    naming = get_naming_params()
    config = get_config_params()

    found_key = naming["volumeColFound"]
    likely_key = naming["likelyVolumeCols"]

    # Success path
    param_success = {found_key: True, likely_key: ["Volume"]}
    _, msgs_success = volume_col_found(param_success)
    assert msgs_success and msgs_success[0][0] == "success"
    assert naming["successIcon"] == msgs_success[0][2]

    # Fallback when not found
    param_fallback = {found_key: False, likely_key: []}
    _, msgs_fallback = volume_col_found(param_fallback)
    assert any(
        m[0] == "caption" and "does not require" in m[1] for m in msgs_fallback
    )


def test_show_input_data_pass_through_df_and_aggregates_messages_on_success():
    naming = get_naming_params()

    sales_found = naming["monetaryLocalCurrencyColFound"]
    sales_likely = naming["likelyLocalCurrencyValueCols"]
    vol_found = naming["volumeColFound"]
    vol_likely = naming["likelyVolumeCols"]

    df = pl.DataFrame({"a": [1, 2], "b": [3, 4]}).lazy()
    param_dict = {
        sales_found: True,
        sales_likely: ["total_sales"],
        vol_found: True,
        vol_likely: ["Volume"],
    }

    out_df, out_params, messages = show_input_data(df, param_dict)

    # df is returned as-is when processing is possible
    assert out_df is df
    # Expect two success messages (sales and volume)
    assert sum(1 for m in messages if m[0] == "success") == 2
    # No impossible flag added
    assert naming["impossibleToProcessFile"] not in out_params


def test_show_input_data_sets_empty_df_when_impossible():
    naming = get_naming_params()

    sales_found = naming["monetaryLocalCurrencyColFound"]
    cogs_found = naming["cogsColFound"]
    impossible_key = naming["impossibleToProcessFile"]

    df = pl.DataFrame({"x": [1]}).lazy()
    param_dict = {sales_found: False, cogs_found: False}

    out_df, out_params, messages = show_input_data(df, param_dict)

    # Flag is set and df becomes empty
    assert out_params[impossible_key] is True
    collected = out_df.collect()
    assert collected.height == 0 and collected.width == 0
    assert any(m[0] == "error" for m in messages)
