from __future__ import annotations

import hashlib
import importlib.util
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
MODULE_PATH = ROOT / "plugins" / "bilancio-xbrl-it" / "scripts" / "client_history.py"


def _load_module():
    spec = importlib.util.spec_from_file_location(
        "bilancio_client_history", MODULE_PATH
    )
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


client_history = _load_module()


def _canonical_hash(value: object) -> str:
    encoded = json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _approved_case() -> dict[str, object]:
    snapshot = {
        "period": {"start": "2024-01-01", "end": "2024-12-31"},
        "selected_form": "ABBREVIATED",
        "disclosure_answers": [
            {
                "key": "post_closing_events",
                "status": "NOT_APPLICABLE_CONFIRMED",
                "value": False,
                "source_refs": ["old_source_1"],
            },
            {
                "key": "basis_of_preparation",
                "status": "ACCEPTED",
                "value": "OIC abbreviato",
                "source_refs": ["old_source_2"],
            },
        ],
        "narrative_blocks": [
            {
                "block_id": "block_1",
                "section_id": "INTRODUCTION",
                "text": "Il bilancio è redatto in forma abbreviata.",
                "status": "ACCEPTED",
                "claims": [
                    {
                        "sentence": "Il bilancio è redatto in forma abbreviata.",
                        "source_refs": ["old_source_2"],
                    }
                ],
            }
        ],
        "disclosure_coverage": {
            "coverage": [
                {"rule_id": "IT.CC.BASIS_PREPARATION", "triggered": True},
                {"rule_id": "IT.CC.LEASES", "triggered": False},
            ]
        },
        "canonical_facts": [{"fact_id": "fact_1", "current_value": "999999.99"}],
    }
    return {
        "case_id": "case_2024",
        "tenant_id": "tenant_1",
        "state": "APPROVED",
        "entity": {
            "tax_identifier": "IT00000000000",
            "legal_name": "Rossi S.r.l.",
        },
        "period": snapshot["period"],
        "approval": {
            "snapshot_hash": _canonical_hash(snapshot),
            "snapshot": snapshot,
        },
    }


def _next_case(tenant_id: str = "tenant_1") -> dict[str, object]:
    return {
        "case_id": "case_2025",
        "tenant_id": tenant_id,
        "state": "DRAFT",
        "entity": {
            "tax_identifier": "IT00000000000",
            "legal_name": "Rossi S.r.l.",
        },
        "period": {"start": "2025-01-01", "end": "2025-12-31"},
    }


def test_approved_history_reuses_decisions_only_as_unconfirmed_suggestions(
    tmp_path: Path,
) -> None:
    history_path = tmp_path / "client-history.json"
    client_history.remember_approved_client_history(
        _approved_case(), history_path, "reviewer_1"
    )

    suggestions = client_history.client_history_suggestions(_next_case(), history_path)

    assert suggestions["form_suggestion"]["status"] == "UNCONFIRMED_PRIOR_SUGGESTION"
    negative = next(
        item
        for item in suggestions["answer_suggestions"]
        if item["key"] == "post_closing_events"
    )
    assert negative["value"] is False
    assert negative["requires_reconfirmation"] is True
    assert suggestions["narrative_suggestions"][0]["requires_redline"] is True
    assert suggestions["recurring_evidence_suggestions"] == [
        {
            "rule_id": "IT.CC.BASIS_PREPARATION",
            "status": "PRIOR_PERIOD_TRIGGER_ONLY",
            "requires_current_period_evaluation": True,
            "source_refs": [
                f"approved_snapshot:{_approved_case()['approval']['snapshot_hash']}"
            ],
        }
    ]


def test_client_history_store_excludes_identity_amounts_and_old_source_refs(
    tmp_path: Path,
) -> None:
    history_path = tmp_path / "client-history.json"
    client_history.remember_approved_client_history(
        _approved_case(), history_path, "reviewer_1"
    )

    stored_text = history_path.read_text(encoding="utf-8")

    assert "IT00000000000" not in stored_text
    assert "Rossi S.r.l." not in stored_text
    assert "999999.99" not in stored_text
    assert "old_source_1" not in stored_text
    assert "old_source_2" not in stored_text


def test_client_history_rejects_cross_tenant_store(tmp_path: Path) -> None:
    history_path = tmp_path / "client-history.json"
    client_history.remember_approved_client_history(
        _approved_case(), history_path, "reviewer_1"
    )

    with pytest.raises(ValueError, match="Cross-tenant"):
        client_history.client_history_suggestions(_next_case("tenant_2"), history_path)


def test_unapproved_case_cannot_enter_client_history(tmp_path: Path) -> None:
    case = _approved_case()
    case["state"] = "DRAFT"

    with pytest.raises(ValueError, match="Only approved"):
        client_history.remember_approved_client_history(
            case, tmp_path / "history.json", "preparer_1"
        )
