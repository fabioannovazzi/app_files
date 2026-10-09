"""User-chosen planning mandates, model-authored cases and fresh ledger runs."""

from __future__ import annotations

import json
import os
import re
import secrets
import shutil
from pathlib import Path
from typing import Any

from native_archive_navigation import (
    archive_module,
    engagement_scope,
    fingerprint,
    page,
    preparation_catalogue,
    reviewer,
    work_ref,
)
from native_bank_preparation import file_hash, tree_hash
from native_business_planning import engine_call

__all__ = ["dispatch"]


def owner(args: dict) -> dict:
    """Bind staging authority to the same explicit local owner and engagement."""
    return {
        "actor": os.environ["VERA_WORKSPACE_ACTOR_ID"],
        "tenant": os.environ["VERA_WORKSPACE_TENANT_ID"],
        "client_id": args["client_id"],
        "engagement_id": args["engagement_id"],
    }


def directory(core: Any, folder: Path, args: dict) -> Path:
    path = (
        core.ledger._engagement_root(folder, args["engagement_id"])
        / ".native-business-planning"
        / fingerprint(owner(args))
    )
    if any(p.is_symlink() for p in (path, *path.parents)):
        raise ValueError("Planning authoring state cannot use linked directories")
    return path


def contract(root: Path) -> dict:
    return {
        "public": engine_call(root, {"operation": "contract"}),
        "authoring": file_hash(Path(__file__)),
        "native": {
            name: file_hash(Path(__file__).with_name(name))
            for name in (
                "native_business_planning.py",
                "native_business_planning_bridge.py",
                "native_business_planning_review.py",
                "native_business_planning_case_review.py",
                "native_archive_navigation.py",
            )
        },
    }


def archive_contract(core: Any) -> dict:
    return {
        Path(module.__file__).name: file_hash(Path(module.__file__))
        for module in (core, core.ledger)
    }


def sources(core: Any, folder: Path, args: dict, descriptor: dict) -> list[dict]:
    """Use the maintained ledger locators and complete upstream handoff gate."""
    ids = descriptor["input_ids"]
    if not isinstance(ids, list) or len(ids) > 999 or len(set(ids)) != len(ids):
        raise ValueError("Choose distinct exact imported inputs")
    rows = [
        core.ledger._input_binding(
            core.ledger.load_input_receipt(folder, args["engagement_id"], value)
        )
        for value in ids
    ]
    upstream = descriptor["upstream_artifacts"]
    if not isinstance(upstream, list) or len(upstream) > 999:
        raise ValueError("Choose exact sealed supporting artifacts")
    for item in upstream:
        if not isinstance(item, dict) or set(item) != {"run_id", "artifact_id"}:
            raise ValueError("Choose exact sealed supporting artifacts")
        rows.append(
            core.ledger._load_artifact_binding(
                folder, args["engagement_id"], {**item, "role": "source"}
            )
        )
    parent = descriptor["parent"]
    if parent is not None:
        if not isinstance(parent, dict) or set(parent) != {"run_id", "artifact_id"}:
            raise ValueError("Choose one exact sealed predecessor")
        row = core.ledger._load_artifact_binding(
            folder, args["engagement_id"], {**parent, "role": "prior_plan"}
        )
        if row["upstream_workflow_id"] != "business-planning":
            raise ValueError("Predecessor must be a sealed Business Planning plan")
        value = json.loads(
            (folder / row["source_relative_path"]).read_text(encoding="utf-8")
        )
        if value.get("schema_version") != "mparanza.business_planning_plan.v3":
            raise ValueError("Select the exact canonical predecessor plan JSON")
        rows.append(row)
    if len({row["binding_id"] for row in rows}) != len(rows) or len(rows) > (
        1000 if "statement_input_id" in descriptor else 999
    ):
        raise ValueError("Choose distinct sources within the complete native limit")
    if not rows:
        raise ValueError("The literal mandate must be registered before authoring")
    for row in rows:
        if file_hash(folder / row["source_relative_path"]) != row["sha256"]:
            raise ValueError("Selected planning source changed")
    return rows


def grant(
    core: Any, folder: Path, args: dict, root: Path, api: Any
) -> tuple[Path, dict]:
    reference = args["grant_ref"]
    if not re.fullmatch(r"author-[0-9a-f]{64}", reference):
        raise ValueError("Choose an exact user-authorized planning mandate")
    base = directory(core, folder, args) / reference
    value = api.read_json(base / "mandate.json")
    request_ref = value["request_ref"]
    if not re.fullmatch(r"request-[0-9a-f]{64}\.json", request_ref):
        raise ValueError("Invalid retained planning request")
    receipt = api.read_json(base.parent / request_ref)
    if receipt.get("result", {}).get("grant_ref") != reference or receipt.get(
        "mandate_sha256"
    ) != file_hash(base / "mandate.json"):
        raise ValueError("Retained planning mandate changed or requires recovery")
    if (
        value["owner"] != owner(args)
        or value["grant_ref"] != reference
        or value["implementation"] != contract(root)
        or value["archive_implementation"] != archive_contract(core)
    ):
        raise ValueError("Planning mandate owner or implementation changed")
    if sources(core, folder, args, value["descriptor"]) != value["sources"]:
        raise ValueError("Planning mandate source receipts changed")
    if tree_hash(base / "inputs") != value["input_hashes"]:
        raise ValueError("Retained authoring evidence changed")
    return base, value


def uncertain(base: Path, api: Any) -> bool:
    """An unresolved write blocks distinct requests rather than duplicating work."""
    return any(
        "result" not in api.read_json(path)
        for pattern in ("stage-request-*.json", "launch-request-*.json")
        for path in base.glob(pattern)
    )


def intake(home: Path, args: dict, api: Any, revision: str) -> dict:
    path = home / "intake-draft.json"
    value = api.read_json(path) if path.exists() else None
    if value and value["owner"] != owner(args):
        raise ValueError("Planning draft belongs to another owner")
    return {
        "draft_revision": file_hash(path) if value else "",
        "fields": (
            value["fields"]
            if value
            else {
                "input_ids": [],
                "upstream_artifacts": [],
                "parent": None,
                "question": "",
                "label": "",
                "purpose": "",
            }
        ),
        "stale": bool(value and value["scope_revision"] != revision),
    }


def staged(base: Path, api: Any) -> dict | None:
    path = base / "stage-state.json"
    state = api.read_json(path) if path.exists() else None
    known = {row["stage_ref"] for row in state["stages"]} if state else set()
    if any(p.name not in known for p in base.glob("case-*")):
        raise ValueError("Unreceipted planning proposal requires specialist recovery")
    if state:
        for row in state["stages"]:
            if tree_hash(base / row["stage_ref"]) != row["artifacts"]:
                raise ValueError("Retained planning proposal changed")
    return state


def inspect(base: Path, value: dict, case: dict, root: Path, api: Any) -> dict:
    """Close exact selected bytes and public replay; never judge the business case."""
    indexed = {
        row["execution_relative_path"].removeprefix("inputs/"): row
        for row in value["sources"]
    }
    if (
        not isinstance(case, dict)
        or case.get("schema_version") != "mparanza.business_planning_case.v3"
    ):
        raise ValueError("Model must author the shared Business Planning v3 case")
    declared = case.get("sources", [])
    if (
        not isinstance(declared, list)
        or len(declared) != len(indexed)
        or {row["path"] for row in declared} != set(indexed)
    ):
        raise ValueError(
            "Authored case must retain every selected source, including contradictions"
        )
    parent = value["descriptor"]["parent"]
    parents = [row for row in declared if row["role"] == "prior_plan"]
    if len(parents) != int(parent is not None):
        raise ValueError("Use only the explicitly selected sealed predecessor")
    for row in declared:
        bound = indexed[row["path"]]
        if row["sha256"] != bound["sha256"] or (row["role"] == "prior_plan") != (
            bound["role"] == "prior_plan"
        ):
            raise ValueError("Authored source identity or predecessor role disagrees")
    # Fresh human attestations cannot be manufactured by model staging. Exact
    # retained records remain available to the model, but new drafts stay partial.
    review = case.get("review", {})
    if review != {"status": "unreviewed", "reviewer": "", "reviewed_at": ""}:
        raise ValueError(
            "A model-authored case starts without a new professional attestation"
        )
    original = []
    original_sources = []
    for row in value["sources"]:
        path = base / "inputs" / row["execution_relative_path"].removeprefix("inputs/")
        if path.suffix.lower() != ".json":
            continue
        try:
            source = json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, UnicodeDecodeError):
            # A selected data file is not necessarily a planning-case document.
            # It remains complete evidence, but cannot confer an attestation.
            continue
        if isinstance(source, dict) and source.get("schema_version") in {
            "mparanza.business_planning_case.v3",
            "mparanza.business_planning_plan.v3",
        }:
            previous = source.get("case", source)
            original_sources.extend(previous.get("sources", []))
            original.extend(
                record
                for collection in (
                    "evidence",
                    "assumptions",
                    "decisions",
                    "observations",
                    "narrative",
                )
                for record in previous.get(collection, [])
            )
    for collection in (
        "evidence",
        "assumptions",
        "decisions",
        "observations",
        "narrative",
    ):
        for record in case.get(collection, []):
            metadata = record.get("review", record)
            if (
                metadata.get("status") in {"reviewed", "confirmed"}
                or metadata.get("reviewer")
                or metadata.get("reviewed_at")
            ) and record not in original:
                raise ValueError(
                    "Fresh record attestations require actual professional review, not model completion"
                )
    for row in declared:
        if row.get("review_status") in {"reviewed", "confirmed"}:
            retained = {key: item for key, item in row.items() if key != "path"}
            if retained not in [
                {key: item for key, item in source.items() if key != "path"}
                for source in original_sources
            ]:
                raise ValueError("A fresh source cannot receive model-invented review")
    path = base / "inspect-case.json"
    api.atomic_json(path, case)
    try:
        return engine_call(
            root,
            {
                "operation": "inspect",
                "case": str(path),
                "source_root": str(base / "inputs"),
            },
        )
    finally:
        path.unlink(missing_ok=True)


def dispatch(archive_root: Path, root: Path, tool: str, args: dict, api: Any) -> dict:
    """Stage only user-requested analysis; app execution uses a fresh real run."""
    core = archive_module(archive_root)
    folder, engagement = engagement_scope(
        core, args["client_id"], args["engagement_id"]
    )
    home = directory(core, folder, args)
    if tool in {
        "vera_workspace_business_plan_author_draft_store",
        "vera_workspace_business_plan_author_draft_clear",
    }:
        current = preparation_catalogue(archive_root, args)
        if (
            not current["can_prepare"]
            or args.get("confirmed") is not True
            or args["scope_revision"] != current["scope_revision"]
        ):
            raise PermissionError("Reopen the current reviewer-owned planning intake")
        home.mkdir(mode=0o700, parents=True, exist_ok=True)
        with api.write_lock(home / "outputs"):
            draft = intake(home, args, api, current["scope_revision"])
            if args["expected_draft_revision"] != draft["draft_revision"]:
                raise ValueError("Planning intake draft changed; reopen before writing")
            path = home / "intake-draft.json"
            if tool.endswith("_clear"):
                path.unlink(missing_ok=True)
                return {
                    "saved": True,
                    "status": "planning_intake_discarded",
                    "draft_revision": "",
                }
            fields = args["fields"]
            if not isinstance(fields, dict) or set(fields) != {
                "input_ids",
                "upstream_artifacts",
                "parent",
                "question",
                "label",
                "purpose",
            }:
                raise ValueError("Retain only literal unfinished planning choices")
            for key, maximum in (("question", 4000), ("label", 160), ("purpose", 500)):
                if not isinstance(fields[key], str) or len(fields[key]) > maximum:
                    raise ValueError("Invalid literal planning intake field")
            if (
                not isinstance(fields["input_ids"], list)
                or len(fields["input_ids"]) > 999
                or any(
                    not isinstance(item, str) or not item or len(item) > 200
                    for item in fields["input_ids"]
                )
            ):
                raise ValueError("Invalid exact draft input choices")
            if (
                not isinstance(fields["upstream_artifacts"], list)
                or len(fields["upstream_artifacts"]) > 999
            ):
                raise ValueError("Invalid exact draft upstream choices")
            for item in [
                *fields["upstream_artifacts"],
                *([fields["parent"]] if fields["parent"] is not None else []),
            ]:
                if (
                    not isinstance(item, dict)
                    or set(item) != {"run_id", "artifact_id"}
                    or any(
                        not isinstance(text, str) or not text or len(text) > 200
                        for text in item.values()
                    )
                ):
                    raise ValueError("Invalid exact draft artifact choice")
            api.atomic_json(
                path,
                {
                    "owner": owner(args),
                    "scope_revision": current["scope_revision"],
                    "fields": fields,
                },
            )
            return {
                "saved": True,
                "status": "planning_intake_draft_saved",
                "draft_revision": file_hash(path),
                "professional_approval": False,
            }
    if tool == "vera_workspace_business_plan_author_setup":
        view = preparation_catalogue(archive_root, args)
        grants = []
        for path in sorted(home.glob("author-*/mandate.json")):
            value = api.read_json(path)
            if value["owner"] != owner(args):
                raise ValueError("Planning mandate belongs to another owner")
            grants.append(
                {
                    "grant_ref": value["grant_ref"],
                    "question": value["descriptor"]["question"],
                    "label": value["descriptor"]["label"],
                }
            )
        if len(grants) > 1000:
            raise ValueError("Planning mandate catalogue exceeds native limit")
        mandates = page(grants, {"offset": args.get("mandate_offset", 0)})
        for row in view["upstream_rows"]:
            row["predecessor_eligible"] = False
            loaded = core.ledger.load_run(folder, args["engagement_id"], row["run_id"])
            if loaded["run"]["workflow_id"] == "business-planning" and row[
                "path"
            ].endswith(".json"):
                content = json.loads(
                    (Path(loaded["output_dir"]) / row["path"]).read_text(
                        encoding="utf-8"
                    )
                )
                row["predecessor_eligible"] = (
                    isinstance(content, dict)
                    and content.get("schema_version")
                    == "mparanza.business_planning_plan.v3"
                )
        return {
            **view,
            "mandates": mandates,
            "draft": intake(home, args, api, view["scope_revision"]),
            "professional_approval": False,
        }
    if tool == "vera_workspace_business_plan_author_request":
        if (
            not reviewer()
            or engagement["status"] != "open"
            or args.get("confirmed") is not True
        ):
            raise PermissionError(
                "An open engagement and explicit reviewer request are required"
            )
        current = preparation_catalogue(archive_root, args)
        home.mkdir(mode=0o700, parents=True, exist_ok=True)
        with api.write_lock(home / "outputs"):
            intent = home / (
                "request-" + fingerprint(args["idempotency_key"]) + ".json"
            )
            request_hash = fingerprint(args)
            if intent.exists():
                previous = api.read_json(intent)
                if (
                    previous["request_sha256"] != request_hash
                    or "result" not in previous
                ):
                    raise ValueError(
                        "Planning request changed or requires specialist recovery"
                    )
                grant(
                    core,
                    folder,
                    {**args, "grant_ref": previous["result"]["grant_ref"]},
                    root,
                    api,
                )
                return previous["result"]
            if any(
                "result" not in api.read_json(path)
                for path in home.glob("request-*.json")
            ):
                raise ValueError(
                    "Uncertain planning request requires specialist recovery"
                )
            if args["scope_revision"] != current["scope_revision"]:
                raise ValueError("Reopen current engagement inputs")
            draft = intake(home, args, api, current["scope_revision"])
            if (
                args["expected_draft_revision"] != draft["draft_revision"]
                or draft["stale"]
            ):
                raise ValueError(
                    "Reopen or explicitly discard the changed planning intake"
                )
            descriptor = {
                key: args[key]
                for key in (
                    "input_ids",
                    "upstream_artifacts",
                    "parent",
                    "question",
                    "label",
                    "purpose",
                )
            }
            if draft["draft_revision"] and draft["fields"] != descriptor:
                raise ValueError(
                    "Request must match the exact saved literal planning draft"
                )
            for key, maximum in (("question", 4000), ("label", 160), ("purpose", 500)):
                if (
                    not isinstance(descriptor[key], str)
                    or not descriptor[key].strip()
                    or len(descriptor[key]) > maximum
                ):
                    raise ValueError(
                        "Provide the actual planning question and run label/purpose"
                    )
            # Validate all supplied identities before the first durable write.
            if (
                descriptor["input_ids"]
                or descriptor["upstream_artifacts"]
                or descriptor["parent"]
            ):
                sources(core, folder, args, descriptor)
            reference = "author-" + secrets.token_hex(32)
            base = home / reference
            implementation = contract(root)
            api.atomic_json(intent, {"request_sha256": request_hash})
            base.mkdir(mode=0o700)
            literal = base / "user-statement.txt"
            literal.write_text(descriptor["question"], encoding="utf-8")
            receipt = core.ledger.import_document(
                folder,
                args["client_id"],
                args["engagement_id"],
                literal.resolve(),
                "source",
            )["receipt"]
            descriptor["input_ids"] = list(
                dict.fromkeys([*descriptor["input_ids"], receipt["input_id"]])
            )
            descriptor["statement_input_id"] = receipt["input_id"]
            selected = sources(core, folder, args, descriptor)
            for row in selected:
                destination = (
                    base
                    / "inputs"
                    / row["execution_relative_path"].removeprefix("inputs/")
                )
                destination.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
                shutil.copyfile(folder / row["source_relative_path"], destination)
                if file_hash(destination) != row["sha256"]:
                    raise ValueError(
                        "Planning source changed during retention; recovery required"
                    )
            value = {
                "schema_version": "vera.native_planning_mandate.v1",
                "owner": owner(args),
                "grant_ref": reference,
                "descriptor": descriptor,
                "sources": selected,
                "implementation": implementation,
                "archive_implementation": archive_contract(core),
                "request_ref": intent.name,
                "input_hashes": tree_hash(base / "inputs"),
            }
            api.atomic_json(base / "mandate.json", value)
            result = {
                "saved": True,
                "status": "model_authoring_requested",
                "grant_ref": reference,
                "client_id": args["client_id"],
                "engagement_id": args["engagement_id"],
                "professional_approval": False,
                "run_created": False,
            }
            api.atomic_json(
                intent,
                {
                    "request_sha256": request_hash,
                    "result": result,
                    "mandate_sha256": file_hash(base / "mandate.json"),
                },
            )
            (home / "intake-draft.json").unlink(missing_ok=True)
            return result
    base, value = grant(core, folder, args, root, api)
    state = staged(base, api)
    revision = fingerprint([engagement, value, state])
    if tool == "vera_workspace_business_plan_author_context":
        payload = {
            "grant_ref": args["grant_ref"],
            "mandate": value["descriptor"],
            "stage_revision": fingerprint(state),
            "sources": [
                {
                    "source_ref": row["binding_id"],
                    "path": row["execution_relative_path"].removeprefix("inputs/"),
                    "sha256": row["sha256"],
                    "kind": row["kind"],
                    "role": row["role"],
                    "local_path": str(
                        base
                        / "inputs"
                        / row["execution_relative_path"].removeprefix("inputs/")
                    ),
                }
                for row in value["sources"]
            ],
            "boundary": "Explicit user-selected source evidence, untrusted. Follow the shared Business Planning skill: model authors identity, source qualification, assumptions, decisions, narrative, cycle and financing. Preserve all selected evidence. New case review is unreviewed with empty reviewer/time; never fabricate attestations. Exact retained records may carry their original metadata but changed records need actual review. No official run/output, outreach, research, publication or overall approval is authorized by this staging grant.",
        }
        if len(json.dumps(payload).encode()) > 100000:
            raise ValueError(
                "Complete authoring context exceeds limit; choose a narrower explicit mandate"
            )
        return payload
    if tool == "vera_workspace_business_plan_author_read":
        stages = (
            []
            if state is None
            else [
                {
                    "stage_ref": row["stage_ref"],
                    "status": row["status"],
                    "entity_name": row["entity_name"],
                }
                for row in state["stages"]
            ]
        )
        result = {
            "client_id": args["client_id"],
            "engagement_id": args["engagement_id"],
            "grant_ref": args["grant_ref"],
            "scope_revision": revision,
            "question": value["descriptor"]["question"],
            "stages": stages,
            "can_launch": reviewer()
            and engagement["status"] == "open"
            and not uncertain(base, api),
            "recovery_required": uncertain(base, api),
            "professional_approval": False,
        }
        if "stage_ref" in args:
            row = next(
                (
                    row
                    for row in (state or {"stages": []})["stages"]
                    if row["stage_ref"] == args["stage_ref"]
                ),
                None,
            )
            if row is None:
                raise ValueError("Choose one exact retained authored proposal")
            result.update(
                {
                    "selected_stage": row["stage_ref"],
                    "plan": api.read_json(base / row["stage_ref"] / "plan.json"),
                    "report": (base / row["stage_ref"] / "report.html").read_text(
                        encoding="utf-8"
                    ),
                }
            )
            if len(json.dumps(result).encode()) > 2000000:
                raise ValueError("Complete staged report exceeds native limit")
        return result
    if not reviewer() or engagement["status"] != "open":
        raise PermissionError(
            "Planning authoring requires reviewer scope and an open engagement"
        )
    with api.write_lock(home / "outputs"):
        base, value = grant(core, folder, args, root, api)
        state = staged(base, api)
        if tool == "vera_workspace_business_plan_author_stage":
            intent = base / (
                "stage-request-" + fingerprint(args["idempotency_key"]) + ".json"
            )
            request_hash = fingerprint(args)
            if intent.exists():
                previous = api.read_json(intent)
                if (
                    previous["request_sha256"] != request_hash
                    or "result" not in previous
                ):
                    raise ValueError(
                        "Authored stage changed or requires specialist recovery"
                    )
                return previous["result"]
            if uncertain(base, api):
                raise ValueError(
                    "Uncertain planning write requires specialist recovery"
                )
            if args["expected_stage_revision"] != fingerprint(state):
                raise ValueError(
                    "Model proposal changed; read current authoring context"
                )
            case = args["case"]
            compiled = inspect(base, value, case, root, api)
            reference = "case-" + fingerprint(case)
            target = base / reference
            if target.exists():
                raise ValueError(
                    "This proposal already exists; select its retained stage"
                )
            api.atomic_json(intent, {"request_sha256": request_hash})
            target.mkdir(mode=0o700)
            api.atomic_json(target / "case.json", case)
            api.atomic_json(target / "plan.json", compiled["plan"])
            (target / "report.html").write_text(compiled["report"], encoding="utf-8")
            grant(core, folder, args, root, api)
            row = {
                "stage_ref": reference,
                "status": compiled["plan"]["status"],
                "entity_name": case["entity_name"],
                "artifacts": tree_hash(target),
            }
            api.atomic_json(
                base / "stage-state.json",
                {"stages": [*(state or {"stages": []})["stages"], row]},
            )
            result = {
                "saved": True,
                "status": "model_case_staged",
                "stage_ref": reference,
                "case_sha256": compiled["plan"]["case_sha256"],
                "plan_status": compiled["plan"]["status"],
                "professional_approval": False,
                "run_created": False,
            }
            api.atomic_json(intent, {"request_sha256": request_hash, "result": result})
            return result
        if (
            tool != "vera_workspace_business_plan_author_launch"
            or args.get("confirmed") is not True
        ):
            raise ValueError(
                "Choose an explicit app execution of the authored proposal"
            )
        intent = base / (
            "launch-request-" + fingerprint(args["idempotency_key"]) + ".json"
        )
        request_hash = fingerprint(args)
        if intent.exists():
            retained = api.read_json(intent)
            if retained["request_sha256"] != request_hash or "result" not in retained:
                raise ValueError(
                    "Planning execution changed or requires specialist recovery"
                )
            loaded = core.ledger.load_run(
                folder, args["engagement_id"], retained["result"]["run_id"]
            )
            directory_out = (
                Path(loaded["output_dir"]) / retained["result"]["generation"]
            )
            if tree_hash(directory_out) != retained["output_hashes"]:
                raise ValueError("Retained authored run outputs changed")
            return retained["result"]
        if uncertain(base, api):
            raise ValueError("Uncertain planning write requires specialist recovery")
        if args["scope_revision"] != fingerprint([engagement, value, state]):
            raise ValueError("Reopen the current planning proposal")
        row = next(
            (
                row
                for row in (state or {"stages": []})["stages"]
                if row["stage_ref"] == args["stage_ref"]
            ),
            None,
        )
        if row is None:
            raise ValueError("Choose one exact authored stage")
        case_path = base / row["stage_ref"] / "case.json"
        compiled = inspect(base, value, api.read_json(case_path), root, api)
        if compiled["plan"] != api.read_json(
            base / row["stage_ref"] / "plan.json"
        ) or compiled["report"] != (base / row["stage_ref"] / "report.html").read_text(
            encoding="utf-8"
        ):
            raise ValueError("Authored proposal differs from the public replay")
        api.atomic_json(intent, {"request_sha256": request_hash})
        imported = core.ledger.import_document(
            folder,
            args["client_id"],
            args["engagement_id"],
            case_path.resolve(),
            "source",
        )["receipt"]
        prepared = core.prepare_studio_client_workflow(
            args["engagement_id"],
            "business-planning",
            input_ids=[*value["descriptor"]["input_ids"], imported["input_id"]],
            upstream_artifacts=(
                [
                    *(
                        {**item, "role": "source"}
                        for item in value["descriptor"]["upstream_artifacts"]
                    ),
                    {**value["descriptor"]["parent"], "role": "prior_plan"},
                ]
                if value["descriptor"]["parent"]
                else [
                    {**item, "role": "source"}
                    for item in value["descriptor"]["upstream_artifacts"]
                ]
            ),
            label=value["descriptor"]["label"],
            purpose=value["descriptor"]["purpose"],
            idempotency_key="native-planning-"
            + fingerprint([owner(args), args["grant_ref"], args["idempotency_key"]]),
            new_run=True,
        )
        run_id = prepared["run"]["run_id"]
        core.start_studio_client_workflow(
            args["client_id"], args["engagement_id"], run_id
        )
        binding = {
            "client_root": str(folder),
            "client_id": args["client_id"],
            "engagement_id": args["engagement_id"],
            "run_id": run_id,
            "workflow_id": "business-planning",
        }
        loaded = api.load_binding(binding)
        from native_business_planning import context
        from native_business_planning import dispatch as planning_dispatch

        current = context(binding, loaded, root, api)
        reference = work_ref(args["client_id"], args["engagement_id"], run_id)
        produced = planning_dispatch(
            "vera_workspace_business_plan_prepare",
            {
                "work_ref": reference,
                "revision": current["revision"],
                "case_input_id": imported["input_id"],
                "idempotency_key": "authored-cycle",
            },
            binding,
            loaded,
            root,
            api,
        )
        if produced["status"] != compiled["plan"]["status"]:
            raise ValueError(
                "Authored report status changed during execution; recovery required"
            )
        grant(core, folder, args, root, api)
        produced_directory = Path(loaded["output_dir"]) / produced["generation"]
        if (
            api.read_json(produced_directory / "business_plan.json") != compiled["plan"]
            or (produced_directory / "business_plan_review.html").read_text(
                encoding="utf-8"
            )
            != compiled["report"]
        ):
            raise ValueError(
                "Executed proposal differs from staged replay; recovery required"
            )
        result = {
            "saved": True,
            "status": "authored_cycle_retained",
            "client_id": args["client_id"],
            "engagement_id": args["engagement_id"],
            "run_id": run_id,
            "work_ref": reference,
            "generation": produced["generation"],
            "plan_status": produced["status"],
            "professional_approval": False,
            "run_completed": False,
        }
        api.atomic_json(
            intent,
            {
                "request_sha256": request_hash,
                "result": result,
                "output_hashes": tree_hash(produced_directory),
            },
        )
        return result
