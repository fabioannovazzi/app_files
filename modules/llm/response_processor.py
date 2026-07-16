import json
import logging
from contextlib import nullcontext

from modules.utilities.ui_notifier import ui

from modules.llm.prompt_helpers import (
    synchronize_keys,
    transform_str_dictionary_to_dict,
)


def check_if_image_in_source_dictionary(llmOutputDict, originalDict, col=None):
    isWrongKey = False
    context_manager = col if col is not None else nullcontext()
    with context_manager:
        ui.caption("Checking dictionary for missing images....")
        if isinstance(llmOutputDict, str):
            try:
                llmOutputDict = transform_str_dictionary_to_dict(llmOutputDict)
            except json.JSONDecodeError as e:
                logging.exception(e)
                ui.error("Something went wrong while parsing the LLM response.")
        if isinstance(originalDict, str):
            try:
                originalDict = transform_str_dictionary_to_dict(originalDict)
            except json.JSONDecodeError as e:
                logging.exception(e)
                ui.error("Something went wrong while parsing the LLM response.")
        if isinstance(llmOutputDict, dict):
            for key, value in llmOutputDict.items():
                if key in originalDict:
                    pass
                else:
                    isWrongKey = True
        if isWrongKey:
            synchronizedDict = synchronize_keys(originalDict, llmOutputDict, col)
            return synchronizedDict
        else:
            return llmOutputDict
    return llmOutputDict
