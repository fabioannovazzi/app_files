"""Owned complete model proposals, private previews and explicitly adopted SARI drafts."""

from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any

from native_bank_preparation import file_hash, tree_hash
from native_sari_intake import bounded
from native_sari_intake import snapshot as intake_snapshot

__all__ = ["dispatch", "audit_run"]


def stamp(value: Any) -> str:
    """Exact identities and receipts enforce authorization, never source relevance."""
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, ensure_ascii=False).encode()
    ).hexdigest()


def engine(root: Path, request: dict) -> dict:
    result = subprocess.run(
        [
            sys.executable,
            "-I",
            "-B",
            str(Path(__file__).with_name("native_sari_author_bridge.py")),
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
            result.stderr.strip().splitlines()[-1] or "Registry proposal refused"
        )
    return json.loads(result.stdout)


def audit_run(output: Path, api: Any) -> dict:
    """Open mandates and uncertain writes remain visible across actors and closure."""
    states = {}
    recovery, unfinished = False, False
    for directory in api.ui_state_directory(output, create=False).glob("sari-author-*"):
        if directory.is_symlink() or not directory.is_dir():
            raise ValueError("Invalid registry authoring directory")
        path = directory / "state.json"
        state = (
            api.read_json(path) if path.exists() else {"grants": [], "operations": []}
        )
        if len({row["key"] for row in state["operations"]}) != len(state["operations"]):
            raise ValueError("Registry authoring operation keys changed")
        for operation in state["operations"]:
            if operation["fingerprint"] != stamp(operation["request"]):
                raise ValueError("Registry authoring request changed")
            if operation["status"] not in {"pending", "complete"}:
                raise ValueError("Invalid registry authoring operation")
            recovery |= operation["status"] == "pending"
            if operation["status"] == "complete" and operation[
                "receipt_sha256"
            ] != stamp(operation["receipt"]):
                raise ValueError("Registry authoring receipt changed")
        known = set()
        for row in state["grants"]:
            reference = row["grant_ref"]
            if (
                not re.fullmatch(r"mandate-[0-9a-f]{64}", reference)
                or reference in known
            ):
                raise ValueError("Invalid registry mandate identity")
            known.add(reference)
            home = directory / reference
            if file_hash(home / "mandate.json") != row["mandate_sha256"]:
                raise ValueError("Registry mandate changed")
            if tree_hash(home / "initial-output") != row["initial_artifacts"]:
                raise ValueError("Registry preserved initial output changed")
            origin = next(
                (op for op in state["operations"] if op["key"] == row["operation_key"]),
                None,
            )
            if (
                origin is None
                or origin["status"] != "complete"
                or origin["request"]["action"] != "request"
                or origin["receipt"].get("grant_ref") != reference
            ):
                raise ValueError(
                    "Registry mandate lacks its completed authorization receipt"
                )
            if row["status"] not in {"open", "registered", "cancelled"}:
                raise ValueError("Invalid registry mandate status")
            unfinished |= row["status"] == "open"
            stages = set()
            for stage in row["stages"]:
                ref = stage["stage_ref"]
                if not re.fullmatch(r"proposal-[0-9a-f]{64}", ref) or ref in stages:
                    raise ValueError("Invalid registry proposal identity")
                stages.add(ref)
                if tree_hash(home / ref) != stage["artifacts"]:
                    raise ValueError("Registry private proposal or preview changed")
                operation = next(
                    (
                        op
                        for op in state["operations"]
                        if op["key"] == stage["operation_key"]
                    ),
                    None,
                )
                if (
                    operation is None
                    or operation["status"] != "complete"
                    or operation["request"]["action"] != "stage"
                    or operation["request"]["grant_ref"] != reference
                    or operation["receipt"].get("stage_ref") != ref
                    or operation["request"]["proposal_sha256"]
                    != stamp(api.read_json(home / ref / "proposal.json"))
                ):
                    raise ValueError(
                        "Registry proposal lacks its completed staging receipt"
                    )
            if row["status"] != "open" and not any(
                op["status"] == "complete"
                and op["request"]["action"]
                == ("register" if row["status"] == "registered" else "cancel")
                and op["request"]["grant_ref"] == reference
                for op in state["operations"]
            ):
                raise ValueError("Registry mandate closure lacks its completed receipt")
            recovery |= any(path.name not in stages for path in home.glob("proposal-*"))
        recovery |= any(path.name not in known for path in directory.glob("mandate-*"))
        for operation in state["operations"]:
            if operation["status"] != "complete":
                continue
            reference = operation["receipt"].get("grant_ref")
            if reference not in known:
                raise ValueError(
                    "Registry completed receipt lost its conserved mandate"
                )
            if operation["request"]["action"] == "stage" and not any(
                stage["stage_ref"] == operation["receipt"].get("stage_ref")
                for row in state["grants"]
                if row["grant_ref"] == reference
                for stage in row["stages"]
            ):
                raise ValueError("Registry staging receipt lost its conserved proposal")
        states[directory.name] = state
    return {"states": states, "recovery_required": recovery, "unfinished": unfinished}


def snapshot(binding: dict, loaded: dict, root: Path, api: Any) -> dict:
    current = intake_snapshot(binding, loaded, root, api)
    audit = audit_run(current["output"], api)
    identity = {
        **current["identity"],
        "authoring_implementation": [
            file_hash(Path(__file__)),
            file_hash(Path(__file__).with_name("native_sari_author_bridge.py")),
            file_hash(Path(__file__).parents[1] / "mcp/workspace.cjs"),
        ],
    }
    owner = [
        *identity["owner"],
        binding["client_id"],
        binding["engagement_id"],
        binding["run_id"],
    ]
    home = api.ui_state_directory(current["output"], create=False) / (
        "sari-author-" + stamp(owner)
    )
    state = audit["states"].get(home.name, {"grants": [], "operations": []})
    path = home / "draft.json"
    draft = (
        api.read_json(path)
        if path.exists()
        else {
            "identity": identity,
            "generation": 0,
            "fields": {"question": "", "input_ids": []},
        }
    )
    sources = [
        {
            "input_id": row["binding_id"],
            "name": Path(row["execution_relative_path"])
            .relative_to("inputs")
            .as_posix(),
            "path": str(Path(loaded["run_root"]) / row["execution_relative_path"]),
            "sha256": row["sha256"],
        }
        for row in loaded["input_manifest"]["inputs"]
    ]
    running = loaded["run"]["status"] == "running" and "REVIEWER" in os.environ.get(
        "VERA_WORKSPACE_ROLES", ""
    ).split(",")
    clean = not (current["recovery_required"] or audit["recovery_required"])
    initial = current["inventory"] is not None and not any(
        name in current["files"]
        for name in (
            "official_sources.json",
            "practice_validation_audit.json",
            "review_payload.json",
            "final_artifacts.json",
        )
    )
    return {
        **current,
        "identity": identity,
        "revision": stamp(identity),
        "home": home,
        "state": state,
        "draft": draft,
        "draft_revision": stamp(draft),
        "draft_stale": draft["identity"] != identity,
        "sources": sources,
        "can_write": running and clean,
        "can_author": running and clean and initial,
        "recovery_required": not clean,
    }


def fields(value: Any, sources: list[dict], *, complete: bool = False) -> dict:
    if not isinstance(value, dict) or set(value) != {"question", "input_ids"}:
        raise ValueError("Use literal question and explicitly selected original IDs")
    if (
        not isinstance(value["question"], str)
        or len(value["question"]) > 4000
        or complete
        and not value["question"].strip()
    ):
        raise ValueError("Describe the actual registry work to prepare")
    identities = value["input_ids"]
    if (
        not isinstance(identities, list)
        or len(identities) > 1000
        or any(not isinstance(v, str) for v in identities)
        or len(set(identities)) != len(identities)
        or set(identities) - {row["input_id"] for row in sources}
    ):
        raise PermissionError("Original selection leaves this exact registry run")
    return value


def dispatch(
    tool: str, args: dict, binding: dict, loaded: dict, root: Path, api: Any
) -> dict:
    """Model semantics, private literal choices and confirmed public conservation stay separate."""
    if binding["workflow_id"] != root.name or root.name != "registro-imprese-sari":
        raise PermissionError("Registry authoring belongs to another workflow")
    action = tool.removeprefix("vera_workspace_sari_author_")
    current = snapshot(binding, loaded, root, api)
    base = {
        "work_ref": binding["work_ref"],
        "revision": current["revision"],
        "run_status": loaded["run"]["status"],
        "can_write": current["can_write"],
        "can_author": current["can_author"],
        "recovery_required": current["recovery_required"],
        "draft_revision": current["draft_revision"],
        "draft_stale": current["draft_stale"],
        "fields": current["draft"]["fields"],
        "actual_model_reads_verified": False,
    }
    if action == "setup":
        return bounded(
            {
                **base,
                "sources": [
                    {k: row[k] for k in ("input_id", "name", "sha256")}
                    for row in current["sources"]
                ],
                "grants": [
                    {key: row[key] for key in ("grant_ref", "question", "status")}
                    for row in current["state"]["grants"]
                ],
            }
        )
    row = next(
        (
            row
            for row in current["state"]["grants"]
            if row["grant_ref"] == args.get("grant_ref")
        ),
        None,
    )
    mandate, selected = None, []
    if row is not None:
        mandate = api.read_json(current["home"] / row["grant_ref"] / "mandate.json")
        selected = [
            source
            for source in current["sources"]
            if source["input_id"] in mandate["fields"]["input_ids"]
        ]
    if action in {"read", "context", "stage", "register", "cancel"} and row is None:
        raise PermissionError("Choose a mandate owned by this actor and exact run")
    obsolete = mandate is not None and mandate["identity"] != current["identity"]
    stage = (
        next(
            (
                stage
                for stage in row["stages"]
                if stage["stage_ref"] == args.get("stage_ref")
            ),
            None,
        )
        if row
        else None
    )
    if action == "read":
        if args.get("stage_ref") and stage is None:
            raise PermissionError("Choose one proposal from this exact mandate")
        result = {
            **base,
            "grant_ref": row["grant_ref"],
            "status": row["status"],
            "question": row["question"],
            "obsolete": obsolete,
            "stages": [
                {
                    key: item[key]
                    for key in ("stage_ref", "audit_status", "blocker_count")
                }
                for item in row["stages"]
            ],
        }
        if stage is not None:
            home = current["home"] / row["grant_ref"] / stage["stage_ref"]
            result.update(
                stage_ref=stage["stage_ref"],
                source_ref=stage["stage_ref"],
                data={"selection": {"source_ref": stage["stage_ref"]}},
                proposal=api.read_json(home / "proposal.json"),
                preview=api.read_json(home / "preview-result.json"),
                checklist=(
                    (home / "preview/studio_checklist.md").read_text()
                    if (home / "preview/studio_checklist.md").exists()
                    else None
                ),
            )
        return bounded(result)
    if action == "context":
        if (
            args["revision"] != current["revision"]
            or obsolete
            or not current["can_author"]
            or row["status"] != "open"
        ):
            raise ValueError(
                "Registry mandate changed, closed or lacks current authoring authority"
            )
        return bounded(
            {
                "work_ref": binding["work_ref"],
                "grant_ref": row["grant_ref"],
                "revision": current["revision"],
                "question": row["question"],
                "initial_case": api.read_json(
                    current["output"] / "case_intake_draft.json"
                ),
                "initial_plan": api.read_json(
                    current["output"] / "practice_plan_draft.json"
                ),
                "selected_originals": selected,
                "public_skill": str(root / "skills/registro-imprese-sari/SKILL.md"),
                "schemas": {
                    name: json.loads(
                        (root / "schemas" / (name + ".schema.json")).read_bytes()
                    )
                    for name in ("case_intake", "practice_plan")
                },
                "untrusted_evidence": True,
                "actual_model_reads_verified": False,
                "professional_decisions": "pending_only",
                "source_registration_fields": [
                    "source_id",
                    "source_type",
                    "title",
                    "official_url",
                    "publisher",
                    "territorial_applicability",
                    "updated_date",
                    "snapshot_input_id",
                ],
                "source_copy_boundary": "Only an explicitly selected registered original can be proposed as a user-provided source copy; no native fetch, permission invention or undocumented connector.",
            },
            64_000,
        )
    if action not in {"draft_save", "request", "stage", "register", "cancel"}:
        raise ValueError("Unsupported registry authoring action")
    if not current["can_write"]:
        raise PermissionError("Registry authoring is readonly or requires recovery")
    proposed = (
        fields(args["fields"], current["sources"], complete=action == "request")
        if action in {"draft_save", "request"}
        else None
    )
    request = {
        "action": action,
        "grant_ref": args.get("grant_ref"),
        "revision": args["revision"],
        "fields": proposed,
        "stage_ref": args.get("stage_ref"),
        "reviewer": args.get("reviewer"),
        "source_ids": args.get("source_ids"),
        "proposal_sha256": stamp(args["proposal"]) if action == "stage" else None,
        "expected_draft_revision": args.get("expected_draft_revision"),
    }
    key = args.get("idempotency_key")
    if action != "draft_save":
        if not isinstance(key, str) or not 1 <= len(key) <= 200:
            raise ValueError("Use an exact registry operation key")
        previous = next(
            (op for op in current["state"]["operations"] if op["key"] == key), None
        )
        if previous is not None:
            if previous["request"] != request or previous["status"] != "complete":
                raise ValueError("Registry retry differs or has an uncertain outcome")
            return previous["receipt"]
    if args["revision"] != current["revision"]:
        raise ValueError("Registry originals or public case changed; reopen")
    if (
        action in {"draft_save", "request"}
        and args["expected_draft_revision"] != current["draft_revision"]
    ):
        raise ValueError("Registry private question changed; reopen")
    if action != "cancel" and not current["can_author"]:
        raise ValueError("This registry case requires ordinary continuation")
    if action in {"context", "stage", "register"} and (
        obsolete or row["status"] != "open"
    ):
        raise ValueError("Registry mandate is obsolete or closed")
    if (
        action in {"request", "register", "cancel"}
        and args.get("confirmed") is not True
    ):
        raise PermissionError("Renew the explicit registry confirmation")
    if action == "request" and (
        current["draft_stale"] or current["draft"]["fields"] != proposed
    ):
        raise ValueError(
            "Authorize only the exact saved registry question and originals"
        )
    if action == "stage" and len(json.dumps(args["proposal"]).encode()) > 96_000:
        raise ValueError(
            "Complete registry proposal exceeds the native bound; use ordinary files"
        )
    if action == "cancel" and row["status"] != "open":
        raise ValueError("Only an open registry mandate can be cancelled")
    if action == "register":
        if (
            stage is None
            or stage["audit_status"] == "schema_error"
            or args["source_ref"] != stage["stage_ref"]
        ):
            raise ValueError("Select one mechanically valid whole registry proposal")
        body = api.read_json(
            current["home"] / row["grant_ref"] / stage["stage_ref"] / "proposal.json"
        )
        if (
            not isinstance(args["source_ids"], list)
            or set(args["source_ids"])
            != {item["source_id"] for item in body["sources"]}
            or len(args["source_ids"]) != len(body["sources"])
        ):
            raise PermissionError(
                "Explicitly choose every source used by the whole proposal"
            )
        if (
            not isinstance(args["reviewer"], str)
            or not args["reviewer"].strip()
            or len(args["reviewer"]) > 120
        ):
            raise ValueError("Declare the actual source selector before conservation")
    if action == "stage":
        # Exercise the maintained mechanical contracts away from the actual run.
        # Expected invalid proposals cannot leave a public-write intent behind.
        with tempfile.TemporaryDirectory(prefix="vera-sari-preflight-") as temporary:
            engine(
                root,
                {
                    "operation": "preview",
                    "context": str(loaded["context_path"]),
                    "grant_ref": row["grant_ref"],
                    "proposal": args["proposal"],
                    "selected_inputs": selected,
                    "destination": str(Path(temporary).resolve() / "preview"),
                },
            )
    with api.write_lock(current["output"]):
        newest = snapshot(binding, api.load_binding(binding), root, api)
        if (
            newest["revision"] != current["revision"]
            or newest["draft_revision"] != current["draft_revision"]
            or newest["state"] != current["state"]
        ):
            raise ValueError("Registry authoring changed before write")
        current["home"].mkdir(mode=0o700, exist_ok=True)
        if action == "draft_save":
            saved = {
                "identity": current["identity"],
                "generation": current["draft"]["generation"] + 1,
                "fields": proposed,
            }
            api.atomic_json(current["home"] / "draft.json", saved)
            return {
                **base,
                "saved": True,
                "fields": proposed,
                "draft_revision": stamp(saved),
                "draft_stale": False,
                "status": "private_question_saved",
            }
        operation = {
            "key": key,
            "request": request,
            "fingerprint": stamp(request),
            "status": "pending",
        }
        state = current["state"]
        state["operations"].append(operation)
        bounded(state, 1_000_000)
        state_path = current["home"] / "state.json"
        api.atomic_json(state_path, state)
        if action == "request":
            ref = "mandate-" + stamp([current["identity"], proposed, key])
            home = current["home"] / ref
            home.mkdir(mode=0o700)
            mandate = {"identity": current["identity"], "fields": proposed}
            api.atomic_json(home / "mandate.json", mandate)
            shutil.copytree(current["output"], home / "initial-output")
            state["grants"].append(
                {
                    "grant_ref": ref,
                    "mandate_sha256": file_hash(home / "mandate.json"),
                    "initial_artifacts": tree_hash(home / "initial-output"),
                    "operation_key": key,
                    "question": proposed["question"],
                    "status": "open",
                    "stages": [],
                }
            )
            result = {
                "work_ref": binding["work_ref"],
                "grant_ref": ref,
                "status": "open",
                "revision": current["revision"],
            }
        elif action == "cancel":
            row["status"] = "cancelled"
            result = {
                "work_ref": binding["work_ref"],
                "grant_ref": row["grant_ref"],
                "status": "cancelled",
                "public_case_unchanged": True,
            }
        else:
            home = current["home"] / row["grant_ref"]
            if action == "stage":
                reference = "proposal-" + stamp(
                    [row["grant_ref"], args["proposal"], key]
                )
                directory = home / reference
                directory.mkdir(mode=0o700)
                api.atomic_json(directory / "proposal.json", args["proposal"])
                preview = engine(
                    root,
                    {
                        "operation": "preview",
                        "context": str(loaded["context_path"]),
                        "grant_ref": row["grant_ref"],
                        "proposal": args["proposal"],
                        "selected_inputs": selected,
                        "destination": str(directory / "preview"),
                    },
                )
                api.atomic_json(directory / "preview-result.json", preview)
                record = {
                    "stage_ref": reference,
                    "operation_key": key,
                    "audit_status": preview["audit"]["status"],
                    "blocker_count": preview["audit"]["blocker_count"],
                    "artifacts": tree_hash(directory),
                }
                row["stages"].append(record)
                result = {
                    "work_ref": binding["work_ref"],
                    "grant_ref": row["grant_ref"],
                    **{
                        k: record[k]
                        for k in ("stage_ref", "audit_status", "blocker_count")
                    },
                    "public_outputs_registered": False,
                    "actual_model_reads_verified": False,
                }
            else:
                outcome = engine(
                    root,
                    {
                        "operation": "register",
                        "context": str(loaded["context_path"]),
                        "grant_ref": row["grant_ref"],
                        "proposal": body,
                        "selected_inputs": selected,
                        "source_ids": args["source_ids"],
                        "reviewer": args["reviewer"],
                    },
                )
                if outcome["final_artifacts"] is None:
                    raise ValueError(
                        "Registry conservation has an uncertain validation outcome; recover ordinarily"
                    )
                row["status"] = "registered"
                result = {
                    "work_ref": binding["work_ref"],
                    "grant_ref": row["grant_ref"],
                    "stage_ref": stage["stage_ref"],
                    "status": outcome["final_artifacts"]["status"],
                    "ready_to_file": False,
                    "professional_review_required": True,
                    "artifacts": tree_hash(current["output"]),
                    "actual_model_reads_verified": False,
                }
        operation.update(
            status="complete", receipt=result, receipt_sha256=stamp(result)
        )
        api.atomic_json(state_path, state)
        return bounded(result)
