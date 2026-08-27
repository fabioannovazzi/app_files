"""Ed25519 signing for minimal Vera run-receipt records."""

from __future__ import annotations

import base64
import hashlib
import json
import os
import re
from collections.abc import Mapping
from functools import lru_cache
from typing import Any

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import (
    Ed25519PrivateKey,
    Ed25519PublicKey,
)

__all__ = [
    "RunReceiptSigner",
    "RunReceiptSigningError",
    "canonical_receipt_bytes",
    "get_run_receipt_signer",
]

_PRIVATE_KEY_ENV = "VERA_RUN_RECEIPT_SIGNING_PRIVATE_KEY"
_KEY_ID_ENV = "VERA_RUN_RECEIPT_SIGNING_KEY_ID"
_VERIFY_KEYS_ENV = "VERA_RUN_RECEIPT_VERIFY_KEYS_JSON"
_SIGNED_FIELDS = {
    "schema_version",
    "receipt_id",
    "plugin_version",
    "report_sha256",
    "stamped_at",
    "key_id",
}
_BASE64URL_RE = re.compile(r"^[A-Za-z0-9_-]+$")
_KEY_ID_RE = re.compile(r"^[A-Za-z0-9._-]{1,64}$")


class RunReceiptSigningError(RuntimeError):
    """Raised when receipt signing or verification cannot be completed safely."""


def _base64url_encode(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).decode("ascii").rstrip("=")


def _base64url_decode(value: str, *, label: str) -> bytes:
    if _BASE64URL_RE.fullmatch(value) is None:
        raise RunReceiptSigningError(f"{label} is not valid base64url.")
    try:
        padding = "=" * (-len(value) % 4)
        return base64.urlsafe_b64decode(value + padding)
    except (ValueError, TypeError) as exc:
        raise RunReceiptSigningError(f"{label} is not valid base64url.") from exc


def canonical_receipt_bytes(payload: Mapping[str, Any]) -> bytes:
    """Return the one canonical byte representation covered by the signature."""

    if set(payload) != _SIGNED_FIELDS:
        raise RunReceiptSigningError(
            "Signed receipt fields do not match schema version 1."
        )
    return json.dumps(
        dict(payload),
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")


class RunReceiptSigner:
    """Sign current receipts and verify current or retained public keys."""

    def __init__(
        self,
        *,
        private_key: Ed25519PrivateKey,
        key_id: str | None = None,
        verification_keys: Mapping[str, Ed25519PublicKey] | None = None,
    ) -> None:
        public_key = private_key.public_key()
        public_bytes = public_key.public_bytes(
            encoding=serialization.Encoding.Raw,
            format=serialization.PublicFormat.Raw,
        )
        self._key_id = (
            key_id or f"ed25519-{hashlib.sha256(public_bytes).hexdigest()[:16]}"
        )
        if _KEY_ID_RE.fullmatch(self._key_id) is None:
            raise RunReceiptSigningError(
                "Receipt signing key ID must use 1-64 letters, digits, dots, underscores, or hyphens."
            )
        self._private_key = private_key
        self._verification_keys = dict(verification_keys or {})
        self._verification_keys[self._key_id] = public_key

    @property
    def key_id(self) -> str:
        """Return the active stable public-key identifier."""

        return self._key_id

    def public_key_base64url(self, key_id: str) -> str | None:
        """Return one retained raw Ed25519 public key, if configured."""

        public_key = self._verification_keys.get(key_id)
        if public_key is None:
            return None
        return _base64url_encode(
            public_key.public_bytes(
                encoding=serialization.Encoding.Raw,
                format=serialization.PublicFormat.Raw,
            )
        )

    def sign(self, payload: Mapping[str, Any]) -> str:
        """Sign a canonical receipt record with the active private key."""

        if payload.get("key_id") != self._key_id:
            raise RunReceiptSigningError(
                "Receipt key_id is not the active signing key."
            )
        return _base64url_encode(
            self._private_key.sign(canonical_receipt_bytes(payload))
        )

    def verify(self, payload: Mapping[str, Any], signature: str) -> bool | None:
        """Return true/false, or ``None`` when the historical key is unavailable."""

        key_id = str(payload.get("key_id") or "")
        public_key = self._verification_keys.get(key_id)
        if public_key is None:
            return None
        try:
            public_key.verify(
                _base64url_decode(signature, label="signature"),
                canonical_receipt_bytes(payload),
            )
        except InvalidSignature:
            return False
        return True

    @classmethod
    def from_environment(cls) -> RunReceiptSigner:
        """Load the active private key and retained public-key ring from env."""

        encoded_private = os.environ.get(_PRIVATE_KEY_ENV, "").strip()
        if not encoded_private:
            raise RunReceiptSigningError(
                f"{_PRIVATE_KEY_ENV} must contain a base64url Ed25519 private key."
            )
        private_bytes = _base64url_decode(encoded_private, label=_PRIVATE_KEY_ENV)
        if len(private_bytes) != 32:
            raise RunReceiptSigningError(
                f"{_PRIVATE_KEY_ENV} must decode to exactly 32 bytes."
            )
        try:
            private_key = Ed25519PrivateKey.from_private_bytes(private_bytes)
        except ValueError as exc:
            raise RunReceiptSigningError(
                f"{_PRIVATE_KEY_ENV} is not a valid Ed25519 private key."
            ) from exc

        verification_keys: dict[str, Ed25519PublicKey] = {}
        encoded_keyring = os.environ.get(_VERIFY_KEYS_ENV, "").strip()
        if encoded_keyring:
            try:
                keyring = json.loads(encoded_keyring)
            except json.JSONDecodeError as exc:
                raise RunReceiptSigningError(
                    f"{_VERIFY_KEYS_ENV} must be a JSON object."
                ) from exc
            if not isinstance(keyring, dict):
                raise RunReceiptSigningError(
                    f"{_VERIFY_KEYS_ENV} must be a JSON object."
                )
            for key_id, encoded_public in keyring.items():
                if not isinstance(key_id, str) or not isinstance(encoded_public, str):
                    raise RunReceiptSigningError(
                        f"{_VERIFY_KEYS_ENV} keys and values must be strings."
                    )
                public_bytes = _base64url_decode(
                    encoded_public, label=f"{_VERIFY_KEYS_ENV}[{key_id}]"
                )
                if len(public_bytes) != 32:
                    raise RunReceiptSigningError(
                        f"{_VERIFY_KEYS_ENV}[{key_id}] must decode to 32 bytes."
                    )
                verification_keys[key_id] = Ed25519PublicKey.from_public_bytes(
                    public_bytes
                )
        return cls(
            private_key=private_key,
            key_id=os.environ.get(_KEY_ID_ENV, "").strip() or None,
            verification_keys=verification_keys,
        )


@lru_cache(maxsize=1)
def get_run_receipt_signer() -> RunReceiptSigner:
    """Return the configured process-wide receipt signer."""

    return RunReceiptSigner.from_environment()
