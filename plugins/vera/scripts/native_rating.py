"""Owned prepared Rating dossiers, complete previews and recoverable selections.

Fixed receipts, hashes and CAS enforce integrity and auditability. The unchanged
specialist producer retains legal judgment, prerequisites and history semantics.
"""

from __future__ import annotations

import base64
import json
import os
import re
import subprocess
import sys
from pathlib import Path, PurePosixPath
from typing import Any

from native_bank_preparation import file_hash, tree_hash
from native_sales_plan_authoring import owner_scope

__all__ = ["dispatch"]

PREFIX = "vera_workspace_rating_"
EMPTY = {"case_input_id": "", "previous_input_id": "", "note": ""}


def bounded(value: dict) -> dict:
    """Refuse oversized whole views; never truncate evidence or decisions."""
    if len(json.dumps(value, ensure_ascii=False, allow_nan=False).encode()) > 2_000_000:
        raise ValueError("Rating dossier exceeds the complete native view limit")
    return value


def fields(value: object) -> dict:
    """Literal unfinished selection is not a professional decision or consent."""
    if (
        not isinstance(value, dict)
        or set(value) != set(EMPTY)
        or any(not isinstance(v, str) for v in value.values())
        or any(len(value[k]) > (2000 if k == "note" else 200) for k in EMPTY)
    ):
        raise ValueError("Invalid Rating selection fields")
    return dict(value)


def implementation(root: Path) -> dict:
    """Bind public contracts and native implementation without package caches."""
    result = {}
    for name, suffixes in (
        ("scripts", {".py"}),
        ("schemas", {".json"}),
        ("references", {".json", ".md"}),
    ):
        result[name] = {
            n: h
            for n, h in tree_hash(root / name).items()
            if Path(n).suffix in suffixes
        }
    for vendor in (
        root / "vendor/modules",
        root.parent.parent / "vendor/modules",
        root.parent / "_shared/vendor/modules",
    ):
        if (vendor / "vera_assurance").is_dir():
            result["vera_assurance"] = {
                n: h
                for n, h in tree_hash(vendor / "vera_assurance").items()
                if Path(n).suffix == ".py"
            }
            break
    for path in (
        Path(__file__),
        Path(__file__).with_name("native_rating_bridge.py"),
        Path(__file__).parents[1] / "ui/rating.js",
    ):
        result[path.name] = file_hash(path)
    return result


def selected(identity: str, loaded: dict, api: Any, *, previous: bool = False) -> Path:
    """Choose only exact run receipts; predecessors must be sealed upstream output."""
    row = next(
        (r for r in loaded["input_manifest"]["inputs"] if r["binding_id"] == identity),
        None,
    )
    if row is None:
        raise PermissionError("Rating selection is outside the exact run receipts")
    path = Path(loaded["run_root"]) / row["execution_relative_path"]
    if path.suffix.lower() != ".json" or file_hash(path) != row["sha256"]:
        raise ValueError("Rating input differs from its registered JSON receipt")
    if previous and (
        row["kind"] != "upstream_artifact"
        or row["upstream_workflow_id"] != "rating-legalita"
        or path.name != "dossier.json"
    ):
        raise PermissionError(
            "Rating predecessor must be a sealed same-workflow dossier"
        )
    if not previous and row["kind"] != "import":
        raise PermissionError("Select the registered authored Rating case")
    return path


def request_for(selection: dict, loaded: dict, api: Any) -> dict:
    """Require every declared evidence file and any known continuation receipt."""
    path = selected(selection["case_input_id"], loaded, api)
    case = api.read_json(path)
    if case.get("schema_version") != "0.1" or "snapshots" not in case:
        raise ValueError("Select a Rating case conforming to the public schema")
    root = Path(loaded["run_root"])
    receipts = {
        (root / r["execution_relative_path"]).resolve(): r
        for r in loaded["input_manifest"]["inputs"]
    }
    for row in case["evidence"]:
        uri = row["uri"]
        relative = PurePosixPath(uri)
        if (
            not uri
            or "\\" in uri
            or relative.is_absolute()
            or relative.as_posix() != uri
            or ".." in relative.parts
        ):
            raise ValueError("Rating evidence locator must be canonical and relative")
        evidence = root / "inputs" / uri
        receipt = receipts.get(evidence.resolve())
        if receipt is None or receipt["sha256"] != row["sha256"]:
            raise PermissionError("Rating evidence is outside the exact run receipts")
        if file_hash(evidence) != row["sha256"]:
            raise ValueError("Rating evidence bytes changed")
    predecessors = [
        r
        for r in loaded["input_manifest"]["inputs"]
        if r["kind"] == "upstream_artifact"
        and r["upstream_workflow_id"] == "rating-legalita"
        and Path(r["execution_relative_path"]).name == "dossier.json"
    ]
    if predecessors and not selection["previous_input_id"]:
        raise ValueError("Select the registered prior dossier on continuation")
    previous = (
        selected(selection["previous_input_id"], loaded, api, previous=True)
        if selection["previous_input_id"]
        else None
    )
    return {
        "operation": "inspect",
        "case": str(path),
        "previous": str(previous) if previous else None,
        "context": str(loaded["context_path"]),
    }


def engine_call(root: Path, request: dict) -> dict:
    """No model or network call; producer errors stay out of model-visible logs."""
    result = subprocess.run(
        [
            sys.executable,
            "-I",
            "-B",
            str(Path(__file__).with_name("native_rating_bridge.py")),
            str(root),
        ],
        input=json.dumps(request, ensure_ascii=False, allow_nan=False),
        text=True,
        capture_output=True,
        timeout=90,
        check=False,
    )
    if result.returncode:
        raise ValueError(
            "Rating producer refused validation; inspect the case in the specialist workflow"
        )
    return bounded(json.loads(result.stdout))


def current(binding: dict, loaded: dict, root: Path, api: Any) -> dict:
    """Scope includes the whole run, declared inputs, artifacts and implementation."""
    if binding["workflow_id"] != "rating-legalita":
        raise PermissionError("Rating belongs to another workflow")
    output = Path(loaded["output_dir"])
    private = api.ui_state_directory(output, create=False)
    artifacts = tree_hash(output)
    contract = implementation(root)
    revision = api.digest(
        [loaded["run"], loaded["input_manifest"], artifacts, contract]
    )
    receipts = [api.read_json(p) for p in sorted(private.glob("rating-request-*.json"))]
    for receipt in receipts:
        if receipt.get("content_sha256") != api.digest(
            {k: v for k, v in receipt.items() if k != "content_sha256"}
        ):
            raise ValueError("Rating intent receipt hash changed")
        if "result" in receipt and (
            receipt["implementation"] != contract
            or receipt["artifacts"] != artifacts
            or receipt["owner_scope"] != owner_scope(binding)
        ):
            raise ValueError("Rating completed receipt or artifacts changed")
    return {
        "output": output,
        "private": private,
        "artifacts": artifacts,
        "implementation": contract,
        "revision": revision,
        "source_ref": api.digest([owner_scope(binding), revision]),
        "pending": [r["request_sha256"] for r in receipts if "result" not in r],
    }


def draft_path(context: dict, binding: dict, api: Any) -> Path:
    return context["private"] / (
        "rating-draft-" + api.digest(owner_scope(binding)) + ".json"
    )


def draft(context: dict, binding: dict, api: Any) -> dict:
    path = draft_path(context, binding, api)
    if not path.exists():
        return {
            "fields": dict(EMPTY),
            "draft_revision": api.digest([owner_scope(binding), "empty_rating_draft"]),
            "draft_stale": False,
        }
    value = api.read_json(path)
    if value["owner_scope"] != owner_scope(binding):
        raise PermissionError("Rating private draft belongs to another owner")
    return {
        "fields": fields(value["fields"]),
        "draft_revision": file_hash(path),
        "draft_stale": value["revision"] != context["revision"],
    }


def exact(args: dict, context: dict) -> None:
    if (
        args["revision"] != context["revision"]
        or args["source_ref"] != context["source_ref"]
    ):
        raise ValueError("Stale Rating scope; reopen the run")


def seal(path: Path, value: dict, api: Any) -> None:
    """A self-hash detects accidental receipt alteration, not signer authenticity."""
    api.atomic_json(path, {**value, "content_sha256": api.digest(value)})


def preview(
    selection: dict, binding: dict, loaded: dict, root: Path, context: dict, api: Any
) -> dict:
    value = engine_call(root, request_for(selection, loaded, api))
    value["preview_ref"] = api.digest(
        [owner_scope(binding), context["revision"], selection, value]
    )
    return value


def dispatch(
    tool: str, args: dict, binding: dict, loaded: dict, root: Path, api: Any
) -> dict:
    """Expose prepared dossiers privately and invoke only unchanged public render."""
    context = current(binding, loaded, root, api)
    writable = (
        "REVIEWER" in os.environ.get("VERA_WORKSPACE_ROLES", "").split(",")
        and loaded["run"]["status"] == "running"
    )
    action = tool.removeprefix(PREFIX)
    if action == "setup":
        return bounded(
            {
                "work_ref": binding["work_ref"],
                "revision": context["revision"],
                "source_ref": context["source_ref"],
                "data": {"selection": {"source_ref": context["source_ref"]}},
                "can_write": writable,
                "can_render": writable
                and not context["pending"]
                and not context["artifacts"],
                "pending_operations": context["pending"],
                "status": loaded["run"]["status"],
                "items": [
                    {
                        "id": r["binding_id"],
                        "name": Path(r["execution_relative_path"]).name,
                    }
                    for r in loaded["input_manifest"]["inputs"]
                    if r["kind"] == "import"
                    and Path(r["execution_relative_path"]).suffix.lower() == ".json"
                ],
                "predecessors": [
                    {
                        "id": r["binding_id"],
                        "name": r["upstream_run_id"] + " · dossier.json",
                    }
                    for r in loaded["input_manifest"]["inputs"]
                    if r["kind"] == "upstream_artifact"
                    and r["upstream_workflow_id"] == "rating-legalita"
                    and Path(r["execution_relative_path"]).name == "dossier.json"
                ],
                "artifacts": [
                    {"name": n, "sha256": h} for n, h in context["artifacts"].items()
                ],
                **draft(context, binding, api),
                "run_completed": False,
                "submission_authorized": False,
            }
        )
    if action in {"draft_save", "draft_clear", "execute"}:
        if not writable:
            raise PermissionError(
                "Rating writes require a running run and reviewer role"
            )
        with api.write_lock(context["output"]):
            loaded = api.load_binding(binding)
            context = current(binding, loaded, root, api)
            if loaded["run"]["status"] != "running":
                raise PermissionError("Rating run is no longer running")
            if action == "execute":
                key = args["idempotency_key"]
                if not re.fullmatch(r"[A-Za-z0-9_-]{1,120}", key):
                    raise ValueError("Invalid Rating request key")
                intent = context["private"] / (
                    "rating-request-"
                    + api.digest([owner_scope(binding), key])
                    + ".json"
                )
                fingerprint = api.digest([owner_scope(binding), tool, args])
                if intent.exists():
                    retained = api.read_json(intent)
                    if retained["request_sha256"] != fingerprint:
                        raise ValueError(
                            "Rating request key belongs to different fields"
                        )
                    if "result" not in retained:
                        raise ValueError(
                            "Rating write is uncertain; specialist recovery required"
                        )
                    engine_call(
                        root,
                        {
                            **request_for(fields(args["fields"]), loaded, api),
                            "operation": "replay",
                        },
                    )
                    return retained["result"]
            exact(args, context)
            saved = draft(context, binding, api)
            if args["expected_draft_revision"] != saved["draft_revision"]:
                raise ValueError("Rating draft changed; reopen before writing")
            if action == "draft_clear":
                if args["confirmed"] is not True:
                    raise ValueError("Confirm discarding only private Rating fields")
                draft_path(context, binding, api).unlink(missing_ok=True)
                return {
                    "saved": True,
                    "draft_revision": api.digest(
                        [owner_scope(binding), "empty_rating_draft"]
                    ),
                    "fields": dict(EMPTY),
                }
            selection = fields(args["fields"])
            if saved["draft_stale"]:
                raise ValueError("Compare and discard stale Rating fields first")
            if action == "draft_save":
                api.atomic_json(
                    draft_path(context, binding, api),
                    {
                        "owner_scope": owner_scope(binding),
                        "revision": context["revision"],
                        "fields": selection,
                    },
                )
                return {
                    "saved": True,
                    "draft_revision": file_hash(draft_path(context, binding, api)),
                    "fields": selection,
                }
            if context["pending"] or context["artifacts"]:
                raise ValueError(
                    "Rating needs recovery or a fresh registered continuation run"
                )
            if args["confirmed"] is not True or selection != saved["fields"]:
                raise ValueError("Save and confirm the exact current Rating selection")
            value = preview(selection, binding, loaded, root, context, api)
            if args["preview_ref"] != value["preview_ref"]:
                raise ValueError(
                    "Review the whole current Rating preview before rendering"
                )
            if (
                current(binding, api.load_binding(binding), root, api)["revision"]
                != context["revision"]
            ):
                raise ValueError("Rating scope changed before render")
            seal(
                intent,
                {"request_sha256": fingerprint, "owner_scope": owner_scope(binding)},
                api,
            )
            rendered = engine_call(
                root, {**request_for(selection, loaded, api), "operation": "render"}
            )
            after_loaded = api.load_binding(binding)
            after = current(binding, after_loaded, root, api)
            expected_names = {
                rendered["record"]["record_sha256"] + "/" + name
                for name in ("dossier.json", "dossier.md")
            }
            if (
                after["implementation"] != context["implementation"]
                or rendered != {k: v for k, v in value.items() if k != "preview_ref"}
                or after_loaded["run"] != loaded["run"]
                or after_loaded["input_manifest"] != loaded["input_manifest"]
                or set(after["artifacts"]) != expected_names
            ):
                raise ValueError(
                    "Rating implementation or dossier changed during render"
                )
            result = {
                "saved": True,
                "status": rendered["record"]["assessment"]["status"],
                "record_sha256": rendered["record"]["record_sha256"],
                "revision": after["revision"],
                "run_completed": False,
                "submission_authorized": False,
                "professional_approval_added": False,
            }
            seal(
                intent,
                {
                    "request_sha256": fingerprint,
                    "owner_scope": owner_scope(binding),
                    "implementation": after["implementation"],
                    "artifacts": after["artifacts"],
                    "result": result,
                },
                api,
            )
            return result
    exact(args, context)
    if action == "read":
        selection = fields(args["fields"])
        value = preview(selection, binding, loaded, root, context, api)
        if context["artifacts"]:
            engine_call(
                root, {**request_for(selection, loaded, api), "operation": "replay"}
            )
        return bounded(
            {
                "work_ref": binding["work_ref"],
                "revision": context["revision"],
                "source_ref": context["source_ref"],
                "data": {"selection": {"source_ref": context["source_ref"]}},
                **value,
            }
        )
    if action == "artifact":
        name = args["artifact_ref"]
        if (
            not re.fullmatch(r"[0-9a-f]{64}/dossier\.(json|md)", name)
            or name not in context["artifacts"]
        ):
            raise PermissionError("Choose an exact verified Rating artifact")
        record = api.read_json(context["output"] / name.split("/")[0] / "dossier.json")
        candidates = []
        for row in loaded["input_manifest"]["inputs"]:
            if (
                row["kind"] == "import"
                and Path(row["execution_relative_path"]).suffix.lower() == ".json"
            ):
                path = selected(row["binding_id"], loaded, api)
                if api.read_json(path) == record["case"]:
                    candidates.append(row["binding_id"])
        if len(candidates) != 1:
            raise ValueError("Rating artifact has no unique current registered case")
        previous_id = ""
        if record["previous_record_sha256"]:
            prior = [
                r
                for r in loaded["input_manifest"]["inputs"]
                if r["kind"] == "upstream_artifact"
                and r["upstream_workflow_id"] == "rating-legalita"
                and Path(r["execution_relative_path"]).name == "dossier.json"
                and api.read_json(
                    selected(r["binding_id"], loaded, api, previous=True)
                )["record_sha256"]
                == record["previous_record_sha256"]
            ]
            if len(prior) != 1:
                raise ValueError(
                    "Rating artifact predecessor receipt is missing or ambiguous"
                )
            previous_id = prior[0]["binding_id"]
        replay = engine_call(
            root,
            {
                **request_for(
                    {
                        "case_input_id": candidates[0],
                        "previous_input_id": previous_id,
                        "note": "",
                    },
                    loaded,
                    api,
                ),
                "operation": "replay",
            },
        )
        if replay["record"] != record:
            raise ValueError("Rating artifact differs from complete public replay")
        path = context["output"] / name
        data = path.read_bytes()
        if len(data) > 1_000_000 or file_hash(path) != context["artifacts"][name]:
            raise ValueError("Rating artifact is changed or exceeds the download limit")
        return {
            "name": path.name,
            "base64": base64.b64encode(data).decode(),
            "mime_type": (
                "application/json"
                if path.suffix == ".json"
                else "text/markdown;charset=utf-8"
            ),
        }
    raise ValueError("Unknown native Rating route")
