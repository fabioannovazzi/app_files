"""Explicit per-source native intake before the existing Open-item review flow."""

from __future__ import annotations

import base64
import hashlib
import json
import os
import re
import subprocess
import sys
from datetime import date
from pathlib import Path
from typing import Any

from native_bank_preparation import file_hash

__all__ = ["dispatch"]

TEXT_FIELDS = {
    "scope_year",
    "cutoff_date",
    "currency",
    "jurisdiction",
    "language",
    "document_language",
    "reviewer_ref",
    "reviewed_on",
    "title",
    "narrative",
}
POLICY_FIELDS = {
    "post_cutoff_events_excluded",
    "payment_orders_are_bank_evidence",
    "factoring_pro_soluto_closes_item",
    "compensation_requires_bank",
}
KEYWORD_FIELDS = {"counterparty_keywords", "factoring_operator_keywords"}
SOURCE_FIELDS = {
    "role",
    "adapter_family",
    "perimeter",
    "money",
    "date",
}
GROUP_FIELDS = {
    "perimeter": {
        "entity_ref",
        "party_ref",
        "currency",
        "unit",
        "direction_policy",
        "allocation_policy",
    },
    "money": {
        "decimal_separator",
        "thousands_separator",
        "reported_unit",
        "reported_increment",
    },
    "date": {"order"},
}
LANGUAGES = {"it", "en", "fr", "de", "es"}
PREFIX = "vera_workspace_open_items_intake_"
# Base64 and JSON must fit the shared MCP bridge's existing 8 MiB envelope.
SOURCE_LIMIT = 4 * 1024 * 1024


def engine_call(root: Path, request: dict[str, Any]) -> dict[str, Any]:
    """Isolation and fixed paths preserve the producer's implementation boundary."""
    completed = subprocess.run(
        [
            sys.executable,
            "-I",
            "-B",
            str(Path(__file__).with_name("native_open_items_intake_bridge.py")),
            str(root),
        ],
        input=json.dumps(request),
        text=True,
        capture_output=True,
        timeout=90,
        check=False,
    )
    if completed.returncode:
        raise ValueError(completed.stderr.strip() or "Open-item intake refused")
    return json.loads(completed.stdout)


def owner(binding: dict[str, Any]) -> list[str]:
    """Private namespaces are routing scopes, not authenticated professional identities."""
    return [
        os.environ["VERA_WORKSPACE_TENANT_ID"],
        os.environ["VERA_WORKSPACE_ACTOR_ID"],
        binding["client_id"],
        binding["engagement_id"],
        binding["run_id"],
    ]


def context(
    binding: dict[str, Any], loaded: dict[str, Any], root: Path, api: Any
) -> dict[str, Any]:
    """Exact receipts and an unresolved intent gate execution; no source-role inference."""
    if binding["workflow_id"] != "open-item-reconciliation":
        raise PermissionError("Open-item intake belongs to another workflow")
    output = Path(loaded["output_dir"])
    private = api.ui_state_directory(output, create=False)
    contract = engine_call(root, {"operation": "contract"})
    pending = any(
        "result" not in api.read_json(path)
        for path in private.glob("open-items-intake-request-*.json")
    )
    prepared = (output / "reconciliation/run_manifest.json").is_file()
    status = (
        "recovery_required"
        if pending
        else (
            "prepared"
            if prepared
            else "ready" if not any(output.iterdir()) else "recovery_required"
        )
    )
    if prepared and not pending:
        engine_call(
            root, {"operation": "read", "output": str(output / "reconciliation")}
        )
    revision = api.digest(
        [
            loaded["run"],
            loaded["input_manifest"],
            contract["implementation"],
            file_hash(Path(__file__)),
            file_hash(Path(__file__).with_name("native_open_items_intake_bridge.py")),
        ]
    )
    return {
        "output": output,
        "private": private,
        "contract": contract,
        "revision": revision,
        "status": status,
    }


def validate_fields(value: object, inputs: dict[str, Any]) -> dict[str, Any]:
    """Shape, size and receipt identities are mechanical; accounting meaning is reviewed."""
    if (
        not isinstance(value, dict)
        or set(value) - (TEXT_FIELDS | POLICY_FIELDS | KEYWORD_FIELDS | {"sources"})
        or len(json.dumps(value).encode()) > 900_000
    ):
        raise ValueError("Invalid Open-item intake fields")
    for key, item in value.items():
        if key in TEXT_FIELDS:
            if not isinstance(item, str) or len(item) > 8_000:
                raise ValueError("Open-item intake text must be bounded")
        elif key in POLICY_FIELDS:
            if type(item) is not bool:
                raise ValueError("Declare each Open-item evidence policy explicitly")
        elif key in KEYWORD_FIELDS:
            if (
                not isinstance(item, list)
                or len(item) > 100
                or any(not isinstance(word, str) or len(word) > 200 for word in item)
            ):
                raise ValueError("Invalid literal Open-item keyword choices")
        else:
            if not isinstance(item, dict) or set(item) - set(inputs):
                raise ValueError("Open-item source choice is outside this run")
            for row in item.values():
                if not isinstance(row, dict) or set(row) - SOURCE_FIELDS:
                    raise ValueError("Unexpected source decision fields")
                for field, content in row.items():
                    if field in GROUP_FIELDS:
                        if (
                            not isinstance(content, dict)
                            or set(content) - GROUP_FIELDS[field]
                            or any(
                                not isinstance(v, str) or len(v) > 1_000
                                for v in content.values()
                            )
                        ):
                            raise ValueError("Invalid unfinished source convention")
                    elif not isinstance(content, str) or len(content) > 200:
                        raise ValueError("Invalid source role or adapter choice")
    return value


def draft(
    current: dict[str, Any], binding: dict[str, Any], api: Any
) -> tuple[Path, dict[str, Any]]:
    path = current["private"] / (
        "open-items-intake-draft-" + api.digest(owner(binding)) + ".json"
    )
    if path.exists() or path.is_symlink():
        file_hash(path)
        saved = api.read_json(path)
    else:
        saved = None
    if saved:
        if saved["owner"] != owner(binding) or saved["draft_revision"] != api.digest(
            {k: v for k, v in saved.items() if k != "draft_revision"}
        ):
            raise ValueError("Open-item intake draft changed")
    return path, {
        "fields": saved["fields"] if saved else {},
        "draft_revision": saved["draft_revision"] if saved else "",
        "stale": bool(saved and saved["revision"] != current["revision"]),
    }


def compile_assumptions(
    fields: dict[str, Any], loaded: dict[str, Any], contract: dict[str, Any]
) -> dict[str, Any]:
    """Translate explicitly confirmed input handles to the producer's exact paths."""
    required = {
        "scope_year",
        "cutoff_date",
        "currency",
        "jurisdiction",
        "language",
        "document_language",
        "reviewer_ref",
        "reviewed_on",
        "sources",
    } | POLICY_FIELDS
    if not required <= set(fields):
        raise ValueError("Complete the source decisions and evidence policies first")
    if (
        not re.fullmatch(r"[0-9]{4}", fields["scope_year"])
        or not re.fullmatch(r"[A-Z]{3}", fields["currency"])
        or fields["jurisdiction"] not in {"IT", "CH-GE"}
        or fields["language"] not in LANGUAGES
        or fields["document_language"] not in LANGUAGES
    ):
        raise ValueError("Invalid declared Open-item scope")
    date.fromisoformat(fields["cutoff_date"])
    reviewed = date.fromisoformat(fields["reviewed_on"])
    if reviewed > date.today():
        raise ValueError("Source review date cannot be in the future")
    inputs = {row["binding_id"]: row for row in loaded["input_manifest"]["inputs"]}
    if set(fields["sources"]) != set(inputs) or not inputs:
        raise ValueError("Review every exact registered Open-item source")
    decisions = {}
    for identity, choice in fields["sources"].items():
        if set(choice) != SOURCE_FIELDS or any(
            set(choice[group]) != keys for group, keys in GROUP_FIELDS.items()
        ):
            raise ValueError("Complete every source convention")
        if (
            choice["role"] not in contract["roles"]
            or choice["adapter_family"] not in contract["adapters"]
        ):
            raise ValueError("Choose a maintained source role and adapter")
        path = Path(loaded["run_root"]) / inputs[identity]["execution_relative_path"]
        if file_hash(path) != inputs[identity]["sha256"]:
            raise ValueError("Selected source differs from its exact receipt")
        relative = path.relative_to(Path(loaded["context"]["input_dir"])).as_posix()
        decisions[relative] = {
            **choice,
            "reviewer_ref": fields["reviewer_ref"],
            "reviewed_on": fields["reviewed_on"],
        }
    if not any(choice["role"] == "open_items" for choice in fields["sources"].values()):
        raise ValueError("Declare the population reported as open at the cut-off")
    return {
        **{k: fields[k] for k in POLICY_FIELDS | KEYWORD_FIELDS if k in fields},
        "scope_year": fields["scope_year"],
        "cutoff_date": fields["cutoff_date"],
        "currency": fields["currency"],
        "jurisdiction": fields["jurisdiction"],
        "report_language": fields["language"],
        "document_language": fields["document_language"],
        "assurance_run_date": date.today().isoformat(),
        "reviewed_source_decisions": decisions,
        "ocr_scanned": False,
    }


def dispatch(
    tool: str,
    args: dict[str, Any],
    binding: dict[str, Any],
    loaded: dict[str, Any],
    root: Path,
    api: Any,
) -> dict[str, Any]:
    """Preserve drafts, uncertain work and public assurance without approving the case."""
    action = tool.removeprefix(PREFIX)
    if not tool.startswith(PREFIX) or action not in {
        "setup",
        "source",
        "draft_save",
        "draft_clear",
        "prepare",
    }:
        raise ValueError("Unknown Open-item intake action")
    current = context(binding, loaded, root, api)
    path, saved = draft(current, binding, api)
    inputs = {row["binding_id"]: row for row in loaded["input_manifest"]["inputs"]}
    writable = loaded["run"]["status"] == "running" and "REVIEWER" in os.environ.get(
        "VERA_WORKSPACE_ROLES", ""
    ).split(",")
    if action == "setup":
        offset = args.get("offset", 0)
        if type(offset) is not int or offset < 0:
            raise ValueError("Invalid Open-item source page")
        items = [
            {
                "id": identity,
                "title": Path(row["execution_relative_path"]).name,
                "kind": Path(row["execution_relative_path"]).suffix.lower(),
            }
            for identity, row in inputs.items()
        ]
        return {
            "work_ref": binding["work_ref"],
            "revision": current["revision"],
            "status": current["status"],
            "can_prepare": writable and current["status"] == "ready",
            "can_discard": writable,
            "items": items[offset : offset + 30],
            "total": len(items),
            "has_more": offset + 30 < len(items),
            "roles": current["contract"]["roles"],
            "adapters": current["contract"]["adapters"],
            "draft": saved,
        }
    if action == "source":
        # Exact identities and byte receipts authorize only local source viewing.
        if args["revision"] != current["revision"]:
            raise ValueError("Open-item source scope changed")
        source = inputs.get(args["input_id"])
        if source is None:
            raise PermissionError("Open-item source belongs to another run")
        source_path = Path(loaded["run_root"]) / source["execution_relative_path"]
        if file_hash(source_path) != source["sha256"]:
            raise ValueError("Open-item source changed")
        with source_path.open("rb") as stream:
            raw = stream.read(SOURCE_LIMIT + 1)
        if len(raw) > SOURCE_LIMIT:
            raise ValueError("Open this source in the registered Studio Archive folder")
        if hashlib.sha256(raw).hexdigest() != source["sha256"]:
            raise ValueError("Open-item source changed during reading")
        api.load_binding(binding)
        return {
            "input_id": args["input_id"],
            "name": source_path.name,
            "sha256": source["sha256"],
            "byte_count": len(raw),
            "encoding": "base64",
            "content": base64.b64encode(raw).decode("ascii"),
            "mime_type": (
                "application/pdf"
                if source_path.suffix.lower() == ".pdf"
                else "application/octet-stream"
            ),
        }
    if not writable:
        raise PermissionError(
            "A running Open-item run and reviewer authority are required"
        )
    with api.write_lock(current["output"]):
        loaded = api.load_binding(binding)
        current = context(binding, loaded, root, api)
        path, saved = draft(current, binding, api)
        if loaded["run"]["status"] != "running":
            raise PermissionError("Open-item run is no longer running")
        if action == "prepare":
            key = args["idempotency_key"]
            if not re.fullmatch(r"[A-Za-z0-9_-]{1,120}", key):
                raise ValueError("Invalid Open-item submission key")
            receipt = current["private"] / (
                "open-items-intake-request-"
                + api.digest([owner(binding), key])
                + ".json"
            )
            request_digest = api.digest(
                {k: v for k, v in args.items() if k != "review_ticket"}
            )
            if receipt.exists():
                prior = api.read_json(receipt)
                if prior["request_digest"] != request_digest or "result" not in prior:
                    raise ValueError("Open-item request changed or requires recovery")
                return prior["result"]
        if (
            args["revision"] != current["revision"]
            or args["expected_draft_revision"] != saved["draft_revision"]
        ):
            raise ValueError("Open-item run or draft changed")
        if action == "draft_clear":
            path.unlink(missing_ok=True)
            return {"draft_revision": "", "cleared": True}
        if current["status"] != "ready":
            raise ValueError(
                "Existing Open-item outputs or interrupted work require review or recovery"
            )
        if action == "draft_save":
            fields = validate_fields(args["fields"], inputs)
            record = {
                "owner": owner(binding),
                "revision": current["revision"],
                "fields": fields,
            }
            record["draft_revision"] = api.digest(record)
            api.atomic_json(path, record)
            return {"draft_revision": record["draft_revision"], "saved": True}
        if args.get("human_reviewed") is not True or saved["stale"]:
            raise ValueError("Renew explicit review of the complete Open-item intake")
        fields = validate_fields(saved["fields"], inputs)
        assumptions = compile_assumptions(fields, loaded, current["contract"])
        retained = {
            "request_digest": request_digest,
            "revision": current["revision"],
            "owner": owner(binding),
            "fields": fields,
        }
        api.atomic_json(receipt, retained)
        result = engine_call(
            root,
            {
                "operation": "prepare",
                "context": str(loaded["context_path"]),
                "assumptions": assumptions,
                "title": fields.get("title"),
                "narrative": fields.get("narrative", ""),
                "language": fields["language"],
            },
        )
        api.load_binding(binding)
        retained["result"] = result
        api.atomic_json(receipt, retained)
        return result
