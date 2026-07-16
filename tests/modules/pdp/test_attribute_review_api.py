from __future__ import annotations

import pytest

pytest.importorskip("fastapi")
from fastapi.testclient import TestClient  # type: ignore  # pylint: disable=wrong-import-position

from modules.auth.config import get_auth_config
from modules.pdp.api import app


client = TestClient(app)


@pytest.fixture(autouse=True)
def _disable_auth_for_review_api_tests(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Keep review API tests deterministic regardless of host auth env vars."""

    for env_var in ("AUTH_ENABLED", "GOOGLE_CLIENT_ID", "AUTH_SESSION_SECRET"):
        monkeypatch.delenv(env_var, raising=False)
    get_auth_config.cache_clear()
    yield
    get_auth_config.cache_clear()


def test_retailer_listing() -> None:
    response = client.get("/review/retailers")
    assert response.status_code == 200
    payload = response.json()
    assert "retailers" in payload
    assert "brands" in payload
    assert any(ret.lower() == "kiko" for ret in payload["retailers"])


def test_category_listing_for_retailer() -> None:
    response = client.get(
        "/review/categories",
        params={"retailer": "kiko"},
    )
    assert response.status_code == 200
    payload = response.json()
    labels = [item["label"].lower() for item in payload["categories"]]
    assert "bronzer" in labels


def test_attribute_metadata_for_category() -> None:
    response = client.get(
        "/review/filters",
        params={"retailer": "kiko", "category": "bronzer"},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["attributes"], "Expected at least one attribute definition"
    attr_ids = {attr["id"] for attr in data["attributes"]}
    assert "form" in attr_ids
    format_attr = next(attr for attr in data["attributes"] if attr["id"] == "form")
    assert 0.0 <= float(format_attr["coverage_pct"]) <= 1.0
    assert int(format_attr["total_records"]) >= 0
    assert int(format_attr["non_placeholder_records"]) >= 0
    assert int(format_attr["total_records"]) >= int(
        format_attr["non_placeholder_records"]
    )
    assert int(format_attr["distinct_non_placeholder_values"]) >= 0


def test_records_endpoint_returns_data() -> None:
    response = client.get(
        "/review/records",
        params={
            "retailer": "kiko",
            "category": "bronzer",
            "record_type": "parent",
            "limit": 5,
        },
    )
    assert response.status_code == 200
    data = response.json()
    assert data["total"] >= len(data["records"])
    assert data["records"], "Expected at least one parent record"
    first = data["records"][0]
    assert "product_name" in first


def test_records_download_returns_unbounded_results() -> None:
    limited = client.get(
        "/review/records",
        params={
            "retailer": "kiko",
            "category": "bronzer",
            "record_type": "parent",
            "limit": 1,
        },
    ).json()

    download = client.get(
        "/review/records/download",
        params={
            "retailer": "kiko",
            "category": "bronzer",
            "record_type": "parent",
        },
    )
    assert download.status_code == 200
    data = download.json()
    assert data["total"] == data["limit"]
    assert data["total"] >= len(limited["records"])
    if data["records"]:
        assert "product_name" in data["records"][0]


def test_records_supports_also_blush_filter() -> None:
    baseline = client.get(
        "/review/records",
        params={
            "retailer": "kiko",
            "category": "bronzer",
            "record_type": "parent",
            "limit": 50,
        },
    )
    assert baseline.status_code == 200
    baseline_payload = baseline.json()

    filtered = client.get(
        "/review/records",
        params={
            "retailer": "kiko",
            "category": "bronzer",
            "record_type": "parent",
            "also_blush": "yes",
            "limit": 50,
        },
    )
    assert filtered.status_code == 200
    filtered_payload = filtered.json()

    assert filtered_payload["total"] <= baseline_payload["total"]
    for record in filtered_payload["records"]:
        assert bool(record.get("also_blush")) is True


def test_stage_debug_endpoint() -> None:
    response = client.get(
        "/review/debug",
        params={
            "table": "pdp_attribute_values",
            "retailer": "kiko",
            "parent": "52958",
        },
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["table"] == "pdp_attribute_values"
    assert "records" in payload


def test_endpoint_accessible_without_token() -> None:
    response = client.get("/review/retailers")
    assert response.status_code == 200
