from __future__ import annotations

import hashlib
import importlib.util
import json
import sys
from pathlib import Path

from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parents[2]
PLUGIN_ROOT = ROOT / "plugins" / "bilancio-xbrl-it"
SCRIPTS = PLUGIN_ROOT / "scripts"
RULE_PACK_PATH = PLUGIN_ROOT / "rulepacks" / "it" / "statutory-forms-2026.1.json"


def _load_module(name: str):
    if str(SCRIPTS) not in sys.path:
        sys.path.insert(0, str(SCRIPTS))
    path = SCRIPTS / f"{name}.py"
    spec = importlib.util.spec_from_file_location(f"bilancio_http_{name}", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


case_service = _load_module("case_service")
http_api = _load_module("http_api")


def _context(roles: tuple[str, ...] = ("PREPARER",)):
    return case_service.RequestContext(
        tenant_id="tenant_api",
        actor_id="actor_api",
        roles=roles,
        originating_interface="pytest-http",
    )


def _payload() -> dict[str, object]:
    return {
        "case_id": "case_api_2025",
        "tenant_id": "untrusted_payload_tenant",
        "entity": {
            "legal_name": "API S.r.l.",
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


def _client(tmp_path: Path, roles: tuple[str, ...] = ("PREPARER",)) -> TestClient:
    service = case_service.CaseService(tmp_path / "store")
    rule_pack = json.loads(RULE_PACK_PATH.read_text(encoding="utf-8"))
    app = http_api.create_app(service, rule_pack, lambda _request: _context(roles))
    return TestClient(app)


def test_http_api_requires_host_authenticated_context(tmp_path: Path) -> None:
    service = case_service.CaseService(tmp_path / "store")
    rule_pack = json.loads(RULE_PACK_PATH.read_text(encoding="utf-8"))
    client = TestClient(http_api.create_app(service, rule_pack))

    response = client.get("/v1/xbrl-cases/case_missing")

    assert response.status_code == 401


def test_http_case_create_is_idempotent_and_uses_authenticated_tenant(
    tmp_path: Path,
) -> None:
    client = _client(tmp_path)
    headers = {"Idempotency-Key": "create_1"}

    first = client.post("/v1/xbrl-cases", json=_payload(), headers=headers)
    replay = client.post("/v1/xbrl-cases", json=_payload(), headers=headers)

    assert first.status_code == 201
    assert replay.json() == first.json()
    stored = json.loads(
        (tmp_path / "store/tenant_api/case_api_2025/case.json").read_text(
            encoding="utf-8"
        )
    )
    assert stored["tenant_id"] == "tenant_api"


def test_http_case_create_rejects_request_selected_rule_pack(tmp_path: Path) -> None:
    client = _client(tmp_path)
    untrusted = json.loads(RULE_PACK_PATH.read_text(encoding="utf-8"))

    response = client.post(
        "/v1/xbrl-cases",
        json={"payload": _payload(), "rule_pack": untrusted},
        headers={"Idempotency-Key": "create_1"},
    )

    assert response.status_code == 422
    assert "deployment configuration" in response.json()["detail"]


def test_http_mutation_requires_idempotency_and_revision_headers(
    tmp_path: Path,
) -> None:
    client = _client(tmp_path)
    client.post(
        "/v1/xbrl-cases",
        json=_payload(),
        headers={"Idempotency-Key": "create_1"},
    )

    missing = client.post(
        "/v1/xbrl-cases/case_api_2025/determine-forms",
        json={"metrics": []},
    )

    assert missing.status_code == 422


def test_http_statutory_presentation_route_is_revision_bound(tmp_path: Path) -> None:
    client = _client(tmp_path)
    client.post(
        "/v1/xbrl-cases",
        json=_payload(),
        headers={"Idempotency-Key": "create_1"},
    )

    response = client.post(
        "/v1/xbrl-cases/case_api_2025/statutory-presentation",
        json={"decisions": []},
        headers={"Idempotency-Key": "presentation_1", "If-Match": "rev_1"},
    )

    assert response.status_code == 422
    assert "taxonomy catalogue" in response.json()["detail"]


def test_http_mutation_replay_and_stale_revision_are_distinct(tmp_path: Path) -> None:
    client = _client(tmp_path)
    client.post(
        "/v1/xbrl-cases",
        json=_payload(),
        headers={"Idempotency-Key": "create_1"},
    )
    body = {
        "metrics": [
            {"year": 2025, "assets": "1", "revenue": "1", "employees": "1"},
            {"year": 2024, "assets": "1", "revenue": "1", "employees": "1"},
        ]
    }
    headers = {"Idempotency-Key": "forms_1", "If-Match": '"rev_1"'}

    first = client.post(
        "/v1/xbrl-cases/case_api_2025/determine-forms",
        json=body,
        headers=headers,
    )
    replay = client.post(
        "/v1/xbrl-cases/case_api_2025/determine-forms",
        json=body,
        headers=headers,
    )
    stale = client.post(
        "/v1/xbrl-cases/case_api_2025/determine-forms",
        json=body,
        headers={"Idempotency-Key": "forms_2", "If-Match": "rev_1"},
    )

    assert first.status_code == 200
    assert first.json()["revision_id"] == "rev_2"
    assert replay.json() == first.json()
    assert stale.status_code == 409
    assert "Stale revision" in stale.json()["detail"]


def test_http_regulatory_migration_returns_change_report_for_admin(
    tmp_path: Path,
) -> None:
    client = _client(tmp_path, ("STUDIO_ADMIN",))
    client.post(
        "/v1/xbrl-cases",
        json=_payload(),
        headers={"Idempotency-Key": "create_1"},
    )

    response = client.post(
        "/v1/xbrl-cases/case_api_2025/regulatory-migrations",
        json=_regulatory_migration(),
        headers={"Idempotency-Key": "migration_1", "If-Match": "rev_1"},
    )

    assert response.status_code == 200
    assert response.json()["latest_regulatory_migration"]["revalidation_status"] == (
        "REQUIRED"
    )


def test_http_read_resources_and_review_view_return_compact_json(
    tmp_path: Path,
) -> None:
    client = _client(tmp_path)
    client.post(
        "/v1/xbrl-cases",
        json=_payload(),
        headers={"Idempotency-Key": "create_1"},
    )

    case = client.get("/v1/xbrl-cases/case_api_2025")
    mappings = client.get("/v1/xbrl-cases/case_api_2025/mappings")
    dashboard = client.get("/v1/xbrl-cases/case_api_2025/review-views/CASE_DASHBOARD")

    assert case.status_code == 200
    assert set(case.json()) >= {"case_id", "revision_id", "state"}
    assert mappings.json() == []
    assert dashboard.json()["next_action"] == "INGEST_TRIAL_BALANCE"


def test_http_role_failure_is_forbidden_before_domain_approval(
    tmp_path: Path,
) -> None:
    client = _client(tmp_path)
    client.post(
        "/v1/xbrl-cases",
        json=_payload(),
        headers={"Idempotency-Key": "create_1"},
    )

    response = client.post(
        "/v1/xbrl-cases/case_api_2025/approve",
        json={"declaration": {}},
        headers={"Idempotency-Key": "approve_1", "If-Match": "rev_1"},
    )

    assert response.status_code == 403
    assert "APPROVE" in response.json()["detail"]


def test_http_job_uses_idempotency_header_as_stable_job_identifier(
    tmp_path: Path,
) -> None:
    client = _client(tmp_path)
    client.post(
        "/v1/xbrl-cases",
        json=_payload(),
        headers={"Idempotency-Key": "create_1"},
    )

    queued = client.post(
        "/v1/xbrl-cases/case_api_2025/jobs",
        json={"operation": "validate", "payload": {}},
        headers={"Idempotency-Key": "validate_job_1", "If-Match": "rev_1"},
    )
    status = client.get("/v1/xbrl-cases/case_api_2025/jobs/validate_job_1")

    assert queued.status_code == 202
    assert queued.json() == status.json()
    assert status.json()["status"] == "PENDING"


def test_http_adapter_issues_and_redeems_short_lived_artifact_grant(
    tmp_path: Path,
) -> None:
    storage = tmp_path / "store"
    service = case_service.CaseService(
        storage,
        artifact_signing_secret=b"s" * 32,
        artifact_download_base_url="/v1/xbrl-artifacts/download",
    )
    context = _context(("REVIEWER",))
    rule_pack = json.loads(RULE_PACK_PATH.read_text(encoding="utf-8"))
    service.create(context, _payload(), rule_pack, "create_1")
    case_dir = storage / "tenant_api/case_api_2025"
    case = case_service.load_case(case_dir)
    case["state"] = "EXPORTED"
    case["approval"] = {"revision_id": "rev_1"}
    content = b"approved workpaper"
    output = case_dir / "exports/rev_1"
    output.mkdir(parents=True)
    (output / "workpaper.json").write_bytes(content)
    case["artifacts"] = [
        {
            "file_name": "workpaper.json",
            "sha256": hashlib.sha256(content).hexdigest(),
            "size_bytes": len(content),
        }
    ]
    case_service.save_case(case_dir, case)
    app = http_api.create_app(service, rule_pack, lambda _request: context)
    client = TestClient(app)

    grant = client.post(
        "/v1/xbrl-cases/case_api_2025/artifacts/workpaper.json/download-grants",
        headers={"Idempotency-Key": "grant_1"},
        json={"ttl_seconds": 60},
    )
    downloaded = client.get(grant.json()["download_url"])

    assert grant.status_code == 201
    assert downloaded.status_code == 200
    assert downloaded.content == content
    assert downloaded.headers["cache-control"] == "private, no-store"
    assert downloaded.headers["x-content-type-options"] == "nosniff"
