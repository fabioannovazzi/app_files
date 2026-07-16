from __future__ import annotations

import polars as pl
import pytest

from modules.utilities.helpers import (
    add_app_message_to_paramdict,
    add_warning_message_in_load_data_tab,
    get_image_name_hash,
    is_valid_lazyframe,
)
from modules.utilities.config import get_naming_params


def test_add_app_message_to_paramdict_appends_and_deduplicates():
    # Arrange
    naming = get_naming_params()
    keys = {
        "arr": naming["appMessageArray"],
        "content": naming["appMessageContent"],
        "type": naming["appMessageType"],
        "toast": naming["showAppMessageAsToast"],
        "status": naming["showAppMessageAsStatus"],
        "icon": naming["appMessageIconType"],
        "tab": naming["appMessageTab"],
        "col": naming["appMessageColumn"],
    }

    msg_type = naming["warningMessageType"]
    tab = naming["loadDataTab"]
    message = "Something to warn about"
    param = {}

    # Act
    out1 = add_app_message_to_paramdict(
        message, msg_type, tab, param, isMessage=True, isToast=True, colNumber=0
    )
    out2 = add_app_message_to_paramdict(
        message, msg_type, tab, param, isMessage=True, isToast=True, colNumber=0
    )  # same payload → dedup

    # Assert (shape + semantics + deduplication)
    assert out1 is param  # mutates and returns the same dict
    assert out2 is param
    entries = param[keys["arr"]]
    assert isinstance(entries, list) and len(entries) == 1
    entry = entries[0]
    assert entry[keys["content"]] == message
    assert entry[keys["type"]] == msg_type
    assert entry[keys["toast"]] is True and entry[keys["status"]] is True
    assert entry[keys["tab"]] == tab
    assert entry[keys["col"]] == 0
    # icon is mapped based on type; ensure it is present and non-empty for warnings
    assert entry[keys["icon"]] == naming["warningIcon"]


def test_add_warning_message_in_load_data_tab_sets_type_and_tab():
    # Arrange
    naming = get_naming_params()
    keys = {
        "arr": naming["appMessageArray"],
        "content": naming["appMessageContent"],
        "type": naming["appMessageType"],
        "toast": naming["showAppMessageAsToast"],
        "status": naming["showAppMessageAsStatus"],
        "icon": naming["appMessageIconType"],
        "tab": naming["appMessageTab"],
        "col": naming["appMessageColumn"],
    }

    param = {}
    message = "check duplicates"

    # Act
    out = add_warning_message_in_load_data_tab(param, message)

    # Assert
    assert out is param
    entries = param[keys["arr"]]
    assert len(entries) == 1
    entry = entries[0]
    assert entry[keys["content"]] == message
    assert entry[keys["type"]] == naming["warningMessageType"]
    assert entry[keys["tab"]] == naming["loadDataTab"]
    assert entry[keys["icon"]] == naming["warningIcon"]
    assert entry[keys["toast"]] is True and entry[keys["status"]] is True
    assert entry[keys["col"]] == 0


@pytest.mark.parametrize(
    "obj",
    [
        pl.DataFrame({"a": [1]}),
        pl.DataFrame({"a": [1]}).lazy(),
    ],
)
def test_is_valid_lazyframe_true_for_valid_frames(obj):
    # Act / Assert
    assert is_valid_lazyframe(obj) is True


@pytest.mark.parametrize(
    "obj",
    [
        pl.DataFrame(schema={"a": pl.Int64}),  # empty eager frame
        None,  # non-frame
    ],
)
def test_is_valid_lazyframe_false_for_invalid_objects(obj):
    # Act / Assert
    assert is_valid_lazyframe(obj) is False


def test_get_image_name_hash_uses_metric_discriminator_value():
    # Arrange
    payload = {"chosenChart": "area", "metricsToPlot": ["sales", "units"]}

    # Act
    sales_hash, _ = get_image_name_hash(payload, "sales", {})
    units_hash, _ = get_image_name_hash(payload, "units", {})
    baseline_hash, _ = get_image_name_hash(payload, False, {})

    # Assert
    assert sales_hash != units_hash
    assert sales_hash != baseline_hash
    assert units_hash != baseline_hash
