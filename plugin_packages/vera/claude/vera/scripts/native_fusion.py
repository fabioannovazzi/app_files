"""Owned multi-company merger review over authoritative P0/P1 case APIs.

Byte receipts and CAS are fixed integrity controls, not legal classifiers.
Prepared semantic proposals and actual professional confirmations stay separate.
"""

from __future__ import annotations

import base64
import hashlib
import json
import os
import re
import subprocess
import sys
from pathlib import Path
from typing import Any

from native_transformation import bounded, files, read, regular, stamp

__all__ = ["dispatch"]

PREFIX = "vera_workspace_fusion_"
EMPTY = {
    key: ""
    for key in (
        "operation",
        "proposal_ref",
        "target_id",
        "decision_id",
        "professional_role",
        "scope_text",
        "confirmation",
        "note",
    )
}
APPLY_ACTIONS = {"put", "workpaper", "bind_archive", "import_archive"}


def fields(value: Any) -> dict:
    """Keep complete literal private fields; do not restore execution consent."""
    if (
        not isinstance(value, dict)
        or set(value) != set(EMPTY)
        or any(not isinstance(v, str) or len(v) > 4000 for v in value.values())
        or value["operation"] not in {"", "apply_proposal", "approve", "export"}
    ):
        raise ValueError("Invalid merger selection fields")
    return dict(value)


def bindings() -> tuple[dict, list]:
    """Trusted host configuration names exact cases and existing logical actors."""
    owner = {
        key: os.environ.get("VERA_WORKSPACE_" + key.upper(), "")
        for key in ("tenant_id", "actor_id")
    }
    if not all(owner.values()):
        raise PermissionError("Open mergers through the owned MCP service")
    path = os.environ.get("VERA_FUSIONE_WORKSPACE_BINDINGS")
    if not path:
        return owner, []
    config = read(Path(path))
    if any(config.get(k) != v for k, v in owner.items()):
        raise PermissionError("Merger bindings belong to another operator")
    rows = config["bindings"]
    if not isinstance(rows, list) or len(rows) > 200:
        raise ValueError("Bind at most 200 exact merger cases")
    refs = [row["work_ref"] for row in rows]
    if len(set(refs)) != len(refs) or any(
        not isinstance(ref, str) or not re.fullmatch(r"[A-Za-z0-9_-]{1,120}", ref)
        for ref in refs
    ):
        raise ValueError("Merger references must be unique identifiers")
    return owner, rows


def connection(row: dict) -> Path:
    """Case and proposal files remain exact private host-bound paths."""
    root = Path(row["case_dir"])
    regular(root)
    if (
        not root.is_absolute()
        or not root.is_dir()
        or root in {Path(root.anchor), Path.home()}
        or any((p / ".git").exists() for p in (root, *root.parents))
        or {"public", "published", "static", "plugin_packages"}
        & {p.lower() for p in root.parts}
    ):
        raise ValueError(
            "Bind a dedicated private merger case outside Git and public directories"
        )
    regular(root / "case.sqlite")
    if not (root / "case.sqlite").is_file():
        raise ValueError("Initialize the merger case with the public helper first")
    if not re.fullmatch(r"op_[0-9a-f]{32}", row["operation_id"]) or not re.fullmatch(
        r"[A-Za-z0-9_.-]{1,120}", row["case_actor"]
    ):
        raise ValueError("Declare exact existing operation and actor identities")
    proposals = row.get("proposals", [])
    if not isinstance(proposals, list) or len(proposals) > 200:
        raise ValueError("Bind at most 200 exact prepared merger requests")
    refs = [r["proposal_ref"] for r in proposals]
    if len(set(refs)) != len(refs):
        raise ValueError("Duplicate merger proposal binding")
    for item in proposals:
        path = Path(item["path"])
        regular(path)
        if (
            not path.is_absolute()
            or not path.is_file()
            or path.suffix.lower() != ".json"
            or path.stat().st_size > 1_000_000
            or not path.resolve().is_relative_to(root.parent)
            or path.resolve().is_relative_to(root / ".native-workspace")
            or not re.fullmatch(r"[A-Za-z0-9_-]{1,120}", item["proposal_ref"])
        ):
            raise ValueError(
                "Bind one exact prepared JSON request in the selected case area"
            )
    return root


def producer(
    module: Path, root: Path, row: dict, action: str, **arguments: Any
) -> dict:
    """Use isolated unchanged public methods, never alternate calculations."""
    result = subprocess.run(
        [
            sys.executable,
            "-I",
            "-B",
            str(Path(__file__).with_name("native_fusion_bridge.py")),
        ],
        input=bounded(
            {
                "module": str(module),
                "workspace": str(root),
                "operation_id": row["operation_id"],
                "case_actor": row["case_actor"],
                "action": action,
                **arguments,
            }
        ),
        text=True,
        capture_output=True,
        timeout=90,
        check=False,
    )
    if result.returncode:
        raise ValueError(
            "Merger producer refused this operation; inspect permissions, exact inputs and public workflow requirements"
        )
    value = json.loads(result.stdout)
    bounded(value)
    return value


def private_directory(root: Path, owner: dict, row: dict) -> Path:
    path = (
        root
        / ".native-workspace"
        / (
            "fusion-"
            + stamp([owner, row["work_ref"], row["operation_id"], row["case_actor"]])
        )
    )
    regular(path)
    return path


def checked_receipt(path: Path) -> dict:
    value = read(path)
    if value.get("content_sha256") != stamp(
        {k: v for k, v in value.items() if k != "content_sha256"}
    ):
        raise ValueError("Merger receipt integrity changed")
    return value


def seal(path: Path, value: dict, api: Any) -> None:
    api.atomic_json(path, {**value, "content_sha256": stamp(value)})


def snapshot(owner: dict, row: dict, module: Path) -> tuple[Path, Path, dict]:
    root = connection(row)
    before = files(root)
    data = producer(module, root, row, "snapshot")
    implementation = {
        section + "/" + key: value
        for section in ("scripts", "skills")
        for key, value in files(module / section).items()
        if Path(key).suffix in {".py", ".json", ".md"}
    }
    for path in (
        Path(__file__),
        Path(__file__).with_name("native_fusion_bridge.py"),
        Path(__file__).parents[1] / "ui/fusion.js",
        Path(__file__).parents[1] / "ui/model-data-report.js",
    ):
        regular(path)
        implementation[path.name] = hashlib.sha256(path.read_bytes()).hexdigest()
    implementation.update(data["shared_implementation"])
    proposals = []
    for item in row.get("proposals", []):
        path = Path(item["path"])
        request = read(path)
        if request.get("action") not in APPLY_ACTIONS:
            raise ValueError(
                "Prepared merger requests cannot bypass separate confirmations or grants"
            )
        proposals.append(
            {
                "proposal_ref": item["proposal_ref"],
                "name": path.name,
                "action": request["action"],
                "request_sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
            }
        )
    directory = private_directory(root, owner, row)
    exports = []
    for path in sorted(directory.glob("export-*.json")):
        receipt = checked_receipt(path)
        destination = Path(receipt["directory"])
        baseline = Path(receipt["baseline"])
        if (
            receipt["owner"] != owner
            or receipt["operation_id"] != row["operation_id"]
            or receipt["case_actor"] != row["case_actor"]
            or receipt["implementation"] != implementation
            or not destination.is_relative_to(root / "exports")
            or not baseline.is_relative_to(directory / "export-bases")
            or files(destination) != receipt["artifacts"]
        ):
            raise ValueError("Merger export receipt or scope changed")
        verified = producer(module, root, row, "verify_export", receipt=receipt)
        exports.append(
            {
                "export_ref": receipt["export_ref"],
                "case_report": verified["case_report"],
                "model_report": verified["model_report"],
                "model_report_markdown": verified["model_report_markdown"],
                "artifacts": [
                    {"name": n, "sha256": h} for n, h in receipt["artifacts"].items()
                ],
            }
        )
    if before != files(root):
        raise ValueError("Merger changed during native readback")
    revision = stamp([owner, row, before, implementation, proposals, exports])
    return (
        root,
        directory,
        {
            "work_ref": row["work_ref"],
            "revision": revision,
            "source_ref": revision,
            "data": {
                "selection": {"source_ref": revision},
                **data,
                "proposals": proposals,
                "exports": exports,
            },
            "implementation": implementation,
        },
    )


def proposal(row: dict, selection: dict) -> Path:
    item = next(
        (
            r
            for r in row.get("proposals", [])
            if r["proposal_ref"] == selection["proposal_ref"]
        ),
        None,
    )
    if item is None:
        raise PermissionError("Select an exact host-bound merger proposal")
    path = Path(item["path"])
    request = read(path)
    if request["action"] not in APPLY_ACTIONS:
        raise ValueError(
            "Separate professional confirmation cannot be embedded in a proposal"
        )
    if request["action"] == "bind_archive":
        identity = {
            k: request[k] for k in ("client_root", "client_id", "engagement_id")
        }
        if identity not in row.get("archives", []):
            raise PermissionError(
                "Select an explicitly host-authorized company Archive binding"
            )
    if (
        request["action"] == "put"
        and request.get("kind") == "Entity"
        and any(
            p not in row.get("allowed_source_roots", [])
            for p in request["data"]["source_roots"]
        )
    ):
        raise PermissionError("Company source roots require exact host authorization")
    return path


def preview(root: Path, row: dict, page: dict, selection: dict, module: Path) -> dict:
    operation = selection["operation"]
    if operation == "apply_proposal":
        path = proposal(row, selection)
        result = {
            "request": read(path),
            **producer(
                module,
                root,
                row,
                "preview_proposal",
                expected_files=files(root),
                proposal=str(path),
            ),
        }
        # Preview records are not persisted identities. Bind the complete computed
        # content and actual dependencies, without an invented creation clock/hash.
        result["proposed_record"].pop("created_at")
        result["proposed_record"].pop("sha256")
        result["status"]["reference"] = None
    elif operation == "approve":
        target = next(
            (
                r
                for r in page["data"]["report"]["records"]
                if r["record"]["id"] == selection["target_id"]
            ),
            None,
        )
        if target is None:
            raise PermissionError("Select one exact accessible merger record")
        if any(
            not selection[k].strip()
            for k in ("decision_id", "professional_role", "scope_text", "confirmation")
        ):
            raise ValueError(
                "Enter the actual role, defined scope and professional confirmation"
            )
        result = {
            "target": target["record"],
            "status": target["status"],
            "proposed_confirmation": {
                k: selection[k]
                for k in (
                    "decision_id",
                    "professional_role",
                    "scope_text",
                    "confirmation",
                )
            },
            "professional_confirmation_recorded": False,
        }
    elif operation == "export":
        result = {
            "report": page["data"]["report"],
            "runtime_profile": "openai-codex",
            "legal_effect": "not_verified",
            "filing": "not_performed",
        }
    else:
        raise ValueError("Choose a prepared proposal, separate confirmation or export")
    return {**result, "preview_ref": stamp([page["revision"], selection, result])}


def dispatch(tool: str, args: dict, module: Path, api: Any) -> dict:
    """Preserve authoritative multi-company storage and separately asserted review."""
    owner, rows = bindings()
    action = tool.removeprefix(PREFIX)
    if action == "catalogue":
        works = []
        for row in rows:
            _, _, page = snapshot(owner, row, module)
            report = page["data"]["report"]
            operation = next(
                r["record"]
                for r in report["records"]
                if r["record"]["id"] == "operation"
            )
            works.append(
                {
                    "work_ref": row["work_ref"],
                    "operation_id": report["operation_id"],
                    "objective": operation["data"]["objectives"],
                    "synthetic": report["synthetic"],
                    "case_actor": report["actor"],
                }
            )
        return {
            "works": works,
            "configured": bool(rows),
            "workspace_scope": "explicit_multi_company_case",
            "model_context_transferred": False,
        }
    row = next((r for r in rows if r["work_ref"] == args["work_ref"]), None)
    if row is None:
        raise PermissionError("Unknown owned merger case")
    root = connection(row)
    with api.write_lock(root / "native-fusion-marker"):
        _, directory, page = snapshot(owner, row, module)
        directory.mkdir(mode=0o700, parents=True, exist_ok=True)
        path = directory / "draft.json"
        draft = (
            read(path)
            if path.exists()
            else {"generation": 0, "revision": "", "fields": dict(EMPTY)}
        )
        fields(draft["fields"])
        intents = {
            p.name: checked_receipt(p) for p in sorted(directory.glob("intent-*.json"))
        }
        pending = [k for k, value in intents.items() if "result" not in value]
        can_write = (
            "REVIEWER" in os.environ.get("VERA_WORKSPACE_ROLES", "").split(",")
            and page["data"]["grant"]["role"] != "reader"
        )
        if action == "setup":
            page.pop("implementation")
            return json.loads(
                bounded(
                    {
                        **page,
                        "fields": draft["fields"],
                        "draft_revision": stamp(draft),
                        "draft_stale": bool(
                            draft["revision"] and draft["revision"] != page["revision"]
                        ),
                        "can_write": can_write,
                        "can_approve": can_write
                        and page["data"]["grant"]["role"]
                        in {"reviewer", "administrator"},
                        "pending_operations": pending,
                        "confirmation_restored": False,
                        "initial_authoring_available": False,
                        "model_authoring_available": False,
                    }
                )
            )
        if (
            any(args[k] != page[k] for k in ("revision", "source_ref"))
            and action != "execute"
        ):
            raise ValueError("Stale merger scope; reopen the case")
        if action == "preview":
            selection = fields(args["fields"])
            return json.loads(
                bounded(
                    {
                        "work_ref": page["work_ref"],
                        "revision": page["revision"],
                        "data": {"selection": {"source_ref": page["source_ref"]}},
                        **preview(root, row, page, selection, module),
                    }
                )
            )
        if action == "artifact":
            if args.get("document_ref"):
                item = next(
                    (
                        r
                        for r in page["data"]["report"]["history"]
                        if stamp(
                            {
                                k: r[k]
                                for k in ("operation_id", "id", "version", "sha256")
                            }
                        )
                        == args["document_ref"]
                        and r["kind"] in {"Evidence", "Artifact"}
                    ),
                    None,
                )
                if item is None:
                    raise PermissionError(
                        "Select an exact accessible preserved document"
                    )
                return producer(
                    module,
                    root,
                    row,
                    "document",
                    object_id=item["id"],
                    version=item["version"],
                    record_sha256=item["sha256"],
                )
            export = next(
                (
                    e
                    for e in page["data"]["exports"]
                    if e["export_ref"] == args["export_ref"]
                ),
                None,
            )
            if export is None or args["artifact_ref"] not in {
                x["name"] for x in export["artifacts"]
            }:
                raise PermissionError(
                    "Select an exact independently verified merger export"
                )
            receipt = checked_receipt(
                directory / ("export-" + args["export_ref"] + ".json")
            )
            target = Path(receipt["directory"]) / args["artifact_ref"]
            regular(target)
            if target.stat().st_size > 1_000_000:
                raise ValueError("Merger export exceeds native download limit")
            data = target.read_bytes()
            if (
                hashlib.sha256(data).hexdigest()
                != receipt["artifacts"][args["artifact_ref"]]
            ):
                raise ValueError("Merger export changed during download")
            return {
                "name": target.name,
                "base64": base64.b64encode(data).decode(),
                "mime_type": "application/octet-stream",
            }
        if not can_write:
            raise PermissionError(
                "Merger writes require operator and actual case write authority"
            )
        if action == "execute":
            key = args["idempotency_key"]
            if not re.fullmatch(r"[A-Za-z0-9_-]{1,120}", key):
                raise ValueError("Invalid merger request key")
            intent = directory / ("intent-" + stamp(key) + ".json")
            if intent.exists():
                previous = checked_receipt(intent)
                if previous["request_sha256"] != stamp(args):
                    raise ValueError("Merger key belongs to another exact request")
                if "result" not in previous:
                    raise ValueError(
                        "Merger write is uncertain; specialist recovery required"
                    )
                if previous["after_revision"] != page["revision"]:
                    raise ValueError(
                        "Merger advanced since this receipt; inspect current history"
                    )
                return previous["result"]
        if any(args[k] != page[k] for k in ("revision", "source_ref")) or args[
            "expected_draft_revision"
        ] != stamp(draft):
            raise ValueError("Merger scope or private draft CAS changed")
        if action == "draft_clear":
            if args["confirmed"] is not True:
                raise ValueError("Confirm discarding only these private merger fields")
            value = {
                "generation": draft["generation"] + 1,
                "revision": page["revision"],
                "fields": dict(EMPTY),
            }
            api.atomic_json(path, value)
            return {
                "saved": True,
                "draft_revision": stamp(value),
                "fields": value["fields"],
            }
        selection = fields(args["fields"])
        if draft["revision"] and draft["revision"] != page["revision"]:
            raise ValueError("Compare and explicitly discard stale merger fields")
        if action == "draft_save":
            value = {
                "generation": draft["generation"] + 1,
                "revision": page["revision"],
                "fields": selection,
            }
            api.atomic_json(path, value)
            return {"saved": True, "draft_revision": stamp(value), "fields": selection}
        if action != "execute":
            raise ValueError("Unknown native merger route")
        if pending or selection != draft["fields"] or args["confirmed"] is not True:
            raise ValueError(
                "Save and confirm current merger fields; recover uncertain writes first"
            )
        inspected = preview(root, row, page, selection, module)
        if args["preview_ref"] != inspected["preview_ref"]:
            raise ValueError("Review the exact complete merger preview first")
        operation = selection["operation"]
        if operation == "approve" and page["data"]["grant"]["role"] not in {
            "reviewer",
            "administrator",
        }:
            raise PermissionError("Actual merger reviewer authority is required")
        seal(
            intent,
            {
                "owner": owner,
                "operation_id": row["operation_id"],
                "case_actor": row["case_actor"],
                "request_sha256": stamp(args),
            },
            api,
        )
        arguments = {"expected_files": files(root)}
        if operation == "apply_proposal":
            arguments["proposal"] = str(proposal(row, selection))
        elif operation == "approve":
            arguments["fields"] = selection
            arguments["target"] = {
                k: inspected["target"][k]
                for k in ("operation_id", "id", "version", "sha256")
            }
        else:
            export_ref = stamp([owner, row["operation_id"], key])
            arguments.update(
                baseline=str(directory / "export-bases" / export_ref / "case.sqlite"),
                destination=str(root / "exports" / ("native-" + export_ref)),
            )
        result = producer(module, root, row, operation, **arguments)
        if operation == "apply_proposal":
            content = {
                k: v
                for k, v in result["record"].items()
                if k not in {"sha256", "created_at"}
            }
            status = {**result["status"], "reference": None}
            if content != inspected["proposed_record"] or status != inspected["status"]:
                raise ValueError(
                    "Merger proposal changed during execution; recover the retained intent"
                )
        if operation == "export":
            seal(
                directory / ("export-" + export_ref + ".json"),
                {
                    **result,
                    "owner": owner,
                    "operation_id": row["operation_id"],
                    "case_actor": row["case_actor"],
                    "implementation": page["implementation"],
                    "export_ref": export_ref,
                },
                api,
            )
        _, _, after = snapshot(owner, row, module)
        if after["implementation"] != page["implementation"]:
            raise ValueError(
                "Merger implementation changed during execution; recover the retained intent"
            )
        summary = {
            "saved": True,
            "work_ref": row["work_ref"],
            "revision": after["revision"],
            "operation": operation,
            "result": result,
            "sent_or_filed": False,
            "archive_engagements_changed": False,
            "authenticated_signature": False,
        }
        seal(
            intent,
            {
                "owner": owner,
                "operation_id": row["operation_id"],
                "case_actor": row["case_actor"],
                "request_sha256": stamp(args),
                "after_revision": after["revision"],
                "result": summary,
            },
            api,
        )
        return json.loads(bounded(summary))
