# Pandas Import Inventory

All application modules now use **Polars** exclusively and no longer import `pandas`. This document remains for historical reference. A few unit tests still import `pandas` when verifying error handling.

The test suite includes ``test_no_pandas_imports`` which asserts that no source
files contain ``import pandas``.

## Date parsing

Earlier versions relied on `dateutil.parser.parse` to normalise timestamp strings. The codebase now uses Polars expressions directly (e.g. `pl.col("date").str.strptime(pl.Date)`) so `dateutil` is no longer a dependency.

## Marimekko helpers

Utilities for marimekko charts—`get_marimekko_positions`,
`prepare_data_for_marimekko`, `set_marimekko_params_and_add_trace` and
`add_total_annotations_for_marimekko`—now accept `polars.LazyFrame` inputs.
The previous pandas-based versions have been removed.

## UpSet helpers

UpSet charts are still generated entirely with **Polars**. The
`plot_upset` helper now accepts a `polars.LazyFrame`, and the whole
pipeline stays lazy until calling `collect()` for the Plotly chart. No
pandas conversion is required.

## Distribution chart helpers

All distribution chart routines now operate lazily with **Polars**. Key functions such as `aggregate_values_in_distribution_plots`, `draw_histogram_chart`, `draw_boxplot_chart`, `draw_stripplot_chart`, `draw_ecdf_chart` and `draw_kernel_density_chart` accept `polars.LazyFrame` inputs and collect data only once before plotting.

## Multitier bar chart example

Calling ``draw_multitier_bar_chart`` works the same way. Pass a ``polars.LazyFrame`` and simple configuration dictionaries. All transformations remain lazy and the data is only collected immediately before Plotly draws the figure.

```python
import polars as pl
from modules.charting.draw_multitier import draw_multitier_bar_chart

lf = pl.DataFrame({"tier": ["A", "B"], "metric": [10, 15]}).lazy()
param = {}
chart = {"selectDimensionsToPlot": ["tier"], "chosenChart": "bar", "selectedPeriods": []}

fig = draw_multitier_bar_chart(
    lf,
    chosenDimension="tier",
    xColumn="tier",
    metricsToPlot=["metric"],
    valueCols=["metric"],
    paramDict=param,
    chartDictCopy=chart,
)
```

