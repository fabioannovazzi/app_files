#!/usr/bin/env python3
"""Seal and authorize purpose-bound model use for Financial Analysis."""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

SCRIPTS_DIR = Path(__file__).resolve().parent
PLUGIN_ROOT = SCRIPTS_DIR.parent
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

for _vendor_root in (
    PLUGIN_ROOT / "vendor" / "modules",
    PLUGIN_ROOT.parent.parent / "vendor" / "modules",
    PLUGIN_ROOT.parent / "_shared" / "vendor" / "modules",
):
    if (_vendor_root / "vera_assurance").is_dir():
        if str(_vendor_root) not in sys.path:
            sys.path.insert(0, str(_vendor_root))
        break

from managed_case_inputs import declared_case_input_bindings  # noqa: E402
from preparation_contract_kernel import (  # noqa: E402
    canonical_json_sha256,
    file_snapshot_beneath,
)
from vera_assurance import (  # noqa: E402
    AssuranceContractError,
    load_client_engagement_context_file,
    validate_client_workflow_run,
)

SCHEMA_VERSION = "vera.model_use_manifest.v1"
REQUEST_SCHEMA_VERSION = "vera.model_use_request.v1"
MANIFEST_NAME = "model_use_manifest.json"
REQUEST_DIR_NAME = "model_drilldowns"
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")


class ModelUseError(ValueError):
    """Raised when a model-use manifest or evidence request is invalid."""


def is_vera_managed_host() -> bool:
    root = PLUGIN_ROOT.resolve()
    host_manifest = root.parent.parent / ".codex-plugin" / "plugin.json"
    return (
        root.name == "financial-analysis"
        and root.parent.name == "modules"
        and root.parent.parent.name == "vera"
    ) or (
        host_manifest.is_file()
        and json.loads(host_manifest.read_text(encoding="utf-8")).get("name")
        == "vera"
    )


def _snapshot(path: Path) -> dict[str, Any]:
    byte_count, sha256 = file_snapshot_beneath(path, root=path.parent)
    return {"byte_count": byte_count, "sha256": sha256}


def _artifact_purpose(path: str) -> str:
    if path == "reconciliation.json":
        return "mechanical_reconciliation_and_stop_conditions"
    if path == "prepared_evidence_manifest.json":
        return "prepared_evidence_lineage_and_review_boundary"
    if path.endswith("_audit.json"):
        return "contract_and_replay_audit"
    if path.endswith(".csv"):
        return "purpose_bound_prepared_table"
    if path.endswith(".json"):
        return "purpose_bound_prepared_context"
    return "purpose_bound_prepared_artifact"


def build_manifest(
    *,
    pack_id: str,
    case_path: Path,
    case_sha256: str,
    source_bindings: Sequence[tuple[str, Path]],
    output_artifacts: Sequence[Mapping[str, Any]],
    status: str,
) -> dict[str, Any]:
    """Build the sealed post-mapping model-use contract."""

    case_root = Path(case_path).resolve().parent
    sources: list[dict[str, Any]] = []
    for artifact_id, source_path in source_bindings:
        resolved = Path(source_path).resolve()
        try:
            resolved.relative_to(case_root)
        except ValueError as exc:
            raise ModelUseError("financial source is outside the reviewed case root") from exc
        sources.append(
            {
                "artifact_id": artifact_id,
                **_snapshot(resolved),
            }
        )
    default_artifacts = [
        {
            "artifact_id": str(item["artifact_ref"]),
            "path": str(item["path"]),
            "byte_count": int(item["byte_count"]),
            "sha256": str(item["sha256"]),
            "purpose": _artifact_purpose(str(item["path"])),
        }
        for item in output_artifacts
        if str(item.get("path")) != MANIFEST_NAME
    ]
    content: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "workflow_id": "financial-analysis",
        "pack_id": pack_id,
        "phase": "post_semantic_mapping",
        "status": status,
        "source_population": {
            "processing_scope": "complete_reviewed_in_scope_population",
            "case_sha256": case_sha256,
            "source_artifacts": sources,
        },
        "semantic_boundary": {
            "status": "reviewed_contracts_and_crosswalks_required",
            "default_source_access": "prepared_artifacts_first",
            "automatic_anonymization": False,
            "automatic_pseudonymization": False,
        },
        "default_model_use": {
            "artifacts": default_artifacts,
            "raw_source_files_included": False,
        },
        "evidence_drilldown": {
            "mode": "explicit_named_source_request",
            "request_schema_version": REQUEST_SCHEMA_VERSION,
            "receipt_directory": REQUEST_DIR_NAME,
            "requires": [
                "specific_unresolved_professional_question",
                "named_source_artifact_id",
                "reason",
            ],
            "semantic_relevance_decided_by": "model_and_professional",
        },
        "runtime_account_boundary": {
            "selected_by": "firm_or_user",
            "verified_by_vera": False,
            "per_case_record_required": False,
        },
    }
    return {**content, "content_sha256": canonical_json_sha256(content)}


def validate_manifest(value: object) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        raise ModelUseError("model-use manifest must be an object")
    manifest = dict(value)
    if manifest.get("schema_version") != SCHEMA_VERSION:
        raise ModelUseError("model-use manifest schema_version is invalid")
    if manifest.get("workflow_id") != "financial-analysis":
        raise ModelUseError("model-use manifest workflow_id is invalid")
    supplied = manifest.pop("content_sha256", None)
    if not isinstance(supplied, str) or not SHA256_RE.fullmatch(supplied):
        raise ModelUseError("model-use manifest content_sha256 is invalid")
    if canonical_json_sha256(manifest) != supplied:
        raise ModelUseError("model-use manifest content_sha256 is stale")
    manifest["content_sha256"] = supplied
    sources = manifest.get("source_population", {}).get("source_artifacts")
    if not isinstance(sources, list) or not sources:
        raise ModelUseError("model-use manifest source_artifacts must not be empty")
    return manifest


def write_manifest(output_boundary: Any, manifest: Mapping[str, Any]) -> None:
    validate_manifest(manifest)
    output_boundary.write_json_exclusive(MANIFEST_NAME, dict(manifest))


def _load_json(path: Path) -> dict[str, Any]:
    value = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ModelUseError(f"{path.name} must contain an object")
    return value


def _canonical_request(
    *,
    manifest: Mapping[str, Any],
    source_artifact_id: str,
    reason: str,
    selectors: Sequence[str],
) -> dict[str, Any]:
    request = {
        "schema_version": REQUEST_SCHEMA_VERSION,
        "workflow_id": "financial-analysis",
        "manifest_sha256": manifest["content_sha256"],
        "source_artifact_id": source_artifact_id,
        "reason": reason,
        "selectors": sorted(set(selectors)),
    }
    return {**request, "request_sha256": canonical_json_sha256(request)}


def authorize_evidence(
    *,
    manifest_path: Path,
    case_path: Path,
    pack_id: str,
    source_artifact_id: str,
    reason: str,
    selectors: Sequence[str],
    client_engagement_path: Path | None,
) -> dict[str, Any]:
    manifest_path = Path(manifest_path).resolve()
    case_path = Path(case_path).resolve()
    manifest = validate_manifest(_load_json(manifest_path))
    if manifest.get("pack_id") != pack_id:
        raise ModelUseError("model-use manifest pack_id does not match the request")
    reason = reason.strip()
    if not reason:
        raise ModelUseError("evidence request reason must not be empty")
    if len(reason) > 1_000:
        raise ModelUseError("evidence request reason must be at most 1000 characters")
    selectors = tuple(selector.strip() for selector in selectors if selector.strip())
    if len(selectors) > 20 or any(len(selector) > 500 for selector in selectors):
        raise ModelUseError("evidence request selectors exceed the supported bounds")
    bindings = dict(declared_case_input_bindings(case_path, pack_id))
    if source_artifact_id not in bindings:
        raise ModelUseError("evidence request names an unknown source artifact")
    source_path = bindings[source_artifact_id].resolve()
    listed = {
        str(item["artifact_id"]): item
        for item in manifest["source_population"]["source_artifacts"]
    }
    if source_artifact_id not in listed:
        raise ModelUseError("source artifact is not sealed in the model-use manifest")
    current = _snapshot(source_path)
    if (
        current["byte_count"] != listed[source_artifact_id]["byte_count"]
        or current["sha256"] != listed[source_artifact_id]["sha256"]
    ):
        raise ModelUseError("requested source artifact no longer matches the sealed manifest")
    if client_engagement_path is not None:
        context = load_client_engagement_context_file(
            client_engagement_path,
            expected_workflow_id="financial-analysis",
            input_paths=[case_path],
            output_dir=manifest_path.parent,
        )
        validate_client_workflow_run(
            context,
            expected_workflow_id="financial-analysis",
            input_paths=[case_path, *bindings.values()],
            output_dir=manifest_path.parent,
        )
    elif os.environ.get("VERA_COMPONENT_HOST") == "1" or is_vera_managed_host():
        raise ModelUseError("Vera evidence requests require --client-engagement")
    request = _canonical_request(
        manifest=manifest,
        source_artifact_id=source_artifact_id,
        reason=reason,
        selectors=selectors,
    )
    request_dir = manifest_path.parent / REQUEST_DIR_NAME
    request_dir.mkdir(parents=True, exist_ok=True)
    receipt_path = request_dir / f"evidence_request_{request['request_sha256'][:24]}.json"
    receipt_content = {
        **request,
        "source_sha256": current["sha256"],
        "source_byte_count": current["byte_count"],
        "authorization": "open_only_this_named_source_for_the_recorded_question",
    }
    receipt = {
        **receipt_content,
        "content_sha256": canonical_json_sha256(receipt_content),
    }
    rendered = json.dumps(receipt, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    if receipt_path.exists():
        if receipt_path.read_text(encoding="utf-8") != rendered:
            raise ModelUseError("existing evidence request receipt does not match")
    else:
        receipt_path.write_text(rendered, encoding="utf-8")
    return {
        "ok": True,
        "source_artifact_id": source_artifact_id,
        "authorized_source_path": str(source_path),
        "receipt_path": str(receipt_path),
        "request_sha256": request["request_sha256"],
    }


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--case", type=Path, required=True)
    parser.add_argument("--pack", required=True)
    parser.add_argument("--source-artifact-id", required=True)
    parser.add_argument("--reason", required=True)
    parser.add_argument("--selector", action="append", default=[])
    parser.add_argument("--client-engagement", type=Path)
    args = parser.parse_args(argv)
    try:
        result = authorize_evidence(
            manifest_path=args.manifest,
            case_path=args.case,
            pack_id=args.pack,
            source_artifact_id=args.source_artifact_id,
            reason=args.reason,
            selectors=args.selector,
            client_engagement_path=args.client_engagement,
        )
    except (AssuranceContractError, ModelUseError, OSError, ValueError) as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, sort_keys=True))
        return 2
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
