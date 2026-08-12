from __future__ import annotations

import argparse
import json
import logging
import secrets
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from apertura_pratica_core import (
    ValidationError,
    load_json,
    prepare_review,
    review_payload_hash,
    utc_now,
    write_json,
)

ASSET = Path(__file__).resolve().parents[1] / "assets" / "apertura-pratica-review.html"
MAX_REQUEST_BYTES = 512 * 1024


class ReviewHandler(BaseHTTPRequestHandler):
    run_dir: Path
    token: str
    page: bytes

    def _path(self, suffix: str) -> str:
        return f"/{self.token}{suffix}"

    def _send(self, status: HTTPStatus, body: bytes, content_type: str) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header(
            "Content-Security-Policy",
            "default-src 'self'; style-src 'unsafe-inline'; script-src 'unsafe-inline'; connect-src 'self'; frame-ancestors 'none'; base-uri 'none'",
        )
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "no-referrer")
        self.end_headers()
        self.wfile.write(body)

    def _json(self, status: HTTPStatus, payload: Any) -> None:
        self._send(
            status,
            json.dumps(payload, ensure_ascii=False).encode("utf-8"),
            "application/json; charset=utf-8",
        )

    def do_GET(self) -> None:  # noqa: N802
        path = urlparse(self.path).path
        if path in {self._path(""), self._path("/")}:
            self._send(HTTPStatus.OK, self.page, "text/html; charset=utf-8")
            return
        if path == self._path("/api/review"):
            try:
                payload = load_json(self.run_dir / "review_payload.json")
            except ValidationError as exc:
                self._json(HTTPStatus.CONFLICT, {"error": str(exc)})
                return
            self._json(
                HTTPStatus.OK,
                {
                    "review": payload,
                    "review_payload_sha256": review_payload_hash(payload),
                },
            )
            return
        self._json(HTTPStatus.NOT_FOUND, {"error": "not found"})

    def do_POST(self) -> None:  # noqa: N802
        if urlparse(self.path).path != self._path("/api/decisions"):
            self._json(HTTPStatus.NOT_FOUND, {"error": "not found"})
            return
        try:
            length = int(self.headers.get("Content-Length", "0"))
        except ValueError:
            self._json(HTTPStatus.BAD_REQUEST, {"error": "invalid content length"})
            return
        if length <= 0 or length > MAX_REQUEST_BYTES:
            self._json(
                HTTPStatus.REQUEST_ENTITY_TOO_LARGE, {"error": "invalid request size"}
            )
            return
        try:
            submitted = json.loads(self.rfile.read(length))
            review = load_json(self.run_dir / "review_payload.json")
            if not isinstance(submitted, dict) or not isinstance(
                submitted.get("decisions"), list
            ):
                raise ValidationError("Decisions payload is incomplete.")
            reviewer = str(submitted.get("reviewer", "")).strip()
            if not reviewer:
                raise ValidationError("Reviewer is required.")
            pending = {
                "schema_version": "1.0",
                "workflow": "apertura-pratica",
                "run_id": review["run_id"],
                "intake_sha256": review["intake_sha256"],
                "review_payload_sha256": review_payload_hash(review),
                "reviewer": reviewer,
                "decision_source": "local_workbench",
                "confirmed_by_user": True,
                "saved_at": utc_now(),
                "decisions": submitted["decisions"],
            }
            write_json(self.run_dir / "pending_review_decisions.json", pending)
        except (json.JSONDecodeError, ValidationError, OSError) as exc:
            self._json(HTTPStatus.BAD_REQUEST, {"error": str(exc)})
            return
        self._json(
            HTTPStatus.OK,
            {"saved": True, "path": "pending_review_decisions.json", "applied": False},
        )

    def log_message(self, message: str, *args: object) -> None:
        logging.info("review-ui %s", message % args)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Serve the local Apertura pratica review workbench."
    )
    parser.add_argument("run_dir", type=Path)
    parser.add_argument("--port", type=int, default=0)
    args = parser.parse_args()
    try:
        prepare_review(args.run_dir)
        page = ASSET.read_bytes()
    except (ValidationError, OSError) as exc:
        logging.error("%s", exc)
        return 2
    token = secrets.token_urlsafe(24)
    handler = type(
        "BoundReviewHandler",
        (ReviewHandler,),
        {"run_dir": args.run_dir.resolve(), "token": token, "page": page},
    )
    server = ThreadingHTTPServer(("127.0.0.1", args.port), handler)
    host, port = server.server_address
    logging.info("Review workbench: http://%s:%s/%s/", host, port, token)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        return 0
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    raise SystemExit(main())
