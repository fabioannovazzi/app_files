"""Optional native SARI initialization, ordinary inventory and explicit text selection."""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from datetime import date
from pathlib import Path
from typing import Any

from native_bank_preparation import file_hash, tree_hash

__all__ = ["dispatch", "audit_run"]


def engine(root: Path, request: dict) -> dict:
    """Call only fixed offline public producers in an isolated interpreter."""
    result = subprocess.run(
        [
            sys.executable,
            "-I",
            "-B",
            str(Path(__file__).with_name("native_sari_intake_bridge.py")),
            str(root),
        ],
        input=json.dumps(request),
        text=True,
        capture_output=True,
        timeout=90,
        check=False,
    )
    if result.returncode:
        raise ValueError(
            result.stderr.strip().splitlines()[-1] or "SARI intake refused"
        )
    return json.loads(result.stdout)


def bounded(value: dict, limit: int = 2_000_000) -> dict:
    """Refuse complete oversized content rather than silently truncate evidence."""
    if len(json.dumps(value, ensure_ascii=False).encode()) > limit:
        raise ValueError(
            "Complete SARI content exceeds native limit; use ordinary files"
        )
    return value


def audit_run(output: Path, api: Any) -> dict:
    """Keep uncertain intake writes visible and unavailable for duplicate execution."""
    path = api.ui_state_directory(output, create=False) / "sari-intake-operations.json"
    state = api.read_json(path) if path.exists() else {"operations": []}
    known = set()
    for row in state["operations"]:
        if row["key"] in known or row["fingerprint"] != api.digest(row["request"]):
            raise ValueError("SARI intake operation identity changed")
        known.add(row["key"])
        if row["status"] not in {"pending", "complete"}:
            raise ValueError("Invalid SARI intake operation status")
        if row["status"] == "complete" and row["receipt_sha256"] != api.digest(
            row["receipt"]
        ):
            raise ValueError("SARI intake receipt changed")
    return {
        "state": state,
        "recovery_required": any(
            row["status"] == "pending" for row in state["operations"]
        ),
    }


def fields(value: Any, *, complete: bool = False) -> dict:
    """Validate literal parameters; jurisdiction is never inferred from language."""
    if not isinstance(value, dict) or set(value) != {
        "reference_date",
        "client_reference",
        "language",
        "jurisdiction",
    }:
        raise ValueError("Invalid SARI initial parameters")
    if any(not isinstance(v, str) for v in value.values()):
        raise ValueError("SARI parameters must be literal text")
    if value["language"] not in {"it", "en", "fr", "de", "es"} or value[
        "jurisdiction"
    ] not in {"IT", "CH-GE"}:
        raise ValueError("Unsupported SARI language or jurisdiction")
    if len(value["reference_date"]) > 10 or len(value["client_reference"]) > 80:
        raise ValueError("SARI parameter exceeds its public limit")
    if complete:
        if (
            date.fromisoformat(value["reference_date"]).isoformat()
            != value["reference_date"]
        ):
            raise ValueError("Use an exact ISO reference date")
        if (
            re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]{0,79}", value["client_reference"])
            is None
        ):
            raise ValueError("Use the public safe client reference")
    return value


def snapshot(binding: dict, loaded: dict, root: Path, api: Any) -> dict:
    output = Path(loaded["output_dir"])
    before = tree_hash(output)
    audit = audit_run(output, api)
    identity = {
        "owner": [
            os.environ["VERA_WORKSPACE_TENANT_ID"],
            os.environ["VERA_WORKSPACE_ACTOR_ID"],
        ],
        "binding": binding,
        "run": loaded["run"],
        "inputs": loaded["input_manifest"],
        "outputs": before,
        "implementation": [
            engine(root, {"operation": "implementation"}),
            file_hash(Path(__file__)),
            file_hash(Path(__file__).with_name("native_sari_intake_bridge.py")),
        ],
    }
    inventory_path = output / "local_evidence_inventory.json"
    inventory = api.read_json(inventory_path) if inventory_path.exists() else None
    if inventory is not None:
        if inventory["plugin"] != root.name or inventory["run_id"] != binding["run_id"]:
            raise PermissionError("Registry inventory belongs to another run")
        originals = {
            Path(row["execution_relative_path"])
            .relative_to("inputs")
            .as_posix(): row["sha256"]
            for row in loaded["input_manifest"]["inputs"]
        }
        if (
            len(inventory["documents"]) != inventory["document_count"]
            or len({row["document_id"] for row in inventory["documents"]})
            != len(inventory["documents"])
            or len({row["relative_path"] for row in inventory["documents"]})
            != len(inventory["documents"])
        ):
            raise ValueError("Registry inventory population changed")
        if {
            row["relative_path"]: row["sha256"] for row in inventory["documents"]
        } != originals:
            raise ValueError("Registry inventory differs from registered originals")
        for row in inventory["documents"]:
            if row["text_path"] is not None:
                name = "extracted/" + row["document_id"] + ".txt"
                if row["text_path"] != name or before.get(name) != row["text_sha256"]:
                    raise ValueError("Registry extracted text changed")
    if tree_hash(output) != before:
        raise ValueError("Registry outputs changed while reading; reopen intake")
    return {
        "output": output,
        "identity": identity,
        "revision": api.digest(identity),
        "files": before,
        "inventory": inventory,
        **audit,
    }


def draft(current: dict, api: Any) -> tuple[Path, dict, str]:
    path = api.ui_state_directory(current["output"], create=False) / (
        "sari-intake-draft-" + api.digest(current["identity"]["owner"]) + ".json"
    )
    saved = (
        api.read_json(path)
        if path.exists()
        else {
            "identity": current["identity"],
            "generation": 0,
            "fields": {
                "reference_date": "",
                "client_reference": "",
                "language": "it",
                "jurisdiction": "IT",
            },
        }
    )
    fields(saved["fields"])
    return path, saved, api.digest(saved)


def dispatch(
    tool: str, args: dict, binding: dict, loaded: dict, root: Path, api: Any
) -> dict:
    """Separate incomplete private parameters, explicit extraction and model context."""
    if (
        binding["workflow_id"] != "registro-imprese-sari"
        or root.name != binding["workflow_id"]
    ):
        raise PermissionError("Registry intake belongs to another workflow")
    action = tool.removeprefix("vera_workspace_sari_")
    current = snapshot(binding, loaded, root, api)
    path, saved, stamp = draft(current, api)
    documents = current["inventory"]["documents"] if current["inventory"] else []
    can_write = (
        loaded["run"]["status"] == "running"
        and "REVIEWER" in os.environ.get("VERA_WORKSPACE_ROLES", "").split(",")
        and not current["recovery_required"]
    )
    base = {
        "work_ref": binding["work_ref"],
        "revision": current["revision"],
        "source_ref": current["files"].get("local_evidence_inventory.json", ""),
        "draft_revision": stamp,
        "fields": saved["fields"],
        "draft_stale": saved["identity"] != current["identity"],
        "run_status": loaded["run"]["status"],
        "can_write": can_write,
        "can_prepare": can_write and not current["files"],
        "recovery_required": current["recovery_required"],
        "setup_status": (
            "inventory_available"
            if current["inventory"]
            else (
                "ordinary_continuation_required"
                if current["files"]
                else "initialization_required"
            )
        ),
        "actual_model_reads_verified": False,
    }
    if action == "setup":
        offset = args.get("offset", 0)
        if type(offset) is not int or offset < 0:
            raise ValueError("Invalid registry page offset")
        return bounded(
            {
                **base,
                "offset": offset,
                "total": len(documents),
                "has_more": offset + 30 < len(documents),
                "sources": [
                    {
                        "name": Path(row["execution_relative_path"])
                        .relative_to("inputs")
                        .as_posix(),
                        "sha256": row["sha256"],
                    }
                    for row in loaded["input_manifest"]["inputs"]
                ],
                "rows": [
                    {
                        key: row[key]
                        for key in (
                            "document_id",
                            "relative_path",
                            "extraction_status",
                            "limitations",
                        )
                    }
                    for row in documents[offset : offset + 30]
                ],
            }
        )
    if action in {"read", "context", "outputs"}:
        if args["revision"] != current["revision"]:
            raise ValueError("Registry sources or outputs changed; reopen")
        if action == "outputs":
            names = {
                "case_intake_draft.json",
                "practice_plan_draft.json",
                "run_intake.json",
                "local_evidence_inventory.json",
            }
            return bounded(
                {
                    **base,
                    "files": [
                        {
                            "name": name,
                            "sha256": checksum,
                            "content": (current["output"] / name).read_text(
                                encoding="utf-8"
                            ),
                        }
                        for name, checksum in current["files"].items()
                        if name in names
                    ],
                }
            )
        inventory_hash = current["files"].get("local_evidence_inventory.json")
        if args["source_ref"] != inventory_hash:
            raise ValueError("Choose the exact registry inventory")
        row = next(
            (row for row in documents if row["document_id"] == args["item_id"]), None
        )
        if row is None:
            raise PermissionError("Choose one document from this registry run")
        content = (
            (current["output"] / row["text_path"]).read_text(encoding="utf-8")
            if row["text_path"]
            else None
        )
        evidence = {
            key: row[key]
            for key in (
                "document_id",
                "relative_path",
                "sha256",
                "extraction_status",
                "limitations",
                "text_sha256",
            )
        }
        return bounded(
            {
                "work_ref": binding["work_ref"],
                "revision": current["revision"],
                "source_ref": inventory_hash,
                "evidence": evidence,
                "content": content,
                "actual_model_reads_verified": False,
                "untrusted_evidence": True,
                "professional_review": "pending",
            },
            64_000 if action == "context" else 2_000_000,
        )
    if action not in {"draft_save", "draft_clear", "prepare"}:
        raise ValueError("Unsupported native registry intake action")
    if not can_write:
        raise PermissionError("Registry intake is read-only or requires recovery")
    if action == "prepare":
        key = args["idempotency_key"]
        if not isinstance(key, str) or not 1 <= len(key) <= 200:
            raise ValueError("Invalid registry operation key")
        request = {
            key: value for key, value in args.items() if key != "idempotency_key"
        }
        previous = next(
            (row for row in current["state"]["operations"] if row["key"] == key), None
        )
        if previous is not None:
            if previous["request"] != request or previous["status"] != "complete":
                raise ValueError("Registry retry differs or has an uncertain outcome")
            return previous["receipt"]
    if (
        args["revision"] != current["revision"]
        or args["expected_draft_revision"] != stamp
    ):
        raise ValueError("Registry scope or private draft changed; reopen")
    if action != "draft_save" and args.get("confirmed") is not True:
        raise PermissionError("Registry action requires renewed confirmation")
    proposed = (
        fields(args["fields"], complete=action == "prepare")
        if action != "draft_clear"
        else None
    )
    if action == "prepare" and (
        current["files"]
        or saved["identity"] != current["identity"]
        or saved["fields"] != proposed
    ):
        raise ValueError(
            "Prepare only the exact saved initial parameters on an empty run"
        )
    with api.write_lock(current["output"]):
        refreshed = snapshot(binding, api.load_binding(binding), root, api)
        _, newest, newest_stamp = draft(refreshed, api)
        if refreshed["revision"] != current["revision"] or newest_stamp != stamp:
            raise ValueError("Registry state changed before write")
        if action in {"draft_save", "draft_clear"}:
            record = {
                "identity": current["identity"],
                "generation": newest["generation"] + 1,
                "fields": (
                    proposed
                    if proposed is not None
                    else {
                        "reference_date": "",
                        "client_reference": "",
                        "language": "it",
                        "jurisdiction": "IT",
                    }
                ),
            }
            api.atomic_json(path, record)
            return {
                **base,
                "saved": True,
                "status": "private_parameters_saved",
                "fields": record["fields"],
                "draft_revision": api.digest(record),
                "draft_stale": False,
            }
        operation = {
            "key": key,
            "request": request,
            "fingerprint": api.digest(request),
            "status": "pending",
        }
        state = current["state"]
        state["operations"].append(operation)
        state_path = (
            api.ui_state_directory(current["output"], create=False)
            / "sari-intake-operations.json"
        )
        api.atomic_json(state_path, state)
        result = engine(
            root,
            {
                "operation": "prepare",
                "context": str(loaded["context_path"]),
                "fields": proposed,
            },
        )
        receipt = {
            "work_ref": binding["work_ref"],
            **result,
            "artifacts": tree_hash(current["output"]),
        }
        operation.update(
            status="complete", receipt=receipt, receipt_sha256=api.digest(receipt)
        )
        api.atomic_json(state_path, state)
        return receipt
