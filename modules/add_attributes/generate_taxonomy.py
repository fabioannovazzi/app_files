import json
import logging
from typing import Any, Callable, Dict, List, Optional

from .taxonomy_schema import canonicalize_branch, validate_branch, branch_metrics
from .policies import build_policy_text

# ---------------------------------------------------------------------------
# Prompt builders
# ---------------------------------------------------------------------------


def build_generation_prompt(
    category_name: str,
    example_categories: List[Dict[str, Any]],
    *,
    industry: Optional[str] = None,
    industry_description: Optional[str] = None,
    company: Optional[str] = None,
) -> str:
    """Constructs a detailed prompt for the LLM to generate a taxonomy branch."""
    prompt_lines: List[str] = []

    # Role and task description
    prompt_lines.append(
        f"You are an expert in product taxonomies. Your task is to create a comprehensive set of attribute branches "
        f'for the product category "{category_name}". Each branch can be either hierarchical (2 levels) or multi-select '
        f"(flat). Use 'id' (snake_case) and 'label' (human-readable). Provide synonyms for each leaf so the model can match variants. "
        f"Always include an 'unknown' node when the attribute might be unstated, and an 'other' node labelled 'not in taxonomy' for values that fall outside your list."
    )

    # Insert industry/description/company context if provided
    context_lines: List[str] = []
    if industry:
        context_lines.append(f"Industry: {industry}.")
    if industry_description:
        context_lines.append(f"Industry description: {industry_description}.")
    if company:
        context_lines.append(f"Company: {company}.")
    if context_lines:
        prompt_lines.append(" ".join(context_lines))

    # Present examples (trim to first 3 attributes each)
    if example_categories:
        examples_text = []
        for cat in example_categories:
            attrs = cat.get("attributes", [])[:3]
            examples_text.append(
                {
                    "id": cat["id"],
                    "label": cat.get("label", cat["id"]),
                    "attributes": [
                        {"id": a.get("id"), "label": a.get("label")} for a in attrs
                    ],
                }
            )
        prompt_lines.append(
            f"Example categories: ```json\n{json.dumps(examples_text, indent=2)}\n```"
        )

    # Policy constraints
    policy_text = build_policy_text(category_name)
    if policy_text:
        prompt_lines.append("Policy:" + policy_text)

    # Final instructions
    prompt_lines.append(
        "Return a JSON object with this shape. Parents are structure-only (no synonyms on any node that has children).\n"
        "{\n"
        '  "id": (category id),\n'
        '  "label": (category name),\n'
        '  "attributes": [\n'
        "    {\n"
        '      "id": (attribute id),\n'
        '      "label": (attribute label),\n'
        '      "hierarchical": true | false,\n'
        '      "levels": 2 | 1,\n'
        '      "selection": "single" | "multi",\n'
        '      "scope": "product" | "variant",\n'
        '      "kind": "composition" | "performance" | "regulatory",\n'
        '      "nodes": [\n'
        '        {"id": (node id), "label": (node label), "synonyms": [..], "children": [...]?},\n'
        '        {"id": "unknown", "label": "N/A (not stated)"},\n'
        '        {"id": "other", "label": "not in taxonomy"}\n'
        "      ]\n"
        "    },\n"
        "    ...\n"
        "  ]\n"
        "}"
    )

    return "\n".join(prompt_lines)


def build_review_prompt(
    category_name: str,
    draft_json: Dict[str, Any],
    *,
    industry: Optional[str] = None,
    industry_description: Optional[str] = None,
    company: Optional[str] = None,
) -> str:
    """Asks the LLM to review the draft and return a PATCH only."""
    policy_text = build_policy_text(category_name)
    return (
        f'You are a taxonomy reviewer. Review the draft taxonomy for category "{category_name}" below. '
        "Identify any missing obvious attribute values or sub-nodes (e.g. packaging glass). Suggest additional synonyms "
        "for existing values if helpful. Respect the policy below. Return a PATCH ONLY with this exact shape: \n"
        "{ 'add_nodes': [{'attribute_id': str, 'id': str, 'label': str, 'parent_id': str?}],\n"
        "  'add_synonyms': [{'attribute_id': str, 'node_id': str, 'synonym': str}] }\n"
        "If nothing is missing, return { }.\n\n"
        f"Policy:{policy_text}\n\n"
        f"Draft taxonomy:\n```json\n{json.dumps(draft_json, indent=2)}\n```\n\n"
        "Please return JSON only. Do NOT return the full branch or remove anything."
    )


# ---------------------------------------------------------------------------
# Utility: ensure unknown/other nodes exist
# ---------------------------------------------------------------------------


def _normalize_and_validate(branch: Dict[str, Any]) -> Dict[str, Any]:
    """Apply canonicalization and strict validation; log warnings if any."""
    normalized, warnings = validate_branch(branch)
    if warnings:
        logger.info("taxonomy normalization warnings: %s", ", ".join(warnings))
    return normalized


# ---------------------------------------------------------------------------
# Main generator with optional review
# ---------------------------------------------------------------------------


def generate_category_taxonomy(
    llm_call: Callable[[str], Dict[str, Any]],
    category_name: str,
    existing_data: Dict[str, Any],
    example_count: int = 2,
    perform_review: bool = True,
    *,
    industry: Optional[str] = None,
    industry_description: Optional[str] = None,
    company: Optional[str] = None,
) -> Dict[str, Any]:
    """Generates a taxonomy branch for a new category."""
    examples = (
        existing_data.get("categories", [])[:example_count] if existing_data else []
    )

    gen_prompt = build_generation_prompt(
        category_name,
        examples,
        industry=industry,
        industry_description=industry_description,
        company=company,
    )
    draft_json = llm_call(gen_prompt)
    draft_json = canonicalize_branch(draft_json)
    draft_json = _normalize_and_validate(draft_json)
    # Log metrics for observability
    try:
        logger.info("branch metrics: %s", branch_metrics(draft_json))
    except Exception as e:
        logger.warning("Failed to log branch metrics: %s", e)

    if perform_review:
        review_prompt = build_review_prompt(
            category_name,
            draft_json,
            industry=industry,
            industry_description=industry_description,
            company=company,
        )
        review_json = llm_call(review_prompt)
        if isinstance(review_json, dict):
            # Accept patches only
            add_nodes = review_json.get("add_nodes") or []
            add_syns = review_json.get("add_synonyms") or []
            if add_nodes or add_syns:
                attrs_by_id = {a["id"]: a for a in draft_json.get("attributes", [])}
                for n in add_nodes:
                    try:
                        attr_id = str(n.get("attribute_id"))
                        parent_id = n.get("parent_id")
                        node = {"id": n["id"], "label": n.get("label", n["id"]) }
                    except Exception:
                        logger.exception("Invalid add_node patch; skipping: %r", n)
                        continue
                    attr = attrs_by_id.get(attr_id)
                    if not attr:
                        continue
                    if parent_id:
                        for top in attr.get("nodes", []):
                            if top.get("id") == parent_id:
                                top.setdefault("children", []).append(node)
                                break
                    else:
                        attr.setdefault("nodes", []).append(node)
                for s in add_syns:
                    try:
                        attr_id = str(s.get("attribute_id"))
                        node_id = str(s.get("node_id"))
                        syn = s.get("synonym")
                    except Exception:
                        logger.exception("Invalid add_synonym patch; skipping: %r", s)
                        continue
                    if not syn:
                        continue
                    attr = attrs_by_id.get(attr_id)
                    if not attr:
                        continue
                    for top in attr.get("nodes", []):
                        if top.get("id") == node_id and not top.get("children"):
                            top.setdefault("synonyms", []).append(syn)
                            break
                        for ch in (top.get("children") or []):
                            if ch.get("id") == node_id:
                                ch.setdefault("synonyms", []).append(syn)
                                break
                draft_json = _normalize_and_validate(draft_json)
                try:
                    logger.info(
                        "branch metrics after patch: %s", branch_metrics(draft_json)
                    )
                except Exception as e:
                    logger.warning("Failed to log post-review metrics: %s", e)

    return draft_json
logger = logging.getLogger(__name__)
