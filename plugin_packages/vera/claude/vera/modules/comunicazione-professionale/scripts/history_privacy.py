#!/usr/bin/env python3
"""Prepare selected communication history for one semantic privacy pass."""

from __future__ import annotations

import hashlib
import html
import re
import zipfile
from email import policy
from email.parser import BytesParser
from pathlib import Path
from typing import Any, Callable, Iterable

from defusedxml import ElementTree
from defusedxml.common import DefusedXmlException

__all__ = [
    "MECHANICAL_STRIPPING_VERSION",
    "extract_history_text",
    "strip_mechanical_identifiers",
]

MECHANICAL_STRIPPING_VERSION = "mechanical-identifiers-v1"

_EMAIL_RE = re.compile(
    r"(?<![\w.+-])(?P<value>[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,63})(?![\w.-])",
    re.IGNORECASE,
)
_ITALIAN_TAX_CODE_RE = re.compile(
    r"(?<![A-Z0-9])(?P<value>[A-Z]{6}[0-9]{2}[A-Z][0-9]{2}[A-Z][0-9]{3}[A-Z])(?![A-Z0-9])",
    re.IGNORECASE,
)
_LABELLED_TAX_ID_RE = re.compile(
    r"(?P<label>\b(?:codice\s+fiscale|c\.?\s*f\.?|partita\s+iva|p\.?\s*iva|tax\s+code|tax\s+id|vat(?:\s+(?:id|number))?|tin|nif)\b\s*[:#-]?\s*)"
    r"(?P<value>(?:[A-Z]{2})?[A-Z0-9][A-Z0-9._-]{4,30})",
    re.IGNORECASE,
)
_LABELLED_PHONE_RE = re.compile(
    r"(?P<label>\b(?:tel(?:efono)?|cell(?:ulare)?|mobile|phone|fax|whatsapp)\b\s*[:#-]?\s*)"
    r"(?P<value>\+?[0-9][0-9 ()/.-]{5,}[0-9])",
    re.IGNORECASE,
)
_INTERNATIONAL_PHONE_RE = re.compile(
    r"(?<![\w+])(?P<value>\+[1-9][0-9 ()/.-]{7,}[0-9])(?!\w)",
)
_ITALIAN_MOBILE_RE = re.compile(
    r"(?<![\w+])(?P<value>3[0-9]{2}(?:[ ./-]?[0-9]){7})(?!\w)",
)
_LABELLED_ACCOUNT_RE = re.compile(
    r"(?P<label>\b(?:numero\s+di\s+conto|numero\s+conto|conto\s+corrente|conto|c\s*/\s*c|account(?:\s+number)?)\b\s*[:#-]?\s*)"
    r"(?P<value>(?=[A-Z0-9./_-]{4,40}\b)(?=[A-Z0-9./_-]*\d)[A-Z0-9][A-Z0-9./_-]{3,39})",
    re.IGNORECASE,
)
_LABELLED_CASE_RE = re.compile(
    r"(?P<label>\b(?:numero\s+pratica|pratica|fascicolo|case|protocollo|prot\.?|riferimento|rif\.?)\b\s*[:#-]?\s*)"
    r"(?P<value>(?=[A-Z0-9./_-]{2,50}\b)(?=[A-Z0-9./_-]*\d)[A-Z0-9][A-Z0-9./_-]{1,49})",
    re.IGNORECASE,
)
_IBAN_CANDIDATE_RE = re.compile(
    r"(?<![A-Z0-9])(?P<value>[A-Z]{2}\d{2}(?:[ ]?[A-Z0-9]){11,30})(?![A-Z0-9])",
    re.IGNORECASE,
)


def _decode_text(data: bytes, *, label: str) -> str:
    """Decode human-authored text without silently replacing unknown bytes."""

    for encoding in ("utf-8-sig", "utf-16", "cp1252"):
        try:
            return data.decode(encoding)
        except UnicodeDecodeError:
            continue
    raise ValueError(f"Selected history is not readable text: {label}")


def _html_to_text(value: str) -> str:
    """Preserve visible block boundaries while removing markup locally."""

    without_scripts = re.sub(
        r"(?is)<(?:script|style)\b[^>]*>.*?</(?:script|style)>", "", value
    )
    with_breaks = re.sub(
        r"(?i)</?(?:p|div|section|article|header|footer|li|h[1-6]|tr|br)\b[^>]*>",
        "\n",
        without_scripts,
    )
    text = re.sub(r"(?s)<[^>]+>", "", with_breaks)
    return html.unescape(text)


def _extract_eml(path: Path) -> str:
    """Extract readable headers and bodies from one local RFC 822 message."""

    message = BytesParser(policy=policy.default).parsebytes(path.read_bytes())
    header_lines = [
        f"{name}: {message.get(name)}"
        for name in ("From", "To", "Cc", "Date", "Subject")
        if message.get(name)
    ]
    bodies: list[str] = []
    parts = message.walk() if message.is_multipart() else [message]
    for part in parts:
        if part.is_multipart() or part.get_content_disposition() == "attachment":
            continue
        content_type = part.get_content_type()
        if content_type not in {"text/plain", "text/html"}:
            continue
        try:
            content = part.get_content()
        except (LookupError, UnicodeDecodeError) as exc:
            raise ValueError(f"Selected email body is not readable: {path}") from exc
        if not isinstance(content, str):
            continue
        bodies.append(
            _html_to_text(content) if content_type == "text/html" else content
        )
    return "\n".join([*header_lines, *bodies])


def _extract_docx(path: Path) -> str:
    """Extract ordered WordprocessingML text without expanding the archive."""

    try:
        with zipfile.ZipFile(path) as archive:
            names = archive.namelist()
            selected = [
                name
                for name in names
                if re.fullmatch(
                    r"word/(?:document|header\d+|footer\d+|footnotes|endnotes)\.xml",
                    name,
                )
            ]
            if "word/document.xml" not in selected:
                raise ValueError(f"DOCX has no main document part: {path}")
            ordered = [
                "word/document.xml",
                *sorted(set(selected) - {"word/document.xml"}),
            ]
            parts: list[str] = []
            for name in ordered:
                root = ElementTree.fromstring(archive.read(name))
                paragraphs: list[str] = []
                for paragraph in root.iter(
                    "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}p"
                ):
                    value = "".join(
                        node.text or ""
                        for node in paragraph.iter(
                            "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}t"
                        )
                    )
                    if value.strip():
                        paragraphs.append(value)
                if paragraphs:
                    parts.append("\n".join(paragraphs))
    except (zipfile.BadZipFile, ElementTree.ParseError, DefusedXmlException) as exc:
        raise ValueError(f"Selected DOCX is not readable: {path}") from exc
    return "\n\n".join(parts)


def _extract_pdf(path: Path) -> str:
    """Extract locally available PDF text; never send an unreadable PDF onward."""

    try:
        from pypdf import PdfReader

        reader = PdfReader(str(path))
        if reader.is_encrypted:
            raise ValueError(f"Selected PDF is encrypted: {path}")
        return "\n\n".join((page.extract_text() or "") for page in reader.pages)
    except (OSError, ValueError) as exc:
        raise ValueError(f"Selected PDF is not readable locally: {path}") from exc


def extract_history_text(path: Path) -> str:
    """Extract a complete textual derivative from a supported local document."""

    source = path.resolve(strict=True)
    suffix = source.suffix.lower()
    if suffix == ".eml":
        text = _extract_eml(source)
    elif suffix == ".docx":
        text = _extract_docx(source)
    elif suffix == ".pdf":
        text = _extract_pdf(source)
    elif suffix in {".html", ".htm"}:
        text = _html_to_text(_decode_text(source.read_bytes(), label=str(source)))
    elif suffix in {".txt", ".md", ".markdown", ".csv", ".json", ".xml"}:
        text = _decode_text(source.read_bytes(), label=str(source))
    else:
        raise ValueError(
            "Selected history format cannot be stripped locally; use TXT, Markdown, "
            f"HTML, EML, DOCX, or text-readable PDF: {source.name}"
        )
    normalized = text.replace("\r\n", "\n").replace("\r", "\n").strip()
    if not normalized:
        raise ValueError(
            f"Selected history contains no locally readable text: {source}"
        )
    return normalized + "\n"


def _iban_valid(value: str) -> bool:
    compact = re.sub(r"\s+", "", value).upper()
    if not 15 <= len(compact) <= 34 or not compact[:2].isalpha():
        return False
    rearranged = compact[4:] + compact[:4]
    numeric = "".join(
        str(ord(char) - 55) if char.isalpha() else char for char in rearranged
    )
    remainder = 0
    for character in numeric:
        remainder = (remainder * 10 + int(character)) % 97
    return remainder == 1


def _phone_valid(value: str) -> bool:
    digits = re.sub(r"\D", "", value)
    return 7 <= len(digits) <= 15


def _labelled_value_valid(value: str) -> bool:
    return any(character.isdigit() for character in value)


def _normalizer(category: str, value: str) -> str:
    if category == "email":
        return value.casefold()
    if category in {"phone", "tax_id", "bank_account"}:
        return re.sub(r"[\s()./-]+", "", value).upper()
    return re.sub(r"\s+", " ", value).strip().casefold()


def _candidate_matches(
    text: str,
) -> Iterable[tuple[int, int, str, str, str]]:
    patterns: tuple[tuple[str, re.Pattern[str], Callable[[str], bool]], ...] = (
        ("email", _EMAIL_RE, lambda _value: True),
        ("tax_id", _ITALIAN_TAX_CODE_RE, lambda _value: True),
        ("tax_id", _LABELLED_TAX_ID_RE, _labelled_value_valid),
        ("bank_account", _IBAN_CANDIDATE_RE, _iban_valid),
        ("phone", _LABELLED_PHONE_RE, _phone_valid),
        ("phone", _INTERNATIONAL_PHONE_RE, _phone_valid),
        ("phone", _ITALIAN_MOBILE_RE, _phone_valid),
        ("bank_account", _LABELLED_ACCOUNT_RE, _labelled_value_valid),
        ("case_number", _LABELLED_CASE_RE, _labelled_value_valid),
    )
    for category, pattern, validator in patterns:
        for match in pattern.finditer(text):
            value = match.group("value").strip()
            if validator(value):
                start, end = match.span("value")
                yield start, end, category, value, pattern.pattern


def strip_mechanical_identifiers(
    text: str,
    *,
    existing_placeholders: dict[tuple[str, str], str] | None = None,
    counters: dict[str, int] | None = None,
) -> tuple[str, list[dict[str, Any]], dict[tuple[str, str], str], dict[str, int]]:
    """Replace explicit-format identifiers and return a local reversible map.

    Fixed patterns are justified here because the matched formats are mechanically
    verifiable and must be removed before any model sees the selected history.
    Contextual names, addresses, organizations, and case meaning remain model-led.
    """

    placeholders = existing_placeholders if existing_placeholders is not None else {}
    next_numbers = counters if counters is not None else {}
    candidates = sorted(
        _candidate_matches(text), key=lambda row: (row[0], -(row[1] - row[0]))
    )
    accepted: list[tuple[int, int, str, str, str]] = []
    last_end = -1
    for candidate in candidates:
        start, end, _category, _value, _rule = candidate
        if start < last_end:
            continue
        accepted.append(candidate)
        last_end = end

    pieces: list[str] = []
    entries: list[dict[str, Any]] = []
    cursor = 0
    labels = {
        "email": "EMAIL",
        "phone": "PHONE",
        "tax_id": "TAX_ID",
        "bank_account": "ACCOUNT",
        "case_number": "CASE",
    }
    for start, end, category, value, rule in accepted:
        normalized = _normalizer(category, value)
        key = (category, normalized)
        placeholder = placeholders.get(key)
        if placeholder is None:
            next_numbers[category] = next_numbers.get(category, 0) + 1
            placeholder = f"[{labels[category]}_{next_numbers[category]}]"
            placeholders[key] = placeholder
        pieces.extend((text[cursor:start], placeholder))
        entries.append(
            {
                "category": category,
                "original_value": value,
                "original_sha256": hashlib.sha256(value.encode("utf-8")).hexdigest(),
                "placeholder": placeholder,
                "detected_by": MECHANICAL_STRIPPING_VERSION,
                "rule_sha256": hashlib.sha256(rule.encode("utf-8")).hexdigest(),
            }
        )
        cursor = end
    pieces.append(text[cursor:])
    return "".join(pieces), entries, placeholders, next_numbers
