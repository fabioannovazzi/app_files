"""Provision a private CPython without requiring pip, uv or changing system Python."""

from __future__ import annotations

import hashlib
import io
import os
import platform
import subprocess
import sys
import tempfile
import urllib.error
import urllib.request
import zipfile
from pathlib import Path
from typing import Any

__all__ = ["provision"]
# Official PyPI uv 0.12.10 wheels, pinned at release review.
ASSETS = {
    "darwin:arm64": (
        "https://files.pythonhosted.org/packages/04/2e/5614e9a940fe1bf291342410b2cde9fe35a1430135ae7434ea8fd67033f8/uv-0.12.10-py3-none-macosx_11_0_arm64.whl",
        "5dc26c73826d2119292d49d71c5a9d5ba9dd97dd02459d816b8226f47f3dc6bd",
    ),
    "darwin:x86_64": (
        "https://files.pythonhosted.org/packages/ab/4d/ef846ec0a4dfa8d4f47b96a87a1e331143be5a045c28c8b4b0374946455f/uv-0.12.10-py3-none-macosx_10_12_x86_64.whl",
        "7e3a70d9dff95481afccd7d41e7ec42fdc230d53487b3e7e633f9b35610401b5",
    ),
    "win32:amd64": (
        "https://files.pythonhosted.org/packages/a6/88/e980985d93283c546374b6b9dfa486a28091c4c056226711e31bb0f722d1/uv-0.12.10-py3-none-win_amd64.whl",
        "2ad71395c31b5db20c56327f62ee0299f75833308d4413284aba87324d092afa",
    ),
    "win32:arm64": (
        "https://files.pythonhosted.org/packages/84/10/fa542546044f783060d09a624f9964b595c0a0713cf2d89ade69c6667d8b/uv-0.12.10-py3-none-win_arm64.whl",
        "4f097c6b7f63eceb3faf5102009f9a8cc22fd7d8a341858d2fd540f46a592f7a",
    ),
    "linux:x86_64": (
        "https://files.pythonhosted.org/packages/f0/41/f0e14ba1f881f7126152dcaf04119b3a2bd7566ba1cac1d22834bd134cbf/uv-0.12.10-py3-none-manylinux_2_17_x86_64.manylinux2014_x86_64.whl",
        "f7d6248ad9f2d282fea795f248da8fa666ab382df50d8385bd98e01049440a0c",
    ),
    "linux:aarch64": (
        "https://files.pythonhosted.org/packages/d1/03/e71936935b8ac26390b280e102b9db823e90adb1134f7e226538054fdece/uv-0.12.10-py3-none-manylinux_2_17_aarch64.manylinux2014_aarch64.musllinux_1_1_aarch64.whl",
        "bd0afae6918795c6a61a649e64d735e339f3d62f8310235da6f19eb3f66f323b",
    ),
}
MAX_DOWNLOAD = 64 * 1024 * 1024


def _uv(base: Path) -> Path:
    machine = platform.machine().lower()
    if machine == "aarch64" and sys.platform in {"darwin", "win32"}:
        machine = "arm64"
    if machine == "x86_64" and sys.platform == "win32":
        machine = "amd64"
    key = f"{sys.platform}:{machine}"
    if key not in ASSETS:
        raise ValueError(f"Automatic Python setup is unavailable for {key}.")
    url, digest = ASSETS[key]
    if base.is_symlink():
        raise ValueError("Python bootstrap storage cannot be a symlink")
    base.mkdir(parents=True, exist_ok=True)
    binary = base / ("uv.exe" if sys.platform == "win32" else "uv")
    # Download only during cold provisioning, under the shared installer lock.
    try:
        with urllib.request.urlopen(
            url, timeout=120
        ) as response:  # nosec B310 - fixed HTTPS release URLs and pinned SHA-256
            payload = response.read(MAX_DOWNLOAD + 1)
    except (OSError, urllib.error.URLError) as error:
        raise ValueError(
            f"Automatic Python download failed; check network access and retry: {error}"
        ) from error
    if len(payload) > MAX_DOWNLOAD or hashlib.sha256(payload).hexdigest() != digest:
        raise ValueError(
            "Automatic Python setup rejected a uv download with an invalid SHA-256."
        )
    with zipfile.ZipFile(io.BytesIO(payload)) as archive:
        candidates = [
            entry
            for entry in archive.infolist()
            if entry.filename.endswith(".data/scripts/" + binary.name)
        ]
        if len(candidates) != 1 or candidates[0].file_size > MAX_DOWNLOAD:
            raise ValueError("Automatic Python setup received an invalid uv wheel.")
        data = archive.read(candidates[0])
    with tempfile.NamedTemporaryFile(dir=base, delete=False) as handle:
        temporary = Path(handle.name)
        handle.write(data)
    try:
        temporary.chmod(0o700)
        temporary.replace(binary)
    finally:
        temporary.unlink(missing_ok=True)
    return binary


def provision(base: Path, runner: Any = subprocess.run) -> str:
    """Install Python into shared storage, without shell profiles or global binaries."""
    if (base / "python").is_symlink():
        raise ValueError("Private Python storage cannot be a symlink")
    uv = _uv(base / "bootstrap")
    environment = {
        key: value
        for key, value in os.environ.items()
        if not key.startswith("UV_")
        and key not in {"VIRTUAL_ENV", "CONDA_PREFIX", "PYTHONHOME", "PYTHONPATH"}
    }
    environment.update(
        {
            "UV_PYTHON_INSTALL_DIR": str(base / "python"),
            "UV_CACHE_DIR": str(base / "bootstrap/cache"),
            "UV_PYTHON_BIN_DIR": str(base / "bootstrap/bin"),
            "UV_PYTHON_INSTALL_BIN": "0",
        }
    )
    commands = [
        [str(uv), "--no-config", "python", "install", "--no-bin", "cpython@3.12"],
        [
            str(uv),
            "--no-config",
            "python",
            "find",
            "--no-project",
            "--system",
            "--managed-python",
            "cpython@3.12",
        ],
    ]
    candidate = ""
    for command in commands:
        result = runner(
            command,
            env=environment,
            capture_output=True,
            text=True,
            timeout=600,
            check=False,
        )
        if result.returncode:
            raise ValueError(
                "Automatic Python setup failed; retry after resolving download or storage access: "
                + result.stderr.strip()
            )
        candidate = result.stdout.strip()
    executable = Path(candidate)
    if not executable.is_file() or not executable.resolve().is_relative_to(
        (base / "python").resolve()
    ):
        raise ValueError(
            "Automatic Python setup did not return its private interpreter."
        )
    probe = runner(
        [
            str(executable),
            "-I",
            "-c",
            "import sys; assert sys.implementation.name == 'cpython' and sys.version_info[:2] == (3, 12)",
        ],
        env=environment,
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )
    if probe.returncode:
        raise ValueError("Automatic Python setup returned an incompatible interpreter.")
    return str(executable)
