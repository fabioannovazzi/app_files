from __future__ import annotations

from typing import Any, List

import polars as pl
import pytest

import modules.layout.filter_widgets as fw
from modules.utilities.config import get_naming_params
from modules.utilities.session_context import get_session_state


class DummyContainer:
    """Minimal context manager to satisfy `with col_array[i]:` blocks."""

    def __enter__(self):  # pragma: no cover - trivial
        return self

    def __exit__(self, *exc):  # pragma: no cover - trivial
        return False


@pytest.fixture(autouse=True)
def _clear_ui_state():
    get_session_state().clear()
    yield
    get_session_state().clear()


def _stub_ui_base(monkeypatch: pytest.MonkeyPatch) -> None:
    """Install no‑op stubs for UI methods used by the widgets module."""

    # Silence visuals and text outputs
    monkeypatch.setattr(fw.ui, "caption", lambda *a, **k: None)
    monkeypatch.setattr(fw.ui, "markdown", lambda *a, **k: None)
    monkeypatch.setattr(fw.ui, "write", lambda *a, **k: None)
    monkeypatch.setattr(fw.ui, "error", lambda *a, **k: None)


def _stub_multiselect(monkeypatch: pytest.MonkeyPatch, include: List[str] | None, exclude: List[str] | None) -> None:
    """Stub `ui.multiselect` to return provided selections by label."""

    naming = get_naming_params()
    include_label = naming["chooseToIncludeItemsLabel"]
    exclude_label = naming["chooseToExcludeItemsLabel"]

    def _multi(label: str, *, options: list[Any], default=None, **_k):
        if label == include_label:
            return include if include is not None else (default or [])
        if label == exclude_label:
            return exclude if exclude is not None else (default or [])
        return default or []

    monkeypatch.setattr(fw.ui, "multiselect", _multi)


def _stub_searchable_selectbox(monkeypatch: pytest.MonkeyPatch, returns: list[str]) -> None:
    """Stub `searchable_selectbox_with_state` to return successive values from `returns`."""

    seq = returns.copy()

    def _selectbox(_label: str, _options: list[str], **_k) -> str:
        return seq.pop(0) if seq else _options[_k.get("index", 0)]

    monkeypatch.setattr(fw, "searchable_selectbox_with_state", _selectbox)


def _make_cols(n: int) -> list[DummyContainer]:
    return [DummyContainer() for _ in range(n)]


def test_get_items_to_filter_categorical_includes_selection(monkeypatch: pytest.MonkeyPatch) -> None:
    _stub_ui_base(monkeypatch)
    # Arrange
    naming = get_naming_params()
    nothing = naming["nothingFilteredName"]
    column_hash_key = naming["columnHash"]
    top_word_key = naming["topWordDict"]
    to_include = naming["toIncludeItems"]
    to_exclude = naming["toExcludeItems"]

    df = pl.DataFrame({"category": ["A", "B", "C"]})
    index_cols = [nothing, "category"]
    param_dict = {column_hash_key: 1, top_word_key: {"category": ["A", "B", "C"]}}
    filter_dict: dict[str, dict[str, list[str]]] = {}
    number_filter_dict: dict[str, dict[str, Any]] = {}
    col_array = _make_cols(3)

    _stub_searchable_selectbox(monkeypatch, ["category"])  # choose the column
    _stub_multiselect(monkeypatch, include=["A", "C"], exclude=["B"])  # user choices

    # Act
    fdict, ndict, to_filter, remaining = fw.get_items_to_filter(
        df, index_cols, param_dict, filter_dict, number_filter_dict, 1, col_array, {}
    )

    # Assert
    assert to_filter is True
    assert "category" in fdict and to_include in fdict["category"]
    assert fdict["category"][to_include] == ["A", "C"]
    assert fdict["category"][to_exclude] == ["B"]
    assert ndict.get("category", {}) == {}
    assert "category" not in remaining and nothing in remaining


def test_get_items_to_filter_returns_no_filter_when_none_selected(monkeypatch: pytest.MonkeyPatch) -> None:
    _stub_ui_base(monkeypatch)
    # Arrange
    naming = get_naming_params()
    nothing = naming["nothingFilteredName"]
    column_hash_key = naming["columnHash"]
    top_word_key = naming["topWordDict"]

    df = pl.DataFrame({"category": ["A", "B"]})
    index_cols = [nothing, "category"]
    param_dict = {column_hash_key: 42, top_word_key: {"category": ["A", "B"]}}
    filter_dict: dict[str, dict[str, list[str]]] = {}
    number_filter_dict: dict[str, dict[str, Any]] = {}
    col_array = _make_cols(3)

    _stub_searchable_selectbox(monkeypatch, [nothing])  # user picks "None"
    _stub_multiselect(monkeypatch, include=[], exclude=[])

    # Act
    fdict, ndict, to_filter, remaining = fw.get_items_to_filter(
        df, index_cols, param_dict, filter_dict, number_filter_dict, 1, col_array, {}
    )

    # Assert
    assert to_filter is False
    assert fdict == {}
    assert ndict == {}
    assert remaining == index_cols  # unchanged


def test_get_items_to_filter_numeric_slider_builds_number_filter(monkeypatch: pytest.MonkeyPatch) -> None:
    _stub_ui_base(monkeypatch)
    # Arrange: numeric column triggers slider path
    naming = get_naming_params()
    nothing = naming["nothingFilteredName"]
    column_hash_key = naming["columnHash"]
    top_word_key = naming["topWordDict"]
    to_include = naming["toIncludeItems"]

    df = pl.DataFrame({"age": [10, 20, 30]})
    index_cols = [nothing, "age"]
    param_dict = {column_hash_key: 7, top_word_key: {"age": ["10", "20", "30"]}}
    filter_dict: dict[str, dict[str, list[str]]] = {}
    number_filter_dict: dict[str, dict[str, Any]] = {}
    col_array = _make_cols(3)

    _stub_searchable_selectbox(monkeypatch, ["age"])  # choose numeric column

    # Patch slider inside the slider helper module used by get_items_to_filter
    import modules.layout.set_up_widgets as su

    def _slider(label: str, *, min_value: int, max_value: int, value: Any, **_k):
        # For include: shrink the upper bound so a filter is applied.
        if "include" in label.lower():
            return (min_value, max_value - 1)
        # For exclude: keep default (no filter)
        return (min_value, min_value)

    monkeypatch.setattr(su.ui, "slider", _slider)
    monkeypatch.setattr(su.ui, "caption", lambda *a, **k: None)

    # Act
    fdict, ndict, to_filter, remaining = fw.get_items_to_filter(
        df, index_cols, param_dict, filter_dict, number_filter_dict, 1, col_array, {}
    )

    # Assert: numeric filter applied, dicts populated accordingly
    assert to_filter is True
    assert fdict.get("age", {}) == {}
    assert ndict["age"][to_include] == (10, 29)
    assert "age" not in remaining


def test_make_filter_dict_integration_builds_chart_and_flags_filtered(monkeypatch: pytest.MonkeyPatch) -> None:
    _stub_ui_base(monkeypatch)
    # Arrange
    naming = get_naming_params()
    nothing = naming["nothingFilteredName"]
    filter_dict_name = naming["filterDictName"]
    number_filter_dict_name = naming["numberFilterDictName"]
    processing_choice = naming["processingChoice"]
    period_name = naming["periodName"]
    is_filtered_key = naming["isFilteredKey"]
    column_hash_key = naming["columnHash"]
    top_word_key = naming["topWordDict"]
    to_include = naming["toIncludeItems"]

    df = pl.DataFrame({"category": ["A", "B"], period_name: ["2024", "2024"]})
    index_cols = ["category", period_name]
    param_dict = {column_hash_key: 99, top_word_key: {"category": ["A", "B"]}}
    chart_dict: dict[str, Any] = {processing_choice: "any"}
    col_array = _make_cols(4)

    # First filter selection returns the real column, then "None" to stop.
    _stub_searchable_selectbox(monkeypatch, ["category", nothing])
    _stub_multiselect(monkeypatch, include=["A"], exclude=[])

    # radio is shown only if any filter active; return the default
    monkeypatch.setattr(fw.ui, "radio", lambda *a, options, index=1, **k: options[index])

    # Act
    p_out, c_out = fw.make_filter_dict(df, index_cols, param_dict, chart_dict, {}, col_array)

    # Assert
    assert p_out[is_filtered_key] is True
    assert filter_dict_name in c_out and number_filter_dict_name in c_out
    assert c_out[filter_dict_name]["category"][to_include] == ["A"]
    # Period column is not offered for filtering
    assert period_name not in c_out[filter_dict_name]
