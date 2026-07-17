"""Authenticated server-side boundary for local Attribute Reporting runs."""

from __future__ import annotations

import csv
import fcntl
import hashlib
import importlib.util
import json
import logging
import math
import os
import re
import shutil
import stat
import sys
import threading
import uuid
import zipfile
from collections.abc import Callable, Iterable, Iterator, Mapping, Sequence
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from functools import lru_cache
from pathlib import Path
from types import ModuleType
from typing import Any, Protocol

from modules.pdp.review_constants import (
    DEFAULT_PDP_STORE_PATH,
    enforce_default_pdp_store_path,
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

__all__ = [
    "AttributeReportingBridge",
    "BridgeConflictError",
    "BridgeNotFoundError",
    "BridgeValidationError",
    "get_attribute_reporting_bridge",
]

LOGGER = logging.getLogger(__name__)
SCHEMA_PREFIX = "attribute_reporting.server_bridge"
SAFE_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}$")
MAX_EVIDENCE_TREE_FILES = 20_000
MAX_EVIDENCE_TREE_BYTES = 512 * 1024 * 1024
MAX_MAPPING_ARTIFACT_BYTES = 32 * 1024 * 1024
MAX_MAPPING_SUBMISSION_BYTES = 64 * 1024 * 1024
MAX_MAPPING_TASKS = 10_000
MAX_JSON_DEPTH = 16
MAX_JSON_STRING_LENGTH = 16_000
MAX_JSON_NODES = 500_000
MAX_ACTOR_EVIDENCE_JOBS = 25
MAX_ACTOR_BRAND_FIT_JOBS = 25
MAX_ACTOR_WORKSETS = 25
MAX_ACTOR_SUBMISSIONS = 100
MAX_ACTOR_RETAINED_BYTES = 8 * 1024 * 1024 * 1024
MAX_GLOBAL_RETAINED_BYTES = 64 * 1024 * 1024 * 1024
MAX_GLOBAL_CONCURRENT_EVIDENCE_BUILDS = 2
EVIDENCE_JOB_TTL = timedelta(days=30)
BRAND_FIT_JOB_TTL = timedelta(days=30)
WORKSET_TTL = timedelta(days=7)
SUBMISSION_TTL = timedelta(days=180)
REQUIRED_PRODUCT_CACHE_ENTRIES = (
    "parent_filtered",
    "variant_result",
    "combined",
    "parents_all",
)


class BridgeValidationError(ValueError):
    """Raised when a bridge request violates a pinned artifact contract."""


class BridgeNotFoundError(LookupError):
    """Raised when an artifact is absent or belongs to another actor."""


class BridgeConflictError(RuntimeError):
    """Raised when central state changed after a workset was issued."""


class MappingEngine(Protocol):
    """Subset of the packaged Attribute Reporting mapping contract used here."""

    def create_mapping_tasks(
        self,
        package_dir: Path,
        taxonomy: Mapping[str, Any],
        output_path: Path,
        *,
        max_tasks: int = 0,
        include_resolved: bool = False,
    ) -> dict[str, Any]: ...

    def validate_mapping_payloads(
        self,
        tasks: Mapping[str, Any],
        decisions: Mapping[str, Any],
        *,
        taxonomy: Mapping[str, Any] | None = None,
    ) -> dict[str, Any]: ...

    def verify_mapping_tasks_against_source(
        self,
        tasks: Mapping[str, Any],
        taxonomy: Mapping[str, Any],
    ) -> dict[str, Any]: ...

    def validate_mapping_review_payloads(
        self,
        tasks: Mapping[str, Any],
        decisions: Mapping[str, Any],
        validated: Mapping[str, Any],
        review: Mapping[str, Any],
        *,
        taxonomy: Mapping[str, Any] | None = None,
    ) -> dict[str, Any]: ...

    def select_codex_effective_correction_tasks(
        self,
        tasks: Sequence[Mapping[str, Any]],
        codex_mapping_identities: Iterable[Sequence[str] | Mapping[str, Any]],
    ) -> dict[str, Any]: ...


class MappingApplyEngine(Protocol):
    """Exact validated-mapping-to-storage expansion owned by the plugin."""

    def mapping_record_specs(
        self, mapping: Mapping[str, Any]
    ) -> list[dict[str, Any]]: ...


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _canonical_json_bytes(payload: Any) -> bytes:
    return json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def _canonical_sha256(payload: Mapping[str, Any]) -> str:
    return hashlib.sha256(_canonical_json_bytes(payload)).hexdigest()


def _file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _parse_timestamp(value: object) -> datetime:
    text = str(value or "").strip().replace("Z", "+00:00")
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError as exc:
        raise BridgeValidationError(
            "Bridge artifact has an invalid timestamp."
        ) from exc
    if parsed.tzinfo is None:
        raise BridgeValidationError(
            "Bridge artifact timestamp must include a timezone."
        )
    return parsed.astimezone(timezone.utc)


def _bounded_tree_stats(root: Path) -> tuple[int, int]:
    """Return file count/bytes while rejecting links, special files, and excess."""

    file_count = 0
    total_bytes = 0
    for path in root.rglob("*"):
        if path.is_symlink():
            raise RuntimeError("Evidence package trees cannot contain symlinks.")
        mode = path.stat().st_mode
        if stat.S_ISDIR(mode):
            continue
        if not stat.S_ISREG(mode):
            raise RuntimeError("Evidence package trees require ordinary files only.")
        file_count += 1
        total_bytes += path.stat().st_size
        if file_count > MAX_EVIDENCE_TREE_FILES:
            raise RuntimeError("Evidence package contains too many files.")
        if total_bytes > MAX_EVIDENCE_TREE_BYTES:
            raise RuntimeError("Evidence package exceeds the server byte limit.")
    return file_count, total_bytes


def _ordinary_tree_bytes(root: Path, *, stop_after: int) -> int:
    """Count retained ordinary-file bytes without following filesystem links."""

    total_bytes = 0
    for path in root.rglob("*"):
        if path.is_symlink():
            raise BridgeValidationError(
                "Retained Attribute Reporting artifacts cannot contain symlinks."
            )
        mode = path.stat().st_mode
        if stat.S_ISDIR(mode):
            continue
        if not stat.S_ISREG(mode):
            raise BridgeValidationError(
                "Retained Attribute Reporting artifacts require ordinary files."
            )
        total_bytes += path.stat().st_size
        if total_bytes > stop_after:
            return total_bytes
    return total_bytes


def _assert_bounded_json(value: Any, *, label: str) -> int:
    """Bound submitted JSON depth, nodes, strings, and encoded byte size."""

    stack: list[tuple[Any, int]] = [(value, 0)]
    node_count = 0
    while stack:
        item, depth = stack.pop()
        node_count += 1
        if node_count > MAX_JSON_NODES:
            raise BridgeValidationError(f"{label} contains too many JSON values.")
        if depth > MAX_JSON_DEPTH:
            raise BridgeValidationError(f"{label} exceeds the JSON nesting limit.")
        if isinstance(item, str):
            if len(item) > MAX_JSON_STRING_LENGTH:
                raise BridgeValidationError(f"{label} contains an oversized string.")
        elif isinstance(item, Mapping):
            for key, child in item.items():
                if not isinstance(key, str) or len(key) > 256:
                    raise BridgeValidationError(f"{label} contains an invalid key.")
                stack.append((child, depth + 1))
        elif isinstance(item, Sequence) and not isinstance(
            item, (str, bytes, bytearray)
        ):
            stack.extend((child, depth + 1) for child in item)
        elif isinstance(item, float):
            if not math.isfinite(item):
                raise BridgeValidationError(f"{label} contains a non-finite number.")
        elif item is not None and not isinstance(item, (bool, int)):
            raise BridgeValidationError(f"{label} contains a non-JSON value.")
    try:
        size = len(_canonical_json_bytes(value))
    except (TypeError, ValueError) as exc:
        raise BridgeValidationError(f"{label} is not valid JSON.") from exc
    if size > MAX_MAPPING_ARTIFACT_BYTES:
        raise BridgeValidationError(f"{label} exceeds the artifact byte limit.")
    return size


def _serialize_mapping_state_groups(
    states: Mapping[
        AttributeMappingIdentity,
        Sequence[AttributeMappingStateRow],
    ],
) -> list[dict[str, Any]]:
    groups: list[dict[str, Any]] = []
    for identity in sorted(states):
        rows = sorted(
            (AttributeMappingStateRow(*row) for row in states[identity]),
            key=lambda row: row.attribute_id,
        )
        groups.append(
            {
                "identity": dict(identity._asdict()),
                "rows": [dict(row._asdict()) for row in rows],
            }
        )
    return groups


def _mapping_state_payload(
    states: Mapping[
        AttributeMappingIdentity,
        Sequence[AttributeMappingStateRow],
    ],
    *,
    retailer: str,
    category_key: str,
    captured_at: str,
    schema_suffix: str,
) -> dict[str, Any]:
    core = {
        "scope": {
            "source": "codex",
            "retailer": retailer,
            "category_key": category_key,
        },
        "groups": _serialize_mapping_state_groups(states),
    }
    payload = {
        "schema_version": f"{SCHEMA_PREFIX}.{schema_suffix}.v1",
        **core,
        "state_sha256": _canonical_sha256(core),
        "captured_at": captured_at,
    }
    _assert_bounded_json(payload, label="Mapping state snapshot")
    return payload


def _mapping_states_from_payload(
    payload: Mapping[str, Any],
    *,
    expected_retailer: str,
    expected_category_key: str,
) -> dict[AttributeMappingIdentity, tuple[AttributeMappingStateRow, ...]]:
    scope = payload.get("scope")
    raw_groups = payload.get("groups")
    if not isinstance(scope, Mapping) or not isinstance(raw_groups, list):
        raise BridgeConflictError("The pinned mapping state snapshot is invalid.")
    if (
        scope.get("source") != "codex"
        or scope.get("retailer") != expected_retailer
        or scope.get("category_key") != expected_category_key
    ):
        raise BridgeConflictError("The pinned mapping state scope changed.")
    core = {"scope": dict(scope), "groups": raw_groups}
    if payload.get("state_sha256") != _canonical_sha256(core):
        raise BridgeConflictError("The pinned mapping state checksum changed.")
    states: dict[
        AttributeMappingIdentity,
        tuple[AttributeMappingStateRow, ...],
    ] = {}
    try:
        for raw_group in raw_groups:
            if not isinstance(raw_group, Mapping) or set(raw_group) != {
                "identity",
                "rows",
            }:
                raise TypeError
            raw_identity = raw_group["identity"]
            raw_rows = raw_group["rows"]
            if not isinstance(raw_identity, Mapping) or set(raw_identity) != set(
                AttributeMappingIdentity._fields
            ):
                raise TypeError
            identity = AttributeMappingIdentity(
                **{field: str(raw_identity[field]) for field in raw_identity}
            )
            if (
                identity.source != "codex"
                or identity.retailer != expected_retailer
                or identity.category_key != expected_category_key
                or not isinstance(raw_rows, list)
                or identity in states
            ):
                raise TypeError
            rows: list[AttributeMappingStateRow] = []
            for raw_row in raw_rows:
                if not isinstance(raw_row, Mapping) or set(raw_row) != set(
                    AttributeMappingStateRow._fields
                ):
                    raise TypeError
                rows.append(
                    AttributeMappingStateRow(
                        attribute_id=str(raw_row["attribute_id"]),
                        attribute_label=(
                            None
                            if raw_row["attribute_label"] is None
                            else str(raw_row["attribute_label"])
                        ),
                        value=(
                            None if raw_row["value"] is None else str(raw_row["value"])
                        ),
                        oov_candidate=(
                            None
                            if raw_row["oov_candidate"] is None
                            else str(raw_row["oov_candidate"])
                        ),
                        note=(
                            None if raw_row["note"] is None else str(raw_row["note"])
                        ),
                        updated_at=str(raw_row["updated_at"]),
                    )
                )
            ordered = tuple(sorted(rows, key=lambda row: row.attribute_id))
            if len({row.attribute_id for row in ordered}) != len(ordered):
                raise TypeError
            states[identity] = ordered
    except (KeyError, TypeError, ValueError) as exc:
        raise BridgeConflictError(
            "The pinned mapping state snapshot is invalid."
        ) from exc
    if _serialize_mapping_state_groups(states) != raw_groups:
        raise BridgeConflictError("The pinned mapping state ordering changed.")
    return states


def _mapping_identity_from_task(task: Mapping[str, Any]) -> AttributeMappingIdentity:
    product = task.get("product")
    attribute = task.get("attribute")
    if not isinstance(product, Mapping) or not isinstance(attribute, Mapping):
        raise BridgeValidationError(
            "Mapping task has no product or attribute identity."
        )
    identity = AttributeMappingIdentity(
        source="codex",
        retailer=str(product.get("retailer") or ""),
        row_type=str(product.get("row_type") or ""),
        parent_product_id=str(product.get("parent_product_id") or ""),
        variant_id=str(product.get("variant_id") or ""),
        category_key=str(product.get("category_key") or ""),
        base_attribute_id=str(attribute.get("id") or ""),
    )
    if not all(
        (
            identity.source,
            identity.retailer,
            identity.row_type,
            identity.parent_product_id,
            identity.category_key,
            identity.base_attribute_id,
        )
    ):
        raise BridgeValidationError("Mapping task has an incomplete database identity.")
    return identity


def _mapping_states_from_value_records(
    records: Sequence[AttributeValueRecord],
) -> dict[AttributeMappingIdentity, tuple[AttributeMappingStateRow, ...]]:
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
    return {
        identity: tuple(sorted(rows, key=lambda row: row.attribute_id))
        for identity, rows in grouped.items()
    }


_PRIVATE_PATH_FIELDS = frozenset(
    {
        "run_dir",
        "pdp_store_path",
        "local_image_path",
        "pack_image_path",
        "image_file",
        "innovation_package_dir",
        "innovation_brief_path",
        "owned_cli_dir",
        "owned_cli_dirs",
        "output_dir",
        "package_zip",
    }
)
_EMBEDDED_IMAGE_FIELDS = frozenset(
    {
        "base64_image",
        "image_base64",
        "image_blob",
        "image_bytes",
        "image_data",
        "image_data_uri",
    }
)
_WINDOWS_ABSOLUTE_PATH_RE = re.compile(r"^(?:[A-Za-z]:[\\/]|\\\\|//)")
_PRIVATE_PATH_SUBSTRING_RE = re.compile(
    r"(?:^|[\s('`\"=:,])(?:/(?:srv|home|root|users|var|private|tmp|etc)(?:[\\/]|$)|[A-Za-z]:[\\/]|\\\\[^\s\\/]+[\\/])",
    flags=re.IGNORECASE,
)
_PRIVATE_URI_SUBSTRING_RE = re.compile(
    r"data:image/|blob:|file:(?://|[\\/])|(?:postgres(?:ql)?|mysql|mariadb|sqlite|mongodb|redis)://|database_url\s*=",
    flags=re.IGNORECASE,
)
_PUBLIC_HTTP_URL_RE = re.compile(r"^https?://[^\s]+$", flags=re.IGNORECASE)
_IMAGE_SUFFIXES = frozenset(
    {
        ".avif",
        ".bmp",
        ".gif",
        ".heic",
        ".heif",
        ".jpeg",
        ".jpg",
        ".png",
        ".svg",
        ".tif",
        ".tiff",
        ".webp",
    }
)
_PORTABLE_TEXT_SUFFIXES = frozenset({".csv", ".html", ".json", ".md", ".txt"})
_PROVENANCE_FILES = (
    "mapping_tasks.json",
    "mapping_decisions.json",
    "validated_mappings.json",
    "mapping_review.json",
)
_SERVER_PROVENANCE_FILES = (
    ("mapping_submission_receipt.json", "receipt.json"),
    ("mapping_review_validation.json", "mapping_review_validation.json"),
)


def _is_unsafe_portable_string(value: str) -> bool:
    """Identify embedded image bytes, local URIs, and cross-platform paths."""

    text = value.strip()
    if _PUBLIC_HTTP_URL_RE.fullmatch(text):
        return False
    lowered = text.casefold()
    return bool(
        _PRIVATE_URI_SUBSTRING_RE.search(text)
        or _PRIVATE_PATH_SUBSTRING_RE.search(text)
        or lowered.startswith(("data:image/", "blob:", "file:"))
        or _WINDOWS_ABSOLUTE_PATH_RE.match(text)
        or Path(text).is_absolute()
    )


def _sanitize_json_paths(value: Any, *, key: str = "") -> tuple[Any, int]:
    normalized_key = key.casefold()
    if (
        normalized_key in _PRIVATE_PATH_FIELDS
        or normalized_key in _EMBEDDED_IMAGE_FIELDS
    ):
        return None, int(value is not None and value != "")
    if key == "image_source" and isinstance(value, str):
        is_public_url = value.startswith(("https://", "http://"))
        return (value if is_public_url else None), int(
            bool(value) and not is_public_url
        )
    if isinstance(value, dict):
        output: dict[str, Any] = {}
        changed = 0
        for child_key, child_value in value.items():
            clean_value, child_changed = _sanitize_json_paths(
                child_value,
                key=str(child_key),
            )
            output[str(child_key)] = clean_value
            changed += child_changed
        return output, changed
    if isinstance(value, list):
        output_list = []
        changed = 0
        for child_value in value:
            clean_value, child_changed = _sanitize_json_paths(child_value)
            output_list.append(clean_value)
            changed += child_changed
        return output_list, changed
    if isinstance(value, str) and _is_unsafe_portable_string(value):
        return None, 1
    return value, 0


def _sanitize_json_file(path: Path) -> int:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"Invalid package JSON: {path.name}") from exc
    sanitized, changed = _sanitize_json_paths(payload)
    if changed:
        path.write_text(
            json.dumps(sanitized, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
    return changed


def _sanitize_csv_file(path: Path) -> int:
    with path.open(encoding="utf-8", newline="") as source:
        reader = csv.DictReader(source)
        fieldnames = list(reader.fieldnames or [])
        rows = [dict(row) for row in reader]
    private_columns = [
        name
        for name in fieldnames
        if name.casefold() in _PRIVATE_PATH_FIELDS
        or name.casefold() in _EMBEDDED_IMAGE_FIELDS
    ]
    changed = 0
    for row in rows:
        for column in private_columns:
            if row.get(column):
                changed += 1
            row[column] = ""
        if "image_source" in row:
            image_source = str(row.get("image_source") or "")
            if image_source and not image_source.startswith(("https://", "http://")):
                row["image_source"] = ""
                changed += 1
        for column, value in row.items():
            text = str(value or "")
            if (
                column not in private_columns
                and text
                and _is_unsafe_portable_string(text)
            ):
                row[column] = ""
                changed += 1
    if not changed:
        return 0
    with path.open("w", encoding="utf-8", newline="") as target:
        writer = csv.DictWriter(target, fieldnames=fieldnames, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)
    return changed


def _assert_no_unsafe_portable_values(root: Path) -> None:
    """Independently verify that sanitization left no local/image-byte payloads."""

    def assert_value(value: Any, *, key: str = "") -> None:
        normalized_key = key.casefold()
        if normalized_key in _PRIVATE_PATH_FIELDS and value is not None and value != "":
            raise RuntimeError("Portable package still contains a local path field.")
        if (
            normalized_key in _EMBEDDED_IMAGE_FIELDS
            and value is not None
            and value != ""
        ):
            raise RuntimeError("Portable package still contains embedded image data.")
        if isinstance(value, Mapping):
            for child_key, child_value in value.items():
                assert_value(child_value, key=str(child_key))
        elif isinstance(value, list):
            for child_value in value:
                assert_value(child_value)
        elif isinstance(value, str) and _is_unsafe_portable_string(value):
            raise RuntimeError(
                "Portable package still contains a local URI or private path."
            )

    for path in sorted(root.rglob("*")):
        if not path.is_file():
            continue
        suffix = path.suffix.casefold()
        if suffix == ".json":
            assert_value(_load_json(path))
        elif suffix == ".csv":
            with path.open(encoding="utf-8", newline="") as handle:
                for row in csv.DictReader(handle):
                    assert_value(dict(row))
        elif suffix in {".html", ".md", ".txt"}:
            text = path.read_text(encoding="utf-8", errors="replace")
            if _is_unsafe_portable_string(text):
                raise RuntimeError(
                    "Portable package still contains embedded image data or a local URI."
                )


def _assert_portable_file_types(root: Path) -> None:
    """Reject disguised binary payloads after known image files are removed."""

    for path in sorted(root.rglob("*")):
        if path.is_file() and path.suffix.casefold() not in _PORTABLE_TEXT_SUFFIXES:
            raise RuntimeError(
                f"Portable evidence package contains an unsupported file type: {path.name}"
            )


def _write_sorted_zip(source_dir: Path, output_path: Path) -> None:
    """Write a stable portable ZIP from ordinary files only."""

    _bounded_tree_stats(source_dir)
    with zipfile.ZipFile(
        output_path,
        mode="w",
        compression=zipfile.ZIP_DEFLATED,
        compresslevel=9,
        allowZip64=True,
    ) as archive:
        for path in sorted(source_dir.rglob("*"), key=lambda item: item.as_posix()):
            if path.is_symlink():
                raise RuntimeError(
                    "Portable evidence packages cannot contain symlinks."
                )
            if not path.is_file():
                continue
            relative = path.relative_to(source_dir).as_posix()
            info = zipfile.ZipInfo(relative, date_time=(1980, 1, 1, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = (stat.S_IFREG | 0o600) << 16
            with (
                path.open("rb") as source,
                archive.open(
                    info,
                    mode="w",
                    force_zip64=True,
                ) as target,
            ):
                shutil.copyfileobj(source, target, length=1024 * 1024)
    os.chmod(output_path, 0o600)
    if output_path.stat().st_size > MAX_EVIDENCE_TREE_BYTES:
        output_path.unlink(missing_ok=True)
        raise RuntimeError("Portable evidence ZIP exceeds the server byte limit.")


def _extract_server_package(source_zip: Path, destination: Path) -> None:
    """Extract a checksum-verified server ZIP without accepting unsafe members."""

    if destination.exists():
        shutil.rmtree(destination)
    destination.mkdir(parents=True)
    file_count = 0
    total_bytes = 0
    with zipfile.ZipFile(source_zip) as archive:
        for info in archive.infolist():
            member = Path(info.filename)
            if (
                not info.filename
                or "\\" in info.filename
                or member.is_absolute()
                or any(part in {"", ".", ".."} for part in member.parts)
                or stat.S_ISLNK(info.external_attr >> 16)
            ):
                raise RuntimeError("Source evidence ZIP contains an unsafe member.")
            if info.is_dir():
                continue
            file_count += 1
            total_bytes += info.file_size
            if (
                file_count > MAX_EVIDENCE_TREE_FILES
                or total_bytes > MAX_EVIDENCE_TREE_BYTES
            ):
                raise RuntimeError("Source evidence ZIP exceeds server limits.")
            target = destination.joinpath(*member.parts)
            target.parent.mkdir(parents=True, exist_ok=True)
            with archive.open(info) as source, target.open("wb") as output:
                shutil.copyfileobj(source, output, length=1024 * 1024)
    _bounded_tree_stats(destination)


def _build_portable_package(
    source_dir: Path,
    portable_dir: Path,
    output_zip: Path,
    *,
    provenance_dir: Path | None = None,
    private_path_roots: Sequence[Path] = (),
    regenerate_brand_fit_manifest: bool = False,
) -> dict[str, Any]:
    """Remove server paths/images and create a URL-only portable evidence ZIP."""

    if source_dir.is_symlink() or any(
        path.is_symlink() for path in source_dir.rglob("*")
    ):
        raise RuntimeError("Portable evidence packages cannot contain symlinks.")
    _bounded_tree_stats(source_dir)
    if portable_dir.exists():
        shutil.rmtree(portable_dir)
    shutil.copytree(source_dir, portable_dir, symlinks=False)
    removed_images: list[str] = []
    for path in sorted(portable_dir.rglob("*")):
        if path.is_symlink():
            raise RuntimeError("Portable evidence packages cannot contain symlinks.")
        if not path.is_file():
            continue
        relative = path.relative_to(portable_dir)
        if "images" in relative.parts or path.suffix.casefold() in _IMAGE_SUFFIXES:
            removed_images.append(relative.as_posix())
            path.unlink()
    for path in sorted(portable_dir.rglob("*"), reverse=True):
        if path.is_dir() and not any(path.iterdir()):
            path.rmdir()

    # This legacy handoff prompt is not part of the installed Clara workflow.
    # Codex creates and checks the report locally from the evidence tables.
    legacy_prompt = portable_dir / "prompt_for_pro.txt"
    legacy_prompt.unlink(missing_ok=True)

    sanitized_field_count = 0
    for path in sorted(portable_dir.rglob("*.json")):
        sanitized_field_count += _sanitize_json_file(path)
    for path in sorted(portable_dir.rglob("*.csv")):
        sanitized_field_count += _sanitize_csv_file(path)

    provenance_hashes: dict[str, str] = {}
    if provenance_dir is not None:
        for file_name in _PROVENANCE_FILES:
            source = provenance_dir / file_name
            if not source.is_file():
                raise RuntimeError("Mapping provenance is incomplete.")
            target = portable_dir / file_name
            shutil.copyfile(source, target)
            provenance_hashes[file_name] = _file_sha256(target)
        for target_name, source_name in _SERVER_PROVENANCE_FILES:
            source = provenance_dir / source_name
            if not source.is_file():
                raise RuntimeError("Server mapping provenance is incomplete.")
            target = portable_dir / target_name
            shutil.copyfile(source, target)
            provenance_hashes[target_name] = _file_sha256(target)

    private_needles = {
        str(source_dir.resolve()),
        str(_repo_root().resolve()),
        str(DEFAULT_PDP_STORE_PATH.resolve()),
        *(str(path.resolve()) for path in private_path_roots),
    }
    for path in sorted(portable_dir.rglob("*")):
        if not path.is_file() or path.suffix.casefold() not in {
            ".csv",
            ".html",
            ".json",
            ".md",
            ".txt",
        }:
            continue
        text = path.read_text(encoding="utf-8", errors="replace")
        if any(needle and needle in text for needle in private_needles):
            raise RuntimeError("Portable evidence package still contains server paths.")

    integrity = _load_json(portable_dir / "package_integrity.json")
    if str(integrity.get("status") or "").casefold() != "pass":
        raise RuntimeError("Portable evidence package integrity is not pass.")
    sanitization = {
        "schema_version": f"{SCHEMA_PREFIX}.package_sanitization.v1",
        "image_policy": "urls_only_no_image_bytes",
        "removed_image_file_count": len(removed_images),
        "sanitized_private_path_field_count": sanitized_field_count,
        "mapping_provenance": provenance_hashes,
        "package_integrity_status": "pass",
    }
    _atomic_write_json(portable_dir / "server_sanitization_receipt.json", sanitization)
    if regenerate_brand_fit_manifest:
        manifest_path = portable_dir / "pack_manifest.json"
        manifest = _load_json(manifest_path)
        package_type = str(manifest.get("package_type") or "").strip()
        if not package_type:
            raise RuntimeError("Brand Fit package manifest has no package type.")
        # The portable manifest is a mechanical inventory of the final sanitized
        # handoff, so build it only after the sanitization receipt exists.
        _atomic_write_json(
            manifest_path,
            {
                "package_type": package_type,
                "files": sorted(
                    path.relative_to(portable_dir).as_posix()
                    for path in portable_dir.rglob("*")
                    if path.is_file() and path != manifest_path
                ),
                "summary": _load_json(portable_dir / "summary.json"),
            },
        )
    _assert_portable_file_types(portable_dir)
    _assert_no_unsafe_portable_values(portable_dir)
    _write_sorted_zip(portable_dir, output_zip)
    return sanitization


def _atomic_write_json(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
    temporary.write_text(
        json.dumps(dict(payload), ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    os.chmod(temporary, 0o600)
    temporary.replace(path)


@contextmanager
def _nonblocking_file_lock(path: Path) -> Iterator[bool]:
    """Yield whether this process acquired one cross-worker artifact lock."""

    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a+", encoding="utf-8") as handle:
        os.chmod(path, 0o600)
        acquired = False
        try:
            fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            acquired = True
        except BlockingIOError:
            pass
        try:
            yield acquired
        finally:
            if acquired:
                fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


@contextmanager
def _first_available_file_lock(paths: Sequence[Path]) -> Iterator[bool]:
    """Hold the first available lock slot for the duration of the context."""

    for path in paths:
        with _nonblocking_file_lock(path) as acquired:
            if acquired:
                yield True
                return
    yield False


@contextmanager
def _blocking_file_lock(path: Path) -> Iterator[None]:
    """Serialize one actor operation across application workers."""

    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a+", encoding="utf-8") as handle:
        os.chmod(path, 0o600)
        fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


def _load_json(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError, OSError) as exc:
        raise BridgeNotFoundError(
            "Attribute Reporting artifact is unavailable."
        ) from exc
    if not isinstance(payload, dict):
        raise BridgeNotFoundError("Attribute Reporting artifact is unavailable.")
    return payload


def _clean_actor(actor_email: str) -> str:
    actor = actor_email.strip().casefold()
    if not actor or len(actor) > 320 or "@" not in actor:
        if actor == "local-dev":
            return actor
        raise BridgeValidationError("A valid authenticated actor is required.")
    return actor


def _clean_scope_value(value: str, *, field: str) -> str:
    clean = value.strip()
    if not SAFE_ID_RE.fullmatch(clean):
        raise BridgeValidationError(f"Invalid {field}.")
    return clean


def _clean_display_text(value: str, *, field: str, maximum: int = 256) -> str:
    clean = " ".join(value.split())
    if not clean or len(clean) > maximum or any(ord(char) < 32 for char in clean):
        raise BridgeValidationError(f"Invalid {field}.")
    return clean


def _taxonomy_token(value: object) -> str:
    return re.sub(r"[^a-z0-9]+", "_", str(value or "").casefold()).strip("_")


def _category_branch(taxonomy: Mapping[str, Any], category_key: str) -> dict[str, Any]:
    categories = taxonomy.get("categories")
    if not isinstance(categories, list):
        raise BridgeValidationError("The central taxonomy has no categories.")
    target = _taxonomy_token(category_key)
    for category in categories:
        if isinstance(category, dict) and _taxonomy_token(category.get("id")) == target:
            return dict(category)
    raise BridgeNotFoundError("Category is absent from the central taxonomy.")


def _validate_enriched_mapping_tasks(
    stored_tasks: Mapping[str, Any],
    submitted_tasks: Mapping[str, Any],
) -> dict[str, Any]:
    """Allow only locally hydrated image pins to differ from the public workset."""

    stored_rows = stored_tasks.get("tasks")
    submitted_rows = submitted_tasks.get("tasks")
    if not isinstance(stored_rows, list) or not isinstance(submitted_rows, list):
        raise BridgeValidationError("Mapping tasks must contain a tasks list.")
    if len(stored_rows) != len(submitted_rows):
        raise BridgeConflictError("Submitted mapping tasks differ from the workset.")
    normalized = json.loads(json.dumps(submitted_tasks, ensure_ascii=False))
    normalized_rows = normalized["tasks"]
    for index, (stored_row, submitted_row) in enumerate(
        zip(stored_rows, submitted_rows)
    ):
        if not isinstance(stored_row, dict) or not isinstance(submitted_row, dict):
            raise BridgeValidationError("Each mapping task must be an object.")
        stored_product = stored_row.get("product")
        submitted_product = submitted_row.get("product")
        normalized_product = normalized_rows[index].get("product")
        if not all(
            isinstance(item, dict)
            for item in (stored_product, submitted_product, normalized_product)
        ):
            raise BridgeValidationError("Each mapping task requires a product object.")
        local_images = submitted_product.get("local_images")
        if not isinstance(local_images, list) or len(local_images) > 12:
            raise BridgeValidationError("Local mapping images must be a bounded list.")
        seen_paths: set[str] = set()
        for image in local_images:
            if not isinstance(image, dict) or set(image) != {"path", "sha256"}:
                raise BridgeValidationError(
                    "Each local mapping image requires only path and sha256."
                )
            path_text = str(image.get("path") or "")
            path = Path(path_text)
            if (
                not path_text
                or "\\" in path_text
                or path.is_absolute()
                or not path.parts
                or path.parts[0] != "images"
                or any(part in {"", ".", ".."} for part in path.parts)
                or path.suffix.casefold() not in _IMAGE_SUFFIXES
                or path_text in seen_paths
            ):
                raise BridgeValidationError(
                    "Local mapping image paths must be unique package-relative images/*."
                )
            if not re.fullmatch(r"[0-9a-f]{64}", str(image.get("sha256") or "")):
                raise BridgeValidationError(
                    "Local mapping image checksums must be SHA-256 values."
                )
            seen_paths.add(path_text)
        normalized_product["local_images"] = stored_product.get("local_images", [])
    if normalized != stored_tasks:
        raise BridgeConflictError(
            "Only product.local_images may differ from the issued workset."
        )
    return json.loads(json.dumps(submitted_tasks, ensure_ascii=False))


def _validate_public_tasks_match_server(
    server_tasks: Mapping[str, Any],
    public_tasks: Mapping[str, Any],
) -> None:
    """Prove sanitation changed only paths, hashes, and server-local images."""

    server = json.loads(json.dumps(server_tasks, ensure_ascii=False))
    public = json.loads(json.dumps(public_tasks, ensure_ascii=False))
    server_scope = server.get("scope")
    public_scope = public.get("scope")
    if not isinstance(server_scope, dict) or not isinstance(public_scope, dict):
        raise BridgeValidationError("Mapping worksets require source scope objects.")
    for key in ("retailer", "category_key", "row_type"):
        if server_scope.get(key) != public_scope.get(key):
            raise BridgeConflictError("Portable mapping scope differs from the source.")
    server["scope"] = {
        key: server_scope.get(key) for key in ("retailer", "category_key", "row_type")
    }
    public["scope"] = dict(server["scope"])
    server.pop("generated_at", None)
    public.pop("generated_at", None)
    server_rows = server.get("tasks")
    public_rows = public.get("tasks")
    if not isinstance(server_rows, list) or not isinstance(public_rows, list):
        raise BridgeValidationError("Mapping worksets require task lists.")
    if len(server_rows) != len(public_rows):
        raise BridgeConflictError("Portable mapping task coverage differs from source.")
    for server_row, public_row in zip(server_rows, public_rows):
        if not isinstance(server_row, dict) or not isinstance(public_row, dict):
            raise BridgeValidationError("Mapping workset tasks must be objects.")
        server_product = server_row.get("product")
        public_product = public_row.get("product")
        if not isinstance(server_product, dict) or not isinstance(public_product, dict):
            raise BridgeValidationError("Mapping tasks require product objects.")
        server_product["source_row_sha256"] = "portable-row-hash"
        public_product["source_row_sha256"] = "portable-row-hash"
        server_product["local_images"] = []
        public_product["local_images"] = []
    if server != public:
        raise BridgeConflictError(
            "Portable mapping tasks differ semantically from the private source."
        )


def _select_correction_workset(
    mapping_engine: MappingEngine,
    workset: Mapping[str, Any],
    pinned_identities: Iterable[AttributeMappingIdentity],
) -> dict[str, Any]:
    """Select the complete report-effective Codex correction subset."""

    raw_tasks = workset.get("tasks")
    coverage = workset.get("coverage")
    if not isinstance(raw_tasks, list) or not isinstance(coverage, Mapping):
        raise BridgeValidationError("Correction workset has invalid task coverage.")
    selection = mapping_engine.select_codex_effective_correction_tasks(
        raw_tasks,
        pinned_identities,
    )
    selected_rows = selection.get("tasks")
    selected_count = selection.get("task_count")
    count_fields = (
        "task_count_before_selection",
        "excluded_unresolved_count",
        "excluded_non_codex_effective_count",
        "excluded_not_pinned_count",
    )
    selection_counts = {field: selection.get(field) for field in count_fields}
    if (
        not isinstance(selected_rows, list)
        or not isinstance(selected_count, int)
        or isinstance(selected_count, bool)
        or selected_count != len(selected_rows)
        or any(not isinstance(row, Mapping) for row in selected_rows)
        or any(
            not isinstance(value, int) or isinstance(value, bool) or value < 0
            for value in selection_counts.values()
        )
        or selection_counts["task_count_before_selection"] != len(raw_tasks)
        or selected_count
        + selection_counts["excluded_unresolved_count"]
        + selection_counts["excluded_non_codex_effective_count"]
        + selection_counts["excluded_not_pinned_count"]
        != len(raw_tasks)
    ):
        raise BridgeValidationError("Correction task selection is invalid.")
    if selection_counts["excluded_not_pinned_count"]:
        raise BridgeConflictError(
            "The evidence package contains Codex-effective mappings absent from its "
            "pinned database state; rebuild the evidence job."
        )
    source_hashes = [_canonical_sha256(row) for row in raw_tasks]
    selected_hashes = [_canonical_sha256(row) for row in selected_rows]
    remaining = list(source_hashes)
    for selected_hash in selected_hashes:
        try:
            remaining.remove(selected_hash)
        except ValueError as exc:
            raise BridgeConflictError(
                "Correction selection introduced a task outside the source workset."
            ) from exc
    selected = json.loads(json.dumps(workset, ensure_ascii=False))
    selected["tasks"] = [dict(row) for row in selected_rows]
    selected_coverage = dict(coverage)
    selected_coverage["task_count_before_limit"] = selected_count
    selected_coverage["task_count"] = selected_count
    selected_coverage["truncated"] = False
    selected_coverage["include_resolved"] = True
    selected["coverage"] = selected_coverage
    selected["correction_selection"] = {
        key: value for key, value in selection.items() if key != "tasks"
    }
    return selected


def _active_leaf_values(nodes: object) -> list[dict[str, str]]:
    if not isinstance(nodes, list):
        return []
    values: list[dict[str, str]] = []
    for node in nodes:
        if not isinstance(node, dict):
            continue
        children = node.get("children")
        if isinstance(children, list) and children:
            values.extend(_active_leaf_values(children))
            continue
        status = str(node.get("status") or "active").casefold()
        value_id = str(node.get("id") or "").strip()
        label = str(node.get("label") or "").strip()
        if status == "active" and value_id and label:
            values.append({"id": value_id, "label": label})
    return values


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


def _assert_private_bridge_root(root: Path) -> Path:
    candidate = root.expanduser()
    if not candidate.is_absolute():
        raise RuntimeError("Attribute Reporting bridge root must be an absolute path.")
    resolved = candidate.resolve()
    for parent in (resolved, *resolved.parents):
        if (parent / ".git").exists():
            raise RuntimeError(
                "Attribute Reporting bridge artifacts must stay outside Git workspaces."
            )
    return resolved


def _load_python_module(name: str, path: Path) -> ModuleType:
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Cannot load Attribute Reporting runtime: {path.name}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


@lru_cache(maxsize=1)
def _default_mapping_engine() -> MappingEngine:
    path = (
        _repo_root()
        / "plugins"
        / "attribute-reporting"
        / "scripts"
        / "attribute_reporting.py"
    )
    return _load_python_module("attribute_reporting", path)  # type: ignore[return-value]


@lru_cache(maxsize=1)
def _default_mapping_apply_engine() -> MappingApplyEngine:
    _default_mapping_engine()
    path = (
        _repo_root()
        / "plugins"
        / "attribute-reporting"
        / "scripts"
        / "apply_validated_mappings.py"
    )
    return _load_python_module("attribute_reporting_apply", path)  # type: ignore[return-value]


def _default_taxonomy_loader() -> dict[str, Any]:
    from modules.add_attributes.attribute_taxonomy import (
        get_runtime_attribute_taxonomy,
    )

    return get_runtime_attribute_taxonomy()


def _default_package_builder(
    retailer: str,
    category_key: str,
    output_root: Path,
) -> Path:
    from scripts.build_retailer_category_evidence_pack import (
        DEFAULT_CLI_ROOT,
        build_pack,
    )

    return build_pack(
        retailer=retailer,
        category_key=category_key,
        run_dir=None,
        pdp_store_path=enforce_default_pdp_store_path(DEFAULT_PDP_STORE_PATH),
        cli_root=DEFAULT_CLI_ROOT,
        output_root=output_root,
        max_pack_images=0,
    )


def _default_brand_fit_builder(
    *,
    brand_source_retailer: str,
    brand_name: str,
    category_key: str,
    retailer: str,
    innovation_package_dir: Path,
    output_root: Path,
    owned_category_keys: Sequence[str],
    retailer_category_keys: Sequence[str],
    source_retailer_report: Mapping[str, str],
    source_retailer_evidence: Mapping[str, str],
    retailer_presence_snapshot: Mapping[str, str],
    product_data_snapshot: Mapping[str, Any],
    mapping_state_snapshot: Mapping[str, Any] | None = None,
) -> Path:
    """Run the deterministic Brand Fit builder in installed-plugin mode."""

    from scripts.build_brand_retailer_reference_package import build_package

    return build_package(
        brand_source_retailer=brand_source_retailer,
        brand_name=brand_name,
        category_key=category_key,
        retailer=retailer,
        innovation_package_dir=innovation_package_dir,
        innovation_brief_path=None,
        owned_category_keys=owned_category_keys,
        retailer_category_keys=retailer_category_keys,
        output_root=output_root,
        retailer_live_check=False,
        allow_missing_brand_images=True,
        require_innovation_brief=False,
        include_image_bytes=False,
        write_legacy_prompt=False,
        source_retailer_report=source_retailer_report,
        source_retailer_evidence=source_retailer_evidence,
        retailer_presence_snapshot=retailer_presence_snapshot,
        product_data_snapshot=product_data_snapshot,
        mapping_state_snapshot=mapping_state_snapshot,
        require_retailer_brand_column=True,
        require_owned_brand_column=True,
        refresh_database_cache=True,
    )


def _default_store_factory() -> PDPStore:
    return PDPStore(enforce_default_pdp_store_path(DEFAULT_PDP_STORE_PATH))


class AttributeReportingBridge:
    """Persist immutable bridge artifacts and apply reviewed mappings atomically."""

    def __init__(
        self,
        root: Path,
        *,
        taxonomy_loader: Callable[[], dict[str, Any]] = _default_taxonomy_loader,
        package_builder: Callable[[str, str, Path], Path] = _default_package_builder,
        brand_fit_builder: Callable[..., Path] = _default_brand_fit_builder,
        mapping_engine: MappingEngine | None = None,
        mapping_apply_engine: MappingApplyEngine | None = None,
        store_factory: Callable[[], PDPStore] = _default_store_factory,
        now: Callable[[], str] = _utc_now,
    ) -> None:
        self.root = _assert_private_bridge_root(root)
        self.root.mkdir(parents=True, mode=0o700, exist_ok=True)
        os.chmod(self.root, 0o700)
        self.taxonomy_loader = taxonomy_loader
        self.package_builder = package_builder
        self.brand_fit_builder = brand_fit_builder
        self.mapping_engine = mapping_engine or _default_mapping_engine()
        self.mapping_apply_engine = (
            mapping_apply_engine or _default_mapping_apply_engine()
        )
        self.store_factory = store_factory
        self.now = now
        self._lock = threading.RLock()

    def _actor_operation_lock(self, collection: str, actor: str) -> Path:
        actor_token = hashlib.sha256(actor.encode("utf-8")).hexdigest()
        return self.root / ".actor-locks" / f"{collection}-{actor_token}.lock"

    @staticmethod
    def _retention_policy(
        collection: str,
    ) -> tuple[str, str, str, timedelta]:
        policies: dict[str, tuple[str, str, str, timedelta]] = {
            "evidence_jobs": (
                "request.json",
                "requested_by",
                "requested_at",
                EVIDENCE_JOB_TTL,
            ),
            "brand_fit_jobs": (
                "request.json",
                "requested_by",
                "requested_at",
                BRAND_FIT_JOB_TTL,
            ),
            "worksets": (
                "metadata.json",
                "requested_by",
                "created_at",
                WORKSET_TTL,
            ),
            "submissions": (
                "metadata.json",
                "submitted_by",
                "submitted_at",
                SUBMISSION_TTL,
            ),
        }
        try:
            return policies[collection]
        except KeyError as exc:
            raise BridgeValidationError(
                "Unsupported bridge artifact collection."
            ) from exc

    def _prune_expired_artifacts(self) -> None:
        """Remove expired transient bridge artifacts under one cross-worker lock."""

        with _nonblocking_file_lock(self.root / ".retention.lock") as acquired:
            if not acquired:
                return
            now = _parse_timestamp(self.now())
            for collection in (
                "evidence_jobs",
                "brand_fit_jobs",
                "worksets",
                "submissions",
            ):
                metadata_name, _owner_key, timestamp_key, ttl = self._retention_policy(
                    collection
                )
                collection_root = self.root / collection
                if not collection_root.is_dir():
                    continue
                for artifact_dir in sorted(collection_root.iterdir()):
                    if artifact_dir.is_symlink() or not artifact_dir.is_dir():
                        continue
                    try:
                        metadata = _load_json(artifact_dir / metadata_name)
                        created_at = _parse_timestamp(metadata.get(timestamp_key))
                    except (BridgeNotFoundError, BridgeValidationError):
                        LOGGER.warning(
                            "Skipping malformed Attribute Reporting retention artifact: %s",
                            artifact_dir,
                        )
                        continue
                    if now - created_at <= ttl:
                        continue
                    if collection in {"evidence_jobs", "brand_fit_jobs"}:
                        if self._evidence_job_has_live_workset(
                            artifact_dir.name,
                            now=now,
                        ):
                            continue
                        with _nonblocking_file_lock(
                            artifact_dir / ".build.lock"
                        ) as build_lock_acquired:
                            if not build_lock_acquired:
                                continue
                            shutil.rmtree(artifact_dir)
                    elif collection == "worksets":
                        if self._workset_has_pending_submission(
                            artifact_dir.name,
                            now=now,
                        ):
                            continue
                        shutil.rmtree(artifact_dir)
                    else:
                        shutil.rmtree(artifact_dir)

    def _workset_has_pending_submission(
        self,
        workset_id: str,
        *,
        now: datetime,
    ) -> bool:
        """Retain repair inputs while a database submission may need recovery."""

        submissions_root = self.root / "submissions"
        if not submissions_root.is_dir():
            return False
        for submission_dir in submissions_root.iterdir():
            if submission_dir.is_symlink() or not submission_dir.is_dir():
                continue
            try:
                metadata = _load_json(submission_dir / "metadata.json")
                submitted_at = _parse_timestamp(metadata.get("submitted_at"))
            except (BridgeNotFoundError, BridgeValidationError):
                continue
            if (
                metadata.get("status") == "pending"
                and str(metadata.get("workset_id") or "") == workset_id
                and now - submitted_at <= SUBMISSION_TTL
            ):
                return True
        return False

    def _evidence_job_has_live_workset(
        self,
        job_id: str,
        *,
        now: datetime,
    ) -> bool:
        """Keep source evidence while a non-expired workset still depends on it."""

        worksets_root = self.root / "worksets"
        if worksets_root.is_dir():
            for workset_dir in worksets_root.iterdir():
                if workset_dir.is_symlink() or not workset_dir.is_dir():
                    continue
                try:
                    metadata = _load_json(workset_dir / "metadata.json")
                    created_at = _parse_timestamp(metadata.get("created_at"))
                except (BridgeNotFoundError, BridgeValidationError):
                    continue
                if str(metadata.get("evidence_job_id") or "") == job_id and (
                    now - created_at <= WORKSET_TTL
                    or self._workset_has_pending_submission(
                        workset_dir.name,
                        now=now,
                    )
                ):
                    return True
        brand_fit_root = self.root / "brand_fit_jobs"
        if brand_fit_root.is_dir():
            for brand_fit_dir in brand_fit_root.iterdir():
                if brand_fit_dir.is_symlink() or not brand_fit_dir.is_dir():
                    continue
                try:
                    request = _load_json(brand_fit_dir / "request.json")
                    requested_at = _parse_timestamp(request.get("requested_at"))
                    status = _load_json(brand_fit_dir / "status.json")
                except (BridgeNotFoundError, BridgeValidationError):
                    continue
                if (
                    str(request.get("source_evidence_job_id") or "") == job_id
                    and status.get("status") in {"pending", "running"}
                    and now - requested_at <= BRAND_FIT_JOB_TTL
                ):
                    return True
        return False

    def _enforce_actor_quota(
        self,
        collection: str,
        *,
        actor: str,
        maximum: int,
    ) -> None:
        metadata_name, owner_key, _timestamp_key, _ttl = self._retention_policy(
            collection
        )
        collection_root = self.root / collection
        count = 0
        if collection_root.is_dir():
            for artifact_dir in collection_root.iterdir():
                if artifact_dir.is_symlink() or not artifact_dir.is_dir():
                    continue
                try:
                    metadata = _load_json(artifact_dir / metadata_name)
                except BridgeNotFoundError:
                    continue
                if str(metadata.get(owner_key) or "").casefold() == actor:
                    count += 1
        if count >= maximum:
            raise BridgeConflictError(
                "The per-user Attribute Reporting artifact quota is full; wait for "
                "retention cleanup before creating more server work."
            )

    def _retained_artifact_bytes(
        self,
        *,
        actor: str | None,
        stop_after: int,
    ) -> int:
        """Count retained bridge bytes globally or for one normalized owner."""

        total_bytes = 0
        for collection in (
            "evidence_jobs",
            "brand_fit_jobs",
            "worksets",
            "submissions",
        ):
            metadata_name, owner_key, _timestamp_key, _ttl = self._retention_policy(
                collection
            )
            collection_root = self.root / collection
            if not collection_root.is_dir():
                continue
            for artifact_dir in collection_root.iterdir():
                if artifact_dir.is_symlink() or not artifact_dir.is_dir():
                    continue
                if actor is not None:
                    try:
                        metadata = _load_json(artifact_dir / metadata_name)
                    except (BridgeNotFoundError, BridgeValidationError):
                        continue
                    if str(metadata.get(owner_key) or "").casefold() != actor:
                        continue
                total_bytes += _ordinary_tree_bytes(
                    artifact_dir,
                    stop_after=max(0, stop_after - total_bytes),
                )
                if total_bytes > stop_after:
                    return total_bytes
        return total_bytes

    def _enforce_retained_byte_quotas(
        self,
        *,
        actor: str,
        additional_bytes: int = 0,
    ) -> None:
        """Bound aggregate disk retention under one cross-worker accounting lock."""

        if additional_bytes < 0:
            raise BridgeValidationError("Retained-byte reservation cannot be negative.")
        with _blocking_file_lock(self.root / ".retained-bytes.lock"):
            actor_bytes = self._retained_artifact_bytes(
                actor=actor,
                stop_after=MAX_ACTOR_RETAINED_BYTES,
            )
            if actor_bytes + additional_bytes > MAX_ACTOR_RETAINED_BYTES:
                raise BridgeConflictError(
                    "The per-user Attribute Reporting retained-byte quota is full; "
                    "wait for retention cleanup before creating more server work."
                )
            global_bytes = self._retained_artifact_bytes(
                actor=None,
                stop_after=MAX_GLOBAL_RETAINED_BYTES,
            )
            if global_bytes + additional_bytes > MAX_GLOBAL_RETAINED_BYTES:
                raise BridgeConflictError(
                    "The Attribute Reporting server retained-byte quota is full; "
                    "try again after operator cleanup."
                )

    def _assert_request_taxonomy_is_current(
        self,
        request_payload: Mapping[str, Any],
    ) -> None:
        """Reject queued work if its central taxonomy pin became stale."""

        scope = request_payload.get("scope")
        pinned = request_payload.get("taxonomy_snapshot")
        if not isinstance(scope, Mapping) or not isinstance(pinned, Mapping):
            raise BridgeValidationError("Evidence request has invalid taxonomy scope.")
        snapshot = self.taxonomy_snapshot(
            str(scope.get("category_key") or ""),
            actor_email=str(request_payload.get("requested_by") or ""),
        )
        if (
            pinned.get("version") != snapshot["version"]
            or pinned.get("sha256") != snapshot["sha256"]
        ):
            raise BridgeConflictError(
                "The taxonomy changed while the evidence job was queued; create a fresh job."
            )

    def _capture_mapping_state_snapshot(
        self,
        *,
        retailer: str,
        category_key: str,
        schema_suffix: str = "mapping_state_snapshot",
    ) -> dict[str, Any]:
        states = self.store_factory().read_attribute_mapping_states(
            retailer=retailer,
            category_key=category_key,
            source="codex",
        )
        return _mapping_state_payload(
            states,
            retailer=retailer,
            category_key=category_key,
            captured_at=self.now(),
            schema_suffix=schema_suffix,
        )

    def _capture_brand_fit_mapping_state_snapshot(
        self,
        *,
        retailer: str,
        retailer_category_keys: Sequence[str],
        brand_source_retailer: str,
        owned_category_keys: Sequence[str],
    ) -> dict[str, Any]:
        """Pin accepted mappings for the retailer-presence and owned-catalog scopes."""

        identities = sorted(
            {
                *((retailer, category) for category in retailer_category_keys),
                *(
                    (brand_source_retailer, category)
                    for category in owned_category_keys
                ),
            }
        )
        scopes = [
            self._capture_mapping_state_snapshot(
                retailer=scope_retailer,
                category_key=scope_category,
            )
            for scope_retailer, scope_category in identities
        ]
        state_core = [
            {
                "scope": dict(snapshot["scope"]),
                "state_sha256": str(snapshot["state_sha256"]),
            }
            for snapshot in scopes
        ]
        payload = {
            "schema_version": f"{SCHEMA_PREFIX}.brand_fit_mapping_state_snapshot.v1",
            "captured_at": self.now(),
            "scopes": scopes,
        }
        payload["state_sha256"] = _canonical_sha256({"scopes": state_core})
        return payload

    def _capture_product_data_snapshot(
        self,
        *,
        retailer: str,
        retailer_category_keys: Sequence[str],
        brand_source_retailer: str,
        owned_category_keys: Sequence[str],
    ) -> dict[str, Any]:
        """Hash the exact cached product/attribute blobs used by Brand Fit."""

        entries = self.store_factory().read_attribute_cache_entries()
        missing = [
            name for name in REQUIRED_PRODUCT_CACHE_ENTRIES if name not in entries
        ]
        if missing:
            raise BridgeConflictError(
                "The product attribute cache is incomplete for Brand Fit."
            )
        entry_rows: list[dict[str, Any]] = []
        for name in REQUIRED_PRODUCT_CACHE_ENTRIES:
            raw_payload, generated_at = entries[name]
            payload_bytes = bytes(raw_payload)
            generated_text = str(generated_at or "").strip()
            if not generated_text:
                raise BridgeConflictError(
                    "The product attribute cache has no generation timestamp."
                )
            try:
                _parse_timestamp(generated_text)
            except BridgeValidationError as exc:
                raise BridgeConflictError(
                    "The product attribute cache has an invalid generation timestamp."
                ) from exc
            entry_rows.append(
                {
                    "name": name,
                    "payload_sha256": hashlib.sha256(payload_bytes).hexdigest(),
                    "payload_size_bytes": len(payload_bytes),
                    "generated_at": generated_text,
                }
            )
        generated_at_values = {row["generated_at"] for row in entry_rows}
        if len(generated_at_values) != 1:
            raise BridgeConflictError(
                "The product attribute cache entries are from different generations."
            )
        batch_generated_at = next(iter(generated_at_values))
        scope = {
            "retailer": retailer,
            "retailer_category_keys": list(retailer_category_keys),
            "brand_source_retailer": brand_source_retailer,
            "owned_category_keys": list(owned_category_keys),
        }
        core = {
            "scope": scope,
            "batch_generated_at": batch_generated_at,
            "entries": entry_rows,
        }
        return {
            "schema_version": f"{SCHEMA_PREFIX}.product_data_snapshot.v1",
            **core,
            "snapshot_sha256": _canonical_sha256(core),
            "read_at": self.now(),
        }

    @staticmethod
    def _assert_submission_mapping_state_is_current(
        current_snapshot: Mapping[str, Any],
        submission_receipt: Mapping[str, Any],
        *,
        retailer: str,
        category_key: str,
    ) -> None:
        result = submission_receipt.get("mapping_state_result")
        if not isinstance(result, Mapping):
            raise BridgeConflictError(
                "Mapping submission has no accepted database-state result."
            )
        current_states = _mapping_states_from_payload(
            current_snapshot,
            expected_retailer=retailer,
            expected_category_key=category_key,
        )
        result_states = _mapping_states_from_payload(
            result,
            expected_retailer=retailer,
            expected_category_key=category_key,
        )
        if any(
            current_states.get(identity, ()) != expected_rows
            for identity, expected_rows in result_states.items()
        ):
            raise BridgeConflictError(
                "Accepted mappings changed after this submission; rebuild from the current mapping operation."
            )

    def taxonomy_snapshot(
        self, category_key: str, *, actor_email: str
    ) -> dict[str, Any]:
        """Return one category branch pinned to the central taxonomy checksum."""

        actor = _clean_actor(actor_email)
        category_key = _clean_scope_value(category_key, field="category key")
        taxonomy = self.taxonomy_loader()
        version = str(taxonomy.get("version") or "").strip()
        if not version:
            raise BridgeValidationError("The central taxonomy has no version.")
        branch = _category_branch(taxonomy, category_key)
        active_leaves = []
        for attribute in branch.get("attributes") or []:
            if not isinstance(attribute, dict):
                continue
            active_leaves.append(
                {
                    "attribute_id": str(attribute.get("id") or ""),
                    "selection": str(attribute.get("selection") or "single"),
                    "values": _active_leaf_values(attribute.get("nodes")),
                }
            )
        return {
            "schema_version": f"{SCHEMA_PREFIX}.taxonomy_snapshot.v1",
            "version": version,
            "sha256": _canonical_sha256(taxonomy),
            "category_key": category_key,
            "category": branch,
            "active_leaves": active_leaves,
            "requested_by": actor,
        }

    def create_evidence_job(
        self,
        *,
        retailer: str,
        category_key: str,
        taxonomy_version: str,
        taxonomy_sha256: str,
        actor_email: str,
        mapping_submission_id: str | None = None,
    ) -> dict[str, Any]:
        """Serialize job creation so the per-actor quota is a hard limit."""

        actor = _clean_actor(actor_email)
        with _blocking_file_lock(self._actor_operation_lock("evidence-jobs", actor)):
            return self._create_evidence_job_locked(
                retailer=retailer,
                category_key=category_key,
                taxonomy_version=taxonomy_version,
                taxonomy_sha256=taxonomy_sha256,
                actor_email=actor,
                mapping_submission_id=mapping_submission_id,
            )

    def _create_evidence_job_locked(
        self,
        *,
        retailer: str,
        category_key: str,
        taxonomy_version: str,
        taxonomy_sha256: str,
        actor_email: str,
        mapping_submission_id: str | None = None,
    ) -> dict[str, Any]:
        """Register an immutable current-database evidence-pack build."""

        actor = _clean_actor(actor_email)
        self._prune_expired_artifacts()
        self._enforce_retained_byte_quotas(actor=actor)
        self._enforce_actor_quota(
            "evidence_jobs",
            actor=actor,
            maximum=MAX_ACTOR_EVIDENCE_JOBS,
        )
        retailer = _clean_scope_value(retailer, field="retailer")
        category_key = _clean_scope_value(category_key, field="category key")
        snapshot = self.taxonomy_snapshot(category_key, actor_email=actor)
        if (
            taxonomy_version != snapshot["version"]
            or taxonomy_sha256 != snapshot["sha256"]
        ):
            raise BridgeConflictError(
                "The taxonomy changed; retrieve a fresh snapshot before building."
            )
        submission_id = None
        if mapping_submission_id:
            submission_id = _clean_scope_value(
                mapping_submission_id,
                field="mapping submission id",
            )
            submission_dir = self._artifact_dir("submissions", submission_id)
            submission_receipt = _load_json(submission_dir / "receipt.json")
            if str(submission_receipt.get("submitted_by") or "").casefold() != actor:
                raise BridgeNotFoundError(
                    "Attribute Reporting artifact is unavailable."
                )
            if any(
                not (submission_dir / file_name).is_file()
                for file_name in _PROVENANCE_FILES
            ) or any(
                not (submission_dir / source_name).is_file()
                for _target_name, source_name in _SERVER_PROVENANCE_FILES
            ):
                raise BridgeConflictError("Mapping provenance is incomplete.")
            if submission_receipt.get("operation_id") != submission_id:
                raise BridgeConflictError("Mapping submission receipt is inconsistent.")
            provenance_tasks = _load_json(submission_dir / "mapping_tasks.json")
            provenance_decisions = _load_json(submission_dir / "mapping_decisions.json")
            provenance_validated = _load_json(
                submission_dir / "validated_mappings.json"
            )
            provenance_review = _load_json(submission_dir / "mapping_review.json")
            provenance_scope = provenance_tasks.get("scope")
            if not isinstance(provenance_scope, dict) or (
                provenance_scope.get("retailer") != retailer
                or provenance_scope.get("category_key") != category_key
            ):
                raise BridgeConflictError(
                    "Mapping submission belongs to another retailer/category scope."
                )
            taxonomy = self.taxonomy_loader()
            validated_check = self.mapping_engine.validate_mapping_payloads(
                provenance_tasks,
                provenance_decisions,
                taxonomy=taxonomy,
            )
            review_check = self.mapping_engine.validate_mapping_review_payloads(
                provenance_tasks,
                provenance_decisions,
                provenance_validated,
                provenance_review,
                taxonomy=taxonomy,
            )
            expected_operation_id = _canonical_sha256(
                {
                    "validation_sha256": validated_check["validation_sha256"],
                    "mapping_review_validation_sha256": review_check[
                        "review_validation_sha256"
                    ],
                }
            )
            if (
                expected_operation_id != submission_id
                or submission_receipt.get("validation_sha256")
                != validated_check["validation_sha256"]
                or submission_receipt.get("mapping_review_validation_sha256")
                != review_check["review_validation_sha256"]
                or review_check.get("review_state")
                not in {"approved", "approved_with_caveats"}
            ):
                raise BridgeConflictError(
                    "Mapping submission provenance failed current validation."
                )
            current_mapping_state = self._capture_mapping_state_snapshot(
                retailer=retailer,
                category_key=category_key,
            )
            self._assert_submission_mapping_state_is_current(
                current_mapping_state,
                submission_receipt,
                retailer=retailer,
                category_key=category_key,
            )
        job_id = uuid.uuid4().hex
        job_dir = self.root / "evidence_jobs" / job_id
        request_payload = {
            "schema_version": f"{SCHEMA_PREFIX}.evidence_request.v1",
            "job_id": job_id,
            "scope": {
                "retailer": retailer,
                "category_key": category_key,
                "snapshot_mode": "current_database",
            },
            "taxonomy_snapshot": {
                "version": taxonomy_version,
                "sha256": taxonomy_sha256,
            },
            "requested_by": actor,
            "requested_at": self.now(),
            "mapping_submission_id": submission_id,
        }
        with self._lock:
            job_dir.mkdir(parents=True, exist_ok=False)
            _atomic_write_json(job_dir / "request.json", request_payload)
            status_payload = {
                "schema_version": f"{SCHEMA_PREFIX}.evidence_status.v1",
                "job_id": job_id,
                "status": "pending",
                "attempt": 0,
                "requested_at": request_payload["requested_at"],
            }
            _atomic_write_json(job_dir / "status.json", status_payload)
        return status_payload

    def build_evidence_job(self, job_id: str) -> None:
        """Build only when per-actor and global worker capacity is available."""

        job_dir = self._artifact_dir("evidence_jobs", job_id)
        request_payload = _load_json(job_dir / "request.json")
        actor = _clean_actor(str(request_payload.get("requested_by") or ""))
        actor_lock = self._actor_operation_lock("evidence-builds", actor)
        global_slots = [
            self.root / ".build-slots" / f"global-{index}.lock"
            for index in range(MAX_GLOBAL_CONCURRENT_EVIDENCE_BUILDS)
        ]
        with _nonblocking_file_lock(actor_lock) as actor_capacity:
            if not actor_capacity:
                return
            with _first_available_file_lock(global_slots) as global_capacity:
                if not global_capacity:
                    return
                self._build_evidence_job_locked(job_id)

    def _build_evidence_job_locked(self, job_id: str) -> None:
        """Build or resume a registered job once across processes/workers."""

        job_dir = self._artifact_dir("evidence_jobs", job_id)
        with _nonblocking_file_lock(job_dir / ".build.lock") as acquired:
            if not acquired:
                return
            prior_status = _load_json(job_dir / "status.json")
            if prior_status.get("status") == "ready":
                return
            request_payload = _load_json(job_dir / "request.json")
            actor = _clean_actor(str(request_payload.get("requested_by") or ""))
            status_path = job_dir / "status.json"
            started_at = self.now()
            attempt = int(prior_status.get("attempt") or 0) + 1
            for directory in (job_dir / "build", job_dir / "portable"):
                if directory.exists():
                    shutil.rmtree(directory)
            for artifact in (
                job_dir / "evidence_pack.zip",
                job_dir / "receipt.json",
                job_dir / "mapping_state_snapshot.json",
            ):
                artifact.unlink(missing_ok=True)
            _atomic_write_json(
                status_path,
                {
                    "schema_version": f"{SCHEMA_PREFIX}.evidence_status.v1",
                    "job_id": job_id,
                    "status": "running",
                    "attempt": attempt,
                    "started_at": started_at,
                },
            )
            scope = request_payload["scope"]
            try:
                self._assert_request_taxonomy_is_current(request_payload)
                retailer = str(scope["retailer"])
                category_key = str(scope["category_key"])
                mapping_state_before = self._capture_mapping_state_snapshot(
                    retailer=retailer,
                    category_key=category_key,
                )
                submission_id = request_payload.get("mapping_submission_id")
                provenance_dir = (
                    self._artifact_dir("submissions", str(submission_id))
                    if submission_id
                    else None
                )
                submission_receipt = (
                    _load_json(provenance_dir / "receipt.json")
                    if provenance_dir is not None
                    else None
                )
                if submission_receipt is not None:
                    self._assert_submission_mapping_state_is_current(
                        mapping_state_before,
                        submission_receipt,
                        retailer=retailer,
                        category_key=category_key,
                    )
                package_dir = self.package_builder(
                    retailer,
                    category_key,
                    job_dir / "build",
                ).resolve()
                if not package_dir.is_dir() or job_dir not in package_dir.parents:
                    raise RuntimeError(
                        "Package builder returned an invalid output path."
                    )
                package_zip = job_dir / "evidence_pack.zip"
                integrity_path = package_dir / "package_integrity.json"
                integrity = _load_json(integrity_path)
                if str(integrity.get("status") or "").casefold() != "pass":
                    raise RuntimeError("Evidence package integrity is not pass.")
                self._assert_request_taxonomy_is_current(request_payload)
                mapping_state_after = self._capture_mapping_state_snapshot(
                    retailer=retailer,
                    category_key=category_key,
                )
                if (
                    mapping_state_before["state_sha256"]
                    != mapping_state_after["state_sha256"]
                ):
                    raise BridgeConflictError(
                        "Accepted mappings changed while the evidence package was being built; create a fresh job."
                    )
                if submission_receipt is not None:
                    self._assert_submission_mapping_state_is_current(
                        mapping_state_after,
                        submission_receipt,
                        retailer=retailer,
                        category_key=category_key,
                    )
                _atomic_write_json(
                    job_dir / "mapping_state_snapshot.json",
                    mapping_state_before,
                )
                sanitization = _build_portable_package(
                    package_dir,
                    job_dir / "portable",
                    package_zip,
                    provenance_dir=provenance_dir,
                )
                receipt = {
                    "schema_version": f"{SCHEMA_PREFIX}.evidence_receipt.v1",
                    "job_id": job_id,
                    "scope": dict(scope),
                    "taxonomy_snapshot": dict(request_payload["taxonomy_snapshot"]),
                    "package_sha256": _file_sha256(package_zip),
                    "package_size_bytes": package_zip.stat().st_size,
                    "package_integrity_sha256": _file_sha256(integrity_path),
                    "server_sanitization_receipt_sha256": _file_sha256(
                        job_dir / "portable" / "server_sanitization_receipt.json"
                    ),
                    "image_policy": sanitization["image_policy"],
                    "mapping_submission_id": submission_id,
                    "mapping_state_snapshot_sha256": mapping_state_before[
                        "state_sha256"
                    ],
                    "built_at": self.now(),
                }
                _atomic_write_json(job_dir / "receipt.json", receipt)
                self._enforce_retained_byte_quotas(actor=actor)
                _atomic_write_json(
                    status_path,
                    {
                        "schema_version": f"{SCHEMA_PREFIX}.evidence_status.v1",
                        "job_id": job_id,
                        "status": "ready",
                        "attempt": attempt,
                        "started_at": started_at,
                        "completed_at": receipt["built_at"],
                        "package_sha256": receipt["package_sha256"],
                        "package_size_bytes": receipt["package_size_bytes"],
                    },
                )
            except (
                BridgeConflictError,
                BridgeNotFoundError,
                OSError,
                RuntimeError,
                ValueError,
            ) as exc:
                LOGGER.exception("Attribute Reporting evidence job %s failed", job_id)
                for directory in (job_dir / "build", job_dir / "portable"):
                    shutil.rmtree(directory, ignore_errors=True)
                for artifact in (
                    job_dir / "evidence_pack.zip",
                    job_dir / "receipt.json",
                    job_dir / "mapping_state_snapshot.json",
                ):
                    artifact.unlink(missing_ok=True)
                _atomic_write_json(
                    status_path,
                    {
                        "schema_version": f"{SCHEMA_PREFIX}.evidence_status.v1",
                        "job_id": job_id,
                        "status": "failed",
                        "attempt": attempt,
                        "started_at": started_at,
                        "completed_at": self.now(),
                        "error": "Evidence package build failed.",
                        "error_type": type(exc).__name__,
                    },
                )

    def evidence_status(self, job_id: str, *, actor_email: str) -> dict[str, Any]:
        """Return public build status for an actor-owned job."""

        job_dir = self._owned_artifact_dir(
            "evidence_jobs", job_id, actor_email=actor_email
        )
        return _load_json(job_dir / "status.json")

    def evidence_download(
        self, job_id: str, *, actor_email: str
    ) -> tuple[Path, dict[str, Any]]:
        """Return one ready package path and its immutable receipt."""

        job_dir = self._owned_artifact_dir(
            "evidence_jobs", job_id, actor_email=actor_email
        )
        status_payload = _load_json(job_dir / "status.json")
        if status_payload.get("status") != "ready":
            raise BridgeConflictError("The evidence package is not ready.")
        receipt = _load_json(job_dir / "receipt.json")
        package_path = job_dir / "evidence_pack.zip"
        if not package_path.is_file() or _file_sha256(package_path) != receipt.get(
            "package_sha256"
        ):
            raise BridgeConflictError("The evidence package failed its checksum.")
        return package_path, receipt

    def create_brand_fit_job(
        self,
        *,
        source_evidence_job_id: str,
        brand_source_retailer: str,
        brand_name: str,
        retailer_report_sha256: str,
        retailer_report_verdict: str,
        actor_email: str,
        owned_category_keys: Sequence[str] | None = None,
        retailer_category_keys: Sequence[str] | None = None,
    ) -> dict[str, Any]:
        """Register an actor-owned Brand Fit build against checked retailer signals."""

        actor = _clean_actor(actor_email)
        with _blocking_file_lock(self._actor_operation_lock("brand-fit-jobs", actor)):
            self._prune_expired_artifacts()
            self._enforce_retained_byte_quotas(actor=actor)
            self._enforce_actor_quota(
                "brand_fit_jobs",
                actor=actor,
                maximum=MAX_ACTOR_BRAND_FIT_JOBS,
            )
            source_id = _clean_scope_value(
                source_evidence_job_id,
                field="source evidence job id",
            )
            source_dir = self._owned_artifact_dir(
                "evidence_jobs",
                source_id,
                actor_email=actor,
            )
            source_status = _load_json(source_dir / "status.json")
            if source_status.get("status") != "ready":
                raise BridgeConflictError(
                    "The source Retailer Signals evidence package is not ready."
                )
            source_request = _load_json(source_dir / "request.json")
            self._assert_request_taxonomy_is_current(source_request)
            _source_zip, source_receipt = self.evidence_download(
                source_id,
                actor_email=actor,
            )
            source_scope = source_request.get("scope")
            taxonomy_snapshot = source_request.get("taxonomy_snapshot")
            if not isinstance(source_scope, Mapping) or not isinstance(
                taxonomy_snapshot,
                Mapping,
            ):
                raise BridgeConflictError("Source evidence scope is invalid.")
            retailer = _clean_scope_value(
                str(source_scope.get("retailer") or ""),
                field="retailer",
            )
            category_key = _clean_scope_value(
                str(source_scope.get("category_key") or ""),
                field="category key",
            )
            source_retailer = _clean_scope_value(
                brand_source_retailer,
                field="brand source retailer",
            )
            clean_brand_name = _clean_display_text(brand_name, field="brand name")
            report_hash = retailer_report_sha256.strip().casefold()
            if not re.fullmatch(r"[0-9a-f]{64}", report_hash):
                raise BridgeValidationError("Invalid retailer report sha256.")
            if retailer_report_verdict not in {
                "Correct",
                "Correct with caveats",
            }:
                raise BridgeValidationError(
                    "Brand Fit requires a checked retailer report with verdict Correct or Correct with caveats."
                )

            def clean_category_scope(
                values: Sequence[str] | None,
                *,
                field: str,
            ) -> list[str]:
                raw_values = list(values or (category_key,))
                if not raw_values or len(raw_values) > 32:
                    raise BridgeValidationError(f"Invalid {field}.")
                return list(
                    dict.fromkeys(
                        _clean_scope_value(value, field=field) for value in raw_values
                    )
                )

            owned_categories = clean_category_scope(
                owned_category_keys,
                field="owned category key",
            )
            retailer_categories = clean_category_scope(
                retailer_category_keys,
                field="retailer category key",
            )
            job_id = uuid.uuid4().hex
            job_dir = self.root / "brand_fit_jobs" / job_id
            requested_at = self.now()
            request_payload = {
                "schema_version": f"{SCHEMA_PREFIX}.brand_fit_request.v1",
                "job_id": job_id,
                "source_evidence_job_id": source_id,
                "source_evidence_package_sha256": source_receipt["package_sha256"],
                "scope": {
                    "retailer": retailer,
                    "category_key": category_key,
                    "brand_source_retailer": source_retailer,
                    "brand_name": clean_brand_name,
                    "owned_category_keys": owned_categories,
                    "retailer_category_keys": retailer_categories,
                    "retailer_presence_mode": "current_database_snapshot",
                },
                "taxonomy_snapshot": {
                    "version": str(taxonomy_snapshot.get("version") or ""),
                    "sha256": str(taxonomy_snapshot.get("sha256") or ""),
                },
                "source_retailer_report": {
                    "sha256": report_hash,
                    "verdict": retailer_report_verdict,
                },
                "requested_by": actor,
                "requested_at": requested_at,
            }
            with self._lock:
                job_dir.mkdir(parents=True, exist_ok=False)
                _atomic_write_json(job_dir / "request.json", request_payload)
                status_payload = {
                    "schema_version": f"{SCHEMA_PREFIX}.brand_fit_status.v1",
                    "job_id": job_id,
                    "status": "pending",
                    "attempt": 0,
                    "requested_at": requested_at,
                }
                _atomic_write_json(job_dir / "status.json", status_payload)
            return status_payload

    def build_brand_fit_job(self, job_id: str) -> None:
        """Build Brand Fit when actor and shared evidence-worker capacity is free."""

        job_dir = self._artifact_dir("brand_fit_jobs", job_id)
        request_payload = _load_json(job_dir / "request.json")
        actor = _clean_actor(str(request_payload.get("requested_by") or ""))
        actor_lock = self._actor_operation_lock("brand-fit-builds", actor)
        global_slots = [
            self.root / ".build-slots" / f"global-{index}.lock"
            for index in range(MAX_GLOBAL_CONCURRENT_EVIDENCE_BUILDS)
        ]
        with _nonblocking_file_lock(actor_lock) as actor_capacity:
            if not actor_capacity:
                return
            with _first_available_file_lock(global_slots) as global_capacity:
                if not global_capacity:
                    return
                self._build_brand_fit_job_locked(job_id)

    def _build_brand_fit_job_locked(self, job_id: str) -> None:
        """Build or resume one immutable Brand Fit package."""

        job_dir = self._artifact_dir("brand_fit_jobs", job_id)
        with _nonblocking_file_lock(job_dir / ".build.lock") as acquired:
            if not acquired:
                return
            prior_status = _load_json(job_dir / "status.json")
            if prior_status.get("status") == "ready":
                return
            request_payload = _load_json(job_dir / "request.json")
            actor = _clean_actor(str(request_payload.get("requested_by") or ""))
            status_path = job_dir / "status.json"
            started_at = self.now()
            attempt = int(prior_status.get("attempt") or 0) + 1
            for directory in (
                job_dir / "build",
                job_dir / "portable",
                job_dir / "source_retailer_package",
            ):
                shutil.rmtree(directory, ignore_errors=True)
            for artifact in (
                job_dir / "brand_fit_pack.zip",
                job_dir / "receipt.json",
                job_dir / "mapping_state_snapshot.json",
                job_dir / "product_data_snapshot.json",
            ):
                artifact.unlink(missing_ok=True)
            _atomic_write_json(
                status_path,
                {
                    "schema_version": f"{SCHEMA_PREFIX}.brand_fit_status.v1",
                    "job_id": job_id,
                    "status": "running",
                    "attempt": attempt,
                    "started_at": started_at,
                },
            )
            try:
                self._assert_request_taxonomy_is_current(request_payload)
                scope = request_payload.get("scope")
                if not isinstance(scope, Mapping):
                    raise BridgeValidationError("Brand Fit request scope is invalid.")
                retailer = str(scope["retailer"])
                category_key = str(scope["category_key"])
                brand_source_retailer = str(scope["brand_source_retailer"])
                owned_category_keys = [
                    str(value) for value in scope["owned_category_keys"]
                ]
                retailer_category_keys = [
                    str(value) for value in scope["retailer_category_keys"]
                ]
                source_id = str(request_payload["source_evidence_job_id"])
                source_dir = self._owned_artifact_dir(
                    "evidence_jobs",
                    source_id,
                    actor_email=actor,
                )
                source_request = _load_json(source_dir / "request.json")
                source_scope = source_request.get("scope")
                if not isinstance(source_scope, Mapping):
                    raise BridgeConflictError(
                        "The source Retailer Signals evidence scope is invalid."
                    )
                if (
                    source_scope.get("retailer") != retailer
                    or source_scope.get("category_key") != category_key
                    or source_request.get("taxonomy_snapshot")
                    != request_payload.get("taxonomy_snapshot")
                ):
                    raise BridgeConflictError(
                        "The source Retailer Signals evidence scope changed."
                    )
                source_zip, source_receipt = self.evidence_download(
                    source_id,
                    actor_email=actor,
                )
                if source_receipt.get("package_sha256") != request_payload.get(
                    "source_evidence_package_sha256"
                ):
                    raise BridgeConflictError(
                        "The source Retailer Signals evidence package changed."
                    )
                product_data_before = self._capture_product_data_snapshot(
                    retailer=retailer,
                    retailer_category_keys=retailer_category_keys,
                    brand_source_retailer=brand_source_retailer,
                    owned_category_keys=owned_category_keys,
                )
                mapping_state_before = self._capture_brand_fit_mapping_state_snapshot(
                    retailer=retailer,
                    retailer_category_keys=retailer_category_keys,
                    brand_source_retailer=brand_source_retailer,
                    owned_category_keys=owned_category_keys,
                )
                source_package_dir = job_dir / "source_retailer_package"
                _extract_server_package(source_zip, source_package_dir)
                source_sanitization = _load_json(
                    source_package_dir / "server_sanitization_receipt.json"
                )
                if source_sanitization.get("image_policy") != (
                    "urls_only_no_image_bytes"
                ):
                    raise BridgeConflictError(
                        "Source Retailer Signals package is not URL-only."
                    )
                report_payload = request_payload.get("source_retailer_report")
                if not isinstance(report_payload, Mapping):
                    raise BridgeValidationError(
                        "Brand Fit retailer report binding is invalid."
                    )
                report_binding = dict(report_payload)
                source_evidence_binding = {
                    "job_id": source_id,
                    "package_sha256": str(source_receipt["package_sha256"]),
                }
                presence_snapshot = {
                    "mode": "current_database_snapshot",
                    "read_at": str(product_data_before["read_at"]),
                }
                package_dir = self.brand_fit_builder(
                    brand_source_retailer=brand_source_retailer,
                    brand_name=str(scope["brand_name"]),
                    category_key=category_key,
                    retailer=retailer,
                    innovation_package_dir=source_package_dir,
                    output_root=job_dir / "build",
                    owned_category_keys=owned_category_keys,
                    retailer_category_keys=retailer_category_keys,
                    source_retailer_report=report_binding,
                    source_retailer_evidence=source_evidence_binding,
                    retailer_presence_snapshot=presence_snapshot,
                    product_data_snapshot=product_data_before,
                    mapping_state_snapshot=mapping_state_before,
                ).resolve()
                if not package_dir.is_dir() or job_dir not in package_dir.parents:
                    raise RuntimeError(
                        "Brand Fit builder returned an invalid output path."
                    )
                integrity_path = package_dir / "package_integrity.json"
                integrity = _load_json(integrity_path)
                if str(integrity.get("status") or "").casefold() != "pass":
                    raise RuntimeError("Brand Fit package integrity is not pass.")
                summary = _load_json(package_dir / "summary.json")
                if summary.get("source_retailer_report") != report_binding:
                    raise RuntimeError(
                        "Brand Fit package did not preserve the retailer report binding."
                    )
                if summary.get("source_retailer_evidence") != source_evidence_binding:
                    raise RuntimeError(
                        "Brand Fit package did not preserve the source evidence binding."
                    )
                if summary.get("retailer_presence") != presence_snapshot:
                    raise RuntimeError(
                        "Brand Fit package did not label the database presence snapshot."
                    )
                if summary.get("product_data_snapshot") != product_data_before:
                    raise RuntimeError(
                        "Brand Fit package did not preserve product-data snapshot provenance."
                    )
                built_mapping_state = _load_json(
                    package_dir / "mapping_state_snapshot.json"
                )
                if (
                    summary.get("mapping_state_snapshot_sha256")
                    != mapping_state_before["state_sha256"]
                    or built_mapping_state != mapping_state_before
                ):
                    raise RuntimeError(
                        "Brand Fit package did not preserve accepted mapping-state provenance."
                    )
                built_manifest_path = package_dir / "pack_manifest.json"
                built_manifest = _load_json(built_manifest_path)
                built_manifest_files = sorted(
                    path.relative_to(package_dir).as_posix()
                    for path in package_dir.rglob("*")
                    if path.is_file() and path != built_manifest_path
                )
                if (
                    built_manifest.get("summary") != summary
                    or built_manifest.get("files") != built_manifest_files
                ):
                    raise RuntimeError(
                        "Brand Fit package manifest does not describe its exact builder output."
                    )
                summary_sources = summary.get("sources")
                if not isinstance(summary_sources, Mapping) or (
                    summary_sources.get("retailer_live_check_enabled") is not False
                    or summary_sources.get("retailer_presence_mode")
                    != "current_database_snapshot"
                ):
                    raise RuntimeError(
                        "Brand Fit package mislabeled current retailer presence."
                    )
                self._assert_request_taxonomy_is_current(request_payload)
                product_data_after = self._capture_product_data_snapshot(
                    retailer=retailer,
                    retailer_category_keys=retailer_category_keys,
                    brand_source_retailer=brand_source_retailer,
                    owned_category_keys=owned_category_keys,
                )
                if (
                    product_data_before["snapshot_sha256"]
                    != product_data_after["snapshot_sha256"]
                ):
                    raise BridgeConflictError(
                        "Product or attribute cache data changed while Brand Fit was being built; create a fresh job."
                    )
                mapping_state_after = self._capture_brand_fit_mapping_state_snapshot(
                    retailer=retailer,
                    retailer_category_keys=retailer_category_keys,
                    brand_source_retailer=brand_source_retailer,
                    owned_category_keys=owned_category_keys,
                )
                if (
                    mapping_state_before["state_sha256"]
                    != mapping_state_after["state_sha256"]
                ):
                    raise BridgeConflictError(
                        "Accepted mappings changed while Brand Fit was being built; create a fresh job."
                    )
                _atomic_write_json(
                    job_dir / "mapping_state_snapshot.json",
                    mapping_state_before,
                )
                _atomic_write_json(
                    job_dir / "product_data_snapshot.json",
                    product_data_before,
                )
                package_zip = job_dir / "brand_fit_pack.zip"
                sanitization = _build_portable_package(
                    package_dir,
                    job_dir / "portable",
                    package_zip,
                    private_path_roots=(job_dir, source_package_dir),
                    regenerate_brand_fit_manifest=True,
                )
                portable_summary = _load_json(job_dir / "portable" / "summary.json")
                if portable_summary.get("source_retailer_report") != report_binding:
                    raise RuntimeError(
                        "Portable Brand Fit package lost the retailer report binding."
                    )
                if (
                    portable_summary.get("source_retailer_evidence")
                    != source_evidence_binding
                ):
                    raise RuntimeError(
                        "Portable Brand Fit package lost the source evidence binding."
                    )
                if portable_summary.get("product_data_snapshot") != product_data_before:
                    raise RuntimeError(
                        "Portable Brand Fit package lost product-data snapshot provenance."
                    )
                portable_mapping_state = _load_json(
                    job_dir / "portable" / "mapping_state_snapshot.json"
                )
                if (
                    portable_summary.get("mapping_state_snapshot_sha256")
                    != mapping_state_before["state_sha256"]
                    or portable_mapping_state != mapping_state_before
                ):
                    raise RuntimeError(
                        "Portable Brand Fit package lost accepted mapping-state provenance."
                    )
                portable_manifest_path = job_dir / "portable" / "pack_manifest.json"
                portable_manifest = _load_json(portable_manifest_path)
                portable_manifest_files = sorted(
                    path.relative_to(job_dir / "portable").as_posix()
                    for path in (job_dir / "portable").rglob("*")
                    if path.is_file() and path != portable_manifest_path
                )
                if (
                    portable_manifest.get("package_type")
                    != built_manifest.get("package_type")
                    or portable_manifest.get("summary") != portable_summary
                    or portable_manifest.get("files") != portable_manifest_files
                ):
                    raise RuntimeError(
                        "Portable Brand Fit package manifest does not describe the exact handoff."
                    )
                if (job_dir / "portable" / "prompt_for_pro.txt").exists():
                    raise RuntimeError(
                        "Portable Brand Fit package contains a legacy prompt."
                    )
                legacy_phrases = ("NotebookLM", "for Pro", "Pro can", "to Pro")
                for text_path in (job_dir / "portable").rglob("*"):
                    if not text_path.is_file() or text_path.suffix.casefold() not in {
                        ".md",
                        ".txt",
                    }:
                        continue
                    text_value = text_path.read_text(
                        encoding="utf-8",
                        errors="replace",
                    )
                    if any(phrase in text_value for phrase in legacy_phrases):
                        raise RuntimeError(
                            "Portable Brand Fit package contains legacy report-service instructions."
                        )
                receipt = {
                    "schema_version": f"{SCHEMA_PREFIX}.brand_fit_receipt.v1",
                    "job_id": job_id,
                    "source_evidence_job_id": source_id,
                    "source_evidence_package_sha256": source_receipt["package_sha256"],
                    "source_retailer_report": report_binding,
                    "source_retailer_evidence": source_evidence_binding,
                    "scope": dict(scope),
                    "taxonomy_snapshot": dict(request_payload["taxonomy_snapshot"]),
                    "retailer_presence": presence_snapshot,
                    "product_data_snapshot": product_data_before,
                    "product_data_snapshot_sha256": product_data_before[
                        "snapshot_sha256"
                    ],
                    "mapping_state_snapshot_sha256": mapping_state_before[
                        "state_sha256"
                    ],
                    "package_sha256": _file_sha256(package_zip),
                    "package_size_bytes": package_zip.stat().st_size,
                    "package_integrity_sha256": _file_sha256(integrity_path),
                    "server_sanitization_receipt_sha256": _file_sha256(
                        job_dir / "portable" / "server_sanitization_receipt.json"
                    ),
                    "image_policy": sanitization["image_policy"],
                    "model_execution": "none",
                    "built_at": self.now(),
                }
                _atomic_write_json(job_dir / "receipt.json", receipt)
                self._enforce_retained_byte_quotas(actor=actor)
                _atomic_write_json(
                    status_path,
                    {
                        "schema_version": f"{SCHEMA_PREFIX}.brand_fit_status.v1",
                        "job_id": job_id,
                        "status": "ready",
                        "attempt": attempt,
                        "started_at": started_at,
                        "completed_at": receipt["built_at"],
                        "package_sha256": receipt["package_sha256"],
                        "package_size_bytes": receipt["package_size_bytes"],
                    },
                )
            except (
                BridgeConflictError,
                BridgeNotFoundError,
                OSError,
                RuntimeError,
                KeyError,
                TypeError,
                ValueError,
            ) as exc:
                LOGGER.exception("Attribute Reporting Brand Fit job %s failed", job_id)
                for directory in (
                    job_dir / "build",
                    job_dir / "portable",
                    job_dir / "source_retailer_package",
                ):
                    shutil.rmtree(directory, ignore_errors=True)
                for artifact in (
                    job_dir / "brand_fit_pack.zip",
                    job_dir / "receipt.json",
                    job_dir / "mapping_state_snapshot.json",
                    job_dir / "product_data_snapshot.json",
                ):
                    artifact.unlink(missing_ok=True)
                _atomic_write_json(
                    status_path,
                    {
                        "schema_version": f"{SCHEMA_PREFIX}.brand_fit_status.v1",
                        "job_id": job_id,
                        "status": "failed",
                        "attempt": attempt,
                        "started_at": started_at,
                        "completed_at": self.now(),
                        "error": "Brand Fit package build failed.",
                        "error_type": type(exc).__name__,
                    },
                )

    def brand_fit_status(self, job_id: str, *, actor_email: str) -> dict[str, Any]:
        """Return public build status for one actor-owned Brand Fit job."""

        job_dir = self._owned_artifact_dir(
            "brand_fit_jobs",
            job_id,
            actor_email=actor_email,
        )
        return _load_json(job_dir / "status.json")

    def brand_fit_download(
        self,
        job_id: str,
        *,
        actor_email: str,
    ) -> tuple[Path, dict[str, Any]]:
        """Return one checksum-verified URL-only Brand Fit package."""

        job_dir = self._owned_artifact_dir(
            "brand_fit_jobs",
            job_id,
            actor_email=actor_email,
        )
        status_payload = _load_json(job_dir / "status.json")
        if status_payload.get("status") != "ready":
            raise BridgeConflictError("The Brand Fit package is not ready.")
        receipt = _load_json(job_dir / "receipt.json")
        package_path = job_dir / "brand_fit_pack.zip"
        if not package_path.is_file() or _file_sha256(package_path) != receipt.get(
            "package_sha256"
        ):
            raise BridgeConflictError("The Brand Fit package failed its checksum.")
        return package_path, receipt

    def create_mapping_workset(
        self,
        *,
        evidence_job_id: str,
        taxonomy_version: str,
        taxonomy_sha256: str,
        actor_email: str,
        mapping_mode: str = "unresolved",
        correction_reason: str | None = None,
    ) -> dict[str, Any]:
        """Serialize workset creation so the per-actor quota is a hard limit."""

        actor = _clean_actor(actor_email)
        with _blocking_file_lock(self._actor_operation_lock("worksets", actor)):
            return self._create_mapping_workset_locked(
                evidence_job_id=evidence_job_id,
                taxonomy_version=taxonomy_version,
                taxonomy_sha256=taxonomy_sha256,
                actor_email=actor,
                mapping_mode=mapping_mode,
                correction_reason=correction_reason,
            )

    def _create_mapping_workset_locked(
        self,
        *,
        evidence_job_id: str,
        taxonomy_version: str,
        taxonomy_sha256: str,
        actor_email: str,
        mapping_mode: str = "unresolved",
        correction_reason: str | None = None,
    ) -> dict[str, Any]:
        """Create an immutable unresolved or explicit correction workset."""

        actor = _clean_actor(actor_email)
        if mapping_mode not in {"unresolved", "correction"}:
            raise BridgeValidationError("Unsupported mapping workset mode.")
        normalized_correction_reason = str(correction_reason or "").strip()
        if mapping_mode == "correction":
            if not normalized_correction_reason:
                raise BridgeValidationError(
                    "A correction workset requires an audit reason."
                )
            if len(normalized_correction_reason) > 1_000:
                raise BridgeValidationError("The correction reason is too long.")
        elif normalized_correction_reason:
            raise BridgeValidationError(
                "A correction reason is valid only for a correction workset."
            )
        self._prune_expired_artifacts()
        self._enforce_retained_byte_quotas(actor=actor)
        self._enforce_actor_quota(
            "worksets",
            actor=actor,
            maximum=MAX_ACTOR_WORKSETS,
        )
        job_dir = self._owned_artifact_dir(
            "evidence_jobs", evidence_job_id, actor_email=actor
        )
        status_payload = _load_json(job_dir / "status.json")
        if status_payload.get("status") != "ready":
            raise BridgeConflictError("The evidence package is not ready.")
        request_payload = _load_json(job_dir / "request.json")
        category_key = str(request_payload["scope"]["category_key"])
        snapshot = self.taxonomy_snapshot(category_key, actor_email=actor)
        if (
            taxonomy_version != snapshot["version"]
            or taxonomy_sha256 != snapshot["sha256"]
        ):
            raise BridgeConflictError(
                "The taxonomy changed; rebuild the evidence package and workset."
            )
        retailer = str(request_payload["scope"]["retailer"])
        mapping_state_snapshot = _load_json(job_dir / "mapping_state_snapshot.json")
        mapping_states = _mapping_states_from_payload(
            mapping_state_snapshot,
            expected_retailer=retailer,
            expected_category_key=category_key,
        )
        evidence_receipt = _load_json(job_dir / "receipt.json")
        if evidence_receipt.get(
            "mapping_state_snapshot_sha256"
        ) != mapping_state_snapshot.get("state_sha256"):
            raise BridgeConflictError(
                "The evidence job mapping-state snapshot is inconsistent."
            )
        package_dirs = [
            path.parent for path in (job_dir / "build").rglob("package_integrity.json")
        ]
        if len(package_dirs) != 1:
            raise BridgeConflictError("The evidence package source is unavailable.")
        taxonomy = self.taxonomy_loader()
        workset_seed = {
            "evidence_job_id": evidence_job_id,
            "requested_by": actor,
            "created_at": self.now(),
            "nonce": uuid.uuid4().hex,
        }
        workset_id = _canonical_sha256(workset_seed)
        workset_dir = self.root / "worksets" / workset_id
        server_tasks_path = workset_dir / "mapping_tasks.server.json"
        tasks_path = workset_dir / "mapping_tasks.json"
        workset_dir.mkdir(parents=True, exist_ok=False)
        try:
            server_source_tasks = self.mapping_engine.create_mapping_tasks(
                package_dirs[0],
                taxonomy,
                server_tasks_path,
                max_tasks=0,
                include_resolved=mapping_mode == "correction",
            )
            _atomic_write_json(server_tasks_path, server_source_tasks)
            public_source_tasks = self.mapping_engine.create_mapping_tasks(
                job_dir / "portable",
                taxonomy,
                tasks_path,
                max_tasks=0,
                include_resolved=mapping_mode == "correction",
            )
            _assert_bounded_json(
                server_source_tasks,
                label="Private mapping workset",
            )
            _assert_bounded_json(
                public_source_tasks,
                label="Public mapping workset",
            )
            if mapping_mode == "correction":
                server_tasks = _select_correction_workset(
                    self.mapping_engine,
                    server_source_tasks,
                    mapping_states,
                )
                tasks = _select_correction_workset(
                    self.mapping_engine,
                    public_source_tasks,
                    mapping_states,
                )
                _atomic_write_json(tasks_path, tasks)
            else:
                server_tasks = server_source_tasks
                tasks = public_source_tasks
            task_rows = tasks.get("tasks")
            if not isinstance(task_rows, list) or len(task_rows) > MAX_MAPPING_TASKS:
                raise BridgeConflictError(
                    "The complete mapping workset exceeds the server task limit."
                )
            correction_precondition: dict[str, Any] | None = None
            if mapping_mode == "correction":
                if not task_rows:
                    raise BridgeConflictError(
                        "There are no report-effective accepted Codex mappings to correct."
                    )
                expected_states: dict[
                    AttributeMappingIdentity,
                    tuple[AttributeMappingStateRow, ...],
                ] = {}
                for task in task_rows:
                    if not isinstance(task, Mapping):
                        raise BridgeValidationError(
                            "Mapping workset contains an invalid task."
                        )
                    identity = _mapping_identity_from_task(task)
                    if identity in expected_states:
                        raise BridgeConflictError(
                            "Correction workset contains a duplicate database identity."
                        )
                    expected_states[identity] = mapping_states.get(identity, ())
                correction_precondition = _mapping_state_payload(
                    expected_states,
                    retailer=retailer,
                    category_key=category_key,
                    captured_at=str(mapping_state_snapshot["captured_at"]),
                    schema_suffix="correction_precondition",
                )
                _atomic_write_json(
                    workset_dir / "correction_precondition.json",
                    correction_precondition,
                )
            _validate_public_tasks_match_server(server_tasks, tasks)
            # The public workset is built from the sanitized URL-only package,
            # so its row hashes match local hydration.  Its server path remains
            # opaque; the raw source-bound workset stays private for submit-time
            # regeneration and comparison.
            scope = tasks.get("scope")
            if not isinstance(scope, dict):
                raise BridgeValidationError("Mapping workset has no source scope.")
            scope["source_package"] = f"evidence-job:{evidence_job_id}"
            _atomic_write_json(tasks_path, tasks)
            tasks_sha256 = _canonical_sha256(tasks)
            metadata = {
                "schema_version": f"{SCHEMA_PREFIX}.mapping_workset.v1",
                "workset_id": workset_id,
                "workset_sha256": tasks_sha256,
                "evidence_job_id": evidence_job_id,
                "taxonomy_snapshot": {
                    "version": taxonomy_version,
                    "sha256": taxonomy_sha256,
                },
                "requested_by": actor,
                "created_at": workset_seed["created_at"],
                "status": "no_work" if not task_rows else "open",
                "mapping_mode": mapping_mode,
                "mapping_state_snapshot_sha256": mapping_state_snapshot["state_sha256"],
                "correction_precondition_sha256": (
                    correction_precondition["state_sha256"]
                    if correction_precondition is not None
                    else None
                ),
                "correction_reason": (
                    normalized_correction_reason
                    if mapping_mode == "correction"
                    else None
                ),
            }
            _atomic_write_json(workset_dir / "metadata.json", metadata)
            self._enforce_retained_byte_quotas(actor=actor)
        except (OSError, RuntimeError, ValueError):
            shutil.rmtree(workset_dir, ignore_errors=True)
            raise
        return {**metadata, "mapping_tasks": tasks}

    def get_mapping_workset(
        self, workset_id: str, *, actor_email: str
    ) -> dict[str, Any]:
        """Return an immutable actor-owned workset and its tasks."""

        workset_dir = self._owned_artifact_dir(
            "worksets", workset_id, actor_email=actor_email
        )
        metadata = _load_json(workset_dir / "metadata.json")
        tasks = _load_json(workset_dir / "mapping_tasks.json")
        if _canonical_sha256(tasks) != metadata.get("workset_sha256"):
            raise BridgeConflictError("The mapping workset failed its checksum.")
        return {**metadata, "mapping_tasks": tasks}

    def submit_mapping_results(
        self,
        *,
        workset_id: str,
        workset_sha256: str,
        idempotency_key: str,
        mapping_tasks: Mapping[str, Any],
        decisions: Mapping[str, Any],
        validated_mappings: Mapping[str, Any],
        mapping_review: Mapping[str, Any],
        actor_email: str,
    ) -> dict[str, Any]:
        """Serialize acceptance so quota and idempotency checks are race-safe."""

        actor = _clean_actor(actor_email)
        with _blocking_file_lock(self._actor_operation_lock("submissions", actor)):
            return self._submit_mapping_results_locked(
                workset_id=workset_id,
                workset_sha256=workset_sha256,
                idempotency_key=idempotency_key,
                mapping_tasks=mapping_tasks,
                decisions=decisions,
                validated_mappings=validated_mappings,
                mapping_review=mapping_review,
                actor_email=actor,
            )

    def _submit_mapping_results_locked(
        self,
        *,
        workset_id: str,
        workset_sha256: str,
        idempotency_key: str,
        mapping_tasks: Mapping[str, Any],
        decisions: Mapping[str, Any],
        validated_mappings: Mapping[str, Any],
        mapping_review: Mapping[str, Any],
        actor_email: str,
    ) -> dict[str, Any]:
        """Validate and atomically accept one complete Codex mapping submission."""

        actor = _clean_actor(actor_email)
        self._prune_expired_artifacts()
        self._enforce_retained_byte_quotas(actor=actor)
        artifact_sizes = [
            _assert_bounded_json(mapping_tasks, label="Mapping tasks"),
            _assert_bounded_json(decisions, label="Mapping decisions"),
            _assert_bounded_json(
                validated_mappings,
                label="Validated mappings",
            ),
            _assert_bounded_json(mapping_review, label="Mapping review"),
        ]
        if sum(artifact_sizes) > MAX_MAPPING_SUBMISSION_BYTES:
            raise BridgeValidationError(
                "The complete mapping submission exceeds the server byte limit."
            )
        self._enforce_retained_byte_quotas(
            actor=actor,
            additional_bytes=sum(artifact_sizes) + 2 * 1024 * 1024,
        )
        submitted_task_rows = mapping_tasks.get("tasks")
        if not isinstance(submitted_task_rows, list) or not submitted_task_rows:
            raise BridgeValidationError(
                "The mapping submission must contain at least one task."
            )
        if len(submitted_task_rows) > MAX_MAPPING_TASKS:
            raise BridgeValidationError(
                "The mapping submission exceeds the server task limit."
            )
        workset = self.get_mapping_workset(workset_id, actor_email=actor)
        mapping_mode = str(workset.get("mapping_mode") or "unresolved")
        if mapping_mode not in {"unresolved", "correction"}:
            raise BridgeConflictError("The mapping workset mode is invalid.")
        correction_reason = str(workset.get("correction_reason") or "").strip()
        if mapping_mode == "correction" and not correction_reason:
            raise BridgeConflictError("The correction workset has no audit reason.")
        if workset_sha256 != workset["workset_sha256"]:
            raise BridgeConflictError("The submitted workset checksum is stale.")
        stored_tasks = workset["mapping_tasks"]
        tasks = _validate_enriched_mapping_tasks(stored_tasks, mapping_tasks)
        category_key = str(tasks["taxonomy_snapshot"]["category_key"])
        scope = tasks.get("scope")
        if not isinstance(scope, Mapping):
            raise BridgeValidationError("Mapping tasks have no source scope.")
        retailer = str(scope.get("retailer") or "")
        if not retailer:
            raise BridgeValidationError("Mapping tasks have no retailer scope.")
        taxonomy = self.taxonomy_loader()
        snapshot = self.taxonomy_snapshot(category_key, actor_email=actor)
        pinned = workset["taxonomy_snapshot"]
        if (
            pinned.get("version") != snapshot["version"]
            or pinned.get("sha256") != snapshot["sha256"]
        ):
            raise BridgeConflictError(
                "The taxonomy changed; rebuild the evidence package and workset."
            )
        workset_dir = self._owned_artifact_dir(
            "worksets", workset_id, actor_email=actor
        )
        expected_existing_source_states: (
            dict[
                AttributeMappingIdentity,
                tuple[AttributeMappingStateRow, ...],
            ]
            | None
        ) = None
        if mapping_mode == "correction":
            correction_precondition = _load_json(
                workset_dir / "correction_precondition.json"
            )
            if correction_precondition.get("state_sha256") != workset.get(
                "correction_precondition_sha256"
            ):
                raise BridgeConflictError(
                    "The correction workset precondition changed."
                )
            expected_existing_source_states = _mapping_states_from_payload(
                correction_precondition,
                expected_retailer=retailer,
                expected_category_key=category_key,
            )
        server_source_tasks = _load_json(workset_dir / "mapping_tasks.server.json")
        portable_dir = (
            self._artifact_dir("evidence_jobs", workset["evidence_job_id"]) / "portable"
        )
        regenerated_path = workset_dir / (
            f".mapping_tasks.public-recheck-{uuid.uuid4().hex}.json"
        )
        try:
            regenerated_source_tasks = self.mapping_engine.create_mapping_tasks(
                portable_dir,
                taxonomy,
                regenerated_path,
                max_tasks=0,
                include_resolved=mapping_mode == "correction",
            )
        finally:
            regenerated_path.unlink(missing_ok=True)
        if mapping_mode == "correction":
            if expected_existing_source_states is None:
                raise BridgeConflictError(
                    "The correction workset has no pinned database precondition."
                )
            server_tasks = _select_correction_workset(
                self.mapping_engine,
                server_source_tasks,
                expected_existing_source_states,
            )
            regenerated_tasks = _select_correction_workset(
                self.mapping_engine,
                regenerated_source_tasks,
                expected_existing_source_states,
            )
        else:
            server_tasks = server_source_tasks
            regenerated_tasks = regenerated_source_tasks
        if "generated_at" in stored_tasks:
            regenerated_tasks["generated_at"] = stored_tasks["generated_at"]
        else:
            regenerated_tasks.pop("generated_at", None)
        regenerated_scope = regenerated_tasks.get("scope")
        if not isinstance(regenerated_scope, dict):
            raise BridgeValidationError(
                "Regenerated mapping workset has no source scope."
            )
        regenerated_scope["source_package"] = (
            f"evidence-job:{workset['evidence_job_id']}"
        )
        if regenerated_tasks != stored_tasks:
            raise BridgeConflictError(
                "The portable evidence package changed; create a fresh mapping workset."
            )
        _validate_public_tasks_match_server(server_tasks, regenerated_tasks)
        source_scope = self.mapping_engine.verify_mapping_tasks_against_source(
            server_source_tasks, taxonomy
        )
        validated = self.mapping_engine.validate_mapping_payloads(
            tasks,
            decisions,
            taxonomy=taxonomy,
        )
        review_validation = self.mapping_engine.validate_mapping_review_payloads(
            tasks,
            decisions,
            validated_mappings,
            mapping_review,
            taxonomy=taxonomy,
        )
        review_state = str(review_validation.get("review_state") or "")
        if review_state not in {"approved", "approved_with_caveats"}:
            raise BridgeConflictError(
                "Independent semantic mapping review does not approve submission."
            )
        operation_id = _canonical_sha256(
            {
                "validation_sha256": validated["validation_sha256"],
                "mapping_review_validation_sha256": review_validation[
                    "review_validation_sha256"
                ],
            }
        )
        if not re.fullmatch(r"[0-9a-f]{64}", idempotency_key):
            raise BridgeValidationError("The idempotency key must be a SHA-256 value.")
        if idempotency_key != operation_id:
            raise BridgeValidationError(
                "The idempotency key must bind the validated mapping and review."
            )
        submission_dir = self.root / "submissions" / operation_id
        receipt_path = submission_dir / "receipt.json"
        metadata_path = submission_dir / "metadata.json"
        if (
            submission_dir.exists()
            and not metadata_path.exists()
            and not receipt_path.exists()
        ):
            if submission_dir.is_symlink() or not submission_dir.is_dir():
                raise BridgeConflictError(
                    "The mapping submission reservation is invalid."
                )
            shutil.rmtree(submission_dir)
        if receipt_path.is_file():
            receipt = _load_json(receipt_path)
            if (
                receipt.get("submitted_by") != actor
                or receipt.get("workset_id") != workset_id
            ):
                raise BridgeConflictError(
                    "The idempotency key belongs to another submission."
                )
            return receipt

        existing_metadata: dict[str, Any] | None = None
        if metadata_path.is_file():
            existing_metadata = _load_json(metadata_path)
            if (
                existing_metadata.get("operation_id") != operation_id
                or existing_metadata.get("submitted_by") != actor
                or existing_metadata.get("workset_id") != workset_id
            ):
                raise BridgeConflictError(
                    "The pending mapping submission is inconsistent."
                )
            submitted_at = str(existing_metadata.get("submitted_at") or "")
            _parse_timestamp(submitted_at)
        else:
            self._enforce_actor_quota(
                "submissions",
                actor=actor,
                maximum=MAX_ACTOR_SUBMISSIONS,
            )
            submitted_at = self.now()
            _parse_timestamp(submitted_at)
        value_records: list[AttributeValueRecord] = []
        audit_records: list[AttributeAuditRecord] = []
        for raw_mapping in validated.get("mappings") or []:
            if not isinstance(raw_mapping, Mapping):
                raise BridgeValidationError("Validated mapping row is invalid.")
            mapping = dict(raw_mapping)
            for spec in self.mapping_apply_engine.mapping_record_specs(mapping):
                value_records.append(
                    AttributeValueRecord(
                        retailer=str(mapping["retailer"]),
                        row_type=str(mapping["row_type"]),
                        parent_product_id=str(mapping["parent_product_id"]),
                        variant_id=str(mapping.get("variant_id") or ""),
                        category_key=str(mapping["category_key"]),
                        attribute_id=str(spec["attribute_id"]),
                        attribute_label=str(spec["attribute_label"]) or None,
                        value=spec["value"],
                        oov_candidate=spec["oov_candidate"],
                        note=spec["note"],
                        source="codex",
                        updated_at=submitted_at,
                    )
                )
                audit_records.append(
                    AttributeAuditRecord(
                        timestamp=submitted_at,
                        source="codex",
                        row_type=str(mapping["row_type"]),
                        retailer=str(mapping["retailer"]),
                        parent_product_id=str(mapping["parent_product_id"]),
                        variant_id=str(mapping.get("variant_id") or ""),
                        attribute_id=str(spec["attribute_id"]),
                        value=spec["value"],
                        decision_rule=str(spec["decision_rule"]),
                        evidence_json=json.dumps(
                            {
                                "task_id": mapping["task_id"],
                                "base_attribute_id": mapping["attribute_id"],
                                "leaf_value_id": spec["leaf_value_id"],
                                "selected_value_ids": mapping["value_ids"],
                                "selected_value_labels": mapping["value_labels"],
                                "taxonomy_version": snapshot["version"],
                                "taxonomy_sha256": snapshot["sha256"],
                                "tasks_sha256": validated["tasks_sha256"],
                                "decisions_sha256": validated["decisions_sha256"],
                                "validation_sha256": validated["validation_sha256"],
                                "mapping_review_sha256": review_validation[
                                    "mapping_review_sha256"
                                ],
                                "mapping_review_validation_sha256": review_validation[
                                    "review_validation_sha256"
                                ],
                                "mapping_review_state": review_state,
                                "mapping_reviewer": review_validation["reviewer"],
                                "source_scope": source_scope,
                                "reason": mapping["reason"],
                                "confidence": mapping["confidence"],
                                "agent": validated["agent"],
                                "submission": {
                                    "actor_email": actor,
                                    "workset_id": workset_id,
                                    "workset_sha256": workset_sha256,
                                    "submitted_at": submitted_at,
                                    "mapping_mode": mapping_mode,
                                    "correction_reason": (
                                        correction_reason
                                        if mapping_mode == "correction"
                                        else None
                                    ),
                                },
                            },
                            ensure_ascii=False,
                            sort_keys=True,
                        ),
                        category_key=str(mapping["category_key"]),
                    )
                )
        submission_artifacts = {
            "mapping_tasks.json": tasks,
            "mapping_decisions.json": decisions,
            "validated_mappings.json": validated_mappings,
            "mapping_review.json": mapping_review,
            "mapping_review_validation.json": review_validation,
        }

        def operation_evidence_for(
            *,
            committed_timestamp: str,
            state_result: Mapping[str, Any],
        ) -> dict[str, Any]:
            return {
                "schema_version": (f"{SCHEMA_PREFIX}.mapping_operation_evidence.v1"),
                "operation_id": operation_id,
                "workset_id": workset_id,
                "workset_sha256": workset_sha256,
                "submitted_by": actor,
                "submitted_at": committed_timestamp,
                "mapping_count": validated["mapping_count"],
                "attribute_value_record_count": len(value_records),
                "validation_sha256": validated["validation_sha256"],
                "mapping_review_sha256": review_validation["mapping_review_sha256"],
                "mapping_review_validation_sha256": review_validation[
                    "review_validation_sha256"
                ],
                "mapping_review_state": review_state,
                "mapping_reviewer": review_validation["reviewer"],
                "mapping_mode": mapping_mode,
                "correction_reason": (
                    correction_reason if mapping_mode == "correction" else None
                ),
                "correction_precondition_sha256": workset.get(
                    "correction_precondition_sha256"
                ),
                "mapping_state_result_sha256": _canonical_sha256(state_result),
                "taxonomy_snapshot": {
                    "version": snapshot["version"],
                    "sha256": snapshot["sha256"],
                },
                "artifact_sha256": {
                    name: _canonical_sha256(artifact)
                    for name, artifact in submission_artifacts.items()
                },
            }

        mapping_state_result = _mapping_state_payload(
            _mapping_states_from_value_records(value_records),
            retailer=retailer,
            category_key=category_key,
            captured_at=submitted_at,
            schema_suffix="mapping_state_result",
        )
        operation_evidence = operation_evidence_for(
            committed_timestamp=submitted_at,
            state_result=mapping_state_result,
        )
        if existing_metadata is None:
            submission_dir.mkdir(parents=True, exist_ok=False)
            _atomic_write_json(
                metadata_path,
                {
                    "schema_version": f"{SCHEMA_PREFIX}.mapping_submission_metadata.v1",
                    "operation_id": operation_id,
                    "workset_id": workset_id,
                    "submitted_by": actor,
                    "submitted_at": submitted_at,
                    "status": "pending",
                },
            )
        elif existing_metadata.get("status") != "pending":
            raise BridgeConflictError(
                "A receipt-less mapping submission must remain pending."
            )
        for file_name, artifact in submission_artifacts.items():
            artifact_path = submission_dir / file_name
            if artifact_path.exists():
                if not artifact_path.is_file() or _load_json(artifact_path) != artifact:
                    raise BridgeConflictError(
                        "The pending mapping submission artifacts changed."
                    )
            else:
                _atomic_write_json(artifact_path, artifact)
        try:
            operation_result = self.store_factory().upsert_attribute_values_with_audit(
                value_records,
                audit_records,
                operation_id=operation_id,
                reject_existing_source_values=mapping_mode == "unresolved",
                replace_existing_source_values=mapping_mode == "correction",
                expected_existing_source_states=expected_existing_source_states,
                operation_evidence=operation_evidence,
                return_operation_result=True,
            )
        except AttributeMappingConflictError as exc:
            shutil.rmtree(submission_dir, ignore_errors=True)
            raise BridgeConflictError(str(exc)) from exc
        except ValueError:
            shutil.rmtree(submission_dir, ignore_errors=True)
            raise
        if not isinstance(operation_result, AttributeMappingOperationResult):
            shutil.rmtree(submission_dir, ignore_errors=True)
            raise BridgeValidationError(
                "The mapping store did not return a durable operation result."
            )
        committed_at = operation_result.committed_at
        _parse_timestamp(committed_at)
        if committed_at != submitted_at:
            for record in value_records:
                record.updated_at = committed_at
            for record in audit_records:
                record.timestamp = committed_at
            submitted_at = committed_at
        mapping_state_result = _mapping_state_payload(
            _mapping_states_from_value_records(value_records),
            retailer=retailer,
            category_key=category_key,
            captured_at=submitted_at,
            schema_suffix="mapping_state_result",
        )
        operation_evidence = operation_evidence_for(
            committed_timestamp=submitted_at,
            state_result=mapping_state_result,
        )
        try:
            committed_marker = json.loads(operation_result.operation_evidence_json)
        except (TypeError, json.JSONDecodeError) as exc:
            raise BridgeConflictError(
                "The durable mapping operation evidence is unreadable."
            ) from exc
        if committed_marker != {
            "operation_id": operation_id,
            "operation_evidence": operation_evidence,
        }:
            raise BridgeConflictError(
                "The durable mapping operation evidence does not match this submission."
            )
        receipt = {
            "schema_version": f"{SCHEMA_PREFIX}.mapping_submission_receipt.v1",
            "operation_id": operation_id,
            "workset_id": workset_id,
            "workset_sha256": workset_sha256,
            "submitted_by": actor,
            "submitted_at": submitted_at,
            "mapping_count": validated["mapping_count"],
            "attribute_value_record_count": len(value_records),
            "database_write": (
                "applied" if operation_result.applied else "already_applied"
            ),
            "validation_sha256": validated["validation_sha256"],
            "mapping_review_sha256": review_validation["mapping_review_sha256"],
            "mapping_review_validation_sha256": review_validation[
                "review_validation_sha256"
            ],
            "mapping_review_state": review_state,
            "mapping_reviewer": review_validation["reviewer"],
            "mapping_mode": mapping_mode,
            "correction_reason": (
                correction_reason if mapping_mode == "correction" else None
            ),
            "correction_precondition_sha256": workset.get(
                "correction_precondition_sha256"
            ),
            "mapping_state_result": mapping_state_result,
            "taxonomy_snapshot": {
                "version": snapshot["version"],
                "sha256": snapshot["sha256"],
            },
        }
        _atomic_write_json(receipt_path, receipt)
        _atomic_write_json(
            metadata_path,
            {
                "schema_version": f"{SCHEMA_PREFIX}.mapping_submission_metadata.v1",
                "operation_id": operation_id,
                "workset_id": workset_id,
                "submitted_by": actor,
                "submitted_at": submitted_at,
                "status": "accepted",
                "receipt_sha256": _file_sha256(receipt_path),
            },
        )
        return receipt

    def _artifact_dir(self, collection: str, artifact_id: str) -> Path:
        clean_id = _clean_scope_value(artifact_id, field="artifact id")
        path = self.root / collection / clean_id
        if not path.is_dir():
            raise BridgeNotFoundError("Attribute Reporting artifact is unavailable.")
        return path

    def _owned_artifact_dir(
        self,
        collection: str,
        artifact_id: str,
        *,
        actor_email: str,
    ) -> Path:
        actor = _clean_actor(actor_email)
        path = self._artifact_dir(collection, artifact_id)
        metadata_name = (
            "request.json"
            if collection in {"evidence_jobs", "brand_fit_jobs"}
            else "metadata.json"
        )
        metadata = _load_json(path / metadata_name)
        owner = str(metadata.get("requested_by") or "").casefold()
        if owner != actor:
            # Do not reveal whether another user's private artifact exists.
            raise BridgeNotFoundError("Attribute Reporting artifact is unavailable.")
        return path


@lru_cache(maxsize=1)
def get_attribute_reporting_bridge() -> AttributeReportingBridge:
    """Return the process-wide bridge rooted in private server data."""

    configured = os.getenv("ATTRIBUTE_REPORTING_BRIDGE_ROOT", "").strip()
    root = (
        Path(configured)
        if configured
        else Path.home() / ".local" / "share" / "mparanza" / "attribute_reporting"
    )
    return AttributeReportingBridge(root)
