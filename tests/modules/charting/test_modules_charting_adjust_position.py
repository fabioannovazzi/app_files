import pytest
import polars as pl

from modules.charting import adjust_position as ap


class _Ann:
    def __init__(self, text: str, y: float):
        self.text = text
        self.y = y


class _Fig:
    def __init__(self, annotations):
        class _Layout:
            def __init__(self, ann):
                self.annotations = ann

        self.layout = _Layout(list(annotations))


@pytest.mark.parametrize(
    "n_titles, expected_adj",
    [
        (4, 0.01),  # boundary: <= 4
        (5, 0.003),  # boundary: > 4
    ],
)
def test_move_labels_up_marimekko_small_multiples_boundary(n_titles, expected_adj):
    naming = ap.get_naming_params()
    titles = [f"T{i}" for i in range(n_titles)]
    anns = [_Ann(t, 0.2) for t in titles] + [_Ann("OTHER", 0.3)]
    fig = _Fig(anns)

    chart_dict = {
        naming["plotSmallMultiplesOtherCharts"]: True,
        naming["chosenChart"]: naming["marimekkoChart"],
    }

    out = ap.move_labels_up(fig, chart_dict, titles)

    # Only labels in titles are moved, by expected_adj; others unchanged
    moved = [ann for ann in out.layout.annotations if ann.text in titles]
    assert all(abs(ann.y - (0.2 + expected_adj)) < 1e-12 for ann in moved)
    other = next(ann for ann in out.layout.annotations if ann.text == "OTHER")
    assert other.y == 0.3


def test_move_labels_up_select_dimensions_uses_chart_list_when_no_x_axis():
    naming = ap.get_naming_params()
    # uniqueItems intentionally different; function should use chart list instead
    unique_items = ["X1", "X2"]
    chart_list = ["A", "B"]
    anns = [_Ann("A", 0.0), _Ann("B", 0.5), _Ann("Z", 1.0)]
    fig = _Fig(anns)

    chart_dict = {
        naming["selectDimensionsToPlot"]: chart_list,
        # Do NOT include xAxisDimension to trigger chart_list usage
    }

    out = ap.move_labels_up(fig, chart_dict, unique_items)

    # For len(chart_list)=2, adjustment should be 0.05
    adj = 0.05
    a = next(ann for ann in out.layout.annotations if ann.text == "A")
    b = next(ann for ann in out.layout.annotations if ann.text == "B")
    z = next(ann for ann in out.layout.annotations if ann.text == "Z")
    assert a.y == pytest.approx(0.0 + adj)
    assert b.y == pytest.approx(0.5 + adj)
    assert z.y == 1.0  # unchanged


def test_move_labels_up_no_conditions_no_change():
    # Empty chartDict should not move anything
    anns = [_Ann("A", 0.1), _Ann("B", 0.2)]
    fig = _Fig(anns)

    out = ap.move_labels_up(fig, {}, ["A", "B"])  # uniqueItems ignored
    assert [ann.y for ann in out.layout.annotations] == [0.1, 0.2]


def test_get_label_length_mixed_types():
    naming = ap.get_naming_params()
    work_col = naming["workColumn"]
    # Mixed types coerced to Utf8; '123' counted as length 3
    ser = pl.Series(work_col, [123, "abcd", "éé"], dtype=pl.Utf8, strict=False)
    df = pl.DataFrame({work_col: ser})

    max_len = ap.get_label_length(df)
    assert isinstance(max_len, int)
    assert max_len == 4


def test_get_waterfall_plot_height_and_width_variable_dim():
    naming = ap.get_naming_params()
    work_col = naming["workColumn"]
    df = pl.DataFrame({work_col: ["a", "bbb", "cccccc"]})  # max len = 6, rows = 3

    chart_dict = {naming["processingChoice"]: naming["runVariableDimensionalAnalysis"]}

    height, width, max_len = ap.get_waterfall_plot_height_and_width(
        df, chart_dict, None, None
    )

    assert max_len == 6
    # height = 120 + 25*3 + 5 = 200; width = 6*5 + 250 = 280
    assert height == 200
    assert width == 280


def test_get_waterfall_plot_height_and_width_small_multiples_branch():
    naming = ap.get_naming_params()
    work_col = naming["workColumn"]
    df = pl.DataFrame({work_col: ["ab", "cd", "ef", "gh"]})  # rows=4, max len=2

    chart_dict = {
        naming["processingChoice"]: naming[
            "runOneDimensionalAnalysis"
        ],  # not variable-dim branch
        naming["plotSmallMultiplesWaterfall"]: True,
    }

    height, width, max_len = ap.get_waterfall_plot_height_and_width(
        df, chart_dict, numberOfRows=2, numberOfCols=3
    )

    assert max_len == 2
    # singleRowHeight=20 in this branch
    # height = 120 + ((20*4) + (5+35)) * 2 = 120 + (80+40)*2 = 360
    # width  = (2*5) + (250*3) = 10 + 750 = 760
    assert height == 360
    assert width == 760


def test_get_y1_y0_values_supports_more_than_nine_waterfall_panels():
    arrow_positions = []

    for row in [1, 2, 3, 4]:
        y0, y1, yshift, line_color = ap.get_y1_y0_values(
            12,
            False,
            True,
            row,
            False,
            "red",
            {},
            row,
        )
        arrow_positions.append(y0)
        assert y0 == pytest.approx(y1)
        assert yshift == 0
        assert line_color == "red"

    assert arrow_positions == sorted(arrow_positions, reverse=True)


def test_get_y1_y0_values_keeps_legacy_three_row_positions():
    y0, y1, yshift, line_color = ap.get_y1_y0_values(
        9,
        False,
        True,
        1,
        False,
        "green",
        {},
        1,
    )

    assert y0 == pytest.approx(0.72)
    assert y1 == pytest.approx(0.72)
    assert yshift == 0
    assert line_color == "green"
