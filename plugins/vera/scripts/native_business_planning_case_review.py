"""Apply exact human attestations to a new case without changing business inputs."""

from __future__ import annotations

import copy
import os
import re
import tempfile
from pathlib import Path
from typing import Any

from native_bank_preparation import tree_hash
from native_sales_plan_authoring import owner_scope

__all__ = ["audit", "dispatch"]

REVIEWABLE = {
    "case_review",
    "sources",
    "evidence",
    "assumptions",
    "decisions",
    "narrative",
}


def audit(output: Path, private: Path, saved: dict | None, api: Any) -> dict:
    """Retain interrupted projection/execution evidence instead of adopting it."""
    path = private / "planning-case-review-state.json"
    state = api.read_json(path) if path.exists() else {"cases": [], "launches": []}
    rows = state["cases"]
    known = set()
    for row in rows:
        reference = row["case_ref"]
        if (
            not re.fullmatch(r"planning-case-review-[0-9a-f]{64}", reference)
            or reference in known
            or not saved
            or row["generation"] != saved["generation"]
            or tree_hash(output / reference) != row["artifacts"]
        ):
            raise ValueError("Reviewed planning case or its receipt changed")
        known.add(reference)
        lineage = api.read_json(output / reference / "review_lineage.json")
        case = api.read_json(output / reference / "case.json")
        if reference != "planning-case-review-" + api.digest([case, lineage]):
            raise ValueError("Reviewed planning case differs from its exact lineage")
    requests = [api.read_json(p) for p in private.glob("planning-case-request-*.json")]
    launches = [api.read_json(p) for p in private.glob("planning-case-launch-*.json")]
    uncertain = any("result" not in r for r in [*requests, *launches])
    uncertain |= any(p.name not in known for p in output.glob("planning-case-review-*"))
    uncertain |= any(
        not any(
            r.get("result", {}).get("case_ref") == row["case_ref"] for r in requests
        )
        for row in rows
    )
    uncertain |= any(
        r.get("result", {}).get("case_ref") not in known
        for r in requests
        if "result" in r
    )
    retained_launches = state.get("launches", [])
    launch_names = {row["request_ref"] for row in retained_launches}
    for row in retained_launches:
        name = row["request_ref"]
        if not re.fullmatch(r"planning-case-launch-[0-9a-f]{64}\.json", name):
            raise ValueError("Invalid reviewed-case execution receipt")
        receipt = api.read_json(private / name) if (private / name).exists() else {}
        uncertain |= (
            receipt.get("result") != row["result"]
            or receipt.get("output_hashes") != row["output_hashes"]
        )
    uncertain |= any(
        p.name not in launch_names for p in private.glob("planning-case-launch-*.json")
    )
    return {
        "cases": rows,
        "launches": retained_launches,
        "recovery_required": uncertain,
    }


def project(current: dict, loaded: dict, binding: dict, root: Path, api: Any) -> dict:
    """Mechanically copy only exact human decisions into public review fields."""
    from native_business_planning import replay
    from native_business_planning_review import selected

    original = replay(current, loaded, root, api)["plan"]
    case = copy.deepcopy(original["case"])
    latest = {}
    for row in current["professional_reviews"]["reviews"]:
        decision = api.read_json(
            current["output"] / row["review_ref"] / "professional_review.json"
        )
        target = decision["target"]
        if target["collection"] not in REVIEWABLE:
            continue
        actual, record = selected(target, current, loaded, root, api, plan=original)
        if actual != target or record != decision["record"]:
            raise ValueError("Review no longer matches its complete original record")
        if decision["owner"][1:] != owner_scope(binding)[1:]:
            raise PermissionError("Planning decision belongs to another tenant")
        latest[(target["collection"], target["index"])] = (row["review_ref"], decision)
    changes = []
    for (collection, index), (reference, decision) in latest.items():
        fields = decision["fields"]
        # These are literal human attestations, not a semantic classifier or
        # automatic approval of the other records, the plan or its next version.
        positive = fields["action"] == "accept"
        metadata = {
            "status": "reviewed" if positive else "unreviewed",
            "reviewer": fields["reviewer"],
            "reviewed_at": fields["reviewed_at"],
        }
        if collection == "case_review":
            case["review"] = metadata
        elif collection == "sources":
            case[collection][index]["review_status"] = (
                "reviewed" if positive else "unverified"
            )
        elif collection == "narrative":
            case[collection][index]["review"] = metadata
        else:
            case[collection][index].update(metadata)
        changes.append(
            {
                "collection": collection,
                "index": index,
                "review_ref": reference,
                "fields": fields,
            }
        )
    return {
        "case": case,
        "original": original,
        "changes": changes,
        "lineage": {
            "schema_version": "vera.native_planning_case_review.v1",
            "owner": owner_scope(binding),
            "generation": current["saved"]["generation"],
            "original_case_sha256": original["case_sha256"],
            "original_plan_content_sha256": original["content_sha256"],
            "original_artifacts": current["saved"]["artifacts"],
            "review_chain_sha256": api.digest(
                current["professional_reviews"]["reviews"]
            ),
            "changes": changes,
            "professional_plan_approval": False,
            "substantive_business_inputs_changed": False,
        },
    }


def compile_case(path: Path, case: dict, loaded: dict, root: Path, api: Any) -> dict:
    """Use unchanged public rules; review cannot clear substantive missing evidence."""
    from native_business_planning import engine_call

    with tempfile.TemporaryDirectory(
        prefix="planning-read-", dir=path.parent
    ) as temporary:
        selected_case = Path(temporary) / "case.json"
        api.atomic_json(selected_case, case)
        return engine_call(
            root,
            {
                "operation": "inspect",
                "case": str(selected_case),
                "source_root": str(Path(loaded["run_root"]) / "inputs"),
            },
        )


def owned_core(binding: dict, api: Any) -> Any:
    """New runs require actual configured Archive ownership, never operator bindings."""
    from native_archive_navigation import archive_module, engagement_scope

    if not api.owned_archive:
        raise PermissionError(
            "Reviewed-case execution requires the configured owned Archive"
        )
    core = archive_module(api.archive_root)
    folder, engagement = engagement_scope(
        core, binding["client_id"], binding["engagement_id"]
    )
    if (
        folder.resolve() != Path(binding["client_root"]).resolve()
        or engagement["status"] != "open"
    ):
        raise PermissionError("Reviewed cases require the exact open owned engagement")
    return core


def dispatch(
    tool: str, args: dict, binding: dict, loaded: dict, root: Path, api: Any
) -> dict:
    """Preview, retain and explicitly execute one metadata-only case revision."""
    from native_archive_navigation import work_ref
    from native_business_planning import bounded, context
    from native_business_planning import dispatch as planning_dispatch
    from native_business_planning_authoring import archive_contract
    from native_business_planning_review import selected

    current = context(binding, loaded, root, api)
    if args.get("collection") != "case_review" or args.get("index") != 0:
        raise ValueError("Choose the complete exact case review, not a header or page")
    selected(args, current, loaded, root, api)
    writable = (
        loaded["run"]["status"] == "running"
        and "REVIEWER" in os.environ.get("VERA_WORKSPACE_ROLES", "").split(",")
        and api.owned_archive
    )
    if tool == "vera_workspace_business_plan_case_review_read":
        if args["revision"] != current["revision"]:
            raise ValueError("Reopen the current reviewed-case proposal")
        result = {
            "work_ref": args["work_ref"],
            "revision": current["revision"],
            "selection": {"id": "case_review:0"},
            "cases": [
                {"case_ref": r["case_ref"], "status": r["status"]}
                for r in current["case_reviews"]["cases"]
            ],
            "can_prepare": writable
            and not current["professional_reviews"]["recovery_required"],
            "can_launch": False,
            "professional_plan_approval": False,
            "recovery_required": current["professional_reviews"]["recovery_required"],
        }
        if args.get("case_ref"):
            row = next(
                (
                    r
                    for r in current["case_reviews"]["cases"]
                    if r["case_ref"] == args["case_ref"]
                ),
                None,
            )
            if row is None:
                raise ValueError("Choose an exact retained reviewed case")
            directory = current["output"] / row["case_ref"]
            case = api.read_json(directory / "case.json")
            compiled = compile_case(
                current["private"] / "case-review-inspect.json", case, loaded, root, api
            )
            if compiled["plan"] != api.read_json(directory / "plan.json") or compiled[
                "report"
            ] != (directory / "report.html").read_text(encoding="utf-8"):
                raise ValueError("Reviewed case differs from unchanged public replay")
            lineage = api.read_json(directory / "review_lineage.json")
            result.update(
                {
                    "selected_case": row["case_ref"],
                    "plan": compiled["plan"],
                    "report": compiled["report"],
                    "changes": lineage["changes"],
                    "can_launch": result["can_prepare"]
                    and lineage["owner"] == owner_scope(binding)
                    and lineage["review_chain_sha256"]
                    == api.digest(current["professional_reviews"]["reviews"]),
                }
            )
        else:
            proposal = project(current, loaded, binding, root, api)
            compiled = compile_case(
                current["private"] / "case-review-inspect.json",
                proposal["case"],
                loaded,
                root,
                api,
            )
            result.update(
                {
                    "plan": compiled["plan"],
                    "report": compiled["report"],
                    "changes": proposal["changes"],
                    "can_prepare": result["can_prepare"]
                    and proposal["case"] != proposal["original"]["case"],
                }
            )
        return bounded(result, 2000000)
    if not writable:
        raise PermissionError("Reviewed cases require a running reviewer-owned run")
    if tool not in {
        "vera_workspace_business_plan_case_review_prepare",
        "vera_workspace_business_plan_case_review_launch",
    }:
        raise ValueError("Unknown reviewed-case operation")
    if args.get("confirmed") is not True:
        raise ValueError("Explicit app selection of the reviewed case is required")
    key = args["idempotency_key"]
    if not re.fullmatch(r"[A-Za-z0-9_-]{1,120}", key):
        raise ValueError("Invalid reviewed-case request key")
    with api.write_lock(current["output"]):
        loaded = api.load_binding(binding)
        current = context(binding, loaded, root, api)
        selected(args, current, loaded, root, api)
        core = owned_core(binding, api)
        contract = archive_contract(core)
        launching = tool.endswith("_launch")
        intent = current["private"] / (
            ("planning-case-launch-" if launching else "planning-case-request-")
            + api.digest([owner_scope(binding), key])
            + ".json"
        )
        request_hash = api.digest([tool, owner_scope(binding), args])
        if intent.exists():
            retained = api.read_json(intent)
            if (
                retained["request_sha256"] != request_hash
                or "result" not in retained
                or current["professional_reviews"]["recovery_required"]
            ):
                raise ValueError("Reviewed-case request changed or requires recovery")
            if retained["archive_implementation"] != contract:
                raise ValueError("Reviewed-case Archive implementation changed")
            if launching:
                prior = core.ledger.load_run(
                    Path(binding["client_root"]),
                    binding["engagement_id"],
                    retained["result"]["run_id"],
                )
                if (
                    tree_hash(
                        Path(prior["output_dir"]) / retained["result"]["generation"]
                    )
                    != retained["output_hashes"]
                ):
                    raise ValueError("Reviewed-case execution outputs changed")
            return retained["result"]
        if (
            loaded["run"]["status"] != "running"
            or args["revision"] != current["revision"]
            or current["professional_reviews"]["recovery_required"]
        ):
            raise ValueError("Reviewed-case authority changed or requires recovery")
        if not launching:
            proposal = project(current, loaded, binding, root, api)
            if proposal["case"] == proposal["original"]["case"]:
                raise ValueError("No exact human review changes to apply")
            compiled = compile_case(
                current["private"] / "case-review-inspect.json",
                proposal["case"],
                loaded,
                root,
                api,
            )
            lineage = {**proposal["lineage"], "archive_implementation": contract}
            reference = "planning-case-review-" + api.digest(
                [proposal["case"], lineage]
            )
            directory = current["output"] / reference
            if directory.exists():
                raise ValueError(
                    "This exact case already exists; select its retained receipt"
                )
            if (
                context(binding, api.load_binding(binding), root, api)["revision"]
                != current["revision"]
            ):
                raise ValueError("Planning changed before reviewed-case preparation")
            api.atomic_json(intent, {"request_sha256": request_hash})
            directory.mkdir(mode=0o700)
            api.atomic_json(directory / "case.json", proposal["case"])
            api.atomic_json(directory / "plan.json", compiled["plan"])
            api.atomic_json(directory / "review_lineage.json", lineage)
            (directory / "report.html").write_text(compiled["report"], encoding="utf-8")
            after_loaded = api.load_binding(binding)
            after = context(binding, after_loaded, root, api)
            if (
                after_loaded["run"] != loaded["run"]
                or after_loaded["input_manifest"] != loaded["input_manifest"]
                or after["saved"] != current["saved"]
                or after["implementation"] != current["implementation"]
                or after["professional_reviews"]["reviews"]
                != current["professional_reviews"]["reviews"]
                or archive_contract(core) != contract
            ):
                raise ValueError(
                    "Planning changed during preparation; recovery required"
                )
            row = {
                "case_ref": reference,
                "generation": args["generation"],
                "status": compiled["plan"]["status"],
                "artifacts": tree_hash(directory),
            }
            api.atomic_json(
                current["private"] / "planning-case-review-state.json",
                {
                    "cases": [*current["case_reviews"]["cases"], row],
                    "launches": current["case_reviews"]["launches"],
                },
            )
            result = {
                "saved": True,
                "case_ref": reference,
                "status": compiled["plan"]["status"],
                "professional_plan_approval": False,
                "run_created": False,
            }
            api.atomic_json(
                intent,
                {
                    "request_sha256": request_hash,
                    "archive_implementation": contract,
                    "result": result,
                },
            )
            return result
        row = next(
            (
                r
                for r in current["case_reviews"]["cases"]
                if r["case_ref"] == args["case_ref"]
            ),
            None,
        )
        if row is None:
            raise ValueError("Choose one exact retained reviewed case")
        directory = current["output"] / row["case_ref"]
        lineage = api.read_json(directory / "review_lineage.json")
        if (
            lineage["owner"] != owner_scope(binding)
            or lineage["archive_implementation"] != contract
            or lineage["review_chain_sha256"]
            != api.digest(current["professional_reviews"]["reviews"])
        ):
            raise ValueError(
                "Reviewed case belongs to another owner or earlier decisions"
            )
        proposal = project(current, loaded, binding, root, api)
        case = api.read_json(directory / "case.json")
        if case != proposal["case"]:
            raise ValueError("Reviewed case differs from the exact human decisions")
        compiled = compile_case(
            current["private"] / "case-review-inspect.json", case, loaded, root, api
        )
        if compiled["plan"] != api.read_json(directory / "plan.json") or compiled[
            "report"
        ] != (directory / "report.html").read_text(encoding="utf-8"):
            raise ValueError("Reviewed case differs from its public replay")
        inputs, upstream = [], []
        for source in loaded["input_manifest"]["inputs"]:
            if source["kind"] == "import":
                inputs.append(source["binding_id"])
            elif source["kind"] == "upstream_artifact":
                upstream.append(
                    {
                        "run_id": source["upstream_run_id"],
                        "artifact_id": source["upstream_artifact_id"],
                        "role": source["role"],
                    }
                )
            else:
                raise ValueError("Unknown planning input receipt kind")
        if (
            context(binding, api.load_binding(binding), root, api)["revision"]
            != current["revision"]
        ):
            raise ValueError("Planning changed before reviewed-case execution")
        api.atomic_json(intent, {"request_sha256": request_hash})
        folder = Path(binding["client_root"])
        imported = core.ledger.import_document(
            folder,
            binding["client_id"],
            binding["engagement_id"],
            (directory / "case.json").resolve(),
            "source",
        )["receipt"]
        # A control receipt preserves the actual attestation lineage in the new
        # run. It is not invented business evidence or an additional case source.
        review_receipt = core.ledger.import_document(
            folder,
            binding["client_id"],
            binding["engagement_id"],
            (directory / "review_lineage.json").resolve(),
            "support",
        )["receipt"]
        prepared = core.prepare_studio_client_workflow(
            binding["engagement_id"],
            "business-planning",
            input_ids=[*inputs, imported["input_id"], review_receipt["input_id"]],
            upstream_artifacts=upstream,
            label=loaded["run"]["label"],
            purpose="Ricalcolo dello stesso caso dopo le decisioni professionali esatte",
            idempotency_key="native-planning-review-"
            + api.digest([owner_scope(binding), key]),
            new_run=True,
        )
        run_id = prepared["run"]["run_id"]
        core.start_studio_client_workflow(
            binding["client_id"], binding["engagement_id"], run_id
        )
        next_binding = {**binding, "run_id": run_id}
        next_loaded = api.load_binding(next_binding)
        exact = context(next_binding, next_loaded, root, api)
        reference = work_ref(binding["client_id"], binding["engagement_id"], run_id)
        produced = planning_dispatch(
            "vera_workspace_business_plan_prepare",
            {
                "work_ref": reference,
                "revision": exact["revision"],
                "case_input_id": imported["input_id"],
                "idempotency_key": "reviewed-case",
            },
            next_binding,
            next_loaded,
            root,
            api,
        )
        produced_directory = Path(next_loaded["output_dir"]) / produced["generation"]
        after_loaded = api.load_binding(binding)
        after = context(binding, after_loaded, root, api)
        if (
            after_loaded["run"] != loaded["run"]
            or after_loaded["input_manifest"] != loaded["input_manifest"]
            or after["saved"] != current["saved"]
            or after["implementation"] != current["implementation"]
            or after["professional_reviews"]["reviews"]
            != current["professional_reviews"]["reviews"]
            or archive_contract(core) != contract
        ):
            raise ValueError("Planning changed during execution; recovery required")
        if (
            api.read_json(produced_directory / "business_plan.json") != compiled["plan"]
            or (produced_directory / "business_plan_review.html").read_text(
                encoding="utf-8"
            )
            != compiled["report"]
        ):
            raise ValueError("Executed reviewed case differs from its original preview")
        result = {
            "saved": True,
            "status": produced["status"],
            "work_ref": reference,
            "run_id": run_id,
            "generation": produced["generation"],
            "professional_plan_approval": False,
            "run_completed": False,
        }
        output_hashes = tree_hash(produced_directory)
        api.atomic_json(
            current["private"] / "planning-case-review-state.json",
            {
                "cases": current["case_reviews"]["cases"],
                "launches": [
                    *current["case_reviews"]["launches"],
                    {
                        "request_ref": intent.name,
                        "result": result,
                        "output_hashes": output_hashes,
                    },
                ],
            },
        )
        api.atomic_json(
            intent,
            {
                "request_sha256": request_hash,
                "archive_implementation": contract,
                "result": result,
                "output_hashes": output_hashes,
            },
        )
        return result
