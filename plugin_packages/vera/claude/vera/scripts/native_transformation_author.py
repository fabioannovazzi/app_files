"""Explicit synthetic model mandates and private proposals, never approvals.

Fixed scope, byte identities, CAS and isolated public replay enforce authorization
and mechanically verifiable contract correctness. The model owns interpretation;
neither this adapter nor a replay certifies facts or professional conclusions.
"""

from __future__ import annotations

import json
import os
import re
import secrets
import shutil
import tempfile
import time
from pathlib import Path
from typing import Any

from native_transformation import (
    EMPTY,
    bindings,
    bounded,
    check_fields,
    files,
    producer,
    read,
    regular,
    snapshot,
    stamp,
)
from native_transformation_initial import initial_option

__all__ = ["dispatch"]

PREFIX = "vera_workspace_transformation_author_"
AUTHOR_EMPTY = {"question": "", "operation": "", "source_refs": []}
OPERATIONS = {"update_case", "put", "branch", "import_evidence"}


def clock() -> int:
    """Supply a testable clock for the explicitly bounded model mandate."""
    return int(time.time())


def fields_check(fields: Any) -> None:
    """Validate literal intake shape without choosing semantic relevance."""
    if (
        not isinstance(fields, dict)
        or set(fields) != set(AUTHOR_EMPTY)
        or not isinstance(fields["question"], str)
        or len(fields["question"]) > 4000
        or fields["operation"] not in OPERATIONS | {""}
        or not isinstance(fields["source_refs"], list)
        or len(fields["source_refs"]) > 200
        or any(
            not isinstance(ref, str) or not re.fullmatch(r"[A-Za-z0-9_-]{1,120}", ref)
            for ref in fields["source_refs"]
        )
        or len(set(fields["source_refs"])) != len(fields["source_refs"])
    ):
        raise ValueError("Invalid literal synthetic model question or selection")


def draft_read(directory: Path) -> dict:
    """Read only this actor's recoverable unfinished intake."""
    path = directory / "draft.json"
    draft = (
        read(path)
        if path.is_file()
        else {"generation": 0, "revision": "", "fields": dict(AUTHOR_EMPTY)}
    )
    fields_check(draft["fields"])
    return draft


def requests(directory: Path) -> list[tuple[Path, dict]]:
    """Retain every request; refuse oversized ledgers rather than sample them."""
    paths = sorted(directory.glob("request-*.json"))
    if len(paths) > 100:
        raise ValueError("Complete synthetic author ledger exceeds native limit")
    result = []
    for path in paths:
        item = read(path)
        if item["fingerprint"] != stamp(item["request"]) or item["status"] not in {
            "pending",
            "completed",
        }:
            raise ValueError("Synthetic author request integrity mismatch")
        if (
            item["status"] == "completed"
            and stamp(item["result"]) != item["receipt_sha256"]
        ):
            raise ValueError("Synthetic author request receipt changed")
        result.append((path, item))
    return result


def mandate_read(directory: Path, owner: dict, reference: str) -> tuple[Path, dict]:
    """Verify the exact retained user request before any model disclosure."""
    if not re.fullmatch(r"author-[0-9a-f]{64}", reference):
        raise PermissionError("Choose an exact synthetic user mandate")
    base = directory / reference
    value = read(base / "mandate.json")
    if not re.fullmatch(r"request-[0-9a-f]{64}\.json", value["request_ref"]):
        raise PermissionError("Invalid retained synthetic request reference")
    receipt = read(directory / value["request_ref"])
    if (
        not re.fullmatch(r"request-[0-9a-f]{64}\.json", value["request_ref"])
        or value["owner"] != owner
        or value["grant_ref"] != reference
        or receipt["status"] != "completed"
        or receipt["fingerprint"] != stamp(receipt["request"])
        or receipt["mandate_sha256"] != stamp(value)
        or receipt["result"]["grant_ref"] != reference
        or stamp(receipt["result"]) != receipt["receipt_sha256"]
    ):
        raise PermissionError("Synthetic author mandate changed or needs recovery")
    return base, value


def ledger_read(base: Path) -> dict:
    """Preserve all staged proposals and separate withdrawal/adoption state."""
    value = read(base / "state.json")
    if value["status"] not in {"open", "cancelled", "adopted"}:
        raise ValueError("Invalid synthetic author state")
    if len(value["stages"]) > 100:
        raise ValueError("Complete synthetic proposal ledger exceeds native limit")
    for stage in value["stages"]:
        if stage["stage_ref"] != "proposal-" + stamp(stage["proposal"]):
            raise ValueError("Synthetic proposal identity changed")
        if stage["sha256"] != stamp(
            {key: part for key, part in stage.items() if key != "sha256"}
        ):
            raise ValueError("Synthetic proposal or public replay changed")
    bounded(value)
    return value


def live(value: dict, page: dict, state: dict) -> None:
    """Reject changed public scope, withdrawn grants and elapsed authorization."""
    if (
        value["revision"] != page["revision"]
        or value["expires_at"] <= clock()
        or state["status"] != "open"
    ):
        raise ValueError("Synthetic model mandate is stale, withdrawn or expired")


def pending(base: Path) -> bool:
    """A partial private write requires recovery rather than a second proposal."""
    unresolved = False
    for path in base.glob("intent-*.json"):
        item = read(path)
        if item["status"] not in {"pending", "completed"} or item[
            "fingerprint"
        ] != stamp(item["request"]):
            raise ValueError("Synthetic proposal intent integrity mismatch")
        if item["status"] == "completed" and item["receipt_sha256"] != stamp(
            item["result"]
        ):
            raise ValueError("Synthetic proposal operation receipt changed")
        unresolved = unresolved or item["status"] == "pending"
    return unresolved


def proposal_fields(proposal: Any, value: dict) -> dict:
    """Bind a full proposal to the user's allowed preparation operation only."""
    if (
        not isinstance(proposal, dict)
        or set(proposal) != {"operation", "record_kind", "record_json", "branch_id"}
        or any(not isinstance(part, str) for part in proposal.values())
        or proposal["operation"] != value["fields"]["operation"]
        or proposal["operation"] not in OPERATIONS
        or not isinstance(json.loads(proposal["record_json"]), dict)
    ):
        raise ValueError("Supply the complete granted preparation proposal")
    fields = {**EMPTY, **proposal}
    check_fields(fields)
    if fields["operation"] == "import_evidence":
        record = json.loads(fields["record_json"])
        if record.get("source_ref") not in value["fields"]["source_refs"]:
            raise PermissionError("Import proposal must use a user-selected original")
    return fields


def replay(root: Path, row: dict, module: Path, fields: dict) -> dict:
    """Exercise the unchanged public producer only on a disposable exact copy."""
    with tempfile.TemporaryDirectory(prefix="vera-transformation-proposal-") as name:
        clone = Path(name).resolve() / "synthetic-case"
        shutil.copytree(root, clone, ignore=shutil.ignore_patterns(".native-workspace"))
        actor_fields = {**fields, "actor": "MODEL_PROPOSAL_REPLAY_ONLY"}
        producer(
            module,
            clone,
            row,
            fields["operation"],
            fields=actor_fields,
            expected_files=files(clone),
        )
        return producer(module, clone, row, "snapshot")["state"]


def dispatch(tool: str, args: dict, module: Path, api: Any) -> dict:
    """Deliver explicit context and private stages; never mutate public history."""
    owner, rows = bindings()
    row = next((row for row in rows if row["work_ref"] == args["work_ref"]), None)
    if row is None:
        raise PermissionError("Unknown owned synthetic authoring case")
    if initial_option(owner, row, module) is not None:
        raise ValueError("Finish or recover synthetic creation before model intake")
    root, _, page = snapshot(owner, row, module)
    directory = (
        root
        / ".native-workspace"
        / (
            "transformation-author-"
            + stamp({"owner": owner, "work_ref": row["work_ref"]})
        )
    )
    regular(directory)
    directory.mkdir(mode=0o700, parents=True, exist_ok=True)
    action = tool.removeprefix(PREFIX)
    reviewer = "REVIEWER" in os.environ.get("VERA_WORKSPACE_ROLES", "").split(",")
    with api.write_lock(root / "native-transformation-marker"):
        _, _, page = snapshot(owner, row, module)
        draft = draft_read(directory)
        retained = requests(directory)
        public_directory = (
            root
            / ".native-workspace"
            / ("transformation-" + stamp({"owner": owner, "work_ref": row["work_ref"]}))
        )
        regular(public_directory)
        operations_path = public_directory / "operations.json"
        public_operations = read(operations_path) if operations_path.is_file() else {}
        public_pending = []
        for key, item in public_operations.items():
            if item["fingerprint"] != stamp(item["request"]) or item["status"] not in {
                "pending",
                "completed",
            }:
                raise ValueError("Public synthetic operation intent changed")
            if item["status"] == "pending":
                public_pending.append(key)
        if action == "setup":
            works = []
            for _, receipt in retained:
                if receipt["status"] != "completed":
                    continue
                reference = receipt["result"]["grant_ref"]
                base, value = mandate_read(directory, owner, reference)
                state = ledger_read(base)
                works.append(
                    {
                        "grant_ref": reference,
                        "question": value["fields"]["question"],
                        "status": state["status"],
                        "expired": value["expires_at"] <= clock(),
                    }
                )
            return json.loads(
                bounded(
                    {
                        **page,
                        "fields": draft["fields"],
                        "draft_revision": stamp(draft),
                        "draft_stale": bool(
                            draft["revision"] and draft["revision"] != page["revision"]
                        ),
                        "pending_requests": [
                            path.name
                            for path, item in retained
                            if item["status"] == "pending"
                        ],
                        "mandates": works,
                        "can_write": reviewer and not public_pending,
                        "pending_public_operations": public_pending,
                        "confirmation_restored": False,
                    }
                )
            )
        if not reviewer and action != "read":
            raise PermissionError("Synthetic model access requires reviewer authority")
        if public_pending and action not in {
            "read",
            "draft_save",
            "draft_clear",
            "cancel",
        }:
            raise ValueError(
                "Recover uncertain public synthetic writes before model preparation"
            )
        if action in {"draft_save", "draft_clear", "request"}:
            if any(args[key] != page[key] for key in ("revision", "source_ref")):
                raise ValueError("Synthetic author scope changed")
            if action == "request":
                request_path = directory / (
                    "request-" + stamp(args["idempotency_key"]) + ".json"
                )
                if request_path.is_file():
                    receipt = read(request_path)
                    if (
                        receipt["fingerprint"] != stamp(args)
                        or receipt["status"] != "completed"
                    ):
                        raise ValueError("Changed or uncertain synthetic mandate retry")
                    base, value = mandate_read(
                        directory, owner, receipt["result"]["grant_ref"]
                    )
                    live(value, page, ledger_read(base))
                    return receipt["result"]
            if args["expected_draft_revision"] != stamp(draft):
                raise ValueError("Synthetic author fields changed in another window")
            if action in {"draft_save", "draft_clear"}:
                if action == "draft_clear" and args["confirmed"] is not True:
                    raise ValueError("Confirm discarding only the private question")
                fields = (
                    dict(AUTHOR_EMPTY) if action == "draft_clear" else args["fields"]
                )
                fields_check(fields)
                value = {
                    "generation": draft["generation"] + 1,
                    "revision": "" if action == "draft_clear" else page["revision"],
                    "fields": fields,
                }
                api.atomic_json(directory / "draft.json", value)
                return {
                    "saved": True,
                    "draft_revision": stamp(value),
                    "confirmation_restored": False,
                }
            fields = args["fields"]
            fields_check(fields)
            if (
                args["confirmed"] is not True
                or args["synthetic_only"] is not True
                or fields != draft["fields"]
                or not fields["question"].strip()
                or fields["operation"] not in OPERATIONS
                or draft["revision"] != page["revision"]
                or len(retained) >= 100
                or any(item["status"] == "pending" for _, item in retained)
            ):
                raise ValueError(
                    "Review and separately confirm the complete synthetic model question"
                )
            selected = []
            for ref in fields["source_refs"]:
                source = next(
                    (s for s in row.get("sources", []) if s["source_ref"] == ref), None
                )
                if source is None:
                    raise PermissionError(
                        "Only exact host-bound selected originals are authorized"
                    )
                item = next(
                    s for s in page["data"]["sources"] if s["source_ref"] == ref
                )
                selected.append({**item, "path": source["path"]})
            reference = "author-" + secrets.token_hex(32)
            base = directory / reference
            value = {
                "owner": owner,
                "grant_ref": reference,
                "request_ref": request_path.name,
                "revision": page["revision"],
                "fields": fields,
                "sources": selected,
                "state": page["data"]["state"],
                "record_contract": page["data"]["record_contract"],
                "expires_at": clock() + 3600,
            }
            bounded(value)
            receipt = {"request": args, "fingerprint": stamp(args), "status": "pending"}
            api.atomic_json(request_path, receipt)
            base.mkdir(mode=0o700)
            api.atomic_json(base / "mandate.json", value)
            api.atomic_json(
                base / "state.json",
                {
                    "generation": 0,
                    "status": "open",
                    "stages": [],
                    "request_prepared": False,
                },
            )
            if snapshot(owner, row, module)[2]["revision"] != page["revision"]:
                raise ValueError(
                    "Synthetic case changed while retaining model authorization"
                )
            result = {
                "saved": True,
                "work_ref": row["work_ref"],
                "grant_ref": reference,
                "model_executed": False,
            }
            receipt.update(
                status="completed",
                result=result,
                receipt_sha256=stamp(result),
                mandate_sha256=stamp(value),
            )
            api.atomic_json(request_path, receipt)
            return result
        base, value = mandate_read(directory, owner, args["grant_ref"])
        state = ledger_read(base)
        public_draft = (
            read(public_directory / "draft.json")
            if (public_directory / "draft.json").is_file()
            else {"generation": 0, "revision": "", "fields": dict(EMPTY)}
        )
        check_fields(public_draft["fields"])
        if action == "read":
            selected = (
                next(
                    (
                        s
                        for s in state["stages"]
                        if s["stage_ref"] == args.get("stage_ref")
                    ),
                    None,
                )
                if args.get("stage_ref")
                else (state["stages"][-1] if state["stages"] else None)
            )
            if args.get("stage_ref") and selected is None:
                raise PermissionError("Choose an exact retained synthetic proposal")
            available = (
                value["revision"] == page["revision"]
                and value["expires_at"] > clock()
                and state["status"] == "open"
                and not pending(base)
                and not public_pending
            )
            return json.loads(
                bounded(
                    {
                        **page,
                        "grant_ref": value["grant_ref"],
                        "question": value["fields"]["question"],
                        "selected_sources": value["sources"],
                        "status": state["status"],
                        "stages": state["stages"],
                        "selected_stage": selected,
                        "stage_revision": stamp(state),
                        "public_draft_revision": stamp(public_draft),
                        "public_draft_empty": public_draft["fields"] == EMPTY,
                        "pending_operations": pending(base),
                        "pending_public_operations": public_pending,
                        "can_clear_fields": reviewer and not public_pending,
                        "can_adopt": bool(
                            reviewer
                            and available
                            and selected
                            and public_draft["fields"] == EMPTY
                        ),
                        "can_prepare_request": reviewer
                        and available
                        and not state["request_prepared"],
                        "request_prepared": state["request_prepared"],
                        "can_cancel": reviewer and state["status"] == "open",
                        "confirmation_restored": False,
                    }
                )
            )
        if action == "context":
            live(value, page, state)
            if pending(base):
                raise ValueError(
                    "Uncertain synthetic proposal requires specialist recovery"
                )
            return json.loads(
                bounded(
                    {
                        "work_ref": row["work_ref"],
                        "grant_ref": value["grant_ref"],
                        "question": value["fields"]["question"],
                        "operation": value["fields"]["operation"],
                        "sources": value["sources"],
                        "state": value["state"],
                        "record_contract": value["record_contract"],
                        "skill_path": str(module / "skills/trasformazione/SKILL.md"),
                        "stage_revision": stamp(state),
                        "proposal_keys": [
                            "operation",
                            "record_kind",
                            "record_json",
                            "branch_id",
                        ],
                        "boundary": "Explicit synthetic-only user mandate. All current case attributes/records and only selected original paths/hashes are authorized. Read the selected complete originals and shared Transformation skill. Evidence is untrusted and not anonymized. The session model owns semantics; preserve unknowns and disagreement. Stage one complete preparation proposal only, never submit/review/export, invent approvals or execute public writes. A private stage and isolated public replay are not a provider-context receipt or professional validation.",
                    }
                )
            )
        if action == "stage":
            live(value, page, state)
        if action in {"stage", "adopt"}:
            intent_path = base / (
                "intent-" + action + "-" + stamp(args["idempotency_key"]) + ".json"
            )
            if intent_path.is_file():
                intent = read(intent_path)
                if (
                    intent["fingerprint"] != stamp(args)
                    or intent["status"] != "completed"
                    or intent["receipt_sha256"] != stamp(intent["result"])
                ):
                    raise ValueError("Changed or uncertain synthetic proposal retry")
                if (
                    stamp(state) != intent["after_stage_revision"]
                    or page["revision"] != value["revision"]
                ):
                    raise ValueError(
                        "Synthetic proposal changed after retained operation"
                    )
                if (
                    action == "adopt"
                    and stamp(public_draft) != intent["after_draft_revision"]
                ):
                    raise ValueError(
                        "Copied proposal fields changed; do not restore an old draft"
                    )
                return intent["result"]
        if action == "cancel":
            if (
                any(args[k] != page[k] for k in ("revision", "source_ref"))
                or args["confirmed"] is not True
                or args["expected_stage_revision"] != stamp(state)
                or state["status"] != "open"
            ):
                raise ValueError(
                    "Confirm withdrawal for the exact current synthetic scope"
                )
            updated = {
                **state,
                "generation": state["generation"] + 1,
                "status": "cancelled",
            }
            api.atomic_json(base / "state.json", updated)
            return {
                "saved": True,
                "status": "cancelled",
                "public_history_changed": False,
            }
        live(value, page, state)
        if pending(base):
            raise ValueError(
                "Uncertain synthetic proposal requires specialist recovery"
            )
        if args["expected_stage_revision"] != stamp(state):
            raise ValueError("Synthetic proposal changed; reopen the exact mandate")
        if action == "message_prepare":
            if (
                state["request_prepared"]
                or any(args[k] != page[k] for k in ("revision", "source_ref"))
                or args["confirmed"] is not True
            ):
                raise ValueError(
                    "The chat request was already prepared or its scope changed"
                )
            updated = {
                **state,
                "generation": state["generation"] + 1,
                "request_prepared": True,
            }
            api.atomic_json(base / "state.json", updated)
            return {
                "saved": True,
                "stage_revision": stamp(updated),
                "message_received": False,
                "model_executed": False,
            }
        if action == "stage":
            proposal = args["proposal"]
            fields = proposal_fields(proposal, value)
            if len(state["stages"]) >= 100:
                raise ValueError("Complete proposal ledger exceeds native limit")
            preview = replay(root, row, module, fields)
            if snapshot(owner, row, module)[2]["revision"] != value["revision"]:
                raise ValueError(
                    "Synthetic source or implementation changed during replay"
                )
            reference = "proposal-" + stamp(proposal)
            if any(s["stage_ref"] == reference for s in state["stages"]):
                raise ValueError(
                    "This private proposal already exists; inspect its retained stage"
                )
            stage = {
                "stage_ref": reference,
                "proposal": proposal,
                "preview_state": preview,
                "professional_validation": False,
                "public_history_changed": False,
            }
            stage["sha256"] = stamp(stage)
            updated = {
                **state,
                "generation": state["generation"] + 1,
                "stages": [*state["stages"], stage],
            }
            bounded(updated)
        elif action == "adopt":
            if (
                any(args[k] != page[k] for k in ("revision", "source_ref"))
                or args["confirmed"] is not True
                or args["expected_public_draft_revision"] != stamp(public_draft)
                or public_draft["fields"] != EMPTY
            ):
                raise ValueError(
                    "Compare existing fields and separately confirm copying the proposal"
                )
            stage = next(
                (s for s in state["stages"] if s["stage_ref"] == args["stage_ref"]),
                None,
            )
            if stage is None:
                raise PermissionError("Choose an exact retained model proposal")
            fields = proposal_fields(stage["proposal"], value)
            updated = {
                **state,
                "generation": state["generation"] + 1,
                "status": "adopted",
            }
        else:
            raise ValueError("Unsupported synthetic authoring action")
        intent = {"request": args, "fingerprint": stamp(args), "status": "pending"}
        api.atomic_json(intent_path, intent)
        if action == "adopt":
            public_directory.mkdir(mode=0o700, parents=True, exist_ok=True)
            copied = {
                "generation": public_draft["generation"] + 1,
                "revision": page["revision"],
                "fields": fields,
            }
            api.atomic_json(public_directory / "draft.json", copied)
            intent["after_draft_revision"] = stamp(copied)
        api.atomic_json(base / "state.json", updated)
        result = {
            "saved": True,
            "stage_revision": stamp(updated),
            "status": updated["status"],
            "public_history_changed": False,
            "professional_validation": False,
        }
        if action == "stage":
            result["stage_ref"] = reference
        intent.update(
            status="completed",
            result=result,
            after_stage_revision=stamp(updated),
            receipt_sha256=stamp(result),
        )
        api.atomic_json(intent_path, intent)
        return result
