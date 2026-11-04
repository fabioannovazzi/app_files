"""Behavioral checks for local download attribution, not bank compatibility."""

from __future__ import annotations

import hashlib
import importlib.util
import json
import os
import stat
from pathlib import Path
from types import SimpleNamespace

import pytest

SCRIPT = (
    Path(__file__).resolve().parents[2] / "plugins/vera/scripts/bank_csv_download.py"
)


@pytest.fixture
def pilot(monkeypatch):
    spec = importlib.util.spec_from_file_location("bank_download_pilot", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    monkeypatch.setattr(module, "time", SimpleNamespace(sleep=lambda seconds: None))
    return module


def request():
    return {
        "bank": "Intesa Sanpaolo",
        "portal": "Inbiz",
        "client": "Synthetic client",
        "account": "Synthetic account",
        "date_from": "2026-10-01",
        "date_to": "2026-10-31",
    }


def prepare(pilot, tmp_path):
    downloads = tmp_path / "Downloads"
    downloads.mkdir()
    run = tmp_path / "run"
    pilot.start(request(), downloads, run)
    return downloads, run


def test_collect_preserves_exact_new_file_bytes_without_exposing_contents(
    pilot, tmp_path
):
    downloads, run = prepare(pilot, tmp_path)
    original = (
        b"Data;Importo;Descrizione\r\n01/10/2026;-1,23;Sensitive counterparty\r\n"
    )
    source = downloads / "client-account.csv"
    source.write_bytes(original)

    result = pilot.collect(run)

    retained = Path(result["report_path"]).parent / "original.csv"
    assert result["status"] == "original_retained"
    assert result["byte_length"] == len(original)
    assert result["sha256"] == hashlib.sha256(original).hexdigest()
    assert retained.read_bytes() == original
    assert source.read_bytes() == original
    assert "Sensitive counterparty" not in json.dumps(result)
    assert "client-account" not in json.dumps(result)
    assert "complete" not in result
    if os.name == "posix":
        assert stat.S_IMODE(retained.stat().st_mode) == 0o600
        assert stat.S_IMODE(run.stat().st_mode) == 0o700


def test_collect_never_accepts_preexisting_file(pilot, tmp_path):
    downloads = tmp_path / "Downloads"
    downloads.mkdir()
    (downloads / "old.csv").write_text("old private data")
    run = tmp_path / "run"
    pilot.start(request(), downloads, run)

    result = pilot.collect(run)

    assert result["status"] == "no_new_file"
    assert not list(run.rglob("original.*"))
    assert Path(result["report_path"]).exists()


@pytest.mark.parametrize("suffix", [".crdownload", ".part", ".partial", ".tmp"])
def test_collect_records_unfinished_download_without_copying(pilot, tmp_path, suffix):
    downloads, run = prepare(pilot, tmp_path)
    (downloads / f"movements.csv{suffix}").write_bytes(b"unfinished")

    result = pilot.collect(run)

    assert result["status"] == "download_in_progress"
    assert result["sha256"] is None
    assert not list(run.rglob("original.*"))


def test_collect_reports_concurrent_files_as_ambiguous(pilot, tmp_path):
    downloads, run = prepare(pilot, tmp_path)
    (downloads / "bank.csv").write_bytes(b"bank")
    (downloads / "unrelated.csv").write_bytes(b"other")

    result = pilot.collect(run)

    assert result["status"] == "ambiguous_download"
    assert not list(run.rglob("original.*"))
    assert "unrelated" not in json.dumps(result)


def test_collect_does_not_attribute_completion_of_old_partial(pilot, tmp_path):
    downloads = tmp_path / "Downloads"
    downloads.mkdir()
    partial = downloads / "old.csv.crdownload"
    partial.write_bytes(b"old")
    run = tmp_path / "run"
    pilot.start(request(), downloads, run)
    partial.rename(downloads / "old.csv")

    result = pilot.collect(run)

    assert result["status"] == "ambiguous_download"


def test_collect_accepts_new_file_despite_unchanged_old_partial(pilot, tmp_path):
    downloads = tmp_path / "Downloads"
    downloads.mkdir()
    (downloads / "old.csv.crdownload").write_bytes(b"old")
    run = tmp_path / "run"
    pilot.start(request(), downloads, run)
    (downloads / "new.csv").write_bytes(b"new")

    result = pilot.collect(run)

    assert result["status"] == "original_retained"


def test_collect_rejects_existing_file_overwrite(pilot, tmp_path):
    downloads = tmp_path / "Downloads"
    downloads.mkdir()
    old = downloads / "movements.csv"
    old.write_bytes(b"old")
    run = tmp_path / "run"
    pilot.start(request(), downloads, run)
    old.write_bytes(b"overwritten new export")

    result = pilot.collect(run)

    assert result["status"] == "existing_file_changed"
    assert not list(run.rglob("original.*"))


def test_collect_does_not_read_symlink_target(pilot, tmp_path):
    downloads, run = prepare(pilot, tmp_path)
    unrelated = tmp_path / "private.csv"
    unrelated.write_bytes(b"unrelated private data")
    try:
        (downloads / "bank.csv").symlink_to(unrelated)
    except OSError as error:
        if getattr(error, "winerror", None) == 1314:
            pytest.skip("This Windows account lacks symlink creation permission")
        raise

    result = pilot.collect(run)

    assert result["status"] == "not_a_regular_file"
    assert not list(run.rglob("original.*"))


def test_collect_retains_an_unknown_format_without_claiming_csv_validity(
    pilot, tmp_path
):
    downloads, run = prepare(pilot, tmp_path)
    (downloads / "export.xls").write_bytes(b"unknown binary")

    result = pilot.collect(run)

    assert result["status"] == "original_retained"
    assert (
        Path(result["report_path"]).parent / "original.bin"
    ).read_bytes() == b"unknown binary"


def test_collect_resumes_same_baseline_after_incomplete_attempt(pilot, tmp_path):
    downloads, run = prepare(pilot, tmp_path)
    pending = pilot.collect(run)
    (downloads / "movements.csv").write_bytes(b"completed")

    result = pilot.collect(run)

    assert result["status"] == "original_retained"
    assert Path(pending["report_path"]).exists()
    assert pending["report_path"] != result["report_path"]


def test_collect_reuses_retained_original_without_another_export(pilot, tmp_path):
    downloads, run = prepare(pilot, tmp_path)
    (downloads / "movements.csv").write_bytes(b"completed")
    previous = pilot.collect(run)
    (downloads / "unrelated-later.csv").write_bytes(b"later")

    result = pilot.collect(run)

    assert result == previous
    assert len(list(run.rglob("original.csv"))) == 1


def test_collect_detects_modified_retained_original(pilot, tmp_path):
    downloads, run = prepare(pilot, tmp_path)
    (downloads / "movements.csv").write_bytes(b"completed")
    previous = pilot.collect(run)
    (Path(previous["report_path"]).parent / "original.csv").write_bytes(b"tampered")

    with pytest.raises(ValueError, match="retained original changed"):
        pilot.collect(run)


def test_collect_detects_growth_during_stability_window(pilot, tmp_path, monkeypatch):
    downloads, run = prepare(pilot, tmp_path)
    source = downloads / "movements.csv"
    source.write_bytes(b"partial")
    monkeypatch.setattr(
        pilot,
        "time",
        SimpleNamespace(sleep=lambda seconds: source.write_bytes(b"finished")),
    )

    result = pilot.collect(run)

    assert result["status"] == "file_changed"
    assert not list(run.rglob("original.*"))


@pytest.mark.parametrize("descriptor_changes", [False, True])
def test_collect_compares_descriptor_timestamps_with_descriptor_observations(
    pilot, tmp_path, monkeypatch, descriptor_changes
):
    downloads, run = prepare(pilot, tmp_path)
    (downloads / "movements.csv").write_bytes(b"completed")
    fstat = os.fstat
    calls = 0

    def descriptor_stat(fd):
        nonlocal calls
        calls += 1
        observed = fstat(fd)
        return SimpleNamespace(
            st_mode=observed.st_mode,
            st_dev=observed.st_dev,
            st_ino=observed.st_ino,
            st_size=observed.st_size,
            st_mtime_ns=observed.st_mtime_ns,
            st_ctime_ns=observed.st_ctime_ns
            + 1_000_000
            + (calls if descriptor_changes else 0),
        )

    monkeypatch.setattr(pilot.os, "fstat", descriptor_stat)

    result = pilot.collect(run)

    assert result["status"] == (
        "file_changed" if descriptor_changes else "original_retained"
    )
    assert bool(list(run.rglob("original.csv"))) is not descriptor_changes


def test_collect_persists_report_when_download_disappears(pilot, tmp_path, monkeypatch):
    downloads, run = prepare(pilot, tmp_path)
    source = downloads / "movements.csv"
    source.write_bytes(b"partial")
    monkeypatch.setattr(
        pilot, "time", SimpleNamespace(sleep=lambda seconds: source.unlink())
    )

    result = pilot.collect(run)

    assert result["status"] == "file_unavailable"
    assert Path(result["report_path"]).is_file()


def test_start_preserves_run_on_repeated_request(pilot, tmp_path):
    downloads, run = prepare(pilot, tmp_path)
    original = (run / "request.json").read_bytes()

    with pytest.raises(FileExistsError):
        pilot.start(request(), downloads, run)

    assert (run / "request.json").read_bytes() == original


@pytest.mark.parametrize(
    "change",
    [{"date_from": "2026-11-01"}, {"date_from": "20261001"}, {"password": "secret"}],
)
def test_start_rejects_invalid_request_without_creating_run(pilot, tmp_path, change):
    downloads = tmp_path / "Downloads"
    downloads.mkdir()
    run = tmp_path / "run"

    with pytest.raises(ValueError):
        pilot.start(request() | change, downloads, run)

    assert not run.exists()


def test_start_keeps_downloaded_data_outside_git_workspaces(pilot, tmp_path):
    downloads = tmp_path / "Downloads"
    downloads.mkdir()
    repository = tmp_path / "repository"
    repository.mkdir()
    (repository / ".git").mkdir()

    with pytest.raises(ValueError, match="outside Git"):
        pilot.start(request(), downloads, repository / "run")

    assert not (repository / "run").exists()
