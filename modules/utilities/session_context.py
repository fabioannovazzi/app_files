from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass, field
import contextvars
import hashlib
import logging
from pathlib import Path
import pickle
import threading
from typing import Any, Mapping, MutableMapping

from fastapi import Request

from modules.auth.config import get_auth_config
from modules.auth.session import AuthenticatedUser

__all__ = [
    "SessionContext",
    "build_session_context",
    "get_session_context",
    "get_active_session_context",
    "get_session_state",
    "resolve_session_state",
    "session_state",
    "set_active_session_context",
    "use_session_context",
]

LOGGER = logging.getLogger(__name__)
_SESSION_STORAGE_DIR = Path("tmp") / "session_context_sessions"
_POP_DEFAULT = object()


@dataclass
class SessionContext:
    """Container for per-request state previously stored in session_state."""

    state: MutableMapping[str, Any] = field(default_factory=dict)
    user: AuthenticatedUser | None = None
    cookies: Mapping[str, str] = field(default_factory=dict)
    payload: Mapping[str, Any] = field(default_factory=dict)
    session_key: str | None = None

    @classmethod
    def from_state(cls, state: MutableMapping[str, Any]) -> "SessionContext":
        return cls(state=state)

_CURRENT_SESSION_CONTEXT: contextvars.ContextVar[SessionContext] = contextvars.ContextVar(
    "_CURRENT_SESSION_CONTEXT",
    default=SessionContext(),
)


def _session_storage_key(session_key: str) -> str:
    return hashlib.sha256(session_key.encode("utf-8")).hexdigest()


def _session_path(storage_key: str) -> Path:
    return _SESSION_STORAGE_DIR / f"{storage_key}.pkl"


def _load_state(storage_key: str) -> dict[str, Any]:
    path = _session_path(storage_key)
    if not path.exists():
        return {}
    try:
        with path.open("rb") as handle:
            data = pickle.load(handle)
    except (OSError, pickle.PickleError, EOFError, AttributeError, ValueError) as exc:
        LOGGER.warning("Failed to load session state from %s: %s", path, exc)
        return {}
    if isinstance(data, dict):
        return data
    LOGGER.warning("Unexpected session state payload in %s; resetting.", path)
    return {}


def _persist_state(storage_key: str, snapshot: dict[str, Any]) -> None:
    path = _session_path(storage_key)
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        temp_path = path.with_suffix(".tmp")
        with temp_path.open("wb") as handle:
            pickle.dump(snapshot, handle)
        temp_path.replace(path)
    except OSError as exc:
        LOGGER.warning("Failed to persist session state to %s: %s", path, exc)


def _safe_snapshot(data: dict[str, Any]) -> dict[str, Any]:
    try:
        pickle.dumps(data)
        return dict(data)
    except (pickle.PickleError, TypeError, AttributeError, ValueError):
        filtered: dict[str, Any] = {}
        skipped: list[str] = []
        for key, value in data.items():
            try:
                pickle.dumps(value)
            except (pickle.PickleError, TypeError, AttributeError, ValueError):
                skipped.append(str(key))
                continue
            filtered[key] = value
        if skipped:
            LOGGER.warning("Skipping non-serializable session keys: %s", skipped)
        return filtered


class SessionStateStore(MutableMapping[str, Any]):
    def __init__(self, *, session_key: str, initial: Mapping[str, Any] | None = None) -> None:
        self._session_key = session_key
        self._storage_key = _session_storage_key(session_key)
        self._data: dict[str, Any] = dict(initial or {})
        self._lock = threading.Lock()

    def _persist(self) -> None:
        snapshot = _safe_snapshot(self._data)
        _persist_state(self._storage_key, snapshot)

    def __getitem__(self, key: str) -> Any:
        return self._data[key]

    def __setitem__(self, key: str, value: Any) -> None:
        with self._lock:
            self._data[key] = value
            self._persist()

    def __delitem__(self, key: str) -> None:
        with self._lock:
            del self._data[key]
            self._persist()

    def __iter__(self):
        return iter(self._data)

    def __len__(self) -> int:
        return len(self._data)

    def clear(self) -> None:
        with self._lock:
            self._data.clear()
            self._persist()

    def update(self, *args: Any, **kwargs: Any) -> None:
        with self._lock:
            self._data.update(*args, **kwargs)
            self._persist()

    def setdefault(self, key: str, default: Any = None) -> Any:
        with self._lock:
            if key in self._data:
                return self._data[key]
            self._data[key] = default
            self._persist()
            return default

    def pop(self, key: str, default: Any = _POP_DEFAULT) -> Any:
        with self._lock:
            if key in self._data:
                value = self._data.pop(key)
                self._persist()
                return value
            if default is not _POP_DEFAULT:
                return default
            raise KeyError(key)


_SESSION_STORE: dict[str, SessionStateStore] = {}
_SESSION_STORE_LOCK = threading.Lock()


def _get_state_store(session_key: str) -> SessionStateStore:
    with _SESSION_STORE_LOCK:
        store = _SESSION_STORE.get(session_key)
        if store is not None:
            return store
        initial = _load_state(_session_storage_key(session_key))
        store = SessionStateStore(session_key=session_key, initial=initial)
        _SESSION_STORE[session_key] = store
        return store


def resolve_session_state(
    session: SessionContext | MutableMapping[str, Any],
) -> MutableMapping[str, Any]:
    """Return the mutable state map for the supplied session object."""

    if isinstance(session, SessionContext):
        return session.state
    return session


def get_active_session_context() -> SessionContext:
    """Return the current SessionContext."""

    return _CURRENT_SESSION_CONTEXT.get()


def set_active_session_context(session_context: SessionContext) -> contextvars.Token[SessionContext]:
    """Set the active SessionContext for the current context."""

    return _CURRENT_SESSION_CONTEXT.set(session_context)


@contextmanager
def use_session_context(session_context: SessionContext):
    """Temporarily set the active SessionContext for the current context."""

    token = set_active_session_context(session_context)
    try:
        yield session_context
    finally:
        _CURRENT_SESSION_CONTEXT.reset(token)


def get_session_state(
    session_context: SessionContext | MutableMapping[str, Any] | None = None,
) -> MutableMapping[str, Any]:
    """Return a mutable session state mapping."""

    if session_context is None:
        session_context = get_active_session_context()
    return resolve_session_state(session_context)


class SessionStateProxy(MutableMapping[str, Any]):
    """Proxy to access session state without direct UI usage."""

    def __getitem__(self, key: str) -> Any:
        return get_session_state()[key]

    def __setitem__(self, key: str, value: Any) -> None:
        get_session_state()[key] = value

    def __delitem__(self, key: str) -> None:
        del get_session_state()[key]

    def __iter__(self):
        return iter(get_session_state())

    def __len__(self) -> int:
        return len(get_session_state())


session_state = SessionStateProxy()


def build_session_context(
    request: Request,
    *,
    user: AuthenticatedUser | None = None,
    payload: Mapping[str, Any] | None = None,
    session_id: str | None = None,
) -> SessionContext:
    """Create a SessionContext backed by a per-user/per-session store."""

    cookies = dict(request.cookies)
    session_key: str | None = None
    if session_id:
        session_key = session_id
    if session_key is None and user is not None and user.email:
        session_key = user.email
    if session_key is None:
        auth_cookie_name = get_auth_config().session_cookie_name
        session_key = cookies.get(auth_cookie_name) or cookies.get("session_id")
    if session_key is None:
        session_key = "anonymous"
    state = _get_state_store(session_key)
    return SessionContext(
        state=state,
        user=user,
        cookies=cookies,
        payload=dict(payload or {}),
        session_key=session_key,
    )


def get_session_context(session_key: str) -> SessionContext:
    """Return a SessionContext for a stored session key without a request."""

    state = _get_state_store(session_key)
    return SessionContext(state=state, session_key=session_key)
