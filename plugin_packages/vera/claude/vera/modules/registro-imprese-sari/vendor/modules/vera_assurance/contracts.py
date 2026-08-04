"""Small package-neutral assurance contracts for Vera workflows.

The validators enforce mechanically checkable structure, exact-value closure,
and gate dependencies. They deliberately do not judge source authority,
accounting meaning, evidence sufficiency, materiality, or professional
conclusions.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import stat
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from .money import MoneyValidationError, parse_canonical_decimal
from .serialization import canonical_json_sha256

__all__ = [
    "AssuranceContractError",
    "JOURNAL_SAMPLING_CHECK_ENTRIES_HANDOFF",
    "VERA_CLIENT_WORKFLOW_IDS",
    "build_client_engagement_context",
    "build_gate_register",
    "build_numeric_evidence_ledger",
    "build_source_qualification",
    "build_studio_client_folder_binding",
    "load_client_engagement_context_file",
    "load_client_workflow_context_for_output",
    "validate_client_engagement_context",
    "validate_client_workflow_run",
    "validate_gate_register",
    "validate_numeric_evidence_ledger",
    "validate_source_qualification",
    "validate_studio_client_folder_binding",
]

_IDENTIFIER_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")
_QUALIFICATION_STATUSES = {
    "qualified",
    "needs_review",
    "unsupported_source_layout",
}
_CONTROL_STATUSES = {"passed", "failed", "not_assessed"}
_GATE_NAMES = (
    "source",
    "preparation",
    "reconciliation",
    "semantic_review",
    "reporting",
    "publication",
)
_GATE_STATUSES = {
    "passed",
    "failed",
    "blocked",
    "not_assessed",
    "not_applicable",
    "withheld",
}
_DEFAULT_GATE_DEPENDENCIES = {
    "preparation": ("source",),
    "reconciliation": ("preparation",),
    "semantic_review": ("preparation",),
    "reporting": ("reconciliation", "semantic_review"),
    "publication": ("reporting",),
}
_STUDIO_CLIENT_ID_RE = re.compile(r"^client_[0-9a-f]{24}$")
_STUDIO_SCOPE_ID_RE = re.compile(r"^scope_[0-9a-f]{24}$")
_ENGAGEMENT_ID_RE = re.compile(r"^eng_[0-9a-f]{24}$")
_RUN_ID_RE = re.compile(r"^run_[0-9a-f]{24}$")
_RUN_MANIFEST_FIELDS = {
    "schema_version",
    "client_id",
    "engagement_id",
    "workflow_id",
    "workflow_version",
    "run_id",
    "label",
    "purpose",
    "idempotency_key",
    "input_manifest",
    "input_manifest_sha256",
    "context",
    "created_at",
    "status",
    "updated_at",
    "failure",
    "status_history",
    "static_sha256",
}
_RUN_STATIC_KEYS = (
    "schema_version",
    "client_id",
    "engagement_id",
    "workflow_id",
    "workflow_version",
    "run_id",
    "label",
    "purpose",
    "idempotency_key",
    "input_manifest",
    "input_manifest_sha256",
    "context",
    "created_at",
)
_RUN_TRANSITIONS = {
    "prepared": {"running", "failed", "cancelled"},
    "running": {"ready_for_review", "failed", "cancelled"},
    "ready_for_review": {"running", "completed", "failed", "cancelled"},
    "failed": {"running", "cancelled"},
    "completed": set(),
    "cancelled": set(),
}

# Studio Archive owns the durable client/engagement/run boundary for every
# executable Vera workflow. Studio Archive itself owns (rather than consumes)
# this boundary. Client File Preparation remains a subordinate New Client
# engine at the product layer, but receives its own run folder because it emits
# an independently reviewed package that New Client consumes.
VERA_CLIENT_WORKFLOW_IDS = (
    "audit-reconciliation",
    "client-file-preparation",
    "new-client",
    "journal-sampling",
    "check-entries",
    "journal-bank-reconciliation",
    "sales-plan",
    "financial-analysis",
    "report-builder",
    "concordato-plan-review",
    "prompt-optimizer",
    "deep-research-validator",
    "previdenza-inps",
    "registro-imprese-sari",
)

# This is an exact file-contract handoff, so fixed rules provide mechanically
# verifiable correctness and prevent the producing and consuming workflows from
# drifting.  They do not decide whether the sample or support is sufficient.
JOURNAL_SAMPLING_CHECK_ENTRIES_HANDOFF = (
    (
        "normalization/normalized_journal.csv",
        "prepared.normalized_journal",
        "journal_normalization",
    ),
    (
        "normalization/normalization_diagnostics.json",
        "internal.normalization_diagnostics",
        "journal_normalization",
    ),
    (
        "normalization/normalization_recipe.json",
        None,
        "journal_normalization",
    ),
    (
        "normalization/suggested_recipe.json",
        None,
        "journal_normalization",
    ),
    (
        "normalization/reviewed_decisions.json",
        None,
        "journal_normalization",
    ),
    (
        "normalization/assurance_gates.json",
        None,
        "journal_normalization",
    ),
    (
        "normalization/assurance_envelope.json",
        None,
        "journal_normalization",
    ),
    (
        "normalization/qualification_review_payload.json",
        None,
        "journal_normalization",
    ),
    (
        "sample/journal_sample.csv",
        "prepared.journal_sample_csv",
        "journal_sample",
    ),
)


class AssuranceContractError(ValueError):
    """Raised when a Vera assurance contract is internally inconsistent."""


def _mapping(value: object, *, label: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise AssuranceContractError(f"{label} must be an object")
    return value


def _sequence(value: object, *, label: str) -> list[Any]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes, bytearray)):
        raise AssuranceContractError(f"{label} must be a list")
    return list(value)


def _text(value: object, *, label: str, allow_empty: bool = False) -> str:
    if not isinstance(value, str) or value != value.strip():
        raise AssuranceContractError(f"{label} must be trimmed text")
    if not value and not allow_empty:
        raise AssuranceContractError(f"{label} must be non-empty")
    return value


def _identifier(value: object, *, label: str) -> str:
    text = _text(value, label=label)
    if _IDENTIFIER_RE.fullmatch(text) is None:
        raise AssuranceContractError(f"{label} must be a canonical identifier")
    return text


def _bounded_identifier(value: object, *, label: str, maximum: int = 120) -> str:
    text = _identifier(value, label=label)
    if len(text) > maximum:
        raise AssuranceContractError(
            f"{label} must contain at most {maximum} characters"
        )
    return text


def _non_negative_int(value: object, *, label: str) -> int:
    if not isinstance(value, int) or isinstance(value, bool) or value < 0:
        raise AssuranceContractError(f"{label} must be a non-negative integer")
    return value


def _exact_fields(
    value: Mapping[str, Any],
    *,
    required: set[str],
    optional: set[str] | None = None,
    label: str,
) -> None:
    optional = optional or set()
    missing = required - set(value)
    unexpected = set(value) - required - optional
    if missing or unexpected:
        raise AssuranceContractError(
            f"{label} fields invalid; missing={sorted(missing)}, "
            f"unexpected={sorted(unexpected)}"
        )


def _absolute_path(value: object, *, label: str) -> str:
    text = _text(value, label=label)
    path = Path(text)
    if (
        not path.is_absolute()
        or str(path) != text
        or any(part in {".", ".."} for part in path.parts)
    ):
        raise AssuranceContractError(f"{label} must be a normalized absolute path")
    return str(path)


def _relative_scope_path(value: object) -> str:
    text = _text(value, label="scope_relative_dir")
    if text == ".":
        raise AssuranceContractError(
            "studio client folders must be immediate child scopes"
        )
    path = Path(text)
    if (
        path.is_absolute()
        or path.as_posix() != text
        or any(part in {"", ".", ".."} for part in path.parts)
    ):
        raise AssuranceContractError(
            "scope_relative_dir must be a normalized relative path"
        )
    return text


def _path_is_within(path: str, parent: str) -> bool:
    try:
        Path(path).relative_to(Path(parent))
    except ValueError:
        return False
    return True


def validate_studio_client_folder_binding(value: object) -> dict[str, Any]:
    """Validate one exact Studio Archive scope as a portable client folder."""

    payload = _mapping(value, label="studio client folder binding")
    _exact_fields(
        payload,
        required={
            "schema_version",
            "studio_client_id",
            "scope_id",
            "archive_root",
            "scope_relative_dir",
            "client_root",
            "display_name",
            "content_sha256",
        },
        label="studio client folder binding",
    )
    if payload["schema_version"] != "vera.studio_client_folder.v2":
        raise AssuranceContractError("unsupported studio client folder schema")
    studio_client_id = _text(payload["studio_client_id"], label="studio_client_id")
    if _STUDIO_CLIENT_ID_RE.fullmatch(studio_client_id) is None:
        raise AssuranceContractError("studio_client_id must be a stable client ID")
    scope_id = _text(payload["scope_id"], label="scope_id")
    if _STUDIO_SCOPE_ID_RE.fullmatch(scope_id) is None:
        raise AssuranceContractError("scope_id must be an exact archive scope ID")
    archive_root = _absolute_path(payload["archive_root"], label="archive_root")
    relative_dir = _relative_scope_path(payload["scope_relative_dir"])
    client_root = _absolute_path(payload["client_root"], label="client_root")
    expected_root = Path(archive_root) / Path(relative_dir)
    if Path(client_root) != expected_root:
        raise AssuranceContractError(
            "client_root does not match archive_root and scope_relative_dir"
        )
    expected_scope_id = (
        "scope_"
        + hashlib.sha256(relative_dir.casefold().encode("utf-8")).hexdigest()[:24]
    )
    if scope_id != expected_scope_id:
        raise AssuranceContractError("scope_id does not match scope_relative_dir")
    content = {
        "schema_version": "vera.studio_client_folder.v2",
        "studio_client_id": studio_client_id,
        "scope_id": scope_id,
        "archive_root": archive_root,
        "scope_relative_dir": relative_dir,
        "client_root": client_root,
        "display_name": _text(payload["display_name"], label="display_name"),
    }
    digest = _text(payload["content_sha256"], label="content_sha256")
    expected_digest = canonical_json_sha256(content)
    if digest != expected_digest:
        raise AssuranceContractError("studio client folder content_sha256 is stale")
    return {**content, "content_sha256": expected_digest}


def build_studio_client_folder_binding(
    *,
    studio_client_id: str,
    scope_id: str,
    archive_root: str | Path,
    scope_relative_dir: str,
    client_root: str | Path,
    display_name: str,
) -> dict[str, Any]:
    """Build a digest-bound client folder from one reviewed archive scope."""

    content = {
        "schema_version": "vera.studio_client_folder.v2",
        "studio_client_id": studio_client_id,
        "scope_id": scope_id,
        "archive_root": str(archive_root),
        "scope_relative_dir": scope_relative_dir,
        "client_root": str(client_root),
        "display_name": display_name,
    }
    return validate_studio_client_folder_binding(
        {**content, "content_sha256": canonical_json_sha256(content)}
    )


def _validate_v1_client_engagement_context(value: object) -> dict[str, Any]:
    """Validate the legacy absolute-path client engagement context."""

    payload = _mapping(value, label="client engagement context")
    _exact_fields(
        payload,
        required={
            "schema_version",
            "studio_client_folder",
            "engagement_id",
            "workflow_id",
            "run_id",
            "input_dir",
            "workspace_root",
            "output_dir",
            "content_sha256",
        },
        label="client engagement context",
    )
    if payload["schema_version"] != "vera.client_engagement.v1":
        raise AssuranceContractError("unsupported client engagement schema")
    folder = validate_studio_client_folder_binding(payload["studio_client_folder"])
    engagement_id = _bounded_identifier(payload["engagement_id"], label="engagement_id")
    workflow_id = _bounded_identifier(
        payload["workflow_id"], label="workflow_id", maximum=80
    )
    if workflow_id not in VERA_CLIENT_WORKFLOW_IDS:
        raise AssuranceContractError("workflow_id is not a registered Vera workflow")
    run_id = _bounded_identifier(payload["run_id"], label="run_id")
    input_dir = _absolute_path(payload["input_dir"], label="input_dir")
    workspace_root = _absolute_path(payload["workspace_root"], label="workspace_root")
    output_dir = _absolute_path(payload["output_dir"], label="output_dir")
    if not _path_is_within(input_dir, folder["client_root"]):
        raise AssuranceContractError(
            "input_dir must be inside the selected studio client folder"
        )
    if _path_is_within(workspace_root, folder["client_root"]):
        raise AssuranceContractError(
            "workspace_root must be outside the studio client evidence folder"
        )
    expected_output = (
        Path(workspace_root)
        / "clients"
        / folder["studio_client_id"]
        / "engagements"
        / engagement_id
        / "runs"
        / workflow_id
        / run_id
    )
    if Path(output_dir) != expected_output:
        raise AssuranceContractError(
            "output_dir does not match the client engagement run layout"
        )
    content = {
        "schema_version": "vera.client_engagement.v1",
        "studio_client_folder": folder,
        "engagement_id": engagement_id,
        "workflow_id": workflow_id,
        "run_id": run_id,
        "input_dir": input_dir,
        "workspace_root": workspace_root,
        "output_dir": output_dir,
    }
    digest = _text(payload["content_sha256"], label="content_sha256")
    expected_digest = canonical_json_sha256(content)
    if digest != expected_digest:
        raise AssuranceContractError("client engagement content_sha256 is stale")
    return {**content, "content_sha256": expected_digest}


def _relative_path(value: object, *, label: str) -> str:
    text = _text(value, label=label)
    path = Path(text)
    if (
        path.is_absolute()
        or path.as_posix() != text
        or any(part in {"", ".", ".."} for part in path.parts)
    ):
        raise AssuranceContractError(f"{label} must be a normalized relative path")
    return text


def _validate_v2_input_binding(value: object) -> dict[str, Any]:
    binding = _mapping(value, label="client workflow input binding")
    _exact_fields(
        binding,
        required={
            "binding_id",
            "kind",
            "role",
            "source_relative_path",
            "execution_relative_path",
            "receipt_relative_path",
            "receipt_sha256",
            "sha256",
            "byte_count",
            "upstream_workflow_id",
            "upstream_run_id",
            "upstream_artifact_id",
            "path",
            "source_path",
        },
        label="client workflow input binding",
    )
    binding_id = _text(binding["binding_id"], label="binding_id")
    kind = _text(binding["kind"], label="input kind")
    if kind not in {"import", "upstream_artifact"}:
        raise AssuranceContractError("input kind is unsupported")
    role = _bounded_identifier(binding["role"], label="input role", maximum=80)
    source_relative_path = _relative_path(
        binding["source_relative_path"], label="source_relative_path"
    )
    execution_relative_path = _relative_path(
        binding["execution_relative_path"], label="execution_relative_path"
    )
    if not execution_relative_path.startswith("inputs/"):
        raise AssuranceContractError("execution_relative_path must stay inside inputs")
    receipt_relative_path = _relative_path(
        binding["receipt_relative_path"], label="receipt_relative_path"
    )
    receipt_sha256 = _text(binding["receipt_sha256"], label="receipt_sha256")
    if re.fullmatch(r"[0-9a-f]{64}", receipt_sha256) is None:
        raise AssuranceContractError("receipt_sha256 is invalid")
    sha256 = _text(binding["sha256"], label="input sha256")
    if re.fullmatch(r"[0-9a-f]{64}", sha256) is None:
        raise AssuranceContractError("input sha256 is invalid")
    byte_count = _non_negative_int(binding["byte_count"], label="input byte_count")
    path = _absolute_path(binding["path"], label="input path")
    source_path = _absolute_path(binding["source_path"], label="input source path")
    upstream_workflow_id = binding["upstream_workflow_id"]
    upstream_run_id = binding["upstream_run_id"]
    upstream_artifact_id = binding["upstream_artifact_id"]
    if kind == "import":
        if re.fullmatch(r"input_[0-9a-f]{24}", binding_id) is None:
            raise AssuranceContractError("import binding_id is invalid")
        if any(
            item is not None
            for item in (
                upstream_workflow_id,
                upstream_run_id,
                upstream_artifact_id,
            )
        ):
            raise AssuranceContractError("import binding has upstream fields")
    else:
        upstream_workflow_id = _bounded_identifier(
            upstream_workflow_id,
            label="upstream_workflow_id",
            maximum=80,
        )
        upstream_run_id = _bounded_identifier(upstream_run_id, label="upstream_run_id")
        upstream_artifact_id = _bounded_identifier(
            upstream_artifact_id,
            label="upstream_artifact_id",
        )
        if binding_id != f"artifact:{upstream_run_id}:{upstream_artifact_id}":
            raise AssuranceContractError("upstream artifact binding_id is stale")
    return {
        "binding_id": binding_id,
        "kind": kind,
        "role": role,
        "source_relative_path": source_relative_path,
        "execution_relative_path": execution_relative_path,
        "receipt_relative_path": receipt_relative_path,
        "receipt_sha256": receipt_sha256,
        "sha256": sha256,
        "byte_count": byte_count,
        "upstream_workflow_id": upstream_workflow_id,
        "upstream_run_id": upstream_run_id,
        "upstream_artifact_id": upstream_artifact_id,
        "path": path,
        "source_path": source_path,
    }


def _validate_v2_client_engagement_context(value: object) -> dict[str, Any]:
    """Validate a portable run identity and its optional runtime hydration."""

    payload = _mapping(value, label="client workflow context")
    portable_fields = {
        "schema_version",
        "client_id",
        "engagement_id",
        "workflow_id",
        "workflow_version",
        "run_id",
        "label",
        "purpose",
        "created_at",
        "input_manifest",
        "input_manifest_sha256",
        "run_relative_path",
        "output_relative_path",
        "content_sha256",
    }
    runtime_fields = {
        "studio_client_folder",
        "input_bindings",
        "input_dir",
        "workspace_root",
        "output_dir",
        "run_root",
        "run_manifest_path",
        "input_manifest_path",
        "context_path",
    }
    if (
        not portable_fields.issubset(payload)
        or set(payload) - portable_fields - runtime_fields
    ):
        missing = portable_fields - set(payload)
        unexpected = set(payload) - portable_fields - runtime_fields
        raise AssuranceContractError(
            "client workflow context fields invalid; "
            f"missing={sorted(missing)}, unexpected={sorted(unexpected)}"
        )
    present_runtime = set(payload) & runtime_fields
    if present_runtime and present_runtime != runtime_fields:
        raise AssuranceContractError("client workflow runtime hydration is incomplete")
    if payload["schema_version"] != "vera.client_workflow_context.v2":
        raise AssuranceContractError("unsupported client workflow context schema")
    client_id = _text(payload["client_id"], label="client_id")
    if _STUDIO_CLIENT_ID_RE.fullmatch(client_id) is None:
        raise AssuranceContractError("client_id must be a stable client ID")
    engagement_id = _bounded_identifier(payload["engagement_id"], label="engagement_id")
    if re.fullmatch(r"eng_[0-9a-f]{24}", engagement_id) is None:
        raise AssuranceContractError("engagement_id is invalid")
    workflow_id = _bounded_identifier(
        payload["workflow_id"], label="workflow_id", maximum=80
    )
    if workflow_id not in VERA_CLIENT_WORKFLOW_IDS:
        raise AssuranceContractError("workflow_id is not a registered Vera workflow")
    workflow_version = _text(payload["workflow_version"], label="workflow_version")
    run_id = _bounded_identifier(payload["run_id"], label="run_id")
    if re.fullmatch(r"run_[0-9a-f]{24}", run_id) is None:
        raise AssuranceContractError("run_id is invalid")
    label = _text(payload["label"], label="run label")
    purpose = _text(payload["purpose"], label="run purpose")
    created_at = _text(payload["created_at"], label="created_at")
    input_manifest = _relative_path(payload["input_manifest"], label="input_manifest")
    if input_manifest != "input_manifest.json":
        raise AssuranceContractError("input_manifest must name the run manifest")
    input_manifest_sha256 = _text(
        payload["input_manifest_sha256"], label="input_manifest_sha256"
    )
    if re.fullmatch(r"[0-9a-f]{64}", input_manifest_sha256) is None:
        raise AssuranceContractError("input_manifest_sha256 is invalid")
    run_relative_path = _relative_path(
        payload["run_relative_path"], label="run_relative_path"
    )
    expected_run_relative = (
        Path("Vera") / "engagements" / engagement_id / "runs" / run_id
    ).as_posix()
    if run_relative_path != expected_run_relative:
        raise AssuranceContractError(
            "run_relative_path does not match the run identity"
        )
    output_relative_path = _relative_path(
        payload["output_relative_path"], label="output_relative_path"
    )
    if output_relative_path != "outputs":
        raise AssuranceContractError("output_relative_path must be outputs")
    content = {
        "schema_version": "vera.client_workflow_context.v2",
        "client_id": client_id,
        "engagement_id": engagement_id,
        "workflow_id": workflow_id,
        "workflow_version": workflow_version,
        "run_id": run_id,
        "label": label,
        "purpose": purpose,
        "created_at": created_at,
        "input_manifest": input_manifest,
        "input_manifest_sha256": input_manifest_sha256,
        "run_relative_path": run_relative_path,
        "output_relative_path": output_relative_path,
    }
    digest = _text(payload["content_sha256"], label="content_sha256")
    expected_digest = canonical_json_sha256(content)
    if digest != expected_digest:
        raise AssuranceContractError("client workflow context digest is stale")
    normalized: dict[str, Any] = {**content, "content_sha256": expected_digest}
    if not present_runtime:
        return normalized
    folder = _mapping(payload["studio_client_folder"], label="runtime client folder")
    _exact_fields(
        folder,
        required={"schema_version", "studio_client_id", "client_root"},
        label="runtime client folder",
    )
    if folder["schema_version"] != "vera.studio_client_folder.runtime.v1":
        raise AssuranceContractError("runtime client folder schema is unsupported")
    studio_client_id = _text(folder["studio_client_id"], label="studio_client_id")
    if studio_client_id != client_id:
        raise AssuranceContractError("runtime client folder belongs to another client")
    client_root = _absolute_path(folder["client_root"], label="client_root")
    run_root = _absolute_path(payload["run_root"], label="run_root")
    expected_run_root = Path(client_root) / run_relative_path
    if Path(run_root) != expected_run_root:
        raise AssuranceContractError("run_root does not match the portable run path")
    output_dir = _absolute_path(payload["output_dir"], label="output_dir")
    if Path(output_dir) != expected_run_root / output_relative_path:
        raise AssuranceContractError("output_dir does not match the portable run path")
    workspace_root = _absolute_path(payload["workspace_root"], label="workspace_root")
    if Path(workspace_root) != Path(client_root) / "Vera":
        raise AssuranceContractError("workspace_root must be the customer Vera ledger")
    input_dir = _absolute_path(payload["input_dir"], label="input_dir")
    if not _path_is_within(input_dir, client_root):
        raise AssuranceContractError("input_dir must stay inside the customer folder")
    expected_paths = {
        "run_manifest_path": expected_run_root / "run.json",
        "input_manifest_path": expected_run_root / input_manifest,
        "context_path": expected_run_root / "context.json",
    }
    runtime_paths: dict[str, str] = {}
    for key, expected_path in expected_paths.items():
        runtime_paths[key] = _absolute_path(payload[key], label=key)
        if Path(runtime_paths[key]) != expected_path:
            raise AssuranceContractError(f"{key} does not match the run layout")
    bindings = [
        _validate_v2_input_binding(item)
        for item in _sequence(payload["input_bindings"], label="input_bindings")
    ]
    if not bindings:
        raise AssuranceContractError("client workflow must bind at least one input")
    if len({item["binding_id"] for item in bindings}) != len(bindings):
        raise AssuranceContractError("client workflow input bindings are duplicated")
    for binding in bindings:
        expected_source = Path(client_root) / binding["source_relative_path"]
        expected_path = Path(run_root) / binding["execution_relative_path"]
        if Path(binding["source_path"]) != expected_source:
            raise AssuranceContractError(
                "input source does not match its receipt binding"
            )
        if Path(binding["path"]) != expected_path:
            raise AssuranceContractError(
                "execution input does not match its run binding"
            )
        source_parts = Path(binding["source_relative_path"]).parts
        if (
            len(source_parts) < 5
            or source_parts[0] != "Vera"
            or source_parts[1] != "engagements"
            or source_parts[2] != engagement_id
        ):
            raise AssuranceContractError("input belongs to another engagement")
    normalized.update(
        {
            "studio_client_folder": {
                "schema_version": "vera.studio_client_folder.runtime.v1",
                "studio_client_id": client_id,
                "client_root": client_root,
            },
            "input_bindings": bindings,
            "input_dir": input_dir,
            "workspace_root": workspace_root,
            "output_dir": output_dir,
            "run_root": run_root,
            **runtime_paths,
        }
    )
    return normalized


def validate_client_engagement_context(value: object) -> dict[str, Any]:
    """Validate either a legacy context or the portable customer-folder context."""

    payload = _mapping(value, label="client engagement context")
    if payload.get("schema_version") == "vera.client_workflow_context.v2":
        return _validate_v2_client_engagement_context(payload)
    return _validate_v1_client_engagement_context(payload)


def build_client_engagement_context(
    *,
    studio_client_folder: Mapping[str, Any],
    engagement_id: str,
    workflow_id: str,
    run_id: str,
    input_dir: str | Path,
    workspace_root: str | Path,
) -> dict[str, Any]:
    """Build the only permitted output path for a client-bound workflow run."""

    folder = validate_studio_client_folder_binding(studio_client_folder)
    output_dir = (
        Path(workspace_root)
        / "clients"
        / folder["studio_client_id"]
        / "engagements"
        / engagement_id
        / "runs"
        / workflow_id
        / run_id
    )
    content = {
        "schema_version": "vera.client_engagement.v1",
        "studio_client_folder": folder,
        "engagement_id": engagement_id,
        "workflow_id": workflow_id,
        "run_id": run_id,
        "input_dir": str(input_dir),
        "workspace_root": str(workspace_root),
        "output_dir": str(output_dir),
    }
    return validate_client_engagement_context(
        {**content, "content_sha256": canonical_json_sha256(content)}
    )


def validate_client_workflow_run(
    value: object,
    *,
    expected_workflow_id: str,
    input_paths: Sequence[str | Path] = (),
    output_dir: str | Path | None = None,
) -> dict[str, Any]:
    """Enforce mechanically verifiable path identity and client containment.

    Client selection and source relevance remain model/user judgments. Fixed
    rules are appropriate here because path ancestry, workflow identity, and
    digest closure are exact security and audit properties.
    """

    if expected_workflow_id not in VERA_CLIENT_WORKFLOW_IDS:
        raise AssuranceContractError(
            "expected_workflow_id is not a registered Vera workflow"
        )
    context = validate_client_engagement_context(value)
    if context["workflow_id"] != expected_workflow_id:
        raise AssuranceContractError(
            "client engagement context belongs to a different Vera workflow"
        )
    expected_output = Path(context["output_dir"])
    if output_dir is not None:
        try:
            observed_output = Path(output_dir).expanduser().resolve()
        except OSError as exc:
            raise AssuranceContractError(
                f"output_dir cannot be resolved: {exc}"
            ) from exc
        if not (
            observed_output == expected_output
            or observed_output.is_relative_to(expected_output)
        ):
            raise AssuranceContractError(
                "output_dir is outside the client engagement run"
            )
    if context["schema_version"] == "vera.client_workflow_context.v2":
        selected = {Path(item["path"]) for item in context["input_bindings"]}
        for raw_path in input_paths:
            try:
                candidate = Path(raw_path).expanduser().resolve(strict=True)
            except OSError as exc:
                raise AssuranceContractError(
                    f"workflow input is unavailable: {exc}"
                ) from exc
            if candidate == expected_output or candidate.is_relative_to(
                expected_output
            ):
                continue
            if candidate.is_file():
                if candidate not in selected:
                    raise AssuranceContractError(
                        "workflow input is not one of the run's exact receipts"
                    )
                continue
            if not candidate.is_dir() or candidate.is_symlink():
                raise AssuranceContractError(
                    "workflow input must be a receipted file or closed input folder"
                )
            observed_files: set[Path] = set()
            for child in candidate.rglob("*"):
                if child.is_symlink():
                    raise AssuranceContractError(
                        "workflow input folder contains a symbolic link"
                    )
                if child.is_dir():
                    continue
                if not child.is_file():
                    raise AssuranceContractError(
                        "workflow input folder contains a non-regular entry"
                    )
                if child.name in {"receipt.json", ".DS_Store"}:
                    continue
                observed_files.add(child.resolve(strict=True))
            selected_inside = {
                item for item in selected if item.is_relative_to(candidate)
            }
            if not selected_inside or observed_files != selected_inside:
                raise AssuranceContractError(
                    "workflow input folder is not closed to the run's exact receipts"
                )
        return context
    folder = context["studio_client_folder"]
    engagement_workspace = (
        Path(context["workspace_root"])
        / "clients"
        / folder["studio_client_id"]
        / "engagements"
        / context["engagement_id"]
    )
    managed_input = Path(context["input_dir"])
    for raw_path in input_paths:
        try:
            candidate = Path(raw_path).expanduser().resolve(strict=True)
        except OSError as exc:
            raise AssuranceContractError(
                f"workflow input is unavailable: {exc}"
            ) from exc
        if not (
            candidate == managed_input
            or candidate.is_relative_to(managed_input)
            or candidate == engagement_workspace
            or candidate.is_relative_to(engagement_workspace)
        ):
            raise AssuranceContractError(
                "workflow input is outside the selected client engagement"
            )
    return context


def _read_bounded_regular_json(
    path: Path,
    *,
    label: str,
    maximum_bytes: int = 4 * 1024 * 1024,
) -> dict[str, Any]:
    """Read a stable manifest without following a final-component symlink."""

    try:
        before = path.lstat()
    except OSError as exc:
        raise AssuranceContractError(f"{label} is unavailable: {exc}") from exc
    if (
        path.is_symlink()
        or not stat.S_ISREG(before.st_mode)
        or before.st_nlink < 1
        or before.st_size > maximum_bytes
    ):
        raise AssuranceContractError(f"{label} must be a bounded regular file")
    descriptor = -1
    try:
        descriptor = os.open(path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
        opened = os.fstat(descriptor)
        identity = (
            before.st_dev,
            before.st_ino,
            before.st_size,
            before.st_mtime_ns,
            before.st_nlink,
        )
        if identity != (
            opened.st_dev,
            opened.st_ino,
            opened.st_size,
            opened.st_mtime_ns,
            opened.st_nlink,
        ):
            raise AssuranceContractError(f"{label} changed before it was read")
        chunks: list[bytes] = []
        remaining = before.st_size + 1
        while remaining:
            chunk = os.read(descriptor, min(64 * 1024, remaining))
            if not chunk:
                break
            chunks.append(chunk)
            remaining -= len(chunk)
        raw = b"".join(chunks)
        after = os.fstat(descriptor)
        if (
            identity
            != (
                after.st_dev,
                after.st_ino,
                after.st_size,
                after.st_mtime_ns,
                after.st_nlink,
            )
            or len(raw) != after.st_size
        ):
            raise AssuranceContractError(f"{label} changed while it was read")
        payload = json.loads(raw.decode("utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise AssuranceContractError(f"{label} is unreadable: {exc}") from exc
    finally:
        if descriptor >= 0:
            os.close(descriptor)
    if not isinstance(payload, dict):
        raise AssuranceContractError(f"{label} must contain a JSON object")
    return payload


def _validated_sealed_manifest(
    payload: Mapping[str, Any], *, label: str
) -> dict[str, Any]:
    digest = _text(payload.get("content_sha256"), label=f"{label}.content_sha256")
    content = {key: value for key, value in payload.items() if key != "content_sha256"}
    if digest != canonical_json_sha256(content):
        raise AssuranceContractError(f"{label} content digest is stale")
    return dict(payload)


def _stable_file_identity(path: Path, *, label: str) -> tuple[int, str]:
    """Hash one stable ordinary file for exact run-input replay."""

    try:
        before_path = path.lstat()
    except OSError as exc:
        raise AssuranceContractError(f"{label} is unavailable: {exc}") from exc
    if path.is_symlink() or not stat.S_ISREG(before_path.st_mode):
        raise AssuranceContractError(f"{label} must be a regular non-symlink file")
    digest = hashlib.sha256()
    byte_count = 0
    try:
        with path.open("rb") as handle:
            before = os.fstat(handle.fileno())
            identity = (
                before.st_dev,
                before.st_ino,
                before.st_size,
                before.st_mtime_ns,
            )
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(chunk)
                byte_count += len(chunk)
            after = os.fstat(handle.fileno())
    except OSError as exc:
        raise AssuranceContractError(f"{label} is unreadable: {exc}") from exc
    if (
        identity
        != (
            after.st_dev,
            after.st_ino,
            after.st_size,
            after.st_mtime_ns,
        )
        or byte_count != after.st_size
    ):
        raise AssuranceContractError(f"{label} changed while it was read")
    return byte_count, digest.hexdigest()


def _validated_portable_run_manifest(
    payload: Mapping[str, Any], *, label: str
) -> dict[str, Any]:
    """Validate the static seal and mechanically consistent lifecycle."""

    _exact_fields(payload, required=_RUN_MANIFEST_FIELDS, label=label)
    if payload["schema_version"] != "vera.workflow_run.v1":
        raise AssuranceContractError(f"{label} schema is unsupported")
    client_id = _text(payload["client_id"], label=f"{label}.client_id")
    engagement_id = _text(payload["engagement_id"], label=f"{label}.engagement_id")
    run_id = _text(payload["run_id"], label=f"{label}.run_id")
    if _STUDIO_CLIENT_ID_RE.fullmatch(client_id) is None:
        raise AssuranceContractError(f"{label} client_id is invalid")
    if _ENGAGEMENT_ID_RE.fullmatch(engagement_id) is None:
        raise AssuranceContractError(f"{label} engagement_id is invalid")
    if _RUN_ID_RE.fullmatch(run_id) is None:
        raise AssuranceContractError(f"{label} run_id is invalid")
    workflow_id = _bounded_identifier(
        payload["workflow_id"], label=f"{label}.workflow_id", maximum=80
    )
    if workflow_id not in VERA_CLIENT_WORKFLOW_IDS:
        raise AssuranceContractError(f"{label} workflow_id is unsupported")
    for key in (
        "workflow_version",
        "label",
        "purpose",
        "idempotency_key",
        "created_at",
        "updated_at",
    ):
        _text(payload[key], label=f"{label}.{key}")
    if payload["input_manifest"] != "input_manifest.json":
        raise AssuranceContractError(f"{label} input manifest path is invalid")
    if payload["context"] != "context.json":
        raise AssuranceContractError(f"{label} context path is invalid")
    for key in ("input_manifest_sha256", "static_sha256"):
        digest = _text(payload[key], label=f"{label}.{key}")
        if re.fullmatch(r"[0-9a-f]{64}", digest) is None:
            raise AssuranceContractError(f"{label} {key} is invalid")
    if payload["static_sha256"] != canonical_json_sha256(
        {key: payload[key] for key in _RUN_STATIC_KEYS}
    ):
        raise AssuranceContractError(f"{label} static digest is stale")
    status = _text(payload["status"], label=f"{label}.status")
    if status not in _RUN_TRANSITIONS:
        raise AssuranceContractError(f"{label} status is invalid")
    history = _sequence(payload["status_history"], label=f"{label}.status_history")
    if not history:
        raise AssuranceContractError(f"{label} status history is empty")
    observed_statuses: list[str] = []
    observed_times: list[str] = []
    for index, raw_event in enumerate(history):
        event = _mapping(raw_event, label=f"{label}.status_history[{index}]")
        _exact_fields(
            event,
            required={"status", "at"},
            label=f"{label}.status_history[{index}]",
        )
        event_status = _text(
            event["status"], label=f"{label}.status_history[{index}].status"
        )
        if event_status not in _RUN_TRANSITIONS:
            raise AssuranceContractError(f"{label} status history is invalid")
        observed_statuses.append(event_status)
        observed_times.append(
            _text(event["at"], label=f"{label}.status_history[{index}].at")
        )
    if observed_statuses[0] != "prepared":
        raise AssuranceContractError(f"{label} must begin in prepared state")
    for current, target in zip(observed_statuses, observed_statuses[1:]):
        if target not in _RUN_TRANSITIONS[current]:
            raise AssuranceContractError(f"{label} status history is inconsistent")
    if observed_statuses[-1] != status or observed_times[-1] != payload["updated_at"]:
        raise AssuranceContractError(f"{label} current lifecycle is stale")
    failure = payload["failure"]
    if status == "failed":
        failure_record = _mapping(failure, label=f"{label}.failure")
        _exact_fields(
            failure_record,
            required={"reason", "recorded_at"},
            label=f"{label}.failure",
        )
        _text(failure_record["reason"], label=f"{label}.failure.reason")
        if (
            _text(
                failure_record["recorded_at"],
                label=f"{label}.failure.recorded_at",
            )
            != payload["updated_at"]
        ):
            raise AssuranceContractError(f"{label} failure timestamp is stale")
    elif failure is not None:
        raise AssuranceContractError(f"{label} has a failure outside failed state")
    return dict(payload)


def _hydrate_v2_client_workflow_context(
    context_path: Path,
    payload: Mapping[str, Any],
    *,
    allowed_statuses: frozenset[str],
) -> dict[str, Any]:
    portable = _validate_v2_client_engagement_context(payload)
    if context_path.name != "context.json" or len(context_path.parents) < 6:
        raise AssuranceContractError(
            "client workflow context path is not a run context"
        )
    run_root = context_path.parent
    client_root = context_path.parents[5]
    expected_run_root = client_root / portable["run_relative_path"]
    if run_root != expected_run_root:
        raise AssuranceContractError(
            "context path does not match its portable run identity"
        )
    for parent in (
        client_root,
        client_root / "Vera",
        client_root / "Vera" / "engagements",
        client_root / "Vera" / "engagements" / portable["engagement_id"],
        run_root.parent,
        run_root,
    ):
        try:
            observed = parent.lstat()
        except OSError as exc:
            raise AssuranceContractError(f"run path is unavailable: {exc}") from exc
        if parent.is_symlink() or not stat.S_ISDIR(observed.st_mode):
            raise AssuranceContractError("run path contains a non-directory or symlink")

    client_manifest = _validated_sealed_manifest(
        _read_bounded_regular_json(
            client_root / "Vera" / "client.json", label="client manifest"
        ),
        label="client manifest",
    )
    if (
        client_manifest.get("schema_version") != "vera.customer_folder.v1"
        or client_manifest.get("client_id") != portable["client_id"]
    ):
        raise AssuranceContractError("client manifest does not match the run")
    engagement_manifest = _validated_sealed_manifest(
        _read_bounded_regular_json(
            client_root
            / "Vera"
            / "engagements"
            / portable["engagement_id"]
            / "engagement.json",
            label="engagement manifest",
        ),
        label="engagement manifest",
    )
    if (
        engagement_manifest.get("schema_version") != "vera.engagement.v1"
        or engagement_manifest.get("client_id") != portable["client_id"]
        or engagement_manifest.get("engagement_id") != portable["engagement_id"]
        or engagement_manifest.get("status") not in {"open", "closed"}
    ):
        raise AssuranceContractError("engagement manifest does not authorize this run")
    engagement_status = engagement_manifest["status"]

    run_manifest = _validated_portable_run_manifest(
        _read_bounded_regular_json(run_root / "run.json", label="run manifest"),
        label="run manifest",
    )
    if (
        run_manifest.get("schema_version") != "vera.workflow_run.v1"
        or run_manifest.get("client_id") != portable["client_id"]
        or run_manifest.get("engagement_id") != portable["engagement_id"]
        or run_manifest.get("workflow_id") != portable["workflow_id"]
        or run_manifest.get("workflow_version") != portable["workflow_version"]
        or run_manifest.get("run_id") != portable["run_id"]
        or run_manifest.get("label") != portable["label"]
        or run_manifest.get("purpose") != portable["purpose"]
        or run_manifest.get("created_at") != portable["created_at"]
        or run_manifest.get("context") != "context.json"
        or run_manifest.get("input_manifest") != portable["input_manifest"]
        or run_manifest.get("input_manifest_sha256")
        != portable["input_manifest_sha256"]
    ):
        raise AssuranceContractError("run manifest does not match the context")
    if run_manifest.get("status") not in allowed_statuses:
        if allowed_statuses == frozenset({"running"}):
            raise AssuranceContractError(
                "workflow helper execution requires a run in running state"
            )
        raise AssuranceContractError(
            "workflow helper execution requires an explicitly allowed run state"
        )
    if engagement_status == "closed" and run_manifest.get("status") != "completed":
        raise AssuranceContractError(
            "a closed engagement authorizes completed run evidence only"
        )
    input_manifest_path = run_root / portable["input_manifest"]
    input_manifest = _validated_sealed_manifest(
        _read_bounded_regular_json(
            input_manifest_path,
            label="run input manifest",
            maximum_bytes=16 * 1024 * 1024,
        ),
        label="run input manifest",
    )
    if (
        input_manifest.get("schema_version") != "vera.run_inputs.v1"
        or input_manifest.get("client_id") != portable["client_id"]
        or input_manifest.get("engagement_id") != portable["engagement_id"]
        or input_manifest.get("run_id") != portable["run_id"]
        or input_manifest.get("content_sha256") != portable["input_manifest_sha256"]
    ):
        raise AssuranceContractError("run input manifest does not match the context")
    raw_bindings = _sequence(input_manifest.get("inputs"), label="run inputs")
    if not raw_bindings:
        raise AssuranceContractError("run input manifest is empty")
    bindings: list[dict[str, Any]] = []
    for index, raw_binding in enumerate(raw_bindings):
        item = _mapping(raw_binding, label=f"run inputs[{index}]")
        relative_source = _relative_path(
            item.get("source_relative_path"), label="source_relative_path"
        )
        source = client_root / relative_source
        try:
            if source.resolve(strict=True) != source:
                raise AssuranceContractError(
                    "bound workflow input path contains a symbolic link"
                )
        except OSError as exc:
            raise AssuranceContractError(
                f"bound workflow input path is unavailable: {exc}"
            ) from exc
        byte_count, sha256 = _stable_file_identity(source, label="bound workflow input")
        relative_execution = _relative_path(
            item.get("execution_relative_path"), label="execution_relative_path"
        )
        execution = run_root / relative_execution
        try:
            if execution.resolve(strict=True) != execution:
                raise AssuranceContractError(
                    "run execution input path contains a symbolic link"
                )
        except OSError as exc:
            raise AssuranceContractError(
                f"run execution input path is unavailable: {exc}"
            ) from exc
        execution_byte_count, execution_sha256 = _stable_file_identity(
            execution, label="run execution input"
        )
        binding = _validate_v2_input_binding(
            {**item, "source_path": str(source), "path": str(execution)}
        )
        if byte_count != binding["byte_count"] or sha256 != binding["sha256"]:
            raise AssuranceContractError(
                "bound workflow input no longer matches its receipt"
            )
        if (
            execution_byte_count != binding["byte_count"]
            or execution_sha256 != binding["sha256"]
        ):
            raise AssuranceContractError(
                "run execution input no longer matches its receipt"
            )
        receipt_path = client_root / binding["receipt_relative_path"]
        try:
            if receipt_path.resolve(strict=True) != receipt_path:
                raise AssuranceContractError(
                    "bound input receipt path contains a symbolic link"
                )
        except OSError as exc:
            raise AssuranceContractError(
                f"bound input receipt path is unavailable: {exc}"
            ) from exc
        receipt = _validated_sealed_manifest(
            _read_bounded_regular_json(
                receipt_path,
                label="input receipt",
                maximum_bytes=16 * 1024 * 1024,
            ),
            label="input receipt",
        )
        if receipt.get("content_sha256") != binding["receipt_sha256"]:
            raise AssuranceContractError("bound input receipt digest is stale")
        if binding["kind"] == "import":
            if (
                receipt.get("schema_version") != "vera.input_receipt.v1"
                or receipt.get("client_id") != portable["client_id"]
                or receipt.get("engagement_id") != portable["engagement_id"]
                or receipt.get("input_id") != binding["binding_id"]
                or receipt.get("sha256") != binding["sha256"]
                or receipt.get("byte_count") != binding["byte_count"]
                or receipt_path.parent / str(receipt.get("stored_name")) != source
            ):
                raise AssuranceContractError("import receipt does not match its input")
        else:
            if (
                receipt.get("schema_version") != "vera.artifact_manifest.v1"
                or receipt.get("client_id") != portable["client_id"]
                or receipt.get("engagement_id") != portable["engagement_id"]
                or receipt.get("run_id") != binding["upstream_run_id"]
                or receipt.get("workflow_id") != binding["upstream_workflow_id"]
            ):
                raise AssuranceContractError("upstream artifact manifest is invalid")
            upstream_run_manifest = _validated_portable_run_manifest(
                _read_bounded_regular_json(
                    receipt_path.parent / "run.json", label="upstream run manifest"
                ),
                label="upstream run manifest",
            )
            if (
                upstream_run_manifest["client_id"] != portable["client_id"]
                or upstream_run_manifest["engagement_id"] != portable["engagement_id"]
                or upstream_run_manifest["run_id"] != binding["upstream_run_id"]
                or upstream_run_manifest["workflow_id"]
                != binding["upstream_workflow_id"]
                or upstream_run_manifest["status"]
                not in {"ready_for_review", "completed"}
            ):
                raise AssuranceContractError(
                    "upstream run is no longer available for handoff"
                )
            artifacts = _sequence(receipt.get("artifacts"), label="upstream artifacts")
            artifact = next(
                (
                    candidate
                    for candidate in artifacts
                    if isinstance(candidate, Mapping)
                    and candidate.get("artifact_id") == binding["upstream_artifact_id"]
                ),
                None,
            )
            if (
                artifact is None
                or artifact.get("sha256") != binding["sha256"]
                or artifact.get("byte_count") != binding["byte_count"]
                or receipt_path.parent / "outputs" / str(artifact.get("path")) != source
            ):
                raise AssuranceContractError("upstream artifact binding is stale")
        bindings.append(binding)
    if len({item["binding_id"] for item in bindings}) != len(bindings):
        raise AssuranceContractError("run input bindings are duplicated")
    hydrated = {
        **portable,
        "studio_client_folder": {
            "schema_version": "vera.studio_client_folder.runtime.v1",
            "studio_client_id": portable["client_id"],
            "client_root": str(client_root),
        },
        "input_bindings": bindings,
        "input_dir": str(run_root / "inputs"),
        "workspace_root": str(client_root / "Vera"),
        "output_dir": str(run_root / "outputs"),
        "run_root": str(run_root),
        "run_manifest_path": str(run_root / "run.json"),
        "input_manifest_path": str(input_manifest_path),
        "context_path": str(context_path),
    }
    return _validate_v2_client_engagement_context(hydrated)


def load_client_engagement_context_file(
    path: str | Path,
    *,
    expected_workflow_id: str,
    input_paths: Sequence[str | Path] = (),
    output_dir: str | Path | None = None,
    allowed_statuses: Sequence[str] = ("running",),
) -> dict[str, Any]:
    """Read and validate one private Studio Archive workflow context file.

    Writers use the default running-only boundary. Read-only consumers may opt
    into the finalized states they can consume without mutating that run.
    """

    if isinstance(allowed_statuses, (str, bytes)):
        raise AssuranceContractError("allowed_statuses must be a status sequence")
    normalized_statuses = frozenset(allowed_statuses)
    readable_statuses = frozenset({"running", "ready_for_review", "completed"})
    if not normalized_statuses or not normalized_statuses.issubset(readable_statuses):
        raise AssuranceContractError(
            "allowed_statuses contains an unreadable run state"
        )

    context_path = Path(path).expanduser()
    if not context_path.is_absolute():
        raise AssuranceContractError("client engagement context path must be absolute")
    try:
        before = context_path.lstat()
    except OSError as exc:
        raise AssuranceContractError(
            f"client engagement context file is unavailable: {exc}"
        ) from exc
    if (
        context_path.is_symlink()
        or not stat.S_ISREG(before.st_mode)
        or before.st_nlink != 1
        or before.st_size > 256 * 1024
    ):
        raise AssuranceContractError(
            "client engagement context must be a bounded single-link regular file"
        )
    descriptor = -1
    try:
        descriptor = os.open(
            context_path,
            os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0),
        )
        opened = os.fstat(descriptor)
        identity = (
            before.st_dev,
            before.st_ino,
            before.st_size,
            before.st_mtime_ns,
            before.st_nlink,
        )
        if identity != (
            opened.st_dev,
            opened.st_ino,
            opened.st_size,
            opened.st_mtime_ns,
            opened.st_nlink,
        ):
            raise AssuranceContractError(
                "client engagement context changed before it was read"
            )
        chunks: list[bytes] = []
        remaining = before.st_size + 1
        while remaining:
            chunk = os.read(descriptor, min(64 * 1024, remaining))
            if not chunk:
                break
            chunks.append(chunk)
            remaining -= len(chunk)
        current = b"".join(chunks)
        after = os.fstat(descriptor)
        if (
            identity
            != (
                after.st_dev,
                after.st_ino,
                after.st_size,
                after.st_mtime_ns,
                after.st_nlink,
            )
            or len(current) != after.st_size
        ):
            raise AssuranceContractError(
                "client engagement context changed while it was read"
            )
        payload = json.loads(current.decode("utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise AssuranceContractError(
            f"client engagement context file is unreadable: {exc}"
        ) from exc
    finally:
        if descriptor >= 0:
            os.close(descriptor)
    if (
        not isinstance(payload, Mapping)
        or payload.get("schema_version") != "vera.client_workflow_context.v2"
    ):
        raise AssuranceContractError(
            "workflow entrypoints require a portable customer-folder context"
        )
    context = _hydrate_v2_client_workflow_context(
        context_path,
        payload,
        allowed_statuses=normalized_statuses,
    )
    return validate_client_workflow_run(
        context,
        expected_workflow_id=expected_workflow_id,
        input_paths=input_paths,
        output_dir=output_dir,
    )


def load_client_workflow_context_for_output(
    output_path: str | Path,
    *,
    expected_workflow_id: str,
    input_paths: Sequence[str | Path] = (),
) -> dict[str, Any]:
    """Hydrate the portable run context owning one output path.

    This is the gate for secondary writers whose only natural entry point is a
    run output folder. The context is discovered from the portable customer
    tree, never from an absolute path persisted inside an earlier artifact.
    """

    candidate = Path(output_path).expanduser()
    if not candidate.is_absolute():
        raise AssuranceContractError("workflow output path must be absolute")
    if any(part in {".", ".."} for part in candidate.parts):
        raise AssuranceContractError("workflow output path must be normalized")
    # Inspect the caller's lexical path before resolve() can erase an alias.
    # This fixed rule protects exact run ownership and is mechanically verifiable.
    probe = Path(candidate.anchor)
    candidate_parts = candidate.parts[1:]
    for index, part in enumerate(candidate_parts):
        probe /= part
        if not probe.exists() and not probe.is_symlink():
            continue
        try:
            observed = probe.lstat()
        except OSError as exc:
            raise AssuranceContractError(
                f"workflow output path is unavailable: {exc}"
            ) from exc
        if stat.S_ISLNK(observed.st_mode):
            raise AssuranceContractError(
                "workflow output path contains a symbolic link"
            )
        if index < len(candidate_parts) - 1 and not stat.S_ISDIR(observed.st_mode):
            raise AssuranceContractError(
                "workflow output path contains a non-directory ancestor"
            )
    try:
        resolved = candidate.resolve()
    except OSError as exc:
        raise AssuranceContractError(
            f"workflow output path cannot be resolved: {exc}"
        ) from exc
    output_root = next(
        (
            ancestor
            for ancestor in (resolved, *resolved.parents)
            if ancestor.name == "outputs"
            and (ancestor.parent / "context.json").is_file()
        ),
        None,
    )
    if output_root is None:
        raise AssuranceContractError(
            "workflow output is not inside a portable customer-folder run"
        )
    context = load_client_engagement_context_file(
        output_root.parent / "context.json",
        expected_workflow_id=expected_workflow_id,
        input_paths=input_paths,
        output_dir=resolved,
    )
    probe = output_root
    relative = resolved.relative_to(output_root)
    for index, part in enumerate(relative.parts):
        probe /= part
        if not probe.exists() and not probe.is_symlink():
            continue
        try:
            observed = probe.lstat()
        except OSError as exc:
            raise AssuranceContractError(
                f"workflow output path is unavailable: {exc}"
            ) from exc
        if probe.is_symlink():
            raise AssuranceContractError(
                "workflow output path contains a symbolic link"
            )
        if index < len(relative.parts) - 1 and not stat.S_ISDIR(observed.st_mode):
            raise AssuranceContractError(
                "workflow output path contains a non-directory ancestor"
            )
    return context


def _validated_control(control: object, *, label: str) -> dict[str, Any]:
    item = _mapping(control, label=label)
    _exact_fields(
        item,
        required={"control_id", "required", "status", "evidence_refs", "detail"},
        label=label,
    )
    control_id = _identifier(item["control_id"], label=f"{label}.control_id")
    if not isinstance(item["required"], bool):
        raise AssuranceContractError(f"{label}.required must be boolean")
    status = _text(item["status"], label=f"{label}.status")
    if status not in _CONTROL_STATUSES:
        raise AssuranceContractError(f"{label}.status is unsupported")
    evidence_refs = [
        _identifier(ref, label=f"{label}.evidence_refs[{index}]")
        for index, ref in enumerate(
            _sequence(item["evidence_refs"], label=f"{label}.evidence_refs")
        )
    ]
    if len(evidence_refs) != len(set(evidence_refs)):
        raise AssuranceContractError(f"{label}.evidence_refs must be unique")
    return {
        "control_id": control_id,
        "required": item["required"],
        "status": status,
        "evidence_refs": evidence_refs,
        "detail": _text(item["detail"], label=f"{label}.detail", allow_empty=True),
    }


def validate_source_qualification(value: object) -> dict[str, Any]:
    """Validate a pre-parser source qualification record."""

    payload = _mapping(value, label="source qualification")
    _exact_fields(
        payload,
        required={
            "schema_version",
            "qualification_id",
            "adapter_id",
            "adapter_version",
            "source_family",
            "status",
            "source_artifact_refs",
            "reviewed_mapping_ref",
            "candidate_row_count",
            "emitted_row_count",
            "controls",
            "limitations",
        },
        label="source qualification",
    )
    if payload["schema_version"] != "vera.source_qualification.v1":
        raise AssuranceContractError("unsupported source qualification schema")
    normalized: dict[str, Any] = {
        "schema_version": "vera.source_qualification.v1",
        "qualification_id": _identifier(
            payload["qualification_id"], label="qualification_id"
        ),
        "adapter_id": _identifier(payload["adapter_id"], label="adapter_id"),
        "adapter_version": _identifier(
            payload["adapter_version"], label="adapter_version"
        ),
        "source_family": _identifier(payload["source_family"], label="source_family"),
    }
    status = _text(payload["status"], label="status")
    if status not in _QUALIFICATION_STATUSES:
        raise AssuranceContractError("unsupported source qualification status")
    normalized["status"] = status
    source_refs = [
        _identifier(ref, label=f"source_artifact_refs[{index}]")
        for index, ref in enumerate(
            _sequence(payload["source_artifact_refs"], label="source_artifact_refs")
        )
    ]
    if not source_refs or len(source_refs) != len(set(source_refs)):
        raise AssuranceContractError(
            "source_artifact_refs must be non-empty and unique"
        )
    normalized["source_artifact_refs"] = source_refs
    reviewed_mapping_ref = payload["reviewed_mapping_ref"]
    if reviewed_mapping_ref is not None:
        reviewed_mapping_ref = _identifier(
            reviewed_mapping_ref, label="reviewed_mapping_ref"
        )
    normalized["reviewed_mapping_ref"] = reviewed_mapping_ref
    candidate_count = _non_negative_int(
        payload["candidate_row_count"], label="candidate_row_count"
    )
    emitted_count = _non_negative_int(
        payload["emitted_row_count"], label="emitted_row_count"
    )
    normalized["candidate_row_count"] = candidate_count
    normalized["emitted_row_count"] = emitted_count
    if emitted_count > candidate_count:
        raise AssuranceContractError(
            "emitted_row_count cannot exceed candidate_row_count"
        )
    controls = [
        _validated_control(item, label=f"controls[{index}]")
        for index, item in enumerate(_sequence(payload["controls"], label="controls"))
    ]
    control_ids = [item["control_id"] for item in controls]
    if not controls or len(control_ids) != len(set(control_ids)):
        raise AssuranceContractError("controls must be non-empty and unique")
    normalized["controls"] = controls
    normalized["limitations"] = [
        _text(item, label=f"limitations[{index}]")
        for index, item in enumerate(
            _sequence(payload["limitations"], label="limitations")
        )
    ]

    required = [item for item in controls if item["required"]]
    required_failed = [item for item in required if item["status"] == "failed"]
    required_unassessed = [
        item for item in required if item["status"] == "not_assessed"
    ]
    if status == "qualified":
        if required_failed or required_unassessed:
            raise AssuranceContractError(
                "qualified source requires every required control to pass"
            )
    elif status == "unsupported_source_layout":
        if not required_failed:
            raise AssuranceContractError(
                "unsupported layout requires a failed required control"
            )
        if emitted_count:
            raise AssuranceContractError("unsupported layout cannot emit prepared rows")
    else:
        if required_failed or not required_unassessed:
            raise AssuranceContractError(
                "needs_review requires unassessed, but no failed, required controls"
            )
        if emitted_count:
            raise AssuranceContractError(
                "needs_review source cannot emit prepared rows"
            )
    return normalized


def build_source_qualification(
    *,
    qualification_id: str,
    adapter_id: str,
    adapter_version: str,
    source_family: str,
    status: str,
    source_artifact_refs: Sequence[str],
    controls: Sequence[Mapping[str, Any]],
    candidate_row_count: int = 0,
    emitted_row_count: int = 0,
    reviewed_mapping_ref: str | None = None,
    limitations: Sequence[str] = (),
) -> dict[str, Any]:
    """Build and validate a source qualification record."""

    return validate_source_qualification(
        {
            "schema_version": "vera.source_qualification.v1",
            "qualification_id": qualification_id,
            "adapter_id": adapter_id,
            "adapter_version": adapter_version,
            "source_family": source_family,
            "status": status,
            "source_artifact_refs": list(source_artifact_refs),
            "reviewed_mapping_ref": reviewed_mapping_ref,
            "candidate_row_count": candidate_row_count,
            "emitted_row_count": emitted_row_count,
            "controls": [dict(item) for item in controls],
            "limitations": list(limitations),
        }
    )


def validate_gate_register(value: object) -> dict[str, Any]:
    """Validate independent assurance gates and their declared dependencies."""

    payload = _mapping(value, label="gate register")
    _exact_fields(
        payload,
        required={"schema_version", "gates", "report_ready"},
        label="gate register",
    )
    if payload["schema_version"] != "vera.assurance_gates.v1":
        raise AssuranceContractError("unsupported gate-register schema")
    gates = _mapping(payload["gates"], label="gates")
    if set(gates) != set(_GATE_NAMES):
        raise AssuranceContractError(f"gates must contain exactly {_GATE_NAMES}")
    normalized_gates: dict[str, Any] = {}
    for gate_name in _GATE_NAMES:
        gate = _mapping(gates[gate_name], label=f"gates.{gate_name}")
        _exact_fields(
            gate,
            required={"status", "evidence_refs", "limitations"},
            label=f"gates.{gate_name}",
        )
        status = _text(gate["status"], label=f"gates.{gate_name}.status")
        if status not in _GATE_STATUSES:
            raise AssuranceContractError(f"gates.{gate_name}.status is unsupported")
        evidence_refs = [
            _identifier(ref, label=f"gates.{gate_name}.evidence_refs[{index}]")
            for index, ref in enumerate(
                _sequence(
                    gate["evidence_refs"], label=f"gates.{gate_name}.evidence_refs"
                )
            )
        ]
        if len(evidence_refs) != len(set(evidence_refs)):
            raise AssuranceContractError(
                f"gates.{gate_name}.evidence_refs must be unique"
            )
        limitations = [
            _text(item, label=f"gates.{gate_name}.limitations[{index}]")
            for index, item in enumerate(
                _sequence(gate["limitations"], label=f"gates.{gate_name}.limitations")
            )
        ]
        if status == "passed" and not evidence_refs:
            raise AssuranceContractError(
                f"passed gate {gate_name} requires evidence_refs"
            )
        normalized_gates[gate_name] = {
            "status": status,
            "evidence_refs": evidence_refs,
            "limitations": limitations,
        }
    for gate_name, dependencies in _DEFAULT_GATE_DEPENDENCIES.items():
        if normalized_gates[gate_name]["status"] != "passed":
            continue
        for dependency in dependencies:
            if normalized_gates[dependency]["status"] not in {
                "passed",
                "not_applicable",
            }:
                raise AssuranceContractError(
                    f"passed gate {gate_name} requires {dependency} to pass "
                    "or be not_applicable"
                )
    if not isinstance(payload["report_ready"], bool):
        raise AssuranceContractError("report_ready must be boolean")
    ready_statuses = {
        normalized_gates[name]["status"]
        for name in (
            "source",
            "preparation",
            "reconciliation",
            "semantic_review",
            "reporting",
        )
    }
    computed_ready = ready_statuses <= {"passed", "not_applicable"}
    if payload["report_ready"] != computed_ready:
        raise AssuranceContractError("report_ready does not match gate statuses")
    return {
        "schema_version": "vera.assurance_gates.v1",
        "gates": normalized_gates,
        "report_ready": computed_ready,
    }


def build_gate_register(
    gates: Mapping[str, Mapping[str, Any]],
) -> dict[str, Any]:
    """Build a gate register and derive report readiness."""

    raw = {
        "schema_version": "vera.assurance_gates.v1",
        "gates": {name: dict(value) for name, value in gates.items()},
        "report_ready": all(
            gates.get(name, {}).get("status") in {"passed", "not_applicable"}
            for name in (
                "source",
                "preparation",
                "reconciliation",
                "semantic_review",
                "reporting",
            )
        ),
    }
    return validate_gate_register(raw)


def _validated_locator(value: object, *, label: str) -> dict[str, str]:
    locator = _mapping(value, label=label)
    _exact_fields(
        locator,
        required={"artifact_ref", "locator", "value"},
        label=label,
    )
    return {
        "artifact_ref": _identifier(
            locator["artifact_ref"], label=f"{label}.artifact_ref"
        ),
        "locator": _text(locator["locator"], label=f"{label}.locator"),
        "value": _canonical_value(locator["value"], label=f"{label}.value"),
    }


def _canonical_value(value: object, *, label: str) -> str:
    try:
        parse_canonical_decimal(value, label=label)
    except MoneyValidationError as exc:
        raise AssuranceContractError(str(exc)) from exc
    return str(value)


def validate_numeric_evidence_ledger(value: object) -> dict[str, Any]:
    """Validate exact source-prepared-output numeric closure."""

    payload = _mapping(value, label="numeric evidence ledger")
    _exact_fields(
        payload,
        required={"schema_version", "ledger_id", "entries", "content_sha256"},
        label="numeric evidence ledger",
    )
    if payload["schema_version"] != "vera.numeric_evidence_ledger.v1":
        raise AssuranceContractError("unsupported numeric-evidence schema")
    ledger_id = _identifier(payload["ledger_id"], label="ledger_id")
    entries: list[dict[str, Any]] = []
    for index, raw_entry in enumerate(_sequence(payload["entries"], label="entries")):
        label = f"entries[{index}]"
        entry = _mapping(raw_entry, label=label)
        _exact_fields(
            entry,
            required={
                "evidence_id",
                "value",
                "unit",
                "currency",
                "source",
                "prepared",
                "outputs",
                "calculation_ref",
                "decision_ref",
                "limitations",
            },
            label=label,
        )
        value_text = _canonical_value(entry["value"], label=f"{label}.value")
        source = _validated_locator(entry["source"], label=f"{label}.source")
        if source["value"] != value_text:
            raise AssuranceContractError(
                f"{label}.source.value does not equal the ledger value"
            )
        prepared = _mapping(entry["prepared"], label=f"{label}.prepared")
        _exact_fields(
            prepared,
            required={"artifact_ref", "locator", "value"},
            label=f"{label}.prepared",
        )
        prepared_value = _canonical_value(
            prepared["value"], label=f"{label}.prepared.value"
        )
        if prepared_value != value_text:
            raise AssuranceContractError(
                f"{label}.prepared.value does not equal the ledger value"
            )
        outputs: list[dict[str, str]] = []
        for output_index, output_value in enumerate(
            _sequence(entry["outputs"], label=f"{label}.outputs")
        ):
            output_label = f"{label}.outputs[{output_index}]"
            output = _mapping(output_value, label=output_label)
            _exact_fields(
                output,
                required={"artifact_ref", "locator", "value"},
                label=output_label,
            )
            rendered_value = _canonical_value(
                output["value"], label=f"{output_label}.value"
            )
            if rendered_value != value_text:
                raise AssuranceContractError(
                    f"{output_label}.value does not equal the ledger value"
                )
            outputs.append(
                {
                    "artifact_ref": _identifier(
                        output["artifact_ref"],
                        label=f"{output_label}.artifact_ref",
                    ),
                    "locator": _text(
                        output["locator"], label=f"{output_label}.locator"
                    ),
                    "value": rendered_value,
                }
            )
        if not outputs:
            raise AssuranceContractError(f"{label}.outputs must be non-empty")
        calculation_ref = entry["calculation_ref"]
        if calculation_ref is not None:
            calculation_ref = _identifier(
                calculation_ref, label=f"{label}.calculation_ref"
            )
        decision_ref = entry["decision_ref"]
        if decision_ref is not None:
            decision_ref = _identifier(decision_ref, label=f"{label}.decision_ref")
        entries.append(
            {
                "evidence_id": _identifier(
                    entry["evidence_id"], label=f"{label}.evidence_id"
                ),
                "value": value_text,
                "unit": _text(entry["unit"], label=f"{label}.unit"),
                "currency": (
                    None
                    if entry["currency"] is None
                    else _text(entry["currency"], label=f"{label}.currency")
                ),
                "source": source,
                "prepared": {
                    "artifact_ref": _identifier(
                        prepared["artifact_ref"],
                        label=f"{label}.prepared.artifact_ref",
                    ),
                    "locator": _text(
                        prepared["locator"], label=f"{label}.prepared.locator"
                    ),
                    "value": prepared_value,
                },
                "outputs": outputs,
                "calculation_ref": calculation_ref,
                "decision_ref": decision_ref,
                "limitations": [
                    _text(item, label=f"{label}.limitations[{item_index}]")
                    for item_index, item in enumerate(
                        _sequence(entry["limitations"], label=f"{label}.limitations")
                    )
                ],
            }
        )
    ids = [entry["evidence_id"] for entry in entries]
    if not entries or len(ids) != len(set(ids)):
        raise AssuranceContractError(
            "numeric evidence IDs must be non-empty and unique"
        )
    content = {
        "schema_version": "vera.numeric_evidence_ledger.v1",
        "ledger_id": ledger_id,
        "entries": entries,
    }
    digest = _text(payload["content_sha256"], label="content_sha256")
    expected = canonical_json_sha256(content)
    if digest != expected:
        raise AssuranceContractError("numeric evidence content_sha256 is stale")
    return {**content, "content_sha256": expected}


def build_numeric_evidence_ledger(
    entries: Sequence[Mapping[str, Any]],
    *,
    ledger_id: str = "numeric_evidence",
) -> dict[str, Any]:
    """Build and seal a numeric evidence ledger."""

    content = {
        "schema_version": "vera.numeric_evidence_ledger.v1",
        "ledger_id": ledger_id,
        "entries": [dict(entry) for entry in entries],
    }
    return validate_numeric_evidence_ledger(
        {**content, "content_sha256": canonical_json_sha256(content)}
    )
