"""Isolated inference process: raw text, spans and library diagnostics stay here."""

from __future__ import annotations

import contextlib
import json
import os
import socket
import sys
from collections import Counter
from dataclasses import asdict
from pathlib import Path
from typing import Any

from .contracts import LABELS, FilteredDocument, FilterError
from .extract import extract_text

__all__ = ["filter_document", "main"]


class _OfflineSocket(socket.socket):
    """Block Python outbound connections, including a tokenizer cache miss."""

    def connect(self, address: Any) -> None:
        raise OSError("network_disabled_during_filtering")

    def connect_ex(self, address: Any) -> int:
        raise OSError("network_disabled_during_filtering")


def filter_document(path: Path, model: Any) -> FilteredDocument:
    """Apply model spans using fixed placeholders; never serialize OPF results."""
    text = extract_text(path)
    result = model.redact(text)
    if result.warning is not None or result.text != text:
        raise FilterError("tokenizer_roundtrip_mismatch")
    cursor = 0
    pieces: list[str] = []
    counts: Counter[str] = Counter()
    for span in result.detected_spans:
        # These are mechanical output checks, not additional PII detection rules.
        if (
            span.label not in LABELS
            or type(span.start) is not int
            or type(span.end) is not int
            or not cursor <= span.start < span.end <= len(text)
        ):
            raise FilterError("invalid_model_spans")
        pieces.extend((text[cursor : span.start], "[" + span.label.upper() + "]"))
        counts[span.label] += 1
        cursor = span.end
    pieces.append(text[cursor:])
    return FilteredDocument("".join(pieces), dict(counts), len(text))


def main() -> None:
    """Accept one local request; stdout contains only the restricted response."""
    socket.socket = _OfflineSocket  # type: ignore[misc]  # Process-local network guard.
    os.environ.update(
        HF_HUB_OFFLINE="1",
        HF_HUB_DISABLE_TELEMETRY="1",
        OPF_TORCH_COMPILE="0",
    )
    request = json.loads(sys.stdin.read())
    os.environ["TIKTOKEN_CACHE_DIR"] = request["tokenizer_cache"]
    response: dict[str, Any]
    # The parent also discards stderr at the process boundary. Library output
    # must never contaminate MCP stdout or enter host diagnostic logs.
    with open(os.devnull, "w") as sink, contextlib.redirect_stdout(sink):
        try:
            import torch
            from opf import OPF

            torch.set_num_threads(4)
            model = OPF(model=request["checkpoint"], device=request["device"])
            path = Path(request["path"]).resolve(strict=True)
            if not path.is_relative_to(Path(request["input_root"])):
                raise FilterError("outside_input_directory")
            response = asdict(filter_document(path, model))
        except FilterError as exc:
            response = {"error": str(exc)}
        except (OSError, ValueError, RuntimeError, ImportError, TypeError, MemoryError):
            response = {"error": "processing_failed"}
    sys.stdout.write(json.dumps(response, ensure_ascii=False))


if __name__ == "__main__":
    main()
