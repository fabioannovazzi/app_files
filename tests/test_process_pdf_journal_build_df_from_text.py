import importlib.util
import sys
import types
from pathlib import Path

_utils_spec = importlib.util.spec_from_file_location(
    "modules.utilities.utils",
    Path(__file__).resolve().parents[1] / "modules" / "utilities" / "utils.py",
)
_utils = importlib.util.module_from_spec(_utils_spec)
assert _utils_spec.loader is not None
_utils_spec.loader.exec_module(_utils)
get_row_count = _utils.get_row_count
get_schema_and_column_names = _utils.get_schema_and_column_names


def _stub_modules():
    pkg_j = types.ModuleType("journal_ingest")
    pkg_j.__path__ = []
    sys.modules["journal_ingest"] = pkg_j

    config = types.ModuleType("journal_ingest.config")
    config.get_recipe = lambda *args, **kwargs: None
    sys.modules["journal_ingest.config"] = config

    core = types.ModuleType("journal_ingest.core")
    core.ParserConfidenceError = type("ParserConfidenceError", (Exception,), {})
    core.ValidationError = type("ValidationError", (Exception,), {})
    sys.modules["journal_ingest.core"] = core

    router = types.ModuleType("journal_ingest.router")
    router.Router = object
    sys.modules["journal_ingest.router"] = router

    strategies = types.ModuleType("journal_ingest.strategies")
    strategies.JournalStrategyTableArea = object
    strategies.JournalStrategyTextLayout = object
    strategies.TablePDFParser = object
    strategies.TextPDFParser = object
    sys.modules["journal_ingest.strategies"] = strategies

    utilities_pkg = sys.modules.setdefault(
        "modules.utilities", types.ModuleType("modules.utilities")
    )
    utilities_pkg.__path__ = [
        str(Path(__file__).resolve().parents[1] / "modules" / "utilities")
    ]
    sys.modules["modules.utilities.utils"] = _utils

    pdf_utils = types.ModuleType("modules.pdf_utils.pdf_utils")
    pdf_utils._extract_pdf_text_with_ocr_once = lambda *a, **k: None
    sys.modules.setdefault("modules.pdf_utils", types.ModuleType("modules.pdf_utils"))
    sys.modules["modules.pdf_utils.pdf_utils"] = pdf_utils

    sys.modules.setdefault("modules.utils", types.ModuleType("modules.utils"))
    pew = types.ModuleType("modules.utils.polars_excel_writer")
    pew.write_polars_excel = lambda *a, **k: None
    sys.modules["modules.utils.polars_excel_writer"] = pew

    pkg_ppj = types.ModuleType("modules.process_pdf_journal")
    pkg_ppj.__path__ = []
    sys.modules["modules.process_pdf_journal"] = pkg_ppj
    pdf_fallback = types.ModuleType("modules.process_pdf_journal.pdf_text_fallback")
    pdf_fallback.parse_pdf_group_lines = lambda *a, **k: []
    pdf_fallback.parse_pdf_posting_groups = lambda *a, **k: []
    pdf_fallback.parse_pdf_text_mode = lambda *a, **k: []
    sys.modules["modules.process_pdf_journal.pdf_text_fallback"] = pdf_fallback


_stub_modules()

logic_spec = importlib.util.spec_from_file_location(
    "modules.process_pdf_journal.logic",
    Path(__file__).resolve().parents[1]
    / "modules"
    / "process_pdf_journal"
    / "logic.py",
)
logic = importlib.util.module_from_spec(logic_spec)
assert logic_spec.loader is not None
logic_spec.loader.exec_module(logic)


def test_build_df_from_text_amount_only_line_is_skipped(monkeypatch):
    monkeypatch.setattr(
        logic,
        "_extract_pdf_text_with_ocr_once",
        lambda *args, **kwargs: type("R", (), {"text": "", "method": ""})(),
    )
    tokens = [
        ["date", "description", "amount"],
        ["2024-06-01", "Coffee", "5.00"],
        ["10.00"],
    ]
    monkeypatch.setattr(logic, "_tokenize_lines", lambda text: tokens)

    df, numeric_tokens = logic._build_df_from_text(b"", use_ocr=False)

    columns, _ = get_schema_and_column_names(df)
    assert get_row_count(df) == 1
    assert columns == ["date", "description", "amount"]
    assert numeric_tokens == ["5.00", "10.00"]
