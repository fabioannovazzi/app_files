from __future__ import annotations

import datetime as dt
from dataclasses import dataclass, field
from decimal import Decimal
from pathlib import Path
from typing import Any, Mapping, MutableMapping, Sequence


@dataclass(slots=True)
class FetchResult:
    """Store HTTP fetch metadata."""

    url: str
    status_code: int
    headers: Mapping[str, str]
    html: str
    fetched_at: dt.datetime


@dataclass(slots=True)
class ListingObservation:
    """Store one retailer listing observation for a PDP URL."""

    retailer: str
    category_key: str
    source_surface: str
    sort_mode: str
    page: int
    position: int
    pdp_url: str
    parent_product_id: str | None
    product_name: str | None
    brand: str | None = None
    has_new_badge: bool = False
    listing_url: str | None = None


@dataclass(slots=True)
class FilterSurface:
    """Describe one retailer filter surface discovered on a listing page."""

    retailer: str
    category_key: str
    filter_family: str
    filter_value: str
    filter_url: str
    filter_label: str | None = None


@dataclass(slots=True)
class FilterObservation:
    """Store one retailer filter-membership observation for a PDP URL."""

    retailer: str
    category_key: str
    filter_family: str
    filter_value: str
    source_surface: str
    pdp_url: str
    parent_product_id: str | None
    page: int
    position: int
    listing_url: str | None = None


@dataclass(slots=True)
class SitemapObservation:
    """Store one retailer sitemap observation."""

    retailer: str
    sitemap_source: str
    url: str
    lastmod: str | None
    url_type: str


@dataclass(slots=True)
class EvidenceBlob:
    """Record an extracted JSON/document blob with provenance."""

    source: str
    selector: str
    index: int
    payload: Any


@dataclass(slots=True)
class RawEvidence:
    """Link persisted evidence artifacts."""

    html_path: Path | None = None
    blob_paths: tuple[Path, ...] = ()
    html_sha256: str | None = None
    blob_sha256: tuple[str, ...] = ()


@dataclass(slots=True)
class ParentProduct:
    """Normalized parent (shadeable PDP)."""

    retailer: str
    parent_product_id: str
    pdp_url: str
    brand_raw: str
    brand_normalized: str | None
    title_raw: str
    title_normalized: str | None
    series_label_raw: str | None
    category_path: tuple[str, ...]
    has_color_selector: bool
    qa_flags: tuple[str, ...] = ()
    extras: MutableMapping[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class Variant:
    """Normalized child variant / SKU."""

    retailer: str
    parent_product_id: str
    variant_id: str
    shade_name_raw: str | None
    shade_name_normalized: str | None
    size_text_raw: str | None
    price_raw: str | None
    price: Decimal | None
    currency: str | None
    barcode: str | None
    swatch_image_url: str | None
    hero_image_url: str | None
    availability: str | None
    source_index: int | None = None
    qa_flags: tuple[str, ...] = ()
    extras: MutableMapping[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class ParseResult:
    """Outcome of parsing a single PDP."""

    parent: ParentProduct | None
    variants: tuple[Variant, ...]
    fetch_result: FetchResult
    blobs: tuple[EvidenceBlob, ...]
    raw_evidence: RawEvidence
    errors: tuple[str, ...] = ()
    warnings: tuple[str, ...] = ()


@dataclass(slots=True)
class BatchParseResult:
    """Aggregate result for multiple PDP URLs."""

    retailer: str
    profile_name: str
    parsed: tuple[ParseResult, ...]
    failures: tuple[str, ...]
    generated_at: dt.datetime

    def parents(self) -> Sequence[ParentProduct]:
        return [result.parent for result in self.parsed if result.parent is not None]

    def variants(self) -> Sequence[Variant]:
        variants: list[Variant] = []
        for result in self.parsed:
            variants.extend(result.variants)
        return variants


__all__ = [
    "BatchParseResult",
    "EvidenceBlob",
    "FilterObservation",
    "FilterSurface",
    "FetchResult",
    "ListingObservation",
    "ParentProduct",
    "ParseResult",
    "RawEvidence",
    "SitemapObservation",
    "Variant",
]
