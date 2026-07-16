from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable, Sequence
import math

from .models import ListingObservation


def profile_to_category_key(profile_name: str) -> str:
    """Return the category key for an Ulta PDP profile name."""

    text = str(profile_name or "").strip()
    if text.startswith("ulta_"):
        return text.split("ulta_", 1)[1]
    return text


def listing_identity(observation: ListingObservation) -> str:
    """Return the stable identity used for listing history comparisons."""

    parent_id = str(observation.parent_product_id or "").strip()
    if parent_id:
        return parent_id
    return observation.pdp_url


def category_listing_identity(observation: ListingObservation) -> tuple[str, str]:
    """Return the stable `(category, identity)` key for list-local status checks."""

    return (observation.category_key, listing_identity(observation))


def classify_listing_statuses(
    observations: Sequence[ListingObservation],
    *,
    recent_share: float = 0.20,
) -> dict[tuple[str, str], str]:
    """Classify current Ulta listing observations per category as `recent` or `rest`."""

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
        if observation.sort_mode != "new_arrivals":
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

    for category_identity, _rows in by_category_identity.items():
        category_key, identity = category_identity
        statuses[category_identity] = (
            "recent"
            if identity in recent_identities_by_category.get(category_key, set())
            else "rest"
        )

    return statuses


def collect_unseen_pdp_urls(
    observations: Iterable[ListingObservation],
    *,
    existing_parent_ids: set[str],
) -> list[str]:
    """Return unique PDP URLs that do not already exist in the local parent store."""

    unseen: list[str] = []
    seen_urls: set[str] = set()
    for observation in observations:
        if observation.pdp_url in seen_urls:
            continue
        parent_id = str(observation.parent_product_id or "").strip()
        if parent_id and parent_id in existing_parent_ids:
            continue
        unseen.append(observation.pdp_url)
        seen_urls.add(observation.pdp_url)
    return unseen


__all__ = [
    "category_listing_identity",
    "classify_listing_statuses",
    "collect_unseen_pdp_urls",
    "listing_identity",
    "profile_to_category_key",
]
