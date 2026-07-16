from __future__ import annotations

import json
from urllib.parse import parse_qs, unquote, urlparse

from modules.pdp import kiko_filter_discovery
from modules.pdp.kiko_filter_discovery import (
    crawl_kiko_filter_observations,
    extract_kiko_filter_surfaces,
)


def _category_html() -> str:
    params = {
        "facetFilters": json.dumps([["categories.lvl3:FOUNDATION"]]),
        "facets": json.dumps(["coverage", "finishEffect", "prices.value"]),
        "hitsPerPage": "16",
        "page": "0",
    }
    payload = {
        "props": {
            "pageProps": {
                "serverState": {
                    "initialResults": {
                        "647_en-US": {
                            "results": [
                                {
                                    "hits": [{"objectID": "v1"}],
                                    "index": "647_en-US",
                                    "params": "&".join(
                                        f"{key}={value}"
                                        for key, value in params.items()
                                    ),
                                    "facets": {
                                        "coverage": {"HIGH": 2},
                                        "finishEffect": {"MATTE": 1, "SATIN": 1},
                                        "prices.value": {"20.0": 2},
                                        "averageRating": {"4.5": 2},
                                    },
                                }
                            ]
                        }
                    }
                }
            }
        }
    }
    return (
        '<html><body><script id="__NEXT_DATA__" type="application/json">'
        f"{json.dumps(payload)}"
        "</script></body></html>"
    )


class _FakeResponse:
    status_code = 200

    def __init__(self, hits: list[dict[str, object]]) -> None:
        self._hits = hits

    def json(self) -> dict[str, object]:
        return {
            "results": [
                {
                    "hits": self._hits,
                    "nbPages": 1,
                }
            ]
        }


class _FakeSession:
    def __init__(self) -> None:
        self.requests: list[dict[str, object]] = []

    def post(self, url: str, **kwargs: object) -> _FakeResponse:
        self.requests.append({"url": url, **kwargs})
        body = kwargs["json"]
        request = body["requests"][0]  # type: ignore[index]
        params = parse_qs(str(request["params"]))  # type: ignore[index]
        filters = json.loads(unquote(params["facetFilters"][0]))
        flattened = {item[0] for item in filters if isinstance(item, list) and item}
        if "finishEffect:MATTE" in flattened:
            return _FakeResponse([{"objectID": "v1", "slug": "matte-product"}])
        if "finishEffect:SATIN" in flattened:
            return _FakeResponse([{"code": "backend-v2", "slug": "satin-product"}])
        if "coverage:HIGH" in flattened:
            return _FakeResponse(
                [{"baseBackendId": "backend-parent", "slug": "coverage-product"}]
            )
        return _FakeResponse([])


def test_extract_kiko_filter_surfaces_keeps_only_semantic_facets() -> None:
    surfaces = extract_kiko_filter_surfaces(
        category_url="https://www.kikocosmetics.com/en-us/c/make-up/face/foundations/",
        html=_category_html(),
        category_key="foundation",
    )

    assert [(item.filter_family, item.filter_value) for item in surfaces] == [
        ("coverage", "full"),
        ("finish", "matte"),
        ("finish", "satin"),
    ]
    assert all("kiko-filter=" in item.filter_url for item in surfaces)


def test_crawl_kiko_filter_observations_maps_variant_hits_to_parent_ids(
    monkeypatch,
) -> None:
    monkeypatch.setattr(
        kiko_filter_discovery,
        "KIKO_ALGOLIA_API_KEY",
        "configured-via-environment",
    )
    session = _FakeSession()
    observations = crawl_kiko_filter_observations(
        category_url="https://www.kikocosmetics.com/en-us/c/make-up/face/foundations/",
        html=_category_html(),
        category_key="foundation",
        variant_parent_lookup={
            "v1": ("p1",),
            "backend-v2": ("p2",),
            "backend-parent": ("p3",),
        },
        session=session,  # type: ignore[arg-type]
    )

    assert {
        (item.parent_product_id, item.filter_family, item.filter_value)
        for item in observations
    } == {
        ("p1", "finish", "matte"),
        ("p2", "finish", "satin"),
        ("p3", "coverage", "full"),
    }
    assert urlparse(observations[0].pdp_url or "").path.startswith("/en-us/p/")


def test_crawl_kiko_filter_observations_skips_request_without_env_key(
    monkeypatch,
) -> None:
    monkeypatch.setattr(kiko_filter_discovery, "KIKO_ALGOLIA_API_KEY", "")
    session = _FakeSession()

    observations = crawl_kiko_filter_observations(
        category_url="https://www.kikocosmetics.com/en-us/c/make-up/face/foundations/",
        html=_category_html(),
        category_key="foundation",
        variant_parent_lookup={"v1": ("p1",)},
        session=session,  # type: ignore[arg-type]
    )

    assert observations == []
    assert session.requests == []
