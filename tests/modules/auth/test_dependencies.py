from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

import pytest
from fastapi import HTTPException
from starlette.requests import Request

from modules.auth import dependencies as auth_dependencies
from modules.auth.config import AuthConfig
from modules.auth.dependencies import (
    get_allowed_page_keys_for_email,
    get_permission_key_for_path,
    require_authenticated_user,
    require_authenticated_user_for_site,
    require_site_permission_for_request,
)
from modules.auth.google_identity import GoogleUserInfo
from modules.auth.session import create_session_cookie


def _config(**overrides) -> AuthConfig:
    base = AuthConfig(
        google_client_id="client",
        google_authorized_origins=(),
        allowed_domains=(),
        allowed_emails=(),
        authentication_enabled=True,
        session_secret="secret",
        session_cookie_name="mp_auth",
        session_ttl_seconds=300,
        cookie_secure=True,
        magic_link_ttl_seconds=900,
        magic_link_default_redirect="/",
    )
    return replace(base, **overrides)


def _request(headers: list[tuple[bytes, bytes]] | None = None) -> Request:
    scope = {
        "type": "http",
        "method": "GET",
        "path": "/",
        "headers": headers or [],
    }
    return Request(scope, receive=lambda: None)


def _request_for_path(
    path: str,
    *,
    headers: list[tuple[bytes, bytes]] | None = None,
    query_string: bytes = b"",
) -> Request:
    scope = {
        "type": "http",
        "method": "GET",
        "path": path,
        "headers": headers or [],
        "query_string": query_string,
    }
    return Request(scope, receive=lambda: None)


def test_require_authenticated_user_no_auth(monkeypatch: pytest.MonkeyPatch) -> None:
    config = _config(authentication_enabled=False, session_secret="")
    monkeypatch.setattr("modules.auth.dependencies.get_auth_config", lambda: config)

    assert require_authenticated_user(_request()) is None


def test_require_authenticated_user_success(monkeypatch: pytest.MonkeyPatch) -> None:
    config = _config()
    monkeypatch.setattr("modules.auth.dependencies.get_auth_config", lambda: config)
    cookie_value, _ = create_session_cookie(
        GoogleUserInfo(email="user@example.com"), config
    )
    request = _request(
        [(b"cookie", f"{config.session_cookie_name}={cookie_value}".encode())]
    )

    user = require_authenticated_user(request)
    assert user is not None
    assert user.email == "user@example.com"


def test_require_authenticated_user_invalid_cookie(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    config = _config()
    monkeypatch.setattr("modules.auth.dependencies.get_auth_config", lambda: config)
    request = _request([(b"cookie", f"{config.session_cookie_name}=invalid".encode())])

    with pytest.raises(HTTPException) as excinfo:
        require_authenticated_user(request)

    assert excinfo.value.status_code == 401


def test_require_authenticated_user_for_site_redirects_to_auth_page(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    config = _config()
    monkeypatch.setattr("modules.auth.dependencies.get_auth_config", lambda: config)
    request = _request_for_path("/slides/page", query_string=b"lang=it")

    with pytest.raises(HTTPException) as excinfo:
        require_authenticated_user_for_site(request)

    assert excinfo.value.status_code == 307
    location = excinfo.value.headers["Location"]
    parsed = urlsplit(location)
    params = parse_qs(parsed.query)
    assert parsed.path == "/auth/page"
    assert params["lang"] == ["it"]
    assert params["redirect"] == ["/slides/page?lang=it"]


def test_get_permission_key_for_path_uses_column_groups(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    structure_file = tmp_path / "permission_structure.json"
    structure_file.write_text(
        json.dumps(
            {
                "attribute_analysis": [
                    "/review/reports",
                    "/review/product-hypotheses",
                ],
                "deck_toolkit": ["/presentations", "/slides"],
                "clara": [
                    "/downloads/clara",
                    "/static/shared/clara/downloads",
                    "/case-notes/voice",
                    "/case-notes/api/voice",
                    "/case-notes/api/attribute-reporting",
                ],
                "private_documents": ["/case-notes/private/"],
                "legacy_attribute_analysis": [
                    "/review/coverage",
                    "/review/explicit-rules",
                    "/review/issues",
                    "/review",
                ],
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(auth_dependencies, "_PERMISSION_STRUCTURE_FILE", structure_file)
    auth_dependencies._get_permission_structure.cache_clear()
    try:
        assert (
            get_permission_key_for_path("/review/page") == "legacy_attribute_analysis"
        )
        assert (
            get_permission_key_for_path("/review/explicit-rules/page")
            == "legacy_attribute_analysis"
        )
        assert (
            get_permission_key_for_path("/review/issues/page")
            == "legacy_attribute_analysis"
        )
        assert (
            get_permission_key_for_path("/review/reports/page") == "attribute_analysis"
        )
        assert (
            get_permission_key_for_path("/review/product-hypotheses/page")
            == "attribute_analysis"
        )
        assert get_permission_key_for_path("/presentations/page") == "deck_toolkit"
        assert get_permission_key_for_path("/slides/page") == "deck_toolkit"
        assert get_permission_key_for_path("/brief/page") is None
        assert get_permission_key_for_path("/check/page") is None
        assert (
            get_permission_key_for_path(
                "/static/shared/deep-research-validator/index.html"
            )
            is None
        )
        assert get_permission_key_for_path("/static/shared/clara/index.html") is None
        assert (
            get_permission_key_for_path(
                "/static/shared/deep-research-validator/downloads/package.zip"
            )
            is None
        )
        assert (
            get_permission_key_for_path("/static/shared/clara/downloads/package.zip")
            == "clara"
        )
        assert get_permission_key_for_path("/downloads/clara") == "clara"
        assert (
            get_permission_key_for_path(
                "/static/shared/distribution-analysis/downloads/package.zip"
            )
            is None
        )
        assert (
            get_permission_key_for_path(
                "/static/shared/period-comparison/downloads/package.zip"
            )
            is None
        )
        assert (
            get_permission_key_for_path(
                "/static/shared/scatter-bubble-analysis/downloads/package.zip"
            )
            is None
        )
        assert (
            get_permission_key_for_path(
                "/static/shared/variance-analysis/downloads/package.zip"
            )
            is None
        )
        assert (
            get_permission_key_for_path(
                "/case-notes/private/example-project/scenario-working-pack"
            )
            == "private_documents"
        )
        assert (
            get_permission_key_for_path("/case-notes/private/another-artifact")
            == "private_documents"
        )
        assert get_permission_key_for_path("/case-notes/private") is None
        assert get_permission_key_for_path("/case-notes/privateproject/page") is None
        assert get_permission_key_for_path("/case-notes/voice") == "clara"
        assert (
            get_permission_key_for_path(
                "/case-notes/api/voice/interviews/example-token/bundle"
            )
            == "clara"
        )
        assert (
            get_permission_key_for_path(
                "/case-notes/api/attribute-reporting/evidence-packs/example-job"
            )
            == "clara"
        )
    finally:
        auth_dependencies._get_permission_structure.cache_clear()


def test_get_allowed_page_keys_for_email_reads_grouped_permissions(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.delenv("APP_PRIVATE_CONFIG_DIR", raising=False)
    monkeypatch.delenv("SITE_PAGE_PERMISSIONS_FILE", raising=False)
    permissions_file = tmp_path / "site_page_permissions.json"
    permissions_file.write_text(
        json.dumps(
            {
                "attribute_analysis": ["analyst@example.com"],
                "deck_toolkit": ["analyst@example.com", "deck@example.com"],
                "clara": ["*"],
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(auth_dependencies, "_SITE_PERMISSIONS_FILE", permissions_file)
    auth_dependencies._get_site_permissions.cache_clear()
    try:
        assert get_allowed_page_keys_for_email("analyst@example.com") == {
            "attribute_analysis",
            "clara",
            "deck_toolkit",
        }
        assert get_allowed_page_keys_for_email("deck@example.com") == {
            "clara",
            "deck_toolkit",
        }
        assert get_allowed_page_keys_for_email("missing@example.com") == {"clara"}
    finally:
        auth_dependencies._get_site_permissions.cache_clear()


def test_require_site_permission_for_request_denies_unconfigured_mapped_page(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.delenv("APP_PRIVATE_CONFIG_DIR", raising=False)
    monkeypatch.delenv("SITE_PAGE_PERMISSIONS_FILE", raising=False)
    config = _config()
    monkeypatch.setattr("modules.auth.dependencies.get_auth_config", lambda: config)

    structure_file = tmp_path / "permission_structure.json"
    structure_file.write_text(
        json.dumps({"attribute_analysis": ["/review/reports"]}),
        encoding="utf-8",
    )
    permissions_file = tmp_path / "site_page_permissions.json"
    permissions_file.write_text(
        json.dumps({"deck_toolkit": ["user@example.com"]}),
        encoding="utf-8",
    )

    monkeypatch.setattr(auth_dependencies, "_PERMISSION_STRUCTURE_FILE", structure_file)
    monkeypatch.setattr(auth_dependencies, "_SITE_PERMISSIONS_FILE", permissions_file)
    auth_dependencies._get_permission_structure.cache_clear()
    auth_dependencies._get_site_permissions.cache_clear()

    cookie_value, _ = create_session_cookie(
        GoogleUserInfo(email="user@example.com"), config
    )
    request = _request_for_path(
        "/review/reports/page",
        headers=[(b"cookie", f"{config.session_cookie_name}={cookie_value}".encode())],
    )

    try:
        with pytest.raises(HTTPException) as excinfo:
            require_site_permission_for_request(request)
        assert excinfo.value.status_code == 403
    finally:
        auth_dependencies._get_permission_structure.cache_clear()
        auth_dependencies._get_site_permissions.cache_clear()


def test_site_permissions_use_private_config_directory(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    private_config_dir = tmp_path / "private-config"
    private_config_dir.mkdir()
    permissions_file = private_config_dir / "site_page_permissions.json"
    permissions_file.write_text(
        json.dumps({"clara": ["person@example.com"]}),
        encoding="utf-8",
    )
    monkeypatch.setenv("APP_PRIVATE_CONFIG_DIR", str(private_config_dir))
    monkeypatch.delenv("SITE_PAGE_PERMISSIONS_FILE", raising=False)
    auth_dependencies._get_site_permissions.cache_clear()

    try:
        permissions = auth_dependencies.get_site_permissions()
        assert permissions == {"clara": {"person@example.com"}}
    finally:
        auth_dependencies._get_site_permissions.cache_clear()


def test_require_site_permission_for_request_fails_closed_without_permissions(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    config = _config()
    monkeypatch.setattr("modules.auth.dependencies.get_auth_config", lambda: config)
    structure_file = tmp_path / "permission_structure.json"
    structure_file.write_text(
        json.dumps({"clara": ["/case-notes/voice"]}),
        encoding="utf-8",
    )
    missing_permissions_file = tmp_path / "missing-site-page-permissions.json"
    monkeypatch.setattr(auth_dependencies, "_PERMISSION_STRUCTURE_FILE", structure_file)
    monkeypatch.setattr(
        auth_dependencies, "_SITE_PERMISSIONS_FILE", missing_permissions_file
    )
    monkeypatch.delenv("APP_PRIVATE_CONFIG_DIR", raising=False)
    monkeypatch.delenv("SITE_PAGE_PERMISSIONS_FILE", raising=False)
    auth_dependencies._get_permission_structure.cache_clear()
    auth_dependencies._get_site_permissions.cache_clear()
    cookie_value, _ = create_session_cookie(
        GoogleUserInfo(email="person@example.com"), config
    )
    request = _request_for_path(
        "/case-notes/voice",
        headers=[(b"cookie", f"{config.session_cookie_name}={cookie_value}".encode())],
    )

    try:
        with pytest.raises(HTTPException) as excinfo:
            require_site_permission_for_request(request)
        assert excinfo.value.status_code == 503
        assert excinfo.value.detail["error"] == "permissions_unavailable"
    finally:
        auth_dependencies._get_permission_structure.cache_clear()
        auth_dependencies._get_site_permissions.cache_clear()
