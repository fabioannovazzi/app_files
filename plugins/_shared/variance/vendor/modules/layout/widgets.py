"""Reusable widget state helpers."""

from __future__ import annotations

from typing import Any, Literal, Sequence, TypeVar, cast

from modules.layout.core.widget_state import resolve_option_value

T = TypeVar("T")


def searchable_selectbox_with_state(
    label: str,
    options: Sequence[T],
    *,
    key: str,
    index: int = 0,
    max_height: int = 200,
    placeholder: str | None = None,
    label_visibility: Literal["visible", "hidden", "collapsed"] = "visible",
    width: int | str | None = None,
    **kwargs: Any,
) -> T:
    """Resolve a selectbox selection from session state."""
    if not options:
        options = [cast(T, "")]
        index = 0
    if not 0 <= index < len(options):
        index = 0
    default = options[index]
    return cast(
        T,
        resolve_option_value(
            key,
            options,
            index=index,
            default=default,
        ),
    )
