"""Owner-private checkpoints of one admitted run, independent of its destination.

Exact byte hashes and portable run identities justify these mechanical checks.
Recovery preserves prior bytes; it does not approve changed professional inputs.
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import shutil
import sqlite3
import stat
import tempfile
from contextlib import closing
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath
from typing import Any
from uuid import uuid4

from .serialization import canonical_json_sha256, exclusive_file_lock

__all__ = ["checkpoint_run", "restore_run", "repair_run_inputs"]
_REFERENCE = "work-recovery.json"


def _ordinary(path: Path, *, directory: bool = False) -> None:
    if any(item.is_symlink() for item in (path, *path.parents)):
        raise ValueError("Recovery paths cannot contain symbolic links")
    observed = path.stat()
    if not (
        stat.S_ISDIR(observed.st_mode) if directory else stat.S_ISREG(observed.st_mode)
    ):
        raise ValueError("Recovery needs an ordinary file or directory")


def _private_directory(path: Path) -> None:
    if any(item.is_symlink() for item in (path, *path.parents)):
        raise ValueError("Recovery storage cannot contain symbolic links")
    missing = []
    candidate = path
    while not candidate.exists():
        missing.append(candidate)
        candidate = candidate.parent
    for directory in reversed(missing):
        directory.mkdir(exist_ok=True, mode=0o700)
    _ordinary(path, directory=True)
    if os.name == "posix" and stat.S_IMODE(path.stat().st_mode) & 0o077:
        raise ValueError("Recovery storage must be owner-private")


def _json(path: Path) -> dict[str, Any]:
    _ordinary(path)
    if path.stat().st_size > 16 * 1024 * 1024:
        raise ValueError("Recovery manifest is too large")
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError("Recovery manifest must be an object")
    return value


def _write(path: Path, value: dict[str, Any]) -> None:
    _private_directory(path.parent)
    if path.exists() or path.is_symlink():
        _ordinary(path)
    descriptor, name = tempfile.mkstemp(prefix=".recovery-", dir=path.parent)
    temporary = Path(name)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            json.dump(
                value, handle, sort_keys=True, ensure_ascii=False, allow_nan=False
            )
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        temporary.replace(path)
    finally:
        temporary.unlink(missing_ok=True)


def _identity(path: Path) -> tuple[int, str]:
    _ordinary(path)
    before = path.stat()
    digest = hashlib.sha256()
    count = 0
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
            count += len(block)
    after = path.stat()
    if (before.st_ino, before.st_size, before.st_mtime_ns) != (
        after.st_ino,
        after.st_size,
        after.st_mtime_ns,
    ) or count != after.st_size:
        raise ValueError("Recovery source changed while being read")
    return count, digest.hexdigest()


def _relative(value: str) -> Path:
    path = PurePosixPath(value)
    if (
        path.is_absolute()
        or not path.parts
        or any(part in {"..", "."} for part in path.parts)
        or "\\" in value
        or ":" in value
    ):
        raise ValueError("Recovery manifest has an unsafe relative path")
    return Path(*path.parts)


def _run_identity(run: dict[str, Any]) -> tuple[str, str, str, str]:
    return run["client_id"], run["engagement_id"], run["run_id"], run["static_sha256"]


def _object(store: Path, record: dict[str, Any]) -> Path:
    digest = record["sha256"]
    if (
        not isinstance(digest, str)
        or len(digest) != 64
        or any(c not in "0123456789abcdef" for c in digest)
    ):
        raise ValueError("Recovery object digest is invalid")
    if type(record["byte_count"]) is not int or record["byte_count"] < 0:
        raise ValueError("Recovery byte count is invalid")
    return store / "objects" / digest


def _snapshot(store: Path, digest: str | None = None) -> dict[str, Any]:
    _ordinary(store, directory=True)
    if digest is None:
        digest = _json(store / "latest.json")["snapshot_sha256"]
    if (
        not isinstance(digest, str)
        or len(digest) != 64
        or any(c not in "0123456789abcdef" for c in digest)
    ):
        raise ValueError("Recovery snapshot digest is invalid")
    snapshot = _json(store / "snapshots" / (digest + ".json"))
    if (
        snapshot.get("schema_version") != "vera.work_checkpoint.v1"
        or canonical_json_sha256(snapshot) != digest
    ):
        raise ValueError("Recovery snapshot no longer matches its receipt")
    return snapshot


def _retain(source: Path, store: Path) -> dict[str, Any]:
    """Publish verified immutable bytes, using SQLite backup for the collector."""
    _private_directory(store / "objects")
    descriptor, name = tempfile.mkstemp(prefix=".copy-", dir=store)
    os.close(descriptor)
    temporary = Path(name)
    try:
        _ordinary(source)
        if source.name == "events.sqlite3" and source.parent.name == "reporting":
            with closing(
                sqlite3.connect(source.as_uri() + "?mode=ro", uri=True)
            ) as original:
                with closing(sqlite3.connect(temporary)) as copied:
                    original.backup(copied)
        else:
            before = _identity(source)
            shutil.copyfile(source, temporary)
            if _identity(temporary) != before or _identity(source) != before:
                raise ValueError("Recovery source changed during copying")
        count, digest = _identity(temporary)
        with temporary.open("rb") as handle:
            os.fsync(handle.fileno())
        target = store / "objects" / digest
        if target.exists():
            if _identity(target) != (count, digest):
                raise ValueError("Retained recovery object is damaged")
        else:
            temporary.replace(target)
        return {"byte_count": count, "sha256": digest}
    finally:
        temporary.unlink(missing_ok=True)


def checkpoint_run(context_path: Path, store: Path | None = None) -> dict[str, Any]:
    """Retain only this run and its portable owner headers, preserving all stages."""
    from .contracts import load_client_engagement_context_file

    context_path = Path(context_path).absolute()
    reference = context_path.parent / _REFERENCE
    retained_reference = store is None
    if store is None:
        if not reference.is_file():
            return {"status": "not_configured"}
        pointer = _json(reference)
        if pointer.get("schema_version") != "vera.work_recovery.v1":
            raise ValueError("Recovery reference schema is invalid")
        store = Path(pointer["store"])
    store = Path(store).absolute()
    portable = _json(context_path)
    context = load_client_engagement_context_file(
        context_path,
        expected_workflow_id=portable["workflow_id"],
        allowed_statuses=(
            "prepared",
            "running",
            "ready_for_review",
            "completed",
            "failed",
            "cancelled",
        ),
    )
    root = Path(context["studio_client_folder"]["client_root"])
    run_root = context_path.parent
    if store.is_relative_to(root):
        raise ValueError(
            "Recovery storage must be independent of the archive destination"
        )
    _private_directory(store)
    with exclusive_file_lock(store / "checkpoint.lock"):
        run = _json(run_root / "run.json")
        if retained_reference and tuple(
            _snapshot(store)["run_identity"]
        ) != _run_identity(run):
            raise ValueError("Recovery reference belongs to another run")
        headers = [root / "Vera/client.json", run_root.parents[1] / "engagement.json"]

        def files() -> list[Path]:
            paths = list(run_root.rglob("*"))
            if any(path.is_symlink() for path in paths):
                raise ValueError("A run checkpoint cannot follow symbolic links")
            excluded = {
                run_root / _REFERENCE,
                run_root / "recovery.lock",
                *(
                    run_root / "reporting" / name
                    for name in (
                        "collection.lock",
                        "events.sqlite3-wal",
                        "events.sqlite3-shm",
                    )
                ),
            }
            return sorted(
                [
                    *headers,
                    *(
                        path
                        for path in paths
                        if path.is_file() and path not in excluded
                    ),
                ]
            )

        selected = files()
        records = {
            str(path.relative_to(root).as_posix()): _retain(path, store)
            for path in selected
        }
        if files() != selected or _json(run_root / "run.json") != run:
            raise ValueError(
                "Run changed during checkpoint; retain the previous checkpoint"
            )
        for source in selected:
            if source == run_root / "reporting/events.sqlite3":
                continue  # Its SQLite backup already represents a committed transaction.
            record = records[source.relative_to(root).as_posix()]
            if _identity(source) != (record["byte_count"], record["sha256"]):
                raise ValueError(
                    "Run changed during checkpoint; retain the previous checkpoint"
                )
        snapshot = {
            "schema_version": "vera.work_checkpoint.v1",
            "client_root": str(root),
            "context_relative_path": context_path.relative_to(root).as_posix(),
            "run_identity": list(_run_identity(run)),
            "recorded_at": datetime.now(timezone.utc).isoformat(),
            "files": records,
            "directories": sorted(
                path.relative_to(root).as_posix()
                for path in run_root.rglob("*")
                if path.is_dir()
            ),
        }
        digest = canonical_json_sha256(snapshot)
        _write(store / "snapshots" / (digest + ".json"), snapshot)
        _write(store / "latest.json", {"snapshot_sha256": digest})
        _write(
            reference, {"schema_version": "vera.work_recovery.v1", "store": str(store)}
        )
        return {
            "status": "retained",
            "snapshot_sha256": digest,
            "store": str(store),
            "file_count": len(records),
        }


def restore_run(
    store: Path, destination: Path, identities: tuple[str, str, str]
) -> Path:
    """Restore one exact snapshot into a new explicitly selected destination."""
    store, destination = Path(store).absolute(), Path(destination).absolute()
    _ordinary(store, directory=True)
    lock = "restore-" + hashlib.sha256(str(destination).encode()).hexdigest() + ".lock"
    with exclusive_file_lock(store / lock):
        return _restore_run(store, destination, identities)


def _restore_run(
    store: Path, destination: Path, identities: tuple[str, str, str]
) -> Path:
    store, destination = Path(store).absolute(), Path(destination).absolute()
    marker = destination / "work-restore.json"
    prior = _json(marker) if marker.is_file() else None
    if prior is not None and prior.get("store") != str(store):
        raise ValueError("Recovery destination belongs to another restore request")
    snapshot = _snapshot(store, prior["snapshot_sha256"] if prior is not None else None)
    if tuple(snapshot["run_identity"][:3]) != identities:
        raise ValueError("Recovery snapshot belongs to another run")
    restore_record = {
        "schema_version": "vera.work_restore.v1",
        "store": str(store),
        "snapshot_sha256": canonical_json_sha256(snapshot),
    }
    progress: dict[str, Any] = {**restore_record, "status": "copying", "written": []}
    if destination.exists() or destination.is_symlink():
        _ordinary(destination, directory=True)
        if not marker.is_file():
            raise ValueError(
                "Recovery destination already exists; preserve its contents"
            )
        progress = _json(marker)
        if any(progress.get(key) != value for key, value in restore_record.items()):
            raise ValueError("Recovery destination belongs to another restore request")
        if progress["status"] == "restored":
            context = destination / _relative(snapshot["context_relative_path"])
            if _run_identity(_json(context.parent / "run.json")) != tuple(
                snapshot["run_identity"]
            ):
                raise ValueError("Recovery destination now belongs to another run")
            return context  # Replaying a restore must not roll back subsequent work.
    _ordinary(destination.parent, directory=True)
    # Verify every retained byte before creating any destination files.
    for relative, record in snapshot["files"].items():
        _relative(relative)
        if _identity(_object(store, record)) != (
            record["byte_count"],
            record["sha256"],
        ):
            raise ValueError("Retained recovery bytes no longer match the checkpoint")
    directories = [_relative(relative) for relative in snapshot["directories"]]
    destination.mkdir(mode=0o700, exist_ok=True)
    _write(marker, progress)
    for directory in directories:
        _private_directory(destination / directory)
    expected_paths = {_relative(relative) for relative in snapshot["files"]}
    context_relative = _relative(snapshot["context_relative_path"])
    for existing in destination.rglob("*"):
        if existing.is_symlink():
            raise ValueError("Recovery destination contains a symbolic link")
        if (
            existing.is_file()
            and not existing.is_relative_to(destination / "work-restore-evidence")
            and existing.relative_to(destination)
            not in {
                *expected_paths,
                Path("work-restore.json"),
                context_relative.parent / _REFERENCE,
            }
        ):
            raise ValueError("Recovery destination contains unrelated work")
    for relative, record in snapshot["files"].items():
        target = destination / _relative(relative)
        _private_directory(target.parent)
        if target.exists():
            if _identity(target) == (record["byte_count"], record["sha256"]):
                continue
            if relative in progress["written"] or progress["status"] == "restored":
                raise ValueError(
                    "Recovery destination changed after verification; preserve its current work"
                )
            evidence = destination / "work-restore-evidence" / uuid4().hex
            _private_directory(evidence)
            target.rename(evidence / "partial-copy")
        descriptor, name = tempfile.mkstemp(prefix=".recovery-", dir=target.parent)
        temporary = Path(name)
        try:
            with (
                os.fdopen(descriptor, "wb") as handle,
                _object(store, record).open("rb") as source,
            ):
                shutil.copyfileobj(source, handle)
                handle.flush()
                os.fsync(handle.fileno())
            if _identity(temporary) != (record["byte_count"], record["sha256"]):
                raise ValueError(
                    "Recovery copy verification failed; retained checkpoint is intact"
                )
            # Ordinary exclusive writes also work on destinations without hardlinks.
            # If interrupted, the partial copy remains available as recovery evidence.
            with target.open("xb") as handle, temporary.open("rb") as source:
                shutil.copyfileobj(source, handle)
                handle.flush()
                os.fsync(handle.fileno())
        finally:
            temporary.unlink(missing_ok=True)
        if _identity(target) != (record["byte_count"], record["sha256"]):
            raise ValueError(
                "Recovery copy verification failed; retained checkpoint is intact"
            )
        progress["written"].append(relative)
        _write(marker, progress)
    context = destination / context_relative
    if _run_identity(_json(context.parent / "run.json")) != tuple(
        snapshot["run_identity"]
    ):
        raise ValueError("Restored run identity does not match the selected checkpoint")
    _write(
        context.parent / _REFERENCE,
        {"schema_version": "vera.work_recovery.v1", "store": str(store)},
    )
    _write(marker, {**progress, "status": "restored"})
    return context


def repair_run_inputs(context_path: Path) -> None:
    """Restore exact admitted inputs and retain changed bytes as separate evidence."""
    run_root = Path(context_path).parent
    inputs = _json(run_root / "input_manifest.json")["inputs"]
    damaged = []
    for binding in inputs:
        target = run_root / _relative(binding["execution_relative_path"])
        if target.is_symlink():
            raise ValueError("Recovery does not replace symbolic links")
        if not target.exists() or _identity(target) != (
            binding["byte_count"],
            binding["sha256"],
        ):
            damaged.append(binding)
    if not damaged:
        return  # An unavailable optional checkpoint cannot reopen a passed input gate.
    reference = run_root / _REFERENCE
    if not reference.is_file():
        return
    store = Path(_json(reference)["store"])
    snapshot = _snapshot(store)
    run = _json(run_root / "run.json")
    if tuple(snapshot["run_identity"]) != _run_identity(run):
        raise ValueError("Recovery snapshot belongs to another admitted run")
    client_root = Path(context_path).parents[5]
    with exclusive_file_lock(run_root / "recovery.lock"):
        for binding in damaged:
            target = run_root / _relative(binding["execution_relative_path"])
            expected = (binding["byte_count"], binding["sha256"])
            if target.is_symlink():
                raise ValueError("Recovery does not replace symbolic links")
            if target.exists() and _identity(target) == expected:
                continue
            record = snapshot["files"].get(target.relative_to(client_root).as_posix())
            if record is None or (record["byte_count"], record["sha256"]) != expected:
                raise ValueError("Checkpoint has no exact copy of this admitted input")
            retained = _object(store, record)
            if _identity(retained) != expected:
                raise ValueError("Retained input is damaged; preserve current work")
            evidence = run_root / "recovery-evidence" / uuid4().hex
            _private_directory(evidence)
            if target.exists():
                prior = _identity(target)
                shutil.copyfile(target, evidence / "changed-input")
                if (
                    _identity(evidence / "changed-input") != prior
                    or _identity(target) != prior
                ):
                    raise ValueError("Changed input could not be preserved exactly")
            _private_directory(target.parent)
            descriptor, name = tempfile.mkstemp(prefix=".recovery-", dir=target.parent)
            os.close(descriptor)
            temporary = Path(name)
            try:
                shutil.copyfile(retained, temporary)
                if _identity(temporary) != expected:
                    raise ValueError("Restored input does not match its admitted bytes")
                temporary.replace(target)
            finally:
                temporary.unlink(missing_ok=True)
            _write(
                evidence / "repair.json",
                {
                    "execution_relative_path": binding["execution_relative_path"],
                    "restored_sha256": binding["sha256"],
                },
            )
            logging.getLogger(__name__).warning(
                "Restored an admitted input from its checkpoint; prior evidence is retained at %s",
                evidence,
            )
