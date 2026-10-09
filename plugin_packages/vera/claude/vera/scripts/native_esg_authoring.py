"""Explicit ESG source mandates, partial proposals and actual human decisions.

IDs, digests, CAS and locks are mechanically verifiable authorization controls.
Meaning, framework applicability and professional sufficiency stay with people.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from native_bank_preparation import file_hash, tree_hash
from native_esg import engine as read_engine
from native_esg import limited

__all__ = ["audit_run", "dispatch"]

COMMANDS = {"start_case", "bind_evidence", "register_source", "build_deliverables"}
INTAKE = {"question", "command", "input_ids", "previous_run_id"}
DECISION = {
    "id",
    "type",
    "decided_by",
    "decided_on",
    "outcome",
    "decision",
    "rationale",
    "dependency_refs",
}


def canonical(value: Any) -> str:
    """Match the public ESG request digest, not the shared UI digest format."""
    return hashlib.sha256(
        json.dumps(
            value,
            sort_keys=True,
            ensure_ascii=False,
            separators=(",", ":"),
            allow_nan=False,
        ).encode()
    ).hexdigest()


def producer(root: Path, value: dict) -> dict:
    """Call only the fixed isolated public-execute bridge."""
    result = subprocess.run(
        [
            sys.executable,
            "-I",
            "-B",
            str(Path(__file__).with_name("native_esg_author_bridge.py")),
            str(root),
        ],
        input=json.dumps(value),
        text=True,
        capture_output=True,
        check=False,
        timeout=90,
    )
    if result.returncode:
        raise ValueError(
            result.stderr.strip().splitlines()[-1] or "ESG producer refused"
        )
    return json.loads(result.stdout)


def grant_ref(row: dict) -> str:
    """Self-contained exact identity also works in the shared closure capability set."""
    return "esg-mandate-" + canonical(
        [
            row[k]
            for k in ("scope", "fields", "base_state", "previous_case", "request_key")
        ]
    )


def audit_run(output: Path, api: Any) -> dict:
    """Retain uncertain side effects and prevent abandoned mandates closing a run."""
    home = api.ui_state_directory(output, create=False)
    state = (
        api.read_json(home / "esg-authoring.json")
        if (home / "esg-authoring.json").exists()
        else {"grants": [], "proposals": []}
    )
    known = set()
    for row in state["grants"]:
        if (
            row["grant_ref"] != grant_ref(row)
            or row["grant_ref"] in known
            or row["status"] not in {"open", "conserved", "cancelled"}
        ):
            raise ValueError("ESG source mandate changed")
        known.add(row["grant_ref"])
    folders = set()
    for row in state["proposals"]:
        name = row["case_ref"]
        if (
            not re.fullmatch(r"esg-proposal-[a-f0-9]{64}", name)
            or name in folders
            or row["grant_ref"] not in known
        ):
            raise ValueError("ESG proposal identity changed")
        folders.add(name)
        if tree_hash(home / name) != row["artifacts"] or {
            p.name for p in (home / name).iterdir()
        } != {"request.json", "preview.json"}:
            raise ValueError("Whole ESG proposal changed")
    recovery = (output / ".esg-write.lock").exists()
    for path in home.glob("esg-intent-*.json"):
        intent = api.read_json(path)
        if "result" not in intent:
            recovery = True
            continue
        for name, digest in intent["outputs"].items():
            if Path(name).name != name or file_hash(output / name) != digest:
                raise ValueError("Conserved ESG ordinary artifact changed")
        if "public_key" in intent:
            state_path = output / "esg_state.json"
            public = api.read_json(state_path)
            entry = public["requests"].get(intent["public_key"])
            if (
                entry is None
                or entry["sha256"]
                != canonical(
                    {"command": intent["command"], "request": intent["public_request"]}
                )
                or entry["result"] != intent["result"]["reference"]
            ):
                raise ValueError(
                    "ESG native conservation lost its public request receipt"
                )
    recovery |= any(p.name not in folders for p in home.glob("esg-proposal-*"))
    return {
        "home": home,
        "state": state,
        "recovery_required": recovery,
        "pending": any(r["status"] == "open" for r in state["grants"]),
    }


def snapshot(binding: dict, loaded: dict, root: Path, api: Any) -> dict:
    if (
        binding["workflow_id"] != "esg-reporting-assurance"
        or root.name != binding["workflow_id"]
    ):
        raise PermissionError("ESG authoring belongs to another workflow")
    output = Path(loaded["output_dir"])
    path = output / "esg_state.json"
    if path.is_symlink():
        raise ValueError("Linked ESG state is unavailable")
    public = (
        read_engine(
            root, {"operation": "resume", "context": str(loaded["context_path"])}
        )
        if path.exists()
        else None
    )
    owner = [
        os.environ["VERA_WORKSPACE_ACTOR_ID"],
        os.environ["VERA_WORKSPACE_TENANT_ID"],
        *[binding[k] for k in ("client_id", "engagement_id", "run_id")],
    ]
    scope = {
        "owner": owner,
        "inputs": loaded["input_manifest"],
        "implementation": read_engine(root, {"operation": "implementation"}),
        "native": {
            p.name: file_hash(p)
            for p in (
                Path(__file__),
                Path(__file__).with_name("native_esg_author_bridge.py"),
                Path(__file__).with_name("native_esg.py"),
                Path(__file__).with_name("native_esg_bridge.py"),
            )
        },
    }
    audit = audit_run(output, api)
    return {
        **audit,
        "output": output,
        "scope": scope,
        "public": public,
        "base_state": public["summary"]["state_sha256"] if public else None,
        "revision": api.digest([scope, loaded["run"], public, audit["state"]]),
    }


def writable(current: dict, loaded: dict) -> bool:
    return (
        loaded["run"]["status"] == "running"
        and not current["recovery_required"]
        and "REVIEWER" in os.environ.get("VERA_WORKSPACE_ROLES", "").split(",")
    )


def draft(
    current: dict, identity: str, empty: dict, api: Any
) -> tuple[Path, dict, str]:
    path = current["home"] / (
        "esg-draft-private-"
        + api.digest([current["scope"]["owner"], identity])
        + ".json"
    )
    saved = (
        api.read_json(path)
        if path.exists()
        else {"scope": current["scope"], "generation": 0, "fields": empty}
    )
    if saved["scope"] != current["scope"]:
        raise ValueError(
            "ESG private draft belongs to changed sources or implementation"
        )
    return path, saved, api.digest(saved)


def sources(loaded: dict) -> list[dict]:
    return [
        {
            "input_id": r["binding_id"],
            "name": Path(r["source_relative_path"]).name,
            "sha256": r["sha256"],
            "source_relative_path": r["source_relative_path"],
        }
        for r in loaded["input_manifest"]["inputs"]
    ]


def previous_case(identifier: str, binding: dict, api: Any) -> dict | None:
    if not identifier:
        return None
    if identifier == binding["run_id"] or not re.fullmatch(
        r"run_[a-f0-9]{24}", identifier
    ):
        raise ValueError("Choose a different exact ESG predecessor in this engagement")
    prior = api.load_binding({**binding, "run_id": identifier})
    recovered = read_engine(
        api.module_root("esg-reporting-assurance"),
        {"operation": "resume", "context": str(prior["context_path"])},
    )
    path = Path(prior["output_dir"]) / "esg_state.json"
    return {
        "run_id": identifier,
        "context_path": str(prior["context_path"]),
        "authorized_path": str(path),
        "sha256": recovered["state_file_sha256"],
        "state_sha256": recovered["summary"]["state_sha256"],
        "case_id": recovered["summary"]["case_id"],
    }


def intake(
    value: Any,
    current: dict,
    loaded: dict,
    binding: dict,
    api: Any,
    *,
    final: bool = False,
) -> dict:
    if not isinstance(value, dict) or set(value) != INTAKE:
        raise ValueError("Invalid ESG literal intake")
    if any(
        not isinstance(value[k], str) or len(value[k]) > 4000
        for k in INTAKE - {"input_ids"}
    ):
        raise ValueError("Invalid ESG question/command/predecessor")
    ids = value["input_ids"]
    allowed = {r["input_id"] for r in sources(loaded)}
    if (
        not isinstance(ids, list)
        or any(not isinstance(x, str) or x not in allowed for x in ids)
        or len(set(ids)) != len(ids)
    ):
        raise ValueError("Choose actual registered ESG sources")
    if value["command"] not in COMMANDS | {""}:
        raise ValueError("The model may not register a professional decision")
    if final:
        if not value["question"].strip() or not ids or value["command"] not in COMMANDS:
            raise ValueError("Complete the question, operation and selected sources")
        if (value["command"] == "start_case") != (current["public"] is None):
            raise ValueError(
                "Start only an absent case; use its current exact state otherwise"
            )
        if value["previous_run_id"] and value["command"] != "start_case":
            raise ValueError("A predecessor is selected only for a new ESG run")
        previous_case(value["previous_run_id"], binding, api)
    return value


def human_fields(value: Any) -> dict:
    if not isinstance(value, dict) or set(value) != DECISION:
        raise ValueError("Invalid literal human ESG decision draft")
    if any(
        not isinstance(value[k], str) or len(value[k]) > 10000
        for k in DECISION - {"dependency_refs"}
    ):
        raise ValueError("Invalid literal decision field")
    refs = value["dependency_refs"]
    if (
        not isinstance(refs, list)
        or len(refs) > 1000
        or any(
            not isinstance(x, str) or not re.fullmatch(r"[a-f0-9]{64}", x) for x in refs
        )
        or len(set(refs)) != len(refs)
    ):
        raise ValueError("Choose exact ESG dependency versions")
    return value


def decision_request(value: dict, current: dict, key: str) -> dict:
    if current["public"] is None:
        raise ValueError("Start the case before recording a decision")
    rows = current["public"]["summary"]["objects"]
    refs = []
    for selected in value["dependency_refs"]:
        row = next((r for r in rows if r["reference"]["sha256"] == selected), None)
        if row is None or not row["current"]:
            raise ValueError("Decision dependency is foreign or stale")
        refs.append(row["reference"])
    return {
        "id": value["id"],
        "idempotency_key": key,
        "expected_state_sha256": current["base_state"],
        "dependencies": refs,
        "record": {k: value[k] for k in DECISION - {"id", "dependency_refs"}},
    }


def grant(current: dict, identifier: str, *, fresh: bool = False) -> dict:
    row = next(
        (
            r
            for r in current["state"]["grants"]
            if r["grant_ref"] == identifier
            and r["scope"]["owner"] == current["scope"]["owner"]
        ),
        None,
    )
    if row is None:
        raise PermissionError("ESG mandate belongs to another owner or run")
    if fresh and (
        row["status"] != "open"
        or row["scope"] != current["scope"]
        or row["base_state"] != current["base_state"]
    ):
        raise ValueError("ESG mandate is closed or obsolete; reopen the current case")
    return row


def model_request(proposal: Any, row: dict, key: str) -> dict:
    if not isinstance(proposal, dict) or set(proposal) & {
        "idempotency_key",
        "expected_state_sha256",
        "previous_context",
    }:
        raise ValueError(
            "Supply only the authored body; scope and request IDs are fixed by the mandate"
        )
    if (
        row["fields"]["command"] == "bind_evidence"
        and proposal.get("input_id") not in row["fields"]["input_ids"]
    ):
        raise PermissionError("This ESG evidence source was not granted")
    result = {**limited(proposal, 96000), "idempotency_key": key}
    if row["fields"]["command"] == "start_case":
        result["previous_context"] = (
            row["previous_case"]["context_path"] if row["previous_case"] else None
        )
    else:
        result["expected_state_sha256"] = row["base_state"]
    return result


def publish(
    root: Path,
    binding: dict,
    loaded: dict,
    current: dict,
    command: str,
    request: dict,
    preview: dict,
    intent: Path,
    fingerprint: str,
    api: Any,
) -> dict:
    """Conserve ordinary request, public object/draft and exact native receipt."""
    reloaded = api.load_binding(binding)
    fresh = snapshot(binding, reloaded, root, api)
    if fresh["revision"] != current["revision"] or not writable(fresh, reloaded):
        raise ValueError("ESG sources, run or mandate changed during preview")
    key = request["idempotency_key"]
    stamp = api.digest(key)
    name = "esg-native-request-" + stamp + ".json"
    receipt_name = "esg-native-receipt-" + stamp + ".json"
    if (current["output"] / name).exists() or (
        current["output"] / receipt_name
    ).exists():
        raise ValueError("Unreceipted ESG conservation requires recovery")
    pending = {
        "fingerprint": fingerprint,
        "public_key": key,
        "command": command,
        "public_request": request,
    }
    api.atomic_json(intent, pending)
    api.atomic_json(current["output"] / name, {"command": command, "request": request})
    applied = producer(
        root,
        {
            "operation": "apply",
            "context": str(loaded["context_path"]),
            "command": command,
            "request": request,
        },
    )
    if (
        applied["result"]["reference"] != preview["reference"]
        or applied["object"]["record"] != preview["object"]["record"]
    ):
        raise ValueError(
            "Actual ESG record differs from its complete preview; inspect outputs"
        )
    reloaded = api.load_binding(binding)
    after = snapshot(binding, reloaded, root, api)
    if (
        after["scope"] != current["scope"]
        or after["state"] != current["state"]
        or after["base_state"] != applied["result"]["state_sha256"]
        or reloaded["run"]["status"] != "running"
        or "REVIEWER" not in os.environ.get("VERA_WORKSPACE_ROLES", "").split(",")
    ):
        raise ValueError("ESG conservation changed scope; retain the recovery intent")
    outputs = {name: file_hash(current["output"] / name)}
    if applied["result"]["reference"]["kind"] == "artifact":
        for suffix in (".json", ".md"):
            artifact_name = (
                "esg-draft-" + applied["result"]["reference"]["sha256"] + suffix
            )
            outputs[artifact_name] = file_hash(current["output"] / artifact_name)
    receipt = {
        "schema_version": 1,
        "command": command,
        "reference": applied["result"]["reference"],
        "public_state_sha256": applied["result"]["state_sha256"],
        "owner": current["scope"]["owner"],
        "recorded_at": datetime.now(timezone.utc).isoformat(),
        "identity_authenticated": False,
        "professional_confirmation_recorded": command == "record_decision",
        "files": outputs,
    }
    api.atomic_json(current["output"] / receipt_name, receipt)
    outputs[receipt_name] = file_hash(current["output"] / receipt_name)
    return {
        "saved": True,
        "reference": applied["result"]["reference"],
        "public_state_sha256": applied["result"]["state_sha256"],
        "professional_confirmation_recorded": command == "record_decision",
        "identity_authenticated": False,
        "files": [
            {"name": n, "path": str(current["output"] / n), "sha256": h}
            for n, h in outputs.items()
        ],
        "_intent": pending,
        "_outputs": outputs,
    }


def dispatch(
    tool: str, args: dict, binding: dict, loaded: dict, root: Path, api: Any
) -> dict:
    """Public execution requires exact saved body and separately renewed human choice."""
    action = tool.removeprefix("vera_workspace_esg_author_")
    current = snapshot(binding, loaded, root, api)
    operations = {"request", "stage", "publish", "cancel", "decision_commit"}
    key = args.get("idempotency_key")
    intent = (
        current["home"]
        / ("esg-intent-" + api.digest([current["scope"]["owner"], key]) + ".json")
        if action in operations
        and isinstance(key, str)
        and re.fullmatch(r"[A-Za-z0-9_-]{1,120}", key)
        else None
    )
    fingerprint = api.digest([tool, args, current["scope"]])
    if intent is not None and intent.exists():
        prior = api.read_json(intent)
        if (
            current["recovery_required"]
            or prior["fingerprint"] != fingerprint
            or "result" not in prior
        ):
            raise ValueError("Changed or uncertain ESG retry")
        return prior["result"]
    base = {
        "work_ref": binding["work_ref"],
        "revision": current["revision"],
        "can_write": writable(current, loaded),
        "recovery_required": current["recovery_required"],
        "state_sha256": current["base_state"],
        "actual_model_reads_verified": False,
        "identity_authenticated": False,
        "assurance_opinion": False,
    }
    if action in {"setup", "draft_save", "request"}:
        path, saved, stamp = draft(
            current,
            "intake",
            {"question": "", "command": "", "input_ids": [], "previous_run_id": ""},
            api,
        )
        if action == "setup":
            sys.path.insert(0, str(api.module_root("studio-archive") / "scripts"))
            from client_ledger import list_runs

            prior = [
                r
                for r in list_runs(
                    Path(binding["client_root"]), binding["engagement_id"]
                )
                if r["run"]["workflow_id"] == binding["workflow_id"]
                and r["run"]["run_id"] != binding["run_id"]
                and (Path(r["output_dir"]) / "esg_state.json").is_file()
            ]
            return limited(
                {
                    **base,
                    "fields": saved["fields"],
                    "draft_revision": stamp,
                    "sources": sources(loaded),
                    "commands": sorted(
                        COMMANDS - {"start_case"}
                        if current["public"]
                        else {"start_case"}
                    ),
                    "previous_runs": [
                        {
                            "run_id": r["run"]["run_id"],
                            "label": r["run"]["label"],
                            "status": r["run"]["status"],
                        }
                        for r in prior
                    ],
                    "grants": [
                        {
                            "grant_ref": r["grant_ref"],
                            "status": r["status"],
                            "question": r["fields"]["question"],
                        }
                        for r in current["state"]["grants"]
                        if r["scope"]["owner"] == current["scope"]["owner"]
                    ],
                }
            )
    if action in {
        "decision_setup",
        "decision_draft_save",
        "decision_preview",
        "decision_commit",
    }:
        if action != "decision_setup" and (
            args["source_ref"] != current["base_state"]
            or args["item_id"] != "esg-decision"
        ):
            raise ValueError("Select the exact current ESG decision scope")
        identity = "decision:" + str(current["base_state"])
        path, saved, stamp = draft(
            current,
            identity,
            {**{k: "" for k in DECISION - {"dependency_refs"}}, "dependency_refs": []},
            api,
        )
        if action == "decision_setup":
            if current["public"] is None:
                raise ValueError("Start the ESG case before a professional decision")
            offset = args.get("offset", 0)
            if type(offset) is not int or offset < 0:
                raise ValueError("Invalid ESG decision dependency page")
            rows = current["public"]["summary"]["objects"]
            return limited(
                {
                    **base,
                    "data": {"selection": {"source_ref": current["base_state"]}},
                    "selection": {"id": "esg-decision"},
                    "fields": saved["fields"],
                    "draft_revision": stamp,
                    "dependencies": rows[offset : offset + 30],
                    "offset": offset,
                    "total": len(rows),
                    "has_more": offset + 30 < len(rows),
                }
            )
        if action == "decision_preview":
            if (
                args["revision"] != current["revision"]
                or args["expected_draft_revision"] != stamp
                or args["fields"] != saved["fields"]
            ):
                raise ValueError("Reopen the exact saved human decision before preview")
            request = decision_request(
                human_fields(saved["fields"]), current, "esg-preview-decision"
            )
            preview = producer(
                root,
                {
                    "operation": "preview",
                    "context": str(loaded["context_path"]),
                    "command": "record_decision",
                    "request": request,
                },
            )
            return limited(
                {
                    **base,
                    "preview": preview,
                    "fields": saved["fields"],
                    "draft_revision": stamp,
                }
            )
    if action in {"read", "context", "stage", "publish", "cancel"}:
        row = grant(current, args["grant_ref"])
        proposals = [
            r
            for r in current["state"]["proposals"]
            if r["grant_ref"] == row["grant_ref"]
        ]
        selected = next(
            (r for r in proposals if r["case_ref"] == args.get("case_ref")), None
        )
        if args.get("case_ref") and selected is None:
            raise ValueError("Select an exact complete ESG proposal")
        if action in {"read", "context"}:
            obsolete = (
                row["scope"] != current["scope"]
                or row["base_state"] != current["base_state"]
            )
            value = {
                **base,
                "grant_ref": row["grant_ref"],
                "status": row["status"],
                "obsolete": obsolete,
                "question": row["fields"]["question"],
                "command": row["fields"]["command"],
                "source_ref": row["grant_ref"],
                "data": {"selection": {"source_ref": row["grant_ref"]}},
                "selection": {"id": selected["case_ref"]} if selected else None,
                "proposals": [
                    {"case_ref": r["case_ref"], "conserved": "conservation" in r}
                    for r in proposals
                ],
            }
            if action == "context":
                grant(current, row["grant_ref"], fresh=True)
                if (
                    args["revision"] != current["revision"]
                    or current["recovery_required"]
                ):
                    raise ValueError(
                        "Reopen the exact ESG mandate before model context"
                    )
                previous = previous_case(row["fields"]["previous_run_id"], binding, api)
                if previous != row["previous_case"]:
                    raise ValueError("ESG predecessor changed after confirmation")
                value["sources"] = [
                    {
                        "input_id": r["binding_id"],
                        "authorized_path": str(
                            Path(binding["client_root"]) / r["source_relative_path"]
                        ),
                        "sha256": r["sha256"],
                    }
                    for r in loaded["input_manifest"]["inputs"]
                    if r["binding_id"] in row["fields"]["input_ids"]
                ]
                value["current_case"] = (
                    {
                        "authorized_path": str(current["output"] / "esg_state.json"),
                        "sha256": current["public"]["state_file_sha256"],
                    }
                    if current["public"]
                    else None
                )
                value["previous_case"] = previous
                value["skill_path"] = str(
                    root / "skills/esg-reporting-assurance/SKILL.md"
                )
                value["proposal_contract_path"] = str(
                    root / "schemas/foundation.schema.json"
                )
                value["selected_proposal"] = (
                    {
                        "authorized_path": str(
                            current["home"] / selected["case_ref"] / "request.json"
                        ),
                        "sha256": file_hash(
                            current["home"] / selected["case_ref"] / "request.json"
                        ),
                    }
                    if selected
                    else None
                )
                return limited(value, 64000)
            if selected:
                value.update(
                    case_ref=selected["case_ref"],
                    proposal=api.read_json(
                        current["home"] / selected["case_ref"] / "request.json"
                    ),
                    preview=api.read_json(
                        current["home"] / selected["case_ref"] / "preview.json"
                    ),
                    conservation=selected.get("conservation"),
                )
            return limited(value)
    with api.write_lock(current["output"]):
        loaded = api.load_binding(binding)
        current = snapshot(binding, loaded, root, api)
        if not writable(current, loaded):
            raise PermissionError(
                "ESG writes require a running reviewer without uncertain writes"
            )
        if args["revision"] != current["revision"]:
            raise ValueError("Reopen the current exact ESG state")
        if action in operations and intent is None:
            raise ValueError("Invalid ESG request identity")
        result: dict
        outputs = {}
        pending = {"fingerprint": fingerprint}
        if action in {
            "draft_save",
            "request",
            "decision_draft_save",
            "decision_commit",
        }:
            empty = (
                {"question": "", "command": "", "input_ids": [], "previous_run_id": ""}
                if action in {"draft_save", "request"}
                else {
                    **{k: "" for k in DECISION - {"dependency_refs"}},
                    "dependency_refs": [],
                }
            )
            identity = (
                "intake"
                if action in {"draft_save", "request"}
                else "decision:" + str(current["base_state"])
            )
            path, saved, stamp = draft(current, identity, empty, api)
            if args["expected_draft_revision"] != stamp:
                raise ValueError("ESG private draft generation changed")
            fields = (
                intake(
                    args["fields"],
                    current,
                    loaded,
                    binding,
                    api,
                    final=action == "request",
                )
                if action in {"draft_save", "request"}
                else human_fields(args["fields"])
            )
            if action in {"draft_save", "decision_draft_save"}:
                api.atomic_json(
                    path,
                    {
                        "scope": current["scope"],
                        "generation": saved["generation"] + 1,
                        "fields": fields,
                    },
                )
                return {"saved": True, "professional_confirmation_recorded": False}
            if args.get("confirmed") is not True or fields != saved["fields"]:
                raise ValueError("Renew confirmation of the exact saved ESG fields")
            if action == "request":
                row = {
                    "scope": current["scope"],
                    "fields": fields,
                    "base_state": current["base_state"],
                    "previous_case": previous_case(
                        fields["previous_run_id"], binding, api
                    ),
                    "request_key": key,
                    "status": "open",
                }
                row["grant_ref"] = grant_ref(row)
                api.atomic_json(intent, pending)
                current["state"]["grants"].append(row)
                result = {
                    "saved": True,
                    "grant_ref": row["grant_ref"],
                    "actual_model_reads_verified": False,
                }
            else:
                request = decision_request(
                    fields,
                    current,
                    "esg-native-" + api.digest([current["scope"]["owner"], key]),
                )
                preview = producer(
                    root,
                    {
                        "operation": "preview",
                        "context": str(loaded["context_path"]),
                        "command": "record_decision",
                        "request": request,
                    },
                )
                result = publish(
                    root,
                    binding,
                    loaded,
                    current,
                    "record_decision",
                    request,
                    preview,
                    intent,
                    fingerprint,
                    api,
                )
                pending = result.pop("_intent")
                outputs = result.pop("_outputs")
        elif action == "stage":
            row = grant(current, args["grant_ref"], fresh=True)
            if (
                previous_case(row["fields"]["previous_run_id"], binding, api)
                != row["previous_case"]
            ):
                raise ValueError("ESG predecessor changed")
            request = model_request(
                args["proposal"],
                row,
                "esg-native-" + api.digest([current["scope"]["owner"], key]),
            )
            preview = producer(
                root,
                {
                    "operation": "preview",
                    "context": str(loaded["context_path"]),
                    "command": row["fields"]["command"],
                    "request": request,
                },
            )
            reloaded = api.load_binding(binding)
            after = snapshot(binding, reloaded, root, api)
            if after["revision"] != current["revision"] or not writable(
                after, reloaded
            ):
                raise ValueError("ESG scope changed during proposal validation")
            name = "esg-proposal-" + api.digest([row["grant_ref"], request])
            folder = current["home"] / name
            api.atomic_json(intent, pending)
            folder.mkdir(exist_ok=False)
            api.atomic_json(folder / "request.json", request)
            api.atomic_json(folder / "preview.json", preview)
            current["state"]["proposals"].append(
                {
                    "grant_ref": row["grant_ref"],
                    "case_ref": name,
                    "artifacts": tree_hash(folder),
                }
            )
            result = {
                "saved": True,
                "case_ref": name,
                "professional_confirmation_recorded": False,
            }
        elif action == "cancel":
            row = grant(current, args["grant_ref"])
            if (
                row["status"] != "open"
                or args.get("confirmed") is not True
                or args["source_ref"] != row["grant_ref"]
            ):
                raise ValueError("Confirm cancellation of this exact open ESG mandate")
            api.atomic_json(intent, pending)
            row["status"] = "cancelled"
            result = {"saved": True, "status": "cancelled"}
        elif action == "publish":
            row = grant(current, args["grant_ref"], fresh=True)
            selected = next(
                (
                    r
                    for r in current["state"]["proposals"]
                    if r["grant_ref"] == row["grant_ref"]
                    and r["case_ref"] == args["case_ref"]
                ),
                None,
            )
            if (
                selected is None
                or args.get("confirmed") is not True
                or args["source_ref"] != row["grant_ref"]
                or args["item_id"] != selected["case_ref"]
            ):
                raise ValueError("Renew confirmation of the exact whole ESG proposal")
            if (
                previous_case(row["fields"]["previous_run_id"], binding, api)
                != row["previous_case"]
            ):
                raise ValueError("ESG predecessor changed")
            request = api.read_json(
                current["home"] / selected["case_ref"] / "request.json"
            )
            preview = api.read_json(
                current["home"] / selected["case_ref"] / "preview.json"
            )
            verified = producer(
                root,
                {
                    "operation": "preview",
                    "context": str(loaded["context_path"]),
                    "command": row["fields"]["command"],
                    "request": request,
                },
            )
            if verified["reference"] != preview["reference"]:
                raise ValueError("ESG proposal validation changed")
            result = publish(
                root,
                binding,
                loaded,
                current,
                row["fields"]["command"],
                request,
                preview,
                intent,
                fingerprint,
                api,
            )
            pending = result.pop("_intent")
            outputs = result.pop("_outputs")
            selected["conservation"] = result
            row["status"] = "conserved"
        else:
            raise ValueError("Unsupported ESG authoring action")
        api.atomic_json(current["home"] / "esg-authoring.json", current["state"])
        api.atomic_json(intent, {**pending, "outputs": outputs, "result": result})
        return result
