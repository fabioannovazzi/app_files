"""Capture one public web source and register an explicit advisory observation."""

from __future__ import annotations

# Direct CLI calls must select dependencies before importing workflow modules.
if __name__ == "__main__":
    import runpy as _runpy
    from pathlib import Path as _Path

    for _parent in _Path(__file__).resolve().parents:
        _launcher = _parent / "scripts" / "self_relaunch.py"
        if not _launcher.is_file():
            _launcher = _parent / "clara" / "scripts" / "self_relaunch.py"
        if _launcher.is_file():
            _runpy.run_path(str(_launcher))["ensure_running_in_managed_venv"](__file__)
            break
    else:
        # Standalone components retain their host's dependency setup.
        if any(
            (_p / "components.json").is_file()
            for _p in _Path(__file__).resolve().parents
        ):
            raise SystemExit(
                "Managed Python launcher is missing; rebuild the plugin package."
            )

import argparse
import hashlib
import html
import ipaddress
import json
import logging
import re
import shutil
import socket
import tempfile
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from html.parser import HTMLParser
from pathlib import Path
from typing import Any, Sequence

from advisory_evidence_lineage import LineageError, record_evidence

__all__ = ["UnsafePublicUrlError", "capture_web_evidence"]

LOGGER = logging.getLogger(__name__)
MAX_CAPTURE_BYTES = 1_000_000
STANDARD_PORTS = {"http": 80, "https": 443}
SAFE_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")


class UnsafePublicUrlError(ValueError):
    """Raised when a URL can reach a non-public network destination."""


class _VisibleTextParser(HTMLParser):
    HIDDEN = {"script", "style", "template"}

    def __init__(self) -> None:
        super().__init__()
        self.parts: list[str] = []
        self.hidden_depth = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag.casefold() in self.HIDDEN:
            self.hidden_depth += 1
        elif not self.hidden_depth and tag.casefold() in {
            "p",
            "br",
            "li",
            "tr",
            "h1",
            "h2",
            "h3",
        }:
            self.parts.append("\n")

    def handle_endtag(self, tag: str) -> None:
        if tag.casefold() in self.HIDDEN and self.hidden_depth:
            self.hidden_depth -= 1
        elif not self.hidden_depth and tag.casefold() in {
            "p",
            "li",
            "tr",
            "h1",
            "h2",
            "h3",
        }:
            self.parts.append("\n")

    def handle_data(self, data: str) -> None:
        if not self.hidden_depth:
            self.parts.append(html.unescape(data))

    def text(self) -> str:
        return re.sub(r"\n{3,}", "\n\n", "".join(self.parts)).strip()


def _validate_public_url(url: str) -> None:
    parsed = urllib.parse.urlparse(url)
    if (
        parsed.scheme.casefold() not in STANDARD_PORTS
        or not parsed.hostname
        or parsed.username is not None
        or parsed.password is not None
    ):
        raise UnsafePublicUrlError("only public HTTP/S URLs without credentials")
    try:
        port = parsed.port
    except ValueError as exc:
        raise UnsafePublicUrlError("URL port is invalid") from exc
    expected_port = STANDARD_PORTS[parsed.scheme.casefold()]
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
        addresses = [
            ipaddress.ip_address(record[4][0])
            for record in socket.getaddrinfo(
                hostname,
                expected_port,
                type=socket.SOCK_STREAM,
            )
        ]
    if not addresses or any(not address.is_global for address in addresses):
        raise UnsafePublicUrlError("URL resolves to a non-public network address")


class _PublicRedirectHandler(urllib.request.HTTPRedirectHandler):
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


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _artifact(case_dir: Path, path: Path, media_type: str) -> dict[str, Any]:
    return {
        "path": path.resolve().relative_to(case_dir.resolve()).as_posix(),
        "path_reference": "case_relative",
        "sha256": _sha256(path),
        "byte_count": path.stat().st_size,
        "media_type": media_type,
    }


def capture_web_evidence(
    case_dir: Path,
    *,
    url: str,
    evidence_id: str,
    observation: str,
    scope: str,
    limitations: Sequence[str] = (),
    recorded_by: str = "clara:clara",
    recorded_at: datetime | None = None,
    timeout: float = 10.0,
    opener: Any | None = None,
) -> dict[str, Any]:
    """Capture source bytes; semantic observation and limits stay caller-authored."""

    if SAFE_ID_RE.fullmatch(evidence_id) is None:
        raise ValueError("evidence_id contains unsupported characters")
    if not observation.strip() or not scope.strip():
        raise ValueError("observation and scope are required")
    _validate_public_url(url)
    request = urllib.request.Request(
        url,
        headers={"User-Agent": "MparanzaClaraAdvisoryEvidence/0.1"},
    )
    active_opener = opener or urllib.request.build_opener(_PublicRedirectHandler())
    with active_opener.open(request, timeout=timeout) as response:
        raw = response.read(MAX_CAPTURE_BYTES + 1)
        truncated = len(raw) > MAX_CAPTURE_BYTES
        raw = raw[:MAX_CAPTURE_BYTES]
        final_url = str(response.geturl()) if callable(response.geturl) else url
        _validate_public_url(final_url)
        headers = getattr(response, "headers", None)
        media_type = (
            str(headers.get_content_type())
            if headers is not None and hasattr(headers, "get_content_type")
            else "application/octet-stream"
        )
        charset = (
            str(headers.get_content_charset() or "utf-8")
            if headers is not None and hasattr(headers, "get_content_charset")
            else "utf-8"
        )
        http_status = int(getattr(response, "status", 0) or 0)

    decoded = raw.decode(charset, errors="replace")
    if "html" in media_type.casefold():
        parser = _VisibleTextParser()
        parser.feed(decoded)
        normalized = parser.text()
    else:
        normalized = decoded.strip()
    capture_parent = case_dir / "source_materials" / "web"
    capture_parent.mkdir(parents=True, exist_ok=True)
    capture_dir = capture_parent / evidence_id
    if capture_dir.exists():
        raise FileExistsError(capture_dir)
    temporary_dir = Path(
        tempfile.mkdtemp(prefix=f".{evidence_id}.", dir=capture_parent)
    )
    try:
        (temporary_dir / "response.bin").write_bytes(raw)
        (temporary_dir / "normalized.txt").write_text(
            normalized.rstrip() + "\n", encoding="utf-8"
        )
        temporary_dir.replace(capture_dir)
    finally:
        if temporary_dir.exists():
            shutil.rmtree(temporary_dir)
    raw_path = capture_dir / "response.bin"
    normalized_path = capture_dir / "normalized.txt"
    timestamp = (recorded_at or datetime.now(timezone.utc)).isoformat()
    recorded_limitations = [str(item) for item in limitations if str(item).strip()]
    if truncated:
        recorded_limitations.append(
            f"Capture was truncated after {MAX_CAPTURE_BYTES} response bytes."
        )
    receipt = {
        "id": evidence_id,
        "evidence_type": "web_capture",
        "recorded_at": timestamp,
        "recorded_by": recorded_by,
        "capture_status": "captured",
        "source": {
            "material_ids": [],
            "url": final_url,
            "locator": f"requested {url}; final {final_url}; HTTP {http_status}",
            "artifact_refs": [
                _artifact(case_dir, raw_path, media_type),
                _artifact(case_dir, normalized_path, "text/plain"),
            ],
        },
        "observation": observation.strip(),
        "scope": scope.strip(),
        "limitations": recorded_limitations,
        "verification": {
            "status": "identity_verified",
            "checked_at": timestamp,
            "method": "public HTTP capture with requested and final URL validation",
            "notes": [
                "Identity verification confirms the captured response, not the semantic truth or completeness of the caller-authored observation."
            ],
        },
        "rechecks_evidence_id": "",
        "supersedes_evidence_id": "",
    }
    try:
        record_evidence(case_dir, [receipt])
    except (LineageError, OSError, json.JSONDecodeError):
        shutil.rmtree(capture_dir)
        raise
    return receipt


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("case_dir", type=Path)
    parser.add_argument("url")
    parser.add_argument("--evidence-id", required=True)
    parser.add_argument("--observation", required=True)
    parser.add_argument("--scope", required=True)
    parser.add_argument("--limitation", action="append", default=[])
    parser.add_argument("--recorded-by", default="clara:clara")
    parser.add_argument("--timeout", type=float, default=10.0)
    return parser


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    args = _parser().parse_args()
    receipt = capture_web_evidence(
        args.case_dir,
        url=args.url,
        evidence_id=args.evidence_id,
        observation=args.observation,
        scope=args.scope,
        limitations=args.limitation,
        recorded_by=args.recorded_by,
        timeout=args.timeout,
    )
    LOGGER.info("Captured advisory web evidence: %s", receipt["id"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
