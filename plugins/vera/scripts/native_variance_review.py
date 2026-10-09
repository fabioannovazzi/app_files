"""Literal professional decisions over exact public variance evidence.

Receipt hashes, CAS and public readiness are mechanical audit contracts. The
adapter never interprets causes or supplies a professional decision itself.
"""

from __future__ import annotations

import json
import os
import re
from datetime import datetime
from pathlib import Path
from typing import Any

from native_archive_navigation import archive_module, engagement_scope, work_ref
from native_bank_preparation import file_hash, tree_hash
from native_variance import bounded, context, directory, selected, selection

__all__ = ["audit_review", "dispatch"]
SECTIONS = {"professional_review", "root_cause_review"}
FIELDS = {"decision", "reviewer", "reviewed_at", "basis"}


def audit_review(output: Path, api: Any) -> dict:
    """Incomplete conservation cannot be adopted, repeated or closed."""
    private = api.ui_state_directory(output, create=False)
    records = [api.read_json(p) for p in private.glob("variance-review-request-*.json")]
    known = set()
    for row in records:
        if "result" not in row:
            continue
        ref = row["case_ref"]
        if not re.fullmatch(r"variance-reviewed-[a-f0-9]{64}", ref) or ref in known:
            raise ValueError("Invalid variance review conservation identity")
        known.add(ref)
        if tree_hash(private / ref) != row["artifacts"]:
            raise ValueError("Conserved variance review artifacts changed")
        target = row["binding"]
        if (
            any(
                target[k] != row["owner"][k]
                for k in ("client_id", "engagement_id", "workflow_id")
            )
            or target["run_id"] == row["owner"]["run_id"]
        ):
            raise PermissionError(
                "Variance review selected another engagement or predecessor"
            )
        hydrated = api.load_binding(target)
        for identity, name in (
            (row["result"]["recipe_input_id"], "comparison.json"),
            (row["result"]["review_input_id"], "professional-decision.json"),
        ):
            if file_hash(selected(identity, hydrated)[0]) != file_hash(
                private / ref / name
            ):
                raise ValueError("Registered variance review receipt changed")
        if (
            file_hash(selected(row["result"]["source_input_id"], hydrated)[0])
            != row["source_sha256"]
        ):
            raise ValueError("Reviewed variance original changed")
    return {
        "requests": records,
        "recovery_required": any("result" not in r for r in records)
        or any(p.name not in known for p in private.glob("variance-reviewed-*")),
    }


def fields(value: Any, *, final: bool) -> dict:
    """Names are literal declarations, never authenticated professional identity."""
    if (
        not isinstance(value, dict)
        or set(value) != FIELDS
        or any(not isinstance(v, str) or len(v) > 4000 for v in value.values())
    ):
        raise ValueError("Use complete literal variance decision, name, time and basis")
    if value["decision"] not in {"", "accepted", "rejected", "changes_requested"}:
        raise ValueError("Choose an explicit variance decision")
    if final:
        if any(not v.strip() for v in value.values()):
            raise ValueError(
                "Supply actual variance decision, reviewer, review time and basis"
            )
        stamp = datetime.fromisoformat(value["reviewed_at"])
        if stamp.tzinfo is None or stamp.utcoffset() is None:
            raise ValueError("Actual variance review time requires its timezone")
    return dict(value)


def snapshot(binding: dict, loaded: dict, root: Path, api: Any, args: dict) -> dict:
    current = context(binding, loaded, root, api)
    folder = directory(current, args)
    implementation = {
        p.name: file_hash(p)
        for p in (
            Path(__file__),
            Path(__file__).with_name("native_variance_review_bridge.py"),
        )
    }
    current["scope"] = {
        **current["scope"],
        "professional_review_implementation": implementation,
    }
    current["revision"] = api.digest([current["scope"], current["saved"]])
    recipe = api.read_json(folder / "used_recipe.json")
    public = api.read_json(folder / "final_artifacts.json")["accounting_readiness"]
    path = folder / "root_cause_sweep_model_context.json"
    alternatives = api.read_json(path)["alternatives"] if path.is_file() else []
    if not isinstance(alternatives, list) or any(
        not isinstance(r, dict)
        or isinstance(r["alternative_result"], bool)
        or not isinstance(r["alternative_result"], int)
        for r in alternatives
    ):
        raise ValueError("Invalid public variance alternative population")
    if len({r["alternative_result"] for r in alternatives}) != len(alternatives):
        raise ValueError("Duplicate public variance alternatives")
    current.update(
        recipe=recipe, readiness=public, alternatives=alternatives, folder=folder
    )
    return current


def record(current: dict, args: dict) -> tuple[str, dict]:
    section = args["section"]
    alternative = args.get("alternative", 0)
    if (
        section not in SECTIONS
        or isinstance(alternative, bool)
        or not isinstance(alternative, int)
    ):
        raise ValueError("Choose an exact professional variance record")
    evidence = {
        "accounting_readiness": current["readiness"],
        "declared_controls": current["recipe"]["accounting_review"],
    }
    if section == "professional_review":
        if alternative != 0:
            raise ValueError(
                "Accounting review does not select a root-cause alternative"
            )
        evidence["comparison"] = current["recipe"]["mappings"]
        evidence["totals"] = current["readiness"]["source_tie_out"]
    else:
        chosen = next(
            (
                r
                for r in current["alternatives"]
                if r["alternative_result"] == alternative
            ),
            None,
        )
        if chosen is None:
            raise ValueError(
                "Select an actual retained public alternative; no default selection"
            )
        evidence["alternative"] = chosen
        evidence["interpretation_boundary"] = (
            "Each selected contribution is residual after earlier rows; the sequence does not demonstrate economic causes."
        )
    return section + ":" + str(alternative), evidence


def draft(current: dict, identity: str, api: Any) -> tuple[Path, dict, str]:
    scope = [current["scope"], current["saved"]["generation"], identity]
    path = current["private"] / (
        "variance-professional-draft-" + api.digest(scope) + ".json"
    )
    saved = (
        api.read_json(path)
        if path.exists()
        else {"scope": scope, "generation": 0, "fields": dict.fromkeys(FIELDS, "")}
    )
    if saved["scope"] != scope:
        raise PermissionError(
            "Variance professional draft belongs to another exact record"
        )
    fields(saved["fields"], final=False)
    return path, saved, api.digest(saved)


def conserve(
    binding: dict,
    loaded: dict,
    current: dict,
    recipe: dict,
    review: dict,
    identity: str,
    key: str,
    api: Any,
) -> dict:
    core = archive_module(api.archive_root)
    folder, _ = engagement_scope(core, binding["client_id"], binding["engagement_id"])
    if folder.resolve() != Path(binding["client_root"]).resolve():
        raise PermissionError("Variance review belongs to another client")
    ref = "variance-reviewed-" + api.digest([current["scope"], identity, key])
    target = current["private"] / ref
    target.mkdir(exist_ok=False)
    api.atomic_json(target / "comparison.json", recipe)
    api.atomic_json(
        target / "professional-decision.json",
        {
            "schema_version": "vera.native.variance_professional_decision.v1",
            "scope": current["scope"],
            "source_ref": current["saved"]["generation"],
            "item_id": identity,
            "fields": review,
            "recipe_sha256": file_hash(target / "comparison.json"),
            "report_calculated": False,
            "reviewer_authenticated": False,
        },
    )
    imported = [
        core.ledger.import_document(
            folder,
            binding["client_id"],
            binding["engagement_id"],
            (target / name).resolve(),
            "source",
        )["receipt"]["input_id"]
        for name in ("comparison.json", "professional-decision.json")
    ]
    inputs = loaded["input_manifest"]["inputs"]
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
        label="Scostamenti: decisione su " + identity,
        purpose="Conservare la decisione attribuita e calcolare separatamente il confronto riscontrato.",
        idempotency_key="native-variance-review-"
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
    for input_id, name in zip(
        imported, ("comparison.json", "professional-decision.json")
    ):
        if file_hash(selected(input_id, hydrated)[0]) != file_hash(target / name):
            raise ValueError("Variance successor differs from the named decision")
    return {
        "binding": successor,
        "case_ref": ref,
        "artifacts": tree_hash(target),
        "result": {
            "saved": True,
            "status": "variance_professional_decision_registered",
            "work_ref": successor["work_ref"],
            "run_id": run_id,
            "recipe_input_id": imported[0],
            "review_input_id": imported[1],
            "source_input_id": current["saved"]["fields"]["source_input_id"],
            "calculation_choices": {
                **current["saved"]["fields"],
                "recipe_input_id": imported[0],
            },
            "decision": review["decision"],
            "comparison_calculated": False,
            "professional_approval": False,
            "reviewer_authenticated": False,
            "run_completed": False,
        },
    }


def dispatch(
    tool: str, args: dict, binding: dict, loaded: dict, root: Path, api: Any
) -> dict:
    action = tool.removeprefix("vera_workspace_variance_review_")
    current = snapshot(binding, loaded, root, api, args)
    writable = loaded["run"]["status"] == "running" and "REVIEWER" in os.environ.get(
        "VERA_WORKSPACE_ROLES", ""
    ).split(",")
    if action == "setup":
        return bounded(
            {
                "work_ref": args["work_ref"],
                "source_ref": args["source_ref"],
                "revision": current["revision"],
                "readiness": current["readiness"],
                "alternatives": [
                    {
                        "alternative": r["alternative_result"],
                        "row_count": r["row_count"],
                        "other_residual": r["other_residual"],
                    }
                    for r in current["alternatives"]
                ],
                "can_write": writable,
                "acceptance_available": current["readiness"]["accounting_status"]
                == "ready_for_professional_review",
            }
        )
    identity, evidence = record(current, args)
    path, saved, stamp = draft(current, identity, api)
    if action == "read":
        return bounded(
            {
                "work_ref": args["work_ref"],
                "source_ref": args["source_ref"],
                "revision": current["revision"],
                "section": args["section"],
                "alternative": args.get("alternative", 0),
                "selection": {"id": identity},
                "data": {"selection": {"source_ref": args["source_ref"]}},
                "record": evidence,
                "declared_review": current["recipe"]["accounting_review"][
                    args["section"]
                ],
                "draft": saved["fields"],
                "draft_revision": stamp,
                "can_write": writable,
                "acceptance_available": current["readiness"]["accounting_status"]
                == "ready_for_professional_review",
                "reviewer_authenticated": False,
                "run_completed": False,
            }
        )
    if action == "explain":
        if args["revision"] != current["revision"]:
            raise ValueError("Stale professional variance discussion")
        return bounded(
            {
                "work_ref": args["work_ref"],
                "source_ref": args["source_ref"],
                "revision": current["revision"],
                "item_id": identity,
                "record": evidence,
                "evidence_status": "untrusted_public_variance_evidence",
                "professional_approval": False,
                "run_completed": False,
            }
        )
    if action not in {"draft_save", "commit"} or not writable:
        raise PermissionError("Variance decisions require an owned running reviewer")
    if args["item_id"] != identity:
        raise ValueError("Review only the exact selected variance record")
    with api.write_lock(current["output"]):
        loaded = api.load_binding(binding)
        current = snapshot(binding, loaded, root, api, args)
        identity, evidence = record(current, args)
        key = args.get("idempotency_key")
        intent = None
        fingerprint = api.digest([current["scope"], tool, args])
        if action == "commit":
            if not isinstance(key, str) or not re.fullmatch(
                r"[A-Za-z0-9_-]{1,120}", key
            ):
                raise ValueError("Invalid variance decision request key")
            intent = current["private"] / (
                "variance-review-request-"
                + api.digest([current["scope"]["owner"], key])
                + ".json"
            )
            if intent.exists():
                previous = api.read_json(intent)
                if (
                    previous["request_sha256"] != fingerprint
                    or "result" not in previous
                ):
                    raise ValueError(
                        "Changed decision retry or uncertain variance conservation requires recovery"
                    )
                return previous["result"]
        if args["revision"] != current["revision"]:
            raise ValueError("Reopen the exact current variance decision")
        path, saved, stamp = draft(current, identity, api)
        if args["expected_draft_revision"] != stamp:
            raise ValueError("Variance professional draft changed concurrently")
        if action == "draft_save":
            updated = {
                **saved,
                "generation": saved["generation"] + 1,
                "fields": fields(args["fields"], final=False),
            }
            api.atomic_json(path, updated)
            return {
                "saved": True,
                "draft_revision": api.digest(updated),
                "professional_approval": False,
            }
        if args.get("confirmed") is not True:
            raise PermissionError(
                "Renew confirmation of this exact saved professional decision"
            )
        review = fields(saved["fields"], final=True)
        source, original_recipe, original = selection(
            current["saved"]["fields"], loaded, api
        )
        checked = review_recipe(root, current, original, args, review, api)
        api.atomic_json(intent, {"request_sha256": fingerprint})
        conserved = conserve(
            binding, loaded, current, checked, review, identity, key, api
        )
        after = context(binding, api.load_binding(binding), root, api)
        after["scope"]["professional_review_implementation"] = {
            p.name: file_hash(p)
            for p in (
                Path(__file__),
                Path(__file__).with_name("native_variance_review_bridge.py"),
            )
        }
        if current["scope"] != after["scope"]:
            raise ValueError(
                "Variance predecessor changed during decision conservation"
            )
        api.atomic_json(
            intent,
            {
                "request_sha256": fingerprint,
                "owner": binding,
                "source_sha256": file_hash(source),
                **conserved,
            },
        )
        return conserved["result"]


def review_recipe(
    root: Path, current: dict, original: dict, args: dict, review: dict, api: Any
) -> dict:
    """The unchanged public readiness decides eligibility, never this adapter's opinion."""
    import subprocess
    import sys

    result = subprocess.run(
        [
            sys.executable,
            "-I",
            "-B",
            str(Path(__file__).with_name("native_variance_review_bridge.py")),
            str(root),
        ],
        input=json.dumps(
            {
                "recipe": original,
                "used_recipe": current["recipe"],
                "readiness": current["readiness"],
                "section": args["section"],
                "alternative": args.get("alternative", 0),
                "available_alternatives": [
                    r["alternative_result"] for r in current["alternatives"]
                ],
                "review": review,
            }
        ),
        text=True,
        capture_output=True,
        timeout=45,
        check=False,
    )
    if result.returncode:
        raise ValueError(
            result.stderr.strip().splitlines()[-1] or "Public variance review refused"
        )
    return json.loads(result.stdout)["recipe"]
