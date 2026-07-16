from __future__ import annotations

from collections.abc import Sequence
import json
import re
from pathlib import Path
from types import SimpleNamespace

import polars as pl
import pytest

import scripts.run_retailer_listing_discovery_cdp as discovery_cdp
from modules.pdp.cdp_listing_engine import CandidateLink, CapturedListingPage
from modules.pdp.chewy_cdp_strategy import ChewyCDPStrategy
from modules.pdp.models import FilterObservation, FilterSurface, ListingObservation
from modules.pdp.saksfifthavenue_cdp_strategy import SaksfifthavenueCDPStrategy
from modules.pdp.saloncentric_cdp_strategy import SaloncentricCDPStrategy
from scripts.run_retailer_listing_discovery_cdp import (
    CHEWY_DEFAULT_FILTER_FAMILIES,
    FatalRetailerDiscoveryError,
    _activate_cdp_tab_for_manual_navigation,
    _apply_retailer_defaults,
    _build_manual_navigation_loader,
    _category_links_from_observations,
    _crawl_surface,
    _load_kiko_variant_parent_lookup,
    _manual_navigation_urls_match,
    _merge_links_payload,
    _parse_args,
    _read_links_payload,
    main,
)


@pytest.fixture(autouse=True)
def _disable_local_secrets(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(discovery_cdp, "load_env_from_secrets_file", lambda: {})


class _FakePDPStore:
    instances: list[_FakePDPStore] = []

    def __init__(self, store_path: Path | str | None = None) -> None:
        self.store_path = None if store_path is None else Path(store_path)
        self.listing_observations: list[ListingObservation] = []
        self.filter_surfaces: list[FilterSurface] = []
        self.filter_observations: list[FilterObservation] = []
        _FakePDPStore.instances.append(self)

    def append_retailer_listing_observations(
        self,
        *,
        crawl_ts: str,
        observations: Sequence[ListingObservation],
    ) -> None:
        del crawl_ts
        self.listing_observations.extend(observations)

    def append_retailer_filter_surfaces(
        self,
        *,
        crawl_ts: str,
        surfaces: Sequence[FilterSurface],
    ) -> None:
        del crawl_ts
        self.filter_surfaces.extend(surfaces)

    def append_retailer_filter_observations(
        self,
        *,
        crawl_ts: str,
        observations: Sequence[FilterObservation],
    ) -> None:
        del crawl_ts
        self.filter_observations.extend(observations)

    def materialize_retailer_filter_attributes(
        self,
        *,
        retailer: str | None = None,
        category_key: str | None = None,
        crawl_ts: str | None = None,
    ) -> int:
        del retailer, category_key, crawl_ts
        return len(
            {
                (
                    observation.parent_product_id,
                    observation.category_key,
                    observation.filter_family,
                )
                for observation in self.filter_observations
                if observation.parent_product_id
            }
        )


@pytest.fixture(autouse=True)
def fake_pdp_stores(monkeypatch: pytest.MonkeyPatch) -> list[_FakePDPStore]:
    _FakePDPStore.instances.clear()
    monkeypatch.setattr(discovery_cdp, "PDPStore", _FakePDPStore)
    return _FakePDPStore.instances


def _kiko_category_html() -> str:
    params = {
        "facetFilters": json.dumps([["categories.lvl3:FOUNDATION"]]),
        "facets": json.dumps(["coverage", "finishEffect"]),
        "hitsPerPage": "16",
        "page": "0",
    }
    payload = {
        "props": {
            "pageProps": {
                "serverState": {
                    "initialResults": {
                        "647_en-US": {
                            "results": [
                                {
                                    "hits": [{"objectID": "variant-a"}],
                                    "index": "647_en-US",
                                    "params": "&".join(
                                        f"{key}={value}"
                                        for key, value in params.items()
                                    ),
                                    "facets": {
                                        "coverage": {"HIGH": 2},
                                        "finishEffect": {"MATTE": 1},
                                    },
                                }
                            ]
                        }
                    }
                }
            }
        }
    }
    return (
        '<html><body><script id="__NEXT_DATA__" type="application/json">'
        f"{json.dumps(payload)}"
        "</script></body></html>"
    )


def test_merge_links_payload_replaces_target_categories_and_keeps_others() -> None:
    existing = {
        "amazon": {"lipstick": ["https://www.amazon.com/dp/B012345678"]},
        "saloncentric": {
            "permanent": ["https://www.saloncentric.com/p/old"],
            "demi": ["https://www.saloncentric.com/p/demi"],
        },
    }

    merged = _merge_links_payload(
        existing,
        retailer="saloncentric",
        category_links={"permanent": ["https://www.saloncentric.com/p/new"]},
    )

    assert merged["amazon"]["lipstick"] == ["https://www.amazon.com/dp/B012345678"]
    assert merged["saloncentric"]["permanent"] == ["https://www.saloncentric.com/p/new"]
    assert merged["saloncentric"]["demi"] == ["https://www.saloncentric.com/p/demi"]


def test_category_links_from_observations_dedupes_within_category_and_filters() -> None:
    observations = [
        ListingObservation(
            retailer="saloncentric",
            category_key="permanent",
            source_surface="category",
            sort_mode="default",
            page=1,
            position=1,
            pdp_url="https://www.saloncentric.com/p/a",
            parent_product_id="a",
            product_name="A",
        ),
        ListingObservation(
            retailer="saloncentric",
            category_key="permanent",
            source_surface="category",
            sort_mode="newest",
            page=1,
            position=1,
            pdp_url="https://www.saloncentric.com/p/a",
            parent_product_id="a",
            product_name="A",
        ),
        FilterObservation(
            retailer="saloncentric",
            category_key="permanent",
            filter_family="haircolor tone",
            filter_value="cool",
            source_surface="filter",
            pdp_url="https://www.saloncentric.com/p/b",
            parent_product_id="b",
            page=1,
            position=1,
        ),
    ]

    links = _category_links_from_observations(
        observations,
        category_keys={"permanent", "demi"},
    )

    assert links == {
        "demi": [],
        "permanent": [
            "https://www.saloncentric.com/p/a",
            "https://www.saloncentric.com/p/b",
        ],
    }


def test_normalize_listing_surface_sort_modes_preserves_saks_sales_first() -> None:
    sort_modes = discovery_cdp._normalize_listing_surface_sort_modes(
        "saksfifthavenue",
        ["new_arrivals", "sales_first", "best_sellers", "sales_first"],
    )

    assert sort_modes == ("new_arrivals", "best_sellers", "sales_first")


def test_normalize_listing_surface_sort_modes_preserves_lorealparis_default() -> None:
    sort_modes = discovery_cdp._normalize_listing_surface_sort_modes(
        "lorealparis",
        ["default"],
    )

    assert sort_modes == ("default",)


def test_normalize_categories_keeps_chewy_wet_cat_food() -> None:
    categories = discovery_cdp._normalize_categories(["wet_cat_food"], retailer="chewy")

    assert categories == {"wet_cat_food"}


def test_apply_retailer_defaults_sets_amazon_filter_families() -> None:
    args = _parse_args(["--retailer", "amazon"])

    normalized = _apply_retailer_defaults(args)

    assert normalized.filter_families == list(
        discovery_cdp.AMAZON_DEFAULT_FILTER_FAMILIES
    )
    assert normalized.materialize_filter_attributes is True


def test_limit_filter_surfaces_caps_after_extraction_order() -> None:
    surfaces = [
        FilterSurface(
            retailer="amazon",
            category_key="wet_cat_food",
            filter_family="brand",
            filter_value=f"Brand {index}",
            filter_url=f"https://www.amazon.com/s?k=wet+cat+food&rh=p_89%3ABrand{index}",
        )
        for index in range(3)
    ]

    limited = discovery_cdp._limit_filter_surfaces(surfaces, limit=2)

    assert [surface.filter_value for surface in limited] == ["Brand 0", "Brand 1"]


def test_limit_filter_surfaces_balances_filter_families() -> None:
    surfaces = [
        FilterSurface(
            retailer="amazon",
            category_key="wet_cat_food",
            filter_family="flavor",
            filter_value="Chicken",
            filter_url="https://www.amazon.com/s?k=wet+cat+food&rh=flavor%3AChicken",
        ),
        FilterSurface(
            retailer="amazon",
            category_key="wet_cat_food",
            filter_family="flavor",
            filter_value="Beef",
            filter_url="https://www.amazon.com/s?k=wet+cat+food&rh=flavor%3ABeef",
        ),
        FilterSurface(
            retailer="amazon",
            category_key="wet_cat_food",
            filter_family="packaging type",
            filter_value="Can",
            filter_url="https://www.amazon.com/s?k=wet+cat+food&rh=container%3ACan",
        ),
        FilterSurface(
            retailer="amazon",
            category_key="wet_cat_food",
            filter_family="food texture",
            filter_value="Pate",
            filter_url="https://www.amazon.com/s?k=wet+cat+food&rh=form%3APate",
        ),
    ]

    limited = discovery_cdp._limit_filter_surfaces(surfaces, limit=3)

    assert [(surface.filter_family, surface.filter_value) for surface in limited] == [
        ("flavor", "Chicken"),
        ("packaging type", "Can"),
        ("food texture", "Pate"),
    ]


def test_discovery_checkpoint_round_trips_progress(tmp_path: Path) -> None:
    output_dir = tmp_path / "run"
    listing = ListingObservation(
        retailer="chewy",
        category_key="wet_cat_food",
        source_surface="category",
        sort_mode="newest",
        page=1,
        position=1,
        pdp_url="https://www.chewy.com/product/dp/123",
        parent_product_id="123",
        product_name="Product",
    )
    surface = FilterSurface(
        retailer="chewy",
        category_key="wet_cat_food",
        filter_family="flavor",
        filter_value="Chicken",
        filter_url="https://www.chewy.com/f/chicken-wet-cat-food_c389_f4v",
    )
    filter_observation = FilterObservation(
        retailer="chewy",
        category_key="wet_cat_food",
        filter_family="flavor",
        filter_value="Chicken",
        source_surface="filter:flavor=Chicken",
        pdp_url="https://www.chewy.com/product/dp/123",
        parent_product_id="123",
        page=1,
        position=1,
    )
    completed_key = discovery_cdp._filter_surface_checkpoint_key(surface)

    path = discovery_cdp._write_discovery_checkpoint(
        output_dir=output_dir,
        crawl_ts="2026-04-30T00:00:00+00:00",
        retailer="chewy",
        categories=["wet_cat_food"],
        sort_modes=["newest", "best_selling"],
        observations=[listing],
        filter_surfaces=[surface],
        filter_observations=[filter_observation],
        completed_surface_keys={completed_key},
    )

    (
        crawl_ts,
        listings,
        surfaces,
        filter_observations,
        completed_keys,
        metadata,
    ) = discovery_cdp._load_discovery_checkpoint(output_dir)

    assert path == output_dir / discovery_cdp.CHECKPOINT_FILENAME
    assert crawl_ts == "2026-04-30T00:00:00+00:00"
    assert listings == [listing]
    assert surfaces == [surface]
    assert filter_observations == [filter_observation]
    assert completed_keys == {completed_key}
    assert metadata["retailer"] == "chewy"
    assert (
        metadata["chewy_sort_guard_version"] == discovery_cdp.CHEWY_SORT_GUARD_VERSION
    )


def test_load_discovery_checkpoint_preserves_chewy_wet_cat_food(
    tmp_path: Path,
) -> None:
    output_dir = tmp_path / "run"
    output_dir.mkdir()
    completed_key = discovery_cdp._listing_surface_checkpoint_key(
        category_key="wet_cat_food",
        source_surface="category",
        sort_mode="newest",
        surface_url="https://www.chewy.com/b/wet-food-389",
    )
    (output_dir / discovery_cdp.CHECKPOINT_FILENAME).write_text(
        json.dumps(
            {
                "schema_version": 1,
                "crawl_ts": "2026-04-30T00:00:00+00:00",
                "retailer": "chewy",
                "categories": ["wet_cat_food"],
                "sort_modes": ["newest"],
                "listing_observations": [
                    {
                        "retailer": "chewy",
                        "category_key": "wet_cat_food",
                        "source_surface": "category",
                        "sort_mode": "newest",
                        "page": 1,
                        "position": 1,
                        "pdp_url": "https://www.chewy.com/product/dp/123",
                    }
                ],
                "filter_surfaces": [],
                "filter_observations": [],
                "completed_surface_keys": [completed_key],
            }
        ),
        encoding="utf-8",
    )

    _, listings, _, _, completed_keys, metadata = (
        discovery_cdp._load_discovery_checkpoint(output_dir)
    )

    assert listings[0].category_key == "wet_cat_food"
    assert completed_keys == {
        discovery_cdp._listing_surface_checkpoint_key(
            category_key="wet_cat_food",
            source_surface="category",
            sort_mode="newest",
            surface_url="https://www.chewy.com/b/wet-food-389",
        )
    }
    assert metadata["categories"] == ["wet_cat_food"]


def test_latest_checkpoint_run_dir_uses_newest_checkpoint(tmp_path: Path) -> None:
    output_root = tmp_path / "runs"
    older_run = output_root / "chewy" / "20260429T010000Z"
    newer_run = output_root / "chewy" / "20260430T010000Z"
    ignored_run = output_root / "chewy" / "20260431T010000Z"
    older_run.mkdir(parents=True)
    newer_run.mkdir(parents=True)
    ignored_run.mkdir(parents=True)
    (older_run / discovery_cdp.CHECKPOINT_FILENAME).write_text("{}", encoding="utf-8")
    (newer_run / discovery_cdp.CHECKPOINT_FILENAME).write_text("{}", encoding="utf-8")

    latest = discovery_cdp._latest_checkpoint_run_dir(
        output_root=output_root,
        retailer="chewy",
    )

    assert latest == newer_run


def test_main_resume_skips_completed_listing_surface(
    monkeypatch,
    tmp_path: Path,
) -> None:
    output_root = tmp_path / "runs"
    resume_dir = output_root / "chewy" / "20260430T010000Z"
    links_path = tmp_path / "links.json"
    pdp_store_path = tmp_path / "pdp_store"
    strategy = ChewyCDPStrategy()
    category_url = "https://www.chewy.com/b/wet-food-389"
    completed_url = strategy.apply_sort_mode(category_url, "newest")
    completed_key = discovery_cdp._listing_surface_checkpoint_key(
        category_key="wet_cat_food",
        source_surface="category",
        sort_mode="newest",
        surface_url=completed_url,
    )
    completed_observation = ListingObservation(
        retailer="chewy",
        category_key="wet_cat_food",
        source_surface="category",
        sort_mode="newest",
        page=1,
        position=1,
        pdp_url="https://www.chewy.com/old-product/dp/111",
        parent_product_id="111",
        product_name="Old Product",
    )
    discovery_cdp._write_discovery_checkpoint(
        output_dir=resume_dir,
        crawl_ts="2026-04-30T00:00:00+00:00",
        retailer="chewy",
        categories=["wet_cat_food"],
        sort_modes=["newest", "best_selling"],
        observations=[completed_observation],
        filter_surfaces=[],
        filter_observations=[],
        completed_surface_keys={completed_key},
    )
    profile = SimpleNamespace(
        profile_name="chewy_wet_cat_food",
        base_url="https://www.chewy.com",
        category_urls=(category_url,),
        id_extractors=SimpleNamespace(parent_from_url_regex=re.compile(r"/dp/(\d+)")),
    )
    capture_calls: list[str] = []

    class _FakeEngine:
        def __init__(self, **_kwargs) -> None:
            return None

        def __enter__(self):
            return self

        def __exit__(self, *_args) -> None:
            return None

        def capture_listing_page(self, *, url: str, **_kwargs):
            capture_calls.append(url)
            return CapturedListingPage(
                requested_url=url,
                final_url=url,
                html="<html><body>Chewy products</body></html>",
                candidates=(
                    CandidateLink(
                        url="https://www.chewy.com/new-product/dp/222",
                        title="New Product",
                    ),
                ),
            )

    monkeypatch.setattr(
        "scripts.run_retailer_listing_discovery_cdp._load_profiles",
        lambda retailer, categories: [profile],
    )
    monkeypatch.setattr(
        "scripts.run_retailer_listing_discovery_cdp.strategy_for_retailer",
        lambda retailer: strategy,
    )
    monkeypatch.setattr(
        "scripts.run_retailer_listing_discovery_cdp.CDPListingEngine",
        _FakeEngine,
    )

    exit_code = main(
        [
            "--retailer",
            "chewy",
            "--output-root",
            str(output_root),
            "--resume",
            "--links-path",
            str(links_path),
            "--pdp-store-path",
            str(pdp_store_path),
            "--categories",
            "wet_cat_food",
            "--max-pages",
            "1",
            "--delay-seconds",
            "0",
            "--no-capture-filters",
            "--no-manual-navigation-auto-paste",
        ]
    )

    assert exit_code == 0
    assert capture_calls == [strategy.apply_sort_mode(category_url, "best_selling")]
    links_payload = json.loads(links_path.read_text(encoding="utf-8"))
    assert links_payload["chewy"]["wet_cat_food"] == [
        "https://www.chewy.com/old-product/dp/111",
        "https://www.chewy.com/new-product/dp/222",
    ]


def test_main_rejects_old_chewy_checkpoint_without_sort_guard(
    monkeypatch,
    tmp_path: Path,
) -> None:
    resume_dir = tmp_path / "runs" / "chewy" / "20260430T010000Z"
    resume_dir.mkdir(parents=True)
    (resume_dir / discovery_cdp.CHECKPOINT_FILENAME).write_text(
        json.dumps(
            {
                "schema_version": 1,
                "crawl_ts": "2026-04-30T00:00:00+00:00",
                "retailer": "chewy",
                "categories": ["wet_cat_food"],
                "sort_modes": ["newest", "best_selling"],
                "listing_observations": [],
                "filter_surfaces": [],
                "filter_observations": [],
                "completed_surface_keys": [],
            }
        ),
        encoding="utf-8",
    )
    profile = SimpleNamespace(profile_name="chewy_wet_cat_food", category_urls=())

    class _FakeEngine:
        def __init__(self, **_kwargs) -> None:
            raise AssertionError("engine should not start for an old Chewy checkpoint")

    monkeypatch.setattr(
        "scripts.run_retailer_listing_discovery_cdp._load_profiles",
        lambda retailer, categories: [profile],
    )
    monkeypatch.setattr(
        "scripts.run_retailer_listing_discovery_cdp.CDPListingEngine",
        _FakeEngine,
    )

    exit_code = main(
        [
            "--retailer",
            "chewy",
            "--resume-run-dir",
            str(resume_dir),
            "--links-path",
            str(tmp_path / "links.json"),
            "--pdp-store-path",
            str(tmp_path / "pdp_store"),
            "--categories",
            "wet_cat_food",
            "--no-capture-filters",
            "--no-manual-navigation-auto-paste",
        ]
    )

    assert exit_code == 1


def test_read_links_payload_supports_legacy_shape(tmp_path: Path) -> None:
    path = tmp_path / "links.json"
    path.write_text(
        """
        {
          "retailer": "saloncentric",
          "categories": {
            "permanent": ["https://www.saloncentric.com/p/a"]
          }
        }
        """,
        encoding="utf-8",
    )

    payload = _read_links_payload(path)

    assert payload == {
        "saloncentric": {"permanent": ["https://www.saloncentric.com/p/a"]}
    }


def test_parse_args_enables_filter_capture_by_default(monkeypatch) -> None:
    monkeypatch.setattr(
        "sys.argv",
        ["run_retailer_listing_discovery_cdp.py", "--retailer", "saloncentric"],
    )

    args = _parse_args(["--retailer", "saloncentric"])

    assert args.capture_filters is True
    assert args.filter_families is None
    assert args.reuse_open_tab is True
    assert args.recent_share == 0.20
    assert args.locale == "en-us"


def test_parse_args_allows_disabling_tab_reuse() -> None:
    args = _parse_args(
        [
            "--retailer",
            "saloncentric",
            "--no-reuse-open-tab",
        ]
    )

    assert args.reuse_open_tab is False


def test_parse_args_supports_manual_navigation_flags() -> None:
    args = _parse_args(
        [
            "--retailer",
            "chewy",
            "--manual-navigation",
            "--manual-navigation-notify",
            "--manual-navigation-crawl-filter-memberships",
            "--manual-navigation-auto-paste",
        ]
    )

    assert args.manual_navigation is True
    assert args.manual_navigation_notify is True
    assert args.manual_navigation_crawl_filter_memberships is True
    assert args.manual_navigation_auto_paste is True


def test_parse_args_supports_resume_flag() -> None:
    args = _parse_args(["--retailer", "chewy", "--resume"])

    assert args.resume is True
    assert args.resume_run_dir is None


def test_apply_retailer_defaults_sets_chewy_discovery_presets() -> None:
    args = _apply_retailer_defaults(_parse_args(["--retailer", "chewy"]))

    assert args.max_pages == 100
    assert args.filter_max_pages == 100
    assert args.delay_seconds == 1.0
    assert args.wait_ms == 3_000
    assert args.max_idle_scrolls == 2
    assert args.sort_modes is None
    assert args.filter_families == list(CHEWY_DEFAULT_FILTER_FAMILIES)
    assert args.manual_navigation is False
    assert args.manual_navigation_auto_paste is False
    assert args.manual_navigation_crawl_filter_memberships is True
    assert args.manual_navigation_auto_paste_wait_seconds == 20.0
    assert args.manual_navigation_auto_paste_attempts == 5
    assert args.chewy_manual_sort_widget is False


def test_apply_retailer_defaults_preserves_explicit_chewy_overrides() -> None:
    args = _apply_retailer_defaults(
        _parse_args(
            [
                "--retailer",
                "chewy",
                "--max-pages",
                "4",
                "--filter-max-pages",
                "7",
                "--delay-seconds",
                "0",
                "--wait-ms",
                "3000",
                "--max-idle-scrolls",
                "4",
                "--filter-families",
                "lifestage",
                "--no-manual-navigation-auto-paste",
                "--no-manual-navigation-crawl-filter-memberships",
                "--manual-navigation-auto-paste-wait-seconds",
                "30",
                "--manual-navigation-auto-paste-attempts",
                "2",
                "--no-chewy-manual-sort-widget",
            ]
        )
    )

    assert args.max_pages == 4
    assert args.filter_max_pages == 7
    assert args.delay_seconds == 0
    assert args.wait_ms == 3_000
    assert args.max_idle_scrolls == 4
    assert args.filter_families == ["lifestage"]
    assert args.manual_navigation_auto_paste is False
    assert args.manual_navigation_crawl_filter_memberships is False
    assert args.manual_navigation_auto_paste_wait_seconds == 30
    assert args.manual_navigation_auto_paste_attempts == 2
    assert args.chewy_manual_sort_widget is False


def test_load_kiko_variant_parent_lookup_reads_cache(tmp_path: Path) -> None:
    cache_dir = tmp_path / "cache" / "kiko"
    cache_dir.mkdir(parents=True)
    pl.DataFrame(
        [
            {
                "parent_product_id": "parent-a",
                "variant_id": "variant-a",
                "backend_id": "backend-a",
                "backend_parent_id": "",
            },
            {
                "parent_product_id": "parent-b",
                "variant_id": "variant-b",
                "backend_id": "backend-a",
                "backend_parent_id": "backend-parent",
            },
        ]
    ).write_parquet(cache_dir / "variants.parquet")

    lookup = _load_kiko_variant_parent_lookup(tmp_path / "cache")

    assert lookup["variant-a"] == ("parent-a",)
    assert lookup["backend-a"] == ("parent-a", "parent-b")
    assert lookup["backend-parent"] == ("parent-b",)


def test_manual_navigation_url_match_allows_extra_query_params() -> None:
    assert _manual_navigation_urls_match(
        "https://www.chewy.com/b/wet-food-389?sort=bestselling&ref=abc",
        "https://www.chewy.com/b/wet-food-389?sort=bestselling",
    )
    assert not _manual_navigation_urls_match(
        "https://www.chewy.com/b/wet-food-389?sort=newest",
        "https://www.chewy.com/b/wet-food-389?sort=bestselling",
    )
    assert not _manual_navigation_urls_match(
        "https://www.chewy.com/b/wet-food-389?sort=bestselling",
        "https://www.chewy.com/b/wet-food-389",
    )
    assert not _manual_navigation_urls_match(
        "https://www.chewy.com/b/wet-food-389?page=4",
        "https://www.chewy.com/b/wet-food-389",
    )


def test_manual_navigation_url_match_allows_chewy_slug_rewrite_same_dp_id() -> None:
    assert _manual_navigation_urls_match(
        "https://www.chewy.com/chewy-pate-beef-poultry-cat-food/dp/1753870",
        "https://www.chewy.com/chewy-pate-beef-poultry-variety/dp/1753870",
    )
    assert not _manual_navigation_urls_match(
        "https://www.chewy.com/chewy-pate-beef-poultry-cat-food/dp/1753870",
        "https://www.chewy.com/chewy-pate-beef-poultry-variety/dp/9999999",
    )


def test_manual_navigation_auto_paste_loader_does_not_prompt(monkeypatch) -> None:
    calls: list[tuple[str, str]] = []

    monkeypatch.setattr(
        discovery_cdp,
        "_activate_cdp_tab_for_manual_navigation",
        lambda **kwargs: calls.append(("activate", kwargs["requested_url"]))
        or ("Wet Cat Food", "https://www.chewy.com/b/wet-food-389?sort=newest"),
    )
    monkeypatch.setattr(
        discovery_cdp,
        "_paste_url_into_windows_chrome",
        lambda url, *, title_hint=None: calls.append(("paste", f"{url}|{title_hint}")),
    )
    monkeypatch.setattr(
        discovery_cdp,
        "_wait_for_cdp_tab_url",
        lambda **kwargs: calls.append(("wait", kwargs["stale_url"])) or True,
    )
    monkeypatch.setattr(
        discovery_cdp,
        "_send_manual_navigation_prompt_alert",
        lambda **kwargs: calls.append(("alert", kwargs["requested_url"])),
    )
    monkeypatch.setattr(
        "builtins.input",
        lambda _prompt: (_ for _ in ()).throw(AssertionError("input called")),
    )

    loader = _build_manual_navigation_loader(
        retailer="chewy",
        remote_url="http://localhost:9222",
        send_notifications=True,
        auto_paste=True,
        auto_paste_wait_seconds=1,
        auto_paste_attempts=1,
    )

    loader(
        "https://www.chewy.com/b/wet-food-389?sort=bestselling",
        "wet_cat_food",
        "category",
        1,
    )

    assert calls == [
        ("alert", "https://www.chewy.com/b/wet-food-389?sort=bestselling"),
        ("activate", "https://www.chewy.com/b/wet-food-389?sort=bestselling"),
        ("paste", "https://www.chewy.com/b/wet-food-389?sort=bestselling|Wet Cat Food"),
        ("wait", "https://www.chewy.com/b/wet-food-389?sort=newest"),
    ]


def test_activate_cdp_tab_for_manual_navigation_prefers_listing_over_pdp(
    monkeypatch,
) -> None:
    activated: list[str] = []

    monkeypatch.setattr(
        discovery_cdp,
        "_read_cdp_tabs",
        lambda remote_url: (
            {
                "id": "pdp",
                "title": "Chewy Pate",
                "type": "page",
                "url": "https://www.chewy.com/chewy-pate-beef-poultry-cat-food/dp/1753870",
            },
            {
                "id": "listing",
                "title": "Beef Wet Cat Food",
                "type": "page",
                "url": "https://www.chewy.com/f/beef-flavored-wet-cat-food_c389_f4v59627",
            },
        ),
    )
    monkeypatch.setattr(
        discovery_cdp,
        "_activate_cdp_tab",
        lambda tab_id, *, remote_url: activated.append(tab_id),
    )

    title_hint, stale_url = _activate_cdp_tab_for_manual_navigation(
        remote_url="http://localhost:9222",
        requested_url="https://www.chewy.com/f/cheese-flavored-wet-cat-food_c389_f4v20053",
    )

    assert title_hint == "Beef Wet Cat Food"
    assert (
        stale_url == "https://www.chewy.com/f/beef-flavored-wet-cat-food_c389_f4v59627"
    )
    assert activated == ["listing"]


def test_crawl_surface_manual_navigation_prompts_and_skips_cdp_navigation(
    tmp_path: Path,
) -> None:
    profile = SimpleNamespace(
        base_url="https://www.chewy.com",
        id_extractors=SimpleNamespace(parent_from_url_regex=re.compile(r"/dp/(\d+)")),
    )
    capture_calls: list[tuple[str, bool, str | None]] = []
    manual_calls: list[tuple[str, str, str, int]] = []

    class _FakeEngine:
        def capture_listing_page(
            self,
            *,
            url: str,
            navigate: bool = True,
            sort_mode: str | None = None,
            **_kwargs,
        ):
            capture_calls.append((url, navigate, sort_mode))
            return CapturedListingPage(
                requested_url=url,
                final_url=url,
                html="<html><body>Chewy products</body></html>",
                candidates=(
                    CandidateLink(
                        url="https://www.chewy.com/example-product/dp/123",
                        title="Example Product",
                    ),
                ),
            )

    def _manual_loader(
        requested_url: str,
        category_key: str,
        source_surface: str,
        page_number: int,
    ) -> None:
        manual_calls.append((requested_url, category_key, source_surface, page_number))

    observations, first_capture, completed = _crawl_surface(
        engine=_FakeEngine(),  # type: ignore[arg-type]
        strategy=ChewyCDPStrategy(),
        profile=profile,  # type: ignore[arg-type]
        category_key="wet_cat_food",
        surface_url="https://www.chewy.com/b/wet-food-389",
        source_surface="category",
        sort_mode="newest",
        max_pages=1,
        delay_seconds=0,
        failure_artifact_root=tmp_path,
        manual_navigation_loader=_manual_loader,
    )

    assert manual_calls == [
        (
            "https://www.chewy.com/b/wet-food-389",
            "wet_cat_food",
            "category",
            1,
        )
    ]
    assert capture_calls == [("https://www.chewy.com/b/wet-food-389", False, "newest")]
    assert first_capture is not None
    assert completed is True
    assert [row.parent_product_id for row in observations] == ["123"]


def test_crawl_surface_clicks_chewy_next_page_after_widget_sort(
    tmp_path: Path,
) -> None:
    profile = SimpleNamespace(
        base_url="https://www.chewy.com",
        id_extractors=SimpleNamespace(parent_from_url_regex=re.compile(r"/dp/(\d+)")),
    )
    base_url = "https://www.chewy.com/b/wet-food-389"
    page_two_url = "https://www.chewy.com/b/wet-food-389?page=2"
    capture_calls: list[tuple[str, bool, str | None]] = []
    clicked_next: list[str] = []

    class _FakeEngine:
        current_url = base_url

        def capture_listing_page(
            self,
            *,
            url: str,
            navigate: bool = True,
            sort_mode: str | None = None,
            **_kwargs,
        ):
            capture_calls.append((url, navigate, sort_mode))
            if self.current_url == base_url:
                return CapturedListingPage(
                    requested_url=url,
                    final_url=base_url,
                    html=(
                        '<html><body><a aria-label="Next Page" '
                        f'href="{page_two_url}">Next</a></body></html>'
                    ),
                    candidates=(
                        CandidateLink(
                            url="https://www.chewy.com/page-one-product/dp/111",
                            title="Page One Product",
                        ),
                    ),
                )
            return CapturedListingPage(
                requested_url=url,
                final_url=page_two_url,
                html="<html><body></body></html>",
                candidates=(
                    CandidateLink(
                        url="https://www.chewy.com/page-two-product/dp/222",
                        title="Page Two Product",
                    ),
                ),
            )

        def click_next_listing_page(self, *, retailer: str) -> str | None:
            clicked_next.append(retailer)
            self.current_url = page_two_url
            return page_two_url

    observations, _first_capture, completed = _crawl_surface(
        engine=_FakeEngine(),  # type: ignore[arg-type]
        strategy=ChewyCDPStrategy(),
        profile=profile,  # type: ignore[arg-type]
        category_key="wet_cat_food",
        surface_url=base_url,
        source_surface="category",
        sort_mode="newest",
        max_pages=2,
        delay_seconds=0,
        failure_artifact_root=tmp_path,
    )

    assert completed is True
    assert clicked_next == ["chewy"]
    assert capture_calls == [
        (base_url, True, "newest"),
        (page_two_url, False, "newest"),
    ]
    assert [row.parent_product_id for row in observations] == ["111", "222"]


def test_crawl_surface_clicks_chewy_next_page_for_filter_surface(
    tmp_path: Path,
) -> None:
    profile = SimpleNamespace(
        base_url="https://www.chewy.com",
        id_extractors=SimpleNamespace(parent_from_url_regex=re.compile(r"/dp/(\d+)")),
    )
    base_url = "https://www.chewy.com/f/chicken-wet-cat-food_c389_f4v59627"
    page_two_url = f"{base_url}?page=2"
    capture_calls: list[tuple[str, bool, str | None]] = []
    clicked_next: list[str] = []

    class _FakeEngine:
        current_url = base_url

        def capture_listing_page(
            self,
            *,
            url: str,
            navigate: bool = True,
            sort_mode: str | None = None,
            **_kwargs,
        ):
            capture_calls.append((url, navigate, sort_mode))
            if self.current_url == base_url:
                return CapturedListingPage(
                    requested_url=url,
                    final_url=base_url,
                    html="<html><body>filter page without next anchor</body></html>",
                    candidates=(
                        CandidateLink(
                            url="https://www.chewy.com/filter-page-one/dp/111",
                            title="Filter Page One",
                        ),
                    ),
                )
            return CapturedListingPage(
                requested_url=url,
                final_url=page_two_url,
                html="<html><body></body></html>",
                candidates=(
                    CandidateLink(
                        url="https://www.chewy.com/filter-page-two/dp/222",
                        title="Filter Page Two",
                    ),
                ),
            )

        def click_next_listing_page(self, *, retailer: str) -> str | None:
            clicked_next.append(retailer)
            self.current_url = page_two_url
            return page_two_url

    observations, _first_capture, completed = _crawl_surface(
        engine=_FakeEngine(),  # type: ignore[arg-type]
        strategy=ChewyCDPStrategy(),
        profile=profile,  # type: ignore[arg-type]
        category_key="wet_cat_food",
        surface_url=base_url,
        source_surface="filter:flavor=Chicken",
        sort_mode="default",
        max_pages=2,
        delay_seconds=0,
        failure_artifact_root=tmp_path,
    )

    assert completed is True
    assert clicked_next == ["chewy"]
    assert capture_calls == [
        (base_url, True, "default"),
        (page_two_url, False, "default"),
    ]
    assert [row.parent_product_id for row in observations] == ["111", "222"]


def test_crawl_surface_skips_chewy_filter_redirected_to_base_category(
    tmp_path: Path,
) -> None:
    profile = SimpleNamespace(
        base_url="https://www.chewy.com",
        id_extractors=SimpleNamespace(parent_from_url_regex=re.compile(r"/dp/(\d+)")),
    )

    class _FakeEngine:
        def capture_listing_page(self, *, url: str, **_kwargs):
            return CapturedListingPage(
                requested_url=url,
                final_url="https://www.chewy.com/b/wet-food-389",
                html="<html><body>base category</body></html>",
                candidates=(
                    CandidateLink(
                        url="https://www.chewy.com/base-category-product/dp/111",
                        title="Base Category Product",
                    ),
                ),
            )

        def click_next_listing_page(self, *, retailer: str) -> str | None:
            raise AssertionError("redirected filter should not paginate")

    observations, first_capture, completed = _crawl_surface(
        engine=_FakeEngine(),  # type: ignore[arg-type]
        strategy=ChewyCDPStrategy(),
        profile=profile,  # type: ignore[arg-type]
        category_key="wet_cat_food",
        surface_url="https://www.chewy.com/f/alligator-wet-cat-food_c389_f4v265383",
        source_surface="filter:flavor=Alligator",
        sort_mode="default",
        max_pages=2,
        delay_seconds=0,
        failure_artifact_root=tmp_path,
    )

    assert completed is True
    assert first_capture is not None
    assert observations == []


def test_crawl_surface_manual_navigation_failure_is_resumable_fatal(
    tmp_path: Path,
) -> None:
    profile = SimpleNamespace(
        base_url="https://www.chewy.com",
        id_extractors=SimpleNamespace(parent_from_url_regex=re.compile(r"/dp/(\d+)")),
    )

    class _FakeEngine:
        def capture_listing_page(self, **_kwargs):
            raise AssertionError("capture should not run after navigation failure")

    def _manual_loader(*_args) -> None:
        raise RuntimeError("Chrome did not reach requested URL")

    with pytest.raises(FatalRetailerDiscoveryError) as exc_info:
        _crawl_surface(
            engine=_FakeEngine(),  # type: ignore[arg-type]
            strategy=ChewyCDPStrategy(),
            profile=profile,  # type: ignore[arg-type]
            category_key="wet_cat_food",
            surface_url="https://www.chewy.com/b/wet-food-389",
            source_surface="category",
            sort_mode="newest",
            max_pages=1,
            delay_seconds=0,
            failure_artifact_root=tmp_path,
            manual_navigation_loader=_manual_loader,
        )

    assert "resume with --resume" in str(exc_info.value)


def test_crawl_surface_completes_after_duplicate_only_later_page(
    tmp_path: Path,
) -> None:
    profile = SimpleNamespace(
        base_url="https://www.saloncentric.com",
        id_extractors=SimpleNamespace(
            parent_from_url_regex=re.compile(r"/([^/?#]+)\.html")
        ),
    )
    candidates = (
        CandidateLink(
            url="https://www.saloncentric.com/PRODUCT-A.html",
            title="Product A",
        ),
        CandidateLink(
            url="https://www.saloncentric.com/PRODUCT-B.html",
            title="Product B",
        ),
    )

    class _Strategy(SaloncentricCDPStrategy):
        def next_page_url(self, *, current_url: str, html: str, current_page: int):
            if current_page == 1:
                return "https://www.saloncentric.com/hair-color?page=2"
            return None

    class _FakeEngine:
        def capture_listing_page(self, *, url: str, **_kwargs):
            return CapturedListingPage(
                requested_url=url,
                final_url=url,
                html="<html><body></body></html>",
                candidates=candidates,
            )

    observations, _first_capture, completed = _crawl_surface(
        engine=_FakeEngine(),  # type: ignore[arg-type]
        strategy=_Strategy(),
        profile=profile,  # type: ignore[arg-type]
        category_key="permanent",
        surface_url="https://www.saloncentric.com/hair-color",
        source_surface="category",
        sort_mode="new_arrivals",
        max_pages=2,
        delay_seconds=0,
        failure_artifact_root=tmp_path,
    )

    assert completed is True
    assert [row.parent_product_id for row in observations] == ["PRODUCT-A", "PRODUCT-B"]
    assert not (tmp_path / "failure_bundles").exists()


def test_crawl_surface_stops_before_building_rows_from_saks_pdp_landing(
    tmp_path: Path,
) -> None:
    profile = SimpleNamespace(
        base_url="https://www.saksfifthavenue.com",
        id_extractors=SimpleNamespace(
            parent_from_url_regex=re.compile(r"-(\d+)\.html")
        ),
    )

    class _FakeEngine:
        def capture_listing_page(self, *, url: str, **_kwargs):
            if "start=24" in url:
                return CapturedListingPage(
                    requested_url=url,
                    final_url=(
                        "https://www.saksfifthavenue.com/product/"
                        "miu-miu-cashmere-polo-sweater-0400024848677.html"
                    ),
                    html="<html><body>pdp recommendations</body></html>",
                    candidates=(
                        CandidateLink(
                            url=(
                                "https://www.saksfifthavenue.com/product/"
                                "recommendation-cashmere-sweater-0400026541319.html"
                            ),
                            title="Recommendation Cashmere Sweater",
                        ),
                    ),
                )
            return CapturedListingPage(
                requested_url=url,
                final_url=url,
                html="<html><body>listing</body></html>",
                candidates=(
                    CandidateLink(
                        url=(
                            "https://www.saksfifthavenue.com/product/"
                            "saks-fifth-avenue-cashmere-cardigan-0400024692491.html"
                        ),
                        title="Cashmere Cardigan",
                    ),
                ),
            )

    observations, _first_capture, completed = _crawl_surface(
        engine=_FakeEngine(),  # type: ignore[arg-type]
        strategy=SaksfifthavenueCDPStrategy(),
        profile=profile,  # type: ignore[arg-type]
        category_key="cashmere_sweaters",
        surface_url="https://www.saksfifthavenue.com/c/women-s-apparel/sweaters/cashmere",
        source_surface="filter:style=Graphic & Logo",
        sort_mode="default",
        max_pages=2,
        delay_seconds=0,
        failure_artifact_root=tmp_path,
    )

    assert completed is True
    assert [row.parent_product_id for row in observations] == ["0400024692491"]
    assert all("/product/" not in row.listing_url for row in observations)


def test_main_writes_outputs_and_updates_links(
    monkeypatch,
    tmp_path: Path,
    fake_pdp_stores: list[_FakePDPStore],
) -> None:
    output_root = tmp_path / "runs"
    links_path = tmp_path / "links.json"
    pdp_store_path = tmp_path / "pdp_store"
    profile = SimpleNamespace(
        profile_name="saloncentric_permanent",
        base_url="https://www.saloncentric.com",
        category_urls=(
            "https://www.saloncentric.com/hair-color?plp=true&prefn1=productTypeSc&prefv1=permanent",
        ),
        id_extractors=SimpleNamespace(
            parent_from_url_regex=re.compile(r"/([^/?#]+)\.html")
        ),
    )

    capture_calls: list[str] = []

    class _FakeEngine:
        def __init__(self, **_kwargs) -> None:
            return None

        def __enter__(self):
            return self

        def __exit__(self, *_args) -> None:
            return None

        def capture_listing_page(self, *, url: str, **_kwargs):
            capture_calls.append(url)
            if "haircolortonesc" in url.lower():
                return CapturedListingPage(
                    requested_url=url,
                    final_url=url,
                    html="<html><body>filter page</body></html>",
                    candidates=(
                        CandidateLink(
                            url="https://www.saloncentric.com/PRODUCT-B.html",
                            title="Product B",
                        ),
                    ),
                )
            base_html = """
            <html><body>
              <a href="/hair-color?plp=true&prefn1=productTypeSc&prefv1=permanent&prefn2=hairColorToneSc&prefv2=Cool">
                Cool
              </a>
            </body></html>
            """
            return CapturedListingPage(
                requested_url=url,
                final_url=url,
                html=base_html,
                candidates=(
                    CandidateLink(
                        url="https://www.saloncentric.com/PRODUCT-A.html",
                        title="Product A",
                    ),
                ),
            )

    monkeypatch.setattr(
        "scripts.run_retailer_listing_discovery_cdp._load_profiles",
        lambda retailer, categories: [profile],
    )
    monkeypatch.setattr(
        "scripts.run_retailer_listing_discovery_cdp.strategy_for_retailer",
        lambda retailer: SaloncentricCDPStrategy(),
    )
    monkeypatch.setattr(
        "scripts.run_retailer_listing_discovery_cdp.CDPListingEngine",
        _FakeEngine,
    )
    monkeypatch.setattr(
        "scripts.run_retailer_listing_discovery_cdp._send_manual_intervention_alert",
        lambda **_kwargs: None,
    )

    exit_code = main(
        [
            "--retailer",
            "saloncentric",
            "--output-root",
            str(output_root),
            "--links-path",
            str(links_path),
            "--pdp-store-path",
            str(pdp_store_path),
            "--write-csv-artifacts",
            "--categories",
            "permanent",
            "--filter-families",
            "haircolor tone",
            "--delay-seconds",
            "0",
        ]
    )

    assert exit_code == 0
    run_dirs = sorted(
        path for path in (output_root / "saloncentric").iterdir() if path.is_dir()
    )
    assert len(run_dirs) == 1
    output_dir = run_dirs[0]
    assert (output_dir / "retailer_listing_observations.csv").exists()
    assert (output_dir / "retailer_listing_classification.csv").exists()
    assert (output_dir / "retailer_filter_surfaces.csv").exists()
    assert (output_dir / "retailer_filter_observations.csv").exists()
    assert not (output_dir / "listing_observations.csv").exists()
    assert not (output_dir / "classification.csv").exists()
    assert not (output_dir / "filter_surfaces.csv").exists()
    assert not (output_dir / "filter_observations.csv").exists()

    summary = json.loads((output_dir / "summary.json").read_text(encoding="utf-8"))
    assert summary["categories"] == ["permanent"]
    assert summary["listing_rows"] == 2
    assert summary["filter_surface_rows"] == 1
    assert summary["filter_observation_rows"] == 1
    assert summary["classification_rows"] == 1
    assert summary["pdp_store_backend"] == "postgres"
    assert summary["csv_artifacts_written"] is True
    assert "pdp_store_path" not in summary

    assert len(fake_pdp_stores) == 1
    assert len(fake_pdp_stores[0].listing_observations) == 2
    assert len(fake_pdp_stores[0].filter_surfaces) == 1
    assert len(fake_pdp_stores[0].filter_observations) == 1

    links_payload = json.loads(links_path.read_text(encoding="utf-8"))
    assert links_payload == {
        "saloncentric": {
            "permanent": [
                "https://www.saloncentric.com/PRODUCT-A.html",
                "https://www.saloncentric.com/PRODUCT-B.html",
            ]
        }
    }
    assert (
        capture_calls.count(
            "https://www.saloncentric.com/hair-color?plp=true&prefn1=productTypeSc&prefv1=permanent"
        )
        == 1
    )
    assert (
        "https://www.saloncentric.com/hair-color?plp=true&prefn1=productTypeSc&prefv1=permanent&prefn2=hairColorToneSc&prefv2=Cool"
        in capture_calls
    )


def test_main_fails_when_ranked_sort_sequences_are_identical(
    monkeypatch,
    tmp_path: Path,
) -> None:
    output_root = tmp_path / "runs"
    links_path = tmp_path / "links.json"
    pdp_store_path = tmp_path / "pdp_store"
    profile = SimpleNamespace(
        profile_name="saloncentric_permanent",
        base_url="https://www.saloncentric.com",
        category_urls=(
            "https://www.saloncentric.com/hair-color?plp=true&prefn1=productTypeSc&prefv1=permanent",
        ),
        id_extractors=SimpleNamespace(
            parent_from_url_regex=re.compile(r"/([^/?#]+)\.html")
        ),
    )
    candidates = tuple(
        CandidateLink(
            url=f"https://www.saloncentric.com/PRODUCT-{index}.html",
            title=f"Product {index}",
        )
        for index in range(1, 6)
    )

    class _FakeEngine:
        def __init__(self, **_kwargs) -> None:
            return None

        def __enter__(self):
            return self

        def __exit__(self, *_args) -> None:
            return None

        def capture_listing_page(self, *, url: str, **_kwargs):
            return CapturedListingPage(
                requested_url=url,
                final_url=url,
                html="<html><body></body></html>",
                candidates=candidates,
            )

    monkeypatch.setattr(
        "scripts.run_retailer_listing_discovery_cdp._load_profiles",
        lambda retailer, categories: [profile],
    )
    monkeypatch.setattr(
        "scripts.run_retailer_listing_discovery_cdp.strategy_for_retailer",
        lambda retailer: SaloncentricCDPStrategy(),
    )
    monkeypatch.setattr(
        "scripts.run_retailer_listing_discovery_cdp.CDPListingEngine",
        _FakeEngine,
    )

    exit_code = main(
        [
            "--retailer",
            "saloncentric",
            "--output-root",
            str(output_root),
            "--links-path",
            str(links_path),
            "--pdp-store-path",
            str(pdp_store_path),
            "--categories",
            "permanent",
            "--delay-seconds",
            "0",
            "--no-capture-filters",
        ]
    )

    assert exit_code == 1
    run_dirs = sorted(
        path for path in (output_root / "saloncentric").iterdir() if path.is_dir()
    )
    assert len(run_dirs) == 1
    summary = json.loads((run_dirs[0] / "summary.json").read_text(encoding="utf-8"))
    assert summary["sort_sequence_quality"]["status"] == "failed"
    assert summary["sort_sequence_quality"]["blocking_identical_sort_sequence_pairs"]
    assert not links_path.exists()
    assert not pdp_store_path.exists()


def test_main_aborts_saks_stale_identical_sort_before_filters(
    monkeypatch,
    tmp_path: Path,
) -> None:
    output_root = tmp_path / "runs"
    links_path = tmp_path / "links.json"
    pdp_store_path = tmp_path / "pdp_store"
    profile = SimpleNamespace(
        profile_name="saksfifthavenue_low_top_sneakers",
        base_url="https://www.saksfifthavenue.com",
        category_urls=(
            "https://www.saksfifthavenue.com/c/shoes/shoes/sneakers/low-tops",
        ),
        id_extractors=SimpleNamespace(
            parent_from_url_regex=re.compile(r"/product/([^/?#]+)\.html")
        ),
    )
    candidates = tuple(
        CandidateLink(
            url=f"https://www.saksfifthavenue.com/product/sneaker-{index}.html",
            title=f"Sneaker {index}",
        )
        for index in range(1, 6)
    )
    capture_calls: list[tuple[str, bool]] = []

    class _FakeEngine:
        def __init__(self, **_kwargs) -> None:
            return None

        def __enter__(self):
            return self

        def __exit__(self, *_args) -> None:
            return None

        def capture_listing_page(
            self,
            *,
            url: str,
            force_navigation: bool = False,
            **_kwargs,
        ):
            capture_calls.append((url, force_navigation))
            return CapturedListingPage(
                requested_url=url,
                final_url=url,
                html="<html><body></body></html>",
                candidates=candidates,
            )

    monkeypatch.setattr(
        "scripts.run_retailer_listing_discovery_cdp._load_profiles",
        lambda retailer, categories: [profile],
    )
    monkeypatch.setattr(
        "scripts.run_retailer_listing_discovery_cdp.strategy_for_retailer",
        lambda retailer: SaksfifthavenueCDPStrategy(),
    )
    monkeypatch.setattr(
        "scripts.run_retailer_listing_discovery_cdp.CDPListingEngine",
        _FakeEngine,
    )

    exit_code = main(
        [
            "--retailer",
            "saksfifthavenue",
            "--output-root",
            str(output_root),
            "--links-path",
            str(links_path),
            "--pdp-store-path",
            str(pdp_store_path),
            "--categories",
            "low_top_sneakers",
            "--delay-seconds",
            "0",
            "--max-pages",
            "1",
            "--no-capture-filters",
        ]
    )

    assert exit_code == 1
    assert capture_calls == [
        (
            "https://www.saksfifthavenue.com/c/shoes/shoes/sneakers/low-tops?srule=new-arrivals",
            False,
        ),
        (
            "https://www.saksfifthavenue.com/c/shoes/shoes/sneakers/low-tops?srule=best-sellers-dollars",
            False,
        ),
        (
            "https://www.saksfifthavenue.com/c/shoes/shoes/sneakers/low-tops?srule=best-sellers-dollars",
            True,
        ),
    ]
    run_dirs = sorted(
        path for path in (output_root / "saksfifthavenue").iterdir() if path.is_dir()
    )
    assert len(run_dirs) == 1
    assert (run_dirs[0] / "resume_checkpoint.json").exists()
    assert not (run_dirs[0] / "summary.json").exists()
    assert not links_path.exists()
    assert not pdp_store_path.exists()


def test_main_aborts_resumed_saks_identical_sort_before_filters(
    monkeypatch,
    tmp_path: Path,
) -> None:
    output_root = tmp_path / "runs"
    run_dir = output_root / "saksfifthavenue" / "resume-run"
    links_path = tmp_path / "links.json"
    pdp_store_path = tmp_path / "pdp_store"
    category_url = "https://www.saksfifthavenue.com/c/shoes/shoes/sneakers/low-tops"
    category_key = "low_top_sneakers"
    profile = SimpleNamespace(
        profile_name="saksfifthavenue_low_top_sneakers",
        base_url="https://www.saksfifthavenue.com",
        category_urls=(category_url,),
        id_extractors=SimpleNamespace(
            parent_from_url_regex=re.compile(r"/product/([^/?#]+)\.html")
        ),
    )
    strategy = SaksfifthavenueCDPStrategy()
    observations = [
        ListingObservation(
            retailer="saksfifthavenue",
            category_key=category_key,
            source_surface="category",
            sort_mode=sort_mode,
            page=1,
            position=position,
            pdp_url=(
                "https://www.saksfifthavenue.com/product/" f"sneaker-{position}.html"
            ),
            parent_product_id=f"sneaker-{position}",
            product_name=f"Sneaker {position}",
            listing_url=strategy.apply_sort_mode(category_url, sort_mode),
        )
        for sort_mode in strategy.default_sort_modes
        for position in range(1, 6)
    ]
    completed_surface_keys = {
        discovery_cdp._listing_surface_checkpoint_key(
            category_key=category_key,
            source_surface="category",
            sort_mode=sort_mode,
            surface_url=strategy.apply_sort_mode(category_url, sort_mode),
        )
        for sort_mode in strategy.default_sort_modes
    }
    discovery_cdp._write_discovery_checkpoint(
        output_dir=run_dir,
        crawl_ts="2026-05-01T00:00:00+00:00",
        retailer="saksfifthavenue",
        categories=[category_key],
        sort_modes=strategy.default_sort_modes,
        observations=observations,
        filter_surfaces=[
            FilterSurface(
                retailer="saksfifthavenue",
                category_key=category_key,
                filter_family="color",
                filter_value="Black",
                filter_url=f"{category_url}?prefn1=color&prefv1=Black",
            )
        ],
        filter_observations=[],
        completed_surface_keys=completed_surface_keys,
    )

    class _FakeEngine:
        def __init__(self, **_kwargs) -> None:
            return None

        def __enter__(self):
            return self

        def __exit__(self, *_args) -> None:
            return None

        def capture_listing_page(self, **_kwargs):
            raise AssertionError("invalid resumed sort evidence should stop first")

    monkeypatch.setattr(
        "scripts.run_retailer_listing_discovery_cdp._load_profiles",
        lambda retailer, categories: [profile],
    )
    monkeypatch.setattr(
        "scripts.run_retailer_listing_discovery_cdp.strategy_for_retailer",
        lambda retailer: strategy,
    )
    monkeypatch.setattr(
        "scripts.run_retailer_listing_discovery_cdp.CDPListingEngine",
        _FakeEngine,
    )

    exit_code = main(
        [
            "--retailer",
            "saksfifthavenue",
            "--output-root",
            str(output_root),
            "--links-path",
            str(links_path),
            "--pdp-store-path",
            str(pdp_store_path),
            "--categories",
            category_key,
            "--resume-run-dir",
            str(run_dir),
            "--delay-seconds",
            "0",
        ]
    )

    assert exit_code == 1
    assert not links_path.exists()
    assert not pdp_store_path.exists()


def test_main_kiko_captures_filter_evidence_from_generic_discovery(
    monkeypatch,
    tmp_path: Path,
) -> None:
    output_root = tmp_path / "runs"
    links_path = tmp_path / "links.json"
    pdp_store_path = tmp_path / "pdp_store"
    evidence_root = tmp_path / "retailer_filter_evidence"
    cache_root = tmp_path / "attribute_cache"
    (cache_root / "kiko").mkdir(parents=True)
    pl.DataFrame(
        [
            {
                "parent_product_id": "parent-a",
                "variant_id": "variant-a",
                "backend_id": "",
                "backend_parent_id": "",
            }
        ]
    ).write_parquet(cache_root / "kiko" / "variants.parquet")
    profile = SimpleNamespace(
        profile_name="kiko_foundation",
        base_url="https://www.kikocosmetics.com",
        category_urls=(
            "https://www.kikocosmetics.com/{locale}/c/make-up/face/foundations/",
        ),
        id_extractors=SimpleNamespace(
            parent_from_url_regex=re.compile(r"/p/([A-Za-z0-9-]+)")
        ),
    )
    crawl_call: dict[str, object] = {}

    class _FakeEngine:
        def __init__(self, **_kwargs) -> None:
            return None

        def __enter__(self):
            return self

        def __exit__(self, *_args) -> None:
            return None

        def capture_listing_page(self, *, url: str, **_kwargs):
            return CapturedListingPage(
                requested_url=url,
                final_url=url,
                html=_kiko_category_html(),
                candidates=(
                    CandidateLink(
                        url="https://www.kikocosmetics.com/en-us/p/listing-product-123/",
                        title="Listing Product",
                    ),
                ),
            )

    def _fake_crawl_kiko_filter_observations(**kwargs):
        crawl_call.update(kwargs)
        return [
            FilterObservation(
                retailer="kiko",
                category_key="foundation",
                filter_family="finish",
                filter_value="matte",
                source_surface="filter:finish=matte",
                pdp_url="https://www.kikocosmetics.com/en-us/p/filter-product-123/",
                parent_product_id="parent-a",
                page=1,
                position=1,
                listing_url=kwargs["category_url"],
            )
        ]

    monkeypatch.setattr(
        "scripts.run_retailer_listing_discovery_cdp._load_profiles",
        lambda retailer, categories: [profile],
    )
    monkeypatch.setattr(
        "scripts.run_retailer_listing_discovery_cdp.CDPListingEngine",
        _FakeEngine,
    )
    monkeypatch.setattr(
        "scripts.run_retailer_listing_discovery_cdp.crawl_kiko_filter_observations",
        _fake_crawl_kiko_filter_observations,
    )
    monkeypatch.setattr(
        "scripts.run_retailer_listing_discovery_cdp._send_manual_intervention_alert",
        lambda **_kwargs: None,
    )

    exit_code = main(
        [
            "--retailer",
            "kiko",
            "--output-root",
            str(output_root),
            "--links-path",
            str(links_path),
            "--pdp-store-path",
            str(pdp_store_path),
            "--filter-evidence-root",
            str(evidence_root),
            "--attribute-cache-root",
            str(cache_root),
            "--categories",
            "foundation",
            "--filter-families",
            "finish",
            "--delay-seconds",
            "0",
            "--max-pages",
            "1",
            "--filter-max-pages",
            "1",
        ]
    )

    assert exit_code == 0
    assert crawl_call["category_url"] == (
        "https://www.kikocosmetics.com/en-us/c/make-up/face/foundations/"
    )
    assert crawl_call["variant_parent_lookup"] == {"variant-a": ("parent-a",)}
    assert crawl_call["allowed_families"] == ("finish",)

    run_dirs = sorted(
        path for path in (output_root / "kiko").iterdir() if path.is_dir()
    )
    assert len(run_dirs) == 1
    summary = json.loads((run_dirs[0] / "summary.json").read_text(encoding="utf-8"))
    assert summary["filter_surface_rows"] == 1
    assert summary["filter_observation_rows"] == 1
    assert summary["filter_evidence_dir"] == str(evidence_root / "kiko")
    assert summary["csv_artifacts_written"] is False
    assert not (run_dirs[0] / "retailer_listing_observations.csv").exists()

    evidence_frame = pl.read_parquet(
        evidence_root / "kiko" / "filter_observations.parquet"
    )
    assert evidence_frame.to_dicts()[0]["parent_product_id"] == "parent-a"
    assert (evidence_root / "kiko" / "filter_surfaces.parquet").exists()
    assert (evidence_root / "kiko" / "retailer_filter_surfaces.csv").exists()
    assert (evidence_root / "kiko" / "retailer_filter_observations.csv").exists()

    links_payload = json.loads(links_path.read_text(encoding="utf-8"))
    assert links_payload == {
        "kiko": {
            "foundation": [
                "https://www.kikocosmetics.com/en-us/p/filter-product-123/",
            ]
        }
    }


def test_main_writes_failure_bundle_for_blocked_page(
    monkeypatch,
    tmp_path: Path,
) -> None:
    output_root = tmp_path / "runs"
    links_path = tmp_path / "links.json"
    pdp_store_path = tmp_path / "pdp_store"
    profile = SimpleNamespace(
        profile_name="saloncentric_permanent",
        base_url="https://www.saloncentric.com",
        category_urls=(
            "https://www.saloncentric.com/hair-color?plp=true&prefn1=productTypeSc&prefv1=permanent",
        ),
        id_extractors=SimpleNamespace(
            parent_from_url_regex=re.compile(r"/([^/?#]+)\.html")
        ),
    )

    class _FakeEngine:
        def __init__(self, **_kwargs) -> None:
            return None

        def __enter__(self):
            return self

        def __exit__(self, *_args) -> None:
            return None

        def capture_listing_page(self, *, url: str, **_kwargs):
            html = """
            <html>
              <head><title>Just a moment...</title></head>
              <body>
                <iframe src="https://challenges.cloudflare.com/cdn-cgi/challenge-platform/h/g/turnstile"></iframe>
              </body>
            </html>
            """
            return CapturedListingPage(
                requested_url=url,
                final_url=url,
                html=html,
                candidates=(),
                page_title="Just a moment...",
                selector_found=False,
            )

    monkeypatch.setattr(
        "scripts.run_retailer_listing_discovery_cdp._load_profiles",
        lambda retailer, categories: [profile],
    )
    monkeypatch.setattr(
        "scripts.run_retailer_listing_discovery_cdp.strategy_for_retailer",
        lambda retailer: SaloncentricCDPStrategy(),
    )
    monkeypatch.setattr(
        "scripts.run_retailer_listing_discovery_cdp.CDPListingEngine",
        _FakeEngine,
    )

    exit_code = main(
        [
            "--retailer",
            "saloncentric",
            "--output-root",
            str(output_root),
            "--links-path",
            str(links_path),
            "--pdp-store-path",
            str(pdp_store_path),
            "--categories",
            "permanent",
            "--delay-seconds",
            "0",
        ]
    )

    assert exit_code == 0
    run_dirs = sorted(
        path for path in (output_root / "saloncentric").iterdir() if path.is_dir()
    )
    assert len(run_dirs) == 1
    output_dir = run_dirs[0]

    summary = json.loads((output_dir / "summary.json").read_text(encoding="utf-8"))
    assert summary["listing_rows"] == 0
    assert summary["failure_bundle_count"] >= 1

    diagnosis_files = sorted((output_dir / "failure_bundles").glob("*/diagnosis.json"))
    assert diagnosis_files
    diagnosis = json.loads(diagnosis_files[0].read_text(encoding="utf-8"))
    assert diagnosis["classification"] == "cloudflare_challenge"


def test_main_sends_alert_for_manual_intervention_failure(
    monkeypatch,
    tmp_path: Path,
) -> None:
    output_root = tmp_path / "runs"
    links_path = tmp_path / "links.json"
    pdp_store_path = tmp_path / "pdp_store"
    profile = SimpleNamespace(
        profile_name="cosmoprofbeauty_permanent",
        base_url="https://www.cosmoprofbeauty.com",
        category_urls=("https://www.cosmoprofbeauty.com/hair-color/permanent",),
        id_extractors=SimpleNamespace(
            parent_from_url_regex=re.compile(r"/([^/?#]+)\\.html")
        ),
    )
    alerts: list[dict[str, object]] = []

    class _FakeStrategy:
        retailer = "cosmoprofbeauty"
        selector = ".product-grid .grid-tile a[href$='.html']"
        default_sort_modes = ("new_arrivals",)
        filter_sort_modes = ()
        load_more_texts = ()

        def profile_to_category_key(self, profile_name: str) -> str:
            return "permanent"

        def apply_sort_mode(self, url: str, sort_mode: str) -> str:
            return url

        def next_page_url(self, *, current_url: str, html: str, current_page: int):
            return None

        def build_observations(self, **_kwargs):
            return []

        def extract_filter_surfaces(self, **_kwargs):
            return []

    class _FakeEngine:
        def __init__(self, **_kwargs) -> None:
            return None

        def __enter__(self):
            return self

        def __exit__(self, *_args) -> None:
            return None

        def capture_listing_page(self, *, url: str, **_kwargs):
            html = """
            <html>
              <head><title>Access to this page has been denied.</title></head>
              <body>
                SECURITY CHECK
                Access to this page has been denied.
              </body>
            </html>
            """
            return CapturedListingPage(
                requested_url=url,
                final_url=url,
                html=html,
                candidates=(),
                page_title="Access to this page has been denied.",
                selector_found=False,
            )

    monkeypatch.setattr(
        "scripts.run_retailer_listing_discovery_cdp._load_profiles",
        lambda retailer, categories: [profile],
    )
    monkeypatch.setattr(
        "scripts.run_retailer_listing_discovery_cdp.strategy_for_retailer",
        lambda retailer: _FakeStrategy(),
    )
    monkeypatch.setattr(
        "scripts.run_retailer_listing_discovery_cdp.CDPListingEngine",
        _FakeEngine,
    )
    monkeypatch.setattr(
        "scripts.run_retailer_listing_discovery_cdp._send_manual_intervention_alert",
        lambda **kwargs: alerts.append(kwargs),
    )

    exit_code = main(
        [
            "--retailer",
            "cosmoprofbeauty",
            "--output-root",
            str(output_root),
            "--links-path",
            str(links_path),
            "--pdp-store-path",
            str(pdp_store_path),
            "--categories",
            "permanent",
            "--delay-seconds",
            "0",
        ]
    )

    assert exit_code == 0
    assert len(alerts) == 1
    assert alerts[0]["classification"] == "access_denied_interstitial"


def test_main_aborts_for_chewy_blank_error_page(
    monkeypatch,
    tmp_path: Path,
) -> None:
    output_root = tmp_path / "runs"
    links_path = tmp_path / "links.json"
    pdp_store_path = tmp_path / "pdp_store"
    profile = SimpleNamespace(
        profile_name="chewy_wet_cat_food",
        base_url="https://www.chewy.com",
        category_urls=("https://www.chewy.com/b/wet-food-389",),
        id_extractors=SimpleNamespace(parent_from_url_regex=re.compile(r"/dp/(\\d+)")),
    )

    class _FakeStrategy:
        retailer = "chewy"
        selector = "a[href]"
        default_sort_modes = ("newest",)
        filter_sort_modes = ()
        load_more_texts = ()

        def profile_to_category_key(self, profile_name: str) -> str:
            return "wet_cat_food"

        def apply_sort_mode(self, url: str, sort_mode: str) -> str:
            return f"{url}?sort=newest"

        def next_page_url(self, *, current_url: str, html: str, current_page: int):
            return None

        def build_observations(self, **_kwargs):
            return []

        def extract_filter_surfaces(self, **_kwargs):
            return []

    class _FakeEngine:
        def __init__(self, **_kwargs) -> None:
            return None

        def __enter__(self):
            return self

        def __exit__(self, *_args) -> None:
            return None

        def capture_listing_page(self, *, url: str, **_kwargs):
            html = (
                "<html><body><script>window.KPSDK={};</script>"
                "<script src='/challenge/ips.js?KP_UIDz=abc'></script></body></html>"
            )
            return CapturedListingPage(
                requested_url=url,
                final_url=url,
                html=html,
                candidates=(),
                page_title="",
                selector_found=False,
            )

    monkeypatch.setattr(
        "scripts.run_retailer_listing_discovery_cdp._load_profiles",
        lambda retailer, categories: [profile],
    )
    monkeypatch.setattr(
        "scripts.run_retailer_listing_discovery_cdp.strategy_for_retailer",
        lambda retailer: _FakeStrategy(),
    )
    monkeypatch.setattr(
        "scripts.run_retailer_listing_discovery_cdp.CDPListingEngine",
        _FakeEngine,
    )

    exit_code = main(
        [
            "--retailer",
            "chewy",
            "--output-root",
            str(output_root),
            "--links-path",
            str(links_path),
            "--pdp-store-path",
            str(pdp_store_path),
            "--categories",
            "wet_cat_food",
            "--delay-seconds",
            "0",
            "--sort-modes",
            "newest",
            "--no-manual-navigation-auto-paste",
            "--no-capture-filters",
        ]
    )

    assert exit_code == 1
