import polars as pl

import modules.add_attributes.grouping as grp


def test_select_grouping_level_two_options_uses_radio_and_counts_correct(monkeypatch):
    # Arrange: small dataset with duplicates to test unique counts
    df = pl.DataFrame({
        "cat": ["A", "A", "B", "C"],  # 3 unique
        "subcat": ["x", "y", "x", "y"],  # 2 unique
    })
    lf = df.lazy()
    mapping = {"category_column": "cat", "subcategory_column": "subcat"}

    captured: dict = {}

    def fake_radio(label, options, index=0, format_func=None):
        captured["label"] = label
        captured["options"] = options
        captured["format_func"] = format_func
        # Pretend the user selects subcategory
        return "subcategory"

    monkeypatch.setattr(grp.ui, "radio", fake_radio)

    # Act
    choice, col = grp.select_grouping_level(mapping, lf)

    # Assert: returns chosen option and column name
    assert (choice, col) == ("subcategory", "subcat")
    # Radio called with both options and a formatter producing counts
    assert captured["options"] == ["category", "subcategory"]
    fmt = captured["format_func"]
    assert callable(fmt)
    # Labels should include the column name and correct unique counts (3 and 2)
    assert "cat" in fmt("category") and "3" in fmt("category")
    assert "subcat" in fmt("subcategory") and "2" in fmt("subcategory")


def test_select_grouping_level_only_one_level_defaults_and_informs(monkeypatch):
    # Arrange: only category column present
    df = pl.DataFrame({"cat": ["A", "B"]})
    lf = df.lazy()
    mapping = {"category_column": "cat"}

    infos: list[str] = []

    def fake_info(msg):
        infos.append(str(msg))

    monkeypatch.setattr(grp.ui, "info", fake_info)

    # Act
    choice, col = grp.select_grouping_level(mapping, lf)

    # Assert: defaults to category and informs via UI notifier
    assert (choice, col) == ("category", "cat")
    assert len(infos) == 1 and "Only one grouping level" in infos[0]


def test_select_grouping_level_no_levels_warns_and_returns_none(monkeypatch):
    # Arrange: mapping points to missing columns
    df = pl.DataFrame({"product": ["P1", "P2"]})
    lf = df.lazy()
    mapping = {"category_column": "cat", "subcategory_column": "subcat"}

    warnings: list[str] = []

    def fake_warning(msg):
        warnings.append(str(msg))

    monkeypatch.setattr(grp.ui, "warning", fake_warning)

    # Act
    choice, col = grp.select_grouping_level(mapping, lf)

    # Assert: no grouping available
    assert (choice, col) == ("none", None)
    assert len(warnings) == 1 and "No category fields detected" in warnings[0]
