from __future__ import annotations

from io import BytesIO
from typing import Mapping

import polars as pl
from polars.testing import assert_frame_equal
import pytest

from src.check_entries_review import merge_review_feedback, pdf_bytes_for


def test_pdf_bytes_for_bytesio_returns_data_default_name_and_resets_pointer():
    # Arrange
    movement = "001"
    content = b"%PDF-sample\n"
    buf = BytesIO(content)
    buf.seek(3)  # simulate prior reads
    pdf_map: Mapping[str, object] = {movement: buf}

    # Act
    data, name = pdf_bytes_for(movement, pdf_map)

    # Assert
    assert data == content
    assert name == f"{movement}.pdf"
    assert buf.tell() == 0  # reset for re-reads


def test_pdf_bytes_for_read_only_object_uses_name_and_resets_pointer():
    # Arrange: custom file-like with read/seek and a name
    class FakeFile:
        def __init__(self, data: bytes, name: str):
            self._data = data
            self._pos = 0
            self.name = name

        def read(self) -> bytes:
            try:
                chunk = self._data[self._pos :]
            finally:
                self._pos = len(self._data)
            return chunk

        def seek(self, pos: int) -> None:
            self._pos = pos

        def tell(self) -> int:  # for assertion only
            return self._pos

    movement = "mv"
    data_bytes = b"PDFDATA"
    f = FakeFile(data_bytes, name="custom.pdf")
    pdf_map: Mapping[str, object] = {movement: f}

    # Act
    data, name = pdf_bytes_for(movement, pdf_map)

    # Assert
    assert data == data_bytes
    assert name == "custom.pdf"
    assert f.tell() == 0


@pytest.mark.parametrize("pdf_map", [{}, {"X": None}])
def test_pdf_bytes_for_missing_entry_returns_none_and_empty_name(pdf_map):
    # Arrange
    movement = "X"
    # Act
    data, name = pdf_bytes_for(movement, pdf_map)
    # Assert
    assert data is None and name == ""


def test_merge_review_feedback_overrides_status_and_adds_reason():
    # Arrange
    df = pl.DataFrame(
        {
            "movement_number": ["101", "102"],
            "check_status": ["mismatch", "ok"],
        }
    )
    status = {"101": "ok"}  # override first row
    reasons = {"101": "human override"}

    # Act
    out = merge_review_feedback(df, status, reasons)

    # Assert
    expected = pl.DataFrame(
        {
            "movement_number": ["101", "102"],
            "check_status": ["mismatch", "ok"],
            "review_status": ["ok", "ok"],
            "review_reason": ["human override", ""],
        }
    )
    assert_frame_equal(out, expected)


def test_merge_review_feedback_handles_numeric_movement_numbers_as_str_keys():
    # Arrange: integer movement numbers, string keys in mappings
    df = pl.DataFrame(
        {
            "movement_number": [1, 2],
            "check_status": ["mismatch", "mismatch"],
        }
    )
    status = {"1": "ok"}
    reasons = {"2": "explained"}

    # Act
    out = merge_review_feedback(df, status, reasons)

    # Assert
    expected = pl.DataFrame(
        {
            "movement_number": [1, 2],
            "check_status": ["mismatch", "mismatch"],
            "review_status": ["ok", "mismatch"],
            "review_reason": ["", "explained"],
        }
    )
    assert_frame_equal(out, expected)


def test_merge_review_feedback_defaults_to_empty_when_check_status_missing():
    # Arrange: no check_status column present
    df = pl.DataFrame({"movement_number": ["201"]})

    # Act
    out = merge_review_feedback(df, status={}, reasons={})

    # Assert: review_status falls back to ""; review_reason also ""
    expected = pl.DataFrame(
        {
            "movement_number": ["201"],
            "review_status": [""],
            "review_reason": [""],
        }
    )
    assert_frame_equal(out, expected)
