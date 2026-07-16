import sys
from pathlib import Path

import polars as pl

ROOT = Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tests.modules.process_pdf_journal.test_modules_process_pdf_journal_logic import (
    _ensure_minimal_journal_ingest_modules,
)


def _import_infer_columns():
    _ensure_minimal_journal_ingest_modules()
    from modules.process_pdf_journal.logic import _infer_columns

    return _infer_columns


def test_infer_columns_sorted_unique_int_is_line_id():
    _infer_columns = _import_infer_columns()
    df = pl.DataFrame({"line": [1, 2, 3], "amount": [1.0, 2.0, 3.0]})

    roles = _infer_columns(df, {})

    assert roles["line_id"]["name"] == "line"
