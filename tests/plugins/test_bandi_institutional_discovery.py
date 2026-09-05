from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest

from tests.plugins.test_bandi_opportunity_radar import (
    _contribution_args,
    _initialized_radar,
    _opportunity,
    _review,
    _scan,
    _source,
    _start_scan,
)

__all__: list[str] = []


def _gazette_scan(tmp_path: Path) -> tuple[ModuleType, Path]:
    """Start a synthetic public gazette scan with reviewed source selection."""
    radar, workspace = _initialized_radar(tmp_path)
    source = _source([])
    source.update(source_surface="official_gazette", profile_refs=[])
    radar.record_source(
        workspace, source=source, idempotency_key="source", **_contribution_args()
    )
    _review(
        radar, workspace, scope="source", target_id="SOURCE-REGION", key="review-source"
    )
    _start_scan(radar, workspace)
    return radar, workspace


def _inventory() -> dict[str, Any]:
    """Return synthetic issue evidence independent of live publications."""
    return {
        "index_urls": ["https://official.example/archive"],
        "enumerated_at": "2026-08-07T10:05:00+00:00",
        "window_start": "2026-06-09",
        "window_end": "2026-08-07",
        "enumeration_complete": True,
        "empty_window_rationale": "",
        "issues": [
            {
                "issue_id": "ISSUE-001",
                "official_url": "https://official.example/issue-1",
                "publication_date": "2026-08-07",
                "status": "checked",
                "checked_at": "2026-08-07T10:10:00+00:00",
                "act_urls": ["https://official.example/programming-decree"],
                "notes": "Synthetic programming decree retained after summary review.",
            }
        ],
    }


def _check(
    radar: ModuleType,
    workspace: Path,
    inventory: dict[str, Any] | None,
    *,
    status: str = "checked",
) -> dict[str, Any]:
    """Record one synthetic issue-backed source check."""
    return radar.record_source_check(
        workspace,
        source_id="SOURCE-REGION",
        check_id="CHECK-001",
        scan_id="SCAN-001",
        check_status=status,
        checked_at="2026-08-07T11:00:00+00:00",
        window_start="2026-06-09",
        window_end="2026-08-07",
        next_check_on=None,
        result_count=1 if status == "checked" else None,
        error_code=None if status == "checked" else "ISSUE_UNAVAILABLE",
        cursor_after=None,
        issue_inventory=inventory,
        idempotency_key="check",
    )


@pytest.mark.parametrize(
    "defect, error",
    [
        ("missing", "requires an issue inventory"),
        ("incomplete", "complete issue coverage"),
        ("unavailable", "complete issue coverage"),
        ("empty", "evidenced rationale"),
        ("duplicate", "duplicate issue_id"),
        ("short_window", "does not cover"),
        ("outside_date", "outside inventory window"),
        ("future_check", "cannot follow"),
        ("future_inventory", "enumerated after"),
    ],
)
def test_gazette_rejects_incomplete_or_inconsistent_evidence(
    tmp_path: Path, defect: str, error: str
) -> None:
    radar, workspace = _gazette_scan(tmp_path)
    inventory = _inventory()
    if defect == "missing":
        inventory = None
    elif defect == "incomplete":
        inventory["enumeration_complete"] = False
    elif defect == "unavailable":
        inventory["issues"][0]["status"] = "unavailable"
    elif defect == "empty":
        inventory["issues"] = []
    elif defect == "duplicate":
        inventory["issues"].append(deepcopy(inventory["issues"][0]))
    elif defect == "short_window":
        inventory["window_start"] = "2026-08-01"
    elif defect == "outside_date":
        inventory["issues"][0]["publication_date"] = "2026-08-08"
    elif defect == "future_check":
        inventory["issues"][0]["checked_at"] = "2026-08-07T12:00:00+00:00"
    elif defect == "future_inventory":
        inventory["enumerated_at"] = "2026-08-07T12:00:00+00:00"
    with pytest.raises(ValueError, match=error):
        _check(radar, workspace, inventory)


def test_gazette_inventory_is_reviewed_sealed_and_visible(tmp_path: Path) -> None:
    radar, workspace = _gazette_scan(tmp_path)
    inventory = _inventory()
    _check(radar, workspace, inventory)
    _review(
        radar,
        workspace,
        scope="source_check",
        target_id="SOURCE-REGION",
        key="review-check",
    )
    radar.record_scan(
        workspace,
        scan=_scan(outcome="complete", completed_at="2026-08-07T12:00:00+00:00"),
        next_scan_on=None,
        idempotency_key="finish",
    )

    saved = radar.load_validated_radar(workspace)
    assert (
        saved["monitoring"]["scan_history"][0]["source_check_snapshots"][0][
            "issue_inventory"
        ]
        == inventory
    )
    report = radar.render_radar_report(workspace).read_text()
    assert "https://official.example/issue-1" in report
    assert "https://official.example/programming-decree" in report


def test_unavailable_issue_can_be_recorded_but_scan_remains_partial(
    tmp_path: Path,
) -> None:
    radar, workspace = _gazette_scan(tmp_path)
    inventory = _inventory()
    inventory["issues"][0]["status"] = "unavailable"
    _check(radar, workspace, inventory, status="unavailable")
    _review(
        radar,
        workspace,
        scope="source_check",
        target_id="SOURCE-REGION",
        key="review-check",
    )
    radar.record_scan(
        workspace,
        scan=_scan(outcome="partial", completed_at="2026-08-07T12:00:00+00:00"),
        next_scan_on=None,
        idempotency_key="finish",
    )
    saved = radar.load_validated_radar(workspace)
    assert saved["monitoring"]["scan_history"][0]["coverage"][
        "unverified_priority_source_ids"
    ] == ["SOURCE-REGION"]


@pytest.mark.parametrize("lifecycle", ["programmed", "no_operating_calendar"])
def test_public_discovery_reports_non_open_opportunities_without_matches(
    tmp_path, lifecycle
):
    radar, workspace = _gazette_scan(tmp_path)
    opportunity = _opportunity()
    opportunity["opening_date"] = None
    opportunity["closing_date"] = None
    opportunity["lifecycle_history"][0]["status"] = lifecycle
    opportunity["current_lifecycle"] = lifecycle
    radar.record_opportunity(
        workspace,
        opportunity=opportunity,
        idempotency_key="opportunity",
        **_contribution_args(),
    )
    report = radar.render_radar_report(workspace).read_text()
    assert opportunity["official_title"] in report
    assert lifecycle in report


def test_codex_and_chatgpt_packages_preserve_the_same_discovery_contract() -> None:
    from tests.plugins.test_codex_plugin_packages import load_builder

    builder = load_builder()
    vera = {item.name: item for item in builder.load_bundles()}["vera"]
    chatgpt = builder.chatgpt_upload_entries(vera)
    codex = builder.expected_zip_entries(vera)
    reference = "modules/bandi-agevolazioni/skills/bandi-agevolazioni/references/institutional-discovery.md"
    matching = [value for name, value in codex.items() if name.endswith(reference)]
    assert matching == [chatgpt[reference]]
    card = chatgpt["skills/bandi-agevolazioni/SKILL.md"].decode()
    assert "../../modules/bandi-agevolazioni" in card
    assert "references/institutional-discovery.md" in card
    assert "Gazzetta Ufficiale" in card
    assert "ChatGPT" in card


def test_changed_issue_evidence_invalidates_professional_review(tmp_path: Path) -> None:
    radar, workspace = _gazette_scan(tmp_path)
    _check(radar, workspace, _inventory())
    _review(
        radar,
        workspace,
        scope="source_check",
        target_id="SOURCE-REGION",
        key="review-check",
    )
    path = workspace / "opportunity_radar.json"
    saved = json.loads(path.read_text())
    saved["source_plan"]["entries"][0]["issue_inventory"]["issues"][0][
        "notes"
    ] = "Changed interpretation after review."
    path.write_text(json.dumps(saved))

    with pytest.raises(ValueError, match="stale professional review"):
        radar.load_validated_radar(workspace)


def test_new_institution_preserves_prior_registry_and_requires_review(
    tmp_path: Path,
) -> None:
    radar, workspace = _gazette_scan(tmp_path)
    prior = radar.load_validated_radar(workspace)["source_plan"]["entries"][0]
    discovered = _source([])
    discovered.update(
        source_id="SOURCE-FESR",
        profile_refs=[],
        relevance_rationale="Discovered through https://official.example/programme; FESR managing authority.",
    )

    radar.record_source(
        workspace,
        source=discovered,
        idempotency_key="new-source",
        **_contribution_args(),
    )

    entries = radar.load_validated_radar(workspace)["source_plan"]["entries"]
    assert entries[0] == prior
    assert entries[1]["review_status"] == "proposed"
    assert entries[1]["check_status"] == "planned"
    assert (
        discovered["relevance_rationale"]
        in radar.render_radar_report(workspace).read_text()
    )
