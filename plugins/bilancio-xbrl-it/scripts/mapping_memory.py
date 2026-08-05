#!/usr/bin/env python3
"""Tenant-isolated reuse of explicitly approved account mappings.

Exact tenant, client-key, source-template, and account-code matching is used
because cross-tenant isolation and precedence are audit requirements. This
module never infers account meaning from descriptions or code patterns.
"""

from __future__ import annotations

import hashlib
import json
import tempfile
from copy import deepcopy
from pathlib import Path
from typing import Any, Mapping

__all__ = ["mapping_candidates", "remember_approved_mappings"]

SCHEMA_VERSION = 1


def _canonical_hash(value: Any) -> str:
    encoded = json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _client_key(case: Mapping[str, Any]) -> str:
    entity = case["entity"]
    stable = str(entity.get("client_id") or entity["tax_identifier"])
    material = f"{case['tenant_id']}\x00{stable}".encode("utf-8")
    return hashlib.sha256(material).hexdigest()


def _read_store(path: Path, tenant_id: str) -> dict[str, Any]:
    if path.is_symlink():
        raise ValueError("Mapping memory must not be read through a symbolic link")
    if not path.exists():
        return {
            "schema_version": SCHEMA_VERSION,
            "tenant_id": tenant_id,
            "client_mappings": [],
            "tenant_mappings": [],
        }
    if not path.is_file():
        raise ValueError("Mapping memory must be a regular JSON file")
    payload = json.loads(path.read_text(encoding="utf-8"))
    if payload.get("schema_version") != SCHEMA_VERSION:
        raise ValueError("Unsupported mapping-memory schema version")
    if payload.get("tenant_id") != tenant_id:
        raise ValueError("Cross-tenant mapping-memory access is forbidden")
    for key in ("client_mappings", "tenant_mappings"):
        if not isinstance(payload.get(key), list):
            raise ValueError(f"Mapping-memory field {key} must be an array")
    return payload


def mapping_candidates(
    case: Mapping[str, Any], memory_path: Path, source_system_template: str
) -> list[dict[str, Any]]:
    """Return exact approved candidates with client scope taking precedence."""

    template = source_system_template.strip()
    if not template:
        raise ValueError("A source-system template identifier is required")
    if memory_path.is_symlink():
        raise ValueError("Mapping memory must not be read through a symbolic link")
    store = _read_store(memory_path.resolve(), str(case["tenant_id"]))
    client_key = _client_key(case)
    client_lookup = {
        (item["source_system_template"], item["account_code"]): item
        for item in store["client_mappings"]
        if item.get("client_key") == client_key
    }
    tenant_lookup = {
        (item["source_system_template"], item["account_code"]): item
        for item in store["tenant_mappings"]
    }
    candidates: list[dict[str, Any]] = []
    for account in (case.get("trial_balance") or {}).get("entries", []):
        key = (template, account["account_code"])
        remembered = client_lookup.get(key) or tenant_lookup.get(key)
        if remembered is None:
            continue
        scope = "CLIENT" if key in client_lookup else "TENANT"
        candidates.append(
            {
                "account_id": account["account_id"],
                "account_code": account["account_code"],
                "candidate_source": f"APPROVED_{scope}_MEMORY",
                "confidence_band": "HIGH",
                "requires_review": True,
                "rationale": "Exact approved tenant-isolated mapping match",
                "allocations": deepcopy(remembered["allocations"]),
                "approved_snapshot_hash": remembered["approved_snapshot_hash"],
            }
        )
    return candidates


def remember_approved_mappings(
    case: Mapping[str, Any],
    memory_path: Path,
    source_system_template: str,
    actor: str,
) -> dict[str, Any]:
    """Persist accepted mappings from an immutable approval snapshot."""

    approval = case.get("approval")
    if not approval or case.get("state") not in {"APPROVED", "EXPORTED"}:
        raise ValueError("Only approved mappings may enter mapping memory")
    if _canonical_hash(approval.get("snapshot")) != approval.get("snapshot_hash"):
        raise ValueError("Approved mapping snapshot hash is invalid")
    template = source_system_template.strip()
    if not template:
        raise ValueError("A source-system template identifier is required")
    if memory_path.is_symlink():
        raise ValueError("Mapping memory must not be written through a symbolic link")
    target = memory_path.resolve()
    store = _read_store(target, str(case["tenant_id"]))
    snapshot = approval["snapshot"]
    accounts = {
        item["account_id"]: item
        for item in (snapshot.get("trial_balance") or {}).get("entries", [])
    }
    client_key = _client_key(case)
    remembered = 0
    for mapping in snapshot.get("mappings", []):
        if mapping.get("decision") != "ACCEPTED":
            continue
        account = accounts.get(mapping["account_id"])
        if account is None:
            raise ValueError("Approved mapping references a missing account")
        scope = str(mapping.get("memory_scope", "CLIENT")).upper()
        if scope not in {"CLIENT", "TENANT"}:
            raise ValueError("Mapping memory scope must be CLIENT or TENANT")
        collection_name = "client_mappings" if scope == "CLIENT" else "tenant_mappings"
        collection = store[collection_name]
        identity = (template, account["account_code"])
        if scope == "CLIENT":
            identity = (*identity, client_key)

        def same_identity(item: Mapping[str, Any]) -> bool:
            candidate: tuple[str, ...] = (
                str(item.get("source_system_template")),
                str(item.get("account_code")),
            )
            if scope == "CLIENT":
                candidate = (*candidate, str(item.get("client_key")))
            return candidate == identity

        collection[:] = [item for item in collection if not same_identity(item)]
        record = {
            "source_system_template": template,
            "account_code": account["account_code"],
            "allocations": [
                {
                    "canonical_line": allocation["canonical_line"],
                    "statement_section": allocation["statement_section"],
                    "xbrl_concept": allocation.get("xbrl_concept"),
                    "xbrl_sign_multiplier": allocation.get("xbrl_sign_multiplier", "1"),
                    "schedule_triggers": list(allocation.get("schedule_triggers", [])),
                }
                for allocation in mapping["allocations"]
            ],
            "approved_snapshot_hash": approval["snapshot_hash"],
            "approved_by": actor,
            "memory_scope": scope,
        }
        if scope == "CLIENT":
            record["client_key"] = client_key
        collection.append(record)
        remembered += 1
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.is_symlink():
        raise ValueError("Refusing to write mapping memory through a symbolic link")
    with tempfile.NamedTemporaryFile(
        mode="w",
        encoding="utf-8",
        prefix=f".{target.name}.",
        suffix=".tmp",
        dir=target.parent,
        delete=False,
    ) as handle:
        handle.write(
            json.dumps(store, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
            + "\n"
        )
        temporary = Path(handle.name)
    temporary.replace(target)
    return {"remembered": remembered, "memory_path": str(target)}
