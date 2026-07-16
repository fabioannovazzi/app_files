"""FastAPI router for authentication endpoints (Google + magic links)."""

from __future__ import annotations

import logging
import re
from urllib.parse import urlencode

import html

from fastapi import APIRouter, HTTPException, Request, Response, status
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel, Field

from modules.auth.dependencies import get_allowed_page_keys_for_email
from modules.auth.config import AuthConfig, get_auth_config
from modules.auth.google_identity import (
    GoogleUserInfo,
    InvalidGoogleTokenError,
    UnauthorizedGoogleUserError,
    verify_google_identity_token,
)
from modules.auth.magic_links import (
    MagicLinkExpiredError,
    MagicLinkNotFoundError,
    MagicLinkRecord,
    consume_magic_link,
    issue_magic_link,
)
from modules.auth.session import (
    AuthenticatedUser,
    InvalidSessionError,
    create_session_cookie,
    decode_session_cookie,
)
from modules.notifications.resend_client import (
    ResendAuthenticationError,
    is_resend_configured,
    send_email,
)
from modules.pdp.language import get_navigation_label, get_page_copy, resolve_language

router = APIRouter(prefix="/auth", tags=["auth"])
site_router = APIRouter(prefix="/auth")
LOGGER = logging.getLogger(__name__)
_EMAIL_REGEX = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
_LOCAL_GOOGLE_ORIGIN_HOSTS = {"localhost", "127.0.0.1", "::1"}
templates = Jinja2Templates(directory="templates")


class LoginRequest(BaseModel):
    credential: str


class MagicLinkRequest(BaseModel):
    email: str = Field(..., min_length=3, max_length=320)
    redirect_path: str | None = None


class MagicLinkVerifyRequest(BaseModel):
    token: str


class SessionResponse(BaseModel):
    email: str
    full_name: str | None = None
    given_name: str | None = None
    family_name: str | None = None
    picture: str | None = None
    redirect_path: str | None = None
    allowed_page_keys: list[str] = Field(default_factory=list)

    @classmethod
    def from_user(cls, user: AuthenticatedUser) -> "SessionResponse":
        return cls(
            email=user.email,
            full_name=user.full_name,
            given_name=user.given_name,
            family_name=user.family_name,
            picture=user.picture,
            allowed_page_keys=sorted(get_allowed_page_keys_for_email(user.email)),
        )


@site_router.get("/page", include_in_schema=False)
def auth_page(request: Request) -> HTMLResponse:
    config = get_auth_config()
    lang = resolve_language(request)
    page_label = get_navigation_label(lang, "/auth/page")
    default_redirect = "/" if not lang else f"/?lang={lang}"
    redirect_path = _normalise_redirect_path(
        request.query_params.get("redirect"),
        default_redirect,
    )
    return templates.TemplateResponse(
        request,
        "auth_login.html",
        {
            "lang": lang,
            "page_label": page_label,
            "copy": get_page_copy("auth_login", lang),
            "auth_enabled": config.authentication_enabled,
            "google_client_id": _google_client_id_for_request(request, config),
            "redirect_path": redirect_path,
        },
    )


def _request_origin(request: Request) -> str:
    hostname = request.url.hostname or ""
    if ":" in hostname and not hostname.startswith("["):
        hostname = f"[{hostname}]"
    port = request.url.port
    default_port = 443 if request.url.scheme == "https" else 80
    host = hostname if not port or port == default_port else f"{hostname}:{port}"
    return f"{request.url.scheme}://{host}".lower()


def _is_local_google_origin(request: Request) -> bool:
    hostname = (request.url.hostname or "").lower()
    return hostname in _LOCAL_GOOGLE_ORIGIN_HOSTS


def _google_client_id_for_request(request: Request, config: AuthConfig) -> str:
    if not config.google_client_id:
        return ""
    origin = _request_origin(request)
    if config.google_authorized_origins:
        return (
            config.google_client_id
            if origin in config.google_authorized_origins
            else ""
        )
    if _is_local_google_origin(request):
        return ""
    return config.google_client_id


def _clear_cookie(response: Response) -> None:
    config = get_auth_config()
    response.delete_cookie(
        key=config.session_cookie_name,
        path="/",
        httponly=True,
        secure=config.cookie_secure,
        samesite="lax",
    )


def _ensure_authentication_enabled(config: AuthConfig) -> None:
    if not config.authentication_enabled:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Authentication is disabled.",
        )


def _set_session_cookie(response: Response, user_info: GoogleUserInfo, config) -> None:
    cookie_value, expires_at = create_session_cookie(user_info, config)
    response.set_cookie(
        key=config.session_cookie_name,
        value=cookie_value,
        httponly=True,
        secure=config.cookie_secure,
        samesite="lax",
        max_age=config.session_ttl_seconds,
        expires=expires_at,
        path="/",
    )


def _normalise_redirect_path(value: str | None, default_path: str) -> str:
    candidate = (value or "").strip()
    if not candidate:
        return default_path
    if not candidate.startswith("/"):
        candidate = "/" + candidate.lstrip("/")
    return candidate


def _validate_email_address(raw_email: str) -> str:
    candidate = (raw_email or "").strip().lower()
    if not candidate or not _EMAIL_REGEX.match(candidate):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Provide a valid email address.",
        )
    return candidate


def _enforce_email_policy(
    email: str, allowed_domains: tuple[str, ...], allowed_emails: tuple[str, ...]
) -> None:
    normalised_email = email.strip().lower()
    if allowed_emails and normalised_email not in allowed_emails:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Email address is not permitted to sign in.",
        )
    if allowed_domains:
        domain = normalised_email.split("@")[-1]
        if domain not in allowed_domains:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Email domain is not permitted to sign in.",
            )


def _consume_magic_token(token: str) -> MagicLinkRecord:
    try:
        return consume_magic_link(token)
    except MagicLinkExpiredError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Magic link expired. Request a new email.",
        ) from exc
    except MagicLinkNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Magic link is invalid or already used.",
        ) from exc


def _magic_link_subject() -> str:
    return "Sign in to Mparanza"


def _magic_link_minutes(ttl_seconds: int) -> int:
    return max(int(round(ttl_seconds / 60)), 1)


def _magic_link_text_message(link: str, ttl_seconds: int) -> str:
    minutes = _magic_link_minutes(ttl_seconds)
    plural = "" if minutes == 1 else "s"
    return (
        "Mparanza sign-in request\n\n"
        "You requested a secure link to sign in to your account on mparanza.com.\n\n"
        f"Sign in to Mparanza: {link}\n\n"
        "This link:\n"
        "- works only once\n"
        f"- expires in {minutes} minute{plural}\n"
        "- is valid only for this email address\n\n"
        "If you did not request this, you can ignore this email. No action is required."
    )


def _magic_link_html_message(link: str, ttl_seconds: int) -> str:
    minutes = _magic_link_minutes(ttl_seconds)
    plural = "" if minutes == 1 else "s"
    escaped_link = html.escape(link, quote=True)
    return (
        "<!doctype html>"
        "<html>"
        '<body style="margin:0;padding:0;background:#f5f3ee;color:#1c1c18;'
        "font-family:Georgia,'Times New Roman',serif;\">"
        '<table role="presentation" width="100%" cellspacing="0" cellpadding="0" '
        'style="background:#f5f3ee;padding:32px 16px;">'
        '<tr><td align="center">'
        '<table role="presentation" width="100%" cellspacing="0" cellpadding="0" '
        'style="max-width:560px;background:#fffdf8;border:1px solid #ddd5c6;border-radius:18px;'
        'padding:36px 32px;">'
        "<tr><td>"
        '<p style="margin:0 0 12px;font-size:14px;letter-spacing:0.08em;text-transform:uppercase;'
        'color:#6f6759;">Mparanza sign-in request</p>'
        '<h1 style="margin:0 0 16px;font-size:28px;line-height:1.2;font-weight:600;color:#1c1c18;">'
        "Continue to your account</h1>"
        '<p style="margin:0 0 24px;font-size:16px;line-height:1.6;color:#353127;">'
        "You requested a secure link to sign in to your account on mparanza.com.</p>"
        '<p style="margin:0 0 28px;">'
        f'<a href="{escaped_link}" style="display:inline-block;padding:13px 22px;border-radius:999px;'
        'background:#1f3d7a;color:#fffdf8;text-decoration:none;font-size:15px;font-weight:600;">'
        "Sign in to Mparanza</a></p>"
        '<p style="margin:0 0 12px;font-size:16px;line-height:1.6;color:#353127;">This link:</p>'
        '<ul style="margin:0 0 24px 20px;padding:0;color:#353127;font-size:16px;line-height:1.7;">'
        "<li>works only once</li>"
        f"<li>expires in {minutes} minute{plural}</li>"
        "<li>is valid only for this email address</li>"
        "</ul>"
        '<p style="margin:0 0 18px;font-size:15px;line-height:1.6;color:#5c5548;">'
        "If you did not request this, you can ignore this email. No action is required.</p>"
        '<p style="margin:0;font-size:13px;line-height:1.6;color:#7a7367;">'
        "If the button does not work, copy and paste this link into your browser:<br>"
        f'<a href="{escaped_link}" style="color:#1f3d7a;word-break:break-all;">{escaped_link}</a>'
        "</p>"
        "</td></tr></table>"
        "</td></tr></table>"
        "</body>"
        "</html>"
    )


@router.post("/login", response_model=SessionResponse)
def login(payload: LoginRequest, response: Response) -> SessionResponse:
    config = get_auth_config()
    if not config.authentication_enabled:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Authentication is disabled.",
        )

    credential = (payload.credential or "").strip()
    if not credential:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Missing credential.",
        )

    try:
        user_info = verify_google_identity_token(
            credential,
            config.google_client_id,
            allowed_domains=config.allowed_domains,
            allowed_emails=config.allowed_emails,
        )
    except (InvalidGoogleTokenError, UnauthorizedGoogleUserError) as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=str(exc),
        ) from exc

    _set_session_cookie(response, user_info, config)

    return SessionResponse(
        email=user_info.email,
        full_name=user_info.full_name,
        given_name=user_info.given_name,
        family_name=user_info.family_name,
        picture=user_info.picture,
        allowed_page_keys=sorted(get_allowed_page_keys_for_email(user_info.email)),
    )


@router.post("/logout")
def logout(response: Response) -> dict[str, str]:
    config = get_auth_config()
    if config.authentication_enabled:
        _clear_cookie(response)
    return {"status": "ok"}


@router.get("/session", response_model=SessionResponse)
def session(request: Request, response: Response) -> SessionResponse:
    config = get_auth_config()
    if not config.authentication_enabled:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Authentication is not enabled.",
        )

    cookie_value = request.cookies.get(config.session_cookie_name)
    if not cookie_value:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required.",
        )

    try:
        user = decode_session_cookie(cookie_value, config)
    except InvalidSessionError as exc:
        _clear_cookie(response)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required.",
        ) from exc

    return SessionResponse.from_user(user)


@router.post("/magic/request")
def request_magic_link(payload: MagicLinkRequest, request: Request) -> dict[str, str]:
    config = get_auth_config()
    _ensure_authentication_enabled(config)
    if not is_resend_configured():
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Email delivery is not configured. Set RESEND_API_KEY and RESEND_FROM_EMAIL.",
        )

    email = _validate_email_address(payload.email)
    _enforce_email_policy(email, config.allowed_domains, config.allowed_emails)
    redirect_path = _normalise_redirect_path(
        payload.redirect_path, config.magic_link_default_redirect
    )

    token = issue_magic_link(
        email,
        ttl_seconds=config.magic_link_ttl_seconds,
        redirect_path=redirect_path,
    )
    base_url = request.url_for("consume_magic_link")
    link = f"{base_url}?{urlencode({'token': token})}"
    subject = _magic_link_subject()
    text_message = _magic_link_text_message(link, config.magic_link_ttl_seconds)
    html_message = _magic_link_html_message(link, config.magic_link_ttl_seconds)

    try:
        delivered = send_email(
            email,
            subject,
            text_message,
            html_body=html_message,
        )
    except ResendAuthenticationError:
        LOGGER.warning("Resend rejected the configured credentials for %s", email)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=(
                "Email delivery credentials were rejected. "
                "Verify RESEND_API_KEY is valid and RESEND_FROM_EMAIL is a verified sender "
                "in Resend (quoted values are accepted and stripped)."
            ),
        ) from None
    if not delivered:
        LOGGER.warning("Failed to send magic link email to %s", email)
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Unable to send magic link email. Try again later.",
        )

    return {"status": "sent"}


@router.post("/magic/verify", response_model=SessionResponse)
def verify_magic_link(
    payload: MagicLinkVerifyRequest, response: Response
) -> SessionResponse:
    config = get_auth_config()
    _ensure_authentication_enabled(config)
    if not payload.token.strip():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Missing magic link token.",
        )

    record = _consume_magic_token(payload.token.strip())
    redirect_path = record.redirect_path or config.magic_link_default_redirect
    user_info = GoogleUserInfo(email=record.email)
    _set_session_cookie(response, user_info, config)
    return SessionResponse(
        email=user_info.email,
        full_name=user_info.full_name,
        given_name=user_info.given_name,
        family_name=user_info.family_name,
        picture=user_info.picture,
        redirect_path=redirect_path,
        allowed_page_keys=sorted(get_allowed_page_keys_for_email(user_info.email)),
    )


@router.get("/magic/consume", name="consume_magic_link", response_model=None)
def consume_magic_link_endpoint(
    token: str | None = None,
    redirect: str | None = None,
    lang: str | None = None,
) -> RedirectResponse | HTMLResponse:
    config = get_auth_config()
    _ensure_authentication_enabled(config)
    if not token:
        return _render_magic_error_page(
            "Magic link token missing. Request a new email.", lang=lang
        )
    try:
        record = _consume_magic_token(token)
    except HTTPException as exc:
        detail = (
            exc.detail
            if isinstance(exc.detail, str)
            else "Magic link is invalid or already used."
        )
        return _render_magic_error_page(detail, lang=lang, status_code=exc.status_code)
    redirect_path = _normalise_redirect_path(
        redirect or record.redirect_path,
        config.magic_link_default_redirect,
    )
    user_info = GoogleUserInfo(email=record.email)
    response = RedirectResponse(
        url=redirect_path,
        status_code=status.HTTP_307_TEMPORARY_REDIRECT,
    )
    _set_session_cookie(response, user_info, config)
    return response


def _render_magic_error_page(
    message: str,
    *,
    lang: str | None = None,
    status_code: int = status.HTTP_400_BAD_REQUEST,
) -> HTMLResponse:
    safe_message = html.escape(message or "Magic link is invalid or already used.")
    target = "/" if not lang else f"/?lang={html.escape(lang)}"
    content = f"""
    <!DOCTYPE html>
    <html lang="{html.escape(lang or 'en')}">
      <head>
        <meta charset="utf-8" />
        <title>Magic link expired</title>
        <style>
          body {{
            font-family: "Inter", "Segoe UI", system-ui, -apple-system, BlinkMacSystemFont, sans-serif;
            background: #f8fafc;
            color: #0f172a;
            display: flex;
            align-items: center;
            justify-content: center;
            min-height: 100vh;
            margin: 0;
          }}
          .card {{
            background: white;
            border-radius: 16px;
            border: 1px solid rgba(148, 163, 184, 0.4);
            box-shadow: 0 25px 50px rgba(15, 23, 42, 0.08);
            padding: 32px;
            max-width: 420px;
            text-align: center;
          }}
          .card h1 {{
            font-size: 1.4rem;
            margin-bottom: 12px;
          }}
          .card p {{
            margin: 0 0 20px 0;
            color: #475467;
            line-height: 1.45;
          }}
          .card a {{
            display: inline-flex;
            align-items: center;
            justify-content: center;
            padding: 10px 18px;
            border-radius: 999px;
            border: 1px solid rgba(15, 23, 42, 0.12);
            color: #0f172a;
            text-decoration: none;
            font-weight: 600;
            transition: background 0.15s ease, border-color 0.15s ease;
          }}
          .card a:hover {{
            background: rgba(15, 23, 42, 0.05);
            border-color: rgba(15, 23, 42, 0.25);
          }}
        </style>
      </head>
      <body>
        <div class="card">
          <h1>Request a new link</h1>
          <p>{safe_message}</p>
          <a href="{target}">Back to sign in</a>
        </div>
      </body>
    </html>
    """
    return HTMLResponse(content=content, status_code=status_code)
