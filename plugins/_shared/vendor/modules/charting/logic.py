from __future__ import annotations

from src.charting_logic import plot_one_period_datasets as core_plot_one_period_datasets

__all__ = ["plot_one_period_datasets", "should_plot"]


def should_plot(
    *, apply_plot: bool, submit_plot: bool, chart_not_changed: bool
) -> bool:
    """Return True when charting should run based on explicit inputs."""

    return apply_plot or (submit_plot and chart_not_changed)


def plot_one_period_datasets(
    df_dict,
    index_cols,
    value_cols,
    param_dict,
    chart_dict,
    output_column,
) -> tuple[dict, str | None]:
    """Run charting logic and return updated params with an optional message."""

    param_dict, sample_message = core_plot_one_period_datasets(
        df_dict,
        index_cols,
        value_cols,
        param_dict,
        chart_dict,
        output_column,
    )
    return param_dict, sample_message
