"""Explicit model source grants and separately named comparison conservation.

Receipt identity, whole-file hashes, CAS and literal attestation boundaries are
mechanical audit controls. Models and professionals own accounting meaning.
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
from native_sales_plan_authoring import owner_scope
from native_valuation_authoring import digest
from native_valuation_review import fields as review_fields
from native_variance import LANGUAGES, bounded, engine_call, offset, selected

__all__ = ["audit_authoring", "dispatch"]

FIELD_NAMES = {
    "question",
    "source_input_id",
    "evidence_input_ids",
    "base_recipe_input_id",
    "currency",
    "language",
}


def choices(value: Any, loaded: dict, api: Any, *, final: bool = False) -> dict:
    """Validate exact literal receipt choices; never infer measure or period meaning."""
    if not isinstance(value, dict) or set(value) != FIELD_NAMES:
        raise ValueError("Use the complete comparison-preparation choices")
    if any(
        not isinstance(value[k], str) or len(value[k]) > 4000
        for k in FIELD_NAMES - {"evidence_input_ids"}
    ):
        raise ValueError("Invalid comparison-preparation text")
    ids = value["evidence_input_ids"]
    if (
        not isinstance(ids, list)
        or len(ids) > 1000
        or any(not isinstance(v, str) for v in ids)
        or len(set(ids)) != len(ids)
    ):
        raise ValueError("Choose distinct registered supporting receipts")
    for identity in [*ids, value["source_input_id"], value["base_recipe_input_id"]]:
        if identity:
            selected(identity, loaded)
    if value["source_input_id"] and selected(value["source_input_id"], loaded)[
        0
    ].suffix.lower() not in {".csv", ".tsv", ".psv", ".xlsx", ".xlsm"}:
        raise ValueError("Choose one registered original variance table")
    if value["base_recipe_input_id"]:
        path, _ = selected(value["base_recipe_input_id"], loaded)
        if path.suffix != ".json" or not isinstance(
            api.read_json(path).get("mappings"), dict
        ):
            raise ValueError("Choose an exact prior public comparison recipe")
    if final and (
        not value["question"].strip()
        or not value["source_input_id"]
        or not re.fullmatch(r"[A-Z]{3}", value["currency"])
        or value["language"] not in LANGUAGES
    ):
        raise ValueError(
            "Confirm the literal question, original table, currency and language"
        )
    return value


def audit_authoring(output: Path, api: Any) -> dict:
    """Retain whole proposals/intake outputs and refuse uncertain successors."""
    private = api.ui_state_directory(output, create=False)
    path = private / "variance-author-state.json"
    state = api.read_json(path) if path.exists() else {"grants": [], "proposals": []}
    known_intakes = set()
    known_proposals = set()
    known_readbacks = set()
    for grant in state["grants"]:
        ref = grant["grant_ref"]
        if ref != "variance-mandate-" + digest(grant["mandate"]) or grant[
            "status"
        ] not in {"open", "registered", "cancelled"}:
            raise ValueError("Variance model mandate changed")
        intake = grant["intake_ref"]
        if (
            intake != "variance-intake-" + digest(grant["mandate"])
            or intake in known_intakes
            or tree_hash(output / intake) != grant["intake_artifacts"]
        ):
            raise ValueError("Variance public input inspection changed")
        known_intakes.add(intake)
    for row in state["proposals"]:
        ref = row["case_ref"]
        if (
            not re.fullmatch(r"variance-authored-[a-f0-9]{64}", ref)
            or ref in known_proposals
            or not any(g["grant_ref"] == row["grant_ref"] for g in state["grants"])
            or tree_hash(private / ref) != row["artifacts"]
        ):
            raise ValueError("Variance complete proposal changed")
        known_proposals.add(ref)
        if "registration" in row:
            receipt = row["registration"]
            grant = next(
                g for g in state["grants"] if g["grant_ref"] == row["grant_ref"]
            )
            owner = grant["mandate"]["scope"]["owner"]
            successor = receipt["binding"]
            if (
                grant["status"] != "registered"
                or [successor[k] for k in ("client_id", "engagement_id", "workflow_id")]
                != [owner[2], owner[3], owner[5]]
                or successor["run_id"] == owner[4]
            ):
                raise PermissionError(
                    "Variance authored successor belongs to another engagement"
                )
            hydrated = api.load_binding(successor)
            readback = receipt["receipt_ref"]
            if (
                not re.fullmatch(r"variance-comparison-readback-[a-f0-9]{64}", readback)
                or readback in known_readbacks
                or tree_hash(private / readback) != receipt["readback_artifacts"]
            ):
                raise ValueError("Variance named comparison readback changed")
            known_readbacks.add(readback)
            if (
                receipt["source_input_id"]
                != grant["mandate"]["fields"]["source_input_id"]
                or file_hash(selected(receipt["recipe_input_id"], hydrated)[0])
                != file_hash(private / ref / "comparison.json")
                or file_hash(selected(receipt["review_input_id"], hydrated)[0])
                != file_hash(private / readback / "comparison-readback.json")
            ):
                raise ValueError(
                    "Variance registered comparison or named readback changed"
                )
    requests = [
        api.read_json(p) for p in private.glob("variance-author-request-*.json")
    ]
    for grant in state["grants"]:
        conserved = [
            r
            for r in state["proposals"]
            if r["grant_ref"] == grant["grant_ref"] and "registration" in r
        ]
        if (grant["status"] == "registered") != (len(conserved) == 1) or len(
            conserved
        ) > 1:
            raise ValueError("Variance mandate and successor disagree")
    return {
        "state": state,
        "intakes": known_intakes,
        "private": private,
        "recovery_required": any("result" not in r for r in requests)
        or any(p.name not in known_intakes for p in output.glob("variance-intake-*"))
        or any(
            p.name not in known_proposals for p in private.glob("variance-authored-*")
        )
        or any(
            p.name not in known_readbacks
            for p in private.glob("variance-comparison-readback-*")
        ),
        "pending": any(g["status"] == "open" for g in state["grants"]),
    }


def context(binding: dict, loaded: dict, root: Path, api: Any) -> dict:
    if binding["workflow_id"] != "variance-analysis":
        raise PermissionError("Variance preparation belongs to another workflow")
    from native_variance import audit_run

    output = Path(loaded["output_dir"])
    authoring = audit_authoring(output, api)
    implementation = engine_call(root, {"operation": "contract"})
    implementation["native_authoring"] = {
        p.name: file_hash(p)
        for p in (
            Path(__file__),
            Path(__file__).with_name("native_variance_author_bridge.py"),
            Path(__file__).with_name("native_variance_bridge.py"),
        )
    }
    scope = {
        "owner": owner_scope(binding),
        "run": loaded["run"],
        "inputs": loaded["input_manifest"],
        "implementation": implementation,
    }
    return {
        "output": output,
        "private": authoring["private"],
        "scope": scope,
        "revision": digest([scope, authoring["state"]]),
        "state": authoring["state"],
        "recovery_required": authoring["recovery_required"]
        or audit_run(output, api)["recovery_required"],
    }


def writable(current: dict, loaded: dict) -> bool:
    return (
        loaded["run"]["status"] == "running"
        and not current["recovery_required"]
        and "REVIEWER" in os.environ.get("VERA_WORKSPACE_ROLES", "").split(",")
    )


def draft(current: dict, loaded: dict, api: Any) -> tuple[Path, dict, str]:
    path = current["private"] / (
        "variance-author-draft-" + digest(current["scope"]["owner"]) + ".json"
    )
    saved = (
        api.read_json(path)
        if path.exists()
        else {
            "scope": current["scope"],
            "generation": 0,
            "fields": {k: [] if k == "evidence_input_ids" else "" for k in FIELD_NAMES},
        }
    )
    if saved["scope"] != current["scope"]:
        raise PermissionError("Comparison-preparation draft belongs to a changed scope")
    choices(saved["fields"], loaded, api)
    return path, saved, digest(saved)


def grant_page(
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
        raise PermissionError("Choose the current owned comparison-preparation mandate")
    rows = [
        r for r in current["state"]["proposals"] if r["grant_ref"] == grant["grant_ref"]
    ]
    row = next((r for r in rows if r["case_ref"] == args.get("case_ref")), None)
    if args.get("case_ref") and row is None:
        raise ValueError(
            "Select an exact comparison proposal, never an implicit latest"
        )
    result = {
        "work_ref": args["work_ref"],
        "grant_ref": grant["grant_ref"],
        "revision": digest([current["revision"], grant, rows]),
        "status": grant["status"],
        "mandate": grant["mandate"],
        "proposals": [{k: r[k] for k in ("case_ref", "validation")} for r in rows],
        "selection": {"id": row["case_ref"]} if row else None,
        "data": {"selection": {"source_ref": grant["grant_ref"]}},
        "can_write": writable(current, loaded) and grant["status"] == "open",
        "professional_approval": False,
        "comparison_calculated": False,
    }
    if row:
        directory = current["private"] / row["case_ref"]
        result["proposal"] = api.read_json(directory / "proposal.json")
        result["validation"] = row["validation"]
        review_scope = [
            current["scope"],
            {k: v for k, v in row.items() if k != "registration"},
        ]
        review_path = current["private"] / (
            "variance-readback-draft-" + row["case_ref"] + ".json"
        )
        review = (
            api.read_json(review_path)
            if review_path.exists()
            else {
                "scope": review_scope,
                "generation": 0,
                "fields": dict.fromkeys(
                    ("decision", "reviewer", "reviewed_at", "basis"), ""
                ),
            }
        )
        if review["scope"] != review_scope:
            raise PermissionError(
                "Comparison readback draft belongs to another proposal"
            )
        review_fields(review["fields"], final=False)
        result.update(
            review_draft=review["fields"],
            draft_revision=digest(review),
            review_generation=review["generation"],
        )
        if "registration" in row:
            result["registration"] = {
                k: row["registration"][k]
                for k in (
                    "work_ref",
                    "recipe_input_id",
                    "source_input_id",
                    "review_input_id",
                )
            }
            result["registration"]["fields"] = api.read_json(
                current["private"]
                / row["registration"]["receipt_ref"]
                / "comparison-readback.json"
            )["fields"]
    if model:
        if grant["status"] != "open" or current["recovery_required"]:
            raise PermissionError("This comparison model mandate is closed")
        result["mandate"] = {
            "fields": grant["mandate"]["fields"],
            "sources": grant["mandate"]["sources"],
        }
        result["sources"] = [
            {**r, "authorized_path": str(selected(r["input_id"], loaded)[0])}
            for r in grant["mandate"]["sources"]
        ]
        result["inspection_path"] = str(
            current["output"] / grant["intake_ref"] / "inspection.json"
        )
        result["suggested_recipe_path"] = str(
            current["output"] / grant["intake_ref"] / "suggested_recipe.json"
        )
        result["method_path"] = str(root / "skills/variance-analysis/SKILL.md")
        result["boundary"] = (
            "Read the complete public skill and only the explicitly authorized originals. Inspection samples cover at most ten rows of suggested candidate columns, not the source population; inspect complete authorized originals with maintained readers when needed. Author the entire public recipe with literal reviewed periods, measures, optional units, dimensions, filters/cohorts and accounting declarations; retain unknowns. Suggested mappings are unapproved proposals. Do not invent economic causes, human approval, root-cause acceptance or reading claims. The new recipe professional_review and root_cause_review must stay pending; prior raw reviews remain separately preserved. Stage proposal={recipe:complete_recipe,note:open_items}. Full named readback, immutable conservation in a new same-engagement run, calculation and professional decisions are separate. Record only actual model exposure. No provider worker is launched."
        )
        for key in ("review_draft", "draft_revision", "review_generation"):
            result.pop(key, None)
    return result


def preflight(root: Path, loaded: dict, grant: dict, proposal: dict) -> dict:
    if (
        not isinstance(proposal, dict)
        or set(proposal) != {"recipe", "note"}
        or not isinstance(proposal["recipe"], dict)
        or not isinstance(proposal["note"], str)
        or len(proposal["note"]) > 12000
        or len(json.dumps(proposal).encode()) > 100000
    ):
        raise ValueError(
            "Stage a complete bounded public comparison recipe and literal open-items note"
        )
    values = grant["mandate"]["fields"]
    completed = subprocess.run(
        [
            sys.executable,
            "-I",
            "-B",
            str(Path(__file__).with_name("native_variance_author_bridge.py")),
            str(root),
        ],
        input=json.dumps(
            {
                "source": str(selected(values["source_input_id"], loaded)[0]),
                "recipe": proposal["recipe"],
                "context": loaded["context_path"],
                "currency": values["currency"],
                "language": values["language"],
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
            or "Public comparison schema preflight refused"
        )
    return json.loads(completed.stdout)


def conserve(
    binding: dict,
    loaded: dict,
    current: dict,
    page: dict,
    fields: dict,
    key: str,
    api: Any,
) -> dict:
    """Import actual comparison/readback receipts and start a fresh authoritative run."""
    core = archive_module(api.archive_root)
    folder, _ = engagement_scope(core, binding["client_id"], binding["engagement_id"])
    if folder.resolve() != Path(binding["client_root"]).resolve():
        raise PermissionError("Comparison successor belongs to another client")
    directory = current["private"] / page["selection"]["id"]
    receipt_ref = "variance-comparison-readback-" + digest(
        [current["scope"], page["selection"]["id"], key]
    )
    receipt_directory = current["private"] / receipt_ref
    receipt_directory.mkdir(exist_ok=False)
    readback = receipt_directory / "comparison-readback.json"
    api.atomic_json(
        readback,
        {
            "schema_version": "vera.native.variance_comparison_readback.v1",
            "scope": current["scope"],
            "case_ref": page["selection"]["id"],
            "recipe_sha256": file_hash(directory / "comparison.json"),
            "fields": fields,
            "professional_accounting_approval": False,
            "root_cause_acceptance": False,
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
        for p in (directory / "comparison.json", readback)
    ]
    chosen = page["mandate"]["sources"]
    inputs = [
        r
        for r in loaded["input_manifest"]["inputs"]
        if r["binding_id"] in {s["input_id"] for s in chosen}
    ]
    prepared = core.prepare_studio_client_workflow(
        binding["engagement_id"],
        "variance-analysis",
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
        label="Scostamenti: confronto preparato e riscontrato",
        purpose="Calcolare separatamente il confronto dopo il riscontro completo delle scelte.",
        idempotency_key="native-variance-author-"
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
    if file_hash(selected(imported[0], hydrated)[0]) != file_hash(
        directory / "comparison.json"
    ) or file_hash(selected(imported[1], hydrated)[0]) != file_hash(readback):
        raise ValueError("Registered comparison differs from the named readback")
    return {
        "binding": successor,
        "work_ref": successor["work_ref"],
        "recipe_input_id": imported[0],
        "review_input_id": imported[1],
        "source_input_id": page["mandate"]["fields"]["source_input_id"],
        "receipt_ref": receipt_ref,
        "readback_artifacts": tree_hash(receipt_directory),
    }


def dispatch(
    tool: str, args: dict, binding: dict, loaded: dict, root: Path, api: Any
) -> dict:
    action = tool.removeprefix("vera_workspace_variance_author_")
    current = context(binding, loaded, root, api)
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
        page = grant_page(current, loaded, root, args, api, model=action == "context")
        if action == "context" and args["revision"] != page["revision"]:
            raise ValueError("Stale comparison model context")
        return bounded(page, 64000 if action == "context" else 2000000)
    with api.write_lock(current["output"]):
        loaded = api.load_binding(binding)
        current = context(binding, loaded, root, api)
        if not writable(current, loaded):
            raise PermissionError(
                "Comparison authoring requires an owned running reviewer without uncertain writes"
            )
        state = current["state"]
        intent = None
        fingerprint = digest([current["scope"], tool, args])
        key = args.get("idempotency_key")
        if action in {"request", "stage", "publish", "cancel"}:
            if not isinstance(key, str) or not re.fullmatch(
                r"[A-Za-z0-9_-]{1,120}", key
            ):
                raise ValueError("Invalid comparison request identity")
            intent = current["private"] / (
                "variance-author-request-"
                + digest([current["scope"]["owner"], key])
                + ".json"
            )
            if intent.exists():
                prior = api.read_json(intent)
                if prior["request_sha256"] != fingerprint or "result" not in prior:
                    raise ValueError("Changed or uncertain comparison authoring retry")
                return prior["result"]
        if action in {"draft_save", "request"}:
            if args["revision"] != current["revision"]:
                raise ValueError("Reopen current comparison preparation")
            path, saved, stamp = draft(current, loaded, api)
            if args["expected_draft_revision"] != stamp:
                raise ValueError("Comparison preparation draft changed concurrently")
            value = choices(args["fields"], loaded, api, final=action == "request")
            if action == "draft_save":
                saved.update(fields=value, generation=saved["generation"] + 1)
                api.atomic_json(path, saved)
                return {
                    "saved": True,
                    "draft_revision": digest(saved),
                    "model_grant": False,
                }
            if args.get("confirmed") is not True or value != saved["fields"]:
                raise ValueError(
                    "Renew confirmation of the exact saved question and source choices"
                )
            identities = list(
                dict.fromkeys(
                    [
                        value["source_input_id"],
                        *value["evidence_input_ids"],
                        *(
                            [value["base_recipe_input_id"]]
                            if value["base_recipe_input_id"]
                            else []
                        ),
                    ]
                )
            )
            mandate = {
                "scope": current["scope"],
                "fields": value,
                "sources": [
                    {
                        "input_id": identity,
                        "sha256": file_hash(selected(identity, loaded)[0]),
                    }
                    for identity in identities
                ],
                "request_sha256": fingerprint,
            }
            ref = "variance-mandate-" + digest(mandate)
            intake = "variance-intake-" + digest(mandate)
            api.atomic_json(intent, {"request_sha256": fingerprint})
            engine_call(
                root,
                {
                    "operation": "inspect",
                    "source": str(selected(value["source_input_id"], loaded)[0]),
                    "output": str(current["output"] / intake),
                    "context": loaded["context_path"],
                    "language": value["language"],
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
                "professional_approval": False,
                "comparison_calculated": False,
            }
        else:
            page = grant_page(current, loaded, root, args, api)
            if page["status"] != "open" or args["revision"] != page["revision"]:
                raise ValueError("Stale or closed comparison model mandate")
            grant = next(
                g for g in state["grants"] if g["grant_ref"] == args["grant_ref"]
            )
            if action == "stage":
                checked = preflight(root, loaded, grant, args["proposal"])
                ref = "variance-authored-" + fingerprint
                directory = current["private"] / ref
                api.atomic_json(intent, {"request_sha256": fingerprint})
                directory.mkdir(exist_ok=False)
                proposal = {**args["proposal"], "recipe": checked["recipe"]}
                base = grant["mandate"]["fields"]["base_recipe_input_id"]
                if base:
                    proposal["prior_recipe_and_reviews"] = api.read_json(
                        selected(base, loaded)[0]
                    )
                api.atomic_json(directory / "proposal.json", proposal)
                api.atomic_json(directory / "comparison.json", checked["recipe"])
                api.atomic_json(directory / "validation.json", checked["validation"])
                state["proposals"].append(
                    {
                        "case_ref": ref,
                        "grant_ref": grant["grant_ref"],
                        "artifacts": tree_hash(directory),
                        "validation": checked["validation"],
                    }
                )
                result = {
                    "saved": True,
                    "case_ref": ref,
                    "validation": checked["validation"],
                    "professional_approval": False,
                }
            elif action in {"review_draft_save", "publish"}:
                if (
                    args["source_ref"] != grant["grant_ref"]
                    or args["item_id"] != args["case_ref"]
                    or args["expected_draft_revision"] != page["draft_revision"]
                ):
                    raise ValueError(
                        "Review only the exact complete comparison and current draft"
                    )
                value = review_fields(args["fields"], final=action == "publish")
                row = next(
                    r for r in state["proposals"] if r["case_ref"] == args["case_ref"]
                )
                if action == "review_draft_save":
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
                        / ("variance-readback-draft-" + args["case_ref"] + ".json"),
                        saved,
                    )
                    return {
                        "saved": True,
                        "draft_revision": digest(saved),
                        "comparison_contents_confirmed": False,
                    }
                if (
                    args.get("confirmed") is not True
                    or value != page["review_draft"]
                    or value["decision"] != "accepted"
                ):
                    raise ValueError(
                        "Renew the exact saved named comparison readback; accounting approval is separate"
                    )
                api.atomic_json(intent, {"request_sha256": fingerprint})
                registration = conserve(binding, loaded, current, page, value, key, api)
                row["registration"] = registration
                grant["status"] = "registered"
                result = {
                    "saved": True,
                    "status": "authored_comparison_registered",
                    **{
                        k: registration[k]
                        for k in (
                            "work_ref",
                            "source_input_id",
                            "recipe_input_id",
                            "review_input_id",
                        )
                    },
                    "comparison_calculated": False,
                    "professional_approval": False,
                    "run_completed": False,
                }
            elif action == "cancel":
                if args.get("confirmed") is not True:
                    raise ValueError(
                        "Confirm cancellation of this exact comparison mandate"
                    )
                api.atomic_json(intent, {"request_sha256": fingerprint})
                grant["status"] = "cancelled"
                result = {"saved": True, "status": "cancelled"}
            else:
                raise ValueError("Unknown comparison-preparation action")
        if (
            context(binding, api.load_binding(binding), root, api)["scope"]
            != current["scope"]
        ):
            raise ValueError(
                "Variance authoring source or implementation changed during conservation"
            )
        api.atomic_json(current["private"] / "variance-author-state.json", state)
        api.atomic_json(intent, {"request_sha256": fingerprint, "result": result})
        return result
