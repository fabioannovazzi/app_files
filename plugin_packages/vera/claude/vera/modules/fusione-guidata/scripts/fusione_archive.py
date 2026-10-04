"""Read explicit Studio Archive bindings and verified input receipts.

No folder discovery or cross-client writes are performed. Exact identity/hash
checks are mechanical controls, not authentication of the declared operator.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path
from typing import Any

from fusione_model import CaseError

__all__ = ["ledger", "binding_data", "selected_receipt"]


def ledger() -> Any:
    root = Path(__file__).resolve().parents[1]
    candidates = (
        root.parent / "studio-archive" / "scripts" / "client_ledger.py",
        root / "vendor" / "modules" / "client_ledger.py",
    )
    for path in candidates:
        if path.is_file():
            spec = importlib.util.spec_from_file_location("fusione_studio_ledger", path)
            if spec is not None and spec.loader is not None:
                module = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(module)
                return module
    raise CaseError("Studio Archive's client ledger is unavailable in this package.")


def binding_data(
    entity_id: str, client_root: Path, client_id: str, engagement_id: str
) -> dict[str, Any]:
    api = ledger()
    try:
        client = api.load_client_manifest(client_root)
        engagement = api.load_engagement_manifest(client_root, engagement_id)
    except api.LedgerError as exc:
        raise CaseError(str(exc)) from exc
    if client["client_id"] != client_id or engagement["client_id"] != client_id:
        raise CaseError(
            "The selected archive identities do not match this company binding."
        )
    if engagement["status"] != "open":
        raise CaseError("Select an open, explicitly authorized engagement.")
    return {
        "entity_id": entity_id,
        "client_root": str(client_root),
        "client_id": client_id,
        "engagement_id": engagement_id,
        "client_sha256": client["content_sha256"],
        "engagement_sha256": engagement["content_sha256"],
    }


def selected_receipt(binding: dict[str, Any], input_id: str) -> dict[str, Any]:
    api = ledger()
    current = binding_data(
        binding["entity_id"],
        Path(binding["client_root"]),
        binding["client_id"],
        binding["engagement_id"],
    )
    if current != binding:
        raise CaseError(
            "Archive binding changed; review and bind the new exact version."
        )
    try:
        return api.load_input_receipt(
            Path(binding["client_root"]),
            binding["engagement_id"],
            input_id,
            verify_bytes=True,
        )
    except api.LedgerError as exc:
        raise CaseError(str(exc)) from exc
