#!/usr/bin/env python3
"""Short-lived, checksum-bound artifact download grants."""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import secrets
from datetime import UTC, datetime
from typing import Any, Mapping
from urllib.parse import urlencode, urlparse

__all__ = [
    "ExpiredDownloadGrant",
    "SignedArtifactDelivery",
]


class ExpiredDownloadGrant(ValueError):
    """Raised when a structurally valid artifact grant is no longer active."""


def _canonical_json(value: Mapping[str, Any]) -> bytes:
    return json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")


def _encode(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).rstrip(b"=").decode("ascii")


def _decode(value: str) -> bytes:
    if not value or "=" in value:
        raise ValueError("Artifact download grant encoding is invalid")
    padding = "=" * (-len(value) % 4)
    try:
        decoded = base64.b64decode(
            value + padding,
            altchars=b"-_",
            validate=True,
        )
    except (ValueError, TypeError) as exc:
        raise ValueError("Artifact download grant encoding is invalid") from exc
    if _encode(decoded) != value:
        raise ValueError("Artifact download grant encoding is not canonical")
    return decoded


class SignedArtifactDelivery:
    """Issue and verify opaque bearer grants without exposing storage paths."""

    def __init__(self, secret: bytes, download_base_url: str) -> None:
        if len(secret) < 32:
            raise ValueError("Artifact signing secret must contain at least 32 bytes")
        parsed = urlparse(download_base_url)
        relative = download_base_url.startswith(
            "/"
        ) and not download_base_url.startswith("//")
        secure_absolute = parsed.scheme == "https" and bool(parsed.netloc)
        if not relative and not secure_absolute:
            raise ValueError(
                "Artifact download base URL must be HTTPS or an absolute application path"
            )
        if parsed.query or parsed.fragment:
            raise ValueError(
                "Artifact download base URL must not include query or fragment"
            )
        self._secret = secret
        self._download_base_url = download_base_url.rstrip("?")

    def issue(
        self,
        claims: Mapping[str, Any],
        *,
        ttl_seconds: int = 300,
        now: datetime | None = None,
    ) -> dict[str, Any]:
        """Issue one grant with a maximum fifteen-minute lifetime."""

        if isinstance(ttl_seconds, bool) or not 30 <= ttl_seconds <= 900:
            raise ValueError("Artifact grant lifetime must be from 30 to 900 seconds")
        issued_at = (now or datetime.now(tz=UTC)).astimezone(UTC)
        required = {"tenant_id", "case_id", "artifact_id", "sha256"}
        missing = sorted(key for key in required if not str(claims.get(key, "")))
        if missing:
            raise ValueError(f"Artifact grant is missing claims: {', '.join(missing)}")
        payload = {
            "version": 1,
            **{key: str(claims[key]) for key in sorted(required)},
            "grant_id": secrets.token_urlsafe(16),
            "issued_at": int(issued_at.timestamp()),
            "expires_at": int(issued_at.timestamp()) + ttl_seconds,
        }
        encoded_payload = _encode(_canonical_json(payload))
        signature = hmac.new(
            self._secret, encoded_payload.encode("ascii"), hashlib.sha256
        ).digest()
        token = f"{encoded_payload}.{_encode(signature)}"
        return {
            "grant_id": payload["grant_id"],
            "artifact_id": payload["artifact_id"],
            "sha256": payload["sha256"],
            "expires_at": datetime.fromtimestamp(
                payload["expires_at"], tz=UTC
            ).isoformat(timespec="seconds"),
            "download_url": f"{self._download_base_url}?{urlencode({'token': token})}",
            "token": token,
        }

    def verify(self, token: str, *, now: datetime | None = None) -> dict[str, Any]:
        """Verify signature, shape, and expiry and return exact grant claims."""

        parts = token.split(".")
        if len(parts) != 2 or not all(parts):
            raise ValueError("Artifact download grant structure is invalid")
        encoded_payload, encoded_signature = parts
        try:
            supplied_signature = _decode(encoded_signature)
        except ValueError as exc:
            raise ValueError("Artifact download grant signature is invalid") from exc
        expected_signature = hmac.new(
            self._secret, encoded_payload.encode("ascii"), hashlib.sha256
        ).digest()
        if not hmac.compare_digest(supplied_signature, expected_signature):
            raise ValueError("Artifact download grant signature is invalid")
        payload = json.loads(_decode(encoded_payload))
        required = {
            "version",
            "tenant_id",
            "case_id",
            "artifact_id",
            "sha256",
            "grant_id",
            "issued_at",
            "expires_at",
        }
        if not isinstance(payload, dict) or set(payload) != required:
            raise ValueError("Artifact download grant claims are invalid")
        if payload["version"] != 1:
            raise ValueError("Artifact download grant version is unsupported")
        current = int((now or datetime.now(tz=UTC)).astimezone(UTC).timestamp())
        if (
            not isinstance(payload["expires_at"], int)
            or current >= payload["expires_at"]
        ):
            raise ExpiredDownloadGrant("Artifact download grant has expired")
        if (
            not isinstance(payload["issued_at"], int)
            or payload["issued_at"] > current
            or payload["expires_at"] - payload["issued_at"] > 900
        ):
            raise ValueError("Artifact download grant timestamps are invalid")
        return payload
