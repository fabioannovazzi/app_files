"""Verify the exact reviewed semantic inputs for one selected analysis.

Byte hashes, schema references and declared policy identities are mechanical
contracts. This module does not decide whether the reviewed business meaning
is correct, choose a chart, or approve a professional recommendation.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from profile_dataset import profile_dataset
from semantic_layer import (
    DEFAULT_MANIFEST,
    DEFAULT_SEMANTIC_SCHEMA,
    build_snapshot_attachment,
    canonical_snapshot_fingerprint,
    validate_semantic_layer,
)

__all__ = ["verify_execution_context"]


def _read(path: Path) -> dict[str, Any]:
    result = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(result, dict):
        raise ValueError(f"Expected an object: {path}")
    return result


def _digest(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for block in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def verify_execution_context(
    dataset_path: Path,
    *,
    layer_path: Path,
    profile_path: Path,
    acceptance_path: Path,
    source_paths: list[Path],
    analysis_id: str,
    capability_id: str,
) -> dict[str, Any]:
    """Return current declared semantics only after exact-input verification."""
    receipt_hashes = {
        "acceptance": _digest(acceptance_path),
        "profile": _digest(profile_path),
    }
    acceptance = _read(acceptance_path)
    layer = _read(layer_path)
    profile = _read(profile_path)
    if acceptance.get("result") != "pass":
        raise ValueError("Semantic acceptance did not pass")
    if layer.get("review", {}).get("status") not in {
        "model_reviewed",
        "human_reviewed",
    }:
        raise ValueError("Semantic layer has not been reviewed")
    identities = {
        "dataset": dataset_path,
        "semantic_layer": layer_path,
        "manifest": DEFAULT_MANIFEST,
        "semantic_schema": DEFAULT_SEMANTIC_SCHEMA,
    }
    hashes = {key: _digest(path) for key, path in identities.items()}
    for key, digest in hashes.items():
        if acceptance.get("inputs", {}).get(key, {}).get("sha256") != digest:
            raise ValueError(f"Semantic acceptance is stale or mismatched: {key}")
    if (acceptance.get("semantic_layer_id"), acceptance.get("semantic_version")) != (
        layer.get("semantic_layer_id"),
        layer.get("semantic_version"),
    ):
        raise ValueError("Semantic acceptance identity/version mismatch")
    source_hashes = sorted(_digest(path) for path in source_paths)
    expected_sources = sorted(
        item.get("sha256", "")
        for item in acceptance.get("inputs", {}).get("semantic_sources", [])
    )
    if not source_hashes or source_hashes != expected_sources:
        raise ValueError("Semantic source evidence is missing or changed")
    parser = profile.get("source", {})
    fresh = profile_dataset(
        dataset_path,
        dataset_id=profile.get("dataset_id"),
        sheet_name=parser.get("sheet_name"),
        csv_options=parser.get("parser_options"),
    )
    fingerprint = canonical_snapshot_fingerprint(fresh)
    if fingerprint != canonical_snapshot_fingerprint(profile):
        raise ValueError(
            "Dataset profile does not describe the current parsed snapshot"
        )
    origins = [
        item
        for item in acceptance.get("snapshot_reuse_proof", [])
        if item.get("case_id") == "origin_snapshot"
    ]
    if len(origins) != 1 or origins[0].get("snapshot_fingerprint") != fingerprint:
        raise ValueError("Acceptance does not bind this worksheet/parser/snapshot")
    validation = validate_semantic_layer(layer, fresh, _read(DEFAULT_MANIFEST))
    if (
        validation["status"] != "contract_valid"
        or validation["semantic_readiness"] != "ready_as_scoped_semantic_input"
    ):
        raise ValueError("Current semantic layer is not valid for scoped execution")
    matches = [
        item
        for item in validation["policy_results"]
        if item["analysis_id"] == analysis_id
    ]
    if (
        len(matches) != 1
        or not matches[0].get("usable_as_semantic_input")
        or capability_id not in matches[0].get("candidate_capability_ids", [])
    ):
        raise ValueError(
            "Selected capability is not supported by the reviewed analysis policy"
        )
    policy = next(
        item
        for item in layer["analysis_policies"]
        if item["analysis_id"] == analysis_id
    )
    attachment = build_snapshot_attachment(layer, fresh)
    if attachment["attachment_status"] != "attached":
        raise ValueError("Semantic snapshot attachment is rejected")
    # Detect a caller changing source bytes while the profile was being read.
    if hashes != {
        key: _digest(path) for key, path in identities.items()
    } or source_hashes != sorted(_digest(path) for path in source_paths):
        raise ValueError("Semantic inputs changed during verification")
    if receipt_hashes != {
        "acceptance": _digest(acceptance_path),
        "profile": _digest(profile_path),
    }:
        raise ValueError("Semantic receipts changed during verification")
    return {
        "status": "reviewed_input_identity_verified",
        "semantic_layer_id": layer["semantic_layer_id"],
        "semantic_version": layer["semantic_version"],
        "analysis_id": analysis_id,
        "capability_id": capability_id,
        "input_sha256": hashes,
        "semantic_source_sha256": source_hashes,
        "acceptance_sha256": receipt_hashes["acceptance"],
        "profile_sha256": receipt_hashes["profile"],
        "snapshot_fingerprint": fingerprint,
        "parser_settings": {
            "sheet_name": parser.get("sheet_name"),
            "csv_options": parser.get("parser_options"),
        },
        "capability_contract": _read(DEFAULT_MANIFEST)["capabilities"][capability_id],
        "policy": policy,
        "metrics": layer["metrics"],
        "dimensions": layer["dimensions"],
        "periods": layer["periods"],
        "snapshot_attachment": attachment,
        "boundary": "Exact reviewed input and policy wiring only; effective recipe compilation and professional deliverable approval are separate checks.",
    }
