from __future__ import annotations

from contextlib import contextmanager
from typing import Any, Iterable, Sequence

from modules.layout.core.widget_state import (
    DownloadPayload,
    record_download,
    resolve_checkbox_value,
    resolve_multi_value,
    resolve_option_value,
    resolve_radio_value,
    resolve_slider_value,
)
from modules.utilities.ui_notifier import Notifier, get_ui_notifier

__all__ = ["UIAdapter", "ui"]


class UIAdapter:
    """Framework-neutral adapter for UI-like interactions."""

    def __init__(self, notifier: Notifier | None = None) -> None:
        self._notifier = notifier or get_ui_notifier()

    def __enter__(self) -> "UIAdapter":
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: Any | None,
    ) -> None:
        return None

    def _notify(self, level: str, message: str) -> None:
        notify = getattr(self._notifier, level, None)
        if callable(notify):
            notify(message)

    def info(self, message: str) -> None:
        self._notify("info", message)

    def warning(self, message: str) -> None:
        self._notify("warning", message)

    def error(self, message: str) -> None:
        self._notify("error", message)

    def success(self, message: str) -> None:
        self._notify("success", message)

    def caption(self, message: str) -> None:
        self.info(message)

    def markdown(self, message: str, **_kwargs: Any) -> None:
        self.info(message)

    def exception(self, exc: Exception | str) -> None:
        self.error(str(exc))

    def selectbox(
        self,
        _label: str,
        options: Sequence[Any],
        *,
        key: str,
        index: int = 0,
        **_kwargs: Any,
    ) -> Any:
        return resolve_option_value(key, options, index=index)

    def multiselect(
        self,
        _label: str,
        options: Sequence[Any],
        *,
        key: str,
        default: Iterable[Any] | None = None,
        **_kwargs: Any,
    ) -> list[Any]:
        return resolve_multi_value(key, options, default=default)

    def radio(
        self,
        _label: str,
        options: Sequence[Any],
        *,
        key: str,
        index: int = 0,
        **_kwargs: Any,
    ) -> Any:
        return resolve_radio_value(key, options, index=index)

    def checkbox(
        self,
        _label: str,
        *,
        key: str,
        value: bool = False,
        **_kwargs: Any,
    ) -> bool:
        return resolve_checkbox_value(key, default=value)

    def slider(
        self,
        _label: str,
        *,
        min_value: int | float,
        max_value: int | float,
        value: tuple[int | float, int | float] | None = None,
        key: str,
        **_kwargs: Any,
    ) -> tuple[int | float, int | float]:
        return resolve_slider_value(key, min_value=min_value, max_value=max_value, value=value)

    def button(
        self,
        _label: str,
        *,
        key: str,
        **_kwargs: Any,
    ) -> bool:
        return resolve_checkbox_value(key, default=False)

    def download_button(
        self,
        *,
        label: str,
        data: Any,
        file_name: str,
        mime: str | None = None,
        key: str | None = None,
        **_kwargs: Any,
    ) -> None:
        record_download(
            DownloadPayload(label=label, data=data, file_name=file_name, mime=mime, key=key)
        )

    @contextmanager
    def container(self):
        yield self

    @contextmanager
    def expander(self, _label: str):
        yield self

    def columns(self, weights: Sequence[int | float]):
        return [self for _ in weights]

    def image(self, *_args: Any, **_kwargs: Any) -> None:
        return None


ui = UIAdapter()
