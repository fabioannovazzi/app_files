from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
PLUGIN_ROOT = ROOT / "plugins" / "bilancio-xbrl-it"
SCRIPTS = PLUGIN_ROOT / "scripts"
RULE_PACK = PLUGIN_ROOT / "rulepacks" / "it" / "statutory-forms-2026.1.json"


def _load_module(name: str):
    if str(SCRIPTS) not in sys.path:
        sys.path.insert(0, str(SCRIPTS))
    path = SCRIPTS / f"{name}.py"
    spec = importlib.util.spec_from_file_location(f"bilancio_{name}_views", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


xbrl_case = _load_module("xbrl_case")
review_views = _load_module("review_views")


def _case(tmp_path: Path) -> dict[str, object]:
    rule_pack = json.loads(RULE_PACK.read_text(encoding="utf-8"))
    case = xbrl_case.create_case(
        tmp_path / "case",
        {
            "case_id": "case_views",
            "tenant_id": "tenant_1",
            "entity": {
                "legal_name": "Views S.r.l.",
                "tax_identifier": "IT00000000000",
                "registered_office": "Milano (MI), Italia",
                "legal_form": "SRL",
                "accounting_framework": "OIC",
                "listed": False,
                "regulated_sector": False,
                "consolidated": False,
                "final_liquidation": False,
                "first_financial_year": False,
                "prior_year_form": "ABBREVIATED",
                "micro_exclusion_flags": [],
            },
            "period": {"start": "2025-01-01", "end": "2025-12-31"},
            "oic_rule_pack": "OIC_2026.1",
            "taxonomy_checksum": "a" * 64,
        },
        rule_pack,
        "preparer_1",
    )
    entries = [
        {
            "account_id": f"acc_{index:06d}",
            "account_code": str(index),
            "account_description": f"Account {index}",
            "closing_signed": str(index),
            "prior_closing_signed": str(index - 1),
            "source_refs": [f"src_{index}"],
        }
        for index in range(1, 4)
    ]
    case["trial_balance"] = {
        "layout": "SIGNED_BALANCES",
        "confirmed_convention": "SIGNED_BALANCE_ONLY",
        "entries": entries,
        "source_anchors": [
            {"source_ref": f"src_{index}", "row": index + 1, "column": "balance"}
            for index in range(1, 4)
        ],
        "calibration": {"closing_difference": "0"},
    }
    case["selected_form"] = "ABBREVIATED"
    case["form_analysis"] = {"eligible_forms": ["ABBREVIATED", "ORDINARY"]}
    case["mappings"] = [
        {"account_id": "acc_000001", "decision": "ACCEPTED", "allocations": []}
    ]
    case["mapping_candidates"] = [
        {"account_id": "acc_000002", "candidate_source": "CLIENT_MEMORY"}
    ]
    case["statements"] = {
        "facts": [
            {
                "fact_id": "fact_1",
                "key": "SP.ATTIVO.CASSA",
                "current_value": "1",
                "prior_value": "0",
                "allocation_refs": ["acc_000001_1"],
            }
        ],
        "section_totals": {"ASSETS": {"current": "1", "prior": "0"}},
        "reporting_precision": 0,
        "rounding_adjustments": [],
    }
    case["canonical_facts"] = list(case["statements"]["facts"])
    case["schedules"] = [
        {
            "schedule_id": "schedule_1",
            "schedule_type": "FIXED_ASSETS",
            "status": "COMPLETE",
        }
    ]
    case["disclosure_rule_pack"] = {"id": "DISCLOSURE_TEST"}
    case["disclosure_coverage"] = {"triggered_count": 1}
    case["questionnaire"] = [
        {"question_id": "question_1", "state": "OPEN", "reason": "Evidence needed"}
    ]
    case["note_outline"] = [{"section_id": "POLICIES", "status": "DRAFT"}]
    case["narrative_blocks"] = [
        {"block_id": "block_1", "section_id": "POLICIES", "status": "DRAFT"}
    ]
    case["validation"] = {
        "status": "FAIL",
        "blockers": 1,
        "high": 0,
        "review_required": 0,
        "issues": [{"issue_id": "issue_1", "severity": "BLOCKER", "rule_id": "TEST"}],
    }
    case["preview"] = {"file_name": "preview.html", "sha256": "b" * 64}
    case["xbrl_review"] = {"status": "PASS", "candidate_sha256": "c" * 64}
    case["approval"] = {
        "snapshot_id": "snapshot_1",
        "snapshot_hash": "d" * 64,
        "snapshot": {"private": "must not be returned"},
    }
    case["artifacts"] = [{"file_name": "accounts.xbrl", "sha256": "e" * 64}]
    return case


@pytest.mark.parametrize(
    ("view", "expected_key"),
    [
        ("CASE_DASHBOARD", "next_action"),
        ("SOURCE_REVIEW", "anchors"),
        ("MAPPING_GRID", "rows"),
        ("STATEMENTS", "facts"),
        ("SCHEDULES", "schedules"),
        ("QUESTIONNAIRE", "questions"),
        ("NOTES_EDITOR", "narrative_blocks"),
        ("ISSUES_PANEL", "issues"),
        ("PREVIEW", "resource_ids"),
        ("APPROVAL_EXPORT", "artifacts"),
    ],
)
def test_all_required_professional_review_views_are_structured(
    tmp_path: Path, view: str, expected_key: str
) -> None:
    case = _case(tmp_path)

    result = review_views.build_review_view(case, view, offset=0, limit=2)

    assert result["view"] == view
    assert result["case_id"] == "case_views"
    assert result["revision_id"] == case["revision_id"]
    assert expected_key in result
    assert "completion_percentage" not in json.dumps(result)


def test_review_view_paginates_large_grids_and_preserves_decisions(
    tmp_path: Path,
) -> None:
    case = _case(tmp_path)

    result = review_views.build_review_view(case, "MAPPING_GRID", offset=1, limit=1)

    assert result["rows"]["page"] == {
        "offset": 1,
        "limit": 1,
        "returned": 1,
        "total": 3,
        "has_more": True,
    }
    row = result["rows"]["items"][0]
    assert row["account_id"] == "acc_000002"
    assert row["candidate"]["candidate_source"] == "CLIENT_MEMORY"
    assert row["decision"] is None


def test_approval_review_view_excludes_immutable_snapshot_payload(
    tmp_path: Path,
) -> None:
    result = review_views.build_review_view(_case(tmp_path), "APPROVAL_EXPORT")

    assert result["approval"]["snapshot_id"] == "snapshot_1"
    assert "snapshot" not in result["approval"]


def test_preview_review_view_returns_receipt_without_embedded_html_bytes(
    tmp_path: Path,
) -> None:
    case = _case(tmp_path)
    case["preview"]["content_base64"] = "PGh0bWw+PC9odG1sPg=="

    result = review_views.build_review_view(case, "PREVIEW")

    assert result["preview"]["sha256"] == "b" * 64
    assert "content_base64" not in result["preview"]


def test_statement_view_exposes_statutory_requirements_and_next_action(
    tmp_path: Path,
) -> None:
    case = _case(tmp_path)
    case["mappings"] = [
        {"account_id": f"acc_{index:06d}", "decision": "ACCEPTED"}
        for index in range(1, 4)
    ]
    case["statutory_presentation"] = {
        "status": "INCOMPLETE",
        "summary": {"missing_period_decisions": 1, "issues": 0},
        "inventory": {
            "inventory_sha256": "a" * 64,
            "requirements": [
                {"xbrl_concept": "itcc:Cash", "label_it": "Disponibilità liquide"}
            ],
            "totals": [],
            "formulas": [],
        },
        "decisions": [],
        "missing": [{"xbrl_concept": "itcc:Cash", "period": "prior"}],
        "issues": [],
    }

    statements = review_views.build_review_view(case, "STATEMENTS")
    dashboard = review_views.build_review_view(case, "CASE_DASHBOARD")

    presentation = statements["statutory_presentation"]
    assert presentation["status"] == "INCOMPLETE"
    assert presentation["requirements"]["items"][0]["missing_periods"] == ["prior"]
    assert dashboard["next_action"] == "REVIEW_STATUTORY_PRESENTATION"


@pytest.mark.parametrize(
    ("view", "offset", "limit", "message"),
    [
        ("UNKNOWN", 0, 10, "Unsupported"),
        ("SOURCE_REVIEW", -1, 10, "offset"),
        ("SOURCE_REVIEW", 0, 501, "limit"),
    ],
)
def test_review_view_rejects_invalid_contract(
    tmp_path: Path, view: str, offset: int, limit: int, message: str
) -> None:
    with pytest.raises(ValueError, match=message):
        review_views.build_review_view(
            _case(tmp_path), view, offset=offset, limit=limit
        )
