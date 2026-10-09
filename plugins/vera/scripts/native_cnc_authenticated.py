"""Optional human-selected receipt preparation/import; exact security bindings only."""

from __future__ import annotations

import hashlib
import json
import re
import subprocess
import sys
from pathlib import Path
from typing import Any

from native_bank_preparation import file_hash
from native_cnc import draft, limited, snapshot, writable

__all__ = ["dispatch"]

PAGE = "https://mparanza.com/vera/cnc-review"
ENDPOINT = "https://mparanza.com/api/vera/cnc-reviews/verify"
UUID = r"[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}"


def opaque(value: Any) -> str:
    """Match the unchanged public hosted-review client's canonical JSON digest."""
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, ensure_ascii=False, allow_nan=False).encode()
    ).hexdigest()


def engine(root: Path, args: dict) -> dict:
    """Run the fixed public preparation/verifier/writer in an isolated process."""
    result = subprocess.run(
        [
            sys.executable,
            "-I",
            "-B",
            str(Path(__file__).with_name("native_cnc_authenticated_bridge.py")),
            str(root),
        ],
        input=json.dumps(args),
        text=True,
        capture_output=True,
        timeout=90,
        check=False,
    )
    if result.returncode:
        raise ValueError(
            result.stderr.strip().splitlines()[-1] or "CNC review service refused"
        )
    return json.loads(result.stdout)


def fields(value: Any, *, final: bool = False) -> dict:
    """Preserve private literal receipt/reason drafts, without verifying or sending."""
    if (
        not isinstance(value, dict)
        or set(value) != {"receipt", "reason"}
        or not isinstance(value["receipt"], (dict, type(None)))
        or not isinstance(value["reason"], str)
        or len(value["reason"]) > 10000
    ):
        raise ValueError("Invalid private CNC receipt draft")
    limited(value, 32000)
    if final and (not value["reason"].strip() or not value["receipt"]):
        raise ValueError("Choose the actual receipt and state its review reason")
    return value


def targets(
    current: dict, binding: dict, node: dict, role: str, api: Any
) -> list[dict]:
    """Read only actual public review files in this run; never infer a review."""
    expected_case = opaque(
        {
            "client": binding["client_id"],
            "engagement": binding["engagement_id"],
            "workflow": "composizione-negoziata",
        }
    )
    rows = []
    for path in sorted(current["output"].glob("cnc-review-*.json")):
        if re.fullmatch("cnc-review-" + UUID + r"\.json", path.name) is None:
            continue
        sha = file_hash(path)
        value = api.read_json(path)
        request = value["request"]
        original = value["node"]
        if (
            set(value) != {"node", "request"}
            or set(request)
            != {"request_id", "case_ref", "role", "node_ref", "node_version"}
            or request["request_id"] != path.stem.removeprefix("cnc-review-")
            or request["case_ref"] != expected_case
            or request["role"] != role
            or request["node_ref"] != opaque(original["id"])
            or request["node_version"] != original["version"]
            or original["version"]
            != opaque({k: v for k, v in original.items() if k != "version"})
        ):
            raise ValueError(
                "Ordinary CNC review target changed or belongs to another scope"
            )
        if original["id"] == node["id"]:
            rows.append(
                {
                    "target_ref": sha,
                    "name": path.name,
                    "path": str(path),
                    "sha256": sha,
                    "current": original == node,
                    "target": value,
                }
            )
    return rows


def verify_shape(receipt: dict, target: dict) -> None:
    """Reject local scope conflicts before contacting the fixed verification service."""
    required = {
        "schema_version",
        "request_id",
        "case_ref",
        "role",
        "node_ref",
        "node_version",
        "decision",
        "actor",
        "reviewed_at",
        "authority",
    }
    if (
        set(receipt) != required
        or any(receipt[k] != v for k, v in target["request"].items())
        or receipt["schema_version"] != "vera.cnc_authenticated_review.v1"
        or receipt["authority"] != "mparanza_authenticated_account"
        or receipt["decision"] not in {"accepted", "changes_requested", "rejected"}
        or not isinstance(receipt["actor"], str)
        or not receipt["actor"].strip()
        or not isinstance(receipt["reviewed_at"], str)
    ):
        raise ValueError("Receipt does not identify this prepared exact CNC version")


def dispatch(
    tool: str, args: dict, binding: dict, loaded: dict, root: Path, api: Any
) -> dict:
    """Separate local preparation, human confirmation and chosen hosted verification."""
    action = tool.removeprefix("vera_workspace_cnc_authenticated_")
    current = snapshot(binding, loaded, root, api)
    native = {
        p.name: file_hash(p)
        for p in (
            Path(__file__),
            Path(__file__).with_name("native_cnc_authenticated_bridge.py"),
        )
    }
    current["scope"] = {**current["scope"], "authenticated_native": native}
    scope = [current["scope"], native]
    intent = None
    fingerprint = None
    if action in {"prepare", "import"}:
        key = args["idempotency_key"]
        if (
            not isinstance(key, str)
            or re.fullmatch(r"[A-Za-z0-9_-]{1,120}", key) is None
        ):
            raise ValueError("Choose a fresh CNC review request identity")
        fingerprint = api.digest([tool, args, scope])
        intent = current["private"] / (
            "cnc-request-" + api.digest([scope, key]) + ".json"
        )
        if intent.exists():
            prior = api.read_json(intent)
            if (
                current["recovery_required"]
                or prior["fingerprint"] != fingerprint
                or "result" not in prior
            ):
                raise ValueError("Changed or uncertain authenticated CNC retry")
            return prior["result"]
    history = current["history"]["rows"]
    if not history or history[-1]["record"]["content_sha256"] != args["source_ref"]:
        raise ValueError("Select the exact current CNC case")
    record = history[-1]["record"]
    state = record["payload"]
    node = state["nodes"].get(args["item_id"])
    if node is None:
        raise PermissionError("Choose an exact current CNC node")
    rows = targets(current, binding, node, state["role"], api)
    selected = next(
        (r for r in rows if r["target_ref"] == args.get("target_ref")), None
    )
    if action in {"read", "draft_save", "import"} and selected is None:
        raise PermissionError("Choose a prepared review file in this exact run")
    path, saved, stamp = draft(
        current,
        api,
        "authenticated-" + (args.get("target_ref") or "unselected"),
        {"receipt": None, "reason": ""},
    )
    fields(saved["fields"])
    revision = api.digest([current["revision"], native, rows, stamp])
    base = {
        "work_ref": binding["work_ref"],
        "revision": revision,
        "source_ref": args["source_ref"],
        "data": {"selection": {"source_ref": args["source_ref"]}},
        "selection": {"id": node["id"]},
        "node": node,
        "role": state["role"],
        "can_write": writable(current, loaded)
        and node["id"] not in state["stale_nodes"],
        "review_page": PAGE,
        "verification_endpoint": ENDPOINT,
        "professional_approval": False,
        "actual_model_reads_verified": False,
        "recovery_required": current["recovery_required"],
    }
    if action == "setup":
        offset = args.get("offset", 0)
        if type(offset) is not int or offset < 0:
            raise ValueError("Invalid CNC target page")
        return limited(
            {
                **base,
                "total": len(rows),
                "offset": offset,
                "has_more": offset + 30 < len(rows),
                "rows": [
                    {k: v for k, v in r.items() if k != "target"}
                    for r in rows[offset : offset + 30]
                ],
            }
        )
    if action == "read":
        return limited(
            {
                **base,
                "can_write": base["can_write"] and selected["current"],
                "prepared": selected,
                "draft": saved["fields"],
                "draft_revision": stamp,
                "receipt_verified": False,
            }
        )
    if not base["can_write"] or args["revision"] != revision:
        raise PermissionError("Reopen an editable current CNC review selection")
    if action in {"draft_save", "import"}:
        value = fields(args["fields"], final=action == "import")
        if not selected["current"] or args["expected_draft_revision"] != stamp:
            raise ValueError("Prepared CNC version or private draft generation changed")
    if action == "import":
        if value != saved["fields"] or args["confirmed"] is not True:
            raise ValueError("Confirm the exact saved receipt and fixed service choice")
        verify_shape(value["receipt"], selected["target"])
    elif action == "prepare":
        if args["confirmed"] is not True:
            raise ValueError("Choose preparation of this exact local review file")
    elif action != "draft_save":
        raise ValueError("Unsupported authenticated CNC action")
    with api.write_lock(current["output"]):
        rebound = api.load_binding(binding)
        fresh = snapshot(binding, rebound, root, api)
        if fresh["revision"] != current["revision"] or any(
            file_hash(Path(__file__).with_name(name)) != sha
            for name, sha in native.items()
        ):
            raise ValueError("CNC source/implementation changed before review mutation")
        if targets(fresh, binding, node, state["role"], api) != rows:
            raise ValueError("Prepared CNC file changed before review mutation")
        fresh["scope"] = {**fresh["scope"], "authenticated_native": native}
        _, saved_now, stamp_now = draft(
            fresh,
            api,
            "authenticated-" + (args.get("target_ref") or "unselected"),
            {"receipt": None, "reason": ""},
        )
        if stamp_now != stamp:
            raise ValueError("Another writer changed the CNC receipt draft")
        if action == "draft_save":
            api.atomic_json(
                path,
                {
                    **saved_now,
                    "generation": saved_now["generation"] + 1,
                    "fields": value,
                },
            )
            return {
                "saved": True,
                "receipt_verified": False,
                "professional_approval": False,
            }
        api.atomic_json(intent, {"fingerprint": fingerprint})
        produced = engine(
            root,
            {
                "operation": action,
                "context": str(loaded["context_path"]),
                "source_ref": args["source_ref"],
                "item_id": node["id"],
                **(
                    {
                        "receipt": value["receipt"],
                        "reason": value["reason"],
                        "request_key": "cnc-native-auth-" + api.digest([scope, key]),
                    }
                    if action == "import"
                    else {}
                ),
            },
        )
        if produced.get("verification_pending"):
            result = {
                "saved": False,
                "verification_pending": True,
                "error": produced["error"],
                "receipt_verified": False,
                "professional_approval": False,
            }
            outputs = {}
        else:
            files = [Path(p) for p in produced["files"]]
            if any(p.parent != current["output"] for p in files):
                raise PermissionError("CNC review output escaped the managed run")
            outputs = {p.name: file_hash(p) for p in files}
            result = {
                "saved": True,
                "files": [
                    {"name": p.name, "path": str(p), "sha256": outputs[p.name]}
                    for p in files
                ],
                "receipt_verified": action == "import",
                "professional_approval": False,
                "external_action_authorized": False,
                "run_completed": False,
                **(
                    {
                        "authority": produced["record"]["payload"]["reviews"][-1][
                            "authority"
                        ],
                        "case_revision": produced["record"]["revision"],
                    }
                    if action == "import"
                    else {"target": produced["target"]}
                ),
            }
        api.atomic_json(
            intent, {"fingerprint": fingerprint, "outputs": outputs, "result": result}
        )
        return limited(result)
