from __future__ import annotations

import os

import pytest

from modules.pdp.http_proxies import get_proxies_for_retailer


@pytest.mark.parametrize(
    "env,expected",
    [
        (
            {
                "PDP_SEPHORA_HTTP_PROXY": "http://retailer-http",
                "PDP_SEPHORA_HTTPS_PROXY": "http://retailer-https",
            },
            {"http": "http://retailer-http", "https": "http://retailer-https"},
        ),
        (
            {
                "PDP_SEPHORA_PROXY": "http://retailer-all",
                "PDP_HTTPS_PROXY": "http://global-https",
            },
            {"http": "http://retailer-all", "https": "http://retailer-all"},
        ),
        (
            {
                "PDP_HTTP_PROXY": "http://global-http",
                "PDP_HTTPS_PROXY": "http://global-https",
            },
            {"http": "http://global-http", "https": "http://global-https"},
        ),
    ],
)
def test_get_proxies_for_retailer(env: dict[str, str], expected: dict[str, str], monkeypatch: pytest.MonkeyPatch) -> None:
    for key in list(os.environ):
        if key.startswith("PDP_"):
            monkeypatch.delenv(key, raising=False)

    for key, value in env.items():
        monkeypatch.setenv(key, value)

    proxies = get_proxies_for_retailer("sephora")
    assert proxies == expected
