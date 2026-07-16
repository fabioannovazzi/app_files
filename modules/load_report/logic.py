from __future__ import annotations

from modules.utilities.config import get_config_params, get_naming_params

__all__ = [
    "build_report_choice_list",
    "initialize_conversation_params",
    "update_conversation_state",
]


def build_report_choice_list() -> tuple[list[str], dict[str, str]]:
    """Return the selectable report choices and the report mapping."""

    naming = get_naming_params()
    config = get_config_params()
    report_list = config[naming["reportListDict"]]
    report_upload_choice = naming["reportUploadChoice"]
    choice_array = [report_upload_choice]
    for report_name in report_list:
        if report_name not in choice_array:
            choice_array.append(report_name)
    return choice_array, report_list


def initialize_conversation_params() -> dict:
    """Return a new parameter dict with dataset state initialized."""

    naming = get_naming_params()
    param_dict: dict = {}
    param_dict[naming["isdataset"]] = False
    return param_dict


def update_conversation_state(
    param_dict: dict,
    *,
    chosen_report: str | None,
    exec_sum,
    img_dict,
    desc_dict,
) -> tuple:
    """Update params based on the chosen report and uploaded data."""

    naming = get_naming_params()
    config = get_config_params()
    report_list = config[naming["reportListDict"]]
    isdataset = naming["isdataset"]
    not_met = naming["notMetConditionValue"]
    met = naming["metConditionValue"]
    file_code_name = naming["fileCodeName"]

    if chosen_report is not None or (
        exec_sum is not None
        and len(exec_sum) > 0
        and img_dict is not None
        and len(img_dict) > 0
    ):
        param_dict[isdataset] = True

    if param_dict.get(isdataset):
        if chosen_report is not None:
            file_code = report_list[chosen_report]
            param_dict[file_code_name] = file_code
            param_dict[naming["isDataUploaded"]] = not_met
            exec_sum = None
            img_dict = None
        elif exec_sum is not None:
            param_dict[naming["isDataUploaded"]] = met
            param_dict[file_code_name] = None

    return exec_sum, img_dict, desc_dict, param_dict
