"""Portable customer-folder ledger for Vera client work.

The ledger deliberately uses deterministic rules for IDs, paths, hashes,
manifest closure, and lifecycle transitions because those properties are
mechanically verifiable and form the audit boundary.  It does not choose a
client, engagement, workflow, or semantically relevant source.
"""

from __future__ import annotations

import errno
import hashlib
import json
import os
import re
import secrets
import shutil
import stat
import tempfile
import threading
import time
from collections.abc import Iterator, Mapping, Sequence
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

if os.name == "nt":
    import msvcrt as _PROCESS_LOCK_MODULE
else:
    import fcntl as _PROCESS_LOCK_MODULE

__all__ = [
    "ARTIFACT_AUDIENCES",
    "CLIENT_MANIFEST_SCHEMA",
    "ENGAGEMENT_MANIFEST_SCHEMA",
    "INPUT_RECEIPT_SCHEMA",
    "LEDGER_DIRECTORY",
    "LedgerError",
    "RUN_LIFECYCLE_STATES",
    "RUN_MANIFEST_SCHEMA",
    "cancel_run",
    "close_engagement",
    "complete_run",
    "create_client_manifest",
    "create_engagement",
    "fail_run",
    "finalize_run",
    "find_client_manifests",
    "import_document",
    "list_engagements",
    "list_inputs",
    "list_runs",
    "load_client_manifest",
    "load_engagement_manifest",
    "load_input_receipt",
    "load_run",
    "prepare_run",
    "retention_report",
    "start_run",
    "validate_run_artifacts",
]


LEDGER_DIRECTORY = "Vera"
CLIENT_MANIFEST_SCHEMA = "vera.customer_folder.v1"
ENGAGEMENT_MANIFEST_SCHEMA = "vera.engagement.v1"
INPUT_RECEIPT_SCHEMA = "vera.input_receipt.v1"
INPUT_MANIFEST_SCHEMA = "vera.run_inputs.v1"
RUN_CONTEXT_SCHEMA = "vera.client_workflow_context.v2"
RUN_MANIFEST_SCHEMA = "vera.workflow_run.v1"
ARTIFACT_MANIFEST_SCHEMA = "vera.artifact_manifest.v1"

RUN_LIFECYCLE_STATES = frozenset(
    {
        "prepared",
        "running",
        "ready_for_review",
        "completed",
        "failed",
        "cancelled",
    }
)
_RUN_TRANSITIONS = {
    "prepared": {"running", "failed", "cancelled"},
    "running": {"ready_for_review", "failed", "cancelled"},
    "ready_for_review": {"running", "completed", "failed", "cancelled"},
    "failed": {"running", "cancelled"},
    "completed": set(),
    "cancelled": set(),
}
ARTIFACT_AUDIENCES = frozenset({"internal", "review", "deliverable"})
IMPORT_ROLES = frozenset({"journal", "source", "support"})
_CLIENT_ID_RE = re.compile(r"^client_[0-9a-f]{24}$")
_ENGAGEMENT_ID_RE = re.compile(r"^eng_[0-9a-f]{24}$")
_INPUT_ID_RE = re.compile(r"^input_[0-9a-f]{24}$")
_RUN_ID_RE = re.compile(r"^run_[0-9a-f]{24}$")
_ARTIFACT_ID_RE = re.compile(r"^[a-z0-9][a-z0-9._-]{0,119}$")
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_CONTROL_NAMES = {"receipt.json", ".DS_Store"}
_MAX_JSON_BYTES = 16 * 1024 * 1024
_MAX_INPUTS = 10_000
_MAX_RUNS = 50_000
_MAX_ARTIFACTS = 20_000
_ENGAGEMENT_LOCK_NAME = ".vera-engagement.lock"
_ENGAGEMENT_LOCK_CONTENT = b"Vera engagement mutation lock\n"
_ENGAGEMENT_THREAD_LOCKS_GUARD = threading.Lock()
_ENGAGEMENT_THREAD_LOCKS: dict[str, Any] = {}


class LedgerError(RuntimeError):
    """Raised when a customer-folder ledger invariant is violated."""


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _canonical_json_sha256(value: Mapping[str, Any]) -> str:
    payload = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _stable_file_identity(path: Path, *, label: str) -> tuple[int, str]:
    """Hash one regular file while proving its path and bytes stayed stable."""

    before_path = _ordinary_file(path, label=label)
    descriptor = -1
    try:
        descriptor = os.open(path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
        before = os.fstat(descriptor)
        identity = (
            before.st_dev,
            before.st_ino,
            before.st_size,
            before.st_mtime_ns,
            before.st_ctime_ns,
            before.st_nlink,
        )
        if identity != (
            before_path.st_dev,
            before_path.st_ino,
            before_path.st_size,
            before_path.st_mtime_ns,
            before_path.st_ctime_ns,
            before_path.st_nlink,
        ):
            raise LedgerError(f"{label} changed before it was opened.")
        digest = hashlib.sha256()
        while True:
            chunk = os.read(descriptor, 1024 * 1024)
            if not chunk:
                break
            digest.update(chunk)
        after = os.fstat(descriptor)
        final_path = _ordinary_file(path, label=label)
        final_identity = (
            after.st_dev,
            after.st_ino,
            after.st_size,
            after.st_mtime_ns,
            after.st_ctime_ns,
            after.st_nlink,
        )
        if final_identity != identity or final_identity != (
            final_path.st_dev,
            final_path.st_ino,
            final_path.st_size,
            final_path.st_mtime_ns,
            final_path.st_ctime_ns,
            final_path.st_nlink,
        ):
            raise LedgerError(f"{label} changed while it was read.")
        return after.st_size, digest.hexdigest()
    except OSError as exc:
        raise LedgerError(f"{label} could not be read safely: {exc}") from exc
    finally:
        if descriptor >= 0:
            os.close(descriptor)


def _new_id(prefix: str) -> str:
    return f"{prefix}_{secrets.token_hex(12)}"


def _text(value: object, *, label: str, maximum: int = 240) -> str:
    if not isinstance(value, str):
        raise LedgerError(f"{label} must be text.")
    normalized = re.sub(r"\s+", " ", value).strip()
    if (
        not normalized
        or len(normalized) > maximum
        or re.search(r"[\x00-\x1f\x7f]", normalized)
    ):
        raise LedgerError(f"{label} must contain 1 to {maximum} safe characters.")
    return normalized


def _identifier(value: object, *, label: str, pattern: re.Pattern[str]) -> str:
    if not isinstance(value, str) or pattern.fullmatch(value) is None:
        raise LedgerError(f"{label} is invalid.")
    return value


def _relative_path(value: object, *, label: str) -> str:
    if not isinstance(value, str) or not value:
        raise LedgerError(f"{label} is invalid.")
    path = Path(value)
    if (
        path.is_absolute()
        or path.as_posix() != value
        or any(part in {"", ".", ".."} for part in path.parts)
    ):
        raise LedgerError(f"{label} must be a normalized relative path.")
    return value


def _ordinary_directory(path: Path, *, label: str, create: bool = False) -> Path:
    if create and not path.exists() and not path.is_symlink():
        path.mkdir(mode=0o700, parents=True)
    try:
        observed = path.lstat()
    except OSError as exc:
        raise LedgerError(f"{label} is unavailable: {exc}") from exc
    if path.is_symlink() or not stat.S_ISDIR(observed.st_mode):
        raise LedgerError(f"{label} must be a real directory.")
    return path.resolve(strict=True)


def _ordinary_file(path: Path, *, label: str) -> os.stat_result:
    try:
        observed = path.lstat()
    except OSError as exc:
        raise LedgerError(f"{label} is unavailable: {exc}") from exc
    if path.is_symlink() or not stat.S_ISREG(observed.st_mode) or observed.st_nlink < 1:
        raise LedgerError(f"{label} must be a regular non-symlink file.")
    return observed


def _engagement_thread_lock(path: Path) -> Any:
    """Return one process-local lock for an engagement mutation boundary."""

    key = str(path)
    with _ENGAGEMENT_THREAD_LOCKS_GUARD:
        lock = _ENGAGEMENT_THREAD_LOCKS.get(key)
        if lock is None:
            lock = threading.RLock()
            _ENGAGEMENT_THREAD_LOCKS[key] = lock
        return lock


def _acquire_process_lock(descriptor: int) -> None:
    """Acquire the platform process lock for one stable engagement file."""

    if os.name != "nt":
        _PROCESS_LOCK_MODULE.flock(descriptor, _PROCESS_LOCK_MODULE.LOCK_EX)
        return
    os.lseek(descriptor, 0, os.SEEK_SET)
    while True:
        try:
            _PROCESS_LOCK_MODULE.locking(
                descriptor,
                _PROCESS_LOCK_MODULE.LK_NBLCK,
                1,
            )
            return
        except OSError as exc:
            if exc.errno not in {errno.EACCES, errno.EDEADLK}:
                raise
            time.sleep(0.05)


def _open_engagement_lock(path: Path) -> int:
    """Open or recover the stable, purpose-specific engagement lock file."""

    descriptor = -1
    try:
        descriptor = os.open(
            path,
            os.O_RDWR | os.O_CREAT | getattr(os, "O_NOFOLLOW", 0),
            0o600,
        )
        opened = os.fstat(descriptor)
        if not stat.S_ISREG(opened.st_mode) or opened.st_nlink != 1:
            raise LedgerError(
                "Engagement mutation lock must be a single-link regular file."
            )
        try:
            current = path.lstat()
        except OSError as exc:
            raise LedgerError(
                f"Engagement mutation lock is unavailable: {exc}"
            ) from exc
        if path.is_symlink() or (opened.st_dev, opened.st_ino) != (
            current.st_dev,
            current.st_ino,
        ):
            raise LedgerError("Engagement mutation lock path is unsafe.")
        if opened.st_size == 0:
            os.write(descriptor, _ENGAGEMENT_LOCK_CONTENT)
            os.fsync(descriptor)
        elif opened.st_size > 1024:
            raise LedgerError("Engagement mutation lock exceeds its size limit.")
        os.lseek(descriptor, 0, os.SEEK_SET)
        return descriptor
    except LedgerError:
        if descriptor >= 0:
            os.close(descriptor)
        raise
    except OSError as exc:
        if descriptor >= 0:
            os.close(descriptor)
        raise LedgerError(f"Engagement mutation lock is unavailable: {exc}") from exc


@contextmanager
def _engagement_lock(client_root: Path, engagement_id: str) -> Iterator[None]:
    """Serialize idempotent engagement writes across threads and processes.

    A fixed lock is justified because one imported content identity or run
    idempotency key must mechanically resolve to one ledger record even when
    separate local MCP processes retry together. The dedicated lock file has
    this single documented runtime purpose and stays stable when manifests are
    atomically replaced.
    """

    lock_path = (
        _engagement_root(client_root.resolve(), engagement_id) / _ENGAGEMENT_LOCK_NAME
    )
    thread_lock = _engagement_thread_lock(lock_path)
    with thread_lock:
        descriptor = -1
        for _attempt in range(8):
            try:
                descriptor = _open_engagement_lock(lock_path)
                opened = os.fstat(descriptor)
                _acquire_process_lock(descriptor)
                current = _ordinary_file(
                    lock_path,
                    label="engagement mutation lock",
                )
                if (opened.st_dev, opened.st_ino) != (
                    current.st_dev,
                    current.st_ino,
                ):
                    os.close(descriptor)
                    descriptor = -1
                    continue
                break
            except LedgerError:
                if descriptor >= 0:
                    os.close(descriptor)
                raise
            except OSError as exc:
                if descriptor >= 0:
                    os.close(descriptor)
                raise LedgerError(
                    f"Engagement mutation lock is unavailable: {exc}"
                ) from exc
        else:
            raise LedgerError("Engagement changed repeatedly while acquiring its lock.")
        try:
            yield
        finally:
            os.close(descriptor)


def _read_json(path: Path, *, label: str) -> dict[str, Any]:
    observed = _ordinary_file(path, label=label)
    if observed.st_size > _MAX_JSON_BYTES:
        raise LedgerError(f"{label} exceeds its size limit.")
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise LedgerError(f"{label} is unreadable: {exc}") from exc
    if not isinstance(payload, dict):
        raise LedgerError(f"{label} must contain a JSON object.")
    return payload


def _write_json(path: Path, payload: Mapping[str, Any]) -> None:
    parent = _ordinary_directory(path.parent, label="manifest directory")
    encoded = (
        json.dumps(
            payload, ensure_ascii=False, indent=2, sort_keys=True, allow_nan=False
        )
        + "\n"
    ).encode("utf-8")
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{path.name}.", suffix=".tmp", dir=parent
    )
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(encoded)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        if temporary.exists():
            temporary.unlink()


def _sealed(content: Mapping[str, Any]) -> dict[str, Any]:
    normalized = dict(content)
    return {**normalized, "content_sha256": _canonical_json_sha256(normalized)}


def _validate_seal(payload: Mapping[str, Any], *, label: str) -> dict[str, Any]:
    digest = payload.get("content_sha256")
    if not isinstance(digest, str) or _SHA256_RE.fullmatch(digest) is None:
        raise LedgerError(f"{label} has no valid content digest.")
    content = {key: value for key, value in payload.items() if key != "content_sha256"}
    if _canonical_json_sha256(content) != digest:
        raise LedgerError(f"{label} content digest is stale.")
    return dict(payload)


def _client_manifest_path(client_root: Path) -> Path:
    return client_root / LEDGER_DIRECTORY / "client.json"


def _engagements_root(client_root: Path) -> Path:
    return client_root / LEDGER_DIRECTORY / "engagements"


def _engagement_root(client_root: Path, engagement_id: str) -> Path:
    return _engagements_root(client_root) / engagement_id


def _run_root(client_root: Path, engagement_id: str, run_id: str) -> Path:
    return _engagement_root(client_root, engagement_id) / "runs" / run_id


def create_client_manifest(
    client_root: Path,
    client_id: str,
    *,
    created_at: str | None = None,
) -> dict[str, Any]:
    """Create or replay the stable opaque identity inside one customer folder."""

    client_id = _identifier(client_id, label="client_id", pattern=_CLIENT_ID_RE)
    root = _ordinary_directory(client_root, label="client folder")
    ledger_root = root / LEDGER_DIRECTORY
    _ordinary_directory(ledger_root, label="Vera ledger directory", create=True)
    path = _client_manifest_path(root)
    if path.exists() or path.is_symlink():
        existing = load_client_manifest(root)
        if existing["client_id"] != client_id:
            raise LedgerError("Customer folder already belongs to another client ID.")
        return existing
    content = {
        "schema_version": CLIENT_MANIFEST_SCHEMA,
        "client_id": client_id,
        "created_at": created_at or _now_iso(),
    }
    manifest = _sealed(content)
    _write_json(path, manifest)
    _ordinary_directory(
        _engagements_root(root), label="engagement ledger directory", create=True
    )
    return manifest


def load_client_manifest(client_root: Path) -> dict[str, Any]:
    """Load and validate one portable customer-folder identity."""

    root = _ordinary_directory(client_root, label="client folder")
    payload = _validate_seal(
        _read_json(_client_manifest_path(root), label="client manifest"),
        label="client manifest",
    )
    if (
        set(payload)
        != {
            "schema_version",
            "client_id",
            "created_at",
            "content_sha256",
        }
        or payload["schema_version"] != CLIENT_MANIFEST_SCHEMA
    ):
        raise LedgerError("Client manifest shape is invalid.")
    _identifier(payload["client_id"], label="client_id", pattern=_CLIENT_ID_RE)
    _text(payload["created_at"], label="created_at", maximum=80)
    return payload


def find_client_manifests(
    scoped_roots: Sequence[tuple[str, Path]],
) -> tuple[dict[str, Any], ...]:
    """Discover stable client IDs from exact configured top-level scopes."""

    found: list[dict[str, Any]] = []
    seen: dict[str, Path] = {}
    for scope_id, raw_root in scoped_roots:
        root = _ordinary_directory(raw_root, label="configured client scope")
        path = _client_manifest_path(root)
        if not path.exists() and not path.is_symlink():
            continue
        manifest = load_client_manifest(root)
        previous = seen.get(manifest["client_id"])
        if previous is not None and previous != root:
            raise LedgerError(
                "The same stable client ID appears in more than one customer folder."
            )
        seen[manifest["client_id"]] = root
        found.append(
            {
                "client_id": manifest["client_id"],
                "scope_id": scope_id,
                "client_root": str(root),
                "created_at": manifest["created_at"],
            }
        )
    return tuple(sorted(found, key=lambda item: item["client_id"]))


def _validate_engagement_manifest(
    payload: Mapping[str, Any], *, expected_client_id: str | None = None
) -> dict[str, Any]:
    normalized = _validate_seal(payload, label="engagement manifest")
    required = {
        "schema_version",
        "client_id",
        "engagement_id",
        "label",
        "status",
        "created_at",
        "closed_at",
        "content_sha256",
    }
    if (
        set(normalized) != required
        or normalized["schema_version"] != ENGAGEMENT_MANIFEST_SCHEMA
    ):
        raise LedgerError("Engagement manifest shape is invalid.")
    client_id = _identifier(
        normalized["client_id"], label="client_id", pattern=_CLIENT_ID_RE
    )
    _identifier(
        normalized["engagement_id"],
        label="engagement_id",
        pattern=_ENGAGEMENT_ID_RE,
    )
    _text(normalized["label"], label="engagement label", maximum=160)
    _text(normalized["created_at"], label="created_at", maximum=80)
    if normalized["status"] not in {"open", "closed"}:
        raise LedgerError("Engagement status is invalid.")
    closed_at = normalized["closed_at"]
    if normalized["status"] == "open" and closed_at is not None:
        raise LedgerError("An open engagement cannot have closed_at.")
    if normalized["status"] == "closed":
        _text(closed_at, label="closed_at", maximum=80)
    if expected_client_id is not None and client_id != expected_client_id:
        raise LedgerError("Engagement belongs to another client.")
    return normalized


def load_engagement_manifest(client_root: Path, engagement_id: str) -> dict[str, Any]:
    """Load one customer-folder engagement manifest."""

    client = load_client_manifest(client_root)
    engagement_id = _identifier(
        engagement_id, label="engagement_id", pattern=_ENGAGEMENT_ID_RE
    )
    path = _engagement_root(client_root.resolve(), engagement_id) / "engagement.json"
    return _validate_engagement_manifest(
        _read_json(path, label="engagement manifest"),
        expected_client_id=client["client_id"],
    )


def create_engagement(
    client_root: Path,
    client_id: str,
    label: str,
) -> dict[str, Any]:
    """Create one explicit engagement in the customer folder."""

    root = _ordinary_directory(client_root, label="client folder")
    client = load_client_manifest(root)
    if client["client_id"] != client_id:
        raise LedgerError("Customer folder belongs to another client.")
    engagements_root = _ordinary_directory(
        _engagements_root(root), label="engagement ledger directory"
    )
    for _ in range(100):
        engagement_id = _new_id("eng")
        target = engagements_root / engagement_id
        try:
            target.mkdir(mode=0o700)
            break
        except FileExistsError:
            continue
    else:
        raise LedgerError("Could not allocate a unique engagement ID.")
    try:
        for child in ("inputs", "runs"):
            (target / child).mkdir(mode=0o700)
        content = {
            "schema_version": ENGAGEMENT_MANIFEST_SCHEMA,
            "client_id": client_id,
            "engagement_id": engagement_id,
            "label": _text(label, label="engagement label", maximum=160),
            "status": "open",
            "created_at": _now_iso(),
            "closed_at": None,
        }
        manifest = _sealed(content)
        _write_json(target / "engagement.json", manifest)
        lock_descriptor = _open_engagement_lock(target / _ENGAGEMENT_LOCK_NAME)
        os.close(lock_descriptor)
    except (LedgerError, OSError):
        shutil.rmtree(target, ignore_errors=True)
        raise
    return manifest


def _iter_manifest_directories(root: Path, *, prefix: str, maximum: int) -> list[Path]:
    directory = _ordinary_directory(root, label="ledger collection")
    entries = sorted(directory.iterdir(), key=lambda item: item.name)
    if len(entries) > maximum:
        raise LedgerError("Ledger collection exceeds its supported size.")
    result: list[Path] = []
    pattern = re.compile(rf"^{re.escape(prefix)}_[0-9a-f]{{24}}$")
    for entry in entries:
        observed = entry.lstat()
        if (
            entry.is_symlink()
            or not stat.S_ISDIR(observed.st_mode)
            or pattern.fullmatch(entry.name) is None
        ):
            raise LedgerError("Ledger collection contains an invalid entry.")
        result.append(entry)
    return result


def list_engagements(client_root: Path, client_id: str) -> tuple[dict[str, Any], ...]:
    """List every validated engagement stored in one customer folder."""

    client = load_client_manifest(client_root)
    if client["client_id"] != client_id:
        raise LedgerError("Customer folder belongs to another client.")
    manifests = [
        _validate_engagement_manifest(
            _read_json(path / "engagement.json", label="engagement manifest"),
            expected_client_id=client_id,
        )
        for path in _iter_manifest_directories(
            _engagements_root(client_root.resolve()),
            prefix="eng",
            maximum=_MAX_RUNS,
        )
    ]
    return tuple(
        sorted(manifests, key=lambda item: (item["created_at"], item["engagement_id"]))
    )


def _validate_input_receipt(
    payload: Mapping[str, Any],
    *,
    expected_client_id: str | None = None,
    expected_engagement_id: str | None = None,
) -> dict[str, Any]:
    normalized = _validate_seal(payload, label="input receipt")
    required = {
        "schema_version",
        "client_id",
        "engagement_id",
        "input_id",
        "role",
        "stored_name",
        "original_name",
        "byte_count",
        "sha256",
        "imported_at",
        "content_sha256",
    }
    if (
        set(normalized) != required
        or normalized["schema_version"] != INPUT_RECEIPT_SCHEMA
    ):
        raise LedgerError("Input receipt shape is invalid.")
    client_id = _identifier(
        normalized["client_id"], label="client_id", pattern=_CLIENT_ID_RE
    )
    engagement_id = _identifier(
        normalized["engagement_id"], label="engagement_id", pattern=_ENGAGEMENT_ID_RE
    )
    _identifier(normalized["input_id"], label="input_id", pattern=_INPUT_ID_RE)
    if normalized["role"] not in IMPORT_ROLES:
        raise LedgerError("Input receipt role is invalid.")
    for key in ("stored_name", "original_name"):
        name = _text(normalized[key], label=key, maximum=255)
        if Path(name).name != name or name in {".", "..", "receipt.json"}:
            raise LedgerError(f"Input receipt {key} is unsafe.")
    if (
        not isinstance(normalized["byte_count"], int)
        or isinstance(normalized["byte_count"], bool)
        or normalized["byte_count"] < 0
        or not isinstance(normalized["sha256"], str)
        or _SHA256_RE.fullmatch(normalized["sha256"]) is None
    ):
        raise LedgerError("Input receipt byte identity is invalid.")
    _text(normalized["imported_at"], label="imported_at", maximum=80)
    if expected_client_id is not None and client_id != expected_client_id:
        raise LedgerError("Input receipt belongs to another client.")
    if expected_engagement_id is not None and engagement_id != expected_engagement_id:
        raise LedgerError("Input receipt belongs to another engagement.")
    return normalized


def load_input_receipt(
    client_root: Path,
    engagement_id: str,
    input_id: str,
    *,
    verify_bytes: bool = True,
) -> dict[str, Any]:
    """Load one receipt and optionally replay the controlled-copy hash."""

    client = load_client_manifest(client_root)
    engagement = load_engagement_manifest(client_root, engagement_id)
    input_id = _identifier(input_id, label="input_id", pattern=_INPUT_ID_RE)
    input_root = (
        _engagement_root(client_root.resolve(), engagement_id) / "inputs" / input_id
    )
    _ordinary_directory(input_root, label="input snapshot")
    receipt = _validate_input_receipt(
        _read_json(input_root / "receipt.json", label="input receipt"),
        expected_client_id=client["client_id"],
        expected_engagement_id=engagement["engagement_id"],
    )
    if receipt["input_id"] != input_id:
        raise LedgerError("Input directory and receipt IDs disagree.")
    stored = input_root / receipt["stored_name"]
    if verify_bytes:
        byte_count, sha256 = _stable_file_identity(
            stored,
            label="controlled input snapshot",
        )
        if byte_count != receipt["byte_count"] or sha256 != receipt["sha256"]:
            raise LedgerError(
                "Controlled input snapshot no longer matches its receipt."
            )
    else:
        _ordinary_file(stored, label="controlled input snapshot")
    return {
        **receipt,
        "relative_path": stored.relative_to(client_root.resolve()).as_posix(),
        "receipt_relative_path": (input_root / "receipt.json")
        .relative_to(client_root.resolve())
        .as_posix(),
        "path": str(stored),
    }


def list_inputs(client_root: Path, engagement_id: str) -> tuple[dict[str, Any], ...]:
    """List and re-hash every immutable input receipt in one engagement."""

    load_engagement_manifest(client_root, engagement_id)
    inputs_root = _engagement_root(client_root.resolve(), engagement_id) / "inputs"
    receipts = [
        load_input_receipt(client_root, engagement_id, directory.name)
        for directory in _iter_manifest_directories(
            inputs_root, prefix="input", maximum=_MAX_INPUTS
        )
    ]
    return tuple(
        sorted(receipts, key=lambda item: (item["imported_at"], item["input_id"]))
    )


def _stable_copy(source_path: Path, destination: Path) -> tuple[int, str]:
    source = source_path.expanduser()
    if not source.is_absolute() or source.is_symlink():
        raise LedgerError("Imported document must be an absolute non-symlink file.")
    before_path = _ordinary_file(source, label="import source")
    source_descriptor = os.open(source, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
    temporary: Path | None = None
    try:
        before = os.fstat(source_descriptor)
        identity = (
            before.st_dev,
            before.st_ino,
            before.st_size,
            before.st_mtime_ns,
            before.st_ctime_ns,
        )
        if identity != (
            before_path.st_dev,
            before_path.st_ino,
            before_path.st_size,
            before_path.st_mtime_ns,
            before_path.st_ctime_ns,
        ):
            raise LedgerError("Imported document changed before it was opened.")
        descriptor, temporary_name = tempfile.mkstemp(
            prefix=".vera-input-", suffix=".tmp", dir=destination.parent
        )
        temporary = Path(temporary_name)
        digest = hashlib.sha256()
        byte_count = 0
        with os.fdopen(descriptor, "wb") as target:
            while True:
                chunk = os.read(source_descriptor, 1024 * 1024)
                if not chunk:
                    break
                target.write(chunk)
                digest.update(chunk)
                byte_count += len(chunk)
            target.flush()
            os.fsync(target.fileno())
        after = os.fstat(source_descriptor)
        final_path = source.lstat()
        final_identity = (
            after.st_dev,
            after.st_ino,
            after.st_size,
            after.st_mtime_ns,
            after.st_ctime_ns,
        )
        if final_identity != identity or final_identity != (
            final_path.st_dev,
            final_path.st_ino,
            final_path.st_size,
            final_path.st_mtime_ns,
            final_path.st_ctime_ns,
        ):
            raise LedgerError("Imported document changed during the copy.")
        os.replace(temporary, destination)
        temporary = None
        return byte_count, digest.hexdigest()
    finally:
        os.close(source_descriptor)
        if temporary is not None and temporary.exists():
            temporary.unlink()


def import_document(
    client_root: Path,
    client_id: str,
    engagement_id: str,
    source_path: Path,
    role: str,
) -> dict[str, Any]:
    """Create or reuse one immutable, content-addressed input snapshot."""

    root = _ordinary_directory(client_root, label="client folder")
    client = load_client_manifest(root)
    engagement = load_engagement_manifest(root, engagement_id)
    if client["client_id"] != client_id or engagement["client_id"] != client_id:
        raise LedgerError("Selected client and engagement do not match.")
    if engagement["status"] != "open":
        raise LedgerError("Documents cannot be imported into a closed engagement.")
    if role not in IMPORT_ROLES:
        raise LedgerError("Import role must be journal, source, or support.")
    selected_source = source_path.expanduser()
    if not selected_source.is_absolute():
        raise LedgerError("Imported document must use an absolute path.")
    _ordinary_file(selected_source, label="import source")
    source = selected_source.resolve(strict=True)
    if source != selected_source:
        raise LedgerError("Imported document path cannot contain symbolic links.")
    source_stat = _ordinary_file(source, label="import source")
    source_sha256 = _sha256_file(source)
    with _engagement_lock(root, engagement_id):
        engagement = load_engagement_manifest(root, engagement_id)
        if engagement["client_id"] != client_id:
            raise LedgerError("Selected client and engagement do not match.")
        if engagement["status"] != "open":
            raise LedgerError("Documents cannot be imported into a closed engagement.")
        inputs_root = _ordinary_directory(
            _engagement_root(root, engagement_id) / "inputs",
            label="engagement input directory",
        )
        for input_dir in _iter_manifest_directories(
            inputs_root, prefix="input", maximum=_MAX_INPUTS
        ):
            receipt = load_input_receipt(root, engagement_id, input_dir.name)
            if receipt["role"] == role and receipt["sha256"] == source_sha256:
                if receipt["byte_count"] != source_stat.st_size:
                    raise LedgerError(
                        "Matching input digest has a conflicting byte count."
                    )
                return {
                    "status": "already_imported",
                    "receipt": receipt,
                    "imported_path": receipt["path"],
                    "original_preserved": True,
                    "source_archive_mutated": False,
                }
        input_id = _new_id("input")
        target = inputs_root / input_id
        target.mkdir(mode=0o700)
        safe_name = source.name
        if Path(safe_name).name != safe_name or safe_name in {
            "",
            ".",
            "..",
            "receipt.json",
        }:
            target.rmdir()
            raise LedgerError("Imported document name is unsafe.")
        destination = target / safe_name
        try:
            byte_count, digest = _stable_copy(source, destination)
            if digest != source_sha256 or byte_count != source_stat.st_size:
                raise LedgerError("Imported document copy does not match its source.")
            content = {
                "schema_version": INPUT_RECEIPT_SCHEMA,
                "client_id": client_id,
                "engagement_id": engagement_id,
                "input_id": input_id,
                "role": role,
                "stored_name": safe_name,
                "original_name": safe_name,
                "byte_count": byte_count,
                "sha256": digest,
                "imported_at": _now_iso(),
            }
            _write_json(target / "receipt.json", _sealed(content))
            receipt = load_input_receipt(root, engagement_id, input_id)
        except (LedgerError, OSError):
            shutil.rmtree(target, ignore_errors=True)
            raise
        return {
            "status": "imported",
            "receipt": receipt,
            "imported_path": receipt["path"],
            "original_preserved": True,
            "source_archive_mutated": True,
        }


def _validate_artifact_record(record: Mapping[str, Any]) -> dict[str, Any]:
    required = {
        "artifact_id",
        "path",
        "purpose",
        "audience",
        "media_type",
        "byte_count",
        "sha256",
    }
    if set(record) != required:
        raise LedgerError("Artifact declaration shape is invalid.")
    artifact_id = _text(record["artifact_id"], label="artifact_id", maximum=120)
    if _ARTIFACT_ID_RE.fullmatch(artifact_id) is None:
        raise LedgerError("artifact_id is invalid.")
    path = _relative_path(record["path"], label="artifact path")
    purpose = _text(record["purpose"], label="artifact purpose", maximum=500)
    audience = record["audience"]
    if audience not in ARTIFACT_AUDIENCES:
        raise LedgerError("Artifact audience is invalid.")
    media_type = _text(record["media_type"], label="artifact media_type", maximum=160)
    byte_count = record["byte_count"]
    sha256 = record["sha256"]
    if (
        not isinstance(byte_count, int)
        or isinstance(byte_count, bool)
        or byte_count < 0
        or not isinstance(sha256, str)
        or _SHA256_RE.fullmatch(sha256) is None
    ):
        raise LedgerError("Artifact byte identity is invalid.")
    return {
        "artifact_id": artifact_id,
        "path": path,
        "purpose": purpose,
        "audience": audience,
        "media_type": media_type,
        "byte_count": byte_count,
        "sha256": sha256,
    }


def _load_artifact_binding(
    client_root: Path,
    engagement_id: str,
    reference: Mapping[str, Any],
) -> dict[str, Any]:
    if set(reference) != {"run_id", "artifact_id", "role"}:
        raise LedgerError("Upstream artifact reference shape is invalid.")
    run_id = _identifier(reference["run_id"], label="run_id", pattern=_RUN_ID_RE)
    artifact_id = _text(reference["artifact_id"], label="artifact_id", maximum=120)
    role = _text(reference["role"], label="upstream artifact role", maximum=80)
    upstream = load_run(client_root, engagement_id, run_id, verify_inputs=True)
    if upstream["run"]["status"] not in {"ready_for_review", "completed"}:
        raise LedgerError("Upstream run is not available for handoff.")
    artifacts = validate_run_artifacts(client_root, engagement_id, run_id)
    artifact = next(
        (item for item in artifacts["artifacts"] if item["artifact_id"] == artifact_id),
        None,
    )
    if artifact is None:
        raise LedgerError("Upstream artifact was not found in its manifest.")
    run_root = _run_root(client_root.resolve(), engagement_id, run_id)
    source = run_root / "outputs" / artifact["path"]
    return {
        "binding_id": f"artifact:{run_id}:{artifact_id}",
        "kind": "upstream_artifact",
        "role": role,
        "source_relative_path": source.relative_to(client_root.resolve()).as_posix(),
        "execution_relative_path": (
            Path("inputs") / "upstream" / run_id / artifact["path"]
        ).as_posix(),
        "receipt_relative_path": (run_root / "artifact_manifest.json")
        .relative_to(client_root.resolve())
        .as_posix(),
        "receipt_sha256": artifacts["content_sha256"],
        "sha256": artifact["sha256"],
        "byte_count": artifact["byte_count"],
        "upstream_workflow_id": upstream["run"]["workflow_id"],
        "upstream_run_id": run_id,
        "upstream_artifact_id": artifact_id,
    }


def _input_binding(receipt: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "binding_id": receipt["input_id"],
        "kind": "import",
        "role": receipt["role"],
        "source_relative_path": receipt["relative_path"],
        "execution_relative_path": (
            Path("inputs")
            / "imports"
            / receipt["input_id"]
            / Path(receipt["relative_path"]).name
        ).as_posix(),
        "receipt_relative_path": receipt["receipt_relative_path"],
        "receipt_sha256": receipt["content_sha256"],
        "sha256": receipt["sha256"],
        "byte_count": receipt["byte_count"],
        "upstream_workflow_id": None,
        "upstream_run_id": None,
        "upstream_artifact_id": None,
    }


def _validate_input_manifest(payload: Mapping[str, Any]) -> dict[str, Any]:
    normalized = _validate_seal(payload, label="run input manifest")
    required = {
        "schema_version",
        "client_id",
        "engagement_id",
        "run_id",
        "inputs",
        "content_sha256",
    }
    if (
        set(normalized) != required
        or normalized["schema_version"] != INPUT_MANIFEST_SCHEMA
    ):
        raise LedgerError("Run input manifest shape is invalid.")
    _identifier(normalized["client_id"], label="client_id", pattern=_CLIENT_ID_RE)
    _identifier(
        normalized["engagement_id"], label="engagement_id", pattern=_ENGAGEMENT_ID_RE
    )
    _identifier(normalized["run_id"], label="run_id", pattern=_RUN_ID_RE)
    inputs = normalized["inputs"]
    if not isinstance(inputs, list) or not inputs or len(inputs) > _MAX_INPUTS:
        raise LedgerError("Every run must bind one or more exact inputs.")
    required_input = {
        "binding_id",
        "kind",
        "role",
        "source_relative_path",
        "execution_relative_path",
        "receipt_relative_path",
        "receipt_sha256",
        "sha256",
        "byte_count",
        "upstream_workflow_id",
        "upstream_run_id",
        "upstream_artifact_id",
    }
    seen_ids: set[str] = set()
    seen_paths: set[str] = set()
    seen_execution_paths: set[str] = set()
    for item in inputs:
        if not isinstance(item, dict) or set(item) != required_input:
            raise LedgerError("Run input binding shape is invalid.")
        binding_id = _text(item["binding_id"], label="binding_id", maximum=260)
        if binding_id in seen_ids:
            raise LedgerError("Run input bindings must be unique.")
        source_path = _relative_path(item["source_relative_path"], label="source path")
        execution_path = _relative_path(
            item["execution_relative_path"], label="execution path"
        )
        if not execution_path.startswith("inputs/"):
            raise LedgerError("Run execution path must stay inside inputs.")
        _relative_path(item["receipt_relative_path"], label="receipt path")
        if (
            not isinstance(item["receipt_sha256"], str)
            or _SHA256_RE.fullmatch(item["receipt_sha256"]) is None
        ):
            raise LedgerError("Run input receipt digest is invalid.")
        if source_path in seen_paths:
            raise LedgerError("Run input source paths must be unique.")
        if execution_path in seen_execution_paths:
            raise LedgerError("Run execution input paths must be unique.")
        if item["kind"] not in {"import", "upstream_artifact"}:
            raise LedgerError("Run input binding kind is invalid.")
        _text(item["role"], label="input role", maximum=80)
        if (
            not isinstance(item["byte_count"], int)
            or isinstance(item["byte_count"], bool)
            or item["byte_count"] < 0
            or not isinstance(item["sha256"], str)
            or _SHA256_RE.fullmatch(item["sha256"]) is None
        ):
            raise LedgerError("Run input byte identity is invalid.")
        if item["kind"] == "import":
            _identifier(binding_id, label="input_id", pattern=_INPUT_ID_RE)
            if any(
                item[key] is not None
                for key in (
                    "upstream_workflow_id",
                    "upstream_run_id",
                    "upstream_artifact_id",
                )
            ):
                raise LedgerError("Imported input has upstream artifact fields.")
        else:
            _text(
                item["upstream_workflow_id"],
                label="upstream_workflow_id",
                maximum=80,
            )
            _identifier(
                item["upstream_run_id"],
                label="upstream_run_id",
                pattern=_RUN_ID_RE,
            )
            _text(
                item["upstream_artifact_id"],
                label="upstream_artifact_id",
                maximum=120,
            )
        seen_ids.add(binding_id)
        seen_paths.add(source_path)
        seen_execution_paths.add(execution_path)
    return normalized


def _run_static_content(run: Mapping[str, Any]) -> dict[str, Any]:
    return {
        key: run[key]
        for key in (
            "schema_version",
            "client_id",
            "engagement_id",
            "workflow_id",
            "workflow_version",
            "run_id",
            "label",
            "purpose",
            "idempotency_key",
            "input_manifest",
            "input_manifest_sha256",
            "context",
            "created_at",
        )
    }


def _validate_run_manifest(payload: Mapping[str, Any]) -> dict[str, Any]:
    required = {
        "schema_version",
        "client_id",
        "engagement_id",
        "workflow_id",
        "workflow_version",
        "run_id",
        "label",
        "purpose",
        "idempotency_key",
        "input_manifest",
        "input_manifest_sha256",
        "context",
        "created_at",
        "status",
        "updated_at",
        "failure",
        "status_history",
        "static_sha256",
    }
    if set(payload) != required or payload.get("schema_version") != RUN_MANIFEST_SCHEMA:
        raise LedgerError("Run manifest shape is invalid.")
    _identifier(payload["client_id"], label="client_id", pattern=_CLIENT_ID_RE)
    _identifier(
        payload["engagement_id"], label="engagement_id", pattern=_ENGAGEMENT_ID_RE
    )
    _identifier(payload["run_id"], label="run_id", pattern=_RUN_ID_RE)
    _text(payload["workflow_id"], label="workflow_id", maximum=80)
    _text(payload["workflow_version"], label="workflow_version", maximum=80)
    _text(payload["label"], label="run label", maximum=160)
    _text(payload["purpose"], label="run purpose", maximum=500)
    _text(payload["idempotency_key"], label="idempotency_key", maximum=200)
    _relative_path(payload["input_manifest"], label="input manifest path")
    _relative_path(payload["context"], label="context path")
    if (
        not isinstance(payload["input_manifest_sha256"], str)
        or _SHA256_RE.fullmatch(payload["input_manifest_sha256"]) is None
    ):
        raise LedgerError("Run input manifest digest is invalid.")
    if payload["status"] not in RUN_LIFECYCLE_STATES:
        raise LedgerError("Run status is invalid.")
    for key in ("created_at", "updated_at"):
        _text(payload[key], label=key, maximum=80)
    failure = payload["failure"]
    if failure is not None:
        if not isinstance(failure, dict) or set(failure) != {"reason", "recorded_at"}:
            raise LedgerError("Run failure record is invalid.")
        _text(failure["reason"], label="failure reason", maximum=1000)
        _text(failure["recorded_at"], label="failure recorded_at", maximum=80)
    if payload["status"] == "failed":
        if failure is None or failure["recorded_at"] != payload["updated_at"]:
            raise LedgerError("Run failure record is stale.")
    elif failure is not None:
        raise LedgerError("A non-failed run cannot retain a failure record.")
    history = payload["status_history"]
    if not isinstance(history, list) or not history:
        raise LedgerError("Run status history is invalid.")
    observed_statuses: list[str] = []
    for event in history:
        if (
            not isinstance(event, dict)
            or set(event) != {"status", "at"}
            or event["status"] not in RUN_LIFECYCLE_STATES
        ):
            raise LedgerError("Run status history entry is invalid.")
        _text(event["at"], label="status timestamp", maximum=80)
        observed_statuses.append(event["status"])
    if observed_statuses[0] != "prepared":
        raise LedgerError("Run status history must begin with prepared.")
    if any(
        target not in _RUN_TRANSITIONS[current]
        for current, target in zip(observed_statuses, observed_statuses[1:])
    ):
        raise LedgerError("Run status history contains an invalid transition.")
    if (
        history[-1]["status"] != payload["status"]
        or history[-1]["at"] != payload["updated_at"]
    ):
        raise LedgerError("Run status history is stale.")
    static_sha256 = payload["static_sha256"]
    if not isinstance(static_sha256, str) or static_sha256 != _canonical_json_sha256(
        _run_static_content(payload)
    ):
        raise LedgerError("Run manifest static digest is stale.")
    return dict(payload)


def _context_content(run: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "schema_version": RUN_CONTEXT_SCHEMA,
        "client_id": run["client_id"],
        "engagement_id": run["engagement_id"],
        "workflow_id": run["workflow_id"],
        "workflow_version": run["workflow_version"],
        "run_id": run["run_id"],
        "label": run["label"],
        "purpose": run["purpose"],
        "created_at": run["created_at"],
        "input_manifest": run["input_manifest"],
        "input_manifest_sha256": run["input_manifest_sha256"],
        "run_relative_path": (
            Path(LEDGER_DIRECTORY)
            / "engagements"
            / run["engagement_id"]
            / "runs"
            / run["run_id"]
        ).as_posix(),
        "output_relative_path": "outputs",
    }


def _validate_context(
    payload: Mapping[str, Any], run: Mapping[str, Any]
) -> dict[str, Any]:
    normalized = _validate_seal(payload, label="run context")
    expected = _sealed(_context_content(run))
    if normalized != expected:
        raise LedgerError("Run context does not match its run manifest.")
    return normalized


def _load_run_paths(
    client_root: Path, engagement_id: str, run_id: str
) -> tuple[Path, Path, Path, Path]:
    root = _ordinary_directory(client_root, label="client folder")
    engagement_id = _identifier(
        engagement_id, label="engagement_id", pattern=_ENGAGEMENT_ID_RE
    )
    run_id = _identifier(run_id, label="run_id", pattern=_RUN_ID_RE)
    run_root = _run_root(root, engagement_id, run_id)
    _ordinary_directory(run_root, label="workflow run")
    return (
        run_root,
        run_root / "run.json",
        run_root / "input_manifest.json",
        run_root / "context.json",
    )


def load_run(
    client_root: Path,
    engagement_id: str,
    run_id: str,
    *,
    verify_inputs: bool = True,
) -> dict[str, Any]:
    """Replay one run and materialize its current absolute paths."""

    root = _ordinary_directory(client_root, label="client folder")
    client = load_client_manifest(root)
    engagement = load_engagement_manifest(root, engagement_id)
    run_root, run_path, input_path, context_path = _load_run_paths(
        root, engagement_id, run_id
    )
    run = _validate_run_manifest(_read_json(run_path, label="run manifest"))
    if run["client_id"] != client["client_id"] or run["engagement_id"] != engagement_id:
        raise LedgerError("Run belongs to another client or engagement.")
    inputs = _validate_input_manifest(
        _read_json(input_path, label="run input manifest")
    )
    if (
        inputs["client_id"] != client["client_id"]
        or inputs["engagement_id"] != engagement_id
        or inputs["run_id"] != run_id
        or inputs["content_sha256"] != run["input_manifest_sha256"]
    ):
        raise LedgerError("Run input manifest does not match the run.")
    context = _validate_context(_read_json(context_path, label="run context"), run)
    resolved_bindings: list[dict[str, Any]] = []
    for binding in inputs["inputs"]:
        source = root / binding["source_relative_path"]
        if verify_inputs:
            byte_count, sha256 = _stable_file_identity(
                source,
                label="bound workflow input",
            )
            if byte_count != binding["byte_count"] or sha256 != binding["sha256"]:
                raise LedgerError(
                    "A bound workflow input no longer matches its receipt."
                )
        else:
            _ordinary_file(source, label="bound workflow input")
        execution = run_root / binding["execution_relative_path"]
        if verify_inputs:
            execution_byte_count, execution_sha256 = _stable_file_identity(
                execution,
                label="run execution input",
            )
            if (
                execution_byte_count != binding["byte_count"]
                or execution_sha256 != binding["sha256"]
            ):
                raise LedgerError("Run execution input no longer matches its receipt.")
        else:
            _ordinary_file(execution, label="run execution input")
        receipt_path = root / binding["receipt_relative_path"]
        _ordinary_file(receipt_path, label="bound workflow input receipt")
        if binding["kind"] == "import":
            receipt = _validate_input_receipt(
                _read_json(receipt_path, label="bound input receipt"),
                expected_client_id=client["client_id"],
                expected_engagement_id=engagement_id,
            )
            expected_receipt_path = (
                _engagement_root(root, engagement_id)
                / "inputs"
                / binding["binding_id"]
                / "receipt.json"
            )
            if (
                receipt_path != expected_receipt_path
                or receipt["input_id"] != binding["binding_id"]
                or receipt["content_sha256"] != binding["receipt_sha256"]
                or receipt["sha256"] != binding["sha256"]
                or receipt["byte_count"] != binding["byte_count"]
                or receipt_path.parent / receipt["stored_name"] != source
            ):
                raise LedgerError("Bound input receipt no longer matches its run.")
        else:
            upstream_run_id = binding["upstream_run_id"]
            expected_receipt_path = (
                _run_root(root, engagement_id, upstream_run_id)
                / "artifact_manifest.json"
            )
            if receipt_path != expected_receipt_path:
                raise LedgerError("Upstream artifact receipt path is stale.")
            artifact_manifest = validate_run_artifacts(
                root,
                engagement_id,
                upstream_run_id,
            )
            artifact = next(
                (
                    item
                    for item in artifact_manifest["artifacts"]
                    if item["artifact_id"] == binding["upstream_artifact_id"]
                ),
                None,
            )
            if (
                artifact_manifest["content_sha256"] != binding["receipt_sha256"]
                or artifact_manifest["workflow_id"] != binding["upstream_workflow_id"]
                or artifact is None
                or artifact["sha256"] != binding["sha256"]
                or artifact["byte_count"] != binding["byte_count"]
                or receipt_path.parent / "outputs" / artifact["path"] != source
            ):
                raise LedgerError(
                    "Upstream artifact receipt no longer matches its run."
                )
        resolved_bindings.append(
            {**binding, "source_path": str(source), "path": str(execution)}
        )
    output_dir = run_root / "outputs"
    _ordinary_directory(output_dir, label="workflow output directory")
    hydrated_context = {
        **context,
        "studio_client_folder": {
            "schema_version": "vera.studio_client_folder.runtime.v1",
            "studio_client_id": client["client_id"],
            "client_root": str(root),
        },
        "input_bindings": resolved_bindings,
        "input_dir": str(run_root / "inputs"),
        "workspace_root": str(root / LEDGER_DIRECTORY),
        "output_dir": str(output_dir),
        "run_root": str(run_root),
        "run_manifest_path": str(run_path),
        "input_manifest_path": str(input_path),
        "context_path": str(context_path),
    }
    return {
        "run": run,
        "input_manifest": inputs,
        "context": hydrated_context,
        "run_root": str(run_root),
        "output_dir": str(output_dir),
        "context_path": str(context_path),
    }


def _iter_runs(client_root: Path, engagement_id: str) -> list[dict[str, Any]]:
    runs_root = _engagement_root(client_root.resolve(), engagement_id) / "runs"
    result: list[dict[str, Any]] = []
    for directory in _iter_manifest_directories(
        runs_root, prefix="run", maximum=_MAX_RUNS
    ):
        result.append(load_run(client_root, engagement_id, directory.name))
    return sorted(
        result,
        key=lambda item: (item["run"]["created_at"], item["run"]["run_id"]),
    )


def list_runs(
    client_root: Path,
    engagement_id: str,
    *,
    verify_inputs: bool = True,
) -> tuple[dict[str, Any], ...]:
    """List every validated run in creation order for one engagement."""

    load_engagement_manifest(client_root, engagement_id)
    if verify_inputs:
        return tuple(_iter_runs(client_root, engagement_id))
    runs_root = _engagement_root(client_root.resolve(), engagement_id) / "runs"
    result = [
        load_run(
            client_root,
            engagement_id,
            directory.name,
            verify_inputs=False,
        )
        for directory in _iter_manifest_directories(
            runs_root, prefix="run", maximum=_MAX_RUNS
        )
    ]
    return tuple(
        sorted(
            result,
            key=lambda item: (item["run"]["created_at"], item["run"]["run_id"]),
        )
    )


def prepare_run(
    client_root: Path,
    client_id: str,
    engagement_id: str,
    workflow_id: str,
    workflow_version: str,
    *,
    input_ids: Sequence[str] = (),
    upstream_artifacts: Sequence[Mapping[str, Any]] = (),
    label: str | None = None,
    purpose: str | None = None,
    idempotency_key: str | None = None,
    new_run: bool = False,
) -> dict[str, Any]:
    """Prepare or replay one exact, idempotent workflow run."""

    root = _ordinary_directory(client_root, label="client folder")
    client = load_client_manifest(root)
    engagement = load_engagement_manifest(root, engagement_id)
    if client["client_id"] != client_id or engagement["client_id"] != client_id:
        raise LedgerError("Selected client and engagement do not match.")
    if engagement["status"] != "open":
        raise LedgerError("A workflow cannot be prepared in a closed engagement.")
    workflow_id = _text(workflow_id, label="workflow_id", maximum=80)
    workflow_version = _text(workflow_version, label="workflow_version", maximum=80)
    bindings = [
        _input_binding(load_input_receipt(root, engagement_id, input_id))
        for input_id in input_ids
    ]
    bindings.extend(
        _load_artifact_binding(root, engagement_id, reference)
        for reference in upstream_artifacts
    )
    if not bindings:
        raise LedgerError("Every workflow run must select at least one exact input.")
    binding_ids = [item["binding_id"] for item in bindings]
    if len(set(binding_ids)) != len(binding_ids):
        raise LedgerError("Workflow input selections contain duplicates.")
    normalized_label = _text(
        label or workflow_id.replace("-", " ").title(),
        label="run label",
        maximum=160,
    )
    normalized_purpose = _text(
        purpose or f"Execute the {workflow_id} workflow for this engagement.",
        label="run purpose",
        maximum=500,
    )
    request_content = {
        "client_id": client_id,
        "engagement_id": engagement_id,
        "workflow_id": workflow_id,
        "workflow_version": workflow_version,
        "label": normalized_label,
        "purpose": normalized_purpose,
        "inputs": bindings,
    }
    request_sha256 = _canonical_json_sha256(request_content)
    normalized_key = _text(
        idempotency_key or f"auto:{request_sha256}",
        label="idempotency_key",
        maximum=200,
    )
    stored_key = (
        "new:" + hashlib.sha256(normalized_key.encode("utf-8")).hexdigest()
        if new_run
        else normalized_key
    )
    with _engagement_lock(root, engagement_id):
        engagement = load_engagement_manifest(root, engagement_id)
        if engagement["client_id"] != client_id:
            raise LedgerError("Selected client and engagement do not match.")
        if engagement["status"] != "open":
            raise LedgerError("A workflow cannot be prepared in a closed engagement.")
        existing_runs = _iter_runs(root, engagement_id)
        for existing in existing_runs:
            run = existing["run"]
            if run["idempotency_key"] != stored_key:
                continue
            existing_request = {
                "client_id": run["client_id"],
                "engagement_id": run["engagement_id"],
                "workflow_id": run["workflow_id"],
                "workflow_version": run["workflow_version"],
                "label": run["label"],
                "purpose": run["purpose"],
                "inputs": existing["input_manifest"]["inputs"],
            }
            if _canonical_json_sha256(existing_request) != request_sha256:
                raise LedgerError(
                    "Idempotency key is already bound to a different run request."
                )
            return {"status": "already_prepared", **existing}
        runs_root = _ordinary_directory(
            _engagement_root(root, engagement_id) / "runs",
            label="workflow runs directory",
        )
        for _ in range(100):
            run_id = _new_id("run")
            run_root = runs_root / run_id
            try:
                run_root.mkdir(mode=0o700)
                break
            except FileExistsError:
                continue
        else:
            raise LedgerError("Could not allocate a unique run ID.")
        try:
            (run_root / "inputs").mkdir(mode=0o700)
            (run_root / "outputs").mkdir(mode=0o700)
            for binding in bindings:
                source = root / binding["source_relative_path"]
                destination = run_root / binding["execution_relative_path"]
                destination_parent = run_root
                for part in destination.parent.relative_to(run_root).parts:
                    destination_parent /= part
                    if (
                        not destination_parent.exists()
                        and not destination_parent.is_symlink()
                    ):
                        destination_parent.mkdir(mode=0o700)
                    _ordinary_directory(
                        destination_parent,
                        label="run execution input directory",
                    )
                _ordinary_file(source, label="selected run input")
                copied_bytes, copied_sha256 = _stable_copy(source, destination)
                copied = _ordinary_file(destination, label="run execution input")
                if (
                    copied.st_size != binding["byte_count"]
                    or copied_bytes != binding["byte_count"]
                    or copied_sha256 != binding["sha256"]
                ):
                    raise LedgerError("Run execution input copy is not exact.")
            inputs_content = {
                "schema_version": INPUT_MANIFEST_SCHEMA,
                "client_id": client_id,
                "engagement_id": engagement_id,
                "run_id": run_id,
                "inputs": bindings,
            }
            input_manifest = _sealed(inputs_content)
            created_at = _now_iso()
            run: dict[str, Any] = {
                "schema_version": RUN_MANIFEST_SCHEMA,
                "client_id": client_id,
                "engagement_id": engagement_id,
                "workflow_id": workflow_id,
                "workflow_version": workflow_version,
                "run_id": run_id,
                "label": normalized_label,
                "purpose": normalized_purpose,
                "idempotency_key": stored_key,
                "input_manifest": "input_manifest.json",
                "input_manifest_sha256": input_manifest["content_sha256"],
                "context": "context.json",
                "created_at": created_at,
                "status": "prepared",
                "updated_at": created_at,
                "failure": None,
                "status_history": [{"status": "prepared", "at": created_at}],
            }
            run["static_sha256"] = _canonical_json_sha256(_run_static_content(run))
            context = _sealed(_context_content(run))
            _write_json(run_root / "input_manifest.json", input_manifest)
            _write_json(run_root / "context.json", context)
            _write_json(run_root / "run.json", run)
            loaded = load_run(root, engagement_id, run_id)
        except (LedgerError, OSError):
            shutil.rmtree(run_root, ignore_errors=True)
            raise
        return {"status": "prepared", **loaded}


def _write_run_status_locked(
    client_root: Path,
    engagement_id: str,
    run_id: str,
    target_status: str,
    *,
    reason: str | None = None,
) -> dict[str, Any]:
    engagement = load_engagement_manifest(client_root, engagement_id)
    loaded = load_run(client_root, engagement_id, run_id)
    run = loaded["run"]
    current = run["status"]
    if target_status == current:
        if current == "completed":
            validate_run_artifacts(client_root, engagement_id, run_id)
        return loaded
    if engagement["status"] != "open":
        raise LedgerError("Runs cannot change after their engagement is closed.")
    if target_status not in _RUN_TRANSITIONS[current]:
        raise LedgerError(f"Run cannot transition from {current} to {target_status}.")
    if target_status == "completed":
        validate_run_artifacts(client_root, engagement_id, run_id)
    at = _now_iso()
    updated = {
        **run,
        "status": target_status,
        "updated_at": at,
        "failure": (
            {
                "reason": _text(reason, label="failure reason", maximum=1000),
                "recorded_at": at,
            }
            if target_status == "failed"
            else None
        ),
        "status_history": [
            *run["status_history"],
            {"status": target_status, "at": at},
        ],
    }
    _write_json(Path(loaded["run_root"]) / "run.json", updated)
    return load_run(client_root, engagement_id, run_id)


def _write_run_status(
    client_root: Path,
    engagement_id: str,
    run_id: str,
    target_status: str,
    *,
    reason: str | None = None,
) -> dict[str, Any]:
    root = _ordinary_directory(client_root, label="client folder")
    with _engagement_lock(root, engagement_id):
        return _write_run_status_locked(
            root,
            engagement_id,
            run_id,
            target_status,
            reason=reason,
        )


def start_run(client_root: Path, engagement_id: str, run_id: str) -> dict[str, Any]:
    """Mark one prepared or failed run as actively executing."""

    return _write_run_status(client_root, engagement_id, run_id, "running")


def fail_run(
    client_root: Path, engagement_id: str, run_id: str, reason: str
) -> dict[str, Any]:
    """Record one bounded failure reason without deleting the run."""

    return _write_run_status(
        client_root, engagement_id, run_id, "failed", reason=reason
    )


def cancel_run(client_root: Path, engagement_id: str, run_id: str) -> dict[str, Any]:
    """Explicitly cancel an abandoned non-terminal run."""

    return _write_run_status(client_root, engagement_id, run_id, "cancelled")


def _output_files(output_dir: Path) -> tuple[Path, ...]:
    files: list[Path] = []
    for path in sorted(output_dir.rglob("*"), key=lambda item: item.as_posix()):
        observed = path.lstat()
        if path.is_symlink():
            raise LedgerError("Workflow outputs cannot contain symbolic links.")
        if stat.S_ISDIR(observed.st_mode):
            continue
        if not stat.S_ISREG(observed.st_mode) or observed.st_nlink < 1:
            raise LedgerError("Workflow outputs contain a non-regular entry.")
        files.append(path)
    return tuple(files)


def finalize_run(
    client_root: Path,
    engagement_id: str,
    run_id: str,
    declarations: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    """Seal every physical output with an explicit purpose and audience."""

    root = _ordinary_directory(client_root, label="client folder")
    with _engagement_lock(root, engagement_id):
        return _finalize_run_locked(root, engagement_id, run_id, declarations)


def _finalize_run_locked(
    client_root: Path,
    engagement_id: str,
    run_id: str,
    declarations: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    engagement = load_engagement_manifest(client_root, engagement_id)
    if engagement["status"] != "open":
        raise LedgerError("Runs cannot be finalized after their engagement is closed.")
    loaded = load_run(client_root, engagement_id, run_id)
    if loaded["run"]["status"] not in {"running", "ready_for_review"}:
        raise LedgerError("Only a running or review-ready run can be finalized.")
    output_dir = Path(loaded["output_dir"])
    files = _output_files(output_dir)
    if not files:
        raise LedgerError("An empty workflow output cannot be finalized.")
    if isinstance(declarations, (str, bytes)) or len(declarations) > _MAX_ARTIFACTS:
        raise LedgerError("Artifact declarations are invalid or too numerous.")
    declared: dict[str, Mapping[str, Any]] = {}
    seen_ids: set[str] = set()
    for raw in declarations:
        if not isinstance(raw, Mapping):
            raise LedgerError("Artifact declaration must be an object.")
        missing = {
            "artifact_id",
            "path",
            "purpose",
            "audience",
            "media_type",
        } - set(raw)
        unexpected = set(raw) - {
            "artifact_id",
            "path",
            "purpose",
            "audience",
            "media_type",
        }
        if missing or unexpected:
            raise LedgerError(
                "Artifact declaration shape is invalid; "
                f"missing={sorted(missing)}, unexpected={sorted(unexpected)}."
            )
        path = _relative_path(raw.get("path"), label="artifact path")
        if path in declared:
            raise LedgerError("An output path was declared more than once.")
        artifact_id = _text(raw.get("artifact_id"), label="artifact_id", maximum=120)
        if _ARTIFACT_ID_RE.fullmatch(artifact_id) is None or artifact_id in seen_ids:
            raise LedgerError("Artifact IDs must be safe and unique.")
        declared[path] = raw
        seen_ids.add(artifact_id)
    physical = {path.relative_to(output_dir).as_posix(): path for path in files}
    if set(declared) != set(physical):
        missing = sorted(set(physical) - set(declared))
        unexpected = sorted(set(declared) - set(physical))
        raise LedgerError(
            "Artifact declarations do not close the output tree; "
            f"undeclared={missing}, missing={unexpected}."
        )
    artifacts: list[dict[str, Any]] = []
    for relative_path in sorted(physical):
        source = physical[relative_path]
        byte_count, sha256 = _stable_file_identity(
            source,
            label="workflow artifact",
        )
        raw = declared[relative_path]
        record = _validate_artifact_record(
            {
                "artifact_id": raw["artifact_id"],
                "path": relative_path,
                "purpose": raw["purpose"],
                "audience": raw["audience"],
                "media_type": raw["media_type"],
                "byte_count": byte_count,
                "sha256": sha256,
            }
        )
        artifacts.append(record)
    if _output_files(output_dir) != files:
        raise LedgerError("Workflow outputs changed while they were being sealed.")
    if loaded["run"]["status"] == "ready_for_review":
        existing = validate_run_artifacts(client_root, engagement_id, run_id)
        requested = [
            {
                "artifact_id": item["artifact_id"],
                "path": item["path"],
                "purpose": item["purpose"],
                "audience": item["audience"],
                "media_type": item["media_type"],
                "byte_count": item["byte_count"],
                "sha256": item["sha256"],
            }
            for item in artifacts
        ]
        if existing["artifacts"] != requested:
            raise LedgerError(
                "Review-ready artifacts are already sealed with different declarations."
            )
        return {**loaded, "artifact_manifest": existing}
    manifest = _sealed(
        {
            "schema_version": ARTIFACT_MANIFEST_SCHEMA,
            "client_id": loaded["run"]["client_id"],
            "engagement_id": engagement_id,
            "workflow_id": loaded["run"]["workflow_id"],
            "run_id": run_id,
            "generated_at": _now_iso(),
            "artifacts": artifacts,
        }
    )
    _write_json(Path(loaded["run_root"]) / "artifact_manifest.json", manifest)
    manifest = validate_run_artifacts(client_root, engagement_id, run_id)
    if loaded["run"]["status"] == "running":
        loaded = _write_run_status_locked(
            client_root, engagement_id, run_id, "ready_for_review"
        )
    return {**loaded, "artifact_manifest": manifest}


def validate_run_artifacts(
    client_root: Path, engagement_id: str, run_id: str
) -> dict[str, Any]:
    """Verify that a run's declared artifacts still close its exact output tree."""

    loaded = load_run(client_root, engagement_id, run_id)
    manifest_path = Path(loaded["run_root"]) / "artifact_manifest.json"
    manifest = _validate_seal(
        _read_json(manifest_path, label="artifact manifest"),
        label="artifact manifest",
    )
    required = {
        "schema_version",
        "client_id",
        "engagement_id",
        "workflow_id",
        "run_id",
        "generated_at",
        "artifacts",
        "content_sha256",
    }
    if (
        set(manifest) != required
        or manifest["schema_version"] != ARTIFACT_MANIFEST_SCHEMA
    ):
        raise LedgerError("Artifact manifest shape is invalid.")
    for key in ("client_id", "engagement_id", "workflow_id", "run_id"):
        if manifest[key] != loaded["run"][key]:
            raise LedgerError("Artifact manifest belongs to another run.")
    raw_artifacts = manifest["artifacts"]
    if not isinstance(raw_artifacts, list) or not raw_artifacts:
        raise LedgerError("Artifact manifest must declare at least one output.")
    artifacts = [_validate_artifact_record(item) for item in raw_artifacts]
    if len({item["artifact_id"] for item in artifacts}) != len(artifacts) or len(
        {item["path"] for item in artifacts}
    ) != len(artifacts):
        raise LedgerError("Artifact manifest entries must be unique.")
    output_dir = Path(loaded["output_dir"])
    physical = {
        path.relative_to(output_dir).as_posix(): path
        for path in _output_files(output_dir)
    }
    declared = {item["path"]: item for item in artifacts}
    if set(physical) != set(declared):
        raise LedgerError("Artifact manifest no longer closes the output tree.")
    for relative_path, path in physical.items():
        byte_count, sha256 = _stable_file_identity(
            path,
            label="workflow artifact",
        )
        record = declared[relative_path]
        if byte_count != record["byte_count"] or sha256 != record["sha256"]:
            raise LedgerError("Workflow artifact no longer matches its manifest.")
    return manifest


def complete_run(client_root: Path, engagement_id: str, run_id: str) -> dict[str, Any]:
    """Mark a valid review-ready run completed."""

    return _write_run_status(client_root, engagement_id, run_id, "completed")


def close_engagement(client_root: Path, engagement_id: str) -> dict[str, Any]:
    """Close an engagement only after active runs have been resolved."""

    root = _ordinary_directory(client_root, label="client folder")
    with _engagement_lock(root, engagement_id):
        engagement = load_engagement_manifest(root, engagement_id)
        if engagement["status"] == "closed":
            return engagement
        active = [
            item["run"]["run_id"]
            for item in _iter_runs(root, engagement_id)
            if item["run"]["status"] in {"prepared", "running", "ready_for_review"}
        ]
        if active:
            raise LedgerError(
                "Engagement has active runs; complete or cancel them before closing: "
                + ", ".join(active)
            )
        content = {
            key: engagement[key]
            for key in (
                "schema_version",
                "client_id",
                "engagement_id",
                "label",
                "created_at",
            )
        }
        content.update({"status": "closed", "closed_at": _now_iso()})
        closed = _sealed(content)
        _write_json(_engagement_root(root, engagement_id) / "engagement.json", closed)
        return closed


def retention_report(
    client_root: Path,
    *,
    as_of: datetime | None = None,
    older_than_days: int | None = None,
) -> dict[str, Any]:
    """Report retention candidates without deleting or changing any data."""

    root = _ordinary_directory(client_root, label="client folder")
    client = load_client_manifest(root)
    if older_than_days is not None and older_than_days < 0:
        raise LedgerError("older_than_days cannot be negative.")
    now = as_of or datetime.now(timezone.utc)
    rows: list[dict[str, Any]] = []
    for engagement in list_engagements(root, client["client_id"]):
        for loaded in _iter_runs(root, engagement["engagement_id"]):
            run = loaded["run"]
            try:
                updated = datetime.fromisoformat(run["updated_at"])
            except ValueError as exc:
                raise LedgerError("Run updated_at is not ISO formatted.") from exc
            if updated.tzinfo is None:
                updated = updated.replace(tzinfo=timezone.utc)
            age_days = max(0, (now - updated).days)
            size_bytes = sum(
                path.lstat().st_size
                for path in Path(loaded["run_root"]).rglob("*")
                if path.is_file() and not path.is_symlink()
            )
            candidate = (
                older_than_days is not None
                and age_days >= older_than_days
                and run["status"] in {"completed", "failed", "cancelled"}
            )
            artifact_integrity = "not_applicable"
            artifact_issue: str | None = None
            if run["status"] in {"ready_for_review", "completed"}:
                try:
                    validate_run_artifacts(
                        root,
                        engagement["engagement_id"],
                        run["run_id"],
                    )
                    artifact_integrity = "valid"
                except LedgerError as exc:
                    artifact_integrity = "invalid"
                    artifact_issue = str(exc)
            rows.append(
                {
                    "engagement_id": engagement["engagement_id"],
                    "run_id": run["run_id"],
                    "workflow_id": run["workflow_id"],
                    "status": run["status"],
                    "updated_at": run["updated_at"],
                    "age_days": age_days,
                    "size_bytes": size_bytes,
                    "retention_candidate": candidate,
                    "artifact_integrity": artifact_integrity,
                    "artifact_issue": artifact_issue,
                }
            )
    return {
        "schema_version": "vera.retention_report.v1",
        "client_id": client["client_id"],
        "generated_at": now.isoformat(),
        "older_than_days": older_than_days,
        "destructive_action_performed": False,
        "runs": rows,
    }
