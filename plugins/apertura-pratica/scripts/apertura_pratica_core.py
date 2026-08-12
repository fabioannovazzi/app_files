from __future__ import annotations

import hashlib
import json
import mimetypes
import os
import re
import shutil
import stat
import tempfile
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping, Sequence

from jsonschema import Draft202012Validator, FormatChecker

__all__ = [
    "REQUIRED_REVIEW_SCOPES",
    "ValidationError",
    "add_evidence",
    "apply_decisions",
    "build_default_intake",
    "canonical_json_hash",
    "initialize_workspace",
    "load_json",
    "prepare_review",
    "review_payload_hash",
    "utc_now",
    "validate_run",
    "write_json",
]

PLUGIN_ROOT = Path(__file__).resolve().parents[1]
SCHEMA_ROOT = PLUGIN_ROOT / "schemas"
INTAKE_SCHEMA_PATH = SCHEMA_ROOT / "matter_intake.schema.json"
DECISIONS_SCHEMA_PATH = SCHEMA_ROOT / "ui_decisions.schema.json"
SOURCE_REGISTRY_PATH = PLUGIN_ROOT / "references" / "source-registry.json"
MARKER_NAME = ".apertura-pratica.json"
INTAKE_NAME = "matter_intake.json"
WORKFLOW_ID = "apertura-pratica"
SCHEMA_VERSION = "1.0"
MAX_EVIDENCE_BYTES = 250 * 1024 * 1024
REQUIRED_REVIEW_SCOPES = ("conflict", "engagement", "deadlines", "opening")
REFERENCE_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.:-]{2,95}$")


class ValidationError(ValueError):
    """Raised when a mechanical workflow contract is not satisfied."""


def utc_now() -> str:
    """Return one canonical UTC timestamp."""

    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def canonical_json_bytes(payload: Mapping[str, Any] | Sequence[Any]) -> bytes:
    """Return stable UTF-8 JSON bytes for digest binding."""

    return json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def canonical_json_hash(payload: Mapping[str, Any] | Sequence[Any]) -> str:
    """Hash a JSON value using the workflow's canonical serialization."""

    return hashlib.sha256(canonical_json_bytes(payload)).hexdigest()


def review_payload_hash(payload: Mapping[str, Any]) -> str:
    """Hash substantive review content while ignoring its render timestamp."""

    stable = dict(payload)
    stable.pop("generated_at", None)
    return canonical_json_hash(stable)


def load_json(path: Path) -> dict[str, Any]:
    """Read one JSON object from a regular file."""

    candidate = path.expanduser()
    if candidate.is_symlink() or not candidate.is_file():
        raise ValidationError(f"JSON file is unavailable or linked: {candidate}")
    try:
        payload = json.loads(candidate.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValidationError(f"JSON file is unreadable: {candidate}: {exc}") from exc
    if not isinstance(payload, dict):
        raise ValidationError(f"JSON root must be an object: {candidate}")
    return payload


def _atomic_write(path: Path, content: bytes) -> None:
    """Write owner-only bytes atomically inside an existing directory."""

    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{path.name}.", suffix=".tmp", dir=path.parent
    )
    temporary = Path(temporary_name)
    try:
        os.fchmod(descriptor, 0o600)
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
        path.chmod(0o600)
    finally:
        if temporary.exists():
            temporary.unlink()


def write_json(path: Path, payload: Mapping[str, Any] | Sequence[Any]) -> None:
    """Write stable, readable JSON with owner-only permissions."""

    content = (
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    ).encode("utf-8")
    _atomic_write(path, content)


def _write_text(path: Path, content: str) -> None:
    _atomic_write(path, content.encode("utf-8"))


def _load_schema(path: Path) -> dict[str, Any]:
    return load_json(path)


def _schema_errors(payload: Mapping[str, Any], schema_path: Path) -> list[str]:
    validator = Draft202012Validator(
        _load_schema(schema_path), format_checker=FormatChecker()
    )
    return [
        f"{'.'.join(str(part) for part in error.path) or '$'}: {error.message}"
        for error in sorted(
            validator.iter_errors(payload), key=lambda item: list(item.path)
        )
    ]


def _repo_root() -> Path | None:
    candidate = PLUGIN_ROOT.parents[1]
    return candidate if (candidate / ".git").exists() else None


def _assert_outside_repo(path: Path) -> None:
    root = _repo_root()
    if root is None:
        return
    resolved = path.expanduser().resolve()
    if resolved == root or root in resolved.parents:
        raise ValidationError(
            "Apertura pratica outputs must stay outside this Git workspace."
        )


def _managed_context(
    run_dir: Path, *, input_paths: Sequence[Path] = ()
) -> dict[str, Any] | None:
    """Validate an optional Studio Archive context owning this output path."""

    output_root = next(
        (
            ancestor
            for ancestor in (run_dir, *run_dir.parents)
            if ancestor.name == "outputs"
            and (ancestor.parent / "context.json").is_file()
        ),
        None,
    )
    if output_root is None:
        return None
    import sys

    studio_scripts = PLUGIN_ROOT.parent / "studio-archive" / "scripts"
    if not studio_scripts.is_dir():
        raise ValidationError(
            "The shared Studio Archive ledger is unavailable for this managed run."
        )
    if str(studio_scripts) not in sys.path:
        sys.path.insert(0, str(studio_scripts))
    try:
        import client_ledger as ledger  # type: ignore[import-not-found]
    except ImportError as exc:
        raise ValidationError(
            "The shared Studio Archive ledger cannot be loaded for this managed run."
        ) from exc
    try:
        context = load_json(output_root.parent / "context.json")
        engagement_id = str(context["engagement_id"])
        run_id = str(context["run_id"])
        client_root = output_root.parents[5]
        loaded = ledger.load_run(
            client_root,
            engagement_id,
            run_id,
            verify_inputs=True,
        )
        if loaded["run"]["workflow_id"] != WORKFLOW_ID:
            raise ValidationError("Managed run belongs to another workflow.")
        if Path(loaded["output_dir"]).resolve() != output_root.resolve():
            raise ValidationError("Managed run output path does not match its ledger.")
        allowed_inputs = {
            Path(binding["path"]).resolve()
            for binding in loaded["context"]["input_bindings"]
        }
        outside = [path for path in input_paths if path.resolve() not in allowed_inputs]
        if outside:
            raise ValidationError(
                "Managed evidence must come from the run's exact immutable input view."
            )
        return dict(loaded["context"])
    except (KeyError, IndexError, ledger.LedgerError) as exc:
        raise ValidationError(
            f"Managed client-engagement context is invalid: {exc}"
        ) from exc


def _run_dir(path: Path, *, require_marker: bool = True) -> Path:
    candidate = path.expanduser()
    if not candidate.is_absolute():
        candidate = candidate.resolve()
    if candidate.is_symlink():
        raise ValidationError("Run directory must not be a symbolic link.")
    resolved = candidate.resolve()
    _assert_outside_repo(resolved)
    if require_marker and not (resolved / MARKER_NAME).is_file():
        raise ValidationError(f"Not an Apertura pratica run: {resolved}")
    _managed_context(resolved)
    return resolved


def _review(
    status: str = "pending", basis: str = "Professional review required."
) -> dict[str, Any]:
    return {"status": status, "reviewer": None, "reviewed_at": None, "basis": basis}


def build_default_intake(
    *,
    run_id: str,
    opening_mode: str,
    client_reference: str,
    matter_reference: str,
    language: str,
) -> dict[str, Any]:
    """Build a schema-valid intake whose unresolved decisions stay explicit."""

    return {
        "schema_version": SCHEMA_VERSION,
        "run_id": run_id,
        "language": language,
        "professional_country": "IT",
        "opening_mode": opening_mode,
        "client": {
            "reference": client_reference,
            "display_name": None,
            "relationship_status": (
                "prospective" if opening_mode == "new_client_new_matter" else "existing"
            ),
            "identity_status": "unknown",
            "evidence_ids": [],
        },
        "matter": {
            "reference": matter_reference,
            "title": None,
            "objective": None,
            "requested_work": None,
            "summary": None,
            "jurisdiction": {
                "status": "unknown",
                "primary": None,
                "additional": [],
                "basis": "Confirm applicable law, forum and any cross-border elements.",
            },
            "procedural_posture": None,
            "urgency": "unknown",
        },
        "confirmed_facts": [],
        "parties": [
            {
                "party_id": "party-client-001",
                "display_name": client_reference,
                "party_type": "unknown",
                "roles": ["client"],
                "aliases": [],
                "identity_keys": [],
                "identity_status": "unknown",
                "evidence_ids": [],
                "assessment_basis": "Placeholder created at intake; verify identity and role.",
            }
        ],
        "evidence_register": [],
        "conflict_check": {
            "register_scope": "unavailable",
            "register_snapshot_reference": None,
            "searched_at": None,
            "searched_party_ids": [],
            "search_method": "No approved client/matter register has been searched.",
            "candidates": [],
            "professional_decision": {
                "status": "pending",
                "reviewer": None,
                "reviewed_at": None,
                "basis": "Conflict review has not been completed.",
            },
        },
        "engagement": {
            "scope_items": [
                {
                    "scope_id": "scope-001",
                    "description": "Define the requested legal work.",
                    "status": "proposed",
                    "evidence_ids": [],
                }
            ],
            "exclusions": [],
            "authority_status": "unknown",
            "fee_terms_status": "missing",
            "engagement_document_status": "missing",
            "professional_owner": None,
            "review": _review(
                basis="Confirm scope, exclusions, authority and engagement status."
            ),
        },
        "deadline_review": {
            "status": "pending",
            "candidates": [],
            "basis": "Identify and professionally confirm or reject every possible deadline.",
            "reviewer": None,
            "reviewed_at": None,
        },
        "confidentiality": {
            "classification": "confidential_legal_matter",
            "external_disclosure_status": "not_requested",
            "restricted_material": [],
            "handling_notes": "Keep matter material inside the selected private workspace.",
            "review": _review(
                basis="Confirm matter-specific secrecy and handling restrictions."
            ),
        },
        "aml": {
            "applicability": "uncertain",
            "basis": "Assess applicability from the concrete legal service; do not infer it from client novelty.",
            "source_ids": ["d-lgs-231-2007"],
            "review": _review(basis="Professional AML applicability review required."),
            "separate_assessment_status": "not_started",
        },
        "privacy_retention": {
            "notice_status": "unknown",
            "retention_policy_reference": None,
            "handling_notes": "Use only approved firm templates and retention policies.",
            "review": _review(basis="Confirm privacy notice and retention posture."),
        },
        "missing_items": [
            {
                "item_id": "missing-client-identity",
                "kind": "identity",
                "description": "Verify the client and assisted-party identity and role.",
                "blocking": True,
                "status": "open",
                "evidence_ids": [],
            },
            {
                "item_id": "missing-conflict-register",
                "kind": "register",
                "description": "Search the complete approved client/matter register for every relevant party.",
                "blocking": True,
                "status": "open",
                "evidence_ids": [],
            },
        ],
        "folder_plan": [
            {
                "path": "00_Intake",
                "purpose": "Opening evidence and intake decisions",
                "source_evidence_ids": [],
                "status": "proposed",
            },
            {
                "path": "01_Incarico",
                "purpose": "Engagement scope, terms and approvals",
                "source_evidence_ids": [],
                "status": "proposed",
            },
            {
                "path": "02_Evidenze",
                "purpose": "Matter evidence received or acquired",
                "source_evidence_ids": [],
                "status": "proposed",
            },
            {
                "path": "03_Ricerca",
                "purpose": "Research plans, authorities and validation",
                "source_evidence_ids": [],
                "status": "proposed",
            },
            {
                "path": "04_Elaborati",
                "purpose": "Draft and reviewed work product",
                "source_evidence_ids": [],
                "status": "proposed",
            },
            {
                "path": "05_Corrispondenza",
                "purpose": "Matter correspondence",
                "source_evidence_ids": [],
                "status": "proposed",
            },
        ],
        "model_assessment": {
            "provider": None,
            "model": None,
            "recorded_at": None,
            "assumptions": [],
            "unresolved_questions": [],
        },
    }


def initialize_workspace(
    output_dir: Path,
    *,
    opening_mode: str,
    client_reference: str,
    matter_reference: str,
    language: str,
) -> Path:
    """Create a fresh private run without modifying any source document."""

    if not REFERENCE_RE.fullmatch(client_reference) or not REFERENCE_RE.fullmatch(
        matter_reference
    ):
        raise ValidationError(
            "Client and matter references must be stable safe identifiers."
        )
    candidate = output_dir.expanduser()
    if not candidate.is_absolute():
        candidate = candidate.resolve()
    _assert_outside_repo(candidate)
    if candidate.exists() and candidate.is_symlink():
        raise ValidationError("Output directory must not be a symbolic link.")
    candidate.mkdir(parents=True, exist_ok=True, mode=0o700)
    existing = [path for path in candidate.iterdir() if path.name != "context.json"]
    if existing:
        raise ValidationError(
            "Output directory must be fresh or contain only its managed context."
        )
    candidate.chmod(0o700)
    context = _managed_context(candidate)
    run_id = (
        str(context["run_id"])
        if context is not None
        else f"apertura-{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}-{uuid.uuid4().hex[:8]}"
    )
    marker = {
        "schema_version": SCHEMA_VERSION,
        "workflow": WORKFLOW_ID,
        "run_id": run_id,
        "created_at": utc_now(),
        "storage_mode": (
            "studio_archive" if context is not None else "standalone_private"
        ),
    }
    write_json(candidate / MARKER_NAME, marker)
    intake = build_default_intake(
        run_id=run_id,
        opening_mode=opening_mode,
        client_reference=client_reference,
        matter_reference=matter_reference,
        language=language,
    )
    write_json(candidate / INTAKE_NAME, intake)
    (candidate / "evidence").mkdir(mode=0o700)
    run_intake = {
        "schema_version": SCHEMA_VERSION,
        "workflow": WORKFLOW_ID,
        "run_id": run_id,
        "created_at": marker["created_at"],
        "output_dir": candidate.as_posix(),
        "language": language,
        "storage_mode": marker["storage_mode"],
        "source_paths": [INTAKE_NAME],
        "local_data_posture": {
            "files_read_locally": True,
            "real_case_data_may_enter_selected_model_context": True,
            "automatic_anonymization": False,
            "external_connectors_used": [],
            "mparanza_receives_case_files": False,
        },
    }
    write_json(candidate / "run_intake.json", run_intake)
    return candidate


def _secure_source(path: Path) -> tuple[os.stat_result, int]:
    source = path.expanduser()
    if not source.is_absolute():
        source = source.resolve()
    try:
        before = source.lstat()
    except OSError as exc:
        raise ValidationError(f"Evidence source is unavailable: {exc}") from exc
    if source.is_symlink() or not stat.S_ISREG(before.st_mode):
        raise ValidationError("Evidence source must be an ordinary non-linked file.")
    if before.st_size > MAX_EVIDENCE_BYTES:
        raise ValidationError(f"Evidence file exceeds {MAX_EVIDENCE_BYTES} bytes.")
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
    try:
        descriptor = os.open(source, flags)
    except OSError as exc:
        raise ValidationError(
            f"Evidence source cannot be opened safely: {exc}"
        ) from exc
    opened = os.fstat(descriptor)
    if (
        before.st_dev,
        before.st_ino,
        before.st_size,
        before.st_mtime_ns,
    ) != (opened.st_dev, opened.st_ino, opened.st_size, opened.st_mtime_ns):
        os.close(descriptor)
        raise ValidationError("Evidence source changed before it was opened.")
    return before, descriptor


def add_evidence(run_dir: Path, source: Path, *, role: str) -> dict[str, Any]:
    """Snapshot one exact source and register its immutable receipt."""

    root = _run_dir(run_dir)
    source = source.expanduser()
    if not source.is_absolute():
        source = source.resolve()
    _managed_context(root, input_paths=[source])
    before, descriptor = _secure_source(source)
    digest = hashlib.sha256()
    evidence_id = f"evidence-{uuid.uuid4().hex[:12]}"
    target_dir = root / "evidence" / evidence_id
    target_dir.mkdir(mode=0o700)
    target = target_dir / source.name
    try:
        with (
            os.fdopen(descriptor, "rb") as read_handle,
            target.open("xb") as write_handle,
        ):
            target.chmod(0o600)
            while True:
                chunk = read_handle.read(1024 * 1024)
                if not chunk:
                    break
                digest.update(chunk)
                write_handle.write(chunk)
            write_handle.flush()
            os.fsync(write_handle.fileno())
        after = source.stat()
        if (
            before.st_dev,
            before.st_ino,
            before.st_size,
            before.st_mtime_ns,
        ) != (after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns):
            raise ValidationError("Evidence source changed while it was copied.")
        if target.stat().st_size != before.st_size:
            raise ValidationError("Evidence copy size does not match the source.")
        intake_path = root / INTAKE_NAME
        intake = load_json(intake_path)
        existing = next(
            (
                item
                for item in intake.get("evidence_register", [])
                if item.get("sha256") == digest.hexdigest()
                and item.get("bytes") == before.st_size
            ),
            None,
        )
        if existing is not None:
            target.unlink()
            target_dir.rmdir()
            return dict(existing)
        record = {
            "evidence_id": evidence_id,
            "stored_path": target.relative_to(root).as_posix(),
            "original_name": source.name,
            "sha256": digest.hexdigest(),
            "bytes": before.st_size,
            "media_type": mimetypes.guess_type(source.name)[0]
            or "application/octet-stream",
            "role": role,
            "review_status": "unreviewed",
            "captured_at": utc_now(),
        }
        intake.setdefault("evidence_register", []).append(record)
        errors = _schema_errors(intake, INTAKE_SCHEMA_PATH)
        if errors:
            raise ValidationError("Updated intake is invalid: " + "; ".join(errors[:5]))
        write_json(intake_path, intake)
        return record
    except (OSError, ValidationError):
        if target.exists():
            target.unlink()
        if target_dir.exists():
            target_dir.rmdir()
        raise


def _hash_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _unique(records: Sequence[Mapping[str, Any]], key: str, label: str) -> list[str]:
    values = [record.get(key) for record in records]
    duplicates = sorted({str(value) for value in values if values.count(value) > 1})
    return [f"{label} contains duplicate {key}: {value}" for value in duplicates]


def _known_source_ids() -> set[str]:
    registry = load_json(SOURCE_REGISTRY_PATH)
    return {str(item["id"]) for item in registry.get("sources", [])}


def _validate_evidence(
    root: Path, intake: Mapping[str, Any]
) -> tuple[list[str], list[str]]:
    blockers: list[str] = []
    warnings: list[str] = []
    evidence = intake.get("evidence_register", [])
    blockers.extend(_unique(evidence, "evidence_id", "evidence_register"))
    hash_ids: dict[tuple[str, int], list[str]] = {}
    for record in evidence:
        relative = Path(str(record["stored_path"]))
        if relative.is_absolute() or ".." in relative.parts:
            blockers.append(f"Evidence path escapes the run: {relative}")
            continue
        candidate = root / relative
        if candidate.is_symlink() or not candidate.is_file():
            blockers.append(f"Evidence file is unavailable: {relative}")
            continue
        size = candidate.stat().st_size
        if size != record["bytes"]:
            blockers.append(f"Evidence size drift: {record['evidence_id']}")
            continue
        digest = _hash_file(candidate)
        if digest != record["sha256"]:
            blockers.append(f"Evidence hash drift: {record['evidence_id']}")
        hash_ids.setdefault((digest, size), []).append(str(record["evidence_id"]))
    for ids in hash_ids.values():
        if len(ids) > 1:
            warnings.append("Exact duplicate evidence receipts: " + ", ".join(ids))
    return blockers, warnings


def _referential_errors(intake: Mapping[str, Any]) -> list[str]:
    errors: list[str] = []
    evidence_ids = {str(item["evidence_id"]) for item in intake["evidence_register"]}
    party_ids = {str(item["party_id"]) for item in intake["parties"]}
    source_ids = _known_source_ids()
    records_with_evidence: list[tuple[str, Mapping[str, Any]]] = [
        ("client", intake["client"]),
        *((f"party:{item['party_id']}", item) for item in intake["parties"]),
        *(
            (f"conflict:{item['candidate_id']}", item)
            for item in intake["conflict_check"]["candidates"]
        ),
        *(
            (f"scope:{item['scope_id']}", item)
            for item in intake["engagement"]["scope_items"]
        ),
        *(
            (f"deadline:{item['deadline_id']}", item)
            for item in intake["deadline_review"]["candidates"]
        ),
        *((f"missing:{item['item_id']}", item) for item in intake["missing_items"]),
    ]
    for label, record in records_with_evidence:
        unknown = sorted(set(record.get("evidence_ids", [])) - evidence_ids)
        if unknown:
            errors.append(f"{label} references unknown evidence: {', '.join(unknown)}")
    for item in intake["folder_plan"]:
        unknown = sorted(set(item["source_evidence_ids"]) - evidence_ids)
        if unknown:
            errors.append(
                f"folder:{item['path']} references unknown evidence: {', '.join(unknown)}"
            )
    conflict = intake["conflict_check"]
    unknown_searched = sorted(set(conflict["searched_party_ids"]) - party_ids)
    if unknown_searched:
        errors.append(
            "Conflict search references unknown parties: " + ", ".join(unknown_searched)
        )
    for candidate in conflict["candidates"]:
        unknown = sorted(set(candidate["subject_party_ids"]) - party_ids)
        if unknown:
            errors.append(
                f"Conflict candidate {candidate['candidate_id']} references unknown parties: "
                + ", ".join(unknown)
            )
    unknown_sources = sorted(set(intake["aml"]["source_ids"]) - source_ids)
    if unknown_sources:
        errors.append(
            "AML review references unknown source IDs: " + ", ".join(unknown_sources)
        )
    return errors


def _professional_gate_errors(intake: Mapping[str, Any]) -> tuple[list[str], list[str]]:
    blockers: list[str] = []
    warnings: list[str] = []
    if not intake["evidence_register"] and not intake["confirmed_facts"]:
        blockers.append(
            "No snapshotted evidence or explicitly confirmed fact is available."
        )
    if intake["client"]["identity_status"] != "verified":
        blockers.append("Client identity is not verified.")
    party_roles = {role for party in intake["parties"] for role in party["roles"]}
    if "client" not in party_roles or "assisted_party" not in party_roles:
        blockers.append(
            "The party map must identify both client and assisted party roles."
        )
    matter = intake["matter"]
    for field in ("title", "objective", "requested_work", "summary"):
        if not matter[field]:
            blockers.append(f"Matter {field} is unresolved.")
    if matter["jurisdiction"]["status"] != "confirmed":
        blockers.append("Matter jurisdiction is not professionally confirmed.")

    conflict = intake["conflict_check"]
    if conflict["register_scope"] != "complete":
        blockers.append("Conflict-check register scope is not complete.")
    if not conflict["searched_at"] or not conflict["searched_party_ids"]:
        blockers.append("Conflict-check search evidence is incomplete.")
    unresolved_candidates = [
        item["candidate_id"]
        for item in conflict["candidates"]
        if item["resolution"]["status"] in {"pending", "insufficient_data"}
    ]
    if unresolved_candidates:
        blockers.append(
            "Unresolved conflict candidates: " + ", ".join(unresolved_candidates)
        )
    if any(
        item["resolution"]["status"] == "conflict" for item in conflict["candidates"]
    ):
        blockers.append(
            "A conflict candidate is professionally resolved as a conflict."
        )
    if conflict["professional_decision"]["status"] != "cleared":
        blockers.append(
            "The lawyer has not recorded a current conflict clearance decision."
        )

    engagement = intake["engagement"]
    if any(item["status"] == "proposed" for item in engagement["scope_items"]):
        blockers.append("Engagement scope still contains unconfirmed proposals.")
    if engagement["authority_status"] not in {"verified", "not_applicable"}:
        blockers.append("Authority to instruct or represent is unresolved.")
    if engagement["fee_terms_status"] not in {"accepted", "not_applicable"}:
        blockers.append("Fee terms are not accepted or marked not applicable.")
    if engagement["engagement_document_status"] not in {"accepted", "not_required"}:
        blockers.append(
            "Engagement document is not accepted or professionally marked not required."
        )
    if not engagement["professional_owner"]:
        blockers.append("Responsible lawyer is not recorded.")
    if engagement["review"]["status"] != "confirmed":
        blockers.append("Engagement scope has not been professionally confirmed.")

    deadlines = intake["deadline_review"]
    if deadlines["status"] == "pending":
        blockers.append("Deadline review is pending.")
    for deadline in deadlines["candidates"]:
        if deadline["status"] == "candidate":
            blockers.append(f"Deadline remains a candidate: {deadline['deadline_id']}")
        if deadline["status"] == "confirmed" and not deadline["due_at"]:
            blockers.append(
                f"Confirmed deadline has no due_at: {deadline['deadline_id']}"
            )
        if deadline["status"] in {"confirmed", "rejected"} and (
            not deadline["reviewer"] or not deadline["reviewed_at"]
        ):
            blockers.append(
                f"Deadline decision lacks reviewer receipt: {deadline['deadline_id']}"
            )
    if deadlines["status"] == "confirmed_none" and deadlines["candidates"]:
        blockers.append("confirmed_none cannot retain deadline candidates.")

    if intake["confidentiality"]["review"]["status"] != "confirmed":
        blockers.append(
            "Confidentiality handling has not been professionally confirmed."
        )
    aml = intake["aml"]
    if aml["review"]["status"] != "confirmed":
        blockers.append("AML applicability has not been professionally confirmed.")
    if aml["applicability"] == "uncertain":
        blockers.append("AML applicability remains uncertain.")
    if (
        aml["applicability"] == "applicable"
        and aml["separate_assessment_status"] != "completed"
    ):
        blockers.append("Applicable AML assessment is not complete.")
    if (
        aml["applicability"] == "not_applicable"
        and aml["separate_assessment_status"] != "not_required"
    ):
        blockers.append("AML not-applicable posture is structurally inconsistent.")
    if intake["privacy_retention"]["review"]["status"] != "confirmed":
        blockers.append(
            "Privacy and retention posture has not been professionally confirmed."
        )

    open_blockers = [
        item["item_id"]
        for item in intake["missing_items"]
        if item["blocking"] and item["status"] == "open"
    ]
    if open_blockers:
        blockers.append(
            "Blocking intake items remain open: " + ", ".join(open_blockers)
        )
    open_nonblockers = [
        item["item_id"]
        for item in intake["missing_items"]
        if not item["blocking"] and item["status"] == "open"
    ]
    if open_nonblockers:
        warnings.append(
            "Non-blocking intake items remain open: " + ", ".join(open_nonblockers)
        )
    if any(item["status"] == "proposed" for item in intake["folder_plan"]):
        warnings.append(
            "Folder plan still contains proposals; no file operation is authorized."
        )
    assessment = intake["model_assessment"]
    if (
        not assessment["provider"]
        or not assessment["model"]
        or not assessment["recorded_at"]
    ):
        blockers.append("Model assessment provenance is incomplete.")
    if assessment["unresolved_questions"]:
        warnings.append("Model assessment retains unresolved questions.")
    return blockers, warnings


def _current_review_receipts(
    root: Path, intake_sha256: str
) -> tuple[dict[str, Any], list[str]]:
    path = root / "review_receipts.json"
    if not path.exists():
        return {}, []
    receipts = load_json(path)
    warnings: list[str] = []
    if receipts.get("intake_sha256") != intake_sha256:
        warnings.append(
            "Professional review receipts are stale for the current intake."
        )
        return {}, warnings
    scopes = receipts.get("scopes")
    if not isinstance(scopes, dict):
        warnings.append("Professional review receipts have no valid scope map.")
        return {}, warnings
    return scopes, warnings


def validate_run(run_dir: Path) -> dict[str, Any]:
    """Validate the exact intake and return the specialised gate report."""

    root = _run_dir(run_dir)
    intake = load_json(root / INTAKE_NAME)
    schema_errors = _schema_errors(intake, INTAKE_SCHEMA_PATH)
    blockers = list(schema_errors)
    warnings: list[str] = []
    if not schema_errors:
        blockers.extend(_unique(intake["parties"], "party_id", "parties"))
        blockers.extend(
            _unique(
                intake["conflict_check"]["candidates"],
                "candidate_id",
                "conflict candidates",
            )
        )
        blockers.extend(
            _unique(intake["engagement"]["scope_items"], "scope_id", "engagement scope")
        )
        blockers.extend(
            _unique(
                intake["deadline_review"]["candidates"],
                "deadline_id",
                "deadline candidates",
            )
        )
        blockers.extend(_unique(intake["missing_items"], "item_id", "missing items"))
        evidence_blockers, evidence_warnings = _validate_evidence(root, intake)
        blockers.extend(evidence_blockers)
        warnings.extend(evidence_warnings)
        blockers.extend(_referential_errors(intake))
        gate_blockers, gate_warnings = _professional_gate_errors(intake)
        blockers.extend(gate_blockers)
        warnings.extend(gate_warnings)
    intake_sha256 = canonical_json_hash(intake)
    scopes, receipt_warnings = _current_review_receipts(root, intake_sha256)
    warnings.extend(receipt_warnings)
    accepted_scopes = sorted(
        scope
        for scope, receipt in scopes.items()
        if isinstance(receipt, dict) and receipt.get("decision") == "accepted"
    )
    current_reviews_complete = set(accepted_scopes) == set(REQUIRED_REVIEW_SCOPES)
    if blockers:
        status = "blocked"
    elif current_reviews_complete:
        status = "ready_to_open"
    elif warnings:
        status = "partial"
    else:
        status = "ready_for_review"
    return {
        "schema_version": SCHEMA_VERSION,
        "workflow": WORKFLOW_ID,
        "run_id": intake.get("run_id"),
        "validated_at": utc_now(),
        "validator": "apertura_pratica_validator_v1",
        "intake_sha256": intake_sha256,
        "status": status,
        "blockers": sorted(set(blockers)),
        "warnings": sorted(set(warnings)),
        "required_review_scopes": list(REQUIRED_REVIEW_SCOPES),
        "accepted_review_scopes": accepted_scopes,
        "mechanical_boundary": (
            "Schema, hashes, reference closure, receipt freshness and review completeness only; "
            "legal meaning, conflict, deadline and applicability remain lawyer decisions."
        ),
    }


def _item(
    item_id: str,
    *,
    scope: str,
    item_type: str,
    title: str,
    status: str,
    recommended_action: str,
    data: Mapping[str, Any],
    evidence_ids: Sequence[str] = (),
) -> dict[str, Any]:
    return {
        "id": item_id,
        "scope": scope,
        "item_type": item_type,
        "title": title,
        "status": status,
        "allowed_actions": ["accept", "return", "reject"],
        "recommended_action": recommended_action,
        "data": dict(data),
        "evidence_ids": list(evidence_ids),
    }


def _build_review_payload(
    intake: Mapping[str, Any], report: Mapping[str, Any]
) -> dict[str, Any]:
    conflict = intake["conflict_check"]
    engagement = intake["engagement"]
    deadlines = intake["deadline_review"]
    items = [
        _item(
            "review-conflict-scope",
            scope="conflict",
            item_type="conflict_scope",
            title="Perimetro e risultato del controllo conflitti",
            status=conflict["professional_decision"]["status"],
            recommended_action=(
                "accept"
                if conflict["register_scope"] == "complete"
                and conflict["professional_decision"]["status"] == "cleared"
                else "return"
            ),
            data={
                "register_scope": conflict["register_scope"],
                "register_snapshot_reference": conflict["register_snapshot_reference"],
                "searched_at": conflict["searched_at"],
                "searched_party_ids": conflict["searched_party_ids"],
                "search_method": conflict["search_method"],
                "professional_decision": conflict["professional_decision"],
            },
        ),
        _item(
            "review-engagement",
            scope="engagement",
            item_type="engagement",
            title="Perimetro e condizioni dell'incarico",
            status=engagement["review"]["status"],
            recommended_action=(
                "accept" if engagement["review"]["status"] == "confirmed" else "return"
            ),
            data=engagement,
            evidence_ids=[
                evidence_id
                for scope_item in engagement["scope_items"]
                for evidence_id in scope_item["evidence_ids"]
            ],
        ),
        _item(
            "review-deadline-posture",
            scope="deadlines",
            item_type="deadline_posture",
            title="Esito della revisione delle scadenze",
            status=deadlines["status"],
            recommended_action=(
                "accept" if deadlines["status"] != "pending" else "return"
            ),
            data={
                key: deadlines[key]
                for key in ("status", "basis", "reviewer", "reviewed_at")
            },
        ),
        _item(
            "review-party-map",
            scope="opening",
            item_type="party_map",
            title="Soggetti e ruoli della pratica",
            status="proposed",
            recommended_action="accept",
            data={"client": intake["client"], "parties": intake["parties"]},
        ),
        _item(
            "review-confidentiality",
            scope="opening",
            item_type="confidentiality",
            title="Riserbo e trattamento del fascicolo",
            status=intake["confidentiality"]["review"]["status"],
            recommended_action=(
                "accept"
                if intake["confidentiality"]["review"]["status"] == "confirmed"
                else "return"
            ),
            data=intake["confidentiality"],
        ),
        _item(
            "review-aml",
            scope="opening",
            item_type="aml_applicability",
            title="Applicabilità antiriciclaggio",
            status=intake["aml"]["review"]["status"],
            recommended_action=(
                "accept"
                if intake["aml"]["review"]["status"] == "confirmed"
                and intake["aml"]["applicability"] != "uncertain"
                else "return"
            ),
            data=intake["aml"],
        ),
        _item(
            "review-privacy-retention",
            scope="opening",
            item_type="privacy_retention",
            title="Privacy e conservazione",
            status=intake["privacy_retention"]["review"]["status"],
            recommended_action=(
                "accept"
                if intake["privacy_retention"]["review"]["status"] == "confirmed"
                else "return"
            ),
            data=intake["privacy_retention"],
        ),
        _item(
            "review-folder-plan",
            scope="opening",
            item_type="folder_plan",
            title="Piano del fascicolo, senza operazioni sui file",
            status=(
                "accepted"
                if all(item["status"] == "accepted" for item in intake["folder_plan"])
                else "proposed"
            ),
            recommended_action="accept",
            data={"folders": intake["folder_plan"]},
        ),
    ]
    for candidate in conflict["candidates"]:
        resolution = candidate["resolution"]["status"]
        items.append(
            _item(
                f"review-conflict-{candidate['candidate_id']}",
                scope="conflict",
                item_type="conflict_candidate",
                title=f"Candidato conflitto · {candidate['matched_reference']}",
                status=resolution,
                recommended_action=(
                    "accept" if resolution == "no_conflict" else "return"
                ),
                data=candidate,
                evidence_ids=candidate["evidence_ids"],
            )
        )
    for deadline in deadlines["candidates"]:
        items.append(
            _item(
                f"review-deadline-{deadline['deadline_id']}",
                scope="deadlines",
                item_type="deadline_candidate",
                title=f"Scadenza possibile · {deadline['description']}",
                status=deadline["status"],
                recommended_action=(
                    "accept"
                    if deadline["status"] in {"confirmed", "rejected"}
                    else "return"
                ),
                data=deadline,
                evidence_ids=deadline["evidence_ids"],
            )
        )
    for missing in intake["missing_items"]:
        items.append(
            _item(
                f"review-missing-{missing['item_id']}",
                scope="opening",
                item_type="missing_item",
                title=f"Informazione mancante · {missing['description']}",
                status=missing["status"],
                recommended_action=(
                    "return" if missing["status"] == "open" else "accept"
                ),
                data=missing,
                evidence_ids=missing["evidence_ids"],
            )
        )
    payload = {
        "schema_version": SCHEMA_VERSION,
        "workflow": WORKFLOW_ID,
        "run_id": intake["run_id"],
        "language": intake["language"],
        "review_type": "legal_matter_opening",
        "status": report["status"],
        "intake_sha256": report["intake_sha256"],
        "generated_at": utc_now(),
        "required_scopes": list(REQUIRED_REVIEW_SCOPES),
        "source_paths": [INTAKE_NAME, "validation_report.json", "folder_plan.json"],
        "local_data_posture": {
            "real_case_data_may_enter_selected_model_context": True,
            "automatic_anonymization": False,
            "external_connector_used": False,
            "review_ui": "local_only",
        },
        "items": items,
        "item_count": len(items),
    }
    return payload


_HEADINGS = {
    "it": ("Memo di apertura pratica", "Informazioni e documenti mancanti"),
    "en": ("Matter-opening memo", "Missing information and documents"),
    "fr": ("Mémo d'ouverture du dossier", "Informations et documents manquants"),
    "de": ("Mandatseröffnungsvermerk", "Fehlende Informationen und Unterlagen"),
    "es": ("Memorando de apertura del asunto", "Información y documentos pendientes"),
}


def _matter_memo(intake: Mapping[str, Any], report: Mapping[str, Any]) -> str:
    title, _ = _HEADINGS[intake["language"]]
    parties = "\n".join(
        f"- {item['display_name']} — {', '.join(item['roles'])} — {item['identity_status']}"
        for item in intake["parties"]
    )
    blockers = "\n".join(f"- {item}" for item in report["blockers"]) or "- None"
    warnings = "\n".join(f"- {item}" for item in report["warnings"]) or "- None"
    return (
        f"# {title}\n\n"
        f"**Status:** `{report['status']}`  \n"
        f"**Client:** {intake['client']['display_name'] or intake['client']['reference']}  \n"
        f"**Matter:** {intake['matter']['title'] or intake['matter']['reference']}  \n"
        f"**Jurisdiction:** {intake['matter']['jurisdiction']['primary'] or 'unresolved'}  \n"
        f"**Opening mode:** `{intake['opening_mode']}`\n\n"
        "## Objective\n\n"
        f"{intake['matter']['objective'] or 'Unresolved'}\n\n"
        "## Requested work\n\n"
        f"{intake['matter']['requested_work'] or 'Unresolved'}\n\n"
        "## Parties\n\n"
        f"{parties}\n\n"
        "## Conflict posture\n\n"
        f"Register scope: `{intake['conflict_check']['register_scope']}`; "
        f"professional decision: `{intake['conflict_check']['professional_decision']['status']}`.\n\n"
        "## Deadline posture\n\n"
        f"`{intake['deadline_review']['status']}` with "
        f"{len(intake['deadline_review']['candidates'])} recorded candidate(s).\n\n"
        "## Blockers\n\n"
        f"{blockers}\n\n"
        "## Warnings\n\n"
        f"{warnings}\n\n"
        "This memo is a review artifact. It is not conflict clearance, engagement acceptance, "
        "a binding deadline calculation, or legal advice.\n"
    )


def _missing_request(intake: Mapping[str, Any]) -> str:
    _, title = _HEADINGS[intake["language"]]
    open_items = [item for item in intake["missing_items"] if item["status"] == "open"]
    body = "\n".join(f"- {item['description']}" for item in open_items) or "- None"
    return (
        f"# {title}\n\n{body}\n\n"
        "Draft for lawyer review. Do not send until recipient, wording, confidentiality and "
        "matter identity have been confirmed.\n"
    )


def _artifact_manifest(
    root: Path, names: Sequence[str], *, status: str
) -> dict[str, Any]:
    artifacts = []
    for name in names:
        path = root / name
        if not path.is_file():
            continue
        artifacts.append(
            {
                "path": name,
                "bytes": path.stat().st_size,
                "sha256": _hash_file(path),
                "purpose": "Apertura pratica review and audit artifact",
            }
        )
    return {
        "schema_version": SCHEMA_VERSION,
        "workflow": WORKFLOW_ID,
        "generated_at": utc_now(),
        "status": status,
        "artifacts": artifacts,
    }


def prepare_review(run_dir: Path) -> dict[str, Any]:
    """Write the complete specialised review package for the current intake."""

    root = _run_dir(run_dir)
    report = validate_run(root)
    intake = load_json(root / INTAKE_NAME)
    review_payload = _build_review_payload(intake, report)
    write_json(root / "validation_report.json", report)
    write_json(root / "review_payload.json", review_payload)
    write_json(root / "folder_plan.json", {"folders": intake["folder_plan"]})
    _write_text(root / "matter_opening_memo.md", _matter_memo(intake, report))
    _write_text(root / "missing_information_request.md", _missing_request(intake))
    _write_text(
        root / "review_handoff.md",
        "# Apertura pratica · review\n\n"
        f"Current status: `{report['status']}`. Review every item in `review_payload.json` "
        "through the local workbench or an equivalent explicitly confirmed review. "
        "No source file operation is authorized by this package.\n",
    )
    _write_text(
        root / "codex_run_review.md",
        "# Apertura pratica · stato del run\n\n"
        f"Status: `{report['status']}`  \n"
        f"Blockers: {len(report['blockers'])}  \n"
        f"Warnings: {len(report['warnings'])}  \n\n"
        "Use `review_payload.json` for the item review and `review_handoff.md` "
        "for the professional boundary.\n",
    )
    names = (
        INTAKE_NAME,
        "run_intake.json",
        "validation_report.json",
        "review_payload.json",
        "folder_plan.json",
        "matter_opening_memo.md",
        "missing_information_request.md",
        "review_handoff.md",
        "codex_run_review.md",
        "review_decisions.json",
        "applied_decisions.json",
        "review_receipts.json",
    )
    manifest = _artifact_manifest(root, names, status=str(report["status"]))
    write_json(root / "artifact_manifest.json", manifest)
    final_artifacts = {
        "schema_version": SCHEMA_VERSION,
        "workflow": WORKFLOW_ID,
        "run_id": intake["run_id"],
        "status": report["status"],
        "intake_sha256": report["intake_sha256"],
        "blockers": report["blockers"],
        "warnings": report["warnings"],
        "professional_review_required": True,
        "conflict_cleared_by_software": False,
        "deadline_confirmed_by_software": False,
        "engagement_accepted_by_software": False,
        "source_files_modified": False,
        "artifacts": [item["path"] for item in manifest["artifacts"]],
    }
    write_json(root / "final_artifacts.json", final_artifacts)
    return final_artifacts


def _validate_decisions(
    decisions: Mapping[str, Any],
    *,
    intake: Mapping[str, Any],
    review_payload: Mapping[str, Any],
) -> None:
    errors = _schema_errors(decisions, DECISIONS_SCHEMA_PATH)
    if errors:
        raise ValidationError("Review decisions are invalid: " + "; ".join(errors[:10]))
    if decisions["run_id"] != intake["run_id"]:
        raise ValidationError("Review decisions belong to a different run.")
    if decisions["intake_sha256"] != canonical_json_hash(intake):
        raise ValidationError("Review decisions are stale for the current intake.")
    if decisions["review_payload_sha256"] != review_payload_hash(review_payload):
        raise ValidationError(
            "Review decisions are stale for the current review payload."
        )
    item_by_id = {str(item["id"]): item for item in review_payload["items"]}
    seen: set[str] = set()
    for decision in decisions["decisions"]:
        item_id = str(decision["item_id"])
        if item_id in seen:
            raise ValidationError(f"Duplicate review decision: {item_id}")
        seen.add(item_id)
        if item_id not in item_by_id:
            raise ValidationError(
                f"Review decision references an unknown item: {item_id}"
            )


def apply_decisions(
    run_dir: Path,
    decisions_path: Path,
    *,
    confirmed_by_user: bool,
) -> dict[str, Any]:
    """Persist scope receipts bound to the exact current intake and review payload."""

    if not confirmed_by_user:
        raise ValidationError("Applying review requires explicit user confirmation.")
    root = _run_dir(run_dir)
    decisions = load_json(decisions_path)
    intake = load_json(root / INTAKE_NAME)
    review_payload = load_json(root / "review_payload.json")
    _validate_decisions(decisions, intake=intake, review_payload=review_payload)
    item_by_id = {str(item["id"]): item for item in review_payload["items"]}
    decisions_by_scope: dict[str, list[dict[str, Any]]] = {
        scope: [] for scope in REQUIRED_REVIEW_SCOPES
    }
    for decision in decisions["decisions"]:
        scope = str(item_by_id[str(decision["item_id"])]["scope"])
        decisions_by_scope[scope].append(dict(decision))
    scopes: dict[str, Any] = {}
    for scope in REQUIRED_REVIEW_SCOPES:
        expected_ids = {
            str(item["id"])
            for item in review_payload["items"]
            if item["scope"] == scope
        }
        observed = decisions_by_scope[scope]
        observed_ids = {str(item["item_id"]) for item in observed}
        actions = {str(item["action"]) for item in observed}
        if observed_ids != expected_ids:
            decision = "pending"
        elif "reject" in actions:
            decision = "rejected"
        elif "return" in actions:
            decision = "returned"
        elif actions == {"accept"}:
            decision = "accepted"
        else:
            decision = "pending"
        scopes[scope] = {
            "decision": decision,
            "reviewer": decisions["reviewer"],
            "reviewed_at": decisions["saved_at"],
            "item_ids": sorted(observed_ids),
            "notes": [item["note"] for item in observed if item["note"]],
        }
    receipts = {
        "schema_version": SCHEMA_VERSION,
        "workflow": WORKFLOW_ID,
        "run_id": intake["run_id"],
        "intake_sha256": canonical_json_hash(intake),
        "review_payload_sha256": review_payload_hash(review_payload),
        "applied_at": utc_now(),
        "reviewer": decisions["reviewer"],
        "scopes": scopes,
    }
    write_json(root / "review_decisions.json", decisions)
    write_json(root / "applied_decisions.json", receipts)
    write_json(root / "review_receipts.json", receipts)
    prepare_review(root)
    return receipts
