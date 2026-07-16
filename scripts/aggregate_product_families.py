from __future__ import annotations

import argparse
import datetime as dt
import json
import logging
import re
import sys
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

REPO_ROOT = Path(__file__).resolve().parents[1]
root_str = str(REPO_ROOT)
if root_str not in sys.path:
    sys.path.insert(0, root_str)

from modules.pdp.postgres_compat import DICT_ROW_FACTORY, connect_pdp_database
from modules.pdp.review_constants import (
    DEFAULT_PDP_STORE_PATH,
    add_pdp_store_path_argument,
    enforce_default_pdp_store_path,
)
from modules.utilities.secrets_loader import load_env_from_secrets_file

LOGGER = logging.getLogger(__name__)
AMAZON_ASIN_IN_URL = re.compile(r"/(?:dp|gp/product)/([A-Z0-9]{10})", re.IGNORECASE)

FAMILIES_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS product_families (
    retailer TEXT NOT NULL,
    category_key TEXT NOT NULL,
    parent_product_id TEXT NOT NULL,
    variant_count INTEGER NOT NULL,
    source_link_count INTEGER NOT NULL,
    generated_at TEXT NOT NULL,
    payload_json TEXT NOT NULL,
    PRIMARY KEY (retailer, category_key, parent_product_id)
)
"""

VARIANTS_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS product_variants (
    retailer TEXT NOT NULL,
    category_key TEXT NOT NULL,
    variant_id TEXT NOT NULL,
    parent_product_id TEXT NOT NULL,
    source_link_count INTEGER NOT NULL,
    generated_at TEXT NOT NULL,
    payload_json TEXT NOT NULL,
    PRIMARY KEY (retailer, category_key, variant_id)
)
"""

RUNS_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS product_aggregation_runs (
    retailer TEXT NOT NULL,
    category_key TEXT NOT NULL,
    generated_at TEXT NOT NULL,
    summary_json TEXT NOT NULL,
    PRIMARY KEY (retailer, category_key, generated_at)
)
"""


@dataclass(slots=True)
class CategoryAggregation:
    families: list[dict[str, Any]]
    variants: list[dict[str, Any]]
    summary: dict[str, Any]


def _parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Aggregate parsed PDP variants into product families by retailer/category "
            "using data/pdp/links.json + the PDP store."
        )
    )
    parser.add_argument(
        "--retailer",
        default="amazon",
        help="Retailer key from links.json and PDP store tables (default: amazon).",
    )
    parser.add_argument(
        "--category",
        action="append",
        help=(
            "Category key(s) from links.json to aggregate (use multiple times). "
            "Defaults to all categories for the retailer."
        ),
    )
    parser.add_argument(
        "--categories",
        action="append",
        dest="category",
        help=argparse.SUPPRESS,
    )
    parser.add_argument(
        "--links-path",
        type=Path,
        default=Path("data/pdp/links.json"),
        help="Path to links.json.",
    )
    add_pdp_store_path_argument(parser, default=None)
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("data/pdp/aggregates"),
        help="Directory where aggregation JSON files are written.",
    )
    parser.add_argument(
        "--skip-pdp-store-write",
        dest="skip_pdp_store_write",
        action="store_true",
        help="Skip writing product_families/product_variants tables to the PDP store.",
    )
    return parser.parse_args(argv)


def _dedupe_keep_order(values: Iterable[str]) -> list[str]:
    seen: set[str] = set()
    deduped: list[str] = []
    for value in values:
        normalized = str(value or "").strip()
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        deduped.append(normalized)
    return deduped


def _extract_amazon_asin(url: str) -> str | None:
    match = AMAZON_ASIN_IN_URL.search(url)
    if not match:
        return None
    return match.group(1).upper()


def _normalize_category(category: str) -> str:
    return str(category or "").strip().lower()


def _parse_json_object(raw: str | None) -> dict[str, Any]:
    if not raw:
        return {}
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError:
        return {}
    if isinstance(payload, Mapping):
        return dict(payload)
    return {}


def _category_keys_for_parent(
    category_path_raw: str | None,
    extras_raw: str | None,
) -> set[str]:
    categories: set[str] = set()
    if category_path_raw:
        try:
            parsed = json.loads(category_path_raw)
        except json.JSONDecodeError:
            parsed = None
        if isinstance(parsed, list):
            for value in parsed:
                normalized = _normalize_category(str(value))
                if normalized:
                    categories.add(normalized)
    extras = _parse_json_object(extras_raw)
    for key in ("category_key", "category", "category_slug"):
        value = extras.get(key)
        if isinstance(value, str):
            normalized = _normalize_category(value)
            if normalized:
                categories.add(normalized)
    categories_value = extras.get("categories")
    if isinstance(categories_value, list):
        for value in categories_value:
            normalized = _normalize_category(str(value))
            if normalized:
                categories.add(normalized)
    return categories


def _load_links_payload(links_path: Path) -> dict[str, Any]:
    if not links_path.exists():
        raise FileNotFoundError(f"Links file not found: {links_path}")
    payload = json.loads(links_path.read_text(encoding="utf-8"))
    if not isinstance(payload, Mapping):
        raise ValueError("links.json must contain a JSON object.")
    return dict(payload)


def _resolve_categories(
    links_payload: dict[str, Any],
    retailer: str,
    categories: Sequence[str] | None,
) -> list[str]:
    retailer_payload = links_payload.get(retailer)
    if not isinstance(retailer_payload, Mapping):
        raise ValueError(f"Retailer '{retailer}' not found in links payload.")

    available_categories = {
        _normalize_category(category): category for category in retailer_payload.keys()
    }
    if categories:
        requested = [_normalize_category(category) for category in categories]
        resolved = [category for category in requested if category]
        missing = sorted(
            category for category in resolved if category not in available_categories
        )
        if missing:
            raise ValueError(
                f"Categories not found for retailer '{retailer}': {', '.join(missing)}"
            )
        return _dedupe_keep_order(resolved)

    return sorted([category for category in available_categories if category])


def _category_links(
    links_payload: dict[str, Any],
    retailer: str,
    category_key: str,
) -> tuple[list[str], list[str]]:
    retailer_payload = links_payload.get(retailer)
    if not isinstance(retailer_payload, Mapping):
        return [], []
    links_value: Any = None
    for raw_category, raw_links in retailer_payload.items():
        if _normalize_category(str(raw_category)) == category_key:
            links_value = raw_links
            break
    if not isinstance(links_value, list):
        return [], []
    raw_links = [str(url).strip() for url in links_value if str(url).strip()]
    unique_links = _dedupe_keep_order(raw_links)
    return raw_links, unique_links


def _fetch_parent_rows(
    conn: Any,
    retailer: str,
    category_key: str,
) -> dict[str, dict[str, Any]]:
    rows = conn.execute(
        """
        SELECT
            parent_product_id,
            pdp_url,
            brand_raw,
            title_raw,
            title_normalized,
            category_path,
            extras
        FROM parent_products
        WHERE retailer = ?
        """,
        (retailer,),
    ).fetchall()
    parents: dict[str, dict[str, Any]] = {}
    for row in rows:
        parent_id = str(row["parent_product_id"] or "").strip()
        if not parent_id:
            continue
        categories = _category_keys_for_parent(row["category_path"], row["extras"])
        if category_key not in categories:
            continue
        parents[parent_id] = {
            "parent_product_id": parent_id,
            "pdp_url": str(row["pdp_url"] or "").strip(),
            "brand_raw": str(row["brand_raw"] or "").strip(),
            "title_raw": str(row["title_raw"] or "").strip(),
            "title_normalized": str(row["title_normalized"] or "").strip(),
            "category_keys": sorted(categories),
            "extras": _parse_json_object(row["extras"]),
        }
    return parents


def _fetch_variant_rows(
    conn: Any,
    retailer: str,
    parent_ids: Sequence[str],
) -> list[dict[str, Any]]:
    if not parent_ids:
        return []
    variants: list[dict[str, Any]] = []
    chunk_size = 400
    for start in range(0, len(parent_ids), chunk_size):
        chunk = parent_ids[start : start + chunk_size]
        placeholders = ",".join("?" for _ in chunk)
        rows = conn.execute(
            f"""
            SELECT
                variant_id,
                parent_product_id,
                shade_name_raw,
                size_text_raw,
                availability,
                hero_image_url,
                swatch_image_url,
                price_raw,
                price,
                currency,
                source_index,
                extras
            FROM variants
            WHERE retailer = ?
              AND parent_product_id IN ({placeholders})
            """,
            (retailer, *chunk),
        ).fetchall()
        for row in rows:
            variant_id = str(row["variant_id"] or "").strip()
            parent_id = str(row["parent_product_id"] or "").strip()
            if not variant_id or not parent_id:
                continue
            variants.append(
                {
                    "variant_id": variant_id,
                    "parent_product_id": parent_id,
                    "shade_name_raw": row["shade_name_raw"],
                    "size_text_raw": row["size_text_raw"],
                    "availability": row["availability"],
                    "hero_image_url": row["hero_image_url"],
                    "swatch_image_url": row["swatch_image_url"],
                    "price_raw": row["price_raw"],
                    "price": row["price"],
                    "currency": row["currency"],
                    "source_index": row["source_index"],
                    "extras": _parse_json_object(row["extras"]),
                }
            )
    variants.sort(key=lambda row: (row["parent_product_id"], row["variant_id"]))
    return variants


def aggregate_category(
    conn: Any,
    *,
    retailer: str,
    category_key: str,
    links: Sequence[str],
    generated_at: str,
) -> CategoryAggregation:
    parents = _fetch_parent_rows(conn, retailer=retailer, category_key=category_key)
    parent_ids = sorted(parents.keys())
    variants = _fetch_variant_rows(conn, retailer=retailer, parent_ids=parent_ids)

    variants_by_parent: dict[str, list[dict[str, Any]]] = defaultdict(list)
    variant_parent_map: dict[str, str] = {}
    for variant in variants:
        parent_id = variant["parent_product_id"]
        variant_id = variant["variant_id"]
        variants_by_parent[parent_id].append(variant)
        variant_parent_map[variant_id] = parent_id

    unique_links = _dedupe_keep_order(links)
    asin_to_links: dict[str, list[str]] = defaultdict(list)
    links_without_asin: list[str] = []
    for link in unique_links:
        asin = _extract_amazon_asin(link)
        if not asin:
            links_without_asin.append(link)
            continue
        asin_to_links[asin].append(link)

    source_links_by_family: dict[str, list[str]] = defaultdict(list)
    source_links_by_variant: dict[str, list[str]] = defaultdict(list)
    unmatched_asins: list[str] = []
    matched_asin_count = 0

    for asin, asin_links in asin_to_links.items():
        parent_id = variant_parent_map.get(asin)
        if parent_id is None and asin in parents:
            parent_id = asin
        if not parent_id:
            unmatched_asins.append(asin)
            continue

        matched_asin_count += 1
        source_links_by_family[parent_id].extend(asin_links)
        if asin in variant_parent_map:
            source_links_by_variant[asin].extend(asin_links)

    families: list[dict[str, Any]] = []
    for parent_id in parent_ids:
        parent = parents[parent_id]
        family_variants = variants_by_parent.get(parent_id, [])
        variant_ids = [row["variant_id"] for row in family_variants]
        family_links = _dedupe_keep_order(source_links_by_family.get(parent_id, []))
        variants_with_links = sum(
            1
            for variant_id in variant_ids
            if bool(_dedupe_keep_order(source_links_by_variant.get(variant_id, [])))
        )
        families.append(
            {
                "retailer": retailer,
                "category_key": category_key,
                "parent_product_id": parent_id,
                "pdp_url": parent["pdp_url"],
                "brand_raw": parent["brand_raw"],
                "title_raw": parent["title_raw"],
                "title_normalized": parent["title_normalized"],
                "category_keys": parent["category_keys"],
                "variant_count": len(variant_ids),
                "variants_with_source_links_count": variants_with_links,
                "source_link_count": len(family_links),
                "variant_ids": variant_ids,
                "source_links": family_links,
                "generated_at": generated_at,
            }
        )

    variant_rows: list[dict[str, Any]] = []
    for variant in variants:
        variant_id = variant["variant_id"]
        links_for_variant = _dedupe_keep_order(
            source_links_by_variant.get(variant_id, [])
        )
        variant_rows.append(
            {
                "retailer": retailer,
                "category_key": category_key,
                "parent_product_id": variant["parent_product_id"],
                "variant_id": variant_id,
                "canonical_url": f"https://www.amazon.com/dp/{variant_id}",
                "shade_name_raw": variant["shade_name_raw"],
                "size_text_raw": variant["size_text_raw"],
                "availability": variant["availability"],
                "price_raw": variant["price_raw"],
                "price": variant["price"],
                "currency": variant["currency"],
                "hero_image_url": variant["hero_image_url"],
                "swatch_image_url": variant["swatch_image_url"],
                "source_index": variant["source_index"],
                "source_link_count": len(links_for_variant),
                "source_links": links_for_variant,
                "generated_at": generated_at,
            }
        )

    families_with_links = sum(1 for row in families if row["source_link_count"] > 0)
    variants_with_links = sum(1 for row in variant_rows if row["source_link_count"] > 0)
    summary = {
        "retailer": retailer,
        "category_key": category_key,
        "links_total": len(list(links)),
        "links_unique": len(unique_links),
        "links_with_asin": len(unique_links) - len(links_without_asin),
        "links_without_asin": len(links_without_asin),
        "unique_asins_from_links": len(asin_to_links),
        "matched_asin_count": matched_asin_count,
        "unmatched_asin_count": len(unmatched_asins),
        "unmatched_asin_examples": sorted(unmatched_asins)[:20],
        "parents_total": len(parents),
        "families_total": len(families),
        "families_with_source_links": families_with_links,
        "variants_total": len(variant_rows),
        "variants_with_source_links": variants_with_links,
        "families_without_source_links_examples": [
            row["parent_product_id"]
            for row in families
            if row["source_link_count"] == 0
        ][:20],
        "variants_without_source_links_examples": [
            row["variant_id"] for row in variant_rows if row["source_link_count"] == 0
        ][:20],
        "generated_at": generated_at,
    }

    return CategoryAggregation(
        families=families, variants=variant_rows, summary=summary
    )


def _ensure_aggregation_tables(conn: Any) -> None:
    conn.execute(FAMILIES_TABLE_SQL)
    conn.execute(VARIANTS_TABLE_SQL)
    conn.execute(RUNS_TABLE_SQL)


def _persist_category_to_store(
    conn: Any,
    *,
    retailer: str,
    category_key: str,
    aggregation: CategoryAggregation,
) -> None:
    _ensure_aggregation_tables(conn)
    conn.execute(
        "DELETE FROM product_families WHERE retailer = ? AND category_key = ?",
        (retailer, category_key),
    )
    conn.execute(
        "DELETE FROM product_variants WHERE retailer = ? AND category_key = ?",
        (retailer, category_key),
    )

    family_rows = [
        (
            retailer,
            category_key,
            record["parent_product_id"],
            int(record["variant_count"]),
            int(record["source_link_count"]),
            str(record["generated_at"]),
            json.dumps(record, ensure_ascii=False),
        )
        for record in aggregation.families
    ]
    variant_rows = [
        (
            retailer,
            category_key,
            record["variant_id"],
            record["parent_product_id"],
            int(record["source_link_count"]),
            str(record["generated_at"]),
            json.dumps(record, ensure_ascii=False),
        )
        for record in aggregation.variants
    ]

    if family_rows:
        conn.executemany(
            """
            INSERT INTO product_families (
                retailer,
                category_key,
                parent_product_id,
                variant_count,
                source_link_count,
                generated_at,
                payload_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            family_rows,
        )
    if variant_rows:
        conn.executemany(
            """
            INSERT INTO product_variants (
                retailer,
                category_key,
                variant_id,
                parent_product_id,
                source_link_count,
                generated_at,
                payload_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            variant_rows,
        )
    conn.execute(
        """
        INSERT INTO product_aggregation_runs (
            retailer,
            category_key,
            generated_at,
            summary_json
        ) VALUES (?, ?, ?, ?)
        """,
        (
            retailer,
            category_key,
            str(aggregation.summary["generated_at"]),
            json.dumps(aggregation.summary, ensure_ascii=False),
        ),
    )
    conn.commit()


def _write_category_outputs(
    output_dir: Path,
    *,
    retailer: str,
    category_key: str,
    aggregation: CategoryAggregation,
) -> tuple[Path, Path, Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    base = f"{retailer}_{category_key}"
    families_path = output_dir / f"{base}_product_families.json"
    variants_path = output_dir / f"{base}_product_variants.json"
    summary_path = output_dir / f"{base}_aggregation_summary.json"

    families_path.write_text(
        json.dumps(aggregation.families, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    variants_path.write_text(
        json.dumps(aggregation.variants, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    summary_path.write_text(
        json.dumps(aggregation.summary, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return families_path, variants_path, summary_path


def main(argv: Sequence[str] | None = None) -> int:
    args = _parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    load_env_from_secrets_file()

    retailer = str(args.retailer or "").strip().lower()
    if not retailer:
        raise ValueError("Retailer must be non-empty.")

    pdp_store_path = (
        args.pdp_store_path
        if args.pdp_store_path is not None
        else enforce_default_pdp_store_path(DEFAULT_PDP_STORE_PATH)
    )
    links_payload = _load_links_payload(args.links_path)
    categories = _resolve_categories(links_payload, retailer, args.category)
    if not categories:
        LOGGER.info("No categories to aggregate for retailer=%s", retailer)
        return 0

    generated_at = dt.datetime.now(dt.timezone.utc).isoformat()
    LOGGER.info(
        "Aggregating retailer=%s categories=%s pdp_store_path=%s",
        retailer,
        categories,
        pdp_store_path,
    )

    with connect_pdp_database(pdp_store_path) as conn:
        conn.row_factory = DICT_ROW_FACTORY
        for category_key in categories:
            raw_links, unique_links = _category_links(
                links_payload, retailer, category_key
            )
            aggregation = aggregate_category(
                conn,
                retailer=retailer,
                category_key=category_key,
                links=raw_links,
                generated_at=generated_at,
            )
            families_path, variants_path, summary_path = _write_category_outputs(
                args.output_dir,
                retailer=retailer,
                category_key=category_key,
                aggregation=aggregation,
            )
            if not args.skip_pdp_store_write:
                _persist_category_to_store(
                    conn,
                    retailer=retailer,
                    category_key=category_key,
                    aggregation=aggregation,
                )

            LOGGER.info(
                "Category=%s complete | links=%d unique_links=%d families=%d variants=%d "
                "families_with_links=%d variants_with_links=%d | outputs=%s %s %s",
                category_key,
                len(raw_links),
                len(unique_links),
                aggregation.summary["families_total"],
                aggregation.summary["variants_total"],
                aggregation.summary["families_with_source_links"],
                aggregation.summary["variants_with_source_links"],
                families_path,
                variants_path,
                summary_path,
            )

    return 0


if __name__ == "__main__":
    raise SystemExit(main())


__all__ = [
    "CategoryAggregation",
    "aggregate_category",
    "main",
]
