"""Hermetic contract tests for the hosted Vera WhatsApp connector."""

from __future__ import annotations

import hashlib
import hmac
import json
import re
import threading
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from modules.auth.session import AuthenticatedUser
from modules.whatsapp_business import api
from modules.whatsapp_business import store as store_module
from modules.whatsapp_business.config import (
    WhatsAppBusinessConfig,
    get_whatsapp_business_config,
)
from modules.whatsapp_business.mcp import (
    MCP_TOOLS,
    McpQueryError,
    parse_search_query,
)
from modules.whatsapp_business.security import (
    OAUTH_SCOPE,
    owner_key_for_email,
    pkce_challenge,
)
from modules.whatsapp_business.store import (
    IncomingWhatsAppMessage,
    OAuthClientRegistrationLimitError,
    WhatsAppBusinessStore,
    WhatsAppBusinessStoreUnavailableError,
)
from modules.whatsapp_business.webhook import parse_whatsapp_webhook

OWNER_EMAIL = "fabio@example.com"
OTHER_EMAIL = "paolo@example.com"
TENANT_SECRET = "tenant-secret-for-tests-0123456789abcdef"
OAUTH_SECRET = "oauth-secret-for-tests-fedcba9876543210"
META_SECRET = "meta-secret-for-tests"
VERIFY_TOKEN = "verify-token-for-tests"
PHONE_NUMBER_ID = "111222333"
WABA_ID = "999888777"
BUSINESS_PHONE = "+390212345678"
CLIENT_PHONE = "+393331112222"


@pytest.fixture
def config() -> WhatsAppBusinessConfig:
    return WhatsAppBusinessConfig(
        base_url="https://mparanza.example",
        resource_url="https://mparanza.example/whatsapp/mcp",
        webhook_verify_token=VERIFY_TOKEN,
        meta_app_secret=META_SECRET,
        tenant_secret=TENANT_SECRET,
        oauth_secret=OAUTH_SECRET,
        retention_days=90,
        access_token_ttl_seconds=3600,
        sqlite_path="",
        allowed_redirect_origins=("https://local.example",),
        allowed_mcp_origins=(),
        setup_allowed_emails=(OWNER_EMAIL,),
        browser_auth_enabled=True,
        openai_apps_challenge_token="openai-domain-challenge-for-tests",
    )


@pytest.fixture
def store(tmp_path: Path) -> WhatsAppBusinessStore:
    return WhatsAppBusinessStore(sqlite_path=tmp_path / "whatsapp.sqlite3")


@pytest.fixture
def user() -> AuthenticatedUser:
    return AuthenticatedUser(email=OWNER_EMAIL, full_name="Fabio")


@pytest.fixture
def app(
    config: WhatsAppBusinessConfig,
    store: WhatsAppBusinessStore,
    user: AuthenticatedUser,
) -> FastAPI:
    instance = FastAPI()
    instance.include_router(api.well_known_router)
    instance.include_router(api.router)
    instance.dependency_overrides[api.get_whatsapp_business_config] = lambda: config
    instance.dependency_overrides[api.get_whatsapp_business_store] = lambda: store
    instance.dependency_overrides[api.get_whatsapp_connector_rate_limiter] = (
        lambda: api.WhatsAppConnectorRateLimiter(
            limits={
                "register": (100, 100),
                "oauth": (100, 100),
                "mcp": (100, 100),
            },
        )
    )
    instance.dependency_overrides[api.require_whatsapp_setup_user] = lambda: user
    return instance


@pytest.fixture
def client(app: FastAPI) -> TestClient:
    return TestClient(app)


def _owner(email: str = OWNER_EMAIL) -> str:
    return owner_key_for_email(email, TENANT_SECRET)


def _account(
    store: WhatsAppBusinessStore,
    *,
    email: str = OWNER_EMAIL,
    phone_number_id: str = PHONE_NUMBER_ID,
):
    return store.upsert_account(
        owner_key=_owner(email),
        waba_id=WABA_ID,
        phone_number_id=phone_number_id,
        display_phone_number=BUSINESS_PHONE,
        label="Studio",
    )


def _message(
    *,
    message_id: str = "wamid.message-1",
    phone_number_id: str = PHONE_NUMBER_ID,
    sender_phone: str = CLIENT_PHONE,
    body: str = "Invio la distinta F24 di giugno.",
    occurred_at: str = "2026-07-23T10:00:00+00:00",
) -> IncomingWhatsAppMessage:
    return IncomingWhatsAppMessage(
        message_id=message_id,
        phone_number_id=phone_number_id,
        sender_phone=sender_phone,
        sender_name="Mario Rossi",
        occurred_at=occurred_at,
        message_type="text",
        body=body,
    )


def _signature(raw_body: bytes) -> str:
    digest = hmac.new(
        META_SECRET.encode("utf-8"),
        raw_body,
        hashlib.sha256,
    ).hexdigest()
    return f"sha256={digest}"


def _webhook_payload() -> dict[str, object]:
    return {
        "object": "whatsapp_business_account",
        "entry": [
            {
                "id": WABA_ID,
                "changes": [
                    {
                        "field": "messages",
                        "value": {
                            "metadata": {
                                "display_phone_number": "390212345678",
                                "phone_number_id": PHONE_NUMBER_ID,
                            },
                            "contacts": [
                                {
                                    "wa_id": CLIENT_PHONE.removeprefix("+"),
                                    "profile": {"name": "Mario Rossi"},
                                }
                            ],
                            "messages": [
                                {
                                    "from": CLIENT_PHONE.removeprefix("+"),
                                    "id": "wamid.message-1",
                                    "timestamp": "1784800800",
                                    "type": "text",
                                    "text": {
                                        "body": "Invio la distinta F24 di giugno."
                                    },
                                }
                            ],
                        },
                    }
                ],
            }
        ],
    }


def _issue_token(
    store: WhatsAppBusinessStore,
    config: WhatsAppBusinessConfig,
    *,
    email: str = OWNER_EMAIL,
) -> str:
    callback = "https://chatgpt.com/connector/oauth/test-connector"
    client = store.register_oauth_client(
        client_name="ChatGPT",
        redirect_uris=(callback,),
    )
    verifier = "v" * 43
    code = store.issue_authorization_code(
        client_id=client.client_id,
        owner_key=_owner(email),
        redirect_uri=callback,
        resource=config.resource_url,
        scope=OAUTH_SCOPE,
        code_challenge=pkce_challenge(verifier),
    )
    assert code is not None
    issued = store.exchange_authorization_code(
        code,
        client_id=client.client_id,
        redirect_uri=callback,
        resource=config.resource_url,
        code_challenge=pkce_challenge(verifier),
        ttl_seconds=3600,
    )
    assert issued is not None
    token, _identity = issued
    return token


def _mcp_call(
    client: TestClient,
    *,
    name: str,
    arguments: dict[str, object],
    token: str | None = None,
) -> dict[str, object]:
    headers = {"Authorization": f"Bearer {token}"} if token else {}
    response = client.post(
        "/whatsapp/mcp",
        headers=headers,
        json={
            "jsonrpc": "2.0",
            "id": 3,
            "method": "tools/call",
            "params": {"name": name, "arguments": arguments},
        },
    )
    assert response.status_code == 200
    return response.json()["result"]


def test_store_deduplicates_and_isolates_messages_by_owner(
    store: WhatsAppBusinessStore,
) -> None:
    account = _account(store)
    other_account = _account(
        store,
        email=OTHER_EMAIL,
        phone_number_id="444555666",
    )

    inserted = store.ingest_messages(account, [_message(), _message()])
    other_inserted = store.ingest_messages(
        other_account,
        [
            _message(
                message_id="wamid.other",
                phone_number_id=other_account.phone_number_id,
                body="Messaggio di Paolo",
            )
        ],
    )

    owner_results = store.search_messages(
        owner_key=account.owner_key,
        phone_number_id=account.phone_number_id,
        client_phone=CLIENT_PHONE,
        terms=("F24",),
        after=None,
        before=None,
        retention_days=90,
    )
    other_results = store.search_messages(
        owner_key=other_account.owner_key,
        phone_number_id=other_account.phone_number_id,
        client_phone=CLIENT_PHONE,
        terms=(),
        after=None,
        before=None,
        retention_days=90,
    )
    cross_tenant_fetch = store.fetch_message(
        owner_key=other_account.owner_key,
        phone_number_id=other_account.phone_number_id,
        source_id=owner_results[0].source_id,
        retention_days=90,
    )

    assert inserted == 1
    assert other_inserted == 1
    assert [item.body for item in owner_results] == ["Invio la distinta F24 di giugno."]
    assert [item.body for item in other_results] == ["Messaggio di Paolo"]
    assert cross_tenant_fetch is None


def test_store_purges_expired_messages_and_deletes_account_data(
    store: WhatsAppBusinessStore,
    config: WhatsAppBusinessConfig,
) -> None:
    account = _account(store)
    old_date = (datetime.now(timezone.utc) - timedelta(days=100)).isoformat()
    store.ingest_messages(account, [_message(occurred_at=old_date)])
    access_token = _issue_token(store, config)
    oauth_client = store.register_oauth_client(
        client_name="Pending ChatGPT",
        redirect_uris=("https://chatgpt.com/connector/oauth/pending",),
    )
    pending_code = store.issue_authorization_code(
        client_id=oauth_client.client_id,
        owner_key=account.owner_key,
        redirect_uri=oauth_client.redirect_uris[0],
        resource=config.resource_url,
        scope=OAUTH_SCOPE,
        code_challenge=pkce_challenge("v" * 43),
    )
    assert pending_code is not None

    purged = store.purge_expired_messages(90)
    deleted = store.delete_account(account.owner_key)

    assert purged == 1
    assert deleted is True
    assert store.get_account_for_owner(account.owner_key) is None
    assert store.resolve_access_token(access_token) is None
    _account(store)
    assert (
        store.exchange_authorization_code(
            pending_code,
            client_id=oauth_client.client_id,
            redirect_uri=oauth_client.redirect_uris[0],
            resource=config.resource_url,
            code_challenge=pkce_challenge("v" * 43),
            ttl_seconds=3600,
        )
        is None
    )


def test_account_deletion_race_cannot_resurrect_oauth_token_after_relink(
    store: WhatsAppBusinessStore,
    config: WhatsAppBusinessConfig,
) -> None:
    account = _account(store)
    callback = "https://chatgpt.com/connector/oauth/race"
    oauth_client = store.register_oauth_client(
        client_name="Race client",
        redirect_uris=(callback,),
    )
    verifier = "r" * 43
    code = store.issue_authorization_code(
        client_id=oauth_client.client_id,
        owner_key=account.owner_key,
        redirect_uri=callback,
        resource=config.resource_url,
        scope=OAUTH_SCOPE,
        code_challenge=pkce_challenge(verifier),
    )
    assert code is not None
    barrier = threading.Barrier(2)
    issued: list[tuple[str, object] | None] = []

    def exchange() -> None:
        barrier.wait()
        issued.append(
            store.exchange_authorization_code(
                code,
                client_id=oauth_client.client_id,
                redirect_uri=callback,
                resource=config.resource_url,
                code_challenge=pkce_challenge(verifier),
                ttl_seconds=3600,
            )
        )

    def delete() -> None:
        barrier.wait()
        store.delete_account(account.owner_key)

    exchange_thread = threading.Thread(target=exchange)
    delete_thread = threading.Thread(target=delete)
    exchange_thread.start()
    delete_thread.start()
    exchange_thread.join(timeout=10)
    delete_thread.join(timeout=10)
    assert not exchange_thread.is_alive()
    assert not delete_thread.is_alive()
    _account(store)

    assert len(issued) == 1
    if issued[0] is not None:
        assert store.resolve_access_token(issued[0][0]) is None
    assert (
        store.exchange_authorization_code(
            code,
            client_id=oauth_client.client_id,
            redirect_uri=callback,
            resource=config.resource_url,
            code_challenge=pkce_challenge(verifier),
            ttl_seconds=3600,
        )
        is None
    )


def test_store_never_returns_expired_messages_before_daily_cleanup(
    store: WhatsAppBusinessStore,
) -> None:
    account = _account(store)
    old_date = (datetime.now(timezone.utc) - timedelta(days=100)).isoformat()
    store.ingest_messages(account, [_message(occurred_at=old_date)])

    retained_for_test = store.search_messages(
        owner_key=account.owner_key,
        phone_number_id=account.phone_number_id,
        client_phone=CLIENT_PHONE,
        terms=(),
        after=None,
        before=None,
        retention_days=1_000,
    )
    search_results = store.search_messages(
        owner_key=account.owner_key,
        phone_number_id=account.phone_number_id,
        client_phone=CLIENT_PHONE,
        terms=(),
        after=None,
        before=None,
        retention_days=90,
    )
    fetched = store.fetch_message(
        owner_key=account.owner_key,
        phone_number_id=account.phone_number_id,
        source_id=retained_for_test[0].source_id,
        retention_days=90,
    )
    purged = store.purge_expired_messages(90)

    assert search_results == []
    assert fetched is None
    assert purged == 1


def test_switching_business_number_clears_old_messages_and_oauth_access(
    store: WhatsAppBusinessStore,
    config: WhatsAppBusinessConfig,
) -> None:
    account = _account(store)
    store.ingest_messages(account, [_message()])
    old_result = store.search_messages(
        owner_key=account.owner_key,
        phone_number_id=account.phone_number_id,
        client_phone=CLIENT_PHONE,
        terms=(),
        after=None,
        before=None,
        retention_days=90,
    )[0]
    access_token = _issue_token(store, config)

    replacement = store.upsert_account(
        owner_key=account.owner_key,
        waba_id="121212121",
        phone_number_id="343434343",
        display_phone_number="+390298765432",
        label="Studio replacement",
    )
    stale_inserted = store.ingest_messages(
        account,
        [_message(message_id="wamid.stale-after-switch")],
    )

    assert stale_inserted == 0
    assert (
        store.fetch_message(
            owner_key=account.owner_key,
            phone_number_id=replacement.phone_number_id,
            source_id=old_result.source_id,
            retention_days=90,
        )
        is None
    )
    assert store.resolve_access_token(access_token) is None


def test_store_requires_explicit_sqlite_when_postgres_is_unavailable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("WHATSAPP_DB_PATH", raising=False)
    monkeypatch.setattr(store_module, "is_postgres_enabled", lambda: False)
    unconfigured = WhatsAppBusinessStore()

    with pytest.raises(WhatsAppBusinessStoreUnavailableError):
        unconfigured.get_account_for_owner(_owner())


@pytest.mark.parametrize(
    ("environment_name", "invalid_value"),
    [
        ("WHATSAPP_RETENTION_DAYS", "91"),
        ("WHATSAPP_OAUTH_ACCESS_TOKEN_TTL_SECONDS", "604801"),
    ],
)
def test_environment_config_rejects_disclosure_breaking_limits(
    monkeypatch: pytest.MonkeyPatch,
    environment_name: str,
    invalid_value: str,
) -> None:
    monkeypatch.setenv(environment_name, invalid_value)
    get_whatsapp_business_config.cache_clear()

    with pytest.raises(ValueError, match=environment_name):
        get_whatsapp_business_config()

    get_whatsapp_business_config.cache_clear()


def test_environment_config_rejects_weak_or_reused_connector_secrets(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("WHATSAPP_TENANT_SECRET", "too-short")
    monkeypatch.setenv("WHATSAPP_OAUTH_SECRET", OAUTH_SECRET)
    get_whatsapp_business_config.cache_clear()

    with pytest.raises(ValueError, match="WHATSAPP_TENANT_SECRET"):
        get_whatsapp_business_config()

    monkeypatch.setenv("WHATSAPP_TENANT_SECRET", TENANT_SECRET)
    monkeypatch.setenv("WHATSAPP_OAUTH_SECRET", TENANT_SECRET)
    get_whatsapp_business_config.cache_clear()

    with pytest.raises(ValueError, match="must be distinct"):
        get_whatsapp_business_config()

    get_whatsapp_business_config.cache_clear()


def test_oauth_client_registry_deduplicates_redirects(
    tmp_path: Path,
) -> None:
    limited_store = WhatsAppBusinessStore(
        sqlite_path=tmp_path / "limited.sqlite3",
        oauth_client_limit=1,
    )
    callback = "https://chatgpt.com/connector/oauth/one"

    first = limited_store.register_oauth_client(
        client_name="ChatGPT",
        redirect_uris=(callback,),
    )
    duplicate = limited_store.register_oauth_client(
        client_name="ChatGPT duplicate",
        redirect_uris=(callback,),
    )

    assert duplicate.client_id == first.client_id


def test_oauth_client_registry_evicts_oldest_unused_registration(
    tmp_path: Path,
) -> None:
    limited_store = WhatsAppBusinessStore(
        sqlite_path=tmp_path / "limited.sqlite3",
        oauth_client_limit=1,
    )
    first = limited_store.register_oauth_client(
        client_name="ChatGPT",
        redirect_uris=("https://chatgpt.com/connector/oauth/one",),
    )

    second = limited_store.register_oauth_client(
        client_name="Another client",
        redirect_uris=("https://chatgpt.com/connector/oauth/two",),
    )

    assert second.client_id != first.client_id
    assert limited_store.get_oauth_client(first.client_id) is None


def test_oauth_client_registry_preserves_registration_with_pending_code(
    tmp_path: Path,
) -> None:
    limited_store = WhatsAppBusinessStore(
        sqlite_path=tmp_path / "limited.sqlite3",
        oauth_client_limit=1,
    )
    callback = "https://chatgpt.com/connector/oauth/one"
    active = limited_store.register_oauth_client(
        client_name="ChatGPT",
        redirect_uris=(callback,),
    )
    account = _account(limited_store)
    code = limited_store.issue_authorization_code(
        client_id=active.client_id,
        owner_key=account.owner_key,
        redirect_uri=callback,
        resource="https://mparanza.example/whatsapp/mcp",
        scope=OAUTH_SCOPE,
        code_challenge=pkce_challenge("v" * 43),
    )
    assert code is not None

    with pytest.raises(OAuthClientRegistrationLimitError):
        limited_store.register_oauth_client(
            client_name="Another client",
            redirect_uris=("https://chatgpt.com/connector/oauth/two",),
        )


def test_whatsapp_connector_rate_limiter_is_bounded() -> None:
    now = [100.0]
    limiter = api.WhatsAppConnectorRateLimiter(
        window_seconds=60,
        limits={"register": (1, 2)},
        clock=lambda: now[0],
    )

    limiter.check("source-a", "register")

    with pytest.raises(api.WhatsAppConnectorRateLimitError):
        limiter.check("source-a", "register")


def test_dcr_rejects_an_oversized_redirect_before_storage(
    client: TestClient,
) -> None:
    response = client.post(
        "/whatsapp/oauth/register",
        json={
            "client_name": "Oversized",
            "redirect_uris": ["https://chatgpt.com/connector/oauth/" + ("x" * 2_050)],
        },
    )

    assert response.status_code == 400
    assert response.json()["error"] == "invalid_client_metadata"
    assert response.headers["cache-control"] == "no-store"


def test_dcr_rejects_fragmented_chatgpt_redirect_uri(
    client: TestClient,
) -> None:
    response = client.post(
        "/whatsapp/oauth/register",
        json={
            "client_name": "Fragmented",
            "redirect_uris": [
                "https://chatgpt.com/connector/oauth/connector-id#attacker"
            ],
        },
    )

    assert response.status_code == 400
    assert response.json()["error"] == "invalid_redirect_uri"


def test_token_endpoint_returns_oauth_error_for_missing_form_fields(
    client: TestClient,
) -> None:
    response = client.post(
        "/whatsapp/oauth/token",
        data={"grant_type": "authorization_code"},
    )

    assert response.status_code == 400
    assert response.json()["error"] == "invalid_request"
    assert response.headers["cache-control"] == "no-store"


def test_dcr_fails_closed_when_oauth_secrets_are_missing(
    app: FastAPI,
    config: WhatsAppBusinessConfig,
) -> None:
    app.dependency_overrides[api.get_whatsapp_business_config] = lambda: replace(
        config,
        tenant_secret="",
        oauth_secret="",
    )
    unconfigured_client = TestClient(app)

    response = unconfigured_client.post(
        "/whatsapp/oauth/register",
        json={
            "client_name": "ChatGPT",
            "redirect_uris": ["https://chatgpt.com/connector/oauth/unconfigured"],
        },
    )

    assert response.status_code == 503


def test_setup_page_is_unframeable_and_disconnect_deletes_live_data(
    client: TestClient,
    store: WhatsAppBusinessStore,
) -> None:
    _account(store)
    page = client.get("/whatsapp/setup")
    token_match = re.search(
        r'action="/whatsapp/setup-delete".*?name="csrf_token" value="([^"]+)"',
        page.text,
        flags=re.DOTALL,
    )
    assert token_match is not None

    disconnected = client.post(
        "/whatsapp/setup-delete",
        data={
            "csrf_token": token_match.group(1),
            "confirmation": "disconnect",
        },
    )

    assert page.status_code == 200
    assert page.headers["x-frame-options"] == "DENY"
    assert "frame-ancestors 'none'" in page.headers["content-security-policy"]
    assert disconnected.status_code == 200
    assert store.get_account_for_owner(_owner()) is None


def test_search_query_requires_exactly_one_e164_client() -> None:
    parsed = parse_search_query(
        'client:+393331112222 after:2026-01-01 before:2026-08-01 "F24 giugno"'
    )

    assert parsed.client_phone == CLIENT_PHONE
    assert parsed.terms == ("F24 giugno",)
    assert parsed.after == "2026-01-01"
    assert parsed.before == "2026-08-01"

    with pytest.raises(McpQueryError, match="Exactly one"):
        parse_search_query("F24 giugno")
    with pytest.raises(McpQueryError, match="Exactly one"):
        parse_search_query("client:+393331112222 client:+393339998888 F24")


def test_parser_ignores_history_groups_location_and_media_bytes() -> None:
    payload = _webhook_payload()
    changes = payload["entry"][0]["changes"]
    changes.extend(
        [
            {"field": "history", "value": {"messages": [{"text": "old"}]}},
            {
                "field": "messages",
                "value": {
                    "metadata": {"phone_number_id": PHONE_NUMBER_ID},
                    "messages": [
                        {
                            "from": CLIENT_PHONE.removeprefix("+"),
                            "id": "wamid.location",
                            "timestamp": "1784800800",
                            "type": "location",
                            "location": {
                                "latitude": 45.0,
                                "longitude": 9.0,
                            },
                        }
                    ],
                },
            },
        ]
    )
    value = changes[0]["value"]
    value["messages"].extend(
        [
            {
                "from": CLIENT_PHONE.removeprefix("+"),
                "group_id": "group-123",
                "id": "wamid.group",
                "timestamp": "1784800801",
                "type": "text",
                "text": {"body": "Group evidence must not be stored."},
            },
            {
                "from_user_id": "bsuid-only-sender",
                "id": "wamid.bsuid",
                "timestamp": "1784800802",
                "type": "text",
                "text": {"body": "No numeric sender is available."},
            },
        ]
    )

    parsed = parse_whatsapp_webhook(payload)
    messages = parsed.messages_by_account[(WABA_ID, PHONE_NUMBER_ID)]

    expected_message_id = "meta_" + hashlib.sha256(b"wamid.message-1").hexdigest()
    assert [message.message_id for message in messages] == [expected_message_id]
    assert messages[0].media_id is None
    assert parsed.ignored_events == 4


def test_parser_minimizes_documents_buttons_and_outbound_echoes() -> None:
    payload = _webhook_payload()
    value = payload["entry"][0]["changes"][0]["value"]
    value["messages"] = [
        {
            "from": CLIENT_PHONE.removeprefix("+"),
            "id": "wamid.document",
            "timestamp": "1784800800",
            "type": "document",
            "document": {
                "id": "sensitive-media-id",
                "filename": "tax-code-secret.pdf",
            },
        },
        {
            "from": CLIENT_PHONE.removeprefix("+"),
            "id": "wamid.button",
            "timestamp": "1784800801",
            "type": "button",
            "button": {"payload": "SECRET_INTERNAL_PAYLOAD"},
        },
        {
            "from": BUSINESS_PHONE.removeprefix("+"),
            "id": "wamid.outbound",
            "timestamp": "1784800802",
            "type": "text",
            "text": {"body": "outbound echo"},
        },
    ]

    parsed = parse_whatsapp_webhook(payload)
    messages = parsed.messages_by_account[(WABA_ID, PHONE_NUMBER_ID)]

    assert [message.body for message in messages] == [
        "[document]",
        "[button reply]",
    ]
    assert all(message.media_id is None for message in messages)
    assert parsed.ignored_events == 1


def test_signed_webhook_rejects_a_mismatched_waba(
    client: TestClient,
    store: WhatsAppBusinessStore,
) -> None:
    _account(store)
    payload = _webhook_payload()
    payload["entry"][0]["id"] = "123123123"
    raw_body = json.dumps(payload, separators=(",", ":")).encode()

    response = client.post(
        "/whatsapp/webhook",
        content=raw_body,
        headers={
            "content-type": "application/json",
            "x-hub-signature-256": _signature(raw_body),
        },
    )

    assert response.status_code == 200
    assert response.json()["stored_messages"] == 0
    assert response.json()["unknown_accounts"] == 1


def test_webhook_verifies_signature_before_ingestion_and_deduplicates(
    client: TestClient,
    store: WhatsAppBusinessStore,
) -> None:
    _account(store)
    raw_body = json.dumps(_webhook_payload(), separators=(",", ":")).encode()

    rejected = client.post(
        "/whatsapp/webhook",
        content=raw_body,
        headers={"content-type": "application/json"},
    )
    first = client.post(
        "/whatsapp/webhook",
        content=raw_body,
        headers={
            "content-type": "application/json",
            "x-hub-signature-256": _signature(raw_body),
        },
    )
    duplicate = client.post(
        "/whatsapp/webhook",
        content=raw_body,
        headers={
            "content-type": "application/json",
            "x-hub-signature-256": _signature(raw_body),
        },
    )

    assert rejected.status_code == 401
    assert first.json()["stored_messages"] == 1
    assert duplicate.json()["stored_messages"] == 0


def test_webhook_verification_uses_constant_token_contract(
    client: TestClient,
) -> None:
    accepted = client.get(
        "/whatsapp/webhook",
        params={
            "hub.mode": "subscribe",
            "hub.verify_token": VERIFY_TOKEN,
            "hub.challenge": "challenge-value",
        },
    )
    rejected = client.get(
        "/whatsapp/webhook",
        params={
            "hub.mode": "subscribe",
            "hub.verify_token": "wrong",
            "hub.challenge": "challenge-value",
        },
    )

    assert accepted.status_code == 200
    assert accepted.text == "challenge-value"
    assert rejected.status_code == 403


def test_oauth_dcr_authorization_code_and_pkce_flow(
    client: TestClient,
    store: WhatsAppBusinessStore,
    user: AuthenticatedUser,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(api, "maybe_current_user", lambda _request: user)
    _account(store)
    callback = "https://chatgpt.com/connector/oauth/connector-id"
    registration = client.post(
        "/whatsapp/oauth/register",
        json={
            "client_name": "ChatGPT",
            "redirect_uris": [callback],
            "token_endpoint_auth_method": "none",
            "grant_types": ["authorization_code"],
            "response_types": ["code"],
        },
    )
    assert registration.status_code == 201
    assert isinstance(registration.json()["client_id_issued_at"], int)
    client_id = registration.json()["client_id"]
    verifier = "p" * 43
    authorize = client.get(
        "/whatsapp/oauth/authorize",
        params={
            "client_id": client_id,
            "redirect_uri": callback,
            "response_type": "code",
            "scope": OAUTH_SCOPE,
            "resource": "https://mparanza.example/whatsapp/mcp",
            "code_challenge": pkce_challenge(verifier),
            "code_challenge_method": "S256",
            "state": "state-123",
        },
    )
    token_match = re.search(
        r'name="consent_token" value="([^"]+)"',
        authorize.text,
    )
    assert token_match is not None
    decision = client.post(
        "/whatsapp/oauth/authorize",
        data={
            "consent_token": token_match.group(1),
            "decision": "allow",
        },
        follow_redirects=False,
    )
    assert decision.status_code == 303, decision.text
    query = parse_qs(urlparse(decision.headers["location"]).query)
    assert "code" in query, decision.headers["location"]
    invalid_verifier_response = client.post(
        "/whatsapp/oauth/token",
        data={
            "grant_type": "authorization_code",
            "code": query["code"][0],
            "client_id": client_id,
            "redirect_uri": callback,
            "code_verifier": "é" * 43,
            "resource": "https://mparanza.example/whatsapp/mcp",
        },
    )
    wrong_verifier_response = client.post(
        "/whatsapp/oauth/token",
        data={
            "grant_type": "authorization_code",
            "code": query["code"][0],
            "client_id": client_id,
            "redirect_uri": callback,
            "code_verifier": "x" * 43,
            "resource": "https://mparanza.example/whatsapp/mcp",
        },
    )
    token_response = client.post(
        "/whatsapp/oauth/token",
        data={
            "grant_type": "authorization_code",
            "code": query["code"][0],
            "client_id": client_id,
            "redirect_uri": callback,
            "code_verifier": verifier,
            "resource": "https://mparanza.example/whatsapp/mcp",
        },
    )

    assert registration.status_code == 201
    assert authorize.status_code == 200
    assert query["state"] == ["state-123"]
    assert invalid_verifier_response.status_code == 400
    assert invalid_verifier_response.json()["error"] == "invalid_grant"
    assert wrong_verifier_response.status_code == 400
    assert wrong_verifier_response.json()["error"] == "invalid_grant"
    assert token_response.status_code == 200
    assert token_response.json()["token_type"] == "Bearer"
    assert store.resolve_access_token(token_response.json()["access_token"]) is not None


def test_oauth_consent_post_does_not_redirect_an_expired_session(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(api, "maybe_current_user", lambda _request: None)

    response = client.post(
        "/whatsapp/oauth/authorize",
        data={"consent_token": "x" * 40, "decision": "allow"},
        follow_redirects=False,
    )

    assert response.status_code == 401
    assert "location" not in response.headers


def test_oauth_cleanup_removes_consumed_codes_and_expired_tokens(
    store: WhatsAppBusinessStore,
    config: WhatsAppBusinessConfig,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    now = [1_000]
    monkeypatch.setattr(store_module.time, "time", lambda: now[0])
    _account(store)
    callback = "https://chatgpt.com/connector/oauth/cleanup"
    oauth_client = store.register_oauth_client(
        client_name="Cleanup client",
        redirect_uris=(callback,),
    )
    verifier = "c" * 43
    code = store.issue_authorization_code(
        client_id=oauth_client.client_id,
        owner_key=_owner(),
        redirect_uri=callback,
        resource=config.resource_url,
        scope=OAUTH_SCOPE,
        code_challenge=pkce_challenge(verifier),
    )
    assert code is not None
    issued = store.exchange_authorization_code(
        code,
        client_id=oauth_client.client_id,
        redirect_uri=callback,
        resource=config.resource_url,
        code_challenge=pkce_challenge(verifier),
        ttl_seconds=300,
    )
    assert issued is not None
    token, _identity = issued
    now[0] = 2_000

    purged = store.purge_expired_oauth_records()

    assert purged == 2
    assert store.resolve_access_token(token) is None


def test_mcp_exposes_only_read_tools_and_requires_oauth(
    client: TestClient,
) -> None:
    initialized = client.post(
        "/whatsapp/mcp",
        json={"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}},
    )
    listed = client.post(
        "/whatsapp/mcp",
        json={"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}},
    )
    unauthorized = _mcp_call(
        client,
        name="search",
        arguments={"query": f"client:{CLIENT_PHONE} F24"},
    )
    tools = listed.json()["result"]["tools"]

    assert initialized.json()["result"]["protocolVersion"] == "2025-06-18"
    assert [tool["name"] for tool in tools] == [
        "whatsapp_account_status",
        "search",
        "fetch",
    ]
    assert tools == MCP_TOOLS
    assert all(tool["annotations"]["readOnlyHint"] is True for tool in tools)
    assert all(tool["annotations"]["destructiveHint"] is False for tool in tools)
    assert all(
        tool["securitySchemes"] == [{"type": "oauth2", "scopes": [OAUTH_SCOPE]}]
        for tool in tools
    )
    assert all(
        tool["_meta"]["securitySchemes"] == tool["securitySchemes"] for tool in tools
    )
    assert all("outputSchema" in tool for tool in tools)
    assert unauthorized["isError"] is True
    assert "mcp/www_authenticate" in unauthorized["_meta"]
    challenge = unauthorized["_meta"]["mcp/www_authenticate"][0]
    assert 'error="invalid_token"' in challenge
    assert 'error_description="Authentication required"' in challenge


def test_mcp_rejects_untrusted_origin_and_protocol_version(
    client: TestClient,
) -> None:
    message = {"jsonrpc": "2.0", "id": 1, "method": "tools/list", "params": {}}

    untrusted = client.post(
        "/whatsapp/mcp",
        headers={"Origin": "https://attacker.example"},
        json=message,
    )
    unsupported = client.post(
        "/whatsapp/mcp",
        headers={"MCP-Protocol-Version": "2099-01-01"},
        json=message,
    )
    trusted = client.post(
        "/whatsapp/mcp",
        headers={
            "Origin": "https://chatgpt.com",
            "MCP-Protocol-Version": "2025-06-18",
        },
        json=message,
    )

    assert untrusted.status_code == 403
    assert unsupported.status_code == 400
    assert trusted.status_code == 200


def test_openai_apps_challenge_uses_deployment_private_token(
    client: TestClient,
    app: FastAPI,
    config: WhatsAppBusinessConfig,
) -> None:
    response = client.get("/.well-known/openai-apps-challenge")
    app.dependency_overrides[api.get_whatsapp_business_config] = lambda: replace(
        config,
        openai_apps_challenge_token="",
    )

    missing = client.get("/.well-known/openai-apps-challenge")

    assert response.status_code == 200
    assert response.text == "openai-domain-challenge-for-tests"
    assert response.headers["cache-control"] == "no-store"
    assert missing.status_code == 404


def test_mcp_account_status_matches_its_closed_output_contract(
    client: TestClient,
    store: WhatsAppBusinessStore,
    config: WhatsAppBusinessConfig,
) -> None:
    _account(store)
    token = _issue_token(store, config)

    result = _mcp_call(
        client,
        name="whatsapp_account_status",
        arguments={},
        token=token,
    )

    assert result["structuredContent"] == {
        "connected": True,
        "setup_url": "https://mparanza.example/whatsapp/setup",
        "account_label": "Studio",
        "business_phone": BUSINESS_PHONE,
        "retention_days": 90,
        "history_imported": False,
        "media_download_enabled": False,
        "send_enabled": False,
    }


def test_mcp_storage_outage_is_not_reported_as_an_auth_failure(
    client: TestClient,
    store: WhatsAppBusinessStore,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def unavailable(_token: str):
        raise WhatsAppBusinessStoreUnavailableError("database unavailable")

    monkeypatch.setattr(store, "resolve_access_token", unavailable)

    response = client.post(
        "/whatsapp/mcp",
        headers={"Authorization": "Bearer invalid-but-present"},
        json={
            "jsonrpc": "2.0",
            "id": 9,
            "method": "tools/call",
            "params": {
                "name": "whatsapp_account_status",
                "arguments": {},
            },
        },
    )

    assert response.status_code == 503
    assert "www-authenticate" not in response.headers
    assert response.json()["result"]["isError"] is True


def test_mcp_search_and_fetch_are_tenant_scoped_and_company_knowledge_shaped(
    client: TestClient,
    store: WhatsAppBusinessStore,
    config: WhatsAppBusinessConfig,
) -> None:
    account = _account(store)
    _account(
        store,
        email=OTHER_EMAIL,
        phone_number_id="777666555",
    )
    store.ingest_messages(account, [_message()])
    token = _issue_token(store, config)
    other_token = _issue_token(store, config, email=OTHER_EMAIL)

    searched = _mcp_call(
        client,
        name="search",
        arguments={"query": f"client:{CLIENT_PHONE} F24"},
        token=token,
    )
    result = searched["structuredContent"]["results"][0]
    fetched = _mcp_call(
        client,
        name="fetch",
        arguments={"id": result["id"]},
        token=token,
    )
    cross_tenant = _mcp_call(
        client,
        name="fetch",
        arguments={"id": result["id"]},
        token=other_token,
    )

    assert set(result) == {"id", "title", "url"}
    assert result["url"] == ""
    assert set(fetched["structuredContent"]) == {
        "id",
        "title",
        "text",
        "url",
        "metadata",
    }
    assert fetched["structuredContent"]["text"] == "Invio la distinta F24 di giugno."
    assert set(fetched["structuredContent"]["metadata"]) == {
        "source",
        "sender_phone",
        "sender_name",
        "occurred_at",
        "message_type",
        "direction",
    }
    assert fetched["content"][0]["text"] == json.dumps(
        fetched["structuredContent"],
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    )
    assert cross_tenant["isError"] is True
    assert "structuredContent" not in cross_tenant
    assert cross_tenant["content"] == [
        {"type": "text", "text": "Unknown WhatsApp source."}
    ]


def test_connector_has_no_send_route_or_tool(
    app: FastAPI,
) -> None:
    route_paths = {route.path for route in app.routes}
    tool_names = {tool["name"] for tool in MCP_TOOLS}

    assert not any("send" in path or "reply" in path for path in route_paths)
    assert not any("send" in name or "reply" in name for name in tool_names)
