# Legacy Distribution Inventory

The distribution plugin wraps the existing legacy Plotly charting functions.
It does not redraw these charts with another library.

| Plugin chart | Legacy chart key | Legacy plotter | Legacy draw function | Small multiples |
| --- | --- | --- | --- | --- |
| `histogram` | `histogramChart` -> `histogram` | `modules.charting.plot_charts.plot_histogram_charts` | `modules.charting.draw_distribution.draw_histogram_chart` | Same plotter, enabled by `chartDict[smallMultiplesColumn]` |
| `boxplot` | `boxplotChart` -> `boxplot` | `modules.charting.plot_charts.plot_boxplot_charts` | `modules.charting.draw_distribution.draw_boxplot_chart` | Same plotter, enabled by `chartDict[smallMultiplesColumn]` |
| `stripplot` | `stripplotChart` -> `stripplot` | `modules.charting.plot_charts.plot_stripplot_charts` | `modules.charting.draw_distribution.draw_stripplot_chart` | Same plotter, enabled by `chartDict[smallMultiplesColumn]` |
| `ecdf` | `ecdfChart` -> `ECDF` | `modules.charting.plot_charts.plot_ecdf_charts` | `modules.charting.draw_distribution.draw_ecdf_chart` | Same plotter, enabled by `chartDict[smallMultiplesColumn]` |
| `kernel_density` | `kernelDensityChart` -> `kernel density` | `modules.charting.plot_charts.plot_kernel_density_charts` | `modules.charting.draw_distribution.draw_kernel_density_chart` | Same plotter, enabled by `chartDict[smallMultiplesColumn]` |

Shared legacy preparation used by these chart families:

- `modules.data.misc_charts_data_prep.aggregate_values_in_distribution_plots`
- `modules.data.common_data_utils.show_only_largest`
- `modules.charting.plotting_utilities.check_if_two_periods_in_distribution_chart`
- `modules.charting.make_titles.make_distribution_charts_title`
- `modules.charting.chart_helpers.set_up_tab_for_show_or_download_chart`

Legacy settings exposed by the plugin:

- `xAxisMetric`: metric to plot.
- `xAxisDimension`: optional dimension used to aggregate observations before plotting.
- `smallMultiplesColumn`: optional panel dimension.
- `selectedPeriods`: one or two periods/scenarios shown as color groups.
- `cumulativeHistogram`: histogram mode.
- `reversedEcdf`: ECDF direction.
- `showOutliers`: boxplot point policy.
- `logXAxis`: log-scale option.
- `X[numberOfTop]` and `X[aggregateOtherItems]`: top-N/Other handling for small multiples.
