#!/usr/bin/env python3
from __future__ import annotations

"""Apply taxonomy patches from CLI (add/remove synonyms or nodes).

Examples (fast path)
--------
1) Remove a weak synonym, then add a better one (your example):

    python tools/taxonomy_apply_patch.py \
        --category lipstick \
        --remove-syn finish:semi_matte:no-shine \
        --add-syn finish:semi_matte:"soft matte"

Or, if you prefer using names (labels) instead of IDs:

    python tools/taxonomy_apply_patch.py \
        --category lipstick \
        --remove-syn-label "Finish:Semi-matte:no-shine" \
        --add-syn-label "Finish:Semi-matte:soft matte"

2) Apply a JSON patch file (supports add_synonyms/add_nodes/update_attributes
   and remove_synonyms/remove_nodes):

    python tools/taxonomy_apply_patch.py --category lipstick --patch-file patch.json

Patch file shape
----------------
{
  "add_synonyms": [
    {"attribute_id": "finish", "node_id": "semi_matte", "synonym": "soft matte"}
  ],
  "remove_synonyms": [
    {"attribute_id": "finish", "node_id": "semi_matte", "synonym": "no-shine"}
  ]
}
"""

import argparse
import json
import sys
from typing import Any, Dict, List, Tuple

from modules.add_attributes.attribute_taxonomy import (
    get_attribute_taxonomy,
    save_attribute_taxonomy,
)
from modules.add_attributes.grounding import apply_grounding_patch
from modules.add_attributes.taxonomy_patch import apply_taxonomy_patch


def _load_patch_from_file(path: str) -> Dict[str, Any]:
    with open(path, "r", encoding="utf-8") as fh:
        data = json.load(fh)
    if not isinstance(data, dict):
        raise ValueError("Patch file must contain a JSON object")
    return data


def _parse_triplets(values: List[str], kind: str) -> List[Dict[str, str]]:
    out: List[Dict[str, str]] = []
    for v in values or []:
        try:
            attr_id, node_id, token = v.split(":", 2)
        except ValueError:
            raise SystemExit(
                f"Invalid {kind} triplet '{v}'. Expected 'attribute_id:node_id:value'"
            )
        item = {"attribute_id": attr_id.strip(), "node_id": node_id.strip()}
        key = "synonym" if kind.endswith("syn") else "id"
        item[key] = token.strip()
        out.append(item)
    return out


def _find_branch(taxonomy: Dict[str, Any], category_id: str) -> Dict[str, Any] | None:
    key = category_id.strip().lower()
    for c in taxonomy.get("categories", []) or []:
        if str(c.get("id", "")).strip().lower() == key:
            return c
    return None


def _label_to_ids(
    branch: Dict[str, Any], attr_label: str, leaf_label: str
) -> Tuple[str | None, str | None]:
    """Return (attribute_id, node_id) for given labels (case-insensitive)."""
    a_id = None
    n_id = None
    al = attr_label.strip().lower()
    ll = leaf_label.strip().lower()
    for a in branch.get("attributes", []) or []:
        a_lab = str(a.get("label", "")).strip().lower()
        if a_lab == al or str(a.get("id", "")).strip().lower() == al:
            a_id = str(a.get("id"))
            for n in a.get("nodes", []) or []:
                children = n.get("children")
                if children:
                    for ch in children:
                        lab = str(ch.get("label", "")).strip().lower()
                        if lab == ll or str(ch.get("id", "")).strip().lower() == ll:
                            n_id = str(ch.get("id"))
                            return a_id, n_id
                else:
                    lab = str(n.get("label", "")).strip().lower()
                    if lab == ll or str(n.get("id", "")).strip().lower() == ll:
                        n_id = str(n.get("id"))
                        return a_id, n_id
    return a_id, n_id


def main(argv: List[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="Apply taxonomy patches (add/remove)")
    p.add_argument("--category", required=True, help="Category id (snake_case)")
    p.add_argument(
        "--patch-file",
        help="JSON file with add/remove keys (add_synonyms, add_nodes, update_attributes, remove_synonyms, remove_nodes)",
    )
    p.add_argument(
        "--add-syn",
        action="append",
        default=[],
        help="Add synonym triplet 'attribute_id:node_id:synonym' (can repeat)",
    )
    p.add_argument(
        "--remove-syn",
        action="append",
        default=[],
        help="Remove synonym triplet 'attribute_id:node_id:synonym' (can repeat)",
    )
    p.add_argument(
        "--add-syn-label",
        action="append",
        default=[],
        help="Add synonym using labels 'Attribute Label:Leaf Label:Synonym' (can repeat)",
    )
    p.add_argument(
        "--remove-syn-label",
        action="append",
        default=[],
        help="Remove synonym using labels 'Attribute Label:Leaf Label:Synonym' (can repeat)",
    )

    args = p.parse_args(argv)

    # Load taxonomy once
    taxonomy = get_attribute_taxonomy()
    branch = _find_branch(taxonomy, args.category)
    if branch is None:
        print(f"Category '{args.category}' not found in taxonomy.", file=sys.stderr)
        return 1

    # Build patch dict from CLI flags (if any)
    cli_patch: Dict[str, Any] = {}
    add_syn = _parse_triplets(args.add_syn, "add_syn") if args.add_syn else []
    rm_syn = _parse_triplets(args.remove_syn, "remove_syn") if args.remove_syn else []
    if add_syn:
        cli_patch["add_synonyms"] = add_syn
    if rm_syn:
        cli_patch["remove_synonyms"] = rm_syn

    # Label-based triplets
    if args.add_syn_label or args.remove_syn_label:
        add_syn_labeled: List[Dict[str, str]] = []
        rm_syn_labeled: List[Dict[str, str]] = []
        for raw in args.add_syn_label or []:
            try:
                attr_lab, leaf_lab, syn = raw.split(":", 2)
            except ValueError:
                raise SystemExit(
                    f"Invalid --add-syn-label '{raw}'. Expected 'Attribute Label:Leaf Label:Synonym'"
                )
            a_id, n_id = _label_to_ids(branch, attr_lab, leaf_lab)
            if not a_id or not n_id:
                raise SystemExit(
                    f"Could not resolve labels: attribute '{attr_lab}', leaf '{leaf_lab}' in category '{args.category}'."
                )
            add_syn_labeled.append(
                {"attribute_id": a_id, "node_id": n_id, "synonym": syn.strip()}
            )
        for raw in args.remove_syn_label or []:
            try:
                attr_lab, leaf_lab, syn = raw.split(":", 2)
            except ValueError:
                raise SystemExit(
                    f"Invalid --remove-syn-label '{raw}'. Expected 'Attribute Label:Leaf Label:Synonym'"
                )
            a_id, n_id = _label_to_ids(branch, attr_lab, leaf_lab)
            if not a_id or not n_id:
                raise SystemExit(
                    f"Could not resolve labels: attribute '{attr_lab}', leaf '{leaf_lab}' in category '{args.category}'."
                )
            rm_syn_labeled.append(
                {"attribute_id": a_id, "node_id": n_id, "synonym": syn.strip()}
            )
        if add_syn_labeled:
            cli_patch["add_synonyms"] = (cli_patch.get("add_synonyms") or []) + add_syn_labeled
        if rm_syn_labeled:
            cli_patch["remove_synonyms"] = (cli_patch.get("remove_synonyms") or []) + rm_syn_labeled

    # Load file patch if provided
    file_patch: Dict[str, Any] = {}
    if args.patch_file:
        file_patch = _load_patch_from_file(args.patch_file)

    # Merge patches: file first, then CLI additions override
    patch: Dict[str, Any] = {**file_patch}
    for k in ("add_synonyms", "add_nodes", "update_attributes", "remove_synonyms", "remove_nodes"):
        if k in cli_patch:
            patch[k] = (patch.get(k) or []) + cli_patch[k]

    # Apply removals first (if any), then additions
    changed = False
    if patch.get("remove_synonyms") or patch.get("remove_nodes"):
        new_branch = apply_grounding_patch(
            branch,
            {
                k: patch[k]
                for k in ("remove_synonyms", "remove_nodes")
                if patch.get(k)
            },
        )
        # Replace and persist
        cats = taxonomy.get("categories", []) or []
        for i, c in enumerate(cats):
            if str(c.get("id", "")).strip().lower() == args.category.strip().lower():
                cats[i] = new_branch
                break
        save_attribute_taxonomy(taxonomy)
        changed = True

    add_payload: Dict[str, Any] = {}
    for k in ("add_nodes", "add_synonyms", "update_attributes"):
        if patch.get(k):
            add_payload[k] = patch[k]
    if add_payload:
        ok = apply_taxonomy_patch(args.category, add_payload)
        changed = changed or ok

    if changed:
        print("Patch applied and taxonomy saved.")
        return 0
    else:
        print("No changes applied (empty patch or no-ops).")
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
