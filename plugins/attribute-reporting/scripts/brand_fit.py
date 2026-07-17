#!/usr/bin/env python3
"""Local, hash-bound Brand Fit preparation, rendering, review, and checking.

The server supplies structured Brand Fit evidence only.  The checked Retailer
Signals report, hydrated image bytes, authored HTML, and semantic review stay in
the local workspace.  This module performs no model or provider API calls.
"""

from __future__ import annotations

import csv
import hashlib
import html
import io
import json
import os
import re
import shutil
import uuid
from collections.abc import Mapping, Sequence
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

__all__ = [
    "BrandFitContractError",
    "check_brand_fit_report",
    "completed_retailer_report",
    "prepare_brand_fit_run",
    "render_brand_fit_report",
]

CATALOG_SCHEMA = "attribute_reporting.brand_fit_evidence_catalog.v1"
MODEL_SCHEMA = "attribute_reporting.brand_fit_report_model.v1"
REVIEW_SCHEMA = "attribute_reporting.brand_fit_semantic_review.v1"
RENDER_SCHEMA = "attribute_reporting.brand_fit_render_manifest.v1"
VERDICT_SCHEMA = "attribute_reporting.brand_fit_correctness_verdict.v1"
FINAL_SCHEMA = "attribute_reporting.brand_fit_final_artifacts.v1"
IMAGE_MANIFEST_SCHEMA = "attribute_reporting.local_image_manifest.v1"
SAFE_ID_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}")
SHA256_RE = re.compile(r"[0-9a-f]{64}")
TOKEN_RE = re.compile(r"\{\{([A-Za-z0-9_.:-]+)\.([A-Za-z0-9_:-]+)\}\}")
NUMBER_RE = re.compile(r"(?<![A-Za-z])\d+(?:[.,]\d+)?%?")
VERDICT_PLACEHOLDER = (
    '<div class="verdict pending" data-correctness-verdict="pending">'
    '<span class="mark">?</span><div><strong>Correctness pending</strong>'
    "<p>Independent review and mechanical checks have not finished.</p></div></div>"
)
SOURCE_RETAILER_VERDICT_PLACEHOLDER = (
    "<!-- ATTRIBUTE_REPORTING_VERDICT -->"
    '<aside class="verdict unable_to_determine provisional" '
    'data-correctness-verdict="pending">'
    '<span class="mark">?</span><div><strong>Correctness review pending</strong>'
    "<span>The final evidence-backed verdict will replace this banner after "
    "independent semantic review and browser QA.</span></div></aside>"
)

SECTION_IDS = (
    "executive_summary",
    "retailer_signals",
    "current_retailer_presence",
    "owned_catalogue",
    "brand_fit_opportunities",
    "method_and_caveats",
)
REVIEW_DIMENSIONS = (
    "source_fidelity",
    "retailer_signal_calibration",
    "current_presence_interpretation",
    "owned_catalogue_interpretation",
    "candidate_relevance",
    "caveat_handling",
    "html_readability",
)
EVIDENCE_FILES = (
    "signal_bundles.csv",
    "plain_language_signal_guide.csv",
    "attribute_coverage.csv",
    "retailer_brand_anchors.csv",
    "retailer_brand_anchor_signal_fit.csv",
    "retailer_live_presence_audit.csv",
    "brand_at_retailer_review_validation.csv",
    "brand_at_retailer_bundle_matches.csv",
    "manufacturer_catalog_products.csv",
    "manufacturer_products_not_at_retailer.csv",
    "manufacturer_catalog_bundle_matches.csv",
    "reference_candidates.csv",
    "image_index.csv",
)
PRODUCT_FILES = frozenset(
    {
        "retailer_brand_anchors.csv",
        "manufacturer_catalog_products.csv",
        "manufacturer_products_not_at_retailer.csv",
        "reference_candidates.csv",
    }
)
BRAND_FIT_IMAGE_SOURCE_FILES = (
    "retailer_brand_anchors.csv",
    "manufacturer_catalog_products.csv",
    "manufacturer_products_not_at_retailer.csv",
    "reference_candidates.csv",
)
IMAGE_SUFFIXES = frozenset({".png", ".jpg", ".jpeg", ".webp", ".gif", ".avif"})
SERVER_PORTABLE_SUFFIXES = frozenset({".csv", ".json", ".md", ".txt", ".html"})
PRIVATE_SERVER_PATH_RE = re.compile(
    r"/(?:srv|home|root|users|var|private|tmp|etc)/|pdp_store\.sqlite",
    flags=re.IGNORECASE,
)
UNSAFE_PORTABLE_MARKERS = (
    "data:image/",
    "blob:",
    "iVBORw0KGgo",
    "/9j/",
)
PRIVATE_URI_RE = re.compile(
    r"(?:postgres(?:ql)?|mysql|mariadb|mongodb|redis|sqlite)://|"
    r"database_url\s*=|file:(?://|/)",
    flags=re.IGNORECASE,
)
EMBEDDED_IMAGE_FIELDS = frozenset(
    {
        "image_base64",
        "base64_image",
        "image_blob",
        "image_bytes",
        "image_data",
        "image_data_uri",
    }
)
TABLE_KEYS = {
    "retailer_signals": "signal_bundles.csv",
    "current_retailer_presence": "retailer_brand_anchors.csv",
    "owned_catalogue": "manufacturer_catalog_products.csv",
    "brand_fit_candidates": "reference_candidates.csv",
}
SCOPE_METRICS_FILE = "brand_fit_scope_metrics.csv"
REQUIRED_EVIDENCE_SCOPES = frozenset(
    {"retailer_signals", "current_retailer_presence", "owned_catalogue"}
)
REQUIRED_PRODUCT_CACHE_ENTRIES = (
    "parent_filtered",
    "variant_result",
    "combined",
    "parents_all",
)
MAPPING_STATE_SCHEMA = (
    "attribute_reporting.server_bridge.brand_fit_mapping_state_snapshot.v1"
)
MAPPING_SCOPE_SCHEMA = "attribute_reporting.server_bridge.mapping_state_snapshot.v1"
MAPPING_IDENTITY_ORDER = (
    "source",
    "retailer",
    "row_type",
    "parent_product_id",
    "variant_id",
    "category_key",
    "base_attribute_id",
)
MAPPING_IDENTITY_FIELDS = frozenset(MAPPING_IDENTITY_ORDER)
MAPPING_ROW_FIELDS = frozenset(
    {
        "attribute_id",
        "attribute_label",
        "value",
        "oov_candidate",
        "note",
        "updated_at",
    }
)
SOURCE_REVIEW_DIMENSIONS = (
    "claim_coverage",
    "story_coherence",
    "importance_calibration",
    "caveat_handling",
    "brand_and_example_interpretation",
    "html_readability",
)
SECTION_TABLE_KEYS = {
    "retailer_signals": frozenset({"retailer_signals"}),
    "current_retailer_presence": frozenset({"current_retailer_presence"}),
    "owned_catalogue": frozenset({"owned_catalogue"}),
    "brand_fit_opportunities": frozenset({"brand_fit_candidates"}),
}
PRODUCT_SOURCE_ROLES = {
    "retailer_brand_anchors.csv": "current_presence",
    "manufacturer_catalog_products.csv": "owned_catalogue",
    "manufacturer_products_not_at_retailer.csv": "owned_catalogue",
    "reference_candidates.csv": "candidate",
}


class BrandFitContractError(ValueError):
    """Raised when Brand Fit evidence or a local artifact breaks its contract."""


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _canonical_sha256(payload: Any) -> str:
    encoded = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _load_json(path: Path, *, label: str = "JSON artifact") -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise BrandFitContractError(f"Cannot read {label}: {path}") from exc
    if not isinstance(payload, dict):
        raise BrandFitContractError(f"{label} must be a JSON object: {path}")
    return payload


def _write_json(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
    try:
        temporary.write_text(
            json.dumps(dict(payload), ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        os.chmod(temporary, 0o600)
        temporary.replace(path)
    finally:
        temporary.unlink(missing_ok=True)


def _contains_nonempty_embedded_image_field(value: Any, *, key: str = "") -> bool:
    """Reject image-byte fields only when sanitization left a nonempty value."""

    if key.casefold() in EMBEDDED_IMAGE_FIELDS and value not in (None, "", [], {}):
        return True
    if isinstance(value, Mapping):
        return any(
            _contains_nonempty_embedded_image_field(child, key=str(child_key))
            for child_key, child in value.items()
        )
    if isinstance(value, list):
        return any(_contains_nonempty_embedded_image_field(child) for child in value)
    return False


def _portable_file_has_embedded_image_field(path: Path, text: str) -> bool:
    suffix = path.suffix.casefold()
    if suffix == ".json":
        try:
            payload = json.loads(text)
        except json.JSONDecodeError as exc:
            raise BrandFitContractError(
                f"Server Brand Fit package contains invalid JSON: {path.name}"
            ) from exc
        return _contains_nonempty_embedded_image_field(payload)
    if suffix == ".csv":
        try:
            reader = csv.DictReader(io.StringIO(text))
            return any(
                str(value or "").strip()
                for row in reader
                for field, value in row.items()
                if str(field or "").casefold() in EMBEDDED_IMAGE_FIELDS
            )
        except csv.Error as exc:
            raise BrandFitContractError(
                f"Server Brand Fit package contains invalid CSV: {path.name}"
            ) from exc
    return False


def _safe_relative(value: str, *, label: str) -> Path:
    path = Path(value)
    if not value or path.is_absolute() or ".." in path.parts:
        raise BrandFitContractError(f"Unsafe {label}: {value!r}")
    return path


def _contained(root: Path, relative: str, *, label: str) -> Path:
    path = (root / _safe_relative(relative, label=label)).resolve()
    if not path.is_relative_to(root.resolve()):
        raise BrandFitContractError(f"{label} escapes its local root")
    return path


def _read_csv(path: Path) -> tuple[list[str], list[dict[str, str]]]:
    try:
        with path.open("r", encoding="utf-8-sig", newline="") as handle:
            reader = csv.DictReader(handle)
            if reader.fieldnames is None:
                raise BrandFitContractError(f"CSV has no header: {path}")
            fields = [str(field) for field in reader.fieldnames]
            rows = [
                {str(key): str(value or "") for key, value in row.items()}
                for row in reader
            ]
    except OSError as exc:
        raise BrandFitContractError(f"Cannot read CSV: {path}") from exc
    return fields, rows


def _write_csv(path: Path, rows: Sequence[Mapping[str, Any]]) -> None:
    if not rows:
        raise BrandFitContractError(f"Cannot write a headerless CSV: {path}")
    fields = [str(field) for field in rows[0]]
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
    try:
        with temporary.open("w", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=fields)
            writer.writeheader()
            writer.writerows(rows)
        os.chmod(temporary, 0o600)
        temporary.replace(path)
    finally:
        temporary.unlink(missing_ok=True)


def _row_sha256(row: Mapping[str, str]) -> str:
    return _canonical_sha256(dict(row))


def _copy_file(source: Path, destination: Path) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_name(f".{destination.name}.{uuid.uuid4().hex}.tmp")
    try:
        shutil.copyfile(source, temporary)
        os.chmod(temporary, 0o600)
        temporary.replace(destination)
    finally:
        temporary.unlink(missing_ok=True)


def completed_retailer_report(run_dir: Path) -> dict[str, str]:
    """Validate and identify a completed local Retailer Signals report.

    The report itself is never returned as request data.  Only its SHA-256 and
    one of the two admissible completed verdict labels cross the bridge.
    """

    run = run_dir.expanduser().resolve()
    final_path = run / "final_artifacts.json"
    correctness_path = run / "correctness_verdict.json"
    report_path = run / "report.html"
    download_receipt_path = run / "local_download_receipt.json"
    catalog_path = run / "evidence_catalog.json"
    if not run.is_dir() or not all(
        path.is_file() for path in (final_path, correctness_path, report_path)
    ):
        raise BrandFitContractError(
            "Retailer Signals run requires final_artifacts.json, "
            "correctness_verdict.json, and report.html"
        )
    final = _load_json(final_path, label="Retailer Signals final artifacts")
    correctness = _load_json(
        correctness_path, label="Retailer Signals correctness verdict"
    )
    if final.get("schema_version") != "attribute_reporting.final_artifacts.v1":
        raise BrandFitContractError("Unsupported Retailer Signals final schema")
    if final.get("status") != "final_ready":
        raise BrandFitContractError("Retailer Signals report is not final_ready")
    privacy = final.get("privacy")
    if not isinstance(privacy, dict) or (
        privacy.get("storage") != "private_local_only"
        or privacy.get("uploaded_to_server") is not False
    ):
        raise BrandFitContractError(
            "Retailer Signals report privacy contract is invalid"
        )
    verdict_key = str(correctness.get("verdict") or "")
    if verdict_key not in {"correct", "correct_with_caveats"}:
        raise BrandFitContractError(
            "Retailer Signals verdict must be Correct or Correct with caveats"
        )
    if final.get("correctness_verdict") != verdict_key:
        raise BrandFitContractError(
            "Retailer Signals final artifacts and correctness verdict disagree"
        )
    outputs = final.get("outputs")
    if not isinstance(outputs, list):
        raise BrandFitContractError("Retailer Signals output manifest is invalid")
    report_records = [
        item
        for item in outputs
        if isinstance(item, dict) and item.get("path") == "report.html"
    ]
    if len(report_records) != 1:
        raise BrandFitContractError(
            "Retailer Signals report.html is not uniquely listed"
        )
    actual_sha = _sha256_file(report_path)
    if report_records[0].get("sha256") != actual_sha:
        raise BrandFitContractError("Retailer Signals report.html hash is stale")
    correctness_records = [
        item
        for item in outputs
        if isinstance(item, dict) and item.get("path") == "correctness_verdict.json"
    ]
    if len(correctness_records) != 1 or correctness_records[0].get(
        "sha256"
    ) != _sha256_file(correctness_path):
        raise BrandFitContractError(
            "Retailer Signals correctness verdict is not hash-pinned"
        )
    if f'data-correctness-verdict="{verdict_key}"' not in report_path.read_text(
        encoding="utf-8"
    ):
        raise BrandFitContractError(
            "Retailer Signals HTML does not carry its checked verdict"
        )
    _validate_completed_retailer_lineage(
        run,
        correctness=correctness,
        final=final,
        report_path=report_path,
        verdict_key=verdict_key,
    )
    if not download_receipt_path.is_file() or not catalog_path.is_file():
        raise BrandFitContractError(
            "Retailer Signals run has no hash-pinned server download receipt"
        )
    receipt = _load_json(
        download_receipt_path, label="Retailer Signals download receipt"
    )
    source_catalog = _load_json(catalog_path, label="Retailer Signals evidence catalog")
    lineage = source_catalog.get("transport_lineage")
    artifacts = lineage.get("artifacts") if isinstance(lineage, dict) else None
    if not isinstance(artifacts, dict) or artifacts.get(
        "local_download_receipt.json"
    ) != _sha256_file(download_receipt_path):
        raise BrandFitContractError(
            "Retailer Signals download receipt is not pinned by its evidence catalog"
        )
    job_id = str(receipt.get("job_id") or "").strip()
    archive_sha256 = str(receipt.get("sha256") or "")
    download = lineage.get("download") if isinstance(lineage, dict) else None
    if (
        not re.fullmatch(r"[0-9a-f]{32}", job_id)
        or not SHA256_RE.fullmatch(archive_sha256)
        or not isinstance(download, dict)
        or download.get("job_id") != job_id
        or download.get("archive_sha256") != archive_sha256
    ):
        raise BrandFitContractError(
            "Retailer Signals evidence job identity is missing or inconsistent"
        )
    return {
        "path": str(report_path),
        "sha256": actual_sha,
        "verdict": ("Correct" if verdict_key == "correct" else "Correct with caveats"),
        "job_id": job_id,
        "package_sha256": archive_sha256,
    }


def _source_semantic_review_state(
    review: Mapping[str, Any],
    *,
    model: Mapping[str, Any],
    render: Mapping[str, Any],
) -> str:
    """Recompute the completed Retailer Signals semantic-review state."""

    author = model.get("author")
    reviewer = review.get("reviewer")
    targets = review.get("targets")
    expected_targets = {
        "report_id": model.get("report_id"),
        "evidence_catalog_sha256": render.get("evidence_catalog_sha256"),
        "report_model_sha256": render.get("report_model_sha256"),
        "draft_html_sha256": render.get("draft_html_sha256"),
    }
    if (
        review.get("schema_version") != "attribute_reporting.semantic_review.v1"
        or not SAFE_ID_RE.fullmatch(str(review.get("review_id") or ""))
        or not isinstance(author, dict)
        or not isinstance(reviewer, dict)
        or reviewer.get("execution") != "codex_agent"
        or reviewer.get("role") != "independent_reviewer"
        or reviewer.get("independent_from_author") is not True
        or not str(reviewer.get("agent_id") or "").strip()
        or reviewer.get("agent_id") == author.get("agent_id")
        or review.get("author_agent_id") != author.get("agent_id")
        or targets != expected_targets
        or not str(review.get("summary") or "").strip()
    ):
        raise BrandFitContractError(
            "Retailer Signals semantic review identity or targets are invalid"
        )
    statuses: list[str] = []
    dimensions = review.get("dimensions")
    if not isinstance(dimensions, dict) or set(dimensions) != set(
        SOURCE_REVIEW_DIMENSIONS
    ):
        raise BrandFitContractError(
            "Retailer Signals semantic review dimensions are incomplete"
        )
    for dimension in SOURCE_REVIEW_DIMENSIONS:
        item = dimensions[dimension]
        if (
            not isinstance(item, dict)
            or item.get("status")
            not in {"pass", "caveat", "fail", "unable_to_determine"}
            or not str(item.get("rationale") or "").strip()
        ):
            raise BrandFitContractError(
                f"Retailer Signals semantic dimension is invalid: {dimension}"
            )
        statuses.append(str(item["status"]))
    raw_claims = model.get("claims")
    claim_reviews = review.get("claim_reviews")
    if not isinstance(raw_claims, list) or not isinstance(claim_reviews, list):
        raise BrandFitContractError("Retailer Signals semantic claim review is invalid")
    claim_ids = [
        str(item.get("claim_id") or "") if isinstance(item, dict) else ""
        for item in raw_claims
    ]
    reviewed_claim_ids = [
        str(item.get("claim_id") or "") if isinstance(item, dict) else ""
        for item in claim_reviews
    ]
    if (
        any(not SAFE_ID_RE.fullmatch(claim_id) for claim_id in claim_ids)
        or len(set(claim_ids)) != len(claim_ids)
        or sorted(reviewed_claim_ids) != sorted(claim_ids)
        or len(set(reviewed_claim_ids)) != len(reviewed_claim_ids)
    ):
        raise BrandFitContractError(
            "Retailer Signals semantic review does not cover every claim"
        )
    claim_state = {
        "supported": "pass",
        "supported_with_caveat": "caveat",
        "unsupported": "fail",
        "unable_to_determine": "unable_to_determine",
    }
    for item in claim_reviews:
        if (
            not isinstance(item, dict)
            or item.get("verdict") not in claim_state
            or not str(item.get("reason") or "").strip()
        ):
            raise BrandFitContractError(
                "Retailer Signals semantic claim review is invalid"
            )
        statuses.append(claim_state[str(item["verdict"])])
    report_findings = review.get("report_level_findings")
    if not isinstance(report_findings, list):
        raise BrandFitContractError(
            "Retailer Signals semantic report findings are invalid"
        )
    finding_codes: set[str] = set()
    for item in report_findings:
        if (
            not isinstance(item, dict)
            or not SAFE_ID_RE.fullmatch(str(item.get("code") or ""))
            or str(item.get("code")) in finding_codes
            or item.get("status") not in {"caveat", "fail", "unable_to_determine"}
            or not str(item.get("finding") or "").strip()
        ):
            raise BrandFitContractError(
                "Retailer Signals semantic report finding is invalid"
            )
        finding_codes.add(str(item["code"]))
        statuses.append(str(item["status"]))
    featured = render.get("featured_products") or []
    images_reviewed = review.get("images_reviewed")
    if not isinstance(featured, list) or not isinstance(images_reviewed, list):
        raise BrandFitContractError("Retailer Signals semantic image review is invalid")
    expected_images = {
        str(item.get("product_id") or ""): item
        for item in featured
        if isinstance(item, dict) and item.get("image_path")
    }
    actual_images: dict[str, Mapping[str, Any]] = {}
    for item in images_reviewed:
        product_id = str(item.get("product_id") or "") if isinstance(item, dict) else ""
        expected = expected_images.get(product_id)
        if (
            not isinstance(item, dict)
            or expected is None
            or product_id in actual_images
            or item.get("image_path") != expected.get("image_path")
            or item.get("image_sha256") != expected.get("image_sha256")
            or item.get("status")
            not in {"pass", "caveat", "fail", "unable_to_determine"}
            or not str(item.get("observation") or "").strip()
        ):
            raise BrandFitContractError(
                "Retailer Signals semantic image review is invalid"
            )
        actual_images[product_id] = item
        statuses.append(str(item["status"]))
    if set(actual_images) != set(expected_images):
        raise BrandFitContractError(
            "Retailer Signals semantic review does not cover every local image"
        )
    overall = str(review.get("overall_verdict") or "")
    overall_status = {
        "correct": "pass",
        "correct_with_caveats": "caveat",
        "incorrect": "fail",
        "unable_to_determine": "unable_to_determine",
    }.get(overall)
    if overall_status is None:
        raise BrandFitContractError(
            "Retailer Signals semantic overall verdict is invalid"
        )
    statuses.append(overall_status)
    derived = (
        "incorrect"
        if "fail" in statuses
        else (
            "unable_to_determine"
            if "unable_to_determine" in statuses
            else "correct_with_caveats" if "caveat" in statuses else "correct"
        )
    )
    if overall != derived:
        raise BrandFitContractError(
            "Retailer Signals semantic overall verdict is inconsistent"
        )
    return derived


def _source_mapping_review_state(
    run: Path, correctness: Mapping[str, Any], state: str
) -> None:
    """Validate source mapping-review hashes when the source run used mappings."""

    if state == "not_applicable":
        if (
            correctness.get("mapping_review_sha256") is not None
            or correctness.get("mapping_review_validation_sha256") is not None
        ):
            raise BrandFitContractError(
                "Retailer Signals mapping-review basis is inconsistent"
            )
        return
    review_path = run / "mapping_review.json"
    validation_path = run / "mapping_review_validation.json"
    if not review_path.is_file() or not validation_path.is_file():
        raise BrandFitContractError(
            "Retailer Signals mapping-review artifacts are missing"
        )
    review = _load_json(review_path, label="source mapping review")
    validation = _load_json(validation_path, label="source mapping review validation")
    allowed_review_states = {
        "correct": {"approved"},
        # Scope/coverage findings can caveat an otherwise approved mapping review.
        "correct_with_caveats": {"approved", "approved_with_caveats"},
    }[state]
    stable_validation = {
        key: value
        for key, value in validation.items()
        if key not in {"validated_at", "review_validation_sha256"}
    }
    if (
        validation.get("schema_version")
        != "attribute_reporting.mapping_review_validation.v1"
        or validation.get("status") != "valid"
        or validation.get("review_state") not in allowed_review_states
        or validation.get("mapping_review_sha256") != _canonical_sha256(review)
        or validation.get("review_validation_sha256")
        != _canonical_sha256(stable_validation)
        or correctness.get("mapping_review_sha256")
        != validation.get("mapping_review_sha256")
        or correctness.get("mapping_review_validation_sha256")
        != validation.get("review_validation_sha256")
    ):
        raise BrandFitContractError("Retailer Signals mapping-review hashes are stale")


def _source_browser_qa_state(
    run: Path,
    correctness: Mapping[str, Any],
    render: Mapping[str, Any],
    state: str,
) -> None:
    """Validate source browser evidence when the source run required it."""

    path = run / "browser_qa.json"
    if state == "not_applicable":
        if correctness.get("browser_qa_sha256") is not None or path.is_file():
            raise BrandFitContractError(
                "Retailer Signals browser-QA basis is inconsistent"
            )
        return
    if not path.is_file():
        raise BrandFitContractError("Retailer Signals browser QA is missing")
    qa = _load_json(path, label="source browser QA")
    expected_targets = {
        "draft_html": str((run / "report_draft.html").resolve()),
        "draft_html_sha256": render.get("draft_html_sha256"),
        "render_manifest_sha256": _sha256_file(run / "render_manifest.json"),
    }
    if (
        qa.get("schema_version") != "attribute_reporting.browser_qa.v1"
        or qa.get("report_id") != render.get("report_id")
        or qa.get("targets") != expected_targets
        or qa.get("status") != "pass"
        or str(qa.get("browser_error") or "")
        or correctness.get("browser_qa_sha256") != _canonical_sha256(qa)
    ):
        raise BrandFitContractError("Retailer Signals browser QA is stale")
    viewports = qa.get("viewports")
    expected_sizes = {"desktop": (1440, 1000), "mobile": (390, 844)}
    if not isinstance(viewports, list) or len(viewports) != 2:
        raise BrandFitContractError("Retailer Signals browser QA is incomplete")
    flattened: list[dict[str, Any]] = []
    seen: set[str] = set()
    for viewport in viewports:
        if not isinstance(viewport, dict):
            raise BrandFitContractError("Retailer Signals browser viewport is invalid")
        name = str(viewport.get("name") or "")
        screenshot = _contained(
            run,
            str(viewport.get("screenshot") or ""),
            label="source browser screenshot",
        )
        findings = viewport.get("findings")
        metrics = viewport.get("metrics")
        expected_codes = {
            f"browser.{name}.{suffix}"
            for suffix in (
                "horizontal_overflow",
                "local_images",
                "asset_locality",
                "table_scrolling",
                "required_elements",
                "product_links",
                "runtime",
            )
        }
        if (
            name in seen
            or expected_sizes.get(name)
            != (viewport.get("width"), viewport.get("height"))
            or not screenshot.is_file()
            or _sha256_file(screenshot) != viewport.get("screenshot_sha256")
            or not isinstance(metrics, dict)
            or not isinstance(findings, list)
            or len(findings) != len(expected_codes)
            or {
                str(item.get("code") or "")
                for item in findings
                if isinstance(item, dict)
            }
            != expected_codes
            or any(
                not isinstance(item, dict)
                or item.get("status") != "pass"
                or not str(item.get("message") or "").strip()
                for item in findings
            )
            or any(
                bool(metrics.get(key))
                for key in (
                    "horizontalOverflow",
                    "brokenImages",
                    "unsafeAssets",
                    "uncontainedWideTables",
                    "missingRequiredElements",
                    "unsafeProductLinks",
                )
            )
            or next(
                item
                for item in findings
                if item.get("code") == f"browser.{name}.runtime"
            ).get("details")
            not in ([], None)
        ):
            raise BrandFitContractError("Retailer Signals browser viewport is invalid")
        seen.add(name)
        flattened.extend(dict(item) for item in findings)
    if seen != set(expected_sizes) or qa.get("findings") != flattened:
        raise BrandFitContractError(
            "Retailer Signals browser findings are inconsistent"
        )


def _validate_completed_retailer_lineage(
    run: Path,
    *,
    correctness: Mapping[str, Any],
    final: Mapping[str, Any],
    report_path: Path,
    verdict_key: str,
) -> None:
    """Recheck the existing Retailer Signals render and correctness hash chain."""

    required = {
        "evidence_catalog.json",
        "report_model.json",
        "claim_ledger.json",
        "render_manifest.json",
        "report_draft.html",
        "semantic_review.json",
    }
    missing = sorted(name for name in required if not (run / name).is_file())
    if missing:
        raise BrandFitContractError(
            "Retailer Signals checked-artifact lineage is incomplete: "
            + ", ".join(missing)
        )
    catalog = _load_json(run / "evidence_catalog.json", label="source evidence catalog")
    model = _load_json(run / "report_model.json", label="source report model")
    ledger = _load_json(run / "claim_ledger.json", label="source claim ledger")
    render = _load_json(run / "render_manifest.json", label="source render manifest")
    review = _load_json(run / "semantic_review.json", label="source semantic review")
    draft_path = run / "report_draft.html"
    report_id = str(model.get("report_id") or "")
    if (
        catalog.get("schema_version") != "attribute_reporting.evidence_catalog.v1"
        or model.get("schema_version") != "attribute_reporting.report_model.v1"
        or ledger.get("schema_version") != "attribute_reporting.claim_ledger.v1"
        or correctness.get("schema_version")
        != "attribute_reporting.correctness_verdict.v1"
        or final.get("schema_version") != "attribute_reporting.final_artifacts.v1"
        or not SAFE_ID_RE.fullmatch(report_id)
        or any(
            artifact.get("report_id") != report_id
            for artifact in (catalog, ledger, render, correctness, final)
        )
    ):
        raise BrandFitContractError(
            "Retailer Signals checked-artifact schemas or report ids are inconsistent"
        )
    expected = {
        "evidence_catalog_sha256": _canonical_sha256(catalog),
        "report_model_sha256": _canonical_sha256(model),
        "claim_ledger_sha256": _canonical_sha256(ledger),
        "draft_html_sha256": _sha256_file(draft_path),
    }
    if (
        render.get("schema_version") != "attribute_reporting.render_manifest.v1"
        or render.get("draft_html") != "report_draft.html"
        or any(render.get(key) != value for key, value in expected.items())
    ):
        raise BrandFitContractError("Retailer Signals render lineage is stale")
    if (
        correctness.get("report_model_sha256") != expected["report_model_sha256"]
        or correctness.get("draft_html_sha256") != expected["draft_html_sha256"]
    ):
        raise BrandFitContractError("Retailer Signals correctness hashes are stale")
    if correctness.get("semantic_review_sha256") != _canonical_sha256(review):
        raise BrandFitContractError("Retailer Signals semantic review hash is stale")
    if correctness.get("mechanical_findings") != []:
        raise BrandFitContractError(
            "Retailer Signals mechanical findings are not clean"
        )
    basis = correctness.get("basis")
    if (
        not isinstance(basis, dict)
        or set(basis)
        != {
            "package_integrity",
            "mechanical_claims",
            "html_parity",
            "mapping_review",
            "browser_qa",
            "semantic_review",
        }
        or basis.get("package_integrity") != "pass"
        or basis.get("mechanical_claims") != "pass"
        or basis.get("html_parity") != "pass"
        or basis.get("mapping_review")
        not in {"not_applicable", "correct", "correct_with_caveats"}
        or basis.get("browser_qa") not in {"not_applicable", "correct"}
        or basis.get("semantic_review") not in {"correct", "correct_with_caveats"}
    ):
        raise BrandFitContractError("Retailer Signals correctness basis is not clean")
    semantic_state = _source_semantic_review_state(review, model=model, render=render)
    if semantic_state != basis.get("semantic_review"):
        raise BrandFitContractError(
            "Retailer Signals semantic review and correctness basis disagree"
        )
    _source_mapping_review_state(run, correctness, str(basis["mapping_review"]))
    _source_browser_qa_state(run, correctness, render, str(basis["browser_qa"]))
    active_warnings = correctness.get("active_warning_codes")
    caveats = correctness.get("caveats")
    if not isinstance(active_warnings, list) or not isinstance(caveats, list):
        raise BrandFitContractError("Retailer Signals caveat ledger is invalid")
    expected_verdict = (
        "correct_with_caveats"
        if basis.get("mapping_review") == "correct_with_caveats"
        or semantic_state == "correct_with_caveats"
        or bool(active_warnings)
        or bool(caveats)
        else "correct"
    )
    if (
        verdict_key != expected_verdict
        or correctness.get("label")
        != ("Correct" if expected_verdict == "correct" else "Correct with caveats")
        or final.get("correctness_verdict") != expected_verdict
    ):
        raise BrandFitContractError(
            "Retailer Signals final verdict does not follow its reviewed evidence"
        )
    draft = draft_path.read_text(encoding="utf-8")
    if draft.count(SOURCE_RETAILER_VERDICT_PLACEHOLDER) != 1:
        raise BrandFitContractError(
            "Retailer Signals draft verdict placeholder is invalid"
        )
    prefix, suffix = draft.split(SOURCE_RETAILER_VERDICT_PLACEHOLDER)
    final_html = report_path.read_text(encoding="utf-8")
    if (
        not final_html.startswith(prefix)
        or not final_html.endswith(suffix)
        or f'data-correctness-verdict="{verdict_key}"'
        not in final_html[
            len(prefix) : len(final_html) - len(suffix) if suffix else None
        ]
    ):
        raise BrandFitContractError(
            "Retailer Signals final HTML does not derive from its draft"
        )
    outputs = final.get("outputs")
    if not isinstance(outputs, list):
        raise BrandFitContractError("Retailer Signals final output ledger is invalid")
    for raw in outputs:
        if not isinstance(raw, dict):
            raise BrandFitContractError("Retailer Signals final output row is invalid")
        relative = str(raw.get("path") or "")
        if relative not in {"report.html", "correctness_verdict.json"}:
            continue
        artifact = _contained(run, relative, label="Retailer Signals final artifact")
        if not artifact.is_file() or _sha256_file(artifact) != raw.get("sha256"):
            raise BrandFitContractError(
                f"Retailer Signals final artifact hash is stale: {relative}"
            )


def _verify_transport(
    package: Path,
    *,
    download_receipt_path: Path,
    extraction_receipt_path: Path,
) -> tuple[dict[str, Any], dict[str, Any]]:
    download = _load_json(download_receipt_path, label="download receipt")
    extraction = _load_json(extraction_receipt_path, label="extraction receipt")
    if (
        download.get("schema_version")
        != "attribute_reporting.local_download_receipt.v1"
    ):
        raise BrandFitContractError("Unsupported Brand Fit download receipt")
    if extraction.get("schema_version") != (
        "attribute_reporting.local_extraction_receipt.v1"
    ):
        raise BrandFitContractError("Unsupported Brand Fit extraction receipt")
    if not re.fullmatch(r"[0-9a-f]{32}", str(download.get("job_id") or "")):
        raise BrandFitContractError("Brand Fit download receipt has an invalid job id")
    archive = Path(str(download.get("path") or "")).expanduser().resolve()
    expected_sha = str(download.get("sha256") or "")
    if (
        not archive.is_file()
        or not SHA256_RE.fullmatch(expected_sha)
        or _sha256_file(archive) != expected_sha
        or archive.stat().st_size != int(download.get("size_bytes") or -1)
    ):
        raise BrandFitContractError("Brand Fit download receipt does not pin the ZIP")
    if (
        str(extraction.get("archive_sha256") or "") != expected_sha
        or Path(str(extraction.get("archive_path") or "")).expanduser().resolve()
        != archive
        or Path(str(extraction.get("output_dir") or "")).expanduser().resolve()
        != package
    ):
        raise BrandFitContractError(
            "Brand Fit extraction and download receipts disagree"
        )
    raw_files = extraction.get("files")
    if not isinstance(raw_files, list) or len(raw_files) != int(
        extraction.get("file_count") or -1
    ):
        raise BrandFitContractError("Brand Fit extraction file manifest is invalid")
    expected_paths: set[str] = set()
    expected_total = 0
    for raw in raw_files:
        if not isinstance(raw, dict):
            raise BrandFitContractError("Brand Fit extraction file entry is invalid")
        relative = str(raw.get("path") or "")
        collision_key = relative.casefold()
        if collision_key in {path.casefold() for path in expected_paths}:
            raise BrandFitContractError(
                "Brand Fit extraction file manifest has duplicate paths"
            )
        expected_paths.add(relative)
        current = _contained(package, relative, label="extracted package path")
        if (
            not current.is_file()
            or _sha256_file(current) != str(raw.get("sha256") or "")
            or current.stat().st_size != int(raw.get("size_bytes") or -1)
        ):
            raise BrandFitContractError(
                f"Extracted Brand Fit file changed after receipt: {relative}"
            )
        expected_total += current.stat().st_size
        relative_path = Path(relative)
        if (
            "images" in relative_path.parts
            or relative_path.suffix.casefold() in IMAGE_SUFFIXES
        ):
            raise BrandFitContractError(
                f"Server Brand Fit package contains image bytes: {relative}"
            )
        if relative_path.suffix.casefold() not in SERVER_PORTABLE_SUFFIXES:
            raise BrandFitContractError(
                f"Server Brand Fit package contains a disallowed file type: {relative}"
            )
        if current.suffix.casefold() in {".csv", ".json", ".md", ".txt", ".html"}:
            text = current.read_text(encoding="utf-8", errors="replace")
            text_without_public_urls = re.sub(r"https?://[^\s,\"']+", "", text)
            if (
                any(
                    marker.casefold() in text.casefold()
                    for marker in UNSAFE_PORTABLE_MARKERS
                )
                or PRIVATE_URI_RE.search(text_without_public_urls)
                or _portable_file_has_embedded_image_field(current, text)
                or re.search(r"(?:[A-Za-z]:\\|\\\\[^\\\s]+\\)", text)
            ):
                raise BrandFitContractError(
                    f"Server Brand Fit package contains an embedded image or unsafe local URL/path: {relative}"
                )
            if PRIVATE_SERVER_PATH_RE.search(text_without_public_urls):
                raise BrandFitContractError(
                    f"Server Brand Fit package exposes a private server path: {relative}"
                )
    if expected_total != int(extraction.get("total_size_bytes") or -1):
        raise BrandFitContractError("Brand Fit extraction total size is inconsistent")
    current_paths = {
        path.relative_to(package).as_posix()
        for path in package.rglob("*")
        if path.is_file()
    }
    invalid_additions = sorted(
        relative
        for relative in current_paths - expected_paths
        if relative != "local_image_manifest.json"
        and not relative.startswith("images/local/")
    )
    if invalid_additions:
        raise BrandFitContractError(
            "Brand Fit package has unapproved post-extraction files: "
            + ", ".join(invalid_additions)
        )
    return download, extraction


def _validate_sanitization_receipt(package: Path) -> dict[str, Any]:
    path = package / "server_sanitization_receipt.json"
    if not path.is_file():
        raise BrandFitContractError(
            "Brand Fit package has no server sanitization receipt"
        )
    receipt = _load_json(path, label="server sanitization receipt")
    if (
        receipt.get("schema_version")
        != "attribute_reporting.server_bridge.package_sanitization.v1"
        or receipt.get("image_policy") != "urls_only_no_image_bytes"
        or receipt.get("package_integrity_status") != "pass"
    ):
        raise BrandFitContractError("Brand Fit server sanitization receipt is invalid")
    return receipt


def _validate_pack_manifest(
    package: Path, summary: Mapping[str, Any]
) -> dict[str, Any]:
    """Reconcile the server manifest with every portable pre-hydration file."""

    path = package / "pack_manifest.json"
    if not path.is_file():
        raise BrandFitContractError("Brand Fit pack manifest is missing")
    manifest = _load_json(path, label="Brand Fit pack manifest")
    raw_files = manifest.get("files")
    if (
        manifest.get("package_type") != "brand_retailer_reference_handoff"
        or manifest.get("summary") != dict(summary)
        or not isinstance(raw_files, list)
        or any(not isinstance(item, str) or not item for item in raw_files)
        or raw_files != sorted(set(raw_files))
    ):
        raise BrandFitContractError("Brand Fit pack manifest is invalid or stale")
    expected_files = sorted(
        candidate.relative_to(package).as_posix()
        for candidate in package.rglob("*")
        if candidate.is_file()
        and candidate != path
        and candidate.name != "local_image_manifest.json"
        and not candidate.relative_to(package).as_posix().startswith("images/local/")
    )
    if raw_files != expected_files:
        raise BrandFitContractError(
            "Brand Fit pack manifest does not match the portable server package"
        )
    return manifest


def _validate_product_data_snapshot(
    summary: Mapping[str, Any], retailer_presence: Mapping[str, Any]
) -> dict[str, Any]:
    snapshot = summary.get("product_data_snapshot")
    if not isinstance(snapshot, dict) or set(snapshot) != {
        "schema_version",
        "scope",
        "batch_generated_at",
        "entries",
        "snapshot_sha256",
        "read_at",
    }:
        raise BrandFitContractError("Brand Fit product data snapshot is invalid")
    if snapshot.get("schema_version") != (
        "attribute_reporting.server_bridge.product_data_snapshot.v1"
    ):
        raise BrandFitContractError("Unsupported Brand Fit product data snapshot")
    scope = snapshot.get("scope")
    expected_scope_keys = {
        "retailer",
        "retailer_category_keys",
        "brand_source_retailer",
        "owned_category_keys",
    }
    if (
        not isinstance(scope, dict)
        or set(scope) != expected_scope_keys
        or scope.get("retailer") != summary.get("retailer")
        or scope.get("brand_source_retailer") != summary.get("brand_source_retailer")
        or not isinstance(scope.get("retailer_category_keys"), list)
        or not isinstance(scope.get("owned_category_keys"), list)
    ):
        raise BrandFitContractError("Brand Fit product data snapshot scope is invalid")
    entries = snapshot.get("entries")
    if not isinstance(entries, list) or [
        str(entry.get("name") or "") if isinstance(entry, dict) else ""
        for entry in entries
    ] != list(REQUIRED_PRODUCT_CACHE_ENTRIES):
        raise BrandFitContractError(
            "Brand Fit product data snapshot entries are invalid"
        )
    batch_generated_at = str(snapshot.get("batch_generated_at") or "")
    for entry in entries:
        if not isinstance(entry, dict) or set(entry) != {
            "name",
            "payload_sha256",
            "payload_size_bytes",
            "generated_at",
        }:
            raise BrandFitContractError("Brand Fit product cache entry is invalid")
        if (
            not SHA256_RE.fullmatch(str(entry.get("payload_sha256") or ""))
            or not isinstance(entry.get("payload_size_bytes"), int)
            or int(entry["payload_size_bytes"]) <= 0
            or entry.get("generated_at") != batch_generated_at
        ):
            raise BrandFitContractError("Brand Fit product cache entry pin is invalid")
    for label, value in (
        ("batch_generated_at", batch_generated_at),
        ("read_at", str(snapshot.get("read_at") or "")),
    ):
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError as exc:
            raise BrandFitContractError(
                f"Brand Fit product data snapshot {label} is invalid"
            ) from exc
        if parsed.tzinfo is None:
            raise BrandFitContractError(
                f"Brand Fit product data snapshot {label} has no timezone"
            )
    core = {
        "scope": scope,
        "batch_generated_at": batch_generated_at,
        "entries": entries,
    }
    if snapshot.get("snapshot_sha256") != _canonical_sha256(core):
        raise BrandFitContractError("Brand Fit product data snapshot hash is stale")
    if snapshot.get("read_at") != retailer_presence.get("read_at"):
        raise BrandFitContractError(
            "Brand Fit product snapshot and retailer-presence read times disagree"
        )
    return dict(snapshot)


def _validate_mapping_state_snapshot(
    package: Path,
    summary: Mapping[str, Any],
    product_data_snapshot: Mapping[str, Any],
) -> dict[str, Any]:
    """Validate the exact accepted-mapping state used by the server build.

    This is deterministic because the bridge contract requires a reproducible
    checksum over fixed database identities; it does not judge mapping meaning.
    """

    path = package / "mapping_state_snapshot.json"
    if not path.is_file():
        raise BrandFitContractError("Brand Fit mapping-state snapshot is missing")
    snapshot = _load_json(path, label="Brand Fit mapping-state snapshot")
    if set(snapshot) != {"schema_version", "captured_at", "scopes", "state_sha256"}:
        raise BrandFitContractError("Brand Fit mapping-state snapshot is invalid")
    if snapshot.get("schema_version") != MAPPING_STATE_SCHEMA:
        raise BrandFitContractError("Unsupported Brand Fit mapping-state snapshot")
    captured_at = str(snapshot.get("captured_at") or "")
    try:
        parsed = datetime.fromisoformat(captured_at.replace("Z", "+00:00"))
    except ValueError as exc:
        raise BrandFitContractError(
            "Brand Fit mapping-state snapshot captured_at is invalid"
        ) from exc
    if parsed.tzinfo is None:
        raise BrandFitContractError(
            "Brand Fit mapping-state snapshot captured_at has no timezone"
        )
    product_scope = product_data_snapshot.get("scope")
    if not isinstance(product_scope, dict):
        raise BrandFitContractError("Brand Fit product-data scope is unavailable")
    expected_identities = sorted(
        {
            *(
                (str(product_scope.get("retailer") or ""), str(category))
                for category in product_scope.get("retailer_category_keys") or []
            ),
            *(
                (str(product_scope.get("brand_source_retailer") or ""), str(category))
                for category in product_scope.get("owned_category_keys") or []
            ),
        }
    )
    if any(not retailer or not category for retailer, category in expected_identities):
        raise BrandFitContractError("Brand Fit mapping-state scope is invalid")
    raw_scopes = snapshot.get("scopes")
    if not isinstance(raw_scopes, list) or len(raw_scopes) != len(expected_identities):
        raise BrandFitContractError("Brand Fit mapping-state scopes are incomplete")
    observed_identities: list[tuple[str, str]] = []
    state_core: list[dict[str, Any]] = []
    for raw_scope in raw_scopes:
        if not isinstance(raw_scope, dict) or set(raw_scope) != {
            "schema_version",
            "scope",
            "groups",
            "state_sha256",
            "captured_at",
        }:
            raise BrandFitContractError("Brand Fit mapping-state scope is invalid")
        if raw_scope.get("schema_version") != MAPPING_SCOPE_SCHEMA:
            raise BrandFitContractError("Unsupported Brand Fit mapping-state scope")
        scope_captured_at = str(raw_scope.get("captured_at") or "")
        try:
            scope_captured = datetime.fromisoformat(
                scope_captured_at.replace("Z", "+00:00")
            )
        except ValueError as exc:
            raise BrandFitContractError(
                "Brand Fit mapping-state scope captured_at is invalid"
            ) from exc
        if scope_captured.tzinfo is None:
            raise BrandFitContractError(
                "Brand Fit mapping-state scope captured_at has no timezone"
            )
        scope = raw_scope.get("scope")
        groups = raw_scope.get("groups")
        if (
            not isinstance(scope, dict)
            or set(scope) != {"source", "retailer", "category_key"}
            or scope.get("source") != "codex"
            or not isinstance(groups, list)
        ):
            raise BrandFitContractError("Brand Fit mapping-state scope is invalid")
        identity = (
            str(scope.get("retailer") or ""),
            str(scope.get("category_key") or ""),
        )
        observed_identities.append(identity)
        serialized_groups: list[dict[str, Any]] = []
        seen_group_identities: set[tuple[str, ...]] = set()
        for raw_group in groups:
            if not isinstance(raw_group, dict) or set(raw_group) != {
                "identity",
                "rows",
            }:
                raise BrandFitContractError("Brand Fit mapping-state group is invalid")
            group_identity = raw_group.get("identity")
            rows = raw_group.get("rows")
            if (
                not isinstance(group_identity, dict)
                or set(group_identity) != MAPPING_IDENTITY_FIELDS
                or any(
                    not isinstance(group_identity[field], str)
                    for field in group_identity
                )
                or group_identity.get("source") != "codex"
                or group_identity.get("retailer") != identity[0]
                or group_identity.get("category_key") != identity[1]
                or not isinstance(rows, list)
            ):
                raise BrandFitContractError(
                    "Brand Fit mapping-state identity is invalid"
                )
            identity_key = tuple(
                str(group_identity[field]) for field in MAPPING_IDENTITY_ORDER
            )
            if identity_key in seen_group_identities:
                raise BrandFitContractError(
                    "Brand Fit mapping-state contains a duplicate identity"
                )
            seen_group_identities.add(identity_key)
            seen_attributes: set[str] = set()
            normalized_rows: list[dict[str, Any]] = []
            for raw_row in rows:
                if not isinstance(raw_row, dict) or set(raw_row) != MAPPING_ROW_FIELDS:
                    raise BrandFitContractError(
                        "Brand Fit mapping-state row is invalid"
                    )
                attribute_id = str(raw_row.get("attribute_id") or "")
                if (
                    not attribute_id
                    or attribute_id in seen_attributes
                    or not isinstance(raw_row.get("updated_at"), str)
                    or any(
                        raw_row.get(field) is not None
                        and not isinstance(raw_row.get(field), str)
                        for field in (
                            "attribute_label",
                            "value",
                            "oov_candidate",
                            "note",
                        )
                    )
                ):
                    raise BrandFitContractError(
                        "Brand Fit mapping-state row is invalid"
                    )
                seen_attributes.add(attribute_id)
                normalized_rows.append(dict(raw_row))
            if normalized_rows != sorted(
                normalized_rows, key=lambda row: str(row["attribute_id"])
            ):
                raise BrandFitContractError(
                    "Brand Fit mapping-state row order is invalid"
                )
            serialized_groups.append(
                {"identity": dict(group_identity), "rows": normalized_rows}
            )
        if serialized_groups != sorted(
            serialized_groups,
            key=lambda group: tuple(
                group["identity"][field] for field in MAPPING_IDENTITY_ORDER
            ),
        ):
            # The server serializes mapping identities in their declared field order.
            raise BrandFitContractError(
                "Brand Fit mapping-state group order is invalid"
            )
        core = {"scope": dict(scope), "groups": serialized_groups}
        if raw_scope.get("state_sha256") != _canonical_sha256(core):
            raise BrandFitContractError("Brand Fit mapping-state scope hash is stale")
        state_core.append(
            {"scope": dict(scope), "state_sha256": raw_scope["state_sha256"]}
        )
    if observed_identities != expected_identities:
        raise BrandFitContractError(
            "Brand Fit mapping-state scopes do not match the build"
        )
    state_sha256 = _canonical_sha256({"scopes": state_core})
    if (
        snapshot.get("state_sha256") != state_sha256
        or summary.get("mapping_state_snapshot_sha256") != state_sha256
    ):
        raise BrandFitContractError("Brand Fit mapping-state snapshot hash is stale")
    return dict(snapshot)


def _warning_codes(
    package: Path, summary: Mapping[str, Any]
) -> tuple[list[dict[str, Any]], list[str]]:
    warnings_path = package / "package_warnings.json"
    if not warnings_path.is_file():
        raise BrandFitContractError("Brand Fit package warnings artifact is missing")
    payload = _load_json(warnings_path, label="Brand Fit package warnings")
    warnings = payload.get("warnings") or []
    if not isinstance(warnings, list) or any(
        not isinstance(item, dict) or not str(item.get("code") or "").strip()
        for item in warnings
    ):
        raise BrandFitContractError("Brand Fit package warnings are invalid")
    normalized = [dict(item) for item in warnings]
    if payload.get("warning_count") != len(normalized):
        raise BrandFitContractError("Brand Fit package warning count is inconsistent")
    if (
        summary.get("package_warning_count") != len(normalized)
        or summary.get("package_warnings") != normalized
    ):
        raise BrandFitContractError(
            "Brand Fit summary and package_warnings.json disagree"
        )
    return normalized, sorted({str(item["code"]) for item in normalized})


def _write_scope_metrics(output: Path, retailer_presence: Mapping[str, Any]) -> str:
    evidence_root = output / "evidence" / "brand_fit"
    scope_inputs = {
        "retailer_signals": "signal_bundles.csv",
        "current_retailer_presence": "retailer_brand_anchors.csv",
        "owned_catalogue": "manufacturer_catalog_products.csv",
    }
    gap_count = len(
        _read_csv(evidence_root / "manufacturer_products_not_at_retailer.csv")[1]
    )
    candidate_count = len(_read_csv(evidence_root / "reference_candidates.csv")[1])
    rows: list[dict[str, Any]] = []
    for scope, name in scope_inputs.items():
        source = evidence_root / name
        row_count = len(_read_csv(source)[1])
        rows.append(
            {
                "scope": scope,
                "primary_source_file": name,
                "primary_row_count": row_count,
                "scope_status": "present" if row_count else "no_rows_in_snapshot",
                "gap_product_count": gap_count if scope == "owned_catalogue" else "",
                "candidate_count": (
                    candidate_count if scope == "owned_catalogue" else ""
                ),
                "snapshot_mode": (
                    retailer_presence.get("mode")
                    if scope == "current_retailer_presence"
                    else ""
                ),
                "snapshot_read_at": (
                    retailer_presence.get("read_at")
                    if scope == "current_retailer_presence"
                    else ""
                ),
                "primary_source_sha256": _sha256_file(source),
            }
        )
    relative = f"evidence/derived/{SCOPE_METRICS_FILE}"
    _write_csv(output / relative, rows)
    return relative


def _copy_local_images(package: Path, output: Path) -> dict[str, Any] | None:
    manifest_path = package / "local_image_manifest.json"
    if not manifest_path.is_file():
        raise BrandFitContractError(
            "Brand Fit requires a completed local image-hydration manifest"
        )
    manifest = _load_json(manifest_path, label="local image manifest")
    if manifest.get("schema_version") != IMAGE_MANIFEST_SCHEMA:
        raise BrandFitContractError("Unsupported local image manifest")
    source_hashes = manifest.get("source_table_sha256")
    expected_source_hashes = {
        name: _sha256_file(package / name)
        for name in BRAND_FIT_IMAGE_SOURCE_FILES
        if (package / name).is_file()
    }
    if source_hashes != expected_source_hashes:
        raise BrandFitContractError("Local image manifest source tables are stale")
    expected_records: dict[str, dict[str, str]] = {}
    for name in BRAND_FIT_IMAGE_SOURCE_FILES:
        _fields, rows = _read_csv(package / name)
        for row in rows:
            product_id = str(
                row.get("parent_product_id")
                or row.get("product_key")
                or row.get("listing_identity")
                or ""
            ).strip()
            if not product_id:
                raise BrandFitContractError(
                    f"Brand Fit image source row has no product identity: {name}"
                )
            scope = str(row.get("product_scope") or name.removesuffix(".csv"))
            record_id = f"{name}:{scope}:{product_id}"
            if record_id in expected_records:
                raise BrandFitContractError(
                    f"Brand Fit image source has a duplicate identity: {record_id}"
                )
            expected_records[record_id] = {name: _row_sha256(row)}
    products = manifest.get("products")
    summary = manifest.get("summary")
    policy = manifest.get("policy")
    if (
        not isinstance(products, list)
        or not isinstance(summary, dict)
        or not isinstance(policy, dict)
        or policy.get("uploaded_to_server") is not False
    ):
        raise BrandFitContractError("Local image manifest structure is invalid")
    valid_statuses = {
        "downloaded",
        "existing",
        "reused",
        "failed",
        "unavailable",
        "not_attempted",
    }
    record_ids: set[str] = set()
    copied_products: list[dict[str, Any]] = []
    destination_root = output / "evidence" / "local_images"
    for raw in products:
        if not isinstance(raw, dict):
            raise BrandFitContractError("Local image manifest product is invalid")
        entry = dict(raw)
        record_id = str(entry.get("record_id") or "")
        source_rows = entry.get("source_rows")
        status = str(entry.get("status") or "")
        if (
            not record_id
            or record_id in record_ids
            or not str(entry.get("product_id") or "")
            or status not in valid_statuses
            or not isinstance(source_rows, dict)
            or not source_rows
            or any(
                name not in expected_source_hashes
                or not SHA256_RE.fullmatch(str(row_sha or ""))
                for name, row_sha in source_rows.items()
            )
            or str(entry.get("source_row_sha256") or "")
            not in {str(value) for value in source_rows.values()}
            or source_rows != expected_records.get(record_id)
        ):
            raise BrandFitContractError(
                "Local image manifest product identity is invalid"
            )
        record_ids.add(record_id)
        if entry.get("status") not in {"downloaded", "existing", "reused"}:
            if entry.get("image_path") or entry.get("sha256"):
                raise BrandFitContractError(
                    "Unavailable local image entry unexpectedly carries image bytes"
                )
            entry["image_path"] = ""
            copied_products.append(entry)
            continue
        relative = _safe_relative(
            str(entry.get("image_path") or ""), label="hydrated image path"
        )
        source = (package / relative).resolve()
        image_root = (package / "images").resolve()
        expected = str(entry.get("sha256") or "")
        if (
            not source.is_file()
            or not source.is_relative_to(image_root)
            or not SHA256_RE.fullmatch(expected)
            or _sha256_file(source) != expected
        ):
            raise BrandFitContractError(
                f"Hydrated image is missing or stale for {entry.get('product_id')}"
            )
        destination = destination_root / f"{expected[:16]}-{source.name}"
        _copy_file(source, destination)
        entry["package_image_path"] = relative.as_posix()
        entry["image_path"] = destination.relative_to(output).as_posix()
        copied_products.append(entry)
    if record_ids != set(expected_records):
        raise BrandFitContractError(
            "Local image manifest does not cover every scope-separated product row"
        )
    counts = {
        "available_count": sum(
            item.get("status") in {"downloaded", "existing", "reused"}
            for item in products
        ),
        "failure_count": sum(item.get("status") == "failed" for item in products),
        "unavailable_count": sum(
            item.get("status") == "unavailable" for item in products
        ),
        "not_attempted_count": sum(
            item.get("status") == "not_attempted" for item in products
        ),
    }
    derived_status = (
        "complete"
        if counts["available_count"] == len(products)
        else "partial" if counts["available_count"] else "blocked"
    )
    expected_summary = {
        "product_count": len(products),
        **counts,
        "status": derived_status,
    }
    if summary != expected_summary:
        raise BrandFitContractError("Local image manifest summary is inconsistent")
    copied = {
        "schema_version": IMAGE_MANIFEST_SCHEMA,
        "scope": "brand_fit_local_report_evidence",
        "source_manifest_sha256": _sha256_file(manifest_path),
        "products": copied_products,
        "source_table_sha256": expected_source_hashes,
        "summary": expected_summary,
        "policy": {
            "storage": "private_local_only",
            "uploaded_to_server": False,
        },
    }
    _write_json(output / "evidence" / "local_image_manifest.json", copied)
    return copied


def _catalog_file_record(output: Path, relative: str) -> dict[str, Any]:
    path = _contained(output, relative, label="catalog evidence path")
    record: dict[str, Any] = {
        "path": relative,
        "sha256": _sha256_file(path),
        "size_bytes": path.stat().st_size,
    }
    if path.suffix.casefold() == ".csv":
        fields, rows = _read_csv(path)
        record.update({"columns": fields, "row_count": len(rows)})
    return record


def prepare_brand_fit_run(
    package_dir: Path,
    *,
    retailer_run_dir: Path,
    output_dir: Path,
    author_agent_id: str,
    download_receipt_path: Path,
    extraction_receipt_path: Path,
    require_browser_qa: bool = True,
) -> dict[str, Any]:
    """Prepare immutable Brand Fit evidence and Codex author/review templates."""

    if not author_agent_id.strip() or not SAFE_ID_RE.fullmatch(author_agent_id.strip()):
        raise BrandFitContractError("author_agent_id is required and must be stable")
    package = package_dir.expanduser().resolve()
    output = output_dir.expanduser().resolve()
    if not package.is_dir():
        raise BrandFitContractError(f"Brand Fit package is unavailable: {package}")
    if output.exists() and (not output.is_dir() or any(output.iterdir())):
        raise BrandFitContractError(
            "Brand Fit output directory must be absent or empty"
        )
    retailer = completed_retailer_report(retailer_run_dir)
    download_receipt, extraction_receipt = _verify_transport(
        package,
        download_receipt_path=download_receipt_path,
        extraction_receipt_path=extraction_receipt_path,
    )
    summary = _load_json(package / "summary.json", label="Brand Fit summary")
    integrity = _load_json(
        package / "package_integrity.json", label="Brand Fit package integrity"
    )
    if summary.get("analysis_type") != "brand_retailer_reference_handoff":
        raise BrandFitContractError("Package is not a Brand Fit handoff")
    if integrity.get("status") != "pass":
        raise BrandFitContractError("Brand Fit package integrity is not pass")
    _validate_sanitization_receipt(package)
    pack_manifest = _validate_pack_manifest(package, summary)
    retailer_presence = summary.get("retailer_presence")
    if not isinstance(retailer_presence, dict) or retailer_presence.get("mode") != (
        "current_database_snapshot"
    ):
        raise BrandFitContractError(
            "Brand Fit retailer presence must be a current database snapshot"
        )
    read_at = str(retailer_presence.get("read_at") or "").strip()
    try:
        parsed_read_at = datetime.fromisoformat(read_at.replace("Z", "+00:00"))
    except ValueError as exc:
        raise BrandFitContractError(
            "Brand Fit retailer presence requires an ISO read_at timestamp"
        ) from exc
    if parsed_read_at.tzinfo is None:
        raise BrandFitContractError(
            "Brand Fit retailer presence read_at must include a timezone"
        )
    product_data_snapshot = _validate_product_data_snapshot(summary, retailer_presence)
    mapping_state_snapshot = _validate_mapping_state_snapshot(
        package, summary, product_data_snapshot
    )
    source_report = summary.get("source_retailer_report")
    if not isinstance(source_report, dict) or source_report != {
        "sha256": retailer["sha256"],
        "verdict": retailer["verdict"],
    }:
        raise BrandFitContractError(
            "Brand Fit package is not bound to this checked Retailer Signals report"
        )
    source_evidence = summary.get("source_retailer_evidence")
    if not isinstance(source_evidence, dict) or source_evidence != {
        "job_id": retailer["job_id"],
        "package_sha256": retailer["package_sha256"],
    }:
        raise BrandFitContractError(
            "Brand Fit package is not bound to the Retailer Signals evidence job"
        )
    missing = [name for name in EVIDENCE_FILES if not (package / name).is_file()]
    if missing:
        raise BrandFitContractError(
            "Brand Fit package is missing required evidence: " + ", ".join(missing)
        )
    warnings, warning_codes = _warning_codes(package, summary)
    output.mkdir(parents=True, mode=0o700, exist_ok=True)
    evidence_root = output / "evidence" / "brand_fit"
    copied_relatives: list[str] = []
    server_files = [*pack_manifest["files"], "pack_manifest.json"]
    if len({Path(str(name)).name for name in server_files}) != len(server_files):
        raise BrandFitContractError(
            "Brand Fit portable package contains duplicate evidence basenames"
        )
    for name in server_files:
        relative = f"evidence/brand_fit/{name}"
        _copy_file(package / name, output / relative)
        copied_relatives.append(relative)
    copied_relatives.append(_write_scope_metrics(output, retailer_presence))
    source_root = output / "evidence" / "retailer_signals"
    retailer_run = retailer_run_dir.expanduser().resolve()
    for name in ("report.html", "correctness_verdict.json", "final_artifacts.json"):
        _copy_file(retailer_run / name, source_root / name)
    _copy_file(download_receipt_path, output / "transport" / "download_receipt.json")
    _copy_file(
        extraction_receipt_path, output / "transport" / "extraction_receipt.json"
    )
    copied_images = _copy_local_images(package, output)
    files = {
        Path(relative).name: _catalog_file_record(output, relative)
        for relative in copied_relatives
    }
    report_id = f"brand-fit-{uuid.uuid4().hex}"
    catalog: dict[str, Any] = {
        "schema_version": CATALOG_SCHEMA,
        "report_id": report_id,
        "prepared_at": _utc_now(),
        "analysis_type": "brand_fit",
        "author_agent_id": author_agent_id.strip(),
        "scope": {
            "retailer": summary.get("retailer"),
            "category_key": summary.get("category_key"),
            "brand_name": summary.get("brand_name"),
            "brand_source_retailer": summary.get("brand_source_retailer"),
        },
        "retailer_presence": dict(retailer_presence),
        "product_data_snapshot": product_data_snapshot,
        "mapping_state_snapshot": {
            "path": "evidence/brand_fit/mapping_state_snapshot.json",
            "sha256": _sha256_file(evidence_root / "mapping_state_snapshot.json"),
            "state_sha256": mapping_state_snapshot["state_sha256"],
            "captured_at": mapping_state_snapshot["captured_at"],
            "scope_count": len(mapping_state_snapshot["scopes"]),
        },
        "source_retailer_evidence": dict(source_evidence),
        "source_retailer_report": {
            "path": "evidence/retailer_signals/report.html",
            "sha256": retailer["sha256"],
            "verdict": retailer["verdict"],
            "correctness_path": "evidence/retailer_signals/correctness_verdict.json",
            "correctness_sha256": _sha256_file(
                source_root / "correctness_verdict.json"
            ),
            "final_artifacts_path": "evidence/retailer_signals/final_artifacts.json",
            "final_artifacts_sha256": _sha256_file(
                source_root / "final_artifacts.json"
            ),
            "uploaded_to_server": False,
        },
        "files": files,
        "transport": {
            "download_receipt": {
                "path": "transport/download_receipt.json",
                "sha256": _sha256_file(output / "transport" / "download_receipt.json"),
                "job_id": download_receipt.get("job_id"),
            },
            "extraction_receipt": {
                "path": "transport/extraction_receipt.json",
                "sha256": _sha256_file(
                    output / "transport" / "extraction_receipt.json"
                ),
                "archive_sha256": extraction_receipt.get("archive_sha256"),
            },
        },
        "warnings": warnings,
        "warning_codes": warning_codes,
        "local_image_manifest": (
            {
                "path": "evidence/local_image_manifest.json",
                "sha256": _sha256_file(
                    output / "evidence" / "local_image_manifest.json"
                ),
                "status": (copied_images or {}).get("summary", {}).get("status"),
            }
            if copied_images is not None
            else None
        ),
        "quality_gates": {
            "package_integrity": "pass",
            "browser_qa_required": require_browser_qa,
            "independent_semantic_review_required": True,
        },
        "privacy": {
            "storage": "private_local_only",
            "report_uploaded_to_server": False,
            "image_bytes_uploaded_to_server": False,
        },
    }
    _write_json(output / "evidence_catalog.json", catalog)
    template = {
        "schema_version": MODEL_SCHEMA,
        "report_id": report_id,
        "authoring_status": "template_requires_codex",
        "author": {
            "execution": "codex_agent",
            "agent_id": author_agent_id.strip(),
            "role": "brand_fit_report_author",
        },
        "title": "Brand Fit",
        "subtitle": "",
        "claims": [],
        "sections": [
            {
                "section_id": section_id,
                "title": section_id.replace("_", " ").title(),
                "summary": "",
                "claim_ids": [],
                "table_keys": [],
            }
            for section_id in SECTION_IDS
        ],
        "featured_products": [],
        "acknowledged_warning_codes": warning_codes,
        "limitations": [
            {"code": code, "text": "Codex must explain this package warning."}
            for code in warning_codes
        ],
    }
    _write_json(output / "report_model.json", template)
    _write_json(
        output / "authoring_contract.json",
        {
            "schema_version": "attribute_reporting.brand_fit_authoring_contract.v1",
            "report_id": report_id,
            "model_schema": MODEL_SCHEMA,
            "required_sections": list(SECTION_IDS),
            "allowed_table_keys": sorted(TABLE_KEYS),
            "evidence_reference": {
                "shape": {
                    "ref_id": "stable-id",
                    "source": (
                        "evidence/brand_fit/<server-file>.csv or "
                        f"evidence/derived/{SCOPE_METRICS_FILE}"
                    ),
                    "selector": {"match": {"column": "exact value"}},
                    "fields": ["column_to_render"],
                },
                "rule": (
                    "Every selector must match exactly one current CSV row. Use "
                    "{{ref_id.field}} tokens for displayed evidence values."
                ),
            },
            "judgment_boundary": {
                "deterministic": "row identity, hashes, arithmetic, rendering",
                "codex": (
                    "signal importance, fit interpretation, candidate relevance, "
                    "narrative, and independent review"
                ),
                "no_model_api": True,
            },
        },
    )
    return catalog


def _assert_file_hashes(output: Path, catalog: Mapping[str, Any]) -> None:
    files = catalog.get("files")
    if not isinstance(files, dict):
        raise BrandFitContractError("Brand Fit evidence catalog has no files")
    for name, raw in files.items():
        if not isinstance(raw, dict):
            raise BrandFitContractError(f"Invalid catalog file record: {name}")
        path = _contained(output, str(raw.get("path") or ""), label="evidence path")
        if not path.is_file() or _sha256_file(path) != raw.get("sha256"):
            raise BrandFitContractError(f"Brand Fit evidence changed: {name}")
    evidence_root = output / "evidence" / "brand_fit"
    summary = _load_json(evidence_root / "summary.json", label="Brand Fit summary")
    _validate_pack_manifest(evidence_root, summary)
    retailer_presence = catalog.get("retailer_presence")
    if not isinstance(retailer_presence, dict):
        raise BrandFitContractError("Brand Fit retailer-presence binding is invalid")
    product_snapshot = _validate_product_data_snapshot(summary, retailer_presence)
    if product_snapshot != catalog.get("product_data_snapshot"):
        raise BrandFitContractError("Brand Fit product-data binding changed")
    mapping_snapshot = _validate_mapping_state_snapshot(
        evidence_root, summary, product_snapshot
    )
    expected_mapping_record = {
        "path": "evidence/brand_fit/mapping_state_snapshot.json",
        "sha256": _sha256_file(evidence_root / "mapping_state_snapshot.json"),
        "state_sha256": mapping_snapshot["state_sha256"],
        "captured_at": mapping_snapshot["captured_at"],
        "scope_count": len(mapping_snapshot["scopes"]),
    }
    if catalog.get("mapping_state_snapshot") != expected_mapping_record:
        raise BrandFitContractError("Brand Fit mapping-state binding changed")
    source = catalog.get("source_retailer_report")
    if not isinstance(source, dict):
        raise BrandFitContractError("Source Retailer Signals binding is missing")
    report = _contained(output, str(source.get("path") or ""), label="source report")
    if not report.is_file() or _sha256_file(report) != source.get("sha256"):
        raise BrandFitContractError("Checked Retailer Signals report changed")
    for path_key, hash_key in (
        ("correctness_path", "correctness_sha256"),
        ("final_artifacts_path", "final_artifacts_sha256"),
    ):
        source_artifact = _contained(
            output, str(source.get(path_key) or ""), label=path_key
        )
        if not source_artifact.is_file() or _sha256_file(source_artifact) != source.get(
            hash_key
        ):
            raise BrandFitContractError(f"Checked Retailer Signals {path_key} changed")
    image_record = catalog.get("local_image_manifest")
    if image_record is not None:
        if not isinstance(image_record, dict):
            raise BrandFitContractError("Local image manifest record is invalid")
        path = _contained(
            output, str(image_record.get("path") or ""), label="image manifest"
        )
        if not path.is_file() or _sha256_file(path) != image_record.get("sha256"):
            raise BrandFitContractError("Local image manifest changed")
    transport = catalog.get("transport")
    if not isinstance(transport, dict):
        raise BrandFitContractError("Brand Fit transport binding is missing")
    for key in ("download_receipt", "extraction_receipt"):
        record = transport.get(key)
        if not isinstance(record, dict):
            raise BrandFitContractError(f"Brand Fit {key} binding is missing")
        path = _contained(output, str(record.get("path") or ""), label=key)
        if not path.is_file() or _sha256_file(path) != record.get("sha256"):
            raise BrandFitContractError(f"Brand Fit {key} changed")


def _source_record(
    output: Path, catalog: Mapping[str, Any], source: str
) -> tuple[Path, Mapping[str, Any]]:
    name = Path(source).name
    files = catalog.get("files")
    record = files.get(name) if isinstance(files, dict) else None
    if (
        not isinstance(record, dict)
        or str(record.get("path") or "") != source
        or not (
            source.startswith("evidence/brand_fit/")
            or source == f"evidence/derived/{SCOPE_METRICS_FILE}"
        )
        or not source.endswith(".csv")
    ):
        raise BrandFitContractError(f"Unsupported Brand Fit evidence source: {source}")
    return _contained(output, source, label="claim evidence source"), record


def _selected_row(
    output: Path,
    catalog: Mapping[str, Any],
    ref: Mapping[str, Any],
) -> tuple[dict[str, str], str, Mapping[str, Any]]:
    source = str(ref.get("source") or "")
    path, record = _source_record(output, catalog, source)
    selector = ref.get("selector")
    match = selector.get("match") if isinstance(selector, dict) else None
    if (
        not isinstance(match, dict)
        or not match
        or any(
            not isinstance(key, str) or not isinstance(value, str)
            for key, value in match.items()
        )
    ):
        raise BrandFitContractError("Evidence selector.match must be exact text fields")
    fields, rows = _read_csv(path)
    unknown = sorted(set(match) - set(fields))
    if unknown:
        raise BrandFitContractError(f"Evidence selector uses unknown fields: {unknown}")
    selected = [
        row
        for row in rows
        if all(row.get(key, "") == value for key, value in match.items())
    ]
    if len(selected) != 1:
        raise BrandFitContractError(
            f"Evidence selector for {source} matched {len(selected)} rows; expected one"
        )
    return selected[0], _row_sha256(selected[0]), record


def _evidence_scope(source: str, row: Mapping[str, str]) -> str:
    name = Path(source).name
    if name == SCOPE_METRICS_FILE:
        scope = str(row.get("scope") or "")
        return scope if scope in REQUIRED_EVIDENCE_SCOPES else ""
    if name in {"signal_bundles.csv", "plain_language_signal_guide.csv"}:
        return "retailer_signals"
    if name in {
        "retailer_brand_anchors.csv",
        "retailer_brand_anchor_signal_fit.csv",
        "retailer_live_presence_audit.csv",
        "brand_at_retailer_review_validation.csv",
        "brand_at_retailer_bundle_matches.csv",
    }:
        return "current_retailer_presence"
    if name in {
        "manufacturer_catalog_products.csv",
        "manufacturer_products_not_at_retailer.csv",
        "manufacturer_catalog_bundle_matches.csv",
        "reference_candidates.csv",
    }:
        return "owned_catalogue"
    return ""


def _has_unbound_number(text: str) -> bool:
    return bool(NUMBER_RE.search(TOKEN_RE.sub("", text)))


def _authored_text(value: Any, *, label: str, allow_empty: bool = True) -> str:
    if not isinstance(value, str):
        raise BrandFitContractError(f"{label} must be text")
    clean = value.strip()
    if not clean and not allow_empty:
        raise BrandFitContractError(f"{label} cannot be empty")
    if _has_unbound_number(clean):
        raise BrandFitContractError(
            f"{label} contains an unbound number; use an evidence token"
        )
    return clean


def _validate_model(
    output: Path, catalog: Mapping[str, Any], model: Mapping[str, Any]
) -> tuple[dict[str, Mapping[str, Any]], list[dict[str, Any]]]:
    if model.get("schema_version") != MODEL_SCHEMA:
        raise BrandFitContractError("Unsupported Brand Fit report model schema")
    if model.get("report_id") != catalog.get("report_id"):
        raise BrandFitContractError("Brand Fit report_id does not match its evidence")
    if model.get("authoring_status") != "codex_complete":
        raise BrandFitContractError("Brand Fit report still requires Codex authoring")
    author = model.get("author")
    if not isinstance(author, dict) or (
        author.get("execution") != "codex_agent"
        or author.get("role") != "brand_fit_report_author"
        or author.get("agent_id") != catalog.get("author_agent_id")
    ):
        raise BrandFitContractError("Brand Fit report author identity is invalid")
    _authored_text(model.get("title"), label="report title", allow_empty=False)
    _authored_text(model.get("subtitle", ""), label="report subtitle")
    raw_claims = model.get("claims")
    if not isinstance(raw_claims, list) or not raw_claims:
        raise BrandFitContractError("Brand Fit report requires at least one claim")
    claims: dict[str, Mapping[str, Any]] = {}
    claim_scopes: dict[str, set[str]] = {}
    resolved_refs: list[dict[str, Any]] = []
    ref_ids: set[str] = set()
    for raw in raw_claims:
        if not isinstance(raw, dict):
            raise BrandFitContractError("Every Brand Fit claim must be an object")
        claim_id = str(raw.get("claim_id") or "")
        if not SAFE_ID_RE.fullmatch(claim_id) or claim_id in claims:
            raise BrandFitContractError(f"Invalid or duplicate claim_id: {claim_id!r}")
        kind = str(raw.get("kind") or "")
        if kind not in {"deterministic", "semantic"}:
            raise BrandFitContractError(f"Unsupported claim kind for {claim_id}")
        _authored_text(
            raw.get("headline"), label=f"claim {claim_id} headline", allow_empty=False
        )
        text_template = _authored_text(
            raw.get("text_template"),
            label=f"claim {claim_id} text",
            allow_empty=False,
        )
        _authored_text(
            raw.get("interpretation", ""), label=f"claim {claim_id} interpretation"
        )
        _authored_text(raw.get("caveat", ""), label=f"claim {claim_id} caveat")
        if raw.get("confidence") not in {"high", "medium", "low"}:
            raise BrandFitContractError(f"Claim {claim_id} confidence is invalid")
        refs = raw.get("evidence_refs") or []
        supporting = raw.get("supporting_claim_ids") or []
        if not isinstance(refs, list) or not isinstance(supporting, list):
            raise BrandFitContractError(f"Claim {claim_id} references must be lists")
        if kind == "deterministic" and not refs:
            raise BrandFitContractError(
                f"Deterministic claim {claim_id} has no evidence"
            )
        if kind == "semantic" and (refs or not supporting):
            raise BrandFitContractError(
                f"Semantic claim {claim_id} must support deterministic claims only"
            )
        declared_tokens: set[tuple[str, str]] = set()
        for ref in refs:
            if not isinstance(ref, dict):
                raise BrandFitContractError(f"Claim {claim_id} evidence ref is invalid")
            ref_id = str(ref.get("ref_id") or "")
            if not SAFE_ID_RE.fullmatch(ref_id) or ref_id in ref_ids:
                raise BrandFitContractError(f"Invalid or duplicate ref_id: {ref_id!r}")
            fields = ref.get("fields")
            if (
                not isinstance(fields, list)
                or not fields
                or any(not isinstance(field, str) or not field for field in fields)
            ):
                raise BrandFitContractError(f"Evidence ref {ref_id} fields are invalid")
            row, row_sha, record = _selected_row(output, catalog, ref)
            scope = _evidence_scope(str(ref["source"]), row)
            if not scope:
                raise BrandFitContractError(
                    f"Evidence ref {ref_id} does not establish a Brand Fit scope"
                )
            unknown_fields = sorted(set(fields) - set(row))
            if unknown_fields:
                raise BrandFitContractError(
                    f"Evidence ref {ref_id} uses unknown fields: {unknown_fields}"
                )
            declared_tokens.update((ref_id, field) for field in fields)
            resolved_refs.append(
                {
                    "claim_id": claim_id,
                    "ref_id": ref_id,
                    "source": ref["source"],
                    "source_sha256": record["sha256"],
                    "selector": ref["selector"],
                    "source_row_sha256": row_sha,
                    "evidence_scope": scope,
                    "values": {field: row[field] for field in fields},
                }
            )
            ref_ids.add(ref_id)
        used_tokens = set(TOKEN_RE.findall(text_template))
        if kind == "deterministic" and (
            not used_tokens or used_tokens != declared_tokens
        ):
            raise BrandFitContractError(
                f"Claim {claim_id} must use every and only its declared evidence tokens"
            )
        if kind == "semantic" and used_tokens:
            raise BrandFitContractError(
                f"Semantic claim {claim_id} cannot add evidence tokens"
            )
        claims[claim_id] = raw
        claim_scopes[claim_id] = {
            str(item["evidence_scope"])
            for item in resolved_refs
            if item["claim_id"] == claim_id
        }
    for claim_id, claim in claims.items():
        if claim.get("kind") != "semantic":
            continue
        supporting = claim.get("supporting_claim_ids") or []
        if any(
            support not in claims
            or support == claim_id
            or claims[support].get("kind") != "deterministic"
            for support in supporting
        ):
            raise BrandFitContractError(
                f"Semantic claim {claim_id} has invalid supporting claims"
            )
    sections = model.get("sections")
    if (
        not isinstance(sections, list)
        or tuple(
            str(item.get("section_id") or "") if isinstance(item, dict) else ""
            for item in sections
        )
        != SECTION_IDS
    ):
        raise BrandFitContractError("Brand Fit sections are missing or out of order")
    used_claims: list[str] = []
    for section in sections:
        if not isinstance(section, dict):
            raise BrandFitContractError("Brand Fit section must be an object")
        section_id = str(section["section_id"])
        _authored_text(
            section.get("title"), label=f"section {section_id} title", allow_empty=False
        )
        _authored_text(
            section.get("summary", ""), label=f"section {section_id} summary"
        )
        claim_ids = section.get("claim_ids") or []
        table_keys = section.get("table_keys") or []
        if not isinstance(claim_ids, list) or not isinstance(table_keys, list):
            raise BrandFitContractError(f"Section {section_id} references are invalid")
        if any(claim_id not in claims for claim_id in claim_ids):
            raise BrandFitContractError(
                f"Section {section_id} references an unknown claim"
            )
        if any(table_key not in TABLE_KEYS for table_key in table_keys):
            raise BrandFitContractError(
                f"Section {section_id} references an unknown table"
            )
        allowed_tables = SECTION_TABLE_KEYS.get(section_id, frozenset())
        if (
            len(table_keys) != len(set(table_keys))
            or not set(table_keys) <= allowed_tables
        ):
            raise BrandFitContractError(
                f"Section {section_id} uses a table from another evidence scope"
            )
        if not section.get("summary") and not claim_ids and not table_keys:
            raise BrandFitContractError(f"Section {section_id} cannot be empty")
        used_claims.extend(str(claim_id) for claim_id in claim_ids)
    if sorted(used_claims) != sorted(claims) or len(used_claims) != len(
        set(used_claims)
    ):
        raise BrandFitContractError("Every Brand Fit claim must appear exactly once")
    section_claims = {
        str(section["section_id"]): [
            str(claim_id) for claim_id in section.get("claim_ids") or []
        ]
        for section in sections
        if isinstance(section, dict)
    }
    for section_id, scope in {
        "retailer_signals": "retailer_signals",
        "current_retailer_presence": "current_retailer_presence",
        "owned_catalogue": "owned_catalogue",
    }.items():
        if not any(
            claims[claim_id].get("kind") == "deterministic"
            and scope in claim_scopes.get(claim_id, set())
            for claim_id in section_claims.get(section_id, [])
        ):
            raise BrandFitContractError(
                f"Section {section_id} requires a deterministic {scope} claim"
            )
    cross_scope_semantic = False
    for claim_id in section_claims.get("brand_fit_opportunities", []):
        claim = claims[claim_id]
        if claim.get("kind") != "semantic":
            continue
        supported_scopes: set[str] = set()
        for support in claim.get("supporting_claim_ids") or []:
            supported_scopes.update(claim_scopes.get(str(support), set()))
        if REQUIRED_EVIDENCE_SCOPES <= supported_scopes:
            cross_scope_semantic = True
            break
    if not cross_scope_semantic:
        raise BrandFitContractError(
            "Brand Fit opportunities require a semantic comparison supported across retailer signals, current presence, and owned catalogue"
        )
    warning_codes = set(catalog.get("warning_codes") or [])
    if set(model.get("acknowledged_warning_codes") or []) != warning_codes:
        raise BrandFitContractError(
            "Every package warning must be acknowledged exactly"
        )
    limitations = model.get("limitations")
    if not isinstance(limitations, list):
        raise BrandFitContractError("Brand Fit limitations must be a list")
    limitation_codes: set[str] = set()
    for limitation in limitations:
        if not isinstance(limitation, dict):
            raise BrandFitContractError("Brand Fit limitation is invalid")
        code = str(limitation.get("code") or "")
        limitation_codes.add(code)
        _authored_text(
            limitation.get("text"), label=f"limitation {code}", allow_empty=False
        )
    if not warning_codes <= limitation_codes:
        raise BrandFitContractError("Every active package warning must be visible")
    products = model.get("featured_products")
    if not isinstance(products, list) or len(products) > 8:
        raise BrandFitContractError(
            "featured_products must contain at most eight items"
        )
    featured_identities: set[tuple[str, str]] = set()
    for product in products:
        if not isinstance(product, dict):
            raise BrandFitContractError("Featured Brand Fit product is invalid")
        source = str(product.get("source") or "")
        if Path(source).name not in PRODUCT_FILES:
            raise BrandFitContractError("Featured product source is unsupported")
        row, row_sha, _record = _selected_row(output, catalog, product)
        product_id = str(
            row.get("parent_product_id")
            or row.get("product_key")
            or row.get("listing_identity")
            or ""
        )
        if not product_id or product.get("product_id") != product_id:
            raise BrandFitContractError(
                "Featured product identity does not match its row"
            )
        source_name = Path(source).name
        if product.get("role") != PRODUCT_SOURCE_ROLES[source_name]:
            raise BrandFitContractError(
                "Featured product role does not match its evidence scope"
            )
        featured_identity = (source, row_sha)
        if featured_identity in featured_identities:
            raise BrandFitContractError("Featured product is duplicated")
        featured_identities.add(featured_identity)
        _authored_text(
            product.get("rationale"),
            label="featured product rationale",
            allow_empty=False,
        )
        supports = product.get("supporting_claim_ids") or []
        if (
            not isinstance(supports, list)
            or not supports
            or any(claim_id not in claims for claim_id in supports)
        ):
            raise BrandFitContractError(
                "Featured product supporting claims are invalid"
            )
        evidence_scope = _evidence_scope(source, row)
        if not any(
            claims[str(claim_id)].get("kind") == "deterministic"
            and evidence_scope in claim_scopes.get(str(claim_id), set())
            for claim_id in supports
        ):
            raise BrandFitContractError(
                "Featured product needs a deterministic claim from its evidence scope"
            )
    return claims, resolved_refs


def _render_template(text: str, values: Mapping[tuple[str, str], str]) -> str:
    chunks: list[str] = []
    position = 0
    for match in TOKEN_RE.finditer(text):
        chunks.append(html.escape(text[position : match.start()]))
        key = (match.group(1), match.group(2))
        if key not in values:
            raise BrandFitContractError(f"Unresolved evidence token: {match.group(0)}")
        chunks.append(html.escape(values[key]))
        position = match.end()
    chunks.append(html.escape(text[position:]))
    return "".join(chunks)


def _safe_http_url(value: str) -> str:
    clean = value.strip()
    if not re.fullmatch(r"https?://[^\s<>\"']+", clean, flags=re.IGNORECASE):
        return ""
    return clean


def _render_table(output: Path, catalog: Mapping[str, Any], table_key: str) -> str:
    source = f"evidence/brand_fit/{TABLE_KEYS[table_key]}"
    path, _record = _source_record(output, catalog, source)
    fields, rows = _read_csv(path)
    preferred = {
        "retailer_signals": [
            "bundle_label",
            "signal_layers",
            "signal_score",
            "rank_weighted_incremental_visibility_share",
        ],
        "current_retailer_presence": [
            "product_name",
            "anchor_status",
            "matched_signal_count",
            "fit_status",
            "commercial_read",
        ],
        "owned_catalogue": [
            "product_name",
            "brand",
            "variant_count",
            "price",
            "category",
        ],
        "brand_fit_candidates": [
            "product_name",
            "matched_bundle_labels",
            "reference_rationale",
            "reference_score",
        ],
    }[table_key]
    columns = [column for column in preferred if column in fields] or fields[:6]
    head = "".join(
        f"<th>{html.escape(column.replace('_', ' ').title())}</th>"
        for column in columns
    )
    body = "".join(
        "<tr>"
        + "".join(f"<td>{html.escape(row.get(column, ''))}</td>" for column in columns)
        + "</tr>"
        for row in rows[:12]
    )
    if not rows:
        body = f'<tr><td colspan="{max(len(columns), 1)}">No rows in this evidence table.</td></tr>'
    return f'<div class="table-scroll" data-table-key="{html.escape(table_key)}"><table><thead><tr>{head}</tr></thead><tbody>{body}</tbody></table></div>'


def _selected_products(
    output: Path,
    catalog: Mapping[str, Any],
    model: Mapping[str, Any],
    *,
    copy_assets: bool = True,
) -> list[dict[str, Any]]:
    manifest_record = catalog.get("local_image_manifest")
    manifest: dict[str, Any] = {}
    if isinstance(manifest_record, dict):
        manifest = _load_json(
            _contained(output, str(manifest_record["path"]), label="image manifest"),
            label="copied local image manifest",
        )
    image_entries = [
        item
        for item in manifest.get("products") or []
        if isinstance(item, dict) and str(item.get("product_id") or "")
    ]
    selected: list[dict[str, Any]] = []
    asset_root = output / "assets" / "products"
    for product in model.get("featured_products") or []:
        row, row_sha, _record = _selected_row(output, catalog, product)
        product_id = str(product["product_id"])
        source_name = Path(str(product["source"])).name
        matching_images = [
            item
            for item in image_entries
            if item.get("product_id") == product_id
            and isinstance(item.get("source_rows"), dict)
            and item["source_rows"].get(source_name) == row_sha
        ]
        if len(matching_images) > 1:
            raise BrandFitContractError(
                f"Ambiguous local image evidence for featured product {product_id}"
            )
        image = matching_images[0] if matching_images else None
        asset_relative = ""
        image_sha = ""
        if isinstance(image, dict) and image.get("status") in {
            "downloaded",
            "existing",
            "reused",
        }:
            source_rows = image.get("source_rows")
            if (
                not isinstance(source_rows, dict)
                or source_rows.get(source_name) != row_sha
            ):
                raise BrandFitContractError(
                    f"Local image evidence is stale for featured product {product_id}"
                )
            image_path = _contained(
                output, str(image.get("image_path") or ""), label="copied image"
            )
            image_sha = str(image.get("sha256") or "")
            if not image_path.is_file() or _sha256_file(image_path) != image_sha:
                raise BrandFitContractError(f"Local image changed for {product_id}")
            destination = asset_root / f"{image_sha[:16]}{image_path.suffix.casefold()}"
            if copy_assets:
                _copy_file(image_path, destination)
            elif not destination.is_file() or _sha256_file(destination) != image_sha:
                raise BrandFitContractError(
                    f"Rendered featured image changed for {product_id}"
                )
            asset_relative = destination.relative_to(output).as_posix()
        selected.append(
            {
                "product_id": product_id,
                "source": product["source"],
                "source_row_sha256": row_sha,
                "role": product["role"],
                "rationale": product["rationale"],
                "supporting_claim_ids": product["supporting_claim_ids"],
                "product_name": row.get("product_name")
                or row.get("name")
                or product_id,
                "pdp_url": _safe_http_url(
                    str(
                        row.get("pdp_url")
                        or row.get("product_url")
                        or row.get("url")
                        or ""
                    )
                ),
                "asset_path": asset_relative,
                "image_sha256": image_sha,
                "image_status": "available" if asset_relative else "unavailable",
            }
        )
    return selected


def _report_css() -> str:
    return """
:root{--ink:#14231b;--muted:#657069;--line:#dce3de;--card:#fff;--paper:#f4f7f4;--green:#2f7553;--amber:#a86c10;--red:#a33939}*{box-sizing:border-box}body{margin:0;background:var(--paper);color:var(--ink);font:16px/1.55 ui-sans-serif,system-ui,-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif;overflow-wrap:anywhere}.report-shell{max-width:1180px;margin:0 auto;padding:28px}.hero{border-radius:28px;background:#13271d;color:white;padding:54px}.eyebrow,.product-role{font-size:.72rem;text-transform:uppercase;letter-spacing:.14em;font-weight:750}.hero h1{font:500 clamp(2.4rem,6vw,5.3rem)/.98 Georgia,serif;margin:.35rem 0}.hero p{max-width:760px;color:#dbe5de}.report-nav{display:flex;gap:8px;flex-wrap:wrap;padding:18px 0}.report-nav a{color:var(--ink);background:white;border:1px solid var(--line);border-radius:99px;padding:7px 12px;text-decoration:none}.verdict-slot{margin:0 0 20px}.verdict{display:grid;grid-template-columns:auto 1fr;gap:16px;align-items:center;background:white;border:1px solid var(--line);border-radius:18px;padding:16px 20px}.verdict p{margin:.2rem 0;color:var(--muted)}.mark{display:grid;place-items:center;width:44px;height:44px;border-radius:50%;background:#7a827d;color:white;font-weight:800}.verdict.correct .mark{background:var(--green)}.verdict.correct_with_caveats .mark{background:var(--amber)}.verdict.incorrect .mark{background:var(--red)}section{background:white;border:1px solid var(--line);border-radius:22px;padding:28px;margin:18px 0}section h2{font:500 2rem/1.1 Georgia,serif;margin:.1rem 0 1rem}.claim{border-left:4px solid #88a494;padding:4px 0 4px 18px;margin:20px 0}.claim h3{margin:0 0 .25rem}.claim p{margin:.25rem 0}.meta,.caveat{color:var(--muted);font-size:.88rem}.table-scroll{overflow-x:auto;margin:18px 0}table{border-collapse:collapse;min-width:720px;width:100%;font-size:.86rem}th,td{padding:10px;text-align:left;border-bottom:1px solid var(--line);vertical-align:top}th{background:#eef3ef}.product-grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(220px,1fr));gap:16px}.product-card{border:1px solid var(--line);border-radius:18px;overflow:hidden;background:white}.product-card img,.image-placeholder{width:100%;height:220px;object-fit:cover;background:#e8ede9}.image-placeholder{display:grid;place-items:center;color:var(--muted)}.product-card .copy{padding:16px}.product-card h3{margin:.25rem 0}.product-card a{color:inherit}.limitations{padding-left:1.2rem}@media(max-width:640px){.report-shell{padding:14px}.hero{padding:34px 24px}section{padding:22px}.hero h1{font-size:2.7rem}}
""".strip()


def render_brand_fit_report(output_dir: Path) -> dict[str, Any]:
    """Render a Codex-authored Brand Fit model and exact claim ledger to HTML."""

    output = output_dir.expanduser().resolve()
    catalog = _load_json(
        output / "evidence_catalog.json", label="Brand Fit evidence catalog"
    )
    model = _load_json(output / "report_model.json", label="Brand Fit report model")
    if catalog.get("schema_version") != CATALOG_SCHEMA:
        raise BrandFitContractError("Unsupported Brand Fit evidence catalog schema")
    _assert_file_hashes(output, catalog)
    claims, resolved_refs = _validate_model(output, catalog, model)
    ledger = {
        "schema_version": "attribute_reporting.brand_fit_claim_ledger.v1",
        "report_id": catalog["report_id"],
        "evidence_catalog_sha256": _sha256_file(output / "evidence_catalog.json"),
        "report_model_sha256": _sha256_file(output / "report_model.json"),
        "refs": resolved_refs,
    }
    _write_json(output / "claim_ledger.json", ledger)
    values: dict[tuple[str, str], str] = {}
    for ref in resolved_refs:
        for field, value in ref["values"].items():
            values[(str(ref["ref_id"]), str(field))] = str(value)
    selected_products = _selected_products(output, catalog, model)
    claim_html: dict[str, str] = {}
    for claim_id, claim in claims.items():
        body = _render_template(str(claim["text_template"]), values)
        interpretation = _render_template(
            str(claim.get("interpretation") or ""), values
        )
        caveat = _render_template(str(claim.get("caveat") or ""), values)
        claim_html[claim_id] = (
            f'<article class="claim" data-claim-id="{html.escape(claim_id)}">'
            f"<h3>{html.escape(str(claim['headline']))}</h3><p>{body}</p>"
            + (f"<p>{interpretation}</p>" if interpretation else "")
            + (f'<p class="caveat">Caveat: {caveat}</p>' if caveat else "")
            + f'<p class="meta">Confidence: {html.escape(str(claim["confidence"]))}</p></article>'
        )
    section_html: list[str] = []
    for section in model["sections"]:
        section_id = str(section["section_id"])
        body = [
            f'<section id="{html.escape(section_id)}" data-section-id="{html.escape(section_id)}">',
            f"<h2>{html.escape(str(section['title']))}</h2>",
        ]
        if section.get("summary"):
            body.append(f"<p>{html.escape(str(section['summary']))}</p>")
        body.extend(
            claim_html[str(claim_id)] for claim_id in section.get("claim_ids") or []
        )
        body.extend(
            _render_table(output, catalog, str(key))
            for key in section.get("table_keys") or []
        )
        if section_id == "method_and_caveats" and model.get("limitations"):
            body.append('<ul class="limitations">')
            for limitation in model["limitations"]:
                body.append(
                    f'<li data-warning-code="{html.escape(str(limitation["code"]))}">'
                    f'{html.escape(str(limitation["text"]))}</li>'
                )
            body.append("</ul>")
        if section_id == "method_and_caveats":
            presence = catalog.get("retailer_presence") or {}
            product_snapshot = catalog.get("product_data_snapshot") or {}
            body.append(
                '<p class="meta" data-retailer-presence-mode="current_database_snapshot">'
                "Current retailer presence uses the server database snapshot read at "
                f'{html.escape(str(presence.get("read_at") or ""))}. The pinned product cache generation is '
                f'{html.escape(str(product_snapshot.get("batch_generated_at") or ""))} '
                f'(snapshot {html.escape(str(product_snapshot.get("snapshot_sha256") or ""))}). '
                "It is not a claim of a fresh retailer-site scrape.</p>"
            )
        body.append("</section>")
        section_html.append("".join(body))
    product_cards: list[str] = []
    for product in selected_products:
        name = html.escape(str(product["product_name"]))
        if product["pdp_url"]:
            title = f'<a href="{html.escape(product["pdp_url"])}" target="_blank" rel="noreferrer">{name}</a>'
        else:
            title = name
        visual = (
            f'<img src="{html.escape(product["asset_path"])}" alt="{name}">'
            if product["asset_path"]
            else '<div class="image-placeholder">Local image unavailable</div>'
        )
        product_cards.append(
            f'<article class="product-card" data-product-id="{html.escape(product["product_id"])}">'
            f'{visual}<div class="copy"><span class="product-role">{html.escape(product["role"])}</span>'
            f"<h3>{title}</h3><p>{html.escape(str(product['rationale']))}</p></div></article>"
        )
    product_section = (
        '<section data-section-id="product_evidence"><h2>Product evidence</h2>'
        f'<div class="product-grid">{"".join(product_cards)}</div></section>'
        if product_cards
        else ""
    )
    nav = "".join(
        f'<a href="#{html.escape(section_id)}">{html.escape(section_id.replace("_", " ").title())}</a>'
        for section_id in SECTION_IDS
    )
    scope = catalog.get("scope") or {}
    draft = (
        '<!doctype html><html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">'
        f"<title>{html.escape(str(model['title']))}</title><style>{_report_css()}</style></head><body>"
        f'<main class="report-shell" data-report-id="{html.escape(str(model["report_id"]))}">'
        '<header class="hero"><span class="eyebrow">Clara · Brand Fit</span>'
        f"<h1>{html.escape(str(model['title']))}</h1><p>{html.escape(str(model.get('subtitle') or ''))}</p>"
        f'<p>{html.escape(str(scope.get("brand_name") or ""))} · {html.escape(str(scope.get("retailer") or ""))} · {html.escape(str(scope.get("category_key") or ""))}</p></header>'
        f'<nav class="report-nav">{nav}</nav><div class="verdict-slot">{VERDICT_PLACEHOLDER}</div>'
        f'{"".join(section_html)}{product_section}</main></body></html>'
    )
    draft_path = output / "report_draft.html"
    draft_path.write_text(draft, encoding="utf-8")
    manifest = {
        "schema_version": RENDER_SCHEMA,
        "report_id": catalog["report_id"],
        "rendered_at": _utc_now(),
        "evidence_catalog_sha256": _sha256_file(output / "evidence_catalog.json"),
        "report_model_sha256": _sha256_file(output / "report_model.json"),
        "claim_ledger_sha256": _sha256_file(output / "claim_ledger.json"),
        "draft_html": "report_draft.html",
        "draft_html_sha256": _sha256_file(draft_path),
        "selected_products": selected_products,
        "privacy": {"storage": "private_local_only", "uploaded_to_server": False},
    }
    _write_json(output / "render_manifest.json", manifest)
    review_template = {
        "schema_version": REVIEW_SCHEMA,
        "review_id": f"brand-fit-review-{uuid.uuid4().hex}",
        "review_status": "template_requires_codex",
        "reviewer": {
            "execution": "codex_agent",
            "agent_id": "",
            "role": "independent_brand_fit_reviewer",
            "independent_from_author": True,
        },
        "author_agent_id": model["author"]["agent_id"],
        "targets": {
            "report_id": model["report_id"],
            "evidence_catalog_sha256": manifest["evidence_catalog_sha256"],
            "report_model_sha256": manifest["report_model_sha256"],
            "claim_ledger_sha256": manifest["claim_ledger_sha256"],
            "draft_html_sha256": manifest["draft_html_sha256"],
        },
        "claim_reviews": [
            {"claim_id": claim_id, "status": "", "rationale": ""} for claim_id in claims
        ],
        "image_reviews": [
            {
                "product_id": product["product_id"],
                "source": product["source"],
                "source_row_sha256": product["source_row_sha256"],
                "role": product["role"],
                "image_sha256": product["image_sha256"],
                "status": "",
                "rationale": "",
            }
            for product in selected_products
        ],
        "dimensions": {
            dimension: {"status": "", "rationale": ""}
            for dimension in REVIEW_DIMENSIONS
        },
        "overall_status": "",
        "summary": "",
    }
    _write_json(output / "semantic_review.json", review_template)
    return manifest


def _review_state(
    review: Mapping[str, Any],
    *,
    model: Mapping[str, Any],
    manifest: Mapping[str, Any],
) -> tuple[str, list[str]]:
    errors: list[str] = []
    if (
        review.get("schema_version") != REVIEW_SCHEMA
        or review.get("review_status") != "codex_complete"
    ):
        errors.append("Independent Brand Fit review is missing or incomplete")
        return "unable", errors
    reviewer = review.get("reviewer")
    author_id = (
        str(model.get("author", {}).get("agent_id") or "")
        if isinstance(model.get("author"), dict)
        else ""
    )
    if not isinstance(reviewer, dict) or (
        reviewer.get("execution") != "codex_agent"
        or reviewer.get("role") != "independent_brand_fit_reviewer"
        or reviewer.get("independent_from_author") is not True
        or not str(reviewer.get("agent_id") or "")
        or reviewer.get("agent_id") == author_id
        or review.get("author_agent_id") != author_id
    ):
        errors.append("Brand Fit reviewer is not independent from the author")
    expected_targets = {
        "report_id": model.get("report_id"),
        "evidence_catalog_sha256": manifest.get("evidence_catalog_sha256"),
        "report_model_sha256": manifest.get("report_model_sha256"),
        "claim_ledger_sha256": manifest.get("claim_ledger_sha256"),
        "draft_html_sha256": manifest.get("draft_html_sha256"),
    }
    if review.get("targets") != expected_targets:
        errors.append("Brand Fit review targets stale report artifacts")
    statuses: list[str] = []
    claim_reviews = review.get("claim_reviews")
    expected_claim_ids = {
        str(claim.get("claim_id") or "")
        for claim in model.get("claims") or []
        if isinstance(claim, dict)
    }
    if (
        not isinstance(claim_reviews, list)
        or {
            str(item.get("claim_id") or "")
            for item in claim_reviews
            if isinstance(item, dict)
        }
        != expected_claim_ids
        or len(claim_reviews) != len(expected_claim_ids)
    ):
        errors.append("Brand Fit review does not cover every claim exactly once")
    else:
        for item in claim_reviews:
            if (
                not isinstance(item, dict)
                or item.get("status")
                not in {"pass", "caveat", "fail", "unable_to_determine"}
                or not str(item.get("rationale") or "").strip()
            ):
                errors.append("Brand Fit claim review is invalid")
                continue
            statuses.append(str(item["status"]))
    dimensions = review.get("dimensions")
    if not isinstance(dimensions, dict) or set(dimensions) != set(REVIEW_DIMENSIONS):
        errors.append("Brand Fit review does not cover every required dimension")
    else:
        for dimension in REVIEW_DIMENSIONS:
            item = dimensions[dimension]
            if (
                not isinstance(item, dict)
                or item.get("status")
                not in {"pass", "caveat", "fail", "unable_to_determine"}
                or not str(item.get("rationale") or "").strip()
            ):
                errors.append(f"Brand Fit review dimension is invalid: {dimension}")
                continue
            statuses.append(str(item["status"]))
    image_reviews = review.get("image_reviews")
    expected_images = {
        (
            str(item.get("product_id") or ""),
            str(item.get("source") or ""),
            str(item.get("source_row_sha256") or ""),
            str(item.get("role") or ""),
            str(item.get("image_sha256") or ""),
        )
        for item in manifest.get("selected_products") or []
        if isinstance(item, dict)
    }
    actual_images = {
        (
            str(item.get("product_id") or ""),
            str(item.get("source") or ""),
            str(item.get("source_row_sha256") or ""),
            str(item.get("role") or ""),
            str(item.get("image_sha256") or ""),
        )
        for item in image_reviews or []
        if isinstance(item, dict)
    }
    if (
        not isinstance(image_reviews, list)
        or actual_images != expected_images
        or len(image_reviews) != len(expected_images)
    ):
        errors.append("Brand Fit review does not cover every selected local image")
    else:
        for item in image_reviews:
            if (
                item.get("status")
                not in {"pass", "caveat", "fail", "unable_to_determine"}
                or not str(item.get("rationale") or "").strip()
            ):
                errors.append("Brand Fit image review is invalid")
                continue
            statuses.append(str(item["status"]))
    if not str(review.get("summary") or "").strip():
        errors.append("Brand Fit review summary is required")
    if errors:
        return "unable", errors
    expected_overall = (
        "fail"
        if "fail" in statuses
        else (
            "unable_to_determine"
            if "unable_to_determine" in statuses
            else "caveat" if "caveat" in statuses else "pass"
        )
    )
    if review.get("overall_status") != expected_overall:
        return "unable", ["Brand Fit review overall status is inconsistent"]
    return expected_overall, []


def _browser_state(
    output: Path, catalog: Mapping[str, Any], manifest: Mapping[str, Any]
) -> tuple[str, list[str]]:
    if not bool((catalog.get("quality_gates") or {}).get("browser_qa_required")):
        return "not_required", []
    path = output / "browser_qa.json"
    if not path.is_file():
        return "unable", ["Required desktop/mobile browser QA is missing"]
    try:
        qa = _load_json(path, label="Brand Fit browser QA")
    except BrandFitContractError as exc:
        return "unable", [str(exc)]
    if qa.get("schema_version") != "attribute_reporting.browser_qa.v1" or qa.get(
        "report_id"
    ) != catalog.get("report_id"):
        return "unable", ["Brand Fit browser QA schema or report target is invalid"]
    targets = qa.get("targets")
    if (
        not isinstance(targets, dict)
        or targets.get("draft_html_sha256") != manifest.get("draft_html_sha256")
        or Path(str(targets.get("draft_html") or "")).expanduser().resolve()
        != (output / "report_draft.html").resolve()
        or targets.get("render_manifest_sha256")
        != _sha256_file(output / "render_manifest.json")
    ):
        return "unable", ["Brand Fit browser QA targets a stale draft"]
    if qa.get("status") not in {"pass", "fail"}:
        return "unable", ["Desktop/mobile browser QA is blocked or incomplete"]
    if str(qa.get("browser_error") or "").strip():
        return "unable", ["Desktop/mobile browser QA records a browser error"]
    viewports = qa.get("viewports")
    if not isinstance(viewports, list) or len(viewports) != 2:
        return "unable", ["Brand Fit browser QA requires desktop and mobile viewports"]
    expected_viewports = {
        "desktop": (1440, 1000),
        "mobile": (390, 844),
    }
    seen: set[str] = set()
    flattened_findings: list[dict[str, Any]] = []
    measured_failure = False
    for viewport in viewports:
        if not isinstance(viewport, dict):
            return "unable", ["Brand Fit browser QA viewport is invalid"]
        name = str(viewport.get("name") or "")
        if name in seen or expected_viewports.get(name) != (
            viewport.get("width"),
            viewport.get("height"),
        ):
            return "unable", ["Brand Fit browser QA viewport dimensions are invalid"]
        seen.add(name)
        screenshot_value = str(viewport.get("screenshot") or "")
        try:
            screenshot = _contained(
                output, screenshot_value, label="browser screenshot"
            )
        except BrandFitContractError as exc:
            return "unable", [str(exc)]
        if (
            not screenshot.is_file()
            or not SHA256_RE.fullmatch(str(viewport.get("screenshot_sha256") or ""))
            or _sha256_file(screenshot) != viewport.get("screenshot_sha256")
        ):
            return "unable", [f"Brand Fit browser screenshot is stale: {name}"]
        metrics = viewport.get("metrics")
        findings = viewport.get("findings")
        if not isinstance(metrics, dict) or not isinstance(findings, list):
            return "unable", [f"Brand Fit browser metrics are invalid: {name}"]
        expected_statuses = {
            f"browser.{name}.horizontal_overflow": (
                "fail" if bool(metrics.get("horizontalOverflow")) else "pass"
            ),
            f"browser.{name}.local_images": (
                "fail" if bool(metrics.get("brokenImages")) else "pass"
            ),
            f"browser.{name}.asset_locality": (
                "fail" if bool(metrics.get("unsafeAssets")) else "pass"
            ),
            f"browser.{name}.table_scrolling": (
                "fail" if bool(metrics.get("uncontainedWideTables")) else "pass"
            ),
            f"browser.{name}.required_elements": (
                "fail" if bool(metrics.get("missingRequiredElements")) else "pass"
            ),
            f"browser.{name}.product_links": (
                "fail" if bool(metrics.get("unsafeProductLinks")) else "pass"
            ),
        }
        finding_by_code = {
            str(item.get("code") or ""): item
            for item in findings
            if isinstance(item, dict)
        }
        runtime_code = f"browser.{name}.runtime"
        if (
            set(finding_by_code) != {*expected_statuses, runtime_code}
            or len(findings) != len(finding_by_code)
            or any(
                not isinstance(item, dict)
                or item.get("status") not in {"pass", "fail"}
                or not str(item.get("message") or "").strip()
                for item in findings
            )
        ):
            return "unable", [f"Brand Fit browser findings are invalid: {name}"]
        if any(
            finding_by_code[code].get("status") != expected_status
            for code, expected_status in expected_statuses.items()
        ):
            return "unable", [
                f"Brand Fit browser metrics disagree with findings: {name}"
            ]
        runtime = finding_by_code[runtime_code]
        runtime_details = runtime.get("details")
        if not isinstance(runtime_details, list) or (
            (runtime.get("status") == "pass" and runtime_details)
            or (runtime.get("status") == "fail" and not runtime_details)
        ):
            return "unable", [f"Brand Fit browser runtime finding is invalid: {name}"]
        measured_failure = measured_failure or any(
            item.get("status") == "fail" for item in findings
        )
        flattened_findings.extend(dict(item) for item in findings)
    if seen != set(expected_viewports) or qa.get("findings") != flattened_findings:
        return "unable", ["Brand Fit aggregate browser findings are inconsistent"]
    expected_status = "fail" if measured_failure else "pass"
    if qa.get("status") != expected_status:
        return "unable", ["Brand Fit browser status disagrees with measured findings"]
    if measured_failure:
        return "fail", ["Desktop/mobile browser QA failed"]
    return "pass", []


def _mechanical_state(
    output: Path,
    catalog: Mapping[str, Any],
    model: Mapping[str, Any],
    manifest: Mapping[str, Any],
) -> list[str]:
    errors: list[str] = []
    try:
        _assert_file_hashes(output, catalog)
        _claims, refs = _validate_model(output, catalog, model)
        selected_products = _selected_products(
            output, catalog, model, copy_assets=False
        )
        if manifest.get("selected_products") != selected_products:
            errors.append("Brand Fit selected product or image manifest is stale")
        expected_ledger = {
            "schema_version": "attribute_reporting.brand_fit_claim_ledger.v1",
            "report_id": catalog["report_id"],
            "evidence_catalog_sha256": _sha256_file(output / "evidence_catalog.json"),
            "report_model_sha256": _sha256_file(output / "report_model.json"),
            "refs": refs,
        }
        if (
            _load_json(output / "claim_ledger.json", label="Brand Fit claim ledger")
            != expected_ledger
        ):
            errors.append("Brand Fit claim ledger is stale or altered")
        if manifest.get("schema_version") != RENDER_SCHEMA or manifest.get(
            "report_id"
        ) != catalog.get("report_id"):
            errors.append("Brand Fit render manifest is invalid")
        expected_hashes = {
            "evidence_catalog_sha256": _sha256_file(output / "evidence_catalog.json"),
            "report_model_sha256": _sha256_file(output / "report_model.json"),
            "claim_ledger_sha256": _sha256_file(output / "claim_ledger.json"),
            "draft_html_sha256": _sha256_file(output / "report_draft.html"),
        }
        for key, expected in expected_hashes.items():
            if manifest.get(key) != expected:
                errors.append(f"Brand Fit render manifest has a stale {key}")
        draft = (output / "report_draft.html").read_text(encoding="utf-8")
        if draft.count(VERDICT_PLACEHOLDER) != 1:
            errors.append(
                "Brand Fit HTML correctness placeholder is missing or duplicated"
            )
        if (
            f'data-report-id="{html.escape(str(catalog.get("report_id") or ""))}"'
            not in draft
        ):
            errors.append("Brand Fit HTML report id is missing")
        for claim in model.get("claims") or []:
            claim_id = html.escape(str(claim.get("claim_id") or ""))
            if draft.count(f'data-claim-id="{claim_id}"') != 1:
                errors.append(f"Brand Fit HTML claim parity failed: {claim_id}")
        for section_id in SECTION_IDS:
            if draft.count(f'data-section-id="{section_id}"') != 1:
                errors.append(f"Brand Fit HTML section parity failed: {section_id}")
        if re.search(r"<(?:script|img)[^>]+src=[\"']https?://", draft, re.IGNORECASE):
            errors.append("Brand Fit HTML contains an external script or image")
        for product in manifest.get("selected_products") or []:
            if not isinstance(product, dict) or not product.get("asset_path"):
                continue
            path = _contained(
                output, str(product["asset_path"]), label="featured image"
            )
            if not path.is_file() or _sha256_file(path) != product.get("image_sha256"):
                errors.append(f"Featured image changed: {product.get('product_id')}")
    except (BrandFitContractError, OSError, UnicodeError) as exc:
        errors.append(str(exc))
    return errors


def _verdict_html(verdict: str, details: Sequence[str]) -> str:
    key = {
        "Correct": "correct",
        "Correct with caveats": "correct_with_caveats",
        "Incorrect": "incorrect",
        "Unable to determine": "unable_to_determine",
    }[verdict]
    mark = {
        "Correct": "✓",
        "Correct with caveats": "!",
        "Incorrect": "×",
        "Unable to determine": "?",
    }[verdict]
    detail_html = "".join(f"<li>{html.escape(detail)}</li>" for detail in details)
    return (
        f'<div class="verdict {key}" data-correctness-verdict="{key}"><span class="mark">{mark}</span>'
        f"<div><strong>{html.escape(verdict)}</strong><p>Evidence, review, and rendering checks completed.</p>"
        + (f"<ul>{detail_html}</ul>" if detail_html else "")
        + "</div></div>"
    )


def check_brand_fit_report(output_dir: Path) -> dict[str, Any]:
    """Answer Brand Fit correctness with one exact direct verdict label."""

    output = output_dir.expanduser().resolve()
    catalog = _load_json(
        output / "evidence_catalog.json", label="Brand Fit evidence catalog"
    )
    model = _load_json(output / "report_model.json", label="Brand Fit report model")
    manifest = _load_json(
        output / "render_manifest.json", label="Brand Fit render manifest"
    )
    review_path = output / "semantic_review.json"
    try:
        review = _load_json(review_path, label="Brand Fit semantic review")
    except BrandFitContractError as exc:
        review = {"review_load_error": str(exc)}
    mechanical = _mechanical_state(output, catalog, model, manifest)
    review_state, review_findings = _review_state(
        review, model=model, manifest=manifest
    )
    browser_state, browser_findings = _browser_state(output, catalog, manifest)
    caveats: list[str] = []
    source = catalog.get("source_retailer_report") or {}
    if isinstance(source, dict) and source.get("verdict") == "Correct with caveats":
        caveats.append("The source Retailer Signals report is Correct with caveats")
    warning_codes = [str(code) for code in catalog.get("warning_codes") or []]
    caveats.extend(f"Active package warning: {code}" for code in warning_codes)
    image_manifest = catalog.get("local_image_manifest")
    if isinstance(image_manifest, dict) and image_manifest.get("status") != "complete":
        caveats.append("Local product-image hydration is incomplete")
    unavailable_products = [
        str(item.get("product_id") or "")
        for item in manifest.get("selected_products") or []
        if isinstance(item, dict) and item.get("image_status") != "available"
    ]
    caveats.extend(
        f"Selected product has no verified local image: {product_id}"
        for product_id in unavailable_products
    )
    if mechanical:
        verdict = "Incorrect"
    elif review_state == "fail" or browser_state == "fail":
        verdict = "Incorrect"
    elif review_state == "unable" or browser_state == "unable":
        verdict = "Unable to determine"
    elif review_state == "caveat" or caveats:
        verdict = "Correct with caveats"
    else:
        verdict = "Correct"
    details = [*mechanical, *review_findings, *browser_findings, *caveats]
    result = {
        "schema_version": VERDICT_SCHEMA,
        "checked_at": _utc_now(),
        "report_id": catalog.get("report_id"),
        "verdict": verdict,
        "basis": {
            "mechanical": "fail" if mechanical else "pass",
            "semantic_review": review_state,
            "browser_qa": browser_state,
            "source_retailer_report": (
                source.get("verdict") if isinstance(source, dict) else None
            ),
        },
        "mechanical_findings": mechanical,
        "semantic_findings": review_findings,
        "browser_findings": browser_findings,
        "caveats": caveats,
        "targets": {
            "evidence_catalog_sha256": _sha256_file(output / "evidence_catalog.json"),
            "report_model_sha256": _sha256_file(output / "report_model.json"),
            "render_manifest_sha256": _sha256_file(output / "render_manifest.json"),
            "semantic_review_sha256": (
                _sha256_file(review_path) if review_path.is_file() else None
            ),
        },
    }
    _write_json(output / "correctness_verdict.json", result)
    draft = (output / "report_draft.html").read_text(encoding="utf-8")
    report = draft.replace(VERDICT_PLACEHOLDER, _verdict_html(verdict, details), 1)
    (output / "report.html").write_text(report, encoding="utf-8")
    status = (
        "final_ready"
        if verdict in {"Correct", "Correct with caveats"}
        else "not_ready" if verdict == "Incorrect" else "partial"
    )
    review_lines = [
        "# Brand Fit run review",
        "",
        f"- Direct verdict: **{verdict}**",
        f"- Mechanical evidence: {result['basis']['mechanical']}",
        f"- Independent semantic review: {result['basis']['semantic_review']}",
        f"- Desktop/mobile browser QA: {result['basis']['browser_qa']}",
        f"- Source Retailer Signals report: {result['basis']['source_retailer_report']}",
        "- Storage: private local only; no report or image bytes uploaded",
    ]
    if details:
        review_lines.extend(["", "## Findings", ""])
        review_lines.extend(f"- {detail}" for detail in details)
    (output / "codex_run_review.md").write_text(
        "\n".join(review_lines) + "\n", encoding="utf-8"
    )
    outputs = []
    output_specs = [
        ("report.html", "html"),
        ("correctness_verdict.json", "json"),
        ("codex_run_review.md", "markdown"),
        ("evidence_catalog.json", "json"),
        ("report_model.json", "json"),
        ("render_manifest.json", "json"),
        ("claim_ledger.json", "json"),
    ]
    if review_path.is_file():
        output_specs.append(("semantic_review.json", "json"))
    if (output / "browser_qa.json").is_file():
        output_specs.append(("browser_qa.json", "json"))
    for name, kind in output_specs:
        path = output / name
        outputs.append(
            {
                "path": name,
                "kind": kind,
                "sha256": _sha256_file(path),
                "status": "written",
            }
        )
    final = {
        "schema_version": FINAL_SCHEMA,
        "status": status,
        "report_id": catalog.get("report_id"),
        "correctness_verdict": verdict,
        "privacy": {"storage": "private_local_only", "uploaded_to_server": False},
        "outputs": outputs,
    }
    _write_json(output / "final_artifacts.json", final)
    return result
