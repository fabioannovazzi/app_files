from __future__ import annotations

import logging
from typing import Iterable, List, Tuple, Dict, Any
from urllib.parse import urlparse

__all__ = ["build_web_search_request"]

logger = logging.getLogger(__name__)


def _normalize_domains(domains: Iterable[str]) -> List[str]:
    """Return normalized hostnames suitable for OpenAI domain filters."""

    normalized: List[str] = []
    for raw in domains:
        if not raw:
            continue
        text = str(raw).strip()
        if not text:
            continue
        if "://" not in text:
            candidate = f"http://{text}"
        else:
            candidate = text
        parsed = urlparse(candidate)
        host = parsed.netloc or parsed.path
        host = host.strip().lstrip("/")
        if host:
            normalized.append(host.lower())
    # De-duplicate while preserving order
    seen: set[str] = set()
    unique: List[str] = []
    for host in normalized:
        if host not in seen:
            seen.add(host)
            unique.append(host)
    return unique[:20]


def build_web_search_request(
    domains: Iterable[str] | None,
) -> Tuple[List[dict], Dict[str, Any] | None]:
    """Return a ``tools`` list (and optional ``extra_body``) for web search.

    Follows the OpenAI Responses spec for domain filtering by embedding the
    filter directly in the web_search tool as ``filters.allowed_domains``.
    ``extra_body`` is not required for domain filtering and is therefore
    returned as ``None``.
    """

    normalized = _normalize_domains(domains or [])
    if normalized:
        tools = [
            {"type": "web_search", "filters": {"allowed_domains": normalized}}
        ]
        # Ask the Responses API to include structured sources for audit
        extra_body = {"include": ["web_search_call.action.sources"]}
    else:
        tools = [{"type": "web_search_preview"}]
        extra_body = None

    # Debug visibility only (no UI output)
    logger.debug("Web search request built: tools=%s extra_body=%s", tools, extra_body)

    return tools, extra_body
