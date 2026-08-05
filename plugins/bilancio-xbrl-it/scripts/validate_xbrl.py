#!/usr/bin/env python3
"""Run pinned Arelle validation behind a replaceable subprocess interface."""

from __future__ import annotations

import argparse
import hashlib
import json
import logging
import shutil

# The validator runs one fixed local Arelle argv and never invokes a shell.
import subprocess  # nosec B404
import sys
import tempfile
from datetime import UTC, datetime
from pathlib import Path
from zipfile import BadZipFile, ZipFile

from defusedxml import ElementTree

__all__ = ["main", "validate_instance"]

LOGGER = logging.getLogger(__name__)
MAX_MEMBERS = 20_000
MAX_EXPANDED_BYTES = 512 * 1024 * 1024
XBRLI_NS = "http://www.xbrl.org/2003/instance"
LINK_NS = "http://www.xbrl.org/2003/linkbase"
XLINK_NS = "http://www.w3.org/1999/xlink"


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _safe_extract(package: Path, destination: Path) -> None:
    """Extract a bounded taxonomy ZIP without links or path traversal."""

    try:
        archive = ZipFile(package)
    except BadZipFile as exc:
        raise ValueError("Taxonomy package is not a readable ZIP archive") from exc
    with archive:
        members = archive.infolist()
        if len(members) > MAX_MEMBERS:
            raise ValueError("Taxonomy package has too many members")
        if sum(member.file_size for member in members) > MAX_EXPANDED_BYTES:
            raise ValueError("Taxonomy package exceeds the expanded-size limit")
        destination_resolved = destination.resolve()
        for member in members:
            relative = Path(member.filename)
            if relative.is_absolute() or ".." in relative.parts:
                raise ValueError("Taxonomy package contains an unsafe path")
            if (member.external_attr >> 16) & 0o170000 == 0o120000:
                raise ValueError("Taxonomy package contains a symbolic link")
            target = (destination / relative).resolve()
            if (
                target != destination_resolved
                and destination_resolved not in target.parents
            ):
                raise ValueError("Taxonomy member escapes the extraction directory")
            if member.is_dir():
                target.mkdir(parents=True, exist_ok=True)
                continue
            target.parent.mkdir(parents=True, exist_ok=True)
            with archive.open(member) as source, target.open("xb") as output:
                shutil.copyfileobj(source, output)


def _parse_log(log_file: Path) -> tuple[list[dict[str, str]], bool]:
    """Return Arelle messages and whether any validation error was recorded."""

    if not log_file.is_file():
        return [], True
    root = ElementTree.parse(log_file).getroot()
    messages: list[dict[str, str]] = []
    has_error = False
    for entry in root.iter():
        if entry.tag.rsplit("}", 1)[-1] != "entry":
            continue
        level = entry.attrib.get("level", "").lower()
        code = entry.attrib.get("code", "")
        text = " ".join("".join(entry.itertext()).split())
        messages.append({"level": level, "code": code, "message": text})
        if level in {
            "critical",
            "error",
            "error-semantic",
            "exception",
            "fatal",
            "assertion-not-satisfied",
            "inconsistency",
        }:
            has_error = True
    return messages, has_error


def _preflight_instance(instance: Path) -> list[dict[str, str]]:
    """Reject files that Arelle would otherwise treat as generic XML."""

    try:
        root = ElementTree.parse(instance).getroot()
    except ElementTree.ParseError as exc:
        return [{"level": "error", "code": "VERA.XML", "message": str(exc)}]
    errors: list[dict[str, str]] = []
    if root.tag != f"{{{XBRLI_NS}}}xbrl":
        errors.append(
            {
                "level": "error",
                "code": "VERA.XBRL_ROOT",
                "message": "The document root is not xbrli:xbrl.",
            }
        )
        return errors
    schema_refs = root.findall(f"{{{LINK_NS}}}schemaRef")
    if len(schema_refs) != 1:
        errors.append(
            {
                "level": "error",
                "code": "VERA.SCHEMA_REF",
                "message": "Exactly one link:schemaRef is required.",
            }
        )
    elif schema_refs[0].get(f"{{{XLINK_NS}}}type") != "simple" or not schema_refs[
        0
    ].get(f"{{{XLINK_NS}}}href"):
        errors.append(
            {
                "level": "error",
                "code": "VERA.SCHEMA_REF",
                "message": "The schemaRef must have xlink:type='simple' and a non-empty href.",
            }
        )
    if not root.findall(f"{{{XBRLI_NS}}}context"):
        errors.append(
            {
                "level": "error",
                "code": "VERA.CONTEXT",
                "message": "At least one XBRL context is required.",
            }
        )
    return errors


def validate_instance(
    instance: Path,
    report: Path,
    taxonomy_package: Path | None = None,
    expected_taxonomy_sha256: str | None = None,
) -> dict[str, object]:
    """Validate one local XBRL instance and persist the exact processor output."""

    if instance.is_symlink() or not instance.is_file():
        raise ValueError("XBRL instance must be a regular local file")
    if report.is_symlink():
        raise ValueError("Validation report must not be a symbolic link")
    if expected_taxonomy_sha256 and taxonomy_package is None:
        raise ValueError(
            "A taxonomy package is required when an expected checksum is supplied"
        )
    if taxonomy_package is not None:
        if taxonomy_package.is_symlink() or not taxonomy_package.is_file():
            raise ValueError("Taxonomy package must be a regular local file")
        actual_checksum = _sha256(taxonomy_package)
        if expected_taxonomy_sha256 and actual_checksum != expected_taxonomy_sha256:
            raise ValueError(
                "Taxonomy package checksum does not match the expected checksum"
            )
    else:
        actual_checksum = None

    preflight_messages = _preflight_instance(instance)

    with tempfile.TemporaryDirectory(prefix="vera-xbrl-validation-") as temporary:
        root = Path(temporary)
        if taxonomy_package is not None:
            _safe_extract(taxonomy_package, root)
        validation_instance = root / instance.name
        shutil.copy2(instance, validation_instance)
        log_file = root / "arelle-log.xml"
        cache_dir = root / "arelle-cache"
        try:
            import arelle
        except ImportError as exc:
            raise RuntimeError(
                "arelle-release is required for XBRL validation"
            ) from exc
        bundled_cache = Path(arelle.__file__).parent / "resources" / "cache"
        if bundled_cache.is_dir():
            shutil.copytree(bundled_cache, cache_dir)
        else:
            cache_dir.mkdir()
        command = [
            sys.executable,
            "-m",
            "arelle.CntlrCmdLine",
            "--disablePersistentConfig",
            "--cacheDirectory",
            str(cache_dir),
            "--file",
            str(validation_instance),
            "--validate",
            "--calc",
            "xbrl21",
            "--internetConnectivity",
            "offline",
            "--logFile",
            str(log_file),
            "--logFileMode",
            "w",
        ]
        # Every variable argv member is a validated path under this temporary run.
        completed = subprocess.run(  # nosec B603
            command,
            cwd=root,
            capture_output=True,
            check=False,
            text=True,
            timeout=120,
        )
        messages, has_validation_error = _parse_log(log_file)
        messages = [*preflight_messages, *messages]
        has_validation_error = has_validation_error or bool(preflight_messages)
    payload: dict[str, object] = {
        "schema_version": 1,
        "processor": "arelle-release",
        "command": [
            "python",
            "-m",
            "arelle.CntlrCmdLine",
            "--disablePersistentConfig",
            "--file",
            instance.name,
            "--validate",
            "--calc",
            "xbrl21",
            "--internetConnectivity",
            "offline",
        ],
        "taxonomy_package_sha256": actual_checksum,
        "returncode": completed.returncode,
        "status": (
            "PASS" if completed.returncode == 0 and not has_validation_error else "FAIL"
        ),
        "messages": messages,
        "stdout": completed.stdout,
        "stderr": completed.stderr,
        "validated_at": datetime.now(tz=UTC).replace(microsecond=0).isoformat(),
    }
    report.parent.mkdir(parents=True, exist_ok=True)
    report.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    return payload


def main(argv: list[str] | None = None) -> int:
    """Run Arelle validation and return nonzero when it fails."""

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("instance", type=Path)
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument("--taxonomy-package", type=Path)
    parser.add_argument("--expected-taxonomy-sha256")
    args = parser.parse_args(argv)
    try:
        result = validate_instance(
            args.instance,
            args.report,
            args.taxonomy_package,
            args.expected_taxonomy_sha256,
        )
        LOGGER.info("Arelle validation: %s", result["status"])
        return 0 if result["status"] == "PASS" else 1
    except (OSError, RuntimeError, subprocess.SubprocessError, ValueError) as exc:
        LOGGER.error("%s", exc)
        return 2


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    raise SystemExit(main())
