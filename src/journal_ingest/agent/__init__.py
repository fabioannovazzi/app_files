"""Optional agent helpers."""

from __future__ import annotations

from typing import Any

from .config_generator import (
    PROMPT_TEMPLATE,
    gate_config,
    propose_layout_config,
)


def generate_layout(*_: Any, **__: Any) -> Any:  # pragma: no cover - stub
    """Stub for an automated layout generator."""
    raise NotImplementedError("Agent generation is not implemented.")


__all__ = [
    "generate_layout",
    "propose_layout_config",
    "gate_config",
    "PROMPT_TEMPLATE",
]
