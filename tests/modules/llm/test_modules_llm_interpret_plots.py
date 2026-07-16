import types

import pytest

from modules.llm.interpret_plots import (
    change_dict_of_metrics_if_cost_analysis,
    explain_metrics_for_barmekko_prompt,
    explain_metrics_for_stacked_column_prompt,
)
from modules.utilities.config import get_metric_array_params, get_naming_params


def _base_chart_dict(*, dataset_type: str) -> dict:
    np = get_naming_params()
    # minimal chartDict used by the target functions
    return {
        np["datasetTypeName"]: dataset_type,
        np["valuePrefixDict"]: {},
        np["metricsToPlot"]: [],
        np["fullCurrencyName"]: "US Dollar",
    }


def test_change_dict_of_metrics_if_cost_analysis_translates_for_expenses():
    np = get_naming_params()
    chart = _base_chart_dict(dataset_type=np["companyExpenses"])  # cost analysis on
    # Include direct match, substring match, and an untouched key
    td = {
        np["monetaryLocalCurrencyName"]: "m",  # Sales -> Costs
        np["pricePerUnitName"]: "k",  # Unit Price -> Unit Cost
        f"Avg {np['monetaryLocalCurrencyName']}": "b",  # Avg Sales -> Avg Costs
        "Other": "",
    }

    out = change_dict_of_metrics_if_cost_analysis(td, chart)

    assert out[np["costsName"]] == "m"
    assert out[np["costPerUnitName"]] == "k"
    assert out[f"Avg {np['costsName']}"] == "b"
    assert out["Other"] == ""


def test_change_dict_of_metrics_if_cost_analysis_noop_for_non_expenses():
    np = get_naming_params()
    chart = _base_chart_dict(dataset_type=np["companySales"])  # no cost analysis
    td = {np["monetaryLocalCurrencyName"]: "m", "Other": ""}

    out = change_dict_of_metrics_if_cost_analysis(td, chart)

    # Must return unchanged when not an expenses dataset
    assert out == td


def test_change_dict_of_metrics_if_cost_analysis_non_string_key_raises(monkeypatch):
    """Non-string metric keys trigger formatting error and then a TypeError in membership check."""
    np = get_naming_params()
    # Stub UI notifier in the module to avoid UI calls during the error path
    import modules.llm.interpret_plots as ip

    ip.ui = types.SimpleNamespace(error=lambda *args, **kwargs: None)

    chart = _base_chart_dict(dataset_type=np["companyExpenses"])
    td = {123: "x"}  # not a string, will fail .strip() and then `in` check

    with pytest.raises(TypeError):
        change_dict_of_metrics_if_cost_analysis(td, chart)


def test_explain_metrics_for_stacked_column_prompt_builds_text_and_params():
    np = get_naming_params()
    chart = _base_chart_dict(dataset_type=np["companySales"])  # sales context

    # Setup prefixes so function can resolve multipliers
    chart[np["valuePrefixDict"]] = {
        np["monetaryLocalCurrencyName"]: "k",  # thousand
        np["unitsName"]: "",  # number
    }
    chart[np["metricsToPlot"]] = [np["monetaryLocalCurrencyName"], np["unitsName"]]

    out = explain_metrics_for_stacked_column_prompt(
        chartDict=chart,
        currencyName="USD",
        secondCurrency="EUR",
        metric=np["monetaryLocalCurrencyName"],
        element=np["unitsName"],
    )

    text_key = np["metricText"]
    params_key = np["metricParams"]

    # Assert key parts of the explanation without being brittle on spacing
    assert " **Sales** are in **thousand** of **US Dollars**." in out[text_key]
    assert " **Units** are in **number**." in out[text_key]
    # Params are propagated (no cost analysis here)
    assert out[params_key] == chart[np["valuePrefixDict"]]


def test_explain_metrics_for_barmekko_prompt_builds_expected_text():
    np = get_naming_params()
    chart = _base_chart_dict(dataset_type=np["companySales"])  # sales context

    # Required axis keys
    chart[np["yAxisMetric"]] = np["monetaryLocalCurrencyName"]  # Sales
    chart[np["xAxisMetric"]] = np["unitsName"]  # Units
    chart[np["multipliedMetric"]] = np["monetaryLocalCurrencyName"]  # area metric

    # Prefixes drive the "abbreviationDict" lookups
    chart[np["valuePrefixDict"]] = {
        np["monetaryLocalCurrencyName"]: "m",  # million -> millions
        np["unitsName"]: "",  # number -> numbers
    }

    out = explain_metrics_for_barmekko_prompt(
        chartDict=chart,
        currencyName="USD",
        secondCurrency="USD",
        thirdCurrency="USD",
        metric=np["monetaryLocalCurrencyName"],
        element=np["unitsName"],
    )

    text = out[np["metricText"]]
    assert "Bar length values represent **Sales** and are in **millions** of **US Dollars**." in text
    assert "Bar width values represent **Units** and are in **numbers**." in text
    assert "Bar area values represent **Sales** and are in **millions** of **US Dollars**." in text
