"""Website resolution for merchant and brand names.

This module caches website lookups in ``caches/merchant_brand_websites.json``.
The mapping is loaded once per session and extended only for previously unseen
names.

Improvements:
- Prompts include market/industry context (when available) to avoid
  cross-industry mismatches (e.g., NAM the association vs. a cosmetics brand).
- Missing lookups are processed in small chunks and saved incrementally so
  partial progress is not lost if a run is interrupted.
"""

from __future__ import annotations

import json
import logging
import os
import re
from datetime import datetime, timedelta, timezone
from itertools import islice
from typing import Dict, Iterable
from urllib.parse import urlparse

logger = logging.getLogger(__name__)

from modules.llm.batch_runner import run_step_json
from modules.llm.model_router import query_llm_return_json
from modules.utilities.cache import get_cache_path
from modules.utilities.config import get_naming_params
from modules.utilities.session_context import session_state
from modules.utilities.ui_notifier import ui
from src.file_lock import FileLock

FILE_PATH = get_cache_path("merchant_brand_websites.json")
_WEBSITE_CACHE: Dict[str, str | None] | None = None

# CLI/test fallback market context when UI session state is unavailable.
_CLI_MARKET_CONTEXT: Dict[str, str | None] = {
    "industry": None,
    "industry_description": None,
}

# Store retry metadata separately to keep the primary mapping file stable for
# existing tools/tests. Entries are keyed by canonical name and store
# ISO-8601 timestamps for the last failed attempt.
META_PATH = get_cache_path("merchant_brand_websites_meta.json")
# Do not retry failed lookups within this window
RETRY_TTL = timedelta(days=14)
_URL_RE = re.compile(r"https?://[^\s\"'<>]+", re.IGNORECASE)
_DOMAIN_RE = re.compile(r"\b(?:[a-z0-9-]+\.)+[a-z]{2,}\b", re.IGNORECASE)


def _normalize_website(value: object) -> str | None:
    if not isinstance(value, str):
        return None
    raw = value.strip()
    if not raw:
        return None
    raw = raw.strip(" \t\r\n.,;:()[]{}<>")
    if raw.startswith("www."):
        raw = "https://" + raw
    elif not raw.startswith(("http://", "https://")):
        if _DOMAIN_RE.fullmatch(raw) or ("." in raw and " " not in raw):
            raw = "https://" + raw
    try:
        parsed = urlparse(raw)
    except Exception:
        return None
    if not parsed.scheme or not parsed.netloc:
        return None
    return raw


def _extract_website_from_text(text: str) -> str | None:
    if not text:
        return None
    # Try to parse JSON blob if present.
    try:
        data = json.loads(text)
        if isinstance(data, dict):
            return _normalize_website(data.get("website"))
    except Exception:
        pass
    # Try to locate a JSON snippet containing "website".
    match = re.search(r'"website"\s*:\s*"([^"]+)"', text, re.IGNORECASE)
    if match:
        return _normalize_website(match.group(1))
    # Fall back to URLs/domains in the text.
    url_match = _URL_RE.search(text)
    if url_match:
        return _normalize_website(url_match.group(0))
    domain_match = _DOMAIN_RE.search(text)
    if domain_match:
        return _normalize_website(domain_match.group(0))
    return None


def load_mapping() -> Dict[str, str | None]:
    """Return the cached website mapping, loading it from disk if needed."""

    global _WEBSITE_CACHE
    if _WEBSITE_CACHE is None:
        if FILE_PATH.exists():
            try:
                _WEBSITE_CACHE = json.loads(FILE_PATH.read_text())
            except json.JSONDecodeError:
                _WEBSITE_CACHE = {}
        else:
            _WEBSITE_CACHE = {}
    return _WEBSITE_CACHE


def _load_meta() -> Dict[str, Dict[str, str]]:
    try:
        if META_PATH.exists():
            return json.loads(META_PATH.read_text())
    except Exception:
        logger.exception("Failed to load website lookup meta: %s", META_PATH)
    return {}


def _save_meta(meta: Dict[str, Dict[str, str]]) -> None:
    try:
        META_PATH.parent.mkdir(parents=True, exist_ok=True)
        with FileLock(META_PATH):
            on_disk: Dict[str, Dict[str, str]] = {}
            if META_PATH.exists():
                try:
                    on_disk = json.loads(META_PATH.read_text())
                except json.JSONDecodeError:
                    on_disk = {}
            merged: Dict[str, Dict[str, str]] = dict(on_disk)
            merged.update(meta)
            tmp_path = META_PATH.with_suffix(META_PATH.suffix + ".tmp")
            data = json.dumps(merged, indent=2, sort_keys=True)
            with tmp_path.open("w", encoding="utf-8") as fh:
                fh.write(data)
                fh.flush()
                try:
                    os.fsync(fh.fileno())
                except OSError:
                    pass
            tmp_path.replace(META_PATH)
            meta.clear()
            meta.update(merged)
    except Exception:
        logger.exception("Failed to write website lookup meta: %s", META_PATH)


def _save_mapping(mapping: Dict[str, str | None]) -> None:
    """Atomically persist the website mapping to disk.

    Writes to a temporary file in the same directory and then replaces the
    target file to avoid partial writes if the process crashes mid-write.
    """
    global _WEBSITE_CACHE

    FILE_PATH.parent.mkdir(parents=True, exist_ok=True)
    with FileLock(FILE_PATH):
        on_disk: Dict[str, str | None] = {}
        if FILE_PATH.exists():
            try:
                on_disk = json.loads(FILE_PATH.read_text())
            except json.JSONDecodeError:
                on_disk = {}
        merged: Dict[str, str | None] = dict(on_disk)
        merged.update(mapping)
        tmp_path = FILE_PATH.with_suffix(FILE_PATH.suffix + ".tmp")
        data = json.dumps(merged, indent=2, sort_keys=True)
        with tmp_path.open("w", encoding="utf-8") as fh:
            fh.write(data)
            fh.flush()
            try:
                os.fsync(fh.fileno())
            except OSError:
                # fsync may not be available on all platforms/filesystems
                pass
        tmp_path.replace(FILE_PATH)
        mapping.clear()
        mapping.update(merged)
        _WEBSITE_CACHE = mapping


def set_lookup_market_context(
    *, industry: str | None = None, industry_description: str | None = None
) -> None:
    """Set fallback market context for CLI runs and tests.

    Parameters
    ----------
    industry:
        Market or industry name to include in lookup prompts.
    industry_description:
        Optional descriptive text for the market/industry.
    """

    def _clean(value: str | None) -> str | None:
        if isinstance(value, str):
            value = value.strip()
            return value or None
        return None

    _CLI_MARKET_CONTEXT["industry"] = _clean(industry)
    _CLI_MARKET_CONTEXT["industry_description"] = _clean(industry_description)


def _get_market_context() -> dict:
    """Return market/industry context from session/config when available."""

    def _clean(value: object) -> str | None:
        if isinstance(value, str):
            value = value.strip()
            return value or None
        return None

    industry = _clean(_CLI_MARKET_CONTEXT.get("industry"))
    industry_desc = _clean(_CLI_MARKET_CONTEXT.get("industry_description"))
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


def lookup_websites(
    llm_wrapper,
    names: Iterable[str],
    aliases: Dict[str, str] | None = None,
    service_tier: str | None = "flex",
    *,
    force_refresh: bool = False,
) -> Dict[str, str | None]:
    """Ensure websites exist for ``names`` and return the full mapping.

    Parameters
    ----------
    llm_wrapper:
        Wrapper used for LLM calls.
    names:
        Iterable of brand or merchant names to resolve.
    aliases:
        Optional mapping of normalized names to a canonical representation. The
        canonical form is used as the cache key to avoid duplicate entries for
        spelling or casing variants.
    service_tier:
        Service tier used for LLM queries.
    force_refresh:
        When True, retry lookups even if a previous failure is within the TTL.
    """

    mapping = load_mapping()
    namingParams = get_naming_params()
    merchantBrandWebsiteLookup = namingParams["merchantBrandWebsiteLookup"]

    def _canon(n: str) -> str:
        base = n.strip().lower()
        return aliases.get(base, base) if aliases else base

    canonical_names = {_canon(n) for n in names if n}
    # Treat entries with a non-empty string URL as present.
    # For failed lookups (None/empty), only retry if the TTL has expired.
    meta = _load_meta()

    def _too_soon(n: str) -> bool:
        rec = meta.get(n)
        if not isinstance(rec, dict):
            return False
        ts = rec.get("last_failed")
        if not ts:
            return False
        try:
            when = datetime.fromisoformat(ts)
            if when.tzinfo is None:
                when = when.replace(tzinfo=timezone.utc)
        except Exception:
            return False
        return datetime.now(timezone.utc) - when < RETRY_TTL

    missing = []
    for n in canonical_names:
        val = mapping.get(n)
        if isinstance(val, str) and val.strip():
            continue  # already resolved
        # Skip if recently failed unless forcing refresh
        if not force_refresh and _too_soon(n):
            continue
        missing.append(n)

    if missing:
        # Add market context to prompts when available
        ctx = _get_market_context()
        industry = ctx.get("industry")
        industry_desc = ctx.get("industry_description")

        # Require at least some market context to reduce false matches
        if not (industry or industry_desc):
            ui.error(
                "Please provide the market Industry (or an Industry description) to resolve websites."
            )
            # Do not modify the cache; let the caller handle this as a blocking condition
            raise ValueError("Missing market context for website lookup")

        system = "You are a careful web research assistant. Return JSON only."
        strict_system = "Return JSON only."

        def _prompt_for(name: str) -> str:
            parts = [
                f"Find the official website for the company or brand '{name}'.",
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
                "Rules: choose the official brand/company site (not retailers, marketplaces, or associations). "
                "If the site does not clearly belong to this market/industry, return null."
            )
            parts.append('Return JSON {"website": "https://example.com"} where website can be null.')
            return " ".join(parts)

        # Process in small chunks to persist progress incrementally
        CHUNK_SIZE = 20
        it = iter(missing)
        while True:
            chunk = list(islice(it, CHUNK_SIZE))
            if not chunk:
                break
            prompts = [_prompt_for(n) for n in chunk]
            try:
                results = run_step_json(
                    llm_wrapper,
                    merchantBrandWebsiteLookup,
                    system,
                    prompts,
                    tools=[{"type": "web_search_preview"}],
                    tool_choice="required",
                    service_tier=service_tier,
                )
            except Exception as e:
                logger.warning("Website lookup batch failed: %s", e)
                results = [{} for _ in chunk]

            updated = 0
            for n, resp in zip(chunk, results):
                raw_text = None
                website = None
                if isinstance(resp, dict):
                    website = _normalize_website(resp.get("website"))
                    if website is None:
                        raw_text = resp.get("raw") if isinstance(resp.get("raw"), str) else None
                        if raw_text:
                            website = _extract_website_from_text(raw_text)
                elif isinstance(resp, str):
                    raw_text = resp
                    website = _extract_website_from_text(raw_text)

                # Strict JSON enforcement: if still missing but we have text, re-ask
                if website is None and raw_text:
                    try:
                        strict_resp = query_llm_return_json(
                            llm_wrapper,
                            merchantBrandWebsiteLookup,
                            strict_system,
                            (
                                "Extract the official website from the text below. "
                                "Return JSON {\"website\": \"https://example.com\"} "
                                "or {\"website\": null}.\n\nTEXT:\n"
                                + raw_text
                            ),
                            tools=None,
                            tool_choice="none",
                            service_tier=service_tier,
                        )
                        if isinstance(strict_resp, dict):
                            website = _normalize_website(strict_resp.get("website"))
                    except Exception as exc:
                        logger.warning("Strict JSON re-ask failed for %s: %s", n, exc)

                if website:
                    mapping[n] = website
                    updated += 1
                    if n in meta:
                        meta.pop(n, None)
                else:
                    mapping[n] = None
                    meta[n] = {"last_failed": datetime.now(timezone.utc).isoformat()}

            # Save after each chunk so partial results survive interruptions
            _save_mapping(mapping)
            _save_meta(meta)
            logger.info(
                "Resolved %d/%d websites this chunk; cache saved to %s",
                updated,
                len(chunk),
                FILE_PATH,
            )

        # Summarize the whole run
        added = sum(1 for n in missing if mapping.get(n))
        msg = (
            f"Added {added} website entries to {FILE_PATH}"
            if added
            else f"No websites were found for {len(missing)} names."
        )
        logger.info(msg)
        ui.info(msg)
    return mapping


__all__ = ["lookup_websites", "load_mapping", "set_lookup_market_context"]
