from __future__ import annotations

"""Web-grounding hooks for taxonomy branches (optional).

This module provides an optional pass that uses web search tools to
gather evidence for nodes/synonyms and optionally prune low-confidence
entries. By default it is conservative and returns the branch as-is.

Design
- Evidence-driven: ask for manufacturer/major retailer snippets.
- Patch-based: request a minimal patch (add/remove synonyms or nodes).
- Deterministic: apply patch, then revalidate via taxonomy_schema.

Usage
------
branch = ground_branch_with_web(llm_wrapper, branch, category)

Notes
- This is disabled by default in call sites to avoid surprises.
- Relies on the project's model_router to access web_search tools.
"""

from typing import Any, Dict, List
import logging

from modules.add_attributes.taxonomy_schema import validate_branch
from modules.llm.model_router import query_llm_return_json
from modules.utilities.config import get_naming_params

logger = logging.getLogger(__name__)


def _build_grounding_prompt(category: str, branch: Dict[str, Any]) -> str:
    return (
        "You are validating a taxonomy branch against web evidence.\n"
        f"Category: {category}.\n"
        "Use web search to check manufacturer and major retailer pages."
        " Keep only synonyms explicitly present in reliable sources; propose removals for ambiguous or unsupported ones.\n"
        "Return a PATCH, not a full branch, in JSON with keys: \n"
        "{ 'remove_synonyms': [{'attribute_id': str, 'node_id': str, 'synonym': str}],"
        "  'remove_nodes': [{ 'attribute_id': str, 'node_id': str }]}\n\n"
        f"Branch to validate (JSON):\n```json\n{branch}\n```"
    )


def apply_grounding_patch(branch: Dict[str, Any], patch: Dict[str, Any]) -> Dict[str, Any]:
    """Apply a conservative grounding patch to a branch and re-validate."""
    attrs = {a["id"]: a for a in branch.get("attributes", [])}
    for rm in patch.get("remove_synonyms", []) or []:
        a = attrs.get(rm.get("attribute_id"))
        if not a:
            continue
        nid = rm.get("node_id")
        syn = (rm.get("synonym") or "").strip().lower()
        if not nid or not syn:
            continue
        for top in a.get("nodes", []):
            if top.get("id") == nid and not top.get("children"):
                if top.get("synonyms"):
                    top["synonyms"] = [s for s in top["synonyms"] if s != syn]
                break
            for ch in (top.get("children") or []):
                if ch.get("id") == nid and ch.get("synonyms"):
                    ch["synonyms"] = [s for s in ch["synonyms"] if s != syn]
                    break

    for rm in patch.get("remove_nodes", []) or []:
        a = attrs.get(rm.get("attribute_id"))
        if not a:
            continue
        nid = rm.get("node_id")
        if not nid:
            continue
        nodes = a.get("nodes", [])
        a["nodes"] = [n for n in nodes if n.get("id") != nid]

    normalized, _ = validate_branch(branch)
    return normalized


def ground_branch_with_web(
    llm_wrapper,
    branch: Dict[str, Any],
    category: str,
    *,
    service_tier: str | None = None,
) -> Dict[str, Any]:
    """Return a grounded branch using web evidence (conservative)."""
    naming = get_naming_params()
    try:
        query_step = naming["taxonomyGroundingQuery"]
    except KeyError:
        query_step = naming["taxonomyGenerationQuery"]
    system_prompt = "You verify taxonomy nodes against evidence. Return JSON only."
    prompt = _build_grounding_prompt(category, branch)
    patch = query_llm_return_json(
        llm_wrapper,
        query_step,
        system_prompt,
        prompt,
        tools=[{"type": "web_search_preview"}],
        tool_choice="auto",
        service_tier=service_tier,
    )
    if isinstance(patch, dict) and (patch.get("remove_synonyms") or patch.get("remove_nodes")):
        try:
            return apply_grounding_patch(branch, patch)
        except Exception as e:
            logger.exception("Failed to apply grounding patch; returning original branch")
            return branch
    return branch

__all__ = ["ground_branch_with_web", "apply_grounding_patch"]
