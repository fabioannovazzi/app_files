"""Bind teaching progress to local execution evidence and generated files.

These are file-identity and routing checks, not an assessment of professional
meaning or authenticated host receipts. The working host attests execution;
the teacher must inspect the native run records and actual output before saving.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

__all__ = ["ExecutionError", "collect_execution", "verify_execution"]


class ExecutionError(ValueError):
    """The supplied local run does not support this teaching checkpoint."""


def _file(root: Path, value: Any) -> Path:
    if not isinstance(value, str) or not value.strip():
        raise ExecutionError("Execution evidence needs a real local file path")
    path = Path(value)
    if not path.is_absolute():
        path = root / path
    if any(part.is_symlink() for part in (path, *path.parents)):
        raise ExecutionError("Execution evidence must not use symlinks")
    path = path.resolve()
    if not path.is_relative_to(root) or not path.is_file():
        raise ExecutionError("Execution evidence must stay inside this lesson")
    return path


def _digest(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _json(path: Path) -> dict[str, Any]:
    if path.stat().st_size > 1_000_000:
        raise ExecutionError("Execution record is too large")
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (ValueError, UnicodeError) as exc:
        raise ExecutionError("Recover the invalid execution record") from exc
    if not isinstance(value, dict):
        raise ExecutionError("Execution record must be a JSON object")
    return value


def _records(root: Path, values: Any, field: str) -> list[dict[str, str]]:
    if not isinstance(values, list) or not 1 <= len(values) <= 30:
        raise ExecutionError(f"Execution requires 1 to 30 {field}")
    records = []
    for value in values:
        if not isinstance(value, dict) or set(value) != {"path", "sha256"}:
            raise ExecutionError(f"Each {field} entry needs its path and SHA-256")
        path = _file(root, value["path"])
        digest = _digest(path)
        if value["sha256"] != digest:
            raise ExecutionError("Execution artifacts changed; inspect the current run")
        records.append({"path": path.relative_to(root).as_posix(), "sha256": digest})
    if len({item["path"] for item in records}) != len(records):
        raise ExecutionError(f"Duplicate execution {field}")
    return records


def _prepared(root: Path) -> tuple[set[Path], set[str]]:
    directories: set[Path] = set()
    digests: set[str] = set()
    for path in root.rglob("course-provenance.json"):
        path = _file(root, str(path))
        record = _json(path)
        if record.get("prepared_material_only") is True:
            directories.add(path.parent)
            digests.add(_digest(path))
            for item in record.get("prepared_artifacts", []):
                if isinstance(item, dict) and isinstance(item.get("sha256"), str):
                    digests.add(item["sha256"])
    return directories, digests


def collect_execution(
    *,
    root: Path,
    plugin_root: Path,
    product: str,
    workflow: str,
    phase: str,
    worker_thread_id: str | None,
    record_path: Any,
    artifacts: list[dict[str, str]],
) -> dict[str, Any]:
    """Check exact scope, input/run/output hashes and prepared-file exclusion."""
    root = root.resolve()
    path = _file(root, record_path)
    receipt = _json(path)
    if (
        receipt.get("schema") != "mparanza.teaching_execution.v1"
        or receipt.get("evidence_kind") != "host_attested_local_execution"
        or receipt.get("product") != product
        or receipt.get("workflow_id") != workflow
        or receipt.get("phase") != phase
        or receipt.get("outcome") not in {"completed", "review_required"}
    ):
        raise ExecutionError("Record this phase's actual own-product execution")
    worker = receipt.get("worker_thread_id")
    if (
        not isinstance(worker, str)
        or not worker.strip()
        or (worker_thread_id is not None and worker != worker_thread_id)
    ):
        raise ExecutionError("Execution belongs to another working thread")
    skill = plugin_root / "skills" / workflow / "SKILL.md"
    if receipt.get("skill_sha256") != _digest(skill):
        raise ExecutionError(
            "The workflow changed; run and review its current procedure"
        )
    inputs = _records(root, receipt.get("inputs"), "inputs")
    native = _records(root, receipt.get("native_records"), "native run records")
    outputs = _records(root, receipt.get("outputs"), "outputs")
    if outputs != artifacts:
        raise ExecutionError(
            "Lesson artifacts must match the execution's exact outputs"
        )
    input_paths = {item["path"] for item in inputs}
    native_paths = {item["path"] for item in native}
    output_paths = {item["path"] for item in outputs}
    if (
        input_paths & native_paths
        or input_paths & output_paths
        or native_paths & output_paths
        or path.relative_to(root).as_posix()
        in input_paths | native_paths | output_paths
    ):
        raise ExecutionError(
            "Keep inputs, native run records and generated outputs distinct"
        )
    directories, prepared_hashes = _prepared(root)
    source_hashes = {item["sha256"] for item in inputs}
    for item in [*native, *outputs]:
        actual = root / item["path"]
        if any(actual.is_relative_to(folder) for folder in directories) or (
            item["sha256"] in prepared_hashes | source_hashes
        ):
            raise ExecutionError(
                "Prepared material or copied input is not execution evidence"
            )
    return {
        "path": path.relative_to(root).as_posix(),
        "sha256": _digest(path),
        "evidence_kind": "host_attested_local_execution",
    }


def verify_execution(*, recorded: dict[str, Any], **kwargs: Any) -> None:
    """Recheck the retained execution and all its files before completion."""
    if not isinstance(recorded, dict):
        raise ExecutionError("Record the actual working-thread execution first")
    current = collect_execution(
        **kwargs, worker_thread_id=None, record_path=recorded.get("path")
    )
    if current != recorded:
        raise ExecutionError(
            "Execution record changed; inspect and record the actual run"
        )
