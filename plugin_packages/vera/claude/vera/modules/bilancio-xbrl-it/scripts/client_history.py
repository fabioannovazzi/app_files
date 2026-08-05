#!/usr/bin/env python3
"""Tenant-isolated reuse of approved client knowledge as suggestions only."""

from __future__ import annotations

import hashlib
import json
import tempfile
from pathlib import Path
from typing import Any, Mapping

__all__ = ["client_history_suggestions", "remember_approved_client_history"]

SCHEMA_VERSION = 1


def _canonical_hash(value: Any) -> str:
    encoded = json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _client_key(case: Mapping[str, Any]) -> str:
    stable = str(case["entity"].get("client_id") or case["entity"]["tax_identifier"])
    material = f"{case['tenant_id']}\x00{stable}".encode("utf-8")
    return hashlib.sha256(material).hexdigest()


def _read_store(path: Path, tenant_id: str) -> dict[str, Any]:
    if path.is_symlink():
        raise ValueError("Client history must not use a symbolic link")
    if not path.exists():
        return {
            "schema_version": SCHEMA_VERSION,
            "tenant_id": tenant_id,
            "clients": [],
        }
    if not path.is_file():
        raise ValueError("Client history must be a regular JSON file")
    store = json.loads(path.read_text(encoding="utf-8"))
    if store.get("schema_version") != SCHEMA_VERSION:
        raise ValueError("Unsupported client-history schema version")
    if store.get("tenant_id") != tenant_id:
        raise ValueError("Cross-tenant client-history access is forbidden")
    if not isinstance(store.get("clients"), list):
        raise ValueError("Client-history clients must be an array")
    return store


def client_history_suggestions(
    case: Mapping[str, Any], history_path: Path
) -> dict[str, Any]:
    """Return the most recent earlier approved history as unconfirmed suggestions."""

    store = _read_store(history_path.resolve(), str(case["tenant_id"]))
    current_end = str(case["period"]["end"])
    candidates = [
        item
        for item in store["clients"]
        if item.get("client_key") == _client_key(case)
        and str(item.get("period_end", "")) < current_end
    ]
    if not candidates:
        return {
            "source": "APPROVED_CLIENT_HISTORY",
            "prior_period_end": None,
            "form_suggestion": None,
            "answer_suggestions": [],
            "narrative_suggestions": [],
            "recurring_evidence_suggestions": [],
        }
    prior = max(candidates, key=lambda item: str(item["period_end"]))
    snapshot_ref = f"approved_snapshot:{prior['snapshot_hash']}"
    return {
        "source": "APPROVED_CLIENT_HISTORY",
        "prior_period_end": prior["period_end"],
        "form_suggestion": {
            "selected_form": prior["selected_form"],
            "status": "UNCONFIRMED_PRIOR_SUGGESTION",
            "source_ref": snapshot_ref,
        },
        "answer_suggestions": [
            {
                "key": item["key"],
                "value": item.get("value"),
                "prior_status": item["prior_status"],
                "status": "UNCONFIRMED_PRIOR_SUGGESTION",
                "requires_reconfirmation": True,
                "source_refs": [snapshot_ref],
            }
            for item in prior["answers"]
        ],
        "narrative_suggestions": [
            {
                "suggestion_id": (
                    f"client_history_{prior['period_end']}_{item['block_id']}"
                ),
                "section_id": item["section_id"],
                "text": item["text"],
                "status": "UNCONFIRMED_STALE_SUGGESTION",
                "requires_redline": True,
                "source_refs": [snapshot_ref],
            }
            for item in prior["narratives"]
        ],
        "recurring_evidence_suggestions": [
            {
                "rule_id": rule_id,
                "status": "PRIOR_PERIOD_TRIGGER_ONLY",
                "requires_current_period_evaluation": True,
                "source_refs": [snapshot_ref],
            }
            for rule_id in prior["triggered_rule_ids"]
        ],
    }


def remember_approved_client_history(
    case: Mapping[str, Any], history_path: Path, actor: str
) -> dict[str, Any]:
    """Persist reviewed form, answers, and narrative without current amounts."""

    approval = case.get("approval")
    if not approval or case.get("state") not in {"APPROVED", "EXPORTED"}:
        raise ValueError("Only approved cases may enter client history")
    if _canonical_hash(approval.get("snapshot")) != approval.get("snapshot_hash"):
        raise ValueError("Approved client-history snapshot hash is invalid")
    target = history_path.resolve()
    store = _read_store(target, str(case["tenant_id"]))
    snapshot = approval["snapshot"]
    record = {
        "client_key": _client_key(case),
        "period_end": snapshot["period"]["end"],
        "selected_form": snapshot["selected_form"],
        "answers": [
            {
                "key": item["key"],
                "value": item.get("value"),
                "prior_status": item["status"],
            }
            for item in snapshot.get("disclosure_answers", [])
            if item.get("status") in {"ACCEPTED", "NOT_APPLICABLE_CONFIRMED"}
        ],
        "narratives": [
            {
                "block_id": item["block_id"],
                "section_id": item["section_id"],
                "text": item["text"],
            }
            for item in snapshot.get("narrative_blocks", [])
            if item.get("status") == "ACCEPTED"
        ],
        "triggered_rule_ids": [
            item["rule_id"]
            for item in (snapshot.get("disclosure_coverage") or {}).get("coverage", [])
            if item.get("triggered")
        ],
        "snapshot_hash": approval["snapshot_hash"],
        "remembered_by": actor,
    }
    store["clients"] = [
        item
        for item in store["clients"]
        if not (
            item.get("client_key") == record["client_key"]
            and item.get("period_end") == record["period_end"]
        )
    ] + [record]
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.is_symlink():
        raise ValueError("Refusing to write client history through a symbolic link")
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
    return {
        "remembered_period_end": record["period_end"],
        "history_file_name": target.name,
    }
