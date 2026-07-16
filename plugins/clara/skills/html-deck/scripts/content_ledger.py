#!/usr/bin/env python3
"""Validate and publish traceable Clara HTML deck content ledgers.

The ledger enforces referential integrity only. It does not judge whether a
claim is true, relevant, or correctly interpreted; those semantic decisions
remain part of Clara's advisory and presentation loops.
"""

from __future__ import annotations

import html
import json
import re
from collections.abc import Mapping, Sequence
from typing import Any

__all__ = [
    "CLASSIFICATIONS",
    "SCHEMA_VERSION",
    "embedded_ledger_markup",
    "extract_embedded_ledger",
    "publication_ledger",
    "validate_content_ledger",
]

SCHEMA_VERSION = "clara.html_deck_ledger.v1"
LEDGER_ELEMENT_ID = "claraContentLedger"
SAFE_ID_RE = re.compile(r"^[a-z0-9][a-z0-9._-]*$")
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
CLASSIFICATIONS = frozenset(
    {
        "fact",
        "assumption",
        "target",
        "forecast",
        "probability",
        "illustrative",
        "judgement",
        "open-question",
    }
)
BASIS_STATUSES = frozenset({"source-backed", "speaker-judgement", "not-applicable"})
EMBEDDED_LEDGER_RE = re.compile(
    rf'<script\b[^>]*id=["\']{LEDGER_ELEMENT_ID}["\'][^>]*>(?P<payload>.*?)</script>',
    flags=re.IGNORECASE | re.DOTALL,
)


def _mapping(value: Any, *, label: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise ValueError(f"{label} must be an object")
    return value


def _sequence(value: Any, *, label: str) -> list[Any]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes, bytearray)):
        raise ValueError(f"{label} must be a list")
    return list(value)


def _required_text(value: Any, *, label: str) -> str:
    text = str(value or "").strip()
    if not text:
        raise ValueError(f"{label} is required")
    return text


def _safe_id(value: Any, *, label: str) -> str:
    text = _required_text(value, label=label)
    if not SAFE_ID_RE.fullmatch(text):
        raise ValueError(f"{label} must be a stable lowercase ID")
    return text


def validate_content_ledger(
    ledger: Mapping[str, Any],
    *,
    slide_ids: Sequence[str] | None = None,
) -> dict[str, Any]:
    """Return a normalized ledger after checking mechanical integrity."""

    if ledger.get("schema_version") != SCHEMA_VERSION:
        raise ValueError(
            f"unsupported content ledger schema: {ledger.get('schema_version')!r}"
        )

    normalized_sources: list[dict[str, Any]] = []
    source_ids: set[str] = set()
    for index, raw_source in enumerate(
        _sequence(ledger.get("sources"), label="ledger.sources")
    ):
        source = _mapping(raw_source, label=f"ledger.sources[{index}]")
        source_id = _safe_id(source.get("id"), label=f"ledger.sources[{index}].id")
        if source_id in source_ids:
            raise ValueError(f"duplicate source ID: {source_id}")
        source_ids.add(source_id)
        publish_locator = source.get("publish_locator", False)
        if type(publish_locator) is not bool:
            raise ValueError(
                f"ledger.sources[{index}].publish_locator must be a boolean"
            )
        source_sha256 = str(source.get("sha256", "")).strip()
        if source_sha256 and not SHA256_RE.fullmatch(source_sha256):
            raise ValueError(
                f"ledger.sources[{index}].sha256 must be a lowercase SHA-256 value"
            )
        normalized_sources.append(
            {
                "id": source_id,
                "label": _required_text(
                    source.get("label"), label=f"ledger.sources[{index}].label"
                ),
                "kind": _required_text(
                    source.get("kind", "source"), label=f"ledger.sources[{index}].kind"
                ),
                "locator": str(source.get("locator", "")).strip(),
                "sha256": source_sha256,
                "publish_locator": publish_locator,
            }
        )

    normalized_slides: list[dict[str, Any]] = []
    seen_slides: set[str] = set()
    seen_claims: set[str] = set()
    for index, raw_slide in enumerate(
        _sequence(ledger.get("slides"), label="ledger.slides")
    ):
        slide = _mapping(raw_slide, label=f"ledger.slides[{index}]")
        slide_id = _safe_id(
            slide.get("slide_id"), label=f"ledger.slides[{index}].slide_id"
        )
        if slide_id in seen_slides:
            raise ValueError(f"duplicate ledger slide ID: {slide_id}")
        seen_slides.add(slide_id)
        status = _required_text(
            slide.get("basis_status"),
            label=f"ledger.slides[{index}].basis_status",
        )
        if status not in BASIS_STATUSES:
            raise ValueError(
                f"unsupported basis_status for slide {slide_id}: {status!r}"
            )
        claims: list[dict[str, Any]] = []
        for claim_index, raw_claim in enumerate(
            _sequence(slide.get("claims", []), label=f"ledger.slides[{index}].claims")
        ):
            claim = _mapping(
                raw_claim,
                label=f"ledger.slides[{index}].claims[{claim_index}]",
            )
            claim_id = _safe_id(
                claim.get("id"),
                label=f"ledger.slides[{index}].claims[{claim_index}].id",
            )
            if claim_id in seen_claims:
                raise ValueError(f"duplicate claim ID: {claim_id}")
            seen_claims.add(claim_id)
            classification = _required_text(
                claim.get("classification"),
                label=f"claim {claim_id}.classification",
            )
            if classification not in CLASSIFICATIONS:
                raise ValueError(
                    f"unsupported classification for claim {claim_id}: {classification!r}"
                )
            claim_basis_status = _required_text(
                claim.get("basis_status"),
                label=f"claim {claim_id}.basis_status",
            )
            if claim_basis_status not in BASIS_STATUSES:
                raise ValueError(
                    f"unsupported basis_status for claim {claim_id}: "
                    f"{claim_basis_status!r}"
                )
            claim_source_ids = [
                _safe_id(item, label=f"claim {claim_id}.source_ids[]")
                for item in _sequence(
                    claim.get("source_ids", []),
                    label=f"claim {claim_id}.source_ids",
                )
            ]
            unknown_sources = sorted(set(claim_source_ids) - source_ids)
            if unknown_sources:
                raise ValueError(
                    f"claim {claim_id} references unknown sources: {unknown_sources}"
                )
            if claim_basis_status == "source-backed" and not claim_source_ids:
                raise ValueError(
                    f"source-backed claim {claim_id} must reference at least one source"
                )
            if classification == "fact" and claim_basis_status != "source-backed":
                raise ValueError(
                    f"fact claim {claim_id} must use source-backed basis_status"
                )
            claim_basis_note = str(claim.get("basis_note", "")).strip()
            if claim_basis_status != "source-backed" and not claim_basis_note:
                raise ValueError(
                    f"claim {claim_id} with basis_status {claim_basis_status!r} "
                    "needs basis_note"
                )
            claims.append(
                {
                    "id": claim_id,
                    "statement": _required_text(
                        claim.get("statement"),
                        label=f"claim {claim_id}.statement",
                    ),
                    "classification": classification,
                    "basis_status": claim_basis_status,
                    "basis_note": claim_basis_note,
                    "source_ids": sorted(set(claim_source_ids)),
                    "qualification": str(claim.get("qualification", "")).strip(),
                }
            )
        if status == "source-backed" and not claims:
            raise ValueError(f"source-backed slide {slide_id} must contain a claim")
        if status != "source-backed" and not str(slide.get("basis_note", "")).strip():
            raise ValueError(
                f"slide {slide_id} with basis_status {status!r} needs basis_note"
            )
        normalized_slides.append(
            {
                "slide_id": slide_id,
                "basis_status": status,
                "basis_note": str(slide.get("basis_note", "")).strip(),
                "claims": claims,
            }
        )

    if slide_ids is not None:
        expected = list(slide_ids)
        if len(expected) != len(set(expected)):
            raise ValueError("deck slide IDs must be unique before ledger validation")
        missing = sorted(set(expected) - seen_slides)
        extra = sorted(seen_slides - set(expected))
        if missing or extra:
            raise ValueError(
                f"ledger/deck slide mismatch; missing={missing}, extra={extra}"
            )

    return {
        "schema_version": SCHEMA_VERSION,
        "sources": normalized_sources,
        "slides": normalized_slides,
    }


def publication_ledger(ledger: Mapping[str, Any]) -> dict[str, Any]:
    """Remove private source locators unless publication is explicitly allowed."""

    normalized = validate_content_ledger(ledger)
    sources: list[dict[str, Any]] = []
    for source in normalized["sources"]:
        published = {
            "id": source["id"],
            "label": source["label"],
            "kind": source["kind"],
        }
        if source["sha256"]:
            published["sha256"] = source["sha256"]
        if source["publish_locator"] and source["locator"]:
            published["locator"] = source["locator"]
        sources.append(published)
    return {
        "schema_version": SCHEMA_VERSION,
        "sources": sources,
        "slides": normalized["slides"],
    }


def embedded_ledger_markup(ledger: Mapping[str, Any]) -> str:
    """Return safe inline JSON for the standalone publication."""

    rendered = json.dumps(
        publication_ledger(ledger),
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    )
    rendered = (
        rendered.replace("&", "\\u0026").replace("<", "\\u003c").replace(">", "\\u003e")
    )
    return (
        f'<script id="{LEDGER_ELEMENT_ID}" type="application/json" '
        f'data-schema-version="{SCHEMA_VERSION}">{rendered}</script>'
    )


def extract_embedded_ledger(html_text: str) -> dict[str, Any] | None:
    """Return and validate the publication ledger embedded in a deck."""

    match = EMBEDDED_LEDGER_RE.search(html_text)
    if not match:
        return None
    payload = json.loads(html.unescape(match.group("payload")))
    return validate_content_ledger(_mapping(payload, label="embedded ledger"))
