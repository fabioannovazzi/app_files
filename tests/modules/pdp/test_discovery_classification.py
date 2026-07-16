from __future__ import annotations

from modules.pdp.discovery_classification import (
    assign_pareto_from_most_popular,
    build_parent_sort_snapshot,
)
from modules.pdp.models import ListingObservation


def test_assign_pareto_from_most_popular_uses_20_30_50_split() -> None:
    observations = [
        ListingObservation(
            retailer="cosmoprofbeauty",
            category_key="permanent",
            source_surface="category",
            sort_mode="most_popular",
            page=1,
            position=index,
            pdp_url=f"https://www.cosmoprofbeauty.com/P{index}.html",
            parent_product_id=f"P{index}",
            product_name=f"Product {index}",
        )
        for index in range(1, 11)
    ]

    frame = assign_pareto_from_most_popular(frame=build_parent_sort_snapshot(observations))

    labels = dict(zip(frame.get_column("parent_product_id"), frame.get_column("pareto_class")))

    assert labels["P1"] == "A"
    assert labels["P2"] == "A"
    assert labels["P3"] == "B"
    assert labels["P5"] == "B"
    assert labels["P6"] == "C"
    assert labels["P10"] == "C"
