from __future__ import annotations

import polars as pl

from src.io_utils import get_schema_and_column_names

OK_MSG = (
    "Verificato automaticamente: importi/dati coerenti; nessuna discrepanza "
    "rilevata."
)


def flatten_mismatches(
    df: pl.DataFrame,
    column: str = "mismatches",
    prefix: str = "mismatch_",
) -> tuple[pl.DataFrame, dict[str, str]]:
    """Explode and unnest a struct column, ensuring unique field names.

    Parameters
    ----------
    df: pl.DataFrame
        DataFrame containing a list of structs in ``column``.
    column: str, default ``"mismatches"``
        Column with struct entries to flatten.
    prefix: str, default ``"mismatch_"``
        Prefix used when a struct field conflicts with an existing column.

    Returns
    -------
    tuple[pl.DataFrame, dict[str, str]]
        ``(df_out, mapping)`` where ``df_out`` has the struct exploded and
        unnested, and ``mapping`` maps original field names to the final
        column names.
    """

    columns, _ = get_schema_and_column_names(df)
    if column not in columns:
        return df, {}

    exploded = df.explode(column)
    columns_after, schema = get_schema_and_column_names(exploded)
    struct_fields = [field.name for field in schema[column].fields]

    existing_cols = set(columns_after)
    renamed_fields: list[str] = []
    mapping: dict[str, str] = {}

    for name in struct_fields:
        new_name = name
        if new_name in existing_cols:
            new_name = f"{prefix}{new_name}"
            while new_name in existing_cols:
                new_name = f"{prefix}{new_name}"
        renamed_fields.append(new_name)
        mapping[name] = new_name
        existing_cols.add(new_name)

    df_out = exploded.with_columns(
        pl.col(column).struct.rename_fields(renamed_fields).alias(column)
    ).unnest(column)

    return df_out, mapping


def normalize_status(df: pl.DataFrame) -> pl.DataFrame:
    """Replace ``verified`` statuses with ``ok`` and fill explanations.

    Parameters
    ----------
    df:
        Results DataFrame produced by the check-entries pipeline.

    Returns
    -------
    pl.DataFrame
        A new DataFrame where rows previously marked as ``verified`` have
        ``check_status`` set to ``ok`` and, when the ``explanation`` column is
        empty or null, populated with a default message.
    """

    was_verified = pl.col("check_status") == "verified"

    return df.with_columns(
        [
            pl.when(was_verified)
            .then(pl.lit("ok"))
            .otherwise(pl.col("check_status"))
            .alias("check_status"),
            pl.when(
                was_verified
                & (
                    pl.col("explanation").is_null()
                    | (pl.col("explanation").str.len_chars() == 0)
                )
            )
            .then(pl.lit(OK_MSG))
            .otherwise(pl.col("explanation"))
            .alias("explanation"),
        ]
    )


def hide_line_numbers(df: pl.DataFrame) -> pl.DataFrame:
    """Return a copy of *df* without exposing line numbers."""

    def _strip(
        mismatches: list[dict[str, object]] | pl.Series | None,
    ) -> list[dict[str, object]] | None:
        """Remove ``line_numbers`` from each mismatch entry.

        ``map_elements`` may pass a :class:`polars.Series` for list entries,
        which cannot be evaluated directly in boolean context. This helper
        handles ``None`` and empty collections explicitly to avoid the
        ``TypeError: the truth value of a Series is ambiguous``.
        """

        if mismatches is None:
            return None

        if isinstance(mismatches, pl.Series):
            if mismatches.len() == 0:
                return []
            iterable = mismatches.to_list()
        else:
            if len(mismatches) == 0:  # type: ignore[arg-type]
                return mismatches
            iterable = mismatches

        return [
            {k: v for k, v in mismatch.items() if k != "line_numbers"}
            for mismatch in iterable
        ]

    columns, schema = get_schema_and_column_names(df)
    result = df.drop("line_numbers", strict=False)
    if "mismatches" in columns and schema and "mismatches" in schema:
        mismatches_dtype = schema["mismatches"]
        return_dtype = mismatches_dtype
        if isinstance(mismatches_dtype, pl.List) and isinstance(
            mismatches_dtype.inner, pl.Struct
        ):
            fields = {
                f.name: f.dtype
                for f in mismatches_dtype.inner.fields
                if f.name != "line_numbers"
            }
            return_dtype = pl.List(pl.Struct(fields))
        result = result.with_columns(
            pl.col("mismatches").map_elements(_strip, return_dtype=return_dtype)
        )
    return result
