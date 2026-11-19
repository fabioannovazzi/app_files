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


def test_staging_failure_preserves_os_cause_and_directory_evidence(ledger, tmp_path):
    source = tmp_path / "input.bin"
    source.write_bytes(b"original evidence")
    missing = tmp_path / "unavailable destination"

    with pytest.raises(
        ledger.LedgerError, match="Temporary file creation failed"
    ) as raised:
        ledger._stable_copy(source, missing / "copied.bin")

    assert isinstance(raised.value.__cause__, FileNotFoundError)
    assert raised.value.__cause__.errno == 2
    assert "parent_exists=False" in str(raised.value)
    assert f"parent_characters={len(str(missing))}" in str(raised.value)
    assert "winerror=" in str(raised.value)
    assert source.read_bytes() == b"original evidence"


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


def test_deep_unicode_source_staging_receipt_and_reopen(ledger, tmp_path):
    parent = tmp_path
    for _ in range(5):
        parent /= "documenti-contabilità-" * 3
    ledger._io_path(parent).mkdir(parents=True)
    source = parent / "estratto.bin"
    snapshot = parent / "copia.bin"
    receipt = parent / "ricevuta.json"
    ledger._io_path(source).write_bytes(b"synthetic bank source")

    size, digest = ledger._stable_copy(source, snapshot)
    ledger._write_json(receipt, {"size": size, "digest": digest})

    assert ledger._read_json(receipt, label="receipt") == {
        "size": 21,
        "digest": hashlib.sha256(b"synthetic bank source").hexdigest(),
    }
    assert ledger._stable_file_identity(snapshot, label="saved source") == (
        size,
        digest,
    )


@pytest.mark.skipif(
    os.name != "nt", reason="Requires native Windows UNC path semantics"
)
def test_unc_long_path_preserves_server_and_share(ledger):
    ordinary = Path(r"\\server\share") / ("x" * 110) / ("y" * 110) / "ricevuta.json"
    extended = ledger._io_path(ordinary)
    assert str(extended) == "\\\\?\\UNC\\" + str(ordinary)[2:]
    assert ledger._io_path(extended) == extended


@pytest.mark.skipif(os.name != "nt", reason="Requires a native Windows share")
def test_available_loopback_unc_share_stages_and_reopens_unicode_receipt(
    ledger, tmp_path
):
    # Only address this runner's own temporary directory, via its local disk share.
    if len(tmp_path.drive) != 2:
        pytest.skip("Runner temp directory is not drive-backed")
    share = Path(f"//localhost/{tmp_path.drive[0]}$/").joinpath(*tmp_path.parts[1:])
    if not share.is_dir():
        pytest.skip("Runner does not expose its loopback disk share")
    parent = share.joinpath(*(["Documenti di contabilità" * 3] * 4))
    ledger._io_path(parent).mkdir(parents=True)
    source, copied = parent / "fonte.bin", parent / "copia.bin"
    ledger._io_path(source).write_bytes(b"synthetic UNC input")
    byte_count, digest = ledger._stable_copy(source, copied)
    receipt = parent / "ricevuta.json"
    ledger._write_json(receipt, {"digest": digest})
    assert ledger._read_json(receipt, label="receipt")["digest"] == digest
    assert ledger._stable_file_identity(copied, label="saved") == (byte_count, digest)
