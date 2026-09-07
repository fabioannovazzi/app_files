"""One mutable, leased Python environment for all Mparanza products."""

from __future__ import annotations

import errno
import hashlib
import json
import os
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
POLICY_REVISION = 3
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
            import msvcrt
            _mpr_lease.seek(0)
            msvcrt.locking(_mpr_lease.fileno(), msvcrt.LK_RLCK, 1)
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
    constraint = _constraint(root)
    lock_bytes = (constraint.read_bytes() if constraint else b"") + Path(
        __file__
    ).read_bytes()
    return {
        name: hashlib.sha256(
            (root / f"requirements-shared-{name}.txt").read_bytes() + lock_bytes
        ).hexdigest()
        for name in sorted(features)
    }


def _constraint(root: Path) -> Path | None:
    if sys.platform == "darwin":
        path = root / "constraints-shared-macos-py312.txt"
        return path if path.is_file() else None
    return None


def ready(selection: Any, path: Path, api: Any) -> bool:
    """Require the shared receipt, interpreter and all enabled recipe hashes."""
    try:
        receipt = _read(path / RECEIPT)
        features = set(receipt.get("features", []))
        return bool(
            receipt
            and _features(selection) <= features
            and receipt["recipes"] == _recipes(selection.plugin_root, features)
            and receipt["runtime_key"] == api.runtime_key()
            and api.runtime_python(path).is_file()
            and (path / "pyvenv.cfg").is_file()
        )
    except (OSError, ValueError, KeyError, TypeError):
        return False


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
        temporary.replace(path)
    finally:
        temporary.unlink(missing_ok=True)


@contextmanager
def _writer(path: Path, timeout: float = 60) -> Iterator[None]:
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
                if time.monotonic() >= deadline:
                    raise OSError(
                        "Shared runtime is busy; close running workflows and retry."
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
    if policy.get("runtime_key", api.runtime_key()) != api.runtime_key():
        raise ValueError(
            "Shared interpreter platform changed; explicit maintenance rebuild is required."
        )
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
    _write(
        path.parent / POLICY,
        {
            "features": sorted(features),
            "runtime_key": api.runtime_key(),
            "revision": POLICY_REVISION,
            "recipes": recipes,
        },
    )
    # Invalidate before any package mutation. Failed setup remains explicitly
    # unavailable and is repaired by the next serialized install, never reused.
    (path / RECEIPT).unlink(missing_ok=True)
    if not (path / "pyvenv.cfg").is_file():
        try:
            interpreter = api._python312_executable(run, allow_uv=False)
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
            interpreter = bootstrap.provision(path.parent, run)
        result = run(
            [interpreter, "-m", "venv", "--without-pip", str(path)],
            capture_output=True,
            text=True,
            check=False,
            timeout=120,
        )
        if result.returncode:
            return False, path, api._process_detail(result)
    pip, environment, detail = api._bootstrap_pip(path, runner=run)
    if pip is None:
        return False, path, detail
    command = [*pip, "install", "--disable-pip-version-check", "--no-input"]
    for feature in sorted(features):
        command.extend(
            ["-r", str(selection.plugin_root / f"requirements-shared-{feature}.txt")]
        )
    constraint = _constraint(selection.plugin_root)
    if constraint is not None:
        command.extend(["-c", str(constraint)])
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
            "runtime_key": api.runtime_key(),
            "installed_distributions": api._resolved_dependencies(path),
        },
    )
    return True, path, f"Shared Mparanza runtime installed at {path}"
