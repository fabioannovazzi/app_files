from __future__ import annotations

"""Alias index mapping for taxonomy leaves.

The alias index maps observed raw terms (aliases) to canonical leaf labels
per attribute, enabling deterministic pre-classification before LLM calls.

Persistence: ``<project-root>/caches/alias_index.json``. Structure (lowercased keys):
{
  "categories": {
    "<category_id>": {
      "attributes": {
        "<attribute_label>": { "aliases": { "alias": "leaf_label" } }
      }
    }
  }
}
"""

import json
import logging
from typing import Any, Dict, Iterable, List, Tuple

from rapidfuzz import fuzz

from modules.utilities.cache import get_cache_path


ALIAS_INDEX_PATH = get_cache_path("alias_index.json")
logger = logging.getLogger(__name__)

__all__ = [
    "load_alias_index",
    "save_alias_index",
    "build_alias_index_from_novelty",
    "merge_aliases",
]


def _norm(s: str) -> str:
    return " ".join(str(s).lower().replace("-", " ").split())


def load_alias_index() -> Dict[str, Any]:
    if ALIAS_INDEX_PATH.exists():
        try:
            return json.loads(ALIAS_INDEX_PATH.read_text(encoding="utf-8"))
        except Exception:
            logger.exception("Failed to load alias index JSON: %s", ALIAS_INDEX_PATH)
    return {"categories": {}}


def save_alias_index(data: Dict[str, Any]) -> None:
    data = data or {"categories": {}}
    try:
        ALIAS_INDEX_PATH.parent.mkdir(parents=True, exist_ok=True)
        ALIAS_INDEX_PATH.write_text(
            json.dumps(data, indent=2, sort_keys=True), encoding="utf-8"
        )
    except OSError:
        logger.exception("Failed to write alias index JSON: %s", ALIAS_INDEX_PATH)


def _leaf_catalog_for_attr(attr_info: Dict[str, Any]) -> List[Tuple[str, str]]:
    """Return list of (leaf_label_lower, node_id) for an attribute."""
    out: List[Tuple[str, str]] = []
    for n in attr_info.get("nodes", []) or []:
        ch = n.get("children")
        if ch:
            for c in ch:
                lab = str(c.get("label", "")).strip().lower()
                nid = str(c.get("id", lab))
                if lab:
                    out.append((lab, nid))
        else:
            lab = str(n.get("label", "")).strip().lower()
            nid = str(n.get("id", lab))
            if lab:
                out.append((lab, nid))
    return out


def _best_leaf_match(
    leafs: List[Tuple[str, str]], alias: str, threshold: int
) -> Tuple[str | None, str | None]:
    """Return (leaf_label, node_id) if best fuzzy match >= threshold, else (None, None)."""
    best = (None, None, -1)
    a = _norm(alias)
    for lab, nid in leafs:
        score = fuzz.token_set_ratio(a, lab)
        if score > best[2]:
            best = (lab, nid, score)
    return (best[0], best[1]) if best[2] >= threshold else (None, None)


def build_alias_index_from_novelty(
    taxonomy: Dict[str, Any],
    *,
    min_count: int = 3,
    sim_threshold: int = 88,
) -> Dict[str, Any]:
    """Build alias index from observed inputs aligned to nearest leaf.

    Only includes aliases that meet min_count and match an existing leaf
    above sim_threshold. Does not create new nodes.
    """
    from .novelty import load_novelty  # type: ignore
    df = load_novelty()
    out = {"categories": {}}
    if df.is_empty():
        return out
    cats = {
        str(c.get("id", "")).strip().lower(): c for c in taxonomy.get("categories", [])
    }
    # group by category/attribute/raw_value
    grp = (
        df.group_by(["category", "attribute", "raw_value"])
        .len()
        .rename({"len": "count"})
    )
    grp = grp.filter(grp["count"] >= min_count)
    if grp.is_empty():
        return out
    for row in grp.iter_rows(named=True):
        cat = str(row["category"]).strip().lower()
        attr_label = str(row["attribute"]).strip().lower()
        raw = str(row["raw_value"]).strip()
        if not cat or not attr_label or not raw:
            continue
        if cat not in cats:
            continue
        # find attribute node by label
        attr_info = None
        for a in cats[cat].get("attributes", []):
            lab = str(a.get("label", "")).strip().lower()
            if lab == attr_label:
                attr_info = a
                break
        if not attr_info:
            continue
        # skip numeric-like attributes (e.g., spf)
        if attr_label == "spf" or str(attr_info.get("id", "")).strip().lower() == "spf":
            continue
        leafs = _leaf_catalog_for_attr(attr_info)
        leaf_label, node_id = _best_leaf_match(leafs, raw, sim_threshold)
        if not leaf_label:
            continue
        cat_bucket = out["categories"].setdefault(cat, {"attributes": {}})
        attr_bucket = cat_bucket["attributes"].setdefault(attr_label, {"aliases": {}})
        attr_bucket["aliases"][_norm(raw)] = leaf_label
    return out


def merge_aliases(base: Dict[str, Any], update: Dict[str, Any]) -> Dict[str, Any]:
    """Deep-merge alias index dicts with last-write-wins for aliases."""
    out = {"categories": {}}
    out["categories"].update(base.get("categories", {}))
    for cat, cdata in update.get("categories", {}).items():
        bucket = out["categories"].setdefault(cat, {"attributes": {}})
        for attr, adata in cdata.get("attributes", {}).items():
            ab = bucket["attributes"].setdefault(attr, {"aliases": {}})
            ab["aliases"].update(adata.get("aliases", {}))
    return out
