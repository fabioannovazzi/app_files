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


def navigate(action: str, *, bank: bool = False, fail_save: bool = False) -> dict:
    """Click real workspace handlers using an isolated DOM and host transport."""
    fixture = {
        "action": action,
        "fail_save": fail_save,
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
        check=True,
        timeout=20,
    )
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


@pytest.mark.parametrize(
    ("action", "expected"),
    [
        ("refresh", {"client_id": CLIENT, "engagement_id": ENGAGEMENT, "offset": 30}),
        ("← Clienti", {}),
        ("← Incarichi del cliente", {"client_id": CLIENT}),
    ],
)
def test_directory_refresh_preserves_scope_and_explicit_back_changes_it(
    action, expected
):
    result = navigate(action)

    assert result["calls"] == [{"name": "vera_workspace_open", "arguments": expected}]
    assert result["buttons"].count("← Clienti") == 1
    assert "Clienti e incarichi" not in result["buttons"]
