from __future__ import annotations

import hashlib
import importlib.util
import json
import subprocess
import sys
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import pytest

ROOT = Path(__file__).resolve().parents[2]
PLUGIN_ROOT = ROOT / "plugins" / "bilancio-xbrl-it"
SCRIPTS = PLUGIN_ROOT / "scripts"
RULE_PACK_PATH = PLUGIN_ROOT / "rulepacks" / "it" / "statutory-forms-2026.1.json"


def _load_module(name: str):
    if str(SCRIPTS) not in sys.path:
        sys.path.insert(0, str(SCRIPTS))
    path = SCRIPTS / f"{name}.py"
    spec = importlib.util.spec_from_file_location(f"bilancio_{name}", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


access_control = _load_module("access_control")
case_service = _load_module("case_service")


def _context(tenant_id: str = "tenant_1", roles: tuple[str, ...] = ("PREPARER",)):
    return access_control.RequestContext(
        tenant_id=tenant_id,
        actor_id="actor_1",
        roles=roles,
        originating_interface="pytest",
    )


def _worker_context(tenant_id: str = "tenant_1"):
    return access_control.RequestContext(
        tenant_id=tenant_id,
        actor_id="worker_1",
        roles=("SERVICE_WORKER",),
        originating_interface="background-worker",
    )


def _payload() -> dict[str, object]:
    return {
        "case_id": "case_2025",
        "entity": {
            "legal_name": "Rossi S.r.l.",
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
            "prior_period_start": "2024-01-01",
            "prior_period_end": "2024-12-31",
            "micro_exclusion_flags": [],
        },
        "period": {"start": "2025-01-01", "end": "2025-12-31"},
        "oic_rule_pack": "OIC_2024_2025.1",
        "filing_campaign_year": 2026,
        "taxonomy_checksum": "a" * 64,
    }


def _rule_pack() -> dict[str, object]:
    return json.loads(RULE_PACK_PATH.read_text(encoding="utf-8"))


def _regulatory_migration() -> dict[str, object]:
    return {
        "reason": "Adopt the reviewed replacement packs for this open case.",
        "statutory_rule_pack": "IT_CC_2026.1",
        "oic_rule_pack": "OIC_2024_2025.1",
        "taxonomy_id": "PCI_2018-11-04-R2",
        "taxonomy_checksum": "b" * 64,
        "filing_instruction_pack": "RI_2026.1",
        "filing_campaign_year": 2026,
        "early_adoption_flags": [],
    }


def _write_presentation_config(
    tmp_path: Path,
) -> tuple[Path, Path]:
    role = "https://example.invalid/role/primary"
    catalogue = {
        "schema_version": 2,
        "taxonomy_id": "PCI_2018-11-04",
        "taxonomy_package_sha256": "a" * 64,
        "concepts": [
            {
                "qname": "itcc:Root",
                "type": "xbrli:stringItemType",
                "period_type": "instant",
                "abstract": True,
                "is_item": True,
                "is_tuple": False,
                "label_it": "Radice",
            },
            *[
                {
                    "qname": f"itcc:{name}",
                    "type": "xbrli:monetaryItemType",
                    "period_type": "instant",
                    "abstract": False,
                    "is_item": True,
                    "is_tuple": False,
                    "label_it": name,
                }
                for name in ("A", "B", "Total")
            ],
        ],
        "relationships": {
            "presentation": [
                {
                    "form": "ABBREVIATED",
                    "role": role,
                    "from": source,
                    "to": target,
                }
                for source, target in (
                    ("itcc:Root", "itcc:Total"),
                    ("itcc:Total", "itcc:A"),
                    ("itcc:Total", "itcc:B"),
                )
            ],
            "calculation": [
                {
                    "form": "ABBREVIATED",
                    "role": role,
                    "from": "itcc:Total",
                    "to": target,
                    "weight": "1",
                }
                for target in ("itcc:A", "itcc:B")
            ],
        },
    }
    policy = {
        "id": "TEST_PRESENTATION_1",
        "taxonomy_id": "PCI_2018-11-04",
        "effective_from": "2018-11-04",
        "effective_to": "2026-12-31",
        "statement_sections": {
            "ASSETS": {
                "expected_role_kind": "BALANCE_SHEET",
                "root_concept": "itcc:Total",
                "canonical_multiplier": "1",
            }
        },
        "schedule_trigger_roots": {"FIXED_ASSETS": ["itcc:A"]},
        "forms": {"ABBREVIATED": {"roles": [{"kind": "BALANCE_SHEET", "role": role}]}},
    }
    catalogue_path = tmp_path / "catalogue.json"
    policy_path = tmp_path / "presentation-policy.json"
    catalogue_path.write_text(json.dumps(catalogue), encoding="utf-8")
    policy_path.write_text(json.dumps(policy), encoding="utf-8")
    return catalogue_path, policy_path


def _prepare_exported_artifact(
    storage: Path, content: bytes = b"approved workpaper"
) -> None:
    case_dir = storage / "tenant_1" / "case_2025"
    case = case_service.load_case(case_dir)
    case["state"] = "EXPORTED"
    case["approval"] = {"revision_id": case["revision_id"]}
    output = case_dir / "exports" / case["revision_id"]
    output.mkdir(parents=True)
    artifact = output / "workpaper.json"
    artifact.write_bytes(content)
    case["artifacts"] = [
        {
            "file_name": artifact.name,
            "sha256": hashlib.sha256(content).hexdigest(),
            "size_bytes": len(content),
        }
    ]
    case_service.save_case(case_dir, case)


def test_case_service_create_is_tenant_scoped_and_idempotent(tmp_path: Path) -> None:
    service = case_service.CaseService(tmp_path / "store")
    context = _context()

    first = service.create(context, _payload(), _rule_pack(), "create_1")
    repeated = service.create(context, _payload(), _rule_pack(), "create_1")

    assert repeated == first
    case_file = tmp_path / "store" / "tenant_1" / "case_2025" / "case.json"
    persisted = json.loads(case_file.read_text(encoding="utf-8"))
    assert persisted["tenant_id"] == "tenant_1"
    assert persisted["audit_events"][-1]["originating_interface"] == "pytest"
    assert persisted["audit_events"][-1]["tenant_id"] == "tenant_1"
    assert len(persisted["audit_events"][-1]["after_hash"]) == 64
    checksum = (
        case_file.with_name("case.json.sha256").read_text(encoding="ascii").strip()
    )
    assert len(checksum) == 64
    idempotency_checksum = (
        case_file.parent / ".idempotency" / "create_1.sha256"
    ).read_text(encoding="ascii")
    assert len(idempotency_checksum.strip()) == 64


def test_case_service_rejects_tampered_idempotency_record(tmp_path: Path) -> None:
    service = case_service.CaseService(tmp_path / "store")
    context = _context()
    service.create(context, _payload(), _rule_pack(), "create_1")
    record = (
        tmp_path / "store" / "tenant_1" / "case_2025" / ".idempotency" / "create_1.json"
    )
    record.write_text("{}\n", encoding="utf-8")

    with pytest.raises(ValueError, match="Idempotency record integrity"):
        service.create(context, _payload(), _rule_pack(), "create_1")


def test_case_service_rejects_missing_idempotency_checksum(tmp_path: Path) -> None:
    service = case_service.CaseService(tmp_path / "store")
    context = _context()
    service.create(context, _payload(), _rule_pack(), "create_1")
    checksum = (
        tmp_path
        / "store"
        / "tenant_1"
        / "case_2025"
        / ".idempotency"
        / "create_1.sha256"
    )
    checksum.unlink()

    with pytest.raises(ValueError, match="missing integrity metadata"):
        service.create(context, _payload(), _rule_pack(), "create_1")


def test_case_service_same_idempotency_key_different_request_is_rejected(
    tmp_path: Path,
) -> None:
    service = case_service.CaseService(tmp_path / "store")
    context = _context()
    service.create(context, _payload(), _rule_pack(), "create_1")
    changed = _payload()
    changed["requested_form"] = "ORDINARY"

    with pytest.raises(ValueError, match="another request"):
        service.create(context, changed, _rule_pack(), "create_1")


def test_case_service_mutation_replay_does_not_advance_revision_twice(
    tmp_path: Path,
) -> None:
    service = case_service.CaseService(tmp_path / "store")
    context = _context()
    service.create(context, _payload(), _rule_pack(), "create_1")
    request = {
        "metrics": [
            {"year": 2025, "assets": "1", "revenue": "1", "employees": "1"},
            {"year": 2024, "assets": "1", "revenue": "1", "employees": "1"},
        ],
        "rule_pack": _rule_pack(),
    }

    first = service.mutate(
        context, "case_2025", "determine_forms", request, "rev_1", "forms_1"
    )
    replay = service.mutate(
        context, "case_2025", "determine_forms", request, "rev_1", "forms_1"
    )

    assert replay == first
    assert first["revision_id"] == "rev_2"
    case_file = tmp_path / "store" / "tenant_1" / "case_2025" / "case.json"
    persisted = json.loads(case_file.read_text(encoding="utf-8"))
    mutation_events = [
        event for event in persisted["audit_events"] if event["revision_id"] == "rev_2"
    ]
    assert mutation_events
    assert all(event["originating_interface"] == "pytest" for event in mutation_events)
    assert any(event["before_hash"] for event in mutation_events)


def test_case_service_regulatory_migration_requires_admin_configuration_role(
    tmp_path: Path,
) -> None:
    service = case_service.CaseService(tmp_path / "store")
    preparer = _context()
    administrator = _context(roles=("STUDIO_ADMIN",))
    service.create(preparer, _payload(), _rule_pack(), "create_1")

    with pytest.raises(PermissionError, match="CONFIGURE"):
        service.mutate(
            preparer,
            "case_2025",
            "migrate_regulatory_versions",
            _regulatory_migration(),
            "rev_1",
            "migration_denied_1",
        )

    result = service.mutate(
        administrator,
        "case_2025",
        "migrate_regulatory_versions",
        _regulatory_migration(),
        "rev_1",
        "migration_1",
    )

    assert result["revision_id"] == "rev_2"
    assert result["latest_regulatory_migration"]["revalidation_status"] == "REQUIRED"
    persisted = case_service.load_case(tmp_path / "store" / "tenant_1" / "case_2025")
    assert persisted["audit_events"][-1]["originating_interface"] == "pytest"


def test_case_service_records_reviewed_statutory_presentation(
    tmp_path: Path,
) -> None:
    catalogue, presentation_policy = _write_presentation_config(tmp_path)
    storage = tmp_path / "store"
    service = case_service.CaseService(
        storage,
        taxonomy_catalogue_path=catalogue,
        statutory_presentation_rule_pack_path=presentation_policy,
    )
    service.create(_context(), _payload(), _rule_pack(), "create_1")
    case_dir = storage / "tenant_1" / "case_2025"
    case = case_service.load_case(case_dir)
    case["selected_form"] = "ABBREVIATED"
    case["canonical_facts"] = [
        {
            "fact_id": "fact_a",
            "xbrl_concept": "itcc:A",
            "statement_section": "ASSETS",
            "xbrl_sign_multiplier": "1",
            "current_value": "100",
            "prior_value": "90",
            "status": "OBSERVED",
            "source_refs": ["source:a"],
        }
    ]
    case["statements"] = {
        "facts": list(case["canonical_facts"]),
        "section_totals": {"ASSETS": {"current": "100", "prior": "90"}},
    }
    case_service.save_case(case_dir, case)

    indexed = service.mutate(
        _context(),
        "case_2025",
        "taxonomy_mapping_index",
        {},
        "rev_1",
        "taxonomy_index_1",
    )
    service.mutate(
        _context(),
        "case_2025",
        "record_statutory_presentation",
        {
            "decisions": [
                {
                    "xbrl_concept": "itcc:B",
                    "current_status": "ZERO_CONFIRMED",
                    "prior_status": "ZERO_CONFIRMED",
                    "reason": "Confermato in sede di chiusura annuale.",
                }
            ]
        },
        indexed["revision_id"],
        "presentation_1",
    )

    persisted = case_service.load_case(case_dir)
    assert persisted["statutory_presentation"]["status"] == "COMPLETE"
    assert persisted["statutory_presentation"]["recorded_by"] == "actor_1"
    assert persisted["audit_events"][-1]["action"] == (
        "statutory_presentation_recorded"
    )


def test_case_service_preparer_cannot_approve(tmp_path: Path) -> None:
    service = case_service.CaseService(tmp_path / "store")
    context = _context()
    service.create(context, _payload(), _rule_pack(), "create_1")

    with pytest.raises(PermissionError, match="APPROVE"):
        service.mutate(
            context,
            "case_2025",
            "approve",
            {"declaration": {}},
            "rev_1",
            "approve_1",
        )


def test_authorize_rejects_cross_tenant_even_for_reviewer() -> None:
    case = {"case_id": "case_1", "tenant_id": "tenant_1"}

    with pytest.raises(PermissionError, match="Cross-tenant"):
        access_control.authorize(_context("tenant_2", ("REVIEWER",)), "READ", case)


def test_platform_operator_requires_time_limited_case_grant() -> None:
    case = {"case_id": "case_1", "tenant_id": "tenant_1"}
    without_grant = _context("tenant_1", ("PLATFORM_OPERATOR",))

    with pytest.raises(PermissionError, match="support access"):
        access_control.authorize(without_grant, "READ", case)

    with_grant = access_control.RequestContext(
        tenant_id="tenant_1",
        actor_id="operator_1",
        roles=("PLATFORM_OPERATOR",),
        originating_interface="support-console",
        support_grant={
            "tenant_id": "tenant_1",
            "case_id": "case_1",
            "reason": "Customer-authorized incident",
            "expires_at": "2099-01-01T00:00:00+00:00",
        },
    )

    access_control.authorize(with_grant, "READ", case)


def test_case_service_rejects_path_traversal_identifier(tmp_path: Path) -> None:
    service = case_service.CaseService(tmp_path / "store")
    payload = _payload()
    payload["case_id"] = "../escape"

    with pytest.raises(ValueError, match="safe stable IDs"):
        service.create(_context(), payload, _rule_pack(), "create_1")


def test_case_service_rejects_source_outside_configured_input_root(
    tmp_path: Path,
) -> None:
    input_root = tmp_path / "inputs"
    input_root.mkdir()
    service = case_service.CaseService(tmp_path / "store", input_root=input_root)
    service.create(_context(), _payload(), _rule_pack(), "create_1")
    outside = tmp_path / "outside.csv"
    outside.write_text("not authorized", encoding="utf-8")

    with pytest.raises(ValueError, match="outside the configured input root"):
        service.mutate(
            _context(),
            "case_2025",
            "ingest",
            {"source_path": str(outside)},
            "rev_1",
            "ingest_1",
        )


def test_case_service_ingests_regular_source_inside_configured_input_root(
    tmp_path: Path,
) -> None:
    input_root = tmp_path / "inputs"
    input_root.mkdir()
    source = input_root / "trial-balance.csv"
    source.write_text(
        "account_code,account_description,opening_signed,period_debit,period_credit,closing_signed,prior_closing_signed\n"
        "1000,Cassa,90,10,0,100,90\n"
        "2000,Debiti,-90,0,10,-100,-90\n",
        encoding="utf-8",
    )
    service = case_service.CaseService(tmp_path / "store", input_root=input_root)
    service.create(_context(), _payload(), _rule_pack(), "create_1")

    result = service.mutate(
        _context(),
        "case_2025",
        "ingest",
        {"source_path": str(source)},
        "rev_1",
        "ingest_1",
    )

    assert result["state"] == "INPUT_REVIEW"
    assert result["revision_id"] == "rev_2"


def test_case_service_requires_configured_malware_scanner_when_enabled(
    tmp_path: Path,
) -> None:
    input_root = tmp_path / "inputs"
    input_root.mkdir()
    source = input_root / "trial-balance.csv"
    source.write_text(
        "account_code,account_description,opening_signed,period_debit,period_credit,closing_signed,prior_closing_signed\n"
        "1000,Cassa,90,10,0,100,90\n"
        "2000,Debiti,-90,0,10,-100,-90\n",
        encoding="utf-8",
    )
    service = case_service.CaseService(
        tmp_path / "store",
        input_root=input_root,
        require_malware_scan=True,
    )
    service.create(_context(), _payload(), _rule_pack(), "create_1")

    with pytest.raises(ValueError, match="malware scanner is required"):
        service.mutate(
            _context(),
            "case_2025",
            "ingest",
            {"source_path": str(source)},
            "rev_1",
            "ingest_1",
        )


def test_case_service_records_checksum_bound_clean_scan_before_ingestion(
    tmp_path: Path,
) -> None:
    input_root = tmp_path / "inputs"
    input_root.mkdir()
    source = input_root / "trial-balance.csv"
    source.write_text(
        "account_code,account_description,opening_signed,period_debit,period_credit,closing_signed,prior_closing_signed\n"
        "1000,Cassa,90,10,0,100,90\n"
        "2000,Debiti,-90,0,10,-100,-90\n",
        encoding="utf-8",
    )

    def clean_scanner(_path: Path) -> dict[str, str]:
        return {
            "status": "CLEAN",
            "engine": "test-scanner",
            "signature_version": "2026-08-05",
        }

    service = case_service.CaseService(
        tmp_path / "store",
        input_root=input_root,
        malware_scanner=clean_scanner,
        require_malware_scan=True,
    )
    service.create(_context(), _payload(), _rule_pack(), "create_1")

    service.mutate(
        _context(),
        "case_2025",
        "ingest",
        {"source_path": str(source)},
        "rev_1",
        "ingest_1",
    )

    persisted = json.loads(
        (tmp_path / "store/tenant_1/case_2025/case.json").read_text(encoding="utf-8")
    )
    document = persisted["source_documents"][0]
    receipt = persisted["file_security_scans"][0]
    assert document["security_scan_id"] == receipt["scan_id"]
    assert receipt["document_id"] == document["document_id"]
    assert receipt["sha256"] == document["sha256"]
    assert receipt["engine"] == "test-scanner"
    assert any(
        event["action"] == "document_malware_scanned"
        for event in persisted["audit_events"]
    )


def test_case_service_rejects_non_clean_scanner_verdict_without_mutation(
    tmp_path: Path,
) -> None:
    input_root = tmp_path / "inputs"
    input_root.mkdir()
    source = input_root / "trial-balance.csv"
    source.write_text("not parsed after rejection", encoding="utf-8")

    def infected_scanner(_path: Path) -> dict[str, str]:
        return {
            "status": "INFECTED",
            "engine": "test-scanner",
            "signature_version": "2026-08-05",
        }

    service = case_service.CaseService(
        tmp_path / "store",
        input_root=input_root,
        malware_scanner=infected_scanner,
        require_malware_scan=True,
    )
    service.create(_context(), _payload(), _rule_pack(), "create_1")

    with pytest.raises(ValueError, match="clean verdict"):
        service.mutate(
            _context(),
            "case_2025",
            "ingest",
            {"source_path": str(source)},
            "rev_1",
            "ingest_1",
        )

    persisted = json.loads(
        (tmp_path / "store/tenant_1/case_2025/case.json").read_text(encoding="utf-8")
    )
    assert persisted["revision_id"] == "rev_1"
    assert persisted["source_documents"] == []
    assert persisted["file_security_scans"] == []


def test_case_service_rejects_symlinked_case_storage(tmp_path: Path) -> None:
    storage = tmp_path / "store"
    tenant = storage / "tenant_1"
    other = storage / "tenant_2" / "case_2025"
    tenant.mkdir(parents=True)
    other.mkdir(parents=True)
    (tenant / "case_2025").symlink_to(other, target_is_directory=True)
    service = case_service.CaseService(storage)

    with pytest.raises(ValueError, match="must not be symbolic links"):
        service.create(_context(), _payload(), _rule_pack(), "create_1")


def test_case_service_detects_tampered_case_record(tmp_path: Path) -> None:
    service = case_service.CaseService(tmp_path / "store")
    service.create(_context(), _payload(), _rule_pack(), "create_1")
    case_file = tmp_path / "store/tenant_1/case_2025/case.json"
    case_file.write_bytes(case_file.read_bytes() + b" ")

    with pytest.raises(ValueError, match="integrity verification failed"):
        service.get(_context(), "case_2025")


def test_case_service_rejects_missing_case_checksum(tmp_path: Path) -> None:
    service = case_service.CaseService(tmp_path / "store")
    service.create(_context(), _payload(), _rule_pack(), "create_1")
    checksum = tmp_path / "store/tenant_1/case_2025/case.json.sha256"
    checksum.unlink()

    with pytest.raises(ValueError, match="checksum metadata is missing"):
        service.get(_context(), "case_2025")


def test_case_service_background_job_is_idempotent_and_revision_bound(
    tmp_path: Path,
) -> None:
    service = case_service.CaseService(tmp_path / "store")
    service.create(_context(), _payload(), _rule_pack(), "create_1")

    queued = service.enqueue_job(
        _context(),
        "case_2025",
        "validate_1",
        "validate",
        {},
        "rev_1",
    )
    repeated_enqueue = service.enqueue_job(
        _context(),
        "case_2025",
        "validate_1",
        "validate",
        {},
        "rev_1",
    )
    completed = service.run_job(_worker_context(), "case_2025", "validate_1")
    replayed = service.run_job(_worker_context(), "case_2025", "validate_1")

    assert repeated_enqueue == queued
    assert completed["status"] == "SUCCEEDED"
    assert completed["attempts"] == 1
    assert completed["result"]["revision_id"] == "rev_2"
    assert replayed == completed
    case = json.loads(
        (tmp_path / "store/tenant_1/case_2025/case.json").read_text(encoding="utf-8")
    )
    validation_events = [
        event for event in case["audit_events"] if event["action"] == "validation_run"
    ]
    assert len(validation_events) == 1


def test_case_service_background_job_cannot_apply_to_newer_revision(
    tmp_path: Path,
) -> None:
    service = case_service.CaseService(tmp_path / "store")
    service.create(_context(), _payload(), _rule_pack(), "create_1")
    service.enqueue_job(
        _context(),
        "case_2025",
        "validate_stale",
        "validate",
        {},
        "rev_1",
    )
    service.mutate(
        _context(),
        "case_2025",
        "determine_forms",
        {
            "metrics": [
                {"year": 2025, "assets": "1", "revenue": "1", "employees": "1"},
                {"year": 2024, "assets": "1", "revenue": "1", "employees": "1"},
            ],
            "rule_pack": _rule_pack(),
        },
        "rev_1",
        "forms_1",
    )

    result = service.run_job(_worker_context(), "case_2025", "validate_stale")

    assert result["status"] == "STALE"
    assert result["last_error"]["code"] == "STALE_REVISION"
    case = json.loads(
        (tmp_path / "store/tenant_1/case_2025/case.json").read_text(encoding="utf-8")
    )
    assert case["revision_id"] == "rev_2"
    assert not any(
        event["action"] == "validation_run" for event in case["audit_events"]
    )


def test_case_service_background_job_failure_is_retry_safe(
    tmp_path: Path,
) -> None:
    service = case_service.CaseService(tmp_path / "store")
    service.create(_context(), _payload(), _rule_pack(), "create_1")
    service.enqueue_job(
        _context(),
        "case_2025",
        "ingest_failure",
        "ingest",
        {"source_path": str(tmp_path / "missing.csv")},
        "rev_1",
        max_attempts=2,
    )

    first = service.run_job(_worker_context(), "case_2025", "ingest_failure")
    second = service.run_job(_worker_context(), "case_2025", "ingest_failure")
    exhausted = service.run_job(_worker_context(), "case_2025", "ingest_failure")

    assert first["status"] == "FAILED"
    assert first["attempts"] == 1
    assert second["status"] == "FAILED"
    assert second["attempts"] == 2
    assert exhausted == second
    case = json.loads(
        (tmp_path / "store/tenant_1/case_2025/case.json").read_text(encoding="utf-8")
    )
    assert case["revision_id"] == "rev_1"


def test_case_service_background_job_detects_record_tampering(tmp_path: Path) -> None:
    service = case_service.CaseService(tmp_path / "store")
    service.create(_context(), _payload(), _rule_pack(), "create_1")
    service.enqueue_job(_context(), "case_2025", "validate_1", "validate", {}, "rev_1")
    job_path = tmp_path / "store/tenant_1/case_2025/.jobs/validate_1.json"
    job_path.write_bytes(job_path.read_bytes() + b" ")

    with pytest.raises(ValueError, match="integrity verification failed"):
        service.get_job(_context(), "case_2025", "validate_1")


def test_case_service_background_job_rejects_changed_request_and_unsafe_scope(
    tmp_path: Path,
) -> None:
    service = case_service.CaseService(tmp_path / "store")
    service.create(_context(), _payload(), _rule_pack(), "create_1")
    service.enqueue_job(_context(), "case_2025", "validate_1", "validate", {}, "rev_1")

    with pytest.raises(ValueError, match="another request"):
        service.enqueue_job(
            _context(),
            "case_2025",
            "validate_1",
            "preview",
            {},
            "rev_1",
        )
    with pytest.raises(ValueError, match="not queueable"):
        service.enqueue_job(
            _context(),
            "case_2025",
            "forms_1",
            "determine_forms",
            {},
            "rev_1",
        )
    with pytest.raises(ValueError, match="safe stable ID"):
        service.enqueue_job(
            _context(), "case_2025", "../escape", "validate", {}, "rev_1"
        )


def test_background_worker_entrypoint_executes_queued_job(tmp_path: Path) -> None:
    storage = tmp_path / "store"
    service = case_service.CaseService(storage)
    service.create(_context(), _payload(), _rule_pack(), "create_1")
    service.enqueue_job(_context(), "case_2025", "validate_1", "validate", {}, "rev_1")

    completed = subprocess.run(
        [
            sys.executable,
            str(SCRIPTS / "run_background_job.py"),
            "--storage-root",
            str(storage),
            "--tenant-id",
            "tenant_1",
            "--case-id",
            "case_2025",
            "--job-id",
            "validate_1",
        ],
        cwd=SCRIPTS,
        capture_output=True,
        check=False,
        text=True,
    )

    assert completed.returncode == 0, completed.stderr
    result = json.loads(completed.stdout)
    assert result["status"] == "SUCCEEDED"
    assert result["result"]["revision_id"] == "rev_2"


def test_case_service_returns_authorized_structured_review_view(
    tmp_path: Path,
) -> None:
    service = case_service.CaseService(tmp_path / "store")
    service.create(_context(), _payload(), _rule_pack(), "create_1")

    dashboard = service.review_view(_context(), "case_2025", "CASE_DASHBOARD", limit=50)

    assert dashboard["case_id"] == "case_2025"
    assert dashboard["next_action"] == "INGEST_TRIAL_BALANCE"
    assert dashboard["validation"]["status"] == "NOT_RUN"


def test_case_service_issues_and_redeems_checksum_bound_artifact_grant(
    tmp_path: Path,
) -> None:
    storage = tmp_path / "store"
    service = case_service.CaseService(
        storage,
        artifact_signing_secret=b"s" * 32,
        artifact_download_base_url="https://vera.example/v1/xbrl-artifacts/download",
    )
    reviewer = _context(roles=("REVIEWER",))
    service.create(reviewer, _payload(), _rule_pack(), "create_1")
    _prepare_exported_artifact(storage)

    grant = service.issue_artifact_download(
        reviewer,
        "case_2025",
        "workpaper.json",
        "download_1",
        ttl_seconds=60,
    )
    repeated = service.issue_artifact_download(
        reviewer,
        "case_2025",
        "workpaper.json",
        "download_1",
        ttl_seconds=60,
    )
    token = parse_qs(urlparse(grant["download_url"]).query)["token"][0]
    artifact = service.redeem_artifact_download(token)

    assert repeated == grant
    assert artifact["content"] == b"approved workpaper"
    assert artifact["file_name"] == "workpaper.json"
    assert "/Users/" not in grant["download_url"]
    case = case_service.load_case(storage / "tenant_1" / "case_2025")
    access_actions = [
        event["action"]
        for event in case["audit_events"]
        if event["action"].startswith("artifact_download")
    ]
    assert access_actions == [
        "artifact_download_grant_issued",
        "artifact_downloaded",
    ]


def test_case_service_artifact_grant_enforces_role_and_manifest_checksum(
    tmp_path: Path,
) -> None:
    storage = tmp_path / "store"
    service = case_service.CaseService(
        storage,
        artifact_signing_secret=b"s" * 32,
        artifact_download_base_url="/v1/xbrl-artifacts/download",
    )
    reviewer = _context(roles=("REVIEWER",))
    service.create(reviewer, _payload(), _rule_pack(), "create_1")
    _prepare_exported_artifact(storage)

    with pytest.raises(PermissionError, match="DOWNLOAD_ARTIFACT"):
        service.issue_artifact_download(
            _context(roles=("PREPARER",)),
            "case_2025",
            "workpaper.json",
            "download_denied",
        )
    grant = service.issue_artifact_download(
        reviewer, "case_2025", "workpaper.json", "download_1"
    )
    token = parse_qs(urlparse(grant["download_url"]).query)["token"][0]
    artifact_path = storage / "tenant_1/case_2025/exports/rev_1/workpaper.json"
    artifact_path.write_bytes(b"tampered")

    with pytest.raises(ValueError, match="approved manifest"):
        service.redeem_artifact_download(token)


def test_case_service_archive_requires_host_policy_and_admin_role(
    tmp_path: Path,
) -> None:
    without_policy = case_service.CaseService(tmp_path / "store_without_policy")
    admin = _context(roles=("STUDIO_ADMIN",))
    without_policy.create(admin, _payload(), _rule_pack(), "create_1")

    with pytest.raises(ValueError, match="host retention policy"):
        without_policy.mutate(
            admin,
            "case_2025",
            "archive",
            {"reason": "Case closed"},
            "rev_1",
            "archive_1",
        )

    service = case_service.CaseService(tmp_path / "store", retention_days=30)
    service.create(admin, _payload(), _rule_pack(), "create_1")
    with pytest.raises(PermissionError, match="ARCHIVE"):
        service.mutate(
            _context(roles=("PREPARER",)),
            "case_2025",
            "archive",
            {"reason": "Case closed"},
            "rev_1",
            "archive_denied",
        )

    archived = service.mutate(
        admin,
        "case_2025",
        "archive",
        {"reason": "Case closed"},
        "rev_1",
        "archive_1",
    )

    assert archived["state"] == "ARCHIVED"
    case = case_service.load_case(tmp_path / "store/tenant_1/case_2025")
    assert case["revision_id"] == "rev_1"
    assert case["archive"]["retention_days"] == 30
    assert case["archive"]["reason"] == "Case closed"
    assert case["audit_events"][-1]["action"] == "case_archived"


def test_case_service_deletes_only_after_retention_and_replays_tombstone(
    tmp_path: Path,
) -> None:
    storage = tmp_path / "store"
    admin = _context(roles=("STUDIO_ADMIN",))
    service = case_service.CaseService(storage, retention_days=1)
    service.create(admin, _payload(), _rule_pack(), "create_1")
    service.mutate(
        admin,
        "case_2025",
        "archive",
        {"reason": "Engagement completed"},
        "rev_1",
        "archive_1",
    )

    with pytest.raises(ValueError, match="retention period has not elapsed"):
        service.delete_archived_case(
            admin,
            "case_2025",
            "rev_1",
            "delete_1",
            reason="Retention elapsed",
        )

    case_dir = storage / "tenant_1/case_2025"
    case = case_service.load_case(case_dir)
    case["archive"]["retain_until"] = "2000-01-01T00:00:00+00:00"
    case_service.save_case(case_dir, case)

    deleted = service.delete_archived_case(
        admin,
        "case_2025",
        "rev_1",
        "delete_1",
        reason="Retention elapsed",
    )
    replayed = service.delete_archived_case(
        admin,
        "case_2025",
        "rev_1",
        "delete_1",
        reason="Retention elapsed",
    )

    assert replayed == deleted
    assert deleted["status"] == "DELETED"
    assert not case_dir.exists()
    receipt = storage / "tenant_1/.deletions/case_2025/delete_1.json"
    checksum = receipt.with_suffix(".sha256")
    assert json.loads(receipt.read_text(encoding="utf-8"))["status"] == "DELETED"
    assert (
        hashlib.sha256(receipt.read_bytes()).hexdigest()
        == checksum.read_text(encoding="ascii").strip()
    )


def test_archived_export_artifact_remains_downloadable_during_retention(
    tmp_path: Path,
) -> None:
    storage = tmp_path / "store"
    service = case_service.CaseService(
        storage,
        retention_days=30,
        artifact_signing_secret=b"s" * 32,
        artifact_download_base_url="/v1/xbrl-artifacts/download",
    )
    admin = _context(roles=("STUDIO_ADMIN",))
    reviewer = _context(roles=("REVIEWER",))
    service.create(admin, _payload(), _rule_pack(), "create_1")
    _prepare_exported_artifact(storage)
    service.mutate(
        admin,
        "case_2025",
        "archive",
        {"reason": "Export delivered"},
        "rev_1",
        "archive_1",
    )

    grant = service.issue_artifact_download(
        reviewer, "case_2025", "workpaper.json", "download_1"
    )
    token = parse_qs(urlparse(grant["download_url"]).query)["token"][0]

    assert service.redeem_artifact_download(token)["content"] == b"approved workpaper"


def test_taxonomy_catalogue_build_job_uses_only_configured_registry_and_package(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    storage = tmp_path / "store"
    package = tmp_path / "official-taxonomy.zip"
    package.write_bytes(b"controlled taxonomy package")
    package_sha256 = hashlib.sha256(package.read_bytes()).hexdigest()
    registry = tmp_path / "taxonomy-registry.json"
    registry.write_text(
        json.dumps(
            {
                "taxonomy_id": "PCI_2018-11-04",
                "official_source": "https://example.invalid/official.zip",
                "taxonomy_package_sha256": package_sha256,
                "entry_points": {
                    "ORDINARY": "taxonomy/ordinary.xsd",
                    "ABBREVIATED": "taxonomy/abbreviated.xsd",
                    "MICRO": "taxonomy/micro.xsd",
                },
            }
        ),
        encoding="utf-8",
    )
    service = case_service.CaseService(
        storage,
        taxonomy_package_path=package,
        taxonomy_registry_path=registry,
    )
    payload = _payload()
    payload["taxonomy_checksum"] = package_sha256
    service.create(_context(), payload, _rule_pack(), "create_1")

    def fake_build_catalogue(
        source: Path,
        entry_points: dict[str, str],
        taxonomy_id: str,
        expected_sha256: str,
        official_source: str,
    ) -> dict[str, object]:
        assert source == package.resolve()
        assert set(entry_points) == {"ORDINARY", "ABBREVIATED", "MICRO"}
        assert taxonomy_id == "PCI_2018-11-04"
        assert expected_sha256 == package_sha256
        assert official_source == "https://example.invalid/official.zip"
        return {
            "schema_version": 2,
            "taxonomy_id": taxonomy_id,
            "taxonomy_package_sha256": expected_sha256,
            "official_source": official_source,
            "entry_points": entry_points,
            "namespaces": {},
            "concepts": [
                {
                    "qname": "itcc-ci:TotaleAttivo",
                    "is_item": True,
                    "is_tuple": False,
                }
            ],
            "relationships": {},
        }

    monkeypatch.setattr(case_service, "build_catalogue", fake_build_catalogue)
    queued = service.enqueue_job(
        _context(),
        "case_2025",
        "taxonomy_1",
        "taxonomy_catalogue_build",
        {},
        "rev_1",
    )
    completed = service.run_job(_worker_context(), "case_2025", "taxonomy_1")

    assert queued["status"] == "PENDING"
    assert completed["status"] == "SUCCEEDED"
    assert completed["result"]["revision_id"] == "rev_2"
    case = case_service.load_case(storage / "tenant_1/case_2025")
    receipt = case["taxonomy_catalogue_build"]
    catalogue = storage / "tenant_1/case_2025/taxonomy/catalogue-rev_1.json"
    assert receipt["concept_count"] == 1
    assert receipt["taxonomy_package_sha256"] == package_sha256
    assert hashlib.sha256(catalogue.read_bytes()).hexdigest() == receipt["sha256"]
    assert case["audit_events"][-1]["action"] == "taxonomy_catalogue_built"


def test_taxonomy_catalogue_job_rejects_request_selected_paths(tmp_path: Path) -> None:
    service = case_service.CaseService(tmp_path / "store")
    service.create(_context(), _payload(), _rule_pack(), "create_1")

    with pytest.raises(ValueError, match="does not accept request-selected"):
        service.enqueue_job(
            _context(),
            "case_2025",
            "taxonomy_1",
            "taxonomy_catalogue_build",
            {"package_path": "/tmp/untrusted.zip"},
            "rev_1",
        )


def _workflow_guidance_response() -> dict[str, object]:
    return {
        "output": {
            "summary_it": "Occorre acquisire il bilancio di verifica.",
            "recommended_next_action": "INGEST_TRIAL_BALANCE",
            "why_it_matters": "La fonte contabile non è ancora disponibile.",
            "attention_items": [],
            "confidence_band": "HIGH",
        },
        "model_metadata": {
            "provider": "test-provider",
            "model": "test-model",
            "prompt_template_version": "bilancio-v1",
        },
    }


def test_queued_intelligence_invokes_host_outside_mutation_and_records_suggestion(
    tmp_path: Path,
) -> None:
    seen_packets: list[dict[str, object]] = []

    def runner(packet: dict[str, object]) -> dict[str, object]:
        seen_packets.append(packet)
        return _workflow_guidance_response()

    service = case_service.CaseService(tmp_path / "store", intelligence_runner=runner)
    service.create(_context(), _payload(), _rule_pack(), "create_1")
    service.enqueue_job(
        _context(),
        "case_2025",
        "intelligence_1",
        "invoke_intelligence",
        {"task": "WORKFLOW_GUIDANCE", "subject_ids": []},
        "rev_1",
    )

    completed = service.run_job(_worker_context(), "case_2025", "intelligence_1")

    assert completed["status"] == "SUCCEEDED"
    assert completed["result"]["revision_id"] == "rev_2"
    assert len(seen_packets) == 1
    assert seen_packets[0]["case_ref"]["revision_id"] == "rev_1"
    assert seen_packets[0]["policy"]["suggestions_are_non_authoritative"] is True
    assert "prepared_invocation" not in completed
    case = case_service.load_case(tmp_path / "store/tenant_1/case_2025")
    assert case["intelligence_runs"][0]["status"] == "MODEL_SUGGESTED"
    assert case["intelligence_runs"][0]["input_revision_id"] == "rev_1"


def test_queued_intelligence_becomes_stale_after_concurrent_professional_edit(
    tmp_path: Path,
) -> None:
    service: object

    def runner(_packet: dict[str, object]) -> dict[str, object]:
        service.mutate(
            _context(),
            "case_2025",
            "determine_forms",
            {
                "metrics": [
                    {
                        "year": 2025,
                        "assets": "1",
                        "revenue": "1",
                        "employees": "1",
                    },
                    {
                        "year": 2024,
                        "assets": "1",
                        "revenue": "1",
                        "employees": "1",
                    },
                ],
                "rule_pack": _rule_pack(),
            },
            "rev_1",
            "professional_edit",
        )
        return _workflow_guidance_response()

    service = case_service.CaseService(tmp_path / "store", intelligence_runner=runner)
    service.create(_context(), _payload(), _rule_pack(), "create_1")
    service.enqueue_job(
        _context(),
        "case_2025",
        "intelligence_stale",
        "invoke_intelligence",
        {"task": "WORKFLOW_GUIDANCE", "subject_ids": []},
        "rev_1",
    )

    completed = service.run_job(_worker_context(), "case_2025", "intelligence_stale")

    assert completed["status"] == "STALE"
    assert completed["last_error"]["code"] == "STALE_REVISION"
    case = case_service.load_case(tmp_path / "store/tenant_1/case_2025")
    assert case["revision_id"] == "rev_2"
    assert case["intelligence_runs"] == []


def test_queued_intelligence_rejects_request_supplied_output(tmp_path: Path) -> None:
    service = case_service.CaseService(tmp_path / "store")
    service.create(_context(), _payload(), _rule_pack(), "create_1")

    with pytest.raises(ValueError, match="requires only task and subject_ids"):
        service.enqueue_job(
            _context(),
            "case_2025",
            "intelligence_1",
            "invoke_intelligence",
            {
                "task": "WORKFLOW_GUIDANCE",
                "subject_ids": [],
                "output": _workflow_guidance_response()["output"],
            },
            "rev_1",
        )
