from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable, Sequence

from .models import ListingObservation

__all__ = [
    "EXCLUDED_RANKED_SORT_MODES",
    "HIGH_TOP_WINDOW_OVERLAP_THRESHOLD",
    "SORT_TOP_WINDOW_SIZE",
    "build_sort_sequence_quality_report",
    "normalize_ranked_sort_modes",
]

SORT_TOP_WINDOW_SIZE = 20
HIGH_TOP_WINDOW_OVERLAP_THRESHOLD = 0.80

EXCLUDED_RANKED_SORT_MODES = frozenset(
    {
        "",
        "default",
        "sale",
        "sale_first",
        "sales_first",
        "clearance",
        "promotion",
        "promotions",
    }
)
RECENT_RANKED_SORT_MODES = frozenset({"new_arrivals", "newest", "most_recent"})
POPULARITY_RANKED_SORT_MODES = frozenset(
    {
        "best_sellers",
        "best_selling",
        "bestselling",
        "top_sellers",
        "top_selling",
        "most_popular",
    }
)


def normalize_ranked_sort_modes(sort_modes: Sequence[str]) -> tuple[str, ...]:
    """Return rank-bearing sort modes, excluding default and promotion sorts."""

    normalized: list[str] = []
    seen: set[str] = set()
    for sort_mode in sort_modes:
        value = str(sort_mode or "").strip()
        key = value.lower()
        if key in EXCLUDED_RANKED_SORT_MODES or key in seen:
            continue
        normalized.append(value)
        seen.add(key)
    return tuple(normalized)


def _listing_identity(observation: ListingObservation) -> str:
    return str(observation.parent_product_id or observation.pdp_url or "").strip()


def _is_recent_popularity_pair(left_mode: str, right_mode: str) -> bool:
    left = left_mode.strip().lower()
    right = right_mode.strip().lower()
    return (
        left in RECENT_RANKED_SORT_MODES and right in POPULARITY_RANKED_SORT_MODES
    ) or (right in RECENT_RANKED_SORT_MODES and left in POPULARITY_RANKED_SORT_MODES)


def _ordered_sequence(observations: Sequence[ListingObservation]) -> list[str]:
    ordered = sorted(
        observations,
        key=lambda observation: (
            int(observation.page),
            int(observation.position),
            str(observation.pdp_url or ""),
        ),
    )
    return [
        identity
        for observation in ordered
        if (identity := _listing_identity(observation))
    ]


def _issue_payload(
    *,
    retailer: str,
    category_key: str,
    source_surface: str,
    sort_modes: tuple[str, str],
    sequence: Sequence[str],
) -> dict[str, object]:
    return {
        "retailer": retailer,
        "category_key": category_key,
        "source_surface": source_surface,
        "sort_modes": list(sort_modes),
        "product_count": len(sequence),
        "sample_product_ids": list(sequence[:10]),
    }


def _top_window_overlap_payload(
    *,
    retailer: str,
    category_key: str,
    source_surface: str,
    sort_modes: tuple[str, str],
    left_sequence: Sequence[str],
    right_sequence: Sequence[str],
    top_window_size: int,
    overlap_threshold: float,
) -> dict[str, object] | None:
    window_size = min(top_window_size, len(left_sequence), len(right_sequence))
    if window_size <= 0:
        return None
    left_window = list(left_sequence[:window_size])
    right_window = list(right_sequence[:window_size])
    overlap_ids = sorted(set(left_window) & set(right_window))
    overlap_ratio = len(overlap_ids) / window_size
    if overlap_ratio < overlap_threshold:
        return None
    return {
        "retailer": retailer,
        "category_key": category_key,
        "source_surface": source_surface,
        "sort_modes": list(sort_modes),
        "top_window_size": window_size,
        "top_window_overlap_count": len(overlap_ids),
        "top_window_overlap_ratio": overlap_ratio,
        "overlap_threshold": overlap_threshold,
        "sample_overlap_product_ids": overlap_ids[:10],
        "left_sample_product_ids": left_window[:10],
        "right_sample_product_ids": right_window[:10],
    }


def build_sort_sequence_quality_report(
    observations: Iterable[ListingObservation],
    *,
    min_products: int = 5,
    top_window_size: int = SORT_TOP_WINDOW_SIZE,
    high_top_window_overlap_threshold: float = HIGH_TOP_WINDOW_OVERLAP_THRESHOLD,
) -> dict[str, object]:
    """Find duplicate or suspiciously similar ranked sort mode captures."""

    grouped: dict[tuple[str, str, str], dict[str, list[ListingObservation]]] = (
        defaultdict(lambda: defaultdict(list))
    )
    for observation in observations:
        sort_mode = str(observation.sort_mode or "").strip()
        if sort_mode.lower() in EXCLUDED_RANKED_SORT_MODES:
            continue
        group_key = (
            str(observation.retailer or "").strip().lower(),
            str(observation.category_key or "").strip(),
            str(observation.source_surface or "").strip(),
        )
        if not all(group_key):
            continue
        grouped[group_key][sort_mode].append(observation)

    identical_pairs: list[dict[str, object]] = []
    high_top_window_overlap_pairs: list[dict[str, object]] = []
    for (retailer, category_key, source_surface), by_sort in sorted(grouped.items()):
        sequences = {
            sort_mode: _ordered_sequence(sort_observations)
            for sort_mode, sort_observations in by_sort.items()
        }
        sort_modes = sorted(sequences)
        for index, left_mode in enumerate(sort_modes):
            left_sequence = sequences[left_mode]
            for right_mode in sort_modes[index + 1 :]:
                right_sequence = sequences[right_mode]
                if (
                    len(left_sequence) < min_products
                    or len(right_sequence) < min_products
                ):
                    continue
                if left_sequence == right_sequence:
                    identical_pairs.append(
                        _issue_payload(
                            retailer=retailer,
                            category_key=category_key,
                            source_surface=source_surface,
                            sort_modes=(left_mode, right_mode),
                            sequence=left_sequence,
                        )
                    )
                    continue
                if not _is_recent_popularity_pair(left_mode, right_mode):
                    continue
                overlap_payload = _top_window_overlap_payload(
                    retailer=retailer,
                    category_key=category_key,
                    source_surface=source_surface,
                    sort_modes=(left_mode, right_mode),
                    left_sequence=left_sequence,
                    right_sequence=right_sequence,
                    top_window_size=top_window_size,
                    overlap_threshold=high_top_window_overlap_threshold,
                )
                if overlap_payload is not None:
                    high_top_window_overlap_pairs.append(overlap_payload)

    status = "passed"
    if high_top_window_overlap_pairs:
        status = "warning"
    if identical_pairs:
        status = "failed"

    return {
        "status": status,
        "min_products": int(min_products),
        "top_window_size": int(top_window_size),
        "high_top_window_overlap_threshold": float(high_top_window_overlap_threshold),
        "blocking_identical_sort_sequence_pairs": identical_pairs,
        "warning_high_top_window_overlap_pairs": high_top_window_overlap_pairs,
    }
