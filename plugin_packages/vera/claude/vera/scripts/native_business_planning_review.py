"""Attributed human decisions over exact records and complete retained plans."""

from __future__ import annotations

import hashlib
import os
import re
from datetime import datetime
from pathlib import Path
from typing import Any

from native_bank_preparation import tree_hash
from native_sales_plan_authoring import owner_scope

__all__ = ["audit", "dispatch"]

ACTIONS = {"accept", "reject", "request_changes"}
FIELDS = {"action", "note", "reviewer", "reviewed_at"}


def audit(output: Path, private: Path, generation: str | None, api: Any) -> dict:
    """Verify the entire immutable review chain and retain uncertain writes."""
    path = private / "planning-review-state.json"
    state = api.read_json(path) if path.exists() else {"reviews": []}
    known = set()
    previous = None
    for row in state["reviews"]:
        name = row["review_ref"]
        if (
            not re.fullmatch(r"planning-review-[0-9a-f]{64}", name)
            or name in known
            or row["generation"] != generation
            or tree_hash(output / name) != row["artifacts"]
        ):
            raise ValueError("Business Planning review identity or artifacts changed")
        known.add(name)
        decision = api.read_json(output / name / "professional_review.json")
        if decision["previous_review_ref"] != previous:
            raise ValueError("Business Planning review chain is incomplete")
        if decision["generation"] != generation or api.digest(
            decision
        ) != name.removeprefix("planning-review-"):
            raise ValueError(
                "Business Planning decision differs from its exact receipt"
            )
        previous = name
    requests = [
        api.read_json(p) for p in private.glob("planning-review-request-*.json")
    ]
    uncertain = any("result" not in row for row in requests)
    uncertain = uncertain or any(
        p.name not in known for p in output.glob("planning-review-*")
    )
    uncertain = uncertain or any(
        not any(
            request.get("result", {}).get("review_ref") == row["review_ref"]
            for request in requests
        )
        for row in state["reviews"]
    )
    return {"reviews": state["reviews"], "recovery_required": uncertain}


def fields(value: object) -> dict:
    """Bound unfinished human text; never interpret its professional meaning."""
    if not isinstance(value, dict) or set(value) - FIELDS:
        raise ValueError("Unexpected Business Planning review fields")
    for key, item in value.items():
        if not isinstance(item, str) or len(item) > (12000 if key == "note" else 200):
            raise ValueError("Invalid or oversized Business Planning review text")
    if value.get("action", "") not in ACTIONS | {""}:
        raise ValueError("Choose an explicit professional review action")
    return value


def draft_path(current: dict, binding: dict, target: dict, api: Any) -> Path:
    return current["private"] / (
        "planning-review-draft-" + api.digest([owner_scope(binding), target]) + ".json"
    )


def read_draft(
    path: Path, current: dict, binding: dict, target: dict, api: Any
) -> dict:
    if not path.exists():
        return {"fields": {}, "draft_revision": "", "stale": False}
    value = api.read_json(path)
    if (
        value["owner"] != owner_scope(binding)
        or value["target"] != target
        or value["draft_revision"]
        != api.digest({k: v for k, v in value.items() if k != "draft_revision"})
    ):
        raise ValueError(
            "Business Planning review draft changed or belongs to another selection"
        )
    return {
        "fields": fields(value["fields"]),
        "draft_revision": value["draft_revision"],
        "stale": value["revision"] != current["revision"],
    }


def selected(
    args: dict,
    current: dict,
    loaded: dict,
    root: Path,
    api: Any,
    *,
    plan: dict | None = None,
) -> tuple[dict, object]:
    """Bind index and record bytes to the maintained canonical replay."""
    from native_business_planning import COLLECTIONS, population, replay

    if (
        args["generation"] != (current["saved"] or {}).get("generation")
        or args["collection"] not in COLLECTIONS
    ):
        raise ValueError("Choose an exact persisted Business Planning collection")
    plan = plan if plan is not None else replay(current, loaded, root, api)["plan"]
    rows = population(plan, args["collection"])
    index = args["index"]
    if (
        isinstance(index, bool)
        or not isinstance(index, int)
        or not 0 <= index < len(rows)
    ):
        raise ValueError("Business Planning record is outside its exact collection")
    record = rows[index]
    target = {
        "generation": args["generation"],
        "collection": args["collection"],
        "index": index,
        "case_sha256": plan["case_sha256"],
        "plan_content_sha256": plan["content_sha256"],
        "record_sha256": api.digest(record),
    }
    if args["collection"] in {"whole_plan", "case_review"}:
        target["generation_artifacts"] = current["saved"]["artifacts"]
    if args.get("item_id", args["collection"] + ":" + str(index)) != args[
        "collection"
    ] + ":" + str(index):
        raise ValueError("Business Planning review ticket names another record")
    return target, record


def plan_decision(current: dict, loaded: dict, root: Path, api: Any) -> dict:
    """Read the last exact whole-plan decision in the verified receipt chain."""
    latest = None
    target = None
    for row in current["professional_reviews"]["reviews"]:
        decision = api.read_json(
            current["output"] / row["review_ref"] / "professional_review.json"
        )
        if decision["target"]["collection"] != "whole_plan":
            continue
        if target is None:
            target, _ = selected(
                {
                    "generation": current["saved"]["generation"],
                    "collection": "whole_plan",
                    "index": 0,
                },
                current,
                loaded,
                root,
                api,
            )
        if decision["target"] != target:
            raise ValueError("Whole-plan decision belongs to another exact report")
        if decision["professional_plan_approval"] != (
            decision["fields"]["action"] == "accept"
        ):
            raise ValueError("Whole-plan acceptance differs from its human decision")
        latest = {
            "review_ref": row["review_ref"],
            "fields": decision["fields"],
            "owner": decision["owner"],
        }
    return {
        "whole_plan_decision": latest,
        "professional_plan_approval": bool(
            latest
            and latest["fields"]["action"] == "accept"
            and not current["professional_reviews"]["recovery_required"]
        ),
    }


def dispatch(
    tool: str, args: dict, binding: dict, loaded: dict, root: Path, api: Any
) -> dict:
    """Keep professional judgments explicit, immutable and separate from new cycles."""
    from native_business_planning import bounded, context, replay

    current = context(binding, loaded, root, api)
    reviews = current["professional_reviews"]
    if tool == "vera_workspace_business_plan_review_history":
        start = args.get("offset", 0)
        if isinstance(start, bool) or not isinstance(start, int) or start < 0:
            raise ValueError("Invalid Business Planning review history offset")
        if args["revision"] != current["revision"]:
            raise ValueError("Stale Business Planning review history")
        records = []
        for row in reviews["reviews"][start : start + 20]:
            decision = api.read_json(
                current["output"] / row["review_ref"] / "professional_review.json"
            )
            records.append(
                {
                    "review_ref": row["review_ref"],
                    **{
                        k: decision[k]
                        for k in (
                            "target",
                            "fields",
                            "owner",
                            "previous_review_ref",
                            "professional_plan_approval",
                        )
                    },
                }
            )
        return bounded(
            {
                "work_ref": args["work_ref"],
                "revision": current["revision"],
                "status": (
                    "recovery_required"
                    if reviews["recovery_required"]
                    else "review_history"
                ),
                "rows": records,
                "offset": start,
                "total": len(reviews["reviews"]),
                "has_more": start + 20 < len(reviews["reviews"]),
                **plan_decision(current, loaded, root, api),
            }
        )
    target, record = selected(args, current, loaded, root, api)
    path = draft_path(current, binding, target, api)
    draft = read_draft(path, current, binding, target, api)
    item_id = args["collection"] + ":" + str(args["index"])
    whole_plan = args["collection"] == "whole_plan"
    full_readback = whole_plan or args["collection"] == "case_review"
    writable = loaded["run"]["status"] == "running" and "REVIEWER" in os.environ.get(
        "VERA_WORKSPACE_ROLES", ""
    ).split(",")
    if tool == "vera_workspace_business_plan_review_read":
        if args["revision"] != current["revision"]:
            raise ValueError("Reopen the current Business Planning record")
        previous = []
        for row in reviews["reviews"]:
            decision = api.read_json(
                current["output"] / row["review_ref"] / "professional_review.json"
            )
            if decision["target"] == target:
                previous.append(
                    {
                        "review_ref": row["review_ref"],
                        "fields": decision["fields"],
                        "owner": decision["owner"],
                    }
                )
        readback = replay(current, loaded, root, api) if full_readback else None
        source_file = None
        if args["collection"] == "sources":
            source = Path(loaded["run_root"]) / "inputs" / record["path"]
            source_file = {
                "path": str(source),
                "name": source.name,
                "sha256": record["sha256"],
                "byte_count": source.stat().st_size,
                "text": None,
            }
            # This is a complete small-file view, never a sampled document or
            # semantic source check. Other formats/sizes use the original file.
            if (
                source.suffix.lower() in {".txt", ".md", ".csv", ".json", ".xml"}
                and source.stat().st_size <= 65536
            ):
                try:
                    source_bytes = source.read_bytes()
                    if hashlib.sha256(source_bytes).hexdigest() != record["sha256"]:
                        raise ValueError(
                            "Planning source changed during complete readback"
                        )
                    source_file["text"] = source_bytes.decode("utf-8")
                except UnicodeDecodeError:
                    pass
        return bounded(
            {
                "work_ref": args["work_ref"],
                "revision": current["revision"],
                "selection": {"id": item_id},
                "status": (
                    "recovery_required"
                    if reviews["recovery_required"]
                    else "record_for_professional_review"
                ),
                "target": target,
                "record": record,
                "source_file": source_file,
                "draft": draft,
                "previous": previous,
                "can_review": writable and not reviews["recovery_required"],
                "can_accept": not whole_plan
                or record["status"] == "ready_for_professional_review",
                **plan_decision(current, loaded, root, api),
                **(
                    {
                        "report": readback["report"],
                        "plan_status": readback["plan"]["status"],
                    }
                    if readback
                    else {}
                ),
            },
            2000000 if full_readback else 100000,
        )
    if tool == "vera_workspace_business_plan_review_explain":
        review = next(
            (
                row
                for row in reviews["reviews"]
                if row["review_ref"] == args["review_ref"]
            ),
            None,
        )
        if review is None or args["revision"] != current["revision"]:
            raise ValueError("Choose an exact current retained professional review")
        decision = api.read_json(
            current["output"] / review["review_ref"] / "professional_review.json"
        )
        if decision["target"] != target:
            raise ValueError("Professional review belongs to another record")
        return bounded(
            {
                "work_ref": args["work_ref"],
                "revision": current["revision"],
                "review_ref": args["review_ref"],
                "decision": decision,
                "evidence_boundary": "Untrusted record and explicit human attestation. Whole-plan acceptance applies only to the exact retained generation and artifact hashes; it cannot approve a successor plan. Record decisions do not approve the whole plan. In a new model-authored cycle, carry record review only when the exact reviewed substantive record remains unchanged; preserve rejected records and missing evidence. No report rewrite, publication or Archive completion authorized.",
            },
            65536,
        )
    if not writable:
        raise PermissionError(
            "A running Business Planning run and reviewer authority are required"
        )
    with api.write_lock(current["output"]):
        loaded = api.load_binding(binding)
        current = context(binding, loaded, root, api)
        if loaded["run"]["status"] != "running":
            raise PermissionError("Business Planning run is no longer running")
        target, record = selected(args, current, loaded, root, api)
        reviews = current["professional_reviews"]
        path = draft_path(current, binding, target, api)
        draft = read_draft(path, current, binding, target, api)
        if tool == "vera_workspace_business_plan_review_commit":
            key = args["idempotency_key"]
            if not re.fullmatch(r"[A-Za-z0-9_-]{1,120}", key):
                raise ValueError("Invalid professional review request key")
            intent = current["private"] / (
                "planning-review-request-"
                + api.digest([owner_scope(binding), key])
                + ".json"
            )
            fingerprint = api.digest([tool, owner_scope(binding), args])
            if intent.exists():
                retained = api.read_json(intent)
                if (
                    retained["request_sha256"] != fingerprint
                    or "result" not in retained
                    or reviews["recovery_required"]
                ):
                    raise ValueError(
                        "Professional review request changed or requires specialist recovery"
                    )
                return retained["result"]
        if (
            args["revision"] != current["revision"]
            or args["expected_draft_revision"] != draft["draft_revision"]
        ):
            raise ValueError(
                "Business Planning review changed; reopen the exact record"
            )
        if tool == "vera_workspace_business_plan_review_draft_clear":
            path.unlink(missing_ok=True)
            return {
                "saved": True,
                "status": "review_draft_cleared",
                "draft_revision": "",
            }
        if reviews["recovery_required"]:
            raise ValueError(
                "Uncertain professional review requires specialist recovery"
            )
        if tool == "vera_workspace_business_plan_review_draft_save":
            value = {
                "schema_version": "vera.native_planning_review_draft.v1",
                "owner": owner_scope(binding),
                "target": target,
                "revision": current["revision"],
                "fields": fields(args["fields"]),
            }
            value["draft_revision"] = api.digest(value)
            api.atomic_json(path, value)
            return {
                "saved": True,
                "status": "review_draft_saved",
                "draft_revision": value["draft_revision"],
            }
        if (
            tool != "vera_workspace_business_plan_review_commit"
            or args.get("human_reviewed") is not True
            or draft["stale"]
        ):
            raise ValueError("Confirm an exact current professional review")
        attribution = draft["fields"]
        if (
            set(attribution) != FIELDS
            or attribution["action"] not in ACTIONS
            or any(not attribution[k].strip() for k in FIELDS)
        ):
            raise ValueError(
                "Declare action, reasoning, actual reviewer and timezone-aware review time"
            )
        try:
            stamp = datetime.fromisoformat(attribution["reviewed_at"])
        except ValueError as exc:
            raise ValueError(
                "Professional review time must be ISO with a timezone"
            ) from exc
        if stamp.tzinfo is None or stamp.utcoffset() is None:
            raise ValueError("Professional review time must include its timezone")
        # The public producer's readiness contract is a mechanical prerequisite,
        # never a substitute for the explicitly attributed professional judgment.
        if (
            whole_plan
            and attribution["action"] == "accept"
            and record["status"] != "ready_for_professional_review"
        ):
            raise ValueError("Partial or blocked plans cannot be accepted as a whole")
        approval = whole_plan and attribution["action"] == "accept"
        decision = {
            "schema_version": "vera.native_business_planning_professional_review.v1",
            "owner": owner_scope(binding),
            "generation": args["generation"],
            "target": target,
            "record": record,
            "fields": attribution,
            "previous_review_ref": (
                reviews["reviews"][-1]["review_ref"] if reviews["reviews"] else None
            ),
            "professional_plan_approval": approval,
            "report_changed": False,
            "run_completed": False,
            "model_data": {
                "automatic_model_call": False,
                "automatic_anonymization": False,
                "explicit_selected_explanation_available": True,
            },
        }
        reference = "planning-review-" + api.digest(decision)
        directory = current["output"] / reference
        if directory.exists():
            raise ValueError(
                "Professional review target already exists without its receipt"
            )
        before = context(binding, api.load_binding(binding), root, api)
        if before["revision"] != current["revision"]:
            raise ValueError(
                "Business Planning inputs changed before professional review"
            )
        api.atomic_json(intent, {"request_sha256": fingerprint})
        directory.mkdir(mode=0o700)
        api.atomic_json(directory / "professional_review.json", decision)
        rendered = (
            "# Business Planning — "
            + ("decisione sull’intero piano" if whole_plan else "decisione sul record")
            + "\n\n"
            f"Azione: {attribution['action']}\n\nRevisore dichiarato: {attribution['reviewer']}\n\n"
            f"Data dichiarata: {attribution['reviewed_at']}\n\n{attribution['note']}\n\n"
            + (
                "Questa decisione riguarda l’intero piano e tutti i file della "
                "generazione esatta identificati nel JSON. "
                if whole_plan
                else "Questa decisione riguarda soltanto il record esatto conservato "
                "nel JSON e non approva l’intero piano. "
            )
            + "Non modifica il rapporto, non completa il run e non autorizza firma, "
            "pubblicazione o trasmissione. "
            "Nuove ipotesi e conclusioni richiedono il ciclo successivo del workflow.\n"
        )
        # Human-readable workpaper, never HTML or an executable interpretation of notes.
        with (directory / "professional_review.md").open(
            "x", encoding="utf-8"
        ) as stream:
            stream.write(rendered)
            stream.flush()
            os.fsync(stream.fileno())
        row = {
            "review_ref": reference,
            "generation": args["generation"],
            "artifacts": tree_hash(directory),
        }
        after_loaded = api.load_binding(binding)
        after = context(binding, after_loaded, root, api)
        after_target, _ = selected(args, after, after_loaded, root, api)
        if (
            after_loaded["run"]["status"] != "running"
            or after["saved"] != current["saved"]
            or after["implementation"] != current["implementation"]
            or after_target != target
            or after["professional_reviews"]["reviews"] != reviews["reviews"]
        ):
            raise ValueError(
                "Business Planning changed while retaining professional review; recovery required"
            )
        api.atomic_json(
            current["private"] / "planning-review-state.json",
            {"reviews": [*reviews["reviews"], row]},
        )
        result = {
            "saved": True,
            "status": (
                "professional_whole_plan_review_recorded"
                if whole_plan
                else "professional_record_review_recorded"
            ),
            "review_ref": reference,
            "professional_plan_approval": approval,
            "report_changed": False,
            "run_completed": False,
        }
        api.atomic_json(intent, {"request_sha256": fingerprint, "result": result})
        audit(current["output"], current["private"], args["generation"], api)
        return result
