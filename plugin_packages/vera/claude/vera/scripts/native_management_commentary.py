"""Whole model commentary, named readback and normal same-run report conservation.

Hashes, schema/metric references, CAS and lifecycle are mechanical contracts.
The model and professional judge prose, causation and business significance.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from pathlib import Path
from typing import Any

from native_bank_preparation import file_hash, tree_hash
from native_management_execution import bounded, bridge, context, directory
from native_variance_review import fields

__all__ = ["audit_commentary", "dispatch"]
COMMENTARY_KEYS = {
    "schema_version",
    "workflow_id",
    "pack_sha256",
    "observations",
    "hypotheses",
    "questions",
    "limitations",
}
FINAL_OUTPUTS = {
    "management_control_report.md",
    "management_control_dashboard_reviewed.html",
    "commentary_receipt.json",
}


def public(root: Path, request: dict) -> dict:
    completed = subprocess.run(
        [
            sys.executable,
            "-I",
            "-B",
            str(Path(__file__).with_name("native_management_commentary_bridge.py")),
            str(root),
        ],
        input=json.dumps(request),
        capture_output=True,
        text=True,
        check=False,
        timeout=90,
    )
    if completed.returncode:
        raise ValueError(completed.stderr.strip().splitlines()[-1])
    return json.loads(completed.stdout)


def audit_commentary(output: Path, api: Any) -> dict:
    """Check every whole proposal/report and refuse partial write adoption."""
    private = api.ui_state_directory(output, create=False)
    path = private / "management-commentary-state.json"
    state = api.read_json(path) if path.exists() else {"versions": []}
    candidates, conserved = set(), set()
    for row in state["versions"]:
        ref = row["case_ref"]
        if (
            not re.fullmatch(r"management-commentary-[a-f0-9]{64}", ref)
            or ref in candidates
            or tree_hash(private / ref) != row["artifacts"]
            or {p.name for p in (private / ref).iterdir()}
            != {"management_commentary.json", "proposal.json"}
        ):
            raise ValueError("Complete management commentary proposal changed")
        candidates.add(ref)
        proposal = api.read_json(private / ref / "proposal.json")
        if proposal["scope"] != row["scope"] or proposal[
            "commentary_sha256"
        ] != file_hash(private / ref / "management_commentary.json"):
            raise ValueError("Management commentary proposal receipt disagrees")
        if row["status"] == "pending":
            if "conservation" in row:
                raise ValueError("Pending commentary cannot have conserved readback")
            continue
        if row["status"] not in {"accepted", "rejected", "changes_requested"}:
            raise ValueError("Unknown named management commentary decision")
        saved = row["conservation"]
        ref = saved["output_ref"]
        if (
            not re.fullmatch(r"codex-management-notes-[a-f0-9]{64}", ref)
            or ref in conserved
        ):
            raise ValueError("Invalid conserved management commentary identity")
        conserved.add(ref)
        folder = output / ref
        expected = {"management_commentary.json", "native_commentary_readback.json"}
        if row["status"] == "accepted":
            expected |= FINAL_OUTPUTS
        if (
            tree_hash(folder) != saved["artifacts"]
            or {p.name for p in folder.iterdir()} != expected
        ):
            raise ValueError("Conserved management commentary/report bytes changed")
        receipt = api.read_json(folder / "native_commentary_readback.json")
        if (
            receipt["scope"] != row["scope"]
            or receipt["case_ref"] != row["case_ref"]
            or receipt["review"]["decision"] != row["status"]
            or receipt["review"] != saved["review"]
            or receipt["commentary_sha256"] != proposal["commentary_sha256"]
            or file_hash(folder / "management_commentary.json")
            != proposal["commentary_sha256"]
        ):
            raise ValueError("Named management readback disagrees with whole proposal")
    requests = [
        api.read_json(p) for p in private.glob("management-commentary-request-*.json")
    ]
    if any(
        r["result"]["case_ref"] not in candidates
        or ("output_ref" in r["result"] and r["result"]["output_ref"] not in conserved)
        for r in requests
        if "result" in r
    ):
        raise ValueError("Management commentary request lost its conserved proposal")
    return {
        "state": state,
        "private": private,
        "recovery_required": any("result" not in r for r in requests)
        or any(
            p.name not in candidates for p in private.glob("management-commentary-*/")
        )
        or any(
            p.name not in conserved for p in output.glob("codex-management-notes-*")
        ),
        "pending": any(r["status"] == "pending" for r in state["versions"]),
    }


def snapshot(binding: dict, loaded: dict, root: Path, api: Any, args: dict) -> dict:
    current = context(binding, loaded, root, api)
    current["folder"] = directory(current, args)
    current["stable"] = {
        **current["stable"],
        "calculation": args["source_ref"],
        "artifacts": current["saved"]["artifacts"],
        "commentary_implementation": {
            name: file_hash(Path(__file__).with_name(name))
            for name in (
                "native_management_commentary.py",
                "native_management_commentary_bridge.py",
                "native_variance_review.py",
            )
        },
    }
    current["revision"] = api.digest([current["stable"], loaded["run"]])
    current["commentary"] = audit_commentary(current["output"], api)
    return current


def candidate(current: dict, args: dict) -> dict:
    chosen = next(
        (
            r
            for r in current["commentary"]["state"]["versions"]
            if r["case_ref"] == args["case_ref"]
        ),
        None,
    )
    if chosen is None or chosen["scope"] != current["stable"]:
        raise ValueError("Choose this exact calculation's complete commentary")
    return chosen


def draft(current: dict, row: dict, api: Any) -> tuple[Path, dict, str]:
    scope = [current["stable"], row["case_ref"], row["artifacts"]]
    path = current["private"] / (
        "management-commentary-draft-" + api.digest(scope) + ".json"
    )
    value = (
        api.read_json(path)
        if path.exists()
        else {
            "scope": scope,
            "generation": 0,
            "fields": dict.fromkeys(
                ("decision", "reviewer", "reviewed_at", "basis"), ""
            ),
        }
    )
    if value["scope"] != scope:
        raise PermissionError("Commentary readback draft belongs to another proposal")
    fields(value["fields"], final=False)
    return path, value, api.digest(value)


def dispatch(
    tool: str, args: dict, binding: dict, loaded: dict, root: Path, api: Any
) -> dict:
    """Stage complete commentary; conserve named decisions without approving delivery."""
    action = tool.removeprefix("vera_workspace_management_commentary_")
    current = snapshot(binding, loaded, root, api, args)
    audit = current["commentary"]
    writable = (
        loaded["run"]["status"] == "running"
        and "REVIEWER" in os.environ.get("VERA_WORKSPACE_ROLES", "").split(",")
        and not audit["recovery_required"]
    )
    status = current["saved"]["result"]["status"]
    common = {
        "work_ref": args["work_ref"],
        "source_ref": args["source_ref"],
        "revision": current["revision"],
        "calculation_status": status,
        "data": {"selection": {"source_ref": args["source_ref"]}},
        "professional_approval": False,
        "actual_model_reads_verified": False,
        "run_completed": False,
    }
    if action == "setup":
        return bounded(
            {
                **common,
                "can_stage": writable and status != "blocked",
                "recovery_required": audit["recovery_required"],
                "versions": [
                    {k: row[k] for k in ("case_ref", "status")}
                    for row in audit["state"]["versions"]
                    if row["scope"] == current["stable"]
                ],
            }
        )
    if action == "read":
        row = candidate(current, args)
        _, saved, stamp = draft(current, row, api)
        conservation = row.get("conservation")
        return bounded(
            {
                **common,
                "selection": {"id": row["case_ref"]},
                "status": row["status"],
                "can_write": writable and row["status"] == "pending",
                "commentary": api.read_json(
                    current["private"] / row["case_ref"] / "management_commentary.json"
                ),
                "draft": saved["fields"],
                "draft_revision": stamp,
                "conservation": conservation,
                "files": (
                    [
                        {"name": p.name, "path": str(p), "sha256": file_hash(p)}
                        for p in sorted(
                            (current["output"] / conservation["output_ref"]).iterdir()
                        )
                    ]
                    if conservation
                    else []
                ),
            },
            maximum=128000,
        )
    if action == "context":
        if args["revision"] != current["revision"] or audit["recovery_required"]:
            raise ValueError("Reopen this exact complete management commentary context")
        result = {
            **{k: v for k, v in common.items() if k != "data"},
            **bridge(root, {"operation": "context", "output": str(current["folder"])}),
            "public_skill": {
                "authorized_path": str(
                    root / "skills/management-control-pack/SKILL.md"
                ),
                "sha256": file_hash(root / "skills/management-control-pack/SKILL.md"),
            },
            "evidence_status": "untrusted_exact_generated_management_context",
        }
        if args.get("case_ref"):
            row = candidate(current, args)
            result["chosen_commentary"] = api.read_json(
                current["private"] / row["case_ref"] / "management_commentary.json"
            )
        return bounded(result, maximum=384000)
    if action not in {"stage", "draft_save", "commit"} or not writable:
        raise PermissionError(
            "Commentary requires an owned running reviewer without uncertain writes"
        )
    with api.write_lock(current["output"]):
        latest = api.load_binding(binding)
        current = snapshot(binding, latest, root, api, args)
        if (
            latest["run"]["status"] != "running"
            or current["commentary"]["recovery_required"]
        ):
            raise PermissionError("The current commentary run cannot be written")
        state = current["commentary"]["state"]
        key, intent = args.get("idempotency_key"), None
        fingerprint = api.digest([current["stable"], latest["run"], tool, args])
        if action != "draft_save":
            if not isinstance(key, str) or not re.fullmatch(
                r"[A-Za-z0-9_-]{1,120}", key
            ):
                raise ValueError("Invalid management commentary request identity")
            intent = current["private"] / (
                "management-commentary-request-"
                + api.digest([current["stable"]["owner"], key])
                + ".json"
            )
            if intent.exists():
                previous = api.read_json(intent)
                if (
                    previous["request_sha256"] != fingerprint
                    or "result" not in previous
                ):
                    raise ValueError(
                        "Changed or uncertain commentary retry requires recovery"
                    )
                return previous["result"]
        if args["revision"] != current["revision"]:
            raise ValueError("Reopen this exact management commentary revision")
        if action == "stage":
            commentary = args["commentary"]
            if (
                not isinstance(commentary, dict)
                or set(commentary) != COMMENTARY_KEYS
                or len(json.dumps(commentary, ensure_ascii=False).encode()) > 96000
            ):
                raise ValueError(
                    "Stage the complete normal commentary within 96 KiB; use the file path for larger work"
                )
            public(
                root,
                {
                    "operation": "validate",
                    "pack": str(current["folder"] / "management_control_pack.json"),
                    "commentary": commentary,
                },
            )
            ref = "management-commentary-" + api.digest(
                [current["stable"], commentary, key]
            )
            folder = current["private"] / ref
            api.atomic_json(intent, {"request_sha256": fingerprint})
            folder.mkdir(exist_ok=False)
            api.atomic_json(folder / "management_commentary.json", commentary)
            api.atomic_json(
                folder / "proposal.json",
                {
                    "scope": current["stable"],
                    "commentary_sha256": file_hash(
                        folder / "management_commentary.json"
                    ),
                    "actual_model_reads_verified": False,
                },
            )
            state["versions"].append(
                {
                    "scope": current["stable"],
                    "case_ref": ref,
                    "status": "pending",
                    "artifacts": tree_hash(folder),
                }
            )
            result = {
                "saved": True,
                "case_ref": ref,
                "status": "commentary_proposed_for_review",
                **common,
            }
        else:
            row = candidate(current, args)
            path, saved, stamp = draft(current, row, api)
            if (
                row["status"] != "pending"
                or args["item_id"] != row["case_ref"]
                or args["expected_draft_revision"] != stamp
            ):
                raise ValueError(
                    "Choose this exact pending commentary and current draft"
                )
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
                    "Renew confirmation of the complete named commentary readback"
                )
            review = fields(saved["fields"], final=True)
            proposal = (
                current["private"] / row["case_ref"] / "management_commentary.json"
            )
            if review["decision"] == "accepted":
                public(
                    root,
                    {
                        "operation": "validate",
                        "pack": str(current["folder"] / "management_control_pack.json"),
                        "commentary": api.read_json(proposal),
                    },
                )
            ref = "codex-management-notes-" + api.digest(
                [current["stable"], row["case_ref"], review, key]
            )
            folder = current["output"] / ref
            api.atomic_json(intent, {"request_sha256": fingerprint})
            folder.mkdir(exist_ok=False)
            (folder / "management_commentary.json").write_bytes(proposal.read_bytes())
            if review["decision"] == "accepted":
                public(
                    root,
                    {
                        "operation": "finalize",
                        "pack": str(current["folder"] / "management_control_pack.json"),
                        "commentary": str(folder / "management_commentary.json"),
                        "context": latest["context_path"],
                        "output": str(folder),
                    },
                )
            receipt = {
                "schema_version": "vera.native.management_commentary_readback.v1",
                "scope": current["stable"],
                "case_ref": row["case_ref"],
                "commentary_sha256": file_hash(proposal),
                "review": review,
                "calculation_status": status,
                "report_status": (
                    "draft_pending_professional_review"
                    if review["decision"] == "accepted"
                    else "commentary_not_accepted"
                ),
                "actual_model_reads_verified": False,
                "record_actual_model_reads_in_run_report": True,
                "reviewer_authenticated": False,
                "professional_approval": False,
                "run_completed": False,
                "sent_or_published": False,
            }
            api.atomic_json(folder / "native_commentary_readback.json", receipt)
            row.update(
                status=review["decision"],
                conservation={
                    "output_ref": ref,
                    "artifacts": tree_hash(folder),
                    "review": review,
                },
            )
            result = {
                "saved": True,
                "status": "commentary_readback_conserved",
                "work_ref": args["work_ref"],
                "case_ref": row["case_ref"],
                "output_ref": ref,
                "decision": review["decision"],
                "professional_approval": False,
                "run_completed": False,
                "sent_or_published": False,
            }
        after = context(binding, api.load_binding(binding), root, api)
        if after["scope"] != {**current["saved"]["scope"], "run": latest["run"]}:
            raise ValueError(
                "Management calculation scope changed during commentary conservation"
            )
        api.atomic_json(current["private"] / "management-commentary-state.json", state)
        api.atomic_json(intent, {"request_sha256": fingerprint, "result": result})
        return result
