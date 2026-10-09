"""Owned registry reviewer choices over unchanged public save and apply producers."""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

from native_bank_preparation import file_hash, tree_hash
from native_sari_authoring import audit_run as audit_authoring
from native_sari_authoring import stamp
from native_sari_intake import audit_run as audit_intake
from native_sari_intake import bounded

__all__ = ["dispatch", "audit_run"]

MUTABLE = {
    "ui_decisions.json",
    "applied_decisions.json",
    "final_artifacts.json",
    "run_intake.json",
}


def engine(root: Path, request: dict, api: Any) -> dict:
    """Only fixed maintained public contracts, using the already available runtime."""
    result = subprocess.run(
        [
            sys.executable,
            "-I",
            "-B",
            str(Path(__file__).with_name("native_sari_review_bridge.py")),
            str(root),
        ],
        input=json.dumps(
            {**request, "node": api.workbench_module()._node_executable()}
        ),
        text=True,
        capture_output=True,
        check=False,
        timeout=90,
    )
    if result.returncode:
        raise ValueError(
            result.stderr.strip().splitlines()[-1] or "Registry review refused"
        )
    return json.loads(result.stdout)


def audit_run(output: Path, api: Any) -> dict:
    """Uncertain mutations and missing retained prior versions prevent closure and retries."""
    directory = api.ui_state_directory(output, create=False)
    path = directory / "sari-review-operations.json"
    state = api.read_json(path) if path.exists() else {"operations": []}
    known = set()
    references = set()
    recovery = False
    for row in state["operations"]:
        if row["key"] in known or row["fingerprint"] != stamp(row["request"]):
            raise ValueError("Registry review operation identity changed")
        known.add(row["key"])
        if row["status"] not in {"pending", "complete"}:
            raise ValueError("Invalid registry review operation status")
        reference = row["snapshot_ref"]
        if (
            reference != "review-" + stamp([row["request"], row["key"]])
            or reference in references
        ):
            raise ValueError("Invalid registry prior-version identity")
        references.add(reference)
        recovery |= row["status"] == "pending"
        if row["status"] == "complete":
            if (
                row["receipt"]["result"]["work_ref"]
                != row["request"]["binding"]["work_ref"]
                or row["receipt"]["result"]["public_operation"]
                != row["request"]["action"]
            ):
                raise ValueError("Registry review receipt belongs to another operation")
            if (
                row["receipt_sha256"] != stamp(row["receipt"])
                or tree_hash(directory / "sari-review-receipts" / reference)
                != row["receipt"]["preserved_before"]
            ):
                raise ValueError("Registry review receipt or prior version changed")
    home = directory / "sari-review-receipts"
    recovery |= any(p.name not in references for p in home.glob("*"))
    return {"state": state, "recovery_required": recovery}


def snapshot(binding: dict, loaded: dict, root: Path, api: Any) -> dict:
    output = Path(loaded["output_dir"])
    before = tree_hash(output)
    public = (
        engine(root, {"operation": "read", "context": str(loaded["context_path"])}, api)
        if "review_payload.json" in before
        else None
    )
    if tree_hash(output) != before:
        raise ValueError("Registry outputs changed while opening review")
    audit = audit_run(output, api)
    intake = audit_intake(output, api)
    author = audit_authoring(output, api)
    recovery = (
        audit["recovery_required"]
        or intake["recovery_required"]
        or author["recovery_required"]
    )
    scope = {
        "owner": [
            os.environ["VERA_WORKSPACE_TENANT_ID"],
            os.environ["VERA_WORKSPACE_ACTOR_ID"],
        ],
        "binding": binding,
        "run": loaded["run"],
        "inputs": loaded["input_manifest"],
        "outputs": before,
        "implementation": {
            "public": engine(root, {"operation": "implementation"}, api),
            "native": {
                p.name: file_hash(p)
                for p in (
                    Path(__file__),
                    Path(__file__).with_name("native_sari_review_bridge.py"),
                    Path(__file__).with_name("native_sari_review_rpc.cjs"),
                    Path(__file__).parents[1] / "mcp/workspace.cjs",
                )
            },
        },
    }
    path = api.ui_state_directory(output, create=False) / (
        "sari-review-draft-" + stamp(scope["owner"]) + ".json"
    )
    draft = (
        api.read_json(path)
        if path.exists()
        else {
            "scope": scope,
            "generation": 0,
            "fields": {"reviewer": "", "decisions": {}},
        }
    )
    can_write = (
        bool(public)
        and loaded["run"]["status"] == "running"
        and "REVIEWER" in os.environ.get("VERA_WORKSPACE_ROLES", "").split(",")
        and not recovery
        and not author["unfinished"]
    )
    return {
        "output": output,
        "scope": scope,
        "revision": stamp(scope),
        "files": before,
        "public": public,
        "state": audit["state"],
        "recovery_required": recovery,
        "authoring_unfinished": author["unfinished"],
        "can_write": can_write,
        "draft_path": path,
        "draft": draft,
        "draft_revision": stamp(draft),
        "draft_stale": draft["scope"] != scope,
    }


def fields(value: Any, items: list[dict]) -> dict:
    """Only literal allowed item/action shape; professional judgment stays with the reviewer."""
    if (
        not isinstance(value, dict)
        or set(value) != {"reviewer", "decisions"}
        or not isinstance(value["reviewer"], str)
        or len(value["reviewer"]) > 160
    ):
        raise ValueError("Invalid registry reviewer draft")
    decisions = value["decisions"]
    index = {row["id"]: row for row in items}
    if not isinstance(decisions, dict) or len(decisions) > 500:
        raise ValueError("Invalid registry decision population")
    for identity, record in decisions.items():
        if (
            identity not in index
            or not isinstance(record, dict)
            or set(record)
            != {"action", "reviewer_note", "edit_value", "requested_documents"}
        ):
            raise ValueError("Registry choice leaves the exact review population")
        if any(
            not isinstance(v, str) or len(v) > 10000 for v in record.values()
        ) or record["action"] not in ["", *index[identity]["allowed_actions"]]:
            raise ValueError("Invalid literal registry choice")
    return bounded(value, 1_000_000)


def choices(value: dict) -> dict:
    """Translate explicitly selected literal fields, without defaults or semantic classification."""
    return {
        "reviewer": value["reviewer"],
        "decision_source": "vera_native_human_review",
        "decisions": [
            {
                "item_id": identity,
                "action": row["action"],
                "reviewer_note": row["reviewer_note"],
                "edit_value": row["edit_value"],
                "requested_documents": [
                    line
                    for line in row["requested_documents"].splitlines()
                    if line.strip()
                ],
            }
            for identity, row in value["decisions"].items()
            if row["action"]
        ],
    }


def dispatch(
    tool: str, args: dict, binding: dict, loaded: dict, root: Path, api: Any
) -> dict:
    """Private draft, public saved selection and applied review remain separate exact versions."""
    if root.name != "registro-imprese-sari" or binding["workflow_id"] != root.name:
        raise PermissionError("Registry review belongs to another workflow")
    action = tool.removeprefix("vera_workspace_sari_review_")
    current = snapshot(binding, loaded, root, api)
    public = current["public"]["payload"] if current["public"] else None
    items = public["review_payload"]["items"] if public else []
    base = {
        "work_ref": binding["work_ref"],
        "revision": current["revision"],
        "run_status": loaded["run"]["status"],
        "source_ref": current["public"]["review_sha256"] if public else "",
        "can_write": current["can_write"],
        "recovery_required": current["recovery_required"],
        "authoring_unfinished": current["authoring_unfinished"],
        "draft_revision": current["draft_revision"],
        "draft_stale": current["draft_stale"],
        "fields": current["draft"]["fields"],
        "actual_model_reads_verified": False,
        "review_status": public["review_payload"]["status"] if public else None,
        "public_decisions": public["ui_decisions"] if public else None,
        "public_decisions_sha256": current["files"].get("ui_decisions.json"),
        "final_artifacts": public["final_artifacts"] if public else None,
        "data": {
            "selection": {
                "source_ref": current["public"]["review_sha256"] if public else None
            }
        },
    }
    if action == "setup":
        offset = args.get("offset", 0)
        if type(offset) is not int or offset < 0:
            raise ValueError("Invalid registry review page")
        return bounded(
            {
                **base,
                "setup_status": (
                    "review_available" if public else "preparation_required"
                ),
                "total": len(items),
                "offset": offset,
                "has_more": offset + 30 < len(items),
                "rows": [
                    {
                        "item_id": row["id"],
                        "title": row["title"],
                        "item_type": row["item_type"],
                    }
                    for row in items[offset : offset + 30]
                ],
            }
        )
    if action in {"read", "context", "outputs"}:
        if args["revision"] != current["revision"]:
            raise ValueError("Registry review changed; reopen the current version")
        if action == "outputs":
            names = {
                "case_intake_draft.json",
                "practice_plan_draft.json",
                "case_intake_validated.json",
                "practice_plan_validated.json",
                "official_sources.json",
                "practice_validation_audit.json",
                "dire_practice_plan.json",
                "studio_checklist.md",
                "sari_question_draft.md",
                "review_handoff.md",
                "review_payload.json",
                "ui_decisions.json",
                "applied_decisions.json",
                "final_artifacts.json",
                "run_intake.json",
            }
            rows = []
            for name in sorted(names & current["files"].keys()):
                file = current["output"] / name
                if file.stat().st_size > 1_500_000:
                    raise ValueError(
                        "Complete registry output exceeds native limit; use the ordinary file"
                    )
                rows.append(
                    {
                        "name": name,
                        "sha256": current["files"][name],
                        "content": file.read_text(),
                        "byte_count": file.stat().st_size,
                    }
                )
            return bounded({**base, "files": rows})
        selected = next((row for row in items if row["id"] == args["item_id"]), None)
        if selected is None or args["source_ref"] != base["source_ref"]:
            raise PermissionError(
                "Choose an exact registry review item in this owned run"
            )
        if action == "context":
            return bounded(
                {
                    "work_ref": binding["work_ref"],
                    "revision": current["revision"],
                    "source_ref": base["source_ref"],
                    "item_id": selected["id"],
                    "evidence": selected,
                    "review_status": base["review_status"],
                    "actual_model_reads_verified": False,
                    "untrusted_evidence": True,
                    "professional_approval": False,
                },
                64000,
            )
        return bounded({**base, "item": selected, "item_id": selected["id"]})
    if action not in {"draft_save", "draft_clear", "save", "apply"}:
        raise ValueError("Unsupported registry review action")
    if not current["can_write"]:
        raise PermissionError(
            "Registry review needs a running reviewer, closed authoring and no uncertain writes"
        )
    # Exact completed retries precede changing output/draft CAS, never pending retries.
    request = {
        "owner": current["scope"]["owner"],
        "binding": binding,
        "action": action,
        "args": args,
    }
    key = args.get("idempotency_key")
    if action in {"save", "apply"}:
        if not isinstance(key, str) or not re.fullmatch(r"[A-Za-z0-9_.-]{1,200}", key):
            raise ValueError("Invalid registry review operation key")
        previous = next(
            (row for row in current["state"]["operations"] if row["key"] == key), None
        )
        if previous:
            if previous["request"] != request or previous["status"] != "complete":
                raise ValueError(
                    "Registry review retry changed or has an uncertain outcome"
                )
            return previous["receipt"]["result"]
    if (
        args["revision"] != current["revision"]
        or args["source_ref"] != base["source_ref"]
    ):
        raise ValueError("Registry sources changed; reopen the exact review")
    if (
        action != "apply"
        and args["expected_draft_revision"] != current["draft_revision"]
    ):
        raise ValueError("Registry private choices changed; reopen")
    if action in {"draft_clear", "save", "apply"} and args.get("confirmed") is not True:
        raise PermissionError("Renew the separate explicit registry confirmation")
    selected = None
    if action in {"draft_save", "save"}:
        if current["draft_stale"]:
            raise ValueError("Inspect and explicitly discard the stale registry draft")
        selected = fields(args["fields"], items)
    if action == "save":
        if selected != current["draft"]["fields"] or not selected["reviewer"].strip():
            raise ValueError(
                "Save the actual named registry choices privately before public conservation"
            )
        outgoing = choices(selected)
        if not outgoing["decisions"]:
            raise ValueError("Choose at least one actual registry review action")
        prior_ids = {row["item_id"] for row in public["ui_decisions"]["decisions"]}
        if prior_ids - {row["item_id"] for row in outgoing["decisions"]}:
            raise ValueError(
                "Explicitly reconsider every previously saved item before replacing public selections"
            )
    elif action == "apply":
        stored = public["ui_decisions"]
        if (
            args["public_decisions_sha256"] != base["public_decisions_sha256"]
            or not stored["decisions"]
            or not isinstance(args["reviewer"], str)
            or args["reviewer"].strip() != stored.get("reviewer")
        ):
            raise ValueError(
                "Apply only the exact saved public choices with their declared actual reviewer"
            )
        outgoing = {
            "reviewer": stored["reviewer"],
            "decision_source": "vera_native_human_review",
            "decisions": [
                {
                    k: row[k]
                    for k in (
                        "item_id",
                        "action",
                        "reviewer_note",
                        "edit_value",
                        "requested_documents",
                    )
                    if k in row
                }
                for row in stored["decisions"]
            ],
        }
    if action in {"save", "apply"}:
        engine(
            root,
            {
                "operation": "preflight",
                "context": str(loaded["context_path"]),
                "choices": outgoing,
            },
            api,
        )
    with api.write_lock(current["output"]):
        fresh = snapshot(binding, api.load_binding(binding), root, api)
        if (
            fresh["revision"] != current["revision"]
            or fresh["draft_revision"] != current["draft_revision"]
            or fresh["state"] != current["state"]
        ):
            raise ValueError("Registry review changed before write")
        if action in {"draft_save", "draft_clear"}:
            value = (
                selected
                if action == "draft_save"
                else {"reviewer": "", "decisions": {}}
            )
            saved = {
                "scope": current["scope"],
                "generation": current["draft"]["generation"] + 1,
                "fields": value,
            }
            api.atomic_json(current["draft_path"], saved)
            return {
                "work_ref": binding["work_ref"],
                "revision": current["revision"],
                "saved": True,
                "fields": value,
                "draft_revision": stamp(saved),
                "draft_stale": False,
                "status": "private_choices_saved",
            }
        reference = "review-" + stamp([request, key])
        directory = (
            api.ui_state_directory(current["output"])
            / "sari-review-receipts"
            / reference
        )
        row = {
            "key": key,
            "request": request,
            "fingerprint": stamp(request),
            "snapshot_ref": reference,
            "status": "pending",
        }
        state = current["state"]
        state["operations"].append(row)
        bounded(state, 2_000_000)
        ledger = (
            api.ui_state_directory(current["output"]) / "sari-review-operations.json"
        )
        api.atomic_json(ledger, state)
        directory.parent.mkdir(mode=0o700, exist_ok=True)
        directory.parent.chmod(0o700)
        directory.mkdir(mode=0o700)
        for name in MUTABLE & current["files"].keys():
            shutil.copyfile(current["output"] / name, directory / name)
            (directory / name).chmod(0o600)
        outcome = engine(
            root,
            {
                "operation": action,
                "context": str(loaded["context_path"]),
                "choices": outgoing,
            },
            api,
        )["payload"]
        after = tree_hash(current["output"])
        run = api.load_binding(binding)
        changed = {
            name
            for name in set(after) | set(current["files"])
            if after.get(name) != current["files"].get(name)
        }
        if (
            changed - MUTABLE
            or run["run"] != loaded["run"]
            or run["input_manifest"] != loaded["input_manifest"]
        ):
            raise ValueError(
                "Registry public review changed unapproved output or run scope; ordinary recovery required"
            )
        result = {
            "work_ref": binding["work_ref"],
            "saved": True,
            "status": outcome.get(
                "application_status", outcome["status"] if "status" in outcome else None
            ),
            "public_operation": action,
            "public_result": outcome,
            "actual_model_reads_verified": False,
        }
        receipt = {
            "result": result,
            "before_files": current["files"],
            "after_files": after,
            "preserved_before": tree_hash(directory),
        }
        row.update(status="complete", receipt=receipt, receipt_sha256=stamp(receipt))
        api.atomic_json(ledger, state)
        return bounded(result)
