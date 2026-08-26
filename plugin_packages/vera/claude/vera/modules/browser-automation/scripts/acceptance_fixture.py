#!/usr/bin/env python3
"""Serve a deterministic local page for Browser Automation acceptance tests."""

from __future__ import annotations

import argparse
import hashlib
import io
import json
import logging
import sys
import threading
import zipfile
from http.client import HTTPConnection, HTTPException
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Mapping

__all__ = ["main", "run_self_check", "serve_fixture"]

LOGGER = logging.getLogger(__name__)
SCHEMA_VERSION = "browser-automation-acceptance-fixture/v2"
DOWNLOAD_PATH = "/synthetic-package.zip"
DOWNLOAD_ENTRY_NAME = "vera-browser-acceptance.txt"
DOWNLOAD_ENTRY_BYTES = b"Synthetic Vera browser acceptance artifact.\n"


def _build_download() -> bytes:
    """Build one byte-stable ZIP without filesystem or clock dependencies."""

    archive_buffer = io.BytesIO()
    entry = zipfile.ZipInfo(DOWNLOAD_ENTRY_NAME, date_time=(2026, 1, 1, 0, 0, 0))
    entry.compress_type = zipfile.ZIP_STORED
    entry.create_system = 3
    entry.external_attr = 0o600 << 16
    with zipfile.ZipFile(archive_buffer, mode="w") as archive:
        archive.writestr(entry, DOWNLOAD_ENTRY_BYTES)
    return archive_buffer.getvalue()


DOWNLOAD_BYTES = _build_download()
DOWNLOAD_SHA256 = hashlib.sha256(DOWNLOAD_BYTES).hexdigest()
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
    <label for="client-code">Client code</label>
    <input id="client-code" name="client-code" autocomplete="off">
    <p id="client-state" role="status" aria-live="polite">Client code pending</p>

    <label for="document-type">Document type</label>
    <select id="document-type" name="document-type" data-native-select="true">
      <option value="">Choose a document type</option>
      <option value="Invoice">Invoice</option>
      <option value="Credit note">Credit note</option>
    </select>

    <label><input id="reviewed" name="reviewed" type="checkbox"> Reviewed</label>
    <button id="prepare" type="button">Prepare package</button>
    <p id="result" role="status" aria-live="polite">Waiting</p>
    <a id="download" href="/synthetic-package.zip" hidden>Download synthetic ZIP</a>
  </main>
  <script>
    const clientCode = document.querySelector('#client-code');
    const clientState = document.querySelector('#client-state');
    const documentType = document.querySelector('#document-type');
    const reviewed = document.querySelector('#reviewed');
    const result = document.querySelector('#result');
    const download = document.querySelector('#download');

    clientCode.addEventListener('keydown', (event) => {
      if (event.key !== 'Enter') return;
      event.preventDefault();
      const value = clientCode.value.trim();
      clientCode.dataset.acceptedValue = value;
      clientState.textContent = value ? 'Client code accepted' : 'Client code required';
    });

    document.querySelector('#prepare').addEventListener('click', () => {
      const acceptedClient = clientCode.dataset.acceptedValue || '';
      const currentClient = clientCode.value.trim();
      download.hidden = true;
      if (!currentClient || acceptedClient !== currentClient) {
        result.textContent = 'Accept the client code with Enter';
        return;
      }
      if (!documentType.value) {
        result.textContent = 'Document type required';
        return;
      }
      if (!reviewed.checked) {
        result.textContent = 'Review required';
        return;
      }
      result.textContent = `Package ready: ${documentType.value}; reviewed yes`;
      download.hidden = false;
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

    def _write(
        self,
        status: int,
        content_type: str,
        body: bytes,
        extra_headers: Mapping[str, str] | None = None,
    ) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("Connection", "close")
        for name, value in (extra_headers or {}).items():
            self.send_header(name, value)
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
        if path == DOWNLOAD_PATH:
            self._write(
                200,
                "application/zip",
                DOWNLOAD_BYTES,
                {
                    "Content-Disposition": (
                        'attachment; filename="vera-browser-acceptance.zip"'
                    )
                },
            )
            return
        self._write(404, "text/plain; charset=utf-8", b"Not found\n")

    def log_message(self, format: str, *args: object) -> None:
        LOGGER.debug(format, *args)


def _read_local_response(port: int, path: str) -> tuple[int, Mapping[str, str], bytes]:
    connection = HTTPConnection("127.0.0.1", port, timeout=2)
    try:
        connection.request("GET", path)
        response = connection.getresponse()
        headers = {name.lower(): value for name, value in response.getheaders()}
        return response.status, headers, response.read()
    finally:
        connection.close()


def _probe(port: int) -> None:
    """Verify the bound server before advertising it to connected Chrome."""

    health_status, _, health_body = _read_local_response(port, "/healthz")
    if health_status != 200:
        raise RuntimeError("Local acceptance fixture health endpoint failed.")
    payload = json.loads(health_body.decode("utf-8"))
    if payload != {"schema_version": SCHEMA_VERSION, "status": "ready"}:
        raise RuntimeError(
            "Local acceptance fixture returned an invalid health record."
        )
    page_status, _, page_body = _read_local_response(port, "/")
    required_page_markers = (
        b"Vera browser acceptance fixture",
        b">Client code</label>",
        b">Document type</label>",
        b'<option value="Invoice">Invoice</option>',
        b" Reviewed</label>",
        b">Prepare package</button>",
        b">Download synthetic ZIP</a>",
        b'role="status"',
    )
    if page_status != 200 or any(
        marker not in page_body for marker in required_page_markers
    ):
        raise RuntimeError("Local acceptance fixture page is incomplete.")
    download_status, download_headers, download_body = _read_local_response(
        port, DOWNLOAD_PATH
    )
    if (
        download_status != 200
        or download_headers.get("content-type") != "application/zip"
        or "attachment;" not in download_headers.get("content-disposition", "")
        or hashlib.sha256(download_body).hexdigest() != DOWNLOAD_SHA256
    ):
        raise RuntimeError("Local acceptance fixture download is invalid.")
    with zipfile.ZipFile(io.BytesIO(download_body)) as archive:
        if (
            archive.namelist() != [DOWNLOAD_ENTRY_NAME]
            or archive.read(DOWNLOAD_ENTRY_NAME) != DOWNLOAD_ENTRY_BYTES
        ):
            raise RuntimeError("Local acceptance fixture ZIP contents are invalid.")


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
            "client_code_label": "Client code",
            "client_code_submit_key": "Enter",
            "client_ready_text": "Client code accepted",
            "document_type_label": "Document type",
            "document_type_value": "Invoice",
            "reviewed_label": "Reviewed",
            "action_name": "Prepare package",
            "result_role": "status",
            "terminal_text": "Package ready: Invoice; reviewed yes",
            "download_name": "Download synthetic ZIP",
            "download_path": DOWNLOAD_PATH,
            "download_entry_name": DOWNLOAD_ENTRY_NAME,
            "download_byte_length": len(DOWNLOAD_BYTES),
            "download_sha256": DOWNLOAD_SHA256,
            "operation_contract": [
                "goto",
                "wait_for",
                "fill",
                "press",
                "select",
                "set_checked",
                "click",
                "extract",
                "download",
            ],
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
