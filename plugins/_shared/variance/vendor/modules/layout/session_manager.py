from __future__ import annotations

from typing import Any, MutableMapping

from modules.utilities.session_context import (
    SessionContext,
    get_session_state,
    resolve_session_state,
)

__all__ = ["SessionManager"]


class SessionManager:
    """Session manager backed by a dict or ``SessionContext``."""

    def __init__(
        self, state: SessionContext | MutableMapping[str, Any] | None = None
    ) -> None:
        if state is None:
            self._state = get_session_state()
        else:
            self._state = resolve_session_state(state)

    def __getitem__(self, key: str) -> Any:
        return self._state[key]

    def get(self, key: str, default: Any = None) -> Any:
        return self._state.get(key, default)

    def set(self, key: str, value: Any) -> None:
        self._state[key] = value

    def contains(self, key: str) -> bool:
        return key in self._state

    def delete(self, key: str) -> None:
        self._state.pop(key, None)

    def increment(self, key: str, amount: int = 1) -> None:
        self._state[key] = self._state.get(key, 0) + amount
