from __future__ import annotations

import hashlib
import importlib.util
import json
import sys
import zipfile
from copy import deepcopy
from decimal import Decimal
from pathlib import Path

import pytest
from lxml import etree

ROOT = Path(__file__).resolve().parents[2]
PLUGIN_ROOT = ROOT / "plugins" / "bilancio-xbrl-it"
MODULE_PATH = PLUGIN_ROOT / "scripts" / "xbrl_case.py"
RULE_PACK_PATH = PLUGIN_ROOT / "rulepacks" / "it" / "statutory-forms-2026.1.json"
HISTORICAL_RULE_PACK_PATH = (
    PLUGIN_ROOT / "rulepacks" / "it" / "statutory-forms-2016.1.json"
)
DISCLOSURE_RULE_PACK_PATH = PLUGIN_ROOT / "rulepacks" / "it" / "disclosures-2026.1.json"


def _load_module():
    if str(MODULE_PATH.parent) not in sys.path:
        sys.path.insert(0, str(MODULE_PATH.parent))
    spec = importlib.util.spec_from_file_location("bilancio_xbrl_case", MODULE_PATH)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


xbrl_case = _load_module()


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("12.345,67", Decimal("12345.67")),
        ("12,345.67", Decimal("12345.67")),
        ("(1.250,00)", Decimal("-1250.00")),
        ("€ 0,00", Decimal("0.00")),
    ],
)
def test_normalize_decimal_supported_locale_value_returns_exact_decimal(
    raw: str, expected: Decimal
) -> None:
    result = xbrl_case.normalize_decimal(raw)

    assert result == expected


@pytest.mark.parametrize("raw", ["", "   ", None])
def test_normalize_decimal_missing_value_is_not_inferred_as_zero(raw: object) -> None:
    with pytest.raises(ValueError, match="monetary value is required"):
        xbrl_case.normalize_decimal(raw)


@pytest.mark.parametrize(
    "raw",
    [
        "NaN",
        "Infinity",
        "-Infinity",
        "1e6",
        "(-100)",
        Decimal("NaN"),
        float("inf"),
        "1234567890123456789.00",
        "1.1234567",
    ],
)
def test_normalize_decimal_rejects_nonfinite_ambiguous_or_unbounded_value(
    raw: object,
) -> None:
    with pytest.raises(ValueError):
        xbrl_case.normalize_decimal(raw)


def _case_payload(*, listed: bool = False) -> dict[str, object]:
    return {
        "case_id": "case_rossi_2025",
        "tenant_id": "tenant_studio_1",
        "entity": {
            "legal_name": "Rossi S.r.l.",
            "tax_identifier": "IT00000000000",
            "registered_office": "Milano (MI), Italia",
            "legal_form": "SRL",
            "accounting_framework": "OIC",
            "listed": listed,
            "regulated_sector": False,
            "consolidated": False,
            "final_liquidation": False,
            "first_financial_year": False,
            "prior_year_form": "ABBREVIATED",
            "prior_period_start": "2024-01-01",
            "prior_period_end": "2024-12-31",
            "micro_exclusion_flags": [],
        },
        "period": {"start": "2025-01-01", "end": "2025-12-31"},
        "oic_rule_pack": "OIC_2024_2025.1",
        "filing_campaign_year": 2026,
        "taxonomy_checksum": "a" * 64,
    }


def _rule_pack() -> dict[str, object]:
    return json.loads(RULE_PACK_PATH.read_text(encoding="utf-8"))


def _historical_rule_pack() -> dict[str, object]:
    return json.loads(HISTORICAL_RULE_PACK_PATH.read_text(encoding="utf-8"))


def _disclosure_rule_pack() -> dict[str, object]:
    return json.loads(DISCLOSURE_RULE_PACK_PATH.read_text(encoding="utf-8"))


def _regulatory_migration() -> dict[str, object]:
    return {
        "reason": "Adopt the reviewed replacement packs for this open case.",
        "statutory_rule_pack": "IT_CC_2026.1",
        "oic_rule_pack": "OIC_2026.1",
        "taxonomy_id": "PCI_2018-11-04-R2",
        "taxonomy_checksum": "b" * 64,
        "filing_instruction_pack": "RI_2026.1",
        "filing_campaign_year": 2026,
        "early_adoption_flags": ["OIC_AMENDMENTS_2025"],
    }


def test_create_case_listed_entity_is_blocked_as_unsupported(tmp_path: Path) -> None:
    case_dir = tmp_path / "case"

    case = xbrl_case.create_case(
        case_dir, _case_payload(listed=True), _rule_pack(), "preparer_1"
    )

    assert case["state"] == "UNSUPPORTED"
    assert case["unsupported_reasons"] == ["LISTED_OR_UNCONFIRMED"]


def test_create_case_ifrs_entity_is_blocked_before_generation(tmp_path: Path) -> None:
    payload = _case_payload()
    payload["entity"]["accounting_framework"] = "IFRS"

    case = xbrl_case.create_case(tmp_path / "case", payload, _rule_pack(), "preparer_1")

    assert case["state"] == "UNSUPPORTED"
    assert case["unsupported_reasons"] == ["UNSUPPORTED_ACCOUNTING_FRAMEWORK"]


def test_create_case_defaults_to_italian_and_supports_one_english_output(
    tmp_path: Path,
) -> None:
    italian = xbrl_case.create_case(
        tmp_path / "italian", _case_payload(), _rule_pack(), "preparer_1"
    )
    english_payload = _case_payload()
    english_payload["output_language"] = "en"
    english = xbrl_case.create_case(
        tmp_path / "english", english_payload, _rule_pack(), "preparer_1"
    )

    assert italian["output_language"] == "it"
    assert english["output_language"] == "en"


def test_create_case_rejects_unsupported_output_language(tmp_path: Path) -> None:
    payload = _case_payload()
    payload["output_language"] = "fr"

    with pytest.raises(ValueError, match="Output language"):
        xbrl_case.create_case(tmp_path / "case", payload, _rule_pack(), "preparer_1")


@pytest.mark.parametrize(
    ("payload_update", "message"),
    [
        ({"oic_rule_pack": "OIC_UNVERIFIED"}, "exactly one controlled pack"),
        (
            {"filing_instruction_pack": "RI_UNVERIFIED"},
            "exactly one controlled pack",
        ),
        (
            {
                "oic_rule_pack": {
                    "id": "OIC_CALLER_SUPPLIED",
                    "kind": "OIC_ACCOUNTING_RULES",
                }
            },
            "controlled rule-pack identifier",
        ),
    ],
)
def test_create_case_rejects_uncontrolled_regulatory_pack_labels(
    tmp_path: Path, payload_update: dict[str, object], message: str
) -> None:
    payload = _case_payload()
    payload.update(payload_update)

    with pytest.raises(ValueError, match=message):
        xbrl_case.create_case(tmp_path / "case", payload, _rule_pack(), "preparer_1")


def test_create_case_requires_explicit_2025_oic_early_adoption(
    tmp_path: Path,
) -> None:
    payload = _case_payload()
    payload["oic_rule_pack"] = "OIC_2026.1"

    with pytest.raises(ValueError, match="early-adoption flag"):
        xbrl_case.create_case(
            tmp_path / "without-flag", payload, _rule_pack(), "preparer_1"
        )

    payload["early_adoption_flags"] = ["OIC_AMENDMENTS_2025"]
    case = xbrl_case.create_case(
        tmp_path / "with-flag", payload, _rule_pack(), "preparer_1"
    )

    assert case["rule_pack_versions"]["oic_rule_pack"] == "OIC_2026.1"
    assert len(case["oic_rule_pack_checksum"]) == 64
    assert len(case["filing_instruction_pack_checksum"]) == 64


def test_create_case_rejects_non_https_regulatory_source(tmp_path: Path) -> None:
    rule_pack = _rule_pack()
    rule_pack["source_register"][0]["url"] = "http://example.invalid/manual.pdf"

    with pytest.raises(ValueError, match="must use HTTPS"):
        xbrl_case.create_case(
            tmp_path / "case", _case_payload(), rule_pack, "preparer_1"
        )


def test_create_case_rejects_unrecognized_oic_early_adoption_flag(
    tmp_path: Path,
) -> None:
    payload = _case_payload()
    payload["early_adoption_flags"] = ["UNRECOGNIZED_FLAG"]

    with pytest.raises(ValueError, match="does not recognize"):
        xbrl_case.create_case(tmp_path / "case", payload, _rule_pack(), "preparer_1")


def test_create_case_rejects_early_adoption_flag_after_pack_is_mandatory(
    tmp_path: Path,
) -> None:
    payload = _case_payload()
    payload["period"] = {"start": "2026-01-01", "end": "2026-12-31"}
    payload["oic_rule_pack"] = "OIC_2026.1"
    payload["early_adoption_flags"] = ["OIC_AMENDMENTS_2025"]

    with pytest.raises(ValueError, match="invalid after.*mandatory"):
        xbrl_case.create_case(tmp_path / "case", payload, _rule_pack(), "preparer_1")


def test_create_case_rejects_filing_pack_for_another_campaign(
    tmp_path: Path,
) -> None:
    payload = _case_payload()
    payload["filing_campaign_year"] = 2025

    with pytest.raises(ValueError, match="does not match the selected campaign"):
        xbrl_case.create_case(tmp_path / "case", payload, _rule_pack(), "preparer_1")


def test_create_case_supports_2016_onward_period_with_effective_packs(
    tmp_path: Path,
) -> None:
    payload = _case_payload()
    payload["period"] = {"start": "2020-01-01", "end": "2020-12-31"}
    payload["entity"]["prior_period_start"] = "2019-01-01"
    payload["entity"]["prior_period_end"] = "2019-12-31"
    payload["oic_rule_pack"] = "OIC_2016_2023.1"
    case = xbrl_case.create_case(
        tmp_path / "historical", payload, _historical_rule_pack(), "preparer_1"
    )
    metrics = [
        {"year": 2020, "assets": "1", "revenue": "1", "employees": "1"},
        {"year": 2019, "assets": "1", "revenue": "1", "employees": "1"},
    ]

    result = xbrl_case.determine_forms(
        case,
        metrics,
        _historical_rule_pack(),
        "preparer_1",
        case["revision_id"],
    )

    assert result["rule_pack_versions"]["statutory_rule_pack"] == "IT_CC_2016.1"
    assert result["form_analysis"]["eligible_forms"] == [
        "MICRO",
        "ABBREVIATED",
        "ORDINARY",
    ]


def test_create_case_rejects_rule_pack_outside_period_up_front(tmp_path: Path) -> None:
    payload = _case_payload()
    payload["period"] = {"start": "2020-01-01", "end": "2020-12-31"}
    payload["entity"]["prior_period_start"] = "2019-01-01"
    payload["entity"]["prior_period_end"] = "2019-12-31"
    payload["oic_rule_pack"] = "OIC_2016_2023.1"

    with pytest.raises(ValueError, match="not effective for the reporting period"):
        xbrl_case.create_case(tmp_path / "case", payload, _rule_pack(), "preparer_1")


@pytest.mark.parametrize(
    "missing_field", ["legal_name", "tax_identifier", "registered_office"]
)
def test_create_case_rejects_missing_required_entity_identity(
    tmp_path: Path, missing_field: str
) -> None:
    payload = _case_payload()
    payload["entity"].pop(missing_field)

    with pytest.raises(ValueError, match=missing_field):
        xbrl_case.create_case(tmp_path / "case", payload, _rule_pack(), "preparer_1")


def test_create_case_non_first_year_requires_prior_form(tmp_path: Path) -> None:
    payload = _case_payload()
    payload["entity"].pop("prior_year_form")

    with pytest.raises(ValueError, match="prior-year statutory form"):
        xbrl_case.create_case(tmp_path / "case", payload, _rule_pack(), "preparer_1")


def test_create_case_requires_explicit_reviewed_micro_exclusions(
    tmp_path: Path,
) -> None:
    payload = _case_payload()
    payload["entity"].pop("micro_exclusion_flags")

    with pytest.raises(ValueError, match="micro-exclusion flags"):
        xbrl_case.create_case(tmp_path / "case", payload, _rule_pack(), "preparer_1")


def test_create_case_rejects_incomplete_or_overlapping_comparative_period(
    tmp_path: Path,
) -> None:
    payload = _case_payload()
    payload["entity"]["prior_period_start"] = "2024-01-01"
    payload["entity"].pop("prior_period_end")

    with pytest.raises(ValueError, match="requires both prior start and end"):
        xbrl_case.create_case(
            tmp_path / "incomplete", payload, _rule_pack(), "preparer_1"
        )

    payload["entity"]["prior_period_end"] = "2025-01-01"
    with pytest.raises(ValueError, match="overlaps"):
        xbrl_case.create_case(tmp_path / "overlap", payload, _rule_pack(), "preparer_1")


def test_create_case_requires_explicit_dates_for_every_comparative_period(
    tmp_path: Path,
) -> None:
    payload = _case_payload()
    payload["entity"].pop("prior_period_start")
    payload["entity"].pop("prior_period_end")

    with pytest.raises(ValueError, match="explicit comparative period"):
        xbrl_case.create_case(tmp_path / "case", payload, _rule_pack(), "preparer_1")


def _write_trial_balance(path: Path, *, imbalance: bool = False) -> None:
    liability_closing = "-99,00" if imbalance else "-100,00"
    path.write_text(
        "account_code;account_description;opening_signed;period_debit;period_credit;closing_signed;prior_closing_signed\n"
        "1000;Cassa;90,00;10,00;0,00;100,00;90,00\n"
        f"2000;Debiti;-90,00;0,00;10,00;{liability_closing};-90,00\n",
        encoding="utf-8",
    )


def _created_case(tmp_path: Path) -> tuple[Path, dict[str, object]]:
    case_dir = tmp_path / "case"
    case = xbrl_case.create_case(case_dir, _case_payload(), _rule_pack(), "preparer_1")
    return case_dir, case


def _first_year_mapping_decisions(case: dict[str, object]) -> list[dict[str, object]]:
    entries = case["trial_balance"]["entries"]
    return [
        {
            "account_id": entries[0]["account_id"],
            "decision": "ACCEPTED",
            "allocations": [
                {
                    "canonical_line": "FIRST_YEAR.ASSETS",
                    "statement_section": "ASSETS",
                    "xbrl_concept": "itcc:Assets",
                    "xbrl_sign_multiplier": "1",
                    "current_amount": "100",
                    "evidence_status": "OBSERVED",
                }
            ],
        },
        {
            "account_id": entries[1]["account_id"],
            "decision": "ACCEPTED",
            "allocations": [
                {
                    "canonical_line": "FIRST_YEAR.LIABILITIES_EQUITY",
                    "statement_section": "LIABILITIES_EQUITY",
                    "xbrl_concept": "itcc:LiabilitiesEquity",
                    "xbrl_sign_multiplier": "-1",
                    "current_amount": "-100",
                    "evidence_status": "OBSERVED",
                }
            ],
        },
    ]


def test_cli_status_reads_the_integrity_verified_case_record(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    case_dir, case = _created_case(tmp_path)

    result = xbrl_case.main(["status", "--case-dir", str(case_dir)])
    output = json.loads(capsys.readouterr().out)

    assert result == 0
    assert output["case_id"] == case["case_id"]
    assert output["revision_id"] == "rev_1"


def test_ingest_trial_balance_excluding_opening_detects_exact_convention(
    tmp_path: Path,
) -> None:
    _, case = _created_case(tmp_path)
    source = tmp_path / "trial_balance.csv"
    _write_trial_balance(source)

    result = xbrl_case.ingest_trial_balance(case, source, "preparer_1", "rev_1")

    calibration = result["trial_balance"]["calibration"]
    assert calibration["detected_convention"] == "TURNOVER_EXCLUDES_OPENING"
    assert calibration["unmatched_rows"] == 0
    assert calibration["closing_entries_assessment"] == {
        "appears_included": None,
        "status": "REQUIRES_PROFESSIONAL_CONFIRMATION",
        "reason": (
            "The supported numeric columns do not mechanically distinguish "
            "ordinary turnover from closing entries."
        ),
    }
    assert len(result["trial_balance"]["source_anchors"]) == 14
    first_anchor = result["trial_balance"]["source_anchors"][0]
    assert first_anchor["column"] == "A"
    assert first_anchor["column_header"] == "account_code"
    assert first_anchor["normalized_column"] == "account_code"
    assert first_anchor["raw_value"] == "1000"
    assert first_anchor["normalized_value"] == "1000"


def test_first_financial_year_uses_only_current_annuality_end_to_end(
    tmp_path: Path,
) -> None:
    payload = _case_payload()
    payload["entity"]["first_financial_year"] = True
    payload["entity"].pop("prior_year_form")
    payload["entity"].pop("prior_period_start")
    payload["entity"].pop("prior_period_end")
    case = xbrl_case.create_case(tmp_path / "case", payload, _rule_pack(), "preparer_1")
    case["statutory_presentation_required"] = False
    source = tmp_path / "current-only.csv"
    source.write_text(
        "account_code;account_description;opening_signed;period_debit;"
        "period_credit;closing_signed\n"
        "1000;Cassa;0;100;0;100\n"
        "2000;Capitale;0;0;100;-100\n",
        encoding="utf-8",
    )
    case = xbrl_case.ingest_trial_balance(
        case, source, "preparer_1", case["revision_id"]
    )
    assert case["trial_balance"]["comparative_status"] == (
        "NOT_APPLICABLE_FIRST_FINANCIAL_YEAR"
    )
    assert all(
        entry["prior_closing_signed"] is None
        for entry in case["trial_balance"]["entries"]
    )
    case = xbrl_case.confirm_parser(
        case,
        "TURNOVER_EXCLUDES_OPENING",
        "preparer_1",
        case["revision_id"],
    )
    case = xbrl_case.determine_forms(
        case,
        [{"year": 2025, "assets": "35000", "revenue": "1", "employees": "1"}],
        _rule_pack(),
        "preparer_1",
        case["revision_id"],
    )
    case = xbrl_case.select_form(case, "ABBREVIATED", "preparer_1", case["revision_id"])
    case = xbrl_case.apply_mapping_decisions(
        case,
        _first_year_mapping_decisions(case),
        "preparer_1",
        case["revision_id"],
    )
    result = xbrl_case.build_statements(case, "preparer_1", case["revision_id"])

    assert result["statements"]["comparative_status"] == (
        "NOT_APPLICABLE_FIRST_FINANCIAL_YEAR"
    )
    assert all(fact["prior_value"] is None for fact in result["canonical_facts"])
    assert all(fact["prior_value"] is None for fact in result["statements"]["facts"])
    preview = xbrl_case.render_preview_html(result).decode("utf-8")
    assert "Valori del primo esercizio" in preview
    assert "Comparativo" not in preview


def test_first_financial_year_rejects_comparative_source_column(tmp_path: Path) -> None:
    payload = _case_payload()
    payload["entity"]["first_financial_year"] = True
    payload["entity"].pop("prior_year_form")
    payload["entity"].pop("prior_period_start")
    payload["entity"].pop("prior_period_end")
    case = xbrl_case.create_case(tmp_path / "case", payload, _rule_pack(), "preparer_1")
    source = tmp_path / "invalid-comparative.csv"
    _write_trial_balance(source)

    with pytest.raises(ValueError, match="cannot contain comparative columns"):
        xbrl_case.ingest_trial_balance(case, source, "preparer_1", case["revision_id"])


def test_first_financial_year_accepts_current_only_debit_credit_layout(
    tmp_path: Path,
) -> None:
    payload = _case_payload()
    payload["entity"]["first_financial_year"] = True
    payload["entity"].pop("prior_year_form")
    payload["entity"].pop("prior_period_start")
    payload["entity"].pop("prior_period_end")
    case = xbrl_case.create_case(tmp_path / "case", payload, _rule_pack(), "preparer_1")
    source = tmp_path / "current-only-separate.csv"
    source.write_text(
        "account_code;account_description;opening_debit;opening_credit;"
        "period_debit;period_credit;closing_debit;closing_credit\n"
        "1000;Cassa;0;0;100;0;100;0\n"
        "2000;Capitale;0;0;0;100;0;100\n",
        encoding="utf-8",
    )

    result = xbrl_case.ingest_trial_balance(
        case, source, "preparer_1", case["revision_id"]
    )

    assert result["trial_balance"]["layout"] == "SEPARATE_DEBIT_CREDIT"
    assert result["trial_balance"]["entries"][0]["prior_closing_debit"] is None
    assert result["trial_balance"]["entries"][1]["prior_closing_credit"] is None


def test_ingest_trial_balance_rejects_aliases_that_collide_after_normalization(
    tmp_path: Path,
) -> None:
    _, case = _created_case(tmp_path)
    source = tmp_path / "duplicate-header.csv"
    source.write_text(
        "account_code;conto;account_description;opening_signed;period_debit;"
        "period_credit;closing_signed;prior_closing_signed\n"
        "ORIGINAL;OVERWRITE;Cassa;90;10;0;100;90\n",
        encoding="utf-8",
    )

    with pytest.raises(
        ValueError,
        match="Duplicate normalized column 'account_code'.*A.*B",
    ):
        xbrl_case.ingest_trial_balance(case, source, "preparer_1", "rev_1")


def test_ingest_trial_balance_preserves_original_header_and_raw_cell_text(
    tmp_path: Path,
) -> None:
    _, case = _created_case(tmp_path)
    source = tmp_path / "original-cell.csv"
    source.write_text(
        " account_code ;account_description;opening_signed;period_debit;"
        "period_credit;closing_signed;prior_closing_signed\n"
        " 1000 ;Cassa;90;10;0;100;90\n"
        "2000;Debiti;-90;0;10;-100;-90\n",
        encoding="utf-8",
    )

    result = xbrl_case.ingest_trial_balance(
        case, source, "preparer_1", case["revision_id"]
    )

    anchor = result["trial_balance"]["source_anchors"][0]
    assert anchor["column_header"] == " account_code "
    assert anchor["normalized_column"] == "account_code"
    assert anchor["raw_value"] == " 1000 "
    assert anchor["normalized_value"] == "1000"


def test_ingest_signed_trial_balance_requires_turnover_columns(tmp_path: Path) -> None:
    _, case = _created_case(tmp_path)
    source = tmp_path / "missing-turnover.csv"
    source.write_text(
        "account_code;account_description;opening_signed;closing_signed;"
        "prior_closing_signed\n"
        "1000;Cassa;90;100;90\n",
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="does not match supported"):
        xbrl_case.ingest_trial_balance(case, source, "preparer_1", "rev_1")


def test_ingest_trial_balance_blank_monetary_cell_is_not_zero(tmp_path: Path) -> None:
    _, case = _created_case(tmp_path)
    source = tmp_path / "blank-turnover.csv"
    source.write_text(
        "account_code;account_description;opening_signed;period_debit;"
        "period_credit;closing_signed;prior_closing_signed\n"
        "1000;Cassa;90;;0;100;90\n",
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="blank is not zero"):
        xbrl_case.ingest_trial_balance(case, source, "preparer_1", "rev_1")


def test_confirm_parser_unknown_convention_is_rejected(tmp_path: Path) -> None:
    _, case = _created_case(tmp_path)
    source = tmp_path / "trial_balance.csv"
    _write_trial_balance(source, imbalance=True)
    ingested = xbrl_case.ingest_trial_balance(case, source, "preparer_1", "rev_1")

    with pytest.raises(ValueError, match="UNKNOWN cannot be confirmed"):
        xbrl_case.confirm_parser(
            ingested, "UNKNOWN", "preparer_1", ingested["revision_id"]
        )


def test_confirm_parser_unbalanced_trial_balance_is_rejected(tmp_path: Path) -> None:
    _, case = _created_case(tmp_path)
    source = tmp_path / "trial_balance.csv"
    _write_trial_balance(source, imbalance=True)
    case = xbrl_case.ingest_trial_balance(case, source, "preparer_1", "rev_1")

    with pytest.raises(ValueError, match="debit and credit totals do not reconcile"):
        xbrl_case.confirm_parser(
            case,
            "TURNOVER_EXCLUDES_OPENING",
            "preparer_1",
            case["revision_id"],
        )


@pytest.mark.parametrize(
    ("convention", "appears_included"),
    [
        ("TURNOVER_EXCLUDES_OPENING", False),
        ("TURNOVER_INCLUDES_OPENING", False),
        ("TURNOVER_INCLUDES_CLOSING_ENTRIES", True),
        ("SIGNED_BALANCE_ONLY", None),
    ],
)
def test_confirm_parser_records_professional_closing_entry_assessment(
    tmp_path: Path, convention: str, appears_included: bool | None
) -> None:
    _, case = _created_case(tmp_path)
    source = tmp_path / "trial_balance.csv"
    _write_trial_balance(source)
    case = xbrl_case.ingest_trial_balance(case, source, "preparer_1", "rev_1")

    result = xbrl_case.confirm_parser(
        case,
        convention,
        "preparer_1",
        case["revision_id"],
    )

    review = result["trial_balance"]["closing_entries_review"]
    assert review["appears_included"] is appears_included
    assert review["status"] == "USER_CONFIRMED"
    assert review["confirmed_convention"] == convention
    assert review["confirmed_by"] == "preparer_1"
    assert (
        result["trial_balance"]["calibration"]["closing_entries_assessment"] == review
    )


def test_determine_forms_two_small_years_recommends_micro(tmp_path: Path) -> None:
    _, case = _created_case(tmp_path)
    metrics = [
        {"year": 2025, "assets": "200000", "revenue": "400000", "employees": "5"},
        {"year": 2024, "assets": "210000", "revenue": "430000", "employees": "5"},
    ]

    result = xbrl_case.determine_forms(
        case, metrics, _rule_pack(), "preparer_1", "rev_1"
    )

    assert result["form_analysis"]["eligible_forms"] == [
        "MICRO",
        "ABBREVIATED",
        "ORDINARY",
    ]
    assert result["form_analysis"]["recommended_form"] == "MICRO"


def test_determine_forms_micro_exclusion_preserves_abbreviated_option(
    tmp_path: Path,
) -> None:
    payload = _case_payload()
    payload["entity"]["micro_exclusion_flags"] = ["ENTITY_EXCLUDED_BY_STATUTE"]
    case = xbrl_case.create_case(tmp_path / "case", payload, _rule_pack(), "preparer_1")
    metrics = [
        {"year": 2025, "assets": "200000", "revenue": "400000", "employees": "5"},
        {"year": 2024, "assets": "210000", "revenue": "430000", "employees": "5"},
    ]

    result = xbrl_case.determine_forms(
        case, metrics, _rule_pack(), "preparer_1", "rev_1"
    )

    assert result["form_analysis"]["eligible_forms"] == ["ABBREVIATED", "ORDINARY"]
    assert result["form_analysis"]["calculations"]["MICRO"]["reasons"] == [
        "ENTITY_EXCLUDED_BY_STATUTE"
    ]


def _transition_metric(year: int, within: bool, target_form: str) -> dict[str, object]:
    if within:
        return {"year": year, "assets": "1", "revenue": "1", "employees": "1"}
    if target_form == "MICRO":
        return {
            "year": year,
            "assets": "220001",
            "revenue": "440001",
            "employees": "1",
        }
    return {
        "year": year,
        "assets": "5500001",
        "revenue": "11000001",
        "employees": "1",
    }


@pytest.mark.parametrize(
    (
        "prior_form",
        "current_within",
        "prior_within",
        "target_form",
        "expected_eligible",
        "expected_basis",
    ),
    [
        (
            "ABBREVIATED",
            False,
            True,
            "ABBREVIATED",
            True,
            "CONTINUATION_UNTIL_TWO_CONSECUTIVE_EXCEEDANCES",
        ),
        (
            "ABBREVIATED",
            False,
            False,
            "ABBREVIATED",
            False,
            "CONTINUATION_UNTIL_TWO_CONSECUTIVE_EXCEEDANCES",
        ),
        (
            "ORDINARY",
            True,
            False,
            "ABBREVIATED",
            False,
            "ENTRY_REQUIRES_TWO_CONSECUTIVE_YEARS_WITHIN",
        ),
        (
            "ORDINARY",
            True,
            True,
            "ABBREVIATED",
            True,
            "ENTRY_REQUIRES_TWO_CONSECUTIVE_YEARS_WITHIN",
        ),
        (
            "MICRO",
            False,
            True,
            "MICRO",
            True,
            "CONTINUATION_UNTIL_TWO_CONSECUTIVE_EXCEEDANCES",
        ),
    ],
)
def test_determine_forms_applies_entry_and_exit_transition_rules(
    tmp_path: Path,
    prior_form: str,
    current_within: bool,
    prior_within: bool,
    target_form: str,
    expected_eligible: bool,
    expected_basis: str,
) -> None:
    payload = _case_payload()
    payload["entity"]["prior_year_form"] = prior_form
    case = xbrl_case.create_case(tmp_path / "case", payload, _rule_pack(), "preparer_1")

    result = xbrl_case.determine_forms(
        case,
        [
            _transition_metric(2025, current_within, target_form),
            _transition_metric(2024, prior_within, target_form),
        ],
        _rule_pack(),
        "preparer_1",
        case["revision_id"],
    )
    calculation = result["form_analysis"]["calculations"][target_form]

    assert calculation["eligible"] is expected_eligible
    assert calculation["eligibility_basis"] == expected_basis


def test_determine_forms_reports_consequences_of_form_change(tmp_path: Path) -> None:
    payload = _case_payload()
    payload["entity"]["prior_year_form"] = "ABBREVIATED"
    case = xbrl_case.create_case(tmp_path / "case", payload, _rule_pack(), "preparer_1")
    metrics = [
        {"year": 2025, "assets": "1", "revenue": "1", "employees": "1"},
        {"year": 2024, "assets": "1", "revenue": "1", "employees": "1"},
    ]

    result = xbrl_case.determine_forms(
        case, metrics, _rule_pack(), "preparer_1", case["revision_id"]
    )
    ordinary = result["form_analysis"]["consequences_of_changing_form"]["ORDINARY"]

    assert ordinary["change_type"] == "MORE_DETAILED"
    assert ordinary["required_components"] == [
        "BALANCE_SHEET",
        "INCOME_STATEMENT",
        "CASH_FLOW_STATEMENT",
        "NOTES",
    ]
    assert ordinary["effects"] == [
        "CASH_FLOW_STATEMENT_REQUIRED",
        "ORDINARY_NOTES_REQUIRED",
    ]


def test_determine_forms_first_year_reports_current_threshold_failure(
    tmp_path: Path,
) -> None:
    payload = _case_payload()
    payload["entity"]["first_financial_year"] = True
    payload["entity"].pop("prior_year_form")
    payload["entity"].pop("prior_period_start")
    payload["entity"].pop("prior_period_end")
    case = xbrl_case.create_case(tmp_path / "case", payload, _rule_pack(), "preparer_1")
    metrics = [
        {
            "year": 2025,
            "assets": "5500001",
            "revenue": "11000001",
            "employees": "1",
        }
    ]

    result = xbrl_case.determine_forms(
        case, metrics, _rule_pack(), "preparer_1", case["revision_id"]
    )

    assert result["form_analysis"]["eligible_forms"] == ["ORDINARY"]
    assert result["form_analysis"]["calculations"]["ABBREVIATED"]["reasons"] == [
        "CURRENT_YEAR_THRESHOLDS_NOT_MET"
    ]


def test_determine_forms_rejects_duplicate_or_future_metric_years(
    tmp_path: Path,
) -> None:
    _, case = _created_case(tmp_path)
    metrics = [
        {"year": 2099, "assets": "1", "revenue": "1", "employees": "1"},
        {"year": 2099, "assets": "1", "revenue": "1", "employees": "1"},
    ]

    with pytest.raises(ValueError, match="unique record"):
        xbrl_case.determine_forms(
            case, metrics, _rule_pack(), "preparer_1", case["revision_id"]
        )


def test_determine_forms_rejects_metric_year_outside_reporting_window(
    tmp_path: Path,
) -> None:
    _, case = _created_case(tmp_path)
    metrics = [
        {"year": 2025, "assets": "1", "revenue": "1", "employees": "1"},
        {"year": 2023, "assets": "1", "revenue": "1", "employees": "1"},
    ]

    with pytest.raises(ValueError, match="do not align"):
        xbrl_case.determine_forms(
            case, metrics, _rule_pack(), "preparer_1", case["revision_id"]
        )


def test_determine_forms_reports_blank_metric_as_missing_not_zero(
    tmp_path: Path,
) -> None:
    _, case = _created_case(tmp_path)
    metrics = [
        {"year": 2025, "assets": "", "revenue": "1", "employees": "1"},
        {"year": 2024, "assets": "1", "revenue": "1", "employees": "1"},
    ]

    result = xbrl_case.determine_forms(
        case, metrics, _rule_pack(), "preparer_1", case["revision_id"]
    )

    assert result["form_analysis"]["eligible_forms"] == []
    assert result["form_analysis"]["recommended_form"] is None
    assert result["form_analysis"]["missing_fields"] == ["threshold_assets_for_2025"]


def test_determine_forms_rejects_negative_legal_threshold_metrics(
    tmp_path: Path,
) -> None:
    _, case = _created_case(tmp_path)

    with pytest.raises(ValueError, match="cannot be negative: assets"):
        xbrl_case.determine_forms(
            case,
            [
                {
                    "year": 2025,
                    "assets": "-1",
                    "revenue": "1",
                    "employees": "1",
                }
            ],
            _rule_pack(),
            "preparer_1",
            case["revision_id"],
        )


def test_determine_forms_rejects_silent_rule_pack_replacement(tmp_path: Path) -> None:
    _, case = _created_case(tmp_path)
    replacement = _rule_pack()
    replacement["id"] = "IT_CC_2026.2"

    with pytest.raises(ValueError, match="explicit migration"):
        xbrl_case.determine_forms(
            case,
            [],
            replacement,
            "preparer_1",
            case["revision_id"],
        )


def _prepared_case(
    tmp_path: Path, selected_form: str = "ABBREVIATED"
) -> dict[str, object]:
    _, case = _created_case(tmp_path)
    # This compact synthetic helper uses a five-concept catalogue. Dedicated
    # statutory-presentation tests retain the production requirement and cover
    # complete official-network behavior.
    case["statutory_presentation_required"] = False
    source = tmp_path / "trial_balance.csv"
    _write_trial_balance(source)
    case = xbrl_case.ingest_trial_balance(case, source, "preparer_1", "rev_1")
    case = xbrl_case.confirm_parser(
        case,
        "TURNOVER_EXCLUDES_OPENING",
        "preparer_1",
        case["revision_id"],
    )
    metrics = [
        {"year": 2025, "assets": "200000", "revenue": "400000", "employees": "5"},
        {"year": 2024, "assets": "210000", "revenue": "430000", "employees": "5"},
    ]
    case = xbrl_case.determine_forms(
        case, metrics, _rule_pack(), "preparer_1", case["revision_id"]
    )
    case = xbrl_case.select_form(case, selected_form, "preparer_1", case["revision_id"])
    decisions = [
        {
            "account_id": "acc_000001",
            "decision": "ACCEPTED",
            "allocations": [
                {
                    "canonical_line": "SP.ATTIVO.CASSA",
                    "statement_section": "ASSETS",
                    "xbrl_concept": "itcc:Assets",
                    "xbrl_sign_multiplier": "1",
                    "current_amount": "100",
                    "prior_amount": "90",
                    "evidence_status": "OBSERVED",
                }
            ],
        },
        {
            "account_id": "acc_000002",
            "decision": "ACCEPTED",
            "allocations": [
                {
                    "canonical_line": "SP.PASSIVO.DEBITI",
                    "statement_section": "LIABILITIES_EQUITY",
                    "xbrl_concept": "itcc:LiabilitiesEquity",
                    "xbrl_sign_multiplier": "-1",
                    "current_amount": "-100",
                    "prior_amount": "-90",
                    "evidence_status": "USER_CONFIRMED",
                }
            ],
        },
    ]
    case = xbrl_case.apply_mapping_decisions(
        case, decisions, "preparer_1", case["revision_id"]
    )
    return xbrl_case.build_statements(case, "preparer_1", case["revision_id"])


def test_regulatory_migration_invalidates_outputs_but_retains_evidence(
    tmp_path: Path,
) -> None:
    case = _prepared_case(tmp_path)
    source_documents = list(case["source_documents"])

    result = xbrl_case.migrate_regulatory_versions(
        case,
        _regulatory_migration(),
        "studio_admin_1",
        case["revision_id"],
    )

    assert result["state"] == "INPUT_REVIEW"
    assert result["source_documents"] == source_documents
    assert result["trial_balance"]["confirmed_convention"] == (
        "TURNOVER_EXCLUDES_OPENING"
    )
    assert result["selected_form"] is None
    assert result["mappings"] == []
    assert result["statements"] is None
    assert result["rule_pack_versions"]["statutory_rule_pack"] == "IT_CC_2026.1"
    report = result["regulatory_migrations"][-1]
    assert report["from_revision_id"] != report["to_revision_id"]
    assert report["revalidation_status"] == "REQUIRED"
    assert {item["component"] for item in report["invalidated_components"]} >= {
        "mappings",
        "statements",
    }
    assert result["audit_events"][-1]["action"] == ("regulatory_versions_migrated")


def test_regulatory_migration_rejects_caller_supplied_rule_pack_objects(
    tmp_path: Path,
) -> None:
    case = _prepared_case(tmp_path)
    migration = _regulatory_migration()
    migration["statutory_rule_pack"] = _rule_pack()

    with pytest.raises(ValueError, match="controlled rule-pack identifier"):
        xbrl_case.migrate_regulatory_versions(
            case,
            migration,
            "studio_admin_1",
            case["revision_id"],
        )


def test_create_case_requires_pinned_taxonomy_package_checksum(
    tmp_path: Path,
) -> None:
    payload = _case_payload()
    payload.pop("taxonomy_checksum")

    with pytest.raises(ValueError, match="taxonomy package checksum"):
        xbrl_case.create_case(tmp_path / "case", payload, _rule_pack(), "preparer_1")


def test_regulatory_migration_full_validation_result_is_recorded(
    tmp_path: Path,
) -> None:
    case = _prepared_case(tmp_path)
    case = xbrl_case.migrate_regulatory_versions(
        case,
        _regulatory_migration(),
        "studio_admin_1",
        case["revision_id"],
    )

    result = xbrl_case.run_validation(case, "reviewer_1", case["revision_id"])

    report = result["regulatory_migrations"][-1]
    assert result["validation"]["status"] == "FAIL"
    assert report["revalidation_status"] == "FAILED"
    assert report["revalidation_runs"] == [
        {
            "revision_id": result["revision_id"],
            "result": "FAIL",
            "completed_at": report["revalidation_runs"][0]["completed_at"],
        }
    ]


def test_regulatory_migration_cannot_change_an_approved_case(tmp_path: Path) -> None:
    _, case = _created_case(tmp_path)
    case["state"] = "APPROVED"
    case["approval"] = {"snapshot_id": "snap_0001"}
    before = json.loads(json.dumps(case))

    with pytest.raises(ValueError, match="cannot be migrated"):
        xbrl_case.migrate_regulatory_versions(
            case,
            _regulatory_migration(),
            "studio_admin_1",
            case["revision_id"],
        )

    assert case == before


def test_statement_output_records_complete_reproducibility_context(
    tmp_path: Path,
) -> None:
    case = _prepared_case(tmp_path)

    context = case["statements"]["computation_context"]

    assert set(context) == {
        "case_id",
        "revision_id",
        "input_manifest_hash",
        "mapping_version",
        "rule_pack_versions",
        "regulatory_rule_pack_checksums",
        "filing_campaign_year",
        "taxonomy_checksum",
        "model_version",
        "template_version",
        "computed_at",
    }
    assert context["case_id"] == case["case_id"]
    assert context["revision_id"] == case["revision_id"]
    assert len(context["input_manifest_hash"]) == 64
    assert len(context["mapping_version"]) == 64
    assert context["rule_pack_versions"] == case["rule_pack_versions"]
    assert context["regulatory_rule_pack_checksums"] == {
        "statutory_rule_pack": case["rule_pack_checksum"],
        "oic_rule_pack": case["oic_rule_pack_checksum"],
        "filing_instruction_pack": case["filing_instruction_pack_checksum"],
        "disclosure_rule_pack": None,
        "statutory_presentation_rule_pack": None,
        "schedule_taxonomy_adapter_rule_pack": None,
    }
    assert context["filing_campaign_year"] == 2026
    assert context["taxonomy_checksum"] == case["taxonomy_checksum"]
    assert context["model_version"] is None
    assert context["template_version"] == "statement-engine-v1"


def test_apply_mapping_decisions_unbalanced_split_is_rejected(tmp_path: Path) -> None:
    _, case = _created_case(tmp_path)
    source = tmp_path / "trial_balance.csv"
    _write_trial_balance(source)
    case = xbrl_case.ingest_trial_balance(case, source, "preparer_1", "rev_1")
    case = xbrl_case.confirm_parser(
        case, "TURNOVER_EXCLUDES_OPENING", "preparer_1", case["revision_id"]
    )
    case["selected_form"] = "ABBREVIATED"
    case["statutory_presentation_required"] = False
    decision = {
        "account_id": "acc_000001",
        "decision": "ACCEPTED",
        "allocations": [
            {
                "canonical_line": "SP.ATTIVO.CASSA",
                "statement_section": "ASSETS",
                "current_amount": "99",
                "prior_amount": "90",
                "evidence_status": "OBSERVED",
            }
        ],
    }

    with pytest.raises(ValueError, match="does not balance"):
        xbrl_case.apply_mapping_decisions(
            case, [decision], "preparer_1", case["revision_id"]
        )


def test_mapped_taxonomy_concept_requires_explicit_sign_convention(
    tmp_path: Path,
) -> None:
    _, case = _created_case(tmp_path)
    source = tmp_path / "trial_balance.csv"
    _write_trial_balance(source)
    case = xbrl_case.ingest_trial_balance(case, source, "preparer_1", "rev_1")
    case = xbrl_case.confirm_parser(
        case, "TURNOVER_EXCLUDES_OPENING", "preparer_1", case["revision_id"]
    )
    case["selected_form"] = "ABBREVIATED"
    case["statutory_presentation_required"] = False
    decision = {
        "account_id": "acc_000001",
        "decision": "ACCEPTED",
        "allocations": [
            {
                "canonical_line": "SP.ATTIVO.CASSA",
                "statement_section": "ASSETS",
                "xbrl_concept": "itcc:Assets",
                "current_amount": "100",
                "prior_amount": "90",
                "evidence_status": "OBSERVED",
            }
        ],
    }

    with pytest.raises(ValueError, match="explicit sign multiplier"):
        xbrl_case.apply_mapping_decisions(
            case, [decision], "preparer_1", case["revision_id"]
        )


def test_reviewed_presentation_adjustment_preserves_precision_and_exposes_rounding(
    tmp_path: Path,
) -> None:
    case = _prepared_case(tmp_path)
    case = xbrl_case.record_adjustments(
        case,
        [
            {
                "adjustment_id": "reclass_receivable",
                "reason": "Reviewed presentation reclassification",
                "lines": [
                    {
                        "canonical_line": "SP.ATTIVO.CASSA",
                        "statement_section": "ASSETS",
                        "xbrl_concept": "itcc:Assets",
                        "xbrl_sign_multiplier": "1",
                        "current_amount": "-0.50",
                        "prior_amount": "-0.50",
                    },
                    {
                        "canonical_line": "SP.ATTIVO.CREDITI",
                        "statement_section": "ASSETS",
                        "xbrl_concept": "itcc:Receivables",
                        "xbrl_sign_multiplier": "1",
                        "current_amount": "0.50",
                        "prior_amount": "0.50",
                    },
                ],
            }
        ],
        "reviewer_1",
        case["revision_id"],
    )

    result = xbrl_case.build_statements(case, "preparer_1", case["revision_id"])

    cash = next(
        fact
        for fact in result["statements"]["facts"]
        if fact["key"] == "SP.ATTIVO.CASSA"
    )
    rounding = next(
        item
        for item in result["statements"]["rounding_adjustments"]
        if item["statement_section"] == "ASSETS" and item["period"] == "current"
    )
    assert cash["current_value"] == "99.50"
    assert cash["derivation"]["adjustment_refs"] == ["reclass_receivable_1"]
    assert rounding["amount"] == "-1.00"
    assert rounding["repairs_substantive_imbalance"] is False


def test_unbalanced_presentation_adjustment_is_rejected(tmp_path: Path) -> None:
    case = _prepared_case(tmp_path)

    with pytest.raises(ValueError, match="must balance"):
        xbrl_case.record_adjustments(
            case,
            [
                {
                    "adjustment_id": "invalid_adjustment",
                    "reason": "Attempted one-sided change",
                    "lines": [
                        {
                            "canonical_line": "SP.ATTIVO.CASSA",
                            "statement_section": "ASSETS",
                            "current_amount": "1",
                            "prior_amount": "1",
                        },
                        {
                            "canonical_line": "SP.ATTIVO.CREDITI",
                            "statement_section": "ASSETS",
                            "current_amount": "0",
                            "prior_amount": "0",
                        },
                    ],
                }
            ],
            "reviewer_1",
            case["revision_id"],
        )


def test_nil_taxonomy_fact_requires_explicit_reviewed_reason(tmp_path: Path) -> None:
    case = _prepared_case(tmp_path)

    with pytest.raises(ValueError, match="explicit reviewed reason"):
        xbrl_case.record_taxonomy_facts(
            case,
            [
                {
                    "fact_id": "optional_amount",
                    "xbrl_concept": "itcc:OptionalAmount",
                    "period": "current_instant",
                    "fact_type": "NIL",
                    "status": "USER_CONFIRMED",
                    "nil_reason": "Not applicable",
                }
            ],
            "reviewer_1",
            case["revision_id"],
        )


def test_duplicate_taxonomy_fact_for_same_context_is_rejected(tmp_path: Path) -> None:
    case = _prepared_case(tmp_path)
    duplicate = {
        "xbrl_concept": "itcc:OptionalAmount",
        "period": "current_instant",
        "fact_type": "MONETARY",
        "value": "10",
        "currency": "EUR",
        "status": "USER_CONFIRMED",
        "source_refs": [case["canonical_facts"][0]["fact_id"]],
    }

    with pytest.raises(ValueError, match="Conflicting duplicate taxonomy fact"):
        xbrl_case.record_taxonomy_facts(
            case,
            [
                {**duplicate, "fact_id": "optional_amount_1"},
                {**duplicate, "fact_id": "optional_amount_2"},
            ],
            "reviewer_1",
            case["revision_id"],
        )


def test_non_eur_taxonomy_fact_is_rejected(tmp_path: Path) -> None:
    case = _prepared_case(tmp_path)

    with pytest.raises(ValueError, match="must use EUR"):
        xbrl_case.record_taxonomy_facts(
            case,
            [
                {
                    "fact_id": "optional_amount",
                    "xbrl_concept": "itcc:OptionalAmount",
                    "period": "current_instant",
                    "fact_type": "MONETARY",
                    "value": "10",
                    "currency": "USD",
                    "status": "USER_CONFIRMED",
                    "source_refs": ["src_1"],
                }
            ],
            "reviewer_1",
            case["revision_id"],
        )


def _negative_answers() -> list[dict[str, object]]:
    keys = [
        "guarantees_and_commitments",
        "contingent_liabilities",
        "related_party_transactions",
        "off_balance_sheet_arrangements",
        "derivatives",
        "post_closing_events",
        "accounting_policy_changes",
        "prior_period_errors",
        "going_concern_uncertainties",
        "non_market_transactions",
        "double_format_events",
    ]
    return [
        {
            "key": key,
            "status": "NOT_APPLICABLE_CONFIRMED",
            "reason": "Explicit annual confirmation",
        }
        for key in keys
    ]


def _ready_case(tmp_path: Path) -> dict[str, object]:
    case = _prepared_case(tmp_path)
    case = _complete_disclosures_and_preview(case, tmp_path)
    case = xbrl_case.run_validation(case, "reviewer_1", case["revision_id"])
    warning = next(
        issue
        for issue in case["validation"]["issues"]
        if issue["rule_id"] == "INPUT.PRIOR_XBRL_RECOMMENDED"
    )
    case = xbrl_case.record_issue_reviews(
        case,
        [
            {
                "issue_id": warning["issue_id"],
                "action": "ACKNOWLEDGED",
                "reason": "Prior filing was unavailable and the comparative was reviewed.",
            }
        ],
        "reviewer_1",
        case["revision_id"],
    )
    case = xbrl_case.create_preview(
        case, tmp_path / "reviewed-preview.html", "reviewer_1", case["revision_id"]
    )
    case = xbrl_case.run_validation(case, "reviewer_1", case["revision_id"])
    return case


def _passing_xbrl_validator(
    instance: Path,
    report: Path,
    taxonomy_package: Path | None,
    expected_taxonomy_sha256: str | None,
) -> dict[str, object]:
    result = {
        "status": "PASS",
        "processor": "test-validator",
        "taxonomy_package_sha256": expected_taxonomy_sha256,
        "instance": instance.name,
        "package": taxonomy_package.name if taxonomy_package else None,
    }
    report.write_text(json.dumps(result) + "\n", encoding="utf-8")
    return result


def _reviewer_declaration() -> dict[str, bool]:
    return {
        "entity_period_confirmed": True,
        "form_confirmed": True,
        "evidence_reviewed": True,
        "preview_reviewed": True,
        "filing_boundary_understood": True,
        "rendered_output_confirmed": True,
        "outstanding_warnings_understood": True,
    }


def _approved_case(tmp_path: Path) -> dict[str, object]:
    case = _ready_case(tmp_path)
    catalogue = tmp_path / "approval-catalogue.json"
    _write_catalogue(catalogue, "a" * 64)
    package = tmp_path / "approval-taxonomy.zip"
    package.write_bytes(b"test taxonomy package")
    case = xbrl_case.prepare_xbrl_review(
        case,
        catalogue,
        package,
        tmp_path / "approval-xbrl-review",
        "reviewer_1",
        case["revision_id"],
        validator=_passing_xbrl_validator,
    )
    return xbrl_case.approve_case(
        case, "reviewer_1", case["revision_id"], _reviewer_declaration()
    )


def test_issue_warning_requires_auditable_reviewer_acknowledgement(
    tmp_path: Path,
) -> None:
    case = _prepared_case(tmp_path)
    case = _complete_disclosures_and_preview(case, tmp_path)
    case = xbrl_case.run_validation(case, "reviewer_1", case["revision_id"])
    assert case["validation"]["computation_context"]["revision_id"] == (
        case["revision_id"]
    )
    warning = next(
        issue
        for issue in case["validation"]["issues"]
        if issue["rule_id"] == "INPUT.PRIOR_XBRL_RECOMMENDED"
    )

    result = xbrl_case.record_issue_reviews(
        case,
        [
            {
                "issue_id": warning["issue_id"],
                "action": "ACKNOWLEDGED",
                "reason": "The unavailable prior filing was considered during review.",
            }
        ],
        "reviewer_1",
        case["revision_id"],
    )

    assert result["review_decisions"][0]["issue_fingerprint"] == warning["fingerprint"]
    assert result["validation"]["issues"][0]["review_status"] == "ACKNOWLEDGED"
    assert result["preview"] is None
    resolution = next(
        event for event in result["audit_events"] if event["action"] == "issue_resolved"
    )
    assert resolution["details"] == {
        "issue_id": warning["issue_id"],
        "decision_id": result["review_decisions"][0]["decision_id"],
        "resolution": "ACKNOWLEDGED",
    }


def test_structural_blocker_cannot_be_overridden() -> None:
    case = {
        "case_id": "case_1",
        "revision_id": "rev_1",
        "validation": {
            "validated_revision_id": "rev_1",
            "issues": [
                {
                    "issue_id": "iss_0001",
                    "severity": "BLOCKER",
                    "rule_id": "STATEMENT.BALANCE_SHEET",
                    "message": "Assets do not equal liabilities and equity",
                    "affected_facts": [],
                    "source_refs": [],
                    "override_allowed": False,
                }
            ],
        },
        "review_decisions": [],
        "audit_events": [],
        "updated_at": "2026-01-01T00:00:00+00:00",
    }

    with pytest.raises(ValueError, match="cannot be overridden"):
        xbrl_case.record_issue_reviews(
            case,
            [
                {
                    "issue_id": "iss_0001",
                    "action": "OVERRIDDEN",
                    "reason": "Professional judgment would otherwise accept this.",
                }
            ],
            "reviewer_1",
            "rev_1",
        )


def _complete_disclosures_and_preview(
    case: dict[str, object], tmp_path: Path
) -> dict[str, object]:
    case = xbrl_case.activate_disclosures(
        case,
        _disclosure_rule_pack(),
        "preparer_1",
        case["revision_id"],
    )
    trigger_source_ref = case["canonical_facts"][0]["fact_id"]
    case = xbrl_case.record_disclosure_trigger_decisions(
        case,
        [
            {
                "flag": flag,
                "status": "NOT_APPLICABLE_CONFIRMED",
                "reason": "Synthetic annual applicability review",
                "source_refs": [trigger_source_ref],
            }
            for flag in sorted(
                xbrl_case.manual_disclosure_flags(case["disclosure_rule_pack"])
            )
        ],
        "reviewer_1",
        case["revision_id"],
    )
    negative_keys = {item["key"] for item in _negative_answers()}
    answers = [
        {
            "key": question["answer_key"],
            "status": (
                "NOT_APPLICABLE_CONFIRMED"
                if question["answer_key"] in negative_keys
                else "ACCEPTED"
            ),
            "value": False if question["answer_key"] in negative_keys else True,
            "reason": "Synthetic reviewed fixture",
        }
        for question in case["questionnaire"]
        if question["state"] != "NOT_TRIGGERED"
    ]
    case = xbrl_case.record_disclosure_answers(
        case, answers, "preparer_1", case["revision_id"]
    )
    section_ids = {
        item["note_section"]
        for item in case["disclosure_coverage"]["coverage"]
        if item["triggered"]
    }
    fact_ref = case["canonical_facts"][0]["fact_id"]
    blocks = []
    for position, section_id in enumerate(sorted(section_ids), start=1):
        sentence = f"Sezione {section_id} verificata sui dati accettati."
        blocks.append(
            {
                "block_id": f"block_{position:02d}",
                "section_id": section_id,
                "text": sentence,
                "status": "ACCEPTED",
                "xbrl_concept": (
                    "itcc:NotesText"
                    if position == 1
                    else f"itcc:NotesText{position:02d}"
                ),
                "claims": [
                    {
                        "sentence": sentence,
                        "kind": "FACTUAL",
                        "source_refs": [fact_ref],
                        "semantic_support": {
                            "status": "SUPPORTED",
                            "reason": "The reviewer confirmed the sentence against the cited fact.",
                        },
                    }
                ],
            }
        )
    case = xbrl_case.record_narrative_blocks(
        case, blocks, "reviewer_1", case["revision_id"]
    )
    return xbrl_case.create_preview(
        case, tmp_path / "preview.html", "reviewer_1", case["revision_id"]
    )


def test_oic_pack_selection_changes_required_professional_review_questions(
    tmp_path: Path,
) -> None:
    def questions_for(
        directory: str,
        period_start: str,
        period_end: str,
        prior_start: str,
        prior_end: str,
        oic_pack: str,
        statutory_pack: dict[str, object],
    ) -> set[str]:
        payload = _case_payload()
        payload["case_id"] = f"case_{directory}"
        payload["period"] = {"start": period_start, "end": period_end}
        payload["entity"]["prior_period_start"] = prior_start
        payload["entity"]["prior_period_end"] = prior_end
        payload["oic_rule_pack"] = oic_pack
        case = xbrl_case.create_case(
            tmp_path / directory, payload, statutory_pack, "preparer_1"
        )
        case["selected_form"] = "ABBREVIATED"
        case["statements"] = {"facts": []}
        case = xbrl_case.activate_disclosures(
            case,
            _disclosure_rule_pack(),
            "reviewer_1",
            case["revision_id"],
        )
        return {
            question["answer_key"]
            for question in case["questionnaire"]
            if str(question["answer_key"]).startswith("oic")
        }

    historical = questions_for(
        "historical",
        "2023-01-01",
        "2023-12-31",
        "2022-01-01",
        "2022-12-31",
        "OIC_2016_2023.1",
        _historical_rule_pack(),
    )
    current = questions_for(
        "current",
        "2025-01-01",
        "2025-12-31",
        "2024-01-01",
        "2024-12-31",
        "OIC_2024_2025.1",
        _rule_pack(),
    )
    amended = questions_for(
        "amended",
        "2026-01-01",
        "2026-12-31",
        "2025-01-01",
        "2025-12-31",
        "OIC_2026.1",
        _rule_pack(),
    )

    assert historical == set()
    assert current == {"oic34_revenue_policy_review"}
    assert amended == {
        "oic34_revenue_policy_review",
        "oic_2025_amendments_review",
    }


def test_open_structured_disclosures_enter_data_gaps_state(tmp_path: Path) -> None:
    case = _prepared_case(tmp_path)

    result = xbrl_case.activate_disclosures(
        case,
        _disclosure_rule_pack(),
        "preparer_1",
        case["revision_id"],
    )
    trigger_source_ref = result["canonical_facts"][0]["fact_id"]
    result = xbrl_case.record_disclosure_trigger_decisions(
        result,
        [
            {
                "flag": flag,
                "status": "NOT_APPLICABLE_CONFIRMED",
                "reason": "Synthetic annual applicability review",
                "source_refs": [trigger_source_ref],
            }
            for flag in sorted(
                xbrl_case.manual_disclosure_flags(result["disclosure_rule_pack"])
            )
        ],
        "reviewer_1",
        result["revision_id"],
    )

    assert result["state"] == "DATA_GAPS"
    assert any(question["state"] == "OPEN" for question in result["questionnaire"])


def test_reviewed_manual_trigger_activates_relevant_disclosure_question(
    tmp_path: Path,
) -> None:
    case = _prepared_case(tmp_path)
    case = xbrl_case.activate_disclosures(
        case,
        _disclosure_rule_pack(),
        "preparer_1",
        case["revision_id"],
    )
    fact_ref = case["canonical_facts"][0]["fact_id"]

    result = xbrl_case.record_disclosure_trigger_decisions(
        case,
        [
            {
                "flag": "EMPLOYEES_OR_BODIES_PRESENT",
                "status": "TRIGGERED",
                "reason": "Payroll evidence indicates employees during the year.",
                "source_refs": [fact_ref],
            }
        ],
        "reviewer_1",
        case["revision_id"],
    )

    assert "EMPLOYEES_OR_BODIES_PRESENT" in result["disclosure_trigger_flags"]
    assert any(
        item["rule_id"] == "IT.CC.EMPLOYEES_CORPORATE_BODIES" and item["triggered"]
        for item in result["disclosure_coverage"]["coverage"]
    )


def test_unreviewed_manual_disclosure_flags_block_validation(tmp_path: Path) -> None:
    case = _prepared_case(tmp_path)
    case = xbrl_case.activate_disclosures(
        case,
        _disclosure_rule_pack(),
        "preparer_1",
        case["revision_id"],
    )

    result = xbrl_case.validate_case(case)

    assert "DISCLOSURE.MANUAL_TRIGGER_REVIEW_REQUIRED" in {
        item["rule_id"] for item in result["issues"]
    }


def test_completed_structured_inputs_enter_note_draft_state(tmp_path: Path) -> None:
    case = _prepared_case(tmp_path)

    result = _complete_disclosures_and_preview(case, tmp_path)

    assert result["state"] == "NOTE_DRAFT"
    assert result["narrative_blocks"]


def test_validate_case_missing_negative_confirmations_is_blocked(
    tmp_path: Path,
) -> None:
    case = _prepared_case(tmp_path)

    result = xbrl_case.validate_case(case)

    assert result["status"] == "FAIL"
    assert "DISCLOSURE.NEGATIVE_CONFIRMATIONS" in {
        issue["rule_id"] for issue in result["issues"]
    }


def test_approve_case_creates_hash_bound_immutable_snapshot(tmp_path: Path) -> None:
    case = _approved_case(tmp_path)

    snapshot_hash = case["approval"]["snapshot_hash"]

    assert case["state"] == "APPROVED"
    assert len(snapshot_hash) == 64
    assert case["approval"]["snapshot"]["revision_id"] == case["revision_id"]
    assert case["approval"]["snapshot"]["xbrl_review"]["status"] == "PASS"


def test_approval_requires_passing_local_xbrl_review_of_current_content(
    tmp_path: Path,
) -> None:
    case = _ready_case(tmp_path)

    with pytest.raises(ValueError, match="passing local XBRL review"):
        xbrl_case.approve_case(
            case,
            "reviewer_1",
            case["revision_id"],
            _reviewer_declaration(),
        )


def test_prepare_xbrl_review_binds_render_and_processor_report(
    tmp_path: Path,
) -> None:
    case = _ready_case(tmp_path)
    catalogue = tmp_path / "catalogue.json"
    _write_catalogue(catalogue, "a" * 64)
    package = tmp_path / "taxonomy.zip"
    package.write_bytes(b"test taxonomy package")

    result = xbrl_case.prepare_xbrl_review(
        case,
        catalogue,
        package,
        tmp_path / "xbrl-review",
        "reviewer_1",
        case["revision_id"],
        validator=_passing_xbrl_validator,
    )

    assert result["state"] == "READY_FOR_REVIEW"
    assert result["xbrl_review"]["status"] == "PASS"
    assert len(result["xbrl_review"]["candidate_sha256"]) == 64
    assert len(result["xbrl_review"]["validation_report_sha256"]) == 64
    assert result["validation"]["validated_revision_id"] == result["revision_id"]


def test_prepare_xbrl_review_rejects_validator_that_modifies_candidate(
    tmp_path: Path,
) -> None:
    case = _ready_case(tmp_path)
    catalogue = tmp_path / "catalogue.json"
    _write_catalogue(catalogue, "a" * 64)
    package = tmp_path / "taxonomy.zip"
    package.write_bytes(b"test taxonomy package")

    def modifying_validator(
        instance: Path,
        report: Path,
        taxonomy_package: Path | None,
        expected_taxonomy_sha256: str | None,
    ) -> dict[str, object]:
        instance.write_bytes(instance.read_bytes() + b"<!-- modified -->")
        return _passing_xbrl_validator(
            instance,
            report,
            taxonomy_package,
            expected_taxonomy_sha256,
        )

    with pytest.raises(ValueError, match="modified the rendered XBRL"):
        xbrl_case.prepare_xbrl_review(
            case,
            catalogue,
            package,
            tmp_path / "xbrl-review",
            "reviewer_1",
            case["revision_id"],
            validator=modifying_validator,
        )


def test_failed_xbrl_review_job_leaves_no_partial_output_and_can_retry(
    tmp_path: Path,
) -> None:
    case = _ready_case(tmp_path)
    catalogue = tmp_path / "catalogue.json"
    _write_catalogue(catalogue, "a" * 64)
    package = tmp_path / "taxonomy.zip"
    package.write_bytes(b"test taxonomy package")
    output = tmp_path / "retryable-xbrl-review"

    def failing_validator(
        instance: Path,
        report: Path,
        taxonomy_package: Path | None,
        expected_taxonomy_sha256: str | None,
    ) -> dict[str, object]:
        report.write_text('{"status":"FAIL"}\n', encoding="utf-8")
        raise RuntimeError("processor interrupted")

    with pytest.raises(RuntimeError, match="processor interrupted"):
        xbrl_case.prepare_xbrl_review(
            case,
            catalogue,
            package,
            output,
            "reviewer_1",
            case["revision_id"],
            validator=failing_validator,
        )

    assert not output.exists()
    result = xbrl_case.prepare_xbrl_review(
        case,
        catalogue,
        package,
        output,
        "reviewer_1",
        case["revision_id"],
        validator=_passing_xbrl_validator,
    )

    assert result["xbrl_review"]["status"] == "PASS"
    assert sorted(path.name for path in output.iterdir()) == [
        "local-xbrl-validation.json",
        "review-candidate.xbrl",
    ]


def test_xbrl_review_rejects_symbolic_link_in_output_ancestor(
    tmp_path: Path,
) -> None:
    case = _ready_case(tmp_path)
    catalogue = tmp_path / "catalogue.json"
    _write_catalogue(catalogue, "a" * 64)
    package = tmp_path / "taxonomy.zip"
    package.write_bytes(b"test taxonomy package")
    outside = tmp_path / "outside"
    outside.mkdir()
    linked_parent = tmp_path / "artifacts"
    linked_parent.symlink_to(outside, target_is_directory=True)

    with pytest.raises(ValueError, match="symbolic-link components"):
        xbrl_case.prepare_xbrl_review(
            case,
            catalogue,
            package,
            linked_parent / "review",
            "reviewer_1",
            case["revision_id"],
            validator=_passing_xbrl_validator,
        )

    assert list(outside.iterdir()) == []


def test_post_approval_form_change_invalidates_prior_approval(tmp_path: Path) -> None:
    case = _approved_case(tmp_path)

    result = xbrl_case.select_form(case, "ORDINARY", "reviewer_1", case["revision_id"])

    assert result["approval"] is None
    assert result["xbrl_review"] is None
    assert len(result["approval_snapshots"]) == 1
    assert result["approval_snapshots"][0]["invalidated_by_action"] == "form_selected"


def _write_catalogue(path: Path, checksum: str) -> None:
    path.write_text(
        json.dumps(
            {
                "schema_version": 2,
                "taxonomy_id": "PCI_2018-11-04",
                "taxonomy_package_sha256": checksum,
                "entry_points": {
                    "ORDINARY": "https://example.invalid/ordinary.xsd",
                    "ABBREVIATED": "https://example.invalid/abbreviated.xsd",
                    "MICRO": "https://example.invalid/micro.xsd",
                },
                "namespaces": {
                    "itcc": "https://example.invalid/itcc",
                    "itcc-ci": "https://example.invalid/itcc-ci",
                },
                "concepts": [
                    {
                        "qname": "itcc:Assets",
                        "type": "xbrli:monetaryItemType",
                        "period_type": "instant",
                        "abstract": False,
                        "is_item": True,
                        "is_tuple": False,
                    },
                    {
                        "qname": "itcc:LiabilitiesEquity",
                        "type": "xbrli:monetaryItemType",
                        "period_type": "instant",
                        "abstract": False,
                        "is_item": True,
                        "is_tuple": False,
                    },
                    {
                        "qname": "itcc:NotesText",
                        "type": "nonnum:textBlockItemType",
                        "period_type": "duration",
                        "abstract": False,
                        "is_item": True,
                        "is_tuple": False,
                    },
                    {
                        "qname": "itcc-ci:CommentoInformazioniCalceAlloStatoPatrimonialeMicro",
                        "type": "nonnum:textBlockItemType",
                        "period_type": "instant",
                        "abstract": False,
                        "is_item": True,
                        "is_tuple": False,
                        "forms": ["MICRO"],
                    },
                    *[
                        {
                            "qname": f"itcc:NotesText{position:02d}",
                            "type": "nonnum:textBlockItemType",
                            "period_type": "duration",
                            "abstract": False,
                            "is_item": True,
                            "is_tuple": False,
                        }
                        for position in range(2, 15)
                    ],
                    {
                        "qname": "itcc:DimensionText",
                        "type": "nonnum:textBlockItemType",
                        "period_type": "duration",
                        "abstract": False,
                        "is_item": True,
                        "is_tuple": False,
                        "nillable": False,
                    },
                    {
                        "qname": "itcc:OptionalAmount",
                        "type": "xbrli:monetaryItemType",
                        "period_type": "instant",
                        "abstract": False,
                        "is_item": True,
                        "is_tuple": False,
                        "nillable": True,
                    },
                    {
                        "qname": "itcc:RegionAxis",
                        "period_type": "duration",
                        "abstract": True,
                        "is_item": True,
                        "is_tuple": False,
                        "is_dimension_item": True,
                    },
                    {
                        "qname": "itcc:ItalyMember",
                        "period_type": "duration",
                        "abstract": True,
                        "is_item": True,
                        "is_tuple": False,
                        "is_dimension_item": False,
                        "is_hypercube_item": False,
                    },
                ],
            }
        ),
        encoding="utf-8",
    )


def test_render_xbrl_approved_case_uses_current_and_comparative_contexts(
    tmp_path: Path,
) -> None:
    case = _approved_case(tmp_path)
    catalogue = tmp_path / "catalogue.json"
    _write_catalogue(catalogue, "a" * 64)

    xml = xbrl_case.render_xbrl(case, catalogue)

    root = etree.fromstring(xml)
    context_ids = {
        element.get("id")
        for element in root.findall("{http://www.xbrl.org/2003/instance}context")
    }
    assert context_ids == {
        "current_duration",
        "current_instant",
        "prior_duration",
        "prior_instant",
    }
    assert len(root.findall("{https://example.invalid/itcc}Assets")) == 2
    liability_values = {
        element.get("contextRef"): Decimal(str(element.text))
        for element in root.findall("{https://example.invalid/itcc}LiabilitiesEquity")
    }
    assert liability_values == {
        "current_instant": Decimal("100"),
        "prior_instant": Decimal("90"),
    }
    prior_duration = root.xpath(
        "xbrli:context[@id='prior_duration']/xbrli:period",
        namespaces={"xbrli": "http://www.xbrl.org/2003/instance"},
    )[0]
    assert (
        prior_duration.findtext("{http://www.xbrl.org/2003/instance}startDate")
        == "2024-01-01"
    )
    assert (
        prior_duration.findtext("{http://www.xbrl.org/2003/instance}endDate")
        == "2024-12-31"
    )
    rendered_facts = root.xpath("//*[@contextRef]")
    fact_ids = [element.get("id") for element in rendered_facts]
    assert all(fact_ids)
    assert len(fact_ids) == len(set(fact_ids))


def test_previous_year_date_handles_leap_day_without_invalid_context() -> None:
    result = xbrl_case._previous_year_date(xbrl_case.date(2024, 2, 29))

    assert result.isoformat() == "2023-02-28"


def test_render_xbrl_unverified_catalogue_is_rejected(tmp_path: Path) -> None:
    case = _approved_case(tmp_path)
    catalogue = tmp_path / "catalogue.json"
    _write_catalogue(catalogue, "UNVERIFIED")

    with pytest.raises(ValueError, match="not bound to a verified"):
        xbrl_case.render_xbrl(case, catalogue)


def test_render_xbrl_rejects_non_item_tuple_concept(tmp_path: Path) -> None:
    case = _approved_case(tmp_path)
    catalogue = tmp_path / "catalogue.json"
    _write_catalogue(catalogue, "a" * 64)
    catalogue_payload = json.loads(catalogue.read_text(encoding="utf-8"))
    catalogue_payload["concepts"].append(
        {
            "qname": "itcc:MovementTuple",
            "type": "xbrli:stringItemType",
            "period_type": None,
            "abstract": False,
            "is_item": False,
            "is_tuple": True,
        }
    )
    catalogue.write_text(json.dumps(catalogue_payload), encoding="utf-8")
    snapshot = case["approval"]["snapshot"]
    snapshot["canonical_facts"][0]["xbrl_concept"] = "itcc:MovementTuple"
    case["approval"]["snapshot_hash"] = hashlib.sha256(
        xbrl_case._canonical_json(snapshot)
    ).hexdigest()

    with pytest.raises(ValueError, match="non-item taxonomy concept"):
        xbrl_case.render_xbrl(case, catalogue)


def test_render_xbrl_emits_repeated_tuple_occurrences(tmp_path: Path) -> None:
    case = _approved_case(tmp_path)
    catalogue = tmp_path / "catalogue.json"
    _write_catalogue(catalogue, "a" * 64)
    catalogue_payload = json.loads(catalogue.read_text(encoding="utf-8"))
    catalogue_payload["concepts"].extend(
        [
            {
                "qname": "itcc:MovementTuple",
                "type": "xbrli:stringItemType",
                "period_type": None,
                "abstract": False,
                "is_item": False,
                "is_tuple": True,
            },
            {
                "qname": "itcc:MovementAmount",
                "type": "xbrli:monetaryItemType",
                "period_type": "instant",
                "abstract": False,
                "is_item": True,
                "is_tuple": False,
            },
        ]
    )
    catalogue.write_text(json.dumps(catalogue_payload), encoding="utf-8")
    snapshot = case["approval"]["snapshot"]
    snapshot["schedule_taxonomy_facts"] = [
        {
            "fact_id": f"tuple_amount_{position}",
            "xbrl_concept": "itcc:MovementAmount",
            "period": "current_instant",
            "fact_type": "MONETARY",
            "value": value,
            "status": "DERIVED",
            "dimensions": {},
            "tuple_path": ["itcc:MovementTuple"],
            "tuple_instance_id": f"movement:{position}",
        }
        for position, value in ((1, "10"), (2, "20"))
    ]
    case["approval"]["snapshot_hash"] = hashlib.sha256(
        xbrl_case._canonical_json(snapshot)
    ).hexdigest()

    root = etree.fromstring(xbrl_case.render_xbrl(case, catalogue))

    tuples = root.findall("{https://example.invalid/itcc}MovementTuple")
    assert len(tuples) == 2
    assert [
        tuple_element.findtext("{https://example.invalid/itcc}MovementAmount")
        for tuple_element in tuples
    ] == ["10.00", "20.00"]


def test_stale_revision_is_rejected_before_mutation(tmp_path: Path) -> None:
    _, case = _created_case(tmp_path)

    with pytest.raises(ValueError, match="Stale revision"):
        xbrl_case.determine_forms(case, [], _rule_pack(), "preparer_1", "rev_999")


def _write_prior_xbrl(path: Path, entity_identifier: str = "IT00000000000") -> None:
    path.write_text(
        f"""<?xml version="1.0" encoding="UTF-8"?>
<xbrli:xbrl xmlns:xbrli="http://www.xbrl.org/2003/instance"
 xmlns:link="http://www.xbrl.org/2003/linkbase"
 xmlns:xlink="http://www.w3.org/1999/xlink"
 xmlns:iso4217="http://www.xbrl.org/2003/iso4217"
 xmlns:itcc-ci="http://www.infocamere.it/itnn/fr/itcc/ci/2018-11-04">
 <link:schemaRef xlink:type="simple" xlink:href="2018-11-04/itcc-ci-abb-2018-11-04.xsd"/>
 <xbrli:context id="prior-instant">
  <xbrli:entity><xbrli:identifier scheme="http://www.registroimprese.it">{entity_identifier}</xbrli:identifier></xbrli:entity>
  <xbrli:period><xbrli:instant>2024-12-31</xbrli:instant></xbrli:period>
 </xbrli:context>
 <xbrli:unit id="EUR"><xbrli:measure>iso4217:EUR</xbrli:measure></xbrli:unit>
 <itcc-ci:TotaleAttivo contextRef="prior-instant" unitRef="EUR" decimals="0">90</itcc-ci:TotaleAttivo>
</xbrli:xbrl>
""",
        encoding="utf-8",
    )


def _eur_unit_record() -> dict[str, object]:
    return {
        "kind": "MEASURE",
        "measure": {
            "namespace": "http://www.xbrl.org/2003/iso4217",
            "local_name": "EUR",
        },
    }


def test_ingest_prior_xbrl_preserves_source_and_trial_balance_manifests(
    tmp_path: Path,
) -> None:
    _, case = _created_case(tmp_path)
    prior = tmp_path / "prior.xbrl"
    _write_prior_xbrl(prior)
    case = xbrl_case.ingest_prior_xbrl(case, prior, "preparer_1", case["revision_id"])
    source = tmp_path / "trial_balance.csv"
    _write_trial_balance(source)

    result = xbrl_case.ingest_trial_balance(
        case, source, "preparer_1", case["revision_id"]
    )

    assert {item["purpose"] for item in result["source_documents"]} == {
        "PRIOR_XBRL",
        "TRIAL_BALANCE",
    }
    assert result["prior_xbrl"]["matching_context_ids"] == ["prior-instant"]
    assert result["prior_xbrl"]["facts"][0]["source_anchor"]["document_id"]
    actions = [event["action"] for event in result["audit_events"]]
    assert actions.count("evidence_attached") == 2
    assert actions.count("document_parsed") == 2


def test_ingest_prior_xbrl_wrong_entity_is_rejected(tmp_path: Path) -> None:
    _, case = _created_case(tmp_path)
    prior = tmp_path / "wrong-entity.xbrl"
    _write_prior_xbrl(prior, "IT99999999999")

    with pytest.raises(ValueError, match="identifier does not match"):
        xbrl_case.ingest_prior_xbrl(case, prior, "preparer_1", case["revision_id"])


def test_prior_xbrl_non_eur_monetary_fact_cannot_reconcile_comparative(
    tmp_path: Path,
) -> None:
    case = _prepared_case(tmp_path)
    prior = tmp_path / "prior-usd.xbrl"
    _write_prior_xbrl(prior)
    prior.write_text(
        prior.read_text(encoding="utf-8").replace(
            "iso4217:EUR</xbrli:measure>",
            "iso4217:USD</xbrli:measure>",
        ),
        encoding="utf-8",
    )
    parsed = xbrl_case.parse_prior_xbrl(prior)
    parsed["matching_context_ids"] = ["prior-instant"]
    parsed["facts"][0]["qname"] = "itcc:Assets"
    parsed["facts"][0]["value"] = "90"
    case["prior_xbrl"] = parsed

    result = xbrl_case.validate_case(case)

    assert "INPUT.PRIOR_XBRL_MONETARY_UNIT_INVALID" in {
        issue["rule_id"] for issue in result["issues"]
    }


def test_prior_xbrl_locale_formatted_monetary_value_cannot_reconcile(
    tmp_path: Path,
) -> None:
    case = _prepared_case(tmp_path)
    prior = tmp_path / "prior-invalid-decimal.xbrl"
    _write_prior_xbrl(prior)
    parsed = xbrl_case.parse_prior_xbrl(prior)
    parsed["matching_context_ids"] = ["prior-instant"]
    parsed["facts"][0]["qname"] = "itcc:Assets"
    parsed["facts"][0]["value"] = "90,00"
    case["prior_xbrl"] = parsed

    result = xbrl_case.validate_case(case)

    assert "INPUT.PRIOR_XBRL_MONETARY_VALUE_INVALID" in {
        issue["rule_id"] for issue in result["issues"]
    }


def test_validate_case_blocks_comparative_mismatch_with_attached_prior_xbrl(
    tmp_path: Path,
) -> None:
    case = _prepared_case(tmp_path)
    case["prior_xbrl"] = {
        "matching_context_ids": ["prior-instant"],
        "contexts": [
            {
                "context_id": "prior-instant",
                "has_dimensions": False,
            }
        ],
        "facts": [
            {
                "qname": "itcc:Assets",
                "context_ref": "prior-instant",
                "unit_ref": "EUR",
                "unit": _eur_unit_record(),
                "nil": False,
                "value": "999",
                "source_anchor": {"source_ref": "prior_fact_assets"},
            },
            {
                "qname": "itcc:LiabilitiesEquity",
                "context_ref": "prior-instant",
                "unit_ref": "EUR",
                "unit": _eur_unit_record(),
                "nil": False,
                "value": "90",
                "source_anchor": {"source_ref": "prior_fact_liabilities"},
            },
        ],
    }
    workpaper = tmp_path / "restatement-workpaper.txt"
    workpaper.write_text("Reviewed comparative restatement evidence", encoding="utf-8")
    case = xbrl_case.attach_supporting_document(
        case,
        workpaper,
        "RESTATEMENT_WORKPAPER",
        "Approved correction of the prior-period comparative",
        "reviewer_1",
        case["revision_id"],
    )

    result = xbrl_case.validate_case(case)

    assert result["prior_xbrl_reconciliation"]["status"] == "FAIL"
    assert "INPUT.PRIOR_XBRL_COMPARATIVE_MISMATCH" in {
        issue["rule_id"] for issue in result["issues"]
    }


def test_evidenced_restatement_resolves_prior_xbrl_comparative_blocker(
    tmp_path: Path,
) -> None:
    case = _prepared_case(tmp_path)
    case["prior_xbrl"] = {
        "matching_context_ids": ["prior-instant"],
        "contexts": [{"context_id": "prior-instant", "has_dimensions": False}],
        "facts": [
            {
                "qname": "itcc:Assets",
                "context_ref": "prior-instant",
                "unit_ref": "EUR",
                "unit": _eur_unit_record(),
                "nil": False,
                "value": "999",
                "source_anchor": {"source_ref": "prior_fact_assets"},
            },
            {
                "qname": "itcc:LiabilitiesEquity",
                "context_ref": "prior-instant",
                "unit_ref": "EUR",
                "unit": _eur_unit_record(),
                "nil": False,
                "value": "90",
                "source_anchor": {"source_ref": "prior_fact_liabilities"},
            },
        ],
    }
    workpaper = tmp_path / "restatement-decision.txt"
    workpaper.write_text("Reviewed comparative restatement evidence", encoding="utf-8")
    case = xbrl_case.attach_supporting_document(
        case,
        workpaper,
        "RESTATEMENT_WORKPAPER",
        "Approved correction of the prior-period comparative",
        "reviewer_1",
        case["revision_id"],
    )
    case = xbrl_case.record_comparative_reconciliation_decisions(
        case,
        [
            {
                "xbrl_concept": "itcc:Assets",
                "action": "RESTATEMENT_CONFIRMED",
                "reason": "The comparative was restated after correcting an error.",
                "source_refs": [case["source_documents"][-1]["document_id"]],
            }
        ],
        "reviewer_1",
        case["revision_id"],
    )

    result = xbrl_case.validate_case(case)

    assert result["prior_xbrl_reconciliation"]["status"] == "PASS"
    assert "INPUT.PRIOR_XBRL_COMPARATIVE_MISMATCH" not in {
        issue["rule_id"] for issue in result["issues"]
    }
    assert "INPUT.PRIOR_XBRL_RESTATEMENT_REVIEWED" in {
        issue["rule_id"] for issue in result["issues"]
    }


def test_prior_xbrl_doctype_is_rejected_before_xml_parsing(tmp_path: Path) -> None:
    prior = tmp_path / "doctype.xbrl"
    prior.write_text(
        '<!DOCTYPE xbrl [<!ENTITY leak SYSTEM "file:///etc/passwd">]><xbrl/>',
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="document type"):
        xbrl_case.parse_prior_xbrl(prior)


def test_prior_xbrl_preserves_explicit_and_typed_table_contexts(
    tmp_path: Path,
) -> None:
    prior = tmp_path / "dimensional-prior.xbrl"
    prior.write_text(
        """<?xml version="1.0" encoding="UTF-8"?>
<xbrli:xbrl xmlns:xbrli="http://www.xbrl.org/2003/instance"
 xmlns:link="http://www.xbrl.org/2003/linkbase"
 xmlns:xlink="http://www.w3.org/1999/xlink"
 xmlns:xbrldi="http://xbrl.org/2006/xbrldi"
 xmlns:itcc="https://example.invalid/itcc"
 xmlns:dim="https://example.invalid/dim"
 xmlns:mem="https://example.invalid/member"
 xmlns:typed="https://example.invalid/typed">
 <link:schemaRef xlink:type="simple" xlink:href="taxonomy.xsd"/>
 <xbrli:context id="table-row-1">
  <xbrli:entity>
   <xbrli:identifier scheme="https://example.invalid/entity">IT00000000000</xbrli:identifier>
  </xbrli:entity>
  <xbrli:period><xbrli:instant>2024-12-31</xbrli:instant></xbrli:period>
  <xbrli:scenario>
   <xbrldi:explicitMember dimension="dim:ClassAxis">mem:TradeMember</xbrldi:explicitMember>
   <xbrldi:typedMember dimension="dim:RegionAxis"><typed:Region>North</typed:Region></xbrldi:typedMember>
  </xbrli:scenario>
 </xbrli:context>
 <itcc:Amount contextRef="table-row-1">25</itcc:Amount>
</xbrli:xbrl>
""",
        encoding="utf-8",
    )

    result = xbrl_case.parse_prior_xbrl(prior)

    context = result["contexts"][0]
    assert result["schema_version"] == 4
    assert context["has_dimensions"] is True
    assert [item["kind"] for item in context["dimensions"]] == [
        "EXPLICIT",
        "TYPED",
    ]
    assert context["dimensions"][0]["axis"]["qname"] == "dim:ClassAxis"
    assert context["dimensions"][0]["member"]["qname"] == "mem:TradeMember"
    assert context["dimensions"][1]["typed_value"]["local_name"] == "Region"
    assert result["facts"][0]["dimension_signature"] == context["dimension_signature"]
    assert result["context_fact_groups"][0]["facts"] == [
        {"fact_id": "prior_fact_000001", "qname": "itcc:Amount"}
    ]


def test_prior_xbrl_extracts_facts_nested_in_tuple_containers(
    tmp_path: Path,
) -> None:
    prior = tmp_path / "tuple-prior.xbrl"
    prior.write_text(
        """<?xml version="1.0" encoding="UTF-8"?>
<xbrli:xbrl xmlns:xbrli="http://www.xbrl.org/2003/instance"
 xmlns:link="http://www.xbrl.org/2003/linkbase"
 xmlns:xlink="http://www.w3.org/1999/xlink"
 xmlns:itcc="https://example.invalid/itcc">
 <link:schemaRef xlink:type="simple" xlink:href="taxonomy.xsd"/>
 <xbrli:context id="table-row-1">
  <xbrli:entity>
   <xbrli:identifier scheme="https://example.invalid/entity">IT00000000000</xbrli:identifier>
  </xbrli:entity>
  <xbrli:period><xbrli:instant>2024-12-31</xbrli:instant></xbrli:period>
 </xbrli:context>
 <itcc:MovementsTable>
  <itcc:MovementRow>
   <itcc:OpeningAmount contextRef="table-row-1">25</itcc:OpeningAmount>
  </itcc:MovementRow>
 </itcc:MovementsTable>
</xbrli:xbrl>
""",
        encoding="utf-8",
    )

    result = xbrl_case.parse_prior_xbrl(prior)

    assert [fact["qname"] for fact in result["facts"]] == ["itcc:OpeningAmount"]
    assert [item["qname"] for item in result["facts"][0]["tuple_ancestors"]] == [
        "itcc:MovementsTable",
        "itcc:MovementRow",
    ]
    assert result["facts"][0]["source_anchor"]["xpath"].endswith(
        "/itcc:MovementsTable/itcc:MovementRow/itcc:OpeningAmount"
    )


def test_mapping_memory_reuses_only_same_tenant_and_client(tmp_path: Path) -> None:
    approved = _approved_case(tmp_path)
    memory = tmp_path / "mapping-memory.json"
    remembered = xbrl_case.remember_mappings(
        approved,
        memory,
        "generic_it_tb_v1",
        "reviewer_1",
        approved["revision_id"],
    )
    assert remembered["audit_events"][-1]["action"] == "approved_mappings_remembered"

    _, new_case = _created_case(tmp_path / "new")
    source = tmp_path / "new" / "trial_balance.csv"
    source.parent.mkdir(exist_ok=True)
    _write_trial_balance(source)
    new_case = xbrl_case.ingest_trial_balance(
        new_case, source, "preparer_1", new_case["revision_id"]
    )
    new_case = xbrl_case.confirm_parser(
        new_case,
        "TURNOVER_EXCLUDES_OPENING",
        "preparer_1",
        new_case["revision_id"],
    )
    new_case["statutory_presentation_required"] = False
    new_case = xbrl_case.determine_forms(
        new_case,
        [
            {"year": 2025, "assets": "1", "revenue": "1", "employees": "1"},
            {"year": 2024, "assets": "1", "revenue": "1", "employees": "1"},
        ],
        _rule_pack(),
        "preparer_1",
        new_case["revision_id"],
    )
    new_case = xbrl_case.select_form(
        new_case, "ABBREVIATED", "preparer_1", new_case["revision_id"]
    )
    new_case = xbrl_case.generate_mapping_candidates(
        new_case,
        memory,
        "generic_it_tb_v1",
        "preparer_1",
        new_case["revision_id"],
    )

    assert len(new_case["mapping_candidates"]) == 2
    assert {item["candidate_source"] for item in new_case["mapping_candidates"]} == {
        "APPROVED_CLIENT_MEMORY"
    }
    suggestion = next(
        event
        for event in new_case["audit_events"]
        if event["action"] == "mapping_suggested"
    )
    assert suggestion["details"]["candidate_count"] == 2
    assert len(suggestion["details"]["account_ids_sha256"]) == 64
    cross_tenant = dict(new_case)
    cross_tenant["tenant_id"] = "another_tenant"
    with pytest.raises(ValueError, match="Cross-tenant"):
        xbrl_case.mapping_candidates(cross_tenant, memory, "generic_it_tb_v1")

    different_client = dict(new_case)
    different_client["entity"] = {
        **new_case["entity"],
        "tax_identifier": "IT11111111111",
    }
    assert (
        xbrl_case.mapping_candidates(different_client, memory, "generic_it_tb_v1") == []
    )


def test_revising_an_accepted_mapping_records_bounded_change_event(
    tmp_path: Path,
) -> None:
    case = _prepared_case(tmp_path)
    decisions = [
        {
            "account_id": "acc_000001",
            "decision": "ACCEPTED",
            "allocations": [
                {
                    "canonical_line": "SP.ATTIVO.ALTRI",
                    "statement_section": "ASSETS",
                    "xbrl_concept": "itcc:Assets",
                    "xbrl_sign_multiplier": "1",
                    "current_amount": "100",
                    "prior_amount": "90",
                    "evidence_status": "OBSERVED",
                }
            ],
        },
        {
            "account_id": "acc_000002",
            "decision": "ACCEPTED",
            "allocations": [
                {
                    "canonical_line": "SP.PASSIVO.DEBITI",
                    "statement_section": "LIABILITIES_EQUITY",
                    "xbrl_concept": "itcc:LiabilitiesEquity",
                    "xbrl_sign_multiplier": "-1",
                    "current_amount": "-100",
                    "prior_amount": "-90",
                    "evidence_status": "USER_CONFIRMED",
                }
            ],
        },
    ]

    result = xbrl_case.apply_mapping_decisions(
        case, decisions, "reviewer_1", case["revision_id"]
    )

    changes = [
        event
        for event in result["audit_events"]
        if event["action"] == "mapping_changed"
    ]
    assert len(changes) == 1
    assert changes[0]["details"]["previous"]["canonical_lines"] == ["SP.ATTIVO.CASSA"]
    assert changes[0]["details"]["current"]["canonical_lines"] == ["SP.ATTIVO.ALTRI"]
    assert "current_amount" not in json.dumps(changes[0]["details"])


def test_tenant_mapping_scope_requires_explicit_reuse_approval(tmp_path: Path) -> None:
    _, case = _created_case(tmp_path)
    source = tmp_path / "trial_balance.csv"
    _write_trial_balance(source)
    case = xbrl_case.ingest_trial_balance(case, source, "preparer_1", "rev_1")
    case = xbrl_case.confirm_parser(
        case,
        "TURNOVER_EXCLUDES_OPENING",
        "preparer_1",
        case["revision_id"],
    )
    case["selected_form"] = "ABBREVIATED"
    case["statutory_presentation_required"] = False
    decision = {
        "account_id": "acc_000001",
        "decision": "ACCEPTED",
        "memory_scope": "TENANT",
        "allocations": [],
    }

    with pytest.raises(ValueError, match="explicit approval"):
        xbrl_case.apply_mapping_decisions(
            case, [decision], "preparer_1", case["revision_id"]
        )


def test_mapping_patch_preserves_unsubmitted_professional_decisions(
    tmp_path: Path,
) -> None:
    case = _prepared_case(tmp_path)
    untouched = deepcopy(case["mappings"][1])
    changed = deepcopy(case["mappings"][0])
    changed["allocations"][0]["canonical_line"] = "SP.ATTIVO.ALTRI"

    result = xbrl_case.apply_mapping_decisions(
        case, [changed], "reviewer_1", case["revision_id"]
    )

    assert len(result["mappings"]) == 2
    assert result["mappings"][1] == untouched
    assert result["mappings"][0]["allocations"][0]["canonical_line"] == (
        "SP.ATTIVO.ALTRI"
    )


def test_nonzero_account_cannot_be_excluded_from_statement_generation(
    tmp_path: Path,
) -> None:
    case = _prepared_case(tmp_path)

    with pytest.raises(ValueError, match="Non-zero account"):
        xbrl_case.apply_mapping_decisions(
            case,
            [
                {
                    "account_id": case["mappings"][0]["account_id"],
                    "decision": "EXCLUDED",
                    "reason": "Reviewed but outside the desired presentation.",
                }
            ],
            "reviewer_1",
            case["revision_id"],
        )


def test_exact_zero_account_can_be_excluded_with_review_reason(
    tmp_path: Path,
) -> None:
    case = _prepared_case(tmp_path)
    account = case["trial_balance"]["entries"][0]
    account["closing_signed"] = "0"
    account["prior_closing_signed"] = "0"

    result = xbrl_case.apply_mapping_decisions(
        case,
        [
            {
                "account_id": account["account_id"],
                "decision": "EXCLUDED",
                "reason": "Both presented annualities have an exact zero balance.",
            }
        ],
        "reviewer_1",
        case["revision_id"],
    )

    assert result["mappings"][0]["decision"] == "EXCLUDED"
    assert result["mappings"][0]["allocations"] == []


def test_validation_defensively_blocks_tampered_nonzero_exclusions(
    tmp_path: Path,
) -> None:
    case = _prepared_case(tmp_path)
    case["mappings"][0]["decision"] = "EXCLUDED"
    case["mappings"][0]["allocations"] = []

    result = xbrl_case.validate_case(case)

    assert "MAPPING.NONZERO_EXCLUSION" in {
        issue["rule_id"] for issue in result["issues"]
    }


def test_receivable_schedule_exact_maturity_and_statement_tie_out_is_complete(
    tmp_path: Path,
) -> None:
    case = _prepared_case(tmp_path)
    payload = {
        "schedule_id": "receivables_cash",
        "schedule_type": "RECEIVABLES",
        "statement_line": "SP.ATTIVO.CASSA",
        "rows": [
            {
                "row_id": "cash",
                "source_refs": ["src_1"],
                "evidence_status": "USER_CONFIRMED",
                "opening_amount": "90",
                "increases": "10",
                "decreases": "0",
                "reclassifications": "0",
                "exchange_effects": "0",
                "other_movements": "0",
                "closing_amount": "100",
                "due_within_next_year": "100",
                "due_after_next_year": "0",
                "over_five_years": "0",
                "gross_closing_amount": "100",
                "allowance_opening": "0",
                "allowance_additions": "0",
                "allowance_uses": "0",
                "allowance_releases": "0",
                "allowance_other_movements": "0",
                "allowance_closing": "0",
                "receivable_class": "TRADE",
                "geography": "ITALY",
                "related_party_class": "NONE_CONFIRMED",
                "factoring_status": "NOT_FACTORED_CONFIRMED",
                "measurement_basis": "NOMINAL_VALUE",
                "currency": "EUR",
                "tax_class": "NON_TAX",
            }
        ],
    }

    result = xbrl_case.record_schedule(case, payload, "preparer_1", case["revision_id"])

    assert result["schedules"][0]["status"] == "COMPLETE"
    result = _complete_disclosures_and_preview(result, tmp_path)
    assert xbrl_case.validate_case(result)["status"] == "PASS"
    assert result["schedules"][0]["issues"] == []


def test_ordinary_case_requires_evidenced_cash_flow_schedule(tmp_path: Path) -> None:
    case = _prepared_case(tmp_path, selected_form="ORDINARY")

    result = xbrl_case.validate_case(case)

    assert "SCHEDULE.REQUIRED" in {item["rule_id"] for item in result["issues"]}


def test_micro_case_can_use_reviewed_footer_without_note_blocks(tmp_path: Path) -> None:
    case = _prepared_case(tmp_path, selected_form="MICRO")
    case = xbrl_case.record_micro_reporting(
        case,
        {
            "mode": "FOOTER_ONLY",
            "footer_items": [
                {
                    "key": "guarantees_commitments_contingencies",
                    "status": "NOT_APPLICABLE_CONFIRMED",
                    "reason": "Annual negative confirmation",
                },
                {
                    "key": "director_auditor_compensation",
                    "status": "PRESENT",
                    "value": "Compensi complessivi euro 1.000.",
                    "source_refs": ["fact_000001"],
                },
                {
                    "key": "own_and_parent_shares",
                    "status": "NOT_APPLICABLE_CONFIRMED",
                    "reason": "No own or parent-company shares held",
                },
            ],
        },
        "reviewer_1",
        case["revision_id"],
    )
    case = xbrl_case.activate_disclosures(
        case, _disclosure_rule_pack(), "preparer_1", case["revision_id"]
    )
    case = xbrl_case.record_disclosure_trigger_decisions(
        case,
        [
            {
                "flag": flag,
                "status": "NOT_APPLICABLE_CONFIRMED",
                "reason": "Reviewed annual micro-company applicability",
                "source_refs": [case["canonical_facts"][0]["fact_id"]],
            }
            for flag in sorted(
                xbrl_case.manual_disclosure_flags(_disclosure_rule_pack())
            )
        ],
        "reviewer_1",
        case["revision_id"],
    )
    negative_keys = {item["key"] for item in _negative_answers()}
    answers = [
        {
            "key": question["answer_key"],
            "status": "ACCEPTED",
            "value": False if question["answer_key"] in negative_keys else True,
            "reason": "Synthetic reviewed micro fixture",
        }
        for question in case["questionnaire"]
        if question["state"] != "NOT_TRIGGERED"
    ]
    answered_keys = {answer["key"] for answer in answers}
    answers.extend(
        {
            "key": key,
            "status": "NOT_APPLICABLE_CONFIRMED",
            "value": False,
            "reason": "Explicit annual micro-company confirmation",
        }
        for key in sorted(negative_keys - answered_keys)
    )
    case = xbrl_case.record_disclosure_answers(
        case, answers, "reviewer_1", case["revision_id"]
    )
    case = xbrl_case.create_preview(
        case, tmp_path / "micro-preview.html", "reviewer_1", case["revision_id"]
    )

    validation = xbrl_case.validate_case(case)

    assert validation["status"] == "PASS"
    assert case["narrative_blocks"] == []
    assert (
        case["disclosure_coverage"]["complete_count"]
        == case["disclosure_coverage"]["triggered_count"]
    )
    assert "Informazioni in calce micro-imprese" in xbrl_case.render_preview_html(
        case
    ).decode("utf-8")

    case = xbrl_case.run_validation(case, "reviewer_1", case["revision_id"])
    warning = next(
        issue
        for issue in case["validation"]["issues"]
        if issue["rule_id"] == "INPUT.PRIOR_XBRL_RECOMMENDED"
    )
    case = xbrl_case.record_issue_reviews(
        case,
        [
            {
                "issue_id": warning["issue_id"],
                "action": "ACKNOWLEDGED",
                "reason": "The unavailable prior filing was considered during review.",
            }
        ],
        "reviewer_1",
        case["revision_id"],
    )
    case = xbrl_case.create_preview(
        case,
        tmp_path / "micro-reviewed-preview.html",
        "reviewer_1",
        case["revision_id"],
    )
    case = xbrl_case.run_validation(case, "reviewer_1", case["revision_id"])
    catalogue = tmp_path / "micro-catalogue.json"
    _write_catalogue(catalogue, "a" * 64)
    package = tmp_path / "micro-taxonomy.zip"
    package.write_bytes(b"test taxonomy package")
    case = xbrl_case.prepare_xbrl_review(
        case,
        catalogue,
        package,
        tmp_path / "micro-xbrl-review",
        "reviewer_1",
        case["revision_id"],
        validator=_passing_xbrl_validator,
    )
    case = xbrl_case.approve_case(
        case, "reviewer_1", case["revision_id"], _reviewer_declaration()
    )

    root = etree.fromstring(xbrl_case.render_xbrl(case, catalogue))
    footer = root.find(
        "{https://example.invalid/itcc-ci}CommentoInformazioniCalceAlloStatoPatrimonialeMicro"
    )
    assert footer is not None
    assert footer.get("contextRef") == "current_instant"
    assert "Compensi complessivi euro 1.000" in str(footer.text)


def test_micro_footer_only_conflicts_with_positive_going_concern_answer(
    tmp_path: Path,
) -> None:
    case = _prepared_case(tmp_path, selected_form="MICRO")
    case["micro_reporting"] = {
        "mode": "FOOTER_ONLY",
        "status": "CONFIRMED",
        "footer_items": [],
    }
    case["disclosure_answers"] = [
        {
            "key": "going_concern_uncertainties",
            "status": "ACCEPTED",
            "value": True,
        }
    ]

    validation = xbrl_case.validate_case(case)

    assert "MICRO.FOOTER_ONLY_DISCLOSURE_CONFLICT" in {
        issue["rule_id"] for issue in validation["issues"]
    }


def test_payable_schedule_uses_explicit_presentation_sign_multiplier(
    tmp_path: Path,
) -> None:
    case = _prepared_case(tmp_path)
    payload = {
        "schedule_id": "payables",
        "schedule_type": "PAYABLES",
        "statement_line": "SP.PASSIVO.DEBITI",
        "statement_multiplier": "-1",
        "rows": [
            {
                "row_id": "trade_payables",
                "source_refs": [case["trial_balance"]["entries"][1]["source_refs"][0]],
                "evidence_status": "OBSERVED",
                "opening_amount": "90",
                "increases": "10",
                "decreases": "0",
                "reclassifications": "0",
                "exchange_effects": "0",
                "other_movements": "0",
                "closing_amount": "100",
                "due_within_next_year": "100",
                "due_after_next_year": "0",
                "over_five_years": "0",
                "secured_amount": "0",
                "payable_class": "TRADE",
                "geography": "ITALY",
                "related_party_class": "NONE_CONFIRMED",
                "security_type": "UNSECURED_CONFIRMED",
                "guarantee_asset": "NONE_CONFIRMED",
                "covenant_status": "NO_COVENANTS_CONFIRMED",
                "shareholder_financing_status": "NOT_SHAREHOLDER_FINANCING",
                "currency": "EUR",
            }
        ],
    }

    result = xbrl_case.record_schedule(case, payload, "preparer_1", case["revision_id"])

    assert result["schedules"][0]["status"] == "COMPLETE"
    assert result["schedules"][0]["statement_multiplier"] == "-1"


def test_fixed_asset_schedule_reconciles_components_and_movements(
    tmp_path: Path,
) -> None:
    case = _prepared_case(tmp_path)
    payload = {
        "schedule_id": "fixed_assets",
        "schedule_type": "FIXED_ASSETS",
        "statement_line": "SP.ATTIVO.CASSA",
        "amortisation_reconciliation_exception": {
            "reason": "Synthetic fixture has no separate amortisation expense line",
            "source_refs": ["review_note_1"],
        },
        "rows": [
            {
                "row_id": "plant",
                "source_refs": ["asset_register_1"],
                "evidence_status": "USER_CONFIRMED",
                "opening_gross_cost": "100",
                "opening_revaluations": "0",
                "opening_accumulated_amortisation": "10",
                "opening_accumulated_impairment": "0",
                "opening_net_carrying_amount": "90",
                "additions": "20",
                "capitalised_internal_costs": "0",
                "reclassifications_in": "0",
                "reclassifications_out": "0",
                "disposals_gross_cost": "0",
                "disposals_accumulated_amortisation": "0",
                "disposals_accumulated_impairment": "0",
                "current_revaluations": "0",
                "current_amortisation": "10",
                "current_impairment": "0",
                "impairment_reversals": "0",
                "other_movements": "0",
                "closing_gross_cost": "120",
                "closing_accumulated_amortisation": "20",
                "closing_accumulated_impairment": "0",
                "closing_net_carrying_amount": "100",
                "asset_class": "PLANT_AND_MACHINERY",
                "ownership_status": "OWNED",
                "pledged_status": "NOT_PLEDGED_CONFIRMED",
            }
        ],
    }

    result = xbrl_case.record_schedule(case, payload, "preparer_1", case["revision_id"])

    assert result["schedules"][0]["status"] == "COMPLETE"


@pytest.mark.parametrize("schedule_type", ["PROVISIONS", "TFR"])
def test_provision_and_tfr_schedules_reconcile_exact_movements(
    tmp_path: Path, schedule_type: str
) -> None:
    case = _prepared_case(tmp_path)
    payload = {
        "schedule_id": schedule_type.lower(),
        "schedule_type": schedule_type,
        "statement_line": "SP.PASSIVO.DEBITI",
        "statement_multiplier": "-1",
        "rows": [
            {
                "row_id": "movement",
                "source_refs": ["schedule_1"],
                "evidence_status": "USER_CONFIRMED",
                "opening_amount": "90",
                "additions": "10",
                "uses": "0",
                "releases": "0",
                "other_increases": "0",
                "other_decreases": "0",
                "closing_amount": "100",
                "provision_class": "OTHER_PROVISION",
                "tfr_class": "EMPLOYEE_TFR",
            }
        ],
    }

    result = xbrl_case.record_schedule(case, payload, "preparer_1", case["revision_id"])

    assert result["schedules"][0]["status"] == "COMPLETE"


def test_schedule_amount_can_support_narrative_and_schedule_edit_invalidates_it(
    tmp_path: Path,
) -> None:
    case = _prepared_case(tmp_path)
    payload = {
        "schedule_id": "provisions_note",
        "schedule_type": "PROVISIONS",
        "statement_line": "SP.PASSIVO.DEBITI",
        "statement_multiplier": "-1",
        "rows": [
            {
                "row_id": "other_provision",
                "source_refs": [],
                "evidence_status": "USER_CONFIRMED",
                "opening_amount": "90",
                "additions": "10",
                "uses": "0",
                "releases": "0",
                "other_increases": "0",
                "other_decreases": "0",
                "closing_amount": "100",
                "provision_class": "OTHER_PROVISION",
            }
        ],
    }
    case = xbrl_case.record_schedule(case, payload, "reviewer_1", case["revision_id"])
    case = xbrl_case.activate_disclosures(
        case, _disclosure_rule_pack(), "preparer_1", case["revision_id"]
    )
    fact_ref = "schedule:provisions_note:other_provision:additions"
    case = xbrl_case.record_narrative_blocks(
        case,
        [
            {
                "block_id": "provisions_movement_note",
                "section_id": "LIABILITIES_EQUITY",
                "text": "Gli incrementi ammontano a euro 10.",
                "xbrl_concept": "itcc:NotesText",
                "status": "ACCEPTED",
                "claims": [
                    {
                        "sentence": "Gli incrementi ammontano a euro 10.",
                        "kind": "FACTUAL",
                        "source_refs": [fact_ref],
                        "template_version": "",
                        "semantic_support": {
                            "status": "SUPPORTED",
                            "reason": "Exact accepted provisions-schedule addition",
                        },
                        "fact_assertions": [
                            {
                                "fact_ref": fact_ref,
                                "value_field": "value",
                                "value": "10",
                            }
                        ],
                    }
                ],
            }
        ],
        "reviewer_1",
        case["revision_id"],
    )

    changed = json.loads(json.dumps(payload))
    changed["rows"][0]["additions"] = "20"
    changed["rows"][0]["uses"] = "10"
    result = xbrl_case.record_schedule(case, changed, "reviewer_1", case["revision_id"])

    assert result["narrative_blocks"] == []
    assert result["note_outline"][3]["status"] == "EMPTY"


def test_equity_schedule_reconciles_explicit_resolution_movements(
    tmp_path: Path,
) -> None:
    case = _prepared_case(tmp_path)
    payload = {
        "schedule_id": "equity",
        "schedule_type": "EQUITY",
        "statement_line": "SP.PASSIVO.DEBITI",
        "statement_multiplier": "-1",
        "rows": [
            {
                "row_id": "equity_total",
                "source_refs": ["resolution_1"],
                "evidence_status": "USER_CONFIRMED",
                "opening_amount": "90",
                "prior_result_allocation": "0",
                "contributions": "10",
                "reductions": "0",
                "dividends": "0",
                "transfers_in": "0",
                "transfers_out": "0",
                "reserve_uses": "0",
                "current_year_result": "0",
                "other_movements": "0",
                "closing_amount": "100",
                "equity_class": "SHARE_CAPITAL",
                "origin": "SHAREHOLDER_CONTRIBUTION",
                "availability": "AVAILABLE",
                "distributability": "NOT_DISTRIBUTABLE",
                "prior_uses": "NONE_CONFIRMED",
                "treasury_shares_status": "NONE_CONFIRMED",
                "fair_value_reserve_status": "NOT_APPLICABLE_CONFIRMED",
            }
        ],
    }

    result = xbrl_case.record_schedule(case, payload, "preparer_1", case["revision_id"])

    assert result["schedules"][0]["status"] == "COMPLETE"


def test_tax_and_guarantee_schedules_keep_distinct_reconciliation_boundaries(
    tmp_path: Path,
) -> None:
    case = _prepared_case(tmp_path)
    tax_payload = {
        "schedule_id": "tax",
        "schedule_type": "TAXES",
        "statement_line": "SP.ATTIVO.CASSA",
        "rows": [
            {
                "row_id": "tax_asset",
                "source_refs": ["tax_computation_1"],
                "evidence_status": "USER_CONFIRMED",
                "opening_amount": "90",
                "increases": "10",
                "decreases": "0",
                "closing_amount": "100",
                "current_tax_expense": "0",
                "tax_base": "100",
                "temporary_difference": "0",
                "recognised_amount": "100",
                "unrecognised_amount": "0",
                "tax_type": "CURRENT_TAX_RECEIVABLE",
                "jurisdiction": "IT",
                "recoverability_assessment": "RECOVERABLE_CONFIRMED",
            }
        ],
    }
    case = xbrl_case.record_schedule(
        case, tax_payload, "preparer_1", case["revision_id"]
    )
    guarantee_payload = {
        "schedule_id": "guarantees",
        "schedule_type": "GUARANTEES_COMMITMENTS",
        "rows": [
            {
                "row_id": "guarantee_1",
                "source_refs": ["guarantee_register_1"],
                "evidence_status": "USER_CONFIRMED",
                "closing_amount": "50",
                "guarantee_type": "SURETY",
                "beneficiary": "BANK",
                "secured_asset": "NONE_CONFIRMED",
                "related_party_class": "NONE_CONFIRMED",
                "expiry": "2027-12-31",
            }
        ],
    }

    result = xbrl_case.record_schedule(
        case, guarantee_payload, "preparer_1", case["revision_id"]
    )

    assert [item["status"] for item in result["schedules"]] == [
        "COMPLETE",
        "COMPLETE",
    ]
    assert result["schedules"][1]["statement_line"] is None


def test_cash_flow_schedule_reconciles_opening_closing_and_net_change(
    tmp_path: Path,
) -> None:
    case = _prepared_case(tmp_path, selected_form="ORDINARY")
    payload = {
        "schedule_id": "cash_flow",
        "schedule_type": "CASH_FLOW",
        "cash_statement_line": "SP.ATTIVO.CASSA",
        "opening_cash": "90",
        "closing_cash": "100",
        "items": [
            {
                "item_id": "operating_1",
                "category": "OPERATING",
                "amount": "10",
                "source_refs": ["src_1"],
                "evidence_status": "USER_CONFIRMED",
                "movement_evidence_type": "LEDGER_DETAIL",
                "rationale": "Reviewed cash ledger movement",
            }
        ],
    }

    result = xbrl_case.record_schedule(case, payload, "preparer_1", case["revision_id"])

    assert result["schedules"][0]["status"] == "COMPLETE"
    result = _complete_disclosures_and_preview(result, tmp_path)
    assert xbrl_case.validate_case(result)["status"] == "PASS"


def test_cash_flow_schedule_must_reconcile_to_statutory_xbrl_root(
    tmp_path: Path,
) -> None:
    case = _prepared_case(tmp_path, selected_form="ORDINARY")
    payload = {
        "schedule_id": "cash_flow",
        "schedule_type": "CASH_FLOW",
        "cash_statement_line": "SP.ATTIVO.CASSA",
        "opening_cash": "90",
        "closing_cash": "100",
        "items": [
            {
                "item_id": "operating_1",
                "category": "OPERATING",
                "amount": "10",
                "source_refs": ["src_1"],
                "evidence_status": "USER_CONFIRMED",
                "movement_evidence_type": "LEDGER_DETAIL",
                "rationale": "Reviewed cash ledger movement",
            }
        ],
    }
    case = xbrl_case.record_schedule(case, payload, "preparer_1", case["revision_id"])
    case["statutory_presentation_required"] = True
    case["statutory_presentation"] = {
        "status": "COMPLETE",
        "cash_flow_values": {"current_value": "9", "prior_value": "0"},
        "input_context": {},
        "output_facts": [],
    }

    mismatch_codes = {
        issue["rule_id"] for issue in xbrl_case.validate_case(case)["issues"]
    }
    case["statutory_presentation"]["cash_flow_values"]["current_value"] = "10"
    matching_codes = {
        issue["rule_id"] for issue in xbrl_case.validate_case(case)["issues"]
    }

    assert "CASH_FLOW.XBRL_NET_CHANGE_RECONCILIATION" in mismatch_codes
    assert "CASH_FLOW.XBRL_NET_CHANGE_RECONCILIATION" not in matching_codes


def test_duplicate_schedule_type_is_a_validation_blocker(tmp_path: Path) -> None:
    case = _prepared_case(tmp_path, selected_form="ORDINARY")
    payload = {
        "schedule_id": "cash_flow_primary",
        "schedule_type": "CASH_FLOW",
        "cash_statement_line": "SP.ATTIVO.CASSA",
        "opening_cash": "90",
        "closing_cash": "100",
        "items": [
            {
                "item_id": "operating_1",
                "category": "OPERATING",
                "amount": "10",
                "source_refs": ["src_1"],
                "evidence_status": "USER_CONFIRMED",
                "movement_evidence_type": "LEDGER_DETAIL",
                "rationale": "Reviewed cash ledger movement",
            }
        ],
    }
    case = xbrl_case.record_schedule(case, payload, "preparer_1", case["revision_id"])
    duplicate = dict(case["schedules"][0])
    duplicate["schedule_id"] = "cash_flow_duplicate"
    case["schedules"].append(duplicate)

    codes = {issue["rule_id"] for issue in xbrl_case.validate_case(case)["issues"]}

    assert "SCHEDULE.DUPLICATE_TYPE" in codes


def test_cash_flow_item_without_movement_evidence_is_rejected(tmp_path: Path) -> None:
    case = _prepared_case(tmp_path, selected_form="ORDINARY")
    payload = {
        "schedule_id": "cash_flow",
        "schedule_type": "CASH_FLOW",
        "cash_statement_line": "SP.ATTIVO.CASSA",
        "opening_cash": "90",
        "closing_cash": "100",
        "items": [
            {
                "item_id": "unsupported",
                "category": "INVESTING",
                "amount": "10",
                "source_refs": [],
                "evidence_status": "MODEL_SUGGESTED",
                "movement_evidence_type": "TRIAL_BALANCE",
            }
        ],
    }

    with pytest.raises(ValueError, match="requires accepted movement evidence"):
        xbrl_case.record_schedule(case, payload, "preparer_1", case["revision_id"])


def test_incomplete_schedule_is_a_validation_blocker(tmp_path: Path) -> None:
    case = _prepared_case(tmp_path)
    payload = {
        "schedule_id": "bad_receivables",
        "schedule_type": "RECEIVABLES",
        "statement_line": "SP.ATTIVO.CASSA",
        "rows": [
            {
                "row_id": "cash",
                "source_refs": [case["trial_balance"]["entries"][0]["source_refs"][0]],
                "evidence_status": "OBSERVED",
                "opening_amount": "90",
                "increases": "10",
                "decreases": "0",
                "reclassifications": "0",
                "exchange_effects": "0",
                "other_movements": "0",
                "closing_amount": "100",
                "due_within_next_year": "80",
                "due_after_next_year": "0",
                "over_five_years": "0",
                "gross_closing_amount": "100",
                "allowance_opening": "0",
                "allowance_additions": "0",
                "allowance_uses": "0",
                "allowance_releases": "0",
                "allowance_other_movements": "0",
                "allowance_closing": "0",
            }
        ],
    }
    case = xbrl_case.record_schedule(case, payload, "preparer_1", case["revision_id"])

    result = xbrl_case.validate_case(case)

    assert case["schedules"][0]["status"] == "INCOMPLETE"
    assert "SCHEDULE.RECEIVABLES.GEOGRAPHY_REQUIRED" in {
        item["rule_id"] for item in case["schedules"][0]["issues"]
    }
    assert "SCHEDULE.RECONCILIATION" in {item["rule_id"] for item in result["issues"]}


def test_ingest_payable_schedule_csv_preserves_cell_anchors_and_reconciles(
    tmp_path: Path,
) -> None:
    case = _prepared_case(tmp_path)
    source = tmp_path / "payables.csv"
    source.write_text(
        "row_id;label;opening_amount;increases;decreases;reclassifications;"
        "exchange_effects;other_movements;closing_amount;due_within_next_year;"
        "due_after_next_year;over_five_years;secured_amount;payable_class;geography;"
        "related_party_class;security_type;guarantee_asset;covenant_status;"
        "shareholder_financing_status;currency\n"
        "trade;Debiti commerciali;90,00;10,00;0,00;0,00;0,00;0,00;100,00;"
        "100,00;0,00;0,00;0,00;TRADE;ITALY;NONE_CONFIRMED;UNSECURED_CONFIRMED;"
        "NONE_CONFIRMED;NO_COVENANTS_CONFIRMED;NOT_SHAREHOLDER_FINANCING;EUR\n",
        encoding="utf-8",
    )

    result = xbrl_case.ingest_schedule_file(
        case,
        source,
        "PAYABLES",
        "payables_imported",
        "SP.PASSIVO.DEBITI",
        {"statement_multiplier": "-1"},
        "preparer_1",
        case["revision_id"],
    )

    schedule = result["schedules"][0]
    document = result["source_documents"][-1]
    assert schedule["status"] == "COMPLETE"
    assert schedule["rows"][0]["closing_amount"] == "100.00"
    assert document["purpose"] == "PAYABLES_SCHEDULE"
    assert len(document["source_anchors"]) == 21
    assert document["source_anchors"][0] == {
        "source_ref": "src_doc_0002_0000001",
        "document_id": "doc_0002",
        "sheet": "csv",
        "row": 2,
        "column": "A",
        "column_header": "row_id",
        "normalized_column": "row_id",
        "raw_value": "trade",
        "normalized_value": "trade",
        "parser_profile": "payables_template_v1",
        "confidence": "HIGH",
    }
    assert schedule["rows"][0]["source_refs"] == [
        item["source_ref"] for item in document["source_anchors"]
    ]


def test_ingest_schedule_rejects_headers_that_collide_after_normalization(
    tmp_path: Path,
) -> None:
    case = _prepared_case(tmp_path)
    source = tmp_path / "duplicate-schedule-header.csv"
    source.write_text("row_id;row id\ntrade;overwrite\n", encoding="utf-8")

    with pytest.raises(ValueError, match="Duplicate normalized column 'row_id'"):
        xbrl_case.ingest_schedule_file(
            case,
            source,
            "PAYABLES",
            "payables_imported",
            "SP.PASSIVO.DEBITI",
            {"statement_multiplier": "-1"},
            "preparer_1",
            case["revision_id"],
        )


def test_ingest_schedule_template_missing_required_column_is_rejected(
    tmp_path: Path,
) -> None:
    case = _prepared_case(tmp_path)
    source = tmp_path / "payables.csv"
    source.write_text("row_id;closing_amount\ntrade;100\n", encoding="utf-8")

    with pytest.raises(ValueError, match="missing columns"):
        xbrl_case.ingest_schedule_file(
            case,
            source,
            "PAYABLES",
            "payables_imported",
            "SP.PASSIVO.DEBITI",
            {"statement_multiplier": "-1"},
            "preparer_1",
            case["revision_id"],
        )


def test_ingest_schedule_template_blank_required_value_is_not_zero(
    tmp_path: Path,
) -> None:
    case = _prepared_case(tmp_path)
    source = tmp_path / "payables-blank.csv"
    source.write_text(
        "row_id;opening_amount;increases;decreases;reclassifications;"
        "exchange_effects;other_movements;closing_amount;due_within_next_year;"
        "due_after_next_year;over_five_years;secured_amount;payable_class;geography;"
        "related_party_class;security_type;guarantee_asset;covenant_status;"
        "shareholder_financing_status;currency\n"
        "trade;90;10;0;0;0;0;;100;0;0;0;TRADE;ITALY;NONE_CONFIRMED;"
        "UNSECURED_CONFIRMED;NONE_CONFIRMED;NO_COVENANTS_CONFIRMED;"
        "NOT_SHAREHOLDER_FINANCING;EUR\n",
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="blank is not zero"):
        xbrl_case.ingest_schedule_file(
            case,
            source,
            "PAYABLES",
            "payables_imported",
            "SP.PASSIVO.DEBITI",
            {"statement_multiplier": "-1"},
            "preparer_1",
            case["revision_id"],
        )


def test_xlsx_formula_without_cached_value_is_rejected(tmp_path: Path) -> None:
    openpyxl = pytest.importorskip("openpyxl")
    _, case = _created_case(tmp_path)
    source = tmp_path / "formula.xlsx"
    workbook = openpyxl.Workbook()
    sheet = workbook.active
    sheet.append(
        [
            "account_code",
            "account_description",
            "opening_signed",
            "period_debit",
            "period_credit",
            "closing_signed",
            "prior_closing_signed",
        ]
    )
    sheet.append(["1000", "Cassa", "=80+10", 10, 0, 100, 90])
    workbook.save(source)

    with pytest.raises(ValueError, match="formula has no trusted cached value"):
        xbrl_case.ingest_trial_balance(case, source, "preparer_1", "rev_1")


def test_xlsx_member_path_traversal_is_rejected(tmp_path: Path) -> None:
    _, case = _created_case(tmp_path)
    source = tmp_path / "unsafe.xlsx"
    with zipfile.ZipFile(source, "w") as archive:
        archive.writestr("../escape.xml", "unsafe")

    with pytest.raises(ValueError, match="Unsafe XLSX member path"):
        xbrl_case.ingest_trial_balance(case, source, "preparer_1", "rev_1")


def test_disclosure_rule_pack_exposes_every_annual_negative_confirmation(
    tmp_path: Path,
) -> None:
    case = _prepared_case(tmp_path)

    result = xbrl_case.activate_disclosures(
        case,
        _disclosure_rule_pack(),
        "preparer_1",
        case["revision_id"],
    )

    negative_keys = {item["key"] for item in _negative_answers()}
    question_keys = {
        item["answer_key"]
        for item in result["questionnaire"]
        if item["state"] != "NOT_TRIGGERED"
    }
    assert negative_keys <= question_keys


def test_disclosure_rule_pack_outside_effective_period_is_rejected(
    tmp_path: Path,
) -> None:
    case = _prepared_case(tmp_path)
    rule_pack = _disclosure_rule_pack()
    rule_pack["effective_from"] = "2026-01-01"
    before = json.loads(json.dumps(case))

    with pytest.raises(ValueError, match="not effective"):
        xbrl_case.activate_disclosures(
            case, rule_pack, "preparer_1", case["revision_id"]
        )

    assert case == before


def test_disclosure_rule_pack_without_rules_is_rejected_before_mutation(
    tmp_path: Path,
) -> None:
    case = _prepared_case(tmp_path)
    rule_pack = _disclosure_rule_pack()
    rule_pack["rules"] = []
    before = json.loads(json.dumps(case))

    with pytest.raises(ValueError, match="non-empty schema-1"):
        xbrl_case.activate_disclosures(
            case, rule_pack, "preparer_1", case["revision_id"]
        )

    assert case == before


def test_narrative_text_outside_sentence_claims_is_rejected() -> None:
    blocks = [
        {
            "block_id": "block_1",
            "section_id": "INTRODUCTION",
            "text": "Claim supported. Extra unsupported assertion.",
            "claims": [
                {
                    "sentence": "Claim supported.",
                    "kind": "FACTUAL",
                    "source_refs": ["fact_1"],
                }
            ],
        }
    ]

    with pytest.raises(ValueError, match="composed exactly"):
        xbrl_case.normalize_narrative_blocks(blocks, "reviewer_1")


def test_narrative_blocks_cannot_mix_languages_in_one_output() -> None:
    blocks = [
        {
            "block_id": "block_1",
            "section_id": "INTRODUCTION",
            "language": "en",
            "text": "Supported statement.",
            "claims": [
                {
                    "sentence": "Supported statement.",
                    "kind": "FACTUAL",
                    "source_refs": ["fact_1"],
                }
            ],
        }
    ]

    with pytest.raises(ValueError, match="cannot mix languages"):
        xbrl_case.normalize_narrative_blocks(blocks, "reviewer_1", output_language="it")


def test_accepted_narrative_amount_must_match_the_cited_fact(tmp_path: Path) -> None:
    case = _prepared_case(tmp_path)
    case = xbrl_case.activate_disclosures(
        case,
        _disclosure_rule_pack(),
        "reviewer_1",
        case["revision_id"],
    )
    fact_ref = case["canonical_facts"][0]["fact_id"]
    sentence = "I ricavi dell'esercizio ammontano a euro 999999."
    blocks = [
        {
            "block_id": "block_false_amount",
            "section_id": "INTRODUCTION",
            "text": sentence,
            "status": "ACCEPTED",
            "xbrl_concept": "itcc:NotesText",
            "claims": [
                {
                    "sentence": sentence,
                    "kind": "FACTUAL",
                    "source_refs": [fact_ref],
                    "fact_assertions": [
                        {
                            "fact_ref": fact_ref,
                            "value_field": "current_value",
                            "value": "999999",
                        }
                    ],
                    "semantic_support": {
                        "status": "SUPPORTED",
                        "reason": "Controlled negative-test review decision.",
                    },
                }
            ],
        }
    ]

    with pytest.raises(ValueError, match="does not match structured evidence"):
        xbrl_case.record_narrative_blocks(
            case, blocks, "reviewer_1", case["revision_id"]
        )


def test_accepted_italian_narrative_parses_grouped_money_literal(
    tmp_path: Path,
) -> None:
    case = _prepared_case(tmp_path)
    case = xbrl_case.activate_disclosures(
        case,
        _disclosure_rule_pack(),
        "reviewer_1",
        case["revision_id"],
    )
    case["canonical_facts"][0]["current_value"] = "15000"
    fact_ref = case["canonical_facts"][0]["fact_id"]
    sentence = "La disponibilita dell'esercizio ammonta a euro 15.000."
    blocks = [
        {
            "block_id": "block_grouped_amount",
            "section_id": "INTRODUCTION",
            "text": sentence,
            "status": "ACCEPTED",
            "xbrl_concept": "itcc:NotesText",
            "claims": [
                {
                    "sentence": sentence,
                    "kind": "FACTUAL",
                    "source_refs": [fact_ref],
                    "fact_assertions": [
                        {
                            "fact_ref": fact_ref,
                            "value_field": "current_value",
                            "value": "15000",
                        }
                    ],
                    "semantic_support": {
                        "status": "SUPPORTED",
                        "reason": "The sentence describes the cited reviewed fact.",
                    },
                }
            ],
        }
    ]

    result = xbrl_case.record_narrative_blocks(
        case, blocks, "reviewer_1", case["revision_id"]
    )

    assert result["narrative_blocks"][0]["status"] == "ACCEPTED"


def test_accepted_narrative_requires_an_xbrl_destination(tmp_path: Path) -> None:
    case = _prepared_case(tmp_path)
    case = xbrl_case.activate_disclosures(
        case,
        _disclosure_rule_pack(),
        "reviewer_1",
        case["revision_id"],
    )
    fact_ref = case["canonical_facts"][0]["fact_id"]
    sentence = "La sezione è stata verificata sul fatto contabile citato."
    blocks = [
        {
            "block_id": "block_without_destination",
            "section_id": "INTRODUCTION",
            "text": sentence,
            "status": "ACCEPTED",
            "claims": [
                {
                    "sentence": sentence,
                    "kind": "FACTUAL",
                    "source_refs": [fact_ref],
                    "semantic_support": {
                        "status": "SUPPORTED",
                        "reason": "Controlled negative-test review decision.",
                    },
                }
            ],
        }
    ]

    with pytest.raises(ValueError, match="requires an XBRL concept"):
        xbrl_case.record_narrative_blocks(
            case, blocks, "reviewer_1", case["revision_id"]
        )


def test_prior_narrative_redline_records_word_changes() -> None:
    redline = xbrl_case.narrative_redline(
        "La società non ha dipendenti.",
        "La società ha cinque dipendenti.",
    )

    assert "-non" in redline
    assert "+cinque" in redline


def test_validate_case_blocks_unmapped_non_cash_schedule_table(
    tmp_path: Path,
) -> None:
    case = _prepared_case(tmp_path)
    case["taxonomy_mapping_index"] = {"inventory_sha256": "inventory_1"}
    case["schedules"] = [
        {
            "schedule_id": "provisions_1",
            "schedule_type": "PROVISIONS",
            "status": "COMPLETE",
            "rows": [],
        }
    ]

    result = xbrl_case.validate_case(case)

    assert "SCHEDULE.TAXONOMY_ADAPTER_REQUIRED" in {
        issue["rule_id"] for issue in result["issues"]
    }


def test_preview_escapes_untrusted_narrative_markup(tmp_path: Path) -> None:
    case = _prepared_case(tmp_path)
    case["narrative_blocks"] = [
        {
            "section_id": "INTRODUCTION",
            "text": "<script>alert('unsafe')</script>",
            "status": "DRAFT",
        }
    ]

    preview = xbrl_case.render_preview_html(case).decode("utf-8")

    assert "<script>" not in preview
    assert "&lt;script&gt;" in preview


def test_preview_has_keyboard_and_screen_reader_table_structure(
    tmp_path: Path,
) -> None:
    case = _prepared_case(tmp_path)

    root = etree.HTML(xbrl_case.render_preview_html(case))

    assert root.get("lang") == "it"
    assert root.xpath('//a[@class="skip-link" and @href="#main-content"]')
    assert root.xpath('//main[@id="main-content" and @tabindex="-1"]')
    tables = root.xpath("//table")
    assert len(tables) == 6
    assert all(table.find("caption") is not None for table in tables)
    assert all(header.get("scope") == "col" for header in root.xpath("//th"))
    regions = root.xpath('//div[@role="region"]')
    assert len(regions) == 6
    assert all(region.get("tabindex") == "0" for region in regions)


def test_preview_surfaces_statutory_presentation_review_status(tmp_path: Path) -> None:
    case = _prepared_case(tmp_path)
    case["statutory_presentation"] = {
        "status": "INCOMPLETE",
        "summary": {
            "required_leaf_concepts": 87,
            "explicit_decisions": 12,
            "missing_period_decisions": 3,
            "issues": 1,
        },
    }

    preview = xbrl_case.render_preview_html(case).decode("utf-8")

    assert "Copertura dei prospetti civilistici" in preview
    assert "decisioni mancanti 3" in preview


def test_validation_requires_current_preview_and_disclosure_pack(
    tmp_path: Path,
) -> None:
    case = _prepared_case(tmp_path)
    case = xbrl_case.record_disclosure_answers(
        case, _negative_answers(), "preparer_1", case["revision_id"]
    )

    result = xbrl_case.validate_case(case)

    rule_ids = {item["rule_id"] for item in result["issues"]}
    assert "DISCLOSURE.RULE_PACK_REQUIRED" in rule_ids
    assert "REVIEW.PREVIEW_REQUIRED" in rule_ids


def test_validation_blocks_unbalanced_comparative_balance_sheet(
    tmp_path: Path,
) -> None:
    case = _prepared_case(tmp_path)
    case["statements"]["section_totals"]["ASSETS"]["prior"] = "91"

    result = xbrl_case.validate_case(case)

    assert "STATEMENT.COMPARATIVE_BALANCE_SHEET" in {
        issue["rule_id"] for issue in result["issues"]
    }


def test_validation_blocks_comparative_result_equity_mismatch(
    tmp_path: Path,
) -> None:
    case = _prepared_case(tmp_path)
    case["statements"]["facts"] = [
        *case["statements"]["facts"],
        *[
            {
                "statement_section": "INCOME_RESULT",
                "current_value": "0",
                "prior_value": "10",
            },
            {
                "statement_section": "EQUITY_RESULT",
                "current_value": "0",
                "prior_value": "0",
            },
        ],
    ]

    result = xbrl_case.validate_case(case)

    assert "STATEMENT.COMPARATIVE_RESULT_TIE_OUT" in {
        issue["rule_id"] for issue in result["issues"]
    }


@pytest.mark.parametrize(
    ("answer", "message"),
    [
        (
            {"key": "post_closing_events", "status": "ACCEPTED", "value": None},
            "reviewed structured value",
        ),
        (
            {
                "key": "post_closing_events",
                "status": "NOT_APPLICABLE_CONFIRMED",
                "reason": "",
            },
            "specific reason",
        ),
        (
            {
                "key": "post_closing_events",
                "status": "ACCEPTED",
                "value": False,
                "confirmed_by": "another_user",
            },
            "authenticated actor",
        ),
        (
            {"key": "invented_answer", "status": "ACCEPTED", "value": True},
            "not active or annual",
        ),
    ],
)
def test_disclosure_completion_rejects_empty_professional_confirmations(
    tmp_path: Path,
    answer: dict[str, object],
    message: str,
) -> None:
    case = _prepared_case(tmp_path)

    with pytest.raises(ValueError, match=message):
        xbrl_case.record_disclosure_answers(
            case, [answer], "reviewer_1", case["revision_id"]
        )


def test_substantive_taxonomy_mismatch_requires_reviewed_treatment_and_report(
    tmp_path: Path,
) -> None:
    case = _prepared_case(tmp_path)
    case = _complete_disclosures_and_preview(case, tmp_path)
    case = xbrl_case.record_disclosure_answers(
        case,
        [
            {
                "key": "double_format_events",
                "status": "ACCEPTED",
                "value": True,
                "reason": "The approved notes contain a substantive difference.",
            }
        ],
        "reviewer_1",
        case["revision_id"],
    )

    missing_treatment = xbrl_case.validate_case(case)

    assert "XBRL.SUBSTANTIVE_TAXONOMY_MISMATCH" in {
        issue["rule_id"] for issue in missing_treatment["issues"]
    }
    case = xbrl_case.record_taxonomy_representation(
        case,
        {
            "mismatch_present": True,
            "affected_sections": ["OTHER_INFORMATION"],
            "differences": [
                {
                    "difference_id": "difference_1",
                    "description": "The taxonomy cannot express the approved table layout.",
                    "affected_facts": ["fact_000001"],
                    "source_refs": [],
                }
            ],
            "chosen_treatment": "DOUBLE_FORMAT_ROUTE_REFERRED_FOR_PROFESSIONAL_FILING",
            "reviewer_reason": "The filing route remains a professional decision outside Vera.",
        },
        "reviewer_1",
        case["revision_id"],
    )
    case = xbrl_case.create_preview(
        case, tmp_path / "mismatch-preview.html", "reviewer_1", case["revision_id"]
    )
    case = xbrl_case.run_validation(case, "reviewer_1", case["revision_id"])
    warning = next(
        issue
        for issue in case["validation"]["issues"]
        if issue["rule_id"] == "XBRL.SUBSTANTIVE_TAXONOMY_MISMATCH_REVIEWED"
    )
    case = xbrl_case.record_issue_reviews(
        case,
        [
            {
                "issue_id": warning["issue_id"],
                "action": "ACKNOWLEDGED",
                "reason": "The selected professional filing treatment was reviewed.",
            }
        ],
        "reviewer_1",
        case["revision_id"],
    )

    assert case["taxonomy_representation"]["vera_did_not_select_filing_route"] is True


def test_external_validation_record_preserves_approved_snapshot(
    tmp_path: Path,
) -> None:
    case = _approved_case(tmp_path)
    snapshot_hash = case["approval"]["snapshot_hash"]
    report = tmp_path / "tebeni-report.txt"
    report.write_text("Controllo completato", encoding="utf-8")

    result = xbrl_case.record_external_validation(
        case,
        report,
        "PASS",
        [],
        "reviewer_1",
        case["revision_id"],
    )

    assert result["approval"]["snapshot_hash"] == snapshot_hash
    assert result["external_validation"]["route"] == "USER_CONTROLLED_MANUAL_UPLOAD"
    assert result["external_validation"]["report"]["sha256"]


def test_workpaper_includes_external_validation_as_non_authoritative_addendum(
    tmp_path: Path,
) -> None:
    case = _approved_case(tmp_path)
    snapshot_hash = case["approval"]["snapshot_hash"]
    report = tmp_path / "tebeni-report.txt"
    report.write_text("Controllo completato", encoding="utf-8")
    case = xbrl_case.record_external_validation(
        case,
        report,
        "PASS",
        [],
        "reviewer_1",
        case["revision_id"],
    )
    catalogue = tmp_path / "catalogue.json"
    _write_catalogue(catalogue, "a" * 64)
    output = tmp_path / "export-with-external-result"

    xbrl_case.export_case(case, output, catalogue, "reviewer_1")

    workpaper = json.loads((output / "workpaper.json").read_text(encoding="utf-8"))
    assert workpaper["approval"]["snapshot_hash"] == snapshot_hash
    assert workpaper["external_validation"]["authoritative_for_filing"] is False
    assert workpaper["external_validation"]["result"] == "PASS"
    assert workpaper["external_validation_documents"][0]["purpose"] == (
        "EXTERNAL_VALIDATION_REPORT"
    )


def _artifact_bytes_by_name(output_dir: Path) -> dict[str, bytes]:
    return {
        path.name: path.read_bytes()
        for path in sorted(output_dir.iterdir())
        if path.is_file()
    }


def test_export_includes_review_preview_and_structured_notes(tmp_path: Path) -> None:
    case = _approved_case(tmp_path)
    catalogue = tmp_path / "catalogue.json"
    _write_catalogue(catalogue, "a" * 64)
    output_dir = tmp_path / "export"

    result = xbrl_case.export_case(case, output_dir, catalogue, "reviewer_1")

    workpaper = json.loads((output_dir / "workpaper.json").read_text(encoding="utf-8"))
    mapping_report = json.loads(
        (output_dir / "mapping_report.json").read_text(encoding="utf-8")
    )
    issue_report = json.loads(
        (output_dir / "issue_report.json").read_text(encoding="utf-8")
    )
    validation_report = json.loads(
        (output_dir / "validation_report.json").read_text(encoding="utf-8")
    )
    manifest = json.loads(
        (output_dir / "artifact_manifest.json").read_text(encoding="utf-8")
    )
    exported_preview = output_dir / "preview.html"
    assert (
        exported_preview.read_bytes()
        == (tmp_path / "reviewed-preview.html").read_bytes()
    )
    exported_xbrl = next(output_dir.glob("*.xbrl"))
    assert (
        exported_xbrl.read_bytes()
        == (tmp_path / "approval-xbrl-review" / "review-candidate.xbrl").read_bytes()
    )
    assert "content_base64" not in workpaper["preview"]
    assert workpaper["disclosure_coverage"]["triggered_count"] > 0
    assert workpaper["narrative_blocks"]
    assert workpaper["assumptions"] == []
    assert workpaper["filing_campaign_year"] == 2026
    assert workpaper["regulatory_rule_pack_checksums"] == {
        "statutory_rule_pack": case["approval"]["snapshot"]["rule_pack_checksum"],
        "oic_rule_pack": case["approval"]["snapshot"]["oic_rule_pack_checksum"],
        "filing_instruction_pack": case["approval"]["snapshot"][
            "filing_instruction_pack_checksum"
        ],
        "disclosure_rule_pack": case["approval"]["snapshot"][
            "disclosure_rule_pack_checksum"
        ],
        "statutory_presentation_rule_pack": case["approval"]["snapshot"].get(
            "statutory_presentation_rule_pack_checksum"
        ),
        "schedule_taxonomy_adapter_rule_pack": case["approval"]["snapshot"].get(
            "schedule_taxonomy_adapter_rule_pack_checksum"
        ),
    }
    assert mapping_report["snapshot_hash"] == case["approval"]["snapshot_hash"]
    assert mapping_report["summary"] == {
        "total_accounts": 2,
        "accepted_accounts": 2,
        "excluded_accounts": 0,
        "split_accounts": 0,
        "unresolved_accounts": 0,
    }
    assert all(row["decision"] for row in mapping_report["rows"])
    assert all(row["source_refs"] for row in mapping_report["rows"])
    assert issue_report["snapshot_hash"] == case["approval"]["snapshot_hash"]
    assert issue_report["validation_status"] == "PASS"
    assert validation_report["case_validation"]["status"] == "PASS"
    assert validation_report["local_xbrl_review"]["status"] == "PASS"
    assert {item["file_name"] for item in result["artifacts"]} >= {
        "preview.html",
        "workpaper.json",
        "validation_report.json",
        "mapping_report.json",
        "issue_report.json",
    }
    peer_manifest = workpaper["artifact_manifest"]["peer_artifacts"]
    assert {item["file_name"] for item in peer_manifest} == {
        item["file_name"] for item in manifest["artifacts"]
    } - {"workpaper.json"}
    for artifact in peer_manifest:
        path = output_dir / artifact["file_name"]
        assert xbrl_case._sha256_file(path) == artifact["sha256"]
        assert path.stat().st_size == artifact["size_bytes"]


def test_repeated_export_of_same_approval_is_byte_reproducible(
    tmp_path: Path,
) -> None:
    case = _approved_case(tmp_path)
    catalogue = tmp_path / "catalogue.json"
    _write_catalogue(catalogue, "a" * 64)
    first_output = tmp_path / "export-first"
    second_output = tmp_path / "export-second"

    case = xbrl_case.export_case(case, first_output, catalogue, "reviewer_1")
    xbrl_case.export_case(case, second_output, catalogue, "reviewer_2")

    assert _artifact_bytes_by_name(first_output) == _artifact_bytes_by_name(
        second_output
    )


def test_failed_export_leaves_no_partial_output_and_can_retry(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    case = _approved_case(tmp_path)
    catalogue = tmp_path / "catalogue.json"
    _write_catalogue(catalogue, "a" * 64)
    output = tmp_path / "retryable-export"
    original_mapping_report = xbrl_case._mapping_report

    def failing_mapping_report(*args: object, **kwargs: object) -> dict[str, object]:
        raise RuntimeError("workpaper interrupted")

    monkeypatch.setattr(xbrl_case, "_mapping_report", failing_mapping_report)
    with pytest.raises(RuntimeError, match="workpaper interrupted"):
        xbrl_case.export_case(case, output, catalogue, "reviewer_1")

    assert not output.exists()
    monkeypatch.setattr(xbrl_case, "_mapping_report", original_mapping_report)
    result = xbrl_case.export_case(case, output, catalogue, "reviewer_1")

    assert result["state"] == "EXPORTED"
    assert (output / "artifact_manifest.json").is_file()


def test_export_rejects_catalogue_that_differs_from_approved_review(
    tmp_path: Path,
) -> None:
    case = _approved_case(tmp_path)
    changed_catalogue = tmp_path / "changed-catalogue.json"
    _write_catalogue(changed_catalogue, "a" * 64)
    payload = json.loads(changed_catalogue.read_text(encoding="utf-8"))
    payload["entry_points"]["ABBREVIATED"] = "https://example.invalid/changed.xsd"
    changed_catalogue.write_text(json.dumps(payload), encoding="utf-8")
    output = tmp_path / "rejected-export"

    with pytest.raises(ValueError, match="differs from the approved review catalogue"):
        xbrl_case.export_case(case, output, changed_catalogue, "reviewer_1")

    assert not output.exists()


def test_export_rejects_tampered_reviewed_preview_bytes(tmp_path: Path) -> None:
    case = _approved_case(tmp_path)
    snapshot = case["approval"]["snapshot"]
    snapshot["preview"]["content_base64"] = "dGFtcGVyZWQ="
    case["approval"]["snapshot_hash"] = xbrl_case._sha256_bytes(
        xbrl_case._canonical_json(snapshot)
    )
    catalogue = tmp_path / "catalogue.json"
    _write_catalogue(catalogue, "a" * 64)
    output = tmp_path / "rejected-preview-export"

    with pytest.raises(ValueError, match="preview byte length"):
        xbrl_case.export_case(case, output, catalogue, "reviewer_1")

    assert not output.exists()


def test_export_rejects_bytes_that_differ_from_approved_candidate(
    tmp_path: Path,
) -> None:
    case = _approved_case(tmp_path)
    snapshot = case["approval"]["snapshot"]
    snapshot["xbrl_review"]["candidate_sha256"] = "0" * 64
    case["approval"]["snapshot_hash"] = xbrl_case._sha256_bytes(
        xbrl_case._canonical_json(snapshot)
    )
    catalogue = tmp_path / "catalogue.json"
    _write_catalogue(catalogue, "a" * 64)
    output = tmp_path / "rejected-candidate-export"

    with pytest.raises(ValueError, match="final XBRL bytes differ"):
        xbrl_case.export_case(case, output, catalogue, "reviewer_1")

    assert not output.exists()


def test_xbrl_renderer_emits_only_accepted_concept_bound_narrative(
    tmp_path: Path,
) -> None:
    case = _approved_case(tmp_path)
    snapshot = case["approval"]["snapshot"]
    snapshot["narrative_blocks"][0]["xbrl_concept"] = "itcc:NotesText"
    case["approval"]["snapshot_hash"] = xbrl_case._sha256_bytes(
        xbrl_case._canonical_json(snapshot)
    )
    catalogue = tmp_path / "catalogue.json"
    _write_catalogue(catalogue, "a" * 64)

    xml = xbrl_case.render_xbrl(case, catalogue)
    root = etree.fromstring(xml)
    narrative = root.find("{https://example.invalid/itcc}NotesText")

    assert narrative is not None
    assert narrative.text == snapshot["narrative_blocks"][0]["text"]
    assert narrative.get("{http://www.w3.org/XML/1998/namespace}lang") == "it"


def test_xbrl_renderer_emits_approved_english_narrative_language(
    tmp_path: Path,
) -> None:
    case = _approved_case(tmp_path)
    snapshot = case["approval"]["snapshot"]
    snapshot["output_language"] = "en"
    snapshot["narrative_blocks"] = [
        {**block, "language": "en"} for block in snapshot["narrative_blocks"]
    ]
    case["approval"]["snapshot_hash"] = xbrl_case._sha256_bytes(
        xbrl_case._canonical_json(snapshot)
    )
    catalogue = tmp_path / "catalogue.json"
    _write_catalogue(catalogue, "a" * 64)

    root = etree.fromstring(xbrl_case.render_xbrl(case, catalogue))
    narrative = root.find("{https://example.invalid/itcc}NotesText")

    assert narrative is not None
    assert narrative.get("{http://www.w3.org/XML/1998/namespace}lang") == "en"


def test_xbrl_renderer_builds_dimensional_context_and_permitted_nil_fact(
    tmp_path: Path,
) -> None:
    case = _approved_case(tmp_path)
    snapshot = case["approval"]["snapshot"]
    snapshot["taxonomy_facts"] = [
        {
            "fact_id": "regional_note",
            "xbrl_concept": "itcc:DimensionText",
            "period": "current_duration",
            "fact_type": "TEXT",
            "value": "Operatività italiana.",
            "status": "USER_CONFIRMED",
            "source_refs": ["fact_000001"],
            "derivation": None,
            "dimensions": {"itcc:RegionAxis": "itcc:ItalyMember"},
            "nil_reason": None,
        },
        {
            "fact_id": "optional_amount",
            "xbrl_concept": "itcc:OptionalAmount",
            "period": "current_instant",
            "fact_type": "NIL",
            "value": None,
            "status": "USER_CONFIRMED",
            "source_refs": [],
            "derivation": None,
            "dimensions": {},
            "nil_reason": "Taxonomy-permitted field is not applicable",
        },
    ]
    case["approval"]["snapshot_hash"] = xbrl_case._sha256_bytes(
        xbrl_case._canonical_json(snapshot)
    )
    catalogue = tmp_path / "catalogue-dimensional.json"
    _write_catalogue(catalogue, "a" * 64)

    root = etree.fromstring(xbrl_case.render_xbrl(case, catalogue))
    member = root.find(".//{http://xbrl.org/2006/xbrldi}explicitMember")
    text_fact = root.find("{https://example.invalid/itcc}DimensionText")
    nil_fact = root.find("{https://example.invalid/itcc}OptionalAmount")

    assert member is not None
    assert member.get("dimension") == "itcc:RegionAxis"
    assert member.text == "itcc:ItalyMember"
    assert text_fact is not None
    assert text_fact.get("contextRef").startswith("ctx_dim_")
    assert nil_fact is not None
    assert nil_fact.get("{http://www.w3.org/2001/XMLSchema-instance}nil") == "true"
    assert nil_fact.get("unitRef") == "EUR"


def test_xbrl_renderer_rejects_fact_period_incompatible_with_concept(
    tmp_path: Path,
) -> None:
    case = _approved_case(tmp_path)
    snapshot = case["approval"]["snapshot"]
    snapshot["taxonomy_facts"] = [
        {
            "fact_id": "wrong_period",
            "xbrl_concept": "itcc:OptionalAmount",
            "period": "current_duration",
            "fact_type": "MONETARY",
            "value": "10",
            "status": "USER_CONFIRMED",
            "source_refs": ["src_1"],
            "derivation": None,
            "dimensions": {},
            "nil_reason": None,
        }
    ]
    case["approval"]["snapshot_hash"] = xbrl_case._sha256_bytes(
        xbrl_case._canonical_json(snapshot)
    )
    catalogue = tmp_path / "catalogue-wrong-period.json"
    _write_catalogue(catalogue, "a" * 64)

    with pytest.raises(ValueError, match="period does not match concept period type"):
        xbrl_case.render_xbrl(case, catalogue)
