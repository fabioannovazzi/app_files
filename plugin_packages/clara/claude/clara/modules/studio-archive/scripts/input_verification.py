"""Read-only verification of selected portable Archive inputs.

Receipt seals, IDs and byte hashes are mechanically verifiable. Document
meaning, version lineage and professional approval are deliberately not inferred.
"""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import client_ledger as ledger

__all__ = ["verify_inputs"]

_INPUT_ID = re.compile(r"input_[0-9a-f]{24}")
_SHA256 = re.compile(r"[0-9a-f]{64}")
_MAX_SELECTION = 100


def _selection(
    input_ids: Sequence[str],
    expected_receipts: Sequence[Mapping[str, Any]] | None,
) -> tuple[list[str], dict[str, str] | None]:
    if (
        not isinstance(input_ids, (list, tuple))
        or not 1 <= len(input_ids) <= _MAX_SELECTION
        or any(
            not isinstance(item, str) or _INPUT_ID.fullmatch(item) is None
            for item in input_ids
        )
        or len(set(input_ids)) != len(input_ids)
    ):
        raise ledger.LedgerError("Select 1 to 100 distinct exact input IDs.")
    selected = list(input_ids)
    if expected_receipts is None:
        return selected, None
    if not isinstance(expected_receipts, (list, tuple)):
        raise ledger.LedgerError("Expected receipts must be an array.")
    expected: dict[str, str] = {}
    for item in expected_receipts:
        if (
            not isinstance(item, Mapping)
            or set(item) != {"input_id", "content_sha256"}
            or not isinstance(item["input_id"], str)
            or item["input_id"] not in selected
            or item["input_id"] in expected
            or not isinstance(item["content_sha256"], str)
            or _SHA256.fullmatch(item["content_sha256"]) is None
        ):
            raise ledger.LedgerError(
                "Expected receipts require one input_id and content_sha256 "
                "copied from each selected input's prior receipt."
            )
        expected[item["input_id"]] = item["content_sha256"]
    if set(expected) != set(selected):
        raise ledger.LedgerError("Expected receipts must cover every selected input.")
    return selected, expected


def verify_inputs(
    client_root: Path,
    client_id: str,
    engagement_id: str,
    input_ids: Sequence[str],
    *,
    expected_receipts: Sequence[Mapping[str, Any]] | None = None,
    require_exact_input_set: bool = False,
) -> dict[str, Any]:
    """Verify selected receipt/byte identities without editing the client tree.

    Optional prior receipt seals establish preservation against that supplied
    baseline. Exact-set checking additionally reads all inputs in this engagement.
    This is an observation at verification time, not a lock on future file changes.
    """

    selected, expected = _selection(input_ids, expected_receipts)
    if not isinstance(require_exact_input_set, bool):
        raise ledger.LedgerError("require_exact_input_set must be boolean.")
    client = ledger.load_client_manifest(client_root)
    engagement = ledger.load_engagement_manifest(client_root, engagement_id)
    if client["client_id"] != client_id or engagement["client_id"] != client_id:
        raise ledger.LedgerError("Selected engagement belongs to another client.")

    results: list[dict[str, Any]] = []
    failures: list[dict[str, Any]] = []
    for input_id in selected:
        try:
            receipt = ledger.load_input_receipt(client_root, engagement_id, input_id)
            # Reuse the supported reader; raw receipt JSON intentionally omits
            # hydrated paths. Recheck metadata after the complete byte read.
            after = ledger.load_input_receipt(
                client_root, engagement_id, input_id, verify_bytes=False
            )
            if after != receipt:
                raise ledger.LedgerError("Input receipt changed during verification.")
        except (ledger.LedgerError, OSError) as exc:
            failure = {
                "input_id": input_id,
                "code": "input_verification_failed",
                "message": str(exc),
            }
            failures.append(failure)
            results.append(
                {"input_id": input_id, "status": "failed", "failure": failure}
            )
            continue
        baseline_matches = (
            receipt["content_sha256"] == expected[input_id]
            if expected is not None
            else None
        )
        result = {
            "input_id": input_id,
            "status": "verified" if baseline_matches is not False else "failed",
            "receipt_valid": True,
            "controlled_bytes_match_receipt": True,
            "expected_receipt_matches": baseline_matches,
            "receipt": receipt,
        }
        if baseline_matches is False:
            failure = {
                "input_id": input_id,
                "code": "expected_receipt_mismatch",
                "message": "Current receipt differs from the supplied prior receipt.",
            }
            failures.append(failure)
            result["failure"] = failure
        results.append(result)

    input_set_matches = None
    current_input_ids = None
    if require_exact_input_set:
        try:
            inventory = ledger.list_inputs(client_root, engagement_id)
            current_input_ids = sorted(item["input_id"] for item in inventory)
            input_set_matches = current_input_ids == sorted(selected)
            # Revalidate selected receipt identities against the final listing.
            earlier = {
                item["input_id"]: item["receipt"]
                for item in results
                if "receipt" in item
            }
            if any(
                item["input_id"] in earlier and item != earlier[item["input_id"]]
                for item in inventory
            ):
                raise ledger.LedgerError("Selected inputs changed during verification.")
            if not input_set_matches:
                failures.append(
                    {
                        "code": "input_set_mismatch",
                        "message": "Engagement inputs differ from the exact selected set.",
                        "missing_input_ids": sorted(
                            set(selected) - set(current_input_ids)
                        ),
                        "additional_input_ids": sorted(
                            set(current_input_ids) - set(selected)
                        ),
                    }
                )
        except (ledger.LedgerError, OSError) as exc:
            input_set_matches = False
            failures.append(
                {"code": "input_inventory_verification_failed", "message": str(exc)}
            )
    if ledger.load_engagement_manifest(client_root, engagement_id) != engagement:
        failures.append(
            {
                "code": "engagement_changed",
                "message": "Engagement changed during verification.",
            }
        )
    verified = not failures
    return {
        "schema_version": "vera.input_verification.v1",
        "status": "verified" if verified else "blocked",
        "verified": verified,
        "checked_at": datetime.now(timezone.utc).isoformat(),
        "client_id": client_id,
        "engagement_id": engagement_id,
        "engagement_status": engagement["status"],
        "selected_input_count": len(selected),
        "inputs": results,
        "expected_receipts_checked": expected is not None,
        "require_exact_input_set": require_exact_input_set,
        "input_set_matches": input_set_matches,
        "current_input_ids": current_input_ids,
        "failures": failures,
        "source_archive_mutated": False,
        "document_contents_returned": False,
        "not_checked": [
            "external_originals",
            "folder_delivery_tree",
            "document_meaning_and_authored_lineage",
            "historical_import_retry_outcome",
            "workflow_outputs_and_readable_navigation",
            "visual_and_professional_acceptance",
        ],
    }
