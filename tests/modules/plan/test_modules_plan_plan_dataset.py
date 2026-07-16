import types

import pytest

from modules.plan import plan_dataset as pd_module


class _Writer:
    def __init__(self, idx: int):
        self.idx = idx
        self.buffer = []

    # UI-like write stub
    def write(self, text: str):
        self.buffer.append(text)

    # Support context manager when needed elsewhere
    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False


def test_pull_widgets_down_writes_newlines_per_target_columns():
    col_array = [_Writer(0), _Writer(1), _Writer(2)]
    # Act
    result = pd_module.pull_widgets_down(col_array, [0, 2])
    # Assert
    assert result is None
    assert col_array[0].buffer == ["\n"] * 8
    assert col_array[2].buffer == ["\n"] * 8
    assert col_array[1].buffer == []


@pytest.fixture()
def naming_defaults():
    return {
        "defaultForecastName": "baseline",
        "percentChangeLabel": "percent change",
        "forecastChangeLabel": "forecast",
        "modifierLabel": "modifier",
    }


def test_get_percent_change_labels_with_label_and_default_forecast(monkeypatch, naming_defaults):
    monkeypatch.setattr(pd_module, "get_naming_params", lambda: naming_defaults)
    # Arrange
    metric = "units"
    label = "percent change units"
    label_prefix = "Q1 "
    forecast_type = "baseline"  # equals default
    price = "price"
    # Act
    out_label, tooltip, message = pd_module.get_percent_change_labels(
        metric, label, label_prefix, forecast_type, price
    )
    # Assert
    assert out_label == "Q1 percent change units"
    assert tooltip == "Baseline units price forecast in %"
    assert message.startswith("✳️Baseline units price forecast in %")
    assert message.count("✳️") == 1


def test_get_percent_change_labels_non_default_replaces_label_and_tooltip(monkeypatch, naming_defaults):
    monkeypatch.setattr(pd_module, "get_naming_params", lambda: naming_defaults)
    # Arrange
    metric = "units"
    label = "percent change units"
    label_prefix = "Q1 "
    forecast_type = "alt"  # not default
    price = "price"
    # Act
    out_label, tooltip, message = pd_module.get_percent_change_labels(
        metric, label, label_prefix, forecast_type, price
    )
    # Assert
    assert out_label == "Q1 modifier units"  # percent change -> modifier
    assert tooltip == "Alt units price modifier in %"  # forecast -> modifier
    assert message == "✳️Alt units price forecast in %"  # message not replaced


def test_get_percent_change_labels_empty_label_builds_defaults(monkeypatch, naming_defaults):
    monkeypatch.setattr(pd_module, "get_naming_params", lambda: naming_defaults)
    # Arrange
    metric = "units"
    label = ""
    label_prefix = "Pfx "
    forecast_type = "alt"
    price = ""
    # Act
    out_label, tooltip, message = pd_module.get_percent_change_labels(
        metric, label, label_prefix, forecast_type, price
    )
    # Assert
    assert out_label == ""  # label remains empty when not provided
    assert tooltip == "Units modifier in % for alt."  # forecast -> modifier
    assert message.count("✳️") == 2  # double prefixing for empty-label path


def _make_naming_for_forecast():
    return {
        # value keys used by get_forecast_params
        "unitsForecastValue": "units_change",
        "unitsForecastLabel": "percent change units",
        "unitPriceForecastValue": "unit_price_change",
        "unitPriceForecastLabel": "percent change price",
        "volumesForecastValue": "vol_change",
        "volumePriceForecastValue": "vol_price_change",
        "volumesForecastLabel": "percent change vol",
        "volumePriceForecastLabel": "percent change vol price",
        "salesForecastValue": "sales_change",
        "salesForecastLabel": "percent change sales",
        "discountsForecastValue": "discounts_change",
        "discountsForecastLabel": "percent change discounts",
        "cogsForecastValue": "cogs_change",
        "cogsForecastLabel": "percent change cogs",
        # names used to route logic
        "unitsName": "Units",
        "volumeName": "Volume",
        "costsName": "Costs",
        "discountName": "Discount",
        "monetaryLocalCurrencyName": "Amount",
        "defaultForecastName": "baseline",
        "cogsName": "Cogs",
        "colorChoice": "colorChoice",
        "greenToRed": "green2red",
        "blueToOrange": "blue2orange",
        "changeInProportionToSales": "propSales",
    }


def test_get_forecast_params_units_branch_calls_widgets(monkeypatch):
    # Patch names
    monkeypatch.setattr(pd_module, "get_naming_params", _make_naming_for_forecast)
    # Neutralize label builder; its content isn't under test here
    monkeypatch.setattr(
        pd_module,
        "get_percent_change_labels",
        lambda *args, **kwargs: ("LBL", "TT", "MSG"),
    )
    calls = []

    def _spcw(value_key, label, message, tooltip, plan_dict, param_dict, col, forecast_type, show_message, disabled, dimension_nbr, item_nbr, plan_playback_dict):
        calls.append(
            {
                "value_key": value_key,
                "col_idx": getattr(col, "idx", None),
                "disabled": disabled,
                "forecast_type": forecast_type,
                "show_message": show_message,
                "dimension_nbr": dimension_nbr,
                "item_nbr": item_nbr,
            }
        )
        return plan_dict

    monkeypatch.setattr(pd_module, "show_percentage_change_widget", _spcw)

    # Arrange minimal inputs
    df = None
    index_cols = []
    value_cols = ["Units"]  # trigger units branch
    plan_dict = {}
    param_dict = {}
    chart_dict = {}
    forecast_type = "alt"  # not default to avoid context branch
    item_nbr = 0
    col_array = [_Writer(i) for i in range(5)]
    multiple_dimensions = True
    dimension_nbr = 2
    plan_playback_dict = {}

    # Act
    out = pd_module.get_forecast_params(
        df,
        index_cols,
        value_cols,
        plan_dict,
        param_dict,
        chart_dict,
        forecast_type,
        item_nbr,
        col_array,
        multiple_dimensions,
        dimension_nbr,
        plan_playback_dict,
    )

    # Assert
    assert out is plan_dict
    assert [c["value_key"] for c in calls] == [
        "units_change",
        "unit_price_change",
    ]
    # both left/right use dimension index when multiple_dimensions is True
    assert all(c["col_idx"] == dimension_nbr for c in calls)
    assert all(not c["disabled"] for c in calls)
    assert all(c["forecast_type"] == forecast_type for c in calls)
    assert all(not c["show_message"] for c in calls)


def test_get_forecast_params_sales_branch_and_disabled(monkeypatch):
    monkeypatch.setattr(pd_module, "get_naming_params", _make_naming_for_forecast)
    # Keep label builder neutral
    monkeypatch.setattr(
        pd_module,
        "get_percent_change_labels",
        lambda *args, **kwargs: ("LBL", "TT", "MSG"),
    )
    calls = []

    def _spcw(value_key, label, message, tooltip, plan_dict, param_dict, col, forecast_type, show_message, disabled, dimension_nbr, item_nbr, plan_playback_dict):
        calls.append({"value_key": value_key, "disabled": disabled, "col_idx": getattr(col, "idx", None)})
        return plan_dict

    monkeypatch.setattr(pd_module, "show_percentage_change_widget", _spcw)

    # Arrange: ensure units/volume not present; colorChoice triggers costsName path
    df = None
    index_cols = []
    value_cols = ["Other"]
    plan_dict = {}
    param_dict = {}
    chart_dict = {"colorChoice": "green2red"}
    forecast_type = "alt"
    item_nbr = 1
    col_array = [_Writer(i) for i in range(4)]
    multiple_dimensions = False
    dimension_nbr = 1
    plan_playback_dict = {}

    # Act
    out = pd_module.get_forecast_params(
        df,
        index_cols,
        value_cols,
        plan_dict,
        param_dict,
        chart_dict,
        forecast_type,
        item_nbr,
        col_array,
        multiple_dimensions,
        dimension_nbr,
        plan_playback_dict,
    )

    # Assert: sales + volumePrice widgets, second disabled=True
    keys = [c["value_key"] for c in calls]
    assert keys == ["sales_change", "vol_price_change"]
    assert calls[0]["disabled"] is False
    assert calls[1]["disabled"] is True
    # both use dimension index as column when not default forecast
    assert all(c["col_idx"] == dimension_nbr for c in calls)
