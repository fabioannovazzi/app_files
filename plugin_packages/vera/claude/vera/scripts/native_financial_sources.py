"""Named source questions preserve immutable calculations and real public receipts."""

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

__all__ = ["audit_sources", "dispatch"]
PAGE_CHARS = 24000


def bridge(root: Path, request: dict) -> dict:
    result = subprocess.run(
        [
            sys.executable,
            "-I",
            "-B",
            str(Path(__file__).with_name("native_financial_sources_bridge.py")),
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
            result.stderr.strip().splitlines()[-1] or "Financial source request refused"
        )
    return json.loads(result.stdout)


def audit_sources(output: Path, api: Any) -> dict:
    """Exact trees and intents audit mechanical integrity, not question relevance."""
    private = api.ui_state_directory(output, create=False)
    path = private / "financial-evidence-state.json"
    rows = api.read_json(path)["rows"] if path.exists() else []
    known = set()
    for row in rows:
        identity = row["grant_ref"]
        if (
            not re.fullmatch(r"financial-evidence-[0-9a-f]{64}", identity)
            or identity in known
        ):
            raise ValueError("Invalid or duplicate Financial source request")
        known.add(identity)
        if tree_hash(output / identity) != row["artifacts"]:
            raise ValueError("Financial source request artifacts changed")
    return {
        "rows": rows,
        "recovery_required": any(
            "result" not in api.read_json(p)
            for p in private.glob("financial-evidence-request-*.json")
        ),
    }


def selected_parent(
    current: dict, root: Path, binding: dict, loaded: dict, args: dict, api: Any
) -> tuple[dict, dict]:
    from native_financial_execution import read_version

    row = next(
        (
            v
            for v in current["state"]["versions"]
            if v["source_ref"] == args["source_ref"]
        ),
        None,
    )
    if row is None:
        raise ValueError("Choose an exact retained Financial calculation")
    read_version(root, binding, loaded, {"source_ref": row["source_ref"]}, api)
    inventory = bridge(
        root,
        {
            "operation": "inventory",
            "directory": str(current["output"] / row["source_ref"]),
        },
    )
    return row, inventory


def fields_valid(fields: dict) -> None:
    if (
        not isinstance(fields, dict)
        or set(fields) != {"question", "selectors_text"}
        or any(not isinstance(fields[k], str) for k in fields)
    ):
        raise ValueError("Invalid Financial source question fields")
    if len(fields["question"]) > 1000 or len(fields["selectors_text"]) > 12000:
        raise ValueError("Financial source question exceeds public bounds")
    values = fields["selectors_text"].splitlines()
    if len([v for v in values if v.strip()]) > 20 or any(
        len(v.strip()) > 500 for v in values
    ):
        raise ValueError("Financial source selectors exceed public bounds")


def question_draft(
    current: dict, parent: dict, item: dict, api: Any
) -> tuple[Path, dict, str, int]:
    scope = [current["owner"], current["implementation"], parent, item]
    path = current["private"] / (
        "financial-source-draft-"
        + api.digest([current["owner"], parent["source_ref"], item["artifact_id"]])
        + ".json"
    )
    value = api.read_json(path) if path.exists() else None
    if value and value["scope"] != scope:
        raise PermissionError(
            "Financial source question draft belongs to another scope"
        )
    fields = value["fields"] if value else {"question": "", "selectors_text": ""}
    fields_valid(fields)
    return (
        path,
        fields,
        api.digest(value) if value else "",
        value["generation"] if value else 0,
    )


def source_setup(
    root: Path, binding: dict, loaded: dict, args: dict, api: Any
) -> tuple[dict, dict, dict]:
    from native_financial_execution import context

    current = context(binding, loaded, root, api)
    parent, inventory = selected_parent(current, root, binding, loaded, args, api)
    item = next(
        (v for v in inventory["sources"] if v["artifact_id"] == args.get("item_id")),
        None,
    )
    revision = api.digest([current["revision"], parent, inventory])
    data = {
        "work_ref": binding["work_ref"],
        "source_ref": parent["source_ref"],
        "data": {"selection": {"source_ref": parent["source_ref"]}},
        "revision": revision,
        "items": inventory["sources"],
        "selection": {"id": item["artifact_id"]} if item else None,
        "grants": [
            {k: v[k] for k in ("grant_ref", "source_artifact_id", "question")}
            for v in current["evidence"]
            if v["parent_ref"] == parent["source_ref"]
        ],
        "can_write": loaded["run"]["status"] == "running"
        and not current["recovery_required"]
        and "REVIEWER" in os.environ.get("VERA_WORKSPACE_ROLES", "").split(","),
        "recovery_required": current["recovery_required"],
        "report_ready": False,
    }
    if args.get("item_id") and item is None:
        raise ValueError("Choose one sealed Financial source artifact")
    if item:
        _, fields, stamp, _ = question_draft(current, parent, item, api)
        data.update(draft=fields, draft_revision=stamp)
    return current, parent, data


def read_grant(root: Path, binding: dict, loaded: dict, args: dict, api: Any) -> dict:
    from native_financial_execution import context, read_version

    current = context(binding, loaded, root, api)
    row = next(
        (v for v in current["evidence"] if v["grant_ref"] == args["grant_ref"]), None
    )
    if row is None:
        raise PermissionError("Choose an exact owned Financial source request")
    parent = next(
        (
            v
            for v in current["state"]["versions"]
            if v["source_ref"] == row["parent_ref"]
        ),
        None,
    )
    if parent is None or parent["artifacts"] != row["parent_artifacts"]:
        raise ValueError("Financial source request parent changed")
    read_version(root, binding, loaded, {"source_ref": row["parent_ref"]}, api)
    directory = current["output"] / row["grant_ref"]
    # Revalidate the retained copy through the same maintained prepared reader.
    from native_financial_analysis import read_prepared

    read_prepared(
        root,
        {**loaded, "output_dir": str(directory)},
        {},
        api.read_json,
        exact_case_path=directory / "case/case.json",
    )
    path = directory / "case" / row["public"]["source_locator"]
    offset = args.get("offset", 0)
    if (
        not isinstance(offset, int)
        or isinstance(offset, bool)
        or offset < 0
        or offset % PAGE_CHARS
    ):
        raise ValueError("Choose an exact Financial source text page")
    preview = {
        "offset": offset,
        "page_size": PAGE_CHARS,
        "available": False,
        "coverage": "Only this UTF-8 text page; selectors record purpose and do not filter the source.",
    }
    try:
        with path.open(encoding="utf-8", newline="") as handle:
            remaining = offset
            while remaining:
                skipped = handle.read(min(remaining, PAGE_CHARS))
                if not skipped:
                    raise ValueError("Financial source text page is outside the file")
                remaining -= len(skipped)
            text = handle.read(PAGE_CHARS)
            more = bool(handle.read(1))
        if offset and not text:
            raise ValueError("Financial source text page is outside the file")
        preview.update(
            available=True,
            text=text,
            has_more=more,
            complete_file=offset == 0 and not more,
        )
    except UnicodeError:
        preview["limitation"] = (
            "This exact file is not readable as UTF-8. Use its authorized file path through the maintained selected-runtime file reader; no OCR or conversion was performed."
        )
    if (
        file_hash(path) != row["source"]["sha256"]
        or tree_hash(directory) != row["artifacts"]
    ):
        raise ValueError("Financial source request changed during reading")
    return {
        "work_ref": binding["work_ref"],
        "grant_ref": row["grant_ref"],
        "parent_ref": row["parent_ref"],
        "revision": api.digest([current["revision"], row]),
        "question": row["question"],
        "selectors_text": row["selectors_text"],
        "public_receipt": row["public"]["receipt"],
        "source_artifact_id": row["source_artifact_id"],
        "source": row["source"],
        "page": preview,
        "authorized_source_path": str(path),
        "report_ready": False,
        "authorization": "This one complete named sealed source for the recorded question; selectors are purpose annotations, not filters. No other original source is authorized by this request.",
    }


def dispatch(
    tool: str, args: dict, binding: dict, loaded: dict, root: Path, api: Any
) -> dict:
    action = tool.removeprefix("vera_workspace_financial_source_")
    if action in {"view", "context"}:
        data = read_grant(root, binding, loaded, args, api)
        if action == "context" and args["revision"] != data["revision"]:
            raise ValueError("Reopen the exact Financial source request and text page")
        return data
    current, parent, data = source_setup(root, binding, loaded, args, api)
    if action == "setup":
        return data
    if action not in {"draft_save", "grant"}:
        raise ValueError("Unknown Financial source action")
    if not data["can_write"]:
        raise PermissionError(
            "Financial source requests require an owned running reviewer run"
        )
    item = next(
        (v for v in data["items"] if v["artifact_id"] == args.get("item_id")), None
    )
    if item is None:
        raise ValueError("Choose one exact sealed source")
    fields_valid(args["fields"])
    key = args.get("idempotency_key")
    if action == "grant" and (
        not isinstance(key, str) or not re.fullmatch(r"[A-Za-z0-9_-]{1,120}", key)
    ):
        raise ValueError("Invalid Financial source request key")
    fingerprint = api.digest([tool, current["owner"], args])
    with api.write_lock(current["output"]):
        loaded = api.load_binding(binding)
        current, parent, data = source_setup(root, binding, loaded, args, api)
        private = api.ui_state_directory(current["output"])
        intent = private / (
            "financial-evidence-request-"
            + api.digest([current["owner"], key])
            + ".json"
        )
        if action == "grant" and intent.exists():
            saved = api.read_json(intent)
            if saved["request_sha256"] != fingerprint or "result" not in saved:
                raise ValueError("Different or interrupted Financial source request")
            return saved["result"]
        if not data["can_write"] or args["revision"] != data["revision"]:
            raise ValueError("Stale or uncertain Financial source scope")
        path, _, stamp, generation = question_draft(current, parent, item, api)
        if args["expected_draft_revision"] != stamp:
            raise ValueError(
                "Financial source question draft changed in another window"
            )
        if action == "draft_save":
            value = {
                "scope": [current["owner"], current["implementation"], parent, item],
                "fields": args["fields"],
                "generation": generation + 1,
            }
            api.atomic_json(path, value)
            return {
                "saved": True,
                "draft_revision": api.digest(value),
                "report_ready": False,
                "model_grant": False,
            }
        if args["confirmed"] is not True or not args["fields"]["question"].strip():
            raise ValueError(
                "Confirm the exact named source and specific professional question"
            )
        api.atomic_json(intent, {"request_sha256": fingerprint})
        grant_ref = "financial-evidence-" + fingerprint
        directory = current["output"] / grant_ref
        shutil.copytree(current["output"] / parent["source_ref"], directory)
        if tree_hash(directory) != parent["artifacts"]:
            raise ValueError("Financial source request copied population changed")
        public = bridge(
            root,
            {
                "operation": "authorize",
                "directory": str(directory),
                "pack_id": parent["pack_id"],
                "source_artifact_id": item["artifact_id"],
                "question": args["fields"]["question"],
                "selectors": args["fields"]["selectors_text"].splitlines(),
                "context": loaded["context_path"],
            },
        )
        from native_financial_execution import context

        refreshed = api.load_binding(binding)
        after = context(binding, refreshed, root, api)
        if (
            refreshed["run"]["status"] != "running"
            or refreshed["input_manifest"] != loaded["input_manifest"]
            or after["implementation"] != current["implementation"]
        ):
            raise ValueError(
                "Financial source request scope changed during authorization"
            )
        if tree_hash(current["output"] / parent["source_ref"]) != parent["artifacts"]:
            raise ValueError(
                "Financial source request parent changed during authorization"
            )
        row = {
            "grant_ref": grant_ref,
            "parent_ref": parent["source_ref"],
            "parent_artifacts": parent["artifacts"],
            "owner": current["owner"],
            "implementation": current["implementation"],
            "inputs": loaded["input_manifest"],
            "source_artifact_id": item["artifact_id"],
            "source": item,
            "question": args["fields"]["question"],
            "selectors_text": args["fields"]["selectors_text"],
            "public": public,
            "artifacts": tree_hash(directory),
        }
        api.atomic_json(
            private / "financial-evidence-state.json",
            {"rows": [*current["evidence"], row]},
        )
        result = {
            "saved": True,
            "grant_ref": grant_ref,
            "parent_ref": parent["source_ref"],
            "report_ready": False,
            "professional_approval": False,
            "run_completed": False,
        }
        api.atomic_json(intent, {"request_sha256": fingerprint, "result": result})
        return result
