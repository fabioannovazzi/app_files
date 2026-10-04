"""Self-contained loopback API fixture shared by transport acceptance tests."""

from __future__ import annotations

import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from types import SimpleNamespace

import pytest

__all__: list[str] = []


@pytest.fixture
def api():
    state = SimpleNamespace(
        status=200,
        health={
            "status": "ok",
            "model_loaded": True,
            "app_version": "2.0.0",
            "model_version": "1.5.0",
            "device": "cpu",
            "ignored": "secret",
        },
        result={
            "anonymized_text": "[FULLNAME_1] writes.",
            "by_label": {"FULLNAME": 1},
            "mapping_enabled": False,
            "mapping": {},
            "excluded_tags": [],
            "n_chars": 12,
            "n_entities": 1,
            "source_text": "Anna writes.",
            "segments": [{"t": "Anna"}],
        },
        requests=[],
        mapped_result={
            "anonymized_text": "[FULLNAME_1] writes.",
            "by_label": {"FULLNAME": 1},
            "mapping_enabled": True,
            "mapping": {"[FULLNAME_1]": "Anna"},
            "excluded_tags": [],
            "n_chars": 12,
            "n_entities": 1,
            "n_unique": 1,
            "source_text": "Anna writes.",
            "segments": [{"t": "Anna"}],
        },
    )

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            state.requests.append(("GET", self.path))
            self.reply(state.health)

        def do_POST(self):
            body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
            state.requests.append(("POST", self.path, body))
            self.reply(
                state.mapped_result
                if body.get("include_mapping") is True
                else state.result
            )

        def reply(self, body):
            data = body if isinstance(body, bytes) else json.dumps(body).encode()
            self.send_response(state.status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(data)))
            self.send_header("Location", "https://example.com/must-not-follow")
            self.end_headers()
            self.wfile.write(data)

        def log_message(self, *args):
            pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    state.port = server.server_port
    try:
        yield state
    finally:
        server.shutdown()
        server.server_close()
        thread.join()
