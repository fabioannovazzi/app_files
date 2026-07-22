"""Shared safety, public-query, and serialization helpers for Registro Imprese cases."""

from __future__ import annotations

import hashlib
import json
import re
import stat
import urllib.parse
from datetime import date, datetime, timezone
from html.parser import HTMLParser
from pathlib import Path
from typing import Any

__all__ = [
    "PLUGIN_NAME",
    "PrivacyError",
    "assert_generic_public_query",
    "ensure_safe_output_dir",
    "iso_now",
    "load_json_object",
    "mark_private_file",
    "normalize_html_text",
    "safe_identifier",
    "sha256_bytes",
    "sha256_file",
    "validate_iso_date",
    "validate_official_source_url",
    "write_private_json",
    "write_private_bytes",
    "write_private_text",
]

PLUGIN_NAME = "registro-imprese-sari"
MAX_JSON_BYTES = 5_000_000
SAFE_IDENTIFIER_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,79}$")
EMAIL_RE = re.compile(r"\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b", re.IGNORECASE)
ITALIAN_TAX_CODE_RE = re.compile(
    r"\b[A-Z]{6}[0-9]{2}[A-EHLMPRST][0-9]{2}[A-Z][0-9]{3}[A-Z]\b",
    re.IGNORECASE,
)
ITALIAN_VAT_RE = re.compile(r"(?<!\d)\d{11}(?!\d)")
PHONE_RE = re.compile(r"(?<!\w)(?:\+?39[ .-]?)?(?:0\d{1,3}|3\d{2})[ .-]?\d{5,8}(?!\w)")
OFFICIAL_EXACT_HOSTS = {
    "supportospecialisticori.infocamere.it",
    "registroimprese.infocamere.it",
    "dire.registroimprese.it",
    "www.inps.it",
    "www.ivass.it",
    "www.impresainungiorno.gov.it",
    "www.unioncamere.gov.it",
}


class PrivacyError(ValueError):
    """Raised when a public-source query appears to contain a direct identifier."""


class _TextExtractor(HTMLParser):
    """Extract readable text from the limited HTML fragments returned by SARI."""

    _BLOCK_TAGS = {
        "br",
        "div",
        "h1",
        "h2",
        "h3",
        "h4",
        "h5",
        "h6",
        "li",
        "ol",
        "p",
        "table",
        "td",
        "th",
        "tr",
        "ul",
    }

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        del attrs
        if tag.lower() in self._BLOCK_TAGS:
            self.parts.append("\n")

    def handle_endtag(self, tag: str) -> None:
        if tag.lower() in self._BLOCK_TAGS:
            self.parts.append("\n")

    def handle_data(self, data: str) -> None:
        self.parts.append(data)


def iso_now() -> str:
    """Return the current UTC timestamp in an audit-friendly ISO form."""

    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def sha256_bytes(raw: bytes) -> str:
    """Return a SHA-256 digest for bytes."""

    return hashlib.sha256(raw).hexdigest()


def sha256_file(path: Path) -> str:
    """Return a SHA-256 digest for one local file."""

    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def safe_identifier(value: object, *, field: str) -> str:
    """Validate a stable artifact identifier."""

    text = str(value or "").strip()
    if not SAFE_IDENTIFIER_RE.fullmatch(text):
        raise ValueError(
            f"{field} must be 1-80 characters using letters, digits, '.', '_' or '-'"
        )
    return text


def validate_iso_date(value: object, *, field: str) -> str:
    """Validate and normalize an ISO calendar date."""

    text = str(value or "").strip()
    try:
        parsed = date.fromisoformat(text)
    except ValueError as exc:
        raise ValueError(f"{field} must use YYYY-MM-DD") from exc
    return parsed.isoformat()


def validate_official_source_url(value: object) -> str:
    """Allow only known Italian institutional HTTPS source hosts."""

    text = str(value or "").strip()
    parsed = urllib.parse.urlsplit(text)
    host = (parsed.hostname or "").lower()
    host_allowed = host in OFFICIAL_EXACT_HOSTS or host.endswith(".camcom.it")
    if (
        parsed.scheme != "https"
        or not host_allowed
        or parsed.username
        or parsed.password
        or parsed.port not in (None, 443)
    ):
        raise ValueError("source URL must use an allowlisted official HTTPS host")
    if host == "supportospecialisticori.infocamere.it" and not parsed.path.startswith(
        "/sariWeb/"
    ):
        raise ValueError("SARI source URL must remain under /sariWeb/")
    return urllib.parse.urlunsplit(parsed)


def assert_generic_public_query(query: object) -> str:
    """Reject direct identifiers before a query is transmitted to public SARI.

    This gate is intentionally narrow: it detects mechanically recognizable email,
    Italian tax-code, and eleven-digit VAT patterns. It does not infer whether a
    legal or business concept is sensitive.
    """

    text = " ".join(str(query or "").split())
    if len(text) < 3 or len(text) > 160:
        raise PrivacyError("SARI query must contain 3-160 characters")
    findings: list[str] = []
    if EMAIL_RE.search(text):
        findings.append("email_address")
    if ITALIAN_TAX_CODE_RE.search(text):
        findings.append("italian_tax_code")
    if ITALIAN_VAT_RE.search(text):
        findings.append("eleven_digit_identifier")
    if PHONE_RE.search(text):
        findings.append("phone_number")
    if findings:
        raise PrivacyError(
            "SARI query must be generic and must not contain direct identifiers: "
            + ", ".join(findings)
        )
    return text


def normalize_html_text(value: object) -> str:
    """Convert a SARI HTML fragment to stable readable plain text."""

    parser = _TextExtractor()
    parser.feed(str(value or ""))
    parser.close()
    lines = [" ".join(line.split()) for line in "".join(parser.parts).splitlines()]
    return "\n".join(line for line in lines if line).strip()


def _find_git_root(start: Path) -> Path | None:
    for candidate in (start.resolve(), *start.resolve().parents):
        if (candidate / ".git").exists():
            return candidate
    return None


def _prepare_private_directory(path: Path) -> Path:
    if path.is_symlink():
        raise PermissionError(f"output directory cannot be a symbolic link: {path}")
    if path.exists():
        if not path.is_dir():
            raise NotADirectoryError(path)
        permissions = stat.S_IMODE(path.stat().st_mode)
        if permissions & 0o077:
            raise PermissionError(
                f"existing output directory must already be owner-only (0700): {path}"
            )
        return path
    path.mkdir(parents=True, mode=0o700, exist_ok=False)
    path.chmod(0o700)
    return path


def ensure_safe_output_dir(output_dir: Path, *, plugin_root: Path) -> Path:
    """Create a private output directory outside the source Git workspace."""

    expanded = output_dir.expanduser()
    if expanded.is_symlink():
        raise ValueError("output directory cannot be a symbolic link")
    resolved = expanded.resolve()
    git_root = _find_git_root(plugin_root)
    if git_root is not None and (resolved == git_root or git_root in resolved.parents):
        raise ValueError(
            f"output directory must be outside the Git workspace: {git_root}"
        )
    return _prepare_private_directory(resolved)


def mark_private_file(path: Path) -> Path:
    """Restrict a written case artifact to its owner."""

    path.chmod(0o600)
    return path


def write_private_text(path: Path, text: str) -> Path:
    """Write UTF-8 text under an existing private case directory."""

    if path.parent.is_symlink():
        raise PermissionError(f"output parent cannot be a symbolic link: {path.parent}")
    path.parent.mkdir(parents=True, mode=0o700, exist_ok=True)
    path.parent.chmod(0o700)
    path.write_text(text, encoding="utf-8")
    return mark_private_file(path)


def write_private_bytes(path: Path, raw: bytes) -> Path:
    """Write bytes under an existing private case directory."""

    if path.parent.is_symlink():
        raise PermissionError(f"output parent cannot be a symbolic link: {path.parent}")
    path.parent.mkdir(parents=True, mode=0o700, exist_ok=True)
    path.parent.chmod(0o700)
    path.write_bytes(raw)
    return mark_private_file(path)


def write_private_json(path: Path, payload: dict[str, Any]) -> Path:
    """Write stable, owner-only UTF-8 JSON."""

    return write_private_text(
        path, json.dumps(payload, ensure_ascii=False, indent=2) + "\n"
    )


def load_json_object(path: Path) -> dict[str, Any]:
    """Read a bounded JSON object from a regular file."""

    if path.is_symlink() or not path.is_file():
        raise ValueError(f"JSON input must be a regular file: {path}")
    if path.stat().st_size > MAX_JSON_BYTES:
        raise ValueError(f"JSON input exceeds {MAX_JSON_BYTES} bytes: {path}")
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"JSON input must contain an object: {path}")
    return payload
