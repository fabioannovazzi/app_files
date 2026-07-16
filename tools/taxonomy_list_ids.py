#!/usr/bin/env python3
from __future__ import annotations

"""List taxonomy IDs quickly (category → attribute → leaves).

Usage
-----
- All categories:
    python tools/taxonomy_list_ids.py

- One category (e.g., lipstick):
    python tools/taxonomy_list_ids.py lipstick

Shows attribute IDs and leaf node IDs you need for patches.
"""

import sys
from typing import Any, Dict

from modules.add_attributes.attribute_taxonomy import get_attribute_taxonomy


def _print_branch(branch: Dict[str, Any]) -> None:
    cid = branch.get("id", "?")
    clab = branch.get("label", cid)
    print(f"Category: {cid} ({clab})")
    for a in branch.get("attributes", []) or []:
        aid = a.get("id", "?")
        alab = a.get("label", aid)
        print(f"  Attribute: {aid} ({alab})")
        for n in a.get("nodes", []) or []:
            ch = n.get("children")
            if ch:
                for c in ch:
                    nid = c.get("id", "?")
                    nlab = c.get("label", nid)
                    print(f"    Leaf: {nid} ({nlab})")
            else:
                nid = n.get("id", "?")
                nlab = n.get("label", nid)
                print(f"    Leaf: {nid} ({nlab})")


def main() -> int:
    taxonomy = get_attribute_taxonomy()
    cats = taxonomy.get("categories", []) or []
    if len(sys.argv) > 1:
        key = sys.argv[1].strip().lower()
        for c in cats:
            if str(c.get("id", "")).strip().lower() == key:
                _print_branch(c)
                return 0
        print(f"Category '{key}' not found.")
        return 1
    else:
        for c in cats:
            _print_branch(c)
        return 0


if __name__ == "__main__":
    raise SystemExit(main())

