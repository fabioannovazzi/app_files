"""Owner-bound native review of saved tax matters and studio document formats.

Public matter/profile APIs own persistence. Binding, exact hash, CAS and byte
checks are mechanical controls, not legal or professional certification.
"""

from __future__ import annotations

import json
import os
import re
import sys
import uuid
from pathlib import Path
from typing import Any

from native_communication import read, regular, stamp

__all__ = ["dispatch"]
PREFIX = "vera_workspace_practice_"


def configuration() -> tuple[dict[str, str], list[dict]]:
    owner = {
        key: os.environ.get("VERA_WORKSPACE_" + key.upper(), "")
        for key in ("tenant_id", "actor_id")
    }
    if not all(owner.values()):
        raise PermissionError("Open practice review through its owned local service")
    filename = os.environ.get("VERA_PRACTICE_WORKSPACE_BINDINGS")
    if not filename:
        return owner, []
    value = read(Path(filename))
    if any(value.get(key) != expected for key, expected in owner.items()):
        raise PermissionError("Practice bindings belong to another actor or tenant")
    rows = value["bindings"]
    if (
        not isinstance(rows, list)
        or len(rows) > 200
        or any(
            row.get("kind") not in {"tax", "format"}
            or not re.fullmatch(r"[A-Za-z0-9_-]{1,120}", row.get("work_ref", ""))
            for row in rows
        )
    ):
        raise ValueError("Invalid bounded practice bindings")
    if len({row["work_ref"] for row in rows}) != len(rows):
        raise ValueError("Practice references must be unique")
    return owner, rows


def helpers(api: Any, kind: str) -> Any:
    if kind == "tax":
        directory = api.ROOT / "vendor/modules/scripts"
        if not directory.is_dir():
            directory = api.ROOT.parent / "lucia/scripts"
        sys.path.insert(0, str(directory))
        import legal_matter

        return legal_matter
    sys.path.insert(0, str(api.module_root("comunicazione-professionale") / "scripts"))
    import studio_document_format

    return studio_document_format


def review_root(row: dict, owner: dict) -> Path:
    root = Path(row["run_dir"] if row["kind"] == "tax" else row["workspace"])
    regular(root)
    root = root.resolve(strict=True)
    if any((parent / ".git").exists() for parent in (root, *root.parents)):
        raise ValueError("Professional practice data must remain outside Git")
    if row["kind"] == "tax":
        return root
    selector = (
        root
        / ".native-workspace"
        / ("format-" + stamp([owner, row["work_ref"]]) + ".json")
    )
    chosen = read(selector)["review_id"] if selector.exists() else row["review_id"]
    if not re.fullmatch(r"[A-Za-z0-9_-]{1,160}", chosen):
        raise ValueError("Invalid owned format review ID")
    selected = root / "runs" / chosen
    regular(selected)
    return selected


def snapshot(row: dict, owner: dict, api: Any) -> dict:
    root = review_root(row, owner)
    module = helpers(api, row["kind"])
    if row["kind"] == "tax":
        status = module.status(root)
        matter = read(root / "matter.json")
        if matter["kind"] != "contenzioso-tributario":
            raise ValueError("This panel requires an actual tax-litigation matter")
        pack = module.read_pack(root)
        data = {"matter": matter, "status": status, "sources": pack["sources"]}
        label = matter["purpose"]
    else:
        from workflow_core import canonical_digest, file_digest, load_workspace

        manifest = load_workspace(root.parent.parent)
        proposal = read(root / "format_review.json")
        if (
            proposal["workspace_id"] != manifest["workspace_id"]
            or canonical_digest(
                {
                    key: value
                    for key, value in proposal.items()
                    if key != "review_digest"
                }
            )
            != proposal["review_digest"]
        ):
            raise ValueError("Format proposal identity or digest changed")
        preview = read(root / "preview_manifest.json")
        if (
            preview["review_digest"] != proposal["review_digest"]
            or {record["path"] for record in preview["outputs"]}
            != {"preview-short.docx", "preview-long.docx"}
            or len(preview["outputs"]) != 2
        ):
            raise ValueError("Both exact format previews are required")
        for record in [
            *proposal["samples"],
            *([proposal["logo"]] if proposal["logo"] else []),
        ]:
            path = Path(record["snapshot_path"])
            regular(path)
            if (
                not path.resolve().is_relative_to(root / "inputs")
                or file_digest(path) != record["sha256"]
            ):
                raise ValueError("Format sample identity changed")
        for record in preview["outputs"]:
            path = root / record["path"]
            regular(path)
            if not path.is_file() or file_digest(path) != record["sha256"]:
                raise ValueError("Format preview bytes changed")
        stored_path = root.parent.parent / "studio_profile.json"
        stored = read(stored_path) if stored_path.is_file() else None
        data = {
            "proposal": proposal,
            "previews": preview["outputs"],
            "current_profile": stored,
            "base_current": (file_digest(stored_path) if stored else None)
            == proposal["previous_profile_sha256"],
        }
        label = proposal["studio_name"]
    result = {
        "work_ref": row["work_ref"],
        "kind": row["kind"],
        "label": label,
        "data": data,
        "can_write": "REVIEWER"
        in os.environ.get("VERA_WORKSPACE_ROLES", "").split(","),
    }
    result["revision"] = stamp(result)
    return result


def dispatch(tool: str, args: dict, api: Any) -> dict:
    action = tool.removeprefix(PREFIX)
    owner, rows = configuration()
    if action == "catalogue":
        return {
            "configured": bool(rows),
            "practices": [
                {
                    "work_ref": row["work_ref"],
                    "kind": row["kind"],
                    "label": snapshot(row, owner, api)["label"],
                }
                for row in rows
            ],
        }
    row = next((row for row in rows if row["work_ref"] == args.get("work_ref")), None)
    if row is None:
        raise PermissionError("Practice is not connected to this owned service")
    current = snapshot(row, owner, api)
    if (
        action in {"read", "context"}
        and args.get("revision")
        and args["revision"] != current["revision"]
    ):
        raise ValueError("Practice changed; reopen before continuing")
    if action == "read":
        return current
    root = review_root(row, owner)
    module = helpers(api, row["kind"])
    if action == "context":
        reference = args["item_id"]
        if row["kind"] == "format":
            if reference == "settings":
                selected = current["data"]["proposal"]["profile"]["document"]
            elif reference in {"preview-short.docx", "preview-long.docx"}:
                selected = {
                    "path": str(root / reference),
                    "artifact": next(
                        record
                        for record in current["data"]["previews"]
                        if record["path"] == reference
                    ),
                }
            else:
                raise ValueError("Select one exact format item")
        else:
            matter = current["data"]["matter"]
            collection, separator, item_id = reference.partition(":")
            if not separator or collection not in {"calendar", "questions", "stages"}:
                raise ValueError("Choose an exact namespaced matter item")
            selected = next(
                (item for item in matter.get(collection, []) if item["id"] == item_id),
                None,
            )
            if selected is None:
                raise ValueError("Select one exact saved matter item")
            chosen = {
                (citation["source_id"], citation["anchor"])
                for citation in selected.get("citations", [])
            }
            selected = {
                "item": selected,
                "source_units": [
                    {
                        "source_id": source["id"],
                        "anchor": unit["anchor"],
                        "text": unit["text"],
                    }
                    for source in current["data"]["sources"]
                    for unit in source["units"]
                    if (source["id"], unit["anchor"]) in chosen
                ],
            }
        if len(json.dumps(selected).encode()) > 64000:
            raise ValueError("Selected complete practice context exceeds its limit")
        return {
            "work_ref": row["work_ref"],
            "item_id": reference,
            "revision": current["revision"],
            "untrusted_evidence": selected,
            "instruction": "Exact user-selected saved evidence only. No legal deadline calculation, professional approval or other-source discovery is implied.",
        }
    if action not in {"tax_save", "format_prepare", "format_approve"}:
        raise ValueError("Unknown practice action")
    if (
        "REVIEWER" not in os.environ.get("VERA_WORKSPACE_ROLES", "").split(",")
        or args.get("human_reviewed") is not True
    ):
        raise PermissionError("Explicit reviewer confirmation is required")
    if action not in (
        {"tax_save"} if row["kind"] == "tax" else {"format_prepare", "format_approve"}
    ):
        raise ValueError("Practice action does not match its bound kind")
    key = args["idempotency_key"]
    if not re.fullmatch(r"[A-Za-z0-9_-]{1,120}", key):
        raise ValueError("Invalid practice submission key")
    state_root = root if row["kind"] == "tax" else root.parent.parent
    # The shared UI-state helper stores beside its output argument. A virtual
    # child anchors private state inside this exact owner workspace/case.
    private_anchor = state_root / ".native-practice-anchor"
    with api.write_lock(private_anchor):
        current = snapshot(row, owner, api)
        receipt = api.ui_state_directory(private_anchor) / (
            "practice-" + stamp([owner, key]) + ".json"
        )
        identity = stamp({"owner": owner, "args": args, "tool": tool})
        if receipt.exists():
            stored = read(receipt)
            if stored["identity"] != identity:
                raise ValueError("Practice submission key belongs to another request")
            if stored["status"] != "completed":
                raise ValueError(
                    "Practice write is uncertain; inspect the retained intent"
                )
            if stored["revision"] != current["revision"]:
                raise ValueError(
                    "Completed practice result changed; inspect its history"
                )
            return current
        if current["revision"] != args["revision"]:
            raise ValueError("Practice changed before saving")
        for pending in receipt.parent.glob("practice-*.json"):
            if (
                re.fullmatch(r"practice-[0-9a-f]{64}\.json", pending.name)
                and read(pending).get("status") == "uncertain"
            ):
                raise ValueError(
                    "An earlier practice write is uncertain; inspect its retained intent"
                )
        if action == "tax_save":
            review = args["review"]
            if any(
                review.get(key) != current["data"]["matter"][key]
                for key in ("kind", "schema_version", "revision")
            ):
                raise ValueError("Keep the exact loaded matter identity and revision")
            module._check(root, review)
        if action == "format_prepare":
            from copy import deepcopy

            from review_document_format import _validate_profile

            candidate = deepcopy(current["data"]["proposal"]["profile"])
            candidate["document"]["docx"] = {
                **candidate["document"].get("docx", {}),
                **args["settings"],
            }
            if not args["settings"]:
                raise ValueError("Change at least one document preference")
            _validate_profile(candidate)
        api.atomic_json(receipt, {"identity": identity, "status": "uncertain"})
        if action == "tax_save" and row["kind"] == "tax":
            proposal = receipt.with_name(receipt.stem + "-proposal.json")
            api.atomic_json(proposal, args["review"])
            module.save(root, proposal, current["data"]["matter"]["revision"])
            module.render(root)
        elif action == "format_approve" and row["kind"] == "format":
            from review_document_format import approve_format_review

            approve_format_review(
                root,
                review_digest=current["data"]["proposal"]["review_digest"],
                reviewer=args["reviewer"],
                confirmed_by_user=True,
            )
        elif action == "format_prepare" and row["kind"] == "format":
            proposal = current["data"]["proposal"]
            settings = receipt.with_name(receipt.stem + "-settings.json")
            api.atomic_json(settings, args["settings"])
            from review_document_format import prepare_format_review

            base = receipt.with_name(receipt.stem + "-base.json")
            brand = dict(proposal["brand_profile"])
            if proposal["logo"]:
                brand["logo_path"] = proposal["logo"]["snapshot_path"]
            api.atomic_json(
                base, {"brand_profile": brand, "profile": proposal["profile"]}
            )
            review_id = "native-format-" + uuid.uuid4().hex
            prepare_format_review(
                state_root,
                review_id=review_id,
                settings_path=settings,
                samples=[
                    Path(record["snapshot_path"]) for record in proposal["samples"]
                ],
                base_profile_path=(
                    base if current["data"]["current_profile"] is None else None
                ),
            )
            module.create_previews(state_root / "runs" / review_id)
            selector = api.ui_state_directory(private_anchor) / (
                "format-" + stamp([owner, row["work_ref"]]) + ".json"
            )
            api.atomic_json(selector, {"review_id": review_id})
        else:
            raise ValueError("Practice action does not match its bound kind")
        result = snapshot(row, owner, api)
        api.atomic_json(
            receipt,
            {
                "identity": identity,
                "status": "completed",
                "revision": result["revision"],
            },
        )
        return result
