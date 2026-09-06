"""Bind one Reporting Engine result to Clara's advisory evidence lineage."""

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
import hashlib
import json
import logging
from pathlib import Path
from typing import Any, Mapping, Sequence

from advisor_case_core import record_analysis_contribution

__all__ = ["ReportingContributionError", "record_reporting_contribution", "main"]

LOGGER = logging.getLogger(__name__)


class ReportingContributionError(ValueError):
    """Raised when a Reporting Engine result cannot be bound safely."""


def _load_object(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ReportingContributionError(
            f"cannot read JSON object {path}: {exc}"
        ) from exc
    if not isinstance(payload, dict):
        raise ReportingContributionError(f"JSON payload must be an object: {path}")
    return payload


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _canonical_json_sha256(value: Any) -> str:
    encoded = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _resolve(reference: str, *, base_dir: Path) -> Path:
    path = Path(reference).expanduser()
    if not path.is_absolute():
        path = base_dir / path
    resolved = path.resolve()
    if not resolved.is_file():
        raise ReportingContributionError(
            f"reporting artifact does not exist: {resolved}"
        )
    return resolved


def _verify_declared_artifact(
    path: Path,
    record: Mapping[str, Any],
    *,
    subject: str,
) -> None:
    expected_hash = str(record.get("sha256", ""))
    expected_size = record.get("size_bytes")
    if _sha256(path) != expected_hash or path.stat().st_size != expected_size:
        raise ReportingContributionError(
            f"{subject} bytes do not match render_manifest.json"
        )


def _artifact_receipt(path: Path, *, case_dir: Path) -> dict[str, Any]:
    resolved = path.resolve()
    try:
        reference = resolved.relative_to(case_dir.resolve()).as_posix()
        path_reference = "case_relative"
    except ValueError:
        reference = str(resolved)
        path_reference = "absolute"
    return {
        "path": reference,
        "path_reference": path_reference,
        "sha256": _sha256(resolved),
        "byte_count": resolved.stat().st_size,
    }


def _verify_render_manifest(
    manifest_path: Path,
    manifest: Mapping[str, Any],
) -> tuple[Path, list[Path], list[Path]]:
    if manifest.get("schema_version") != "0.2" or manifest.get("owner") != (
        "clara.reporting-engine"
    ):
        raise ReportingContributionError(
            "render manifest is not an authoritative Clara Reporting Engine 0.2 result"
        )
    runner = manifest.get("runner")
    proof = manifest.get("render_proof")
    if not isinstance(runner, dict) or runner.get("returncode") != 0:
        raise ReportingContributionError("Reporting Engine runner did not complete")
    if not isinstance(proof, dict) or proof.get("status") not in {
        "rendered",
        "not_required_data_only",
    }:
        raise ReportingContributionError("Reporting Engine render proof did not pass")

    evidence = manifest.get("evidence")
    if not isinstance(evidence, dict):
        raise ReportingContributionError("render manifest has no evidence object")
    input_record = evidence.get("input")
    if not isinstance(input_record, dict):
        raise ReportingContributionError("render manifest has no input receipt")
    input_path = _resolve(
        str(input_record.get("path", manifest.get("input_file", ""))),
        base_dir=manifest_path.parent,
    )
    _verify_declared_artifact(input_path, input_record, subject="reporting input")

    output_dir = _resolve_output_dir(manifest_path, manifest)
    output_records = evidence.get("outputs")
    if not isinstance(output_records, list) or not output_records:
        raise ReportingContributionError("render manifest has no output receipts")
    output_paths: list[Path] = []
    for index, record in enumerate(output_records):
        if not isinstance(record, dict):
            raise ReportingContributionError("render output receipt must be an object")
        output_path = _resolve(str(record.get("path", "")), base_dir=output_dir)
        _verify_declared_artifact(
            output_path,
            record,
            subject=f"reporting output {index}",
        )
        output_paths.append(output_path)
    if evidence.get("output_set_sha256") != _canonical_json_sha256(output_records):
        raise ReportingContributionError("reporting output-set digest does not match")

    verification_paths = [manifest_path.resolve()]
    recipe = evidence.get("recipe")
    if isinstance(recipe, dict) and recipe.get("path"):
        recipe_path = _resolve(str(recipe["path"]), base_dir=manifest_path.parent)
        _verify_declared_artifact(recipe_path, recipe, subject="reporting recipe")
        verification_paths.append(recipe_path)
    return input_path, output_paths, verification_paths


def _resolve_output_dir(manifest_path: Path, manifest: Mapping[str, Any]) -> Path:
    reference = str(manifest.get("output_dir", "")).strip()
    if not reference:
        return manifest_path.parent.resolve()
    path = Path(reference).expanduser()
    if not path.is_absolute():
        path = manifest_path.parent / path
    resolved = path.resolve()
    if not resolved.is_dir():
        raise ReportingContributionError(
            f"reporting output directory does not exist: {resolved}"
        )
    return resolved


def record_reporting_contribution(
    case_dir: Path,
    render_manifest_path: Path,
    contribution: Mapping[str, Any],
    *,
    additional_verification_artifacts: Sequence[Path] = (),
) -> dict[str, Any]:
    """Record model-authored calculation meaning with exact mechanical receipts."""

    case_dir = case_dir.resolve()
    manifest_path = render_manifest_path.resolve()
    manifest = _load_object(manifest_path)
    input_path, output_paths, verification_paths = _verify_render_manifest(
        manifest_path,
        manifest,
    )
    verification_paths.extend(
        path.resolve() for path in additional_verification_artifacts
    )
    for path in verification_paths:
        if not path.is_file():
            raise ReportingContributionError(
                f"verification artifact does not exist: {path}"
            )

    evidence_fields = contribution.get("evidence")
    claim = contribution.get("claim")
    judgements = contribution.get("judgement_entries", [])
    if not isinstance(evidence_fields, dict) or not isinstance(claim, dict):
        raise ReportingContributionError(
            "contribution requires model-authored evidence and claim objects"
        )
    if not isinstance(judgements, list):
        raise ReportingContributionError("judgement_entries must be an array")
    receipt_id = str(evidence_fields.get("id", ""))
    if not receipt_id:
        raise ReportingContributionError("contribution evidence.id is required")
    dependency = claim.get("dependency")
    links = claim.get("evidence_links")
    if (
        not isinstance(dependency, dict)
        or dependency.get("calculation_evidence_id") != receipt_id
    ):
        raise ReportingContributionError(
            "claim dependency.calculation_evidence_id must reference contribution evidence.id"
        )
    if not isinstance(links, list) or receipt_id not in {
        str(link.get("evidence_id")) for link in links if isinstance(link, dict)
    }:
        raise ReportingContributionError(
            "claim evidence_links must reference contribution evidence.id"
        )

    all_paths = [input_path, *output_paths, *verification_paths]
    unique_paths = list(dict.fromkeys(path.resolve() for path in all_paths))
    artifacts = [_artifact_receipt(path, case_dir=case_dir) for path in unique_paths]
    receipt = {
        "id": receipt_id,
        "evidence_type": "calculation_run",
        "recorded_at": evidence_fields.get("recorded_at"),
        "recorded_by": evidence_fields.get("recorded_by"),
        "capture_status": "captured",
        "source": {
            "material_ids": evidence_fields.get("material_ids", []),
            "url": "",
            "locator": str(manifest.get("capability_id", "Reporting Engine run")),
            "artifact_refs": artifacts,
        },
        "observation": evidence_fields.get("observation"),
        "scope": evidence_fields.get("scope"),
        "limitations": evidence_fields.get("limitations", []),
        "verification": {
            "status": "identity_verified",
            "checked_at": evidence_fields.get("recorded_at"),
            "method": "Exact input, output, recipe, and Reporting Engine manifest hashes verified.",
            "notes": evidence_fields.get("verification_notes", []),
        },
        "rechecks_evidence_id": "",
        "supersedes_evidence_id": "",
        "calculation": {
            "method": evidence_fields.get("method"),
            "input_artifact_paths": [artifacts[0]["path"]],
            "output_artifact_paths": [
                _artifact_receipt(path, case_dir=case_dir)["path"]
                for path in output_paths
            ],
            "verification_artifact_paths": [
                _artifact_receipt(path, case_dir=case_dir)["path"]
                for path in verification_paths
            ],
        },
    }
    result = record_analysis_contribution(
        case_dir,
        evidence_receipts=[receipt],
        claims=[claim],
        judgement_entries=judgements,
    )
    return {
        **result,
        "calculation_evidence_id": receipt_id,
        "claim_id": claim.get("id"),
        "render_manifest": str(manifest_path),
    }


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--case-dir", type=Path, required=True)
    parser.add_argument("--render-manifest", type=Path, required=True)
    parser.add_argument("--contribution", type=Path, required=True)
    parser.add_argument(
        "--verification-artifact",
        type=Path,
        action="append",
        default=[],
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    result = record_reporting_contribution(
        args.case_dir,
        args.render_manifest,
        _load_object(args.contribution),
        additional_verification_artifacts=args.verification_artifact,
    )
    LOGGER.info(
        "Recorded reporting contribution: %s", json.dumps(result, sort_keys=True)
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
