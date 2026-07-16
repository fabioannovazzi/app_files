"""List candidate judgement entries or mark them for decision-pack use."""

from __future__ import annotations

import argparse
import json
import logging
import re
from pathlib import Path
from typing import Any

from advisor_case_core import (
    INCLUSION_BUNDLES_FILENAME,
    JUDGEMENT_STATUSES,
    CaseWorkspaceError,
    load_case_file,
    set_judgement_statuses,
)

__all__ = ["main"]

LOGGER = logging.getLogger(__name__)


def _compact_text(value: str, *, limit: int = 170) -> str:
    text = re.sub(r"\s+", " ", value).strip()
    if len(text) <= limit:
        return text
    return f"{text[:limit].rstrip()}..."


def _material_titles(case_dir: Path) -> dict[str, str]:
    registry = load_case_file(case_dir, "materials")
    return {
        str(material["id"]): str(material.get("title") or material["id"])
        for material in registry["materials"]
    }


def _pending_entries(case_dir: Path) -> list[dict[str, Any]]:
    judgement = load_case_file(case_dir, "judgement")
    return [entry for entry in judgement["entries"] if entry.get("status") == "pending"]


def _pending_bundle_groups(
    case_dir: Path,
    pending_entries: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    bundles_path = case_dir / INCLUSION_BUNDLES_FILENAME
    if not bundles_path.exists():
        return []
    payload = json.loads(bundles_path.read_text(encoding="utf-8"))
    bundles = payload.get("bundles", []) if isinstance(payload, dict) else []
    pending_by_id = {str(entry["id"]): entry for entry in pending_entries}
    groups: list[dict[str, Any]] = []
    for bundle in bundles:
        if not isinstance(bundle, dict):
            continue
        entries = [
            pending_by_id[str(entry_id)]
            for entry_id in bundle.get("entry_ids", [])
            if str(entry_id) in pending_by_id
        ]
        if entries:
            groups.append(
                {
                    "id": str(bundle.get("id", "")).strip(),
                    "title": str(bundle.get("title", "")).strip(),
                    "entries": entries,
                }
            )
    return groups


def _log_pending_summary(
    case_dir: Path,
    *,
    show_ids: bool = False,
) -> list[dict[str, Any]]:
    pending_entries = _pending_entries(case_dir)
    pending_bundles = _pending_bundle_groups(case_dir, pending_entries)
    material_titles = _material_titles(case_dir)
    if not pending_entries:
        LOGGER.info("No candidate judgement entries waiting for decision-pack use.")
        return []

    LOGGER.info("Candidate decision-pack entries (%s):", len(pending_entries))
    if pending_bundles:
        LOGGER.info("Candidate inclusion bundles (%s):", len(pending_bundles))
        pending_index_by_id = {
            str(entry["id"]): index
            for index, entry in enumerate(pending_entries, start=1)
        }
        for index, bundle in enumerate(pending_bundles, start=1):
            item_numbers = [
                str(pending_index_by_id[str(entry["id"])])
                for entry in bundle["entries"]
            ]
            LOGGER.info(
                "Bundle %s. %s (%s item%s): items %s",
                index,
                bundle["title"] or bundle["id"],
                len(bundle["entries"]),
                "" if len(bundle["entries"]) == 1 else "s",
                ", ".join(item_numbers),
            )
    for index, entry in enumerate(pending_entries, start=1):
        source_titles = [
            material_titles.get(str(source_id), str(source_id))
            for source_id in entry.get("source_material_ids", [])
        ]
        source_text = ""
        if source_titles:
            source_text = " Sources: " + ", ".join(source_titles) + "."
        entry_label = f"{index}."
        if show_ids:
            entry_label = f"{entry_label} {entry['id']}"
        LOGGER.info(
            "%s [%s] %s%s",
            entry_label,
            entry["kind"],
            _compact_text(str(entry["text"])),
            source_text,
        )
    return pending_entries


def _log_next_actions() -> None:
    LOGGER.info("")
    LOGGER.info("Tell Clara: include all pending items.")
    LOGGER.info("Tell Clara: include bundle <number>.")
    LOGGER.info(
        "Tell Clara: include item <number>, exclude item <number>, or correct item <number>."
    )
    LOGGER.info(
        "Clara will record the inclusion decision mechanically after confirmation."
    )


def main() -> int:
    """Run candidate summary or bulk decision-pack status update."""

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("case_dir", type=Path)
    parser.add_argument(
        "entry_ids",
        nargs="*",
        help="Advanced: specific judgement entry IDs to update after review.",
    )
    parser.add_argument(
        "--item",
        action="append",
        default=[],
        type=int,
        help="1-based item number from the candidate summary to update.",
    )
    parser.add_argument(
        "--bundle",
        action="append",
        default=[],
        help="1-based bundle number or bundle ID from the candidate summary to update.",
    )
    parser.add_argument(
        "--all-pending",
        action="store_true",
        help="Mark every candidate entry shown in the summary.",
    )
    status_group = parser.add_mutually_exclusive_group()
    status_group.add_argument(
        "--status",
        choices=sorted(JUDGEMENT_STATUSES),
        default=None,
        help="Advanced internal status to apply: approved=include, rejected=exclude.",
    )
    status_group.add_argument(
        "--include",
        action="store_true",
        help="Mark selected entries ready for the client pack.",
    )
    status_group.add_argument(
        "--exclude",
        action="store_true",
        help="Exclude selected entries from the client pack.",
    )
    parser.add_argument(
        "--reviewer",
        "--recorded-by",
        dest="reviewer",
        default="",
        help="Name recorded in the audit log; for solo work, use the advisor name.",
    )
    parser.add_argument("--review-note", default="")
    parser.add_argument(
        "--list-only",
        action="store_true",
        help="Show the candidate summary without applying any update.",
    )
    parser.add_argument(
        "--show-ids",
        action="store_true",
        help="Include stable judgement entry IDs in the pending summary.",
    )
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(message)s")

    if args.all_pending and (args.entry_ids or args.item or args.bundle):
        parser.error(
            "use --all-pending, --bundle, --item, or explicit entry IDs; not together"
        )
    selected_modes = sum(
        bool(mode) for mode in (args.entry_ids, args.item, args.bundle)
    )
    if selected_modes > 1:
        parser.error("use --bundle, --item, or explicit entry IDs; not together")

    try:
        pending_entries = _log_pending_summary(args.case_dir, show_ids=args.show_ids)
    except (CaseWorkspaceError, json.JSONDecodeError) as exc:
        parser.error(str(exc))
    if args.list_only or (
        not args.all_pending
        and not args.entry_ids
        and not args.item
        and not args.bundle
    ):
        _log_next_actions()
        return 0
    if args.all_pending and not pending_entries:
        return 0

    if args.all_pending:
        entry_ids = [entry["id"] for entry in pending_entries]
    elif args.bundle:
        pending_bundles = _pending_bundle_groups(args.case_dir, pending_entries)
        selected_entry_ids: list[str] = []
        for raw_selector in args.bundle:
            selector = str(raw_selector).strip()
            selected_bundle: dict[str, Any] | None = None
            if selector.isdigit():
                bundle_number = int(selector)
                if bundle_number < 1 or bundle_number > len(pending_bundles):
                    parser.error(
                        f"candidate summary bundle number out of range: {selector}"
                    )
                selected_bundle = pending_bundles[bundle_number - 1]
            else:
                matches = [
                    bundle
                    for bundle in pending_bundles
                    if selector == bundle["id"]
                    or selector.lower() == str(bundle["title"]).strip().lower()
                ]
                if not matches:
                    parser.error(f"candidate summary bundle not found: {selector}")
                if len(matches) > 1:
                    parser.error(
                        f"candidate summary bundle selector is ambiguous: {selector}"
                    )
                selected_bundle = matches[0]
            selected_entry_ids.extend(
                entry["id"] for entry in selected_bundle["entries"]
            )
        entry_ids = selected_entry_ids
    elif args.item:
        invalid_items = [
            item for item in args.item if item < 1 or item > len(pending_entries)
        ]
        if invalid_items:
            parser.error(
                "candidate summary item number out of range: "
                + ", ".join(str(item) for item in invalid_items)
            )
        entry_ids = [pending_entries[item - 1]["id"] for item in args.item]
    else:
        entry_ids = args.entry_ids
    status = args.status
    if status is None:
        status = "rejected" if args.exclude else "approved"

    updated_entries = set_judgement_statuses(
        args.case_dir,
        entry_ids,
        status=status,
        reviewer=args.reviewer,
        review_note=args.review_note,
    )

    LOGGER.info("")
    LOGGER.info(
        "Judgement entries marked: %s status=%s.",
        len(updated_entries),
        status,
    )
    for entry in updated_entries:
        LOGGER.info(
            "- [%s] %s",
            entry["kind"],
            _compact_text(str(entry["text"]), limit=120),
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
