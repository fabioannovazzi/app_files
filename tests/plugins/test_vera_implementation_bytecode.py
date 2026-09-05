"""Bytecode tolerance and bounded repair for Vera implementation contracts."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

__all__: list[str] = []
ROOT = Path(__file__).resolve().parents[2]
MODULES = (
    "journal-sampling",
    "open-item-reconciliation",
    "journal-bank-reconciliation",
    "concordato-plan-review",
    "report-builder",
    "check-entries",
)


@pytest.fixture(params=MODULES)
def module_copy(request: pytest.FixtureRequest, tmp_path: Path) -> Path:
    """Copy a standalone module with its own assurance package."""
    root = tmp_path / request.param
    ignore = shutil.ignore_patterns("__pycache__", "*.pyc", "*.pyo")
    shutil.copytree(ROOT / "plugins" / request.param, root, ignore=ignore)
    shutil.copytree(
        ROOT / "plugins/_shared/vendor/modules/vera_assurance",
        root / "vendor/modules/vera_assurance",
        ignore=ignore,
    )
    return root


def validate(root: Path) -> subprocess.CompletedProcess[str]:
    """Validate source in a fresh process without changing pytest's import state."""
    return subprocess.run(
        [
            sys.executable,
            "-B",
            "-c",
            "import implementation_bootstrap as b; b.activate_implementation_boundary()",
        ],
        cwd=root / "scripts",
        capture_output=True,
        text=True,
        check=False,
    )


@pytest.mark.parametrize(
    "artifact", ["__pycache__/foo.cpython-3x.pyc", "foo.pyc", "foo.pyo"]
)
def test_bytecode_does_not_break_exact_contract(
    module_copy: Path, artifact: str
) -> None:
    cache = module_copy / "vendor/modules/vera_assurance" / artifact
    cache.parent.mkdir(parents=True, exist_ok=True)
    cache.write_bytes(b"dummy bytecode")
    result = validate(module_copy)
    assert result.returncode == 0, result.stderr


@pytest.mark.parametrize("entry", ["unexpected.py", "unexpected-directory"])
def test_unexpected_entry_still_fails(module_copy: Path, entry: str) -> None:
    extra = module_copy / "vendor/modules/vera_assurance" / entry
    if entry.endswith(".py"):
        extra.write_text("# not allowed\n")
    else:
        extra.mkdir()
    result = validate(module_copy)
    assert result.returncode != 0
    assert "contract" in result.stderr


def test_ambient_import_then_dependency_check_passes(module_copy: Path) -> None:
    vendor = module_copy / "vendor/modules"
    env = dict(os.environ, PYTHONPATH=str(vendor))
    env.pop("PYTHONDONTWRITEBYTECODE", None)
    env.pop("PYTHONPYCACHEPREFIX", None)
    subprocess.run(
        [
            sys.executable,
            "-c",
            "import vera_assurance.money, vera_assurance.serialization",
        ],
        cwd=module_copy,
        env=env,
        check=True,
        capture_output=True,
    )
    assert list((vendor / "vera_assurance/__pycache__").glob("*.pyc"))
    result = subprocess.run(
        [sys.executable, str(module_copy / "scripts/check_dependencies.py")],
        cwd=module_copy,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr


def test_repair_removes_only_own_regular_cache_pyc(
    module_copy: Path, tmp_path: Path
) -> None:
    cache = module_copy / "vendor/modules/vera_assurance/__pycache__"
    cache.mkdir()
    removable = cache / "foo.pyc"
    removable.write_bytes(b"cache")
    retained = cache / "keep.txt"
    retained.write_text("retain")
    pyo = cache / "keep.pyo"
    pyo.write_bytes(b"retain")
    outside = tmp_path / "outside.pyc"
    outside.write_bytes(b"outside")
    (cache / "linked.pyc").symlink_to(outside)
    result = subprocess.run(
        [
            sys.executable,
            str(module_copy / "scripts/implementation_bootstrap.py"),
            "--repair",
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    assert not removable.exists()
    assert retained.read_text() == "retain"
    assert pyo.read_bytes() == b"retain"
    assert outside.read_bytes() == b"outside"
    assert (cache / "linked.pyc").is_symlink()


def test_bytecode_named_symlink_is_rejected(module_copy: Path, tmp_path: Path) -> None:
    outside = tmp_path / "outside"
    outside.mkdir()
    (module_copy / "vendor/modules/vera_assurance/__pycache__").symlink_to(outside)
    result = validate(module_copy)
    assert result.returncode != 0
    assert "symlink" in result.stderr


def test_repair_refuses_contract_mismatch_without_removing_cache(
    module_copy: Path,
) -> None:
    cache = module_copy / "vendor/modules/vera_assurance/__pycache__"
    cache.mkdir()
    bytecode = cache / "foo.pyc"
    bytecode.write_bytes(b"retain on failure")
    (module_copy / "scripts/unexpected.py").write_text("# unexpected\n")
    result = subprocess.run(
        [
            sys.executable,
            str(module_copy / "scripts/implementation_bootstrap.py"),
            "--repair",
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode != 0
    assert "contract" in result.stderr
    assert bytecode.read_bytes() == b"retain on failure"


@pytest.mark.parametrize(
    "artifact", ["__pycache__/ambient.pyc", "ambient.pyc", "ambient.pyo"]
)
def test_mcp_starts_with_incidental_bytecode(module_copy: Path, artifact: str) -> None:
    node = shutil.which("node")
    if node is None:
        pytest.skip("Node.js is required for MCP startup tests")
    cache = module_copy / "vendor/modules/vera_assurance" / artifact
    cache.parent.mkdir(parents=True, exist_ok=True)
    cache.write_bytes(b"inert cache")
    requests = [
        {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}},
        {"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}},
    ]

    result = subprocess.run(
        [node, str(module_copy / "mcp/server.cjs"), "--stdio"],
        input="".join(json.dumps(request) + "\n" for request in requests),
        cwd=module_copy,
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    responses = [json.loads(line) for line in result.stdout.splitlines()]
    assert responses[0]["result"]["serverInfo"]
    assert responses[1]["result"]["tools"]
    assert cache.read_bytes() == b"inert cache"


@pytest.mark.parametrize("unsafe", ["source", "cache_symlink", "bytecode_hardlink"])
def test_mcp_still_rejects_unsafe_implementation_entries(
    module_copy: Path,
    tmp_path: Path,
    unsafe: str,
) -> None:
    node = shutil.which("node")
    if node is None:
        pytest.skip("Node.js is required for MCP startup tests")
    vendor = module_copy / "vendor/modules/vera_assurance"
    external = tmp_path / "external"
    if unsafe == "source":
        (vendor / "unexpected.py").write_text("# unowned source\n")
    elif unsafe == "cache_symlink":
        external.mkdir()
        (vendor / "__pycache__").symlink_to(external, target_is_directory=True)
    else:
        external.write_bytes(b"external")
        os.link(external, vendor / "ambient.pyc")

    result = subprocess.run(
        [node, str(module_copy / "mcp/server.cjs"), "--stdio"],
        input="",
        cwd=module_copy,
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )

    assert result.returncode != 0
