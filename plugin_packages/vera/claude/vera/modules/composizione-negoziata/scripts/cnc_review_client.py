"""Verify professional decisions with the fixed authenticated Mparanza service."""

from __future__ import annotations

import hashlib
import json
import urllib.request
from typing import Any

__all__ = ["case_reference", "verify_receipt"]

ENDPOINT = "https://mparanza.com/api/vera/cnc-reviews/verify"


def _digest(value: Any) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, ensure_ascii=False, allow_nan=False).encode()
    ).hexdigest()


def case_reference(context: dict[str, Any]) -> str:
    """Expose an opaque engagement binding, never its name or local path."""
    return _digest(
        {
            "client": context["client_id"],
            "engagement": context["engagement_id"],
            "workflow": "composizione-negoziata",
        }
    )


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(
        self, req: Any, fp: Any, code: int, msg: str, headers: Any, newurl: str
    ) -> None:
        raise ValueError("Review verification redirects are forbidden")


def verify_receipt(
    receipt: dict[str, Any],
    context: dict[str, Any],
    *,
    node_id: str,
    node_version: str,
    role: str,
    decision: str,
) -> dict[str, Any]:
    """Require server-retained identity and exact scope; JSON authority flags are insufficient."""
    fields = {
        "schema_version",
        "request_id",
        "case_ref",
        "role",
        "node_ref",
        "node_version",
        "decision",
        "actor",
        "reviewed_at",
        "authority",
    }
    if not isinstance(receipt, dict) or set(receipt) != fields:
        raise ValueError("Invalid authenticated review receipt fields")
    expected = {
        "schema_version": "vera.cnc_authenticated_review.v1",
        "case_ref": case_reference(context),
        "role": role,
        "node_ref": _digest(node_id),
        "node_version": node_version,
        "decision": decision,
        "authority": "mparanza_authenticated_account",
    }
    if any(receipt[key] != value for key, value in expected.items()):
        raise ValueError(
            "Review receipt belongs to another case, role, version or decision"
        )
    data = json.dumps(
        {"receipt_id": receipt["request_id"], "receipt_sha256": _digest(receipt)}
    ).encode()
    request = urllib.request.Request(
        ENDPOINT, data=data, headers={"Content-Type": "application/json"}, method="POST"
    )
    # Fixed HTTPS destination and redirect refusal prevent document-controlled exfiltration.
    with urllib.request.build_opener(_NoRedirect()).open(
        request, timeout=15
    ) as response:
        content = response.read(16385)
    if len(content) > 16384 or json.loads(content) != receipt:
        raise ValueError("Server did not verify this exact review receipt")
    if not isinstance(receipt["actor"], str) or not receipt["actor"].strip():
        raise ValueError("Server receipt has no authenticated actor")
    return receipt
