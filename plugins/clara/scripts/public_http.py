"""Public GET transport adapted from the tested image-hydration client.

Connect only to addresses returned by the caller's public-target validator.
TLS authenticates the original hostname; environment proxies are not used.
"""

from __future__ import annotations

import http.client
import ipaddress
import math
import socket
import ssl
import threading
import time
import urllib.parse
import urllib.request
from collections.abc import Callable
from typing import Any

__all__ = ["open_public_url"]
MAX_REDIRECTS = 5


class _RequestDeadline:
    """Enforce a mechanical elapsed-time budget, including trickled HTTP reads.

    Socket shutdown interrupts buffered header/body reads. The caller's resolver
    is synchronous: elapsed DNS time consumes the budget but cannot be interrupted
    here. No request proceeds after a resolver returns beyond the deadline.
    """

    def __init__(self, timeout: float) -> None:
        if not math.isfinite(timeout) or timeout <= 0:
            raise ValueError("Public evidence timeout must be finite and positive")
        self._expires = time.monotonic() + timeout
        self._lock = threading.Lock()
        self._socket: socket.socket | None = None
        self._closed = False
        self._timer = threading.Timer(timeout, self._interrupt)
        self._timer.daemon = True
        self._timer.start()

    def remaining(self) -> float:
        remaining = self._expires - time.monotonic()
        if remaining <= 0:
            raise TimeoutError(
                "Public evidence request exceeded its elapsed-time budget"
            )
        return remaining

    def watch(self, connection: socket.socket) -> None:
        with self._lock:
            self.remaining()
            self._socket = connection

    def _interrupt(self) -> None:
        with self._lock:
            if not self._closed and self._socket is not None:
                try:
                    self._socket.shutdown(socket.SHUT_RDWR)
                except OSError:
                    # The owning HTTP connection may already have closed it.
                    pass

    def close(self) -> None:
        with self._lock:
            self._closed = True
            if self._socket is not None:
                self._socket.close()
            self._socket = None
            self._timer.cancel()


def _connect_pinned_socket(
    address: str, port: int, timeout: float, *, deadline: _RequestDeadline
) -> socket.socket:
    """Connect to one already-vetted numeric address without resolving again."""

    parsed = ipaddress.ip_address(address)
    family = socket.AF_INET6 if parsed.version == 6 else socket.AF_INET
    target: tuple[Any, ...] = (
        (address, port, 0, 0) if family == socket.AF_INET6 else (address, port)
    )
    connection = socket.socket(family, socket.SOCK_STREAM)
    try:
        deadline.watch(connection)
        connection.settimeout(timeout)
        connection.connect(target)
    except OSError:
        connection.close()
        raise
    return connection


class _PinnedResponse:
    """Small response wrapper that owns its pinned HTTP connection."""

    def __init__(
        self,
        response: http.client.HTTPResponse,
        connection: http.client.HTTPConnection,
        final_url: str,
        deadline: _RequestDeadline,
    ) -> None:
        self._response = response
        self._connection = connection
        self._final_url = final_url
        self._deadline = deadline
        self.headers = response.headers
        self.status = response.status

    def read(self, amount: int = -1) -> bytes:
        self._deadline.remaining()
        try:
            data = self._response.read(amount)
        finally:
            # A shutdown can look like ordinary EOF for an unframed response.
            # Never accept that partial body as a completed capture.
            self._deadline.remaining()
        return data

    def geturl(self) -> str:
        return self._final_url

    def close(self) -> None:
        self._deadline.close()
        try:
            self._response.close()
        finally:
            self._connection.close()

    def __enter__(self) -> _PinnedResponse:
        return self

    def __exit__(self, *args: object) -> None:
        self.close()


def _open_pinned_connection(
    *,
    scheme: str,
    hostname: str,
    port: int,
    address: str,
    timeout: float,
    deadline: _RequestDeadline,
) -> http.client.HTTPConnection:
    raw_socket = _connect_pinned_socket(address, port, timeout, deadline=deadline)
    if scheme == "https":
        context = ssl.create_default_context()
        connected_socket = None
        try:
            raw_socket.settimeout(deadline.remaining())
            connected_socket = context.wrap_socket(
                raw_socket,
                server_hostname=hostname,
            )
            deadline.watch(connected_socket)
        except (OSError, ssl.SSLError):
            if connected_socket is not None:
                connected_socket.close()
            raw_socket.close()
            raise
        connection: http.client.HTTPConnection = http.client.HTTPSConnection(
            hostname,
            port,
            timeout=timeout,
            context=context,
        )
        connection.sock = connected_socket
        return connection
    connection = http.client.HTTPConnection(hostname, port, timeout=timeout)
    connection.sock = raw_socket
    return connection


def open_public_url(
    request: urllib.request.Request,
    timeout: float,
    resolver: Callable[[str], tuple[str, int, tuple[str, ...]]],
) -> _PinnedResponse:
    """Pin public targets and share one elapsed budget across HTTP operations.

    Synchronous resolver calls consume this budget but are not cancellable here.
    The returned response must be closed to release its socket/deadline timer.
    """

    deadline = _RequestDeadline(timeout)
    response = None
    try:
        response = _open_public_url(request, resolver, deadline)
        return response
    finally:
        if response is None:
            deadline.close()


def _open_public_url(
    request: urllib.request.Request,
    resolver: Callable[[str], tuple[str, int, tuple[str, ...]]],
    deadline: _RequestDeadline,
) -> _PinnedResponse:
    """Resolve and open within the response-owned deadline lifecycle."""
    if request.data is not None or request.get_method() != "GET":
        raise ValueError(
            "Public evidence hydration supports only bodyless GET requests"
        )
    current_url = request.full_url
    headers = dict(request.header_items())
    for redirect_count in range(MAX_REDIRECTS + 1):
        deadline.remaining()
        safe_url = current_url
        hostname, port, addresses = resolver(safe_url)
        deadline.remaining()
        parts = urllib.parse.urlsplit(safe_url)
        request_target = parts.path or "/"
        if parts.query:
            request_target = f"{request_target}?{parts.query}"
        response: http.client.HTTPResponse | None = None
        connection: http.client.HTTPConnection | None = None
        last_error: BaseException | None = None
        for address in addresses:
            try:
                connection = _open_pinned_connection(
                    scheme=parts.scheme,
                    hostname=hostname,
                    port=port,
                    address=address,
                    timeout=deadline.remaining(),
                    deadline=deadline,
                )
                connection.request("GET", request_target, headers=headers)
                response = connection.getresponse()
                deadline.remaining()
                break
            except (OSError, ssl.SSLError, http.client.HTTPException) as exc:
                last_error = exc
                if response is not None:
                    response.close()
                    response = None
                if connection is not None:
                    connection.close()
                connection = None
                deadline.remaining()
        if response is None or connection is None:
            raise ValueError(
                f"Public evidence host could not be reached through its vetted public addresses: "
                f"{hostname}"
            ) from last_error
        if response.status in {301, 302, 303, 307, 308}:
            location = str(response.headers.get("Location") or "").strip()
            response.close()
            connection.close()
            if not location:
                raise ValueError("Public evidence redirect has no destination")
            if redirect_count >= MAX_REDIRECTS:
                raise ValueError("Public evidence request exceeded the redirect limit")
            current_url = urllib.parse.urljoin(safe_url, location)
            continue
        if not 200 <= response.status < 300:
            status = response.status
            response.close()
            connection.close()
            raise ValueError(f"Public evidence request failed with HTTP {status}")
        return _PinnedResponse(response, connection, safe_url, deadline)
    raise ValueError("Public evidence request exceeded the redirect limit")
