#!/usr/bin/env python3
"""Validate Clara privacy-surface coverage and source freshness.

The checks are deterministic because workflow registration, manifest shape,
hosted-service references, confirmation consistency, and byte fingerprints are
mechanically verifiable. Purpose-based data minimisation and legal compliance
remain outside this validator.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import logging
from collections.abc import Iterable, Mapping
from pathlib import Path, PurePosixPath
from typing import Any

__all__ = ["main", "validate_privacy_surfaces"]

LOGGER = logging.getLogger(__name__)

SKIP_DIRS = {".git", ".mypy_cache", ".pytest_cache", ".ruff_cache", "__pycache__"}
SKIP_SUFFIXES = {".pyc", ".pyo"}
REVIEW_SKILL = "privacy-surface-review"
CODEX_CONTEXT_POLICY = "real_professional_data_may_enter_codex_context"
BOUNDARY_KINDS = {
    "public_research",
    "hosted_service",
    "external_connector",
    "send_or_publish",
}
ACCOUNT_REVIEW_ITEMS = [
    "account_or_workspace_plan",
    "model_training_data_controls",
    "retention_and_deletion_controls",
]
ORDINARY_CODEX_MODEL_PROCESSING = {
    "scope": "content_supplied_to_the_codex_model",
    "account_arrangement": "user_selected_chatgpt_or_codex_account",
    "separate_clara_recipient_or_arrangement": False,
    "automatic_anonymisation": False,
    "local_filter_or_aggregate": "only_when_useful_for_professional_work",
    "plan_visibility": "not_inspected_or_enforced_by_clara",
}
RETENTION_STATUSES = {
    "documented",
    "partially_documented",
    "not_established_by_plugin_source",
}


def _clara_root() -> Path:
    return Path(__file__).resolve().parents[3]


def _workflow_names(clara_root: Path) -> set[str]:
    skills_root = clara_root / "skills"
    return {
        path.parent.name
        for path in skills_root.glob("*/SKILL.md")
        if path.parent.name != REVIEW_SKILL
    }


def _physical_target(clara_root: Path, logical_path: str) -> Path:
    logical = PurePosixPath(logical_path)
    if logical.is_absolute() or ".." in logical.parts:
        raise ValueError(f"governed path must be plugin-relative: {logical_path}")
    if logical.parts and logical.parts[0] == "repository":
        return clara_root.parents[1].joinpath(*logical.parts[1:])
    target = clara_root.joinpath(*logical.parts)
    if target.exists() or logical.parts[:2] != ("modules", "attribute-reporting"):
        return target
    return clara_root.parent.joinpath("attribute-reporting", *logical.parts[2:])


def _governed_files(clara_root: Path, paths: Iterable[str]) -> list[tuple[str, Path]]:
    files: dict[str, Path] = {}
    for logical_path in paths:
        target = _physical_target(clara_root, logical_path)
        logical = PurePosixPath(logical_path)
        if target.is_file():
            files[logical.as_posix()] = target
            continue
        if not target.is_dir():
            raise FileNotFoundError(f"governed path not found: {logical_path}")
        for path in target.rglob("*"):
            if not path.is_file():
                continue
            relative = path.relative_to(target)
            if any(part in SKIP_DIRS for part in relative.parts):
                continue
            if path.suffix in SKIP_SUFFIXES:
                continue
            name = (logical / PurePosixPath(relative.as_posix())).as_posix()
            files[name] = path
    return sorted(files.items())


def _fingerprint(clara_root: Path, paths: Iterable[str]) -> str:
    digest = hashlib.sha256()
    for logical_path, path in _governed_files(clara_root, paths):
        name = logical_path.encode("utf-8")
        digest.update(len(name).to_bytes(4, "big"))
        digest.update(name)
        content = path.read_bytes()
        digest.update(len(content).to_bytes(8, "big"))
        digest.update(content)
    return digest.hexdigest()


def _non_empty_string(value: Any) -> bool:
    return isinstance(value, str) and bool(value.strip())


def _string_list(value: Any, *, allow_empty: bool = False) -> bool:
    return (
        isinstance(value, list)
        and (allow_empty or bool(value))
        and all(_non_empty_string(item) for item in value)
        and len(value) == len(set(value))
    )


def _review_errors(
    review: Any,
    *,
    subject: str,
    expected_basis: str,
) -> list[str]:
    if not isinstance(review, Mapping):
        return [f"{subject}: review must be an object"]
    errors: list[str] = []
    if not _non_empty_string(review.get("reviewed_at")):
        errors.append(f"{subject}: reviewed_at must be non-empty")
    if review.get("reviewed_by") != REVIEW_SKILL:
        errors.append(f"{subject}: unexpected reviewer")
    if review.get("basis") != expected_basis:
        errors.append(f"{subject}: unexpected review basis")
    fingerprint = review.get("source_fingerprint")
    if (
        not isinstance(fingerprint, str)
        or len(fingerprint) != 64
        or any(character not in "0123456789abcdef" for character in fingerprint)
    ):
        errors.append(f"{subject}: invalid source fingerprint")
    return errors


def _context_errors(context: Any, *, subject: str) -> list[str]:
    if not isinstance(context, Mapping):
        return [f"{subject}: codex_context must be an object"]
    errors: list[str] = []
    if context.get("policy") != CODEX_CONTEXT_POLICY:
        errors.append(f"{subject}: unexpected Codex context policy")
    classes = context.get("classes")
    if not isinstance(classes, list) or not classes:
        return errors + [f"{subject}: codex_context.classes must be non-empty"]
    identifiers: list[str] = []
    for index, item in enumerate(classes):
        if not isinstance(item, Mapping) or not all(
            _non_empty_string(item.get(field)) for field in ("id", "purpose", "content")
        ):
            errors.append(f"{subject}: codex_context.classes[{index}] is incomplete")
            continue
        identifiers.append(str(item["id"]))
    if len(identifiers) != len(set(identifiers)):
        errors.append(f"{subject}: Codex context ids must be unique")
    return errors


def _account_errors(account: Any, *, subject: str) -> list[str]:
    if not isinstance(account, Mapping):
        return [f"{subject}: codex_account_boundary must be an object"]
    errors: list[str] = []
    if account.get("selected_by") != "firm_or_user":
        errors.append(f"{subject}: account must be selected by the firm or user")
    if account.get("clara_runtime_enforcement") != "none":
        errors.append(f"{subject}: Clara cannot claim to enforce account settings")
    if (
        account.get("review_timing")
        != "before_professional_use_and_when_account_or_terms_change"
    ):
        errors.append(f"{subject}: account review timing is inaccurate")
    if account.get("review_items") != ACCOUNT_REVIEW_ITEMS:
        errors.append(f"{subject}: incomplete Codex account boundary review")
    if account.get("per_case_record_required") is not False:
        errors.append(f"{subject}: account review must not require a per-case record")
    return errors


def _control_errors(controls: Any, *, subject: str) -> list[str]:
    # Array shape and stable identifiers are mechanical release invariants. An
    # empty array is valid: inventing a control is worse than recording that a
    # workflow has no source-enforced security control of its own.
    if not isinstance(controls, list):
        return [f"{subject}: security_controls must be an array"]
    errors: list[str] = []
    identifiers: list[str] = []
    for index, control in enumerate(controls):
        if not isinstance(control, Mapping) or not all(
            _non_empty_string(control.get(field)) for field in ("id", "control")
        ):
            errors.append(f"{subject}: security_controls[{index}] is incomplete")
            continue
        identifiers.append(str(control["id"]))
    if len(identifiers) != len(set(identifiers)):
        errors.append(f"{subject}: security control ids must be unique")
    return errors


def _workflow_errors(
    payload: Any,
    *,
    workflow: str,
    service_ids: set[str],
) -> list[str]:
    subject = f"workflow {workflow}"
    if not isinstance(payload, Mapping):
        return [f"{subject}: manifest must be an object"]
    required = {
        "schema_version",
        "workflow",
        "display_name",
        "governed_paths",
        "codex_context",
        "ordinary_codex_model_processing",
        "codex_account_boundary",
        "hosted_service_ids",
        "boundaries_beyond_codex",
        "security_controls",
        "review",
    }
    missing = sorted(required - payload.keys())
    if missing:
        return [f"{subject}: missing fields: {', '.join(missing)}"]
    errors: list[str] = []
    if payload.get("schema_version") != 1:
        errors.append(f"{subject}: schema_version must be 1")
    if payload.get("workflow") != workflow:
        errors.append(f"{subject}: manifest workflow does not match filename")
    if not _non_empty_string(payload.get("display_name")):
        errors.append(f"{subject}: display_name must be non-empty")
    if not _string_list(payload.get("governed_paths")):
        errors.append(f"{subject}: governed_paths must be unique non-empty strings")
    errors.extend(_context_errors(payload.get("codex_context"), subject=subject))
    if (
        payload.get("ordinary_codex_model_processing")
        != ORDINARY_CODEX_MODEL_PROCESSING
    ):
        errors.append(
            f"{subject}: ordinary Codex model processing policy is inaccurate"
        )
    errors.extend(
        _account_errors(payload.get("codex_account_boundary"), subject=subject)
    )

    hosted_ids = payload.get("hosted_service_ids")
    if not _string_list(hosted_ids, allow_empty=True):
        errors.append(f"{subject}: hosted_service_ids must be unique strings")
        hosted_ids = []
    for service_id in hosted_ids:
        if service_id not in service_ids:
            errors.append(f"{subject}: unknown hosted service {service_id}")

    boundaries = payload.get("boundaries_beyond_codex")
    if not isinstance(boundaries, list):
        errors.append(f"{subject}: boundaries_beyond_codex must be an array")
        boundaries = []
    boundary_ids: list[str] = []
    referenced_services: set[str] = set()
    for index, boundary in enumerate(boundaries):
        label = f"{subject}: boundary[{index}]"
        if not isinstance(boundary, Mapping):
            errors.append(f"{label} must be an object")
            continue
        if not all(
            _non_empty_string(boundary.get(field))
            for field in ("id", "destination", "purpose", "content")
        ):
            errors.append(f"{label} text must be non-empty")
        boundary_ids.append(str(boundary.get("id", "")))
        kind = boundary.get("kind")
        if kind not in BOUNDARY_KINDS:
            errors.append(f"{label} has invalid kind")
        optional = boundary.get("optional")
        confirmation = boundary.get("requires_confirmation")
        if not isinstance(optional, bool) or not isinstance(confirmation, bool):
            errors.append(f"{label} flags must be boolean")
        elif confirmation and not optional:
            errors.append(f"{label} confirmation is allowed only when optional")
        controls = boundary.get("controls")
        if not _string_list(controls):
            errors.append(f"{label} controls must be unique non-empty strings")
        hosted_service_id = boundary.get("hosted_service_id")
        if kind == "hosted_service":
            if not _non_empty_string(hosted_service_id):
                errors.append(f"{label} must name hosted_service_id")
            else:
                referenced_services.add(str(hosted_service_id))
        elif hosted_service_id is not None:
            errors.append(f"{label} non-hosted boundary cannot name a hosted service")
    if len(boundary_ids) != len(set(boundary_ids)):
        errors.append(f"{subject}: boundary ids must be unique")
    if set(hosted_ids) != referenced_services:
        errors.append(
            f"{subject}: hosted_service_ids must exactly match hosted boundaries"
        )

    errors.extend(_control_errors(payload.get("security_controls"), subject=subject))
    errors.extend(
        _review_errors(
            payload.get("review"),
            subject=subject,
            expected_basis="external_boundary_review_of_workflow_source",
        )
    )
    return errors


def _data_class_errors(value: Any, *, subject: str, field: str) -> list[str]:
    if not isinstance(value, list) or not value:
        return [f"{subject}: {field} must be non-empty"]
    errors: list[str] = []
    identifiers: list[str] = []
    for index, item in enumerate(value):
        if not isinstance(item, Mapping) or not all(
            _non_empty_string(item.get(key)) for key in ("id", "when", "content")
        ):
            errors.append(f"{subject}: {field}[{index}] is incomplete")
            continue
        identifiers.append(str(item["id"]))
    if len(identifiers) != len(set(identifiers)):
        errors.append(f"{subject}: {field} ids must be unique")
    return errors


def _service_errors(
    payload: Any,
    *,
    service_id: str,
    workflow_names: set[str],
) -> list[str]:
    subject = f"hosted service {service_id}"
    if not isinstance(payload, Mapping):
        return [f"{subject}: manifest must be an object"]
    required = {
        "schema_version",
        "service_id",
        "display_name",
        "provider_or_recipients",
        "workflows",
        "governed_paths",
        "trigger",
        "automatic",
        "data_sent",
        "data_returned",
        "access",
        "retention",
        "security_controls",
        "review",
    }
    missing = sorted(required - payload.keys())
    if missing:
        return [f"{subject}: missing fields: {', '.join(missing)}"]
    errors: list[str] = []
    if payload.get("schema_version") != 1:
        errors.append(f"{subject}: schema_version must be 1")
    if payload.get("service_id") != service_id:
        errors.append(f"{subject}: service_id does not match filename")
    if not _non_empty_string(payload.get("display_name")):
        errors.append(f"{subject}: display_name must be non-empty")
    if not _string_list(payload.get("provider_or_recipients")):
        errors.append(f"{subject}: provider_or_recipients must be non-empty")
    workflows = payload.get("workflows")
    if not _string_list(workflows):
        errors.append(f"{subject}: workflows must be unique non-empty strings")
        workflows = []
    for workflow in workflows:
        if workflow not in workflow_names:
            errors.append(f"{subject}: unknown workflow {workflow}")
    if not _string_list(payload.get("governed_paths")):
        errors.append(f"{subject}: governed_paths must be unique non-empty strings")
    if not _non_empty_string(payload.get("trigger")):
        errors.append(f"{subject}: trigger must be non-empty")
    if not isinstance(payload.get("automatic"), bool):
        errors.append(f"{subject}: automatic must be boolean")
    errors.extend(
        _data_class_errors(payload.get("data_sent"), subject=subject, field="data_sent")
    )
    errors.extend(
        _data_class_errors(
            payload.get("data_returned"), subject=subject, field="data_returned"
        )
    )
    access = payload.get("access")
    if not isinstance(access, Mapping):
        errors.append(f"{subject}: access must be an object")
    else:
        if not _non_empty_string(access.get("arrangement")):
            errors.append(f"{subject}: access arrangement must be non-empty")
        if not _string_list(access.get("controls")):
            errors.append(f"{subject}: access controls must be non-empty")
    retention = payload.get("retention")
    if not isinstance(retention, Mapping):
        errors.append(f"{subject}: retention must be an object")
    else:
        if retention.get("status") not in RETENTION_STATUSES:
            errors.append(f"{subject}: retention status is invalid")
        if not _non_empty_string(retention.get("statement")):
            errors.append(f"{subject}: retention statement must be non-empty")
    errors.extend(_control_errors(payload.get("security_controls"), subject=subject))
    errors.extend(
        _review_errors(
            payload.get("review"),
            subject=subject,
            expected_basis="hosted_service_boundary_review_of_source",
        )
    )
    return errors


def _load_manifests(directory: Path) -> tuple[dict[str, Path], list[str]]:
    errors: list[str] = []
    manifests: dict[str, Path] = {}
    if not directory.is_dir():
        return {}, [f"manifest directory not found: {directory}"]
    for path in sorted(directory.glob("*.json")):
        if path.stem in manifests:
            errors.append(f"duplicate manifest id: {path.stem}")
        manifests[path.stem] = path
    return manifests, errors


def _read_json(path: Path, *, subject: str) -> tuple[dict[str, Any] | None, str | None]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return None, f"{subject}: cannot read manifest: {exc}"
    if not isinstance(payload, dict):
        return None, f"{subject}: manifest must be an object"
    return payload, None


def validate_privacy_surfaces(clara_root: Path | None = None) -> list[str]:
    root = clara_root or _clara_root()
    workflow_names = _workflow_names(root)
    workflow_paths, errors = _load_manifests(root / "privacy" / "workflows")
    service_paths, service_directory_errors = _load_manifests(
        root / "privacy" / "hosted-services"
    )
    errors.extend(service_directory_errors)
    service_ids = set(service_paths)

    for missing in sorted(workflow_names - workflow_paths.keys()):
        errors.append(f"workflow {missing}: registered skill has no privacy manifest")
    for extra in sorted(workflow_paths.keys() - workflow_names):
        errors.append(f"workflow {extra}: privacy manifest has no registered skill")

    workflows: dict[str, dict[str, Any]] = {}
    services: dict[str, dict[str, Any]] = {}
    for workflow in sorted(workflow_names & workflow_paths.keys()):
        payload, read_error = _read_json(
            workflow_paths[workflow], subject=f"workflow {workflow}"
        )
        if read_error:
            errors.append(read_error)
            continue
        assert payload is not None
        workflows[workflow] = payload
        manifest_errors = _workflow_errors(
            payload,
            workflow=workflow,
            service_ids=service_ids,
        )
        errors.extend(manifest_errors)
        if manifest_errors:
            continue
        try:
            actual = _fingerprint(root, payload["governed_paths"])
        except (OSError, ValueError) as exc:
            errors.append(f"workflow {workflow}: cannot fingerprint source: {exc}")
            continue
        if actual != payload["review"]["source_fingerprint"]:
            errors.append(
                f"workflow {workflow}: privacy review is stale; review source, then --refresh"
            )

    for service_id in sorted(service_paths):
        payload, read_error = _read_json(
            service_paths[service_id], subject=f"hosted service {service_id}"
        )
        if read_error:
            errors.append(read_error)
            continue
        assert payload is not None
        services[service_id] = payload
        manifest_errors = _service_errors(
            payload,
            service_id=service_id,
            workflow_names=workflow_names,
        )
        errors.extend(manifest_errors)
        if manifest_errors:
            continue
        try:
            actual = _fingerprint(root, payload["governed_paths"])
        except (OSError, ValueError) as exc:
            errors.append(
                f"hosted service {service_id}: cannot fingerprint source: {exc}"
            )
            continue
        if actual != payload["review"]["source_fingerprint"]:
            errors.append(
                f"hosted service {service_id}: privacy review is stale; review source, then --refresh"
            )

    for service_id, service in services.items():
        for workflow in service.get("workflows", []):
            workflow_payload = workflows.get(str(workflow))
            if workflow_payload is None:
                continue
            if service_id not in workflow_payload.get("hosted_service_ids", []):
                errors.append(
                    f"hosted service {service_id}: workflow {workflow} does not reference it"
                )
    for workflow, payload in workflows.items():
        for service_id in payload.get("hosted_service_ids", []):
            service = services.get(str(service_id))
            if service is not None and workflow not in service.get("workflows", []):
                errors.append(
                    f"workflow {workflow}: hosted service {service_id} does not link back"
                )
    return errors


def _refresh(identifier: str, clara_root: Path) -> None:
    workflow_path = clara_root / "privacy" / "workflows" / f"{identifier}.json"
    service_path = clara_root / "privacy" / "hosted-services" / f"{identifier}.json"
    matches = [path for path in (workflow_path, service_path) if path.is_file()]
    if not matches:
        raise ValueError(f"unknown workflow or hosted service: {identifier}")
    if len(matches) != 1:
        raise ValueError(f"ambiguous workflow and hosted service id: {identifier}")
    path = matches[0]
    payload = json.loads(path.read_text(encoding="utf-8"))
    payload["review"]["source_fingerprint"] = _fingerprint(
        clara_root, payload["governed_paths"]
    )
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    LOGGER.info("refreshed %s", identifier)


def _refresh_all(clara_root: Path) -> None:
    identifiers = sorted(
        {
            path.stem
            for directory in (
                clara_root / "privacy" / "workflows",
                clara_root / "privacy" / "hosted-services",
            )
            for path in directory.glob("*.json")
        }
    )
    for identifier in identifiers:
        _refresh(identifier, clara_root)


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    parser = argparse.ArgumentParser()
    parser.add_argument("--refresh", metavar="WORKFLOW_OR_SERVICE")
    parser.add_argument("--refresh-all", action="store_true")
    args = parser.parse_args()
    root = _clara_root()
    if args.refresh and args.refresh_all:
        parser.error("choose --refresh or --refresh-all")
    try:
        if args.refresh:
            _refresh(args.refresh, root)
        elif args.refresh_all:
            _refresh_all(root)
    except (OSError, ValueError, KeyError, json.JSONDecodeError) as exc:
        LOGGER.error("ERROR: %s", exc)
        return 1
    errors = validate_privacy_surfaces(root)
    if errors:
        for error in errors:
            LOGGER.error("ERROR: %s", error)
        return 1
    LOGGER.info("Clara privacy surfaces are complete and current.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
