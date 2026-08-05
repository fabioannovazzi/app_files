#!/usr/bin/env python3
"""Run the official XBRL 2.1 conformance suite with pinned local Arelle."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import logging
import shutil
import subprocess  # nosec B404
import sys
from collections import Counter
from datetime import UTC, datetime
from importlib.metadata import version
from pathlib import Path

from validate_xbrl import _safe_extract

__all__ = ["main", "run_conformance"]

LOGGER = logging.getLogger(__name__)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _prepare_output(output_dir: Path) -> Path:
    if output_dir.is_symlink():
        raise ValueError("Conformance output must not be a symbolic link")
    output_dir.mkdir(parents=True, exist_ok=True)
    if any(output_dir.iterdir()):
        raise ValueError("Conformance output directory must be empty")
    return output_dir.resolve()


def run_conformance(
    suite_package: Path,
    expected_sha256: str,
    output_dir: Path,
) -> dict[str, object]:
    """Extract, execute, and checksum one official conformance-suite run."""

    if suite_package.is_symlink() or not suite_package.is_file():
        raise ValueError("Conformance suite must be a regular local ZIP file")
    actual_sha256 = _sha256(suite_package)
    if actual_sha256 != expected_sha256:
        raise ValueError("Conformance suite checksum does not match the registry")
    root = _prepare_output(output_dir)
    suite_root = root / "suite"
    suite_root.mkdir()
    _safe_extract(suite_package, suite_root)
    entry_points = list(suite_root.glob("*/xbrl.xml"))
    if len(entry_points) != 1:
        raise ValueError("Conformance suite must contain one top-level xbrl.xml")
    report = root / "test-report.csv"
    log = root / "arelle-log.txt"
    command = [
        sys.executable,
        "-m",
        "arelle.CntlrCmdLine",
        "--disablePersistentConfig",
        "--file",
        str(entry_points[0]),
        "--validate",
        "--calc",
        "xbrl21",
        "--internetConnectivity",
        "offline",
        "--testReport",
        str(report),
        "--logFile",
        str(log),
        "--logLevel",
        "error",
    ]
    completed = subprocess.run(  # nosec B603
        command,
        cwd=root,
        capture_output=True,
        check=False,
        text=True,
        timeout=300,
    )
    if not report.is_file() or not log.is_file():
        raise RuntimeError("Arelle did not produce conformance report artifacts")
    with report.open(newline="", encoding="utf-8-sig") as handle:
        rows = list(csv.DictReader(handle))
    if not rows or "Status" not in rows[0]:
        raise RuntimeError("Arelle conformance report has no variation statuses")
    statuses = Counter(str(row["Status"]).lower() for row in rows)
    failures = [
        {
            key: row.get(key, "")
            for key in ("Testcase", "Id", "Name", "Expected", "Actual", "Status")
        }
        for row in rows
        if str(row["Status"]).lower() != "pass"
    ]
    payload: dict[str, object] = {
        "schema_version": 1,
        "suite_id": suite_package.stem,
        "suite_sha256": actual_sha256,
        "processor": "arelle-release",
        "processor_version": version("arelle-release"),
        "processor_mode": "XBRL_2.1_CALCULATIONS",
        "offline": True,
        "variation_count": len(rows),
        "passed_count": statuses["pass"],
        "failed_count": len(rows) - statuses["pass"],
        "status": (
            "PASS"
            if completed.returncode == 0 and statuses["pass"] == len(rows)
            else "FAIL"
        ),
        "failures": failures,
        "report": {"file_name": report.name, "sha256": _sha256(report)},
        "log": {"file_name": log.name, "sha256": _sha256(log)},
        "returncode": completed.returncode,
        "stdout": completed.stdout,
        "stderr": completed.stderr,
        "completed_at": datetime.now(tz=UTC).replace(microsecond=0).isoformat(),
    }
    manifest = root / "conformance-manifest.json"
    manifest.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    payload["manifest_sha256"] = _sha256(manifest)
    if payload["status"] == "PASS":
        shutil.rmtree(suite_root)
    return payload


def main(argv: list[str] | None = None) -> int:
    """Run the conformance suite from the command line."""

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--suite-package", type=Path, required=True)
    parser.add_argument("--expected-sha256", required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        result = run_conformance(
            args.suite_package, args.expected_sha256, args.output_dir
        )
    except (OSError, RuntimeError, subprocess.SubprocessError, ValueError) as exc:
        LOGGER.error("%s", exc)
        return 2
    sys.stdout.write(json.dumps(result, ensure_ascii=False, indent=2) + "\n")
    return 0 if result["status"] == "PASS" else 1


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    raise SystemExit(main())
