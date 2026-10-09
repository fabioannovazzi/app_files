"""Compare retained retry results while checking newly issued review scopes."""

from __future__ import annotations

import base64
import json
import re
from typing import Any

__all__ = ["assert_same_retained_response"]


def assert_same_retained_response(first: dict[str, Any], retry: dict[str, Any]) -> None:
    """Require identical business data and signed claims except ticket expiry."""
    assert {k: v for k, v in first.items() if k != "review_ticket"} == {
        k: v for k, v in retry.items() if k != "review_ticket"
    }
    first_scope = _claims(first["review_ticket"])
    retry_scope = _claims(retry["review_ticket"])
    assert first_scope["revision"] == first["revision"]
    assert type(first_scope.pop("expires")) is int
    assert type(retry_scope.pop("expires")) is int
    assert first_scope == retry_scope


def _claims(ticket: str) -> dict[str, Any]:
    """Read the exact wire scope; server authorization has separate RPC checks."""
    body, signature = ticket.split(".")
    assert re.fullmatch(r"[A-Za-z0-9_-]+", body)
    assert re.fullmatch(r"[0-9a-f]{64}", signature)
    return json.loads(base64.urlsafe_b64decode(body + "=" * (-len(body) % 4)))
