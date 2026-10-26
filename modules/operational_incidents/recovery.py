"""Browser-held reporting identity independent of the installed plugin runtime."""

from __future__ import annotations

import hashlib
import secrets
import time
from uuid import UUID, uuid4

from modules.operational_incidents.contracts import Credentials
from modules.operational_incidents.store import ConnectionActor, IncidentStore
from modules.workflow_usage.products import Product

__all__ = ["RecoverySessions", "RecoverySessionError", "SESSION_SECONDS"]

SESSION_SECONDS = 90 * 24 * 3600
_SCHEMA = (
    "CREATE TABLE IF NOT EXISTS operational_recovery_sessions "
    "(token_hash TEXT PRIMARY KEY, connection_id TEXT NOT NULL, expires_at BIGINT NOT NULL)"
)
_TRANSFER_SCHEMA = (
    "CREATE TABLE IF NOT EXISTS operational_recovery_transfers "
    "(code_hash TEXT PRIMARY KEY, connection_id TEXT NOT NULL, expires_at BIGINT NOT NULL, used INTEGER NOT NULL)"
)


class RecoverySessionError(ValueError):
    """A missing or expired browser identity, without credential disclosure."""


class RecoverySessions:
    """Keep capabilities in HttpOnly cookies and only their hashes in the store."""

    def __init__(self, store: IncidentStore) -> None:
        self.store = store

    def create(self, product: Product) -> tuple[str, ConnectionActor]:
        """Create an anonymous browser identity without executing plugin code."""
        owner = Credentials(
            installation_id=uuid4(), installation_key=secrets.token_urlsafe(32)
        )
        self.store.register(owner, product=product)
        actor = ConnectionActor(owner.installation_id, owner.installation_id)
        return self.bind(actor), actor

    def bind(self, actor: ConnectionActor) -> str:
        """Retain an already authenticated connection identity in a new browser."""
        self.store.product(actor)
        token = secrets.token_urlsafe(48)
        with self.store._connection() as connection:
            self.store._schema(connection)
            connection.execute(_SCHEMA)
            connection.execute(
                self.store._sql(
                    "INSERT INTO operational_recovery_sessions VALUES (?,?,?)"
                ),
                (
                    hashlib.sha256(token.encode()).hexdigest(),
                    str(actor.connection_id),
                    int(time.time()) + SESSION_SECONDS,
                ),
            )
        return token

    def actor(self, token: str, product: Product) -> ConnectionActor:
        """Reject foreign/expired cookies without silently replacing ownership."""
        if not token or len(token) > 128:
            raise RecoverySessionError("Reporting browser session is unavailable")
        with self.store._connection() as connection:
            self.store._schema(connection)
            connection.execute(_SCHEMA)
            row = connection.execute(
                self.store._sql(
                    "SELECT connection_id, expires_at FROM operational_recovery_sessions "
                    "WHERE token_hash=?"
                ),
                (hashlib.sha256(token.encode()).hexdigest(),),
            ).fetchone()
        if row is None or row["expires_at"] <= int(time.time()):
            raise RecoverySessionError("Reporting browser session is unavailable")
        identifier = UUID(row["connection_id"])
        actor = ConnectionActor(identifier, identifier)
        if self.store.product(actor) != product:
            raise RecoverySessionError("Reporting browser session is unavailable")
        return actor

    def transfer(self, actor: ConnectionActor) -> str:
        """Bind an authenticated owner to a short-lived, single-use restore proof."""
        self.store.product(actor)
        code = secrets.token_urlsafe(48)
        with self.store._connection() as connection:
            self.store._schema(connection)
            connection.execute(_TRANSFER_SCHEMA)
            connection.execute(
                self.store._sql(
                    "INSERT INTO operational_recovery_transfers VALUES (?,?,?,0)"
                ),
                (
                    hashlib.sha256(code.encode()).hexdigest(),
                    str(actor.connection_id),
                    int(time.time()) + 300,
                ),
            )
        return code

    def restore(
        self,
        code: str,
        product: Product,
        current_actor: ConnectionActor | None = None,
    ) -> tuple[str, ConnectionActor]:
        """Transfer the original namespace atomically without copying its reports."""
        if not code or len(code) > 128:
            raise RecoverySessionError("Reporting identity transfer is unavailable")
        members: list[str] = []
        if current_actor is not None:
            if self.store.product(current_actor) != product:
                raise RecoverySessionError("Reporting identity transfer is unavailable")
            members = self.store.connection_members(current_actor)
        digest = hashlib.sha256(code.encode()).hexdigest()
        token = secrets.token_urlsafe(48)
        with self.store._connection() as connection:
            self.store._schema(connection)
            connection.execute(_TRANSFER_SCHEMA)
            connection.execute(_SCHEMA)
            row = connection.execute(
                self.store._sql(
                    "SELECT * FROM operational_recovery_transfers WHERE code_hash=?"
                ),
                (digest,),
            ).fetchone()
            if (
                row is None
                or row["used"]
                or row["expires_at"] <= int(time.time())
                or self.store._installation_product(connection, row["connection_id"])
                != product
            ):
                raise RecoverySessionError("Reporting identity transfer is unavailable")
            consumed = connection.execute(
                self.store._sql(
                    "UPDATE operational_recovery_transfers SET used=1 WHERE code_hash=? AND used=0"
                ),
                (digest,),
            )
            if consumed.rowcount != 1:
                raise RecoverySessionError("Reporting identity transfer is unavailable")
            # Both the current cookie and the transfer code prove ownership.
            # Preserve access to any earlier browser reports and linked local
            # runs, retaining each record's original installation identity.
            for member in members:
                if member != row["connection_id"]:
                    connection.execute(
                        self.store._sql(
                            "INSERT INTO operational_connection_links VALUES (?,?) "
                            "ON CONFLICT (connection_id,installation_id) DO NOTHING"
                        ),
                        (row["connection_id"], member),
                    )
            connection.execute(
                self.store._sql(
                    "INSERT INTO operational_recovery_sessions VALUES (?,?,?)"
                ),
                (
                    hashlib.sha256(token.encode()).hexdigest(),
                    row["connection_id"],
                    int(time.time()) + SESSION_SECONDS,
                ),
            )
        identifier = UUID(row["connection_id"])
        return token, ConnectionActor(identifier, identifier)
