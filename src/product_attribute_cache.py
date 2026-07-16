from __future__ import annotations

import contextlib
import copy
import json
import logging
import os
import threading
import time
from pathlib import Path
from typing import Any, Dict, Iterable, List, MutableMapping, TypedDict

from modules.add_attributes.normalization import normalize_product_key
from modules.utilities.cache import get_cache_dir
from src.file_lock import FileLock

logger = logging.getLogger(__name__)


class CacheRecord(TypedDict):
    category: str
    brand: str
    product: str
    attributes: Dict[str, str]


def _get_cache_dir() -> Path:
    """Return a writable directory for caching product attributes.

    Uses the shared project cache root via
    modules.utilities.cache.get_cache_dir("product_attribute_cache").
    """
    return get_cache_dir("product_attribute_cache")


_CACHE_DIR = _get_cache_dir()
CACHE_FILE = _CACHE_DIR / "product_attributes.json"

__all__ = ["load_cache", "save_cache"]

_CACHE_LOCK = threading.Lock()


def _normalize_key(text: str | None) -> str:
    if text is None:
        return ""
    t = str(text).strip().lower()
    return t


def _mapping_to_records(
    mapping: MutableMapping[str, MutableMapping[str, Any]]
) -> List[CacheRecord]:
    """Convert nested in-memory mapping to flat records for on-disk JSON.

    Supported in-memory shapes:
    - {category -> product -> attributes} (no brand available)
    - {category -> brand -> product -> attributes}
    """
    records: List[CacheRecord] = []
    for category, products_or_brands in (mapping or {}).items():
        if not isinstance(products_or_brands, dict):
            continue
        # Detect shape: either {product -> attrs} or {brand -> {product -> attrs}}
        if products_or_brands and all(
            isinstance(v, dict) and (
                # product -> attrs (leaf dict values are str-ish)
                any(isinstance(lv, (str, int, float)) for lv in v.values())
            )
            for v in products_or_brands.values()
        ):
            # Treat as brandless: brand=""
            for product, attrs in products_or_brands.items():
                if not isinstance(attrs, dict):
                    continue
                records.append(
                    CacheRecord(
                        category=str(category),
                        brand="",
                        product=str(product),
                        attributes={str(k): str(v) for k, v in (attrs or {}).items()},
                    )
                )
        else:
            # Assume {brand -> {product -> attrs}}
            for brand, products in products_or_brands.items():
                if not isinstance(products, dict):
                    continue
                for product, attrs in products.items():
                    if not isinstance(attrs, dict):
                        continue
                    records.append(
                        CacheRecord(
                            category=str(category),
                            brand=str(brand),
                            product=str(product),
                            attributes={str(k): str(v) for k, v in (attrs or {}).items()},
                        )
                    )
    return records


def _records_to_mapping(records: Iterable[CacheRecord]) -> Dict[str, Dict[str, Dict[str, Dict[str, str]]]]:
    """Convert flat records from disk to the nested in-memory mapping.

    Produces: {category -> brand -> product -> attributes} with lowercase keys
    for deterministic lookups. Brand may be an empty string when unknown.
    """
    out: Dict[str, Dict[str, Dict[str, Dict[str, str]]]] = {}
    for rec in records or []:
        category = _normalize_key(rec.get("category"))
        brand = _normalize_key(rec.get("brand"))
        product = normalize_product_key(rec.get("product"))
        cat_bucket = out.setdefault(category, {})
        brand_bucket = cat_bucket.setdefault(brand, {})
        brand_bucket[product] = {
            str(k): str(v) for k, v in (rec.get("attributes") or {}).items()
        }
    return out


def load_cache() -> Dict[str, Dict[str, Dict[str, Dict[str, str]]]]:
    """Return the product attribute cache as a nested mapping.

    On disk the cache is a single JSON file containing a list of records with
    explicit "category", "brand", "product", and "attributes" fields.
    For backward compatibility, if the file contains a dict in the old nested
    format, it is returned as-is (with normalized lowercase keys).
    """
    return _load_cache_file(CACHE_FILE)


def _load_cache_file(path: Path) -> Dict[str, Dict[str, Dict[str, Dict[str, str]]]]:
    if not path.exists():
        return {}

    text = path.read_text(encoding="utf-8")
    data = json.loads(text)

    if isinstance(data, list):
        # New schema: list of records
        return _records_to_mapping(data)  # type: ignore[arg-type]
    if isinstance(data, dict):
        # Backward-compat: treat as {category -> product -> attrs} (brandless)
        out: Dict[str, Dict[str, Dict[str, Dict[str, str]]]] = {}
        for cat, products in data.items():
            cat_key = _normalize_key(cat)
            brand_bucket = out.setdefault(cat_key, {}).setdefault("", {})
            if isinstance(products, dict):
                for product, attrs in products.items():
                    brand_bucket[normalize_product_key(product)] = {
                        str(ka): str(va) for ka, va in (attrs or {}).items()
                    }
        return out
    raise ValueError("Invalid cache JSON structure: expected list or dict")


def save_cache(
    mapping: MutableMapping[str, MutableMapping[str, MutableMapping[str, str]]],
) -> None:
    """Atomically persist the full cache mapping to disk using the flat schema.

    The on-disk file is a JSON array of objects with keys:
    "category", "brand", "product", and "attributes".
    """
    normalized = _normalize_mapping(mapping)
    with _CACHE_LOCK:
        with FileLock(CACHE_FILE):
            existing = _load_cache_file(CACHE_FILE)
            merged = _merge_cache(existing, normalized)
            _write_cache_file(merged)


def _write_cache_file(
    cache: MutableMapping[str, MutableMapping[str, MutableMapping[str, str]]]
) -> None:
    records = _mapping_to_records(cache)
    CACHE_FILE.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = CACHE_FILE.with_suffix(CACHE_FILE.suffix + ".tmp")
    data = json.dumps(records, ensure_ascii=False, indent=2)
    with tmp_path.open("w", encoding="utf-8") as fh:
        fh.write(data)
        fh.flush()
        with contextlib.suppress(OSError):
            os.fsync(fh.fileno())
    for attempt in range(5):
        try:
            tmp_path.replace(CACHE_FILE)
            return
        except PermissionError:
            if attempt == 4:
                raise
            time.sleep(0.1 * (attempt + 1))


def _normalize_mapping(
    mapping: MutableMapping[str, MutableMapping[str, MutableMapping[str, str]]]
) -> Dict[str, Dict[str, Dict[str, Dict[str, str]]]]:
    normalized: Dict[str, Dict[str, Dict[str, Dict[str, str]]]] = {}
    for category, brand_map in (mapping or {}).items():
        if not isinstance(brand_map, dict):
            continue
        cat_key = _normalize_key(category)
        cat_bucket = normalized.setdefault(cat_key, {})
        for brand, product_map in brand_map.items():
            if not isinstance(product_map, dict):
                continue
            brand_key = _normalize_key(brand)
            brand_bucket = cat_bucket.setdefault(brand_key, {})
            for product, attrs in product_map.items():
                if not isinstance(attrs, dict):
                    continue
                prod_key = normalize_product_key(product)
                attr_dict = brand_bucket.setdefault(prod_key, {})
                for k, v in attrs.items():
                    if v is None:
                        continue
                    attr_dict[str(k)] = str(v)
    return normalized


def _merge_cache(
    base: Dict[str, Dict[str, Dict[str, Dict[str, str]]]],
    updates: Dict[str, Dict[str, Dict[str, Dict[str, str]]]],
) -> Dict[str, Dict[str, Dict[str, Dict[str, str]]]]:
    merged = copy.deepcopy(base)
    for cat, brands in updates.items():
        cat_bucket = merged.setdefault(cat, {})
        for brand, products in brands.items():
            brand_bucket = cat_bucket.setdefault(brand, {})
            for product, attrs in products.items():
                prod_bucket = brand_bucket.setdefault(product, {})
                prod_bucket.update(attrs)
    return merged
