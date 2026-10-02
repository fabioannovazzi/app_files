"""Restricted adapter to the separately installed Rizzo PII loopback service."""

from __future__ import annotations

import http.client
import json
import re
from typing import Any

from .contracts import FilteredDocument, FilterError
from .engines import RIZZO

__all__ = ["analyze", "health", "validate_port"]

MAX_RESPONSE_BYTES = 16 * 1024 * 1024


def validate_port(port: int) -> None:
    """Permit a port only; no configurable host, URL, proxy or redirect target."""
    if type(port) is not int or not 1 <= port <= 65535:
        raise FilterError("invalid_rizzo_port")


def _request(
    port: int, path: str, payload: dict[str, Any] | None = None
) -> dict[str, Any]:
    validate_port(port)
    # HTTPConnection connects directly, ignores proxy environment variables and
    # never follows redirects. The literal loopback address is a transport boundary.
    connection = http.client.HTTPConnection(
        "127.0.0.1", port, timeout=590 if payload is not None else 3
    )
    try:
        connection.request(
            "POST" if payload is not None else "GET",
            path,
            body=json.dumps(payload).encode("utf-8") if payload is not None else None,
            headers={"Content-Type": "application/json", "Accept": "application/json"},
        )
        response = connection.getresponse()
        if response.status != 200:
            raise FilterError("rizzo_unavailable")
        raw = response.read(MAX_RESPONSE_BYTES + 1)
        if len(raw) > MAX_RESPONSE_BYTES:
            raise FilterError("invalid_rizzo_response")
        result = json.loads(raw)
        if not isinstance(result, dict):
            raise FilterError("invalid_rizzo_response")
        return result
    except FilterError:
        raise
    except (OSError, http.client.HTTPException):
        raise FilterError("rizzo_unavailable") from None
    except (ValueError, UnicodeError):
        raise FilterError("invalid_rizzo_response") from None
    finally:
        connection.close()


def health(port: int) -> dict[str, Any]:
    """Return fixed readiness fields and validated versions, never raw diagnostics."""
    body = _request(port, "/health")
    if body.get("status") != "ok" or body.get("model_loaded") is not True:
        raise FilterError("rizzo_unavailable")
    result: dict[str, Any] = {"model_ready": True}
    for key in ("app_version", "model_version"):
        value = body.get(key)
        # Version syntax is mechanically checkable; arbitrary server strings must
        # not become chat metadata. This is not a model-quality classifier.
        if not isinstance(value, str) or not re.fullmatch(
            r"\d{1,4}(?:\.\d{1,4}){1,3}", value
        ):
            raise FilterError("invalid_rizzo_response")
        result[key] = value
    if body.get("device") not in ("cpu", "cuda"):
        raise FilterError("invalid_rizzo_response")
    result["device"] = body["device"]
    return result


def analyze(text: str, port: int) -> FilteredDocument:
    """Use upstream detection and request all tags without a restoration mapping."""
    text = text.strip()  # Match the documented /analyze endpoint's normalization.
    body = _request(
        port,
        "/analyze",
        {"text": text, "include_mapping": False, "exclude_tags": []},
    )
    counts, filtered = body.get("by_label"), body.get("anonymized_text")
    if (
        body.get("mapping_enabled") is not False
        or body.get("mapping") != {}
        or body.get("excluded_tags") != []
        or type(body.get("n_chars")) is not int
        or body["n_chars"] != len(text)
        or not isinstance(filtered, str)
        or not filtered
        or not isinstance(counts, dict)
        or not set(counts).issubset(RIZZO.labels)
        or any(type(n) is not int or n < 0 for n in counts.values())
        or type(body.get("n_entities")) is not int
        or body["n_entities"] != sum(counts.values())
    ):
        raise FilterError("invalid_rizzo_response")
    # Deliberately select only the shared contract. source_text, segments, mapping,
    # unknown fields and diagnostics never cross into the MCP response or artifact.
    return FilteredDocument(filtered, counts, len(text))
