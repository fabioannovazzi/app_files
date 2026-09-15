"""Copy exact reporting evidence into a relocatable, independently checked bundle.

Paths and byte identity are mechanically verifiable; this does not approve the
report's interpretation, chart design, or professional conclusions.
"""

from __future__ import annotations

import hashlib
import json
import shutil
import tempfile
from pathlib import Path, PurePosixPath, PureWindowsPath
from typing import Any

__all__ = ["delivery_context_paths", "export_reviewed_execution"]

DESCRIPTOR = "reporting_delivery.json"


def _member(root: Path, relative: str) -> Path:
    pure = PurePosixPath(relative)
    if (
        not relative
        or pure.is_absolute()
        or PureWindowsPath(relative).drive
        or ".." in pure.parts
        or "\\" in relative
    ):
        raise ValueError("Unsafe reporting delivery path")
    path = root.joinpath(*pure.parts)
    if path.is_symlink() or not path.resolve().is_relative_to(root.resolve()):
        raise ValueError("Reporting delivery path escapes its bundle")
    return path


def _sha(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def delivery_context_paths(root: Path, receipt: dict[str, Any]) -> dict[str, Any]:
    """Resolve copied inputs without rewriting the original execution receipt."""
    descriptor = root / DESCRIPTOR
    if not descriptor.exists():
        return receipt["context_inputs"]
    payload = json.loads(descriptor.read_text(encoding="utf-8"))
    if (
        payload.get("schema_version") != 1
        or payload.get("status") != "exported"
        or payload.get("execution_receipt_sha256")
        != _sha(root / "reviewed_execution.json")
    ):
        raise ValueError("Reporting delivery does not bind its execution receipt")
    paths = payload["context_inputs"]
    return {
        **{
            key: str(_member(root, paths[key]))
            for key in (
                "dataset_path",
                "layer_path",
                "profile_path",
                "acceptance_path",
            )
        },
        "source_paths": [str(_member(root, path)) for path in paths["source_paths"]],
    }


def export_reviewed_execution(output_dir: Path, destination: Path) -> dict[str, Any]:
    """Export verified inputs, outputs and the current generation without renaming."""
    from render_capability import output_lock, write_json_receipt
    from run_capability import verify_reviewed_execution

    output_dir = output_dir.resolve()
    destination = destination.absolute()
    if destination.resolve().is_relative_to(output_dir) or output_dir.is_relative_to(
        destination.resolve()
    ):
        raise ValueError("Delivery directory must be separate from execution")
    destination.parent.mkdir(parents=True, exist_ok=True)
    with (
        output_lock(destination.parent, name=f".{destination.name}.delivery.lock"),
        output_lock(output_dir, name=".reviewed-execution.lock"),
        output_lock(output_dir),
    ):
        if destination.exists() or destination.is_symlink():
            raise ValueError("Delivery destination already exists")
        receipt = verify_reviewed_execution(output_dir)
        context = delivery_context_paths(output_dir, receipt)
        manifest = json.loads((output_dir / "render_manifest.json").read_text())
        pointer = json.loads((output_dir / "current_reporting.json").read_text())
        generation = PurePosixPath(pointer["manifest"]).parent
        members = {
            "reviewed_execution.json",
            "render_manifest.json",
            "current_reporting.json",
            pointer["manifest"],
            *(item["path"] for item in manifest["evidence"]["outputs"]),
            *(
                str(generation / item["path"])
                for item in manifest["evidence"]["snapshot_outputs"]
            ),
        }
        with tempfile.TemporaryDirectory(
            prefix=".reporting-delivery-", dir=destination.parent
        ) as temporary:
            stage = Path(temporary) / "bundle"
            stage.mkdir()
            for relative in sorted(members):
                source = _member(output_dir, relative)
                target = _member(stage, relative)
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(source, target)
            copied: dict[str, Any] = {}
            for key, value in context.items():
                paths = value if key == "source_paths" else [value]
                targets = []
                for index, value_path in enumerate(paths):
                    source = Path(value_path)
                    relative = f"inputs/{key}/{index}/{source.name}"
                    target = _member(stage, relative)
                    target.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copyfile(source, target)
                    targets.append(relative)
                copied[key] = targets if key == "source_paths" else targets[0]
            descriptor = {
                "schema_version": 1,
                "status": "exported",
                "execution_receipt_sha256": _sha(stage / "reviewed_execution.json"),
                "context_inputs": copied,
                "boundary": "Portable exact-byte evidence; professional and visual review remain separate.",
            }
            write_json_receipt(stage / DESCRIPTOR, descriptor)
            verify_reviewed_execution(stage)
            if verify_reviewed_execution(output_dir) != receipt:
                raise ValueError("Reviewed execution changed during delivery export")
            stage.rename(destination)
    return descriptor
