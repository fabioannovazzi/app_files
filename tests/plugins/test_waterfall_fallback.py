"""Regression tests for mixed-trace waterfall fallback rendering."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import ModuleType

import pytest

__all__: list[str] = []


def load_vendor_draw_waterfall() -> ModuleType:
    path = (
        Path(__file__).resolve().parents[2]
        / "plugins/_shared/variance/vendor/modules/charting/draw_waterfall.py"
    )
    spec = importlib.util.spec_from_file_location("waterfall_fallback_regression", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


@pytest.mark.parametrize("panel_count", [1, 2, 4])
def test_waterfall_fallback_ignores_supporting_traces(
    tmp_path: Path, panel_count: int
) -> None:
    import plotly.graph_objects as go

    waterfall = load_vendor_draw_waterfall()
    fig = go.Figure(
        data=[
            go.Waterfall(
                orientation="h",
                measure=["absolute", "relative", "total"],
                y=["Budget", "Movement", "Actual"],
                x=[1800, 100, 1900],
            )
        ]
        * panel_count
    )
    fig.update_layout(title="Actual vs Budget")
    expected = tmp_path / "waterfall_only.png"
    waterfall.write_waterfall_fallback_png(fig, str(expected))
    fig.add_trace(go.Scatter(x=[100], y=["Movement"], mode="text", text=["5.6% "]))
    fig.add_trace(go.Bar(x=[1800], y=["Budget"], orientation="h"))
    actual = tmp_path / "with_supporting_traces.png"

    waterfall.write_waterfall_fallback_png(fig, str(actual))

    assert actual.read_bytes() == expected.read_bytes()


def test_waterfall_fallback_rejects_figure_without_waterfall(tmp_path: Path) -> None:
    import plotly.graph_objects as go

    waterfall = load_vendor_draw_waterfall()
    fig = go.Figure(go.Scatter(x=[1], y=[2]))

    with pytest.raises(ValueError, match="No waterfall traces"):
        waterfall.write_waterfall_fallback_png(fig, str(tmp_path / "invalid.png"))
