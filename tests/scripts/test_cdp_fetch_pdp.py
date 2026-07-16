from __future__ import annotations

import datetime as dt
from pathlib import Path

import pytest

from modules.pdp.models import (
    FetchResult,
    ParentProduct,
    ParseResult,
    RawEvidence,
    Variant,
)
from scripts.cdp_fetch_pdp import (
    _adapter_for_retailer,
    _apply_category_context,
    _apply_retailer_defaults,
    _canonicalize_amazon_parent_from_existing_variants,
    _canonicalize_parent_from_existing_variants,
    _cdp_version_url,
    _extract_parent_id_from_url,
    _filter_tasks_against_existing,
    _find_retailer_seed_page,
    _goto,
    _goto_via_auto_paste,
    _image_records_for_result,
    _is_cloudflare_challenge_content,
    _is_known_invalid_text,
    _is_manual_intervention_content,
    _known_invalid_page_details,
    _known_invalid_page_details_from_content,
    _load_links,
    _navigate_to_pdp,
    _open_work_page,
    _parse_args,
    _parse_single,
    _probe_cdp_endpoint,
    _profile_for_category,
    _purge_known_invalid_existing,
    _should_abort_after_invalid_page,
    _should_abort_after_parse_failure,
    _should_overwrite_existing_rows,
    _should_take_batch_pause,
    _skippable_fatal_pdp_failure_detail,
    _wait_for_manual_intervention_clear,
)


def _make_parent(
    *,
    parent_product_id: str,
    pdp_url: str,
    retailer: str = "ulta",
    title_raw: str = "Product",
) -> ParentProduct:
    return ParentProduct(
        retailer=retailer,
        parent_product_id=parent_product_id,
        pdp_url=pdp_url,
        brand_raw="Brand",
        brand_normalized="brand",
        title_raw=title_raw,
        title_normalized="product",
        series_label_raw=None,
        category_path=("Makeup", "Lips"),
        has_color_selector=False,
        qa_flags=(),
        extras={},
    )


class _ExistingStore:
    def __init__(
        self,
        parent_ids: set[str],
        *,
        variant_parent_ids: dict[str, str] | None = None,
    ) -> None:
        self._parent_ids = set(parent_ids)
        self._variant_parent_ids = dict(variant_parent_ids or {})

    def existing_parent_ids(self, _retailer: str) -> set[str]:
        return set(self._parent_ids)

    def parent_ids_for_variant_ids(
        self, _retailer: str, variant_ids: list[str]
    ) -> dict[str, str]:
        return {
            variant_id: parent_id
            for variant_id, parent_id in self._variant_parent_ids.items()
            if variant_id in variant_ids
        }


class _RowsConnection:
    def __init__(self, rows: list[tuple[str, str, str]]) -> None:
        self._rows = list(rows)

    def __enter__(self) -> "_RowsConnection":
        return self

    def __exit__(self, *_args: object) -> None:
        return None

    def execute(self, _query: str, _params: tuple[str, ...]) -> "_RowsConnection":
        return self

    def fetchall(self) -> list[tuple[str, str, str]]:
        return list(self._rows)


class _PurgeStore:
    path = Path("unused")

    def __init__(self, rows: list[tuple[str, str, str]]) -> None:
        self.rows = list(rows)

    def delete_parent_with_variants(self, retailer: str, parent_product_id: str) -> int:
        _ = retailer
        before_count = len(self.rows)
        self.rows = [row for row in self.rows if row[0] != parent_product_id]
        return before_count - len(self.rows)

    def existing_parent_ids(self, _retailer: str) -> set[str]:
        return {parent_product_id for parent_product_id, _url, _title in self.rows}


def test_load_links_reads_chewy_wet_cat_food_category(
    tmp_path: Path,
) -> None:
    links_path = tmp_path / "links.json"
    pdp_url = "https://www.chewy.com/fancy-feast-gravy-lovers/dp/103856"
    links_path.write_text(
        f'{{"chewy": {{"wet_cat_food": ["{pdp_url}"]}}}}',
        encoding="utf-8",
    )

    links = _load_links(links_path, "chewy", {"wet_cat_food"})

    assert links == [("wet_cat_food", pdp_url)]


def test_profile_for_category_uses_chewy_wet_cat_food_profile() -> None:
    profile_name = _profile_for_category("chewy", "wet_cat_food")

    assert profile_name == "chewy_wet_cat_food"


def test_filter_tasks_against_existing_skips_existing_and_duplicate_ulta_parent_ids() -> (
    None
):
    store = _ExistingStore({"pimprod123"})

    tasks = [
        ("lipstick", "https://www.ulta.com/p/existing-product-pimprod123"),
        ("lipstick", "https://www.ulta.com/p/new-product-pimprod456"),
        ("lipstick", "https://www.ulta.com/p/new-product-duplicate-pimprod456"),
        ("lip_gloss", "https://www.ulta.com/p/new-gloss-mkt77006099"),
    ]

    filtered, skipped_existing, skipped_duplicate = _filter_tasks_against_existing(
        tasks,
        store,
        retailer="ulta",
    )

    assert skipped_existing == 1
    assert skipped_duplicate == 1
    assert filtered == [
        ("lipstick", "https://www.ulta.com/p/new-product-pimprod456"),
        ("lip_gloss", "https://www.ulta.com/p/new-gloss-mkt77006099"),
    ]


def test_extract_parent_id_from_url_prefers_first_capture_group() -> None:
    import re

    pattern = re.compile(r"/([^/?#]+)\.html")

    parent_id = _extract_parent_id_from_url(
        pattern,
        "https://www.saloncentric.com/loreal-professionnel-majirel-permanent-color.html",
    )

    assert parent_id == "loreal-professionnel-majirel-permanent-color"


def test_cdp_version_url_appends_json_version() -> None:
    assert (
        _cdp_version_url("http://127.0.0.1:9222")
        == "http://127.0.0.1:9222/json/version"
    )
    assert (
        _cdp_version_url("http://127.0.0.1:9222/devtools")
        == "http://127.0.0.1:9222/devtools/json/version"
    )


def test_probe_cdp_endpoint_reports_unavailable(monkeypatch: object) -> None:
    import urllib.error

    def _boom(*_args: object, **_kwargs: object) -> object:
        raise urllib.error.URLError("connection refused")

    monkeypatch.setattr("scripts.cdp_fetch_pdp.urlopen", _boom)

    ready, detail = _probe_cdp_endpoint("http://127.0.0.1:9222")

    assert ready is False
    assert "chrome/cdp is not reachable" in detail.lower()


def test_known_invalid_page_details_from_content_detects_cloudflare() -> None:
    details = _known_invalid_page_details_from_content(
        retailer="saloncentric",
        parent_title="Verifying you are human. This may take a few seconds.",
        html="<html><body>Verify you are human Enable JavaScript and cookies to continue</body></html>",
    )

    assert details == (403, "cloudflare_challenge")


def test_known_invalid_page_details_from_content_detects_chewy_kasada_shell() -> None:
    details = _known_invalid_page_details_from_content(
        retailer="chewy",
        parent_title="",
        html=(
            "<html><body><script>window.KPSDK={};</script>"
            "<script src='/challenge/ips.js?KP_UIDz=abc'></script></body></html>"
        ),
    )

    assert details == (429, "kasada_challenge")


def test_known_invalid_page_details_from_content_detects_chewy_blank_shell() -> None:
    details = _known_invalid_page_details_from_content(
        retailer="chewy",
        parent_title="",
        html="<html><head></head><body></body></html>",
    )

    assert details == (204, "blank_html_shell")


def test_is_cloudflare_challenge_content_returns_true_for_cloudflare_page() -> None:
    assert _is_cloudflare_challenge_content(
        retailer="saloncentric",
        title="Verifying you are human. This may take a few seconds.",
        html="<html><body>Verifying...</body></html>",
    )


def test_known_invalid_page_details_from_content_detects_access_denied_interstitial() -> (
    None
):
    details = _known_invalid_page_details_from_content(
        retailer="cosmoprofbeauty",
        parent_title="Access to this page has been denied.",
        html="<html><body>SECURITY CHECK Access to this page has been denied.</body></html>",
    )

    assert details == (403, "access_denied_interstitial")


def test_known_invalid_page_details_from_content_detects_page_not_found() -> None:
    details = _known_invalid_page_details_from_content(
        retailer="cosmoprofbeauty",
        parent_title="CosmoProf",
        html="<html><head><title>CosmoProf</title></head><body><h1>404 - Page Not Found</h1></body></html>",
    )

    assert details == (404, "error_interstitial_404")


def test_known_invalid_page_details_from_content_detects_saks_generic_shell() -> None:
    details = _known_invalid_page_details_from_content(
        retailer="saksfifthavenue",
        parent_title="Runner Sneaker",
        page_title="saksfifthavenue.com",
        html="<html><head><title>saksfifthavenue.com</title></head><body>shell</body></html>",
    )

    assert details == (503, "generic_shell_interstitial")


def test_is_known_invalid_text_detects_saks_generic_shell_title() -> None:
    assert _is_known_invalid_text("saksfifthavenue.com")


def test_is_manual_intervention_content_returns_true_for_access_denied_page() -> None:
    assert _is_manual_intervention_content(
        retailer="cosmoprofbeauty",
        title="Access to this page has been denied.",
        html="<html><body>SECURITY CHECK</body></html>",
    )


def test_should_abort_after_invalid_page_returns_true_for_chewy_blank_shell() -> None:
    assert _should_abort_after_invalid_page(
        retailer="chewy",
        reason="blank_html_shell",
    )


def test_should_abort_after_invalid_page_returns_false_for_nonfatal_reason() -> None:
    assert (
        _should_abort_after_invalid_page(
            retailer="ulta",
            reason="some_other_reason",
        )
        is False
    )


def test_should_abort_after_invalid_page_returns_true_for_chewy_kasada() -> None:
    assert _should_abort_after_invalid_page(
        retailer="chewy",
        reason="kasada_challenge",
    )


def test_should_abort_after_parse_failure_returns_true_for_chewy() -> None:
    assert _should_abort_after_parse_failure(retailer="chewy")


def test_should_abort_after_parse_failure_returns_false_for_ulta() -> None:
    assert _should_abort_after_parse_failure(retailer="ulta") is False


def test_skippable_fatal_pdp_failure_detail_returns_chewy_failure_detail() -> None:
    exc = RuntimeError(
        "Aborting fetch run after unusable Chewy page "
        "(blank_html_shell) at https://www.chewy.com/example/dp/123"
    )

    detail = _skippable_fatal_pdp_failure_detail(
        exc,
        retailer="chewy",
        fallback_url="https://www.chewy.com/fallback/dp/999",
    )

    assert (
        detail == "https://www.chewy.com/example/dp/123 "
        "(http_status=204; blank_html_shell)"
    )


def test_skippable_fatal_pdp_failure_detail_returns_none_for_non_chewy() -> None:
    exc = RuntimeError(
        "Aborting fetch run after unusable Chewy page "
        "(blank_html_shell) at https://www.chewy.com/example/dp/123"
    )

    detail = _skippable_fatal_pdp_failure_detail(
        exc,
        retailer="ulta",
        fallback_url="https://www.ulta.com/p/example",
    )

    assert detail is None


def test_adapter_for_retailer_supports_saloncentric() -> None:
    adapter = _adapter_for_retailer("saloncentric")
    assert getattr(adapter, "retailer", "") == "saloncentric"


def test_adapter_for_retailer_supports_cosmoprofbeauty() -> None:
    adapter = _adapter_for_retailer("cosmoprofbeauty")
    assert getattr(adapter, "retailer", "") == "cosmoprofbeauty"


def test_adapter_for_retailer_supports_chewy() -> None:
    adapter = _adapter_for_retailer("chewy")
    assert getattr(adapter, "retailer", "") == "chewy"


def test_adapter_for_retailer_supports_saksfifthavenue() -> None:
    adapter = _adapter_for_retailer("saksfifthavenue")
    assert getattr(adapter, "retailer", "") == "saksfifthavenue"


def test_adapter_for_retailer_supports_lorealparis() -> None:
    adapter = _adapter_for_retailer("lorealparis")
    assert getattr(adapter, "retailer", "") == "lorealparis"


def test_apply_retailer_defaults_sets_chewy_auto_paste_presets() -> None:
    args = _apply_retailer_defaults(_parse_args(["--retailer", "chewy"]))

    assert args.manual_navigation_auto_paste is True
    assert args.manual_navigation_auto_paste_wait_seconds == 20.0
    assert args.manual_navigation_auto_paste_attempts == 5
    assert args.timeout_ms == 20000
    assert args.request_pause_seconds == 15.0
    assert args.batch_pause_every == 30
    assert args.batch_pause_seconds == 180.0


def test_goto_uses_domcontentloaded_for_chewy() -> None:
    calls: list[tuple[str, str, int]] = []

    class _FakePage:
        def __init__(self) -> None:
            self.url = "about:blank"

        def goto(self, url: str, *, wait_until: str, timeout: int) -> None:
            calls.append((url, wait_until, timeout))
            self.url = url

    ok = _goto(
        _FakePage(),  # type: ignore[arg-type]
        "https://www.chewy.com/example/dp/123",
        45000,
        retailer="chewy",
    )

    assert ok is True
    assert calls == [
        ("https://www.chewy.com/example/dp/123", "domcontentloaded", 20000)
    ]


def test_should_take_batch_pause_returns_true_on_batch_boundary() -> None:
    assert _should_take_batch_pause(
        processed=10,
        batch_pause_every=10,
        task_index=10,
        task_total=100,
        max_per_run=None,
    )


def test_should_take_batch_pause_returns_false_at_run_end() -> None:
    assert (
        _should_take_batch_pause(
            processed=10,
            batch_pause_every=10,
            task_index=10,
            task_total=10,
            max_per_run=None,
        )
        is False
    )


def test_should_take_batch_pause_returns_false_when_max_per_run_reached() -> None:
    assert (
        _should_take_batch_pause(
            processed=10,
            batch_pause_every=10,
            task_index=10,
            task_total=100,
            max_per_run=10,
        )
        is False
    )


def test_should_overwrite_existing_rows_respects_rescrape_existing_flag() -> None:
    assert _should_overwrite_existing_rows(rescrape_existing=True) is True
    assert _should_overwrite_existing_rows(rescrape_existing=False) is False


def test_amazon_canonicalization_ignores_existing_variant_family_matches() -> None:
    parent = _make_parent(
        parent_product_id="B0CURRENT1",
        pdp_url="https://www.amazon.com/dp/B0CURRENT1",
        retailer="amazon",
        title_raw="Current product",
    )
    variant = Variant(
        retailer="amazon",
        parent_product_id="B0CURRENT1",
        variant_id="B0RELATED1",
        shade_name_raw=None,
        shade_name_normalized=None,
        size_text_raw=None,
        price_raw=None,
        price=None,
        currency="USD",
        barcode=None,
        swatch_image_url=None,
        hero_image_url=None,
        availability=None,
        source_index=None,
        qa_flags=(),
        extras={},
    )
    result = ParseResult(
        parent=parent,
        variants=(variant,),
        fetch_result=FetchResult(
            url=parent.pdp_url,
            status_code=200,
            headers={},
            html="",
            fetched_at=dt.datetime(2026, 5, 21, tzinfo=dt.timezone.utc),
        ),
        blobs=tuple(),
        raw_evidence=RawEvidence(),
    )
    store = _ExistingStore(
        {"B0EXISTING1"},
        variant_parent_ids={"B0RELATED1": "B0EXISTING1"},
    )

    canonical_parent = _canonicalize_amazon_parent_from_existing_variants(
        store,  # type: ignore[arg-type]
        result,
    )

    assert canonical_parent == "B0CURRENT1"
    assert result.parent.parent_product_id == "B0CURRENT1"
    assert result.variants[0].parent_product_id == "B0CURRENT1"


def test_parse_single_uses_final_browser_url_after_redirect(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    final_url = "https://www.amazon.com/dp/B0FINAL123"
    parsed_urls: list[str] = []

    class _FakeParser:
        def parse_url(self, url: str, *, html: str, timeout: float) -> ParseResult:
            parsed_urls.append(url)
            assert html == "<html><h1>Redirected PDP</h1></html>"
            assert timeout == 60.0
            parent = _make_parent(
                parent_product_id="B0FINAL123",
                pdp_url=url,
                retailer="amazon",
                title_raw="Redirected PDP",
            )
            return ParseResult(
                parent=parent,
                variants=tuple(),
                fetch_result=FetchResult(
                    url=url,
                    status_code=200,
                    headers={},
                    html=html,
                    fetched_at=dt.datetime(2026, 5, 21, tzinfo=dt.timezone.utc),
                ),
                blobs=tuple(),
                raw_evidence=RawEvidence(),
            )

    class _FakeElement:
        def inner_text(self) -> str:
            return "Redirected PDP"

    class _FakePage:
        url = final_url

        def wait_for_timeout(self, _timeout: int) -> None:
            return None

        def content(self) -> str:
            return "<html><h1>Redirected PDP</h1></html>"

        def title(self) -> str:
            return "Redirected PDP"

        def query_selector(self, selector: str) -> _FakeElement | None:
            assert selector == "h1"
            return _FakeElement()

    def _fake_navigate(page: object, **_kwargs: object) -> tuple[bool, object]:
        return True, page

    monkeypatch.setattr("scripts.cdp_fetch_pdp._navigate_to_pdp", _fake_navigate)

    result, returned_page = _parse_single(
        _FakeParser(),  # type: ignore[arg-type]
        _FakePage(),  # type: ignore[arg-type]
        "https://www.amazon.com/dp/B0REQUEST1",
        60000,
        0,
        "amazon",
        "wet_cat_food",
        "http://127.0.0.1:9223",
        False,
        20.0,
        3,
    )

    assert parsed_urls == [final_url]
    assert result is not None
    assert result.parent is not None
    assert result.parent.pdp_url == final_url
    assert returned_page.url == final_url


def test_navigate_to_pdp_uses_auto_paste_for_chewy(monkeypatch: object) -> None:
    calls: list[tuple[str, str]] = []

    class _FakePage:
        pass

    def _fake_goto_via_auto_paste(
        page,
        *,
        remote_url: str,
        url: str,
        timeout_ms: int,
        wait_seconds: float,
        attempts: int,
    ):
        calls.append(
            ("auto_paste", f"{remote_url}|{url}|{timeout_ms}|{wait_seconds}|{attempts}")
        )
        return True, page

    def _unexpected_goto(*_args: object, **_kwargs: object) -> bool:
        raise AssertionError("_goto should not be called for chewy auto-paste")

    monkeypatch.setattr(
        "scripts.cdp_fetch_pdp._goto_via_auto_paste", _fake_goto_via_auto_paste
    )
    monkeypatch.setattr("scripts.cdp_fetch_pdp._goto", _unexpected_goto)

    ok, page = _navigate_to_pdp(
        _FakePage(),  # type: ignore[arg-type]
        retailer="chewy",
        remote_url="http://localhost:9222",
        url="https://www.chewy.com/fancy-feast-gravy-lovers-poultry-beef/dp/103856",
        timeout_ms=45000,
        manual_navigation_auto_paste=True,
        auto_paste_wait_seconds=20.0,
        auto_paste_attempts=5,
    )

    assert ok is True
    assert isinstance(page, _FakePage)
    assert calls == [
        (
            "auto_paste",
            "http://localhost:9222|https://www.chewy.com/fancy-feast-gravy-lovers-poultry-beef/dp/103856|45000|20.0|5",
        )
    ]


def test_navigate_to_pdp_uses_plain_goto_when_chewy_auto_paste_disabled(
    monkeypatch: object,
) -> None:
    calls: list[str] = []

    class _FakePage:
        pass

    def _fake_goto(
        page, url: str, timeout_ms: int, *, retailer: str | None = None
    ) -> bool:
        calls.append(f"{url}|{timeout_ms}|{retailer}")
        return True

    def _unexpected_auto_paste(
        *_args: object, **_kwargs: object
    ) -> tuple[bool, object]:
        raise AssertionError("_goto_via_auto_paste should not be called")

    monkeypatch.setattr("scripts.cdp_fetch_pdp._goto", _fake_goto)
    monkeypatch.setattr(
        "scripts.cdp_fetch_pdp._goto_via_auto_paste",
        _unexpected_auto_paste,
    )

    ok, page = _navigate_to_pdp(
        _FakePage(),  # type: ignore[arg-type]
        retailer="chewy",
        remote_url="http://localhost:9222",
        url="https://www.chewy.com/fancy-feast-gravy-lovers-poultry-beef/dp/103856",
        timeout_ms=45000,
        manual_navigation_auto_paste=False,
        auto_paste_wait_seconds=20.0,
        auto_paste_attempts=5,
    )

    assert ok is True
    assert isinstance(page, _FakePage)
    assert calls == [
        "https://www.chewy.com/fancy-feast-gravy-lovers-poultry-beef/dp/103856|45000|chewy"
    ]


def test_find_retailer_seed_page_returns_existing_chewy_tab() -> None:
    class _FakePage:
        def __init__(self, url: str) -> None:
            self.url = url

        def is_closed(self) -> bool:
            return False

    class _FakeContext:
        def __init__(self, pages: list[object]) -> None:
            self.pages = pages

    chewy_page = _FakePage("https://www.chewy.com/")
    context = _FakeContext(
        [
            _FakePage("about:blank"),
            _FakePage("https://www.google.com/"),
            chewy_page,
        ]
    )

    matched = _find_retailer_seed_page(context, "chewy")  # type: ignore[arg-type]

    assert matched is chewy_page


def test_goto_via_auto_paste_returns_immediately_when_current_page_already_at_requested_pdp(
    monkeypatch: object,
) -> None:
    class _FakePage:
        def __init__(self, url: str) -> None:
            self.url = url
            self.context = None

        def is_closed(self) -> bool:
            return False

        def bring_to_front(self) -> None:
            return None

        def wait_for_load_state(self, _state: str, timeout: int) -> None:
            assert timeout == 45000

        def title(self) -> str:
            return "Chewy"

    class _FakeContext:
        def __init__(self, pages: list[object]) -> None:
            self.pages = pages

    target_url = "https://www.chewy.com/friskies-savory-shreds-turkey-cheese/dp/104231"
    page = _FakePage(target_url)
    context = _FakeContext([page])
    page.context = context

    monkeypatch.setattr("scripts.cdp_fetch_pdp.sys.platform", "win32")

    ok, matched_page = _goto_via_auto_paste(
        page,  # type: ignore[arg-type]
        remote_url="http://127.0.0.1:9222",
        url=target_url,
        timeout_ms=45000,
        wait_seconds=20.0,
        attempts=5,
    )

    assert ok is True
    assert matched_page is page
    assert page.url == target_url


def test_goto_via_auto_paste_requires_same_playwright_page_to_reach_requested_pdp(
    monkeypatch: object,
) -> None:
    class _FakePage:
        def __init__(self, url: str, *, title: str = "Chewy") -> None:
            self.url = url
            self.context = None
            self._title = title

        def bring_to_front(self) -> None:
            return None

        def wait_for_load_state(self, _state: str, timeout: int) -> None:
            assert timeout == 45000

        def wait_for_timeout(self, _timeout: int) -> None:
            return None

        def title(self) -> str:
            return self._title

    class _FakeContext:
        def __init__(self, pages: list[object]) -> None:
            self.pages = pages

    target_url = "https://www.chewy.com/reveal-natural-grain-free-chicken/dp/637782"
    page = _FakePage("about:blank", title="")
    context = _FakeContext([page])
    page.context = context
    pasted_urls: list[str] = []

    monkeypatch.setattr("scripts.cdp_fetch_pdp.sys.platform", "win32")

    def _fake_activate_current(
        *, remote_url: str, page: object
    ) -> tuple[str | None, str | None, str | None]:
        assert remote_url == "http://127.0.0.1:9222"
        assert page is not None
        return "tab-1", "Chewy", "about:blank"

    def _fake_paste(url: str, *, title_hint: str | None = None) -> None:
        assert title_hint == "Chewy"
        pasted_urls.append(url)

    def _fake_wait_for_tab_id(
        *,
        remote_url: str,
        tab_id: str,
        requested_url: str,
        timeout_seconds: float,
        stale_url: str | None = None,
        unchanged_timeout_seconds: float = 8.0,
    ) -> bool:
        assert remote_url == "http://127.0.0.1:9222"
        assert tab_id == "tab-1"
        assert requested_url == target_url
        assert timeout_seconds == 20.0
        assert stale_url == "about:blank"
        assert unchanged_timeout_seconds == 8.0
        return True

    def _fake_wait_for_page(
        page_obj: object, requested_url: str, *, timeout_ms: int
    ) -> bool:
        assert page_obj is page
        assert requested_url == target_url
        assert timeout_ms == 5000
        page.url = requested_url
        return True

    monkeypatch.setattr(
        "scripts.cdp_fetch_pdp._activate_current_cdp_tab_for_page",
        _fake_activate_current,
    )
    monkeypatch.setattr(
        "scripts.cdp_fetch_pdp._paste_url_into_windows_chrome",
        _fake_paste,
    )
    monkeypatch.setattr(
        "scripts.cdp_fetch_pdp._wait_for_cdp_tab_id_url",
        _fake_wait_for_tab_id,
    )
    monkeypatch.setattr(
        "scripts.cdp_fetch_pdp._wait_for_page_url",
        _fake_wait_for_page,
    )

    ok, matched_page = _goto_via_auto_paste(
        page,  # type: ignore[arg-type]
        remote_url="http://127.0.0.1:9222",
        url=target_url,
        timeout_ms=45000,
        wait_seconds=20.0,
        attempts=5,
    )

    assert ok is True
    assert matched_page is page
    assert pasted_urls == [target_url]
    assert page.url == target_url


def test_open_work_page_raises_when_chewy_seed_tab_required_but_missing() -> None:
    class _FakePage:
        def __init__(self, url: str) -> None:
            self.url = url

        def is_closed(self) -> bool:
            return False

    class _FakeContext:
        def __init__(self, pages: list[object]) -> None:
            self.pages = pages

        def new_page(self) -> object:
            raise AssertionError(
                "new_page should not be called when Chewy seed is required"
            )

    context = _FakeContext(
        [
            _FakePage("about:blank"),
            _FakePage("https://www.google.com/"),
        ]
    )

    with pytest.raises(RuntimeError, match="Open chewy.com"):
        _open_work_page(  # type: ignore[arg-type]
            context,
            retailer="chewy",
            require_seeded_retailer_page=True,
        )


def test_image_records_for_result_includes_parent_hero_image() -> None:
    parent = ParentProduct(
        retailer="saloncentric",
        parent_product_id="majirel",
        pdp_url="https://www.saloncentric.com/majirel.html",
        brand_raw="Brand",
        brand_normalized="brand",
        title_raw="Majirel",
        title_normalized="majirel",
        series_label_raw=None,
        category_path=("Hair", "Color"),
        has_color_selector=True,
        qa_flags=(),
        extras={"hero_image_url": "https://media.saloncentric.com/parent.jpg"},
    )
    variant = Variant(
        retailer="saloncentric",
        parent_product_id="majirel",
        variant_id="sku-1",
        shade_name_raw="1N",
        shade_name_normalized="1n",
        size_text_raw="2oz.",
        price_raw="11.34",
        price=None,
        currency="USD",
        barcode=None,
        swatch_image_url=None,
        hero_image_url="https://media.saloncentric.com/shade.jpg",
        availability="InStock",
        source_index=None,
        qa_flags=(),
        extras={},
    )
    result = ParseResult(
        parent=parent,
        variants=(variant,),
        fetch_result=FetchResult(
            url=parent.pdp_url,
            status_code=200,
            headers={},
            html="",
            fetched_at=dt.datetime(2026, 4, 14, tzinfo=dt.timezone.utc),
        ),
        blobs=tuple(),
        raw_evidence=RawEvidence(),
    )

    records = _image_records_for_result(result)

    assert len(records) == 2
    assert records[0]["variant_id"] == "sku-1"
    assert records[1]["variant_id"] is None
    assert records[1]["hero_image_url"] == "https://media.saloncentric.com/parent.jpg"
    assert records[1]["extras"] == {"image_role": "parent_hero"}


def test_apply_category_context_appends_specific_category_key() -> None:
    parent = ParentProduct(
        retailer="saloncentric",
        parent_product_id="majirel",
        pdp_url="https://www.saloncentric.com/majirel.html",
        brand_raw="Brand",
        brand_normalized="brand",
        title_raw="Majirel",
        title_normalized="majirel",
        series_label_raw=None,
        category_path=("Hair", "Hair Color"),
        has_color_selector=True,
        qa_flags=(),
        extras={},
    )
    result = ParseResult(
        parent=parent,
        variants=tuple(),
        fetch_result=FetchResult(
            url=parent.pdp_url,
            status_code=200,
            headers={},
            html="",
            fetched_at=dt.datetime(2026, 4, 14, tzinfo=dt.timezone.utc),
        ),
        blobs=tuple(),
        raw_evidence=RawEvidence(),
    )

    updated = _apply_category_context(result, "permanent")

    assert updated is not None
    assert updated.parent is not None
    assert updated.parent.category_path == ("Hair", "Hair Color", "permanent")
    assert updated.parent.extras["category_key"] == "permanent"


def test_known_invalid_page_details_detects_saloncentric_error_page() -> None:
    parent = _make_parent(
        parent_product_id="bad-page",
        pdp_url="https://www.saloncentric.com/bad-page.html",
        retailer="saloncentric",
        title_raw="Web server is down Error code 521",
    )
    result = ParseResult(
        parent=parent,
        variants=tuple(),
        fetch_result=FetchResult(
            url=parent.pdp_url,
            status_code=200,
            headers={},
            html="<html><title>www.saloncentric.com | 521: Web server is down</title></html>",
            fetched_at=dt.datetime(2026, 4, 14, tzinfo=dt.timezone.utc),
        ),
        blobs=tuple(),
        raw_evidence=RawEvidence(),
    )

    details = _known_invalid_page_details(result, retailer="saloncentric")

    assert details == (521, "error_interstitial_521")


def test_known_invalid_page_details_keeps_real_zero_variant_saloncentric_product() -> (
    None
):
    parent = _make_parent(
        parent_product_id="real-kit",
        pdp_url="https://www.saloncentric.com/real-kit.html",
        retailer="saloncentric",
        title_raw="Ionic Natural Series Try Me Kit",
    )
    result = ParseResult(
        parent=parent,
        variants=tuple(),
        fetch_result=FetchResult(
            url=parent.pdp_url,
            status_code=200,
            headers={},
            html="<html><title>Ionic Natural Series Try Me Kit</title><h1>Ionic Natural Series Try Me Kit</h1></html>",
            fetched_at=dt.datetime(2026, 4, 14, tzinfo=dt.timezone.utc),
        ),
        blobs=tuple(),
        raw_evidence=RawEvidence(),
    )

    details = _known_invalid_page_details(result, retailer="saloncentric")

    assert details is None


def test_wait_for_manual_intervention_clear_returns_after_page_changes(
    monkeypatch: object,
) -> None:
    class _FakePage:
        def __init__(self) -> None:
            self._reads = 0

        def title(self) -> str:
            if self._reads < 1:
                return "Verifying you are human. This may take a few seconds."
            return "Real PDP"

        def content(self) -> str:
            self._reads += 1
            if self._reads < 2:
                return "<html><body>Verify you are human</body></html>"
            return "<html><body>Actual PDP body</body></html>"

    monkeypatch.setattr("scripts.cdp_fetch_pdp.time.sleep", lambda _seconds: None)

    cleared = _wait_for_manual_intervention_clear(
        page=_FakePage(),
        retailer="saloncentric",
        url="https://www.saloncentric.com/test.html",
        poll_seconds=0.01,
        max_wait_seconds=1.0,
    )

    assert cleared is True


def test_purge_known_invalid_existing_removes_only_bad_rows(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    invalid_parent = _make_parent(
        parent_product_id="bad-page",
        pdp_url="https://www.saloncentric.com/bad-page.html",
        retailer="saloncentric",
        title_raw="Web server is down Error code 521",
    )
    valid_parent = _make_parent(
        parent_product_id="real-kit",
        pdp_url="https://www.saloncentric.com/real-kit.html",
        retailer="saloncentric",
        title_raw="Ionic Natural Series Try Me Kit",
    )
    rows = [
        (
            invalid_parent.parent_product_id,
            invalid_parent.pdp_url,
            invalid_parent.title_raw,
        ),
        (valid_parent.parent_product_id, valid_parent.pdp_url, valid_parent.title_raw),
    ]
    store = _PurgeStore(rows)
    monkeypatch.setattr(
        "scripts.cdp_fetch_pdp.connect_pdp_database",
        lambda _path: _RowsConnection(store.rows),
    )

    removed_count, removed_urls = _purge_known_invalid_existing(
        [
            ("permanent", invalid_parent.pdp_url),
            ("permanent", valid_parent.pdp_url),
        ],
        store,
        retailer="saloncentric",
    )

    assert removed_count == 1
    assert removed_urls == [invalid_parent.pdp_url]
    assert store.existing_parent_ids("saloncentric") == {"real-kit"}


def test_purge_known_invalid_existing_removes_blank_chewy_rows(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    blank_parent = _make_parent(
        parent_product_id="1017654",
        pdp_url="https://www.chewy.com/sheba-gravy-indulgence-white-fish/dp/1017654",
        retailer="chewy",
        title_raw="",
    )
    valid_parent = _make_parent(
        parent_product_id="103856",
        pdp_url="https://www.chewy.com/fancy-feast-gravy-lovers-poultry-beef/dp/103856",
        retailer="chewy",
        title_raw="Fancy Feast Gravy Lovers",
    )
    rows = [
        (blank_parent.parent_product_id, blank_parent.pdp_url, blank_parent.title_raw),
        (valid_parent.parent_product_id, valid_parent.pdp_url, valid_parent.title_raw),
    ]
    store = _PurgeStore(rows)
    monkeypatch.setattr(
        "scripts.cdp_fetch_pdp.connect_pdp_database",
        lambda _path: _RowsConnection(store.rows),
    )

    removed_count, removed_urls = _purge_known_invalid_existing(
        [
            ("wet_cat_food", blank_parent.pdp_url),
            ("wet_cat_food", valid_parent.pdp_url),
        ],
        store,
        retailer="chewy",
    )

    assert removed_count == 1
    assert removed_urls == [blank_parent.pdp_url]
    assert store.existing_parent_ids("chewy") == {"103856"}


def test_filter_tasks_against_existing_skips_existing_saloncentric_parent_ids() -> None:
    parent = _make_parent(
        parent_product_id="loreal-professionnel-majirel-permanent-color",
        pdp_url="https://www.saloncentric.com/loreal-professionnel-majirel-permanent-color.html",
        retailer="saloncentric",
        title_raw="Majirel",
    )
    store = _ExistingStore({parent.parent_product_id})

    filtered, skipped_existing, skipped_duplicate = _filter_tasks_against_existing(
        [
            ("permanent", parent.pdp_url),
            (
                "permanent",
                "https://www.saloncentric.com/redken-cover-fusion-permanent-color-cream.html",
            ),
        ],
        store,
        retailer="saloncentric",
    )

    assert skipped_existing == 1
    assert skipped_duplicate == 0
    assert filtered == [
        (
            "permanent",
            "https://www.saloncentric.com/redken-cover-fusion-permanent-color-cream.html",
        )
    ]
