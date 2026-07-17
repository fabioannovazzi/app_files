from __future__ import annotations

import json
from contextlib import suppress
from pathlib import Path
from typing import Iterator

import pytest

pytest.importorskip("fastapi")
from fastapi.testclient import (
    TestClient,  # type: ignore  # pylint: disable=wrong-import-position
)

from modules.auth.config import get_auth_config
from modules.auth.google_identity import GoogleUserInfo
from modules.auth.session import create_session_cookie
from modules.pdp.api import app

AUTHORIZED_REVIEW_EMAIL = "reviewer@example.com"


def _enable_auth_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AUTH_ENABLED", "1")
    monkeypatch.setenv("GOOGLE_CLIENT_ID", "dummy-client-id")
    monkeypatch.setenv("AUTH_SESSION_SECRET", "dummy-secret")


def _disable_auth_env(monkeypatch: pytest.MonkeyPatch) -> None:
    for env_var in ("AUTH_ENABLED", "GOOGLE_CLIENT_ID", "AUTH_SESSION_SECRET"):
        monkeypatch.delenv(env_var, raising=False)


def _write_dataset_permissions(path: Path, payload: dict[str, list[str]]) -> Path:
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def _write_download_permissions(path: Path, payload: dict[str, list[str]]) -> Path:
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def _write_site_permissions(path: Path, payload: dict[str, list[str]]) -> Path:
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def _make_authenticated_client(
    monkeypatch: pytest.MonkeyPatch,
    *,
    email: str,
) -> Iterator[TestClient]:
    _enable_auth_env(monkeypatch)
    get_auth_config.cache_clear()
    with TestClient(app) as test_client:
        config = get_auth_config()
        token, _ = create_session_cookie(GoogleUserInfo(email=email), config)
        cookie_header = f"{config.session_cookie_name}={token}"
        test_client.cookies.set(config.session_cookie_name, token, domain="testserver")
        test_client.headers.update({"cookie": cookie_header})
        yield test_client
    get_auth_config.cache_clear()


@pytest.fixture(autouse=True)
def _reset_auth(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    monkeypatch.delenv("APP_PRIVATE_CONFIG_DIR", raising=False)
    yield
    _disable_auth_env(monkeypatch)
    get_auth_config.cache_clear()


@pytest.fixture(autouse=True)
def _reset_sales_dataset_permissions_cache() -> Iterator[None]:
    import modules.pdp.sales_dataset_permissions as permissions_mod

    permissions_mod._load_sales_dataset_permissions.cache_clear()
    yield
    permissions_mod._load_sales_dataset_permissions.cache_clear()


@pytest.fixture(autouse=True)
def _reset_sales_dataset_download_permissions_cache() -> Iterator[None]:
    import modules.pdp.sales_dataset_download_permissions as permissions_mod

    permissions_mod._load_sales_dataset_download_permissions.cache_clear()
    yield
    permissions_mod._load_sales_dataset_download_permissions.cache_clear()


@pytest.fixture(autouse=True)
def _reset_site_permissions_cache() -> Iterator[None]:
    import modules.auth.dependencies as auth_dependencies

    auth_dependencies._get_site_permissions.cache_clear()
    yield
    auth_dependencies._get_site_permissions.cache_clear()


def test_review_page_not_gated_by_sales_dataset_permissions(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    import modules.pdp.sales_dataset_permissions as permissions_mod

    permissions_path = _write_dataset_permissions(
        tmp_path / "sales_dataset_permissions.json",
        {"default": ["default-user@example.com"]},
    )
    site_permissions_path = _write_site_permissions(
        tmp_path / "site_page_permissions.json",
        {"legacy_attribute_analysis": [AUTHORIZED_REVIEW_EMAIL]},
    )
    monkeypatch.setattr(
        permissions_mod, "_SALES_DATASET_PERMISSIONS_FILE", permissions_path
    )
    monkeypatch.setenv("SITE_PAGE_PERMISSIONS_FILE", str(site_permissions_path))

    client_iter = _make_authenticated_client(monkeypatch, email=AUTHORIZED_REVIEW_EMAIL)
    client = next(client_iter)
    try:
        response = client.get("/review/page?lang=en")
        assert response.status_code == 200
    finally:
        with suppress(StopIteration):
            next(client_iter)


def test_review_sales_metrics_requires_sales_dataset_permission(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    import modules.pdp.sales_dataset_permissions as permissions_mod

    permissions_path = _write_dataset_permissions(
        tmp_path / "sales_dataset_permissions.json",
        {"default": ["default-user@example.com"]},
    )
    monkeypatch.setattr(
        permissions_mod, "_SALES_DATASET_PERMISSIONS_FILE", permissions_path
    )

    client_iter = _make_authenticated_client(monkeypatch, email=AUTHORIZED_REVIEW_EMAIL)
    client = next(client_iter)
    try:
        response = client.get(
            "/review/sales/metrics",
            params=[("retailer", "ulta"), ("category", "lipstick")],
        )
        assert response.status_code == 403
    finally:
        with suppress(StopIteration):
            next(client_iter)


def test_review_sales_retailers_requires_sales_dataset_permission(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    import modules.pdp.sales_dataset_permissions as permissions_mod

    permissions_path = _write_dataset_permissions(
        tmp_path / "sales_dataset_permissions.json",
        {"default": ["default-user@example.com"]},
    )
    monkeypatch.setattr(
        permissions_mod, "_SALES_DATASET_PERMISSIONS_FILE", permissions_path
    )

    client_iter = _make_authenticated_client(monkeypatch, email=AUTHORIZED_REVIEW_EMAIL)
    client = next(client_iter)
    try:
        response = client.get("/review/sales/retailers")
        assert response.status_code == 403
    finally:
        with suppress(StopIteration):
            next(client_iter)


def test_review_sales_metrics_requires_authentication_when_auth_enabled(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _enable_auth_env(monkeypatch)
    get_auth_config.cache_clear()
    with TestClient(app) as client:
        response = client.get(
            "/review/sales/metrics",
            params=[("retailer", "ulta"), ("category", "lipstick")],
        )
    assert response.status_code == 401


def test_review_sales_page_route_is_not_found() -> None:
    with TestClient(app) as client:
        response = client.get("/review/sales?lang=en", follow_redirects=False)
    assert response.status_code == 404


def test_review_sales_metrics_honors_dataset_query_permission(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    import modules.pdp.sales_dataset_permissions as permissions_mod

    permissions_path = _write_dataset_permissions(
        tmp_path / "sales_dataset_permissions.json",
        {
            "default": ["default-user@example.com"],
            "kiko": [AUTHORIZED_REVIEW_EMAIL],
        },
    )
    monkeypatch.setattr(
        permissions_mod, "_SALES_DATASET_PERMISSIONS_FILE", permissions_path
    )

    client_iter = _make_authenticated_client(monkeypatch, email=AUTHORIZED_REVIEW_EMAIL)
    client = next(client_iter)
    try:
        default_response = client.get(
            "/review/sales/metrics",
            params=[
                ("retailer", "ulta"),
                ("category", "lipstick"),
                ("dimension", "brand"),
            ],
        )
        assert default_response.status_code == 403

        kiko_response = client.get(
            "/review/sales/metrics",
            params=[
                ("dataset", "kiko"),
                ("retailer", "ulta"),
                ("category", "lipstick"),
                ("dimension", "brand"),
            ],
        )
        assert kiko_response.status_code != 403
    finally:
        with suppress(StopIteration):
            next(client_iter)


def test_review_sales_datasets_lists_only_authorized(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    import modules.pdp.sales_dataset_download_permissions as download_permissions_mod
    import modules.pdp.sales_dataset_permissions as permissions_mod

    permissions_path = _write_dataset_permissions(
        tmp_path / "sales_dataset_permissions.json",
        {
            "default": ["default-user@example.com"],
            "kiko": [AUTHORIZED_REVIEW_EMAIL],
            "us_cosmetics": [AUTHORIZED_REVIEW_EMAIL],
        },
    )
    monkeypatch.setattr(
        permissions_mod, "_SALES_DATASET_PERMISSIONS_FILE", permissions_path
    )
    download_permissions_path = _write_download_permissions(
        tmp_path / "sales_dataset_download_permissions.json",
        {
            "kiko": [AUTHORIZED_REVIEW_EMAIL],
        },
    )
    monkeypatch.setattr(
        download_permissions_mod,
        "_SALES_DATASET_DOWNLOAD_PERMISSIONS_FILE",
        download_permissions_path,
    )

    client_iter = _make_authenticated_client(monkeypatch, email=AUTHORIZED_REVIEW_EMAIL)
    client = next(client_iter)
    try:
        response = client.get("/review/sales/datasets", params=[("dataset", "unknown")])
        assert response.status_code == 200
        payload = response.json()
        assert payload["selected_dataset"] == "us_cosmetics"
        assert [entry["key"] for entry in payload["datasets"]] == [
            "us_cosmetics",
            "kiko",
        ]
        assert payload["datasets"][0]["download_allowed"] is False
        assert payload["datasets"][1]["download_allowed"] is True
    finally:
        with suppress(StopIteration):
            next(client_iter)


def test_review_sales_retailers_are_scoped_to_selected_dataset(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    import polars as pl

    import modules.pdp.api as pdp_api_mod
    import modules.pdp.sales_dataset_permissions as permissions_mod

    permissions_path = _write_dataset_permissions(
        tmp_path / "sales_dataset_permissions.json",
        {
            "kiko": [AUTHORIZED_REVIEW_EMAIL],
            "us_cosmetics": [AUTHORIZED_REVIEW_EMAIL],
        },
    )
    monkeypatch.setattr(
        permissions_mod, "_SALES_DATASET_PERMISSIONS_FILE", permissions_path
    )

    def _fake_sales_data(
        _retailer: str | None, dataset: str | None = None
    ) -> pl.DataFrame:
        if dataset == "kiko":
            return pl.DataFrame({"merchant": ["kiko", "KIKO"]})
        return pl.DataFrame({"merchant": ["ulta", "sephora", "amazon"]})

    monkeypatch.setattr(pdp_api_mod, "load_full_sales_data", _fake_sales_data)

    client_iter = _make_authenticated_client(monkeypatch, email=AUTHORIZED_REVIEW_EMAIL)
    client = next(client_iter)
    try:
        us_response = client.get(
            "/review/sales/retailers", params=[("dataset", "us_cosmetics")]
        )
        assert us_response.status_code == 200
        assert us_response.json()["retailers"] == ["amazon", "sephora", "ulta"]

        kiko_response = client.get(
            "/review/sales/retailers", params=[("dataset", "kiko")]
        )
        assert kiko_response.status_code == 200
        assert kiko_response.json()["retailers"] == ["kiko"]
    finally:
        with suppress(StopIteration):
            next(client_iter)


def test_review_sales_joined_download_requires_dataset_download_permission(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    import modules.pdp.sales_dataset_download_permissions as download_permissions_mod
    import modules.pdp.sales_dataset_permissions as permissions_mod

    permissions_path = _write_dataset_permissions(
        tmp_path / "sales_dataset_permissions.json",
        {"us_cosmetics": [AUTHORIZED_REVIEW_EMAIL]},
    )
    monkeypatch.setattr(
        permissions_mod, "_SALES_DATASET_PERMISSIONS_FILE", permissions_path
    )
    download_permissions_path = _write_download_permissions(
        tmp_path / "sales_dataset_download_permissions.json",
        {"us_cosmetics": ["someone-else@example.com"]},
    )
    monkeypatch.setattr(
        download_permissions_mod,
        "_SALES_DATASET_DOWNLOAD_PERMISSIONS_FILE",
        download_permissions_path,
    )

    client_iter = _make_authenticated_client(monkeypatch, email=AUTHORIZED_REVIEW_EMAIL)
    client = next(client_iter)
    try:
        response = client.get(
            "/review/sales/joined.csv",
            params=[
                ("dataset", "us_cosmetics"),
                ("retailer", "ulta"),
                ("category", "blush"),
            ],
        )
        assert response.status_code == 403
    finally:
        with suppress(StopIteration):
            next(client_iter)


def test_review_sales_metrics_download_requires_dataset_download_permission(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    import modules.pdp.sales_dataset_download_permissions as download_permissions_mod
    import modules.pdp.sales_dataset_permissions as permissions_mod

    permissions_path = _write_dataset_permissions(
        tmp_path / "sales_dataset_permissions.json",
        {"us_cosmetics": [AUTHORIZED_REVIEW_EMAIL]},
    )
    monkeypatch.setattr(
        permissions_mod, "_SALES_DATASET_PERMISSIONS_FILE", permissions_path
    )
    download_permissions_path = _write_download_permissions(
        tmp_path / "sales_dataset_download_permissions.json",
        {"us_cosmetics": ["someone-else@example.com"]},
    )
    monkeypatch.setattr(
        download_permissions_mod,
        "_SALES_DATASET_DOWNLOAD_PERMISSIONS_FILE",
        download_permissions_path,
    )

    client_iter = _make_authenticated_client(monkeypatch, email=AUTHORIZED_REVIEW_EMAIL)
    client = next(client_iter)
    try:
        response = client.get(
            "/review/sales/metrics.csv",
            params=[
                ("dataset", "us_cosmetics"),
                ("retailer", "ulta"),
                ("category", "blush"),
            ],
        )
        assert response.status_code == 403
    finally:
        with suppress(StopIteration):
            next(client_iter)


def test_review_sales_attribute_mapping_download_requires_dataset_download_permission(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    import modules.pdp.sales_dataset_download_permissions as download_permissions_mod
    import modules.pdp.sales_dataset_permissions as permissions_mod

    permissions_path = _write_dataset_permissions(
        tmp_path / "sales_dataset_permissions.json",
        {"us_cosmetics": [AUTHORIZED_REVIEW_EMAIL]},
    )
    monkeypatch.setattr(
        permissions_mod, "_SALES_DATASET_PERMISSIONS_FILE", permissions_path
    )
    download_permissions_path = _write_download_permissions(
        tmp_path / "sales_dataset_download_permissions.json",
        {"us_cosmetics": ["someone-else@example.com"]},
    )
    monkeypatch.setattr(
        download_permissions_mod,
        "_SALES_DATASET_DOWNLOAD_PERMISSIONS_FILE",
        download_permissions_path,
    )

    client_iter = _make_authenticated_client(monkeypatch, email=AUTHORIZED_REVIEW_EMAIL)
    client = next(client_iter)
    try:
        response = client.get(
            "/review/sales/attribute-mapping.csv",
            params=[
                ("dataset", "us_cosmetics"),
                ("retailer", "ulta"),
                ("category", "blush"),
                ("record_type", "parent"),
            ],
        )
        assert response.status_code == 403
    finally:
        with suppress(StopIteration):
            next(client_iter)
