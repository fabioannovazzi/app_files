"""Owned task mandates and explicit decisions over public grant intelligence."""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

from native_bandi import snapshot as dossier_snapshot
from native_bandi import stamp
from native_bank_preparation import file_hash, tree_hash

__all__ = ["dispatch", "audit_run"]

LIMIT = 2_000_000


def bounded(value: Any) -> Any:
    """Complete task contexts fail closed instead of taking arbitrary first rows."""
    if len(json.dumps(value, ensure_ascii=False).encode()) > LIMIT:
        raise ValueError("Complete grant contribution exceeds its boundary")
    return value


def engine(root: Path, request: dict) -> dict:
    bounded(request)
    result = subprocess.run(
        [
            sys.executable,
            "-I",
            "-B",
            str(Path(__file__).with_name("native_bandi_intelligence_bridge.py")),
            str(root),
        ],
        input=json.dumps(request, ensure_ascii=False),
        text=True,
        capture_output=True,
        check=False,
        timeout=90,
    )
    if result.returncode:
        raise ValueError(
            result.stderr.strip().splitlines()[-1] or "Grant contribution refused"
        )
    return bounded(json.loads(result.stdout))


def audit_run(output: Path, api: Any) -> dict:
    """All actors' mandates, retained bytes and uncertain writes govern closure."""
    states = {}
    pending = recovery = False
    for home in api.ui_state_directory(output, create=False).glob("bandi-author-*"):
        if home.is_symlink() or not home.is_dir():
            raise ValueError("Invalid private grant authoring directory")
        state = (
            api.read_json(home / "state.json")
            if (home / "state.json").exists()
            else {"grants": [], "operations": []}
        )
        keys = set()
        retained_refs = set()
        for operation in state["operations"]:
            if operation["key"] in keys or operation["fingerprint"] != stamp(
                operation["request"]
            ):
                raise ValueError("Grant authoring intent changed")
            keys.add(operation["key"])
            if operation["status"] not in {"pending", "complete"}:
                raise ValueError("Invalid grant authoring operation state")
            recovery |= operation["status"] == "pending"
            if operation["status"] == "complete" and operation[
                "receipt_sha256"
            ] != stamp(operation["receipt"]):
                raise ValueError("Grant authoring receipt changed")
            retained = operation.get("snapshot_ref")
            if retained:
                if (
                    retained
                    != "operation-" + stamp([operation["key"], operation["request"]])
                    or retained in retained_refs
                    or tree_hash(home / retained) != operation["request"]["before"]
                ):
                    raise ValueError("Grant authoring prior bytes changed")
                retained_refs.add(retained)
        recovery |= any(
            path.name not in retained_refs for path in home.glob("operation-*")
        )
        references = set()
        for grant in state["grants"]:
            reference = grant["grant_ref"]
            if (
                not re.fullmatch(r"mandate-[0-9a-f]{64}", reference)
                or reference in references
            ):
                raise ValueError("Invalid grant contribution mandate")
            references.add(reference)
            directory = home / reference
            mandate = api.read_json(directory / "mandate.json")
            origin = next(
                (
                    row
                    for row in state["operations"]
                    if row["key"] == grant["operation_key"]
                ),
                None,
            )
            if (
                origin is None
                or origin["status"] != "complete"
                or origin["receipt"].get("grant_ref") != reference
            ):
                raise ValueError("Grant contribution lacks completed authorization")
            if origin["request"][
                "action"
            ] != "request" or reference != "mandate-" + stamp(
                [mandate["identity"], mandate["fields"], origin["key"]]
            ):
                raise ValueError("Grant mandate differs from its literal authorization")
            if (
                origin["request"]["owner"] != mandate["identity"]["owner"]
                or origin["request"]["binding"] != mandate["identity"]["binding"]
                or origin["request"]["args"]["fields"] != mandate["fields"]
            ):
                raise ValueError("Grant mandate ownership or scope changed")
            if home.name != "bandi-author-" + stamp(mandate["identity"]["owner"]):
                raise ValueError("Grant mandate actor identity changed")
            if (
                file_hash(directory / "mandate.json") != grant["mandate_sha256"]
                or file_hash(directory / "packet.json") != grant["packet_file_sha256"]
            ):
                raise ValueError("Authorized grant task or packet changed")
            if (
                stamp(api.read_json(directory / "packet.json"))
                != grant["packet_sha256"]
                or tree_hash(directory / "initial-output") != grant["initial_artifacts"]
            ):
                raise ValueError("Grant initial case evidence changed")
            if grant["status"] not in {
                "open",
                "recorded",
                "decided",
                "cancelled",
                "stale",
            }:
                raise ValueError("Invalid grant contribution status")
            pending |= grant["status"] in {"open", "recorded"}
            stages = set()
            for stage in grant["stages"]:
                ref = stage["stage_ref"]
                if (
                    not re.fullmatch(r"proposal-[0-9a-f]{64}", ref)
                    or ref in stages
                    or tree_hash(directory / ref) != stage["artifacts"]
                ):
                    raise ValueError("Grant proposal preview changed")
                stages.add(ref)
                op = next(
                    (
                        row
                        for row in state["operations"]
                        if row["key"] == stage["operation_key"]
                    ),
                    None,
                )
                if (
                    op is None
                    or op["status"] != "complete"
                    or op["receipt"].get("stage_ref") != ref
                ):
                    raise ValueError("Grant proposal lacks its completed stage receipt")
                staged_args = op["request"]["args"]
                if (
                    op["request"]["action"] != "stage"
                    or staged_args["grant_ref"] != reference
                    or ref
                    != "proposal-"
                    + stamp(
                        [
                            reference,
                            staged_args["proposal"],
                            staged_args["metadata"],
                            op["key"],
                        ]
                    )
                ):
                    raise ValueError("Grant proposal authorization changed")
                if (
                    api.read_json(directory / ref / "proposal.json")
                    != staged_args["proposal"]
                    or api.read_json(directory / ref / "metadata.json")
                    != staged_args["metadata"]
                ):
                    raise ValueError(
                        "Grant proposal differs from declared model provenance"
                    )
            recovery |= any(
                path.name not in stages for path in directory.glob("proposal-*")
            )
            if grant["status"] in {"recorded", "decided", "stale"}:
                public = api.read_json(output / "intelligence_register.json")
                selected = [
                    row
                    for row in public["runs"]
                    if row["intelligence_run_id"] == grant["intelligence_run_id"]
                ]
                completed = next(
                    (
                        row
                        for row in state["operations"]
                        if row["key"] == grant["public_operation_key"]
                    ),
                    None,
                )
                if (
                    len(selected) != 1
                    or completed is None
                    or completed["status"] != "complete"
                    or stamp(selected[0]) != grant["public_record_sha256"]
                    or stamp(
                        {
                            key: value
                            for key, value in completed["receipt"].items()
                            if key != "files"
                        }
                    )
                    != grant["public_record_sha256"]
                ):
                    raise ValueError(
                        "Public grant suggestion differs from its completed receipt"
                    )
                allowed = {
                    "recorded": {"MODEL_SUGGESTED"},
                    "decided": {"ACCEPTED", "REJECTED", "RETURNED"},
                    "stale": {"STALE"},
                }
                if selected[0]["status"] not in allowed[grant["status"]]:
                    raise ValueError("Public grant suggestion disposition changed")
        recovery |= any(path.name not in references for path in home.glob("mandate-*"))
        states[home.name] = state
    return {"states": states, "pending": pending, "recovery_required": recovery}


def fields(value: Any) -> dict:
    """Retain only declared task selectors; never infer scope or a fresh session."""
    if not isinstance(value, dict) or set(value) != {
        "task",
        "subject_ids",
        "model_session_ref",
        "raw_source_ids",
    }:
        raise ValueError("Use the complete grant task selection")
    for name in ("task", "model_session_ref"):
        if not isinstance(value[name], str) or len(value[name]) > 80:
            raise ValueError("Invalid grant task field")
    for name in ("subject_ids", "raw_source_ids"):
        ids = value[name]
        if (
            not isinstance(ids, list)
            or len(ids) > 500
            or any(
                not isinstance(item, str)
                or not re.fullmatch(r"[A-Za-z0-9_.-]{1,80}", item)
                for item in ids
            )
            or len(set(ids)) != len(ids)
        ):
            raise ValueError("Choose unique exact grant source and subject IDs")
    return value


def snapshot(binding: dict, loaded: dict, root: Path, api: Any) -> dict:
    public = dossier_snapshot(binding, loaded, root, "dossier", api)
    audit = audit_run(public["output"], api)
    owner = [
        os.environ["VERA_WORKSPACE_TENANT_ID"],
        os.environ["VERA_WORKSPACE_ACTOR_ID"],
    ]
    home = api.ui_state_directory(public["output"], create=False) / (
        "bandi-author-" + stamp(owner)
    )
    state = audit["states"].get(home.name, {"grants": [], "operations": []})
    identity = {
        "owner": owner,
        "binding": binding,
        "inputs": loaded["input_manifest"],
        "run_status": loaded["run"]["status"],
        "case_hashes": {
            name: public["public"]["record_hashes"].get(name)
            for name in ("case_intake", "source_register", "application_workbench")
        },
        "implementation": {
            "public": public["identity"]["implementation"],
            "authoring": {
                p.name: file_hash(p)
                for p in (
                    Path(__file__),
                    Path(__file__).with_name("native_bandi_intelligence_bridge.py"),
                    Path(__file__).with_name("native_bandi_decision_drafts.py"),
                    Path(__file__).parents[1] / "ui/bandi-contributions.js",
                )
            },
        },
    }
    identity = json.loads(json.dumps(identity))
    empty = {
        "task": "",
        "subject_ids": [],
        "model_session_ref": "",
        "raw_source_ids": [],
    }
    draft = (
        api.read_json(home / "draft.json")
        if (home / "draft.json").exists()
        else {"identity": identity, "generation": 0, "fields": empty}
    )
    fields(draft["fields"])
    return {
        "public": public,
        "identity": identity,
        "case_ref": stamp(identity),
        "revision": stamp([identity, public["revision"], state]),
        "source_ref": public["source_ref"],
        "home": home,
        "state": state,
        "draft": draft,
        "draft_revision": stamp(draft),
        "draft_stale": draft["identity"] != identity,
        "can_write": public["can_write"] and not audit["recovery_required"],
        **audit,
    }


def view(current: dict, binding: dict, root: Path) -> dict:
    records = current["public"]["public"]["records"]
    return bounded(
        {
            "work_ref": binding["work_ref"],
            "revision": current["revision"],
            "source_ref": current["source_ref"],
            "data": {"selection": {"source_ref": current["source_ref"]}},
            "fields": current["draft"]["fields"],
            "draft_revision": current["draft_revision"],
            "draft_stale": current["draft_stale"],
            "can_write": current["can_write"],
            "confirmation_restored": False,
            "tasks": engine(root, {"operation": "describe"})["tasks"],
            "sources": [
                {
                    key: row[key]
                    for key in ("source_id", "source_type", "title", "sha256")
                }
                for row in records.get("source_register", {}).get("sources", [])
            ],
            "grants": [
                {
                    **{
                        key: row[key]
                        for key in ("grant_ref", "status", "task", "stages")
                    },
                    "intelligence_run_id": row.get("intelligence_run_id"),
                }
                for row in current["state"]["grants"]
            ],
            "public_suggestions": records.get("intelligence_register", {}).get(
                "runs", []
            ),
            "actual_model_reads_verified": False,
            "fresh_session_assurance": "operator_asserted_not_provider_authenticated",
        }
    )


def dispatch(
    tool: str, args: dict, binding: dict, loaded: dict, root: Path, api: Any
) -> dict:
    """Mechanics preserve task provenance; the model and professional decide meaning."""
    if (
        binding["workflow_id"] != "bandi-agevolazioni"
        or binding["component"] != "bandi-agevolazioni"
    ):
        raise PermissionError("Selected work is not a grant dossier")
    action = tool.removeprefix("vera_workspace_bandi_author_")
    current = snapshot(binding, loaded, root, api)
    if action == "setup":
        return view(current, binding, root)
    request = {
        "action": action,
        "owner": current["identity"]["owner"],
        "binding": binding,
        "args": {key: value for key, value in args.items() if key != "review_ticket"},
    }
    key = args.get("idempotency_key")
    if key is not None:
        for op in current["state"]["operations"]:
            if op["key"] == key:
                if {
                    name: value
                    for name, value in op["request"].items()
                    if name != "before"
                } != request or op["status"] != "complete":
                    raise ValueError(
                        "Grant contribution retry conflicts or needs recovery"
                    )
                return op["receipt"]
    if (
        args["revision"] != current["revision"]
        or args["source_ref"] != current["source_ref"]
    ):
        raise ValueError("Grant contribution view changed; reopen the current task")
    grant = next(
        (
            row
            for row in current["state"]["grants"]
            if row["grant_ref"] == args.get("grant_ref")
        ),
        None,
    )
    if action not in {"draft_save", "request"} and grant is None:
        raise PermissionError("Grant mandate belongs to another actor or case")
    home = current["home"] / grant["grant_ref"] if grant else None
    mandate = api.read_json(home / "mandate.json") if home else None
    common = {
        "context": str(loaded["context_path"]),
        "expected_files": current["public"]["public"]["files"],
    }
    if action in {"context", "source", "stage", "record"}:
        if (
            not current["can_write"]
            or grant["status"] != "open"
            or mandate["identity"] != current["identity"]
        ):
            raise ValueError(
                "Grant mandate is closed or stale; obtain a new contribution"
            )
    if action == "read":
        selected = next(
            (row for row in grant["stages"] if row["stage_ref"] == args["stage_ref"]),
            None,
        )
        if selected is None:
            raise ValueError("Select one retained private contribution")
        directory = home / selected["stage_ref"]
        return bounded(
            {
                "grant_ref": grant["grant_ref"],
                "stage_ref": selected["stage_ref"],
                "status": grant["status"],
                "proposal": api.read_json(directory / "proposal.json"),
                "normalized_output": api.read_json(directory / "normalized.json"),
                "metadata": api.read_json(directory / "metadata.json"),
                "public_case_changed": False,
            }
        )
    if action == "context":
        packet = api.read_json(home / "packet.json")
        return bounded(
            {
                "work_ref": binding["work_ref"],
                "grant_ref": grant["grant_ref"],
                "revision": current["revision"],
                "source_ref": current["source_ref"],
                "packet": packet,
                "packet_sha256": grant["packet_sha256"],
                "raw_source_ids": mandate["fields"]["raw_source_ids"],
                "actual_model_reads_verified": False,
                "untrusted_evidence": True,
            }
        )
    if action == "source":
        if args["source_id"] not in mandate["fields"]["raw_source_ids"]:
            raise PermissionError(
                "This raw source was not explicitly selected for the task"
            )
        return engine(
            root, {**common, "operation": "source", "source_id": args["source_id"]}
        )
    if not current["can_write"]:
        raise PermissionError("Grant contribution is read-only or requires recovery")
    if action == "draft_save":
        if args["expected_draft_revision"] != current["draft_revision"]:
            raise ValueError("Grant task draft changed")
        proposed = fields(args["fields"])
    elif action in {"request", "record", "decide", "cancel", "expire"}:
        if args.get("confirmed") is not True:
            raise ValueError("Confirm this exact grant contribution action")
    if action == "request":
        proposed = fields(args["fields"])
        if current["draft_stale"]:
            raise ValueError(
                "Inspect and explicitly resave the task fields on the current dossier"
            )
        if (
            proposed != current["draft"]["fields"]
            or args["expected_draft_revision"] != current["draft_revision"]
        ):
            raise ValueError("Save and inspect the exact grant task fields first")
        if not re.fullmatch(r"[A-Za-z0-9_.-]{8,80}", proposed["model_session_ref"]):
            raise ValueError(
                "Declare a fresh operator-attested model session reference"
            )
        if args.get("fresh_session_confirmed") is not True:
            raise ValueError("Explicitly attest a separate fresh model session")
        if any(
            row["model_metadata"]["model_session_ref"] == proposed["model_session_ref"]
            for row in current["public"]["public"]["records"]["intelligence_register"][
                "runs"
            ]
        ):
            raise ValueError(
                "This model session reference already belongs to a public contribution"
            )
        for state in current["states"].values():
            for prior in state["grants"]:
                if (
                    api.read_json(
                        current["home"].parent
                        / ("bandi-author-" + stamp(prior["owner"]))
                        / prior["grant_ref"]
                        / "mandate.json"
                    )["fields"]["model_session_ref"]
                    == proposed["model_session_ref"]
                ):
                    raise ValueError(
                        "This grant session reference was already authorized"
                    )
        packet_result = engine(
            root,
            {
                **common,
                "operation": "packet",
                **{
                    name: proposed[name]
                    for name in ("task", "subject_ids", "model_session_ref")
                },
            },
        )
        available = {
            row["source_id"]: row
            for row in current["public"]["public"]["records"]["source_register"][
                "sources"
            ]
        }
        packet_ids = {
            row["source_id"]
            for row in packet_result["packet"]["untrusted_evidence"]["sources"]
        }
        policy = packet_result["packet"]["session_boundary"]["raw_evidence_access"]
        # Declared source types enforce the public data boundary, never authority.
        allowed_types = (
            {
                "call",
                "formal_amendment",
                "annex",
                "official_faq",
                "portal_instructions",
                "form_template",
                "incorporated_law",
            }
            if policy == "selected_official_sources_only"
            else (
                {"beneficiary_evidence", "quotation"}
                if policy == "selected_client_evidence_only"
                else set()
            )
        )
        if any(
            identifier not in packet_ids
            or available[identifier]["source_type"] not in allowed_types
            for identifier in proposed["raw_source_ids"]
        ):
            raise PermissionError(
                "Raw source selection violates this task's declared data boundary"
            )
    stage = (
        next(
            (
                row
                for row in grant["stages"]
                if row["stage_ref"] == args.get("stage_ref")
            ),
            None,
        )
        if grant
        else None
    )
    if action in {"stage", "record"}:
        selection = {
            name: mandate["fields"][name]
            for name in ("task", "subject_ids", "model_session_ref")
        }
        if action == "stage":
            metadata = args["metadata"]
            if (
                set(metadata) != {"provider", "model", "prompt_template_version"}
                or any(
                    not isinstance(value, str) or not value.strip() or len(value) > 200
                    for value in metadata.values()
                )
                or metadata["prompt_template_version"]
                != engine(root, {"operation": "describe"})["contract_version"]
            ):
                raise ValueError(
                    "Declare the exact provider/model and maintained template"
                )
            validated = engine(
                root,
                {
                    **common,
                    **selection,
                    "operation": "validate",
                    "packet_sha256": grant["packet_sha256"],
                    "proposal": args["proposal"],
                },
            )
        elif stage is None:
            raise ValueError("Inspect one exact retained grant proposal")
    if action in {"decide", "expire"}:
        if grant["status"] != "recorded":
            raise ValueError(
                "Record the selected proposal before professional disposition"
            )
        engine(
            root,
            {
                **common,
                "operation": "preflight_" + action,
                "intelligence_run_id": grant["intelligence_run_id"],
                "fields": args["fields"],
            },
        )
    if action == "cancel" and grant["status"] != "open":
        raise ValueError(
            "A recorded public suggestion needs its separate professional decision"
        )
    if action not in {
        "draft_save",
        "request",
        "stage",
        "record",
        "decide",
        "cancel",
        "expire",
    }:
        raise ValueError("Unsupported grant authoring action")
    if action != "draft_save" and (
        not isinstance(key, str) or not 1 <= len(key) <= 200
    ):
        raise ValueError("Grant contribution needs a stable bounded idempotency key")
    with api.write_lock(current["public"]["output"]):
        newest = snapshot(binding, api.load_binding(binding), root, api)
        if (
            newest["revision"] != current["revision"]
            or newest["draft_revision"] != current["draft_revision"]
        ):
            raise ValueError("Grant contribution changed before write")
        current["home"].mkdir(mode=0o700, exist_ok=True)
        if action == "draft_save":
            saved = {
                "identity": current["identity"],
                "generation": current["draft"]["generation"] + 1,
                "fields": proposed,
            }
            api.atomic_json(current["home"] / "draft.json", saved)
            return {
                "saved": True,
                "draft_revision": stamp(saved),
                "confirmation_restored": False,
            }
        operation = {
            "key": key,
            "request": request,
            "fingerprint": stamp(request),
            "status": "pending",
        }
        state = current["state"]
        if action in {"record", "decide", "expire"}:
            request["before"] = common["expected_files"]
            retained = "operation-" + stamp([key, request])
            operation["snapshot_ref"] = retained
            operation["fingerprint"] = stamp(request)
            destination = current["home"] / retained
            destination.mkdir(mode=0o700)
            for name in common["expected_files"]:
                target = destination / name
                target.parent.mkdir(parents=True, mode=0o700, exist_ok=True)
                shutil.copyfile(current["public"]["output"] / name, target)
                target.chmod(0o600)
            if tree_hash(destination) != common["expected_files"]:
                raise ValueError("Grant prior bytes changed during preservation")
        state["operations"].append(operation)
        api.atomic_json(current["home"] / "state.json", state)
        if action == "request":
            reference = "mandate-" + stamp([current["identity"], proposed, key])
            directory = current["home"] / reference
            directory.mkdir(mode=0o700)
            api.atomic_json(
                directory / "mandate.json",
                {
                    "identity": current["identity"],
                    "fields": proposed,
                    "fresh_session_confirmed": True,
                },
            )
            api.atomic_json(directory / "packet.json", packet_result["packet"])
            initial = directory / "initial-output"
            initial.mkdir(mode=0o700)
            for name in common["expected_files"]:
                target = initial / name
                target.parent.mkdir(parents=True, mode=0o700, exist_ok=True)
                shutil.copyfile(current["public"]["output"] / name, target)
                target.chmod(0o600)
            if tree_hash(initial) != common["expected_files"]:
                raise ValueError("Grant initial output changed during preservation")
            state["grants"].append(
                {
                    "grant_ref": reference,
                    "owner": current["identity"]["owner"],
                    "task": proposed["task"],
                    "operation_key": key,
                    "status": "open",
                    "mandate_sha256": file_hash(directory / "mandate.json"),
                    "packet_sha256": packet_result["packet_sha256"],
                    "packet_file_sha256": file_hash(directory / "packet.json"),
                    "initial_artifacts": tree_hash(initial),
                    "stages": [],
                }
            )
            result = {
                "work_ref": binding["work_ref"],
                "grant_ref": reference,
                "status": "open",
                "actual_model_reads_verified": False,
            }
        elif action == "stage":
            reference = "proposal-" + stamp(
                [grant["grant_ref"], args["proposal"], metadata, key]
            )
            directory = home / reference
            directory.mkdir(mode=0o700)
            api.atomic_json(directory / "proposal.json", args["proposal"])
            api.atomic_json(
                directory / "normalized.json", validated["normalized_output"]
            )
            api.atomic_json(directory / "metadata.json", metadata)
            grant["stages"].append(
                {
                    "stage_ref": reference,
                    "operation_key": key,
                    "artifacts": tree_hash(directory),
                }
            )
            result = {
                "work_ref": binding["work_ref"],
                "grant_ref": grant["grant_ref"],
                "stage_ref": reference,
                "status": "private_proposal_retained",
                "public_case_changed": False,
                "normalized_output": validated["normalized_output"],
            }
        elif action == "record":
            directory = home / stage["stage_ref"]
            result = engine(
                root,
                {
                    **common,
                    **selection,
                    "operation": "record",
                    "proposal": api.read_json(directory / "proposal.json"),
                    "metadata": api.read_json(directory / "metadata.json"),
                    "packet_sha256": grant["packet_sha256"],
                    "recorded_by": current["identity"]["owner"][1],
                    "idempotency_key": "native-" + stamp([binding, key])[:64],
                },
            )
            grant.update(
                status="recorded", intelligence_run_id=result["intelligence_run_id"]
            )
        elif action in {"decide", "expire"}:
            result = engine(
                root,
                {
                    **common,
                    "operation": action,
                    "intelligence_run_id": grant["intelligence_run_id"],
                    "fields": args["fields"],
                    "confirmed": True,
                },
            )
            grant["status"] = "decided" if action == "decide" else "stale"
        else:
            grant["status"] = "cancelled"
            result = {
                "work_ref": binding["work_ref"],
                "grant_ref": grant["grant_ref"],
                "status": "cancelled",
                "public_case_changed": False,
            }
        if action in {"record", "decide", "expire"}:
            grant.update(
                public_operation_key=key,
                public_record_sha256=stamp(
                    {name: value for name, value in result.items() if name != "files"}
                ),
            )
        operation.update(
            status="complete", receipt=result, receipt_sha256=stamp(result)
        )
        api.atomic_json(current["home"] / "state.json", state)
        audit_run(current["public"]["output"], api)
        return result
