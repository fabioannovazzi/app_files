from __future__ import annotations

import argparse
import hashlib
import json
import logging
import re
import stat
import sys
from pathlib import Path, PurePosixPath
from typing import Any, Iterator, Sequence

from new_client_core import ValidationError, sha256_file, validate_contract

__all__ = [
    "DeliveryValidationError",
    "seal_delivery",
    "validate_delivery",
]

LOGGER = logging.getLogger(__name__)
DELIVERY_MANIFEST_NAME = "delivery_manifest.json"
SOURCE_EVIDENCE_DIRECTORY = "source-evidence"
DEFAULT_FORBIDDEN_TERMS = ("codex", "claude", "openai", "anthropic")
RUN_ID_PATTERN = re.compile(r"\bnew-client-[0-9]{14,}-[0-9a-f]{12}\b")
UNICODE_ESCAPE_PATTERN = re.compile(r"\\u([0-9a-fA-F]{4})")
SHA256_PATTERN = re.compile(r"[0-9a-f]{64}")
MANIFEST_KEYS = frozenset(
    {
        "schema_version",
        "status",
        "run_id",
        "base_contract_status",
        "base_contract_artifact_count",
        "artifact_count",
        "directory_count",
        "artifacts",
        "package_hash",
    }
)
RECEIPT_KEYS = frozenset({"path", "size_bytes", "sha256"})


class DeliveryValidationError(ValueError):
    """Raised when a delivered New Client dossier breaks its mechanical contract."""


def _strict_json_loads(content: str, *, label: str) -> Any:
    def reject_duplicate_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        payload: dict[str, Any] = {}
        for key, value in pairs:
            if key in payload:
                raise DeliveryValidationError(
                    f"{label} contains duplicate JSON key {key!r}."
                )
            payload[key] = value
        return payload

    try:
        return json.loads(content, object_pairs_hook=reject_duplicate_keys)
    except json.JSONDecodeError as exc:
        raise DeliveryValidationError(f"{label} is not valid JSON: {exc}") from exc


def _load_json_object(path: Path) -> dict[str, Any]:
    try:
        content = path.read_text(encoding="utf-8")
    except UnicodeDecodeError as exc:
        raise DeliveryValidationError(f"{path.name} is not valid UTF-8.") from exc
    payload = _strict_json_loads(content, label=path.name)
    if not isinstance(payload, dict):
        raise DeliveryValidationError(f"{path.name} must contain a JSON object.")
    return payload


def _expected_run_id(output_dir: Path) -> str:
    payload = _load_json_object(output_dir / "final_artifacts.json")
    run_id = payload.get("run_id")
    if not isinstance(run_id, str) or RUN_ID_PATTERN.fullmatch(run_id) is None:
        raise DeliveryValidationError(
            "final_artifacts.json does not contain a contract-shaped run_id."
        )
    return run_id


def _is_source_evidence(relative_path: Path) -> bool:
    return bool(relative_path.parts) and (
        relative_path.parts[0] == SOURCE_EVIDENCE_DIRECTORY
    )


def _normalized_scan_text(value: str) -> str:
    return UNICODE_ESCAPE_PATTERN.sub(
        lambda match: chr(int(match.group(1), 16)),
        value,
    )


def _is_source_evidence_reference(
    value: str,
    *,
    json_path: tuple[str, ...],
    registered_paths: frozenset[str],
) -> bool:
    path_fields = {
        "input_paths",
        "inputs",
        "local_files_read",
        "local_path",
        "path",
        "resolved_path",
    }
    if not any(part in path_fields for part in json_path):
        return False
    normalized = value.replace("\\", "/")
    marker = f"/{SOURCE_EVIDENCE_DIRECTORY}/"
    if normalized.startswith(f"{SOURCE_EVIDENCE_DIRECTORY}/"):
        relative_path = normalized
    elif marker in normalized and normalized.startswith("/"):
        relative_path = normalized[normalized.index(marker) + 1 :]
    else:
        return False
    return relative_path in registered_paths


def _validate_scannable_text(
    value: str,
    *,
    context: str,
    expected_run_id: str,
    forbidden_terms: Sequence[str],
) -> None:
    normalized = _normalized_scan_text(value)
    lowered = normalized.casefold()
    for term in forbidden_terms:
        if term.casefold() in lowered:
            raise DeliveryValidationError(
                f"Assistant-authored content contains forbidden host/provider "
                f"name {term!r}: {context}"
            )
    stale_run_ids = sorted(
        match
        for match in set(RUN_ID_PATTERN.findall(normalized))
        if match != expected_run_id
    )
    if stale_run_ids:
        raise DeliveryValidationError(
            f"{context} contains run IDs that do not match "
            f"final_artifacts.json: {', '.join(stale_run_ids)}"
        )


def _iter_json_strings(
    value: Any,
    *,
    path: tuple[str, ...] = (),
) -> Iterator[tuple[tuple[str, ...], str]]:
    if isinstance(value, dict):
        for key, nested in value.items():
            key_text = str(key)
            yield (*path, "<key>"), key_text
            yield from _iter_json_strings(nested, path=(*path, key_text))
    elif isinstance(value, list):
        for index, nested in enumerate(value):
            yield from _iter_json_strings(nested, path=(*path, str(index)))
    elif isinstance(value, str):
        yield path, value


def _validate_json_text(
    content: str,
    *,
    relative_path: Path,
    expected_run_id: str,
    forbidden_terms: Sequence[str],
    registered_source_paths: frozenset[str],
) -> None:
    payload = _strict_json_loads(
        content,
        label=f"Assistant-authored JSON {relative_path.as_posix()}",
    )
    for json_path, value in _iter_json_strings(payload):
        if _is_source_evidence_reference(
            value,
            json_path=json_path,
            registered_paths=registered_source_paths,
        ):
            continue
        _validate_scannable_text(
            value,
            context=f"{relative_path.as_posix()}:{'.'.join(json_path)}",
            expected_run_id=expected_run_id,
            forbidden_terms=forbidden_terms,
        )


def _validate_assistant_text(
    path: Path,
    relative_path: Path,
    *,
    expected_run_id: str,
    forbidden_terms: Sequence[str],
    registered_source_paths: frozenset[str],
) -> None:
    if _is_source_evidence(relative_path):
        return

    _validate_scannable_text(
        relative_path.as_posix(),
        context=f"assistant-authored path {relative_path.as_posix()}",
        expected_run_id=expected_run_id,
        forbidden_terms=forbidden_terms,
    )

    if not path.is_file():
        return
    try:
        content = path.read_text(encoding="utf-8")
    except UnicodeDecodeError as exc:
        raise DeliveryValidationError(
            f"Assistant-authored text file is not UTF-8: {relative_path.as_posix()}"
        ) from exc
    suffix = path.suffix.casefold()
    if suffix == ".json":
        _validate_json_text(
            content,
            relative_path=relative_path,
            expected_run_id=expected_run_id,
            forbidden_terms=forbidden_terms,
            registered_source_paths=registered_source_paths,
        )
        return
    if suffix == ".jsonl":
        for line_number, line in enumerate(content.splitlines(), start=1):
            if not line.strip():
                continue
            _validate_json_text(
                line,
                relative_path=Path(f"{relative_path.as_posix()} line {line_number}"),
                expected_run_id=expected_run_id,
                forbidden_terms=forbidden_terms,
                registered_source_paths=registered_source_paths,
            )
        return
    _validate_scannable_text(
        content,
        context=relative_path.as_posix(),
        expected_run_id=expected_run_id,
        forbidden_terms=forbidden_terms,
    )


def _registered_source_evidence(
    output_dir: Path,
) -> dict[str, str]:
    input_payload = _load_json_object(output_dir / "new_client_input.json")
    run_intake = _load_json_object(output_dir / "run_intake.json")
    input_binding = run_intake.get("input")
    if not isinstance(input_binding, dict):
        raise DeliveryValidationError(
            "run_intake.json input binding must authenticate new_client_input.json."
        )
    bound_input_sha256 = input_binding.get("sha256")
    if (
        not isinstance(bound_input_sha256, str)
        or SHA256_PATTERN.fullmatch(bound_input_sha256.casefold()) is None
        or bound_input_sha256.casefold()
        != sha256_file(output_dir / "new_client_input.json")
    ):
        raise DeliveryValidationError(
            "new_client_input.json does not match the sealed run_intake.json "
            "input hash."
        )
    raw_register = input_payload.get("evidence_register")
    if not isinstance(raw_register, list):
        raise DeliveryValidationError(
            "new_client_input.json evidence_register must authenticate copied "
            "source evidence."
        )
    registered: dict[str, str] = {}
    for index, raw_record in enumerate(raw_register):
        if not isinstance(raw_record, dict):
            raise DeliveryValidationError(
                f"new_client_input.json evidence_register[{index}] must be an object."
            )
        local_path = raw_record.get("local_path")
        expected_sha256 = raw_record.get("sha256")
        status = raw_record.get("status")
        if not isinstance(local_path, str):
            continue
        pure_path = PurePosixPath(local_path)
        if (
            pure_path.is_absolute()
            or pure_path.as_posix() != local_path
            or ".." in pure_path.parts
            or not pure_path.parts
            or pure_path.parts[0] != SOURCE_EVIDENCE_DIRECTORY
        ):
            continue
        if (
            not isinstance(expected_sha256, str)
            or SHA256_PATTERN.fullmatch(expected_sha256.casefold()) is None
        ):
            raise DeliveryValidationError(
                f"Evidence receipt has an invalid SHA-256: {local_path}"
            )
        if local_path in registered:
            raise DeliveryValidationError(
                f"Duplicate source-evidence receipt: {local_path}"
            )
        if status not in {"available", "verified"}:
            raise DeliveryValidationError(
                f"Copied source evidence is not available or verified: {local_path}"
            )
        registered[local_path] = expected_sha256.casefold()
    return registered


def _validate_source_evidence(
    output_dir: Path,
    files: Sequence[Path],
    *,
    registered: dict[str, str],
) -> None:
    actual_paths = {
        path.relative_to(output_dir).as_posix(): path
        for path in files
        if _is_source_evidence(path.relative_to(output_dir))
    }

    if set(actual_paths) != set(registered):
        missing = sorted(set(registered) - set(actual_paths))
        unexpected = sorted(set(actual_paths) - set(registered))
        details: list[str] = []
        if missing:
            details.append(f"missing copied evidence: {', '.join(missing)}")
        if unexpected:
            details.append(f"unregistered copied evidence: {', '.join(unexpected)}")
        raise DeliveryValidationError(
            "Copied source evidence does not match the evidence register "
            f"({'; '.join(details)})."
        )
    for relative_path, path in actual_paths.items():
        expected_sha256 = registered.get(relative_path)
        if expected_sha256 is None:  # pragma: no cover - set equality proves this
            raise DeliveryValidationError("Internal source receipt mismatch.")
        if sha256_file(path) != expected_sha256:
            raise DeliveryValidationError(
                f"Copied source evidence hash mismatch: {relative_path}"
            )


def _reject_symlinked_path_components(output_dir: Path) -> None:
    current = Path(output_dir.anchor)
    for part in output_dir.parts[1:]:
        current /= part
        mode = current.lstat().st_mode
        if stat.S_ISLNK(mode):
            raise DeliveryValidationError(
                f"Delivery path contains a symbolic-link component: {current}"
            )


def _validate_tree(
    output_dir: Path,
    *,
    expected_run_id: str | None,
    forbidden_terms: Sequence[str],
    registered_source_paths: frozenset[str] = frozenset(),
    ignore_existing_manifest: bool = False,
    scan_content: bool = True,
) -> tuple[list[Path], int]:
    # Modes, file types, literal names, and run-ID equality are mechanical facts.
    # Fixed validation is therefore more auditable and reproducible than model review.
    root_mode = output_dir.lstat().st_mode
    if not stat.S_ISDIR(root_mode) or stat.S_ISLNK(root_mode):
        raise DeliveryValidationError("Delivery root must be a real directory.")
    if stat.S_IMODE(root_mode) != 0o700:
        raise DeliveryValidationError(
            f"Delivery root must be mode 0700, found {oct(stat.S_IMODE(root_mode))}."
        )

    files: list[Path] = []
    directories: list[Path] = []
    directory_count = 1
    for path in sorted(output_dir.rglob("*")):
        relative_path = path.relative_to(output_dir)
        mode = path.lstat().st_mode
        if stat.S_ISLNK(mode):
            raise DeliveryValidationError(
                f"Delivery contains a symbolic link: {relative_path.as_posix()}"
            )
        if stat.S_ISDIR(mode):
            directory_count += 1
            directories.append(path)
            if stat.S_IMODE(mode) != 0o700:
                raise DeliveryValidationError(
                    f"Directory must be mode 0700: {relative_path.as_posix()}"
                )
            if scan_content:
                if expected_run_id is None:
                    raise DeliveryValidationError(
                        "Internal error: expected_run_id is required for content scan."
                    )
                _validate_assistant_text(
                    path,
                    relative_path,
                    expected_run_id=expected_run_id,
                    forbidden_terms=forbidden_terms,
                    registered_source_paths=registered_source_paths,
                )
            continue
        if not stat.S_ISREG(mode):
            raise DeliveryValidationError(
                f"Delivery contains a special file: {relative_path.as_posix()}"
            )
        if (
            ignore_existing_manifest
            and relative_path.as_posix() == DELIVERY_MANIFEST_NAME
        ):
            continue
        if path.stat().st_nlink != 1:
            raise DeliveryValidationError(
                f"Delivery contains a hard-linked file: {relative_path.as_posix()}"
            )
        if stat.S_IMODE(mode) != 0o600:
            raise DeliveryValidationError(
                f"File must be mode 0600: {relative_path.as_posix()}"
            )
        is_root_manifest = relative_path.as_posix() == DELIVERY_MANIFEST_NAME
        if scan_content and not is_root_manifest:
            if expected_run_id is None:
                raise DeliveryValidationError(
                    "Internal error: expected_run_id is required for content scan."
                )
            _validate_assistant_text(
                path,
                relative_path,
                expected_run_id=expected_run_id,
                forbidden_terms=forbidden_terms,
                registered_source_paths=registered_source_paths,
            )
        files.append(path)
    for directory in directories:
        try:
            next(directory.iterdir())
        except StopIteration as exc:
            raise DeliveryValidationError(
                "Delivery contains an empty directory that cannot be bound by "
                f"file receipts: {directory.relative_to(output_dir).as_posix()}"
            ) from exc
    return files, directory_count


def _receipt(path: Path, output_dir: Path) -> dict[str, Any]:
    return {
        "path": path.relative_to(output_dir).as_posix(),
        "size_bytes": path.stat().st_size,
        "sha256": sha256_file(path),
    }


def _package_hash(receipts: Sequence[dict[str, Any]]) -> str:
    payload = {str(receipt["path"]): str(receipt["sha256"]) for receipt in receipts}
    encoded = json.dumps(
        payload,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def seal_delivery(
    output_dir: Path,
    *,
    forbidden_terms: Sequence[str] = DEFAULT_FORBIDDEN_TERMS,
) -> dict[str, Any]:
    """Seal every delivered file after checking privacy, naming, and run identity."""

    resolved = output_dir.expanduser().absolute()
    _reject_symlinked_path_components(resolved)
    _validate_tree(
        resolved,
        expected_run_id=None,
        forbidden_terms=forbidden_terms,
        ignore_existing_manifest=True,
        scan_content=False,
    )
    expected_run_id = _expected_run_id(resolved)
    registered_source_evidence = _registered_source_evidence(resolved)
    manifest_path = resolved / DELIVERY_MANIFEST_NAME

    files, directory_count = _validate_tree(
        resolved,
        expected_run_id=expected_run_id,
        forbidden_terms=forbidden_terms,
        registered_source_paths=frozenset(registered_source_evidence),
        ignore_existing_manifest=True,
    )
    _validate_source_evidence(
        resolved,
        files,
        registered=registered_source_evidence,
    )
    base_validation = validate_contract(resolved)
    receipts = [
        _receipt(path, resolved)
        for path in files
        if path.relative_to(resolved).as_posix() != DELIVERY_MANIFEST_NAME
    ]
    manifest = {
        "schema_version": "1.0",
        "status": "delivery_sealed_for_professional_review",
        "run_id": expected_run_id,
        "base_contract_status": base_validation["status"],
        "base_contract_artifact_count": base_validation["artifact_count"],
        "artifact_count": len(receipts),
        "directory_count": directory_count,
        "artifacts": receipts,
        "package_hash": _package_hash(receipts),
    }
    temporary_manifest_path = resolved / f".{DELIVERY_MANIFEST_NAME}.tmp"
    temporary_manifest_path.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    temporary_manifest_path.chmod(0o600)
    temporary_manifest_path.replace(manifest_path)
    return validate_delivery(resolved, forbidden_terms=forbidden_terms)


def validate_delivery(
    output_dir: Path,
    *,
    forbidden_terms: Sequence[str] = DEFAULT_FORBIDDEN_TERMS,
) -> dict[str, Any]:
    """Validate the base contract and the complete delivered dossier seal."""

    resolved = output_dir.expanduser().absolute()
    _reject_symlinked_path_components(resolved)
    _validate_tree(
        resolved,
        expected_run_id=None,
        forbidden_terms=forbidden_terms,
        scan_content=False,
    )
    expected_run_id = _expected_run_id(resolved)
    registered_source_evidence = _registered_source_evidence(resolved)
    files, directory_count = _validate_tree(
        resolved,
        expected_run_id=expected_run_id,
        forbidden_terms=forbidden_terms,
        registered_source_paths=frozenset(registered_source_evidence),
    )
    _validate_source_evidence(
        resolved,
        files,
        registered=registered_source_evidence,
    )
    base_validation = validate_contract(resolved)

    manifest_path = resolved / DELIVERY_MANIFEST_NAME
    manifest = _load_json_object(manifest_path)
    if set(manifest) != MANIFEST_KEYS:
        raise DeliveryValidationError(
            "delivery_manifest.json must contain exactly the generated schema fields."
        )
    if manifest.get("schema_version") != "1.0":
        raise DeliveryValidationError(
            "delivery_manifest.json schema_version must be 1.0."
        )
    if manifest.get("status") != "delivery_sealed_for_professional_review":
        raise DeliveryValidationError("delivery_manifest.json status is invalid.")
    if manifest.get("run_id") != expected_run_id:
        raise DeliveryValidationError(
            "delivery_manifest.json run_id does not match final_artifacts.json."
        )
    if manifest.get("base_contract_status") != base_validation["status"]:
        raise DeliveryValidationError(
            "delivery_manifest.json base_contract_status is stale or invalid."
        )
    if (
        manifest.get("base_contract_artifact_count")
        != base_validation["artifact_count"]
    ):
        raise DeliveryValidationError(
            "delivery_manifest.json base_contract_artifact_count is stale or invalid."
        )
    raw_receipts = manifest.get("artifacts")
    if not isinstance(raw_receipts, list):
        raise DeliveryValidationError(
            "delivery_manifest.json artifacts must be a list."
        )
    receipts: list[dict[str, Any]] = []
    for index, raw_receipt in enumerate(raw_receipts):
        if not isinstance(raw_receipt, dict):
            raise DeliveryValidationError(
                f"delivery_manifest.json artifacts[{index}] must be an object."
            )
        if set(raw_receipt) != RECEIPT_KEYS:
            raise DeliveryValidationError(
                f"delivery_manifest.json artifacts[{index}] has invalid fields."
            )
        path_value = raw_receipt.get("path")
        if not isinstance(path_value, str) or not path_value:
            raise DeliveryValidationError(
                f"delivery_manifest.json artifacts[{index}].path is invalid."
            )
        pure_path = PurePosixPath(path_value)
        if (
            pure_path.is_absolute()
            or pure_path.as_posix() != path_value
            or ".." in pure_path.parts
            or path_value == DELIVERY_MANIFEST_NAME
        ):
            raise DeliveryValidationError(
                f"delivery_manifest.json artifacts[{index}].path is unsafe."
            )
        size_bytes = raw_receipt.get("size_bytes")
        if (
            isinstance(size_bytes, bool)
            or not isinstance(size_bytes, int)
            or size_bytes < 0
        ):
            raise DeliveryValidationError(
                f"delivery_manifest.json artifacts[{index}].size_bytes is invalid."
            )
        sha256 = raw_receipt.get("sha256")
        if not isinstance(sha256, str) or SHA256_PATTERN.fullmatch(sha256) is None:
            raise DeliveryValidationError(
                f"delivery_manifest.json artifacts[{index}].sha256 is invalid."
            )
        receipts.append(raw_receipt)

    sealed_paths = [str(receipt["path"]) for receipt in receipts]
    if len(sealed_paths) != len(set(sealed_paths)):
        raise DeliveryValidationError(
            "delivery_manifest.json contains duplicate artifact paths."
        )
    if sealed_paths != sorted(sealed_paths):
        raise DeliveryValidationError(
            "delivery_manifest.json artifact paths are not in canonical order."
        )
    actual_paths = sorted(
        path.relative_to(resolved).as_posix()
        for path in files
        if path.relative_to(resolved).as_posix() != DELIVERY_MANIFEST_NAME
    )
    if sorted(sealed_paths) != actual_paths:
        raise DeliveryValidationError(
            "delivery_manifest.json does not cover the exact delivered file set."
        )
    for receipt in receipts:
        relative_path = PurePosixPath(str(receipt["path"]))
        path = resolved.joinpath(*relative_path.parts)
        if receipt.get("size_bytes") != path.stat().st_size:
            raise DeliveryValidationError(
                f"Delivery size receipt mismatch: {relative_path.as_posix()}"
            )
        if receipt.get("sha256") != sha256_file(path):
            raise DeliveryValidationError(
                f"Delivery hash receipt mismatch: {relative_path.as_posix()}"
            )
    expected_package_hash = _package_hash(receipts)
    package_hash = manifest.get("package_hash")
    if (
        not isinstance(package_hash, str)
        or SHA256_PATTERN.fullmatch(package_hash) is None
        or package_hash != expected_package_hash
    ):
        raise DeliveryValidationError(
            "delivery_manifest.json package_hash does not match its receipts."
        )
    artifact_count = manifest.get("artifact_count")
    if (
        isinstance(artifact_count, bool)
        or not isinstance(artifact_count, int)
        or artifact_count != len(receipts)
    ):
        raise DeliveryValidationError(
            "delivery_manifest.json artifact_count does not match its receipts."
        )
    manifest_directory_count = manifest.get("directory_count")
    if (
        isinstance(manifest_directory_count, bool)
        or not isinstance(manifest_directory_count, int)
        or manifest_directory_count != directory_count
    ):
        raise DeliveryValidationError(
            "delivery_manifest.json directory_count does not match the delivery."
        )
    return {
        "status": "delivery_validated_for_professional_review",
        "run_id": expected_run_id,
        "artifact_count": len(receipts),
        "directory_count": directory_count,
        "package_hash": expected_package_hash,
        "base_contract_status": base_validation["status"],
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Seal or validate a complete New Client delivery."
    )
    parser.add_argument("command", choices=("seal", "validate"))
    parser.add_argument("--output-dir", required=True, type=Path)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        if args.command == "seal":
            report = seal_delivery(args.output_dir)
        else:
            report = validate_delivery(args.output_dir)
    except (DeliveryValidationError, ValidationError, OSError) as exc:
        LOGGER.error("%s", exc)
        return 1
    sys.stdout.write(
        json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
