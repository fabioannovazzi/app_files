#!/usr/bin/env python3
"""Validate Vera external-boundary coverage and source freshness.

The checks are deterministic because registration, JSON shape, confirmation
consistency, and byte fingerprints are mechanically verifiable. Purpose-based
data minimisation and legal compliance remain outside this validator.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any, Iterable

__all__ = ["main", "validate_privacy_surfaces"]

SKIP_DIRS = {".git", ".mypy_cache", ".pytest_cache", ".ruff_cache", "__pycache__"}
SKIP_SUFFIXES = {".pyc", ".pyo"}
MODEL_CONTEXT_POLICY = "real_case_data_may_enter_selected_runtime_model_context"
BOUNDARY_KINDS = {
    "public_research",
    "hosted_service",
    "external_connector",
    "send_or_publish",
}
SERVICE_BOUNDARY_KINDS = {"hosted_service", "send_or_publish"}
ACCOUNT_REVIEW_ITEMS = [
    "account_or_workspace_plan",
    "model_training_data_controls",
    "retention_and_deletion_controls",
]
ACCOUNT_BOUNDARY = {
    "selected_by": "firm_or_user",
    "vera_runtime_enforcement": "none",
    "review_timing": "before_professional_use_and_when_account_or_terms_change",
    "review_items": ACCOUNT_REVIEW_ITEMS,
    "per_case_record_required": False,
}
EXPECTED_RUNTIME_PROFILES = {
    "openai-codex": {
        "provider": "OpenAI",
        "runtime": "Codex",
        "surfaces": ["codex"],
        "account_boundary": ACCOUNT_BOUNDARY,
        "model_processing": {
            "scope": "ordinary_openai_codex_model_processing",
            "destination": "OpenAI model processing used by Codex",
            "account_arrangement": (
                "existing_openai_codex_account_or_workspace_selected_by_firm_or_user"
            ),
            "separate_vera_recipient": False,
            "automatic_anonymization": False,
            "local_only": False,
            "local_filtering_or_aggregation": "only_when_useful_for_the_work",
        },
    },
    "anthropic-cowork": {
        "provider": "Anthropic",
        "runtime": "Cowork",
        "surfaces": ["cowork"],
        "account_boundary": ACCOUNT_BOUNDARY,
        "model_processing": {
            "scope": "ordinary_anthropic_cowork_model_processing",
            "destination": "Anthropic model processing used by Cowork",
            "account_arrangement": (
                "existing_anthropic_claude_account_or_workspace_selected_by_firm_or_user"
            ),
            "separate_vera_recipient": False,
            "automatic_anonymization": False,
            "local_only": False,
            "local_filtering_or_aggregation": "only_when_useful_for_the_work",
        },
    },
}
RUNTIME_PROFILE_IDS = list(EXPECTED_RUNTIME_PROFILES)


def _vera_root() -> Path:
    return Path(__file__).resolve().parents[3]


def _components(vera_root: Path) -> tuple[set[str], dict[str, dict[str, Any]]]:
    payload = json.loads((vera_root / "components.json").read_text(encoding="utf-8"))
    names = set(payload["plugins"])
    roles = payload.get("workflow_roles", {})
    return names, roles


def _shared_services(vera_root: Path) -> set[str]:
    payload = json.loads((vera_root / "components.json").read_text(encoding="utf-8"))
    return set(payload.get("shared_services", []))


def _runtime_profile_errors(vera_root: Path) -> list[str]:
    path = vera_root / "privacy" / "runtime-profiles.json"
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return [f"runtime-profiles: cannot read profile catalog: {exc}"]
    if not isinstance(payload, dict):
        return ["runtime-profiles: catalog must be an object"]
    errors: list[str] = []
    if payload.get("schema_version") != 1:
        errors.append("runtime-profiles: schema_version must be 1")
    profiles = payload.get("profiles")
    if not isinstance(profiles, list):
        return [*errors, "runtime-profiles: profiles must be an array"]
    profile_ids = [
        str(profile.get("id", "")) if isinstance(profile, dict) else ""
        for profile in profiles
    ]
    if len(profile_ids) != len(set(profile_ids)):
        errors.append("runtime-profiles: profile ids must be unique")
    if profile_ids != RUNTIME_PROFILE_IDS:
        errors.append(
            "runtime-profiles: profiles must contain openai-codex and "
            "anthropic-cowork in that order"
        )
    for index, profile in enumerate(profiles):
        if not isinstance(profile, dict):
            errors.append(f"runtime-profiles: profile[{index}] must be an object")
            continue
        profile_id = str(profile.get("id", ""))
        expected = EXPECTED_RUNTIME_PROFILES.get(profile_id)
        if expected is None:
            errors.append(f"runtime-profiles: profile[{index}] has unknown id")
            continue
        actual = {key: value for key, value in profile.items() if key != "id"}
        if actual != expected:
            errors.append(
                f"runtime-profiles: {profile_id} account or model-processing "
                "boundary is inaccurate"
            )
    return errors


def _component_root(vera_root: Path, workstream: str) -> Path:
    packaged = vera_root / "modules" / workstream
    if packaged.is_dir():
        return packaged
    source = vera_root.parent / workstream
    if source.is_dir():
        return source
    raise FileNotFoundError(f"component source not found: {workstream}")


def _governed_files(component_root: Path, paths: Iterable[str]) -> list[Path]:
    files: set[Path] = set()
    for relative in paths:
        target = component_root / relative
        if target.is_file():
            files.add(target)
            continue
        if not target.is_dir():
            raise FileNotFoundError(f"governed path not found: {target}")
        for path in target.rglob("*"):
            if not path.is_file():
                continue
            rel_parts = path.relative_to(component_root).parts
            if any(part in SKIP_DIRS for part in rel_parts):
                continue
            if path.suffix in SKIP_SUFFIXES:
                continue
            files.add(path)
    return sorted(files, key=lambda item: item.relative_to(component_root).as_posix())


def _shared_governed_files(
    vera_root: Path, paths: Iterable[str], *, packaged: bool
) -> dict[str, Path]:
    """Resolve package-relative shared files from source or an installed Vera."""

    logical_files: dict[str, Path] = {}
    source_root = vera_root if packaged else vera_root.parent / "_shared"
    resolved_source_root = source_root.resolve()
    for value in paths:
        relative = Path(value)
        if relative.is_absolute() or ".." in relative.parts:
            raise ValueError(f"governed shared path must be package-relative: {value}")
        target = source_root / relative
        if target.is_symlink():
            raise ValueError(f"governed shared path must not be a symlink: {target}")
        try:
            target.resolve(strict=True).relative_to(resolved_source_root)
        except (FileNotFoundError, ValueError) as exc:
            raise FileNotFoundError(
                f"governed shared path not found or outside source root: {target}"
            ) from exc
        if target.is_file():
            logical_files[f"vera-shared/{relative.as_posix()}"] = target
            continue
        if not target.is_dir():
            raise FileNotFoundError(f"governed shared path not found: {target}")
        for path in target.rglob("*"):
            if path.is_symlink():
                raise ValueError(
                    f"governed shared source must not use symlinks: {path}"
                )
            if not path.is_file():
                continue
            rel_parts = path.relative_to(target).parts
            if any(part in SKIP_DIRS for part in rel_parts):
                continue
            if path.suffix in SKIP_SUFFIXES:
                continue
            logical_path = relative / path.relative_to(target)
            logical_files[f"vera-shared/{logical_path.as_posix()}"] = path
    return logical_files


def _repository_governed_files(
    vera_root: Path,
    paths: Iterable[str],
) -> dict[str, Path]:
    """Resolve repository-root-relative hosted service source without escapes."""

    logical_files: dict[str, Path] = {}
    repository_root = vera_root.parents[1]
    resolved_repository_root = repository_root.resolve()
    for value in paths:
        relative = Path(value)
        if relative.is_absolute() or ".." in relative.parts:
            raise ValueError(
                f"governed repository path must be repository-relative: {value}"
            )
        target = repository_root / relative
        if target.is_symlink():
            raise ValueError(
                f"governed repository path must not be a symlink: {target}"
            )
        try:
            target.resolve(strict=True).relative_to(resolved_repository_root)
        except (FileNotFoundError, ValueError) as exc:
            raise FileNotFoundError(
                "governed repository path not found or outside repository: " f"{target}"
            ) from exc
        if target.is_file():
            logical_files[f"repository:{relative.as_posix()}"] = target
            continue
        if not target.is_dir():
            raise FileNotFoundError(f"governed repository path not found: {target}")
        for path in target.rglob("*"):
            if path.is_symlink():
                raise ValueError(
                    f"governed repository source must not use symlinks: {path}"
                )
            if not path.is_file():
                continue
            rel_parts = path.relative_to(target).parts
            if any(part in SKIP_DIRS for part in rel_parts):
                continue
            if path.suffix in SKIP_SUFFIXES:
                continue
            logical_path = relative / path.relative_to(target)
            logical_files[f"repository:{logical_path.as_posix()}"] = path
    return logical_files


def _fingerprint(
    component_root: Path,
    paths: Iterable[str],
    *,
    wrapper: Path | None = None,
    vera_root: Path | None = None,
    shared_paths: Iterable[str] = (),
    repository_paths: Iterable[str] = (),
) -> str:
    governed_paths = tuple(paths)
    logical_files = {
        path.relative_to(component_root).as_posix(): path
        for path in _governed_files(component_root, governed_paths)
    }
    shared_governed_paths = tuple(shared_paths)
    if shared_governed_paths:
        if vera_root is None:
            raise ValueError("vera_root is required for governed shared paths")
        try:
            component_root.resolve().relative_to((vera_root / "modules").resolve())
            packaged = True
        except ValueError:
            packaged = False
        logical_files.update(
            _shared_governed_files(vera_root, shared_governed_paths, packaged=packaged)
        )
    repository_governed_paths = tuple(repository_paths)
    if repository_governed_paths:
        if vera_root is None:
            raise ValueError("vera_root is required for governed repository paths")
        logical_files.update(
            _repository_governed_files(vera_root, repository_governed_paths)
        )
    projected_review_server = "scripts/review_server.py"
    adapter = component_root / "assets" / "review-workbench-adapter.json"
    source_review_server = component_root / projected_review_server
    scripts_are_governed = any(
        relative == "scripts" or relative == projected_review_server
        for relative in governed_paths
    )
    if (
        adapter.is_file()
        and json.loads(adapter.read_text(encoding="utf-8")).get("injectLocalServer")
        is not False
        and scripts_are_governed
        and not source_review_server.is_file()
    ):
        repository_root = component_root.parents[1]
        shared_review_server = repository_root / "scripts" / "serve_review_workbench.py"
        if not shared_review_server.is_file():
            raise FileNotFoundError(
                "shared review workbench source not found: " f"{shared_review_server}"
            )
        logical_files[projected_review_server] = shared_review_server

    digest = hashlib.sha256()
    for logical_path, path in sorted(logical_files.items()):
        relative = logical_path.encode("utf-8")
        digest.update(len(relative).to_bytes(4, "big"))
        digest.update(relative)
        content = path.read_bytes()
        digest.update(len(content).to_bytes(8, "big"))
        digest.update(content)
    if wrapper is not None:
        wrapper_root = wrapper.parent
        wrapper_files = _governed_files(wrapper_root, (".",))
        if wrapper not in wrapper_files:
            raise FileNotFoundError(f"workflow wrapper not found: {wrapper}")
        for path in wrapper_files:
            logical_path = (
                Path("vera-wrapper") / path.relative_to(wrapper_root)
            ).as_posix()
            digest.update(logical_path.encode("utf-8"))
            content = path.read_bytes()
            digest.update(len(content).to_bytes(8, "big"))
            digest.update(content)
    return digest.hexdigest()


def _boundary_errors(
    boundaries: Any,
    *,
    scope: str,
    allowed_kinds: set[str],
    manifest_runtime_profiles: Any,
    require_retention: bool = False,
    require_activation: bool = False,
) -> list[str]:
    errors: list[str] = []
    if not isinstance(boundaries, list):
        return [f"{scope}: external_boundaries must be an array"]
    available_profiles = (
        set(manifest_runtime_profiles)
        if isinstance(manifest_runtime_profiles, list)
        else set()
    )
    boundary_ids: list[str] = []
    for index, boundary in enumerate(boundaries):
        if not isinstance(boundary, dict):
            errors.append(f"{scope}: boundary[{index}] must be an object")
            continue
        fields = {
            "id",
            "kind",
            "destination",
            "purpose",
            "content",
            "optional",
            "requires_confirmation",
            "controls",
            "runtime_profiles",
        }
        text_fields = ["id", "destination", "purpose", "content"]
        if require_retention:
            fields.add("retention")
            text_fields.append("retention")
        if require_activation:
            fields.add("activation")
            text_fields.append("activation")
        if fields - boundary.keys():
            errors.append(f"{scope}: boundary[{index}] is incomplete")
        if not all(
            isinstance(boundary.get(field), str) and boundary[field].strip()
            for field in text_fields
        ):
            errors.append(f"{scope}: boundary[{index}] text must be non-empty")
        boundary_ids.append(str(boundary.get("id", "")))
        if boundary.get("kind") not in allowed_kinds:
            errors.append(f"{scope}: boundary[{index}] has invalid kind")
        optional = boundary.get("optional")
        confirmation = boundary.get("requires_confirmation")
        if not isinstance(optional, bool) or not isinstance(confirmation, bool):
            errors.append(f"{scope}: boundary[{index}] flags must be boolean")
        elif confirmation and not optional:
            errors.append(
                f"{scope}: confirmation is allowed only for an optional boundary"
            )
        if require_activation:
            activation = boundary.get("activation")
            automatic = {
                "automatic_session_start",
                "automatic_on_first_use",
                "automatic_after_prior_submission",
                "automatic_after_prior_connection",
                "automatic_per_durable_run",
            }
            if activation not in automatic | {"explicit_user_choice"}:
                errors.append(f"{scope}: boundary[{index}] has invalid activation")
            elif activation == "explicit_user_choice" and (
                optional is not True or confirmation is not True
            ):
                errors.append(
                    f"{scope}: explicit user choice must be optional and confirmed"
                )
            elif activation in automatic and (
                optional is not False or confirmation is not False
            ):
                errors.append(
                    f"{scope}: automatic boundary cannot request confirmation"
                )
        controls = boundary.get("controls")
        if (
            not isinstance(controls, list)
            or not controls
            or not all(isinstance(item, str) and item.strip() for item in controls)
        ):
            errors.append(f"{scope}: boundary[{index}] controls must be non-empty")
        profiles = boundary.get("runtime_profiles")
        if (
            not isinstance(profiles, list)
            or not profiles
            or not all(isinstance(item, str) and item for item in profiles)
        ):
            errors.append(
                f"{scope}: boundary[{index}] runtime_profiles must be non-empty strings"
            )
        elif len(profiles) != len(set(profiles)):
            errors.append(f"{scope}: boundary[{index}] runtime_profiles must be unique")
        elif not set(profiles) <= available_profiles:
            errors.append(
                f"{scope}: boundary[{index}] references a runtime outside the manifest"
            )
    if len(boundary_ids) != len(set(boundary_ids)):
        errors.append(f"{scope}: boundary ids must be unique")
    return errors


def _security_control_errors(
    controls: Any,
    *,
    scope: str,
    governed_paths: Iterable[str] = (),
    require_implementation: bool = False,
) -> list[str]:
    errors: list[str] = []
    if not isinstance(controls, list):
        return [f"{scope}: security_controls must be an array"]
    control_ids: list[str] = []
    for index, control in enumerate(controls):
        if not isinstance(control, dict):
            errors.append(f"{scope}: security_controls[{index}] must be an object")
            continue
        if not all(
            isinstance(control.get(field), str) and control[field].strip()
            for field in ("id", "control")
        ):
            errors.append(f"{scope}: security_controls[{index}] is incomplete")
        if require_implementation:
            implementations = control.get("implemented_by")
            on_violation = control.get("on_violation")
            if (
                not isinstance(implementations, list)
                or not implementations
                or not all(
                    isinstance(item, str) and item.strip() for item in implementations
                )
                or not isinstance(on_violation, str)
                or not on_violation.strip()
            ):
                errors.append(
                    f"{scope}: security_controls[{index}] lacks executable support"
                )
            else:
                governed = tuple(governed_paths)
                for implementation in implementations:
                    implementation_path = Path(implementation)
                    if (
                        implementation_path.is_absolute()
                        or ".." in implementation_path.parts
                    ):
                        errors.append(
                            f"{scope}: security_controls[{index}] has unsafe implementation path"
                        )
                        continue
                    covered = any(
                        implementation == path
                        or implementation.startswith(path.rstrip("/") + "/")
                        for path in governed
                    )
                    if not covered:
                        errors.append(
                            f"{scope}: security_controls[{index}] implementation is not governed"
                        )
        control_ids.append(str(control.get("id", "")))
    if len(control_ids) != len(set(control_ids)):
        errors.append(f"{scope}: security control ids must be unique")
    return errors


def _runtime_profile_reference_errors(
    profiles: Any,
    *,
    scope: str,
    require_all: bool,
) -> list[str]:
    if (
        not isinstance(profiles, list)
        or not profiles
        or not all(isinstance(item, str) and item for item in profiles)
    ):
        return [f"{scope}: runtime_profiles must be non-empty strings"]
    errors: list[str] = []
    if len(profiles) != len(set(profiles)):
        errors.append(f"{scope}: runtime_profiles must be unique")
    unknown = sorted(set(profiles) - set(RUNTIME_PROFILE_IDS))
    if unknown:
        errors.append(f"{scope}: unknown runtime_profiles: {', '.join(unknown)}")
    if require_all and profiles != RUNTIME_PROFILE_IDS:
        errors.append(
            f"{scope}: every workstream must reference openai-codex and "
            "anthropic-cowork in that order"
        )
    return errors


def _manifest_errors(
    payload: dict[str, Any], *, workstream: str, expected_role: str
) -> list[str]:
    errors: list[str] = []
    required = {
        "schema_version",
        "workstream",
        "display_name",
        "role",
        "governed_paths",
        "runtime_profiles",
        "model_context",
        "external_boundaries",
        "security_controls",
        "review",
    }
    missing = sorted(required - payload.keys())
    if missing:
        return [f"{workstream}: missing fields: {', '.join(missing)}"]
    if payload["schema_version"] != 3:
        errors.append(f"{workstream}: schema_version must be 3")
    if payload["workstream"] != workstream:
        errors.append(f"{workstream}: manifest workstream does not match filename")
    if (
        not isinstance(payload["display_name"], str)
        or not payload["display_name"].strip()
    ):
        errors.append(f"{workstream}: display_name must be non-empty")
    if payload["role"] != expected_role:
        errors.append(f"{workstream}: role must be {expected_role}")
    governed = payload["governed_paths"]
    if (
        not isinstance(governed, list)
        or not governed
        or not all(isinstance(item, str) and item for item in governed)
    ):
        errors.append(f"{workstream}: governed_paths must be non-empty strings")
    shared_governed = payload.get("governed_shared_paths", [])
    if not isinstance(shared_governed, list) or not all(
        isinstance(item, str) and item for item in shared_governed
    ):
        errors.append(f"{workstream}: governed_shared_paths must be strings")
    repository_governed = payload.get("governed_repository_paths", [])
    if not isinstance(repository_governed, list) or not all(
        isinstance(item, str) and item for item in repository_governed
    ):
        errors.append(f"{workstream}: governed_repository_paths must be strings")
    errors.extend(
        _runtime_profile_reference_errors(
            payload["runtime_profiles"],
            scope=workstream,
            require_all=True,
        )
    )
    context = payload["model_context"]
    if not isinstance(context, dict):
        errors.append(f"{workstream}: model_context must be an object")
    else:
        if context.get("policy") != MODEL_CONTEXT_POLICY:
            errors.append(f"{workstream}: unexpected model-context policy")
        classes = context.get("classes")
        if not isinstance(classes, list) or not classes:
            errors.append(f"{workstream}: model_context.classes must be non-empty")
            classes = []
        context_ids: list[str] = []
        for index, item in enumerate(classes):
            if not isinstance(item, dict):
                errors.append(
                    f"{workstream}: model_context.classes[{index}] must be an object"
                )
                continue
            fields = {"id", "purpose", "content", "runtime_profiles"}
            if fields - item.keys() or not all(
                isinstance(item.get(field), str) and item[field].strip()
                for field in ("id", "purpose", "content")
            ):
                errors.append(
                    f"{workstream}: model_context.classes[{index}] is incomplete"
                )
            profiles = item.get("runtime_profiles")
            if (
                not isinstance(profiles, list)
                or not profiles
                or not all(isinstance(value, str) and value for value in profiles)
                or len(profiles) != len(set(profiles))
                or not set(profiles) <= set(payload["runtime_profiles"])
            ):
                errors.append(
                    f"{workstream}: model_context.classes[{index}] has invalid "
                    "runtime_profiles"
                )
            context_ids.append(str(item.get("id", "")))
        if len(context_ids) != len(set(context_ids)):
            errors.append(f"{workstream}: model_context ids must be unique")
    errors.extend(
        _boundary_errors(
            payload["external_boundaries"],
            scope=workstream,
            allowed_kinds=BOUNDARY_KINDS,
            manifest_runtime_profiles=payload["runtime_profiles"],
        )
    )
    errors.extend(
        _security_control_errors(payload["security_controls"], scope=workstream)
    )

    review = payload["review"]
    if not isinstance(review, dict):
        errors.append(f"{workstream}: review must be an object")
    else:
        if review.get("reviewed_by") != "privacy-surface-review":
            errors.append(f"{workstream}: unexpected reviewer")
        if review.get("basis") != "external_boundary_review_of_workflow_source":
            errors.append(f"{workstream}: unexpected external-boundary review basis")
        fingerprint = review.get("source_fingerprint")
        if not isinstance(fingerprint, str) or len(fingerprint) != 64:
            errors.append(f"{workstream}: invalid source fingerprint")
    return errors


def _service_manifest_errors(payload: dict[str, Any], *, service_id: str) -> list[str]:
    errors: list[str] = []
    required = {
        "schema_version",
        "service_id",
        "display_name",
        "governed_paths",
        "runtime_profiles",
        "external_boundaries",
        "security_controls",
        "review",
    }
    missing = sorted(required - payload.keys())
    if missing:
        return [f"{service_id}: missing fields: {', '.join(missing)}"]
    if payload["schema_version"] != 2:
        errors.append(f"{service_id}: schema_version must be 2")
    if payload["service_id"] != service_id:
        errors.append(f"{service_id}: manifest service_id does not match filename")
    if (
        not isinstance(payload["display_name"], str)
        or not payload["display_name"].strip()
    ):
        errors.append(f"{service_id}: display_name must be non-empty")
    governed = payload["governed_paths"]
    if (
        not isinstance(governed, list)
        or not governed
        or not all(isinstance(item, str) and item for item in governed)
    ):
        errors.append(f"{service_id}: governed_paths must be non-empty strings")
    repository_governed = payload.get("governed_repository_paths", [])
    if not isinstance(repository_governed, list) or not all(
        isinstance(item, str) and item for item in repository_governed
    ):
        errors.append(f"{service_id}: governed_repository_paths must be strings")
    errors.extend(
        _runtime_profile_reference_errors(
            payload["runtime_profiles"],
            scope=service_id,
            require_all=False,
        )
    )
    errors.extend(
        _boundary_errors(
            payload["external_boundaries"],
            scope=service_id,
            allowed_kinds=SERVICE_BOUNDARY_KINDS,
            manifest_runtime_profiles=payload["runtime_profiles"],
            require_retention=True,
            require_activation=True,
        )
    )
    errors.extend(
        _security_control_errors(
            payload["security_controls"],
            scope=service_id,
            governed_paths=[
                *payload["governed_paths"],
                *(
                    f"repository:{path}"
                    for path in payload.get("governed_repository_paths", [])
                ),
            ],
            require_implementation=True,
        )
    )
    review = payload["review"]
    if not isinstance(review, dict):
        errors.append(f"{service_id}: review must be an object")
    else:
        if review.get("reviewed_by") != "privacy-surface-review":
            errors.append(f"{service_id}: unexpected reviewer")
        if review.get("basis") != "external_boundary_review_of_shared_service_source":
            errors.append(f"{service_id}: unexpected external-boundary review basis")
        fingerprint = review.get("source_fingerprint")
        if not isinstance(fingerprint, str) or len(fingerprint) != 64:
            errors.append(f"{service_id}: invalid source fingerprint")
    return errors


def _expected_role(workstream: str, roles: dict[str, dict[str, Any]]) -> str:
    return str(roles.get(workstream, {}).get("kind", "workflow"))


def validate_privacy_surfaces(vera_root: Path | None = None) -> list[str]:
    root = vera_root or _vera_root()
    names, roles = _components(root)
    manifest_dir = root / "privacy" / "workstreams"
    manifests = {path.stem: path for path in manifest_dir.glob("*.json")}
    errors = _runtime_profile_errors(root)
    for missing in sorted(names - manifests.keys()):
        errors.append(f"{missing}: registered workstream has no privacy manifest")
    for extra in sorted(manifests.keys() - names):
        errors.append(f"{extra}: privacy manifest is not a registered workstream")
    for workstream in sorted(names & manifests.keys()):
        path = manifests[workstream]
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            errors.append(f"{workstream}: cannot read manifest: {exc}")
            continue
        role = _expected_role(workstream, roles)
        manifest_errors = _manifest_errors(
            payload, workstream=workstream, expected_role=role
        )
        errors.extend(manifest_errors)
        if manifest_errors:
            continue
        try:
            component_root = _component_root(root, workstream)
            wrapper = (
                root / "skills" / workstream / "SKILL.md"
                if role != "internal_engine"
                else None
            )
            actual = _fingerprint(
                component_root,
                payload["governed_paths"],
                wrapper=wrapper,
                vera_root=root,
                shared_paths=payload.get("governed_shared_paths", []),
                repository_paths=payload.get("governed_repository_paths", []),
            )
        except (OSError, ValueError) as exc:
            errors.append(f"{workstream}: cannot fingerprint governed source: {exc}")
            continue
        if actual != payload["review"]["source_fingerprint"]:
            errors.append(
                f"{workstream}: privacy review is stale; run the review skill, then --refresh"
            )

    service_names = _shared_services(root)
    service_dir = root / "privacy" / "services"
    service_manifests = {path.stem: path for path in service_dir.glob("*.json")}
    for missing in sorted(service_names - service_manifests.keys()):
        errors.append(f"{missing}: registered shared service has no privacy manifest")
    for extra in sorted(service_manifests.keys() - service_names):
        errors.append(f"{extra}: privacy manifest is not a registered shared service")
    for service_id in sorted(service_names & service_manifests.keys()):
        path = service_manifests[service_id]
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            errors.append(f"{service_id}: cannot read manifest: {exc}")
            continue
        manifest_errors = _service_manifest_errors(payload, service_id=service_id)
        errors.extend(manifest_errors)
        if manifest_errors:
            continue
        try:
            actual = _fingerprint(
                root,
                payload["governed_paths"],
                vera_root=root,
                repository_paths=payload.get("governed_repository_paths", []),
            )
        except (OSError, ValueError) as exc:
            errors.append(
                f"{service_id}: cannot fingerprint governed service source: {exc}"
            )
            continue
        if actual != payload["review"]["source_fingerprint"]:
            errors.append(
                f"{service_id}: privacy review is stale; run the review skill, "
                "then --refresh-service"
            )
    return errors


def _refresh(workstream: str, vera_root: Path) -> None:
    names, _ = _components(vera_root)
    selected = sorted(names) if workstream == "all" else [workstream]
    for name in selected:
        if name not in names:
            raise ValueError(f"unknown registered workstream: {name}")
        manifest_path = vera_root / "privacy" / "workstreams" / f"{name}.json"
        payload = json.loads(manifest_path.read_text(encoding="utf-8"))
        component_root = _component_root(vera_root, name)
        _, roles = _components(vera_root)
        role = _expected_role(name, roles)
        wrapper = (
            vera_root / "skills" / name / "SKILL.md"
            if role != "internal_engine"
            else None
        )
        payload["review"]["source_fingerprint"] = _fingerprint(
            component_root,
            payload["governed_paths"],
            wrapper=wrapper,
            vera_root=vera_root,
            shared_paths=payload.get("governed_shared_paths", []),
            repository_paths=payload.get("governed_repository_paths", []),
        )
        manifest_path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
        print(f"refreshed {name}")


def _refresh_service(service_id: str, vera_root: Path) -> None:
    names = _shared_services(vera_root)
    selected = sorted(names) if service_id == "all" else [service_id]
    for name in selected:
        if name not in names:
            raise ValueError(f"unknown registered shared service: {name}")
        manifest_path = vera_root / "privacy" / "services" / f"{name}.json"
        payload = json.loads(manifest_path.read_text(encoding="utf-8"))
        payload["review"]["source_fingerprint"] = _fingerprint(
            vera_root,
            payload["governed_paths"],
            vera_root=vera_root,
            repository_paths=payload.get("governed_repository_paths", []),
        )
        manifest_path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        print(f"refreshed service {name}")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--refresh", metavar="WORKSTREAM")
    parser.add_argument("--refresh-service", metavar="SERVICE")
    parser.add_argument("--refresh-all", action="store_true")
    args = parser.parse_args()
    root = _vera_root()
    selected_refreshes = sum(
        bool(value) for value in (args.refresh, args.refresh_service, args.refresh_all)
    )
    if selected_refreshes > 1:
        parser.error("choose --refresh, --refresh-service, or --refresh-all")
    if args.refresh_all:
        _refresh("all", root)
        _refresh_service("all", root)
    elif args.refresh:
        _refresh(args.refresh, root)
    elif args.refresh_service:
        _refresh_service(args.refresh_service, root)
    errors = validate_privacy_surfaces(root)
    if errors:
        for error in errors:
            print(f"ERROR: {error}")
        return 1
    print("Vera privacy surfaces are complete and current.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
