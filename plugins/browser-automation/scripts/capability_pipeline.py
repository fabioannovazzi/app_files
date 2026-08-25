#!/usr/bin/env python3
"""Validate, promote, finalize, seal, and verify executable browser capabilities.

The model owns semantic discovery, workflow meaning, locator repair, and the
decision that observed evidence supports a process. This module is deterministic
only where exact contracts are better: schema shape, origin bounds, approval
lineage, execution hashes, receipt linkage, file permissions, and bundle hashes.
"""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
import logging
import math
import re
import stat
from collections.abc import Mapping, Sequence
from pathlib import Path, PurePosixPath
from typing import Any
from urllib.parse import urlsplit

__all__ = [
    "canonical_json_bytes",
    "execution_contract_sha256",
    "finalize_capability",
    "main",
    "promote_capability",
    "seal_capability",
    "validate_capability",
    "validate_discovery_record",
    "validate_recovery_proposals",
    "validate_run_lock",
    "validate_run_receipt",
    "verify_bundle",
]

LOGGER = logging.getLogger(__name__)

CAPABILITY_SCHEMA = "browser-capability/v2"
DISCOVERY_SCHEMA = "browser-discovery/v2"
RECEIPT_SCHEMA = "browser-run-receipt/v1"
RUN_LOCK_SCHEMA = "browser-run-lock/v1"
RECOVERY_RUN_LOCK_SCHEMA = "browser-run-lock/v2"
RECOVERY_PROPOSAL_SCHEMA = "browser-recovery-proposals/v1"
BUNDLE_LOCK_SCHEMA = "browser-capability-lock/v2"
SAFE_ID = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
SEMVER = re.compile(r"^[0-9]+\.[0-9]+\.[0-9]+$")
SHA256 = re.compile(r"^[a-f0-9]{64}$")
ISO_DATE_TIME = re.compile(r"^[0-9]{4}-[0-9]{2}-[0-9]{2}T.+$")
EMAIL_ADDRESS = re.compile(
    r"(?<![A-Za-z0-9._%+-])[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}(?![A-Za-z0-9.-])"
)

CAPABILITY_KEYS = {
    "schema_version",
    "capability_id",
    "version",
    "status",
    "site",
    "process",
    "runtime",
    "authority",
    "inputs",
    "outputs",
    "entry_milestone",
    "milestones",
    "completion",
    "privacy",
    "validation",
    "provenance",
}
DISCOVERY_KEYS = {
    "schema_version",
    "record_id",
    "recorded_at",
    "site",
    "process",
    "runtime",
    "authority",
    "privacy",
    "observations",
    "branches",
    "downloads",
    "review",
}
RECEIPT_KEYS = {
    "schema_version",
    "runtime_version",
    "run_id",
    "capability_id",
    "capability_version",
    "execution_contract_sha256",
    "discovery_record_sha256",
    "started_at",
    "finished_at",
    "result",
    "entry_milestone",
    "completed_milestones",
    "terminal_milestone",
    "action_results",
    "outputs",
    "input_hashes",
    "locator_changes_during_run",
    "private_evidence_retained",
    "environment",
    "error",
}
RUN_LOCK_KEYS = {
    "schema_version",
    "run_id",
    "capability_id",
    "execution_contract_sha256",
    "outputs_sha256",
    "receipt_sha256",
}
RECOVERY_RUN_LOCK_KEYS = RUN_LOCK_KEYS | {"recovery_proposals_sha256"}
RECOVERY_PROPOSAL_KEYS = {
    "schema_version",
    "runtime_version",
    "run_id",
    "capability_id",
    "capability_version",
    "execution_contract_sha256",
    "discovery_record_sha256",
    "proposals",
    "portable",
    "requires_operator_review_before_persistence",
}
RECOVERY_ITEM_KEYS = {
    "sequence",
    "milestone_id",
    "action_id",
    "action_intent",
    "operation",
    "effect",
    "origin",
    "path",
    "original_locator_candidates_sha256",
    "candidate_index",
    "candidate",
    "candidate_sha256",
    "rationale",
    "uncertainty",
    "original_failure",
    "outcome",
    "outcome_error",
    "approved_for_persistence",
}
FORBIDDEN_KEYS = {
    "access_token",
    "authorization",
    "cookie",
    "cookies",
    "credential",
    "credentials",
    "downloaded_bytes",
    "har",
    "html",
    "one_time_code",
    "otp",
    "passcode",
    "password",
    "pin",
    "refresh_token",
    "request_body",
    "response_body",
    "screenshot",
    "screenshots",
    "session_url",
    "storage_state",
    "token",
    "trace",
}
MANDATORY_EXCLUSIONS = {
    "credentials",
    "cookies",
    "browser_storage",
    "session_urls",
    "page_html",
    "screenshots",
    "network_bodies",
    "downloaded_file_bytes",
    "observed_private_values",
}
ALLOWED_STATUS = {"scaffold", "draft", "discovered", "validated_local"}
EXECUTABLE_STATUS = {"discovered", "validated_local"}
ALLOWED_OPERATIONS = {
    "click",
    "download",
    "extract",
    "fill",
    "goto",
    "press",
    "select",
    "set_checked",
    "wait_for",
}
ALLOWED_EFFECTS = {"read_only", "reversible", "consequential"}
ALLOWED_LOCATORS = {"role", "label", "placeholder", "test_id", "text", "css"}
SEMANTIC_LOCATORS = ALLOWED_LOCATORS - {"css"}
CONDITION_KINDS = {
    "always",
    "locator_hidden",
    "locator_text_contains",
    "locator_visible",
    "none",
    "output_count",
    "output_empty",
    "output_nonempty",
    "url_includes",
    "url_path_equals",
}


def _is_sequence(value: Any) -> bool:
    return isinstance(value, Sequence) and not isinstance(value, (str, bytes))


def _non_empty_text(value: Any) -> bool:
    return isinstance(value, str) and bool(value.strip())


def _is_sha256(value: Any) -> bool:
    return isinstance(value, str) and bool(SHA256.fullmatch(value))


def _is_timestamp(value: Any) -> bool:
    return isinstance(value, str) and bool(ISO_DATE_TIME.fullmatch(value))


def _output_count(value: Any) -> int:
    if _is_sequence(value):
        return len(value)
    return 0 if value is None else 1


def _validate_record_value(
    value: Any,
    declaration: Mapping[str, Any],
    *,
    scope: str,
) -> list[str]:
    errors: list[str] = []
    if not isinstance(value, Mapping):
        return [f"{scope} must be an object"]
    fields = {field["name"]: field for field in declaration["fields"]}
    if set(value) != set(fields):
        errors.append(f"{scope} fields do not match the output declaration")
        return errors
    for name, field in fields.items():
        item = value[name]
        field_scope = f"{scope}.{name}"
        if item is None:
            if field["required"]:
                errors.append(f"{field_scope} is required")
            continue
        field_type = field["type"]
        if field_type == "boolean" and not isinstance(item, bool):
            errors.append(f"{field_scope} must be boolean")
        elif field_type == "number" and (
            isinstance(item, bool)
            or not isinstance(item, (int, float))
            or not math.isfinite(item)
        ):
            errors.append(f"{field_scope} must be numeric")
        elif field_type == "date" and (
            not isinstance(item, str) or not re.fullmatch(r"\d{4}-\d{2}-\d{2}", item)
        ):
            errors.append(f"{field_scope} must be an ISO date")
        elif field_type == "text" and not isinstance(item, str):
            errors.append(f"{field_scope} must be text")
    return errors


def _validate_output_value(
    value: Any,
    declaration: Mapping[str, Any],
    *,
    scope: str,
) -> list[str]:
    output_type = declaration["type"]
    if output_type == "record":
        return _validate_record_value(value, declaration, scope=scope)
    if output_type == "record_set":
        if not isinstance(value, list):
            return [f"{scope} must be an array"]
        return [
            error
            for index, record in enumerate(value)
            for error in _validate_record_value(
                record,
                declaration,
                scope=f"{scope}[{index}]",
            )
        ]
    if output_type == "download_set":
        if not isinstance(value, list):
            return [f"{scope} must be an array"]
        errors: list[str] = []
        for index, download in enumerate(value):
            item_scope = f"{scope}[{index}]"
            if not isinstance(download, Mapping) or set(download) != {
                "path",
                "byte_length",
                "sha256",
            }:
                errors.append(
                    f"{item_scope} must contain path, byte_length, and sha256"
                )
                continue
            if not _non_empty_text(download["path"]):
                errors.append(f"{item_scope}.path must be non-empty")
            if (
                not isinstance(download["byte_length"], int)
                or download["byte_length"] < 0
            ):
                errors.append(f"{item_scope}.byte_length must be non-negative")
            if not _is_sha256(download["sha256"]):
                errors.append(f"{item_scope}.sha256 must be a SHA-256")
        return errors
    if output_type == "summary":
        return [] if _non_empty_text(value) else [f"{scope} must be non-empty text"]
    if output_type == "scalar":
        if value is None or isinstance(value, (Mapping, list)):
            return [f"{scope} must be a scalar"]
        if isinstance(value, float) and not math.isfinite(value):
            return [f"{scope} must be finite"]
        return []
    return [f"{scope} has an unsupported output type"]


def _required_output_satisfied(value: Any, output_type: str) -> bool:
    if output_type == "record_set":
        return isinstance(value, list)
    if output_type == "download_set":
        return isinstance(value, list) and bool(value)
    if output_type == "record":
        return isinstance(value, Mapping)
    if output_type == "summary":
        return _non_empty_text(value)
    if output_type == "scalar":
        return value is not None and not isinstance(value, (Mapping, list))
    return False


def _exact_keys(
    value: Any,
    expected: set[str],
    *,
    scope: str,
    errors: list[str],
) -> Mapping[str, Any] | None:
    if not isinstance(value, Mapping):
        errors.append(f"{scope} must be an object")
        return None
    actual = set(value)
    missing = sorted(expected - actual)
    extra = sorted(actual - expected)
    if missing:
        errors.append(f"{scope} is missing: {', '.join(missing)}")
    if extra:
        errors.append(f"{scope} has unsupported fields: {', '.join(extra)}")
    return value


def _walk_private_material(value: Any, *, scope: str, errors: list[str]) -> None:
    if isinstance(value, Mapping):
        for key, nested in value.items():
            normalized = str(key).strip().lower()
            if normalized in FORBIDDEN_KEYS:
                errors.append(f"{scope} contains forbidden field {key!r}")
            _walk_private_material(nested, scope=f"{scope}.{key}", errors=errors)
        return
    if _is_sequence(value):
        for index, nested in enumerate(value):
            _walk_private_material(nested, scope=f"{scope}[{index}]", errors=errors)
        return
    if isinstance(value, str) and EMAIL_ADDRESS.search(value):
        errors.append(f"{scope} contains an email address; use a runtime input")


def canonical_json_bytes(payload: Any) -> bytes:
    """Return deterministic UTF-8 JSON bytes for hashing and artifacts."""

    return (
        json.dumps(
            payload,
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
            allow_nan=False,
        )
        + "\n"
    ).encode("utf-8")


def sha256_payload(payload: Any) -> str:
    """Hash one JSON payload using the portable canonical representation."""

    return hashlib.sha256(canonical_json_bytes(payload)).hexdigest()


def execution_contract_payload(capability: Mapping[str, Any]) -> dict[str, Any]:
    """Return the immutable executable projection, excluding validation claims."""

    projected = copy.deepcopy(dict(capability))
    projected.pop("status", None)
    projected.pop("validation", None)
    return projected


def execution_contract_sha256(capability: Mapping[str, Any]) -> str:
    """Hash the executable projection shared by discovered and validated states."""

    return sha256_payload(execution_contract_payload(capability))


def _validate_origin(value: Any, *, scope: str, errors: list[str]) -> str | None:
    if not _non_empty_text(value):
        errors.append(f"{scope} must be a non-empty origin")
        return None
    parsed = urlsplit(value)
    local_host = parsed.hostname in {"127.0.0.1", "localhost", "::1"}
    if parsed.scheme != "https" and not (parsed.scheme == "http" and local_host):
        errors.append(f"{scope} must use HTTPS, except for loopback development")
    if not parsed.hostname or parsed.username or parsed.password:
        errors.append(f"{scope} must be an origin without embedded credentials")
    if parsed.path not in {"", "/"} or parsed.query or parsed.fragment:
        errors.append(f"{scope} must not contain a path, query, or fragment")
    return (
        f"{parsed.scheme}://{parsed.netloc}"
        if parsed.scheme and parsed.netloc
        else None
    )


def _validate_site(value: Any, *, scope: str, errors: list[str]) -> set[str]:
    site = _exact_keys(
        value,
        {"name", "allowed_origins", "start_url"},
        scope=scope,
        errors=errors,
    )
    if site is None:
        return set()
    if not _non_empty_text(site.get("name")):
        errors.append(f"{scope}.name must be non-empty")
    origins = site.get("allowed_origins")
    normalized_origins: set[str] = set()
    if not _is_sequence(origins) or not origins:
        errors.append(f"{scope}.allowed_origins must be a non-empty array")
    else:
        for index, origin in enumerate(origins):
            normalized = _validate_origin(
                origin,
                scope=f"{scope}.allowed_origins[{index}]",
                errors=errors,
            )
            if normalized:
                normalized_origins.add(normalized)
        if len(normalized_origins) != len(origins):
            errors.append(f"{scope}.allowed_origins must be unique")
    start_url = site.get("start_url")
    if not _non_empty_text(start_url):
        errors.append(f"{scope}.start_url must be non-empty")
    else:
        parsed = urlsplit(start_url)
        start_origin = f"{parsed.scheme}://{parsed.netloc}"
        if start_origin not in normalized_origins:
            errors.append(f"{scope}.start_url must use an allowed origin")
        if parsed.username or parsed.password or parsed.query or parsed.fragment:
            errors.append(
                f"{scope}.start_url must not contain credentials, query, or fragment"
            )
    return normalized_origins


def _validate_process(value: Any, *, scope: str, errors: list[str]) -> None:
    process = _exact_keys(
        value,
        {"name", "objective", "out_of_scope"},
        scope=scope,
        errors=errors,
    )
    if process is None:
        return
    for field in ("name", "objective"):
        if not _non_empty_text(process.get(field)):
            errors.append(f"{scope}.{field} must be non-empty")
    out_of_scope = process.get("out_of_scope")
    if not _is_sequence(out_of_scope) or not all(
        _non_empty_text(item) for item in out_of_scope
    ):
        errors.append(f"{scope}.out_of_scope must contain non-empty strings")


def _validate_runtime(value: Any, *, scope: str, errors: list[str]) -> None:
    runtime = _exact_keys(
        value,
        {
            "browser",
            "controller",
            "semantic_driver",
            "mechanical_driver",
            "os_fallback",
        },
        scope=scope,
        errors=errors,
    )
    if runtime is None:
        return
    expected = {
        "browser": "existing_chrome",
        "controller": "chrome_extension",
        "semantic_driver": "model",
        "mechanical_driver": "playwright",
        "os_fallback": "operator_handoff_on_native_gap",
    }
    for key, expected_value in expected.items():
        if runtime.get(key) != expected_value:
            errors.append(f"{scope}.{key} must be {expected_value!r}")


def _validate_authority(value: Any, *, scope: str, errors: list[str]) -> None:
    authority = _exact_keys(
        value,
        {
            "operator_authorized",
            "authentication",
            "secret_policy",
            "consequential_actions",
        },
        scope=scope,
        errors=errors,
    )
    if authority is None:
        return
    expected = {
        "operator_authorized": True,
        "authentication": "operator_only",
        "secret_policy": "never_request_read_store",
        "consequential_actions": "confirm_at_action_time",
    }
    for key, expected_value in expected.items():
        if authority.get(key) != expected_value:
            errors.append(f"{scope}.{key} must be {expected_value!r}")


def _validate_privacy(value: Any, *, scope: str, errors: list[str]) -> None:
    privacy = _exact_keys(
        value,
        {"model_data", "portable_artifact_excludes", "private_evidence_retained"},
        scope=scope,
        errors=errors,
    )
    if privacy is None:
        return
    model_data = privacy.get("model_data")
    if (
        not _is_sequence(model_data)
        or not model_data
        or not all(_non_empty_text(item) for item in model_data)
    ):
        errors.append(f"{scope}.model_data must contain non-empty strings")
    exclusions = privacy.get("portable_artifact_excludes")
    if not _is_sequence(exclusions):
        errors.append(f"{scope}.portable_artifact_excludes must be an array")
    elif not MANDATORY_EXCLUSIONS <= set(exclusions):
        missing = sorted(MANDATORY_EXCLUSIONS - set(exclusions))
        errors.append(
            f"{scope}.portable_artifact_excludes is missing: {', '.join(missing)}"
        )
    if privacy.get("private_evidence_retained") is not False:
        errors.append(f"{scope}.private_evidence_retained must be false")


def _validate_locator(value: Any, *, scope: str, errors: list[str]) -> str | None:
    locator = _exact_keys(
        value,
        {"kind", "role", "value", "exact"},
        scope=scope,
        errors=errors,
    )
    if locator is None:
        return None
    kind = locator.get("kind")
    if kind not in ALLOWED_LOCATORS:
        errors.append(f"{scope}.kind is unsupported")
        return None
    role = locator.get("role")
    if kind == "role":
        if not _non_empty_text(role):
            errors.append(f"{scope}.role is required for a role locator")
        value_text = locator.get("value")
        if value_text is not None and not _non_empty_text(value_text):
            errors.append(f"{scope}.value must be null or non-empty")
    else:
        if role is not None:
            errors.append(f"{scope}.role must be null outside a role locator")
        if not _non_empty_text(locator.get("value")):
            errors.append(f"{scope}.value must be non-empty")
    if not isinstance(locator.get("exact"), bool):
        errors.append(f"{scope}.exact must be boolean")
    return str(kind)


def _validate_locators(
    value: Any,
    *,
    scope: str,
    errors: list[str],
    required: bool,
    require_semantic: bool = True,
) -> list[str]:
    if not _is_sequence(value):
        errors.append(f"{scope} must be an array")
        return []
    kinds = [
        kind
        for index, locator in enumerate(value)
        if (
            kind := _validate_locator(
                locator,
                scope=f"{scope}[{index}]",
                errors=errors,
            )
        )
    ]
    if required and not kinds:
        errors.append(f"{scope} must contain a locator")
    if require_semantic and kinds and not set(kinds) & SEMANTIC_LOCATORS:
        errors.append(f"{scope} requires at least one semantic locator")
    return kinds


def _validate_inputs(value: Any, *, errors: list[str]) -> dict[str, str]:
    if not _is_sequence(value):
        errors.append("inputs must be an array")
        return {}
    names: list[str] = []
    input_types: dict[str, str] = {}
    for index, item in enumerate(value):
        scope = f"inputs[{index}]"
        entry = _exact_keys(
            item,
            {"name", "type", "required", "sensitivity", "purpose", "enum_values"},
            scope=scope,
            errors=errors,
        )
        if entry is None:
            continue
        name = entry.get("name")
        if not isinstance(name, str) or not SAFE_ID.fullmatch(name):
            errors.append(f"{scope}.name must be a lower-case slug")
        else:
            names.append(name)
        input_type = entry.get("type")
        if input_type not in {"boolean", "date", "enum", "number", "text"}:
            errors.append(f"{scope}.type is unsupported")
        elif isinstance(name, str) and SAFE_ID.fullmatch(name):
            input_types[name] = input_type
        if not isinstance(entry.get("required"), bool):
            errors.append(f"{scope}.required must be boolean")
        if entry.get("sensitivity") not in {
            "non_sensitive",
            "private_runtime_only",
        }:
            errors.append(f"{scope}.sensitivity is unsupported")
        if not _non_empty_text(entry.get("purpose")):
            errors.append(f"{scope}.purpose must be non-empty")
        enum_values = entry.get("enum_values")
        if not _is_sequence(enum_values) or not all(
            _non_empty_text(enum_value) for enum_value in enum_values
        ):
            errors.append(f"{scope}.enum_values must contain strings")
        if input_type == "enum" and not enum_values:
            errors.append(f"{scope}.enum_values must be non-empty for enum")
        if input_type != "enum" and enum_values:
            errors.append(f"{scope}.enum_values must be empty outside enum")
    if len(names) != len(set(names)):
        errors.append("input names must be unique")
    return input_types


def _validate_outputs(
    value: Any, *, errors: list[str]
) -> tuple[dict[str, str], dict[str, set[str]]]:
    if not _is_sequence(value) or not value:
        errors.append("outputs must be a non-empty array")
        return {}, {}
    output_types: dict[str, str] = {}
    output_fields: dict[str, set[str]] = {}
    for index, item in enumerate(value):
        scope = f"outputs[{index}]"
        output = _exact_keys(
            item,
            {
                "name",
                "type",
                "sensitivity",
                "delivery",
                "description",
                "fields",
            },
            scope=scope,
            errors=errors,
        )
        if output is None:
            continue
        name = output.get("name")
        if not isinstance(name, str) or not SAFE_ID.fullmatch(name):
            errors.append(f"{scope}.name must be a lower-case slug")
            continue
        if name in output_types:
            errors.append("output names must be unique")
        output_type = output.get("type")
        if output_type not in {
            "download_set",
            "record",
            "record_set",
            "scalar",
            "summary",
        }:
            errors.append(f"{scope}.type is unsupported")
        else:
            output_types[name] = output_type
        if output.get("sensitivity") not in {"non_sensitive", "private"}:
            errors.append(f"{scope}.sensitivity is unsupported")
        delivery = output.get("delivery")
        if delivery not in {
            "artifact_only",
            "model_and_artifact",
            "model_summary",
        }:
            errors.append(f"{scope}.delivery is unsupported")
        if delivery == "model_summary" and output_type not in {"scalar", "summary"}:
            errors.append(
                f"{scope}.model_summary delivery requires scalar or summary type"
            )
        if output_type == "download_set" and delivery != "artifact_only":
            errors.append(f"{scope}.download_set delivery must be artifact_only")
        if not _non_empty_text(output.get("description")):
            errors.append(f"{scope}.description must be non-empty")
        fields = output.get("fields")
        if not _is_sequence(fields):
            errors.append(f"{scope}.fields must be an array")
            continue
        field_names: list[str] = []
        for field_index, field_value in enumerate(fields):
            field_scope = f"{scope}.fields[{field_index}]"
            field = _exact_keys(
                field_value,
                {"name", "type", "required"},
                scope=field_scope,
                errors=errors,
            )
            if field is None:
                continue
            field_name = field.get("name")
            if not isinstance(field_name, str) or not SAFE_ID.fullmatch(field_name):
                errors.append(f"{field_scope}.name must be a lower-case slug")
            else:
                field_names.append(field_name)
            if field.get("type") not in {"boolean", "date", "number", "text"}:
                errors.append(f"{field_scope}.type is unsupported")
            if not isinstance(field.get("required"), bool):
                errors.append(f"{field_scope}.required must be boolean")
        if len(field_names) != len(set(field_names)):
            errors.append(f"{scope}.field names must be unique")
        if output_type in {"record", "record_set"} and not fields:
            errors.append(f"{scope}.fields must be non-empty for record outputs")
        if output_type not in {"record", "record_set"} and fields:
            errors.append(f"{scope}.fields must be empty for {output_type}")
        output_fields[name] = set(field_names)
    return output_types, output_fields


def _validate_condition(
    value: Any,
    *,
    scope: str,
    errors: list[str],
    output_names: set[str],
    allow_none: bool,
    allow_structural_visible_css: bool = False,
) -> None:
    condition = _exact_keys(
        value,
        {
            "kind",
            "locator_candidates",
            "value",
            "output_ref",
            "comparator",
            "expected",
            "timeout_ms",
        },
        scope=scope,
        errors=errors,
    )
    if condition is None:
        return
    kind = condition.get("kind")
    if kind not in CONDITION_KINDS or (kind == "none" and not allow_none):
        errors.append(f"{scope}.kind is unsupported")
    locator_kind = kind in {
        "locator_hidden",
        "locator_text_contains",
        "locator_visible",
    }
    locator_candidates = condition.get("locator_candidates")
    # Transition-only visible state markers may need a bounded structural CSS
    # selector. Forcing a broad semantic fallback caused Gmail's empty branch
    # to match unrelated rows, while `:visible` mechanically excludes retained
    # hidden results. Interactive action locators keep the semantic requirement.
    structural_visible_css = (
        allow_structural_visible_css
        and kind == "locator_visible"
        and _is_sequence(locator_candidates)
        and bool(locator_candidates)
        and all(
            isinstance(locator, Mapping)
            and locator.get("kind") == "css"
            and isinstance(locator.get("value"), str)
            and ":visible" in locator["value"]
            for locator in locator_candidates
        )
    )
    _validate_locators(
        locator_candidates,
        scope=f"{scope}.locator_candidates",
        errors=errors,
        required=locator_kind,
        require_semantic=not structural_visible_css,
    )
    if not locator_kind and condition.get("locator_candidates"):
        errors.append(f"{scope}.locator_candidates must be empty for {kind}")
    value_required = kind in {
        "locator_text_contains",
        "url_includes",
        "url_path_equals",
    }
    if value_required and not _non_empty_text(condition.get("value")):
        errors.append(f"{scope}.value is required for {kind}")
    if not value_required and condition.get("value") is not None:
        errors.append(f"{scope}.value must be null for {kind}")
    output_required = kind in {"output_count", "output_empty", "output_nonempty"}
    if output_required and condition.get("output_ref") not in output_names:
        errors.append(f"{scope}.output_ref must name a declared output")
    if not output_required and condition.get("output_ref") is not None:
        errors.append(f"{scope}.output_ref must be null for {kind}")
    if kind == "output_count":
        if condition.get("comparator") not in {"eq", "gte", "lte"}:
            errors.append(f"{scope}.comparator is unsupported")
        if (
            not isinstance(condition.get("expected"), int)
            or condition.get("expected") < 0
        ):
            errors.append(f"{scope}.expected must be a non-negative integer")
    else:
        if condition.get("comparator") is not None:
            errors.append(f"{scope}.comparator must be null for {kind}")
        if condition.get("expected") is not None:
            errors.append(f"{scope}.expected must be null for {kind}")
    timeout_ms = condition.get("timeout_ms")
    if not isinstance(timeout_ms, int) or not 1 <= timeout_ms <= 30_000:
        errors.append(f"{scope}.timeout_ms must be between 1 and 30000")


def _validate_extraction(
    value: Any,
    *,
    scope: str,
    errors: list[str],
    input_types: Mapping[str, str],
    output_type: str | None,
    output_fields: set[str],
) -> None:
    extraction = _exact_keys(
        value,
        {
            "mode",
            "fields",
            "max_items",
            "limit_input_ref",
            "empty_allowed",
            "dedupe_by",
        },
        scope=scope,
        errors=errors,
    )
    if extraction is None:
        return
    mode = extraction.get("mode")
    expected_mode = {
        "record": "single",
        "record_set": "list",
        "scalar": "text",
        "summary": "text",
    }.get(output_type)
    if mode not in {"single", "list", "text"}:
        errors.append(f"{scope}.mode is unsupported")
    elif expected_mode is not None and mode != expected_mode:
        errors.append(
            f"{scope}.mode must be {expected_mode!r} for {output_type} output"
        )
    max_items = extraction.get("max_items")
    if not isinstance(max_items, int) or not 1 <= max_items <= 500:
        errors.append(f"{scope}.max_items must be between 1 and 500")
    limit_input_ref = extraction.get("limit_input_ref")
    if limit_input_ref is not None:
        if limit_input_ref not in input_types:
            errors.append(f"{scope}.limit_input_ref must name a declared input")
        elif input_types[limit_input_ref] != "number":
            errors.append(f"{scope}.limit_input_ref must name a number input")
    if not isinstance(extraction.get("empty_allowed"), bool):
        errors.append(f"{scope}.empty_allowed must be boolean")
    fields = extraction.get("fields")
    field_names: list[str] = []
    if not _is_sequence(fields):
        errors.append(f"{scope}.fields must be an array")
    elif mode == "text" and fields:
        errors.append(f"{scope}.fields must be empty for text mode")
    elif mode != "text" and not fields:
        errors.append(f"{scope}.fields must be a non-empty array")
    else:
        for index, field_value in enumerate(fields):
            field_scope = f"{scope}.fields[{index}]"
            field = _exact_keys(
                field_value,
                {"name", "locator_candidates", "read", "required"},
                scope=field_scope,
                errors=errors,
            )
            if field is None:
                continue
            name = field.get("name")
            if name not in output_fields:
                errors.append(f"{field_scope}.name must name an output field")
            elif isinstance(name, str):
                field_names.append(name)
            _validate_locators(
                field.get("locator_candidates"),
                scope=f"{field_scope}.locator_candidates",
                errors=errors,
                required=False,
                require_semantic=False,
            )
            read = _exact_keys(
                field.get("read"),
                {"kind", "attribute"},
                scope=f"{field_scope}.read",
                errors=errors,
            )
            if read is not None:
                read_kind = read.get("kind")
                if read_kind not in {"attribute", "inner_text", "text_content"}:
                    errors.append(f"{field_scope}.read.kind is unsupported")
                if read_kind == "attribute":
                    if not _non_empty_text(read.get("attribute")):
                        errors.append(f"{field_scope}.read.attribute is required")
                elif read.get("attribute") is not None:
                    errors.append(f"{field_scope}.read.attribute must be null")
            if not isinstance(field.get("required"), bool):
                errors.append(f"{field_scope}.required must be boolean")
    if len(field_names) != len(set(field_names)):
        errors.append(f"{scope}.field names must be unique")
    if mode != "text" and set(field_names) != output_fields:
        errors.append(f"{scope}.fields must exactly cover the output fields")
    dedupe_by = extraction.get("dedupe_by")
    if not _is_sequence(dedupe_by) or not all(
        isinstance(name, str) and name in output_fields for name in dedupe_by
    ):
        errors.append(f"{scope}.dedupe_by must contain output field names")
    if mode == "text":
        if max_items != 1:
            errors.append(f"{scope}.max_items must be 1 for text mode")
        if limit_input_ref is not None:
            errors.append(f"{scope}.limit_input_ref must be null for text mode")
        if dedupe_by:
            errors.append(f"{scope}.dedupe_by must be empty for text mode")
    if mode == "single":
        if max_items != 1:
            errors.append(f"{scope}.max_items must be 1 for single mode")
        if limit_input_ref is not None:
            errors.append(f"{scope}.limit_input_ref must be null for single mode")


def _validate_milestones(
    value: Any,
    *,
    status: Any,
    input_types: Mapping[str, str],
    outputs: Mapping[str, str],
    output_fields: Mapping[str, set[str]],
    allowed_origins: set[str],
    errors: list[str],
) -> tuple[list[str], list[str]]:
    if not _is_sequence(value) or not value:
        errors.append("milestones must be a non-empty array")
        return [], []
    milestone_ids: list[str] = []
    action_ids: list[str] = []
    transition_targets: list[str] = []
    for milestone_index, item in enumerate(value):
        scope = f"milestones[{milestone_index}]"
        milestone = _exact_keys(
            item,
            {"id", "intent", "preconditions", "actions", "transitions"},
            scope=scope,
            errors=errors,
        )
        if milestone is None:
            continue
        milestone_id = milestone.get("id")
        if not isinstance(milestone_id, str) or not SAFE_ID.fullmatch(milestone_id):
            errors.append(f"{scope}.id must be a lower-case slug")
        else:
            milestone_ids.append(milestone_id)
        if not _non_empty_text(milestone.get("intent")):
            errors.append(f"{scope}.intent must be non-empty")
        preconditions = milestone.get("preconditions")
        if not _is_sequence(preconditions) or not all(
            _non_empty_text(item) for item in preconditions
        ):
            errors.append(f"{scope}.preconditions must contain strings")
        actions = milestone.get("actions")
        if not _is_sequence(actions):
            errors.append(f"{scope}.actions must be an array")
            actions = []
        if status != "scaffold" and not actions:
            errors.append(f"{scope}.actions must be non-empty outside a scaffold")
        if status == "scaffold" and actions:
            errors.append(f"{scope}.actions must be empty in a scaffold")
        for action_index, action_value in enumerate(actions):
            action_scope = f"{scope}.actions[{action_index}]"
            action = _exact_keys(
                action_value,
                {
                    "id",
                    "intent",
                    "operation",
                    "effect",
                    "confirmation",
                    "locator_candidates",
                    "input_ref",
                    "key",
                    "path",
                    "target_origin",
                    "output_ref",
                    "extract",
                    "postcondition",
                    "timeout_ms",
                },
                scope=action_scope,
                errors=errors,
            )
            if action is None:
                continue
            action_id = action.get("id")
            if not isinstance(action_id, str) or not SAFE_ID.fullmatch(action_id):
                errors.append(f"{action_scope}.id must be a lower-case slug")
            else:
                action_ids.append(action_id)
            if not _non_empty_text(action.get("intent")):
                errors.append(f"{action_scope}.intent must be non-empty")
            operation = action.get("operation")
            if operation not in ALLOWED_OPERATIONS:
                errors.append(f"{action_scope}.operation is unsupported")
            effect = action.get("effect")
            if effect not in ALLOWED_EFFECTS:
                errors.append(f"{action_scope}.effect is unsupported")
            expected_confirmation = (
                "action_time" if effect == "consequential" else "none"
            )
            if action.get("confirmation") != expected_confirmation:
                errors.append(
                    f"{action_scope}.confirmation must be {expected_confirmation!r}"
                )
            _validate_locators(
                action.get("locator_candidates"),
                scope=f"{action_scope}.locator_candidates",
                errors=errors,
                required=operation != "goto",
            )
            if operation == "goto" and action.get("locator_candidates"):
                errors.append(
                    f"{action_scope}.locator_candidates must be empty for goto"
                )
            input_ref = action.get("input_ref")
            if operation in {"fill", "select", "set_checked"}:
                if input_ref not in input_types:
                    errors.append(f"{action_scope}.input_ref must name an input")
            elif input_ref is not None:
                errors.append(f"{action_scope}.input_ref must be null for {operation}")
            key = action.get("key")
            if operation == "press":
                if not _non_empty_text(key):
                    errors.append(f"{action_scope}.key is required for press")
            elif key is not None:
                errors.append(f"{action_scope}.key must be null for {operation}")
            path = action.get("path")
            target_origin = action.get("target_origin")
            if operation == "goto":
                if (
                    not isinstance(path, str)
                    or not path.startswith("/")
                    or "?" in path
                    or "#" in path
                ):
                    errors.append(f"{action_scope}.path must be a query-free path")
                if target_origin not in allowed_origins:
                    errors.append(f"{action_scope}.target_origin must be allowed")
            else:
                if path is not None:
                    errors.append(f"{action_scope}.path must be null for {operation}")
                if target_origin is not None:
                    errors.append(
                        f"{action_scope}.target_origin must be null for {operation}"
                    )
            output_ref = action.get("output_ref")
            if operation in {"download", "extract"}:
                if output_ref not in outputs:
                    errors.append(f"{action_scope}.output_ref must name an output")
            elif output_ref is not None:
                errors.append(f"{action_scope}.output_ref must be null for {operation}")
            extraction = action.get("extract")
            if operation == "extract":
                output_type = outputs.get(output_ref)
                if output_type not in {"record", "record_set", "scalar", "summary"}:
                    errors.append(
                        f"{action_scope}.output_ref must be an extractable output"
                    )
                _validate_extraction(
                    extraction,
                    scope=f"{action_scope}.extract",
                    errors=errors,
                    input_types=input_types,
                    output_type=output_type,
                    output_fields=output_fields.get(str(output_ref), set()),
                )
            elif extraction is not None:
                errors.append(f"{action_scope}.extract must be null for {operation}")
            if operation == "download" and outputs.get(output_ref) != "download_set":
                errors.append(
                    f"{action_scope}.output_ref must be a download_set output"
                )
            _validate_condition(
                action.get("postcondition"),
                scope=f"{action_scope}.postcondition",
                errors=errors,
                output_names=set(outputs),
                allow_none=True,
            )
            timeout_ms = action.get("timeout_ms")
            if not isinstance(timeout_ms, int) or not 1 <= timeout_ms <= 30_000:
                errors.append(f"{action_scope}.timeout_ms must be 1..30000")
        transitions = milestone.get("transitions")
        if not _is_sequence(transitions) or not transitions:
            errors.append(f"{scope}.transitions must be non-empty")
            transitions = []
        for transition_index, transition_value in enumerate(transitions):
            transition_scope = f"{scope}.transitions[{transition_index}]"
            transition = _exact_keys(
                transition_value,
                {"when", "next_milestone", "terminal"},
                scope=transition_scope,
                errors=errors,
            )
            if transition is None:
                continue
            _validate_condition(
                transition.get("when"),
                scope=f"{transition_scope}.when",
                errors=errors,
                output_names=set(outputs),
                allow_none=False,
                allow_structural_visible_css=True,
            )
            terminal = transition.get("terminal")
            if not isinstance(terminal, bool):
                errors.append(f"{transition_scope}.terminal must be boolean")
            next_milestone = transition.get("next_milestone")
            if terminal is True:
                if next_milestone is not None:
                    errors.append(
                        f"{transition_scope}.next_milestone must be null when terminal"
                    )
            elif not isinstance(next_milestone, str) or not SAFE_ID.fullmatch(
                next_milestone
            ):
                errors.append(
                    f"{transition_scope}.next_milestone must be a milestone slug"
                )
            else:
                transition_targets.append(next_milestone)
    if len(milestone_ids) != len(set(milestone_ids)):
        errors.append("milestone ids must be unique")
    if len(action_ids) != len(set(action_ids)):
        errors.append("action ids must be unique")
    for target in transition_targets:
        if target not in milestone_ids:
            errors.append(f"transition target does not exist: {target}")
    return milestone_ids, action_ids


def _validate_completion(
    value: Any,
    *,
    milestone_ids: list[str],
    output_names: set[str],
    errors: list[str],
) -> None:
    completion = _exact_keys(
        value,
        {"terminal_milestones", "required_outputs"},
        scope="completion",
        errors=errors,
    )
    if completion is None:
        return
    terminal = completion.get("terminal_milestones")
    if (
        not _is_sequence(terminal)
        or not terminal
        or not all(item in milestone_ids for item in terminal)
    ):
        errors.append("completion.terminal_milestones must name milestones")
    required_outputs = completion.get("required_outputs")
    if (
        not _is_sequence(required_outputs)
        or not required_outputs
        or not all(item in output_names for item in required_outputs)
    ):
        errors.append("completion.required_outputs must name outputs")


def _validate_execution_graph(
    capability: Mapping[str, Any],
    *,
    status: Any,
    output_types: Mapping[str, str],
    errors: list[str],
) -> None:
    milestones_value = capability.get("milestones")
    completion = capability.get("completion")
    entry = capability.get("entry_milestone")
    if (
        not _is_sequence(milestones_value)
        or not isinstance(completion, Mapping)
        or not isinstance(entry, str)
    ):
        return
    milestones = {
        milestone["id"]: milestone
        for milestone in milestones_value
        if isinstance(milestone, Mapping)
        and isinstance(milestone.get("id"), str)
        and _is_sequence(milestone.get("transitions"))
        and _is_sequence(milestone.get("actions"))
    }
    if entry not in milestones or len(milestones) != len(milestones_value):
        return
    declared_terminals_value = completion.get("terminal_milestones")
    required_outputs_value = completion.get("required_outputs")
    if not _is_sequence(declared_terminals_value) or not _is_sequence(
        required_outputs_value
    ):
        return
    declared_terminals = set(declared_terminals_value)
    adjacency: dict[str, set[str]] = {name: set() for name in milestones}
    actual_terminals: set[str] = set()
    for milestone_id, milestone in milestones.items():
        transitions = milestone["transitions"]
        for index, transition in enumerate(transitions):
            if not isinstance(transition, Mapping):
                continue
            condition = transition.get("when")
            if (
                isinstance(condition, Mapping)
                and condition.get("kind") == "always"
                and index != len(transitions) - 1
            ):
                errors.append(
                    f"milestone {milestone_id} unconditional transition must be last"
                )
            if transition.get("terminal") is True:
                actual_terminals.add(milestone_id)
            else:
                target = transition.get("next_milestone")
                if target in milestones:
                    adjacency[milestone_id].add(target)
    if actual_terminals != declared_terminals:
        errors.append(
            "completion terminal milestones do not match terminal transitions"
        )

    reachable = {entry}
    frontier = [entry]
    while frontier:
        current = frontier.pop()
        for target in adjacency[current] - reachable:
            reachable.add(target)
            frontier.append(target)
    unreachable = sorted(set(milestones) - reachable)
    if unreachable:
        errors.append("unreachable milestones: " + ", ".join(unreachable))

    can_reach_terminal = set(actual_terminals)
    changed = True
    while changed:
        changed = False
        for source, targets in adjacency.items():
            if source not in can_reach_terminal and targets & can_reach_terminal:
                can_reach_terminal.add(source)
                changed = True
    dead_ends = sorted(reachable - can_reach_terminal)
    if dead_ends:
        errors.append("milestones cannot reach a terminal: " + ", ".join(dead_ends))

    if status == "scaffold" or not declared_terminals <= reachable:
        return
    required_outputs = set(required_outputs_value)
    initially_satisfied = {
        name
        for name, output_type in output_types.items()
        if output_type == "record_set"
    }
    produced = {
        milestone_id: {
            action["output_ref"]
            for action in milestone["actions"]
            if isinstance(action, Mapping) and action.get("output_ref") in output_types
        }
        for milestone_id, milestone in milestones.items()
    }
    predecessors: dict[str, set[str]] = {name: set() for name in milestones}
    for source, targets in adjacency.items():
        for target in targets:
            predecessors[target].add(source)
    universe = set(output_types)
    guaranteed_in = {
        name: (set(initially_satisfied) if name == entry else set(universe))
        for name in milestones
    }
    guaranteed_out = {name: guaranteed_in[name] | produced[name] for name in milestones}
    changed = True
    while changed:
        changed = False
        for milestone_id in milestones:
            if milestone_id == entry:
                new_in = set(initially_satisfied)
            else:
                incoming = [guaranteed_out[item] for item in predecessors[milestone_id]]
                new_in = set.intersection(*incoming) if incoming else set(universe)
            new_out = new_in | produced[milestone_id]
            if (
                new_in != guaranteed_in[milestone_id]
                or new_out != guaranteed_out[milestone_id]
            ):
                guaranteed_in[milestone_id] = new_in
                guaranteed_out[milestone_id] = new_out
                changed = True
    for terminal in sorted(declared_terminals):
        missing = sorted(required_outputs - guaranteed_out[terminal])
        if missing:
            errors.append(
                f"terminal {terminal} can finish without required outputs: "
                + ", ".join(missing)
            )


def _validate_provenance(value: Any, *, status: Any, errors: list[str]) -> None:
    provenance = _exact_keys(
        value,
        {
            "source",
            "discovery_record_sha256",
            "discovery_approval_id",
            "discovery_approved_at",
            "portable_bundle_contains_private_evidence",
        },
        scope="provenance",
        errors=errors,
    )
    if provenance is None:
        return
    if provenance.get("portable_bundle_contains_private_evidence") is not False:
        errors.append("portable bundles must not contain private discovery evidence")
    source = provenance.get("source")
    fingerprint = provenance.get("discovery_record_sha256")
    approval_id = provenance.get("discovery_approval_id")
    approved_at = provenance.get("discovery_approved_at")
    if status == "scaffold":
        if source != "developer_scaffold":
            errors.append("a scaffold provenance source must be developer_scaffold")
        if any(value is not None for value in (fingerprint, approval_id, approved_at)):
            errors.append("a scaffold must not claim discovery or approval")
    elif status == "draft":
        if source != "live_discovery_unreviewed":
            errors.append("a draft provenance source must be live_discovery_unreviewed")
        if not _is_sha256(fingerprint):
            errors.append("a draft requires a discovery SHA-256")
        if approval_id is not None or approved_at is not None:
            errors.append("a draft must not claim operator approval")
    else:
        if source != "authorized_live_discovery":
            errors.append("an executable capability requires authorized_live_discovery")
        if not _is_sha256(fingerprint):
            errors.append("an executable capability requires a discovery SHA-256")
        if not isinstance(approval_id, str) or not SAFE_ID.fullmatch(approval_id):
            errors.append("an executable capability requires an approval id")
        if not _is_timestamp(approved_at):
            errors.append("an executable capability requires an approval timestamp")


def _validate_validation(
    value: Any,
    *,
    status: Any,
    capability: Mapping[str, Any],
    errors: list[str],
) -> None:
    validation = _exact_keys(
        value,
        {
            "environment_scope",
            "execution_contract_sha256",
            "receipts",
            "known_limits",
        },
        scope="validation",
        errors=errors,
    )
    if validation is None:
        return
    expected_scope = (
        "existing_chrome_origin_ui" if status == "validated_local" else "not_validated"
    )
    if validation.get("environment_scope") != expected_scope:
        errors.append(f"validation.environment_scope must be {expected_scope!r}")
    known_limits = validation.get("known_limits")
    if not _is_sequence(known_limits) or not all(
        _non_empty_text(item) for item in known_limits
    ):
        errors.append("validation.known_limits must contain strings")
    execution_hash = validation.get("execution_contract_sha256")
    receipts = validation.get("receipts")
    if not _is_sequence(receipts):
        errors.append("validation.receipts must be an array")
        return
    receipt_ids: list[str] = []
    for index, receipt_value in enumerate(receipts):
        scope = f"validation.receipts[{index}]"
        receipt = _exact_keys(
            receipt_value,
            {
                "run_id",
                "receipt_sha256",
                "executed_at",
                "result",
                "environment_fingerprint",
            },
            scope=scope,
            errors=errors,
        )
        if receipt is None:
            continue
        run_id = receipt.get("run_id")
        if not isinstance(run_id, str) or not SAFE_ID.fullmatch(run_id):
            errors.append(f"{scope}.run_id must be a lower-case slug")
        else:
            receipt_ids.append(run_id)
        for field in ("receipt_sha256", "environment_fingerprint"):
            if not _is_sha256(receipt.get(field)):
                errors.append(f"{scope}.{field} must be a SHA-256")
        if not _is_timestamp(receipt.get("executed_at")):
            errors.append(f"{scope}.executed_at must be a timestamp")
        if receipt.get("result") != "passed":
            errors.append(f"{scope}.result must be passed")
    if len(receipt_ids) != len(set(receipt_ids)):
        errors.append("validation receipt run ids must be unique")
    if status == "validated_local":
        expected_hash = execution_contract_sha256(capability)
        if execution_hash != expected_hash:
            errors.append("validation execution hash does not match capability")
        if len(receipts) < 2:
            errors.append("validated_local requires two receipt references")
    else:
        if execution_hash is not None:
            errors.append("unvalidated capability execution hash must be null")
        if receipts:
            errors.append("unvalidated capability must not contain receipts")


def validate_capability(payload: Any) -> list[str]:
    """Return mechanical violations for one executable capability payload."""

    errors: list[str] = []
    capability = _exact_keys(
        payload,
        CAPABILITY_KEYS,
        scope="capability",
        errors=errors,
    )
    if capability is None:
        return errors
    _walk_private_material(capability, scope="capability", errors=errors)
    if capability.get("schema_version") != CAPABILITY_SCHEMA:
        errors.append(f"schema_version must be {CAPABILITY_SCHEMA!r}")
    capability_id = capability.get("capability_id")
    if not isinstance(capability_id, str) or not SAFE_ID.fullmatch(capability_id):
        errors.append("capability_id must be a lower-case slug")
    if not isinstance(capability.get("version"), str) or not SEMVER.fullmatch(
        capability["version"]
    ):
        errors.append("version must use MAJOR.MINOR.PATCH")
    status = capability.get("status")
    if status not in ALLOWED_STATUS:
        errors.append("status is unsupported")
    allowed_origins = _validate_site(
        capability.get("site"), scope="site", errors=errors
    )
    _validate_process(capability.get("process"), scope="process", errors=errors)
    _validate_runtime(capability.get("runtime"), scope="runtime", errors=errors)
    _validate_authority(capability.get("authority"), scope="authority", errors=errors)
    input_types = _validate_inputs(capability.get("inputs"), errors=errors)
    output_types, output_fields = _validate_outputs(
        capability.get("outputs"), errors=errors
    )
    milestone_ids, _ = _validate_milestones(
        capability.get("milestones"),
        status=status,
        input_types=input_types,
        outputs=output_types,
        output_fields=output_fields,
        allowed_origins=allowed_origins,
        errors=errors,
    )
    entry = capability.get("entry_milestone")
    if entry not in milestone_ids:
        errors.append("entry_milestone must name a milestone")
    _validate_completion(
        capability.get("completion"),
        milestone_ids=milestone_ids,
        output_names=set(output_types),
        errors=errors,
    )
    _validate_execution_graph(
        capability,
        status=status,
        output_types=output_types,
        errors=errors,
    )
    if status != "scaffold" and isinstance(capability.get("completion"), Mapping):
        produced_outputs = {
            action.get("output_ref")
            for milestone in capability.get("milestones", [])
            if isinstance(milestone, Mapping)
            for action in milestone.get("actions", [])
            if isinstance(action, Mapping) and action.get("output_ref") is not None
        }
        required_outputs = set(capability["completion"].get("required_outputs", []))
        missing_producers = sorted(required_outputs - produced_outputs)
        if missing_producers:
            errors.append(
                "required outputs have no executable producer: "
                + ", ".join(missing_producers)
            )
    _validate_privacy(capability.get("privacy"), scope="privacy", errors=errors)
    _validate_provenance(capability.get("provenance"), status=status, errors=errors)
    _validate_validation(
        capability.get("validation"),
        status=status,
        capability=capability,
        errors=errors,
    )
    return errors


def _validate_observation(value: Any, *, index: int, errors: list[str]) -> None:
    scope = f"observations[{index}]"
    observation = _exact_keys(
        value,
        {
            "milestone_id",
            "intent",
            "origin",
            "path",
            "controls",
            "action",
            "outcome",
            "uncertainties",
        },
        scope=scope,
        errors=errors,
    )
    if observation is None:
        return
    milestone_id = observation.get("milestone_id")
    if not isinstance(milestone_id, str) or not SAFE_ID.fullmatch(milestone_id):
        errors.append(f"{scope}.milestone_id must be a lower-case slug")
    for field in ("intent", "action", "outcome"):
        if not _non_empty_text(observation.get(field)):
            errors.append(f"{scope}.{field} must be non-empty")
    _validate_origin(observation.get("origin"), scope=f"{scope}.origin", errors=errors)
    path = observation.get("path")
    if (
        not isinstance(path, str)
        or not path.startswith("/")
        or "?" in path
        or "#" in path
    ):
        errors.append(f"{scope}.path must be a query-free path")
    _validate_locators(
        observation.get("controls"),
        scope=f"{scope}.controls",
        errors=errors,
        required=False,
    )
    uncertainties = observation.get("uncertainties")
    if not _is_sequence(uncertainties) or not all(
        _non_empty_text(item) for item in uncertainties
    ):
        errors.append(f"{scope}.uncertainties must contain strings")


def validate_discovery_record(payload: Any) -> list[str]:
    """Return mechanical violations for one private discovery record."""

    errors: list[str] = []
    record = _exact_keys(payload, DISCOVERY_KEYS, scope="discovery", errors=errors)
    if record is None:
        return errors
    _walk_private_material(record, scope="discovery", errors=errors)
    if record.get("schema_version") != DISCOVERY_SCHEMA:
        errors.append(f"schema_version must be {DISCOVERY_SCHEMA!r}")
    record_id = record.get("record_id")
    if not isinstance(record_id, str) or not SAFE_ID.fullmatch(record_id):
        errors.append("record_id must be a lower-case slug")
    if not _is_timestamp(record.get("recorded_at")):
        errors.append("recorded_at must be a timestamp")
    allowed_origins = _validate_site(record.get("site"), scope="site", errors=errors)
    _validate_process(record.get("process"), scope="process", errors=errors)
    _validate_runtime(record.get("runtime"), scope="runtime", errors=errors)
    _validate_authority(record.get("authority"), scope="authority", errors=errors)
    _validate_privacy(record.get("privacy"), scope="privacy", errors=errors)
    observations = record.get("observations")
    if not _is_sequence(observations) or not observations:
        errors.append("observations must be a non-empty array")
    else:
        for index, observation in enumerate(observations):
            before = len(errors)
            _validate_observation(observation, index=index, errors=errors)
            if (
                len(errors) == before
                and observation.get("origin") not in allowed_origins
            ):
                errors.append(
                    f"observations[{index}].origin is outside allowed origins"
                )
    for field in ("branches", "downloads"):
        values = record.get(field)
        if not _is_sequence(values) or not all(
            _non_empty_text(item) for item in values
        ):
            errors.append(f"{field} must contain strings")
    review = _exact_keys(
        record.get("review"),
        {
            "operator_reviewed",
            "approved_for_capability_authoring",
            "reviewed_at",
            "approval_id",
        },
        scope="review",
        errors=errors,
    )
    if review is not None:
        operator_reviewed = review.get("operator_reviewed")
        approved = review.get("approved_for_capability_authoring")
        if not isinstance(operator_reviewed, bool):
            errors.append("review.operator_reviewed must be boolean")
        if not isinstance(approved, bool):
            errors.append("review.approved_for_capability_authoring must be boolean")
        if approved is True and operator_reviewed is not True:
            errors.append("capability authoring approval requires operator review")
        if approved is True:
            if not _is_timestamp(review.get("reviewed_at")):
                errors.append("approved discovery requires review timestamp")
            approval_id = review.get("approval_id")
            if not isinstance(approval_id, str) or not SAFE_ID.fullmatch(approval_id):
                errors.append("approved discovery requires approval id")
        elif (
            review.get("reviewed_at") is not None
            or review.get("approval_id") is not None
        ):
            errors.append("unapproved discovery must not claim approval details")
    return errors


def validate_run_receipt(payload: Any) -> list[str]:
    """Return mechanical violations for a machine-generated run receipt."""

    errors: list[str] = []
    receipt = _exact_keys(payload, RECEIPT_KEYS, scope="receipt", errors=errors)
    if receipt is None:
        return errors
    _walk_private_material(receipt, scope="receipt", errors=errors)
    if receipt.get("schema_version") != RECEIPT_SCHEMA:
        errors.append(f"receipt.schema_version must be {RECEIPT_SCHEMA!r}")
    for field in ("run_id", "capability_id", "entry_milestone"):
        value = receipt.get(field)
        if not isinstance(value, str) or not SAFE_ID.fullmatch(value):
            errors.append(f"receipt.{field} must be a lower-case slug")
    runtime_version = receipt.get("runtime_version")
    if not isinstance(runtime_version, str) or not re.fullmatch(
        r"browser-capability-runtime/[0-9]+", runtime_version
    ):
        errors.append("receipt.runtime_version is unsupported")
    if not isinstance(receipt.get("capability_version"), str) or not SEMVER.fullmatch(
        receipt["capability_version"]
    ):
        errors.append("receipt.capability_version must use MAJOR.MINOR.PATCH")
    for field in ("execution_contract_sha256", "discovery_record_sha256"):
        if not _is_sha256(receipt.get(field)):
            errors.append(f"receipt.{field} must be a SHA-256")
    for field in ("started_at", "finished_at"):
        if not _is_timestamp(receipt.get(field)):
            errors.append(f"receipt.{field} must be a timestamp")
    if receipt.get("result") not in {"passed", "failed"}:
        errors.append("receipt.result must be passed or failed")
    completed = receipt.get("completed_milestones")
    if not _is_sequence(completed) or not all(
        isinstance(item, str) and SAFE_ID.fullmatch(item) for item in completed
    ):
        errors.append("receipt.completed_milestones must contain milestone ids")
    terminal = receipt.get("terminal_milestone")
    if terminal is not None and (
        not isinstance(terminal, str) or not SAFE_ID.fullmatch(terminal)
    ):
        errors.append("receipt.terminal_milestone must be null or a milestone id")
    action_results = receipt.get("action_results")
    if not _is_sequence(action_results):
        errors.append("receipt.action_results must be an array")
    else:
        for index, action_value in enumerate(action_results):
            scope = f"receipt.action_results[{index}]"
            action = _exact_keys(
                action_value,
                {
                    "milestone_id",
                    "action_id",
                    "operation",
                    "result",
                    "started_at",
                    "finished_at",
                    "locator_candidate",
                    "origin",
                    "path",
                    "output_ref",
                    "output_count",
                    "output_sha256",
                    "error",
                },
                scope=scope,
                errors=errors,
            )
            if action is None:
                continue
            for field in ("milestone_id", "action_id"):
                if not isinstance(action.get(field), str) or not SAFE_ID.fullmatch(
                    action[field]
                ):
                    errors.append(f"{scope}.{field} must be an id")
            if action.get("operation") not in ALLOWED_OPERATIONS:
                errors.append(f"{scope}.operation is unsupported")
            if action.get("result") not in {"passed", "failed"}:
                errors.append(f"{scope}.result must be passed or failed")
            for field in ("started_at", "finished_at"):
                if not _is_timestamp(action.get(field)):
                    errors.append(f"{scope}.{field} must be a timestamp")
            locator = action.get("locator_candidate")
            if locator is not None:
                locator_record = _exact_keys(
                    locator,
                    {"index", "kind"},
                    scope=f"{scope}.locator_candidate",
                    errors=errors,
                )
                if locator_record is not None:
                    if (
                        not isinstance(locator_record.get("index"), int)
                        or locator_record["index"] < 0
                    ):
                        errors.append(f"{scope}.locator_candidate.index is invalid")
                    if locator_record.get("kind") not in ALLOWED_LOCATORS:
                        errors.append(f"{scope}.locator_candidate.kind is invalid")
            if action.get("origin") is not None:
                _validate_origin(
                    action["origin"], scope=f"{scope}.origin", errors=errors
                )
            path = action.get("path")
            if path is not None and (
                not isinstance(path, str)
                or not path.startswith("/")
                or "?" in path
                or "#" in path
            ):
                errors.append(f"{scope}.path must be query-free")
            if (
                not isinstance(action.get("output_count"), int)
                or action["output_count"] < 0
            ):
                errors.append(f"{scope}.output_count must be non-negative")
            output_hash = action.get("output_sha256")
            if output_hash is not None and not _is_sha256(output_hash):
                errors.append(f"{scope}.output_sha256 must be null or SHA-256")
            error = action.get("error")
            if error is not None:
                error_record = _exact_keys(
                    error,
                    {"code", "detail_sha256"},
                    scope=f"{scope}.error",
                    errors=errors,
                )
                if error_record is not None:
                    if not _non_empty_text(error_record.get("code")):
                        errors.append(f"{scope}.error.code must be non-empty")
                    if not _is_sha256(error_record.get("detail_sha256")):
                        errors.append(f"{scope}.error.detail_sha256 must be SHA-256")
    if receipt.get("result") == "passed":
        if terminal is None:
            errors.append("passed receipt requires a terminal milestone")
        if not action_results:
            errors.append("passed receipt requires action results")
        elif any(
            isinstance(action, Mapping) and action.get("result") != "passed"
            for action in action_results
        ):
            errors.append("passed receipt must not contain failed actions")
    outputs = receipt.get("outputs")
    if not _is_sequence(outputs) or not outputs:
        errors.append("receipt.outputs must be non-empty")
    else:
        for index, output_value in enumerate(outputs):
            scope = f"receipt.outputs[{index}]"
            output = _exact_keys(
                output_value,
                {
                    "name",
                    "type",
                    "sensitivity",
                    "delivery",
                    "record_count",
                    "sha256",
                    "artifact",
                },
                scope=scope,
                errors=errors,
            )
            if output is None:
                continue
            if not isinstance(output.get("name"), str) or not SAFE_ID.fullmatch(
                output["name"]
            ):
                errors.append(f"{scope}.name must be an id")
            if output.get("type") not in {
                "download_set",
                "record",
                "record_set",
                "scalar",
                "summary",
            }:
                errors.append(f"{scope}.type is unsupported")
            if output.get("sensitivity") not in {"non_sensitive", "private"}:
                errors.append(f"{scope}.sensitivity is unsupported")
            if output.get("delivery") not in {
                "artifact_only",
                "model_and_artifact",
                "model_summary",
            }:
                errors.append(f"{scope}.delivery is unsupported")
            if (
                not isinstance(output.get("record_count"), int)
                or output["record_count"] < 0
            ):
                errors.append(f"{scope}.record_count must be non-negative")
            if not _is_sha256(output.get("sha256")):
                errors.append(f"{scope}.sha256 must be SHA-256")
            if output.get("artifact") != "outputs.json":
                errors.append(f"{scope}.artifact must be outputs.json")
    input_hashes = receipt.get("input_hashes")
    if not isinstance(input_hashes, Mapping) or not all(
        isinstance(name, str) and SAFE_ID.fullmatch(name) and _is_sha256(value)
        for name, value in input_hashes.items()
    ):
        errors.append("receipt.input_hashes must map input ids to SHA-256 values")
    if not isinstance(receipt.get("locator_changes_during_run"), bool):
        errors.append("receipt.locator_changes_during_run must be boolean")
    if receipt.get("private_evidence_retained") is not False:
        errors.append("receipt.private_evidence_retained must be false")
    environment = _exact_keys(
        receipt.get("environment"),
        {"browser", "controller", "origin_ui", "locale"},
        scope="receipt.environment",
        errors=errors,
    )
    if environment is not None:
        if environment.get("browser") != "existing_chrome":
            errors.append("receipt.environment.browser must be existing_chrome")
        if environment.get("controller") != "chrome_extension":
            errors.append("receipt.environment.controller must be chrome_extension")
        for field in ("origin_ui", "locale"):
            if not _non_empty_text(environment.get(field)):
                errors.append(f"receipt.environment.{field} must be non-empty")
    receipt_error = receipt.get("error")
    if receipt.get("result") == "passed" and receipt_error is not None:
        errors.append("passed receipt.error must be null")
    if receipt.get("result") == "failed":
        if not isinstance(receipt_error, Mapping):
            errors.append("failed receipt requires sanitized error metadata")
        else:
            error_record = _exact_keys(
                receipt_error,
                {"code", "detail_sha256"},
                scope="receipt.error",
                errors=errors,
            )
            if error_record is not None:
                if not _non_empty_text(error_record.get("code")):
                    errors.append("receipt.error.code must be non-empty")
                if not _is_sha256(error_record.get("detail_sha256")):
                    errors.append("receipt.error.detail_sha256 must be SHA-256")
    return errors


def validate_recovery_proposals(payload: Any) -> list[str]:
    """Return mechanical errors for owner-only model recovery proposals."""

    errors: list[str] = []
    record = _exact_keys(
        payload,
        RECOVERY_PROPOSAL_KEYS,
        scope="recovery",
        errors=errors,
    )
    if record is None:
        return errors
    _walk_private_material(record, scope="recovery", errors=errors)
    if record.get("schema_version") != RECOVERY_PROPOSAL_SCHEMA:
        errors.append(f"recovery.schema_version must be {RECOVERY_PROPOSAL_SCHEMA!r}")
    runtime_version = record.get("runtime_version")
    if not isinstance(runtime_version, str) or not re.fullmatch(
        r"browser-capability-runtime/[0-9]+", runtime_version
    ):
        errors.append("recovery.runtime_version is unsupported")
    for field in ("run_id", "capability_id"):
        value = record.get(field)
        if not isinstance(value, str) or not SAFE_ID.fullmatch(value):
            errors.append(f"recovery.{field} must be a lower-case slug")
    version = record.get("capability_version")
    if not isinstance(version, str) or not SEMVER.fullmatch(version):
        errors.append("recovery.capability_version must use MAJOR.MINOR.PATCH")
    for field in ("execution_contract_sha256", "discovery_record_sha256"):
        if not _is_sha256(record.get(field)):
            errors.append(f"recovery.{field} must be a SHA-256")
    if record.get("portable") is not False:
        errors.append("recovery.portable must be false")
    if record.get("requires_operator_review_before_persistence") is not True:
        errors.append(
            "recovery.requires_operator_review_before_persistence must be true"
        )
    proposals = record.get("proposals")
    if not _is_sequence(proposals) or not proposals:
        errors.append("recovery.proposals must be a non-empty array")
        return errors
    sequences: list[int] = []
    for index, value in enumerate(proposals):
        scope = f"recovery.proposals[{index}]"
        proposal = _exact_keys(
            value,
            RECOVERY_ITEM_KEYS,
            scope=scope,
            errors=errors,
        )
        if proposal is None:
            continue
        sequence = proposal.get("sequence")
        if not isinstance(sequence, int) or sequence < 1:
            errors.append(f"{scope}.sequence must be a positive integer")
        else:
            sequences.append(sequence)
        for field in ("milestone_id", "action_id"):
            identifier = proposal.get(field)
            if not isinstance(identifier, str) or not SAFE_ID.fullmatch(identifier):
                errors.append(f"{scope}.{field} must be a lower-case slug")
        for field in ("action_intent", "rationale", "uncertainty"):
            text = proposal.get(field)
            if not _non_empty_text(text) or len(text) > 500:
                errors.append(f"{scope}.{field} must be bounded non-empty text")
        if proposal.get("operation") not in ALLOWED_OPERATIONS - {"goto"}:
            errors.append(f"{scope}.operation is not recoverable")
        if proposal.get("effect") not in {"read_only", "reversible"}:
            errors.append(f"{scope}.effect is not recoverable")
        _validate_origin(proposal.get("origin"), scope=f"{scope}.origin", errors=errors)
        path = proposal.get("path")
        if (
            not isinstance(path, str)
            or not path.startswith("/")
            or "?" in path
            or "#" in path
        ):
            errors.append(f"{scope}.path must be query-free")
        for field in (
            "original_locator_candidates_sha256",
            "candidate_sha256",
        ):
            if not _is_sha256(proposal.get(field)):
                errors.append(f"{scope}.{field} must be a SHA-256")
        candidate_index = proposal.get("candidate_index")
        if not isinstance(candidate_index, int) or candidate_index < 0:
            errors.append(f"{scope}.candidate_index must be non-negative")
        candidate_before = len(errors)
        kind = _validate_locator(
            proposal.get("candidate"),
            scope=f"{scope}.candidate",
            errors=errors,
        )
        if kind is not None and kind not in SEMANTIC_LOCATORS:
            errors.append(f"{scope}.candidate must be semantic")
        if len(errors) == candidate_before and proposal.get(
            "candidate_sha256"
        ) != sha256_payload(proposal["candidate"]):
            errors.append(f"{scope}.candidate_sha256 does not match candidate")
        original_failure = _exact_keys(
            proposal.get("original_failure"),
            {"code", "detail_sha256"},
            scope=f"{scope}.original_failure",
            errors=errors,
        )
        if original_failure is not None:
            if original_failure.get("code") != "locator_not_found":
                errors.append(f"{scope}.original_failure.code is unsupported")
            if not _is_sha256(original_failure.get("detail_sha256")):
                errors.append(f"{scope}.original_failure.detail_sha256 must be SHA-256")
        outcome = proposal.get("outcome")
        if outcome not in {"passed", "failed"}:
            errors.append(f"{scope}.outcome must be passed or failed")
        outcome_error = proposal.get("outcome_error")
        if outcome == "passed" and outcome_error is not None:
            errors.append(f"{scope}.passed outcome must not have an error")
        if outcome == "failed":
            failure = _exact_keys(
                outcome_error,
                {"code", "detail_sha256"},
                scope=f"{scope}.outcome_error",
                errors=errors,
            )
            if failure is not None:
                if failure.get("code") != "recovery_failed":
                    errors.append(f"{scope}.outcome_error.code is unsupported")
                if not _is_sha256(failure.get("detail_sha256")):
                    errors.append(
                        f"{scope}.outcome_error.detail_sha256 must be SHA-256"
                    )
        if proposal.get("approved_for_persistence") is not False:
            errors.append(f"{scope}.approved_for_persistence must be false")
    if sequences and sequences != list(range(1, len(sequences) + 1)):
        errors.append("recovery proposal sequence must be contiguous and ordered")
    return errors


def validate_run_lock(payload: Any) -> list[str]:
    """Return mechanical violations for one runtime-generated hash lock."""

    errors: list[str] = []
    schema = payload.get("schema_version") if isinstance(payload, Mapping) else None
    expected_keys = (
        RECOVERY_RUN_LOCK_KEYS if schema == RECOVERY_RUN_LOCK_SCHEMA else RUN_LOCK_KEYS
    )
    lock = _exact_keys(payload, expected_keys, scope="run_lock", errors=errors)
    if lock is None:
        return errors
    if lock.get("schema_version") not in {
        RUN_LOCK_SCHEMA,
        RECOVERY_RUN_LOCK_SCHEMA,
    }:
        errors.append("run_lock.schema_version is unsupported")
    for field in ("run_id", "capability_id"):
        value = lock.get(field)
        if not isinstance(value, str) or not SAFE_ID.fullmatch(value):
            errors.append(f"run_lock.{field} must be a lower-case slug")
    for field in (
        "execution_contract_sha256",
        "outputs_sha256",
        "receipt_sha256",
    ):
        if not _is_sha256(lock.get(field)):
            errors.append(f"run_lock.{field} must be a SHA-256")
    if schema == RECOVERY_RUN_LOCK_SCHEMA and not _is_sha256(
        lock.get("recovery_proposals_sha256")
    ):
        errors.append("run_lock.recovery_proposals_sha256 must be a SHA-256")
    return errors


def _load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _write_owner_only(path: Path, content: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True, mode=stat.S_IRWXU)
    with path.open("xb") as stream:
        stream.write(content)
    path.chmod(stat.S_IRUSR | stat.S_IWUSR)


def _raise_errors(errors: list[str]) -> None:
    if errors:
        raise ValueError("; ".join(errors))


def _approved_discovery(path: Path) -> tuple[dict[str, Any], str]:
    discovery = _load_json(path)
    _raise_errors(validate_discovery_record(discovery))
    review = discovery["review"]
    if review["operator_reviewed"] is not True:
        raise ValueError("discovery record has not been reviewed by the operator")
    if review["approved_for_capability_authoring"] is not True:
        raise ValueError("discovery record is not approved for capability authoring")
    return discovery, sha256_payload(discovery)


def promote_capability(
    draft_path: Path, discovery_path: Path, output_path: Path
) -> Path:
    """Promote a draft only when its exact discovery record is reviewed."""

    draft = _load_json(draft_path)
    _raise_errors(validate_capability(draft))
    if draft["status"] != "draft":
        raise ValueError("only a draft capability may be promoted")
    discovery, discovery_hash = _approved_discovery(discovery_path)
    if draft["provenance"]["discovery_record_sha256"] != discovery_hash:
        raise ValueError("draft discovery hash does not match reviewed record")
    for field in ("site", "process", "runtime", "authority", "privacy"):
        if draft[field] != discovery[field]:
            raise ValueError(
                f"draft {field} does not match the reviewed discovery record"
            )
    observed_milestones = {
        observation["milestone_id"] for observation in discovery["observations"]
    }
    executable_milestones = {
        milestone["id"] for milestone in draft["milestones"] if milestone["actions"]
    }
    missing_observations = sorted(executable_milestones - observed_milestones)
    if missing_observations:
        raise ValueError(
            "reviewed discovery does not cover executable milestones: "
            + ", ".join(missing_observations)
        )
    promoted = copy.deepcopy(draft)
    promoted["status"] = "discovered"
    promoted["provenance"] = {
        "source": "authorized_live_discovery",
        "discovery_record_sha256": discovery_hash,
        "discovery_approval_id": discovery["review"]["approval_id"],
        "discovery_approved_at": discovery["review"]["reviewed_at"],
        "portable_bundle_contains_private_evidence": False,
    }
    _raise_errors(validate_capability(promoted))
    _write_owner_only(output_path, canonical_json_bytes(promoted))
    return output_path


def _verified_receipt(
    path: Path,
    capability: Mapping[str, Any],
    execution_hash: str,
) -> tuple[dict[str, Any], str, dict[str, Any], str]:
    receipt_bytes = path.read_bytes()
    receipt = json.loads(receipt_bytes)
    _raise_errors(validate_run_receipt(receipt))
    if receipt_bytes != canonical_json_bytes(receipt):
        raise ValueError(f"receipt {path} is not canonical runtime output")
    if receipt["result"] != "passed":
        raise ValueError(f"receipt {path} did not pass")
    if receipt["locator_changes_during_run"] is True:
        raise ValueError(
            f"receipt {path} used model recovery and is not a clean validation run"
        )
    if receipt["capability_id"] != capability["capability_id"]:
        raise ValueError(f"receipt {path} capability id does not match")
    if receipt["capability_version"] != capability["version"]:
        raise ValueError(f"receipt {path} capability version does not match")
    if receipt["execution_contract_sha256"] != execution_hash:
        raise ValueError(f"receipt {path} execution hash does not match")
    if (
        receipt["discovery_record_sha256"]
        != capability["provenance"]["discovery_record_sha256"]
    ):
        raise ValueError(f"receipt {path} discovery hash does not match")
    if (
        receipt["terminal_milestone"]
        not in capability["completion"]["terminal_milestones"]
    ):
        raise ValueError(f"receipt {path} did not reach a declared terminal")
    completed = receipt["completed_milestones"]
    if (
        not completed
        or completed[0] != capability["entry_milestone"]
        or completed[-1] != receipt["terminal_milestone"]
    ):
        raise ValueError(f"receipt {path} milestone path is inconsistent")
    milestones = {item["id"]: item for item in capability["milestones"]}
    if any(milestone_id not in milestones for milestone_id in completed):
        raise ValueError(f"receipt {path} contains an unknown milestone")
    for current_id, next_id in zip(completed, completed[1:], strict=False):
        targets = {
            transition["next_milestone"]
            for transition in milestones[current_id]["transitions"]
            if transition["terminal"] is False
        }
        if next_id not in targets:
            raise ValueError(f"receipt {path} milestone transition is not declared")
    expected_actions = [
        (milestone_id, action["id"], action["operation"])
        for milestone_id in completed
        for action in milestones[milestone_id]["actions"]
    ]
    actual_actions = [
        (item["milestone_id"], item["action_id"], item["operation"])
        for item in receipt["action_results"]
    ]
    if actual_actions != expected_actions:
        raise ValueError(f"receipt {path} action sequence does not match capability")
    expected_action_records = [
        action
        for milestone_id in completed
        for action in milestones[milestone_id]["actions"]
    ]
    allowed_origins = set(capability["site"]["allowed_origins"])
    for action_result, action in zip(
        receipt["action_results"], expected_action_records, strict=True
    ):
        if action_result["output_ref"] != action["output_ref"]:
            raise ValueError(f"receipt {path} action output reference does not match")
        if action_result["origin"] not in allowed_origins:
            raise ValueError(f"receipt {path} action origin is outside capability")
        locator = action_result["locator_candidate"]
        if action["operation"] == "goto":
            if locator is not None:
                raise ValueError(f"receipt {path} goto action must not claim a locator")
        else:
            candidates = action["locator_candidates"]
            if locator is None or locator["index"] >= len(candidates):
                raise ValueError(f"receipt {path} action locator is inconsistent")
            if candidates[locator["index"]]["kind"] != locator["kind"]:
                raise ValueError(f"receipt {path} action locator kind does not match")

    outputs_path = path.with_name("outputs.json")
    run_lock_path = path.with_name("run.lock.json")
    try:
        outputs_bytes = outputs_path.read_bytes()
        run_lock_bytes = run_lock_path.read_bytes()
    except OSError as exc:
        raise ValueError(f"receipt {path} is missing linked run evidence") from exc
    outputs = json.loads(outputs_bytes)
    run_lock = json.loads(run_lock_bytes)
    if not isinstance(outputs, Mapping):
        raise ValueError(f"receipt {path} outputs artifact must be an object")
    if outputs_bytes != canonical_json_bytes(outputs):
        raise ValueError(f"receipt {path} outputs artifact is not canonical")
    _raise_errors(validate_run_lock(run_lock))
    if run_lock_bytes != canonical_json_bytes(run_lock):
        raise ValueError(f"receipt {path} run lock is not canonical")
    receipt_hash = hashlib.sha256(receipt_bytes).hexdigest()
    outputs_hash = hashlib.sha256(outputs_bytes).hexdigest()
    if run_lock["run_id"] != receipt["run_id"]:
        raise ValueError(f"receipt {path} run lock id does not match")
    if run_lock["capability_id"] != capability["capability_id"]:
        raise ValueError(f"receipt {path} run lock capability does not match")
    if run_lock["execution_contract_sha256"] != execution_hash:
        raise ValueError(f"receipt {path} run lock execution hash does not match")
    if run_lock["receipt_sha256"] != receipt_hash:
        raise ValueError(f"receipt {path} run lock receipt hash does not match")
    if run_lock["outputs_sha256"] != outputs_hash:
        raise ValueError(f"receipt {path} run lock output hash does not match")

    output_declarations = {item["name"]: item for item in capability["outputs"]}
    declared_output_names = set(output_declarations)
    receipt_outputs = {item["name"]: item for item in receipt["outputs"]}
    if (
        set(receipt_outputs) != declared_output_names
        or set(outputs) != declared_output_names
    ):
        raise ValueError(f"receipt {path} output set does not match capability")
    for name, evidence in receipt_outputs.items():
        value = outputs[name]
        declaration = output_declarations[name]
        for field in ("type", "sensitivity", "delivery"):
            if evidence[field] != declaration[field]:
                raise ValueError(
                    f"receipt {path} output declaration does not match: {name}"
                )
        output_errors = _validate_output_value(
            value,
            declaration,
            scope=f"outputs.{name}",
        )
        if output_errors:
            raise ValueError(f"receipt {path} " + "; ".join(output_errors))
        if evidence["sha256"] != sha256_payload(value):
            raise ValueError(f"receipt {path} output hash does not match: {name}")
        if evidence["record_count"] != _output_count(value):
            raise ValueError(f"receipt {path} output count does not match: {name}")
    for name in capability["completion"]["required_outputs"]:
        if not _required_output_satisfied(
            outputs[name], output_declarations[name]["type"]
        ):
            raise ValueError(f"receipt {path} required output is incomplete: {name}")
    declared_inputs = {item["name"]: item for item in capability["inputs"]}
    input_hashes = receipt["input_hashes"]
    if not set(input_hashes) <= set(declared_inputs):
        raise ValueError(f"receipt {path} contains undeclared input hashes")
    missing_required_inputs = {
        name
        for name, declaration in declared_inputs.items()
        if declaration["required"] and name not in input_hashes
    }
    if missing_required_inputs:
        raise ValueError(f"receipt {path} is missing required input hashes")
    return (
        receipt,
        receipt_hash,
        run_lock,
        hashlib.sha256(run_lock_bytes).hexdigest(),
    )


def finalize_capability(
    capability_path: Path,
    receipt_paths: Sequence[Path],
    output_path: Path,
) -> Path:
    """Create validated_local state from two machine-generated clean receipts."""

    capability = _load_json(capability_path)
    _raise_errors(validate_capability(capability))
    if capability["status"] != "discovered":
        raise ValueError("only a discovered capability may be finalized")
    if len(receipt_paths) < 2:
        raise ValueError("finalization requires at least two receipts")
    execution_hash = execution_contract_sha256(capability)
    receipts = [
        _verified_receipt(path, capability, execution_hash) for path in receipt_paths
    ]
    run_ids = [receipt[0]["run_id"] for receipt in receipts]
    if len(run_ids) != len(set(run_ids)):
        raise ValueError("finalization receipts must have unique run ids")
    environment_hashes = {
        sha256_payload(receipt[0]["environment"]) for receipt in receipts
    }
    if len(environment_hashes) != 1:
        raise ValueError("clean validation receipts must use the same environment")
    runtime_versions = {receipt[0]["runtime_version"] for receipt in receipts}
    if len(runtime_versions) != 1:
        raise ValueError("clean validation receipts must use the same runtime version")
    finalized = copy.deepcopy(capability)
    finalized["status"] = "validated_local"
    finalized["validation"] = {
        "environment_scope": "existing_chrome_origin_ui",
        "execution_contract_sha256": execution_hash,
        "receipts": [
            {
                "run_id": receipt["run_id"],
                "receipt_sha256": receipt_hash,
                "executed_at": receipt["finished_at"],
                "result": receipt["result"],
                "environment_fingerprint": sha256_payload(receipt["environment"]),
            }
            for receipt, receipt_hash, _, _ in receipts
        ],
        "known_limits": capability["validation"]["known_limits"],
    }
    _raise_errors(validate_capability(finalized))
    _write_owner_only(output_path, canonical_json_bytes(finalized))
    return output_path


def seal_capability(
    capability_path: Path,
    output_directory: Path,
    discovery_path: Path,
    receipt_paths: Sequence[Path] = (),
) -> Path:
    """Seal one reviewed executable capability with any required run receipts."""

    capability = _load_json(capability_path)
    _raise_errors(validate_capability(capability))
    if capability["status"] not in EXECUTABLE_STATUS:
        raise ValueError("only discovered or validated capabilities may be sealed")
    discovery, discovery_hash = _approved_discovery(discovery_path)
    provenance = capability["provenance"]
    if provenance["discovery_record_sha256"] != discovery_hash:
        raise ValueError("capability discovery hash does not match reviewed record")
    if provenance["discovery_approval_id"] != discovery["review"]["approval_id"]:
        raise ValueError("capability approval id does not match reviewed record")
    execution_hash = execution_contract_sha256(capability)
    receipt_records: list[tuple[dict[str, Any], str, dict[str, Any], str]] = []
    if capability["status"] == "validated_local":
        if len(receipt_paths) < 2:
            raise ValueError("validated bundle requires its run receipts")
        receipt_records = [
            _verified_receipt(path, capability, execution_hash)
            for path in receipt_paths
        ]
        expected_hashes = {
            item["receipt_sha256"] for item in capability["validation"]["receipts"]
        }
        actual_hashes = {receipt_hash for _, receipt_hash, _, _ in receipt_records}
        if actual_hashes != expected_hashes:
            raise ValueError("provided receipts do not match capability validation")
    elif receipt_paths:
        raise ValueError("discovered bundle must not include validation receipts")
    target = output_directory / capability["capability_id"]
    if target.exists():
        raise FileExistsError(f"refusing to overwrite existing bundle: {target}")
    target.mkdir(parents=True, mode=stat.S_IRWXU)
    target.chmod(stat.S_IRWXU)
    capability_bytes = canonical_json_bytes(capability)
    readme = (
        f"# {capability['process']['name']}\n\n"
        f"Capability: `{capability['capability_id']}` {capability['version']}\n\n"
        f"Status: `{capability['status']}`\n\n"
        "Verify this folder before running it. It contains no browser session, "
        "credentials, observed private values, discovery record, or business output.\n"
    ).encode("utf-8")
    _write_owner_only(target / "capability.json", capability_bytes)
    _write_owner_only(target / "README.md", readme)
    receipt_files: dict[str, str] = {}
    if receipt_records:
        receipts_directory = target / "receipts"
        run_locks_directory = target / "run-locks"
        receipts_directory.mkdir(mode=stat.S_IRWXU)
        run_locks_directory.mkdir(mode=stat.S_IRWXU)
        receipts_directory.chmod(stat.S_IRWXU)
        run_locks_directory.chmod(stat.S_IRWXU)
        for receipt, receipt_hash, run_lock, run_lock_hash in receipt_records:
            name = f"{receipt['run_id']}.json"
            _write_owner_only(receipts_directory / name, canonical_json_bytes(receipt))
            _write_owner_only(
                run_locks_directory / name,
                canonical_json_bytes(run_lock),
            )
            receipt_files[f"receipts/{name}"] = receipt_hash
            receipt_files[f"run-locks/{name}"] = run_lock_hash
    lock = {
        "schema_version": BUNDLE_LOCK_SCHEMA,
        "capability_id": capability["capability_id"],
        "version": capability["version"],
        "status": capability["status"],
        "execution_contract_sha256": execution_hash,
        "files": {
            "capability.json": hashlib.sha256(capability_bytes).hexdigest(),
            "README.md": hashlib.sha256(readme).hexdigest(),
            **receipt_files,
        },
    }
    _write_owner_only(target / "capability.lock.json", canonical_json_bytes(lock))
    return target


def verify_bundle(bundle_path: Path) -> list[str]:
    """Return mechanical integrity errors for a sealed handoff folder."""

    errors: list[str] = []
    try:
        capability = _load_json(bundle_path / "capability.json")
        lock = _load_json(bundle_path / "capability.lock.json")
    except (OSError, json.JSONDecodeError) as exc:
        return [str(exc)]
    errors.extend(validate_capability(capability))
    lock_record = _exact_keys(
        lock,
        {
            "schema_version",
            "capability_id",
            "version",
            "status",
            "execution_contract_sha256",
            "files",
        },
        scope="lock",
        errors=errors,
    )
    if lock_record is None:
        return errors
    if lock_record.get("schema_version") != BUNDLE_LOCK_SCHEMA:
        errors.append("bundle lock schema is unsupported")
    for field in ("capability_id", "version", "status"):
        if lock_record.get(field) != capability.get(field):
            errors.append(f"bundle lock {field} does not match capability")
    if lock_record.get("execution_contract_sha256") != execution_contract_sha256(
        capability
    ):
        errors.append("bundle execution hash does not match capability")
    files = lock_record.get("files")
    if (
        not isinstance(files, Mapping)
        or "capability.json" not in files
        or "README.md" not in files
    ):
        errors.append("bundle lock files are invalid")
        return errors
    bundle_receipts: dict[str, tuple[dict[str, Any], str]] = {}
    bundle_run_locks: dict[str, dict[str, Any]] = {}
    for relative, expected_hash in files.items():
        relative_path = PurePosixPath(str(relative))
        if (
            relative_path.is_absolute()
            or ".." in relative_path.parts
            or str(relative_path) != str(relative)
            or relative_path.name == "capability.lock.json"
        ):
            errors.append(f"bundle lock path is unsafe: {relative}")
            continue
        if not _is_sha256(expected_hash):
            errors.append(f"bundle file hash is invalid: {relative}")
            continue
        path = bundle_path / relative
        if not path.is_file():
            errors.append(f"bundle file is missing: {relative}")
            continue
        actual_hash = hashlib.sha256(path.read_bytes()).hexdigest()
        if actual_hash != expected_hash:
            errors.append(f"bundle file hash mismatch: {relative}")
        if relative.startswith("receipts/"):
            try:
                receipt = _load_json(path)
                errors.extend(validate_run_receipt(receipt))
                if isinstance(receipt, Mapping) and _non_empty_text(
                    receipt.get("run_id")
                ):
                    bundle_receipts[str(receipt["run_id"])] = (
                        dict(receipt),
                        actual_hash,
                    )
            except json.JSONDecodeError:
                errors.append(f"bundle receipt is invalid JSON: {relative}")
        if relative.startswith("run-locks/"):
            try:
                run_lock = _load_json(path)
                errors.extend(validate_run_lock(run_lock))
                if isinstance(run_lock, Mapping) and _non_empty_text(
                    run_lock.get("run_id")
                ):
                    bundle_run_locks[str(run_lock["run_id"])] = dict(run_lock)
            except json.JSONDecodeError:
                errors.append(f"bundle run lock is invalid JSON: {relative}")
    expected_run_ids = {item["run_id"] for item in capability["validation"]["receipts"]}
    if set(bundle_receipts) != expected_run_ids:
        errors.append("bundle receipts do not match capability validation")
    if set(bundle_run_locks) != expected_run_ids:
        errors.append("bundle run locks do not match capability validation")
    for run_id in sorted(
        expected_run_ids & set(bundle_receipts) & set(bundle_run_locks)
    ):
        receipt, receipt_hash = bundle_receipts[run_id]
        run_lock = bundle_run_locks[run_id]
        if run_lock.get("receipt_sha256") != receipt_hash:
            errors.append(f"bundle run lock receipt hash mismatch: {run_id}")
        if run_lock.get("capability_id") != capability.get("capability_id"):
            errors.append(f"bundle run lock capability mismatch: {run_id}")
        if run_lock.get("execution_contract_sha256") != execution_contract_sha256(
            capability
        ):
            errors.append(f"bundle run lock execution hash mismatch: {run_id}")
        if receipt.get("execution_contract_sha256") != run_lock.get(
            "execution_contract_sha256"
        ):
            errors.append(f"bundle receipt and run lock disagree: {run_id}")
    expected_paths = set(files) | {"capability.lock.json"}
    actual_paths = {
        path.relative_to(bundle_path).as_posix()
        for path in bundle_path.rglob("*")
        if path.is_file()
    }
    for unexpected in sorted(actual_paths - expected_paths):
        errors.append(f"bundle contains unlisted file: {unexpected}")
    return errors


def _write_errors(errors: list[str]) -> int:
    if not errors:
        return 0
    for error in errors:
        LOGGER.error("%s", error)
    return 1


def main(argv: list[str] | None = None) -> int:
    """Run the executable capability pipeline CLI."""

    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)

    validate_parser = subparsers.add_parser("validate")
    validate_parser.add_argument("path", type=Path)
    validate_parser.add_argument(
        "--kind",
        choices=(
            "capability",
            "discovery",
            "receipt",
            "recovery-proposals",
            "run-lock",
        ),
        required=True,
    )

    promote_parser = subparsers.add_parser("promote")
    promote_parser.add_argument("path", type=Path)
    promote_parser.add_argument("--discovery-record", type=Path, required=True)
    promote_parser.add_argument("--output", type=Path, required=True)

    finalize_parser = subparsers.add_parser("finalize")
    finalize_parser.add_argument("path", type=Path)
    finalize_parser.add_argument("--receipt", type=Path, action="append", required=True)
    finalize_parser.add_argument("--output", type=Path, required=True)

    seal_parser = subparsers.add_parser("seal")
    seal_parser.add_argument("path", type=Path)
    seal_parser.add_argument("--discovery-record", type=Path, required=True)
    seal_parser.add_argument("--receipt", type=Path, action="append", default=[])
    seal_parser.add_argument("--output-directory", type=Path, required=True)

    verify_parser = subparsers.add_parser("verify-bundle")
    verify_parser.add_argument("path", type=Path)

    args = parser.parse_args(argv)
    try:
        if args.command == "validate":
            payload = _load_json(args.path)
            validators = {
                "capability": validate_capability,
                "discovery": validate_discovery_record,
                "receipt": validate_run_receipt,
                "recovery-proposals": validate_recovery_proposals,
                "run-lock": validate_run_lock,
            }
            errors = validators[args.kind](payload)
            if _write_errors(errors):
                return 1
            LOGGER.info("%s contract is valid.", args.kind.capitalize())
            return 0
        if args.command == "promote":
            target = promote_capability(args.path, args.discovery_record, args.output)
        elif args.command == "finalize":
            target = finalize_capability(args.path, args.receipt, args.output)
        elif args.command == "seal":
            target = seal_capability(
                args.path,
                args.output_directory,
                args.discovery_record,
                args.receipt,
            )
        else:
            errors = verify_bundle(args.path)
            if _write_errors(errors):
                return 1
            LOGGER.info("Bundle is valid: %s", args.path)
            return 0
    except (FileExistsError, OSError, ValueError, json.JSONDecodeError) as exc:
        LOGGER.error("%s", exc)
        return 1
    LOGGER.info("Wrote: %s", target)
    return 0


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    raise SystemExit(main())
