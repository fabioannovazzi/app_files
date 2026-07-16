import types

import pytest

from src.charting_logic import plot_one_period_datasets as plot_logic
from modules.utilities.config import get_naming_params


def test_plot_one_period_datasets_success_passthrough(monkeypatch):
    # Arrange
    df_dict = {"df": object()}
    index_cols = ["A"]
    value_cols = ["V"]
    orig_param = {"p": 1}
    chart_dict = {"type": "x"}
    expander = object()

    called = {}

    def fake_run_charting(d, i, v, p, c, e):
        called["args"] = (d, i, v, p, c, e)
        # Return a distinct dict and a non-empty message
        return {"updated": True}, "sampled"

    monkeypatch.setattr("src.charting_logic.run_charting", fake_run_charting)

    # Act
    out_param, out_msg = plot_logic(
        df_dict, index_cols, value_cols, orig_param, chart_dict, expander
    )

    # Assert
    assert out_param == {"updated": True}
    assert out_msg == "sampled"
    # Ensure arguments are passed through unchanged (identity where applicable)
    assert called["args"] == (df_dict, index_cols, value_cols, orig_param, chart_dict, expander)


def test_plot_one_period_datasets_minimal_inputs(monkeypatch):
    # Arrange: boundary case with minimal/empty inputs and empty message
    df_dict = {}
    index_cols: list[str] = []
    value_cols: list[str] = []
    orig_param: dict = {}
    chart_dict: dict = {}
    expander = None

    def fake_run_charting(d, i, v, p, c, e):
        # Return the same dict (no mutation) and empty message
        return p, ""

    monkeypatch.setattr("src.charting_logic.run_charting", fake_run_charting)

    # Act
    out_param, out_msg = plot_logic(
        df_dict, index_cols, value_cols, orig_param, chart_dict, expander
    )

    # Assert
    assert out_param is orig_param  # passthrough of param dict
    assert out_msg == ""  # empty message is preserved


def test_plot_one_period_datasets_handles_exception_and_adds_message(monkeypatch):
    # Arrange
    df_dict = {}
    index_cols: list[str] = []
    value_cols: list[str] = []
    orig_param: dict = {"k": "v"}
    chart_dict: dict = {}
    expander = None

    err = ValueError("boom")

    def raising_run_charting(*_args, **_kwargs):
        raise err

    monkeypatch.setattr("src.charting_logic.run_charting", raising_run_charting)

    naming = get_naming_params()
    expected_error_type = naming["errorMessageType"]
    expected_tab = naming["plotChartsTab"]

    captured = {}

    def fake_add_app_message_to_paramdict(
        message, messageType, tabName, paramDict, isMessage, isToast, colNumber
    ):
        captured.update(
            dict(
                message=message,
                messageType=messageType,
                tabName=tabName,
                paramDict=paramDict,
                isMessage=isMessage,
                isToast=isToast,
                colNumber=colNumber,
            )
        )
        return {"final": True}

    printed = {}

    def fake_print_error_details(exc):
        printed["exc"] = exc
        return "printed"

    monkeypatch.setattr(
        "src.charting_logic.add_app_message_to_paramdict",
        fake_add_app_message_to_paramdict,
    )
    monkeypatch.setattr("src.charting_logic.print_error_details", fake_print_error_details)

    # Act
    out_param, out_msg = plot_logic(
        df_dict, index_cols, value_cols, orig_param, chart_dict, expander
    )

    # Assert: returns updated dict and empty message
    assert out_param == {"final": True}
    assert out_msg == ""
    # Assert: error was routed to message helper with expected metadata and original param dict
    assert captured["message"] is err
    assert captured["messageType"] == expected_error_type
    assert captured["tabName"] == expected_tab
    assert captured["paramDict"] is orig_param
    assert captured["isMessage"] is True
    assert captured["isToast"] is True
    assert captured["colNumber"] == 0
    # Assert: error details were printed
    assert printed["exc"] is err
