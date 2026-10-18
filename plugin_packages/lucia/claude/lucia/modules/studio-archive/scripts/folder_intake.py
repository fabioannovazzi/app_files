"""Authorized, receipted intake of one external tree into client working files."""

from __future__ import annotations

import json
import os
import re
import stat
import unicodedata
from pathlib import Path
from typing import Any

import client_ledger as ledger

__all__ = ["copy_source_folder"]

_PENDING = ".vera-folder-intake-pending.json"
_SCHEMA = "vera.client_folder_intake.v1"
_MAX_ENTRIES = 5000
_MAX_BYTES = 2 * 1024 * 1024 * 1024


def _safe_name(name: str) -> None:
    """Keep source names portable without renaming or interpreting documents."""
    if (
        not name
        or len(name) > 255
        or name in {".", "..", _PENDING}
        or re.search(r'[<>:"/\\\\|?*\x00-\x1f\x7f]', name)
        or name.endswith((" ", "."))
        or name.split(".")[0].upper()
        in {
            "CON",
            "PRN",
            "AUX",
            "NUL",
            *(f"COM{i}" for i in range(1, 10)),
            *(f"LPT{i}" for i in range(1, 10)),
        }
    ):
        raise ledger.LedgerError("Folder intake contains an unsafe portable name.")


def _inventory(root: Path, *, pending_allowed: bool = False) -> dict[str, Any]:
    """Hash a complete bounded tree; links and special files fail closed."""
    ledger._ordinary_directory(root, label="folder intake directory")
    directories: list[str] = []
    files: list[dict[str, Any]] = []
    total = 0
    queue = [root]
    portable_paths: set[str] = set()
    while queue:
        directory = queue.pop()
        if (
            ledger._ordinary_directory(directory, label="intake subdirectory")
            != directory
        ):
            raise ledger.LedgerError("Folder intake cannot follow symbolic links.")
        for path in sorted(directory.iterdir()):
            if pending_allowed and path == root / _PENDING:
                continue
            _safe_name(path.name)
            observed = path.lstat()
            if path.is_symlink():
                raise ledger.LedgerError("Folder intake cannot follow symbolic links.")
            relative = path.relative_to(root).as_posix()
            portable = unicodedata.normalize("NFC", relative).casefold()
            if portable in portable_paths:
                raise ledger.LedgerError(
                    "Folder intake names collide on a portable filesystem."
                )
            portable_paths.add(portable)
            if stat.S_ISDIR(observed.st_mode):
                directories.append(relative)
                queue.append(path)
            elif stat.S_ISREG(observed.st_mode):
                if observed.st_size > _MAX_BYTES - total:
                    raise ledger.LedgerError("Folder intake exceeds its 2 GB boundary.")
                size, digest = ledger._stable_file_identity(path, label="intake source")
                total += size
                files.append(
                    {"relative_path": relative, "byte_count": size, "sha256": digest}
                )
            else:
                raise ledger.LedgerError(
                    "Folder intake accepts only ordinary files and directories."
                )
            if len(files) + len(directories) > _MAX_ENTRIES or total > _MAX_BYTES:
                raise ledger.LedgerError("Folder intake exceeds 5,000 entries or 2 GB.")
    return {
        "directories": sorted(directories),
        "files": sorted(files, key=lambda x: x["relative_path"]),
    }


def copy_source_folder(
    client_root: Path,
    client_id: str,
    engagement_id: str,
    source: Path,
    destination_name: str | None = None,
) -> dict[str, Any]:
    """Preserve one selected tree outside Vera/, with explicit interrupted retry."""
    root = ledger._ordinary_directory(client_root, label="selected client folder")
    selected = source.expanduser()
    if not selected.is_absolute():
        raise ledger.LedgerError("Select an absolute folder intake source.")
    resolved = ledger._ordinary_directory(selected, label="folder intake source")
    if resolved != selected:
        raise ledger.LedgerError("Folder intake source cannot contain symbolic links.")
    name = destination_name if destination_name is not None else source.name
    _safe_name(name)
    if name.casefold() == ledger.LEDGER_DIRECTORY.casefold():
        raise ledger.LedgerError(
            "Folder intake cannot replace the managed Vera directory."
        )
    inventory = _inventory(resolved)
    if not inventory["files"]:
        raise ledger.LedgerError("Folder intake has no ordinary source files.")
    request = {
        "schema_version": _SCHEMA,
        "client_id": client_id,
        "engagement_id": engagement_id,
        "source_name": resolved.name,
        "destination_name": name,
        "inventory": inventory,
    }
    intake_id = "intake_" + ledger._canonical_json_sha256(request)[:24]
    maximum_receipt = ledger._sealed(
        {
            "request": request,
            "intake_id": intake_id,
            "status": "completed",
            "created_at": ledger._now_iso(),
            "completed_at": ledger._now_iso(),
        }
    )
    if (
        len(
            json.dumps(
                maximum_receipt, ensure_ascii=False, indent=2, sort_keys=True
            ).encode("utf-8")
        )
        + 1
        > ledger._MAX_JSON_BYTES
    ):
        raise ledger.LedgerError("Folder intake receipt exceeds its bounded size.")
    destination = root / name
    with ledger._engagement_lock(root, engagement_id):
        client = ledger.load_client_manifest(root)
        engagement = ledger.load_engagement_manifest(root, engagement_id)
        if client["client_id"] != client_id or engagement["client_id"] != client_id:
            raise ledger.LedgerError(
                "Folder intake client and engagement do not match."
            )
        if engagement["status"] != "open":
            raise ledger.LedgerError(
                "A closed engagement cannot receive a folder intake."
            )
        store = ledger._ordinary_directory(
            ledger._engagement_root(root, engagement_id) / "folder_intakes",
            label="folder intake receipts",
            create=True,
        )
        receipt_path = store / (intake_id + ".json")
        reused = receipt_path.exists() or receipt_path.is_symlink()
        if reused:
            receipt = ledger._validate_seal(
                ledger._read_json(receipt_path, label="folder intake receipt"),
                label="folder intake receipt",
            )
            if receipt["request"] != request or receipt["intake_id"] != intake_id:
                raise ledger.LedgerError(
                    "Folder intake receipt does not match this request."
                )
        else:
            if destination.exists() or destination.is_symlink():
                raise ledger.LedgerError(
                    "The delivery folder already exists; choose a separate delivery name."
                )
            receipt = {
                "request": request,
                "intake_id": intake_id,
                "status": "prepared",
                "created_at": ledger._now_iso(),
            }
            ledger._write_json(receipt_path, ledger._sealed(receipt))
        marker = destination / _PENDING
        if not destination.exists() and not destination.is_symlink():
            if reused and receipt["status"] == "completed":
                raise ledger.LedgerError("Previously copied intake folder is missing.")
            destination.mkdir(mode=0o700)
            # A crash between exclusive mkdir and this marker is intentionally
            # uncertain. A retry never adopts an unmarked pre-existing folder.
            with marker.open("x", encoding="utf-8") as handle:
                handle.write(intake_id)
                handle.flush()
                os.fsync(handle.fileno())
        ledger._ordinary_directory(destination, label="intake destination")
        if destination.resolve(strict=True) != destination:
            raise ledger.LedgerError(
                "Folder intake destination cannot contain symbolic links."
            )
        if receipt["status"] == "completed":
            if _inventory(destination, pending_allowed=True) != inventory:
                raise ledger.LedgerError(
                    "Previously copied intake files changed or moved."
                )
            if marker.exists() or marker.is_symlink():
                ledger._ordinary_file(marker, label="folder intake pending marker")
                if marker.read_text(encoding="utf-8") != intake_id:
                    raise ledger.LedgerError(
                        "Folder intake marker belongs to another request."
                    )
                marker.unlink()
            return _result(
                receipt_path, destination, intake_id, inventory, "already_copied"
            )
        ledger._ordinary_file(marker, label="folder intake pending marker")
        if marker.read_text(encoding="utf-8") != intake_id:
            raise ledger.LedgerError(
                "Folder intake has an uncertain or foreign destination."
            )
        observed = _inventory(destination, pending_allowed=True)
        expected = {row["relative_path"]: row for row in inventory["files"]}
        if not set(observed["directories"]).issubset(inventory["directories"]) or any(
            expected.get(row["relative_path"]) != row for row in observed["files"]
        ):
            raise ledger.LedgerError(
                "Pending intake contains unexpected or changed files."
            )
        for relative in inventory["directories"]:
            path = destination / relative
            if not path.exists() and not path.is_symlink():
                path.mkdir(mode=0o700, parents=True)
            if (
                ledger._ordinary_directory(path, label="intake destination directory")
                != path
            ):
                raise ledger.LedgerError(
                    "Folder intake destination contains symbolic links."
                )
        for row in inventory["files"]:
            target = destination / row["relative_path"]
            original = resolved / row["relative_path"]
            if target.exists() or target.is_symlink():
                size, digest = ledger._stable_file_identity(
                    target, label="retained intake file"
                )
            else:
                size, digest = ledger._stable_copy(
                    original,
                    target,
                    exclusive=True,
                    temporary_directory=store,
                )
            if (size, digest) != (row["byte_count"], row["sha256"]):
                raise ledger.LedgerError(
                    "Copied folder intake file does not match its source."
                )
        if (
            _inventory(resolved) != inventory
            or _inventory(destination, pending_allowed=True) != inventory
        ):
            raise ledger.LedgerError(
                "Folder intake source or destination changed during copying."
            )
        receipt.pop("content_sha256", None)
        receipt.update(status="completed", completed_at=ledger._now_iso())
        ledger._write_json(receipt_path, ledger._sealed(receipt))
        marker.unlink()
        return _result(receipt_path, destination, intake_id, inventory, "copied")


def _result(
    receipt: Path,
    destination: Path,
    intake_id: str,
    inventory: dict[str, Any],
    status: str,
) -> dict[str, Any]:
    return {
        "status": status,
        "intake_id": intake_id,
        "receipt_path": str(receipt),
        "destination_path": str(destination),
        "file_count": len(inventory["files"]),
        "directory_count": len(inventory["directories"]),
        "byte_count": sum(row["byte_count"] for row in inventory["files"]),
        "original_preserved": True,
        "tree_preserved": True,
        "document_meaning_qualified": False,
    }
