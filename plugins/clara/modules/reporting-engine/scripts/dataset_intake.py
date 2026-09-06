"""Profile one dataset snapshot and create or reuse reviewed business semantics.

This helper deliberately performs no semantic classification. It prepares the
profile and authoring context that a model or human reviews, or it validates and
attaches an explicitly supplied semantic layer for the same dataset contract.
"""

from __future__ import annotations

# Direct CLI calls must select dependencies before importing workflow modules.
if __name__ == "__main__":
    import runpy as _runpy
    from pathlib import Path as _Path

    for _parent in _Path(__file__).resolve().parents:
        _launcher = _parent / "scripts" / "self_relaunch.py"
        if not _launcher.is_file():
            _launcher = _parent / "clara" / "scripts" / "self_relaunch.py"
        if _launcher.is_file():
            _runpy.run_path(str(_launcher))["ensure_running_in_managed_venv"](__file__)
            break
    else:
        # Standalone components retain their host's dependency setup.
        if any(
            (_p / "components.json").is_file()
            for _p in _Path(__file__).resolve().parents
        ):
            raise SystemExit(
                "Managed Python launcher is missing; rebuild the plugin package."
            )

import argparse
import importlib.util
import json
import logging
import re
from pathlib import Path
from types import ModuleType
from typing import Any, Sequence

__all__ = ["main", "run_dataset_intake"]

LOGGER = logging.getLogger(__name__)
REPORTING_ENGINE_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_MANIFEST = REPORTING_ENGINE_ROOT / "catalog" / "selection_manifest.json"
DATASET_CONTRACT_ID_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")

PROFILE_FILENAME = "dataset_profile.json"
DRAFT_LAYER_FILENAME = "semantic_layer.draft.json"
AUTHORING_CONTEXT_FILENAME = "semantic_authoring_context.json"
ATTACHMENT_FILENAME = "snapshot_attachment.json"
RECEIPT_FILENAME = "dataset_intake.json"


def _load_script(module_name: str, filename: str) -> ModuleType:
    module_path = Path(__file__).resolve().parent / filename
    spec = importlib.util.spec_from_file_location(module_name, module_path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Could not load Reporting Engine helper: {module_path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _load_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"Expected a JSON object in {path}.")
    return payload


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )


def _prepare_output_dir(output_dir: Path, filenames: Sequence[str]) -> Path:
    resolved = output_dir.expanduser().resolve()
    if resolved.exists() and not resolved.is_dir():
        raise ValueError(f"Output path is not a directory: {resolved}")
    resolved.mkdir(parents=True, exist_ok=True)
    existing = [
        resolved / filename for filename in filenames if (resolved / filename).exists()
    ]
    if existing:
        paths = ", ".join(str(path) for path in existing)
        raise FileExistsError(
            f"Dataset intake will not overwrite existing artifacts: {paths}"
        )
    return resolved


def _artifact_paths(output_dir: Path, *, reuse_existing_layer: bool) -> dict[str, Path]:
    paths = {
        "dataset_profile": output_dir / PROFILE_FILENAME,
        "semantic_authoring_context": output_dir / AUTHORING_CONTEXT_FILENAME,
        "dataset_intake": output_dir / RECEIPT_FILENAME,
    }
    if reuse_existing_layer:
        paths["snapshot_attachment"] = output_dir / ATTACHMENT_FILENAME
    else:
        paths["semantic_layer_draft"] = output_dir / DRAFT_LAYER_FILENAME
    return paths


def _mapped_role_availability(
    layer: dict[str, Any], attachment: dict[str, Any]
) -> dict[str, str]:
    compatibility = attachment.get("compatibility") or {}
    concept_results = {
        str(result.get("concept_id")): result
        for result in compatibility.get("concept_results") or []
        if isinstance(result, dict) and result.get("concept_id")
    }
    availability: dict[str, str] = {}
    mappings = layer.get("business_metric_mappings") or {}
    for role, raw_mapping in mappings.items():
        if not isinstance(raw_mapping, dict) or raw_mapping.get("state") != "mapped":
            continue
        metric_id = str(raw_mapping.get("metric_id") or "")
        availability[str(role)] = str(
            (concept_results.get(metric_id) or {}).get("status") or "missing"
        )
    return availability


def _receipt_artifacts(paths: dict[str, Path]) -> dict[str, str]:
    return {name: str(path) for name, path in paths.items()}


def run_dataset_intake(
    dataset_path: Path,
    *,
    dataset_contract_id: str,
    output_dir: Path,
    semantic_layer_path: Path | None = None,
    sheet_name: str | None = None,
) -> dict[str, Any]:
    """Prepare first-upload semantic review or reuse one reviewed contract."""

    contract_id = dataset_contract_id.strip()
    if not DATASET_CONTRACT_ID_PATTERN.fullmatch(contract_id):
        raise ValueError(
            "dataset_contract_id must start with a letter or number and contain "
            "only letters, numbers, dots, underscores, or hyphens."
        )

    dataset = dataset_path.expanduser().resolve()
    if not dataset.is_file():
        raise FileNotFoundError(f"Dataset does not exist: {dataset}")
    existing_layer_path = (
        semantic_layer_path.expanduser().resolve()
        if semantic_layer_path is not None
        else None
    )
    if existing_layer_path is not None and not existing_layer_path.is_file():
        raise FileNotFoundError(f"Semantic layer does not exist: {existing_layer_path}")

    reuse_existing_layer = existing_layer_path is not None
    filenames = [
        PROFILE_FILENAME,
        AUTHORING_CONTEXT_FILENAME,
        RECEIPT_FILENAME,
        ATTACHMENT_FILENAME if reuse_existing_layer else DRAFT_LAYER_FILENAME,
    ]
    resolved_output_dir = _prepare_output_dir(output_dir, filenames)
    paths = _artifact_paths(
        resolved_output_dir,
        reuse_existing_layer=reuse_existing_layer,
    )

    profiler = _load_script(
        "reporting_engine_dataset_intake_profiler", "profile_dataset.py"
    )
    semantic = _load_script(
        "reporting_engine_dataset_intake_semantics", "semantic_layer.py"
    )
    manifest = _load_json(DEFAULT_MANIFEST)
    profile = profiler.profile_dataset(
        dataset,
        dataset_id=contract_id,
        sheet_name=sheet_name,
    )
    _write_json(paths["dataset_profile"], profile)

    if existing_layer_path is None:
        layer = semantic.build_semantic_layer_scaffold(
            profile,
            dataset_contract_id=contract_id,
            profile_locator=str(paths["dataset_profile"]),
        )
        context = semantic.build_authoring_context(
            profile,
            manifest,
            semantic_layer=layer,
        )
        mapping_summary = semantic.summarize_business_metric_mappings(layer)
        receipt = {
            "schema_version": "0.1",
            "status": "review_required",
            "mode": "first_upload",
            "reason": "source_backed_semantic_review_required",
            "dataset_contract_id": contract_id,
            "semantic_layer_dataset_contract_id": None,
            "business_metric_mappings": mapping_summary,
            "artifacts": _receipt_artifacts(paths),
            "next_action": (
                "Review the dataset and available business evidence, then author "
                "Sales, Discount, and COGS as mapped, absent, ambiguous, or unknown "
                "in the persistent semantic layer."
            ),
            "boundary": (
                "The intake profiler and scaffold do not identify business meaning "
                "from headers or values."
            ),
        }
        _write_json(paths["semantic_layer_draft"], layer)
        _write_json(paths["semantic_authoring_context"], context)
        _write_json(paths["dataset_intake"], receipt)
        return receipt

    layer = _load_json(existing_layer_path)
    raw_layer_contract = layer.get("dataset_contract")
    layer_contract = raw_layer_contract if isinstance(raw_layer_contract, dict) else {}
    layer_contract_id = layer_contract.get("dataset_contract_id")
    if layer_contract_id != contract_id:
        receipt = {
            "schema_version": "0.1",
            "status": "rejected",
            "mode": "existing_semantic_layer",
            "reason": "dataset_contract_id_mismatch",
            "dataset_contract_id": contract_id,
            "semantic_layer_dataset_contract_id": layer_contract_id,
            "business_metric_mappings": (
                semantic.summarize_business_metric_mappings(layer)
            ),
            "artifacts": _receipt_artifacts(
                {
                    "dataset_profile": paths["dataset_profile"],
                    "dataset_intake": paths["dataset_intake"],
                }
            ),
            "next_action": (
                "Supply the reviewed semantic layer for this exact dataset contract; "
                "schema similarity cannot establish dataset identity."
            ),
            "boundary": ("The supplied semantic layer was not attached or replaced."),
        }
        _write_json(paths["dataset_intake"], receipt)
        return receipt

    validation = semantic.validate_semantic_layer(layer, profile, manifest)
    attachment = semantic.build_snapshot_attachment(layer, profile)
    attachment["semantic_contract_validation"] = {
        "status": validation["status"],
        "semantic_readiness": validation["semantic_readiness"],
        "errors": validation["errors"],
    }
    if validation["status"] != "contract_valid":
        attachment["attachment_status"] = "rejected"
    context = semantic.build_authoring_context(
        profile,
        manifest,
        semantic_layer=layer,
    )
    mapping_summary = semantic.summarize_business_metric_mappings(layer)
    mapped_role_availability = _mapped_role_availability(layer, attachment)
    unavailable_mapped_roles = sorted(
        role
        for role, status in mapped_role_availability.items()
        if status != "compatible"
    )

    review = layer.get("review")
    review_status = review.get("status") if isinstance(review, dict) else None
    if attachment["attachment_status"] != "attached":
        status = "rejected"
        reason = "semantic_contract_or_snapshot_rejected"
    elif (
        review_status in {"model_reviewed", "human_reviewed"}
        and mapping_summary["status"] == "resolved"
        and not unavailable_mapped_roles
    ):
        status = "mapping_reused"
        reason = "reviewed_business_metric_mapping_reused"
    else:
        status = "review_required"
        reason = (
            "mapped_metric_unavailable_in_snapshot"
            if unavailable_mapped_roles
            else "business_metric_mapping_review_required"
        )

    receipt = {
        "schema_version": "0.1",
        "status": status,
        "mode": "existing_semantic_layer",
        "reason": reason,
        "dataset_contract_id": contract_id,
        "semantic_layer_dataset_contract_id": layer_contract_id,
        "semantic_layer_id": layer.get("semantic_layer_id"),
        "semantic_version": layer.get("semantic_version"),
        "semantic_review_status": review_status,
        "semantic_contract_status": validation["status"],
        "semantic_readiness": validation["semantic_readiness"],
        "snapshot_attachment_status": attachment["attachment_status"],
        "snapshot_compatibility_status": (
            (attachment.get("compatibility") or {}).get("status")
        ),
        "business_metric_mappings": mapping_summary,
        "mapped_role_snapshot_availability": mapped_role_availability,
        "unavailable_mapped_roles": unavailable_mapped_roles,
        "artifacts": _receipt_artifacts(paths),
        "next_action": (
            "Use the attached reviewed mapping for this snapshot."
            if status == "mapping_reused"
            else (
                "Resolve the reported semantic or snapshot incompatibility; do not "
                "replace the persistent layer automatically."
                if status == "rejected"
                else (
                    "Review unresolved or unavailable Sales, Discount, and COGS "
                    "roles before using them."
                )
            )
        ),
        "boundary": (
            "Reuse preserves the supplied semantic version and never rewrites the "
            "persistent semantic layer."
        ),
    }
    _write_json(paths["snapshot_attachment"], attachment)
    _write_json(paths["semantic_authoring_context"], context)
    _write_json(paths["dataset_intake"], receipt)
    return receipt


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("dataset", type=Path)
    parser.add_argument("--dataset-contract-id", required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--semantic-layer", type=Path)
    parser.add_argument("--sheet-name")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    """Run dataset intake and return non-zero only when intake is rejected."""

    args = _parser().parse_args(argv)
    try:
        receipt = run_dataset_intake(
            args.dataset,
            dataset_contract_id=args.dataset_contract_id,
            output_dir=args.output_dir,
            semantic_layer_path=args.semantic_layer,
            sheet_name=args.sheet_name,
        )
    except (FileNotFoundError, FileExistsError, OSError, ValueError) as error:
        LOGGER.error("%s", error)
        return 1
    LOGGER.info("%s", (args.output_dir / RECEIPT_FILENAME).expanduser().resolve())
    return 1 if receipt["status"] == "rejected" else 0


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    raise SystemExit(main())
