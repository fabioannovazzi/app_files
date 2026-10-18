"""Bind each host package to reviewed source contracts and its actual installed bytes."""

from __future__ import annotations

import hashlib
import importlib.util
import json
import tempfile
from pathlib import Path
from typing import Any

__all__ = ["project_privacy"]
ROOT = Path(__file__).resolve().parents[1]


def _load(path: Path, name: str) -> Any:
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise ValueError(f"Cannot load privacy implementation: {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def project_privacy(
    entries: dict[str, bytes],
    product: str,
    *,
    prefix: str = "",
    host: str,
    source_root: Path = ROOT,
) -> dict[str, Any]:
    """Retain source declarations; derive installed hashes after all host transforms.

    Package projection is mechanical, not a renewed semantic review. The full
    original contract remains available and omitted local paths are recorded.
    Server files are represented by declarations, never asserted to be deployed.
    """
    shared = source_root / "plugins/_shared/privacy-runtime"
    validator = _load(
        shared / "skills/privacy-surface-review/scripts/validate_privacy_surfaces.py",
        "_package_privacy_validator",
    )
    contract = _load(
        shared / "scripts/privacy_contract.py", "_package_privacy_contract"
    )
    source = source_root / "plugins" / product
    errors = validator.validate_privacy_surfaces(source)
    if errors:
        raise ValueError(
            f"{product}: source privacy review failed: " + "; ".join(errors)
        )
    registry = json.loads((source / "privacy/registry.json").read_text())
    source_index = json.loads((source / "privacy/contracts/index.json").read_text())
    source_contracts = {}
    for name in registry["workstreams"]:
        raw = (source / f"privacy/contracts/{name}.json").read_bytes()
        if (
            raw != contract.canonical_bytes(contract.contract_document(source, name))
            or hashlib.sha256(raw).hexdigest() != source_index["contracts"][name]
        ):
            raise ValueError(
                f"{product}/{name}: source contract must be rebuilt after review"
            )
        source_contracts[name] = raw
    local = {
        name.removeprefix(prefix): data
        for name, data in entries.items()
        if name.startswith(prefix)
    }

    def installed_path(value: str) -> str:
        parts = value.split("/")
        if host == "anthropic-cowork":
            for index in range(len(parts) - 1):
                if parts[index] == "skills" and not parts[index + 1].startswith(
                    "mparanza-"
                ):
                    parts[index + 1] = "mparanza-" + parts[index + 1]
        return "/".join(parts)

    if host == "anthropic-cowork":
        registry["developer_skills"] = [
            "mparanza-" + name for name in registry["developer_skills"]
        ]
        for record in registry["workstreams"].values():
            record["skills"] = ["mparanza-" + name for name in record["skills"]]
    components = json.loads(local["components.json"])["plugins"]
    installed_skills = {
        Path(name).parts[1]
        for name in local
        if len(Path(name).parts) == 3
        and name.startswith("skills/")
        and name.endswith("/SKILL.md")
    }
    omitted_records = []
    for name, record in list(registry["workstreams"].items()):
        record["skills"] = [
            skill for skill in record["skills"] if skill in installed_skills
        ]
        record["components"] = [
            component for component in record["components"] if component in components
        ]
        if not record["skills"] and not record["components"]:
            omitted_records.append(name)
            del registry["workstreams"][name]
    # Host builders explicitly exclude inactive services, for example native
    # teaching in Cowork. Their source contracts are retained unchanged below.
    excluded_services = (
        registry.get("host_omissions", {}).get(host, {}).get("services", [])
    )
    registry["services"] = [
        name for name in registry["services"] if name not in excluded_services
    ]
    for name in excluded_services:
        local.pop(f"privacy/services/{name}.json", None)
    missing_services = [
        name
        for name in registry["services"]
        if f"privacy/services/{name}.json" not in local
    ]
    if missing_services:
        raise ValueError(
            f"{product}/{host}: missing reviewed services: {missing_services}"
        )
    for name in list(local):
        if (
            name.startswith("privacy/workstreams/")
            and Path(name).stem not in registry["workstreams"]
        ):
            del local[name]
        if name.startswith("privacy/repository-source-reviews/"):
            del local[name]
    if "usage/pipelines.json" in local:
        usage = json.loads(local["usage/pipelines.json"])
        available = {
            alias
            for entry in registry["workstreams"].values()
            for alias in entry["workflow_ids"]
        }
        usage["pipelines"] = {
            name: title
            for name, title in usage["pipelines"].items()
            if name in available
        }
        if "aliases" in usage:
            usage["aliases"] = {
                name: target
                for name, target in usage["aliases"].items()
                if target in usage["pipelines"]
            }
        local["usage/pipelines.json"] = contract.canonical_bytes(usage)
    local["privacy/registry.json"] = contract.canonical_bytes(registry)
    projection = {
        "schema_version": 1,
        "product": product,
        "host": host,
        "scope": "installed_bytes_and_retained_source_declarations_not_host_acceptance",
        "omitted_workstreams": sorted(omitted_records),
        "omitted_services": excluded_services,
        "omitted_paths": {},
    }
    local["privacy/package-projection.json"] = contract.canonical_bytes(projection)
    for name, raw in source_contracts.items():
        local[f"privacy/contracts/{name}.json"] = raw

    with tempfile.TemporaryDirectory(prefix=f"{product}-{host}-privacy-") as temporary:
        package = Path(temporary) / "plugins" / product
        for name, raw in local.items():
            path = package / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(raw)
        _, roles = validator._components(package)
        for kind, names in (
            ("workstreams", registry["workstreams"]),
            ("services", registry["services"]),
        ):
            for name in names:
                relative = f"privacy/{kind}/{name}.json"
                payload = json.loads((source / relative).read_text())
                original = json.loads((source / relative).read_text())
                payload["packaged_for_runtime"] = host
                component = (
                    validator._component_root(package, name)
                    if kind == "workstreams"
                    else package
                )
                omitted = []
                paths = []
                for value in payload["governed_paths"]:
                    value = installed_path(value)
                    if (component / value).exists():
                        paths.append(value)
                    else:
                        omitted.append(value)
                if not paths:
                    raise ValueError(
                        f"{product}/{host}/{name}: no installed governed implementation"
                    )
                payload["governed_paths"] = paths
                shared_paths = []
                for value in payload.get("governed_shared_paths", []):
                    value = installed_path(value)
                    if (package / value).exists():
                        shared_paths.append(value)
                    else:
                        omitted.append("shared:" + value)
                if "governed_shared_paths" in payload:
                    payload["governed_shared_paths"] = shared_paths
                if kind == "workstreams":
                    payload["role"] = registry["workstreams"][name]["role"]
                    payload["service_ids"] = [
                        value
                        for value in payload["service_ids"]
                        if value in registry["services"]
                    ]
                    payload["source_contract_sha256"] = source_index["contracts"][name]
                else:
                    payload["source_contract_sha256"] = hashlib.sha256(
                        contract.canonical_bytes(original)
                    ).hexdigest()
                repository_paths = payload.get("governed_repository_paths", [])
                if repository_paths:
                    identity = "workstream-" + name if kind == "workstreams" else name
                    files = []
                    for logical, path in validator._repository_governed_files(
                        source, repository_paths
                    ).items():
                        content = path.read_bytes()
                        repository_path = logical.removeprefix("repository:")
                        installed = []
                        # Exact copies are verifiable. Rewritten host instructions
                        # are governed independently by the installed fingerprint.
                        for candidate in (
                            installed_path(
                                repository_path.removeprefix(f"plugins/{product}/")
                            ),
                        ):
                            if (
                                candidate != repository_path
                                and local.get(candidate) == content
                            ):
                                installed.append(candidate)
                                if (
                                    candidate not in payload["governed_paths"]
                                    and kind == "services"
                                ):
                                    payload["governed_paths"].append(candidate)
                        files.append(
                            {
                                "path": repository_path,
                                "bytes": len(content),
                                "sha256": hashlib.sha256(content).hexdigest(),
                                "installed_paths": installed,
                            }
                        )
                    declaration = {
                        "schema_version": 1,
                        "service_id": identity,
                        "scope": validator.REPOSITORY_REVIEW_SCOPE,
                        "hosted_runtime_verified": False,
                        "limitations": [
                            "Hashes record repository bytes inspected during packaging; hosted code is not included or executed.",
                            "Installed validation checks local client bytes and this retained review declaration.",
                            "Hosted deployment, live controls and model delivery require separate acceptance evidence.",
                        ],
                        "source_manifest": original,
                        "files": files,
                    }
                    review_path = f"privacy/repository-source-reviews/{identity}.json"
                    raw = contract.canonical_bytes(declaration)
                    local[review_path] = raw
                    (package / review_path).parent.mkdir(parents=True, exist_ok=True)
                    (package / review_path).write_bytes(raw)
                    payload["repository_source_review"] = {
                        "path": review_path,
                        "service_id": identity,
                        "scope": validator.REPOSITORY_REVIEW_SCOPE,
                    }
                    payload["review"][
                        "fingerprint_scope"
                    ] = "installed_client_and_repository_review_declaration"
                if kind == "services":
                    # Keep repository control declarations. Omitted host-only
                    # implementations are disclosed, not silently asserted local.
                    controls = []
                    for control in payload["security_controls"]:
                        implementations = [
                            (
                                path
                                if path.startswith("repository:")
                                else installed_path(path)
                            )
                            for path in control["implemented_by"]
                            if path.startswith("repository:")
                            or (package / installed_path(path)).exists()
                        ]
                        if implementations:
                            control["implemented_by"] = implementations
                            controls.append(control)
                        else:
                            omitted.append("control:" + control["id"])
                    payload["security_controls"] = controls
                if omitted:
                    projection["omitted_paths"][relative] = sorted(omitted)
                payload["review"]["source_fingerprint"] = validator._fingerprint(
                    component,
                    payload["governed_paths"],
                    wrapper=(
                        validator._wrapper(package, name, roles)
                        if kind == "workstreams"
                        else None
                    ),
                    vera_root=package,
                    shared_paths=payload.get("governed_shared_paths", []),
                    repository_paths=repository_paths,
                    repository_review=payload.get("repository_source_review"),
                )
                raw = contract.canonical_bytes(payload)
                local[relative] = raw
                (package / relative).write_bytes(raw)
        reviewed_omissions = registry.get("host_omissions", {}).get(host, {})
        if sorted(projection["omitted_workstreams"]) != sorted(
            reviewed_omissions.get("workstreams", [])
        ) or projection["omitted_paths"] != reviewed_omissions.get("paths", {}):
            raise ValueError(
                f"{product}/{host}: package omissions differ from the reviewed host contract"
            )
        local["privacy/package-projection.json"] = contract.canonical_bytes(projection)
        index = {
            "schema_version": 1,
            "product": product,
            "contracts": source_index["contracts"],
            "installed_contracts": {},
        }
        for name in registry["workstreams"]:
            index["installed_contracts"][name] = hashlib.sha256(
                contract.canonical_bytes(contract.contract_document(package, name))
            ).hexdigest()
        local["privacy/contracts/index.json"] = contract.canonical_bytes(index)
        (package / "privacy/contracts/index.json").write_bytes(
            local["privacy/contracts/index.json"]
        )
        errors = validator.validate_privacy_surfaces(package)
        if errors:
            raise ValueError(
                f"{product}/{host}: installed privacy review failed: "
                + "; ".join(errors)
            )
        for name, record in registry["workstreams"].items():
            if record["workflow_ids"]:
                contract.bind_run(package, record["workflow_ids"][0], host)
    for name in list(entries):
        if name.startswith(prefix) and name.removeprefix(prefix).startswith("privacy/"):
            del entries[name]
    entries.update({prefix + name: raw for name, raw in local.items()})
    return projection
