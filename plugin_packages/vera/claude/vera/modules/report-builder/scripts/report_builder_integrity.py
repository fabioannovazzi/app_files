"""Local source and handoff integrity controls for Report Builder.

These controls are deterministic because byte identity, canonical JSON
identity, path containment, and exact receipt replay are mechanically
verifiable. They do not decide whether a source or report conclusion is
professionally sufficient.
"""

from __future__ import annotations

import hashlib
import json
import os
import stat
import unicodedata
import zipfile
from collections.abc import Mapping, Sequence
from io import BytesIO
from pathlib import Path, PurePosixPath
from typing import Any

try:
    from .implementation_contract import (
        build_implementation_receipts,
        validate_implementation_contract,
    )
    from .physical_output_set import (
        expected_output_paths,
        validate_output_set,
    )
    from .prepared_contract import validate_prepared_report
except ImportError:  # pragma: no cover - supports direct script imports
    from implementation_contract import (
        build_implementation_receipts,
        validate_implementation_contract,
    )
    from physical_output_set import expected_output_paths, validate_output_set
    from prepared_contract import validate_prepared_report

__all__ = [
    "INTEGRITY_FILE_NAME",
    "SOURCE_INDEX_FILE_NAME",
    "canonical_json_sha256",
    "load_source_index",
    "seal_review_integrity",
    "validate_review_integrity",
    "validate_source_index",
    "write_source_index",
]

INTEGRITY_FILE_NAME = "review_integrity.json"
SOURCE_INDEX_FILE_NAME = "source_index.json"
INTEGRITY_SCHEMA = "report_builder.review_integrity.v4"
SOURCE_INDEX_SCHEMA = "report_builder.source_index.v2"
_REVIEW_FILES = (
    "run_intake.json",
    "review_payload.json",
    "final_artifacts.json",
)
_OPTIONAL_REVIEW_FILES = (
    "ui_decisions.json",
    "applied_decisions.json",
)
_PUBLIC_OUTPUT_ALLOWLIST = {
    "report_tables.json",
    "report_tables.xlsx",
    "report_analysis.json",
    "report_draft.md",
    "report.docx",
    "report_audit.json",
    "used_recipe.json",
    "numeric_evidence_ledger.json",
    "source_receipts.json",
    "review_handoff.md",
}


def _canonical_json_bytes(value: Any) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")


def canonical_json_sha256(value: Any) -> str:
    """Return a stable digest for a JSON-compatible value."""

    return hashlib.sha256(_canonical_json_bytes(value)).hexdigest()


def _checkpoint(value: object, *, required: bool) -> str | None:
    checkpoint = str(value or "").strip()
    if not checkpoint:
        if required:
            raise ValueError("Report Builder predecessor checkpoint is required")
        return None
    if len(checkpoint) != 64 or any(
        character not in "0123456789abcdef" for character in checkpoint
    ):
        raise ValueError("Report Builder predecessor checkpoint is malformed")
    return checkpoint


def _write_json(path: Path, value: Mapping[str, Any]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            value,
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
            allow_nan=False,
        )
        + "\n",
        encoding="utf-8",
    )
    return path


def _read_object(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"Expected JSON object: {path}")
    return payload


def _file_snapshot(path: Path) -> tuple[int, str]:
    """Hash one stable regular-file snapshot."""

    source = Path(path)
    if source.is_symlink():
        raise ValueError(f"Integrity artifact cannot be a symlink: {source}")
    digest = hashlib.sha256()
    byte_count = 0
    try:
        with source.open("rb") as handle:
            before = os.fstat(handle.fileno())
            if not stat.S_ISREG(before.st_mode) or before.st_nlink != 1:
                raise ValueError(
                    f"Integrity artifact must be an ordinary single-link file: {source}"
                )
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                byte_count += len(chunk)
                digest.update(chunk)
            after = os.fstat(handle.fileno())
    except FileNotFoundError as exc:
        raise ValueError(f"Integrity artifact is missing: {source}") from exc
    identity_before = (
        before.st_dev,
        before.st_ino,
        before.st_size,
        before.st_mtime_ns,
        before.st_nlink,
    )
    identity_after = (
        after.st_dev,
        after.st_ino,
        after.st_size,
        after.st_mtime_ns,
        after.st_nlink,
    )
    if identity_before != identity_after or byte_count != after.st_size:
        raise ValueError(f"Integrity artifact changed while read: {source}")
    return byte_count, digest.hexdigest()


def _contained_file(root: Path, relative_path: str) -> Path:
    relative = Path(relative_path)
    if relative.is_absolute() or ".." in relative.parts or "\\" in relative_path:
        raise ValueError(f"Integrity path must be canonical: {relative_path}")
    resolved_root = root.resolve()
    unresolved = resolved_root / relative
    if unresolved.is_symlink():
        raise ValueError(f"Integrity path cannot be a symlink: {relative_path}")
    try:
        resolved = unresolved.resolve(strict=True)
    except FileNotFoundError as exc:
        raise ValueError(f"Integrity artifact is missing: {relative_path}") from exc
    if not resolved.is_relative_to(resolved_root):
        raise ValueError(f"Integrity path escapes the output root: {relative_path}")
    return resolved


def _relative_receipt(root: Path, relative_path: str, *, role: str) -> dict[str, Any]:
    path = _contained_file(root, relative_path)
    byte_count, digest = _file_snapshot(path)
    return {
        "path": Path(relative_path).as_posix(),
        "role": role,
        "byte_count": byte_count,
        "sha256": digest,
    }


def _validate_relative_receipt(root: Path, receipt: Mapping[str, Any]) -> None:
    path_value = receipt.get("path")
    if not isinstance(path_value, str) or not path_value:
        raise ValueError("Integrity receipt path is missing")
    path = _contained_file(root, path_value)
    byte_count, digest = _file_snapshot(path)
    if receipt.get("byte_count") != byte_count or receipt.get("sha256") != digest:
        raise ValueError(f"Integrity receipt is stale: {path_value}")


def _private_source_records(
    tables: Sequence[Mapping[str, Any]],
) -> tuple[
    list[dict[str, Any]],
    list[dict[str, Any]],
    list[dict[str, Any]],
]:
    sources: dict[str, dict[str, Any]] = {}
    archive_manifests: dict[str, dict[str, Any]] = {}
    archive_member_bindings: dict[tuple[str, str], dict[str, Any]] = {}

    def add_source(source_receipt: Mapping[str, Any], artifact_id: str) -> None:
        root_path = source_receipt.get("root_path")
        receipt = source_receipt.get("receipt")
        identity_key = source_receipt.get("identity_key")
        if (
            not isinstance(root_path, str)
            or not isinstance(receipt, Mapping)
            or not isinstance(identity_key, str)
            or not identity_key
        ):
            raise ValueError(f"Malformed source receipt for {artifact_id}")
        record = {
            "artifact_id": artifact_id,
            "identity_key": identity_key,
            "root_path": root_path,
            "receipt": dict(receipt),
        }
        previous = sources.get(artifact_id)
        if previous is not None and previous != record:
            raise ValueError(f"Source artifact identity collision: {artifact_id}")
        sources[artifact_id] = record

    for table in tables:
        artifact_id = str(table.get("source_artifact_ref") or "")
        source_receipt = table.get("source_receipt")
        if artifact_id and isinstance(source_receipt, Mapping):
            add_source(source_receipt, artifact_id)
        container_receipt = table.get("container_source_receipt")
        if isinstance(container_receipt, Mapping):
            receipt = container_receipt.get("receipt")
            container_artifact_id = (
                str(receipt.get("artifact_id") or "")
                if isinstance(receipt, Mapping)
                else ""
            )
            if not container_artifact_id:
                raise ValueError("Malformed archive-container source receipt")
            add_source(container_receipt, container_artifact_id)
            raw_manifest = table.get("container_member_manifest")
            if not isinstance(raw_manifest, list):
                raise ValueError("Archive source is missing its canonical manifest")
            manifest = {
                "container_artifact_id": container_artifact_id,
                "members": raw_manifest,
            }
            previous_manifest = archive_manifests.get(container_artifact_id)
            if previous_manifest is not None and previous_manifest != manifest:
                raise ValueError("Archive member manifests conflict")
            archive_manifests[container_artifact_id] = manifest
            raw_binding = table.get("archive_member_binding")
            if not isinstance(raw_binding, Mapping):
                raise ValueError(
                    "Archive member source is missing its derivation binding"
                )
            binding = dict(raw_binding)
            member_path = binding.get("member_path")
            if (
                binding.get("container_artifact_id") != container_artifact_id
                or not isinstance(member_path, str)
                or not member_path
            ):
                raise ValueError("Archive member derivation binding is malformed")
            binding_key = (container_artifact_id, member_path)
            previous_binding = archive_member_bindings.get(binding_key)
            if previous_binding is not None and previous_binding != binding:
                raise ValueError("Archive member derivation bindings conflict")
            archive_member_bindings[binding_key] = binding
    return (
        [sources[key] for key in sorted(sources)],
        [archive_manifests[key] for key in sorted(archive_manifests)],
        [archive_member_bindings[key] for key in sorted(archive_member_bindings)],
    )


def write_source_index(
    output_dir: Path,
    tables: Sequence[Mapping[str, Any]],
) -> Path:
    """Persist private source locations for later exact receipt replay."""

    output_root = Path(output_dir)
    sources, archive_manifests, archive_member_bindings = _private_source_records(
        tables
    )
    if not sources:
        raise ValueError("Report Builder source index cannot be empty")
    content = {
        "schema_version": SOURCE_INDEX_SCHEMA,
        "sources": sources,
        "archive_manifests": archive_manifests,
        "archive_member_bindings": archive_member_bindings,
    }
    return _write_json(
        output_root / SOURCE_INDEX_FILE_NAME,
        {**content, "content_sha256": canonical_json_sha256(content)},
    )


def load_source_index(output_dir: Path) -> dict[str, Any]:
    """Load and validate the private source-index structure."""

    path = Path(output_dir) / SOURCE_INDEX_FILE_NAME
    payload = _read_object(path)
    if payload.get("schema_version") != SOURCE_INDEX_SCHEMA:
        raise ValueError("Unsupported Report Builder source-index schema")
    sources = payload.get("sources")
    if not isinstance(sources, list) or not sources:
        raise ValueError("Report Builder source index has no sources")
    archive_manifests = payload.get("archive_manifests")
    archive_member_bindings = payload.get("archive_member_bindings")
    if not isinstance(archive_manifests, list) or not isinstance(
        archive_member_bindings, list
    ):
        raise ValueError("Report Builder source index archive bindings are malformed")
    content = {
        "schema_version": SOURCE_INDEX_SCHEMA,
        "sources": sources,
        "archive_manifests": archive_manifests,
        "archive_member_bindings": archive_member_bindings,
    }
    if payload.get("content_sha256") != canonical_json_sha256(content):
        raise ValueError("Report Builder source-index digest is stale")
    return payload


def _validate_private_source(record: Mapping[str, Any]) -> None:
    artifact_id = record.get("artifact_id")
    identity_key = record.get("identity_key")
    root_path = record.get("root_path")
    receipt = record.get("receipt")
    if (
        not isinstance(artifact_id, str)
        or not artifact_id
        or not isinstance(identity_key, str)
        or not identity_key
        or not isinstance(root_path, str)
        or not isinstance(receipt, Mapping)
    ):
        raise ValueError("Malformed Report Builder private source record")
    path_value = receipt.get("path")
    if not isinstance(path_value, str) or not path_value:
        raise ValueError(f"Source receipt path is missing for {artifact_id}")
    source_path = _contained_file(Path(root_path), path_value)
    byte_count, digest = _file_snapshot(source_path)
    if (
        receipt.get("artifact_id") != artifact_id
        or receipt.get("byte_count") != byte_count
        or receipt.get("sha256") != digest
    ):
        raise ValueError(f"Source receipt does not match current bytes: {artifact_id}")


def _source_record_path(record: Mapping[str, Any]) -> Path:
    root_path = record.get("root_path")
    receipt = record.get("receipt")
    if not isinstance(root_path, str) or not isinstance(receipt, Mapping):
        raise ValueError("Malformed Report Builder private source record")
    path_value = receipt.get("path")
    if not isinstance(path_value, str) or not path_value:
        raise ValueError("Report Builder private source path is missing")
    return _contained_file(Path(root_path), path_value)


def _canonical_zip_member_path(member_name: str) -> str:
    normalized = unicodedata.normalize("NFC", member_name.replace("\\", "/"))
    member_path = PurePosixPath(normalized)
    if (
        not normalized
        or normalized.startswith("/")
        or member_path.is_absolute()
        or any(part in {"", ".", ".."} for part in member_path.parts)
    ):
        raise ValueError(f"Unsafe ZIP member path: {member_name}")
    return member_path.as_posix()


def _zip_manifest(source_bytes: bytes) -> list[dict[str, Any]]:
    manifest: list[dict[str, Any]] = []
    with zipfile.ZipFile(BytesIO(source_bytes)) as archive:
        seen: dict[str, str] = {}
        for member in archive.infolist():
            if member.is_dir():
                continue
            canonical = _canonical_zip_member_path(member.filename)
            identity = canonical.casefold()
            if identity in seen:
                raise ValueError(
                    "ZIP contains duplicate canonical member paths: "
                    f"{seen[identity]} and {member.filename}"
                )
            if (member.external_attr >> 16) & 0o170000 == 0o120000:
                raise ValueError(
                    f"ZIP symbolic links are not supported: {member.filename}"
                )
            digest = hashlib.sha256()
            byte_count = 0
            with archive.open(member) as source:
                for chunk in iter(lambda: source.read(1024 * 1024), b""):
                    byte_count += len(chunk)
                    digest.update(chunk)
            if byte_count != member.file_size:
                raise ValueError(f"ZIP member size changed while read: {canonical}")
            seen[identity] = member.filename
            manifest.append(
                {
                    "path": canonical,
                    "byte_count": byte_count,
                    "sha256": digest.hexdigest(),
                }
            )
    return sorted(manifest, key=lambda item: str(item["path"]).casefold())


def validate_source_index(output_dir: Path) -> dict[str, Any]:
    """Replay every persisted source receipt against current bytes."""

    payload = load_source_index(output_dir)
    seen: set[str] = set()
    sources_by_id: dict[str, Mapping[str, Any]] = {}
    for source in payload["sources"]:
        if not isinstance(source, Mapping):
            raise ValueError("Malformed Report Builder source index entry")
        artifact_id = str(source.get("artifact_id") or "")
        if artifact_id in seen:
            raise ValueError(f"Duplicate source artifact identity: {artifact_id}")
        seen.add(artifact_id)
        _validate_private_source(source)
        sources_by_id[artifact_id] = source
    manifests_by_container: dict[str, list[dict[str, Any]]] = {}
    for raw_manifest in payload["archive_manifests"]:
        if not isinstance(raw_manifest, Mapping):
            raise ValueError("Malformed Report Builder archive manifest")
        container_id = raw_manifest.get("container_artifact_id")
        members = raw_manifest.get("members")
        if (
            not isinstance(container_id, str)
            or not container_id
            or not isinstance(members, list)
            or container_id in manifests_by_container
        ):
            raise ValueError("Malformed Report Builder archive manifest")
        container = sources_by_id.get(container_id)
        if container is None:
            raise ValueError("Archive manifest container source is missing")
        current_manifest = _zip_manifest(_source_record_path(container).read_bytes())
        if members != current_manifest:
            raise ValueError("Archive member manifest does not match current bytes")
        manifests_by_container[container_id] = current_manifest
    seen_bindings: set[tuple[str, str]] = set()
    bound_member_ids: set[str] = set()
    for raw_binding in payload["archive_member_bindings"]:
        if not isinstance(raw_binding, Mapping):
            raise ValueError("Malformed Report Builder archive-member binding")
        container_id = raw_binding.get("container_artifact_id")
        member_path = raw_binding.get("member_path")
        member_id = raw_binding.get("member_artifact_id")
        if (
            not isinstance(container_id, str)
            or not isinstance(member_path, str)
            or not isinstance(member_id, str)
        ):
            raise ValueError("Malformed Report Builder archive-member binding")
        key = (container_id, member_path)
        if key in seen_bindings or member_id in bound_member_ids:
            raise ValueError("Duplicate Report Builder archive-member binding")
        seen_bindings.add(key)
        bound_member_ids.add(member_id)
        manifest = manifests_by_container.get(container_id)
        member = next(
            (item for item in manifest or [] if item["path"] == member_path),
            None,
        )
        source = sources_by_id.get(member_id)
        if member is None or source is None:
            raise ValueError("Archive-member binding has missing evidence")
        receipt = source.get("receipt")
        if not isinstance(receipt, Mapping):
            raise ValueError("Archive-member source receipt is malformed")
        if (
            raw_binding.get("byte_count") != member["byte_count"]
            or raw_binding.get("sha256") != member["sha256"]
            or receipt.get("byte_count") != member["byte_count"]
            or receipt.get("sha256") != member["sha256"]
        ):
            raise ValueError("Archive-member derivation binding is stale")
        identity_key = source.get("identity_key")
        if not isinstance(identity_key, str) or not identity_key.endswith(
            f"::{member_path}"
        ):
            raise ValueError("Archive-member source identity is stale")
    extracted_member_ids = {
        artifact_id
        for artifact_id, source in sources_by_id.items()
        if isinstance(source.get("identity_key"), str)
        and "::" in str(source.get("identity_key"))
    }
    if extracted_member_ids != bound_member_ids:
        raise ValueError("Archive-member derivation bindings are incomplete")
    return payload


def _protected_relative_paths(output_dir: Path) -> list[str]:
    final_artifacts = _read_object(Path(output_dir) / "final_artifacts.json")
    _validate_final_artifact_gallery(Path(output_dir), final_artifacts)
    outputs = final_artifacts.get("outputs")
    if not isinstance(outputs, list):
        raise ValueError("final_artifacts.json outputs must be a list")
    paths = list(_REVIEW_FILES)
    paths.append(SOURCE_INDEX_FILE_NAME)
    for optional in _OPTIONAL_REVIEW_FILES:
        if (Path(output_dir) / optional).is_file():
            paths.append(optional)
    applied_path = Path(output_dir) / "applied_decisions.json"
    if applied_path.is_file():
        applied = _read_object(applied_path)
        history_paths = applied.get("review_history_paths", [])
        if not isinstance(history_paths, list) or not all(
            isinstance(path, str) for path in history_paths
        ):
            raise ValueError("Report Builder review history paths are malformed")
        paths.extend(history_paths)
        retained_paths = applied.get("retained_review_paths", [])
        if not isinstance(retained_paths, list) or not all(
            isinstance(path, str) for path in retained_paths
        ):
            raise ValueError("Report Builder retained review paths are malformed")
        paths.extend(retained_paths)
    for output in outputs:
        if not isinstance(output, Mapping):
            raise ValueError("final_artifacts.json contains a malformed output")
        path_value = output.get("path")
        if not isinstance(path_value, str) or not path_value:
            raise ValueError("final_artifacts.json output path is missing")
        paths.append(path_value)
    return list(dict.fromkeys(paths))


def _validate_final_artifact_gallery(
    output_dir: Path,
    final_artifacts: Mapping[str, Any],
) -> None:
    """Close the public gallery against the exact current allowlisted bytes."""

    outputs = final_artifacts.get("outputs")
    if not isinstance(outputs, list):
        raise ValueError("final_artifacts.json outputs must be a list")
    seen: set[str] = set()
    for output in outputs:
        if not isinstance(output, Mapping):
            raise ValueError("final_artifacts.json contains a malformed output")
        relative_path = output.get("path")
        if (
            not isinstance(relative_path, str)
            or relative_path not in _PUBLIC_OUTPUT_ALLOWLIST
        ):
            raise ValueError(
                "final_artifacts.json contains a non-allowlisted output: "
                f"{relative_path}"
            )
        if relative_path in seen:
            raise ValueError(
                f"final_artifacts.json contains a duplicate output: {relative_path}"
            )
        seen.add(relative_path)
        path = _contained_file(output_dir, relative_path)
        byte_count, digest = _file_snapshot(path)
        if output.get("size_bytes") != byte_count or output.get("sha256") != digest:
            raise ValueError(
                "final_artifacts.json output receipt is stale: " f"{relative_path}"
            )


def seal_review_integrity(
    output_dir: Path,
    *,
    run_id: str,
    expected_predecessor_checkpoint: str | None = None,
) -> Path:
    """Seal sources, review payload, and the exact outputs shown for review."""

    output_root = Path(output_dir)
    if not run_id:
        raise ValueError("Report Builder review integrity requires a run_id")
    validate_output_set(output_root, permit_missing_integrity=True)
    validate_source_index(output_root)
    final_artifacts = _read_object(output_root / "final_artifacts.json")
    if final_artifacts.get("run_id") != run_id:
        raise ValueError("final_artifacts.json run_id does not match review state")
    _validate_final_artifact_gallery(output_root, final_artifacts)
    protected_files = [
        _relative_receipt(output_root, relative, role="review_handoff")
        for relative in _protected_relative_paths(output_root)
    ]
    payload_digests = {
        name.removesuffix(".json"): canonical_json_sha256(
            _read_object(output_root / name)
        )
        for name in _REVIEW_FILES
    }
    for optional_name in _OPTIONAL_REVIEW_FILES:
        optional_path = output_root / optional_name
        if optional_path.is_file():
            payload_digests[optional_name.removesuffix(".json")] = (
                canonical_json_sha256(_read_object(optional_path))
            )
    predecessor_checkpoint: str | None = None
    applied_path = output_root / "applied_decisions.json"
    if applied_path.is_file():
        applied = _read_object(applied_path)
        history_paths = applied.get("review_history_paths", [])
        if not isinstance(history_paths, list):
            raise ValueError("Report Builder review history paths are malformed")
        if history_paths:
            predecessor_checkpoint = _checkpoint(
                expected_predecessor_checkpoint,
                required=True,
            )
            if applied.get("predecessor_checkpoint") != predecessor_checkpoint:
                raise ValueError(
                    "Report Builder predecessor checkpoint does not match "
                    "the applied successor"
                )
            latest_history = _read_object(output_root / str(history_paths[-1]))
            if (
                latest_history.get("predecessor_checkpoint") != predecessor_checkpoint
                or not isinstance(latest_history.get("predecessor_integrity"), Mapping)
                or latest_history["predecessor_integrity"].get("content_sha256")
                != predecessor_checkpoint
            ):
                raise ValueError(
                    "Report Builder predecessor checkpoint does not match "
                    "the archived predecessor"
                )
        elif applied.get("predecessor_checkpoint") is not None:
            raise ValueError("Report Builder predecessor checkpoint is unexpected")
    elif expected_predecessor_checkpoint is not None:
        _checkpoint(expected_predecessor_checkpoint, required=False)
    implementation_receipts = build_implementation_receipts()
    prepared_validation = validate_prepared_report(output_root)
    physical_paths = sorted(expected_output_paths(output_root))
    physical_directories = sorted(
        {
            parent.as_posix()
            for relative_path in physical_paths
            for parent in Path(relative_path).parents
            if parent != Path(".")
        }
    )
    content = {
        "schema_version": INTEGRITY_SCHEMA,
        "run_id": run_id,
        "source_index": SOURCE_INDEX_FILE_NAME,
        "predecessor_checkpoint": predecessor_checkpoint,
        "protected_files": protected_files,
        "payload_digests": payload_digests,
        "implementation_artifact_refs": [
            receipt["artifact_id"] for receipt in implementation_receipts
        ],
        "implementation_receipts": implementation_receipts,
        "prepared_validation": prepared_validation,
        "physical_paths": physical_paths,
        "physical_directories": physical_directories,
    }
    path = _write_json(
        output_root / INTEGRITY_FILE_NAME,
        {**content, "content_sha256": canonical_json_sha256(content)},
    )
    validate_output_set(output_root)
    return path


def validate_review_integrity(
    output_dir: Path,
    *,
    supplied_review_payload: Mapping[str, Any] | None = None,
    supplied_run_intake: Mapping[str, Any] | None = None,
    supplied_final_artifacts: Mapping[str, Any] | None = None,
    expected_predecessor_checkpoint: str | None = None,
    source_and_review_only: bool = False,
) -> dict[str, Any]:
    """Replay persisted source/review/output receipts before review work."""

    output_root = Path(output_dir)
    payload = _read_object(output_root / INTEGRITY_FILE_NAME)
    expected_keys = {
        "schema_version",
        "run_id",
        "source_index",
        "predecessor_checkpoint",
        "protected_files",
        "payload_digests",
        "implementation_artifact_refs",
        "implementation_receipts",
        "prepared_validation",
        "physical_paths",
        "physical_directories",
        "content_sha256",
    }
    if set(payload) != expected_keys:
        raise ValueError("Report Builder review-integrity fields are not exact")
    if payload.get("schema_version") != INTEGRITY_SCHEMA:
        raise ValueError("Unsupported Report Builder review-integrity schema")
    if payload.get("source_index") != SOURCE_INDEX_FILE_NAME:
        raise ValueError("Report Builder source-index binding is stale")
    content = {
        "schema_version": INTEGRITY_SCHEMA,
        "run_id": payload.get("run_id"),
        "source_index": payload.get("source_index"),
        "predecessor_checkpoint": payload.get("predecessor_checkpoint"),
        "protected_files": payload.get("protected_files"),
        "payload_digests": payload.get("payload_digests"),
        "implementation_artifact_refs": payload.get("implementation_artifact_refs"),
        "implementation_receipts": payload.get("implementation_receipts"),
        "prepared_validation": payload.get("prepared_validation"),
        "physical_paths": payload.get("physical_paths"),
        "physical_directories": payload.get("physical_directories"),
    }
    if payload.get("content_sha256") != canonical_json_sha256(content):
        raise ValueError("Report Builder review-integrity digest is stale")
    predecessor_checkpoint = payload.get("predecessor_checkpoint")
    if predecessor_checkpoint is None:
        if expected_predecessor_checkpoint is not None:
            _checkpoint(expected_predecessor_checkpoint, required=False)
    else:
        supplied_checkpoint = _checkpoint(
            expected_predecessor_checkpoint,
            required=True,
        )
        if predecessor_checkpoint != supplied_checkpoint:
            raise ValueError(
                "Report Builder predecessor checkpoint does not match "
                "the persisted successor"
            )
    validate_implementation_contract(
        payload.get("implementation_artifact_refs"),
        payload.get("implementation_receipts"),
    )
    physical_state = validate_output_set(
        output_root,
        permit_review_transition=source_and_review_only,
    )
    if not source_and_review_only and (
        payload.get("physical_paths") != physical_state["physical_paths"]
        or payload.get("physical_directories") != physical_state["physical_directories"]
    ):
        raise ValueError("Report Builder physical output binding is stale")
    validate_source_index(output_root)
    stored_prepared = payload.get("prepared_validation")
    current_prepared = validate_prepared_report(
        output_root,
        validate_delivery_state=not source_and_review_only,
    )
    if source_and_review_only and isinstance(stored_prepared, Mapping):
        stored_prepared = {
            key: value
            for key, value in stored_prepared.items()
            if key != "review_successor"
        }
    if stored_prepared != current_prepared:
        raise ValueError("Report Builder prepared-output binding is stale")
    receipts = payload.get("protected_files")
    if not isinstance(receipts, list):
        raise ValueError("Report Builder review-integrity receipts are malformed")
    receipt_paths = [
        receipt.get("path") for receipt in receipts if isinstance(receipt, Mapping)
    ]
    if len(receipt_paths) != len(set(receipt_paths)):
        raise ValueError("Report Builder review-integrity paths are not unique")
    required_paths = {SOURCE_INDEX_FILE_NAME, "review_payload.json"}
    found_paths = {
        str(receipt.get("path")) for receipt in receipts if isinstance(receipt, Mapping)
    }
    if not required_paths <= found_paths:
        raise ValueError("Report Builder review-integrity receipts are incomplete")
    for receipt in receipts:
        if not isinstance(receipt, Mapping):
            raise ValueError("Report Builder review-integrity receipt is malformed")
        path_value = str(receipt.get("path") or "")
        if source_and_review_only and path_value not in required_paths:
            continue
        _validate_relative_receipt(output_root, receipt)
    payload_digests = payload.get("payload_digests")
    if not isinstance(payload_digests, Mapping):
        raise ValueError("Report Builder payload digests are malformed")
    expected_digest_names = {name.removesuffix(".json") for name in _REVIEW_FILES}
    expected_digest_names.update(
        name.removesuffix(".json")
        for name in _OPTIONAL_REVIEW_FILES
        if (output_root / name).is_file()
    )
    if source_and_review_only:
        base_digest_names = {name.removesuffix(".json") for name in _REVIEW_FILES}
        allowed_digest_names = base_digest_names | {
            name.removesuffix(".json") for name in _OPTIONAL_REVIEW_FILES
        }
        if (
            not base_digest_names <= set(payload_digests)
            or not set(payload_digests) <= allowed_digest_names
        ):
            raise ValueError("Report Builder payload digest fields are not exact")
    elif set(payload_digests) != expected_digest_names:
        raise ValueError("Report Builder payload digest fields are not exact")
    digest_files = ("review_payload.json",) if source_and_review_only else _REVIEW_FILES
    for name in digest_files:
        key = name.removesuffix(".json")
        persisted = _read_object(output_root / name)
        if payload_digests.get(key) != canonical_json_sha256(persisted):
            raise ValueError(f"Persisted {key} digest is stale")
    current_review_digest = payload_digests.get("review_payload")
    for optional_name in _OPTIONAL_REVIEW_FILES:
        optional_path = output_root / optional_name
        if not optional_path.is_file():
            continue
        optional_state = _read_object(optional_path)
        optional_key = optional_name.removesuffix(".json")
        if not source_and_review_only and payload_digests.get(
            optional_key
        ) != canonical_json_sha256(optional_state):
            raise ValueError(f"Persisted {optional_key} digest is stale")
        if optional_state.get("run_id") != payload.get("run_id"):
            raise ValueError(f"Persisted {optional_name} run_id is stale")
        if optional_state.get("review_payload_sha256") != current_review_digest:
            raise ValueError(
                f"Persisted {optional_name} review payload binding is stale"
            )
    if not source_and_review_only:
        final_artifacts = _read_object(output_root / "final_artifacts.json")
        _validate_final_artifact_gallery(output_root, final_artifacts)
    supplied = {
        "review_payload": supplied_review_payload,
        "run_intake": supplied_run_intake,
        "final_artifacts": supplied_final_artifacts,
    }
    for key, value in supplied.items():
        if value is None:
            continue
        expected = payload_digests.get(key)
        if expected != canonical_json_sha256(value):
            raise ValueError(f"Supplied {key} does not match persisted review state")
    return payload
