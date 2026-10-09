"""Exact source preparation and complete model proposals over public invoice APIs.

Membership, byte inventories and CAS are mechanical authorization checks.
Source grouping, extraction meaning and fiscal decisions remain model judgments.
"""

from __future__ import annotations

import json
import re
import tempfile
from pathlib import Path
from typing import Any

from native_bank_preparation import tree_hash
from native_invoice import engine

__all__ = [
    "artifact_names",
    "audit_evidence",
    "dispatch_evidence",
    "evidence_context",
    "inspect",
]


def artifact_names(record: dict) -> set[str]:
    """Close the actual public draft, original proposal and every prepared page."""
    ref = record["proposal_sha256"]
    return (
        {
            "draft-" + ref + "/" + name
            for name in (
                "proposal.json",
                "validation.json",
                "preview.html",
                "review_request.json",
            )
        }
        | {"invoice-native-proposal-" + ref + ".json"}
        | set(record["intake_artifacts"])
    )


def audit_evidence(base: Path, state: dict, api: Any) -> bool:
    """Reject altered pages and flag unreceipted work without adopting an outcome."""
    known, requests = set(), set()
    recovery = False
    for row in state.get("evidence", []):
        ref, request = row["evidence_ref"], row["request_ref"]
        if (
            not re.fullmatch(r"evidence-[0-9a-f]{64}", ref)
            or ref in known
            or not re.fullmatch(r"evidence-request-[0-9a-f]{64}\.json", request)
            or request in requests
        ):
            raise ValueError("Invalid prepared invoice evidence receipt")
        known.add(ref)
        requests.add(request)
        if tree_hash(base / ref) != row["artifacts"]:
            raise ValueError("Prepared invoice text or pages changed")
        if api.read_json(base / ref / "source_evidence.json") != row["manifest"]:
            raise ValueError("Invoice evidence inventory changed")
        path = base / request
        receipt = api.read_json(path) if path.exists() else {}
        recovery |= (
            receipt.get("result") != row["result"]
            or receipt.get("artifacts") != row["artifacts"]
        )
    recovery |= any(p.name not in known for p in base.glob("evidence-*") if p.is_dir())
    recovery |= any(
        p.name not in requests or "result" not in api.read_json(p)
        for p in base.glob("evidence-request-*.json")
    )
    return recovery


def evidence_context(base: Path, state: dict) -> list[dict]:
    """Expose complete material inventories, never assert pages actually reached vision."""
    return [
        {
            "evidence_ref": row["evidence_ref"],
            "views_directory": str(base / row["evidence_ref"]),
            "manifest": row["manifest"],
        }
        for row in state.get("evidence", [])
    ]


def dispatch_evidence(
    args: dict, binding: dict, loaded: dict, root: Path, api: Any
) -> dict:
    """Prepare complete originals with the unchanged helper under an explicit source mandate."""
    from native_aml_authoring import grant, home, snapshot

    with api.write_lock(Path(loaded["output_dir"])):
        loaded = api.load_binding(binding)
        current = snapshot(binding, loaded, root, api)
        base, value = grant(home(binding, loaded, api), args, current, api)
        if not current["can_write"]:
            raise PermissionError(
                "Invoice source preparation requires a running reviewer run without uncertain writes"
            )
        key = args["idempotency_key"]
        if not re.fullmatch(r"[A-Za-z0-9_-]{1,120}", key):
            raise ValueError("Invalid invoice evidence request key")
        intent = base / ("evidence-request-" + api.digest(key) + ".json")
        fingerprint = api.digest([binding, args])
        if intent.exists():
            receipt = api.read_json(intent)
            if receipt["request_sha256"] != fingerprint or "result" not in receipt:
                raise ValueError(
                    "Invoice evidence request changed or requires recovery"
                )
            return receipt["result"]
        state_path = base / "state.json"
        state = (
            api.read_json(state_path)
            if state_path.exists()
            else {"stages": [], "publications": []}
        )
        stamp = api.digest(state) if state_path.exists() else ""
        if args["expected_stage_revision"] != stamp:
            raise ValueError("Concurrent invoice preparation; reread the mandate")
        selection = args["selection"]
        indexed = {r["relative_path"]: r for r in value["sources"]}
        fields = {"id", "path", "title", "role", "evidence_group"}
        if (
            not isinstance(selection, list)
            or len(selection) != len(indexed)
            or any(not isinstance(r, dict) or set(r) != fields for r in selection)
            or any(
                any(
                    not isinstance(v, str) or not v.strip() or len(v) > 4000
                    for v in r.values()
                )
                for r in selection
            )
            or {r["path"] for r in selection} != set(indexed)
            or len({r["id"] for r in selection}) != len(selection)
            or any(
                r["role"]
                not in {
                    "invoice",
                    "party_profile",
                    "professional_confirmation",
                    "context",
                }
                for r in selection
            )
        ):
            raise PermissionError(
                "Prepare every chosen original once with explicit grouping and source role"
            )
        ref = "evidence-" + api.digest(selection)
        target = base / ref
        if target.exists():
            raise ValueError(
                "This source selection is already prepared; choose its retained receipt"
            )
        # Render before durable intent; unsupported/illegible formats leave no adopted work.
        # The actual prepared directory is then moved atomically, without rendering twice.
        with tempfile.TemporaryDirectory(
            prefix="inspect-invoice-evidence-", dir=base
        ) as temporary:
            directory = Path(temporary)
            request = directory / "selection.json"
            api.atomic_json(request, selection)
            prepared = engine(
                root,
                {
                    "operation": "prepare_evidence",
                    "context": str(loaded["context_path"]),
                    "selection": str(request),
                    "output": str(directory),
                },
            )
            if any(
                r["sha256"] != indexed[r["path"]]["sha256"]
                for r in prepared["manifest"]["sources"]
            ):
                raise ValueError("Invoice originals changed during preparation")
            if (
                snapshot(binding, api.load_binding(binding), root, api)["identity"]
                != current["identity"]
            ):
                raise ValueError(
                    "Invoice source scope changed before evidence retention"
                )
            result = {
                "evidence_ref": ref,
                "views_directory": str(target),
                "manifest": prepared["manifest"],
                "model_exposure_verified": False,
            }
            if len(json.dumps(result).encode()) > 100_000:
                raise ValueError(
                    "Complete invoice evidence inventory exceeds model context limit; use the specialist route"
                )
            api.atomic_json(intent, {"request_sha256": fingerprint})
            Path(prepared["directory"]).rename(target)
            if (
                snapshot(binding, api.load_binding(binding), root, api)["identity"]
                != current["identity"]
            ):
                raise ValueError(
                    "Invoice originals changed during retention; recovery required"
                )
            artifacts = tree_hash(target)
            state.setdefault("evidence", []).append(
                {
                    "evidence_ref": ref,
                    "request_ref": intent.name,
                    "manifest": prepared["manifest"],
                    "artifacts": artifacts,
                    "result": result,
                }
            )
            api.atomic_json(state_path, state)
            api.atomic_json(
                intent,
                {
                    "request_sha256": fingerprint,
                    "result": result,
                    "artifacts": artifacts,
                },
            )
            return result


def inspect(
    review: dict,
    value: dict,
    loaded: dict,
    root: Path,
    base: Path,
    api: Any,
    *,
    save: bool = False,
) -> dict:
    """Replay the complete public proposal and captured material without new approvals."""
    if (
        not isinstance(review, dict)
        or set(review) != {"proposal", "evidence_ref"}
        or not isinstance(review["proposal"], dict)
        or not set(review["proposal"])
        <= {
            "schema_version",
            "draft_id",
            "route",
            "transmission_mode",
            "sources",
            "invoice",
            "field_evidence",
            "decisions",
            "questions",
        }
    ):
        raise ValueError("Propose a complete invoice without export or approval fields")
    state = api.read_json(base / "state.json")
    prepared = next(
        (
            r
            for r in state.get("evidence", [])
            if r["evidence_ref"] == review["evidence_ref"]
        ),
        None,
    )
    if (
        prepared is None
        or review["proposal"].get("sources") != prepared["manifest"]["sources"]
    ):
        raise PermissionError(
            "Use exactly this mandate's complete prepared original-source records"
        )
    indexed = {r["relative_path"]: r["sha256"] for r in value["sources"]}
    if {r["path"]: r["sha256"] for r in review["proposal"]["sources"]} != indexed:
        raise PermissionError(
            "Prepared invoice sources differ from the chosen original receipts"
        )
    with tempfile.TemporaryDirectory(
        prefix="inspect-invoice-proposal-", dir=base
    ) as temporary:
        request = Path(temporary) / "proposal.json"
        api.atomic_json(request, review["proposal"])
        return engine(
            root,
            {
                "operation": "save_proposal" if save else "inspect_proposal",
                "context": str(loaded["context_path"]),
                "proposal": str(request),
                "expected_intake_artifacts": prepared["artifacts"],
            },
        )
