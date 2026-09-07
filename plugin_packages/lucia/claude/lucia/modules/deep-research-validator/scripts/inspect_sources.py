"""Inspect cited sources for an answer-validation run."""

from __future__ import annotations

import argparse
import hashlib
import http.client
import ipaddress
import json
import re
import socket
import ssl
import sys
import urllib.error
import urllib.parse
import urllib.request
from html.parser import HTMLParser
from pathlib import Path
from typing import Any

PLUGIN_ROOT = Path(__file__).resolve().parents[1]
for _vendor_root in (
    PLUGIN_ROOT / "vendor" / "modules",
    PLUGIN_ROOT.parent.parent / "vendor" / "modules",
    PLUGIN_ROOT.parent / "_shared" / "vendor" / "modules",
):
    if (_vendor_root / "vera_assurance").is_dir():
        if str(_vendor_root) not in sys.path:
            sys.path.insert(0, str(_vendor_root))
        break

from vera_assurance import (  # noqa: E402
    AssuranceContractError,
    load_client_engagement_context_file,
)

__all__ = ["inspect_sources", "write_source_inventory"]

URL_RE = re.compile(r"https?://[^\s)\]>\"']+", re.IGNORECASE)
ACCESS_BARRIER_SNIPPETS = (
    "access denied",
    "forbidden",
    "captcha",
    "verify you are human",
    "cloudflare",
    "enable javascript",
    "subscription",
    "sign in",
    "login",
)
_STANDARD_PORTS = {"http": 80, "https": 443}
MAX_CAPTURE_BYTES = 1_000_000


class UnsafePublicUrlError(ValueError):
    """Raised when a cited URL can reach a non-public network destination."""


def _validate_public_url(url: str) -> None:
    """Enforce public HTTP/S destinations for auditable SSRF prevention."""

    parsed = urllib.parse.urlparse(url)
    if (
        parsed.scheme.lower() not in _STANDARD_PORTS
        or not parsed.hostname
        or parsed.username is not None
        or parsed.password is not None
    ):
        raise UnsafePublicUrlError("only public HTTP/S URLs without credentials")
    try:
        port = parsed.port
    except ValueError as exc:
        raise UnsafePublicUrlError("URL port is invalid") from exc
    expected_port = _STANDARD_PORTS[parsed.scheme.lower()]
    if port not in {None, expected_port}:
        raise UnsafePublicUrlError("only standard HTTP/S ports are allowed")
    hostname = parsed.hostname.rstrip(".").casefold()
    if hostname == "localhost" or hostname.endswith(".localhost"):
        raise UnsafePublicUrlError("localhost destinations are not allowed")
    try:
        literal = ipaddress.ip_address(hostname)
    except ValueError:
        literal = None
    if literal is not None:
        addresses = [literal]
    else:
        try:
            addresses = [
                ipaddress.ip_address(record[4][0])
                for record in socket.getaddrinfo(
                    hostname,
                    expected_port,
                    type=socket.SOCK_STREAM,
                )
            ]
        except socket.gaierror:
            raise
    if not addresses or any(not address.is_global for address in addresses):
        raise UnsafePublicUrlError("URL resolves to a non-public network address")


class _PublicRedirectHandler(urllib.request.HTTPRedirectHandler):
    """Reapply the public-network rule to every redirect target."""

    def redirect_request(
        self,
        req: urllib.request.Request,
        fp: Any,
        code: int,
        msg: str,
        headers: Any,
        newurl: str,
    ) -> urllib.request.Request | None:
        _validate_public_url(newurl)
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def _connect_public_address(
    address: tuple[str, int],
    timeout: float | None,
    source_address: tuple[str, int] | None = None,
) -> socket.socket:
    """Validate the exact socket destinations to prevent DNS rebinding."""
    host, port = address
    candidates = socket.getaddrinfo(host, port, type=socket.SOCK_STREAM)
    if not candidates or any(
        not ipaddress.ip_address(candidate[4][0]).is_global for candidate in candidates
    ):
        raise UnsafePublicUrlError("Connection resolves to a non-public address")
    last_error: OSError | None = None
    for family, socktype, protocol, _, sockaddr in candidates:
        connection = socket.socket(family, socktype, protocol)
        try:
            connection.settimeout(timeout)
            if source_address is not None:
                connection.bind(source_address)
            connection.connect(sockaddr)
            return connection
        except OSError as exc:
            connection.close()
            last_error = exc
    assert last_error is not None
    raise last_error


class _PublicHTTPConnection(http.client.HTTPConnection):
    """HTTP connection whose socket cannot resolve unchecked destinations."""

    def connect(self) -> None:
        self._create_connection = _connect_public_address
        super().connect()


class _PublicHTTPSConnection(http.client.HTTPSConnection):
    """HTTPS connection preserving TLS identity over a checked socket."""

    def connect(self) -> None:
        self._create_connection = _connect_public_address
        # Keep the original hostname for TLS certificate validation and SNI.
        super().connect()


class _PublicHTTPHandler(urllib.request.HTTPHandler):
    """Route HTTP requests through the public socket transport."""

    def http_open(self, request: urllib.request.Request) -> Any:
        return self.do_open(_PublicHTTPConnection, request)


class _PublicHTTPSHandler(urllib.request.HTTPSHandler):
    """Route HTTPS requests through the public socket transport."""

    _context: ssl.SSLContext | None

    def https_open(self, request: urllib.request.Request) -> Any:
        return self.do_open(_PublicHTTPSConnection, request, context=self._context)


def _ordered_unique(items: list[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for item in items:
        cleaned = item.strip().rstrip(".,;:!?)\\]}>'\"")
        if not cleaned:
            continue
        # URL paths and query values can be case-sensitive.
        key = cleaned
        if key in seen:
            continue
        seen.add(key)
        out.append(cleaned)
    return out


def _read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _extract_urls_from_inventory(path: Path) -> list[str]:
    payload = _read_json(path)
    urls = [str(url) for url in payload.get("urls", [])]
    for footnote in payload.get("footnotes", []):
        urls.extend(URL_RE.findall(str(footnote.get("text", ""))))
    for link in payload.get("markdown_links", []):
        urls.append(str(link.get("url", "")))
    return _ordered_unique(urls)


def _source_file_record(
    path: Path,
    *,
    run_root: Path | None = None,
) -> dict[str, Any]:
    resolved = path.expanduser().resolve()
    recorded_path = resolved.as_posix()
    path_reference = "absolute"
    if run_root is not None:
        try:
            recorded_path = resolved.relative_to(run_root.resolve()).as_posix()
        except ValueError as exc:
            raise ValueError(
                "managed source file is outside the current customer run"
            ) from exc
        path_reference = "run_root_relative"
    try:
        raw = resolved.read_bytes()
    except OSError as exc:
        return {
            "kind": "file",
            "name": path.name,
            "path_reference": path_reference,
            "path": recorded_path,
            "origin_path": recorded_path,
            "status": "unreadable",
            "character_count": 0,
            "capture_scope": "unavailable_local_source",
            "error": type(exc).__name__,
            "excerpt": "",
        }
    text, extraction = _extract_source_text(raw, suffix=path.suffix)
    encoded = text.encode("utf-8")
    return {
        "kind": "file",
        "name": path.name,
        "path_reference": path_reference,
        "path": recorded_path,
        "origin_path": recorded_path,
        "status": extraction["status"],
        "character_count": len(text.strip()),
        "content_hash": hashlib.sha256(encoded).hexdigest(),
        "source_bytes_sha256": hashlib.sha256(raw).hexdigest(),
        "extracted_text_sha256": hashlib.sha256(encoded).hexdigest(),
        "capture_scope": (
            "complete_local_text"
            if extraction["format"] == "text" and text
            else extraction["capture_scope"]
        ),
        "extraction": extraction,
        "excerpt": re.sub(r"\s+", " ", text.strip())[:1200],
        "_captured_text": text,
    }


def _looks_blocked(text: str) -> bool:
    """Flag exact interstitial text as a hint, never a semantic access verdict."""

    sample = re.sub(r"\s+", " ", text).strip().casefold()
    return sample in ACCESS_BARRIER_SNIPPETS


class _HTMLTextExtractor(HTMLParser):
    """Parse HTML syntax so quoted attributes cannot enter source evidence."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []
        self.hidden_tag: str | None = None

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag in {"script", "style"}:
            self.hidden_tag = tag
        self.parts.append(" ")

    def handle_endtag(self, tag: str) -> None:
        if tag == self.hidden_tag:
            self.hidden_tag = None
        self.parts.append(" ")

    def handle_data(self, data: str) -> None:
        if self.hidden_tag is None:
            self.parts.append(data)


def _extract_source_text(
    raw: bytes, *, content_type: str = "", suffix: str = ""
) -> tuple[str, dict[str, Any]]:
    """Decode formats mechanically and disclose uncovered pages or failures."""

    is_pdf = (
        raw.startswith(b"%PDF-")
        or content_type == "application/pdf"
        or suffix.lower() == ".pdf"
    )
    if is_pdf:
        import fitz

        try:
            with fitz.open(stream=raw, filetype="pdf") as document:
                pages = [page.get_text() for page in document]
        except (fitz.FileDataError, RuntimeError, ValueError) as exc:
            return "", {
                "format": "pdf",
                "status": "unreadable",
                "capture_scope": "extraction_failed",
                "error": str(exc),
            }
        empty_pages = [
            index for index, page in enumerate(pages, start=1) if not page.strip()
        ]
        text = "\n\n".join(
            f"[Page {index}]\n{page}"
            for index, page in enumerate(pages, start=1)
            if page.strip()
        )
        complete = bool(pages) and not empty_pages
        return text, {
            "format": "pdf",
            "status": (
                "available" if complete else "partial_text" if text else "unreadable"
            ),
            "capture_scope": (
                "all_pages_extracted_text" if complete else "incomplete_page_text"
            ),
            "page_count": len(pages),
            "pages_without_text": empty_pages,
        }
    try:
        text = raw.decode("utf-8-sig")
    except UnicodeDecodeError:
        return "", {
            "format": "unknown",
            "status": "unreadable",
            "capture_scope": "unsupported_encoding",
        }
    is_html = (
        content_type == "text/html"
        or suffix.lower() in {".html", ".htm"}
        or bool(re.match(r"\s*(?:<!doctype html|<html|<body)", text, re.I))
    )
    if is_html:
        parser = _HTMLTextExtractor()
        parser.feed(text)
        parser.close()
        text = "".join(parser.parts)
    elif b"\x00" in raw or (
        content_type
        and not content_type.startswith("text/")
        and content_type not in {"application/json", "application/xml"}
    ):
        return "", {
            "format": "unknown",
            "status": "unreadable",
            "capture_scope": "unsupported_format",
        }
    return text, {
        "format": "html" if is_html else "text",
        "status": "available" if text.strip() else "empty",
        "capture_scope": "complete_extracted_text",
    }


def _fetch_url_record(url: str, timeout: float) -> dict[str, Any]:
    try:
        _validate_public_url(url)
    except UnsafePublicUrlError as exc:
        return {
            "kind": "url",
            "url": url,
            "status": "blocked_non_public_destination",
            "http_status": 0,
            "character_count": 0,
            "excerpt": "",
            "error": str(exc),
        }
    except socket.gaierror as exc:
        return {
            "kind": "url",
            "url": url,
            "status": "unreachable",
            "http_status": 0,
            "character_count": 0,
            "excerpt": "",
            "error": str(exc),
        }
    request = urllib.request.Request(
        url,
        headers={"User-Agent": "MparanzaDeepResearchValidator/0.1"},
    )
    opener = urllib.request.build_opener(
        _PublicRedirectHandler(),
        urllib.request.ProxyHandler({}),
        _PublicHTTPHandler(),
        _PublicHTTPSHandler(),
    )
    try:
        with opener.open(request, timeout=timeout) as response:
            raw = response.read(MAX_CAPTURE_BYTES + 1)
            truncated = len(raw) > MAX_CAPTURE_BYTES
            raw = raw[:MAX_CAPTURE_BYTES]
            status = int(getattr(response, "status", 0) or 0)
            geturl = getattr(response, "geturl", None)
            final_url = str(geturl()) if callable(geturl) else url
            headers = getattr(response, "headers", None)
            declared_length = str(headers.get("Content-Length", "")) if headers else ""
            incomplete_response = declared_length.isdecimal() and int(
                declared_length
            ) > len(raw)
            content_type = (
                str(headers.get_content_type())
                if headers is not None and hasattr(headers, "get_content_type")
                else ""
            )
    except UnsafePublicUrlError as exc:
        return {
            "kind": "url",
            "url": url,
            "status": "blocked_non_public_destination",
            "http_status": 0,
            "character_count": 0,
            "excerpt": "",
            "error": str(exc),
        }
    except urllib.error.HTTPError as exc:
        return {
            "kind": "url",
            "url": url,
            "status": "http_error",
            "http_status": int(exc.code),
            "character_count": 0,
            "excerpt": "",
            "error": str(exc),
        }
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        return {
            "kind": "url",
            "url": url,
            "status": "unreachable",
            "http_status": 0,
            "character_count": 0,
            "excerpt": "",
            "error": str(exc),
        }

    cleaned, extraction = _extract_source_text(raw, content_type=content_type)
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    # HTTP 206 mechanically identifies a partial representation, even when
    # every byte of this particular response was captured.
    partial_response = status == 206
    parse_status = (
        "partial_capture"
        if truncated or partial_response or incomplete_response
        else extraction["status"]
    )
    return {
        "kind": "url",
        "url": url,
        "requested_url": url,
        "final_url": final_url,
        "status": parse_status,
        "http_status": status,
        "character_count": len(cleaned),
        "content_type": content_type,
        "content_hash": hashlib.sha256(raw).hexdigest(),
        "source_bytes_sha256": hashlib.sha256(raw).hexdigest(),
        "extracted_text_sha256": hashlib.sha256(cleaned.encode("utf-8")).hexdigest(),
        "extraction": extraction,
        "access_barrier_hint": _looks_blocked(cleaned),
        "capture_scope": (
            f"first_{MAX_CAPTURE_BYTES}_response_bytes"
            if truncated
            else (
                "incomplete_response"
                if incomplete_response
                else "partial_response" if partial_response else "complete_response"
            )
        ),
        "capture_truncated": truncated,
        "excerpt": cleaned[:1200],
        "error": "",
        "_captured_text": cleaned,
    }


def _persist_source_captures(
    records: list[dict[str, Any]],
    *,
    capture_dir: Path | None,
    capture_base_dir: Path | None,
) -> list[dict[str, Any]]:
    """Assign stable IDs and optionally persist complete normalized snapshots."""

    if capture_dir is not None:
        capture_dir.mkdir(parents=True, exist_ok=True)
    selected_base = capture_base_dir or capture_dir
    base_dir = selected_base.resolve() if selected_base is not None else None
    out: list[dict[str, Any]] = []
    canonical_captures: dict[str, tuple[str, str]] = {}
    for index, raw_record in enumerate(records, start=1):
        record = dict(raw_record)
        source_id = f"source-{index:03d}"
        record["source_id"] = source_id
        captured_text = str(record.pop("_captured_text", "") or "")
        if capture_dir is not None and base_dir is not None and captured_text:
            content_hash = str(record.get("content_hash") or "")
            canonical = canonical_captures.get(content_hash) if content_hash else None
            if canonical is None:
                capture_path = capture_dir / f"{source_id}.txt"
                capture_path.write_text(captured_text, encoding="utf-8")
                captured_text_path = (
                    capture_path.resolve().relative_to(base_dir).as_posix()
                )
                record["captured_text_path"] = captured_text_path
                if content_hash:
                    canonical_captures[content_hash] = (source_id, captured_text_path)
            else:
                canonical_source_id, captured_text_path = canonical
                record["captured_text_path"] = captured_text_path
                record["duplicate_content_of_source_id"] = canonical_source_id
                record["capture_reused"] = True
        out.append(record)
    return out


def inspect_sources(
    inventory_path: Path,
    *,
    source_files: list[Path] | None = None,
    timeout: float = 10.0,
    fetch_urls: bool = True,
    capture_dir: Path | None = None,
    capture_base_dir: Path | None = None,
    run_root: Path | None = None,
) -> dict[str, Any]:
    """Return deterministic source inventory."""

    urls = _extract_urls_from_inventory(inventory_path)
    url_records = (
        [_fetch_url_record(url, timeout) for url in urls]
        if fetch_urls
        else [
            {
                "kind": "url",
                "url": url,
                "status": "listed_not_fetched",
                "http_status": 0,
                "character_count": 0,
                "excerpt": "",
                "error": "",
            }
            for url in urls
        ]
    )
    file_records = [
        _source_file_record(path, run_root=run_root) for path in (source_files or [])
    ]
    records = _persist_source_captures(
        [*url_records, *file_records],
        capture_dir=capture_dir,
        capture_base_dir=capture_base_dir,
    )
    return {
        "path_reference": ("run_root_relative" if run_root is not None else "absolute"),
        "url_count": len(urls),
        "file_count": len(file_records),
        "sources": records,
    }


def write_source_inventory(
    inventory_path: Path,
    output_dir: Path,
    *,
    source_files: list[Path] | None = None,
    timeout: float = 10.0,
    fetch_urls: bool = True,
    run_root: Path | None = None,
) -> dict[str, Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    payload = inspect_sources(
        inventory_path,
        source_files=source_files,
        timeout=timeout,
        fetch_urls=fetch_urls,
        capture_dir=output_dir / "sources",
        capture_base_dir=output_dir,
        run_root=run_root,
    )
    path = output_dir / "source_inventory.json"
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return {"source_inventory": path}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("document_inventory", type=Path)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--client-engagement", type=Path, required=True)
    parser.add_argument("--source-file", type=Path, action="append", default=[])
    parser.add_argument("--timeout", type=float, default=10.0)
    parser.add_argument("--no-fetch", action="store_true")
    args = parser.parse_args()
    try:
        context = load_client_engagement_context_file(
            args.client_engagement,
            expected_workflow_id="deep-research-validator",
            input_paths=[args.document_inventory, *args.source_file],
            output_dir=args.output_dir,
        )
    except AssuranceContractError as exc:
        parser.error(str(exc))
    write_source_inventory(
        args.document_inventory,
        args.output_dir,
        source_files=args.source_file,
        timeout=args.timeout,
        fetch_urls=not args.no_fetch,
        run_root=Path(context["run_root"]),
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
