"""Explicit source grants, complete model proposals and named case conservation.

Receipt identity, immutable bytes, CAS and attestation provenance are mechanical
audit controls. Models and professionals retain every economic choice.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import subprocess
import sys
from pathlib import Path
from typing import Any

from native_archive_navigation import archive_module, engagement_scope, work_ref
from native_bank_preparation import file_hash, tree_hash
from native_valuation_review import fields as review_fields

__all__ = ["audit_authoring", "dispatch"]


def digest(value: Any) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, ensure_ascii=False).encode()
    ).hexdigest()


def audit_authoring(output: Path, api: Any) -> dict:
    """Incomplete or orphaned authoring never becomes a registered success."""
    private = api.ui_state_directory(output, create=False)
    path = private / "valuation-author-state.json"
    state = api.read_json(path) if path.exists() else {"grants": [], "cases": []}
    if set(state) != {"grants", "cases"} or not all(
        isinstance(state[k], list) for k in state
    ):
        raise ValueError("Invalid valuation authoring state")
    grants = set()
    for row in state["grants"]:
        ref = row["grant_ref"]
        if (
            ref != "valuation-mandate-" + digest(row["mandate"])
            or ref in grants
            or row["status"] not in {"open", "registered", "cancelled"}
        ):
            raise ValueError("Valuation authoring mandate changed")
        grants.add(ref)
    known = set()
    receipts = set()
    for row in state["cases"]:
        ref = row["case_ref"]
        if (
            not re.fullmatch(r"valuation-authored-[0-9a-f]{64}", ref)
            or ref in known
            or row["grant_ref"] not in grants
        ):
            raise ValueError("Invalid valuation proposal identity")
        if tree_hash(private / ref) != row["artifacts"]:
            raise ValueError("Valuation complete proposal changed")
        if "registration" in row:
            registration = row["registration"]
            grant = next(
                g for g in state["grants"] if g["grant_ref"] == row["grant_ref"]
            )
            original_owner = grant["mandate"]["scope"]["owner"]
            successor_binding = registration["binding"]
            if (
                grant["status"] != "registered"
                or [
                    successor_binding[k]
                    for k in ("client_id", "engagement_id", "workflow_id")
                ]
                != [original_owner[2], original_owner[3], original_owner[5]]
                or successor_binding["run_id"] == original_owner[4]
            ):
                raise PermissionError(
                    "Valuation authored successor belongs to a different engagement"
                )
            receipt = registration["receipt_ref"]
            if (
                not re.fullmatch(r"valuation-case-readback-[0-9a-f]{64}", receipt)
                or receipt in receipts
                or tree_hash(private / receipt) != registration["artifacts"]
            ):
                raise ValueError("Valuation named case readback changed")
            successor = api.load_binding(registration["binding"])
            case_path = registered(successor, registration["case_input_id"])
            readback_path = registered(successor, registration["review_input_id"])
            if file_hash(case_path) != file_hash(
                private / ref / "case.json"
            ) or file_hash(readback_path) != file_hash(
                private / receipt / "valuation-case-readback.json"
            ):
                raise ValueError("Valuation registered successor changed")
            receipts.add(receipt)
        known.add(ref)
    requests = [
        api.read_json(p) for p in private.glob("valuation-author-request-*.json")
    ]
    for grant in state["grants"]:
        conserved = [
            r
            for r in state["cases"]
            if r["grant_ref"] == grant["grant_ref"] and "registration" in r
        ]
        if (grant["status"] == "registered") != (len(conserved) == 1) or len(
            conserved
        ) > 1:
            raise ValueError("Valuation mandate and conserved successor disagree")
    return {
        "state": state,
        "recovery_required": any("result" not in r for r in requests)
        or any(p.name not in known for p in private.glob("valuation-authored-*"))
        or any(
            p.name not in receipts for p in private.glob("valuation-case-readback-*")
        )
        or any(
            not any(r.get("result", {}).get("case_ref") == ref for r in requests)
            for ref in known
        ),
        "pending": any(g["status"] == "open" for g in state["grants"]),
    }


def registered(loaded: dict, identity: str) -> Path:
    row = next(
        (r for r in loaded["input_manifest"]["inputs"] if r["binding_id"] == identity),
        None,
    )
    if row is None:
        raise PermissionError("Choose an exact registered valuation source")
    path = Path(loaded["run_root"]) / row["execution_relative_path"]
    if file_hash(path) != row["sha256"]:
        raise ValueError("Valuation authoring source changed")
    return path


def choices(value: Any, loaded: dict, root: Path, api: Any) -> dict:
    if not isinstance(value, dict) or set(value) != {
        "question",
        "input_ids",
        "base_input_id",
    }:
        raise ValueError("Use complete valuation authoring choices")
    if (
        not isinstance(value["question"], str)
        or len(value["question"]) > 4000
        or not isinstance(value["base_input_id"], str)
    ):
        raise ValueError("Invalid valuation authoring question or predecessor")
    ids = value["input_ids"]
    if (
        not isinstance(ids, list)
        or len(ids) > 1000
        or any(not isinstance(v, str) for v in ids)
        or len(set(ids)) != len(ids)
    ):
        raise ValueError("Select distinct original receipts")
    for identity in ids:
        registered(loaded, identity)
    if value["base_input_id"]:
        from native_valuation import selected

        selected(value["base_input_id"], loaded, root, api)
    return value


def draft(current: dict, loaded: dict, root: Path, api: Any) -> tuple[Path, dict, str]:
    path = current["private"] / "valuation-author-draft.json"
    saved = (
        api.read_json(path)
        if path.exists()
        else {
            "scope": current["scope"],
            "generation": 0,
            "fields": {"question": "", "input_ids": [], "base_input_id": ""},
        }
    )
    if saved["scope"] != current["scope"]:
        raise PermissionError("Valuation authoring draft belongs to a changed scope")
    choices(saved["fields"], loaded, root, api)
    return path, saved, digest(saved)


def writable(current: dict, loaded: dict) -> bool:
    return (
        loaded["run"]["status"] == "running"
        and not current["recovery_required"]
        and "REVIEWER" in os.environ.get("VERA_WORKSPACE_ROLES", "").split(",")
    )


def preflight(root: Path, loaded: dict, grant: dict, proposal: dict, api: Any) -> dict:
    from native_valuation import selected

    base_id = grant["mandate"]["fields"]["base_input_id"]
    base = selected(base_id, loaded, root, api)[1] if base_id else None
    completed = subprocess.run(
        [
            sys.executable,
            "-I",
            "-B",
            str(Path(__file__).with_name("native_valuation_author_bridge.py")),
            str(root),
        ],
        input=json.dumps(
            {
                "case": proposal["case"],
                "base": base,
                "source_bindings": proposal["source_bindings"],
                "selected_input_ids": grant["mandate"]["fields"]["input_ids"],
                "context": str(loaded["context_path"]),
            }
        ),
        text=True,
        capture_output=True,
        timeout=90,
        check=False,
    )
    if completed.returncode:
        raise ValueError(
            completed.stderr.strip().splitlines()[-1]
            or "Public valuation preflight refused"
        )
    return json.loads(completed.stdout)


def grant_page(current: dict, loaded: dict, root: Path, args: dict, api: Any) -> dict:
    from native_valuation import selected

    grant = next(
        (
            g
            for g in current["authoring"]["grants"]
            if g["grant_ref"] == args["grant_ref"]
        ),
        None,
    )
    if grant is None or grant["mandate"]["scope"] != current["scope"]:
        raise PermissionError("Select the exact owned valuation authoring mandate")
    for item in grant["mandate"]["sources"]:
        if file_hash(registered(loaded, item["input_id"])) != item["sha256"]:
            raise ValueError("Selected valuation mandate source changed")
    rows = [
        r for r in current["authoring"]["cases"] if r["grant_ref"] == grant["grant_ref"]
    ]
    chosen = next((r for r in rows if r["case_ref"] == args.get("case_ref")), None)
    if args.get("case_ref") and chosen is None:
        raise ValueError("Choose an exact proposal, never an implicit latest")
    page = {
        "work_ref": args["work_ref"],
        "grant_ref": grant["grant_ref"],
        "revision": digest([current["revision"], grant, rows]),
        "status": grant["status"],
        "data": {"selection": {"source_ref": grant["grant_ref"]}},
        "selection": {"id": chosen["case_ref"]} if chosen else None,
        "mandate": grant["mandate"],
        "proposals": [{k: r[k] for k in ["case_ref", "validation"]} for r in rows],
        "can_write": writable(current, loaded) and grant["status"] == "open",
        "case_contents_confirmed": False,
        "professional_approval": False,
    }
    if chosen:
        page["proposal"] = api.read_json(
            current["private"] / chosen["case_ref"] / "proposal.json"
        )
        page["validation"] = chosen["validation"]
        if "registration" in chosen:
            registration = chosen["registration"]
            receipt = api.read_json(
                current["private"]
                / registration["receipt_ref"]
                / "valuation-case-readback.json"
            )
            page["registration"] = {
                "work_ref": registration["binding"]["work_ref"],
                "case_input_id": registration["case_input_id"],
                "fields": receipt["fields"],
                "case_calculated": False,
                "method_or_conclusion_acceptance": False,
            }
            page["case_contents_confirmed"] = True
        review_path = current["private"] / (
            "valuation-case-review-draft-" + chosen["case_ref"] + ".json"
        )
        review_scope = [
            current["scope"],
            {k: v for k, v in chosen.items() if k != "registration"},
        ]
        value = (
            api.read_json(review_path)
            if review_path.exists()
            else {
                "scope": review_scope,
                "generation": 0,
                "fields": {
                    "decision": "",
                    "reviewer": "",
                    "reviewed_at": "",
                    "basis": "",
                },
            }
        )
        if value["scope"] != review_scope:
            raise PermissionError(
                "Valuation case review draft belongs to a changed proposal"
            )
        review_fields(value["fields"], final=False)
        page.update(
            review_draft=value["fields"],
            draft_revision=digest(value),
            review_generation=value["generation"],
        )
    if args.get("model_context"):
        if grant["status"] != "open":
            raise PermissionError("The valuation model mandate is closed")
        # CAS uses the whole scope privately; unselected receipts and ownership
        # metadata are not part of the model's explicit source authorization.
        page["mandate"] = {k: grant["mandate"][k] for k in ("fields", "sources")}
        page["sources"] = [
            {**r, "authorized_path": str(registered(loaded, r["input_id"]))}
            for r in grant["mandate"]["sources"]
        ]
        base_id = grant["mandate"]["fields"]["base_input_id"]
        if base_id:
            page["predecessor_case"] = selected(base_id, loaded, root, api)[1]
        page["method_path"] = str(root / "skills/business-valuation/SKILL.md")
        page["contract_path"] = str(root / "references/case-contract.md")
        page["schema_path"] = str(root / "references/valuation-case.schema.json")
        page["boundary"] = (
            "Read only explicitly authorized originals. Author the entire public case and exact source-ID to receipt-ID bindings; retain unknowns and proposed data states. Source paths and hashes come from actual receipts. No new or changed human review, reviewer or acceptance is permitted; preserve original predecessor review-bearing records. Staging is a prospective check, not human confirmation. Named full-case readback, immutable import into a fresh run, calculation and individual professional decisions are separate. No provider worker is launched; record only actual model exposure."
        )
        # Private draft attribution is never added to model context.
        for key in ["review_draft", "draft_revision", "review_generation"]:
            page.pop(key, None)
    return page


def dispatch(
    tool: str, args: dict, binding: dict, loaded: dict, root: Path, api: Any
) -> dict:
    from native_valuation import bounded, context

    action = tool.removeprefix("vera_workspace_valuation_author_")
    current = context(binding, loaded, root, api)
    if action == "setup":
        _, saved, stamp = draft(current, loaded, root, api)
        return bounded(
            {
                "work_ref": args["work_ref"],
                "revision": current["revision"],
                "draft": saved["fields"],
                "draft_revision": stamp,
                "inputs": [
                    {
                        "id": r["binding_id"],
                        "title": Path(r["execution_relative_path"]).name,
                    }
                    for r in loaded["input_manifest"]["inputs"]
                ],
                "grants": [
                    {
                        "grant_ref": g["grant_ref"],
                        "status": g["status"],
                        "question": g["mandate"]["fields"]["question"],
                    }
                    for g in current["authoring"]["grants"]
                ],
                "can_write": writable(current, loaded),
                "professional_approval": False,
            }
        )
    if action in {"read", "context"}:
        page = grant_page(
            current, loaded, root, {**args, "model_context": action == "context"}, api
        )
        if action == "context" and args["revision"] != page["revision"]:
            raise ValueError("Stale valuation model context selection")
        return bounded(page, 64000 if action == "context" else 2000000)
    with api.write_lock(current["output"]):
        loaded = api.load_binding(binding)
        current = context(binding, loaded, root, api)
        if not writable(current, loaded):
            raise PermissionError(
                "Valuation authoring requires an owned running reviewer scope without uncertain writes"
            )
        key = args.get("idempotency_key")
        intent = None
        fingerprint = digest([current["scope"], tool, args])
        if action in {"request", "stage", "publish", "cancel"}:
            if not isinstance(key, str) or not re.fullmatch(
                r"[A-Za-z0-9_-]{1,120}", key
            ):
                raise ValueError("Invalid valuation authoring request key")
            intent = current["private"] / (
                "valuation-author-request-"
                + digest([current["scope"]["owner"], key])
                + ".json"
            )
            if intent.exists():
                old = api.read_json(intent)
                if old["request_sha256"] != fingerprint or "result" not in old:
                    raise ValueError("Changed or uncertain valuation authoring retry")
                return old["result"]
        state = current["authoring"]
        if action in {"draft_save", "request"}:
            if args["revision"] != current["revision"]:
                raise ValueError("Reopen current valuation authoring intake")
            path, saved, stamp = draft(current, loaded, root, api)
            if args["expected_draft_revision"] != stamp:
                raise ValueError("Valuation authoring draft changed concurrently")
            value = choices(args["fields"], loaded, root, api)
            if action == "draft_save":
                updated = {
                    **saved,
                    "fields": value,
                    "generation": saved["generation"] + 1,
                }
                api.atomic_json(path, updated)
                return {
                    "saved": True,
                    "draft_revision": digest(updated),
                    "model_grant": False,
                    "professional_approval": False,
                }
            if (
                args.get("confirmed") is not True
                or not value["question"].strip()
                or not value["input_ids"]
            ):
                raise ValueError(
                    "Confirm selected originals and the actual case-preparation question"
                )
            mandate = {
                "scope": current["scope"],
                "fields": value,
                "sources": [
                    {
                        "input_id": identity,
                        "sha256": file_hash(registered(loaded, identity)),
                    }
                    for identity in value["input_ids"]
                ],
                "request_sha256": fingerprint,
            }
            ref = "valuation-mandate-" + digest(mandate)
            state["grants"].append(
                {"grant_ref": ref, "mandate": mandate, "status": "open"}
            )
            result = {"saved": True, "grant_ref": ref, "professional_approval": False}
        else:
            page = grant_page(current, loaded, root, args, api)
            if page["status"] != "open" or args["revision"] != page["revision"]:
                raise ValueError("Stale or closed valuation authoring mandate")
            grant = next(
                g for g in state["grants"] if g["grant_ref"] == args["grant_ref"]
            )
            if action == "stage":
                proposal = args["proposal"]
                if (
                    not isinstance(proposal, dict)
                    or set(proposal) != {"case", "source_bindings", "note"}
                    or not isinstance(proposal["case"], dict)
                    or not isinstance(proposal["source_bindings"], dict)
                    or not isinstance(proposal["note"], str)
                    or len(proposal["note"]) > 12000
                    or len(json.dumps(proposal).encode()) > 100000
                ):
                    raise ValueError(
                        "Stage one complete bounded valuation case with explicit receipt bindings and note"
                    )
                checked = preflight(root, loaded, grant, proposal, api)
                ref = "valuation-authored-" + fingerprint
                directory = current["private"] / ref
                api.atomic_json(intent, {"request_sha256": fingerprint})
                directory.mkdir(exist_ok=False)
                api.atomic_json(
                    directory / "proposal.json", {**proposal, "case": checked["case"]}
                )
                api.atomic_json(directory / "case.json", checked["case"])
                api.atomic_json(directory / "validation.json", checked["validation"])
                if (
                    context(binding, api.load_binding(binding), root, api)["scope"]
                    != current["scope"]
                ):
                    raise ValueError("Valuation authoring scope changed during staging")
                row = {
                    "case_ref": ref,
                    "grant_ref": grant["grant_ref"],
                    "artifacts": tree_hash(directory),
                    "validation": checked["validation"],
                }
                state["cases"].append(row)
                result = {
                    "saved": True,
                    "case_ref": ref,
                    "validation": row["validation"],
                    "case_contents_confirmed": False,
                    "professional_approval": False,
                }
            elif action in {"review_draft_save", "publish"}:
                if (
                    args["source_ref"] != grant["grant_ref"]
                    or args["item_id"] != args["case_ref"]
                    or args["expected_draft_revision"] != page["draft_revision"]
                ):
                    raise ValueError(
                        "Review only the exact displayed complete valuation proposal and draft"
                    )
                value = review_fields(args["fields"], final=action == "publish")
                if action == "review_draft_save":
                    row = next(
                        r for r in state["cases"] if r["case_ref"] == args["case_ref"]
                    )
                    saved = {
                        "scope": [
                            current["scope"],
                            {k: v for k, v in row.items() if k != "registration"},
                        ],
                        "generation": page["review_generation"] + 1,
                        "fields": value,
                    }
                    api.atomic_json(
                        current["private"]
                        / ("valuation-case-review-draft-" + args["case_ref"] + ".json"),
                        saved,
                    )
                    return {
                        "saved": True,
                        "draft_revision": digest(saved),
                        "case_contents_confirmed": False,
                    }
                if (
                    value != page["review_draft"]
                    or value["decision"] != "accepted"
                    or args.get("confirmed") is not True
                ):
                    raise ValueError(
                        "Renew confirmation of the exact saved named full-case readback; this does not accept methods or conclusions"
                    )
                result, registration = conserve(
                    binding,
                    loaded,
                    current,
                    page,
                    value,
                    key,
                    api,
                    intent,
                    fingerprint,
                    root,
                )
                row = next(
                    r for r in state["cases"] if r["case_ref"] == args["case_ref"]
                )
                row["registration"] = registration
                grant["status"] = "registered"
            elif action == "cancel":
                if args.get("confirmed") is not True:
                    raise ValueError("Confirm cancellation of this exact model mandate")
                grant["status"] = "cancelled"
                result = {"saved": True, "status": "cancelled"}
            else:
                raise ValueError("Unknown valuation authoring action")
        assert intent is not None
        if action in {"request", "cancel"}:
            api.atomic_json(intent, {"request_sha256": fingerprint})
        api.atomic_json(current["private"] / "valuation-author-state.json", state)
        api.atomic_json(intent, {"request_sha256": fingerprint, "result": result})
        return result


def conserve(
    binding: dict,
    loaded: dict,
    current: dict,
    page: dict,
    review: dict,
    key: str,
    api: Any,
    intent: Path,
    fingerprint: str,
    root: Path,
) -> tuple[dict, dict]:
    """Use authoritative Archive import/prepare/start; never export or complete here."""
    core = archive_module(api.archive_root)
    folder, _ = engagement_scope(core, binding["client_id"], binding["engagement_id"])
    if folder.resolve() != Path(binding["client_root"]).resolve():
        raise PermissionError("Authored successor belongs to another client")
    directory = current["private"] / page["selection"]["id"]
    api.atomic_json(intent, {"request_sha256": fingerprint})
    receipt_ref = "valuation-case-readback-" + fingerprint
    receipt_directory = current["private"] / receipt_ref
    receipt_directory.mkdir(exist_ok=False)
    receipt_path = receipt_directory / "valuation-case-readback.json"
    receipt = {
        "schema_version": "vera.native.valuation_case_readback.v1",
        "scope": current["scope"],
        "case_ref": page["selection"]["id"],
        "case_sha256": file_hash(directory / "case.json"),
        "fields": review,
        "method_or_conclusion_acceptance": False,
        "piv_conformity": "not_assessed",
    }
    api.atomic_json(receipt_path, receipt)
    imported = [
        core.ledger.import_document(
            folder,
            binding["client_id"],
            binding["engagement_id"],
            path.resolve(),
            "source",
        )["receipt"]["input_id"]
        for path in [directory / "case.json", receipt_path]
    ]
    inputs = loaded["input_manifest"]["inputs"]
    prepared = core.prepare_studio_client_workflow(
        binding["engagement_id"],
        "business-valuation",
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
        label="Valutazione: caso preparato e riesaminato",
        purpose="Calcolare separatamente il caso dopo il riscontro completo dei dati dichiarati.",
        idempotency_key="native-valuation-author-"
        + digest([current["scope"]["owner"], key]),
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
    if file_hash(registered(hydrated, imported[0])) != receipt[
        "case_sha256"
    ] or file_hash(registered(hydrated, imported[1])) != file_hash(receipt_path):
        raise ValueError("Registered valuation case differs from the reviewed proposal")
    from native_valuation import context

    if (
        context(
            binding,
            api.load_binding(binding),
            root,
            api,
        )["scope"]
        != current["scope"]
    ):
        raise ValueError("Valuation authoring scope changed during conservation")
    result = {
        "saved": True,
        "status": "authored_case_registered",
        "work_ref": successor["work_ref"],
        "run_id": run_id,
        "case_input_id": imported[0],
        "review_input_id": imported[1],
        "case_contents_confirmed": True,
        "case_calculated": False,
        "method_or_conclusion_acceptance": False,
        "run_completed": False,
        "piv_conformity": "not_assessed",
    }
    return result, {
        "binding": successor,
        "receipt_ref": receipt_ref,
        "artifacts": tree_hash(receipt_directory),
        "case_input_id": imported[0],
        "review_input_id": imported[1],
    }
