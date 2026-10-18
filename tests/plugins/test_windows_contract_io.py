"""Run the real financial/plan contract boundaries on Windows and POSIX."""

from __future__ import annotations

import hashlib
import importlib.util
import os
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture(
    params=[
        ("financial-analysis", "preparation_contract_kernel"),
        ("sales-plan", "plan_contract_kernel"),
    ]
)
def kernel(request, monkeypatch):
    product, name = request.param
    scripts = ROOT / "plugins" / product / "scripts"
    monkeypatch.syspath_prepend(str(scripts))
    spec = importlib.util.spec_from_file_location(
        "portable_" + name, scripts / (name + ".py")
    )
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_pinned_output_roundtrip_and_exclusive_creation(kernel, tmp_path):
    with kernel.pinned_directory(tmp_path) as directory:
        directory.write_json_exclusive(
            "résultat.json", {"label": "caffè", "amount": "10.00"}
        )
        directory.verify_tracked()
        assert directory.names() == ["résultat.json"]
        assert directory.snapshot_file("résultat.json") == (
            (tmp_path / "résultat.json").stat().st_size,
            hashlib.sha256((tmp_path / "résultat.json").read_bytes()).hexdigest(),
        )
        with pytest.raises(kernel.ContractValidationError):
            directory.write_json_exclusive("résultat.json", {"changed": True})
        directory.cleanup_tracked()
        assert directory.names() == []


def test_nested_input_snapshot_is_exact(kernel, tmp_path):
    parent = tmp_path / "états"
    parent.mkdir()
    source = parent / "source.csv"
    source.write_bytes(b"amount\r\n100.00\r\n")
    assert kernel.file_snapshot_beneath(source, root=tmp_path) == (
        len(source.read_bytes()),
        hashlib.sha256(source.read_bytes()).hexdigest(),
    )


def test_beneath_rejects_hardlink_and_traversal(kernel, tmp_path):
    source = tmp_path / "original"
    source.write_bytes(b"private")
    target = tmp_path / "linked"
    os.link(source, target)
    with pytest.raises(kernel.ContractValidationError):
        kernel.file_snapshot_beneath(target, root=tmp_path)
    with pytest.raises(kernel.ContractValidationError):
        kernel.file_snapshot_beneath(tmp_path / ".." / "outside", root=tmp_path)


def test_beneath_rejects_symlink_or_junction(kernel, tmp_path):
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "secret").write_bytes(b"private")
    root = tmp_path / "approved"
    root.mkdir()
    link = root / "link"
    if os.name == "nt":
        import subprocess

        subprocess.run(
            ["cmd", "/c", "mklink", "/J", str(link), str(outside)],
            check=True,
            capture_output=True,
        )
    else:
        link.symlink_to(outside, target_is_directory=True)
    with pytest.raises(kernel.ContractValidationError):
        kernel.file_snapshot_beneath(link / "secret", root=root)


def test_directory_substitution_is_refused(kernel, tmp_path):
    output = tmp_path / "output"
    output.mkdir()
    with kernel.pinned_directory(output) as directory:
        if os.name == "nt":
            with pytest.raises(OSError):
                output.rename(tmp_path / "moved")
        else:
            output.rename(tmp_path / "moved")
            output.mkdir()
            with pytest.raises(kernel.ContractValidationError):
                directory.write_json_exclusive("result.json", {"a": 1})
    assert not (output / "result.json").exists()


def test_cleanup_does_not_remove_replacement(kernel, tmp_path):
    with kernel.pinned_directory(tmp_path) as directory:
        directory.write_json_exclusive("partial.json", {"a": 1})
        (tmp_path / "partial.json").rename(tmp_path / "old.json")
        (tmp_path / "partial.json").write_bytes(b"other work")
        with pytest.raises(kernel.ContractValidationError):
            directory.cleanup_tracked()
    assert (tmp_path / "partial.json").read_bytes() == b"other work"


def test_native_helpers_remain_identical():
    assert (
        ROOT / "plugins/financial-analysis/scripts/windows_contract_io.py"
    ).read_bytes() == (
        ROOT / "plugins/sales-plan/scripts/windows_contract_io.py"
    ).read_bytes()
