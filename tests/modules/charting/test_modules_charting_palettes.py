import pytest

import modules.charting.palettes as palettes


@pytest.mark.parametrize(
    "theme_fn",
    [palettes.cirque_theme, palettes.modern_theme, palettes.buleAndGreen_theme],
)
def test_theme_structure_and_invariants(theme_fn):
    # Act
    cfg = theme_fn()

    # Assert: top-level shape and essential nested keys
    assert isinstance(cfg, dict)
    assert "config" in cfg and isinstance(cfg["config"], dict)
    inner = cfg["config"]
    for key in ("title", "axis", "header", "legend", "range"):
        assert key in inner
    # Legend contract and range families present
    assert inner["legend"]["labelLimit"] == 0
    for rng in ("category", "diverging", "heatmap", "ramp", "ordinal"):
        assert rng in inner["range"]


@pytest.mark.parametrize(
    "theme_fn,expected_category",
    [
        (
            palettes.cirque_theme,
            [
                "#4E6551",
                "#88A98C",
                "#4395A7",
                "#0F4E59",
                "#5A3C4B",
                "#B06B8B",
                "#DDA567",
                "#9F6027",
                "#BE8E31",
                "#EED069",
                "#4F5971",
            ],
        ),
        (
            palettes.modern_theme,
            [
                "#3C511B",
                "#83905A",
                "#7C982E",
                "#C7EA5B",
                "#854210",
                "#DA8545",
                "#FFC293",
                "#3C4255",
                "#184243",
                "#43C5D2",
                "#74E5E6",
            ],
        ),
        (
            palettes.buleAndGreen_theme,
            [
                "#1B3643",
                "#3B5C68",
                "#597F8E",
                "#7BA3AE",
                "#ACD5E5",
                "#776846",
                "#6E7743",
                "#4F5971",
                "#8B9450",
                "#C4CA78",
                "#e7e9c9",
            ],
        ),
    ],
)
def test_category_palettes_exact(theme_fn, expected_category):
    # Act
    cfg = theme_fn()

    # Assert exact palette and length
    category = cfg["config"]["range"]["category"]
    assert category == expected_category
    assert len(category) == 11


@pytest.mark.parametrize(
    "theme_fn",
    [palettes.cirque_theme, palettes.modern_theme, palettes.buleAndGreen_theme],
)
def test_theme_uses_font_from_config(monkeypatch, theme_fn):
    # Arrange: override config to a custom font and size
    monkeypatch.setattr(
        palettes,
        "get_config_params",
        lambda: {"fontChoice": "TestFont123", "fontSizeText": 13},
    )

    # Act
    cfg = theme_fn()

    # Assert: multiple places pick up the configured font
    title_font = cfg["config"]["title"]["font"]
    legend_font = cfg["config"]["legend"]["labelFont"]
    assert title_font == "TestFont123"
    assert legend_font == "TestFont123"


def test_missing_font_key_raises_keyerror(monkeypatch):
    # Arrange: remove the expected font key from config
    monkeypatch.setattr(
        palettes,
        "get_config_params",
        lambda: {"fontSizeText": 12},
    )

    # Act / Assert: direct key access should raise KeyError
    with pytest.raises(KeyError):
        palettes.cirque_theme()
