"""Read local files in isolation and call only Rizzo's local text endpoint."""

from __future__ import annotations

import contextlib
import json
import os
import sys
from dataclasses import asdict
from pathlib import Path
from typing import Any

from .contracts import FilterError
from .extract import extract_text
from .rizzo_api import analyze, health

__all__ = ["main"]


def main() -> None:
    """Return a filtered document or a fixed error; suppress raw diagnostics."""
    response: dict[str, Any]
    with open(os.devnull, "w") as sink, contextlib.redirect_stdout(sink):
        try:
            request = json.loads(sys.stdin.read())
            path = Path(request["path"]).resolve(strict=True)
            if not path.is_relative_to(Path(request["input_root"])):
                raise FilterError("outside_input_directory")
            health(request["rizzo_port"])
            response = asdict(analyze(extract_text(path), request["rizzo_port"]))
        except FilterError as exc:
            response = {"error": str(exc)}
        except (OSError, ValueError, TypeError, KeyError, MemoryError):
            response = {"error": "processing_failed"}
    sys.stdout.write(json.dumps(response, ensure_ascii=False))


if __name__ == "__main__":
    main()
