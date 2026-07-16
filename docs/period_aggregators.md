# Period Aggregators

`src.period_aggregators` centralises helpers for time aggregation. Each function accepts a Polars `DataFrame` or `LazyFrame` and returns lazy output when the input was lazy.

## Calendar options

Use `src.period_options.determine_most_recent_period_options` to build the slider for selecting the final period.

```python
options, mapping, default, show, params = determine_most_recent_period_options(
    df.lazy(), params, chart
)
```

## Rolling windows

`calculate_rolling_period` assigns rows to rolling-year buckets when comparing to the prior year.

```python
rolled, params, _, chart = calculate_rolling_period(df, [], params, chart)
```

## Period-to-date (current year)

`calculate_period_to_date_same_year` labels month-to-date or quarter-to-date rows for the current year.

```python
mtd, params = calculate_period_to_date_same_year(df, params)
```

## Period-to-date vs previous year

`calculate_period_to_date_year_ago` performs the same calculation but compares against the previous year.

```python
ytd, params = calculate_period_to_date_year_ago(df, params)
```
