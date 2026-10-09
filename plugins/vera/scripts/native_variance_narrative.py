"""Immutable host-authored Variance notes beside the sealed public calculation.

Hash/receipt identity, file shape, CAS and conservation are mechanical audit
contracts. The host model and professional alone judge the narrative content.
"""

from __future__ import annotations

import json
import os
import re
from pathlib import Path
from typing import Any

from native_bank_preparation import file_hash, tree_hash

__all__ = ["audit_narrative", "dispatch"]
DOCUMENTS = {
    "codex_business_analysis.md",
    "codex_root_cause_sweep_analysis.md",
    "codex_run_review.md",
}


def documents(value: Any) -> dict:
    """Keep every literal normal note; never grade prose by keywords or truncate."""
    if (
        not isinstance(value, dict)
        or set(value) != DOCUMENTS
        or any(not isinstance(v, str) or not v.strip() for v in value.values())
        or len(json.dumps(value, ensure_ascii=False).encode()) > 96000
    ):
        raise ValueError(
            "Supply all three complete Variance Markdown notes within 96 KiB"
        )
    return dict(value)


def audit_narrative(output: Path, api: Any) -> dict:
    """Uncertain note writes cannot be adopted, overwritten or silently closed."""
    private = api.ui_state_directory(output, create=False)
    state_path = private / "variance-narrative-state.json"
    state = api.read_json(state_path) if state_path.exists() else {"versions": []}
    candidates, outputs = set(), set()
    for row in state["versions"]:
        ref = row["case_ref"]
        if (
            not re.fullmatch(r"variance-narrative-[a-f0-9]{64}", ref)
            or ref in candidates
        ):
            raise ValueError("Invalid Variance narrative identity")
        candidates.add(ref)
        folder = private / ref
        if tree_hash(folder) != row["artifacts"]:
            raise ValueError("Complete proposed Variance notes changed")
        proposal = api.read_json(folder / "proposal.json")
        if proposal["scope"] != row["scope"] or set(proposal["documents"]) != DOCUMENTS:
            raise ValueError("Variance narrative scope or normal notes changed")
        for name, digest in proposal["documents"].items():
            if file_hash(folder / name) != digest:
                raise ValueError("Proposed Variance note differs from its receipt")
        if row["status"] == "pending":
            if "conservation" in row:
                raise ValueError("Pending Variance notes cannot have conservation")
            continue
        if row["status"] not in {"accepted", "rejected", "changes_requested"}:
            raise ValueError("Invalid named narrative decision")
        saved = row["conservation"]
        ref = saved["output_ref"]
        if not re.fullmatch(r"codex-notes-[a-f0-9]{64}", ref) or ref in outputs:
            raise ValueError("Invalid conserved Variance notes identity")
        outputs.add(ref)
        target = output / ref
        if tree_hash(target) != saved["artifacts"]:
            raise ValueError("Conserved Variance notes changed")
        receipt = api.read_json(target / "narrative_receipt.json")
        if (
            receipt["scope"] != row["scope"]
            or receipt["case_ref"] != row["case_ref"]
            or receipt["review"]["decision"] != row["status"]
            or receipt["documents"] != proposal["documents"]
        ):
            raise ValueError("Conserved Variance narrative receipt disagrees")
        for name, digest in proposal["documents"].items():
            if file_hash(target / name) != digest:
                raise ValueError(
                    "Conserved narrative differs from the complete proposal"
                )
    requests = [
        api.read_json(p) for p in private.glob("variance-narrative-request-*.json")
    ]
    return {
        "state": state,
        "recovery_required": any("result" not in r for r in requests)
        or any(p.name not in candidates for p in private.glob("variance-narrative-*/"))
        or any(p.name not in outputs for p in output.glob("codex-notes-*")),
        "pending": any(r["status"] == "pending" for r in state["versions"]),
    }


def snapshot(binding: dict, loaded: dict, root: Path, api: Any, args: dict) -> dict:
    from native_variance import context, directory

    current = context(binding, loaded, root, api)
    current["folder"] = directory(current, args)
    current["scope"] = {
        **current["scope"],
        "calculated_generation": args["source_ref"],
        "calculated_artifacts": current["saved"]["artifacts"],
        "narrative_implementation": file_hash(Path(__file__)),
    }
    current["revision"] = api.digest(current["scope"])
    current["narrative"] = audit_narrative(current["output"], api)
    current["readiness"] = api.read_json(current["folder"] / "final_artifacts.json")[
        "accounting_readiness"
    ]
    return current


def same_calculation(left: dict, right: dict) -> bool:
    """Lifecycle labels/status may change; calculation, owner and receipts may not."""
    return {k: v for k, v in left.items() if k != "run"} == {
        k: v for k, v in right.items() if k != "run"
    }


def candidate(current: dict, args: dict) -> dict:
    chosen = next(
        (
            r
            for r in current["narrative"]["state"]["versions"]
            if r["case_ref"] == args["case_ref"]
        ),
        None,
    )
    if chosen is None or not same_calculation(chosen["scope"], current["scope"]):
        raise ValueError("Select this exact calculation's complete narrative proposal")
    return chosen


def draft(current: dict, row: dict, api: Any) -> tuple[Path, dict, str]:
    from native_variance_review import fields

    scope = [current["scope"], row["case_ref"], row["artifacts"]]
    path = current["private"] / (
        "variance-narrative-draft-" + api.digest(scope) + ".json"
    )
    saved = (
        api.read_json(path)
        if path.exists()
        else {
            "scope": scope,
            "generation": 0,
            "fields": {"decision": "", "reviewer": "", "reviewed_at": "", "basis": ""},
        }
    )
    if saved["scope"] != scope:
        raise PermissionError("Narrative readback belongs to another exact proposal")
    fields(saved["fields"], final=False)
    return path, saved, api.digest(saved)


def model_context(current: dict, root: Path, args: dict, api: Any) -> dict:
    from native_variance import artifact, offset

    manifest_path = current["folder"] / "model_use_manifest.json"
    manifest = api.read_json(manifest_path)
    references = []
    for row in manifest["default_model_use"]["artifacts"]:
        path = artifact(current["folder"], row["path"])
        if file_hash(path) != row["sha256"] or path.stat().st_size != row["byte_count"]:
            raise ValueError("Default Variance model-use artifact changed")
        references.append({**row, "authorized_path": str(path)})
    # Visual QA follows numerical review; charts remain unchanged engine artifacts.
    charts = [
        {
            "path": p.relative_to(current["folder"]).as_posix(),
            "authorized_path": str(p),
            "sha256": file_hash(p),
        }
        for p in sorted(current["folder"].rglob("*.png"))
    ]
    records = [*references, *charts]
    start = offset(args)
    result = {
        "work_ref": args["work_ref"],
        "source_ref": args["source_ref"],
        "revision": current["revision"],
        "accounting_readiness": current["readiness"],
        "model_use_manifest": {
            "authorized_path": str(manifest_path),
            "sha256": file_hash(manifest_path),
        },
        "public_skill": {
            "authorized_path": str(root / "skills/variance-analysis/SKILL.md"),
            "sha256": file_hash(root / "skills/variance-analysis/SKILL.md"),
        },
        "artifacts": records[start : start + 30],
        "total": len(records),
        "offset": start,
        "has_more": start + 30 < len(records),
        "required_documents": sorted(DOCUMENTS),
        "evidence_status": "untrusted_exact_generated_variance_evidence",
        "actual_model_reads_verified": False,
        "record_actual_model_reads_in_run_report": True,
        "professional_approval": False,
        "run_completed": False,
    }
    if args.get("case_ref"):
        chosen = candidate(current, args)
        result["chosen_documents"] = {
            name: (current["private"] / chosen["case_ref"] / name).read_text(
                encoding="utf-8"
            )
            for name in sorted(DOCUMENTS)
        }
    return result


def dispatch(
    tool: str, args: dict, binding: dict, loaded: dict, root: Path, api: Any
) -> dict:
    from native_variance import bounded, context
    from native_variance_review import fields

    action = tool.removeprefix("vera_workspace_variance_narrative_")
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
                "can_write": writable,
                "accounting_readiness": current["readiness"],
                "versions": [
                    {k: row[k] for k in ("case_ref", "status")}
                    for row in current["narrative"]["state"]["versions"]
                    if same_calculation(row["scope"], current["scope"])
                ],
                "data": {"selection": {"source_ref": args["source_ref"]}},
                "required_documents": sorted(DOCUMENTS),
                "professional_approval": False,
                "run_completed": False,
            }
        )
    if action == "context":
        if args["revision"] != current["revision"]:
            raise ValueError("Reopen this exact Variance narrative context")
        return bounded(model_context(current, root, args, api), maximum=128000)
    if action == "read":
        row = candidate(current, args)
        _, saved, stamp = draft(current, row, api)
        return bounded(
            {
                "work_ref": args["work_ref"],
                "source_ref": args["source_ref"],
                "revision": current["revision"],
                "selection": {"id": row["case_ref"]},
                "data": {"selection": {"source_ref": args["source_ref"]}},
                "status": row["status"],
                "can_write": writable and row["status"] == "pending",
                "documents": {
                    name: (current["private"] / row["case_ref"] / name).read_text(
                        encoding="utf-8"
                    )
                    for name in sorted(DOCUMENTS)
                },
                "accounting_readiness": current["readiness"],
                "draft": saved["fields"],
                "draft_revision": stamp,
                "conservation": row.get("conservation"),
                "files": (
                    [
                        {
                            "name": name,
                            "path": str(
                                current["output"]
                                / row["conservation"]["output_ref"]
                                / name
                            ),
                            "sha256": file_hash(
                                current["output"]
                                / row["conservation"]["output_ref"]
                                / name
                            ),
                        }
                        for name in sorted([*DOCUMENTS, "narrative_receipt.json"])
                    ]
                    if "conservation" in row
                    else []
                ),
                "professional_approval": False,
                "run_completed": False,
            },
            maximum=128000,
        )
    if action not in {"stage", "draft_save", "commit"} or not writable:
        raise PermissionError("Variance notes require an owned running reviewer")
    with api.write_lock(current["output"]):
        current = snapshot(binding, api.load_binding(binding), root, api, args)
        state = current["narrative"]["state"]
        fingerprint = api.digest([current["scope"], tool, args])
        key, intent = args.get("idempotency_key"), None
        if action != "draft_save":
            if not isinstance(key, str) or not re.fullmatch(
                r"[A-Za-z0-9_-]{1,120}", key
            ):
                raise ValueError("Invalid Variance narrative request key")
            intent = current["private"] / (
                "variance-narrative-request-"
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
                        "Changed or uncertain narrative retry requires recovery"
                    )
                return previous["result"]
        if args["revision"] != current["revision"]:
            raise ValueError("Review this exact current Variance narrative")
        if action == "stage":
            notes = documents(args["documents"])
            ref = "variance-narrative-" + api.digest([current["scope"], notes, key])
            folder = current["private"] / ref
            api.atomic_json(intent, {"request_sha256": fingerprint})
            folder.mkdir(exist_ok=False)
            for name, text in notes.items():
                (folder / name).write_text(text, encoding="utf-8")
            api.atomic_json(
                folder / "proposal.json",
                {
                    "scope": current["scope"],
                    "documents": {name: file_hash(folder / name) for name in notes},
                    "actual_model_reads_verified": False,
                },
            )
            state["versions"].append(
                {
                    "scope": current["scope"],
                    "case_ref": ref,
                    "status": "pending",
                    "artifacts": tree_hash(folder),
                }
            )
            result = {
                "saved": True,
                "status": "narrative_proposed_for_review",
                "case_ref": ref,
                "work_ref": args["work_ref"],
                "actual_model_reads_verified": False,
                "professional_approval": False,
                "run_completed": False,
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
                    "Review only this pending exact narrative and current draft"
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
                    "Renew confirmation of this saved narrative readback"
                )
            review = fields(saved["fields"], final=True)
            api.atomic_json(intent, {"request_sha256": fingerprint})
            ref = "codex-notes-" + api.digest(
                [current["scope"], row["case_ref"], review, key]
            )
            folder = current["output"] / ref
            folder.mkdir(exist_ok=False)
            proposal = api.read_json(
                current["private"] / row["case_ref"] / "proposal.json"
            )
            for name in sorted(DOCUMENTS):
                (folder / name).write_bytes(
                    (current["private"] / row["case_ref"] / name).read_bytes()
                )
            receipt = {
                "schema_version": "vera.native.variance_narrative_receipt.v1",
                "scope": current["scope"],
                "case_ref": row["case_ref"],
                "documents": proposal["documents"],
                "review": review,
                "accounting_readiness": current["readiness"],
                "actual_model_reads_verified": False,
                "record_actual_model_reads_in_run_report": True,
                "reviewer_authenticated": False,
                "professional_approval": False,
                "run_completed": False,
                "sent_or_published": False,
            }
            api.atomic_json(folder / "narrative_receipt.json", receipt)
            row["status"] = review["decision"]
            row["conservation"] = {
                "output_ref": ref,
                "artifacts": tree_hash(folder),
                "review": review,
            }
            result = {
                "saved": True,
                "status": "narrative_readback_conserved",
                "work_ref": args["work_ref"],
                "case_ref": row["case_ref"],
                "output_ref": ref,
                "decision": review["decision"],
                "professional_approval": False,
                "run_completed": False,
                "sent_or_published": False,
            }
        after = context(binding, api.load_binding(binding), root, api)
        for name in ("owner", "run", "inputs", "implementation"):
            if after["scope"][name] != current["scope"][name]:
                raise ValueError(
                    "Variance calculation scope changed during narrative conservation"
                )
        if file_hash(Path(__file__)) != current["scope"]["narrative_implementation"]:
            raise ValueError(
                "Variance narrative implementation changed during conservation"
            )
        api.atomic_json(current["private"] / "variance-narrative-state.json", state)
        api.atomic_json(intent, {"request_sha256": fingerprint, "result": result})
        return result
