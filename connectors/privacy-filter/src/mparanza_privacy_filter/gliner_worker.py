"""Isolated GLiNER2 inference: original text and detected values stay local."""

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

from .contracts import FilteredDocument, FilterError
from .engines import GLINER2
from .extract import extract_text
from .worker import _OfflineSocket

__all__ = ["filter_document", "main"]


def filter_document(path: Path, model: Any) -> FilteredDocument:
    """Mask validated global offsets, covering the union of overlapping spans."""
    text = extract_text(path)
    result = model.extract_entities_long(
        text,
        sorted(GLINER2.labels),
        threshold=0.5,
        chunk_size=256,
        chunk_overlap=64,
        batch_size=1,
        include_spans=True,
        overlap_policy="allow",
    )
    if not isinstance(result, dict) or not isinstance(result.get("entities"), dict):
        raise FilterError("invalid_model_spans")
    spans: set[tuple[int, int, str]] = set()
    for label, values in result["entities"].items():
        if label not in GLINER2.labels or not isinstance(values, list):
            raise FilterError("invalid_model_spans")
        for value in values:
            if not isinstance(value, dict):
                raise FilterError("invalid_model_spans")
            start, end = value.get("start"), value.get("end")
            # Exact offsets and allowlisted labels are a mechanical privacy
            # boundary. No regex or heuristic is used to detect extra PII.
            if (
                type(start) is not int
                or type(end) is not int
                or not 0 <= start < end <= len(text)
                or value.get("text") != text[start:end]
            ):
                raise FilterError("invalid_model_spans")
            spans.add((start, end, label))
    counts: Counter[str] = Counter(label for _, _, label in spans)
    regions: list[tuple[int, int, str]] = []
    for start, end, label in sorted(
        spans, key=lambda span: (span[0], -span[1], span[2])
    ):
        if regions and start < regions[-1][1]:
            left, right, first_label = regions[-1]
            regions[-1] = (left, max(right, end), first_label)
        else:
            regions.append((start, end, label))
    pieces: list[str] = []
    cursor = 0
    for start, end, label in regions:
        pieces.extend((text[cursor:start], "[" + label.upper() + "]"))
        cursor = end
    pieces.append(text[cursor:])
    return FilteredDocument("".join(pieces), dict(counts), len(text))


def main() -> None:
    """Load only local assets and return the shared restricted worker contract."""
    socket.socket = _OfflineSocket  # type: ignore[misc]  # Process-local network guard.
    os.environ.update(
        HF_HUB_OFFLINE="1",
        HF_HUB_DISABLE_TELEMETRY="1",
        TRANSFORMERS_OFFLINE="1",
        TOKENIZERS_PARALLELISM="false",
    )
    response: dict[str, Any]
    with open(os.devnull, "w") as sink, contextlib.redirect_stdout(sink):
        try:
            request = json.loads(sys.stdin.read())
            path = Path(request["path"]).resolve(strict=True)
            if not path.is_relative_to(Path(request["input_root"])):
                raise FilterError("outside_input_directory")
            import torch
            from gliner2 import GLiNER2

            torch.set_num_threads(4)
            model = GLiNER2.from_pretrained(
                request["checkpoint"],
                local_files_only=True,
                map_location=request["device"],
            )
            model.eval()
            with torch.inference_mode():
                response = asdict(filter_document(path, model))
        except FilterError as exc:
            response = {"error": str(exc)}
        except (
            OSError,
            ValueError,
            RuntimeError,
            ImportError,
            TypeError,
            MemoryError,
            KeyError,
            AttributeError,
        ):
            response = {"error": "processing_failed"}
    sys.stdout.write(json.dumps(response, ensure_ascii=False))


if __name__ == "__main__":
    main()
