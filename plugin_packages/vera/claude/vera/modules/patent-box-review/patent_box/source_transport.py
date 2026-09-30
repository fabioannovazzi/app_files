"""Bounded HTTPS retrieval for public sources, with no cookies or credentials.

Fixed URL/IP checks are security boundaries, not legal source selection. The
approved research plan supplies exact hostnames. A parent process enforces the
whole-request deadline, including DNS, redirects and slow response bodies.
"""

from __future__ import annotations

import base64
import http.client
import ipaddress
import json
import socket
import ssl
import subprocess
import sys
from dataclasses import dataclass
from urllib.parse import parse_qsl, urljoin, urlsplit, urlunsplit

__all__ = [
    "FetchError",
    "PublicResponse",
    "checked_url",
    "public_addresses",
    "fetch_public",
]

MAX_BYTES = 16 * 1024 * 1024
MAX_REDIRECTS = 3
SENSITIVE_QUERY_KEYS = frozenset(
    {
        "access_token",
        "api_key",
        "apikey",
        "authorization",
        "password",
        "secret",
        "token",
    }
)


class FetchError(ValueError):
    """Retrieval failure that must be retained as incomplete research coverage."""


@dataclass(frozen=True)
class PublicResponse:
    """Original response bytes plus their acquisition metadata."""

    url: str
    content_type: str
    body: bytes
    redirects: tuple[str, ...] = ()
    etag: str | None = None
    last_modified: str | None = None


def checked_url(url: str, allowed_hosts: set[str]) -> str:
    """Require an exact approved HTTPS host and reject credential-bearing URLs."""
    if not isinstance(url, str) or len(url) > 8192 or any(ord(c) < 33 for c in url):
        raise FetchError("URL is not a bounded HTTPS address")
    parsed = urlsplit(url)
    try:
        host = (parsed.hostname or "").encode("idna").decode("ascii").lower()
        port = parsed.port
    except (ValueError, UnicodeError) as error:
        raise FetchError("Malformed URL authority") from error
    if parsed.scheme != "https" or not host or port not in (None, 443):
        raise FetchError("Only public HTTPS on port 443 is supported")
    if (
        host not in allowed_hosts
        or parsed.username is not None
        or parsed.password is not None
    ):
        raise FetchError("Host not in the reviewed plan, or URL includes credentials")
    if host.endswith(".") or "\\" in url or "%" in host:
        raise FetchError("Ambiguous URL authority")
    if any(
        key.casefold() in SENSITIVE_QUERY_KEYS for key, _ in parse_qsl(parsed.query)
    ):
        raise FetchError("Credentials are forbidden in public-source queries")
    # Fragments are local document anchors and are not part of an HTTP request.
    return urlunsplit(("https", host, parsed.path or "/", parsed.query, ""))


def public_addresses(host: str) -> list[str]:
    """Reject mixed public/private DNS answers; the connection uses these exact IPs."""
    try:
        records = socket.getaddrinfo(host, 443, type=socket.SOCK_STREAM)
    except OSError as error:
        raise FetchError("Public hostname could not be resolved") from error
    resolved: set[str] = set()
    for record in records:
        address = record[4][0]
        if not isinstance(address, str):
            raise FetchError("Invalid resolved address")
        resolved.add(address)
    addresses = sorted(resolved)
    if not addresses:
        raise FetchError("Empty DNS response")
    for address in addresses:
        try:
            ip = ipaddress.ip_address(address)
        except ValueError as error:
            raise FetchError("Invalid resolved address") from error
        candidates = [ip]
        if isinstance(ip, ipaddress.IPv6Address) and ip.ipv4_mapped:
            candidates.append(ip.ipv4_mapped)
        if any(
            not candidate.is_global
            or candidate.is_multicast
            or candidate.is_unspecified
            for candidate in candidates
        ):
            raise FetchError(
                "Local, private, reserved or multicast destination is forbidden"
            )
    return addresses


class _PinnedHTTPSConnection(http.client.HTTPSConnection):
    """Retain hostname TLS verification while pinning the checked DNS address."""

    def __init__(self, host: str, address: str, timeout: float) -> None:
        self._tls_context = ssl.create_default_context()
        super().__init__(host, port=443, timeout=timeout, context=self._tls_context)
        self.address = address

    def connect(self) -> None:
        raw = socket.create_connection((self.address, 443), timeout=self.timeout)
        try:
            if ipaddress.ip_address(raw.getpeername()[0]) != ipaddress.ip_address(
                self.address
            ):
                raise FetchError("Connection peer differs from checked address")
            self.sock = self._tls_context.wrap_socket(raw, server_hostname=self.host)
        except (OSError, ValueError):
            raw.close()
            raise


def _request(
    url: str, allowed_hosts: set[str], max_bytes: int, timeout: float
) -> PublicResponse:
    """Worker-only fetch; the parent kills this process at the total deadline."""
    redirects: list[str] = []
    for redirect_number in range(MAX_REDIRECTS + 1):
        url = checked_url(url, allowed_hosts)
        parsed = urlsplit(url)
        host = parsed.hostname
        if host is None:
            raise FetchError("Missing hostname")
        addresses = public_addresses(host)
        # No second DNS resolution: only a validated numeric address is connected.
        connection = _PinnedHTTPSConnection(host, addresses[0], timeout)
        try:
            path = urlunsplit(("", "", parsed.path, parsed.query, ""))
            connection.request(
                "GET",
                path,
                headers={
                    "User-Agent": "Vera-Patent-Box-Source-Review/0.1",
                    "Accept": "application/pdf,text/html,text/plain,application/json,application/xml;q=0.8,*/*;q=0.1",
                    "Accept-Encoding": "identity",
                    "Connection": "close",
                },
            )
            response = connection.getresponse()
            if response.status in (301, 302, 303, 307, 308):
                location = response.getheader("Location")
                if location is None or redirect_number == MAX_REDIRECTS:
                    raise FetchError(
                        "Missing redirect target or redirect limit exceeded"
                    )
                next_url = checked_url(urljoin(url, location), allowed_hosts)
                if next_url in redirects or next_url == url:
                    raise FetchError("Redirect cycle")
                redirects.append(url)
                url = next_url
                continue
            if response.status != 200:
                raise FetchError(f"HTTP status {response.status}")
            encoding = response.getheader("Content-Encoding", "identity").lower()
            if encoding not in ("", "identity"):
                raise FetchError(
                    "Compressed HTTP content is unsupported; retrieval is partial"
                )
            length = response.getheader("Content-Length")
            if length is not None and (
                not length.isdecimal() or int(length) > max_bytes
            ):
                raise FetchError("Invalid or excessive response size")
            body = response.read(max_bytes + 1)
            if len(body) > max_bytes:
                raise FetchError("Response exceeds byte limit")
            if length is not None and len(body) != int(length):
                raise FetchError("Truncated response")
            return PublicResponse(
                url,
                response.getheader("Content-Type", "application/octet-stream"),
                body,
                tuple(redirects),
                response.getheader("ETag"),
                response.getheader("Last-Modified"),
            )
        except (OSError, http.client.HTTPException) as error:
            raise FetchError(
                "HTTPS retrieval failed: " + type(error).__name__
            ) from error
        finally:
            connection.close()
    raise FetchError("Redirect limit exceeded")


def fetch_public(
    url: str,
    *,
    allowed_hosts: set[str],
    max_bytes: int = MAX_BYTES,
    timeout: float = 25.0,
) -> PublicResponse:
    """Retrieve public bytes within a hard wall-clock deadline, without proxy inheritance."""
    url = checked_url(url, allowed_hosts)
    if not 1 <= max_bytes <= MAX_BYTES or not 0 < timeout <= 30:
        raise FetchError("Invalid retrieval limits")
    arguments = json.dumps(
        {
            "url": url,
            "allowed_hosts": sorted(allowed_hosts),
            "max_bytes": max_bytes,
            "timeout": timeout,
        }
    )
    try:
        result = subprocess.run(
            [sys.executable, "-I", __file__, arguments],
            check=False,
            capture_output=True,
            timeout=timeout,
        )
    except subprocess.TimeoutExpired as error:
        raise FetchError("Total retrieval deadline exceeded") from error
    if len(result.stdout) > 2 * max_bytes + 65536:
        raise FetchError("Worker response exceeds limit")
    try:
        payload = json.loads(result.stdout)
    except (ValueError, UnicodeError) as error:
        raise FetchError("Invalid retrieval worker response") from error
    if result.returncode != 0:
        raise FetchError(str(payload.get("error", "Retrieval worker failed")))
    body = base64.b64decode(payload["body"], validate=True)
    if len(body) > max_bytes:
        raise FetchError("Worker body exceeds limit")
    return PublicResponse(
        payload["url"],
        payload["content_type"],
        body,
        tuple(payload["redirects"]),
        payload["etag"],
        payload["last_modified"],
    )


def _worker() -> int:
    """Standalone transport process; never reads client files or execution directives."""
    try:
        request = json.loads(sys.argv[1])
        response = _request(
            request["url"],
            set(request["allowed_hosts"]),
            request["max_bytes"],
            request["timeout"],
        )
        payload = {
            "url": response.url,
            "content_type": response.content_type,
            "body": base64.b64encode(response.body).decode("ascii"),
            "redirects": response.redirects,
            "etag": response.etag,
            "last_modified": response.last_modified,
        }
        code = 0
    except (FetchError, ValueError, KeyError) as error:
        payload = {"error": str(error)}
        code = 2
    sys.stdout.write(json.dumps(payload, ensure_ascii=True))
    return code


if __name__ == "__main__":
    raise SystemExit(_worker())
