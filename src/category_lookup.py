"""Website resolution for product categories.

This module caches website lookups in ``caches/category_websites.json``
relative to the repository root. The mapping is loaded once per session and
extended only for previously unseen categories.

Improvements:
- Prompts include market/industry context (when available) to avoid
  cross-industry mismatches; if unsure, return an empty list.
- Missing lookups are processed in small chunks and saved incrementally so
  partial progress is not lost if a run is interrupted.
"""

from __future__ import annotations

import json
import logging
import os
from itertools import islice
from typing import Dict, Iterable, List

from modules.llm.batch_runner import run_step_json
from modules.utilities.cache import get_cache_path
from modules.utilities.config import get_naming_params
from modules.utilities.session_context import session_state
from modules.utilities.ui_notifier import ui

FILE_PATH = get_cache_path("category_websites.json")
_WEBSITE_CACHE: Dict[str, List[str]] | None = None
logger = logging.getLogger(__name__)

_CLI_CATEGORY_CONTEXT: Dict[str, str | None] = {
    "industry": None,
    "industry_description": None,
}


def load_mapping() -> Dict[str, List[str]]:
    """Return the cached category website mapping."""

    global _WEBSITE_CACHE
    if _WEBSITE_CACHE is None:
        if FILE_PATH.exists():
            try:
                raw: Dict[str, list[str] | str] = json.loads(FILE_PATH.read_text())
                _WEBSITE_CACHE = {
                    k: v if isinstance(v, list) else [v] for k, v in raw.items()
                }
            except json.JSONDecodeError:
                _WEBSITE_CACHE = {}
        else:
            _WEBSITE_CACHE = {}
    return _WEBSITE_CACHE


def _save_mapping(mapping: Dict[str, List[str]]) -> None:
    """Atomically persist the category website mapping to disk."""
    FILE_PATH.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = FILE_PATH.with_suffix(FILE_PATH.suffix + ".tmp")
    data = json.dumps(mapping, indent=2, sort_keys=True)
    with tmp_path.open("w", encoding="utf-8") as fh:
        fh.write(data)
        fh.flush()
        try:
            os.fsync(fh.fileno())
        except OSError:
            pass
    tmp_path.replace(FILE_PATH)


def set_category_market_context(
    *, industry: str | None = None, industry_description: str | None = None
) -> None:
    """Set fallback market context for category lookups when UI is absent."""

    def _clean(value: str | None) -> str | None:
        if isinstance(value, str):
            value = value.strip()
            return value or None
        return None

    _CLI_CATEGORY_CONTEXT["industry"] = _clean(industry)
    _CLI_CATEGORY_CONTEXT["industry_description"] = _clean(industry_description)


def _get_market_context() -> dict:
    """Return market/industry context from session/config when available."""

    def _clean(value: object) -> str | None:
        if isinstance(value, str):
            value = value.strip()
            return value or None
        return None

    industry = _clean(_CLI_CATEGORY_CONTEXT.get("industry"))
    industry_desc = _clean(_CLI_CATEGORY_CONTEXT.get("industry_description"))
    naming = get_naming_params()
    industry_key = naming["industry"]
    industry_desc_key = naming["industryDescription"]
    param_dict = session_state.get("attr_param_dict") or {}
    if isinstance(param_dict, dict):
        session_industry = _clean(
            session_state.get(industry_key) or param_dict.get(industry_key)
        )
        session_desc = _clean(
            session_state.get(industry_desc_key) or param_dict.get(industry_desc_key)
        )
        industry = session_industry or industry
        industry_desc = session_desc or industry_desc
    return {
        "industry": industry,
        "industry_description": industry_desc,
    }


def lookup_category_websites(
    llm_wrapper,
    categories: Iterable[str],
    *,
    service_tier: str | None = "flex",
) -> Dict[str, List[str]]:
    """Ensure websites exist for ``categories`` and return the full mapping.

    Adds market/industry context to improve precision. Returns an empty list
    for categories where relevant websites cannot be confidently identified.
    """

    mapping = load_mapping()
    # Treat entries with at least one non-empty URL as present; retry if empty/missing
    categories_set = {c for c in set(categories) if c}
    missing = []
    for c in categories_set:
        val = mapping.get(c)
        if not (isinstance(val, list) and any(isinstance(s, str) and s.strip() for s in val)):
            missing.append(c)
    if missing:
        naming = get_naming_params()
        categoryWebsiteLookup = naming["categoryWebsiteLookup"]

        ctx = _get_market_context()
        industry = ctx.get("industry")
        industry_desc = ctx.get("industry_description")

        # Require at least some market context to reduce false matches
        if not (industry or industry_desc):
            ui.error(
                "Please provide the market Industry (or an Industry description) to resolve category websites."
            )
            # Do not modify the cache; let the caller handle this as a blocking condition
            raise ValueError("Missing market context for category website lookup")

        system = "You are a careful web research assistant. Return JSON only."

        def _prompt_for(cat: str) -> str:
            parts = [
                f"Find up to three official websites for the product category '{cat}'.",
            ]
            context_bits = []
            if industry:
                context_bits.append(f"industry: {industry}")
            if industry_desc:
                context_bits.append(f"industry description: {industry_desc}")
            if context_bits:
                parts.append(
                    "Context: this is about the product's market (" + ", ".join(context_bits) + ")."
                )
            parts.append(
                "Rules: choose official brand/company category sites (not retailers or trade associations). "
                "If the sites do not clearly belong to this market/industry, return an empty list."
            )
            parts.append(
                'Return JSON {"websites": ["https://example.com", "https://example.org"]}.'
            )
            return " ".join(parts)

        CHUNK_SIZE = 20
        it = iter(missing)
        while True:
            chunk = list(islice(it, CHUNK_SIZE))
            if not chunk:
                break
            prompts = [_prompt_for(c) for c in chunk]
            try:
                results = run_step_json(
                    llm_wrapper,
                    categoryWebsiteLookup,
                    system,
                    prompts,
                    tools=[{"type": "web_search_preview"}],
                    tool_choice="auto",
                    service_tier=service_tier,
                )
            except Exception as e:
                logger.warning("Category website lookup batch failed: %s", e)
                results = [{} for _ in chunk]

            for cat, resp in zip(chunk, results):
                websites: list[str] = []
                if isinstance(resp, dict):
                    sites = resp.get("websites") or resp.get("website")
                    if isinstance(sites, str):
                        websites = [sites]
                    elif isinstance(sites, list):
                        websites = [s for s in sites if isinstance(s, str)]

                unique_sites = list(dict.fromkeys(websites))[:3]
                if unique_sites:
                    mapping[cat] = unique_sites
                else:
                    mapping.pop(cat, None)

            _save_mapping(mapping)
            logger.info(
                "Saved %d category website mappings this chunk to %s",
                len(chunk),
                FILE_PATH,
            )

    return mapping


__all__ = [
    "lookup_category_websites",
    "load_mapping",
    "set_category_market_context",
]
