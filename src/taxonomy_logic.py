"""Taxonomy helpers."""

from __future__ import annotations

from typing import Any, Dict, List

from modules.add_attributes.add_attributes import process_taxonomy_review_queue
from modules.add_attributes.attribute_taxonomy import (
    get_attribute_taxonomy,
    load_taxonomy_review_queue,
    remove_taxonomy_review_entry,
)

__all__ = [
    "flatten_taxonomy",
    "get_pending_taxonomy_reviews",
    "approve_pending_taxonomy_value",
    "reject_pending_taxonomy_value",
]


def _collect_leaf_paths(
    nodes: List[Dict[str, Any]], path: List[str]
) -> List[List[str]]:
    """Return all leaf node paths under ``nodes``."""
    paths: List[List[str]] = []
    for node in nodes or []:
        label = str(node.get("label", "")).lower()
        children = node.get("children")
        if children:
            paths.extend(_collect_leaf_paths(children, path + [label]))
        else:
            paths.append(path + [label])
    return paths


def flatten_taxonomy(query: str | None = None) -> List[Dict[str, str]]:
    """Return flattened taxonomy terms optionally filtered by ``query``."""
    taxonomy = get_attribute_taxonomy()
    result: List[Dict[str, str]] = []
    query_lower = query.lower() if query else None

    for category in taxonomy.get("categories", []):
        cat_label = str(category.get("label", "")).lower()
        for attr in category.get("attributes", []):
            attr_label = str(attr.get("label", "")).lower()
            for path in _collect_leaf_paths(attr.get("nodes", []), []):
                term = path[-1]
                row = {
                    "category": cat_label,
                    "attribute": attr_label,
                    "term": term,
                    "path": " > ".join(path),
                }
                if query_lower:
                    haystack = " ".join([cat_label, attr_label] + path).lower()
                    if query_lower in haystack:
                        result.append(row)
                else:
                    result.append(row)
    return result


def get_pending_taxonomy_reviews() -> List[Dict[str, Any]]:
    """Return queued attribute values awaiting approval."""

    return load_taxonomy_review_queue()


def approve_pending_taxonomy_value(llm_wrapper, entry: Dict[str, Any]) -> None:
    """Validate and persist ``entry`` into the taxonomy."""

    process_taxonomy_review_queue(llm_wrapper, [entry])


def reject_pending_taxonomy_value(entry: Dict[str, Any]) -> None:
    """Discard ``entry`` from the review queue."""

    remove_taxonomy_review_entry(entry)
