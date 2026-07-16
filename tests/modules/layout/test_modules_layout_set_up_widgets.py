import types

import pytest

from modules.layout import set_up_widgets as sut


def test_get_hashed_key_for_widgets_truthy_and_falsy():
    # Arrange / Act / Assert
    assert sut.get_hashed_key_for_widgets("base", None) == "base"
    assert sut.get_hashed_key_for_widgets("base", 0) == "base"
    assert sut.get_hashed_key_for_widgets("base", "") == "base"
    assert sut.get_hashed_key_for_widgets("base", 5) == "base_5"
    assert sut.get_hashed_key_for_widgets("base", "abc") == "base_abc"


def test_selectbox_with_state_builds_key_and_returns_value(monkeypatch):
    # Arrange
    captured = {}

    def fake_searchable_selectbox_with_state(*, label, options, key, index, **kwargs):  # type: ignore[no-redef]
        captured.update({
            "label": label,
            "options": options,
            "key": key,
            "index": index,
            "kwargs": kwargs,
        })
        return options[index]

    monkeypatch.setattr(sut, "searchable_selectbox_with_state", fake_searchable_selectbox_with_state)

    options = ["a", "b", "c"]

    # Act
    result = sut.selectbox_with_state(
        name="field",
        column_hash="colhash",
        label="Choose",
        options=options,
        index=2,
        placeholder="pick one",
    )

    # Assert
    assert result == "c"
    assert captured["key"] == "field_colhash"
    assert captured["label"] == "Choose"
    # extra kwargs are forwarded
    assert captured["kwargs"]["placeholder"] == "pick one"


def test_selectbox_with_state_uses_base_key_when_hash_falsy(monkeypatch):
    # Arrange
    captured = {}

    def fake_searchable_selectbox_with_state(*, label, options, key, index, **kwargs):  # type: ignore[no-redef]
        captured.update({"key": key, "index": index})
        return options[index]

    monkeypatch.setattr(sut, "searchable_selectbox_with_state", fake_searchable_selectbox_with_state)

    # Act
    result = sut.selectbox_with_state(
        name="field",
        column_hash=0,  # falsy -> base key
        label="Choose",
        options=[10, 20, 30],
    )

    # Assert
    assert result == 10  # default index=0
    assert captured["key"] == "field"
    assert captured["index"] == 0


@pytest.mark.parametrize(
    "param_setup, expect_add_parse_called",
    [
        ({"is_ds": True, "is_upload": True}, True),  # golden path
        ({"is_ds": True, "is_upload": False}, False),  # dataset ok, no upload
        ({}, False),  # dataset flag missing
    ],
)
def test_set_up_join_dataset_widgets_branches(monkeypatch, param_setup, expect_add_parse_called):
    # Arrange: stub naming params so function looks up our keys
    def fake_get_naming_params():
        return {
            "isdataset": "is_ds",
            "isDataUploaded": "is_upload",
        }

    monkeypatch.setattr(sut, "get_naming_params", fake_get_naming_params)

    # Counters to validate which helpers are invoked
    calls = {"neg_zero": 0, "drop_dups": 0, "add_dims": 0, "parse": 0}

    def fake_neg_to_zero(param_dict, widget_dict, col):  # type: ignore[no-redef]
        calls["neg_zero"] += 1
        widget_dict = dict(widget_dict)
        widget_dict["neg_zero_called"] = True
        return widget_dict

    def fake_drop_dups(param_dict, widget_dict, col):  # type: ignore[no-redef]
        calls["drop_dups"] += 1
        widget_dict = dict(widget_dict)
        widget_dict["drop_duplicates_called"] = True
        return widget_dict

    def fake_add_dims(param_dict, col):  # type: ignore[no-redef]
        calls["add_dims"] += 1
        new = dict(param_dict)
        new["added"] = True
        return new

    def fake_parse(param_dict):  # type: ignore[no-redef]
        calls["parse"] += 1
        new = dict(param_dict)
        new["parsed"] = True
        return new

    monkeypatch.setattr(sut, "set_up_negative_values_to_zero_widget", fake_neg_to_zero)
    monkeypatch.setattr(sut, "set_up_drop_duplicates_widget", fake_drop_dups)
    monkeypatch.setattr(sut, "set_up_add_dimensions_widget", fake_add_dims)
    monkeypatch.setattr(sut, "parse_dimension_datasets", fake_parse)

    param = dict(param_setup)  # copy
    data_prep = {}
    col1_array = [object()]

    # Act
    out_param, out_widgets = sut.set_up_join_dataset_widgets(param, data_prep, col1_array)

    # Assert: the two prep helpers always run
    assert calls["neg_zero"] == 1
    assert calls["drop_dups"] == 1
    assert out_widgets.get("neg_zero_called") is True
    assert out_widgets.get("drop_duplicates_called") is True

    # add/parse only when both flags are True
    if expect_add_parse_called:
        assert calls["add_dims"] == 1
        assert calls["parse"] == 1
        assert out_param.get("added") is True
        assert out_param.get("parsed") is True
    else:
        assert calls["add_dims"] == 0
        assert calls["parse"] == 0
        assert "added" not in out_param and "parsed" not in out_param


def test_set_up_date_parameters_widgets_valid_colarray_calls_all_helpers(monkeypatch):
    """All helper widgets run when enough columns are provided."""
    monkeypatch.setattr(
        sut, "get_naming_params", lambda: {"datasetParametersLabel": "lbl"}
    )
    monkeypatch.setattr(sut, "is_valid_lazyframe", lambda _df: True)

    calls: list[tuple[str, object]] = []

    def fake_select_date_aggregation(df, param, chart, auto, col):  # type: ignore[no-redef]
        calls.append(("date", col))
        return chart

    def fake_select_by_fiscal_year(param, chart, auto, col):  # type: ignore[no-redef]
        calls.append(("fiscal", col))
        return chart

    def fake_select_if_year_before(param, chart, auto, col):  # type: ignore[no-redef]
        calls.append(("year_before", col))
        return chart

    def fake_select_most_recent_period(df, param, chart, auto, col):  # type: ignore[no-redef]
        calls.append(("most_recent", col))
        return chart, param

    def fake_select_period_order(chart, auto, param, col):  # type: ignore[no-redef]
        calls.append(("order", col))
        return chart

    monkeypatch.setattr(sut, "select_date_aggregation", fake_select_date_aggregation)
    monkeypatch.setattr(sut, "select_by_fiscal_year", fake_select_by_fiscal_year)
    monkeypatch.setattr(sut, "select_if_year_before", fake_select_if_year_before)
    monkeypatch.setattr(sut, "select_most_recent_period", fake_select_most_recent_period)
    monkeypatch.setattr(sut, "select_period_order", fake_select_period_order)

    chart, param = {}, {}
    col_array = ["c0", "c1", "c2"]

    out_chart, out_param = sut.set_up_date_parameters_widgets(
        object(), param, chart, {}, col_array
    )

    assert out_chart is chart and out_param is param
    assert calls == [
        ("date", "c0"),
        ("fiscal", "c1"),
        ("year_before", "c1"),
        ("most_recent", "c2"),
        ("order", "c0"),
    ]


def test_set_up_date_parameters_widgets_short_colarray_warns(monkeypatch):
    """A warning is shown and helpers are skipped when columns are missing."""
    monkeypatch.setattr(
        sut, "get_naming_params", lambda: {"datasetParametersLabel": "lbl"}
    )

    warned: dict[str, str] = {}

    def fake_warning(msg: str) -> None:  # type: ignore[no-redef]
        warned["msg"] = msg

    monkeypatch.setattr(sut, "show_warning_ui", fake_warning)

    def unexpected(*_a, **_k):  # type: ignore[no-redef]
        raise AssertionError("helper should not be called")

    monkeypatch.setattr(sut, "is_valid_lazyframe", unexpected)
    monkeypatch.setattr(sut, "select_date_aggregation", unexpected)
    monkeypatch.setattr(sut, "select_by_fiscal_year", unexpected)
    monkeypatch.setattr(sut, "select_if_year_before", unexpected)
    monkeypatch.setattr(sut, "select_most_recent_period", unexpected)
    monkeypatch.setattr(sut, "select_period_order", unexpected)

    chart, param = {}, {}
    out_chart, out_param = sut.set_up_date_parameters_widgets(object(), param, chart, {}, [])

    assert out_chart is chart and out_param is param
    assert warned["msg"] == "Not enough columns to display date-parameter widgets."
