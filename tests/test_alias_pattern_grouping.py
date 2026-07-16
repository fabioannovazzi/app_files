from __future__ import annotations

import sys
from datetime import date
from pathlib import Path
from types import ModuleType

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
for path in (ROOT, SRC):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

# Minimal stubs for optional modules
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

from src.check_statements.alias_pattern_grouping import (  # noqa: E402
    PatternGroup,
    group_seed_patterns,
)
from src.check_statements.alias_seed import collect_matched_seed_pairs  # noqa: E402
from src.check_statements.models import Transaction  # noqa: E402


def _txn(
    *,
    dt: date,
    amount: float,
    description: str,
    beneficiary: str | None,
    references: list[str] | None = None,
    metadata: dict[str, object] | None = None,
) -> Transaction:
    return Transaction(
        date=dt,
        amount=amount,
        description=description,
        beneficiary=beneficiary,
        reference_ids=references or [],
        metadata=metadata or {},
    )


def test_group_seed_patterns_clusters_by_feature_and_support() -> None:
    bank = [
        _txn(
            dt=date(2024, 1, 2),
            amount=100.0,
            description="Bonifico Supplier Alpha INV-001",
            beneficiary="Supplier Alpha",
            metadata={"details": "Pay Supplier Alpha", "language": "it"},
        ),
        _txn(
            dt=date(2024, 1, 4),
            amount=200.0,
            description="Bonifico Supplier Alpha INV-002",
            beneficiary="Supplier Alpha",
            metadata={"details": "Pay Supplier Alpha", "language": "it"},
        ),
        _txn(
            dt=date(2024, 1, 5),
            amount=300.0,
            description="Bonifico Verdi",
            beneficiary="Verdi",
            references=["INV-003"],
        ),
    ]

    ledger = [
        _txn(
            dt=date(2024, 1, 2),
            amount=100.0,
            description="Pagamento Supplier Alpha Ltd",
            beneficiary="Supplier Alpha Ltd",
            references=["INV-001"],
            metadata={"details": "Fattura Supplier Alpha", "language": "it"},
        ),
        _txn(
            dt=date(2024, 1, 4),
            amount=200.0,
            description="Pagamento Supplier Alpha Ltd",
            beneficiary="Supplier Alpha Ltd",
            references=["INV-002"],
            metadata={"details": "Fattura Supplier Alpha", "language": "it"},
        ),
        _txn(
            dt=date(2024, 1, 6),
            amount=300.0,
            description="Pagamento Verdi INV-003",
            beneficiary="Verdi Srl",
        ),
    ]

    matched_pairs = [(0, 0, "assign"), (1, 1, "assign"), (2, 2, "assign")]
    candidates = [[0], [1], [2]]

    seeds = collect_matched_seed_pairs(
        bank,
        ledger,
        matched_pairs,
        candidates,
        exclude_types=set(),
        existing_alias_map={},
    )

    groups = group_seed_patterns(seeds, min_support=2, max_groups=10)
    assert groups
    top = groups[0]
    assert isinstance(top, PatternGroup)
    assert top.field == "beneficiary"
    assert top.support == 2
    assert top.bank_token == "supplier alpha"
    assert top.ledger_token == "supplier alpha ltd"
    payload = top.to_payload()
    assert payload["support"] == 2
    assert payload["field"] == "beneficiary"
    assert len(payload["examples"]) >= 1


def test_group_seed_patterns_respects_field_priority_and_filters_support() -> None:
    bank = [
        _txn(
            dt=date(2024, 2, 1),
            amount=500.0,
            description="Pagamento ID123",
            beneficiary=None,
        ),
        _txn(
            dt=date(2024, 2, 3),
            amount=700.0,
            description="Pagamento ID123",
            beneficiary=None,
        ),
        _txn(
            dt=date(2024, 2, 7),
            amount=900.0,
            description="Pagamento ID124",
            beneficiary=None,
        ),
    ]
    ledger = [
        _txn(
            dt=date(2024, 2, 1),
            amount=500.0,
            description="Invoice ID123",
            beneficiary=None,
        ),
        _txn(
            dt=date(2024, 2, 3),
            amount=700.0,
            description="Invoice ID123",
            beneficiary=None,
        ),
        _txn(
            dt=date(2024, 2, 9),
            amount=900.0,
            description="Invoice ID124",
            beneficiary=None,
        ),
    ]

    matched_pairs = [(0, 0, "assign"), (1, 1, "assign"), (2, 2, "assign")]
    candidates = [[0], [1], [2]]

    seeds = collect_matched_seed_pairs(
        bank,
        ledger,
        matched_pairs,
        candidates,
        exclude_types=set(),
        existing_alias_map={},
    )

    groups = group_seed_patterns(
        seeds,
        min_support=2,
        prefer_fields=("references", "description_tokens"),
    )

    assert groups
    assert groups[0].field in {"references", "description_tokens"}
    assert groups[0].support == 2
    assert any(group.field == "description_tokens" for group in groups)


def test_group_seed_patterns_metadata_tokens_capture_shared_terms() -> None:
    bank = [
        _txn(
            dt=date(2024, 3, 1),
            amount=1000.0,
            description="Bonifico",
            beneficiary=None,
            metadata={"extra_desc": "EXAMPLE SUPPLIER invoice 101"},
        ),
        _txn(
            dt=date(2024, 3, 5),
            amount=1500.0,
            description="Bonifico",
            beneficiary=None,
            metadata={"extra_desc": "Payment Example Supplier invoice 202"},
        ),
    ]
    ledger = [
        _txn(
            dt=date(2024, 3, 1),
            amount=1000.0,
            description="Pagamento",
            beneficiary=None,
            metadata={"extra_desc": "EXAMPLE SUPPLIER fattura 101"},
        ),
        _txn(
            dt=date(2024, 3, 5),
            amount=1500.0,
            description="Pagamento",
            beneficiary=None,
            metadata={"extra_desc": "Example Supplier fattura 202"},
        ),
    ]

    matched_pairs = [(0, 0, "assign"), (1, 1, "assign")]
    candidates = [[0], [1]]

    seeds = collect_matched_seed_pairs(
        bank,
        ledger,
        matched_pairs,
        candidates,
        exclude_types=set(),
        existing_alias_map={},
    )

    groups = group_seed_patterns(
        seeds,
        min_support=2,
        prefer_fields=("metadata_tokens.extra_desc", "description_tokens"),
    )

    assert groups
    assert groups[0].field == "metadata_tokens.extra_desc"
    assert groups[0].support == 2
    token_values = {groups[0].bank_token, groups[0].ledger_token}
    assert any("supplier" in token for token in token_values)
    # pattern with support 1 should be filtered out
    assert all(group.ledger_token != "id124" for group in groups)
