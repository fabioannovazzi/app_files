"""Verify installed package bytes and materialize hardlinks outside host caches.

The host-installed package remains the trust anchor; its embedded digest index
detects drift, not publisher authenticity. No case files or network are used.
"""

from __future__ import annotations

import argparse
import atexit
import hashlib
import json
import logging
import os
import re
import runpy
import shutil
import sqlite3
import stat
import subprocess
import sys
import tempfile
from contextlib import contextmanager
from pathlib import Path, PurePosixPath, PureWindowsPath
from typing import Iterator

product_name = runpy.run_path(str(Path(__file__).with_name("reporting_product.py")))[
    "product_name"
]

__all__ = [
    "ASSURED_MODULES",
    "InstallationContentMismatch",
    "MANIFEST",
    "prepare_execution_root",
    "execution_package_id",
    "bind_execution_run",
    "execution_store_lock",
    "collect_execution_store",
    "release_execution_root",
    "own_execution_root",
    "execution_lease_fds",
    "acquire_execution_lease",
    "recover_abandoned_execution_roots",
    "report_preparation_failure",
    "main",
]

ASSURED_MODULES = frozenset(
    {
        "journal-bank-reconciliation",
        "open-item-reconciliation",
        "journal-sampling",
        "report-builder",
        "check-entries",
        "concordato-plan-review",
    }
)
MANIFEST = "execution-files.json"
LOGGER = logging.getLogger(__name__)
# Only copies created by this process may be removed. Never infer ownership
# from a directory name or delete a caller's installation/input/output tree.
_OWNED_COPIES: dict[Path, tuple[int, int, int]] = {}


# POSIX kernel leases survive owner termination while detached workers retain
# the descriptor. Exclusive acquisition is mechanical proof that no holder uses
# this code; directory names, age and PID liveness alone are not such proof.
_LEASES: dict[Path, int] = {}
_SHARED_ROOTS: dict[Path, tuple[int, int]] = {}


def _lease_directory() -> Path:
    directory = Path(tempfile.gettempdir()).resolve() / ".vera-execution-leases"
    directory.mkdir(mode=0o700, exist_ok=True)
    info = directory.lstat()
    if not stat.S_ISDIR(info.st_mode) or info.st_uid != os.getuid():
        raise ValueError("Execution lease directory is not privately owned")
    if stat.S_IMODE(info.st_mode) != 0o700:
        raise ValueError("Execution lease directory is not private")
    return directory


def own_execution_root(root: Path) -> None:
    """Record a newly created code root and hold its kernel lifetime lease."""
    info = root.lstat()
    _OWNED_COPIES[root] = (os.getpid(), info.st_dev, info.st_ino)
    if os.name != "posix":
        return
    import fcntl

    if root.parent != Path(tempfile.gettempdir()).resolve():
        raise ValueError("Execution copy must belong to this OS temporary folder")
    lease = _lease_directory() / (root.name + ".json")
    descriptor = os.open(lease, os.O_CREAT | os.O_EXCL | os.O_RDWR, 0o600)
    try:
        fcntl.flock(descriptor, fcntl.LOCK_SH)
        os.write(
            descriptor,
            json.dumps(
                {"schema_version": 2, "device": info.st_dev, "inode": info.st_ino}
            ).encode(),
        )
        _LEASES[root] = descriptor
    except BaseException:
        os.close(descriptor)
        lease.unlink(missing_ok=True)
        raise


def execution_lease_fds(root: Path) -> tuple[int, ...]:
    """Keep the code lease in a detached worker until its helper finishes."""
    shared = _SHARED_ROOTS.get(root)
    descriptor = shared[0] if shared else _LEASES.get(root)
    return () if descriptor is None else (descriptor,)


def acquire_execution_lease(root: Path) -> int | None:
    """Borrow a registered snapshot lease for a CLI child before launching it."""
    if os.name == "posix" and root.parent.name == "code":
        if root.parent != _code_store() or not re.fullmatch("[0-9a-f]{64}", root.name):
            return None
        with execution_store_lock():
            descriptor = _lock_descriptor(
                root.parent / f"{root.name}.lock", exclusive=False
            )
            try:
                record = json.loads(_read_regular(root.parent / f"{root.name}.json")[0])
                info = root.lstat()
                if not stat.S_ISDIR(info.st_mode) or record["identity"] != [
                    info.st_dev,
                    info.st_ino,
                ]:
                    raise ValueError(
                        "CLI code lease no longer matches its execution root"
                    )
                return descriptor
            except BaseException:
                os.close(descriptor)
                raise
    if os.name != "posix" or root.parent != Path(tempfile.gettempdir()).resolve():
        return None
    if not re.fullmatch(
        r"vera-(?:verified|execution-bootstrap)-[A-Za-z0-9_-]+", root.name
    ):
        return None
    import fcntl

    lease = _lease_directory() / (root.name + ".json")
    try:
        descriptor = os.open(lease, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    except FileNotFoundError:
        return None  # Unmarked/borrowed code is never swept automatically.
    try:
        fcntl.flock(descriptor, fcntl.LOCK_SH)
        info = os.fstat(descriptor)
        data = json.loads(os.read(descriptor, 4096))
        current = root.lstat()
        if (
            not stat.S_ISREG(info.st_mode)
            or info.st_uid != os.getuid()
            or info.st_nlink != 1
            or not stat.S_ISDIR(current.st_mode)
            or current.st_uid != os.getuid()
            or not isinstance(data, dict)
            or data.get("schema_version") not in (1, 2)
            or (current.st_dev, current.st_ino)
            != (data.get("device"), data.get("inode"))
        ):
            raise ValueError("CLI code lease no longer matches its execution root")
        return descriptor
    except BaseException:
        os.close(descriptor)
        raise


def recover_abandoned_execution_roots() -> None:
    """Recover only identity-bound code with an exclusively acquired OS lease.

    Windows retains normal cleanup; orphan recovery is enabled only where the
    OS supplies inheritable POSIX flock leases. Unmarked historical copies and
    any malformed/replaced/locked entry are always retained.
    """
    if os.name != "posix":
        return
    import fcntl

    directory = _lease_directory()
    for lease in directory.glob("*.json"):
        descriptor = None
        try:
            name = lease.name.removesuffix(".json")
            if not re.fullmatch(
                r"vera-(?:verified|execution-bootstrap)-[A-Za-z0-9_-]+", name
            ):
                continue
            descriptor = os.open(lease, os.O_RDWR | os.O_NOFOLLOW | os.O_NONBLOCK)
            info = os.fstat(descriptor)
            if (
                not stat.S_ISREG(info.st_mode)
                or info.st_uid != os.getuid()
                or info.st_nlink != 1
            ):
                continue
            fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
            data = json.loads(os.read(descriptor, 4096))
            if set(data) != {"schema_version", "device", "inode"}:
                continue
            # Protocol 1 did not guarantee CLI-child inheritance. Retain it
            # even with no holder: a legacy helper may still be running.
            if data["schema_version"] != 2:
                continue
            root = directory.parent / name
            try:
                current = root.lstat()
            except FileNotFoundError:
                lease.unlink(missing_ok=True)
                continue
            if (
                not stat.S_ISDIR(current.st_mode)
                or current.st_uid != os.getuid()
                or (current.st_dev, current.st_ino) != (data["device"], data["inode"])
            ):
                continue
            shutil.rmtree(root)
            lease.unlink(missing_ok=True)
        except BlockingIOError:
            pass  # A live service or worker still owns the code.
        except (OSError, ValueError, TypeError):
            LOGGER.warning(
                "Execution orphan recovery pending: %s", lease, exc_info=True
            )
        finally:
            if descriptor is not None:
                os.close(descriptor)


def release_execution_root(root: Path) -> None:
    """Remove owned code only after all inherited kernel leases have closed."""
    shared = _SHARED_ROOTS.get(root)
    if shared is not None:
        shared_descriptor, references = shared
        if references > 1:
            _SHARED_ROOTS[root] = (shared_descriptor, references - 1)
        else:
            del _SHARED_ROOTS[root]
            os.close(shared_descriptor)
            collect_execution_store()
        return
    identity = _OWNED_COPIES.get(root)
    if identity is None or identity[0] != os.getpid():
        return
    descriptor = _LEASES.pop(root, None)
    if descriptor is not None:
        os.close(descriptor)
    exclusive = None
    lease = None
    try:
        if os.name == "posix":
            import fcntl

            lease = _lease_directory() / (root.name + ".json")
            if lease.exists():
                exclusive = os.open(lease, os.O_RDWR | os.O_NOFOLLOW)
                # A new open-file description conflicts with an inherited
                # worker lease; upgrading the parent's shared descriptor would
                # incorrectly upgrade the worker's very same flock lock.
                fcntl.flock(exclusive, fcntl.LOCK_EX | fcntl.LOCK_NB)
        info = root.lstat()
        if not stat.S_ISDIR(info.st_mode) or (info.st_dev, info.st_ino) != identity[1:]:
            LOGGER.warning(
                "Temporary execution root changed; cleanup skipped: %s", root
            )
            return
        shutil.rmtree(root)
        _OWNED_COPIES.pop(root, None)
        if lease is not None:
            lease.unlink(missing_ok=True)
    except BlockingIOError:
        return  # A persistent worker owns the code; a future sweep will retry.
    except FileNotFoundError:
        _OWNED_COPIES.pop(root, None)
        if lease is not None:
            lease.unlink(missing_ok=True)
    except OSError:
        LOGGER.warning("Temporary execution cleanup pending: %s", root, exc_info=True)
    finally:
        if exclusive is not None:
            os.close(exclusive)


def _release_owned_copies() -> None:
    for root in tuple(_SHARED_ROOTS):
        descriptor, _ = _SHARED_ROOTS.pop(root)
        os.close(descriptor)
    for root in tuple(_OWNED_COPIES):
        release_execution_root(root)


atexit.register(_release_owned_copies)


def _identity(info: os.stat_result) -> tuple[int, ...]:
    return (
        info.st_dev,
        info.st_ino,
        info.st_mode,
        info.st_size,
        info.st_mtime_ns,
        # CPython 3.12 Windows lstat uses creation time for ctime, while
        # fstat uses change time. Birthtime is comparable across both APIs.
        (
            getattr(info, "st_birthtime_ns", info.st_ctime_ns)
            if os.name == "nt"
            else info.st_ctime_ns
        ),
        info.st_nlink,
    )


def _read_regular(path: Path) -> tuple[bytes, int]:
    """Read a stable regular file, permitting hardlinks only as copy sources."""

    _real_ancestors(path.parent)
    before = path.lstat()
    if (
        not stat.S_ISREG(before.st_mode)
        or _reparse_point(before)
        or before.st_nlink < 1
    ):
        raise ValueError(f"Non-regular installation file: {path}")
    descriptor = os.open(path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
    with os.fdopen(descriptor, "rb") as handle:
        opened = os.fstat(handle.fileno())
        if _identity(before) != _identity(opened):
            raise ValueError(f"Installation file changed before read: {path}")
        data = handle.read()
        after = os.fstat(handle.fileno())
        if (
            _identity(before) != _identity(after)
            or opened.st_ctime_ns != after.st_ctime_ns
            or _identity(before) != _identity(path.lstat())
        ):
            raise ValueError(f"Installation file changed during read: {path}")
    _real_ancestors(path.parent)
    return data, before.st_nlink


def _reparse_point(info: os.stat_result) -> bool:
    return bool(
        getattr(info, "st_file_attributes", 0)
        & getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0)
    )


def _real_ancestors(root: Path) -> None:
    for path in (root, *root.parents):
        info = path.lstat()
        if not stat.S_ISDIR(info.st_mode) or _reparse_point(info):
            raise ValueError(f"Installation ancestor must be a real directory: {path}")


def _validate_host_use_markers(directory: Path) -> None:
    """Accept only numeric regular host leases; none become executable inputs.

    Exact filesystem rules distinguish the reported host bookkeeping from code
    without allowing an arbitrary ignored subtree in the integrity boundary.
    """

    for marker in directory.iterdir():
        info = marker.lstat()
        if (
            not marker.name.isascii()
            or not marker.name.isdecimal()
            or not stat.S_ISREG(info.st_mode)
            or _reparse_point(info)
            or info.st_nlink != 1
        ):
            raise ValueError(f"Invalid host use marker: {marker}")


def _inventory(root: Path) -> tuple[dict[str, Path], set[str]]:
    """Reject unexpected filesystem types before reading any installed code."""

    files: dict[str, Path] = {}
    directories: set[str] = set()
    pending = [root]
    while pending:
        directory = pending.pop()
        for path in directory.iterdir():
            info = path.lstat()
            relative = path.relative_to(root).as_posix()
            if _reparse_point(info):
                raise ValueError(f"Reparse installation entry: {path}")
            if stat.S_ISDIR(info.st_mode):
                if relative == ".in_use":
                    _validate_host_use_markers(path)
                    continue
                if path.name != "__pycache__":
                    directories.add(relative)
                    pending.append(path)
            elif stat.S_ISREG(info.st_mode):
                if path.suffix in {".pyc", ".pyo"}:
                    if info.st_nlink != 1:
                        raise ValueError(
                            f"Hardlinked bytecode is not repairable: {path}"
                        )
                    continue
                files[relative] = path
            else:
                raise ValueError(f"Non-regular installation entry: {path}")
    return files, directories


def _manifest(data: bytes) -> dict[str, str]:
    payload = json.loads(data)
    if (
        not isinstance(payload, dict)
        or payload.get("schema_version") != 1
        or not isinstance(payload.get("files"), dict)
    ):
        raise ValueError("Invalid execution digest index")
    files = payload["files"]
    for name, digest in files.items():
        path = PurePosixPath(name)
        if (
            not name
            or path.is_absolute()
            or ".." in path.parts
            or "\\" in name
            or PureWindowsPath(name).drive
            or path.as_posix() != name
            or name == MANIFEST
            or not isinstance(digest, str)
            or len(digest) != 64
            or any(character not in "0123456789abcdef" for character in digest)
        ):
            raise ValueError("Invalid execution digest index entry")
    return files


def _validate_module(root: Path, module: str | None) -> None:
    """Run the unchanged module boundary only after package-byte verification."""

    if module is None:
        return
    component = root / "modules" / module
    bootstrap = component / "scripts" / "implementation_bootstrap.py"
    if module not in ASSURED_MODULES and not bootstrap.is_file():
        return
    code = (
        "import runpy, sys; "
        "namespace = runpy.run_path(sys.argv[1]); "
        "namespace['validate_implementation_tree'](sys.argv[2])"
    )
    result = subprocess.run(
        [sys.executable, "-I", "-B", "-c", code, str(bootstrap), str(component)],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode:
        raise ValueError(f"Module integrity check failed: {result.stderr.strip()}")


def prepare_execution_root(
    root: Path, module: str | None, *, snapshot: bool = False, shared: bool = False
) -> Path:
    """Return verified code; recover only authentic-to-index hardlinked bytes.

    Fixed digests and exact file inventory are mechanical execution controls.
    Recovery never weakens a module's own single-link validation.
    """

    snapshot = snapshot or shared
    product = product_name(root)
    if product == "vera" and module not in ASSURED_MODULES and not snapshot:
        return root
    root = root.absolute()
    # Repository component sources use sibling roots, not installed modules.
    if (
        not (root / "modules").exists()
        and root.parent.name == "plugins"
        and (root.parent.parent / ".git").exists()
        and (module is None or (root.parent / module).is_dir())
    ):
        return root
    _real_ancestors(root)
    observed, directories = _inventory(root)
    if MANIFEST not in observed:
        raise ValueError("Installed product has no execution digest index; update it.")
    manifest_bytes, manifest_links = _read_regular(observed.pop(MANIFEST))
    expected = _manifest(manifest_bytes)
    expected_directories = {
        parent.as_posix()
        for name in expected
        for parent in PurePosixPath(name).parents
        if parent != PurePosixPath(".")
    }
    if directories != expected_directories:
        raise ValueError("Installation directories do not match the digest index")
    if observed.keys() != expected.keys():
        missing = sorted(expected.keys() - observed.keys())
        extra = sorted(observed.keys() - expected.keys())
        raise ValueError(
            f"Installation inventory mismatch; missing={missing}, extra={extra}"
        )
    contents = {}
    hardlinks = manifest_links > 1
    for name, digest in expected.items():
        data, links = _read_regular(observed[name])
        if hashlib.sha256(data).hexdigest() != digest:
            raise InstallationContentMismatch(
                name, digest, hashlib.sha256(data).hexdigest()
            )
        contents[name] = data
        hardlinks = hardlinks or links > 1
    if _read_regular(root / MANIFEST)[0] != manifest_bytes:
        raise ValueError("Execution digest index changed during verification")
    if shared:
        recover_abandoned_execution_roots()
        return _shared_execution_root(contents, manifest_bytes, module)
    if not hardlinks and not snapshot:
        _validate_module(root, module)
        return root

    recover_abandoned_execution_roots()

    # mkdtemp creates a fresh private directory. Never mutate the installed tree
    # or an alias, never reuse an unverified cache, never copy client material.
    private = Path(
        tempfile.mkdtemp(
            prefix="vera-verified-", dir=Path(tempfile.gettempdir()).resolve()
        )
    )
    try:
        own_execution_root(private)
        for name, data in {**contents, MANIFEST: manifest_bytes}.items():
            path = private / name
            path.parent.mkdir(parents=True, exist_ok=True)
            with path.open("xb") as handle:
                handle.write(data)
            installed, links = _read_regular(path)
            if installed != data or links != 1:
                raise ValueError(f"Private execution copy failed verification: {name}")
        _validate_module(private, module)
    except BaseException:
        # Cancellation must not leak a partially materialized package either.
        release_execution_root(private)
        raise
    LOGGER.log(
        logging.INFO if snapshot else logging.WARNING,
        "Vera ha preparato una copia privata verificata del codice.",
    )
    return private


def _code_store() -> Path:
    """Keep verified code separate from host caches and professional state."""
    if os.environ.get("MPARANZA_RUNTIME_ROOT"):
        base = Path(os.environ["MPARANZA_RUNTIME_ROOT"]).expanduser()
    elif os.name == "nt":
        base = (
            Path(os.environ.get("LOCALAPPDATA", str(Path.home() / "AppData/Local")))
            / "mpr"
        )
    else:
        base = Path.home() / ".local/share/mparanza/runtime"
    directory = (base / "code").absolute()
    directory.mkdir(mode=0o700, parents=True, exist_ok=True)
    _real_ancestors(directory)
    info = directory.stat()
    if os.name == "posix" and (
        info.st_uid != os.getuid() or stat.S_IMODE(info.st_mode) != 0o700
    ):
        raise ValueError("Execution code store is not privately owned")
    return directory


def _lock_descriptor(path: Path, *, exclusive: bool, wait: bool = True) -> int:
    """Acquire a kernel lease; close releases it, including after a crash."""
    descriptor = os.open(
        path, os.O_CREAT | os.O_RDWR | getattr(os, "O_NOFOLLOW", 0), 0o600
    )
    try:
        info = os.fstat(descriptor)
        if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1:
            raise ValueError("Invalid execution lock")
        if os.name == "nt":
            import ctypes
            import msvcrt
            from ctypes import wintypes

            class Overlapped(ctypes.Structure):
                _fields_ = [
                    ("Internal", ctypes.c_size_t),
                    ("InternalHigh", ctypes.c_size_t),
                    ("Offset", wintypes.DWORD),
                    ("OffsetHigh", wintypes.DWORD),
                    ("hEvent", wintypes.HANDLE),
                ]

            kernel = getattr(ctypes, "WinDLL")("kernel32", use_last_error=True)
            lock = kernel.LockFileEx
            lock.argtypes = [
                wintypes.HANDLE,
                wintypes.DWORD,
                wintypes.DWORD,
                wintypes.DWORD,
                wintypes.DWORD,
                ctypes.POINTER(Overlapped),
            ]
            lock.restype = wintypes.BOOL
            overlapped = Overlapped()
            if not lock(
                getattr(msvcrt, "get_osfhandle")(descriptor),
                (2 if exclusive else 0) | (0 if wait else 1),
                0,
                1,
                0,
                ctypes.byref(overlapped),
            ):
                error = getattr(ctypes, "get_last_error")()
                if error == 33:
                    raise BlockingIOError("Execution code is in use")
                raise getattr(ctypes, "WinError")(error)
        else:
            import fcntl

            fcntl.flock(
                descriptor,
                (fcntl.LOCK_EX if exclusive else fcntl.LOCK_SH)
                | (0 if wait else fcntl.LOCK_NB),
            )
        return descriptor
    except BaseException:
        os.close(descriptor)
        raise


@contextmanager
def execution_store_lock(name: str = "catalog") -> Iterator[None]:
    """Serialize materialization/collection or a managed install transaction."""
    if name not in {"catalog", "install"}:
        raise ValueError("Unknown execution-store lock")
    descriptor = _lock_descriptor(_code_store() / f"{name}.lock", exclusive=True)
    try:
        yield
    finally:
        os.close(descriptor)


def execution_package_id(root: Path) -> str | None:
    """Identify the complete indexed package, independently of its version label."""
    path = root / MANIFEST
    return hashlib.sha256(_read_regular(path)[0]).hexdigest() if path.exists() else None


def _remove_code(root: Path) -> None:
    """Remove an exclusively owned immutable code tree, including on Windows."""
    for directory, _, files in os.walk(root):
        Path(directory).chmod(0o700)
        for name in files:
            target = Path(directory) / name
            if not target.is_symlink():
                target.chmod(0o600)
    shutil.rmtree(root)


def _collect_execution_store(directory: Path, keep_idle: int) -> None:
    idle = []
    # The catalog lock excludes every creator/collector. A terminated creator's
    # staging directory cannot be read by a service and is safe to reclaim.
    for stage in directory.glob(".staging-*"):
        if stage.is_dir() and not stage.is_symlink():
            _remove_code(stage)
    # A crash between atomic publication and writing the ownership receipt
    # leaves complete code without a lease. Adopt only a complete indexed tree.
    for root in directory.iterdir():
        record = directory / f"{root.name}.json"
        if (
            re.fullmatch("[0-9a-f]{64}", root.name)
            and not record.exists()
            and not root.is_symlink()
        ):
            try:
                manifest = _read_regular(root / MANIFEST)[0]
                expected = _manifest(manifest)
                files, _ = _inventory(root)
                if hashlib.sha256(
                    manifest
                ).hexdigest() != root.name or files.keys() != {*expected, MANIFEST}:
                    continue
                if any(
                    _read_regular(files[name]) != (data, 1)
                    for name, data in {MANIFEST: manifest}.items()
                ):
                    continue
                if any(
                    hashlib.sha256(_read_regular(files[name])[0]).hexdigest() != digest
                    for name, digest in expected.items()
                ):
                    continue
                info = root.stat()
                record.write_text(json.dumps({"identity": [info.st_dev, info.st_ino]}))
            except (OSError, ValueError):
                LOGGER.warning("Unrecognized execution store entry retained: %s", root)
    for record in directory.glob("*.json"):
        digest = record.stem
        if not re.fullmatch("[0-9a-f]{64}", digest):
            continue
        descriptor = None
        try:
            descriptor = _lock_descriptor(
                directory / f"{digest}.lock", exclusive=True, wait=False
            )
            identity = json.loads(_read_regular(record)[0])
            root = directory / digest
            if not root.exists():
                record.unlink()
                os.close(descriptor)
                descriptor = None
                (directory / f"{digest}.lock").unlink()
                continue
            info = root.lstat()
            if (
                not stat.S_ISDIR(info.st_mode)
                or [info.st_dev, info.st_ino] != identity["identity"]
            ):
                continue
            idle.append((record.stat().st_mtime_ns, root, record, descriptor))
            descriptor = None
        except BlockingIOError:
            pass
        except (OSError, ValueError, KeyError, TypeError):
            LOGGER.warning(
                "Execution code collection pending: %s", record, exc_info=True
            )
        finally:
            if descriptor is not None:
                os.close(descriptor)
    retired = []
    try:
        for _, root, record, _ in sorted(idle, reverse=True)[keep_idle:]:
            _remove_code(root)
            record.unlink()
            retired.append(root.name)
    finally:
        for _, _, _, descriptor in idle:
            os.close(descriptor)
        # No waiter can hold this pathname: all acquisitions hold catalog.
        for name in retired:
            (directory / f"{name}.lock").unlink()


def collect_execution_store(*, keep_idle: int = 2) -> None:
    """Keep two idle releases plus live leases; never collect active services."""
    if keep_idle < 0:
        raise ValueError("Idle release count cannot be negative")
    with execution_store_lock():
        _collect_execution_store(_code_store(), keep_idle)


def _shared_execution_root(
    contents: dict[str, bytes], manifest: bytes, module: str | None
) -> Path:
    """Atomically share verified single-link bytes, while pinning their lifetime."""
    digest = hashlib.sha256(manifest).hexdigest()
    expected = {**contents, MANIFEST: manifest}
    directory = _code_store()
    root = directory / digest
    with execution_store_lock():
        _collect_execution_store(directory, 2)
        if not root.exists():
            stage = Path(tempfile.mkdtemp(prefix=".staging-", dir=directory))
            try:
                for name, data in expected.items():
                    path = stage / name
                    path.parent.mkdir(parents=True, exist_ok=True)
                    with path.open("xb") as handle:
                        handle.write(data)
                    path.chmod(0o400)
                for folder, _, _ in os.walk(stage, topdown=False):
                    Path(folder).chmod(0o500)
                stage.rename(root)
            except BaseException:
                if stage.exists():
                    _remove_code(stage)
                raise
        info = root.stat()
        record = directory / f"{digest}.json"
        identity = json.dumps({"identity": [info.st_dev, info.st_ino]})
        if record.exists():
            _read_regular(record)
        if root in _SHARED_ROOTS:
            descriptor, references = _SHARED_ROOTS[root]
            _SHARED_ROOTS[root] = (descriptor, references + 1)
        else:
            descriptor = _lock_descriptor(directory / f"{digest}.lock", exclusive=False)
            _SHARED_ROOTS[root] = (descriptor, 1)
    # The reader lease prevents collection. Verify bytes outside the catalog
    # lock so independent service starts do not queue behind one full-package
    # read or a component validator. Integrity checks still precede execution.
    try:
        # Reuse never trusts a directory name or a previous successful check.
        files, directories = _inventory(root)
        expected_directories = {
            parent.as_posix()
            for name in expected
            for parent in PurePosixPath(name).parents
            if parent != PurePosixPath(".")
        }
        if files.keys() != expected.keys() or directories != expected_directories:
            raise ValueError("Shared execution inventory changed")
        for name, data in expected.items():
            actual, links = _read_regular(files[name])
            if actual != data or links != 1:
                raise ValueError(f"Shared execution code changed: {name}")
        _validate_module(root, module)
        with execution_store_lock():
            _real_ancestors(root)
            if (root.stat().st_dev, root.stat().st_ino) != (info.st_dev, info.st_ino):
                raise ValueError(
                    "Shared execution directory changed during verification"
                )
            # Device numbers can change after a filesystem remount. Persistent
            # identity is a collection receipt, not authority to execute code:
            # renew it only after verifying every byte and the live identity.
            descriptor, name = tempfile.mkstemp(prefix=".identity-", dir=directory)
            receipt = Path(name)
            try:
                with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
                    handle.write(identity)
                receipt.replace(record)
            finally:
                receipt.unlink(missing_ok=True)
        return root
    except BaseException:
        release_execution_root(root)
        raise


def bind_execution_run(run_root: Path, current_root: Path) -> Path:
    """Keep an active Archive run on its first complete package across reconnects.

    The binding is professional state, outside immutable code. Missing retired
    code is explicit; never silently recalculate an old run with a new release.
    The caller must release the returned lease when its operation/service ends.
    """
    digest = execution_package_id(current_root)
    if digest is None:
        return current_root  # Editable repository development has no package index.
    record = run_root / "execution-runtime.json"
    temporary_lease = None
    with execution_store_lock():
        if record.exists():
            binding = json.loads(_read_regular(record)[0])
            selected = binding["package_sha256"]
            if not isinstance(selected, str) or not re.fullmatch(
                "[0-9a-f]{64}", selected
            ):
                raise ValueError("Invalid run execution package binding")
        else:
            selected = digest
            # Catalog serialization and exclusive creation protect simultaneous
            # first calculation/review requests for the same run.
            with record.open("x", encoding="utf-8") as handle:
                json.dump({"schema_version": 1, "package_sha256": digest}, handle)
        root = current_root if selected == digest else _code_store() / selected
        if not root.is_dir():
            raise ValueError(
                "This run's original code is no longer retained; restore its verified package before resuming"
            )
        if root.parent == _code_store():
            temporary_lease = _lock_descriptor(
                root.parent / f"{selected}.lock", exclusive=False
            )
    try:
        if execution_package_id(root) != selected:
            raise ValueError("Run execution package changed")
        return prepare_execution_root(root, None, shared=True)
    finally:
        if temporary_lease is not None:
            os.close(temporary_lease)


class InstallationContentMismatch(ValueError):
    """Carry exact build-relative evidence, never client content or file excerpts."""

    def __init__(self, name: str, expected: str, observed: str) -> None:
        self.name = name
        self.expected = expected
        self.observed = observed
        super().__init__(f"Installation content mismatch: {name}")


def report_preparation_failure(
    root: Path,
    module: str | None,
    error: Exception,
    *,
    stage: str = "installation-preparation",
    technical_code: str | None = None,
    technical_type: str | None = None,
) -> None:
    """Report through independently index-verified code while keeping work blocked.

    Exact byte checks are mechanical trust controls, not a semantic classifier.
    The reporter uses only stdlib; snapshot it and product metadata before loading
    so altered workflow code and host-cache aliases never execute for telemetry.
    """
    try:
        manifest, _ = _read_regular(root / MANIFEST)
        expected = _manifest(manifest)
        metadata = next(
            name
            for name in (".codex-plugin/plugin.json", ".claude-plugin/plugin.json")
            if name in expected
        )
        contents = {}
        for name in (
            "scripts/verified_execution.py",
            "scripts/operational_incidents.py",
            "scripts/reporting_product.py",
            metadata,
        ):
            data, _ = _read_regular(root / name)
            if hashlib.sha256(data).hexdigest() != expected[name]:
                raise ValueError(
                    "Incident reporting component failed byte verification"
                )
            contents[name] = data
        # Detect an index replacement during the independent verification too.
        if _read_regular(root / MANIFEST)[0] != manifest:
            raise ValueError("Incident reporting index changed during verification")
        detail = "Installed product failed its installation preparation check."
        complete = technical_code is not None
        if technical_code is not None:
            detail = f"Product could not start the published helper: {technical_type or type(error).__name__}."
        if isinstance(error, InstallationContentMismatch):
            technical_code = "installation.content-mismatch"
            complete = True
            detail = (
                f"Installation content mismatch: {error.name}; "
                f"expected SHA-256={error.expected}; observed SHA-256={error.observed}."
            )
        with tempfile.TemporaryDirectory(prefix="vera-incident-verified-") as directory:
            snapshot = Path(directory)
            for name, data in contents.items():
                target = snapshot / name
                target.parent.mkdir(parents=True, exist_ok=True)
                with target.open("xb") as handle:
                    handle.write(data)
            # -I excludes the original script directory, cwd and PYTHONPATH:
            # an unindexed module cannot shadow a stdlib reporter dependency.
            program = (
                "import json, runpy, sys; "
                "from pathlib import Path; "
                "sys.path.insert(0, str(Path(sys.argv[1]).parent)); "
                "reporter = runpy.run_path(sys.argv[1]); "
                "receipt = reporter['report_failure'](**json.load(sys.stdin)); "
                "receipt['outbox_path'] = reporter['local_context']()['outbox_path'] "
                "if receipt['reporting'] in ('queued', 'delivered') else None; "
                "sys.stdout.write(json.dumps(receipt))"
            )
            result = subprocess.run(
                [
                    sys.executable,
                    "-I",
                    "-B",
                    "-c",
                    program,
                    str(snapshot / "scripts/operational_incidents.py"),
                ],
                input=json.dumps(
                    {
                        "workflow": module or "unknown",
                        "stage": stage,
                        "message": detail,
                        "error_type": type(error).__name__,
                        "exit_code": 1,
                        "errno": getattr(error, "errno", None),
                        "capture_state": "complete" if complete else "unavailable",
                        "technical_diagnostics": [
                            {
                                "component": product_name(root) + "-runtime",
                                "stage": stage,
                                "error_type": technical_type or type(error).__name__,
                                "error_code": technical_code
                                or "reporting.preflight-evidence-missing",
                                "message": detail,
                                "exit_code": 1,
                                "errno": getattr(error, "errno", None),
                                "evidence_source": "runtime-exception",
                            }
                        ],
                    }
                ),
                text=True,
                capture_output=True,
                check=False,
                timeout=45,
            )
            if result.returncode:
                raise ValueError("Verified incident reporting process failed")
            receipt = json.loads(result.stdout)
        LOGGER.error("VERA_INSTALLATION_INCIDENT: %s", json.dumps(receipt))
        if receipt["reporting"] == "delivered":
            return
        # The queued original envelope keeps its stable UUID for remote retries.
    except (
        OSError,
        ValueError,
        KeyError,
        StopIteration,
        sqlite3.Error,
        subprocess.SubprocessError,
    ) as reporting_error:
        LOGGER.error(
            "Incident reporting verification unavailable: %s",
            type(reporting_error).__name__,
        )
    if os.environ.get("MPARANZA_INCIDENT_DELIVERY") == "local-only":
        LOGGER.error(
            "VERA_LOCAL_INCIDENT: workflow=%s stage=installation-preparation error_type=%s. "
            "Retain local evidence; incident transmission is disabled for this execution.",
            module or "unknown",
            type(error).__name__,
        )
        return
    LOGGER.error(
        "VERA_BROWSER_INCIDENT_REQUIRED: workflow=%s stage=installation-preparation error_type=%s. "
        "Use the host browser recovery page documented in incident-recovery.md automatically. Deliver the exact queued "
        "original envelope when available; otherwise report the observed technical failure "
        "without running unverified plugin code. Verify recorded:true before claiming delivery. "
        "Do not ask the professional to report it or consent again.",
        module or "unknown",
        type(error).__name__,
    )


def main(argv: list[str] | None = None) -> int:
    """Prepare the workflow internally; the professional does not run a terminal."""

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--module")
    args = parser.parse_args(argv)
    root = Path(__file__).absolute().parents[1]
    try:
        prepared = prepare_execution_root(root, args.module)
    except (OSError, ValueError) as error:
        LOGGER.error("Preparazione di Vera bloccata: %s", error)
        report_preparation_failure(root, args.module, error)
        return 1
    # Preflight is a check, not a lease spanning unrelated shell processes.
    # Subsequent managed commands prepare their own scoped execution copy.
    release_execution_root(prepared)
    sys.stdout.write(json.dumps({"execution_root": str(root)}) + "\n")
    return 0


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    raise SystemExit(main())
