import json
import sys
from pathlib import Path
from types import ModuleType

import pytest

# Ensure 'src' is on sys.path
ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
for path in (ROOT, SRC):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

# Minimal stubs to satisfy imports in check_statements_logic
modules_pkg = sys.modules.setdefault("modules", ModuleType("modules"))
modules_pkg.__path__ = [str(ROOT / "modules")]

utilities_pkg = ModuleType("modules.utilities")
utilities_pkg.__path__ = [str(ROOT / "modules" / "utilities")]
config_mod = ModuleType("modules.utilities.config")
config_mod.get_naming_params = lambda: {}
config_mod.get_run_params = lambda: {}
utilities_pkg.config = config_mod
utils_mod = ModuleType("modules.utilities.utils")
utils_mod.get_row_count = lambda df: getattr(df, "height", 0)
utils_mod.get_schema_and_column_names = lambda df: (getattr(df, "columns", []), [])
utils_mod.ensure_polars_df = lambda df: df
utilities_pkg.utils = utils_mod
sys.modules["modules.utilities"] = utilities_pkg
sys.modules["modules.utilities.config"] = config_mod
sys.modules["modules.utilities.utils"] = utils_mod

utils_pkg = ModuleType("modules.utils")
polars_writer_mod = ModuleType("modules.utils.polars_excel_writer")
polars_writer_mod._prepare_df_for_excel = lambda df: df
utils_pkg.polars_excel_writer = polars_writer_mod
sys.modules["modules.utils"] = utils_pkg
sys.modules["modules.utils.polars_excel_writer"] = polars_writer_mod
sys.modules.setdefault("modules.pdf_utils", ModuleType("modules.pdf_utils"))
sys.modules.setdefault(
    "modules.process_pdf_journal", ModuleType("modules.process_pdf_journal")
)

from src.check_statements import load_ledger_files


def _csv_bytes(rows: list[tuple[str, str, float]]) -> bytes:
    header = "date,description,amount\n"
    lines = "\n".join(f"{d},{desc},{amt}" for d, desc, amt in rows)
    return (header + lines + "\n").encode()


def test_load_ledger_files_ignores_configured_patterns() -> None:
    csv = _csv_bytes(
        [
            ("2024-01-01", "apertura conto", 100.0),
            ("2024-01-02", "bonifico", 200.0),
        ]
    )
    txns = load_ledger_files([("ledger.csv", csv)])
    assert len(txns) == 1
    assert txns[0].description == "bonifico"


def test_load_ledger_files_supports_custom_config(tmp_path: Path) -> None:
    cfg = tmp_path / "patterns.json"
    cfg.write_text(json.dumps({"ignore_descriptions": ["bonifico"]}), encoding="utf-8")
    csv = _csv_bytes([("2024-01-02", "bonifico", 200.0)])
    txns = load_ledger_files([("ledger.csv", csv)], ignore_patterns_path=cfg)
    assert txns == []
