#!/usr/bin/env python3
"""Secure intake and comparison of a user-controlled TEBENI result.

This module never sends an XBRL instance to an external service. It records a
report that the user chose to upload after the manual TEBENI step, then compares
declared external rule identifiers with the last local validation result.
"""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any, Mapping, Sequence

__all__ = ["record_external_validation_result"]

ALLOWED_SUFFIXES = {".html", ".htm", ".json", ".pdf", ".txt", ".xml"}
MAX_REPORT_BYTES = 20 * 1024 * 1024
RESULTS = {"PASS", "FAIL", "WARNING"}


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def record_external_validation_result(
    case: Mapping[str, Any],
    report_path: Path,
    result: str,
    reported_issues: Sequence[Mapping[str, Any]],
    actor: str,
) -> dict[str, Any]:
    """Build a checksum-bound, non-authoritative external-validation record."""

    if not (case.get("validation") or {}).get("validated_revision_id"):
        raise ValueError("Local validation is required before external report intake")
    if report_path.is_symlink() or not report_path.is_file():
        raise ValueError("External validation report must be a regular local file")
    resolved = report_path.resolve()
    if resolved.suffix.lower() not in ALLOWED_SUFFIXES:
        raise ValueError("Unsupported external validation report type")
    size = resolved.stat().st_size
    if size > MAX_REPORT_BYTES:
        raise ValueError("External validation report exceeds the size limit")
    normalized_result = str(result).upper()
    if normalized_result not in RESULTS:
        raise ValueError("External validation result must be PASS, FAIL, or WARNING")
    normalized_issues: list[dict[str, str]] = []
    seen: set[str] = set()
    for issue in reported_issues:
        rule_id = str(issue["rule_id"]).strip()
        message = str(issue["message"]).strip()
        if not rule_id or not message or rule_id in seen:
            raise ValueError(
                "External issue IDs and messages must be present and unique"
            )
        seen.add(rule_id)
        normalized_issues.append({"rule_id": rule_id, "message": message})
    local_ids = {
        str(issue["rule_id"])
        for issue in (case.get("validation") or {}).get("issues", [])
    }
    external_ids = {item["rule_id"] for item in normalized_issues}
    return {
        "provider": "TEBENI",
        "route": "USER_CONTROLLED_MANUAL_UPLOAD",
        "authoritative_for_filing": False,
        "result": normalized_result,
        "report": {
            "file_name": resolved.name,
            "media_suffix": resolved.suffix.lower(),
            "sha256": _sha256_file(resolved),
            "size_bytes": size,
        },
        "reported_issues": normalized_issues,
        "comparison": {
            "matched_rule_ids": sorted(local_ids & external_ids),
            "external_only_rule_ids": sorted(external_ids - local_ids),
            "local_only_rule_ids": sorted(local_ids - external_ids),
        },
        "validated_revision_id": case["revision_id"],
        "recorded_by": actor,
    }
