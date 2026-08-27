"""Public API and verification page for minimal Vera run receipts."""

from __future__ import annotations

import hmac
import threading
import time
from collections import OrderedDict, deque
from collections.abc import Callable, Coroutine
from datetime import datetime, timezone
from functools import lru_cache
from typing import Annotated, Any, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from fastapi.responses import HTMLResponse, Response
from fastapi.routing import APIRoute
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel, ConfigDict, Field, field_validator

from modules.run_receipts.signing import (
    RunReceiptSigner,
    RunReceiptSigningError,
    get_run_receipt_signer,
)
from modules.run_receipts.store import (
    RunReceiptConflictError,
    RunReceiptRecord,
    RunReceiptStore,
    RunReceiptStoreUnavailableError,
    get_run_receipt_store,
)

__all__ = [
    "RunReceiptStampRequest",
    "RunReceiptStampResponse",
    "api_router",
    "get_run_receipt_rate_limiter",
    "site_router",
]

MAX_REQUEST_BODY_BYTES = 4096
RATE_LIMIT_WINDOW_SECONDS = 60.0
STAMP_PER_SOURCE_LIMIT = 60
STAMP_GLOBAL_LIMIT = 600
VERIFY_PER_SOURCE_LIMIT = 240
VERIFY_GLOBAL_LIMIT = 2400
_SHA256_PATTERN = r"^[0-9a-f]{64}$"
_PLUGIN_VERSION_PATTERN = r"^[0-9]+\.[0-9]+\.[0-9]+(?:[-+][0-9A-Za-z.-]+)?$"

_VERIFY_COPY = {
    "it": {
        "title": "Verifica della ricevuta",
        "verified": "Corrispondenza verificata: il server Mparanza conserva una ricevuta firmata con questo identificativo e questo digest.",
        "missing": "Nessuna ricevuta corrispondente è stata trovata per questa coppia di identificativo e digest.",
        "id": "Identificativo",
        "time": "Marca temporale server",
        "version": "Versione Vera",
        "digest": "Digest del report",
        "key": "Algoritmo e chiave",
        "signature": "Firma valida",
        "yes": "sì",
        "limit": "Questa verifica prova esistenza, data server e integrità del report locale corrispondente. Non prova chi ha presentato il digest, la consegna al provider, la correttezza dell’analisi o la conformità GDPR.",
        "boundary": "Il server non conserva il report, i documenti, i nomi dei file, i dati del cliente o gli hash dei documenti fonte.",
        "link": "Come Mparanza gestisce questi dati",
    },
    "en": {
        "title": "Receipt verification",
        "verified": "Match verified: the Mparanza server retains a signed receipt with this identifier and digest.",
        "missing": "No matching receipt was found for this identifier and digest.",
        "id": "Identifier",
        "time": "Server timestamp",
        "version": "Vera version",
        "digest": "Report digest",
        "key": "Algorithm and key",
        "signature": "Valid signature",
        "yes": "yes",
        "limit": "This verification proves existence, server time, and integrity of the matching local report. It does not prove who submitted the digest, provider-side delivery, analytical correctness, or GDPR compliance.",
        "boundary": "The server does not retain the report, documents, filenames, client data, or source-document hashes.",
        "link": "How Mparanza handles this data",
    },
    "fr": {
        "title": "Vérification du reçu",
        "verified": "Correspondance vérifiée : le serveur Mparanza conserve un reçu signé avec cet identifiant et ce hash.",
        "missing": "Aucun reçu correspondant n’a été trouvé pour cet identifiant et ce hash.",
        "id": "Identifiant",
        "time": "Horodatage serveur",
        "version": "Version de Vera",
        "digest": "Hash du rapport",
        "key": "Algorithme et clé",
        "signature": "Signature valide",
        "yes": "oui",
        "limit": "Cette vérification prouve l’existence, l’heure serveur et l’intégrité du rapport local correspondant. Elle ne prouve pas l’auteur de l’envoi, la transmission au fournisseur, la justesse de l’analyse ou la conformité RGPD.",
        "boundary": "Le serveur ne conserve ni le rapport, ni les documents, ni les noms de fichiers, ni les données client, ni les hash des documents sources.",
        "link": "Comment Mparanza traite ces données",
    },
    "de": {
        "title": "Belegprüfung",
        "verified": "Übereinstimmung bestätigt: Der Mparanza-Server speichert einen signierten Beleg mit dieser ID und diesem Hash.",
        "missing": "Für diese ID und diesen Hash wurde kein passender Beleg gefunden.",
        "id": "Beleg-ID",
        "time": "Serverzeit",
        "version": "Vera-Version",
        "digest": "Berichtshash",
        "key": "Algorithmus und Schlüssel",
        "signature": "Gültige Signatur",
        "yes": "ja",
        "limit": "Diese Prüfung belegt Existenz, Serverzeit und Integrität des zugehörigen lokalen Berichts. Sie beweist weder den Absender noch die Übermittlung an den Provider, analytische Richtigkeit oder DSGVO-Konformität.",
        "boundary": "Der Server speichert weder Bericht noch Dokumente, Dateinamen, Mandantendaten oder Hashes der Quelldokumente.",
        "link": "So verarbeitet Mparanza diese Daten",
    },
    "es": {
        "title": "Verificación del recibo",
        "verified": "Coincidencia verificada: el servidor Mparanza conserva un recibo firmado con este identificador y hash.",
        "missing": "No se encontró un recibo coincidente para este identificador y hash.",
        "id": "Identificador",
        "time": "Hora del servidor",
        "version": "Versión de Vera",
        "digest": "Hash del informe",
        "key": "Algoritmo y clave",
        "signature": "Firma válida",
        "yes": "sí",
        "limit": "Esta verificación prueba existencia, hora del servidor e integridad del informe local correspondiente. No prueba quién presentó el hash, la entrega al proveedor, la corrección analítica ni el cumplimiento del RGPD.",
        "boundary": "El servidor no conserva el informe, los documentos, los nombres de archivo, los datos del cliente ni los hashes de documentos fuente.",
        "link": "Cómo trata Mparanza estos datos",
    },
}

templates = Jinja2Templates(directory="templates")


class RunReceiptRateLimitError(RuntimeError):
    """Raised when a public source exceeds the fixed receipt-service quota."""

    def __init__(self, retry_after_seconds: int) -> None:
        super().__init__("Run-receipt rate limit exceeded.")
        self.retry_after_seconds = retry_after_seconds


class RunReceiptRateLimiter:
    """Bound public stamping and verification with auditable fixed quotas."""

    def __init__(
        self,
        *,
        window_seconds: float = RATE_LIMIT_WINDOW_SECONDS,
        stamp_per_source: int = STAMP_PER_SOURCE_LIMIT,
        stamp_global: int = STAMP_GLOBAL_LIMIT,
        verify_per_source: int = VERIFY_PER_SOURCE_LIMIT,
        verify_global: int = VERIFY_GLOBAL_LIMIT,
        max_sources: int = 4096,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._window_seconds = max(float(window_seconds), 1.0)
        self._limits = {
            "stamp": (max(stamp_per_source, 1), max(stamp_global, 1)),
            "verify": (max(verify_per_source, 1), max(verify_global, 1)),
        }
        self._max_sources = max(max_sources, 1)
        self._clock = clock
        self._source_events: OrderedDict[tuple[str, str], deque[float]] = OrderedDict()
        self._global_events = {action: deque() for action in self._limits}
        self._lock = threading.Lock()

    def check(self, source: str, action: str) -> None:
        """Admit one operation or raise with a bounded retry interval."""

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
                raise RunReceiptRateLimitError(int(self._window_seconds))
            source_events.append(now)
            global_events.append(now)


@lru_cache(maxsize=1)
def get_run_receipt_rate_limiter() -> RunReceiptRateLimiter:
    """Return the process-wide receipt-service limiter."""

    return RunReceiptRateLimiter()


class _BoundedRunReceiptRoute(APIRoute):
    """Reject oversized receipt requests before JSON parsing."""

    def get_route_handler(
        self,
    ) -> Callable[[Request], Coroutine[Any, Any, Response]]:
        original_handler = super().get_route_handler()

        async def bounded_handler(request: Request) -> Response:
            if request.method == "POST":
                raw_length = request.headers.get("content-length")
                if raw_length:
                    try:
                        declared_length = int(raw_length)
                    except ValueError as exc:
                        raise HTTPException(
                            status_code=status.HTTP_400_BAD_REQUEST,
                            detail="Invalid Content-Length header.",
                        ) from exc
                    if declared_length < 0 or declared_length > MAX_REQUEST_BODY_BYTES:
                        raise HTTPException(
                            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                            detail="Run-receipt body is too large.",
                        )
                body = bytearray()
                async for chunk in request.stream():
                    body.extend(chunk)
                    if len(body) > MAX_REQUEST_BODY_BYTES:
                        raise HTTPException(
                            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                            detail="Run-receipt body is too large.",
                        )
                setattr(request, "_body", bytes(body))
            response = await original_handler(request)
            response.headers["Cache-Control"] = "no-store"
            return response

        return bounded_handler


api_router = APIRouter(
    prefix="/api/vera/run-receipts",
    tags=["vera-run-receipts"],
    route_class=_BoundedRunReceiptRoute,
)
site_router = APIRouter(tags=["vera-run-receipts"])

Store = Annotated[RunReceiptStore, Depends(get_run_receipt_store)]
Signer = Annotated[RunReceiptSigner, Depends(get_run_receipt_signer)]
RateLimiter = Annotated[RunReceiptRateLimiter, Depends(get_run_receipt_rate_limiter)]


class RunReceiptStampRequest(BaseModel):
    """The complete field allow-list accepted from a Vera run."""

    model_config = ConfigDict(extra="forbid")

    schema_version: Literal[1] = 1
    receipt_id: UUID
    plugin_version: str = Field(
        min_length=5, max_length=64, pattern=_PLUGIN_VERSION_PATTERN
    )
    report_sha256: str = Field(pattern=_SHA256_PATTERN)


class RunReceiptStampResponse(BaseModel):
    """Portable proof returned to the firm and its customer."""

    model_config = ConfigDict(extra="forbid")

    schema_version: Literal[1] = 1
    receipt_id: UUID
    plugin_version: str
    report_sha256: str
    stamped_at: str
    key_id: str
    algorithm: Literal["Ed25519"] = "Ed25519"
    signature: str
    public_key: str
    verification_url: str
    signature_valid: bool

    @field_validator("stamped_at")
    @classmethod
    def require_timezone(cls, value: str) -> str:
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError as exc:
            raise ValueError("stamped_at must be an RFC 3339 timestamp") from exc
        if parsed.tzinfo is None or parsed.utcoffset() is None or "T" not in value:
            raise ValueError("stamped_at must include a timezone")
        return value


def _enforce_rate_limit(
    request: Request, limiter: RunReceiptRateLimiter, action: str
) -> None:
    source = request.client.host if request.client is not None else "unknown"
    try:
        limiter.check(source, action)
    except RunReceiptRateLimitError as exc:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Too many run-receipt operations. Try again shortly.",
            headers={"Retry-After": str(exc.retry_after_seconds)},
        ) from exc


def _server_timestamp() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _verification_url(record: RunReceiptRecord) -> str:
    return (
        f"https://mparanza.com/verify/vera-run-receipt/{record.receipt_id}"
        f"?sha256={record.report_sha256}"
    )


def _response(
    record: RunReceiptRecord, signer: RunReceiptSigner
) -> RunReceiptStampResponse:
    verified = signer.verify(record.signed_payload, record.signature)
    public_key = signer.public_key_base64url(record.key_id)
    if verified is not True or public_key is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="The receipt verification key is unavailable or invalid.",
        )
    return RunReceiptStampResponse(
        **record.signed_payload,
        algorithm="Ed25519",
        signature=record.signature,
        public_key=public_key,
        verification_url=_verification_url(record),
        signature_valid=True,
    )


@api_router.post(
    "",
    response_model=RunReceiptStampResponse,
    status_code=status.HTTP_201_CREATED,
)
def stamp_run_receipt(
    payload: RunReceiptStampRequest,
    request: Request,
    store: Store,
    signer: Signer,
    limiter: RateLimiter,
) -> RunReceiptStampResponse:
    """Timestamp, sign, and retain only one minimal per-run proof record."""

    _enforce_rate_limit(request, limiter, "stamp")
    signed_payload = {
        "schema_version": 1,
        "receipt_id": str(payload.receipt_id),
        "plugin_version": payload.plugin_version,
        "report_sha256": payload.report_sha256,
        "stamped_at": _server_timestamp(),
        "key_id": signer.key_id,
    }
    try:
        candidate = RunReceiptRecord(
            receipt_id=signed_payload["receipt_id"],
            plugin_version=signed_payload["plugin_version"],
            report_sha256=signed_payload["report_sha256"],
            stamped_at=signed_payload["stamped_at"],
            key_id=signed_payload["key_id"],
            signature=signer.sign(signed_payload),
        )
        record = store.stamp(candidate)
    except RunReceiptConflictError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail=str(exc)
        ) from exc
    except RunReceiptStoreUnavailableError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Run-receipt storage is temporarily unavailable.",
        ) from exc
    except RunReceiptSigningError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Run-receipt signing is temporarily unavailable.",
        ) from exc
    return _response(record, signer)


@api_router.get("/{receipt_id}", response_model=RunReceiptStampResponse)
def verify_run_receipt(
    receipt_id: UUID,
    request: Request,
    store: Store,
    signer: Signer,
    limiter: RateLimiter,
    sha256: str = Query(pattern=_SHA256_PATTERN),
) -> RunReceiptStampResponse:
    """Verify that the supplied digest matches one valid retained proof."""

    _enforce_rate_limit(request, limiter, "verify")
    try:
        record = store.get(str(receipt_id))
    except RunReceiptStoreUnavailableError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Run-receipt storage is temporarily unavailable.",
        ) from exc
    if record is None or not hmac.compare_digest(record.report_sha256, sha256):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No matching Vera run receipt was found.",
        )
    return _response(record, signer)


@site_router.get(
    "/verify/vera-run-receipt/{receipt_id}",
    response_class=HTMLResponse,
    include_in_schema=False,
)
def verify_run_receipt_page(
    receipt_id: UUID,
    request: Request,
    store: Store,
    signer: Signer,
    limiter: RateLimiter,
    sha256: str = Query(pattern=_SHA256_PATTERN),
    lang: str = Query(default="it", pattern=r"^(it|en|fr|de|es)$"),
) -> HTMLResponse:
    """Render a customer-readable verification result without case content."""

    try:
        response = verify_run_receipt(
            receipt_id=receipt_id,
            request=request,
            store=store,
            signer=signer,
            limiter=limiter,
            sha256=sha256,
        )
        receipt = response.model_dump(mode="json")
        verified = True
    except HTTPException as exc:
        if exc.status_code not in {status.HTTP_404_NOT_FOUND}:
            raise
        receipt = None
        verified = False
    rendered = templates.TemplateResponse(
        request,
        "vera_run_receipt_verify.html",
        {
            "receipt": receipt,
            "verified": verified,
            "receipt_id": str(receipt_id),
            "report_sha256": sha256,
            "lang": lang,
            "copy": _VERIFY_COPY[lang],
        },
        status_code=status.HTTP_200_OK if verified else status.HTTP_404_NOT_FOUND,
    )
    rendered.headers["Cache-Control"] = "no-store"
    return rendered
