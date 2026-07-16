from __future__ import annotations

from collections import defaultdict
from dataclasses import replace
from decimal import Decimal
from pathlib import Path
from typing import Iterable, Mapping, Sequence

import polars as pl
from polars.datatypes import List as ListType
from polars.datatypes import Struct as StructType

from . import (
    BatchParseResult,
    EvidenceStorage,
    HTMLFetcher,
    ParentProduct,
    PDPParser,
    Variant,
    load_profile,
)
from .adapters import NullAdapter
from .adapters.amazon import AmazonAdapter
from .adapters.chewy import ChewyAdapter
from .adapters.cosmoprofbeauty import CosmoprofbeautyAdapter
from .adapters.guestinresidence import GuestInResidenceAdapter
from .adapters.kiko import KikoAdapter
from .adapters.lorealparis import LorealParisAdapter
from .adapters.purina import PurinaAdapter
from .adapters.saksfifthavenue import SaksfifthavenueAdapter
from .adapters.saloncentric import SaloncentricAdapter
from .adapters.sephora import SephoraAdapter
from .adapters.tikicat import TikiCatAdapter
from .adapters.ulta import UltaAdapter
from .adapters.vince import VinceAdapter
from .amazon_fetcher import AmazonFetcher
from .http_headers import get_headers_for_retailer
from .http_proxies import get_proxies_for_retailer
from .pacing import HumanPacingController
from .postgres_compat import connect_pdp_database, pdp_database_exists
from .purina_fetcher import PurinaFetcher
from .sephora_fetcher import SephoraFetcher

PARENT_SCHEMA = {
    "retailer": pl.String,
    "parent_product_id": pl.String,
    "pdp_url": pl.String,
    "brand_raw": pl.String,
    "brand_normalized": pl.String,
    "title_raw": pl.String,
    "title_normalized": pl.String,
    "series_label_raw": pl.String,
    "category_path": pl.List(pl.String),
    "has_color_selector": pl.Boolean,
    "qa_flags": pl.List(pl.String),
}

VARIANT_SCHEMA = {
    "retailer": pl.String,
    "parent_product_id": pl.String,
    "variant_id": pl.String,
    "shade_name_raw": pl.String,
    "shade_name_normalized": pl.String,
    "size_text_raw": pl.String,
    "price_raw": pl.String,
    "price": pl.Decimal(38, 6),
    "currency": pl.String,
    "barcode": pl.String,
    "swatch_image_url": pl.String,
    "hero_image_url": pl.String,
    "availability": pl.String,
    "qa_flags": pl.List(pl.String),
}


def _empty_dataframe(schema: dict[str, pl.DataType]) -> pl.DataFrame:
    return pl.DataFrame(
        {key: pl.Series([], dtype=value) for key, value in schema.items()}
    )


def build_parser(
    profile_name: str,
    *,
    fetcher: HTMLFetcher | None = None,
    storage: EvidenceStorage | None = None,
    pacing: HumanPacingController | None = None,
) -> PDPParser:
    profile = load_profile(profile_name)
    adapter = _adapter_for_retailer(profile.retailer)
    if fetcher is None:
        headers = get_headers_for_retailer(profile.retailer)
        proxies = get_proxies_for_retailer(profile.retailer)
        retailer_lower = profile.retailer.lower()
        if retailer_lower == "sephora":
            storage_path = Path("caches") / "sephora_storage_state.json"
            fetcher = SephoraFetcher(
                headers=headers if headers else None,
                proxies=proxies if proxies else None,
                pacing=pacing,
                storage_path=storage_path,
            )
        elif retailer_lower == "amazon":
            storage_path = Path("caches") / "amazon_storage_state.json"
            fetcher = AmazonFetcher(
                headers=headers if headers else None,
                proxies=proxies if proxies else None,
                pacing=pacing,
                storage_path=storage_path,
            )
        elif retailer_lower == "purina":
            fetcher = PurinaFetcher(
                headers=headers if headers else None,
                proxies=proxies if proxies else None,
                pacing=pacing,
                cache_path=Path("caches") / "purina_api_products.json",
            )
        else:
            fetcher = HTMLFetcher(
                headers=headers if headers else None,
                proxies=proxies if proxies else None,
                pacing=pacing,
            )

    parser = PDPParser(
        profile=profile,
        adapter=adapter,
        fetcher=fetcher,
        storage=storage,
    )
    return parser


def _adapter_for_retailer(retailer: str):
    retailer_lower = retailer.lower()
    if retailer_lower == "ulta":
        return UltaAdapter()
    if retailer_lower == "sephora":
        return SephoraAdapter()
    if retailer_lower == "kiko":
        return KikoAdapter()
    if retailer_lower == "lorealparis":
        return LorealParisAdapter()
    if retailer_lower == "amazon":
        return AmazonAdapter()
    if retailer_lower == "chewy":
        return ChewyAdapter()
    if retailer_lower == "saloncentric":
        return SaloncentricAdapter()
    if retailer_lower == "cosmoprofbeauty":
        return CosmoprofbeautyAdapter()
    if retailer_lower == "saksfifthavenue":
        return SaksfifthavenueAdapter()
    if retailer_lower == "guestinresidence":
        return GuestInResidenceAdapter()
    if retailer_lower == "vince":
        return VinceAdapter()
    if retailer_lower == "tikicat":
        return TikiCatAdapter()
    if retailer_lower == "purina":
        return PurinaAdapter()
    return NullAdapter()


def apply_locale(profile: PDPProfile, locale: str) -> PDPProfile:
    """Return a profile with `{locale}` placeholders substituted."""

    if not locale:
        return profile

    def _maybe_replace(value: str) -> str:
        return value.replace("{locale}", locale) if "{locale}" in value else value

    category_urls = tuple(_maybe_replace(url) for url in profile.category_urls)
    category_hints = tuple(_maybe_replace(hint) for hint in profile.category_hints)
    base_url = _maybe_replace(profile.base_url)
    display_name = _maybe_replace(profile.display_name)

    return replace(
        profile,
        base_url=base_url,
        display_name=display_name,
        category_urls=category_urls,
        category_hints=category_hints,
    )


def parse_urls_to_batch(
    profile_name: str,
    urls: Sequence[str],
    *,
    fetcher: HTMLFetcher | None = None,
    storage: EvidenceStorage | None = None,
    pacing: HumanPacingController | None = None,
) -> BatchParseResult:
    parser = build_parser(profile_name, fetcher=fetcher, storage=storage, pacing=pacing)
    return parser.parse_urls(urls)


def parents_to_frame(parents: Iterable[ParentProduct]) -> pl.DataFrame:
    rows: list[dict[str, object]] = []
    for parent in parents:
        rows.append(
            {
                "retailer": parent.retailer,
                "parent_product_id": parent.parent_product_id,
                "pdp_url": parent.pdp_url,
                "brand_raw": parent.brand_raw,
                "brand_normalized": parent.brand_normalized,
                "title_raw": parent.title_raw,
                "title_normalized": parent.title_normalized,
                "series_label_raw": parent.series_label_raw,
                "category_path": list(parent.category_path),
                "has_color_selector": parent.has_color_selector,
                "qa_flags": list(parent.qa_flags),
            }
        )
    if not rows:
        return _empty_dataframe(PARENT_SCHEMA)
    return pl.from_dicts(rows, schema=PARENT_SCHEMA)


def variants_to_frame(variants: Iterable[Variant]) -> pl.DataFrame:
    rows: list[dict[str, object]] = []
    for variant in variants:
        rows.append(
            {
                "retailer": variant.retailer,
                "parent_product_id": variant.parent_product_id,
                "variant_id": variant.variant_id,
                "shade_name_raw": variant.shade_name_raw,
                "shade_name_normalized": variant.shade_name_normalized,
                "size_text_raw": variant.size_text_raw,
                "price_raw": variant.price_raw,
                "price": variant.price,
                "currency": variant.currency,
                "barcode": variant.barcode,
                "swatch_image_url": variant.swatch_image_url,
                "hero_image_url": variant.hero_image_url,
                "availability": variant.availability,
                "qa_flags": list(variant.qa_flags),
            }
        )
    if not rows:
        return _empty_dataframe(VARIANT_SCHEMA)
    return pl.from_dicts(rows, schema=VARIANT_SCHEMA)


def summarize_batch(batch: BatchParseResult) -> dict[str, object]:
    summary: dict[str, object] = {
        "retailer": batch.retailer,
        "profile": batch.profile_name,
        "parsed_count": len(batch.parsed),
        "failed_count": len(batch.failures),
        "failures": list(batch.failures),
        "warnings": defaultdict(int),
        "errors": defaultdict(int),
    }

    for result in batch.parsed:
        for warning in result.warnings:
            summary["warnings"][warning] += 1  # type: ignore[index]
        for error in result.errors:
            summary["errors"][error] += 1  # type: ignore[index]
    summary["warnings"] = dict(summary["warnings"])
    summary["errors"] = dict(summary["errors"])
    return summary


def load_parent_status(pdp_store_path: Path) -> pl.DataFrame:
    """Return discovery/last-seen/discontinued timestamps for analytics."""

    database_path = Path(pdp_store_path)
    if not pdp_database_exists(database_path):
        raise FileNotFoundError(f"PDP database not found: {database_path}")

    query = """
        SELECT
            retailer,
            parent_product_id,
            pdp_url,
            discovered_at,
            last_seen_at,
            discontinued_at
        FROM parent_products
    """
    with connect_pdp_database(database_path) as conn:
        cursor = conn.execute(query)
        rows = cursor.fetchall()
        column_names = [column[0] for column in cursor.description]

    frame = pl.DataFrame(rows, schema=column_names, orient="row")
    if frame.is_empty():
        return frame

    timestamp_columns = ("discovered_at", "last_seen_at", "discontinued_at")
    frame = frame.with_columns(
        *(pl.col(name).cast(pl.Utf8) for name in timestamp_columns)
    )
    frame = frame.with_columns(
        *(
            pl.col(name).str.strptime(
                pl.Datetime, format="%Y-%m-%dT%H:%M:%S%z", strict=False
            )
            for name in timestamp_columns
        )
    )
    return frame.with_columns(
        *(pl.col(name).dt.replace_time_zone("UTC") for name in timestamp_columns)
    )


def flatten_for_export(
    df: pl.DataFrame, *, list_separator: str = " | "
) -> pl.DataFrame:
    """Convert nested columns to strings for CSV export."""

    expressions: list[pl.Expr] = []
    for name, dtype in df.schema.items():
        if isinstance(dtype, ListType):
            expressions.append(
                pl.col(name)
                .list.eval(pl.element().cast(pl.String))
                .list.join(list_separator)
                .alias(name)
            )
        elif isinstance(dtype, StructType):
            expressions.append(pl.col(name).struct.json_encode().alias(name))
    if not expressions:
        return df
    return df.with_columns(expressions)


def variants_from_json(records: Sequence[Mapping[str, object]]) -> list[Variant]:
    """Reconstruct Variant instances from JSON-like records."""

    variants: list[Variant] = []
    for record in records:
        retailer = str(record.get("retailer") or "").strip()
        parent_id = str(record.get("parent_product_id") or "").strip()
        variant_id = str(record.get("variant_id") or "").strip()
        if not retailer or not parent_id or not variant_id:
            continue

        price_value = _coerce_decimal(record.get("price"))
        extras = record.get("extras")
        extras_mapping = dict(extras) if isinstance(extras, Mapping) else {}
        qa_flags_raw = record.get("qa_flags")
        if isinstance(qa_flags_raw, Sequence):
            qa_flags = tuple(str(flag) for flag in qa_flags_raw)
        else:
            qa_flags = ()

        variants.append(
            Variant(
                retailer=retailer,
                parent_product_id=parent_id,
                variant_id=variant_id,
                shade_name_raw=_optional_string(record.get("shade_name_raw")),
                shade_name_normalized=_optional_string(
                    record.get("shade_name_normalized")
                ),
                size_text_raw=_optional_string(record.get("size_text_raw")),
                price_raw=_optional_string(record.get("price_raw")),
                price=price_value,
                currency=_optional_string(record.get("currency")),
                barcode=_optional_string(record.get("barcode")),
                swatch_image_url=_optional_string(record.get("swatch_image_url")),
                hero_image_url=_optional_string(record.get("hero_image_url")),
                availability=_optional_string(record.get("availability")),
                source_index=_coerce_int(record.get("source_index")),
                qa_flags=qa_flags,
                extras=extras_mapping,
            )
        )
    return variants


def _optional_string(value: object) -> str | None:
    if isinstance(value, str):
        text = value.strip()
        return text or None
    return None


def _coerce_decimal(value: object) -> Decimal | None:
    if value is None:
        return None
    try:
        return Decimal(str(value))
    except Exception:
        return None


def _coerce_int(value: object) -> int | None:
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value)
    if isinstance(value, str) and value.strip():
        try:
            return int(value.strip())
        except ValueError:
            return None
    return None


__all__ = [
    "PARENT_SCHEMA",
    "VARIANT_SCHEMA",
    "apply_locale",
    "build_parser",
    "load_parent_status",
    "parents_to_frame",
    "parse_urls_to_batch",
    "flatten_for_export",
    "summarize_batch",
    "variants_from_json",
    "variants_to_frame",
]
