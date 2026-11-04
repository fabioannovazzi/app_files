#!/usr/bin/env python3
"""Retain a uniquely observed browser download, without interpreting bank data.

File identity, exclusive writes and hashes are deterministic because they prevent
attributing an old, concurrent or changing download to the current export. They
cannot establish the account, date coverage or meaning of a bank CSV.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import logging
import os
import stat
import tempfile
import time
from datetime import date
from pathlib import Path
from typing import Any

__all__ = ["start", "collect", "main"]

LOGGER = logging.getLogger(__name__)
PARTIAL_SUFFIXES = {".crdownload", ".part", ".partial", ".tmp"}
REQUEST_FIELDS = {"bank", "portal", "client", "account", "date_from", "date_to"}


def _signature(path: Path) -> list[int]:
    value = path.lstat()
    return [
        value.st_dev,
        value.st_ino,
        value.st_mode,
        value.st_size,
        value.st_mtime_ns,
        value.st_ctime_ns,
    ]


def _write_json(path: Path, value: Any) -> None:
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
        json.dump(value, stream, ensure_ascii=False, indent=2)
        stream.write("\n")


def _validate_request(request: dict[str, Any]) -> None:
    if set(request) != REQUEST_FIELDS or not all(
        isinstance(value, str) and value.strip() for value in request.values()
    ):
        raise ValueError("request requires exactly the six documented text fields")
    first, last = (date.fromisoformat(request[key]) for key in ("date_from", "date_to"))
    if (
        first.isoformat() != request["date_from"]
        or last.isoformat() != request["date_to"]
    ):
        raise ValueError("dates must use YYYY-MM-DD")
    if first > last:
        raise ValueError("date_from must not follow date_to")


def start(request: dict[str, Any], downloads: Path, run: Path) -> dict[str, Any]:
    """Save a private request and baseline without reading existing documents."""
    _validate_request(request)
    downloads = downloads.resolve(strict=True)
    if not downloads.is_dir():
        raise ValueError("downloads must be the browser's existing download directory")
    run = run.resolve()
    # Download originals must not become source files or published repository data.
    if any((parent / ".git").exists() for parent in (run, *run.parents)):
        raise ValueError("run outputs must be outside Git workspaces")
    run.mkdir(mode=0o700, parents=False, exist_ok=False)
    baseline = {path.name: _signature(path) for path in downloads.iterdir()}
    _write_json(
        run / "request.json",
        {"schema_version": "vera-bank-download/v1", "request": request},
    )
    _write_json(
        run / "baseline.json",
        {"downloads": str(downloads), "entries": baseline},
    )
    result = {
        "status": "awaiting_download",
        "byte_length": None,
        "sha256": None,
        "report_path": str(run / "REPORT.md"),
    }
    _report(run / "REPORT.md", result)
    return result


def _report(path: Path, result: dict[str, Any]) -> None:
    text = (
        "# Acquisizione bancaria — evidenza locale\n\n"
        f"Stato: `{result['status']}`\n\n"
        f"Byte conservati: {result['byte_length']}\n\n"
        f"SHA-256: `{result['sha256']}`\n\n"
        "Il file originale, se presente, è conservato nella stessa cartella. "
        "Il riferimento al cliente, conto e periodo è in request.json nella "
        "cartella principale del run.\n\n"
        "Questo controllo riguarda esclusivamente il file osservato localmente. "
        "Identità del conto, formato CSV, copertura del periodo e completezza "
        "dei movimenti richiedono la verifica separata di Vera sul portale "
        "e sul contenuto. Non sono attestati da questo rapporto.\n\n"
        "Il controllo locale non usa rete e non trasmette il file al modello. "
        "L'esposizione delle schermate durante computer use non è misurata "
        "da questo helper: il rapporto privacy del percorso resta separato.\n"
    )
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
        stream.write(text)


def _observe(
    downloads: Path, baseline: dict[str, list[int]]
) -> tuple[str, Path | None]:
    current = {path.name: _signature(path) for path in downloads.iterdir()}
    # An old partial disappearing could have completed under a new name.
    if any(
        Path(name).suffix.lower() in PARTIAL_SUFFIXES and name not in current
        for name in baseline
    ):
        return "ambiguous_download", None
    changed = [
        name
        for name in baseline.keys() & current.keys()
        if baseline[name] != current[name]
    ]
    if any(stat.S_ISREG(current[name][2]) for name in changed):
        return "existing_file_changed", None
    arrivals = sorted(current.keys() - baseline.keys())
    if any(Path(name).suffix.lower() in PARTIAL_SUFFIXES for name in arrivals):
        return "download_in_progress", None
    if not arrivals:
        return "no_new_file", None
    if len(arrivals) != 1:
        return "ambiguous_download", None
    path = downloads / arrivals[0]
    if not stat.S_ISREG(current[arrivals[0]][2]):
        return "not_a_regular_file", None
    return "candidate", path


def _retain(source: Path, target: Path) -> tuple[str, int | None, str | None]:
    before = _signature(source)
    descriptor = os.open(source, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
    digest = hashlib.sha256()
    size = 0
    with os.fdopen(descriptor, "rb") as incoming:
        opened = incoming.fileno()
        identity = os.fstat(opened)
        if not stat.S_ISREG(identity.st_mode) or (
            identity.st_dev,
            identity.st_ino,
        ) != tuple(before[:2]):
            return "file_changed", None, None
        outgoing_descriptor = os.open(
            target, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600
        )
        with os.fdopen(outgoing_descriptor, "wb") as outgoing:
            while chunk := incoming.read(1024 * 1024):
                digest.update(chunk)
                outgoing.write(chunk)
                size += len(chunk)
        after = os.fstat(opened)
    if (
        _signature(source) != before
        or after.st_size != size
        or after.st_mtime_ns != before[4]
        or after.st_ctime_ns != before[5]
    ):
        # Keep the partial evidence private, but never label it a retained original.
        target.rename(target.with_name("unverified-download.bin"))
        return "file_changed", None, None
    return "original_retained", size, digest.hexdigest()


def _existing_result(run: Path) -> dict[str, Any]:
    result = json.loads((run / "retained.json").read_text(encoding="utf-8"))
    directory = Path(result["report_path"]).parent
    if directory.parent != run:
        raise ValueError("retained report must belong to this run")
    originals = [path for path in directory.glob("original.*") if not path.is_symlink()]
    if len(originals) != 1:
        raise ValueError("retained original missing or ambiguous")
    original = originals[0]
    with original.open("rb") as stream:
        digest = hashlib.file_digest(stream, "sha256").hexdigest()
    if original.stat().st_size != result["byte_length"] or digest != result["sha256"]:
        raise ValueError("retained original changed")
    return result


def collect(run: Path) -> dict[str, Any]:
    """Retain one new file or persist a precise incomplete acquisition outcome."""
    run = run.resolve(strict=True)
    retained = run / "retained.json"
    if retained.exists():
        return _existing_result(run)
    lock = run / ".collect-lock"
    lock.mkdir(mode=0o700)
    try:
        # A second caller could have completed between the first check and the lock.
        if retained.exists():
            return _existing_result(run)
        baseline = json.loads((run / "baseline.json").read_text(encoding="utf-8"))
        attempt = Path(tempfile.mkdtemp(prefix="attempt-", dir=run))
        size, digest = None, None
        try:
            downloads = Path(baseline["downloads"])
            status, source = _observe(downloads, baseline["entries"])
            if source is not None:
                before = _signature(source)
                time.sleep(1)
                status, observed_again = _observe(downloads, baseline["entries"])
                if source != observed_again or before != _signature(source):
                    if status == "candidate":
                        status = "file_changed"
                    elif status == "no_new_file":
                        status = "file_unavailable"
                else:
                    # Preserve bytes, not a claimed CSV format. Extension is a hint.
                    suffix = ".csv" if source.suffix.lower() == ".csv" else ".bin"
                    status, size, digest = _retain(
                        source, attempt / f"original{suffix}"
                    )
        except OSError:
            status = "file_unavailable"
        result = {
            "status": status,
            "byte_length": size,
            "sha256": digest,
            "report_path": str(attempt / "REPORT.md"),
        }
        _report(attempt / "REPORT.md", result)
        _write_json(attempt / "result.json", result)
        if status == "original_retained":
            _write_json(retained, result)
        return result
    finally:
        lock.rmdir()


def main() -> int:
    """Expose local mechanics; never ask the model to read downloaded contents."""
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    prepare = commands.add_parser("start")
    prepare.add_argument("--request", required=True, type=Path)
    prepare.add_argument("--downloads", required=True, type=Path)
    prepare.add_argument("--run", required=True, type=Path)
    finish = commands.add_parser("collect")
    finish.add_argument("--run", required=True, type=Path)
    args = parser.parse_args()
    try:
        if args.command == "start":
            request = json.loads(args.request.read_text(encoding="utf-8"))
            result = start(request, args.downloads, args.run)
        else:
            result = collect(args.run)
    except (OSError, ValueError, KeyError, TypeError):
        # File paths, names and OS exception text can contain client references.
        LOGGER.error(
            "Local download evidence could not be saved; inspect the private run."
        )
        return 1
    LOGGER.info("%s", json.dumps(result, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    raise SystemExit(main())
