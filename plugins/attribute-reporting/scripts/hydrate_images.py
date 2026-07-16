#!/usr/bin/env python3
"""Hydrate evidence-package product image URLs into a local-only sidecar.

The evidence package remains the immutable analytical source.  This helper does
not rewrite package CSV files or upload image bytes; it writes local raster
files plus a hash-bound manifest that mapping and report rendering can consume.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import http.client
import ipaddress
import json
import logging
import os
import re
import socket
import ssl
import urllib.error
import urllib.parse
import urllib.request
import uuid
from collections.abc import Callable, Iterable, Mapping
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Protocol

__all__ = [
    "HydrationError",
    "bind_images_to_mapping_tasks",
    "hydrate_product_images",
    "main",
]

LOGGER = logging.getLogger(__name__)
SCHEMA_VERSION = "attribute_reporting.local_image_manifest.v1"
SOURCE_TABLES = (
    "product_filter_matrix.csv",
    "recent_products.csv",
    "top_seller_products.csv",
)
URL_FIELDS = (
    "hero_image_url",
    "swatch_image_url",
    "og_image_url",
    "image_url",
)
MAX_IMAGE_BYTES = 20 * 1024 * 1024
MAX_REDIRECTS = 5
USER_AGENT = "Mparanza-Clara-Attribute-Reporting/1.0"


class HydrationError(ValueError):
    """Raised when local image hydration cannot satisfy its file contract."""


class _Response(Protocol):
    headers: Mapping[str, str]

    def read(self, amount: int = -1) -> bytes: ...

    def geturl(self) -> str: ...

    def __enter__(self) -> _Response: ...

    def __exit__(self, *args: object) -> None: ...


OpenUrl = Callable[[urllib.request.Request, float], _Response]


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _canonical_row_sha256(row: Mapping[str, Any]) -> str:
    encoded = json.dumps(
        dict(row),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return _sha256_bytes(encoded)


def _assert_package_dir(package_dir: Path) -> Path:
    package = package_dir.expanduser().resolve()
    if not package.is_dir():
        raise HydrationError(f"Evidence package directory not found: {package}")
    if not (package / "pack_manifest.json").is_file():
        raise HydrationError("Evidence package has no pack_manifest.json")
    return package


def _safe_relative_path(value: str, *, label: str) -> Path:
    path = Path(value)
    if path.is_absolute() or ".." in path.parts:
        raise HydrationError(f"Unsafe {label}: {value}")
    return path


def _read_rows(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        if reader.fieldnames is None:
            raise HydrationError(f"CSV has no header: {path}")
        return [
            {str(key): str(value or "") for key, value in row.items()} for row in reader
        ]


def _source_rows(package: Path) -> tuple[list[dict[str, Any]], dict[str, str]]:
    records_by_product: dict[str, dict[str, Any]] = {}
    source_hashes: dict[str, str] = {}
    for name in SOURCE_TABLES:
        path = package / name
        if not path.is_file():
            continue
        source_hashes[name] = _sha256_file(path)
        for row in _read_rows(path):
            product_id = str(
                row.get("parent_product_id") or row.get("listing_identity") or ""
            ).strip()
            if not product_id:
                continue
            current = records_by_product.get(product_id)
            if current is None:
                records_by_product[product_id] = {
                    "row": row,
                    "source_rows": {name: _canonical_row_sha256(row)},
                }
                continue
            current["source_rows"][name] = _canonical_row_sha256(row)
            # Prefer the row with the most useful image URL without changing the
            # product identity or any analytical package file.
            current_row = current["row"]
            current_has_url = any(
                str(current_row.get(field) or "").strip() for field in URL_FIELDS
            )
            row_has_url = any(str(row.get(field) or "").strip() for field in URL_FIELDS)
            if row_has_url and not current_has_url:
                current["row"] = row
    if not records_by_product:
        raise HydrationError("Evidence package contains no product rows")
    return (
        [records_by_product[key] for key in sorted(records_by_product)],
        source_hashes,
    )


def _safe_public_http_url(value: str) -> str:
    text = value.strip()
    parts = urllib.parse.urlsplit(text)
    if (
        parts.scheme not in {"http", "https"}
        or not parts.hostname
        or parts.username is not None
        or parts.password is not None
        or parts.fragment
        or any(character in text for character in ("\r", "\n", "\t"))
    ):
        return ""
    hostname = parts.hostname.casefold().rstrip(".")
    if (
        hostname == "localhost"
        or hostname.endswith(".localhost")
        or hostname.endswith(".local")
        or hostname.endswith(".internal")
    ):
        return ""
    try:
        address = ipaddress.ip_address(hostname)
    except ValueError:
        return text
    if not address.is_global:
        return ""
    return text


def _public_network_target(
    url: str,
    *,
    resolver: Callable[..., list[tuple[Any, ...]]] | None = None,
) -> tuple[str, int, tuple[str, ...]]:
    safe_url = _safe_public_http_url(url)
    if not safe_url:
        raise HydrationError("Image URL is not a supported public HTTP(S) target")
    parts = urllib.parse.urlsplit(safe_url)
    hostname = str(parts.hostname or "")
    try:
        port = parts.port or (443 if parts.scheme == "https" else 80)
    except ValueError as exc:
        raise HydrationError("Image URL has an invalid port") from exc
    active_resolver = resolver or socket.getaddrinfo
    try:
        addresses = {
            str(result[4][0])
            for result in active_resolver(
                hostname,
                port,
                family=socket.AF_UNSPEC,
                type=socket.SOCK_STREAM,
            )
        }
    except (OSError, ValueError) as exc:
        raise HydrationError(
            f"Image hostname could not be resolved safely: {hostname}"
        ) from exc
    if not addresses:
        raise HydrationError(f"Image hostname returned no addresses: {hostname}")
    for raw_address in addresses:
        try:
            address = ipaddress.ip_address(raw_address.split("%", 1)[0])
        except ValueError as exc:
            raise HydrationError(
                f"Image hostname returned an invalid address: {hostname}"
            ) from exc
        if not address.is_global:
            raise HydrationError(
                f"Image hostname resolves to a non-public address: {hostname}"
            )
    return hostname, port, tuple(sorted(addresses))


def _assert_public_network_target(
    url: str,
    *,
    resolver: Callable[..., list[tuple[Any, ...]]] | None = None,
) -> None:
    _public_network_target(url, resolver=resolver)


def _source_url(row: Mapping[str, str]) -> tuple[str, str]:
    for field in URL_FIELDS:
        url = _safe_public_http_url(str(row.get(field) or ""))
        if url:
            return field, url
    return "", ""


def _raster_suffix(payload: bytes) -> str:
    if payload.startswith(b"\xff\xd8\xff"):
        return ".jpg"
    if payload.startswith(b"\x89PNG\r\n\x1a\n"):
        return ".png"
    if payload.startswith((b"GIF87a", b"GIF89a")):
        return ".gif"
    if len(payload) >= 12 and payload.startswith(b"RIFF") and payload[8:12] == b"WEBP":
        return ".webp"
    if (
        len(payload) >= 12
        and payload[4:8] == b"ftyp"
        and (payload[8:12] in {b"avif", b"avis"} or b"avif" in payload[8:32])
    ):
        return ".avif"
    raise HydrationError("Downloaded content is not a supported raster image")


def _safe_product_token(product_id: str) -> str:
    clean = re.sub(r"[^A-Za-z0-9_-]+", "-", product_id).strip("-")[:72]
    return clean or hashlib.sha256(product_id.encode("utf-8")).hexdigest()[:24]


def _connect_pinned_socket(address: str, port: int, timeout: float) -> socket.socket:
    """Connect to one already-vetted numeric address without resolving again."""

    parsed = ipaddress.ip_address(address)
    family = socket.AF_INET6 if parsed.version == 6 else socket.AF_INET
    target: tuple[Any, ...] = (
        (address, port, 0, 0) if family == socket.AF_INET6 else (address, port)
    )
    connection = socket.socket(family, socket.SOCK_STREAM)
    try:
        connection.settimeout(timeout)
        connection.connect(target)
    except OSError:
        connection.close()
        raise
    return connection


class _PinnedResponse:
    """Small response wrapper that owns its pinned HTTP connection."""

    def __init__(
        self,
        response: http.client.HTTPResponse,
        connection: http.client.HTTPConnection,
        final_url: str,
    ) -> None:
        self._response = response
        self._connection = connection
        self._final_url = final_url
        self.headers = response.headers

    def read(self, amount: int = -1) -> bytes:
        return self._response.read(amount)

    def geturl(self) -> str:
        return self._final_url

    def close(self) -> None:
        self._response.close()
        self._connection.close()

    def __enter__(self) -> _PinnedResponse:
        return self

    def __exit__(self, *args: object) -> None:
        self.close()


def _open_pinned_connection(
    *,
    scheme: str,
    hostname: str,
    port: int,
    address: str,
    timeout: float,
) -> http.client.HTTPConnection:
    raw_socket = _connect_pinned_socket(address, port, timeout)
    if scheme == "https":
        context = ssl.create_default_context()
        try:
            connected_socket = context.wrap_socket(
                raw_socket,
                server_hostname=hostname,
            )
        except (OSError, ssl.SSLError):
            raw_socket.close()
            raise
        connection: http.client.HTTPConnection = http.client.HTTPSConnection(
            hostname,
            port,
            timeout=timeout,
            context=context,
        )
        connection.sock = connected_socket
        return connection
    connection = http.client.HTTPConnection(hostname, port, timeout=timeout)
    connection.sock = raw_socket
    return connection


def _default_open_url(request: urllib.request.Request, timeout: float) -> _Response:
    """Open a public image URL while pinning every connection to its vetted IP."""

    if request.data is not None or request.get_method() != "GET":
        raise HydrationError("Image hydration supports only bodyless GET requests")
    current_url = request.full_url
    headers = dict(request.header_items())
    for redirect_count in range(MAX_REDIRECTS + 1):
        safe_url = _safe_public_http_url(current_url)
        if not safe_url:
            raise HydrationError("Image URL is not a supported public HTTP(S) target")
        parts = urllib.parse.urlsplit(safe_url)
        hostname, port, addresses = _public_network_target(safe_url)
        request_target = parts.path or "/"
        if parts.query:
            request_target = f"{request_target}?{parts.query}"
        response: http.client.HTTPResponse | None = None
        connection: http.client.HTTPConnection | None = None
        last_error: BaseException | None = None
        for address in addresses:
            try:
                connection = _open_pinned_connection(
                    scheme=parts.scheme,
                    hostname=hostname,
                    port=port,
                    address=address,
                    timeout=timeout,
                )
                connection.request("GET", request_target, headers=headers)
                response = connection.getresponse()
                break
            except (OSError, ssl.SSLError, http.client.HTTPException) as exc:
                last_error = exc
                if connection is not None:
                    connection.close()
                connection = None
        if response is None or connection is None:
            raise HydrationError(
                f"Image host could not be reached through its vetted public addresses: "
                f"{hostname}"
            ) from last_error
        if response.status in {301, 302, 303, 307, 308}:
            location = str(response.headers.get("Location") or "").strip()
            response.close()
            connection.close()
            if not location:
                raise HydrationError("Image redirect has no destination")
            if redirect_count >= MAX_REDIRECTS:
                raise HydrationError("Image request exceeded the redirect limit")
            current_url = urllib.parse.urljoin(safe_url, location)
            continue
        if not 200 <= response.status < 300:
            status = response.status
            response.close()
            connection.close()
            raise HydrationError(f"Image request failed with HTTP {status}")
        return _PinnedResponse(response, connection, safe_url)
    raise HydrationError("Image request exceeded the redirect limit")


def _download(
    url: str,
    *,
    timeout_seconds: float,
    max_bytes: int,
    open_url: OpenUrl,
) -> tuple[bytes, str, str]:
    request = urllib.request.Request(
        url,
        headers={"User-Agent": USER_AGENT, "Accept": "image/*"},
        method="GET",
    )
    with open_url(request, timeout_seconds) as response:
        final_url = _safe_public_http_url(str(response.geturl() or url))
        if not final_url:
            raise HydrationError("Image request redirected to a disallowed URL")
        declared_length = str(response.headers.get("Content-Length") or "").strip()
        if declared_length:
            try:
                if int(declared_length) > max_bytes:
                    raise HydrationError("Image exceeds the configured byte limit")
            except ValueError as exc:
                raise HydrationError(
                    "Image response has an invalid Content-Length"
                ) from exc
        chunks: list[bytes] = []
        total = 0
        while True:
            chunk = response.read(min(1024 * 1024, max_bytes + 1 - total))
            if not chunk:
                break
            chunks.append(chunk)
            total += len(chunk)
            if total > max_bytes:
                raise HydrationError("Image exceeds the configured byte limit")
        payload = b"".join(chunks)
        if not payload:
            raise HydrationError("Image response is empty")
        suffix = _raster_suffix(payload)
        media_type = (
            str(response.headers.get("Content-Type") or "").split(";", 1)[0].strip()
        )
        return payload, final_url, media_type


def _load_prior_manifest(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    if not isinstance(payload, dict) or payload.get("schema_version") != SCHEMA_VERSION:
        return {}
    return payload


def _reusable_entries(
    package: Path,
    prior: Mapping[str, Any],
    *,
    source_hashes: Mapping[str, str],
) -> dict[str, dict[str, Any]]:
    if prior.get("source_table_sha256") != dict(source_hashes):
        return {}
    entries: dict[str, dict[str, Any]] = {}
    for raw in prior.get("products") or []:
        if not isinstance(raw, dict):
            continue
        product_id = str(raw.get("product_id") or "")
        relative_value = str(raw.get("image_path") or "")
        expected_sha = str(raw.get("sha256") or "")
        if not product_id or not relative_value or not expected_sha:
            continue
        try:
            relative = _safe_relative_path(relative_value, label="hydrated image path")
        except HydrationError:
            continue
        candidate = (package / relative).resolve()
        image_root = (package / "images").resolve()
        if (
            candidate.is_file()
            and candidate.is_relative_to(image_root)
            and _sha256_file(candidate) == expected_sha
        ):
            entries[product_id] = dict(raw)
    return entries


def _existing_pack_image(package: Path, row: Mapping[str, str]) -> Path | None:
    value = str(row.get("pack_image_file") or "").strip()
    if not value:
        return None
    relative = _safe_relative_path(value, label="pack image path")
    candidate = (package / relative).resolve()
    image_root = (package / "images").resolve()
    if not candidate.is_file() or not candidate.is_relative_to(image_root):
        return None
    try:
        _raster_suffix(candidate.read_bytes()[:64])
    except (OSError, HydrationError):
        return None
    return candidate


def _write_json_atomic(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
    try:
        temporary.write_text(
            json.dumps(dict(payload), ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        os.chmod(temporary, 0o600)
        temporary.replace(path)
    finally:
        temporary.unlink(missing_ok=True)


def bind_images_to_mapping_tasks(
    tasks_path: Path,
    manifest_path: Path,
    output_path: Path,
) -> dict[str, Any]:
    """Bind verified local sidecar images to a public server workset.

    Only ``product.local_images`` changes.  The public task identities, source
    rows, taxonomy pins, and bounded product text remain byte-for-byte stable.
    Relative paths avoid sending a user's absolute workspace path back to the
    server when the reviewed workset is submitted.
    """

    try:
        tasks = json.loads(tasks_path.read_text(encoding="utf-8"))
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise HydrationError(f"Unable to read mapping image inputs: {exc}") from exc
    if not isinstance(tasks, dict) or tasks.get("schema_version") != (
        "attribute_reporting.mapping_tasks.v1"
    ):
        raise HydrationError("Unsupported mapping task schema")
    if (
        not isinstance(manifest, dict)
        or manifest.get("schema_version") != SCHEMA_VERSION
    ):
        raise HydrationError("Unsupported local image manifest schema")
    package = Path(str(manifest.get("package_dir") or "")).expanduser().resolve()
    if not package.is_dir() or not manifest_path.expanduser().resolve().is_relative_to(
        package
    ):
        raise HydrationError(
            "Local image manifest is not bound to its package directory"
        )

    entries = {
        str(item.get("product_id") or ""): item
        for item in manifest.get("products") or []
        if isinstance(item, dict) and str(item.get("product_id") or "")
    }
    raw_tasks = tasks.get("tasks")
    if not isinstance(raw_tasks, list):
        raise HydrationError("Mapping tasks must contain a tasks list")
    enriched = json.loads(json.dumps(tasks, ensure_ascii=False))
    bound_count = 0
    for task in enriched["tasks"]:
        if not isinstance(task, dict) or not isinstance(task.get("product"), dict):
            raise HydrationError("Mapping task has an invalid product object")
        product = task["product"]
        product_id = str(product.get("parent_product_id") or "")
        source_row_sha = str(product.get("source_row_sha256") or "")
        current_images = product.get("local_images")
        if current_images not in (None, []):
            raise HydrationError(
                "Public mapping workset already contains local image evidence"
            )
        entry = entries.get(product_id)
        if entry is None or entry.get("status") not in {
            "downloaded",
            "existing",
            "reused",
        }:
            product["local_images"] = []
            continue
        source_rows = entry.get("source_rows")
        if not isinstance(source_rows, dict) or source_row_sha not in {
            str(value) for value in source_rows.values()
        }:
            raise HydrationError(
                f"Local image manifest is stale for mapping product {product_id}"
            )
        relative = _safe_relative_path(
            str(entry.get("image_path") or ""), label="local image path"
        )
        candidate = (package / relative).resolve()
        image_root = (package / "images").resolve()
        expected_sha = str(entry.get("sha256") or "")
        if (
            not candidate.is_file()
            or not candidate.is_relative_to(image_root)
            or not expected_sha
            or _sha256_file(candidate) != expected_sha
        ):
            raise HydrationError(
                f"Local image evidence failed verification for product {product_id}"
            )
        product["local_images"] = [
            {"path": relative.as_posix(), "sha256": expected_sha}
        ]
        bound_count += 1

    output = output_path.expanduser().resolve()
    if output.parent != tasks_path.expanduser().resolve().parent:
        raise HydrationError(
            "Enriched mapping tasks must remain beside the public workset"
        )
    _write_json_atomic(output, enriched)
    return {
        "mapping_tasks": enriched,
        "task_count": len(enriched["tasks"]),
        "image_bound_task_count": bound_count,
        "output": str(output),
    }


def hydrate_product_images(
    package_dir: Path,
    *,
    manifest_path: Path | None = None,
    max_images: int = 0,
    timeout_seconds: float = 20.0,
    max_bytes: int = MAX_IMAGE_BYTES,
    open_url: OpenUrl = _default_open_url,
) -> dict[str, Any]:
    """Download package image URLs locally and write a resumable manifest."""

    package = _assert_package_dir(package_dir)
    if max_images < 0:
        raise HydrationError("max_images cannot be negative")
    if timeout_seconds <= 0:
        raise HydrationError("timeout_seconds must be positive")
    if max_bytes < 64:
        raise HydrationError("max_bytes is too small for supported raster images")
    target_manifest = (
        manifest_path.expanduser().resolve()
        if manifest_path is not None
        else package / "local_image_manifest.json"
    )
    if not target_manifest.is_relative_to(package):
        raise HydrationError("Local image manifest must stay inside the package")

    rows, source_hashes = _source_rows(package)
    prior = _load_prior_manifest(target_manifest)
    reusable = _reusable_entries(package, prior, source_hashes=source_hashes)
    image_root = package / "images" / "local"
    products: list[dict[str, Any]] = []
    attempts = 0
    for record in rows:
        row = record["row"]
        source_rows = dict(record["source_rows"])
        product_id = str(
            row.get("parent_product_id") or row.get("listing_identity") or ""
        ).strip()
        source_row_sha = _canonical_row_sha256(row)
        existing = _existing_pack_image(package, row)
        if existing is not None:
            products.append(
                {
                    "product_id": product_id,
                    "source_row_sha256": source_row_sha,
                    "source_rows": source_rows,
                    "source_field": "pack_image_file",
                    "source_url": "",
                    "final_url": "",
                    "status": "existing",
                    "image_path": existing.relative_to(package).as_posix(),
                    "sha256": _sha256_file(existing),
                    "byte_count": existing.stat().st_size,
                    "media_type": "",
                    "error": "",
                }
            )
            continue
        source_field, url = _source_url(row)
        prior_entry = reusable.get(product_id)
        if (
            prior_entry is not None
            and str(prior_entry.get("source_row_sha256") or "") == source_row_sha
            and str(prior_entry.get("source_url") or "") == url
        ):
            products.append({**prior_entry, "status": "reused"})
            continue
        if not url:
            products.append(
                {
                    "product_id": product_id,
                    "source_row_sha256": source_row_sha,
                    "source_rows": source_rows,
                    "source_field": "",
                    "source_url": "",
                    "final_url": "",
                    "status": "unavailable",
                    "image_path": "",
                    "sha256": "",
                    "byte_count": 0,
                    "media_type": "",
                    "error": "No supported public image URL is present.",
                }
            )
            continue
        if max_images and attempts >= max_images:
            products.append(
                {
                    "product_id": product_id,
                    "source_row_sha256": source_row_sha,
                    "source_rows": source_rows,
                    "source_field": source_field,
                    "source_url": url,
                    "final_url": "",
                    "status": "not_attempted",
                    "image_path": "",
                    "sha256": "",
                    "byte_count": 0,
                    "media_type": "",
                    "error": "The configured hydration limit was reached.",
                }
            )
            continue
        attempts += 1
        try:
            payload, final_url, media_type = _download(
                url,
                timeout_seconds=timeout_seconds,
                max_bytes=max_bytes,
                open_url=open_url,
            )
            suffix = _raster_suffix(payload)
            url_token = hashlib.sha256(url.encode("utf-8")).hexdigest()[:12]
            target = (
                image_root / f"{_safe_product_token(product_id)}-{url_token}{suffix}"
            )
            target.parent.mkdir(parents=True, exist_ok=True)
            temporary = target.with_name(f".{target.name}.{uuid.uuid4().hex}.tmp")
            try:
                temporary.write_bytes(payload)
                os.chmod(temporary, 0o600)
                temporary.replace(target)
            finally:
                temporary.unlink(missing_ok=True)
            entry = {
                "product_id": product_id,
                "source_row_sha256": source_row_sha,
                "source_rows": source_rows,
                "source_field": source_field,
                "source_url": url,
                "final_url": final_url,
                "status": "downloaded",
                "image_path": target.relative_to(package).as_posix(),
                "sha256": _sha256_bytes(payload),
                "byte_count": len(payload),
                "media_type": media_type,
                "error": "",
            }
        except (HydrationError, OSError, urllib.error.URLError) as exc:
            entry = {
                "product_id": product_id,
                "source_row_sha256": source_row_sha,
                "source_rows": source_rows,
                "source_field": source_field,
                "source_url": url,
                "final_url": "",
                "status": "failed",
                "image_path": "",
                "sha256": "",
                "byte_count": 0,
                "media_type": "",
                "error": str(exc),
            }
        products.append(entry)

    available_statuses = {"downloaded", "existing", "reused"}
    available_count = sum(item["status"] in available_statuses for item in products)
    failure_count = sum(item["status"] == "failed" for item in products)
    pending_count = sum(item["status"] == "not_attempted" for item in products)
    unavailable_count = sum(item["status"] == "unavailable" for item in products)
    manifest = {
        "schema_version": SCHEMA_VERSION,
        "generated_at": _utc_now(),
        "package_dir": str(package),
        "source_table_sha256": source_hashes,
        "policy": {
            "storage": "local_machine_only",
            "uploaded_to_server": False,
            "analytical_package_files_modified": False,
            "allowed_schemes": ["https", "http"],
            "max_image_bytes": max_bytes,
        },
        "summary": {
            "product_count": len(products),
            "available_count": available_count,
            "failure_count": failure_count,
            "unavailable_count": unavailable_count,
            "not_attempted_count": pending_count,
            "status": (
                "complete"
                if available_count == len(products)
                else "partial" if available_count else "blocked"
            ),
        },
        "products": products,
    }
    _write_json_atomic(target_manifest, manifest)
    return manifest


def main(argv: Iterable[str] | None = None) -> int:
    """Run local product-image hydration."""

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("package_dir", type=Path)
    parser.add_argument("--manifest", type=Path)
    parser.add_argument("--max-images", type=int, default=0)
    parser.add_argument("--timeout-seconds", type=float, default=20.0)
    parser.add_argument("--max-bytes", type=int, default=MAX_IMAGE_BYTES)
    args = parser.parse_args(list(argv) if argv is not None else None)
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    try:
        result = hydrate_product_images(
            args.package_dir,
            manifest_path=args.manifest,
            max_images=args.max_images,
            timeout_seconds=args.timeout_seconds,
            max_bytes=args.max_bytes,
        )
    except HydrationError as exc:
        LOGGER.error("Image hydration failed: %s", exc)
        return 1
    summary = result["summary"]
    LOGGER.info(
        "Local image hydration %s: available=%s failed=%s unavailable=%s pending=%s",
        summary["status"],
        summary["available_count"],
        summary["failure_count"],
        summary["unavailable_count"],
        summary["not_attempted_count"],
    )
    return 0 if summary["status"] != "blocked" else 2


if __name__ == "__main__":
    raise SystemExit(main())
