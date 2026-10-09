"""Explicit source mandates and model-authored immutable reviews over public services.

Exact producer IDs, source hashes and request receipts enforce authorization and
reproducible conservation. Scope, relevance and adequacy remain model judgments.
"""

from __future__ import annotations

import json
import os
import re
import secrets
import tempfile
from pathlib import Path
from typing import Any

from native_assetti import profile
from native_bank_preparation import file_hash, tree_hash

__all__ = ["audit_run", "dispatch"]


def record_reference(workflow: str, record: dict) -> str:
    """Map only fixed public producer schemas, never infer document meaning."""
    if workflow == "scissione-guidata":
        return record["revision_sha256"]
    if workflow == "invoice-xml":
        return record["proposal_sha256"]
    return profile(Path(workflow))["prefix"] + "-" + record["record_sha256"]


def artifact_names(
    workflow: str, reference: str, record: dict | None = None
) -> set[str]:
    """Close each fixed producer's actual conserved artifact inventory."""
    if workflow == "scissione-guidata":
        from native_scissione_authoring import artifact_names as names

        return names(reference)
    if workflow == "invoice-xml":
        from native_invoice_authoring import artifact_names as invoice_names

        if record is None:
            raise ValueError(
                "Invoice conservation requires its complete prepared record"
            )
        return invoice_names(record)
    return {reference + ".json", reference + ".md"}


def proposed_payload(workflow: str, record: dict) -> dict:
    """Select only fixed producer payload keys, without semantic classification."""
    return record[
        (
            "case"
            if workflow == "scissione-guidata"
            else "proposal" if workflow == "invoice-xml" else "review"
        )
    ]


def owner(binding: dict) -> list:
    """Fixed ownership is an authorization boundary, never an AML judgment."""
    return [
        os.environ["VERA_WORKSPACE_ACTOR_ID"],
        os.environ["VERA_WORKSPACE_TENANT_ID"],
        binding["client_id"],
        binding["engagement_id"],
        binding["run_id"],
    ]


def home(binding: dict, loaded: dict, api: Any) -> Path:
    return api.ui_state_directory(Path(loaded["output_dir"]), create=False) / (
        profile(Path(binding["workflow_id"]))["private_prefix"]
        + "-authoring-"
        + api.digest(owner(binding))
    )


def audit_run(output: Path, api: Any, workflow: str = "aml-review") -> dict:
    """Detect missing/changed/unreceipted work, including another actor's interrupted write."""
    snapshots = {}
    recovery = False
    contract = profile(Path(workflow))
    record_pattern = (
        r"[0-9a-f]{64}"
        if workflow in {"scissione-guidata", "invoice-xml"}
        else re.escape(contract["prefix"]) + r"-[0-9a-f]{64}"
    )
    for directory in api.ui_state_directory(output, create=False).glob(
        contract["private_prefix"] + "-authoring-*"
    ):
        if directory.is_symlink() or not directory.is_dir():
            raise ValueError("Invalid AML authoring directory")
        known = set()
        requests = [api.read_json(p) for p in directory.glob("request-*.json")]
        recovery |= any("result" not in request for request in requests)
        for request in requests:
            if "result" not in request:
                continue
            ref = request["result"]["grant_ref"]
            if not re.fullmatch(r"mandate-[0-9a-f]{64}", ref) or ref in known:
                raise ValueError("Invalid AML mandate receipt")
            known.add(ref)
            base = directory / ref
            if file_hash(base / "mandate.json") != request["mandate_sha256"]:
                raise ValueError("AML mandate changed")
            state_path = base / "state.json"
            state = api.read_json(state_path) if state_path.exists() else {"stages": []}
            if workflow == "invoice-xml":
                from native_invoice_authoring import audit_evidence

                recovery |= audit_evidence(base, state, api)
            staged = set()
            stage_requests = [
                api.read_json(p) for p in base.glob("stage-request-*.json")
            ]
            publish_requests = [
                api.read_json(p) for p in base.glob("publish-request-*.json")
            ]
            recovery |= any(
                "result" not in r for r in [*stage_requests, *publish_requests]
            )
            for row in state["stages"]:
                reference = row["stage_ref"]
                if (
                    not re.fullmatch(r"proposal-[0-9a-f]{64}", reference)
                    or reference in staged
                ):
                    raise ValueError("Invalid AML proposal identity")
                staged.add(reference)
                if tree_hash(base / reference) != row["artifacts"]:
                    raise ValueError("AML staged proposal changed")
                record = api.read_json(base / reference / "record.json")
                if (
                    not re.fullmatch(record_pattern, row["source_ref"])
                    or row["source_ref"] != record_reference(workflow, record)
                    or (
                        workflow not in {"scissione-guidata", "invoice-xml"}
                        and record["workflow_id"] != workflow
                    )
                    or row["status"] != record["status"]
                    or proposed_payload(workflow, record)
                    != (
                        api.read_json(base / reference / "review.json")["case"]
                        if workflow == "scissione-guidata"
                        else (
                            api.read_json(base / reference / "review.json")["proposal"]
                            if workflow == "invoice-xml"
                            else api.read_json(base / reference / "review.json")
                        )
                    )
                ):
                    raise ValueError("AML proposal receipt differs from its record")
                recovery |= not any(
                    r.get("result", {}).get("stage_ref") == reference
                    for r in stage_requests
                )
            recovery |= any(p.name not in staged for p in base.glob("proposal-*"))
            recovery |= any(
                r.get("result", {}).get("stage_ref") not in staged
                for r in stage_requests
                if "result" in r
            )
            publications = state.get("publications", [])
            names = {row["request_ref"] for row in publications}
            for row in publications:
                if not re.fullmatch(record_pattern, row["result"]["source_ref"]):
                    raise ValueError("Invalid conserved AML record identity")
                receipt_path = base / row["request_ref"]
                if not re.fullmatch(
                    r"publish-request-[0-9a-f]{64}\.json", row["request_ref"]
                ):
                    raise ValueError("Invalid AML publication receipt")
                receipt = api.read_json(receipt_path) if receipt_path.exists() else {}
                recovery |= (
                    receipt.get("result") != row["result"]
                    or receipt.get("artifacts") != row["artifacts"]
                )
                retained = next(
                    (
                        stage
                        for stage in state["stages"]
                        if stage["source_ref"] == row["result"]["source_ref"]
                    ),
                    None,
                )
                if retained is None:
                    raise ValueError("Conserved proposal lacks its retained stage")
                conserved = api.read_json(base / retained["stage_ref"] / "record.json")
                expected_artifacts = artifact_names(
                    workflow, row["result"]["source_ref"], conserved
                )
                if set(row["artifacts"]) != expected_artifacts:
                    raise ValueError("Conserved proposal artifact inventory changed")
                for filename, checksum in row["artifacts"].items():
                    if (
                        filename not in expected_artifacts
                        or file_hash(output / filename) != checksum
                    ):
                        raise ValueError("Conserved AML proposal changed")
            recovery |= any(
                p.name not in names for p in base.glob("publish-request-*.json")
            )
            snapshots[ref] = [request["mandate_sha256"], state]
        recovery |= any(p.name not in known for p in directory.glob("mandate-*"))
    return {"mandates": snapshots, "recovery_required": recovery}


def snapshot(binding: dict, loaded: dict, root: Path, api: Any) -> dict:
    from native_aml import catalogue, engine_call

    if root.name == "scissione-guidata":
        from native_scissione_authoring import catalogue, engine_call
    elif root.name == "invoice-xml":
        from native_invoice import catalogue
        from native_invoice import engine as engine_call

    contract = profile(root)
    if binding["workflow_id"] != contract["workflow"]:
        raise PermissionError("Authoring belongs to this exact producer run")
    rows = []
    for row in loaded["input_manifest"]["inputs"]:
        path = Path(loaded["run_root"]) / row["execution_relative_path"]
        if file_hash(path) != row["sha256"]:
            raise ValueError("Registered AML source changed")
        rows.append(
            {
                **row,
                "path": str(path),
                "relative_path": Path(row["execution_relative_path"])
                .relative_to("inputs")
                .as_posix(),
            }
        )
    identity = {
        "owner": owner(binding),
        "run": {
            key: loaded["run"][key]
            for key in ("client_id", "engagement_id", "run_id", "workflow_id")
        },
        "inputs": loaded["input_manifest"],
        "implementation": [
            engine_call(root, {"operation": "implementation"}),
            file_hash(Path(__file__)),
            file_hash(Path(__file__).with_name("native_aml_bridge.py")),
            file_hash(Path(__file__).with_name("native_aml.py")),
            file_hash(Path(__file__).with_name("native_assetti.py")),
        ],
    }
    producer = catalogue(root, binding, loaded, api)
    if root.name == "scissione-guidata":
        identity["case_scope"] = producer["case_scope"]
        identity["implementation"].extend(
            file_hash(Path(__file__).with_name(name))
            for name in (
                "native_scissione.py",
                "native_scissione_authoring.py",
                "native_scissione_bridge.py",
            )
        )
    elif root.name == "invoice-xml":
        identity["implementation"].extend(
            file_hash(Path(__file__).with_name(name))
            for name in (
                "native_invoice.py",
                "native_invoice_bridge.py",
                "native_invoice_authoring.py",
            )
        )
    audit = audit_run(Path(loaded["output_dir"]), api, root.name)
    return {
        "identity": identity,
        "sources": rows,
        "audit": audit,
        "revision": api.digest([identity, producer["checkpoint"], audit]),
        "can_write": loaded["run"]["status"] == "running"
        and "REVIEWER" in os.environ.get("VERA_WORKSPACE_ROLES", "").split(",")
        and not audit["recovery_required"],
    }


def draft_read(directory: Path, api: Any) -> dict:
    path = directory / "draft.json"
    return {
        "draft_revision": file_hash(path) if path.exists() else "",
        "fields": (
            api.read_json(path)["fields"]
            if path.exists()
            else {"question": "", "input_ids": []}
        ),
    }


def fields(value: Any, current: dict, *, complete: bool) -> dict:
    """Validate literal shape and exact receipt choices, without interpreting their content."""
    if not isinstance(value, dict) or set(value) != {"question", "input_ids"}:
        raise ValueError("Choose a literal question and exact input IDs")
    question, ids = value["question"], value["input_ids"]
    if (
        not isinstance(question, str)
        or len(question) > 4000
        or complete
        and not question.strip()
    ):
        raise ValueError("State the actual AML review question")
    if (
        not isinstance(ids, list)
        or len(ids) > 1000
        or any(not isinstance(x, str) for x in ids)
        or len(set(ids)) != len(ids)
        or complete
        and not ids
    ):
        raise ValueError("Choose distinct actual AML sources")
    available = {r["binding_id"] for r in current["sources"]}
    if not set(ids) <= available:
        raise PermissionError("AML source is outside this run")
    return value


def grant(directory: Path, args: dict, current: dict, api: Any) -> tuple[Path, dict]:
    reference = args["grant_ref"]
    if not re.fullmatch(r"mandate-[0-9a-f]{64}", reference):
        raise ValueError("Choose an exact user-authorized AML mandate")
    base = directory / reference
    value = api.read_json(base / "mandate.json")
    if not re.fullmatch(r"request-[0-9a-f]{64}\.json", value["request_ref"]):
        raise ValueError("Invalid AML mandate request receipt")
    receipt = api.read_json(directory / value["request_ref"])
    if receipt.get("result", {}).get("grant_ref") != reference or receipt.get(
        "mandate_sha256"
    ) != file_hash(base / "mandate.json"):
        raise ValueError("AML mandate requires recovery")
    matches = value["identity"] == current["identity"]
    if not matches and current["identity"]["run"]["workflow_id"] == "scissione-guidata":
        from native_scissione_authoring import published_scope_matches

        matches = published_scope_matches(base, value, current, api)
    if not matches:
        raise PermissionError(
            "AML mandate owner, inputs, run or implementation changed"
        )
    fields(value["fields"], current, complete=True)
    selected = [
        r for r in current["sources"] if r["binding_id"] in value["fields"]["input_ids"]
    ]
    if selected != value["sources"]:
        raise ValueError("Selected AML source receipts changed")
    return base, value


def inspect(
    review: dict,
    value: dict,
    loaded: dict,
    root: Path,
    base: Path,
    api: Any,
    *,
    save: bool = False,
) -> dict:
    if root.name == "scissione-guidata":
        from native_scissione_authoring import inspect as inspect_case

        return inspect_case(review, value, loaded, root, base, api, save=save)
    if root.name == "invoice-xml":
        from native_invoice_authoring import inspect as inspect_invoice

        return inspect_invoice(review, value, loaded, root, base, api, save=save)

    from native_aml import engine_call

    if not isinstance(review, dict) or review.get("professional_decision") is not None:
        raise ValueError(
            "The model may propose an AML review, not a professional decision"
        )
    if root.name == "adeguati-assetti" and not isinstance(
        review.get("intelligent_review"), dict
    ):
        # The current public record contract requires this section for new
        # assessments; historical records remain readable through their own API.
        raise ValueError(
            "New assetti proposals require the current intelligent_review contract"
        )
    indexed = {row["relative_path"]: row for row in value["sources"]}
    declared = review.get("sources", [])
    if (
        not isinstance(declared, list)
        or len(declared) != len(indexed)
        or {row["path"] for row in declared} != set(indexed)
        or any(row["sha256"] != indexed[row["path"]]["sha256"] for row in declared)
    ):
        raise ValueError("Retain every explicitly chosen source with its exact bytes")
    if review.get("previous"):
        previous = next(
            row for row in declared if row["id"] == review["previous"]["source_id"]
        )
        receipt = indexed[previous["path"]]
        if (
            receipt["kind"] != "upstream_artifact"
            or receipt["upstream_workflow_id"] != root.name
        ):
            raise PermissionError(
                "Choose a sealed AML predecessor through Archive in a fresh run"
            )
    with tempfile.TemporaryDirectory(prefix="inspect-", dir=base) as temporary:
        path = Path(temporary) / "review.json"
        api.atomic_json(path, review)
        return engine_call(
            root,
            {
                "operation": "save_proposal" if save else "inspect_proposal",
                "review": str(path),
                "inputs": str(Path(loaded["run_root"]) / "inputs"),
                "client_id": value["identity"]["owner"][2],
                "engagement_id": value["identity"]["owner"][3],
                "output": loaded["output_dir"],
            },
        )


def dispatch(
    tool: str, args: dict, binding: dict, loaded: dict, root: Path, api: Any
) -> dict:
    """Retain literal intake, grant model authoring, stage and explicitly conserve a proposal."""
    from native_aml import bounded

    contract = profile(root)
    if not tool.startswith(contract["tool_prefix"] + "author_"):
        raise PermissionError("Authoring tool belongs to another producer")
    tool = tool.replace(contract["tool_prefix"], "vera_workspace_aml_", 1)
    current = snapshot(binding, loaded, root, api)
    directory = home(binding, loaded, api)
    if tool == "vera_workspace_aml_author_setup":
        start = args.get("offset", 0)
        if not isinstance(start, int) or isinstance(start, bool) or start < 0:
            raise ValueError("Invalid AML source offset")
        grants = []
        if directory.exists():
            for path in sorted(directory.glob("mandate-*/mandate.json")):
                value = api.read_json(path)
                grants.append(
                    {
                        "grant_ref": path.parent.name,
                        "question": value["fields"]["question"],
                    }
                )
        return bounded(
            {
                "work_ref": args["work_ref"],
                "workflow": root.name,
                "revision": current["revision"],
                "sources": [
                    {
                        key: row[key]
                        for key in ("binding_id", "relative_path", "sha256", "role")
                    }
                    for row in current["sources"][start : start + 30]
                ],
                "total": len(current["sources"]),
                "offset": start,
                "has_more": start + 30 < len(current["sources"]),
                "draft": draft_read(directory, api),
                "mandates": grants,
                "can_write": current["can_write"],
                "recovery_required": current["audit"]["recovery_required"],
            }
        )
    if tool == "vera_workspace_aml_author_context":
        base, value = grant(directory, args, current, api)
        state = (
            api.read_json(base / "state.json")
            if (base / "state.json").exists()
            else None
        )
        result = {
            "grant_ref": args["grant_ref"],
            "work_ref": args["work_ref"],
            "question": value["fields"]["question"],
            "sources": value["sources"],
            "stage_revision": api.digest(state) if state else "",
            "recovery_required": current["audit"]["recovery_required"],
            "workflow": root.name,
            "instructions": contract["authoring_instructions"],
        }
        if root.name == "scissione-guidata":
            result["case_scope"] = value["identity"]["case_scope"]
        elif root.name == "invoice-xml":
            from native_invoice_authoring import evidence_context

            result["prepared_evidence"] = evidence_context(base, state or {})
        if len(json.dumps(result).encode()) > 100000:
            raise ValueError(
                "Complete AML mandate exceeds model context limit; no sampling"
            )
        return result
    if tool == "vera_workspace_aml_author_read":
        base, value = grant(directory, args, current, api)
        state = (
            api.read_json(base / "state.json")
            if (base / "state.json").exists()
            else {"stages": []}
        )
        result = {
            "work_ref": args["work_ref"],
            "workflow": root.name,
            "revision": current["revision"],
            "question": value["fields"]["question"],
            "stages": [
                {key: row[key] for key in ("stage_ref", "source_ref", "status")}
                for row in state["stages"]
            ],
            "can_write": current["can_write"],
            "recovery_required": current["audit"]["recovery_required"],
        }
        if args.get("stage_ref"):
            row = next(
                (r for r in state["stages"] if r["stage_ref"] == args["stage_ref"]),
                None,
            )
            if row is None:
                raise ValueError("Select an exact retained AML proposal")
            staged = base / row["stage_ref"]
            replay = inspect(
                api.read_json(staged / "review.json"), value, loaded, root, base, api
            )
            if replay["record"] != api.read_json(staged / "record.json") or replay[
                "memo"
            ] != (staged / "memo.md").read_bytes().decode("utf-8"):
                raise ValueError("Staged AML proposal differs from public replay")
            result.update(
                selection={"id": row["stage_ref"]},
                record=replay["record"],
                memo=replay["memo"],
                selected_stage=row["stage_ref"],
            )
        return bounded(result)
    if not current["can_write"]:
        raise PermissionError(
            "AML authoring requires a running reviewer run without uncertain writes"
        )
    with api.write_lock(Path(loaded["output_dir"])):
        loaded = api.load_binding(binding)
        current = snapshot(binding, loaded, root, api)
        if not current["can_write"]:
            raise PermissionError("AML authoring authority changed")
        directory.mkdir(mode=0o700, exist_ok=True)
        if tool in {
            "vera_workspace_aml_author_draft_store",
            "vera_workspace_aml_author_draft_clear",
            "vera_workspace_aml_author_request",
        }:
            draft = draft_read(directory, api)
            if (
                tool != "vera_workspace_aml_author_request"
                and args["revision"] != current["revision"]
            ):
                raise ValueError("Reopen the exact AML intake")
            if (
                tool != "vera_workspace_aml_author_request"
                and args["expected_draft_revision"] != draft["draft_revision"]
            ):
                raise ValueError("Concurrent AML intake change")
            if tool == "vera_workspace_aml_author_draft_clear":
                (directory / "draft.json").unlink(missing_ok=True)
                return {"saved": True, "draft_revision": ""}
            chosen = fields(args["fields"], current, complete=tool.endswith("_request"))
            if tool == "vera_workspace_aml_author_draft_store":
                api.atomic_json(directory / "draft.json", {"fields": chosen})
                return {
                    "saved": True,
                    "draft_revision": file_hash(directory / "draft.json"),
                }
            if args.get("confirmed") is not True:
                raise ValueError("Explicit question and source authorization required")
            key = args["idempotency_key"]
            if not re.fullmatch(r"[A-Za-z0-9_-]{1,120}", key):
                raise ValueError("Invalid AML mandate request key")
            intent = directory / (
                "request-" + api.digest([owner(binding), key]) + ".json"
            )
            fingerprint = api.digest([tool, owner(binding), args])
            if intent.exists():
                saved = api.read_json(intent)
                if saved["request_sha256"] != fingerprint or "result" not in saved:
                    raise ValueError("AML mandate request changed or requires recovery")
                return saved["result"]
            if args["revision"] != current["revision"]:
                raise ValueError("Reopen the exact AML intake")
            if args["expected_draft_revision"] != draft["draft_revision"]:
                raise ValueError("Concurrent AML intake change")
            reference = "mandate-" + secrets.token_hex(32)
            base = directory / reference
            api.atomic_json(intent, {"request_sha256": fingerprint})
            base.mkdir(mode=0o700)
            value = {
                "identity": current["identity"],
                "fields": chosen,
                "sources": [
                    row
                    for row in current["sources"]
                    if row["binding_id"] in chosen["input_ids"]
                ],
                "request_ref": intent.name,
            }
            api.atomic_json(base / "mandate.json", value)
            if (
                snapshot(binding, api.load_binding(binding), root, api)["identity"]
                != current["identity"]
            ):
                raise ValueError("AML inputs changed; mandate requires recovery")
            result = {
                "saved": True,
                "grant_ref": reference,
                "professional_approval": False,
                "run_completed": False,
            }
            api.atomic_json(
                intent,
                {
                    "request_sha256": fingerprint,
                    "mandate_sha256": file_hash(base / "mandate.json"),
                    "result": result,
                },
            )
            return result
        base, value = grant(directory, args, current, api)
        state_path = base / "state.json"
        state = (
            api.read_json(state_path)
            if state_path.exists()
            else {"stages": [], "publications": []}
        )
        if tool not in {
            "vera_workspace_aml_author_stage",
            "vera_workspace_aml_author_publish",
        }:
            raise ValueError("Unknown AML authoring action")
        key = args["idempotency_key"]
        if not re.fullmatch(r"[A-Za-z0-9_-]{1,120}", key):
            raise ValueError("Invalid AML proposal request key")
        publishing = tool.endswith("_publish")
        intent = base / (
            ("publish-request-" if publishing else "stage-request-")
            + api.digest(key)
            + ".json"
        )
        fingerprint = api.digest([tool, owner(binding), args])
        if intent.exists():
            saved = api.read_json(intent)
            if saved["request_sha256"] != fingerprint or "result" not in saved:
                raise ValueError("AML proposal request changed or requires recovery")
            return saved["result"]
        if (
            root.name == "scissione-guidata"
            and current["identity"]["case_scope"] != value["identity"]["case_scope"]
        ):
            raise ValueError("Scissione case changed; create a fresh explicit mandate")
        if publishing:
            if (
                args["revision"] != current["revision"]
                or args.get("confirmed") is not True
                or args["item_id"] != args["stage_ref"]
            ):
                raise ValueError("Select and confirm the exact current AML proposal")
            row = next(
                (r for r in state["stages"] if r["stage_ref"] == args["stage_ref"]),
                None,
            )
            if row is None:
                raise ValueError("Choose an exact retained AML proposal")
            staged = base / row["stage_ref"]
            review = api.read_json(staged / "review.json")
            replay = inspect(review, value, loaded, root, base, api)
            if replay["record"] != api.read_json(staged / "record.json") or replay[
                "memo"
            ] != (staged / "memo.md").read_bytes().decode("utf-8"):
                raise ValueError("AML proposal differs from public replay")
            output = Path(loaded["output_dir"])
            already_conserved = (
                (output / ("draft-" + row["source_ref"])).exists()
                if root.name == "invoice-xml"
                else any(
                    (output / name).exists()
                    for name in artifact_names(
                        root.name, row["source_ref"], replay["record"]
                    )
                )
            )
            if already_conserved:
                raise ValueError(
                    "This proposal already exists; open its retained record instead"
                )
            api.atomic_json(intent, {"request_sha256": fingerprint})
            produced = inspect(review, value, loaded, root, base, api, save=True)
            if produced != replay:
                raise ValueError("AML producer differs from preview; recovery required")
            after_identity = snapshot(binding, api.load_binding(binding), root, api)[
                "identity"
            ]
            if root.name == "scissione-guidata":
                expected_path = (
                    output / "scissione_versions" / row["source_ref"] / "revision.json"
                )
                if after_identity["case_scope"] != {
                    "revision_sha256": row["source_ref"],
                    "path": str(expected_path),
                    "sha256": file_hash(expected_path),
                }:
                    raise ValueError(
                        "Scissione current pointer differs from conservation; recovery required"
                    )
                after_identity = {
                    **after_identity,
                    "case_scope": current["identity"]["case_scope"],
                }
            if after_identity != current["identity"]:
                raise ValueError(
                    "AML inputs changed during conservation; recovery required"
                )
            result = {
                "saved": True,
                "source_ref": row["source_ref"],
                "status": row["status"],
                "professional_approval": False,
                "run_completed": False,
            }
            artifacts = {
                name: file_hash(output / name)
                for name in artifact_names(
                    root.name, row["source_ref"], replay["record"]
                )
            }
            state["publications"].append(
                {"request_ref": intent.name, "result": result, "artifacts": artifacts}
            )
            api.atomic_json(state_path, state)
            api.atomic_json(
                intent,
                {
                    "request_sha256": fingerprint,
                    "result": result,
                    "artifacts": artifacts,
                },
            )
            return result
        stamp = api.digest(state) if state_path.exists() else ""
        if args["expected_stage_revision"] != stamp:
            raise ValueError("Concurrent AML proposal change; reread the exact mandate")
        replay = inspect(args["review"], value, loaded, root, base, api)
        reference = "proposal-" + api.digest([value, replay])
        staged = base / reference
        if staged.exists():
            raise ValueError("This exact proposal already exists; select its receipt")
        api.atomic_json(intent, {"request_sha256": fingerprint})
        staged.mkdir(mode=0o700)
        api.atomic_json(staged / "review.json", args["review"])
        api.atomic_json(staged / "record.json", replay["record"])
        (staged / "memo.md").write_text(replay["memo"], encoding="utf-8")
        if (
            snapshot(binding, api.load_binding(binding), root, api)["identity"]
            != current["identity"]
        ):
            raise ValueError("AML sources changed while staging; recovery required")
        row = {
            "stage_ref": reference,
            "source_ref": record_reference(root.name, replay["record"]),
            "status": replay["record"]["status"],
            "artifacts": tree_hash(staged),
        }
        state["stages"].append(row)
        api.atomic_json(state_path, state)
        result = {
            "saved": True,
            "stage_ref": reference,
            "stage_revision": api.digest(state),
            "status": row["status"],
            "professional_approval": False,
        }
        api.atomic_json(intent, {"request_sha256": fingerprint, "result": result})
        return result
