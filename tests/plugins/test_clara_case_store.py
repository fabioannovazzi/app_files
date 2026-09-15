"""Actual process-death recovery across the case journal's durable boundaries."""

from __future__ import annotations

import errno
import importlib
import subprocess
import sys
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parents[2] / "plugins/clara/scripts"


@pytest.fixture
def store(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.syspath_prepend(str(SCRIPTS))
    return importlib.import_module("case_store")


@pytest.mark.parametrize("boundary", range(1, 10))
def test_process_death_at_each_durable_boundary_recovers_coherent_revision(
    tmp_path: Path, store, boundary: int
) -> None:
    (tmp_path / "first").write_bytes(b"old first")
    (tmp_path / "second").write_bytes(b"old second")
    program = """
import os, sys
from pathlib import Path
sys.path.insert(0, sys.argv[1])
import case_store as store
root = Path(sys.argv[2])
selected = int(sys.argv[3])
original = store._sync_directory
count = 0
def crash_after_sync(path):
    global count
    original(path)
    count += 1
    if count == selected:
        os._exit(41)
store._sync_directory = crash_after_sync
with store.transaction(root):
    store.atomic_bytes(root / 'first', b'new first')
    store.atomic_bytes(root / 'second', b'new second')
    store.atomic_bytes(root / 'created', b'new created')
"""
    child = subprocess.run(
        [sys.executable, "-c", program, str(SCRIPTS), str(tmp_path), str(boundary)],
        timeout=20,
        check=False,
    )

    with store.transaction(tmp_path):
        first = (tmp_path / "first").read_bytes()
        second = (tmp_path / "second").read_bytes()
        created = (
            (tmp_path / "created").read_bytes()
            if (tmp_path / "created").exists()
            else None
        )

    assert child.returncode == 41
    expected = (
        (b"new first", b"new second", b"new created")
        if boundary >= 8
        else (b"old first", b"old second", None)
    )
    assert (first, second, created) == expected
    assert not (tmp_path / ".clara-transaction").exists()


def test_disk_write_failure_is_visible_and_restores_original(
    tmp_path: Path, store, monkeypatch: pytest.MonkeyPatch
) -> None:
    target = tmp_path / "source"
    target.write_bytes(b"original")
    original = store._raw_write

    def fail_target(path, content):
        if path == target:
            raise OSError(errno.ENOSPC, "synthetic disk full")
        return original(path, content)

    monkeypatch.setattr(store, "_raw_write", fail_target)

    with pytest.raises(OSError, match="disk full"):
        with store.transaction(tmp_path):
            store.atomic_bytes(target, b"changed")

    assert target.read_bytes() == b"original"
    assert not (tmp_path / ".clara-transaction").exists()


def test_root_alias_write_is_enlisted_and_rolled_back(tmp_path: Path, store) -> None:
    root = tmp_path / "actual"
    root.mkdir()
    alias = tmp_path / "alias"
    alias.symlink_to(root, target_is_directory=True)
    target = root / "source"
    target.write_bytes(b"original")

    with pytest.raises(RuntimeError, match="interrupt"):
        with store.transaction(alias):
            store.atomic_bytes(alias / "source", b"replacement")
            raise RuntimeError("interrupt")

    assert target.read_bytes() == b"original"
    assert not (root / ".clara-transaction").exists()


def test_root_alias_does_not_allow_internal_symlink_writes(
    tmp_path: Path, store
) -> None:
    root = tmp_path / "actual"
    root.mkdir()
    alias = tmp_path / "alias"
    alias.symlink_to(root, target_is_directory=True)
    outside = tmp_path / "outside"
    outside.mkdir()
    sentinel = outside / "source"
    sentinel.write_bytes(b"preserve")
    (root / "link").symlink_to(outside, target_is_directory=True)

    with pytest.raises(ValueError, match="symbolic link"):
        with store.transaction(alias):
            store.atomic_bytes(alias / "link/source", b"replacement")

    assert sentinel.read_bytes() == b"preserve"


@pytest.mark.parametrize("relative", ["../outside", "/tmp/outside", "link/source"])
def test_recovery_rejects_escaping_target_and_retains_journal(
    tmp_path: Path, store, relative: str
) -> None:
    import json

    root = tmp_path / "case"
    root.mkdir()
    outside = tmp_path / "outside"
    outside.mkdir()
    sentinel = outside / "source"
    sentinel.write_bytes(b"preserve")
    (root / "link").symlink_to(outside, target_is_directory=True)
    journal = root / ".clara-transaction"
    journal.mkdir()
    (journal / "journal.json").write_text(json.dumps({relative: None}))

    with pytest.raises(ValueError):
        with store.transaction(root):
            pytest.fail("Unsafe recovery must prevent the transaction body")

    assert sentinel.read_bytes() == b"preserve"
    assert journal.is_dir()


def test_recovery_can_resume_after_restorer_process_dies(tmp_path: Path, store) -> None:
    import json

    journal = tmp_path / ".clara-transaction"
    journal.mkdir()
    (journal / "journal.json").write_text(
        json.dumps({"first": "0.original", "second": "1.original"})
    )
    (journal / "0.original").write_bytes(b"old first")
    (journal / "1.original").write_bytes(b"old second")
    (tmp_path / "first").write_bytes(b"new first")
    (tmp_path / "second").write_bytes(b"new second")
    program = """
import os,sys
from pathlib import Path
sys.path.insert(0,sys.argv[1])
import case_store as store
original=store._restore_file
def crash(path, source):
    original(path,source)
    os._exit(42)
store._restore_file=crash
with store.transaction(Path(sys.argv[2])):
    raise AssertionError('must not reach operation')
"""
    child = subprocess.run(
        [sys.executable, "-c", program, str(SCRIPTS), str(tmp_path)],
        check=False,
        timeout=20,
    )

    with store.transaction(tmp_path):
        restored = (
            (tmp_path / "first").read_bytes(),
            (tmp_path / "second").read_bytes(),
        )

    assert child.returncode == 42
    assert restored == (b"old first", b"old second")
    assert not journal.exists()
