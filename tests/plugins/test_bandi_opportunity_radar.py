from __future__ import annotations

import importlib.util
import json
import stat
import sys
from pathlib import Path
from types import ModuleType

import pytest

ROOT = Path(__file__).resolve().parents[2]
PLUGIN_ROOT = ROOT / "plugins" / "bandi-agevolazioni"
SCRIPTS_ROOT = PLUGIN_ROOT / "scripts"


def _module_from_path(name: str, path: Path) -> ModuleType:
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _radar_module() -> ModuleType:
    previous = {
        name: sys.modules.get(name) for name in ("case_core", "schema_validation")
    }
    core = _module_from_path("radar_test_case_core", SCRIPTS_ROOT / "case_core.py")
    schema = _module_from_path(
        "radar_test_schema_validation", SCRIPTS_ROOT / "schema_validation.py"
    )
    sys.modules["case_core"] = core
    sys.modules["schema_validation"] = schema
    try:
        return _module_from_path(
            "radar_test_opportunity_radar", SCRIPTS_ROOT / "opportunity_radar.py"
        )
    finally:
        for name, module in previous.items():
            if module is None:
                sys.modules.pop(name, None)
            else:
                sys.modules[name] = module


def _read(path: Path) -> dict[str, object]:
    return json.loads(path.read_text(encoding="utf-8"))


def _profile(client_ref: str = "CLIENT-001") -> dict[str, object]:
    return {
        "client_ref": client_ref,
        "facets": [
            {
                "facet_id": f"FACET-{client_ref}-TERRITORY",
                "category": "territory",
                "value": "Provincia di Padova, Regione Veneto",
                "as_of_date": "2026-08-07",
                "evidence_refs": [f"EVIDENCE-{client_ref}"],
                "provenance": "document_observation",
            },
            {
                "facet_id": f"FACET-{client_ref}-INVESTMENT",
                "category": "planned_investment",
                "value": "Sostituzione di un veicolo strumentale nel 2027",
                "as_of_date": "2026-08-07",
                "evidence_refs": [],
                "provenance": "user_assertion",
            },
        ],
    }


def _evidence(client_ref: str = "CLIENT-001") -> dict[str, object]:
    return {
        "evidence_id": f"EVIDENCE-{client_ref}",
        "client_ref": client_ref,
        "evidence_kind": "document_receipt",
        "receipt_ref": f"RECEIPT-{client_ref}",
        "sha256": "a" * 64,
        "as_of_date": "2026-08-07",
        "description": "Synthetic immutable company-profile receipt.",
    }


def _source(client_refs: list[str] | None = None) -> dict[str, object]:
    return {
        "source_id": "SOURCE-REGION",
        "authority_level": "regional",
        "publisher": "Regione Veneto",
        "official_url": "https://www.regione.veneto.it/bandi",
        "relevance_rationale": "Fonte ufficiale regionale pertinente al territorio dei profili.",
        "profile_refs": client_refs or ["CLIENT-001"],
        "next_check_on": "2026-08-08",
    }


def _opportunity(
    *, history: list[dict[str, object]] | None = None
) -> dict[str, object]:
    observations = history or [
        {
            "observation_id": "OBS-001",
            "status": "upcoming",
            "effective_date": "2026-09-01",
            "observed_at": "2026-08-07T10:00:00+00:00",
            "source_ids": ["SOURCE-REGION"],
            "rationale": "La fonte ufficiale annuncia una prossima apertura.",
        }
    ]
    return {
        "opportunity_id": "OPP-001",
        "official_title": "Bando veicoli strumentali 2026",
        "issuer": "Regione Veneto",
        "official_url": "https://www.regione.veneto.it/bandi/veicoli-2026",
        "source_ids": ["SOURCE-REGION"],
        "opening_date": "2026-09-01",
        "closing_date": "2026-09-03",
        "summary": "Misura sintetica usata esclusivamente per provare il contratto radar.",
        "lifecycle_history": observations,
    }


def _match(client_ref: str = "CLIENT-001") -> dict[str, object]:
    return {
        "match_id": f"MATCH-{client_ref}",
        "opportunity_id": "OPP-001",
        "client_ref": client_ref,
        "compatibility": "high",
        "rationale": [
            "Il progetto dichiarato appare tematicamente compatibile; i requisiti restano da istruire sul bando."
        ],
        "profile_facet_ids": [f"FACET-{client_ref}-INVESTMENT"],
        "source_ids": ["SOURCE-REGION"],
        "missing_information": ["Preventivo aggiornato"],
        "contradictions": [],
        "application_complexity": "simple",
        "economic_estimate": {
            "currency": "EUR",
            "gross_benefit_min": "8000",
            "gross_benefit_max": "12000",
            "preparation_cost_min": "500",
            "preparation_cost_max": "1000",
            "net_value_min": "7000",
            "net_value_max": "11500",
            "methodology": "gross_benefit_range_minus_preparation_cost_range",
            "assumptions": [
                "Importi lordi e costo pratica sono stime da verificare professionalmente."
            ],
        },
        "recommended_action": "contact_client",
    }


def _contribution_args() -> dict[str, str]:
    return {
        "origin": "model_suggested",
        "provider": "openai",
        "model": "gpt-test-pinned",
        "prompt_template_version": "bandi-radar-v1",
        "recorded_by": "codex-local",
    }


def _initialized_radar(
    tmp_path: Path, *, scope: str = "single_client"
) -> tuple[ModuleType, Path]:
    radar = _radar_module()
    workspace = tmp_path / "private-radar"
    radar.initialize_radar(
        workspace,
        radar_id="RADAR-001",
        workspace_id="WORKSPACE-001",
        reference_date="2026-08-07",
        scope=scope,
        authorized_by="reviewer-001",
        retention_owner="Studio Demo",
        confirmed_by_user=True,
    )
    return radar, workspace


def _record_baseline(
    radar: ModuleType, workspace: Path, *, client_refs: list[str] | None = None
) -> None:
    refs = client_refs or ["CLIENT-001"]
    for index, client_ref in enumerate(refs, start=1):
        radar.record_profile_evidence(
            workspace,
            evidence=_evidence(client_ref),
            idempotency_key=f"evidence-{index}",
            **_contribution_args(),
        )
        radar.record_profile(
            workspace,
            profile=_profile(client_ref),
            idempotency_key=f"profile-{index}",
            **_contribution_args(),
        )
    radar.record_source(
        workspace,
        source=_source(refs),
        idempotency_key="source-1",
        **_contribution_args(),
    )


def _record_evidence(
    radar: ModuleType,
    workspace: Path,
    client_ref: str = "CLIENT-001",
    key: str = "evidence-1",
) -> None:
    radar.record_profile_evidence(
        workspace,
        evidence=_evidence(client_ref),
        idempotency_key=key,
        **_contribution_args(),
    )


def _review(
    radar: ModuleType, workspace: Path, *, scope: str, target_id: str, key: str
) -> dict[str, object]:
    return radar.review_item(
        workspace,
        scope=scope,
        target_id=target_id,
        decision="accepted",
        reviewer_id="reviewer-001",
        reviewer_role="commercialista",
        confirmed_by_user=True,
        idempotency_key=key,
    )


def _record_reviewed_source_check(
    radar: ModuleType, workspace: Path, *, key_suffix: str = "1"
) -> None:
    radar.record_source_check(
        workspace,
        source_id="SOURCE-REGION",
        check_status="checked",
        checked_at="2026-08-07T11:00:00+00:00",
        next_check_on="2026-08-08",
        result_count=3,
        error_code=None,
        idempotency_key=f"source-check-{key_suffix}",
    )
    _review(
        radar,
        workspace,
        scope="source_check",
        target_id="SOURCE-REGION",
        key=f"review-source-check-{key_suffix}",
    )


def _confirmed_radar(radar: ModuleType, workspace: Path) -> None:
    _record_baseline(radar, workspace)
    radar.record_opportunity(
        workspace,
        opportunity=_opportunity(),
        idempotency_key="opportunity-1",
        **_contribution_args(),
    )
    radar.record_match(
        workspace,
        match=_match(),
        idempotency_key="match-1",
        **_contribution_args(),
    )
    _record_reviewed_source_check(radar, workspace)
    for scope, target, key in (
        ("evidence", "EVIDENCE-CLIENT-001", "review-evidence"),
        ("profile", "CLIENT-001", "review-profile"),
        ("source", "SOURCE-REGION", "review-source"),
        ("opportunity", "OPP-001", "review-opportunity"),
        ("match", "MATCH-CLIENT-001", "review-match"),
    ):
        _review(radar, workspace, scope=scope, target_id=target, key=key)


def test_radar_initialization_is_private_schema_valid_and_idempotent(
    tmp_path: Path,
) -> None:
    radar, workspace = _initialized_radar(tmp_path)

    repeated = radar.initialize_radar(
        workspace,
        radar_id="RADAR-001",
        workspace_id="WORKSPACE-001",
        reference_date="2026-08-07",
        scope="single_client",
        authorized_by="reviewer-001",
        retention_owner="Studio Demo",
        confirmed_by_user=True,
    )
    payload = radar.load_validated_radar(workspace)

    assert repeated == workspace / "opportunity_radar.json"
    assert payload["source_plan"]["coverage"]["statement"].endswith(
        "not the probability that all opportunities were found."
    )
    assert stat.S_IMODE(repeated.stat().st_mode) == 0o600
    assert stat.S_IMODE(workspace.stat().st_mode) == 0o700


def test_single_client_radar_rejects_a_second_profile(tmp_path: Path) -> None:
    radar, workspace = _initialized_radar(tmp_path)
    _record_evidence(radar, workspace)
    radar.record_profile(
        workspace,
        profile=_profile("CLIENT-001"),
        idempotency_key="profile-1",
        **_contribution_args(),
    )

    _record_evidence(radar, workspace, "CLIENT-002", "evidence-2")
    with pytest.raises(ValueError, match="cannot contain more than one profile"):
        radar.record_profile(
            workspace,
            profile=_profile("CLIENT-002"),
            idempotency_key="profile-2",
            **_contribution_args(),
        )

    assert len(radar.load_validated_radar(workspace)["profiles"]) == 1


def test_source_coverage_counts_checked_plan_not_discovery_probability(
    tmp_path: Path,
) -> None:
    radar, workspace = _initialized_radar(tmp_path)
    _record_baseline(radar, workspace)
    _review(
        radar,
        workspace,
        scope="source",
        target_id="SOURCE-REGION",
        key="review-source-plan",
    )

    radar.record_source_check(
        workspace,
        source_id="SOURCE-REGION",
        check_status="checked",
        checked_at="2026-08-07T11:00:00+00:00",
        next_check_on="2026-08-08",
        result_count=3,
        error_code=None,
        idempotency_key="source-check-1",
    )
    _review(
        radar,
        workspace,
        scope="source_check",
        target_id="SOURCE-REGION",
        key="review-source-check",
    )
    coverage = radar.load_validated_radar(workspace)["source_plan"]["coverage"]

    assert coverage == {
        "plan_entry_count": 1,
        "planned_count": 1,
        "completed_count": 1,
        "unavailable_count": 0,
        "failed_count": 0,
        "unreviewed_count": 0,
        "check_review_pending_count": 0,
        "ratio_basis_points": 10000,
        "status": "planned_sources_checked",
        "statement": "1/1 professionally confirmed applicable plan sources checked and review-confirmed; 0 unreviewed plan entries excluded; this measures execution of the reviewed plan, not the probability that all opportunities were found.",
    }


def test_record_retry_is_idempotent_and_conflicting_retry_is_rejected(
    tmp_path: Path,
) -> None:
    radar, workspace = _initialized_radar(tmp_path)
    _record_evidence(radar, workspace)
    args = {
        "workspace": workspace,
        "profile": _profile(),
        "idempotency_key": "profile-1",
        **_contribution_args(),
    }

    first = radar.record_profile(**args)
    repeated = radar.record_profile(**args)
    conflicting = _profile()
    conflicting["facets"][0]["value"] = "Provincia diversa"  # type: ignore[index]
    with pytest.raises(ValueError, match="idempotency key already used"):
        radar.record_profile(**{**args, "profile": conflicting})

    payload = radar.load_validated_radar(workspace)
    assert repeated == first
    assert len(payload["profiles"]) == 1
    assert len(payload["operations"]) == 2


def test_secret_fields_are_rejected_without_mutating_radar(tmp_path: Path) -> None:
    radar, workspace = _initialized_radar(tmp_path)
    profile = _profile()
    profile["token"] = "synthetic-secret"

    with pytest.raises(ValueError, match="prohibited secret/session fields"):
        radar.record_profile(
            workspace,
            profile=profile,
            idempotency_key="profile-secret",
            **_contribution_args(),
        )

    payload = radar.load_validated_radar(workspace)
    assert payload["profiles"] == []
    assert payload["operations"] == []


def test_bidirectional_portfolio_matching_preserves_opaque_client_refs(
    tmp_path: Path,
) -> None:
    radar, workspace = _initialized_radar(tmp_path, scope="portfolio")
    _record_baseline(radar, workspace, client_refs=["CLIENT-001", "CLIENT-002"])
    radar.record_opportunity(
        workspace,
        opportunity=_opportunity(),
        idempotency_key="opportunity-1",
        **_contribution_args(),
    )
    for index, client_ref in enumerate(("CLIENT-001", "CLIENT-002"), start=1):
        radar.record_match(
            workspace,
            match=_match(client_ref),
            idempotency_key=f"match-{index}",
            **_contribution_args(),
        )

    payload = radar.load_validated_radar(workspace)

    assert {item["client_ref"] for item in payload["matches"]} == {
        "CLIENT-001",
        "CLIENT-002",
    }
    assert all("legal_name" not in item for item in payload["profiles"])


def test_match_rejects_cross_client_facet_and_inexact_economic_range(
    tmp_path: Path,
) -> None:
    radar, workspace = _initialized_radar(tmp_path, scope="portfolio")
    _record_baseline(radar, workspace, client_refs=["CLIENT-001", "CLIENT-002"])
    radar.record_opportunity(
        workspace,
        opportunity=_opportunity(),
        idempotency_key="opportunity-1",
        **_contribution_args(),
    )
    cross_client = _match("CLIENT-002")
    cross_client["profile_facet_ids"] = ["FACET-CLIENT-001-INVESTMENT"]
    with pytest.raises(ValueError, match="another client's facet"):
        radar.record_match(
            workspace,
            match=cross_client,
            idempotency_key="match-cross-client",
            **_contribution_args(),
        )
    inexact = _match("CLIENT-001")
    inexact["economic_estimate"]["net_value_min"] = "7001"  # type: ignore[index]
    with pytest.raises(ValueError, match="does not reproduce exactly"):
        radar.record_match(
            workspace,
            match=inexact,
            idempotency_key="match-inexact",
            **_contribution_args(),
        )

    assert radar.load_validated_radar(workspace)["matches"] == []


def test_review_requires_explicit_confirmation_and_handoff_requires_all_reviews(
    tmp_path: Path,
) -> None:
    radar, workspace = _initialized_radar(tmp_path)
    _record_baseline(radar, workspace)
    radar.record_opportunity(
        workspace,
        opportunity=_opportunity(),
        idempotency_key="opportunity-1",
        **_contribution_args(),
    )
    radar.record_match(
        workspace,
        match=_match(),
        idempotency_key="match-1",
        **_contribution_args(),
    )
    with pytest.raises(ValueError, match="explicit user confirmation"):
        radar.review_item(
            workspace,
            scope="profile",
            target_id="CLIENT-001",
            decision="accepted",
            reviewer_id="reviewer-001",
            reviewer_role="commercialista",
            confirmed_by_user=False,
            idempotency_key="review-profile",
        )
    with pytest.raises(ValueError, match="must be professionally confirmed"):
        radar.create_handoff(
            workspace,
            match_id="MATCH-CLIENT-001",
            output_path=workspace / "handoff.json",
        )

    _record_reviewed_source_check(radar, workspace)
    _review(
        radar,
        workspace,
        scope="evidence",
        target_id="EVIDENCE-CLIENT-001",
        key="review-evidence",
    )
    _review(
        radar, workspace, scope="profile", target_id="CLIENT-001", key="review-profile"
    )
    _review(
        radar, workspace, scope="source", target_id="SOURCE-REGION", key="review-source"
    )
    _review(
        radar,
        workspace,
        scope="opportunity",
        target_id="OPP-001",
        key="review-opportunity",
    )
    _review(
        radar,
        workspace,
        scope="match",
        target_id="MATCH-CLIENT-001",
        key="review-match",
    )
    handoff_path = radar.create_handoff(
        workspace,
        match_id="MATCH-CLIENT-001",
        output_path=workspace / "handoff.json",
    )
    handoff = _read(handoff_path)

    assert handoff["client_ref"] == "CLIENT-001"
    assert handoff["opportunity"]["review_status"] == "confirmed"  # type: ignore[index]
    assert handoff["match"]["review_status"] == "confirmed"  # type: ignore[index]


def test_handoff_hashes_exact_radar_and_report_discloses_boundaries(
    tmp_path: Path,
) -> None:
    radar, workspace = _initialized_radar(tmp_path)
    _record_baseline(radar, workspace)
    radar.record_opportunity(
        workspace,
        opportunity=_opportunity(),
        idempotency_key="opportunity-1",
        **_contribution_args(),
    )
    radar.record_match(
        workspace,
        match=_match(),
        idempotency_key="match-1",
        **_contribution_args(),
    )
    for scope, target, key in (
        ("evidence", "EVIDENCE-CLIENT-001", "review-evidence"),
        ("profile", "CLIENT-001", "review-profile"),
        ("source", "SOURCE-REGION", "review-source"),
        ("opportunity", "OPP-001", "review-opportunity"),
        ("match", "MATCH-CLIENT-001", "review-match"),
    ):
        _review(radar, workspace, scope=scope, target_id=target, key=key)
    _record_reviewed_source_check(radar, workspace)
    handoff_path = radar.create_handoff(
        workspace,
        match_id="MATCH-CLIENT-001",
        output_path=workspace / "handoff.json",
    )
    report_path = radar.render_radar_report(workspace)

    handoff = _read(handoff_path)
    assert handoff["source_entries_sha256"] == radar.canonical_json_sha256(
        handoff["source_plan_entries"]
    )
    radar.validate_opportunity_handoff_payload(handoff)
    report = report_path.read_text(encoding="utf-8")
    assert "not the probability that all opportunities were found" in report
    assert "NESSUN CLIENTE CONTATTATO, NESSUNA DOMANDA INVIATA" in report


def test_confirmed_lifecycle_history_can_only_be_extended(tmp_path: Path) -> None:
    radar, workspace = _initialized_radar(tmp_path)
    _record_baseline(radar, workspace)
    initial = _opportunity()
    radar.record_opportunity(
        workspace,
        opportunity=initial,
        idempotency_key="opportunity-1",
        **_contribution_args(),
    )
    _review(
        radar,
        workspace,
        scope="opportunity",
        target_id="OPP-001",
        key="review-opportunity-1",
    )
    history = initial["lifecycle_history"] + [  # type: ignore[operator]
        {
            "observation_id": "OBS-002",
            "status": "open",
            "effective_date": "2026-09-01",
            "observed_at": "2026-09-01T08:00:00+00:00",
            "source_ids": ["SOURCE-REGION"],
            "rationale": "La fonte ufficiale indica che la finestra è aperta.",
        }
    ]
    radar.record_opportunity(
        workspace,
        opportunity={
            **_opportunity(history=history),
            "revision_event": {
                "revision_id": "OPP-REV-002",
                "observed_at": "2026-09-01T08:00:00+00:00",
                "rationale": "The official source now reports the opening.",
            },
        },
        idempotency_key="opportunity-2",
        **_contribution_args(),
    )
    opportunity = radar.load_validated_radar(workspace)["opportunities"][0]

    assert opportunity["current_lifecycle"] == "open"
    assert opportunity["lifecycle_history"][0]["review_status"] == "confirmed"
    assert opportunity["lifecycle_history"][1]["review_status"] == "proposed"
    assert opportunity["review_status"] == "proposed"


def test_monitoring_scan_is_resumable_but_completed_scan_is_immutable(
    tmp_path: Path,
) -> None:
    radar, workspace = _initialized_radar(tmp_path)
    _record_baseline(radar, workspace)
    running = {
        "scan_id": "SCAN-001",
        "started_at": "2026-08-07T10:00:00+00:00",
        "completed_at": None,
        "source_ids": ["SOURCE-REGION"],
        "outcome": "running",
        "error_codes": [],
    }
    radar.record_scan(
        workspace,
        scan=running,
        next_scan_on=None,
        idempotency_key="scan-start",
    )
    complete = {
        **running,
        "completed_at": "2026-08-07T10:05:00+00:00",
        "outcome": "complete",
    }
    radar.record_scan(
        workspace,
        scan=complete,
        next_scan_on="2026-08-08",
        idempotency_key="scan-finish",
    )
    with pytest.raises(ValueError, match="completed scan cannot be overwritten"):
        radar.record_scan(
            workspace,
            scan={**complete, "outcome": "partial"},
            next_scan_on="2026-08-08",
            idempotency_key="scan-rewrite",
        )

    monitoring = radar.load_validated_radar(workspace)["monitoring"]
    assert monitoring["next_scan_on"] == "2026-08-08"
    assert monitoring["scan_history"][0]["outcome"] == "complete"


def test_workspace_requires_explicit_authorization_and_rejects_git_tree(
    tmp_path: Path,
) -> None:
    radar = _radar_module()
    with pytest.raises(ValueError, match="explicit user confirmation"):
        radar.initialize_radar(
            tmp_path / "unauthorized",
            radar_id="RADAR-001",
            workspace_id="WORKSPACE-001",
            reference_date="2026-08-07",
            scope="portfolio",
            authorized_by="reviewer-001",
            retention_owner="Studio Demo",
            confirmed_by_user=False,
        )
    with pytest.raises(PermissionError, match="Git worktree"):
        radar.initialize_radar(
            ROOT / "synthetic-radar-output",
            radar_id="RADAR-001",
            workspace_id="WORKSPACE-001",
            reference_date="2026-08-07",
            scope="portfolio",
            authorized_by="reviewer-001",
            retention_owner="Studio Demo",
            confirmed_by_user=True,
        )


def test_unreviewed_source_is_excluded_from_reviewed_plan_coverage(
    tmp_path: Path,
) -> None:
    radar, workspace = _initialized_radar(tmp_path)
    _record_baseline(radar, workspace)

    coverage = radar.load_validated_radar(workspace)["source_plan"]["coverage"]

    assert coverage["plan_entry_count"] == 1
    assert coverage["planned_count"] == 0
    assert coverage["unreviewed_count"] == 1
    assert coverage["status"] == "plan_unreviewed"


@pytest.mark.parametrize("decision", ["returned", "rejected"])
def test_nonaccepted_source_is_excluded_from_reviewed_plan_coverage(
    tmp_path: Path, decision: str
) -> None:
    radar, workspace = _initialized_radar(tmp_path)
    _record_baseline(radar, workspace)

    radar.review_item(
        workspace,
        scope="source",
        target_id="SOURCE-REGION",
        decision=decision,
        reviewer_id="reviewer-001",
        reviewer_role="commercialista",
        confirmed_by_user=True,
        idempotency_key=f"review-source-{decision}",
    )
    coverage = radar.load_validated_radar(workspace)["source_plan"]["coverage"]

    assert coverage["planned_count"] == 0
    assert coverage["unreviewed_count"] == 1


def test_profile_cannot_reference_another_clients_evidence(tmp_path: Path) -> None:
    radar, workspace = _initialized_radar(tmp_path, scope="portfolio")
    _record_evidence(radar, workspace, "CLIENT-001", "evidence-client-1")
    profile = _profile("CLIENT-002")
    profile["facets"][0]["evidence_refs"] = [  # type: ignore[index]
        "EVIDENCE-CLIENT-001"
    ]

    with pytest.raises(ValueError, match="another client's evidence"):
        radar.record_profile(
            workspace,
            profile=profile,
            idempotency_key="profile-cross-client-evidence",
            **_contribution_args(),
        )


def test_source_check_change_invalidates_review_and_blocks_handoff(
    tmp_path: Path,
) -> None:
    radar, workspace = _initialized_radar(tmp_path)
    _confirmed_radar(radar, workspace)

    changed = radar.record_source_check(
        workspace,
        source_id="SOURCE-REGION",
        check_status="failed",
        checked_at="2026-08-08T11:00:00+00:00",
        next_check_on="2026-08-09",
        result_count=None,
        error_code="temporary_failure",
        idempotency_key="source-check-failed",
    )

    assert changed["review_status"] == "confirmed"
    assert changed["check_review_status"] == "proposed"
    with pytest.raises(ValueError, match="checked and professionally confirmed"):
        radar.create_handoff(
            workspace,
            match_id="MATCH-CLIENT-001",
            output_path=workspace / "blocked-handoff.json",
        )


def test_handoff_rejects_tampering_and_schema_rejects_empty_objects(
    tmp_path: Path,
) -> None:
    radar, workspace = _initialized_radar(tmp_path)
    _confirmed_radar(radar, workspace)
    handoff_path = radar.create_handoff(
        workspace,
        match_id="MATCH-CLIENT-001",
        output_path=workspace / "handoff.json",
    )
    payload = _read(handoff_path)
    payload["match"]["rationale"] = ["Tampered rationale"]  # type: ignore[index]

    with pytest.raises(ValueError, match="selection hash"):
        radar.validate_opportunity_handoff_payload(payload)

    malformed = _read(handoff_path)
    malformed["opportunity"] = {}
    assert radar.validate_artifact_schema("opportunity_handoff", malformed)


def test_formal_amendment_revises_deadline_and_invalidates_match(
    tmp_path: Path,
) -> None:
    radar, workspace = _initialized_radar(tmp_path)
    _confirmed_radar(radar, workspace)
    amended = _opportunity(
        history=[
            *_opportunity()["lifecycle_history"],  # type: ignore[list-item]
            {
                "observation_id": "OBS-002",
                "status": "open",
                "effective_date": "2026-09-01",
                "observed_at": "2026-08-08T10:00:00+00:00",
                "source_ids": ["SOURCE-REGION"],
                "rationale": "A formal amendment extends the closing date.",
            },
        ]
    )
    amended["closing_date"] = "2026-09-10"
    amended["revision_event"] = {
        "revision_id": "OPP-REV-002",
        "observed_at": "2026-08-08T10:00:00+00:00",
        "rationale": "The reviewed formal amendment extends the deadline.",
    }

    result = radar.record_opportunity(
        workspace,
        opportunity=amended,
        idempotency_key="opportunity-amendment",
        **_contribution_args(),
    )
    current = radar.load_validated_radar(workspace)

    assert result["closing_date"] == "2026-09-10"
    assert result["revision"] == 2
    assert result["review_status"] == "proposed"
    assert current["matches"][0]["review_status"] == "proposed"


def test_confirmed_profile_revision_preserves_history_and_invalidates_match(
    tmp_path: Path,
) -> None:
    radar, workspace = _initialized_radar(tmp_path)
    _confirmed_radar(radar, workspace)
    revised = _profile()
    revised["facets"][1]["value"] = (  # type: ignore[index]
        "Sostituzione di due veicoli strumentali nel 2027"
    )
    revised["revision_event"] = {
        "revision_id": "PROFILE-REV-002",
        "observed_at": "2026-08-08T10:00:00+00:00",
        "rationale": "The professional supplied a revised investment plan.",
    }

    result = radar.record_profile(
        workspace,
        profile=revised,
        idempotency_key="profile-revision",
        **_contribution_args(),
    )
    current = radar.load_validated_radar(workspace)

    assert result["revision"] == 2
    assert result["revision_history"][0]["previous_sha256"]
    assert result["review_status"] == "proposed"
    assert current["matches"][0]["review_status"] == "proposed"


def test_scan_cannot_complete_before_it_starts(tmp_path: Path) -> None:
    radar, workspace = _initialized_radar(tmp_path)
    _record_baseline(radar, workspace)

    with pytest.raises(ValueError, match="completes before it starts"):
        radar.record_scan(
            workspace,
            scan={
                "scan_id": "SCAN-INVALID",
                "started_at": "2026-08-07T11:00:00+00:00",
                "completed_at": "2026-08-07T10:00:00+00:00",
                "source_ids": ["SOURCE-REGION"],
                "outcome": "failed",
                "error_codes": ["clock_error"],
            },
            next_scan_on=None,
            idempotency_key="scan-invalid",
        )


def test_unknown_profile_evidence_and_nonchronological_history_are_rejected(
    tmp_path: Path,
) -> None:
    radar, workspace = _initialized_radar(tmp_path)
    profile = _profile()
    profile["facets"][0]["evidence_refs"] = ["UNKNOWN-EVIDENCE"]  # type: ignore[index]
    with pytest.raises(ValueError, match="unknown evidence"):
        radar.record_profile(
            workspace,
            profile=profile,
            idempotency_key="profile-unknown-evidence",
            **_contribution_args(),
        )

    _record_baseline(radar, workspace)
    history = [
        {
            "observation_id": "OBS-001",
            "status": "open",
            "effective_date": "2026-09-01",
            "observed_at": "2026-08-08T10:00:00+00:00",
            "source_ids": ["SOURCE-REGION"],
            "rationale": "Later observation.",
        },
        {
            "observation_id": "OBS-002",
            "status": "upcoming",
            "effective_date": "2026-09-01",
            "observed_at": "2026-08-07T10:00:00+00:00",
            "source_ids": ["SOURCE-REGION"],
            "rationale": "Earlier observation appended last.",
        },
    ]
    with pytest.raises(ValueError, match="not chronological"):
        radar.record_opportunity(
            workspace,
            opportunity=_opportunity(history=history),
            idempotency_key="opportunity-out-of-order",
            **_contribution_args(),
        )


def test_public_radar_schemas_are_registered_and_valid() -> None:
    jsonschema = pytest.importorskip("jsonschema")
    schema_validation = _module_from_path(
        "radar_schema_registration", SCRIPTS_ROOT / "schema_validation.py"
    )

    for artifact in ("opportunity_radar", "opportunity_handoff"):
        schema_path = (
            PLUGIN_ROOT / "schemas" / schema_validation.ARTIFACT_SCHEMAS[artifact]
        )
        jsonschema.Draft202012Validator.check_schema(_read(schema_path))


def test_radar_cli_initializes_records_profile_and_renders_report(
    tmp_path: Path,
) -> None:
    radar = _radar_module()
    workspace = tmp_path / "cli-radar"
    profile_path = tmp_path / "profile.json"
    evidence_path = tmp_path / "evidence.json"
    profile_path.write_text(json.dumps(_profile()), encoding="utf-8")
    evidence_path.write_text(json.dumps(_evidence()), encoding="utf-8")

    initialized = radar.main(
        [
            "--workspace",
            str(workspace),
            "initialize",
            "--radar-id",
            "RADAR-CLI-001",
            "--workspace-id",
            "WORKSPACE-CLI-001",
            "--reference-date",
            "2026-08-07",
            "--scope",
            "single_client",
            "--authorized-by",
            "reviewer-001",
            "--retention-owner",
            "Studio Demo",
            "--confirmed-by-user",
        ]
    )
    evidence_recorded = radar.main(
        [
            "--workspace",
            str(workspace),
            "record-evidence",
            "--input",
            str(evidence_path),
            "--idempotency-key",
            "evidence-cli-1",
            "--origin",
            "document_observation",
            "--provider",
            "openai",
            "--model",
            "gpt-test-pinned",
            "--prompt-template-version",
            "bandi-radar-v1",
            "--recorded-by",
            "codex-local",
        ]
    )
    recorded = radar.main(
        [
            "--workspace",
            str(workspace),
            "record-profile",
            "--input",
            str(profile_path),
            "--idempotency-key",
            "profile-cli-1",
            "--origin",
            "model_suggested",
            "--provider",
            "openai",
            "--model",
            "gpt-test-pinned",
            "--prompt-template-version",
            "bandi-radar-v1",
            "--recorded-by",
            "codex-local",
        ]
    )
    rendered = radar.main(["--workspace", str(workspace), "report"])

    assert initialized == 0
    assert evidence_recorded == 0
    assert recorded == 0
    assert rendered == 0
    assert (workspace / "opportunity_radar_review.md").is_file()
