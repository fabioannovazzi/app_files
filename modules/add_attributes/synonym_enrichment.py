from __future__ import annotations

"""Automatic, budget‑aware synonym enrichment for taxonomy branches.

Runs on a branch when it's newly created, modified, or first seen.
It queries a high‑quality LLM with web search scoped to merchant/brand
domains to propose additions (and optional replacements) to per‑leaf
synonym lists, then applies a validated patch atomically.

The enrichment pass is fully automatic (no human review) and safe:
- Applies removals first when budget pressure requires replacement.
- Adds only normalized, de‑duplicated synonyms.
- Validation enforces budgets and uniqueness across leaves.

Public entry point:
    enrich_category_if_stale(llm_wrapper, category_id: str, *, service_tier: str | None = "high") -> bool

Returns True if changes were applied, False otherwise.
"""

import hashlib
import json
import logging
from typing import Any, Dict, Iterable, List

from modules.add_attributes.attribute_taxonomy import get_attribute_taxonomy, save_attribute_taxonomy
from modules.add_attributes.grounding import apply_grounding_patch
from modules.add_attributes.taxonomy_patch import apply_taxonomy_patch
from modules.add_attributes.tool_utils import build_web_search_request
from modules.utilities.cache import get_cache_path
from modules.utilities.config import get_naming_params
from modules.llm.model_router import query_llm_return_json

logger = logging.getLogger(__name__)

__all__ = ["enrich_category_if_stale"]


STATE_PATH = get_cache_path("synonym_enrichment_state.json")


DEFAULT_RETAILER_DOMAINS: List[str] = [
    "sephora.com",
    "ulta.com",
    "boots.com",
    "walgreens.com",
    "target.com",
    "walmart.com",
    "douglas.de",
    "amazon.com",
]


def _load_state() -> Dict[str, Any]:
    try:
        if STATE_PATH.exists():
            return json.loads(STATE_PATH.read_text(encoding="utf-8"))
    except Exception:
        logger.exception("Failed to load enrichment state: %s", STATE_PATH)
    return {}


def _save_state(data: Dict[str, Any]) -> None:
    try:
        STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
        STATE_PATH.write_text(json.dumps(data, indent=2, sort_keys=True), encoding="utf-8")
    except Exception:
        logger.exception("Failed to write enrichment state: %s", STATE_PATH)


def _normalized_branch_for_hash(branch: Dict[str, Any]) -> Dict[str, Any]:
    """Return a branch ready for hashing by removing volatile fields.

    We keep the structure and canonical fields relevant to synonym coverage.
    """
    try:
        out = {
            "id": branch.get("id"),
            "label": branch.get("label"),
            "attributes": [],
        }
        for a in branch.get("attributes", []) or []:
            out["attributes"].append(
                {
                    "id": a.get("id"),
                    "label": a.get("label"),
                    "nodes": [
                        {
                            "id": n.get("id"),
                            "label": n.get("label"),
                            # synonyms list order is irrelevant after normalization; include values only
                            "synonyms": sorted([str(s) for s in (n.get("synonyms") or [])]),
                            "children": [
                                {
                                    "id": ch.get("id"),
                                    "label": ch.get("label"),
                                    "synonyms": sorted([str(s) for s in (ch.get("synonyms") or [])]),
                                }
                                for ch in (n.get("children") or [])
                            ],
                        }
                        for n in (a.get("nodes") or [])
                    ],
                }
            )
        return out
    except Exception:
        logger.exception("Failed to build normalized branch snapshot for hash")
        return branch


def _branch_hash(branch: Dict[str, Any]) -> str:
    snapshot = _normalized_branch_for_hash(branch)
    blob = json.dumps(snapshot, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()


def _build_enrichment_prompt(category: str, branch: Dict[str, Any], max_syns: int) -> str:
    return (
        "You are expanding machine-facing synonyms for a taxonomy branch.\n"
        f"Category: {category}.\n"
        f"Goal: for each LEAF node, propose up to {max_syns} short, unambiguous synonyms that appear on official brand or major retailer pages."
        " Prefer common phrases that help an LLM map product descriptions to canonical values.\n"
        "Rules:\n"
        "- Return a PATCH ONLY in JSON: { 'add_synonyms': [{'attribute_id': str, 'node_id': str, 'synonym': str}],"
        " 'remove_synonyms': [{'attribute_id': str, 'node_id': str, 'synonym': str}] }.\n"
        "- Do NOT add labels themselves as synonyms; avoid duplicates, long sentences, or ambiguous tokens.\n"
        "- Only include synonyms actually observed on the allowed domains via web search.\n"
        "- If a leaf already has more than {max_syns} synonyms, propose REMOVE entries for the weakest/rare/ambiguous ones first.\n\n"
        f"Branch JSON (for reference):\n```json\n{json.dumps(branch, ensure_ascii=False)}\n```"
    )


def _max_synonyms_cap() -> int:
    # Keep in sync with modules.add_attributes.policies.DEFAULT_BUDGETS
    try:
        from modules.add_attributes.policies import budgets

        caps = budgets()
        return int(caps.get("max_synonyms_per_node", 5) or 5)
    except Exception:
        return 5


def enrich_category_if_stale(
    llm_wrapper,
    category_id: str,
    *,
    allowed_domains: Iterable[str] | None = None,
    service_tier: str | None = "high",
) -> bool:
    """Enrich synonyms for ``category_id`` if the branch hash changed.

    Returns True if a change was applied; False if skipped or no effective patch.
    """
    if llm_wrapper is None:
        return False
    category_key = str(category_id).strip().lower()
    taxonomy = get_attribute_taxonomy()
    branch = None
    for c in taxonomy.get("categories", []) or []:
        if str(c.get("id", "")).strip().lower() == category_key:
            branch = c
            break
    if branch is None:
        return False

    # Hash gating
    state = _load_state()
    current_hash = _branch_hash(branch)
    prev_hash = state.get(category_key, {}).get("hash")
    if prev_hash == current_hash:
        return False

    # Prepare LLM call
    naming = get_naming_params()
    step = naming.get("synonymResolutionQuery") or naming.get("taxonomyGroundingQuery") or naming["taxonomyGenerationQuery"]
    system_prompt = "You generate high-quality machine-facing synonyms. Return JSON only."
    max_syns = _max_synonyms_cap()
    user_prompt = _build_enrichment_prompt(category_key, branch, max_syns)
    domains = list(allowed_domains or DEFAULT_RETAILER_DOMAINS)
    tools, extra_body = build_web_search_request(domains)

    try:
        patch = query_llm_return_json(
            llm_wrapper,
            step,
            system_prompt,
            user_prompt,
            tools=tools,
            tool_choice="auto",
            service_tier=service_tier,
            reasoning_effort="high",
            extra_body=extra_body,
        )
    except Exception as e:
        logger.exception("Synonym enrichment LLM call failed for '%s': %s", category_key, e)
        return False

    # Apply patch if any. Remove then add to honor budgets and ordering.
    changed = False
    if isinstance(patch, dict):
        try:
            if patch.get("remove_synonyms"):
                new_branch = apply_grounding_patch(branch, {"remove_synonyms": patch["remove_synonyms"]})
                # Persist removal by replacing the category branch
                cats = taxonomy.get("categories", []) or []
                for i, c in enumerate(cats):
                    if str(c.get("id", "")).strip().lower() == category_key:
                        cats[i] = new_branch
                        break
                save_attribute_taxonomy(taxonomy)
                # Refresh branch reference for subsequent additions
                branch = new_branch
                changed = True
        except Exception:
            logger.exception("Failed applying remove_synonyms for '%s'", category_key)
        try:
            if patch.get("add_synonyms"):
                ok = apply_taxonomy_patch(category_key, {"add_synonyms": patch["add_synonyms"]})
                changed = changed or ok
        except Exception:
            logger.exception("Failed applying add_synonyms for '%s'", category_key)

    # Update state if something changed
    if changed:
        try:
            # Re-load taxonomy to compute fresh hash from persisted state
            latest = get_attribute_taxonomy()
            latest_branch = None
            for c in latest.get("categories", []) or []:
                if str(c.get("id", "")).strip().lower() == category_key:
                    latest_branch = c
                    break
            new_hash = _branch_hash(latest_branch or branch)
            state[category_key] = {"hash": new_hash}
            _save_state(state)
        except Exception:
            # Fallback: persist previous hash to avoid immediate re-run
            state[category_key] = {"hash": current_hash}
            _save_state(state)
    else:
        # No effective changes but do not block future runs; keep old hash
        pass

    return changed
