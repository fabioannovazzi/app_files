import logging
from typing import Any, Dict, List, Tuple

import polars as pl
from polars.exceptions import ColumnNotFoundError

# ---------------------------------------------------------------------------
# Monkey patch ``polars.LazyFrame`` with a ``height`` property if the installed
# Polars version lacks it and the class allows attribute assignment.  The
# additional ``__dict__`` check skips patching when a stub or slot-based class
# would raise ``TypeError`` on new attributes.
# ---------------------------------------------------------------------------
if (
    hasattr(pl, "LazyFrame")
    and not hasattr(pl.LazyFrame, "height")
    and hasattr(pl.LazyFrame, "__dict__")  # Guard: stubbed classes lack __dict__
):

    @property
    def _lazyframe_height(self) -> int:  # pragma: no cover - thin wrapper
        return int(self.select(pl.len()).collect().item())

    try:
        pl.LazyFrame.height = _lazyframe_height  # type: ignore[attr-defined]
    except TypeError:  # pragma: no cover - builtins reject new attrs
        pass


def get_schema_and_column_names(
    df: pl.DataFrame | pl.LazyFrame | Any,
) -> Tuple[List[str], Dict[str, pl.DataType] | None]:
    """Return ``df`` column names and schema.

    Polars has evolved its API across versions: attributes such as ``schema`` or
    ``columns`` may be either properties or callables.  Test suites also
    monkeypatch this function with lightweight lambdas.  This helper therefore
    normalises both attributes to concrete Python structures.

    Parameters
    ----------
    df:
        Any object exposing ``schema``/``columns`` similar to Polars frames.

    Returns
    -------
    tuple[list[str], dict | None]
        A list of column names and the schema as a plain ``dict`` when
        available.
    """

    schema_obj = None
    if hasattr(df, "collect_schema") and callable(getattr(df, "collect_schema")):
        schema_obj = df.collect_schema()
    else:
        schema_attr = getattr(df, "schema", None)
        if callable(schema_attr):  # pragma: no cover - depends on Polars version
            schema_obj = schema_attr()
        else:
            schema_obj = schema_attr

    schema: Dict[str, pl.DataType] | None
    if schema_obj is not None:
        schema = dict(schema_obj)
        columns = list(schema.keys())
    else:
        schema = None
        cols_attr = getattr(df, "columns", [])
        cols_val = cols_attr() if callable(cols_attr) else cols_attr
        columns = list(cols_val)

    return columns, schema


def is_valid_lazyframe(lazy_df):
    """Check whether ``lazy_df`` is a valid polars LazyFrame or DataFrame."""

    # Regular polars DataFrame should simply be non-empty
    if isinstance(lazy_df, pl.DataFrame):
        return lazy_df.height > 0

    # If not LazyFrame, it's not valid
    if not isinstance(lazy_df, pl.LazyFrame):
        return False

    # Check if the LazyFrame has a valid schema
    try:
        columns, schema = get_schema_and_column_names(
            lazy_df
        )  # Fetch schema without materializing
        if not schema or len(schema) == 0:
            return False  # No columns in the schema
    except Exception as e:
        logging.exception(e)
        return False  # Schema retrieval failed

    # If schema exists and is valid, consider it a valid LazyFrame
    return True


def get_row_count(df: pl.DataFrame | pl.LazyFrame) -> int:
    """Return the number of rows in ``df``.

    Always prefer ``df.height`` for eager DataFrames; avoid Python's ``len``
    function on data frames.

    Parameters
    ----------
    df:
        A ``polars.DataFrame`` or ``polars.LazyFrame`` instance.

    Returns
    -------
    int
        Row count of ``df``.
    """

    if isinstance(df, pl.DataFrame):
        return df.height
    if isinstance(df, pl.LazyFrame):
        try:
            plan = df.select(pl.len())
            return int(plan.collect()[0, 0])
        except ColumnNotFoundError as exc:
            raise ColumnNotFoundError(
                f"Failed to compute row count due to missing column: {exc}"
            ) from exc
    raise TypeError(f"Unsupported object type: {type(df)!r}")


def ensure_polars_df(df: Any) -> pl.DataFrame:
    """Return ``df`` as a Polars ``DataFrame``."""

    if isinstance(df, pl.DataFrame):
        return df
    if isinstance(df, pl.LazyFrame):
        return df.collect()
    try:
        return pl.DataFrame(df)
    except Exception as e:  # noqa: BLE001
        logging.exception(e)
        raise TypeError(f"Unsupported object type: {type(df)!r}") from e


def ensure_lazyframe(df: pl.DataFrame | pl.LazyFrame) -> pl.LazyFrame:
    """Return ``df`` as a Polars ``LazyFrame``.

    Parameters
    ----------
    df:
        Input data that is either a ``DataFrame`` or ``LazyFrame``.

    Returns
    -------
    pl.LazyFrame
        A lazy representation of ``df``.
    """

    if isinstance(df, pl.LazyFrame):
        return df
    if isinstance(df, pl.DataFrame):
        return df.lazy()
    raise TypeError(f"Unsupported object type: {type(df)!r}")


def collect_chart_frame(df: pl.DataFrame | pl.LazyFrame) -> pl.DataFrame:
    """Collect a chart-sized Polars frame for legacy Plotly rendering."""

    if isinstance(df, pl.DataFrame):
        return df
    if isinstance(df, pl.LazyFrame):
        return df.collect()
    raise TypeError(f"Unsupported object type: {type(df)!r}")


def transpose_chart_frame(
    df: pl.DataFrame | pl.LazyFrame,
    *,
    header_name: str,
    column_names: str | None = None,
    include_header: bool = True,
) -> pl.LazyFrame:
    """Return a legacy-style transposed frame as a ``LazyFrame``.

    Several legacy chart paths used Pandas ``DataFrame.T`` after the data was
    already reduced to plotting size.  Polars supports the same final shape via
    ``DataFrame.transpose`` once the small chart frame is collected.
    """

    frame = collect_chart_frame(df)
    kwargs: dict[str, Any] = {"include_header": include_header}
    if include_header:
        kwargs["header_name"] = header_name
    if column_names and column_names in frame.columns:
        kwargs["column_names"] = column_names
    return frame.transpose(**kwargs).lazy()


def sort_utf8_lazy(
    df: pl.DataFrame | pl.LazyFrame, column: str, *, descending: bool = False
) -> pl.LazyFrame:
    """Sort a text column lazily without relying on removed Categorical APIs."""

    lf = ensure_lazyframe(df)
    columns, _ = get_schema_and_column_names(lf)
    if column not in columns:
        return lf
    return lf.with_columns(
        pl.col(column).cast(pl.Utf8).fill_null("").alias(column)
    ).sort(by=column, descending=descending)


def null_row_like(
    df: pl.DataFrame | pl.LazyFrame, assignments: dict[str, Any] | None = None
) -> pl.LazyFrame:
    """Build a one-row ``LazyFrame`` matching ``df`` schema with optional values."""

    assignments = assignments or {}
    columns, schema = get_schema_and_column_names(df)
    row: dict[str, pl.Series] = {}
    for column in columns:
        dtype = schema[column] if schema and column in schema else None
        value = assignments[column] if column in assignments else None
        if dtype is None:
            row[column] = pl.Series(column, [value])
            continue
        try:
            row[column] = pl.Series(column, [value], dtype=dtype)
        except Exception:
            row[column] = pl.Series(column, [None], dtype=dtype)
    return pl.DataFrame(row).lazy()


def concat_aligned_lazy(
    frames: list[pl.DataFrame | pl.LazyFrame],
) -> pl.LazyFrame:
    """Concatenate Polars frames after aligning their columns in schema order."""

    lazy_frames = [ensure_lazyframe(frame) for frame in frames]
    if not lazy_frames:
        return pl.DataFrame().lazy()
    columns: list[str] = []
    schema: dict[str, pl.DataType] = {}
    for frame in lazy_frames:
        frame_columns, frame_schema = get_schema_and_column_names(frame)
        for column in frame_columns:
            if column not in columns:
                columns.append(column)
            if frame_schema and column in frame_schema and column not in schema:
                schema[column] = frame_schema[column]

    aligned_frames: list[pl.LazyFrame] = []
    for frame in lazy_frames:
        frame_columns, _ = get_schema_and_column_names(frame)
        exprs = []
        for column in columns:
            dtype = schema.get(column)
            if column in frame_columns:
                expr = pl.col(column)
                if dtype is not None:
                    expr = expr.cast(dtype, strict=False)
                exprs.append(expr.alias(column))
            else:
                exprs.append(pl.lit(None).cast(dtype or pl.Null).alias(column))
        aligned_frames.append(frame.select(exprs))
    return pl.concat(aligned_frames, how="vertical_relaxed")


def get_column_sum(obj: pl.DataFrame | pl.LazyFrame, column: str) -> float:
    """Return the numeric sum of ``column`` from ``obj``.

    Parameters
    ----------
    obj:
        Data structure containing the column. Can be a ``DataFrame`` or
        ``LazyFrame``.
    column:
        Name of the column to sum.
    """

    lf = ensure_lazyframe(obj)
    return lf.select(pl.col(column).sum()).collect().item()


def unique_list_lazy(column: str, lf: pl.LazyFrame) -> list[str]:
    """Return unique values from ``column`` using ``engine='streaming'`` collection."""

    return lf.select(pl.col(column).unique()).collect()[column].to_list()


def unique_values_lazy(column: str, df: pl.DataFrame | pl.LazyFrame) -> list[str]:
    """Return unique values from ``column`` in ``df`` using ``engine='streaming'``."""

    lf = ensure_lazyframe(df)
    return lf.select(pl.col(column).unique()).collect()[column].to_list()


def get_uniform_text_min_size(
    config_params: dict | None = None, naming_params: dict | None = None
) -> int:
    """Return the configured minimum uniform text size."""

    from modules.utilities.config import get_config_params, get_naming_params

    if config_params is None:
        config_params = get_config_params()
    if naming_params is None:
        naming_params = get_naming_params()

    key = naming_params["uniformTextMinSize"]
    return int(config_params[key])


def extract_scalar(obj: Any) -> float:
    """Return ``obj`` as a numeric scalar if possible."""

    if isinstance(obj, pl.DataFrame):
        if obj.height == 0:
            raise ValueError("Cannot extract value from an empty DataFrame")
        if obj.width == 1:
            return float(obj.item())
        return float(obj.row(0)[0])
    if isinstance(obj, pl.Series):
        return float(obj.item())
    if isinstance(obj, (int, float)):
        return float(obj)
    raise TypeError(f"Unsupported object type: {type(obj)!r}")


def percentage_cols_lazy(
    lf: pl.LazyFrame | pl.DataFrame, columns: list[str], value_col: str
) -> pl.LazyFrame:
    """Return ``lf`` with ``columns`` expressed as percent of ``value_col`` lazily."""

    lf = ensure_lazyframe(lf)
    exprs = [
        (
            pl.when(pl.col(value_col) == 0)
            .then(0)
            .otherwise(pl.col(c) / pl.col(value_col) * 100)
            .alias(c)
        )
        for c in columns
    ]
    return lf.with_columns(exprs)
