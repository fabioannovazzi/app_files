import pytest

from modules.layout.memoization import (
    ensure_session_state_initialized,
    get_hashed_key,
    get_run_params,
)
from modules.utilities.session_context import SessionContext
from modules.utilities.config import get_naming_params


def test_get_run_params_includes_checkCollect_and_default_false():
    # Act
    run_params = get_run_params()

    # Assert
    assert isinstance(run_params, dict)
    assert "checkCollect" in run_params
    assert isinstance(run_params["checkCollect"], bool)
    assert run_params["checkCollect"] is False


@pytest.mark.parametrize(
    "key,column_hash,expected",
    [
        ("base", "abc", "base_abc"),
        ("base", 123, "base_123"),
        ("base", None, "base"),
        ("base", "", "base"),
    ],
)
def test_get_hashed_key_behaviour(key, column_hash, expected):
    # Act
    result = get_hashed_key(key, column_hash)

    # Assert
    assert result == expected


def test_ensure_session_state_initialized_creates_empty_dict_when_missing():
    # Arrange
    naming = get_naming_params()
    collected_key = naming["collectedHashes"]
    session_context = SessionContext.from_state({})

    # Precondition: key not present
    assert collected_key not in session_context.state

    # Act
    ensure_session_state_initialized(session_context)

    # Assert
    assert collected_key in session_context.state
    assert session_context.state[collected_key] == {}


def test_ensure_session_state_initialized_does_not_overwrite_existing_state():
    # Arrange
    naming = get_naming_params()
    collected_key = naming["collectedHashes"]
    existing = {"sig": "step1"}
    session_context = SessionContext.from_state({collected_key: existing.copy()})

    # Act
    ensure_session_state_initialized(session_context)

    # Assert
    # Existing mapping remains unchanged (no reset to empty)
    assert session_context.state[collected_key] == existing
