#!/usr/bin/env python3
"""Core contracts for Vera professional communications."""

from __future__ import annotations

import hashlib
import importlib
import json
import os
import re
import shutil
import stat
import tempfile
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Iterator

import jsonschema

__all__ = [
    "ALLOWED_CHANNELS",
    "PLUGIN_ROOT",
    "REQUIRED_REVIEW_SCOPES",
    "atomic_copy_file",
    "atomic_write_text",
    "atomic_write_json",
    "canonical_digest",
    "copy_input_snapshot",
    "file_digest",
    "fresh_package_review_decision",
    "fresh_review_decisions",
    "fresh_render_review_decision",
    "load_json",
    "load_workspace",
    "package_digest",
    "recompute_contribution_digest",
    "recompute_input_digest",
    "required_review_scopes",
    "require_accepted_reviews",
    "require_accepted_package_review",
    "require_accepted_render_review",
    "run_dir_from_workspace",
    "utc_now",
    "validate_contribution_semantics",
    "validate_finalized_package",
    "validate_input_integrity",
    "validate_schema",
    "verify_visual_manifest",
    "verify_package_manifest",
    "workflow_lock",
]

PLUGIN_ROOT = Path(__file__).resolve().parents[1]
SCHEMA_ROOT = PLUGIN_ROOT / "schemas"
ALLOWED_CHANNELS = {
    "client_email",
    "client_circular",
    "linkedin",
    "newsletter",
    "website_article",
    "client_alert",
    "faq",
}
REQUIRED_REVIEW_SCOPES = (
    "recommendation",
    "source_basis",
    "claims",
    "copy",
    "visual_story",
)
_SECRET_KEYS = {
    "password",
    "passcode",
    "pin",
    "otp",
    "one_time_code",
    "cookie",
    "session_cookie",
    "token",
    "api_key",
    "client_secret",
    "private_key",
    "secret_key",
    "credential",
    "credentials",
}


def utc_now() -> str:
    """Return a stable UTC timestamp without fractional seconds."""

    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def load_json(path: Path) -> dict[str, Any]:
    """Read one JSON object."""

    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"JSON object required: {path}")
    return payload


def atomic_write_json(path: Path, payload: dict[str, Any]) -> Path:
    """Write one JSON object atomically with owner-only default permissions."""

    path.parent.mkdir(parents=True, exist_ok=True)
    handle, temp_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    temp_path = Path(temp_name)
    try:
        with os.fdopen(handle, "w", encoding="utf-8") as stream:
            json.dump(payload, stream, ensure_ascii=False, indent=2, sort_keys=True)
            stream.write("\n")
        os.chmod(temp_path, 0o600)
        temp_path.replace(path)
    finally:
        if temp_path.exists():
            temp_path.unlink()
    return path


def atomic_write_text(path: Path, content: str) -> Path:
    """Write UTF-8 text atomically with owner-only permissions."""

    path.parent.mkdir(parents=True, exist_ok=True)
    handle, temp_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    temp_path = Path(temp_name)
    try:
        with os.fdopen(handle, "w", encoding="utf-8") as stream:
            stream.write(content)
        os.chmod(temp_path, 0o600)
        temp_path.replace(path)
    finally:
        if temp_path.exists():
            temp_path.unlink()
    return path


def atomic_copy_file(source: Path, destination: Path) -> Path:
    """Copy one regular file atomically and keep the destination owner-only."""

    source_path = source.resolve(strict=True)
    if source.is_symlink() or not source_path.is_file():
        raise ValueError(f"Source must be a regular non-symlink file: {source}")
    destination.parent.mkdir(parents=True, exist_ok=True)
    handle, temp_name = tempfile.mkstemp(
        prefix=f".{destination.name}.", dir=destination.parent
    )
    os.close(handle)
    temp_path = Path(temp_name)
    try:
        shutil.copyfile(source_path, temp_path)
        os.chmod(temp_path, 0o600)
        temp_path.replace(destination)
    finally:
        if temp_path.exists():
            temp_path.unlink()
    return destination


@contextmanager
def workflow_lock(root: Path) -> Iterator[None]:
    """Serialize mutations with an OS lock because concurrent writes are unsafe."""

    root.mkdir(parents=True, exist_ok=True)
    lock_path = root / ".comunicazione-professionale.lock"
    flags = os.O_CREAT | os.O_RDWR
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    descriptor = os.open(lock_path, flags, stat.S_IRUSR | stat.S_IWUSR)
    with os.fdopen(descriptor, "r+", encoding="utf-8") as handle:
        metadata = os.fstat(handle.fileno())
        if not stat.S_ISREG(metadata.st_mode) or metadata.st_nlink != 1:
            raise ValueError("Workflow mutation lock must be one regular file")
        os.fchmod(handle.fileno(), stat.S_IRUSR | stat.S_IWUSR)
        try:
            if os.name == "nt":
                lock_module = importlib.import_module("msvcrt")
                handle.seek(0)
                if not handle.read(1):
                    handle.write("\0")
                    handle.flush()
                handle.seek(0)
                lock_module.locking(handle.fileno(), lock_module.LK_NBLCK, 1)
            else:
                lock_module = importlib.import_module("fcntl")
                lock_module.flock(
                    handle.fileno(), lock_module.LOCK_EX | lock_module.LOCK_NB
                )
        except OSError as exc:
            raise ValueError(
                "Another professional-communication mutation is in progress"
            ) from exc
        handle.seek(0)
        handle.truncate()
        handle.write(f"pid={os.getpid()} acquired_at={utc_now()}\n")
        handle.flush()
        try:
            yield
        finally:
            if os.name == "nt":
                handle.seek(0)
                lock_module.locking(handle.fileno(), lock_module.LK_UNLCK, 1)
            else:
                lock_module.flock(handle.fileno(), lock_module.LOCK_UN)


def canonical_digest(payload: object) -> str:
    """Hash canonical JSON for review freshness and replay evidence."""

    data = json.dumps(
        payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    return hashlib.sha256(data).hexdigest()


def file_digest(path: Path) -> str:
    """Return the SHA-256 digest of one regular file."""

    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def validate_schema(payload: dict[str, Any], schema_name: str) -> None:
    """Validate a payload with an exhaustive bundled JSON Schema."""

    schema = load_json(SCHEMA_ROOT / schema_name)
    validator = jsonschema.Draft202012Validator(
        schema,
        format_checker=jsonschema.FormatChecker(),
    )
    errors = sorted(validator.iter_errors(payload), key=lambda item: list(item.path))
    if errors:
        messages = [
            f"{'/'.join(str(part) for part in error.path) or '<root>'}: {error.message}"
            for error in errors
        ]
        raise ValueError("Schema validation failed:\n- " + "\n- ".join(messages))


def _normalized_key(value: object) -> str:
    return re.sub(r"[^a-z0-9]+", "_", str(value).lower()).strip("_")


def _reject_secret_fields(value: object, *, path: tuple[str, ...] = ()) -> None:
    if isinstance(value, dict):
        for key, child in value.items():
            normalized = _normalized_key(key)
            if normalized in _SECRET_KEYS:
                raise ValueError(
                    f"Secret or session field is prohibited: {'/'.join((*path, str(key)))}"
                )
            _reject_secret_fields(child, path=(*path, str(key)))
    elif isinstance(value, list):
        for index, child in enumerate(value):
            _reject_secret_fields(child, path=(*path, str(index)))


def load_workspace(workspace: Path) -> dict[str, Any]:
    """Load and verify the exact path-bound private workspace."""

    root = workspace.expanduser().resolve()
    manifest_path = root / "workspace.json"
    if not manifest_path.is_file():
        raise ValueError(f"Workspace manifest not found: {manifest_path}")
    payload = load_json(manifest_path)
    validate_schema(payload, "workspace.schema.json")
    if Path(payload["bound_path"]).resolve() != root:
        raise ValueError("Workspace moved or bound_path does not match")
    return payload


def run_dir_from_workspace(workspace: Path, run_id: str) -> Path:
    """Resolve one run directory without allowing path traversal."""

    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]{2,79}", run_id):
        raise ValueError("Invalid run_id")
    root = workspace.expanduser().resolve()
    run_dir = (root / "runs" / run_id).resolve()
    if not run_dir.is_relative_to(root):
        raise ValueError("Run directory escapes workspace")
    return run_dir


def copy_input_snapshot(
    source: Path,
    *,
    destination_dir: Path,
    identity: str,
) -> dict[str, Any]:
    """Copy an explicitly selected real file into the private run snapshot."""

    source_path = source.expanduser().resolve(strict=True)
    if source.is_symlink() or not source_path.is_file():
        raise ValueError(f"Input must be a regular non-symlink file: {source}")
    safe_name = re.sub(r"[^A-Za-z0-9_.-]+", "-", source_path.name).strip("-.")
    target = destination_dir / f"{identity}-{safe_name or 'input'}"
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.exists():
        raise ValueError(f"Input snapshot already exists: {target}")
    shutil.copyfile(source_path, target)
    os.chmod(target, 0o600)
    return {
        "snapshot_path": str(target.resolve()),
        "original_name": source_path.name,
        "sha256": file_digest(target),
        "size_bytes": target.stat().st_size,
    }


def _bound_snapshot_path(run_dir: Path, row: dict[str, Any]) -> Path:
    path = Path(str(row.get("snapshot_path", ""))).resolve()
    if not path.is_relative_to(run_dir.resolve()):
        raise ValueError(f"Input snapshot escapes run directory: {path}")
    return path


def _input_digest_payload(
    intake: dict[str, Any], source_register: dict[str, Any]
) -> dict[str, Any]:
    stable_intake = {
        key: value for key, value in intake.items() if key != "input_digest"
    }
    return {"intake": stable_intake, "source_register": source_register}


def recompute_input_digest(run_dir: Path) -> str:
    """Recompute the exact prepared-input digest from current run records."""

    root = run_dir.resolve()
    intake = load_json(root / "run_intake.json")
    source_register = load_json(root / "source_register.json")
    return canonical_digest(_input_digest_payload(intake, source_register))


def validate_input_integrity(run_dir: Path) -> str:
    """Reject changed input records, snapshots, stored profiles, or brand assets."""

    root = run_dir.resolve()
    intake = load_json(root / "run_intake.json")
    source_register = load_json(root / "source_register.json")
    expected = str(intake.get("input_digest") or "")
    current = canonical_digest(_input_digest_payload(intake, source_register))
    if not expected or current != expected:
        raise ValueError("Prepared input digest mismatch")
    rows = [*source_register.get("sources", []), *source_register.get("history", [])]
    for optional_key in ("brand_logo", "studio_profile"):
        optional = source_register.get(optional_key)
        if isinstance(optional, dict):
            rows.append(optional)
    for row in rows:
        path = _bound_snapshot_path(root, row)
        if not path.is_file():
            raise ValueError(f"Missing input snapshot: {path}")
        if path.stat().st_size != row.get("size_bytes"):
            raise ValueError(f"Input snapshot size mismatch: {path}")
        if file_digest(path) != row.get("sha256"):
            raise ValueError(f"Input snapshot hash mismatch: {path}")
    return current


def recompute_contribution_digest(run_dir: Path) -> str:
    """Recompute the reviewed contribution digest from current exact content."""

    root = run_dir.resolve()
    input_digest = validate_input_integrity(root)
    workbench = load_json(root / "content_workbench.json")
    version = workbench.get("version")
    if not isinstance(version, int) or version < 1:
        raise ValueError("Contribution version is invalid")
    version_path = root / "versions" / f"content_workbench-v{version:03d}.json"
    if not version_path.is_file():
        raise ValueError("Immutable contribution version snapshot is missing")
    version_snapshot = load_json(version_path)
    if canonical_digest(version_snapshot) != canonical_digest(workbench):
        raise ValueError(
            "Current workbench differs from its immutable version snapshot"
        )
    if workbench.get("input_digest") != input_digest:
        raise ValueError("Contribution is bound to stale prepared inputs")
    current = canonical_digest(
        {
            "input_digest": input_digest,
            "contribution": workbench.get("contribution"),
            "provenance": workbench.get("model_provenance"),
        }
    )
    if current != workbench.get("contribution_digest"):
        raise ValueError("Current contribution digest mismatch")
    return current


def _unique(values: Iterable[str], label: str) -> None:
    items = list(values)
    if len(items) != len(set(items)):
        raise ValueError(f"Duplicate {label}")


def required_review_scopes(
    contribution: dict[str, Any], *, visual_requested: bool
) -> list[str]:
    """Return mechanical review scopes implied by generated artifact classes."""

    if contribution["recommendation"] == "no_publish":
        scopes = ["recommendation", "editorial_value", "source_basis"]
        if contribution["studio_profile_proposal"] is not None:
            scopes.append("studio_profile")
        return scopes
    scopes = ["recommendation", "editorial_value", "source_basis", "claims", "copy"]
    if contribution["studio_profile_proposal"] is not None:
        scopes.append("studio_profile")
    if visual_requested:
        scopes.append("visual_story")
    return scopes


def fresh_review_decisions(run_dir: Path) -> dict[str, dict[str, Any]]:
    """Return the latest review event for each scope on the current digest."""

    workbench = load_json(run_dir / "content_workbench.json")
    current_digest = recompute_contribution_digest(run_dir)
    review_log = load_json(run_dir / "review_log.json")
    decisions: dict[str, dict[str, Any]] = {}
    for event in review_log.get("events", []):
        if event.get("contribution_digest") != current_digest:
            continue
        if event.get("input_digest") != workbench["input_digest"]:
            continue
        decisions[str(event["scope"])] = event
    return decisions


def _visual_manifest_digest(payload: dict[str, Any]) -> str:
    stable = {key: value for key, value in payload.items() if key != "manifest_digest"}
    return canonical_digest(stable)


def verify_visual_manifest(run_dir: Path) -> str:
    """Verify rendered-file hashes and geometry recorded by the renderer."""

    root = run_dir.resolve()
    contribution_digest = recompute_contribution_digest(root)
    manifest = load_json(root / "visual_manifest.json")
    if manifest.get("contribution_digest") != contribution_digest:
        raise ValueError("Visual manifest is stale for the current contribution")
    current_digest = _visual_manifest_digest(manifest)
    if current_digest != manifest.get("manifest_digest"):
        raise ValueError("Visual manifest digest mismatch")
    for output in manifest.get("outputs", []):
        relative = output.get("path")
        if not isinstance(relative, str):
            raise ValueError("Visual output path is invalid")
        path = (root / relative).resolve()
        if not path.is_relative_to(root) or not path.is_file():
            raise ValueError(f"Visual output is missing or unbound: {relative}")
        if file_digest(path) != output.get("sha256"):
            raise ValueError(f"Visual output hash mismatch: {relative}")
        if path.stat().st_size != output.get("size_bytes"):
            raise ValueError(f"Visual output size mismatch: {relative}")
        layout = output.get("layout_validation")
        if output.get("kind") == "carousel_slide" and (
            not isinstance(layout, dict) or layout.get("overflow_free") is not True
        ):
            raise ValueError(f"Visual layout validation is missing: {relative}")
        if output.get("kind") == "carousel_slide" and isinstance(layout, dict):
            if float(layout.get("max_line_width_px", 1)) > float(
                layout.get("available_width_px", 0)
            ):
                raise ValueError(f"Visual line overflow recorded: {relative}")
            safe_area = layout.get("safe_area")
            if (
                not isinstance(safe_area, list)
                or len(safe_area) != 4
                or float(layout.get("content_bottom", safe_area[3] + 1))
                > float(safe_area[3])
            ):
                raise ValueError(f"Visual content overflow recorded: {relative}")
    return current_digest


def fresh_render_review_decision(run_dir: Path) -> dict[str, Any] | None:
    """Return an accepted/rejected event only for the current rendered bytes."""

    root = run_dir.resolve()
    manifest_digest = verify_visual_manifest(root)
    contribution_digest = recompute_contribution_digest(root)
    review_log = load_json(root / "review_log.json")
    current: dict[str, Any] | None = None
    for event in review_log.get("events", []):
        if (
            event.get("scope") == "rendered_output"
            and event.get("contribution_digest") == contribution_digest
            and event.get("artifact_digest") == manifest_digest
        ):
            current = event
    return current


def require_accepted_render_review(run_dir: Path) -> dict[str, Any]:
    """Require professional acceptance of the exact current rendered bytes."""

    event = fresh_render_review_decision(run_dir)
    if not event or event.get("decision") != "accepted":
        raise ValueError("Fresh accepted review required for: rendered_output")
    return event


def package_digest(payload: dict[str, Any]) -> str:
    """Hash the immutable package binding independently from lifecycle status."""

    excluded = {"status", "validation_receipt", "package_digest", "packaged_at"}
    stable = {key: value for key, value in payload.items() if key not in excluded}
    return canonical_digest(stable)


def verify_package_manifest(run_dir: Path) -> str:
    """Verify current package bindings and every declared output file."""

    root = run_dir.resolve()
    input_digest = validate_input_integrity(root)
    contribution_digest = recompute_contribution_digest(root)
    final = load_json(root / "final_artifacts.json")
    if final.get("input_digest") != input_digest:
        raise ValueError("Final package is stale for current inputs")
    if final.get("contribution_digest") != contribution_digest:
        raise ValueError("Final package is stale for current contribution")
    current_package_digest = package_digest(final)
    if final.get("package_digest") != current_package_digest:
        raise ValueError("Final package digest mismatch")
    for output in final.get("outputs", []):
        relative = output.get("path")
        if not isinstance(relative, str):
            raise ValueError("Final output path is invalid")
        path = (root / relative).resolve()
        if not path.is_relative_to(root) or not path.is_file():
            raise ValueError(f"Final output is missing or unbound: {relative}")
        if path.stat().st_size != output.get("size_bytes"):
            raise ValueError(f"Final output size mismatch: {relative}")
        if file_digest(path) != output.get("sha256"):
            raise ValueError(f"Final output hash mismatch: {relative}")
    return current_package_digest


def fresh_package_review_decision(run_dir: Path) -> dict[str, Any] | None:
    """Return the latest decision bound to the exact current package bytes."""

    root = run_dir.resolve()
    current_package_digest = verify_package_manifest(root)
    contribution_digest = recompute_contribution_digest(root)
    review_log = load_json(root / "review_log.json")
    current: dict[str, Any] | None = None
    for event in review_log.get("events", []):
        if (
            event.get("scope") == "packaged_output"
            and event.get("contribution_digest") == contribution_digest
            and event.get("artifact_digest") == current_package_digest
        ):
            current = event
    return current


def require_accepted_package_review(run_dir: Path) -> dict[str, Any]:
    """Require user-confirmed acceptance of the exact packaged output bytes."""

    event = fresh_package_review_decision(run_dir)
    if not event or event.get("decision") != "accepted":
        raise ValueError("Fresh accepted review required for: packaged_output")
    return event


def validate_finalized_package(run_dir: Path) -> str:
    """Verify a finalized package and its receipt immediately before delivery."""

    root = run_dir.resolve()
    input_digest = validate_input_integrity(root)
    contribution_digest = recompute_contribution_digest(root)
    final = load_json(root / "final_artifacts.json")
    if final.get("status") != "final_ready":
        raise ValueError("Only a validated final_ready package can be delivered")
    current_package_digest = verify_package_manifest(root)
    package_review = require_accepted_package_review(root)
    receipt = final.get("validation_receipt")
    if not isinstance(receipt, dict):
        raise ValueError("Final package has no validation receipt")
    receipt_body = {
        key: value for key, value in receipt.items() if key != "receipt_digest"
    }
    if canonical_digest(receipt_body) != receipt.get("receipt_digest"):
        raise ValueError("Validation receipt digest mismatch")
    if receipt.get("input_digest") != input_digest:
        raise ValueError("Validation receipt is stale for current inputs")
    if receipt.get("contribution_digest") != contribution_digest:
        raise ValueError("Validation receipt is stale for current contribution")
    if receipt.get("package_digest") != current_package_digest:
        raise ValueError("Validation receipt is stale for current package")
    if receipt.get("package_review_event_id") != package_review.get(
        "event_id"
    ) or receipt.get("package_review_artifact_digest") != package_review.get(
        "artifact_digest"
    ):
        raise ValueError("Validation receipt is stale for packaged-output review")
    return current_package_digest


def require_accepted_reviews(
    run_dir: Path, scopes: Iterable[str]
) -> dict[str, dict[str, Any]]:
    """Require fresh accepted decisions for exact mechanically named scopes."""

    decisions = fresh_review_decisions(run_dir)
    missing = [
        scope
        for scope in scopes
        if decisions.get(scope, {}).get("decision") != "accepted"
    ]
    if missing:
        raise ValueError(f"Fresh accepted review required for: {', '.join(missing)}")
    return decisions


def validate_contribution_semantics(
    contribution: dict[str, Any],
    *,
    intake: dict[str, Any],
    source_register: dict[str, Any],
) -> None:
    """Enforce mechanical closure without deciding semantic professional meaning."""

    validate_schema(contribution, "model_contribution.schema.json")
    _reject_secret_fields(contribution)
    if contribution["run_id"] != intake["run_id"]:
        raise ValueError("Contribution run_id does not match run intake")

    source_ids = {row["id"] for row in source_register["sources"]}
    history_ids = {row["id"] for row in source_register["history"]}
    known_ids = source_ids | history_ids
    assessment_ids = [row["source_id"] for row in contribution["source_assessments"]]
    _unique(assessment_ids, "source assessment id")
    unknown_assessments = set(assessment_ids) - known_ids
    if unknown_assessments:
        raise ValueError(
            f"Unknown source assessment ids: {sorted(unknown_assessments)}"
        )

    claims = contribution["claims"]
    claim_ids = [row["id"] for row in claims]
    _unique(claim_ids, "claim id")
    claim_id_set = set(claim_ids)
    for claim in claims:
        unknown = set(claim["source_ids"]) - source_ids
        if unknown:
            raise ValueError(
                f"Claim {claim['id']} references unknown sources: {sorted(unknown)}"
            )

    drafts = contribution["channel_drafts"]
    draft_channels = [row["channel"] for row in drafts]
    _unique(draft_channels, "channel draft")
    unexpected_channels = set(draft_channels) - set(intake["channels"])
    if unexpected_channels:
        raise ValueError(f"Unrequested channel drafts: {sorted(unexpected_channels)}")
    for draft in drafts:
        unknown_claims = set(draft["claim_ids"]) - claim_id_set
        if unknown_claims:
            raise ValueError(
                f"Draft {draft['channel']} references unknown claims: {sorted(unknown_claims)}"
            )
        if draft["channel"] == "client_circular" and len(draft["sections"]) < 2:
            raise ValueError(
                "client_circular requires at least two structured sections"
            )

    slides = contribution["visual_story"]["slides"]
    for index, slide in enumerate(slides, start=1):
        unknown = set(slide["source_ids"]) - source_ids
        if unknown:
            raise ValueError(
                f"Visual slide {index} references unknown sources: {sorted(unknown)}"
            )
        if slide["kind"] not in {"cover", "close"} and not slide["source_ids"]:
            raise ValueError(f"Substantive visual slide {index} requires source_ids")

    profile_proposal = contribution["studio_profile_proposal"]
    if intake["history_inputs"] and profile_proposal is None:
        raise ValueError("Selected history requires a studio_profile_proposal")
    if not intake["history_inputs"] and profile_proposal is not None:
        raise ValueError("studio_profile_proposal requires selected history inputs")
    if profile_proposal is not None:
        unknown_history = (
            set(profile_proposal["derived_from_history_ids"]) - history_ids
        )
        if unknown_history:
            raise ValueError(
                "Studio profile references unknown history ids: "
                f"{sorted(unknown_history)}"
            )
        document = profile_proposal["document"]
        layout = document["layout"]
        rail_width = (
            layout["contact_rail_width_mm"] if document["use_contact_rail"] else 0
        )
        if layout["left_margin_mm"] + layout["right_margin_mm"] + rail_width > 165:
            raise ValueError("Studio document layout leaves no usable A4 content width")
        if layout["body_leading_pt"] < layout["body_font_size_pt"]:
            raise ValueError("Studio document body leading must not be below font size")

    recommendation = contribution["recommendation"]
    if recommendation == "no_publish":
        if claims or drafts or slides or contribution["master_brief"] is not None:
            raise ValueError(
                "no_publish cannot contain claims, drafts, visual slides, or a master brief"
            )
    else:
        if not claims or not drafts or contribution["master_brief"] is None:
            raise ValueError(
                "publish requires claims, channel drafts, and a master brief"
            )
        missing_channels = set(intake["channels"]) - set(draft_channels)
        if missing_channels:
            raise ValueError(
                f"Missing requested channel drafts: {sorted(missing_channels)}"
            )
        if intake["visual_requested"] and not 2 <= len(slides) <= 8:
            raise ValueError("Requested visual story requires two to eight slides")
        if not intake["visual_requested"] and slides:
            raise ValueError("Visual slides were not requested")
