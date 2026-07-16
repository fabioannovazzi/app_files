from __future__ import annotations

"""
Set selection (single|multi) for specific attributes across the taxonomy.

Usage examples
--------------

1) Mark attributes as single-select globally:
   python tools/taxonomy_set_selection.py --attrs skin_type finish shade_family use_areas --mode single

2) Restrict to specific categories (by id or label, case-insensitive):
   python tools/taxonomy_set_selection.py --attrs finish --mode single --categories makeup foundation

Notes
-----
- This script edits attribute metadata only: selection, hierarchical, levels.
- For single-select, it enforces hierarchical=False and levels=1.
- It does not touch nodes, labels or synonyms.
- Re-run your attribute classification after changing selection (delete or repoint the cache root).
"""

import argparse
from typing import Iterable, List, Set

from modules.add_attributes.attribute_taxonomy import (
    get_attribute_taxonomy,
    save_attribute_taxonomy,
)


def _norm(s: str | None) -> str:
    return str(s or "").strip().lower()


def set_selection(
    *,
    attrs: Iterable[str],
    mode: str,
    categories: Iterable[str] | None = None,
) -> int:
    attr_targets: Set[str] = {_norm(a) for a in attrs}
    cat_targets: Set[str] | None = {_norm(c) for c in categories} if categories else None
    tax = get_attribute_taxonomy()
    changed = 0
    cats = tax.get("categories", []) or []
    for c in cats:
        cid = _norm(c.get("id"))
        clab = _norm(c.get("label"))
        if cat_targets and (cid not in cat_targets and clab not in cat_targets):
            continue
        for a in c.get("attributes", []) or []:
            aid = _norm(a.get("id"))
            alab = _norm(a.get("label"))
            if aid in attr_targets or alab in attr_targets:
                sel = "single" if mode == "single" else "multi"
                if a.get("selection") != sel or a.get("hierarchical") or a.get("levels") != 1:
                    a["selection"] = sel
                    if mode == "single":
                        a["hierarchical"] = False
                        a["levels"] = 1
                    changed += 1
    if changed:
        save_attribute_taxonomy(tax)
    return changed


def main(argv: List[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--attrs", nargs="+", required=True, help="Attribute ids or labels to modify (case-insensitive)")
    ap.add_argument(
        "--mode",
        choices=["single", "multi"],
        default="single",
        help="Set selection to single or multi (default: single)",
    )
    ap.add_argument(
        "--categories",
        nargs="*",
        default=None,
        help="Optional category ids or labels to restrict changes to",
    )
    args = ap.parse_args(argv)
    changed = set_selection(attrs=args.attrs, mode=args.mode, categories=args.categories)
    print(f"Updated {changed} attribute entries.")
    if changed == 0:
        print("No matching attributes found. Check names or category restrictions.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

