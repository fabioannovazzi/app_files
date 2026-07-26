from __future__ import annotations

import sys as _bootstrap_sys  # isort: skip

_bootstrap_sys.dont_write_bytecode = True
_bootstrap_sys.pycache_prefix = (
    r"Z:\__journal_bank_no_bytecode__"
    if _bootstrap_sys.platform == "win32"
    else "/dev/null/journal-bank-reconciliation"
)

import os as _bootstrap_os  # isort: skip

_BOOTSTRAP_PATH = _bootstrap_os.path.join(
    _bootstrap_os.path.dirname(_bootstrap_os.path.abspath(__file__)),
    "implementation_bootstrap.py",
)
_BOOTSTRAP_ENTRY = _bootstrap_os.lstat(_BOOTSTRAP_PATH)
if _BOOTSTRAP_ENTRY.st_mode & 0o170000 != 0o100000 or _BOOTSTRAP_ENTRY.st_nlink != 1:
    raise RuntimeError("Journal–Bank implementation bootstrap is not a real file.")
with open(_BOOTSTRAP_PATH, "rb") as _bootstrap_handle:
    _BOOTSTRAP_BEFORE = _bootstrap_os.fstat(_bootstrap_handle.fileno())
    _BOOTSTRAP_BYTES = _bootstrap_handle.read()
    _BOOTSTRAP_AFTER = _bootstrap_os.fstat(_bootstrap_handle.fileno())
_BOOTSTRAP_IDENTITY = (
    _BOOTSTRAP_ENTRY.st_dev,
    _BOOTSTRAP_ENTRY.st_ino,
    _BOOTSTRAP_ENTRY.st_size,
    _BOOTSTRAP_ENTRY.st_mtime_ns,
)
if (
    _BOOTSTRAP_IDENTITY
    != (
        _BOOTSTRAP_BEFORE.st_dev,
        _BOOTSTRAP_BEFORE.st_ino,
        _BOOTSTRAP_BEFORE.st_size,
        _BOOTSTRAP_BEFORE.st_mtime_ns,
    )
    or _BOOTSTRAP_IDENTITY
    != (
        _BOOTSTRAP_AFTER.st_dev,
        _BOOTSTRAP_AFTER.st_ino,
        _BOOTSTRAP_AFTER.st_size,
        _BOOTSTRAP_AFTER.st_mtime_ns,
    )
    or len(_BOOTSTRAP_BYTES) != _BOOTSTRAP_AFTER.st_size
):
    raise RuntimeError("Journal–Bank implementation bootstrap changed while read.")
_BOOTSTRAP_NAMESPACE = {
    "__file__": _BOOTSTRAP_PATH,
    "__name__": "_journal_bank_implementation_bootstrap",
}
# The exact stable single-link bootstrap source is verified above.
exec(  # nosec B102
    compile(_BOOTSTRAP_BYTES, _BOOTSTRAP_PATH, "exec"), _BOOTSTRAP_NAMESPACE
)
_BOOTSTRAP_NAMESPACE["activate_implementation_boundary"]()
_SCRIPTS_DIR = _bootstrap_os.path.dirname(_bootstrap_os.path.abspath(__file__))
if _SCRIPTS_DIR not in _bootstrap_sys.path:
    _bootstrap_sys.path.insert(0, _SCRIPTS_DIR)

import argparse
import csv
import hashlib
import io
import json
import os
import re
import stat
import sys
import tempfile
from datetime import date
from pathlib import Path
from typing import Any

import openpyxl
from excel_sanitization import excel_safe_value

_COMPONENT_ROOT = Path(__file__).resolve().parents[1]
_VENDOR_CANDIDATES = (
    _COMPONENT_ROOT / "vendor" / "modules",
    _COMPONENT_ROOT.parent.parent / "vendor" / "modules",
    _COMPONENT_ROOT.parent / "_shared" / "vendor" / "modules",
)
for _vendor_candidate in _VENDOR_CANDIDATES:
    if (_vendor_candidate / "vera_assurance").is_dir():
        if str(_vendor_candidate) not in sys.path:
            sys.path.insert(0, str(_vendor_candidate))
        break

from journal_bank_core import (  # noqa: E402
    build_implementation_artifact_receipts,
    implementation_artifact_roots,
    validate_exact_implementation_receipts,
)
from vera_assurance import (  # noqa: E402
    artifact_receipt,
    build_assurance_envelope,
    build_gate_register,
    build_reviewed_decision_receipt,
    canonical_json_sha256,
    validate_allocation_ledger,
    validate_artifact_receipt,
    validate_assurance_envelope,
    validate_gate_register,
    validate_reviewed_decision_receipt,
    validate_source_qualification,
)

__all__ = ["apply_review_edits", "main", "preflight_review_application"]

REGENERATE_NATIVE_OUTPUT_ACTION = (
    "Regenerate native DOCX/XLSX/PDF outputs before final handoff."
)
FINAL_HANDOFF_ACTION = (
    "Use final_artifacts.json as the reviewed artifact gallery for handoff."
)
COMPLETE_REVIEW_ACTION = "Complete remaining review decisions before final handoff."
RESOLVE_ASSURANCE_ACTION = (
    "Resolve withheld or failed assurance gates before final handoff."
)

WORKBOOK_SHEETS = {
    "matches": "reconciliation_matches.csv",
    "relationship_residuals": "relationship_residuals.csv",
    "unmatched_bank": "unmatched_bank.csv",
    "unmatched_journal": "unmatched_journal.csv",
    "bank_pdf_non_movements": "bank_pdf_non_movement_rows.csv",
    "normalized_bank": "normalized_bank.csv",
    "normalized_journal": "normalized_journal.csv",
}

STANDARD_RECEIPT_PATHS = {
    "normalized_bank.csv": "output.normalized_bank_csv",
    "normalized_journal.csv": "output.normalized_journal_csv",
    "reconciliation_matches.csv": "output.reconciliation_matches_csv",
    "relationship_residuals.csv": "output.relationship_residuals_csv",
    "unmatched_bank.csv": "output.unmatched_bank_csv",
    "unmatched_journal.csv": "output.unmatched_journal_csv",
    "bank_pdf_non_movement_rows.csv": "output.bank_pdf_non_movement_rows_csv",
    "journal_bank_reconciliation.xlsx": "output.workbook_xlsx",
    "reconciliation_audit.json": "output.audit_json",
    "review_notes.md": "output.review_notes_md",
    "source_qualifications.json": "output.source_qualifications_json",
    "reviewed_decisions.json": "output.reviewed_decisions_json",
    "lineage.json": "output.lineage_json",
    "relationship_ledger.json": "output.relationship_ledger_json",
    "material_value_ledger.json": "output.material_value_ledger_json",
    "assurance_gates.json": "output.assurance_gates_json",
    "review_payload.json": "output.review_payload_json",
    "ui_decisions.json": "output.ui_decisions_json",
    "applied_decisions.json": "output.applied_decisions_json",
    "final_artifacts.json": "output.final_artifacts_json",
    "run_intake.json": "output.run_intake_json",
    "assurance_envelope.json": "output.assurance_envelope_json",
    "assurance_envelope.reviewed.json": "output.assurance_envelope_reviewed_json",
    "review_baseline_replay.json": "output.review_baseline_replay_json",
}

BASELINE_REPLAY_PATH = "review_baseline_replay.json"
ORIGINAL_ENVELOPE_PATH = "assurance_envelope.json"
REVIEWED_ENVELOPE_PATH = "assurance_envelope.reviewed.json"
REVIEW_ADAPTER_ID = "journal_bank.review_application"
REVIEW_ADAPTER_VERSION = "1"
IDENTIFIER_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")


def clean_text(value: object) -> str:
    """Return a stripped string for safe JSON field comparison."""

    return value.strip() if isinstance(value, str) else ""


def _absolute_path_without_following(path: Path) -> Path:
    """Return an absolute lexical path without resolving filesystem links."""

    return Path(os.path.abspath(path.expanduser()))


def _lstat_or_none(path: Path) -> os.stat_result | None:
    """Return one entry's no-follow stat, or ``None`` when it is absent."""

    try:
        return path.lstat()
    except FileNotFoundError:
        return None


def _validate_real_directory_ancestors(path: Path) -> None:
    """Reject a symlink or non-directory in an existing directory chain."""

    absolute = _absolute_path_without_following(path)
    current = Path(absolute.anchor)
    for component in absolute.parts[1:]:
        current /= component
        current_stat = _lstat_or_none(current)
        if current_stat is None:
            raise ValueError("output directory parent must already exist")
        if stat.S_ISLNK(current_stat.st_mode) or not stat.S_ISDIR(current_stat.st_mode):
            raise ValueError("output directory parent must be a real directory")


def _validate_output_tree(output_dir: Path) -> Path:
    """Reject links, aliases, and special entries in a transaction tree."""

    output_dir = _absolute_path_without_following(output_dir)
    _validate_real_directory_ancestors(output_dir)
    root_stat = _lstat_or_none(output_dir)
    if (
        root_stat is None
        or stat.S_ISLNK(root_stat.st_mode)
        or not stat.S_ISDIR(root_stat.st_mode)
    ):
        raise ValueError("output directory must be a real directory")

    pending = [output_dir]
    while pending:
        current = pending.pop()
        try:
            entries = list(os.scandir(current))
        except FileNotFoundError as exc:
            raise ValueError("output directory changed during validation") from exc
        for entry in entries:
            try:
                entry_stat = entry.stat(follow_symlinks=False)
            except FileNotFoundError as exc:
                raise ValueError("output directory changed during validation") from exc
            if stat.S_ISLNK(entry_stat.st_mode):
                raise ValueError("output directory cannot contain symbolic links")
            if stat.S_ISDIR(entry_stat.st_mode):
                pending.append(Path(entry.path))
                continue
            if not stat.S_ISREG(entry_stat.st_mode):
                raise ValueError(
                    "output directory cannot contain special filesystem entries"
                )
            if entry_stat.st_nlink != 1:
                raise ValueError("output directory cannot contain hardlink aliases")
    return output_dir


def _validate_run_file(output_dir: Path, path: Path, label: str) -> Path:
    """Return one contained, regular, single-link run file."""

    candidate = _absolute_path_without_following(path)
    if not candidate.is_relative_to(output_dir):
        raise ValueError(f"{label} must stay inside the run output")
    _validate_real_directory_ancestors(candidate.parent)
    candidate_stat = _lstat_or_none(candidate)
    if candidate_stat is None:
        raise FileNotFoundError(candidate)
    if stat.S_ISLNK(candidate_stat.st_mode):
        raise ValueError(f"{label} cannot be a symbolic link")
    if not stat.S_ISREG(candidate_stat.st_mode):
        raise ValueError(f"{label} must be a regular file")
    if candidate_stat.st_nlink != 1:
        raise ValueError(f"{label} cannot have hardlink aliases")
    return candidate


def _validate_canonical_output_slot(
    output_dir: Path,
    canonical_output_dir: Path | None,
) -> Path:
    """Validate the canonical peer used by an MCP staging transaction."""

    if canonical_output_dir is None:
        return output_dir
    canonical = _absolute_path_without_following(canonical_output_dir)
    if canonical == output_dir:
        return canonical
    _validate_real_directory_ancestors(canonical.parent)
    canonical_stat = _lstat_or_none(canonical)
    if canonical_stat is not None and (
        stat.S_ISLNK(canonical_stat.st_mode) or not stat.S_ISDIR(canonical_stat.st_mode)
    ):
        raise ValueError("canonical output path must be a real directory")
    # The parent transaction retains and later verifies the exact trusted
    # canonical image; this child only validates the peer path shape.
    return canonical


def _read_bytes(path: Path) -> bytes:
    """Read one regular single-link leaf without following the leaf itself."""

    _validate_real_directory_ancestors(path.parent)
    parent_flags = os.O_RDONLY
    parent_flags |= getattr(os, "O_DIRECTORY", 0)
    parent_flags |= getattr(os, "O_NOFOLLOW", 0)
    parent_fd = os.open(path.parent, parent_flags)
    descriptor: int | None = None
    try:
        file_flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
        descriptor = os.open(path.name, file_flags, dir_fd=parent_fd)
        file_stat = os.fstat(descriptor)
        if not stat.S_ISREG(file_stat.st_mode):
            raise ValueError(f"refusing to read special entry: {path.name}")
        if file_stat.st_nlink != 1:
            raise ValueError(f"refusing to read hardlink alias: {path.name}")
        chunks: list[bytes] = []
        while True:
            chunk = os.read(descriptor, 1024 * 1024)
            if not chunk:
                break
            chunks.append(chunk)
        return b"".join(chunks)
    finally:
        if descriptor is not None:
            os.close(descriptor)
        os.close(parent_fd)


def _atomic_write_bytes(path: Path, payload: bytes) -> None:
    """Replace one leaf without following links or mutating hardlink aliases."""

    _validate_real_directory_ancestors(path.parent)
    parent_flags = os.O_RDONLY
    parent_flags |= getattr(os, "O_DIRECTORY", 0)
    parent_flags |= getattr(os, "O_NOFOLLOW", 0)
    parent_fd = os.open(path.parent, parent_flags)
    temp_name = f".{path.name}.journal-bank-write-{os.getpid()}-{os.urandom(8).hex()}"
    temp_fd: int | None = None
    temp_exists = False
    try:
        existing_mode = 0o644
        try:
            existing = os.stat(path.name, dir_fd=parent_fd, follow_symlinks=False)
        except FileNotFoundError:
            existing = None
        if existing is not None:
            if stat.S_ISLNK(existing.st_mode):
                raise ValueError(f"refusing to replace symbolic link: {path.name}")
            if not stat.S_ISREG(existing.st_mode):
                raise ValueError(f"refusing to replace special entry: {path.name}")
            if existing.st_nlink != 1:
                raise ValueError(f"refusing to replace hardlink alias: {path.name}")
            existing_mode = stat.S_IMODE(existing.st_mode)

        file_flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
        file_flags |= getattr(os, "O_NOFOLLOW", 0)
        temp_fd = os.open(
            temp_name,
            file_flags,
            existing_mode,
            dir_fd=parent_fd,
        )
        temp_exists = True
        view = memoryview(payload)
        while view:
            written = os.write(temp_fd, view)
            if written <= 0:
                raise OSError("atomic review write made no progress")
            view = view[written:]
        os.fsync(temp_fd)
        os.close(temp_fd)
        temp_fd = None

        try:
            current = os.stat(path.name, dir_fd=parent_fd, follow_symlinks=False)
        except FileNotFoundError:
            current = None
        if current is not None:
            if stat.S_ISLNK(current.st_mode):
                raise ValueError(f"refusing to replace symbolic link: {path.name}")
            if not stat.S_ISREG(current.st_mode):
                raise ValueError(f"refusing to replace special entry: {path.name}")
            if current.st_nlink != 1:
                raise ValueError(f"refusing to replace hardlink alias: {path.name}")
        os.replace(
            temp_name,
            path.name,
            src_dir_fd=parent_fd,
            dst_dir_fd=parent_fd,
        )
        temp_exists = False
        os.fsync(parent_fd)
    finally:
        if temp_fd is not None:
            os.close(temp_fd)
        if temp_exists:
            try:
                os.unlink(temp_name, dir_fd=parent_fd)
            except FileNotFoundError:
                pass
        os.close(parent_fd)


def _read_json(path: Path) -> dict[str, Any]:
    payload = json.loads(_read_bytes(path).decode("utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"Expected JSON object: {path}")
    return payload


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    _atomic_write_bytes(
        path,
        (json.dumps(payload, ensure_ascii=False, indent=2) + "\n").encode("utf-8"),
    )


def _canonical_relative_path(value: object) -> str | None:
    text = clean_text(value)
    if not text:
        return None
    path = Path(text)
    if path.is_absolute() or ".." in path.parts or "\\" in text:
        raise ValueError(f"Review artifact path must be canonical: {text!r}")
    return path.as_posix()


def _authorized_changed_paths(
    *,
    applied_decisions_path: Path,
    final_artifacts_path: Path,
    output_dir: Path,
    verified_changed_paths: set[str],
) -> set[str]:
    paths = {
        "ui_decisions.json",
        "run_intake.json",
        BASELINE_REPLAY_PATH,
        *verified_changed_paths,
    }
    for path in (applied_decisions_path, final_artifacts_path):
        try:
            paths.add(path.relative_to(output_dir).as_posix())
        except ValueError:
            continue
    return paths


def _source_roots(output_dir: Path) -> dict[str, Path]:
    audit_path = output_dir / "reconciliation_audit.json"
    if not audit_path.is_file():
        return {}
    audit = _read_json(audit_path)
    run_intake_path = output_dir / "run_intake.json"
    run_intake = (
        _read_json(run_intake_path)
        if _lstat_or_none(run_intake_path) is not None
        else {}
    )
    canonical_output_value = clean_text(run_intake.get("output_dir"))
    canonical_output = (
        _absolute_path_without_following(Path(canonical_output_value))
        if canonical_output_value
        else None
    )
    roots: dict[str, Path] = {
        "run": output_dir,
        **implementation_artifact_roots(),
    }
    for side, field in (
        ("bank", "bank_path"),
        ("journal", "journal_path"),
        ("sample", "sample_path"),
    ):
        value = clean_text(audit.get(field))
        if not value:
            continue
        source = _absolute_path_without_following(Path(value))
        if canonical_output is not None and source.is_relative_to(canonical_output):
            source = output_dir / source.relative_to(canonical_output)
        roots[f"source_{side}"] = source if source.is_dir() else source.parent
    return roots


def preflight_review_application(output_dir: Path) -> dict[str, Any]:
    """Replay the immutable run envelope before any review mutation."""

    output_dir = _validate_output_tree(output_dir)
    envelope_path = _validate_run_file(
        output_dir,
        output_dir / ORIGINAL_ENVELOPE_PATH,
        "original assurance envelope",
    )
    roots = _source_roots(output_dir)
    if not roots:
        raise ValueError("Artifact roots cannot be reconstructed from the run audit.")
    raw_envelope = _read_json(envelope_path)
    validate_exact_implementation_receipts(
        raw_envelope,
        artifact_roots=roots,
    )
    envelope = validate_assurance_envelope(raw_envelope, artifact_roots=roots)
    content = {
        "schema_version": "journal_bank.review_baseline_replay.v1",
        "run_id": envelope["run_id"],
        "envelope_path": ORIGINAL_ENVELOPE_PATH,
        "envelope_content_sha256": envelope["content_sha256"],
        "replayed_on": date.today().isoformat(),
        "artifact_snapshots": [
            {
                "artifact_id": receipt["artifact_id"],
                "root_id": receipt["root_id"],
                "path": receipt["path"],
                "byte_count": receipt["byte_count"],
                "sha256": receipt["sha256"],
            }
            for receipt in envelope["artifact_receipts"]
        ],
    }
    payload = {**content, "content_sha256": canonical_json_sha256(content)}
    _write_json(output_dir / BASELINE_REPLAY_PATH, payload)
    _validate_output_tree(output_dir)
    return payload


def _baseline_replay(output_dir: Path) -> tuple[dict[str, Any], dict[str, Any]]:
    replay_path = output_dir / BASELINE_REPLAY_PATH
    envelope_path = output_dir / ORIGINAL_ENVELOPE_PATH
    if not replay_path.is_file():
        raise ValueError(
            "Review baseline replay is missing; run preflight before any mutation."
        )
    if not envelope_path.is_file():
        raise ValueError("Original assurance envelope is missing.")
    replay = _read_json(replay_path)
    required = {
        "schema_version",
        "run_id",
        "envelope_path",
        "envelope_content_sha256",
        "replayed_on",
        "artifact_snapshots",
        "content_sha256",
    }
    if set(replay) != required:
        raise ValueError("Review baseline replay fields are invalid.")
    content = {key: replay[key] for key in replay if key != "content_sha256"}
    if replay["content_sha256"] != canonical_json_sha256(content):
        raise ValueError("Review baseline replay digest is stale.")
    envelope = _read_json(envelope_path)
    envelope_content = {
        key: envelope[key] for key in envelope if key != "content_sha256"
    }
    if envelope.get("content_sha256") != canonical_json_sha256(envelope_content):
        raise ValueError("Original assurance envelope digest is stale.")
    if replay["envelope_content_sha256"] != envelope["content_sha256"]:
        raise ValueError("Review baseline replay references a different envelope.")
    if replay["run_id"] != envelope.get("run_id"):
        raise ValueError("Review baseline replay run ID is stale.")
    return replay, envelope


def _receipt_bundle(output_dir: Path) -> dict[str, Any] | None:
    path = output_dir / "artifact_receipts.json"
    if not path.is_file():
        return None
    payload = _read_json(path)
    source_receipts = payload.get("source_receipts")
    output_receipts = payload.get("output_receipts")
    if not isinstance(source_receipts, list) or not isinstance(output_receipts, list):
        raise ValueError("artifact_receipts.json has an invalid receipt collection")
    return payload


def _receipt_integrity_errors(
    output_dir: Path,
    *,
    authorized_changed_paths: set[str],
) -> list[str]:
    try:
        bundle = _receipt_bundle(output_dir)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        return [f"Artifact receipt bundle is invalid: {exc}"]
    if bundle is None:
        return ["Artifact receipt bundle is missing."]
    errors: list[str] = []
    roots = _source_roots(output_dir)
    for receipt in bundle["source_receipts"]:
        if not isinstance(receipt, dict):
            errors.append("A source artifact receipt is not an object.")
            continue
        try:
            validate_artifact_receipt(roots, receipt)
        except (OSError, ValueError) as exc:
            errors.append(
                f"Source receipt {receipt.get('artifact_id', '<unknown>')} failed: {exc}"
            )
    for receipt in bundle["output_receipts"]:
        if not isinstance(receipt, dict):
            errors.append("An output artifact receipt is not an object.")
            continue
        if clean_text(receipt.get("path")) in authorized_changed_paths:
            continue
        try:
            validate_artifact_receipt(output_dir, receipt)
        except (OSError, ValueError) as exc:
            errors.append(
                f"Output receipt {receipt.get('artifact_id', '<unknown>')} failed: {exc}"
            )
    return errors


def _reseal_artifact_receipts(output_dir: Path) -> dict[str, Any]:
    previous = _receipt_bundle(output_dir)
    source_receipts = list(previous["source_receipts"]) if previous is not None else []
    previous_by_path = (
        {
            clean_text(receipt.get("path")): receipt
            for receipt in previous["output_receipts"]
            if isinstance(receipt, dict) and clean_text(receipt.get("path"))
        }
        if previous is not None
        else {}
    )
    paths = set(previous_by_path)
    paths.update(
        relative
        for relative in STANDARD_RECEIPT_PATHS
        if (output_dir / relative).is_file()
    )
    output_receipts: list[dict[str, Any]] = []
    for relative in sorted(paths):
        path = output_dir / relative
        if not path.is_file():
            continue
        prior = previous_by_path.get(relative, {})
        artifact_id = clean_text(
            prior.get("artifact_id")
        ) or STANDARD_RECEIPT_PATHS.get(relative)
        if artifact_id is None:
            continue
        kwargs: dict[str, Any] = {}
        if clean_text(prior.get("media_type")):
            kwargs["media_type"] = clean_text(prior["media_type"])
        output_receipts.append(
            artifact_receipt(
                output_dir,
                path,
                artifact_id=artifact_id,
                root_id=clean_text(prior.get("root_id")) or "run",
                role=clean_text(prior.get("role"))
                or f"journal-bank reconciliation {Path(relative).stem}",
                **kwargs,
            )
        )
    payload = {
        "schema_version": "journal_bank.artifact_receipts.v1",
        "source_receipts": source_receipts,
        "output_receipts": output_receipts,
    }
    _write_json(output_dir / "artifact_receipts.json", payload)
    for receipt in output_receipts:
        validate_artifact_receipt(output_dir, receipt)
    return payload


def _write_reviewed_assurance_envelope(
    output_dir: Path,
    receipt_bundle: dict[str, Any],
) -> dict[str, Any]:
    original = _read_json(output_dir / ORIGINAL_ENVELOPE_PATH)
    decisions_payload = _read_json(output_dir / "reviewed_decisions.json")
    qualifications_payload = _read_json(output_dir / "source_qualifications.json")
    gates = validate_gate_register(_read_json(output_dir / "assurance_gates.json"))
    decisions = [
        validate_reviewed_decision_receipt(value)
        for value in decisions_payload.get("decisions", [])
    ]
    qualifications = [
        validate_source_qualification(value)
        for value in qualifications_payload.get("qualifications", [])
    ]
    implementation_receipts = build_implementation_artifact_receipts()
    excluded_paths = {"artifact_receipts.json", REVIEWED_ENVELOPE_PATH}
    output_receipts = [
        receipt
        for receipt in receipt_bundle["output_receipts"]
        if clean_text(receipt.get("path")) not in excluded_paths
    ]
    limitations = [
        limitation
        for gate in gates["gates"].values()
        if gate["status"] not in {"passed", "not_applicable"}
        for limitation in gate["limitations"]
    ]
    envelope = build_assurance_envelope(
        run_id=str(original["run_id"]),
        workflow_id=str(original["workflow_id"]),
        workflow_version=str(original["workflow_version"]),
        artifact_receipts=[
            *receipt_bundle["source_receipts"],
            *implementation_receipts,
            *output_receipts,
        ],
        implementation_artifact_refs=[
            receipt["artifact_id"] for receipt in implementation_receipts
        ],
        reviewed_decisions=decisions,
        source_qualifications=qualifications,
        allocation_ledgers=[],
        numeric_evidence_ledgers=[],
        gate_register=gates,
        limitations=list(dict.fromkeys(limitations)),
        artifact_roots=_source_roots(output_dir),
    )
    _write_json(output_dir / REVIEWED_ENVELOPE_PATH, envelope)
    roots = _source_roots(output_dir)
    validate_exact_implementation_receipts(
        envelope,
        artifact_roots=roots,
    )
    return validate_assurance_envelope(envelope, artifact_roots=roots)


def _receipt_bundle_replay_errors(
    output_dir: Path,
    payload: dict[str, Any],
) -> list[str]:
    errors: list[str] = []
    roots = _source_roots(output_dir)
    for receipt in payload.get("source_receipts", []):
        try:
            validate_artifact_receipt(roots, receipt)
        except (OSError, ValueError) as exc:
            errors.append(
                f"Source receipt {receipt.get('artifact_id', '<unknown>')} failed: {exc}"
            )
    for receipt in payload.get("output_receipts", []):
        try:
            validate_artifact_receipt(output_dir, receipt)
        except (OSError, ValueError) as exc:
            errors.append(
                f"Output receipt {receipt.get('artifact_id', '<unknown>')} failed: {exc}"
            )
    return errors


def _eligible_reconciliation_effect(effect: dict[str, Any]) -> bool:
    """Return whether a structured match edit should refresh the workbook."""

    if effect.get("action") != "edit":
        return False
    if effect.get("artifact_update") != "structured_artifact_updated":
        return False
    if clean_text(effect.get("target_artifact")) != "reconciliation_matches.csv":
        return False
    paths = effect.get("derived_native_regeneration_paths")
    if paths != ["journal_bank_reconciliation.xlsx"]:
        return False
    update = effect.get("structured_update")
    if not isinstance(update, dict):
        return False
    if clean_text(update.get("id_field")) != "bank_transaction_id":
        return False
    if clean_text(update.get("target_field")) != "review_note":
        return False
    record_id = clean_text(update.get("record_id"))
    if not record_id or clean_text(effect.get("edit_value")) == "":
        return False
    if clean_text(effect.get("target_id_field")) != "bank_transaction_id":
        return False
    if clean_text(effect.get("target_record_id")) != record_id:
        return False
    if clean_text(effect.get("target_field")) != "review_note":
        return False
    updated_rows = update.get("updated_rows")
    if updated_rows is not None and updated_rows != 1:
        return False
    return True


def _safe_item_id(value: object) -> str:
    text = clean_text(value) or "item"
    cleaned = "".join(char if char.isalnum() or char in "._-" else "-" for char in text)
    return cleaned.strip("-") or "item"


def _backup_native(output_dir: Path, item_id: str, target_name: str) -> dict[str, Any]:
    source = output_dir / target_name
    source_stat = _lstat_or_none(source)
    if source_stat is None:
        return {}
    if (
        stat.S_ISLNK(source_stat.st_mode)
        or not stat.S_ISREG(source_stat.st_mode)
        or source_stat.st_nlink != 1
    ):
        raise ValueError("native review source must be a regular single-link file")
    suffix = source.suffix or ".xlsx"
    relative = (
        Path("revisions")
        / "originals"
        / f"{source.stem}__{_safe_item_id(item_id)}{suffix}"
    )
    target = output_dir / relative
    target.parent.mkdir(parents=True, exist_ok=True)
    if _lstat_or_none(target) is None:
        _atomic_write_bytes(target, _read_bytes(source))
    return {
        "path": relative.as_posix(),
        "kind": suffix.lstrip(".") or "file",
        "status": "backup_original",
        "source_artifact": target_name,
        "item_id": item_id,
    }


def _upsert_output(outputs: list[dict[str, Any]], record: dict[str, Any]) -> None:
    path = record.get("path")
    for index, output in enumerate(outputs):
        if isinstance(output, dict) and output.get("path") == path:
            outputs[index] = {**output, **record}
            return
    outputs.append(record)


def _csv_rows(path: Path) -> tuple[list[str], list[list[str]]]:
    if _lstat_or_none(path) is None:
        return [], []
    text = _read_bytes(path).decode("utf-8")
    rows = list(csv.reader(io.StringIO(text, newline="")))
    if not rows:
        return [], []
    return rows[0], rows[1:]


def _receipt_for_path(
    envelope: dict[str, Any],
    *,
    root_id: str,
    relative_path: str,
) -> dict[str, Any] | None:
    matches = [
        receipt
        for receipt in envelope.get("artifact_receipts", [])
        if isinstance(receipt, dict)
        and receipt.get("root_id") == root_id
        and receipt.get("path") == relative_path
    ]
    if len(matches) != 1:
        return None
    return matches[0]


def _snapshot_matches_receipt(path: Path, receipt: dict[str, Any]) -> bool:
    try:
        payload = _read_bytes(path)
    except (OSError, ValueError):
        return False
    return len(payload) == receipt.get("byte_count") and hashlib.sha256(
        payload
    ).hexdigest() == receipt.get("sha256")


def _exact_match_review_delta_errors(
    output_dir: Path,
    envelope: dict[str, Any],
    effects: list[dict[str, Any]],
) -> tuple[list[str], set[str]]:
    if not effects:
        return [], set()
    target_relative = "reconciliation_matches.csv"
    receipt = _receipt_for_path(
        envelope,
        root_id="run",
        relative_path=target_relative,
    )
    if receipt is None:
        return ["Original envelope does not bind reconciliation_matches.csv."], set()

    originals: list[Path] = []
    expected_values: dict[str, str] = {}
    for effect in effects:
        backup_relative = _canonical_relative_path(
            effect.get("original_artifact_backup")
        )
        if backup_relative is None or not backup_relative.startswith(
            "revisions/originals/"
        ):
            return [
                "Every structured review edit requires an original artifact backup."
            ], set()
        backup_path = output_dir / backup_relative
        if not backup_path.is_file() or not _snapshot_matches_receipt(
            backup_path, receipt
        ):
            return [
                "A structured review backup does not replay the original "
                "reconciliation_matches.csv receipt."
            ], set()
        originals.append(backup_path)
        update = effect["structured_update"]
        record_id = clean_text(update["record_id"])
        if record_id in expected_values:
            return ["A review application edits the same match more than once."], set()
        expected_values[record_id] = clean_text(effect["edit_value"])

    original_header, original_rows = _csv_rows(originals[0])
    current_header, current_rows = _csv_rows(output_dir / target_relative)
    if original_header != current_header or len(original_rows) != len(current_rows):
        return [
            "The structured review edit changed CSV columns or row membership."
        ], set()
    if (
        "bank_transaction_id" not in original_header
        or "review_note" not in original_header
    ):
        return [
            "The review target lacks its bound identifier or review-note field."
        ], set()
    if any(len(row) != len(original_header) for row in (*original_rows, *current_rows)):
        return ["The review target contains a non-rectangular CSV row."], set()

    id_index = original_header.index("bank_transaction_id")
    note_index = original_header.index("review_note")
    seen_ids: set[str] = set()
    actual_changed_ids: set[str] = set()
    for original_row, current_row in zip(original_rows, current_rows, strict=True):
        record_id = original_row[id_index]
        if record_id in seen_ids:
            return [
                "The review target contains duplicate bank_transaction_id values."
            ], set()
        seen_ids.add(record_id)
        for index, (before, after) in enumerate(
            zip(original_row, current_row, strict=True)
        ):
            if before == after:
                continue
            if index != note_index or record_id not in expected_values:
                return [
                    "The review mutation is not limited to the authorized review_note cell."
                ], set()
            if after != expected_values[record_id]:
                return [
                    "The review_note value does not match the explicit reviewer edit."
                ], set()
            actual_changed_ids.add(record_id)
    if actual_changed_ids != set(expected_values):
        return [
            "The structured review effects do not exactly describe the CSV delta."
        ], set()
    return [], {target_relative}


def _baseline_integrity_errors(
    output_dir: Path,
    effects: list[dict[str, Any]],
) -> tuple[list[str], set[str]]:
    try:
        replay, envelope = _baseline_replay(output_dir)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        return [f"Original-envelope replay failed: {exc}"], set()
    expected_snapshots = [
        {
            "artifact_id": receipt["artifact_id"],
            "root_id": receipt["root_id"],
            "path": receipt["path"],
            "byte_count": receipt["byte_count"],
            "sha256": receipt["sha256"],
        }
        for receipt in envelope.get("artifact_receipts", [])
        if isinstance(receipt, dict)
    ]
    if replay.get("artifact_snapshots") != expected_snapshots:
        return ["Review baseline replay artifact list is stale."], set()

    delta_errors, verified_changed_paths = _exact_match_review_delta_errors(
        output_dir,
        envelope,
        effects,
    )
    errors = list(delta_errors)
    roots = _source_roots(output_dir)
    for receipt in envelope.get("artifact_receipts", []):
        if not isinstance(receipt, dict):
            errors.append("Original envelope contains a non-object artifact receipt.")
            continue
        if (
            receipt.get("root_id") == "run"
            and receipt.get("path") in verified_changed_paths
        ):
            continue
        try:
            validate_artifact_receipt(roots, receipt)
        except (OSError, ValueError) as exc:
            errors.append(
                f"Original envelope artifact "
                f"{receipt.get('artifact_id', '<unknown>')} failed: {exc}"
            )
    return errors, verified_changed_paths


def _write_journal_bank_workbook(output_dir: Path, workbook_path: Path) -> int:
    workbook = openpyxl.Workbook()
    default = workbook.active
    workbook.remove(default)
    matches_row_count = 0
    for sheet_name, relative_csv in WORKBOOK_SHEETS.items():
        header, rows = _csv_rows(output_dir / relative_csv)
        sheet = workbook.create_sheet(sheet_name[:31])
        if header:
            sheet.append([excel_safe_value(value) for value in header])
        for row in rows:
            sheet.append(
                [excel_safe_value(value) if value != "" else None for value in row]
            )
        if sheet_name == "matches":
            matches_row_count = len(rows)
    workbook_path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="journal-bank-workbook-") as temp_name:
        staged_workbook = Path(temp_name) / workbook_path.name
        workbook.save(staged_workbook)
        _atomic_write_bytes(workbook_path, staged_workbook.read_bytes())
    return matches_row_count


def _column_letters(index: int) -> str:
    letters = ""
    while index > 0:
        index, remainder = divmod(index - 1, 26)
        letters = chr(65 + remainder) + letters
    return letters


def _required_cells_for_effects(
    sheet_name: str,
    header: list[str],
    rows: list[list[str]],
    effects: list[dict[str, Any]],
) -> dict[str, dict[str, str]]:
    cells: dict[str, str] = {}
    for effect in effects:
        structured_update = effect.get("structured_update")
        update = structured_update if isinstance(structured_update, dict) else {}
        id_field = clean_text(update.get("id_field") or effect.get("target_id_field"))
        record_id = clean_text(
            update.get("record_id") or effect.get("target_record_id")
        )
        target_field = clean_text(
            update.get("target_field") or effect.get("target_field")
        )
        edit_value = clean_text(effect.get("edit_value"))
        workbook_value = excel_safe_value(edit_value)
        if not id_field or not record_id or not target_field or not edit_value:
            continue
        if id_field not in header or target_field not in header:
            continue
        id_index = header.index(id_field)
        target_index = header.index(target_field)
        for row_number, row in enumerate(rows, start=2):
            if len(row) <= id_index or str(row[id_index]) != record_id:
                continue
            cell_ref = f"{_column_letters(target_index + 1)}{row_number}"
            cells[cell_ref] = str(workbook_value)
            break
    return {sheet_name: cells} if cells else {}


def _workbook_required_headers(output_dir: Path) -> dict[str, list[str]]:
    headers: dict[str, list[str]] = {}
    for sheet_name, relative_csv in WORKBOOK_SHEETS.items():
        header, _ = _csv_rows(output_dir / relative_csv)
        if header:
            headers[sheet_name] = [
                str(excel_safe_value(value)) for value in header if value
            ]
    return headers


def _effect_native_paths(effect: dict[str, Any]) -> list[str]:
    paths = effect.get("derived_native_regeneration_paths")
    if isinstance(paths, list) and paths:
        return [clean_text(path) for path in paths if clean_text(path)]
    if effect.get("requires_native_regeneration"):
        target = clean_text(effect.get("target_artifact"))
        return [target] if target else []
    return []


def _pending_native_paths(effects: list[dict[str, Any]]) -> list[str]:
    paths: list[str] = []
    for effect in effects:
        if not effect.get("requires_native_regeneration"):
            continue
        paths.extend(_effect_native_paths(effect))
    return sorted(dict.fromkeys(paths))


def _review_is_complete(applied: dict[str, Any]) -> bool:
    return int(applied.get("blocker_count") or 0) == 0 and int(
        applied.get("decision_count") or 0
    ) == int(applied.get("item_count") or 0)


def _closed_reconciliation(
    output_dir: Path,
) -> tuple[bool, list[str]]:
    reasons: list[str] = []
    audit_path = output_dir / "reconciliation_audit.json"
    ledger_path = output_dir / "relationship_ledger.json"
    if not audit_path.is_file():
        return False, ["Reconciliation audit is missing."]
    audit = _read_json(audit_path)
    if int(audit.get("unmatched_bank_count") or 0) != 0:
        reasons.append("Unmatched bank rows remain.")
    if int(audit.get("unmatched_journal_count") or 0) != 0:
        reasons.append("Unmatched journal rows remain.")
    if audit.get("relationship_balanced") is not True:
        reasons.append("The audit does not record an exactly balanced relationship.")
    if not ledger_path.is_file():
        reasons.append("Relationship ledger is missing.")
    else:
        try:
            ledger = validate_allocation_ledger(_read_json(ledger_path))
            if ledger["balanced"] is not True:
                reasons.append("Relationship ledger contains unresolved residuals.")
            elif any(
                str(item["residual"]) != "0"
                for item in (
                    *ledger["source_residuals"],
                    *ledger["target_residuals"],
                )
            ):
                reasons.append(
                    "Relationship ledger is within tolerance but not exactly closed."
                )
        except (OSError, ValueError, json.JSONDecodeError) as exc:
            reasons.append(f"Relationship ledger is invalid: {exc}")
    return not reasons, reasons


def _identifier_or_default(value: object, *, default: str) -> str:
    text = clean_text(value)
    return text if IDENTIFIER_RE.fullmatch(text) is not None else default


def _review_application_decision(
    output_dir: Path,
    applied: dict[str, Any],
    effects: list[dict[str, Any]],
    *,
    integrity_errors: list[str],
) -> str | None:
    if integrity_errors or not _review_is_complete(applied):
        return None
    bundle = _receipt_bundle(output_dir)
    if bundle is None:
        return None
    source_refs = [
        clean_text(receipt.get("artifact_id"))
        for receipt in bundle["source_receipts"]
        if isinstance(receipt, dict) and clean_text(receipt.get("artifact_id"))
    ]
    if not source_refs:
        return None
    content = {
        "decision_count": int(applied.get("decision_count") or 0),
        "item_count": int(applied.get("item_count") or 0),
        "blocker_count": int(applied.get("blocker_count") or 0),
        "effects_sha256": canonical_json_sha256(effects),
    }
    decision_suffix = canonical_json_sha256(content)[:16]
    reviewed_on = clean_text(applied.get("applied_at"))[:10]
    try:
        date.fromisoformat(reviewed_on)
    except ValueError:
        reviewed_on = date.today().isoformat()
    reviewer_value = applied.get("reviewer_ref") or applied.get("reviewer")
    if isinstance(reviewer_value, dict):
        reviewer_value = (
            reviewer_value.get("reviewer_ref")
            or reviewer_value.get("id")
            or reviewer_value.get("email")
        )
    decision = build_reviewed_decision_receipt(
        decision_id=f"decision.review_application.{decision_suffix}",
        decision_type="journal_bank_review_application",
        status="reviewed",
        reviewer_ref=_identifier_or_default(
            reviewer_value,
            default="reviewer.recorded",
        ),
        reviewed_on=reviewed_on,
        adapter_id=REVIEW_ADAPTER_ID,
        adapter_version=REVIEW_ADAPTER_VERSION,
        source_artifact_refs=source_refs,
        content=content,
    )
    decisions_path = output_dir / "reviewed_decisions.json"
    payload = _read_json(decisions_path)
    decisions = [
        value
        for value in payload.get("decisions", [])
        if isinstance(value, dict)
        and value.get("decision_id") != decision["decision_id"]
    ]
    decisions.append(decision)
    payload["decisions"] = decisions
    _write_json(decisions_path, payload)
    return str(decision["decision_id"])


def _reviewed_gate_register(
    output_dir: Path,
    applied: dict[str, Any],
    *,
    integrity_errors: list[str],
    semantic_decision_ref: str | None,
) -> tuple[dict[str, Any] | None, str, list[str]]:
    gate_path = output_dir / "assurance_gates.json"
    if not gate_path.is_file():
        return None, "blocked", ["Assurance gate register is missing."]
    try:
        current = validate_gate_register(_read_json(gate_path))
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        return None, "blocked", [f"Assurance gate register is invalid: {exc}"]

    gates = current["gates"]
    closed, closure_reasons = _closed_reconciliation(output_dir)
    upstream_source_preparation = all(
        gates[name]["status"] in {"passed", "not_applicable"}
        for name in ("source", "preparation")
    )
    reconciliation_passed = (
        gates["reconciliation"]["status"] in {"passed", "not_applicable"} and closed
    )
    complete_review = _review_is_complete(applied)
    reasons = [*closure_reasons, *integrity_errors]
    if not upstream_source_preparation:
        reasons.append("Source or preparation assurance is not passed.")
    if not complete_review:
        reasons.append("Review decisions are incomplete or contain blockers.")

    reconciliation_gate = dict(gates["reconciliation"])
    if not closed and reconciliation_gate["status"] == "passed":
        reconciliation_gate = {
            "status": "withheld",
            "evidence_refs": [],
            "limitations": closure_reasons
            or ["Reconciliation closure could not be verified."],
        }
    semantic_passed = (
        upstream_source_preparation
        and complete_review
        and not integrity_errors
        and semantic_decision_ref is not None
    )
    semantic_gate = {
        "status": "passed" if semantic_passed else "blocked",
        "evidence_refs": [semantic_decision_ref] if semantic_passed else [],
        "limitations": (
            []
            if semantic_passed
            else [
                "Professional review is incomplete or upstream preparation is blocked."
            ]
        ),
    }
    reporting_passed = (
        reconciliation_passed and semantic_passed and not integrity_errors
    )
    reporting_gate = {
        "status": "passed" if reporting_passed else "blocked",
        "evidence_refs": (
            ["output.workbook_xlsx", "output.final_artifacts_json"]
            if reporting_passed
            else []
        ),
        "limitations": (
            []
            if reporting_passed
            else reasons or ["Reporting assurance remains withheld."]
        ),
    }
    updated = build_gate_register(
        {
            "source": gates["source"],
            "preparation": gates["preparation"],
            "reconciliation": reconciliation_gate,
            "semantic_review": semantic_gate,
            "reporting": reporting_gate,
            "publication": gates["publication"],
        }
    )
    if updated["report_ready"]:
        return updated, "final_ready", []
    if not complete_review and int(applied.get("blocker_count") or 0) == 0:
        return updated, "partial_review_applied", reasons
    return updated, "blocked", reasons


def _next_actions(current: list[Any], status: str) -> list[str]:
    next_actions = [
        clean_text(action)
        for action in current
        if clean_text(action)
        and clean_text(action)
        not in {
            REGENERATE_NATIVE_OUTPUT_ACTION,
            FINAL_HANDOFF_ACTION,
            COMPLETE_REVIEW_ACTION,
            RESOLVE_ASSURANCE_ACTION,
        }
    ]
    if status == "final_ready":
        next_actions.append(FINAL_HANDOFF_ACTION)
    elif status == "partial_review_applied":
        next_actions.append(COMPLETE_REVIEW_ACTION)
    else:
        next_actions.append(RESOLVE_ASSURANCE_ACTION)
    return list(dict.fromkeys(next_actions))


def _append_review_trace_outputs(output_dir: Path, paths: list[str]) -> None:
    run_intake_path = output_dir / "run_intake.json"
    if not run_intake_path.is_file() or not paths:
        return
    run_intake = _read_json(run_intake_path)
    trace = run_intake.get("execution_trace")
    if not isinstance(trace, list):
        return
    for step in reversed(trace):
        if (
            not isinstance(step, dict)
            or step.get("kind") != "deterministic_review_apply"
        ):
            continue
        outputs = [
            clean_text(value) for value in step.get("outputs", []) if clean_text(value)
        ]
        step["outputs"] = list(dict.fromkeys([*outputs, *paths]))
        _write_json(run_intake_path, run_intake)
        return


def apply_review_edits(
    output_dir: Path,
    applied_decisions_path: Path,
    final_artifacts_path: Path,
    *,
    canonical_output_dir: Path | None = None,
) -> dict[str, Any]:
    """Regenerate the Journal-Bank workbook after explicit CSV review edits."""

    output_dir = _validate_output_tree(output_dir)
    canonical_output_dir = _validate_canonical_output_slot(
        output_dir,
        canonical_output_dir,
    )
    applied_decisions_path = _validate_run_file(
        output_dir,
        applied_decisions_path,
        "applied decisions",
    )
    final_artifacts_path = _validate_run_file(
        output_dir,
        final_artifacts_path,
        "final artifacts",
    )
    workbook_path = output_dir / "journal_bank_reconciliation.xlsx"

    applied = _read_json(applied_decisions_path)
    final_artifacts = _read_json(final_artifacts_path)
    effects = [
        effect for effect in applied.get("effects", []) if isinstance(effect, dict)
    ]
    candidate_effects = [
        effect for effect in effects if _eligible_reconciliation_effect(effect)
    ]
    baseline_errors, verified_changed_paths = _baseline_integrity_errors(
        output_dir,
        candidate_effects,
    )
    authorized_changed_paths = _authorized_changed_paths(
        applied_decisions_path=applied_decisions_path,
        final_artifacts_path=final_artifacts_path,
        output_dir=output_dir,
        verified_changed_paths=verified_changed_paths,
    )
    integrity_errors = [
        *baseline_errors,
        *_receipt_integrity_errors(
            output_dir,
            authorized_changed_paths=authorized_changed_paths,
        ),
    ]
    verified_effects = candidate_effects if not integrity_errors else []
    backup_outputs: list[dict[str, Any]] = []
    native_regenerated_paths: list[str] = []
    row_count = 0
    required_cells: dict[str, dict[str, str]] = {}
    if verified_effects:
        matches_path = output_dir / "reconciliation_matches.csv"
        if not matches_path.exists():
            raise FileNotFoundError(matches_path)
        backup = _backup_native(
            output_dir,
            clean_text(verified_effects[0].get("item_id")),
            "journal_bank_reconciliation.xlsx",
        )
        if backup:
            backup_outputs.append(backup)
        matches_header, matches_rows = _csv_rows(matches_path)
        row_count = _write_journal_bank_workbook(output_dir, workbook_path)
        required_cells = _required_cells_for_effects(
            "matches",
            matches_header,
            matches_rows,
            verified_effects,
        )
        for effect in verified_effects:
            effect["requires_native_regeneration"] = False
            effect["native_regeneration_status"] = "regenerated"
            effect["native_regenerated_paths"] = ["journal_bank_reconciliation.xlsx"]
        native_regenerated_paths = ["journal_bank_reconciliation.xlsx"]

    native_pending = _pending_native_paths(effects)
    applied["effects"] = effects
    applied["native_regeneration_count"] = len(native_pending)
    applied["native_regeneration_paths"] = native_pending
    applied["native_regenerated_count"] = len(verified_effects)
    applied["native_regenerated_paths"] = native_regenerated_paths
    original_backup_paths = list(applied.get("original_backup_paths") or [])
    for backup_output in backup_outputs:
        if backup_output["path"] not in original_backup_paths:
            original_backup_paths.append(backup_output["path"])
    applied["original_backup_paths"] = original_backup_paths
    semantic_decision_ref = _review_application_decision(
        output_dir,
        applied,
        effects,
        integrity_errors=integrity_errors,
    )
    updated_gates, application_status, assurance_reasons = _reviewed_gate_register(
        output_dir,
        applied,
        integrity_errors=integrity_errors,
        semantic_decision_ref=semantic_decision_ref,
    )
    applied["semantic_review_decision_ref"] = semantic_decision_ref
    applied["application_status"] = application_status
    applied["assurance_report_ready"] = bool(
        updated_gates and updated_gates["report_ready"]
    )
    applied["assurance_limitations"] = assurance_reasons
    if updated_gates is not None:
        _write_json(output_dir / "assurance_gates.json", updated_gates)
        audit_path = output_dir / "reconciliation_audit.json"
        if audit_path.is_file():
            audit = _read_json(audit_path)
            audit["review_application_status"] = application_status
            audit["assurance_report_ready"] = updated_gates["report_ready"]
            _write_json(audit_path, audit)

    outputs = [
        output
        for output in final_artifacts.get("outputs", [])
        if isinstance(output, dict)
    ]
    if verified_effects:
        _upsert_output(
            outputs,
            {
                "path": "journal_bank_reconciliation.xlsx",
                "kind": "xlsx",
                "status": "updated_from_review",
                "native_regenerated": True,
                "source_artifact": "reconciliation_matches.csv",
                "source_row_count": row_count,
                "size_bytes": workbook_path.stat().st_size,
                "required_sheets": list(WORKBOOK_SHEETS),
                "required_sheet_headers": _workbook_required_headers(output_dir),
                "required_cells": required_cells,
            },
        )
    for backup_output in backup_outputs:
        _upsert_output(outputs, backup_output)
    final_artifacts["outputs"] = outputs
    final_artifacts["status"] = applied["application_status"]
    final_artifacts["review_status"] = applied["application_status"]
    review_application = final_artifacts.setdefault("review_application", {})
    if isinstance(review_application, dict):
        review_application["application_status"] = applied["application_status"]
        review_application["assurance_report_ready"] = applied["assurance_report_ready"]
        review_application["assurance_limitations"] = assurance_reasons
        review_application["native_regeneration_count"] = applied[
            "native_regeneration_count"
        ]
        review_application["native_regeneration_paths"] = applied[
            "native_regeneration_paths"
        ]
        review_application["native_regenerated_count"] = applied[
            "native_regenerated_count"
        ]
        review_application["native_regenerated_paths"] = native_regenerated_paths
        review_application["original_backup_paths"] = original_backup_paths
    final_artifacts["next_actions"] = _next_actions(
        list(final_artifacts.get("next_actions") or []),
        applied["application_status"],
    )

    _write_json(applied_decisions_path, applied)
    _write_json(final_artifacts_path, final_artifacts)
    _append_review_trace_outputs(
        output_dir,
        [
            *native_regenerated_paths,
            *[backup_output["path"] for backup_output in backup_outputs],
        ],
    )
    post_replay_errors: list[str] = []
    if integrity_errors:
        receipt_payload = _receipt_bundle(output_dir)
    else:
        receipt_payload = _reseal_artifact_receipts(output_dir)
        post_replay_errors.extend(
            _receipt_bundle_replay_errors(output_dir, receipt_payload)
        )
        if not post_replay_errors and applied["application_status"] == "final_ready":
            try:
                _write_reviewed_assurance_envelope(output_dir, receipt_payload)
                receipt_payload = _reseal_artifact_receipts(output_dir)
                post_replay_errors.extend(
                    _receipt_bundle_replay_errors(output_dir, receipt_payload)
                )
                reviewed_envelope = _read_json(output_dir / REVIEWED_ENVELOPE_PATH)
                roots = _source_roots(output_dir)
                validate_exact_implementation_receipts(
                    reviewed_envelope,
                    artifact_roots=roots,
                )
                validate_assurance_envelope(
                    reviewed_envelope,
                    artifact_roots=roots,
                )
            except (OSError, ValueError, json.JSONDecodeError) as exc:
                post_replay_errors.append(f"Reviewed-envelope replay failed: {exc}")
    if post_replay_errors:
        assurance_reasons = [*assurance_reasons, *post_replay_errors]
        updated_gates, application_status, _ = _reviewed_gate_register(
            output_dir,
            applied,
            integrity_errors=assurance_reasons,
            semantic_decision_ref=semantic_decision_ref,
        )
        applied["application_status"] = application_status
        applied["assurance_report_ready"] = False
        applied["assurance_limitations"] = assurance_reasons
        final_artifacts["status"] = application_status
        final_artifacts["review_status"] = application_status
        review_application = final_artifacts.get("review_application")
        if isinstance(review_application, dict):
            review_application["application_status"] = application_status
            review_application["assurance_report_ready"] = False
            review_application["assurance_limitations"] = assurance_reasons
        final_artifacts["next_actions"] = _next_actions(
            list(final_artifacts.get("next_actions") or []),
            application_status,
        )
        if updated_gates is not None:
            _write_json(output_dir / "assurance_gates.json", updated_gates)
        _write_json(applied_decisions_path, applied)
        _write_json(final_artifacts_path, final_artifacts)
    output_receipt_count = (
        len(receipt_payload["output_receipts"])
        if receipt_payload is not None
        and isinstance(receipt_payload.get("output_receipts"), list)
        else 0
    )
    _validate_output_tree(output_dir)
    _validate_canonical_output_slot(output_dir, canonical_output_dir)
    return {
        "ok": True,
        "updated_effect_count": len(verified_effects),
        "native_regenerated_paths": native_regenerated_paths,
        "backup_paths": [backup_output["path"] for backup_output in backup_outputs],
        "application_status": applied["application_status"],
        "assurance_report_ready": applied["assurance_report_ready"],
        "assurance_limitations": assurance_reasons,
        "artifact_receipt_count": output_receipt_count,
        "applied_decisions": applied,
        "final_artifacts": final_artifacts,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=("Apply Journal-Bank review edits and regenerate native outputs.")
    )
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--preflight-only", action="store_true")
    parser.add_argument("--applied-decisions", type=Path)
    parser.add_argument("--final-artifacts", type=Path)
    parser.add_argument("--canonical-output-dir", type=Path)
    args = parser.parse_args(argv)
    if args.preflight_only:
        result = preflight_review_application(args.output_dir)
        sys.stdout.write(json.dumps(result, ensure_ascii=False) + "\n")
        return 0
    if args.applied_decisions is None or args.final_artifacts is None:
        parser.error(
            "--applied-decisions and --final-artifacts are required unless "
            "--preflight-only is used"
        )
    result = apply_review_edits(
        args.output_dir,
        args.applied_decisions,
        args.final_artifacts,
        canonical_output_dir=args.canonical_output_dir,
    )
    sys.stdout.write(json.dumps(result, ensure_ascii=False) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
