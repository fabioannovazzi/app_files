from __future__ import annotations

import csv
import hashlib
import json
import shutil
import threading
import zipfile
from contextlib import contextmanager
from copy import deepcopy
from datetime import timedelta
from pathlib import Path
from typing import Any

import pytest
from fastapi import BackgroundTasks, FastAPI
from fastapi.testclient import TestClient

from modules.auth import dependencies as auth_dependencies
from modules.auth.session import AuthenticatedUser
from modules.pdp import attribute_reporting_api
from modules.pdp import attribute_reporting_bridge as bridge_module
from modules.pdp.attribute_reporting_bridge import (
    AttributeReportingBridge,
    BridgeConflictError,
    BridgeNotFoundError,
    BridgeValidationError,
)
from modules.pdp.store import (
    AttributeAuditRecord,
    AttributeMappingConflictError,
    AttributeMappingIdentity,
    AttributeMappingOperationResult,
    AttributeMappingStateRow,
    AttributeValueRecord,
    PDPStore,
)

ACTOR = "analyst@example.com"
VALIDATION_SHA256 = "a" * 64
REVIEW_VALIDATION_SHA256 = "b" * 64
REVIEW_SHA256 = "c" * 64


def _canonical_sha256(payload: dict[str, Any]) -> str:
    encoded = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _taxonomy() -> dict[str, Any]:
    return {
        "version": "2026-07-15",
        "categories": [
            {
                "id": "cashmere_sweaters",
                "label": "Cashmere Sweaters",
                "attributes": [
                    {
                        "id": "neckline",
                        "label": "Neckline",
                        "selection": "single",
                        "nodes": [
                            {"id": "crew", "label": "Crew", "status": "active"},
                            {
                                "id": "retired",
                                "label": "Retired",
                                "status": "inactive",
                            },
                        ],
                    }
                ],
            }
        ],
    }


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


class _FakeMappingEngine:
    def create_mapping_tasks(
        self,
        package_dir: Path,
        taxonomy: dict[str, Any],
        output_path: Path,
        *,
        max_tasks: int = 0,
        include_resolved: bool = False,
    ) -> dict[str, Any]:
        assert max_tasks == 0
        with (package_dir / "product_filter_matrix.csv").open(
            encoding="utf-8", newline=""
        ) as handle:
            source_row = next(csv.DictReader(handle))
        tasks = {
            "schema_version": "attribute_reporting.mapping_tasks.v1",
            "taxonomy_snapshot": {
                "version": taxonomy["version"],
                "sha256": _canonical_sha256(taxonomy),
                "category_key": "cashmere_sweaters",
            },
            "scope": {
                "retailer": "saksfifthavenue",
                "category_key": "cashmere_sweaters",
                "source_package": str(package_dir.resolve()),
            },
            "coverage": {
                "task_count": 1,
                "truncated": False,
                "include_resolved": include_resolved,
            },
            "tasks": [
                {
                    "task_id": "map-one",
                    "product": {
                        "retailer": "saksfifthavenue",
                        "row_type": "parent",
                        "parent_product_id": "product-one",
                        "variant_id": "",
                        "category_key": "cashmere_sweaters",
                        "source_row_sha256": _canonical_sha256(source_row),
                        "brand": "Brand",
                        "title": "Cashmere Crew",
                        "description": "A cashmere sweater.",
                        "pdp_url": "https://example.com/product-one",
                        "local_images": [],
                    },
                    "attribute": {
                        "id": "neckline",
                        "label": "Neckline",
                        "selection": "single",
                        "allowed_values": [{"id": "crew", "label": "Crew"}],
                    },
                    "existing_evidence": [],
                    "existing_evidence_source": ("codex" if include_resolved else None),
                    "mapping_reason": (
                        "migration_recheck" if include_resolved else "unresolved"
                    ),
                }
            ],
        }
        _write_json(output_path, tasks)
        return tasks

    def select_codex_effective_correction_tasks(
        self,
        tasks: list[dict[str, Any]],
        codex_mapping_identities: Any,
    ) -> dict[str, Any]:
        identities = {
            tuple(identity)[1:] if len(tuple(identity)) == 7 else tuple(identity)
            for identity in codex_mapping_identities
        }
        selected: list[dict[str, Any]] = []
        excluded_unresolved = 0
        excluded_non_codex = 0
        excluded_not_pinned = 0
        for task in tasks:
            identity = (
                task["product"]["retailer"],
                task["product"]["row_type"],
                task["product"]["parent_product_id"],
                task["product"]["variant_id"],
                task["product"]["category_key"],
                task["attribute"]["id"],
            )
            if task.get("mapping_reason") != "migration_recheck":
                excluded_unresolved += 1
            elif task.get("existing_evidence_source") != "codex":
                excluded_non_codex += 1
            elif identity not in identities:
                excluded_not_pinned += 1
            else:
                selected.append(task)
        return {
            "schema_version": "attribute_reporting.correction_task_selection.v1",
            "criteria": {"existing_evidence_source": "codex"},
            "task_count_before_selection": len(tasks),
            "task_count": len(selected),
            "excluded_unresolved_count": excluded_unresolved,
            "excluded_non_codex_effective_count": excluded_non_codex,
            "excluded_not_pinned_count": excluded_not_pinned,
            "tasks": selected,
        }

    def verify_mapping_tasks_against_source(
        self, tasks: dict[str, Any], taxonomy: dict[str, Any]
    ) -> dict[str, Any]:
        source_package = Path(tasks["scope"]["source_package"])
        assert source_package.is_absolute()
        assert source_package.is_dir()
        assert tasks["taxonomy_snapshot"]["version"] == taxonomy["version"]
        return dict(tasks["scope"])

    def validate_mapping_payloads(
        self,
        tasks: dict[str, Any],
        decisions: dict[str, Any],
        *,
        taxonomy: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        assert taxonomy is not None
        assert decisions["schema_version"] == "attribute_reporting.mapping_decisions.v1"
        mapping = {
            "task_id": "map-one",
            "retailer": "saksfifthavenue",
            "row_type": "parent",
            "parent_product_id": "product-one",
            "variant_id": "",
            "category_key": "cashmere_sweaters",
            "attribute_id": "neckline",
            "attribute_label": "Neckline",
            "selection": "single",
            "allowed_values": [{"id": "crew", "label": "Crew"}],
            "status": "mapped",
            "value_ids": ["crew"],
            "value_labels": ["Crew"],
            "value_id": "crew",
            "value_label": "Crew",
            "oov_candidate": None,
            "reason": "The product title and image show a crew neckline.",
            "confidence": "high",
            "source": "codex",
        }
        return {
            "schema_version": "attribute_reporting.validated_mapping_decisions.v1",
            "taxonomy_snapshot": dict(tasks["taxonomy_snapshot"]),
            "agent": dict(decisions["agent"]),
            "tasks_sha256": _canonical_sha256(tasks),
            "decisions_sha256": _canonical_sha256(decisions),
            "validation_sha256": VALIDATION_SHA256,
            "mapping_count": 1,
            "mappings": [mapping],
        }

    def validate_mapping_review_payloads(
        self,
        tasks: dict[str, Any],
        decisions: dict[str, Any],
        validated: dict[str, Any],
        review: dict[str, Any],
        *,
        taxonomy: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        assert taxonomy is not None
        assert tasks["tasks"][0]["product"]["local_images"]
        assert validated["validation_sha256"] == VALIDATION_SHA256
        assert review["overall_verdict"] == "approved"
        assert decisions["agent"]["agent_id"] != review["reviewer"]["agent_id"]
        return {
            "review_state": "approved",
            "mapping_review_sha256": REVIEW_SHA256,
            "review_validation_sha256": REVIEW_VALIDATION_SHA256,
            "reviewer": dict(review["reviewer"]),
        }


class _EmptyMappingEngine(_FakeMappingEngine):
    def create_mapping_tasks(
        self,
        package_dir: Path,
        taxonomy: dict[str, Any],
        output_path: Path,
        *,
        max_tasks: int = 0,
        include_resolved: bool = False,
    ) -> dict[str, Any]:
        tasks = super().create_mapping_tasks(
            package_dir,
            taxonomy,
            output_path,
            max_tasks=max_tasks,
            include_resolved=include_resolved,
        )
        tasks["tasks"] = []
        tasks["coverage"]["task_count"] = 0
        _write_json(output_path, tasks)
        return tasks


class _NonCodexEffectiveMappingEngine(_FakeMappingEngine):
    def create_mapping_tasks(
        self,
        package_dir: Path,
        taxonomy: dict[str, Any],
        output_path: Path,
        *,
        max_tasks: int = 0,
        include_resolved: bool = False,
    ) -> dict[str, Any]:
        tasks = super().create_mapping_tasks(
            package_dir,
            taxonomy,
            output_path,
            max_tasks=max_tasks,
            include_resolved=include_resolved,
        )
        if include_resolved:
            tasks["tasks"][0]["existing_evidence_source"] = "retailer_filter"
            _write_json(output_path, tasks)
        return tasks


class _VariableHashMappingEngine(_FakeMappingEngine):
    def validate_mapping_payloads(
        self,
        tasks: dict[str, Any],
        decisions: dict[str, Any],
        *,
        taxonomy: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        result = super().validate_mapping_payloads(
            tasks,
            decisions,
            taxonomy=taxonomy,
        )
        result["validation_sha256"] = _canonical_sha256(
            {"mapping_agent": decisions["agent"]["agent_id"]}
        )
        return result

    def validate_mapping_review_payloads(
        self,
        tasks: dict[str, Any],
        decisions: dict[str, Any],
        validated: dict[str, Any],
        review: dict[str, Any],
        *,
        taxonomy: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        if taxonomy is None:
            raise AssertionError("taxonomy required")
        return {
            "review_state": "approved",
            "mapping_review_sha256": _canonical_sha256(review),
            "review_validation_sha256": _canonical_sha256(
                {
                    "validation_sha256": validated["validation_sha256"],
                    "reviewer": review["reviewer"]["agent_id"],
                }
            ),
            "reviewer": dict(review["reviewer"]),
        }


class _FakeApplyEngine:
    def mapping_record_specs(self, mapping: dict[str, Any]) -> list[dict[str, Any]]:
        assert mapping["value_id"] == "crew"
        return [
            {
                "attribute_id": "neckline",
                "attribute_label": "Neckline",
                "value": "Crew",
                "oov_candidate": None,
                "note": None,
                "decision_rule": "codex_mapped",
                "leaf_value_id": "crew",
            }
        ]


class _FakeStore:
    def __init__(self, *, conflict: bool = False) -> None:
        self.conflict = conflict
        self.calls: list[tuple[list[Any], list[Any], str, bool, bool]] = []
        self.states: dict[
            AttributeMappingIdentity,
            tuple[AttributeMappingStateRow, ...],
        ] = {}
        self.operation_timestamps: dict[str, str] = {}
        self.operation_evidence_json: dict[str, str] = {}

    def read_attribute_mapping_states(
        self,
        *,
        retailer: str,
        category_key: str,
        source: str = "codex",
    ) -> dict[AttributeMappingIdentity, tuple[AttributeMappingStateRow, ...]]:
        return {
            identity: rows
            for identity, rows in self.states.items()
            if identity.retailer == retailer
            and identity.category_key == category_key
            and identity.source == source
        }

    def upsert_attribute_values_with_audit(
        self,
        value_records: list[Any],
        audit_records: list[Any],
        *,
        operation_id: str,
        reject_existing_source_values: bool,
        replace_existing_source_values: bool,
        expected_existing_source_states: (
            dict[
                AttributeMappingIdentity,
                tuple[AttributeMappingStateRow, ...],
            ]
            | None
        ) = None,
        operation_evidence: dict[str, object] | None = None,
        return_operation_result: bool = False,
    ) -> bool | AttributeMappingOperationResult:
        if self.conflict:
            raise AttributeMappingConflictError("accepted mapping now exists")
        committed_at = self.operation_timestamps.get(operation_id)
        if committed_at is not None:
            result = AttributeMappingOperationResult(
                False,
                committed_at,
                self.operation_evidence_json[operation_id],
            )
            return result if return_operation_result else result.applied
        records = list(value_records)
        if replace_existing_source_values:
            if expected_existing_source_states is None or any(
                self.states.get(identity, ()) != rows
                for identity, rows in expected_existing_source_states.items()
            ):
                raise AttributeMappingConflictError(
                    "accepted mapping changed; rebuild the workset"
                )
        grouped: dict[AttributeMappingIdentity, list[AttributeMappingStateRow]] = {}
        for record in records:
            identity = AttributeMappingIdentity(
                source=record.source,
                retailer=record.retailer,
                row_type=record.row_type,
                parent_product_id=record.parent_product_id,
                variant_id=record.variant_id or "",
                category_key=record.category_key or "",
                base_attribute_id=record.attribute_id.split("__", 1)[0],
            )
            grouped.setdefault(identity, []).append(
                AttributeMappingStateRow(
                    attribute_id=record.attribute_id,
                    attribute_label=record.attribute_label,
                    value=record.value,
                    oov_candidate=record.oov_candidate,
                    note=record.note,
                    updated_at=record.updated_at,
                )
            )
        self.states.update(
            {
                identity: tuple(sorted(rows, key=lambda row: row.attribute_id))
                for identity, rows in grouped.items()
            }
        )
        self.calls.append(
            (
                records,
                list(audit_records),
                operation_id,
                reject_existing_source_values,
                replace_existing_source_values,
            )
        )
        committed_at = records[0].updated_at
        self.operation_timestamps[operation_id] = committed_at
        evidence_json = json.dumps(
            {
                "operation_id": operation_id,
                "operation_evidence": dict(operation_evidence or {}),
            },
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        self.operation_evidence_json[operation_id] = evidence_json
        result = AttributeMappingOperationResult(True, committed_at, evidence_json)
        return result if return_operation_result else result.applied


def _package_builder(retailer: str, category: str, output_root: Path) -> Path:
    package = output_root / category / retailer
    package.mkdir(parents=True)
    _write_json(package / "package_integrity.json", {"status": "pass", "issues": []})
    _write_json(
        package / "pack_manifest.json",
        {
            "retailer": retailer,
            "category_key": category,
            "run_dir": str((package / "private-run").resolve()),
            "pdp_store_path": str((package / "private-store").resolve()),
            "files": {"product_filter_matrix": "product_filter_matrix.csv"},
        },
    )
    _write_json(
        package / "summary.json",
        {"retailer": retailer, "category_key": category},
    )
    with (package / "product_filter_matrix.csv").open(
        "w", encoding="utf-8", newline=""
    ) as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=[
                "parent_product_id",
                "local_image_path",
                "pack_image_path",
                "hero_image_url",
                "og_image_url",
            ],
        )
        writer.writeheader()
        writer.writerow(
            {
                "parent_product_id": "product-one",
                "local_image_path": str((package / "source.png").resolve()),
                "pack_image_path": str((package / "images" / "product.png").resolve()),
                "hero_image_url": "https://cdn.example.com/hero.jpg",
                "og_image_url": "https://cdn.example.com/og.jpg",
            }
        )
    images = package / "images"
    images.mkdir()
    (images / "product.png").write_bytes(b"private-image-bytes")
    return package


def _bridge(tmp_path: Path, store: _FakeStore) -> AttributeReportingBridge:
    return AttributeReportingBridge(
        tmp_path / "bridge",
        taxonomy_loader=_taxonomy,
        package_builder=_package_builder,
        mapping_engine=_FakeMappingEngine(),
        mapping_apply_engine=_FakeApplyEngine(),
        store_factory=lambda: store,
        now=lambda: "2026-07-15T12:00:00+00:00",
    )


def _ready_job(
    bridge: AttributeReportingBridge,
) -> tuple[dict[str, Any], dict[str, Any]]:
    snapshot = bridge.taxonomy_snapshot("cashmere_sweaters", actor_email=ACTOR)
    job = bridge.create_evidence_job(
        retailer="saksfifthavenue",
        category_key="cashmere_sweaters",
        taxonomy_version=snapshot["version"],
        taxonomy_sha256=snapshot["sha256"],
        actor_email=ACTOR,
    )
    bridge.build_evidence_job(job["job_id"])
    return snapshot, job


def _mapping_artifacts(workset: dict[str, Any]) -> dict[str, dict[str, Any]]:
    tasks = deepcopy(workset["mapping_tasks"])
    tasks["tasks"][0]["product"]["local_images"] = [
        {"path": "images/product.png", "sha256": "e" * 64}
    ]
    decisions = {
        "schema_version": "attribute_reporting.mapping_decisions.v1",
        "taxonomy_snapshot": dict(tasks["taxonomy_snapshot"]),
        "agent": {"execution": "codex_agent", "agent_id": "mapping-agent"},
        "decisions": [],
    }
    validated = {
        "schema_version": "attribute_reporting.validated_mapping_decisions.v1",
        "validation_sha256": VALIDATION_SHA256,
    }
    review = {
        "schema_version": "attribute_reporting.mapping_review.v1",
        "overall_verdict": "approved",
        "reviewer": {
            "execution": "codex_agent",
            "agent_id": "review-agent",
            "role": "independent_mapping_reviewer",
            "independent_from_author": True,
        },
    }
    return {
        "tasks": tasks,
        "decisions": decisions,
        "validated": validated,
        "review": review,
    }


def _operation_id() -> str:
    return _canonical_sha256(
        {
            "validation_sha256": VALIDATION_SHA256,
            "mapping_review_validation_sha256": REVIEW_VALIDATION_SHA256,
        }
    )


def _variable_mapping_artifacts(
    workset: dict[str, Any],
    *,
    suffix: str,
) -> tuple[dict[str, dict[str, Any]], str]:
    artifacts = _mapping_artifacts(workset)
    mapping_agent = f"mapping-agent-{suffix}"
    reviewer = f"review-agent-{suffix}"
    artifacts["decisions"]["agent"]["agent_id"] = mapping_agent
    artifacts["review"]["reviewer"]["agent_id"] = reviewer
    validation_sha256 = _canonical_sha256({"mapping_agent": mapping_agent})
    artifacts["validated"]["validation_sha256"] = validation_sha256
    review_validation_sha256 = _canonical_sha256(
        {
            "validation_sha256": validation_sha256,
            "reviewer": reviewer,
        }
    )
    operation_id = _canonical_sha256(
        {
            "validation_sha256": validation_sha256,
            "mapping_review_validation_sha256": review_validation_sha256,
        }
    )
    return artifacts, operation_id


def _body_limit_test_app(monkeypatch: pytest.MonkeyPatch) -> FastAPI:
    permission_dependency = (
        attribute_reporting_api._require_attribute_reporting_permission
    )
    monkeypatch.setattr(
        attribute_reporting_api,
        "_require_attribute_reporting_permission",
        lambda _request: None,
    )
    app = FastAPI()
    app.include_router(attribute_reporting_api.router)
    app.dependency_overrides[permission_dependency] = lambda: None
    app.dependency_overrides[attribute_reporting_api.get_attribute_reporting_bridge] = (
        lambda: object()
    )
    return app


def test_attribute_reporting_api_rejects_oversized_body_before_parsing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    app = _body_limit_test_app(monkeypatch)
    monkeypatch.setattr(attribute_reporting_api, "MAX_REQUEST_BODY_BYTES", 8)

    response = TestClient(app).post(
        "/case-notes/api/attribute-reporting/evidence-packs",
        content=b"123456789",
        headers={"content-type": "application/json"},
    )

    assert response.status_code == 413
    assert response.json() == {
        "detail": "Attribute Reporting request body is too large."
    }


def test_attribute_reporting_api_authorizes_before_buffering_large_body(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    app = FastAPI()
    app.include_router(attribute_reporting_api.router)
    monkeypatch.setattr(attribute_reporting_api, "MAX_REQUEST_BODY_BYTES", 8)

    def reject_request(_request: Any) -> None:
        from fastapi import HTTPException

        raise HTTPException(status_code=403, detail="forbidden before body")

    monkeypatch.setattr(
        attribute_reporting_api,
        "_require_attribute_reporting_permission",
        reject_request,
    )

    response = TestClient(app).post(
        "/case-notes/api/attribute-reporting/mapping-worksets/workset/submissions",
        content=b"123456789",
        headers={"content-type": "application/json"},
    )

    assert response.status_code == 403
    assert response.json() == {"detail": "forbidden before body"}


def test_api_reserves_large_body_allowance_only_for_mapping_submissions(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    app = _body_limit_test_app(monkeypatch)
    monkeypatch.setattr(attribute_reporting_api, "MAX_REQUEST_BODY_BYTES", 32)
    monkeypatch.setattr(attribute_reporting_api, "MAX_SMALL_REQUEST_BODY_BYTES", 8)
    client = TestClient(app)
    body = b'{"x":123}'

    small_response = client.post(
        "/case-notes/api/attribute-reporting/evidence-packs",
        content=body,
        headers={"content-type": "application/json"},
    )
    submission_response = client.post(
        "/case-notes/api/attribute-reporting/mapping-worksets/workset/submissions",
        content=body,
        headers={"content-type": "application/json"},
    )

    assert small_response.status_code == 413
    assert submission_response.status_code != 413


def test_authenticated_attribute_reporting_response_is_not_cacheable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class _TaxonomyBridge:
        def taxonomy_snapshot(
            self,
            category_key: str,
            *,
            actor_email: str,
        ) -> dict[str, str]:
            assert category_key == "cashmere_sweaters"
            assert actor_email == "local-dev"
            return {"category_key": category_key}

    app = _body_limit_test_app(monkeypatch)
    app.dependency_overrides[attribute_reporting_api.get_attribute_reporting_bridge] = (
        _TaxonomyBridge
    )

    response = TestClient(app).get(
        "/case-notes/api/attribute-reporting/taxonomies/cashmere_sweaters"
    )

    assert response.status_code == 200
    assert response.headers["cache-control"] == "private, no-store"
    assert response.headers["pragma"] == "no-cache"
    assert response.headers["vary"] == "Cookie"


def test_attribute_reporting_rejects_user_with_only_general_clara_access(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    permissions_path = tmp_path / "site_page_permissions.json"
    _write_json(
        permissions_path,
        {
            "clara": ["*"],
            "attribute_reporting": ["approved@example.com"],
        },
    )
    monkeypatch.setattr(
        auth_dependencies,
        "_SITE_PERMISSIONS_FILE",
        permissions_path,
    )
    auth_dependencies._get_site_permissions.cache_clear()
    monkeypatch.setattr(
        auth_dependencies,
        "require_authenticated_user_for_site",
        lambda _request: AuthenticatedUser(email="unapproved@example.com"),
    )
    app = FastAPI()
    app.include_router(attribute_reporting_api.router)

    response = TestClient(app).get(
        "/case-notes/api/attribute-reporting/taxonomies/cashmere_sweaters"
    )

    assert response.status_code == 403
    assert response.json()["detail"]["page"] == "attribute_reporting"


def test_attribute_reporting_permission_config_is_deployment_specific() -> None:
    config_dir = Path(__file__).resolve().parents[3] / "config"

    assert not (config_dir / "site_page_permissions.json").exists()
    assert (
        json.loads(
            (config_dir / "site_page_permissions.example.json").read_text(
                encoding="utf-8"
            )
        )
        == {}
    )


def test_taxonomy_snapshot_returns_only_active_leaves(tmp_path: Path) -> None:
    bridge = _bridge(tmp_path, _FakeStore())

    snapshot = bridge.taxonomy_snapshot("cashmere_sweaters", actor_email=ACTOR)

    assert snapshot["version"] == "2026-07-15"
    assert snapshot["requested_by"] == ACTOR
    assert snapshot["active_leaves"] == [
        {
            "attribute_id": "neckline",
            "selection": "single",
            "values": [{"id": "crew", "label": "Crew"}],
        }
    ]


def test_api_correction_workset_request_requires_explicit_reason() -> None:
    with pytest.raises(ValueError, match="correction workset requires a reason"):
        attribute_reporting_api.MappingWorksetRequest(
            evidence_job_id="0" * 32,
            taxonomy_version="2026-07-15",
            taxonomy_sha256="a" * 64,
            mapping_mode="correction",
        )


def test_bridge_correction_workset_requires_explicit_reason(tmp_path: Path) -> None:
    bridge = _bridge(tmp_path, _FakeStore())

    with pytest.raises(BridgeValidationError, match="requires an audit reason"):
        bridge.create_mapping_workset(
            evidence_job_id="0" * 32,
            taxonomy_version="2026-07-15",
            taxonomy_sha256="a" * 64,
            actor_email=ACTOR,
            mapping_mode="correction",
        )


def test_queued_evidence_job_fails_if_taxonomy_changes_before_build(
    tmp_path: Path,
) -> None:
    taxonomy = _taxonomy()
    builder_calls: list[tuple[str, str]] = []

    def package_builder(retailer: str, category: str, output_root: Path) -> Path:
        builder_calls.append((retailer, category))
        return _package_builder(retailer, category, output_root)

    bridge = AttributeReportingBridge(
        tmp_path / "bridge",
        taxonomy_loader=lambda: deepcopy(taxonomy),
        package_builder=package_builder,
        mapping_engine=_FakeMappingEngine(),
        mapping_apply_engine=_FakeApplyEngine(),
        store_factory=lambda: _FakeStore(),
        now=lambda: "2026-07-15T12:00:00+00:00",
    )
    snapshot = bridge.taxonomy_snapshot("cashmere_sweaters", actor_email=ACTOR)
    job = bridge.create_evidence_job(
        retailer="saksfifthavenue",
        category_key="cashmere_sweaters",
        taxonomy_version=snapshot["version"],
        taxonomy_sha256=snapshot["sha256"],
        actor_email=ACTOR,
    )
    taxonomy["version"] = "2026-07-16"

    bridge.build_evidence_job(job["job_id"])

    status = bridge.evidence_status(job["job_id"], actor_email=ACTOR)
    assert status["status"] == "failed"
    assert status["error_type"] == "BridgeConflictError"
    assert builder_calls == []


def test_evidence_job_fails_if_taxonomy_changes_during_build(
    tmp_path: Path,
) -> None:
    taxonomy = _taxonomy()

    def changing_builder(retailer: str, category: str, output_root: Path) -> Path:
        package = _package_builder(retailer, category, output_root)
        taxonomy["version"] = "2026-07-16"
        return package

    bridge = AttributeReportingBridge(
        tmp_path / "bridge",
        taxonomy_loader=lambda: deepcopy(taxonomy),
        package_builder=changing_builder,
        mapping_engine=_FakeMappingEngine(),
        mapping_apply_engine=_FakeApplyEngine(),
        store_factory=lambda: _FakeStore(),
        now=lambda: "2026-07-15T12:00:00+00:00",
    )
    snapshot = bridge.taxonomy_snapshot("cashmere_sweaters", actor_email=ACTOR)
    job = bridge.create_evidence_job(
        retailer="saksfifthavenue",
        category_key="cashmere_sweaters",
        taxonomy_version=snapshot["version"],
        taxonomy_sha256=snapshot["sha256"],
        actor_email=ACTOR,
    )

    bridge.build_evidence_job(job["job_id"])

    status = bridge.evidence_status(job["job_id"], actor_email=ACTOR)
    job_dir = bridge.root / "evidence_jobs" / job["job_id"]
    assert status["status"] == "failed"
    assert status["error_type"] == "BridgeConflictError"
    assert not (job_dir / "build").exists()
    assert not (job_dir / "evidence_pack.zip").exists()
    assert not (job_dir / "portable").exists()


def test_evidence_job_fails_if_accepted_mapping_changes_during_build(
    tmp_path: Path,
) -> None:
    store = _FakeStore()

    def changing_builder(retailer: str, category: str, output_root: Path) -> Path:
        package = _package_builder(retailer, category, output_root)
        store.states[_mapping_identity()] = (
            _mapping_state(
                value="Crew",
                updated_at="2026-07-15T12:01:00+00:00",
            ),
        )
        return package

    bridge = AttributeReportingBridge(
        tmp_path / "bridge",
        taxonomy_loader=_taxonomy,
        package_builder=changing_builder,
        mapping_engine=_FakeMappingEngine(),
        mapping_apply_engine=_FakeApplyEngine(),
        store_factory=lambda: store,
        now=lambda: "2026-07-15T12:00:00+00:00",
    )
    snapshot = bridge.taxonomy_snapshot("cashmere_sweaters", actor_email=ACTOR)
    job = bridge.create_evidence_job(
        retailer="saksfifthavenue",
        category_key="cashmere_sweaters",
        taxonomy_version=snapshot["version"],
        taxonomy_sha256=snapshot["sha256"],
        actor_email=ACTOR,
    )

    bridge.build_evidence_job(job["job_id"])

    status = bridge.evidence_status(job["job_id"], actor_email=ACTOR)
    job_dir = bridge.root / "evidence_jobs" / job["job_id"]
    assert status["status"] == "failed"
    assert status["error_type"] == "BridgeConflictError"
    assert not (job_dir / "build").exists()
    assert not (job_dir / "portable").exists()
    assert not (job_dir / "evidence_pack.zip").exists()


def test_evidence_job_quota_is_enforced_per_actor(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(bridge_module, "MAX_ACTOR_EVIDENCE_JOBS", 1)
    bridge = _bridge(tmp_path, _FakeStore())
    snapshot = bridge.taxonomy_snapshot("cashmere_sweaters", actor_email=ACTOR)
    bridge.create_evidence_job(
        retailer="saksfifthavenue",
        category_key="cashmere_sweaters",
        taxonomy_version=snapshot["version"],
        taxonomy_sha256=snapshot["sha256"],
        actor_email=ACTOR,
    )

    with pytest.raises(BridgeConflictError, match="per-user.*quota"):
        bridge.create_evidence_job(
            retailer="saksfifthavenue",
            category_key="cashmere_sweaters",
            taxonomy_version=snapshot["version"],
            taxonomy_sha256=snapshot["sha256"],
            actor_email=ACTOR,
        )

    other_actor = "other@example.com"
    other_snapshot = bridge.taxonomy_snapshot(
        "cashmere_sweaters", actor_email=other_actor
    )
    other_job = bridge.create_evidence_job(
        retailer="saksfifthavenue",
        category_key="cashmere_sweaters",
        taxonomy_version=other_snapshot["version"],
        taxonomy_sha256=other_snapshot["sha256"],
        actor_email=other_actor,
    )
    assert (
        bridge.evidence_status(other_job["job_id"], actor_email=other_actor)
        == other_job
    )


def test_retained_byte_quota_is_enforced_per_actor(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(bridge_module, "MAX_ACTOR_RETAINED_BYTES", 1)
    bridge = _bridge(tmp_path, _FakeStore())
    snapshot = bridge.taxonomy_snapshot("cashmere_sweaters", actor_email=ACTOR)
    bridge.create_evidence_job(
        retailer="saksfifthavenue",
        category_key="cashmere_sweaters",
        taxonomy_version=snapshot["version"],
        taxonomy_sha256=snapshot["sha256"],
        actor_email=ACTOR,
    )

    with pytest.raises(BridgeConflictError, match="retained-byte quota"):
        bridge.create_evidence_job(
            retailer="saksfifthavenue",
            category_key="cashmere_sweaters",
            taxonomy_version=snapshot["version"],
            taxonomy_sha256=snapshot["sha256"],
            actor_email=ACTOR,
        )


def test_distinct_jobs_for_one_actor_do_not_build_concurrently(
    tmp_path: Path,
) -> None:
    first_started = threading.Event()
    release_first = threading.Event()
    build_calls: list[str] = []

    def blocking_builder(retailer: str, category: str, output_root: Path) -> Path:
        build_calls.append(output_root.parent.name)
        if len(build_calls) == 1:
            first_started.set()
            assert release_first.wait(timeout=5)
        return _package_builder(retailer, category, output_root)

    bridge = AttributeReportingBridge(
        tmp_path / "bridge",
        taxonomy_loader=_taxonomy,
        package_builder=blocking_builder,
        mapping_engine=_FakeMappingEngine(),
        mapping_apply_engine=_FakeApplyEngine(),
        store_factory=lambda: _FakeStore(),
        now=lambda: "2026-07-15T12:00:00+00:00",
    )
    snapshot = bridge.taxonomy_snapshot("cashmere_sweaters", actor_email=ACTOR)
    jobs = [
        bridge.create_evidence_job(
            retailer="saksfifthavenue",
            category_key="cashmere_sweaters",
            taxonomy_version=snapshot["version"],
            taxonomy_sha256=snapshot["sha256"],
            actor_email=ACTOR,
        )
        for _ in range(2)
    ]
    first_thread = threading.Thread(
        target=bridge.build_evidence_job,
        args=(jobs[0]["job_id"],),
    )
    first_thread.start()
    assert first_started.wait(timeout=5)

    bridge.build_evidence_job(jobs[1]["job_id"])

    assert (
        bridge.evidence_status(jobs[1]["job_id"], actor_email=ACTOR)["status"]
        == "pending"
    )
    assert len(build_calls) == 1
    release_first.set()
    first_thread.join(timeout=5)
    assert not first_thread.is_alive()

    bridge.build_evidence_job(jobs[1]["job_id"])

    assert (
        bridge.evidence_status(jobs[1]["job_id"], actor_email=ACTOR)["status"]
        == "ready"
    )
    assert len(build_calls) == 2


def test_expired_artifacts_are_pruned_before_quota_is_checked(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    clock = {"now": "2026-07-15T12:00:00+00:00"}
    monkeypatch.setattr(bridge_module, "EVIDENCE_JOB_TTL", timedelta(seconds=1))
    monkeypatch.setattr(bridge_module, "WORKSET_TTL", timedelta(seconds=1))
    monkeypatch.setattr(bridge_module, "SUBMISSION_TTL", timedelta(seconds=1))
    monkeypatch.setattr(bridge_module, "MAX_ACTOR_EVIDENCE_JOBS", 1)
    bridge = AttributeReportingBridge(
        tmp_path / "bridge",
        taxonomy_loader=_taxonomy,
        package_builder=_package_builder,
        mapping_engine=_FakeMappingEngine(),
        mapping_apply_engine=_FakeApplyEngine(),
        store_factory=lambda: _FakeStore(),
        now=lambda: clock["now"],
    )
    snapshot = bridge.taxonomy_snapshot("cashmere_sweaters", actor_email=ACTOR)
    old_job = bridge.create_evidence_job(
        retailer="saksfifthavenue",
        category_key="cashmere_sweaters",
        taxonomy_version=snapshot["version"],
        taxonomy_sha256=snapshot["sha256"],
        actor_email=ACTOR,
    )
    old_workset_dir = bridge.root / "worksets" / "old-workset"
    _write_json(
        old_workset_dir / "metadata.json",
        {
            "requested_by": ACTOR,
            "created_at": clock["now"],
        },
    )
    old_submission_dir = bridge.root / "submissions" / "old-submission"
    _write_json(
        old_submission_dir / "metadata.json",
        {
            "submitted_by": ACTOR,
            "submitted_at": clock["now"],
        },
    )
    clock["now"] = "2026-07-15T12:00:02+00:00"

    replacement = bridge.create_evidence_job(
        retailer="saksfifthavenue",
        category_key="cashmere_sweaters",
        taxonomy_version=snapshot["version"],
        taxonomy_sha256=snapshot["sha256"],
        actor_email=ACTOR,
    )

    assert not (bridge.root / "evidence_jobs" / old_job["job_id"]).exists()
    assert not old_workset_dir.exists()
    assert not old_submission_dir.exists()
    assert (bridge.root / "evidence_jobs" / replacement["job_id"]).is_dir()


def test_evidence_job_is_retained_while_live_workset_depends_on_it(
    tmp_path: Path,
) -> None:
    clock = {"now": "2026-01-01T12:00:00+00:00"}
    bridge = AttributeReportingBridge(
        tmp_path / "bridge",
        taxonomy_loader=_taxonomy,
        package_builder=_package_builder,
        mapping_engine=_FakeMappingEngine(),
        mapping_apply_engine=_FakeApplyEngine(),
        store_factory=lambda: _FakeStore(),
        now=lambda: clock["now"],
    )
    snapshot = bridge.taxonomy_snapshot("cashmere_sweaters", actor_email=ACTOR)
    source_job = bridge.create_evidence_job(
        retailer="saksfifthavenue",
        category_key="cashmere_sweaters",
        taxonomy_version=snapshot["version"],
        taxonomy_sha256=snapshot["sha256"],
        actor_email=ACTOR,
    )
    bridge.build_evidence_job(source_job["job_id"])
    clock["now"] = "2026-01-30T12:00:00+00:00"
    workset = bridge.create_mapping_workset(
        evidence_job_id=source_job["job_id"],
        taxonomy_version=snapshot["version"],
        taxonomy_sha256=snapshot["sha256"],
        actor_email=ACTOR,
    )

    clock["now"] = "2026-02-01T12:00:00+00:00"
    bridge.create_evidence_job(
        retailer="saksfifthavenue",
        category_key="cashmere_sweaters",
        taxonomy_version=snapshot["version"],
        taxonomy_sha256=snapshot["sha256"],
        actor_email=ACTOR,
    )

    assert (bridge.root / "evidence_jobs" / source_job["job_id"]).is_dir()
    assert (bridge.root / "worksets" / workset["workset_id"]).is_dir()

    clock["now"] = "2026-02-07T12:00:01+00:00"
    bridge.create_evidence_job(
        retailer="saksfifthavenue",
        category_key="cashmere_sweaters",
        taxonomy_version=snapshot["version"],
        taxonomy_sha256=snapshot["sha256"],
        actor_email=ACTOR,
    )

    assert not (bridge.root / "evidence_jobs" / source_job["job_id"]).exists()
    assert not (bridge.root / "worksets" / workset["workset_id"]).exists()


def test_pending_submission_retains_expired_workset_and_source_evidence(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    clock = {"now": "2026-01-01T12:00:00+00:00"}
    monkeypatch.setattr(bridge_module, "EVIDENCE_JOB_TTL", timedelta(seconds=1))
    monkeypatch.setattr(bridge_module, "WORKSET_TTL", timedelta(seconds=1))
    bridge = AttributeReportingBridge(
        tmp_path / "bridge",
        taxonomy_loader=_taxonomy,
        package_builder=_package_builder,
        mapping_engine=_FakeMappingEngine(),
        mapping_apply_engine=_FakeApplyEngine(),
        store_factory=lambda: _FakeStore(),
        now=lambda: clock["now"],
    )
    snapshot, source_job = _ready_job(bridge)
    workset = bridge.create_mapping_workset(
        evidence_job_id=source_job["job_id"],
        taxonomy_version=snapshot["version"],
        taxonomy_sha256=snapshot["sha256"],
        actor_email=ACTOR,
    )
    pending_dir = bridge.root / "submissions" / ("d" * 64)
    _write_json(
        pending_dir / "metadata.json",
        {
            "submitted_by": ACTOR,
            "submitted_at": clock["now"],
            "workset_id": workset["workset_id"],
            "status": "pending",
        },
    )
    clock["now"] = "2026-01-01T12:00:02+00:00"

    bridge.create_evidence_job(
        retailer="saksfifthavenue",
        category_key="cashmere_sweaters",
        taxonomy_version=snapshot["version"],
        taxonomy_sha256=snapshot["sha256"],
        actor_email=ACTOR,
    )

    assert (bridge.root / "evidence_jobs" / source_job["job_id"]).is_dir()
    assert (bridge.root / "worksets" / workset["workset_id"]).is_dir()


@pytest.mark.parametrize(
    "unsafe_root",
    [
        Path("relative/attribute-reporting"),
        Path(__file__).resolve().parents[3] / "data" / "pdp" / "attribute-reporting",
    ],
)
def test_bridge_rejects_relative_or_git_workspace_artifact_roots(
    unsafe_root: Path,
) -> None:
    with pytest.raises(RuntimeError, match="absolute path|outside Git"):
        AttributeReportingBridge(unsafe_root)


def test_evidence_download_is_url_only_portable_and_private(tmp_path: Path) -> None:
    bridge = _bridge(tmp_path, _FakeStore())
    _snapshot, job = _ready_job(bridge)

    package_path, receipt = bridge.evidence_download(job["job_id"], actor_email=ACTOR)

    assert receipt["image_policy"] == "urls_only_no_image_bytes"
    with zipfile.ZipFile(package_path) as archive:
        names = archive.namelist()
        assert "server_sanitization_receipt.json" in names
        assert not any(name.startswith("images/") for name in names)
        assert not any(
            Path(name).suffix.casefold() in {".jpg", ".png"} for name in names
        )
        manifest = json.loads(archive.read("pack_manifest.json"))
        matrix = archive.read("product_filter_matrix.csv").decode("utf-8")
        integrity = json.loads(archive.read("package_integrity.json"))
        all_bytes = b"".join(archive.read(name) for name in names)
    assert manifest["run_dir"] is None
    assert manifest["pdp_store_path"] is None
    assert "https://cdn.example.com/hero.jpg" in matrix
    assert "https://cdn.example.com/og.jpg" in matrix
    assert "private-image-bytes" not in all_bytes.decode("utf-8", errors="ignore")
    assert str(tmp_path).encode() not in all_bytes
    assert integrity["status"] == "pass"


def test_mapping_workset_rejects_more_than_the_complete_task_limit(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    bridge = _bridge(tmp_path, _FakeStore())
    snapshot, job = _ready_job(bridge)
    monkeypatch.setattr(bridge_module, "MAX_MAPPING_TASKS", 0)

    with pytest.raises(BridgeConflictError, match="exceeds the server task limit"):
        bridge.create_mapping_workset(
            evidence_job_id=job["job_id"],
            taxonomy_version=snapshot["version"],
            taxonomy_sha256=snapshot["sha256"],
            actor_email=ACTOR,
        )

    worksets_root = bridge.root / "worksets"
    assert not worksets_root.exists() or list(worksets_root.iterdir()) == []


def test_mapping_workset_rejects_generated_artifact_over_byte_limit(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    bridge = _bridge(tmp_path, _FakeStore())
    snapshot, job = _ready_job(bridge)
    monkeypatch.setattr(bridge_module, "MAX_MAPPING_ARTIFACT_BYTES", 1)

    with pytest.raises(
        BridgeValidationError,
        match="Private mapping workset exceeds the artifact byte limit",
    ):
        bridge.create_mapping_workset(
            evidence_job_id=job["job_id"],
            taxonomy_version=snapshot["version"],
            taxonomy_sha256=snapshot["sha256"],
            actor_email=ACTOR,
        )

    worksets_root = bridge.root / "worksets"
    assert not worksets_root.exists() or list(worksets_root.iterdir()) == []


def test_mapping_submission_rejects_more_than_the_task_limit(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    bridge = _bridge(tmp_path, _FakeStore())
    snapshot, job = _ready_job(bridge)
    workset = bridge.create_mapping_workset(
        evidence_job_id=job["job_id"],
        taxonomy_version=snapshot["version"],
        taxonomy_sha256=snapshot["sha256"],
        actor_email=ACTOR,
    )
    artifacts = _mapping_artifacts(workset)
    monkeypatch.setattr(bridge_module, "MAX_MAPPING_TASKS", 0)

    with pytest.raises(BridgeValidationError, match="exceeds the server task limit"):
        bridge.submit_mapping_results(
            workset_id=workset["workset_id"],
            workset_sha256=workset["workset_sha256"],
            idempotency_key=_operation_id(),
            mapping_tasks=artifacts["tasks"],
            decisions=artifacts["decisions"],
            validated_mappings=artifacts["validated"],
            mapping_review=artifacts["review"],
            actor_email=ACTOR,
        )


def test_mapping_submission_rejects_oversized_json_string(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    bridge = _bridge(tmp_path, _FakeStore())
    snapshot, job = _ready_job(bridge)
    workset = bridge.create_mapping_workset(
        evidence_job_id=job["job_id"],
        taxonomy_version=snapshot["version"],
        taxonomy_sha256=snapshot["sha256"],
        actor_email=ACTOR,
    )
    artifacts = _mapping_artifacts(workset)
    maximum_string_length = 128
    artifacts["decisions"]["oversized"] = "x" * (maximum_string_length + 1)
    monkeypatch.setattr(
        bridge_module,
        "MAX_JSON_STRING_LENGTH",
        maximum_string_length,
    )

    with pytest.raises(
        BridgeValidationError,
        match="Mapping decisions contains an oversized string",
    ):
        bridge.submit_mapping_results(
            workset_id=workset["workset_id"],
            workset_sha256=workset["workset_sha256"],
            idempotency_key=_operation_id(),
            mapping_tasks=artifacts["tasks"],
            decisions=artifacts["decisions"],
            validated_mappings=artifacts["validated"],
            mapping_review=artifacts["review"],
            actor_email=ACTOR,
        )


def test_mapping_submission_rejects_non_finite_json_number(tmp_path: Path) -> None:
    bridge = _bridge(tmp_path, _FakeStore())
    snapshot, job = _ready_job(bridge)
    workset = bridge.create_mapping_workset(
        evidence_job_id=job["job_id"],
        taxonomy_version=snapshot["version"],
        taxonomy_sha256=snapshot["sha256"],
        actor_email=ACTOR,
    )
    artifacts = _mapping_artifacts(workset)
    artifacts["decisions"]["invalid_number"] = float("nan")

    with pytest.raises(
        BridgeValidationError,
        match="Mapping decisions contains a non-finite number",
    ):
        bridge.submit_mapping_results(
            workset_id=workset["workset_id"],
            workset_sha256=workset["workset_sha256"],
            idempotency_key=_operation_id(),
            mapping_tasks=artifacts["tasks"],
            decisions=artifacts["decisions"],
            validated_mappings=artifacts["validated"],
            mapping_review=artifacts["review"],
            actor_email=ACTOR,
        )


def test_mapping_submission_rejects_oversized_combined_payload(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    bridge = _bridge(tmp_path, _FakeStore())
    snapshot, job = _ready_job(bridge)
    workset = bridge.create_mapping_workset(
        evidence_job_id=job["job_id"],
        taxonomy_version=snapshot["version"],
        taxonomy_sha256=snapshot["sha256"],
        actor_email=ACTOR,
    )
    artifacts = _mapping_artifacts(workset)
    monkeypatch.setattr(bridge_module, "MAX_MAPPING_SUBMISSION_BYTES", 1)

    with pytest.raises(
        BridgeValidationError,
        match="complete mapping submission exceeds the server byte limit",
    ):
        bridge.submit_mapping_results(
            workset_id=workset["workset_id"],
            workset_sha256=workset["workset_sha256"],
            idempotency_key=_operation_id(),
            mapping_tasks=artifacts["tasks"],
            decisions=artifacts["decisions"],
            validated_mappings=artifacts["validated"],
            mapping_review=artifacts["review"],
            actor_email=ACTOR,
        )


def test_workset_hides_server_path_and_submission_records_actor_and_review(
    tmp_path: Path,
) -> None:
    store = _FakeStore()
    bridge = _bridge(tmp_path, store)
    snapshot, job = _ready_job(bridge)
    workset = bridge.create_mapping_workset(
        evidence_job_id=job["job_id"],
        taxonomy_version=snapshot["version"],
        taxonomy_sha256=snapshot["sha256"],
        actor_email=ACTOR,
    )
    server_tasks_path = (
        bridge.root / "worksets" / workset["workset_id"] / "mapping_tasks.server.json"
    )
    assert (server_tasks_path.stat().st_mode & 0o777) == 0o600
    with (
        bridge.root
        / "evidence_jobs"
        / job["job_id"]
        / "portable"
        / "product_filter_matrix.csv"
    ).open(encoding="utf-8", newline="") as handle:
        portable_row = next(csv.DictReader(handle))
    assert workset["mapping_tasks"]["tasks"][0]["product"][
        "source_row_sha256"
    ] == _canonical_sha256(portable_row)
    artifacts = _mapping_artifacts(workset)

    receipt = bridge.submit_mapping_results(
        workset_id=workset["workset_id"],
        workset_sha256=workset["workset_sha256"],
        idempotency_key=_operation_id(),
        mapping_tasks=artifacts["tasks"],
        decisions=artifacts["decisions"],
        validated_mappings=artifacts["validated"],
        mapping_review=artifacts["review"],
        actor_email=ACTOR,
    )
    repeated = bridge.submit_mapping_results(
        workset_id=workset["workset_id"],
        workset_sha256=workset["workset_sha256"],
        idempotency_key=_operation_id(),
        mapping_tasks=artifacts["tasks"],
        decisions=artifacts["decisions"],
        validated_mappings=artifacts["validated"],
        mapping_review=artifacts["review"],
        actor_email=ACTOR,
    )

    assert workset["mapping_tasks"]["scope"]["source_package"] == (
        f"evidence-job:{job['job_id']}"
    )
    assert str(tmp_path) not in json.dumps(workset)
    assert receipt == repeated
    assert receipt["operation_id"] == _operation_id()
    assert receipt["mapping_review_state"] == "approved"
    assert len(store.calls) == 1
    assert store.calls[0][3:] == (True, False)
    evidence = json.loads(store.calls[0][1][0].evidence_json)
    assert evidence["submission"]["actor_email"] == ACTOR
    assert evidence["mapping_review_validation_sha256"] == REVIEW_VALIDATION_SHA256


def test_unresolved_workset_with_no_tasks_returns_explicit_no_work_status(
    tmp_path: Path,
) -> None:
    store = _FakeStore()
    bridge = AttributeReportingBridge(
        tmp_path / "bridge",
        taxonomy_loader=_taxonomy,
        package_builder=_package_builder,
        mapping_engine=_EmptyMappingEngine(),
        mapping_apply_engine=_FakeApplyEngine(),
        store_factory=lambda: store,
        now=lambda: "2026-07-15T12:00:00+00:00",
    )
    snapshot, job = _ready_job(bridge)

    workset = bridge.create_mapping_workset(
        evidence_job_id=job["job_id"],
        taxonomy_version=snapshot["version"],
        taxonomy_sha256=snapshot["sha256"],
        actor_email=ACTOR,
    )

    assert workset["status"] == "no_work"
    assert workset["mapping_mode"] == "unresolved"
    assert workset["mapping_tasks"]["coverage"]["task_count"] == 0
    assert workset["mapping_tasks"]["tasks"] == []


def test_submission_retry_recovers_database_committed_timestamp_and_provenance(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    store = _FakeStore()
    bridge = _bridge(tmp_path, store)
    snapshot, job = _ready_job(bridge)
    workset = bridge.create_mapping_workset(
        evidence_job_id=job["job_id"],
        taxonomy_version=snapshot["version"],
        taxonomy_sha256=snapshot["sha256"],
        actor_email=ACTOR,
    )
    artifacts = _mapping_artifacts(workset)
    original_write = bridge_module._atomic_write_json
    failed_once = False

    def fail_after_database_commit(path: Path, payload: dict[str, Any]) -> None:
        nonlocal failed_once
        if path.name == "receipt.json" and not failed_once:
            failed_once = True
            raise OSError("simulated filesystem interruption")
        original_write(path, payload)

    monkeypatch.setattr(bridge_module, "_atomic_write_json", fail_after_database_commit)
    with pytest.raises(OSError, match="filesystem interruption"):
        bridge.submit_mapping_results(
            workset_id=workset["workset_id"],
            workset_sha256=workset["workset_sha256"],
            idempotency_key=_operation_id(),
            mapping_tasks=artifacts["tasks"],
            decisions=artifacts["decisions"],
            validated_mappings=artifacts["validated"],
            mapping_review=artifacts["review"],
            actor_email=ACTOR,
        )

    committed_at = "2026-07-15T12:00:00+00:00"
    shutil.rmtree(bridge.root / "submissions" / _operation_id())
    bridge.now = lambda: "2026-07-16T12:00:00+00:00"
    receipt = bridge.submit_mapping_results(
        workset_id=workset["workset_id"],
        workset_sha256=workset["workset_sha256"],
        idempotency_key=_operation_id(),
        mapping_tasks=artifacts["tasks"],
        decisions=artifacts["decisions"],
        validated_mappings=artifacts["validated"],
        mapping_review=artifacts["review"],
        actor_email=ACTOR,
    )

    assert len(store.calls) == 1
    assert receipt["database_write"] == "already_applied"
    assert receipt["submitted_at"] == committed_at
    result_rows = receipt["mapping_state_result"]["groups"][0]["rows"]
    assert {row["updated_at"] for row in result_rows} == {committed_at}


def test_submission_reclaims_crashed_metadata_less_reservation(tmp_path: Path) -> None:
    store = _FakeStore()
    bridge = _bridge(tmp_path, store)
    snapshot, job = _ready_job(bridge)
    workset = bridge.create_mapping_workset(
        evidence_job_id=job["job_id"],
        taxonomy_version=snapshot["version"],
        taxonomy_sha256=snapshot["sha256"],
        actor_email=ACTOR,
    )
    artifacts = _mapping_artifacts(workset)
    crashed_dir = bridge.root / "submissions" / _operation_id()
    crashed_dir.mkdir(parents=True)
    (crashed_dir / ".metadata.json.tmp").write_text("partial", encoding="utf-8")

    receipt = bridge.submit_mapping_results(
        workset_id=workset["workset_id"],
        workset_sha256=workset["workset_sha256"],
        idempotency_key=_operation_id(),
        mapping_tasks=artifacts["tasks"],
        decisions=artifacts["decisions"],
        validated_mappings=artifacts["validated"],
        mapping_review=artifacts["review"],
        actor_email=ACTOR,
    )

    assert receipt["database_write"] == "applied"
    assert not (crashed_dir / ".metadata.json.tmp").exists()
    assert (crashed_dir / "metadata.json").is_file()


def test_correction_submission_explicitly_replaces_and_preserves_audit_reason(
    tmp_path: Path,
) -> None:
    store = _FakeStore()
    store.states[_mapping_identity()] = (_mapping_state(value="V-neck"),)
    bridge = _bridge(tmp_path, store)
    snapshot, job = _ready_job(bridge)
    correction_reason = "Correct an accepted neckline after source-image review."
    workset = bridge.create_mapping_workset(
        evidence_job_id=job["job_id"],
        taxonomy_version=snapshot["version"],
        taxonomy_sha256=snapshot["sha256"],
        actor_email=ACTOR,
        mapping_mode="correction",
        correction_reason=f"  {correction_reason}  ",
    )
    artifacts = _mapping_artifacts(workset)

    receipt = bridge.submit_mapping_results(
        workset_id=workset["workset_id"],
        workset_sha256=workset["workset_sha256"],
        idempotency_key=_operation_id(),
        mapping_tasks=artifacts["tasks"],
        decisions=artifacts["decisions"],
        validated_mappings=artifacts["validated"],
        mapping_review=artifacts["review"],
        actor_email=ACTOR,
    )

    assert workset["mapping_mode"] == "correction"
    assert workset["correction_reason"] == correction_reason
    assert workset["mapping_tasks"]["coverage"]["include_resolved"] is True
    assert receipt["mapping_mode"] == "correction"
    assert receipt["correction_reason"] == correction_reason
    assert len(store.calls) == 1
    assert store.calls[0][3:] == (False, True)
    evidence = json.loads(store.calls[0][1][0].evidence_json)
    assert evidence["submission"]["mapping_mode"] == "correction"
    assert evidence["submission"]["correction_reason"] == correction_reason


def test_correction_excludes_mapping_hidden_by_higher_authority_effective_source(
    tmp_path: Path,
) -> None:
    store = _FakeStore()
    store.states[_mapping_identity()] = (_mapping_state(value="V-neck"),)
    bridge = AttributeReportingBridge(
        tmp_path / "bridge",
        taxonomy_loader=_taxonomy,
        package_builder=_package_builder,
        mapping_engine=_NonCodexEffectiveMappingEngine(),
        mapping_apply_engine=_FakeApplyEngine(),
        store_factory=lambda: store,
        now=lambda: "2026-07-15T12:00:00+00:00",
    )
    snapshot, job = _ready_job(bridge)

    with pytest.raises(
        BridgeConflictError,
        match="no report-effective accepted Codex mappings",
    ):
        bridge.create_mapping_workset(
            evidence_job_id=job["job_id"],
            taxonomy_version=snapshot["version"],
            taxonomy_sha256=snapshot["sha256"],
            actor_email=ACTOR,
            mapping_mode="correction",
            correction_reason="Correct a mapping after source review.",
        )


def test_correction_rejects_codex_effective_task_absent_from_pinned_state(
    tmp_path: Path,
) -> None:
    bridge = _bridge(tmp_path, _FakeStore())
    snapshot, job = _ready_job(bridge)

    with pytest.raises(
        BridgeConflictError,
        match="absent from its pinned database state",
    ):
        bridge.create_mapping_workset(
            evidence_job_id=job["job_id"],
            taxonomy_version=snapshot["version"],
            taxonomy_sha256=snapshot["sha256"],
            actor_email=ACTOR,
            mapping_mode="correction",
            correction_reason="Correct a mapping after source review.",
        )


def test_second_correction_workset_cannot_overwrite_state_changed_by_first(
    tmp_path: Path,
) -> None:
    store = _FakeStore()
    store.states[_mapping_identity()] = (_mapping_state(value="V-neck"),)
    bridge = AttributeReportingBridge(
        tmp_path / "bridge",
        taxonomy_loader=_taxonomy,
        package_builder=_package_builder,
        mapping_engine=_VariableHashMappingEngine(),
        mapping_apply_engine=_FakeApplyEngine(),
        store_factory=lambda: store,
        now=lambda: "2026-07-15T12:00:00+00:00",
    )
    snapshot, job = _ready_job(bridge)
    first_workset = bridge.create_mapping_workset(
        evidence_job_id=job["job_id"],
        taxonomy_version=snapshot["version"],
        taxonomy_sha256=snapshot["sha256"],
        actor_email=ACTOR,
        mapping_mode="correction",
        correction_reason="First independently reviewed correction.",
    )
    second_workset = bridge.create_mapping_workset(
        evidence_job_id=job["job_id"],
        taxonomy_version=snapshot["version"],
        taxonomy_sha256=snapshot["sha256"],
        actor_email=ACTOR,
        mapping_mode="correction",
        correction_reason="Second independently reviewed correction.",
    )
    first_artifacts, first_operation = _variable_mapping_artifacts(
        first_workset,
        suffix="first",
    )
    second_artifacts, second_operation = _variable_mapping_artifacts(
        second_workset,
        suffix="second",
    )
    bridge.submit_mapping_results(
        workset_id=first_workset["workset_id"],
        workset_sha256=first_workset["workset_sha256"],
        idempotency_key=first_operation,
        mapping_tasks=first_artifacts["tasks"],
        decisions=first_artifacts["decisions"],
        validated_mappings=first_artifacts["validated"],
        mapping_review=first_artifacts["review"],
        actor_email=ACTOR,
    )

    with pytest.raises(BridgeConflictError, match="changed; rebuild the workset"):
        bridge.submit_mapping_results(
            workset_id=second_workset["workset_id"],
            workset_sha256=second_workset["workset_sha256"],
            idempotency_key=second_operation,
            mapping_tasks=second_artifacts["tasks"],
            decisions=second_artifacts["decisions"],
            validated_mappings=second_artifacts["validated"],
            mapping_review=second_artifacts["review"],
            actor_email=ACTOR,
        )


def test_post_mapping_evidence_pack_carries_complete_provenance(tmp_path: Path) -> None:
    store = _FakeStore()
    bridge = _bridge(tmp_path, store)
    snapshot, job = _ready_job(bridge)
    workset = bridge.create_mapping_workset(
        evidence_job_id=job["job_id"],
        taxonomy_version=snapshot["version"],
        taxonomy_sha256=snapshot["sha256"],
        actor_email=ACTOR,
    )
    artifacts = _mapping_artifacts(workset)
    bridge.submit_mapping_results(
        workset_id=workset["workset_id"],
        workset_sha256=workset["workset_sha256"],
        idempotency_key=_operation_id(),
        mapping_tasks=artifacts["tasks"],
        decisions=artifacts["decisions"],
        validated_mappings=artifacts["validated"],
        mapping_review=artifacts["review"],
        actor_email=ACTOR,
    )
    next_job = bridge.create_evidence_job(
        retailer="saksfifthavenue",
        category_key="cashmere_sweaters",
        taxonomy_version=snapshot["version"],
        taxonomy_sha256=snapshot["sha256"],
        actor_email=ACTOR,
        mapping_submission_id=_operation_id(),
    )
    bridge.build_evidence_job(next_job["job_id"])

    package_path, receipt = bridge.evidence_download(
        next_job["job_id"], actor_email=ACTOR
    )
    with zipfile.ZipFile(package_path) as archive:
        names = set(archive.namelist())
        submission_receipt = json.loads(archive.read("mapping_submission_receipt.json"))
    assert set(
        {
            "mapping_tasks.json",
            "mapping_decisions.json",
            "validated_mappings.json",
            "mapping_review.json",
            "mapping_submission_receipt.json",
            "mapping_review_validation.json",
        }
    ).issubset(names)
    assert receipt["mapping_submission_id"] == _operation_id()
    assert submission_receipt["submitted_by"] == ACTOR


def test_stale_mapping_submission_cannot_authorize_a_new_evidence_job(
    tmp_path: Path,
) -> None:
    store = _FakeStore()
    bridge = _bridge(tmp_path, store)
    snapshot, job = _ready_job(bridge)
    workset = bridge.create_mapping_workset(
        evidence_job_id=job["job_id"],
        taxonomy_version=snapshot["version"],
        taxonomy_sha256=snapshot["sha256"],
        actor_email=ACTOR,
    )
    artifacts = _mapping_artifacts(workset)
    bridge.submit_mapping_results(
        workset_id=workset["workset_id"],
        workset_sha256=workset["workset_sha256"],
        idempotency_key=_operation_id(),
        mapping_tasks=artifacts["tasks"],
        decisions=artifacts["decisions"],
        validated_mappings=artifacts["validated"],
        mapping_review=artifacts["review"],
        actor_email=ACTOR,
    )
    store.states[_mapping_identity()] = (
        _mapping_state(
            value="V-neck",
            updated_at="2026-07-16T12:00:00+00:00",
        ),
    )

    with pytest.raises(BridgeConflictError, match="Accepted mappings changed"):
        bridge.create_evidence_job(
            retailer="saksfifthavenue",
            category_key="cashmere_sweaters",
            taxonomy_version=snapshot["version"],
            taxonomy_sha256=snapshot["sha256"],
            actor_email=ACTOR,
            mapping_submission_id=_operation_id(),
        )


def test_post_mapping_evidence_job_rejects_provenance_from_another_scope(
    tmp_path: Path,
) -> None:
    bridge = _bridge(tmp_path, _FakeStore())
    snapshot, job = _ready_job(bridge)
    workset = bridge.create_mapping_workset(
        evidence_job_id=job["job_id"],
        taxonomy_version=snapshot["version"],
        taxonomy_sha256=snapshot["sha256"],
        actor_email=ACTOR,
    )
    artifacts = _mapping_artifacts(workset)
    bridge.submit_mapping_results(
        workset_id=workset["workset_id"],
        workset_sha256=workset["workset_sha256"],
        idempotency_key=_operation_id(),
        mapping_tasks=artifacts["tasks"],
        decisions=artifacts["decisions"],
        validated_mappings=artifacts["validated"],
        mapping_review=artifacts["review"],
        actor_email=ACTOR,
    )

    with pytest.raises(BridgeConflictError, match="another retailer/category"):
        bridge.create_evidence_job(
            retailer="anotherretailer",
            category_key="cashmere_sweaters",
            taxonomy_version=snapshot["version"],
            taxonomy_sha256=snapshot["sha256"],
            actor_email=ACTOR,
            mapping_submission_id=_operation_id(),
        )


def test_submission_rejects_non_image_workset_changes(tmp_path: Path) -> None:
    bridge = _bridge(tmp_path, _FakeStore())
    snapshot, job = _ready_job(bridge)
    workset = bridge.create_mapping_workset(
        evidence_job_id=job["job_id"],
        taxonomy_version=snapshot["version"],
        taxonomy_sha256=snapshot["sha256"],
        actor_email=ACTOR,
    )
    artifacts = _mapping_artifacts(workset)
    artifacts["tasks"]["tasks"][0]["product"]["title"] = "Tampered title"

    with pytest.raises(BridgeConflictError, match="Only product.local_images"):
        bridge.submit_mapping_results(
            workset_id=workset["workset_id"],
            workset_sha256=workset["workset_sha256"],
            idempotency_key=_operation_id(),
            mapping_tasks=artifacts["tasks"],
            decisions=artifacts["decisions"],
            validated_mappings=artifacts["validated"],
            mapping_review=artifacts["review"],
            actor_email=ACTOR,
        )


def test_submission_rejects_portable_package_changed_after_workset(
    tmp_path: Path,
) -> None:
    bridge = _bridge(tmp_path, _FakeStore())
    snapshot, job = _ready_job(bridge)
    workset = bridge.create_mapping_workset(
        evidence_job_id=job["job_id"],
        taxonomy_version=snapshot["version"],
        taxonomy_sha256=snapshot["sha256"],
        actor_email=ACTOR,
    )
    matrix_path = (
        bridge.root
        / "evidence_jobs"
        / job["job_id"]
        / "portable"
        / "product_filter_matrix.csv"
    )
    matrix_path.write_text(
        matrix_path.read_text(encoding="utf-8").replace(
            "https://cdn.example.com/hero.jpg",
            "https://cdn.example.com/changed.jpg",
        ),
        encoding="utf-8",
    )
    artifacts = _mapping_artifacts(workset)

    with pytest.raises(BridgeConflictError, match="portable evidence package changed"):
        bridge.submit_mapping_results(
            workset_id=workset["workset_id"],
            workset_sha256=workset["workset_sha256"],
            idempotency_key=_operation_id(),
            mapping_tasks=artifacts["tasks"],
            decisions=artifacts["decisions"],
            validated_mappings=artifacts["validated"],
            mapping_review=artifacts["review"],
            actor_email=ACTOR,
        )


def test_evidence_build_resumes_abandoned_running_job_and_is_idempotent(
    tmp_path: Path,
) -> None:
    build_calls: list[Path] = []

    def tracked_builder(retailer: str, category: str, output_root: Path) -> Path:
        build_calls.append(output_root)
        return _package_builder(retailer, category, output_root)

    bridge = AttributeReportingBridge(
        tmp_path / "bridge",
        taxonomy_loader=_taxonomy,
        package_builder=tracked_builder,
        mapping_engine=_FakeMappingEngine(),
        mapping_apply_engine=_FakeApplyEngine(),
        store_factory=lambda: _FakeStore(),
        now=lambda: "2026-07-15T12:00:00+00:00",
    )
    snapshot = bridge.taxonomy_snapshot("cashmere_sweaters", actor_email=ACTOR)
    job = bridge.create_evidence_job(
        retailer="saksfifthavenue",
        category_key="cashmere_sweaters",
        taxonomy_version=snapshot["version"],
        taxonomy_sha256=snapshot["sha256"],
        actor_email=ACTOR,
    )
    job_dir = bridge.root / "evidence_jobs" / job["job_id"]
    _write_json(
        job_dir / "status.json",
        {
            "schema_version": "attribute_reporting.server_bridge.evidence_status.v1",
            "job_id": job["job_id"],
            "status": "running",
            "attempt": 1,
        },
    )
    partial = job_dir / "build" / "partial.txt"
    partial.parent.mkdir(parents=True)
    partial.write_text("abandoned", encoding="utf-8")

    bridge.build_evidence_job(job["job_id"])
    first_status = bridge.evidence_status(job["job_id"], actor_email=ACTOR)
    bridge.build_evidence_job(job["job_id"])

    assert first_status["status"] == "ready"
    assert first_status["attempt"] == 2
    assert len(build_calls) == 1
    assert not partial.exists()


def test_poll_route_reschedules_pending_job_for_restart_recovery(
    tmp_path: Path,
) -> None:
    bridge = _bridge(tmp_path, _FakeStore())
    snapshot = bridge.taxonomy_snapshot("cashmere_sweaters", actor_email=ACTOR)
    job = bridge.create_evidence_job(
        retailer="saksfifthavenue",
        category_key="cashmere_sweaters",
        taxonomy_version=snapshot["version"],
        taxonomy_sha256=snapshot["sha256"],
        actor_email=ACTOR,
    )
    background_tasks = BackgroundTasks()

    result = attribute_reporting_api.poll_evidence_pack(
        job["job_id"],
        background_tasks,
        type("User", (), {"email": ACTOR})(),
        bridge,
    )

    assert result["status"] == "pending"
    assert len(background_tasks.tasks) == 1
    assert background_tasks.tasks[0].func == bridge.build_evidence_job


def test_submission_translates_shared_mapping_conflict(tmp_path: Path) -> None:
    bridge = _bridge(tmp_path, _FakeStore(conflict=True))
    snapshot, job = _ready_job(bridge)
    workset = bridge.create_mapping_workset(
        evidence_job_id=job["job_id"],
        taxonomy_version=snapshot["version"],
        taxonomy_sha256=snapshot["sha256"],
        actor_email=ACTOR,
    )
    artifacts = _mapping_artifacts(workset)

    with pytest.raises(BridgeConflictError, match="accepted mapping"):
        bridge.submit_mapping_results(
            workset_id=workset["workset_id"],
            workset_sha256=workset["workset_sha256"],
            idempotency_key=_operation_id(),
            mapping_tasks=artifacts["tasks"],
            decisions=artifacts["decisions"],
            validated_mappings=artifacts["validated"],
            mapping_review=artifacts["review"],
            actor_email=ACTOR,
        )


def test_actor_cannot_read_another_actors_job(tmp_path: Path) -> None:
    bridge = _bridge(tmp_path, _FakeStore())
    _snapshot, job = _ready_job(bridge)

    with pytest.raises(BridgeNotFoundError):
        bridge.evidence_status(job["job_id"], actor_email="other@example.com")


class _Cursor:
    def __init__(self, rows: list[tuple[Any, ...]] | None = None) -> None:
        self.rows = rows or []

    def fetchone(self) -> tuple[Any, ...] | None:
        return self.rows[0] if self.rows else None

    def fetchall(self) -> list[tuple[Any, ...]]:
        return list(self.rows)


class _ExistingMappingConnection:
    def __init__(
        self,
        existing_rows: list[tuple[Any, ...]],
        *,
        committed_operation_timestamp: str | None = None,
        committed_operation_evidence_json: str = "{}",
    ) -> None:
        self.existing_rows = existing_rows
        self.committed_operation_timestamp = committed_operation_timestamp
        self.committed_operation_evidence_json = committed_operation_evidence_json
        self.execute_calls: list[str] = []
        self.executemany_calls: list[str] = []
        self.commit_count = 0
        self.transaction_replay_disabled = False

    def disable_transaction_replay(self) -> None:
        self.transaction_replay_disabled = True

    def execute(self, sql: str, _params: tuple[str, ...]) -> _Cursor:
        self.execute_calls.append(sql)
        if "decision_rule = 'codex_mapping_batch'" in sql:
            if self.committed_operation_timestamp is None:
                return _Cursor()
            return _Cursor(
                [
                    (
                        self.committed_operation_timestamp,
                        self.committed_operation_evidence_json,
                    )
                ]
            )
        if "FROM pdp_attribute_values" in sql:
            return _Cursor(self.existing_rows)
        if "FROM parent_products" in sql:
            return _Cursor([(1,)])
        return _Cursor()

    def executemany(self, sql: str, _rows: list[tuple[Any, ...]]) -> None:
        self.executemany_calls.append(sql)

    def commit(self) -> None:
        self.commit_count += 1


class _MappingStateReadConnection:
    def __init__(self, rows: list[tuple[Any, ...]]) -> None:
        self.rows = rows
        self.params: tuple[str, ...] | None = None

    def execute(self, _sql: str, params: tuple[str, ...]) -> _Cursor:
        self.params = params
        return _Cursor(self.rows)


def _mapping_record_pair() -> tuple[AttributeValueRecord, AttributeAuditRecord]:
    value = AttributeValueRecord(
        retailer="saksfifthavenue",
        row_type="parent",
        parent_product_id="product-one",
        variant_id="",
        category_key="cashmere_sweaters",
        attribute_id="neckline",
        attribute_label="Neckline",
        value="Crew",
        oov_candidate=None,
        note=None,
        source="codex",
        updated_at="2026-07-15T12:00:00+00:00",
    )
    audit = AttributeAuditRecord(
        timestamp=value.updated_at,
        source=value.source,
        row_type=value.row_type,
        retailer=value.retailer,
        parent_product_id=value.parent_product_id,
        variant_id=value.variant_id,
        attribute_id=value.attribute_id,
        value=value.value,
        decision_rule="codex_mapped",
        evidence_json="{}",
        category_key=value.category_key,
    )
    return value, audit


def _store_with_connection(connection: _ExistingMappingConnection) -> PDPStore:
    @contextmanager
    def write_connection(_owner: str):
        yield connection

    store = PDPStore.__new__(PDPStore)
    store._write_connection = write_connection
    return store


def _store_with_read_connection(connection: _MappingStateReadConnection) -> PDPStore:
    @contextmanager
    def read_connection():
        yield connection

    store = PDPStore.__new__(PDPStore)
    store._read_connection = read_connection
    return store


def _mapping_identity() -> AttributeMappingIdentity:
    return AttributeMappingIdentity(
        source="codex",
        retailer="saksfifthavenue",
        row_type="parent",
        parent_product_id="product-one",
        variant_id="",
        category_key="cashmere_sweaters",
        base_attribute_id="neckline",
    )


def _mapping_state(
    *,
    value: str | None,
    note: str | None = None,
    updated_at: str = "2026-07-14T12:00:00+00:00",
) -> AttributeMappingStateRow:
    return AttributeMappingStateRow(
        attribute_id="neckline",
        attribute_label="Neckline",
        value=value,
        oov_candidate=None,
        note=note,
        updated_at=updated_at,
    )


def test_store_reads_exact_attribute_mapping_states_by_scope() -> None:
    connection = _MappingStateReadConnection(
        [
            (
                "parent",
                "product-one",
                "",
                "neckline",
                "Neckline",
                "Crew",
                None,
                None,
                "2026-07-15T12:00:00+00:00",
            ),
            (
                "parent",
                "product-one",
                "",
                "neckline__2",
                "Neckline",
                "V-neck",
                None,
                None,
                "2026-07-15T12:00:01+00:00",
            ),
        ]
    )
    store = _store_with_read_connection(connection)

    states = store.read_attribute_mapping_states(
        retailer="saksfifthavenue",
        category_key="cashmere_sweaters",
        source="codex",
    )

    assert connection.params == (
        "saksfifthavenue",
        "cashmere_sweaters",
        "codex",
    )
    assert states == {
        _mapping_identity(): (
            _mapping_state(
                value="Crew",
                updated_at="2026-07-15T12:00:00+00:00",
            ),
            AttributeMappingStateRow(
                attribute_id="neckline__2",
                attribute_label="Neckline",
                value="V-neck",
                oov_candidate=None,
                note=None,
                updated_at="2026-07-15T12:00:01+00:00",
            ),
        )
    }


def test_store_conflict_check_prevents_silent_shared_mapping_overwrite() -> None:
    connection = _ExistingMappingConnection([tuple(_mapping_state(value="Crew"))])
    store = _store_with_connection(connection)
    value, audit = _mapping_record_pair()

    with pytest.raises(AttributeMappingConflictError, match="rebuild the workset"):
        store.upsert_attribute_values_with_audit(
            [value],
            [audit],
            operation_id="f" * 64,
            reject_existing_source_values=True,
        )

    assert connection.executemany_calls == []
    assert connection.commit_count == 0
    assert connection.transaction_replay_disabled is True


def test_store_conflict_check_allows_reviewed_update_of_unresolved_placeholder() -> (
    None
):
    connection = _ExistingMappingConnection(
        [tuple(_mapping_state(value=None, note="no_value"))]
    )
    store = _store_with_connection(connection)
    value, audit = _mapping_record_pair()

    wrote = store.upsert_attribute_values_with_audit(
        [value],
        [audit],
        operation_id="f" * 64,
        reject_existing_source_values=True,
    )

    assert wrote is True
    assert len(connection.executemany_calls) == 2
    assert any(
        "DELETE FROM pdp_attribute_values" in sql for sql in connection.execute_calls
    )
    assert connection.commit_count == 1
    assert connection.transaction_replay_disabled is True


def test_store_idempotent_retry_returns_original_committed_timestamp() -> None:
    committed_at = "2026-07-14T12:00:00+00:00"
    connection = _ExistingMappingConnection(
        [],
        committed_operation_timestamp=committed_at,
    )
    store = _store_with_connection(connection)
    value, audit = _mapping_record_pair()

    result = store.upsert_attribute_values_with_audit(
        [value],
        [audit],
        operation_id="f" * 64,
        return_operation_result=True,
    )

    assert result == AttributeMappingOperationResult(
        applied=False,
        committed_at=committed_at,
        operation_evidence_json="{}",
    )
    assert connection.executemany_calls == []
    assert connection.commit_count == 0


def test_store_explicit_correction_replaces_existing_accepted_mapping() -> None:
    existing_state = _mapping_state(value="V-neck")
    connection = _ExistingMappingConnection([tuple(existing_state)])
    store = _store_with_connection(connection)
    value, audit = _mapping_record_pair()

    wrote = store.upsert_attribute_values_with_audit(
        [value],
        [audit],
        operation_id="f" * 64,
        reject_existing_source_values=False,
        replace_existing_source_values=True,
        expected_existing_source_states={_mapping_identity(): (existing_state,)},
    )

    assert wrote is True
    assert len(connection.executemany_calls) == 2
    assert any(
        "DELETE FROM pdp_attribute_values" in sql for sql in connection.execute_calls
    )
    assert connection.commit_count == 1
    assert connection.transaction_replay_disabled is True


def test_store_explicit_correction_rejects_aba_state_change() -> None:
    expected_state = _mapping_state(
        value="V-neck",
        updated_at="2026-07-14T12:00:00+00:00",
    )
    current_state = _mapping_state(
        value="V-neck",
        updated_at="2026-07-15T12:00:00+00:00",
    )
    connection = _ExistingMappingConnection([tuple(current_state)])
    store = _store_with_connection(connection)
    value, audit = _mapping_record_pair()

    with pytest.raises(AttributeMappingConflictError, match="rebuild the workset"):
        store.upsert_attribute_values_with_audit(
            [value],
            [audit],
            operation_id="f" * 64,
            reject_existing_source_values=False,
            replace_existing_source_values=True,
            expected_existing_source_states={_mapping_identity(): (expected_state,)},
        )

    assert connection.executemany_calls == []
    assert not any(
        "DELETE FROM pdp_attribute_values" in sql for sql in connection.execute_calls
    )
    assert connection.commit_count == 0
    assert connection.transaction_replay_disabled is True


def test_main_application_registers_attribute_reporting_bridge_routes() -> None:
    from modules.pdp.api import create_app

    paths = {route.path for route in create_app().routes}

    assert "/case-notes/api/attribute-reporting/taxonomies/{category_key}" in paths
    assert "/case-notes/api/attribute-reporting/evidence-packs" in paths
    assert (
        "/case-notes/api/attribute-reporting/mapping-worksets/{workset_id}/submissions"
        in paths
    )
