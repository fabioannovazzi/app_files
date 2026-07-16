from __future__ import annotations

import json
import sys
from pathlib import Path

SCRIPTS_DIR = Path(__file__).resolve().parents[2] / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

from scripts import run_chart_manifest_adversarial_proof as proof


def _write_context(path: Path, payload: dict[str, object]) -> dict[str, str]:
    path.write_text(json.dumps(payload), encoding="utf-8")
    return {"status": "context_written", "path": str(path)}


def test_chart_identity_rejects_context_artifact_as_chart_id(tmp_path: Path) -> None:
    context_status = _write_context(
        tmp_path / "exploded_variance_bridge_context.json",
        {
            "chart_type": "exploded_variance_bridge",
            "capability_id": "variance.exploded_variance_bridge",
        },
    )
    test_case = {
        "capability_id": "variance.exploded_variance_bridge",
        "plugin_chart": "exploded_variance_bridge_context",
        "expected_context_chart_type": "exploded_variance_bridge",
    }

    status = proof._chart_identity_status(test_case, context_status)

    assert status["status"] == "chart_id_is_context_artifact"


def test_chart_identity_accepts_chart_id_with_context_sidecar(
    tmp_path: Path,
) -> None:
    context_status = _write_context(
        tmp_path / "exploded_variance_bridge_context.json",
        {
            "chart_type": "exploded_variance_bridge",
            "analysis_type": "exploded_variance_bridge",
            "capability_id": "variance.exploded_variance_bridge",
        },
    )
    test_case = {
        "capability_id": "variance.exploded_variance_bridge",
        "plugin_chart": "exploded_variance_bridge",
        "verification_artifact": "exploded_variance_bridge_context",
        "expected_context_chart_type": "exploded_variance_bridge",
    }

    status = proof._chart_identity_status(test_case, context_status)

    assert status["status"] == "chart_identity_ok"
    assert status["chart_id"] == "exploded_variance_bridge"


def test_chart_identity_rejects_context_chart_type_mismatch(
    tmp_path: Path,
) -> None:
    context_status = _write_context(
        tmp_path / "exploded_variance_bridge_context.json",
        {
            "chart_type": "root_cause_total_bridge",
            "capability_id": "variance.exploded_variance_bridge",
        },
    )
    test_case = {
        "capability_id": "variance.exploded_variance_bridge",
        "plugin_chart": "exploded_variance_bridge",
        "expected_context_chart_type": "exploded_variance_bridge",
    }

    status = proof._chart_identity_status(test_case, context_status)

    assert status["status"] == "context_chart_identity_mismatch"
    assert status["observed_chart_identities"] == ["root_cause_total_bridge"]


def test_chart_identity_accepts_generic_chart_context_field(
    tmp_path: Path,
) -> None:
    context_status = _write_context(
        tmp_path / "stacked_column_chart_context.json",
        {"chart": "stacked_column", "legacy_chart": "stacked column"},
    )
    test_case = {
        "capability_id": "mix.stacked_column",
        "plugin_chart": "stacked_column",
    }

    status = proof._chart_identity_status(test_case, context_status)

    assert status["status"] == "chart_identity_ok"
    assert status["observed_chart_identities"] == ["stacked_column"]


def test_period_axis_contract_rejects_ac_to_ac_context(tmp_path: Path) -> None:
    context_status = _write_context(
        tmp_path / "column_total_chart_context.json",
        {
            "chart": "column_total",
            "selected_periods": ["AC"],
            "period_grain": "month",
            "chart_title_lines": ["AC to AC"],
        },
    )
    test_case = {
        "capability_id": "mix.column",
        "plugin_chart": "column_total",
        "expected_context_period_axis": {
            "minimum_distinct_periods": 2,
            "required_period_grain": "month",
            "forbid_same_period_title": True,
            "forbid_bare_ac_period": True,
        },
    }

    status = proof._chart_identity_status(test_case, context_status)

    assert status["status"] == "context_period_axis_too_few_periods"
    assert status["observed_periods"] == ["AC"]


def test_period_axis_contract_rejects_same_period_title_even_with_periods(
    tmp_path: Path,
) -> None:
    context_status = _write_context(
        tmp_path / "column_total_chart_context.json",
        {
            "chart": "column_total",
            "selected_periods": ["2025-08-01", "2025-09-01"],
            "period_grain": "month",
            "chart_title_lines": ["AC to AC"],
        },
    )
    test_case = {
        "capability_id": "mix.column",
        "plugin_chart": "column_total",
        "expected_context_period_axis": {
            "minimum_distinct_periods": 2,
            "required_period_grain": "month",
            "forbid_same_period_title": True,
            "forbid_bare_ac_period": True,
        },
    }

    status = proof._chart_identity_status(test_case, context_status)

    assert status["status"] == "context_same_period_title"
    assert status["title_line"] == "AC to AC"


def test_period_axis_contract_accepts_resolved_month_context(
    tmp_path: Path,
) -> None:
    context_status = _write_context(
        tmp_path / "column_total_chart_context.json",
        {
            "chart": "column_total",
            "selected_periods": ["2025-08-01", "2025-09-01"],
            "period_grain": "month",
            "chart_title_lines": ["2025-08-01 to 2025-09-01"],
        },
    )
    test_case = {
        "capability_id": "mix.column",
        "plugin_chart": "column_total",
        "expected_context_period_axis": {
            "minimum_distinct_periods": 2,
            "required_period_grain": "month",
            "forbid_same_period_title": True,
            "forbid_bare_ac_period": True,
        },
    }

    status = proof._chart_identity_status(test_case, context_status)

    assert status["status"] == "chart_identity_ok"
    assert status["context_period_axis"]["status"] == "context_period_axis_ok"


def test_chart_identity_rejects_unresolved_scenario_period_labels(
    tmp_path: Path,
) -> None:
    context_status = _write_context(
        tmp_path / "multitier_bar_chart_context.json",
        {
            "chart": "multitier_bar",
            "selected_periods": ["PY", "AC"],
            "chart_title_lines": ["Company", "Sales", "AC vs PY"],
            "title_contract": {"who": "Company", "what": "Sales", "when": "AC vs PY"},
        },
    )
    test_case = {
        "capability_id": "mix.multitier_bar",
        "plugin_chart": "multitier_bar",
    }

    status = proof._chart_identity_status(test_case, context_status)

    assert status["status"] == "context_period_label_policy_failed"
    assert status["issues"][0]["code"] == (
        "scenario_periods_without_resolved_period_context"
    )


def test_chart_identity_accepts_scenario_period_labels_with_window(
    tmp_path: Path,
) -> None:
    context_status = _write_context(
        tmp_path / "multitier_bar_chart_context.json",
        {
            "chart": "multitier_bar",
            "selected_periods": ["PY", "AC"],
            "chart_title_lines": ["Company", "Sales", "AC vs PY"],
            "title_contract": {"who": "Company", "what": "Sales", "when": "AC vs PY"},
            "period_window": {
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
            },
        },
    )
    test_case = {
        "capability_id": "mix.multitier_bar",
        "plugin_chart": "multitier_bar",
    }

    status = proof._chart_identity_status(test_case, context_status)

    assert status["status"] == "chart_identity_ok"
    assert status["context_period_label_policy"]["status"] == "period_label_policy_ok"


def test_audit_identity_checks_context_period_label_policy(tmp_path: Path) -> None:
    context_path = tmp_path / "scatter_chart_context.json"
    context_path.write_text(
        json.dumps(
            {
                "chart": "scatter",
                "selected_periods": ["AC"],
                "chart_title_lines": ["Company", "Sales", "AC"],
            }
        ),
        encoding="utf-8",
    )
    test_case = {
        "capability_id": "scatter.scatter",
        "plugin_chart": "scatter",
    }

    status = proof._audit_chart_identity_status(
        test_case,
        {
            "status": "data_written",
            "chart_context": {"context_path": context_path.name},
        },
        tmp_path,
    )

    assert status["status"] == "context_period_label_policy_failed"
