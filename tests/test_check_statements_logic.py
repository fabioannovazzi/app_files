import io
import json
import re
import sys
import zipfile
from datetime import date
from pathlib import Path
from types import ModuleType
from xml.etree import ElementTree as ET

import polars as pl
import pytest

# Ensure 'src' is on sys.path so absolute imports resolve
ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
for path in (ROOT, SRC):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

# Minimal utilities.config stub
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

# Stub for modules.utils.polars_excel_writer
utils_pkg = ModuleType("modules.utils")
polars_writer_mod = ModuleType("modules.utils.polars_excel_writer")
polars_writer_mod._prepare_df_for_excel = lambda df: df
utils_pkg.polars_excel_writer = polars_writer_mod
sys.modules["modules.utils"] = utils_pkg
sys.modules["modules.utils.polars_excel_writer"] = polars_writer_mod

import src.check_statements as logic
from src.check_statements_logic import (
    Transaction,
    _enrich_transaction,
    _extract_counterparty_code_and_name,
)


def _extract_sheet_names(xlsx_bytes: bytes) -> list[str]:
    with zipfile.ZipFile(io.BytesIO(xlsx_bytes)) as zf:
        workbook_xml = zf.read("xl/workbook.xml")
    root = ET.fromstring(workbook_xml)
    ns = {"ss": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}
    return [sheet.attrib["name"] for sheet in root.findall("ss:sheets/ss:sheet", ns)]


def test_parse_date_any_accepts_excel_serial_string_with_fraction() -> None:
    """Numbers like 33712.62 should be treated as Excel serial dates."""
    assert logic._parse_date_any("33712.62") == date(1992, 4, 18)


def test_load_fee_patterns_reads_and_compiles_case_insensitive(tmp_path: Path) -> None:
    # Arrange
    cfg = tmp_path / "fee_patterns.json"
    patterns = ["fee", "commissione.*banca"]
    cfg.write_text(json.dumps(patterns), encoding="utf-8")

    # Act
    compiled = logic.load_fee_patterns(cfg)

    # Assert
    assert isinstance(compiled, list) and len(compiled) == 2
    assert all(hasattr(p, "search") for p in compiled)
    # Case-insensitive matching works
    assert compiled[0].flags & re.IGNORECASE
    assert compiled[0].search("FEE")
    assert compiled[1].search("COMMISSIONE BANCA")


def test_load_fee_patterns_missing_file_returns_empty_list(tmp_path: Path) -> None:
    # Arrange
    missing = tmp_path / "does_not_exist.json"

    # Act
    compiled = logic.load_fee_patterns(missing)

    # Assert
    assert compiled == []


def test_load_fee_patterns_skips_invalid_patterns(tmp_path: Path) -> None:
    # Arrange
    cfg = tmp_path / "fee_patterns.json"
    cfg.write_text(json.dumps(["valid.*", "("]), encoding="utf-8")

    # Act
    compiled = logic.load_fee_patterns(cfg)

    # Assert
    assert len(compiled) == 1
    assert compiled[0].pattern == "valid.*"


@pytest.mark.parametrize(
    "beneficiary,expected",
    [
        ("Foo spa", "FOO SPA"),
        ("", ""),
        (None, ""),
    ],
)
def test_transaction_normalised_beneficiary_uppercases_and_handles_empty(
    beneficiary, expected
) -> None:
    # Arrange
    tx = logic.Transaction(
        date=date(2024, 1, 1), amount=0.0, description="", beneficiary=beneficiary
    )

    # Act
    result = tx.normalised_beneficiary()

    # Assert
    assert result == expected


def test_transaction_normalised_description_local_cleaning_when_no_llm(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Arrange
    raw = (
        "Bonifico o/c: 123 Disposizione a favore di Foo S.p.A. "
        "12/08/2024 ABI-CAB: 12345-67890 CIGXYZ CUP123 1.234,56"
    )
    tx = logic.Transaction(date=date(2024, 8, 12), amount=10.0, description=raw)
    monkeypatch.setattr(logic, "_DESCRIPTION_CACHE", {}, raising=True)

    # Act
    cleaned = tx.normalised_description(llm_wrapper=None)

    # Assert
    assert cleaned == "FOO S P A"


def test_transaction_normalised_description_uses_cache_before_local_cleaner(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Arrange
    desc = "Already there"
    tx = logic.Transaction(date=date(2024, 1, 1), amount=0.0, description=desc)
    monkeypatch.setattr(logic, "_DESCRIPTION_CACHE", {desc: "IN CACHE"}, raising=True)

    def should_not_run(*args, **kwargs):  # pragma: no cover - must not be called
        raise AssertionError("Local cleaner should not be invoked when cache hit")

    monkeypatch.setattr(logic, "_clean_description_local", should_not_run, raising=True)

    # Act
    result = tx.normalised_description(llm_wrapper=object())

    # Assert
    assert result == "IN CACHE"


def test_transaction_normalised_description_ignores_llm_wrapper(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Arrange
    desc = "Bonifico a favore di Foo S.p.A."
    tx = logic.Transaction(date=date(2024, 1, 1), amount=0.0, description=desc)
    cache: dict[str, str] = {}
    monkeypatch.setattr(logic, "_DESCRIPTION_CACHE", cache, raising=True)

    calls: list[str] = []

    def fake_local(value: str) -> str:
        calls.append(value)
        return "FOO S P A"

    monkeypatch.setattr(logic, "_clean_description_local", fake_local, raising=True)

    # Act
    out = tx.normalised_description(llm_wrapper=object())

    # Assert
    assert calls == [desc]
    assert out == "FOO S P A"
    assert cache == {}


@pytest.mark.parametrize(
    "raw, expected_code, expected_name",
    [
        ("12345- Beneficiario", "12345", "Beneficiario"),
        ("- CLIENTE", None, "CLIENTE"),
        ("TESORERIA-GENERALE", None, "TESORERIA-GENERALE"),
        ("BANCA-ONLINE", None, "BANCA-ONLINE"),
        ("IVA- VENDITE", "IVA", "VENDITE"),
    ],
)
def test_extract_counterparty_code_and_name_guarded_split(
    raw: str, expected_code: str | None, expected_name: str
) -> None:
    # Act
    result_code, result_name = _extract_counterparty_code_and_name(raw)

    # Assert
    assert result_code == expected_code
    assert result_name == expected_name


def test_reconcile_transactions_exclude_accounts_removes_ignored_accounts() -> None:
    """Ledger entries from excluded accounts should be dropped before matching."""

    # Arrange: ledger with three distinct accounts
    ledger = [
        logic.Transaction(
            date=date(2024, 1, 1),
            amount=1.0,
            description="first",
            metadata={"account_id": "A"},
        ),
        logic.Transaction(
            date=date(2024, 1, 2),
            amount=2.0,
            description="second",
            metadata={"account_id": "B"},
        ),
        logic.Transaction(
            date=date(2024, 1, 3),
            amount=3.0,
            description="third",
            metadata={"account_id": "C"},
        ),
    ]
    bank: list[logic.Transaction] = []

    # Baseline: all accounts included
    _, _, unmatched_all = logic.reconcile_transactions(bank, ledger)
    assert unmatched_all == [0, 1, 2]

    # Act: filter out ledger entries from account "B" via ``ledger_exclude_accounts``
    _, _, unmatched_filtered = logic.reconcile_transactions(
        bank, ledger, ledger_exclude_accounts={"B"}
    )

    # Assert: ledger entry with account ``B`` is removed from the results
    assert unmatched_filtered == [0, 2]


def test_export_to_excel_filters_unmatched_rows() -> None:
    # Arrange
    from modules.utilities.utils import get_row_count

    bank = [
        logic.Transaction(
            date=date(2024, 6, 1),
            amount=100.0,
            description="BON.DA EXAMPLE SUPPLIER S.R.L.",
            beneficiary="",
        ),
        logic.Transaction(
            date=date(2024, 6, 2),
            amount=0.0,
            description="NUOVI ORARI FILIALE",
            beneficiary="",
        ),
    ]
    # Both transactions are initially unmatched
    data = logic.export_to_excel(
        bank,
        [],
        matched_pairs=[],
        unmatched_bank=[0, 1],
        unmatched_ledger=[],
    )

    # Act
    unmatched_bank_df = pl.read_excel(io.BytesIO(data), sheet_name="unmatched_bank")
    dropped_df = pl.read_excel(io.BytesIO(data), sheet_name="unmatched_bank_dropped")
    sheet_names = _extract_sheet_names(data)

    # Assert
    assert get_row_count(unmatched_bank_df) == 1
    assert get_row_count(dropped_df) == 1
    assert sheet_names == [
        "matched",
        "unmatched_bank",
        "unmatched_bank_dropped",
        "unmatched_ledger",
    ]


def test_export_to_excel_logs_filter(monkeypatch) -> None:
    from modules.utilities.utils import get_row_count
    from src import final_pass_filter

    calls: dict[str, int] = {}

    def spy(df: pl.DataFrame, *, collect_stats: bool = False, **kwargs):
        calls["before"] = get_row_count(df)
        result = final_pass_filter.clean_bank_not_matched(
            df, collect_stats=collect_stats, **kwargs
        )
        cleaned = result[0] if isinstance(result, tuple) else result
        calls["after"] = get_row_count(cleaned)
        return result

    messages: list[str] = []
    monkeypatch.setattr(logic, "clean_bank_not_matched", spy)
    monkeypatch.setattr(logic.logger, "info", lambda msg, *a: messages.append(msg % a))

    bank = [
        logic.Transaction(
            date=date(2024, 6, 1),
            amount=100.0,
            description="BON.DA EXAMPLE SUPPLIER S.R.L.",
            beneficiary="",
        ),
        logic.Transaction(
            date=date(2024, 6, 2),
            amount=0.0,
            description="NUOVI ORARI FILIALE",
            beneficiary="",
        ),
    ]
    logic.export_to_excel(
        bank,
        [],
        matched_pairs=[],
        unmatched_bank=[0, 1],
        unmatched_ledger=[],
    )

    assert calls == {"before": 2, "after": 1}
    assert messages == [
        "final-pass-filter: removed 1 balance-summary rows",
        "FinalPassFilter applied: bank_unmatched 2 → 1",
    ]


def test_export_to_excel_skips_filter_when_disabled(monkeypatch) -> None:
    from modules.utilities.utils import get_row_count

    def spy(
        _: pl.DataFrame, *, collect_stats: bool = False, **kwargs
    ):  # pragma: no cover - should not be called
        raise AssertionError("clean_bank_not_matched should not run when disabled")

    monkeypatch.setattr(logic, "clean_bank_not_matched", spy)

    bank = [
        logic.Transaction(
            date=date(2024, 6, 1),
            amount=100.0,
            description="BON.DA EXAMPLE SUPPLIER S.R.L.",
            beneficiary="",
        ),
        logic.Transaction(
            date=date(2024, 6, 2),
            amount=0.0,
            description="NUOVI ORARI FILIALE",
            beneficiary="",
        ),
    ]
    data = logic.export_to_excel(
        bank,
        [],
        matched_pairs=[],
        unmatched_bank=[0, 1],
        unmatched_ledger=[],
        final_pass_filter=False,
    )

    unmatched_bank_df = pl.read_excel(io.BytesIO(data), sheet_name="unmatched_bank")
    sheet_names = _extract_sheet_names(data)
    assert get_row_count(unmatched_bank_df) == 2
    assert sheet_names == ["matched", "unmatched_bank", "unmatched_ledger"]


def test_export_to_excel_omits_diagnostics_sheet() -> None:
    bank = [
        logic.Transaction(
            date=date(2024, 6, 1),
            amount=100.0,
            description="BON.DA EXAMPLE SUPPLIER S.R.L.",
            beneficiary="",
        ),
        logic.Transaction(
            date=date(2024, 6, 2),
            amount=0.0,
            description="NUOVI ORARI FILIALE",
            beneficiary="",
        ),
    ]
    diagnostics = {
        "unmatched_bank_count_before_filter": 5,
        "unmatched_bank_count_after_filter": 3,
    }

    data = logic.export_to_excel(
        bank,
        [],
        matched_pairs=[],
        unmatched_bank=[0, 1],
        unmatched_ledger=[],
        diagnostics=diagnostics,
    )

    sheet_names = _extract_sheet_names(data)
    assert sheet_names == [
        "matched",
        "unmatched_bank",
        "unmatched_bank_dropped",
        "unmatched_ledger",
    ]


def test_export_to_excel_stage_flags_align_with_counters() -> None:
    bank = [
        logic.Transaction(
            date=date(2024, 6, 1),
            amount=100.0,
            description="Bonifico cliente",
            beneficiary="",
        ),
        logic.Transaction(
            date=date(2024, 6, 5),
            amount=1500.0,
            description="Stipendio Giugno",
            beneficiary="",
        ),
    ]
    ledger = [
        logic.Transaction(
            date=date(2024, 6, 1),
            amount=100.0,
            description="Bonifico banca",
            beneficiary="",
        ),
        logic.Transaction(
            date=date(2024, 6, 5),
            amount=1200.0,
            description="Pagamento stipendi",
            beneficiary="",
            metadata={"counter_account_desc": "Stipendi e salari"},
        ),
    ]
    matched_pairs, unmatched_bank, unmatched_ledger, stage_counts = (
        logic.staged_reconcile(
            bank,
            ledger,
            tolerance=0.5,
            date_window=5,
            use_absolute_amounts=False,
            up_to_stage=8,
            dense_day=False,
        )
    )

    assert "stage_origin_counts" in stage_counts
    assert stage_counts.get("matched_bank_total") == sum(
        stage_counts["stage_origin_counts"].values()
    )
    assert stage_counts.get("stage1_assign") == 1
    assert stage_counts.get("stage5_salary_gate") == 1
    stage_flags = stage_counts.get("stage_flags")
    assert isinstance(stage_flags, dict) and len(stage_flags) == 2

    data = logic.export_to_excel(
        bank,
        ledger,
        matched_pairs=matched_pairs,
        unmatched_bank=unmatched_bank,
        unmatched_ledger=unmatched_ledger,
        final_pass_filter=False,
        stage_flags=stage_flags,
    )

    matched_df = pl.read_excel(io.BytesIO(data), sheet_name="matched")
    columns = set(matched_df.columns)
    expected_columns = {
        "match_stage",
        "cash_like_evidence",
        "card_payment_evidence",
        "payroll_tax_evidence",
        "beneficiary_name_evidence",
    }
    assert expected_columns.issubset(columns)

    bool_columns = [
        "cash_like_evidence",
        "card_payment_evidence",
        "payroll_tax_evidence",
        "beneficiary_name_evidence",
    ]
    matched_df = matched_df.with_columns(
        [pl.col(col).cast(pl.Boolean) for col in bool_columns]
    )
    stage_labels = matched_df.get_column("match_stage").to_list()
    assert any("Amount" in label for label in stage_labels)
    assert any("Payroll" in label for label in stage_labels)
    payroll_hits = matched_df.get_column("payroll_tax_evidence").cast(pl.Boolean).sum()
    assert payroll_hits >= 1

    assign_row = matched_df.filter(pl.col("match_type") == "assign").to_dicts()[0]
    salary_row = matched_df.filter(pl.col("match_type") == "salary_gate").to_dicts()[0]

    assert "Amount" in assign_row["match_stage"]
    assert assign_row["payroll_tax_evidence"] is False
    assert "Payroll" in salary_row["match_stage"]
    assert salary_row["payroll_tax_evidence"] is True

    stage_sum_dict = {
        "s1": matched_df.filter(
            pl.col("match_stage").str.contains("stage 1", literal=False)
        ).height,
        "s2": matched_df.filter(
            pl.col("match_stage").str.contains("stage 2", literal=False)
        ).height,
        "s3": matched_df.filter(pl.col("cash_like_evidence").cast(pl.Boolean)).height,
        "s4": matched_df.filter(
            pl.col("card_payment_evidence").cast(pl.Boolean)
        ).height,
        "s5": matched_df.filter(pl.col("payroll_tax_evidence").cast(pl.Boolean)).height,
        "s6": matched_df.filter(
            pl.col("beneficiary_name_evidence").cast(pl.Boolean)
        ).height,
        "s7": matched_df.filter(pl.col("evidence_iban").cast(pl.Boolean)).height,
        "s8": matched_df.filter(
            pl.col("evidence_reference_id").cast(pl.Boolean)
        ).height,
    }

    expected_counts = {
        "s1": int(stage_counts.get("stage1_assign", 0)),
        "s2": int(stage_counts.get("stage2_fix_fee", 0)),
        "s3": int(stage_counts.get("stage3_evidence", 0)),
        "s4": int(stage_counts.get("stage4_evidence", 0)),
        "s5": int(stage_counts.get("stage5_salary_gate", 0)),
        "s6": int(stage_counts.get("stage6_beneficiary", 0)),
        "s7": int(stage_counts.get("stage7_iban", 0)),
        "s8": int(stage_counts.get("stage8_reference", 0)),
    }
    for key, expected in expected_counts.items():
        assert stage_sum_dict.get(key, 0) == expected


@pytest.mark.parametrize("col", ["conto", "account"])
def test_load_ledger_files_preserves_account_metadata(col: str) -> None:
    csv = f"Date,Description,Amount,{col}\n2024-01-01,Test,10,{col.upper()}\n"
    txns = logic.load_ledger_files([(f"ledger_{col}.csv", csv.encode())])
    assert len(txns) == 1
    assert txns[0].metadata.get("account_id") == col.upper()


def test_ledger_account_column_allows_ui_and_reconcile_exclusion() -> None:
    """Ledger accounts are exposed to the UI and can be excluded."""

    csv = (
        "Date,Description,Amount,account\n"
        "2024-01-01,First,10,A\n"
        "2024-01-02,Second,20,B\n"
    )
    ledger = logic.load_ledger_files([("ledger.csv", csv.encode())])

    # UI collects available ledger accounts from transaction metadata
    ledger_accounts = sorted(
        meta.get("account_id") or meta.get("account_identifier")
        for tx in ledger
        if (meta := tx.metadata)
        and (meta.get("account_id") or meta.get("account_identifier"))
    )
    assert ledger_accounts == ["A", "B"]

    bank = [logic.Transaction(date=date(2024, 1, 1), amount=10.0, description="")]
    matched, unmatched_bank, unmatched_ledger = logic.reconcile_transactions(
        bank, ledger, ledger_exclude_accounts=["A"]
    )

    assert matched == []
    assert unmatched_bank == [0]
    assert unmatched_ledger == [1]


def test_load_ledger_files_respects_custom_account_column_for_exclusion() -> None:
    """Nonstandard account columns can be mapped and excluded."""

    csv = (
        "Date,Description,Amount,acct_code\n"
        "2024-01-01,First,10,A1\n"
        "2024-01-02,Second,20,B1\n"
    )
    ledger = logic.load_ledger_files(
        [("ledger.csv", csv.encode())], account_column="acct_code"
    )

    ledger_accounts = sorted(
        meta.get("account_id")
        for tx in ledger
        if (meta := tx.metadata) and meta.get("account_id")
    )
    assert ledger_accounts == ["A1", "B1"]

    bank = [logic.Transaction(date=date(2024, 1, 1), amount=10.0, description="")]
    matched, unmatched_bank, unmatched_ledger = logic.reconcile_transactions(
        bank, ledger, ledger_exclude_accounts=["A1"]
    )

    assert matched == []
    assert unmatched_bank == [0]
    assert unmatched_ledger == [1]


def test_ledger_account_collection_includes_non_string_ids() -> None:
    ledger = [
        logic.Transaction(
            date=date(2024, 1, 1),
            amount=10.0,
            description="",
            metadata={"account_id": 101},
        ),
        logic.Transaction(
            date=date(2024, 1, 1),
            amount=20.0,
            description="",
            metadata={"account_id": "B "},
        ),
    ]
    ledger_accounts = sorted(
        {
            acc.strip().casefold() if isinstance(acc, str) else acc
            for tx in ledger
            for acc in [
                tx.metadata.get("account_id") or tx.metadata.get("account_identifier")
            ]
            if acc is not None and (not isinstance(acc, str) or acc.strip())
        },
        key=str,
    )
    assert ledger_accounts == [101, "b"]


def test_build_bank_candidates_handles_half_step_amounts() -> None:
    """Candidate buckets include amounts at half-step boundaries."""
    bank = [logic.Transaction(date=date(2024, 1, 1), amount=21.0, description="")]
    ledger = [logic.Transaction(date=date(2024, 1, 1), amount=23.0, description="")]

    candidates = logic._build_bank_candidates(
        bank, ledger, tolerance=2.0, date_window=0
    )

    assert candidates == [[0]]


def test_enrich_transaction_uses_auxiliary_fields_for_op_type() -> None:
    """ATM in metadata triggers ATM classification."""
    tx = Transaction(
        date=date(2024, 1, 1),
        amount=10.0,
        description="generic",  # no ATM keyword in main description
        metadata={"descr. agg": "Prelievo bancomat"},
    )

    enriched = _enrich_transaction(tx)

    assert enriched.metadata.get("op_type") == "ATM"
