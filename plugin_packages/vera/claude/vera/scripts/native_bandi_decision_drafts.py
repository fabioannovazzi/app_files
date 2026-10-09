"""Literal actor-owned incomplete disposition fields; never a public decision."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from native_bandi import stamp
from native_bandi_authoring import snapshot as contribution_snapshot

__all__ = ["dispatch"]

EMPTY = {"decision": "", "reviewer_id": "", "reviewer_role": "", "notes": ""}


def fields(value: Any) -> dict:
    """Validate literal form shape for auditability, not professional meaning."""
    if not isinstance(value, dict) or set(value) != set(EMPTY):
        raise ValueError("Keep the complete incomplete disposition fields")
    if any(not isinstance(item, str) or len(item) > 4000 for item in value.values()):
        raise ValueError("Disposition draft fields must be bounded literal strings")
    if value["decision"] not in {"", "accepted", "returned", "rejected"}:
        raise ValueError("Choose a declared disposition or leave it incomplete")
    return value


def snapshot(binding: dict, loaded: dict, root: Path, args: dict, api: Any) -> dict:
    current = contribution_snapshot(binding, loaded, root, api)
    matches = [
        row
        for row in current["state"]["grants"]
        if row["grant_ref"] == args["grant_ref"]
    ]
    if len(matches) != 1:
        raise PermissionError("Disposition draft belongs to another actor or mandate")
    grant = matches[0]
    identity = {
        "case": current["identity"],
        "grant_ref": grant["grant_ref"],
        "public_record_sha256": grant.get("public_record_sha256"),
    }
    path = current["home"] / ("decision-draft-" + grant["grant_ref"] + ".json")
    if path.is_symlink() or path.exists() and path.stat().st_nlink != 1:
        raise PermissionError("Disposition draft cannot be a link")
    draft = (
        api.read_json(path)
        if path.exists()
        else {"identity": identity, "generation": 0, "fields": dict(EMPTY)}
    )
    if (
        not isinstance(draft, dict)
        or set(draft) != {"identity", "generation", "fields"}
        or type(draft["generation"]) is not int
        or draft["generation"] < 0
    ):
        raise ValueError("Incomplete disposition draft needs ordinary recovery")
    fields(draft["fields"])
    return {
        "current": current,
        "grant": grant,
        "identity": identity,
        "path": path,
        "draft": draft,
        "draft_revision": stamp(draft),
        "draft_stale": draft["identity"] != identity,
        "can_write": current["can_write"] and grant["status"] == "recorded",
    }


def dispatch(
    tool: str, args: dict, binding: dict, loaded: dict, root: Path, api: Any
) -> dict:
    """Saving, clearing and restoring fields never restores confirmation."""
    if (
        binding["workflow_id"] != "bandi-agevolazioni"
        or binding["component"] != "bandi-agevolazioni"
    ):
        raise PermissionError("Selected work is not a grant dossier")
    action = tool.removeprefix("vera_workspace_bandi_author_decision_draft_")
    if action not in {"read", "save", "clear"}:
        raise ValueError("Unsupported disposition draft action")
    state = snapshot(binding, loaded, root, args, api)
    current = state["current"]
    if (
        args["revision"] != current["revision"]
        or args["source_ref"] != current["source_ref"]
    ):
        raise ValueError("Disposition draft scope changed; reopen the mandate")
    if action == "read":
        return {
            "work_ref": binding["work_ref"],
            "grant_ref": args["grant_ref"],
            "revision": current["revision"],
            "source_ref": current["source_ref"],
            "data": {"selection": {"source_ref": current["source_ref"]}},
            "fields": state["draft"]["fields"],
            "draft_revision": state["draft_revision"],
            "draft_stale": state["draft_stale"],
            "can_write": state["can_write"],
            "confirmation_restored": False,
        }
    if not state["can_write"]:
        raise PermissionError("Disposition fields are read-only or need recovery")
    if args["expected_draft_revision"] != state["draft_revision"]:
        raise ValueError("Another panel changed these incomplete disposition fields")
    if action == "clear" and args.get("confirmed") is not True:
        raise ValueError("Explicitly confirm discarding only these private fields")
    literal = fields(args["fields"]) if action == "save" else dict(EMPTY)
    with api.write_lock(current["public"]["output"]):
        latest = snapshot(binding, api.load_binding(binding), root, args, api)
        if (
            latest["current"]["revision"] != current["revision"]
            or latest["draft_revision"] != state["draft_revision"]
        ):
            raise ValueError("Disposition or its private fields changed before saving")
        saved = {
            "identity": state["identity"],
            "generation": state["draft"]["generation"] + 1,
            "fields": literal,
        }
        api.atomic_json(state["path"], saved)
    return {
        "saved": True,
        "draft_revision": stamp(saved),
        "confirmation_restored": False,
        "public_case_changed": False,
    }
