from __future__ import annotations

"""Preprocess FEEDFILE into tidy period/channel rows with units and sales."""

import argparse
import logging
import re
import sys
from dataclasses import dataclass
from pathlib import Path

import polars as pl

# Allow direct execution via `python scripts/preprocess_feedfile.py`.
ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.append(str(ROOT_DIR))

from modules.utilities.utils import get_row_count, get_schema_and_column_names

__all__ = ["PreprocessResult", "main", "preprocess_feedfile"]

LOGGER = logging.getLogger(__name__)

EXPECTED_OUTPUT_METRICS = ("units", "sales")
DEFAULT_DIMENSION_COLUMNS = (
    "sku",
    "ean",
    "id_parent_product",
    "product_name",
    "prodlast_lev1",
    "prodlast_lev2",
    "prodlast_lev3",
    "prodlast_lev4",
)


@dataclass(frozen=True)
class PreprocessResult:
    """Store output paths and final tidy shape."""

    csv_path: Path
    parquet_path: Path
    excel_path: Path
    row_count: int
    column_count: int


@dataclass(frozen=True)
class HeaderLayout:
    """Track row/column boundaries of the FEEDFILE structure."""

    header_row_index: int
    metric_row_index: int
    period_row_index: int
    data_start_row_index: int
    sales_start_column_index: int


def _to_snake_case(value: object | None) -> str:
    """Convert text into lowercase snake_case."""

    if value is None:
        return ""
    text = str(value).replace("\xa0", " ").strip().lower()
    text = text.replace("€", " eur ")
    text = re.sub(r"[^a-z0-9]+", "_", text)
    text = re.sub(r"_+", "_", text).strip("_")
    return text


def _deduplicate_column_names(names: list[str]) -> list[str]:
    """Return unique column names by adding numeric suffixes when needed."""

    counts: dict[str, int] = {}
    deduped: list[str] = []
    for index, name in enumerate(names, start=1):
        base = name or f"col_{index}"
        seen = counts.get(base, 0)
        deduped.append(base if seen == 0 else f"{base}_{seen + 1}")
        counts[base] = seen + 1
    return deduped


def _normalize_blank_strings(df: pl.DataFrame) -> pl.DataFrame:
    """Convert blank strings to null values for all string columns."""

    columns, _ = get_schema_and_column_names(df)
    exprs: list[pl.Expr] = []
    for column_name, dtype in zip(columns, df.dtypes):
        if dtype == pl.String:
            exprs.append(
                pl.when(pl.col(column_name).str.strip_chars() == "")
                .then(None)
                .otherwise(pl.col(column_name))
                .alias(column_name)
            )
    if not exprs:
        return df
    return df.with_columns(exprs)


def _normalize_metric(value: object | None) -> str:
    """Map source metric headers to tidy output metric names."""

    metric = _to_snake_case(value)
    mapping = {
        "quantity": "units",
        "net_turnover_eur": "sales",
        "net_turnover": "sales",
        "turnover_eur": "sales",
        "turnover": "sales",
    }
    return mapping.get(metric, metric or "unknown_metric")


def _normalize_period(value: object | None) -> str:
    """Normalize period labels to ENDINGMAYYYYY."""

    raw_period = str(value or "").upper().replace("\xa0", " ").strip()
    if not raw_period:
        return "UNKNOWN_PERIOD"

    compact = raw_period.replace(" ", "")
    match_ending = re.search(r"ENDINGMAY(\d{2,4})", compact)
    if match_ending:
        suffix = match_ending.group(1)
        if len(suffix) == 2:
            suffix = f"20{suffix}"
        return f"ENDINGMAY{suffix}"

    match_range = re.search(r"31/05/(\d{4})", raw_period)
    if match_range:
        return f"ENDINGMAY{match_range.group(1)}"

    match_year = re.search(r"(20\d{2})", raw_period)
    if match_year:
        return f"ENDINGMAY{match_year.group(1)}"

    return "UNKNOWN_PERIOD"


def _normalize_channel(value: object | None) -> str:
    """Normalize channel names."""

    channel = str(value or "").upper().replace("\xa0", " ").strip()
    if not channel:
        return "UNKNOWN_CHANNEL"
    if channel.startswith("TOTAL"):
        return "TOTAL"
    return channel.replace("-", "_").replace(" ", "_")


def _find_header_layout(raw: pl.DataFrame) -> HeaderLayout:
    """Locate key rows/columns in FEEDFILE layout."""

    row_count = get_row_count(raw)
    scan_limit = min(row_count, 50)
    header_row_index = -1

    for row_index in range(scan_limit):
        row = raw.row(row_index)
        if _to_snake_case(row[0]) == "sku" and _to_snake_case(row[1]) == "ean":
            header_row_index = row_index
            break

    if header_row_index < 0:
        raise ValueError("Could not find FEEDFILE header row with SKU/EAN.")

    header_row = raw.row(header_row_index)
    sales_start_column_index = len(header_row)
    for column_index, value in enumerate(header_row):
        if _normalize_channel(value) in {"NEG", "E_COMM", "TOTAL"}:
            sales_start_column_index = column_index
            break

    if sales_start_column_index >= len(header_row):
        raise ValueError("Could not find sales block (NEG/E-COMM/TOTAL columns).")

    return HeaderLayout(
        header_row_index=header_row_index,
        metric_row_index=max(0, header_row_index - 2),
        period_row_index=max(0, header_row_index - 1),
        data_start_row_index=header_row_index + 1,
        sales_start_column_index=sales_start_column_index,
    )


def _build_sales_column_map(
    raw: pl.DataFrame,
    cleaned_headers: list[str],
    layout: HeaderLayout,
) -> tuple[dict[str, str], list[str]]:
    """Build encoded sales columns as metric__period__channel."""

    metric_row = raw.row(layout.metric_row_index)
    period_row = raw.row(layout.period_row_index)
    channel_row = raw.row(layout.header_row_index)

    active_metric = "unknown_metric"
    active_period = "UNKNOWN_PERIOD"
    rename_map: dict[str, str] = {}
    encoded_columns: list[str] = []

    for col_index in range(layout.sales_start_column_index, raw.width):
        metric_cell = metric_row[col_index]
        if metric_cell is not None and str(metric_cell).strip():
            active_metric = _normalize_metric(metric_cell)

        period_cell = period_row[col_index]
        if period_cell is not None and str(period_cell).strip():
            active_period = _normalize_period(period_cell)

        channel = _normalize_channel(channel_row[col_index])
        encoded_name = f"{active_metric}__{active_period}__{channel}"

        source_name = cleaned_headers[col_index]
        rename_map[source_name] = encoded_name
        encoded_columns.append(encoded_name)

    return rename_map, encoded_columns


def preprocess_feedfile(
    input_path: Path,
    output_dir: Path | None = None,
    output_prefix: str | None = None,
) -> PreprocessResult:
    """Transform FEEDFILE into tidy rows with units and sales columns."""

    workbook_path = input_path.expanduser().resolve()
    raw = pl.read_excel(workbook_path, sheet_name="FEEDFILE", has_header=False)
    if get_row_count(raw) == 0:
        raise ValueError("Input FEEDFILE is empty.")

    layout = _find_header_layout(raw)
    raw_columns, _ = get_schema_and_column_names(raw)

    header_cells = list(raw.row(layout.header_row_index))
    normalized_headers: list[str] = []
    for index, cell in enumerate(header_cells):
        if index < layout.sales_start_column_index:
            normalized_headers.append(_to_snake_case(cell))
        else:
            normalized_headers.append(f"sales_col_{index + 1}")
    cleaned_headers = _deduplicate_column_names(normalized_headers)

    data = raw.slice(layout.data_start_row_index).rename(dict(zip(raw_columns, cleaned_headers)))
    data = _normalize_blank_strings(data)
    data = data.filter(
        pl.col("sku").is_not_null()
        & (pl.col("sku").str.strip_chars() != "")
        & (pl.col("sku").str.to_uppercase() != "SKU")
    )

    data_columns, _ = get_schema_and_column_names(data)
    keep_columns = [column for column in DEFAULT_DIMENSION_COLUMNS if column in data_columns]
    if "sku" not in keep_columns:
        raise ValueError("Expected 'sku' column after header normalization.")

    sales_rename_map, sales_columns = _build_sales_column_map(raw, cleaned_headers, layout)
    data = data.rename(sales_rename_map)

    tidy_long = (
        data.select(keep_columns + sales_columns)
        .unpivot(
            index=keep_columns,
            on=sales_columns,
            variable_name="sales_key",
            value_name="value",
        )
        .with_columns(
            pl.col("value").cast(pl.Float64, strict=False),
            pl.col("sales_key").str.split_exact("__", 2).alias("parts"),
        )
        .filter(pl.col("value").is_not_null())
        .with_columns(
            pl.col("parts").struct.field("field_0").alias("metric"),
            pl.col("parts").struct.field("field_1").alias("period"),
            pl.col("parts").struct.field("field_2").alias("channel"),
        )
        .drop(["sales_key", "parts"])
        .filter(
            pl.col("period").is_in(["ENDINGMAY2024", "ENDINGMAY2025"])
            & pl.col("channel").is_in(["NEG", "E_COMM"])
            & pl.col("metric").is_in(EXPECTED_OUTPUT_METRICS)
        )
    )

    tidy = (
        tidy_long.pivot(
            on="metric",
            index=keep_columns + ["period", "channel"],
            values="value",
            aggregate_function="first",
        )
        .with_columns(
            pl.col("units").cast(pl.Float64, strict=False),
            pl.col("sales").cast(pl.Float64, strict=False),
            pl.when(pl.col("channel") == "NEG")
            .then(pl.lit("Shops"))
            .when(pl.col("channel") == "E_COMM")
            .then(pl.lit("Web"))
            .otherwise(pl.col("channel"))
            .alias("channel"),
            pl.when(pl.col("period") == "ENDINGMAY2024")
            .then(pl.lit("2024"))
            .when(pl.col("period") == "ENDINGMAY2025")
            .then(pl.lit("2025"))
            .otherwise(pl.col("period"))
            .alias("period"),
        )
        .select(keep_columns + ["period", "channel", "units", "sales"])
        .sort(["sku", "period", "channel"])
    )

    destination = (output_dir or workbook_path.parent).expanduser().resolve()
    destination.mkdir(parents=True, exist_ok=True)
    prefix = output_prefix or workbook_path.stem

    csv_path = destination / f"{prefix}_tidy.csv"
    parquet_path = destination / f"{prefix}_tidy.parquet"
    excel_path = destination / f"{prefix}_tidy.xlsx"

    tidy.write_csv(csv_path)
    tidy.write_parquet(parquet_path)
    tidy.write_excel(excel_path, worksheet="tidy_feed")

    return PreprocessResult(
        csv_path=csv_path,
        parquet_path=parquet_path,
        excel_path=excel_path,
        row_count=get_row_count(tidy),
        column_count=tidy.width,
    )


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Preprocess FEEDFILE into tidy rows with units and sales."
    )
    parser.add_argument(
        "--input",
        type=Path,
        default=Path("new_datasets/FeedFile.xlsx"),
        help="Path to the source workbook.",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=None,
        help="Directory for output files. Defaults to input file directory.",
    )
    parser.add_argument(
        "--output-prefix",
        default=None,
        help="Prefix for output file names. Defaults to input file stem.",
    )
    return parser.parse_args()


def main() -> None:
    """CLI entrypoint."""

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    args = _parse_args()
    result = preprocess_feedfile(
        input_path=args.input,
        output_dir=args.output_dir,
        output_prefix=args.output_prefix,
    )
    LOGGER.info(
        "Wrote tidy dataset with %s rows x %s columns",
        result.row_count,
        result.column_count,
    )
    LOGGER.info("CSV: %s", result.csv_path)
    LOGGER.info("Parquet: %s", result.parquet_path)
    LOGGER.info("Excel: %s", result.excel_path)


if __name__ == "__main__":
    main()
