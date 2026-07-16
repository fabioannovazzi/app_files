import pytest

from modules.layout import widgets as layout_widgets
from modules.layout.widgets import searchable_selectbox_with_state
from modules.utilities.session_context import get_session_state


class _StubNotifierBase:
    def __init__(self) -> None:
        self.markdown_calls: list[tuple[str, bool]] = []
        self.selectbox_received: dict | None = None

    def markdown(self, content: str, *, unsafe_allow_html: bool = False) -> None:
        self.markdown_calls.append((content, unsafe_allow_html))


class _StubNotifierOptional(_StubNotifierBase):
    def selectbox(
        self,
        label,
        options,
        index,
        key,
        placeholder=None,
        label_visibility="visible",
    ):
        self.selectbox_received = {
            "label": label,
            "options": options,
            "index": index,
            "key": key,
            "placeholder": placeholder,
            "label_visibility": label_visibility,
        }
        return options[index]


class _StubNotifierRequired(_StubNotifierBase):
    def selectbox(self, label, options, index, key):
        return options[index]


def test_searchable_selectbox_uses_session_state_and_injects_css_once():
    # Arrange: stub UI and reset module CSS flag
    notifier = _StubNotifierOptional()
    layout_widgets._DROPDOWN_CSS_INJECTED = False
    session_state = get_session_state()
    session_state.clear()
    session_state["mykey"] = "b"  # previous user choice

    # Act: first call should respect session_state and inject dropdown CSS
    result1 = searchable_selectbox_with_state(
        "Pick one",
        ["a", "b", "c"],
        key="mykey",
        notifier=notifier,
    )

    # Assert: returned option matches session_state and CSS injected once
    assert result1 == "b"
    assert notifier.selectbox_received["index"] == 1  # session_state moved selection
    assert len(notifier.markdown_calls) == 1
    assert "max-height:" in notifier.markdown_calls[0][0]

    # Act: second call should not re-inject dropdown CSS
    result2 = searchable_selectbox_with_state(
        "Pick one",
        ["a", "b", "c"],
        key="mykey",
        notifier=notifier,
    )

    # Assert: still selected, no extra CSS injection
    assert result2 == "b"
    assert len(notifier.markdown_calls) == 1


@pytest.mark.parametrize(
    "width, expected_style",
    [
        (300, "300px"),
        ("75%", "75%"),
    ],
)
def test_width_css_is_injected_and_formatted(width, expected_style):
    # Arrange
    notifier = _StubNotifierRequired()
    layout_widgets._DROPDOWN_CSS_INJECTED = False
    get_session_state().clear()

    # Act
    out = searchable_selectbox_with_state(
        "W",
        ["x", "y"],
        key="k",
        width=width,
        notifier=notifier,
    )

    # Assert: first markdown for height, second for width rule
    assert out == "x"
    assert len(notifier.markdown_calls) == 2
    css = notifier.markdown_calls[1][0]
    assert f"width:{expected_style};" in css
    assert "data-st-key='k'" in css


def test_no_placeholder_or_label_visibility_passed_when_not_supported():
    # Arrange: selectbox signature does NOT include optional params
    notifier = _StubNotifierRequired()
    layout_widgets._DROPDOWN_CSS_INJECTED = False
    get_session_state().clear()

    # Act: providing placeholder/label_visibility must not break the call
    result = searchable_selectbox_with_state(
        "Label",
        ["m", "n"],
        key="k2",
        placeholder="Choose...",
        label_visibility="hidden",
        notifier=notifier,
    )

    # Assert: call succeeds and returns the selected option
    assert result == "m"


def test_empty_options_use_blank_string():
    """Ensure empty option lists do not raise errors and return a blank string."""
    notifier = _StubNotifierOptional()
    layout_widgets._DROPDOWN_CSS_INJECTED = False
    get_session_state().clear()

    out = searchable_selectbox_with_state(
        "Empty",
        [],
        key="k3",
        index=3,
        notifier=notifier,
    )

    assert out == ""
    assert notifier.selectbox_received["options"] == [""]
    assert notifier.selectbox_received["index"] == 0
