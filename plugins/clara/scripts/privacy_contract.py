"""Bind a local run to its reviewed product contract without inventing observations.

IDs and hashes are mechanical integrity checks. The host agent must compare the
actual run with the reviewed description; this module makes no semantic verdict.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

__all__ = [
    "PrivacyContractError",
    "bind_run",
    "canonical_bytes",
    "contract_document",
    "validate_binding",
]
PRODUCTS = {"vera", "clara", "lucia"}


class PrivacyContractError(ValueError):
    """A product privacy contract is missing, foreign or inconsistent."""


def canonical_bytes(value: Any) -> bytes:
    """Use one stable representation for public and local contract identity."""
    return (
        json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        + "\n"
    ).encode("utf-8")


def _digest(value: Any) -> str:
    return hashlib.sha256(canonical_bytes(value)).hexdigest()


def _read(root: Path, relative: str) -> dict[str, Any]:
    path = root / relative
    if path.is_symlink():
        raise PrivacyContractError(f"Contract must not be a symlink: {relative}")
    try:
        path.resolve(strict=True).relative_to(root.resolve())
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise PrivacyContractError(f"Cannot read product contract: {relative}") from exc
    if not isinstance(value, dict):
        raise PrivacyContractError(f"Contract must be an object: {relative}")
    return value


def _identifier(value: Any) -> bool:
    return (
        isinstance(value, str)
        and bool(value)
        and value[0].isalpha()
        and all(
            character in "abcdefghijklmnopqrstuvwxyz0123456789-" for character in value
        )
    )


def _sha256(value: Any) -> bool:
    return (
        isinstance(value, str)
        and len(value) == 64
        and all(character in "0123456789abcdef" for character in value)
    )


def contract_document(root: Path, workstream: str) -> dict[str, Any]:
    """Compose a source contract; package projections retain this exact document."""
    if not _identifier(workstream):
        raise PrivacyContractError("Invalid workstream identity")
    registry = _read(root, "privacy/registry.json")
    product = registry["product"]
    if product not in PRODUCTS or workstream not in registry["workstreams"]:
        raise PrivacyContractError("Unknown product/workstream contract")
    manifest = _read(root, f"privacy/workstreams/{workstream}.json")
    if manifest["workstream"] != workstream:
        raise PrivacyContractError("Foreign workstream manifest")
    profiles = _read(root, "privacy/runtime-profiles.json")["profiles"]
    services = {}
    for service in manifest["service_ids"]:
        if not _identifier(service) or service not in registry["services"]:
            raise PrivacyContractError("Unknown service contract")
        services[service] = _read(root, f"privacy/services/{service}.json")
    return {
        "schema_version": 1,
        "product": product,
        "workstream": workstream,
        "registration": registry["workstreams"][workstream],
        "host_omissions": registry.get("host_omissions", {}),
        "manifest": manifest,
        "services": services,
        "runtime_profiles": [
            profile
            for profile in profiles
            if profile["id"] in manifest["runtime_profiles"]
        ],
        "scope": "reviewed_source_contract_not_observed_run_or_hosted_deployment",
    }


def bind_run(
    product_root: Path, workflow_id: str, runtime_profile: str
) -> dict[str, Any]:
    """Read exact published/source and installed-manifest identities for one run."""
    root = product_root.resolve()
    registry = _read(root, "privacy/registry.json")
    product = registry["product"]
    metadata = (
        _read(root, ".codex-plugin/plugin.json")
        if (root / ".codex-plugin/plugin.json").is_file()
        else _read(root, ".claude-plugin/plugin.json")
    )
    if product not in PRODUCTS or metadata["name"] != product:
        raise PrivacyContractError("Privacy product does not match installed product")
    matches = [
        name
        for name, entry in registry["workstreams"].items()
        if workflow_id in entry["workflow_ids"]
    ]
    if len(matches) != 1:
        raise PrivacyContractError(
            f"Workflow needs exactly one privacy contract: {workflow_id}"
        )
    workstream = matches[0]
    retained = _read(root, f"privacy/contracts/{workstream}.json")
    if (
        retained.get("product") != product
        or retained.get("workstream") != workstream
        or retained.get("schema_version") != 1
    ):
        raise PrivacyContractError("Retained privacy contract has a foreign identity")
    manifest = _read(root, f"privacy/workstreams/{workstream}.json")
    if manifest.get("workstream") != workstream:
        raise PrivacyContractError("Installed privacy manifest has a foreign identity")
    digest = _digest(retained)
    index = _read(root, "privacy/contracts/index.json")
    if index.get("product") != product or index["contracts"].get(workstream) != digest:
        raise PrivacyContractError("Retained privacy contract does not match its index")
    if index["installed_contracts"].get(workstream) != _digest(
        contract_document(root, workstream)
    ):
        raise PrivacyContractError(
            "Installed privacy dependencies changed after packaging"
        )
    projection = manifest.get("source_contract_sha256")
    if projection is not None:
        if projection != digest:
            raise PrivacyContractError(
                "Installed privacy manifest is bound to a different source review"
            )
    elif retained["manifest"] != manifest:
        raise PrivacyContractError("Privacy source changed after the retained review")
    registered_profiles = manifest["runtime_profiles"]
    binding = {
        "schema_version": 1,
        "product": product,
        "product_version": metadata["version"],
        "workflow_id": workflow_id,
        "workstream": workstream,
        "runtime_profile": runtime_profile,
        "status": (
            "bound"
            if runtime_profile in registered_profiles
            and manifest.get("packaged_for_runtime", runtime_profile) == runtime_profile
            else "runtime_not_reviewed"
        ),
        "contract_sha256": digest,
        "installed_manifest_sha256": _digest(manifest),
        "reviewed_source_fingerprint": retained["manifest"]["review"][
            "source_fingerprint"
        ],
        "installed_source_fingerprint": manifest["review"]["source_fingerprint"],
        "scope": "reviewed_contract_reference_not_actual_exposure_verification",
    }
    validate_binding(binding, workflow_id=workflow_id, runtime_profile=runtime_profile)
    return binding


def validate_binding(value: Any, *, workflow_id: str, runtime_profile: str) -> None:
    """Validate a historical binding offline without requiring today's package."""
    fields = {
        "schema_version",
        "product",
        "product_version",
        "workflow_id",
        "workstream",
        "runtime_profile",
        "status",
        "contract_sha256",
        "installed_manifest_sha256",
        "reviewed_source_fingerprint",
        "installed_source_fingerprint",
        "scope",
    }
    if not isinstance(value, dict) or set(value) != fields:
        raise PrivacyContractError("Invalid privacy contract binding fields")
    if (
        value["schema_version"] != 1
        or value["product"] not in PRODUCTS
        or value["workflow_id"] != workflow_id
        or value["runtime_profile"] != runtime_profile
        or not _identifier(value["workstream"])
        or not isinstance(value["product_version"], str)
        or not value["product_version"]
        or value["status"] not in {"bound", "runtime_not_reviewed"}
        or value["scope"]
        != "reviewed_contract_reference_not_actual_exposure_verification"
    ):
        raise PrivacyContractError("Invalid privacy contract binding identity")
    for field in (
        "contract_sha256",
        "installed_manifest_sha256",
        "reviewed_source_fingerprint",
        "installed_source_fingerprint",
    ):
        if not _sha256(value[field]):
            raise PrivacyContractError(f"Invalid privacy binding digest: {field}")
