"""Serve a rendered teaching kit on loopback without changing its files."""

from __future__ import annotations

import functools
import json
import logging
import sys
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import BinaryIO

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
