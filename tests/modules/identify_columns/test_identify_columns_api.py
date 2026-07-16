from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient

from modules.identify_columns import api as identify_columns_api
from modules.utilities.config import get_naming_params


def _build_client() -> TestClient:
    app = FastAPI()
    app.include_router(identify_columns_api.router)
    return TestClient(app)


def test_identify_columns_messages_returns_payload() -> None:
    client = _build_client()
    naming = get_naming_params()
    param_dict = {
        naming["monetaryLocalCurrencyColFound"]: True,
        naming["likelyLocalCurrencyValueCols"]: ["Sales"],
    }

    response = client.post(
        "/identify-columns/messages",
        json={"param_dict": param_dict},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["param_dict"][naming["monetaryLocalCurrencyColFound"]] is True
    assert payload["messages"]
    assert payload["messages"][0]["level"] == "success"


def test_identify_cogs_columns_returns_messages() -> None:
    client = _build_client()
    naming = get_naming_params()
    param_dict = {
        naming["cogsColFound"]: True,
        naming["likelyCogsCols"]: ["COGS"],
    }

    response = client.post(
        "/identify-columns/cogs",
        json={"param_dict": param_dict},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["messages"]
    assert "COGS" in payload["messages"][0]["text"]


def test_identify_indirect_costs_columns_returns_messages() -> None:
    client = _build_client()
    naming = get_naming_params()
    param_dict = {
        naming["indirectCostsColFound"]: True,
        naming["likelyIndirectCostsCols"]: ["Indirect Costs"],
    }

    response = client.post(
        "/identify-columns/indirect-costs",
        json={"param_dict": param_dict},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["messages"]
    assert "indirect costs" in payload["messages"][0]["text"].lower()
