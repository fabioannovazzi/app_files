from __future__ import annotations

import sys as _bootstrap_sys

_bootstrap_sys.dont_write_bytecode = True
_bootstrap_sys.pycache_prefix = (
    r"Z:\__check_entries_no_local_bytecode__"
    if _bootstrap_sys.platform == "win32"
    else "/dev/null/check-entries"
)

import os as _bootstrap_os

_BOOTSTRAP_PATH = _bootstrap_os.path.join(
    _bootstrap_os.path.dirname(_bootstrap_os.path.abspath(__file__)),
    "implementation_bootstrap.py",
)
_BOOTSTRAP_NAMESPACE = {
    "__file__": _BOOTSTRAP_PATH,
    "__name__": "_check_entries_implementation_bootstrap",
}
_bootstrap_lstat = _bootstrap_os.lstat(_BOOTSTRAP_PATH)
if _bootstrap_lstat.st_mode & 0o170000 != 0o100000 or _bootstrap_lstat.st_nlink != 1:
    raise RuntimeError(
        "implementation bootstrap must be an ordinary single-link regular file"
    )
_bootstrap_flags = _bootstrap_os.O_RDONLY
_bootstrap_flags |= getattr(_bootstrap_os, "O_NOFOLLOW", 0)
_bootstrap_flags |= getattr(_bootstrap_os, "O_NONBLOCK", 0)
_bootstrap_fd = _bootstrap_os.open(_BOOTSTRAP_PATH, _bootstrap_flags)
try:
    _bootstrap_before = _bootstrap_os.fstat(_bootstrap_fd)
    _bootstrap_identity = (
        _bootstrap_before.st_dev,
        _bootstrap_before.st_ino,
        _bootstrap_before.st_mode,
        _bootstrap_before.st_nlink,
        _bootstrap_before.st_size,
        _bootstrap_before.st_mtime_ns,
        _bootstrap_before.st_ctime_ns,
    )
    if _bootstrap_identity != (
        _bootstrap_lstat.st_dev,
        _bootstrap_lstat.st_ino,
        _bootstrap_lstat.st_mode,
        _bootstrap_lstat.st_nlink,
        _bootstrap_lstat.st_size,
        _bootstrap_lstat.st_mtime_ns,
        _bootstrap_lstat.st_ctime_ns,
    ):
        raise RuntimeError("implementation bootstrap changed before open")
    _bootstrap_chunks = []
    _bootstrap_remaining = _bootstrap_before.st_size
    while _bootstrap_remaining:
        _bootstrap_chunk = _bootstrap_os.read(
            _bootstrap_fd,
            min(_bootstrap_remaining, 1024 * 1024),
        )
        if not _bootstrap_chunk:
            raise RuntimeError("implementation bootstrap ended during snapshot")
        _bootstrap_chunks.append(_bootstrap_chunk)
        _bootstrap_remaining -= len(_bootstrap_chunk)
    _bootstrap_after = _bootstrap_os.fstat(_bootstrap_fd)
    if _bootstrap_identity != (
        _bootstrap_after.st_dev,
        _bootstrap_after.st_ino,
        _bootstrap_after.st_mode,
        _bootstrap_after.st_nlink,
        _bootstrap_after.st_size,
        _bootstrap_after.st_mtime_ns,
        _bootstrap_after.st_ctime_ns,
    ):
        raise RuntimeError("implementation bootstrap changed during snapshot")
finally:
    _bootstrap_os.close(_bootstrap_fd)
_bootstrap_path_after = _bootstrap_os.lstat(_BOOTSTRAP_PATH)
if _bootstrap_identity != (
    _bootstrap_path_after.st_dev,
    _bootstrap_path_after.st_ino,
    _bootstrap_path_after.st_mode,
    _bootstrap_path_after.st_nlink,
    _bootstrap_path_after.st_size,
    _bootstrap_path_after.st_mtime_ns,
    _bootstrap_path_after.st_ctime_ns,
):
    raise RuntimeError("implementation bootstrap path changed during snapshot")
# The snapshot is the exact no-follow, identity-stable local bootstrap bytes.
exec(  # nosec B102
    compile(b"".join(_bootstrap_chunks), _BOOTSTRAP_PATH, "exec"),
    _BOOTSTRAP_NAMESPACE,
)
_BOOTSTRAP_ROOTS = _BOOTSTRAP_NAMESPACE["activate_implementation_boundary"]()
_BOOTSTRAP_VALIDATE_IMPLEMENTATION = _BOOTSTRAP_NAMESPACE[
    "validate_implementation_tree"
]
_BOOTSTRAP_NAMESPACE["load_assurance_package"](
    _BOOTSTRAP_ROOTS["assurance_implementation"]
)
_bootstrap_path_final = _bootstrap_os.lstat(_BOOTSTRAP_PATH)
if _bootstrap_identity != (
    _bootstrap_path_final.st_dev,
    _bootstrap_path_final.st_ino,
    _bootstrap_path_final.st_mode,
    _bootstrap_path_final.st_nlink,
    _bootstrap_path_final.st_size,
    _bootstrap_path_final.st_mtime_ns,
    _bootstrap_path_final.st_ctime_ns,
):
    raise RuntimeError("implementation bootstrap changed during validation")
_bootstrap_scripts_dir = _bootstrap_os.path.dirname(
    _bootstrap_os.path.abspath(__file__)
)
if _bootstrap_scripts_dir not in _bootstrap_sys.path:
    _bootstrap_sys.path.insert(0, _bootstrap_scripts_dir)
import argparse
import csv
import hashlib
import json
import os
import re
import shutil
import stat
import sys
import tempfile
from datetime import date
from pathlib import Path
from typing import Any

import openpyxl
from check_entries_core import run_entry_checks  # noqa: E402
from implementation_contract import (  # noqa: E402
    implementation_artifact_roots,
    validate_implementation_contract,
)
from physical_output_set import (
    validate_initial_output_set,
    validate_review_successor_output_set,
    validate_review_transition_output_set,
)
from stable_ooxml import write_stable_xlsx
from vera_assurance import (  # noqa: E402
    AssuranceContractError,
    artifact_receipt,
    build_assurance_envelope,
    build_reviewed_decision_receipt,
    canonical_json_sha256,
    load_client_workflow_context_for_output,
    validate_artifact_receipt,
    validate_assurance_envelope,
)

__all__ = ["apply_review_edits", "preflight_assurance", "main"]

REGENERATE_NATIVE_OUTPUT_ACTION = (
    "Regenerate native DOCX/XLSX/PDF outputs before final handoff."
)
FINAL_HANDOFF_ACTION = (
    "Use final_artifacts.json as the reviewed artifact gallery for handoff."
)
COMPLETE_REVIEW_ACTION = "Complete remaining review decisions before final handoff."


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


def _validate_output_tree(output_dir: Path) -> Path:
    """Reject links, aliases, and special entries in a transaction tree."""

    output_dir = _absolute_path_without_following(output_dir)
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
    parent_stat = _lstat_or_none(canonical.parent)
    if (
        parent_stat is None
        or stat.S_ISLNK(parent_stat.st_mode)
        or not stat.S_ISDIR(parent_stat.st_mode)
    ):
        raise ValueError("canonical output parent must be a real directory")
    canonical_stat = _lstat_or_none(canonical)
    if canonical_stat is not None and (
        stat.S_ISLNK(canonical_stat.st_mode) or not stat.S_ISDIR(canonical_stat.st_mode)
    ):
        raise ValueError("canonical output path must be a real directory")
    # The parent transaction deliberately keeps canonical in place while this
    # child works on staging, then verifies its exact in-memory image.
    return canonical


def _atomic_write_bytes(path: Path, payload: bytes) -> None:
    """Replace one leaf through an opened real directory without following links."""

    parent_flags = os.O_RDONLY
    parent_flags |= getattr(os, "O_DIRECTORY", 0)
    parent_flags |= getattr(os, "O_NOFOLLOW", 0)
    parent_fd = os.open(path.parent, parent_flags)
    temp_name = f".{path.name}.check-entries-write-{os.getpid()}-{os.urandom(8).hex()}"
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

        # Recheck the leaf immediately before replacement. The replacement
        # itself is relative to the already-opened parent directory, so a
        # concurrent path swap cannot redirect the write outside that directory.
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
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"Expected JSON object: {path}")
    return payload


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    _atomic_write_bytes(
        path,
        (json.dumps(payload, ensure_ascii=False, indent=2) + "\n").encode("utf-8"),
    )


def _eligible_check_results_effect(effect: dict[str, Any]) -> bool:
    """Return whether a structured CSV edit should refresh the XLSX workbook."""

    if effect.get("action") != "edit":
        return False
    if effect.get("artifact_update") != "structured_artifact_updated":
        return False
    if clean_text(effect.get("target_artifact")) != "check_results.csv":
        return False
    paths = effect.get("derived_native_regeneration_paths")
    if not isinstance(paths, list) or "check_results.xlsx" not in paths:
        return False
    return bool(clean_text(effect.get("edit_value")))


def _safe_item_id(value: object) -> str:
    text = clean_text(value) or "item"
    cleaned = "".join(char if char.isalnum() or char in "._-" else "-" for char in text)
    return cleaned.strip("-") or "item"


def _backup_native(output_dir: Path, item_id: str, target_name: str) -> dict[str, Any]:
    source = output_dir / target_name
    if not source.exists():
        return {}
    suffix = source.suffix or ".xlsx"
    relative = (
        Path("revisions")
        / "originals"
        / f"{source.stem}__{_safe_item_id(item_id)}{suffix}"
    )
    target = output_dir / relative
    target.parent.mkdir(parents=True, exist_ok=True)
    if not target.exists():
        _atomic_write_bytes(target, source.read_bytes())
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
    with path.open("r", encoding="utf-8", newline="") as handle:
        rows = list(csv.reader(handle))
    if not rows:
        raise ValueError(f"Cannot regenerate workbook from empty CSV: {path}")
    return rows[0], rows[1:]


def _write_check_results_workbook(csv_path: Path, workbook_path: Path) -> int:
    header, rows = _csv_rows(csv_path)

    def writer(candidate: Path) -> None:
        workbook = openpyxl.Workbook()
        sheet = workbook.active
        sheet.title = "Sheet1"
        sheet.append(header)
        for row in rows:
            sheet.append([value if value != "" else None for value in row])
        workbook.save(candidate)

    with tempfile.TemporaryDirectory(prefix="check-entries-workbook-") as temp_name:
        staged_workbook = Path(temp_name) / workbook_path.name
        write_stable_xlsx(staged_workbook, writer)
        _atomic_write_bytes(workbook_path, staged_workbook.read_bytes())
    return len(rows)


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
            cells[cell_ref] = edit_value
            break
    return {sheet_name: cells} if cells else {}


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


def _assurance_ready(final_artifacts: dict[str, Any]) -> bool:
    gates = final_artifacts.get("assurance_gates")
    if not isinstance(gates, dict) or gates.get("report_ready") is not True:
        return False
    return final_artifacts.get("professional_conclusion_status") == "reviewed"


def _application_status(
    applied: dict[str, Any],
    final_artifacts: dict[str, Any],
) -> str:
    if int(applied.get("blocker_count") or 0) > 0:
        return "blocked"
    if int(applied.get("native_regeneration_count") or 0) > 0:
        return "partial_review_applied"
    if int(applied.get("decision_count") or 0) < int(applied.get("item_count") or 0):
        return "partial_review_applied"
    if not _assurance_ready(final_artifacts):
        return "blocked"
    return "final_ready"


def _next_actions(current: list[Any], status: str) -> list[str]:
    next_actions = [
        clean_text(action)
        for action in current
        if clean_text(action) and clean_text(action) != REGENERATE_NATIVE_OUTPUT_ACTION
    ]
    if status == "final_ready":
        next_actions.append(FINAL_HANDOFF_ACTION)
    elif status == "partial_review_applied":
        next_actions.append(COMPLETE_REVIEW_ACTION)
    return list(dict.fromkeys(next_actions))


def _resolve_persisted_run_path(
    output_dir: Path,
    run_intake: dict[str, Any],
    value: object,
) -> Path:
    text = clean_text(value)
    if not text:
        raise ValueError("Check Entries persisted path is unavailable")
    reference = Path(text).expanduser()
    if reference.is_absolute():
        return _absolute_path_without_following(reference)
    if (
        run_intake.get("path_reference") != "run_root_relative"
        or ".." in reference.parts
    ):
        raise ValueError("Check Entries persisted path is invalid")
    candidate = output_dir.expanduser().resolve()
    while True:
        context_path = candidate / "context.json"
        context_entry = _lstat_or_none(context_path)
        if (
            context_entry is not None
            and stat.S_ISREG(context_entry.st_mode)
            and not context_path.is_symlink()
            and context_entry.st_nlink == 1
        ):
            return _absolute_path_without_following(candidate / reference)
        if candidate == candidate.parent:
            raise ValueError("Check Entries customer-run context is unavailable")
        candidate = candidate.parent


def _artifact_roots(output_dir: Path, audit: dict[str, Any]) -> dict[str, Path]:
    """Resolve all roots used by the Check Entries assurance envelope."""

    journal_value = clean_text(audit.get("journal"))
    support_value = clean_text(audit.get("pdf_path"))
    if not journal_value:
        raise ValueError("check_audit.json does not identify the normalized journal")
    if not support_value:
        raise ValueError("check_audit.json does not identify the support path")
    run_intake = _read_json(output_dir / "run_intake.json")
    journal = _resolve_persisted_run_path(output_dir, run_intake, journal_value)
    support = _resolve_persisted_run_path(output_dir, run_intake, support_value)
    return {
        "normalization": journal.parent,
        "support": support if support.is_dir() else support.parent,
        "run": output_dir,
        **implementation_artifact_roots(),
    }


def _review_payload_binding(
    output_dir: Path,
    applied: dict[str, Any],
) -> tuple[dict[str, Any], str, dict[str, Any]]:
    """Validate and receipt the exact review payload referenced by decisions."""

    binding = applied.get("review_payload")
    if not isinstance(binding, dict):
        raise ValueError("applied_decisions.json has no review_payload binding")
    relative = Path(clean_text(binding.get("path")) or "review_payload.json")
    if relative.is_absolute() or ".." in relative.parts:
        raise ValueError("review_payload path must stay inside the run output")
    review_payload_path = _absolute_path_without_following(output_dir / relative)
    if not review_payload_path.is_relative_to(output_dir):
        raise ValueError("review_payload path escapes the run output")
    review_payload = _read_json(review_payload_path)
    digest = clean_text(review_payload.get("content_sha256"))
    content = dict(review_payload)
    content.pop("content_sha256", None)
    if not digest or digest != canonical_json_sha256(content):
        raise ValueError("review_payload.content_sha256 is stale")
    bound_digest = clean_text(binding.get("content_sha256"))
    if bound_digest != digest:
        raise ValueError("applied decisions are bound to a different review_payload")
    receipt = artifact_receipt(
        output_dir,
        review_payload_path,
        artifact_id="source.review_payload",
        root_id="run",
        role="source",
        media_type="application/json",
    )
    return review_payload, digest, receipt


def _reviewer_ref(value: object) -> str:
    raw = clean_text(value)
    if not raw:
        return "reviewer.unattributed"
    normalized = re.sub(r"[^A-Za-z0-9._-]+", "-", raw).strip("-._").lower()
    return f"reviewer.{normalized or 'unattributed'}"


def _reviewed_on(value: object) -> str:
    candidate = clean_text(value)[:10]
    try:
        return date.fromisoformat(candidate).isoformat()
    except ValueError as exc:
        raise ValueError("applied_at must contain an ISO date") from exc


def _review_decision_receipt(
    applied: dict[str, Any],
    *,
    review_payload_digest: str,
) -> dict[str, Any]:
    decision_count = int(applied.get("decision_count") or 0)
    item_count = int(applied.get("item_count") or 0)
    decisions = [
        decision
        for decision in applied.get("decisions", [])
        if isinstance(decision, dict)
    ]
    effects = [
        effect for effect in applied.get("effects", []) if isinstance(effect, dict)
    ]
    if len(decisions) != decision_count or len(effects) != decision_count:
        raise ValueError("applied decision and effect counts do not close")
    content = {
        "review_payload_content_sha256": review_payload_digest,
        "decision_count": decision_count,
        "item_count": item_count,
        "application_status": clean_text(applied.get("application_status")),
        "decisions": decisions,
        "effects": effects,
    }
    return build_reviewed_decision_receipt(
        decision_id=f"decision.check_entries_review.{review_payload_digest[:24]}",
        decision_type="check_entries_review_actions",
        status=(
            "reviewed" if item_count > 0 and decision_count == item_count else "draft"
        ),
        reviewer_ref=_reviewer_ref(applied.get("reviewer")),
        reviewed_on=_reviewed_on(applied.get("applied_at")),
        adapter_id="check_entries.review",
        adapter_version="2",
        source_artifact_refs=["source.review_payload"],
        content=content,
    )


def _reissued_receipt(
    output_dir: Path,
    receipt: dict[str, Any],
) -> dict[str, Any]:
    media_type = receipt.get("media_type")
    kwargs: dict[str, Any] = {}
    if isinstance(media_type, str):
        kwargs["media_type"] = media_type
    return artifact_receipt(
        output_dir,
        output_dir / str(receipt["path"]),
        artifact_id=str(receipt["artifact_id"]),
        root_id="run",
        role=str(receipt["role"]),
        **kwargs,
    )


def _validate_audit_digest(audit: dict[str, Any]) -> None:
    digest = clean_text(audit.get("content_sha256"))
    content = dict(audit)
    content.pop("content_sha256", None)
    if not digest or digest != canonical_json_sha256(content):
        raise ValueError("check_audit.json content hash is stale")


def _assurance_paths(output_dir: Path) -> tuple[Path, Path] | None:
    envelope_path = output_dir / "assurance_envelope.json"
    audit_path = output_dir / "check_audit.json"
    if not envelope_path.exists() and not audit_path.exists():
        return None
    if not envelope_path.exists() or not audit_path.exists():
        raise ValueError("assurance envelope and check audit must both be present")
    return envelope_path, audit_path


def _validate_audit_binding(
    output_dir: Path,
    audit: dict[str, Any],
    envelope: dict[str, Any],
) -> None:
    """Validate the audit hash and its exact binding to the local envelope."""

    _validate_audit_digest(audit)
    binding = audit.get("assurance_envelope")
    if not isinstance(binding, dict):
        raise ValueError("check_audit.json has no assurance-envelope binding")
    if clean_text(binding.get("content_sha256")) != clean_text(
        envelope.get("content_sha256")
    ):
        raise ValueError("check audit is bound to a different assurance envelope")
    if audit.get("assurance_gates") != envelope.get("gate_register"):
        raise ValueError("check audit assurance gates differ from the envelope")
    receipt = binding.get("artifact_receipt")
    if not isinstance(receipt, dict):
        raise ValueError("check audit has no assurance-envelope artifact receipt")
    validate_artifact_receipt({"run": output_dir}, receipt)


def _review_successor_decision(
    envelope: dict[str, Any],
) -> dict[str, Any] | None:
    matches = [
        decision
        for decision in envelope.get("reviewed_decisions", [])
        if isinstance(decision, dict)
        and decision.get("decision_type") == "check_entries_review_actions"
        and decision.get("status") in {"draft", "reviewed"}
    ]
    if len(matches) > 1:
        raise ValueError("Check Entries has multiple current review successors.")
    return matches[0] if matches else None


def _stable_regular_bytes(path: Path, *, label: str) -> bytes:
    """Snapshot one ordinary single-link file without following aliases."""

    candidate = _absolute_path_without_following(path)
    observed_path = candidate.lstat()
    if (
        stat.S_ISLNK(observed_path.st_mode)
        or not stat.S_ISREG(observed_path.st_mode)
        or observed_path.st_nlink != 1
    ):
        raise ValueError(f"{label} must be an ordinary single-link file")
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
    descriptor = os.open(candidate, flags)
    try:
        before = os.fstat(descriptor)
        payload = bytearray()
        while True:
            chunk = os.read(descriptor, 1024 * 1024)
            if not chunk:
                break
            payload.extend(chunk)
        after = os.fstat(descriptor)
    finally:
        os.close(descriptor)
    identity = (
        before.st_dev,
        before.st_ino,
        before.st_mode,
        before.st_nlink,
        before.st_size,
        before.st_mtime_ns,
        before.st_ctime_ns,
    )
    if identity != (
        observed_path.st_dev,
        observed_path.st_ino,
        observed_path.st_mode,
        observed_path.st_nlink,
        observed_path.st_size,
        observed_path.st_mtime_ns,
        observed_path.st_ctime_ns,
    ) or identity != (
        after.st_dev,
        after.st_ino,
        after.st_mode,
        after.st_nlink,
        after.st_size,
        after.st_mtime_ns,
        after.st_ctime_ns,
    ):
        raise ValueError(f"{label} changed during snapshot")
    final_path = candidate.lstat()
    if (
        identity
        != (
            final_path.st_dev,
            final_path.st_ino,
            final_path.st_mode,
            final_path.st_nlink,
            final_path.st_size,
            final_path.st_mtime_ns,
            final_path.st_ctime_ns,
        )
        or len(payload) != before.st_size
    ):
        raise ValueError(f"{label} path changed during snapshot")
    return bytes(payload)


def _validated_execution_recipe(
    output_dir: Path,
    audit: dict[str, Any],
    envelope: dict[str, Any],
    run_intake: dict[str, Any],
) -> Path | None:
    """Bind the captured recipe bytes to the still-available original recipe."""

    binding = audit.get("execution_recipe")
    if (
        not isinstance(binding, dict)
        or set(binding) != {"path", "artifact_receipt"}
        or clean_text(binding.get("path")) != "execution_recipe.json"
        or not isinstance(binding.get("artifact_receipt"), dict)
    ):
        raise ValueError("check_audit.json has no exact execution-recipe binding")
    captured_path = _validate_run_file(
        output_dir,
        output_dir / "execution_recipe.json",
        "captured execution recipe",
    )
    receipt = binding["artifact_receipt"]
    validate_artifact_receipt({"run": output_dir}, receipt)
    envelope_receipt = next(
        (
            candidate
            for candidate in envelope.get("artifact_receipts", [])
            if isinstance(candidate, dict)
            and candidate.get("artifact_id") == "source.check_entries_execution_recipe"
        ),
        None,
    )
    if envelope_receipt != receipt:
        raise ValueError("execution recipe is not bound to the assurance envelope")
    captured_bytes = _stable_regular_bytes(
        captured_path,
        label="captured execution recipe",
    )
    assumptions = run_intake.get("assumptions")
    if not isinstance(assumptions, dict):
        raise ValueError("run_intake.json has no exact assumptions")
    recipe_value = assumptions.get("recipe_path")
    if recipe_value is None:
        if captured_bytes != b"{}\n":
            raise ValueError("captured empty recipe is not canonical")
        return None
    if not isinstance(recipe_value, str) or not recipe_value.strip():
        raise ValueError("run_intake.json recipe path is invalid")
    if run_intake.get("path_reference") == "run_root_relative":
        recipe_reference = Path(recipe_value)
        if (
            recipe_reference.is_absolute()
            or ".." in recipe_reference.parts
            or recipe_reference.name != "execution_recipe.json"
        ):
            raise ValueError("run_intake.json recipe path is invalid")
        return captured_path
    recipe_path = _absolute_path_without_following(Path(recipe_value))
    original_bytes = _stable_regular_bytes(
        recipe_path,
        label="original Check Entries recipe",
    )
    if original_bytes != captured_bytes:
        raise ValueError("original Check Entries recipe changed after execution")
    return recipe_path


def _client_engagement_material_projection(value: object) -> object:
    """Keep client/run identity and receipts, excluding hydrated locations."""

    if not isinstance(value, dict):
        return value
    projection = {
        key: value.get(key)
        for key in (
            "schema_version",
            "client_id",
            "engagement_id",
            "workflow_id",
            "workflow_version",
            "run_id",
            "input_manifest",
            "input_manifest_sha256",
            "run_relative_path",
            "output_relative_path",
        )
        if key in value
    }
    folder = value.get("studio_client_folder")
    if isinstance(folder, dict):
        projection["studio_client_folder"] = {
            key: folder.get(key)
            for key in (
                "schema_version",
                "studio_client_id",
                "scope_id",
                "scope_relative_dir",
                "display_name",
            )
            if key in folder
        }
    bindings = value.get("input_bindings")
    if isinstance(bindings, list):
        projection["input_bindings"] = [
            {
                key: binding.get(key)
                for key in (
                    "binding_id",
                    "byte_count",
                    "execution_relative_path",
                    "kind",
                    "receipt_relative_path",
                    "receipt_sha256",
                    "role",
                    "sha256",
                    "source_relative_path",
                    "upstream_artifact_id",
                    "upstream_run_id",
                    "upstream_workflow_id",
                )
                if key in binding
            }
            for binding in bindings
            if isinstance(binding, dict)
        ]
    return projection


def _portable_client_engagement_identity(value: object) -> object:
    """Project only the sealed path-free v2 run identity."""

    if not isinstance(value, dict):
        return value
    if value.get("schema_version") != "vera.client_workflow_context.v2":
        return value
    portable_fields = (
        "schema_version",
        "client_id",
        "engagement_id",
        "workflow_id",
        "workflow_version",
        "run_id",
        "label",
        "purpose",
        "created_at",
        "input_manifest",
        "input_manifest_sha256",
        "run_relative_path",
        "output_relative_path",
        "content_sha256",
    )
    return {field: value.get(field) for field in portable_fields}


def _source_preparation_material_projection(value: object) -> object:
    if not isinstance(value, dict):
        return value
    return {
        **value,
        **(
            {
                "client_engagement": _client_engagement_material_projection(
                    value["client_engagement"]
                )
            }
            if "client_engagement" in value
            else {}
        ),
    }


def _review_payload_material_projection(payload: dict[str, Any]) -> dict[str, Any]:
    """Return source/calculation-facing review data, excluding run-time metadata."""

    items = payload.get("items")
    if not isinstance(items, list):
        raise ValueError("review_payload.items must be a list")
    material_items = [
        item
        for item in items
        if isinstance(item, dict) and item.get("item_type") != "review_artifact"
    ]
    projection = {
        key: payload.get(key)
        for key in (
            "schema_version",
            "plugin",
            "workflow",
            "client_engagement",
            "language",
            "document_language",
            "source_paths",
            "review_type",
            "item_count",
            "columns",
            "source_artifacts",
            "allowed_actions",
            "status",
            "summary",
        )
    } | {"material_items": material_items}
    projection["client_engagement"] = _client_engagement_material_projection(
        payload.get("client_engagement")
    )
    return projection


def _run_intake_material_projection(
    value: dict[str, Any],
    *,
    recipe_reference: str | None = None,
) -> dict[str, Any]:
    projection = {
        key: value.get(key)
        for key in (
            "schema_version",
            "plugin",
            "workflow",
            "client_engagement",
            "language",
            "document_language",
            "input_paths",
            "inferred_task",
            "assumptions",
            "unresolved_questions",
            "dependency_check",
            "data_posture",
            "status",
        )
    }
    projection["client_engagement"] = _client_engagement_material_projection(
        value.get("client_engagement")
    )
    if recipe_reference is not None:
        assumptions = projection.get("assumptions")
        if isinstance(assumptions, dict):
            projection["assumptions"] = {
                **assumptions,
                "recipe_path": recipe_reference,
            }
        data_posture = projection.get("data_posture")
        if isinstance(data_posture, dict):
            local_files = data_posture.get("local_files_read")
            if isinstance(local_files, list):
                projection["data_posture"] = {
                    **data_posture,
                    "local_files_read": [
                        (
                            recipe_reference
                            if isinstance(item, str)
                            and Path(item).name == "execution_recipe.json"
                            else item
                        )
                        for item in local_files
                    ],
                }
    return projection


def _validate_rederived_material_state(
    output_dir: Path,
    audit: dict[str, Any],
    envelope: dict[str, Any],
    successor_decision: dict[str, Any] | None,
    client_engagement: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Freshly rerun every material check and compare the persisted successor."""

    run_intake = _read_json(
        _validate_run_file(
            output_dir,
            output_dir / "run_intake.json",
            "run intake",
        )
    )
    review_payload_path = _validate_run_file(
        output_dir,
        output_dir / "review_payload.json",
        "review payload",
    )
    review_payload = _read_json(review_payload_path)
    review_payload_digest = clean_text(review_payload.get("content_sha256"))
    review_payload_content = dict(review_payload)
    review_payload_content.pop("content_sha256", None)
    if not review_payload_digest or review_payload_digest != canonical_json_sha256(
        review_payload_content
    ):
        raise ValueError("review payload content hash is stale")
    if clean_text(run_intake.get("run_id")) != clean_text(
        audit.get("run_id")
    ) or clean_text(review_payload.get("run_id")) != clean_text(audit.get("run_id")):
        raise ValueError("Check Entries run identities do not close")
    recipe_path = _validated_execution_recipe(
        output_dir,
        audit,
        envelope,
        run_intake,
    )
    if not clean_text(audit.get("journal")) or not clean_text(audit.get("pdf_path")):
        raise ValueError("Check Entries original source paths are unavailable")
    journal = _resolve_persisted_run_path(
        output_dir,
        run_intake,
        audit.get("journal"),
    )
    support = _resolve_persisted_run_path(
        output_dir,
        run_intake,
        audit.get("pdf_path"),
    )

    with tempfile.TemporaryDirectory(
        prefix=".check-entries-material-replay-",
        dir=output_dir.parent,
    ) as temporary_name:
        replay_root = Path(temporary_name)
        replay_output = replay_root / "run"
        run_entry_checks(
            journal,
            support,
            replay_output,
            recipe_path,
            amount_tolerance=clean_text(audit.get("amount_tolerance")),
            date_window_days=audit.get("date_window_days"),
            language=audit.get("language"),
            document_language=audit.get("document_language"),
            connector_name=(
                clean_text(audit.get("connector_name"))
                if audit.get("connector_name") is not None
                else None
            ),
            client_engagement=(
                client_engagement
                if client_engagement is not None
                else (
                    run_intake.get("client_engagement")
                    if isinstance(run_intake.get("client_engagement"), dict)
                    else None
                )
            ),
            _enforce_client_output_path=False,
        )
        if (
            recipe_path is not None
            and _stable_regular_bytes(
                recipe_path,
                label="original Check Entries recipe",
            )
            != (output_dir / "execution_recipe.json").read_bytes()
        ):
            raise ValueError("original Check Entries recipe changed during replay")

        replay_audit = _read_json(replay_output / "check_audit.json")
        replay_envelope = _read_json(replay_output / "assurance_envelope.json")
        replay_payload = _read_json(replay_output / "review_payload.json")
        replay_intake = _read_json(replay_output / "run_intake.json")
        replay_final = _read_json(replay_output / "final_artifacts.json")

        immutable_paths = (
            "execution_recipe.json",
            "invoice_inventory.json",
            "normalized_entries.csv",
            "numeric_evidence_ledger.json",
            "pdf_inventory.json",
            "prepared_support_facts.csv",
            "review_notes.md",
            "support_manifest.json",
        )
        for relative_path in immutable_paths:
            if (output_dir / relative_path).read_bytes() != (
                replay_output / relative_path
            ).read_bytes():
                raise ValueError(
                    f"fresh Check Entries rederivation differs at {relative_path}"
                )

        edit_effects: list[dict[str, Any]] = []
        applied: dict[str, Any] | None = None
        if successor_decision is None:
            if (output_dir / "check_results.csv").read_bytes() != (
                replay_output / "check_results.csv"
            ).read_bytes():
                raise ValueError(
                    "check_results.csv differs from fresh deterministic rederivation"
                )
            if envelope.get("reviewed_decisions") != replay_envelope.get(
                "reviewed_decisions"
            ):
                raise ValueError(
                    "initial reviewed decisions differ from fresh rederivation"
                )
        else:
            applied_path = _validate_run_file(
                output_dir,
                output_dir / "applied_decisions.json",
                "applied decisions",
            )
            applied = _read_json(applied_path)
            edit_effects = _validate_review_application(
                output_dir,
                applied,
                review_payload,
            )
            expected_successor = _review_decision_receipt(
                applied,
                review_payload_digest=review_payload_digest,
            )
            if expected_successor != successor_decision:
                raise ValueError(
                    "applied decisions and effects do not match the successor receipt"
                )
            if envelope.get("reviewed_decisions") != [
                *replay_envelope.get("reviewed_decisions", []),
                successor_decision,
            ]:
                raise ValueError(
                    "successor reviewed decisions do not extend the fresh baseline"
                )
            _validate_csv_delta(
                replay_output / "check_results.csv",
                output_dir / "check_results.csv",
                edit_effects,
            )
            if edit_effects:
                first_backup = _expected_csv_backup_path(
                    output_dir,
                    clean_text(edit_effects[0].get("item_id")),
                )
                if (
                    first_backup.read_bytes()
                    != (replay_output / "check_results.csv").read_bytes()
                ):
                    raise ValueError(
                        "successor original CSV does not match fresh rederivation"
                    )

        if successor_decision is None or not edit_effects:
            expected_workbook = replay_output / "check_results.xlsx"
        else:
            expected_workbook = replay_root / "expected-check-results.xlsx"
            _write_check_results_workbook(
                output_dir / "check_results.csv",
                expected_workbook,
            )
        if (
            expected_workbook.read_bytes()
            != (output_dir / "check_results.xlsx").read_bytes()
        ):
            raise ValueError(
                "check_results.xlsx cells differ from the rederived CSV projection"
            )

        material_audit_fields = (
            "schema_version",
            "client_engagement",
            "language",
            "document_language",
            "journal",
            "pdf_path",
            "journal_row_count",
            "pdf_count",
            "invoice_count",
            "invoice_error_count",
            "connector_name",
            "result_row_count",
            "status_counts",
            "amount_tolerance",
            "date_window_days",
            "mapping",
            "source_preparation",
            "upstream_normalized_csv_receipt",
            "source_qualification",
            "support_manifest",
            "support_source_qualifications",
            "reviewed_recipe_decisions",
            "execution_recipe",
            "numeric_evidence_ledger",
            "reproducibility_checks",
            "input_artifact_receipts",
            "lineage",
            "assurance_gates",
            "professional_conclusion_status",
        )
        for field_name in material_audit_fields:
            current_value = audit.get(field_name)
            replay_value = replay_audit.get(field_name)
            if field_name == "client_engagement":
                current_value = _client_engagement_material_projection(current_value)
                replay_value = _client_engagement_material_projection(replay_value)
            elif field_name == "source_preparation":
                current_value = _source_preparation_material_projection(current_value)
                replay_value = _source_preparation_material_projection(replay_value)
            if current_value != replay_value:
                raise ValueError(
                    f"check_audit.json material field is not rederived: {field_name}"
                )
        for field_name in (
            "gate_register",
            "source_qualifications",
            "allocation_ledgers",
            "numeric_evidence_ledgers",
            "limitations",
        ):
            if envelope.get(field_name) != replay_envelope.get(field_name):
                raise ValueError(
                    f"assurance envelope material field is not rederived: {field_name}"
                )
        excluded_receipt_ids = {
            "output.0003",
            "output.0004",
            "source.review_payload",
        }
        current_receipts = {
            receipt["artifact_id"]: receipt
            for receipt in envelope.get("artifact_receipts", [])
            if isinstance(receipt, dict)
            and receipt.get("artifact_id") not in excluded_receipt_ids
        }
        replay_receipts = {
            receipt["artifact_id"]: receipt
            for receipt in replay_envelope.get("artifact_receipts", [])
            if isinstance(receipt, dict)
            and receipt.get("artifact_id") not in excluded_receipt_ids
        }
        if current_receipts != replay_receipts:
            raise ValueError(
                "assurance receipts differ from fresh deterministic rederivation"
            )
        if _review_payload_material_projection(
            review_payload
        ) != _review_payload_material_projection(replay_payload):
            raise ValueError(
                "review payload material projection differs from fresh rederivation"
            )
        current_intake_projection = _run_intake_material_projection(run_intake)
        current_assumptions = run_intake.get("assumptions")
        recipe_reference = (
            clean_text(current_assumptions.get("recipe_path"))
            if isinstance(current_assumptions, dict)
            else ""
        )
        replay_intake_projection = _run_intake_material_projection(
            replay_intake,
            recipe_reference=recipe_reference or None,
        )
        if current_intake_projection != replay_intake_projection:
            raise ValueError(
                "run intake material projection differs from fresh rederivation"
            )

        final_artifacts = _read_json(
            _validate_run_file(
                output_dir,
                output_dir / "final_artifacts.json",
                "final artifacts",
            )
        )
        if (
            final_artifacts.get("assurance_gates") != replay_envelope["gate_register"]
            or final_artifacts.get("professional_conclusion_status")
            != replay_audit["professional_conclusion_status"]
            or replay_envelope["gate_register"]["gates"]["publication"]["status"]
            != "withheld"
            or replay_envelope["gate_register"]["report_ready"] is not False
        ):
            raise ValueError(
                "final professional/gate state is not derived from replayed facts"
            )
        if successor_decision is None:
            if (
                final_artifacts.get("status") != replay_final.get("status")
                or final_artifacts.get("review_status") is not None
            ):
                raise ValueError("initial final status is not freshly derived")
        else:
            if applied is None:
                raise ValueError("successor applied decisions are unavailable")
            expected_status = _application_status(
                applied,
                {
                    "assurance_gates": replay_envelope["gate_register"],
                    "professional_conclusion_status": replay_audit[
                        "professional_conclusion_status"
                    ],
                },
            )
            if (
                applied.get("application_status") != expected_status
                or final_artifacts.get("status") != expected_status
                or final_artifacts.get("review_status") != expected_status
                or expected_status == "final_ready"
            ):
                raise ValueError("successor final status is not freshly derived")

        return {
            "gate_register": replay_envelope["gate_register"],
            "professional_conclusion_status": replay_audit[
                "professional_conclusion_status"
            ],
        }


def preflight_assurance(
    output_dir: Path,
    *,
    client_engagement: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Replay the persisted Check Entries assurance state before review writes."""

    output_dir = _validate_output_tree(output_dir)
    paths = _assurance_paths(output_dir)
    if paths is None:
        result = {
            "ok": True,
            "assurance_replayed": False,
            "report_ready": False,
            "professional_conclusion_status": None,
            "envelope_content_sha256": None,
        }
    else:
        envelope_path, audit_path = paths
        audit = _read_json(audit_path)
        envelope = _read_json(envelope_path)
        effective_client_engagement = client_engagement
        if effective_client_engagement is None:
            try:
                effective_client_engagement = load_client_workflow_context_for_output(
                    output_dir,
                    expected_workflow_id="check-entries",
                )
            except AssuranceContractError as exc:
                raise ValueError(
                    f"Check Entries current customer-run context is unavailable: {exc}"
                ) from exc
            persisted_intake = _read_json(output_dir / "run_intake.json")
            if _portable_client_engagement_identity(
                persisted_intake.get("client_engagement")
            ) != _portable_client_engagement_identity(effective_client_engagement):
                raise ValueError(
                    "Check Entries current customer-run context does not match "
                    "the persisted run identity"
                )
        artifact_roots = _artifact_roots(output_dir, audit)
        validated = validate_assurance_envelope(
            envelope,
            artifact_roots=artifact_roots,
        )
        validate_implementation_contract(
            validated,
            artifact_roots=artifact_roots,
        )
        _validate_audit_binding(output_dir, audit, validated)
        successor_decision = _review_successor_decision(validated)
        if successor_decision is None:
            validate_initial_output_set(output_dir)
        else:
            validate_review_successor_output_set(
                output_dir,
                successor_decision,
            )
        rederived = _validate_rederived_material_state(
            output_dir,
            audit,
            validated,
            successor_decision,
            effective_client_engagement,
        )
        result = {
            "ok": True,
            "assurance_replayed": True,
            "material_rederived": True,
            "report_ready": rederived["gate_register"]["report_ready"],
            "professional_conclusion_status": rederived[
                "professional_conclusion_status"
            ],
            "envelope_content_sha256": validated["content_sha256"],
        }
    _validate_output_tree(output_dir)
    return result


def _receipt_matches_file(receipt: dict[str, Any], path: Path) -> bool:
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    return (
        path.is_file()
        and receipt.get("byte_count") == path.stat().st_size
        and receipt.get("sha256") == digest
    )


def _expected_csv_backup_path(output_dir: Path, item_id: str) -> Path:
    return (
        output_dir
        / "revisions"
        / "originals"
        / f"check_results__{_safe_item_id(item_id)}.csv"
    )


def _review_items(review_payload: dict[str, Any]) -> dict[str, dict[str, Any]]:
    raw_items = review_payload.get("items")
    if not isinstance(raw_items, list):
        raise ValueError("review_payload.items must be a list")
    items: dict[str, dict[str, Any]] = {}
    for item in raw_items:
        if not isinstance(item, dict):
            raise ValueError("review_payload contains an invalid review item")
        item_id = clean_text(item.get("id"))
        if not item_id or item_id in items:
            raise ValueError(
                "review_payload item identities must be non-empty and unique"
            )
        items[item_id] = item
    if int(review_payload.get("item_count") or 0) != len(items):
        raise ValueError("review_payload item_count does not close")
    return items


def _validate_review_application(
    output_dir: Path,
    applied: dict[str, Any],
    review_payload: dict[str, Any],
) -> list[dict[str, Any]]:
    """Validate decisions and derive the only permitted Check Entries edit delta."""

    items = _review_items(review_payload)
    if clean_text(applied.get("plugin")) != clean_text(review_payload.get("plugin")):
        raise ValueError("applied decisions use a different plugin")
    if clean_text(applied.get("workflow")) != clean_text(
        review_payload.get("workflow")
    ):
        raise ValueError("applied decisions use a different workflow")
    if clean_text(applied.get("run_id")) != clean_text(review_payload.get("run_id")):
        raise ValueError("applied decisions use a different run")

    decisions = [
        decision
        for decision in applied.get("decisions", [])
        if isinstance(decision, dict)
    ]
    effects = [
        effect for effect in applied.get("effects", []) if isinstance(effect, dict)
    ]
    if (
        len(decisions) != int(applied.get("decision_count") or 0)
        or len(effects) != len(decisions)
        or int(applied.get("item_count") or 0) != len(items)
    ):
        raise ValueError("applied decision and effect counts do not close")

    effect_by_id: dict[str, dict[str, Any]] = {}
    for effect in effects:
        item_id = clean_text(effect.get("item_id"))
        if not item_id or item_id in effect_by_id:
            raise ValueError("applied effects must have unique review item identities")
        effect_by_id[item_id] = effect

    seen_decisions: set[str] = set()
    edit_effects: list[dict[str, Any]] = []
    for decision in decisions:
        item_id = clean_text(decision.get("item_id"))
        if not item_id or item_id in seen_decisions or item_id not in items:
            raise ValueError(
                "applied decisions contain an invalid review item identity"
            )
        seen_decisions.add(item_id)
        item = items[item_id]
        action = clean_text(decision.get("action"))
        allowed_actions = item.get("allowed_actions")
        if not isinstance(allowed_actions, list) or action not in allowed_actions:
            raise ValueError(f"review action is not allowed for item {item_id}")
        effect = effect_by_id.get(item_id)
        if effect is None or clean_text(effect.get("action")) != action:
            raise ValueError(f"review effect does not match decision {item_id}")
        if clean_text(effect.get("item_type")) != clean_text(item.get("item_type")):
            raise ValueError(f"review effect item type is stale for {item_id}")
        if clean_text(effect.get("title")) != clean_text(item.get("title")):
            raise ValueError(f"review effect title is stale for {item_id}")
        if action != "edit":
            if clean_text(decision.get("edit_value")) or clean_text(
                effect.get("edit_value")
            ):
                raise ValueError(f"non-edit decision carries an edit value: {item_id}")
            continue

        data = item.get("data")
        item_data = data if isinstance(data, dict) else {}
        expected = {
            "target_artifact": "check_results.csv",
            "target_id_field": "prepared_entry_id",
            "target_record_id": clean_text(item_data.get("target_record_id")),
            "target_field": "review_notes",
        }
        if (
            clean_text(item_data.get("target_artifact")) != expected["target_artifact"]
            or clean_text(item_data.get("target_id_field"))
            != expected["target_id_field"]
            or clean_text(item_data.get("target_field")) != expected["target_field"]
            or not expected["target_record_id"]
        ):
            raise ValueError(
                f"review item {item_id} does not authorize a Check Entries note edit"
            )
        edit_value = clean_text(decision.get("edit_value"))
        if not edit_value or clean_text(effect.get("edit_value")) != edit_value:
            raise ValueError(f"review edit value does not close for {item_id}")
        for field, expected_value in expected.items():
            if clean_text(effect.get(field)) != expected_value:
                raise ValueError(f"review effect {field} is stale for {item_id}")
        update = effect.get("structured_update")
        if not isinstance(update, dict):
            raise ValueError(f"review effect has no structured update for {item_id}")
        if (
            clean_text(update.get("id_field")) != expected["target_id_field"]
            or clean_text(update.get("record_id")) != expected["target_record_id"]
            or clean_text(update.get("target_field")) != expected["target_field"]
            or int(update.get("updated_rows") or 0) != 1
        ):
            raise ValueError(f"review structured update is stale for {item_id}")
        if effect.get("artifact_update") != "structured_artifact_updated":
            raise ValueError(f"review edit was not applied structurally for {item_id}")
        expected_backup = _expected_csv_backup_path(output_dir, item_id)
        actual_backup = output_dir / clean_text(effect.get("original_artifact_backup"))
        if actual_backup.resolve() != expected_backup.resolve():
            raise ValueError(f"review edit backup path is invalid for {item_id}")
        edit_effects.append(effect)
    return edit_effects


def _validate_csv_delta(
    original_path: Path,
    current_path: Path,
    edit_effects: list[dict[str, Any]],
) -> None:
    """Prove that only authorized review_notes cells changed."""

    original_header, original_rows = _csv_rows(original_path)
    current_header, current_rows = _csv_rows(current_path)
    if original_header != current_header or len(original_rows) != len(current_rows):
        raise ValueError("check_results.csv structure changed outside review authority")
    try:
        id_index = original_header.index("prepared_entry_id")
        notes_index = original_header.index("review_notes")
    except ValueError as exc:
        raise ValueError("check_results.csv lacks stable review edit columns") from exc
    authorized = {
        clean_text(effect.get("target_record_id")): clean_text(effect.get("edit_value"))
        for effect in edit_effects
    }
    if len(authorized) != len(edit_effects):
        raise ValueError("review edits contain duplicate prepared entry identities")
    seen: set[str] = set()
    for original_row, current_row in zip(original_rows, current_rows, strict=True):
        if len(original_row) != len(original_header) or len(current_row) != len(
            current_header
        ):
            raise ValueError("check_results.csv row width changed")
        record_id = original_row[id_index]
        if current_row[id_index] != record_id:
            raise ValueError("check_results.csv prepared identities changed")
        for column_index, (old_value, new_value) in enumerate(
            zip(original_row, current_row, strict=True)
        ):
            if old_value == new_value:
                continue
            if (
                column_index != notes_index
                or record_id not in authorized
                or new_value != authorized[record_id]
            ):
                raise ValueError(
                    "check_results.csv contains a change outside authorized review notes"
                )
        if record_id in authorized:
            if current_row[notes_index] != authorized[record_id]:
                raise ValueError(f"authorized review note was not applied: {record_id}")
            seen.add(record_id)
    if seen != set(authorized):
        raise ValueError("an authorized review row is missing from check_results.csv")


def _replay_prior_envelope(
    output_dir: Path,
    audit: dict[str, Any],
    envelope: dict[str, Any],
    *,
    edit_effects: list[dict[str, Any]],
) -> dict[str, Any]:
    """Replay the prior envelope against originals preserved by the review write."""

    _validate_audit_binding(output_dir, audit, envelope)
    artifact_roots = _artifact_roots(output_dir, audit)
    run_receipts = [
        receipt
        for receipt in envelope.get("artifact_receipts", [])
        if isinstance(receipt, dict) and receipt.get("root_id") == "run"
    ]
    results_receipt = next(
        (
            receipt
            for receipt in run_receipts
            if receipt.get("path") == "check_results.csv"
        ),
        None,
    )
    first_backup = (
        _expected_csv_backup_path(
            output_dir,
            clean_text(edit_effects[0].get("item_id")),
        )
        if edit_effects
        else None
    )
    if edit_effects:
        if (
            results_receipt is None
            or first_backup is None
            or not first_backup.is_file()
        ):
            raise ValueError("review edit has no receipted original check_results.csv")
        if not _receipt_matches_file(results_receipt, first_backup):
            raise ValueError(
                "review edit backup does not match the prior assurance receipt"
            )
        _validate_csv_delta(
            first_backup,
            output_dir / "check_results.csv",
            edit_effects,
        )

    with tempfile.TemporaryDirectory(prefix="check-entries-assurance-") as temp_name:
        staged_run = Path(temp_name)
        for receipt in run_receipts:
            relative = Path(str(receipt["path"]))
            source = (
                first_backup
                if edit_effects and relative.as_posix() == "check_results.csv"
                else output_dir / relative
            )
            target = staged_run / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, target)
        return validate_assurance_envelope(
            envelope,
            artifact_roots={**artifact_roots, "run": staged_run},
        )


def _reseal_assurance_after_review(
    output_dir: Path,
    applied: dict[str, Any],
    final_artifacts: dict[str, Any],
    *,
    canonical_output_dir: Path,
    envelope: dict[str, Any],
    review_payload_digest: str,
    review_payload_receipt: dict[str, Any],
    edit_effects: list[dict[str, Any]],
) -> None:
    """Reissue only authorized outputs and bind the persisted review decision."""

    envelope_path = output_dir / "assurance_envelope.json"
    audit_path = output_dir / "check_audit.json"
    audit = _read_json(audit_path)
    recorded_assurance = audit.get("assurance_envelope")
    recorded_assurance_path = (
        recorded_assurance.get("path") if isinstance(recorded_assurance, dict) else None
    )
    artifact_roots = _artifact_roots(output_dir, audit)
    changed_paths = (
        {"check_results.csv", "check_results.xlsx"} if edit_effects else set()
    )

    receipts: list[dict[str, Any]] = []
    for raw_receipt in envelope.get("artifact_receipts", []):
        if not isinstance(raw_receipt, dict):
            raise ValueError("assurance envelope contains an invalid artifact receipt")
        if raw_receipt.get("artifact_id") == review_payload_receipt["artifact_id"] or (
            raw_receipt.get("root_id") == "run"
            and raw_receipt.get("path") == review_payload_receipt["path"]
        ):
            continue
        receipts.append(
            _reissued_receipt(output_dir, raw_receipt)
            if raw_receipt.get("root_id") == "run"
            and raw_receipt.get("path") in changed_paths
            else raw_receipt
        )
    receipts.append(review_payload_receipt)
    decision_receipt = _review_decision_receipt(
        applied,
        review_payload_digest=review_payload_digest,
    )
    reviewed_decisions = [
        decision
        for decision in envelope.get("reviewed_decisions", [])
        if isinstance(decision, dict)
        and decision.get("decision_id") != decision_receipt["decision_id"]
    ]
    reviewed_decisions.append(decision_receipt)
    resealed = build_assurance_envelope(
        run_id=str(envelope["run_id"]),
        workflow_id=str(envelope["workflow_id"]),
        workflow_version=str(envelope["workflow_version"]),
        artifact_receipts=receipts,
        implementation_artifact_refs=envelope["implementation_artifact_refs"],
        reviewed_decisions=reviewed_decisions,
        source_qualifications=envelope["source_qualifications"],
        allocation_ledgers=envelope["allocation_ledgers"],
        numeric_evidence_ledgers=envelope["numeric_evidence_ledgers"],
        gate_register=envelope["gate_register"],
        limitations=envelope["limitations"],
        artifact_roots=artifact_roots,
    )
    validate_implementation_contract(
        resealed,
        artifact_roots=artifact_roots,
    )
    _write_json(envelope_path, resealed)
    envelope_receipt = artifact_receipt(
        output_dir,
        envelope_path,
        artifact_id="output.assurance_envelope",
        root_id="run",
        role="output",
        media_type="application/json",
    )

    audit["output_artifact_receipts"] = [
        receipt
        for receipt in receipts
        if receipt.get("root_id") == "run" and receipt.get("role") == "output"
    ] + [envelope_receipt]
    audit["review_payload_binding"] = {
        "content_sha256": review_payload_digest,
        "artifact_receipt": review_payload_receipt,
    }
    audit["reviewed_decisions"] = reviewed_decisions
    audit["assurance_envelope"] = {
        "path": (
            recorded_assurance_path
            if isinstance(recorded_assurance_path, str)
            and recorded_assurance_path.strip()
            else (canonical_output_dir / envelope_path.name).as_posix()
        ),
        "content_sha256": resealed["content_sha256"],
        "artifact_receipt": envelope_receipt,
    }
    audit.pop("content_sha256", None)
    audit["content_sha256"] = canonical_json_sha256(audit)
    _write_json(audit_path, audit)

    applied["review_decision_ref"] = decision_receipt["decision_id"]
    applied["assurance_replayed"] = True
    applied["assurance_envelope_content_sha256"] = resealed["content_sha256"]
    final_artifacts["assurance_gates"] = resealed["gate_register"]
    final_artifacts["assurance_envelope"] = audit["assurance_envelope"]
    final_artifacts["review_payload_content_sha256"] = review_payload_digest
    final_artifacts["review_decision_ref"] = decision_receipt["decision_id"]
    outputs = [
        output
        for output in final_artifacts.get("outputs", [])
        if isinstance(output, dict)
    ]
    existing_output_paths = {
        clean_text(output.get("path"))
        for output in outputs
        if isinstance(output, dict) and clean_text(output.get("path"))
    }
    current_run_receipts = [
        receipt
        for receipt in [*receipts, envelope_receipt]
        if receipt.get("root_id") == "run"
        and clean_text(receipt.get("path")) in existing_output_paths
    ]
    for receipt in current_run_receipts:
        _upsert_output(
            outputs,
            {
                "path": receipt["path"],
                "size_bytes": receipt["byte_count"],
                "artifact_receipt": receipt,
            },
        )
    _upsert_output(
        outputs,
        {
            "path": audit_path.name,
            "size_bytes": audit_path.stat().st_size,
        },
    )
    final_artifacts["outputs"] = outputs


def apply_review_edits(
    output_dir: Path,
    applied_decisions_path: Path,
    final_artifacts_path: Path,
    *,
    canonical_output_dir: Path | None = None,
) -> dict[str, Any]:
    """Apply authorized review-note edits and reseal any assurance envelope."""

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
    csv_path = output_dir / "check_results.csv"
    workbook_path = output_dir / "check_results.xlsx"

    applied = _read_json(applied_decisions_path)
    final_artifacts = _read_json(final_artifacts_path)
    effects = [
        effect for effect in applied.get("effects", []) if isinstance(effect, dict)
    ]
    candidate_effects = [
        effect for effect in effects if _eligible_check_results_effect(effect)
    ]
    assurance_paths = _assurance_paths(output_dir)
    if not candidate_effects and assurance_paths is None:
        return {
            "ok": True,
            "updated_effect_count": 0,
            "message": "No Check Entries workbook regeneration was required.",
        }

    envelope: dict[str, Any] | None = None
    audit: dict[str, Any] | None = None
    review_payload_digest: str | None = None
    review_payload_receipt: dict[str, Any] | None = None
    edit_effects = candidate_effects
    if assurance_paths is not None:
        envelope_path, audit_path = assurance_paths
        envelope = _read_json(envelope_path)
        audit = _read_json(audit_path)
        review_payload, review_payload_digest, review_payload_receipt = (
            _review_payload_binding(output_dir, applied)
        )
        edit_effects = _validate_review_application(
            output_dir,
            applied,
            review_payload,
        )
        if {id(effect) for effect in edit_effects} != {
            id(effect) for effect in candidate_effects
        }:
            raise ValueError(
                "review application contains an unsupported Check Entries edit"
            )
        validate_review_transition_output_set(output_dir, applied)
        envelope = _replay_prior_envelope(
            output_dir,
            audit,
            envelope,
            edit_effects=edit_effects,
        )

    if candidate_effects and not csv_path.exists():
        raise FileNotFoundError(csv_path)

    backup_outputs: list[dict[str, Any]] = []
    native_regenerated_paths: list[str] = []
    row_count = 0
    header: list[str] = []
    required_cells: dict[str, dict[str, str]] = {}
    if candidate_effects:
        backup = _backup_native(
            output_dir,
            clean_text(candidate_effects[0].get("item_id")),
            "check_results.xlsx",
        )
        if backup:
            backup_outputs.append(backup)

        header, rows = _csv_rows(csv_path)
        row_count = _write_check_results_workbook(csv_path, workbook_path)
        required_cells = _required_cells_for_effects(
            "Sheet1",
            header,
            rows,
            candidate_effects,
        )

        for effect in candidate_effects:
            effect["requires_native_regeneration"] = False
            effect["native_regeneration_status"] = "regenerated"
            effect["native_regenerated_paths"] = ["check_results.xlsx"]
        native_regenerated_paths = ["check_results.xlsx"]

    native_pending = _pending_native_paths(effects)
    applied["effects"] = effects
    applied["native_regeneration_count"] = len(native_pending)
    applied["native_regeneration_paths"] = native_pending
    applied["native_regenerated_count"] = len(candidate_effects)
    applied["native_regenerated_paths"] = native_regenerated_paths
    original_backup_paths = list(applied.get("original_backup_paths") or [])
    for backup_output in backup_outputs:
        if backup_output["path"] not in original_backup_paths:
            original_backup_paths.append(backup_output["path"])
    applied["original_backup_paths"] = original_backup_paths
    status_basis = final_artifacts
    if envelope is not None and audit is not None:
        status_basis = {
            "assurance_gates": envelope["gate_register"],
            "professional_conclusion_status": audit.get(
                "professional_conclusion_status"
            ),
        }
    applied["application_status"] = _application_status(applied, status_basis)

    outputs = [
        output
        for output in final_artifacts.get("outputs", [])
        if isinstance(output, dict)
    ]
    if candidate_effects:
        _upsert_output(
            outputs,
            {
                "path": "check_results.xlsx",
                "kind": "xlsx",
                "status": "updated_from_review",
                "native_regenerated": True,
                "source_artifact": "check_results.csv",
                "source_row_count": row_count,
                "size_bytes": workbook_path.stat().st_size,
                "required_sheets": ["Sheet1"],
                "required_sheet_headers": {
                    "Sheet1": [value for value in header if value]
                },
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

    if (
        envelope is not None
        and review_payload_digest is not None
        and review_payload_receipt is not None
    ):
        _reseal_assurance_after_review(
            output_dir,
            applied,
            final_artifacts,
            canonical_output_dir=canonical_output_dir,
            envelope=envelope,
            review_payload_digest=review_payload_digest,
            review_payload_receipt=review_payload_receipt,
            edit_effects=edit_effects,
        )
    _write_json(applied_decisions_path, applied)
    _write_json(final_artifacts_path, final_artifacts)
    _validate_output_tree(output_dir)
    if envelope is not None:
        successor_envelope = _read_json(output_dir / "assurance_envelope.json")
        successor_decision = _review_successor_decision(successor_envelope)
        if successor_decision is None:
            raise ValueError("Check Entries review successor is missing.")
        validate_review_successor_output_set(
            output_dir,
            successor_decision,
        )
    return {
        "ok": True,
        "updated_effect_count": len(candidate_effects),
        "native_regenerated_paths": native_regenerated_paths,
        "backup_paths": [backup_output["path"] for backup_output in backup_outputs],
        "application_status": applied["application_status"],
        "assurance_replayed": envelope is not None,
        "applied_decisions": applied,
        "final_artifacts": final_artifacts,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Apply Check Entries review edits and regenerate native outputs."
    )
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--applied-decisions", type=Path)
    parser.add_argument("--final-artifacts", type=Path)
    parser.add_argument("--canonical-output-dir", type=Path)
    parser.add_argument(
        "--client-run-preflight-only",
        action="store_true",
        help="Validate the owning running customer-folder run without writing.",
    )
    parser.add_argument(
        "--preflight-only",
        action="store_true",
        help="Replay persisted assurance before any review artifacts are written.",
    )
    args = parser.parse_args(argv)
    client_output_dir = args.canonical_output_dir or args.output_dir
    try:
        client_context = load_client_workflow_context_for_output(
            client_output_dir.expanduser().resolve(),
            expected_workflow_id="check-entries",
        )
    except AssuranceContractError as exc:
        parser.error(str(exc))
    if args.client_run_preflight_only:
        result = {
            "ok": True,
            "schema_version": client_context["schema_version"],
            "workflow_id": client_context["workflow_id"],
            "client_run_id": client_context["run_id"],
        }
        sys.stdout.write(json.dumps(result, ensure_ascii=False) + "\n")
        return 0
    if args.preflight_only:
        result = preflight_assurance(
            args.output_dir,
            client_engagement=client_context,
        )
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
