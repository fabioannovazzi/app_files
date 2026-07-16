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

# Minimal stubs for optional modules expected by the package
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

from src.check_statements.alias_seed import (  # noqa: E402
    collect_matched_seed_pairs,
    extract_seed_features,
)
from src.check_statements.models import Transaction  # noqa: E402


def _txn(
    *,
    description: str,
    beneficiary: str | None,
    amount: float = 100.0,
    references: list[str] | None = None,
    metadata: dict[str, object] | None = None,
) -> Transaction:
    return Transaction(
        date=date(2024, 1, 5),
        amount=amount,
        description=description,
        reference_ids=references or [],
        beneficiary=beneficiary,
        metadata=metadata or {},
    )


def test_extract_seed_features_collects_multiple_fields() -> None:
    bank = _txn(
        description="Bonifico fattura 1234 Supplier Alpha Ltd",
        beneficiary="Supplier Alpha",
        references=["INV-1234"],
        metadata={"note": "cliente storico"},
    )
    ledger = _txn(
        description="Pagamento fattura 1234 Supplier Alpha Limited",
        beneficiary="SUPPLIER ALPHA LIMITED",
        references=["1234/2024"],
        metadata={"note": "Cliente storico"},
    )

    features = extract_seed_features(bank, ledger)
    feature_map = {feature.field: feature for feature in features}

    assert "beneficiary" in feature_map
    assert feature_map["beneficiary"].bank.normalized == ("supplier alpha",)
    assert feature_map["beneficiary"].ledger.normalized == ("supplier alpha limited",)

    assert "description_tokens" in feature_map
    tokens_bank = feature_map["description_tokens"].bank.normalized
    tokens_ledger = feature_map["description_tokens"].ledger.normalized
    assert "supplier" in tokens_bank
    assert "supplier" in tokens_ledger

    assert "references" in feature_map
    assert feature_map["references"].bank.normalized[0].startswith("inv")

    # Metadata keys are namespaced to avoid collisions between fields.
    assert "metadata.note" in feature_map


def test_collect_matched_seed_pairs_allows_pairs_without_beneficiary() -> None:
    bank = _txn(description="Payment INV123", beneficiary=None)
    ledger = _txn(description="Invoice INV123", beneficiary=None)

    seeds = collect_matched_seed_pairs(
        [bank],
        [ledger],
        matched_pairs=[(0, 0, "assign")],
        bank_candidates=[[0]],
        exclude_types={"FEE"},
        existing_alias_map={},
    )

    assert len(seeds) == 1
    seed = seeds[0]
    assert (
        seed.feature_by_field("beneficiary") is None
        or not seed.feature_by_field("beneficiary").has_both()
    )
    reference_feature = seed.feature_by_field("references")
    assert reference_feature is not None
    assert reference_feature.bank.normalized
    assert "inv123" in reference_feature.ledger.normalized


def test_collect_matched_seed_pairs_skips_known_alias() -> None:
    bank = _txn(description="Bonifico", beneficiary="Example Client")
    ledger = _txn(description="Pagamento", beneficiary="Example Client Spa")

    alias_map = {"example client": "example client spa"}

    seeds = collect_matched_seed_pairs(
        [bank],
        [ledger],
        matched_pairs=[(0, 0, "assign")],
        bank_candidates=[[0]],
        exclude_types={"FEE"},
        existing_alias_map=alias_map,
    )

    assert seeds == []


def test_collect_matched_seed_pairs_ignores_strong_signal_matches() -> None:
    bank = _txn(description="Payment", beneficiary="Test")
    ledger = _txn(description="Payment", beneficiary="Test")

    seeds = collect_matched_seed_pairs(
        [bank],
        [ledger],
        matched_pairs=[(0, 0, "beneficiary")],
        bank_candidates=[[0]],
        exclude_types={"FEE"},
        existing_alias_map={},
    )

    assert seeds == []


def test_extract_seed_features_metadata_tokens_include_repeated_terms() -> None:
    bank = _txn(
        description="Bonifico fornitore invoice",
        beneficiary=None,
        metadata={"extra_desc": "EXAMPLE SUPPLIER invoice 123"},
    )
    ledger = _txn(
        description="Pagamento fornitore",
        beneficiary=None,
        metadata={"extra_desc": "Invoice 456 per Example Supplier"},
    )

    features = extract_seed_features(bank, ledger)
    feature_map = {feature.field: feature for feature in features}
    token_feature = feature_map.get("metadata_tokens.extra_desc")
    assert token_feature is not None
    assert "supplier" in token_feature.bank.normalized
    assert "supplier" in token_feature.ledger.normalized
