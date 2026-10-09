"""Preserve explicitly mapped, already reviewed CH-GE documents as Archive outputs.

Hash, path and receipt rules enforce mechanically verifiable byte preservation and
portable packaging. They never choose sources or review extracted invoice meaning.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from native_bank_preparation import file_hash, tree_hash
from native_passive_audit import object_file, ordinary
from native_passive_service import read_record, save_record, scoped

__all__ = ["dispatch"]

FIELDS = {"canonical_id", "originals", "operator_ref", "decision_basis"}
RESERVED = {"population.json", "grouping-review.json"}
MAX_COPY_BYTES = 512 * 1024 * 1024


def portable(value: Any) -> str:
    """Reject escape, alias and nonportable paths rather than rewrite reviewed locators."""
    if not isinstance(value, str) or len(value) > 500:
        raise ValueError("Invalid declared original path")
    parts = value.split("/")
    if any(
        not part
        or part in {".", ".."}
        or part[-1:] in {".", " "}
        or re.search(r'[<>:"\\|?*\x00-\x1f]', part)
        or re.fullmatch(r"(?i:CON|PRN|AUX|NUL|COM[1-9]|LPT[1-9])(?:\..*)?", part)
        for part in parts
    ):
        raise ValueError("Declared original path is not portable within its group")
    if parts[0].casefold() in RESERVED:
        raise ValueError("Declared original conflicts with group metadata")
    return value


def implementation(root: Path, api: Any) -> str:
    return api.digest(
        {
            str(path): file_hash(path)
            for path in (
                Path(__file__),
                Path(__file__).with_name("native_passive_sources_bridge.py"),
                Path(__file__).with_name("native_workspace.py"),
                Path(__file__).with_name("native_passive_service.py"),
                Path(__file__).with_name("native_bank_preparation.py"),
                root / "scripts/reviewed_invoices.py",
            )
        }
    )


def consumer(root: Path, directory: Path) -> dict:
    """The fixed public reader owns extraction review, schema and original digests."""
    result = subprocess.run(
        [
            sys.executable,
            "-I",
            "-B",
            str(Path(__file__).with_name("native_passive_sources_bridge.py")),
            str(root),
        ],
        input=json.dumps({"population": str(directory / "population.json")}),
        text=True,
        capture_output=True,
        timeout=90,
        check=False,
    )
    if result.returncode:
        raise ValueError(result.stderr.strip().splitlines()[-1] or "Review refused")
    return json.loads(result.stdout)


def sources(loaded: dict, api: Any) -> dict:
    # Archive hydrates paths from the verified manifest; its serialized context
    # is an envelope, not an independent collection of trusted filesystem paths.
    context = loaded["context"]
    result = {r["binding_id"]: r for r in context["input_bindings"]}
    if len(result) != len(context["input_bindings"]) or len(result) > 1000:
        raise ValueError("Source group exceeds native limit; use the specialist route")
    for row in result.values():
        ordinary(Path(row["path"]))
        if file_hash(Path(row["path"])) != row["sha256"]:
            raise ValueError("Registered source changed")
    return result


def extraction(inputs: dict, identity: str) -> tuple[dict, dict]:
    if identity not in inputs:
        raise PermissionError("Select a registered reviewed JSON")
    value = object_file(Path(inputs[identity]["path"]))
    if (
        value.get("schema_version") != "vera.reviewed_invoices.v1"
        or value.get("jurisdiction") != "CH-GE"
        or not isinstance(value.get("invoices"), list)
        or not 1 <= len(value["invoices"]) <= 100_000
    ):
        raise ValueError("Expected the maintained reviewed CH-GE invoice population")
    documents: dict[str, dict] = {}
    aliases: dict[str, str] = {}
    for row in value["invoices"]:
        name = portable(row["source_path"])
        alias = name.casefold()
        if alias in aliases and aliases[alias] != name:
            raise ValueError("Declared originals collide on a case-insensitive host")
        aliases[alias] = name
        if name in documents and documents[name]["sha256"] != row["source_sha256"]:
            raise ValueError("One original has conflicting declared digests")
        documents[name] = {"path": name, "sha256": row["source_sha256"]}
    if len(documents) > 1000 or any(
        name.casefold().startswith(other.casefold() + "/")
        for name in documents
        for other in documents
        if name != other
    ):
        raise ValueError(
            "Original population is oversized or has file/directory conflicts"
        )
    return value, documents


def fields(value: Any, inputs: dict) -> dict:
    """Keep partial mappings and attribution separate from confirmation and extraction review."""
    if (
        not isinstance(value, dict)
        or set(value) - FIELDS
        or len(json.dumps(value).encode()) > 800_000
    ):
        raise ValueError("Invalid source-group draft")
    identity = value.get("canonical_id", "")
    if not isinstance(identity, str) or identity and identity not in inputs:
        raise PermissionError("Canonical selection is outside this run")
    chosen = value.get("originals", {})
    if not isinstance(chosen, dict) or len(chosen) > 1000:
        raise ValueError("Invalid original mapping")
    for name, source in chosen.items():
        portable(name)
        if not isinstance(source, str) or source not in inputs:
            raise PermissionError("Original selection is outside this run")
    for key in ("operator_ref", "decision_basis"):
        if key in value and (not isinstance(value[key], str) or len(value[key]) > 4000):
            raise ValueError("Invalid source-group attribution")
    return value


def current(root: Path, binding: dict, loaded: dict, api: Any) -> dict:
    if binding["workflow_id"] != "client-file-preparation":
        raise PermissionError(
            "Source groups belong to an owned document-preparation run"
        )
    output = Path(loaded["output_dir"])
    inputs = sources(loaded, api)
    private = api.ui_state_directory(output, create=False)
    population = tree_hash(output)
    records = []
    for path in sorted(private.glob("source-group-request-*.json")):
        record = read_record(path, api)
        if record["run_scope"] != [
            binding[k] for k in ("client_id", "engagement_id", "run_id")
        ]:
            raise PermissionError("Source-group receipt belongs to another run")
        if record.get("result"):
            identity = record["group_ref"]
            if not re.fullmatch(r"[0-9a-f]{64}", identity):
                raise ValueError("Invalid source-group receipt")
            directory = output / ("reviewed-invoices-" + identity)
            if tree_hash(directory) != record["result"]["hashes"]:
                raise ValueError("Registered source-group outputs changed")
            replay = consumer(root, directory)
            if replay != record["result"]["replay"]:
                raise ValueError("Source-group review differs from the public consumer")
        records.append(record)
    if len(records) > 200:
        raise ValueError(
            "Source-group history exceeds native limit; use the specialist route"
        )
    groups = {"reviewed-invoices-" + r["group_ref"] for r in records if r.get("result")}
    uncertain = any(not r.get("result") for r in records) or any(
        path.name.startswith("reviewed-invoices-") and path.name not in groups
        for path in output.iterdir()
    )
    checkpoint = api.digest(
        [loaded["run"], loaded["input_manifest"], population, implementation(root, api)]
    )
    return {
        "output": output,
        "private": private,
        "inputs": inputs,
        "population": population,
        "records": records,
        "uncertain": uncertain,
        "checkpoint": checkpoint,
    }


def draft_path(state: dict, binding: dict, api: Any) -> Path:
    return state["private"] / (
        "source-group-draft-" + api.digest(scoped(binding)) + ".json"
    )


def draft(state: dict, binding: dict, api: Any) -> dict:
    value = read_record(draft_path(state, binding, api), api)
    if value and value["scope"] != scoped(binding):
        raise PermissionError("Source-group draft belongs to another actor")
    stale = bool(value and value["checkpoint"] != state["checkpoint"])
    return {
        "fields": value["fields"] if value and not stale else {},
        "exists": bool(value),
        "stale": stale,
        "draft_revision": value["record_sha256"] if value else "",
    }


def projection(state: dict, binding: dict, loaded: dict, args: dict, api: Any) -> dict:
    identity = args.get("canonical_id", args.get("source_ref", ""))
    value, documents = extraction(state["inputs"], identity) if identity else ({}, {})
    offset = args.get("offset", 0)
    if type(offset) is not int or offset < 0:
        raise ValueError("Invalid original page")
    rows = list(documents.values())
    return {
        "work_ref": binding["work_ref"],
        "revision": api.digest([state["checkpoint"], identity]),
        "data": {"selection": {"source_ref": identity or None}},
        "workflow": binding["workflow_id"],
        "label": loaded["run"]["label"],
        "inputs": [
            {"id": k, "title": Path(r["path"]).name, "sha256": r["sha256"]}
            for k, r in state["inputs"].items()
        ],
        "documents": rows[offset : offset + 30],
        "total": len(rows),
        "offset": offset,
        "invoice_count": len(value.get("invoices", [])),
        "extraction_review": value.get("professional_review"),
        "draft": draft(state, binding, api),
        "groups": [
            {
                "id": r["group_ref"],
                "invoice_count": r["result"]["replay"]["invoice_count"],
                "operator_ref": r["fields"]["operator_ref"],
            }
            for r in state["records"]
            if r.get("result")
        ],
        "interrupted": state["uncertain"],
        "can_write": loaded["run"]["status"] == "running"
        and "REVIEWER" in os.environ.get("VERA_WORKSPACE_ROLES", "").split(",")
        and not state["uncertain"],
        "professional_approval": False,
    }


def dispatch(
    tool: str, args: dict, binding: dict, loaded: dict, root: Path, api: Any
) -> dict:
    """Preserve intent on faults; completed retries replay, uncertain writes never repeat."""
    state = current(root, binding, loaded, api)
    page = projection(state, binding, loaded, args, api)
    if tool == "vera_workspace_source_group_setup":
        return page
    if tool in {
        "vera_workspace_source_group_source",
        "vera_workspace_source_group_explain",
    }:
        if (
            args["revision"] != page["revision"]
            or args["item_id"] not in state["inputs"]
        ):
            raise PermissionError("Choose an exact current registered source")
        row = state["inputs"][args["item_id"]]
        path = Path(row["path"])
        with path.open("rb") as stream:
            head = stream.read(20_000)
        try:
            excerpt = head.decode("utf-8")
        except UnicodeDecodeError as exc:
            # A byte cap can split a valid UTF-8 character. Preserve the complete
            # text prefix; do not mislabel that mechanically truncated file as binary.
            excerpt = (
                head[: exc.start].decode("utf-8")
                if exc.reason == "unexpected end of data"
                and path.stat().st_size > len(head)
                else None
            )
        selected = {
            "id": args["item_id"],
            "title": path.name,
            "sha256": row["sha256"],
            "byte_count": path.stat().st_size,
            "excerpt": excerpt,
            "coverage": "At most the first 20,000 bytes; binary sources have no text preview.",
        }
        live = api.load_binding(binding)
        if current(root, binding, live, api)["checkpoint"] != state["checkpoint"]:
            raise ValueError("Source group changed during selected read")
        if tool.endswith("_explain"):
            return {
                "work_ref": binding["work_ref"],
                "revision": page["revision"],
                "untrusted_evidence": selected,
                "instruction": "Discuss only this selected source; grouping and extraction review require separate explicit actions.",
            }
        return {**page, "selection": {**selected, "path": str(path)}}
    if tool == "vera_workspace_source_group_outputs":
        identity = args.get("group_ref")
        if args["revision"] != page["revision"]:
            raise ValueError("Source group changed; reopen it")
        record = next(
            (
                r
                for r in state["records"]
                if r.get("result") and r["group_ref"] == identity
            ),
            None,
        )
        if record is None:
            raise PermissionError("Choose a completed exact group")
        base = state["output"] / ("reviewed-invoices-" + identity)
        return {
            **page,
            "outputs": [
                {"name": name, "path": str(base / name)}
                for name in record["result"]["hashes"]
            ],
            "grouping_review": record["fields"],
        }
    if tool not in {
        "vera_workspace_source_group_draft_save",
        "vera_workspace_source_group_draft_clear",
        "vera_workspace_source_group_prepare",
    }:
        raise ValueError("Unknown source-group action")
    if "REVIEWER" not in os.environ.get("VERA_WORKSPACE_ROLES", "").split(","):
        raise PermissionError("Reviewer authority required for local grouping")
    if loaded["run"]["status"] != "running":
        raise PermissionError("Group preparation requires a running owned run")
    value = fields(args.get("fields", {}), state["inputs"])
    if tool != "vera_workspace_source_group_draft_clear" and (
        value.get("canonical_id", "") != (args.get("source_ref") or "")
    ):
        raise ValueError("Draft belongs to another canonical selection")
    request_path = state["private"] / (
        "source-group-request-"
        + api.digest([scoped(binding), args.get("idempotency_key")])
        + ".json"
    )
    with api.write_lock(state["output"]):
        loaded = api.load_binding(binding)
        state = current(root, binding, loaded, api)
        old = read_record(request_path, api) if tool.endswith("_prepare") else None
        if old:
            if old["fields"] != value or old["scope"] != scoped(binding):
                raise ValueError(
                    "Source-group request key belongs to different choices"
                )
            if not old.get("result"):
                raise ValueError("Interrupted grouping requires specialist inspection")
            return {
                **projection(state, binding, loaded, args, api),
                "group_ref": old["group_ref"],
                "status": "already_prepared",
            }
        page = projection(state, binding, loaded, args, api)
        if state["uncertain"] or args["revision"] != page["revision"]:
            raise ValueError(
                "Source/output population changed or grouping is uncertain"
            )
        if page["draft"]["draft_revision"] != args["expected_draft_revision"]:
            raise ValueError("Source-group draft changed; recover the current version")
        if tool.endswith("_draft_clear"):
            path = draft_path(state, binding, api)
            if path.exists():
                path.unlink()
            return projection(state, binding, loaded, args, api)
        if tool.endswith("_draft_save"):
            save_record(
                draft_path(state, binding, api),
                {
                    "scope": scoped(binding),
                    "checkpoint": state["checkpoint"],
                    "fields": value,
                },
                api,
            )
            return projection(state, binding, loaded, args, api)
        if args.get("human_reviewed") is not True:
            raise PermissionError("Confirm the exact original grouping")
        if (
            not value.get("operator_ref", "").strip()
            or not value.get("decision_basis", "").strip()
        ):
            raise ValueError("Supply actual grouping attribution and basis")
        _, documents = extraction(state["inputs"], value["canonical_id"])
        if set(value.get("originals", {})) != set(documents):
            raise ValueError("Map every declared original explicitly")
        for name, identity in value["originals"].items():
            if (
                identity == value["canonical_id"]
                or state["inputs"][identity]["sha256"] != documents[name]["sha256"]
            ):
                raise ValueError(
                    "Selected original differs from the declared source digest"
                )
        byte_count = Path(
            state["inputs"][value["canonical_id"]]["path"]
        ).stat().st_size + sum(
            Path(state["inputs"][i]["path"]).stat().st_size
            for i in value["originals"].values()
        )
        if byte_count > MAX_COPY_BYTES:
            raise ValueError("Source group exceeds native copy limit")
        identity = api.digest([scoped(binding), args["idempotency_key"]])
        base = state["output"] / ("reviewed-invoices-" + identity)
        record = {
            "scope": scoped(binding),
            "run_scope": [binding[k] for k in ("client_id", "engagement_id", "run_id")],
            "group_ref": identity,
            "fields": value,
            "source_checkpoint": state["checkpoint"],
            "requested_at": datetime.now(timezone.utc).isoformat(),
        }
        # Private transient preflight calls the unchanged public reader. Invalid
        # extraction/review never becomes an official output or a durable intent.
        # Once intent exists, rename commits the complete group; faults retain it.
        with tempfile.TemporaryDirectory(
            prefix="source-group-preflight-", dir=state["private"]
        ) as temporary:
            staged = Path(temporary)
            selected = {"population.json": value["canonical_id"], **value["originals"]}
            for name, source_id in selected.items():
                destination = staged / name
                destination.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
                with (
                    Path(state["inputs"][source_id]["path"]).open("rb") as source,
                    destination.open("xb") as target,
                ):
                    shutil.copyfileobj(source, target)
                destination.chmod(0o600)
                if file_hash(destination) != state["inputs"][source_id]["sha256"]:
                    raise ValueError("Source changed during grouping")
            replay = consumer(root, staged)
            api.atomic_json(
                staged / "grouping-review.json",
                {
                    **record,
                    "professional_approval": False,
                    "extraction_review_replaced": False,
                },
            )
            (staged / "grouping-review.json").chmod(0o600)
            live = api.load_binding(binding)
            if (
                live["run"] != loaded["run"]
                or live["input_manifest"] != loaded["input_manifest"]
                or tree_hash(state["output"]) != state["population"]
            ):
                raise ValueError("Archive source/output scope changed before grouping")
            save_record(request_path, record, api)
            if base.exists():
                raise ValueError(
                    "Unregistered existing source group requires inspection"
                )
            staged.rename(base)
        live = api.load_binding(binding)
        if (
            live["run"] != loaded["run"]
            or live["input_manifest"] != loaded["input_manifest"]
        ):
            raise ValueError("Archive scope changed during source grouping")
        physical = tree_hash(state["output"])
        if {
            k: v for k, v in physical.items() if not k.startswith(base.name + "/")
        } != state["population"]:
            raise ValueError("Other outputs changed during grouping")
        result = {"hashes": tree_hash(base), "replay": replay}
    # Only a clean guard release and final source/output replay close the receipt.
    live = api.load_binding(binding)
    if (
        live["run"] != loaded["run"]
        or live["input_manifest"] != loaded["input_manifest"]
        or tree_hash(base) != result["hashes"]
    ):
        raise ValueError(
            "Source group changed before completion; inspect retained intent"
        )
    save_record(request_path, {**record, "result": result}, api)
    state = current(root, binding, live, api)
    return {
        **projection(state, binding, live, args, api),
        "group_ref": identity,
        "status": "prepared",
    }
