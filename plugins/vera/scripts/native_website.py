"""App-only review over the maintained private professional-site workspace.

Exact byte identities, owner scope, CAS and receipts enforce auditability.
They never assess claims, design a site, infer approval or publish content.
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
PREFIX = "vera_workspace_website_"
ACTIONS = {
    "validate_site",
    "review",
    "package_preview",
    "package_release",
    "validate_run",
    "sites_preview_binding",
    "sites_release_binding",
}
SCOPES = {"identity_and_claims", "responsive_preview", "publication_destination"}
EMPTY = {"operation": "", "reviewer": "", "scope": "", "decision": "", "note": ""}


def bounded(value: Any) -> str:
    """Refuse incomplete whole records rather than sampling review evidence."""
    raw = json.dumps(value, ensure_ascii=False, sort_keys=True, allow_nan=False)
    if len(raw.encode()) > LIMIT:
        raise ValueError("Complete website record exceeds native limit")
    return raw


def stamp(value: Any) -> str:
    """Bind literal decisions and exact retries to complete current records."""
    return hashlib.sha256(bounded(value).encode()).hexdigest()


def regular(path: Path) -> None:
    """Reject linked paths before inspecting private owner-selected files."""
    if any(p.is_symlink() for p in (path, *path.parents)):
        raise ValueError("Website paths cannot use symbolic links")
    if (
        path.exists()
        and not path.is_dir()
        and (not path.is_file() or path.stat().st_nlink != 1)
    ):
        raise ValueError("Website files must be regular and single-link")


def read(path: Path) -> dict:
    regular(path)
    if path.stat().st_size > LIMIT:
        raise ValueError("Website JSON exceeds whole-record limit")
    value = json.loads(path.read_bytes())
    if not isinstance(value, dict):
        raise ValueError("Website JSON must be an object")
    return value


def files(root: Path) -> dict:
    """Fingerprint all public producer state, excluding private native bookkeeping."""
    regular(root)
    result = {}
    for path in sorted(root.rglob("*")):
        relative = path.relative_to(root)
        if relative.parts[0] == ".native-workspace":
            continue
        regular(path)
        if path.is_file():
            with path.open("rb") as stream:
                result[relative.as_posix()] = hashlib.file_digest(
                    stream, "sha256"
                ).hexdigest()
    bounded(result)
    return result


def bindings() -> tuple[dict, list]:
    """Only trusted host configuration may select existing studio-wide runs."""
    owner = {
        key: os.environ.get("VERA_WORKSPACE_" + key.upper(), "")
        for key in ("tenant_id", "actor_id")
    }
    if not all(owner.values()):
        raise PermissionError("Open websites through the owned local MCP service")
    filename = os.environ.get("VERA_WEBSITE_WORKSPACE_BINDINGS")
    if not filename:
        return owner, []
    config = read(Path(filename))
    if any(config.get(key) != value for key, value in owner.items()):
        raise PermissionError("Website binding belongs to another host actor")
    rows = config["bindings"]
    if not isinstance(rows, list) or len(rows) > 200:
        raise ValueError("Website binding supports at most 200 exact runs")
    refs = [row["work_ref"] for row in rows]
    if len(set(refs)) != len(refs) or any(
        not isinstance(ref, str) or not re.fullmatch(r"[A-Za-z0-9_-]{1,120}", ref)
        for ref in refs
    ):
        raise ValueError("Website references must be unique bounded identifiers")
    return owner, rows


def connection(row: dict, module: Path) -> tuple[Path, Path]:
    """Preserve the producer's private studio workspace and manifest identity."""
    workspace = Path(row["workspace"])
    regular(workspace)
    workspace = workspace.resolve()
    if (
        not Path(row["workspace"]).is_absolute()
        or any((p / ".git").exists() for p in (workspace, *workspace.parents))
        or {"public", "published", "static", "plugin_packages", "engagements"}
        & {p.lower() for p in workspace.parts}
    ):
        raise ValueError(
            "Use an absolute private studio website workspace outside Git and client engagements"
        )
    if workspace == Path(workspace.anchor) or workspace == Path.home().resolve():
        raise ValueError("Use a dedicated website workspace")
    if not re.fullmatch(r"[0-9]{8}T[0-9]{6}Z-[0-9a-f]{10}", row["run_id"]):
        raise ValueError("Invalid maintained website run ID")
    manifest = read(workspace / ".presenza-digitale-studio.json")
    if (
        manifest["schema_version"] != 1
        or manifest["workspace_id"] != row["workspace_id"]
    ):
        raise PermissionError("Website workspace identity changed")
    run = workspace / "runs" / row["run_id"]
    regular(run)
    if not run.is_dir():
        raise ValueError("Selected website run does not exist")
    return workspace, run


def producer(
    module: Path, workspace: Path, row: dict, action: str, **arguments: Any
) -> dict:
    """Execute only fixed public producer calls in an isolated Python process."""
    request = {
        "module": str(module),
        "workspace": str(workspace),
        "run_id": row["run_id"],
        "action": action,
        **arguments,
    }
    result = subprocess.run(
        [
            sys.executable,
            "-I",
            "-B",
            str(Path(__file__).with_name("native_website_bridge.py")),
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
            else "Website producer failed"
        )
    value = json.loads(result.stdout)
    bounded(value)
    return value


def snapshot(owner: dict, row: dict, module: Path) -> tuple[Path, Path, dict]:
    """Expose complete records with their maintained current validation result."""
    workspace, run = connection(row, module)
    before = files(workspace)
    data = producer(module, workspace, row, "snapshot")
    if data["run_id"] != row["run_id"] or before != files(workspace):
        raise ValueError("Website changed during native inspection")
    implementation = {
        section + "/" + key: value
        for section in ("scripts", "schemas", "skills")
        for key, value in files(module / section).items()
        if Path(key).suffix in {".py", ".json", ".md"}
    }
    for path in (
        Path(__file__),
        Path(__file__).with_name("native_website_bridge.py"),
        Path(__file__).parents[1] / "ui/website.js",
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
    """Check literal shape only; site meaning and decisions remain human/model-led."""
    if (
        not isinstance(value, dict)
        or set(value) != set(EMPTY)
        or any(not isinstance(v, str) for v in value.values())
    ):
        raise ValueError("Invalid literal website fields")
    if (
        value["operation"] not in ACTIONS | {""}
        or value["scope"] not in SCOPES | {""}
        or value["decision"] not in {"", "accepted", "returned", "rejected"}
        or len(value["reviewer"]) > 200
        or len(value["note"]) > 2000
    ):
        raise ValueError("Invalid website operation, review scope or field length")


def dispatch(tool: str, args: dict, module: Path, api: Any) -> dict:
    """Serve exact app-only review without relocating authoritative producer state."""
    owner, rows = bindings()
    action = tool.removeprefix(PREFIX)
    if action == "catalogue":
        works = []
        for row in rows:
            _, _, page = snapshot(owner, row, module)
            data = page["data"]
            works.append(
                {
                    "work_ref": row["work_ref"],
                    "studio": data["studio"],
                    "run_id": data["run_id"],
                    "objective": data["intake"]["objective"],
                    "status": data["validation"]["status"],
                }
            )
        return {
            "works": works,
            "configured": bool(rows),
            "workspace_scope": "studio_wide",
            "initial_authoring_available": False,
            "model_context_transferred": False,
        }
    row = next((r for r in rows if r["work_ref"] == args["work_ref"]), None)
    if row is None:
        raise PermissionError("Unknown owned website run")
    workspace, run = connection(row, module)
    with api.write_lock(workspace / "native-website-marker"):
        _, _, page = snapshot(owner, row, module)
        directory = (
            workspace
            / ".native-workspace"
            / ("website-" + stamp({"owner": owner, "work_ref": row["work_ref"]}))
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
                raise ValueError("Website intent integrity mismatch")
            if item["status"] == "completed" and item["receipt_sha256"] != stamp(
                item["result"]
            ):
                raise ValueError("Website receipt integrity mismatch")
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
                sent_or_published=False,
            )
            return json.loads(bounded(page))
        if action == "artifact":
            if any(args[k] != page[k] for k in ("revision", "source_ref")):
                raise ValueError("Website artifact scope is stale")
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
                    "Select an exact verified site, package or browser artifact"
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
                raise ValueError("Website artifact changed")
            return {
                "name": path.name,
                "sha256": item["sha256"],
                "mime_type": mimetypes.guess_type(path.name)[0]
                or "application/octet-stream",
                "base64": base64.b64encode(content).decode(),
            }
        if not can_write:
            raise PermissionError(
                "Website writes require this host's reviewer authority"
            )
        fingerprint = stamp(args)
        if action == "execute" and args["idempotency_key"] in operations:
            previous = operations[args["idempotency_key"]]
            if previous["fingerprint"] != fingerprint:
                raise ValueError("Changed website retry")
            if previous["status"] != "completed":
                raise ValueError("Uncertain website write requires specialist recovery")
            if previous["after_revision"] != page["revision"]:
                raise ValueError("Website changed after the retained operation")
            return previous["result"]
        if any(args[k] != page[k] for k in ("revision", "source_ref")):
            raise ValueError("Website scope changed; reopen the exact run")
        if args["expected_draft_revision"] != stamp(current):
            raise ValueError("Website fields changed in another window")
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
            raise ValueError("Unsupported website native action")
        if pending:
            raise ValueError("Uncertain website write requires specialist recovery")
        fields = args["fields"]
        check_fields(fields)
        if (
            fields != current["fields"]
            or current["revision"] != page["revision"]
            or args.get("confirmed") is not True
        ):
            raise ValueError("Confirm the exact current saved website fields")
        operation = fields["operation"]
        if operation not in ACTIONS:
            raise ValueError("Choose the website operation")
        if operation == "review" and (
            not fields["reviewer"].strip()
            or fields["scope"] not in SCOPES
            or not fields["decision"]
        ):
            raise ValueError("Supply the actual reviewer, exact scope and decision")
        key = args["idempotency_key"]
        if not isinstance(key, str) or not re.fullmatch(r"[A-Za-z0-9_.:-]{1,120}", key):
            raise ValueError("Invalid website operation key")
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
