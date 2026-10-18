"""Anonymous OAuth capabilities scoped only to the Vera incident resource."""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import re
import secrets
import time
from typing import Any
from urllib.parse import urlsplit
from uuid import UUID, uuid4

from modules.operational_incidents.contracts import Credentials
from modules.operational_incidents.store import ConnectionActor, IncidentStore
from modules.workflow_usage.products import PRODUCTS, Product

__all__ = [
    "IncidentOAuth",
    "OAuthError",
    "ISSUER",
    "RESOURCE",
    "SCOPE",
    "CLAUDE_CLIENT",
]

ISSUER = "https://mparanza.com"
RESOURCE = ISSUER + "/mcp/vera-incidents"
SCOPE = "vera:incidents"
RESOURCES = {ISSUER + f"/mcp/{product}-incidents": product for product in PRODUCTS}
CLAUDE_CLIENT = "https://claude.ai/oauth/mcp-oauth-client-metadata"
CLAUDE_CALLBACK = "https://claude.ai/api/mcp/auth_callback"
ACCESS_SECONDS = 3600
REFRESH_SECONDS = 90 * 24 * 3600
_SCHEMA = (
    "CREATE TABLE IF NOT EXISTS operational_oauth_clients (client_id TEXT PRIMARY KEY, redirects_json TEXT NOT NULL, created_at BIGINT NOT NULL)",
    "CREATE TABLE IF NOT EXISTS operational_oauth_codes (code_hash TEXT PRIMARY KEY, client_id TEXT NOT NULL, redirect_uri TEXT NOT NULL, challenge TEXT NOT NULL, connection_id TEXT NOT NULL, expires_at BIGINT NOT NULL, used INTEGER NOT NULL)",
    "CREATE TABLE IF NOT EXISTS operational_oauth_sessions (session_id TEXT PRIMARY KEY, connection_id TEXT NOT NULL, client_id TEXT NOT NULL, revoked INTEGER NOT NULL, expires_at BIGINT NOT NULL)",
    "CREATE TABLE IF NOT EXISTS operational_oauth_tokens (token_hash TEXT PRIMARY KEY, session_id TEXT NOT NULL, kind TEXT NOT NULL, expires_at BIGINT NOT NULL, used INTEGER NOT NULL)",
)


class OAuthError(ValueError):
    """A bounded OAuth error that never echoes credentials or caller input."""

    def __init__(self, code: str = "invalid_request") -> None:
        super().__init__(code)
        self.code = code


def _hash(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


def _callback(value: str) -> bool:
    """Allow the verified Claude callback or exact registered native loopback URLs."""
    if value == CLAUDE_CALLBACK:
        return True
    try:
        url = urlsplit(value)
        return (
            url.scheme == "http"
            and url.hostname in {"127.0.0.1", "localhost", "::1"}
            and url.port is not None
            and not url.username
            and not url.password
            and not url.query
            and not url.fragment
            and bool(url.path)
        )
    except ValueError:
        return False


class IncidentOAuth:
    """Use the incident transaction lock across API processes and refreshes."""

    def __init__(self, store: IncidentStore) -> None:
        self.store = store

    def _schema(self, connection: Any) -> None:
        self.store._schema(connection)
        for statement in _SCHEMA:
            connection.execute(statement)

    def _execute(self, connection: Any, sql: str, values: tuple[Any, ...]) -> Any:
        return connection.execute(self.store._sql(sql), values)

    def metadata(self) -> dict[str, Any]:
        """Publish fixed URLs, independent of incoming Host and forwarded headers."""
        return {
            "issuer": ISSUER,
            "authorization_endpoint": ISSUER + "/oauth/vera-incidents/authorize",
            "token_endpoint": ISSUER + "/oauth/vera-incidents/token",
            "registration_endpoint": ISSUER + "/oauth/vera-incidents/register",
            "revocation_endpoint": ISSUER + "/oauth/vera-incidents/revoke",
            "response_types_supported": ["code"],
            "grant_types_supported": ["authorization_code", "refresh_token"],
            "token_endpoint_auth_methods_supported": ["none"],
            "code_challenge_methods_supported": ["S256"],
            "scopes_supported": [f"{product}:incidents" for product in PRODUCTS],
            "client_id_metadata_document_supported": True,
        }

    def register(self, data: dict[str, Any]) -> dict[str, Any]:
        """Register public clients without fetching caller-supplied metadata URLs."""
        redirects = data.get("redirect_uris")
        grants = data.get("grant_types", ["authorization_code", "refresh_token"])
        if (
            not isinstance(redirects, list)
            or not 1 <= len(redirects) <= 8
            or any(
                not isinstance(url, str) or len(url) > 2048 or not _callback(url)
                for url in redirects
            )
            or data.get("token_endpoint_auth_method", "none") != "none"
            or data.get("response_types", ["code"]) != ["code"]
            or not isinstance(grants, list)
            or not all(isinstance(grant, str) for grant in grants)
            or "authorization_code" not in grants
            or set(grants) - {"authorization_code", "refresh_token"}
        ):
            raise OAuthError("invalid_client_metadata")
        identifier = secrets.token_urlsafe(32)
        with self.store._connection() as connection:
            self._schema(connection)
            self._execute(
                connection,
                "INSERT INTO operational_oauth_clients VALUES (?,?,?)",
                (identifier, json.dumps(redirects), int(time.time())),
            )
        return {
            "client_id": identifier,
            "client_id_issued_at": int(time.time()),
            "redirect_uris": redirects,
            "token_endpoint_auth_method": "none",
            "grant_types": ["authorization_code", "refresh_token"],
            "response_types": ["code"],
        }

    def _client(
        self, connection: Any, client_id: str, redirect: str | None = None
    ) -> None:
        if client_id == CLAUDE_CLIENT:
            # Fixed, directly verified published metadata. Never fetch arbitrary URLs.
            redirects = [CLAUDE_CALLBACK]
        else:
            row = self._execute(
                connection,
                "SELECT * FROM operational_oauth_clients WHERE client_id=?",
                (client_id,),
            ).fetchone()
            if row is None:
                raise OAuthError("invalid_client")
            redirects = json.loads(row["redirects_json"])
        if redirect is not None and redirect not in redirects:
            raise OAuthError("invalid_request")

    def authorize(self, data: dict[str, str]) -> str:
        """Create a new anonymous namespace without any personal browser account."""
        challenge = data.get("code_challenge", "")
        product = RESOURCES.get(data.get("resource", ""))
        if (
            data.get("response_type") != "code"
            or data.get("code_challenge_method") != "S256"
            or not re.fullmatch(r"[A-Za-z0-9_-]{43}", challenge)
            or product is None
            or data.get("scope", f"{product}:incidents") != f"{product}:incidents"
            or not data.get("redirect_uri")
        ):
            raise OAuthError()
        code = secrets.token_urlsafe(32)
        namespace = Credentials(
            installation_id=uuid4(), installation_key=secrets.token_urlsafe(32)
        )
        with self.store._connection() as connection:
            self._schema(connection)
            self._client(connection, data.get("client_id", ""), data["redirect_uri"])
            self._execute(
                connection,
                "INSERT INTO operational_installations VALUES (?,?,?)",
                (
                    str(namespace.installation_id),
                    _hash(namespace.installation_key),
                    str(int(time.time())),
                ),
            )
            self._execute(
                connection,
                "INSERT INTO operational_installation_products VALUES (?,?)",
                (str(namespace.installation_id), product),
            )
            self._execute(
                connection,
                "INSERT INTO operational_oauth_codes VALUES (?,?,?,?,?,?,?)",
                (
                    _hash(code),
                    data["client_id"],
                    data["redirect_uri"],
                    challenge,
                    str(namespace.installation_id),
                    int(time.time()) + 300,
                    0,
                ),
            )
        return code

    def _tokens(
        self, connection: Any, session_id: str, product: Product = "vera"
    ) -> dict[str, Any]:
        access, refresh = secrets.token_urlsafe(32), secrets.token_urlsafe(32)
        now = int(time.time())
        self._execute(
            connection,
            "UPDATE operational_oauth_sessions SET expires_at=? WHERE session_id=?",
            (now + REFRESH_SECONDS, session_id),
        )
        for value, kind, expires in (
            (access, "access", now + ACCESS_SECONDS),
            (refresh, "refresh", now + REFRESH_SECONDS),
        ):
            self._execute(
                connection,
                "INSERT INTO operational_oauth_tokens VALUES (?,?,?,?,?)",
                (_hash(value), session_id, kind, expires, 0),
            )
        return {
            "access_token": access,
            "token_type": "Bearer",
            "expires_in": ACCESS_SECONDS,
            "refresh_token": refresh,
            "scope": f"{product}:incidents",
        }

    def token(self, data: dict[str, str]) -> dict[str, Any]:
        """Bind codes to PKCE/client/resource and rotate refreshes atomically."""
        product = RESOURCES.get(data.get("resource", ""))
        if (
            product is None
            or data.get("scope", f"{product}:incidents") != f"{product}:incidents"
        ):
            raise OAuthError("invalid_target")
        grant = data.get("grant_type")
        if grant not in {"authorization_code", "refresh_token"}:
            raise OAuthError("unsupported_grant_type")
        result: dict[str, Any] = {}
        replay = False
        with self.store._connection() as connection:
            self._schema(connection)
            self._client(connection, data.get("client_id", ""))
            now = int(time.time())
            if grant == "authorization_code":
                row = self._execute(
                    connection,
                    "SELECT * FROM operational_oauth_codes WHERE code_hash=?",
                    (_hash(data.get("code", "")),),
                ).fetchone()
                verifier = data.get("code_verifier", "")
                computed = (
                    base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest())
                    .decode()
                    .rstrip("=")
                )
                if (
                    row is None
                    or row["used"]
                    or row["expires_at"] <= now
                    or row["client_id"] != data["client_id"]
                    or row["redirect_uri"] != data.get("redirect_uri")
                    or not re.fullmatch(r"[A-Za-z0-9._~-]{43,128}", verifier)
                    or not hmac.compare_digest(row["challenge"], computed)
                    or self.store._installation_product(
                        connection, row["connection_id"]
                    )
                    != product
                ):
                    raise OAuthError("invalid_grant")
                session_id = str(uuid4())
                self._execute(
                    connection,
                    "UPDATE operational_oauth_codes SET used=1 WHERE code_hash=?",
                    (_hash(data["code"]),),
                )
                self._execute(
                    connection,
                    "INSERT INTO operational_oauth_sessions VALUES (?,?,?,?,?)",
                    (
                        session_id,
                        row["connection_id"],
                        data["client_id"],
                        0,
                        now + REFRESH_SECONDS,
                    ),
                )
                result = self._tokens(connection, session_id, product)
            else:
                row = self._execute(
                    connection,
                    "SELECT t.*,s.connection_id,s.revoked,s.client_id,s.expires_at AS session_expires FROM operational_oauth_tokens t JOIN operational_oauth_sessions s ON t.session_id=s.session_id WHERE token_hash=?",
                    (_hash(data.get("refresh_token", "")),),
                ).fetchone()
                if (
                    row is None
                    or row["kind"] != "refresh"
                    or row["client_id"] != data["client_id"]
                    or row["revoked"]
                    or row["expires_at"] <= now
                    or row["session_expires"] <= now
                    or self.store._installation_product(
                        connection, row["connection_id"]
                    )
                    != product
                ):
                    raise OAuthError("invalid_grant")
                if row["used"]:
                    self._execute(
                        connection,
                        "UPDATE operational_oauth_sessions SET revoked=1 WHERE session_id=?",
                        (row["session_id"],),
                    )
                    replay = True
                else:
                    self._execute(
                        connection,
                        "UPDATE operational_oauth_tokens SET used=1 WHERE token_hash=?",
                        (_hash(data["refresh_token"]),),
                    )
                    result = self._tokens(connection, row["session_id"], product)
        # Commit revocation before returning the replay error.
        if replay:
            raise OAuthError("invalid_grant")
        return result

    def actor(self, token: str, product: Product = "vera") -> ConnectionActor:
        """Resolve only live access tokens bound to the fixed incident resource."""
        with self.store._connection() as connection:
            self._schema(connection)
            row = self._execute(
                connection,
                "SELECT t.*,s.connection_id,s.revoked,s.expires_at AS session_expires FROM operational_oauth_tokens t JOIN operational_oauth_sessions s ON t.session_id=s.session_id WHERE token_hash=?",
                (_hash(token),),
            ).fetchone()
            now = int(time.time())
            if (
                row is None
                or row["kind"] != "access"
                or row["revoked"]
                or row["expires_at"] <= now
                or row["session_expires"] <= now
                or self.store._installation_product(connection, row["connection_id"])
                != product
            ):
                raise OAuthError("invalid_token")
            identifier = UUID(row["connection_id"])
        return ConnectionActor(identifier, identifier)

    def revoke(self, data: dict[str, str]) -> None:
        """Revoke the connection grant without exposing token existence."""
        with self.store._connection() as connection:
            self._schema(connection)
            row = self._execute(
                connection,
                "SELECT s.session_id,s.client_id FROM operational_oauth_tokens t JOIN operational_oauth_sessions s ON t.session_id=s.session_id WHERE token_hash=?",
                (_hash(data.get("token", "")),),
            ).fetchone()
            if row is not None and row["client_id"] == data.get("client_id"):
                self._execute(
                    connection,
                    "UPDATE operational_oauth_sessions SET revoked=1 WHERE session_id=?",
                    (row["session_id"],),
                )
