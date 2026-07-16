"""Utilities for checking journal entries programmatically."""

__all__ = ["check_entries_pipeline", "PartialCheckError"]


def __getattr__(name: str):  # pragma: no cover - lazy import
    if name in __all__:
        from .service import PartialCheckError, check_entries_pipeline

        return locals()[name]
    raise AttributeError(name)
