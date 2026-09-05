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
        "discovery_role": "priority_direct",
        "source_surface": "funding_portal",
        "territories": ["Regione Veneto"],
        "categories": ["artigianato", "investimenti"],
        "act_families": ["dgr", "ddr", "bur_issue", "annex", "amendment"],
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


def _contribution_args(
    model_session_ref: str = "SESSION-PUBLIC-001",
) -> dict[str, str]:
    return {
        "origin": "model_suggested",
        "provider": "openai",
        "model": "gpt-test-pinned",
        "prompt_template_version": "bandi-radar-v1",
        "recorded_by": "codex-local",
        "model_session_ref": model_session_ref,
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
            **_contribution_args(f"SESSION-{client_ref}"),
        )
        radar.record_profile(
            workspace,
            profile=_profile(client_ref),
            idempotency_key=f"profile-{index}",
            **_contribution_args(f"SESSION-{client_ref}"),
        )
    radar.record_source(
        workspace,
        source=_source(refs),
        idempotency_key="source-1",
        **_contribution_args("SESSION-SOURCE-001"),
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
        **_contribution_args(f"SESSION-{client_ref}"),
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


def _scan(
    *,
    scan_id: str = "SCAN-001",
    started_at: str = "2026-08-07T10:00:00+00:00",
    completed_at: str | None = None,
    outcome: str = "running",
    semantic_web_check: dict[str, object] | None = None,
    territories: list[str] | None = None,
    categories: list[str] | None = None,
    source_selection: dict[str, object] | None = None,
) -> dict[str, object]:
    query_territories = territories or ["Regione Veneto"]
    query_categories = categories or ["artigianato"]
    return {
        "scan_id": scan_id,
        "query_context": {
            "territories": query_territories,
            "categories": query_categories,
            "request_summary": (
                "Ricerca sintetica per " + ", ".join(query_territories)
            ),
        },
        "source_selection": source_selection
        or _source_selection(
            territories=query_territories,
            categories=query_categories,
        ),
        "started_at": started_at,
        "completed_at": completed_at,
        "window_start": "2026-06-09",
        "window_end": "2026-08-07",
        "semantic_web_check": semantic_web_check
        or {
            "status": "not_run",
            "checked_at": None,
            "result_count": None,
            "error_code": None,
        },
        "outcome": outcome,
        "error_codes": [],
    }


def _source_selection(
    *,
    territories: list[str] | None = None,
    categories: list[str] | None = None,
    priority_source_ids: list[str] | None = None,
    supplemental_source_ids: list[str] | None = None,
    gaps: set[tuple[str, str]] | None = None,
) -> dict[str, object]:
    selected_priority = (
        ["SOURCE-REGION"] if priority_source_ids is None else priority_source_ids
    )
    selected_supplemental = (
        [] if supplemental_source_ids is None else supplemental_source_ids
    )
    selected_ids = [*selected_priority, *selected_supplemental]
    gap_keys = gaps or set()
    claims: list[dict[str, object]] = []
    for dimension, values in (
        ("territory", territories or ["Regione Veneto"]),
        ("category", categories or ["artigianato"]),
    ):
        for value in values:
            is_gap = (dimension, value) in gap_keys
            claims.append(
                {
                    "dimension": dimension,
                    "query_value": value,
                    "status": "gap" if is_gap else "covered",
                    "source_ids": [] if is_gap else selected_ids,
                    "rationale": (
                        "Nessuna fonte ancora selezionata per questa dimensione."
                        if is_gap
                        else "La pertinenza è proposta semanticamente per revisione professionale."
                    ),
                }
            )
    return {
        "priority_source_ids": selected_priority,
        "supplemental_source_ids": selected_supplemental,
        "scope_coverage": claims,
        "selection_rationale": "Selezione sintetica query-scoped per il test pubblico.",
    }


def _start_scan(
    radar: ModuleType,
    workspace: Path,
    *,
    scan_id: str = "SCAN-001",
    key: str = "scan-start",
    started_at: str = "2026-08-07T10:00:00+00:00",
    source_selection: dict[str, object] | None = None,
    review_selection: bool = True,
    territories: list[str] | None = None,
    categories: list[str] | None = None,
) -> None:
    radar.record_scan(
        workspace,
        scan=_scan(
            scan_id=scan_id,
            started_at=started_at,
            territories=territories,
            categories=categories,
            source_selection=source_selection,
        ),
        next_scan_on=None,
        idempotency_key=key,
        **_contribution_args(),
    )
    if review_selection:
        _review(
            radar,
            workspace,
            scope="scan_source_selection",
            target_id=scan_id,
            key=f"{key}-selection-review",
        )


def _record_reviewed_source_check(
    radar: ModuleType, workspace: Path, *, key_suffix: str = "1"
) -> None:
    scan_id = f"SCAN-{key_suffix}"
    _start_scan(
        radar,
        workspace,
        scan_id=scan_id,
        key=f"scan-start-{key_suffix}",
    )
    radar.record_source_check(
        workspace,
        source_id="SOURCE-REGION",
        check_id=f"CHECK-{key_suffix}",
        scan_id=scan_id,
        check_status="checked",
        checked_at="2026-08-07T11:00:00+00:00",
        window_start="2026-06-09",
        window_end="2026-08-07",
        next_check_on="2026-08-08",
        result_count=3,
        error_code=None,
        cursor_after={
            "external_id": f"BUR-2026-{key_suffix}",
            "publication_date": "2026-08-07",
            "official_url": "https://bur.regione.veneto.it/",
        },
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
    _review(
        radar,
        workspace,
        scope="source",
        target_id="SOURCE-REGION",
        key="review-source",
    )
    _record_reviewed_source_check(radar, workspace)
    for scope, target, key in (
        ("evidence", "EVIDENCE-CLIENT-001", "review-evidence"),
        ("profile", "CLIENT-001", "review-profile"),
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
            **_contribution_args("SESSION-CLIENT-002"),
        )
    assert len(radar.load_validated_radar(workspace)["profiles"]) == 1


def test_portfolio_client_mapping_sessions_cannot_cross_clients(
    tmp_path: Path,
) -> None:
    radar, workspace = _initialized_radar(tmp_path, scope="portfolio")
    radar.record_profile_evidence(
        workspace,
        evidence=_evidence("CLIENT-001"),
        idempotency_key="evidence-client-1",
        **_contribution_args("SESSION-CLIENT-MAP-001"),
    )

    with pytest.raises(ValueError, match="cannot be reused for another client"):
        radar.record_profile_evidence(
            workspace,
            evidence=_evidence("CLIENT-002"),
            idempotency_key="evidence-client-2",
            **_contribution_args("SESSION-CLIENT-MAP-001"),
        )


def test_portfolio_match_requires_session_separate_from_client_mapping(
    tmp_path: Path,
) -> None:
    radar, workspace = _initialized_radar(tmp_path, scope="portfolio")
    _record_baseline(radar, workspace)
    radar.record_opportunity(
        workspace,
        opportunity=_opportunity(),
        idempotency_key="opportunity-1",
        **_contribution_args("SESSION-PUBLIC-OPPORTUNITY"),
    )

    with pytest.raises(ValueError, match="separate from client-evidence mapping"):
        radar.record_match(
            workspace,
            match=_match(),
            idempotency_key="match-1",
            **_contribution_args("SESSION-CLIENT-001"),
        )


def test_public_discovery_sessions_cannot_reuse_client_mapping_sessions(
    tmp_path: Path,
) -> None:
    radar, workspace = _initialized_radar(tmp_path, scope="portfolio")
    radar.record_profile_evidence(
        workspace,
        evidence=_evidence("CLIENT-001"),
        idempotency_key="evidence-client-1",
        **_contribution_args("SESSION-CLIENT-MAP-001"),
    )

    with pytest.raises(ValueError, match="separate from client-evidence mapping"):
        radar.record_source(
            workspace,
            source=_source(["CLIENT-001"]),
            idempotency_key="source-reused-client-session",
            **_contribution_args("SESSION-CLIENT-MAP-001"),
        )


def test_client_mapping_sessions_cannot_reuse_public_discovery_sessions(
    tmp_path: Path,
) -> None:
    radar, workspace = _initialized_radar(tmp_path, scope="portfolio")
    source = _source()
    source["profile_refs"] = []
    radar.record_source(
        workspace,
        source=source,
        idempotency_key="source-public-session",
        **_contribution_args("SESSION-PUBLIC-DISCOVERY-001"),
    )

    with pytest.raises(ValueError, match="separate from public discovery"):
        radar.record_profile_evidence(
            workspace,
            evidence=_evidence("CLIENT-001"),
            idempotency_key="evidence-reused-public-session",
            **_contribution_args("SESSION-PUBLIC-DISCOVERY-001"),
        )


def test_radar_blocks_unmistakable_credentials_without_generic_pii_redaction(
    tmp_path: Path,
) -> None:
    radar, workspace = _initialized_radar(tmp_path)
    evidence = _evidence()
    evidence["description"] = "Codice fiscale 01234567890"
    radar.record_profile_evidence(
        workspace,
        evidence=evidence,
        idempotency_key="evidence-safe",
        **_contribution_args("SESSION-CLIENT-SAFE"),
    )
    profile = _profile()
    profile["facets"][0][
        "value"
    ] = "Authorization: Bearer abcdefghijklmnopqrstuvwxyz123456"

    with pytest.raises(ValueError, match="unmistakable credential/session"):
        radar.record_profile(
            workspace,
            profile=profile,
            idempotency_key="profile-secret",
            **_contribution_args("SESSION-CLIENT-SAFE"),
        )

    assert radar.load_validated_radar(workspace)["profiles"] == []


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

    _record_reviewed_source_check(radar, workspace, key_suffix="coverage")
    coverage = radar.load_validated_radar(workspace)["source_plan"]["coverage"]

    assert coverage == {
        "plan_entry_count": 1,
        "planned_count": 1,
        "completed_count": 1,
        "unavailable_count": 0,
        "failed_count": 0,
        "unreviewed_count": 0,
        "rejected_count": 0,
        "check_review_pending_count": 0,
        "ratio_basis_points": 10000,
        "status": "planned_sources_checked",
        "statement": "1/1 professionally confirmed applicable plan sources checked and review-confirmed; 0 pending plan entries and 0 rejected entries excluded; this measures execution of the reviewed plan, not the probability that all opportunities were found.",
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

    _review(
        radar,
        workspace,
        scope="source",
        target_id="SOURCE-REGION",
        key="review-source",
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
    _review(
        radar,
        workspace,
        scope="source",
        target_id="SOURCE-REGION",
        key="review-source-for-scan",
    )
    _start_scan(radar, workspace)
    worklist = radar.render_scan_worklist(workspace, scan_id="SCAN-001")
    radar.record_source_check(
        workspace,
        source_id="SOURCE-REGION",
        check_id="CHECK-SCAN-001",
        scan_id="SCAN-001",
        check_status="checked",
        checked_at="2026-08-07T11:00:00+00:00",
        window_start="2026-06-09",
        window_end="2026-08-07",
        next_check_on="2026-08-08",
        result_count=1,
        error_code=None,
        cursor_after={
            "external_id": "BUR-2026-098",
            "publication_date": "2026-08-07",
            "official_url": "https://bur.regione.veneto.it/",
        },
        idempotency_key="source-check-for-scan",
    )
    _review(
        radar,
        workspace,
        scope="source_check",
        target_id="SOURCE-REGION",
        key="review-source-check-for-scan",
    )
    complete = _scan(
        completed_at="2026-08-07T11:10:00+00:00",
        outcome="complete",
        semantic_web_check={
            "status": "checked",
            "checked_at": "2026-08-07T11:05:00+00:00",
            "result_count": 2,
            "error_code": None,
        },
    )
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
    assert monitoring["scan_history"][0]["coverage"]["status"] == (
        "priority_sources_verified"
    )
    assert "Ricerca web semantica complementare" in worklist.read_text(encoding="utf-8")


@pytest.mark.parametrize(
    ("check_status", "error_code"),
    [("failed", "publisher_unavailable"), ("unavailable", None)],
)
def test_complete_scan_rejects_unverified_priority_source_and_reports_gap(
    tmp_path: Path, check_status: str, error_code: str | None
) -> None:
    radar, workspace = _initialized_radar(tmp_path)
    _record_baseline(radar, workspace)
    _review(
        radar,
        workspace,
        scope="source",
        target_id="SOURCE-REGION",
        key="review-source-gap",
    )
    _start_scan(radar, workspace, scan_id="SCAN-GAP", key="scan-gap-start")
    radar.record_source_check(
        workspace,
        source_id="SOURCE-REGION",
        check_id="CHECK-GAP",
        scan_id="SCAN-GAP",
        check_status=check_status,
        checked_at="2026-08-07T11:00:00+00:00",
        window_start="2026-06-09",
        window_end="2026-08-07",
        next_check_on="2026-08-08",
        result_count=None,
        error_code=error_code,
        cursor_after=None,
        idempotency_key="source-check-gap",
    )
    _review(
        radar,
        workspace,
        scope="source_check",
        target_id="SOURCE-REGION",
        key="review-source-check-gap",
    )
    terminal = _scan(
        scan_id="SCAN-GAP",
        completed_at="2026-08-07T11:05:00+00:00",
        outcome="complete",
    )

    with pytest.raises(
        ValueError, match="source selection, query scope, or priority sources"
    ):
        radar.record_scan(
            workspace,
            scan=terminal,
            next_scan_on="2026-08-08",
            idempotency_key="scan-gap-complete",
        )

    radar.record_scan(
        workspace,
        scan={**terminal, "outcome": "partial"},
        next_scan_on="2026-08-08",
        idempotency_key="scan-gap-partial",
    )
    scan = radar.load_validated_radar(workspace)["monitoring"]["scan_history"][0]
    report = radar.render_radar_report(workspace).read_text(encoding="utf-8")

    assert scan["coverage"]["unverified_priority_source_ids"] == ["SOURCE-REGION"]
    assert scan["coverage"]["status"] == "partial"
    assert "Fonti prioritarie non verificate: SOURCE-REGION" in report
    assert "2026-06-09 → 2026-08-07" in report


def test_query_scope_requires_exact_claims_and_professional_review(
    tmp_path: Path,
) -> None:
    radar, workspace = _initialized_radar(tmp_path)
    _record_baseline(radar, workspace)
    _review(
        radar,
        workspace,
        scope="source",
        target_id="SOURCE-REGION",
        key="review-source-query-scope",
    )
    mismatched = _source_selection()

    with pytest.raises(ValueError, match="every query territory and category"):
        radar.record_scan(
            workspace,
            scan=_scan(
                scan_id="SCAN-LAZIO-MISMATCH",
                territories=["Regione Lazio"],
                source_selection=mismatched,
            ),
            next_scan_on=None,
            idempotency_key="scan-lazio-mismatch",
            **_contribution_args(),
        )

    selection = _source_selection(territories=["Regione Lazio"])
    _start_scan(
        radar,
        workspace,
        scan_id="SCAN-LAZIO",
        key="scan-lazio-start",
        territories=["Regione Lazio"],
        source_selection=selection,
        review_selection=False,
    )
    running = radar.load_validated_radar(workspace)["monitoring"]["scan_history"][0]

    assert running["coverage"]["status"] == "selection_unreviewed"
    with pytest.raises(ValueError, match="confirmed query-scoped source selection"):
        radar.render_scan_worklist(workspace, scan_id="SCAN-LAZIO")
    with pytest.raises(ValueError, match="confirmed query-scoped source selection"):
        radar.record_source_check(
            workspace,
            source_id="SOURCE-REGION",
            check_id="CHECK-LAZIO-EARLY",
            scan_id="SCAN-LAZIO",
            check_status="checked",
            checked_at="2026-08-07T11:00:00+00:00",
            window_start="2026-06-09",
            window_end="2026-08-07",
            next_check_on=None,
            result_count=0,
            error_code=None,
            cursor_after=None,
            idempotency_key="check-lazio-before-selection-review",
        )

    _review(
        radar,
        workspace,
        scope="scan_source_selection",
        target_id="SCAN-LAZIO",
        key="review-lazio-selection",
    )
    worklist = radar.render_scan_worklist(workspace, scan_id="SCAN-LAZIO")

    assert "Regione Lazio" in worklist.read_text(encoding="utf-8")


def test_rejected_unselected_source_does_not_block_lazio_scan(
    tmp_path: Path,
) -> None:
    radar, workspace = _initialized_radar(tmp_path)
    _record_baseline(radar, workspace)
    lazio_source = _source()
    lazio_source.update(
        {
            "source_id": "SOURCE-LAZIO",
            "publisher": "Regione Lazio",
            "official_url": "https://www.regione.lazio.it/bandi",
            "territories": ["Regione Lazio"],
        }
    )
    radar.record_source(
        workspace,
        source=lazio_source,
        idempotency_key="source-lazio",
        **_contribution_args(),
    )
    radar.review_item(
        workspace,
        scope="source",
        target_id="SOURCE-REGION",
        decision="rejected",
        reviewer_id="reviewer-001",
        reviewer_role="commercialista",
        confirmed_by_user=True,
        idempotency_key="reject-veneto-source",
    )
    _review(
        radar,
        workspace,
        scope="source",
        target_id="SOURCE-LAZIO",
        key="review-lazio-source",
    )
    selection = _source_selection(
        territories=["Regione Lazio"], priority_source_ids=["SOURCE-LAZIO"]
    )
    _start_scan(
        radar,
        workspace,
        scan_id="SCAN-LAZIO-COMPLETE",
        key="scan-lazio-complete-start",
        territories=["Regione Lazio"],
        source_selection=selection,
    )
    radar.record_source_check(
        workspace,
        source_id="SOURCE-LAZIO",
        check_id="CHECK-LAZIO",
        scan_id="SCAN-LAZIO-COMPLETE",
        check_status="checked",
        checked_at="2026-08-07T11:00:00+00:00",
        window_start="2026-06-09",
        window_end="2026-08-07",
        next_check_on=None,
        result_count=1,
        error_code=None,
        cursor_after=None,
        idempotency_key="check-lazio",
    )
    _review(
        radar,
        workspace,
        scope="source_check",
        target_id="SOURCE-LAZIO",
        key="review-check-lazio",
    )
    complete = radar.record_scan(
        workspace,
        scan=_scan(
            scan_id="SCAN-LAZIO-COMPLETE",
            territories=["Regione Lazio"],
            source_selection=selection,
            completed_at="2026-08-07T11:05:00+00:00",
            outcome="complete",
        ),
        next_scan_on=None,
        idempotency_key="scan-lazio-complete-finish",
    )

    assert complete["coverage"]["status"] == "priority_sources_verified"
    assert complete["unreviewed_priority_source_ids"] == []
    assert complete["priority_source_ids"] == ["SOURCE-LAZIO"]


def test_returned_scan_source_selection_can_be_revised_before_checks(
    tmp_path: Path,
) -> None:
    radar, workspace = _initialized_radar(tmp_path)
    _record_baseline(radar, workspace)
    _review(
        radar,
        workspace,
        scope="source",
        target_id="SOURCE-REGION",
        key="review-source-selection-revision",
    )
    original = _source_selection()
    _start_scan(
        radar,
        workspace,
        scan_id="SCAN-SELECTION-REVISION",
        key="scan-selection-revision-start",
        source_selection=original,
        review_selection=False,
    )
    radar.review_item(
        workspace,
        scope="scan_source_selection",
        target_id="SCAN-SELECTION-REVISION",
        decision="returned",
        reviewer_id="reviewer-001",
        reviewer_role="commercialista",
        confirmed_by_user=True,
        idempotency_key="return-scan-selection",
    )
    revised = {
        **original,
        "selection_rationale": "Razionale corretto dopo il ritorno professionale.",
    }

    result = radar.record_scan(
        workspace,
        scan=_scan(scan_id="SCAN-SELECTION-REVISION", source_selection=revised),
        next_scan_on=None,
        idempotency_key="revise-scan-selection",
        **_contribution_args(),
    )

    assert result["source_selection"]["review_status"] == "proposed"
    assert result["source_selection"]["selection_rationale"] == (
        "Razionale corretto dopo il ritorno professionale."
    )
    assert result["coverage"]["status"] == "selection_unreviewed"


def test_declared_query_scope_gap_blocks_complete_scan(tmp_path: Path) -> None:
    radar, workspace = _initialized_radar(tmp_path)
    _record_baseline(radar, workspace)
    _review(
        radar,
        workspace,
        scope="source",
        target_id="SOURCE-REGION",
        key="review-source-scope-gap",
    )
    selection = _source_selection(
        gaps={("territory", "Regione Veneto")},
    )
    _start_scan(
        radar,
        workspace,
        scan_id="SCAN-SCOPE-GAP",
        key="scan-scope-gap-start",
        source_selection=selection,
    )
    radar.record_source_check(
        workspace,
        source_id="SOURCE-REGION",
        check_id="CHECK-SCOPE-GAP",
        scan_id="SCAN-SCOPE-GAP",
        check_status="checked",
        checked_at="2026-08-07T11:00:00+00:00",
        window_start="2026-06-09",
        window_end="2026-08-07",
        next_check_on=None,
        result_count=0,
        error_code=None,
        cursor_after=None,
        idempotency_key="check-scope-gap",
    )
    _review(
        radar,
        workspace,
        scope="source_check",
        target_id="SOURCE-REGION",
        key="review-check-scope-gap",
    )
    terminal = _scan(
        scan_id="SCAN-SCOPE-GAP",
        source_selection=selection,
        completed_at="2026-08-07T11:05:00+00:00",
        outcome="complete",
    )

    with pytest.raises(
        ValueError, match="source selection, query scope, or priority sources"
    ):
        radar.record_scan(
            workspace,
            scan=terminal,
            next_scan_on=None,
            idempotency_key="scan-scope-gap-complete",
        )

    partial = radar.record_scan(
        workspace,
        scan={**terminal, "outcome": "partial"},
        next_scan_on=None,
        idempotency_key="scan-scope-gap-partial",
    )

    assert partial["coverage"]["status"] == "scope_gaps"
    assert partial["coverage"]["uncovered_scope_keys"] == ["territory:Regione Veneto"]


def test_semantic_web_cannot_run_before_priority_source_attempts(
    tmp_path: Path,
) -> None:
    radar, workspace = _initialized_radar(tmp_path)
    _record_baseline(radar, workspace)
    _review(
        radar,
        workspace,
        scope="source",
        target_id="SOURCE-REGION",
        key="review-source-order",
    )
    _start_scan(radar, workspace, scan_id="SCAN-ORDER", key="scan-order-start")

    with pytest.raises(ValueError, match="cannot precede priority-source attempts"):
        radar.record_scan(
            workspace,
            scan=_scan(
                scan_id="SCAN-ORDER",
                completed_at="2026-08-07T10:05:00+00:00",
                outcome="partial",
                semantic_web_check={
                    "status": "checked",
                    "checked_at": "2026-08-07T10:01:00+00:00",
                    "result_count": 1,
                    "error_code": None,
                },
            ),
            next_scan_on=None,
            idempotency_key="scan-order-finish",
        )


def test_source_check_must_cover_the_entire_requested_window(tmp_path: Path) -> None:
    radar, workspace = _initialized_radar(tmp_path)
    _record_baseline(radar, workspace)
    _review(
        radar,
        workspace,
        scope="source",
        target_id="SOURCE-REGION",
        key="review-source-window",
    )
    _start_scan(radar, workspace, scan_id="SCAN-WINDOW", key="scan-window-start")

    with pytest.raises(ValueError, match="does not cover the scan window"):
        radar.record_source_check(
            workspace,
            source_id="SOURCE-REGION",
            check_id="CHECK-WINDOW",
            scan_id="SCAN-WINDOW",
            check_status="checked",
            checked_at="2026-08-07T11:00:00+00:00",
            window_start="2026-07-01",
            window_end="2026-08-07",
            next_check_on="2026-08-08",
            result_count=1,
            error_code=None,
            cursor_after=None,
            idempotency_key="source-check-window",
        )


def test_running_scan_ignores_unselected_source_registry_changes(
    tmp_path: Path,
) -> None:
    radar, workspace = _initialized_radar(tmp_path)
    _record_baseline(radar, workspace)
    _review(
        radar,
        workspace,
        scope="source",
        target_id="SOURCE-REGION",
        key="review-source-drift",
    )
    _start_scan(radar, workspace, scan_id="SCAN-DRIFT", key="scan-drift-start")
    additional = _source()
    additional.update(
        {
            "source_id": "SOURCE-AGENCY",
            "publisher": "Agenzia regionale sintetica",
            "official_url": "https://example.invalid/official-source",
        }
    )
    radar.record_source(
        workspace,
        source=additional,
        idempotency_key="source-agency",
        **_contribution_args(),
    )

    result = radar.record_scan(
        workspace,
        scan=_scan(
            scan_id="SCAN-DRIFT",
            completed_at="2026-08-07T11:00:00+00:00",
            outcome="partial",
        ),
        next_scan_on=None,
        idempotency_key="scan-drift-finish",
    )

    assert result["outcome"] == "partial"
    assert result["priority_source_ids"] == ["SOURCE-REGION"]


def test_source_cursor_persists_when_later_scan_finds_no_new_publication(
    tmp_path: Path,
) -> None:
    radar, workspace = _initialized_radar(tmp_path)
    _record_baseline(radar, workspace)
    _review(
        radar,
        workspace,
        scope="source",
        target_id="SOURCE-REGION",
        key="review-source-cursor",
    )
    _record_reviewed_source_check(radar, workspace, key_suffix="cursor-1")
    radar.record_scan(
        workspace,
        scan=_scan(
            scan_id="SCAN-cursor-1",
            completed_at="2026-08-07T11:05:00+00:00",
            outcome="complete",
        ),
        next_scan_on="2026-08-08",
        idempotency_key="scan-cursor-1-complete",
    )
    _start_scan(
        radar,
        workspace,
        scan_id="SCAN-cursor-2",
        key="scan-cursor-2-start",
        started_at="2026-08-08T10:00:00+00:00",
    )

    current = radar.record_source_check(
        workspace,
        source_id="SOURCE-REGION",
        check_id="CHECK-cursor-2",
        scan_id="SCAN-cursor-2",
        check_status="checked",
        checked_at="2026-08-08T11:00:00+00:00",
        window_start="2026-06-09",
        window_end="2026-08-07",
        next_check_on="2026-08-09",
        result_count=0,
        error_code=None,
        cursor_after=None,
        idempotency_key="source-check-cursor-2",
    )

    assert current["cursor_before"] == current["cursor_after"]
    assert current["cursor_after"]["external_id"] == "BUR-2026-cursor-1"


@pytest.mark.parametrize(
    "status",
    [
        "announced",
        "approved",
        "published",
        "upcoming",
        "open",
        "closing_soon",
        "extended",
        "modified",
        "closed",
    ],
)
def test_lifecycle_contract_accepts_source_backed_discovery_states(
    tmp_path: Path, status: str
) -> None:
    radar, workspace = _initialized_radar(tmp_path)
    _record_baseline(radar, workspace)
    opportunity = _opportunity(
        history=[
            {
                "observation_id": "OBS-STATE",
                "status": status,
                "effective_date": "2026-08-07",
                "observed_at": "2026-08-07T10:00:00+00:00",
                "source_ids": ["SOURCE-REGION"],
                "rationale": "Synthetic source-backed lifecycle proposal.",
            }
        ]
    )

    recorded = radar.record_opportunity(
        workspace,
        opportunity=opportunity,
        idempotency_key=f"opportunity-{status}",
        **_contribution_args(),
    )

    assert recorded["current_lifecycle"] == status


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


@pytest.mark.parametrize(
    ("decision", "pending_count", "rejected_count"),
    [("returned", 1, 0), ("rejected", 0, 1)],
)
def test_nonaccepted_source_is_excluded_from_reviewed_plan_coverage(
    tmp_path: Path, decision: str, pending_count: int, rejected_count: int
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
    assert coverage["unreviewed_count"] == pending_count
    assert coverage["rejected_count"] == rejected_count


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
    radar.record_scan(
        workspace,
        scan=_scan(
            scan_id="SCAN-1",
            completed_at="2026-08-07T11:05:00+00:00",
            outcome="partial",
        ),
        next_scan_on="2026-08-08",
        idempotency_key="scan-1-partial",
    )
    _start_scan(
        radar,
        workspace,
        scan_id="SCAN-FAILED",
        key="scan-failed-start",
        started_at="2026-08-08T10:00:00+00:00",
    )

    changed = radar.record_source_check(
        workspace,
        source_id="SOURCE-REGION",
        check_id="CHECK-FAILED",
        scan_id="SCAN-FAILED",
        check_status="failed",
        checked_at="2026-08-08T11:00:00+00:00",
        window_start="2026-06-09",
        window_end="2026-08-07",
        next_check_on="2026-08-09",
        result_count=None,
        error_code="temporary_failure",
        cursor_after=None,
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
        **_contribution_args("SESSION-CLIENT-REVISION-002"),
    )
    current = radar.load_validated_radar(workspace)

    assert result["revision"] == 2
    assert result["revision_history"][0]["previous_sha256"]
    assert result["review_status"] == "proposed"
    assert current["matches"][0]["review_status"] == "proposed"


def test_scan_cannot_complete_before_it_starts(tmp_path: Path) -> None:
    radar, workspace = _initialized_radar(tmp_path)
    _record_baseline(radar, workspace)
    _review(
        radar,
        workspace,
        scope="source",
        target_id="SOURCE-REGION",
        key="review-source-invalid-scan",
    )

    _start_scan(
        radar,
        workspace,
        scan_id="SCAN-INVALID",
        key="scan-invalid-start",
        started_at="2026-08-07T11:00:00+00:00",
    )
    with pytest.raises(ValueError, match="completes before it starts"):
        radar.record_scan(
            workspace,
            scan=_scan(
                scan_id="SCAN-INVALID",
                started_at="2026-08-07T11:00:00+00:00",
                completed_at="2026-08-07T10:00:00+00:00",
                outcome="failed",
            ),
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
            "--model-session-ref",
            "SESSION-CLI-CLIENT-001",
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
            "--model-session-ref",
            "SESSION-CLI-CLIENT-001",
        ]
    )
    rendered = radar.main(["--workspace", str(workspace), "report"])

    assert initialized == 0
    assert evidence_recorded == 0
    assert recorded == 0
    assert rendered == 0
    assert (workspace / "opportunity_radar_review.md").is_file()


def test_radar_cli_executes_source_first_scan_with_coverage_evidence(
    tmp_path: Path,
) -> None:
    radar = _radar_module()
    workspace = tmp_path / "source-first-cli-radar"
    source_path = tmp_path / "source.json"
    running_path = tmp_path / "running-scan.json"
    terminal_path = tmp_path / "terminal-scan.json"
    cursor_path = tmp_path / "cursor.json"
    source = _source()
    source["profile_refs"] = []
    source_path.write_text(json.dumps(source), encoding="utf-8")
    running_path.write_text(json.dumps(_scan()), encoding="utf-8")
    terminal_path.write_text(
        json.dumps(
            _scan(
                completed_at="2026-08-07T11:10:00+00:00",
                outcome="complete",
                semantic_web_check={
                    "status": "checked",
                    "checked_at": "2026-08-07T11:05:00+00:00",
                    "result_count": 1,
                    "error_code": None,
                },
            )
        ),
        encoding="utf-8",
    )
    cursor_path.write_text(
        json.dumps(
            {
                "external_id": "BUR-2026-CLI",
                "publication_date": "2026-08-07",
                "official_url": "https://example.invalid/publication",
            }
        ),
        encoding="utf-8",
    )
    base = ["--workspace", str(workspace)]

    assert (
        radar.main(
            [
                *base,
                "initialize",
                "--radar-id",
                "RADAR-CLI-SOURCE-FIRST",
                "--workspace-id",
                "WORKSPACE-CLI-SOURCE-FIRST",
                "--reference-date",
                "2026-08-07",
                "--scope",
                "portfolio",
                "--authorized-by",
                "reviewer-001",
                "--retention-owner",
                "Studio Demo",
                "--confirmed-by-user",
            ]
        )
        == 0
    )
    assert (
        radar.main(
            [
                *base,
                "record-source",
                "--input",
                str(source_path),
                "--idempotency-key",
                "source-cli-first",
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
                "--model-session-ref",
                "SESSION-CLI-SOURCE-001",
            ]
        )
        == 0
    )
    for scope, key in (
        ("source", "review-source-cli-first"),
        ("source_check", "review-source-check-cli-first"),
    ):
        if scope == "source_check":
            assert (
                radar.main(
                    [
                        *base,
                        "record-source-check",
                        "--source-id",
                        "SOURCE-REGION",
                        "--check-id",
                        "CHECK-CLI-FIRST",
                        "--scan-id",
                        "SCAN-001",
                        "--check-status",
                        "checked",
                        "--checked-at",
                        "2026-08-07T11:00:00+00:00",
                        "--window-start",
                        "2026-06-09",
                        "--window-end",
                        "2026-08-07",
                        "--next-check-on",
                        "2026-08-08",
                        "--result-count",
                        "1",
                        "--cursor-input",
                        str(cursor_path),
                        "--idempotency-key",
                        "source-check-cli-first",
                    ]
                )
                == 0
            )
        assert (
            radar.main(
                [
                    *base,
                    "review",
                    "--scope",
                    scope,
                    "--target-id",
                    "SOURCE-REGION",
                    "--decision",
                    "accepted",
                    "--reviewer-id",
                    "reviewer-001",
                    "--reviewer-role",
                    "commercialista",
                    "--confirmed-by-user",
                    "--idempotency-key",
                    key,
                ]
            )
            == 0
        )
        if scope == "source":
            assert (
                radar.main(
                    [
                        *base,
                        "record-scan",
                        "--input",
                        str(running_path),
                        "--idempotency-key",
                        "scan-cli-first-start",
                        "--origin",
                        "model_suggested",
                        "--provider",
                        "openai",
                        "--model",
                        "gpt-test-pinned",
                        "--prompt-template-version",
                        "bandi-source-selection-v1",
                        "--recorded-by",
                        "codex-local",
                        "--model-session-ref",
                        "SESSION-CLI-SCAN-001",
                    ]
                )
                == 0
            )
            assert (
                radar.main(
                    [
                        *base,
                        "review",
                        "--scope",
                        "scan_source_selection",
                        "--target-id",
                        "SCAN-001",
                        "--decision",
                        "accepted",
                        "--reviewer-id",
                        "reviewer-001",
                        "--reviewer-role",
                        "commercialista",
                        "--confirmed-by-user",
                        "--idempotency-key",
                        "review-scan-source-selection-cli-first",
                    ]
                )
                == 0
            )
            assert radar.main([*base, "worklist", "--scan-id", "SCAN-001"]) == 0
    assert (
        radar.main(
            [
                *base,
                "record-scan",
                "--input",
                str(terminal_path),
                "--next-scan-on",
                "2026-08-08",
                "--idempotency-key",
                "scan-cli-first-finish",
            ]
        )
        == 0
    )
    assert radar.main([*base, "report"]) == 0

    payload = radar.load_validated_radar(workspace)
    report = (workspace / "opportunity_radar_review.md").read_text(encoding="utf-8")

    assert payload["monitoring"]["scan_history"][0]["coverage"]["status"] == (
        "priority_sources_verified"
    )
    assert "Territori richiesti: **Regione Veneto**" in report
    assert "Selezione fonti: **confirmed**" in report
    assert "Ricerca web complementare: **checked**" in report
