from __future__ import annotations

from typing import Any, Iterable, Mapping, Union

import polars as pl

JsonObject = Mapping[str, Any]
JsonSequence = Iterable[JsonObject]


def _merge_header_rows(row1: list[str], row2: list[str]) -> list[str]:
    """Merge two header rows preferring values from ``row2``."""

    header: list[str] = []
    for h1, h2 in zip(row1, row2):
        h1 = (h1 or "").strip()
        h2 = (h2 or "").strip()
        header.append(h2 if h2 else h1)
    return header


def _unique_column_names(cols: list[str]) -> list[str]:
    """Return *cols* with blanks and duplicates made unique."""

    seen: dict[str, int] = {}
    unique: list[str] = []
    for idx, col in enumerate(cols):
        base = col.strip() if col and col.lower() != "none" else f"column_{idx}"
        count = seen.get(base, 0)
        name = base if count == 0 else f"{base}_{count+1}"
        seen[base] = count + 1
        unique.append(name)
    return unique


def _suggest_header_row(frame: pl.DataFrame) -> int:
    """Return the row index that most likely contains header labels."""

    if frame.height == 0:
        return 0

    best_idx = 0
    best_score = -1
    limit = min(frame.height, 10)
    for idx in range(limit):
        try:
            row = frame.row(idx)
        except Exception:
            break
        score = 0
        for value in row:
            if value is None:
                continue
            text = str(value).strip()
            if not text:
                continue
            score += 1
            if any(ch.isalpha() for ch in text):
                score += 2
        if score > best_score:
            best_idx = idx
            best_score = score
    return best_idx


def _num(col: pl.Series) -> pl.Series:
    """Parse European numbers like '1.234,56' as floats."""
    return (
        col.cast(pl.Utf8)
        .str.replace_all(".", "")
        .str.replace_all(",", ".")
        .cast(pl.Float64, strict=False)
    )


def _parse_date(col: pl.Series) -> pl.Series:
    """Parse 'dd/mm/yy' or 'dd/mm/YYYY' as ``pl.Date``."""
    short = col.str.strptime(pl.Date, "%d/%m/%y", strict=False)
    long = col.str.strptime(pl.Date, "%d/%m/%Y", strict=False)
    return short.fill_null(long)


def explode(df: pl.DataFrame, m: dict[str, str], layout: str) -> pl.DataFrame:
    """Expand journal rows depending on the given *layout*."""
    if layout == "posting_signed":
        amt = _num(df[m["amount"]])
        deb = amt.clip(0, None)
        cre = (-amt).clip(0, None)
        out = pl.DataFrame(
            {
                "date": _parse_date(df[m["date"]]),
                "account": df[m["account"]],
                "debit": deb,
                "credit": cre,
            }
        )

    elif layout == "posting_amount_flag":
        amt = _num(df[m["amount"]])
        flag = df[m["dc_flag"]].str.to_lowercase()
        # Polars `str.starts_with` does not accept a tuple; both "d" and "dr"
        # start with "d", so using a single-prefix check preserves intent.
        deb = amt.where(flag.str.starts_with("d"), 0)
        cre = amt.where(~flag.str.starts_with("d"), 0)
        out = pl.DataFrame(
            {
                "date": _parse_date(df[m["date"]]),
                "account": df[m["account"]],
                "debit": deb,
                "credit": cre,
            }
        )

    elif layout == "posting_split_amt":
        out = pl.DataFrame(
            {
                "date": _parse_date(df[m["date"]]),
                "account": df[m["account"]],
                "debit": _num(df[m["debit_amount"]]).fill_null(0),
                "credit": _num(df[m["credit_amount"]]).fill_null(0),
            }
        )

    elif layout == "entry_split_acc":
        debit_side = pl.DataFrame(
            {
                "date": _parse_date(df[m["date"]]),
                "account": df[m["debit_account"]],
                "debit": _num(df[m["debit_amount"]]).fill_null(0),
                "credit": pl.Series([0.0] * df.height),
            }
        )
        credit_side = pl.DataFrame(
            {
                "date": _parse_date(df[m["date"]]),
                "account": df[m["credit_account"]],
                "debit": pl.Series([0.0] * df.height),
                "credit": _num(df[m["credit_amount"]]).fill_null(0),
            }
        )
        out = pl.concat([debit_side, credit_side])

    elif layout == "entry_split_amt":
        amt = _num(df[m["amount"]]).fill_null(0)
        debit_side = pl.DataFrame(
            {
                "date": _parse_date(df[m["date"]]),
                "account": df[m["debit_account"]],
                "debit": amt,
                "credit": pl.Series([0.0] * df.height),
            }
        )
        credit_side = pl.DataFrame(
            {
                "date": _parse_date(df[m["date"]]),
                "account": df[m["credit_account"]],
                "debit": pl.Series([0.0] * df.height),
                "credit": amt,
            }
        )
        out = pl.concat([debit_side, credit_side])

    else:
        raise ValueError(f"Unknown layout {layout}")

    return out.select(["date", "account", "debit", "credit"])


def _as_dict(value: Union[JsonObject, JsonSequence]) -> JsonObject:
    """Return a dictionary from *value* which may be dict or sequence of dicts."""
    if isinstance(value, Mapping):
        return value

    if isinstance(value, (list, tuple)):
        for item in value:
            if isinstance(item, Mapping):
                return item
        raise ValueError("Sequence contains no dictionaries")

    raise TypeError(f"Expected dict or list/tuple of dicts, got {type(value).__name__}")


__all__ = [
    "_merge_header_rows",
    "_unique_column_names",
    "_suggest_header_row",
    "_num",
    "_parse_date",
    "explode",
    "_as_dict",
    "JsonObject",
    "JsonSequence",
]
