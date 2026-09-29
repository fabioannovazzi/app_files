"""Bound public benchmark reads using the existing pinned-address transport.

Host restrictions, byte limits and MIME checks protect a fixed acquisition
contract. They do not select economically relevant sources or parameters.
"""

from __future__ import annotations

import hashlib
import ipaddress
import socket
import sys
from pathlib import Path
from urllib.parse import urlsplit
from urllib.request import Request

from valuation_engine import ValuationError

ROOT = Path(__file__).resolve().parents[1]
for candidate in (
    ROOT / "vendor/modules",
    ROOT.parent.parent / "vendor/modules",
    ROOT.parent / "clara/scripts",
):
    if (candidate / "public_http.py").is_file():
        sys.path.insert(0, str(candidate))
        break

from public_http import open_public_url  # noqa: E402

__all__ = [
    "download_html",
    "download_csv",
    "resolve_public_target",
    "validate_url",
    "MAX_BYTES",
    "HOSTS",
    "ECB_HOSTS",
]
MAX_BYTES = 2 * 1024 * 1024
HOSTS = frozenset({"pages.stern.nyu.edu", "people.stern.nyu.edu", "www.stern.nyu.edu"})
ECB_HOSTS = frozenset({"www.ecb.europa.eu", "data-api.ecb.europa.eu"})


def validate_url(url: str, *, hosts: frozenset[str] = HOSTS) -> str:
    """Require an explicit supported HTTPS URL; never infer a download URL."""
    if not isinstance(url, str) or len(url) > 4096 or any(ord(c) <= 32 for c in url):
        raise ValuationError("Invalid public acquisition URL")
    parsed = urlsplit(url)
    if (
        parsed.scheme != "https"
        or parsed.hostname not in hosts
        or parsed.port not in {None, 443}
        or parsed.username is not None
        or parsed.password is not None
        or parsed.fragment
        or "\\" in url
    ):
        raise ValuationError(
            "Acquisition requires an allowed HTTPS host without credentials"
        )
    return parsed.hostname


def resolve_public_target(
    url: str, *, hosts: frozenset[str] = HOSTS
) -> tuple[str, int, tuple[str, ...]]:
    """Vet every DNS answer; the shared transport connects to these exact IPs."""
    host = validate_url(url, hosts=hosts)
    addresses = tuple(
        dict.fromkeys(
            row[4][0] for row in socket.getaddrinfo(host, 443, type=socket.SOCK_STREAM)
        )
    )
    if not addresses or any(not ipaddress.ip_address(ip).is_global for ip in addresses):
        raise ValuationError("Acquisition resolved to a non-public address")
    return host, 443, addresses


def download_html(url: str, *, hosts: frozenset[str] = HOSTS) -> tuple[bytes, dict]:
    """Read one bounded HTML document; no cookies, authentication or old cache."""
    return _download(url, "text/html", hosts)


def download_csv(url: str) -> tuple[bytes, dict]:
    """Read one bounded ECB CSV without interpreting formulas or office files."""
    return _download(url, "text/csv", ECB_HOSTS)


def _download(
    url: str, expected_mime: str, hosts: frozenset[str]
) -> tuple[bytes, dict]:
    validate_url(url, hosts=hosts)
    redirects = []

    def resolve(target: str) -> tuple[str, int, tuple[str, ...]]:
        result = resolve_public_target(target, hosts=hosts)
        redirects.append(target)
        return result

    request = Request(
        url,
        headers={
            "User-Agent": "MparanzaValuationEvidence/0.1",
            "Accept": expected_mime,
            "Accept-Encoding": "identity",
        },
    )
    with open_public_url(request, 20, resolve) as response:
        if response.status != 200:
            raise ValuationError("Benchmark response must be complete HTTP 200")
        mime = response.headers.get_content_type()
        if (
            mime != expected_mime
            or response.headers.get("Content-Encoding", "identity") != "identity"
        ):
            raise ValuationError(
                f"Only uncompressed {expected_mime} is supported by this parser"
            )
        length = response.headers.get("Content-Length")
        if length is not None and (not length.isdecimal() or int(length) > MAX_BYTES):
            raise ValuationError("Invalid or oversized benchmark response")
        raw = response.read(MAX_BYTES + 1)
        if len(raw) > MAX_BYTES or (length is not None and len(raw) != int(length)):
            raise ValuationError("Oversized or incomplete benchmark response")
        prefixes = (
            (b"<html", b"<!doctype html")
            if expected_mime == "text/html"
            else (b"key,freq,",)
        )
        if b"\x00" in raw or not raw.lstrip().lower().startswith(prefixes):
            raise ValuationError(
                "Expected source text bytes; archives and office files are not parsed"
            )
        charset = response.headers.get_content_charset() or "utf-8"
        if charset.lower() not in {"utf-8", "utf8", "iso-8859-1", "windows-1252"}:
            raise ValuationError("Unsupported benchmark character encoding")
        raw.decode(charset)
        return raw, {
            "requested_url": url,
            "final_url": response.geturl(),
            "redirect_urls": redirects,
            "mime": mime,
            "charset": charset,
            "bytes": len(raw),
            "sha256": hashlib.sha256(raw).hexdigest(),
            "etag": response.headers.get("ETag"),
            "last_modified": response.headers.get("Last-Modified"),
        }
