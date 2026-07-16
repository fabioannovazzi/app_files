from __future__ import annotations

import contextlib
import contextvars
import logging
from typing import Any, Callable, Iterable, Mapping, Protocol

__all__ = [
    "EventCollector",
    "FastAPINotifier",
    "Notifier",
    "NotifierEvent",
    "NullNotifier",
    "UIEventCollector",
    "get_ui_notifier",
    "set_ui_notifier",
    "ui",
    "use_ui_notifier",
]

LOGGER = logging.getLogger(__name__)

NotifierEvent = dict[str, Any]


class UIContainer(Protocol):
    def __enter__(self) -> "UIContainer":
        ...

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: Any | None,
    ) -> None:
        ...


class Notifier(Protocol):
    """Structured notification interface for logging UI-adjacent events."""

    def notify(
        self,
        level: str,
        message: str,
        context: Mapping[str, Any] | None = None,
    ) -> None:
        ...

    def info(self, message: str, **context: Any) -> None:
        ...

    def warning(self, message: str, **context: Any) -> None:
        ...

    def error(self, message: str, **context: Any) -> None:
        ...

    def success(self, message: str, **context: Any) -> None:
        ...


class NullContainer:
    def __enter__(self) -> "NullContainer":
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: Any | None,
    ) -> None:
        return None


class EventCollector:
    def __init__(self) -> None:
        self.events: list[NotifierEvent] = []

    def notify(
        self,
        level: str,
        message: str,
        context: Mapping[str, Any] | None = None,
    ) -> None:
        self.events.append({"level": level, "message": message, "context": dict(context or {})})

    def info(self, message: str, **context: Any) -> None:
        self.notify("info", str(message), context)

    def warning(self, message: str, **context: Any) -> None:
        self.notify("warning", str(message), context)

    def error(self, message: str, **context: Any) -> None:
        self.notify("error", str(message), context)

    def success(self, message: str, **context: Any) -> None:
        self.notify("success", str(message), context)


class NullNotifier(EventCollector):
    def notify(
        self,
        level: str,
        message: str,
        context: Mapping[str, Any] | None = None,
    ) -> None:
        return None

    def __getattr__(self, name: str) -> Callable[..., Any]:
        def _noop(*_args: Any, **_kwargs: Any) -> Any:
            return ""

        return _noop


class FastAPINotifier(EventCollector):
    def __init__(self, *, logger: logging.Logger | None = None) -> None:
        super().__init__()
        self._logger = logger or LOGGER

    def notify(
        self,
        level: str,
        message: str,
        context: Mapping[str, Any] | None = None,
    ) -> None:
        super().notify(level, message, context)
        if level in {"error", "warning"}:
            self._logger.warning("Notifier %s: %s", level, message)
        else:
            self._logger.info("Notifier %s: %s", level, message)


_current_notifier: contextvars.ContextVar[Notifier] = contextvars.ContextVar(
    "_current_notifier",
    default=NullNotifier(),
)


def get_ui_notifier() -> Notifier:
    return _current_notifier.get()


def set_ui_notifier(notifier: Notifier) -> contextvars.Token[Notifier]:
    return _current_notifier.set(notifier)


@contextlib.contextmanager
def use_ui_notifier(notifier: Notifier):
    token = set_ui_notifier(notifier)
    try:
        yield notifier
    finally:
        _current_notifier.reset(token)

class NotifierProxy:
    def __getattr__(self, name: str) -> Any:
        return getattr(get_ui_notifier(), name)


ui = NotifierProxy()


UIEventCollector = EventCollector
