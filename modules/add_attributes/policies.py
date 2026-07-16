from __future__ import annotations

"""Branch-local prompt policies for taxonomy generation and review.

These are small, domain-agnostic constraints that keep branches compact,
unambiguous, and consistent without centralizing vocabularies.
"""

from typing import Dict

__all__ = ["build_policy_text", "budgets"]


DEFAULT_BUDGETS = {
    "max_attributes": 12,
    "max_nodes_per_attribute": 40,
    "max_synonyms_per_node": 5,
    # Filter-grounded categories can legitimately expose broader multi-select
    # sets (for example ingredient/claim preferences), so keep this threshold
    # comfortably above tiny toy branches.
    "max_multi_leaves": 25,
}


def build_policy_text(category_name: str) -> str:
    """Return a short policy text to embed in prompts for ``category_name``."""
    c = (category_name or "").lower()
    spf_policy = (
        "If SPF is relevant, do not enumerate SPF buckets as nodes. Instead, model: "
        "(a) a numeric field 'spf' (integer), and (b) a categorical 'sun_filter_type' with values 'mineral', "
        "'chemical', or 'hybrid'. You may also include a boolean 'broad_spectrum'."
    )
    general = [
        "IDs must be snake_case; labels human-readable.",
        "Parents are structure-only: only leaf nodes may have synonyms.",
        "Each attribute must include 'unknown' and 'other' top-level nodes.",
        "Synonyms must not be duplicated across nodes within the same attribute.",
        "Avoid ambiguous synonyms that fit multiple nodes (prefer specificity).",
        "Numeric concepts must be numeric fields, not enumerated ranges.",
        f"Budgets: attributes ≤ {DEFAULT_BUDGETS['max_attributes']}, nodes/attribute ≤ {DEFAULT_BUDGETS['max_nodes_per_attribute']}, synonyms/node ≤ {DEFAULT_BUDGETS['max_synonyms_per_node']}.",
        f"Selection governance: use 'single' unless the attribute is naturally multi-select with ≤ {DEFAULT_BUDGETS['max_multi_leaves']} distinct values (e.g., usage areas). Large enumerations (e.g., colors, shades) must be 'single'.",
        "Include governance metadata per attribute: selection ('single'|'multi'), scope ('product'|'variant'), and kind ('composition'|'performance'|'regulatory').",
    ]
    if any(k in c for k in ("foundation", "blush", "bronzer")):
        general.append(spf_policy)
    return "\n- " + "\n- ".join(general)


def budgets() -> Dict[str, int]:
    """Return default budget thresholds used in generation/validation prompts."""
    return dict(DEFAULT_BUDGETS)
