from __future__ import annotations

import pytest

from modules.pdp.cdp_listing_engine import (
    ListingStatePreparationError,
    _chewy_listing_url_state_error,
    _click_load_more_if_available,
    _click_recovery_cta_if_available,
    _find_open_page_matching_url,
    _looks_like_terminal_error_page,
    _manual_navigation_url_matches,
    _navigate_to_listing_page,
    _navigate_via_address_bar,
    _prepare_retailer_listing_state,
    _same_document_url,
    _select_chewy_sort_option,
)


class _FakeCandidate:
    def __init__(
        self,
        *,
        visible: bool = True,
        enabled: bool = True,
        click_raises: bool = False,
    ) -> None:
        self._visible = visible
        self._enabled = enabled
        self._click_raises = click_raises
        self.evaluate_called = False

    def is_visible(self) -> bool:
        return self._visible

    def is_enabled(self) -> bool:
        return self._enabled

    def scroll_into_view_if_needed(self, timeout: int = 0) -> None:
        _ = timeout

    def click(self, timeout: int = 0) -> None:
        _ = timeout
        if self._click_raises:
            raise RuntimeError("outside viewport")

    def evaluate(self, _script: str) -> None:
        self.evaluate_called = True


class _FakeLocatorGroup:
    def __init__(self, *candidates: _FakeCandidate) -> None:
        self._candidates = candidates

    def count(self) -> int:
        return len(self._candidates)

    def nth(self, index: int) -> _FakeCandidate:
        return self._candidates[index]


class _FakePage:
    def __init__(self, locator_group: _FakeLocatorGroup) -> None:
        self._locator_group = locator_group

    def get_by_role(self, *_args, **_kwargs) -> _FakeLocatorGroup:
        return self._locator_group

    def locator(self, *_args, **_kwargs) -> _FakeLocatorGroup:
        return self._locator_group


class _FakeKeyboard:
    def __init__(self, page: "_FakeNavigationPage") -> None:
        self._page = page
        self.events: list[str] = []

    def press(self, key: str) -> None:
        self.events.append(f"press:{key}")
        if key == "Enter":
            self._page.url = self._page.typed_text

    def type(self, text: str) -> None:
        self.events.append(f"type:{text}")
        self._page.typed_text = text


class _FakeNavigationPage:
    def __init__(self, url: str) -> None:
        self.url = url
        self.typed_text = ""
        self.keyboard = _FakeKeyboard(self)
        self.brought_to_front = False
        self.waited_for_load_state = False
        self.waited_for_timeout = False
        self.goto_url = ""

    def bring_to_front(self) -> None:
        self.brought_to_front = True

    def wait_for_load_state(self, *_args, **_kwargs) -> None:
        self.waited_for_load_state = True

    def wait_for_timeout(self, *_args, **_kwargs) -> None:
        self.waited_for_timeout = True

    def goto(self, url: str, **_kwargs) -> None:
        self.goto_url = url
        self.url = url

    def is_closed(self) -> bool:
        return False


class _FakeContext:
    def __init__(self, pages: list[_FakeNavigationPage]) -> None:
        self.pages = pages


class _FakeSortKeyboard:
    def __init__(self, page: "_FakeChewySortPage") -> None:
        self._page = page
        self.events: list[str] = []

    def press(self, key: str) -> None:
        self.events.append(key)
        if not self._page.keyboard_changes:
            return
        if key == "Home":
            self._page.current_label = "Relevance"
        elif key == "ArrowDown":
            labels = ["Relevance", "Newest", "Bestselling"]
            current_index = labels.index(self._page.current_label)
            self._page.current_label = labels[min(current_index + 1, len(labels) - 1)]


class _FakeSortSelect:
    def __init__(self, page: "_FakeChewySortPage") -> None:
        self._page = page

    def scroll_into_view_if_needed(self, timeout: int = 0) -> None:
        self._page.scroll_timeouts.append(timeout)

    def select_option(self, *, value: str, timeout: int = 0) -> list[str]:
        self._page.select_values.append(value)
        self._page.select_timeouts.append(timeout)
        if self._page.native_select_changes:
            self._page.current_label = {
                "byNewest": "Newest",
                "byPopularity": "Bestselling",
            }[value]
        return [value]

    def focus(self, timeout: int = 0) -> None:
        self._page.focus_timeouts.append(timeout)


class _FakeSortLocatorGroup:
    def __init__(self, page: "_FakeChewySortPage") -> None:
        self._page = page

    def count(self) -> int:
        return 1

    def nth(self, index: int) -> _FakeSortSelect:
        assert index == 0
        return _FakeSortSelect(self._page)


class _FakeChewySortPage:
    def __init__(
        self,
        current_label: str,
        *,
        native_select_changes: bool = True,
        keyboard_changes: bool = True,
    ) -> None:
        self.current_label = current_label
        self.native_select_changes = native_select_changes
        self.keyboard_changes = keyboard_changes
        self.keyboard = _FakeSortKeyboard(self)
        self.select_values: list[str] = []
        self.select_timeouts: list[int] = []
        self.scroll_timeouts: list[int] = []
        self.focus_timeouts: list[int] = []
        self.wait_timeouts: list[int] = []
        self.waited_selectors: list[str] = []

    def evaluate(self, *_args, **_kwargs) -> str:
        return self.current_label

    def locator(self, *_args, **_kwargs) -> _FakeSortLocatorGroup:
        return _FakeSortLocatorGroup(self)

    def wait_for_selector(self, selector: str, **_kwargs) -> _FakeSortSelect:
        self.waited_selectors.append(selector)
        return _FakeSortSelect(self)

    def wait_for_timeout(self, timeout: int) -> None:
        self.wait_timeouts.append(timeout)


def test_click_load_more_falls_back_to_dom_click() -> None:
    candidate = _FakeCandidate(click_raises=True)
    page = _FakePage(_FakeLocatorGroup(candidate))

    clicked = _click_load_more_if_available(page, load_more_texts=("load more",))

    assert clicked is True
    assert candidate.evaluate_called is True


def test_click_recovery_cta_clicks_continue_shopping_link() -> None:
    candidate = _FakeCandidate()
    page = _FakePage(_FakeLocatorGroup(candidate))

    clicked = _click_recovery_cta_if_available(page)

    assert clicked is True


def test_looks_like_terminal_error_page_detects_makeover_page() -> None:
    assert _looks_like_terminal_error_page(
        "this page needs a MAKEOVER",
        "For technical reasons, your request could not be handled properly at this time. Continue Shopping",
    )


def test_looks_like_terminal_error_page_detects_back_on_track_page() -> None:
    assert _looks_like_terminal_error_page(
        "Permanent Hair Color",
        "Check your spelling and try it again. products may not be available in your area. "
        "Let's get you back on track. Trending now Featured brands",
    )


def test_looks_like_terminal_error_page_does_not_match_challenge_page() -> None:
    assert not _looks_like_terminal_error_page(
        "Access to this page has been denied.",
        "SECURITY CHECK Press and hold the box below to confirm you are human",
    )


def test_same_document_url_requires_query_match() -> None:
    assert _same_document_url(
        "https://www.chewy.com/b/wet-food-389?sort=newest",
        "https://www.chewy.com/b/wet-food-389?sort=newest",
    )
    assert not _same_document_url(
        "https://www.chewy.com/b/wet-food-389?sort=newest",
        "https://www.chewy.com/b/wet-food-389?sort=bestselling",
    )


def test_navigate_via_address_bar_types_url_and_waits() -> None:
    page = _FakeNavigationPage("https://www.chewy.com/")

    navigated = _navigate_via_address_bar(
        page,  # type: ignore[arg-type]
        "https://www.chewy.com/b/wet-food-389?sort=bestselling",
        timeout_ms=1_000,
    )

    assert navigated is True
    assert page.brought_to_front is True
    assert page.waited_for_load_state is True
    assert page.waited_for_timeout is True
    assert page.keyboard.events == [
        "press:Control+L",
        "type:https://www.chewy.com/b/wet-food-389?sort=bestselling",
        "press:Enter",
    ]


def test_chewy_navigation_falls_back_to_goto_when_address_bar_does_not_navigate() -> (
    None
):
    page = _FakeNavigationPage("about:blank")

    def enter_without_navigation(key: str) -> None:
        page.keyboard.events.append(f"press:{key}")

    page.keyboard.press = enter_without_navigation  # type: ignore[method-assign]

    navigated = _navigate_to_listing_page(
        page,  # type: ignore[arg-type]
        "https://www.chewy.com/b/wet-food-389?sort=newest",
        timeout_ms=1_000,
        retailer="chewy",
    )

    assert navigated is True
    assert page.goto_url == "https://www.chewy.com/b/wet-food-389?sort=newest"
    assert page.url == "https://www.chewy.com/b/wet-food-389?sort=newest"


def test_find_open_page_matching_url_prefers_requested_manual_tab() -> None:
    newest = _FakeNavigationPage("https://www.chewy.com/b/wet-food-389?sort=newest")
    bestselling = _FakeNavigationPage(
        "https://www.chewy.com/b/wet-food-389?sort=bestselling"
    )
    context = _FakeContext([newest, bestselling])

    page = _find_open_page_matching_url(  # type: ignore[arg-type]
        context,
        "https://www.chewy.com/b/wet-food-389?sort=bestselling",
    )

    assert page is bestselling


def test_manual_navigation_url_matches_requested_query_subset() -> None:
    assert _manual_navigation_url_matches(
        "https://www.chewy.com/b/wet-food-389?sort=bestselling&ref=abc",
        "https://www.chewy.com/b/wet-food-389?sort=bestselling",
    )
    assert not _manual_navigation_url_matches(
        "https://www.chewy.com/b/wet-food-389?sort=newest",
        "https://www.chewy.com/b/wet-food-389?sort=bestselling",
    )
    assert not _manual_navigation_url_matches(
        "https://www.chewy.com/b/wet-food-389?sort=bestselling",
        "https://www.chewy.com/b/wet-food-389",
    )
    assert not _manual_navigation_url_matches(
        "https://www.chewy.com/b/wet-food-389?page=4",
        "https://www.chewy.com/b/wet-food-389",
    )


def test_chewy_ranked_url_state_blocks_stale_sort_query() -> None:
    error = _chewy_listing_url_state_error(
        current_url="https://www.chewy.com/b/wet-food-389?sort=bestselling",
        requested_url="https://www.chewy.com/b/wet-food-389",
        retailer="chewy",
        sort_mode="newest",
    )

    assert error is not None
    assert "stale stateful URL" in error


def test_select_chewy_sort_option_uses_native_select_and_verifies() -> None:
    page = _FakeChewySortPage("Relevance")

    selected = _select_chewy_sort_option(page, "Newest")  # type: ignore[arg-type]

    assert selected is True
    assert page.current_label == "Newest"
    assert page.select_values == ["byNewest"]
    assert page.waited_selectors == []


def test_select_chewy_sort_option_uses_keyboard_fallback_when_select_reverts() -> None:
    page = _FakeChewySortPage("Relevance", native_select_changes=False)

    selected = _select_chewy_sort_option(page, "Bestselling")  # type: ignore[arg-type]

    assert selected is True
    assert page.current_label == "Bestselling"
    assert page.select_values == ["byPopularity"]
    assert page.keyboard.events == ["Home", "ArrowDown", "ArrowDown", "Enter"]


def test_prepare_retailer_listing_state_blocks_unverified_chewy_sort() -> None:
    page = _FakeChewySortPage(
        "Relevance",
        native_select_changes=False,
        keyboard_changes=False,
    )

    with pytest.raises(ListingStatePreparationError):
        _prepare_retailer_listing_state(  # type: ignore[arg-type]
            page,
            retailer="chewy",
            sort_mode="newest",
            wait_ms=1,
        )
