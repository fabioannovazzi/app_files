from __future__ import annotations

import types
from io import BytesIO
from pathlib import Path

import polars as pl
import pytest
from polars.testing import assert_frame_equal

from src.load_sales_logic import (
    convert_decimal_columns_lazy,
    encode_uploaded_file,
    parse_csv,
    parse_parquet,
)


class DummyUpload:
    def __init__(self, name: str, content: bytes | None = None) -> None:
        self.name = name
        self._content = content or b""

    def getvalue(self) -> bytes:  # UploadedFile-style API
        return self._content


def _stub_naming():
    # Minimal keys used by encode_uploaded_file
    return {
        "uploadedFileType": "uploadedFileType",
        "uploadedFileName": "uploadedFileName",
        "errorMessageType": "error",
        "captionMessageType": "caption",
        "loadDataTab": "load",
    }


def test_convert_decimal_columns_lazy_converts_decimal_and_preserves_others():
    # Arrange
    df = pl.DataFrame(
        {
            "amount": pl.Series("amount", [1, 2, 3], dtype=pl.Decimal(10, 2)),
            "count": [1, 2, 3],
        }
    )
    lf = df.lazy()

    # Act
    out_lf = convert_decimal_columns_lazy(lf)
    out_df = out_lf.collect()

    # Assert
    assert out_df.schema["amount"] == pl.Float64
    assert out_df.schema["count"] == pl.Int64
    expected = pl.DataFrame({"amount": [1.0, 2.0, 3.0], "count": [1, 2, 3]})
    assert_frame_equal(out_df, expected)


def test_convert_decimal_columns_lazy_no_decimal_noop():
    # Arrange
    df = pl.DataFrame({"x": [1, 2], "y": ["a", "b"]})
    lf = df.lazy()

    # Act
    out_lf = convert_decimal_columns_lazy(lf)
    out_df = out_lf.collect()

    # Assert
    assert out_df.schema == df.schema
    assert_frame_equal(out_df, df)


@pytest.mark.parametrize("suffix", ["csv", "xlsx", "parquet"])
def test_encode_uploaded_file_accepts_known_types(monkeypatch, suffix: str):
    # Arrange
    monkeypatch.setattr("src.load_sales_logic.get_naming_params", _stub_naming)

    messages: list[str] = []

    def add_app_message_to_paramdict(msg, *_args, **_kwargs):
        messages.append(msg)
        return _kwargs.get("param_dict") or _args[-1]

    monkeypatch.setattr(
        "src.load_sales_logic.add_app_message_to_paramdict",
        add_app_message_to_paramdict,
    )

    uploaded = DummyUpload(f"orders.{suffix}")
    param = {}

    # Act
    result, out = encode_uploaded_file(uploaded, "err", "cap", param)

    # Assert
    assert result is uploaded
    assert out["uploadedFileType"] == suffix
    assert out["uploadedFileName"] == "orders"
    assert messages == []  # no error/caption messages for valid types


def test_encode_uploaded_file_rejects_unknown_type_and_populates_messages(monkeypatch):
    # Arrange
    monkeypatch.setattr("src.load_sales_logic.get_naming_params", _stub_naming)

    def add_app_message_to_paramdict(msg, *_args, **_kwargs):
        pd = _kwargs.get("param_dict") or _args[-1]
        pd.setdefault("messages", []).append(msg)
        return pd

    monkeypatch.setattr(
        "src.load_sales_logic.add_app_message_to_paramdict",
        add_app_message_to_paramdict,
    )

    uploaded = DummyUpload("weird.txt")
    param = {}

    # Act
    result, out = encode_uploaded_file(uploaded, "Bad type", "Choose csv/xlsx", param)

    # Assert
    assert result is None
    assert out["uploadedFileType"] == "txt"
    assert out["uploadedFileName"] == "weird"
    assert out["messages"] == [
        "Unrecognized file type. The uploaded file must be CSV, XLSX, or Parquet.",
        "Bad type",
        "Choose csv/xlsx",
    ]


def test_encode_uploaded_file_none_returns_none_and_no_changes(monkeypatch):
    # Arrange
    monkeypatch.setattr("src.load_sales_logic.get_naming_params", _stub_naming)

    # Act
    result, out = encode_uploaded_file(None, "err", "cap", {})

    # Assert
    assert result is None
    assert out == {}


def test_parse_csv_reads_content_and_returns_lazyframe(monkeypatch):
    # Arrange
    # Silence UI side effects and downstream parsing
    monkeypatch.setattr(
        "src.load_sales_logic.find_and_parse_datecolumns",
        lambda df, pd: (df, pd),
    )
    # Build minimal content
    content = b"a,b\n1,2\n3,4\n"
    data = DummyUpload("data.csv", content)
    param = {}

    # Act
    lf, out_param, parse_msg = parse_csv(data, ",", param)

    # Assert
    assert isinstance(lf, pl.LazyFrame)
    df = lf.collect()
    expected = pl.DataFrame({"a": [1, 3], "b": [2, 4]})
    assert_frame_equal(df, expected)
    assert out_param is param
    assert parse_msg == ""


def test_parse_parquet_reads_content_and_returns_lazyframe(monkeypatch):
    monkeypatch.setattr(
        "src.load_sales_logic.find_and_parse_datecolumns",
        lambda df, pd: (df, pd),
    )
    parquet_buffer = BytesIO()
    expected = pl.DataFrame({"a": [1, 3], "b": [2, 4]})
    expected.write_parquet(parquet_buffer)
    data = DummyUpload("data.parquet", parquet_buffer.getvalue())
    param: dict = {}

    lazy_frame, out_param, parse_msg = parse_parquet(data, param)

    assert isinstance(lazy_frame, pl.LazyFrame)
    assert_frame_equal(lazy_frame.collect(), expected)
    assert out_param is param
    assert parse_msg == ""


def test_parse_csv_error_path_adds_message_and_returns_empty(monkeypatch):
    # Arrange
    # Stub UI and error-message helper
    monkeypatch.setattr(
        "src.load_sales_logic.find_and_parse_datecolumns",
        lambda df, pd: (df, pd),
    )

    def add_error(param_dict, msg):
        param_dict.setdefault("errors", []).append(msg)
        return param_dict

    monkeypatch.setattr(
        "src.load_sales_logic.add_error_message_in_load_data_tab", add_error
    )

    data = DummyUpload("bad.csv", b"a,b\n1,2\n")
    param: dict = {}

    # Act: invalid separator triggers exception in pl.scan_csv
    lf, out_param, parse_msg = parse_csv(data, "", param)

    # Assert
    assert isinstance(lf, pl.LazyFrame)
    assert len(lf.collect_schema()) == 0  # empty LazyFrame on error
    assert parse_msg == "Problem parsing the CSV file."
    assert out_param["errors"] == [parse_msg]
