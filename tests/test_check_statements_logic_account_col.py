import sys
import types
from pathlib import Path

import polars as pl

sys.path.append(str(Path(__file__).resolve().parents[1]))

import src  # noqa: F401  # ensure real package is loaded before stubs

modules_to_stub = {
    "parsers.extractors": [
        "extract_beneficiary",
        "extract_references",
        "normalise_name",
    ],
    "modules.pdf_utils.pdf_utils": ["extract_pdf_text_with_ocr"],
    "modules.process_pdf_journal.logic": ["parse_journal"],
    "modules.utilities.config": ["get_naming_params", "get_run_params"],
    "modules.utilities.utils": ["get_row_count", "get_schema_and_column_names"],
    "modules.utils.polars_excel_writer": ["_prepare_df_for_excel"],
    "statements.orchestrator": ["StatementExtractor"],
    "modules.pdf_utils.bank_agent": ["BankTransaction", "extract_bank_pdf"],
    "finance.ledger.ignore_patterns": ["load_ignore_patterns"],
    "src.final_pass_filter": ["FilterReport", "clean_bank_not_matched"],
}


def ensure_package(name: str) -> None:
    if name not in sys.modules:
        pkg = types.ModuleType(name)
        if name == "modules":
            pkg.__path__ = [str(Path(__file__).resolve().parents[1] / "modules")]
        else:
            pkg.__path__ = []
        sys.modules[name] = pkg


for module_name, attrs in modules_to_stub.items():
    parts = module_name.split(".")
    for i in range(1, len(parts)):
        ensure_package(".".join(parts[:i]))
    stub = types.ModuleType(module_name)
    for attr in attrs:
        if attr[0].isupper():
            stub.__dict__[attr] = type(attr, (), {})
        elif module_name == "parsers.extractors" and attr == "extract_references":
            stub.__dict__[attr] = lambda *args, **kwargs: []
        elif attr == "get_schema_and_column_names":
            stub.__dict__[attr] = lambda df: (list(df.columns), list(df.columns))
        elif attr == "get_row_count":
            stub.__dict__[attr] = lambda df: df.height if hasattr(df, "height") else 0
        else:
            stub.__dict__[attr] = lambda *args, **kwargs: None
    sys.modules[module_name] = stub

from src.check_statements import _resolve_account_col


def test_resolve_account_col_exact_match() -> None:
    df = pl.DataFrame({"account": ["123"], "amount": [10]})
    assert _resolve_account_col(df) == "account"


def test_resolve_account_col_ignores_substring() -> None:
    df = pl.DataFrame({"accounting_date": ["2020-01-01"], "value": [1]})
    assert _resolve_account_col(df) is None


def test_resolve_account_col_token_match() -> None:
    df = pl.DataFrame({"acct_num": ["1"], "other": ["x"]})
    assert _resolve_account_col(df) == "acct_num"


def test_resolve_account_col_camelcase() -> None:
    df = pl.DataFrame({"accountId": ["1"], "other": ["x"]})
    assert _resolve_account_col(df) == "accountId"
