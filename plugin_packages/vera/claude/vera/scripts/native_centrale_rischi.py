"""Immutable native CR inspection, reviewed calculation and evidence-linked drafts."""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

from native_bank_preparation import file_hash, tree_hash
from native_financial_analysis import json_page

__all__ = ["audit_run", "dispatch", "read_prepared"]
PREFIX = "vera_workspace_cr_"
PHASE_FILES = {
    "inspection": "inspection.json",
    "analysis": "centrale_rischi_analysis.json",
    "report": "commentary_receipt.json",
}


def engine_call(root: Path, request: dict) -> dict:
    """No provider calls or substitute parser; an interrupted write remains uncertain."""
    result = subprocess.run(
        [
            sys.executable,
            "-I",
            "-B",
            str(Path(__file__).with_name("native_centrale_rischi_bridge.py")),
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
            result.stderr.strip().splitlines()[-1] or "CR producer refused"
        )
    return json.loads(result.stdout)


def audit_run(output: Path, api: Any) -> dict:
    """Refuse archive closure after uncertainty or changed native artifact populations."""
    private = api.ui_state_directory(output, create=False)
    state = (
        api.read_json(private / "cr-state.json")
        if (private / "cr-state.json").exists()
        else {"versions": []}
    )
    known = set()
    for row in state["versions"]:
        identity = row["source_ref"]
        if not re.fullmatch(r"cr-[0-9a-f]{64}", identity) or identity in known:
            raise ValueError("Invalid or duplicate CR revision")
        known.add(identity)
        if tree_hash(output / identity) != row["artifacts"]:
            raise ValueError("CR revision artifacts changed")
    uncertain = any(
        "result" not in api.read_json(p) for p in private.glob("cr-request-*.json")
    )
    unknown = any(p.name not in known for p in output.glob("cr-*"))
    return {"state": state, "recovery_required": uncertain or unknown}


def context(binding: dict, loaded: dict, root: Path, api: Any) -> dict:
    """Bind state to current owner, receipts, implementation and every retained version."""
    if binding["workflow_id"] != "centrale-rischi-review":
        raise PermissionError("CR action belongs to another workflow")
    output = Path(loaded["output_dir"])
    audit = audit_run(output, api)
    implementation = {
        "producer": engine_call(root, {"operation": "implementation"}),
        "adapter": file_hash(Path(__file__)),
        "bridge": file_hash(
            Path(__file__).with_name("native_centrale_rischi_bridge.py")
        ),
        "editor": file_hash(
            Path(__file__).with_name("native_centrale_rischi_editor.py")
        ),
        "drafts": file_hash(
            Path(__file__).with_name("native_centrale_rischi_drafts.py")
        ),
    }
    owner = [
        os.environ["VERA_WORKSPACE_ACTOR_ID"],
        os.environ["VERA_WORKSPACE_TENANT_ID"],
        binding,
    ]
    for row in audit["state"]["versions"]:
        if row["owner"] != owner or row["implementation"] != implementation:
            raise PermissionError(
                "CR version belongs to a different owner or implementation"
            )
        if row["inputs"] != loaded["input_manifest"]:
            raise ValueError("CR input population changed")
    return {
        **audit,
        "output": output,
        "private": api.ui_state_directory(output, create=False),
        "implementation": implementation,
        "owner": owner,
        "revision": api.digest(
            [owner, loaded["run"], loaded["input_manifest"], audit, implementation]
        ),
    }


def version(current: dict, reference: str) -> dict:
    """A version is always explicitly selected; never infer the newest one."""
    selected = next(
        (row for row in current["state"]["versions"] if row["source_ref"] == reference),
        None,
    )
    if selected is None:
        raise ValueError("Choose an exact retained CR version")
    return selected


def selected_inputs(loaded: dict, identities: list[str]) -> list[str]:
    """Use only receipt-bound sources; extensions filter formats, not semantic roles."""
    rows = {row["binding_id"]: row for row in loaded["input_manifest"]["inputs"]}
    if (
        not identities
        or len(set(identities)) != len(identities)
        or not set(identities) <= set(rows)
    ):
        raise ValueError("Choose distinct registered CR sources")
    paths = [
        Path(loaded["run_root"]) / rows[key]["execution_relative_path"]
        for key in identities
    ]
    if any(p.suffix.lower() not in {".pdf", ".csv", ".xlsx", ".xlsm"} for p in paths):
        raise ValueError("CR requires digital PDF or reviewed tabular source; no OCR")
    for identity, path in zip(identities, paths):
        if file_hash(path) != rows[identity]["sha256"]:
            raise ValueError("Registered CR source bytes changed")
    return [str(p) for p in paths]


def source_selector(value: Any) -> dict:
    """Validate mechanical navigation coordinates; never choose columns or roles."""
    if not isinstance(value, dict) or set(value) != {
        "table_id",
        "kind",
        "column",
        "offset",
    }:
        raise ValueError("Invalid CR source selector")
    if (
        not isinstance(value["table_id"], str)
        or len(value["table_id"]) > 200
        or not isinstance(value["kind"], str)
        or value["kind"] not in {"rows", "values"}
        or not isinstance(value["column"], str)
        or len(value["column"]) > 4000
        or not isinstance(value["offset"], int)
        or isinstance(value["offset"], bool)
        or value["offset"] < 0
        or not value["table_id"]
        and (value["column"] or value["kind"] != "rows")
    ):
        raise ValueError("Invalid CR source navigation")
    return value


def read_source(current: dict, loaded: dict, root: Path, args: dict, api: Any) -> dict:
    """Bind complete parsed-source navigation to the selected immutable inspection."""
    row = version(current, args["source_ref"])
    if row["phase"] != "inspection":
        raise ValueError("Choose the exact CR inspection to review source rows")
    selector = source_selector(args["source_selector"])
    directory = current["output"] / row["source_ref"]
    inspection = api.read_json(directory / "inspection.json")
    page = engine_call(
        root,
        {
            "operation": "source_page",
            "inputs": selected_inputs(loaded, row["input_ids"]),
            "recipe": str(directory / "suggested_recipe.json"),
            "inventory_sha256": inspection["inventory_sha256"],
            "selector": selector,
        },
    )
    selected_inputs(api.load_binding(current["owner"][2]), row["input_ids"])
    if tree_hash(directory) != row["artifacts"]:
        raise ValueError("CR inspection artifacts changed during source reading")
    source = {
        "source_ref": row["source_ref"],
        "inventory_sha256": inspection["inventory_sha256"],
        "source_kind": api.read_json(directory / "suggested_recipe.json")[
            "source_kind"
        ],
        "source_selector": selector,
        "page": page,
    }
    return {
        "work_ref": current["owner"][2]["work_ref"],
        "revision": current["revision"],
        "selection": {"id": "source-page-" + api.digest(source)},
        "data": {"selection": {"source_ref": row["source_ref"]}},
        "source": source,
        "professional_approval": False,
        "model_grant_issued": False,
    }


def read_prepared(
    root: Path, binding: dict, loaded: dict, args: dict, api: Any
) -> dict:
    """Read exact JSON pages or complete producer text artifacts in the private panel."""
    current = context(binding, loaded, root, api)
    row = version(current, args.get("source_ref"))
    directory = current["output"] / row["source_ref"]
    files = [
        name
        for name in row["artifacts"]
        if Path(name).suffix in {".json", ".html", ".md"}
    ]
    selected = None
    if args.get("item_id"):
        if args["item_id"] not in files:
            raise ValueError("Unknown CR readable artifact")
        name = args["item_id"]
        selected = {"id": name, "title": name}
        if name.endswith(".json"):
            selected["prepared_context"] = json_page(
                api.read_json(directory / name), args.get("member_ref")
            )
        else:
            if args.get("member_ref"):
                raise ValueError("Text previews require the complete artifact")
            selected["artifact_preview"] = {
                "format": "html" if name.endswith(".html") else "markdown",
                "content": (directory / name).read_bytes().decode("utf-8"),
                "sha256": row["artifacts"][name],
                "complete": True,
            }
    offset = args.get("offset", 0)
    if not isinstance(offset, int) or isinstance(offset, bool) or offset < 0:
        raise ValueError("Invalid CR page offset")
    if tree_hash(directory) != row["artifacts"]:
        raise ValueError("CR artifacts changed during reading")
    return {
        "revision": current["revision"],
        "items": [
            {"id": name, "title": name, "status": row["status"]}
            for name in files[offset : offset + 30]
        ],
        "total": len(files),
        "selection": selected,
        "data": {
            "local_review_read_only": True,
            "phase": row["phase"],
            "status": row["status"],
            "selection": {"source_ref": row["source_ref"]},
            "artifacts": list(row["artifacts"]),
            "recovery_required": current["recovery_required"],
            "professional_approval": False,
        },
    }


def dispatch(
    tool: str, args: dict, binding: dict, loaded: dict, root: Path, api: Any
) -> dict:
    """Separate model proposals, signed mapping review, calculations and draft reports."""
    current = context(binding, loaded, root, api)
    action = tool.removeprefix(PREFIX)
    if action in {"draft_read", "draft_save"}:
        from native_centrale_rischi_drafts import dispatch as draft_dispatch

        return draft_dispatch(action, args, binding, loaded, root, api, current)
    if action.startswith("recipe_"):
        from native_centrale_rischi_editor import dispatch as editor_dispatch

        return editor_dispatch(action, args, binding, loaded, root, api, current)
    if action == "source":
        return read_source(current, loaded, root, args, api)
    if action == "setup":
        offset = args.get("offset", 0)
        if not isinstance(offset, int) or isinstance(offset, bool) or offset < 0:
            raise ValueError("Invalid CR page offset")
        candidates = [
            {
                "id": row["binding_id"],
                "title": Path(row["execution_relative_path"]).name,
            }
            for row in loaded["input_manifest"]["inputs"]
            if Path(row["execution_relative_path"]).suffix.lower()
            in {".pdf", ".csv", ".xlsx", ".xlsm"}
        ]
        return {
            "work_ref": binding["work_ref"],
            "revision": current["revision"],
            "label": loaded["run"]["label"],
            "status": "recovery_required" if current["recovery_required"] else "ready",
            "can_write": not current["recovery_required"]
            and loaded["run"]["status"] == "running"
            and "REVIEWER" in os.environ.get("VERA_WORKSPACE_ROLES", "").split(","),
            "items": candidates[offset : offset + 30],
            "offset": offset,
            "total": len(candidates),
            "has_more": offset + 30 < len(candidates),
            "versions": [
                {k: row[k] for k in ("source_ref", "phase", "status")}
                for row in current["state"]["versions"][offset : offset + 30]
            ],
            "versions_total": len(current["state"]["versions"]),
        }
    if action in {"view", "proposal_read"}:
        if action == "view":
            result = read_prepared(root, binding, loaded, args, api)
            return {"work_ref": binding["work_ref"], **result}
        grant = grant_record(current, args, api)
        candidate, selected = read_proposal(current, grant, args, root, api)
        result = {
            "work_ref": binding["work_ref"],
            "revision": current["revision"],
            "data": {"selection": {"source_ref": grant["source_ref"]}},
            "proposal": selected,
            "proposal_sha256": api.digest(selected),
            "kind": grant["kind"],
            "grant_ref": grant["grant_ref"],
        }
        if args.get("proposal_sha256"):
            result.update(
                selection={"id": "cr-proposal-" + api.digest(selected)},
                history_selected=True,
                is_current=selected == candidate["proposal"],
                proposal_revision=api.digest(candidate),
            )
            if grant["kind"] == "recipe":
                from native_centrale_rischi_editor import snapshot

                _, stored, stamp, _, _ = snapshot(current, grant, api)
                result["draft_revision"] = stamp
                result["draft_exists"] = bool(stored and stored["fields"] is not None)
        return result
    if action == "proposal_history":
        grant = grant_record(current, args, api)
        candidate, _ = read_proposal(current, grant, {}, root, api)
        offset = args.get("offset", 0)
        if not isinstance(offset, int) or isinstance(offset, bool) or offset < 0:
            raise ValueError("Invalid CR proposal history page")
        prefix = grant["grant_ref"] + "-proposal-"
        paths = sorted(current["private"].glob(prefix + "*.json"))
        if any(
            not re.fullmatch(re.escape(prefix) + r"[0-9a-f]{64}\.json", p.name)
            for p in paths
        ):
            raise ValueError("Invalid CR proposal history identity")
        rows = []
        for path in paths[offset : offset + 30]:
            sha = path.stem.removeprefix(prefix)
            _, selected = read_proposal(
                current, grant, {"proposal_sha256": sha}, root, api
            )
            rows.append(
                {
                    "proposal_sha256": sha,
                    "is_current": selected == candidate["proposal"],
                }
            )
        return {
            "grant_ref": grant["grant_ref"],
            "source_ref": grant["source_ref"],
            "kind": grant["kind"],
            "rows": rows,
            "offset": offset,
            "total": len(paths),
            "has_more": offset + 30 < len(paths),
        }
    if action == "grants":
        version(current, args["source_ref"])
        offset = args.get("offset", 0)
        if not isinstance(offset, int) or isinstance(offset, bool) or offset < 0:
            raise ValueError("Invalid CR grants page")
        grants = []
        for path in sorted(current["private"].glob("cr-grant-*.json")):
            if not re.fullmatch(r"cr-grant-[0-9a-f]{64}\.json", path.name):
                continue
            grant = grant_record(current, {"grant_ref": path.stem}, api)
            if grant["source_ref"] == args["source_ref"]:
                grants.append(
                    {
                        **{k: grant[k] for k in ("grant_ref", "question", "kind")},
                        "proposal_available": (
                            current["private"] / (grant["grant_ref"] + "-proposal.json")
                        ).exists(),
                        **(
                            {"source_selector": grant["source_selector"]}
                            if "source_selector" in grant
                            else {}
                        ),
                    }
                )
        return {
            "grants": grants[offset : offset + 30],
            "offset": offset,
            "total": len(grants),
            "has_more": offset + 30 < len(grants),
        }
    if action == "model_context":
        grant = grant_record(current, args, api)
        row = version(current, grant["source_ref"])
        directory = current["output"] / row["source_ref"]
        result = {
            "grant_ref": grant["grant_ref"],
            "question": grant["question"],
            "kind": grant["kind"],
            "context": api.read_json(
                directory
                / (
                    "inspection.json"
                    if grant["kind"] == "recipe"
                    else "model_context.json"
                )
            ),
            "template": api.read_json(
                directory
                / (
                    "suggested_recipe.json"
                    if grant["kind"] == "recipe"
                    else "commentary_template.json"
                )
            ),
            "proposal_revision": proposal_revision(current, grant, api),
            "source_scope": "public bounded inspection or prepared model context only; no raw population or original path",
            "professional_approval": False,
        }
        if "source_selection" in grant:
            selected = read_source(current, loaded, root, grant, api)
            if selected["source"] != grant["source_selection"]:
                raise ValueError("Granted CR source page changed")
            result["selected_source_page"] = selected["source"]
            result[
                "source_scope"
            ] += "; exact explicitly selected parsed table row/value page also authorized; bounded public inspection remains included; other complete source pages not automatically exposed"
        if len(json.dumps(result, ensure_ascii=False).encode()) > 100000:
            raise ValueError(
                "Complete CR model context exceeds this route; use the maintained specialist workflow"
            )
        return result
    if action not in {"inspect", "grant", "stage", "calculate", "finalize"}:
        raise ValueError("Unknown CR action")
    if loaded["run"]["status"] != "running" or "REVIEWER" not in os.environ.get(
        "VERA_WORKSPACE_ROLES", ""
    ).split(","):
        raise PermissionError(
            "CR writes require a running owned run and reviewer authority"
        )
    key = args["idempotency_key"]
    if not re.fullmatch(r"[A-Za-z0-9_-]{1,120}", key):
        raise ValueError("Invalid CR request key")
    fingerprint = api.digest([tool, current["owner"], args])
    with api.write_lock(current["output"]):
        current = context(binding, api.load_binding(binding), root, api)
        private = api.ui_state_directory(current["output"])
        receipt = private / (
            "cr-request-" + api.digest([current["owner"], key]) + ".json"
        )
        if receipt.exists():
            saved = api.read_json(receipt)
            if saved["request_sha256"] != fingerprint or "result" not in saved:
                raise ValueError(
                    "Different or interrupted CR request; specialist recovery required"
                )
            return saved["result"]
        if current["recovery_required"]:
            raise ValueError("CR outputs or interrupted writes require recovery")
        if action != "stage" and args["revision"] != current["revision"]:
            raise ValueError("Stale CR scope; reload the exact selection")
        if action != "stage" and args.get("confirmed") is not True:
            raise ValueError("Explicit CR selection confirmation is required")
        parent = (
            None
            if action == "inspect"
            else version(
                current,
                args.get("source_ref")
                or grant_record(current, args, api)["source_ref"],
            )
        )
        directory = current["output"] / ("cr-" + fingerprint)
        if action == "inspect":
            paths = selected_inputs(loaded, args["input_ids"])
            request = {
                "operation": "inspect",
                "inputs": paths,
                "output": str(directory),
                "context": str(loaded["context_path"]),
            }
            phase = "inspection"
        elif action == "grant":
            if (
                parent["phase"] not in {"inspection", "analysis"}
                or parent["status"] == "blocked"
            ):
                raise ValueError(
                    "CR grant requires an inspection or unblocked analysis"
                )
            question = args["question"]
            if (
                not isinstance(question, str)
                or not question.strip()
                or len(question) > 4000
            ):
                raise ValueError("A literal CR question is required")
            grant = {
                "grant_ref": "cr-grant-" + fingerprint,
                "owner": current["owner"],
                "source_ref": parent["source_ref"],
                "question": question,
                "kind": "recipe" if parent["phase"] == "inspection" else "commentary",
                "implementation": current["implementation"],
                "inputs": loaded["input_manifest"],
            }
            if args.get("source_selector") is not None:
                selected = read_source(current, loaded, root, args, api)
                if (
                    args.get("item_id") != selected["selection"]["id"]
                    or selected["source"]["page"]["kind"] == "tables"
                ):
                    raise ValueError(
                        "CR question requires the exact selected source page"
                    )
                # Authorization retains exact bytes/coordinates; it does not prove reading.
                grant["source_selector"] = selected["source"]["source_selector"]
                grant["source_selection"] = selected["source"]
            elif args.get("item_id"):
                raise ValueError("A CR source page ticket requires its exact selector")
            api.atomic_json(receipt, {"request_sha256": fingerprint})
            api.atomic_json(private / (grant["grant_ref"] + ".json"), grant)
            return retain_result(
                api,
                receipt,
                fingerprint,
                {
                    "saved": True,
                    "status": "model_grant_retained",
                    "grant_ref": grant["grant_ref"],
                    "kind": grant["kind"],
                    "source_ref": parent["source_ref"],
                },
            )
        elif action == "stage":
            grant = grant_record(current, args, api)
            if args["expected_proposal_revision"] != proposal_revision(
                current, grant, api
            ):
                raise ValueError("Stale CR proposal revision")
            proposal = args["proposal"]
            validate_proposal(current, grant, proposal, root, api)
            api.atomic_json(receipt, {"request_sha256": fingerprint})
            api.atomic_json(
                private
                / (grant["grant_ref"] + "-proposal-" + api.digest(proposal) + ".json"),
                proposal,
            )
            api.atomic_json(
                private / (grant["grant_ref"] + "-proposal.json"),
                {
                    "owner": current["owner"],
                    "grant_sha256": api.digest(grant),
                    "proposal": proposal,
                },
            )
            return retain_result(
                api,
                receipt,
                fingerprint,
                {
                    "saved": True,
                    "status": "proposal_pending_review",
                    "proposal_sha256": api.digest(proposal),
                    "professional_approval": False,
                },
            )
        else:
            grant = grant_record(current, args, api)
            if (action, grant["kind"]) not in {
                ("calculate", "recipe"),
                ("finalize", "commentary"),
            } or grant["source_ref"] != parent["source_ref"]:
                raise ValueError("CR grant and selected phase differ")
            _, proposal = read_proposal(current, grant, {}, root, api)
            if args["proposal_sha256"] != api.digest(proposal):
                raise ValueError("Selected CR proposal changed")
            validate_proposal(current, grant, proposal, root, api)
            if action == "calculate":
                if (
                    not isinstance(args["reviewer"], str)
                    or not args["reviewer"].strip()
                    or not args["reviewed_at"].strip()
                ):
                    raise ValueError("A named timestamped mapping review is required")
                reviewed_at = datetime.fromisoformat(args["reviewed_at"])
                if reviewed_at.tzinfo is None:
                    raise ValueError(
                        "CR mapping review requires an ISO 8601 timestamp with timezone"
                    )
                proposal = {
                    **proposal,
                    "mapping_review": {
                        "status": "reviewed",
                        "reviewer": args["reviewer"],
                        "reviewed_at": args["reviewed_at"],
                    },
                }
                paths = selected_inputs(loaded, parent["input_ids"])
                engine_call(
                    root,
                    {
                        "operation": "validate_recipe",
                        "inputs": paths,
                        "recipe": str(
                            current["output"]
                            / parent["source_ref"]
                            / "suggested_recipe.json"
                        ),
                        "proposal": proposal,
                    },
                )
                request = {
                    "operation": "calculate",
                    "inputs": paths,
                    "recipe": str(directory / "reviewed_recipe.json"),
                    "output": str(directory),
                    "context": str(loaded["context_path"]),
                }
                phase = "analysis"
            else:
                request = {
                    "operation": "finalize",
                    "analysis": str(
                        current["output"]
                        / parent["source_ref"]
                        / "centrale_rischi_analysis.json"
                    ),
                    "commentary": str(directory / "commentary.json"),
                    "output": str(directory),
                    "context": str(loaded["context_path"]),
                }
                phase = "report"
        # Public writes must have durable intent before creating any output.
        api.atomic_json(receipt, {"request_sha256": fingerprint})
        directory.mkdir()
        if action == "calculate":
            source = current["output"] / parent["source_ref"]
            for name in (
                "centrale_rischi_normalized.xlsx",
                "pdf_normalization_receipt.json",
            ):
                if name in parent["artifacts"]:
                    shutil.copyfile(source / name, directory / name)
            api.atomic_json(directory / "reviewed_recipe.json", proposal)
        elif action == "finalize":
            api.atomic_json(directory / "commentary.json", proposal)
        response = engine_call(root, request)
        refreshed = api.load_binding(binding)
        if (
            refreshed["input_manifest"] != loaded["input_manifest"]
            or engine_call(root, {"operation": "implementation"})
            != current["implementation"]["producer"]
        ):
            raise ValueError("CR source or implementation changed during execution")
        produced = api.read_json(directory / PHASE_FILES[phase])
        status = produced.get("status", "mapping_pending_review")
        record = {
            "source_ref": directory.name,
            "phase": phase,
            "status": status,
            "parent": parent["source_ref"] if parent else None,
            "input_ids": (
                args["input_ids"] if action == "inspect" else parent["input_ids"]
            ),
            "inputs": loaded["input_manifest"],
            "owner": current["owner"],
            "implementation": current["implementation"],
            "artifacts": tree_hash(directory),
        }
        current["state"]["versions"].append(record)
        api.atomic_json(private / "cr-state.json", current["state"])
        return retain_result(
            api,
            receipt,
            fingerprint,
            {
                "saved": True,
                "status": status,
                "source_ref": directory.name,
                "exit_status": response["exit_status"],
                "professional_approval": False,
                "run_completed": False,
            },
        )


def retain_result(api: Any, receipt: Path, fingerprint: str, result: dict) -> dict:
    """One exact request key retains its result; changed keys cannot overwrite revisions."""
    api.atomic_json(receipt, {"request_sha256": fingerprint, "result": result})
    return result


def grant_record(current: dict, args: dict, api: Any) -> dict:
    """No model context exists without an exact signed UI grant."""
    reference = args["grant_ref"]
    if not re.fullmatch(r"cr-grant-[0-9a-f]{64}", reference):
        raise ValueError("Invalid CR model grant")
    grant = api.read_json(current["private"] / (reference + ".json"))
    if (
        grant["owner"] != current["owner"]
        or grant["implementation"] != current["implementation"]
    ):
        raise PermissionError(
            "CR model grant belongs to another owner or implementation"
        )
    version(current, grant["source_ref"])
    return grant


def proposal_revision(current: dict, grant: dict, api: Any) -> str:
    """CAS covers the complete proposal, not just a truncated preview."""
    path = current["private"] / (grant["grant_ref"] + "-proposal.json")
    return api.digest(api.read_json(path)) if path.exists() else ""


def read_proposal(
    current: dict, grant: dict, args: dict, root: Path, api: Any
) -> tuple[dict, dict]:
    """Reopen exact grant-local history bytes; never infer chronological order."""
    candidate = api.read_json(
        current["private"] / (grant["grant_ref"] + "-proposal.json")
    )
    if candidate["owner"] != current["owner"] or candidate[
        "grant_sha256"
    ] != api.digest(grant):
        raise ValueError("CR proposal belongs to another grant")
    current_sha = api.digest(candidate["proposal"])
    prefix = grant["grant_ref"] + "-proposal-"
    current_proposal = api.read_json(
        current["private"] / (prefix + current_sha + ".json")
    )
    if (
        api.digest(current_proposal) != current_sha
        or current_proposal != candidate["proposal"]
    ):
        raise ValueError("Current CR proposal history bytes changed")
    sha = args.get("proposal_sha256", current_sha)
    if not isinstance(sha, str) or not re.fullmatch(r"[0-9a-f]{64}", sha):
        raise ValueError("Choose an exact retained CR proposal hash")
    selected = (
        current_proposal
        if sha == current_sha
        else api.read_json(current["private"] / (prefix + sha + ".json"))
    )
    if api.digest(selected) != sha:
        raise ValueError("CR proposal history bytes changed")
    validate_proposal(current, grant, selected, root, api)
    if sha != current_sha:
        validate_proposal(current, grant, current_proposal, root, api)
    return candidate, selected


def validate_proposal(
    current: dict, grant: dict, proposal: dict, root: Path, api: Any
) -> None:
    """Mechanical contract closure never fills semantic mappings or approves content."""
    if not isinstance(proposal, dict):
        raise ValueError("CR proposal must be complete JSON")
    directory = current["output"] / grant["source_ref"]
    if grant["kind"] == "recipe":
        template = api.read_json(directory / "suggested_recipe.json")
        if set(proposal) != set(template) or any(
            proposal[k] != template[k]
            for k in (
                "schema_version",
                "workflow_id",
                "inventory_sha256",
                "source_kind",
                "source_document_sha256",
                "mapping_review",
            )
        ):
            raise ValueError(
                "CR model proposal changed provenance or manufactured mapping approval"
            )
    else:
        analysis = directory / "centrale_rischi_analysis.json"
        if proposal.get("analysis_sha256") != file_hash(analysis):
            raise ValueError("CR commentary belongs to another analysis")
        engine_call(
            root,
            {
                "operation": "validate_commentary",
                "analysis": str(analysis),
                "proposal": proposal,
            },
        )
