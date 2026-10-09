"""Bounded navigation over the maintained owner-private Studio Archive."""

from __future__ import annotations

import hashlib
import json
import os
import re
import stat
import sys
import tempfile
from pathlib import Path
from typing import Any

__all__ = ["catalogue", "resolve_binding", "archive_action", "lifecycle_action"]

PAGE_SIZE = 30
WORK_REF = re.compile(r"studio-([0-9a-f]{24})_([0-9a-f]{24})_([0-9a-f]{24})")


def archive_module(root: Path) -> Any:
    """Use the existing session owner, scope checks and portable ledger."""
    sys.path.insert(0, str(root / "scripts"))
    import archive_core

    return archive_core


def page(rows: list[dict[str, Any]], args: dict[str, Any]) -> dict[str, Any]:
    """Bound presentation only; selection and scope remain explicit."""
    offset = args.get("offset", 0)
    if not isinstance(offset, int) or isinstance(offset, bool) or offset < 0:
        raise ValueError("Invalid archive page offset")
    return {
        "rows": rows[offset : offset + PAGE_SIZE],
        "offset": offset,
        "total": len(rows),
        "has_more": offset + PAGE_SIZE < len(rows),
    }


def client_root(core: Any, client_id: str) -> Path:
    """Resolve the stable ID inside this session's configured archive only."""
    return Path(
        core.get_studio_client_folder(client_id)["client_folder"]["client_root"]
    )


def work_ref(client_id: str, engagement_id: str, run_id: str) -> str:
    """Carry exact portable identities, never a browser-supplied filesystem path."""
    return "studio-" + "_".join(
        value.split("_", 1)[1] for value in (client_id, engagement_id, run_id)
    )


def fingerprint(value: Any) -> str:
    """Bind exact displayed identities and receipts, without semantic decisions."""
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, ensure_ascii=False).encode()
    ).hexdigest()


def reviewer() -> bool:
    """Honor the configured local actor's explicit viewer override."""
    return "REVIEWER" in os.environ.get("VERA_WORKSPACE_ROLES", "").split(",")


def engagement_scope(
    core: Any, client_id: str, engagement_id: str
) -> tuple[Path, dict[str, Any]]:
    """Resolve one current owned customer and matching durable engagement."""
    folder = client_root(core, client_id)
    engagement = core.ledger.load_engagement_manifest(folder, engagement_id)
    if engagement["client_id"] != client_id:
        raise PermissionError("Engagement does not belong to the selected client")
    return folder, engagement


def preparation_catalogue(root: Path, args: dict[str, Any]) -> dict[str, Any]:
    """List verified imported receipts and maintained workflow choices for the app."""
    core = archive_module(root)
    folder, engagement = engagement_scope(
        core, args["client_id"], args["engagement_id"]
    )
    receipts = core.ledger.list_inputs(folder, args["engagement_id"])
    from native_archive_imports import audit_engagement

    imports = audit_engagement(core, folder, args["engagement_id"])
    # Artifact eligibility is the public ledger's mechanical receipt/byte gate,
    # not a choice of document relevance. Operators choose every actual reuse.
    upstream, unavailable, source_revisions = [], [], []
    for loaded in core.ledger.list_runs(
        folder, args["engagement_id"], verify_inputs=False
    ):
        run = loaded["run"]
        if run["status"] not in {"ready_for_review", "completed"}:
            continue
        try:
            core.ledger.load_run(folder, args["engagement_id"], run["run_id"])
            manifest = core.ledger.validate_run_artifacts(
                folder, args["engagement_id"], run["run_id"]
            )
        except core.ledger.LedgerError as exc:
            unavailable.append(
                {"run_id": run["run_id"], "label": run["label"], "reason": str(exc)}
            )
            continue
        source_revisions.append([run, manifest["content_sha256"]])
        for artifact in manifest["artifacts"]:
            upstream.append(
                {
                    **{
                        k: artifact[k]
                        for k in (
                            "artifact_id",
                            "path",
                            "purpose",
                            "audience",
                            "media_type",
                            "sha256",
                            "byte_count",
                        )
                    },
                    "run_id": run["run_id"],
                    "run_label": run["label"],
                    "id": fingerprint([run["run_id"], artifact["artifact_id"]]),
                }
            )
    if len(upstream) > 10_000:
        raise ValueError("Archive artifact catalogue exceeds native limit")
    artifact_page = page(upstream, {"offset": args.get("artifact_offset", 0)})
    result = page(
        [
            {
                key: row[key]
                for key in ("input_id", "original_name", "role", "byte_count")
            }
            for row in receipts
        ],
        args,
    )
    return {
        **result,
        "client_id": args["client_id"],
        "engagement_id": args["engagement_id"],
        "engagement_label": engagement["label"],
        "engagement_status": engagement["status"],
        "scope_revision": fingerprint(
            [engagement, receipts, source_revisions, unavailable]
        ),
        "upstream_rows": artifact_page["rows"],
        "upstream_total": artifact_page["total"],
        "upstream_offset": artifact_page["offset"],
        "upstream_has_more": artifact_page["has_more"],
        "upstream_unavailable": unavailable,
        "can_prepare": reviewer()
        and engagement["status"] == "open"
        and not imports["recovery_required"],
        "import_recovery_required": imports["recovery_required"],
        "workflow_choices": list(core.VERA_CLIENT_WORKFLOW_IDS),
    }


def catalogue(root: Path, args: dict[str, Any]) -> dict[str, Any]:
    """Project directory labels and lifecycle; private contacts stay in the engine."""
    core = archive_module(root)
    clients = core.list_studio_clients()
    base = {
        "mode": "studio-archive",
        "works": [],
        "configured": clients["configured"],
        "setup_required": not clients["configured"],
        "refresh_required": clients["scope_configuration_changed"],
        "clients": [],
        "engagements": [],
        "level": "clients",
    }
    if not clients["configured"]:
        return {**base, **page([], args)}
    selected_client = args.get("client_id")
    selected_engagement = args.get("engagement_id")
    if selected_engagement and not selected_client:
        raise ValueError("Select the exact client before its engagement")
    if not selected_client:
        rows = [
            {
                key: row.get(key)
                for key in ("client_id", "display_name", "registration_status")
            }
            for row in clients["clients"]
        ]
        result = page(rows, args)
        return {**base, **result, "clients": result["rows"]}
    selected = next(
        (row for row in clients["clients"] if row["client_id"] == selected_client), None
    )
    if selected is None:
        raise PermissionError("Client is not registered in this archive session")
    folder = client_root(core, selected_client)
    engagements = core.ledger.list_engagements(folder, selected_client)
    base.update(client_id=selected_client, client_label=selected["display_name"])
    if not selected_engagement:
        rows = [
            {
                key: row[key]
                for key in ("engagement_id", "label", "status", "created_at")
            }
            for row in engagements
        ]
        result = page(rows, args)
        return {
            **base,
            **result,
            "level": "engagements",
            "engagements": result["rows"],
            "scope_revision": fingerprint([selected_client, engagements]),
            "can_create_engagement": reviewer() and not base["refresh_required"],
        }
    engagement = next(
        (row for row in engagements if row["engagement_id"] == selected_engagement),
        None,
    )
    if engagement is None:
        raise PermissionError("Engagement does not belong to the selected client")
    rows = []
    for loaded in core.ledger.list_runs(
        folder, selected_engagement, verify_inputs=False
    ):
        run = loaded["run"]
        rows.append(
            {
                **{
                    key: run[key] for key in ("run_id", "label", "status", "created_at")
                },
                "client_id": selected_client,
                "client_label": selected["display_name"],
                "engagement_id": selected_engagement,
                "engagement_label": engagement["label"],
                "workflow": run["workflow_id"],
                "scope_revision": fingerprint(run),
                "work_ref": work_ref(
                    selected_client, selected_engagement, run["run_id"]
                ),
            }
        )
    result = page(rows, args)
    for row in result["rows"]:
        try:
            core.ledger.load_run(folder, selected_engagement, row["run_id"])
            row["inputs_valid"] = True
        except core.ledger.LedgerError:
            row["inputs_valid"] = False
        row["can_start"] = (
            reviewer()
            and engagement["status"] == "open"
            and row["status"] in {"prepared", "failed"}
            and row["inputs_valid"]
        )
        row["closure_available"] = (
            row["inputs_valid"]
            and row["status"] in {"running", "ready_for_review", "completed"}
            and row["workflow"] in core.VERA_CLIENT_WORKFLOW_IDS
        )
    return {
        **base,
        **result,
        "level": "runs",
        "works": result["rows"],
        "engagement_id": selected_engagement,
        "engagement_label": engagement["label"],
        "engagement_status": engagement["status"],
        "can_prepare": reviewer() and engagement["status"] == "open",
    }


def create_engagement_once(core: Any, args: dict[str, Any]) -> dict[str, Any]:
    """Retain one request outcome; interrupted creation refuses a second write."""
    folder = client_root(core, args["client_id"])
    directory = folder / core.ledger.LEDGER_DIRECTORY / ".native-workspace"
    if any(path.is_symlink() for path in (directory, *directory.parents)):
        raise ValueError("Native archive receipts cannot use symbolic links")
    request = {
        **args,
        "actor": os.environ["VERA_WORKSPACE_ACTOR_ID"],
        "tenant": os.environ["VERA_WORKSPACE_TENANT_ID"],
    }
    identity = fingerprint(
        [request["actor"], request["tenant"], args["idempotency_key"]]
    )
    path = directory / ("engagement-" + identity + ".json")
    if path.exists() or path.is_symlink():
        info = path.lstat()
        if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1 or info.st_size > 16000:
            raise ValueError("Invalid native archive request receipt")
        receipt = json.loads(path.read_bytes())
        if receipt["request"] != request:
            raise ValueError(
                "Idempotency key belongs to a different engagement request"
            )
        if "engagement" not in receipt:
            raise ValueError(
                "Engagement creation outcome is uncertain; verify the archive before another request"
            )
        stored = core.ledger.load_engagement_manifest(
            folder, receipt["engagement"]["engagement_id"]
        )
        if stored != receipt["engagement"]:
            raise ValueError("Created engagement has changed; reopen the archive")
        return {
            "status": "already_created",
            "client_id": args["client_id"],
            "engagement_id": stored["engagement_id"],
            "label": stored["label"],
        }
    current = core.ledger.list_engagements(folder, args["client_id"])
    if fingerprint([args["client_id"], current]) != args["scope_revision"]:
        raise ValueError("Archive directory changed; reopen the selected client")
    label = args["label"]
    if not isinstance(label, str) or not label.strip() or len(label) > 160:
        raise ValueError("Provide an engagement label of at most 160 characters")
    # Preserve the maintained label contract before allocating a durable intent.
    core._normalize_engagement_label(label)
    directory.mkdir(mode=0o700, exist_ok=True)
    try:
        descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    except FileExistsError as exc:
        raise ValueError(
            "Engagement request is already in progress; reopen the archive"
        ) from exc
    with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
        json.dump({"request": request}, stream, ensure_ascii=False)
        stream.flush()
        os.fsync(stream.fileno())
    created = core.create_studio_client_engagement(args["client_id"], label)
    # The public projection adds imports; retain the actual ledger manifest only.
    stored = core.ledger.load_engagement_manifest(
        folder, created["engagement"]["engagement_id"]
    )
    # A failed final receipt leaves the durable intent and prevents duplicate creation.
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w", encoding="utf-8", dir=directory, delete=False
        ) as stream:
            temporary = Path(stream.name)
            json.dump(
                {"request": request, "engagement": stored},
                stream,
                ensure_ascii=False,
            )
            stream.flush()
            os.fsync(stream.fileno())
        temporary.replace(path)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)
    return {
        "status": "created",
        "client_id": args["client_id"],
        "engagement_id": stored["engagement_id"],
        "label": stored["label"],
    }


def lifecycle_action(root: Path, tool: str, args: dict[str, Any]) -> dict[str, Any]:
    """Call maintained lifecycle APIs for exact, explicitly selected app requests."""
    if tool == "vera_workspace_archive_inputs":
        return preparation_catalogue(root, args)
    if not reviewer():
        raise PermissionError("Reviewer authority is required")
    if args.get("confirmed") is not True:
        raise ValueError("Confirm the archive lifecycle action")
    core = archive_module(root)
    if tool == "vera_workspace_archive_create_engagement":
        return create_engagement_once(core, args)
    folder, engagement = engagement_scope(
        core, args["client_id"], args["engagement_id"]
    )
    if tool == "vera_workspace_archive_prepare":
        current = preparation_catalogue(root, args)
        if current["scope_revision"] != args["scope_revision"]:
            raise ValueError("Engagement or inputs changed; reopen the preparation")
        if current["import_recovery_required"]:
            raise ValueError(
                "Resolve the interrupted import before preparing another run"
            )
        if args["workflow_id"] not in core.VERA_CLIENT_WORKFLOW_IDS:
            raise ValueError("Workflow is not in the maintained Vera engagement gate")
        inputs = args.get("input_ids", [])
        upstream = args.get("upstream_artifacts", [])
        if (
            not isinstance(inputs, list)
            or not isinstance(upstream, list)
            or not 1 <= len(inputs) + len(upstream) <= 1000
            or any(not isinstance(value, str) for value in inputs)
        ):
            raise ValueError(
                "Select between one and 1000 exact imported inputs or sealed artifacts"
            )
        for reference in upstream:
            if (
                not isinstance(reference, dict)
                or set(reference) != {"run_id", "artifact_id", "role"}
                or not isinstance(reference["role"], str)
                or not reference["role"].strip()
                or len(reference["role"]) > 80
            ):
                raise ValueError(
                    "Expected an exact upstream artifact and explicit role"
                )
            # The public preparer revalidates the exact artifact in this engagement.
        prepared = core.prepare_studio_client_workflow(
            args["engagement_id"],
            args["workflow_id"],
            input_ids=inputs,
            upstream_artifacts=upstream,
            label=args["label"],
            purpose=args["purpose"],
            idempotency_key=args["idempotency_key"],
        )
        run = prepared["run"]
        return {
            "status": prepared["status"],
            "client_id": args["client_id"],
            "engagement_id": args["engagement_id"],
            "run_id": run["run_id"],
            "work_ref": work_ref(
                args["client_id"], args["engagement_id"], run["run_id"]
            ),
            "label": run["label"],
            "workflow_id": run["workflow_id"],
            "workflow_executed": False,
        }
    if tool != "vera_workspace_archive_start":
        raise ValueError("Unknown archive lifecycle action")
    loaded = core.ledger.load_run(folder, args["engagement_id"], args["run_id"])
    if fingerprint(loaded["run"]) != args["scope_revision"]:
        raise ValueError("Run state changed; reopen the selected engagement")
    if engagement["status"] != "open" or loaded["run"]["status"] not in {
        "prepared",
        "failed",
    }:
        raise ValueError("Select a prepared or failed run in an open engagement")
    result = core.start_studio_client_workflow(
        args["client_id"], args["engagement_id"], args["run_id"]
    )
    return {
        "status": result["status"],
        "client_id": args["client_id"],
        "engagement_id": args["engagement_id"],
        "run_id": args["run_id"],
        "workflow_executed": False,
    }


def resolve_binding(root: Path, reference: str) -> dict[str, Any]:
    """Recheck the configured folder and exact ledger identity on every operation."""
    match = WORK_REF.fullmatch(reference)
    if match is None:
        raise PermissionError("Unknown Studio Archive work reference")
    client_id, engagement_id, run_id = (
        prefix + value
        for prefix, value in zip(
            ("client_", "eng_", "run_"), match.groups(), strict=True
        )
    )
    core = archive_module(root)
    folder = client_root(core, client_id)
    engagement = core.ledger.load_engagement_manifest(folder, engagement_id)
    if engagement["client_id"] != client_id:
        raise PermissionError("Engagement does not belong to the selected client")
    loaded = core.ledger.load_run(folder, engagement_id, run_id)
    run = loaded["run"]
    if run["client_id"] != client_id:
        raise PermissionError("Run does not belong to the selected client")
    return {
        "work_ref": reference,
        "client_root": str(folder),
        "client_id": client_id,
        "engagement_id": engagement_id,
        "run_id": run_id,
        "workflow_id": run["workflow_id"],
        "component": run["workflow_id"],
    }


def archive_action(root: Path, operation: str) -> dict[str, Any]:
    """Use the existing folder chooser or refresh/recovery without source edits."""
    core = archive_module(root)
    if operation == "setup":
        return core.setup_archive_with_folder_picker()
    if operation != "refresh":
        raise ValueError("Unknown archive configuration action")
    refreshed = core.refresh_archive()
    recovered = core.recover_studio_client_ledger()
    return {
        "configured": True,
        "setup_required": False,
        "status": "refreshed",
        "recovery_status": recovered["status"],
        "scan_issue_count": len(refreshed.get("scan_issues", [])),
        "source_archive_mutated": False,
    }
