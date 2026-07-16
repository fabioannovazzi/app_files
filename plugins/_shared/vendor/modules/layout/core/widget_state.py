from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable, Sequence

from modules.utilities.session_context import session_state

__all__ = [
    "DownloadPayload",
    "record_download",
    "resolve_checkbox_value",
    "resolve_multi_value",
    "resolve_option_value",
    "resolve_radio_value",
    "resolve_slider_value",
    "resolve_text_value",
]


@dataclass(frozen=True)
class DownloadPayload:
    """Payload metadata for a downloadable asset."""

    label: str
    data: Any
    file_name: str
    mime: str | None = None
    key: str | None = None


def resolve_option_value(
    key: str,
    options: Sequence[Any],
    *,
    index: int = 0,
    default: Any | None = None,
) -> Any:
    """Resolve a single-select widget value from session state."""
    if not options:
        return default
    if not 0 <= index < len(options):
        index = 0
    fallback = options[index] if default is None else default
    value = session_state.get(key, fallback)
    if value not in options:
        value = fallback
    session_state[key] = value
    return value


def resolve_radio_value(
    key: str,
    options: Sequence[Any],
    *,
    index: int = 0,
    default: Any | None = None,
) -> Any:
    """Resolve a radio selection from session state."""
    return resolve_option_value(key, options, index=index, default=default)


def resolve_multi_value(
    key: str,
    options: Sequence[Any],
    *,
    default: Iterable[Any] | None = None,
) -> list[Any]:
    """Resolve a multi-select widget value from session state."""
    default_list = list(default or [])
    value = session_state.get(key, default_list)
    if not isinstance(value, list):
        value = list(value) if isinstance(value, Iterable) else default_list
    filtered = [item for item in value if item in options]
    session_state[key] = filtered
    return filtered


def resolve_checkbox_value(key: str, *, default: bool = False) -> bool:
    """Resolve a checkbox value from session state."""
    value = session_state.get(key, default)
    resolved = bool(value)
    session_state[key] = resolved
    return resolved


def resolve_slider_value(
    key: str,
    *,
    min_value: int | float,
    max_value: int | float,
    value: tuple[int | float, int | float] | None = None,
) -> tuple[int | float, int | float]:
    """Resolve a slider range selection from session state."""
    fallback = value or (min_value, max_value)
    resolved = session_state.get(key, fallback)
    if not isinstance(resolved, (tuple, list)) or len(resolved) != 2:
        resolved = fallback
    low, high = resolved
    low = max(min_value, low)
    high = min(max_value, high)
    if low > high:
        low, high = high, low
    final_value = (low, high)
    session_state[key] = final_value
    return final_value


def resolve_text_value(key: str, *, default: str = "") -> str:
    """Resolve a text input value from session state."""
    value = session_state.get(key, default)
    resolved = str(value)
    session_state[key] = resolved
    return resolved


def record_download(payload: DownloadPayload) -> None:
    """Record a download payload in session state for downstream delivery."""
    downloads = session_state.get("download_payloads", [])
    if not isinstance(downloads, list):
        downloads = []
    downloads.append(payload)
    session_state["download_payloads"] = downloads
