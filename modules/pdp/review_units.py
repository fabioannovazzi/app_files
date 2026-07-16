from __future__ import annotations

import hashlib
import json
from typing import Any, Mapping, Sequence

__all__ = [
    "canonical_review_units_from_payload",
    "review_set_hash_from_payload",
    "review_text_unit_count_from_payload",
]

_SUMMARY_FIELDS = (
    ("reviews_positive", "positive_summary"),
    ("reviews_negative", "negative_summary"),
)


def _clean_text(value: object | None) -> str | None:
    if not isinstance(value, str):
        return None
    text = " ".join(value.split())
    return text or None


def _rating_value(value: object | None) -> float | None:
    if value in (None, ""):
        return None
    try:
        return float(str(value))
    except ValueError:
        return None


def _canonical_text_unit(
    *,
    source: str,
    headline: object | None,
    comment: object | None,
    rating: object | None = None,
    created_date: object | None = None,
) -> dict[str, object] | None:
    clean_headline = _clean_text(headline)
    clean_comment = _clean_text(comment)
    if not clean_headline and not clean_comment:
        return None
    unit: dict[str, object] = {
        "source": source,
        "headline": clean_headline,
        "comment": clean_comment,
    }
    clean_rating = _rating_value(rating)
    if clean_rating is not None:
        unit["rating"] = clean_rating
    clean_created = _clean_text(created_date)
    if clean_created:
        unit["created_date"] = clean_created
    return unit


def _unit_identity(unit: Mapping[str, object]) -> str:
    identity = {
        "source": unit.get("source"),
        "headline": unit.get("headline"),
        "comment": unit.get("comment"),
        "rating": unit.get("rating"),
        "created_date": unit.get("created_date"),
    }
    return json.dumps(
        identity, sort_keys=True, ensure_ascii=False, separators=(",", ":")
    )


def _dedupe_units(units: Sequence[dict[str, object]]) -> list[dict[str, object]]:
    deduped: list[dict[str, object]] = []
    seen: set[str] = set()
    for unit in units:
        identity = _unit_identity(unit)
        if identity in seen:
            continue
        seen.add(identity)
        deduped.append(unit)
    return deduped


def canonical_review_units_from_payload(
    payload: Mapping[str, Any],
) -> tuple[dict[str, object], ...]:
    """Return canonical review text units used to dedupe review LLM calls."""

    units: list[dict[str, object]] = []
    for payload_key, source in _SUMMARY_FIELDS:
        summary = payload.get(payload_key)
        if not isinstance(summary, Mapping):
            continue
        unit = _canonical_text_unit(
            source=source,
            headline=summary.get("headline"),
            comment=summary.get("comment"),
        )
        if unit is not None:
            units.append(unit)

    reviews = payload.get("reviews")
    if isinstance(reviews, Sequence) and not isinstance(
        reviews, (str, bytes, bytearray)
    ):
        review_units: list[dict[str, object]] = []
        for item in reviews:
            if not isinstance(item, Mapping):
                continue
            unit = _canonical_text_unit(
                source="review",
                headline=item.get("headline"),
                comment=item.get("comment"),
                rating=item.get("rating"),
                created_date=item.get("created_date"),
            )
            if unit is not None:
                review_units.append(unit)
        units.extend(_dedupe_units(review_units))

    return tuple(_dedupe_units(units))


def review_text_unit_count_from_payload(payload: Mapping[str, Any]) -> int:
    return len(canonical_review_units_from_payload(payload))


def review_set_hash_from_payload(payload: Mapping[str, Any]) -> str | None:
    """Return a stable SHA-256 hash for the review text sent to an LLM."""

    units = canonical_review_units_from_payload(payload)
    if not units:
        return None
    canonical = json.dumps(
        sorted(units, key=_unit_identity),
        sort_keys=True,
        ensure_ascii=False,
        separators=(",", ":"),
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()
