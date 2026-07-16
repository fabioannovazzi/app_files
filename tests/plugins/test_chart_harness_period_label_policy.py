from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SHARED_VENDOR_ROOT = ROOT / "plugins" / "_shared" / "vendor"
if str(SHARED_VENDOR_ROOT) not in sys.path:
    sys.path.insert(0, str(SHARED_VENDOR_ROOT))

from modules.chart_harness import (  # noqa: E402
    reporting_period_line_from_recipe,
    validate_period_label_policy,
)


def _month_pair_window() -> dict[str, object]:
    return {
        "mode": "explicit_comparison_periods",
        "baseline": {
            "label": "PY",
            "period_label": "2025-08",
            "start_date": "2025-08-01",
            "end_date": "2025-08-31",
        },
        "comparison": {
            "label": "AC",
            "period_label": "2025-09",
            "start_date": "2025-09-01",
            "end_date": "2025-09-30",
        },
    }


def test_policy_rejects_ac_vs_py_without_resolved_period_context() -> None:
    context = {
        "chart_title_lines": ["Company", "Sales", "AC vs PY"],
        "title_contract": {"who": "Company", "what": "Sales", "when": "AC vs PY"},
        "selected_periods": ["PY", "AC"],
    }

    status = validate_period_label_policy(context)

    assert status["status"] == "period_label_policy_failed"
    assert {issue["code"] for issue in status["issues"]} == {
        "scenario_periods_without_resolved_period_context",
        "scenario_labels_without_resolved_period_context",
    }


def test_policy_accepts_scenario_labels_with_resolved_period_window() -> None:
    context = {
        "chart_title_lines": ["Company", "Sales", "AC vs PY"],
        "title_contract": {"who": "Company", "what": "Sales", "when": "AC vs PY"},
        "selected_periods": ["PY", "AC"],
        "period_window": _month_pair_window(),
    }

    status = validate_period_label_policy(context)

    assert status["status"] == "period_label_policy_ok"
    assert status["resolved_period_context"] is True


def test_policy_rejects_same_period_comparison_even_with_context() -> None:
    context = {
        "chart_title_lines": ["Company", "Sales", "AC to AC"],
        "selected_periods": ["PY", "AC"],
        "period_window": _month_pair_window(),
    }

    status = validate_period_label_policy(context)

    assert status["status"] == "period_label_policy_failed"
    assert status["issues"][0]["code"] == "same_period_comparison_label"


def test_policy_accepts_single_actual_when_resolved_to_period() -> None:
    context = {
        "chart_title_lines": ["Company", "Sales", "AC"],
        "selected_periods": ["AC"],
        "period_window": {"current": _month_pair_window()["comparison"]},
    }

    status = validate_period_label_policy(context)

    assert status["status"] == "period_label_policy_ok"


def test_policy_does_not_match_scenario_inside_longer_word() -> None:
    context = {
        "chart_title_lines": ["Company", "Sales", "Actualization analysis"],
    }

    status = validate_period_label_policy(context)

    assert status["status"] == "period_label_policy_not_applicable"
    assert status["scenario_tokens"] == []


def test_policy_accepts_statement_periods_with_scenario_mapping() -> None:
    context = {
        "chart_title_lines": ["P&L", "Sales in mEUR", "FY2025"],
        "periods": ["FY2024", "FY2025"],
        "scenarios_by_period": {"FY2025": ["AC"], "FY2024": ["PY"]},
    }

    status = validate_period_label_policy(context)

    assert status["status"] == "period_label_policy_ok"


def test_reporting_period_line_resolves_scenario_comparison_window() -> None:
    recipe = {"options": {"period_window": _month_pair_window()}}

    label = reporting_period_line_from_recipe(
        recipe,
        current_label="AC",
        previous_label="PY",
    )

    assert label == "AC vs PY, 2025-09 vs 2025-08"


def test_reporting_period_line_uses_period_only_for_single_actual() -> None:
    recipe = {
        "options": {"period_window": {"current": _month_pair_window()["comparison"]}}
    }

    label = reporting_period_line_from_recipe(
        recipe,
        current_label="AC",
        previous_label=None,
    )

    assert label == "2025-09"


def test_reporting_period_line_adds_ytd_cutoff_for_comparison() -> None:
    recipe = {
        "options": {
            "period_comparison_mode": "year_to_date",
            "period_window": {
                "current": {
                    "label": "AC",
                    "start_date": "2025-01-01",
                    "end_date": "2025-09-30",
                },
                "previous": {
                    "label": "PY",
                    "start_date": "2024-01-01",
                    "end_date": "2024-09-30",
                },
            },
        }
    }

    label = reporting_period_line_from_recipe(
        recipe,
        current_label="AC",
        previous_label="PY",
    )

    assert label == "AC vs PY, YTD through 2025-09-30"


def test_reporting_period_line_treats_period_type_to_date_as_cutoff() -> None:
    recipe = {
        "options": {
            "period_comparison_mode": "previous_year",
            "period_window": {
                "current": {
                    "label": "AC",
                    "start_date": "2025-01-01",
                    "end_date": "2025-09-01",
                },
                "previous": {
                    "label": "PY",
                    "start_date": "2024-01-01",
                    "end_date": "2024-09-01",
                },
                "period_type": "to_date",
            },
        }
    }

    label = reporting_period_line_from_recipe(
        recipe,
        current_label="AC",
        previous_label="PY",
    )

    assert label == "AC vs PY, YTD through 2025-09-01"


def test_reporting_period_line_preserves_rolling_window_months() -> None:
    recipe = {
        "options": {
            "period_comparison_mode": "rolling_period",
            "period_window": {"rolling_window_months": 12},
        }
    }

    label = reporting_period_line_from_recipe(
        recipe,
        current_label="~Jun-2019",
        previous_label="~Jun-2018",
    )

    assert label == "~Jun-2019 vs ~Jun-2018, rolling 12 months"
