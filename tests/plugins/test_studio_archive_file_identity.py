from __future__ import annotations

import hashlib
import importlib.util
import os
from pathlib import Path
from types import SimpleNamespace

import pytest

ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture
def ledger():
    spec = importlib.util.spec_from_file_location(
        "file_identity_ledger", ROOT / "plugins/studio-archive/scripts/client_ledger.py"
    )
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def altered(observed, **changes):
    fields = ("st_dev", "st_ino", "st_size", "st_mtime_ns", "st_ctime_ns", "st_nlink")
    return SimpleNamespace(
        **({key: getattr(observed, key) for key in fields} | changes)
    )


def perform(ledger, path, operation):
    if operation == "copy":
        return ledger._stable_copy(path, path.parent / "copied.bin")
    return ledger._stable_file_identity(path, label="input")


@pytest.mark.parametrize("operation", ["hash", "copy"])
def test_hashes_exact_binary_bytes_after_metadata_change(ledger, tmp_path, operation):
    path = tmp_path / "input.bin"
    payload = b"first\r\nsecond\x1alast\r\n"
    path.write_bytes(payload)
    path.chmod(0o400)
    try:
        assert perform(ledger, path, operation) == (
            len(payload),
            hashlib.sha256(payload).hexdigest(),
        )
        if operation == "copy":
            assert (tmp_path / "copied.bin").read_bytes() == payload
    finally:
        path.chmod(0o600)


@pytest.mark.parametrize("mutation", [None, "descriptor_ctime", "path_ctime", "inode"])
@pytest.mark.parametrize("operation", ["hash", "copy"])
def test_windows_ctime_difference_retains_mutation_detection(
    ledger, tmp_path, monkeypatch, mutation, operation
):
    path = tmp_path / "input.bin"
    path.write_bytes(b"unchanged bytes")
    native_stat = path.stat()
    calls = {"descriptor": 0, "path": 0}

    def fstat(descriptor):
        calls["descriptor"] += 1
        observed = os.fstat(descriptor)
        changed = calls["descriptor"] > 1 and mutation == "descriptor_ctime"
        return altered(observed, st_ctime_ns=native_stat.st_ctime_ns + 100 + changed)

    ordinary_file = ledger._ordinary_file

    def lstat(file_path, *, label):
        calls["path"] += 1
        observed = ordinary_file(file_path, label=label)
        changes = {}
        if calls["path"] > 1 and mutation == "path_ctime":
            changes["st_ctime_ns"] = observed.st_ctime_ns + 1
        if mutation == "inode":
            changes["st_ino"] = observed.st_ino + 1
        return altered(observed, **changes)

    monkeypatch.setattr(
        ledger, "os", SimpleNamespace(**(vars(os) | {"name": "nt", "fstat": fstat}))
    )
    monkeypatch.setattr(ledger, "_ordinary_file", lstat)
    if mutation is None:
        assert (
            perform(ledger, path, operation)[1]
            == hashlib.sha256(path.read_bytes()).hexdigest()
        )
    else:
        with pytest.raises(ledger.LedgerError, match="changed"):
            perform(ledger, path, operation)
        assert not (tmp_path / "copied.bin").exists()


@pytest.mark.parametrize("operation", ["hash", "copy"])
def test_rejects_bytes_changed_during_read(ledger, tmp_path, monkeypatch, operation):
    path = tmp_path / "input.bin"
    path.write_bytes(b"original bytes")
    native_read = os.read

    def read(descriptor, size):
        result = native_read(descriptor, size)
        if result:
            path.write_bytes(b"replacement bytes")
        return result

    monkeypatch.setattr(ledger, "os", SimpleNamespace(**(vars(os) | {"read": read})))
    with pytest.raises(ledger.LedgerError, match="changed"):
        perform(ledger, path, operation)
    assert not (tmp_path / "copied.bin").exists()
