from __future__ import annotations

"""Safe application of additions-only taxonomy patches.

Supported patch keys (all optional):
- add_synonyms: [{attribute_id, node_id, synonym}]
- add_nodes: [{attribute_id, id, label, parent_id?}]

Notes
- Synonyms are appended only to leaf nodes; attempts to target parents are ignored.
- Duplicate synonyms (case-insensitive) are ignored.
- After patching a category branch, the result is normalized and validated via
  taxonomy_schema; budgets and collisions are enforced. On validation error,
  no changes are persisted and the function returns False.
"""

from typing import Any, Dict
import logging

from .attribute_taxonomy import (
    get_attribute_taxonomy,
    save_attribute_taxonomy,
)
from .taxonomy_schema import validate_branch

logger = logging.getLogger(__name__)

__all__ = [
    "apply_taxonomy_patch",
    "set_all_attributes_selection",
    "set_all_categories_selection",
    "normalize_all_categories",
]


def _append_synonym_to_leaf(attr: Dict[str, Any], node_id: str, synonym: str) -> bool:
    syn = str(synonym).strip()
    if not syn:
        return False
    # try top-level leaves first
    for n in attr.get("nodes", []) or []:
        if not n.get("children") and str(n.get("id")) == node_id:
            syns = [str(s).lower() for s in (n.get("synonyms") or [])]
            sval = syn.lower()
            if sval in syns or sval == str(n.get("label", "")).strip().lower():
                return False
            n.setdefault("synonyms", []).append(syn)
            return True
        # check children leaves
        for ch in (n.get("children") or []):
            if str(ch.get("id")) == node_id:
                syns = [str(s).lower() for s in (ch.get("synonyms") or [])]
                sval = syn.lower()
                if sval in syns or sval == str(ch.get("label", "")).strip().lower():
                    return False
                ch.setdefault("synonyms", []).append(syn)
                return True
    return False


def _append_node(attr: Dict[str, Any], node: Dict[str, Any], parent_id: str | None) -> bool:
    n_id = str(node.get("id", "")).strip()
    n_lab = str(node.get("label", "")).strip() or n_id
    if not n_id:
        return False
    if parent_id:
        # find parent and ensure it's a parent node
        for top in attr.get("nodes", []) or []:
            if str(top.get("id")) == parent_id:
                top.setdefault("children", []).append({"id": n_id, "label": n_lab})
                return True
        return False
    # append at top-level
    attr.setdefault("nodes", []).append({"id": n_id, "label": n_lab})
    return True


def apply_taxonomy_patch(
    category_id: str,
    patch: Dict[str, Any],
) -> bool:
    """Apply an additions-only patch to the branch for ``category_id`` and persist.

    Returns True on success, False if validation fails or category not found.
    """
    taxonomy = get_attribute_taxonomy()
    cat_key = str(category_id).strip().lower()
    categories = taxonomy.get("categories", [])
    idx = None
    for i, c in enumerate(categories):
        if str(c.get("id", "")).strip().lower() == cat_key:
            idx = i
            break
    if idx is None:
        return False
    branch = categories[idx]
    attrs_by_id = {str(a.get("id")): a for a in branch.get("attributes", [])}

    # apply add_nodes first (they can be targets for add_synonyms)
    for n in (patch.get("add_nodes") or []):
        try:
            attr_id = str(n.get("attribute_id"))
            node = {"id": n["id"], "label": n.get("label", n["id"]) }
        except Exception as e:
            logger.exception("Invalid add_node entry: %r", n)
            continue
        parent_id = n.get("parent_id")
        attr = attrs_by_id.get(attr_id)
        if not attr:
            continue
        _append_node(attr, node, parent_id)

    for s in (patch.get("add_synonyms") or []):
        try:
            attr_id = str(s.get("attribute_id"))
            node_id = str(s.get("node_id"))
            syn = s.get("synonym")
        except Exception as e:
            logger.exception("Invalid add_synonym entry: %r", s)
            continue
        if not syn or not node_id:
            continue
        attr = attrs_by_id.get(attr_id)
        if not attr:
            continue
        _append_synonym_to_leaf(attr, node_id, syn)

    # Update attribute metadata if requested
    for u in (patch.get("update_attributes") or []):
        try:
            attr_id = str(u.get("attribute_id"))
        except Exception as e:
            logger.exception("Invalid update_attributes entry: %r", u)
            continue
        attr = attrs_by_id.get(attr_id)
        if not attr:
            continue
        if "selection" in u and u.get("selection") in ("single", "multi"):
            attr["selection"] = u.get("selection")
        if "scope" in u and u.get("scope") in ("product", "variant"):
            attr["scope"] = u.get("scope")
        if "kind" in u and u.get("kind") in ("composition", "performance", "regulatory"):
            attr["kind"] = u.get("kind")

    # Validate updated branch (normalizes, enforces budgets)
    normalized, _ = validate_branch(branch)
    categories[idx] = normalized
    save_attribute_taxonomy(taxonomy)
    return True

def set_all_attributes_selection(category_id: str, selection: str = "single") -> bool:
    """Set ``selection`` for all attributes under ``category_id`` and persist.

    Returns True if any attribute was updated, False if the category was not found
    or no changes were necessary.
    """
    taxonomy = get_attribute_taxonomy()
    cat_key = str(category_id).strip().lower()
    categories = taxonomy.get("categories", [])
    idx = None
    for i, c in enumerate(categories):
        if str(c.get("id", "")).strip().lower() == cat_key:
            idx = i
            break
    if idx is None:
        return False
    branch = categories[idx]
    changed = False
    for attr in branch.get("attributes", []) or []:
        current = str(attr.get("selection", "single") or "single").strip().lower()
        if current != selection:
            attr["selection"] = selection
            changed = True
    if not changed:
        return False
    # Validate and persist
    normalized, _ = validate_branch(branch)
    categories[idx] = normalized
    save_attribute_taxonomy(taxonomy)
    return True

def set_all_categories_selection(selection: str = "single") -> bool:
    """Set ``selection`` for all attributes in all categories and persist once.

    Returns True if any attribute was updated, False otherwise.
    """
    taxonomy = get_attribute_taxonomy()
    categories = taxonomy.get("categories", []) or []
    changed = False
    new_categories = []
    for branch in categories:
        if not isinstance(branch, dict):
            new_categories.append(branch)
            continue
        local_changed = False
        for attr in branch.get("attributes", []) or []:
            current = str(attr.get("selection", "single") or "single").strip().lower()
            if current != selection:
                attr["selection"] = selection
                local_changed = True
        if local_changed:
            try:
                normalized, _ = validate_branch(branch)
            except Exception:
                normalized = branch
            new_categories.append(normalized)
            changed = True
        else:
            new_categories.append(branch)
    if not changed:
        return False
    taxonomy["categories"] = new_categories
    save_attribute_taxonomy(taxonomy)
    return True

def normalize_all_categories() -> dict:
    """Normalize every category branch and persist changes once.

    Returns a summary dict: { 'normalized': N, 'unchanged': M }.
    """
    taxonomy = get_attribute_taxonomy()
    cats = taxonomy.get("categories", []) or []
    normalized_count = 0
    unchanged = 0
    out: list[dict] = []
    for c in cats:
        if not isinstance(c, dict):
            out.append(c)
            unchanged += 1
            continue
        try:
            norm, warns = validate_branch(c)
        except Exception:
            # If validation fails, keep the original to avoid destructive edits
            out.append(c)
            unchanged += 1
        else:
            if norm != c:
                normalized_count += 1
            else:
                unchanged += 1
            out.append(norm)
            try:
                cid = str((c.get("id") or c.get("label") or "")).strip()
                if warns:
                    logger = logging.getLogger(__name__)
                    logger.info(
                        "normalize: category '%s' warnings: %s", cid, "; ".join(warns)
                    )
            except Exception:
                pass
    taxonomy["categories"] = out
    # Persist even if unchanged for determinism; the writer is atomic
    save_attribute_taxonomy(taxonomy)
    return {"normalized": normalized_count, "unchanged": unchanged}

def normalize_category(category_id: str) -> Dict[str, Any] | None:
    """Normalize and persist a single category branch.

    Returns a summary dict with metrics before/after and any validation warnings,
    or ``None`` if the category was not found.
    """
    from .attribute_taxonomy import get_attribute_taxonomy, save_attribute_taxonomy
    from .taxonomy_schema import branch_metrics

    taxonomy = get_attribute_taxonomy()
    cats = taxonomy.get("categories", [])
    key = str(category_id).strip().lower()
    for i, c in enumerate(cats):
        if str(c.get("id", "")).strip().lower() == key:
            before = branch_metrics(c)
            normalized, warnings = validate_branch(c)
            after = branch_metrics(normalized)
            cats[i] = normalized
            save_attribute_taxonomy(taxonomy)
            return {
                "id": normalized.get("id", key),
                "warnings": warnings,
                "before": before,
                "after": after,
            }
    return None

# expose helper in public API
__all__.append("normalize_category")
