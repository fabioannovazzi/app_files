from __future__ import annotations

import os
from typing import Mapping

_GLOBAL_ENV_MAP: tuple[tuple[str, str], ...] = (
    ("PDP_ALL_PROXY", "all"),
    ("PDP_HTTP_PROXY", "http"),
    ("PDP_HTTPS_PROXY", "https"),
)


def _retailer_env_keys(retailer: str) -> tuple[tuple[str, str], ...]:
    upper = retailer.upper()
    return (
        (f"PDP_{upper}_PROXY", "all"),
        (f"PDP_{upper}_HTTP_PROXY", "http"),
        (f"PDP_{upper}_HTTPS_PROXY", "https"),
    )


def get_proxies_for_retailer(retailer: str) -> dict[str, str]:
    """Return proxy settings for ``requests`` based on environment variables."""

    proxies: dict[str, str] = {}

    for env, scheme in _retailer_env_keys(retailer):
        value = os.getenv(env)
        if not value:
            continue
        if scheme == "all":
            proxies.setdefault("http", value)
            proxies.setdefault("https", value)
        else:
            proxies[scheme] = value

    for env, scheme in _GLOBAL_ENV_MAP:
        if scheme == "all":
            value = os.getenv(env)
            if not value:
                continue
            proxies.setdefault("http", value)
            proxies.setdefault("https", value)
            continue
        if scheme not in proxies:
            value = os.getenv(env)
            if value:
                proxies[scheme] = value

    # requests honours "all" scheme via "http"/"https"
    return proxies


__all__ = ["get_proxies_for_retailer"]
