from __future__ import annotations

import hashlib
import importlib.util
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pytest

ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = ROOT / "plugins" / "clara" / "scripts"


def _load_module(name: str, path: Path) -> Any:
    sys.path.insert(0, str(SCRIPTS))
    try:
        spec = importlib.util.spec_from_file_location(name, path)
        assert spec and spec.loader
        module = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = module
        spec.loader.exec_module(module)
        return module
    finally:
        sys.path.remove(str(SCRIPTS))


@pytest.fixture
def core() -> Any:
    return _load_module("clara_case_delivery_core", SCRIPTS / "advisor_case_core.py")


@pytest.fixture
def delivery() -> Any:
    return _load_module(
        "clara_case_delivery_gate", SCRIPTS / "verify_advisory_html_delivery.py"
    )


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _receipt() -> dict[str, Any]:
    return {
        "id": "ev-market-0001",
        "evidence_type": "management_assertion",
        "recorded_at": "2026-08-20T08:00:00+00:00",
        "recorded_by": "clara:advisory-case-director",
        "capture_status": "assertion_only",
        "source": {
            "material_ids": [],
            "url": "",
            "locator": "Reviewed source document",
            "artifact_refs": [],
        },
        "observation": "The reviewed source reports a bounded market condition.",
        "scope": "The selected source and stated period.",
        "limitations": ["The source does not establish target execution."],
        "verification": {
            "status": "not_checked",
            "checked_at": "",
            "method": "",
            "notes": [],
        },
        "rechecks_evidence_id": "",
        "supersedes_evidence_id": "",
    }


def _claim() -> dict[str, Any]:
    return {
        "id": "cl-proceed-0001",
        "statement": "The opportunity is plausible enough to continue bounded diligence.",
        "claim_type": "recommendation",
        "recorded_at": "2026-08-20T08:00:00+00:00",
        "recorded_by": "clara:advisory-case-director",
        "provenance": {
            "workflow": "clara:advisory-case-director",
            "step": "case direction",
            "artifact": "advisory_workpaper.md",
            "locator": "Current answer",
        },
        "evidence_links": [
            {
                "evidence_id": "ev-market-0001",
                "relationship": "supports",
                "analysis": "The bounded condition makes continued diligence plausible.",
                "proves": "A market-level opportunity is plausible.",
                "does_not_prove": "The target captures the opportunity.",
            }
        ],
        "dependency": {
            "mode": "none",
            "claim_ids": [],
            "derivation_type": "reasoning",
            "explanation": "The model weighed the declared evidence and limitation.",
            "calculation_evidence_id": "",
        },
        "decision_use": "direct",
        "uncertainty": ["Target execution remains untested."],
        "professional_judgement_required": True,
        "appearances": [],
        "state": "active",
        "supersedes_claim_id": "",
    }


def _case_with_workpaper(core: Any, tmp_path: Path) -> tuple[Path, dict[str, Any]]:
    case_dir = tmp_path / "case"
    now = datetime(2026, 8, 20, 8, 0, tzinfo=timezone.utc)
    core.initialize_case(
        case_dir,
        client="Synthetic client",
        project="Synthetic diligence",
        objective="Decide whether to continue diligence",
        audience="Engagement partner",
        output_language="en",
        now=now,
    )
    core.record_analysis_contribution(
        case_dir,
        evidence_receipts=[_receipt()],
        claims=[_claim()],
        now=now,
    )
    staged = tmp_path / "advisory_workpaper.staged.md"
    staged.write_text(
        "# Current answer\n\nContinue bounded diligence while target execution remains untested.\n",
        encoding="utf-8",
    )
    checkpoint = core.commit_advisory_workpaper(
        case_dir,
        staged,
        referenced_claim_ids=["cl-proceed-0001"],
        change_summary="Recorded the initial answer and its target-execution limit.",
        now=now,
    )
    return case_dir, checkpoint


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )


def _delivery_fixture(
    core: Any,
    tmp_path: Path,
    *,
    browser_input_sha256: str | None = None,
) -> tuple[Path, Path, Path]:
    case_dir, _checkpoint = _case_with_workpaper(core, tmp_path)
    deck = tmp_path / "index.html"
    deck.write_text(
        "<!doctype html><html><body><section>Continue bounded diligence.</section></body></html>",
        encoding="utf-8",
    )
    lineage = _load_module(
        "clara_case_delivery_lineage", SCRIPTS / "advisory_evidence_lineage.py"
    )
    lineage.bind_claim_appearances(
        case_dir,
        deck,
        [
            {
                "claim_id": "cl-proceed-0001",
                "locator": "Slide decision",
                "format_claim_id": "cl-proceed-0001",
            }
        ],
        recorded_at="2026-08-20T08:10:00+00:00",
    )
    deck_sha256 = _sha256(deck)
    static_report = tmp_path / "html-build-report.json"
    browser_report = tmp_path / "browser-qa.json"
    _write_json(
        static_report,
        {
            "schema_version": "clara.html_deck_build.v1",
            "result": "pass",
            "input": {"sha256": deck_sha256},
            "deck": {"slide_count": 1},
            "checks": [],
            "summary": {"error_count": 0},
        },
    )
    _write_json(
        browser_report,
        {
            "schema_version": "clara.html_deck_browser_qa.v1",
            "result": "pass",
            "input": {"sha256": browser_input_sha256 or deck_sha256},
            "browser": {"status": "ready"},
            "viewports": [],
        },
    )
    evidence_register = case_dir / "advisory_evidence_register.json"
    claim_register = case_dir / "advisory_claim_register.json"
    audit_path = tmp_path / "validation_audit.json"
    _write_json(
        audit_path,
        {
            "schema_version": "1.1",
            "record_complete": True,
            "errors": [],
            "effective_delivery_readiness": "ready",
            "deliverable": {
                "path": str(deck.resolve()),
                "sha256": deck_sha256,
                "byte_count": deck.stat().st_size,
            },
            "lineage": {
                "provenance_mode": "generation_time",
                "evidence_register": {
                    "source_path": str(evidence_register.resolve()),
                    "sha256": _sha256(evidence_register),
                },
                "claim_register": {
                    "source_path": str(claim_register.resolve()),
                    "sha256": _sha256(claim_register),
                },
                "reviewed_claim_ids": ["cl-proceed-0001"],
                "assessed_claim_ids": ["cl-proceed-0001"],
            },
            "format_check_artifacts": [
                {
                    "workflow": "clara:html-deck",
                    "path": str(static_report.resolve()),
                    "sha256": _sha256(static_report),
                    "byte_count": static_report.stat().st_size,
                },
                {
                    "workflow": "clara:html-deck",
                    "path": str(browser_report.resolve()),
                    "sha256": _sha256(browser_report),
                    "byte_count": browser_report.stat().st_size,
                },
            ],
        },
    )
    return case_dir, deck, audit_path


def test_workpaper_commit_binds_claims_and_preserves_prior_version(
    core: Any, tmp_path: Path
) -> None:
    case_dir, first = _case_with_workpaper(core, tmp_path)
    second_stage = tmp_path / "advisory_workpaper.second.md"
    second_stage.write_text(
        "# Current answer\n\nContinue diligence under an explicit execution test.\n",
        encoding="utf-8",
    )

    second = core.commit_advisory_workpaper(
        case_dir,
        second_stage,
        referenced_claim_ids=["cl-proceed-0001"],
        change_summary="Made the execution condition explicit.",
        now=datetime(2026, 8, 20, 9, 0, tzinfo=timezone.utc),
    )

    history = case_dir / second["prior_workpaper"]["history_path"]
    assert first["lineage"]["referenced_claim_ids"] == ["cl-proceed-0001"]
    assert first["lineage"]["referenced_evidence_ids"] == ["ev-market-0001"]
    assert history.read_text(encoding="utf-8").startswith("# Current answer")
    assert second["workpaper"]["sha256"] == _sha256(case_dir / "advisory_workpaper.md")


def test_workpaper_commit_rejects_an_unknown_model_declared_claim(
    core: Any, tmp_path: Path
) -> None:
    case_dir, _checkpoint = _case_with_workpaper(core, tmp_path)
    staged = tmp_path / "unknown-claim.md"
    staged.write_text("# Answer\n\nUnsupported rewrite.\n", encoding="utf-8")

    with pytest.raises(core.CaseWorkspaceError, match="unknown referenced claim ids"):
        core.commit_advisory_workpaper(
            case_dir,
            staged,
            referenced_claim_ids=["cl-missing"],
            change_summary="Attempted an unregistered claim.",
        )


def test_case_html_delivery_receipt_accepts_exact_current_chain(
    core: Any, delivery: Any, tmp_path: Path
) -> None:
    case_dir, deck, audit_path = _delivery_fixture(core, tmp_path)

    receipt = delivery.verify_advisory_html_delivery(case_dir, deck, audit_path)

    assert receipt["status"] == "ready"
    assert receipt["errors"] == []
    assert receipt["deck"]["active_direct_claim_ids"] == ["cl-proceed-0001"]


def test_case_html_delivery_receipt_rejects_browser_qa_for_other_bytes(
    core: Any, delivery: Any, tmp_path: Path
) -> None:
    case_dir, deck, audit_path = _delivery_fixture(
        core,
        tmp_path,
        browser_input_sha256="0" * 64,
    )

    receipt = delivery.verify_advisory_html_delivery(case_dir, deck, audit_path)

    assert receipt["status"] == "blocked"
    assert any("html_browser_qa did not pass" in error for error in receipt["errors"])


def test_case_html_delivery_receipt_rejects_semantic_lineage_after_checkpoint(
    core: Any, delivery: Any, tmp_path: Path
) -> None:
    case_dir, deck, audit_path = _delivery_fixture(core, tmp_path)
    lineage = _load_module(
        "clara_case_delivery_lineage_stale",
        SCRIPTS / "advisory_evidence_lineage.py",
    )
    second_claim = _claim()
    second_claim["id"] = "cl-new-0002"
    second_claim["statement"] = (
        "A newly registered claim changes the current case meaning."
    )
    second_claim["decision_use"] = "supporting"
    second_claim["provenance"]["locator"] = "New claim"
    lineage.record_claims(case_dir, [second_claim])

    receipt = delivery.verify_advisory_html_delivery(case_dir, deck, audit_path)

    assert receipt["status"] == "blocked"
    assert (
        "Evidence or claim meaning changed after the workpaper checkpoint."
        in receipt["errors"]
    )
    assert "The claim register changed after advisory validation." in receipt["errors"]
