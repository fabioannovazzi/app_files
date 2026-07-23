"""FastAPI routes for WhatsApp webhooks, OAuth, setup, and hosted MCP."""

from __future__ import annotations

import hmac
import html
import json
import threading
import time
from collections import OrderedDict, deque
from collections.abc import Callable, Coroutine
from functools import lru_cache
from typing import Annotated, Any, Literal
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse

from fastapi import (
    APIRouter,
    Depends,
    Form,
    HTTPException,
    Query,
    Request,
    Response,
    status,
)
from fastapi.responses import (
    HTMLResponse,
    JSONResponse,
    PlainTextResponse,
    RedirectResponse,
)
from fastapi.routing import APIRoute
from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator

from modules.auth.dependencies import maybe_current_user
from modules.auth.session import AuthenticatedUser
from modules.whatsapp_business.config import (
    WhatsAppBusinessConfig,
    get_whatsapp_business_config,
)
from modules.whatsapp_business.mcp import (
    MCP_PROTOCOL_VERSION,
    MCP_SERVER_INFO,
    MCP_TOOLS,
    call_tool,
)
from modules.whatsapp_business.security import (
    OAUTH_SCOPE,
    build_consent_token,
    build_www_authenticate,
    is_allowed_mcp_origin,
    is_allowed_redirect_uri,
    is_valid_pkce_verifier,
    normalize_phone_number,
    owner_key_for_email,
    pkce_challenge,
    verify_consent_token,
    verify_meta_signature,
)
from modules.whatsapp_business.store import (
    OAuthClientRegistrationLimitError,
    OAuthIdentity,
    WhatsAppBusinessStore,
    WhatsAppBusinessStoreUnavailableError,
    get_whatsapp_business_store,
)
from modules.whatsapp_business.webhook import parse_whatsapp_webhook

__all__ = [
    "MAX_WHATSAPP_REQUEST_BODY_BYTES",
    "WhatsAppConnectorRateLimitError",
    "WhatsAppConnectorRateLimiter",
    "get_whatsapp_business_config",
    "get_whatsapp_connector_rate_limiter",
    "get_whatsapp_business_store",
    "require_whatsapp_setup_user",
    "router",
    "well_known_router",
]

MAX_WHATSAPP_REQUEST_BODY_BYTES = 1024 * 1024
_AUTHORIZATION_CODE_TTL_SECONDS = 5 * 60
_PKCE_VERIFIER_MIN_LENGTH = 43
_PKCE_VERIFIER_MAX_LENGTH = 128
_RATE_LIMIT_WINDOW_SECONDS = 60.0
_MAX_RATE_LIMIT_SOURCES = 4_096
_MCP_PROTOCOL_HEADER = "MCP-Protocol-Version"
_RATE_LIMITS = {
    "register": (10, 100),
    "oauth": (60, 600),
    "mcp": (120, 1_200),
}
_SENSITIVE_HTML_HEADERS = {
    "Content-Security-Policy": (
        "base-uri 'none'; frame-ancestors 'none'; form-action 'self'"
    ),
    "X-Frame-Options": "DENY",
    "Referrer-Policy": "no-referrer",
    "X-Content-Type-Options": "nosniff",
}


class WhatsAppConnectorRateLimitError(RuntimeError):
    """Raised when one hosted connector surface exceeds its fixed quota."""

    def __init__(self, retry_after_seconds: int) -> None:
        super().__init__("WhatsApp connector rate limit exceeded.")
        self.retry_after_seconds = retry_after_seconds


class WhatsAppConnectorRateLimiter:
    """Bound public connector requests with mechanically auditable quotas."""

    def __init__(
        self,
        *,
        window_seconds: float = _RATE_LIMIT_WINDOW_SECONDS,
        limits: dict[str, tuple[int, int]] | None = None,
        max_sources: int = _MAX_RATE_LIMIT_SOURCES,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._window_seconds = max(float(window_seconds), 1.0)
        configured_limits = limits or _RATE_LIMITS
        self._limits = {
            action: (max(int(values[0]), 1), max(int(values[1]), 1))
            for action, values in configured_limits.items()
        }
        self._max_sources = max(int(max_sources), 1)
        self._clock = clock
        self._source_events: OrderedDict[tuple[str, str], deque[float]] = OrderedDict()
        self._global_events = {action: deque() for action in self._limits}
        self._lock = threading.Lock()

    def check(self, source: str, action: str) -> None:
        """Admit one request or raise with a bounded retry interval."""

        per_source_limit, global_limit = self._limits[action]
        now = self._clock()
        cutoff = now - self._window_seconds
        source_key = (source or "unknown", action)
        with self._lock:
            global_events = self._global_events[action]
            while global_events and global_events[0] <= cutoff:
                global_events.popleft()
            source_events = self._source_events.get(source_key)
            if source_events is None:
                if len(self._source_events) >= self._max_sources:
                    self._source_events.popitem(last=False)
                source_events = deque()
                self._source_events[source_key] = source_events
            else:
                self._source_events.move_to_end(source_key)
            while source_events and source_events[0] <= cutoff:
                source_events.popleft()
            if (
                len(source_events) >= per_source_limit
                or len(global_events) >= global_limit
            ):
                raise WhatsAppConnectorRateLimitError(int(self._window_seconds))
            source_events.append(now)
            global_events.append(now)


@lru_cache(maxsize=1)
def get_whatsapp_connector_rate_limiter() -> WhatsAppConnectorRateLimiter:
    """Return the process-wide hosted connector rate limiter."""

    return WhatsAppConnectorRateLimiter()


class _BoundedWhatsAppRoute(APIRoute):
    """Reject oversized webhook and MCP bodies before parsing."""

    def get_route_handler(
        self,
    ) -> Callable[[Request], Coroutine[Any, Any, Response]]:
        original_handler = super().get_route_handler()

        async def bounded_handler(request: Request) -> Response:
            if request.method in {"POST", "PUT", "PATCH"}:
                raw_length = request.headers.get("content-length")
                if raw_length:
                    try:
                        declared_length = int(raw_length)
                    except ValueError as exc:
                        raise HTTPException(
                            status_code=status.HTTP_400_BAD_REQUEST,
                            detail="Invalid Content-Length header.",
                        ) from exc
                    if (
                        declared_length < 0
                        or declared_length > MAX_WHATSAPP_REQUEST_BODY_BYTES
                    ):
                        raise HTTPException(
                            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                            detail="WhatsApp connector request is too large.",
                        )
                body = bytearray()
                async for chunk in request.stream():
                    body.extend(chunk)
                    if len(body) > MAX_WHATSAPP_REQUEST_BODY_BYTES:
                        raise HTTPException(
                            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                            detail="WhatsApp connector request is too large.",
                        )
                setattr(request, "_body", bytes(body))
            response = await original_handler(request)
            response.headers["Cache-Control"] = "no-store"
            return response

        return bounded_handler


router = APIRouter(
    prefix="/whatsapp",
    tags=["whatsapp-business"],
    route_class=_BoundedWhatsAppRoute,
)
well_known_router = APIRouter(tags=["whatsapp-business-oauth"])
Store = Annotated[WhatsAppBusinessStore, Depends(get_whatsapp_business_store)]
Config = Annotated[WhatsAppBusinessConfig, Depends(get_whatsapp_business_config)]
ConnectorRateLimiter = Annotated[
    WhatsAppConnectorRateLimiter,
    Depends(get_whatsapp_connector_rate_limiter),
]


def _enforce_rate_limit(
    request: Request,
    rate_limiter: WhatsAppConnectorRateLimiter,
    action: str,
) -> None:
    source = request.client.host if request.client is not None else "unknown"
    try:
        rate_limiter.check(source, action)
    except WhatsAppConnectorRateLimitError as exc:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="WhatsApp connector rate limit exceeded.",
            headers={"Retry-After": str(exc.retry_after_seconds)},
        ) from exc


def require_whatsapp_setup_user(
    request: Request,
    config: Config,
) -> AuthenticatedUser:
    """Require a Google-authenticated operator explicitly allowed for setup."""

    user = maybe_current_user(request)
    if user is None or user.email.lower() not in set(config.setup_allowed_emails):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="WhatsApp Business setup is not enabled for this account.",
        )
    return user


SetupUser = Annotated[AuthenticatedUser, Depends(require_whatsapp_setup_user)]


class WhatsAppAccountSetup(BaseModel):
    """Meta identifiers for one operator-verified WhatsApp Business account."""

    model_config = ConfigDict(extra="forbid")

    waba_id: str = Field(min_length=3, max_length=128, pattern=r"^[0-9]+$")
    phone_number_id: str = Field(min_length=3, max_length=128, pattern=r"^[0-9]+$")
    display_phone_number: str = Field(min_length=8, max_length=32)
    label: str = Field(min_length=1, max_length=120)

    @field_validator("display_phone_number")
    @classmethod
    def _normalize_display_phone(cls, value: str) -> str:
        return normalize_phone_number(value)

    @field_validator("label")
    @classmethod
    def _clean_label(cls, value: str) -> str:
        cleaned = " ".join(value.split())
        if not cleaned:
            raise ValueError("label is required.")
        return cleaned


class WhatsAppAccountResponse(BaseModel):
    """Safe account metadata; Meta secrets are never accepted or returned."""

    connected: bool
    waba_id: str
    phone_number_id: str
    display_phone_number: str
    label: str
    retention_days: int
    history_imported: Literal[False] = False
    media_download_enabled: Literal[False] = False
    send_enabled: Literal[False] = False


class OAuthClientRegistration(BaseModel):
    """Supported Dynamic Client Registration fields."""

    model_config = ConfigDict(extra="ignore")

    redirect_uris: list[Annotated[str, Field(min_length=8, max_length=2_048)]] = Field(
        min_length=1, max_length=4
    )
    client_name: str = Field(default="ChatGPT", min_length=1, max_length=200)
    token_endpoint_auth_method: Literal["none"] = "none"
    grant_types: list[str] = Field(default_factory=lambda: ["authorization_code"])
    response_types: list[str] = Field(default_factory=lambda: ["code"])


class OAuthTokenExchange(BaseModel):
    """Validated authorization-code token request."""

    model_config = ConfigDict(extra="forbid")

    grant_type: str = Field(min_length=1, max_length=100)
    code: str = Field(min_length=20, max_length=500)
    client_id: str = Field(min_length=10, max_length=500)
    redirect_uri: str = Field(min_length=8, max_length=2_000)
    code_verifier: str = Field(
        min_length=_PKCE_VERIFIER_MIN_LENGTH,
        max_length=_PKCE_VERIFIER_MAX_LENGTH,
    )
    resource: str = Field(min_length=8, max_length=2_000)


def _store_http_error(exc: WhatsAppBusinessStoreUnavailableError) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        detail=str(exc),
    )


def _require_connector_secret(
    value: str,
    *,
    label: str,
    minimum_bytes: int = 1,
) -> None:
    if not value or len(value.encode("utf-8")) < minimum_bytes:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"{label} is not securely configured.",
        )


def _require_oauth_configuration(config: WhatsAppBusinessConfig) -> None:
    if not config.browser_auth_enabled:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Mparanza browser authentication is not enabled.",
        )
    _require_connector_secret(
        config.tenant_secret,
        label="WhatsApp tenant isolation",
        minimum_bytes=32,
    )
    _require_connector_secret(
        config.oauth_secret,
        label="WhatsApp OAuth signing",
        minimum_bytes=32,
    )
    if config.tenant_secret == config.oauth_secret:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="WhatsApp tenant and OAuth secrets must be distinct.",
        )


def _owner_key(user: AuthenticatedUser, config: WhatsAppBusinessConfig) -> str:
    try:
        return owner_key_for_email(user.email, config.tenant_secret)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=str(exc),
        ) from exc


def _setup_action_token(
    *,
    action: str,
    user: AuthenticatedUser,
    config: WhatsAppBusinessConfig,
) -> str:
    _require_oauth_configuration(config)
    try:
        return build_consent_token(
            {"action": action},
            owner_key=_owner_key(user, config),
            secret=config.oauth_secret,
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=str(exc),
        ) from exc


def _verify_setup_action_token(
    token: str,
    *,
    action: str,
    user: AuthenticatedUser,
    config: WhatsAppBusinessConfig,
) -> None:
    parameters = verify_consent_token(
        token,
        owner_key=_owner_key(user, config),
        secret=config.oauth_secret,
    )
    if parameters != {"action": action}:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Setup request is invalid or expired.",
        )


@router.get("/setup", response_class=HTMLResponse, include_in_schema=False)
def whatsapp_setup_page(
    user: SetupUser,
    store: Store,
    config: Config,
) -> HTMLResponse:
    """Show the deliberately limited first-step connection instructions."""

    try:
        account = store.get_account_for_owner(_owner_key(user, config))
    except WhatsAppBusinessStoreUnavailableError as exc:
        raise _store_http_error(exc) from exc
    link_token = _setup_action_token(
        action="link-account",
        user=user,
        config=config,
    )
    account_section = ""
    if account is not None:
        delete_token = _setup_action_token(
            action="delete-account",
            user=user,
            config=config,
        )
        account_section = f"""
<h2>Current link</h2>
<p>{html.escape(account.label)} · {html.escape(account.display_phone_number)}</p>
<form method="post" action="/whatsapp/setup-delete">
<input type="hidden" name="csrf_token" value="{html.escape(delete_token)}">
<label><input type="checkbox" name="confirmation" value="disconnect" required>
I understand that disconnecting deletes live messages and access tokens.</label><br><br>
<button type="submit">Disconnect and delete live data</button>
</form>"""
    return HTMLResponse(
        f"""<!doctype html>
<html lang="en">
<head><meta charset="utf-8"><meta name="viewport" content="width=device-width">
<title>Vera · WhatsApp Business setup</title></head>
<body style="max-width:720px;margin:48px auto;padding:0 20px;font-family:system-ui">
<h1>Vera · WhatsApp Business</h1>
<p>Signed in as {html.escape(user.email)}.</p>
<p>This first version links one official WhatsApp Business Cloud API number.
It captures only new inbound messages after connection. It does not import
history, download media, or send replies. Messages are deleted after
{config.retention_days} days.</p>
<p>Meta App Review, Business verification, webhook subscription, and the
identifiers below must be completed by the operator before this form is used.</p>
{account_section}
<h2>Link verified identifiers</h2>
<form method="post" action="/whatsapp/setup-form">
<input type="hidden" name="csrf_token" value="{html.escape(link_token)}">
<label>WABA ID<br><input name="waba_id" required pattern="[0-9]+"></label><br><br>
<label>Phone-number ID<br><input name="phone_number_id" required pattern="[0-9]+"></label><br><br>
<label>Business phone (E.164)<br><input name="display_phone_number"
required placeholder="+390212345678"></label><br><br>
<label>Label<br><input name="label" required placeholder="Studio"></label><br><br>
<button type="submit">Link verified identifiers</button>
</form>
</body></html>""",
        headers=_SENSITIVE_HTML_HEADERS,
    )


@router.post("/setup-form", include_in_schema=False)
def whatsapp_setup_form(
    user: SetupUser,
    store: Store,
    config: Config,
    waba_id: Annotated[str, Form()],
    phone_number_id: Annotated[str, Form()],
    display_phone_number: Annotated[str, Form()],
    label: Annotated[str, Form()],
    csrf_token: Annotated[str, Form(min_length=20, max_length=8_000)],
) -> HTMLResponse:
    """Handle the operator setup form without accepting Meta credentials."""

    _verify_setup_action_token(
        csrf_token,
        action="link-account",
        user=user,
        config=config,
    )
    try:
        payload = WhatsAppAccountSetup(
            waba_id=waba_id,
            phone_number_id=phone_number_id,
            display_phone_number=display_phone_number,
            label=label,
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(exc),
        ) from exc
    _upsert_account(user=user, payload=payload, store=store, config=config)
    return HTMLResponse(
        "<!doctype html><html><body><p>WhatsApp Business identifiers linked.</p>"
        '<p><a href="/whatsapp/setup">Back to setup</a></p></body></html>',
        headers=_SENSITIVE_HTML_HEADERS,
    )


@router.post("/setup-delete", include_in_schema=False)
def whatsapp_setup_delete(
    user: SetupUser,
    store: Store,
    config: Config,
    csrf_token: Annotated[str, Form(min_length=20, max_length=8_000)],
    confirmation: Annotated[Literal["disconnect"], Form()],
) -> HTMLResponse:
    """Disconnect the current account and delete its live connector data."""

    del confirmation
    _verify_setup_action_token(
        csrf_token,
        action="delete-account",
        user=user,
        config=config,
    )
    try:
        store.delete_account(_owner_key(user, config))
    except WhatsAppBusinessStoreUnavailableError as exc:
        raise _store_http_error(exc) from exc
    return HTMLResponse(
        "<!doctype html><html><body><p>WhatsApp Business disconnected. "
        "Live messages and access tokens were deleted.</p>"
        '<p><a href="/whatsapp/setup">Back to setup</a></p></body></html>',
        headers=_SENSITIVE_HTML_HEADERS,
    )


def _upsert_account(
    *,
    user: AuthenticatedUser,
    payload: WhatsAppAccountSetup,
    store: WhatsAppBusinessStore,
    config: WhatsAppBusinessConfig,
) -> WhatsAppAccountResponse:
    try:
        account = store.upsert_account(
            owner_key=_owner_key(user, config),
            waba_id=payload.waba_id,
            phone_number_id=payload.phone_number_id,
            display_phone_number=payload.display_phone_number,
            label=payload.label,
        )
    except WhatsAppBusinessStoreUnavailableError as exc:
        raise _store_http_error(exc) from exc
    return WhatsAppAccountResponse(
        connected=True,
        waba_id=account.waba_id,
        phone_number_id=account.phone_number_id,
        display_phone_number=account.display_phone_number,
        label=account.label,
        retention_days=config.retention_days,
    )


@router.put("/api/account", response_model=WhatsAppAccountResponse)
def upsert_whatsapp_account(
    payload: WhatsAppAccountSetup,
    user: SetupUser,
    store: Store,
    config: Config,
) -> WhatsAppAccountResponse:
    """Link operator-verified identifiers without collecting Meta tokens."""

    return _upsert_account(user=user, payload=payload, store=store, config=config)


@router.get("/api/account", response_model=WhatsAppAccountResponse)
def get_whatsapp_account(
    user: SetupUser,
    store: Store,
    config: Config,
) -> WhatsAppAccountResponse:
    """Return the current operator's safe account metadata."""

    try:
        account = store.get_account_for_owner(_owner_key(user, config))
    except WhatsAppBusinessStoreUnavailableError as exc:
        raise _store_http_error(exc) from exc
    if account is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No WhatsApp Business account is linked.",
        )
    return WhatsAppAccountResponse(
        connected=True,
        waba_id=account.waba_id,
        phone_number_id=account.phone_number_id,
        display_phone_number=account.display_phone_number,
        label=account.label,
        retention_days=config.retention_days,
    )


@router.delete("/api/account", status_code=status.HTTP_204_NO_CONTENT)
def delete_whatsapp_account(
    user: SetupUser,
    store: Store,
    config: Config,
) -> Response:
    """Delete the linked account, stored messages, and bearer tokens."""

    try:
        store.delete_account(_owner_key(user, config))
    except WhatsAppBusinessStoreUnavailableError as exc:
        raise _store_http_error(exc) from exc
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/webhook", response_class=PlainTextResponse)
def verify_whatsapp_webhook(
    mode: Annotated[str, Query(alias="hub.mode")],
    verify_token: Annotated[str, Query(alias="hub.verify_token")],
    challenge: Annotated[str, Query(alias="hub.challenge")],
    config: Config,
) -> PlainTextResponse:
    """Complete Meta's webhook verification handshake."""

    _require_connector_secret(
        config.webhook_verify_token,
        label="WhatsApp webhook verification",
    )
    if mode != "subscribe" or not hmac.compare_digest(
        verify_token,
        config.webhook_verify_token,
    ):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Webhook verification failed.",
        )
    return PlainTextResponse(challenge)


@router.post("/webhook")
async def ingest_whatsapp_webhook(
    request: Request,
    store: Store,
    config: Config,
) -> dict[str, int | bool]:
    """Verify and ingest normalized new inbound Meta messages."""

    _require_connector_secret(config.meta_app_secret, label="Meta App Secret")
    raw_body = await request.body()
    signature = request.headers.get("x-hub-signature-256", "")
    if not verify_meta_signature(raw_body, signature, config.meta_app_secret):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid Meta webhook signature.",
        )
    try:
        payload = json.loads(raw_body)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid Meta webhook JSON.",
        ) from exc
    parsed = parse_whatsapp_webhook(payload)
    inserted = 0
    unknown_accounts = 0
    try:
        for (waba_id, phone_number_id), messages in parsed.messages_by_account.items():
            account = store.get_account_for_meta_ids(
                waba_id=waba_id,
                phone_number_id=phone_number_id,
            )
            if account is None:
                unknown_accounts += 1
                continue
            inserted += store.ingest_messages(account, messages)
        store.purge_expired_messages(config.retention_days)
    except WhatsAppBusinessStoreUnavailableError as exc:
        raise _store_http_error(exc) from exc
    return {
        "accepted": True,
        "stored_messages": inserted,
        "ignored_events": parsed.ignored_events,
        "unknown_accounts": unknown_accounts,
    }


@router.get("/.well-known/oauth-protected-resource")
@well_known_router.get("/.well-known/oauth-protected-resource")
def oauth_protected_resource_metadata(config: Config) -> dict[str, Any]:
    """Publish RFC 9728 metadata for ChatGPT."""

    return {
        "resource": config.resource_url,
        "authorization_servers": [config.issuer_url],
        "scopes_supported": [OAUTH_SCOPE],
        "resource_documentation": f"{config.base_url}/privacy",
    }


@router.get("/.well-known/oauth-authorization-server")
@well_known_router.get("/.well-known/oauth-authorization-server")
def oauth_authorization_server_metadata(config: Config) -> dict[str, Any]:
    """Publish the DCR + authorization-code + PKCE contract."""

    return {
        "issuer": config.issuer_url,
        "authorization_endpoint": config.authorization_endpoint,
        "token_endpoint": config.token_endpoint,
        "registration_endpoint": config.registration_endpoint,
        "token_endpoint_auth_methods_supported": ["none"],
        "grant_types_supported": ["authorization_code"],
        "response_types_supported": ["code"],
        "code_challenge_methods_supported": ["S256"],
        "scopes_supported": [OAUTH_SCOPE],
    }


@well_known_router.get(
    "/.well-known/openai-apps-challenge",
    response_class=PlainTextResponse,
    include_in_schema=False,
)
def openai_apps_challenge(config: Config) -> PlainTextResponse:
    """Return the deployment-private OpenAI domain-verification token."""

    token = config.openai_apps_challenge_token
    if not token:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)
    return PlainTextResponse(
        token,
        headers={"Cache-Control": "no-store"},
    )


def _dcr_error(error: str, description: str) -> JSONResponse:
    return JSONResponse(
        status_code=status.HTTP_400_BAD_REQUEST,
        content={"error": error, "error_description": description},
        headers={"Cache-Control": "no-store", "Pragma": "no-cache"},
    )


@router.post("/oauth/register", status_code=status.HTTP_201_CREATED)
async def register_oauth_client(
    request: Request,
    store: Store,
    rate_limiter: ConnectorRateLimiter,
    config: Config,
) -> Response:
    """Register a ChatGPT public client with allowlisted redirect URIs."""

    _require_oauth_configuration(config)
    _enforce_rate_limit(request, rate_limiter, "register")
    try:
        payload = await request.json()
        registration = OAuthClientRegistration.model_validate(payload)
    except (UnicodeDecodeError, json.JSONDecodeError, ValidationError, ValueError):
        return _dcr_error(
            "invalid_client_metadata",
            "Dynamic client metadata is invalid.",
        )
    if registration.grant_types != ["authorization_code"]:
        return _dcr_error(
            "invalid_client_metadata",
            "Only the authorization_code grant is supported.",
        )
    if registration.response_types != ["code"]:
        return _dcr_error(
            "invalid_client_metadata",
            "Only the code response type is supported.",
        )
    redirect_uris = tuple(dict.fromkeys(registration.redirect_uris))
    if not all(
        is_allowed_redirect_uri(
            uri,
            allowed_origins=config.allowed_redirect_origins,
        )
        for uri in redirect_uris
    ):
        return _dcr_error(
            "invalid_redirect_uri",
            "Unsupported OAuth redirect URI.",
        )
    try:
        client = store.register_oauth_client(
            client_name=registration.client_name,
            redirect_uris=redirect_uris,
        )
    except OAuthClientRegistrationLimitError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=str(exc),
            headers={"Retry-After": "3600"},
        ) from exc
    except WhatsAppBusinessStoreUnavailableError as exc:
        raise _store_http_error(exc) from exc
    return JSONResponse(
        {
            "client_id": client.client_id,
            "client_name": client.client_name,
            "redirect_uris": list(client.redirect_uris),
            # OAuth public-client method literal, not a credential.
            "token_endpoint_auth_method": "none",  # nosec B105
            "grant_types": ["authorization_code"],
            "response_types": ["code"],
            "client_id_issued_at": int(time.time()),
        },
        status_code=status.HTTP_201_CREATED,
        headers={"Cache-Control": "no-store", "Pragma": "no-cache"},
    )


def _validate_authorization_request(
    *,
    client_id: str,
    redirect_uri: str,
    response_type: str,
    scope: str,
    resource: str,
    code_challenge: str,
    code_challenge_method: str,
    store: WhatsAppBusinessStore,
    config: WhatsAppBusinessConfig,
) -> None:
    if response_type != "code":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Unsupported OAuth response type.",
        )
    if scope != OAUTH_SCOPE or resource != config.resource_url:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid OAuth resource or scope.",
        )
    if code_challenge_method != "S256" or len(code_challenge) != 43:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="S256 PKCE is required.",
        )
    try:
        client = store.get_oauth_client(client_id)
    except WhatsAppBusinessStoreUnavailableError as exc:
        raise _store_http_error(exc) from exc
    if client is None or redirect_uri not in client.redirect_uris:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Unknown OAuth client or redirect URI.",
        )


def _login_redirect(request: Request) -> RedirectResponse:
    target = request.url.path
    if request.url.query:
        target = f"{target}?{request.url.query}"
    return RedirectResponse(
        f"/auth/page?{urlencode({'redirect': target})}",
        status_code=status.HTTP_307_TEMPORARY_REDIRECT,
    )


@router.get("/oauth/authorize", response_class=HTMLResponse)
def oauth_authorize(
    request: Request,
    store: Store,
    config: Config,
    rate_limiter: ConnectorRateLimiter,
    client_id: str,
    redirect_uri: str,
    response_type: str,
    scope: str,
    resource: str,
    code_challenge: str,
    code_challenge_method: str,
    state: str = "",
) -> Response:
    """Authenticate with Mparanza and display explicit read-only consent."""

    _require_oauth_configuration(config)
    _enforce_rate_limit(request, rate_limiter, "oauth")
    _validate_authorization_request(
        client_id=client_id,
        redirect_uri=redirect_uri,
        response_type=response_type,
        scope=scope,
        resource=resource,
        code_challenge=code_challenge,
        code_challenge_method=code_challenge_method,
        store=store,
        config=config,
    )
    user = maybe_current_user(request)
    if user is None:
        return _login_redirect(request)
    owner_key = _owner_key(user, config)
    parameters = {
        "client_id": client_id,
        "redirect_uri": redirect_uri,
        "response_type": response_type,
        "scope": scope,
        "resource": resource,
        "code_challenge": code_challenge,
        "code_challenge_method": code_challenge_method,
        "state": state,
    }
    try:
        consent_token = build_consent_token(
            parameters,
            owner_key=owner_key,
            secret=config.oauth_secret,
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=str(exc),
        ) from exc
    return HTMLResponse(
        f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport"
content="width=device-width"><title>Connect Vera</title></head>
<body style="max-width:640px;margin:48px auto;padding:0 20px;font-family:system-ui">
<h1>Connect Vera to WhatsApp Business</h1>
<p>Signed in as {html.escape(user.email)}.</p>
<p>Vera will be able to search and open new inbound messages already acquired
for this linked account. It cannot send, reply, import history, or download media.</p>
<form method="post" action="/whatsapp/oauth/authorize">
<input type="hidden" name="consent_token" value="{html.escape(consent_token)}">
<button name="decision" value="allow" type="submit">Allow read-only access</button>
<button name="decision" value="deny" type="submit">Cancel</button>
</form></body></html>""",
        headers=_SENSITIVE_HTML_HEADERS,
    )


def _redirect_with_parameters(url: str, parameters: dict[str, str]) -> str:
    parsed = urlparse(url)
    query = parse_qsl(parsed.query, keep_blank_values=True)
    query.extend(parameters.items())
    return urlunparse(parsed._replace(query=urlencode(query)))


@router.post("/oauth/authorize")
def oauth_authorize_decision(
    request: Request,
    store: Store,
    config: Config,
    rate_limiter: ConnectorRateLimiter,
    consent_token: Annotated[str, Form(min_length=20, max_length=8_000)],
    decision: Annotated[Literal["allow", "deny"], Form()],
) -> Response:
    """Issue one single-use code after authenticated consent."""

    _require_oauth_configuration(config)
    _enforce_rate_limit(request, rate_limiter, "oauth")
    user = maybe_current_user(request)
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Session expired. Restart the connector authorization.",
        )
    owner_key = _owner_key(user, config)
    parameters = verify_consent_token(
        consent_token,
        owner_key=owner_key,
        secret=config.oauth_secret,
    )
    if parameters is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="OAuth consent request is invalid or expired.",
        )
    _validate_authorization_request(
        client_id=parameters.get("client_id", ""),
        redirect_uri=parameters.get("redirect_uri", ""),
        response_type=parameters.get("response_type", ""),
        scope=parameters.get("scope", ""),
        resource=parameters.get("resource", ""),
        code_challenge=parameters.get("code_challenge", ""),
        code_challenge_method=parameters.get("code_challenge_method", ""),
        store=store,
        config=config,
    )
    redirect_uri = parameters["redirect_uri"]
    state_value = parameters.get("state", "")
    if decision == "deny":
        values = {"error": "access_denied"}
        if state_value:
            values["state"] = state_value
        return RedirectResponse(
            _redirect_with_parameters(redirect_uri, values),
            status_code=status.HTTP_303_SEE_OTHER,
            headers={"Referrer-Policy": "no-referrer"},
        )
    try:
        code = store.issue_authorization_code(
            client_id=parameters["client_id"],
            owner_key=owner_key,
            redirect_uri=redirect_uri,
            resource=parameters["resource"],
            scope=parameters["scope"],
            code_challenge=parameters["code_challenge"],
            ttl_seconds=_AUTHORIZATION_CODE_TTL_SECONDS,
        )
    except WhatsAppBusinessStoreUnavailableError as exc:
        raise _store_http_error(exc) from exc
    if code is None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Link a WhatsApp Business account before authorizing access.",
        )
    values = {"code": code}
    if state_value:
        values["state"] = state_value
    return RedirectResponse(
        _redirect_with_parameters(redirect_uri, values),
        status_code=status.HTTP_303_SEE_OTHER,
        headers={"Referrer-Policy": "no-referrer"},
    )


def _oauth_error(error: str, description: str) -> JSONResponse:
    return JSONResponse(
        status_code=status.HTTP_400_BAD_REQUEST,
        content={"error": error, "error_description": description},
        headers={"Cache-Control": "no-store", "Pragma": "no-cache"},
    )


@router.post("/oauth/token")
async def oauth_token(
    request: Request,
    store: Store,
    config: Config,
    rate_limiter: ConnectorRateLimiter,
) -> Response:
    """Exchange one single-use PKCE code for an opaque bearer token."""

    _require_oauth_configuration(config)
    _enforce_rate_limit(request, rate_limiter, "oauth")
    form = await request.form()
    form_items = list(form.multi_items())
    if len({key for key, _value in form_items}) != len(form_items):
        return _oauth_error("invalid_request", "Token fields must not be repeated.")
    try:
        exchange = OAuthTokenExchange.model_validate(dict(form_items))
    except ValidationError:
        return _oauth_error("invalid_request", "Token request is invalid.")
    if exchange.grant_type != "authorization_code":
        return _oauth_error("unsupported_grant_type", "Use authorization_code.")
    try:
        client = store.get_oauth_client(exchange.client_id)
    except WhatsAppBusinessStoreUnavailableError as exc:
        raise _store_http_error(exc) from exc
    if client is None or exchange.redirect_uri not in client.redirect_uris:
        return _oauth_error("invalid_client", "Unknown OAuth client.")
    if not is_valid_pkce_verifier(exchange.code_verifier):
        return _oauth_error("invalid_grant", "PKCE verifier is invalid.")
    expected_code_challenge = pkce_challenge(exchange.code_verifier)
    if exchange.resource != config.resource_url:
        return _oauth_error(
            "invalid_grant",
            "Authorization code, PKCE verifier, resource, or linked account is invalid.",
        )
    try:
        issued = store.exchange_authorization_code(
            exchange.code,
            client_id=exchange.client_id,
            redirect_uri=exchange.redirect_uri,
            resource=exchange.resource,
            code_challenge=expected_code_challenge,
            ttl_seconds=config.access_token_ttl_seconds,
        )
    except WhatsAppBusinessStoreUnavailableError as exc:
        raise _store_http_error(exc) from exc
    if issued is None:
        return _oauth_error(
            "invalid_grant",
            "Authorization code, PKCE verifier, resource, or linked account is invalid.",
        )
    token, identity = issued
    return JSONResponse(
        {
            "access_token": token,
            # OAuth token-type literal, not a credential.
            "token_type": "Bearer",  # nosec B105
            "expires_in": identity.expires_at - int(time.time()),
            "scope": " ".join(sorted(identity.scopes)),
            "resource": identity.resource,
        },
        headers={"Cache-Control": "no-store", "Pragma": "no-cache"},
    )


def _mcp_error(
    request_id: object,
    *,
    code: int,
    message: str,
) -> dict[str, Any]:
    return {
        "jsonrpc": "2.0",
        "id": request_id,
        "error": {"code": code, "message": message},
    }


def _mcp_result(request_id: object, result: object) -> dict[str, Any]:
    return {"jsonrpc": "2.0", "id": request_id, "result": result}


def _bearer_identity(
    request: Request,
    *,
    store: WhatsAppBusinessStore,
) -> OAuthIdentity | None:
    authorization = request.headers.get("authorization", "")
    if not authorization.lower().startswith("bearer "):
        return None
    token = authorization[7:].strip()
    if not token:
        return None
    return store.resolve_access_token(token)


def _validate_mcp_transport(request: Request, config: WhatsAppBusinessConfig) -> None:
    if not is_allowed_mcp_origin(request.headers.get("origin"), config=config):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Untrusted MCP Origin.",
        )
    requested_protocol = request.headers.get(_MCP_PROTOCOL_HEADER)
    if requested_protocol and requested_protocol != MCP_PROTOCOL_VERSION:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Unsupported MCP protocol version.",
        )


@router.post("/mcp")
async def whatsapp_mcp(
    request: Request,
    store: Store,
    config: Config,
    rate_limiter: ConnectorRateLimiter,
) -> Response:
    """Serve a stateless Streamable HTTP MCP endpoint."""

    _validate_mcp_transport(request, config)
    _enforce_rate_limit(request, rate_limiter, "mcp")
    try:
        payload = json.loads(await request.body())
    except (UnicodeDecodeError, json.JSONDecodeError):
        return JSONResponse(_mcp_error(None, code=-32700, message="Parse error."))
    if not isinstance(payload, dict) or payload.get("jsonrpc") != "2.0":
        return JSONResponse(_mcp_error(None, code=-32600, message="Invalid Request."))
    request_id = payload.get("id")
    method = payload.get("method")
    parameters = payload.get("params")
    if not isinstance(method, str):
        return JSONResponse(
            _mcp_error(request_id, code=-32600, message="Invalid Request.")
        )
    if request_id is None:
        return Response(status_code=status.HTTP_202_ACCEPTED)
    if method == "initialize":
        return JSONResponse(
            _mcp_result(
                request_id,
                {
                    "protocolVersion": MCP_PROTOCOL_VERSION,
                    "capabilities": {"tools": {"listChanged": False}},
                    "serverInfo": MCP_SERVER_INFO,
                },
            )
        )
    if method == "ping":
        return JSONResponse(_mcp_result(request_id, {}))
    if method == "tools/list":
        return JSONResponse(_mcp_result(request_id, {"tools": MCP_TOOLS}))
    if method != "tools/call":
        return JSONResponse(
            _mcp_error(request_id, code=-32601, message="Method not found.")
        )
    if not isinstance(parameters, dict) or not isinstance(parameters.get("name"), str):
        return JSONResponse(
            _mcp_error(request_id, code=-32602, message="Invalid params.")
        )
    try:
        _require_oauth_configuration(config)
    except HTTPException as exc:
        return JSONResponse(
            _mcp_result(
                request_id,
                {
                    "content": [{"type": "text", "text": str(exc.detail)}],
                    "isError": True,
                },
            ),
            status_code=exc.status_code,
        )
    try:
        identity = _bearer_identity(request, store=store)
    except WhatsAppBusinessStoreUnavailableError:
        return JSONResponse(
            _mcp_result(
                request_id,
                {
                    "content": [
                        {
                            "type": "text",
                            "text": (
                                "WhatsApp Business storage is temporarily unavailable."
                            ),
                        }
                    ],
                    "isError": True,
                },
            ),
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        )
    result = call_tool(
        name=parameters["name"],
        arguments=parameters.get("arguments", {}),
        identity=identity,
        store=store,
        config=config,
    )
    response = JSONResponse(_mcp_result(request_id, result))
    if identity is None:
        response.headers["WWW-Authenticate"] = build_www_authenticate(config)
    return response


@router.get("/mcp")
def whatsapp_mcp_get(request: Request, config: Config) -> Response:
    """Advertise OAuth on unsupported GET transport attempts."""

    _validate_mcp_transport(request, config)
    return Response(
        status_code=status.HTTP_405_METHOD_NOT_ALLOWED,
        headers={
            "Allow": "POST",
            "WWW-Authenticate": build_www_authenticate(config),
        },
    )
