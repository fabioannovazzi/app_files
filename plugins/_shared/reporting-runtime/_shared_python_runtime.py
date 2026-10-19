"""One mutable, leased Python environment for all Mparanza products."""

from __future__ import annotations

import errno
import hashlib
import json
import logging
import os
import re
import subprocess
import sys
import time
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator

__all__ = ["enabled", "target", "ready", "ensure"]
RECEIPT = ".mparanza-shared-ready.json"
POLICY = ".mparanza-shared-features.json"
INSTALLING = "MPARANZA_RUNTIME_INSTALLING"
# Bump together across products whenever recipes, constraints or this backend change.
POLICY_REVISION = 13
SETUP_WAIT_SECONDS = 1800
# Every process in the managed interpreter holds a reader lease until exit.
# The installer uses the same file exclusively. Never modify the interpreter
# while readers are running. This is concurrency protection, not a sandbox.
GUARD = """from pathlib import Path
import os
import sys
if not os.environ.get("MPARANZA_RUNTIME_INSTALLING"):
    _mpr_root = Path(sys.prefix).parent
    try:
        _mpr_lease = open(_mpr_root / "runtime.lock", "rb")
        if sys.platform == "win32":
            import ctypes
            import msvcrt
            from ctypes import wintypes
            class _MprOverlapped(ctypes.Structure):
                _fields_ = [
                    ("Internal", ctypes.c_size_t),
                    ("InternalHigh", ctypes.c_size_t),
                    ("Offset", wintypes.DWORD),
                    ("OffsetHigh", wintypes.DWORD),
                    ("hEvent", wintypes.HANDLE),
                ]
            _mpr_overlapped = _MprOverlapped()
            _mpr_kernel = ctypes.WinDLL("kernel32", use_last_error=True)
            _mpr_lock = _mpr_kernel.LockFileEx
            _mpr_lock.argtypes = [
                wintypes.HANDLE, wintypes.DWORD, wintypes.DWORD,
                wintypes.DWORD, wintypes.DWORD, ctypes.POINTER(_MprOverlapped),
            ]
            _mpr_lock.restype = wintypes.BOOL
            # CRT LK_RLCK is exclusive. Flags zero requests a real shared lock,
            # allowing nested workflow processes while still excluding installers.
            if not _mpr_lock(msvcrt.get_osfhandle(_mpr_lease.fileno()), 0, 0, 1, 0,
                             ctypes.byref(_mpr_overlapped)):
                raise ctypes.WinError(ctypes.get_last_error())
        else:
            import fcntl
            fcntl.flock(_mpr_lease.fileno(), fcntl.LOCK_SH)
    except OSError as error:
        raise SystemExit("Mparanza runtime lease unavailable: " + str(error))
    if not (Path(sys.prefix) / ".mparanza-shared-ready.json").is_file():
        raise SystemExit("Mparanza shared runtime is not ready; rerun managed setup.")
"""


def enabled(root: Path) -> bool:
    """Opt packaged products into the shared contract through their recipe."""
    return (root / "requirements-shared-core.txt").is_file()


def target(root: Path, data_dir: Path | None = None) -> Path:
    """Return the same stable location regardless of product or module."""
    if data_dir is not None:
        base = data_dir
    elif os.environ.get("MPARANZA_RUNTIME_ROOT"):
        base = Path(os.environ["MPARANZA_RUNTIME_ROOT"]).expanduser()
    elif sys.platform == "win32":
        base = (
            Path(os.environ.get("LOCALAPPDATA", str(Path.home() / "AppData/Local")))
            / "mpr"
        )
    else:
        base = Path.home() / ".local/share/mparanza/runtime"
    base = base.absolute()
    for path in (base, *base.parents):
        if path.is_symlink():
            raise OSError(f"Shared runtime root cannot traverse a symlink: {path}")
    result = base / "venv"
    if result.is_symlink():
        raise OSError("Shared runtime cannot be a symlink")
    return result


def _features(selection: Any) -> set[str]:
    return {"core"} | (
        {"ocr"} if any("ocr" in p.name for p in selection.requirements_files) else set()
    )


def _read(path: Path) -> dict[str, Any]:
    if path.is_symlink():
        raise OSError(f"Runtime metadata cannot be a symlink: {path}")
    if not path.exists():
        return {}
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError("Invalid shared runtime metadata")
    return value


def _recipes(root: Path, features: set[str]) -> dict[str, str]:
    if not features <= {"core", "ocr"}:
        raise ValueError("Unrecognized shared runtime feature")
    implementation = Path(__file__).read_bytes()
    return {
        name: hashlib.sha256(
            (root / f"requirements-shared-{name}.txt").read_bytes()
            + _lock_file(root, name).read_bytes()
            + implementation
        ).hexdigest()
        for name in sorted(features)
    }


def _lock_file(root: Path, feature: str) -> Path:
    """All hosts install the same reviewed lock; never resolve an unlocked recipe."""
    path = root / f"requirements-shared-{feature}.lock"
    if not path.is_file() or path.is_symlink():
        raise ValueError(
            f"Published shared dependency lock is missing or unsafe: {path}"
        )
    return path


def ready(selection: Any, path: Path, api: Any) -> bool:
    """Require the shared receipt, interpreter and all enabled recipe hashes."""
    try:
        receipt = _read(path / RECEIPT)
        policy = _read(path.parent / POLICY)
        features = set(receipt.get("features", []))
        return bool(
            receipt
            and _features(selection) <= features
            and receipt["recipes"] == _recipes(selection.plugin_root, features)
            and api.runtime_python(path).is_file()
            and (path / "pyvenv.cfg").is_file()
            and receipt.get("installed_distributions")
            == api._resolved_dependencies(path)
            and receipt["runtime_key"]
            == policy.get("runtime_key")
            == api.runtime_key(api.runtime_python(path))
        )
    except (OSError, ValueError, KeyError, TypeError, subprocess.SubprocessError):
        return False


def _write_all(descriptor: int, payload: bytes) -> None:
    """Write every byte to an already validated metadata descriptor."""
    view = memoryview(payload)
    while view:
        written = os.write(descriptor, view)
        if written <= 0:
            raise OSError("Runtime metadata write made no progress")
        view = view[written:]


def _replace_state(temporary: Path, path: Path) -> None:
    """Prefer atomic replace; recover only from a cross-volume failure."""
    try:
        temporary.replace(path)
        return
    except OSError as error:
        if error.errno != errno.EXDEV and getattr(error, "winerror", None) != 17:
            raise

    payload = temporary.read_bytes()
    flags = os.O_RDWR | getattr(os, "O_NOFOLLOW", 0)
    descriptor: int | None = None
    created = False
    previous = b""
    try:
        try:
            descriptor = os.open(path, flags | os.O_CREAT | os.O_EXCL, 0o600)
            created = True
        except FileExistsError:
            descriptor = os.open(path, flags)
        info = os.fstat(descriptor)
        import stat

        if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1:
            raise OSError("Runtime metadata must be a single-link regular file")
        if path.is_symlink():
            raise OSError("Runtime metadata cannot be a symlink")
        if not created:
            os.lseek(descriptor, 0, os.SEEK_SET)
            chunks = []
            while chunk := os.read(descriptor, 64 * 1024):
                chunks.append(chunk)
            previous = b"".join(chunks)
        try:
            os.lseek(descriptor, 0, os.SEEK_SET)
            os.ftruncate(descriptor, 0)
            _write_all(descriptor, payload)
            os.fsync(descriptor)
        except OSError:
            if not created:
                os.lseek(descriptor, 0, os.SEEK_SET)
                os.ftruncate(descriptor, 0)
                _write_all(descriptor, previous)
                os.fsync(descriptor)
            raise
    except OSError:
        if descriptor is not None:
            os.close(descriptor)
            descriptor = None
        if created:
            path.unlink(missing_ok=True)
        raise
    finally:
        if descriptor is not None:
            os.close(descriptor)


def _write(path: Path, value: dict[str, Any]) -> None:
    temporary = path.with_name(path.name + f".{os.getpid()}.tmp")
    if temporary.is_symlink() or path.is_symlink():
        raise OSError("Runtime metadata cannot be a symlink")
    try:
        with temporary.open("x", encoding="utf-8") as handle:
            json.dump(value, handle, sort_keys=True)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        _replace_state(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


@contextmanager
def _writer(path: Path, timeout: float = SETUP_WAIT_SECONDS) -> Iterator[None]:
    """Wait for installers and running managed Python readers to finish."""
    import stat

    if path.is_symlink():
        raise OSError("Runtime lock cannot be a symlink")
    fd = os.open(path, os.O_RDWR | os.O_CREAT | getattr(os, "O_NOFOLLOW", 0), 0o600)
    try:
        info = os.fstat(fd)
        if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1:
            raise OSError("Runtime lock must be a single-link regular file")
        if info.st_size == 0:
            os.write(fd, b"1")
        deadline = time.monotonic() + timeout
        announced = False
        while True:
            try:
                if sys.platform == "win32":
                    import msvcrt

                    os.lseek(fd, 0, os.SEEK_SET)
                    msvcrt.locking(fd, msvcrt.LK_NBLCK, 1)
                else:
                    import fcntl

                    fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
                break
            except OSError as error:
                if error.errno not in {errno.EACCES, errno.EAGAIN, errno.EDEADLK}:
                    raise
                if not announced:
                    logging.getLogger(__name__).info(
                        "Waiting for shared Python setup or running workflows to finish."
                    )
                    announced = True
                if time.monotonic() >= deadline:
                    raise OSError(
                        f"Shared runtime is busy after {timeout:g} seconds; "
                        "setup or a running workflow still holds its lock. Retry after it finishes."
                    )
                time.sleep(0.05)
        yield
    finally:
        os.close(fd)


def ensure(selection: Any, path: Path, api: Any, runner: Any) -> tuple[bool, Path, str]:
    """Install the complete declared union, retaining OCR across later updates."""
    if ready(selection, path, api):
        return True, path, f"Shared Mparanza runtime ready at {path}"
    if Path(sys.prefix).resolve() == path.resolve():
        return (
            False,
            path,
            (
                "Shared runtime update requires the base Python interpreter. "
                "Exit this workflow and run the managed setup command outside the managed environment."
            ),
        )
    try:
        path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        if os.name != "nt":
            path.parent.chmod(0o700)
        with _writer(path.parent / "runtime.lock"):
            if ready(selection, path, api):
                return True, path, f"Shared Mparanza runtime ready at {path}"
            return _install(selection, path, api, runner)
    except (
        OSError,
        ValueError,
        KeyError,
        TypeError,
        subprocess.SubprocessError,
    ) as error:
        return False, path, str(error)


def _install(
    selection: Any, path: Path, api: Any, runner: Any
) -> tuple[bool, Path, str]:
    def run(command: list[str], **kwargs: Any) -> Any:
        environment = dict(kwargs.pop("env", os.environ))
        environment.pop("PYTHONPATH", None)
        environment.pop("PYTHONHOME", None)
        environment[INSTALLING] = "1"
        return runner(command, env=environment, **kwargs)

    previous = _read(path / RECEIPT)
    policy = _read(path.parent / POLICY)
    if policy.get("revision", 0) > POLICY_REVISION:
        raise ValueError(
            "Update this plugin: the shared environment uses a newer runtime policy."
        )
    if policy.get("revision") == POLICY_REVISION:
        existing_features = set(policy.get("features", []))
        if policy.get("recipes") != _recipes(selection.plugin_root, existing_features):
            raise ValueError(
                "Conflicting shared recipes at the same revision; update the product packages together."
            )
    features = (
        _features(selection)
        | set(policy.get("features", []))
        | set(previous.get("features", []))
    )
    recipes = _recipes(selection.plugin_root, features)
    existing = (path / "pyvenv.cfg").is_file()
    interpreter = (
        str(api.runtime_python(path)) if existing else _base_python(path, api, run)
    )
    key = api.runtime_key(interpreter, runner=run)
    if any(
        record and record.get("runtime_key") != key for record in (policy, previous)
    ):
        raise ValueError(
            "Shared interpreter platform changed; explicit maintenance rebuild is required."
        )
    _write(
        path.parent / POLICY,
        {
            "features": sorted(features),
            "runtime_key": key,
            "revision": POLICY_REVISION,
            "recipes": recipes,
        },
    )
    # Invalidate before any package mutation. Failed setup remains explicitly
    # unavailable and is repaired by the next serialized install, never reused.
    (path / RECEIPT).unlink(missing_ok=True)
    if not existing:
        result = run(
            [interpreter, "-m", "venv", "--without-pip", str(path)],
            capture_output=True,
            text=True,
            check=False,
            timeout=120,
        )
        if result.returncode:
            return False, path, api._process_detail(result)
        if api.runtime_key(api.runtime_python(path), runner=run) != key:
            raise ValueError(
                "Created shared interpreter does not match selected Python."
            )
    pip, environment, detail = api._bootstrap_pip(path, runner=run)
    if pip is None:
        return False, path, detail
    # The OCR lock includes core and is generated from the same resolution.
    lock = _lock_file(selection.plugin_root, "ocr" if "ocr" in features else "core")
    command = [
        *pip,
        "install",
        "--disable-pip-version-check",
        "--no-input",
        "--require-hashes",
        "-r",
        str(lock),
    ]
    installed = run(
        command,
        env=environment,
        capture_output=True,
        text=True,
        check=False,
        timeout=900,
    )
    if installed.returncode:
        return (
            False,
            path,
            api._network_permission_detail(api._process_detail(installed)),
        )
    _reconcile_locked_inventory(
        selection.plugin_root, path, lock, api, run, pip, environment
    )
    checked = run(
        [*pip, "check"],
        env=environment,
        capture_output=True,
        text=True,
        check=False,
        timeout=120,
    )
    if checked.returncode:
        return False, path, api._process_detail(checked)
    diagnostics: list[str] = []
    if not api._dependencies_ready(
        selection, path, runner=run, require_receipt=False, diagnostics=diagnostics
    ):
        return (
            False,
            path,
            "Shared runtime validation failed: " + "\n".join(diagnostics),
        )
    sites = (
        [path / "Lib/site-packages"]
        if os.name == "nt"
        else list(path.glob("lib/python*/site-packages"))
    )
    if len(sites) != 1:
        raise ValueError("Shared runtime must have exactly one site-packages directory")
    guard = sites[0] / "_mparanza_runtime_guard.py"
    if guard.is_symlink():
        raise OSError("Shared runtime guard cannot be a symlink")
    guard.write_text(GUARD, encoding="utf-8")
    startup = sites[0] / "00_mparanza_runtime.pth"
    if startup.is_symlink():
        raise OSError("Runtime startup hook cannot be a symlink")
    startup.write_text("import _mparanza_runtime_guard\n", encoding="utf-8")
    _write(
        path / RECEIPT,
        {
            "schema_version": 1,
            "features": sorted(features),
            "recipes": recipes,
            "runtime_key": key,
            "installed_distributions": api._resolved_dependencies(path),
        },
    )
    return True, path, f"Shared Mparanza runtime installed at {path}"


def _reconcile_locked_inventory(
    root: Path,
    path: Path,
    lock: Path,
    api: Any,
    run: Any,
    pip: list[str],
    environment: dict[str, str],
) -> None:
    """Validate target-platform pins and remove obsolete managed dependencies."""
    inspected = run(
        [
            str(api.runtime_python(path)),
            "-I",
            "-S",
            str(root / "scripts/_locked_dependencies.py"),
            str(lock),
        ],
        env=environment,
        capture_output=True,
        text=True,
        check=False,
        timeout=30,
    )
    if inspected.returncode:
        raise ValueError(
            "Cannot verify the shared dependency lock: "
            + api._process_detail(inspected)
        )
    expected = json.loads(inspected.stdout)
    if not isinstance(expected, dict) or not all(
        isinstance(name, str) and isinstance(version, str)
        for name, version in expected.items()
    ):
        raise ValueError("Invalid resolved dependency lock")

    def inventory() -> dict[str, str]:
        return {
            re.sub(r"[-_.]+", "-", item["name"]).lower(): item["version"]
            for item in api._resolved_dependencies(path)
        }

    actual = inventory()
    differences = [
        f"{name}: expected {version}, found {actual.get(name, 'missing')}"
        for name, version in expected.items()
        if actual.get(name) != version
    ]
    if differences:
        raise ValueError(
            "Shared dependency versions differ from the published lock: "
            + "; ".join(differences)
        )
    # These are installer tools, not workflow dependencies, unless the lock
    # explicitly requires them. The complete workflow graph must match the lock.
    obsolete = sorted(actual.keys() - expected.keys() - {"pip", "setuptools", "wheel"})
    if obsolete:
        removed = run(
            [*pip, "uninstall", "--yes", *obsolete],
            env=environment,
            capture_output=True,
            text=True,
            check=False,
            timeout=120,
        )
        if removed.returncode or set(obsolete) & inventory().keys():
            raise ValueError(
                "Could not remove obsolete shared dependencies: "
                + api._process_detail(removed)
            )


def _base_python(path: Path, api: Any, run: Any) -> str:
    """Discover or provision the cold-start interpreter before recording identity."""
    try:
        return api._python312_executable(run, allow_uv=False)
    except ValueError as error:
        if "require CPython 3.12" not in str(error):
            raise
        import importlib.util

        bootstrap_path = Path(__file__).with_name("_python_bootstrap.py")
        spec = importlib.util.spec_from_file_location(
            "mparanza_python_bootstrap", bootstrap_path
        )
        if spec is None or spec.loader is None:
            raise ValueError("Packaged Python bootstrap is unavailable")
        bootstrap = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(bootstrap)
        return bootstrap.provision(path.parent, run)
