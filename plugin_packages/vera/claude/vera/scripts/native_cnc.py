"""Optional exact CNC case/revision UI over the maintained public ledger.

Hashes, IDs, draft CAS and explicit grants enforce auditable ownership. They
do not choose a legal phase, assess admissibility or authenticate a reviewer.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

from native_bank_preparation import file_hash, tree_hash

__all__ = ["audit_run", "dispatch"]

INTAKE = {"question", "role", "input_ids"}
REVIEW = {"decision", "reviewer_ref", "confirmation_ref", "reason", "reviewed_at"}


def mandate_ref(row: dict) -> str:
    """Verify exact granted fields mechanically, independent of mutable status."""
    content = [row[k] for k in ("scope", "fields", "base_case", "request_key")]
    return (
        "cnc-mandate-"
        + hashlib.sha256(
            json.dumps(content, sort_keys=True, ensure_ascii=False).encode()
        ).hexdigest()
    )


def engine(root: Path, value: dict) -> dict:
    """Call only the fixed isolated existing CNC validation and persistence bridge."""
    result = subprocess.run(
        [
            sys.executable,
            "-I",
            "-B",
            str(Path(__file__).with_name("native_cnc_bridge.py")),
            str(root),
        ],
        input=json.dumps(value),
        text=True,
        capture_output=True,
        timeout=90,
        check=False,
    )
    if result.returncode:
        raise ValueError(
            result.stderr.strip().splitlines()[-1] or "CNC service refused"
        )
    return json.loads(result.stdout)


def limited(value: dict, maximum: int = 2_000_000) -> dict:
    """Refuse an oversized complete page; never replace a draft with a summary."""
    if len(json.dumps(value, ensure_ascii=False).encode()) > maximum:
        raise ValueError(
            "Complete CNC content exceeds native limit; use the specialist file route"
        )
    return value


def audit_run(output: Path, api: Any) -> dict:
    """Preserve interrupted side effects and close exact staged/public file populations."""
    private = api.ui_state_directory(output, create=False)
    state_path = private / "cnc-state.json"
    state = (
        api.read_json(state_path)
        if state_path.exists()
        else {"grants": [], "proposals": []}
    )
    refs = set()
    for row in state["proposals"]:
        ref = row["case_ref"]
        if (
            not re.fullmatch(r"cnc-proposal-[a-f0-9]{64}", ref)
            or ref in refs
            or tree_hash(private / ref) != row["artifacts"]
        ):
            raise ValueError("Complete CNC proposal changed")
        refs.add(ref)
        if {p.name for p in (private / ref).iterdir()} != {
            "request.json",
            "preview.json",
        }:
            raise ValueError("Unexpected CNC proposal member")
    requests = [api.read_json(p) for p in private.glob("cnc-request-*.json")]
    for request in requests:
        if "result" not in request:
            continue
        for name, sha in request["outputs"].items():
            if Path(name).name != name or file_hash(output / name) != sha:
                raise ValueError("Conserved ordinary CNC artifact changed")
    grants = set()
    for row in state["grants"]:
        if (
            row["grant_ref"] != mandate_ref(row)
            or row["grant_ref"] in grants
            or row["status"] not in {"open", "published", "cancelled"}
        ):
            raise ValueError("CNC source mandate identity changed")
        grants.add(row["grant_ref"])
    if any(row["grant_ref"] not in grants for row in state["proposals"]):
        raise ValueError("CNC proposal lost its explicit mandate")
    return {
        "state": state,
        "private": private,
        "pending": any(row["status"] == "open" for row in state["grants"]),
        "recovery_required": any("result" not in row for row in requests)
        or any(p.name not in refs for p in private.glob("cnc-proposal-*")),
    }


def snapshot(binding: dict, loaded: dict, root: Path, api: Any) -> dict:
    if (
        binding["workflow_id"] != "composizione-negoziata"
        or root.name != binding["workflow_id"]
    ):
        raise PermissionError("CNC belongs to another workflow")
    output = Path(loaded["output_dir"])
    history = engine(
        root, {"operation": "history", "context": str(loaded["context_path"])}
    )
    audit = audit_run(output, api)
    owner = [
        os.environ["VERA_WORKSPACE_ACTOR_ID"],
        os.environ["VERA_WORKSPACE_TENANT_ID"],
        *[binding[k] for k in ("client_id", "engagement_id", "run_id")],
    ]
    scope = {
        "owner": owner,
        "inputs": loaded["input_manifest"],
        "implementation": engine(root, {"operation": "implementation"}),
        "native": {
            p.name: file_hash(p)
            for p in (Path(__file__), Path(__file__).with_name("native_cnc_bridge.py"))
        },
    }
    return {
        **audit,
        "output": output,
        "scope": scope,
        "history": history,
        "revision": api.digest([scope, loaded["run"], history, audit["state"]]),
        "recovery_required": audit["recovery_required"] or history["recovery_required"],
    }


def writable(current: dict, loaded: dict) -> bool:
    return (
        loaded["run"]["status"] == "running"
        and not current["recovery_required"]
        and "REVIEWER" in os.environ.get("VERA_WORKSPACE_ROLES", "").split(",")
    )


def selected_source(identity: str, loaded: dict) -> tuple[Path, dict]:
    rows = [
        r for r in loaded["input_manifest"]["inputs"] if r["binding_id"] == identity
    ]
    if len(rows) != 1:
        raise PermissionError("Choose an exact registered CNC source")
    row = rows[0]
    path = Path(loaded["run_root"]) / row["execution_relative_path"]
    if file_hash(path) != row["sha256"]:
        raise ValueError("CNC original source changed")
    return path, row


def fields(value: Any, current: dict, loaded: dict, *, final: bool = False) -> dict:
    if (
        not isinstance(value, dict)
        or set(value) != INTAKE
        or not isinstance(value["question"], str)
        or len(value["question"]) > 4000
        or value["role"] not in {"", "advisor", "esperto"}
    ):
        raise ValueError("Choose a literal CNC question and professional role")
    ids = value["input_ids"]
    if (
        not isinstance(ids, list)
        or len(ids) > 1000
        or any(not isinstance(i, str) for i in ids)
        or len(set(ids)) != len(ids)
    ):
        raise ValueError("CNC source selection must contain unique registered IDs")
    for identity in ids:
        selected_source(identity, loaded)
    if current["history"]["role"] is not None and value["role"] not in {
        "",
        current["history"]["role"],
    }:
        raise PermissionError("A CNC role change requires a separate engagement")
    if final and (not value["question"].strip() or value["role"] == ""):
        raise ValueError("Confirm the CNC question and fixed professional role")
    return value


def draft(
    current: dict, api: Any, identity: str, empty: dict
) -> tuple[Path, dict, str]:
    path = current["private"] / (
        "cnc-draft-" + api.digest([current["scope"]["owner"], identity]) + ".json"
    )
    saved = (
        api.read_json(path)
        if path.exists()
        else {"scope": current["scope"], "generation": 0, "fields": empty}
    )
    if saved["scope"] != current["scope"]:
        raise PermissionError("CNC draft belongs to changed sources or implementation")
    return path, saved, api.digest(saved)


def grant_view(
    current: dict, args: dict, api: Any, *, allow_stale: bool = False
) -> dict:
    row = next(
        (r for r in current["state"]["grants"] if r["grant_ref"] == args["grant_ref"]),
        None,
    )
    if row is None or row["scope"] != current["scope"]:
        raise PermissionError("CNC source mandate belongs to another scope")
    history = current["history"]["rows"]
    latest = history[-1]["record"]["content_sha256"] if history else None
    if row["status"] == "open" and row["base_case"] != latest and not allow_stale:
        raise ValueError(
            "CNC case changed after this source mandate; reconcile the new revision"
        )
    return row


def review_fields(value: Any, *, final: bool = False) -> dict:
    if (
        not isinstance(value, dict)
        or set(value) != REVIEW
        or any(not isinstance(v, str) or len(v) > 4000 for v in value.values())
        or value["decision"] not in {"", "accepted", "changes_requested", "rejected"}
    ):
        raise ValueError("Invalid declared CNC review fields")
    if final:
        if any(not v.strip() for v in value.values()):
            raise ValueError("Complete the actual version-specific review attribution")
        parsed = datetime.fromisoformat(value["reviewed_at"])
        if parsed.utcoffset() is None:
            raise ValueError("CNC declared review time needs its timezone")
    return value


def model_request(proposal: Any, grant: dict, current: dict, key: str) -> dict:
    required = {
        "role",
        "stage",
        "change_reason",
        "next_action",
        "upsert_nodes",
        "reviews",
    }
    if (
        not isinstance(proposal, dict)
        or set(proposal) - {"closure"} != required
        or proposal["reviews"] != []
        or proposal["role"] != grant["fields"]["role"]
    ):
        raise ValueError(
            "Supply the complete ordinary CNC update with empty model review attribution"
        )
    if any(
        c["binding_id"] not in grant["fields"]["input_ids"]
        for n in proposal["upsert_nodes"]
        for c in n["citations"]
    ):
        raise PermissionError("New CNC citations require an expressly granted source")
    return {
        **proposal,
        "expected_revision": len(current["history"]["rows"]),
        "idempotency_key": key,
    }


def dispatch(
    tool: str, args: dict, binding: dict, loaded: dict, root: Path, api: Any
) -> dict:
    """Conserve full model work and explicit local confirmations without signing."""
    action = tool.removeprefix("vera_workspace_cnc_")
    current = snapshot(binding, loaded, root, api)
    if action in {"author_request", "stage", "publish", "cancel", "review_commit"}:
        key = args.get("idempotency_key")
        if isinstance(key, str) and re.fullmatch(r"[A-Za-z0-9_-]{1,120}", key):
            cached = current["private"] / (
                "cnc-request-" + api.digest([current["scope"]["owner"], key]) + ".json"
            )
            if cached.exists():
                prior = api.read_json(cached)
                if (
                    current["recovery_required"]
                    or prior["fingerprint"]
                    != api.digest([tool, args, current["scope"]])
                    or "result" not in prior
                ):
                    raise ValueError("Changed or uncertain CNC retry")
                return prior["result"]
    base = {
        "work_ref": binding["work_ref"],
        "revision": current["revision"],
        "can_write": writable(current, loaded),
        "recovery_required": current["recovery_required"],
    }
    history = current["history"]["rows"]
    latest = history[-1]["record"] if history else None
    if action == "setup":
        offset = args.get("offset", 0)
        if type(offset) is not int or offset < 0:
            raise ValueError("Invalid CNC page offset")
        nodes = list(latest["payload"]["nodes"].values()) if latest else []
        return limited(
            {
                **base,
                "role": current["history"]["role"],
                "case_revision": latest["revision"] if latest else 0,
                "source_ref": latest["content_sha256"] if latest else "",
                "stage": latest["payload"]["stage"] if latest else "",
                "next_action": latest["payload"]["next_action"] if latest else None,
                "rows": [
                    {
                        "id": n["id"],
                        "title": n["title"],
                        "kind": n["kind"],
                        "classification": n["classification"],
                        "stale": n["id"] in latest["payload"]["stale_nodes"],
                    }
                    for n in nodes[offset : offset + 30]
                ],
                "offset": offset,
                "total": len(nodes),
                "has_more": offset + 30 < len(nodes),
                "grants": [
                    {
                        "grant_ref": r["grant_ref"],
                        "status": r["status"],
                        "question": r["fields"]["question"],
                    }
                    for r in current["state"]["grants"]
                ],
            }
        )
    if action in {"read", "context", "review_draft_save", "review_commit"}:
        if latest is None or args["source_ref"] != latest["content_sha256"]:
            raise ValueError("Choose the exact current CNC case version")
        node = latest["payload"]["nodes"].get(args["item_id"])
        if node is None:
            raise ValueError("Choose an exact current CNC node")
        identity = latest["content_sha256"] + ":" + node["id"]
        path, saved, stamp = draft(current, api, identity, {k: "" for k in REVIEW})
        stale = node["id"] in latest["payload"]["stale_nodes"]
        if action in {"read", "context"}:
            value = {
                **base,
                "source_ref": latest["content_sha256"],
                "data": {"selection": {"source_ref": latest["content_sha256"]}},
                "selection": {"id": node["id"]},
                "node": node,
                "role": latest["payload"]["role"],
                "case_revision": latest["revision"],
                "stale": stale,
                "reviews": [
                    r
                    for r in latest["payload"]["reviews"]
                    if r["node_id"] == node["id"]
                ],
                "professional_approval": False,
                "actual_model_reads_verified": False,
            }
            if action == "context":
                if args["revision"] != current["revision"]:
                    raise ValueError("Reopen the exact CNC node")
                return limited(value, 24000)
            return limited(
                {
                    **value,
                    "draft": saved["fields"],
                    "draft_revision": stamp,
                    "can_write": base["can_write"] and not stale,
                }
            )
    if action in {"author_setup", "author_draft_save", "author_request"}:
        path, saved, stamp = draft(
            current, api, "intake", {"question": "", "role": "", "input_ids": []}
        )
        fields(saved["fields"], current, loaded)
        if action == "author_setup":
            return limited(
                {
                    **base,
                    "fields": saved["fields"],
                    "draft_revision": stamp,
                    "fixed_role": current["history"]["role"],
                    "sources": [
                        {
                            "input_id": r["binding_id"],
                            "name": Path(r["source_relative_path"]).name,
                        }
                        for r in loaded["input_manifest"]["inputs"]
                    ],
                    "grants": current["state"]["grants"],
                }
            )
    if action in {"author_read", "author_context", "stage", "publish", "cancel"}:
        grant = grant_view(
            current, args, api, allow_stale=action in {"author_read", "cancel"}
        )
        proposals = [
            r
            for r in current["state"]["proposals"]
            if r["grant_ref"] == grant["grant_ref"]
        ]
        selected = next(
            (r for r in proposals if r["case_ref"] == args.get("case_ref")), None
        )
        if args.get("case_ref") and selected is None:
            raise ValueError("Choose an exact complete CNC proposal")
        if action in {"author_read", "author_context"}:
            value = {
                **base,
                "grant_ref": grant["grant_ref"],
                "source_ref": grant["grant_ref"],
                "data": {"selection": {"source_ref": grant["grant_ref"]}},
                "selection": {"id": selected["case_ref"]} if selected else None,
                "status": grant["status"],
                "case_changed": grant["base_case"]
                != (latest["content_sha256"] if latest else None),
                "question": grant["fields"]["question"],
                "role": grant["fields"]["role"],
                "proposals": [
                    {"case_ref": r["case_ref"], "conserved": "conservation" in r}
                    for r in proposals
                ],
                "actual_model_reads_verified": False,
                "professional_approval": False,
            }
            if action == "author_context":
                if (
                    grant["status"] == "cancelled"
                    or args["revision"] != current["revision"]
                    or current["recovery_required"]
                ):
                    raise PermissionError(
                        "CNC source mandate is cancelled, stale or uncertain"
                    )
                value["sources"] = [
                    {
                        "input_id": i,
                        "authorized_path": str(selected_source(i, loaded)[0]),
                        "sha256": selected_source(i, loaded)[1]["sha256"],
                    }
                    for i in grant["fields"]["input_ids"]
                ]
                prior_case = next(
                    (
                        r
                        for r in history
                        if r["record"]["content_sha256"] == grant["base_case"]
                    ),
                    None,
                )
                value["current_case"] = (
                    {
                        "authorized_path": prior_case["snapshot_path"],
                        "sha256": prior_case["snapshot_sha256"],
                    }
                    if prior_case
                    else None
                )
                value["skill_path"] = str(
                    root / "skills/composizione-negoziata/SKILL.md"
                )
                value["selected_proposal"] = (
                    {
                        "authorized_path": str(
                            current["private"] / selected["case_ref"] / "request.json"
                        ),
                        "sha256": selected["artifacts"]["request.json"],
                    }
                    if selected
                    else None
                )
                return limited(value, 64000)
            if selected:
                value.update(
                    case_ref=selected["case_ref"],
                    proposal=api.read_json(
                        current["private"] / selected["case_ref"] / "request.json"
                    ),
                    preview=api.read_json(
                        current["private"] / selected["case_ref"] / "preview.json"
                    ),
                    conservation=selected.get("conservation"),
                )
            return limited(value)
    with api.write_lock(current["output"]):
        loaded = api.load_binding(binding)
        current = snapshot(binding, loaded, root, api)
        if not writable(current, loaded):
            raise PermissionError(
                "CNC writes require an owned running reviewer without uncertain writes"
            )
        key = args.get("idempotency_key")
        intent = None
        if action in {"author_request", "stage", "publish", "cancel", "review_commit"}:
            if not isinstance(key, str) or not re.fullmatch(
                r"[A-Za-z0-9_-]{1,120}", key
            ):
                raise ValueError("Invalid CNC request identity")
            intent = current["private"] / (
                "cnc-request-" + api.digest([current["scope"]["owner"], key]) + ".json"
            )
            fingerprint = api.digest([tool, args, current["scope"]])
            if intent.exists():
                prior = api.read_json(intent)
                if prior["fingerprint"] != fingerprint or "result" not in prior:
                    raise ValueError("Changed or uncertain CNC retry")
                return prior["result"]
        if args["revision"] != current["revision"]:
            raise ValueError("Reopen the current CNC case and reconcile changes")
        # Draft files do not alter the case revision. Re-read their generation
        # under the native lock so another writer cannot be overwritten.
        if action in {
            "author_draft_save",
            "author_request",
            "review_draft_save",
            "review_commit",
        }:
            draft_identity = identity if action.startswith("review_") else "intake"
            empty = (
                {k: "" for k in REVIEW}
                if action.startswith("review_")
                else {"question": "", "role": "", "input_ids": []}
            )
            path, saved, stamp = draft(current, api, draft_identity, empty)
        state, outputs = current["state"], {}
        if action in {"author_draft_save", "author_request", "review_draft_save"}:
            if args["expected_draft_revision"] != stamp:
                raise ValueError("CNC private draft generation changed")
            value = (
                fields(
                    args["fields"], current, loaded, final=action == "author_request"
                )
                if action != "review_draft_save"
                else review_fields(args["fields"])
            )
            if action.endswith("draft_save"):
                if action == "review_draft_save" and stale:
                    raise ValueError(
                        "Stale CNC node requires reanalysis before a decision"
                    )
                api.atomic_json(
                    path,
                    {
                        "scope": current["scope"],
                        "generation": saved["generation"] + 1,
                        "fields": value,
                    },
                )
                return {"saved": True, "professional_approval": False}
            if args.get("confirmed") is not True or value != saved["fields"]:
                raise ValueError(
                    "Renew confirmation of the exact saved CNC question and sources"
                )
            grant = {
                "scope": current["scope"],
                "fields": value,
                "base_case": (
                    current["history"]["rows"][-1]["record"]["content_sha256"]
                    if current["history"]["rows"]
                    else None
                ),
                "status": "open",
                "request_key": key,
            }
            grant["grant_ref"] = mandate_ref(grant)
            state["grants"].append(grant)
            result = {
                "saved": True,
                "grant_ref": grant["grant_ref"],
                "model_reads": False,
            }
        elif action == "stage":
            grant = grant_view(current, args, api)
            if grant["status"] != "open":
                raise ValueError("CNC mandate is closed")
            proposal = limited(args["proposal"], 96000)
            update = model_request(
                proposal,
                grant,
                current,
                "cnc-native-" + api.digest([current["scope"]["owner"], key]),
            )
            preview = engine(
                root,
                {
                    "operation": "preview",
                    "context": str(loaded["context_path"]),
                    "update": update,
                },
            )
            ref = "cnc-proposal-" + api.digest([grant["grant_ref"], update])
            folder = current["private"] / ref
            api.atomic_json(intent, {"fingerprint": fingerprint})
            folder.mkdir(exist_ok=False)
            api.atomic_json(folder / "request.json", update)
            api.atomic_json(folder / "preview.json", preview)
            state["proposals"].append(
                {
                    "case_ref": ref,
                    "grant_ref": grant["grant_ref"],
                    "artifacts": tree_hash(folder),
                }
            )
            result = {"saved": True, "case_ref": ref, "professional_approval": False}
        elif action == "cancel":
            grant = grant_view(current, args, api, allow_stale=True)
            if (
                grant["status"] != "open"
                or args.get("confirmed") is not True
                or args["source_ref"] != grant["grant_ref"]
            ):
                raise ValueError("Confirm cancellation of this exact open CNC mandate")
            grant["status"] = "cancelled"
            result = {"saved": True, "status": "cancelled"}
        elif action in {"publish", "review_commit"}:
            if args.get("confirmed") is not True:
                raise ValueError("Renew the exact displayed CNC version confirmation")
            if action == "publish":
                grant = grant_view(current, args, api)
                row = next(
                    (
                        r
                        for r in state["proposals"]
                        if r["grant_ref"] == grant["grant_ref"]
                        and r["case_ref"] == args["case_ref"]
                    ),
                    None,
                )
                if (
                    row is None
                    or grant["status"] != "open"
                    or args["item_id"] != row["case_ref"]
                    or args["source_ref"] != grant["grant_ref"]
                ):
                    raise ValueError("Select the exact complete CNC proposal")
                update = api.read_json(
                    current["private"] / row["case_ref"] / "request.json"
                )
                expected = api.read_json(
                    current["private"] / row["case_ref"] / "preview.json"
                )["payload"]
            else:
                value = review_fields(args["fields"], final=True)
                if (
                    stale
                    or args["expected_draft_revision"] != stamp
                    or value != saved["fields"]
                ):
                    raise ValueError("Confirm the exact saved current CNC node review")
                update = {
                    "expected_revision": latest["revision"],
                    "idempotency_key": "cnc-native-review-"
                    + api.digest([current["scope"]["owner"], key]),
                    "role": latest["payload"]["role"],
                    "stage": latest["payload"]["stage"],
                    "change_reason": value["reason"],
                    "next_action": latest["payload"]["next_action"],
                    "upsert_nodes": [],
                    "reviews": [
                        {
                            "node_id": node["id"],
                            "node_version": node["version"],
                            **{
                                k: value[k]
                                for k in (
                                    "decision",
                                    "reviewer_ref",
                                    "confirmation_ref",
                                    "reason",
                                )
                            },
                        }
                    ],
                }
                expected = engine(
                    root,
                    {
                        "operation": "preview",
                        "context": str(loaded["context_path"]),
                        "update": update,
                    },
                )["payload"]
            api.atomic_json(intent, {"fingerprint": fingerprint})
            request_path = current["output"] / (
                "cnc-native-request-"
                + api.digest([current["scope"]["owner"], key])
                + ".json"
            )
            produced = engine(
                root,
                {
                    "operation": "apply",
                    "context": str(loaded["context_path"]),
                    "update": update,
                    "request_path": str(request_path),
                },
            )
            record = produced["record"]
            if record["payload"] != expected:
                raise ValueError(
                    "CNC saved snapshot differs from complete preview; recovery required"
                )
            receipt = current["output"] / (
                "cnc-native-receipt-"
                + api.digest([current["scope"]["owner"], key])
                + ".json"
            )
            api.atomic_json(
                receipt,
                {
                    "record_sha256": record["content_sha256"],
                    "request_sha256": record["request_sha256"],
                    "declared_fields": value if action == "review_commit" else None,
                    "authority": "record_only_identity_not_verified",
                    "professional_approval": False,
                    "external_action_authorized": False,
                    "actual_model_reads_verified": False,
                },
            )
            files = [
                request_path,
                Path(produced["memo_path"]),
                current["output"] / f"workflow-revision-{record['revision']:06d}.json",
                receipt,
            ]
            outputs = {p.name: file_hash(p) for p in files}
            result = {
                "saved": True,
                "source_ref": record["content_sha256"],
                "case_revision": record["revision"],
                "files": [
                    {"name": p.name, "path": str(p), "sha256": outputs[p.name]}
                    for p in files
                ],
                "authority": "record_only_identity_not_verified",
                "professional_approval": False,
                "external_action_authorized": False,
                "run_completed": False,
            }
            if action == "publish":
                row["conservation"] = result
                grant["status"] = "published"
        else:
            raise ValueError("Unsupported CNC action")
        if intent is not None and not intent.exists():
            api.atomic_json(intent, {"fingerprint": fingerprint})
        api.atomic_json(current["private"] / "cnc-state.json", state)
        if intent is not None:
            api.atomic_json(
                intent,
                {"fingerprint": fingerprint, "outputs": outputs, "result": result},
            )
        return limited(result)
