from __future__ import annotations

from typing import Any, Mapping

from journal_ingest.config import LayoutConfig


def generate_layout(
    file_bytes: bytes, meta: Mapping[str, Any] | None = None
) -> LayoutConfig:
    """Stub for an automated layout generator.

    The real implementation may use external services and is disabled by default.
    """
    raise NotImplementedError("Agent generation is not implemented.")
