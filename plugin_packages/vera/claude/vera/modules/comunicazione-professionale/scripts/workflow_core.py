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
    "validate_answer_contract",
    "validate_claim_assurance",
    "validate_finalized_package",
    "validate_input_integrity",
    "validate_schema",
    "verify_visual_manifest",
    "verify_visual_preview_manifest",
    "verify_visual_assessment",
    "verify_package_manifest",
    "verify_creative_direction_decision",
    "verify_editorial_assessor_qualification",
    "workflow_lock",
]

PLUGIN_ROOT = Path(__file__).resolve().parents[1]
SCHEMA_ROOT = PLUGIN_ROOT / "schemas"
EDITORIAL_CASES_PATH = PLUGIN_ROOT / "evals" / "editorial_quality_cases.json"
EDITORIAL_EXPECTED_PATH = PLUGIN_ROOT / "evals" / "editorial_quality_expected.json"
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


def _verify_embedded_digest(payload: dict[str, Any], field: str) -> str:
    """Verify a mechanical canonical digest embedded in one JSON record."""

    expected = str(payload.get(field) or "")
    stable = {key: value for key, value in payload.items() if key != field}
    current = canonical_digest(stable)
    if expected != current:
        raise ValueError(f"{field} mismatch")
    return current


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
            "answer_contract": workbench.get("answer_contract"),
            "claim_assurance": workbench.get("claim_assurance"),
            "editorial_assessment": workbench.get("editorial_assessment"),
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


def verify_editorial_assessor_qualification(
    workspace: Path,
    *,
    provider: str,
    model: str,
    template_version: str,
) -> dict[str, Any]:
    """Require a current model-led benchmark receipt for the live assessor."""

    root = workspace.resolve()
    cases = load_json(EDITORIAL_CASES_PATH)
    expected = load_json(EDITORIAL_EXPECTED_PATH)
    cases_digest = canonical_digest(cases)
    expected_digest = canonical_digest(expected)
    candidates = list((root / "editorial-qualifications").glob("qualification-*.json"))
    current = root / "editorial_assessor_qualification.json"
    if current.is_file():
        candidates.append(current)
    matching: dict[str, dict[str, Any]] = {}
    for path in candidates:
        record = load_json(path)
        digest = _verify_embedded_digest(record, "qualification_digest")
        identity = record.get("assessor_identity")
        if not isinstance(identity, dict):
            continue
        if (
            identity.get("provider"),
            identity.get("model"),
            identity.get("assessment_template_version"),
        ) != (provider, model, template_version):
            continue
        if (
            record.get("cases_digest") != cases_digest
            or record.get("expected_digest") != expected_digest
        ):
            continue
        matching[digest] = record
    if not matching:
        raise ValueError(
            "Editorial assessor is not qualified for this exact model/template"
        )
    record = max(matching.values(), key=lambda row: str(row.get("qualified_at", "")))
    if record.get("status") != "qualified":
        raise ValueError("Editorial assessor benchmark did not qualify")
    metrics = record.get("metrics")
    if not isinstance(metrics, dict):
        raise ValueError("Editorial assessor qualification metrics are missing")
    if metrics.get("critical_cases_passed") is not True:
        raise ValueError("Editorial assessor failed a critical anti-slop case")
    if int(metrics.get("false_ready_count", -1)) != 0:
        raise ValueError("Editorial assessor has a false-ready benchmark result")
    return record


def validate_answer_contract(
    answer_contract: dict[str, Any],
    *,
    intake: dict[str, Any],
) -> str:
    """Validate the communication-specific answer contract and exact intake binding."""

    validate_schema(answer_contract, "answer_contract.schema.json")
    digest = _verify_embedded_digest(answer_contract, "contract_digest")
    if answer_contract["run_id"] != intake["run_id"]:
        raise ValueError("Answer contract run_id does not match run intake")
    if answer_contract["audience"] != intake["audience"]:
        raise ValueError("Answer contract audience does not match run intake")
    if answer_contract["output_language"] != intake["language"]:
        raise ValueError("Answer contract language does not match run intake")
    if answer_contract["jurisdiction"] != intake["jurisdiction"]:
        raise ValueError("Answer contract jurisdiction does not match run intake")
    return digest


def validate_claim_assurance(
    claim_assurance: dict[str, Any],
    *,
    contribution: dict[str, Any],
    answer_contract_digest: str,
    source_register: dict[str, Any],
) -> None:
    """Honor model-led claim verdicts while enforcing exact coverage and closure."""

    validate_schema(claim_assurance, "claim_assurance.schema.json")
    if claim_assurance["run_id"] != contribution["run_id"]:
        raise ValueError("Claim assurance run_id does not match contribution")
    if claim_assurance["assessed_contribution_digest"] != canonical_digest(
        contribution
    ):
        raise ValueError("Claim assurance is stale for this contribution")
    if claim_assurance["answer_contract_digest"] != answer_contract_digest:
        raise ValueError("Claim assurance is stale for this answer contract")
    claim_ids = [row["id"] for row in contribution["claims"]]
    assessed_ids = [row["claim_id"] for row in claim_assurance["claims"]]
    if assessed_ids != claim_ids:
        raise ValueError("Claim assurance must cover every claim once and in order")
    coverage = claim_assurance["coverage_review"]
    if coverage["reviewed_claim_ids"] != claim_ids:
        raise ValueError("Claim assurance coverage must list every claim in order")
    if claim_assurance["contract_review"]["reviewer_action"] != "accept" or any(
        dimension["status"] != "conforms"
        for name, dimension in claim_assurance["contract_review"].items()
        if name != "reviewer_action"
    ):
        raise ValueError("Claim assurance found an unresolved answer-contract defect")
    source_ids = {row["id"] for row in source_register["sources"]}
    for claim, assessment in zip(
        contribution["claims"], claim_assurance["claims"], strict=True
    ):
        checked_ids = [row["source_id"] for row in assessment["source_checks"]]
        if set(checked_ids) != set(claim["source_ids"]):
            raise ValueError(
                f"Claim assurance source coverage mismatch for {claim['id']}"
            )
        if set(checked_ids) - source_ids:
            raise ValueError(
                f"Claim assurance references an unknown source: {claim['id']}"
            )
        if any(
            row["identity_status"] != "matches_registered_source"
            for row in assessment["source_checks"]
        ):
            raise ValueError(
                f"Claim assurance has unresolved source identity: {claim['id']}"
            )
        if assessment["support"]["status"] != "supported":
            raise ValueError(f"Claim assurance has unresolved support: {claim['id']}")
        if assessment["reasoning"]["status"] not in {"sound", "not_applicable"}:
            raise ValueError(f"Claim assurance has unresolved reasoning: {claim['id']}")
        if assessment["reasoning"]["missing_premises"]:
            raise ValueError(f"Claim assurance has missing premises: {claim['id']}")
        if assessment["professional_judgment"]["status"] in {
            "contested",
            "uncertain",
        }:
            raise ValueError(
                f"Claim assurance has unresolved professional judgment: {claim['id']}"
            )
        if (
            assessment["disposition"] != "retain"
            or assessment["reviewer_action"] != "accept"
        ):
            raise ValueError(
                f"Claim assurance requires contribution revision: {claim['id']}"
            )
        issue_types = {row["type"] for row in assessment["issues"]}
        if "none" in issue_types and len(issue_types) != 1:
            raise ValueError(f"Claim assurance mixes none with defects: {claim['id']}")
        if (
            assessment["professional_judgment"]["status"]
            == "professional_judgment_required"
        ):
            if "judgment_dependent" not in issue_types or not any(
                row["type"] == "judgment_dependent"
                and row["treatment"] == "professional_review"
                for row in assessment["issues"]
            ):
                raise ValueError(
                    f"Claim assurance must route judgment to professional review: {claim['id']}"
                )
        elif issue_types != {"none"}:
            raise ValueError(
                f"Claim assurance retains an unresolved defect: {claim['id']}"
            )
    expected_outcome = (
        "no_publication_supported"
        if contribution["recommendation"] == "no_publish"
        else "ready_for_professional_review"
    )
    if claim_assurance["overall_assessment"]["outcome"] != expected_outcome:
        raise ValueError("Claim assurance outcome does not support this contribution")


def _profile_leaf_paths(value: object, *, prefix: str = "") -> list[str]:
    """List mechanically addressable Studio-profile leaves for evidence coverage."""

    if isinstance(value, dict):
        paths: list[str] = []
        for key, child in value.items():
            if key in {"derived_from_history_ids", "field_provenance"}:
                continue
            child_prefix = f"{prefix}.{key}" if prefix else key
            paths.extend(_profile_leaf_paths(child, prefix=child_prefix))
        return paths
    # Arrays are one profile field: their individual entries share one basis.
    return [prefix]


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


def verify_creative_direction_decision(run_dir: Path) -> dict[str, Any]:
    """Verify the selected Creative Production direction or explicit fallback."""

    root = run_dir.resolve()
    intake = load_json(root / "run_intake.json")
    workbench = load_json(root / "content_workbench.json")
    contribution_digest = recompute_contribution_digest(root)
    story = workbench["contribution"]["visual_story"]
    route = intake["external_routes"]["creative_production"]
    if not route["selected"]:
        return {
            "route_status": "not_selected",
            "decision_digest": "",
            "handoff_digest": "",
            "translation_digest": "",
            "tokens": None,
        }
    if story["decision"] != "render" or not story["slides"]:
        return {
            "route_status": "not_applicable",
            "decision_digest": "",
            "handoff_digest": "",
            "translation_digest": "",
            "tokens": None,
        }
    version = int(workbench["version"])
    directory = root / "creative-direction"
    handoff = load_json(directory / f"handoff-v{version:03d}.json")
    validate_schema(handoff, "creative_direction_handoff.schema.json")
    handoff_digest = _verify_embedded_digest(handoff, "handoff_digest")
    if handoff["binding"] != {
        "input_digest": workbench["input_digest"],
        "contribution_digest": contribution_digest,
        "visual_story_digest": canonical_digest(story),
    }:
        raise ValueError("Creative direction handoff is stale")
    decision = load_json(directory / f"decision-v{version:03d}.json")
    validate_schema(decision, "creative_direction_decision.schema.json")
    decision_digest = _verify_embedded_digest(decision, "decision_digest")
    if decision["run_id"] != workbench["run_id"]:
        raise ValueError("Creative direction decision run_id mismatch")
    if decision["binding"] != {
        "handoff_digest": handoff_digest,
        **handoff["binding"],
    }:
        raise ValueError("Creative direction decision is stale")
    selection = decision["selection"]
    if decision["outcome"] == "fallback":
        return {
            "route_status": "fallback",
            "decision_digest": decision_digest,
            "handoff_digest": handoff_digest,
            "translation_digest": "",
            "fallback_reason": selection["reason"],
            "tokens": None,
        }
    item_ids = [row["item_id"] for row in selection["directions"]]
    _unique(item_ids, "Creative Production direction item")
    if selection["selected_item_id"] not in item_ids:
        raise ValueError(
            "Selected Creative Production item is not on the recorded board"
        )
    for row in selection["directions"]:
        path = (root / row["snapshot_path"]).resolve()
        if not path.is_relative_to(root) or not path.is_file():
            raise ValueError("Creative Production reference snapshot is missing")
        if (
            path.stat().st_size != row["size_bytes"]
            or file_digest(path) != row["sha256"]
        ):
            raise ValueError("Creative Production reference snapshot changed")
    translation = selection["translation"]
    if translation["contribution_change_required"]:
        raise ValueError(
            "Selected direction requires a superseding contribution before rendering"
        )
    return {
        "route_status": "selected",
        "decision_digest": decision_digest,
        "handoff_digest": handoff_digest,
        "translation_digest": canonical_digest(translation),
        "board_id": selection["board_id"],
        "board_revision": selection["board_revision"],
        "selected_item_id": selection["selected_item_id"],
        "tokens": translation["tokens"],
    }


def _visual_manifest_digest(payload: dict[str, Any]) -> str:
    stable = {key: value for key, value in payload.items() if key != "manifest_digest"}
    return canonical_digest(stable)


def _verify_visual_manifest(
    run_dir: Path, *, filename: str, expected_state: str
) -> str:
    """Verify one exact render manifest and every file it binds."""

    root = run_dir.resolve()
    contribution_digest = recompute_contribution_digest(root)
    manifest = load_json(root / filename)
    if manifest.get("render_state") != expected_state:
        raise ValueError(f"Visual manifest is not a {expected_state} render")
    if manifest.get("contribution_digest") != contribution_digest:
        raise ValueError("Visual manifest is stale for the current contribution")
    creative = verify_creative_direction_decision(root)
    recorded_creative = manifest.get("creative_direction")
    expected_creative = {
        key: value for key, value in creative.items() if key != "tokens"
    }
    if recorded_creative != expected_creative:
        raise ValueError(
            "Visual manifest is stale for the Creative Production decision"
        )
    current_digest = _visual_manifest_digest(manifest)
    if current_digest != manifest.get("manifest_digest"):
        raise ValueError("Visual manifest digest mismatch")
    quality_gate = manifest.get("quality_gate")
    if not isinstance(quality_gate, dict):
        raise ValueError("Visual quality gate is missing")
    mechanical_checks = quality_gate.get("mechanical_checks")
    if not isinstance(mechanical_checks, dict) or any(
        value != "passed" for value in mechanical_checks.values()
    ):
        raise ValueError("Visual mechanical quality checks are incomplete")
    if quality_gate.get("model_led_review_required") is not True:
        raise ValueError("Visual model-led review requirement is missing")
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
            if layout.get("internal_id_leakage") is not False:
                raise ValueError(
                    f"Visual internal identifier leakage recorded: {relative}"
                )
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


def verify_visual_manifest(run_dir: Path) -> str:
    """Verify release-candidate rendered files and geometry."""

    return _verify_visual_manifest(
        run_dir,
        filename="visual_manifest.json",
        expected_state="accepted_semantics",
    )


def verify_visual_preview_manifest(run_dir: Path) -> str:
    """Verify isolated QA-preview rendered files and geometry."""

    return _verify_visual_manifest(
        run_dir,
        filename="visual_preview_manifest.json",
        expected_state="qa_preview",
    )


def verify_visual_assessment(run_dir: Path) -> str:
    """Verify the model-led assessment bound to the exact release render."""

    root = run_dir.resolve()
    manifest_digest = verify_visual_manifest(root)
    record = load_json(root / "visual_assessment_record.json")
    stable_record = {
        key: value for key, value in record.items() if key != "record_digest"
    }
    record_digest = canonical_digest(stable_record)
    if record.get("record_digest") != record_digest:
        raise ValueError("Visual assessment record digest mismatch")
    assessment = record.get("assessment")
    if not isinstance(assessment, dict):
        raise ValueError("Visual model-led assessment is missing")
    validate_schema(assessment, "visual_assessment.schema.json")
    workbench = load_json(root / "content_workbench.json")
    if assessment["run_id"] != workbench["run_id"]:
        raise ValueError("Visual assessment run_id mismatch")
    if assessment["render_state"] != "accepted_semantics":
        raise ValueError("Visual assessment is not for accepted-semantics render")
    if assessment["assessed_manifest_digest"] != manifest_digest:
        raise ValueError("Visual assessment is stale for the current render")
    if assessment["verdict"] != "ready":
        raise ValueError("Visual model-led assessment must be ready")
    slide_count = len(workbench["contribution"]["visual_story"]["slides"])
    assessed_indices = [row["slide_index"] for row in assessment["slide_assessments"]]
    if assessed_indices != list(range(1, slide_count + 1)):
        raise ValueError("Visual assessment must cover every slide once and in order")
    if any(
        row["verdict"] in {"weak", "redundant"}
        for row in assessment["slide_assessments"]
    ):
        raise ValueError("Visual assessment contains a weak or redundant slide")
    return record_digest


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
    if (
        not event
        or event.get("decision") != "accepted"
        or event.get("quality_checklist_confirmed") is not True
    ):
        raise ValueError("Fresh accepted review required for: rendered_output")
    visual_assessment_digest = verify_visual_assessment(run_dir)
    if event.get("visual_assessment_digest") != visual_assessment_digest:
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

    visual_story = contribution["visual_story"]
    slides = visual_story["slides"]
    for index, slide in enumerate(slides, start=1):
        unknown = set(slide["source_ids"]) - source_ids
        if unknown:
            raise ValueError(
                f"Visual slide {index} references unknown sources: {sorted(unknown)}"
            )
        if slide["kind"] not in {"cover", "close"} and not slide["source_ids"]:
            raise ValueError(f"Substantive visual slide {index} requires source_ids")
        if slide["source_ids"] and not slide["source_note"].strip():
            raise ValueError(
                f"Visual slide {index} requires a reader-facing source_note"
            )
        if slide["relationship_to_post"] == "restates_post":
            raise ValueError(
                f"Visual slide {index} only restates the post; omit or redesign it"
            )

    # Public copy must never expose internal traceability keys. Exact-ID
    # matching is deterministic because these identifiers are mechanically
    # registered; deciding whether the prose is useful remains model-led.
    public_texts: list[tuple[str, str]] = []
    for draft in drafts:
        public_texts.extend(
            [
                (f"draft {draft['channel']} title", draft["title"]),
                (f"draft {draft['channel']} subject", draft.get("subject", "")),
                (f"draft {draft['channel']} body", draft["body"]),
            ]
        )
        for section in draft["sections"]:
            public_texts.extend(
                [
                    (f"draft {draft['channel']} section heading", section["heading"]),
                    (f"draft {draft['channel']} section body", section["body"]),
                    *(
                        (f"draft {draft['channel']} section bullet", bullet)
                        for bullet in section["bullets"]
                    ),
                ]
            )
    for index, slide in enumerate(slides, start=1):
        public_texts.extend(
            [
                (f"visual slide {index} eyebrow", slide["eyebrow"]),
                (f"visual slide {index} title", slide["title"]),
                (f"visual slide {index} body", slide["body"]),
                (f"visual slide {index} highlight", slide["highlight"]),
                (f"visual slide {index} source note", slide["source_note"]),
                *(
                    (f"visual slide {index} bullet", bullet)
                    for bullet in slide["bullets"]
                ),
            ]
        )
    internal_ids = known_ids | claim_id_set
    for label, text in public_texts:
        leaked = sorted(identifier for identifier in internal_ids if identifier in text)
        if leaked:
            raise ValueError(f"{label} exposes internal ids: {leaked}")

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
        expected_profile_paths = _profile_leaf_paths(profile_proposal)
        covered_profile_paths = [
            field_path
            for record in profile_proposal["field_provenance"]
            for field_path in record["field_paths"]
        ]
        _unique(covered_profile_paths, "studio profile provenance field path")
        if set(covered_profile_paths) != set(expected_profile_paths):
            missing = sorted(set(expected_profile_paths) - set(covered_profile_paths))
            unexpected = sorted(
                set(covered_profile_paths) - set(expected_profile_paths)
            )
            raise ValueError(
                "Studio profile field provenance must cover every field exactly; "
                f"missing={missing}, unexpected={unexpected}"
            )
        for record in profile_proposal["field_provenance"]:
            unknown_evidence = set(record["history_ids"]) - history_ids
            if unknown_evidence:
                raise ValueError(
                    "Studio profile provenance references unknown history ids: "
                    f"{sorted(unknown_evidence)}"
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
        if (
            claims
            or drafts
            or slides
            or contribution["master_brief"] is not None
            or visual_story["decision"] != "omit"
        ):
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
        if intake["visual_requested"]:
            if visual_story["decision"] == "render" and not 2 <= len(slides) <= 8:
                raise ValueError("Rendered visual story requires two to eight slides")
            if visual_story["decision"] == "omit" and slides:
                raise ValueError("Omitted visual story cannot contain slides")
        elif visual_story["decision"] != "omit" or slides:
            raise ValueError("Visual output was not requested and must be omitted")
