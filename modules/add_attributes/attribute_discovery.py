from __future__ import annotations

import time
from difflib import SequenceMatcher
from typing import Iterable, List

from modules.llm import model_router
from modules.llm.batch_runner import run_step_json
from modules.utilities.config import get_naming_params
from modules.add_attributes.tool_utils import build_web_search_request

__all__ = [
    "deduplicate_attributes",
    "discover_attributes_for_category",
]


def _normalize(text: str) -> str:
    return text.lower().replace("_", " ").replace("-", " ").strip()


def _similar(a: str, b: str) -> float:
    return SequenceMatcher(None, a, b).ratio()


def deduplicate_attributes(
    attributes: Iterable[str],
    existing_columns: Iterable[str],
    llm_wrapper=None,
    *,
    threshold: float = 0.8,
) -> List[str]:
    """Remove attribute names that match existing columns."""

    existing_norm = [_normalize(c) for c in existing_columns]
    unique: List[str] = []
    for attr in attributes:
        norm = _normalize(attr)
        if any(
            _similar(norm, col) >= threshold or norm in col or col in norm
            for col in existing_norm
        ):
            continue
        if attr not in unique:
            unique.append(attr)

    if llm_wrapper and unique:
        namingParams = get_naming_params()
        query_step = namingParams["attributeDiscoveryQuery"]
        user_prompt = (
            "Existing columns:"
            f" {', '.join(existing_columns)}\n"
            f"Proposed attributes: {', '.join(unique)}\n"
            'Return JSON {"keep": [attributes not already represented]}'
        )
        resp_list = run_step_json(
            llm_wrapper,
            query_step,
            "You are a data analyst. Return JSON only.",
            user_prompt,
            tools=[{"type": "web_search_preview"}],
            tool_choice="auto",
        )
        resp = resp_list[0] if resp_list else {}
        if isinstance(resp, dict) and isinstance(resp.get("keep"), list):
            keep = set(resp["keep"])
            unique = [a for a in unique if a in keep]
    return unique


def discover_attributes_for_category(
    llm_wrapper,
    category: str,
    existing_columns: Iterable[str],
    *,
    use_batch: bool = False,
    throttle: float = 1.0,
    service_tier: str | None = None,
    domains: List[str] | None = None,
) -> List[str]:
    """Use an LLM to suggest attribute names for a product category.

    Parameters
    ----------
    llm_wrapper:
        Wrapper responsible for invoking the LLM.
    category:
        Product category for which attribute suggestions are requested.
    existing_columns:
        Columns already present in the dataframe to avoid duplicates.
    use_batch:
        Whether to use the batch endpoint for LLM calls.
    throttle:
        Delay between non-batch requests to respect rate limits.
    """
    namingParams = get_naming_params()
    query_step = namingParams["attributeDiscoveryQuery"]
    system_prompt = "You are an expert product analyst. Return JSON only."
    if domains:
        joined = ", ".join(domains)
        domain_txt = (
            " Focus your research on official sources from: "
            f"{joined}. Use web searches with `site:` scoped to these domains "
            "and ignore other sites."
        )
    else:
        domain_txt = ""
    user_prompt = (
        f"What key qualities or attributes do consumers consider when comparing products in the '{category}' category? "
        "Provide a list of 3-7 short attribute names that can be rated from 1 to 5. "
        f"{domain_txt}"
        'Return JSON {"attributes": ["attribute1", ...]}'
    )
    # Unified LLM call path (batching handled by wrapper/config if applicable)
    tools, extra_body = build_web_search_request(domains)
    resp = run_step_json(
        llm_wrapper,
        query_step,
        system_prompt,
        user_prompt,
        tools=tools,
        tool_choice="auto",
        service_tier=service_tier,
        extra_body=extra_body,
    )[0]
    # Optional throttling between sequential requests (no-op for batch mode)
    if throttle > 0 and not use_batch:
        time.sleep(throttle)
    attrs = resp.get("attributes") if isinstance(resp, dict) else []
    if not isinstance(attrs, list):
        attrs = []
    attrs = [str(a) for a in attrs if isinstance(a, (str, int, float))]
    return deduplicate_attributes(attrs, list(existing_columns), llm_wrapper)
