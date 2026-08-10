from __future__ import annotations

import contextlib
import contextvars
import logging
from dataclasses import dataclass
from typing import Any, Callable, Iterable, Mapping, Protocol

__all__ = [
    "CapturedChartOutput",
    "CapturedDataFrame",
    "CapturedPlotlyChart",
    "EventCollector",
    "FastAPINotifier",
    "HeadlessChartCapture",
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


@dataclass(frozen=True)
class CapturedPlotlyChart:
    """One Plotly chart captured from a legacy UI plotting call."""

    figure: Any
    kwargs: dict[str, Any]


@dataclass(frozen=True)
class CapturedDataFrame:
    """One dataframe captured from a legacy UI display/download path."""

    frame: Any
    kwargs: dict[str, Any]


@dataclass(frozen=True)
class CapturedChartOutput:
    """A complete chart output emitted by a legacy chart helper."""

    frame: Any
    figure: Any
    config: dict[str, Any]
    chart_dict: dict[str, Any]
    key: Any
    variance_analysis_chart: bool
    run: Any
    chosen_dimension: Any


class UIContainer(Protocol):
    def __enter__(self) -> "UIContainer": ...

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: Any | None,
    ) -> None: ...


class Notifier(Protocol):
    """Structured notification interface for logging UI-adjacent events."""

    def notify(
        self,
        level: str,
        message: str,
        context: Mapping[str, Any] | None = None,
    ) -> None: ...

    def info(self, message: str, **context: Any) -> None: ...

    def warning(self, message: str, **context: Any) -> None: ...

    def error(self, message: str, **context: Any) -> None: ...

    def success(self, message: str, **context: Any) -> None: ...


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
        self.events.append(
            {"level": level, "message": message, "context": dict(context or {})}
        )

    def info(self, message: str, **context: Any) -> None:
        self.notify("info", str(message), context)

    def warning(self, message: str, **context: Any) -> None:
        self.notify("warning", str(message), context)

    def error(self, message: str, **context: Any) -> None:
        self.notify("error", str(message), context)

    def success(self, message: str, **context: Any) -> None:
        self.notify("success", str(message), context)


class HeadlessChartCapture(EventCollector):
    """Capture Streamlit-style legacy chart side effects in headless runs."""

    def __init__(self) -> None:
        super().__init__()
        self.chart_outputs: list[CapturedChartOutput] = []
        self.plotly_charts: list[CapturedPlotlyChart] = []
        self.dataframes: list[CapturedDataFrame] = []
        self.captions: list[str] = []
        self.markdown_blocks: list[str] = []
        self.writes: list[tuple[tuple[Any, ...], dict[str, Any]]] = []

    def tabs(self, labels: Iterable[str]) -> list[NullContainer]:
        self.notify("tabs", ",".join(str(label) for label in labels), {})
        return [NullContainer() for _label in labels]

    def plotly_chart(self, figure: Any, **kwargs: Any) -> None:
        self.plotly_charts.append(CapturedPlotlyChart(figure=figure, kwargs=kwargs))

    def capture_chart_output(
        self,
        frame: Any,
        figure: Any,
        config: dict[str, Any],
        chart_dict: dict[str, Any],
        key: Any,
        variance_analysis_chart: bool,
        run: Any,
        chosen_dimension: Any,
    ) -> None:
        self.chart_outputs.append(
            CapturedChartOutput(
                frame=frame,
                figure=figure,
                config=config,
                chart_dict=dict(chart_dict),
                key=key,
                variance_analysis_chart=bool(variance_analysis_chart),
                run=run,
                chosen_dimension=chosen_dimension,
            )
        )

    def dataframe(self, frame: Any, **kwargs: Any) -> None:
        self.dataframes.append(CapturedDataFrame(frame=frame, kwargs=kwargs))

    def caption(self, message: Any, **_context: Any) -> None:
        self.captions.append(str(message))

    def markdown(self, message: Any, **_context: Any) -> None:
        self.markdown_blocks.append(str(message))

    def write(self, *args: Any, **kwargs: Any) -> None:
        self.writes.append((args, kwargs))

    def last_figure(self) -> Any:
        if not self.plotly_charts:
            raise ValueError("No Plotly chart was captured from the legacy run.")
        return self.plotly_charts[-1].figure

    def last_chart_output(self) -> CapturedChartOutput:
        if not self.chart_outputs:
            raise ValueError("No chart output was captured from the legacy run.")
        return self.chart_outputs[-1]

    def last_dataframe(self) -> Any:
        if not self.dataframes:
            raise ValueError("No dataframe was captured from the legacy run.")
        return self.dataframes[-1].frame


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
