"""Bind Clara's existing advisory workspace to one shared Archive engagement."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
COMPONENT = ROOT / "modules/studio-archive"
if not COMPONENT.is_dir():
    COMPONENT = ROOT.parent / "studio-archive"
sys.path.insert(0, str(COMPONENT / "scripts"))

import archive_core as archive
import client_ledger as ledger
from advisor_case_core import initialize_case, load_case_file, validate_case_workspace
from case_store import atomic_text, transaction

__all__ = ["open_case", "main"]
BINDING = "clara_archive_binding.json"


def _read(path: Path) -> dict[str, Any]:
    if path.is_symlink():
        raise ValueError("Archive binding cannot be a symbolic link.")
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError("Invalid Clara Archive binding.")
    return value


def open_case(
    client_id: str,
    engagement_id: str,
    *,
    case_dir: str | None = None,
    objective: str | None = None,
    audience: str = "Decision maker",
    output_language: str = "it",
    state_dir: Path | None = None,
) -> dict[str, Any]:
    """Create or resume one case, preserving existing folders and client ownership."""
    folder = archive.get_studio_client_folder(client_id, state_dir=state_dir)[
        "client_folder"
    ]
    root = Path(folder["client_root"])
    engagement = ledger.load_engagement_manifest(root, engagement_id)
    engagement_root = root / ledger.LEDGER_DIRECTORY / "engagements" / engagement_id
    identity = {
        "schema_version": "clara.archive_case.v1",
        "client_id": client_id,
        "engagement_id": engagement_id,
    }
    with transaction(engagement_root):
        pointer = engagement_root / BINDING
        saved = _read(pointer) if pointer.exists() or pointer.is_symlink() else None
        if saved is not None and any(saved.get(k) != v for k, v in identity.items()):
            raise ValueError("Case binding belongs to another client or engagement.")
        if saved is not None:
            stored = Path(saved["case_path"])
            target = root / stored if not stored.is_absolute() else stored
            if case_dir is not None and Path(case_dir).resolve() != target.resolve():
                raise ValueError(
                    "This engagement already has a case; preserve its folder."
                )
        elif case_dir is not None:
            target = Path(case_dir)
            if not target.is_absolute():
                raise ValueError("Select an absolute existing case folder.")
            if not (target / "case_manifest.json").is_file():
                raise ValueError("The selected existing case has no case manifest.")
        else:
            target = engagement_root / "clara-case"
        if any(part.is_symlink() for part in (target, *target.parents)):
            raise ValueError("Case folder cannot traverse symbolic links.")
        target = target.resolve()
        # An explicit legacy path is permitted, but never inside another client.
        for parent in (target, *target.parents):
            if (parent / ledger.LEDGER_DIRECTORY / "client.json").exists():
                if ledger.load_client_manifest(parent)["client_id"] != client_id:
                    raise ValueError("Case folder belongs to another Archive client.")
                break
        if saved is not None and not (target / "case_manifest.json").is_file():
            raise ValueError(
                "Bound case folder is unavailable; restore it before resuming."
            )
        is_existing = (target / "case_manifest.json").is_file()
        if not is_existing and not objective:
            raise ValueError("Supply the assignment objective to create a new case.")
        with transaction(target):
            marker = target / BINDING
            if marker.exists() or marker.is_symlink():
                if _read(marker) != identity:
                    raise ValueError(
                        "Case is already bound to another client or engagement."
                    )
            elif saved is not None:
                raise ValueError(
                    "Bound case identity is missing; do not adopt a replacement folder."
                )
            if is_existing:
                errors = validate_case_workspace(target)
                if errors:
                    raise ValueError("; ".join(errors))
                manifest = load_case_file(target, "manifest")
            else:
                if engagement["status"] != "open":
                    raise ValueError("Select an open engagement for a new case.")
                manifest = initialize_case(
                    target,
                    client=folder["display_name"],
                    project=engagement["label"],
                    objective=objective,
                    audience=audience,
                    output_language=output_language,
                )
            atomic_text(marker, json.dumps(identity, indent=2) + "\n")
            try:
                stored_path = str(target.relative_to(root))
            except ValueError:
                stored_path = str(target)
            atomic_text(
                pointer,
                json.dumps({**identity, "case_path": stored_path}, indent=2) + "\n",
            )
    return {
        "status": "resumed" if is_existing else "created",
        **identity,
        "case_dir": str(target),
        "case_manifest": manifest,
        "case_brief": str(target / "case_brief.md"),
        "data_handling": {
            "local_reads": "Selected client identity, engagement manifest and Clara case state",
            "model_context": "Selected case path and case manifest; source documents are not returned",
            "network_requests": 0,
        },
    }


def main() -> int:
    """Serve one JSON request through the installed local MCP bridge."""
    try:
        request = json.load(sys.stdin)
        if not isinstance(request, dict) or "state_dir" in request:
            raise ValueError("Invalid case request.")
        result = open_case(**request)
    except (
        ValueError,
        OSError,
        TypeError,
        KeyError,
        archive.ArchiveError,
        ledger.LedgerError,
    ) as exc:
        sys.stdout.write(
            json.dumps({"status": "error", "message": str(exc)}, ensure_ascii=False)
            + "\n"
        )
        return 1
    sys.stdout.write(json.dumps(result, ensure_ascii=False) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
