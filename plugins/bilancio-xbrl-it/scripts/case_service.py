#!/usr/bin/env python3
"""Tenant-scoped, idempotent service boundary for Bilancio XBRL cases.

The host must build :class:`RequestContext` from an authenticated session; role
and tenant identifiers are not accepted from a case mutation payload. Exact
accounting behavior remains in ``xbrl_case`` while this layer enforces storage,
authorization, idempotency, and optimistic concurrency.
"""

from __future__ import annotations

import fcntl
import hashlib
import json
import shutil
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Callable, Iterator, Mapping

from access_control import RequestContext, authorize
from artifact_delivery import SignedArtifactDelivery
from build_taxonomy_catalogue import build_catalogue
from intelligence_contract import (
    build_intelligence_packet,
    build_next_intelligence_packet,
)
from review_views import build_review_view
from xbrl_case import (
    SAFE_ID,
    activate_disclosures,
    apply_mapping_decisions,
    approve_case,
    archive_case,
    attach_supporting_document,
    build_statements,
    confirm_parser,
    create_case,
    create_preview,
    determine_forms,
    export_case,
    generate_mapping_candidates,
    ingest_pdf_trial_balance,
    ingest_prior_xbrl,
    ingest_schedule_file,
    ingest_trial_balance,
    load_case,
    load_client_history,
    migrate_regulatory_versions,
    prepare_xbrl_review,
    record_adjustments,
    record_artifact_access,
    record_comparative_reconciliation_decisions,
    record_disclosure_answers,
    record_disclosure_trigger_decisions,
    record_external_validation,
    record_file_security_scan,
    record_intelligence_suggestion,
    record_issue_reviews,
    record_micro_reporting,
    record_narrative_blocks,
    record_pdf_trial_balance_review,
    record_schedule,
    record_schedule_taxonomy_adapter,
    record_statutory_presentation,
    record_taxonomy_catalogue_build,
    record_taxonomy_facts,
    record_taxonomy_mapping_index,
    record_taxonomy_representation,
    remember_client_history,
    run_validation,
    save_case,
    select_form,
)

__all__ = ["CaseService", "LONG_RUNNING_OPERATIONS"]

OPERATION_CAPABILITIES = {
    "ingest": "INGEST",
    "ingest_pdf": "INGEST",
    "ingest_prior_xbrl": "INGEST",
    "attach_supporting_document": "INGEST",
    "confirm_parser": "PREPARE",
    "review_pdf_extraction": "PREPARE",
    "migrate_regulatory_versions": "CONFIGURE",
    "determine_forms": "PREPARE",
    "select_form": "PREPARE",
    "mapping_candidates": "PREPARE",
    "taxonomy_mapping_index": "PREPARE",
    "apply_mappings": "PREPARE",
    "record_adjustments": "PREPARE",
    "record_comparative_reconciliation": "OVERRIDE",
    "record_taxonomy_facts": "PREPARE",
    "record_statutory_presentation": "PREPARE",
    "record_taxonomy_representation": "OVERRIDE",
    "compute_statements": "PREPARE",
    "record_schedule": "PREPARE",
    "record_schedule_taxonomy_adapter": "PREPARE",
    "ingest_schedule": "INGEST",
    "activate_disclosures": "PREPARE",
    "record_disclosure_triggers": "QUESTIONNAIRE",
    "record_answers": "QUESTIONNAIRE",
    "record_narratives": "PREPARE",
    "preview": "PREPARE",
    "validate": "VALIDATE",
    "prepare_xbrl_review": "VALIDATE",
    "approve": "APPROVE",
    "export": "EXPORT",
    "record_external_validation": "EXTERNAL_VALIDATION",
    "record_intelligence": "PREPARE",
    "record_issue_reviews": "OVERRIDE",
    "record_micro_reporting": "OVERRIDE",
    "load_client_history": "PREPARE",
    "remember_client_history": "EXPORT",
    "archive": "ARCHIVE",
    "taxonomy_catalogue_build": "VALIDATE",
    "invoke_intelligence": "PREPARE",
}

LONG_RUNNING_OPERATIONS = frozenset(
    {
        "ingest",
        "ingest_pdf",
        "ingest_prior_xbrl",
        "attach_supporting_document",
        "ingest_schedule",
        "mapping_candidates",
        "taxonomy_mapping_index",
        "record_intelligence",
        "record_narratives",
        "preview",
        "validate",
        "prepare_xbrl_review",
        "export",
        "taxonomy_catalogue_build",
        "invoke_intelligence",
    }
)
TERMINAL_JOB_STATES = frozenset({"SUCCEEDED", "STALE"})


def _canonical_json(value: Any) -> bytes:
    return json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")


def _now() -> str:
    return datetime.now(tz=UTC).isoformat(timespec="seconds")


def re_full_sha256(value: str) -> bool:
    """Return whether *value* is one lowercase hexadecimal SHA-256 digest."""

    return len(value) == 64 and all(
        character in "0123456789abcdef" for character in value
    )


def _job_summary(job: Mapping[str, Any]) -> dict[str, Any]:
    """Return a compact job resource without replaying source-bearing payloads."""

    return {
        "job_id": job["job_id"],
        "case_id": job["case_id"],
        "expected_revision": job["expected_revision"],
        "operation": job["operation"],
        "status": job["status"],
        "attempts": job["attempts"],
        "max_attempts": job["max_attempts"],
        "queued_at": job["queued_at"],
        "started_at": job.get("started_at"),
        "completed_at": job.get("completed_at"),
        "result": job.get("result"),
        "last_error": job.get("last_error"),
        "resource_id": (
            f"xbrl-job://{job['tenant_id']}/{job['case_id']}/{job['job_id']}"
        ),
    }


def _summary(case: Mapping[str, Any]) -> dict[str, Any]:
    validation = case.get("validation") or {}
    presentation = case.get("statutory_presentation") or {}
    return {
        "case_id": case["case_id"],
        "revision_id": case["revision_id"],
        "state": case["state"],
        "period": case["period"],
        "rule_pack_versions": case["rule_pack_versions"],
        "selected_form": case.get("selected_form"),
        "blocking_issues": int(validation.get("blockers", 0)),
        "high_issues": int(validation.get("high", 0)),
        "artifact_ids": [item["file_name"] for item in case.get("artifacts", [])],
        "local_xbrl_status": (case.get("xbrl_review") or {}).get("status"),
        "statutory_presentation": {
            "status": presentation.get("status", "NOT_REVIEWED"),
            "summary": presentation.get("summary"),
        },
        "latest_workflow_guidance": case.get("latest_workflow_guidance"),
        "latest_regulatory_migration": (
            case.get("regulatory_migrations", [])[-1]
            if case.get("regulatory_migrations")
            else None
        ),
    }


class CaseService:
    """File-backed reference service with server-side control enforcement."""

    def __init__(
        self,
        storage_root: Path,
        taxonomy_catalogue_path: Path | None = None,
        taxonomy_package_path: Path | None = None,
        input_root: Path | None = None,
        malware_scanner: Callable[[Path], Mapping[str, Any]] | None = None,
        *,
        require_malware_scan: bool = False,
        artifact_signing_secret: bytes | None = None,
        artifact_download_base_url: str | None = None,
        retention_days: int | None = None,
        taxonomy_registry_path: Path | None = None,
        intelligence_runner: (
            Callable[[Mapping[str, Any]], Mapping[str, Any]] | None
        ) = None,
        statutory_presentation_rule_pack_path: Path | None = None,
        schedule_taxonomy_rule_pack_path: Path | None = None,
    ) -> None:
        if storage_root.is_symlink():
            raise ValueError("Service storage root must not be a symbolic link")
        resolved = storage_root.resolve()
        resolved.mkdir(parents=True, exist_ok=True)
        self.storage_root = resolved
        self.taxonomy_catalogue_path = self._configured_file(
            taxonomy_catalogue_path, "taxonomy catalogue"
        )
        self.taxonomy_package_path = self._configured_file(
            taxonomy_package_path, "taxonomy package"
        )
        self.input_root = self._configured_directory(input_root, "case input root")
        self.malware_scanner = malware_scanner
        self.require_malware_scan = require_malware_scan
        if (artifact_signing_secret is None) != (artifact_download_base_url is None):
            raise ValueError(
                "Artifact signing secret and download base URL must be configured together"
            )
        self.artifact_delivery = (
            SignedArtifactDelivery(
                artifact_signing_secret, str(artifact_download_base_url)
            )
            if artifact_signing_secret is not None
            else None
        )
        if retention_days is not None and (
            isinstance(retention_days, bool) or not 1 <= retention_days <= 3650
        ):
            raise ValueError("Retention days must be from 1 to 3650")
        self.retention_days = retention_days
        self.taxonomy_registry_path = self._configured_file(
            taxonomy_registry_path, "taxonomy registry"
        )
        self.intelligence_runner = intelligence_runner
        default_presentation_rule_pack = (
            Path(__file__).resolve().parents[1]
            / "rulepacks"
            / "it"
            / "statutory-presentation-2026.1.json"
        )
        self.statutory_presentation_rule_pack_path = self._configured_file(
            statutory_presentation_rule_pack_path or default_presentation_rule_pack,
            "statutory presentation rule pack",
        )
        default_schedule_taxonomy_rule_pack = (
            Path(__file__).resolve().parents[1]
            / "rulepacks"
            / "it"
            / "schedule-taxonomy-2026.1.json"
        )
        self.schedule_taxonomy_rule_pack_path = self._configured_file(
            schedule_taxonomy_rule_pack_path or default_schedule_taxonomy_rule_pack,
            "schedule taxonomy rule pack",
        )

    @staticmethod
    def _configured_file(path: Path | None, label: str) -> Path | None:
        if path is None:
            return None
        if path.is_symlink() or not path.is_file():
            raise ValueError(f"Configured {label} must be a regular local file")
        return path.resolve()

    @staticmethod
    def _configured_directory(path: Path | None, label: str) -> Path | None:
        if path is None:
            return None
        if path.is_symlink() or not path.is_dir():
            raise ValueError(f"Configured {label} must be a regular local directory")
        return path.resolve()

    def _controlled_input(self, raw_path: object) -> tuple[Path, dict[str, Any] | None]:
        if self.input_root is None:
            raise ValueError("The service requires a configured case input root")
        source = Path(str(raw_path))
        if any(
            component.is_symlink()
            for component in (source.absolute(), *source.absolute().parents)
        ):
            raise ValueError(
                "Case input path must not contain symbolic-link components"
            )
        if source.is_symlink() or not source.is_file():
            raise ValueError("Case input must be a regular local file")
        resolved = source.resolve()
        if self.input_root not in resolved.parents:
            raise ValueError("Case input path is outside the configured input root")
        before_sha256 = hashlib.sha256(resolved.read_bytes()).hexdigest()
        before_size = resolved.stat().st_size
        if self.malware_scanner is None:
            if self.require_malware_scan:
                raise ValueError(
                    "A configured malware scanner is required before file ingestion"
                )
            return resolved, None
        verdict = dict(self.malware_scanner(resolved))
        after_sha256 = hashlib.sha256(resolved.read_bytes()).hexdigest()
        after_size = resolved.stat().st_size
        if before_sha256 != after_sha256 or before_size != after_size:
            raise ValueError(
                "Case input changed while malware scanning was in progress"
            )
        if str(verdict.get("status")) != "CLEAN":
            raise ValueError("Malware scanner did not return a clean verdict")
        engine = str(verdict.get("engine", "")).strip()
        signature_version = str(verdict.get("signature_version", "")).strip()
        if not engine or not signature_version:
            raise ValueError(
                "Malware scanner must identify its engine and signature version"
            )
        return resolved, {
            "status": "CLEAN",
            "sha256": after_sha256,
            "size_bytes": after_size,
            "engine": engine,
            "signature_version": signature_version,
            "scanned_at": _now(),
        }

    @staticmethod
    def _record_input_scan(
        case: dict[str, Any], receipt: Mapping[str, Any] | None, actor: str
    ) -> dict[str, Any]:
        if receipt is None:
            return case
        return record_file_security_scan(case, receipt, actor)

    def _case_dir(self, tenant_id: str, case_id: str) -> Path:
        if not SAFE_ID.fullmatch(tenant_id) or not SAFE_ID.fullmatch(case_id):
            raise ValueError("Tenant and case identifiers must be safe stable IDs")
        tenant_root = self.storage_root / tenant_id
        unresolved = tenant_root / case_id
        if tenant_root.is_symlink() or unresolved.is_symlink():
            raise ValueError("Tenant and case storage paths must not be symbolic links")
        target = unresolved.resolve()
        if self.storage_root not in target.parents:
            raise ValueError("Case path escapes the configured storage root")
        return target

    @contextmanager
    def _case_lock(self, case_dir: Path) -> Iterator[None]:
        if case_dir.is_symlink():
            raise ValueError("Case directory must not be a symbolic link")
        case_dir.mkdir(parents=True, exist_ok=True)
        lock_path = case_dir / ".service.lock"
        if lock_path.is_symlink():
            raise ValueError("Case lock must not be a symbolic link")
        with lock_path.open("a+b") as handle:
            fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
            try:
                yield
            finally:
                fcntl.flock(handle.fileno(), fcntl.LOCK_UN)

    def _idempotency_paths(self, case_dir: Path, key: str) -> tuple[Path, Path]:
        if not SAFE_ID.fullmatch(key):
            raise ValueError("Idempotency key must be a safe stable identifier")
        directory = case_dir / ".idempotency"
        if directory.is_symlink():
            raise ValueError("Idempotency directory must not be a symbolic link")
        directory.mkdir(parents=True, exist_ok=True)
        record = directory / f"{key}.json"
        checksum = directory / f"{key}.sha256"
        if record.is_symlink() or checksum.is_symlink():
            raise ValueError("Idempotency files must not be symbolic links")
        return record, checksum

    def _load_idempotency(self, case_dir: Path, key: str) -> dict[str, Any]:
        record_path, checksum_path = self._idempotency_paths(case_dir, key)
        if not record_path.is_file() or not checksum_path.is_file():
            raise ValueError("Idempotency record is missing integrity metadata")
        record_bytes = record_path.read_bytes()
        expected_checksum = checksum_path.read_text(encoding="ascii").strip()
        if (
            not re_full_sha256(expected_checksum)
            or hashlib.sha256(record_bytes).hexdigest() != expected_checksum
        ):
            raise ValueError("Idempotency record integrity verification failed")
        payload = json.loads(record_bytes)
        if (
            not isinstance(payload, dict)
            or set(payload) != {"request_hash", "response"}
            or not re_full_sha256(str(payload.get("request_hash", "")))
            or not isinstance(payload.get("response"), dict)
        ):
            raise ValueError("Idempotency record payload is invalid")
        return payload

    def _save_idempotency(
        self, case_dir: Path, key: str, record: Mapping[str, Any]
    ) -> dict[str, Any]:
        record_path, checksum_path = self._idempotency_paths(case_dir, key)
        record_tmp = record_path.with_suffix(".json.tmp")
        checksum_tmp = checksum_path.with_suffix(".sha256.tmp")
        if record_tmp.is_symlink() or checksum_tmp.is_symlink():
            raise ValueError("Temporary idempotency files must not be symbolic links")
        record_bytes = _canonical_json(record) + b"\n"
        record_tmp.write_bytes(record_bytes)
        checksum_tmp.write_text(
            hashlib.sha256(record_bytes).hexdigest() + "\n", encoding="ascii"
        )
        record_tmp.replace(record_path)
        checksum_tmp.replace(checksum_path)
        return self._load_idempotency(case_dir, key)

    def _job_paths(self, case_dir: Path, job_id: str) -> tuple[Path, Path, Path]:
        if not SAFE_ID.fullmatch(job_id):
            raise ValueError("Job identifier must be a safe stable ID")
        directory = case_dir / ".jobs"
        if directory.is_symlink():
            raise ValueError("Case job directory must not be a symbolic link")
        directory.mkdir(parents=True, exist_ok=True)
        record = directory / f"{job_id}.json"
        checksum = directory / f"{job_id}.sha256"
        execution_lock = directory / f"{job_id}.run.lock"
        if any(path.is_symlink() for path in (record, checksum, execution_lock)):
            raise ValueError("Case job files must not be symbolic links")
        return record, checksum, execution_lock

    def _load_job(self, case_dir: Path, job_id: str) -> dict[str, Any]:
        record_path, checksum_path, _ = self._job_paths(case_dir, job_id)
        if not record_path.is_file() or not checksum_path.is_file():
            raise ValueError("Case job does not exist or is missing integrity metadata")
        record_bytes = record_path.read_bytes()
        expected_checksum = checksum_path.read_text(encoding="ascii").strip()
        if not re_full_sha256(expected_checksum):
            raise ValueError("Case job checksum metadata is invalid")
        actual_checksum = hashlib.sha256(record_bytes).hexdigest()
        if actual_checksum != expected_checksum:
            raise ValueError("Case job integrity verification failed")
        payload = json.loads(record_bytes)
        if (
            not isinstance(payload, dict)
            or payload.get("job_id") != job_id
            or payload.get("case_id") != case_dir.name
            or payload.get("tenant_id") != case_dir.parent.name
        ):
            raise ValueError("Case job identity does not match its storage scope")
        return payload

    def _save_job(self, case_dir: Path, job: Mapping[str, Any]) -> dict[str, Any]:
        job_id = str(job["job_id"])
        record_path, checksum_path, _ = self._job_paths(case_dir, job_id)
        record_tmp = record_path.with_suffix(".json.tmp")
        checksum_tmp = checksum_path.with_suffix(".sha256.tmp")
        if record_tmp.is_symlink() or checksum_tmp.is_symlink():
            raise ValueError("Temporary case job files must not be symbolic links")
        record_bytes = _canonical_json(job) + b"\n"
        digest = hashlib.sha256(record_bytes).hexdigest()
        record_tmp.write_bytes(record_bytes)
        checksum_tmp.write_text(digest + "\n", encoding="ascii")
        record_tmp.replace(record_path)
        checksum_tmp.replace(checksum_path)
        return self._load_job(case_dir, job_id)

    @contextmanager
    def _job_execution_lock(self, case_dir: Path, job_id: str) -> Iterator[None]:
        _, _, lock_path = self._job_paths(case_dir, job_id)
        with lock_path.open("a+b") as handle:
            fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
            try:
                yield
            finally:
                fcntl.flock(handle.fileno(), fcntl.LOCK_UN)

    def _idempotent(
        self,
        case_dir: Path,
        key: str,
        request: Mapping[str, Any],
        callback: Callable[[], dict[str, Any]],
    ) -> dict[str, Any]:
        request_hash = hashlib.sha256(_canonical_json(request)).hexdigest()
        record_path, checksum_path = self._idempotency_paths(case_dir, key)
        if record_path.exists() or checksum_path.exists():
            record = self._load_idempotency(case_dir, key)
            if record["request_hash"] != request_hash:
                raise ValueError("Idempotency key was already used for another request")
            return dict(record["response"])
        response = callback()
        record = {"request_hash": request_hash, "response": response}
        return dict(self._save_idempotency(case_dir, key, record)["response"])

    def create(
        self,
        context: RequestContext,
        payload: Mapping[str, Any],
        rule_pack: Mapping[str, Any],
        idempotency_key: str,
    ) -> dict[str, Any]:
        """Create one case under the authenticated tenant namespace."""

        authorize(context, "CREATE")
        case_id = str(payload["case_id"])
        case_dir = self._case_dir(context.tenant_id, case_id)
        request = {
            "operation": "create",
            "payload": dict(payload),
            "rule_pack": dict(rule_pack),
            "actor": context.actor_id,
            "originating_interface": context.originating_interface,
        }
        with self._case_lock(case_dir):

            def perform() -> dict[str, Any]:
                if (case_dir / "case.json").exists():
                    raise ValueError("Case already exists")
                scoped_payload = {**dict(payload), "tenant_id": context.tenant_id}
                case = create_case(
                    case_dir, scoped_payload, rule_pack, context.actor_id
                )
                for event in case["audit_events"]:
                    event["originating_interface"] = context.originating_interface
                save_case(case_dir, case)
                return _summary(case)

            return self._idempotent(case_dir, idempotency_key, request, perform)

    def get(self, context: RequestContext, case_id: str, resource: str = "case") -> Any:
        """Read an allowed structured resource without returning source files."""

        case = load_case(self._case_dir(context.tenant_id, case_id))
        authorize(context, "READ", case)
        resources = {
            "case": _summary(case),
            "mappings": case.get("mappings", []),
            "taxonomy_mapping_index": case.get("taxonomy_mapping_index"),
            "comparative_reconciliation": {
                "decisions": case.get("comparative_reconciliation_decisions", []),
                "result": (case.get("validation") or {}).get(
                    "prior_xbrl_reconciliation"
                ),
            },
            "schedules": case.get("schedules", []),
            "questions": case.get("questionnaire", []),
            "disclosure_triggers": {
                "decisions": case.get("disclosure_trigger_decisions", []),
                "suggestions": case.get("disclosure_activation_suggestions", []),
            },
            "artifacts": case.get("artifacts", []),
            "xbrl_review": case.get("xbrl_review"),
            "audit_events": case.get("audit_events", []),
            "workpaper": (
                case.get("approval", {}).get("snapshot")
                if case.get("approval")
                else None
            ),
        }
        if resource not in resources:
            raise ValueError(f"Unsupported case resource: {resource}")
        return resources[resource]

    def _artifact_file(
        self,
        case_dir: Path,
        case: Mapping[str, Any],
        artifact_id: str,
    ) -> tuple[dict[str, Any], Path]:
        if Path(artifact_id).name != artifact_id or not SAFE_ID.fullmatch(artifact_id):
            raise ValueError("Artifact identifier must be a safe file name")
        if case.get("state") not in {"EXPORTED", "ARCHIVED"} or not case.get(
            "approval"
        ):
            raise ValueError("Artifact downloads require an exported approved case")
        matches = [
            dict(item)
            for item in case.get("artifacts", [])
            if item.get("file_name") == artifact_id
        ]
        if len(matches) != 1:
            raise FileNotFoundError("Artifact is not present in the approved manifest")
        artifact = matches[0]
        revision_id = str(case["approval"]["revision_id"])
        export_root = case_dir / "exports" / revision_id
        candidate = export_root / artifact_id
        if (
            export_root.is_symlink()
            or candidate.is_symlink()
            or not candidate.is_file()
        ):
            raise FileNotFoundError("Artifact file is unavailable or unsafe")
        resolved_root = export_root.resolve()
        resolved = candidate.resolve()
        if resolved.parent != resolved_root:
            raise ValueError("Artifact path escapes the approved export directory")
        content = resolved.read_bytes()
        if len(content) != int(artifact["size_bytes"]):
            raise ValueError("Artifact size no longer matches the approved manifest")
        if hashlib.sha256(content).hexdigest() != str(artifact["sha256"]):
            raise ValueError(
                "Artifact checksum no longer matches the approved manifest"
            )
        return artifact, resolved

    def _case_catalogue_path(
        self, case_dir: Path, case: Mapping[str, Any]
    ) -> Path | None:
        if self.taxonomy_catalogue_path is not None:
            return self.taxonomy_catalogue_path
        receipt = case.get("taxonomy_catalogue_build")
        if not isinstance(receipt, Mapping):
            return None
        file_name = str(receipt.get("file_name", ""))
        if Path(file_name).name != file_name or not SAFE_ID.fullmatch(file_name):
            raise ValueError("Case taxonomy catalogue file name is unsafe")
        directory = case_dir / "taxonomy"
        path = directory / file_name
        if directory.is_symlink() or path.is_symlink() or not path.is_file():
            raise ValueError("Case taxonomy catalogue file is unavailable or unsafe")
        raw = path.read_bytes()
        if len(raw) != int(receipt["size_bytes"]):
            raise ValueError("Case taxonomy catalogue size verification failed")
        if hashlib.sha256(raw).hexdigest() != str(receipt["sha256"]):
            raise ValueError("Case taxonomy catalogue checksum verification failed")
        return path.resolve()

    def _build_case_taxonomy_catalogue(
        self,
        case_dir: Path,
        case: dict[str, Any],
        actor: str,
        revision: str,
        payload: Mapping[str, Any],
    ) -> dict[str, Any]:
        if payload:
            raise ValueError(
                "Taxonomy catalogue build does not accept request-selected inputs"
            )
        if self.taxonomy_package_path is None or self.taxonomy_registry_path is None:
            raise ValueError(
                "Taxonomy catalogue build requires configured package and registry paths"
            )
        registry_raw = self.taxonomy_registry_path.read_bytes()
        registry = json.loads(registry_raw)
        taxonomy_id = str(case["rule_pack_versions"]["taxonomy_id"])
        package_sha256 = hashlib.sha256(
            self.taxonomy_package_path.read_bytes()
        ).hexdigest()
        if str(registry.get("taxonomy_id")) != taxonomy_id:
            raise ValueError("Configured taxonomy registry does not match the case")
        if str(registry.get("taxonomy_package_sha256")) != package_sha256:
            raise ValueError("Configured taxonomy package does not match its registry")
        if str(case.get("taxonomy_checksum")) != package_sha256:
            raise ValueError(
                "Configured taxonomy package does not match the locked case"
            )
        entry_points = registry.get("entry_points")
        if not isinstance(entry_points, Mapping):
            raise ValueError("Configured taxonomy registry has no entry-point mapping")
        official_source = str(registry.get("official_source", "")).strip()
        if not official_source:
            raise ValueError("Configured taxonomy registry has no official source")
        directory = case_dir / "taxonomy"
        if directory.is_symlink():
            raise ValueError("Case taxonomy directory must not be a symbolic link")
        directory.mkdir(parents=True, exist_ok=True)
        file_name = f"catalogue-{revision}.json"
        output = directory / file_name
        temporary = directory / f".{file_name}.tmp"
        if output.is_symlink() or temporary.is_symlink():
            raise ValueError("Case taxonomy catalogue paths must not be symbolic links")
        if output.is_file():
            catalogue = json.loads(output.read_bytes())
            if (
                catalogue.get("taxonomy_id") != taxonomy_id
                or catalogue.get("taxonomy_package_sha256") != package_sha256
            ):
                raise ValueError("Existing case taxonomy catalogue is incompatible")
        else:
            catalogue = build_catalogue(
                self.taxonomy_package_path,
                {str(key): str(value) for key, value in entry_points.items()},
                taxonomy_id,
                package_sha256,
                official_source,
            )
            temporary.write_bytes(_canonical_json(catalogue) + b"\n")
            temporary.replace(output)
        raw = output.read_bytes()
        receipt = {
            "file_name": file_name,
            "sha256": hashlib.sha256(raw).hexdigest(),
            "size_bytes": len(raw),
            "taxonomy_id": taxonomy_id,
            "taxonomy_package_sha256": package_sha256,
            "registry_sha256": hashlib.sha256(registry_raw).hexdigest(),
            "concept_count": len(catalogue.get("concepts", [])),
            "built_at": _now(),
        }
        return record_taxonomy_catalogue_build(case, receipt, actor, revision)

    def issue_artifact_download(
        self,
        context: RequestContext,
        case_id: str,
        artifact_id: str,
        idempotency_key: str,
        *,
        ttl_seconds: int = 300,
    ) -> dict[str, Any]:
        """Issue one authorized, expiring, checksum-bound artifact bearer grant."""

        if self.artifact_delivery is None:
            raise ValueError("Artifact delivery signing is not configured")
        case_dir = self._case_dir(context.tenant_id, case_id)
        request = {
            "operation": "issue_artifact_download",
            "artifact_id": artifact_id,
            "ttl_seconds": ttl_seconds,
            "actor": context.actor_id,
            "originating_interface": context.originating_interface,
        }
        with self._case_lock(case_dir):

            def perform() -> dict[str, Any]:
                case = load_case(case_dir)
                authorize(context, "DOWNLOAD_ARTIFACT", case)
                artifact, _ = self._artifact_file(case_dir, case, artifact_id)
                grant = self.artifact_delivery.issue(
                    {
                        "tenant_id": context.tenant_id,
                        "case_id": case_id,
                        "artifact_id": artifact_id,
                        "sha256": artifact["sha256"],
                    },
                    ttl_seconds=ttl_seconds,
                )
                record_artifact_access(
                    case,
                    "artifact_download_grant_issued",
                    context.actor_id,
                    grant,
                )
                save_case(case_dir, case)
                return {key: value for key, value in grant.items() if key != "token"}

            return self._idempotent(case_dir, idempotency_key, request, perform)

    def redeem_artifact_download(self, token: str) -> dict[str, Any]:
        """Verify one bearer grant, re-check bytes, audit access, and return content."""

        if self.artifact_delivery is None:
            raise ValueError("Artifact delivery signing is not configured")
        claims = self.artifact_delivery.verify(token)
        case_dir = self._case_dir(str(claims["tenant_id"]), str(claims["case_id"]))
        with self._case_lock(case_dir):
            case = load_case(case_dir)
            artifact, path = self._artifact_file(
                case_dir, case, str(claims["artifact_id"])
            )
            if str(artifact["sha256"]) != str(claims["sha256"]):
                raise ValueError(
                    "Artifact grant no longer matches the approved manifest"
                )
            content = path.read_bytes()
            record_artifact_access(
                case,
                "artifact_downloaded",
                f"signed-grant:{claims['grant_id']}",
                claims,
            )
            save_case(case_dir, case)
            media_types = {
                ".html": "text/html; charset=utf-8",
                ".json": "application/json",
                ".xbrl": "application/xbrl+xml",
                ".xml": "application/xml",
            }
            return {
                "file_name": artifact["file_name"],
                "media_type": media_types.get(
                    path.suffix.lower(), "application/octet-stream"
                ),
                "sha256": artifact["sha256"],
                "content": content,
            }

    def _deletion_paths(
        self, tenant_root: Path, case_id: str, idempotency_key: str
    ) -> tuple[Path, Path]:
        if not SAFE_ID.fullmatch(idempotency_key):
            raise ValueError("Idempotency key must be a safe stable identifier")
        directory = tenant_root / ".deletions" / case_id
        if directory.is_symlink():
            raise ValueError("Deletion receipt directory must not be a symbolic link")
        directory.mkdir(parents=True, exist_ok=True)
        record = directory / f"{idempotency_key}.json"
        checksum = directory / f"{idempotency_key}.sha256"
        if record.is_symlink() or checksum.is_symlink():
            raise ValueError("Deletion receipt files must not be symbolic links")
        return record, checksum

    def _load_deletion_receipt(
        self, tenant_root: Path, case_id: str, idempotency_key: str
    ) -> dict[str, Any]:
        record, checksum = self._deletion_paths(tenant_root, case_id, idempotency_key)
        if not record.is_file() or not checksum.is_file():
            raise FileNotFoundError("Deletion receipt is incomplete")
        raw = record.read_bytes()
        expected = checksum.read_text(encoding="ascii").strip()
        if not re_full_sha256(expected) or hashlib.sha256(raw).hexdigest() != expected:
            raise ValueError("Deletion receipt integrity verification failed")
        payload = json.loads(raw)
        if payload.get("case_id") != case_id:
            raise ValueError("Deletion receipt case identity is invalid")
        return payload

    def _save_deletion_receipt(
        self,
        tenant_root: Path,
        case_id: str,
        idempotency_key: str,
        receipt: Mapping[str, Any],
    ) -> dict[str, Any]:
        record, checksum = self._deletion_paths(tenant_root, case_id, idempotency_key)
        raw = _canonical_json(receipt) + b"\n"
        record_tmp = record.with_suffix(".json.tmp")
        checksum_tmp = checksum.with_suffix(".sha256.tmp")
        if record_tmp.is_symlink() or checksum_tmp.is_symlink():
            raise ValueError("Temporary deletion receipt paths are unsafe")
        record_tmp.write_bytes(raw)
        checksum_tmp.write_text(
            hashlib.sha256(raw).hexdigest() + "\n", encoding="ascii"
        )
        record_tmp.replace(record)
        checksum_tmp.replace(checksum)
        return self._load_deletion_receipt(tenant_root, case_id, idempotency_key)

    def delete_archived_case(
        self,
        context: RequestContext,
        case_id: str,
        expected_revision: str,
        idempotency_key: str,
        *,
        reason: str,
    ) -> dict[str, Any]:
        """Purge an archived case after its explicit retention cutoff."""

        normalized_reason = reason.strip()
        if not normalized_reason:
            raise ValueError("Case deletion reason is required")
        case_dir = self._case_dir(context.tenant_id, case_id)
        tenant_root = case_dir.parent
        request = {
            "operation": "delete_archived_case",
            "case_id": case_id,
            "expected_revision": expected_revision,
            "reason": normalized_reason,
            "actor": context.actor_id,
            "originating_interface": context.originating_interface,
        }
        request_hash = hashlib.sha256(_canonical_json(request)).hexdigest()
        receipt_path, _ = self._deletion_paths(tenant_root, case_id, idempotency_key)
        if receipt_path.is_file():
            receipt = self._load_deletion_receipt(tenant_root, case_id, idempotency_key)
            if receipt.get("request_hash") != request_hash:
                raise ValueError("Idempotency key was already used for another request")
            if receipt.get("status") != "DELETED":
                raise RuntimeError("A prior case deletion attempt did not complete")
            return dict(receipt["response"])
        if not case_dir.is_dir():
            raise FileNotFoundError("Archived case does not exist")
        with self._case_lock(case_dir):
            case = load_case(case_dir)
            authorize(context, "DELETE", case)
            if str(case["revision_id"]) != expected_revision:
                raise ValueError(
                    "Stale revision: "
                    f"expected {expected_revision}, current {case['revision_id']}"
                )
            if case.get("state") != "ARCHIVED" or not case.get("archive"):
                raise ValueError("Only an archived case may be deleted")
            retain_until = datetime.fromisoformat(str(case["archive"]["retain_until"]))
            if retain_until.tzinfo is None:
                raise ValueError(
                    "Archived case retention cutoff must include a timezone"
                )
            if datetime.now(tz=UTC) < retain_until.astimezone(UTC):
                raise ValueError("Archived case retention period has not elapsed")
            final_case_sha256 = (
                (case_dir / "case.json.sha256").read_text(encoding="ascii").strip()
            )
            response = {
                "case_id": case_id,
                "status": "DELETED",
                "deleted_at": _now(),
            }
            receipt = {
                "schema_version": 1,
                "tenant_id": context.tenant_id,
                "case_id": case_id,
                "request_hash": request_hash,
                "status": "PENDING",
                "expected_revision": expected_revision,
                "final_case_sha256": final_case_sha256,
                "artifact_checksums": [
                    {
                        "file_name": item["file_name"],
                        "sha256": item["sha256"],
                    }
                    for item in case.get("artifacts", [])
                ],
                "deleted_by": context.actor_id,
                "reason": normalized_reason,
                "response": response,
            }
            self._save_deletion_receipt(tenant_root, case_id, idempotency_key, receipt)
            deleting_root = tenant_root / ".deleting"
            if deleting_root.is_symlink():
                raise ValueError(
                    "Case deletion staging path must not be a symbolic link"
                )
            deleting_root.mkdir(parents=True, exist_ok=True)
            quarantine = deleting_root / f"{case_id}.{idempotency_key}"
            if quarantine.exists() or quarantine.is_symlink():
                raise ValueError("Case deletion staging target already exists")
            case_dir.replace(quarantine)
            try:
                shutil.rmtree(quarantine)
            except OSError:
                receipt["status"] = "FAILED"
                self._save_deletion_receipt(
                    tenant_root, case_id, idempotency_key, receipt
                )
                raise
            receipt["status"] = "DELETED"
            self._save_deletion_receipt(tenant_root, case_id, idempotency_key, receipt)
            return response

    def enqueue_job(
        self,
        context: RequestContext,
        case_id: str,
        job_id: str,
        operation: str,
        payload: Mapping[str, Any],
        expected_revision: str,
        *,
        max_attempts: int = 3,
    ) -> dict[str, Any]:
        """Persist one authorized long-running operation for safe later execution."""

        if operation not in LONG_RUNNING_OPERATIONS:
            raise ValueError(f"Operation is not queueable: {operation}")
        if operation == "taxonomy_catalogue_build" and payload:
            raise ValueError(
                "Taxonomy catalogue build does not accept request-selected inputs"
            )
        if operation == "invoke_intelligence":
            if set(payload) != {"task", "subject_ids"}:
                raise ValueError(
                    "Queued intelligence requires only task and subject_ids"
                )
            if not isinstance(payload["subject_ids"], list) or not all(
                isinstance(item, str) for item in payload["subject_ids"]
            ):
                raise ValueError("Queued intelligence subject_ids must be strings")
        if isinstance(max_attempts, bool) or not 1 <= max_attempts <= 10:
            raise ValueError("Job max_attempts must be an integer from 1 to 10")
        case_dir = self._case_dir(context.tenant_id, case_id)
        request = {
            "case_id": case_id,
            "job_id": job_id,
            "operation": operation,
            "payload": dict(payload),
            "expected_revision": expected_revision,
            "max_attempts": max_attempts,
            "requested_by": {
                "actor_id": context.actor_id,
                "roles": list(context.roles),
                "originating_interface": context.originating_interface,
            },
        }
        request_hash = hashlib.sha256(_canonical_json(request)).hexdigest()
        with self._case_lock(case_dir):
            case = load_case(case_dir)
            authorize(context, "QUEUE", case)
            authorize(context, OPERATION_CAPABILITIES[operation], case)
            if str(case["revision_id"]) != expected_revision:
                raise ValueError(
                    "Stale revision: "
                    f"expected {expected_revision}, current {case['revision_id']}"
                )
            record_path, _, _ = self._job_paths(case_dir, job_id)
            if record_path.exists():
                job = self._load_job(case_dir, job_id)
                if job["request_hash"] != request_hash:
                    raise ValueError(
                        "Job identifier was already used for another request"
                    )
                return _job_summary(job)
            job = {
                "schema_version": 1,
                "tenant_id": context.tenant_id,
                **request,
                "request_hash": request_hash,
                "mutation_idempotency_key": f"job_{request_hash}",
                "status": "PENDING",
                "attempts": 0,
                "queued_at": _now(),
                "started_at": None,
                "completed_at": None,
                "result": None,
                "last_error": None,
                "prepared_invocation": None,
            }
            return _job_summary(self._save_job(case_dir, job))

    def get_job(
        self, context: RequestContext, case_id: str, job_id: str
    ) -> dict[str, Any]:
        """Return the integrity-verified status of one tenant-scoped case job."""

        case_dir = self._case_dir(context.tenant_id, case_id)
        with self._case_lock(case_dir):
            case = load_case(case_dir)
            authorize(context, "READ", case)
            return _job_summary(self._load_job(case_dir, job_id))

    def run_job(
        self, worker_context: RequestContext, case_id: str, job_id: str
    ) -> dict[str, Any]:
        """Execute or safely replay one queued operation as a trusted worker."""

        case_dir = self._case_dir(worker_context.tenant_id, case_id)
        with self._job_execution_lock(case_dir, job_id):
            with self._case_lock(case_dir):
                case = load_case(case_dir)
                authorize(worker_context, "RUN_JOBS", case)
                job = self._load_job(case_dir, job_id)
                if job["status"] in TERMINAL_JOB_STATES:
                    return _job_summary(job)
                if job["status"] == "FAILED" and job["attempts"] >= job["max_attempts"]:
                    return _job_summary(job)
                job["status"] = "RUNNING"
                job["attempts"] += 1
                job["started_at"] = _now()
                job["completed_at"] = None
                job["last_error"] = None
                self._save_job(case_dir, job)

            requester = job["requested_by"]
            request_context = RequestContext(
                tenant_id=job["tenant_id"],
                actor_id=str(requester["actor_id"]),
                roles=tuple(str(role) for role in requester["roles"]),
                originating_interface=str(requester["originating_interface"]),
            )
            try:
                if job["operation"] == "invoke_intelligence":
                    if self.intelligence_runner is None:
                        raise RuntimeError(
                            "A host intelligence runner is required for this job"
                        )
                    prepared = job.get("prepared_invocation")
                    if prepared is None:
                        packet = self.intelligence_packet(
                            request_context,
                            job["case_id"],
                            str(job["payload"]["task"]),
                            [str(item) for item in job["payload"]["subject_ids"]],
                        )
                        prepared = dict(self.intelligence_runner(packet))
                        if set(prepared) != {"output", "model_metadata"} or not all(
                            isinstance(prepared[key], Mapping)
                            for key in ("output", "model_metadata")
                        ):
                            raise ValueError(
                                "Host intelligence response requires object output and model_metadata"
                            )
                        with self._case_lock(case_dir):
                            current_job = self._load_job(case_dir, job_id)
                            current_job["prepared_invocation"] = prepared
                            job = self._save_job(case_dir, current_job)
                    result = self.mutate(
                        request_context,
                        job["case_id"],
                        "record_intelligence",
                        {
                            "task": job["payload"]["task"],
                            "subject_ids": job["payload"]["subject_ids"],
                            "output": prepared["output"],
                            "model_metadata": prepared["model_metadata"],
                        },
                        job["expected_revision"],
                        job["mutation_idempotency_key"],
                    )
                else:
                    result = self.mutate(
                        request_context,
                        job["case_id"],
                        job["operation"],
                        job["payload"],
                        job["expected_revision"],
                        job["mutation_idempotency_key"],
                    )
            except (
                OSError,
                PermissionError,
                RuntimeError,
                TypeError,
                ValueError,
            ) as exc:
                with self._case_lock(case_dir):
                    current_case = load_case(case_dir)
                    current_job = self._load_job(case_dir, job_id)
                    idempotency_record, idempotency_checksum = self._idempotency_paths(
                        case_dir, str(job["mutation_idempotency_key"])
                    )
                    stale = str(current_case["revision_id"]) != job[
                        "expected_revision"
                    ] and not (
                        idempotency_record.is_file() and idempotency_checksum.is_file()
                    )
                    current_job["status"] = "STALE" if stale else "FAILED"
                    current_job["completed_at"] = _now()
                    current_job["last_error"] = {
                        "code": "STALE_REVISION" if stale else type(exc).__name__,
                        "message": str(exc)[:1000],
                    }
                    return _job_summary(self._save_job(case_dir, current_job))

            with self._case_lock(case_dir):
                current_job = self._load_job(case_dir, job_id)
                current_job["status"] = "SUCCEEDED"
                current_job["completed_at"] = _now()
                current_job["result"] = result
                current_job["last_error"] = None
                return _job_summary(self._save_job(case_dir, current_job))

    def mutate(
        self,
        context: RequestContext,
        case_id: str,
        operation: str,
        payload: Mapping[str, Any],
        expected_revision: str,
        idempotency_key: str,
    ) -> dict[str, Any]:
        """Run one authorized, revision-bound case mutation exactly once."""

        if operation not in OPERATION_CAPABILITIES:
            raise ValueError(f"Unsupported service operation: {operation}")
        case_dir = self._case_dir(context.tenant_id, case_id)
        request = {
            "operation": operation,
            "payload": dict(payload),
            "expected_revision": expected_revision,
            "actor": context.actor_id,
            "originating_interface": context.originating_interface,
        }
        with self._case_lock(case_dir):

            def perform() -> dict[str, Any]:
                case = load_case(case_dir)
                authorize(context, OPERATION_CAPABILITIES[operation], case)
                if str(case["revision_id"]) != expected_revision:
                    raise ValueError(
                        "Stale revision: "
                        f"expected {expected_revision}, current {case['revision_id']}"
                    )
                prior_event_count = len(case.get("audit_events", []))
                updated = self._dispatch(
                    case_dir,
                    case,
                    operation,
                    payload,
                    context.actor_id,
                    expected_revision,
                )
                for event in updated.get("audit_events", [])[prior_event_count:]:
                    event["originating_interface"] = context.originating_interface
                save_case(case_dir, updated)
                return _summary(updated)

            return self._idempotent(case_dir, idempotency_key, request, perform)

    def intelligence_packet(
        self,
        context: RequestContext,
        case_id: str,
        task: str,
        subject_ids: list[str],
    ) -> dict[str, Any]:
        """Return minimum-necessary context for one semantic model task."""

        case = load_case(self._case_dir(context.tenant_id, case_id))
        authorize(context, "READ", case)
        if task == "AUTO":
            return build_next_intelligence_packet(case)
        return build_intelligence_packet(case, task, subject_ids)

    def review_view(
        self,
        context: RequestContext,
        case_id: str,
        view: str,
        *,
        offset: int = 0,
        limit: int = 200,
    ) -> dict[str, Any]:
        """Return one authorized, paginated professional-review data contract."""

        case = load_case(self._case_dir(context.tenant_id, case_id))
        authorize(context, "READ", case)
        return build_review_view(case, view, offset=offset, limit=limit)

    def _dispatch(
        self,
        case_dir: Path,
        case: dict[str, Any],
        operation: str,
        payload: Mapping[str, Any],
        actor: str,
        revision: str,
    ) -> dict[str, Any]:
        if operation == "ingest":
            source, receipt = self._controlled_input(payload["source_path"])
            updated = ingest_trial_balance(
                case,
                source,
                actor,
                revision,
                str(payload["sheet"]) if payload.get("sheet") else None,
            )
            return self._record_input_scan(updated, receipt, actor)
        if operation == "ingest_pdf":
            source, receipt = self._controlled_input(payload["source_path"])
            ocr_enabled = payload.get("ocr_enabled", True)
            if not isinstance(ocr_enabled, bool):
                raise ValueError("PDF ocr_enabled must be a boolean")
            updated = ingest_pdf_trial_balance(
                case,
                source,
                actor,
                revision,
                ocr_enabled=ocr_enabled,
                ocr_language=str(payload.get("ocr_language", "it")),
            )
            return self._record_input_scan(updated, receipt, actor)
        if operation == "ingest_prior_xbrl":
            source, receipt = self._controlled_input(payload["source_path"])
            updated = ingest_prior_xbrl(case, source, actor, revision)
            return self._record_input_scan(updated, receipt, actor)
        if operation == "attach_supporting_document":
            source, receipt = self._controlled_input(payload["source_path"])
            updated = attach_supporting_document(
                case,
                source,
                str(payload["purpose"]),
                str(payload["description"]),
                actor,
                revision,
            )
            return self._record_input_scan(updated, receipt, actor)
        if operation == "confirm_parser":
            return confirm_parser(case, str(payload["convention"]), actor, revision)
        if operation == "review_pdf_extraction":
            return record_pdf_trial_balance_review(
                case,
                payload,
                actor,
                revision,
            )
        if operation == "migrate_regulatory_versions":
            return migrate_regulatory_versions(case, payload, actor, revision)
        if operation == "determine_forms":
            return determine_forms(
                case, payload["metrics"], payload["rule_pack"], actor, revision
            )
        if operation == "select_form":
            return select_form(case, str(payload["form"]), actor, revision)
        if operation == "mapping_candidates":
            memory = case_dir.parent / "mapping-memory.json"
            return generate_mapping_candidates(
                case, memory, str(payload["source_system_template"]), actor, revision
            )
        if operation == "taxonomy_mapping_index":
            catalogue_path = self._case_catalogue_path(case_dir, case)
            if catalogue_path is None:
                raise ValueError("Taxonomy mapping index requires a catalogue")
            if self.statutory_presentation_rule_pack_path is None:
                raise ValueError(
                    "Taxonomy mapping index requires a presentation rule pack"
                )
            rule_pack = json.loads(
                self.statutory_presentation_rule_pack_path.read_bytes()
            )
            return record_taxonomy_mapping_index(
                case, catalogue_path, rule_pack, actor, revision
            )
        if operation == "apply_mappings":
            return apply_mapping_decisions(case, payload["decisions"], actor, revision)
        if operation == "record_adjustments":
            return record_adjustments(case, payload["adjustments"], actor, revision)
        if operation == "record_comparative_reconciliation":
            return record_comparative_reconciliation_decisions(
                case, payload["decisions"], actor, revision
            )
        if operation == "record_taxonomy_facts":
            return record_taxonomy_facts(case, payload["facts"], actor, revision)
        if operation == "record_statutory_presentation":
            catalogue_path = self._case_catalogue_path(case_dir, case)
            if catalogue_path is None:
                raise ValueError(
                    "Statutory presentation review requires a taxonomy catalogue"
                )
            if self.statutory_presentation_rule_pack_path is None:
                raise ValueError(
                    "Statutory presentation review requires a configured rule pack"
                )
            rule_pack = json.loads(
                self.statutory_presentation_rule_pack_path.read_bytes()
            )
            return record_statutory_presentation(
                case,
                catalogue_path,
                rule_pack,
                payload.get("decisions", []),
                actor,
                revision,
            )
        if operation == "record_taxonomy_representation":
            return record_taxonomy_representation(case, payload, actor, revision)
        if operation == "compute_statements":
            return build_statements(case, actor, revision)
        if operation == "record_schedule":
            return record_schedule(case, payload["schedule"], actor, revision)
        if operation == "record_schedule_taxonomy_adapter":
            catalogue_path = self._case_catalogue_path(case_dir, case)
            if catalogue_path is None:
                raise ValueError("Schedule taxonomy review requires a catalogue")
            if self.schedule_taxonomy_rule_pack_path is None:
                raise ValueError(
                    "Schedule taxonomy review requires a configured rule pack"
                )
            rule_pack = json.loads(self.schedule_taxonomy_rule_pack_path.read_bytes())
            return record_schedule_taxonomy_adapter(
                case,
                catalogue_path,
                rule_pack,
                payload.get("decisions", []),
                actor,
                revision,
            )
        if operation == "ingest_schedule":
            source, receipt = self._controlled_input(payload["source_path"])
            updated = ingest_schedule_file(
                case,
                source,
                str(payload["schedule_type"]),
                str(payload["schedule_id"]),
                (
                    str(payload["statement_line"])
                    if payload.get("statement_line")
                    else None
                ),
                payload.get("options", {}),
                actor,
                revision,
                str(payload["sheet"]) if payload.get("sheet") else None,
            )
            return self._record_input_scan(updated, receipt, actor)
        if operation == "activate_disclosures":
            return activate_disclosures(case, payload["rule_pack"], actor, revision)
        if operation == "record_disclosure_triggers":
            return record_disclosure_trigger_decisions(
                case, payload["decisions"], actor, revision
            )
        if operation == "record_answers":
            return record_disclosure_answers(case, payload["answers"], actor, revision)
        if operation == "record_narratives":
            return record_narrative_blocks(case, payload["blocks"], actor, revision)
        if operation == "preview":
            return create_preview(
                case, case_dir / "artifacts" / "preview.html", actor, revision
            )
        if operation == "validate":
            return run_validation(case, actor, revision)
        if operation == "prepare_xbrl_review":
            catalogue_path = self._case_catalogue_path(case_dir, case)
            if catalogue_path is None or self.taxonomy_package_path is None:
                raise ValueError(
                    "The service requires configured taxonomy catalogue and package paths"
                )
            return prepare_xbrl_review(
                case,
                catalogue_path,
                self.taxonomy_package_path,
                case_dir / "artifacts" / f"xbrl-review-{case['revision_id']}",
                actor,
                revision,
            )
        if operation == "approve":
            return approve_case(case, actor, revision, payload["declaration"])
        if operation == "export":
            catalogue_path = self._case_catalogue_path(case_dir, case)
            if catalogue_path is None:
                raise ValueError(
                    "The service requires a configured taxonomy catalogue path"
                )
            return export_case(
                case,
                case_dir / "exports" / str(case["revision_id"]),
                catalogue_path,
                actor,
            )
        if operation == "record_external_validation":
            source, receipt = self._controlled_input(payload["report_path"])
            updated = record_external_validation(
                case,
                source,
                str(payload["result"]),
                payload.get("reported_issues", []),
                actor,
                revision,
            )
            return self._record_input_scan(updated, receipt, actor)
        if operation == "record_intelligence":
            return record_intelligence_suggestion(
                case,
                str(payload["task"]),
                payload.get("subject_ids", []),
                payload["output"],
                payload["model_metadata"],
                actor,
                revision,
            )
        if operation == "record_issue_reviews":
            return record_issue_reviews(case, payload["decisions"], actor, revision)
        if operation == "record_micro_reporting":
            return record_micro_reporting(case, payload, actor, revision)
        if operation == "load_client_history":
            return load_client_history(
                case, case_dir.parent / "client-history.json", actor, revision
            )
        if operation == "remember_client_history":
            return remember_client_history(
                case, case_dir.parent / "client-history.json", actor, revision
            )
        if operation == "archive":
            if self.retention_days is None:
                raise ValueError("A host retention policy is required before archiving")
            return archive_case(
                case,
                actor,
                revision,
                retention_days=self.retention_days,
                reason=str(payload.get("reason", "")),
            )
        if operation == "taxonomy_catalogue_build":
            return self._build_case_taxonomy_catalogue(
                case_dir, case, actor, revision, payload
            )
        raise AssertionError(operation)
