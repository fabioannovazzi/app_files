#!/usr/bin/env python3
"""Validate and seal sanitized browser-process evidence for a remote developer.

The model owns semantic interpretation of the demonstrated process. This module
only enforces mechanically verifiable shape, exact lineage, secret exclusions,
operator transfer review, owner-only files, and hash-locked pack integrity.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import logging
import re
import stat
from collections.abc import Mapping, Sequence
from pathlib import Path, PurePosixPath
from typing import Any
from urllib.parse import urlsplit

from capability_pipeline import (
    canonical_json_bytes,
    sha256_payload,
    validate_capability,
    validate_discovery_record,
)

__all__ = [
    "main",
    "seal_developer_pack",
    "validate_discovery_evidence",
    "verify_developer_pack",
]

LOGGER = logging.getLogger(__name__)

EVIDENCE_SCHEMA = "browser-discovery-evidence/v1"
PACK_LOCK_SCHEMA = "browser-developer-pack-lock/v1"
SAFE_ID = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
SHA256 = re.compile(r"^[a-f0-9]{64}$")
ISO_DATE_TIME = re.compile(r"^[0-9]{4}-[0-9]{2}-[0-9]{2}T.+$")
EMAIL_ADDRESS = re.compile(
    r"(?<![A-Za-z0-9._%+-])[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}(?![A-Za-z0-9.-])"
)

EVIDENCE_KEYS = {
    "schema_version",
    "session_id",
    "recorded_at",
    "mode",
    "site",
    "process",
    "runtime",
    "authority",
    "privacy",
    "prompt_summary",
    "boundary",
    "timeline",
    "branches",
    "visual_evidence",
    "known_limits",
    "discovery_record_sha256",
    "capability_draft_sha256",
    "review",
}
MANDATORY_EXCLUSIONS = {
    "credentials",
    "cookies",
    "browser_storage",
    "session_urls",
    "page_html",
    "unreviewed_screenshots",
    "network_bodies",
    "downloaded_file_bytes",
    "observed_private_values",
    "raw_guided_capture",
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
    "session_url",
    "storage_state",
    "token",
}
ALLOWED_MODES = {"guided", "autonomous", "hybrid"}
ALLOWED_ACTORS = {"operator", "model"}
ALLOWED_IMAGE_SUFFIXES = {".jpeg", ".jpg", ".png", ".webp"}


def _is_sequence(value: Any) -> bool:
    return isinstance(value, Sequence) and not isinstance(value, (str, bytes))


def _non_empty_text(value: Any) -> bool:
    return isinstance(value, str) and bool(value.strip())


def _is_sha256(value: Any) -> bool:
    return isinstance(value, str) and bool(SHA256.fullmatch(value))


def _is_timestamp(value: Any) -> bool:
    return isinstance(value, str) and bool(ISO_DATE_TIME.fullmatch(value))


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


def _validate_site(value: Any, *, errors: list[str]) -> set[str]:
    site = _exact_keys(
        value,
        {"name", "allowed_origins", "start_url"},
        scope="site",
        errors=errors,
    )
    if site is None:
        return set()
    if not _non_empty_text(site.get("name")):
        errors.append("site.name must be non-empty")
    origins = site.get("allowed_origins")
    allowed: set[str] = set()
    if not _is_sequence(origins) or not origins:
        errors.append("site.allowed_origins must be a non-empty array")
    else:
        for index, origin in enumerate(origins):
            normalized = _validate_origin(
                origin, scope=f"site.allowed_origins[{index}]", errors=errors
            )
            if normalized:
                allowed.add(normalized)
    start_url = site.get("start_url")
    if not _non_empty_text(start_url):
        errors.append("site.start_url must be non-empty")
    else:
        parsed = urlsplit(start_url)
        if f"{parsed.scheme}://{parsed.netloc}" not in allowed:
            errors.append("site.start_url must use an allowed origin")
        if parsed.username or parsed.password or parsed.query or parsed.fragment:
            errors.append(
                "site.start_url must not contain credentials, query, or fragment"
            )
    return allowed


def _validate_process(value: Any, *, errors: list[str]) -> None:
    process = _exact_keys(
        value,
        {"name", "objective", "out_of_scope"},
        scope="process",
        errors=errors,
    )
    if process is None:
        return
    for field in ("name", "objective"):
        if not _non_empty_text(process.get(field)):
            errors.append(f"process.{field} must be non-empty")
    exclusions = process.get("out_of_scope")
    if not _is_sequence(exclusions) or not all(
        _non_empty_text(item) for item in exclusions
    ):
        errors.append("process.out_of_scope must contain strings")


def _validate_runtime(value: Any, *, errors: list[str]) -> None:
    runtime = _exact_keys(
        value,
        {
            "browser",
            "controller",
            "semantic_driver",
            "mechanical_driver",
            "os_fallback",
        },
        scope="runtime",
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
    for field, expected_value in expected.items():
        if runtime.get(field) != expected_value:
            errors.append(f"runtime.{field} must be {expected_value!r}")


def _validate_authority(value: Any, *, errors: list[str]) -> None:
    authority = _exact_keys(
        value,
        {
            "operator_authorized",
            "authentication",
            "secret_policy",
            "consequential_actions",
        },
        scope="authority",
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
    for field, expected_value in expected.items():
        if authority.get(field) != expected_value:
            errors.append(f"authority.{field} must be {expected_value!r}")


def _validate_privacy(value: Any, *, errors: list[str]) -> None:
    privacy = _exact_keys(
        value,
        {"model_data", "portable_artifact_excludes", "private_evidence_retained"},
        scope="privacy",
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
        errors.append("privacy.model_data must contain strings")
    exclusions = privacy.get("portable_artifact_excludes")
    if not _is_sequence(exclusions) or not MANDATORY_EXCLUSIONS <= set(exclusions):
        errors.append("privacy.portable_artifact_excludes is incomplete")
    if privacy.get("private_evidence_retained") is not False:
        errors.append("privacy.private_evidence_retained must be false")


def _validate_boundary(value: Any, *, errors: list[str]) -> None:
    boundary = _exact_keys(
        value,
        {
            "start_state",
            "end_condition",
            "input_names",
            "output_names",
            "consequential_action_ids",
        },
        scope="boundary",
        errors=errors,
    )
    if boundary is None:
        return
    for field in ("start_state", "end_condition"):
        if not _non_empty_text(boundary.get(field)):
            errors.append(f"boundary.{field} must be non-empty")
    for field in ("input_names", "output_names", "consequential_action_ids"):
        names = boundary.get(field)
        if not _is_sequence(names) or not all(
            isinstance(name, str) and SAFE_ID.fullmatch(name) for name in names
        ):
            errors.append(f"boundary.{field} must contain lower-case slugs")
        elif len(names) != len(set(names)):
            errors.append(f"boundary.{field} must be unique")


def _validate_state(
    value: Any,
    *,
    scope: str,
    allowed_origins: set[str],
    errors: list[str],
) -> None:
    state = _exact_keys(
        value,
        {"origin", "path", "control_fingerprint"},
        scope=scope,
        errors=errors,
    )
    if state is None:
        return
    origin = _validate_origin(
        state.get("origin"), scope=f"{scope}.origin", errors=errors
    )
    if origin and origin not in allowed_origins:
        errors.append(f"{scope}.origin is outside allowed origins")
    path = state.get("path")
    if (
        not isinstance(path, str)
        or not path.startswith("/")
        or "?" in path
        or "#" in path
    ):
        errors.append(f"{scope}.path must be query-free")
    if not _is_sha256(state.get("control_fingerprint")):
        errors.append(f"{scope}.control_fingerprint must be SHA-256")


def _validate_timeline(
    value: Any,
    *,
    mode: Any,
    allowed_origins: set[str],
    errors: list[str],
) -> None:
    if not _is_sequence(value) or not value:
        errors.append("timeline must be a non-empty array")
        return
    sequences: list[int] = []
    actors: set[str] = set()
    for index, item in enumerate(value):
        scope = f"timeline[{index}]"
        entry = _exact_keys(
            item,
            {
                "sequence",
                "actor",
                "observation_index",
                "milestone_id",
                "action_ids",
                "intent",
                "before",
                "after",
                "state_change",
                "outcome",
                "postcondition",
                "uncertainties",
            },
            scope=scope,
            errors=errors,
        )
        if entry is None:
            continue
        sequence = entry.get("sequence")
        if not isinstance(sequence, int) or sequence < 1:
            errors.append(f"{scope}.sequence must be a positive integer")
        else:
            sequences.append(sequence)
        if entry.get("actor") not in ALLOWED_ACTORS:
            errors.append(f"{scope}.actor is unsupported")
        else:
            actors.add(entry["actor"])
        observation_index = entry.get("observation_index")
        if not isinstance(observation_index, int) or observation_index < 0:
            errors.append(f"{scope}.observation_index must be non-negative")
        milestone_id = entry.get("milestone_id")
        if not isinstance(milestone_id, str) or not SAFE_ID.fullmatch(milestone_id):
            errors.append(f"{scope}.milestone_id must be a lower-case slug")
        action_ids = entry.get("action_ids")
        if (
            not _is_sequence(action_ids)
            or not action_ids
            or not all(
                isinstance(action_id, str) and SAFE_ID.fullmatch(action_id)
                for action_id in action_ids
            )
        ):
            errors.append(f"{scope}.action_ids must contain lower-case slugs")
        elif len(action_ids) != len(set(action_ids)):
            errors.append(f"{scope}.action_ids must be unique")
        for field in ("intent", "state_change", "outcome", "postcondition"):
            if not _non_empty_text(entry.get(field)):
                errors.append(f"{scope}.{field} must be non-empty")
        _validate_state(
            entry.get("before"),
            scope=f"{scope}.before",
            allowed_origins=allowed_origins,
            errors=errors,
        )
        _validate_state(
            entry.get("after"),
            scope=f"{scope}.after",
            allowed_origins=allowed_origins,
            errors=errors,
        )
        uncertainties = entry.get("uncertainties")
        if not _is_sequence(uncertainties) or not all(
            _non_empty_text(item) for item in uncertainties
        ):
            errors.append(f"{scope}.uncertainties must contain strings")
    if sequences and sequences != list(range(1, len(sequences) + 1)):
        errors.append("timeline.sequence must be contiguous and ordered")
    if mode == "guided" and actors - {"operator"}:
        errors.append("guided evidence may contain only operator timeline entries")
    if mode == "autonomous" and actors - {"model"}:
        errors.append("autonomous evidence may contain only model timeline entries")
    if mode == "hybrid" and actors != ALLOWED_ACTORS:
        errors.append(
            "hybrid evidence must contain operator and model timeline entries"
        )


def _safe_visual_path(value: Any) -> PurePosixPath | None:
    if not _non_empty_text(value):
        return None
    path = PurePosixPath(str(value))
    if (
        path.is_absolute()
        or ".." in path.parts
        or not path.parts
        or path.parts[0] != "visual-evidence"
        or path.suffix.lower() not in ALLOWED_IMAGE_SUFFIXES
    ):
        return None
    return path


def _validate_visual_evidence(value: Any, *, errors: list[str]) -> None:
    if not _is_sequence(value):
        errors.append("visual_evidence must be an array")
        return
    paths: list[str] = []
    for index, item in enumerate(value):
        scope = f"visual_evidence[{index}]"
        evidence = _exact_keys(
            item,
            {
                "path",
                "sha256",
                "purpose",
                "operator_selected",
                "reviewed_for_transfer",
                "contains_private_values",
            },
            scope=scope,
            errors=errors,
        )
        if evidence is None:
            continue
        visual_path = _safe_visual_path(evidence.get("path"))
        if visual_path is None:
            errors.append(f"{scope}.path is unsafe or unsupported")
        else:
            paths.append(visual_path.as_posix())
        if not _is_sha256(evidence.get("sha256")):
            errors.append(f"{scope}.sha256 must be SHA-256")
        if not _non_empty_text(evidence.get("purpose")):
            errors.append(f"{scope}.purpose must be non-empty")
        if evidence.get("operator_selected") is not True:
            errors.append(f"{scope}.operator_selected must be true")
        if evidence.get("reviewed_for_transfer") is not True:
            errors.append(f"{scope}.reviewed_for_transfer must be true")
        if evidence.get("contains_private_values") is not False:
            errors.append(f"{scope}.contains_private_values must be false")
    if len(paths) != len(set(paths)):
        errors.append("visual_evidence paths must be unique")


def _validate_review(value: Any, *, errors: list[str]) -> None:
    review = _exact_keys(
        value,
        {
            "operator_reviewed",
            "approved_for_developer_transfer",
            "reviewed_at",
            "approval_id",
        },
        scope="review",
        errors=errors,
    )
    if review is None:
        return
    operator_reviewed = review.get("operator_reviewed")
    approved = review.get("approved_for_developer_transfer")
    if not isinstance(operator_reviewed, bool):
        errors.append("review.operator_reviewed must be boolean")
    if not isinstance(approved, bool):
        errors.append("review.approved_for_developer_transfer must be boolean")
    if approved is True and operator_reviewed is not True:
        errors.append("developer transfer approval requires operator review")
    if approved is True:
        if not _is_timestamp(review.get("reviewed_at")):
            errors.append("approved developer transfer requires review timestamp")
        approval_id = review.get("approval_id")
        if not isinstance(approval_id, str) or not SAFE_ID.fullmatch(approval_id):
            errors.append("approved developer transfer requires approval id")
    elif review.get("reviewed_at") is not None or review.get("approval_id") is not None:
        errors.append("unapproved developer evidence must not claim approval details")


def validate_discovery_evidence(payload: Any) -> list[str]:
    """Return mechanical errors for one sanitized developer-evidence manifest."""

    errors: list[str] = []
    evidence = _exact_keys(payload, EVIDENCE_KEYS, scope="evidence", errors=errors)
    if evidence is None:
        return errors
    _walk_private_material(evidence, scope="evidence", errors=errors)
    if evidence.get("schema_version") != EVIDENCE_SCHEMA:
        errors.append(f"schema_version must be {EVIDENCE_SCHEMA!r}")
    session_id = evidence.get("session_id")
    if not isinstance(session_id, str) or not SAFE_ID.fullmatch(session_id):
        errors.append("session_id must be a lower-case slug")
    if not _is_timestamp(evidence.get("recorded_at")):
        errors.append("recorded_at must be a timestamp")
    if evidence.get("mode") not in ALLOWED_MODES:
        errors.append("mode must be guided, autonomous, or hybrid")
    allowed_origins = _validate_site(evidence.get("site"), errors=errors)
    _validate_process(evidence.get("process"), errors=errors)
    _validate_runtime(evidence.get("runtime"), errors=errors)
    _validate_authority(evidence.get("authority"), errors=errors)
    _validate_privacy(evidence.get("privacy"), errors=errors)
    if not _non_empty_text(evidence.get("prompt_summary")):
        errors.append("prompt_summary must be non-empty")
    _validate_boundary(evidence.get("boundary"), errors=errors)
    _validate_timeline(
        evidence.get("timeline"),
        mode=evidence.get("mode"),
        allowed_origins=allowed_origins,
        errors=errors,
    )
    for field in ("branches", "known_limits"):
        values = evidence.get(field)
        if not _is_sequence(values) or not all(
            _non_empty_text(item) for item in values
        ):
            errors.append(f"{field} must contain strings")
    _validate_visual_evidence(evidence.get("visual_evidence"), errors=errors)
    for field in ("discovery_record_sha256", "capability_draft_sha256"):
        if not _is_sha256(evidence.get(field)):
            errors.append(f"{field} must be SHA-256")
    _validate_review(evidence.get("review"), errors=errors)
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


def _draft_action_ids(draft: Mapping[str, Any]) -> set[str]:
    return {
        action["id"]
        for milestone in draft["milestones"]
        for action in milestone["actions"]
    }


def _draft_consequential_action_ids(draft: Mapping[str, Any]) -> set[str]:
    return {
        action["id"]
        for milestone in draft["milestones"]
        for action in milestone["actions"]
        if action["effect"] == "consequential"
    }


def _cross_link_errors(
    evidence: Mapping[str, Any],
    discovery: Mapping[str, Any],
    draft: Mapping[str, Any],
) -> list[str]:
    errors: list[str] = []
    discovery_hash = sha256_payload(discovery)
    draft_hash = sha256_payload(draft)
    if evidence.get("discovery_record_sha256") != discovery_hash:
        errors.append("evidence discovery hash does not match the supplied record")
    if evidence.get("capability_draft_sha256") != draft_hash:
        errors.append("evidence draft hash does not match the supplied capability")
    if draft.get("status") != "draft":
        errors.append("developer evidence requires a non-executable draft capability")
    provenance = draft.get("provenance")
    if (
        not isinstance(provenance, Mapping)
        or provenance.get("discovery_record_sha256") != discovery_hash
    ):
        errors.append("draft provenance does not match the discovery record")
    for field in ("site", "process", "runtime", "authority"):
        if evidence.get(field) != discovery.get(field):
            errors.append(f"evidence {field} does not match the discovery record")
        if draft.get(field) != discovery.get(field):
            errors.append(f"draft {field} does not match the discovery record")
    if draft.get("privacy") != discovery.get("privacy"):
        errors.append("draft privacy does not match the discovery record")
    boundary = evidence.get("boundary")
    if isinstance(boundary, Mapping):
        expected_inputs = {item["name"] for item in draft.get("inputs", [])}
        expected_outputs = {item["name"] for item in draft.get("outputs", [])}
        if set(boundary.get("input_names", [])) != expected_inputs:
            errors.append("evidence boundary inputs do not match the draft")
        if set(boundary.get("output_names", [])) != expected_outputs:
            errors.append("evidence boundary outputs do not match the draft")
        if set(boundary.get("consequential_action_ids", [])) != (
            _draft_consequential_action_ids(draft)
        ):
            errors.append("evidence consequential actions do not match the draft")
    observations = discovery.get("observations")
    observed_actions: set[str] = set()
    if _is_sequence(observations):
        for index, entry in enumerate(evidence.get("timeline", [])):
            observation_index = entry.get("observation_index")
            if not isinstance(observation_index, int) or observation_index >= len(
                observations
            ):
                errors.append(f"timeline[{index}] observation index is out of range")
                continue
            observation = observations[observation_index]
            if entry.get("milestone_id") != observation.get("milestone_id"):
                errors.append(f"timeline[{index}] milestone does not match observation")
            observed_actions.update(entry.get("action_ids", []))
    if observed_actions != _draft_action_ids(draft):
        errors.append("developer evidence timeline does not cover every draft action")
    return errors


def _visual_files(
    evidence: Mapping[str, Any], evidence_path: Path
) -> list[tuple[PurePosixPath, bytes]]:
    files: list[tuple[PurePosixPath, bytes]] = []
    for item in evidence["visual_evidence"]:
        relative = _safe_visual_path(item["path"])
        if relative is None:
            raise ValueError(f"unsafe visual evidence path: {item['path']}")
        source = evidence_path.parent / relative.as_posix()
        content = source.read_bytes()
        if hashlib.sha256(content).hexdigest() != item["sha256"]:
            raise ValueError(f"visual evidence hash mismatch: {relative}")
        files.append((relative, content))
    return files


def seal_developer_pack(
    evidence_path: Path,
    discovery_path: Path,
    draft_path: Path,
    output_directory: Path,
) -> Path:
    """Seal one operator-reviewed sanitized pack for remote capability development."""

    evidence = _load_json(evidence_path)
    discovery = _load_json(discovery_path)
    draft = _load_json(draft_path)
    _raise_errors(validate_discovery_evidence(evidence))
    _raise_errors(validate_discovery_record(discovery))
    _raise_errors(validate_capability(draft))
    _raise_errors(_cross_link_errors(evidence, discovery, draft))
    review = evidence["review"]
    if review["operator_reviewed"] is not True:
        raise ValueError("developer evidence has not been reviewed by the operator")
    if review["approved_for_developer_transfer"] is not True:
        raise ValueError("developer evidence is not approved for transfer")
    visuals = _visual_files(evidence, evidence_path)
    target = output_directory / evidence["session_id"]
    if target.exists():
        raise FileExistsError(
            f"refusing to overwrite existing developer pack: {target}"
        )
    target.mkdir(parents=True, mode=stat.S_IRWXU)
    target.chmod(stat.S_IRWXU)
    evidence_bytes = canonical_json_bytes(evidence)
    discovery_bytes = canonical_json_bytes(discovery)
    draft_bytes = canonical_json_bytes(draft)
    readme = (
        f"# {draft['process']['name']} developer evidence\n\n"
        f"Discovery mode: `{evidence['mode']}`\n\n"
        f"Draft capability: `{draft['capability_id']}` {draft['version']}\n\n"
        "This reviewed pack supports remote capability development. The included "
        "capability is a non-executable draft. The pack excludes authentication "
        "material, browser state, raw guided capture, observed private values, and "
        "unreviewed screenshots. Capability authoring approval and runtime validation "
        "remain separate gates.\n"
    ).encode("utf-8")
    files: dict[str, bytes] = {
        "discovery-evidence.json": evidence_bytes,
        "browser-discovery.json": discovery_bytes,
        "capability.draft.json": draft_bytes,
        "README.md": readme,
    }
    files.update({relative.as_posix(): content for relative, content in visuals})
    for relative, content in files.items():
        _write_owner_only(target / relative, content)
    lock = {
        "schema_version": PACK_LOCK_SCHEMA,
        "session_id": evidence["session_id"],
        "mode": evidence["mode"],
        "files": {
            relative: hashlib.sha256(content).hexdigest()
            for relative, content in sorted(files.items())
        },
    }
    _write_owner_only(target / "developer-pack.lock.json", canonical_json_bytes(lock))
    return target


def verify_developer_pack(pack_path: Path) -> list[str]:
    """Return exact integrity and lineage errors for one sealed developer pack."""

    errors: list[str] = []
    try:
        evidence = _load_json(pack_path / "discovery-evidence.json")
        discovery = _load_json(pack_path / "browser-discovery.json")
        draft = _load_json(pack_path / "capability.draft.json")
        lock = _load_json(pack_path / "developer-pack.lock.json")
    except (OSError, json.JSONDecodeError) as exc:
        return [str(exc)]
    errors.extend(validate_discovery_evidence(evidence))
    errors.extend(validate_discovery_record(discovery))
    errors.extend(validate_capability(draft))
    if not errors:
        errors.extend(_cross_link_errors(evidence, discovery, draft))
    lock_record = _exact_keys(
        lock,
        {"schema_version", "session_id", "mode", "files"},
        scope="lock",
        errors=errors,
    )
    if lock_record is None:
        return errors
    if lock_record.get("schema_version") != PACK_LOCK_SCHEMA:
        errors.append("developer pack lock schema is unsupported")
    if lock_record.get("session_id") != evidence.get("session_id"):
        errors.append("developer pack lock session id does not match")
    if lock_record.get("mode") != evidence.get("mode"):
        errors.append("developer pack lock mode does not match")
    files = lock_record.get("files")
    if not isinstance(files, Mapping):
        errors.append("developer pack lock files must be an object")
        return errors
    required = {
        "discovery-evidence.json",
        "browser-discovery.json",
        "capability.draft.json",
        "README.md",
    }
    if not required <= set(files):
        errors.append("developer pack lock is missing required files")
    for relative, expected_hash in files.items():
        relative_path = PurePosixPath(str(relative))
        if (
            relative_path.is_absolute()
            or ".." in relative_path.parts
            or relative_path.name == "developer-pack.lock.json"
            or relative_path.as_posix() != str(relative)
        ):
            errors.append(f"developer pack lock path is unsafe: {relative}")
            continue
        if not _is_sha256(expected_hash):
            errors.append(f"developer pack file hash is invalid: {relative}")
            continue
        path = pack_path / relative
        if not path.is_file():
            errors.append(f"developer pack file is missing: {relative}")
            continue
        if hashlib.sha256(path.read_bytes()).hexdigest() != expected_hash:
            errors.append(f"developer pack file hash mismatch: {relative}")
    expected_visuals = {item["path"] for item in evidence.get("visual_evidence", [])}
    if set(files) - required != expected_visuals:
        errors.append("developer pack visual files do not match the evidence manifest")
    expected_paths = set(files) | {"developer-pack.lock.json"}
    actual_paths = {
        path.relative_to(pack_path).as_posix()
        for path in pack_path.rglob("*")
        if path.is_file()
    }
    for unexpected in sorted(actual_paths - expected_paths):
        errors.append(f"developer pack contains unlisted file: {unexpected}")
    return errors


def _write_errors(errors: list[str]) -> int:
    if not errors:
        return 0
    for error in errors:
        LOGGER.error("%s", error)
    return 1


def main(argv: list[str] | None = None) -> int:
    """Run developer-evidence validation, sealing, or verification."""

    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    validate_parser = subparsers.add_parser("validate")
    validate_parser.add_argument("path", type=Path)
    seal_parser = subparsers.add_parser("seal")
    seal_parser.add_argument("--evidence", type=Path, required=True)
    seal_parser.add_argument("--discovery-record", type=Path, required=True)
    seal_parser.add_argument("--capability-draft", type=Path, required=True)
    seal_parser.add_argument("--output-directory", type=Path, required=True)
    verify_parser = subparsers.add_parser("verify")
    verify_parser.add_argument("path", type=Path)
    args = parser.parse_args(argv)
    try:
        if args.command == "validate":
            errors = validate_discovery_evidence(_load_json(args.path))
            if _write_errors(errors):
                return 1
            LOGGER.info("Discovery evidence contract is valid.")
            return 0
        if args.command == "seal":
            target = seal_developer_pack(
                args.evidence,
                args.discovery_record,
                args.capability_draft,
                args.output_directory,
            )
            LOGGER.info("Wrote: %s", target)
            return 0
        errors = verify_developer_pack(args.path)
        if _write_errors(errors):
            return 1
        LOGGER.info("Developer pack is valid: %s", args.path)
        return 0
    except (FileExistsError, OSError, ValueError, json.JSONDecodeError) as exc:
        LOGGER.error("%s", exc)
        return 1


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    raise SystemExit(main())
