from __future__ import annotations

import polars as pl
import pytest

from modules.charting.run_charting import run_charting
from modules.utilities.config import get_naming_params
from modules.utilities.ui_notifier import FastAPINotifier


def _minimal_df_dict() -> dict:
    naming = get_naming_params()
    # Provide empty, but valid placeholders for all known keys used by run_charting.
    return {
        naming["dfPeriodsName"]: pl.DataFrame({"x": [1]}),
        naming["dfAllPeriodsName"]: pl.DataFrame({"x": [1]}),
        naming["dfDatesName"]: pl.DataFrame({"x": [1]}),
        naming["dfSnapshotName"]: pl.DataFrame({"x": []}),
    }


def _notifier_context():
    return FastAPINotifier()


def test_when_no_chosen_chart_returns_empty_message_and_no_crash(monkeypatch):
    # Arrange
    notifier = _notifier_context()
    df_dict = _minimal_df_dict()
    chart_dict = {}
    param_dict = {}

    # Act
    out_params, sample_msg = run_charting(
        df_dict,
        indexCols=[],
        valueCols=[],
        paramDict=param_dict,
        chartDict=chart_dict,
        _expander=None,
        notifier=notifier,
    )

    # Assert
    assert isinstance(out_params, dict)
    assert sample_msg == ""


def test_pareto_sets_dataset_choice_and_calls_plotter(monkeypatch):
    # Arrange
    naming = get_naming_params()
    notifier = _notifier_context()

    # Stub plotting and perf helpers to no-ops so we only validate orchestration
    import modules.charting.run_charting as rc

    called = {"pareto": 0}

    def _plot_pareto(df, chart_dict, param_dict):
        called["pareto"] += 1
        # Return param_dict to respect contract
        param_dict["_plot_called"] = True
        return param_dict

    monkeypatch.setattr(rc, "plot_pareto_chart", _plot_pareto)
    monkeypatch.setattr(rc, "download_chart_dataframe", lambda *a, **k: None)
    monkeypatch.setattr(rc, "measure_time", lambda *a, **k: {})
    monkeypatch.setattr(rc, "display_performance_metrics", lambda *a, **k: None)

    df_dict = _minimal_df_dict()
    row_key = naming["rowToPlotName"]
    dataset_choice_key = naming["datasetChoice"]
    period_name = naming["periodName"]
    entire_dataset = naming["entireDatasetName"]

    chart_dict = {
        naming["chosenChart"]: naming["paretoChart"],
        row_key: entire_dataset,
    }
    param_dict = {}

    # Act
    out_params, sample_msg = run_charting(
        df_dict,
        indexCols=["x"],
        valueCols=["x"],
        paramDict=param_dict,
        chartDict=chart_dict,
        _expander=None,
        notifier=notifier,
    )

    # Assert
    assert called["pareto"] == 1
    assert out_params.get("_plot_called") is True
    # The function rewrites rowToPlot to a human-readable message
    assert chart_dict[row_key] == "entire dataset"
    # Dataset choice is set to period for pareto path
    assert chart_dict[dataset_choice_key] == period_name
    assert sample_msg == ""


def test_selected_periods_propagates_date_period_setting(monkeypatch):
    # Arrange
    naming = get_naming_params()
    notifier = _notifier_context()
    df_dict = _minimal_df_dict()

    date_period_key = naming["datePeriodName"]
    selected_periods_key = naming["selectedPeriods"]

    chart_dict = {selected_periods_key: ["dummy"]}
    param_dict = {date_period_key: "FY2024"}

    # Act
    out_params, _ = run_charting(
        df_dict,
        indexCols=[],
        valueCols=[],
        paramDict=param_dict,
        chartDict=chart_dict,
        _expander=None,
        notifier=notifier,
    )

    # Assert
    assert chart_dict[date_period_key] == "FY2024"
