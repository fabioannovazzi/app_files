"""Exact readonly CNC history and ordinary output bytes; no legal judgment."""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any

from native_bank_preparation import file_hash
from native_cnc import limited, snapshot

__all__ = ["dispatch"]


def dispatch(
    tool: str, args: dict, binding: dict, loaded: dict, root: Path, api: Any
) -> dict:
    """Bind immutable history mechanically without granting originals or decisions."""
    action = tool.removeprefix("vera_workspace_cnc_history_")
    current = snapshot(binding, loaded, root, api)
    history = current["history"]["rows"]
    revision = api.digest([current["revision"], file_hash(Path(__file__))])
    base = {
        "work_ref": binding["work_ref"],
        "revision": revision,
        "can_write": False,
        "recovery_required": current["recovery_required"],
        "professional_approval": False,
        "actual_model_reads_verified": False,
    }
    if action == "setup":
        offset = args.get("offset", 0)
        if type(offset) is not int or offset < 0:
            raise ValueError("Invalid CNC history page offset")
        newest = list(reversed(history))
        return limited(
            {
                **base,
                "role": current["history"]["role"],
                "total": len(history),
                "offset": offset,
                "has_more": offset + 30 < len(history),
                "rows": [
                    {
                        "source_ref": row["record"]["content_sha256"],
                        "case_revision": row["record"]["revision"],
                        "stage": row["record"]["payload"]["stage"],
                        "created_at": row["record"]["created_at"],
                        "run_id": row["record"]["run_id"],
                        "node_count": len(row["record"]["payload"]["nodes"]),
                        "stale_count": len(row["record"]["payload"]["stale_nodes"]),
                        "review_count": len(row["record"]["payload"]["reviews"]),
                    }
                    for row in newest[offset : offset + 30]
                ],
            }
        )
    row = next(
        (r for r in history if r["record"]["content_sha256"] == args["source_ref"]),
        None,
    )
    if row is None:
        raise PermissionError("Choose an exact CNC version in this owned engagement")
    record = row["record"]
    value = {
        **base,
        "source_ref": record["content_sha256"],
        "case_revision": record["revision"],
        "run_id": record["run_id"],
        "created_at": record["created_at"],
        "is_latest": row is history[-1],
        "record": record["payload"],
    }
    if action == "read":
        return limited(value)
    if action not in {"context", "outputs"}:
        raise ValueError("Unsupported readonly CNC history action")
    if args["revision"] != revision:
        raise ValueError("Reopen the exact CNC history version before continuing")
    if action == "context":
        # Whole selected case, no automatic source-file paths or private drafts.
        return limited(value, 64000)
    files = []
    for kind, media in (("snapshot", "application/json"), ("memo", "text/markdown")):
        path = Path(row[kind + "_path"])
        expected = row[kind + "_sha256"]
        if expected is None:
            files.append(
                {
                    "name": path.name,
                    "path": str(path),
                    "media_type": media,
                    "available": False,
                    "content": None,
                    "sha256": None,
                }
            )
            continue
        raw = path.read_bytes()
        if path.is_symlink() or hashlib.sha256(raw).hexdigest() != expected:
            raise ValueError("Selected ordinary CNC output changed during reading")
        files.append(
            {
                "name": path.name,
                "path": str(path),
                "media_type": media,
                "available": True,
                "content": raw.decode("utf-8"),
                "sha256": expected,
            }
        )
    return limited({**value, "files": files})
