"""Exact product namespaces shared by reporting, receipts and recovery."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Literal, cast

__all__ = ["Product", "PRODUCTS", "product_name", "catalog_metadata"]

Product = Literal["vera", "clara", "lucia"]
PRODUCTS: tuple[Product, ...] = ("vera", "clara", "lucia")


def product_name(value: str) -> Product:
    """Fixed namespaces enforce ownership and prevent caller-selected file paths."""
    if value not in PRODUCTS:
        raise ValueError("Unknown reporting product")
    return cast(Product, value)


def catalog_metadata(product: Product = "vera") -> dict[str, Any]:
    """Read the authored process inventory; this never classifies user intent."""
    name = product_name(product)
    path = (
        Path(__file__).resolve().parents[2] / "plugins" / name / "usage/pipelines.json"
    )
    return json.loads(path.read_text(encoding="utf-8"))
