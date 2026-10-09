"""Optional owned INPS evidence review; ordinary specialist preparation stays authoritative."""

from __future__ import annotations

import hashlib
import json
import os
import re
import subprocess
import sys
from pathlib import Path
from typing import Any

from native_bank_preparation import file_hash, tree_hash

__all__ = ["dispatch", "audit_run"]


def digest(value: Any) -> str:
    """Exact request integrity, not a professional judgment."""
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, ensure_ascii=False).encode()
    ).hexdigest()


def engine(root: Path, value: dict, api: Any) -> dict:
    """Use only the fixed isolated public-review bridge and host runtime."""
    completed = subprocess.run(
        [
            sys.executable,
            "-I",
            "-B",
            str(Path(__file__).with_name("native_inps_bridge.py")),
            str(root),
        ],
        input=json.dumps({**value, "node": api.workbench_module()._node_executable()}),
        text=True,
        capture_output=True,
        check=False,
        timeout=90,
    )
    if completed.returncode:
        raise ValueError(
            completed.stderr.strip().splitlines()[-1] or "INPS public operation refused"
        )
    return json.loads(completed.stdout)


def bounded(value: dict, maximum: int = 2_000_000) -> dict:
    if len(json.dumps(value, ensure_ascii=False).encode()) > maximum:
        raise ValueError(
            "Complete INPS content exceeds the native limit; use the ordinary file route"
        )
    return value


def audit_run(output: Path, api: Any) -> dict:
    """An unfinished public mutation prevents other writes and archive closure."""
    path = api.ui_state_directory(output, create=False) / "inps-operations.json"
    state = api.read_json(path) if path.exists() else {"operations": []}
    known = set()
    for row in state["operations"]:
        if row["key"] in known or row["fingerprint"] != digest(row["request"]):
            raise ValueError("INPS native operation identity changed")
        known.add(row["key"])
        if row["status"] not in {"pending", "complete"}:
            raise ValueError("Invalid INPS operation state")
        if row["status"] == "complete" and row["receipt_sha256"] != digest(
            row["receipt"]
        ):
            raise ValueError("INPS native receipt changed")
    return {
        "state": state,
        "recovery_required": any(
            row["status"] == "pending" for row in state["operations"]
        ),
    }


def snapshot(binding: dict, loaded: dict, root: Path, api: Any) -> dict:
    output = Path(loaded["output_dir"])
    before = tree_hash(output)
    implementation = {
        "public": engine(root, {"operation": "implementation"}, api),
        "native": {
            p.name: file_hash(p)
            for p in (
                Path(__file__),
                Path(__file__).with_name("native_inps_bridge.py"),
                Path(__file__).with_name("native_inps_rpc.cjs"),
            )
        },
    }
    payload = None
    if "review_payload.json" in before:
        payload = engine(
            root, {"operation": "read", "context": str(loaded["context_path"])}, api
        )
    if tree_hash(output) != before:
        raise ValueError("INPS outputs changed while opening; reopen the review")
    scope = {
        "owner": [
            os.environ["VERA_WORKSPACE_TENANT_ID"],
            os.environ["VERA_WORKSPACE_ACTOR_ID"],
        ],
        "binding": binding,
        "inputs": loaded["input_manifest"],
        "run": loaded["run"],
        "implementation": implementation,
        "outputs": before,
    }
    audit = audit_run(output, api)
    return {
        "output": output,
        "scope": scope,
        "revision": digest(scope),
        "payload": payload,
        "files": before,
        "state": audit["state"],
        "recovery_required": audit["recovery_required"],
    }


def writable(current: dict, loaded: dict) -> bool:
    return (
        loaded["run"]["status"] == "running"
        and "REVIEWER" in os.environ.get("VERA_WORKSPACE_ROLES", "").split(",")
        and not current["recovery_required"]
    )


def draft(current: dict, api: Any) -> tuple[Path, dict, str]:
    path = api.ui_state_directory(current["output"], create=False) / (
        "inps-draft-" + digest(current["scope"]["owner"]) + ".json"
    )
    saved = (
        api.read_json(path)
        if path.exists()
        else {
            "scope": current["scope"],
            "generation": 0,
            "fields": {"reviewer": "", "decisions": {}},
        }
    )
    return path, saved, digest(saved)


def fields(value: Any, items: list[dict]) -> dict:
    """Validate literal unfinished selections; never choose recommended actions."""
    if (
        not isinstance(value, dict)
        or set(value) != {"reviewer", "decisions"}
        or not isinstance(value["reviewer"], str)
        or len(value["reviewer"]) > 200
    ):
        raise ValueError("Invalid INPS reviewer draft")
    decisions = value["decisions"]
    index = {row["id"]: row for row in items}
    if not isinstance(decisions, dict) or len(decisions) > 2500:
        raise ValueError("Invalid INPS decision selection")
    for identity, record in decisions.items():
        if (
            identity not in index
            or not isinstance(record, dict)
            or set(record)
            != {"action", "reviewer_note", "edit_value", "requested_documents"}
        ):
            raise ValueError("INPS choice leaves the exact review population")
        if record["action"] not in ["", *index[identity]["allowed_actions"]]:
            raise ValueError("Unsupported INPS choice")
        if any(
            not isinstance(record[key], str) or len(record[key]) > 10000
            for key in record
        ):
            raise ValueError("Invalid literal INPS choice fields")
    if len(json.dumps(value).encode()) > 1_000_000:
        raise ValueError("INPS private choices exceed the complete-content limit")
    return value


def dispatch(
    tool: str, args: dict, binding: dict, loaded: dict, root: Path, api: Any
) -> dict:
    """Keep current evidence, private draft, explicit model selection and public writes distinct."""
    if (
        binding["workflow_id"] != "previdenza-inps"
        or root.name != binding["workflow_id"]
    ):
        raise PermissionError("INPS belongs to another workflow")
    action = tool.removeprefix("vera_workspace_inps_")
    current = snapshot(binding, loaded, root, api)
    path, saved, stamp = draft(current, api)
    stale = saved["scope"] != current["scope"]
    public = current["payload"]["payload"] if current["payload"] else None
    items = public["review_payload"]["items"] if public else []
    base = {
        "work_ref": binding["work_ref"],
        "revision": current["revision"],
        "source_ref": current["payload"]["review_sha256"] if public else "",
        "run_status": loaded["run"]["status"],
        "can_write": bool(public) and writable(current, loaded),
        "recovery_required": current["recovery_required"],
        "actual_model_reads_verified": False,
        "draft_revision": stamp,
        "draft_stale": stale,
        "draft": saved["fields"],
        "review_status": public["review_payload"]["status"] if public else None,
        "final_artifacts": public["final_artifacts"] if public else None,
        "missing_declared_outputs": (
            [
                row["path"]
                for row in public["final_artifacts"]["outputs"]
                if row["path"] not in current["files"]
            ]
            if public
            else []
        ),
        "ui_decisions": public["ui_decisions"] if public else None,
    }
    if action == "setup":
        offset = args.get("offset", 0)
        if type(offset) is not int or offset < 0:
            raise ValueError("Invalid INPS page offset")
        return bounded(
            {
                **base,
                "setup_status": (
                    "review_available" if public else "preparation_required"
                ),
                "total": len(items),
                "offset": offset,
                "has_more": offset + 30 < len(items),
                "rows": [
                    {
                        "item_id": row["id"],
                        "title": row["title"],
                        "item_type": row["item_type"],
                    }
                    for row in items[offset : offset + 30]
                ],
            }
        )
    if action in {"read", "context", "outputs"}:
        if args["revision"] != current["revision"]:
            raise ValueError("INPS evidence changed; reopen the exact review")
        if action == "outputs":
            names = {
                "studio_memo.md",
                "studio_memo.docx",
                "document_requests.md",
                "review_handoff.md",
                "blocked_case_note.md",
                "extracted_evidence.md",
                "revision_requirements.json",
                "applied_decisions.json",
                "ui_decisions.json",
                "final_artifacts.json",
                "validation_audit.json",
                "case_records_audit.json",
                "calculation_audit.json",
                "calculation_results.json",
                "calculation_results.csv",
                "timeline.csv",
                "evidence_matrix.csv",
            }
            rows = []
            for name in base["missing_declared_outputs"]:
                rows.append({"name": name, "status": "missing"})
            for name in sorted(names & current["files"].keys()):
                file = current["output"] / name
                row = {
                    "name": name,
                    "path": str(file),
                    "sha256": current["files"][name],
                    "byte_count": file.stat().st_size,
                }
                if file.suffix in {".md", ".json", ".csv"}:
                    if file.stat().st_size > 1_500_000:
                        raise ValueError(
                            "Complete INPS output exceeds native limit; use the original file"
                        )
                    row["content"] = file.read_text(encoding="utf-8")
                rows.append(row)
            return bounded({**base, "files": rows})
        selected = next((row for row in items if row["id"] == args["item_id"]), None)
        if (
            selected is None
            or args["source_ref"] != current["payload"]["review_sha256"]
        ):
            raise PermissionError("Choose an exact INPS item in this owned run")
        if action == "context":
            return bounded(
                {
                    "work_ref": binding["work_ref"],
                    "revision": current["revision"],
                    "item_id": selected["id"],
                    "source_ref": args["source_ref"],
                    "evidence": selected,
                    "review_status": base["review_status"],
                    "actual_model_reads_verified": False,
                    "untrusted_evidence": True,
                    "professional_approval": False,
                },
                64000,
            )
        return bounded(
            {
                **base,
                "item_id": selected["id"],
                "source_ref": args["source_ref"],
                "item": selected,
            }
        )
    if action not in {"draft_save", "draft_clear", "commit"}:
        raise ValueError("Unknown INPS native action")
    with api.write_lock(current["output"]):
        loaded = api.load_binding(binding)
        current = snapshot(binding, loaded, root, api)
        if not current["payload"] or not writable(current, loaded):
            raise PermissionError(
                "INPS writes require a running owned reviewer without uncertain writes"
            )
        path, saved, stamp = draft(current, api)
        if action == "commit":
            key = args["idempotency_key"]
            if not re.fullmatch(r"[A-Za-z0-9_.-]{1,200}", key):
                raise ValueError("Invalid INPS operation key")
            request = {
                "owner": current["scope"]["owner"],
                "binding": binding,
                "action": action,
                "args": args,
            }
            fingerprint = digest(request)
            prior = next(
                (row for row in current["state"]["operations"] if row["key"] == key),
                None,
            )
            if prior:
                if prior["fingerprint"] != fingerprint:
                    raise ValueError("Changed INPS retry")
                return prior["receipt"]["result"]
        if (
            args["revision"] != current["revision"]
            or args["expected_draft_revision"] != stamp
        ):
            raise ValueError("INPS source or private draft generation changed")
        if action == "draft_clear":
            if args.get("confirmed") is not True:
                raise ValueError("Explicit discard required")
            value = {"reviewer": "", "decisions": {}}
        else:
            if saved["scope"] != current["scope"]:
                raise ValueError(
                    "Private INPS choices belong to changed evidence; inspect and discard explicitly"
                )
            value = fields(
                args["fields"], current["payload"]["payload"]["review_payload"]["items"]
            )
        if action in {"draft_save", "draft_clear"}:
            updated = {
                "scope": current["scope"],
                "generation": saved["generation"] + 1,
                "fields": value,
            }
            api.atomic_json(path, updated)
            return {
                "work_ref": binding["work_ref"],
                "revision": current["revision"],
                "draft_revision": digest(updated),
                "saved": True,
                "draft": value,
            }
        if (
            args.get("confirmed") is not True
            or value != saved["fields"]
            or not value["reviewer"].strip()
        ):
            raise ValueError("Save and explicitly confirm actual named INPS choices")
        decisions = [
            {
                "item_id": identity,
                "action": row["action"],
                "reviewer_note": row["reviewer_note"],
                "edit_value": row["edit_value"],
                "requested_documents": [
                    line
                    for line in row["requested_documents"].splitlines()
                    if line.strip()
                ],
            }
            for identity, row in value["decisions"].items()
            if row["action"]
        ]
        if not decisions:
            raise ValueError("Choose at least one actual INPS review action")
        ledger = api.ui_state_directory(current["output"]) / "inps-operations.json"
        entry = {
            "key": key,
            "request": request,
            "fingerprint": fingerprint,
            "status": "pending",
        }
        current["state"]["operations"].append(entry)
        api.atomic_json(ledger, current["state"])
        applied = engine(
            root,
            {
                "operation": "apply",
                "context": str(loaded["context_path"]),
                "decisions": {
                    "decisions": decisions,
                    "reviewer": value["reviewer"],
                    "decision_source": "vera_native_human_review",
                },
            },
            api,
        )
        if applied["payload"].get("persisted") is not True:
            raise ValueError(
                "INPS public application did not persist; recovery required"
            )
        refreshed = api.load_binding(binding)
        receipt = {
            "before_files": current["files"],
            "after_files": tree_hash(current["output"]),
            "result": {
                "work_ref": binding["work_ref"],
                "saved": True,
                "status": applied["payload"]["application_status"],
                "public_application": applied["payload"],
                "actual_model_reads_verified": False,
            },
        }
        if (
            refreshed["run"] != loaded["run"]
            or refreshed["input_manifest"] != loaded["input_manifest"]
        ):
            raise ValueError(
                "Owned INPS run changed after public write; recovery required"
            )
        entry.update(status="complete", receipt=receipt, receipt_sha256=digest(receipt))
        api.atomic_json(ledger, current["state"])
        return bounded(receipt["result"])
