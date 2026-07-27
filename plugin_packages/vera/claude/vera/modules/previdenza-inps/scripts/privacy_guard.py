"""Mechanical session and credential guards for INPS case metadata."""

from __future__ import annotations

import ipaddress
import re
from typing import Any
from urllib.parse import urlsplit

__all__ = ["safe_identifier", "safe_source_reference", "session_url_issue"]

_URL = re.compile(r"(?i)https?://[^\s<>'\"]+")
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


def session_url_issue(value: Any) -> str | None:
    """Identify private, credentialed, or tokenized URLs.

    Personal data is legitimate evidence in this private professional workflow.
    This guard is limited to session and credential exposure.
    """

    if not isinstance(value, str) or not value:
        return None
    for match in _URL.finditer(value):
        issue = _url_issue(match.group(0).rstrip(".,);]"))
        if issue:
            return issue
    return None


def safe_identifier(value: Any) -> bool:
    """Return whether a machine identifier is structurally safe."""

    return (
        isinstance(value, str)
        and bool(_SAFE_IDENTIFIER.fullmatch(value))
        and session_url_issue(value) is None
    )


def safe_source_reference(value: Any) -> bool:
    """Permit citation text or a public canonical HTTPS citation."""

    if not isinstance(value, str) or not value.strip() or session_url_issue(value):
        return False
    text = value.strip()
    if "://" not in text:
        return True
    return _url_issue(text) is None
