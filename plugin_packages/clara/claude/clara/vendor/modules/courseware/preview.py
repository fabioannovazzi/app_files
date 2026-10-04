"""Serve a rendered teaching kit on loopback without changing its files."""

from __future__ import annotations

import functools
import json
import logging
import sys
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import BinaryIO
from urllib.parse import quote

__all__ = ["create_server", "serve"]


class _KitHandler(SimpleHTTPRequestHandler):
    """Keep file requests inside the kit, including requests through symlinks."""

    def send_head(self) -> BinaryIO | None:
        root = Path(self.directory).resolve()
        requested = Path(self.translate_path(self.path)).resolve()
        if not requested.is_relative_to(root):
            self.send_error(403)
            return None
        return super().send_head()

    def end_headers(self) -> None:
        # Native documents are downloads; readable PDF pages have their own HTML view.
        requested = Path(self.translate_path(self.path))
        if (
            requested.suffix.lower() == ".html"
            and requested.is_relative_to(Path(self.directory) / "decks")
            and requested.is_file()
        ):
            from .deck_view import deck_csp

            self.send_header("Content-Security-Policy", deck_csp(requested.read_text()))
            self.send_header("X-Content-Type-Options", "nosniff")
        if (
            requested.suffix.lower() in {".xlsx", ".docx", ".pdf", ".xml"}
            and requested.is_file()
        ):
            self.send_header(
                "Content-Disposition",
                "attachment; filename*=UTF-8''" + quote(requested.name, safe=""),
            )
        # Original HTML result bytes are readable but cannot execute code,
        # submit forms, load external resources or escape the reading frame.
        if requested.suffix.lower() == ".html" and requested.parent.name == "outputs":
            self.send_header(
                "Content-Security-Policy",
                "sandbox; default-src 'none'; style-src 'unsafe-inline'; base-uri 'none'; form-action 'none'",
            )
            self.send_header("X-Content-Type-Options", "nosniff")
        # A validated website lesson retains its exact HTML/CSS and local assets.
        # It remains passive: no scripts, forms, popups or external asset loads.
        if requested.is_relative_to(Path(self.directory) / "website"):
            self.send_header(
                "Content-Security-Policy",
                "sandbox; default-src 'none'; style-src 'self' 'unsafe-inline'; "
                "img-src 'self' data:; font-src 'self'; base-uri 'none'; form-action 'none'",
            )
            self.send_header("X-Content-Type-Options", "nosniff")
        super().end_headers()

    def list_directory(self, path: str) -> None:
        """Do not expose directory inventories."""
        self.send_error(403)
        return None

    def log_message(self, format: str, *args: object) -> None:
        logging.getLogger(__name__).debug(format, *args)


def create_server(directory: Path) -> ThreadingHTTPServer:
    """Bind a free loopback port for a materialized course and its assets."""
    directory = directory.resolve(strict=True)
    if not (directory / "course.html").is_file():
        raise OSError("Preview requires a rendered kit containing course.html")
    handler = functools.partial(_KitHandler, directory=str(directory))
    return ThreadingHTTPServer(("127.0.0.1", 0), handler)


def serve(directory: Path) -> None:
    """Emit readiness, then remain alive until the managed session is stopped."""
    with create_server(directory) as server:
        sys.stdout.write(
            json.dumps(
                {
                    "status": "serving",
                    "url": f"http://127.0.0.1:{server.server_port}/course.html",
                    "browser_status": "not_requested",
                }
            )
            + "\n"
        )
        sys.stdout.flush()
        try:
            server.serve_forever()
        except KeyboardInterrupt:
            pass
