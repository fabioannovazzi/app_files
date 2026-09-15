"""Execute a selected reporting analysis from exact reviewed semantic inputs."""

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
import sys
from pathlib import Path
from typing import Any

from compile_execution import compile_reviewed_execution
from render_capability import (
    RenderRequest,
    output_lock,
    render_capability,
    verify_render_generation,
    write_json_receipt,
)
from reporting_delivery import delivery_context_paths, export_reviewed_execution
from semantic_execution import verify_execution_context

__all__ = ["run_reviewed_capability", "verify_reviewed_execution", "main"]


def _sha(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for block in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def run_reviewed_capability(
    dataset_path: Path, *, output_dir: Path, **arguments: Any
) -> dict[str, Any]:
    """Serialize reviewed execution and its receipt independently of diagnostic runs."""
    sources = [dataset_path, *arguments.get("source_paths", [])]
    sources.extend(
        arguments[key]
        for key in ("layer_path", "profile_path", "acceptance_path")
        if key in arguments
    )
    if any(
        Path(source).resolve().is_relative_to(output_dir.resolve())
        for source in sources
    ):
        raise ValueError(
            "Reviewed output directory must be separate from input evidence"
        )
    with output_lock(output_dir, name=".reviewed-execution.lock"):
        return _run_reviewed_capability(
            dataset_path, output_dir=output_dir, **arguments
        )


def verify_reviewed_execution(output_dir: Path) -> dict[str, Any]:
    """Reject stale or changed rendered artifacts before an evidence handoff."""
    receipt = json.loads(
        (output_dir / "reviewed_execution.json").read_text(encoding="utf-8")
    )
    if receipt.get("status") != "reviewed_execution_completed":
        raise ValueError("Reviewed execution did not complete")
    paths = delivery_context_paths(output_dir, receipt)
    current = verify_execution_context(
        Path(paths["dataset_path"]),
        layer_path=Path(paths["layer_path"]),
        profile_path=Path(paths["profile_path"]),
        acceptance_path=Path(paths["acceptance_path"]),
        source_paths=[Path(path) for path in paths["source_paths"]],
        analysis_id=receipt["analysis_id"],
        capability_id=receipt["capability_id"],
    )
    if (
        current["input_sha256"] != receipt["input_sha256"]
        or current["acceptance_sha256"] != receipt["acceptance_sha256"]
        or current["profile_sha256"] != receipt["profile_sha256"]
    ):
        raise ValueError("Reviewed semantic inputs changed after execution")
    manifest_path = output_dir / "render_manifest.json"
    if _sha(manifest_path) != receipt["render_manifest_sha256"]:
        raise ValueError("Reviewed render manifest changed")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if manifest["evidence"]["output_set_sha256"] != receipt["output_set_sha256"]:
        raise ValueError("Reviewed render output set changed")
    for artifact in manifest["evidence"]["outputs"]:
        path = output_dir / artifact["path"]
        if (
            not path.resolve().is_relative_to(output_dir.resolve())
            or _sha(path) != artifact["sha256"]
        ):
            raise ValueError(
                "Reviewed render artifact changed or escaped its directory"
            )
    publication = verify_render_generation(output_dir)
    if publication["manifest_sha256"] != receipt["render_manifest_sha256"]:
        raise ValueError("Published reporting generation differs from reviewed output")
    return {**receipt, "publication": publication}


def _run_reviewed_capability(
    dataset_path: Path,
    *,
    output_dir: Path,
    layer_path: Path,
    profile_path: Path,
    acceptance_path: Path,
    source_paths: list[Path],
    analysis_id: str,
    capability_id: str,
    language: str = "en",
    artifact_mode: str = "data_and_render",
) -> dict[str, Any]:
    """Derive executable bindings; never accept caller overrides of reviewed semantics."""
    receipt_path = output_dir / "reviewed_execution.json"
    state: dict[str, Any] = {
        "schema_version": 1,
        "status": "running",
        "analysis_id": analysis_id,
        "capability_id": capability_id,
        "boundary": "Execution of declared reviewed semantics; business conclusions still require professional review.",
    }
    write_json_receipt(receipt_path, state)
    identity = dict(
        layer_path=layer_path,
        profile_path=profile_path,
        acceptance_path=acceptance_path,
        source_paths=source_paths,
        analysis_id=analysis_id,
        capability_id=capability_id,
    )
    completed = False
    try:
        compiled = compile_reviewed_execution(dataset_path, **identity)
        context = compiled["context"]
        result = render_capability(
            RenderRequest(
                capability_id=capability_id,
                input_file=dataset_path,
                output_dir=output_dir,
                parser_settings=context["parser_settings"],
                role_bindings=compiled["role_bindings"],
                options=compiled["options"],
                currency=compiled["currency"],
                language=language,
                artifact_mode=artifact_mode,
            )
        )
        current = verify_execution_context(dataset_path, **identity)
        if current != context:
            raise ValueError("Reviewed semantics changed during execution")
        render_path = output_dir / "render_manifest.json"
        if json.loads(render_path.read_text(encoding="utf-8")) != result:
            raise ValueError("Render manifest changed before semantic handoff")
        for artifact in result["evidence"]["outputs"]:
            if _sha(output_dir / artifact["path"]) != artifact["sha256"]:
                raise ValueError("Render output changed before semantic handoff")
        state.update(
            status="reviewed_execution_completed",
            context_inputs={
                "dataset_path": str(dataset_path.resolve()),
                "layer_path": str(layer_path.resolve()),
                "profile_path": str(profile_path.resolve()),
                "acceptance_path": str(acceptance_path.resolve()),
                "source_paths": [str(path.resolve()) for path in source_paths],
            },
            semantic_layer_id=context["semantic_layer_id"],
            semantic_version=context["semantic_version"],
            acceptance_sha256=context["acceptance_sha256"],
            profile_sha256=context["profile_sha256"],
            input_sha256=context["input_sha256"],
            semantic_source_sha256=context["semantic_source_sha256"],
            snapshot_fingerprint=context["snapshot_fingerprint"],
            role_bindings=compiled["role_bindings"],
            metric_contracts=compiled["metric_contracts"],
            resolved_scope=compiled["resolved_scope"],
            render_manifest_sha256=_sha(render_path),
            output_set_sha256=result["evidence"]["output_set_sha256"],
        )
        write_json_receipt(receipt_path, state)
        completed = True
        return state
    finally:
        if not completed:
            state["status"] = "failed_or_interrupted"
            write_json_receipt(receipt_path, state)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("dataset", type=Path, nargs="?")
    parser.add_argument("--verify-output", type=Path)
    parser.add_argument("--export-output", type=Path)
    parser.add_argument("--delivery-dir", type=Path)
    parser.add_argument("--output-dir", type=Path)
    parser.add_argument("--layer", type=Path)
    parser.add_argument("--profile", type=Path)
    parser.add_argument("--acceptance", type=Path)
    parser.add_argument("--source", type=Path, action="append")
    parser.add_argument("--analysis-id")
    parser.add_argument("--capability-id")
    parser.add_argument("--language", default="en")
    parser.add_argument(
        "--artifact-mode",
        choices=["data_only", "data_and_render"],
        default="data_and_render",
    )
    args = parser.parse_args()
    if args.export_output is not None:
        if args.delivery_dir is None or args.verify_output is not None:
            parser.error(
                "Export requires --delivery-dir and cannot use --verify-output"
            )
        result = export_reviewed_execution(args.export_output, args.delivery_dir)
        sys.stdout.write(json.dumps(result, indent=2) + "\n")
        return 0
    if args.verify_output is not None:
        if args.delivery_dir is not None:
            parser.error("--delivery-dir requires execution or --export-output")
        result = verify_reviewed_execution(args.verify_output)
        sys.stdout.write(
            json.dumps(
                {
                    "status": "verified",
                    "analysis_id": result["analysis_id"],
                    "capability_id": result["capability_id"],
                    "boundary": result["boundary"],
                },
                indent=2,
            )
            + "\n"
        )
        return 0
    required = (
        "dataset",
        "output_dir",
        "layer",
        "profile",
        "acceptance",
        "source",
        "analysis_id",
        "capability_id",
    )
    missing = [name for name in required if getattr(args, name) is None]
    if missing:
        parser.error("Required for execution: " + ", ".join(missing))
    result = run_reviewed_capability(
        args.dataset,
        output_dir=args.output_dir,
        layer_path=args.layer,
        profile_path=args.profile,
        acceptance_path=args.acceptance,
        source_paths=args.source,
        analysis_id=args.analysis_id,
        capability_id=args.capability_id,
        language=args.language,
        artifact_mode=args.artifact_mode,
    )
    delivery = None
    if args.delivery_dir is not None:
        export_reviewed_execution(args.output_dir, args.delivery_dir)
        verify_reviewed_execution(args.delivery_dir)
        delivery = str(args.delivery_dir.resolve())
    sys.stdout.write(
        json.dumps(
            {
                "status": result["status"],
                "analysis_id": result["analysis_id"],
                "capability_id": result["capability_id"],
                "delivery_required": delivery is None,
                "verified_delivery_dir": delivery,
                "handoff": (
                    "Keep the entire delivery directory, including hidden files. "
                    "Verify again at the recipient location."
                    if delivery is not None
                    else "Before transferring this run, invoke this script with "
                    "--export-output <output-dir> --delivery-dir <new-delivery-dir>, "
                    "then --verify-output <new-delivery-dir>. "
                    "Do not manually select or rename evidence files."
                ),
                "boundary": result["boundary"],
            },
            indent=2,
        )
        + "\n"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
