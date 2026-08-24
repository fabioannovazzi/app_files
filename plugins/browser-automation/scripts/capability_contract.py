#!/usr/bin/env python3
"""Validate and seal portable browser discovery and capability records.

The model owns semantic interpretation, workflow decomposition, locator choice,
and recovery.  This module only enforces mechanically verifiable structure,
origin boundaries, secret-exclusion rules, validation receipts, and deterministic
portable bundles.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import logging
import re
import stat
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

__all__ = [
    "canonical_json_bytes",
    "main",
    "seal_capability",
    "validate_capability",
    "validate_discovery_record",
]

LOGGER = logging.getLogger(__name__)

CAPABILITY_SCHEMA = "browser-capability/v1"
DISCOVERY_SCHEMA = "browser-discovery/v1"
SAFE_ID = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
SEMVER = re.compile(r"^[0-9]+\.[0-9]+\.[0-9]+$")
SHA256 = re.compile(r"^[a-f0-9]{64}$")
ISO_DATE = re.compile(r"^[0-9]{4}-[0-9]{2}-[0-9]{2}(?:T.*)?$")
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
ALLOWED_STATUS = {"scaffold", "discovered", "validated_local"}
ALLOWED_OPERATIONS = {
    "click",
    "download",
    "fill",
    "goto",
    "inspect",
    "press",
    "select",
    "wait_for",
}
ALLOWED_EFFECTS = {"read_only", "reversible", "consequential"}
ALLOWED_LOCATORS = {"role", "label", "placeholder", "test_id", "text", "css"}
SEMANTIC_LOCATORS = ALLOWED_LOCATORS - {"css"}
ALLOWED_EVIDENCE = {
    "download",
    "url_path",
    "visible_control",
    "visible_role",
    "visible_text",
}


def _is_sequence(value: Any) -> bool:
    return isinstance(value, Sequence) and not isinstance(value, (str, bytes))


def _non_empty_text(value: Any) -> bool:
    return isinstance(value, str) and bool(value.strip())


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
        errors.append(f"{scope} contains an email address; use an input reference")


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
        "os_fallback": "computer_use_non_browser_only",
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
        if locator.get("value") is not None and not _non_empty_text(
            locator.get("value")
        ):
            errors.append(f"{scope}.value must be null or a non-empty role name")
    else:
        if role is not None:
            errors.append(f"{scope}.role must be null outside a role locator")
        if not _non_empty_text(locator.get("value")):
            errors.append(f"{scope}.value must be non-empty")
    if not isinstance(locator.get("exact"), bool):
        errors.append(f"{scope}.exact must be boolean")
    return str(kind)


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


def _validate_inputs(value: Any, *, errors: list[str]) -> set[str]:
    if not _is_sequence(value):
        errors.append("inputs must be an array")
        return set()
    names: list[str] = []
    for index, item in enumerate(value):
        scope = f"inputs[{index}]"
        input_item = _exact_keys(
            item,
            {"name", "type", "required", "sensitivity", "purpose"},
            scope=scope,
            errors=errors,
        )
        if input_item is None:
            continue
        name = input_item.get("name")
        if not isinstance(name, str) or not SAFE_ID.fullmatch(name):
            errors.append(f"{scope}.name must be a lower-case slug")
        else:
            names.append(name)
        if input_item.get("type") not in {"boolean", "date", "enum", "number", "text"}:
            errors.append(f"{scope}.type is unsupported")
        if not isinstance(input_item.get("required"), bool):
            errors.append(f"{scope}.required must be boolean")
        if input_item.get("sensitivity") not in {
            "non_sensitive",
            "private_runtime_only",
        }:
            errors.append(f"{scope}.sensitivity is unsupported")
        if not _non_empty_text(input_item.get("purpose")):
            errors.append(f"{scope}.purpose must be non-empty")
    if len(names) != len(set(names)):
        errors.append("input names must be unique")
    return set(names)


def _validate_outputs(value: Any, *, errors: list[str]) -> None:
    if not _is_sequence(value) or not value:
        errors.append("outputs must be a non-empty array")
        return
    names: list[str] = []
    for index, item in enumerate(value):
        scope = f"outputs[{index}]"
        output = _exact_keys(
            item,
            {"name", "type", "content"},
            scope=scope,
            errors=errors,
        )
        if output is None:
            continue
        name = output.get("name")
        if not isinstance(name, str) or not SAFE_ID.fullmatch(name):
            errors.append(f"{scope}.name must be a lower-case slug")
        else:
            names.append(name)
        if output.get("type") not in {
            "browser_state",
            "download",
            "local_artifact",
            "summary",
        }:
            errors.append(f"{scope}.type is unsupported")
        if not _non_empty_text(output.get("content")):
            errors.append(f"{scope}.content must be non-empty")
    if len(names) != len(set(names)):
        errors.append("output names must be unique")


def _validate_milestones(
    value: Any,
    *,
    input_names: set[str],
    status: Any,
    errors: list[str],
) -> list[str]:
    if not _is_sequence(value) or not value:
        errors.append("milestones must be a non-empty array")
        return []
    milestone_ids: list[str] = []
    action_ids: list[str] = []
    for milestone_index, item in enumerate(value):
        scope = f"milestones[{milestone_index}]"
        milestone = _exact_keys(
            item,
            {
                "id",
                "intent",
                "preconditions",
                "actions",
                "success_evidence",
                "recovery",
            },
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
        for field in ("preconditions", "recovery"):
            values = milestone.get(field)
            if not _is_sequence(values) or not all(
                _non_empty_text(value) for value in values
            ):
                errors.append(f"{scope}.{field} must contain non-empty strings")
        evidence = milestone.get("success_evidence")
        if not _is_sequence(evidence) or not evidence:
            errors.append(f"{scope}.success_evidence must be non-empty")
        else:
            for evidence_index, evidence_item in enumerate(evidence):
                evidence_scope = f"{scope}.success_evidence[{evidence_index}]"
                evidence_record = _exact_keys(
                    evidence_item,
                    {"kind", "value"},
                    scope=evidence_scope,
                    errors=errors,
                )
                if evidence_record is None:
                    continue
                if evidence_record.get("kind") not in ALLOWED_EVIDENCE:
                    errors.append(f"{evidence_scope}.kind is unsupported")
                if not _non_empty_text(evidence_record.get("value")):
                    errors.append(f"{evidence_scope}.value must be non-empty")
        actions = milestone.get("actions")
        if not _is_sequence(actions):
            errors.append(f"{scope}.actions must be an array")
            continue
        if status != "scaffold" and not actions:
            errors.append(f"{scope}.actions must be non-empty outside a scaffold")
        for action_index, item_action in enumerate(actions):
            action_scope = f"{scope}.actions[{action_index}]"
            action = _exact_keys(
                item_action,
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
            locators = action.get("locator_candidates")
            if not _is_sequence(locators):
                errors.append(f"{action_scope}.locator_candidates must be an array")
                locator_kinds: list[str] = []
            else:
                locator_kinds = [
                    kind
                    for locator_index, locator in enumerate(locators)
                    if (
                        kind := _validate_locator(
                            locator,
                            scope=f"{action_scope}.locator_candidates[{locator_index}]",
                            errors=errors,
                        )
                    )
                ]
            if operation != "goto" and not locator_kinds:
                errors.append(f"{action_scope} requires locator candidates")
            if locator_kinds and not set(locator_kinds) & SEMANTIC_LOCATORS:
                errors.append(f"{action_scope} requires at least one semantic locator")
            input_ref = action.get("input_ref")
            if operation in {"fill", "select"}:
                if input_ref not in input_names:
                    errors.append(
                        f"{action_scope}.input_ref must name a declared input"
                    )
            elif input_ref is not None:
                errors.append(f"{action_scope}.input_ref must be null for {operation}")
            key = action.get("key")
            if operation == "press":
                if not _non_empty_text(key):
                    errors.append(f"{action_scope}.key is required for press")
            elif key is not None:
                errors.append(f"{action_scope}.key must be null for {operation}")
            path = action.get("path")
            if operation == "goto":
                if (
                    not isinstance(path, str)
                    or not path.startswith("/")
                    or "?" in path
                    or "#" in path
                ):
                    errors.append(
                        f"{action_scope}.path must be a query-free absolute path"
                    )
                if locator_kinds:
                    errors.append(
                        f"{action_scope}.locator_candidates must be empty for goto"
                    )
            elif path is not None:
                errors.append(f"{action_scope}.path must be null for {operation}")
    if len(milestone_ids) != len(set(milestone_ids)):
        errors.append("milestone ids must be unique")
    if len(action_ids) != len(set(action_ids)):
        errors.append("action ids must be unique")
    return milestone_ids


def _validate_completion(
    value: Any, *, milestone_ids: list[str], errors: list[str]
) -> None:
    completion = _exact_keys(
        value,
        {"required_milestones", "evidence_to_record"},
        scope="completion",
        errors=errors,
    )
    if completion is None:
        return
    required = completion.get("required_milestones")
    if not _is_sequence(required) or not required:
        errors.append("completion.required_milestones must be non-empty")
    elif list(required) != milestone_ids:
        errors.append("completion.required_milestones must match milestone order")
    evidence = completion.get("evidence_to_record")
    if (
        not _is_sequence(evidence)
        or not evidence
        or not all(_non_empty_text(item) for item in evidence)
    ):
        errors.append("completion.evidence_to_record must contain non-empty strings")


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


def _validate_validation(
    value: Any,
    *,
    status: Any,
    milestone_ids: list[str],
    errors: list[str],
) -> None:
    validation = _exact_keys(
        value,
        {"environment_scope", "runs", "known_limits"},
        scope="validation",
        errors=errors,
    )
    if validation is None:
        return
    environment_scope = validation.get("environment_scope")
    expected_scope = (
        "existing_chrome_origin_ui" if status == "validated_local" else "not_validated"
    )
    if environment_scope != expected_scope:
        errors.append(f"validation.environment_scope must be {expected_scope!r}")
    known_limits = validation.get("known_limits")
    if not _is_sequence(known_limits) or not all(
        _non_empty_text(item) for item in known_limits
    ):
        errors.append("validation.known_limits must contain non-empty strings")
    runs = validation.get("runs")
    if not _is_sequence(runs):
        errors.append("validation.runs must be an array")
        return
    passed_runs = 0
    run_ids: list[str] = []
    for index, item in enumerate(runs):
        scope = f"validation.runs[{index}]"
        run = _exact_keys(
            item,
            {
                "run_id",
                "validated_at",
                "result",
                "start_state",
                "completed_milestones",
                "locator_changes_during_run",
                "private_evidence_retained",
            },
            scope=scope,
            errors=errors,
        )
        if run is None:
            continue
        run_id = run.get("run_id")
        if not isinstance(run_id, str) or not SAFE_ID.fullmatch(run_id):
            errors.append(f"{scope}.run_id must be a lower-case slug")
        else:
            run_ids.append(run_id)
        if not isinstance(run.get("validated_at"), str) or not ISO_DATE.match(
            run["validated_at"]
        ):
            errors.append(f"{scope}.validated_at must start with an ISO date")
        if run.get("result") not in {"passed", "failed"}:
            errors.append(f"{scope}.result must be passed or failed")
        if not _non_empty_text(run.get("start_state")):
            errors.append(f"{scope}.start_state must be non-empty")
        completed = run.get("completed_milestones")
        if not _is_sequence(completed) or not all(
            isinstance(item, str) for item in completed
        ):
            errors.append(f"{scope}.completed_milestones must be strings")
        if not isinstance(run.get("locator_changes_during_run"), bool):
            errors.append(f"{scope}.locator_changes_during_run must be boolean")
        if run.get("private_evidence_retained") is not False:
            errors.append(f"{scope}.private_evidence_retained must be false")
        if (
            run.get("result") == "passed"
            and list(completed) == milestone_ids
            and run.get("locator_changes_during_run") is False
            and run.get("private_evidence_retained") is False
        ):
            passed_runs += 1
    if len(run_ids) != len(set(run_ids)):
        errors.append("validation run ids must be unique")
    if status == "validated_local" and passed_runs < 2:
        errors.append("validated_local requires two clean complete passed runs")
    if status != "validated_local" and runs:
        errors.append("only validated_local capabilities may contain validation runs")


def _validate_provenance(value: Any, *, status: Any, errors: list[str]) -> None:
    provenance = _exact_keys(
        value,
        {
            "source",
            "discovery_record_sha256",
            "portable_bundle_contains_private_evidence",
        },
        scope="provenance",
        errors=errors,
    )
    if provenance is None:
        return
    source = provenance.get("source")
    expected_source = (
        "developer_scaffold" if status == "scaffold" else "authorized_live_discovery"
    )
    if source != expected_source:
        errors.append(f"provenance.source must be {expected_source!r}")
    fingerprint = provenance.get("discovery_record_sha256")
    if status == "scaffold":
        if fingerprint is not None:
            errors.append("a scaffold must not claim a discovery record")
    elif not isinstance(fingerprint, str) or not SHA256.fullmatch(fingerprint):
        errors.append("a discovered capability requires a discovery SHA-256")
    if provenance.get("portable_bundle_contains_private_evidence") is not False:
        errors.append("portable bundles must not contain private discovery evidence")


def validate_capability(payload: Any) -> list[str]:
    """Return mechanical contract violations for one capability payload."""

    errors: list[str] = []
    capability = _exact_keys(
        payload, CAPABILITY_KEYS, scope="capability", errors=errors
    )
    if capability is None:
        return errors
    _walk_private_material(capability, scope="capability", errors=errors)
    if capability.get("schema_version") != CAPABILITY_SCHEMA:
        errors.append(f"schema_version must be {CAPABILITY_SCHEMA!r}")
    capability_id = capability.get("capability_id")
    if not isinstance(capability_id, str) or not SAFE_ID.fullmatch(capability_id):
        errors.append("capability_id must be a lower-case slug")
    version = capability.get("version")
    if not isinstance(version, str) or not SEMVER.fullmatch(version):
        errors.append("version must use MAJOR.MINOR.PATCH")
    status = capability.get("status")
    if status not in ALLOWED_STATUS:
        errors.append("status must be scaffold, discovered, or validated_local")
    _validate_site(capability.get("site"), scope="site", errors=errors)
    _validate_process(capability.get("process"), scope="process", errors=errors)
    _validate_runtime(capability.get("runtime"), scope="runtime", errors=errors)
    _validate_authority(capability.get("authority"), scope="authority", errors=errors)
    input_names = _validate_inputs(capability.get("inputs"), errors=errors)
    _validate_outputs(capability.get("outputs"), errors=errors)
    milestone_ids = _validate_milestones(
        capability.get("milestones"),
        input_names=input_names,
        status=status,
        errors=errors,
    )
    _validate_completion(
        capability.get("completion"), milestone_ids=milestone_ids, errors=errors
    )
    _validate_privacy(capability.get("privacy"), scope="privacy", errors=errors)
    _validate_validation(
        capability.get("validation"),
        status=status,
        milestone_ids=milestone_ids,
        errors=errors,
    )
    _validate_provenance(capability.get("provenance"), status=status, errors=errors)
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
        errors.append(f"{scope}.path must be a query-free absolute path")
    controls = observation.get("controls")
    if not _is_sequence(controls):
        errors.append(f"{scope}.controls must be an array")
    else:
        for locator_index, locator in enumerate(controls):
            _validate_locator(
                locator,
                scope=f"{scope}.controls[{locator_index}]",
                errors=errors,
            )
    uncertainties = observation.get("uncertainties")
    if not _is_sequence(uncertainties) or not all(
        _non_empty_text(item) for item in uncertainties
    ):
        errors.append(f"{scope}.uncertainties must contain non-empty strings")


def validate_discovery_record(payload: Any) -> list[str]:
    """Return mechanical contract violations for one private discovery record."""

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
    recorded_at = record.get("recorded_at")
    if not isinstance(recorded_at, str) or not ISO_DATE.match(recorded_at):
        errors.append("recorded_at must start with an ISO date")
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
            errors.append(f"{field} must contain non-empty strings")
    review = _exact_keys(
        record.get("review"),
        {"operator_reviewed", "approved_for_capability_authoring"},
        scope="review",
        errors=errors,
    )
    if review is not None:
        if not isinstance(review.get("operator_reviewed"), bool):
            errors.append("review.operator_reviewed must be boolean")
        if not isinstance(review.get("approved_for_capability_authoring"), bool):
            errors.append("review.approved_for_capability_authoring must be boolean")
        if (
            review.get("approved_for_capability_authoring") is True
            and review.get("operator_reviewed") is not True
        ):
            errors.append("capability authoring approval requires operator review")
    return errors


def canonical_json_bytes(payload: Any) -> bytes:
    """Return deterministic UTF-8 JSON bytes for hashing and portable output."""

    return (
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    ).encode("utf-8")


def _write_owner_only(path: Path, content: bytes) -> None:
    path.write_bytes(content)
    path.chmod(stat.S_IRUSR | stat.S_IWUSR)


def seal_capability(source: Path, output_directory: Path) -> Path:
    """Validate and write one non-overwriting, owner-only portable bundle."""

    payload = json.loads(source.read_text(encoding="utf-8"))
    errors = validate_capability(payload)
    if errors:
        raise ValueError("; ".join(errors))
    capability_id = str(payload["capability_id"])
    target = output_directory / capability_id
    if target.exists():
        raise FileExistsError(f"refusing to overwrite existing bundle: {target}")
    target.mkdir(parents=True, mode=stat.S_IRWXU)
    capability_bytes = canonical_json_bytes(payload)
    capability_hash = hashlib.sha256(capability_bytes).hexdigest()
    lock = {
        "schema_version": "browser-capability-lock/v1",
        "capability_id": capability_id,
        "version": payload["version"],
        "capability_sha256": capability_hash,
    }
    readme = (
        f"# {payload['process']['name']}\n\n"
        f"Capability: `{capability_id}` {payload['version']}\n\n"
        f"Status: `{payload['status']}`\n\n"
        "Use this folder with Vera Automazione web. It contains no browser "
        "session, credentials, observed private values, or discovery evidence.\n"
    ).encode("utf-8")
    _write_owner_only(target / "capability.json", capability_bytes)
    _write_owner_only(target / "capability.lock.json", canonical_json_bytes(lock))
    _write_owner_only(target / "README.md", readme)
    return target


def _load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def main(argv: list[str] | None = None) -> int:
    """Run the capability contract command line interface."""

    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    validate_parser = subparsers.add_parser("validate")
    validate_parser.add_argument("path", type=Path)
    validate_parser.add_argument(
        "--kind", choices=("capability", "discovery"), required=True
    )
    seal_parser = subparsers.add_parser("seal")
    seal_parser.add_argument("path", type=Path)
    seal_parser.add_argument("--output-directory", type=Path, required=True)
    args = parser.parse_args(argv)

    try:
        if args.command == "validate":
            payload = _load_json(args.path)
            errors = (
                validate_capability(payload)
                if args.kind == "capability"
                else validate_discovery_record(payload)
            )
            if errors:
                for error in errors:
                    LOGGER.error("%s", error)
                return 1
            LOGGER.info("%s contract is valid.", args.kind.capitalize())
            return 0
        target = seal_capability(args.path, args.output_directory)
    except (FileExistsError, OSError, ValueError, json.JSONDecodeError) as exc:
        LOGGER.error("%s", exc)
        return 1
    LOGGER.info("Sealed capability: %s", target)
    return 0


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    raise SystemExit(main())
