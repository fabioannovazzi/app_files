"""Shared, owner-private Archive panel adapter for Vera, Clara and Lucia."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

__all__ = ["document_search", "dispatch"]


def document_search(
    core: Any, args: dict[str, Any], *, opening: bool = False
) -> dict[str, Any]:
    """Repair stale indexing, then search and verify the selected client scope."""
    directory = core.list_studio_clients()
    if not directory["configured"]:
        raise ValueError("La cartella dell’archivio non è collegata.")
    directory["clients"] = [
        row for row in directory["clients"] if row.get("product_has_work", True)
    ]
    client_id = args.get("client_id")
    scope_id = "all"
    if client_id:
        selected = next(
            (row for row in directory["clients"] if row["client_id"] == client_id), None
        )
        if selected is None:
            raise PermissionError("Client is not registered in this archive session")
        scope_id = core.get_studio_client_folder(client_id)["client_folder"]["scope_id"]
    elif args.get("all_clients") is not True:
        raise ValueError("Select a client or explicitly search the whole archive")
    # Exact freshness metadata is a mechanical cache check, not relevance judgment.
    # Validate the requested client before any indexing; never broaden its scope.
    status = core.studio_archive_status()
    if status["index_requires_refresh"]:
        core.refresh_archive(only_if_required=True)
        directory = core.list_studio_clients()
        if client_id:
            scope_id = core.get_studio_client_folder(client_id)["client_folder"][
                "scope_id"
            ]
    result = core.search_archive(
        args["query"],
        scope_id=scope_id,
        limit=20,
        allowed_scope_ids={
            row["scope_id"]
            for row in directory["clients"]
            if row.get("product_has_work", True)
        },
    )
    if opening:
        if not any(hit["source_id"] == args["source_id"] for hit in result["results"]):
            raise PermissionError("Source is not a result of this scoped search")
        return core.open_archive_source(args["source_id"], context_chunks=1)
    labels = {row["scope_id"]: row["display_name"] for row in directory["clients"]}
    for hit in result["results"]:
        hit["client_label"] = labels.get(hit["scope_id"], "Archivio")
        hit["title"] = Path(hit["relative_path"]).name
    return result


def page(rows: list[dict[str, Any]], args: dict[str, Any]) -> dict[str, Any]:
    """Bound a directory or document page without changing its selection."""
    offset = args.get("offset", 0)
    if type(offset) is not int or offset < 0:
        raise ValueError("Invalid archive page offset")
    return {
        "rows": rows[offset : offset + 30],
        "offset": offset,
        "total": len(rows),
        "has_more": offset + 30 < len(rows),
    }


def dispatch(core: Any, operation: str, args: dict[str, Any]) -> dict[str, Any]:
    """Resolve product-owned IDs before returning data only to the private panel."""
    if operation in {"search", "source"}:
        return document_search(core, args, opening=operation == "source")
    if operation == "setup":
        if args.get("confirmed") is not True:
            raise ValueError("Folder selection requires an explicit click")
        return core.setup_archive_with_folder_picker()
    directory = core.list_studio_clients(include_location=True)
    clients = [
        row for row in directory.get("clients", []) if row.get("product_has_work", True)
    ]
    base = {
        "mode": "studio-archive",
        "configured": directory["configured"],
        "archive_location": directory.get("archive_location"),
        "level": "clients",
        "works": [],
    }
    client_id = args.get("client_id")
    if not client_id:
        if args.get("engagement_id") or operation != "catalogue":
            raise ValueError("Select an exact client")
        rows = [
            {
                key: row.get(key)
                for key in ("client_id", "display_name", "registration_status")
            }
            for row in clients
        ]
        paged = page(rows, args)
        return {**base, **paged, "clients": paged["rows"]}
    selected = next((row for row in clients if row["client_id"] == client_id), None)
    if selected is None:
        raise PermissionError("Client is not available in this product Archive")
    base.update(client_id=client_id, client_label=selected["display_name"])
    engagement_id = args.get("engagement_id")
    if not engagement_id:
        if operation != "catalogue":
            raise ValueError("Select an exact engagement")
        folder = Path(
            core.get_studio_client_folder(client_id)["client_folder"]["client_root"]
        )
        inventory = core.ledger.inspect_engagements(folder, client_id)
        rows = [
            {key: row[key] for key in ("engagement_id", "label", "status")}
            for row in inventory["engagements"]
        ]
        rows.extend(
            {"label": row["entry_name"], "status": "blocked"}
            for row in inventory["blocked_engagements"]
        )
        paged = page(rows, args)
        return {
            **base,
            **paged,
            "level": "engagements",
            "engagements": paged["rows"],
            "collection_issues": inventory["blocked_engagements"],
        }
    # The ledger independently enforces product ownership on reads and file opens.
    if operation == "document":
        document = core.read_studio_incarico_document(
            client_id, engagement_id, args["reference"]
        )
        return {key: document[key] for key in ("name", "path", "preview")}
    if operation not in {"catalogue", "matter"}:
        raise ValueError("Unknown Archive operation")
    raw = core.get_studio_incarico(client_id, engagement_id)

    def document(item: dict[str, Any]) -> dict[str, Any]:
        return {
            key: item[key]
            for key in ("name", "label", "reference", "available", "format", "origin")
            if key in item
        }

    saved = {
        key: raw[key]
        for key in (
            "client_id",
            "engagement_id",
            "label",
            "purpose",
            "legacy_assignments",
            "historical_assignments",
        )
        if key in raw
    }
    saved.update(
        documents=[document(item) for item in raw.get("documents", [])],
        results=[document(item) for item in raw.get("results", [])],
        conversations=[
            {key: item.get(key) for key in ("title", "url")}
            for item in raw.get("conversations", [])
        ],
        deliverables=[
            {
                "versions": [
                    {
                        **{
                            key: version.get(key)
                            for key in (
                                "label",
                                "revision",
                                "issued_at",
                                "primary_format",
                            )
                        },
                        "formats": [document(item) for item in version["formats"]],
                    }
                    for version in entry["versions"]
                ]
            }
            for entry in raw.get("deliverables", [])
        ],
        document_issues=[True] if raw.get("document_issues") else [],
        deliverable_issues=[True] if raw.get("deliverable_issues") else [],
    )
    paged = page(saved["documents"], args if operation == "matter" else {})
    # No private contacts or internal receipts are projected by the overview.
    saved = {**saved, **paged, "documents": paged["rows"]}
    if operation == "matter":
        return saved
    return {
        **base,
        "level": "runs",
        "engagement_id": engagement_id,
        "engagement_label": saved.get("label", "Incarico"),
        "incarico": saved,
    }


def main() -> int:
    """Run the local adapter with a JSON request on stdin."""
    import archive_core

    try:
        request = json.load(sys.stdin)
        result = dispatch(archive_core, request["operation"], request["arguments"])
    except (ValueError, OSError, PermissionError, archive_core.ArchiveError) as error:
        sys.stdout.write(json.dumps({"error": str(error)}, ensure_ascii=False))
        return 1
    sys.stdout.write(json.dumps(result, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
