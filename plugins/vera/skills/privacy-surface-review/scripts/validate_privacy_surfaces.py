#!/usr/bin/env python3
"""Validate Vera privacy-surface coverage and source freshness.

The checks are deterministic because component registration, JSON shape, wrapper
integration, and byte fingerprints are mechanically verifiable. Semantic
necessity and notice wording remain model-reviewed manifest content.
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
NOTICE_MARKER = "Privacy Boundary"


def _vera_root() -> Path:
    return Path(__file__).resolve().parents[3]


def _components(vera_root: Path) -> tuple[set[str], dict[str, dict[str, Any]]]:
    payload = json.loads((vera_root / "components.json").read_text(encoding="utf-8"))
    names = set(payload["plugins"])
    roles = payload.get("workflow_roles", {})
    return names, roles


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


def _fingerprint(
    component_root: Path, paths: Iterable[str], *, wrapper: Path | None = None
) -> str:
    governed_paths = tuple(paths)
    logical_files = {
        path.relative_to(component_root).as_posix(): path
        for path in _governed_files(component_root, governed_paths)
    }
    projected_review_server = "scripts/review_server.py"
    adapter = component_root / "assets" / "review-workbench-adapter.json"
    source_review_server = component_root / projected_review_server
    scripts_are_governed = any(
        relative == "scripts" or relative == projected_review_server
        for relative in governed_paths
    )
    if (
        adapter.is_file()
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
        digest.update(b"vera-wrapper/SKILL.md")
        content = wrapper.read_bytes()
        digest.update(len(content).to_bytes(8, "big"))
        digest.update(content)
    return digest.hexdigest()


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
        "data_flow",
        "residual_risks",
        "commercialista_notice",
        "review",
    }
    missing = sorted(required - payload.keys())
    if missing:
        return [f"{workstream}: missing fields: {', '.join(missing)}"]
    if payload["schema_version"] != 1:
        errors.append(f"{workstream}: schema_version must be 1")
    if payload["workstream"] != workstream:
        errors.append(f"{workstream}: manifest workstream does not match filename")
    if payload["role"] != expected_role:
        errors.append(f"{workstream}: role must be {expected_role}")
    governed = payload["governed_paths"]
    if (
        not isinstance(governed, list)
        or not governed
        or not all(isinstance(item, str) and item for item in governed)
    ):
        errors.append(f"{workstream}: governed_paths must be non-empty strings")
    flow = payload["data_flow"]
    if not isinstance(flow, dict):
        errors.append(f"{workstream}: data_flow must be an object")
    else:
        for field in ("local_sources", "local_processing", "codex_context"):
            if not isinstance(flow.get(field), list) or not flow[field]:
                errors.append(f"{workstream}: data_flow.{field} must be non-empty")
        context_ids: list[str] = []
        for index, item in enumerate(flow.get("codex_context", [])):
            if not isinstance(item, dict):
                errors.append(f"{workstream}: codex_context[{index}] must be an object")
                continue
            fields = {
                "id",
                "purpose",
                "content",
                "minimum_necessary",
                "semantic_reasoning_required",
                "full_source_expected",
            }
            if fields - item.keys():
                errors.append(f"{workstream}: codex_context[{index}] is incomplete")
            context_ids.append(str(item.get("id", "")))
        if len(context_ids) != len(set(context_ids)):
            errors.append(f"{workstream}: codex_context ids must be unique")
    risks = payload["residual_risks"]
    if not isinstance(risks, list) or not risks:
        errors.append(f"{workstream}: residual_risks must be non-empty")
    notice = payload["commercialista_notice"]
    if not isinstance(notice, dict):
        errors.append(f"{workstream}: commercialista_notice must be an object")
    else:
        level = notice.get("level")
        if level not in {"none", "informational", "confirmation"}:
            errors.append(f"{workstream}: invalid notice level")
        confirmation = notice.get("requires_confirmation")
        if confirmation is not (level == "confirmation"):
            errors.append(
                f"{workstream}: notice confirmation flag disagrees with level"
            )
        if level != "none" and not all(
            isinstance(notice.get(key), str) and notice[key].strip()
            for key in ("message_it", "message_en")
        ):
            errors.append(
                f"{workstream}: visible notices require Italian and English text"
            )
        for key in ("message_fr", "message_de"):
            if key in notice and (
                not isinstance(notice[key], str) or not notice[key].strip()
            ):
                errors.append(
                    f"{workstream}: optional {key} notice text must be non-empty"
                )
    review = payload["review"]
    if not isinstance(review, dict):
        errors.append(f"{workstream}: review must be an object")
    else:
        if review.get("reviewed_by") != "privacy-surface-review":
            errors.append(f"{workstream}: unexpected reviewer")
        if review.get("basis") != "model_review_of_workflow_source":
            errors.append(f"{workstream}: review basis must remain model-led")
        fingerprint = review.get("source_fingerprint")
        if not isinstance(fingerprint, str) or len(fingerprint) != 64:
            errors.append(f"{workstream}: invalid source fingerprint")
    return errors


def _expected_role(workstream: str, roles: dict[str, dict[str, Any]]) -> str:
    return str(roles.get(workstream, {}).get("kind", "workflow"))


def _wrapper_errors(vera_root: Path, workstream: str, role: str) -> list[str]:
    if role == "internal_engine":
        return []
    wrapper = vera_root / "skills" / workstream / "SKILL.md"
    if not wrapper.is_file():
        return [f"{workstream}: missing Vera wrapper skill"]
    if NOTICE_MARKER not in wrapper.read_text(encoding="utf-8"):
        return [f"{workstream}: wrapper does not enforce the Privacy Boundary notice"]
    return []


def validate_privacy_surfaces(vera_root: Path | None = None) -> list[str]:
    root = vera_root or _vera_root()
    names, roles = _components(root)
    manifest_dir = root / "privacy" / "workstreams"
    manifests = {path.stem: path for path in manifest_dir.glob("*.json")}
    errors: list[str] = []
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
        errors.extend(_wrapper_errors(root, workstream, role))
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
                component_root, payload["governed_paths"], wrapper=wrapper
            )
        except (OSError, ValueError) as exc:
            errors.append(f"{workstream}: cannot fingerprint governed source: {exc}")
            continue
        if actual != payload["review"]["source_fingerprint"]:
            errors.append(
                f"{workstream}: privacy review is stale; run the review skill, then --refresh"
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
            component_root, payload["governed_paths"], wrapper=wrapper
        )
        manifest_path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
        print(f"refreshed {name}")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--refresh", metavar="WORKSTREAM")
    parser.add_argument("--refresh-all", action="store_true")
    args = parser.parse_args()
    root = _vera_root()
    if args.refresh and args.refresh_all:
        parser.error("choose --refresh or --refresh-all")
    if args.refresh or args.refresh_all:
        _refresh("all" if args.refresh_all else args.refresh, root)
    errors = validate_privacy_surfaces(root)
    if errors:
        for error in errors:
            print(f"ERROR: {error}")
        return 1
    print("Vera privacy surfaces are complete and current.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
