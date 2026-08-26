#!/usr/bin/env python3
"""Serve a deterministic local page for Browser Automation acceptance tests."""

from __future__ import annotations

import argparse
import json
import logging
import sys
import threading
from http.client import HTTPConnection, HTTPException
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

__all__ = ["main", "run_self_check", "serve_fixture"]

LOGGER = logging.getLogger(__name__)
SCHEMA_VERSION = "browser-automation-acceptance-fixture/v1"
FIXTURE_HTML = b"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width,initial-scale=1">
  <link rel="icon" href="data:,">
  <title>Vera browser acceptance fixture</title>
</head>
<body>
  <main>
    <h1>Vera browser acceptance fixture</h1>
    <label for="reference">Reference</label>
    <input id="reference" name="reference" autocomplete="off">
    <label><input id="archive" type="checkbox"> Include archive</label>
    <button id="prepare" type="button">Prepare</button>
    <p id="result" role="status" aria-live="polite">Waiting</p>
  </main>
  <script>
    document.querySelector('#prepare').addEventListener('click', () => {
      const reference = document.querySelector('#reference').value.trim();
      const archive = document.querySelector('#archive').checked ? 'yes' : 'no';
      document.querySelector('#result').textContent =
        reference ? `Prepared ${reference}; archive ${archive}` : 'Reference required';
    });
  </script>
</body>
</html>
"""


class _FixtureServer(ThreadingHTTPServer):
    """Threaded loopback server with fast socket reuse between test runs."""

    allow_reuse_address = True
    daemon_threads = True


class _FixtureHandler(BaseHTTPRequestHandler):
    """Return self-contained responses that never wait on external resources."""

    protocol_version = "HTTP/1.0"

    def _write(self, status: int, content_type: str, body: bytes) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("Connection", "close")
        self.end_headers()
        self.wfile.write(body)
        self.close_connection = True

    def do_GET(self) -> None:  # noqa: N802 - BaseHTTPRequestHandler API
        path = self.path.split("?", 1)[0]
        if path == "/":
            self._write(200, "text/html; charset=utf-8", FIXTURE_HTML)
            return
        if path == "/healthz":
            body = json.dumps(
                {"schema_version": SCHEMA_VERSION, "status": "ready"},
                sort_keys=True,
            ).encode("utf-8")
            self._write(200, "application/json; charset=utf-8", body)
            return
        self._write(404, "text/plain; charset=utf-8", b"Not found\n")

    def log_message(self, format: str, *args: object) -> None:
        LOGGER.debug(format, *args)


def _read_local_response(port: int, path: str) -> tuple[int, bytes]:
    connection = HTTPConnection("127.0.0.1", port, timeout=2)
    try:
        connection.request("GET", path)
        response = connection.getresponse()
        return response.status, response.read()
    finally:
        connection.close()


def _probe(port: int) -> None:
    """Verify the bound server before advertising it to connected Chrome."""

    health_status, health_body = _read_local_response(port, "/healthz")
    if health_status != 200:
        raise RuntimeError("Local acceptance fixture health endpoint failed.")
    payload = json.loads(health_body.decode("utf-8"))
    if payload != {"schema_version": SCHEMA_VERSION, "status": "ready"}:
        raise RuntimeError(
            "Local acceptance fixture returned an invalid health record."
        )
    page_status, page_body = _read_local_response(port, "/")
    required_page_markers = (
        b"Vera browser acceptance fixture",
        b">Reference</label>",
        b" Include archive</label>",
        b">Prepare</button>",
        b'role="status"',
    )
    if page_status != 200 or any(
        marker not in page_body for marker in required_page_markers
    ):
        raise RuntimeError("Local acceptance fixture page is incomplete.")


def _ready_record(server: _FixtureServer) -> dict[str, object]:
    port = int(server.server_address[1])
    origin = f"http://127.0.0.1:{port}"
    return {
        "schema_version": SCHEMA_VERSION,
        "status": "ready",
        "origin": origin,
        "page_url": f"{origin}/",
        "health_url": f"{origin}/healthz",
        "process": {
            "heading": "Vera browser acceptance fixture",
            "reference_label": "Reference",
            "archive_label": "Include archive",
            "action_name": "Prepare",
            "result_role": "status",
        },
    }


def _start_server(port: int) -> tuple[_FixtureServer, threading.Thread]:
    server = _FixtureServer(("127.0.0.1", port), _FixtureHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return server, thread


def run_self_check(port: int = 0) -> dict[str, object]:
    """Start, probe, and stop one fixture without opening a browser."""

    server, thread = _start_server(port)
    try:
        ready = _ready_record(server)
        _probe(int(server.server_address[1]))
        return ready
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)


def serve_fixture(port: int = 0) -> None:
    """Serve until interrupted after emitting one machine-readable ready line."""

    server, thread = _start_server(port)
    try:
        ready = _ready_record(server)
        _probe(int(server.server_address[1]))
        sys.stdout.write(json.dumps(ready, sort_keys=True) + "\n")
        sys.stdout.flush()
        thread.join()
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)


def main(argv: list[str] | None = None) -> int:
    """Run the fixture server or its bounded local self-check."""

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", type=int, default=0)
    parser.add_argument("--self-check", action="store_true")
    args = parser.parse_args(argv)
    if args.port < 0 or args.port > 65535:
        parser.error("--port must be between 0 and 65535")
    try:
        if args.self_check:
            sys.stdout.write(
                json.dumps(run_self_check(args.port), sort_keys=True) + "\n"
            )
        else:
            serve_fixture(args.port)
    except KeyboardInterrupt:
        return 0
    except (OSError, RuntimeError, HTTPException, json.JSONDecodeError) as error:
        LOGGER.error("Browser Automation acceptance fixture failed: %s", error)
        return 1
    return 0


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    raise SystemExit(main())
