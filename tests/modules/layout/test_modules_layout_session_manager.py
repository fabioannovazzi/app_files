import pytest

from modules.layout.session_manager import SessionManager
from modules.utilities.session_context import SessionContext


def test_set_and_get_roundtrip():
    # Arrange
    mgr = SessionManager(state={})

    # Act
    mgr.set("answer", 42)

    # Assert
    assert mgr.get("answer") == 42
    assert mgr.contains("answer") is True


def test_get_missing_returns_default_and_does_not_insert():
    # Arrange
    mgr = SessionManager(state={})

    # Act
    result = mgr.get("missing", default="fallback")

    # Assert
    assert result == "fallback"
    assert mgr.contains("missing") is False  # get should not mutate state


def test_contains_true_even_if_value_is_falsy():
    # Arrange
    mgr = SessionManager(state={})
    mgr.set("flag", False)

    # Act
    value = mgr.get("flag", default=True)

    # Assert
    assert value is False  # returns stored value, not default
    assert mgr.contains("flag") is True


def test_session_manager_updates_session_context_state():
    # Arrange
    state = {"existing": "value"}
    session_context = SessionContext.from_state(state)
    mgr = SessionManager(state=session_context)

    # Act
    mgr.set("answer", 42)
    mgr.increment("count", 2)

    # Assert
    assert session_context.state["answer"] == 42
    assert session_context.state["count"] == 2
    assert state["answer"] == 42
