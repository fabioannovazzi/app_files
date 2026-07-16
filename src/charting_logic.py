from __future__ import annotations

import logging
from modules.charting.run_charting import run_charting
from modules.utilities.config import get_naming_params
from modules.utilities.error_messages import add_app_message_to_paramdict
from modules.utilities.helpers import print_error_details

__all__ = ["plot_one_period_datasets"]


def plot_one_period_datasets(
    df_dict: dict,
    index_cols: list[str],
    value_cols: list[str],
    param_dict: dict,
    chart_dict: dict,
    expander,
) -> tuple[dict, str]:
    """Run charting for the provided dataset."""
    naming = get_naming_params()
    error_type = naming["errorMessageType"]
    tab_key = naming["plotChartsTab"]
    message = ""
    try:
        param_dict, message = run_charting(
            df_dict, index_cols, value_cols, param_dict, chart_dict, expander
        )
    except Exception as e:  # pragma: no cover - just defensive
        logging.exception(e)
        exc = print_error_details(e)
        param_dict = add_app_message_to_paramdict(
            e,
            error_type,
            tab_key,
            param_dict,
            isMessage=True,
            isToast=True,
            colNumber=0,
        )
    return param_dict, message
