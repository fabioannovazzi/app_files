import sys
import types
import importlib
import pytest


@pytest.fixture()
def logic_module(monkeypatch):
    """Import variance_bridge_logic with lightweight stubs to avoid heavy deps.

    Stubs:
    - modules.charting.chart_primitives.get_color_dictionary
    - modules.utilities.config.get_naming_params
    """
    # Provide minimal stub for chart primitives
    fake_chart = types.ModuleType("modules.charting.chart_primitives")
    fake_chart.get_color_dictionary = lambda chart_dict: {"color": "stub"}
    monkeypatch.setitem(sys.modules, "modules.charting.chart_primitives", fake_chart)

    # Provide minimal stub for config naming params
    fake_config = types.ModuleType("modules.utilities.config")
    fake_config.get_naming_params = lambda: {
        "varianceAggregation": "agg_key",
        "runOneDimensionalAnalysis": "Run Analysis",
    }
    monkeypatch.setitem(sys.modules, "modules.utilities.config", fake_config)

    # Ensure a fresh import uses our stubs
    sys.modules.pop("src.variance_bridge_logic", None)
    return importlib.import_module("src.variance_bridge_logic")


@pytest.mark.parametrize(
    "bridge_submit, submit_clicked, chart_unchanged, expected",
    [
        (False, True, True, True),   # golden path: manual submit with unchanged chart
        (False, True, False, False), # negative: submit but chart changed
        (True, False, False, True),  # bridge submit overrides others
        (False, False, True, False), # nothing triggered
    ],
)
def test_should_process_variance_cases(logic_module, bridge_submit, submit_clicked, chart_unchanged, expected):
    should_process = logic_module.should_process_variance
    assert should_process(bridge_submit, submit_clicked, chart_unchanged) is expected


def test_prepare_parameters_sets_aggregation_and_returns_color_and_message(logic_module):
    prepare = logic_module.prepare_parameters_for_each_variance_calculation
    chart = {"other": 123}

    new_chart, color_map, message = prepare(chart, "PRICE")

    # Asserts: aggregation set, color map passed through, label returned, dict mutated
    assert new_chart is chart
    assert new_chart["agg_key"] == "PRICE"
    assert new_chart["other"] == 123
    assert color_map == {"color": "stub"}
    assert message == "Run Analysis"


def test_prepare_parameters_overwrites_existing_key_preserves_others(logic_module):
    prepare = logic_module.prepare_parameters_for_each_variance_calculation
    chart = {"agg_key": "OLD", "x": 1}

    updated_chart, _, _ = prepare(chart, "NEW")

    assert updated_chart["agg_key"] == "NEW"
    assert updated_chart["x"] == 1


def test_prepare_parameters_missing_naming_key_raises_keyerror(monkeypatch, logic_module):
    # Override the already-imported function reference to simulate missing key
    monkeypatch.setattr(
        logic_module,
        "get_naming_params",
        lambda: {"runOneDimensionalAnalysis": "Run Analysis"},
        raising=True,
    )

    prepare = logic_module.prepare_parameters_for_each_variance_calculation
    with pytest.raises(KeyError):
        prepare({}, "BRAND")
