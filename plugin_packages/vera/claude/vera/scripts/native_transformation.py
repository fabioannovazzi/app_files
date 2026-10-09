"""App-only authoring and review over the maintained synthetic transformation store.

Exact byte identities, owner scope, CAS and receipts enforce auditability.
They never infer legal conclusions, approval, statutory terms or real-mandate readiness.
"""

from __future__ import annotations

import base64
import hashlib
import json
import mimetypes
import os
import re
import subprocess
import sys
from pathlib import Path
from typing import Any

__all__ = ["dispatch"]

LIMIT = 2_000_000
PREFIX = "vera_workspace_transformation_"
ACTIONS = {
    "update_case",
    "put",
    "branch",
    "import_evidence",
    "submit",
    "review",
    "export",
}
EMPTY = {
    key: ""
    for key in (
        "operation",
        "actor",
        "record_kind",
        "record_json",
        "branch_id",
        "proposal_digest",
        "decision",
        "reason",
    )
}


def bounded(value: Any) -> str:
    """Refuse incomplete whole records rather than sampling review evidence."""
    raw = json.dumps(value, ensure_ascii=False, sort_keys=True, allow_nan=False)
    if len(raw.encode()) > LIMIT:
        raise ValueError("Complete transformation record exceeds native limit")
    return raw


def stamp(value: Any) -> str:
    """Bind literal decisions and exact retries to complete current records."""
    return hashlib.sha256(bounded(value).encode()).hexdigest()


def regular(path: Path) -> None:
    """Reject linked paths before inspecting private owner-selected files."""
    if any(p.is_symlink() for p in (path, *path.parents)):
        raise ValueError("Transformation paths cannot use symbolic links")
    if (
        path.exists()
        and not path.is_dir()
        and (not path.is_file() or path.stat().st_nlink != 1)
    ):
        raise ValueError("Transformation files must be regular and single-link")


def read(path: Path) -> dict:
    regular(path)
    if path.stat().st_size > LIMIT:
        raise ValueError("Transformation JSON exceeds whole-record limit")
    value = json.loads(path.read_bytes())
    if not isinstance(value, dict):
        raise ValueError("Transformation JSON must be an object")
    return value


def files(root: Path) -> dict:
    """Fingerprint all public producer state, excluding private native bookkeeping."""
    regular(root)
    result = {}
    byte_count = 0
    for path in sorted(root.rglob("*")):
        relative = path.relative_to(root)
        if relative.parts[0] == ".native-workspace":
            continue
        regular(path)
        if path.is_file():
            byte_count += path.stat().st_size
            if byte_count > 40_000_000 or len(result) >= 2000:
                raise ValueError(
                    "Complete synthetic store exceeds bounded native inspection"
                )
            with path.open("rb") as stream:
                result[relative.as_posix()] = hashlib.file_digest(
                    stream, "sha256"
                ).hexdigest()
    bounded(result)
    return result


def bindings() -> tuple[dict, list]:
    """Only trusted host configuration may select exact existing synthetic cases."""
    owner = {
        key: os.environ.get("VERA_WORKSPACE_" + key.upper(), "")
        for key in ("tenant_id", "actor_id")
    }
    if not all(owner.values()):
        raise PermissionError(
            "Open transformations through the owned local MCP service"
        )
    filename = os.environ.get("VERA_TRANSFORMATION_WORKSPACE_BINDINGS")
    if not filename:
        return owner, []
    config = read(Path(filename))
    if any(config.get(key) != value for key, value in owner.items()):
        raise PermissionError("Transformation binding belongs to another host actor")
    rows = config["bindings"]
    if not isinstance(rows, list) or len(rows) > 200:
        raise ValueError("Transformation binding supports at most 200 exact runs")
    refs = [row["work_ref"] for row in rows]
    if len(set(refs)) != len(refs) or any(
        not isinstance(ref, str) or not re.fullmatch(r"[A-Za-z0-9_-]{1,120}", ref)
        for ref in refs
    ):
        raise ValueError("Transformation references must be unique bounded identifiers")
    return owner, rows


def connection(row: dict, module: Path) -> tuple[Path, Path]:
    """Only explicitly bound synthetic stores outside Git/client engagements qualify."""
    workspace = Path(row["case_dir"])
    regular(workspace)
    workspace = workspace.resolve()
    if (
        not Path(row["case_dir"]).is_absolute()
        or any((p / ".git").exists() for p in (workspace, *workspace.parents))
        or {"public", "published", "static", "plugin_packages", "engagements"}
        & {p.lower() for p in workspace.parts}
        or workspace in {Path(workspace.anchor), Path.home().resolve()}
        or row.get("synthetic_only") is not True
    ):
        raise ValueError(
            "Use a dedicated absolute synthetic case outside Git and client engagements"
        )
    if not workspace.is_dir() or not (workspace / "history").is_dir():
        raise ValueError(
            "Initialize the synthetic case with the unchanged public helper first"
        )
    sources = row.get("sources", [])
    if not isinstance(sources, list) or len(sources) > 200:
        raise ValueError("Bind at most 200 exact synthetic source files")
    refs = [item["source_ref"] for item in sources]
    if len(set(refs)) != len(refs):
        raise ValueError("Duplicate synthetic source binding")
    for item in sources:
        path = Path(item["path"])
        regular(path)
        if (
            not path.is_absolute()
            or not path.resolve().is_relative_to(workspace / "synthetic-inputs")
            or not path.is_file()
            or path.stat().st_size > 20_000_000
            or not re.fullmatch(r"[A-Za-z0-9_-]{1,120}", item["source_ref"])
        ):
            raise ValueError(
                "Bind an exact inert file in this case's synthetic-inputs directory"
            )
    return workspace, workspace


def producer(
    module: Path, workspace: Path, row: dict, action: str, **arguments: Any
) -> dict:
    """Execute only fixed public producer calls in an isolated Python process."""
    request = {
        "module": str(module),
        "workspace": str(workspace),
        "case_id": row["case_id"],
        "sources": row.get("sources", []),
        "action": action,
        **arguments,
    }
    result = subprocess.run(
        [
            sys.executable,
            "-I",
            "-B",
            str(Path(__file__).with_name("native_transformation_bridge.py")),
        ],
        input=bounded(request),
        text=True,
        capture_output=True,
        timeout=120,
        check=False,
    )
    if result.returncode:
        raise ValueError(
            result.stderr.strip().splitlines()[-1]
            if result.stderr.strip()
            else "Transformation producer failed"
        )
    value = json.loads(result.stdout)
    bounded(value)
    return value


def snapshot(owner: dict, row: dict, module: Path) -> tuple[Path, Path, dict]:
    """Expose complete records with their maintained current validation result."""
    workspace, run = connection(row, module)
    before = files(workspace)
    data = producer(module, workspace, row, "snapshot")
    if data["state"]["case"]["id"] != row["case_id"] or before != files(workspace):
        raise ValueError("Transformation changed during native inspection")
    implementation = {
        section + "/" + key: value
        for section in ("scripts", "references", "skills")
        for key, value in files(module / section).items()
        if Path(key).suffix in {".py", ".json", ".md"}
    }
    for path in (
        Path(__file__),
        Path(__file__).with_name("native_transformation_bridge.py"),
        Path(__file__).with_name("native_transformation_author.py"),
        Path(__file__).with_name("native_transformation_initial.py"),
        Path(__file__).with_name("native_transformation_initial_bridge.py"),
        Path(__file__).parents[1] / "ui/transformation.js",
    ):
        regular(path)
        implementation[path.name] = hashlib.sha256(path.read_bytes()).hexdigest()
    revision = stamp(
        {
            "owner": owner,
            "binding": row,
            "files": before,
            "implementation": implementation,
        }
    )
    return (
        workspace,
        run,
        {
            "work_ref": row["work_ref"],
            "revision": revision,
            "source_ref": revision,
            "data": {"selection": {"source_ref": revision}, **data},
        },
    )


def check_fields(value: Any) -> None:
    """Validate literal shapes; the public store owns all domain/branch checks."""
    if (
        not isinstance(value, dict)
        or set(value) != set(EMPTY)
        or any(not isinstance(v, str) for v in value.values())
        or value["operation"] not in ACTIONS | {""}
        or value["decision"] not in {"", "approve", "request_changes"}
        or len(value["record_json"].encode()) > 1_000_000
        or any(len(value[k]) > 4000 for k in value if k != "record_json")
    ):
        raise ValueError("Invalid literal synthetic transformation fields")


def dispatch(tool: str, args: dict, module: Path, api: Any) -> dict:
    """Serve exact app-only review without relocating authoritative producer state."""
    if tool.startswith("vera_workspace_transformation_author_"):
        from native_transformation_author import dispatch as author_dispatch

        return author_dispatch(tool, args, module, api)
    from native_transformation_initial import dispatch as initial_dispatch
    from native_transformation_initial import (
        initial_option,
    )

    if tool.startswith("vera_workspace_transformation_initial_"):
        return initial_dispatch(tool, args, module, api)
    owner, rows = bindings()
    action = tool.removeprefix(PREFIX)
    if action == "catalogue":
        works = []
        for row in rows:
            option = initial_option(owner, row, module)
            if option is not None:
                works.append(option)
                continue
            _, _, page = snapshot(owner, row, module)
            data = page["data"]
            works.append(
                {
                    "work_ref": row["work_ref"],
                    "case_id": data["state"]["case"]["id"],
                    "objective": data["state"]["case"]["purpose"],
                    "case_revision": data["state"]["revision"],
                    "synthetic_only": True,
                }
            )
        return {
            "works": works,
            "configured": bool(rows),
            "workspace_scope": "synthetic_prototype",
            "initial_authoring_available": any(
                r.get("initialize") is True for r in rows
            ),
            "bound_case_authoring_available": True,
            "model_context_transferred": False,
        }
    row = next((r for r in rows if r["work_ref"] == args["work_ref"]), None)
    if row is None:
        raise PermissionError("Unknown owned transformation run")
    if initial_option(owner, row, module) is not None:
        raise ValueError(
            "Use initial setup or recover uncertain creation before ordinary case work"
        )
    workspace, run = connection(row, module)
    with api.write_lock(workspace / "native-transformation-marker"):
        _, _, page = snapshot(owner, row, module)
        directory = (
            workspace
            / ".native-workspace"
            / ("transformation-" + stamp({"owner": owner, "work_ref": row["work_ref"]}))
        )
        regular(directory)
        directory.mkdir(parents=True, exist_ok=True, mode=0o700)
        draft_path = directory / "draft.json"
        current = (
            read(draft_path)
            if draft_path.is_file()
            else {"generation": 0, "revision": "", "fields": dict(EMPTY)}
        )
        check_fields(current["fields"])
        operations_path = directory / "operations.json"
        operations = read(operations_path) if operations_path.is_file() else {}
        for key, item in operations.items():
            if (
                item["status"] not in {"pending", "completed"}
                or item["fingerprint"] != stamp(item["request"])
                or item["request"]["idempotency_key"] != key
            ):
                raise ValueError("Transformation intent integrity mismatch")
            if item["status"] == "completed" and item["receipt_sha256"] != stamp(
                item["result"]
            ):
                raise ValueError("Transformation receipt integrity mismatch")
        pending = [
            key for key, item in operations.items() if item["status"] == "pending"
        ]
        can_write = "REVIEWER" in os.environ.get("VERA_WORKSPACE_ROLES", "").split(",")
        if action == "setup":
            page.update(
                fields=current["fields"],
                draft_revision=stamp(current),
                draft_stale=bool(
                    current["revision"] and current["revision"] != page["revision"]
                ),
                confirmation_restored=False,
                can_write=can_write,
                pending_operations=pending,
                initial_authoring_available=False,
                bound_case_authoring_available=True,
                sent_or_published=False,
            )
            return json.loads(bounded(page))
        if action == "artifact":
            if any(args[k] != page[k] for k in ("revision", "source_ref")):
                raise ValueError("Transformation artifact scope is stale")
            item = next(
                (
                    x
                    for x in page["data"]["artifacts"]
                    if x["name"] == args["artifact_ref"]
                ),
                None,
            )
            if item is None:
                raise PermissionError(
                    "Select an exact verified synthetic evidence or dossier artifact"
                )
            path = run / item["name"]
            regular(path)
            if (
                not path.resolve().is_relative_to(run)
                or path.stat().st_size > 1_000_000
            ):
                raise ValueError(
                    "Native artifact exceeds complete bounded download limit"
                )
            content = path.read_bytes()
            if hashlib.sha256(content).hexdigest() != item["sha256"]:
                raise ValueError("Transformation artifact changed")
            return {
                "name": path.name,
                "sha256": item["sha256"],
                "mime_type": mimetypes.guess_type(path.name)[0]
                or "application/octet-stream",
                "base64": base64.b64encode(content).decode(),
            }
        if not can_write:
            raise PermissionError(
                "Transformation writes require this host's reviewer authority"
            )
        fingerprint = stamp(args)
        if action == "execute" and args["idempotency_key"] in operations:
            previous = operations[args["idempotency_key"]]
            if previous["fingerprint"] != fingerprint:
                raise ValueError("Changed transformation retry")
            if previous["status"] != "completed":
                raise ValueError(
                    "Uncertain transformation write requires specialist recovery"
                )
            if previous["after_revision"] != page["revision"]:
                raise ValueError("Transformation changed after the retained operation")
            return previous["result"]
        if any(args[k] != page[k] for k in ("revision", "source_ref")):
            raise ValueError("Transformation scope changed; reopen the exact run")
        if args["expected_draft_revision"] != stamp(current):
            raise ValueError("Transformation fields changed in another window")
        if action in {"draft_save", "draft_clear"}:
            if action == "draft_clear" and args.get("confirmed") is not True:
                raise ValueError("Confirm discarding only private unfinished fields")
            fields = dict(EMPTY) if action == "draft_clear" else args["fields"]
            check_fields(fields)
            next_draft = {
                "generation": current["generation"] + 1,
                "revision": "" if action == "draft_clear" else page["revision"],
                "fields": fields,
            }
            api.atomic_json(draft_path, next_draft)
            return {
                "saved": True,
                "draft_revision": stamp(next_draft),
                "confirmation_restored": False,
            }
        if action != "execute":
            raise ValueError("Unsupported transformation native action")
        if pending:
            raise ValueError(
                "Uncertain transformation write requires specialist recovery"
            )
        fields = args["fields"]
        check_fields(fields)
        if (
            fields != current["fields"]
            or current["revision"] != page["revision"]
            or args.get("confirmed") is not True
        ):
            raise ValueError("Confirm the exact current saved transformation fields")
        operation = fields["operation"]
        if operation not in ACTIONS:
            raise ValueError("Choose the transformation operation")
        if operation != "export" and not fields["actor"].strip():
            raise ValueError("Supply the actual synthetic operator attribution")
        if operation == "review" and (
            not fields["branch_id"]
            or not fields["proposal_digest"]
            or not fields["decision"]
            or not fields["reason"].strip()
        ):
            raise ValueError(
                "Supply the exact submitted branch digest and explicit synthetic decision"
            )
        key = args["idempotency_key"]
        if not isinstance(key, str) or not re.fullmatch(r"[A-Za-z0-9_.:-]{1,120}", key):
            raise ValueError("Invalid transformation operation key")
        intent = {
            "status": "pending",
            "fingerprint": fingerprint,
            "request": args,
            "before_revision": page["revision"],
        }
        operations[key] = intent
        bounded(operations)
        api.atomic_json(operations_path, operations)
        produced = producer(
            module,
            workspace,
            row,
            operation,
            fields=fields,
            expected_files=files(workspace),
        )
        _, _, after = snapshot(owner, row, module)
        result = {
            "saved": True,
            "operation": operation,
            "work_ref": row["work_ref"],
            "revision": after["revision"],
            "result": produced,
            "sent_or_published": False,
            "model_context_transferred": False,
        }
        intent.update(
            status="completed",
            after_revision=after["revision"],
            result=result,
            receipt_sha256=stamp(result),
        )
        bounded(operations)
        api.atomic_json(operations_path, operations)
        return result
