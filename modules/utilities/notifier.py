from __future__ import annotations

import logging
from typing import Any, Protocol

__all__ = ["Notifier", "LoggingNotifier", "get_notifier"]


class Notifier(Protocol):
    def info(self, message: str, **kwargs: Any) -> None:
        ...

    def warning(self, message: str, **kwargs: Any) -> None:
        ...

    def error(self, message: str, **kwargs: Any) -> None:
        ...


class LoggingNotifier:
    def __init__(self, logger: logging.Logger | None = None) -> None:
        self._logger = logger or logging.getLogger(__name__)

    def info(self, message: str, **kwargs: Any) -> None:
        self._logger.info(message, **kwargs)

    def warning(self, message: str, **kwargs: Any) -> None:
        self._logger.warning(message, **kwargs)

    def error(self, message: str, **kwargs: Any) -> None:
        self._logger.error(message, **kwargs)


def get_notifier(
    notifier: Notifier | None, logger: logging.Logger | None = None
) -> Notifier:
    if notifier is None:
        return LoggingNotifier(logger)
    return notifier
