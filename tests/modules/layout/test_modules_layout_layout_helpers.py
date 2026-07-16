import datetime as dt

import pytest

from modules.layout.layout_helpers import (
    add_app_message_to_paramdict,
    get_config_params,
    get_naming_params,
)


def test_get_naming_params_core_contract():
    # Arrange & Act
    naming = get_naming_params()

    # Assert
    assert isinstance(naming, dict)
    # presence of commonly used keys
    for key in [
        "errorMessageType",
        "infoMessageType",
        "plotChartsTab",
        "showPlotExamples",
        "metConditionValue",
        "notMetConditionValue",
        "auditSupportTabLabel",
        "addAttributesTabLabel",
        "runDeepResearchTabLabel",
    ]:
        assert key in naming

    assert naming["metConditionValue"] is True
    assert naming["notMetConditionValue"] is False
    assert isinstance(naming["plotChartsTab"], str)


def test_get_config_params_consistency_with_naming():
    # Arrange
    naming = get_naming_params()

    # Act
    config = get_config_params()

    # Assert
    assert isinstance(config, dict)
    assert "today" in config and isinstance(config["today"], dt.datetime)

    # periodsArray contains first and second period names from naming params
    assert "periodsArray" in config
    assert config["periodsArray"] == [
        naming["firstPeriodName"],
        naming["secondPeriodName"],
    ]

    # metricsColsDict is provided and is a mapping
    assert "metricsColsDict" in config and isinstance(
        config["metricsColsDict"], dict
    )


def test_add_app_message_to_paramdict_inserts_message():
    # Arrange
    naming = get_naming_params()
    param = {}
    message = "Something happened"
    message_type = naming["errorMessageType"]
    tab_name = naming["plotChartsTab"]
    col_number = 2

    # Act
    out = add_app_message_to_paramdict(
        message, message_type, tab_name, param, True, False, col_number
    )

    # Assert
    arr_key = naming["appMessageArray"]
    content_key = naming["appMessageContent"]
    type_key = naming["appMessageType"]
    as_status_key = naming["showAppMessageAsStatus"]
    as_toast_key = naming["showAppMessageAsToast"]
    icon_key = naming["appMessageIconType"]
    tab_key = naming["appMessageTab"]
    col_key = naming["appMessageColumn"]

    assert out is param  # function mutates and returns the same dict
    assert arr_key in out and isinstance(out[arr_key], list)
    assert len(out[arr_key]) == 1

    entry = out[arr_key][0]
    assert entry[content_key] == message
    assert entry[type_key] == message_type
    assert entry[as_status_key] is True
    assert entry[as_toast_key] is False
    assert entry[tab_key] == tab_name
    assert entry[col_key] == col_number
    # icon matches the error type mapping
    assert entry[icon_key] == naming["errorIcon"]


def test_add_app_message_to_paramdict_is_idempotent():
    # Arrange
    naming = get_naming_params()
    param = {}
    args = (
        "Msg",
        naming["infoMessageType"],
        naming["plotChartsTab"],
        param,
        True,
        True,
        1,
    )

    # Act
    add_app_message_to_paramdict(*args)
    add_app_message_to_paramdict(*args)  # same message should not duplicate

    # Assert
    arr_key = naming["appMessageArray"]
    icon_key = naming["appMessageIconType"]
    # still exactly one message, with the info icon
    assert len(param[arr_key]) == 1
    assert param[arr_key][0][icon_key] == naming["infoIcon"]


def test_add_app_message_to_paramdict_unknown_type_raises_key_error():
    # Arrange
    naming = get_naming_params()
    param = {}

    # Act / Assert
    with pytest.raises(KeyError):
        add_app_message_to_paramdict(
            "Msg", "unknown_type", naming["plotChartsTab"], param, True, False, 0
        )
