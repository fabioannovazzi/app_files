import pytest
import polars as pl
import plotly.graph_objects as go

from modules.charting.update_layouts import (
    get_uniform_text_min_size,
    update_histogram_layout,
    update_pareto_layout_and_get_messages,
    update_stacked_bar_layout,
)


def test_get_uniform_text_min_size_golden_and_boundary():
    # Arrange
    naming = {"uniformTextMinSize": "minText"}
    cfg1 = {"minText": "12"}  # string input
    cfg2 = {"minText": 0}  # boundary: zero value

    # Act
    v1 = get_uniform_text_min_size(cfg1, naming)
    v2 = get_uniform_text_min_size(cfg2, naming)

    # Assert
    assert v1 == 12 and isinstance(v1, int)
    assert v2 == 0 and isinstance(v2, int)


def test_get_uniform_text_min_size_missing_key_raises_keyerror():
    # Arrange
    naming = {}  # missing "uniformTextMinSize"
    cfg = {"minText": 10}

    # Act / Assert
    with pytest.raises(KeyError):
        _ = get_uniform_text_min_size(cfg, naming)


@pytest.mark.parametrize(
    "items, expected_height, expected_width",
    [
        (1, 500, 750),  # baseHeight=500; height=500; width=int(500*1.5)
        (3, 600, 900),  # baseHeight=300; height capped at 600; width=int(600*1.5)
    ],
)
def test_update_histogram_layout_sizes(
    monkeypatch, items, expected_height, expected_width
):
    # Arrange: stub config and naming lookups used inside the function
    def fake_get_naming_params():
        return {
            "fontChoice": "fontChoiceKey",
            "fontSizeText": "fontSizeKey",
            "goldenRatio": "goldenRatioKey",
        }

    def fake_get_config_params():
        return {
            "fontChoiceKey": "Arial",
            "fontSizeKey": 12,
            "goldenRatioKey": 1.5,
        }

    import modules.charting.update_layouts as U

    monkeypatch.setattr(U, "get_naming_params", fake_get_naming_params)
    monkeypatch.setattr(U, "get_config_params", fake_get_config_params)

    fig = go.Figure()

    # Act
    out = update_histogram_layout(fig, items)

    # Assert: width/height computed from golden ratio and item count
    assert out is fig
    assert fig.layout.height == expected_height
    assert fig.layout.width == expected_width
    # Key axis visibility settings
    assert fig.layout.xaxis.visible is True
    assert fig.layout.yaxis.visible is False


def test_update_stacked_bar_layout_reserves_title_top_margin():
    from modules.utilities.config import get_config_params, get_naming_params

    names = get_naming_params()
    config = get_config_params()
    chart = {names["chosenChart"]: names["stackedBarChart"]}
    expected_margin = config[names["annotationDict"]][names["stackedBarChart"]][
        "topMargin"
    ]
    fig = go.Figure()

    out = update_stacked_bar_layout(fig, chart)

    assert out is fig
    assert fig.layout.margin.t == expected_margin


@pytest.mark.parametrize(
    "show_rank, expected_autorange", [(True, "reversed"), (False, None)]
)
def test_update_pareto_layout_and_get_messages_respects_show_rank(
    monkeypatch, show_rank, expected_autorange
):
    # Arrange: minimal naming and chart dictionaries
    def fake_get_naming_params():
        return {
            "showRank": "showRank",
            "metricsToPlot": "metricsToPlot",
            "chosenChart": "chosenChart",
            "countColumn": "countColumn",
            "showOnly": "showOnly",
            "showAll": "showAll",
            "showTop": "top",
            "showBottom": "bottom",
        }

    chart_dict = {
        "showRank": show_rank,
        "metricsToPlot": ["metricA"],
        "chosenChart": "pareto",
        "countColumn": "Count",
        "showOnly": "top",
        "showAll": "all",
        "top": "top",
        "bottom": "bottom",
    }
    param_dict = {"ok": True}

    # Stub the heavy collaborators invoked by the function
    def fake_make_title(
        df,
        chosen_chart,
        param_dict_in,
        count_label,
        first_metric,
        chart_dict_in,
        period,
        _,
    ):
        # Return a mutated param_dict to verify it flows through
        mutated = dict(param_dict_in)
        mutated["mutated"] = True
        return "Title", mutated, chart_dict_in

    def fake_update_pareto_layout(
        fig, chart_dict_in, param_dict_in, metric, showYTicklabels, bargap, df
    ):
        # Return fig unchanged and a fixed width
        return fig, 0, 800, chart_dict_in

    def fake_get_user_message(
        fig, chosen_chart, period, _a, param_dict_in, chart_dict_in, df, width, _b
    ):
        return fig, "message"

    def passthrough_fig(*args, **kwargs):
        # First arg is the figure
        return args[0]

    import modules.charting.update_layouts as U

    monkeypatch.setattr(U, "get_naming_params", fake_get_naming_params)
    monkeypatch.setattr(
        U, "make_stacked_pareto_and_pareto_chart_title", fake_make_title
    )
    monkeypatch.setattr(U, "update_pareto_layout", fake_update_pareto_layout)
    monkeypatch.setattr(U, "get_user_message", fake_get_user_message)
    monkeypatch.setattr(U, "add_title_as_annotation", passthrough_fig)
    monkeypatch.setattr(U, "add_message_as_annotation", passthrough_fig)
    monkeypatch.setattr(U, "enable_draw_shapes", passthrough_fig)

    fig = go.Figure()
    df = pl.DataFrame({"Dimension": ["A", "B"], "metricA": [1, 2]})

    # Act
    out_fig, out_params = update_pareto_layout_and_get_messages(
        fig,
        period="2024",
        chartDict=chart_dict,
        paramDict=param_dict,
        metric="metricA",
        showYTicklabels=True,
        bargap=0.1,
        df=df,
    )

    # Assert: y-axis autorange reversed only when showRank is True
    assert out_fig is fig
    assert out_params.get("mutated") is True
    assert getattr(fig.layout.yaxis, "autorange", None) == expected_autorange
