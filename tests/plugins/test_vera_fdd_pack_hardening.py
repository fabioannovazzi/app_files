from __future__ import annotations

import sys
from collections.abc import Callable
from copy import deepcopy
from pathlib import Path
from typing import Any

import pytest

ROOT = Path(__file__).resolve().parents[2]
MODULE_ROOT = ROOT / "plugins" / "_shared" / "vendor" / "modules"
if str(MODULE_ROOT) not in sys.path:
    sys.path.insert(0, str(MODULE_ROOT))

from vera_financial_analysis import (  # noqa: E402
    FDDContractError,
    build_fdd_metric_receipt,
    execute_fdd_case,
)

from tests.plugins.test_vera_fdd_machinery import (
    ARTIFACT_REF,
    PERIOD,
    _build_case,
    _capex_inputs,
    _context,
    _metric_map,
    _net_debt_inputs,
    _qoe_inputs,
    _working_capital_inputs,
)


def _nwc_inputs() -> dict[str, Any]:
    inputs = _working_capital_inputs()
    inputs["selected_target"]["economic_effect_id"] = "effect.nwc.target"
    return inputs


def _set_nested(
    value: dict[str, Any],
    path: tuple[str | int, ...],
    replacement: str,
) -> None:
    current: Any = value
    for part in path[:-1]:
        current = current[part]
    current[path[-1]] = replacement


def _included_adjustment(
    *,
    adjustment_id: str,
    economic_effect_id: str,
    amount: str,
    included: bool,
) -> dict[str, Any]:
    return {
        "adjustment_id": adjustment_id,
        "economic_effect_id": economic_effect_id,
        "description": f"Reviewed adjustment {adjustment_id}.",
        "category_id": "category.reviewed",
        "period_start": PERIOD["start"],
        "period_end": PERIOD["end"],
        "ebitda_impact": amount,
        "included": included,
        "decision_ref": "decision.synthetic",
        "cash_effect": "not_assessed",
        "evidence_refs": [ARTIFACT_REF],
    }


def _net_debt_item(
    *,
    item_id: str,
    classification: str,
    amount: str,
    included: bool,
) -> dict[str, Any]:
    return {
        "item_id": item_id,
        "economic_effect_id": f"effect.{item_id}",
        "description": f"Reviewed net-debt item {item_id}.",
        "as_of_date": PERIOD["end"],
        "classification": classification,
        "amount": amount,
        "included": included,
        "decision_ref": "decision.synthetic",
        "evidence_refs": [ARTIFACT_REF],
    }


def _capex_item(
    *,
    capex_id: str,
    measurement_basis: str,
    classification: str,
    amount: str,
    included: bool = True,
) -> dict[str, Any]:
    return {
        "capex_id": capex_id,
        "economic_effect_id": f"effect.{capex_id}",
        "period": "2025",
        "period_start": PERIOD["start"],
        "period_end": PERIOD["end"],
        "description": f"Reviewed Capex item {capex_id}.",
        "measurement_basis": measurement_basis,
        "classification": classification,
        "amount": amount,
        "included": included,
        "decision_ref": "decision.synthetic",
        "evidence_refs": [ARTIFACT_REF],
    }


def _duplicate_qoe_effect(inputs: dict[str, Any]) -> None:
    duplicate = deepcopy(inputs["adjustments"][0])
    duplicate["adjustment_id"] = "adjustment.duplicate"
    inputs["adjustments"].append(duplicate)


def _duplicate_net_debt_effect(inputs: dict[str, Any]) -> None:
    duplicate = deepcopy(inputs["items"][0])
    duplicate["item_id"] = "item.duplicate"
    inputs["items"].append(duplicate)


def _duplicate_nwc_effect(inputs: dict[str, Any]) -> None:
    inputs["selected_target"]["economic_effect_id"] = "effect.nwc"


def _duplicate_capex_effect(inputs: dict[str, Any]) -> None:
    duplicate = deepcopy(inputs["items"][0])
    duplicate["capex_id"] = "capex.duplicate"
    inputs["items"].append(duplicate)


def _qoe_outside_period(inputs: dict[str, Any]) -> None:
    inputs["adjustments"][0]["period_start"] = "2024-12-31"


def _net_debt_outside_period(inputs: dict[str, Any]) -> None:
    inputs["as_of_date"] = "2024-12-31"
    for item in inputs["items"]:
        item["as_of_date"] = "2024-12-31"


def _nwc_closing_date_mismatch(inputs: dict[str, Any]) -> None:
    inputs["monthly_balances"][1]["period_end"] = "2025-12-30"


def _capex_outside_period(inputs: dict[str, Any]) -> None:
    inputs["items"][0]["period_start"] = "2024-12-31"


def _deal_bridge_inputs(
    context: dict[str, Any],
) -> tuple[dict[str, Any], dict[str, dict[str, Any]]]:
    qoe_case = _build_case(
        context,
        pack_id="quality_of_earnings",
        inputs=_qoe_inputs(),
    )
    qoe_result = execute_fdd_case(qoe_case)
    adjusted_receipt = build_fdd_metric_receipt(
        qoe_case,
        qoe_result,
        "adjusted_ebitda",
    )
    reported_receipt = build_fdd_metric_receipt(
        qoe_case,
        qoe_result,
        "reported_ebitda",
    )
    nwc_case = _build_case(
        context,
        pack_id="normalized_working_capital",
        inputs=_nwc_inputs(),
    )
    nwc_result = execute_fdd_case(nwc_case)
    nwc_receipt = build_fdd_metric_receipt(
        nwc_case,
        nwc_result,
        "closing_vs_target_adjustment",
    )
    inputs = {
        "upstream_metrics": [adjusted_receipt, nwc_receipt],
        "adjusted_ebitda_ref": adjusted_receipt["receipt_id"],
        "enterprise_value": {
            "amount": "5000",
            "decision_ref": "decision.synthetic",
            "evidence_refs": [ARTIFACT_REF],
        },
        "cash_bridge_items": [
            {
                "bridge_item_id": "bridge.cash.nwc",
                "description": "Reviewed working-capital bridge item.",
                "category_id": "category.nwc",
                "economic_effect_refs": nwc_receipt["economic_effect_refs"],
                "cash_flow_impact": nwc_receipt["value"],
                "included": True,
                "decision_ref": "decision.synthetic",
                "evidence_refs": [ARTIFACT_REF],
                "upstream_metric_ref": nwc_receipt["receipt_id"],
                "upstream_multiplier": "1",
            },
            {
                "bridge_item_id": "bridge.cash.excluded",
                "description": "Reviewed excluded bridge item.",
                "category_id": "category.excluded",
                "economic_effect_refs": [],
                "cash_flow_impact": "999",
                "included": False,
                "decision_ref": "decision.synthetic",
                "evidence_refs": [ARTIFACT_REF],
                "upstream_metric_ref": None,
                "upstream_multiplier": None,
            },
        ],
        "equity_bridge_items": [
            {
                "bridge_item_id": "bridge.equity.standalone",
                "description": "Reviewed standalone equity adjustment.",
                "category_id": "category.other",
                "economic_effect_refs": ["effect.equity.standalone"],
                "equity_value_impact": "-100",
                "included": True,
                "decision_ref": "decision.synthetic",
                "evidence_refs": [ARTIFACT_REF],
                "upstream_metric_ref": None,
                "upstream_multiplier": None,
            }
        ],
    }
    return inputs, {
        "adjusted": adjusted_receipt,
        "reported": reported_receipt,
        "nwc": nwc_receipt,
    }


def _bridge_unknown_adjusted(
    inputs: dict[str, Any],
    _receipts: dict[str, dict[str, Any]],
) -> None:
    inputs["adjusted_ebitda_ref"] = "receipt.unknown"


def _bridge_wrong_adjusted_metric(
    inputs: dict[str, Any],
    receipts: dict[str, dict[str, Any]],
) -> None:
    inputs["upstream_metrics"].append(receipts["reported"])
    inputs["adjusted_ebitda_ref"] = receipts["reported"]["receipt_id"]


def _bridge_wrong_adjusted_pack(
    inputs: dict[str, Any],
    receipts: dict[str, dict[str, Any]],
) -> None:
    inputs["adjusted_ebitda_ref"] = receipts["nwc"]["receipt_id"]


def _bridge_unknown_upstream(
    inputs: dict[str, Any],
    _receipts: dict[str, dict[str, Any]],
) -> None:
    inputs["cash_bridge_items"][0]["upstream_metric_ref"] = "receipt.unknown"


def _bridge_half_paired_upstream(
    inputs: dict[str, Any],
    _receipts: dict[str, dict[str, Any]],
) -> None:
    inputs["cash_bridge_items"][0]["upstream_multiplier"] = None


def _bridge_invalid_multiplier(
    inputs: dict[str, Any],
    _receipts: dict[str, dict[str, Any]],
) -> None:
    inputs["cash_bridge_items"][0]["upstream_multiplier"] = "2"


def _bridge_amount_mismatch(
    inputs: dict[str, Any],
    _receipts: dict[str, dict[str, Any]],
) -> None:
    inputs["cash_bridge_items"][0]["cash_flow_impact"] = "999"


def _bridge_effect_mismatch(
    inputs: dict[str, Any],
    _receipts: dict[str, dict[str, Any]],
) -> None:
    inputs["cash_bridge_items"][0]["economic_effect_refs"] = ["effect.other"]


def _bridge_duplicate_effect(
    inputs: dict[str, Any],
    _receipts: dict[str, dict[str, Any]],
) -> None:
    duplicate = deepcopy(inputs["cash_bridge_items"][0])
    duplicate["bridge_item_id"] = "bridge.cash.duplicate"
    inputs["cash_bridge_items"].append(duplicate)


def test_quality_of_earnings_uses_signed_adjustments_and_typed_provenance(
    tmp_path: Path,
) -> None:
    context = _context(tmp_path)
    inputs = _qoe_inputs()
    inputs["adjustments"].extend(
        [
            _included_adjustment(
                adjustment_id="adjustment.negative",
                economic_effect_id="effect.ebitda.negative",
                amount="-25",
                included=True,
            ),
            _included_adjustment(
                adjustment_id="adjustment.not_included",
                economic_effect_id="effect.ebitda.not_included",
                amount="500",
                included=False,
            ),
        ]
    )
    case = _build_case(context, pack_id="quality_of_earnings", inputs=inputs)

    result = execute_fdd_case(case)

    assert _metric_map(result) == {
        "reported_ebitda": "1000",
        "included_adjustments": "75",
        "adjusted_ebitda": "1075",
    }
    assert [item["line_type"] for item in result["line_items"]] == [
        "reported_ebitda_base",
        "adjustment",
        "adjustment",
        "adjustment",
    ]
    assert result["line_items"][0] == {
        "line_type": "reported_ebitda_base",
        "amount": "1000",
        "evidence_refs": [ARTIFACT_REF],
    }
    adjusted_metric = next(
        item for item in result["metrics"] if item["metric_id"] == "adjusted_ebitda"
    )
    assert adjusted_metric["economic_effect_refs"] == [
        "effect.ebitda.negative",
        "effect.ebitda.one",
    ]


def test_net_debt_oracle_covers_liquidity_debt_and_excluded_rows(
    tmp_path: Path,
) -> None:
    context = _context(tmp_path)
    inputs = _net_debt_inputs()
    inputs["items"].extend(
        [
            _net_debt_item(
                item_id="cash_like",
                classification="cash_like",
                amount="25",
                included=True,
            ),
            _net_debt_item(
                item_id="excluded",
                classification="excluded",
                amount="999",
                included=False,
            ),
            _net_debt_item(
                item_id="inactive_debt",
                classification="debt",
                amount="1000",
                included=False,
            ),
        ]
    )
    case = _build_case(context, pack_id="net_debt", inputs=inputs)

    result = execute_fdd_case(case)

    assert _metric_map(result) == {
        "cash": "100",
        "cash_like": "25",
        "debt": "500",
        "debt_like": "50",
        "gross_debt_and_debt_like": "550",
        "net_debt": "425",
    }
    net_debt_metric = next(
        item for item in result["metrics"] if item["metric_id"] == "net_debt"
    )
    assert net_debt_metric["economic_effect_refs"] == [
        "effect.cash",
        "effect.cash_like",
        "effect.debt",
        "effect.debt_like",
    ]


def test_net_debt_can_report_a_net_cash_position(tmp_path: Path) -> None:
    context = _context(tmp_path)
    inputs = {
        "as_of_date": PERIOD["end"],
        "items": [
            _net_debt_item(
                item_id="cash_only",
                classification="cash",
                amount="100",
                included=True,
            ),
            _net_debt_item(
                item_id="small_debt",
                classification="debt",
                amount="20",
                included=True,
            ),
        ],
    }
    case = _build_case(context, pack_id="net_debt", inputs=inputs)

    result = execute_fdd_case(case)

    assert _metric_map(result)["net_debt"] == "-80"


@pytest.mark.parametrize(
    ("pack_id", "inputs_factory"),
    [
        ("net_debt", _net_debt_inputs),
        ("capex", _capex_inputs),
    ],
)
def test_included_excluded_classification_is_rejected(
    tmp_path: Path,
    pack_id: str,
    inputs_factory: Callable[[], dict[str, Any]],
) -> None:
    context = _context(tmp_path)
    inputs = inputs_factory()
    inputs["items"][0]["classification"] = "excluded"

    with pytest.raises(
        FDDContractError,
        match="included must be false when classification is excluded",
    ):
        _build_case(context, pack_id=pack_id, inputs=inputs)


@pytest.mark.parametrize(
    ("pack_id", "inputs_factory"),
    [
        ("net_debt", _net_debt_inputs),
        ("capex", _capex_inputs),
    ],
)
def test_unsigned_packs_reject_negative_amounts(
    tmp_path: Path,
    pack_id: str,
    inputs_factory: Callable[[], dict[str, Any]],
) -> None:
    context = _context(tmp_path)
    inputs = inputs_factory()
    inputs["items"][0]["amount"] = "-1"

    with pytest.raises(FDDContractError, match="must be non-negative"):
        _build_case(context, pack_id=pack_id, inputs=inputs)


@pytest.mark.parametrize(
    ("first_balance", "closing_balance", "expected_average"),
    [
        ("0", "1", "1"),
        ("-1", "0", "-1"),
    ],
)
def test_nwc_average_rounds_half_up_for_positive_and_negative_ties(
    tmp_path: Path,
    first_balance: str,
    closing_balance: str,
    expected_average: str,
) -> None:
    context = _context(tmp_path)
    inputs = _nwc_inputs()
    inputs["average_scale"] = 0
    inputs["monthly_balances"][0]["reported_operating_nwc"] = first_balance
    inputs["monthly_balances"][1]["reported_operating_nwc"] = closing_balance
    inputs["normalization_adjustments"] = []
    inputs["selected_target"]["amount"] = "0"
    case = _build_case(
        context,
        pack_id="normalized_working_capital",
        inputs=inputs,
    )

    result = execute_fdd_case(case)

    assert _metric_map(result)["candidate_average_normalized_nwc"] == expected_average
    assert result["calculation_policy"]["average_rounding"] == "half_up"


def test_nwc_preserves_typed_adjustment_and_target_provenance(
    tmp_path: Path,
) -> None:
    context = _context(tmp_path)
    case = _build_case(
        context,
        pack_id="normalized_working_capital",
        inputs=_nwc_inputs(),
    )

    result = execute_fdd_case(case)

    assert _metric_map(result) == {
        "candidate_average_normalized_nwc": "115",
        "selected_target_nwc": "105",
        "closing_normalized_nwc": "130",
        "closing_vs_target_adjustment": "25",
    }
    assert [item["line_type"] for item in result["line_items"]] == [
        "monthly_balance",
        "monthly_balance",
        "normalization_adjustment",
        "selected_target",
    ]
    adjustment_line = next(
        item
        for item in result["line_items"]
        if item["line_type"] == "normalization_adjustment"
    )
    assert adjustment_line["economic_effect_id"] == "effect.nwc"
    assert adjustment_line["decision_ref"] == "decision.synthetic"
    assert adjustment_line["evidence_refs"] == [ARTIFACT_REF]
    target_line = next(
        item for item in result["line_items"] if item["line_type"] == "selected_target"
    )
    assert target_line["economic_effect_id"] == "effect.nwc.target"
    assert target_line["decision_ref"] == "decision.synthetic"
    assert target_line["evidence_refs"] == [ARTIFACT_REF]
    metric_effects = {
        effect
        for metric in result["metrics"]
        for effect in metric["economic_effect_refs"]
    }
    line_effects = {
        item["economic_effect_id"]
        for item in result["line_items"]
        if "economic_effect_id" in item
    }
    assert metric_effects <= line_effects
    assert next(
        item for item in result["metrics"] if item["metric_id"] == "selected_target_nwc"
    )["economic_effect_refs"] == ["effect.nwc.target"]
    assert next(
        item
        for item in result["metrics"]
        if item["metric_id"] == "closing_vs_target_adjustment"
    )["economic_effect_refs"] == ["effect.nwc", "effect.nwc.target"]


def test_nwc_target_only_receipt_can_feed_a_reviewed_bridge(tmp_path: Path) -> None:
    context = _context(tmp_path)
    qoe_case = _build_case(
        context,
        pack_id="quality_of_earnings",
        inputs=_qoe_inputs(),
    )
    qoe_result = execute_fdd_case(qoe_case)
    qoe_receipt = build_fdd_metric_receipt(
        qoe_case,
        qoe_result,
        "adjusted_ebitda",
    )
    nwc_inputs = _nwc_inputs()
    nwc_inputs["normalization_adjustments"] = []
    nwc_case = _build_case(
        context,
        pack_id="normalized_working_capital",
        inputs=nwc_inputs,
    )
    nwc_result = execute_fdd_case(nwc_case)
    nwc_receipt = build_fdd_metric_receipt(
        nwc_case,
        nwc_result,
        "closing_vs_target_adjustment",
    )
    deal_case = _build_case(
        context,
        pack_id="deal_bridges",
        inputs={
            "upstream_metrics": [qoe_receipt, nwc_receipt],
            "adjusted_ebitda_ref": qoe_receipt["receipt_id"],
            "enterprise_value": {
                "amount": "5000",
                "decision_ref": "decision.synthetic",
                "evidence_refs": [ARTIFACT_REF],
            },
            "cash_bridge_items": [
                {
                    "bridge_item_id": "bridge.cash.nwc",
                    "description": "Target-only working-capital effect.",
                    "category_id": "category.nwc",
                    "economic_effect_refs": nwc_receipt["economic_effect_refs"],
                    "cash_flow_impact": "-15",
                    "included": True,
                    "decision_ref": "decision.synthetic",
                    "evidence_refs": [ARTIFACT_REF],
                    "upstream_metric_ref": nwc_receipt["receipt_id"],
                    "upstream_multiplier": "-1",
                }
            ],
            "equity_bridge_items": [],
        },
    )

    result = execute_fdd_case(deal_case)

    assert nwc_receipt["value"] == "15"
    assert nwc_receipt["economic_effect_refs"] == ["effect.nwc.target"]
    assert _metric_map(result)["cash_bridge_result"] == "1085"
    assert next(
        item
        for item in result["line_items"]
        if item.get("line_type") == "enterprise_value_base"
    ) == {
        "line_type": "enterprise_value_base",
        "bridge": "enterprise_to_equity",
        "amount": "5000",
        "decision_ref": "decision.synthetic",
        "evidence_refs": [ARTIFACT_REF],
    }


def test_deal_bridges_accept_reviewed_excluded_and_standalone_rows(
    tmp_path: Path,
) -> None:
    context = _context(tmp_path)
    inputs, _ = _deal_bridge_inputs(context)
    case = _build_case(context, pack_id="deal_bridges", inputs=inputs)

    result = execute_fdd_case(case)

    assert _metric_map(result)["cash_bridge_result"] == "1125"
    assert _metric_map(result)["equity_value"] == "4900"
    assert (
        next(
            item
            for item in result["line_items"]
            if item.get("bridge_item_id") == "bridge.cash.excluded"
        )["included"]
        is False
    )
    assert (
        next(
            item
            for item in result["line_items"]
            if item.get("bridge_item_id") == "bridge.equity.standalone"
        )["upstream_metric_ref"]
        is None
    )


@pytest.mark.parametrize(
    ("mutate", "message"),
    [
        (_bridge_unknown_adjusted, "not in upstream_metrics"),
        (
            _bridge_wrong_adjusted_metric,
            "must identify a Quality of Earnings adjusted_ebitda metric",
        ),
        (
            _bridge_wrong_adjusted_pack,
            "must identify a Quality of Earnings adjusted_ebitda metric",
        ),
        (_bridge_unknown_upstream, "upstream_metric_ref is unknown"),
        (_bridge_half_paired_upstream, "reference and multiplier must be paired"),
        (_bridge_invalid_multiplier, "upstream_multiplier must be -1 or 1"),
        (_bridge_amount_mismatch, "does not match its upstream metric"),
        (_bridge_effect_mismatch, "economic_effect_refs do not match upstream"),
        (_bridge_duplicate_effect, "included by both"),
    ],
)
def test_deal_bridge_upstream_contracts_fail_closed(
    tmp_path: Path,
    mutate: Callable[
        [dict[str, Any], dict[str, dict[str, Any]]],
        None,
    ],
    message: str,
) -> None:
    context = _context(tmp_path)
    inputs, receipts = _deal_bridge_inputs(context)
    mutate(inputs, receipts)

    with pytest.raises(FDDContractError, match=message):
        _build_case(context, pack_id="deal_bridges", inputs=inputs)


def test_capex_oracle_covers_every_basis_and_classification(
    tmp_path: Path,
) -> None:
    context = _context(tmp_path)
    inputs = {
        "items": [
            _capex_item(
                capex_id="capex.asset_growth",
                measurement_basis="asset_addition",
                classification="growth",
                amount="20",
            ),
            _capex_item(
                capex_id="capex.capitalized_mixed",
                measurement_basis="capitalized_amount",
                classification="mixed",
                amount="30",
            ),
            _capex_item(
                capex_id="capex.cash_growth",
                measurement_basis="cash_paid",
                classification="growth",
                amount="5",
            ),
            _capex_item(
                capex_id="capex.cash_maintenance",
                measurement_basis="cash_paid",
                classification="maintenance",
                amount="10",
            ),
            _capex_item(
                capex_id="capex.disposal_unclassified",
                measurement_basis="disposal_proceeds",
                classification="unclassified",
                amount="40",
            ),
            _capex_item(
                capex_id="capex.excluded",
                measurement_basis="cash_paid",
                classification="excluded",
                amount="999",
                included=False,
            ),
        ]
    }
    case = _build_case(context, pack_id="capex", inputs=inputs)

    result = execute_fdd_case(case)

    assert _metric_map(result) == {
        "capex.asset_addition.total": "20",
        "capex.capitalized_amount.total": "30",
        "capex.cash_paid.total": "15",
        "capex.disposal_proceeds.total": "40",
        "capex.asset_addition.growth": "20",
        "capex.capitalized_amount.mixed": "30",
        "capex.cash_paid.growth": "5",
        "capex.cash_paid.maintenance": "10",
        "capex.disposal_proceeds.unclassified": "40",
    }
    assert all("excluded" not in metric["metric_id"] for metric in result["metrics"])


@pytest.mark.parametrize(
    ("pack_id", "inputs_factory", "mutate"),
    [
        ("quality_of_earnings", _qoe_inputs, _duplicate_qoe_effect),
        ("net_debt", _net_debt_inputs, _duplicate_net_debt_effect),
        ("normalized_working_capital", _nwc_inputs, _duplicate_nwc_effect),
        ("capex", _capex_inputs, _duplicate_capex_effect),
    ],
)
def test_pack_economic_effects_must_be_unique(
    tmp_path: Path,
    pack_id: str,
    inputs_factory: Callable[[], dict[str, Any]],
    mutate: Callable[[dict[str, Any]], None],
) -> None:
    context = _context(tmp_path)
    inputs = inputs_factory()
    mutate(inputs)

    with pytest.raises(FDDContractError, match="economic effect|economic_effect_id"):
        _build_case(context, pack_id=pack_id, inputs=inputs)


@pytest.mark.parametrize(
    ("pack_id", "inputs_factory", "mutate", "message"),
    [
        (
            "quality_of_earnings",
            _qoe_inputs,
            _qoe_outside_period,
            "outside the reporting period",
        ),
        (
            "net_debt",
            _net_debt_inputs,
            _net_debt_outside_period,
            "outside the reporting period",
        ),
        (
            "normalized_working_capital",
            _nwc_inputs,
            _nwc_closing_date_mismatch,
            "must end on the reporting end date",
        ),
        (
            "capex",
            _capex_inputs,
            _capex_outside_period,
            "outside the reporting period",
        ),
    ],
)
def test_pack_dates_must_close_to_the_case_period(
    tmp_path: Path,
    pack_id: str,
    inputs_factory: Callable[[], dict[str, Any]],
    mutate: Callable[[dict[str, Any]], None],
    message: str,
) -> None:
    context = _context(tmp_path)
    inputs = inputs_factory()
    mutate(inputs)

    with pytest.raises(FDDContractError, match=message):
        _build_case(context, pack_id=pack_id, inputs=inputs)


@pytest.mark.parametrize(
    ("pack_id", "inputs_factory", "amount_path"),
    [
        (
            "quality_of_earnings",
            _qoe_inputs,
            ("reported_ebitda", "amount"),
        ),
        ("net_debt", _net_debt_inputs, ("items", 0, "amount")),
        (
            "normalized_working_capital",
            _nwc_inputs,
            ("selected_target", "amount"),
        ),
        ("capex", _capex_inputs, ("items", 0, "amount")),
    ],
)
@pytest.mark.parametrize(
    ("invalid_amount", "message"),
    [
        ("111111111111111111111111111111111111111", "at most 38 digits"),
        ("0.0000001", "at most 6 decimal places"),
    ],
)
def test_fixed_pack_numeric_bounds_fail_closed(
    tmp_path: Path,
    pack_id: str,
    inputs_factory: Callable[[], dict[str, Any]],
    amount_path: tuple[str | int, ...],
    invalid_amount: str,
    message: str,
) -> None:
    context = _context(tmp_path)
    inputs = inputs_factory()
    _set_nested(inputs, amount_path, invalid_amount)

    with pytest.raises(FDDContractError, match=message):
        _build_case(context, pack_id=pack_id, inputs=inputs)


@pytest.mark.parametrize(
    ("reported", "adjustment", "expected"),
    [
        (
            "99999999999999999999999999999999999999",
            "0",
            "99999999999999999999999999999999999999",
        ),
        ("0", "0.000001", "0.000001"),
    ],
)
def test_fixed_pack_numeric_boundaries_are_accepted(
    tmp_path: Path,
    reported: str,
    adjustment: str,
    expected: str,
) -> None:
    context = _context(tmp_path)
    case = _build_case(
        context,
        pack_id="quality_of_earnings",
        inputs=_qoe_inputs(reported=reported, adjustment=adjustment),
    )

    result = execute_fdd_case(case)

    assert _metric_map(result)["adjusted_ebitda"] == expected


def test_fixed_pack_aggregate_outside_numeric_domain_fails_closed(
    tmp_path: Path,
) -> None:
    context = _context(tmp_path)
    case = _build_case(
        context,
        pack_id="quality_of_earnings",
        inputs=_qoe_inputs(
            reported="99999999999999999999999999999999999999",
            adjustment="1",
        ),
    )

    with pytest.raises(FDDContractError, match="at most 38 digits"):
        execute_fdd_case(case)


def test_result_and_metric_receipt_ids_include_case_freshness(
    tmp_path: Path,
) -> None:
    context = _context(tmp_path)
    first_case = _build_case(
        context,
        pack_id="quality_of_earnings",
        inputs=_qoe_inputs(reported="1000"),
    )
    second_case = _build_case(
        context,
        pack_id="quality_of_earnings",
        inputs=_qoe_inputs(reported="1001"),
    )

    first_result = execute_fdd_case(first_case)
    second_result = execute_fdd_case(second_case)
    first_receipt = build_fdd_metric_receipt(
        first_case,
        first_result,
        "adjusted_ebitda",
    )
    second_receipt = build_fdd_metric_receipt(
        second_case,
        second_result,
        "adjusted_ebitda",
    )

    assert first_result["engine_version"] == "1.1.0"
    assert first_result["result_id"] == (
        f"{first_case['case_id']}.quality_of_earnings."
        f"{first_case['content_sha256']}.result"
    )
    assert second_result["result_id"] == (
        f"{second_case['case_id']}.quality_of_earnings."
        f"{second_case['content_sha256']}.result"
    )
    assert first_result["result_id"] != second_result["result_id"]
    assert first_receipt["receipt_id"] != second_receipt["receipt_id"]
    assert first_receipt["receipt_id"] == (
        f"{first_result['result_id']}.adjusted_ebitda"
    )
