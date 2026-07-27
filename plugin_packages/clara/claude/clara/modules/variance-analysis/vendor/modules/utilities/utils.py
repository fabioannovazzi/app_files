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
