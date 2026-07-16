"""Mechanical privacy guards for review-visible INPS case metadata."""

from __future__ import annotations

import ipaddress
import re
from typing import Any
from urllib.parse import urlsplit

__all__ = ["privacy_issue", "safe_identifier", "safe_source_reference"]

_EMAIL = re.compile(
    r"(?i)(?<![\w.+-])[a-z0-9.!#$%&'*+/=?^_`{|}~-]+@[a-z0-9-]+(?:\.[a-z0-9-]+)+(?![\w.-])"
)
_ITALIAN_TAX_CODE = re.compile(
    r"(?i)(?<![a-z0-9])[a-z]{6}[0-9]{2}[a-ehlmprst][0-9]{2}[a-z][0-9]{3}[a-z](?![a-z0-9])"
)
_URL = re.compile(r"(?i)https?://[^\s<>'\"]+")
_IDENTITY_LABEL = re.compile(
    r"(?i)(?:^|\b)(?:codice\s+fiscale|tax\s+code|e-?mail|nome|cognome|full\s+name|name)\s*[:=]"
)
_OPAQUE_PATH_SEGMENT = re.compile(r"^[A-Za-z0-9_-]{48,}$")
_SAFE_IDENTIFIER = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")


def _url_issue(raw: str) -> str | None:
    try:
        parsed = urlsplit(raw)
        port = parsed.port
    except ValueError:
        return "invalid_url"
    if parsed.scheme.lower() != "https":
        return "non_https_url"
    if parsed.username is not None or parsed.password is not None:
        return "credentialed_url"
    if parsed.query or parsed.fragment:
        return "tokenized_url"
    if port not in (None, 443):
        return "nonstandard_port_url"
    host = (parsed.hostname or "").lower().rstrip(".")
    if not host or host == "localhost" or host.endswith(".local"):
        return "private_url"
    try:
        address = ipaddress.ip_address(host)
    except ValueError:
        address = None
    if address is not None and not address.is_global:
        return "private_url"
    if any(
        _OPAQUE_PATH_SEGMENT.fullmatch(segment) for segment in parsed.path.split("/")
    ):
        return "tokenized_url"
    return None


def privacy_issue(value: Any) -> str | None:
    """Identify mechanically verifiable identifiers or private/tokenized URLs.

    Fixed rules are used only for security/auditability; this function does not
    attempt semantic name detection or decide legal relevance.
    """

    if not isinstance(value, str) or not value:
        return None
    if _EMAIL.search(value):
        return "email_address"
    if _ITALIAN_TAX_CODE.search(value):
        return "italian_tax_code"
    if _IDENTITY_LABEL.search(value):
        return "raw_identity_label"
    for match in _URL.finditer(value):
        issue = _url_issue(match.group(0).rstrip(".,);]"))
        if issue:
            return issue
    return None


def safe_identifier(value: Any) -> bool:
    """Return whether a review-visible ID is opaque and identifier-free."""

    return (
        isinstance(value, str)
        and bool(_SAFE_IDENTIFIER.fullmatch(value))
        and privacy_issue(value) is None
    )


def safe_source_reference(value: Any) -> bool:
    """Permit a public canonical HTTPS citation or identifier-free citation text."""

    if not isinstance(value, str) or not value.strip() or privacy_issue(value):
        return False
    text = value.strip()
    if "://" not in text:
        return True
    return _url_issue(text) is None
