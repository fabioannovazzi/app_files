"""Deterministic contracts for local product-attribute HTML reports."""

from __future__ import annotations

import csv
import hashlib
import html
import json
import logging
import math
import os
import re
import shutil
import sys
import tempfile
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime, timezone
from functools import lru_cache
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

__all__ = [
    "ContractError",
    "create_mapping_review_template",
    "create_mapping_tasks",
    "finalize_report",
    "prepare_run",
    "render_report",
    "select_codex_effective_correction_tasks",
    "validate_mapping_decisions",
    "validate_mapping_payloads",
    "validate_mapping_review",
    "validate_mapping_review_payloads",
    "verify_mapping_tasks_against_source",
]

LOGGER = logging.getLogger(__name__)

RUN_SCHEMA = "attribute_reporting.run_intake.v1"
CATALOG_SCHEMA = "attribute_reporting.evidence_catalog.v1"
MODEL_SCHEMA = "attribute_reporting.report_model.v1"
RENDER_SCHEMA = "attribute_reporting.render_manifest.v1"
REVIEW_SCHEMA = "attribute_reporting.semantic_review.v1"
VERDICT_SCHEMA = "attribute_reporting.correctness_verdict.v1"
MAPPING_TASK_SCHEMA = "attribute_reporting.mapping_tasks.v1"
MAPPING_DECISION_SCHEMA = "attribute_reporting.mapping_decisions.v1"
VALIDATED_MAPPING_SCHEMA = "attribute_reporting.validated_mapping_decisions.v1"
MAPPING_REVIEW_SCHEMA = "attribute_reporting.mapping_review.v1"
MAPPING_REVIEW_VALIDATION_SCHEMA = "attribute_reporting.mapping_review_validation.v1"
CORRECTION_TASK_SELECTION_SCHEMA = "attribute_reporting.correction_task_selection.v1"
LOCAL_IMAGE_MANIFEST_SCHEMA = "attribute_reporting.local_image_manifest.v1"
LOCAL_DOWNLOAD_RECEIPT_SCHEMA = "attribute_reporting.local_download_receipt.v1"
LOCAL_EXTRACTION_RECEIPT_SCHEMA = "attribute_reporting.local_extraction_receipt.v1"
TRANSPORT_LINEAGE_SCHEMA = "attribute_reporting.transport_lineage.v1"
LOCAL_TRANSPORT_RECEIPT_FILES = (
    "local_download_receipt.json",
    "local_extraction_receipt.json",
)
NO_WORK_WORKSET_FILE = "mapping_no_work_workset.json"
NO_WORK_MAPPING_BASIS_SCHEMA = "attribute_reporting.mapping_review_basis.v1"
MAX_LOCAL_TRANSPORT_RECEIPT_BYTES = 2 * 1024 * 1024
MAX_NO_WORK_WORKSET_BYTES = 2 * 1024 * 1024
MAPPING_PROVENANCE_FILES = (
    "mapping_tasks.json",
    "mapping_decisions.json",
    "validated_mappings.json",
    "mapping_review.json",
)
SERVER_MAPPING_PROVENANCE_FILES = (
    "mapping_submission_receipt.json",
    "mapping_review_validation.json",
    "server_sanitization_receipt.json",
)
SERVER_BRIDGE_SCHEMA_PREFIX = "attribute_reporting.server_bridge"

VERDICT_LABELS = {
    "correct": "Correct",
    "correct_with_caveats": "Correct with caveats",
    "incorrect": "Incorrect",
    "unable_to_determine": "Unable to determine",
}
VERDICT_PLACEHOLDER_HTML = (
    "<!-- ATTRIBUTE_REPORTING_VERDICT -->"
    '<aside class="verdict unable_to_determine provisional" '
    'data-correctness-verdict="pending">'
    '<span class="mark">?</span><div><strong>Correctness review pending</strong>'
    "<span>The final evidence-backed verdict will replace this banner after "
    "independent semantic review and browser QA.</span></div></aside>"
)
REQUIRED_SECTION_IDS = (
    "executive_summary",
    "winning_now",
    "brand_context",
    "emerging_signal",
    "winner_emerging_bridge",
    "product_evidence",
    "method_and_caveats",
)
REQUIRED_REVIEW_DIMENSIONS = (
    "claim_coverage",
    "story_coherence",
    "importance_calibration",
    "caveat_handling",
    "brand_and_example_interpretation",
    "html_readability",
)
ALLOWED_TABLE_KEYS = {
    "attribute_bundle_comparison_table",
    "attribute_bridge_table",
    "rank_weighted_visibility_table",
    "product_signal_evidence_table",
}
ALLOWED_EVIDENCE_FILES = {
    "summary.json",
    "pack_manifest.json",
    "package_integrity.json",
    "mapped_attribute_comparison.csv",
    "top_seller_mapped_attribute_comparison.csv",
    "innovation_pairs.csv",
    "innovation_triples.csv",
    "top_seller_pairs.csv",
    "top_seller_triples.csv",
    "top_seller_brand_comparison.csv",
    "price_band_comparison.csv",
    "price_comparison.json",
    "resolved_core_comparison.csv",
    "filter_comparison.csv",
    "recent_products.csv",
    "top_seller_products.csv",
    "top_seller_review_validation.csv",
    "bundle_review_validation.csv",
    "sale_pressure_attribute_comparison.csv",
    "sale_pressure_pairs.csv",
    "sale_pressure_triples.csv",
    "sale_pressure_overlap.csv",
    "sort_rank_delta_attributes.csv",
}
SUPPORTED_FORMATS = {
    "text",
    "integer",
    "decimal_1",
    "decimal_2",
    "percent_1",
    "percentage_point_1",
    "ratio_2",
    "currency_0",
}
TOKEN_RE = re.compile(r"\{\{([a-z][a-z0-9_-]{0,63})\}\}")
NUMERIC_LITERAL_RE = re.compile(r"(?<![A-Za-z])\d+(?:[.,]\d+)?")
SAFE_ID_RE = re.compile(r"^[a-zA-Z0-9][a-zA-Z0-9_.:-]{0,127}$")
MAPPING_PLACEHOLDERS = {
    "",
    "n/a",
    "na",
    "none",
    "unknown",
    "n/a (not stated)",
    "not stated",
    "not in taxonomy",
}


class ContractError(ValueError):
    """Raised when a report or mapping artifact violates its contract."""


@dataclass(frozen=True, slots=True)
class ResolvedEvidence:
    """One evidence binding resolved from a package source."""

    ref_id: str
    source: str
    raw_value: Any
    formatted_value: str
    source_sha256: str
    selector: dict[str, Any]
    source_row_sha256: str | None = None


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _load_json(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise ContractError(f"Required JSON file is missing: {path}") from exc
    except json.JSONDecodeError as exc:
        raise ContractError(f"Invalid JSON in {path}: {exc}") from exc
    if not isinstance(payload, dict):
        raise ContractError(f"Expected a JSON object in {path}")
    return payload


def _write_json(path: Path, payload: Mapping[str, Any]) -> None:
    destination = path.expanduser().resolve()
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = tempfile.NamedTemporaryFile(
        mode="w",
        encoding="utf-8",
        dir=destination.parent,
        prefix=f".{destination.name}.",
        suffix=".tmp",
        delete=False,
    )
    temporary_path = Path(temporary.name)
    try:
        with temporary:
            json.dump(payload, temporary, ensure_ascii=False, indent=2)
            temporary.write("\n")
        temporary_path.chmod(0o600)
        temporary_path.replace(destination)
    finally:
        temporary_path.unlink(missing_ok=True)


def _sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _canonical_json_sha256(payload: Mapping[str, Any]) -> str:
    encoded = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return _sha256_bytes(encoded)


def _safe_relative_path(value: str, *, label: str) -> Path:
    path = Path(value)
    if path.is_absolute() or ".." in path.parts or not path.parts:
        raise ContractError(f"{label} must be a safe relative path: {value!r}")
    return path


def _contained_package_path(
    package_dir: Path,
    relative: Path | str,
    *,
    label: str,
) -> Path:
    """Resolve one package path and reject traversal or symlink escapes."""

    root = package_dir.expanduser().resolve()
    safe_relative = _safe_relative_path(str(relative), label=label)
    candidate = (root / safe_relative).resolve()
    if not candidate.is_relative_to(root):
        raise ContractError(f"{label} escapes the evidence package: {relative!s}")
    return candidate


def _assert_safe_output_dir(output_dir: Path) -> Path:
    resolved = output_dir.expanduser().resolve()
    for parent in (resolved, *resolved.parents):
        if (parent / ".git").exists():
            raise ContractError(
                "Run outputs cannot be written inside a Git workspace; choose a "
                "private local output folder outside the repository."
            )
    return resolved


def _read_csv(path: Path) -> tuple[list[str], list[dict[str, str]]]:
    try:
        with path.open("r", encoding="utf-8-sig", newline="") as handle:
            reader = csv.DictReader(handle)
            columns = list(reader.fieldnames or [])
            rows = [dict(row) for row in reader]
    except FileNotFoundError as exc:
        raise ContractError(f"Required CSV file is missing: {path}") from exc
    except csv.Error as exc:
        raise ContractError(f"Invalid CSV in {path}: {exc}") from exc
    if not columns:
        raise ContractError(f"CSV file has no header: {path}")
    return columns, rows


def _source_row_sha256(row: Mapping[str, Any]) -> str:
    return _canonical_json_sha256(dict(row))


def _normalise_mapping_token(value: Any) -> str:
    return re.sub(r"[^a-z0-9]+", "_", str(value or "").casefold()).strip("_")


def _taxonomy_leaf_values(nodes: Any) -> list[dict[str, str]]:
    if not isinstance(nodes, list):
        return []
    values: list[dict[str, str]] = []
    for node in nodes:
        if not isinstance(node, dict):
            continue
        children = node.get("children")
        if isinstance(children, list) and children:
            values.extend(_taxonomy_leaf_values(children))
            continue
        value_id = str(node.get("id") or "").strip()
        label = str(node.get("label") or "").strip()
        if not value_id or not label:
            continue
        if str(node.get("status") or "active").strip().casefold() != "active":
            continue
        if _normalise_mapping_token(value_id) in {"unknown", "other"}:
            continue
        if label.casefold() in {"n/a (not stated)", "not in taxonomy"}:
            continue
        values.append({"id": value_id, "label": label})
    return values


def _mapping_value_parts(value: Any) -> list[str]:
    text = str(value or "").strip()
    if text.casefold() in MAPPING_PLACEHOLDERS:
        return []
    return [part.strip() for part in re.split(r"\s*[|;]\s*", text) if part.strip()]


def _row_attribute_evidence(
    row: Mapping[str, str],
    *,
    attribute_id: str,
    attribute_label: str,
    selection: str,
    allowed_values: Sequence[Mapping[str, str]],
) -> tuple[bool, dict[str, str], str]:
    columns_by_token: dict[str, list[str]] = {}
    for column in row:
        columns_by_token.setdefault(_normalise_mapping_token(column), []).append(column)
    candidate_tokens = [
        _normalise_mapping_token(attribute_id),
        _normalise_mapping_token(attribute_label),
    ]
    candidate_columns: list[str] = []
    for token in candidate_tokens:
        for candidate in (token, f"{token}_mapped"):
            for column in columns_by_token.get(candidate, []):
                if column not in candidate_columns:
                    candidate_columns.append(column)
    evidence = {
        column: str(row.get(column) or "").strip()
        for column in candidate_columns
        if str(row.get(column) or "").strip()
    }
    allowed_tokens = {
        token
        for item in allowed_values
        for token in (
            _normalise_mapping_token(item.get("id")),
            _normalise_mapping_token(item.get("label")),
        )
        if token
    }
    for evidence_column, value in evidence.items():
        parts = _mapping_value_parts(value)
        if parts and all(
            _normalise_mapping_token(part) in allowed_tokens for part in parts
        ):
            evidence_token = _normalise_mapping_token(evidence_column)
            if evidence_token.endswith("_mapped"):
                evidence_token = evidence_token[: -len("_mapped")]
            source_tokens = [
                f"{evidence_token}_effective_source",
                f"{_normalise_mapping_token(attribute_id)}_effective_source",
                f"{_normalise_mapping_token(attribute_label)}_effective_source",
            ]
            source = next(
                (
                    str(row.get(source_column) or "").strip().casefold()
                    for token in source_tokens
                    for source_column in columns_by_token.get(token, [])
                    if str(row.get(source_column) or "").strip()
                ),
                "unattributed",
            )
            return True, evidence, source

    if selection == "multi":
        selected = False
        selected_sources: list[str] = []
        for item in allowed_values:
            leaf_column = f"{attribute_id}__{item['id']}"
            raw_value = str(row.get(leaf_column) or "").strip().casefold()
            if raw_value in {"1", "true", "yes"}:
                evidence[leaf_column] = str(row.get(leaf_column) or "").strip()
                selected = True
                leaf_source_token = (
                    f"{_normalise_mapping_token(leaf_column)}_effective_source"
                )
                selected_sources.append(
                    next(
                        (
                            str(row.get(source_column) or "").strip().casefold()
                            for source_column in columns_by_token.get(
                                leaf_source_token, []
                            )
                            if str(row.get(source_column) or "").strip()
                        ),
                        "unattributed",
                    )
                )
        if selected:
            unique_sources = set(selected_sources)
            source = next(iter(unique_sources)) if len(unique_sources) == 1 else "mixed"
            return True, evidence, source
        for suffix in ("unknown", "other", "not_in_taxonomy"):
            flag_column = f"{attribute_id}__{suffix}"
            raw_value = str(row.get(flag_column) or "").strip()
            if raw_value:
                evidence[flag_column] = raw_value
    return False, evidence, "unresolved"


def _is_supported_local_image(path: Path) -> bool:
    suffix = path.suffix.casefold()
    if suffix not in {".avif", ".gif", ".jpeg", ".jpg", ".png", ".webp"}:
        return False
    try:
        with path.open("rb") as handle:
            header = handle.read(64)
    except OSError:
        return False
    if suffix in {".jpeg", ".jpg"}:
        return header.startswith(b"\xff\xd8\xff")
    if suffix == ".png":
        return header.startswith(b"\x89PNG\r\n\x1a\n")
    if suffix == ".gif":
        return header.startswith((b"GIF87a", b"GIF89a"))
    if suffix == ".webp":
        return (
            len(header) >= 12 and header.startswith(b"RIFF") and header[8:12] == b"WEBP"
        )
    return (
        len(header) >= 12
        and header[4:8] == b"ftyp"
        and (header[8:12] in {b"avif", b"avis"} or b"avif" in header[8:32])
    )


@lru_cache(maxsize=8)
def _cached_local_image_manifest(
    path_text: str,
    modified_ns: int,
    size_bytes: int,
) -> dict[str, Any]:
    """Load one sidecar manifest keyed by file identity for repeated task rows."""

    del modified_ns, size_bytes
    return _load_json(Path(path_text))


def _local_sidecar_image(
    package_dir: Path,
    row: Mapping[str, str],
) -> tuple[Path, str] | None:
    manifest_path = package_dir / "local_image_manifest.json"
    if not manifest_path.is_file():
        return None
    stat = manifest_path.stat()
    manifest = _cached_local_image_manifest(
        str(manifest_path.resolve()), stat.st_mtime_ns, stat.st_size
    )
    if manifest.get("schema_version") != LOCAL_IMAGE_MANIFEST_SCHEMA:
        raise ContractError("Unsupported local image manifest schema")
    if Path(str(manifest.get("package_dir") or "")).expanduser().resolve() != (
        package_dir.resolve()
    ):
        raise ContractError("Local image manifest belongs to another package")
    product_id = str(
        row.get("parent_product_id") or row.get("listing_identity") or ""
    ).strip()
    entry = next(
        (
            item
            for item in manifest.get("products") or []
            if isinstance(item, dict)
            and str(item.get("product_id") or "") == product_id
        ),
        None,
    )
    if entry is None or entry.get("status") not in {
        "downloaded",
        "existing",
        "reused",
    }:
        return None
    current_row_sha = _source_row_sha256(row)
    source_rows = entry.get("source_rows")
    pinned_row_hashes = (
        {str(value) for value in source_rows.values()}
        if isinstance(source_rows, dict)
        else {str(entry.get("source_row_sha256") or "")}
    )
    if current_row_sha not in pinned_row_hashes:
        raise ContractError(f"Local image manifest is stale for product {product_id}")
    relative = _safe_relative_path(
        str(entry.get("image_path") or ""), label="local image sidecar"
    )
    candidate = (package_dir / relative).resolve()
    image_root = (package_dir / "images").resolve()
    if not candidate.is_file() or not candidate.is_relative_to(image_root):
        raise ContractError(f"Local image sidecar is unavailable: {relative}")
    if not _is_supported_local_image(candidate):
        raise ContractError(
            f"Local image sidecar is not a supported raster: {relative}"
        )
    expected_sha = str(entry.get("sha256") or "")
    if not expected_sha or _sha256_file(candidate) != expected_sha:
        raise ContractError(f"Local image sidecar hash changed: {relative}")
    return candidate, relative.as_posix()


def _local_mapping_images(
    package_dir: Path,
    row: Mapping[str, str],
) -> list[dict[str, str]]:
    images: list[dict[str, str]] = []
    seen_paths: set[str] = set()
    package_root = package_dir.resolve()
    image_root = (package_root / "images").resolve()
    if not image_root.is_relative_to(package_root):
        raise ContractError("Evidence-package image directory escapes the package")
    for field in ("pack_image_file", "pack_image_path"):
        raw_value = str(row.get(field) or "").strip()
        if not raw_value:
            continue
        raw_path = Path(raw_value).expanduser()
        candidate = raw_path if raw_path.is_absolute() else package_dir / raw_path
        if candidate.is_file():
            resolved_path = candidate.resolve()
            if not resolved_path.is_relative_to(image_root):
                raise ContractError(
                    f"Mapping image escapes the package image directory: {resolved_path}"
                )
            if not _is_supported_local_image(resolved_path):
                raise ContractError(
                    f"Mapping image is not a supported raster image: {resolved_path}"
                )
            resolved = str(resolved_path)
            if resolved not in seen_paths:
                images.append(
                    {
                        "path": resolved_path.relative_to(package_root).as_posix(),
                        "sha256": _sha256_file(resolved_path),
                    }
                )
                seen_paths.add(resolved)
    sidecar = _local_sidecar_image(package_dir, row)
    if sidecar is not None:
        resolved_path, relative_path = sidecar
        resolved = str(resolved_path)
        if resolved not in seen_paths:
            images.append(
                {"path": relative_path, "sha256": _sha256_file(resolved_path)}
            )
    return images


def _mapping_task_id(
    retailer: str,
    category_key: str,
    row_type: str,
    parent_product_id: str,
    variant_id: str,
    attribute_id: str,
) -> str:
    stable_key = "|".join(
        [
            retailer,
            category_key,
            row_type,
            parent_product_id,
            variant_id,
            attribute_id,
        ]
    )
    return "map-" + hashlib.sha256(stable_key.encode("utf-8")).hexdigest()[:24]


_MAPPING_IDENTITY_FIELDS = (
    "retailer",
    "row_type",
    "parent_product_id",
    "variant_id",
    "category_key",
    "attribute_id",
)


def _mapping_task_identity(task: Mapping[str, Any]) -> tuple[str, ...]:
    product = task.get("product")
    attribute = task.get("attribute")
    if not isinstance(product, Mapping) or not isinstance(attribute, Mapping):
        raise ContractError("Correction selection requires complete task identities")
    identity = (
        str(product.get("retailer") or "").strip(),
        str(product.get("row_type") or "").strip(),
        str(product.get("parent_product_id") or "").strip(),
        str(product.get("variant_id") or "").strip(),
        str(product.get("category_key") or "").strip(),
        str(attribute.get("id") or "").strip(),
    )
    if any(not value for index, value in enumerate(identity) if index != 3):
        raise ContractError("Correction selection encountered an incomplete identity")
    return identity


def select_codex_effective_correction_tasks(
    tasks: Sequence[Mapping[str, Any]],
    codex_mapping_identities: Iterable[Sequence[str] | Mapping[str, Any]],
) -> dict[str, Any]:
    """Select resolved tasks whose accepted Codex value is report-effective.

    This gate is deterministic because it checks exact source provenance and
    database identity membership; it does not make or override the semantic
    mapping decision itself.
    """

    pinned_identities: set[tuple[str, ...]] = set()
    for raw_identity in codex_mapping_identities:
        if isinstance(raw_identity, Mapping):
            raw_source = str(raw_identity.get("source") or "codex").strip().casefold()
            if raw_source != "codex":
                raise ContractError("Correction state identity must use source=codex")
            identity = (
                str(raw_identity.get("retailer") or "").strip(),
                str(raw_identity.get("row_type") or "").strip(),
                str(raw_identity.get("parent_product_id") or "").strip(),
                str(raw_identity.get("variant_id") or "").strip(),
                str(raw_identity.get("category_key") or "").strip(),
                str(
                    raw_identity.get("attribute_id")
                    or raw_identity.get("base_attribute_id")
                    or ""
                ).strip(),
            )
        else:
            identity_values = tuple(str(value or "").strip() for value in raw_identity)
            if len(identity_values) == len(_MAPPING_IDENTITY_FIELDS) + 1:
                source, *identity_parts = identity_values
                if source.casefold() != "codex":
                    raise ContractError(
                        "Correction state identity must use source=codex"
                    )
                identity = tuple(identity_parts)
            else:
                identity = identity_values
        if len(identity) != len(_MAPPING_IDENTITY_FIELDS) or any(
            not value for index, value in enumerate(identity) if index != 3
        ):
            raise ContractError("Pinned Codex mapping identity is incomplete")
        pinned_identities.add(identity)

    selected: list[dict[str, Any]] = []
    excluded_unresolved = 0
    excluded_non_codex_effective = 0
    excluded_not_pinned = 0
    for raw_task in tasks:
        task = dict(raw_task)
        if str(task.get("mapping_reason") or "") != "migration_recheck":
            excluded_unresolved += 1
            continue
        if str(task.get("existing_evidence_source") or "").casefold() != "codex":
            excluded_non_codex_effective += 1
            continue
        if _mapping_task_identity(task) not in pinned_identities:
            excluded_not_pinned += 1
            continue
        selected.append(task)

    return {
        "schema_version": CORRECTION_TASK_SELECTION_SCHEMA,
        "criteria": {
            "mapping_reason": "migration_recheck",
            "existing_evidence_source": "codex",
            "requires_pinned_codex_identity": True,
        },
        "task_count_before_selection": len(tasks),
        "task_count": len(selected),
        "excluded_unresolved_count": excluded_unresolved,
        "excluded_non_codex_effective_count": excluded_non_codex_effective,
        "excluded_not_pinned_count": excluded_not_pinned,
        "tasks": selected,
    }


def _build_mapping_workset(
    package: Path,
    *,
    retailer: str,
    category_key: str,
    rows: Sequence[Mapping[str, str]],
    attributes: Sequence[Any],
    include_resolved: bool,
) -> tuple[list[dict[str, Any]], dict[str, int]]:
    """Build source-bound product tasks and deterministic coverage counts."""

    tasks: list[dict[str, Any]] = []
    skipped_variant_attributes = 0
    resolved_attribute_cells = 0
    unresolved_attribute_cells = 0
    migration_recheck_tasks = 0
    sorted_rows = sorted(
        rows,
        key=lambda row: str(
            row.get("parent_product_id") or row.get("listing_identity") or ""
        ),
    )
    for row in sorted_rows:
        parent_product_id = str(
            row.get("parent_product_id") or row.get("listing_identity") or ""
        ).strip()
        if not parent_product_id:
            continue
        for attribute in attributes:
            if not isinstance(attribute, dict):
                continue
            if str(attribute.get("scope") or "product").casefold() != "product":
                skipped_variant_attributes += 1
                continue
            attribute_id = str(attribute.get("id") or "").strip()
            attribute_label = str(attribute.get("label") or attribute_id).strip()
            selection = str(attribute.get("selection") or "single").casefold()
            if selection not in {"single", "multi"} or not attribute_id:
                raise ContractError(
                    f"Unsupported taxonomy selection for attribute {attribute_id!r}"
                )
            allowed_values = _taxonomy_leaf_values(attribute.get("nodes"))
            if not allowed_values:
                continue
            resolved, existing_evidence, existing_evidence_source = (
                _row_attribute_evidence(
                    row,
                    attribute_id=attribute_id,
                    attribute_label=attribute_label,
                    selection=selection,
                    allowed_values=allowed_values,
                )
            )
            if resolved:
                resolved_attribute_cells += 1
                if not include_resolved:
                    continue
                migration_recheck_tasks += 1
            else:
                unresolved_attribute_cells += 1
            row_type = "parent"
            variant_id = ""
            task_id = _mapping_task_id(
                retailer,
                category_key,
                row_type,
                parent_product_id,
                variant_id,
                attribute_id,
            )
            description = str(
                row.get("description_excerpt")
                or row.get("summary")
                or row.get("description")
                or ""
            ).strip()
            tasks.append(
                {
                    "task_id": task_id,
                    "product": {
                        "retailer": retailer,
                        "row_type": row_type,
                        "parent_product_id": parent_product_id,
                        "variant_id": variant_id,
                        "category_key": category_key,
                        "source_row_sha256": _source_row_sha256(row),
                        "brand": str(row.get("brand") or "").strip(),
                        "title": str(row.get("product_name") or "").strip(),
                        "description": description[:4000],
                        "pdp_url": _safe_http_url(row.get("pdp_url")),
                        "local_images": _local_mapping_images(package, row),
                    },
                    "attribute": {
                        "id": attribute_id,
                        "label": attribute_label,
                        "selection": selection,
                        "allowed_values": allowed_values,
                    },
                    "existing_evidence": existing_evidence,
                    "existing_evidence_source": existing_evidence_source,
                    "mapping_reason": (
                        "migration_recheck" if resolved else "unresolved"
                    ),
                }
            )
    coverage = {
        "product_rows": len(sorted_rows),
        "resolved_attribute_cells": resolved_attribute_cells,
        "unresolved_attribute_cells": unresolved_attribute_cells,
        "migration_recheck_tasks": migration_recheck_tasks,
        "variant_attribute_cells_skipped": skipped_variant_attributes,
    }
    return tasks, coverage


def create_mapping_tasks(
    package_dir: Path,
    taxonomy: Mapping[str, Any],
    output_path: Path,
    *,
    max_tasks: int = 0,
    include_resolved: bool = False,
) -> dict[str, Any]:
    """Create bounded Codex tasks for unresolved product attributes."""

    package = package_dir.expanduser().resolve()
    integrity_path = _contained_package_path(
        package, "package_integrity.json", label="package integrity"
    )
    summary_path = _contained_package_path(
        package, "summary.json", label="package summary"
    )
    manifest_path = _contained_package_path(
        package, "pack_manifest.json", label="pack manifest"
    )
    integrity = _load_json(integrity_path)
    if str(integrity.get("status") or "").casefold() != "pass":
        raise ContractError("Evidence package integrity is not pass")
    summary = _load_json(summary_path)
    manifest = _load_json(manifest_path)
    category_key = str(summary.get("category_key") or "").strip()
    retailer = str(summary.get("retailer") or "").strip()
    if not category_key or not retailer:
        raise ContractError("Package summary requires retailer and category_key")
    if max_tasks < 0:
        raise ContractError("max_tasks cannot be negative")
    matrix_path = _contained_package_path(
        package, "product_filter_matrix.csv", label="product filter matrix"
    )
    _columns, rows = _read_csv(matrix_path)

    categories = taxonomy.get("categories")
    if not isinstance(categories, list):
        raise ContractError("Central taxonomy has no categories list")
    category = next(
        (
            item
            for item in categories
            if isinstance(item, dict)
            and _normalise_mapping_token(item.get("id"))
            == _normalise_mapping_token(category_key)
        ),
        None,
    )
    if category is None:
        raise ContractError(
            f"Category {category_key!r} is absent from the central taxonomy"
        )
    attributes = category.get("attributes")
    if not isinstance(attributes, list):
        raise ContractError(f"Taxonomy category {category_key!r} has no attributes")

    tasks, coverage_counts = _build_mapping_workset(
        package,
        retailer=retailer,
        category_key=category_key,
        rows=rows,
        attributes=attributes,
        include_resolved=include_resolved,
    )

    total_tasks = len(tasks)
    truncated = bool(max_tasks and total_tasks > max_tasks)
    if truncated:
        tasks = tasks[:max_tasks]
    taxonomy_version = str(taxonomy.get("version") or "").strip()
    if not taxonomy_version:
        raise ContractError("Central taxonomy requires a version")
    payload = {
        "schema_version": MAPPING_TASK_SCHEMA,
        "generated_at": _utc_now(),
        "taxonomy_snapshot": {
            "version": taxonomy_version,
            "sha256": _canonical_json_sha256(taxonomy),
            "category_key": category_key,
        },
        "scope": {
            "retailer": retailer,
            "category_key": category_key,
            "row_type": "parent",
            "source_package": str(package),
            "source_package_sha256": _package_fingerprint(
                package,
                _package_source_paths(package, manifest),
            ),
            "source_pack_manifest_sha256": _sha256_file(manifest_path),
            "source_matrix_sha256": _sha256_file(matrix_path),
            "summary_sha256": _sha256_file(summary_path),
            "package_integrity_sha256": _sha256_file(integrity_path),
        },
        "coverage": {
            **coverage_counts,
            "task_count_before_limit": total_tasks,
            "task_count": len(tasks),
            "truncated": truncated,
            "include_resolved": include_resolved,
        },
        "tasks": tasks,
    }
    mapping_output = output_path.expanduser().resolve()
    _assert_safe_output_dir(mapping_output.parent)
    _write_json(mapping_output, payload)
    return payload


def verify_mapping_tasks_against_source(
    tasks: Mapping[str, Any],
    taxonomy: Mapping[str, Any],
) -> dict[str, Any]:
    """Prove a complete workset was regenerated from its unchanged source matrix."""

    if tasks.get("schema_version") != MAPPING_TASK_SCHEMA:
        raise ContractError("Unsupported mapping task schema")
    scope = tasks.get("scope")
    coverage = tasks.get("coverage")
    raw_tasks = tasks.get("tasks")
    if not isinstance(scope, dict) or not isinstance(coverage, dict):
        raise ContractError("Mapping tasks require source scope and coverage objects")
    if not isinstance(raw_tasks, list):
        raise ContractError("Mapping tasks must contain a tasks list")
    if coverage.get("truncated") is not False:
        raise ContractError("Only a complete, non-truncated workset may be applied")
    include_resolved = coverage.get("include_resolved")
    if not isinstance(include_resolved, bool):
        raise ContractError("Mapping coverage requires include_resolved boolean")

    package = Path(str(scope.get("source_package") or "")).expanduser().resolve()
    source_files = {
        "pack_manifest.json": str(scope.get("source_pack_manifest_sha256") or ""),
        "product_filter_matrix.csv": str(scope.get("source_matrix_sha256") or ""),
        "summary.json": str(scope.get("summary_sha256") or ""),
        "package_integrity.json": str(scope.get("package_integrity_sha256") or ""),
    }
    for file_name, expected_sha256 in source_files.items():
        path = _contained_package_path(package, file_name, label="pinned source")
        if not expected_sha256 or not path.is_file():
            raise ContractError(f"Pinned mapping source is unavailable: {path}")
        if _sha256_file(path) != expected_sha256:
            raise ContractError(f"Pinned mapping source changed: {path}")

    manifest = _load_json(
        _contained_package_path(package, "pack_manifest.json", label="pack manifest")
    )
    expected_package_sha256 = str(scope.get("source_package_sha256") or "")
    if (
        not expected_package_sha256
        or _package_fingerprint(
            package,
            _package_source_paths(package, manifest),
        )
        != expected_package_sha256
    ):
        raise ContractError("Pinned mapping source package fingerprint changed")

    integrity = _load_json(
        _contained_package_path(
            package, "package_integrity.json", label="package integrity"
        )
    )
    if str(integrity.get("status") or "").casefold() != "pass":
        raise ContractError("Pinned mapping source package integrity is not pass")
    summary = _load_json(
        _contained_package_path(package, "summary.json", label="package summary")
    )
    retailer = str(summary.get("retailer") or "").strip()
    category_key = str(summary.get("category_key") or "").strip()
    if (
        not retailer
        or not category_key
        or str(scope.get("retailer") or "") != retailer
        or str(scope.get("category_key") or "") != category_key
        or str(scope.get("row_type") or "") != "parent"
    ):
        raise ContractError("Mapping scope differs from the pinned package summary")

    snapshot = tasks.get("taxonomy_snapshot")
    if not isinstance(snapshot, dict):
        raise ContractError("Mapping tasks require a taxonomy snapshot")
    if (
        str(snapshot.get("version") or "") != str(taxonomy.get("version") or "")
        or str(snapshot.get("sha256") or "") != _canonical_json_sha256(taxonomy)
        or str(snapshot.get("category_key") or "") != category_key
    ):
        raise ContractError("Mapping workset differs from the current central taxonomy")

    categories = taxonomy.get("categories")
    if not isinstance(categories, list):
        raise ContractError("Central taxonomy has no categories list")
    category = next(
        (
            item
            for item in categories
            if isinstance(item, dict)
            and _normalise_mapping_token(item.get("id"))
            == _normalise_mapping_token(category_key)
        ),
        None,
    )
    if category is None or not isinstance(category.get("attributes"), list):
        raise ContractError(
            f"Category {category_key!r} is absent from the central taxonomy"
        )
    _columns, rows = _read_csv(
        _contained_package_path(
            package, "product_filter_matrix.csv", label="product filter matrix"
        )
    )
    expected_tasks, coverage_counts = _build_mapping_workset(
        package,
        retailer=retailer,
        category_key=category_key,
        rows=rows,
        attributes=category["attributes"],
        include_resolved=include_resolved,
    )
    expected_coverage = {
        **coverage_counts,
        "task_count_before_limit": len(expected_tasks),
        "task_count": len(expected_tasks),
        "truncated": False,
        "include_resolved": include_resolved,
    }
    if coverage != expected_coverage:
        raise ContractError("Mapping coverage differs from the pinned source workset")
    if raw_tasks != expected_tasks:
        raise ContractError("Mapping tasks differ from the pinned source workset")
    return dict(scope)


def _package_source_paths(package_dir: Path, manifest: Mapping[str, Any]) -> list[Path]:
    package_root = package_dir.resolve()
    paths: set[Path] = {
        _contained_package_path(
            package_root, "pack_manifest.json", label="pack manifest"
        )
    }
    raw_warnings_path = package_root / "package_warnings.json"
    if raw_warnings_path.exists():
        warnings_path = _contained_package_path(
            package_root, "package_warnings.json", label="package warnings"
        )
        if warnings_path.is_file():
            paths.add(warnings_path)
    files = manifest.get("files")
    if not isinstance(files, dict):
        raise ContractError("pack_manifest.json must contain a files object")
    for file_key, raw_value in files.items():
        # Image bytes are hydrated locally and do not affect analytical
        # arithmetic. Selected mapping/report images are pinned separately by
        # exact hashes, so excluding this directory keeps the structured server
        # package fingerprint stable before and after local hydration.
        if str(file_key) == "images_dir":
            continue
        if not isinstance(raw_value, str) or not raw_value.strip():
            continue
        relative = _safe_relative_path(raw_value, label="pack manifest file")
        candidate = _contained_package_path(
            package_root, relative, label="pack manifest file"
        )
        if candidate.is_file():
            paths.add(candidate)
        elif candidate.is_dir():
            for raw_path in candidate.rglob("*"):
                if not raw_path.is_file():
                    continue
                relative_child = raw_path.relative_to(package_root)
                paths.add(
                    _contained_package_path(
                        package_root,
                        relative_child,
                        label="pack manifest directory file",
                    )
                )
    return sorted(paths, key=lambda item: item.relative_to(package_root).as_posix())


def _package_fingerprint(package_dir: Path, paths: Sequence[Path]) -> str:
    digest = hashlib.sha256()
    package_root = package_dir.resolve()
    for path in paths:
        relative = path.relative_to(package_root).as_posix().encode("utf-8")
        digest.update(relative)
        digest.update(b"\0")
        digest.update(_sha256_file(path).encode("ascii"))
        digest.update(b"\n")
    return digest.hexdigest()


def _normalise_warning(
    code: str,
    message: str,
    *,
    source: str,
    interpretation: str = "",
) -> dict[str, str]:
    return {
        "code": code,
        "message": message.strip(),
        "interpretation": interpretation.strip(),
        "source": source,
    }


def _collect_package_warnings(
    package_dir: Path,
    summary: Mapping[str, Any],
    manifest: Mapping[str, Any],
    integrity: Mapping[str, Any],
) -> list[dict[str, str]]:
    warnings: list[dict[str, str]] = []
    seen: set[str] = set()

    def add(item: dict[str, str]) -> None:
        if item["code"] not in seen:
            warnings.append(item)
            seen.add(item["code"])

    overlap = manifest.get("sort_overlap_quality") or summary.get(
        "sort_overlap_quality"
    )
    if isinstance(overlap, dict) and str(overlap.get("status") or "").lower() not in {
        "",
        "pass",
        "ok",
    }:
        add(
            _normalise_warning(
                "sort_overlap_quality",
                str(overlap.get("warning") or "Ranked cohort overlap needs care."),
                source="pack_manifest.json:sort_overlap_quality",
                interpretation=str(overlap.get("interpretation") or ""),
            )
        )

    diagnostic_warnings = summary.get("diagnostic_warnings")
    if isinstance(diagnostic_warnings, list):
        for index, value in enumerate(diagnostic_warnings, start=1):
            if isinstance(value, dict):
                message = str(value.get("message") or value.get("warning") or "")
                code = str(value.get("code") or f"diagnostic_warning_{index}")
            else:
                message = str(value)
                code = f"diagnostic_warning_{index}"
            if message.strip():
                add(
                    _normalise_warning(
                        code,
                        message,
                        source="summary.json:diagnostic_warnings",
                    )
                )

    issues = integrity.get("issues")
    if isinstance(issues, list):
        for index, value in enumerate(issues, start=1):
            if not isinstance(value, dict):
                continue
            severity = str(value.get("severity") or value.get("status") or "").lower()
            if severity not in {"warning", "caveat"}:
                continue
            code = str(
                value.get("check_id")
                or value.get("code")
                or f"integrity_warning_{index}"
            )
            message = str(value.get("message") or value.get("detail") or code)
            add(
                _normalise_warning(
                    code,
                    message,
                    source="package_integrity.json:issues",
                )
            )

    raw_warnings_path = package_dir / "package_warnings.json"
    if raw_warnings_path.exists():
        warnings_path = _contained_package_path(
            package_dir, "package_warnings.json", label="package warnings"
        )
        payload = _load_json(warnings_path)
        raw_items = payload.get("warnings") or payload.get("issues") or []
        if isinstance(raw_items, list):
            for index, value in enumerate(raw_items, start=1):
                if isinstance(value, dict):
                    code = str(
                        value.get("code")
                        or value.get("check_id")
                        or f"package_warning_{index}"
                    )
                    message = str(value.get("message") or value.get("warning") or code)
                    interpretation = str(value.get("interpretation") or "")
                else:
                    code = f"package_warning_{index}"
                    message = str(value)
                    interpretation = ""
                add(
                    _normalise_warning(
                        code,
                        message,
                        source="package_warnings.json",
                        interpretation=interpretation,
                    )
                )
    return warnings


def _load_attribute_table_builder() -> Any:
    plugin_root = Path(__file__).resolve().parents[1]
    candidates = [plugin_root / "vendor", plugin_root.parents[1]]
    for candidate in candidates:
        if (candidate / "modules" / "pdp" / "attribute_table_templates.py").exists():
            candidate_text = str(candidate)
            if candidate_text not in sys.path:
                sys.path.insert(0, candidate_text)
            from modules.pdp.attribute_table_templates import (  # noqa: PLC0415
                build_attribute_tables_from_package,
            )

            return build_attribute_tables_from_package
    raise ContractError(
        "The deterministic attribute-table runtime is unavailable. Run the plugin "
        "dependency checker and use the packaged plugin or the app repository."
    )


def _build_attribute_tables(package_dir: Path, evidence_dir: Path) -> dict[str, Any]:
    builder = _load_attribute_table_builder()
    result = dict(builder(package_dir, output_dir=evidence_dir))
    enriched_tables: list[dict[str, Any]] = []
    for raw_item in result.get("tables") or []:
        item = dict(raw_item)
        csv_relative = _safe_relative_path(
            str(item["csv"]), label="attribute table CSV"
        )
        html_relative = _safe_relative_path(
            str(item["html"]), label="attribute table HTML"
        )
        item["csv_sha256"] = _sha256_file(evidence_dir / csv_relative)
        item["html_sha256"] = _sha256_file(evidence_dir / html_relative)
        enriched_tables.append(item)
    result["tables"] = enriched_tables
    return result


def _catalog_source(
    package_dir: Path, file_name: str, preview_rows: int
) -> dict[str, Any]:
    raw_path = package_dir / file_name
    if not raw_path.exists():
        return {
            "file": file_name,
            "status": "missing",
            "sha256": None,
            "row_count": 0,
            "columns": [],
            "preview": [],
        }
    path = _contained_package_path(package_dir, file_name, label="catalog source")
    if path.suffix.lower() == ".csv":
        columns, rows = _read_csv(path)
        return {
            "file": file_name,
            "status": "available",
            "sha256": _sha256_file(path),
            "row_count": len(rows),
            "columns": columns,
            "preview": rows[:preview_rows],
        }
    payload = _load_json(path)
    return {
        "file": file_name,
        "status": "available",
        "sha256": _sha256_file(path),
        "row_count": 1,
        "columns": sorted(payload),
        "preview": [payload],
    }


def _report_model_template(
    *,
    report_id: str,
    author_agent_id: str,
    summary: Mapping[str, Any],
    warnings: Sequence[Mapping[str, str]],
) -> dict[str, Any]:
    retailer = str(
        summary.get("retailer_label") or summary.get("retailer") or "Retailer"
    )
    category = str(
        summary.get("category_label") or summary.get("category_key") or "Category"
    )
    titles = {
        "executive_summary": "Executive summary",
        "winning_now": "Winning now",
        "brand_context": "Brand context",
        "emerging_signal": "Emerging signal",
        "winner_emerging_bridge": "Winners and emerging signals",
        "product_evidence": "Product evidence",
        "method_and_caveats": "Method and caveats",
    }
    return {
        "schema_version": MODEL_SCHEMA,
        "report_id": report_id,
        "author": {
            "execution": "codex_agent",
            "agent_id": author_agent_id,
            "role": "report_author",
        },
        "title": f"{retailer} {category}",
        "subtitle": "Attribute signals across retailer-defined newness and sales rank",
        "audience": "Market and product teams",
        "acknowledged_warning_codes": [item["code"] for item in warnings],
        "sections": [
            {
                "section_id": section_id,
                "title": titles[section_id],
                "summary": "",
                "claim_ids": [],
                "table_keys": [],
            }
            for section_id in REQUIRED_SECTION_IDS
        ],
        "claims": [],
        "featured_products": [],
        "limitations": [
            {
                "code": item["code"],
                "text": item["message"],
            }
            for item in warnings
        ],
        "authoring_status": "template_requires_codex",
    }


def _semantic_review_template(
    *,
    report_id: str,
    author_agent_id: str,
) -> dict[str, Any]:
    return {
        "schema_version": REVIEW_SCHEMA,
        "review_id": "replace-with-independent-review-id",
        "reviewer": {
            "execution": "codex_agent",
            "agent_id": "replace-with-independent-agent-id",
            "role": "independent_reviewer",
            "tier": "low_cost",
            "independent_from_author": True,
        },
        "author_agent_id": author_agent_id,
        "targets": {
            "report_id": report_id,
            "evidence_catalog_sha256": "replace-after-render",
            "report_model_sha256": "replace-after-render",
            "draft_html_sha256": "replace-after-render",
        },
        "overall_verdict": "unable_to_determine",
        "summary": "Independent semantic review has not run.",
        "dimensions": {
            dimension: {
                "status": "unable_to_determine",
                "rationale": "Not reviewed.",
            }
            for dimension in REQUIRED_REVIEW_DIMENSIONS
        },
        "claim_reviews": [],
        "report_level_findings": [],
        "images_reviewed": [],
    }


def _receipt_integer(value: Any, *, label: str) -> int:
    """Return one non-negative receipt integer without accepting booleans."""

    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ContractError(f"{label} must be a non-negative integer")
    return value


def _receipt_sha256(value: Any, *, label: str) -> str:
    """Return one canonical SHA-256 receipt value."""

    checksum = str(value or "")
    if not re.fullmatch(r"[0-9a-f]{64}", checksum):
        raise ContractError(f"{label} must be a lowercase SHA-256 value")
    return checksum


def _receipt_relative_path(value: Any, *, label: str) -> Path:
    """Return one canonical POSIX path from an extraction receipt."""

    raw_value = str(value or "")
    if "\\" in raw_value:
        raise ContractError(f"{label} must use POSIX separators")
    relative = _safe_relative_path(raw_value, label=label)
    if relative.as_posix() != raw_value:
        raise ContractError(f"{label} is not a canonical relative path: {raw_value!r}")
    return relative


def _path_without_symlink_components(path: Path, *, label: str) -> Path:
    """Resolve an existing path after rejecting every symlink component."""

    expanded = path.expanduser()
    absolute = expanded if expanded.is_absolute() else Path.cwd() / expanded
    absolute = Path(os.path.abspath(absolute))
    current = Path(absolute.anchor)
    for part in absolute.parts[1:]:
        current /= part
        if current.is_symlink():
            raise ContractError(f"{label} cannot contain symlinks: {path}")
    return absolute.resolve()


def _load_local_transport_receipt(path: Path, *, label: str) -> dict[str, Any]:
    """Load one small ordinary receipt from a path without symlinks."""

    resolved = _path_without_symlink_components(path, label=label)
    if not resolved.is_file():
        raise ContractError(f"{label} is unavailable: {resolved}")
    if resolved.stat().st_size > MAX_LOCAL_TRANSPORT_RECEIPT_BYTES:
        raise ContractError(f"{label} exceeds the local receipt size limit")
    return _load_json(resolved)


def _load_no_work_workset(path: Path) -> tuple[Path, dict[str, Any]]:
    """Load one bounded public no-work envelope without following symlinks."""

    resolved = _path_without_symlink_components(
        path,
        label="No-work mapping workset",
    )
    if not resolved.is_file():
        raise ContractError(f"No-work mapping workset is unavailable: {resolved}")
    if resolved.stat().st_size > MAX_NO_WORK_WORKSET_BYTES:
        raise ContractError("No-work mapping workset exceeds the local size limit")
    return resolved, _load_json(resolved)


def _validate_no_work_workset(
    workset: Mapping[str, Any],
    *,
    package_summary: Mapping[str, Any],
    expected_job_id: str,
) -> dict[str, Any]:
    """Validate an explicit server no-work branch against its preliminary pack."""

    if workset.get("schema_version") != (
        f"{SERVER_BRIDGE_SCHEMA_PREFIX}.mapping_workset.v1"
    ):
        raise ContractError("Unsupported no-work mapping-workset schema")
    if workset.get("status") != "no_work":
        raise ContractError("No-work mapping workset must have status no_work")
    if workset.get("mapping_mode") != "unresolved":
        raise ContractError("No-work mapping workset must use unresolved mode")
    if workset.get("correction_reason") not in {None, ""}:
        raise ContractError("No-work mapping workset cannot carry a correction reason")

    evidence_job_id = str(workset.get("evidence_job_id") or "").strip()
    if not evidence_job_id or evidence_job_id != expected_job_id:
        raise ContractError(
            "No-work mapping workset belongs to another evidence download"
        )
    tasks = workset.get("mapping_tasks")
    if (
        not isinstance(tasks, dict)
        or tasks.get("schema_version") != MAPPING_TASK_SCHEMA
    ):
        raise ContractError("No-work mapping workset has invalid mapping tasks")
    task_rows = tasks.get("tasks")
    if task_rows != []:
        raise ContractError("No-work mapping workset must contain zero tasks")
    coverage = tasks.get("coverage")
    if not isinstance(coverage, dict):
        raise ContractError("No-work mapping workset has no coverage object")

    integer_fields = (
        "task_count",
        "task_count_before_limit",
        "resolved_attribute_cells",
        "unresolved_attribute_cells",
        "variant_attribute_cells_skipped",
    )
    counts: dict[str, int] = {}
    for field in integer_fields:
        value = coverage.get(field)
        if isinstance(value, bool) or not isinstance(value, int) or value < 0:
            raise ContractError(
                f"No-work mapping coverage {field} must be a non-negative integer"
            )
        counts[field] = value
    if counts["task_count"] != 0 or counts["task_count_before_limit"] != 0:
        raise ContractError("No-work mapping coverage must report zero tasks")
    if counts["unresolved_attribute_cells"] != 0:
        raise ContractError(
            "No-work mapping coverage cannot report unresolved product cells"
        )
    if coverage.get("include_resolved") is not False:
        raise ContractError("No-work mapping coverage must exclude resolved cells")
    if coverage.get("truncated") is not False:
        raise ContractError("No-work mapping coverage cannot be truncated")

    scope = tasks.get("scope")
    if not isinstance(scope, dict):
        raise ContractError("No-work mapping tasks have no source scope")
    expected_retailer = str(package_summary.get("retailer") or "")
    expected_category = str(package_summary.get("category_key") or "")
    if (
        str(scope.get("retailer") or "") != expected_retailer
        or str(scope.get("category_key") or "") != expected_category
    ):
        raise ContractError("No-work mapping workset belongs to another package scope")
    if str(scope.get("source_package") or "") != f"evidence-job:{evidence_job_id}":
        raise ContractError("No-work mapping workset has an invalid evidence locator")
    if str(workset.get("workset_sha256") or "") != _canonical_json_sha256(tasks):
        raise ContractError("No-work mapping workset hash is inconsistent")

    return {
        "schema_version": NO_WORK_MAPPING_BASIS_SCHEMA,
        "status": "no_work",
        "mapping_mode": "unresolved",
        "mapping_review": "not_applicable",
        "evidence_job_id": evidence_job_id,
        "workset_id": str(workset.get("workset_id") or ""),
        "task_count": 0,
        "include_resolved": False,
        "resolved_attribute_cells": counts["resolved_attribute_cells"],
        "unresolved_attribute_cells": 0,
        "variant_attribute_cells_skipped": counts["variant_attribute_cells_skipped"],
    }


def _package_file_ledger(package_dir: Path) -> dict[str, Path]:
    """Return every ordinary package file while rejecting links/special files."""

    package = package_dir.resolve()
    files: dict[str, Path] = {}
    for candidate in package.rglob("*"):
        relative = candidate.relative_to(package).as_posix()
        if candidate.is_symlink():
            raise ContractError(
                f"Evidence package contains a symlink after extraction: {relative}"
            )
        if candidate.is_dir():
            continue
        if not candidate.is_file():
            raise ContractError(
                f"Evidence package contains a non-regular file: {relative}"
            )
        files[relative] = candidate
    return files


def _validate_hydration_additions(
    package_dir: Path,
    *,
    current_files: Mapping[str, Path],
    addition_paths: set[str],
) -> None:
    """Verify that post-extraction files are genuine local image hydration output."""

    if not addition_paths:
        return
    manifest_path = current_files.get("local_image_manifest.json")
    if manifest_path is None:
        raise ContractError(
            "Post-extraction image files require local_image_manifest.json"
        )
    manifest = _load_json(manifest_path)
    if manifest.get("schema_version") != LOCAL_IMAGE_MANIFEST_SCHEMA:
        raise ContractError("Unsupported local image manifest schema")
    manifest_package = Path(str(manifest.get("package_dir") or "")).expanduser()
    if manifest_package.resolve() != package_dir.resolve():
        raise ContractError("Local image manifest belongs to another package")

    referenced_images: dict[str, tuple[str, int]] = {}
    products = manifest.get("products")
    if not isinstance(products, list):
        raise ContractError("Local image manifest products must be a list")
    for product in products:
        if not isinstance(product, dict):
            raise ContractError("Local image manifest contains an invalid product")
        raw_image_path = str(product.get("image_path") or "")
        if not raw_image_path:
            continue
        if product.get("status") not in {"downloaded", "existing", "reused"}:
            raise ContractError(
                f"Local image manifest has an image for invalid status: {raw_image_path}"
            )
        image_relative = _receipt_relative_path(
            raw_image_path,
            label="local image manifest path",
        )
        if image_relative.parts[:2] != ("images", "local"):
            continue
        image_sha256 = _receipt_sha256(
            product.get("sha256"),
            label=f"local image hash for {raw_image_path}",
        )
        image_size = _receipt_integer(
            product.get("byte_count"),
            label=f"local image size for {raw_image_path}",
        )
        prior = referenced_images.setdefault(
            image_relative.as_posix(),
            (image_sha256, image_size),
        )
        if prior != (image_sha256, image_size):
            raise ContractError(
                f"Local image manifest conflicts for {image_relative.as_posix()}"
            )

    for relative in sorted(addition_paths):
        if relative == "local_image_manifest.json":
            continue
        path = current_files[relative]
        expected = referenced_images.get(relative)
        if expected is None:
            raise ContractError(
                f"Unpinned post-extraction image file is not allowed: {relative}"
            )
        if not _is_supported_local_image(path):
            raise ContractError(
                f"Post-extraction image is not a supported raster: {relative}"
            )
        expected_sha256, expected_size = expected
        if (
            path.stat().st_size != expected_size
            or _sha256_file(path) != expected_sha256
        ):
            raise ContractError(
                f"Post-extraction image differs from its manifest: {relative}"
            )


def _validate_local_transport_receipts(
    package_dir: Path,
    download_receipt: Mapping[str, Any],
    extraction_receipt: Mapping[str, Any],
) -> dict[str, Any]:
    """Validate authenticated-download lineage against the current local package."""

    expected_download_keys = {
        "schema_version",
        "job_id",
        "path",
        "sha256",
        "size_bytes",
    }
    expected_extraction_keys = {
        "schema_version",
        "archive_path",
        "archive_sha256",
        "output_dir",
        "file_count",
        "total_size_bytes",
        "files",
    }
    if set(download_receipt) != expected_download_keys:
        raise ContractError("Local download receipt has an invalid v1 schema")
    if set(extraction_receipt) != expected_extraction_keys:
        raise ContractError("Local extraction receipt has an invalid v1 schema")
    if download_receipt.get("schema_version") != LOCAL_DOWNLOAD_RECEIPT_SCHEMA:
        raise ContractError("Unsupported local download receipt schema")
    if extraction_receipt.get("schema_version") != LOCAL_EXTRACTION_RECEIPT_SCHEMA:
        raise ContractError("Unsupported local extraction receipt schema")
    job_id = str(download_receipt.get("job_id") or "").strip()
    if not job_id or len(job_id) > 256:
        raise ContractError("Local download receipt requires a bounded job_id")

    archive = _path_without_symlink_components(
        Path(str(download_receipt.get("path") or "")),
        label="Downloaded evidence archive",
    )
    extraction_archive = _path_without_symlink_components(
        Path(str(extraction_receipt.get("archive_path") or "")),
        label="Extracted evidence archive",
    )
    if archive != extraction_archive:
        raise ContractError(
            "Download and extraction receipts identify different archives"
        )
    if not archive.is_file():
        raise ContractError(f"Downloaded evidence archive is unavailable: {archive}")
    archive_sha256 = _receipt_sha256(
        download_receipt.get("sha256"),
        label="download receipt archive hash",
    )
    extraction_archive_sha256 = _receipt_sha256(
        extraction_receipt.get("archive_sha256"),
        label="extraction receipt archive hash",
    )
    if archive_sha256 != extraction_archive_sha256:
        raise ContractError("Download and extraction archive hashes differ")
    archive_size = _receipt_integer(
        download_receipt.get("size_bytes"),
        label="download receipt archive size",
    )
    if (
        archive.stat().st_size != archive_size
        or _sha256_file(archive) != archive_sha256
    ):
        raise ContractError("Downloaded evidence archive changed after verification")

    package = package_dir.expanduser().resolve()
    extraction_output = _path_without_symlink_components(
        Path(str(extraction_receipt.get("output_dir") or "")),
        label="Evidence extraction output",
    )
    if extraction_output != package:
        raise ContractError("Extraction receipt belongs to another package directory")
    raw_files = extraction_receipt.get("files")
    if not isinstance(raw_files, list) or len(raw_files) > 1_000:
        raise ContractError("Local extraction receipt has an invalid files ledger")
    expected_files: dict[str, tuple[str, int]] = {}
    casefold_paths: set[str] = set()
    for item in raw_files:
        if not isinstance(item, dict) or set(item) != {
            "path",
            "sha256",
            "size_bytes",
        }:
            raise ContractError("Local extraction receipt has an invalid file row")
        relative = _receipt_relative_path(
            item.get("path"),
            label="extraction receipt file",
        ).as_posix()
        collision_key = relative.casefold()
        if relative in expected_files or collision_key in casefold_paths:
            raise ContractError(
                f"Local extraction receipt has a duplicate file: {relative}"
            )
        casefold_paths.add(collision_key)
        expected_files[relative] = (
            _receipt_sha256(
                item.get("sha256"),
                label=f"extraction receipt hash for {relative}",
            ),
            _receipt_integer(
                item.get("size_bytes"),
                label=f"extraction receipt size for {relative}",
            ),
        )
    expected_count = _receipt_integer(
        extraction_receipt.get("file_count"),
        label="extraction receipt file_count",
    )
    expected_total = _receipt_integer(
        extraction_receipt.get("total_size_bytes"),
        label="extraction receipt total_size_bytes",
    )
    if expected_count != len(expected_files) or expected_total != sum(
        size for _checksum, size in expected_files.values()
    ):
        raise ContractError("Local extraction receipt summary differs from its ledger")

    current_files = _package_file_ledger(package)
    for relative, (expected_sha256, expected_size) in expected_files.items():
        path = current_files.get(relative)
        if path is None:
            raise ContractError(
                f"Extracted package file is missing after extraction: {relative}"
            )
        if (
            path.stat().st_size != expected_size
            or _sha256_file(path) != expected_sha256
        ):
            raise ContractError(
                f"Extracted package file changed after extraction: {relative}"
            )
    addition_paths = set(current_files) - set(expected_files)
    invalid_additions = sorted(
        relative
        for relative in addition_paths
        if relative != "local_image_manifest.json"
        and not relative.startswith("images/local/")
    )
    if invalid_additions:
        raise ContractError(
            "Evidence package has unapproved post-extraction files: "
            + ", ".join(invalid_additions)
        )
    _validate_hydration_additions(
        package,
        current_files=current_files,
        addition_paths=addition_paths,
    )
    return {
        "schema_version": TRANSPORT_LINEAGE_SCHEMA,
        "status": "verified",
        "download": {
            "job_id": job_id,
            "archive_path": str(archive),
            "archive_sha256": archive_sha256,
            "archive_size_bytes": archive_size,
        },
        "extraction": {
            "package_dir": str(package),
            "file_count": expected_count,
            "total_size_bytes": expected_total,
            "hydration_additions": sorted(addition_paths),
        },
    }


def _load_transport_receipts(
    package_dir: Path,
    *,
    download_receipt_path: Path | None,
    extraction_receipt_path: Path | None,
    required: bool,
) -> tuple[dict[str, Any] | None, tuple[Path, Path] | None]:
    """Load and validate a complete local receipt pair when supplied or required."""

    supplied = (download_receipt_path is not None, extraction_receipt_path is not None)
    if required and not all(supplied):
        raise ContractError(
            "Server provenance requires both --download-receipt and "
            "--extraction-receipt"
        )
    if any(supplied) and not all(supplied):
        raise ContractError(
            "Download and extraction receipts must be supplied together"
        )
    if not any(supplied):
        return None, None
    if download_receipt_path is None or extraction_receipt_path is None:
        raise ContractError(
            "Download and extraction receipts must be supplied together"
        )
    download_source = _path_without_symlink_components(
        download_receipt_path,
        label="Local download receipt",
    )
    extraction_source = _path_without_symlink_components(
        extraction_receipt_path,
        label="Local extraction receipt",
    )
    download = _load_local_transport_receipt(
        download_source,
        label="Local download receipt",
    )
    extraction = _load_local_transport_receipt(
        extraction_source,
        label="Local extraction receipt",
    )
    lineage = _validate_local_transport_receipts(package_dir, download, extraction)
    return lineage, (download_source, extraction_source)


def _copy_transport_receipts(
    package_dir: Path,
    output_dir: Path,
    receipt_sources: tuple[Path, Path],
) -> dict[str, Any]:
    """Copy validated transport receipts and bind their exact output hashes."""

    targets = tuple(
        output_dir / file_name for file_name in LOCAL_TRANSPORT_RECEIPT_FILES
    )
    for source, target in zip(receipt_sources, targets, strict=True):
        if source != target.resolve():
            shutil.copyfile(source, target)
    download = _load_local_transport_receipt(
        targets[0],
        label="Copied local download receipt",
    )
    extraction = _load_local_transport_receipt(
        targets[1],
        label="Copied local extraction receipt",
    )
    lineage = _validate_local_transport_receipts(package_dir, download, extraction)
    return {
        **lineage,
        "artifacts": {target.name: _sha256_file(target) for target in targets},
    }


def _validate_server_mapping_acceptance(
    *,
    provenance_root: Path,
    provenance_payloads: Mapping[str, Mapping[str, Any]],
    review_validation: Mapping[str, Any],
    package_summary: Mapping[str, Any],
) -> dict[str, Any]:
    """Validate the server receipts that prove reviewed mappings were accepted."""

    submission = _load_json(provenance_root / "mapping_submission_receipt.json")
    server_review = _load_json(provenance_root / "mapping_review_validation.json")
    sanitization = _load_json(provenance_root / "server_sanitization_receipt.json")
    if submission.get("schema_version") != (
        f"{SERVER_BRIDGE_SCHEMA_PREFIX}.mapping_submission_receipt.v1"
    ):
        raise ContractError("Unsupported server mapping-submission receipt schema")
    if server_review.get("schema_version") != MAPPING_REVIEW_VALIDATION_SCHEMA:
        raise ContractError("Unsupported server mapping-review validation schema")
    if sanitization.get("schema_version") != (
        f"{SERVER_BRIDGE_SCHEMA_PREFIX}.package_sanitization.v1"
    ):
        raise ContractError("Unsupported server package-sanitization receipt schema")

    stable_server_review = {
        key: value for key, value in server_review.items() if key != "validated_at"
    }
    stable_local_review = {
        key: value for key, value in review_validation.items() if key != "validated_at"
    }
    if stable_server_review != stable_local_review:
        raise ContractError(
            "Server mapping-review validation differs from the reviewed mappings"
        )

    tasks = provenance_payloads["mapping_tasks.json"]
    decisions = provenance_payloads["mapping_decisions.json"]
    validated = provenance_payloads["validated_mappings.json"]
    expected_validation = validate_mapping_payloads(tasks, decisions)
    if _stable_mapping_validation(validated) != _stable_mapping_validation(
        expected_validation
    ) or validated.get("validation_sha256") != expected_validation.get(
        "validation_sha256"
    ):
        raise ContractError(
            "Server-accepted validated mappings differ from their task decisions"
        )
    expected_operation_id = _canonical_json_sha256(
        {
            "validation_sha256": expected_validation["validation_sha256"],
            "mapping_review_validation_sha256": review_validation[
                "review_validation_sha256"
            ],
        }
    )
    taxonomy_snapshot = tasks.get("taxonomy_snapshot")
    task_scope = tasks.get("scope")
    if not isinstance(taxonomy_snapshot, dict) or not isinstance(task_scope, dict):
        raise ContractError("Server mapping provenance has no pinned taxonomy or scope")
    expected_submission_fields = {
        "operation_id": expected_operation_id,
        "validation_sha256": expected_validation["validation_sha256"],
        "mapping_review_sha256": review_validation["mapping_review_sha256"],
        "mapping_review_validation_sha256": review_validation[
            "review_validation_sha256"
        ],
        "mapping_review_state": review_validation["review_state"],
        "taxonomy_snapshot": {
            "version": taxonomy_snapshot.get("version"),
            "sha256": taxonomy_snapshot.get("sha256"),
        },
    }
    if any(
        submission.get(key) != value
        for key, value in expected_submission_fields.items()
    ):
        raise ContractError("Server mapping-submission receipt is inconsistent")
    if submission.get("database_write") not in {"applied", "already_applied"}:
        raise ContractError("Server mapping-submission receipt has no accepted write")
    if not str(submission.get("submitted_by") or "").strip():
        raise ContractError("Server mapping-submission receipt has no actor")
    if review_validation.get("review_state") not in {
        "approved",
        "approved_with_caveats",
    }:
        raise ContractError("Server mapping review does not approve the mappings")

    if str(task_scope.get("retailer") or "") != str(
        package_summary.get("retailer") or ""
    ) or str(task_scope.get("category_key") or "") != str(
        package_summary.get("category_key") or ""
    ):
        raise ContractError(
            "Server-accepted mappings belong to another retailer/category scope"
        )
    expected_hash_files = (
        *MAPPING_PROVENANCE_FILES,
        *SERVER_MAPPING_PROVENANCE_FILES[:2],
    )
    expected_hashes = {
        file_name: _sha256_file(provenance_root / file_name)
        for file_name in expected_hash_files
    }
    if sanitization.get("mapping_provenance") != expected_hashes:
        raise ContractError(
            "Server package-sanitization receipt does not pin mapping provenance"
        )
    if (
        sanitization.get("image_policy") != "urls_only_no_image_bytes"
        or sanitization.get("package_integrity_status") != "pass"
    ):
        raise ContractError("Server package-sanitization receipt is not approved")
    return {
        "status": "server_accepted",
        "operation_id": expected_operation_id,
        "submitted_by": submission["submitted_by"],
        "database_write": submission["database_write"],
        "artifacts": {
            file_name: _sha256_file(provenance_root / file_name)
            for file_name in SERVER_MAPPING_PROVENANCE_FILES
        },
    }


def _validate_preliminary_sanitization_receipt(package_dir: Path) -> str:
    """Validate the URL-only, no-mapping receipt on a preliminary server pack."""

    receipt_path = _contained_package_path(
        package_dir,
        "server_sanitization_receipt.json",
        label="preliminary server sanitization receipt",
    )
    if not receipt_path.is_file():
        raise ContractError(
            "A no-work server package requires server_sanitization_receipt.json"
        )
    receipt = _load_json(receipt_path)
    if receipt.get("schema_version") != (
        f"{SERVER_BRIDGE_SCHEMA_PREFIX}.package_sanitization.v1"
    ):
        raise ContractError("Unsupported preliminary server sanitization schema")
    if (
        receipt.get("image_policy") != "urls_only_no_image_bytes"
        or receipt.get("package_integrity_status") != "pass"
        or receipt.get("mapping_provenance") != {}
    ):
        raise ContractError(
            "Preliminary server sanitization does not prove a URL-only, "
            "no-mapping-provenance package"
        )
    for field in (
        "removed_image_file_count",
        "sanitized_private_path_field_count",
    ):
        value = receipt.get(field)
        if isinstance(value, bool) or not isinstance(value, int) or value < 0:
            raise ContractError(f"Preliminary server sanitization {field} is invalid")
    return _sha256_file(receipt_path)


def prepare_run(
    package_dir: Path,
    output_dir: Path,
    *,
    author_agent_id: str,
    preview_rows: int = 12,
    require_browser_qa: bool = False,
    mapping_provenance_dir: Path | None = None,
    download_receipt_path: Path | None = None,
    extraction_receipt_path: Path | None = None,
    no_work_workset_path: Path | None = None,
) -> dict[str, Any]:
    """Prepare immutable evidence views and Codex authoring templates."""

    package = package_dir.expanduser().resolve()
    if not package.is_dir():
        raise ContractError(f"Evidence package directory not found: {package}")
    output = _assert_safe_output_dir(output_dir)
    if not author_agent_id.strip():
        raise ContractError("author_agent_id is required")
    if preview_rows < 1 or preview_rows > 100:
        raise ContractError("preview_rows must be between 1 and 100")

    summary_path = _contained_package_path(
        package, "summary.json", label="package summary"
    )
    manifest_path = _contained_package_path(
        package, "pack_manifest.json", label="pack manifest"
    )
    integrity_path = _contained_package_path(
        package, "package_integrity.json", label="package integrity"
    )
    summary = _load_json(summary_path)
    manifest = _load_json(manifest_path)
    integrity = _load_json(integrity_path)
    if str(integrity.get("status") or "").lower() != "pass":
        raise ContractError(
            "Evidence package integrity is not pass; report authoring is blocked."
        )

    provenance_root = (
        mapping_provenance_dir.expanduser().resolve()
        if mapping_provenance_dir is not None
        else package
    )
    provenance_present = {
        file_name: (provenance_root / file_name).is_file()
        for file_name in MAPPING_PROVENANCE_FILES
    }
    server_provenance_present = {
        file_name: (provenance_root / file_name).is_file()
        for file_name in SERVER_MAPPING_PROVENANCE_FILES
    }
    present_server_count = sum(server_provenance_present.values())
    no_work_source: Path | None = None
    no_work_payload: dict[str, Any] | None = None
    if no_work_workset_path is not None:
        no_work_source, no_work_payload = _load_no_work_workset(no_work_workset_path)
        mapping_server_receipts_present = any(
            server_provenance_present[file_name]
            for file_name in SERVER_MAPPING_PROVENANCE_FILES[:2]
        )
        if (
            mapping_provenance_dir is not None
            or any(provenance_present.values())
            or mapping_server_receipts_present
        ):
            raise ContractError(
                "A no-work mapping branch cannot also carry new-mapping provenance"
            )
        if not server_provenance_present["server_sanitization_receipt.json"]:
            raise ContractError(
                "A no-work server package requires its preliminary sanitization receipt"
            )
    transport_validation, receipt_sources = _load_transport_receipts(
        package,
        download_receipt_path=download_receipt_path,
        extraction_receipt_path=extraction_receipt_path,
        required=bool(present_server_count or no_work_payload is not None),
    )
    no_work_basis: dict[str, Any] | None = None
    if no_work_payload is not None:
        if transport_validation is None:
            raise ContractError(
                "A no-work mapping branch requires verified preliminary transport lineage"
            )
        no_work_basis = _validate_no_work_workset(
            no_work_payload,
            package_summary=summary,
            expected_job_id=str(transport_validation["download"]["job_id"]),
        )
        no_work_basis["server_sanitization_receipt_sha256"] = (
            _validate_preliminary_sanitization_receipt(package)
        )

    source_paths = _package_source_paths(package, manifest)
    package_sha256 = _package_fingerprint(package, source_paths)
    warnings = _collect_package_warnings(package, summary, manifest, integrity)
    report_id = "--".join(
        [
            str(summary.get("retailer") or "retailer"),
            str(summary.get("category_key") or "category"),
            datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ"),
        ]
    )
    sources = [
        _catalog_source(package, file_name, preview_rows)
        for file_name in sorted(ALLOWED_EVIDENCE_FILES)
    ]
    output.mkdir(parents=True, exist_ok=True)
    os.chmod(output, 0o700)
    transport_lineage = (
        _copy_transport_receipts(package, output, receipt_sources)
        if receipt_sources is not None
        else None
    )
    if no_work_basis is not None and no_work_source is not None:
        no_work_target = output / NO_WORK_WORKSET_FILE
        if no_work_source != no_work_target.resolve():
            shutil.copyfile(no_work_source, no_work_target)
        os.chmod(no_work_target, 0o600)
        no_work_basis = {
            **no_work_basis,
            "artifact": NO_WORK_WORKSET_FILE,
            "artifact_sha256": _sha256_file(no_work_target),
        }
    evidence_dir = output / "evidence"
    tables_result = _build_attribute_tables(package, evidence_dir)
    provenance: dict[str, Any] | None = None
    if no_work_basis is None and (
        mapping_provenance_dir is not None
        or any(provenance_present.values())
        or present_server_count
    ):
        missing = sorted(
            file_name
            for file_name, is_present in provenance_present.items()
            if not is_present
        )
        if missing:
            raise ContractError(
                "Mapping provenance is incomplete; missing: " + ", ".join(missing)
            )
        provenance_payloads = {
            file_name: _load_json(provenance_root / file_name)
            for file_name in MAPPING_PROVENANCE_FILES
        }
        provenance_validation = validate_mapping_review_payloads(
            provenance_payloads["mapping_tasks.json"],
            provenance_payloads["mapping_decisions.json"],
            provenance_payloads["validated_mappings.json"],
            provenance_payloads["mapping_review.json"],
        )
        if provenance_validation["review_state"] not in {
            "approved",
            "approved_with_caveats",
        }:
            raise ContractError(
                "Mapping provenance is not approved by its independent review."
            )
        if present_server_count not in {0, len(SERVER_MAPPING_PROVENANCE_FILES)}:
            missing_server = sorted(
                file_name
                for file_name, is_present in server_provenance_present.items()
                if not is_present
            )
            raise ContractError(
                "Server mapping provenance is incomplete; missing: "
                + ", ".join(missing_server)
            )
        server_acceptance = (
            _validate_server_mapping_acceptance(
                provenance_root=provenance_root,
                provenance_payloads=provenance_payloads,
                review_validation=provenance_validation,
                package_summary=summary,
            )
            if present_server_count
            else {
                "status": "local_review_only",
                "operation_id": None,
                "submitted_by": None,
                "database_write": None,
                "artifacts": {},
            }
        )
        provenance_hashes: dict[str, str] = {}
        for file_name in MAPPING_PROVENANCE_FILES:
            source = provenance_root / file_name
            target = output / file_name
            if source.resolve() != target.resolve():
                shutil.copyfile(source, target)
            provenance_hashes[file_name] = _sha256_file(target)
        server_provenance_hashes: dict[str, str] = {}
        if present_server_count:
            for file_name in SERVER_MAPPING_PROVENANCE_FILES:
                source = provenance_root / file_name
                target = output / file_name
                if source.resolve() != target.resolve():
                    shutil.copyfile(source, target)
                server_provenance_hashes[file_name] = _sha256_file(target)
            if server_acceptance["artifacts"] != server_provenance_hashes:
                raise ContractError(
                    "Copied server mapping provenance differs from its validated hashes"
                )
        provenance = {
            "source_dir": str(provenance_root),
            "review_state": provenance_validation["review_state"],
            "review_validation_sha256": provenance_validation[
                "review_validation_sha256"
            ],
            "artifacts": provenance_hashes,
            "server_acceptance": {
                **server_acceptance,
                "artifacts": server_provenance_hashes,
            },
        }
    source_hashes = {
        path.relative_to(package).as_posix(): _sha256_file(path)
        for path in source_paths
    }
    catalog = {
        "schema_version": CATALOG_SCHEMA,
        "generated_at": _utc_now(),
        "report_id": report_id,
        "package": {
            "path": str(package),
            "sha256": package_sha256,
            "integrity_sha256": _sha256_file(integrity_path),
            "retailer": summary.get("retailer"),
            "retailer_label": summary.get("retailer_label"),
            "category_key": summary.get("category_key"),
            "category_label": summary.get("category_label"),
            "discovery_crawl_ts": summary.get("discovery_crawl_ts"),
            "recent_definition": manifest.get("definitions", {}).get("recent"),
            "top_seller_definition": manifest.get("definitions", {}).get("top_sellers"),
        },
        "warnings": warnings,
        "source_hashes": source_hashes,
        "sources": sources,
        "attribute_tables": tables_result.get("tables", []),
        "preview_policy": {
            "rows_per_source": preview_rows,
            "meaning": "Preview only; Codex may inspect any full whitelisted source before selecting a claim.",
        },
    }
    if transport_lineage is not None:
        catalog["transport_lineage"] = transport_lineage
    if no_work_basis is not None:
        catalog["mapping_review_basis"] = no_work_basis
    run_intake = {
        "schema_version": RUN_SCHEMA,
        "created_at": _utc_now(),
        "plugin": "attribute-reporting",
        "workflow": "existing_evidence_package_to_private_html",
        "report_id": report_id,
        "inputs": {
            "package_dir": str(package),
            "package_sha256": package_sha256,
            "mapping_provenance": provenance,
            "mapping_review_basis": no_work_basis,
            "transport_lineage": transport_lineage,
        },
        "output_dir": str(output),
        "data_posture": {
            "scrape_execution": "local",
            "structured_data_persistence": "server_database",
            "taxonomy_authority": "central_per_category",
            "product_images": "local_machine",
            "report_storage": "private_local_only",
            "report_uploaded_to_server": False,
            "model_api_calls_from_scripts": False,
            "codex_agent_judgment": True,
        },
        "assumptions": [
            "The supplied database-derived package is treated as the current data snapshot for this run.",
            "New means the retailer-defined newest or new-arrivals cohort already encoded by the package.",
        ],
        "quality_gates": {
            "browser_qa_required": require_browser_qa,
            "mapping_review_required_when_new_mappings_are_present": True,
            "independent_report_review_required": True,
        },
        "execution_trace": [
            {
                "step_id": "package_integrity",
                "kind": "deterministic",
                "status": "pass",
                "execution_location": "local",
                "inputs": [str(package / "package_integrity.json")],
                "outputs": [],
            },
            {
                "step_id": "attribute_tables",
                "kind": "deterministic",
                "status": "pass",
                "execution_location": "local",
                "inputs": [str(package)],
                "outputs": [str(evidence_dir / "attribute_tables")],
            },
            *(
                [
                    {
                        "step_id": "transport_lineage",
                        "kind": "deterministic",
                        "status": "pass",
                        "execution_location": "local",
                        "inputs": [str(path) for path in receipt_sources],
                        "outputs": [
                            str(output / file_name)
                            for file_name in LOCAL_TRANSPORT_RECEIPT_FILES
                        ],
                    }
                ]
                if receipt_sources is not None
                else []
            ),
            *(
                [
                    {
                        "step_id": "mapping_review_basis",
                        "kind": "deterministic",
                        "status": "not_applicable",
                        "execution_location": "local",
                        "inputs": [str(no_work_source)],
                        "outputs": [str(output / NO_WORK_WORKSET_FILE)],
                    }
                ]
                if no_work_basis is not None
                else []
            ),
            *(
                [
                    {
                        "step_id": "mapping_provenance",
                        "kind": "deterministic",
                        "status": "pass",
                        "execution_location": "local",
                        "inputs": [str(provenance_root)],
                        "outputs": [
                            str(output / file_name)
                            for file_name in (
                                *MAPPING_PROVENANCE_FILES,
                                *(
                                    SERVER_MAPPING_PROVENANCE_FILES
                                    if present_server_count
                                    else ()
                                ),
                            )
                        ],
                    }
                ]
                if provenance is not None
                else []
            ),
        ],
    }
    report_model = _report_model_template(
        report_id=report_id,
        author_agent_id=author_agent_id,
        summary=summary,
        warnings=warnings,
    )
    semantic_review = _semantic_review_template(
        report_id=report_id,
        author_agent_id=author_agent_id,
    )
    catalog["run_intake_sha256"] = _canonical_json_sha256(run_intake)
    _write_json(output / "run_intake.json", run_intake)
    _write_json(output / "evidence_catalog.json", catalog)
    _write_json(output / "report_model.json", report_model)
    _write_json(output / "semantic_review.json", semantic_review)
    result = {
        "output_dir": str(output),
        "run_intake": str(output / "run_intake.json"),
        "evidence_catalog": str(output / "evidence_catalog.json"),
        "report_model": str(output / "report_model.json"),
        "semantic_review": str(output / "semantic_review.json"),
    }
    if provenance is not None:
        result["mapping_provenance"] = provenance
    if no_work_basis is not None:
        result["mapping_review_basis"] = no_work_basis
    if transport_lineage is not None:
        result["transport_lineage"] = transport_lineage
    return result


def _json_path_value(payload: Mapping[str, Any], path_parts: Sequence[str]) -> Any:
    current: Any = payload
    for part in path_parts:
        if not isinstance(current, dict) or part not in current:
            raise ContractError(f"JSON path does not exist: {'.'.join(path_parts)}")
        current = current[part]
    return current


def _match_csv_row(
    rows: Sequence[Mapping[str, str]],
    match: Mapping[str, Any],
    *,
    source: str,
) -> Mapping[str, str]:
    if not match:
        raise ContractError(f"CSV evidence selector for {source} requires match keys")
    matches = [
        row
        for row in rows
        if all(str(row.get(key, "")) == str(value) for key, value in match.items())
    ]
    if len(matches) != 1:
        raise ContractError(
            f"CSV selector for {source} must match exactly one row; matched={len(matches)} selector={dict(match)}"
        )
    return matches[0]


def _numeric(value: Any, *, label: str) -> float:
    if value is None or isinstance(value, bool):
        raise ContractError(f"{label} is not numeric: {value!r}")
    try:
        number = float(str(value).strip())
    except ValueError as exc:
        raise ContractError(f"{label} is not numeric: {value!r}") from exc
    if not math.isfinite(number):
        raise ContractError(f"{label} must be finite: {value!r}")
    return number


def _format_value(value: Any, format_name: str) -> str:
    if format_name not in SUPPORTED_FORMATS:
        raise ContractError(f"Unsupported evidence format: {format_name}")
    if format_name == "text":
        return str(value).strip()
    number = _numeric(value, label="evidence value")
    if format_name == "integer":
        return f"{int(round(number)):,}"
    if format_name == "decimal_1":
        return f"{number:.1f}"
    if format_name == "decimal_2":
        return f"{number:.2f}"
    if format_name == "percent_1":
        return f"{number * 100:.1f}%"
    if format_name == "percentage_point_1":
        sign = "+" if number > 0 else ""
        return f"{sign}{number * 100:.1f} pp"
    if format_name == "ratio_2":
        return f"{number:.2f}x"
    if format_name == "currency_0":
        return f"${number:,.0f}"
    raise ContractError(f"Unsupported evidence format: {format_name}")


def _resolve_evidence_ref(
    ref: Mapping[str, Any],
    *,
    package_dir: Path,
) -> ResolvedEvidence:
    ref_id = str(ref.get("ref_id") or "").strip()
    if not SAFE_ID_RE.fullmatch(ref_id):
        raise ContractError(f"Invalid evidence ref_id: {ref_id!r}")
    source = str(ref.get("source") or "").strip()
    if source not in ALLOWED_EVIDENCE_FILES:
        raise ContractError(f"Evidence source is not whitelisted: {source!r}")
    source_path = _contained_package_path(package_dir, source, label="evidence source")
    selector = ref.get("selector")
    if not isinstance(selector, dict):
        raise ContractError(f"Evidence ref {ref_id} requires a selector object")
    format_name = str(ref.get("format") or "text")
    source_row_sha256: str | None = None
    if source_path.suffix.lower() == ".csv":
        columns, rows = _read_csv(source_path)
        match = selector.get("match")
        field = str(selector.get("field") or "")
        if not isinstance(match, dict):
            raise ContractError(f"CSV evidence ref {ref_id} requires selector.match")
        if field not in columns:
            raise ContractError(f"CSV evidence field {field!r} is absent from {source}")
        row = _match_csv_row(rows, match, source=source)
        raw_value = row.get(field)
        source_row_sha256 = _source_row_sha256(row)
    else:
        raw_path = selector.get("json_path")
        if (
            not isinstance(raw_path, list)
            or not raw_path
            or not all(isinstance(item, str) and item for item in raw_path)
        ):
            raise ContractError(
                f"JSON evidence ref {ref_id} requires selector.json_path"
            )
        raw_value = _json_path_value(_load_json(source_path), raw_path)
    formatted = _format_value(raw_value, format_name)
    return ResolvedEvidence(
        ref_id=ref_id,
        source=source,
        raw_value=raw_value,
        formatted_value=formatted,
        source_sha256=_sha256_file(source_path),
        selector=dict(selector),
        source_row_sha256=source_row_sha256,
    )


def _contains_unbound_number(text: str) -> bool:
    without_tokens = TOKEN_RE.sub("", text)
    return bool(NUMERIC_LITERAL_RE.search(without_tokens))


def _validate_authored_text(text: Any, *, label: str, allow_empty: bool = True) -> str:
    if not isinstance(text, str):
        raise ContractError(f"{label} must be text")
    stripped = text.strip()
    if not stripped and not allow_empty:
        raise ContractError(f"{label} cannot be empty")
    if _contains_unbound_number(stripped):
        raise ContractError(
            f"{label} contains an unbound numeric literal; bind displayed numbers to evidence tokens"
        )
    return stripped


def _validate_report_model(
    model: Mapping[str, Any],
    *,
    catalog: Mapping[str, Any],
) -> tuple[dict[str, Mapping[str, Any]], list[Mapping[str, Any]]]:
    if model.get("schema_version") != MODEL_SCHEMA:
        raise ContractError(
            f"Unsupported report model schema: {model.get('schema_version')!r}"
        )
    if model.get("report_id") != catalog.get("report_id"):
        raise ContractError("report_model report_id does not match evidence_catalog")
    if model.get("authoring_status") != "codex_complete":
        raise ContractError(
            "report_model authoring_status must be codex_complete before rendering"
        )
    author = model.get("author")
    if not isinstance(author, dict) or author.get("execution") != "codex_agent":
        raise ContractError("report_model author must be a Codex agent")
    if not str(author.get("agent_id") or "").strip():
        raise ContractError("report_model author.agent_id is required")
    _validate_authored_text(model.get("title"), label="report title", allow_empty=False)
    _validate_authored_text(model.get("subtitle", ""), label="report subtitle")

    claims = model.get("claims")
    if not isinstance(claims, list) or not claims:
        raise ContractError("report_model requires at least one claim")
    claim_by_id: dict[str, Mapping[str, Any]] = {}
    for claim in claims:
        if not isinstance(claim, dict):
            raise ContractError("Each report claim must be an object")
        claim_id = str(claim.get("claim_id") or "")
        if not SAFE_ID_RE.fullmatch(claim_id) or claim_id in claim_by_id:
            raise ContractError(f"Invalid or duplicate claim_id: {claim_id!r}")
        kind = str(claim.get("kind") or "")
        if kind not in {"deterministic", "semantic"}:
            raise ContractError(f"Claim {claim_id} has unsupported kind: {kind!r}")
        _validate_authored_text(
            claim.get("headline"), label=f"claim {claim_id} headline", allow_empty=False
        )
        _validate_authored_text(
            claim.get("text_template"),
            label=f"claim {claim_id} text_template",
            allow_empty=False,
        )
        _validate_authored_text(
            claim.get("interpretation", ""), label=f"claim {claim_id} interpretation"
        )
        _validate_authored_text(
            claim.get("caveat", ""), label=f"claim {claim_id} caveat"
        )
        if claim.get("confidence") not in {"high", "medium", "low"}:
            raise ContractError(
                f"Claim {claim_id} requires high, medium, or low confidence"
            )
        evidence_refs = claim.get("evidence_refs") or []
        supporting = claim.get("supporting_claim_ids") or []
        if not isinstance(evidence_refs, list) or not isinstance(supporting, list):
            raise ContractError(
                f"Claim {claim_id} evidence/support fields must be lists"
            )
        if kind == "deterministic" and not evidence_refs:
            raise ContractError(
                f"Deterministic claim {claim_id} requires evidence_refs"
            )
        if kind == "semantic" and not supporting:
            raise ContractError(
                f"Semantic claim {claim_id} requires supporting_claim_ids"
            )
        if kind == "semantic" and evidence_refs:
            raise ContractError(
                f"Semantic claim {claim_id} cannot introduce fresh evidence refs"
            )
        claim_by_id[claim_id] = claim

    for claim_id, claim in claim_by_id.items():
        for supporting_id in claim.get("supporting_claim_ids") or []:
            if supporting_id not in claim_by_id or supporting_id == claim_id:
                raise ContractError(
                    f"Claim {claim_id} has invalid supporting claim {supporting_id!r}"
                )
            if claim_by_id[supporting_id].get("kind") != "deterministic":
                raise ContractError(
                    f"Semantic claim {claim_id} must be supported by deterministic claims"
                )

    sections = model.get("sections")
    if not isinstance(sections, list):
        raise ContractError("report_model sections must be a list")
    section_ids = [
        str(item.get("section_id") or "") for item in sections if isinstance(item, dict)
    ]
    if tuple(section_ids) != REQUIRED_SECTION_IDS:
        raise ContractError(
            "report_model sections must appear exactly once in the required order: "
            + ", ".join(REQUIRED_SECTION_IDS)
        )
    used_claim_ids: list[str] = []
    for section in sections:
        section_id = str(section["section_id"])
        _validate_authored_text(
            section.get("title"),
            label=f"section {section_id} title",
            allow_empty=False,
        )
        section_summary = _validate_authored_text(
            section.get("summary", ""),
            label=f"section {section_id} summary",
        )
        raw_claim_ids = section.get("claim_ids") or []
        raw_table_keys = section.get("table_keys") or []
        if not isinstance(raw_claim_ids, list) or not isinstance(raw_table_keys, list):
            raise ContractError(
                f"Section {section_id} claim_ids/table_keys must be lists"
            )
        for claim_id in raw_claim_ids:
            if claim_id not in claim_by_id:
                raise ContractError(
                    f"Section {section_id} references unknown claim {claim_id!r}"
                )
            used_claim_ids.append(claim_id)
        invalid_tables = sorted(set(raw_table_keys) - ALLOWED_TABLE_KEYS)
        if invalid_tables:
            raise ContractError(
                f"Section {section_id} references unsupported tables: {invalid_tables}"
            )
        if not section_summary and not raw_claim_ids and not raw_table_keys:
            raise ContractError(f"Section {section_id} cannot be empty")
    if sorted(used_claim_ids) != sorted(claim_by_id) or len(used_claim_ids) != len(
        set(used_claim_ids)
    ):
        raise ContractError(
            "Every report claim must be referenced by exactly one section"
        )

    expected_warnings = {
        str(item.get("code"))
        for item in catalog.get("warnings") or []
        if isinstance(item, dict)
    }
    acknowledged = set(model.get("acknowledged_warning_codes") or [])
    if acknowledged != expected_warnings:
        raise ContractError(
            "report_model must acknowledge every active package warning and no others"
        )
    limitations = model.get("limitations")
    if not isinstance(limitations, list):
        raise ContractError("report_model limitations must be a list")
    limitation_codes = {
        str(item.get("code")) for item in limitations if isinstance(item, dict)
    }
    if not expected_warnings <= limitation_codes:
        raise ContractError(
            "Every active package warning must be visible in limitations"
        )
    for item in limitations:
        if not isinstance(item, dict):
            raise ContractError("Each limitation must be an object")
        _validate_authored_text(
            item.get("text"),
            label=f"limitation {item.get('code')} text",
            allow_empty=False,
        )

    products = model.get("featured_products")
    if not isinstance(products, list) or len(products) > 8:
        raise ContractError("featured_products must be a list with at most eight items")
    for item in products:
        if not isinstance(item, dict):
            raise ContractError("Each featured product must be an object")
        if not str(item.get("product_id") or "").strip():
            raise ContractError("Featured product requires product_id")
        if item.get("role") not in {"winning_now", "emerging_signal"}:
            raise ContractError(
                "Featured product role must be winning_now or emerging_signal"
            )
        _validate_authored_text(
            item.get("rationale"), label="featured product rationale", allow_empty=False
        )
        supporting = item.get("supporting_claim_ids") or []
        if not supporting or any(
            claim_id not in claim_by_id for claim_id in supporting
        ):
            raise ContractError("Featured product requires valid supporting_claim_ids")
    return claim_by_id, sections


def _selected_csv_row(
    ref: Mapping[str, Any],
    *,
    package_dir: Path,
) -> Mapping[str, str] | None:
    source = str(ref.get("source") or "")
    if not source.endswith(".csv"):
        return None
    selector = ref.get("selector")
    if not isinstance(selector, dict) or not isinstance(selector.get("match"), dict):
        return None
    source_path = _contained_package_path(
        package_dir, source, label="claim checker source"
    )
    _columns, rows = _read_csv(source_path)
    return _match_csv_row(rows, selector["match"], source=source)


def _claim_checker(
    claim: Mapping[str, Any],
    *,
    package_dir: Path,
) -> list[dict[str, Any]]:
    claim_id = str(claim["claim_id"])
    checker = str(claim.get("checker") or "")
    allowed = {
        "cohort_summary",
        "bundle_signal_winning_now",
        "bundle_signal_emerging",
        "bundle_bridge",
        "brand_fact",
        "review_availability",
        "source_fact",
    }
    if checker not in allowed:
        raise ContractError(
            f"Deterministic claim {claim_id} has unsupported checker {checker!r}"
        )
    refs = claim.get("evidence_refs") or []
    rows = [
        (
            str(ref.get("source") or ""),
            _selected_csv_row(ref, package_dir=package_dir),
            ref,
        )
        for ref in refs
        if isinstance(ref, dict)
    ]
    checks: list[dict[str, Any]] = [
        {"check_id": "checker_registered", "status": "pass", "checker": checker}
    ]

    def require_bundle_row(
        sources: set[str],
        *,
        focus_count: str,
        focus_brands: str,
        focus_share: str,
        baseline_share: str,
    ) -> tuple[str, Mapping[str, str]]:
        selected = [
            (source, row, ref)
            for source, row, ref in rows
            if source in sources and row is not None
        ]
        if not selected:
            raise ContractError(
                f"Claim {claim_id} checker {checker} requires evidence from {sorted(sources)}"
            )
        row_identities = {
            (source, _source_row_sha256(row)) for source, row, _ref in selected
        }
        if len(row_identities) != 1:
            raise ContractError(
                f"Claim {claim_id} must bind every layer-specific value to one exact bundle row"
            )
        source, row, _ref = selected[0]
        referenced_fields = {
            str(ref.get("selector", {}).get("field") or "")
            for _source, _row, ref in selected
            if isinstance(ref.get("selector"), dict)
        }
        missing_share_fields = {focus_share, baseline_share} - referenced_fields
        if missing_share_fields:
            raise ContractError(
                f"Claim {claim_id} must display both focus and baseline shares; missing={sorted(missing_share_fields)}"
            )
        bundle_key = str(row.get("bundle_key") or "").strip()
        if not bundle_key:
            raise ContractError(f"Claim {claim_id} requires a non-empty bundle_key")
        count = _numeric(row.get(focus_count), label=f"{claim_id}.{focus_count}")
        brands = _numeric(row.get(focus_brands), label=f"{claim_id}.{focus_brands}")
        focus = _numeric(row.get(focus_share), label=f"{claim_id}.{focus_share}")
        baseline = _numeric(
            row.get(baseline_share), label=f"{claim_id}.{baseline_share}"
        )
        if count < 3 or brands < 2 or focus <= baseline:
            raise ContractError(
                f"Claim {claim_id} does not satisfy the preserved bundle signal thresholds"
            )
        checks.extend(
            [
                {
                    "check_id": "one_exact_bundle_row",
                    "status": "pass",
                    "source": source,
                    "source_row_sha256": _source_row_sha256(row),
                    "bundle_key": bundle_key,
                },
                {
                    "check_id": "focus_product_count_at_least_three",
                    "status": "pass",
                    "actual": count,
                },
                {
                    "check_id": "focus_brand_count_at_least_two",
                    "status": "pass",
                    "actual": brands,
                },
                {
                    "check_id": "focus_share_above_baseline",
                    "status": "pass",
                    "actual": focus,
                    "baseline": baseline,
                },
            ]
        )
        return source, row

    if checker == "bundle_signal_winning_now":
        allowed_sources = {"top_seller_pairs.csv", "top_seller_triples.csv"}
        invalid_sources = sorted(
            {source for source, _row, _ref in rows} - allowed_sources
        )
        if invalid_sources:
            raise ContractError(
                f"Claim {claim_id} has evidence outside its winning layer: {invalid_sources}"
            )
        require_bundle_row(
            allowed_sources,
            focus_count="count_top_seller",
            focus_brands="top_seller_brand_count",
            focus_share="pct_top_seller",
            baseline_share="pct_other",
        )
    elif checker == "bundle_signal_emerging":
        allowed_sources = {"innovation_pairs.csv", "innovation_triples.csv"}
        invalid_sources = sorted(
            {source for source, _row, _ref in rows} - allowed_sources
        )
        if invalid_sources:
            raise ContractError(
                f"Claim {claim_id} has evidence outside its emerging layer: {invalid_sources}"
            )
        require_bundle_row(
            allowed_sources,
            focus_count="count_recent",
            focus_brands="recent_brand_count",
            focus_share="pct_recent",
            baseline_share="pct_rest",
        )
    elif checker == "bundle_bridge":
        winner_sources = {"top_seller_pairs.csv", "top_seller_triples.csv"}
        emerging_sources = {"innovation_pairs.csv", "innovation_triples.csv"}
        invalid_sources = sorted(
            {source for source, _row, _ref in rows} - winner_sources - emerging_sources
        )
        if invalid_sources:
            raise ContractError(
                f"Bridge claim {claim_id} has evidence outside its two layers: {invalid_sources}"
            )
        winner_source, winner = require_bundle_row(
            winner_sources,
            focus_count="count_top_seller",
            focus_brands="top_seller_brand_count",
            focus_share="pct_top_seller",
            baseline_share="pct_other",
        )
        emerging_source, emerging = require_bundle_row(
            emerging_sources,
            focus_count="count_recent",
            focus_brands="recent_brand_count",
            focus_share="pct_recent",
            baseline_share="pct_rest",
        )
        winner_key = str(winner.get("bundle_key") or "").strip()
        emerging_key = str(emerging.get("bundle_key") or "").strip()
        if winner_key != emerging_key:
            raise ContractError(f"Bridge claim {claim_id} must use the same bundle_key")
        if winner_source.removeprefix("top_seller_") != emerging_source.removeprefix(
            "innovation_"
        ):
            raise ContractError(
                f"Bridge claim {claim_id} must compare matching pair or triple layers"
            )
        checks.append(
            {
                "check_id": "same_bundle_key_across_layers",
                "status": "pass",
                "bundle_key": winner_key,
            }
        )
    elif checker == "brand_fact":
        if not any(
            source == "top_seller_brand_comparison.csv" for source, _row, _ref in rows
        ):
            raise ContractError(
                f"Brand claim {claim_id} requires brand comparison evidence"
            )
    elif checker == "cohort_summary":
        if not any(str(ref.get("source")) == "summary.json" for ref in refs):
            raise ContractError(
                f"Cohort claim {claim_id} requires summary.json evidence"
            )
    elif checker == "review_availability":
        review_files = (
            "top_seller_review_validation.csv",
            "bundle_review_validation.csv",
        )
        row_counts = []
        for file_name in review_files:
            raw_path = package_dir / file_name
            if raw_path.exists():
                path = _contained_package_path(
                    package_dir, file_name, label="review evidence source"
                )
                _columns, review_rows = _read_csv(path)
                row_counts.append(len(review_rows))
            else:
                row_counts.append(0)
        checks.append(
            {
                "check_id": "review_evidence_row_counts",
                "status": "pass",
                "top_seller_rows": row_counts[0],
                "emerging_rows": row_counts[1],
            }
        )
    return checks


def _resolve_claims(
    claim_by_id: Mapping[str, Mapping[str, Any]],
    *,
    package_dir: Path,
) -> tuple[dict[str, str], list[dict[str, Any]]]:
    resolved_text: dict[str, str] = {}
    ledger: list[dict[str, Any]] = []
    for claim_id, claim in claim_by_id.items():
        template = str(claim["text_template"])
        kind = str(claim["kind"])
        raw_refs = claim.get("evidence_refs") or []
        resolved_refs: list[ResolvedEvidence] = []
        ref_ids: set[str] = set()
        for raw_ref in raw_refs:
            if not isinstance(raw_ref, dict):
                raise ContractError(f"Claim {claim_id} evidence refs must be objects")
            resolved = _resolve_evidence_ref(raw_ref, package_dir=package_dir)
            if resolved.ref_id in ref_ids:
                raise ContractError(
                    f"Claim {claim_id} has duplicate evidence ref {resolved.ref_id}"
                )
            ref_ids.add(resolved.ref_id)
            resolved_refs.append(resolved)
        token_ids = set(TOKEN_RE.findall(template))
        if token_ids != ref_ids:
            raise ContractError(
                f"Claim {claim_id} tokens must exactly match evidence ref_ids; tokens={sorted(token_ids)} refs={sorted(ref_ids)}"
            )
        text = template
        for item in resolved_refs:
            text = text.replace("{{" + item.ref_id + "}}", item.formatted_value)
        if TOKEN_RE.search(text):
            raise ContractError(f"Claim {claim_id} has unresolved evidence tokens")
        checks = (
            _claim_checker(claim, package_dir=package_dir)
            if kind == "deterministic"
            else [
                {
                    "check_id": "semantic_claim_has_deterministic_support",
                    "status": "pass",
                    "supporting_claim_ids": list(
                        claim.get("supporting_claim_ids") or []
                    ),
                }
            ]
        )
        resolved_text[claim_id] = text
        ledger.append(
            {
                "claim_id": claim_id,
                "kind": kind,
                "checker": claim.get("checker"),
                "resolved_text": text,
                "supporting_claim_ids": list(claim.get("supporting_claim_ids") or []),
                "evidence": [
                    {
                        "ref_id": item.ref_id,
                        "source": item.source,
                        "selector": item.selector,
                        "raw_value": item.raw_value,
                        "formatted_value": item.formatted_value,
                        "source_sha256": item.source_sha256,
                        "source_row_sha256": item.source_row_sha256,
                    }
                    for item in resolved_refs
                ],
                "checks": checks,
                "status": "pass",
            }
        )
    return resolved_text, ledger


def _table_manifest_by_key(catalog: Mapping[str, Any]) -> dict[str, Mapping[str, Any]]:
    output: dict[str, Mapping[str, Any]] = {}
    for item in catalog.get("attribute_tables") or []:
        if not isinstance(item, dict):
            continue
        table_key = str(item.get("table_key") or "")
        if table_key:
            output[table_key] = item
    missing = sorted(ALLOWED_TABLE_KEYS - set(output))
    if missing:
        raise ContractError(
            f"Evidence catalog is missing deterministic tables: {missing}"
        )
    return output


def _render_table(
    table: Mapping[str, Any],
    *,
    output_dir: Path,
) -> tuple[str, dict[str, Any]]:
    relative = _safe_relative_path(str(table["csv"]), label="table CSV")
    path = output_dir / "evidence" / relative
    expected_sha = str(table.get("csv_sha256") or "")
    actual_sha = _sha256_file(path)
    if expected_sha != actual_sha:
        raise ContractError(
            f"Deterministic table changed after preparation: {table['table_key']}"
        )
    columns, rows = _read_csv(path)
    if int(table.get("row_count") or 0) != len(rows):
        raise ContractError(
            f"Deterministic table row count changed: {table['table_key']}"
        )
    header = "".join(
        f'<th scope="col">{html.escape(column)}</th>' for column in columns
    )
    body_rows = []
    for row in rows:
        cells = "".join(
            f"<td>{html.escape(str(row.get(column) or ''))}</td>" for column in columns
        )
        body_rows.append(f"<tr>{cells}</tr>")
    table_html = (
        f"<figure class=\"evidence-table\" data-table-key=\"{html.escape(str(table['table_key']))}\" "
        f'data-table-sha256="{actual_sha}">'
        f"<figcaption><span>{html.escape(str(table.get('title') or table['table_key']))}</span>"
        f"<small>{len(rows)} evidence rows</small></figcaption>"
        '<div class="table-scroll"><table><thead><tr>'
        + header
        + "</tr></thead><tbody>"
        + "".join(body_rows)
        + "</tbody></table></div>"
        f"<p class=\"source-note\">Source: {html.escape(', '.join(table.get('source_files') or []))}</p>"
        "</figure>"
    )
    record = {
        "table_key": table["table_key"],
        "csv": str(relative),
        "sha256": actual_sha,
        "row_count": len(rows),
        "columns": columns,
    }
    return table_html, record


def _safe_http_url(value: Any) -> str:
    text = str(value or "").strip()
    parts = urlsplit(text)
    return text if parts.scheme in {"http", "https"} and parts.netloc else ""


def _product_index(package_dir: Path) -> dict[str, dict[str, str]]:
    products: dict[str, dict[str, str]] = {}
    for file_name in ("recent_products.csv", "top_seller_products.csv"):
        raw_path = package_dir / file_name
        if not raw_path.exists():
            continue
        path = _contained_package_path(
            package_dir, file_name, label="product evidence source"
        )
        _columns, rows = _read_csv(path)
        for row in rows:
            product_id = str(row.get("parent_product_id") or "").strip()
            if product_id and product_id not in products:
                products[product_id] = dict(row)
    return products


def _local_product_image(package_dir: Path, row: Mapping[str, str]) -> Path | None:
    package_root = package_dir.resolve()
    image_root = (package_root / "images").resolve()
    if not image_root.is_relative_to(package_root):
        raise ContractError("Evidence-package image directory escapes the package")
    relative_value = str(row.get("pack_image_file") or "").strip()
    if relative_value:
        relative = _safe_relative_path(relative_value, label="pack image")
        candidate = (package_dir / relative).resolve()
        if candidate.is_file():
            if not candidate.is_relative_to(image_root):
                raise ContractError(
                    f"Pack image escapes the package image directory: {candidate}"
                )
            if not _is_supported_local_image(candidate):
                raise ContractError(
                    f"Pack image is not a supported raster image: {candidate}"
                )
            return candidate
    for field in ("pack_image_path",):
        value = str(row.get(field) or "").strip()
        if value:
            candidate = Path(value).expanduser()
            if candidate.is_file():
                resolved = candidate.resolve()
                if not resolved.is_relative_to(image_root):
                    raise ContractError(
                        f"Pack image escapes the package image directory: {resolved}"
                    )
                if not _is_supported_local_image(resolved):
                    raise ContractError(
                        f"Local product image is not a supported raster image: {resolved}"
                    )
                return resolved
    sidecar = _local_sidecar_image(package_dir, row)
    return sidecar[0] if sidecar is not None else None


def _copy_featured_products(
    featured: Sequence[Mapping[str, Any]],
    *,
    package_dir: Path,
    output_dir: Path,
) -> tuple[str, list[dict[str, Any]]]:
    products = _product_index(package_dir)
    assets_dir = output_dir / "assets" / "products"
    cards: list[str] = []
    records: list[dict[str, Any]] = []
    for item in featured:
        product_id = str(item["product_id"])
        if product_id not in products:
            raise ContractError(
                f"Featured product is absent from cohort files: {product_id}"
            )
        row = products[product_id]
        image_source = _local_product_image(package_dir, row)
        image_relative = ""
        image_sha = ""
        if image_source is not None:
            assets_dir.mkdir(parents=True, exist_ok=True)
            suffix = image_source.suffix.lower() or ".img"
            safe_id = re.sub(r"[^A-Za-z0-9_-]+", "-", product_id).strip("-")
            target = assets_dir / f"{safe_id}{suffix}"
            shutil.copy2(image_source, target)
            image_relative = target.relative_to(output_dir).as_posix()
            image_sha = _sha256_file(target)
            image_markup = (
                f'<img src="{html.escape(image_relative)}" '
                f"alt=\"{html.escape(str(row.get('product_name') or product_id))}\">"
            )
        else:
            image_markup = '<div class="image-placeholder" aria-label="Image unavailable">No local image</div>'
        product_url = _safe_http_url(row.get("pdp_url"))
        name = str(row.get("product_name") or product_id)
        linked_name = (
            f'<a href="{html.escape(product_url)}" target="_blank" rel="noreferrer">{html.escape(name)}</a>'
            if product_url
            else html.escape(name)
        )
        cards.append(
            f'<article class="product-card" data-product-id="{html.escape(product_id)}">'
            f'<div class="product-image">{image_markup}</div>'
            f"<div class=\"product-copy\"><p class=\"product-role\">{html.escape(str(item['role']).replace('_', ' '))}</p>"
            f"<h3>{linked_name}</h3><p class=\"brand\">{html.escape(str(row.get('brand') or ''))}</p>"
            f"<p>{html.escape(str(item['rationale']))}</p></div></article>"
        )
        records.append(
            {
                "product_id": product_id,
                "source_row_sha256": _source_row_sha256(row),
                "image_source": str(image_source) if image_source else None,
                "image_path": image_relative or None,
                "image_sha256": image_sha or None,
                "pdp_url": product_url or None,
            }
        )
    if not cards:
        return "", records
    return f'<div class="product-grid">{"".join(cards)}</div>', records


def _claim_html(claim: Mapping[str, Any], resolved_text: str) -> str:
    claim_id = str(claim["claim_id"])
    interpretation = str(claim.get("interpretation") or "").strip()
    caveat = str(claim.get("caveat") or "").strip()
    supporting = " ".join(str(item) for item in claim.get("supporting_claim_ids") or [])
    extras = ""
    if interpretation:
        extras += f'<p class="interpretation">{html.escape(interpretation)}</p>'
    if caveat:
        extras += f'<p class="claim-caveat">{html.escape(caveat)}</p>'
    return (
        f'<article class="claim" data-claim-id="{html.escape(claim_id)}" '
        f"data-claim-kind=\"{html.escape(str(claim['kind']))}\" "
        f'data-supporting-claims="{html.escape(supporting)}">'
        f"<div class=\"claim-meta\"><span>{html.escape(str(claim['kind']))}</span>"
        f"<span>{html.escape(str(claim['confidence']))} confidence</span></div>"
        f"<h3>{html.escape(str(claim['headline']))}</h3>"
        f'<p class="claim-statement">{html.escape(resolved_text)}</p>{extras}</article>'
    )


def _report_css() -> str:
    return """
:root{--ink:#172019;--muted:#667069;--paper:#f7f4ec;--card:#fffefa;--line:#d9d5c9;--green:#516254;--sage:#a8b7a6;--amber:#c88d42;--red:#a44738;--shadow:0 18px 48px rgba(28,35,29,.09)}
*{box-sizing:border-box}html{scroll-behavior:smooth}body{margin:0;background:var(--paper);color:var(--ink);font-family:Inter,ui-sans-serif,system-ui,-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif;line-height:1.55}
a{color:inherit}.report-shell{max-width:1240px;margin:0 auto;padding:28px}.hero{position:relative;overflow:hidden;border-radius:30px;background:var(--ink);color:white;padding:64px;box-shadow:var(--shadow)}.hero:after{content:"";position:absolute;width:380px;height:380px;border-radius:50%;right:-120px;top:-150px;background:radial-gradient(circle,var(--sage),transparent 66%);opacity:.45}.eyebrow,.product-role{font-size:.72rem;text-transform:uppercase;letter-spacing:.16em;font-weight:750}.hero h1{max-width:780px;margin:.4rem 0 .3rem;font-family:Georgia,serif;font-size:clamp(2.5rem,6vw,5.7rem);line-height:.96;font-weight:500}.hero .subtitle{max-width:680px;color:#d9dfda;font-size:1.12rem}.hero-meta{display:flex;gap:12px;flex-wrap:wrap;margin-top:30px}.hero-meta span{border:1px solid rgba(255,255,255,.24);border-radius:99px;padding:8px 13px;font-size:.82rem}.verdict-slot{margin:20px 0}.verdict{display:grid;grid-template-columns:auto minmax(0,1fr);gap:18px;align-items:center;min-width:0;border:1px solid var(--line);border-radius:18px;background:var(--card);padding:18px 22px}.verdict>div,.verdict span,.verdict-details{min-width:0;overflow-wrap:anywhere}.verdict strong{display:block;font-size:1.15rem}.verdict .mark{width:48px;height:48px;border-radius:50%;display:grid;place-items:center;background:var(--green);color:white;font-weight:800}.verdict-details{margin:.55rem 0 0;padding-left:1.1rem;color:var(--muted);font-size:.84rem}.verdict.correct_with_caveats .mark{background:var(--amber)}.verdict.incorrect .mark{background:var(--red)}.verdict.unable_to_determine .mark{background:#737a75}
.report-nav{position:sticky;top:10px;z-index:4;display:flex;gap:8px;overflow:auto;margin:20px 0;padding:10px;border:1px solid var(--line);border-radius:16px;background:rgba(247,244,236,.92);backdrop-filter:blur(12px)}.report-nav a{white-space:nowrap;text-decoration:none;padding:7px 11px;border-radius:10px;font-size:.78rem}.report-nav a:hover{background:#e5e8df}
.report-section{display:grid;grid-template-columns:minmax(210px,300px) 1fr;gap:34px;padding:54px 0;border-top:1px solid var(--line)}.section-heading{position:sticky;top:90px;align-self:start}.section-number{color:var(--amber);font-family:Georgia,serif;font-size:1.5rem}.section-heading h2{font-family:Georgia,serif;font-weight:500;font-size:clamp(1.8rem,3vw,3rem);line-height:1.05;margin:.25rem 0}.section-summary{color:var(--muted)}.section-body{min-width:0}.claim-grid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:16px}.claim{background:var(--card);border:1px solid var(--line);border-radius:18px;padding:24px;box-shadow:0 8px 25px rgba(28,35,29,.04)}.claim-meta{display:flex;justify-content:space-between;gap:10px;color:var(--muted);font-size:.7rem;text-transform:uppercase;letter-spacing:.08em}.claim h3{font-family:Georgia,serif;font-size:1.45rem;font-weight:500;margin:1rem 0 .6rem}.claim-statement{font-size:1.06rem}.interpretation{border-left:3px solid var(--sage);padding-left:13px}.claim-caveat{color:#755027;background:#faf0dd;border-radius:10px;padding:10px 12px;font-size:.9rem}
.evidence-table{margin:20px 0 0;background:var(--card);border:1px solid var(--line);border-radius:18px;overflow:hidden}.evidence-table figcaption{display:flex;justify-content:space-between;gap:20px;padding:18px 20px;border-bottom:1px solid var(--line);font-family:Georgia,serif;font-size:1.25rem}.evidence-table figcaption small{font-family:inherit;color:var(--muted);font-size:.76rem}.table-scroll{overflow:auto}table{border-collapse:collapse;width:100%;font-size:.78rem}th,td{padding:11px 13px;text-align:left;border-bottom:1px solid #ece8de;vertical-align:top}th{position:sticky;top:0;background:#eeece4;text-transform:uppercase;letter-spacing:.05em;font-size:.66rem}tbody tr:hover{background:#f5f4ef}.source-note{padding:0 18px 12px;color:var(--muted);font-size:.72rem}
.product-grid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:16px;margin-top:20px}.product-card{display:grid;grid-template-columns:42% 1fr;overflow:hidden;background:var(--card);border:1px solid var(--line);border-radius:18px}.product-image{min-height:230px;background:#e9e7df}.product-image img{width:100%;height:100%;object-fit:cover;display:block}.image-placeholder{height:100%;min-height:230px;display:grid;place-items:center;color:var(--muted)}.product-copy{padding:20px}.product-copy h3{font-family:Georgia,serif;font-weight:500;margin:.3rem 0}.brand{color:var(--muted)}.product-role{color:var(--amber)}
.limitations{display:grid;gap:10px}.limitation{border-left:4px solid var(--amber);background:#f5ead6;padding:15px 18px;border-radius:0 12px 12px 0}.limitation code{font-size:.72rem}.footer{display:flex;justify-content:space-between;gap:20px;padding:32px 0 12px;color:var(--muted);font-size:.75rem}.print-button{border:1px solid var(--line);background:var(--card);border-radius:99px;padding:8px 14px;cursor:pointer}
@media(max-width:850px){.report-shell{padding:14px}.hero{padding:38px 25px;border-radius:20px}.report-section{grid-template-columns:1fr;gap:18px;padding:38px 0}.section-heading{position:static}.claim-grid,.product-grid{grid-template-columns:1fr}.product-card{grid-template-columns:38% 1fr}.footer{flex-direction:column}}
@media(max-width:520px){.claim-grid{display:block}.claim{margin-bottom:12px}.product-card{grid-template-columns:1fr}.product-image{max-height:360px}.evidence-table figcaption{display:block}.evidence-table figcaption small{display:block;margin-top:5px}.hero h1{font-size:2.6rem}}
@media print{body{background:white}.report-shell{max-width:none;padding:0}.hero{box-shadow:none;border-radius:0}.report-nav,.print-button{display:none}.report-section{break-inside:avoid}.claim,.evidence-table,.product-card{break-inside:avoid;box-shadow:none}}
"""


def _render_draft_html(
    model: Mapping[str, Any],
    sections: Sequence[Mapping[str, Any]],
    claim_by_id: Mapping[str, Mapping[str, Any]],
    resolved_text: Mapping[str, str],
    *,
    catalog: Mapping[str, Any],
    table_html_by_key: Mapping[str, str],
    product_html: str,
) -> str:
    package = catalog["package"]
    nav = "".join(
        f"<a href=\"#{html.escape(str(section['section_id']))}\">{html.escape(str(section['title']))}</a>"
        for section in sections
    )
    section_markup: list[str] = []
    for index, section in enumerate(sections, start=1):
        section_id = str(section["section_id"])
        claims = "".join(
            _claim_html(claim_by_id[claim_id], resolved_text[claim_id])
            for claim_id in section.get("claim_ids") or []
        )
        claim_grid = f'<div class="claim-grid">{claims}</div>' if claims else ""
        tables = "".join(
            table_html_by_key[table_key]
            for table_key in section.get("table_keys") or []
        )
        products = product_html if section_id == "product_evidence" else ""
        limitations = ""
        if section_id == "method_and_caveats":
            limitations = (
                '<div class="limitations">'
                + "".join(
                    f"<div class=\"limitation\" data-warning-code=\"{html.escape(str(item['code']))}\">"
                    f"<code>{html.escape(str(item['code']))}</code><p>{html.escape(str(item['text']))}</p></div>"
                    for item in model.get("limitations") or []
                )
                + "</div>"
            )
        section_markup.append(
            f'<section class="report-section" id="{html.escape(section_id)}" data-section-id="{html.escape(section_id)}">'
            f'<header class="section-heading"><span class="section-number">{index:02d}</span>'
            f"<h2>{html.escape(str(section['title']))}</h2>"
            f"<p class=\"section-summary\">{html.escape(str(section.get('summary') or ''))}</p></header>"
            f'<div class="section-body">{claim_grid}{tables}{products}{limitations}</div></section>'
        )
    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<meta name="color-scheme" content="light"><title>{html.escape(str(model['title']))}</title><style>{_report_css()}</style></head>
<body data-report-id="{html.escape(str(model['report_id']))}" data-package-sha256="{html.escape(str(package['sha256']))}">
<main class="report-shell"><header class="hero"><p class="eyebrow">Attribute intelligence · private local report</p>
<h1>{html.escape(str(model['title']))}</h1><p class="subtitle">{html.escape(str(model['subtitle']))}</p>
<div class="hero-meta"><span>{html.escape(str(package.get('retailer_label') or package.get('retailer') or ''))}</span>
<span>{html.escape(str(package.get('category_label') or package.get('category_key') or ''))}</span>
<span>Snapshot {html.escape(str(package.get('discovery_crawl_ts') or 'unknown'))}</span></div></header>
<div class="verdict-slot">{VERDICT_PLACEHOLDER_HTML}</div><nav class="report-nav" aria-label="Report sections">{nav}</nav>
{''.join(section_markup)}
<footer class="footer"><span>Generated and checked locally. This report is not stored on the server.</span>
<button class="print-button" type="button" onclick="window.print()">Print report</button></footer></main></body></html>
"""


def render_report(output_dir: Path) -> dict[str, Any]:
    """Resolve evidence tokens and render a private local HTML draft."""

    output = _assert_safe_output_dir(output_dir)
    catalog = _load_json(output / "evidence_catalog.json")
    model = _load_json(output / "report_model.json")
    if catalog.get("schema_version") != CATALOG_SCHEMA:
        raise ContractError("Unsupported evidence catalog schema")
    package_dir = Path(str(catalog["package"]["path"])).resolve()
    claim_by_id, sections = _validate_report_model(model, catalog=catalog)
    resolved_text, claim_ledger = _resolve_claims(claim_by_id, package_dir=package_dir)
    table_manifest = _table_manifest_by_key(catalog)
    used_table_keys = {
        table_key
        for section in sections
        for table_key in section.get("table_keys") or []
    }
    table_html_by_key: dict[str, str] = {}
    rendered_tables: list[dict[str, Any]] = []
    for table_key in sorted(used_table_keys):
        table_html, record = _render_table(table_manifest[table_key], output_dir=output)
        table_html_by_key[table_key] = table_html
        rendered_tables.append(record)
    product_html, product_records = _copy_featured_products(
        model.get("featured_products") or [],
        package_dir=package_dir,
        output_dir=output,
    )
    draft = _render_draft_html(
        model,
        sections,
        claim_by_id,
        resolved_text,
        catalog=catalog,
        table_html_by_key=table_html_by_key,
        product_html=product_html,
    )
    draft_path = output / "report_draft.html"
    draft_path.write_text(draft, encoding="utf-8")
    model_sha = _canonical_json_sha256(model)
    catalog_sha = _canonical_json_sha256(catalog)
    ledger_payload = {
        "schema_version": "attribute_reporting.claim_ledger.v1",
        "report_id": model["report_id"],
        "report_model_sha256": model_sha,
        "claims": claim_ledger,
        "summary": {
            "claim_count": len(claim_ledger),
            "deterministic_count": sum(
                item["kind"] == "deterministic" for item in claim_ledger
            ),
            "semantic_count": sum(item["kind"] == "semantic" for item in claim_ledger),
            "failed_count": 0,
        },
    }
    _write_json(output / "claim_ledger.json", ledger_payload)
    render_manifest = {
        "schema_version": RENDER_SCHEMA,
        "rendered_at": _utc_now(),
        "report_id": model["report_id"],
        "package_sha256": catalog["package"]["sha256"],
        "evidence_catalog_sha256": catalog_sha,
        "report_model_sha256": model_sha,
        "claim_ledger_sha256": _canonical_json_sha256(ledger_payload),
        "draft_html": "report_draft.html",
        "draft_html_sha256": _sha256_file(draft_path),
        "rendered_tables": rendered_tables,
        "featured_products": product_records,
        "external_assets": [],
        "status": "ready_for_independent_semantic_review",
    }
    _write_json(output / "render_manifest.json", render_manifest)
    review_path = output / "semantic_review.json"
    review = _load_json(review_path)
    if (
        review.get("schema_version") == REVIEW_SCHEMA
        and review.get("overall_verdict") == "unable_to_determine"
    ):
        review["targets"] = {
            "report_id": model["report_id"],
            "evidence_catalog_sha256": catalog_sha,
            "report_model_sha256": model_sha,
            "draft_html_sha256": render_manifest["draft_html_sha256"],
        }
        _write_json(review_path, review)
    return render_manifest


def _mechanical_findings(
    *,
    output_dir: Path,
    catalog: Mapping[str, Any],
    model: Mapping[str, Any],
    render_manifest: Mapping[str, Any],
    claim_ledger: Mapping[str, Any],
    draft: str,
) -> list[dict[str, str]]:
    findings: list[dict[str, str]] = []

    def fail(code: str, message: str) -> None:
        findings.append({"code": code, "message": message})

    if _canonical_json_sha256(catalog) != render_manifest.get(
        "evidence_catalog_sha256"
    ):
        fail(
            "catalog_sha256_mismatch",
            "The evidence catalog changed after rendering and semantic review.",
        )
    intake: Mapping[str, Any] | None = None
    expected_intake_sha = str(catalog.get("run_intake_sha256") or "")
    if expected_intake_sha:
        intake_path = output_dir / "run_intake.json"
        if not intake_path.is_file():
            fail("run_intake_missing", "The hash-pinned run intake is missing.")
        else:
            try:
                intake = _load_json(intake_path)
            except ContractError as exc:
                fail("run_intake_invalid", str(exc))
            else:
                if _canonical_json_sha256(intake) != expected_intake_sha:
                    fail(
                        "run_intake_changed",
                        "The run intake changed after evidence preparation.",
                    )
    try:
        _validate_report_model(model, catalog=catalog)
    except ContractError as exc:
        fail("report_model_contract_failed", str(exc))

    package_dir = Path(str(catalog.get("package", {}).get("path") or "")).resolve()
    if not package_dir.is_dir():
        fail("package_missing", f"Evidence package is unavailable: {package_dir}")
        return findings

    catalog_lineage = catalog.get("transport_lineage")
    intake_lineage = None
    if isinstance(intake, dict) and isinstance(intake.get("inputs"), dict):
        intake_lineage = intake["inputs"].get("transport_lineage")
    if catalog_lineage != intake_lineage:
        fail(
            "transport_lineage_intake_mismatch",
            "Evidence catalog and run intake disagree on transport lineage.",
        )
    if catalog_lineage is not None:
        if not isinstance(catalog_lineage, dict):
            fail(
                "transport_lineage_invalid",
                "Evidence catalog transport lineage must be an object.",
            )
        else:
            artifacts = catalog_lineage.get("artifacts")
            if not isinstance(artifacts, dict) or set(artifacts) != set(
                LOCAL_TRANSPORT_RECEIPT_FILES
            ):
                fail(
                    "transport_receipt_ledger_invalid",
                    "Transport lineage does not pin both local receipt copies.",
                )
            else:
                receipt_paths = tuple(
                    output_dir / file_name
                    for file_name in LOCAL_TRANSPORT_RECEIPT_FILES
                )
                receipt_hashes_valid = True
                for receipt_path in receipt_paths:
                    expected_sha256 = str(artifacts.get(receipt_path.name) or "")
                    if (
                        not receipt_path.is_file()
                        or not re.fullmatch(r"[0-9a-f]{64}", expected_sha256)
                        or _sha256_file(receipt_path) != expected_sha256
                    ):
                        receipt_hashes_valid = False
                        fail(
                            "transport_receipt_changed",
                            f"Pinned transport receipt changed: {receipt_path.name}",
                        )
                if receipt_hashes_valid:
                    try:
                        current_lineage = _validate_local_transport_receipts(
                            package_dir,
                            _load_local_transport_receipt(
                                receipt_paths[0],
                                label="Pinned local download receipt",
                            ),
                            _load_local_transport_receipt(
                                receipt_paths[1],
                                label="Pinned local extraction receipt",
                            ),
                        )
                    except ContractError as exc:
                        fail("transport_lineage_failed", str(exc))
                    else:
                        expected_lineage = {
                            key: value
                            for key, value in catalog_lineage.items()
                            if key != "artifacts"
                        }
                        if current_lineage != expected_lineage:
                            fail(
                                "transport_lineage_changed",
                                "Current package transport lineage differs from preparation.",
                            )
    elif isinstance(intake, dict):
        inputs = intake.get("inputs")
        provenance = (
            inputs.get("mapping_provenance") if isinstance(inputs, dict) else None
        )
        acceptance = (
            provenance.get("server_acceptance")
            if isinstance(provenance, dict)
            else None
        )
        if isinstance(acceptance, dict) and acceptance.get("status") == (
            "server_accepted"
        ):
            fail(
                "transport_lineage_missing",
                "Server-accepted provenance has no verified download/extraction lineage.",
            )
    manifest: Mapping[str, Any] = {}
    try:
        manifest = _load_json(
            _contained_package_path(
                package_dir, "pack_manifest.json", label="pack manifest"
            )
        )
        source_paths = _package_source_paths(package_dir, manifest)
        current_package_sha = _package_fingerprint(package_dir, source_paths)
    except ContractError as exc:
        fail("package_fingerprint_unavailable", str(exc))
        current_package_sha = ""
    expected_package_sha = str(catalog.get("package", {}).get("sha256") or "")
    if current_package_sha != expected_package_sha:
        fail(
            "package_sha256_mismatch",
            "The evidence package changed after run preparation.",
        )

    source_hashes = catalog.get("source_hashes")
    if not isinstance(source_hashes, dict):
        fail("source_hashes_missing", "The evidence catalog has no source hash ledger.")
    else:
        for raw_relative, expected_sha in source_hashes.items():
            try:
                relative = _safe_relative_path(
                    str(raw_relative), label="catalog source"
                )
                path = _contained_package_path(
                    package_dir, relative, label="catalog source"
                )
            except ContractError as exc:
                fail("source_path_invalid", str(exc))
                continue
            if not path.is_file():
                fail(
                    "source_missing",
                    f"Package source is missing: {relative.as_posix()}",
                )
            elif _sha256_file(path) != expected_sha:
                fail(
                    "source_sha256_mismatch",
                    f"Package source changed: {relative.as_posix()}",
                )

    catalog_sources = catalog.get("sources")
    if not isinstance(catalog_sources, list):
        fail("source_catalog_missing", "The evidence source catalog is missing.")
    else:
        for item in catalog_sources:
            if not isinstance(item, dict) or item.get("status") != "available":
                continue
            raw_source = str(item.get("file") or "")
            expected_sha = str(item.get("sha256") or "")
            try:
                relative = _safe_relative_path(
                    raw_source, label="available catalog source"
                )
                path = _contained_package_path(
                    package_dir, relative, label="available catalog source"
                )
            except ContractError as exc:
                fail("source_catalog_path_invalid", str(exc))
                continue
            if not expected_sha:
                fail(
                    "source_catalog_sha256_missing",
                    f"Available catalog source has no hash: {relative.as_posix()}",
                )
            elif not path.is_file():
                fail(
                    "source_catalog_missing",
                    f"Available catalog source is missing: {relative.as_posix()}",
                )
            elif _sha256_file(path) != expected_sha:
                fail(
                    "source_catalog_sha256_mismatch",
                    f"Available catalog source changed: {relative.as_posix()}",
                )

    checked_ledger_sources: set[tuple[str, str]] = set()
    for claim in claim_ledger.get("claims") or []:
        if not isinstance(claim, dict):
            continue
        for evidence in claim.get("evidence") or []:
            if not isinstance(evidence, dict):
                continue
            raw_source = str(evidence.get("source") or "")
            expected_sha = str(evidence.get("source_sha256") or "")
            source_identity = (raw_source, expected_sha)
            if source_identity in checked_ledger_sources:
                continue
            checked_ledger_sources.add(source_identity)
            try:
                relative = _safe_relative_path(raw_source, label="claim-ledger source")
                path = _contained_package_path(
                    package_dir, relative, label="claim-ledger source"
                )
            except ContractError as exc:
                fail("source_ledger_path_invalid", str(exc))
                continue
            if not expected_sha:
                fail(
                    "source_ledger_sha256_missing",
                    f"Claim-ledger source has no hash: {relative.as_posix()}",
                )
            elif not path.is_file():
                fail(
                    "source_ledger_missing",
                    f"Claim-ledger source is missing: {relative.as_posix()}",
                )
            elif _sha256_file(path) != expected_sha:
                fail(
                    "source_ledger_sha256_mismatch",
                    f"Claim-ledger source changed: {relative.as_posix()}",
                )

    try:
        integrity_path = _contained_package_path(
            package_dir, "package_integrity.json", label="package integrity"
        )
        integrity = _load_json(integrity_path)
    except ContractError as exc:
        fail("package_integrity_unavailable", str(exc))
    else:
        if str(integrity.get("status") or "").lower() != "pass":
            fail("package_integrity_failed", "Package integrity is not pass.")
        expected_integrity_sha = str(
            catalog.get("package", {}).get("integrity_sha256") or ""
        )
        if _sha256_file(integrity_path) != expected_integrity_sha:
            fail(
                "package_integrity_sha256_mismatch",
                "Package integrity artifact changed.",
            )
        try:
            summary = _load_json(
                _contained_package_path(
                    package_dir, "summary.json", label="package summary"
                )
            )
            expected_warnings = _collect_package_warnings(
                package_dir,
                summary,
                manifest,
                integrity,
            )
        except ContractError as exc:
            fail("catalog_warning_check_failed", str(exc))
        else:
            catalog_warnings = catalog.get("warnings")
            if (
                not isinstance(catalog_warnings, list)
                or catalog_warnings != expected_warnings
            ):
                fail(
                    "catalog_warning_mismatch",
                    "Evidence-catalog warnings differ from the current package warnings.",
                )

    model_sha = _canonical_json_sha256(model)
    if model_sha != render_manifest.get("report_model_sha256"):
        fail("report_model_changed", "The report model changed after rendering.")
    if render_manifest.get("report_id") != model.get("report_id"):
        fail(
            "report_id_mismatch",
            "Render manifest and report model disagree on report_id.",
        )
    if render_manifest.get("package_sha256") != expected_package_sha:
        fail(
            "render_package_mismatch",
            "Render manifest targets another evidence package.",
        )

    draft_path = output_dir / str(render_manifest.get("draft_html") or "")
    if not draft_path.is_file():
        fail("draft_missing", "Rendered HTML draft is missing.")
    elif _sha256_file(draft_path) != render_manifest.get("draft_html_sha256"):
        fail("draft_sha256_mismatch", "Rendered HTML draft changed after rendering.")

    if _canonical_json_sha256(claim_ledger) != render_manifest.get(
        "claim_ledger_sha256"
    ):
        fail("claim_ledger_changed", "The claim ledger changed after rendering.")
    ledger_claims = claim_ledger.get("claims")
    if not isinstance(ledger_claims, list) or not ledger_claims:
        fail("claim_ledger_empty", "The claim ledger has no claims.")
    else:
        for item in ledger_claims:
            if not isinstance(item, dict) or item.get("status") != "pass":
                fail(
                    "claim_check_failed",
                    "At least one deterministic claim check is not pass.",
                )
                break

    for table in render_manifest.get("rendered_tables") or []:
        if not isinstance(table, dict):
            fail(
                "table_manifest_invalid",
                "Rendered table manifest contains a non-object row.",
            )
            continue
        try:
            relative = _safe_relative_path(
                str(table.get("csv") or ""), label="rendered table"
            )
        except ContractError as exc:
            fail("table_path_invalid", str(exc))
            continue
        path = output_dir / "evidence" / relative
        if not path.is_file() or _sha256_file(path) != table.get("sha256"):
            fail(
                "table_sha256_mismatch",
                f"Rendered table changed: {table.get('table_key')}",
            )

    for product in render_manifest.get("featured_products") or []:
        if not isinstance(product, dict) or not product.get("image_path"):
            continue
        try:
            relative = _safe_relative_path(
                str(product["image_path"]), label="product image"
            )
        except ContractError as exc:
            fail("product_image_path_invalid", str(exc))
            continue
        path = output_dir / relative
        if not path.is_file() or _sha256_file(path) != product.get("image_sha256"):
            fail(
                "product_image_sha256_mismatch",
                f"Featured image changed: {product.get('product_id')}",
            )

    report_id = html.escape(str(model.get("report_id") or ""))
    if f'data-report-id="{report_id}"' not in draft:
        fail("html_report_id_missing", "HTML does not carry the report id.")
    for claim in model.get("claims") or []:
        claim_id = html.escape(str(claim.get("claim_id") or ""))
        if draft.count(f'data-claim-id="{claim_id}"') != 1:
            fail("html_claim_parity", f"HTML claim parity failed for {claim_id}.")
    for section in model.get("sections") or []:
        section_id = html.escape(str(section.get("section_id") or ""))
        if draft.count(f'data-section-id="{section_id}"') != 1:
            fail("html_section_parity", f"HTML section parity failed for {section_id}.")
    for warning in catalog.get("warnings") or []:
        warning_code = html.escape(str(warning.get("code") or ""))
        if draft.count(f'data-warning-code="{warning_code}"') != 1:
            fail(
                "html_warning_parity",
                f"HTML does not visibly disclose warning {warning_code}.",
            )
    if re.search(r"<(?:script|img)[^>]+src=[\"']https?://", draft, re.IGNORECASE):
        fail(
            "external_asset_detected",
            "HTML contains an external script or image asset.",
        )
    return findings


def _semantic_review_state(
    review: Mapping[str, Any],
    *,
    model: Mapping[str, Any],
    render_manifest: Mapping[str, Any],
) -> tuple[str, list[dict[str, str]], bool]:
    findings: list[dict[str, str]] = []

    def invalid(code: str, message: str) -> None:
        findings.append({"code": code, "message": message})

    def finding_code(kind: str, identity: str) -> str:
        token = _normalise_mapping_token(identity)[:64] or "item"
        digest = hashlib.sha256(identity.encode("utf-8")).hexdigest()[:8]
        return f"semantic_{kind}_{token}_{digest}"

    if review.get("schema_version") != REVIEW_SCHEMA:
        invalid(
            "semantic_review_schema",
            "Semantic review schema is missing or unsupported.",
        )
        return "unable_to_determine", findings, False
    reviewer = review.get("reviewer")
    author = model.get("author")
    if not isinstance(author, dict):
        invalid("semantic_author_invalid", "Report author identity is invalid.")
        author = {}
    if not SAFE_ID_RE.fullmatch(str(review.get("review_id") or "")):
        invalid("semantic_review_id", "Semantic review_id is missing or invalid.")
    if review.get("author_agent_id") != author.get("agent_id"):
        invalid(
            "semantic_review_author_mismatch",
            "Semantic review does not identify the report author.",
        )
    if not str(review.get("summary") or "").strip():
        invalid("semantic_review_summary", "Semantic review summary is required.")
    if not isinstance(reviewer, dict) or reviewer.get("execution") != "codex_agent":
        invalid(
            "semantic_reviewer_invalid",
            "Semantic review was not attributed to a Codex agent.",
        )
    elif (
        not reviewer.get("independent_from_author")
        or reviewer.get("role") != "independent_reviewer"
        or not str(reviewer.get("agent_id") or "").strip()
        or reviewer.get("agent_id") == author.get("agent_id")
    ):
        invalid(
            "semantic_reviewer_not_independent",
            "Semantic reviewer is not independent from the author.",
        )
    targets = review.get("targets")
    if not isinstance(targets, dict):
        invalid(
            "semantic_review_targets_missing", "Semantic review has no target hashes."
        )
    else:
        expected_targets = {
            "report_id": model.get("report_id"),
            "evidence_catalog_sha256": render_manifest.get("evidence_catalog_sha256"),
            "report_model_sha256": render_manifest.get("report_model_sha256"),
            "draft_html_sha256": render_manifest.get("draft_html_sha256"),
        }
        if any(targets.get(key) != value for key, value in expected_targets.items()):
            invalid(
                "semantic_review_target_mismatch",
                "Semantic review targets another draft or model.",
            )

    dimensions = review.get("dimensions")
    if not isinstance(dimensions, dict) or set(dimensions) != set(
        REQUIRED_REVIEW_DIMENSIONS
    ):
        invalid(
            "semantic_review_dimensions",
            "Semantic review must cover every required dimension.",
        )
        dimension_statuses: list[str] = []
    else:
        dimension_statuses = []
        for dimension in REQUIRED_REVIEW_DIMENSIONS:
            item = dimensions[dimension]
            if (
                not isinstance(item, dict)
                or item.get("status")
                not in {
                    "pass",
                    "caveat",
                    "fail",
                    "unable_to_determine",
                }
                or not str(item.get("rationale") or "").strip()
            ):
                invalid(
                    "semantic_review_dimension_invalid",
                    f"Invalid semantic review dimension: {dimension}",
                )
                continue
            status = str(item["status"])
            dimension_statuses.append(status)
            if status != "pass":
                findings.append(
                    {
                        "code": finding_code("dimension", dimension),
                        "message": str(item["rationale"]).strip(),
                        "status": status,
                    }
                )

    report_level_statuses: list[str] = []
    report_level_findings = review.get("report_level_findings")
    if not isinstance(report_level_findings, list):
        invalid(
            "semantic_report_findings_missing",
            "Semantic review has no report-level findings list.",
        )
    else:
        seen_finding_codes: set[str] = set()
        for item in report_level_findings:
            if not isinstance(item, dict):
                invalid(
                    "semantic_report_finding_invalid",
                    "A report-level finding is not an object.",
                )
                continue
            code = str(item.get("code") or "")
            status = str(item.get("status") or "")
            message = str(item.get("finding") or "").strip()
            if (
                not SAFE_ID_RE.fullmatch(code)
                or code in seen_finding_codes
                or status not in {"caveat", "fail", "unable_to_determine"}
                or not message
            ):
                invalid(
                    "semantic_report_finding_invalid",
                    f"Invalid report-level finding: {code or '(missing code)' }.",
                )
                continue
            seen_finding_codes.add(code)
            report_level_statuses.append(status)
            findings.append({"code": code, "message": message, "status": status})

    model_claim_ids = {str(item.get("claim_id")) for item in model.get("claims") or []}
    claim_reviews = review.get("claim_reviews")
    review_by_id: dict[str, Mapping[str, Any]] = {}
    if not isinstance(claim_reviews, list):
        invalid(
            "semantic_claim_reviews_missing",
            "Semantic review has no claim review list.",
        )
    else:
        for item in claim_reviews:
            if not isinstance(item, dict):
                invalid(
                    "semantic_claim_review_invalid", "A claim review is not an object."
                )
                continue
            claim_id = str(item.get("claim_id") or "")
            if claim_id in review_by_id:
                invalid(
                    "semantic_claim_review_duplicate",
                    f"Claim {claim_id} was reviewed more than once.",
                )
                continue
            if (
                item.get("verdict")
                not in {
                    "supported",
                    "supported_with_caveat",
                    "unsupported",
                    "unable_to_determine",
                }
                or not str(item.get("reason") or "").strip()
            ):
                invalid(
                    "semantic_claim_review_invalid",
                    f"Claim {claim_id} has an invalid semantic verdict.",
                )
                continue
            review_by_id[claim_id] = item
            verdict = str(item["verdict"])
            if verdict != "supported":
                findings.append(
                    {
                        "code": finding_code("claim", claim_id),
                        "message": str(item["reason"]).strip(),
                        "status": {
                            "supported_with_caveat": "caveat",
                            "unsupported": "fail",
                            "unable_to_determine": "unable_to_determine",
                        }[verdict],
                    }
                )
        if set(review_by_id) != model_claim_ids:
            invalid(
                "semantic_claim_coverage",
                "Semantic review must cover every report claim exactly once.",
            )

    image_statuses: list[str] = []
    expected_images = {
        str(item.get("product_id")): item
        for item in render_manifest.get("featured_products") or []
        if isinstance(item, dict) and item.get("image_path")
    }
    images_reviewed = review.get("images_reviewed")
    reviewed_images: dict[str, Mapping[str, Any]] = {}
    if not isinstance(images_reviewed, list):
        invalid(
            "semantic_image_reviews_missing",
            "Semantic review has no image review list.",
        )
    else:
        for item in images_reviewed:
            if not isinstance(item, dict):
                invalid(
                    "semantic_image_review_invalid",
                    "An image review is not an object.",
                )
                continue
            product_id = str(item.get("product_id") or "")
            expected = expected_images.get(product_id)
            status = str(item.get("status") or "")
            if (
                expected is None
                or product_id in reviewed_images
                or item.get("image_path") != expected.get("image_path")
                or item.get("image_sha256") != expected.get("image_sha256")
                or status not in {"pass", "caveat", "fail", "unable_to_determine"}
                or not str(item.get("observation") or "").strip()
            ):
                invalid(
                    "semantic_image_review_invalid",
                    f"Invalid semantic image review for {product_id or '(missing product)' }.",
                )
                continue
            reviewed_images[product_id] = item
            image_statuses.append(status)
            if status != "pass":
                findings.append(
                    {
                        "code": finding_code("image", product_id),
                        "message": str(item["observation"]).strip(),
                        "status": status,
                    }
                )
        if set(reviewed_images) != set(expected_images):
            invalid(
                "semantic_image_review_coverage",
                "Semantic review must cover every rendered local product image exactly once.",
            )

    overall = str(review.get("overall_verdict") or "")
    if overall not in VERDICT_LABELS:
        invalid("semantic_overall_verdict", "Semantic overall verdict is invalid.")
    elif overall != "correct":
        overall_status = {
            "correct_with_caveats": "caveat",
            "incorrect": "fail",
            "unable_to_determine": "unable_to_determine",
        }[overall]
        if not any(item.get("status") == overall_status for item in findings):
            findings.append(
                {
                    "code": "semantic_overall_review",
                    "message": str(review.get("summary") or "").strip(),
                    "status": overall_status,
                }
            )
    structural_findings = [item for item in findings if "status" not in item]
    if structural_findings:
        return "unable_to_determine", findings, False

    claim_verdicts = {str(item.get("verdict")) for item in review_by_id.values()}
    if (
        overall == "incorrect"
        or "unsupported" in claim_verdicts
        or "fail" in dimension_statuses
        or "fail" in report_level_statuses
        or "fail" in image_statuses
    ):
        state = "incorrect"
    elif (
        overall == "unable_to_determine"
        or "unable_to_determine" in claim_verdicts
        or "unable_to_determine" in dimension_statuses
        or "unable_to_determine" in report_level_statuses
        or "unable_to_determine" in image_statuses
    ):
        state = "unable_to_determine"
    elif (
        overall == "correct_with_caveats"
        or "supported_with_caveat" in claim_verdicts
        or "caveat" in dimension_statuses
        or "caveat" in report_level_statuses
        or "caveat" in image_statuses
    ):
        state = "correct_with_caveats"
    else:
        state = "correct"
    return state, findings, True


def _no_work_mapping_review_state(
    output_dir: Path,
    *,
    basis: Any,
    intake_inputs: Mapping[str, Any],
) -> tuple[str, list[dict[str, str]], bool, dict[str, Any] | None]:
    """Validate and disclose one explicit zero-task current-package branch."""

    invalid_finding = {
        "code": "mapping_no_work_basis_invalid",
        "message": (
            "The no-work mapping basis is missing, stale, or inconsistent with "
            "the preliminary current-database package."
        ),
        "status": "unable_to_determine",
    }
    if not isinstance(basis, dict):
        return "unable_to_determine", [invalid_finding], False, None
    artifact_name = str(basis.get("artifact") or "")
    artifact_path = output_dir / artifact_name
    expected_sha256 = str(basis.get("artifact_sha256") or "")
    transport_lineage = intake_inputs.get("transport_lineage")
    download_lineage = (
        transport_lineage.get("download")
        if isinstance(transport_lineage, dict)
        else None
    )
    expected_job_id = (
        str(download_lineage.get("job_id") or "")
        if isinstance(download_lineage, dict)
        else ""
    )
    try:
        if artifact_name != NO_WORK_WORKSET_FILE:
            raise ContractError("Unexpected no-work workset artifact")
        if (
            not re.fullmatch(r"[0-9a-f]{64}", expected_sha256)
            or not artifact_path.is_file()
            or _sha256_file(artifact_path) != expected_sha256
        ):
            raise ContractError("No-work workset artifact changed")
        _source, workset = _load_no_work_workset(artifact_path)
        catalog = _load_json(output_dir / "evidence_catalog.json")
        package = catalog.get("package")
        if not isinstance(package, dict):
            raise ContractError("Evidence catalog has no package scope")
        validated = _validate_no_work_workset(
            workset,
            package_summary=package,
            expected_job_id=expected_job_id,
        )
        package_dir = Path(str(package.get("path") or "")).resolve()
        validated["server_sanitization_receipt_sha256"] = (
            _validate_preliminary_sanitization_receipt(package_dir)
        )
        expected_basis = {
            **validated,
            "artifact": NO_WORK_WORKSET_FILE,
            "artifact_sha256": expected_sha256,
        }
        if basis != expected_basis or catalog.get("mapping_review_basis") != basis:
            raise ContractError("No-work mapping basis changed")
    except ContractError:
        return "unable_to_determine", [invalid_finding], False, None

    resolved_count = int(basis["resolved_attribute_cells"])
    if resolved_count > 0:
        cell_label = "cell" if resolved_count == 1 else "cells"
        message = (
            "No unresolved product/parent mapping tasks were issued. "
            f"{resolved_count} pre-existing resolved attribute {cell_label} from the "
            "central current-database package were treated as trusted input and "
            "were not re-reviewed in this run; mapping review is not applicable."
        )
    else:
        message = (
            "No unresolved product/parent mapping tasks were issued, so no new "
            "mapping was authored or reviewed. The report uses the preliminary "
            "current-database package as-is; mapping review is not applicable."
        )
    findings = [
        {
            "code": "mapping_no_work_trusted_current_package",
            "message": message,
            "status": "caveat",
        }
    ]
    skipped_variants = int(basis["variant_attribute_cells_skipped"])
    if skipped_variants > 0:
        findings.append(
            {
                "code": "variant_mapping_coverage_incomplete",
                "message": (
                    f"{skipped_variants} variant-level attribute cells were outside "
                    "the parent-product zero-task workset and remain a coverage caveat."
                ),
                "status": "caveat",
            }
        )
    validation = {
        "review_state": "not_applicable",
        "summary": message,
        "resolved_attribute_cells": resolved_count,
        "include_resolved": False,
        "task_count": 0,
        "variant_attribute_cells_skipped": skipped_variants,
    }
    return "not_applicable", findings, True, validation


def _mapping_review_state(
    output_dir: Path,
) -> tuple[str, list[dict[str, str]], bool, dict[str, Any] | None]:
    """Validate mapping-review mechanics when this report run carries mappings."""

    artifact_names = {
        "tasks": "mapping_tasks.json",
        "decisions": "mapping_decisions.json",
        "validated": "validated_mappings.json",
        "review": "mapping_review.json",
    }
    present = {
        key: (output_dir / file_name).is_file()
        for key, file_name in artifact_names.items()
    }
    intake_path = output_dir / "run_intake.json"
    intake = _load_json(intake_path) if intake_path.is_file() else {}
    intake_inputs = intake.get("inputs")
    expected_provenance = (
        intake_inputs.get("mapping_provenance")
        if isinstance(intake_inputs, dict)
        else None
    )
    mapping_review_basis = (
        intake_inputs.get("mapping_review_basis")
        if isinstance(intake_inputs, dict)
        else None
    )
    if not any(present.values()) and expected_provenance is None:
        if mapping_review_basis is not None and isinstance(intake_inputs, dict):
            return _no_work_mapping_review_state(
                output_dir,
                basis=mapping_review_basis,
                intake_inputs=intake_inputs,
            )
        return "not_applicable", [], True, None
    if mapping_review_basis is not None:
        return (
            "unable_to_determine",
            [
                {
                    "code": "mapping_review_basis_conflict",
                    "message": (
                        "The run carries both a no-work basis and new-mapping "
                        "review artifacts."
                    ),
                    "status": "unable_to_determine",
                }
            ],
            False,
            None,
        )
    missing = [
        artifact_names[key] for key, is_present in present.items() if not is_present
    ]
    if missing:
        return (
            "unable_to_determine",
            [
                {
                    "code": "mapping_review_artifacts_missing",
                    "message": (
                        "Mapping provenance is incomplete; missing: "
                        + ", ".join(sorted(missing))
                    ),
                    "status": "unable_to_determine",
                }
            ],
            False,
            None,
        )
    acceptance_status = "local_review_only"
    if expected_provenance is not None:
        if not isinstance(expected_provenance, dict) or not isinstance(
            expected_provenance.get("artifacts"), dict
        ):
            return (
                "unable_to_determine",
                [
                    {
                        "code": "mapping_review_provenance_invalid",
                        "message": "Run intake contains an invalid mapping provenance contract.",
                        "status": "unable_to_determine",
                    }
                ],
                False,
                None,
            )
        server_acceptance = expected_provenance.get("server_acceptance")
        if not isinstance(server_acceptance, dict) or server_acceptance.get(
            "status"
        ) not in {"server_accepted", "local_review_only"}:
            return (
                "unable_to_determine",
                [
                    {
                        "code": "mapping_server_acceptance_invalid",
                        "message": (
                            "Run intake contains an invalid server mapping-acceptance "
                            "contract."
                        ),
                        "status": "unable_to_determine",
                    }
                ],
                False,
                None,
            )
        acceptance_status = str(server_acceptance["status"])
        server_hashes = server_acceptance.get("artifacts")
        if not isinstance(server_hashes, dict):
            return (
                "unable_to_determine",
                [
                    {
                        "code": "mapping_server_acceptance_invalid",
                        "message": "Server mapping-acceptance artifact pins are invalid.",
                        "status": "unable_to_determine",
                    }
                ],
                False,
                None,
            )
        expected_server_names = (
            set(SERVER_MAPPING_PROVENANCE_FILES)
            if acceptance_status == "server_accepted"
            else set()
        )
        if set(server_hashes) != expected_server_names or any(
            not (output_dir / file_name).is_file()
            or not re.fullmatch(r"[0-9a-f]{64}", str(expected_sha256 or ""))
            or _sha256_file(output_dir / file_name) != str(expected_sha256)
            for file_name, expected_sha256 in server_hashes.items()
        ):
            return (
                "unable_to_determine",
                [
                    {
                        "code": "mapping_server_acceptance_changed",
                        "message": (
                            "Server mapping-acceptance provenance is missing or differs "
                            "from the run intake hashes."
                        ),
                        "status": "unable_to_determine",
                    }
                ],
                False,
                None,
            )
        expected_hashes = expected_provenance["artifacts"]
        if set(expected_hashes) != set(artifact_names.values()) or any(
            not re.fullmatch(r"[0-9a-f]{64}", str(expected_hashes.get(file_name) or ""))
            or _sha256_file(output_dir / file_name) != str(expected_hashes[file_name])
            for file_name in artifact_names.values()
        ):
            return (
                "unable_to_determine",
                [
                    {
                        "code": "mapping_review_provenance_changed",
                        "message": "Mapping provenance differs from the run intake hashes.",
                        "status": "unable_to_determine",
                    }
                ],
                False,
                None,
            )
    try:
        validation = validate_mapping_review_payloads(
            _load_json(output_dir / artifact_names["tasks"]),
            _load_json(output_dir / artifact_names["decisions"]),
            _load_json(output_dir / artifact_names["validated"]),
            _load_json(output_dir / artifact_names["review"]),
        )
    except ContractError as exc:
        return (
            "unable_to_determine",
            [
                {
                    "code": "mapping_review_invalid",
                    "message": str(exc),
                    "status": "unable_to_determine",
                }
            ],
            False,
            None,
        )

    state = str(validation["review_state"])
    findings: list[dict[str, str]] = []
    status_by_verdict = {
        "supported_with_caveat": "caveat",
        "unsupported": "fail",
        "unable_to_determine": "unable_to_determine",
    }
    for finding in validation.get("findings") or []:
        task_id = str(finding.get("task_id") or "mapping-task")
        digest = hashlib.sha256(task_id.encode("utf-8")).hexdigest()[:8]
        findings.append(
            {
                "code": f"mapping_review_{digest}",
                "message": str(finding.get("reason") or "").strip(),
                "status": status_by_verdict[str(finding["verdict"])],
            }
        )
    if acceptance_status != "server_accepted":
        findings.append(
            {
                "code": "mapping_not_server_accepted",
                "message": (
                    "The mappings passed independent local review but this report run "
                    "does not carry proof that the shared server database accepted them."
                ),
                "status": "caveat",
            }
        )
    tasks_payload = _load_json(output_dir / artifact_names["tasks"])
    coverage = tasks_payload.get("coverage")
    skipped_variants = (
        coverage.get("variant_attribute_cells_skipped", 0)
        if isinstance(coverage, dict)
        else 0
    )
    if not isinstance(skipped_variants, int) or isinstance(skipped_variants, bool):
        skipped_variants = 0
    if skipped_variants > 0:
        findings.append(
            {
                "code": "variant_mapping_coverage_incomplete",
                "message": (
                    f"{skipped_variants} variant-level attribute cells were outside "
                    "the parent-product mapping workset and remain a coverage caveat."
                ),
                "status": "caveat",
            }
        )
    include_resolved = (
        coverage.get("include_resolved") if isinstance(coverage, dict) else None
    )
    resolved_attribute_cells = (
        coverage.get("resolved_attribute_cells", 0) if isinstance(coverage, dict) else 0
    )
    if (
        include_resolved is False
        and isinstance(resolved_attribute_cells, int)
        and not isinstance(resolved_attribute_cells, bool)
        and resolved_attribute_cells > 0
    ):
        cell_label = "cell" if resolved_attribute_cells == 1 else "cells"
        findings.append(
            {
                "code": "central_resolved_mappings_trusted_input",
                "message": (
                    "This incremental review covered unresolved tasks only. "
                    f"{resolved_attribute_cells} pre-existing resolved attribute "
                    f"{cell_label} from the central package were trusted input and were "
                    "not re-reviewed in this run."
                ),
                "status": "caveat",
            }
        )
    correction_selection = tasks_payload.get("correction_selection")
    correction_counts: dict[str, int] = {}
    if correction_selection is not None:
        if (
            not isinstance(correction_selection, dict)
            or correction_selection.get("schema_version")
            != CORRECTION_TASK_SELECTION_SCHEMA
            or not isinstance(correction_selection.get("criteria"), dict)
        ):
            return (
                "unable_to_determine",
                [
                    *findings,
                    {
                        "code": "correction_mapping_scope_invalid",
                        "message": "The correction workset scope disclosure is invalid.",
                        "status": "unable_to_determine",
                    },
                ],
                False,
                None,
            )
        for field in (
            "task_count_before_selection",
            "task_count",
            "excluded_unresolved_count",
            "excluded_non_codex_effective_count",
            "excluded_not_pinned_count",
        ):
            value = correction_selection.get(field)
            if isinstance(value, bool) or not isinstance(value, int) or value < 0:
                return (
                    "unable_to_determine",
                    [
                        *findings,
                        {
                            "code": "correction_mapping_scope_invalid",
                            "message": (
                                "The correction workset scope disclosure is invalid."
                            ),
                            "status": "unable_to_determine",
                        },
                    ],
                    False,
                    None,
                )
            correction_counts[field] = value
        if (
            include_resolved is not True
            or correction_counts["task_count"] != len(tasks_payload.get("tasks") or [])
            or correction_counts["task_count_before_selection"]
            != correction_counts["task_count"]
            + correction_counts["excluded_unresolved_count"]
            + correction_counts["excluded_non_codex_effective_count"]
            + correction_counts["excluded_not_pinned_count"]
        ):
            return (
                "unable_to_determine",
                [
                    *findings,
                    {
                        "code": "correction_mapping_scope_invalid",
                        "message": "The correction workset scope disclosure is invalid.",
                        "status": "unable_to_determine",
                    },
                ],
                False,
                None,
            )
        excluded_unresolved = correction_counts["excluded_unresolved_count"]
        if excluded_unresolved > 0:
            findings.append(
                {
                    "code": "correction_unresolved_cells_not_reviewed",
                    "message": (
                        f"{excluded_unresolved} unresolved attribute cells were outside "
                        "this accepted-mapping correction review and remain unmapped."
                    ),
                    "status": "caveat",
                }
            )
        excluded_non_codex = correction_counts["excluded_non_codex_effective_count"]
        if excluded_non_codex > 0:
            findings.append(
                {
                    "code": "correction_non_codex_effective_cells_not_reviewed",
                    "message": (
                        f"{excluded_non_codex} resolved attribute cells were excluded "
                        "because their effective value did not come from an accepted "
                        "Codex mapping; they were trusted package input and were not "
                        "re-reviewed in this correction run."
                    ),
                    "status": "caveat",
                }
            )
        if correction_counts["excluded_not_pinned_count"] > 0:
            return (
                "unable_to_determine",
                [
                    *findings,
                    {
                        "code": "correction_mapping_state_inconsistent",
                        "message": (
                            "The correction package contains Codex-effective mappings "
                            "that are absent from its pinned database state."
                        ),
                        "status": "unable_to_determine",
                    },
                ],
                False,
                None,
            )
    report_state = {
        "approved": "correct",
        "approved_with_caveats": "correct_with_caveats",
        "rejected": "incorrect",
        "unable_to_determine": "unable_to_determine",
    }[state]
    if report_state == "correct" and any(
        item.get("status") == "caveat" for item in findings
    ):
        report_state = "correct_with_caveats"
    validation = {
        **validation,
        "server_acceptance_status": acceptance_status,
        "variant_attribute_cells_skipped": skipped_variants,
        "include_resolved": include_resolved,
        "resolved_attribute_cells": resolved_attribute_cells,
        "correction_selection": correction_counts or None,
    }
    return report_state, findings, True, validation


def _browser_qa_state(
    output_dir: Path,
    *,
    render_manifest: Mapping[str, Any],
) -> tuple[str, list[dict[str, str]], bool, dict[str, Any] | None]:
    """Validate mechanically measured browser QA without judging report meaning."""

    intake_path = output_dir / "run_intake.json"
    intake = _load_json(intake_path) if intake_path.is_file() else {}
    quality_gates = intake.get("quality_gates")
    required = bool(
        isinstance(quality_gates, dict)
        and quality_gates.get("browser_qa_required") is True
    )
    qa_path = output_dir / "browser_qa.json"
    if not qa_path.is_file():
        if not required:
            return "not_applicable", [], True, None
        return (
            "unable_to_determine",
            [
                {
                    "code": "browser_qa_missing",
                    "message": (
                        "Required desktop/mobile browser QA has not been recorded."
                    ),
                    "status": "unable_to_determine",
                }
            ],
            False,
            None,
        )
    qa = _load_json(qa_path)
    if qa.get("schema_version") != "attribute_reporting.browser_qa.v1":
        return (
            "unable_to_determine",
            [
                {
                    "code": "browser_qa_invalid",
                    "message": "Browser QA uses an unsupported schema.",
                    "status": "unable_to_determine",
                }
            ],
            False,
            qa,
        )
    targets = qa.get("targets")
    expected_targets = {
        "draft_html_sha256": str(render_manifest.get("draft_html_sha256") or ""),
        "render_manifest_sha256": _sha256_file(output_dir / "render_manifest.json"),
    }
    if not isinstance(targets, dict) or any(
        str(targets.get(key) or "") != value for key, value in expected_targets.items()
    ):
        return (
            "unable_to_determine",
            [
                {
                    "code": "browser_qa_stale",
                    "message": "Browser QA targets a different rendered report draft.",
                    "status": "unable_to_determine",
                }
            ],
            False,
            qa,
        )
    status = str(qa.get("status") or "")
    raw_findings = qa.get("findings")
    if status not in {"pass", "fail", "blocked"} or not isinstance(raw_findings, list):
        return (
            "unable_to_determine",
            [
                {
                    "code": "browser_qa_invalid",
                    "message": "Browser QA has an invalid status or findings list.",
                    "status": "unable_to_determine",
                }
            ],
            False,
            qa,
        )
    if status != "blocked":
        raw_viewports = qa.get("viewports")
        expected_viewports = {
            "desktop": (1440, 1000),
            "mobile": (390, 844),
        }
        expected_suffixes = {
            "horizontal_overflow",
            "local_images",
            "asset_locality",
            "table_scrolling",
            "required_elements",
            "product_links",
            "runtime",
        }
        if not isinstance(raw_viewports, list) or len(raw_viewports) != len(
            expected_viewports
        ):
            return (
                "unable_to_determine",
                [
                    {
                        "code": "browser_qa_invalid",
                        "message": "Browser QA must cover desktop and mobile exactly once.",
                        "status": "unable_to_determine",
                    }
                ],
                False,
                qa,
            )
        observed_names: set[str] = set()
        flattened_findings: list[dict[str, Any]] = []
        for viewport in raw_viewports:
            if not isinstance(viewport, dict):
                return (
                    "unable_to_determine",
                    [
                        {
                            "code": "browser_qa_invalid",
                            "message": "Browser QA viewport evidence is invalid.",
                            "status": "unable_to_determine",
                        }
                    ],
                    False,
                    qa,
                )
            name = str(viewport.get("name") or "")
            expected_size = expected_viewports.get(name)
            viewport_findings = viewport.get("findings")
            metrics = viewport.get("metrics")
            screenshot_value = str(viewport.get("screenshot") or "")
            screenshot_sha = str(viewport.get("screenshot_sha256") or "")
            try:
                screenshot_relative = _safe_relative_path(
                    screenshot_value,
                    label="browser QA screenshot",
                )
            except ContractError:
                screenshot_relative = Path(".")
            screenshot_path = (output_dir / screenshot_relative).resolve()
            expected_codes = {
                f"browser.{name}.{suffix}" for suffix in expected_suffixes
            }
            actual_codes = {
                str(item.get("code") or "")
                for item in viewport_findings or []
                if isinstance(item, dict)
            }
            if (
                expected_size is None
                or name in observed_names
                or (viewport.get("width"), viewport.get("height")) != expected_size
                or not isinstance(metrics, dict)
                or not isinstance(viewport_findings, list)
                or actual_codes != expected_codes
                or len(actual_codes) != len(viewport_findings)
                or not screenshot_path.is_relative_to(output_dir.resolve())
                or not screenshot_path.is_file()
                or not re.fullmatch(r"[0-9a-f]{64}", screenshot_sha)
                or _sha256_file(screenshot_path) != screenshot_sha
            ):
                return (
                    "unable_to_determine",
                    [
                        {
                            "code": "browser_qa_invalid",
                            "message": "Browser QA viewport evidence or screenshot is incomplete.",
                            "status": "unable_to_determine",
                        }
                    ],
                    False,
                    qa,
                )
            for item in viewport_findings:
                if (
                    not isinstance(item, dict)
                    or item.get("status") not in {"pass", "fail"}
                    or not str(item.get("message") or "").strip()
                ):
                    return (
                        "unable_to_determine",
                        [
                            {
                                "code": "browser_qa_invalid",
                                "message": "Browser QA contains an invalid viewport finding.",
                                "status": "unable_to_determine",
                            }
                        ],
                        False,
                        qa,
                    )
            observed_names.add(name)
            flattened_findings.extend(viewport_findings)
        if (
            observed_names != set(expected_viewports)
            or flattened_findings != raw_findings
        ):
            return (
                "unable_to_determine",
                [
                    {
                        "code": "browser_qa_invalid",
                        "message": "Browser QA findings do not match its viewport evidence.",
                        "status": "unable_to_determine",
                    }
                ],
                False,
                qa,
            )
        expected_status = (
            "fail"
            if any(item.get("status") == "fail" for item in raw_findings)
            else "pass"
        )
        if status != expected_status or str(qa.get("browser_error") or ""):
            return (
                "unable_to_determine",
                [
                    {
                        "code": "browser_qa_invalid",
                        "message": "Browser QA status does not match its findings.",
                        "status": "unable_to_determine",
                    }
                ],
                False,
                qa,
            )
    findings: list[dict[str, str]] = []
    for item in raw_findings:
        if not isinstance(item, dict) or item.get("status") not in {"pass", "fail"}:
            return (
                "unable_to_determine",
                [
                    {
                        "code": "browser_qa_invalid",
                        "message": "Browser QA contains an invalid finding.",
                        "status": "unable_to_determine",
                    }
                ],
                False,
                qa,
            )
        if item.get("status") == "fail":
            findings.append(
                {
                    "code": str(item.get("code") or "browser_qa_failure"),
                    "message": str(item.get("message") or "Browser QA failed."),
                    "status": "fail",
                }
            )
    if status == "blocked":
        return (
            "unable_to_determine",
            [
                {
                    "code": "browser_qa_blocked",
                    "message": str(
                        qa.get("browser_error")
                        or "The browser runtime was unavailable for report QA."
                    ),
                    "status": "unable_to_determine",
                }
            ],
            False,
            qa,
        )
    if status == "fail" or findings:
        return "incorrect", findings, True, qa
    return "correct", [], True, qa


def _verdict_banner(
    verdict: str,
    summary: str,
    details: Sequence[Mapping[str, str]],
) -> str:
    marks = {
        "correct": "✓",
        "correct_with_caveats": "!",
        "incorrect": "×",
        "unable_to_determine": "?",
    }
    detail_html = ""
    if details:
        detail_html = (
            '<ul class="verdict-details">'
            + "".join(
                f"<li>{html.escape(str(item['message']))}</li>" for item in details
            )
            + "</ul>"
        )
    return (
        f'<aside class="verdict {verdict}" data-correctness-verdict="{verdict}">'
        f'<span class="mark">{marks[verdict]}</span><div><strong>{VERDICT_LABELS[verdict]}</strong>'
        f"<span>{html.escape(summary)}</span>{detail_html}</div></aside>"
    )


def _write_run_review(
    output_dir: Path,
    *,
    verdict: str,
    correctness: Mapping[str, Any],
) -> None:
    mechanical = correctness.get("mechanical_findings") or []
    mapping = correctness.get("mapping_findings") or []
    browser = correctness.get("browser_findings") or []
    semantic = correctness.get("semantic_findings") or []
    caveats = correctness.get("caveats") or []
    lines = [
        "# Attribute Report Run Review",
        "",
        f"**Correctness verdict:** {VERDICT_LABELS[verdict]}",
        "",
        "## Artifact Card",
        "",
        "| Artifact | Purpose | Review status |",
        "| --- | --- | --- |",
        f"| `report.html` | Final private local HTML report | {VERDICT_LABELS[verdict]} |",
        "| `correctness_verdict.json` | Machine-readable direct verdict and basis | Written |",
        "| `claim_ledger.json` | Bound claims and source rows | Checked |",
        (
            "| `mapping_review.json` | Independent semantic mapping review | "
            f"{str(correctness.get('basis', {}).get('mapping_review') or 'not_applicable')} |"
        ),
        (
            "| `browser_qa.json` | Desktop/mobile mechanical browser QA | "
            f"{str(correctness.get('basis', {}).get('browser_qa') or 'not_applicable')} |"
        ),
        "| `semantic_review.json` | Independent Codex semantic review | Checked |",
        "",
        "## Findings",
        "",
    ]
    if not mechanical and not mapping and not browser and not semantic and not caveats:
        lines.append("No blocking mechanical or semantic findings.")
    else:
        for item in [*mechanical, *mapping, *browser, *semantic]:
            lines.append(f"- `{item['code']}` — {item['message']}")
        finding_codes = {item["code"] for item in [*mapping, *browser, *semantic]}
        for item in caveats:
            if item["code"] not in finding_codes:
                lines.append(f"- `{item['code']}` — {item['message']}")
    lines.extend(
        [
            "",
            "## Privacy",
            "",
            (
                "The HTML report, report semantic review, browser QA, and correctness "
                "artifacts remain in this local output folder and were not uploaded. "
                "Only approved structured mapping artifacts may have crossed the "
                "authenticated server boundary."
            ),
            "",
        ]
    )
    (output_dir / "codex_run_review.md").write_text("\n".join(lines), encoding="utf-8")


def _attribute_table_final_outputs(
    output_dir: Path,
    catalog: Mapping[str, Any],
) -> list[dict[str, Any]]:
    """Return existing deterministic table artifacts for final handoff."""

    outputs: list[dict[str, Any]] = []
    manifest_path = output_dir / "evidence" / "attribute_tables" / "manifest.json"
    if manifest_path.is_file():
        outputs.append(
            {
                "path": "evidence/attribute_tables/manifest.json",
                "kind": "json",
                "sha256": _sha256_file(manifest_path),
                "status": "written",
                "artifact_role": "attribute_table_manifest",
            }
        )
    for item in catalog.get("attribute_tables") or []:
        if not isinstance(item, dict):
            continue
        table_key = str(item.get("table_key") or "").strip()
        for field, kind in (("csv", "csv"), ("html", "html")):
            raw_relative = str(item.get(field) or "").strip()
            if not raw_relative:
                continue
            relative = _safe_relative_path(
                raw_relative,
                label=f"attribute table {kind}",
            )
            path = output_dir / "evidence" / relative
            if not path.is_file():
                continue
            outputs.append(
                {
                    "path": f"evidence/{relative.as_posix()}",
                    "kind": kind,
                    "sha256": _sha256_file(path),
                    "status": "written",
                    "artifact_role": "attribute_table",
                    "table_key": table_key,
                }
            )
    return outputs


def finalize_report(output_dir: Path) -> dict[str, Any]:
    """Combine mechanical checks and independent Codex review into a direct verdict."""

    output = _assert_safe_output_dir(output_dir)
    catalog = _load_json(output / "evidence_catalog.json")
    model = _load_json(output / "report_model.json")
    render_manifest = _load_json(output / "render_manifest.json")
    claim_ledger = _load_json(output / "claim_ledger.json")
    review = _load_json(output / "semantic_review.json")
    draft_path = output / str(render_manifest.get("draft_html") or "report_draft.html")
    try:
        draft = draft_path.read_text(encoding="utf-8")
    except FileNotFoundError as exc:
        raise ContractError(f"Rendered HTML draft is missing: {draft_path}") from exc
    if "<!-- ATTRIBUTE_REPORTING_VERDICT -->" not in draft:
        raise ContractError("Rendered HTML draft has no correctness verdict slot")

    mechanical = _mechanical_findings(
        output_dir=output,
        catalog=catalog,
        model=model,
        render_manifest=render_manifest,
        claim_ledger=claim_ledger,
        draft=draft,
    )
    semantic_state, semantic_findings, semantic_complete = _semantic_review_state(
        review,
        model=model,
        render_manifest=render_manifest,
    )
    mapping_state, mapping_findings, mapping_complete, mapping_validation = (
        _mapping_review_state(output)
    )
    browser_state, browser_findings, browser_complete, browser_validation = (
        _browser_qa_state(output, render_manifest=render_manifest)
    )
    active_warnings = [
        str(item.get("code"))
        for item in catalog.get("warnings") or []
        if isinstance(item, dict)
    ]
    warning_caveats = [
        {
            "code": str(item.get("code") or "package_warning"),
            "message": str(item.get("message") or "Active package warning."),
            "status": "caveat",
        }
        for item in catalog.get("warnings") or []
        if isinstance(item, dict)
    ]
    caveats = list(warning_caveats)
    caveat_codes = {item["code"] for item in caveats}
    caveats.extend(
        item
        for item in semantic_findings
        if item.get("status") == "caveat" and item.get("code") not in caveat_codes
    )
    caveat_codes = {item["code"] for item in caveats}
    caveats.extend(
        item
        for item in mapping_findings
        if item.get("status") == "caveat" and item.get("code") not in caveat_codes
    )
    if mechanical:
        verdict = "incorrect"
        verdict_summary = (
            "Mechanical evidence, integrity, or HTML parity checks failed."
        )
    elif browser_state == "incorrect":
        verdict = "incorrect"
        verdict_summary = (
            "Desktop or mobile browser QA found a broken report presentation."
        )
    elif mapping_state == "incorrect":
        verdict = "incorrect"
        verdict_summary = (
            "Independent semantic mapping review rejected one or more product mappings."
        )
    elif semantic_state == "incorrect":
        verdict = "incorrect"
        verdict_summary = "Independent semantic review found unsupported or misleading report content."
    elif not mapping_complete or mapping_state == "unable_to_determine":
        verdict = "unable_to_determine"
        verdict_summary = (
            "The mappings used in this run lack a complete, current independent review."
        )
    elif not browser_complete or browser_state == "unable_to_determine":
        verdict = "unable_to_determine"
        verdict_summary = "Required desktop/mobile browser QA is incomplete or stale."
    elif not semantic_complete or semantic_state == "unable_to_determine":
        verdict = "unable_to_determine"
        verdict_summary = "An independent semantic review is incomplete or cannot support a conclusion."
    elif (
        mapping_state == "correct_with_caveats"
        or semantic_state == "correct_with_caveats"
        or active_warnings
        or caveats
    ):
        verdict = "correct_with_caveats"
        verdict_summary = "The report is supported, with disclosed evidence or interpretation caveats."
    else:
        verdict = "correct"
        verdict_summary = (
            "Mechanical checks pass, required browser QA passes, and independent "
            "semantic review supports every claim."
        )

    detail_candidates: Sequence[Mapping[str, str]] = caveats
    if verdict in {"incorrect", "unable_to_determine"}:
        detail_candidates = [
            *mechanical,
            *mapping_findings,
            *browser_findings,
            *semantic_findings,
            *caveats,
        ]
    verdict_details: list[Mapping[str, str]] = []
    seen_detail_messages: set[str] = set()
    for item in detail_candidates:
        message = str(item.get("message") or "").strip()
        if not message or message in seen_detail_messages:
            continue
        verdict_details.append(item)
        seen_detail_messages.add(message)

    correctness = {
        "schema_version": VERDICT_SCHEMA,
        "checked_at": _utc_now(),
        "report_id": model.get("report_id"),
        "verdict": verdict,
        "label": VERDICT_LABELS[verdict],
        "summary": verdict_summary,
        "basis": {
            "package_integrity": (
                "pass"
                if not any(
                    item["code"].startswith(
                        ("catalog_", "package_", "source_", "render_package_")
                    )
                    for item in mechanical
                )
                else "fail"
            ),
            "mechanical_claims": "pass" if not mechanical else "fail",
            "html_parity": (
                "pass"
                if not any(
                    item["code"].startswith(("html_", "draft_", "external_"))
                    for item in mechanical
                )
                else "fail"
            ),
            "mapping_review": mapping_state,
            "browser_qa": browser_state,
            "semantic_review": semantic_state,
        },
        "mechanical_findings": mechanical,
        "mapping_findings": mapping_findings,
        "browser_findings": browser_findings,
        "semantic_findings": semantic_findings,
        "mapping_review_summary": (
            str(mapping_validation.get("summary") or "")
            if mapping_validation is not None
            else ""
        ),
        "semantic_review_summary": str(review.get("summary") or ""),
        "caveats": caveats,
        "active_warning_codes": active_warnings,
        "report_model_sha256": render_manifest.get("report_model_sha256"),
        "draft_html_sha256": render_manifest.get("draft_html_sha256"),
        "mapping_review_sha256": (
            mapping_validation.get("mapping_review_sha256")
            if mapping_validation is not None
            else None
        ),
        "mapping_review_validation_sha256": (
            mapping_validation.get("review_validation_sha256")
            if mapping_validation is not None
            else None
        ),
        "browser_qa_sha256": (
            _canonical_json_sha256(browser_validation)
            if browser_validation is not None
            else None
        ),
        "semantic_review_sha256": _canonical_json_sha256(review),
    }
    _write_json(output / "correctness_verdict.json", correctness)
    final_html = draft.replace(
        VERDICT_PLACEHOLDER_HTML,
        _verdict_banner(verdict, verdict_summary, verdict_details),
        1,
    )
    final_path = output / "report.html"
    final_path.write_text(final_html, encoding="utf-8")
    final_sha = _sha256_file(final_path)
    _write_run_review(output, verdict=verdict, correctness=correctness)
    status = (
        "final_ready"
        if verdict in {"correct", "correct_with_caveats"}
        else "not_ready" if verdict == "incorrect" else "partial"
    )
    artifact_outputs = [
        {
            "path": "report.html",
            "kind": "html",
            "sha256": final_sha,
            "status": "written",
        },
        {
            "path": "correctness_verdict.json",
            "kind": "json",
            "sha256": _sha256_file(output / "correctness_verdict.json"),
            "status": "written",
        },
        {
            "path": "codex_run_review.md",
            "kind": "markdown",
            "sha256": _sha256_file(output / "codex_run_review.md"),
            "status": "written",
        },
    ]
    if (output / "browser_qa.json").is_file():
        artifact_outputs.append(
            {
                "path": "browser_qa.json",
                "kind": "json",
                "sha256": _sha256_file(output / "browser_qa.json"),
                "status": "checked",
            }
        )
    artifact_outputs.extend(_attribute_table_final_outputs(output, catalog))
    final_artifacts = {
        "schema_version": "attribute_reporting.final_artifacts.v1",
        "status": status,
        "report_id": model.get("report_id"),
        "correctness_verdict": verdict,
        "privacy": {
            "storage": "private_local_only",
            "uploaded_to_server": False,
        },
        "outputs": artifact_outputs,
    }
    _write_json(output / "final_artifacts.json", final_artifacts)
    return correctness


def validate_mapping_payloads(
    tasks: Mapping[str, Any],
    decisions: Mapping[str, Any],
    *,
    taxonomy: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Validate and normalize mapping payloads without writing them."""

    if tasks.get("schema_version") != MAPPING_TASK_SCHEMA:
        raise ContractError("Unsupported mapping task schema")
    if decisions.get("schema_version") != MAPPING_DECISION_SCHEMA:
        raise ContractError("Unsupported mapping decision schema")
    task_taxonomy = tasks.get("taxonomy_snapshot")
    decision_taxonomy = decisions.get("taxonomy_snapshot")
    if not isinstance(task_taxonomy, dict) or not isinstance(decision_taxonomy, dict):
        raise ContractError("Mapping artifacts require taxonomy_snapshot objects")
    for field in ("version", "sha256"):
        if not str(task_taxonomy.get(field) or "").strip():
            raise ContractError(f"Mapping task taxonomy snapshot requires {field}")
        if decision_taxonomy.get(field) != task_taxonomy.get(field):
            raise ContractError(
                f"Mapping decisions target a different taxonomy {field}"
            )
    taxonomy_attributes: dict[tuple[str, str], Mapping[str, Any]] = {}
    if taxonomy is not None:
        if str(taxonomy.get("version") or "") != str(
            task_taxonomy["version"]
        ) or _canonical_json_sha256(taxonomy) != str(task_taxonomy["sha256"]):
            raise ContractError(
                "Mapping tasks do not target the current central taxonomy"
            )
        for category in taxonomy.get("categories") or []:
            if not isinstance(category, dict):
                continue
            category_id = _normalise_mapping_token(category.get("id"))
            for attribute in category.get("attributes") or []:
                if not isinstance(attribute, dict):
                    continue
                attribute_id = str(attribute.get("id") or "").strip()
                if category_id and attribute_id:
                    taxonomy_attributes[(category_id, attribute_id)] = attribute
    agent = decisions.get("agent")
    if not isinstance(agent, dict) or agent.get("execution") != "codex_agent":
        raise ContractError("Mapping decisions must be authored by a Codex agent")
    if not str(agent.get("agent_id") or "").strip():
        raise ContractError("Mapping decision agent_id is required")

    raw_tasks = tasks.get("tasks")
    raw_decisions = decisions.get("decisions")
    if not isinstance(raw_tasks, list) or not isinstance(raw_decisions, list):
        raise ContractError("Mapping tasks and decisions must be lists")
    task_by_id: dict[str, Mapping[str, Any]] = {}
    task_scope = tasks.get("scope") if isinstance(tasks.get("scope"), dict) else {}
    scoped_retailer = str(task_scope.get("retailer") or "").strip()
    scoped_category = str(task_scope.get("category_key") or "").strip()
    snapshot_category = str(task_taxonomy.get("category_key") or "").strip()
    for task in raw_tasks:
        if not isinstance(task, dict):
            raise ContractError("Each mapping task must be an object")
        task_id = str(task.get("task_id") or "")
        if not SAFE_ID_RE.fullmatch(task_id) or task_id in task_by_id:
            raise ContractError(f"Invalid or duplicate mapping task id: {task_id!r}")
        product = task.get("product")
        if not isinstance(product, dict):
            raise ContractError(f"Mapping task {task_id} has no product object")
        row_type = str(product.get("row_type") or "parent")
        required_product_fields = (
            "retailer",
            "parent_product_id",
            "category_key",
        )
        if row_type not in {"parent", "variant"} or any(
            not str(product.get(field) or "").strip()
            for field in required_product_fields
        ):
            raise ContractError(
                f"Mapping task {task_id} has an incomplete product identity"
            )
        if row_type == "variant" and not str(product.get("variant_id") or "").strip():
            raise ContractError(f"Variant mapping task {task_id} requires variant_id")
        if (
            (scoped_retailer and product.get("retailer") != scoped_retailer)
            or (scoped_category and product.get("category_key") != scoped_category)
            or (snapshot_category and product.get("category_key") != snapshot_category)
        ):
            raise ContractError(
                f"Mapping task {task_id} falls outside its pinned scope"
            )
        attribute = task.get("attribute")
        if not isinstance(attribute, dict) or not isinstance(
            attribute.get("allowed_values"), list
        ):
            raise ContractError(
                f"Mapping task {task_id} has no allowed taxonomy values"
            )
        attribute_id = str(attribute.get("id") or "").strip()
        attribute_label = str(attribute.get("label") or "").strip()
        selection = str(attribute.get("selection") or "single").casefold()
        if (
            not attribute_id
            or not attribute_label
            or selection
            not in {
                "single",
                "multi",
            }
        ):
            raise ContractError(
                f"Mapping task {task_id} has invalid attribute metadata"
            )
        expected_task_id = _mapping_task_id(
            str(product["retailer"]),
            str(product["category_key"]),
            row_type,
            str(product["parent_product_id"]),
            str(product.get("variant_id") or ""),
            attribute_id,
        )
        if task_id != expected_task_id:
            raise ContractError(
                f"Mapping task {task_id} does not match its product and attribute identity"
            )
        if not re.fullmatch(
            r"[0-9a-f]{64}", str(product.get("source_row_sha256") or "")
        ):
            raise ContractError(
                f"Mapping task {task_id} requires a source-row checksum"
            )
        allowed_ids: set[str] = set()
        for value in attribute["allowed_values"]:
            if not isinstance(value, dict):
                raise ContractError(
                    f"Mapping task {task_id} has an invalid allowed value"
                )
            value_id = str(value.get("id") or "").strip()
            value_label = str(value.get("label") or "").strip()
            if not value_id or not value_label or value_id in allowed_ids:
                raise ContractError(
                    f"Mapping task {task_id} has empty or duplicate allowed values"
                )
            allowed_ids.add(value_id)
        if not allowed_ids:
            raise ContractError(
                f"Mapping task {task_id} has no allowed taxonomy values"
            )
        if taxonomy is not None:
            taxonomy_attribute = taxonomy_attributes.get(
                (
                    _normalise_mapping_token(product.get("category_key")),
                    attribute_id,
                )
            )
            if taxonomy_attribute is None:
                raise ContractError(
                    f"Mapping task {task_id} attribute is absent from the current taxonomy"
                )
            expected_values = _taxonomy_leaf_values(taxonomy_attribute.get("nodes"))
            if str(
                taxonomy_attribute.get("selection") or "single"
            ).casefold() != selection or expected_values != list(
                attribute["allowed_values"]
            ):
                raise ContractError(
                    f"Mapping task {task_id} allowed values differ from the current taxonomy"
                )
        task_by_id[task_id] = task

    decision_by_id: dict[str, Mapping[str, Any]] = {}
    selected_values_by_id: dict[str, tuple[list[str], list[str]]] = {}
    for decision in raw_decisions:
        if not isinstance(decision, dict):
            raise ContractError("Each mapping decision must be an object")
        task_id = str(decision.get("task_id") or "")
        if task_id not in task_by_id or task_id in decision_by_id:
            raise ContractError(
                f"Unknown or duplicate mapping decision task id: {task_id!r}"
            )
        status = str(decision.get("status") or "")
        if status not in {"mapped", "no_value", "oov_candidate", "unable_to_determine"}:
            raise ContractError(
                f"Mapping decision {task_id} has invalid status {status!r}"
            )
        if decision.get("confidence") not in {"high", "medium", "low"}:
            raise ContractError(f"Mapping decision {task_id} requires a confidence")
        if not str(decision.get("reason") or "").strip():
            raise ContractError(f"Mapping decision {task_id} requires a reason")
        task = task_by_id[task_id]
        allowed_values = {
            str(item.get("id")): str(item.get("label") or "")
            for item in task["attribute"]["allowed_values"]
            if isinstance(item, dict) and str(item.get("id") or "").strip()
        }
        selection = str(task["attribute"].get("selection") or "single").casefold()
        raw_value_ids = decision.get("value_ids")
        raw_value_labels = decision.get("value_labels")
        if raw_value_ids is None and raw_value_labels is None:
            value_id = str(decision.get("value_id") or "")
            value_label = str(decision.get("value_label") or "")
            value_ids = [value_id] if value_id else []
            value_labels = [value_label] if value_label else []
        elif isinstance(raw_value_ids, list) and isinstance(raw_value_labels, list):
            value_ids = [str(value or "").strip() for value in raw_value_ids]
            value_labels = [str(value or "").strip() for value in raw_value_labels]
        else:
            raise ContractError(
                f"Mapping decision {task_id} must set value_ids and value_labels together"
            )
        if status == "mapped":
            if (
                not value_ids
                or len(value_ids) != len(value_labels)
                or len(value_ids) != len(set(value_ids))
                or (selection == "single" and len(value_ids) != 1)
                or any(
                    value_id not in allowed_values
                    or value_label != allowed_values[value_id]
                    for value_id, value_label in zip(value_ids, value_labels)
                )
            ):
                raise ContractError(
                    f"Mapping decision {task_id} is not an exact value from the pinned taxonomy"
                )
            selected = set(value_ids)
            value_ids = [
                value_id for value_id in allowed_values if value_id in selected
            ]
            value_labels = [allowed_values[value_id] for value_id in value_ids]
        elif (
            value_ids
            or value_labels
            or str(decision.get("value_id") or "")
            or str(decision.get("value_label") or "")
        ):
            raise ContractError(
                f"Non-mapped decision {task_id} cannot set a taxonomy value"
            )
        if (
            status == "oov_candidate"
            and not str(decision.get("oov_candidate") or "").strip()
        ):
            raise ContractError(
                f"OOV mapping decision {task_id} requires oov_candidate"
            )
        decision_by_id[task_id] = decision
        selected_values_by_id[task_id] = (value_ids, value_labels)
    if set(decision_by_id) != set(task_by_id):
        missing = sorted(set(task_by_id) - set(decision_by_id))
        raise ContractError(
            f"Mapping decisions do not cover every task: missing={missing}"
        )

    validated_rows = []
    for task_id, task in task_by_id.items():
        decision = decision_by_id[task_id]
        product = task.get("product") if isinstance(task.get("product"), dict) else {}
        attribute = task["attribute"]
        value_ids, value_labels = selected_values_by_id[task_id]
        selection = str(attribute.get("selection") or "single").casefold()
        validated_rows.append(
            {
                "task_id": task_id,
                "retailer": product.get("retailer"),
                "row_type": product.get("row_type", "parent"),
                "parent_product_id": product.get("parent_product_id"),
                "variant_id": product.get("variant_id", ""),
                "category_key": product.get("category_key"),
                "attribute_id": attribute.get("id"),
                "attribute_label": attribute.get("label"),
                "selection": selection,
                "allowed_values": list(attribute["allowed_values"]),
                "status": decision.get("status"),
                "value_ids": value_ids,
                "value_labels": value_labels,
                "value_id": (
                    value_ids[0] if selection == "single" and value_ids else None
                ),
                "value_label": (
                    value_labels[0] if selection == "single" and value_labels else None
                ),
                "oov_candidate": decision.get("oov_candidate"),
                "reason": decision.get("reason"),
                "confidence": decision.get("confidence"),
                "source": "codex",
                "taxonomy_version": task_taxonomy["version"],
                "taxonomy_sha256": task_taxonomy["sha256"],
            }
        )
    stable_validation = {
        "schema_version": "attribute_reporting.validated_mapping_decisions.v1",
        "taxonomy_snapshot": dict(task_taxonomy),
        "agent": dict(agent),
        "tasks_sha256": _canonical_json_sha256(dict(tasks)),
        "decisions_sha256": _canonical_json_sha256(dict(decisions)),
        "status": "valid",
        "mapping_count": len(validated_rows),
        "mappings": validated_rows,
    }
    validated = {
        **stable_validation,
        "validated_at": _utc_now(),
        "validation_sha256": _canonical_json_sha256(stable_validation),
    }
    return validated


def validate_mapping_decisions(
    tasks_path: Path,
    decisions_path: Path,
    output_path: Path,
) -> dict[str, Any]:
    """Validate Codex mapping decisions against a pinned central taxonomy snapshot."""

    tasks = _load_json(tasks_path)
    decisions = _load_json(decisions_path)
    validated = validate_mapping_payloads(tasks, decisions)
    validation_output = output_path.expanduser().resolve()
    _assert_safe_output_dir(validation_output.parent)
    _write_json(validation_output, validated)
    return validated


def _stable_mapping_validation(payload: Mapping[str, Any]) -> dict[str, Any]:
    keys = (
        "schema_version",
        "taxonomy_snapshot",
        "agent",
        "tasks_sha256",
        "decisions_sha256",
        "status",
        "mapping_count",
        "mappings",
    )
    return {key: payload.get(key) for key in keys}


def _verify_validated_mapping_payload(
    tasks: Mapping[str, Any],
    decisions: Mapping[str, Any],
    validated: Mapping[str, Any],
    *,
    taxonomy: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Recompute the mechanical mapping contract before trusting its artifact."""

    expected = validate_mapping_payloads(tasks, decisions, taxonomy=taxonomy)
    if validated.get("schema_version") != VALIDATED_MAPPING_SCHEMA:
        raise ContractError("Unsupported validated mapping schema")
    if _stable_mapping_validation(validated) != _stable_mapping_validation(expected):
        raise ContractError(
            "Validated mappings do not match the supplied task and decision content"
        )
    if validated.get("validation_sha256") != expected["validation_sha256"]:
        raise ContractError("Validated mapping checksum does not match")
    return expected


def _mapping_review_targets(
    tasks: Mapping[str, Any],
    decisions: Mapping[str, Any],
    validated: Mapping[str, Any],
    expected: Mapping[str, Any],
) -> tuple[dict[str, Any], dict[str, dict[str, Any]]]:
    raw_tasks = tasks.get("tasks")
    raw_decisions = decisions.get("decisions")
    raw_mappings = validated.get("mappings")
    if not all(
        isinstance(items, list) for items in (raw_tasks, raw_decisions, raw_mappings)
    ):
        raise ContractError(
            "Mapping review inputs require task, decision, and mapping lists"
        )
    task_by_id = {
        str(item.get("task_id")): item for item in raw_tasks if isinstance(item, dict)
    }
    decision_by_id = {
        str(item.get("task_id")): item
        for item in raw_decisions
        if isinstance(item, dict)
    }
    mapping_by_id = {
        str(item.get("task_id")): item
        for item in raw_mappings
        if isinstance(item, dict)
    }
    task_ids = [
        str(item.get("task_id")) for item in raw_tasks if isinstance(item, dict)
    ]
    if not (
        len(task_ids) == len(task_by_id)
        and set(task_by_id) == set(decision_by_id) == set(mapping_by_id)
    ):
        raise ContractError(
            "Mapping review inputs do not share one exact task identity set"
        )
    author = expected.get("agent")
    mapping_coordinator_id = (
        str(author.get("agent_id") or "").strip() if isinstance(author, dict) else ""
    )
    if not SAFE_ID_RE.fullmatch(mapping_coordinator_id):
        raise ContractError("Mapping author agent_id is missing or invalid")

    global_targets = {
        "taxonomy_snapshot": dict(expected["taxonomy_snapshot"]),
        "tasks_sha256": str(expected["tasks_sha256"]),
        "decisions_sha256": str(expected["decisions_sha256"]),
        "validated_mappings_sha256": _canonical_json_sha256(dict(validated)),
        "validation_sha256": str(expected["validation_sha256"]),
        "mapping_content_sha256": _canonical_json_sha256(
            {
                "tasks": list(raw_tasks),
                "decisions": list(raw_decisions),
                "mappings": list(raw_mappings),
            }
        ),
    }
    per_task_targets: dict[str, dict[str, Any]] = {}
    for task_id in task_ids:
        task = task_by_id[task_id]
        decision = decision_by_id[task_id]
        product = task.get("product") if isinstance(task.get("product"), dict) else {}
        images = product.get("local_images")
        if images is None:
            images = []
        if not isinstance(images, list):
            raise ContractError(
                f"Mapping task {task_id} has invalid local image evidence"
            )
        image_sha256s = [
            str(item.get("sha256") or "") for item in images if isinstance(item, dict)
        ]
        if len(image_sha256s) != len(images):
            raise ContractError(
                f"Mapping task {task_id} has invalid local image evidence"
            )
        contributor_agent_id = str(decision.get("contributor_agent_id") or "").strip()
        if contributor_agent_id and not SAFE_ID_RE.fullmatch(contributor_agent_id):
            raise ContractError(
                f"Mapping task {task_id} has an invalid contributor agent id"
            )
        mapping_author_agent_ids = [mapping_coordinator_id]
        if contributor_agent_id and contributor_agent_id != mapping_coordinator_id:
            mapping_author_agent_ids.append(contributor_agent_id)
        mapping_author_agent_ids.sort()
        per_task_targets[task_id] = {
            "task_sha256": _canonical_json_sha256(dict(task)),
            "decision_sha256": _canonical_json_sha256(dict(decision)),
            "validated_mapping_sha256": _canonical_json_sha256(
                dict(mapping_by_id[task_id])
            ),
            "source_row_sha256": str(product.get("source_row_sha256") or ""),
            "local_image_sha256s": image_sha256s,
            "mapping_author_agent_ids": mapping_author_agent_ids,
        }
    return global_targets, per_task_targets


def create_mapping_review_template(
    tasks_path: Path,
    decisions_path: Path,
    validated_path: Path,
    output_path: Path,
    *,
    reviewer_agent_id: str,
) -> dict[str, Any]:
    """Prepare exact pins; an independent Codex reviewer authors the judgments."""

    if not reviewer_agent_id.strip():
        raise ContractError("Mapping reviewer_agent_id is required")
    tasks = _load_json(tasks_path)
    decisions = _load_json(decisions_path)
    validated = _load_json(validated_path)
    expected = _verify_validated_mapping_payload(tasks, decisions, validated)
    author = expected.get("agent")
    author_agent_id = (
        str(author.get("agent_id") or "") if isinstance(author, dict) else ""
    )
    if reviewer_agent_id == author_agent_id:
        raise ContractError(
            "Mapping reviewer must be different from the mapping author"
        )
    targets, per_task_targets = _mapping_review_targets(
        tasks,
        decisions,
        validated,
        expected,
    )
    review_id = f"mapping-review-{expected['validation_sha256'][:16]}"
    review = {
        "schema_version": MAPPING_REVIEW_SCHEMA,
        "review_id": review_id,
        "author_agent_id": author_agent_id,
        "reviewer": {
            "execution": "codex_agent",
            "agent_id": reviewer_agent_id,
            "role": "independent_mapping_reviewer",
            "tier": "low_cost",
            "independent_from_author": True,
        },
        "targets": targets,
        "overall_verdict": "unable_to_determine",
        "summary": "Independent semantic mapping review has not run.",
        "task_reviews": [
            {
                "task_id": task_id,
                "targets": task_targets,
                "verdict": "unable_to_determine",
                "reason": "This mapping has not been semantically reviewed.",
            }
            for task_id, task_targets in per_task_targets.items()
        ],
    }
    review_output = output_path.expanduser().resolve()
    _assert_safe_output_dir(review_output.parent)
    _write_json(review_output, review)
    return review


def validate_mapping_review_payloads(
    tasks: Mapping[str, Any],
    decisions: Mapping[str, Any],
    validated: Mapping[str, Any],
    review: Mapping[str, Any],
    *,
    taxonomy: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Enforce review integrity without making semantic mapping judgments.

    Exact hashes, identity separation, and coverage are deterministic because they
    are mechanically verifiable. The per-task verdicts and reasons remain the
    independent Codex reviewer's semantic judgment.
    """

    expected = _verify_validated_mapping_payload(
        tasks,
        decisions,
        validated,
        taxonomy=taxonomy,
    )
    if review.get("schema_version") != MAPPING_REVIEW_SCHEMA:
        raise ContractError("Unsupported mapping review schema")
    if not SAFE_ID_RE.fullmatch(str(review.get("review_id") or "")):
        raise ContractError("Mapping review_id is missing or invalid")
    author = expected.get("agent")
    author_agent_id = (
        str(author.get("agent_id") or "") if isinstance(author, dict) else ""
    )
    if review.get("author_agent_id") != author_agent_id:
        raise ContractError("Mapping review does not identify the mapping author")
    reviewer = review.get("reviewer")
    if not isinstance(reviewer, dict) or reviewer.get("execution") != "codex_agent":
        raise ContractError("Mapping review must be attributed to a Codex agent")
    reviewer_agent_id = str(reviewer.get("agent_id") or "").strip()
    if (
        not reviewer_agent_id
        or reviewer_agent_id == author_agent_id
        or reviewer.get("role") != "independent_mapping_reviewer"
        or reviewer.get("independent_from_author") is not True
    ):
        raise ContractError("Mapping reviewer is not independent from the author")
    if not str(review.get("summary") or "").strip():
        raise ContractError("Mapping review summary is required")

    expected_targets, per_task_targets = _mapping_review_targets(
        tasks,
        decisions,
        validated,
        expected,
    )
    if review.get("targets") != expected_targets:
        raise ContractError("Mapping review targets stale or different mapping content")
    task_reviews = review.get("task_reviews")
    if not isinstance(task_reviews, list):
        raise ContractError("Mapping review must contain a task_reviews list")
    review_by_id: dict[str, Mapping[str, Any]] = {}
    allowed_verdicts = {
        "supported",
        "supported_with_caveat",
        "unsupported",
        "unable_to_determine",
    }
    for item in task_reviews:
        if not isinstance(item, dict):
            raise ContractError("Each mapping task review must be an object")
        task_id = str(item.get("task_id") or "")
        if task_id not in per_task_targets or task_id in review_by_id:
            raise ContractError(
                f"Unknown or duplicate mapping review task id: {task_id!r}"
            )
        if item.get("targets") != per_task_targets[task_id]:
            raise ContractError(f"Mapping review task {task_id} has stale content pins")
        task_reviewer_ids = {reviewer_agent_id}
        contributor_agent_id = str(item.get("contributor_agent_id") or "").strip()
        if contributor_agent_id:
            if not SAFE_ID_RE.fullmatch(contributor_agent_id):
                raise ContractError(
                    f"Mapping review task {task_id} has an invalid contributor agent id"
                )
            task_reviewer_ids.add(contributor_agent_id)
        mapping_author_agent_ids = set(
            per_task_targets[task_id]["mapping_author_agent_ids"]
        )
        if task_reviewer_ids & mapping_author_agent_ids:
            raise ContractError(
                f"Mapping review task {task_id} is not independent from its authors"
            )
        if item.get("verdict") not in allowed_verdicts:
            raise ContractError(f"Mapping review task {task_id} has an invalid verdict")
        if not str(item.get("reason") or "").strip():
            raise ContractError(f"Mapping review task {task_id} requires a reason")
        review_by_id[task_id] = item
    if set(review_by_id) != set(per_task_targets):
        missing = sorted(set(per_task_targets) - set(review_by_id))
        raise ContractError(
            f"Mapping review must cover every task exactly once: missing={missing}"
        )

    verdict_counts = {verdict: 0 for verdict in sorted(allowed_verdicts)}
    for item in review_by_id.values():
        verdict_counts[str(item["verdict"])] += 1
    if verdict_counts["unsupported"]:
        review_state = "rejected"
    elif verdict_counts["unable_to_determine"]:
        review_state = "unable_to_determine"
    elif verdict_counts["supported_with_caveat"]:
        review_state = "approved_with_caveats"
    else:
        review_state = "approved"
    if review.get("overall_verdict") != review_state:
        raise ContractError(
            "Mapping review overall_verdict does not match its per-task verdicts"
        )

    findings = [
        {
            "task_id": task_id,
            "verdict": str(item["verdict"]),
            "reason": str(item["reason"]).strip(),
        }
        for task_id, item in review_by_id.items()
        if item.get("verdict") != "supported"
    ]
    stable_validation = {
        "schema_version": MAPPING_REVIEW_VALIDATION_SCHEMA,
        "status": "valid",
        "review_state": review_state,
        "review_id": review.get("review_id"),
        "author_agent_id": author_agent_id,
        "reviewer": dict(reviewer),
        "summary": str(review.get("summary") or "").strip(),
        "targets": expected_targets,
        "task_count": len(review_by_id),
        "task_verdict_counts": verdict_counts,
        "findings": findings,
        "mapping_review_sha256": _canonical_json_sha256(dict(review)),
    }
    return {
        **stable_validation,
        "validated_at": _utc_now(),
        "review_validation_sha256": _canonical_json_sha256(stable_validation),
    }


def validate_mapping_review(
    tasks_path: Path,
    decisions_path: Path,
    validated_path: Path,
    review_path: Path,
    output_path: Path,
) -> dict[str, Any]:
    """Validate an independent semantic mapping review and write its receipt."""

    validation = validate_mapping_review_payloads(
        _load_json(tasks_path),
        _load_json(decisions_path),
        _load_json(validated_path),
        _load_json(review_path),
    )
    validation_output = output_path.expanduser().resolve()
    _assert_safe_output_dir(validation_output.parent)
    _write_json(validation_output, validation)
    return validation
