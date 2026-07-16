from __future__ import annotations

from modules.pdp.models import ListingObservation
from modules.pdp.sort_sequence_quality import (
    build_sort_sequence_quality_report,
    normalize_ranked_sort_modes,
)


def _observation(sort_mode: str, position: int, parent_id: str) -> ListingObservation:
    return ListingObservation(
        retailer="chewy",
        category_key="wet_cat_food",
        source_surface="category",
        sort_mode=sort_mode,
        page=1,
        position=position,
        pdp_url=f"https://www.chewy.com/product/dp/{parent_id}",
        parent_product_id=parent_id,
        product_name=f"Product {parent_id}",
    )


def test_normalize_ranked_sort_modes_removes_default_and_sale_modes() -> None:
    assert normalize_ranked_sort_modes(
        ["default", "newest", "sale_first", "best_selling", "newest"]
    ) == ("newest", "best_selling")


def test_build_sort_sequence_quality_report_fails_identical_ranked_sequences() -> None:
    observations = [
        *(_observation("newest", index, str(index)) for index in range(1, 6)),
        *(_observation("best_selling", index, str(index)) for index in range(1, 6)),
    ]

    report = build_sort_sequence_quality_report(observations)

    assert report["status"] == "failed"
    assert report["blocking_identical_sort_sequence_pairs"][0]["sort_modes"] == [
        "best_selling",
        "newest",
    ]


def test_build_sort_sequence_quality_report_warns_high_top_window_overlap() -> None:
    newest_ids = [str(index) for index in range(1, 11)]
    best_selling_ids = ["2", "1", "3", "4", "5", "6", "7", "8", "11", "12"]
    observations = [
        *(
            _observation("newest", index, parent_id)
            for index, parent_id in enumerate(newest_ids, start=1)
        ),
        *(
            _observation("best_selling", index, parent_id)
            for index, parent_id in enumerate(best_selling_ids, start=1)
        ),
    ]

    report = build_sort_sequence_quality_report(observations)

    assert report["status"] == "warning"
    assert report["blocking_identical_sort_sequence_pairs"] == []
    warning = report["warning_high_top_window_overlap_pairs"][0]
    assert warning["sort_modes"] == ["best_selling", "newest"]
    assert warning["top_window_overlap_count"] == 8
    assert warning["top_window_overlap_ratio"] == 0.8


def test_build_sort_sequence_quality_report_does_not_warn_unrelated_sort_overlap() -> (
    None
):
    observations = [
        *(_observation("top_rated", index, str(index)) for index in range(1, 7)),
        *(
            _observation("best_selling", index, parent_id)
            for index, parent_id in enumerate(["2", "1", "3", "4", "5", "7"], start=1)
        ),
    ]

    report = build_sort_sequence_quality_report(observations)

    assert report["status"] == "passed"
    assert report["warning_high_top_window_overlap_pairs"] == []


def test_build_sort_sequence_quality_report_ignores_default_sequences() -> None:
    observations = [
        *(_observation("default", index, str(index)) for index in range(1, 6)),
        *(_observation("newest", index, str(index)) for index in range(1, 6)),
    ]

    report = build_sort_sequence_quality_report(observations)

    assert report["status"] == "passed"
