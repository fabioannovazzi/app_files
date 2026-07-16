from modules.charting.chart_primitives import get_color_dictionary
from modules.utilities.config import get_naming_params

__all__ = [
    "should_process_variance",
    "prepare_parameters_for_each_variance_calculation",
]


def should_process_variance(
    bridge_submit: bool, submit_clicked: bool, chart_unchanged: bool
) -> bool:
    """Return True if charts should be recalculated."""
    return bridge_submit or (submit_clicked and chart_unchanged)


def prepare_parameters_for_each_variance_calculation(
    chart_dict: dict, element: str
) -> tuple[dict, dict, str]:
    """Set aggregation and return color mapping and message."""
    naming = get_naming_params()
    variance_key = naming["varianceAggregation"]
    run_label = naming["runOneDimensionalAnalysis"]
    color_dict = get_color_dictionary(chart_dict)
    message = run_label
    chart_dict[variance_key] = element
    return chart_dict, color_dict, message
