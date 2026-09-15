"""Exercise the public transport with synthetic sockets and no network."""

from __future__ import annotations

import importlib.util
import io
import urllib.request
from pathlib import Path
from typing import Any

import pytest

SCRIPT = Path(__file__).resolve().parents[2] / "plugins/clara/scripts/public_http.py"


class SyntheticSocket:
    def __init__(self, response: bytes) -> None:
        self.response = response
        self.address: Any = None
        self.sent = b""
        self.closed = False

    def settimeout(self, timeout: float) -> None:
        self.timeout = timeout

    def connect(self, address: Any) -> None:
        self.address = address

    def sendall(self, data: bytes) -> None:
        self.sent += data

    def makefile(self, *args: Any) -> io.BytesIO:
        return io.BytesIO(self.response)

    def close(self) -> None:
        self.closed = True


def _transport() -> Any:
    spec = importlib.util.spec_from_file_location("clara_public_http_test", SCRIPT)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_public_get_connects_vetted_ip_without_second_dns_lookup(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    transport = _transport()
    sock = SyntheticSocket(b"HTTP/1.1 200 OK\r\nContent-Length: 2\r\n\r\nok")
    monkeypatch.setattr(transport.socket, "socket", lambda *args: sock)

    def unexpected_dns(*args: Any, **kwargs: Any) -> None:
        pytest.fail("Transport resolved DNS after receiving vetted addresses")

    monkeypatch.setattr(transport.socket, "getaddrinfo", unexpected_dns)

    with transport.open_public_url(
        urllib.request.Request("http://evidence.example/path?q=1"),
        5,
        lambda url: ("evidence.example", 80, ("93.184.216.34",)),
    ) as response:
        body = response.read()

    assert body == b"ok"
    assert sock.address == ("93.184.216.34", 80)
    assert b"Host: evidence.example\r\n" in sock.sent
    assert sock.closed


def test_public_get_revalidates_redirect_before_connecting(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    transport = _transport()
    sock = SyntheticSocket(
        b"HTTP/1.1 302 Found\r\nLocation: http://127.0.0.1/private\r\nContent-Length: 0\r\n\r\n"
    )
    monkeypatch.setattr(transport.socket, "socket", lambda *args: sock)
    calls = []

    def validate(url: str) -> tuple[str, int, tuple[str, ...]]:
        calls.append(url)
        if "127.0.0.1" in url:
            raise ValueError("private destination")
        return "evidence.example", 80, ("93.184.216.34",)

    with pytest.raises(ValueError, match="private destination"):
        transport.open_public_url(
            urllib.request.Request("http://evidence.example"), 5, validate
        )

    assert calls == ["http://evidence.example", "http://127.0.0.1/private"]
    assert sock.address == ("93.184.216.34", 80)
    assert sock.closed


def test_https_pinning_preserves_hostname_for_tls_validation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    transport = _transport()
    sock = SyntheticSocket(b"HTTP/1.1 200 OK\r\nContent-Length: 2\r\n\r\nok")
    monkeypatch.setattr(transport.socket, "socket", lambda *args: sock)
    server_names = []

    class Context:
        def wrap_socket(self, raw: Any, *, server_hostname: str) -> Any:
            server_names.append(server_hostname)
            return raw

    monkeypatch.setattr(transport.ssl, "create_default_context", Context)

    with transport.open_public_url(
        urllib.request.Request("https://evidence.example"),
        5,
        lambda url: ("evidence.example", 443, ("93.184.216.34",)),
    ) as response:
        body = response.read()

    assert body == b"ok"
    assert server_names == ["evidence.example"]
    assert sock.address == ("93.184.216.34", 443)


def test_public_redirect_validates_each_target_and_closes_both_connections(monkeypatch):
    transport = _transport()
    first = SyntheticSocket(
        b"HTTP/1.1 302 Found\r\nLocation: /final\r\nContent-Length: 0\r\n\r\n"
    )
    second = SyntheticSocket(b"HTTP/1.1 200 OK\r\nContent-Length: 2\r\n\r\nok")
    sockets = iter([first, second])
    monkeypatch.setattr(transport.socket, "socket", lambda *args: next(sockets))
    monkeypatch.setenv("HTTP_PROXY", "http://127.0.0.1:8080")
    resolved = []

    def resolve(url):
        resolved.append(url)
        return "evidence.example", 80, ("93.184.216.34",)

    with transport.open_public_url(
        urllib.request.Request("http://evidence.example/start"), 5, resolve
    ) as response:
        assert response.read() == b"ok"
        assert response.geturl() == "http://evidence.example/final"
    assert resolved == [
        "http://evidence.example/start",
        "http://evidence.example/final",
    ]
    assert first.closed and second.closed
    assert second.address == ("93.184.216.34", 80)
    assert second.sent.startswith(b"GET /final HTTP/1.1")


@pytest.mark.parametrize(
    "phase", ["headers", "length_body", "unframed_body", "chunked_body"]
)
def test_public_get_deadline_interrupts_trickled_response(monkeypatch, phase):
    """Real socketpair exercises HTTP buffering without an external endpoint."""
    import socket
    import threading
    import time

    transport = _transport()
    client, server = socket.socketpair()
    server.settimeout(1)
    budget = 0.15
    header = b"HTTP/1.1 200 OK\r\nContent-Length: 30\r\n\r\n"
    chunks = [b"x"] * 30
    if phase == "headers":
        chunks = [bytes([byte]) for byte in header]
        header = b""
    elif phase == "unframed_body":
        header = b"HTTP/1.1 200 OK\r\nConnection: close\r\n\r\n"
    elif phase == "chunked_body":
        header = b"HTTP/1.1 200 OK\r\nTransfer-Encoding: chunked\r\n\r\n"
        chunks = [b"1\r\nx\r\n"] * 30 + [b"0\r\n\r\n"]

    def send_response():
        with server:
            try:
                server.recv(4096)
                server.sendall(header)
                for chunk in chunks:
                    time.sleep(0.03)
                    server.sendall(chunk)
            except (BrokenPipeError, ConnectionResetError):
                pass

    def connect(address, port, timeout, *, deadline):
        client.settimeout(timeout)
        deadline.watch(client)
        return client

    monkeypatch.setattr(transport, "_connect_pinned_socket", connect)
    worker = threading.Thread(target=send_response, daemon=True)
    worker.start()
    started = time.monotonic()
    try:
        with pytest.raises(TimeoutError, match="elapsed-time budget"):
            with transport.open_public_url(
                urllib.request.Request("http://synthetic.example"),
                budget,
                lambda url: ("synthetic.example", 80, ("93.184.216.34",)),
            ) as response:
                response.read(100)
    finally:
        client.close()
        worker.join(timeout=1)
    assert time.monotonic() - started < 0.65
    assert not worker.is_alive()


@pytest.mark.parametrize("timeout", [0, -1, float("inf"), float("nan")])
def test_public_get_rejects_invalid_deadline_before_resolution(timeout):
    transport = _transport()

    def unexpected_resolver(url):
        pytest.fail("Invalid time budget must fail before resolution")

    with pytest.raises(ValueError, match="finite and positive"):
        transport.open_public_url(
            urllib.request.Request("http://synthetic.example"),
            timeout,
            unexpected_resolver,
        )


def test_public_get_expired_resolution_never_connects(monkeypatch):
    transport = _transport()
    clock = [0.0]
    monkeypatch.setattr(transport.time, "monotonic", lambda: clock[0])

    def resolve(url):
        clock[0] = 6.0
        return "synthetic.example", 80, ("93.184.216.34",)

    def unexpected_connect(*args, **kwargs):
        pytest.fail("Expired resolution must not be followed by a connection")

    monkeypatch.setattr(transport, "_connect_pinned_socket", unexpected_connect)
    with pytest.raises(TimeoutError, match="elapsed-time budget"):
        transport.open_public_url(
            urllib.request.Request("http://synthetic.example"), 5, resolve
        )


def test_public_get_address_retries_share_remaining_budget(monkeypatch):
    transport = _transport()
    clock = [0.0]
    budgets = []
    sock = SyntheticSocket(b"HTTP/1.1 200 OK\r\nContent-Length: 2\r\n\r\nok")
    monkeypatch.setattr(transport.time, "monotonic", lambda: clock[0])

    def connect(address, port, timeout, *, deadline):
        budgets.append(timeout)
        if address == "93.184.216.34":
            clock[0] = 3.0
            raise OSError("Synthetic first-address failure")
        return sock

    monkeypatch.setattr(transport, "_connect_pinned_socket", connect)
    with transport.open_public_url(
        urllib.request.Request("http://synthetic.example"),
        5,
        lambda url: (
            "synthetic.example",
            80,
            ("93.184.216.34", "93.184.216.35"),
        ),
    ) as response:
        assert response.read() == b"ok"
    assert budgets == [5.0, 2.0]
    assert sock.closed


def test_public_get_redirect_does_not_restart_deadline(monkeypatch):
    transport = _transport()
    clock = [0.0]
    sock = SyntheticSocket(
        b"HTTP/1.1 302 Found\r\nLocation: /final\r\nContent-Length: 0\r\n\r\n"
    )
    connections = []
    monkeypatch.setattr(transport.time, "monotonic", lambda: clock[0])

    def connect(address, port, timeout, *, deadline):
        connections.append(address)
        return sock

    def resolve(url):
        clock[0] += 3.0
        return "synthetic.example", 80, ("93.184.216.34",)

    monkeypatch.setattr(transport, "_connect_pinned_socket", connect)
    with pytest.raises(TimeoutError, match="elapsed-time budget"):
        transport.open_public_url(
            urllib.request.Request("http://synthetic.example"), 5, resolve
        )
    assert connections == ["93.184.216.34"]
    assert sock.closed


def test_public_get_interrupt_closes_owned_socket(monkeypatch):
    transport = _transport()
    sock = SyntheticSocket(b"")

    def interrupted_send(data):
        raise KeyboardInterrupt()

    monkeypatch.setattr(sock, "sendall", interrupted_send)
    monkeypatch.setattr(transport.socket, "socket", lambda *args: sock)
    with pytest.raises(KeyboardInterrupt):
        transport.open_public_url(
            urllib.request.Request("http://synthetic.example"),
            5,
            lambda url: ("synthetic.example", 80, ("93.184.216.34",)),
        )
    assert sock.closed
