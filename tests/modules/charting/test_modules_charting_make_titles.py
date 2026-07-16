import pytest


@pytest.fixture()
def stub_title_env(monkeypatch):
    """Stub dependencies used by title builders to keep tests deterministic."""
    from modules.charting import make_titles as mt

    naming = {
        "totalName": "Total",
        "percentSuffix": "%",
        "plotSmallMultiplesOtherCharts": "plotSmallMultiples",
        "metricsToPlot": "metricsToPlot",
        "overlayChartMetric": "overlayChartMetric",
        "plotTitleText": "plotTitleText",
        "aggregateUniquesByDimension": "aggregateUniquesByDimension",
        "countColumn": "countColumn",
        "selectedPeriods": "selectedPeriods",
        "xAxisDimension": "xAxisDimension",
        "nothingFilteredName": "All",
    }

    # Naming/config
    monkeypatch.setattr(mt, "get_naming_params", lambda: naming)

    # Simple, predictable helpers
    monkeypatch.setattr(
        mt, "set_break_row_tag", lambda chartDict, chosenChart: "<br>"
    )
    monkeypatch.setattr(
        mt,
        "make_like_for_like_title_suffix",
        lambda chartDict, paramDict, metric: "[LfL]",
    )
    monkeypatch.setattr(
        mt,
        "get_filter_text_or_company_name",
        lambda chartDict, paramDict: ("ACME", paramDict, chartDict),
    )

    def fake_get_currency_name(chartDict, paramDict, metric):
        if metric == "Revenue":
            return "USD", paramDict
        if metric == "Profit":
            return "EUR", paramDict
        return "", paramDict  # no currency for other metrics

    monkeypatch.setattr(mt, "get_currency_name", fake_get_currency_name)
    monkeypatch.setattr(mt, "change_metric_if_cost_analysis", lambda m, c: m)
    monkeypatch.setattr(
        mt, "get_rolling_and_year_to_date_period", lambda d, p, c, z: d
    )
    monkeypatch.setattr(
        mt,
        "explain_metrics_for_stacked_column_prompt",
        lambda chartDict, c1, c2, m1, m2: chartDict,
    )

    return naming


def test_stacked_column_chart_title_overlay_and_currency(stub_title_env):
    from modules.charting.make_titles import make_stacked_column_chart_title

    chartDict = {
        stub_title_env["metricsToPlot"]: ["Revenue", "Profit"],
        stub_title_env["plotSmallMultiplesOtherCharts"]: True,
        stub_title_env["overlayChartMetric"]: True,
    }
    paramDict = {}

    title, out_params, out_chart = make_stacked_column_chart_title(
        df=None,
        chosenChart="stacked column",
        paramDict=paramDict,
        dimension=stub_title_env["totalName"],
        metric="Revenue",
        chartDict=chartDict,
        period1="2023",
        element=None,
    )

    # Shape and side-effect
    assert isinstance(title, str)
    assert out_params is paramDict  # same object passed through
    assert out_chart[stub_title_env["plotTitleText"]] == title

    # Semantics
    assert title.startswith("ACME")
    assert "Bar chart:" in title and ". Line chart:" in title
    assert "<b> Revenue, Profit</b>" in title  # metrics joined in bar chart
    assert " in USD" in title  # base currency tag
    assert ". Line chart: <b>Profit</b> in EUR" in title  # overlay + currency
    assert title.endswith("2023")
    assert "  " not in title  # double spaces collapsed


def test_stacked_column_chart_title_no_overlay_no_currency(stub_title_env):
    from modules.charting.make_titles import make_stacked_column_chart_title

    chartDict = {stub_title_env["metricsToPlot"]: ["Sales"]}
    paramDict = {}

    title, out_params, out_chart = make_stacked_column_chart_title(
        df=None,
        chosenChart="stacked column",
        paramDict=paramDict,
        dimension=stub_title_env["totalName"],  # omits " by ..."
        metric="Sales",
        chartDict=chartDict,
        period1="2023",
        element=None,
    )

    assert out_chart[stub_title_env["plotTitleText"]] == title
    assert "Bar chart:" not in title and ". Line chart:" not in title
    assert "<b>Sales</b>" in title
    assert " in USD" not in title  # no currency for Sales metric
    assert "  " not in title


def test_pareto_title_with_aggregate_and_currency(stub_title_env):
    from modules.charting.make_titles import (
        make_stacked_pareto_and_pareto_chart_title,
    )

    chartDict = {
        stub_title_env["aggregateUniquesByDimension"]: True,
        stub_title_env["countColumn"]: "count",
        stub_title_env["selectedPeriods"]: ["P0", "P1"],
    }
    paramDict = {}

    title, out_params, out_chart = make_stacked_pareto_and_pareto_chart_title(
        df=None,
        chosenChart="pareto",
        paramDict=paramDict,
        dimension="Category",
        metric="Revenue",
        chartDict=chartDict,
        period1="P0",  # equals first selected period
        element=None,
    )

    assert out_chart[stub_title_env["plotTitleText"]] == title
    assert "ABC by sorted Category Revenue" in title
    assert ", count by count" in title
    assert " in USD" in title
    assert title.endswith("P0")
    assert "  " not in title


def test_distribution_title_with_agg_dimension_and_currency(stub_title_env):
    from modules.charting.make_titles import make_distribution_charts_title

    chartDict = {
        stub_title_env["xAxisDimension"]: "Store",
    }
    paramDict = {}

    title, out_params, out_chart = make_distribution_charts_title(
        df=None,
        chosenChart="histogram",
        paramDict=paramDict,
        dimension="Region",
        metric="Revenue",
        chartDict=chartDict,
        period1="2023",
        element="2024",
    )

    assert out_chart[stub_title_env["plotTitleText"]] == title
    assert "<b>Revenue</b>" in title
    assert " aggregated by Store" in title
    assert " by Region " in title
    assert " in USD, " in title
    assert "2023 vs 2024" in title
    assert "  " not in title


def test_distribution_title_observation_and_no_dimension(stub_title_env):
    from modules.charting.make_titles import make_distribution_charts_title

    chartDict = {stub_title_env["xAxisDimension"]: stub_title_env["nothingFilteredName"]}
    paramDict = {}

    title, out_params, out_chart = make_distribution_charts_title(
        df=None,
        chosenChart="histogram",
        paramDict=paramDict,
        dimension=stub_title_env["totalName"],  # dimension omitted
        metric="Sales",  # no currency
        chartDict=chartDict,
        period1="2023",
        element="2024",
    )

    assert out_chart[stub_title_env["plotTitleText"]] == title
    assert " by observation" in title  # fallback when xAxisDimension == nothingFilteredName
    assert " by Region " not in title and " by Total " not in title  # no extra dimension
    assert "USD" not in title and "EUR" not in title
    assert "  " not in title
