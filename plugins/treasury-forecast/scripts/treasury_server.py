"""Loopback-only review; each write revalidates the archive and exact version."""

from __future__ import annotations

import hmac
import json
import logging
import secrets
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Callable
from urllib.parse import parse_qs, urlparse

from treasury_core import TreasuryError
from treasury_session import current_record, review_session, save_scenario

__all__ = ["make_server", "serve"]


def make_server(
    output: Path, validate: Callable[[], Any], *, port: int = 0
) -> tuple[ThreadingHTTPServer, str]:
    """Serve declared assets and bounded case data with an ephemeral token."""
    token = secrets.token_urlsafe(32)
    assets = Path(__file__).resolve().parents[1] / "assets"

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, format: str, *args: Any) -> None:
            logging.debug("Treasury HTTP request completed")

        def send(self, status: int, content: bytes, media: str) -> None:
            self.send_response(status)
            self.send_header("Content-Type", media)
            self.send_header("Content-Length", str(len(content)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("Referrer-Policy", "no-referrer")
            self.send_header(
                "Content-Security-Policy",
                "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; connect-src 'self'; frame-ancestors 'none'; base-uri 'none'",
            )
            self.end_headers()
            self.wfile.write(content)

        def json(self, status: int, value: Any) -> None:
            self.send(
                status,
                json.dumps(value, ensure_ascii=False, allow_nan=False).encode(),
                "application/json; charset=utf-8",
            )

        def authenticated(self) -> bool:
            return hmac.compare_digest(self.headers.get("X-Treasury-Token", ""), token)

        def do_GET(self) -> None:
            parsed = urlparse(self.path)
            if parsed.path in {
                "/",
                "/review.js",
                "/review.css",
                "/custom_select.js",
                "/instrument-sans-400.ttf",
            }:
                filename = {
                    "/": "review.html",
                    "/review.js": "review.js",
                    "/review.css": "review.css",
                    "/custom_select.js": "custom_select.js",
                    "/instrument-sans-400.ttf": "instrument-sans-400.ttf",
                }[parsed.path]
                media = {
                    "/": "text/html",
                    "/review.js": "text/javascript",
                    "/review.css": "text/css",
                    "/custom_select.js": "text/javascript",
                    "/instrument-sans-400.ttf": "font/ttf",
                }[parsed.path]
                self.send(
                    200, (assets / filename).read_bytes(), media + "; charset=utf-8"
                )
                return
            if not self.authenticated():
                self.json(403, {"error": "Session token required"})
                return
            try:
                validate()
                _, record = current_record(output)
                if parsed.path == "/api/state":
                    query = parse_qs(parsed.query)
                    offset = int(query.get("offset", ["0"])[0])
                    if not 0 <= offset <= len(record["events"]):
                        raise TreasuryError("Invalid page offset")
                    selected = {
                        key: record[key]
                        for key in (
                            "record_sha256",
                            "proposal_sha256",
                            "company_name",
                            "as_of",
                            "horizon_end",
                            "status",
                            "opening_cash",
                            "minimum_daily_cash",
                            "first_negative_day",
                            "calculation_complete",
                            "coverage",
                            "review",
                        )
                    }
                    selected.update(
                        events=record["events"][offset : offset + 100],
                        total_events=len(record["events"]),
                        offset=offset,
                        issue_count=len(record["issues"]),
                        issues=record["issues"][:100],
                        comparison={
                            k: v
                            for k, v in (record["comparison"] or {}).items()
                            if k != "changes"
                        },
                        changes=(record["comparison"] or {}).get("changes", [])[:100],
                        evidence_notes=record["evidence_notes"][:100],
                        daily=record["daily"] if record["calculation_complete"] else [],
                    )
                    self.json(200, selected)
                elif parsed.path in {"/api/workbook", "/api/report"}:
                    filename = (
                        "tesoreria.xlsx"
                        if parsed.path.endswith("workbook")
                        else "report.html"
                    )
                    path = output / "versions" / record["record_sha256"] / filename
                    media = (
                        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                        if filename.endswith("xlsx")
                        else "text/html; charset=utf-8"
                    )
                    self.send(200, path.read_bytes(), media)
                else:
                    self.json(404, {"error": "Unknown route"})
            except (TreasuryError, ValueError, KeyError, OSError) as exc:
                self.json(409, {"error": str(exc)})

        def do_POST(self) -> None:
            expected_origin = f"http://127.0.0.1:{self.server.server_port}"
            if (
                not self.authenticated()
                or self.headers.get("Origin") != expected_origin
            ):
                self.json(403, {"error": "Same-origin authenticated writes only"})
                return
            try:
                size = int(self.headers.get("Content-Length", "0"))
                if not 0 < size <= 1024 * 1024:
                    raise TreasuryError("Invalid request size")
                request = json.loads(self.rfile.read(size))
                if not isinstance(request, dict):
                    raise TreasuryError("Expected a request object")
                validate()
                if self.path == "/api/review":
                    record = review_session(
                        output,
                        expected_record_sha256=request["record_sha256"],
                        decisions=request.get("decisions"),
                        review=request.get("review"),
                    )
                    self.json(
                        200,
                        {
                            "record_sha256": record["record_sha256"],
                            "status": record["status"],
                        },
                    )
                elif self.path == "/api/scenario":
                    self.json(
                        200,
                        save_scenario(
                            output,
                            expected_record_sha256=request["record_sha256"],
                            dates=request["dates"],
                        ),
                    )
                else:
                    self.json(404, {"error": "Unknown route"})
            except (TreasuryError, ValueError, KeyError, OSError) as exc:
                self.json(409, {"error": str(exc)})

    return ThreadingHTTPServer(("127.0.0.1", port), Handler), token


def serve(output: Path, validate: Callable[[], Any], *, port: int = 0) -> None:
    server, token = make_server(output, validate, port=port)
    logging.info("Review: http://127.0.0.1:%s/#token=%s", server.server_port, token)
    try:
        server.serve_forever()
    finally:
        server.server_close()
