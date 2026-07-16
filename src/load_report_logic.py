from __future__ import annotations

import json
import zipfile
from io import BytesIO
from typing import Tuple

import rarfile
from PIL import Image
from pathlib import Path

from modules.layout.manage_session import (
    cleanup_session_folder,
    initialize_session_folder,
)
from modules.llm.prompt_helpers import extract_industry_and_company_from_dict
from modules.llm.ui_helpers import convert_image_for_GPT
from modules.utilities.config import (
    get_file_params,
    get_naming_params,
    get_report_params,
)
from modules.utilities.error_messages import add_error_message_in_load_data_tab

__all__ = [
    "get_json_and_plots_from_disk",
    "load_json_and_plots_from_disk",
    "process_uploaded_files",
]


def get_json_and_plots_from_disk(
    param_dict: dict,
    executive_summary: dict | None,
    image_dict: dict | None,
    descriptions_dict: dict | None,
) -> Tuple[dict | None, dict | None, dict | None]:
    """Return cached report data if available on disk."""
    naming = get_naming_params()
    file_code = naming["fileCodeName"]
    is_uploaded = naming["isDataUploaded"]
    not_met = naming["notMetConditionValue"]
    if (
        is_uploaded in param_dict
        and param_dict[is_uploaded] == not_met
        and file_code in param_dict
        and param_dict[file_code] is not None
    ):
        return load_json_and_plots_from_disk(param_dict)
    return executive_summary, image_dict, descriptions_dict


def load_json_and_plots_from_disk(param_dict: dict) -> Tuple[dict, dict, dict]:
    """Load report JSON and images from disk."""

    naming = get_naming_params()
    file_params = get_file_params()
    report_params = get_report_params()
    json_exe = file_params["jsonExecutiveSummaryName"]
    json_desc = file_params["jsonDescriptionsName"]
    file_code_key = naming["fileCodeName"]
    chosen_folder_key = naming["chosenReportFolderName"]
    reports_folder = file_params["reportsFolderName"]
    json_folder = file_params["jsonFolderName"]
    images_folder = file_params["imagesFolderName"]
    validated = {}
    chosen_folder = report_params[param_dict[file_code_key]][chosen_folder_key]
    exec_path = Path(reports_folder) / chosen_folder / json_folder / f"{json_exe}.json"
    desc_path = Path(reports_folder) / chosen_folder / json_folder / f"{json_desc}.json"
    if exec_path.exists():
        with open(exec_path, "r") as file:
            executive_summary = json.load(file)
    else:
        msg = f"Could not find {json_exe}.json file."
        param_dict = add_error_message_in_load_data_tab(param_dict, msg)
        executive_summary = {}
    if desc_path.exists():
        with open(desc_path, "r") as file:
            descriptions_dict = json.load(file)
    else:
        msg = f"Could not find {json_desc}.json file."
        param_dict = add_error_message_in_load_data_tab(param_dict, msg)
        descriptions_dict = {}
    image_folder = Path(reports_folder) / chosen_folder / images_folder
    if image_folder.exists():
        png_files = [p.name for p in image_folder.iterdir() if p.suffix == ".png"]
        if png_files:
            image_dict = {}
            executive_summary = extract_industry_and_company_from_dict(
                executive_summary
            )
            for file_name in png_files:
                image_path = image_folder / file_name
                image_dict[file_name] = Image.open(image_path)
            for key in executive_summary:
                if f"{key}.png" in image_dict:
                    validated[key] = executive_summary[key]
        else:
            msg = f"No PNG files found in the folder: {str(image_folder)}."
            param_dict = add_error_message_in_load_data_tab(param_dict, msg)
            image_dict = {}
    else:
        msg = f"The directory '{str(image_folder)}' does not exist."
        param_dict = add_error_message_in_load_data_tab(param_dict, msg)
        image_dict = {}
    return validated, image_dict, descriptions_dict


def process_uploaded_files(
    uploaded_files, param_dict: dict
) -> Tuple[dict, dict, dict, dict]:
    """Process uploaded report files and return parsed contents."""
    naming = get_naming_params()
    file_params = get_file_params()
    json_exec = file_params["jsonExecutiveSummaryName"]
    json_desc = file_params["jsonDescriptionsName"]
    met = naming["metConditionValue"]
    report_key = naming["reportUploaded"]
    executive_summary = None
    descriptions_dict = {}
    image_dict: dict = {}
    validated: dict = {}
    png_files: dict[str, BytesIO] = {}
    zip_uploaded = False
    if len(uploaded_files) == 1 and (
        uploaded_files[0].name.endswith(".zip")
        or uploaded_files[0].name.endswith(".rar")
    ):
        zip_uploaded = True
        session_folder = initialize_session_folder()
        if uploaded_files[0].name.endswith(".zip"):
            with zipfile.ZipFile(uploaded_files[0], "r") as zip_ref:
                zip_ref.extractall(session_folder)
        else:
            with rarfile.RarFile(uploaded_files[0], "r") as rar_ref:
                rar_ref.extractall(session_folder)
        for path in Path(session_folder).iterdir():
            if path.suffix == ".png":
                with path.open("rb") as img_file:
                    png_files[path.name] = BytesIO(img_file.read())
            elif path.suffix == ".json":
                if json_exec in path.name and not executive_summary:
                    executive_summary = path
                elif json_desc in path.name and not descriptions_dict:
                    descriptions_dict = path
    else:
        for uploaded_file in uploaded_files:
            if uploaded_file.name.endswith(".png"):
                png_files[uploaded_file.name] = uploaded_file
            elif uploaded_file.name.endswith(".json"):
                if json_exec in uploaded_file.name and not executive_summary:
                    executive_summary = uploaded_file
                elif json_desc in uploaded_file.name and not descriptions_dict:
                    descriptions_dict = uploaded_file
    if executive_summary is not None:
        if isinstance(executive_summary, (str, Path)):
            with open(executive_summary) as f:
                executive_summary = json.load(f)
            if isinstance(descriptions_dict, (str, Path)):
                with open(descriptions_dict) as f:
                    descriptions_dict = json.load(f)
        else:
            executive_summary = json.load(executive_summary)
            descriptions_dict = json.load(descriptions_dict)
        param_dict[report_key] = met
        if png_files and executive_summary is not None:
            executive_summary = extract_industry_and_company_from_dict(
                executive_summary
            )
            for element in png_files:
                base64_img = convert_image_for_GPT(png_files[element], False, "RGBA")
                image_dict[element] = base64_img
            for key in executive_summary:
                if f"{key}.png" in image_dict:
                    validated[key] = executive_summary[key]
        if zip_uploaded:
            cleanup_session_folder(session_folder)
    else:
        msg = f"Missing '{json_exec}' JSON file. The JSON was not found in the upload."
        param_dict = add_error_message_in_load_data_tab(param_dict, msg)
    return validated, image_dict, descriptions_dict, param_dict
