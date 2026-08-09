#!/usr/bin/env python3
"""Plan, review, apply, and roll back one client-folder organization run."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import stat
import sys
import tempfile
from collections import defaultdict
from collections.abc import Mapping, Sequence
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath
from typing import Any

__all__ = [
    "ArchiveOrganizationError",
    "apply_approved_plan",
    "build_review_package",
    "compile_approved_plan",
    "main",
    "persist_review_decisions",
    "rollback_applied_plan",
]

PLUGIN_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_POLICY_PATH = PLUGIN_ROOT / "references" / "default-archive-policy.json"
WORKFLOW_ID = "archive-organization"
SNAPSHOT_SCHEMA = "vera.archive_folder_snapshot.v1"
DRIVE_SNAPSHOT_SCHEMA = "vera.google_drive_folder_snapshot.v1"
POLICY_SCHEMA = "vera.archive_organization_policy.v1"
PROPOSAL_SCHEMA = "vera.archive_organization_proposals.v1"
PLAN_SCHEMA = "vera.archive_organization_plan.v1"
APPROVED_PLAN_SCHEMA = "vera.archive_organization_approved_plan.v1"
JOURNAL_SCHEMA = "vera.archive_organization_apply_journal.v1"
MAX_FILES = 5_000
MAX_TOTAL_BYTES = 2 * 1024 * 1024 * 1024
MAX_JSON_BYTES = 16 * 1024 * 1024
MAX_TEXT = 1_000
RESERVED_TOP_LEVEL = {"Vera"}
ALLOWED_CONFIDENCE = {"low", "medium", "high"}
ALLOWED_DECISIONS = {"accept", "reject", "edit", "mark_unclear", "skip"}
CHANGE_ACTIONS = {"move", "quarantine_exact_duplicate"}


class ArchiveOrganizationError(RuntimeError):
    """Raised when an archive-organization safety invariant is violated."""


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _canonical_bytes(value: object) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def _content_sha256(value: Mapping[str, Any], *, digest_key: str) -> str:
    content = {key: item for key, item in value.items() if key != digest_key}
    return hashlib.sha256(_canonical_bytes(content)).hexdigest()


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def _read_json(path: Path, *, label: str) -> dict[str, Any]:
    try:
        observed = path.lstat()
    except OSError as exc:
        raise ArchiveOrganizationError(f"{label} is unavailable: {exc}") from exc
    if path.is_symlink() or not stat.S_ISREG(observed.st_mode):
        raise ArchiveOrganizationError(f"{label} must be a regular non-symlink file.")
    if observed.st_size > MAX_JSON_BYTES:
        raise ArchiveOrganizationError(f"{label} exceeds the bounded JSON size.")
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ArchiveOrganizationError(
            f"{label} is not valid UTF-8 JSON: {exc}"
        ) from exc
    if not isinstance(payload, dict):
        raise ArchiveOrganizationError(f"{label} must contain a JSON object.")
    return payload


def _write_json(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{path.name}.", suffix=".tmp", dir=path.parent
    )
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, ensure_ascii=False, indent=2, sort_keys=True)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        if temporary.exists():
            temporary.unlink()


def _text(value: object, *, label: str, maximum: int = MAX_TEXT) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ArchiveOrganizationError(f"{label} must be a non-empty string.")
    normalized = value.strip()
    if len(normalized) > maximum or any(
        ord(character) < 32 for character in normalized
    ):
        raise ArchiveOrganizationError(f"{label} is invalid or too long.")
    return normalized


def _optional_text(value: object, *, label: str, maximum: int = 240) -> str | None:
    if value is None or value == "":
        return None
    return _text(value, label=label, maximum=maximum)


def _relative_path(value: object, *, label: str, allow_reserved: bool = False) -> str:
    text = _text(value, label=label, maximum=4096)
    if "\\" in text:
        raise ArchiveOrganizationError(f"{label} must use normalized POSIX separators.")
    path = PurePosixPath(text)
    if path.is_absolute() or path.as_posix() != text:
        raise ArchiveOrganizationError(f"{label} must be a normalized relative path.")
    if any(part in {"", ".", ".."} for part in path.parts):
        raise ArchiveOrganizationError(f"{label} escapes its client-folder boundary.")
    if not allow_reserved and path.parts[0] in RESERVED_TOP_LEVEL:
        raise ArchiveOrganizationError(
            f"{label} cannot target Vera's ledger directory."
        )
    return text


def _path_inside(root: Path, relative_path: str) -> Path:
    candidate = root.joinpath(*PurePosixPath(relative_path).parts)
    try:
        candidate.relative_to(root)
    except ValueError as exc:
        raise ArchiveOrganizationError(
            "Resolved path escapes the client folder."
        ) from exc
    return candidate


def _ordinary_source(path: Path, *, label: str) -> os.stat_result:
    try:
        observed = path.lstat()
    except OSError as exc:
        raise ArchiveOrganizationError(f"{label} is unavailable: {exc}") from exc
    if path.is_symlink() or not stat.S_ISREG(observed.st_mode):
        raise ArchiveOrganizationError(f"{label} must be a regular non-symlink file.")
    return observed


def _add_vendor_path() -> None:
    candidates = (
        PLUGIN_ROOT / "vendor" / "modules",
        PLUGIN_ROOT.parent / "_shared" / "vendor" / "modules",
    )
    for candidate in candidates:
        if (candidate / "vera_assurance").is_dir():
            if str(candidate) not in sys.path:
                sys.path.insert(0, str(candidate))
            return
    raise ArchiveOrganizationError("The required vera_assurance module is unavailable.")


def _load_context(path: Path) -> dict[str, Any]:
    _add_vendor_path()
    try:
        from vera_assurance import load_client_engagement_context_file

        context = load_client_engagement_context_file(
            path,
            expected_workflow_id=WORKFLOW_ID,
        )
    except (ImportError, OSError, ValueError, RuntimeError) as exc:
        raise ArchiveOrganizationError(
            f"Client engagement context is invalid: {exc}"
        ) from exc
    if "studio_client_folder" not in context or "input_bindings" not in context:
        raise ArchiveOrganizationError(
            "Client engagement context is not runtime-hydrated."
        )
    return context


def _load_snapshot(context: Mapping[str, Any]) -> dict[str, Any]:
    candidates: list[dict[str, Any]] = []
    for binding in context["input_bindings"]:
        path = Path(binding["path"])
        if path.suffix.lower() != ".json":
            continue
        payload = _read_json(path, label="workflow input")
        if payload.get("schema_version") in {SNAPSHOT_SCHEMA, DRIVE_SNAPSHOT_SCHEMA}:
            candidates.append(payload)
    if len(candidates) != 1:
        raise ArchiveOrganizationError(
            "The run must contain exactly one Studio Archive folder-snapshot input."
        )
    snapshot = candidates[0]
    if snapshot.get("schema_version") == DRIVE_SNAPSHOT_SCHEMA:
        return _validate_drive_snapshot(snapshot, context)
    required = {
        "schema_version",
        "client_id",
        "engagement_id",
        "captured_at",
        "file_count",
        "total_bytes",
        "files",
        "excluded",
        "content_sha256",
    }
    if set(snapshot) != required:
        raise ArchiveOrganizationError("Folder snapshot shape is invalid.")
    if (
        snapshot["client_id"] != context["client_id"]
        or snapshot["engagement_id"] != context["engagement_id"]
    ):
        raise ArchiveOrganizationError(
            "Folder snapshot belongs to another client or engagement."
        )
    files = snapshot["files"]
    if not isinstance(files, list) or len(files) > MAX_FILES:
        raise ArchiveOrganizationError("Folder snapshot has an invalid file list.")
    seen: set[str] = set()
    total_bytes = 0
    for index, item in enumerate(files):
        if not isinstance(item, dict) or set(item) != {
            "relative_path",
            "byte_count",
            "modified_ns",
            "sha256",
        }:
            raise ArchiveOrganizationError(f"Folder snapshot file {index} is invalid.")
        relative = _relative_path(item["relative_path"], label="snapshot relative_path")
        if relative in seen:
            raise ArchiveOrganizationError("Folder snapshot repeats a relative path.")
        seen.add(relative)
        if (
            not isinstance(item["byte_count"], int)
            or isinstance(item["byte_count"], bool)
            or item["byte_count"] < 0
            or not isinstance(item["modified_ns"], int)
            or item["modified_ns"] < 0
            or not isinstance(item["sha256"], str)
            or re.fullmatch(r"[0-9a-f]{64}", item["sha256"]) is None
        ):
            raise ArchiveOrganizationError("Folder snapshot byte identity is invalid.")
        total_bytes += item["byte_count"]
    excluded = snapshot["excluded"]
    if not isinstance(excluded, list) or len(excluded) > MAX_FILES:
        raise ArchiveOrganizationError("Folder snapshot exclusions are invalid.")
    for item in excluded:
        if not isinstance(item, dict) or set(item) != {"relative_path", "reason"}:
            raise ArchiveOrganizationError("Folder snapshot exclusion is invalid.")
        _relative_path(item["relative_path"], label="excluded relative_path")
        _text(item["reason"], label="exclusion reason", maximum=80)
    if len(files) != snapshot["file_count"] or total_bytes != snapshot["total_bytes"]:
        raise ArchiveOrganizationError("Folder snapshot totals are stale.")
    if total_bytes > MAX_TOTAL_BYTES:
        raise ArchiveOrganizationError(
            "Folder snapshot exceeds the 2 GB pilot boundary."
        )
    if snapshot["content_sha256"] != _content_sha256(
        snapshot, digest_key="content_sha256"
    ):
        raise ArchiveOrganizationError("Folder snapshot content digest is stale.")
    return snapshot


def _validate_drive_snapshot(
    snapshot: dict[str, Any], context: Mapping[str, Any]
) -> dict[str, Any]:
    required = {
        "schema_version",
        "client_id",
        "engagement_id",
        "root_folder_id",
        "root_name",
        "drive_id",
        "captured_at",
        "file_count",
        "folder_count",
        "known_total_bytes",
        "files",
        "excluded",
        "content_sha256",
    }
    if set(snapshot) != required:
        raise ArchiveOrganizationError("Google Drive snapshot shape is invalid.")
    if (
        snapshot["client_id"] != context["client_id"]
        or snapshot["engagement_id"] != context["engagement_id"]
    ):
        raise ArchiveOrganizationError(
            "Google Drive snapshot belongs to another client or engagement."
        )
    drive_id_pattern = re.compile(r"[A-Za-z0-9_-]{3,256}")
    if (
        not isinstance(snapshot["root_folder_id"], str)
        or drive_id_pattern.fullmatch(snapshot["root_folder_id"]) is None
        or not isinstance(snapshot["root_name"], str)
        or not snapshot["root_name"].strip()
        or (
            snapshot["drive_id"] is not None
            and (
                not isinstance(snapshot["drive_id"], str)
                or drive_id_pattern.fullmatch(snapshot["drive_id"]) is None
            )
        )
    ):
        raise ArchiveOrganizationError("Google Drive root identity is invalid.")
    files = snapshot["files"]
    if not isinstance(files, list) or len(files) > MAX_FILES:
        raise ArchiveOrganizationError("Google Drive snapshot files are invalid.")
    expected_fields = {
        "relative_path",
        "file_id",
        "parent_id",
        "name",
        "mime_type",
        "size_bytes",
        "modified_time",
        "version",
        "md5_checksum",
        "sha256_checksum",
        "drive_id",
        "capabilities",
    }
    seen_paths: set[str] = set()
    seen_ids: set[str] = set()
    known_total_bytes = 0
    for item in files:
        if not isinstance(item, dict) or set(item) != expected_fields:
            raise ArchiveOrganizationError("Google Drive snapshot file is invalid.")
        relative = _relative_path(
            item["relative_path"],
            label="Google Drive relative_path",
            allow_reserved=True,
        )
        if relative in seen_paths or item["file_id"] in seen_ids:
            raise ArchiveOrganizationError(
                "Google Drive snapshot repeats a path or file ID."
            )
        seen_paths.add(relative)
        seen_ids.add(item["file_id"])
        if any(
            not isinstance(item[key], str)
            or drive_id_pattern.fullmatch(item[key]) is None
            for key in ("file_id", "parent_id")
        ):
            raise ArchiveOrganizationError("Google Drive file identity is invalid.")
        if (
            not isinstance(item["name"], str)
            or not item["name"].strip()
            or not isinstance(item["mime_type"], str)
            or not item["mime_type"].strip()
            or not isinstance(item["modified_time"], str)
            or not item["modified_time"].strip()
            or not isinstance(item["version"], str)
            or not item["version"].isdigit()
        ):
            raise ArchiveOrganizationError("Google Drive metadata is invalid.")
        size = item["size_bytes"]
        if size is not None and (
            not isinstance(size, int) or isinstance(size, bool) or size < 0
        ):
            raise ArchiveOrganizationError("Google Drive file size is invalid.")
        known_total_bytes += size or 0
        for key, length in (("md5_checksum", 32), ("sha256_checksum", 64)):
            value = item[key]
            if value is not None and (
                not isinstance(value, str)
                or re.fullmatch(rf"[0-9a-f]{{{length}}}", value) is None
            ):
                raise ArchiveOrganizationError(
                    "Google Drive content checksum is invalid."
                )
        if item["drive_id"] != snapshot["drive_id"]:
            raise ArchiveOrganizationError(
                "Google Drive file belongs to another Shared Drive."
            )
        capabilities = item["capabilities"]
        if (
            not isinstance(capabilities, dict)
            or set(capabilities)
            != {
                "can_edit",
                "can_download",
                "can_move_within_drive",
            }
            or not all(isinstance(value, bool) for value in capabilities.values())
        ):
            raise ArchiveOrganizationError("Google Drive capabilities are invalid.")
    excluded = snapshot["excluded"]
    if not isinstance(excluded, list) or len(excluded) > MAX_FILES:
        raise ArchiveOrganizationError("Google Drive exclusions are invalid.")
    for item in excluded:
        if not isinstance(item, dict) or set(item) != {"relative_path", "reason"}:
            raise ArchiveOrganizationError("Google Drive exclusion is invalid.")
        _relative_path(
            item["relative_path"],
            label="Google Drive excluded relative_path",
            allow_reserved=True,
        )
        _text(item["reason"], label="Google Drive exclusion reason", maximum=80)
    if (
        snapshot["file_count"] != len(files)
        or snapshot["known_total_bytes"] != known_total_bytes
        or not isinstance(snapshot["folder_count"], int)
        or snapshot["folder_count"] < 1
        or known_total_bytes > MAX_TOTAL_BYTES
    ):
        raise ArchiveOrganizationError("Google Drive snapshot totals are invalid.")
    if snapshot["content_sha256"] != _content_sha256(
        snapshot, digest_key="content_sha256"
    ):
        raise ArchiveOrganizationError("Google Drive snapshot digest is stale.")
    return snapshot


def _load_policy(path: Path | None) -> dict[str, Any]:
    policy = _read_json(path or DEFAULT_POLICY_PATH, label="archive policy")
    required = {
        "schema_version",
        "policy_id",
        "version",
        "folder_template",
        "filename_template",
        "categories",
        "content_sha256",
    }
    if set(policy) != required or policy["schema_version"] != POLICY_SCHEMA:
        raise ArchiveOrganizationError("Archive policy shape is invalid.")
    categories = policy["categories"]
    if not isinstance(categories, list) or not categories:
        raise ArchiveOrganizationError("Archive policy must define categories.")
    seen_ids: set[str] = set()
    seen_folders: set[str] = set()
    for category in categories:
        if not isinstance(category, dict) or set(category) != {"id", "label", "folder"}:
            raise ArchiveOrganizationError("Archive policy category is invalid.")
        category_id = _text(category["id"], label="category id", maximum=80)
        folder = _relative_path(category["folder"], label="category folder")
        if category_id in seen_ids or folder.casefold() in seen_folders:
            raise ArchiveOrganizationError("Archive policy categories are not unique.")
        seen_ids.add(category_id)
        seen_folders.add(folder.casefold())
    _text(policy["folder_template"], label="folder_template", maximum=200)
    _text(policy["filename_template"], label="filename_template", maximum=200)
    if policy["content_sha256"] != _content_sha256(policy, digest_key="content_sha256"):
        raise ArchiveOrganizationError("Archive policy content digest is stale.")
    return policy


def _load_proposals(
    path: Path, snapshot: Mapping[str, Any], policy: Mapping[str, Any]
) -> dict[str, Any]:
    proposals = _read_json(path, label="semantic classification proposals")
    required = {"schema_version", "client_id", "snapshot_sha256", "proposals"}
    if set(proposals) != required or proposals["schema_version"] != PROPOSAL_SCHEMA:
        raise ArchiveOrganizationError("Semantic proposal shape is invalid.")
    if (
        proposals["client_id"] != snapshot["client_id"]
        or proposals["snapshot_sha256"] != snapshot["content_sha256"]
    ):
        raise ArchiveOrganizationError(
            "Semantic proposals are not bound to this snapshot."
        )
    rows = proposals["proposals"]
    if not isinstance(rows, list) or len(rows) != len(snapshot["files"]):
        raise ArchiveOrganizationError(
            "Semantic proposals must cover every snapshot file exactly once."
        )
    allowed_categories = {item["id"] for item in policy["categories"]}
    snapshot_paths = {item["relative_path"] for item in snapshot["files"]}
    proposal_paths: set[str] = set()
    normalized_rows: list[dict[str, Any]] = []
    drive_snapshot = snapshot["schema_version"] == DRIVE_SNAPSHOT_SCHEMA
    for index, row in enumerate(rows):
        if not isinstance(row, dict) or set(row) != {
            "relative_path",
            "category_id",
            "document_type",
            "document_date",
            "entity",
            "reference",
            "practice",
            "confidence",
            "reason",
            "probable_duplicate_of",
            "anomalies",
        }:
            raise ArchiveOrganizationError(f"Semantic proposal {index} is invalid.")
        relative = _relative_path(
            row["relative_path"],
            label="proposal relative_path",
            allow_reserved=drive_snapshot,
        )
        if relative in proposal_paths or relative not in snapshot_paths:
            raise ArchiveOrganizationError(
                "Semantic proposal path coverage is invalid."
            )
        proposal_paths.add(relative)
        category_id = row["category_id"]
        if category_id is not None and category_id not in allowed_categories:
            raise ArchiveOrganizationError(
                "Semantic proposal uses an unknown category."
            )
        confidence = _text(row["confidence"], label="proposal confidence", maximum=20)
        if confidence not in ALLOWED_CONFIDENCE:
            raise ArchiveOrganizationError("Semantic proposal confidence is invalid.")
        document_date = _optional_text(
            row["document_date"], label="document_date", maximum=10
        )
        if (
            document_date is not None
            and re.fullmatch(r"\d{4}(?:-\d{2}(?:-\d{2})?)?", document_date) is None
        ):
            raise ArchiveOrganizationError(
                "document_date must use YYYY, YYYY-MM, or YYYY-MM-DD."
            )
        duplicate = row["probable_duplicate_of"]
        if duplicate is not None:
            duplicate = _relative_path(duplicate, label="probable_duplicate_of")
            if duplicate not in snapshot_paths or duplicate == relative:
                raise ArchiveOrganizationError("probable_duplicate_of is invalid.")
        anomalies = row["anomalies"]
        if not isinstance(anomalies, list) or len(anomalies) > 20:
            raise ArchiveOrganizationError(
                "proposal anomalies must be a bounded array."
            )
        normalized_rows.append(
            {
                "relative_path": relative,
                "category_id": category_id,
                "document_type": _optional_text(
                    row["document_type"], label="document_type"
                ),
                "document_date": document_date,
                "entity": _optional_text(row["entity"], label="entity"),
                "reference": _optional_text(row["reference"], label="reference"),
                "practice": _optional_text(row["practice"], label="practice"),
                "confidence": confidence,
                "reason": _text(row["reason"], label="proposal reason", maximum=1_000),
                "probable_duplicate_of": duplicate,
                "anomalies": [
                    _text(value, label="anomaly", maximum=240) for value in anomalies
                ],
            }
        )
    return {**proposals, "proposals": normalized_rows}


def _safe_component(value: str) -> str:
    normalized = re.sub(r"[^\w.-]+", "-", value.strip(), flags=re.UNICODE)
    normalized = re.sub(r"[-_.]{2,}", "-", normalized).strip(" .-_")
    return normalized[:120] or "documento"


def _target_for(
    proposal: Mapping[str, Any],
    policy: Mapping[str, Any],
    source: str,
    *,
    source_name: str | None = None,
) -> str:
    if proposal["confidence"] == "low" or proposal["category_id"] in {
        None,
        "da-classificare",
    }:
        return source
    category = next(
        item for item in policy["categories"] if item["id"] == proposal["category_id"]
    )
    parts = [category["folder"]]
    if proposal["document_date"]:
        parts.append(proposal["document_date"][:4])
    if proposal["practice"]:
        parts.append(_safe_component(proposal["practice"]))
    source_path = PurePosixPath(source)
    original_name = source_name or source_path.name
    safe_original_name = original_name.replace("/", "-").replace("\x00", "").strip()
    safe_original_name = safe_original_name[:255] or "documento"
    if proposal["document_date"] and proposal["document_type"]:
        name_parts = [
            proposal["document_date"],
            proposal["document_type"],
            proposal["entity"],
            proposal["reference"],
        ]
        stem = "_".join(_safe_component(value) for value in name_parts if value)
        suffix = PurePosixPath(safe_original_name).suffix.lower()
        filename = f"{stem}{suffix}"
    else:
        filename = safe_original_name
    return PurePosixPath(*parts, filename).as_posix()


def _plan_item_id(relative_path: str) -> str:
    return "file." + hashlib.sha256(relative_path.encode("utf-8")).hexdigest()[:20]


def _storage_kind(snapshot: Mapping[str, Any]) -> str:
    return (
        "google_drive"
        if snapshot["schema_version"] == DRIVE_SNAPSHOT_SCHEMA
        else "local_filesystem"
    )


def _exact_duplicate_key(item: Mapping[str, Any], *, storage_kind: str) -> str | None:
    if storage_kind == "local_filesystem":
        return f"sha256:{item['sha256']}"
    if item["sha256_checksum"]:
        return f"sha256:{item['sha256_checksum']}"
    return None


def _source_identity(item: Mapping[str, Any], *, storage_kind: str) -> str:
    exact = _exact_duplicate_key(item, storage_kind=storage_kind)
    if exact is not None:
        return exact
    return f"drive-version:{item['file_id']}:{item['version']}"


def build_review_package(
    client_engagement: Path,
    proposals_path: Path,
    *,
    policy_path: Path | None = None,
) -> dict[str, Any]:
    """Write the dry-run plan and persistent review package for one exact run."""

    context = _load_context(client_engagement)
    snapshot = _load_snapshot(context)
    policy = _load_policy(policy_path)
    proposals = _load_proposals(proposals_path, snapshot, policy)
    output_dir = Path(context["output_dir"])
    output_dir.mkdir(parents=True, exist_ok=True)
    storage_kind = _storage_kind(snapshot)
    snapshot_by_path = {item["relative_path"]: item for item in snapshot["files"]}
    proposal_by_path = {item["relative_path"]: item for item in proposals["proposals"]}
    hash_groups: dict[str, list[str]] = defaultdict(list)
    for item in snapshot["files"]:
        duplicate_key = _exact_duplicate_key(item, storage_kind=storage_kind)
        if duplicate_key is not None:
            hash_groups[duplicate_key].append(item["relative_path"])
    duplicate_canonical: dict[str, str] = {}
    for paths in hash_groups.values():
        if len(paths) < 2:
            continue
        canonical = min(
            paths,
            key=lambda item: (len(PurePosixPath(item).parts), item.casefold(), item),
        )
        for path in paths:
            duplicate_canonical[path] = canonical

    items: list[dict[str, Any]] = []
    planned_targets: dict[str, list[str]] = defaultdict(list)
    for source in sorted(snapshot_by_path, key=lambda item: (item.casefold(), item)):
        proposal = proposal_by_path[source]
        canonical_duplicate = duplicate_canonical.get(source)
        if canonical_duplicate is not None and canonical_duplicate != source:
            target = PurePosixPath(
                "Da_verificare",
                "Duplicati_esatti",
                context["run_id"],
                source,
            ).as_posix()
            action = "quarantine_exact_duplicate"
        else:
            target = _target_for(
                proposal,
                policy,
                source,
                source_name=(
                    snapshot_by_path[source]["name"]
                    if storage_kind == "google_drive"
                    else None
                ),
            )
            action = "keep" if target == source else "move"
        target = _relative_path(
            target,
            label="planned target",
            allow_reserved=storage_kind == "google_drive" and target == source,
        )
        planned_targets[target.casefold()].append(source)
        items.append(
            {
                "item_id": _plan_item_id(source),
                "storage_kind": storage_kind,
                "source_relative_path": source,
                "source_identity": _source_identity(
                    snapshot_by_path[source], storage_kind=storage_kind
                ),
                "source_sha256": (
                    snapshot_by_path[source]["sha256"]
                    if storage_kind == "local_filesystem"
                    else snapshot_by_path[source]["sha256_checksum"]
                ),
                "byte_count": (
                    snapshot_by_path[source]["byte_count"]
                    if storage_kind == "local_filesystem"
                    else snapshot_by_path[source]["size_bytes"]
                ),
                "drive_file_id": (
                    snapshot_by_path[source]["file_id"]
                    if storage_kind == "google_drive"
                    else None
                ),
                "drive_parent_id": (
                    snapshot_by_path[source]["parent_id"]
                    if storage_kind == "google_drive"
                    else None
                ),
                "drive_name": (
                    snapshot_by_path[source]["name"]
                    if storage_kind == "google_drive"
                    else None
                ),
                "drive_version": (
                    snapshot_by_path[source]["version"]
                    if storage_kind == "google_drive"
                    else None
                ),
                "drive_md5_checksum": (
                    snapshot_by_path[source]["md5_checksum"]
                    if storage_kind == "google_drive"
                    else None
                ),
                "drive_sha256_checksum": (
                    snapshot_by_path[source]["sha256_checksum"]
                    if storage_kind == "google_drive"
                    else None
                ),
                "drive_mime_type": (
                    snapshot_by_path[source]["mime_type"]
                    if storage_kind == "google_drive"
                    else None
                ),
                "proposed_action": action,
                "target_relative_path": target,
                "exact_duplicate_of": (
                    canonical_duplicate if canonical_duplicate != source else None
                ),
                "probable_duplicate_of": proposal["probable_duplicate_of"],
                "category_id": proposal["category_id"],
                "confidence": proposal["confidence"],
                "reason": proposal["reason"],
                "anomalies": proposal["anomalies"],
                "blocked_reasons": [],
            }
        )

    existing_paths = {path.casefold(): path for path in snapshot_by_path}
    for item in items:
        if item["proposed_action"] == "keep":
            continue
        conflicts = planned_targets[item["target_relative_path"].casefold()]
        if len(conflicts) > 1:
            item["blocked_reasons"].append("target_collision_in_plan")
        existing = existing_paths.get(item["target_relative_path"].casefold())
        if existing is not None and existing != item["source_relative_path"]:
            item["blocked_reasons"].append("target_already_exists_in_snapshot")
        if item["blocked_reasons"]:
            item["proposed_action"] = "blocked"

    plan_content = {
        "schema_version": PLAN_SCHEMA,
        "workflow": WORKFLOW_ID,
        "client_id": context["client_id"],
        "engagement_id": context["engagement_id"],
        "run_id": context["run_id"],
        "storage_kind": storage_kind,
        "drive_root_folder_id": snapshot.get("root_folder_id"),
        "drive_id": snapshot.get("drive_id"),
        "created_at": _now_iso(),
        "snapshot_sha256": snapshot["content_sha256"],
        "policy_id": policy["policy_id"],
        "policy_version": policy["version"],
        "policy_sha256": policy["content_sha256"],
        "proposal_sha256": hashlib.sha256(_canonical_bytes(proposals)).hexdigest(),
        "dry_run": True,
        "items": items,
    }
    plan = {
        **plan_content,
        "content_sha256": hashlib.sha256(_canonical_bytes(plan_content)).hexdigest(),
    }
    review_items = []
    for item in items:
        allowed_actions = ["accept", "edit", "mark_unclear", "skip"]
        if item["proposed_action"] != "keep":
            allowed_actions.insert(1, "reject")
        recommended = (
            "mark_unclear" if item["proposed_action"] == "blocked" else "accept"
        )
        review_items.append(
            {
                "id": item["item_id"],
                "item_type": "archive_file_proposal",
                "title": item["source_relative_path"],
                "source_path": item["source_relative_path"],
                "output_path": item["target_relative_path"],
                "allowed_actions": allowed_actions,
                "recommended_action": recommended,
                "data": {
                    "source_path": item["source_relative_path"],
                    "storage_kind": item["storage_kind"],
                    "proposed_action": item["proposed_action"],
                    "target_path": item["target_relative_path"],
                    "category": item["category_id"],
                    "confidence": item["confidence"],
                    "exact_duplicate_of": item["exact_duplicate_of"],
                    "probable_duplicate_of": item["probable_duplicate_of"],
                    "anomalies": item["anomalies"],
                    "blocked_reasons": item["blocked_reasons"],
                    "target_artifact": "approved_plan.json",
                    "target_id_field": "item_id",
                    "target_record_id": item["item_id"],
                    "target_field": "target_relative_path",
                    "edit_hint": "Use a client-relative destination path. Apply will reject Vera/, absolute paths, traversal, collisions, symlinks, and overwrites.",
                },
                "evidence": [
                    {
                        "kind": "semantic_classification",
                        "reason": item["reason"],
                        "confidence": item["confidence"],
                    },
                    {
                        "kind": "deterministic_identity",
                        "identity": item["source_identity"],
                        "sha256": item["source_sha256"],
                        "byte_count": item["byte_count"],
                    },
                ],
            }
        )
    review_payload_content = {
        "schema_version": "1.0",
        "plugin": WORKFLOW_ID,
        "workflow": WORKFLOW_ID,
        "run_id": context["run_id"],
        "review_type": "archive_organization_review",
        "storage_kind": storage_kind,
        "source_paths": [item["source_relative_path"] for item in items],
        "columns": [
            "source_path",
            "proposed_action",
            "target_path",
            "category",
            "confidence",
            "exact_duplicate_of",
            "probable_duplicate_of",
            "anomalies",
        ],
        "source_artifacts": [
            "folder_snapshot.json",
            "policy_snapshot.json",
            "semantic_proposals.json",
            "archive_plan.json",
        ],
        "allowed_actions": sorted(ALLOWED_DECISIONS),
        "status": "pending_review",
        "item_count": len(review_items),
        "items": review_items,
        "summary": {
            "storage_kind": storage_kind,
            "file_count": len(items),
            "move_count": sum(item["proposed_action"] == "move" for item in items),
            "exact_duplicate_count": sum(
                item["exact_duplicate_of"] is not None for item in items
            ),
            "probable_duplicate_count": sum(
                item["probable_duplicate_of"] is not None for item in items
            ),
            "blocked_count": sum(bool(item["blocked_reasons"]) for item in items),
        },
    }
    review_payload = {
        **review_payload_content,
        "content_sha256": hashlib.sha256(
            _canonical_bytes(review_payload_content)
        ).hexdigest(),
    }
    ui_decisions = {
        "schema_version": "1.0",
        "plugin": WORKFLOW_ID,
        "workflow": WORKFLOW_ID,
        "run_id": context["run_id"],
        "review_payload_sha256": review_payload["content_sha256"],
        "status": "pending_review",
        "decided_at": None,
        "decision_source": "not_collected",
        "review_payload_path": "review_payload.json",
        "reviewer": None,
        "decision_count": 0,
        "decisions": [],
    }
    _write_json(output_dir / "folder_snapshot.json", snapshot)
    _write_json(output_dir / "policy_snapshot.json", policy)
    _write_json(output_dir / "semantic_proposals.json", proposals)
    _write_json(output_dir / "archive_plan.json", plan)
    _write_json(output_dir / "review_payload.json", review_payload)
    _write_json(output_dir / "ui_decisions.json", ui_decisions)
    _write_json(
        output_dir / "applied_decisions.json",
        {
            "schema_version": "1.0",
            "plugin": WORKFLOW_ID,
            "workflow": WORKFLOW_ID,
            "run_id": context["run_id"],
            "status": "pending_review",
            "applied_at": None,
            "approved_plan_path": None,
            "decisions": [],
        },
    )
    handoff = """# Review Handoff

Review `review_payload.json` in the shared workbench. Decisions persist to
`ui_decisions.json`; applying review decisions writes `applied_decisions.json`
and `approved_plan.json`, while `final_artifacts.json` tracks the package.

Use the tools in this order:

1. `validate_archive_organization_review`
2. `render_archive_organization_review`
3. `save_archive_organization_decisions`
4. `apply_archive_organization_decisions`

The fourth tool compiles the reviewed plan only. It does not move client files.
Local-filesystem or Google Drive API execution requires a separate explicit
approval and the workflow CLI `apply --explicit-approval`.
"""
    (output_dir / "review_handoff.md").write_text(handoff, encoding="utf-8")
    created_at = _now_iso()
    _write_json(
        output_dir / "run_intake.json",
        {
            "schema_version": "1.0",
            "plugin": WORKFLOW_ID,
            "workflow": WORKFLOW_ID,
            "created_at": created_at,
            "language": "it",
            "input_paths": [
                binding["execution_relative_path"]
                for binding in context["input_bindings"]
            ],
            "output_dir": str(output_dir),
            "inferred_task": "Screen and prepare a reviewable organization plan for one registered client folder.",
            "assumptions": {
                "dry_run_first": True,
                "storage_kind": storage_kind,
                "policy_id": policy["policy_id"],
                "policy_version": policy["version"],
            },
            "unresolved_questions": [],
            "dependency_check": "google_drive_dependencies_declared",
            "data_posture": {
                "local_files_read": ["registered_client_folder_snapshot"],
                "external_connectors_used": (
                    ["google-drive"] if storage_kind == "google_drive" else []
                ),
                "upload_paths_used": [],
                "external_routes_used": [],
                "remote_sql_execution_used": False,
                "hosted_notebook_execution_used": False,
            },
            "execution_trace": [
                {
                    "step_id": "prepare-review",
                    "kind": "deterministic_plan_compilation",
                    "command": ["archive_organization.py", "prepare-review"],
                    "execution_location": "local",
                    "inputs": [
                        "folder_snapshot.json",
                        "semantic_proposals.json",
                        "policy_snapshot.json",
                    ],
                    "outputs": [
                        "archive_plan.json",
                        "review_payload.json",
                        "ui_decisions.json",
                    ],
                    "status": "completed",
                }
            ],
        },
    )
    output_records = [
        {"path": "folder_snapshot.json", "kind": "json", "status": "written"},
        {"path": "policy_snapshot.json", "kind": "json", "status": "written"},
        {"path": "semantic_proposals.json", "kind": "json", "status": "written"},
        {"path": "archive_plan.json", "kind": "json", "status": "written"},
        {"path": "review_payload.json", "kind": "json", "status": "written"},
        {"path": "ui_decisions.json", "kind": "json", "status": "written"},
        {"path": "applied_decisions.json", "kind": "json", "status": "written"},
        {"path": "run_intake.json", "kind": "json", "status": "written"},
        {
            "path": "review_handoff.md",
            "kind": "md",
            "status": "written",
            "required_text": [
                "Review Handoff",
                "review_payload.json",
                "ui_decisions.json",
                "applied_decisions.json",
                "final_artifacts.json",
            ],
            "qa_checks": ["nonempty_text", "required_text"],
        },
    ]
    _write_json(
        output_dir / "final_artifacts.json",
        {
            "schema_version": "1.0",
            "plugin": WORKFLOW_ID,
            "workflow": WORKFLOW_ID,
            "run_id": context["run_id"],
            "outputs": output_records,
            "caveats": [
                "No client file has moved; execution requires reviewed decisions and a separate explicit approval.",
                *(
                    [
                        "Google Drive apply uses the restricted Drive OAuth scope and revalidates file ID, parent, name, version, and available checksums."
                    ]
                    if storage_kind == "google_drive"
                    else []
                ),
            ],
            "next_actions": [
                "Review every proposed change and persist collaborator decisions."
            ],
            "blockers": [],
            "status": "written_pending_review",
        },
    )
    return {
        "status": "pending_review",
        "output_dir": str(output_dir),
        "plan_path": str(output_dir / "archive_plan.json"),
        "review_payload_path": str(output_dir / "review_payload.json"),
        "ui_decisions_path": str(output_dir / "ui_decisions.json"),
        "summary": review_payload["summary"],
        "source_archive_mutated": False,
    }


def _validated_plan(path: Path, context: Mapping[str, Any]) -> dict[str, Any]:
    plan = _read_json(path, label="archive plan")
    if plan.get("schema_version") != PLAN_SCHEMA or plan.get("workflow") != WORKFLOW_ID:
        raise ArchiveOrganizationError("Archive plan identity is invalid.")
    if (
        plan.get("client_id") != context["client_id"]
        or plan.get("run_id") != context["run_id"]
    ):
        raise ArchiveOrganizationError("Archive plan belongs to another run.")
    if plan.get("content_sha256") != _content_sha256(plan, digest_key="content_sha256"):
        raise ArchiveOrganizationError("Archive plan content digest is stale.")
    if not isinstance(plan.get("items"), list) or len(plan["items"]) > MAX_FILES:
        raise ArchiveOrganizationError("Archive plan items are invalid.")
    return plan


def persist_review_decisions(
    client_engagement: Path,
    decisions_path: Path,
) -> dict[str, Any]:
    """Validate and persist reviewer decisions inside the exact run output."""

    context = _load_context(client_engagement)
    output_dir = Path(context["output_dir"])
    review_payload = _read_json(
        output_dir / "review_payload.json", label="review payload"
    )
    if (
        review_payload.get("plugin") != WORKFLOW_ID
        or review_payload.get("run_id") != context["run_id"]
        or review_payload.get("content_sha256")
        != _content_sha256(review_payload, digest_key="content_sha256")
    ):
        raise ArchiveOrganizationError("Review payload identity or digest is invalid.")
    incoming = _read_json(decisions_path, label="review decisions")
    reviewer = _text(incoming.get("reviewer"), label="reviewer", maximum=160)
    decision_source = _text(
        incoming.get("decision_source") or "mcp_widget",
        label="decision_source",
        maximum=80,
    )
    decisions = incoming.get("decisions")
    if not isinstance(decisions, list) or len(decisions) > len(review_payload["items"]):
        raise ArchiveOrganizationError("Review decisions must be a bounded array.")
    items = {item["id"]: item for item in review_payload["items"]}
    normalized: list[dict[str, Any]] = []
    seen: set[str] = set()
    for raw in decisions:
        if not isinstance(raw, dict):
            raise ArchiveOrganizationError("Review decision must be an object.")
        item_id = _text(raw.get("item_id"), label="decision item_id", maximum=120)
        action = _text(raw.get("action"), label="decision action", maximum=40)
        if item_id in seen or item_id not in items or action not in ALLOWED_DECISIONS:
            raise ArchiveOrganizationError(
                "Review decision identity or action is invalid."
            )
        if action not in items[item_id]["allowed_actions"]:
            raise ArchiveOrganizationError(
                "Review action is not allowed for this item."
            )
        edit_value = raw.get("edit_value")
        if action == "edit":
            edit_value = _relative_path(edit_value, label="edited target path")
        elif edit_value not in {None, ""}:
            raise ArchiveOrganizationError(
                "edit_value is allowed only for an edit decision."
            )
        normalized.append(
            {
                "item_id": item_id,
                "action": action,
                "reviewer_note": str(raw.get("reviewer_note") or "")[:1_000],
                "edit_value": edit_value or "",
                "requested_documents": [],
            }
        )
        seen.add(item_id)
    payload = {
        "schema_version": "1.0",
        "plugin": WORKFLOW_ID,
        "workflow": WORKFLOW_ID,
        "run_id": context["run_id"],
        "review_payload_sha256": review_payload["content_sha256"],
        "status": "reviewed",
        "decided_at": _now_iso(),
        "decision_source": decision_source,
        "review_payload_path": "review_payload.json",
        "reviewer": reviewer,
        "decision_count": len(normalized),
        "decisions": sorted(normalized, key=lambda item: item["item_id"]),
    }
    destination = output_dir / "ui_decisions.json"
    _write_json(destination, payload)
    return {
        "status": "reviewed",
        "ui_decisions_path": str(destination),
        "decision_count": len(normalized),
        "reviewer": reviewer,
        "source_archive_mutated": False,
    }


def compile_approved_plan(
    client_engagement: Path, decisions_path: Path
) -> dict[str, Any]:
    """Compile persistent reviewer decisions into an execution-ready plan."""

    context = _load_context(client_engagement)
    output_dir = Path(context["output_dir"])
    plan = _validated_plan(output_dir / "archive_plan.json", context)
    decisions_payload = _read_json(decisions_path, label="review decisions")
    review_payload = _read_json(
        output_dir / "review_payload.json", label="review payload"
    )
    if (
        decisions_payload.get("run_id") != context["run_id"]
        or decisions_payload.get("workflow") != WORKFLOW_ID
        or decisions_payload.get("status") != "reviewed"
        or decisions_payload.get("review_payload_sha256")
        != review_payload.get("content_sha256")
    ):
        raise ArchiveOrganizationError("Review decisions belong to another run.")
    decisions = decisions_payload.get("decisions")
    if not isinstance(decisions, list) or len(decisions) > MAX_FILES:
        raise ArchiveOrganizationError("Review decisions must be a bounded array.")
    by_id: dict[str, dict[str, Any]] = {}
    for decision in decisions:
        if not isinstance(decision, dict):
            raise ArchiveOrganizationError("Review decision is invalid.")
        item_id = _text(decision.get("item_id"), label="decision item_id", maximum=120)
        action = _text(decision.get("action"), label="decision action", maximum=40)
        if action not in ALLOWED_DECISIONS or item_id in by_id:
            raise ArchiveOrganizationError(
                "Review decision action or identity is invalid."
            )
        by_id[item_id] = decision
    reviewer = _text(decisions_payload.get("reviewer"), label="reviewer", maximum=160)
    approved_items: list[dict[str, Any]] = []
    for item in plan["items"]:
        decision = by_id.get(item["item_id"])
        if decision is None:
            if (
                item["proposed_action"] in CHANGE_ACTIONS
                or item["proposed_action"] == "blocked"
            ):
                raise ArchiveOrganizationError(
                    f"A reviewer decision is required for {item['source_relative_path']}."
                )
            action = "keep"
            target = item["source_relative_path"]
        elif decision["action"] == "accept":
            if item["proposed_action"] == "blocked":
                raise ArchiveOrganizationError(
                    "A blocked proposal cannot be accepted without an edited path."
                )
            action = item["proposed_action"]
            target = item["target_relative_path"]
        elif decision["action"] == "edit":
            target = _relative_path(
                decision.get("edit_value"), label="edited target path"
            )
            action = "keep" if target == item["source_relative_path"] else "move"
        else:
            action = "keep"
            target = item["source_relative_path"]
        approved_items.append(
            {
                **item,
                "approved_action": action,
                "approved_target_relative_path": target,
                "reviewer_action": decision["action"] if decision else "implicit_keep",
                "reviewer_note": (
                    str(decision.get("reviewer_note") or "") if decision else ""
                ),
            }
        )
    moving = [
        item for item in approved_items if item["approved_action"] in CHANGE_ACTIONS
    ]
    target_keys: set[str] = set()
    source_keys = {item["source_relative_path"].casefold() for item in approved_items}
    for item in moving:
        target = _relative_path(
            item["approved_target_relative_path"], label="approved target"
        )
        key = target.casefold()
        if key in target_keys:
            raise ArchiveOrganizationError("Approved plan contains a target collision.")
        if key in source_keys and key != item["source_relative_path"].casefold():
            raise ArchiveOrganizationError(
                "Approved target is occupied by another snapshot file."
            )
        target_keys.add(key)
    content = {
        "schema_version": APPROVED_PLAN_SCHEMA,
        "workflow": WORKFLOW_ID,
        "client_id": context["client_id"],
        "engagement_id": context["engagement_id"],
        "run_id": context["run_id"],
        "storage_kind": plan["storage_kind"],
        "drive_root_folder_id": plan["drive_root_folder_id"],
        "drive_id": plan["drive_id"],
        "approved_at": _now_iso(),
        "approved_by": reviewer,
        "archive_plan_sha256": plan["content_sha256"],
        "decisions_sha256": hashlib.sha256(
            _canonical_bytes(decisions_payload)
        ).hexdigest(),
        "items": approved_items,
    }
    approved = {
        **content,
        "content_sha256": hashlib.sha256(_canonical_bytes(content)).hexdigest(),
    }
    approved_path = output_dir / "approved_plan.json"
    _write_json(approved_path, approved)
    _write_json(
        output_dir / "applied_decisions.json",
        {
            "schema_version": "1.0",
            "plugin": WORKFLOW_ID,
            "workflow": WORKFLOW_ID,
            "run_id": context["run_id"],
            "status": "reviewed",
            "applied_at": _now_iso(),
            "approved_plan_path": "approved_plan.json",
            "decisions": approved_items,
        },
    )
    final_artifacts_path = output_dir / "final_artifacts.json"
    final_artifacts = _read_json(final_artifacts_path, label="final artifacts")
    if not any(
        item.get("path") == "approved_plan.json" for item in final_artifacts["outputs"]
    ):
        final_artifacts["outputs"].append(
            {"path": "approved_plan.json", "kind": "json", "status": "written_reviewed"}
        )
    final_artifacts["status"] = "ready_for_review"
    final_artifacts["next_actions"] = [
        "Summarize the approved changes and obtain a separate explicit storage apply approval."
    ]
    _write_json(final_artifacts_path, final_artifacts)
    return {
        "status": "ready_to_apply",
        "approved_plan_path": str(approved_path),
        "approved_change_count": len(moving),
        "reviewer": reviewer,
        "source_archive_mutated": False,
    }


def _copy_exclusive_then_unlink(
    root: Path,
    source: Path,
    target: Path,
    expected_sha256: str,
) -> None:
    _ordinary_source(source, label="approved source")
    try:
        relative_parent = target.parent.relative_to(root)
    except ValueError as exc:
        raise ArchiveOrganizationError(
            "Approved target escapes the client folder."
        ) from exc
    parent = root
    for part in relative_parent.parts:
        parent /= part
        if parent.exists():
            if parent.is_symlink() or not parent.is_dir():
                raise ArchiveOrganizationError(
                    "Approved target parent is linked or not a directory."
                )
        else:
            parent.mkdir(mode=0o700)
    source_handle = source.open("rb")
    descriptor: int | None = None
    try:
        descriptor = os.open(target, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        digest = hashlib.sha256()
        with os.fdopen(descriptor, "wb") as target_handle:
            descriptor = None
            while chunk := source_handle.read(1024 * 1024):
                target_handle.write(chunk)
                digest.update(chunk)
            target_handle.flush()
            os.fsync(target_handle.fileno())
        if digest.hexdigest() != expected_sha256:
            target.unlink(missing_ok=True)
            raise ArchiveOrganizationError(
                "Copied target does not match the approved source hash."
            )
        shutil.copystat(source, target, follow_symlinks=False)
        if _sha256_file(target) != expected_sha256:
            target.unlink(missing_ok=True)
            raise ArchiveOrganizationError("Target hash changed before source removal.")
        source.unlink()
    except FileExistsError as exc:
        raise ArchiveOrganizationError(
            "Approved target already exists; nothing was overwritten."
        ) from exc
    finally:
        source_handle.close()
        if descriptor is not None:
            os.close(descriptor)


def _validated_approved(path: Path, context: Mapping[str, Any]) -> dict[str, Any]:
    approved = _read_json(path, label="approved plan")
    if (
        approved.get("schema_version") != APPROVED_PLAN_SCHEMA
        or approved.get("workflow") != WORKFLOW_ID
    ):
        raise ArchiveOrganizationError("Approved plan identity is invalid.")
    if (
        approved.get("client_id") != context["client_id"]
        or approved.get("run_id") != context["run_id"]
    ):
        raise ArchiveOrganizationError("Approved plan belongs to another run.")
    if approved.get("content_sha256") != _content_sha256(
        approved, digest_key="content_sha256"
    ):
        raise ArchiveOrganizationError("Approved plan content digest is stale.")
    output_dir = Path(context["output_dir"])
    plan = _validated_plan(output_dir / "archive_plan.json", context)
    decisions = _read_json(
        output_dir / "ui_decisions.json", label="persisted review decisions"
    )
    if (
        approved.get("archive_plan_sha256") != plan["content_sha256"]
        or approved.get("decisions_sha256")
        != hashlib.sha256(_canonical_bytes(decisions)).hexdigest()
        or approved.get("storage_kind") != plan.get("storage_kind")
        or approved.get("drive_root_folder_id") != plan.get("drive_root_folder_id")
        or approved.get("drive_id") != plan.get("drive_id")
    ):
        raise ArchiveOrganizationError(
            "Approved plan is not bound to the current plan and review decisions."
        )
    approved_items = approved.get("items")
    if not isinstance(approved_items, list) or len(approved_items) != len(
        plan["items"]
    ):
        raise ArchiveOrganizationError("Approved plan item coverage is invalid.")
    persisted_decisions = decisions.get("decisions")
    if not isinstance(persisted_decisions, list):
        raise ArchiveOrganizationError("Persisted review decisions are invalid.")
    planned_by_id = {item["item_id"]: item for item in plan["items"]}
    decisions_by_id = {
        item["item_id"]: item
        for item in persisted_decisions
        if isinstance(item, dict) and isinstance(item.get("item_id"), str)
    }
    if len(planned_by_id) != len(plan["items"]) or len(decisions_by_id) != len(
        persisted_decisions
    ):
        raise ArchiveOrganizationError("Approved plan sources are invalid.")
    seen: set[str] = set()
    for item in approved_items:
        if not isinstance(item, dict):
            raise ArchiveOrganizationError("Approved plan item is invalid.")
        item_id = item.get("item_id")
        planned = planned_by_id.get(item_id)
        if (
            planned is None
            or item_id in seen
            or any(item.get(key) != value for key, value in planned.items())
        ):
            raise ArchiveOrganizationError(
                "Approved plan source identity differs from the reviewed plan."
            )
        seen.add(str(item_id))
        decision = decisions_by_id.get(item_id)
        if decision is None:
            expected_reviewer_action = "implicit_keep"
            expected_action = "keep"
            expected_target = planned["source_relative_path"]
        elif decision["action"] == "accept":
            expected_reviewer_action = "accept"
            expected_action = planned["proposed_action"]
            expected_target = planned["target_relative_path"]
        elif decision["action"] == "edit":
            expected_reviewer_action = "edit"
            expected_target = decision["edit_value"]
            expected_action = (
                "keep" if expected_target == planned["source_relative_path"] else "move"
            )
        else:
            expected_reviewer_action = decision["action"]
            expected_action = "keep"
            expected_target = planned["source_relative_path"]
        if (
            item.get("reviewer_action") != expected_reviewer_action
            or item.get("approved_action") != expected_action
            or item.get("approved_target_relative_path") != expected_target
        ):
            raise ArchiveOrganizationError(
                "Approved plan action differs from persisted review decisions."
            )
    return approved


def _google_drive_module() -> Any:
    candidates = (
        PLUGIN_ROOT.parent / "studio-archive" / "scripts",
        PLUGIN_ROOT.parent / "modules" / "studio-archive" / "scripts",
    )
    for candidate in candidates:
        if (candidate / "google_drive.py").is_file():
            if str(candidate) not in sys.path:
                sys.path.insert(0, str(candidate))
            try:
                import google_drive
            except ModuleNotFoundError as exc:
                raise ArchiveOrganizationError(
                    "The Studio Archive Google Drive adapter is unavailable."
                ) from exc
            return google_drive
    raise ArchiveOrganizationError(
        "Install Studio Archive with its Google Drive adapter before Drive apply."
    )


def _drive_unique_named_child(
    drive_module: Any,
    gateway: Any,
    parent_id: str,
    name: str,
) -> dict[str, Any] | None:
    matches = [
        item
        for item in gateway.list_children(parent_id)
        if item.get("name") == name and item.get("trashed") is not True
    ]
    if len(matches) > 1:
        raise ArchiveOrganizationError(
            f"Google Drive contains duplicate target names under one folder: {name}."
        )
    if not matches:
        return None
    return matches[0]


def _drive_source_state(
    drive_module: Any,
    gateway: Any,
    item: Mapping[str, Any],
    *,
    parent_id: str | None = None,
) -> dict[str, Any]:
    selected_parent = parent_id or item["drive_parent_id"]
    raw = gateway.get_file(item["drive_file_id"])
    state = drive_module.normalize_file_metadata(raw, selected_parent)
    expected = {
        "file_id": item["drive_file_id"],
        "parent_id": selected_parent,
        "name": item["drive_name"],
        "mime_type": item["drive_mime_type"],
        "version": item["drive_version"],
        "md5_checksum": item["drive_md5_checksum"],
        "sha256_checksum": item["drive_sha256_checksum"],
    }
    for key, value in expected.items():
        if state[key] != value:
            raise ArchiveOrganizationError(
                f"Google Drive source changed after review: {item['source_relative_path']}."
            )
    if (
        not state["capabilities"]["can_edit"]
        or not state["capabilities"]["can_move_within_drive"]
    ):
        raise ArchiveOrganizationError(
            f"Google Drive source cannot be moved: {item['source_relative_path']}."
        )
    return state


def _drive_existing_target_parent(
    drive_module: Any,
    gateway: Any,
    root_folder_id: str,
    folder_parts: Sequence[str],
) -> str | None:
    parent_id = root_folder_id
    for name in folder_parts:
        child = _drive_unique_named_child(drive_module, gateway, parent_id, name)
        if child is None:
            return None
        if child.get("mimeType") != drive_module.DRIVE_FOLDER_MIME_TYPE:
            raise ArchiveOrganizationError(
                f"Google Drive target folder is occupied by a file: {name}."
            )
        parent_id = str(child["id"])
    return parent_id


def _drive_ensure_target_parent(
    drive_module: Any,
    gateway: Any,
    root_folder_id: str,
    folder_parts: Sequence[str],
    created_folders: list[dict[str, Any]],
) -> str:
    parent_id = root_folder_id
    for name in folder_parts:
        child = _drive_unique_named_child(drive_module, gateway, parent_id, name)
        if child is None:
            child = gateway.create_folder(parent_id, name)
            normalized = drive_module.normalize_file_metadata(child, parent_id)
            if normalized["mime_type"] != drive_module.DRIVE_FOLDER_MIME_TYPE:
                raise ArchiveOrganizationError(
                    "Google Drive did not create the requested target folder."
                )
            created_folders.append(
                {
                    "folder_id": normalized["file_id"],
                    "parent_id": parent_id,
                    "name": name,
                    "status": "created_left_in_place",
                }
            )
            child = _drive_unique_named_child(drive_module, gateway, parent_id, name)
            if child is None or child.get("id") != normalized["file_id"]:
                raise ArchiveOrganizationError(
                    "Google Drive target folder collided during creation."
                )
        elif child.get("mimeType") != drive_module.DRIVE_FOLDER_MIME_TYPE:
            raise ArchiveOrganizationError(
                f"Google Drive target folder is occupied by a file: {name}."
            )
        parent_id = str(child["id"])
    return parent_id


def _rollback_drive_operations(
    drive_module: Any,
    gateway: Any,
    journal: dict[str, Any],
    journal_path: Path,
) -> list[str]:
    errors: list[str] = []
    for operation in reversed(journal["operations"]):
        if operation["status"] != "applied":
            continue
        try:
            raw = gateway.get_file(operation["file_id"])
            current = drive_module.normalize_file_metadata(
                raw, operation["target_parent_id"]
            )
            if (
                current["name"] != operation["target_name"]
                or current["version"] != operation["applied_version"]
            ):
                raise ArchiveOrganizationError(
                    "A moved Google Drive file changed before rollback."
                )
            occupied = _drive_unique_named_child(
                drive_module,
                gateway,
                operation["source_parent_id"],
                operation["source_name"],
            )
            if occupied is not None:
                raise ArchiveOrganizationError(
                    "The original Google Drive path is no longer empty."
                )
            restored = gateway.move_file(
                operation["file_id"],
                old_parent_id=operation["target_parent_id"],
                new_parent_id=operation["source_parent_id"],
                new_name=operation["source_name"],
            )
            restored_state = drive_module.normalize_file_metadata(
                restored, operation["source_parent_id"]
            )
            operation["status"] = "rolled_back"
            operation["rolled_back_version"] = restored_state["version"]
        except (ArchiveOrganizationError, OSError, drive_module.DriveError) as exc:
            errors.append(str(exc))
        _write_json(journal_path, journal)
    return errors


def _apply_google_drive_plan(
    context: Mapping[str, Any],
    approved: Mapping[str, Any],
    *,
    gateway: Any | None,
) -> dict[str, Any]:
    drive_module = _google_drive_module()
    selected_gateway = gateway or drive_module.load_google_drive_gateway()
    output_dir = Path(context["output_dir"])
    root_folder_id = approved.get("drive_root_folder_id")
    if not isinstance(root_folder_id, str):
        raise ArchiveOrganizationError("Approved Google Drive root is invalid.")
    actions = [
        item for item in approved["items"] if item["approved_action"] in CHANGE_ACTIONS
    ]
    for item in actions:
        _drive_source_state(drive_module, selected_gateway, item)
        target = PurePosixPath(
            _relative_path(
                item["approved_target_relative_path"], label="approved Drive target"
            )
        )
        parent_id = _drive_existing_target_parent(
            drive_module,
            selected_gateway,
            root_folder_id,
            target.parts[:-1],
        )
        if (
            parent_id is not None
            and _drive_unique_named_child(
                drive_module, selected_gateway, parent_id, target.name
            )
            is not None
        ):
            raise ArchiveOrganizationError(
                f"Approved Google Drive target already exists: {target.as_posix()}."
            )
    lock_path = output_dir / "archive_apply.lock"
    try:
        lock_descriptor = os.open(
            lock_path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600
        )
    except FileExistsError as exc:
        raise ArchiveOrganizationError(
            "Another apply or rollback operation is active."
        ) from exc
    os.close(lock_descriptor)
    journal_path = output_dir / "apply_journal.json"
    journal: dict[str, Any] = {
        "schema_version": JOURNAL_SCHEMA,
        "workflow": WORKFLOW_ID,
        "storage_kind": "google_drive",
        "external_service": "google-drive",
        "client_id": context["client_id"],
        "engagement_id": context["engagement_id"],
        "run_id": context["run_id"],
        "approved_plan_sha256": approved["content_sha256"],
        "drive_root_folder_id": root_folder_id,
        "drive_id": approved.get("drive_id"),
        "status": "applying",
        "started_at": _now_iso(),
        "completed_at": None,
        "created_folders": [],
        "operations": [
            {
                "item_id": item["item_id"],
                "file_id": item["drive_file_id"],
                "source_relative_path": item["source_relative_path"],
                "source_parent_id": item["drive_parent_id"],
                "source_name": item["drive_name"],
                "source_version": item["drive_version"],
                "target_relative_path": item["approved_target_relative_path"],
                "target_parent_id": None,
                "target_name": PurePosixPath(
                    item["approved_target_relative_path"]
                ).name,
                "applied_version": None,
                "status": "pending",
            }
            for item in actions
        ],
    }
    _write_json(journal_path, journal)
    try:
        action_by_id = {item["item_id"]: item for item in actions}
        for operation in journal["operations"]:
            item = action_by_id[operation["item_id"]]
            _drive_source_state(drive_module, selected_gateway, item)
            target = PurePosixPath(operation["target_relative_path"])
            target_parent = _drive_ensure_target_parent(
                drive_module,
                selected_gateway,
                root_folder_id,
                target.parts[:-1],
                journal["created_folders"],
            )
            operation["target_parent_id"] = target_parent
            if (
                _drive_unique_named_child(
                    drive_module, selected_gateway, target_parent, target.name
                )
                is not None
            ):
                raise ArchiveOrganizationError(
                    f"Approved Google Drive target already exists: {target.as_posix()}."
                )
            moved = selected_gateway.move_file(
                operation["file_id"],
                old_parent_id=operation["source_parent_id"],
                new_parent_id=target_parent,
                new_name=target.name,
            )
            operation["status"] = "applied"
            operation["applied_version"] = str(moved.get("version") or "")
            _write_json(journal_path, journal)
            moved_state = drive_module.normalize_file_metadata(moved, target_parent)
            if (
                moved_state["file_id"] != operation["file_id"]
                or moved_state["name"] != target.name
                or moved_state["drive_id"] != approved.get("drive_id")
            ):
                raise ArchiveOrganizationError(
                    "Google Drive move did not produce the approved identity."
                )
            matches = [
                child
                for child in selected_gateway.list_children(target_parent)
                if child.get("name") == target.name
            ]
            if len(matches) != 1 or matches[0].get("id") != operation["file_id"]:
                raise ArchiveOrganizationError(
                    "Google Drive target collided during apply."
                )
            operation["applied_version"] = moved_state["version"]
            _write_json(journal_path, journal)
        journal["status"] = "applied"
        journal["completed_at"] = _now_iso()
        _write_json(journal_path, journal)
    except (ArchiveOrganizationError, OSError, drive_module.DriveError) as exc:
        journal["status"] = "apply_failed"
        journal["failure"] = str(exc)
        _write_json(journal_path, journal)
        rollback_errors = _rollback_drive_operations(
            drive_module, selected_gateway, journal, journal_path
        )
        journal["status"] = (
            "partial_failure" if rollback_errors else "rolled_back_after_failure"
        )
        journal["rollback_errors"] = rollback_errors
        journal["completed_at"] = _now_iso()
        _write_json(journal_path, journal)
        raise ArchiveOrganizationError(
            "Google Drive apply failed; "
            + (
                "manual recovery is required."
                if rollback_errors
                else "all moved files were rolled back."
            )
        ) from exc
    finally:
        lock_path.unlink(missing_ok=True)
    return {
        "status": "applied",
        "storage_kind": "google_drive",
        "applied_count": len(actions),
        "journal_path": str(journal_path),
        "rollback_available": bool(actions),
        "remote_archive_mutated": bool(actions),
        "created_folders_left_in_place": len(journal["created_folders"]),
    }


def apply_approved_plan(
    client_engagement: Path,
    approved_plan_path: Path,
    *,
    explicit_approval: bool,
    drive_gateway: Any | None = None,
) -> dict[str, Any]:
    """Apply only explicitly approved moves with no overwrite and a durable journal."""

    if not explicit_approval:
        raise ArchiveOrganizationError("Explicit apply approval is required.")
    context = _load_context(client_engagement)
    approved = _validated_approved(approved_plan_path, context)
    if approved.get("storage_kind") == "google_drive":
        return _apply_google_drive_plan(
            context,
            approved,
            gateway=drive_gateway,
        )
    if approved.get("storage_kind") != "local_filesystem":
        raise ArchiveOrganizationError("Approved storage kind is unsupported.")
    root = Path(context["studio_client_folder"]["client_root"])
    output_dir = Path(context["output_dir"])
    actions = [
        item for item in approved["items"] if item["approved_action"] in CHANGE_ACTIONS
    ]
    for item in actions:
        source = _path_inside(root, item["source_relative_path"])
        target = _path_inside(
            root,
            _relative_path(
                item["approved_target_relative_path"], label="approved target"
            ),
        )
        _ordinary_source(source, label="approved source")
        if _sha256_file(source) != item["source_sha256"]:
            raise ArchiveOrganizationError(
                f"Source changed after review: {item['source_relative_path']}."
            )
        if target.exists() or target.is_symlink():
            raise ArchiveOrganizationError(
                f"Approved target already exists: {item['approved_target_relative_path']}."
            )
        cursor = target.parent
        while cursor != root:
            if cursor.exists() and cursor.is_symlink():
                raise ArchiveOrganizationError(
                    "Approved target path contains a symbolic link."
                )
            cursor = cursor.parent
    lock_path = output_dir / "archive_apply.lock"
    try:
        lock_descriptor = os.open(
            lock_path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600
        )
    except FileExistsError as exc:
        raise ArchiveOrganizationError(
            "Another apply or rollback operation is active."
        ) from exc
    os.close(lock_descriptor)
    journal_path = output_dir / "apply_journal.json"
    journal: dict[str, Any] = {
        "schema_version": JOURNAL_SCHEMA,
        "workflow": WORKFLOW_ID,
        "storage_kind": "local_filesystem",
        "client_id": context["client_id"],
        "engagement_id": context["engagement_id"],
        "run_id": context["run_id"],
        "approved_plan_sha256": approved["content_sha256"],
        "status": "applying",
        "started_at": _now_iso(),
        "completed_at": None,
        "operations": [
            {
                "item_id": item["item_id"],
                "source_relative_path": item["source_relative_path"],
                "target_relative_path": item["approved_target_relative_path"],
                "sha256": item["source_sha256"],
                "status": "pending",
            }
            for item in actions
        ],
    }
    _write_json(journal_path, journal)
    try:
        for operation in journal["operations"]:
            source = _path_inside(root, operation["source_relative_path"])
            target = _path_inside(root, operation["target_relative_path"])
            _copy_exclusive_then_unlink(root, source, target, operation["sha256"])
            operation["status"] = "applied"
            _write_json(journal_path, journal)
        journal["status"] = "applied"
        journal["completed_at"] = _now_iso()
        _write_json(journal_path, journal)
    except (ArchiveOrganizationError, OSError) as exc:
        journal["status"] = "apply_failed"
        journal["failure"] = str(exc)
        _write_json(journal_path, journal)
        rollback_errors: list[str] = []
        for operation in reversed(journal["operations"]):
            if operation["status"] != "applied":
                continue
            try:
                _copy_exclusive_then_unlink(
                    root,
                    _path_inside(root, operation["target_relative_path"]),
                    _path_inside(root, operation["source_relative_path"]),
                    operation["sha256"],
                )
                operation["status"] = "rolled_back"
            except (ArchiveOrganizationError, OSError) as rollback_exc:
                rollback_errors.append(str(rollback_exc))
            _write_json(journal_path, journal)
        journal["status"] = (
            "partial_failure" if rollback_errors else "rolled_back_after_failure"
        )
        journal["rollback_errors"] = rollback_errors
        journal["completed_at"] = _now_iso()
        _write_json(journal_path, journal)
        raise ArchiveOrganizationError(
            "Apply failed; "
            + (
                "manual rollback is required."
                if rollback_errors
                else "all applied operations were rolled back."
            )
        ) from exc
    finally:
        lock_path.unlink(missing_ok=True)
    return {
        "status": "applied",
        "applied_count": len(actions),
        "journal_path": str(journal_path),
        "rollback_available": bool(actions),
        "source_archive_mutated": bool(actions),
    }


def rollback_applied_plan(
    client_engagement: Path,
    *,
    drive_gateway: Any | None = None,
) -> dict[str, Any]:
    """Reverse a fully applied journal when every destination still matches."""

    context = _load_context(client_engagement)
    root = Path(context["studio_client_folder"]["client_root"])
    journal_path = Path(context["output_dir"]) / "apply_journal.json"
    journal = _read_json(journal_path, label="apply journal")
    if (
        journal.get("schema_version") != JOURNAL_SCHEMA
        or journal.get("run_id") != context["run_id"]
    ):
        raise ArchiveOrganizationError("Apply journal belongs to another run.")
    if journal.get("storage_kind") == "google_drive":
        drive_module = _google_drive_module()
        selected_gateway = drive_gateway or drive_module.load_google_drive_gateway()
        if journal.get("status") != "applied":
            raise ArchiveOrganizationError(
                "Only a fully applied journal can be rolled back."
            )
        errors = _rollback_drive_operations(
            drive_module, selected_gateway, journal, journal_path
        )
        if errors:
            journal["status"] = "partial_failure"
            journal["rollback_errors"] = errors
            journal["completed_at"] = _now_iso()
            _write_json(journal_path, journal)
            raise ArchiveOrganizationError(
                "Google Drive rollback requires manual recovery."
            )
        journal["status"] = "rolled_back"
        journal["completed_at"] = _now_iso()
        _write_json(journal_path, journal)
        return {
            "status": "rolled_back",
            "storage_kind": "google_drive",
            "rolled_back_count": len(journal["operations"]),
            "journal_path": str(journal_path),
            "remote_archive_mutated": bool(journal["operations"]),
            "created_folders_left_in_place": len(journal["created_folders"]),
        }
    if journal.get("storage_kind") != "local_filesystem":
        raise ArchiveOrganizationError("Apply journal storage kind is unsupported.")
    if journal.get("status") != "applied":
        raise ArchiveOrganizationError(
            "Only a fully applied journal can be rolled back."
        )
    for operation in reversed(journal["operations"]):
        source = _path_inside(root, operation["source_relative_path"])
        target = _path_inside(root, operation["target_relative_path"])
        if source.exists() or source.is_symlink():
            raise ArchiveOrganizationError("Rollback source path is no longer empty.")
        _ordinary_source(target, label="rollback target")
        if _sha256_file(target) != operation["sha256"]:
            raise ArchiveOrganizationError("Rollback target changed after apply.")
    for operation in reversed(journal["operations"]):
        _copy_exclusive_then_unlink(
            root,
            _path_inside(root, operation["target_relative_path"]),
            _path_inside(root, operation["source_relative_path"]),
            operation["sha256"],
        )
        operation["status"] = "rolled_back"
        _write_json(journal_path, journal)
    journal["status"] = "rolled_back"
    journal["completed_at"] = _now_iso()
    _write_json(journal_path, journal)
    return {
        "status": "rolled_back",
        "rolled_back_count": len(journal["operations"]),
        "journal_path": str(journal_path),
        "source_archive_mutated": bool(journal["operations"]),
    }


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    managed_context = argparse.ArgumentParser(add_help=False)
    managed_context.add_argument("--client-engagement", type=Path, required=True)
    subparsers = parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser("preflight", parents=[managed_context])
    prepare = subparsers.add_parser("prepare-review", parents=[managed_context])
    prepare.add_argument("--proposals", type=Path, required=True)
    prepare.add_argument("--policy", type=Path)
    approve = subparsers.add_parser("approve", parents=[managed_context])
    approve.add_argument("--decisions", type=Path, required=True)
    save = subparsers.add_parser("save-decisions", parents=[managed_context])
    save.add_argument("--decisions", type=Path, required=True)
    apply = subparsers.add_parser("apply", parents=[managed_context])
    apply.add_argument("--approved-plan", type=Path, required=True)
    apply.add_argument("--explicit-approval", action="store_true")
    subparsers.add_parser("rollback", parents=[managed_context])
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    """Execute one bounded archive-organization operation."""

    args = _parser().parse_args(argv)
    try:
        if args.command == "preflight":
            context = _load_context(args.client_engagement)
            result = {
                "status": "valid",
                "run_id": context["run_id"],
                "client_id": context["client_id"],
                "output_dir": context["output_dir"],
                "source_archive_mutated": False,
            }
        elif args.command == "prepare-review":
            result = build_review_package(
                args.client_engagement,
                args.proposals,
                policy_path=args.policy,
            )
        elif args.command == "save-decisions":
            result = persist_review_decisions(args.client_engagement, args.decisions)
        elif args.command == "approve":
            result = compile_approved_plan(args.client_engagement, args.decisions)
        elif args.command == "apply":
            result = apply_approved_plan(
                args.client_engagement,
                args.approved_plan,
                explicit_approval=args.explicit_approval,
            )
        else:
            result = rollback_applied_plan(args.client_engagement)
    except (ArchiveOrganizationError, OSError, ValueError) as exc:
        sys.stdout.write(
            json.dumps(
                {"error": {"code": "archive_organization_failed", "message": str(exc)}}
            )
            + "\n"
        )
        return 1
    sys.stdout.write(json.dumps(result, ensure_ascii=False, sort_keys=True) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
