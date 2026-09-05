from __future__ import annotations

import pytest

from modules.layout.widgets import searchable_selectbox_with_state
from modules.utilities.session_context import get_session_state


@pytest.mark.parametrize(
    ("options", "stored", "index", "expected"),
    [
        pytest.param(["a", "b"], "b", 0, "b", id="preserves-valid-selection"),
        pytest.param(["a", "b"], "removed", 1, "b", id="replaces-stale-selection"),
        pytest.param(["a", "b"], None, -1, "a", id="negative-index-falls-back"),
        pytest.param(["a", "b"], None, 9, "a", id="oversized-index-falls-back"),
        pytest.param([], "removed", 3, "", id="empty-options-clear-selection"),
    ],
)
def test_selectbox_resolves_and_persists_selection(
    monkeypatch: pytest.MonkeyPatch,
    options: list[str],
    stored: str | None,
    index: int,
    expected: str,
) -> None:
    state = get_session_state()
    key = "test_selection"
    monkeypatch.setitem(state, key, stored)

    result = searchable_selectbox_with_state("Pick one", options, key=key, index=index)

    assert result == expected
    assert state[key] == expected


def test_selectbox_without_saved_selection_uses_requested_default(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    state = get_session_state()
    key = "test_selection"
    monkeypatch.setitem(state, key, None)
    del state[key]

    result = searchable_selectbox_with_state("Pick one", ["a", "b"], key=key, index=1)

    assert result == "b"
    assert state[key] == "b"
