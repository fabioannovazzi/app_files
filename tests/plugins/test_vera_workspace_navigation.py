"""Directory navigation keeps the selected work reachable after refresh/save."""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest

__all__: list[str] = []
ROOT = Path(__file__).resolve().parents[2]
CLIENT = "selected-client"
ENGAGEMENT = "selected-engagement"


def navigate(
    action: str,
    *,
    bank: bool = False,
    fail_save: bool = False,
    linked_workflow: str | None = None,
    fail_link: bool = False,
    next_action: str | None = None,
    notifications: list[dict] | None = None,
) -> dict:
    """Click real workspace handlers using an isolated DOM and host transport."""
    fixture = {
        "action": action,
        "next_action": next_action,
        "fail_save": fail_save,
        "notifications": notifications or [],
        "catalogue": {
            "mode": "studio-archive",
            "configured": True,
            "level": "runs",
            "client_id": CLIENT,
            "engagement_id": ENGAGEMENT,
            "engagement_label": "Current engagement",
            "offset": 30,
            "total": 31,
            "works": [
                {
                    "work_ref": "current-work",
                    "label": "Current bank work",
                    "workflow": "journal-bank-reconciliation",
                    "status": "running",
                    "setup_available": True,
                }
            ],
        },
    }
    if bank:
        fixture["bank_setup"] = {
            "work_ref": "current-work",
            "label": "Current bank work",
            "client_id": CLIENT,
            "engagement_id": ENGAGEMENT,
            "revision": "current-revision",
            "review_ticket": "current-ticket",
            "can_write": True,
            "status": "not_inspected",
            "items": [],
            "offset": 0,
            "total": 0,
        }
    if linked_workflow:
        fixture["fail_link"] = fail_link
        fixture["catalogue"]["works"] = []
        fixture["catalogue"]["incarico"] = {
            "client_id": CLIENT,
            "engagement_id": ENGAGEMENT,
            "purpose": "Requested specialist work",
            "results": [],
            "deliverables": [],
            "documents": [],
            "document_issues": [],
            "conversations": [],
            "work_links": [
                {
                    "workflow_id": linked_workflow,
                    "work_ref": "bound-case",
                    "binding_identity": "a" * 64,
                    "label": "Saved specialist case",
                }
            ],
        }
    node = shutil.which("node")
    assert node is not None, "Node is required for native workspace regressions"
    completed = subprocess.run(
        [
            node,
            str(ROOT / "tests/plugins/archive_run_list_ui.cjs"),
            str(ROOT / "plugins/vera/ui/workspace.js"),
            "navigation",
        ],
        input=json.dumps(fixture),
        text=True,
        capture_output=True,
        check=False,
        timeout=20,
    )
    assert completed.returncode == 0, completed.stderr
    return json.loads(completed.stdout)


@pytest.mark.parametrize(
    ("action", "operation"),
    [
        ("Conserva e torna ai lavori", "vera_workspace_bank_draft_save"),
        ("Scarta e torna ai lavori", "vera_workspace_bank_draft_clear"),
    ],
)
def test_bank_return_keeps_engagement_after_draft_operation(action, operation):
    result = navigate(action, bank=True)

    assert result["calls"][-2]["name"] == operation
    assert result["calls"][-1] == {
        "name": "vera_workspace_open",
        "arguments": {"client_id": CLIENT, "engagement_id": ENGAGEMENT},
    }


def test_bank_failed_save_keeps_preparation_visible_without_navigation():
    result = navigate("Conserva e torna ai lavori", bank=True, fail_save=True)

    assert result["calls"][-1]["name"] == "vera_workspace_bank_draft_save"
    assert "vera_workspace_open" not in [call["name"] for call in result["calls"]]
    assert result["status"] == "Draft write failed"
    assert "Documenti e ruoli" in result["text"]


def test_chat_open_preserves_unsaved_bank_choices():
    result = navigate(
        "refresh",
        bank=True,
        notifications=[
            {
                "navigation_id": "requested-directory",
                "mode": "studio-archive",
                "level": "clients",
                "configured": True,
                "works": [],
                "clients": [],
            }
        ],
    )
    assert "modulo contiene modifiche" in result["status"]
    assert "Documenti e ruoli" in result["text"]
    assert "Clienti e progetti" not in result["text"]


@pytest.mark.parametrize(
    ("workflow", "panel"),
    [
        ("browser-automation", "VeraBrowser"),
        ("comunicazione-professionale", "VeraCommunication"),
        ("fusione-guidata", "VeraFusion"),
        ("presenza-digitale-studio", "VeraWebsite"),
        ("trasformazione", "VeraTransformation"),
        ("contenzioso-tributario", "VeraPracticeReviews"),
        ("studio-document-format", "VeraPracticeReviews"),
    ],
)
def test_incarico_link_opens_the_corresponding_specialist_panel(workflow, panel):
    result = navigate("Saved specialist case", linked_workflow=workflow)
    assert result["calls"] == [
        {
            "name": "vera_incarico_open_work",
            "arguments": {
                "client_id": CLIENT,
                "engagement_id": ENGAGEMENT,
                "workflow_id": workflow,
                "work_ref": "bound-case",
            },
        }
    ]
    assert result["opened"] == [{"panel": panel, "work_ref": "bound-case"}]


def test_unavailable_incarico_link_keeps_work_visible_without_opening_other_case():
    result = navigate(
        "Saved specialist case", linked_workflow="fusione-guidata", fail_link=True
    )
    assert result["opened"] == []
    assert result["status"] == "The saved case is unavailable"
    assert "Saved specialist case" in result["text"]


@pytest.mark.parametrize(
    ("action", "expected"),
    [
        ("refresh", {"client_id": CLIENT, "engagement_id": ENGAGEMENT, "offset": 30}),
        ("← Incarichi", {"client_id": CLIENT}),
    ],
)
def test_directory_refresh_preserves_scope_and_explicit_back_changes_it(
    action, expected
):
    result = navigate(action)

    assert result["calls"] == [{"name": "vera_workspace_open", "arguments": expected}]
    assert "← Clienti" not in result["buttons"]
    assert result["buttons"].count("← Incarichi") == 1
    assert "Clienti e incarichi" not in result["buttons"]


@pytest.mark.parametrize(
    "workflow",
    [
        "browser-automation",
        "comunicazione-professionale",
        "fusione-guidata",
        "presenza-digitale-studio",
        "trasformazione",
        "contenzioso-tributario",
        "studio-document-format",
    ],
)
def test_linked_work_returns_to_its_incarico(workflow):
    result = navigate(
        "Saved specialist case", linked_workflow=workflow, next_action="← Incarico"
    )
    assert result["calls"][-1] == {
        "name": "vera_workspace_open",
        "arguments": {"client_id": CLIENT, "engagement_id": ENGAGEMENT, "offset": 30},
    }
    assert "Saved specialist case" in result["text"]


def test_communication_refresh_retains_the_selected_work():
    result = navigate(
        "Saved specialist case",
        linked_workflow="comunicazione-professionale",
        next_action="refresh",
    )
    assert result["opened"][-1] == {
        "panel": "VeraCommunication",
        "work_ref": "bound-case",
        "refresh": True,
    }
    assert [call["name"] for call in result["calls"]] == ["vera_incarico_open_work"]
