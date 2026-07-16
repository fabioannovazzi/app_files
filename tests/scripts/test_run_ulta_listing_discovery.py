from __future__ import annotations

from pathlib import Path

import polars as pl

from modules.pdp.models import ListingObservation
from scripts.run_ulta_listing_discovery import (
    _parse_args,
    _build_prior_seen_identities,
    _category_links_from_observations,
    _merge_links_payload,
    _read_links_payload,
    _write_run_artifacts,
)


class _PriorSeenStore:
    def fetch_retailer_seen_listing_identities(
        self, *, retailer: str, before_crawl_ts: str
    ) -> set[str]:
        _ = retailer, before_crawl_ts
        return set()

    def existing_parent_ids(self, retailer: str) -> set[str]:
        _ = retailer
        return {"pimprod123"}

    def existing_pdp_urls(self, retailer: str) -> set[str]:
        _ = retailer
        return {"https://www.ulta.com/p/product-123?sku=abc"}


def test_build_prior_seen_identities_includes_existing_ulta_catalog() -> None:
    prior_seen = _build_prior_seen_identities(
        _PriorSeenStore(),
        crawl_ts="2026-04-02T10:00:00+00:00",
    )

    assert "pimprod123" in prior_seen
    assert "https://www.ulta.com/p/product-123" in prior_seen


def test_merge_links_payload_replaces_target_categories_and_keeps_others() -> None:
    existing = {
        "sephora": {"lipstick": ["https://www.sephora.com/p/a"]},
        "ulta": {
            "lipstick": ["https://www.ulta.com/p/old-lipstick-pimprod1"],
            "lip_gloss": ["https://www.ulta.com/p/old-gloss-pimprod2"],
            "foundation": ["https://www.ulta.com/p/foundation-pimprod3"],
        },
    }

    merged = _merge_links_payload(
        existing,
        retailer="ulta",
        category_links={
            "lipstick": ["https://www.ulta.com/p/new-lipstick-pimprod4"],
            "lip_gloss": [],
        },
    )

    assert merged["sephora"]["lipstick"] == ["https://www.sephora.com/p/a"]
    assert merged["ulta"]["lipstick"] == [
        "https://www.ulta.com/p/new-lipstick-pimprod4"
    ]
    assert merged["ulta"]["lip_gloss"] == []
    assert merged["ulta"]["foundation"] == [
        "https://www.ulta.com/p/foundation-pimprod3"
    ]


def test_write_run_artifacts_includes_generic_retailer_csv_aliases(
    tmp_path: Path,
) -> None:
    output_dir = tmp_path / "run"
    observations_frame = pl.DataFrame(
        {
            "crawl_ts": ["2026-04-29T12:00:00+00:00"],
            "retailer": ["ulta"],
            "category_key": ["lipstick"],
            "source_surface": ["category"],
            "sort_mode": ["new_arrivals"],
            "page": [1],
            "position": [1],
            "pdp_url": ["https://www.ulta.com/p/lipstick-pimprod1"],
            "parent_product_id": ["pimprod1"],
            "product_name": ["Lipstick"],
            "brand": ["Brand"],
            "has_new_badge": [False],
            "listing_url": ["https://www.ulta.com/lipstick"],
            "listing_identity": ["pimprod1"],
            "listing_status": ["new"],
        }
    )
    filter_observations_frame = pl.DataFrame(
        {
            "crawl_ts": ["2026-04-29T12:00:00+00:00"],
            "retailer": ["ulta"],
            "category_key": ["lipstick"],
            "filter_family": ["brand"],
            "filter_value": ["brand"],
            "source_surface": ["filter:brand=brand"],
            "pdp_url": ["https://www.ulta.com/p/lipstick-pimprod1"],
            "parent_product_id": ["pimprod1"],
            "page": [1],
            "position": [1],
            "listing_url": ["https://www.ulta.com/lipstick?brand=brand"],
        }
    )
    filter_surfaces_frame = pl.DataFrame(
        {
            "crawl_ts": ["2026-04-29T12:00:00+00:00"],
            "retailer": ["ulta"],
            "category_key": ["lipstick"],
            "filter_family": ["brand"],
            "filter_value": ["brand"],
            "filter_url": ["https://www.ulta.com/lipstick?brand=brand"],
            "filter_label": ["Brand"],
        }
    )

    _write_run_artifacts(
        output_dir=output_dir,
        observations_frame=observations_frame,
        category_links_payload={
            "lipstick": ["https://www.ulta.com/p/lipstick-pimprod1"]
        },
        filter_observations_frame=filter_observations_frame,
        filter_surfaces_frame=filter_surfaces_frame,
        sitemap_observations_frame=None,
        sitemap_missing_products_frame=None,
        summary={"crawl_ts": "2026-04-29T12:00:00+00:00"},
    )

    assert (output_dir / "retailer_listing_observations.csv").exists()
    assert (output_dir / "retailer_filter_observations.csv").exists()
    assert (output_dir / "retailer_filter_surfaces.csv").exists()
    assert not (output_dir / "listing_observations.csv").exists()
    assert not (output_dir / "filter_observations.csv").exists()
    assert not (output_dir / "filter_surfaces.csv").exists()


def test_category_links_from_observations_dedupes_within_category() -> None:
    observations = [
        ListingObservation(
            retailer="ulta",
            category_key="lipstick",
            source_surface="category",
            sort_mode="best_sellers",
            page=1,
            position=1,
            pdp_url="https://www.ulta.com/p/lipstick-a-pimprod1",
            parent_product_id="pimprod1",
            product_name="Lipstick A",
        ),
        ListingObservation(
            retailer="ulta",
            category_key="lipstick",
            source_surface="category",
            sort_mode="new_arrivals",
            page=1,
            position=1,
            pdp_url="https://www.ulta.com/p/lipstick-a-pimprod1",
            parent_product_id="pimprod1",
            product_name="Lipstick A",
        ),
        ListingObservation(
            retailer="ulta",
            category_key="lip_gloss",
            source_surface="category",
            sort_mode="best_sellers",
            page=1,
            position=1,
            pdp_url="https://www.ulta.com/p/gloss-b-pimprod2",
            parent_product_id="pimprod2",
            product_name="Gloss B",
        ),
    ]

    links = _category_links_from_observations(
        observations,
        category_keys={"lipstick", "lip_gloss", "lip_oil"},
    )

    assert links == {
        "lip_gloss": ["https://www.ulta.com/p/gloss-b-pimprod2"],
        "lip_oil": [],
        "lipstick": ["https://www.ulta.com/p/lipstick-a-pimprod1"],
    }


def test_read_links_payload_supports_legacy_single_retailer_shape(
    tmp_path: Path,
) -> None:
    path = tmp_path / "links.json"
    path.write_text(
        """
        {
          "retailer": "sephora",
          "categories": {
            "lipstick": ["https://www.sephora.com/p/a"],
            "lip_gloss": []
          }
        }
        """,
        encoding="utf-8",
    )

    payload = _read_links_payload(path)

    assert payload == {
        "sephora": {
            "lipstick": ["https://www.sephora.com/p/a"],
            "lip_gloss": [],
        }
    }


def test_parse_args_enables_filter_capture_by_default(monkeypatch) -> None:
    monkeypatch.setattr("sys.argv", ["run_ulta_listing_discovery.py"])

    args = _parse_args()

    assert args.capture_filters is True
    assert args.filter_families is None
    assert args.recent_share == 0.20
    assert args.sort_modes == ["best_sellers", "new_arrivals", "top_rated"]


def test_parse_args_allows_disabling_filter_capture(monkeypatch) -> None:
    monkeypatch.setattr(
        "sys.argv",
        ["run_ulta_listing_discovery.py", "--no-capture-filters"],
    )

    args = _parse_args()

    assert args.capture_filters is False
