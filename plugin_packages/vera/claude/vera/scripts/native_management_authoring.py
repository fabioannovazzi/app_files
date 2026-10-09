"""Explicit original-source mandates and complete named Management case conservation.

Source identity, mechanical public contracts, CAS, scope and durable intent are
audit controls. Source roles, classification, drivers and business meaning remain
model and professional judgments. No semantic classifier or calculation runner.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from pathlib import Path
from typing import Any

from native_archive_navigation import archive_module, engagement_scope, work_ref
from native_bank_preparation import file_hash, tree_hash
from native_management_execution import bounded
from native_management_execution import context as calculation_context
from native_variance import offset, selected
from native_variance_review import fields as review_fields

__all__ = ["audit_authoring", "dispatch"]
FIELD_NAMES = {"question", "mode", "input_ids", "base_case_input_id"}


def choices(value: Any, loaded: dict, *, final: bool = False) -> dict:
    """Validate literal user source choices without assigning accounting meaning."""
    if (
        not isinstance(value, dict)
        or set(value) != FIELD_NAMES
        or value["mode"] not in {"", "reporting", "costing"}
    ):
        raise ValueError("Use complete literal Management preparation choices")
    if any(
        not isinstance(value[k], str) or len(value[k]) > 4000
        for k in FIELD_NAMES - {"input_ids"}
    ):
        raise ValueError("Invalid Management preparation text")
    ids = value["input_ids"]
    if (
        not isinstance(ids, list)
        or len(ids) > 1000
        or any(not isinstance(v, str) or not v for v in ids)
        or len(set(ids)) != len(ids)
    ):
        raise ValueError("Select distinct original source receipt IDs")
    for identity in [
        *ids,
        *([value["base_case_input_id"]] if value["base_case_input_id"] else []),
    ]:
        selected(identity, loaded)
    if value["base_case_input_id"] in ids:
        raise ValueError("Keep the prior case separate from original sources")
    if (
        value["base_case_input_id"]
        and selected(value["base_case_input_id"], loaded)[0].suffix.lower() != ".json"
    ):
        raise ValueError("Choose a complete registered prior JSON case")
    if final and (not value["question"].strip() or not value["mode"] or not ids):
        raise ValueError(
            "Confirm the question, reporting/costing path and original sources"
        )
    return {**value, "input_ids": list(ids)}


def public(root: Path, request: dict) -> dict:
    """Use current public inspection and schema contracts in an isolated process."""
    result = subprocess.run(
        [
            sys.executable,
            "-I",
            "-B",
            str(Path(__file__).with_name("native_management_author_bridge.py")),
            str(root),
        ],
        input=json.dumps(request),
        text=True,
        capture_output=True,
        check=False,
        timeout=90,
    )
    if result.returncode:
        raise ValueError(
            result.stderr.strip().splitlines()[-1] or "Management case contract refused"
        )
    return json.loads(result.stdout)


def audit_authoring(output: Path, api: Any) -> dict:
    """Check complete proposals, actual registered cases and uncertain side effects."""
    private = api.ui_state_directory(output, create=False)
    path = private / "management-author-state.json"
    state = api.read_json(path) if path.exists() else {"grants": [], "proposals": []}
    intakes, proposals, readbacks = set(), set(), set()
    for grant in state["grants"]:
        ref, intake = grant["grant_ref"], grant["intake_ref"]
        if (
            ref != "management-mandate-" + api.digest(grant["mandate"])
            or grant["status"] not in {"open", "registered", "cancelled"}
            or intake != "codex-management-intake-" + api.digest(grant["mandate"])
            or intake in intakes
            or tree_hash(output / intake) != grant["intake_artifacts"]
        ):
            raise ValueError("Management source mandate or complete intake changed")
        intakes.add(intake)
    for row in state["proposals"]:
        ref = row["case_ref"]
        grant = next(
            (g for g in state["grants"] if g["grant_ref"] == row["grant_ref"]), None
        )
        expected = {"case.json", "proposal_note.json", "validation.json"} | (
            {"prior_case.json"}
            if grant and grant["mandate"]["fields"]["base_case_input_id"]
            else set()
        )
        if (
            not re.fullmatch(r"management-authored-[a-f0-9]{64}", ref)
            or ref in proposals
            or grant is None
            or tree_hash(private / ref) != row["artifacts"]
            or {p.name for p in (private / ref).iterdir()} != expected
        ):
            raise ValueError("Management complete case proposal changed")
        proposals.add(ref)
        if "registration" not in row:
            continue
        saved = row["registration"]
        binding = saved["binding"]
        owner = grant["mandate"]["scope"]["owner"]
        if (
            grant["status"] != "registered"
            or [binding[k] for k in ("client_id", "engagement_id", "workflow_id")]
            != [owner[2], owner[3], owner[5]]
            or binding["run_id"] == owner[4]
        ):
            raise PermissionError(
                "Management successor is outside this same engagement"
            )
        receipt_ref = saved["receipt_ref"]
        if (
            not re.fullmatch(r"management-case-readback-[a-f0-9]{64}", receipt_ref)
            or receipt_ref in readbacks
            or tree_hash(private / receipt_ref) != saved["readback_artifacts"]
            or {p.name for p in (private / receipt_ref).iterdir()}
            != {"case.json", "case-readback.json"}
        ):
            raise ValueError("Management named case readback changed")
        readbacks.add(receipt_ref)
        hydrated = api.load_binding(binding)
        receipt = api.read_json(private / receipt_ref / "case-readback.json")
        if (
            receipt["scope"] != grant["mandate"]["scope"]
            or receipt["case_ref"] != ref
            or receipt["proposal_sha256"] != file_hash(private / ref / "case.json")
            or receipt["registered_case_sha256"]
            != file_hash(private / receipt_ref / "case.json")
            or receipt["fields"] != saved["fields"]
        ):
            raise ValueError("Management attribution and whole case disagree")
        for key, name in (
            ("recipe_input_id", "case.json"),
            ("review_input_id", "case-readback.json"),
        ):
            if file_hash(selected(saved[key], hydrated)[0]) != file_hash(
                private / receipt_ref / name
            ):
                raise ValueError("Registered Management case/readback bytes changed")
        if saved["input_ids"] != grant["mandate"]["fields"]["input_ids"]:
            raise ValueError("Management original source selection changed")
    for grant in state["grants"]:
        registered = [
            r
            for r in state["proposals"]
            if r["grant_ref"] == grant["grant_ref"] and "registration" in r
        ]
        if (grant["status"] == "registered") != (len(registered) == 1) or len(
            registered
        ) > 1:
            raise ValueError("Management mandate and successor disagree")
    requests = [
        api.read_json(p) for p in private.glob("management-author-request-*.json")
    ]
    if any(
        r["result"].get("case_ref") not in proposals
        for r in requests
        if "result" in r and "case_ref" in r["result"]
    ):
        raise ValueError("Management authoring request lost its complete case")
    return {
        "state": state,
        "private": private,
        "pending": any(g["status"] == "open" for g in state["grants"]),
        "recovery_required": any("result" not in r for r in requests)
        or any(p.name not in intakes for p in output.glob("codex-management-intake-*"))
        or any(p.name not in proposals for p in private.glob("management-authored-*"))
        or any(
            p.name not in readbacks for p in private.glob("management-case-readback-*")
        ),
    }


def snapshot(binding: dict, loaded: dict, root: Path, api: Any) -> dict:
    current = calculation_context(binding, loaded, root, api)
    audit = audit_authoring(current["output"], api)
    current["scope"] = {
        **current["stable"],
        "authoring": {
            name: file_hash(Path(__file__).with_name(name))
            for name in (
                "native_management_authoring.py",
                "native_management_author_bridge.py",
                "native_variance_review.py",
            )
        },
    }
    current.update(
        state=audit["state"],
        recovery_required=current["recovery_required"] or audit["recovery_required"],
    )
    current["revision"] = api.digest(
        [current["scope"], current["state"], loaded["run"]]
    )
    return current


def writable(current: dict, loaded: dict) -> bool:
    return (
        loaded["run"]["status"] == "running"
        and not current["recovery_required"]
        and "REVIEWER" in os.environ.get("VERA_WORKSPACE_ROLES", "").split(",")
    )


def draft(current: dict, loaded: dict, api: Any) -> tuple[Path, dict, str]:
    path = current["private"] / (
        "management-author-draft-" + api.digest(current["scope"]["owner"]) + ".json"
    )
    value = (
        api.read_json(path)
        if path.exists()
        else {
            "scope": current["scope"],
            "generation": 0,
            "fields": {
                "question": "",
                "mode": "",
                "input_ids": [],
                "base_case_input_id": "",
            },
        }
    )
    if value["scope"] != current["scope"]:
        raise PermissionError("Management question draft belongs to a changed scope")
    choices(value["fields"], loaded)
    return path, value, api.digest(value)


def page(
    current: dict,
    loaded: dict,
    root: Path,
    args: dict,
    api: Any,
    *,
    model: bool = False,
) -> dict:
    grant = next(
        (g for g in current["state"]["grants"] if g["grant_ref"] == args["grant_ref"]),
        None,
    )
    if grant is None or grant["mandate"]["scope"] != current["scope"]:
        raise PermissionError("Choose this exact owned Management source mandate")
    rows = [
        r for r in current["state"]["proposals"] if r["grant_ref"] == grant["grant_ref"]
    ]
    row = next((r for r in rows if r["case_ref"] == args.get("case_ref")), None)
    if args.get("case_ref") and row is None:
        raise ValueError("Choose a complete explicit case, never an implicit latest")
    result = {
        "work_ref": args["work_ref"],
        "grant_ref": grant["grant_ref"],
        "revision": api.digest([current["revision"], grant, rows]),
        "status": grant["status"],
        "mandate": grant["mandate"],
        "proposals": [{k: r[k] for k in ("case_ref", "validation")} for r in rows],
        "selection": {"id": row["case_ref"]} if row else None,
        "data": {"selection": {"source_ref": grant["grant_ref"]}},
        "can_write": writable(current, loaded) and grant["status"] == "open",
        "professional_approval": False,
        "calculated": False,
    }
    if row:
        directory = current["private"] / row["case_ref"]
        result.update(
            case=api.read_json(directory / "case.json"),
            note=api.read_json(directory / "proposal_note.json")["note"],
            validation=row["validation"],
        )
        if (directory / "prior_case.json").exists():
            result["prior_case"] = api.read_json(directory / "prior_case.json")
        scope = [current["scope"], row["case_ref"], row["artifacts"]]
        readback_path = current["private"] / (
            "management-readback-draft-" + row["case_ref"] + ".json"
        )
        saved = (
            api.read_json(readback_path)
            if readback_path.exists()
            else {
                "scope": scope,
                "generation": 0,
                "fields": dict.fromkeys(
                    ("decision", "reviewer", "reviewed_at", "basis"), ""
                ),
            }
        )
        if saved["scope"] != scope:
            raise PermissionError(
                "Management named readback belongs to another complete case"
            )
        review_fields(saved["fields"], final=False)
        result.update(
            review_draft=saved["fields"],
            draft_revision=api.digest(saved),
            review_generation=saved["generation"],
        )
        if "registration" in row:
            receipt = row["registration"]
            result["registration"] = {
                k: receipt[k]
                for k in (
                    "work_ref",
                    "input_ids",
                    "recipe_input_id",
                    "review_input_id",
                    "mode",
                    "fields",
                )
            }
    if model:
        if grant["status"] == "cancelled" or current["recovery_required"]:
            raise PermissionError("Management source mandate is cancelled or uncertain")
        sources = [
            {**s, "authorized_path": str(selected(s["input_id"], loaded)[0])}
            for s in grant["mandate"]["sources"]
        ]
        result = {
            "work_ref": args["work_ref"],
            "grant_ref": grant["grant_ref"],
            "revision": result["revision"],
            "status": grant["status"],
            "fields": grant["mandate"]["fields"],
            "sources": sources,
            "intake_path": str(current["output"] / grant["intake_ref"]),
            "public_skill_path": str(root / "skills/management-control-pack/SKILL.md"),
            "costing_method_path": str(root / "references/costing.md"),
            "actual_model_reads_verified": False,
            "boundary": "Read the complete public specialist method and only explicitly granted original sources. Reporting inspection samples are not the complete population; suggested recipe roles remain unapproved. Focused costing has no ledger requirement. Author the entire ordinary recipe/costing payload and open-items note. Keep a new reporting mapping_review exactly not_reviewed with empty reviewer/time; retain prior actual case/reviews separately. Do not invent amounts, classifications, drivers, accounting completeness, review, identity or actual-reading claims. Stage proposal={case:whole_public_payload,note:open_items}. Named complete-case readback, registration into a new same-engagement run, calculation and commentary/report review are separate. No provider worker is launched; record actual model exposure in the ordinary run-level report.",
        }
        if row:
            result["chosen_proposal"] = {
                "authorized_path": str(
                    current["private"] / row["case_ref"] / "case.json"
                ),
                "sha256": file_hash(current["private"] / row["case_ref"] / "case.json"),
                "note": api.read_json(
                    current["private"] / row["case_ref"] / "proposal_note.json"
                )["note"],
            }
    return result


def registered_case(view: dict, fields: dict, loaded: dict, root: Path) -> dict:
    """Check the declared case before recording any import intent or side effect."""
    value = json.loads(json.dumps(view["case"]))
    mode = view["mandate"]["fields"]["mode"]
    if mode == "reporting":
        value["mapping_review"] = {
            "status": "reviewed",
            "reviewer": fields["reviewer"],
            "reviewed_at": fields["reviewed_at"],
            "basis": fields["basis"],
        }
    public(
        root,
        {
            "operation": "register",
            "mode": mode,
            "case": value,
            "sources": [
                str(selected(i, loaded)[0])
                for i in view["mandate"]["fields"]["input_ids"]
            ],
            "context": loaded["context_path"],
        },
    )
    return value


def conserve(
    binding: dict,
    loaded: dict,
    current: dict,
    view: dict,
    fields: dict,
    key: str,
    value: dict,
    api: Any,
) -> dict:
    """Import immutable case/readback and start an actual separate Archive run."""
    core = archive_module(api.archive_root)
    folder, _ = engagement_scope(core, binding["client_id"], binding["engagement_id"])
    if folder.resolve() != Path(binding["client_root"]).resolve():
        raise PermissionError("Management case registration belongs to another client")
    mode = view["mandate"]["fields"]["mode"]
    ref = "management-case-readback-" + api.digest(
        [current["scope"], view["selection"]["id"], key]
    )
    directory = current["private"] / ref
    directory.mkdir(exist_ok=False)
    api.atomic_json(directory / "case.json", value)
    api.atomic_json(
        directory / "case-readback.json",
        {
            "schema_version": "vera.native.management_case_readback.v1",
            "scope": current["scope"],
            "case_ref": view["selection"]["id"],
            "proposal_sha256": file_hash(
                current["private"] / view["selection"]["id"] / "case.json"
            ),
            "registered_case_sha256": file_hash(directory / "case.json"),
            "fields": fields,
            "professional_approval": False,
            "reviewer_authenticated": False,
            "actual_model_reads_verified": False,
            "calculated": False,
            "sent_or_published": False,
        },
    )
    imported = [
        core.ledger.import_document(
            folder,
            binding["client_id"],
            binding["engagement_id"],
            p.resolve(),
            "source",
        )["receipt"]["input_id"]
        for p in (directory / "case.json", directory / "case-readback.json")
    ]
    chosen = {s["input_id"] for s in view["mandate"]["sources"]}
    inputs = [
        r for r in loaded["input_manifest"]["inputs"] if r["binding_id"] in chosen
    ]
    prepared = core.prepare_studio_client_workflow(
        binding["engagement_id"],
        "management-control-pack",
        input_ids=list(
            dict.fromkeys(
                [
                    *[
                        r["binding_id"]
                        for r in inputs
                        if r["kind"] != "upstream_artifact"
                    ],
                    *imported,
                ]
            )
        ),
        upstream_artifacts=[
            {
                "run_id": r["upstream_run_id"],
                "artifact_id": r["upstream_artifact_id"],
                "role": r["role"],
            }
            for r in inputs
            if r["kind"] == "upstream_artifact"
        ],
        label="Controllo di gestione: caso preparato e riscontrato",
        purpose="Calcolare separatamente il caso dopo il riscontro completo di fonti e scelte.",
        idempotency_key="native-management-author-"
        + api.digest([current["scope"]["owner"], key]),
        new_run=True,
    )
    run_id = prepared["run"]["run_id"]
    core.start_studio_client_workflow(
        binding["client_id"], binding["engagement_id"], run_id
    )
    successor = {
        **binding,
        "run_id": run_id,
        "work_ref": work_ref(binding["client_id"], binding["engagement_id"], run_id),
    }
    hydrated = api.load_binding(successor)
    for identity, name in zip(
        imported, ("case.json", "case-readback.json"), strict=True
    ):
        if file_hash(selected(identity, hydrated)[0]) != file_hash(directory / name):
            raise ValueError("Registered Management case differs from named readback")
    return {
        "binding": successor,
        "work_ref": successor["work_ref"],
        "recipe_input_id": imported[0],
        "review_input_id": imported[1],
        "input_ids": view["mandate"]["fields"]["input_ids"],
        "mode": mode,
        "fields": fields,
        "receipt_ref": ref,
        "readback_artifacts": tree_hash(directory),
    }


def dispatch(
    tool: str, args: dict, binding: dict, loaded: dict, root: Path, api: Any
) -> dict:
    """Retain complete user/model/professional steps without implicit execution."""
    action = tool.removeprefix("vera_workspace_management_author_")
    current = snapshot(binding, loaded, root, api)
    if action == "setup":
        _, saved, stamp = draft(current, loaded, api)
        start = offset(args)
        rows = loaded["input_manifest"]["inputs"]
        return bounded(
            {
                "work_ref": args["work_ref"],
                "revision": current["revision"],
                "draft": saved["fields"],
                "draft_revision": stamp,
                "items": [
                    {
                        "id": r["binding_id"],
                        "name": Path(r["execution_relative_path"]).name,
                        "suffix": Path(r["execution_relative_path"]).suffix.lower(),
                    }
                    for r in rows[start : start + 30]
                ],
                "total": len(rows),
                "has_more": start + 30 < len(rows),
                "grants": [
                    {
                        "grant_ref": g["grant_ref"],
                        "status": g["status"],
                        "question": g["mandate"]["fields"]["question"],
                    }
                    for g in current["state"]["grants"]
                ],
                "can_write": writable(current, loaded),
                "recovery_required": current["recovery_required"],
                "model_grant": False,
                "professional_approval": False,
            }
        )
    if action in {"read", "context"}:
        view = page(current, loaded, root, args, api, model=action == "context")
        if action == "context" and args["revision"] != view["revision"]:
            raise ValueError("Reopen the exact Management source mandate")
        return bounded(view, maximum=64000 if action == "context" else 2_000_000)
    with api.write_lock(current["output"]):
        loaded = api.load_binding(binding)
        current = snapshot(binding, loaded, root, api)
        if not writable(current, loaded):
            raise PermissionError(
                "Management preparation requires an owned running reviewer without uncertain writes"
            )
        state, key = current["state"], args.get("idempotency_key")
        fingerprint = api.digest([current["scope"], tool, args])
        intent = None
        if action in {"request", "stage", "register", "cancel"}:
            if not isinstance(key, str) or not re.fullmatch(
                r"[A-Za-z0-9_-]{1,120}", key
            ):
                raise ValueError("Invalid Management preparation request identity")
            intent = current["private"] / (
                "management-author-request-"
                + api.digest([current["scope"]["owner"], key])
                + ".json"
            )
            if intent.exists():
                previous = api.read_json(intent)
                if (
                    previous["request_sha256"] != fingerprint
                    or "result" not in previous
                ):
                    raise ValueError("Changed or uncertain Management authoring retry")
                return previous["result"]
        if action in {"draft_save", "request"}:
            path, saved, stamp = draft(current, loaded, api)
            if (
                args["revision"] != current["revision"]
                or args["expected_draft_revision"] != stamp
            ):
                raise ValueError("Reopen current Management preparation draft")
            value = choices(args["fields"], loaded, final=action == "request")
            if action == "draft_save":
                updated = {
                    **saved,
                    "generation": saved["generation"] + 1,
                    "fields": value,
                }
                api.atomic_json(path, updated)
                return {
                    "saved": True,
                    "draft_revision": api.digest(updated),
                    "model_grant": False,
                }
            if args.get("confirmed") is not True or value != saved["fields"]:
                raise ValueError(
                    "Renew confirmation of the saved question and exact sources"
                )
            ids = [
                *value["input_ids"],
                *([value["base_case_input_id"]] if value["base_case_input_id"] else []),
            ]
            mandate = {
                "scope": current["scope"],
                "fields": value,
                "sources": [
                    {
                        "input_id": i,
                        "sha256": file_hash(selected(i, loaded)[0]),
                        "role": (
                            "prior_case"
                            if i == value["base_case_input_id"]
                            else "source"
                        ),
                    }
                    for i in ids
                ],
                "request_sha256": fingerprint,
            }
            ref, intake = "management-mandate-" + api.digest(
                mandate
            ), "codex-management-intake-" + api.digest(mandate)
            api.atomic_json(intent, {"request_sha256": fingerprint})
            public(
                root,
                {
                    "operation": "inspect",
                    "mode": value["mode"],
                    "sources": [
                        str(selected(i, loaded)[0]) for i in value["input_ids"]
                    ],
                    "context": loaded["context_path"],
                    "output": str(current["output"] / intake),
                },
            )
            state["grants"].append(
                {
                    "grant_ref": ref,
                    "mandate": mandate,
                    "status": "open",
                    "intake_ref": intake,
                    "intake_artifacts": tree_hash(current["output"] / intake),
                }
            )
            result = {
                "saved": True,
                "grant_ref": ref,
                "calculated": False,
                "professional_approval": False,
            }
        else:
            view = page(current, loaded, root, args, api)
            if view["status"] != "open" or args["revision"] != view["revision"]:
                raise ValueError("Management source mandate is stale or closed")
            grant = next(
                g for g in state["grants"] if g["grant_ref"] == args["grant_ref"]
            )
            if action == "stage":
                proposal = args["proposal"]
                if (
                    not isinstance(proposal, dict)
                    or set(proposal) != {"case", "note"}
                    or not isinstance(proposal["case"], dict)
                    or not isinstance(proposal["note"], str)
                    or len(proposal["note"]) > 12000
                    or len(json.dumps(proposal, ensure_ascii=False).encode())
                    > 1_000_000
                ):
                    raise ValueError(
                        "Retain a complete bounded Management case and open-items note; use files for larger work"
                    )
                checked = public(
                    root,
                    {
                        "operation": "stage",
                        "mode": grant["mandate"]["fields"]["mode"],
                        "case": proposal["case"],
                        "sources": [
                            str(selected(i, loaded)[0])
                            for i in grant["mandate"]["fields"]["input_ids"]
                        ],
                        "context": loaded["context_path"],
                    },
                )
                ref = "management-authored-" + fingerprint
                directory = current["private"] / ref
                api.atomic_json(intent, {"request_sha256": fingerprint})
                directory.mkdir(exist_ok=False)
                api.atomic_json(directory / "case.json", proposal["case"])
                api.atomic_json(
                    directory / "proposal_note.json", {"note": proposal["note"]}
                )
                api.atomic_json(directory / "validation.json", checked)
                base = grant["mandate"]["fields"]["base_case_input_id"]
                if base:
                    api.atomic_json(
                        directory / "prior_case.json",
                        api.read_json(selected(base, loaded)[0]),
                    )
                state["proposals"].append(
                    {
                        "case_ref": ref,
                        "grant_ref": grant["grant_ref"],
                        "artifacts": tree_hash(directory),
                        "validation": checked,
                    }
                )
                result = {
                    "saved": True,
                    "case_ref": ref,
                    "validation": checked,
                    "professional_approval": False,
                    "calculated": False,
                }
            elif action in {"review_draft_save", "register"}:
                if (
                    args["source_ref"] != grant["grant_ref"]
                    or args["item_id"] != args["case_ref"]
                    or args["expected_draft_revision"] != view["draft_revision"]
                ):
                    raise ValueError(
                        "Select this exact full Management case and current readback"
                    )
                value = review_fields(args["fields"], final=action == "register")
                row = next(
                    r for r in state["proposals"] if r["case_ref"] == args["case_ref"]
                )
                if action == "review_draft_save":
                    updated = {
                        "scope": [current["scope"], row["case_ref"], row["artifacts"]],
                        "generation": view["review_generation"] + 1,
                        "fields": value,
                    }
                    api.atomic_json(
                        current["private"]
                        / ("management-readback-draft-" + row["case_ref"] + ".json"),
                        updated,
                    )
                    return {
                        "saved": True,
                        "draft_revision": api.digest(updated),
                        "professional_approval": False,
                    }
                if (
                    args.get("confirmed") is not True
                    or value != view["review_draft"]
                    or value["decision"] != "accepted"
                ):
                    raise ValueError(
                        "Renew the exact saved accepted named case readback"
                    )
                case = registered_case(view, value, loaded, root)
                api.atomic_json(intent, {"request_sha256": fingerprint})
                registration = conserve(
                    binding, loaded, current, view, value, key, case, api
                )
                row["registration"] = registration
                grant["status"] = "registered"
                result = {
                    "saved": True,
                    "status": "management_case_registered",
                    "case_ref": row["case_ref"],
                    **{
                        k: registration[k]
                        for k in (
                            "work_ref",
                            "input_ids",
                            "recipe_input_id",
                            "review_input_id",
                            "mode",
                        )
                    },
                    "calculated": False,
                    "professional_approval": False,
                    "run_completed": False,
                }
            elif action == "cancel":
                if args.get("confirmed") is not True:
                    raise ValueError(
                        "Confirm cancellation of this exact Management mandate"
                    )
                api.atomic_json(intent, {"request_sha256": fingerprint})
                grant["status"] = "cancelled"
                result = {"saved": True, "status": "cancelled"}
            else:
                raise ValueError("Unknown Management preparation action")
        if (
            snapshot(binding, api.load_binding(binding), root, api)["scope"]
            != current["scope"]
        ):
            raise ValueError(
                "Management original sources or implementation changed during conservation"
            )
        api.atomic_json(current["private"] / "management-author-state.json", state)
        api.atomic_json(intent, {"request_sha256": fingerprint, "result": result})
        return result
