#!/usr/bin/env python3
"""Create and verify server-stamped proofs for Vera model-data reports.

The Mparanza service receives only an opaque receipt UUID, the Vera version,
and the SHA-256 digest of the canonical local report. It never receives the
report, run ID, workflow ID, source filenames, source hashes, or case content.
"""

from __future__ import annotations

import argparse
import base64
import hashlib
import html
import json
import os
import re
import sys
import tempfile
import urllib.error
import urllib.parse
import urllib.request
import uuid
from collections.abc import Callable, Mapping, Sequence
from datetime import datetime
from pathlib import Path
from typing import Any

__all__ = [
    "NotarizedRunReceiptError",
    "build_receipt_request",
    "main",
    "stamp_model_data_report",
    "verify_model_data_receipt",
]

RECEIPT_ENDPOINT = "https://mparanza.com/api/vera/run-receipts"
_ENDPOINT_ENV = "VERA_RUN_RECEIPT_ENDPOINT"
_REQUEST_FILE = "model_data_receipt_request.json"
_RECEIPT_FILE = "model_data_receipt.json"
_HTML_FILE = "model_data_receipt.html"
_REPORT_FILE = "model_data_report.json"
_MAX_RESPONSE_BYTES = 64 * 1024
_NETWORK_TIMEOUT_SECONDS = 10.0
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_VERSION_RE = re.compile(r"^[0-9]+\.[0-9]+\.[0-9]+(?:[-+][0-9A-Za-z.-]+)?$")
_BASE64URL_RE = re.compile(r"^[A-Za-z0-9_-]+$")
_RESPONSE_FIELDS = {
    "schema_version",
    "receipt_id",
    "plugin_version",
    "report_sha256",
    "stamped_at",
    "key_id",
    "algorithm",
    "signature",
    "public_key",
    "verification_url",
    "signature_valid",
}

_COPY = {
    "it": {
        "lang": "it",
        "title": "Ricevuta della lavorazione Vera",
        "eyebrow": "Vera · evidenza per esecuzione",
        "lead": (
            "Questa ricevuta collega il report locale sui dati arrivati al modello "
            "a una marca temporale e a una firma del server Mparanza."
        ),
        "verified": "Ricevuta firmata dal server",
        "workflow": "Processo Vera",
        "run": "Esecuzione locale",
        "purpose": "Scopo professionale",
        "stamp": "Marca temporale server",
        "version": "Versione Vera",
        "receipt": "Identificativo della ricevuta",
        "digest": "Digest del report locale",
        "phases": "Che cosa registra il report locale",
        "phase": "Fase",
        "outcome": "Esito",
        "source": "Fonte disponibile",
        "processed": "Elaborato localmente",
        "visible": "Visibile al modello",
        "local": "Mai visibile al modello",
        "improvement": "Possibile miglioramento supportato dal report",
        "reduction": "Riduzione stimata",
        "safeguard": "Protezione della qualità",
        "verify": "Verifica sul server Mparanza",
        "print": "Stampa o salva in PDF",
        "technical": "Dettagli della firma",
        "digest_check": "Integrità del report incorporato",
        "signature_check": "Firma Ed25519 incorporata",
        "checking": "verifica in corso",
        "valid": "valida",
        "invalid": "non valida",
        "unavailable": "non disponibile in questo browser; usa la verifica server",
        "limit": (
            "La ricevuta prova esistenza, data server e integrità del report "
            "corrispondente. Non prova chi ha presentato il digest, la consegna lato "
            "provider, la correttezza dell’analisi, la necessità semantica o la "
            "conformità GDPR."
        ),
        "server": (
            "Il server conserva soltanto identificativo opaco, data, versione Vera, "
            "digest del report, firma e identificativo della chiave. Il report, i dati "
            "del cliente, i nomi dei file, i contenuti e gli hash dei documenti fonte "
            "restano locali."
        ),
    },
    "en": {
        "lang": "en",
        "title": "Vera run receipt",
        "eyebrow": "Vera · per-run evidence",
        "lead": (
            "This receipt binds the local model-data report to a Mparanza server "
            "timestamp and signature."
        ),
        "verified": "Server-signed receipt",
        "workflow": "Vera workflow",
        "run": "Local run",
        "purpose": "Professional purpose",
        "stamp": "Server timestamp",
        "version": "Vera version",
        "receipt": "Receipt identifier",
        "digest": "Local report digest",
        "phases": "What the local report records",
        "phase": "Phase",
        "outcome": "Outcome",
        "source": "Available source",
        "processed": "Processed locally",
        "visible": "Model-visible",
        "local": "Never model-visible",
        "improvement": "Potential improvement supported by the report",
        "reduction": "Estimated reduction",
        "safeguard": "Quality safeguard",
        "verify": "Verify on the Mparanza server",
        "print": "Print or save as PDF",
        "technical": "Signature details",
        "digest_check": "Embedded report integrity",
        "signature_check": "Embedded Ed25519 signature",
        "checking": "checking",
        "valid": "valid",
        "invalid": "invalid",
        "unavailable": "unavailable in this browser; use server verification",
        "limit": (
            "The receipt proves existence, server time, and integrity of the matching "
            "report. It does not prove who submitted the digest, provider-side delivery, "
            "analytical correctness, semantic necessity, or GDPR compliance."
        ),
        "server": (
            "The server retains only an opaque identifier, time, Vera version, report "
            "digest, signature, and key identifier. The report, client data, filenames, "
            "content, and source-document hashes stay local."
        ),
    },
    "fr": {
        "lang": "fr",
        "title": "Reçu d’exécution Vera",
        "eyebrow": "Vera · preuve par exécution",
        "lead": "Ce reçu relie le rapport local sur les données du modèle à l’heure et à la signature du serveur Mparanza.",
        "verified": "Reçu signé par le serveur",
        "workflow": "Workflow Vera",
        "run": "Exécution locale",
        "purpose": "Finalité professionnelle",
        "stamp": "Horodatage serveur",
        "version": "Version de Vera",
        "receipt": "Identifiant du reçu",
        "digest": "Hash du rapport local",
        "phases": "Ce que consigne le rapport local",
        "phase": "Phase",
        "outcome": "Résultat",
        "source": "Source disponible",
        "processed": "Traité localement",
        "visible": "Visible par le modèle",
        "local": "Jamais visible par le modèle",
        "improvement": "Amélioration possible étayée par le rapport",
        "reduction": "Réduction estimée",
        "safeguard": "Protection de la qualité",
        "verify": "Vérifier sur le serveur Mparanza",
        "print": "Imprimer ou enregistrer en PDF",
        "technical": "Détails de la signature",
        "digest_check": "Intégrité du rapport incorporé",
        "signature_check": "Signature Ed25519 incorporée",
        "checking": "vérification en cours",
        "valid": "valide",
        "invalid": "non valide",
        "unavailable": "indisponible dans ce navigateur ; utilisez la vérification serveur",
        "limit": "Le reçu prouve uniquement l’existence, l’heure serveur et l’intégrité du rapport correspondant. Il ne prouve pas l’auteur de l’envoi du hash, la transmission côté fournisseur, la justesse de l’analyse, la nécessité sémantique ou la conformité RGPD.",
        "server": "Le serveur conserve uniquement un identifiant opaque, l’heure, la version de Vera, le hash du rapport, la signature et l’identifiant de clé. Le rapport, les données client, les noms de fichiers, les contenus et les hash des documents sources restent locaux.",
    },
    "de": {
        "lang": "de",
        "title": "Vera-Ausführungsbeleg",
        "eyebrow": "Vera · Nachweis je Ausführung",
        "lead": "Dieser Beleg bindet den lokalen Modelldatenbericht an Serverzeit und Signatur von Mparanza.",
        "verified": "Serverseitig signierter Beleg",
        "workflow": "Vera-Workflow",
        "run": "Lokale Ausführung",
        "purpose": "Beruflicher Zweck",
        "stamp": "Serverzeit",
        "version": "Vera-Version",
        "receipt": "Beleg-ID",
        "digest": "Hash des lokalen Berichts",
        "phases": "Inhalt des lokalen Berichts",
        "phase": "Phase",
        "outcome": "Ergebnis",
        "source": "Verfügbare Quelle",
        "processed": "Lokal verarbeitet",
        "visible": "Für das Modell sichtbar",
        "local": "Nie für das Modell sichtbar",
        "improvement": "Vom Bericht gestützte mögliche Verbesserung",
        "reduction": "Geschätzte Reduktion",
        "safeguard": "Qualitätssicherung",
        "verify": "Auf dem Mparanza-Server prüfen",
        "print": "Drucken oder als PDF speichern",
        "technical": "Signaturdetails",
        "digest_check": "Integrität des eingebetteten Berichts",
        "signature_check": "Eingebettete Ed25519-Signatur",
        "checking": "Prüfung läuft",
        "valid": "gültig",
        "invalid": "ungültig",
        "unavailable": "in diesem Browser nicht verfügbar; Serverprüfung verwenden",
        "limit": "Der Beleg weist nur Existenz, Serverzeit und Integrität des zugehörigen Berichts nach. Er beweist weder den Absender des Hashes noch die Übermittlung an den Provider, analytische Richtigkeit, semantische Erforderlichkeit oder DSGVO-Konformität.",
        "server": "Der Server speichert nur eine undurchsichtige ID, Zeit, Vera-Version, Berichtshash, Signatur und Schlüssel-ID. Bericht, Mandantendaten, Dateinamen, Inhalte und Hashes der Quelldokumente bleiben lokal.",
    },
    "es": {
        "lang": "es",
        "title": "Recibo de ejecución de Vera",
        "eyebrow": "Vera · evidencia por ejecución",
        "lead": "Este recibo vincula el informe local de datos del modelo con la hora y la firma del servidor Mparanza.",
        "verified": "Recibo firmado por el servidor",
        "workflow": "Flujo Vera",
        "run": "Ejecución local",
        "purpose": "Finalidad profesional",
        "stamp": "Hora del servidor",
        "version": "Versión de Vera",
        "receipt": "Identificador del recibo",
        "digest": "Hash del informe local",
        "phases": "Qué registra el informe local",
        "phase": "Fase",
        "outcome": "Resultado",
        "source": "Fuente disponible",
        "processed": "Procesado localmente",
        "visible": "Visible para el modelo",
        "local": "Nunca visible para el modelo",
        "improvement": "Posible mejora respaldada por el informe",
        "reduction": "Reducción estimada",
        "safeguard": "Protección de la calidad",
        "verify": "Verificar en el servidor Mparanza",
        "print": "Imprimir o guardar como PDF",
        "technical": "Detalles de la firma",
        "digest_check": "Integridad del informe incorporado",
        "signature_check": "Firma Ed25519 incorporada",
        "checking": "verificando",
        "valid": "válida",
        "invalid": "no válida",
        "unavailable": "no disponible en este navegador; use la verificación del servidor",
        "limit": "El recibo solo prueba existencia, hora del servidor e integridad del informe correspondiente. No prueba quién presentó el hash, la entrega al proveedor, la corrección analítica, la necesidad semántica ni el cumplimiento del RGPD.",
        "server": "El servidor conserva únicamente un identificador opaco, la hora, la versión de Vera, el hash del informe, la firma y el identificador de clave. El informe, los datos del cliente, los nombres de archivo, el contenido y los hashes de los documentos fuente permanecen locales.",
    },
}

_OUTCOME_COPY = {
    "it": {
        "reduced_projection": "Proiezione ridotta",
        "full_context_required": "Contesto completo necessario",
        "no_case_data": "Nessun dato del caso",
        "not_measurable": "Non misurabile",
    },
    "en": {
        "reduced_projection": "Reduced projection",
        "full_context_required": "Full context required",
        "no_case_data": "No case data",
        "not_measurable": "Not measurable",
    },
    "fr": {
        "reduced_projection": "Projection réduite",
        "full_context_required": "Contexte complet nécessaire",
        "no_case_data": "Aucune donnée du dossier",
        "not_measurable": "Non mesurable",
    },
    "de": {
        "reduced_projection": "Reduzierte Projektion",
        "full_context_required": "Vollständiger Kontext erforderlich",
        "no_case_data": "Keine Falldaten",
        "not_measurable": "Nicht messbar",
    },
    "es": {
        "reduced_projection": "Proyección reducida",
        "full_context_required": "Contexto completo necesario",
        "no_case_data": "Sin datos del caso",
        "not_measurable": "No medible",
    },
}


class NotarizedRunReceiptError(RuntimeError):
    """Raised when a receipt cannot be created or verified safely."""


def _canonical_bytes(payload: object) -> bytes:
    return (
        json.dumps(
            payload,
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        )
        + "\n"
    ).encode("utf-8")


def _exact_fields(payload: Mapping[str, Any], fields: set[str], *, label: str) -> None:
    missing = fields - set(payload)
    unexpected = set(payload) - fields
    if missing or unexpected:
        raise NotarizedRunReceiptError(
            f"{label} fields invalid; missing={sorted(missing)}, "
            f"unexpected={sorted(unexpected)}"
        )


def _atomic_write(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(
        dir=path.parent, prefix=f".{path.name}.", suffix=".tmp"
    )
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        if temporary.exists():
            temporary.unlink()


def _write_once_or_identical(path: Path, data: bytes) -> None:
    if path.exists():
        if path.is_symlink() or not path.is_file():
            raise NotarizedRunReceiptError(
                f"refusing to replace non-regular output: {path.name}"
            )
        if path.read_bytes() != data:
            raise NotarizedRunReceiptError(
                f"refusing to replace different receipt output: {path.name}"
            )
        return
    _atomic_write(path, data)


def _plugin_version(plugin_root: Path) -> str:
    manifest_path = next(
        (
            candidate
            for candidate in (
                plugin_root / ".codex-plugin" / "plugin.json",
                plugin_root / ".claude-plugin" / "plugin.json",
            )
            if candidate.is_file() and not candidate.is_symlink()
        ),
        None,
    )
    if manifest_path is None:
        raise NotarizedRunReceiptError("Vera plugin manifest is unavailable")
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise NotarizedRunReceiptError("Vera plugin manifest is invalid") from exc
    version = manifest.get("version") if isinstance(manifest, dict) else None
    if not isinstance(version, str) or _VERSION_RE.fullmatch(version) is None:
        raise NotarizedRunReceiptError("Vera plugin version is invalid")
    return version


def _validated_report(path: Path) -> dict[str, Any]:
    if path.is_symlink() or not path.is_file():
        raise NotarizedRunReceiptError("model-data report must be a regular JSON file")
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise NotarizedRunReceiptError("model-data report is invalid JSON") from exc
    if not isinstance(payload, dict):
        raise NotarizedRunReceiptError("model-data report must be an object")
    try:
        from model_data_report import validate_model_data_report

        return validate_model_data_report(payload)
    except ImportError as exc:
        raise NotarizedRunReceiptError(
            "model-data report validator is unavailable"
        ) from exc


def build_receipt_request(
    report: Mapping[str, Any], *, receipt_id: str, plugin_version: str
) -> dict[str, Any]:
    """Build the complete field allow-list that may reach Mparanza."""

    try:
        canonical_receipt_id = str(uuid.UUID(receipt_id))
    except ValueError as exc:
        raise NotarizedRunReceiptError("receipt_id must be a UUID") from exc
    report_sha256 = hashlib.sha256(_canonical_bytes(report)).hexdigest()
    return {
        "schema_version": 1,
        "receipt_id": canonical_receipt_id,
        "plugin_version": plugin_version,
        "report_sha256": report_sha256,
    }


def _request_for_run(
    path: Path, report: Mapping[str, Any], *, plugin_version: str
) -> dict[str, Any]:
    if path.exists():
        if path.is_symlink() or not path.is_file():
            raise NotarizedRunReceiptError("receipt request must be a regular file")
        try:
            existing = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise NotarizedRunReceiptError("receipt request is invalid") from exc
        if not isinstance(existing, dict):
            raise NotarizedRunReceiptError("receipt request must be an object")
        _exact_fields(
            existing,
            {"schema_version", "receipt_id", "plugin_version", "report_sha256"},
            label="receipt request",
        )
        expected = build_receipt_request(
            report,
            receipt_id=str(existing["receipt_id"]),
            plugin_version=plugin_version,
        )
        if existing != expected:
            raise NotarizedRunReceiptError(
                "existing receipt request belongs to different run evidence"
            )
        return existing
    request = build_receipt_request(
        report,
        receipt_id=str(uuid.uuid4()),
        plugin_version=plugin_version,
    )
    _write_once_or_identical(path, _canonical_bytes(request))
    return request


def _validate_endpoint(value: str) -> str:
    parsed = urllib.parse.urlsplit(value)
    expected_path = "/api/vera/run-receipts"
    production = (
        parsed.scheme == "https"
        and parsed.hostname == "mparanza.com"
        and parsed.port is None
        and parsed.path == expected_path
        and not parsed.query
        and not parsed.fragment
    )
    loopback = (
        parsed.scheme == "http"
        and parsed.hostname in {"127.0.0.1", "localhost"}
        and parsed.port is not None
        and parsed.path == expected_path
        and not parsed.query
        and not parsed.fragment
    )
    if not production and not loopback:
        raise NotarizedRunReceiptError(
            "receipt endpoint must be Mparanza HTTPS or an explicit loopback test port"
        )
    return value


def _configured_endpoint() -> str:
    value = os.environ.get(_ENDPOINT_ENV, "").strip() or RECEIPT_ENDPOINT
    return _validate_endpoint(value)


def _read_bounded_response(response: Any) -> bytes:
    data = response.read(_MAX_RESPONSE_BYTES + 1)
    if len(data) > _MAX_RESPONSE_BYTES:
        raise NotarizedRunReceiptError("receipt service response is too large")
    return data


def _request_json(
    request: urllib.request.Request,
    *,
    opener: Callable[..., Any],
) -> dict[str, Any]:
    try:
        with opener(
            request, timeout=_NETWORK_TIMEOUT_SECONDS
        ) as response:  # nosec B310
            data = _read_bounded_response(response)
    except urllib.error.HTTPError as exc:
        detail = exc.read(4096).decode("utf-8", errors="replace")
        raise NotarizedRunReceiptError(
            f"receipt service rejected the request ({exc.code}): {detail}"
        ) from exc
    except (OSError, TimeoutError, urllib.error.URLError) as exc:
        raise NotarizedRunReceiptError("receipt service is unavailable") from exc
    try:
        payload = json.loads(data.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise NotarizedRunReceiptError("receipt service returned invalid JSON") from exc
    if not isinstance(payload, dict):
        raise NotarizedRunReceiptError("receipt service returned a non-object response")
    return payload


def _post_receipt_request(
    endpoint: str,
    payload: Mapping[str, Any],
    *,
    opener: Callable[..., Any],
) -> dict[str, Any]:
    body = _canonical_bytes(payload)
    request = urllib.request.Request(
        _validate_endpoint(endpoint),
        data=body,
        headers={
            "Accept": "application/json",
            "Content-Type": "application/json",
            "User-Agent": "Vera-Run-Receipt/1",
        },
        method="POST",
    )
    return _request_json(request, opener=opener)


def _validate_verification_url(value: object, *, receipt_id: str, digest: str) -> str:
    if not isinstance(value, str):
        raise NotarizedRunReceiptError("verification_url must be text")
    parsed = urllib.parse.urlsplit(value)
    query = urllib.parse.parse_qs(parsed.query, strict_parsing=True)
    valid = (
        parsed.scheme == "https"
        and parsed.hostname == "mparanza.com"
        and parsed.port is None
        and parsed.path == f"/verify/vera-run-receipt/{receipt_id}"
        and query == {"sha256": [digest]}
        and not parsed.fragment
    )
    if not valid:
        raise NotarizedRunReceiptError(
            "receipt service returned an unsafe verification URL"
        )
    return value


def _validate_response(
    payload: Mapping[str, Any], request: Mapping[str, Any]
) -> dict[str, Any]:
    _exact_fields(payload, _RESPONSE_FIELDS, label="receipt response")
    for field in ("schema_version", "receipt_id", "plugin_version", "report_sha256"):
        if payload[field] != request[field]:
            raise NotarizedRunReceiptError(
                f"receipt response {field} does not match the request"
            )
    if payload["algorithm"] != "Ed25519" or payload["signature_valid"] is not True:
        raise NotarizedRunReceiptError(
            "receipt service did not return a valid signature"
        )
    for field in ("stamped_at", "key_id", "signature", "public_key"):
        if not isinstance(payload[field], str) or not payload[field].strip():
            raise NotarizedRunReceiptError(f"receipt response {field} is invalid")
    try:
        stamped_at = datetime.fromisoformat(
            str(payload["stamped_at"]).replace("Z", "+00:00")
        )
    except ValueError as exc:
        raise NotarizedRunReceiptError(
            "receipt response stamped_at is invalid"
        ) from exc
    if stamped_at.tzinfo is None or stamped_at.utcoffset() is None:
        raise NotarizedRunReceiptError(
            "receipt response stamped_at must include a timezone"
        )
    for field, expected_bytes in (("public_key", 32), ("signature", 64)):
        encoded = str(payload[field])
        if _BASE64URL_RE.fullmatch(encoded) is None:
            raise NotarizedRunReceiptError(
                f"receipt response {field} is not valid base64url"
            )
        try:
            decoded = base64.urlsafe_b64decode(encoded + "=" * (-len(encoded) % 4))
        except ValueError as exc:
            raise NotarizedRunReceiptError(
                f"receipt response {field} is not valid base64url"
            ) from exc
        if len(decoded) != expected_bytes:
            raise NotarizedRunReceiptError(
                f"receipt response {field} has an invalid length"
            )
    if _SHA256_RE.fullmatch(str(payload["report_sha256"])) is None:
        raise NotarizedRunReceiptError("receipt response digest is invalid")
    receipt_id = str(payload["receipt_id"])
    _validate_verification_url(
        payload["verification_url"],
        receipt_id=receipt_id,
        digest=str(payload["report_sha256"]),
    )
    return dict(payload)


def _format_measurements(values: object) -> str:
    if not isinstance(values, Sequence) or isinstance(values, (str, bytes)):
        return "—"
    rendered: list[str] = []
    for value in values:
        if not isinstance(value, Mapping):
            continue
        rendered.append(
            f"{html.escape(str(value.get('quantity', '')))} "
            f"{html.escape(str(value.get('unit', '')))} — "
            f"{html.escape(str(value.get('label', '')))}"
        )
    return "; ".join(rendered) or "—"


def _signed_receipt_bytes(receipt: Mapping[str, Any]) -> bytes:
    payload = {
        field: receipt[field]
        for field in (
            "schema_version",
            "receipt_id",
            "plugin_version",
            "report_sha256",
            "stamped_at",
            "key_id",
        )
    }
    return json.dumps(
        payload,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")


def _improvement_html(report: Mapping[str, Any], copy: Mapping[str, str]) -> str:
    assessment = report.get("improvement_assessment")
    if not isinstance(assessment, Mapping) or assessment.get("status") != "candidate":
        return ""
    candidates = assessment.get("candidates")
    if not isinstance(candidates, Sequence):
        return ""
    items: list[str] = []
    for candidate in candidates:
        if not isinstance(candidate, Mapping):
            continue
        items.append(
            '<article class="improvement">'
            f"<h3>{html.escape(str(candidate.get('change', '')))}</h3>"
            f"<p><strong>{copy['reduction']}:</strong> "
            f"{_format_measurements(candidate.get('estimated_reduction'))}</p>"
            f"<p><strong>{copy['safeguard']}:</strong> "
            f"{html.escape(str(candidate.get('quality_safeguard', '')))}</p>"
            "</article>"
        )
    if not items:
        return ""
    return f"<h2>{copy['improvement']}</h2>{''.join(items)}"


def _render_html(report: Mapping[str, Any], receipt: Mapping[str, Any]) -> str:
    language = str(report.get("language") or "en")
    copy = _COPY.get(language, _COPY["en"])
    outcome_copy = _OUTCOME_COPY.get(language, _OUTCOME_COPY["en"])
    rows: list[str] = []
    phases = report.get("phases")
    if isinstance(phases, Sequence):
        for phase in phases:
            if not isinstance(phase, Mapping):
                continue
            rows.append(
                "<tr>"
                f"<td><code>{html.escape(str(phase.get('phase_id', '')))}</code></td>"
                f"<td>{html.escape(outcome_copy.get(str(phase.get('outcome', '')), str(phase.get('outcome', ''))))}</td>"
                f"<td>{_format_measurements(phase.get('source_extent'))}</td>"
                f"<td>{_format_measurements(phase.get('locally_processed'))}</td>"
                f"<td>{_format_measurements(phase.get('model_visible'))}</td>"
                f"<td>{_format_measurements(phase.get('remained_local'))}</td>"
                "</tr>"
            )
    phase_rows = "".join(rows)
    improvement = _improvement_html(report, copy)
    report_base64 = base64.b64encode(_canonical_bytes(report)).decode("ascii")
    signed_base64 = base64.b64encode(_signed_receipt_bytes(receipt)).decode("ascii")
    verification_url = f"{receipt['verification_url']}&lang={copy['lang']}"
    escape = lambda value: html.escape(str(value))
    return f"""<!doctype html>
<html lang="{copy['lang']}">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{copy['title']}</title>
  <style>
    :root {{ color-scheme: light; font-family: "Instrument Sans", system-ui, sans-serif; color: #121923; background: #f5f7fa; }}
    body {{ margin: 0; }} main {{ width: min(980px, calc(100% - 40px)); margin: 48px auto; background: #fff; border: 1px solid #d7dfe9; padding: clamp(26px, 5vw, 58px); }}
    .eyebrow {{ color: #0060c7; font-size: .76rem; font-weight: 700; letter-spacing: .12em; text-transform: uppercase; }}
    h1 {{ color: #002060; font-size: clamp(2.2rem, 6vw, 4.8rem); line-height: .96; letter-spacing: -.045em; max-width: 12ch; }}
    h2 {{ color: #002060; margin-top: 38px; }} p {{ line-height: 1.6; max-width: 76ch; }}
    .status {{ border-left: 4px solid #008f73; background: #effaf7; padding: 14px 18px; font-weight: 650; }}
    .checks {{ display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 12px; margin: 18px 0 30px; }} .check {{ border: 1px solid #d7dfe9; padding: 13px 15px; }} .check strong {{ display: block; color: #526070; font-size: .78rem; margin-bottom: 4px; text-transform: uppercase; }}
    dl {{ display: grid; grid-template-columns: minmax(170px, 1fr) minmax(0, 2fr); border-top: 1px solid #d7dfe9; }}
    dt, dd {{ margin: 0; padding: 12px 0; border-bottom: 1px solid #d7dfe9; }} dt {{ color: #526070; }} dd {{ overflow-wrap: anywhere; }}
    code, .proof {{ font-family: ui-monospace, SFMono-Regular, monospace; font-size: .88em; }}
    table {{ border-collapse: collapse; width: 100%; font-size: .93rem; }} th, td {{ border-bottom: 1px solid #d7dfe9; padding: 12px 10px; text-align: left; vertical-align: top; }} th {{ color: #526070; font-weight: 650; }}
    .actions {{ display: flex; flex-wrap: wrap; gap: 12px; margin: 30px 0; }} a, button {{ color: #fff; background: #0057b8; border: 0; padding: 11px 16px; font: inherit; text-decoration: none; cursor: pointer; }}
    details {{ margin-top: 28px; }} details p {{ overflow-wrap: anywhere; }} .print-verification {{ display: none; }} .improvement {{ border-left: 3px solid #00a1c9; padding-left: 18px; }} .limits {{ border-top: 1px solid #d7dfe9; margin-top: 42px; padding-top: 24px; color: #465363; }}
    @media (max-width: 660px) {{ dl, .checks {{ grid-template-columns: 1fr; }} dt {{ padding-bottom: 3px; border-bottom: 0; }} dd {{ padding-top: 3px; }} table {{ display: block; overflow-x: auto; }} }}
    @page {{ size: A4; margin: 12mm; }}
    @media print {{
      :root {{ background: #fff; }} main {{ width: auto; margin: 0; border: 0; padding: 0; }}
      h1 {{ font-size: 32px; margin: 10px 0 14px; }} h2 {{ font-size: 20px; margin-top: 20px; }}
      p {{ font-size: 11px; margin: 7px 0; }} .status {{ padding: 9px 12px; }}
      .checks {{ margin: 10px 0 16px; gap: 8px; }} .check {{ padding: 8px 10px; font-size: 10px; }}
      dt, dd {{ padding: 7px 0; font-size: 10px; }} table {{ font-size: 9px; }} th, td {{ padding: 7px 6px; }}
      .actions, details {{ display: none; }} .print-verification {{ display: block; font-size: 8px; overflow-wrap: anywhere; }} .print-verification a {{ background: none; color: #0057b8; padding: 0; font: inherit; }} .limits {{ margin-top: 18px; padding-top: 12px; }}
    }}
  </style>
</head>
<body>
<main>
  <p class="eyebrow">{copy['eyebrow']}</p>
  <h1>{copy['title']}</h1>
  <p>{copy['lead']}</p>
  <p class="status">{copy['verified']}</p>
  <div class="checks">
    <div class="check"><strong>{copy['digest_check']}</strong><span id="digest-status">{copy['checking']}</span></div>
    <div class="check"><strong>{copy['signature_check']}</strong><span id="signature-status">{copy['checking']}</span></div>
  </div>
  <dl>
    <dt>{copy['workflow']}</dt><dd><code>{escape(report.get('workflow_id', ''))}</code></dd>
    <dt>{copy['run']}</dt><dd><code>{escape(report.get('run_id', ''))}</code></dd>
    <dt>{copy['purpose']}</dt><dd>{escape(report.get('professional_purpose', ''))}</dd>
    <dt>{copy['stamp']}</dt><dd>{escape(receipt['stamped_at'])}</dd>
    <dt>{copy['version']}</dt><dd>{escape(receipt['plugin_version'])}</dd>
    <dt>{copy['receipt']}</dt><dd><code>{escape(receipt['receipt_id'])}</code></dd>
    <dt>{copy['digest']}</dt><dd><code>{escape(receipt['report_sha256'])}</code></dd>
  </dl>
  <h2>{copy['phases']}</h2>
  <table>
    <thead><tr><th>{copy['phase']}</th><th>{copy['outcome']}</th><th>{copy['source']}</th><th>{copy['processed']}</th><th>{copy['visible']}</th><th>{copy['local']}</th></tr></thead>
    <tbody>{phase_rows}</tbody>
  </table>
  {improvement}
  <div class="actions">
    <a href="{escape(verification_url)}">{copy['verify']}</a>
    <button type="button" onclick="window.print()">{copy['print']}</button>
  </div>
  <p class="print-verification"><strong>{copy['verify']}:</strong> <a href="{escape(verification_url)}">{escape(verification_url)}</a></p>
  <details><summary>{copy['technical']}</summary>
    <p class="proof">{escape(receipt['algorithm'])} · {escape(receipt['key_id'])}</p>
    <p class="proof">public_key: {escape(receipt['public_key'])}</p>
    <p class="proof">signature: {escape(receipt['signature'])}</p>
  </details>
  <div class="limits"><p>{copy['server']}</p><p>{copy['limit']}</p></div>
  <script id="embedded-report" type="application/octet-stream">{report_base64}</script>
  <script id="signed-receipt" type="application/octet-stream">{signed_base64}</script>
  <script>
    (() => {{
      const words = {{valid: {json.dumps(copy['valid'])}, invalid: {json.dumps(copy['invalid'])}, unavailable: {json.dumps(copy['unavailable'])}}};
      const decodeBase64 = value => Uint8Array.from(atob(value.trim()), character => character.charCodeAt(0));
      const decodeBase64Url = value => decodeBase64(value.replace(/-/g, "+").replace(/_/g, "/") + "=".repeat((4 - value.length % 4) % 4));
      const hex = bytes => Array.from(bytes, byte => byte.toString(16).padStart(2, "0")).join("");
      const reportBytes = decodeBase64(document.getElementById("embedded-report").textContent);
      const signedBytes = decodeBase64(document.getElementById("signed-receipt").textContent);
      crypto.subtle.digest("SHA-256", reportBytes)
        .then(value => hex(new Uint8Array(value)) === {json.dumps(str(receipt['report_sha256']))})
        .then(valid => {{ document.getElementById("digest-status").textContent = valid ? words.valid : words.invalid; }})
        .catch(() => {{ document.getElementById("digest-status").textContent = words.unavailable; }});
      crypto.subtle.importKey("raw", decodeBase64Url({json.dumps(str(receipt['public_key']))}), {{name: "Ed25519"}}, false, ["verify"])
        .then(key => crypto.subtle.verify({{name: "Ed25519"}}, key, decodeBase64Url({json.dumps(str(receipt['signature']))}), signedBytes))
        .then(valid => {{ document.getElementById("signature-status").textContent = valid ? words.valid : words.invalid; }})
        .catch(() => {{ document.getElementById("signature-status").textContent = words.unavailable; }});
    }})();
  </script>
</main>
</body>
</html>
"""


def stamp_model_data_report(
    report_path: Path,
    *,
    output_dir: Path,
    plugin_root: Path,
    endpoint: str | None = None,
    opener: Callable[..., Any] = urllib.request.urlopen,
) -> dict[str, Any]:
    """Stamp one validated local report and write portable JSON and HTML proofs."""

    output = output_dir.expanduser().resolve()
    if output_dir.is_symlink() or not output.is_dir():
        raise NotarizedRunReceiptError("receipt output directory must already exist")
    report = _validated_report(report_path.expanduser().resolve())
    version = _plugin_version(plugin_root.expanduser().resolve())
    request_path = output / _REQUEST_FILE
    receipt_path = output / _RECEIPT_FILE
    html_path = output / _HTML_FILE
    request_payload = _request_for_run(
        request_path,
        report,
        plugin_version=version,
    )

    if receipt_path.exists():
        if receipt_path.is_symlink() or not receipt_path.is_file():
            raise NotarizedRunReceiptError("receipt output must be a regular file")
        try:
            stored = json.loads(receipt_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise NotarizedRunReceiptError("stored receipt is invalid") from exc
        if not isinstance(stored, dict):
            raise NotarizedRunReceiptError("stored receipt must be an object")
        receipt = _validate_response(stored, request_payload)
    else:
        response = _post_receipt_request(
            endpoint or _configured_endpoint(),
            request_payload,
            opener=opener,
        )
        receipt = _validate_response(response, request_payload)
        _write_once_or_identical(receipt_path, _canonical_bytes(receipt))

    _write_once_or_identical(html_path, _render_html(report, receipt).encode("utf-8"))
    return {
        "status": "stamped",
        "receipt_id": receipt["receipt_id"],
        "receipt_path": str(receipt_path),
        "html_path": str(html_path),
        "verification_url": receipt["verification_url"],
    }


def verify_model_data_receipt(
    receipt_path: Path,
    *,
    report_path: Path,
    opener: Callable[..., Any] = urllib.request.urlopen,
) -> dict[str, Any]:
    """Check the local digest and ask Mparanza for the retained signed proof."""

    report = _validated_report(report_path.expanduser().resolve())
    try:
        receipt = json.loads(
            receipt_path.expanduser().resolve().read_text(encoding="utf-8")
        )
    except (OSError, json.JSONDecodeError) as exc:
        raise NotarizedRunReceiptError("receipt file is invalid") from exc
    if not isinstance(receipt, dict):
        raise NotarizedRunReceiptError("receipt file must be an object")
    digest = hashlib.sha256(_canonical_bytes(report)).hexdigest()
    local_request = {
        "schema_version": receipt.get("schema_version"),
        "receipt_id": receipt.get("receipt_id"),
        "plugin_version": receipt.get("plugin_version"),
        "report_sha256": digest,
    }
    validated_local = _validate_response(receipt, local_request)
    verification_url = _validate_verification_url(
        validated_local["verification_url"],
        receipt_id=str(validated_local["receipt_id"]),
        digest=digest,
    )
    api_url = verification_url.replace(
        "/verify/vera-run-receipt/", "/api/vera/run-receipts/", 1
    )
    request = urllib.request.Request(
        api_url,
        headers={"Accept": "application/json", "User-Agent": "Vera-Run-Receipt/1"},
        method="GET",
    )
    verified = _request_json(request, opener=opener)
    validated_server = _validate_response(verified, local_request)
    if validated_server != validated_local:
        raise NotarizedRunReceiptError(
            "local receipt does not match the server's retained proof"
        )
    return {
        "status": "valid",
        "receipt_id": validated_local["receipt_id"],
        "report_sha256": digest,
        "verification_url": verification_url,
    }


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    stamp = subparsers.add_parser("stamp")
    stamp.add_argument("--report", type=Path, required=True)
    stamp.add_argument("--output-dir", type=Path, required=True)
    stamp.add_argument("--plugin-root", type=Path, default=Path(__file__).parents[1])
    stamp.add_argument("--endpoint")
    verify = subparsers.add_parser("verify")
    verify.add_argument("--report", type=Path, required=True)
    verify.add_argument("--receipt", type=Path, required=True)
    return parser


def main(argv: list[str] | None = None) -> int:
    """Stamp a report or verify an existing receipt."""

    args = _parser().parse_args(argv)
    try:
        if args.command == "stamp":
            payload = stamp_model_data_report(
                args.report,
                output_dir=args.output_dir,
                plugin_root=args.plugin_root,
                endpoint=args.endpoint,
            )
        else:
            payload = verify_model_data_receipt(
                args.receipt,
                report_path=args.report,
            )
        sys.stdout.write(json.dumps(payload, ensure_ascii=False, sort_keys=True) + "\n")
        return 0
    except (NotarizedRunReceiptError, OSError) as exc:
        sys.stderr.write(f"notarized-run-receipt: {exc}\n")
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
