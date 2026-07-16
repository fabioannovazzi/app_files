from __future__ import annotations

import pytest

pytest.importorskip("fastapi")
from fastapi.testclient import TestClient  # type: ignore  # pylint: disable=wrong-import-position

from modules.auth.config import get_auth_config
from modules.pdp.api import app

client = TestClient(app)


@pytest.fixture(autouse=True)
def _disable_auth_for_taxonomy_governance_api_tests(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    for env_var in ("AUTH_ENABLED", "GOOGLE_CLIENT_ID", "AUTH_SESSION_SECRET"):
        monkeypatch.delenv(env_var, raising=False)
    get_auth_config.cache_clear()
    yield
    get_auth_config.cache_clear()


def test_taxonomy_governance_validate_returns_normalized_config() -> None:
    payload = {
        "categories": [
            {
                "id": "face_primer",
                "label": "Face primer",
                "attributes": [
                    {
                        "id": "form",
                        "label": "Format",
                        "hierarchical": False,
                        "levels": 1,
                        "nodes": [
                            {"id": "liquid", "label": "Liquid"},
                            {
                                "id": "oil",
                                "label": "Oil",
                                "status": "Needs_Review",
                                "governance_action": "merge",
                                "successor_leaf_ids": ["Liquid"],
                                "governance_reason": "Possible subtype of liquid.",
                            },
                        ],
                    }
                ],
            }
        ]
    }

    response = client.post("/review/taxonomy/config/validate", json={"config": payload})

    assert response.status_code == 200
    body = response.json()
    assert body["valid"] is True
    oil_node = body["normalized_config"]["categories"][0]["attributes"][0]["nodes"][1]
    assert oil_node["status"] == "needs_review"
    assert oil_node["governance_action"] == "merge"
    assert oil_node["successor_leaf_ids"] == ["liquid"]
    assert oil_node["governance_reason"] == "Possible subtype of liquid"


def test_taxonomy_governance_page_route_is_registered() -> None:
    page_routes = [
        route
        for route in app.routes
        if getattr(route, "path", "") == "/review/issues/page"
    ]

    assert len(page_routes) == 1
    assert getattr(page_routes[0].endpoint, "__name__", "") == "taxonomy_issues_page"


def test_taxonomy_governance_validate_rejects_split_for_single_select_attribute() -> (
    None
):
    payload = {
        "categories": [
            {
                "id": "lipstick",
                "label": "Lipstick",
                "attributes": [
                    {
                        "id": "finish",
                        "label": "Finish",
                        "hierarchical": False,
                        "levels": 1,
                        "selection": "single",
                        "nodes": [
                            {
                                "id": "matte_dewy",
                                "label": "Matte Dewy",
                                "status": "deprecated",
                                "governance_action": "split",
                                "successor_leaf_ids": ["matte", "dewy"],
                            },
                            {"id": "matte", "label": "Matte"},
                            {"id": "dewy", "label": "Dewy"},
                        ],
                    }
                ],
            }
        ]
    }

    response = client.post("/review/taxonomy/config/validate", json={"config": payload})

    assert response.status_code == 200
    body = response.json()
    assert body["valid"] is False
    assert any("requires selection='multi'" in message for message in body["errors"])


