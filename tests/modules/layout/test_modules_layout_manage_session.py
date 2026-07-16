import hashlib
import sys
import types

import polars as pl
import pytest

# Stub heavy LLM package to avoid circular imports during module import
if "modules.llm" not in sys.modules:
    llm_pkg = types.ModuleType("modules.llm")
    llm_pkg.__path__ = []  # mark as package
    sys.modules["modules.llm"] = llm_pkg

llm_api = types.ModuleType("modules.llm.llm_api")

def _identity_dict(d):  # minimal stand-in used by manage_session
    return d

setattr(llm_api, "remove_duplicate_charts_in_dictionary", _identity_dict)
sys.modules["modules.llm.llm_api"] = llm_api

from modules.layout.manage_session import (
    get_column_hash,
    get_session_state_query_content,
    hashFor,
)
from modules.utilities.session_context import SessionContext
from modules.utilities.config import get_naming_params
from modules.utilities.utils import get_schema_and_column_names


def test_get_session_state_query_content_returns_value_when_present():
    # Arrange
    naming = get_naming_params()
    prompt_user_key = naming["promptUser"]
    session_context = SessionContext.from_state({prompt_user_key: "hello world"})

    # Act
    result = get_session_state_query_content("ignored", session_context=session_context)

    # Assert
    assert result == "hello world"


def test_get_session_state_query_content_returns_default_when_missing():
    # Arrange
    naming = get_naming_params()
    not_met = naming["notMetConditionValue"]
    session_context = SessionContext.from_state({})

    # Act
    result = get_session_state_query_content("ignored", session_context=session_context)

    # Assert
    assert result is not None
    assert result == not_met


@pytest.mark.parametrize(
    "data",
    [
        [],
        [1, "two"],
        {"x": 1, "y": 2},
        "",
    ],
)
def test_hashFor_matches_md5_of_repr(data):
    # Arrange
    expected = hashlib.md5(repr(data).encode("utf-8")).hexdigest()

    # Act
    result = hashFor(data)

    # Assert
    assert isinstance(result, str)
    assert result == expected


def test_get_column_hash_sets_hash_for_valid_dataframe():
    # Arrange
    df = pl.DataFrame({"a": [1], "b": [2]})
    columns, _ = get_schema_and_column_names(df)
    expected_hash = hashlib.md5(repr(columns).encode("utf-8")).hexdigest()
    naming = get_naming_params()
    key = naming["columnHash"]

    # Act
    out = get_column_hash(df, {})

    # Assert
    assert key in out
    assert out[key] == expected_hash


def test_get_column_hash_sets_default_for_empty_dataframe():
    # Arrange: empty DataFrame (no rows/columns)
    df = pl.DataFrame()
    naming = get_naming_params()
    key = naming["columnHash"]
    not_met = naming["notMetConditionValue"]

    # Act
    out = get_column_hash(df, {})

    # Assert
    assert key in out
    assert out[key] == not_met
