from __future__ import annotations

__all__ = [
    "DeckNotFoundError",
    "SlideNotFoundError",
    "InvalidDeckError",
]


class DeckNotFoundError(FileNotFoundError):
    """Raised when the requested deck directory is missing."""


class SlideNotFoundError(FileNotFoundError):
    """Raised when an expected slide HTML file is missing."""


class InvalidDeckError(ValueError):
    """Raised when a deck cannot be parsed due to malformed inputs."""
