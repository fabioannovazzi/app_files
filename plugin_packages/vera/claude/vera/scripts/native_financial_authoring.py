"""Explicit source mandates, immutable model cases and separately named review.

Ownership, CAS, exact copies and public contract checks are mechanical audit
requirements. Models and professionals own every accounting meaning and choice.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
from datetime import date
from pathlib import Path
from typing import Any

from native_bank_preparation import file_hash, tree_hash

__all__ = ["audit_authoring", "case_path", "dispatch"]


def public_check(root: Path, request: dict) -> dict:
    result = subprocess.run(
        [
            sys.executable,
            "-I",
            "-B",
            str(Path(__file__).with_name("native_financial_author_bridge.py")),
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
            result.stderr.strip().splitlines()[-1]
            or "Financial contract checks refused"
        )
    return json.loads(result.stdout)


def audit_authoring(output: Path, api: Any) -> dict:
    """Audit every retained candidate and incomplete intent, never adopt success."""
    private = api.ui_state_directory(output, create=False)
    state_path = private / "financial-author-state.json"
    state = (
        api.read_json(state_path)
        if state_path.exists()
        else {"grants": [], "cases": []}
    )
    known_grants, known_cases = set(), set()
    for grant in state["grants"]:
        ref = grant["grant_ref"]
        if (
            not re.fullmatch(r"financial-mandate-[0-9a-f]{64}", ref)
            or ref in known_grants
        ):
            raise ValueError("Invalid Financial authoring mandate")
        known_grants.add(ref)
        # The read-only Archive audit supplies no mutation/revision API.
        if hashlib.sha256(
            json.dumps(grant["mandate"], sort_keys=True, ensure_ascii=False).encode()
        ).hexdigest() != ref.removeprefix("financial-mandate-"):
            raise ValueError("Financial authoring mandate changed")
        if grant["status"] not in {"open", "reviewed", "cancelled"}:
            raise ValueError("Invalid Financial authoring status")
    for row in state["cases"]:
        ref = row["case_ref"]
        if (
            not re.fullmatch(r"financial-authored-[0-9a-f]{64}", ref)
            or ref in known_cases
            or row["grant_ref"] not in known_grants
        ):
            raise ValueError("Invalid Financial authored candidate")
        known_cases.add(ref)
        if tree_hash(output / ref) != row["artifacts"]:
            raise ValueError("Financial authored candidate artifacts changed")
        if (
            row["review"] is not None
            and api.read_json(private / (ref + "-review.json")) != row["review"]
        ):
            raise ValueError("Financial named case review changed")
        if row["review"] is not None and ref == row["review"]["reviewed_case_ref"]:
            receipt = api.read_json(output / ref / "case_review.json")
            if (
                receipt != row["review"]
                or {
                    k: v for k, v in row["artifacts"].items() if k != "case_review.json"
                }
                != receipt["reviewed_content_artifacts"]
            ):
                raise ValueError(
                    "Financial reviewed case receipt does not bind its complete content"
                )
    by_ref = {r["case_ref"]: r for r in state["cases"]}
    for row in state["cases"]:
        receipt = row["review"]
        if receipt is None:
            continue
        original = by_ref.get(receipt["proposal_ref"])
        reviewed = by_ref.get(receipt["reviewed_case_ref"])
        if (
            original is None
            or reviewed is None
            or original["artifacts"] != receipt["proposal_artifacts"]
            or original["grant_ref"] != row["grant_ref"]
            or reviewed["grant_ref"] != row["grant_ref"]
            or original["review"] != receipt
            or reviewed["review"] != receipt
        ):
            raise ValueError(
                "Financial named review does not close its exact proposal and reviewed version"
            )
    return {
        "state": state,
        "recovery_required": any(
            "result" not in api.read_json(p)
            for p in private.glob("financial-author-request-*.json")
        )
        or any(p.name not in known_cases for p in output.glob("financial-authored-*")),
        "pending": any(g["status"] == "open" for g in state["grants"]),
    }


def scope(current: dict, loaded: dict) -> dict:
    return {
        "owner": current["owner"],
        "inputs": loaded["input_manifest"],
        "implementation": current["implementation"],
    }


def fields_valid(fields: dict, current: dict, loaded: dict) -> None:
    from native_financial_execution import registered

    if not isinstance(fields, dict) or set(fields) != {
        "pack_id",
        "input_ids",
        "question",
        "base_ref",
    }:
        raise ValueError("Invalid Financial authoring choices")
    if (
        not isinstance(fields["pack_id"], str)
        or fields["pack_id"]
        and fields["pack_id"] not in current["packs"]
    ):
        raise ValueError("Choose a maintained Financial recipe")
    if not isinstance(fields["question"], str) or len(fields["question"]) > 4000:
        raise ValueError("Invalid Financial authoring question")
    ids = fields["input_ids"]
    if (
        not isinstance(ids, list)
        or len(ids) > 1000
        or any(not isinstance(v, str) for v in ids)
        or len(set(ids)) != len(ids)
    ):
        raise ValueError("Choose distinct registered Financial sources")
    for identity in ids:
        registered(loaded, identity)
    if not isinstance(fields["base_ref"], str):
        raise ValueError("Invalid Financial predecessor choice")
    if fields["base_ref"]:
        row = next(
            (
                v
                for v in current["authoring"]["cases"]
                if v["case_ref"] == fields["base_ref"]
            ),
            None,
        )
        if row is None or fields["pack_id"] != row["pack_id"]:
            raise ValueError(
                "Choose an exact retained same-recipe Financial predecessor"
            )


def draft(current: dict, loaded: dict, api: Any) -> tuple[Path, dict, str, int]:
    path = current["private"] / (
        "financial-author-draft-" + api.digest(current["owner"]) + ".json"
    )
    value = api.read_json(path) if path.exists() else None
    if value and value["scope"] != scope(current, loaded):
        raise PermissionError("Financial authoring draft belongs to another scope")
    fields = (
        value["fields"]
        if value
        else {"pack_id": "", "input_ids": [], "question": "", "base_ref": ""}
    )
    fields_valid(fields, current, loaded)
    return (
        path,
        fields,
        api.digest(value) if value else "",
        value["generation"] if value else 0,
    )


def case_path(current: dict, identity: str, *, reviewed: bool = True) -> Path:
    row = next(
        (r for r in current["authoring"]["cases"] if r["case_ref"] == identity), None
    )
    if (
        row is None
        or reviewed
        and (
            row["review"] is None
            or row["review"]["reviewed_case_ref"] != identity
            or not row["validation"]["valid"]
        )
    ):
        raise PermissionError("Choose an exact separately reviewed Financial case")
    return current["output"] / identity / "case/case.json"


def selected_grant(current: dict, loaded: dict, args: dict) -> dict:
    from native_financial_execution import registered

    grant = next(
        (
            v
            for v in current["authoring"]["grants"]
            if v["grant_ref"] == args["grant_ref"]
        ),
        None,
    )
    if grant is None or grant["mandate"]["scope"] != scope(current, loaded):
        raise PermissionError("Choose an exact owned Financial authoring mandate")
    for source in grant["mandate"]["sources"]:
        path = registered(loaded, source["input_id"])
        if (
            file_hash(path) != source["sha256"]
            or path.stat().st_size != source["byte_count"]
        ):
            raise ValueError("Financial authoring original changed")
    return grant


def review_fields_valid(fields: dict) -> None:
    if (
        not isinstance(fields, dict)
        or set(fields) != {"reviewer", "reviewed_at", "basis"}
        or any(not isinstance(v, str) or len(v) > 4000 for v in fields.values())
    ):
        raise ValueError("Invalid Financial professional review fields")


def review_draft(
    current: dict, loaded: dict, row: dict, api: Any
) -> tuple[Path, dict, str, int]:
    path = current["private"] / (row["case_ref"] + "-review-draft.json")
    value = api.read_json(path) if path.exists() else None
    expected = {
        **scope(current, loaded),
        "case_ref": row["case_ref"],
        "artifacts": row["artifacts"],
    }
    if value and value["scope"] != expected:
        raise PermissionError(
            "Financial review draft belongs to another candidate or scope"
        )
    fields = (
        value["fields"] if value else {"reviewer": "", "reviewed_at": "", "basis": ""}
    )
    review_fields_valid(fields)
    return (
        path,
        fields,
        api.digest(value) if value else "",
        value["generation"] if value else 0,
    )


def grant_page(current: dict, loaded: dict, args: dict, root: Path, api: Any) -> dict:
    from native_financial_execution import registered

    grant = selected_grant(current, loaded, args)
    mandate = grant["mandate"]
    rows = [
        r for r in current["authoring"]["cases"] if r["grant_ref"] == grant["grant_ref"]
    ]
    chosen = next((r for r in rows if r["case_ref"] == args.get("case_ref")), None)
    if args.get("case_ref") and chosen is None:
        raise ValueError("Choose an exact Financial proposal, never an implicit latest")
    data = {
        "work_ref": args["work_ref"],
        "grant_ref": grant["grant_ref"],
        "revision": api.digest([current["revision"], grant, rows]),
        "data": {"selection": {"source_ref": grant["grant_ref"]}},
        "selection": {"id": chosen["case_ref"]} if chosen else None,
        "mandate": mandate,
        "status": grant["status"],
        "proposals": [
            {k: r[k] for k in ("case_ref", "pack_id", "validation", "review")}
            for r in rows
        ],
        "can_write": can_write(current, loaded) and grant["status"] == "open",
        "report_ready": False,
        "professional_approval": False,
    }
    if chosen:
        directory = current["output"] / chosen["case_ref"]
        data.update(
            case=api.read_json(directory / "case/case.json"),
            proposal=api.read_json(directory / "proposal.json"),
            validation=chosen["validation"],
            review=chosen["review"],
            case_ref=chosen["case_ref"],
        )
        if not args.get("model_context"):
            _, fields, stamp, _ = review_draft(current, loaded, chosen, api)
            data.update(review_draft=fields, review_draft_revision=stamp)
    if args.get("model_context"):
        if grant["status"] == "cancelled":
            raise PermissionError("Financial authoring mandate was cancelled")
        data["sources"] = [
            {**r, "authorized_path": str(registered(loaded, r["input_id"]))}
            for r in mandate["sources"]
        ]
        data["method_path"] = str(root / "skills/financial-analysis/SKILL.md")
        if mandate["fields"]["pack_id"] not in {
            "monthly_pnl",
            "working_capital",
            "customer_concentration",
        }:
            from native_financial_author_bridge import PENDING_FDD_FIELDS

            data["pending_constructor"] = {
                "schema_version": "vera.native.fdd_case_proposal.v1",
                "fields": list(PENDING_FDD_FIELDS),
                "decisions": "Each decision has exactly decision_ref and basis. No review, reviewer, approval or synthetic review date is supplied. The named human case-review gate supplies actual review metadata to unchanged build_fdd_case and conserves a separate public bundle.",
                "boundary": "Use explicit source-bound package/dataset/relationship/crosswalk contracts and complete public FDD input shapes. Accounting meaning remains proposed. Source table parsing, arithmetic and professional conclusions are separate.",
            }
        if mandate["fields"]["base_ref"]:
            data["predecessor_case"] = api.read_json(
                case_path(current, mandate["fields"]["base_ref"], reviewed=False)
            )
        data["boundary"] = (
            "Only explicitly selected originals and this exact chosen proposal/predecessor. Read complete originals with maintained runtime readers, retain unknowns, use unchanged public builders, never infer roles from names or add professional approval. Staging is private; professional case review, recipe execution and output review are separate. Record only actual model exposure."
        )
    return data


def can_write(current: dict, loaded: dict) -> bool:
    return (
        loaded["run"]["status"] == "running"
        and not current["recovery_required"]
        and "REVIEWER" in os.environ.get("VERA_WORKSPACE_ROLES", "").split(",")
    )


def dispatch(
    tool: str, args: dict, binding: dict, loaded: dict, root: Path, api: Any
) -> dict:
    from native_financial_execution import context, registered

    action = tool.removeprefix("vera_workspace_financial_author_")
    current = context(binding, loaded, root, api)
    if action == "setup":
        _, fields, stamp, _ = draft(current, loaded, api)
        return {
            "work_ref": binding["work_ref"],
            "revision": current["revision"],
            "packs": current["packs"],
            "draft": fields,
            "draft_revision": stamp,
            "inputs": [
                {
                    "id": r["binding_id"],
                    "title": Path(r["execution_relative_path"]).name,
                }
                for r in loaded["input_manifest"]["inputs"]
            ],
            "bases": [
                {"case_ref": r["case_ref"], "pack_id": r["pack_id"]}
                for r in current["authoring"]["cases"]
            ],
            "grants": [
                {
                    "grant_ref": g["grant_ref"],
                    "status": g["status"],
                    "question": g["mandate"]["fields"]["question"],
                }
                for g in current["authoring"]["grants"]
            ],
            "can_write": can_write(current, loaded),
            "report_ready": False,
        }
    if action in {"read", "context"}:
        data = grant_page(
            current, loaded, {**args, "model_context": action == "context"}, root, api
        )
        if action == "context" and args["revision"] != data["revision"]:
            raise ValueError(
                "Reopen the exact Financial authoring mandate and proposal"
            )
        return data
    if action not in {
        "draft_save",
        "request",
        "stage",
        "review_draft_save",
        "review",
        "cancel",
    }:
        raise ValueError("Unknown Financial authoring action")
    if not can_write(current, loaded):
        raise PermissionError(
            "Financial authoring requires an owned running reviewer run without uncertainty"
        )
    with api.write_lock(current["output"]):
        loaded = api.load_binding(binding)
        current = context(binding, loaded, root, api)
        key = args.get("idempotency_key")
        intent = None
        fingerprint = api.digest([tool, scope(current, loaded), args])
        if action not in {"draft_save", "review_draft_save"}:
            if not isinstance(key, str) or not re.fullmatch(
                r"[A-Za-z0-9_-]{1,120}", key
            ):
                raise ValueError("Invalid Financial authoring request key")
            intent = current["private"] / (
                "financial-author-request-"
                + api.digest([current["owner"], key])
                + ".json"
            )
            if intent.exists():
                saved = api.read_json(intent)
                if saved["request_sha256"] != fingerprint or "result" not in saved:
                    raise ValueError(
                        "Changed or interrupted Financial authoring request"
                    )
                return saved["result"]
        if not can_write(current, loaded):
            raise ValueError("Financial authoring scope is stale or uncertain")
        if action in {"draft_save", "request"}:
            if args["revision"] != current["revision"]:
                raise ValueError("Stale Financial authoring intake")
            path, _, stamp, generation = draft(current, loaded, api)
            if args["expected_draft_revision"] != stamp:
                raise ValueError("Financial authoring draft changed in another window")
            fields_valid(args["fields"], current, loaded)
            if action == "draft_save":
                value = {
                    "scope": scope(current, loaded),
                    "fields": args["fields"],
                    "generation": generation + 1,
                }
                api.atomic_json(path, value)
                return {
                    "saved": True,
                    "draft_revision": api.digest(value),
                    "report_ready": False,
                    "model_grant": False,
                }
            fields = args["fields"]
            if (
                args["confirmed"] is not True
                or not fields["question"].strip()
                or not fields["pack_id"]
                or not fields["input_ids"]
            ):
                raise ValueError(
                    "Confirm the explicit recipe, selected originals and specific authoring question"
                )
            rows = {r["binding_id"]: r for r in loaded["input_manifest"]["inputs"]}
            mandate = {
                "scope": scope(current, loaded),
                "fields": fields,
                "sources": [
                    {
                        "input_id": identity,
                        "sha256": rows[identity]["sha256"],
                        "byte_count": registered(loaded, identity).stat().st_size,
                    }
                    for identity in fields["input_ids"]
                ],
                "request_sha256": fingerprint,
            }
            ref = "financial-mandate-" + api.digest(mandate)
            state = current["authoring"]
            state["grants"].append(
                {"grant_ref": ref, "mandate": mandate, "status": "open"}
            )
            result = {
                "saved": True,
                "grant_ref": ref,
                "report_ready": False,
                "professional_approval": False,
            }
        else:
            grant = selected_grant(current, loaded, args)
            page = grant_page(current, loaded, args, root, api)
            if args["revision"] != page["revision"] or grant["status"] != "open":
                raise ValueError("Stale or closed Financial authoring mandate")
            state = current["authoring"]
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
                        "Stage one complete bounded Financial case, exact source bindings and literal note"
                    )
                selected_ids = {r["input_id"] for r in grant["mandate"]["sources"]}
                if any(
                    not isinstance(v, str) or v not in selected_ids
                    for v in proposal["source_bindings"].values()
                ):
                    raise PermissionError(
                        "Financial proposal uses an original outside the explicit mandate"
                    )
                slots = public_check(
                    root,
                    {
                        "operation": "bindings",
                        "value": proposal["case"],
                        "pack_id": grant["mandate"]["fields"]["pack_id"],
                    },
                )["sources"]
                if set(proposal["source_bindings"]) != {s["source_id"] for s in slots}:
                    raise ValueError(
                        "Bind every declared Financial case source exactly once"
                    )
                locators = [s["locator"] for s in slots]
                if any(
                    p == "case.json"
                    or p.startswith("case.json/")
                    or any(
                        other != p and other.startswith(p + "/") for other in locators
                    )
                    for p in locators
                ):
                    raise ValueError(
                        "Financial source locators collide with a case or another source directory"
                    )
                receipts = {}
                for item in slots:
                    original = registered(
                        loaded, proposal["source_bindings"][item["source_id"]]
                    )
                    digest = file_hash(original)
                    if (
                        item["locator"] in receipts
                        and receipts[item["locator"]] != digest
                    ):
                        raise ValueError("Conflicting Financial original locators")
                    receipts[item["locator"]] = digest
                ref = "financial-authored-" + fingerprint
                directory = current["output"] / ref
                api.atomic_json(intent, {"request_sha256": fingerprint})
                case = directory / "case/case.json"
                case.parent.mkdir(parents=True, exist_ok=False)
                api.atomic_json(case, proposal["case"])
                copied = {}
                for item in slots:
                    target = case.parent / item["locator"]
                    if item["locator"] == "case.json":
                        raise ValueError("Financial original collides with the case")
                    original = registered(
                        loaded, proposal["source_bindings"][item["source_id"]]
                    )
                    if item["locator"] in copied:
                        if copied[item["locator"]] != file_hash(original):
                            raise ValueError("Conflicting Financial original locators")
                        continue
                    target.parent.mkdir(parents=True, exist_ok=True)
                    with (
                        original.open("rb") as source,
                        target.open("xb") as destination,
                    ):
                        shutil.copyfileobj(source, destination)
                    copied[item["locator"]] = file_hash(original)
                validation = public_check(
                    root,
                    {
                        "case": str(case),
                        "pack_id": grant["mandate"]["fields"]["pack_id"],
                        "context": str(loaded["context_path"]),
                    },
                )
                api.atomic_json(directory / "proposal.json", proposal)
                api.atomic_json(directory / "validation.json", validation)
                refreshed = api.load_binding(binding)
                if (
                    scope(context(binding, refreshed, root, api), refreshed)
                    != scope(current, loaded)
                    or refreshed["run"]["status"] != "running"
                ):
                    raise ValueError(
                        "Financial authoring source scope changed during staging"
                    )
                for identity in proposal["source_bindings"].values():
                    registered(refreshed, identity)
                state["cases"].append(
                    {
                        "case_ref": ref,
                        "grant_ref": grant["grant_ref"],
                        "scope": scope(current, loaded),
                        "pack_id": grant["mandate"]["fields"]["pack_id"],
                        "source_bindings": proposal["source_bindings"],
                        "artifacts": tree_hash(directory),
                        "validation": validation,
                        "review": None,
                    }
                )
                result = {
                    "saved": True,
                    "case_ref": ref,
                    "validation": validation,
                    "professional_approval": False,
                    "report_ready": False,
                }
            elif action in {"review", "review_draft_save"}:
                if (
                    args["item_id"] != args["case_ref"]
                    or args["source_ref"] != grant["grant_ref"]
                ):
                    raise ValueError("Review only the signed exact Financial candidate")
                fields = args["fields"]
                review_fields_valid(fields)
                row = next(
                    (
                        v
                        for v in state["cases"]
                        if v["case_ref"] == args["case_ref"]
                        and v["grant_ref"] == grant["grant_ref"]
                    ),
                    None,
                )
                if (
                    row is None
                    or not (
                        row["validation"]["valid"]
                        or row["validation"].get("reviewable")
                    )
                    or row["review"] is not None
                ):
                    raise ValueError(
                        "Review only the exact pending case with maintained contract/source checks"
                    )
                path, _, stamp, generation = review_draft(current, loaded, row, api)
                if args["expected_review_draft_revision"] != stamp:
                    raise ValueError(
                        "Financial case review draft changed in another window"
                    )
                if action == "review_draft_save":
                    value = {
                        "scope": {
                            **scope(current, loaded),
                            "case_ref": row["case_ref"],
                            "artifacts": row["artifacts"],
                        },
                        "fields": fields,
                        "generation": generation + 1,
                    }
                    api.atomic_json(path, value)
                    return {
                        "saved": True,
                        "draft_revision": api.digest(value),
                        "report_ready": False,
                        "case_reviewed": False,
                    }
                if (
                    any(not v.strip() for v in fields.values())
                    or args["confirmed"] is not True
                ):
                    raise ValueError(
                        "Record the named professional case review and renew confirmation"
                    )
                if (
                    date.fromisoformat(fields["reviewed_at"]).isoformat()
                    != fields["reviewed_at"]
                ):
                    raise ValueError("Use the exact ISO professional review date")
                proposed_case = api.read_json(
                    current["output"] / row["case_ref"] / "case/case.json"
                )
                reviewed_value = public_check(
                    root,
                    {
                        "operation": "review_value",
                        "value": proposed_case,
                        "pack_id": row["pack_id"],
                        "reviewed_at": fields["reviewed_at"],
                        "reviewer_ref": "reviewer.native-"
                        + api.digest(current["owner"]),
                        "basis": fields["basis"].strip(),
                    },
                )["case"]
                api.atomic_json(intent, {"request_sha256": fingerprint})
                ref = "financial-authored-" + fingerprint
                directory = current["output"] / ref
                shutil.copytree(current["output"] / row["case_ref"], directory)
                if tree_hash(directory) != row["artifacts"]:
                    raise ValueError("Financial reviewed case copy changed")
                api.atomic_json(directory / "case/case.json", reviewed_value)
                original_proposal = api.read_json(directory / "proposal.json")
                api.atomic_json(
                    directory / "proposal.json",
                    {**original_proposal, "case": reviewed_value},
                )
                validation = public_check(
                    root,
                    {
                        "case": str(directory / "case/case.json"),
                        "pack_id": row["pack_id"],
                        "context": str(loaded["context_path"]),
                    },
                )
                if not validation["valid"]:
                    raise ValueError(
                        "Financial reviewed case conservation requires recovery: "
                        + validation.get("error", "contract checks refused")
                    )
                api.atomic_json(directory / "validation.json", validation)
                receipt = {
                    "fields": fields,
                    "scope": scope(current, loaded),
                    "proposal_ref": row["case_ref"],
                    "proposal_artifacts": row["artifacts"],
                    "reviewed_case_ref": ref,
                    "reviewed_content_artifacts": tree_hash(directory),
                    "financial_conclusions_approved": False,
                    "report_ready": False,
                }
                api.atomic_json(directory / "case_review.json", receipt)
                refreshed = api.load_binding(binding)
                if (
                    scope(context(binding, refreshed, root, api), refreshed)
                    != scope(current, loaded)
                    or refreshed["run"]["status"] != "running"
                ):
                    raise ValueError(
                        "Financial case review scope changed during conservation"
                    )
                selected_grant(current, refreshed, args)
                row["review"] = receipt
                api.atomic_json(
                    current["private"] / (row["case_ref"] + "-review.json"),
                    receipt,
                )
                api.atomic_json(current["private"] / (ref + "-review.json"), receipt)
                state["cases"].append(
                    {
                        **row,
                        "case_ref": ref,
                        "artifacts": tree_hash(directory),
                        "validation": validation,
                        "review": receipt,
                    }
                )
                grant["status"] = "reviewed"
                result = {
                    "saved": True,
                    "case_ref": ref,
                    "proposal_ref": row["case_ref"],
                    "case_reviewed": True,
                    "financial_conclusions_approved": False,
                    "report_ready": False,
                    "run_completed": False,
                }
            else:
                if args["confirmed"] is not True:
                    raise ValueError(
                        "Confirm cancellation of this exact authoring mandate"
                    )
                grant["status"] = "cancelled"
                result = {"saved": True, "status": "cancelled", "report_ready": False}
        assert intent is not None
        if action in {"request", "cancel"}:
            api.atomic_json(intent, {"request_sha256": fingerprint})
        api.atomic_json(current["private"] / "financial-author-state.json", state)
        api.atomic_json(intent, {"request_sha256": fingerprint, "result": result})
        return result
