"""Utilities for applying the shared legacy theme."""

from modules.layout.core.ui_adapter import ui


def load_theme() -> None:
    """No-op placeholder for the deprecated UI theme."""
    ui.info("Legacy theme assets have been removed.")


__all__ = ["load_theme"]
