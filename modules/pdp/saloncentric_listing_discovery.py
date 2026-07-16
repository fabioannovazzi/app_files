from __future__ import annotations

from collections import defaultdict
from collections.abc import Sequence
import math

from .models import ListingObservation

__all__ = [
    "category_listing_identity",
    "classify_listing_statuses",
    "listing_identity",
    "profile_to_category_key",
]


def profile_to_category_key(profile_name: str) -> str:
    text = str(profile_name or "").strip()
    if text.startswith("saloncentric_"):
        return text.split("saloncentric_", 1)[1]
    return text


def listing_identity(observation: ListingObservation) -> str:
    parent_id = str(observation.parent_product_id or "").strip()
    if parent_id:
        return parent_id
    return observation.pdp_url


def category_listing_identity(observation: ListingObservation) -> tuple[str, str]:
    return (observation.category_key, listing_identity(observation))


def classify_listing_statuses(
    observations: Sequence[ListingObservation],
    *,
    recent_share: float = 0.20,
    newest_sort_mode: str = "newest",
) -> dict[tuple[str, str], str]:
    if not observations:
        return {}

    by_category_identity: dict[tuple[str, str], list[ListingObservation]] = defaultdict(
        list
    )
    for observation in observations:
        by_category_identity[category_listing_identity(observation)].append(observation)

    by_category: dict[str, set[str]] = defaultdict(set)
    recent_rank_rows: dict[str, dict[str, tuple[int, int]]] = defaultdict(dict)
    for observation in observations:
        category_key, identity = category_listing_identity(observation)
        by_category[category_key].add(identity)
        if str(observation.sort_mode or "").strip().lower() != newest_sort_mode:
            continue
        rank = (int(observation.page), int(observation.position))
        current = recent_rank_rows[category_key].get(identity)
        if current is None or rank < current:
            recent_rank_rows[category_key][identity] = rank

    statuses: dict[tuple[str, str], str] = {}
    recent_identities_by_category: dict[str, set[str]] = defaultdict(set)
    bounded_share = min(max(float(recent_share), 0.0), 1.0)
    for category_key, identities in by_category.items():
        if not identities:
            continue
        category_size = len(identities)
        cutoff = min(category_size, max(1, math.ceil(category_size * bounded_share)))
        ranked = sorted(
            recent_rank_rows.get(category_key, {}).items(),
            key=lambda item: item[1],
        )
        recent_identities_by_category[category_key] = {
            identity for identity, _ in ranked[:cutoff]
        }

    for category_identity in by_category_identity:
        category_key, identity = category_identity
        statuses[category_identity] = (
            "new"
            if identity in recent_identities_by_category.get(category_key, set())
            else "rest"
        )

    return statuses
